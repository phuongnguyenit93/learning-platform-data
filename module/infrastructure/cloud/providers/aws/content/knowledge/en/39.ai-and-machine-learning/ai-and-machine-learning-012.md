# Transcribe, Translate, Polly, and Language Processing Integration

Amazon Transcribe, Amazon Translate, and Amazon Polly address three distinct stages in language processing applications:

- **Amazon Transcribe:** converts speech to text (speech-to-text).
- **Amazon Translate:** translates text between source and target languages (machine translation).
- **Amazon Polly:** converts text to speech (text-to-speech).

Combining these three services enables building captions, meeting transcripts, multilingual contact centers, learning content, accessibility applications, and spoken content delivery systems. However, not every language is supported identically across all three services. Specifically, Vietnamese is recognized by Transcribe and translated by Translate, yet is not currently in the list of languages/voices supported by Polly. Pipeline designs must verify each service's capabilities by language, feature, and Region before deployment.

This lesson belongs to the **AI and machine learning** chapter in the CLOUD_PROVIDERS_AWS module. The module helps learners explore the AWS ecosystem from Regions/AZs, IAM, and VPCs to compute, storage, databases, integration, and serverless—building skills to choose services and design and deploy applications that are secure, observable, resilient, and cost-controlled.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish speech-to-text, machine translation, and text-to-speech.
- Choose between batch transcription and streaming transcription in Amazon Transcribe.
- Configure languages, channel identification, speaker diarization, custom vocabulary, and vocabulary filtering per supported capabilities.
- Use Amazon Translate for real-time text, document translation, and batch translation.
- Apply custom terminology, parallel data, and translation customization options.
- Select engines, voices, output formats, SSML, lexicons, and speech marks in Amazon Polly.
- Design audio and text processing pipelines using S3, EventBridge, Step Functions, Lambda, SQS, SNS, and DynamoDB.
- Integrate using the AWS SDK for Java 2.x and the AWS CLI.
- Protect audio, transcripts, translations, and audio outputs with IAM, KMS, S3 policies, retention, and sensitive data controls.
- Measure pipeline quality, latency, reliability, and costs.

## 1. The Big Picture: Three Services, Three Tasks

| Service | Input | Output | Typical use cases |
|---|---|---|---|
| Amazon Transcribe | Audio/video with speech or audio streams | Transcript, timestamps, confidence, speaker/channel metadata per configuration | Subtitles, meeting notes, searchable recordings, call analytics |
| Amazon Translate | Text or documents | Translated text/documents | Multilingual apps, translating emails, website content, documents |
| Amazon Polly | Text or SSML | Synthesized audio, speech marks in separate requests | Reading content aloud, voice prompts, narration, accessibility |

~~~mermaid
flowchart LR
    A[Input audio] --> B[Amazon Transcribe]
    B --> C[Source transcript]
    C --> D[Amazon Translate]
    D --> E[Target-language text]
    E --> F[Amazon Polly]
    F --> G[Output audio]
    C --> H[S3 / Search / Analytics]
    E --> H
    G --> I[Application / CDN]
~~~

Each step has its own latency, limits, language support, IAM permissions, and costs. If the input is Vietnamese, Transcribe can produce a `vi-VN` transcript and Translate can translate using language code `vi`; Polly requires a language and voice from its supported list. If the product requires playback in Vietnamese, another TTS solution must be chosen for the final step.

## 2. Checking Language Support Before Designing

This is mandatory when building multilingual applications. Baseline language availability does not mean every feature exists for that language.

### 2.1. Vietnamese Support Across the Three Services

| Capability | Amazon Transcribe | Amazon Translate | Amazon Polly |
|---|---|---|---|
| Language | Vietnamese `vi-VN` | Vietnamese `vi` | Not in the current supported language list |
| Batch | Yes | Yes | Yes for text in supported languages/voices |
| Real-time/streaming | Streaming transcription supported | Real-time text translation supported | No Vietnamese voice available for synthesis |
| Feature limitations | No PII redaction, custom language models, or Call Analytics for `vi-VN` in the current feature support matrix | Profanity masking is not supported for Vietnamese; brevity applies only to real-time text translation | Must translate text into a supported voice language or use another TTS provider |

Key points to remember:

- Transcribe supports batch and streaming for `vi-VN`. The current language table also lists number normalization for batch and acronym handling for batch/streaming.
- Transcribe does not support PII redaction for `vi-VN`. Never assume Vietnamese transcripts automatically strip names, phone numbers, addresses, or account details.
- Amazon Translate supports Vietnamese with language code `vi`. Extended features such as formality, brevity, profanity masking, and parallel data have separate support matrices.
- Amazon Translate does not apply profanity masking to Vietnamese. If content requires moderation, build an appropriate inspection layer and include human review when needed.
- Polly's voice catalog currently has no Vietnamese voice. Do not send Vietnamese text to Polly expecting Vietnamese speech.

Support matrices can change over time. Before releasing, verify the supported languages page, feature matrix, voice catalog, and Region compatibility for each service.

### 2.2. Language Codes Differ Across Services

| Service | Example Vietnamese code | Usage |
|---|---|---|
| Transcribe | `vi-VN` | `LanguageCode` |
| Translate | `vi` | `SourceLanguageCode` or `TargetLanguageCode` |
| Polly | No current Vietnamese code | Choose a voice ID from a supported language |

Do not pass `vi-VN` to Translate or `vi` to Transcribe. Each API uses its own language code convention.

## 3. Amazon Transcribe: Speech-to-Text

Amazon Transcribe is an Automatic Speech Recognition (ASR) service. It analyzes audio and returns transcripts with metadata so applications can display, search, or process them further.

### 3.1. Batch Transcription vs. Streaming Transcription

| Criterion | Batch transcription | Streaming transcription |
|---|---|---|
| Input | Media files in Amazon S3 | Audio streamed continuously over HTTP/2 or WebSocket |
| Output | Asynchronous job; results saved as transcript files | Partial and final results emitted during the stream |
| Best fit | Recorded meetings, podcasts, videos, call center recordings | Live captions, voice interfaces, real-time contact centers |
| Orchestration | Start job, track status, process results | Maintain stream connection and manage session lifecycle |
| Characteristics | Easy to retry/replay by file | Sensitive to network, audio format, and latency |

**Batch** fits when complete files exist and immediate transcripts are unnecessary. The application places media in S3, calls `StartTranscriptionJob`, tracks status (`QUEUED`, `IN_PROGRESS`, `COMPLETED`, or `FAILED`), and retrieves the transcript when the job finishes.

**Streaming** fits when results must appear while the user is speaking. The application opens a stream, sends audio chunks, and receives transcript events. Streaming uses HTTP/2 or WebSocket; the AWS CLI does not support streaming transcription, requiring an SDK or appropriate streaming protocol.

### 3.2. Audio Formats and Quality

Transcript quality depends heavily on input audio quality:

- Pick media encoding and sample rate matching the actual audio.
- Avoid declaring a sample rate different from the data actually sent.
- Minimize noise, clipping, echo, and background sound.
- Use suitable microphones and maintain steady volume levels.
- For multi-speaker audio, consider recording separate channels at the source.
- Never upsample to a higher frequency expecting to recover lost information.

