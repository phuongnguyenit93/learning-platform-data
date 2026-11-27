# Calling Bedrock from Java and Handling Streaming Responses

A Java application can call Amazon Bedrock to generate content, summarize documents, answer questions, or support business workflows. With a standard API request, the application sends a prompt and waits for the entire answer. With streaming, Bedrock returns results incrementally as the model generates them. Users can start reading earlier, and the application can forward each chunk to a web UI, mobile app, or downstream service.

The AWS SDK for Java 2.x provides the Amazon Bedrock Runtime client for invoking models. For conversational applications, **Converse** and **ConverseStream** are suitable choices because they provide a unified message structure across models that support conversations. For model-specific features or payloads, applications can use **InvokeModel** and **InvokeModelWithResponseStream**.

Streaming changes how an application processes responses: an answer can be split into multiple events, a content block can have multiple deltas, a stream can end with various stop reasons, and errors can occur after partial content has already been sent to the user. Therefore, the application must explicitly manage callbacks, errors, timeouts, conversation state, and incomplete content.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish the Amazon Bedrock control plane from Bedrock Runtime.
- Configure the AWS SDK for Java 2.x, Region, and credential provider.
- Choose between Converse, ConverseStream, InvokeModel, and InvokeModelWithResponseStream.
- Invoke models synchronously using the Java SDK.
- Use `BedrockRuntimeAsyncClient` to receive streaming responses.
- Handle `messageStart`, `contentBlockDelta`, `messageStop`, and `metadata` events.
- Manage multiple content blocks, tool-use events, and reasoning blocks.
- Organize conversation history at the application layer.
- Configure IAM permissions, inference profiles, timeouts, and retries.
- Combine Guardrails with streaming and protect sensitive data.
- Monitor token usage, latency, throttling, and errors in production.

## 1. Amazon Bedrock Runtime in a Java Architecture

Amazon Bedrock provides foundation models through a managed API. Java applications do not need to deploy GPU infrastructure or manage model servers themselves; the application sends requests to the Bedrock Runtime endpoint and receives inference results.

Distinguish between two client groups:

| Group | SDK client | Purpose |
|---|---|---|
| Bedrock control plane | BedrockClient | Discover foundation models, retrieve model metadata, manage inference profiles, and supported control-plane resources. |
| Bedrock Runtime | BedrockRuntimeClient | Invoke synchronous inference such as Converse or InvokeModel. |
| Bedrock Runtime async | BedrockRuntimeAsyncClient | Call asynchronous APIs and process streaming responses such as ConverseStream or InvokeModelWithResponseStream. |

The Converse and Invoke APIs use the Bedrock Runtime endpoint. An inference request requires an appropriate model ID or resource ID, a Region where the model is supported, and corresponding IAM permissions.

~~~mermaid
flowchart LR
    U["Web / Mobile user"] --> APP["Java application"]
    APP --> SDK["AWS SDK for Java 2.x"]
    SDK --> BR["Amazon Bedrock Runtime"]
    BR --> FM["Foundation model"]
    FM --> EV["Streaming events"]
    EV --> SDK
    SDK --> APP
    APP --> U
    APP --> HIST["Conversation history store"]
    APP --> OBS["Logs / metrics / traces"]
~~~

In this architecture, the Java application is responsible for authenticating users, preparing prompts, managing conversation history, invoking the model, processing outputs, and enforcing business rules. Bedrock provides model inference; the application remains responsible for controlling how content is used.

## 2. Preparing the AWS SDK for Java 2.x

### 2.1. Adding Dependencies

With Maven, use the AWS SDK BOM so all modules share the same version:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>software.amazon.awssdk</groupId>
            <artifactId>bom</artifactId>
            <version>2.x.y</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>bedrockruntime</artifactId>
    </dependency>
</dependencies>
~~~

Replace `2.x.y` with a tested version of the AWS SDK for Java 2.x. The BOM ensures AWS SDK modules use the same version, avoiding errors from mixing incompatible versions.

With Gradle:

~~~kotlin
dependencies {
    implementation(platform("software.amazon.awssdk:bom:2.x.y"))
    implementation("software.amazon.awssdk:bedrockruntime")
}
~~~

If the application needs a specific async HTTP client configuration, you can additionally declare Netty or the AWS CRT client per SDK documentation. Choose an HTTP implementation suited to your runtime and inspect the dependency tree before packaging.

### 2.2. Do Not Embed Access Keys in Source Code

The AWS SDK for Java 2.x supports `DefaultCredentialsProvider`. This provider looks up credentials following the SDK's standard configuration chain, such as environment variables, shared profiles, web identity, container credentials, or instance roles.

In production, prefer an IAM role attached to the compute environment:

