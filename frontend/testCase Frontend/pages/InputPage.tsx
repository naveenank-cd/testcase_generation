'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Image from 'next/image';
import {
  ArrowRight,
  CheckCircle2,
  ChevronRight,
  ExternalLink,
  FileCode2,
  FileText,
  FolderKanban,
  Globe,
  ImagePlus,
  Layers,
  ListOrdered,
  LoaderCircle,
  Lock,
  Plus,
  Radio,
  Search,
  Shield,
  Sparkles,
  StopCircle,
  Tag,
  Trash2,
  UploadCloud,
  X,
} from 'lucide-react';
import { DynamicListField } from '../components/DynamicListField';
import { ConfidenceRing } from '../components/TraceabilityUI';
import { EMPTY_PAYLOAD, FIELD_LABELS } from '../constants';
import { testCaseApi } from '../services/testCaseApi';
import { loadActiveProjectName, saveTestProjectArtifacts, useTestCaseWorkflowStore } from '../store/workflowStore';
import type {
  ApplicationFlow,
  ApplicationKnowledge,
  CrawlAnalysis,
  CrawlJob,
  DocumentSession,
  ManualInputPayload,
  ParsedDocumentStory,
} from '../types';
import { cleanPayload, friendlyError } from '../utils';

const VISIBLE_INPUT_FIELDS = ['user_stories', 'acceptance_criteria'] as const;
const IMAGE_MAX_SIZE_MB = Number(process.env.NEXT_PUBLIC_IMAGE_MAX_SIZE_MB ?? 10);
const DOCUMENT_MAX_SIZE_MB = Number(process.env.NEXT_PUBLIC_DOCUMENT_MAX_SIZE_MB ?? 10);