For streaming, requests require `LanguageCode` or language identification settings, `MediaEncoding`, and `MediaSampleRateHertz`. PCM audio typically uses signed 16-bit little-endian PCM; sample rates must match the audio stream. Choose codecs and sample rates according to Transcribe guidelines and device capabilities.

### 3.3. Specifying Language vs. Automatic Detection

If the language is known ahead of time, specifying an explicit language code is usually easier to control.

- Batch can use `LanguageCode` to specify the language.
- When the language is unknown, use language identification with a list of candidate languages.
- Multi-language identification fits when media contains multiple spoken languages.
- For streaming, language identification requires `LanguageOptions`; `PreferredLanguage` can be added if an initial hint exists.
- To transcribe Vietnamese, use `vi-VN` when the audio is known to be Vietnamese.

Do not pass an overly broad candidate language list if application metadata can narrow it down. That reduces ambiguity on short clips or audio with loanwords.

### 3.4. Transcripts, Timestamps, and Confidence

Batch transcripts typically contain two layers of information:

- `transcripts`: combined full text content.
- `items`: individual words or punctuation marks, with start/end timestamps and confidence scores where available.

Applications can use timestamps to sync captions with video, search and jump to audio positions, highlight words dynamically, clip audio segments for review, and preserve links between transcripts and source recordings.

Confidence scores help prioritize review, not certify spoken words as accurate. For proper names, order numbers, product codes, or domain jargon, reconcile against business data sources.

### 3.5. Channel Identification and Speaker Diarization

These two features solve different problems:

- **Channel identification:** identifies speakers based on separate audio channels—for instance, a stereo call recording with agent and customer channels. When `EnableChannelIdentification` is enabled, the request must specify `NumberOfChannels`.
- **Speaker diarization:** segments transcripts by speaker within audio even when speakers are mixed in the same channel. Outputs carry speaker labels such as `spk_0`, `spk_1`.

Channel identification currently supports audio with up to two channels; Transcribe does not support media with more than two channels. If recording hardware isolates each speaker onto a separate channel, channel identification usually yields cleaner separation. If mono audio captures multiple people taking turns, speaker diarization fits better. Accuracy and availability depend on language, speaker count, overlapping speech, and recording quality.

### 3.6. Custom Vocabulary and Vocabulary Filtering

**Custom vocabulary** helps Transcribe better recognize specialized terms:

- Product names, brands, and proper nouns.
- Internal codes, project names, and technical terminology.
- Abbreviations or pronunciations outside standard dictionaries.

Custom vocabularies must reach `READY` status before being used in a job. The vocabulary's language must match the media's language code. If they mismatch, Transcribe may silently ignore the vocabulary without returning an error.

**Vocabulary filtering** uses a word list to `MASK`, `REMOVE`, or `TAG` terms per policy. It is a vocabulary filter, not a comprehensive PII detector. Never rely on it as a substitute for personal data protection policies.

### 3.7. Partial Results and Final Results in Streaming

Streaming can emit partial results before an utterance finishes. Partial results can change as the service receives more audio.

- Persist or publish transcripts only when results are marked final.
- Partial-results stabilization can be enabled to reduce flicker in displayed text, though it may affect accuracy.
- Retain `SessionId` and session metadata for log correlation.
- On disconnect, decide whether to resume the session or start a new session; never concatenate two streams into one transcript without preserving boundaries.
- Sending partial text to Translate can trigger repeated translations and unstable output. Wait for complete sentences/utterances before forwarding downstream.

### 3.8. PII and Redaction Limits

Amazon Transcribe supports PII identification/redaction for specific languages. However, in the current feature support matrix, `vi-VN` does not support redaction.

Therefore, for Vietnamese transcripts:

1. Restrict access to raw audio and raw transcripts.
2. Persist only fields needed by the business workflow.
3. Build a separate detection and replacement step tailored to Vietnamese and Vietnamese data formats.
4. Combine business rules, format checks, and human review by authorized staff.
5. Keep originals in a protected storage tier per retention policies; expose only processed versions to downstream systems.

For supported languages, Transcribe can output redacted transcripts and optionally unredacted transcripts. Verify PII types, languages, and batch/streaming modes before enabling. Never assume enabling redaction masks every identifying detail.

## 4. Amazon Translate: Translating Text and Documents

Amazon Translate is a neural machine translation service. It takes source text, source/target language codes, and returns translated text.

### 4.1. Real-Time vs. Asynchronous Batch

| Criterion | Real-time | Asynchronous batch |
|---|---|---|
| Request | Synchronous, immediate response | Asynchronous, job tracking |
| Input | Text snippets or supported documents | Document sets in S3 |
| Output | Response or returned document | Translated documents in S3 output prefix |
| Best fit | Chat, UI translation, individual transcript segments | Document repositories, websites, thousands of files |
| Limits | Text requests up to 10,000 bytes | Larger document, file count, and total volume quotas |

Real-time translation fits when applications need fast responses for a piece of text. Batch translation fits when processing large document sets in the background.

For real-time text translation, inputs are limited to 10,000 UTF-8 bytes under current default quotas. Do not equate 10,000 bytes with 10,000 characters: accented Vietnamese characters use more bytes than ASCII. Measure UTF-8 byte length before calling the API and split text along sentence/paragraph boundaries when necessary.

### 4.2. Language Codes and Automatic Language Detection

Examples: Vietnamese `vi`, English `en`, Japanese `ja`, and Thai `th`.

You can set the source language to `auto` for automatic language detection. Auto-detection can incur separate charges and is not always necessary. If source metadata already specifies the language, passing an explicit language code provides better pipeline control.

Amazon Translate supports many language pairs, though some features apply only to a subset of languages. Verify source/target pairs before enabling customization features.

### 4.3. Custom Terminology

Custom terminology lets you specify how critical terms should be translated:

| Source term | Target term | Reason |
|---|---|---|
| My Business Shop | My Business Shop | Preserve brand name |
| Redshift | Amazon Redshift | Preserve product name |
| fulfillment center | trung tâm hoàn tất đơn hàng | Standardize terminology |
| order ID | mã đơn hàng | Use consistent business phrasing |

Custom terminology is useful for brand/product names, technical terms, titles, legal phrases, finance, and customer support.

Terminology must be imported into the target Region, match the language pair, and be referenced in the request. A `TranslateText` request or batch translation job can reference at most one terminology resource per current quotas. Custom terminology is a contextual hint rather than a guarantee that the target term is always used; validate outputs with business test sentences.

### 4.4. Parallel Data and Active Custom Translation

Parallel data is a collection of example pairs containing source sentences and desired translations. Amazon Translate uses these examples to adapt style, tone, and word choice for batch translation.

- Custom terminology governs how specific terms are translated.
- Parallel data guides style and phrasing across full sentences/paragraphs.

Parallel data fits content with brand voice, legal phrasing, or domain jargon. Active Custom Translation uses parallel data inside batch translation jobs; do not assume identical support for every real-time request.

### 4.5. Additional Customization Options

Amazon Translate offers several options:

- **Do-not-translate tags:** marks HTML spans to preserve untranslated.
- **Brevity:** shortens translations for real-time text translation; unsupported in batch translation jobs.
- **Formality:** selects formal or informal tone for supported languages.
- **Profanity masking:** masks profane words/phrases using the service's recognition list.
- **Parallel data:** tunes style, tone, and word choice for batch jobs.