- EC2 instance profile.
- ECS task role.
- EKS workload identity.
- Lambda execution role.
- IAM role assumed via federation when running outside AWS.

Do not hardcode access keys or secret keys directly in Java source code, configuration files committed to Git, or Docker images.

### 2.3. Choosing Region and Model ID

The model ID must exist and support inference in the selected Region. The examples below use Amazon Nova Lite as an illustrative model; verify model availability, API compatibility, and streaming support at deployment time.

~~~java
import software.amazon.awssdk.regions.Region;

Region region = Region.US_EAST_1;
String modelId = "amazon.nova-lite-v1:0";
~~~

In real applications, retrieve Region and model ID from environment/configuration:

~~~java
Region region = Region.of(
    System.getenv().getOrDefault("AWS_REGION", "us-east-1")
);

String modelId = System.getenv().getOrDefault(
    "BEDROCK_MODEL_ID",
    "amazon.nova-lite-v1:0"
);
~~~

The model ID can also be an inference profile ID/ARN, a provisioned throughput ARN, or a prompt resource supported by the API. Do not assume every model is invoked with a foundation model ID.

## 3. Verifying the Model and Access Permissions Before Calling

Before deployment, verify:

1. Is the model offered in the source Region?
2. Does the model support the Converse or Invoke API chosen by the application?
3. Does the model support response streaming?
4. Has the account satisfied model agreement or first-time-use requirements?
5. Does the IAM role have permission to invoke inference on that model/profile?
6. Are service quotas and throughput sufficient for expected load?

On the control plane, you can use `GetFoundationModel` to read model details. The `responseStreamingSupported` field indicates whether the model supports response streaming. The model catalog also shows input modalities, output modalities, and Region availability.

For most commercial models, model access can be enabled on first invocation according to published AWS terms. Some third-party models require EULA acceptance; certain Anthropic versions require completing a first-time-use case before calling. Check model access documentation rather than assuming every model follows the same process.

## 4. Choosing the API: Converse or Invoke?

Amazon Bedrock has two common inference API families:

| API | Streaming | Request structure | When to use |
|---|---|---|---|
| Converse | No | Unified messages, system prompt, inferenceConfig, and toolConfig | Chat, multi-turn conversations, and model portability. |
| ConverseStream | Yes | Same as Converse, returns response as events | Chat needing incremental output display. |
| InvokeModel | No | JSON body matching the model's native schema | Need model-specific parameters or payloads. |
| InvokeModelWithResponseStream | Yes | Model-specific JSON body, response is a stream of chunks | Need streaming with a model's native protocol. |

The Converse API lets applications use a unified message structure across models supporting messages. If a model has specific inference parameters, the request can pass `additionalModelRequestFields` according to the model's schema.

InvokeModel is flexible with model-specific request/response formats, but the application must construct the JSON body and decode the response for each provider/model. When switching models, the payload mapping logic may need to change.

For new conversational Java applications, start with Converse/ConverseStream if the model supports it. Choose the Invoke family when you need specific capabilities or request formats that Converse does not expose.

## 5. Calling Converse Synchronously from Java

Converse fits when an application needs a complete response before returning to the caller. For example: batch jobs, backend APIs that do not need token streaming, or an internal processing step.

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.services.bedrockruntime.BedrockRuntimeClient;
import software.amazon.awssdk.services.bedrockruntime.model.*;

public class BedrockConverseExample {

    public static void main(String[] args) {
        String modelId = "amazon.nova-lite-v1:0";

        Message userMessage = Message.builder()
            .role(ConversationRole.USER)
            .content(ContentBlock.fromText(
                "Explain what an AWS Region is in two sentences."
            ))
            .build();

        try (BedrockRuntimeClient client = BedrockRuntimeClient.builder()
                .credentialsProvider(DefaultCredentialsProvider.create())
                .region(Region.US_EAST_1)
                .build()) {

            ConverseResponse response = client.converse(request -> request
                .modelId(modelId)
                .messages(userMessage)
                .inferenceConfig(config -> config
                    .maxTokens(256)
                    .temperature(0.2F)
                )
            );

            for (ContentBlock block :
                    response.output().message().content()) {
                if (block.text() != null) {
                    System.out.print(block.text());
                }
            }

            System.out.println();
            System.out.println("Stop reason: " + response.stopReason());
            System.out.println("Input tokens: " +
                response.usage().inputTokens());
            System.out.println("Output tokens: " +
                response.usage().outputTokens());
        }
    }
}
~~~

The example uses a single text message to focus on API structure. In multi-turn applications, `messages` can contain previous user and assistant messages. Converse does not automatically store session history for the application; the caller must send the required context in every request.

## 6. Why Streaming?

With a non-streaming response, users must wait until the model finishes generating the entire content before seeing results. With streaming, the application receives chunks of output as they are generated.

