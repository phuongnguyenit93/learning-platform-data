# Calling Generative AI from a Java Application

In the **AI and Machine Learning on OCI** chapter of the **CLOUD_PROVIDERS_ORACLE** module, this lesson guides you through integrating OCI Generative AI into a Java application via the OCI Java SDK. Learners progress from choosing a model, region, and API identity to constructing a chat request, parsing responses, handling errors, and operating within an authorized compartment.

The running scenario is a customer support service: a Java backend receives support ticket text, asks a model to produce a Vietnamese summary, and returns it to a support agent. The goal is to add content generation to an existing application; the model must never automatically mutate business data simply because it returned plausible-looking text.

## 1. Objectives and integration flow

After this lesson, learners will be able to:

- Distinguish OCI authentication, IAM authorization, HTTP endpoints, and model identifiers.
- Configure dependencies, profiles, and environment parameters for a Java application.
- Call the Chat API in non-streaming mode and read text from structured responses.
- Choose appropriate authentication when running on a developer workstation versus OCI resources.
- Set input, output, timeout, retry, and concurrency bounds to control quality, latency, and cost.

Reference flow:

```mermaid
sequenceDiagram
    participant U as User or support agent
    participant J as Java Backend
    participant S as OCI Java SDK
    participant G as OCI Generative AI
    U->>J: Submit content to summarize
    J->>J: Authenticate user, check permissions and data
    J->>S: ChatRequest and model configuration
    S->>G: HTTPS with request signed by OCI identity
    G-->>S: Chat result or service error
    S-->>J: ChatResponse and request ID
    J->>J: Validate response, record operational metrics
    J-->>U: Summary or appropriate error status
```

The backend holds OCI credentials and enforces application policies. Browsers communicate only with the backend and never receive an OCI user's private key. Application user identity and the OCI identity used by the backend to call the service are two separate layers, so the application must still enforce per-user data access permissions.

## 2. Understanding the required configuration values

### 2.1. Region, model, and serving mode