Profanity masking does not currently support Vietnamese. Moreover, profanity detection operates on words/phrases without full contextual understanding; it can mistakenly mask benign words inside phrases. If an application needs Vietnamese content moderation, build a dedicated policy and evaluate outputs before release.

### 4.6. Batch Translation and Quotas

Batch jobs read documents from S3, translate into one or more target languages, and write outputs to S3. Current default quotas include:

- Up to 10 target languages per job.
- Up to 1,000,000 documents per batch.
- Up to 5 GB total batch size.
- Up to 10 concurrent batch jobs under default quotas.
- Up to 1 MB of translatable text per document and 20 MB maximum file size.

These are default quotas, which may change or be raised via Service Quotas/AWS Support. Verify Regional quotas before scheduling large batches. For large workloads, use queues and concurrency controls instead of firing all requests at once.

### 4.7. Translating Transcripts While Preserving Metadata

When translating transcripts with timestamps and speaker labels, do not feed the entire JSON into Translate and overwrite the structure. Separate the text to translate and keep metadata outside.

~~~json
{
  "segmentId": "seg-00042",
  "speaker": "spk_1",
  "startMs": 12500,
  "endMs": 16800,
  "sourceLanguage": "vi",
  "sourceText": "Tôi sẽ gửi báo giá trong hôm nay.",
  "targetLanguage": "en",
  "translatedText": "I will send the quotation today."
}
~~~

Applications can translate each completed utterance or segment and attach results back to `segmentId`. Translation can change length and word order; source transcript timestamps do not automatically become exact timestamps for the translated audio.

## 5. Amazon Polly: Text-to-Speech

Amazon Polly converts text or SSML into synthesized audio. Applications can play audio immediately from the response or store outputs for later distribution.

### 5.1. Choosing Voices and Engines

| Engine | Characteristics | When to consider |
|---|---|---|
| Standard | Standard speech synthesis | Short prompts, alerts, cost-sensitive workloads |
| Neural | More natural voices for supported languages/voices | Content users listen to frequently |
| Long-form | Optimized for long-form content on supported voices | Audiobooks, lessons, long narration |
| Generative | Generative voices suited to conversational experiences on supported voices | Voice assistants, conversational responses |

Not every voice supports every engine. Check language, voice ID, engine, Region, SSML tags, and quotas. Use `DescribeVoices` to query the voice catalog rather than hardcoding voice lists long-term.

### 5.2. Polly's Vietnamese Limitation

According to Amazon Polly's current language/voice catalog, Vietnamese is not among supported languages. Therefore:

- Polly cannot synthesize Vietnamese speech directly.
- If a Vietnamese transcript is translated to English, Polly can read the English translation using an English voice/engine.
- If the product requires Vietnamese audio, pick another TTS service supporting Vietnamese or deploy a custom TTS model on appropriate infrastructure.
- Never pass `LanguageCode=vi` or invent a voice ID hoping to bypass language limits.

Example: a Vietnamese meeting is transcribed as `vi-VN`, translated to English via `vi` → `en`, and then Polly reads the English version using an `en-US` voice. This is a translate-and-speak-in-English workflow, not Polly speaking Vietnamese.

### 5.3. SynthesizeSpeech and Asynchronous Synthesis

**SynthesizeSpeech** fits short text segments needing an immediate audio response:

- Up to 6,000 total characters per request, of which at most 3,000 are billable characters.
- Audio output per request is capped at 10 minutes; remaining speech is truncated. Use asynchronous synthesis or suitable streaming for long content.
- Supports engines compatible with the chosen voice.
- Can return an audio stream for clients to save to file or forward to players.

**StartSpeechSynthesisTask** fits long text:

- Up to 200,000 total characters input, of which at most 100,000 are billable characters per current quotas.
- Runs asynchronously.
- Audio or speech marks are saved directly to S3.
- Can specify an SNS topic for task completion notifications.
- Track progress with `GetSpeechSynthesisTask` and `ListSpeechSynthesisTasks`.

Do not split long text arbitrarily by character count. Split along sentence/paragraph boundaries, preserve ordering metadata, and stitch audio in order.

### 5.4. Bidirectional Speech Synthesis Streaming

Polly provides `StartSpeechSynthesisStream` to send text incrementally and receive audio incrementally over HTTP/2:

- Uses only the Generative engine.
- Fits when text arrives progressively, such as voice assistants or real-time translations.
- Each `TextEvent` holds up to 6,000 total characters, with up to 3,000 billable characters; there is no total character limit for the entire stream session.
- Does not support speech marks.
- Requires an SDK supporting bidirectional event streams; the AWS CLI does not support this API.

Choose streaming only when the application genuinely produces text incrementally and wants to play audio before the entire text finishes.

### 5.5. SSML: Controlling Pronunciation and Delivery

Speech Synthesis Markup Language (SSML) controls how Polly pronounces speech:

- `break`: insert pauses.
- `prosody`: adjust rate, pitch, and volume.
- `say-as`: guide reading of numbers, dates, characters, or special formats.
- `phoneme`: guide pronunciation using supported phonetic alphabets.
- `lang`: specify the language for a span of words.
- `p`, `s`: organize paragraphs and sentences.

~~~xml
<speak>
  <p>Hello and welcome.</p>
  <p>
    Your order number is
    <say-as interpret-as="characters">A B 1 2 3</say-as>.
  </p>
  <break time="500ms"/>
  <prosody rate="medium" volume="medium">
    Your package will arrive tomorrow.
  </prosody>
</speak>
~~~

All SSML content must be wrapped in `<speak>`. Escape reserved characters like `&`, `<`, and `>` in text. Supported tag lists differ across Standard, Neural, Long-form, and Generative; verify compatibility before deploying.

### 5.6. Pronunciation Lexicons and Speech Marks

Lexicons customize pronunciation of words or phrases, useful for proper names, brands, and specialized terms. Lexicons are stored per Region, lexicon language must match voice language, and a single request can apply up to 5 lexicons per current quotas.

Speech marks are metadata describing the timing of words, sentences, or visemes in audio. They can drive word-by-word highlighting, subtitle syncing, lip-syncing animated characters, and video timeline synchronization. Speech marks are returned in a separate request, not alongside the audio stream. The Generative engine does not currently support speech marks; `StartSpeechSynthesisStream` does not support them either.

## 6. Integrating Services in an AWS Architecture

### 6.1. Batch Audio Processing Pipeline

~~~mermaid
flowchart TB
    U[Application uploads audio] --> S3[S3 raw audio]
    S3 --> EB[EventBridge]
    EB --> SF[Step Functions]
    SF --> T[Amazon Transcribe]
    T --> OUT[S3 transcript JSON]
    OUT --> N[Lambda normalize]
    N --> TR[Amazon Translate]
    TR --> TXT[S3 translated text]
    TXT --> P[Amazon Polly]
    P --> AUDIO[S3 synthesized audio]
    AUDIO --> CDN[CloudFront / API]
    N --> DB[DynamoDB metadata]
    TR --> DB
    P --> DB
~~~

Components:

- **Amazon S3:** stores raw audio, transcripts, translations, and audio outputs in separate prefixes.
- **Amazon EventBridge:** receives job state change events or orchestrates event triggers.
- **AWS Step Functions:** orchestrates steps, retries, timeouts, error branches, and pipeline state.
- **AWS Lambda:** normalizes transcripts, chunks text, checks metadata, and invokes appropriate APIs.
- **Amazon SQS:** buffers tasks, throttles rates, and decouples producers/consumers.
- **Amazon SNS:** notifies applications/operators of completion or failure.
- **Amazon DynamoDB:** tracks job metadata, status, versions, and idempotency keys.
- **Amazon CloudFront:** distributes audio outputs under access policies.

You do not always need all services. For small applications, Lambda + S3 + EventBridge may suffice. For high volume or multi-step workflows needing resilience, Step Functions and SQS provide cleaner retry/concurrency management.

### 6.2. Transcribe Completion Events

Amazon Transcribe emits job state events via EventBridge. You can create rules invoking Lambda or sending messages to SQS when jobs become `COMPLETED` or `FAILED`.

~~~json
{
  "source": ["aws.transcribe"],
  "detail-type": ["Transcribe Job State Change"],
  "detail": {
    "TranscriptionJobStatus": ["COMPLETED", "FAILED"]
  }
}
~~~

Upon receiving an event, extract `TranscriptionJobName` and status, verify the event matches a tracked job/version, process outputs if `COMPLETED`, or log failure reasons if `FAILED`. EventBridge delivers Transcribe events best-effort, so never treat events as the sole source of state: persist job metadata and add a reconciliation step calling `GetTranscriptionJob` if events arrive late or are missed. Events can be redelivered; never re-trigger Translate/Polly repeatedly just because the same event arrived twice. S3 event notifications can also deliver duplicates out of order; use `versionId`, object keys, and a state store to deduplicate.

### 6.3. Idempotency and Retries

Asynchronous APIs require dedicated orchestration controls. Track state by `jobId`, `bucket`, `objectKey`, `versionId`, or `requestId`.

~~~mermaid
stateDiagram-v2
    [*] --> RECEIVED
    RECEIVED --> TRANSCRIBING
    TRANSCRIBING --> TRANSCRIBED
    TRANSCRIBING --> FAILED
    TRANSCRIBED --> TRANSLATING
    TRANSLATING --> TRANSLATED
    TRANSLATING --> FAILED
    TRANSLATED --> SYNTHESIZING
    SYNTHESIZING --> COMPLETED
    SYNTHESIZING --> FAILED
    FAILED --> RETRY_PENDING
    RETRY_PENDING --> TRANSCRIBING
    RETRY_PENDING --> TRANSLATING
    RETRY_PENDING --> SYNTHESIZING
    COMPLETED --> [*]
~~~

Rules:

- Generate unique job names and persist them before calling services.
- Never retry invalid input, unsupported language, or permission-denied errors without fixing the root cause.
- Use exponential backoff and jitter for throttling/transient errors.
- Configure max attempts, timeouts, and DLQs.
- Save checkpoints after each stage so a Polly failure does not force re-transcribing.
- Version transcripts and translations; when sources change, mark older outputs stale.

### 6.4. Real-Time Speech Translation

~~~mermaid
sequenceDiagram
    participant C as Client
    participant T as Transcribe Streaming
    participant X as Translate
    participant P as Polly
    C->>T: Audio chunks
    T-->>C: Partial transcript
    T-->>X: Final utterance
    X-->>P: Translated text
    P-->>C: Audio response
~~~

Design notes: forward only finalized utterances to Translate; preserve speaker/channel metadata and segment order; use Translate real-time for small text chunks. When text streams in, Polly `StartSpeechSynthesisStream` can accept incremental text, though it supports only the Generative engine and compatible voices. If the target voice does not support Generative, use `SynthesizeSpeech` or async tasks with suitable chunking. Bound queues and buffers to avoid accumulating unbounded latency.

If the target language is Vietnamese, Polly has no corresponding voice in its current catalog. Switch to a TTS provider supporting Vietnamese or a self-hosted TTS model.

### 6.5. Combining Other Language Services

Depending on inputs and product goals, you can add:

- **Amazon Textract:** extracts text, forms, and tables from images/PDFs before translating documents. Preserve page numbers, bounding boxes, and confidence so UIs can align translations with original documents.
- **Amazon Comprehend:** analyzes sentiment, entities, key phrases, or PII across supported languages/APIs. Language matrices differ per feature; do not assume Comprehend PII detection supports Vietnamese just because Translate supports `vi`.
- **Amazon Lex:** manages intents, slots, and dialogs for chatbots/voice bots. Transcribe can supply input text; Polly can speak responses when the target language has a matching voice.
- **Amazon Bedrock:** summarizes, classifies, or drafts content from transcripts/translations. Guard against prompt injection inside transcripts, enforce data permissions, grounding, Guardrails, and human review for risky content.
- **Amazon Connect:** integrates contact center flows, recordings, and analytics/agent assistance features. Connect features have their own language matrices; do not assume Transcribe Call Analytics supports Vietnamese.

Additional services add cost and data copies. Forward only required fields, carry correlation IDs across stages, and verify Region/feature support for every API.

## 7. Integration Examples with AWS SDK for Java 2.x

### 7.1. Dependencies

Use the AWS SDK for Java 2.x and manage versions centrally via the AWS SDK BOM in the parent `pom.xml`. Add the required modules:

~~~xml
<dependencies>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>transcribe</artifactId>
    </dependency>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>transcribestreaming</artifactId>
    </dependency>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>translate</artifactId>
    </dependency>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>polly</artifactId>
    </dependency>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>s3</artifactId>
    </dependency>
</dependencies>
~~~

Do not embed access keys directly in source code. Use the default credential provider chain, workload IAM roles, or dedicated profiles for development environments.

### 7.2. Starting Batch Transcription for Vietnamese Audio

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.transcribe.TranscribeClient;
import software.amazon.awssdk.services.transcribe.model.LanguageCode;
import software.amazon.awssdk.services.transcribe.model.Media;
import software.amazon.awssdk.services.transcribe.model.StartTranscriptionJobRequest;
import software.amazon.awssdk.services.transcribe.model.StartTranscriptionJobResponse;

public class StartVietnameseTranscription {
    public static void main(String[] args) {
        String jobName = "meeting-2026-11-20-001";

        try (TranscribeClient transcribe = TranscribeClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build()) {

            StartTranscriptionJobRequest request =
                    StartTranscriptionJobRequest.builder()
                            .transcriptionJobName(jobName)
                            .languageCode(LanguageCode.VI_VN)
                            .media(Media.builder()
                                    .mediaFileUri(
                                        "s3://example-audio/raw/meeting.wav")
                                    .build())
                            .outputBucketName("example-transcripts")
                            .outputKey("transcripts/meeting-2026-11-20-001/")
                            .build();

            StartTranscriptionJobResponse response =
                    transcribe.startTranscriptionJob(request);

            System.out.println(
                    response.transcriptionJob().transcriptionJobStatus());
        }
    }
}
~~~

This example only starts the job. The audio bucket must exist and Transcribe/caller permissions must be properly configured. Output buckets, KMS keys, and roles must align with security policies. After starting, monitor status via `GetTranscriptionJob` or EventBridge; do not assume the transcript is ready immediately when the API returns.

### 7.2.1. Configuring Streaming Transcription