For example, when a model answers a question:

- Non-streaming: the application waits for the full answer, then returns the HTTP response.
- Streaming: the application receives each delta and pushes it to the browser via Server-Sent Events or WebSockets.

Streaming reduces time-to-first-token and creates a more responsive feel. However, streaming does not make the model reason faster in all cases, does not reduce total generated tokens, and does not guarantee a complete answer.

Initial output chunks may be an incomplete sentence, partial JSON, or a tool call. The application must distinguish temporary content from the final result.

## 7. ConverseStream and the Event Lifecycle

ConverseStream returns a sequence of events. General sequence:

~~~mermaid
sequenceDiagram
    participant App as Java application
    participant Bedrock as Bedrock Runtime
    App->>Bedrock: ConverseStream request
    Bedrock-->>App: messageStart
    loop Each content block
        opt Tool use
            Bedrock-->>App: contentBlockStart
        end
        loop Partial content
            Bedrock-->>App: contentBlockDelta
        end
        Bedrock-->>App: contentBlockStop
    end
    Bedrock-->>App: messageStop with stopReason
    Bedrock-->>App: metadata with usage and metrics
~~~

Key events:

| Event | Meaning |
|---|---|
| messageStart | Starts an assistant message, usually carrying the role. |
| contentBlockStart | Starts a content block; commonly appears when the model emits a tool-use block. |
| contentBlockDelta | A piece of generated content. Can be text, reasoning content, or tool-use input. |
| contentBlockStop | Ends a content block. |
| messageStop | Ends the message; contains `stopReason`. |
| metadata | Inference usage and metrics information. |

Content block events are grouped by `contentBlockIndex`. A message can contain multiple content blocks; do not assume the entire output is always a single text string.

### 7.1. contentBlockDelta Is Not Always Text

A delta can carry one of the following:

- Text: newly generated text segment from the model.
- Reasoning content: structured reasoning block that may include a signature.
- Tool use: partial JSON input for a tool call.

With reasoning-enabled models, if the application continues the conversation using returned reasoning content, keep the signature and related messages intact per API requirements. Do not alter or strip blocks containing signatures when resending conversation context.

Do not display reasoning blocks to end users as if they were the final answer. Process only the content types the application is designed to handle.

### 7.2. messageStop and stopReason

`messageStop` marks that the model has finished the current message. `stopReason` indicates why the model stopped.

Examples:

- `end_turn`: the model completed its turn.
- `max_tokens`: the model hit the output token limit.
- `tool_use`: the model wants the application to execute a tool.
- `stop_sequence`: the model encountered a configured stop sequence.
- `guardrail_intervened`: a guardrail intervened in the response.
- `content_filtered`, `malformed_model_output`, `malformed_tool_use`, or `model_context_window_exceeded`: the model could not respond normally because content was filtered, output was invalid, or the context limit was exceeded.

Do not treat `max_tokens` as a complete answer if the content is cut off. The UI can notify the user that output was truncated, or the backend can ask the model to continue if the workflow permits.

## 8. Calling ConverseStream with BedrockRuntimeAsyncClient

Streaming uses the async client. The AWS SDK for Java 2.x returns a `CompletableFuture` and uses a response handler to process events as they arrive.

Complete example for text streaming:

~~~java
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.bedrockruntime.BedrockRuntimeAsyncClient;
import software.amazon.awssdk.services.bedrockruntime.model.*;

import java.util.concurrent.ExecutionException;

public class BedrockConverseStreamExample {

    public static void main(String[] args) {
        String modelId = "amazon.nova-lite-v1:0";
        String prompt = "Explain Amazon S3 in three short paragraphs.";

        Message userMessage = Message.builder()
            .role(ConversationRole.USER)
            .content(ContentBlock.fromText(prompt))
            .build();

        ConverseStreamRequest request = ConverseStreamRequest.builder()
            .modelId(modelId)
            .messages(userMessage)
            .inferenceConfig(config -> config
                .maxTokens(512)
                .temperature(0.2F)
            )
            .build();

        var streamHandler = ConverseStreamResponseHandler.builder()
            .subscriber(ConverseStreamResponseHandler.Visitor.builder()
                .onContentBlockDelta(event -> {
                    String text = event.delta().text();

                    if (text != null && !text.isEmpty()) {
                        System.out.print(text);
                        System.out.flush();
                    }
                })
                .build())
            .onError(error -> System.err.println(
                "Bedrock stream failed: " + error.getMessage()
            ))
            .build();

        try (BedrockRuntimeAsyncClient client =
                BedrockRuntimeAsyncClient.builder()
                    .credentialsProvider(
                        DefaultCredentialsProvider.create()
                    )
                    .region(Region.US_EAST_1)
                    .build()) {

            client.converseStream(request, streamHandler).get();
            System.out.println();

        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                "The Bedrock streaming call was interrupted.", e
            );
        } catch (ExecutionException e) {
            throw new IllegalStateException(
                "The Bedrock streaming call failed.", e.getCause()
            );
        }
    }
}
~~~