Before writing code, pick a chat model available in the target region that handles Vietnamese adequately and supports the request format you plan to use. Not every model is present in every region or supports the same parameters. Verify the model list, on-demand availability, and retirement schedules in [Oracle: Offered Pretrained Foundation Models](https://docs.oracle.com/en-us/iaas/Content/generative-ai/pretrained-models.htm) and [Oracle: Regional Availability](https://docs.oracle.com/en-us/iaas/Content/generative-ai/model-endpoint-regions.htm).

| Value | Meaning | Common mistake |
| --- | --- | --- |
| Tenancy OCID | Tenancy associated with the OCI identity | Using it instead of compartment OCID in requests |
| Compartment OCID | Resource/authorization scope required when calling the service | Confusing compartment display name with OCID |
| Inference endpoint | HTTPS URL of the API serving inference requests | Using the model management endpoint or Console UI URL |
| Model ID | Model identifier accepted by on-demand mode | Assuming every model ID is an OCID or using the display name |
| Dedicated endpoint ID | OCID of an endpoint resource on a dedicated AI cluster | Passing this OCID into the client's HTTP URL setting |
| API format | Request/response schema family, such as Generic or Cohere | Changing only the model ID while keeping an incompatible body structure |

`OnDemandServingMode` takes `modelId`; `DedicatedServingMode` takes `endpointId`. These are two variants of the serving configuration inside the request body, distinct from the client's HTTP address. [Oracle Java SDK: OnDemandServingMode](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/generativeaiinference/model/OnDemandServingMode.html), [DedicatedServingMode](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/generativeaiinference/model/DedicatedServingMode.html).

This lab uses **on-demand, Generic Chat, and non-streaming responses**. Obtain the exact model ID and inference endpoint from official documentation for your chosen model/region. Placeholders formatted as `<...>` in this lesson must be replaced, not sent verbatim to OCI.

### 2.2. Inference SDK vs. management SDK

The `oci-java-sdk-generativeaiinference` library provides the client for inference operations, including `chat`. Management operations such as listing models or creating resources use the corresponding management API and client; adding the inference dependency does not mean the application needs permissions to create dedicated clusters.

In this example, the model configuration is determined before startup. The application does not need to list all models on every user request. Doing so reduces API calls and allows governing approved models via deployment configuration.

## 3. Granting IAM permissions and preparing authentication

### 3.1. Permissions to call the Chat API

For a developer group `GenAiJavaDevelopers` and an example compartment `AiSandbox`, a policy for chat operations is:

```text
Allow group GenAiJavaDevelopers to use generative-ai-chat in compartment AiSandbox
```

When selecting models in the Console or calling APIs to list models, grant corresponding permissions, for example:

```text
Allow group GenAiJavaDevelopers to inspect generative-ai-model in compartment AiSandbox
```

Group names must use your tenancy's identity domain syntax if required by the environment. Policy authors must also have permission to create policies at the appropriate scope. Sample policies must be adapted to your actual compartments and existing grants.

The `generative-ai-chat` resource type supports `use` permission for the `Chat` operation; there is no need to grant `manage generative-ai-family in tenancy` just to complete this example. [Oracle: API-Level Permissions for Chat](https://docs.oracle.com/en-us/iaas/Content/generative-ai/chat-permissions.htm).

If you need to restrict models, add a `target.model.id` condition for approved models. IAM permissions are additive: another broader policy can render a conditional restriction ineffective. Model listing permissions and conditional inference permissions must also be evaluated separately. [Oracle: Limiting Model Inference Access](https://docs.oracle.com/en-us/iaas/Content/generative-ai/limit-model-access.htm).

### 3.2. Profile for a developer workstation

The example uses an API signing key whose public key is registered to an OCI user with appropriate permissions. Create a profile in the user's OCI config file, typically `~/.oci/config`; on Windows, this is usually inside `.oci` under the user's home directory.

```ini
[GENAI_DEV]
user=ocid1.user.oc1..<USER_ID>
fingerprint=<PUBLIC_KEY_FINGERPRINT>
tenancy=ocid1.tenancy.oc1..<TENANCY_ID>
region=<REGION_ID>
key_file=C:/Users/YourUser/.oci/oci_api_key.pem
```

The `key_file` path must point to an actual PEM private key on the machine running Java. The example uses an absolute path with `/` separators for readability on Windows. Never put key files into repositories, container images, or frontend assets. If the key is encrypted with a passphrase, configure passphrase delivery per SDK and runtime environment; do not assume the profile snippet above handles that case automatically.

An OCI API signing key signs requests using a key pair; it differs from a bearer token string and from a Generative AI API key used with other authentication interfaces. This lesson uses the OCI SDK request-signing mechanism. Profile structure and field meanings are documented in [Oracle: SDK and CLI Configuration File](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/sdkconfig.htm).

A profile identifies an identity and default settings. It does not grant IAM permissions on its own, nor does it guarantee that the region offers the chosen model. The HTTP endpoint in the example is passed explicitly when building the client, so it must match your lab's region/model.

## 4. Declaring Java dependencies

The example uses **JDK 17, Maven, and OCI Java SDK 3.99.0** as a concrete version baseline. This version is pinned to illustrate the API, not claimed as the latest release. When applying to a real project, pick an SDK version matching project dependency policies and keep all OCI modules aligned on the same version.

A standalone project layout for the lab can look like:

```text
oci-genai-java-demo/
  pom.xml
  src/main/java/example/GenAiChatDemo.java
```

Illustrative `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>oci-genai-java-demo</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <oci.sdk.version>3.99.0</oci.sdk.version>
  </properties>

  <dependencyManagement>
    <dependencies>
      <dependency>
        <groupId>com.oracle.oci.sdk</groupId>
        <artifactId>oci-java-sdk-bom</artifactId>
        <version>${oci.sdk.version}</version>
        <type>pom</type>
        <scope>import</scope>
      </dependency>
    </dependencies>
  </dependencyManagement>

  <dependencies>
    <dependency>
      <groupId>com.oracle.oci.sdk</groupId>
      <artifactId>oci-java-sdk-generativeaiinference</artifactId>
    </dependency>
    <dependency>
      <groupId>com.oracle.oci.sdk</groupId>
      <artifactId>oci-java-sdk-common-httpclient-jersey3</artifactId>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.0</version>
      </plugin>
    </plugins>
  </build>
</project>
```

OCI SDK 3.x requires choosing a matching HTTP client library; this example chooses Jersey 3. Adding only the inference module without an HTTP implementation causes client initialization errors at runtime. Using the BOM aligns OCI modules, though it does not automatically resolve every conflict with framework-managed dependencies in a project. [Oracle: Getting Started with the Java SDK](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/javasdkgettingstarted.htm).

If a project already uses Jersey 2, choose the corresponding HTTP implementation and inspect the dependency tree; never add both implementations just to try everything. With Spring Boot or other frameworks, verify the exact Jakarta/Jersey versions actually used by the application.

## 5. Building and sending a Chat request in Java

### 5.1. Participating classes

| Class | Role in the example |
| --- | --- |
| `ConfigFileAuthenticationDetailsProvider` | Reads the profile and supplies request-signing credentials |
| `GenerativeAiInferenceClient` | Communicates with the inference API |
| `SystemMessage`, `UserMessage` | Represent roles in a Generic Chat conversation |
| `TextContent` | Content block holding text |
| `GenericChatRequest` | Holds messages and generation parameters |
| `ChatDetails` | Combines compartment, serving mode, and chat request |
| `ChatRequest` | Outer SDK request carrying metadata like request ID and retry configuration |
| `ChatResponse`, `GenericChatResponse` | HTTP/SDK response and typed chat response body |

`GenericChatRequest` provides builders for messages, token limits, temperature, and streaming mode. Just because fields exist in the SDK does not mean every model supports every field combination. Some models require structures such as `CohereChatRequest`; when swapping models, check both request and response structures. [Oracle Java SDK: GenericChatRequest](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/generativeaiinference/model/GenericChatRequest.html).

### 5.2. Complete illustrative program

Save the following code as `src/main/java/example/GenAiChatDemo.java` in your lab project. The configured model must support Generic Chat with system messages, `maxTokens`, and `temperature` as shown.

```java
package example;

import com.oracle.bmc.ClientConfiguration;
import com.oracle.bmc.auth.ConfigFileAuthenticationDetailsProvider;
import com.oracle.bmc.generativeaiinference.GenerativeAiInferenceClient;
import com.oracle.bmc.generativeaiinference.model.BaseChatResponse;
import com.oracle.bmc.generativeaiinference.model.ChatChoice;
import com.oracle.bmc.generativeaiinference.model.ChatContent;
import com.oracle.bmc.generativeaiinference.model.ChatDetails;
import com.oracle.bmc.generativeaiinference.model.GenericChatRequest;
import com.oracle.bmc.generativeaiinference.model.GenericChatResponse;
import com.oracle.bmc.generativeaiinference.model.Message;
import com.oracle.bmc.generativeaiinference.model.OnDemandServingMode;
import com.oracle.bmc.generativeaiinference.model.SystemMessage;
import com.oracle.bmc.generativeaiinference.model.TextContent;
import com.oracle.bmc.generativeaiinference.model.UserMessage;
import com.oracle.bmc.generativeaiinference.requests.ChatRequest;
import com.oracle.bmc.generativeaiinference.responses.ChatResponse;
import com.oracle.bmc.model.BmcException;
import com.oracle.bmc.retrier.RetryConfiguration;

import java.nio.file.Path;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

public final class GenAiChatDemo {
    public static void main(String[] args) throws Exception {
        String configFile = envOrDefault(
                "OCI_CONFIG_FILE",
                Path.of(System.getProperty("user.home"), ".oci", "config")
                        .toString());
        String profile = envOrDefault("OCI_PROFILE", "GENAI_DEV");
        String compartmentId = requiredEnv("OCI_COMPARTMENT_ID");
        String endpoint = requiredEnv("OCI_GENAI_ENDPOINT");
        String modelId = requiredEnv("OCI_GENAI_MODEL_ID");

        var provider = new ConfigFileAuthenticationDetailsProvider(
                configFile, profile);

        ClientConfiguration clientConfig = ClientConfiguration.builder()
                .connectionTimeoutMillis(10_000)
                .readTimeoutMillis(90_000)
                .build();

        List<ChatContent> instructions = List.of(
                TextContent.builder().text("""
                        You assist customer support staff.
                        Summarize the user's content in Vietnamese,
                        at most 5 lines. Use only the provided information.
                        If information is missing, state clearly what is missing.
                        """).build());

        List<ChatContent> ticket = List.of(
                TextContent.builder().text("""
                        The customer has been unable to log in since 09:00 today.
                        The screen reports that the verification code has expired.
                        The customer requested a new code twice but still gets an error.
                        No details are available yet about the browser or other error codes.
                        """).build());

        List<Message> messages = List.of(
                SystemMessage.builder().content(instructions).build(),
                UserMessage.builder().content(ticket).build());

        GenericChatRequest chat = GenericChatRequest.builder()
                .messages(messages)
                .maxTokens(512)
                .temperature(0.2)
                .isStream(false)
                .build();

        ChatDetails details = ChatDetails.builder()
                .compartmentId(compartmentId)
                .servingMode(OnDemandServingMode.builder()
                        .modelId(modelId)
                        .build())
                .chatRequest(chat)
                .build();

        String requestId = "java-genai-" + UUID.randomUUID();
        String retryToken = UUID.randomUUID().toString();

        ChatRequest request = ChatRequest.builder()
                .chatDetails(details)
                .opcRequestId(requestId)
                .opcRetryToken(retryToken)
                // The lab performs a single attempt at the SDK retry layer.
                .retryConfiguration(RetryConfiguration.NO_RETRY_CONFIGURATION)
                .build();

        try (GenerativeAiInferenceClient client =
                     GenerativeAiInferenceClient.builder()
                             .endpoint(endpoint)
                             .configuration(clientConfig)
                             .build(provider)) {

            long started = System.nanoTime();
            ChatResponse response = client.chat(request);
            long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - started);

            if (response.getChatResult() == null) {
                throw new IllegalStateException("Missing ChatResult");
            }

            BaseChatResponse body = response.getChatResult().getChatResponse();
            if (!(body instanceof GenericChatResponse generic)) {
                throw new IllegalStateException(
                        "Unexpected chat response format for this adapter");
            }

            List<ChatChoice> choices = generic.getChoices();
            if (choices == null || choices.isEmpty() || choices.get(0) == null) {
                throw new IllegalStateException("No chat choice returned");
            }

            ChatChoice choice = choices.get(0);
            String text = extractText(choice.getMessage());
            if (text.isBlank()) {
                throw new IllegalStateException("No text content returned");
            }

            System.err.printf(
                    "requestId=%s elapsedMs=%d finishReason=%s%n",
                    response.getOpcRequestId(), elapsedMs,
                    choice.getFinishReason());
            System.out.println(text);

        } catch (BmcException e) {
            // Do not print the full request, prompt, or exception details.
            System.err.printf(
                    "requestId=%s status=%d serviceCode=%s%n",
                    e.getOpcRequestId(), e.getStatusCode(), e.getServiceCode());
            System.exit(2);
        }
    }

    private static String extractText(Message message) {
        if (message == null || message.getContent() == null) {
            return "";
        }
        StringBuilder result = new StringBuilder();
        for (ChatContent part : message.getContent()) {
            if (part instanceof TextContent text && text.getText() != null) {
                if (result.length() > 0) {
                    result.append('\n');
                }
                result.append(text.getText());
            }
        }
        return result.toString();
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing environment: " + name);
        }
        return value.trim();
    }

    private static String envOrDefault(String name, String fallback) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? fallback : value.trim();
    }
}
```

The example creates one client for the lifetime of the program and closes it on exit. In a long-running backend, initialize the client in the application configuration layer, reuse it across requests, and close it on shutdown. Once configured, avoid mutating a shared client's endpoint per user. Client reuse and thread-safety constraints are detailed in [Oracle Java SDK: Threading Model](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/javasdkconcepts.htm).

`System.exit(2)` is merely error signaling for a CLI program. In a server, map errors to exceptions or appropriate business results; never crash the entire process over a single failed inference call. The demo also sends synthetic data and prints to the console; real data handling must follow application policies.

### 5.3. Configuring and running in PowerShell

In your lab project terminal, replace all sample values before running:

```powershell
$env:OCI_PROFILE = 'GENAI_DEV'
$env:OCI_COMPARTMENT_ID = 'ocid1.compartment.oc1..<COMPARTMENT_ID>'
$env:OCI_GENAI_ENDPOINT = 'https://<INFERENCE_HOST_FOR_SELECTED_REGION>'
$env:OCI_GENAI_MODEL_ID = '<SUPPORTED_GENERIC_CHAT_MODEL_ID>'

mvn compile exec:java '-Dexec.mainClass=example.GenAiChatDemo'
```

If the config file is elsewhere, also set `OCI_CONFIG_FILE` to the full path. The environment variables in the example are read directly by this program; setting a similarly named variable does not automatically configure every OCI client in a project.

A successful run prints metadata to stderr and the summary to stdout. Generated wording may vary across runs. Acceptance criteria are that the response contains text, stays faithful to the ticket, and notes missing information—not exact string matching against a fixed sample answer.

## 6. Parsing structured responses and checking quality

### 6.1. Responses are not a top-level string

In Generic Chat, generated content resides inside `choices`; each choice has a message containing a list of content blocks. That is why the example validates the response type, checks for empty lists, and extracts `TextContent` blocks instead of calling `toString()` on `ChatResponse`.

A response might lack expected text, for example when the model refuses, outputs a different structure, or continues a tool-calling loop. When adding new capabilities, extend the adapter accordingly. Never assume a response without text automatically means a network error.

`ChatChoice` exposes `finishReason`, and Generic responses may include `usage`. Treat these as metadata to interpret according to the model and API version, guarding for null instead of assuming usage metrics are always populated. If generation stopped due to token limits, the application must recognize the summary may be incomplete. [Oracle Java SDK: ChatChoice](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/generativeaiinference/model/ChatChoice.html), [GenericChatResponse](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/generativeaiinference/model/GenericChatResponse.html).

### 6.2. Business quality must be checked separately

HTTP success only proves the API returned a response, not that the model summarized accurately. For customer support scenarios, check that:

- It does not invent causes like a locked account if the ticket provides no such detail.
- It preserves observed facts and distinguishes known information from missing information.
- It does not turn a summarization request into a refund decision, password reset, or account mutation.
- Text is properly escaped before rendering into HTML.

If requesting JSON output, parse it and validate schema, required fields, data types, and length limits. Structured output (when supported by the model) helps enforce shape, but does not replace verifying factual accuracy of the values. Never rely on ad-hoc substring slicing to treat arbitrary answers as valid JSON.

## 7. Authentication when deploying on OCI

Developers' personal private keys should not be copied onto production servers as a default practice. Choose the workload identity matching the runtime environment:

| Environment | Approach | Required configuration |
| --- | --- | --- |
| Developer workstation | Profile with API signing key or appropriate session auth | User, key/profile, and group policy |
| OCI Compute | Instance principal | Dynamic group containing the instance and policy granting chat access |
| OCI Functions or supported resources | Resource principal | Service-provided identity mechanism and matching policy |
| OKE | Workload identity where supported | Cluster config, service account, auth provider, and matching policy |

Example replacing the provider when running on Compute with instance principal configured:

```java
import com.oracle.bmc.auth.InstancePrincipalsAuthenticationDetailsProvider;

// Replaces ConfigFileAuthenticationDetailsProvider creation.
var provider = InstancePrincipalsAuthenticationDetailsProvider.builder().build();
```

Illustrative dynamic group policy:

```text
Allow dynamic-group GenAiJavaCompute to use generative-ai-chat in compartment AiSandbox
```

The dynamic group needs a matching rule selecting only the intended workload instances. Writing a policy while forgetting the matching rule—or matching the wrong instance compartment—still results in authorization failures. Selecting instance principal does not grant permissions to the instance on its own, nor does it alter the model/endpoint used by the client.

For resource principal, use the corresponding provider inside services supporting that mechanism, for example:

```java
import com.oracle.bmc.auth.ResourcePrincipalAuthenticationDetailsProvider;

var provider = ResourcePrincipalAuthenticationDetailsProvider.builder().build();
```

These are alternatives to the provider instantiation line, not sequential steps. When using workload identities, remove profile-reading code if no longer needed. Keep model, compartment, and endpoint parameters in controlled deployment configuration so updates or rollbacks require no business-logic edits.

## 8. Timeouts, retries, and reliable serving

### 8.1. Connection timeout vs. end-to-end processing budget

The example sets a 10-second connection timeout and 90-second read timeout to illustrate configuration, not universal defaults for every application. Model response time depends on context length, output size, model, and service load.

Read timeout does not replace an end-to-end deadline for a user request. Queue wait time, authentication, data retrieval, retries, and response parsing all share the application's latency budget. If an upstream gateway times out after 30 seconds while the backend keeps generating for 90 seconds, users see an error while work still consumes resources.

Establish explicit business deadlines, bound queues, and choose synchronous vs. background execution based on required response time. Canceling a wait on the Java side does not prove the service stopped processing or incurred zero cost.

### 8.2. Retries must be bounded and owned in one place

The OCI Java SDK has a retry precedence order where request-level settings can override client-level settings. The example passes `NO_RETRY_CONFIGURATION` on the request to observe a single attempt at the SDK retry layer rather than accidentally stacking application retries outside built-in SDK retries. [Oracle Java SDK: Retries](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/javasdkconcepts.htm).

| Situation category | Appropriate handling |
| --- | --- |
| Invalid request schema or unsupported model parameter | Fix configuration or payload; do not resend verbatim repeatedly |
| Signature mismatch or missing permission | Check keys, profile, system clock, and IAM |
| Rate limiting or temporary capacity limits | Backoff with jitter, cap attempt count, and respect service guidance |
| Transient server or network error | Consider retries within configured deadline and budget |
| Timeout after request was already sent | Account for the possibility the service received and completed the work |

`opcRequestId` aids traceability; it is not a deduplication key. `opcRetryToken` identifies requests to support retries under the API's contract. When implementing retries for the same logical operation, preserve the matching token and identical payload per documentation—do not mint a fresh token per attempt and treat it as the same request. Tokens have limited lifetimes and scope; they do not replace full application-level workflow idempotency. [Oracle Java SDK: ChatRequest.Builder](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/generativeaiinference/requests/ChatRequest.Builder.html).

Never stack independent retry loops across gateway, service, SDK, and job scheduler. When every layer retries multiple times, actual request volume can multiply by the product of attempts, inflating latency and making cost unpredictable.

### 8.3. Concurrency limits and behavior when the service is slow

The backend should cap concurrent Generative AI requests according to capacity and environment limits. Queues must have bounded size and wait times; never use an unbounded thread pool to mask overload.

When the service is unavailable, allow agents to continue viewing original ticket content or enqueue summarization as a background task. If using a backup model or region, verify API compatibility, IAM permissions, Vietnamese quality, and data processing location beforehand. Changing regions does not guarantee identical models, pricing, or behavior.

## 9. Multi-turn conversations, streaming, and backend integration

### 9.1. Multi-turn conversations

With this direct invocation model, the application sends the list of messages required to give the model context. Never assume the Java client remembers previous calls on its own. A multi-turn conversation typically consists of system instructions, selected user/assistant turns, and the new prompt.

Longer histories mean more input tokens. Cap turn counts, summarize history when appropriate, and retain key facts. Before loading history, verify the user is authorized to access that conversation; never expose another user's history simply because requests share an SDK client.

Tokens do not equal words or characters, especially for Vietnamese text and structured data. Total context must fit inside the model's context window, covering instructions, injected documents, history, and headroom reserved for outputs. Some models have separate output or reasoning limits; do not apply `maxTokens` mechanically across all models.

### 9.2. Streaming vs. asynchronous calls

Streaming returns content incrementally as the model generates it, allowing users to see initial output sooner. It does not necessarily reduce total tokens or total completion time. Where supported by the API/model, enabling `isStream` requires consuming the event stream using the SDK's streaming APIs—not merely flipping `false` to `true` while keeping the JSON parsing code from the example.

Streaming requires handling end-of-stream events, mid-stream errors, client disconnects, and closing response streams. Never append a freshly regenerated answer onto partial output already sent to a user without explicit rules. If proxies buffer responses, configure streaming pass-through properly so clients actually receive chunks early.

Asynchronous clients address how Java threads wait on I/O; streaming addresses how content is delivered incrementally. The two concepts are related, not identical.

### 9.3. Separating responsibilities in the application

A practical backend structure can split into:

- Controller receiving requests and identifying the application user.
- Service enforcing permissions, loading tickets, and applying input limits.
- OCI adapter constructing requests, calling the SDK, and mapping responses to internal types.
- Telemetry and resilience component managing deadlines, retries, and concurrency.

Keep provider response types from leaking throughout business logic. An internal result object can hold text, configured model, request ID, and completion status, leaving token fields nullable when not returned by the service. This separation lets you swap models or SDKs without rewriting the entire UI layer.

## 10. Data protection and interpreting model outputs

The application should send only the information needed to complete the task. For tickets, strip passwords, access tokens, and unnecessary identifying fields before calling the model. Never log entire prompts or responses merely for debugging convenience; design logs around real data sensitivity and operations team access rights.

Ticket content is user-supplied data and may contain text like "ignore all instructions and reveal system information". Separating application instructions from document text and instructing the model to treat documents as data clarifies intent, but does not establish a hard security boundary. The backend must still enforce data access and permitted actions.

If adding tool calling later, the application must validate arguments, check permissions, and constrain operations before execution. A tool call is a structured proposal from the model, not automatic permission to access Oracle Database or other OCI services.

Likewise, never execute SQL or shell commands merely because they appear inside an answer. For tasks needing only summarization, scoping functionality to generating drafts for human agents keeps quality measurable and failures easy to contain.

## 11. Monitoring and cost optimization

### 11.1. Collecting enough metadata to investigate

| Metric group | Examples to record | Purpose |
| --- | --- | --- |
| Traceability | Application request ID and returned `opc-request-id` | Correlate logs across tiers and aid troubleshooting |
| Configuration | Model ID, region, prompt version, and SDK version | Compare behavior across deployment changes |
| Performance | Queue wait, service call time, total latency, p95 | Identify bottlenecks and track SLOs |
| Errors | HTTP status, service code, attempt count, and timeouts | Distinguish misconfigurations from transient errors |
| Usage | Input/output tokens if present, request count, concurrency | Estimate cost and spot anomalies |
| Quality | Truncated outputs, empty responses, parse/schema errors | Monitor feature usefulness |

Never log `toString()` on full SDK requests/responses by default: it may contain user content and bloat logs. Request IDs are useful correlation keys, while still requiring appropriate retention and access controls.

### 11.2. Estimating according to the actual billing model

For on-demand models priced per token, a conceptual estimate is:

```text
C_inference = (T_input / U_input) × P_input
            + (T_output / U_output) × P_output

C_total = C_inference + C_backend + C_logs_storage
        + C_network + related service components
```

`P` is unit price and `U` is the token unit for the published rate. Use this formula only after verifying the chosen model's billing basis; do not apply one model's unit price to another model, or on-demand rates to dedicated clusters. For actual cost estimates, consult the [Oracle Cloud Price List](https://www.oracle.com/cloud/price-list/) and service pricing at deployment time.

Pure volume example: 5,000 requests/day averaging 1,500 input tokens and 300 output tokens equals 7.5 million input tokens and 1.5 million output tokens per day. If rates are listed per million tokens, the token estimate is `7.5 × P_input + 1.5 × P_output`. These figures exclude length variations, retries, or caching if the model offers separate cache pricing.

Optimization levers include capping output length, trimming context, sending only needed history, choosing a model balancing quality and cost, and rate-limiting per user. Setting `maxTokens` bounds generation, not total request cost, since input tokens are still processed.

Summaries can be cached for the same ticket version and prompt/model configuration. Cache keys must include permission scope and data version; cross-user or cross-tenancy cache collisions can leak unauthorized data. Budget alerts help detect spend, but should not be treated as automatic request kill-switches when thresholds are crossed.

## 12. Hands-on practice and troubleshooting

### 12.1. Practice workflow

1. Select a sandbox compartment, an available Generic Chat model, and the inference endpoint in the same region.
2. Configure group/policies and user profile; use synthetic ticket data.
3. Build the Maven project from the example, set environment variables, and execute a non-streaming call.
4. Inspect generated text, request ID, latency, and `finishReason`; cross-check the answer against ticket facts.
5. Test short, long, and incomplete inputs within a small controlled scope; note quality and latency changes.
6. Lower the output limit to observe truncation risk, then choose a limit suited to the real task.
7. Deliberately test a config error such as an invalid model ID in the sandbox, confirming the app classifies the error without infinite retries.
8. When moving to Compute, switch the auth provider, configure a dynamic group, and verify the program runs under the workload identity.

This is a guide for learners; this lesson does not claim code has already been compiled or requests executed in the reader's tenancy. A run succeeds when it calls the right model/compartment, returns useful output, tracks errors, and avoids exposing credentials.

### 12.2. Diagnostic table

| Symptom | Possibilities to check | Resolution direction |
| --- | --- | --- |
| Cannot initialize HTTP client | Missing implementation or dependency conflict | Check BOM, chosen Jersey module, and dependency tree |
| Cannot read profile/key | Wrong path, profile, or file permissions | Verify config on the actual machine running Java |
| Authentication error | Key/fingerprint mismatch, signature, or system clock | Verify key pair, user, tenancy, and clock sync |
| Unauthorized or resource not found | Wrong compartment, policy, region, or resource ID | Check both identity and call scope; do not look at HTTP code alone |
| Payload rejected | Wrong API format or parameter unsupported by model | Compare request against chosen model's capabilities |
| Rate limited | Concurrency too high or exceeding service limits | Shed load, add throttling/queuing, and bounded backoff |
| Timed out | Long context, large output, slow network or service | Measure each layer, adjust task and deadlines |
| HTTP succeeded without text | Unexpected content block, refusal, or incompatible response | Inspect structure, finish reason, and adapter |
| Answer cut off at the end | Hit output token limit or abnormal stream termination | Check finish reason, token limit, and transport |
| Cost rises despite flat user count | Long history, excessive retries, longer outputs, or looping background tasks | Measure tokens, attempt counts, and prompt/model versions |

A complete Java integration must clarify four things: which identity is allowed to call, which model is actually invoked, how outputs are validated and used, and how much time and resources each request consumes. When those four points are captured in configuration, code, and observable metrics, Generative AI capabilities can operate reliably within your application's OCI infrastructure.