With the Java SDK, use the `transcribestreaming` module, `TranscribeStreamingAsyncClient`, and `StartStreamTranscriptionRequest`. The publisher sending audio chunks and response handler receiving transcript events must implement the SDK's event stream protocol:

~~~java
import java.util.concurrent.CompletableFuture;

import org.reactivestreams.Publisher;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.transcribestreaming.TranscribeStreamingAsyncClient;
import software.amazon.awssdk.services.transcribestreaming.model.AudioStream;
import software.amazon.awssdk.services.transcribestreaming.model.LanguageCode;
import software.amazon.awssdk.services.transcribestreaming.model.MediaEncoding;
import software.amazon.awssdk.services.transcribestreaming.model.PartialResultsStability;
import software.amazon.awssdk.services.transcribestreaming.model.StartStreamTranscriptionRequest;
import software.amazon.awssdk.services.transcribestreaming.model.StartStreamTranscriptionResponseHandler;

TranscribeStreamingAsyncClient client = TranscribeStreamingAsyncClient.builder()
        .region(Region.AP_SOUTHEAST_1)
        .build();

StartStreamTranscriptionRequest request =
        StartStreamTranscriptionRequest.builder()
                .languageCode(LanguageCode.VI_VN)
                .mediaEncoding(MediaEncoding.PCM)
                .mediaSampleRateHertz(16_000)
                .enablePartialResultsStabilization(true)
                .partialResultsStability(PartialResultsStability.MEDIUM)
                .build();

// audioPublisher emits PCM chunks; responseHandler processes TranscriptEvent.
CompletableFuture<Void> stream = client.startStreamTranscription(
        request, audioPublisher, responseHandler);
~~~

This is an integration skeleton; `audioPublisher` must implement `Publisher<AudioStream>` and `responseHandler` must be a `StartStreamTranscriptionResponseHandler`. Close clients/streams cleanly, handle backpressure, network errors, partial/final results, and real sample rates. Do not enable partial stabilization without measuring the latency vs. accuracy trade-off.

### 7.3. Translating Vietnamese Text to English

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.translate.TranslateClient;
import software.amazon.awssdk.services.translate.model.TranslateTextRequest;
import software.amazon.awssdk.services.translate.model.TranslateTextResponse;

public class TranslateVietnameseText {
    public static void main(String[] args) {
        String sourceText =
                "Tôi sẽ gửi báo giá và lịch giao hàng trong hôm nay.";

        try (TranslateClient translate = TranslateClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build()) {

            TranslateTextRequest request =
                    TranslateTextRequest.builder()
                            .text(sourceText)
                            .sourceLanguageCode("vi")
                            .targetLanguageCode("en")
                            .build();

            TranslateTextResponse response =
                    translate.translateText(request);

            System.out.println(response.translatedText());
        }
    }
}
~~~

This example uses real-time translation. For long transcripts, split into context-preserving segments and retain `segmentId` to link translations back to timestamps/speakers. If using terminology, pass `TerminologyNames` per the API model and verify the language pair.

### 7.4. Synthesizing English Audio with Polly

Because Polly does not currently support a Vietnamese voice, this example speaks the English translation produced by Translate.

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.polly.PollyClient;
import software.amazon.awssdk.services.polly.model.Engine;
import software.amazon.awssdk.services.polly.model.OutputFormat;
import software.amazon.awssdk.services.polly.model.SynthesizeSpeechRequest;
import software.amazon.awssdk.services.polly.model.SynthesizeSpeechResponse;
import software.amazon.awssdk.services.polly.model.TextType;
import software.amazon.awssdk.services.polly.model.VoiceId;

public class SpeakTranslatedText {
    public static void main(String[] args) throws Exception {
        String translatedText =
                "I will send the quotation and delivery schedule today.";

        try (PollyClient polly = PollyClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build()) {

            SynthesizeSpeechRequest request =
                    SynthesizeSpeechRequest.builder()
                            .engine(Engine.NEURAL)
                            .voiceId(VoiceId.JOANNA)
                            .outputFormat(OutputFormat.MP3)
                            .textType(TextType.TEXT)
                            .text(translatedText)
                            .build();

            try (ResponseInputStream<SynthesizeSpeechResponse> audio =
                         polly.synthesizeSpeech(request)) {
                Files.copy(
                        audio,
                        Path.of("translated-audio.mp3"),
                        StandardCopyOption.REPLACE_EXISTING);
            }
        }
    }
}
~~~

Voice IDs and engines in the example must be verified with `DescribeVoices` in the target Region. `Joanna` is an English example; do not replace this voice ID with a made-up string expecting Vietnamese speech.

### 7.5. AWS CLI: Batch Transcribe, Translate, and Polly

~~~bash
aws transcribe start-transcription-job \
  --region ap-southeast-1 \
  --transcription-job-name meeting-20261120-001 \
  --language-code vi-VN \
  --media MediaFileUri=s3://example-audio/raw/meeting.wav \
  --output-bucket-name example-transcripts \
  --output-key transcripts/meeting-20261120-001/
~~~

~~~bash
aws transcribe get-transcription-job \
  --region ap-southeast-1 \
  --transcription-job-name meeting-20261120-001
~~~

~~~bash
aws translate translate-text \
  --region ap-southeast-1 \
  --text "Tôi sẽ gửi báo giá trong hôm nay." \
  --source-language-code vi \
  --target-language-code en
~~~

~~~bash
aws polly synthesize-speech \
  --region ap-southeast-1 \
  --engine neural \
  --voice-id Joanna \
  --output-format mp3 \
  --text "I will send the quotation today." \
  translated-audio.mp3
~~~

For document sets in S3, you can launch a batch translation job:

~~~bash
aws translate start-text-translation-job \
  --region ap-southeast-1 \
  --input-data-config S3Uri=s3://example-translation/input/,ContentType=text/plain \
  --output-data-config S3Uri=s3://example-translation/output/ \
  --data-access-role-arn arn:aws:iam::123456789012:role/TranslateBatchRole \
  --source-language-code vi \
  --target-language-codes en ja
~~~

The batch job role needs permissions to read the input prefix, write to the output prefix, and appropriate KMS permissions if S3 uses SSE-KMS. Monitor jobs via `describe-text-translation-job`; handle completion/failure states through orchestration.

Polly asynchronous task for long narration:

~~~bash
aws polly start-speech-synthesis-task \
  --region ap-southeast-1 \
  --engine neural \
  --voice-id Joanna \
  --output-format mp3 \
  --output-s3-bucket-name example-audio-output \
  --output-s3-key-prefix narration/ \
  --text-type ssml \
  --text file://narration.ssml
~~~

These commands are examples. Replace buckets, keys, Regions, and voices according to your environment. Verify S3, KMS, quota, and engine compatibility before running.

## 8. Security, Access Control, and Data Management

### 8.1. IAM Least Privilege

Separate permissions by stage and workload:

| Component | Typically required permissions |
|---|---|
| API/backend starting Transcribe | `transcribe:StartTranscriptionJob`, `transcribe:GetTranscriptionJob` |
| Lambda processing results | `s3:GetObject` on the transcript prefix, metadata write permissions |
| Translate worker | `translate:TranslateText` or corresponding batch job permissions |
| Polly worker | `polly:SynthesizeSpeech` or `polly:StartSpeechSynthesisTask` |
| Polly task output | S3 write permissions and `sns:Publish` if using SNS notifications |
| EventBridge | Permission to invoke targets via appropriate resource policies/roles |