Key points:

- `BedrockRuntimeAsyncClient` is used for async APIs.
- `ConverseStreamRequest` contains the model ID, messages, and inference config.
- The response handler receives each event.
- `onContentBlockDelta` processes only text in this example.
- `CompletableFuture` completes when the stream finishes or fails.
- The client is closed to release HTTP connections and thread resources.

This is an illustrative console program. In an application server, do not block event-loop threads with `get()`. Forward results through a reactive pipeline, an appropriate executor, or your framework's streaming mechanism.

## 9. Pushing Deltas to the Browser or Downstream Services

In a web application, the Java backend typically acts as an intermediary:

1. The browser sends the prompt to the Java API.
2. The Java backend authenticates the user and checks quotas.
3. The backend calls `ConverseStream`.
4. Each text delta is converted into an SSE event or WebSocket frame.
5. When `messageStop` and `metadata` arrive, the backend sends a completion event with appropriate usage info.
6. The backend persists conversation state and audit metadata per policy.

Simple SSE payload example:

~~~text
event: token
data: Hello

event: token
data: there

event: token
data: friend

event: done
data: {"stopReason":"end_turn"}
~~~

An application-level token event usually corresponds to a text chunk or partial chunk, not necessarily a single model token. SDK delta boundaries, model token boundaries, and SSE frame boundaries are three distinct concepts.

When forwarding chunks downstream:

- Do not block callbacks with database queries or remote API calls.
- Use a bounded queue to prevent unbounded memory growth.
- Implement backpressure or rate limiting.
- Attach a request/session ID to correlate events.
- Handle browser disconnects and cancel the upstream request when appropriate.
- Send a terminal event when the stream completes or errors.

## 10. Managing Conversation History

The Converse API takes a list of messages. Bedrock does not manage session history on the application's behalf.

A multi-turn conversation might look like:

~~~text
[
  { role: user,      content: "What is a VPC?" },
  { role: assistant, content: "A VPC is..." },
  { role: user,      content: "How do subnets fit into it?" }
]
~~~

On the next turn, the application sends the necessary messages so the model understands the context. With streaming, the assistant response must be assembled into a complete message before being added to history for the next turn.

Best practices:

- Store history per user/session in an access-controlled datastore.
- Send only the context needed for the current question.
- Limit the number of turns or token budget.
- Summarize older conversation turns when history grows long.
- Separate system prompts from user content.
- Never allow users to alter the system prompt via arbitrary string concatenation.
- Do not save a partial assistant response as a complete message if the stream fails mid-way.

In multi-instance systems, do not keep conversation history solely in static variables or a single JVM's memory. Use an appropriate store such as DynamoDB, a relational database, or a cache with persistence as required.

## 11. When to Use InvokeModelWithResponseStream?

`InvokeModelWithResponseStream` takes a request body matching the model's specific schema. The application must know the field names for prompts, inference parameters, and the response structure required by the model.

General workflow:

1. Choose a model with `responseStreamingSupported`.
2. Build a JSON request matching the model/provider schema.
3. Call `InvokeModelWithResponseStream`.
4. Receive chunks in the response event stream.
5. Assemble or decode chunks according to the model's protocol.
6. Extract text, finish reason, and usage if the model returns those fields.

For example, models may return JSON fragments with varying structures. Do not concatenate all bytes and assume each chunk is always a complete JSON document. You may need to buffer bytes, handle UTF-8 boundaries, and parse events per protocol.

Choose `InvokeModelWithResponseStream` when:

- The model does not yet support Converse but supports Invoke streaming.
- The application needs model-specific request parameters.
- The application already has a dedicated adapter for a provider/model.
- A specific capability is not yet exposed by Converse.

For models supporting messages, `ConverseStream` usually reduces coupling to model-specific request formats.

## 12. Tool Use in ConverseStream

A model can request that the application call an external function or API. Converse supports tool use via `toolConfig`.

Example support application looking up order status with a tool:

~~~json
{
  "toolSpec": {
    "name": "get_order_status",
    "description": "Look up an order status by order ID",
    "inputSchema": {
      "json": {
        "type": "object",
        "properties": {
          "orderId": { "type": "string" }
        },
        "required": ["orderId"]
      }
    }
  }
}
~~~

During streaming, tool input JSON can arrive across multiple deltas. Never execute a tool upon receiving only partial JSON.

Safe workflow:

1. Receive `contentBlockStart` and record `contentBlockIndex`.
2. Accumulate `toolUse` deltas into a buffer associated with that block.
3. Wait for `contentBlockStop` to know the input block is complete.
4. Wait for `messageStop` and check that `stopReason` is `tool_use`.
5. Parse the complete JSON and validate against the schema.
6. Verify the tool name is on the allowlist.
7. Verify the user has permission to perform that operation.
8. Execute the tool with appropriate timeouts, auditing, and idempotency.
9. Send the tool result in the next message using the Converse structure.
10. Call the model again to generate the response for the user.

The model only proposes tool calls. The Java application decides whether to execute them. Do not let the model freely pick IAM roles, SQL queries, or arbitrary access permissions. Actions that mutate data or cause external side effects require independent authorization and validation.

## 13. Guardrails While Streaming

Amazon Bedrock Guardrails can evaluate inputs and outputs against configured policies. With streaming, you must choose how chunks are processed:

| Mode | How it works | Trade-off |
|---|---|---|
| Synchronous | The guardrail evaluates one or more response chunks before sending them to the caller. | Safer content before display, but increases chunk latency. |
| Asynchronous | Chunks are sent as soon as available; the guardrail continues evaluating in the background and can block subsequent chunks if a violation is detected. | Lower latency, but already-sent chunks may contain content not yet fully evaluated. |

Asynchronous mode cannot recall chunks already delivered to the browser and does not support sensitive information masking like synchronous mode. If the application must guarantee content is checked before display, choose synchronous processing.

With `ConverseStream`, guardrail configuration uses `GuardrailStreamConfiguration`. With `InvokeModelWithResponseStream`, guardrail configuration is passed in the corresponding request fields/headers. Verify model support and guardrail policies before deployment.

Guardrails do not replace authorization, output validation, or business rules. For example, an answer might not violate any safety policy yet still expose another user's order ID if the backend failed to check data access permissions.

When using tool calling, guardrails do not automatically evaluate every part of the tool interaction. Tool definitions, model-generated tool-use arguments, and tool results returned by the application may fall outside automatic evaluation. The backend must independently validate tool schemas, check permissions, and filter tool result data before sending it back to the model.

If enabling guardrail traces for investigation, protect traces as sensitive data. Traces may contain original unmasked values; do not write full traces to standard logs or share them broadly.

## 14. IAM Permissions for Java Applications

Key IAM actions:

| API | IAM action |
|---|---|
| Converse | `bedrock:InvokeModel` |
| ConverseStream | `bedrock:InvokeModelWithResponseStream` |
| InvokeModel | `bedrock:InvokeModel` |
| InvokeModelWithResponseStream | `bedrock:InvokeModelWithResponseStream` |
| Using inference profiles | May require `bedrock:GetInferenceProfile` depending on resource and access flow. |
| Using Guardrails | Grant `bedrock:GetGuardrail` and `bedrock:ApplyGuardrail` along with permissions on the guardrail ARN per configuration and AWS guidance. |

Grant permissions scoped to model ARNs or inference profiles and related resources according to current authorization rules. If using cross-Region inference, IAM/SCPs must allow the profile's destination Regions.

Do not use `AmazonBedrockFullAccess` for runtime applications if they only need to call a few models. Separate roles by environment and workload; restrict models, profiles, and API actions to the appropriate scope.

When using Guardrails, Prompt management, or other Bedrock resources, add the specific permissions required for each capability rather than granting broad wildcard permissions.

## 15. Inference Profiles and Cross-Region Inference

An inference profile lets you invoke a model via a profile resource. Cross-Region inference can route requests from a source Region to one of the destination Regions defined by the profile.

In Java, `modelId` can be an inference profile ID or ARN:

~~~java
String modelId = System.getenv("BEDROCK_INFERENCE_PROFILE_ID");

ConverseStreamRequest request = ConverseStreamRequest.builder()
    .modelId(modelId)
    .messages(userMessage)
    .build();
~~~

Before using cross-Region inference, you should:

- Check whether the source Region supports the profile.
- Read the profile's list of destination Regions.
- Allow inference actions in all required destination Regions in IAM/SCPs.
- Review data residency and data handling policies.
- Evaluate latency, throughput, and costs per profile.

Destination Regions may include opt-in Regions. Requests can be routed to these Regions even if the account has not enabled that Region normally; prompts and outputs may be stored in the opt-in Region for abuse detection. If an SCP blocks a destination Region in the profile, requests can fail even if other destinations are allowed.

Do not assume profile IDs or destination lists remain static forever. AWS may update Global profiles when adding new commercial Regions; geographic profiles have their own stability rules. Check the model detail page and `GetInferenceProfile` before changing routing policies.