export function InputPage() {
  const router = useRouter();
  const { hydrate, setWorkflow, setKnowledgeAndFlow } = useTestCaseWorkflowStore();
  const [currentStep, setCurrentStep] = useState<'input' | 'crawling' | 'knowledge_review'>('input');
  const [projectName, setProjectName] = useState(loadActiveProjectName);
  const [payload, setPayload] = useState<ManualInputPayload>(() => structuredClone(EMPTY_PAYLOAD));
  const [submitting, setSubmitting] = useState(false);
  const [mockMode, setMockMode] = useState(false);
  const [confidenceThreshold, setConfidenceThreshold] = useState(95);
  const [error, setError] = useState('');
  const [userStoryError, setUserStoryError] = useState('');
  const [urlError, setUrlError] = useState('');
  const [imageError, setImageError] = useState('');
  const [referenceImage, setReferenceImage] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState('');
  const [imageDescription, setImageDescription] = useState('');
  const [analysisStatus, setAnalysisStatus] = useState('');
  const [documentSession, setDocumentSession] = useState<DocumentSession | null>(null);
  const [documentStories, setDocumentStories] = useState<ParsedDocumentStory[]>([]);
  const [documentLoading, setDocumentLoading] = useState(false);
  const [documentError, setDocumentError] = useState('');

  // Application Crawl State
  const [applicationUrl, setApplicationUrl] = useState('');
  const [authMode, setAuthMode] = useState<'none' | 'credentials'>('none');
  const [authUsername, setAuthUsername] = useState('');
  const [authPassword, setAuthPassword] = useState('');
  const [crawlScope, setCrawlScope] = useState<'full_application' | 'specific_page'>('full_application');
  const [crawlJob, setCrawlJob] = useState<CrawlJob | null>(null);
  const [crawlProgressInfo, setCrawlProgressInfo] = useState<string>('Initializing Playwright browser crawler…');
  const [discoveredKnowledge, setDiscoveredKnowledge] = useState<ApplicationKnowledge | null>(null);
  const [discoveredFlow, setDiscoveredFlow] = useState<ApplicationFlow | null>(null);
  const [activeTab, setActiveTab] = useState<'pages' | 'flow' | 'locators' | 'forms'>('pages');

  useEffect(() => hydrate(), [hydrate]);

  const isCrawling = Boolean(crawlJob && ['queued', 'running', 'stopping'].includes(crawlJob.status));

  // Poll crawl job status
  useEffect(() => {
    if (!crawlJob?.job_id || !isCrawling) return;
    let disposed = false;
    let timer: number | undefined;

    const poll = async () => {
      try {
        const current = await testCaseApi.getCrawlJob(crawlJob.job_id);
        if (disposed) return;
        setCrawlJob(current);

        if (current.progress) {
          const pagesDone = current.progress.pages_completed ?? 0;
          const elementsCount = current.progress.elements_found ?? 0;
          const currentScanningUrl = current.progress.current_url ? ` · Scanning ${current.progress.current_url}` : '';
          setCrawlProgressInfo(`Visited ${pagesDone} pages · Found ${elementsCount} interactive elements${currentScanningUrl}`);
        }

        if (current.status === 'completed') {
          // Fetch structured knowledge and flow from backend
          const crawlId = current.result?.crawl_id || crawlJob.job_id;
          const knowledgeData = await testCaseApi.getApplicationKnowledge(crawlId).catch(() => null);
          if (knowledgeData?.application_knowledge) {
            setDiscoveredKnowledge(knowledgeData.application_knowledge);
            setDiscoveredFlow(knowledgeData.application_flow ?? null);
            setKnowledgeAndFlow(knowledgeData.application_knowledge, knowledgeData.application_flow ?? null);
          } else if (current.result) {
            // Build fallback knowledge from result
            const rawPages = (current.result.scripts || []).map((s) => ({
              url: s.page_url || applicationUrl,
              route_path: new URL(s.page_url || applicationUrl).pathname || '/',
              title: s.name || 'Discovered Page',
              element_count: s.page_elements?.length || 0,
              interactive_elements_count: s.page_elements?.length || 0,
              form_count: 0,
            }));
            const mockKnowledge: ApplicationKnowledge = {
              application_url: applicationUrl,
              crawl_id: current.result.crawl_id,
              crawl_status: 'crawl_completed',
              pages: rawPages,
              actions: [],
              navigation_paths: [],
              forms: [],
              verified_locators: {},
              summary: {
                total_pages: rawPages.length,
                total_elements: current.result.discovered_elements?.length || 0,
                total_actions: 0,
                total_navigation_paths: 0,
                total_forms: 0,
                crawl_status: 'crawl_completed',
                application_url: applicationUrl,
              },
            };
            setDiscoveredKnowledge(mockKnowledge);
          }
          setCurrentStep('knowledge_review');
        } else if (current.status === 'failed') {
          setError(current.error || 'The application crawl could not be completed.');
          setCurrentStep('input');
        }
      } catch (err) {
        if (!disposed) {
          setError(friendlyError(err));
        }
      } finally {
        if (!disposed && isCrawling) {
          timer = window.setTimeout(poll, 1500);
        }
      }
    };

    void poll();
    return () => {
      disposed = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [crawlJob?.job_id, isCrawling, applicationUrl, setKnowledgeAndFlow]);

  const updateList = (key: Exclude<keyof ManualInputPayload, 'tech_stack'>, values: string[]) =>
    setPayload((current) => ({ ...current, [key]: values }));

  const uploadReferenceImage = (file?: File) => {
    if (!file) return;
    if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) {
      setImageError('Select a PNG, JPEG, or WebP image.');
      return;
    }
    if (file.size > IMAGE_MAX_SIZE_MB * 1024 * 1024) {
      setImageError(`The image must be ${IMAGE_MAX_SIZE_MB} MB or smaller.`);
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      setReferenceImage(file);
      setImagePreview(String(reader.result));
      setImageError('');
    };
    reader.onerror = () => setImageError('The image could not be read.');
    reader.readAsDataURL(file);
  };

  const uploadDocument = async (file?: File) => {
    if (!file) return;
    const extension = file.name.split('.').pop()?.toLowerCase();
    if (!extension || !['pdf', 'docx', 'txt'].includes(extension)) {
      setDocumentError('Unsupported file. Select a PDF, DOCX, or TXT document.');
      return;
    }
    if (file.size > DOCUMENT_MAX_SIZE_MB * 1024 * 1024) {
      setDocumentError(`The document must be ${DOCUMENT_MAX_SIZE_MB} MB or smaller.`);
      return;
    }
    setDocumentLoading(true);
    setDocumentError('');
    try {
      const session = await testCaseApi.uploadDocument(file);
      setDocumentSession(session);
      setDocumentStories(session.stories);
      setPayload((current) => ({
        ...current,
        user_stories: session.stories.map((story) => story.text),
        acceptance_criteria: session.stories.flatMap((story) => story.acceptance_criteria),
      }));
      setUserStoryError('');
    } catch (requestError) {
      setDocumentSession(null);
      setDocumentStories([]);
      setDocumentError(friendlyError(requestError));
    } finally {
      setDocumentLoading(false);
    }
  };

  const removeDocument = () => {
    setDocumentSession(null);
    setDocumentStories([]);
    setDocumentError('');
  };

  // Step 1: Trigger Application Crawl
  const startApplicationCrawl = async (event: React.FormEvent) => {
    event.preventDefault();
    if (submitting || isCrawling) return;

    const cleaned = cleanPayload(payload);
    if (documentSession && !documentStories.length) {
      setUserStoryError('The document must contain at least one user story.');
      return;
    }
    if (!cleaned.user_stories.length) {
      setUserStoryError('Enter at least one user story to define requirements before crawling.');
      return;
    }
    if (!applicationUrl.trim()) {
      setUrlError('Enter a valid deployed application URL to start application crawling.');
      return;
    }

    try {
      new URL(applicationUrl.trim());
    } catch {
      setUrlError('Please enter a valid absolute URL (for example: https://example.com).');
      return;
    }

    setUserStoryError('');
    setUrlError('');
    setError('');
    setSubmitting(true);

    try {
      if (referenceImage) {
        setAnalysisStatus('Analyzing image locally…');
        const analysis = await testCaseApi.uploadImage(referenceImage, imageDescription, confidenceThreshold / 100);
        cleaned.image_ids = [analysis.image_id];
        setAnalysisStatus(`Image analyzed: ${analysis.screen_type}`);
      }
      if (documentSession) {
        await testCaseApi.updateDocumentSession(documentSession.session_id, documentStories);
      }

      setCurrentStep('crawling');
      setCrawlProgressInfo('Launching Playwright Chromium crawler in browser engine…');

      const authPayload =
        authMode === 'credentials' && authUsername.trim() && authPassword
          ? {
              auth_mode: 'credentials' as const,
              identifier: authUsername.trim(),
              email: authUsername.trim(),
              password: authPassword,
            }
          : undefined;

      const job = await testCaseApi.startCrawlJob(applicationUrl.trim(), {
        testing_scope: crawlScope,
        authentication: authPayload,
      });
      setCrawlJob(job);
    } catch (requestError) {
      setError(friendlyError(requestError));
      setCurrentStep('input');
    } finally {
      setSubmitting(false);
    }
  };

  const stopCrawl = async () => {
    if (!crawlJob?.job_id) return;
    try {
      const stopped = await testCaseApi.stopCrawlJob(crawlJob.job_id);
      setCrawlJob(stopped);
    } catch (err) {
      setError(friendlyError(err));
    }
  };

  // Step 3: Approve Application Flow & Start Scenario Generation
  const approveAndGenerateScenarios = async () => {
    if (submitting) return;
    if (!discoveredKnowledge) {
      setError('Valid Application Knowledge is required before test scenario generation can proceed.');
      return;
    }
    setSubmitting(true);
    setError('');

    try {
      const cleaned = cleanPayload(payload);
      cleaned.application_url = applicationUrl.trim();
      cleaned.crawl_id = discoveredKnowledge.crawl_id || crawlJob?.job_id || undefined;
      cleaned.application_knowledge = discoveredKnowledge;
      cleaned.application_flow = discoveredFlow || undefined;

      const response = await testCaseApi.startWorkflow({
        source_type: 'manual',
        input_payload: cleaned,
        mock_mode: mockMode,
        confidence_threshold: confidenceThreshold / 100,
        application_url: applicationUrl.trim(),
        crawl_id: discoveredKnowledge.crawl_id || crawlJob?.job_id || undefined,
        application_knowledge: discoveredKnowledge,
        application_flow: discoveredFlow || undefined,
      });

      setWorkflow(response.workflow_id, response.project_id, projectName.trim() || undefined);
      saveTestProjectArtifacts(response.workflow_id, null, null, null, null, discoveredKnowledge, discoveredFlow);
      router.push('/test-case-generation/progress');
    } catch (requestError) {
      setError(friendlyError(requestError));
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* HEADER HERO */}
      <div className="relative flex min-h-[44vh] overflow-hidden rounded-[2rem] border border-primary/20 bg-gradient-to-br from-primary/15 via-card/90 to-card p-6 shadow-2xl shadow-primary/10 sm:p-10 lg:p-12">
        <div className="relative z-10 flex max-w-5xl items-start gap-4 self-center">
          <div className="rounded-xl bg-primary p-3 text-primary-foreground shadow-xl shadow-primary/30">
            <Sparkles className="h-6 w-6" />
          </div>
          <div className="min-w-0">
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-primary">Crawl-First Test Automation Engine</p>
            <h1 className="mt-3 text-2xl font-extrabold sm:text-3xl lg:text-4xl text-foreground">
              {currentStep === 'input' && 'Define Requirements and Target Application'}
              {currentStep === 'crawling' && 'Executing Application Crawl & Discovery'}
              {currentStep === 'knowledge_review' && 'Review Application Knowledge and Flow'}
            </h1>
            <p className="mt-4 max-w-2xl text-sm leading-6 text-muted-foreground sm:text-base">
              {currentStep === 'input' && 'Provide user stories and your deployed application address. The system inspects live pages, interactive controls, and navigation flows before generating test scenarios.'}
              {currentStep === 'crawling' && 'The real Playwright browser is inspecting application pages, interactive elements, forms, and navigation relationships.'}
              {currentStep === 'knowledge_review' && 'Application structure has been successfully extracted. Verify discovered pages, locators, and navigation sequences before generating test scenarios.'}
            </p>
            {/* WORKFLOW PIPELINE TRACKER */}
            <div className="mt-6 flex flex-wrap items-center gap-2 text-xs font-bold uppercase tracking-wider text-muted-foreground">
              <span className={currentStep === 'input' ? 'text-primary' : 'text-foreground'}>01 · Requirement Input</span>
              <span className="text-muted-foreground/40">→</span>
              <span className={currentStep === 'crawling' ? 'text-primary font-extrabold' : currentStep === 'knowledge_review' ? 'text-foreground' : ''}>02 · Application Crawl</span>
              <span className="text-muted-foreground/40">→</span>
              <span className={currentStep === 'knowledge_review' ? 'text-primary font-extrabold' : ''}>03 · Application Knowledge & Flow</span>
              <span className="text-muted-foreground/40">→</span>
              <span>04 · Test Scenarios</span>
              <span className="text-muted-foreground/40">→</span>
              <span>05 · Test Cases</span>
              <span className="text-muted-foreground/40">→</span>
              <span>06 · Automation Scripts</span>
            </div>
          </div>
        </div>
      </div>

      {error && (
        <div role="alert" className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-600 dark:text-red-300">
          {error}
        </div>
      )}

      {/* STEP 1: REQUIREMENT AND APPLICATION INPUT */}
      {currentStep === 'input' && (
        <form onSubmit={startApplicationCrawl} className="space-y-6">
          {/* Project Name */}
          <section className="rounded-2xl border border-primary/20 bg-card p-5 shadow-sm sm:p-6">
            <div className="flex items-center gap-3 mb-3">
              <FolderKanban className="h-5 w-5 text-primary" />
              <div>
                <h2 className="font-semibold text-foreground">Project Name</h2>
                <p className="mt-0.5 text-xs text-muted-foreground">Give your test generation project a clear title.</p>
              </div>
            </div>
            <input
              type="text"
              value={projectName}
              onChange={(e) => setProjectName(e.target.value)}
              placeholder="e.g., Customer Portal Authentication and Account Settings Test Suite"
              className="w-full rounded-xl border border-input bg-background p-3.5 text-sm font-semibold outline-none focus:border-primary focus:ring-2 focus:ring-primary/10 transition placeholder:text-muted-foreground/60"
            />
          </section>

          {/* Deployed Application Target Section */}
          <section className="rounded-2xl border border-primary/20 bg-card p-5 shadow-sm sm:p-6">
            <div className="flex items-center gap-3 mb-3">
              <Globe className="h-5 w-5 text-primary" />
              <div>
                <h2 className="font-semibold text-foreground">Deployed Application Target Address</h2>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  The real Playwright crawler will inspect this application URL before test scenario generation.
                </p>
              </div>
            </div>
            <div className="space-y-4">
              <div>
                <label htmlFor="application-url-input" className="block text-xs font-bold uppercase tracking-wider text-muted-foreground mb-1.5">
                  Application Target URL <span className="text-red-500">*</span>
                </label>
                <input
                  id="application-url-input"
                  type="url"
                  value={applicationUrl}
                  onChange={(e) => setApplicationUrl(e.target.value)}
                  placeholder="https://example.com or http://localhost:3000"
                  required
                  className="w-full rounded-xl border border-input bg-background p-3.5 text-sm font-semibold outline-none focus:border-primary focus:ring-2 focus:ring-primary/10 transition placeholder:text-muted-foreground/60"
                />
                {urlError && <p className="mt-1 text-xs text-red-500">{urlError}</p>}
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider text-muted-foreground mb-1.5">
                    Testing Scope
                  </label>
                  <select
                    value={crawlScope}
                    onChange={(e) => setCrawlScope(e.target.value as any)}
                    className="w-full rounded-xl border border-input bg-background p-3 text-sm font-medium outline-none focus:border-primary"
                  >
                    <option value="full_application">Full Application Discovery</option>
                    <option value="specific_page">Specific Page Only</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider text-muted-foreground mb-1.5">
                    Authentication Credentials
                  </label>
                  <select
                    value={authMode}
                    onChange={(e) => setAuthMode(e.target.value as any)}
                    className="w-full rounded-xl border border-input bg-background p-3 text-sm font-medium outline-none focus:border-primary"
                  >
                    <option value="none">Public Application (No Credentials Required)</option>
                    <option value="credentials">Sign In Credentials</option>
                  </select>
                </div>
              </div>

              {authMode === 'credentials' && (
                <div className="grid gap-4 rounded-xl border border-primary/20 bg-primary/5 p-4 sm:grid-cols-2">
                  <div>
                    <label className="block text-xs font-semibold text-foreground mb-1">Username or Email Address</label>
                    <input
                      type="text"
                      value={authUsername}
                      onChange={(e) => setAuthUsername(e.target.value)}
                      placeholder="test-user@example.com"
                      className="w-full rounded-lg border border-input bg-background p-2.5 text-sm outline-none focus:border-primary"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-foreground mb-1">Password</label>
                    <input
                      type="password"
                      value={authPassword}
                      onChange={(e) => setAuthPassword(e.target.value)}
                      placeholder="••••••••"
                      className="w-full rounded-lg border border-input bg-background p-2.5 text-sm outline-none focus:border-primary"
                    />
                  </div>
                </div>
              )}
            </div>
          </section>

          {/* User Stories and Acceptance Criteria */}
          <section className="rounded-2xl border border-border bg-card p-5 shadow-sm sm:p-6">
            <div className="flex items-start gap-3 mb-4">
              <FileText className="mt-0.5 h-5 w-5 text-primary" />
              <div>
                <h2 className="font-semibold">User Stories and Acceptance Criteria</h2>
                <p className="mt-1 text-xs text-muted-foreground">
                  Provide functional specifications or upload a requirements document (PDF, Word Document, or Plain Text).
                </p>
              </div>
            </div>

            {!documentSession ? (
              <label className={`mb-6 flex cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-input bg-background px-6 py-8 text-center hover:border-primary hover:bg-primary/5 ${documentLoading ? 'pointer-events-none opacity-60' : ''}`}>
                {documentLoading ? <LoaderCircle className="h-8 w-8 animate-spin text-primary" /> : <UploadCloud className="h-8 w-8 text-muted-foreground" />}
                <span className="mt-3 text-sm font-semibold">{documentLoading ? 'Uploading and extracting stories…' : 'Upload Requirements Specification Document'}</span>
                <input type="file" accept=".pdf,.docx,.txt" className="sr-only" disabled={documentLoading} onChange={(event) => { void uploadDocument(event.target.files?.[0]); event.currentTarget.value = ''; }} />
              </label>
            ) : (
              <div className="mb-6 space-y-4">
                <div className="flex items-center justify-between rounded-xl border border-primary/20 bg-primary/5 p-3">
                  <div>
                    <p className="text-sm font-semibold">{documentSession.filename}</p>
                    <p className="text-xs text-muted-foreground">{documentStories.length} user stories extracted</p>
                  </div>
                  <button type="button" onClick={removeDocument} className="rounded-lg p-2 text-red-500 hover:bg-red-500/10" aria-label="Remove document">
                    <X className="h-4 w-4" />
                  </button>
                </div>
              </div>
            )}

            {!documentSession && (
              <div className="grid gap-6 lg:grid-cols-2">
                {VISIBLE_INPUT_FIELDS.map((key) => (
                  <DynamicListField
                    key={key}
                    label={FIELD_LABELS[key]}
                    values={payload[key]}
                    required={key === 'user_stories'}
                    recommended={key === 'acceptance_criteria'}
                    error={key === 'user_stories' ? userStoryError : undefined}
                    onChange={(values) => updateList(key, values)}
                  />
                ))}
              </div>
            )}
          </section>

          {/* Wireframe Screenshot */}
          <section className="rounded-2xl border border-border bg-card p-5 shadow-sm sm:p-6">
            <div className="flex items-center gap-3">
              <ImagePlus className="h-5 w-5 text-primary" />
              <div>
                <h2 className="font-semibold">User Interface Wireframe or Screenshot</h2>
                <p className="mt-1 text-xs text-muted-foreground">Optional visual reference image (PNG, JPEG, or WebP).</p>
              </div>
            </div>
            {!imagePreview ? (
              <label className="mt-4 flex cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-input bg-background px-6 py-8 text-center hover:border-primary hover:bg-primary/5">
                <ImagePlus className="h-8 w-8 text-muted-foreground" />
                <span className="mt-3 text-sm font-semibold">Choose a wireframe or application screenshot</span>
                <input type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" onChange={(event) => uploadReferenceImage(event.target.files?.[0])} />
              </label>
            ) : (
              <div className="relative mt-4 overflow-hidden rounded-xl border border-border bg-background p-3">
                <Image src={imagePreview} alt="Screenshot preview" width={1200} height={700} unoptimized className="max-h-80 w-full rounded-lg object-contain" />
                <button type="button" onClick={() => { setReferenceImage(null); setImagePreview(''); }} className="absolute right-5 top-5 rounded-full bg-background/90 p-2 text-red-500 shadow" aria-label="Remove image">
                  <X className="h-4 w-4" />
                </button>
              </div>
            )}
            {analysisStatus && <p className="mt-3 text-sm font-medium text-primary">{analysisStatus}</p>}
          </section>

          {/* Action Submission */}
          <div className="flex justify-end gap-4">
            <button
              type="submit"
              disabled={submitting}
              className="inline-flex min-w-60 items-center justify-center gap-2.5 rounded-xl bg-primary px-7 py-3.5 text-sm font-bold text-primary-foreground shadow-xl shadow-primary/25 transition hover:bg-primary/90 disabled:opacity-60"
            >
              {submitting ? (
                <>
                  <LoaderCircle className="h-4 w-4 animate-spin" /> Preparing Crawler…
                </>
              ) : (
                <>
                  Start Application Discovery and Crawl <ArrowRight className="h-4 w-4" />
                </>
              )}
            </button>
          </div>
        </form>
      )}

      {/* STEP 2: LIVE CRAWL IN PROGRESS */}
      {currentStep === 'crawling' && (
        <div className="rounded-2xl border border-primary/30 bg-card p-8 shadow-xl text-center space-y-6">
          <div className="flex justify-center">
            <div className="relative flex h-20 w-20 items-center justify-center rounded-full bg-primary/10 text-primary">
              <LoaderCircle className="h-10 w-10 animate-spin" />
              <Globe className="absolute h-5 w-5" />
            </div>
          </div>
          <div>
            <h2 className="text-xl font-bold text-foreground">Crawling Deployed Application</h2>
            <p className="mt-2 text-sm text-muted-foreground">{applicationUrl}</p>
            <p className="mt-3 text-sm font-semibold text-primary">{crawlProgressInfo}</p>
          </div>

          <div className="flex justify-center gap-4">
            <button
              type="button"
              onClick={stopCrawl}
              className="inline-flex items-center gap-2 rounded-xl border border-red-500/30 bg-red-500/10 px-5 py-2.5 text-sm font-bold text-red-600 hover:bg-red-500/20"
            >
              <StopCircle className="h-4 w-4" /> Stop Crawl and Generate Knowledge
            </button>
          </div>
        </div>
      )}

      {/* STEP 3: DISCOVERED APPLICATION KNOWLEDGE & FLOW REVIEW */}
      {currentStep === 'knowledge_review' && discoveredKnowledge && (
        <div className="space-y-6">
          <div className="rounded-2xl border border-emerald-500/30 bg-emerald-500/10 p-5 text-emerald-800 dark:text-emerald-300 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <CheckCircle2 className="h-6 w-6 text-emerald-600 dark:text-emerald-400 shrink-0" />
              <div>
                <p className="font-bold text-sm">Application Discovery Successfully Completed</p>
                <p className="text-xs text-emerald-700 dark:text-emerald-300/90 mt-0.5">
                  Discovered {discoveredKnowledge.pages.length} pages, {discoveredKnowledge.summary.total_elements} interactive elements, and {discoveredKnowledge.forms.length} forms from {discoveredKnowledge.application_url}.
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setCurrentStep('input')}
              className="text-xs font-bold underline hover:no-underline"
            >
              Reconfigure Crawl
            </button>
          </div>

          {/* Navigation Tabs for Knowledge */}
          <div className="flex gap-2 border-b border-border pb-2">
            {[
              { id: 'pages', label: `Discovered Pages (${discoveredKnowledge.pages.length})`, icon: Layers },
              { id: 'flow', label: `Application Navigation Flow (${discoveredFlow?.sequences.length || 0})`, icon: ListOrdered },
              { id: 'forms', label: `Discovered Forms (${discoveredKnowledge.forms.length})`, icon: FileText },
              { id: 'locators', label: `Verified Playwright Locators (${Object.keys(discoveredKnowledge.verified_locators).length})`, icon: Tag },
            ].map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                type="button"
                onClick={() => setActiveTab(id as any)}
                className={`inline-flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-bold transition ${
                  activeTab === id
                    ? 'bg-primary text-primary-foreground shadow-sm'
                    : 'bg-muted/60 text-muted-foreground hover:bg-muted'
                }`}
              >
                <Icon className="h-4 w-4" />
                {label}
              </button>
            ))}
          </div>

          {/* TAB 1: PAGES */}
          {activeTab === 'pages' && (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {discoveredKnowledge.pages.map((page, idx) => (
                <div key={idx} className="rounded-xl border border-border bg-card p-4 shadow-sm space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="rounded-md bg-primary/10 px-2 py-0.5 text-[10px] font-bold text-primary">
                      {page.module_name || 'Module'}
                    </span>
                    <span className="text-[11px] text-muted-foreground">{page.element_count} elements</span>
                  </div>
                  <h3 className="font-bold text-sm text-foreground">{page.title || 'Discovered Page'}</h3>
                  <p className="text-xs font-mono text-muted-foreground truncate">{page.route_path}</p>
                </div>
              ))}
            </div>
          )}

          {/* TAB 2: APPLICATION NAVIGATION FLOW */}
          {activeTab === 'flow' && discoveredFlow && (
            <div className="space-y-4">
              {discoveredFlow.sequences.map((seq, idx) => (
                <div key={idx} className="rounded-xl border border-primary/20 bg-card p-5 shadow-sm space-y-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="rounded-md bg-purple-500/10 px-2 py-0.5 text-[10px] font-bold text-purple-600 dark:text-purple-400">
                        {seq.identified_module || 'User Journey Sequence'}
                      </span>
                      <h3 className="font-bold text-base text-foreground mt-1">{seq.name}</h3>
                    </div>
                    <span className="text-xs text-muted-foreground">{seq.steps.length} Steps</span>
                  </div>
                  <div className="space-y-2">
                    {seq.steps.map((step, sIdx) => (
                      <div key={sIdx} className="flex items-start gap-3 rounded-lg border border-border/70 bg-background/60 p-3 text-xs">
                        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary/10 text-primary font-bold text-[10px]">
                          {step.step_number}
                        </span>
                        <div className="flex-1 min-w-0">
                          <p className="font-semibold text-foreground">{step.action}</p>
                          {step.verified_locator && (
                            <p className="font-mono text-[11px] text-muted-foreground mt-0.5 truncate">
                              Locator: {step.verified_locator}
                            </p>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* TAB 3: FORMS */}
          {activeTab === 'forms' && (
            <div className="space-y-4">
              {discoveredKnowledge.forms.map((form, idx) => (
                <div key={idx} className="rounded-xl border border-border bg-card p-4 shadow-sm space-y-3">
                  <h3 className="font-bold text-sm text-foreground">{form.form_name}</h3>
                  <p className="text-xs text-muted-foreground">Page: {form.page_url}</p>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {form.fields.map((f, fIdx) => (
                      <div key={fIdx} className="rounded-lg border border-border/60 bg-background p-2.5 text-xs">
                        <p className="font-semibold text-foreground">{f.label || f.name || 'Input field'}</p>
                        <p className="text-[11px] text-muted-foreground font-mono mt-0.5">{f.verified_locator}</p>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* TAB 4: LOCATORS */}
          {activeTab === 'locators' && (
            <div className="rounded-xl border border-border bg-card p-4 space-y-2 max-h-96 overflow-y-auto font-mono text-xs">
              {Object.entries(discoveredKnowledge.verified_locators).map(([key, loc], idx) => (
                <div key={idx} className="flex justify-between border-b border-border/50 py-1.5 gap-4">
                  <span className="text-muted-foreground truncate">{key}</span>
                  <span className="text-primary font-bold shrink-0">{loc}</span>
                </div>
              ))}
            </div>
          )}

          {/* PROCEED ACTION */}
          <div className="flex justify-end gap-4 pt-4 border-t border-border">
            <button
              type="button"
              onClick={approveAndGenerateScenarios}
              disabled={submitting}
              className="inline-flex min-w-72 items-center justify-center gap-2.5 rounded-xl bg-primary px-8 py-4 text-sm font-bold text-primary-foreground shadow-xl shadow-primary/30 transition hover:bg-primary/90 disabled:opacity-60"
            >
              {submitting ? (
                <>
                  <LoaderCircle className="h-4 w-4 animate-spin" /> Generating Test Scenarios…
                </>
              ) : (
                <>
                  Approve Application Flow & Generate Test Scenarios <ArrowRight className="h-4 w-4" />
                </>
              )}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