Do not grant account-wide `s3:*`, `transcribe:*`, `translate:*`, or `polly:*` just for a lab. Restrict by action, resource, bucket/prefix, and Region where supported.

### 8.2. Encryption and S3

Audio and transcripts may contain personal information or internal data:

- Use HTTPS/TLS for API calls.
- Enable S3 Block Public Access and bucket policies blocking public access.
- Enable SSE-S3 or SSE-KMS; use customer managed KMS keys when key policy/audit control is needed.
- Restrict read permissions on raw audio and unredacted transcripts.
- Configure S3 versioning, lifecycles, and retention per policy.
- Never write transcripts, emails, phone numbers, or tokens into application logs unnecessarily.
- Use time-limited signed URLs if files must be shared with clients.
- Evaluate data residency, Region, and compliance requirements before sending audio outside the boundary.

Transcribe supports TLS in transit and accepts a KMS key configuration for job outputs. Without a specified KMS key, S3 outputs may default to SSE-S3. Verify actual encryption on input buckets, output buckets, and downstream copies.

### 8.3. Data Privacy of Amazon Translate

Current Translate documentation notes that data may be retained to improve model quality; you can contact AWS Support to request data deletion and opt future account data out of storage via AWS-supported mechanisms. Opting out may affect model quality improvements derived from your data.

For sensitive data:

- Determine data classification before calling Translate.
- Strip or tokenize unnecessary information.
- Never send secrets, passwords, access tokens, or raw payment details in requests.
- Review AWS data policies and organizational legal requirements.
- Apply human review for content carrying legal/financial consequences or directly affecting customers.

### 8.4. Consent and Audio Retention

When recording calls/meetings, provide notice and capture consent per legal/organizational policies; restrict purpose and retention duration; define who may listen to raw audio; maintain audit trails for downloads/deletions; and synchronize deletion of audio and transcripts upon retention expiration or valid user requests. Never assume that redacting PII from a transcript makes the original audio non-sensitive.

## 9. Ensuring Output Quality

### 9.1. Transcription Quality

Measure with metrics such as:

- Word Error Rate (WER): rate of word substitutions, insertions, and deletions against a reference transcript.
- Character Error Rate (CER): useful for languages with diacritics/character variants.
- Language identification accuracy.
- Rate of low-confidence segments.
- Recognition accuracy on proper nouns/product codes.
- Latency from audio end to final transcript availability.

For Vietnamese, evaluate tone diacritics, proper names, loanwords, phone numbers, and order codes. A transcript with high confidence can still misread a critical identifier.

### 9.2. Translation Quality

Do not check grammatical correctness alone. Verify meaning, product terminology, pronouns, speaker roles, politeness registers, numbers, currencies, dates/times, units, negations, and exceptions. Translated segments must preserve `segmentId` and speaker context.

Use custom terminology for core terms, parallel data when consistent style is needed, and human review for high-risk documents.

### 9.3. TTS Quality

Evaluate pronunciation of proper names/abbreviations, intelligibility, naturalness, speaking rate, pitch, pauses, volume, audio duration, sample rate, format, time-to-first-audio-byte latency, and alignment of speech marks with text.

Do not force one voice/engine for every context. A voice suited for short notifications differs from one suited for audiobooks or conversational bots.

## 10. Monitoring, Reliability, and Costs

### 10.1. Metrics to Track

| Stage | Metrics | Purpose |
|---|---|---|
| Upload | File count, size, invalid media | Catch malformed inputs |
| Transcribe | Job duration, failure rate, queue time, language | Measure recognition throughput |
| Translate | Request latency, throttling, batch completion, bytes/characters | Monitor throughput |
| Polly | Synthesis duration, task status, throttling, output size | Measure audio generation |
| Pipeline | End-to-end latency, retry count, DLQ depth | Measure reliability |
| Quality | WER/CER, translation review score, pronunciation score | Ensure quality |
| Cost | Cost/audio minute, cost/million chars, cost/output minute | Track unit economics |

Combine CloudWatch metrics/logs, EventBridge events, and DynamoDB metadata. Logs should record `jobId`, `segmentId`, service operation, duration, and error codes; avoid logging full transcripts or audio payloads unnecessarily.

### 10.2. Costs

The three services bill on different units:

| Service | Primary billing unit | Cost drivers |
|---|---|---|
| Transcribe | Audio seconds processed | Total duration, streaming/batch, add-on features |
| Translate | Characters processed | Target language count, retries, custom translation |
| Polly | Characters synthesized | Engine/voice, speech marks, synthesis runs |

Also factor in S3 storage/requests, data transfer, Lambda duration, Step Functions state transitions, SQS/SNS, EventBridge, KMS requests, and audio storage/delivery via CDN.

Measure unit economics such as cost per audio minute, cost per million translated characters, or cost per generated audio minute. Do not look only at AI service bills while overlooking orchestration and storage costs.

### 10.3. Cutting Costs Without Sacrificing Quality

- Use Transcribe batch for files that do not need real-time transcripts.
- Enable diarization, channel identification, or add-on features only when needed.
- Use Translate batch for large document volumes.
- Cache translation outputs by content hash to avoid re-translating identical content.
- Cache Polly outputs keyed by text + voice + engine + SSML version.
- Use Polly asynchronous synthesis for long content rather than splitting into excessive tiny requests.
- Do not re-submit identical segments on retries; use idempotency keys.
- Set S3 lifecycle rules for raw audio, transcripts, and audio outputs per retention policies.
- Monitor throttling and tune concurrency rather than retrying infinitely.

## 11. Architecture Scenario: Customer Support Contact Center

An enterprise has a Vietnamese contact center and an international support team that need to archive calls, generate Vietnamese transcripts, translate transcripts to English, produce English audio for staff, and search calls by order ID/content.

1. The contact center saves recordings to S3 raw audio.
2. EventBridge detects new objects and launches Step Functions.
3. Transcribe batch uses `vi-VN` to generate transcripts.
4. Lambda reads transcripts, preserves speaker/timestamps, and normalizes segments.
5. A dedicated step handles Vietnamese PII checks because Transcribe redaction does not support `vi-VN`.
6. Translate converts `vi` → `en` with custom terminology for product names.
7. Polly speaks the English translation using a supported voice/engine.
8. S3 stores raw transcripts, processed transcripts, translations, and audio outputs in separate prefixes.
9. DynamoDB tracks status, language, job IDs, versions, and URIs.
10. CloudFront or an authenticated API serves content to authorized users.
11. CloudWatch monitors errors, latency, retries, quality samples, and costs.

If the support team needs Vietnamese audio playback, Polly cannot serve it directly. Integrate another TTS provider supporting Vietnamese or a self-hosted TTS model while keeping the same output storage and metadata contract so the rest of the pipeline remains intact.

## 12. Lab: Processing a Vietnamese Audio File

This lab demonstrates a batch workflow, translating to English, and generating English audio. Use a sandbox account, dedicated buckets, and audio containing no sensitive information.

### Step 1: Prepare S3

Create prefixes `raw/`, `transcripts/`, `translations/`, and `audio-en/`. Enable Block Public Access, encryption, and policies granting access only to the lab role.

### Step 2: Upload Audio

~~~bash
aws s3 cp meeting.wav \
  s3://example-audio-lab/raw/meeting.wav