## 16. Timeouts, Retries, and Error Handling

Streaming can last longer than a short inference request. Timeouts must account for connection time, time-to-first-token, inter-chunk intervals, and total generation duration.

The AWS SDK for Java 2.x has two main timeout layers:

- API call attempt timeout: limits the duration of a single attempt.
- API call timeout: limits the entire operation, including retries and backoff.

The SDK does not set a default API call timeout or attempt timeout. For streaming, the API call timeout must be long enough for the entire generation. Do not set a read timeout shorter than valid silent intervals between chunks; otherwise, long streams can be cut off mid-way.

### 16.1. Common Errors

| Error | HTTP | Common cause | Resolution |
|---|---:|---|---|
| AccessDeniedException | 403 | Missing IAM, SCP, or model/profile permissions | Verify action, resource ARN, and Region. |
| ResourceNotFoundException | 404 | Incorrect model ID/profile or unavailable in Region | Check model catalog and profile. |
| ValidationException | 400 | Invalid payload, parameters, or message schema | Validate request against model/API schema. |
| ThrottlingException | 429 | Exceeded quota or throughput | Backoff, reduce concurrency, check quotas or capacity. |
| ServiceQuotaExceededException | 400 | Exceeded a specific service quota | Check Service Quotas and account configuration. |
| ModelTimeoutException | 408 | Model processing exceeded allowed time | Reduce prompt/output size, check model latency and request limits. |
| ModelStreamErrorException | 424 | Error occurred during streaming | Record partial output, investigate model error, decide on retry. |
| InternalServerException | 500 | Temporary internal error | Retry using standard strategy and backoff. |
| ServiceUnavailableException | 503 | Bedrock temporarily lacks capacity or is unavailable | Backoff with jitter, consider an appropriate inference profile. |

### 16.2. Retries Must Not Corrupt Output

The AWS SDK has retry strategies for retryable errors such as throttling, network timeouts, and transient service errors. The standard retry strategy is a suitable default for most workloads.

With streaming, note one caveat: if part of the output has already been sent to the browser and the connection fails, retrying the entire request can generate a brand new answer from the beginning. If the application appends the new response to the old one, the user will see duplicated or garbled context.

How to handle it:

- Distinguish errors before receiving any chunk from errors after chunks have been emitted.
- If no content has been emitted yet, retrying can be safe per policy.
- If partial output has already been emitted, mark the stream as incomplete.
- Only restart generation when the application can reset the UI or explicitly start a new attempt.
- Never automatically append retry output onto old partial output.
- Use request/session IDs and attempt IDs to track state.
- For tool calls or business actions, use independent idempotency and authorization.

Do not blindly retry `ValidationException` or `AccessDeniedException`. Those errors require fixing the request or policy.

## 17. Observability and Token Usage

A production application should measure both model performance and user experience.

| Metric | Meaning |
|---|---|
| Time to first token | Time from sending the request to receiving the first text chunk. |
| Inter-token/chunk latency | Time interval between chunks. |
| Total generation time | Time from request to `messageStop`. |
| Input tokens | Tokens in the prompt and conversation context. |
| Output tokens | Tokens generated by the model. |
| Stop reason | Reason the model stopped generation. |
| Error rate | Error rate by API, model, Region, and tenant. |
| Throttle rate | Rate of quota-limited requests. |
| Cancellation rate | Streams canceled by user/client. |
| Partial completion rate | Responses interrupted after sending partial output. |

The `ConverseStream` metadata event includes usage and metrics. Use this data to calculate cost estimates, enforce token budgets, and analyze latency. Do not infer output token count by counting deltas; a single delta can contain multiple tokens or just part of a token.

### 17.1. Model Invocation Logging

Bedrock model invocation logging can write requests, responses, and metadata to Amazon S3 or CloudWatch Logs. Logging is disabled by default; when enabled, data is stored according to the destination configuration.

Invocation logs may contain prompts, document contents, responses, and identifying information. Before enabling:

- Identify data classification.
- Restrict log read permissions.
- Configure retention and encryption.
- Do not put secrets or credentials in prompts.
- Consider masking or redaction before sending content.
- Verify legal requirements and organizational policies.

Do not turn on full-payload logging just for debugging without assessing the data impact.

## 18. Prompt and Output Security

Prompts may contain user information, internal documents, or business data. Responses may contain inaccurate information or unauthorized content if the backend is poorly designed.

Best practices:

- Authenticate users before invoking the model.
- Check data access permissions before putting data into prompts.
- Do not treat model-generated content as a source of truth.
- Use Guardrails according to appropriate policies.
- Validate JSON or structured outputs against schemas.
- Never execute SQL statements, shell commands, or tool calls directly from raw text output.
- Never let the model decide access permissions.
- Log audit metadata without exposing sensitive prompts.
- Enforce quotas, rate limits, and token budgets per user/tenant.
- Implement timeouts and cancellation for long-running requests.