~~~

Ensure the audio file has acceptable quality and a format supported by Transcribe.

### Step 3: Create Transcription Job

~~~bash
aws transcribe start-transcription-job \
  --region ap-southeast-1 \
  --transcription-job-name lab-vietnamese-meeting \
  --language-code vi-VN \
  --media MediaFileUri=s3://example-audio-lab/raw/meeting.wav \
  --output-bucket-name example-audio-lab \
  --output-key transcripts/lab-vietnamese-meeting/
~~~

Check status:

~~~bash
aws transcribe get-transcription-job \
  --region ap-southeast-1 \
  --transcription-job-name lab-vietnamese-meeting
~~~

Wait for `COMPLETED`. If `FAILED`, inspect `FailureReason`, media URI, IAM, KMS, and Region.

### Step 4: Read the Transcript

Retrieve the transcript URI from `Transcript.TranscriptFileUri` in the job response. Download the JSON file or read it from S3 using granted permissions.

~~~bash
aws s3 ls \
  s3://example-audio-lab/transcripts/lab-vietnamese-meeting/ \
  --recursive
~~~

Read `results.transcripts[0].transcript` to obtain the full text. If timestamps, speakers, or confidence scores are needed, parse `results.items` and corresponding metadata.

### Step 5: Translate to English

~~~bash
aws translate translate-text \
  --region ap-southeast-1 \
  --text "Tôi sẽ gửi báo giá trong hôm nay." \
  --source-language-code vi \
  --target-language-code en
~~~

For long transcripts, split into context-preserving segments while keeping order and IDs. For batch translation, upload files to S3 and call `StartTextTranslationJob`.

### Step 6: Generate English Audio with Polly

~~~bash
aws polly synthesize-speech \
  --region ap-southeast-1 \
  --engine neural \
  --voice-id Joanna \
  --output-format mp3 \
  --text "I will send the quotation today." \
  translated-audio.mp3
~~~

~~~bash
aws s3 cp translated-audio.mp3 \
  s3://example-audio-lab/audio-en/translated-audio.mp3
~~~

### Step 7: Evaluate

Compare the transcript against the original audio; check proper nouns and numbers; verify the translation against source meaning; listen to the English audio for pronunciation; and record latency, errors, audio duration, and character counts processed.

The lab does not generate Vietnamese audio with Polly because Vietnamese is not in the supported voice catalog.

## 13. Common Troubleshooting

| Symptom | Possible cause | Investigation steps |
|---|---|---|
| Transcribe `AccessDenied` | Role, S3 bucket policy, or KMS | Check input/output buckets, roles, and key policies |
| Transcribe `BadRequestException` | Invalid language code, media encoding, sample rate, or channel config | Inspect request parameters and audio metadata |
| Transcribe misrecognizes domain terms | Poor audio, unsuitable vocabulary, or language mismatch | Clean audio, check vocabulary state/language |
| Transcript lacks speaker labels | Diarization disabled or unsupported language/feature | Check feature matrix and request settings |
| Vietnamese transcript still contains PII | `vi-VN` does not support Transcribe redaction | Add dedicated PII handling and review |
| Streaming partial results keep changing | Partial results are not final yet | Commit only final results |
| Translate `UnsupportedLanguagePairException` | Language pair or feature unsupported | Check supported language pairs |
| Translate throttling | Request rate too high or quota exceeded | Lower concurrency, back off, request quota increase |
| Translate request too large | Exceeded 10,000 real-time bytes or document quota | Split along sentence/paragraph boundaries and measure UTF-8 bytes |
| Wrong terminology in translation | Missing terminology or context | Add terminology/parallel data and human review |
| Polly rejects voice/engine | Voice does not support engine or Region | Run `DescribeVoices` and verify compatibility |
| Polly cannot speak Vietnamese | Vietnamese absent from voice catalog | Use another TTS or translate to a Polly-supported language |
| Polly output truncated | Exceeded sync character or audio duration limit | Use `StartSpeechSynthesisTask` or suitable streaming API |
| Polly mispronounces words | Unsuitable text/SSML/lexicon | Check SSML support and pronunciation lexicons |
| Duplicate job runs | Duplicate events or non-idempotent retries | Use job IDs, object versions, and state store |
| Pipeline backlog builds up | Downstream slower than upstream | Use SQS, cap concurrency, and monitor queue age |

## 14. Common Mistakes

**Assuming one language exists across all three services.** Each service maintains its own catalog and feature matrix. Verify language support before designing.

**Using Transcribe redaction for Vietnamese transcripts.** `vi-VN` does not currently support redaction. Implement a dedicated PII protection step.

**Enabling profanity masking for Vietnamese Translate.** This feature does not support `vi`. Use another moderation layer suited to requirements.

**Assuming Polly can speak Vietnamese.** Polly has no Vietnamese voices in its current catalog. Use a different TTS provider or translate into a supported voice language.

**Translating every partial result.** Partial text fluctuates, causing duplicate and inaccurate translations. Forward only final utterances or completed segments.

**Translating raw transcript JSON as a single blob.** This can corrupt timestamps, speaker IDs, and JSON structure. Translate only text fields while keeping metadata separate.

**Treating confidence scores as guaranteed accuracy.** Use confidence to prioritize review, not as a substitute for business validation.

**Using Polly `SynthesizeSpeech` for long audiobooks.** Use asynchronous synthesis or an appropriate streaming API.

**Retrying every error infinitely.** Permission, language, and invalid-input errors require fixing the root cause; infinite retries only inflate costs.

**Failing to version content.** When audio/transcripts change, older translations and audio fall out of sync. Track content hashes/versions and stale flags.

## 15. Self-Check Questions

1. Which three tasks do Amazon Transcribe, Translate, and Polly solve?
2. When should you use batch transcription vs. streaming?
3. Which services use `vi-VN` and `vi`?
4. Why must you check the feature matrix per language?
5. How does channel identification differ from speaker diarization?
6. What are the purposes of custom vocabulary and vocabulary filtering?
7. How can partial results change during streaming?
8. Why should you avoid translating partial transcripts?
9. Does Transcribe automatically redact PII for Vietnamese?
10. How does Amazon Translate real-time differ from batch translation?
11. How does custom terminology differ from parallel data?
12. Can Translate's brevity option be used in batch translation?
13. Does Translate's profanity masking support Vietnamese?
14. Why are 10,000 bytes not equivalent to 10,000 Vietnamese characters?
15. How do Polly Standard, Neural, Long-form, and Generative differ?
16. How does `SynthesizeSpeech` differ from `StartSpeechSynthesisTask`?
17. When should `StartSpeechSynthesisStream` be used?
18. How does SSML help control speech output?
19. Which UI experiences can speech marks enable?
20. Why can Polly not generate Vietnamese speech in the current catalog?
21. How does EventBridge help orchestrate Transcribe jobs?
22. Why do S3 events and job events require idempotency?
23. Where do IAM roles and KMS keys participate in securing the pipeline?
24. How are WER/CER used to evaluate transcription quality?
25. Which units must be measured to calculate end-to-end cost?

## 16. Production Checklist