Streaming increases safety requirements because output may be displayed before the full message finishes. If the application needs moderation before display, choose guardrail synchronous mode or buffer content until validation finishes.

## 19. Practical Scenario: Java Support Assistant

An enterprise wants to build a technical support assistant for employees. Users ask questions about AWS; the application retrieves authorized internal documents, sends context to Bedrock, and streams the answer to the chat UI.

### 19.1. Processing Flow

1. The browser sends the question and conversation ID to the Java backend.
2. The backend authenticates the employee and checks document access permissions.
3. The retrieval service finds relevant document passages.
4. The backend constructs the system prompt and user message.
5. The backend calls `ConverseStream` using `BedrockRuntimeAsyncClient`.
6. Text deltas are pushed to the browser via SSE.
7. `messageStop` and `metadata` are recorded.
8. The complete assistant message is saved to conversation history.
9. The backend logs token usage, latency, and error status.

~~~mermaid
sequenceDiagram
    participant Browser
    participant Java as Java backend
    participant RAG as Retrieval service
    participant Bedrock as Bedrock Runtime
    participant Store as Conversation store

    Browser->>Java: Question + session ID
    Java->>Java: Authenticate and authorize
    Java->>RAG: Retrieve permitted documents
    RAG-->>Java: Relevant context
    Java->>Bedrock: ConverseStream
    loop Streaming deltas
        Bedrock-->>Java: contentBlockDelta
        Java-->>Browser: SSE token event
    end
    Bedrock-->>Java: messageStop + metadata
    Java->>Store: Save completed conversation
    Java-->>Browser: done event
~~~

### 19.2. Production Requirements

- Each session has an owner and authorization scope.
- Retrieved documents must be filtered by user permissions before being placed into prompts.
- Limits exist on document count and context tokens.
- Timeouts exist for retrieval and Bedrock requests.
- Cancellation triggers when the browser disconnects.
- Partial outputs are never saved as final assistant answers.
- Retry policies and dedicated handling exist for errors after partial chunks.
- Guardrails and output validation are active.
- Token budgets and rate limits apply per tenant.
- Log correlation IDs exist for investigation without logging full prompts.

## 20. Common Design Mistakes

1. **Using `BedrockClient` to call `ConverseStream`.** Streaming inference belongs to the Bedrock Runtime async client.
2. **Confusing control plane and runtime endpoints.** `GetFoundationModel` belongs to control plane; `ConverseStream` belongs to runtime.
3. **Assuming every model supports streaming.** Always verify `responseStreamingSupported` and API compatibility.
4. **Using a model ID in the wrong Region.** Model/profile availability depends on Region.
5. **Embedding access keys in source code.** Use `DefaultCredentialsProvider` and IAM roles.
6. **Using one model's `InvokeModel` payload for another model.** Invoke request bodies depend on provider/model.
7. **Assuming each delta is one word or one token.** A delta is a content chunk, not a token boundary.
8. **Handling only text deltas.** Streams can contain tool-use or reasoning blocks.
9. **Parsing tool JSON before all chunks arrive.** Buffer by `contentBlockIndex` and wait for `contentBlockStop`.
10. **Assuming `messageStop` always means `end_turn`.** Check `stopReason`, especially for `tool_use` or `max_tokens`.
11. **Saving partial output as a complete answer.** Commit assistant messages only when the stream completes per policy.
12. **Retrying and appending new output onto old output.** This can produce duplicate or corrupted content.
13. **Blocking the event-loop inside callbacks.** Offload data to a queue or reactive pipeline.
14. **Setting timeouts too short.** Streams can be terminated mid-generation.
15. **Ignoring cross-Region destinations.** An SCP blocking one destination can fail profile requests.
16. **Enabling asynchronous guardrails while expecting pre-display blocking.** Already-sent chunks cannot be recalled.
17. **Logging full prompts without controls.** Invocation logs can contain sensitive data.
18. **Assuming Bedrock retains conversation history.** Applications must store and send required messages.
19. **Leaving token usage unchecked.** Long prompt histories and large outputs increase latency/costs.
20. **Failing to close clients.** This can leak threads and connection pools.

## 21. Self-Check Questions

**1. How does Bedrock Runtime differ from the Bedrock control plane?**

The control plane is used to discover/manage resources; Runtime performs model inference.

**2. Which Java client does ConverseStream require?**

`BedrockRuntimeAsyncClient` from the AWS SDK for Java 2.x.

**3. When should you use ConverseStream?**

When the model supports messages and streaming, the application needs a unified conversational API, and you want incremental output.

**4. When should you use InvokeModelWithResponseStream?**

When you need a model's specific request/response schema or a capability not exposed by Converse.

**5. Which IAM action is required for ConverseStream?**

`bedrock:InvokeModelWithResponseStream`.

**6. What can a `contentBlockDelta` event contain?**

Text, reasoning content, or partial tool-use input.

**7. Why must you use `contentBlockIndex`?**

To group events belonging to the same content block when a message has multiple blocks.

**8. What information does `messageStop` provide?**

It marks the end of the message and carries `stopReason`.

**9. Does Bedrock automatically store conversation history?**

No. The application manages and sends the required messages for each turn.

**10. Why should you not execute a tool upon receiving partial JSON?**

The input is incomplete; you must wait for the block to finish, then parse, validate, and authorize before executing.

**11. How does API call timeout differ from attempt timeout?**

Attempt timeout limits a single call attempt; API call timeout limits the entire operation including retries and backoff.

**12. Why does retrying after partial output require special handling?**

A new request can generate a different answer from scratch; appending to old output can create duplicates or inaccuracies.

**13. How does cross-Region inference affect IAM/SCPs?**

Destination Regions in the profile must be permitted; blocking any destination can cause requests to fail.

**14. How do synchronous and asynchronous guardrails differ?**

Synchronous inspects chunks before sending, increasing latency; asynchronous sends faster but may let uninspected chunks slip through.

**15. Why must invocation logging be controlled?**

Logs can contain prompts, responses, and sensitive data; appropriate encryption, retention, and access controls are required.

## 22. Production Checklist

- [ ] SDK for Java 2.x and `bedrockruntime` dependency are managed via BOM.
- [ ] Client uses `DefaultCredentialsProvider` or an appropriate credential provider.
- [ ] Region, model ID, and streaming support are verified.
- [ ] Model access/EULA/first-time-use requirements are completed.
- [ ] Converse or Invoke API is chosen according to model capabilities.
- [ ] IAM role has only necessary inference actions and resources.
- [ ] Cross-Region profile destination Regions are reviewed against SCPs/IAM.
- [ ] Async client is reused and closed properly according to lifecycle.
- [ ] Callbacks do not block the event loop.
- [ ] Chunks are reassembled by `contentBlockIndex` and content type.
- [ ] Tool-use JSON is processed only after the block completes.
- [ ] `stopReason` and usage metadata are recorded.
- [ ] Conversation history is managed at the application layer.
- [ ] API call timeout and attempt timeout match generation duration.
- [ ] Retries do not duplicate partial output.
- [ ] Client disconnect/cancellation is handled.
- [ ] Guardrail streaming mode matches moderation requirements.
- [ ] Prompts/outputs are not logged outside policy.
- [ ] Token budgets, concurrency, and rate limits are configured.
- [ ] Dashboards exist for time-to-first-token, total latency, token usage, and error rate.
- [ ] Runbooks exist for AccessDenied, throttling, timeouts, and stream failures.
- [ ] Tests cover multi-turn, tool use, long responses, and partial stream failures.

## References

- [Amazon Bedrock Runtime examples using SDK for Java 2.x](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/java_bedrock-runtime_code_examples.html)
- [Amazon Bedrock examples using SDK for Java 2.x](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/java_bedrock_code_examples.html)
- [Inference using Converse API](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html)
- [Converse API reference](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html)
- [ConverseStream API reference](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_ConverseStream.html)
- [Invoke API](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-api.html)
- [InvokeModelWithResponseStream API reference](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_InvokeModelWithResponseStream.html)
- [Supported foundation models in Amazon Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/models-supported.html)
- [Prerequisites for running model inference](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-prereq.html)
- [Request access to models](https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html)
- [Supported Regions and models for inference profiles](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-support.html)
- [Use an inference profile](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles.html)
- [Tool use with the Converse API](https://docs.aws.amazon.com/bedrock/latest/userguide/tool-use.html)
- [Use Guardrails with the Converse API](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-use-converse-api.html)
- [Set up permissions to use Amazon Bedrock Guardrails](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-permissions.html)
- [Enforce the use of specific guardrails in model inference requests](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-permissions-id.html)
- [Configure streaming response behavior to filter content](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-streaming.html)
- [Monitor model invocation using CloudWatch Logs and Amazon S3](https://docs.aws.amazon.com/bedrock/latest/userguide/model-invocation-logging.html)
- [Programming asynchronously using AWS SDK for Java 2.x](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/asynchronous.html)
- [Configure timeouts in AWS SDK for Java 2.x](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/timeouts.html)
- [Configure retry behavior in AWS SDK for Java 2.x](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/retry-strategy.html)
- [Best practices for using AWS SDK for Java 2.x](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/best-practices.html)