- [ ] Language codes and feature support confirmed for every service.
- [ ] Batch vs. streaming chosen according to latency targets.
- [ ] Audio encoding/sample rates match actual inputs.
- [ ] Handling exists for partial vs. final results.
- [ ] Speaker/channel settings and custom vocabularies verified where needed.
- [ ] PII redaction language support confirmed; Vietnamese has a dedicated replacement step.
- [ ] Translate uses custom terminology and human review for key terms.
- [ ] Real-time/batch quotas and UTF-8 byte limits verified.
- [ ] Polly voice, engine, Region, and SSML tags tested.
- [ ] Polly is never assumed to support Vietnamese.
- [ ] Job state, retries, timeouts, and DLQs configured.
- [ ] EventBridge/S3 events use idempotency keys and deduplication.
- [ ] Audio, transcripts, translations, and outputs have versioning and retention.
- [ ] Least-privilege IAM, S3 Block Public Access, and KMS encryption configured.
- [ ] Logs exclude audio payloads and sensitive transcripts unnecessarily.
- [ ] Consent, retention, and data deletion workflows exist.
- [ ] Dashboards track latency, errors, queue depth, throttling, and costs.
- [ ] Evaluations cover WER/CER, translation review, and TTS pronunciation.
- [ ] Human review exists for high-risk content.
- [ ] Restore/replay tests executed confirming outputs are not duplicated.

## Conclusion

Amazon Transcribe, Amazon Translate, and Amazon Polly form a practical language processing toolkit when each stage is matched to data types, latency, languages, and supported features. Transcribe converts audio to transcripts, Translate converts text across languages, and Polly generates audio from text/SSML.

For Vietnamese, Transcribe supports batch and streaming and Translate supports text translation, yet Transcribe does not yet support PII redaction for `vi-VN`, Translate does not yet support profanity masking for `vi`, and Polly does not yet offer Vietnamese voices in its current catalog. These constraints must be designed directly into the architecture. Combining S3, EventBridge, Step Functions, Lambda, SQS, SNS, and DynamoDB yields a scalable, resilient, and observable pipeline. Data security, linguistic quality, idempotency, and cost must be engineered alongside core functionality.

## AWS Reference Documentation

- [Amazon Transcribe Developer Guide](https://docs.aws.amazon.com/transcribe/latest/dg/what-is.html)
- [Supported languages and language-specific features — Transcribe](https://docs.aws.amazon.com/transcribe/latest/dg/supported-languages.html)
- [Amazon Transcribe feature matrix](https://docs.aws.amazon.com/transcribe/latest/dg/feature-matrix.html)
- [Batch transcription jobs](https://docs.aws.amazon.com/transcribe/latest/dg/how-input.html)
- [Transcribing streaming audio](https://docs.aws.amazon.com/transcribe/latest/dg/streaming.html)
- [StartStreamTranscription API](https://docs.aws.amazon.com/transcribe/latest/APIReference/API_streaming_StartStreamTranscription.html)
- [Channel identification](https://docs.aws.amazon.com/transcribe/latest/dg/channel-id.html)
- [Speaker diarization](https://docs.aws.amazon.com/transcribe/latest/dg/diarization.html)
- [Using a custom vocabulary](https://docs.aws.amazon.com/transcribe/latest/dg/custom-vocabulary-using.html)
- [Redacting or identifying PII](https://docs.aws.amazon.com/transcribe/latest/dg/pii-redaction.html)
- [Data encryption — Transcribe](https://docs.aws.amazon.com/transcribe/latest/dg/data-encryption.html)
- [Using EventBridge with Transcribe](https://docs.aws.amazon.com/transcribe/latest/dg/monitoring-events.html)
- [Streaming Transcribe examples using SDK for Java 2.x](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/java_transcribe-streaming_code_examples.html)
- [Amazon Transcribe pricing](https://aws.amazon.com/transcribe/pricing/)
- [Amazon Translate Developer Guide](https://docs.aws.amazon.com/translate/latest/dg/what-is.html)
- [Supported languages and language codes — Translate](https://docs.aws.amazon.com/translate/latest/dg/what-is-languages.html)
- [Translation processing modes](https://docs.aws.amazon.com/translate/latest/dg/processing.html)
- [Customizing translations](https://docs.aws.amazon.com/translate/latest/dg/customizing-translations.html)
- [Masking profanity in Amazon Translate](https://docs.aws.amazon.com/translate/latest/dg/customizing-translations-profanity.html)
- [Custom terminology](https://docs.aws.amazon.com/translate/latest/dg/how-custom-terminology.html)
- [Parallel data and Active Custom Translation](https://docs.aws.amazon.com/translate/latest/dg/customizing-translations-parallel-data.html)
- [Running a batch translation job](https://docs.aws.amazon.com/translate/latest/dg/async-start.html)
- [Guidelines and quotas — Translate](https://docs.aws.amazon.com/translate/latest/dg/what-is-limits.html)
- [Amazon Translate pricing](https://aws.amazon.com/translate/pricing/)
- [Amazon Polly Developer Guide](https://docs.aws.amazon.com/polly/latest/dg/what-is.html)
- [Languages in Amazon Polly](https://docs.aws.amazon.com/polly/latest/dg/supported-languages.html)
- [Available voices](https://docs.aws.amazon.com/polly/latest/dg/available-voices.html)
- [Generative voices](https://docs.aws.amazon.com/polly/latest/dg/generative-voices.html)
- [Long-form voices](https://docs.aws.amazon.com/polly/latest/dg/long-form-voices.html)
- [Generating speech with SSML](https://docs.aws.amazon.com/polly/latest/dg/ssml.html)
- [Supported SSML tags](https://docs.aws.amazon.com/polly/latest/dg/supportedtags.html)
- [Speech marks](https://docs.aws.amazon.com/polly/latest/dg/speechmarks.html)
- [Long audio files and asynchronous synthesis](https://docs.aws.amazon.com/polly/latest/dg/asynchronous.html)
- [SynthesizeSpeech and StartSpeechSynthesisStream comparison](https://docs.aws.amazon.com/polly/latest/dg/bidirectional-streaming-choosing.html)
- [Polly quotas](https://docs.aws.amazon.com/polly/latest/dg/limits.html)
- [Amazon Polly pricing](https://aws.amazon.com/polly/pricing/)
- [AWS SDK for Java 2.x — Transcribe examples](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/java_transcribe_code_examples.html)
- [AWS SDK for Java 2.x — Translate examples](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/java_translate_code_examples.html)
- [AWS SDK for Java 2.x — Polly examples](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/java_polly_code_examples.html)
- [AWS Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html)
- [Amazon EventBridge](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-what-is.html)
- [Amazon S3 Event Notifications](https://docs.aws.amazon.com/AmazonS3/latest/userguide/EventNotifications.html)
- [Amazon Textract Developer Guide](https://docs.aws.amazon.com/textract/latest/dg/what-is.html)
- [Amazon Comprehend Developer Guide](https://docs.aws.amazon.com/comprehend/latest/dg/what-is.html)
- [Amazon Lex V2 Developer Guide](https://docs.aws.amazon.com/lexv2/latest/dg/what-is.html)
- [Amazon Bedrock User Guide](https://docs.aws.amazon.com/bedrock/latest/userguide/what-is-bedrock.html)
- [Amazon Connect Administrator Guide](https://docs.aws.amazon.com/connect/latest/adminguide/what-is-amazon-connect.html)
- [AWS Pricing Calculator](https://calculator.aws/)
