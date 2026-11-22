# Gọi Bedrock từ Java và xử lý phản hồi streaming

Một ứng dụng Java có thể gọi Amazon Bedrock để tạo nội dung, tóm tắt tài liệu, trả lời câu hỏi hoặc hỗ trợ quy trình nghiệp vụ. Với một API request thông thường, ứng dụng gửi prompt và chờ toàn bộ câu trả lời. Với streaming, Bedrock trả kết quả thành từng phần ngay khi model tạo ra chúng. Người dùng có thể bắt đầu đọc sớm hơn, còn ứng dụng có thể chuyển từng chunk tới giao diện web, mobile hoặc một dịch vụ downstream.

AWS SDK for Java 2.x cung cấp Amazon Bedrock Runtime client để gọi các model. Với ứng dụng hội thoại, **Converse** và **ConverseStream** là lựa chọn phù hợp vì chúng cung cấp cấu trúc message thống nhất cho các model hỗ trợ conversation. Với các tính năng hoặc payload riêng của từng model, ứng dụng có thể dùng **InvokeModel** và **InvokeModelWithResponseStream**.

Streaming làm thay đổi cách ứng dụng xử lý response: một câu trả lời có thể được chia thành nhiều event, một content block có thể có nhiều delta, một stream có thể kết thúc bằng nhiều stop reason và lỗi có thể xảy ra sau khi một phần nội dung đã được gửi tới người dùng. Vì vậy, ứng dụng phải quản lý callback, lỗi, timeout, trạng thái hội thoại và nội dung chưa hoàn chỉnh một cách rõ ràng.

## Mục tiêu học tập

Sau bài học, người học có thể:

- Phân biệt Amazon Bedrock control plane với Bedrock Runtime.
- Cấu hình AWS SDK for Java 2.x, Region và credential provider.
- Chọn Converse, ConverseStream, InvokeModel hoặc InvokeModelWithResponseStream.
- Gọi model đồng bộ bằng Java SDK.
- Dùng BedrockRuntimeAsyncClient để nhận response streaming.
- Xử lý các event messageStart, contentBlockDelta, messageStop và metadata.
- Quản lý nhiều content block, tool-use event và reasoning block.
- Tổ chức conversation history ở tầng ứng dụng.
- Thiết lập IAM permission, inference profile, timeout và retry.
- Kết hợp Guardrails với streaming và bảo vệ dữ liệu nhạy cảm.
- Theo dõi token usage, latency, throttling và lỗi trong production.

## 1. Amazon Bedrock Runtime trong kiến trúc Java

Amazon Bedrock cung cấp các foundation models thông qua API được quản lý. Ứng dụng Java không cần tự triển khai hạ tầng GPU hoặc quản lý model server; ứng dụng gửi request tới Bedrock Runtime endpoint và nhận kết quả inference.

Cần phân biệt hai nhóm client:

| Nhóm | SDK client | Mục đích |
|---|---|---|
| Bedrock control plane | BedrockClient | Khám phá foundation models, lấy thông tin model, quản lý inference profiles và các tài nguyên control-plane được hỗ trợ. |
| Bedrock Runtime | BedrockRuntimeClient | Gọi inference đồng bộ như Converse hoặc InvokeModel. |
| Bedrock Runtime async | BedrockRuntimeAsyncClient | Gọi API bất đồng bộ và xử lý streaming response như ConverseStream hoặc InvokeModelWithResponseStream. |

Converse và Invoke API sử dụng endpoint Bedrock Runtime. Một request inference cần có model ID hoặc resource ID phù hợp, Region có hỗ trợ model và IAM permission tương ứng.

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

Trong kiến trúc này, Java application chịu trách nhiệm xác thực người dùng, chuẩn bị prompt, quản lý conversation history, gọi model, xử lý output và áp dụng các business rules. Bedrock cung cấp model inference; ứng dụng vẫn phải kiểm soát cách nội dung được sử dụng.

## 2. Chuẩn bị AWS SDK for Java 2.x

### 2.1. Thêm dependency

Với Maven, nên dùng AWS SDK BOM để các module có cùng phiên bản:

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

Thay 2.x.y bằng một phiên bản AWS SDK for Java 2.x đã được dự án kiểm thử. BOM giúp các module AWS SDK dùng cùng version, tránh lỗi do trộn những phiên bản không tương thích.

Với Gradle:

~~~kotlin
dependencies {
    implementation(platform("software.amazon.awssdk:bom:2.x.y"))
    implementation("software.amazon.awssdk:bedrockruntime")
}
~~~

Nếu ứng dụng cần cấu hình HTTP async client cụ thể, có thể khai báo thêm Netty hoặc AWS CRT client theo hướng dẫn SDK. Hãy chọn một HTTP implementation phù hợp với runtime và kiểm tra dependency tree trước khi đóng gói.

### 2.2. Không nhúng access key trong source code

AWS SDK for Java 2.x hỗ trợ DefaultCredentialsProvider. Provider này tìm credentials theo chuỗi cấu hình chuẩn của SDK, ví dụ environment variables, shared profile, web identity, container credentials hoặc instance role.

Trong production, ưu tiên IAM role gắn với compute environment:

- EC2 instance profile.
- ECS task role.
- EKS workload identity.
- Lambda execution role.
- IAM role được assume qua federation khi chạy ngoài AWS.

Không ghi access key hoặc secret key trực tiếp vào Java source, file cấu hình được commit vào Git hay Docker image.

### 2.3. Chọn Region và model ID

Model ID phải tồn tại và hỗ trợ inference trong Region được chọn. Ví dụ dưới đây dùng Amazon Nova Lite làm model minh họa; cần kiểm tra model availability, API compatibility và streaming support tại thời điểm triển khai.

~~~java
import software.amazon.awssdk.regions.Region;

Region region = Region.US_EAST_1;
String modelId = "amazon.nova-lite-v1:0";
~~~

Trong ứng dụng thực tế, nên lấy Region và model ID từ environment/configuration:

~~~java
Region region = Region.of(
    System.getenv().getOrDefault("AWS_REGION", "us-east-1")
);

String modelId = System.getenv().getOrDefault(
    "BEDROCK_MODEL_ID",
    "amazon.nova-lite-v1:0"
);
~~~

Model ID cũng có thể là inference profile ID/ARN, provisioned throughput ARN hoặc prompt resource được API hỗ trợ. Không mặc định mọi model đều được gọi bằng foundation model ID.

## 3. Xác minh model và quyền truy cập trước khi gọi

Trước khi triển khai, kiểm tra:

1. Model có được cung cấp trong source Region không?
2. Model có hỗ trợ Converse hoặc Invoke API mà ứng dụng chọn không?
3. Model có hỗ trợ response streaming không?
4. Account đã đáp ứng điều kiện model agreement hoặc first-time-use requirements chưa?
5. IAM role có quyền gọi inference với model/profile đó không?
6. Service quota và throughput có đủ cho tải dự kiến không?

Với control plane, có thể dùng GetFoundationModel để đọc thông tin model. Trường responseStreamingSupported cho biết model có hỗ trợ response streaming hay không. Model catalog cũng hiển thị input modality, output modality và Region availability.

Đối với phần lớn model thương mại, model access có thể được kích hoạt khi gọi lần đầu theo điều kiện AWS công bố. Một số third-party models có yêu cầu chấp thuận EULA; một số phiên bản Anthropic cần hoàn thành first-time-use case trước khi gọi. Hãy kiểm tra model access documentation thay vì giả định mọi model có cùng quy trình.

## 4. Chọn API: Converse hay Invoke?

Amazon Bedrock có hai nhóm API inference phổ biến:

| API | Streaming | Cấu trúc request | Khi nên dùng |
|---|---|---|---|
| Converse | Không | Messages, system prompt, inferenceConfig và toolConfig thống nhất | Chat, multi-turn conversation và model portability. |
| ConverseStream | Có | Giống Converse, trả response theo event | Chat cần hiển thị từng phần output. |
| InvokeModel | Không | JSON body theo schema riêng của model | Cần tham số hoặc payload riêng của model. |
| InvokeModelWithResponseStream | Có | JSON body riêng của model, response là stream chunk | Cần streaming với protocol riêng của model. |

Converse API giúp ứng dụng dùng một cấu trúc message thống nhất với các model hỗ trợ messages. Nếu model có inference parameter riêng, request có thể truyền additionalModelRequestFields theo schema của model.

InvokeModel linh hoạt với model-specific request/response format, nhưng ứng dụng phải tự xây dựng JSON body và giải mã response theo từng nhà cung cấp/model. Khi đổi model, phần mapping payload có thể phải thay đổi.

Đối với ứng dụng Java hội thoại mới, nên bắt đầu với Converse/ConverseStream nếu model hỗ trợ. Chọn Invoke family khi cần capability hoặc định dạng request riêng mà Converse chưa đáp ứng.

## 5. Gọi Converse đồng bộ bằng Java

Converse phù hợp khi ứng dụng cần một response hoàn chỉnh trước khi trả về cho caller. Ví dụ: batch job, backend API không cần token streaming hoặc một bước xử lý nội bộ.

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

Ví dụ dùng một message văn bản để tập trung vào cấu trúc API. Trong ứng dụng nhiều lượt, messages có thể chứa các message user và assistant trước đó. Converse không tự lưu session history cho ứng dụng; caller phải gửi context cần thiết trong mỗi request.

## 6. Vì sao cần streaming?

Với response không streaming, người dùng phải chờ model tạo xong toàn bộ nội dung mới nhìn thấy kết quả. Với streaming, ứng dụng nhận các phần output khi chúng được tạo ra.

Ví dụ một model trả lời câu hỏi:

- Không streaming: ứng dụng chờ toàn bộ câu trả lời, sau đó mới trả HTTP response.
- Streaming: ứng dụng nhận từng delta, đẩy tới browser qua Server-Sent Events hoặc WebSocket.

Streaming giúp giảm time-to-first-token và tạo cảm giác phản hồi nhanh hơn. Tuy nhiên, streaming không làm model suy luận nhanh hơn trong mọi trường hợp, không giảm tổng token được sinh và không tự bảo đảm câu trả lời hoàn chỉnh.

Các phần output đầu tiên có thể là một câu chưa hoàn chỉnh, một phần JSON hoặc một tool call. Ứng dụng phải phân biệt nội dung tạm thời với kết quả cuối cùng.

## 7. ConverseStream và vòng đời event

ConverseStream trả về một chuỗi event. Trình tự tổng quát:

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

Các event chính:

| Event | Ý nghĩa |
|---|---|
| messageStart | Bắt đầu một assistant message, thường mang role. |
| contentBlockStart | Bắt đầu content block; thường xuất hiện khi model tạo tool-use block. |
| contentBlockDelta | Một phần nội dung được sinh ra. Có thể là text, reasoning content hoặc tool-use input. |
| contentBlockStop | Kết thúc một content block. |
| messageStop | Kết thúc message; chứa stopReason. |
| metadata | Thông tin usage và metrics của inference. |

Các event content block được nhóm theo contentBlockIndex. Một message có thể chứa nhiều content block; không nên giả định toàn bộ output luôn là một chuỗi text duy nhất.

### 7.1. contentBlockDelta không phải lúc nào cũng là text

Delta có thể mang một trong các dạng:

- Text: phần văn bản mới được model sinh.
- Reasoning content: block reasoning có cấu trúc và có thể kèm signature.
- Tool use: một phần JSON input của tool call.

Với reasoning-enabled models, nếu ứng dụng tiếp tục hội thoại bằng reasoning content đã trả về, cần giữ nguyên signature và các message liên quan theo yêu cầu API. Không chỉnh sửa hoặc loại bỏ block có signature khi gửi lại conversation context.

Không hiển thị reasoning block cho end user như thể đó là câu trả lời cuối. Chỉ xử lý những content type mà ứng dụng được thiết kế để nhận.

### 7.2. messageStop và stopReason

messageStop đánh dấu model đã kết thúc message hiện tại. stopReason cho biết vì sao model dừng.

Ví dụ:

- end_turn: model hoàn tất lượt trả lời.
- max_tokens: model chạm giới hạn token output.
- tool_use: model muốn ứng dụng thực hiện một tool.
- stop_sequence: model gặp stop sequence được cấu hình.
- guardrail_intervened: guardrail can thiệp vào response.
- content_filtered, malformed_model_output, malformed_tool_use hoặc model_context_window_exceeded: model không thể trả lời theo cách thông thường vì nội dung bị lọc, output không hợp lệ hoặc vượt giới hạn context.

Không coi max_tokens là câu trả lời hoàn chỉnh nếu nội dung còn dang dở. UI có thể thông báo output bị giới hạn hoặc backend có thể yêu cầu model tiếp tục nếu workflow cho phép.

## 8. Gọi ConverseStream bằng BedrockRuntimeAsyncClient

Streaming sử dụng async client. AWS SDK for Java 2.x trả về CompletableFuture và dùng response handler để xử lý event khi chúng đến.

Ví dụ hoàn chỉnh cho text streaming:

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

Điểm quan trọng:

- BedrockRuntimeAsyncClient được dùng cho API async.
- ConverseStreamRequest chứa model ID, messages và inference config.
- Response handler nhận từng event.
- onContentBlockDelta chỉ xử lý text trong ví dụ này.
- CompletableFuture hoàn tất khi stream kết thúc hoặc lỗi.
- Client được đóng để giải phóng HTTP connections và thread resources.

Đây là chương trình console minh họa. Trong server ứng dụng, không nên block event-loop thread bằng get(). Hãy chuyển kết quả qua reactive pipeline, executor phù hợp hoặc cơ chế streaming của framework đang dùng.

## 9. Đẩy delta tới browser hoặc service downstream

Trong web application, Java backend thường đóng vai trò trung gian:

1. Browser gửi prompt tới Java API.
2. Java backend xác thực user và kiểm tra quota.
3. Backend gọi ConverseStream.
4. Mỗi text delta được chuyển thành một SSE event hoặc WebSocket frame.
5. Khi messageStop và metadata đến, backend gửi event kết thúc cùng thông tin usage phù hợp.
6. Backend lưu conversation state và audit metadata theo policy.

Ví dụ payload SSE đơn giản:

~~~text
event: token
data: Xin

event: token
data: chào

event: token
data: bạn

event: done
data: {"stopReason":"end_turn"}
~~~

Một token event ở tầng ứng dụng thường tương ứng một chunk text hoặc một phần chunk, không nhất thiết là một model token. SDK delta boundary, model token boundary và SSE frame boundary là ba khái niệm khác nhau.

Khi chuyển chunk tới downstream:

- Không block callback bằng database query hoặc remote API call.
- Dùng bounded queue để tránh bộ nhớ tăng không giới hạn.
- Có cơ chế backpressure hoặc giới hạn tốc độ.
- Gắn request/session ID để ghép các event.
- Xử lý browser disconnect và hủy upstream request nếu phù hợp.
- Gửi terminal event khi stream hoàn tất hoặc lỗi.

## 10. Quản lý conversation history

Converse API nhận danh sách messages. Bedrock không tự quản lý session history thay cho ứng dụng.

Một conversation nhiều lượt có thể có cấu trúc:

~~~text
[
  { role: user,      content: "What is a VPC?" },
  { role: assistant, content: "A VPC is..." },
  { role: user,      content: "How do subnets fit into it?" }
]
~~~

Khi gọi lượt tiếp theo, ứng dụng gửi các message cần thiết để model hiểu ngữ cảnh. Trong streaming, assistant response phải được ghép thành một message hoàn chỉnh trước khi đưa vào history cho lượt kế tiếp.

Best practices:

- Lưu history theo user/session trong datastore có kiểm soát quyền.
- Chỉ gửi phần context cần thiết cho câu hỏi hiện tại.
- Giới hạn số lượt hoặc token budget.
- Tóm tắt các đoạn hội thoại cũ khi history dài.
- Tách system prompt khỏi user content.
- Không cho user thay đổi system prompt bằng cách nối chuỗi tùy tiện.
- Không lưu partial assistant response như một message hoàn chỉnh nếu stream lỗi giữa chừng.

Với hệ thống có nhiều instance, không giữ conversation history chỉ trong biến static hoặc memory của một JVM. Dùng store phù hợp như DynamoDB, relational database hoặc cache có persistence theo yêu cầu.

## 11. Khi nào dùng InvokeModelWithResponseStream?

InvokeModelWithResponseStream dùng request body theo schema riêng của model. Ứng dụng phải biết tên trường prompt, inference parameters và cấu trúc response mà model yêu cầu.

Quy trình tổng quát:

1. Chọn model có responseStreamingSupported.
2. Tạo JSON request đúng model/provider schema.
3. Gọi InvokeModelWithResponseStream.
4. Nhận các chunk trong response event stream.
5. Ghép hoặc giải mã chunk theo protocol của model.
6. Trích xuất text, finish reason và usage nếu model trả các trường đó.

Ví dụ, các model có thể trả JSON fragments với cấu trúc khác nhau. Không nối tất cả bytes rồi giả định chúng luôn là một JSON document hoàn chỉnh ở từng chunk. Có thể phải giữ buffer, xử lý UTF-8 boundary và parse các event theo protocol.

Chọn InvokeModelWithResponseStream khi:

- Model chưa hỗ trợ Converse nhưng có Invoke streaming.
- Ứng dụng cần request parameter đặc thù của model.
- Ứng dụng đã có adapter riêng cho một provider/model.
- Một capability cụ thể chưa được Converse expose.

Đối với model hỗ trợ messages, ConverseStream thường giúp giảm coupling với model-specific request format.

## 12. Tool use trong ConverseStream

Một model có thể yêu cầu ứng dụng gọi một function hoặc API bên ngoài. Converse hỗ trợ tool use thông qua toolConfig.

Ví dụ ứng dụng hỗ trợ tra cứu trạng thái đơn hàng có tool:

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

Trong streaming, tool input JSON có thể được gửi thành nhiều delta. Không thực thi tool khi mới nhận một phần JSON.

Quy trình an toàn:

1. Nhận contentBlockStart và ghi nhận contentBlockIndex.
2. Gom các toolUse deltas vào buffer tương ứng với block.
3. Đợi contentBlockStop để biết input block đã hoàn tất.
4. Đợi messageStop và kiểm tra stopReason là tool_use.
5. Parse JSON hoàn chỉnh và validate schema.
6. Kiểm tra tool name có nằm trong allowlist.
7. Kiểm tra user có quyền thực hiện thao tác đó.
8. Thực thi tool với timeout, audit và idempotency phù hợp.
9. Gửi tool result trong message tiếp theo theo cấu trúc Converse.
10. Gọi model lần nữa để tạo câu trả lời cho user.

Model chỉ đề xuất tool call. Java application quyết định có thực thi hay không. Không cho model tự chọn IAM role, SQL query hoặc quyền truy cập tùy ý. Các hành động thay đổi dữ liệu hoặc gây tác động bên ngoài cần authorization và validation độc lập.

## 13. Guardrails khi streaming

Amazon Bedrock Guardrails có thể đánh giá input và output theo các policy được cấu hình. Với streaming, cần lựa chọn cách xử lý chunk:

| Mode | Cách hoạt động | Trade-off |
|---|---|---|
| Synchronous | Guardrail đánh giá một hoặc nhiều response chunks trước khi gửi chúng tới caller. | Nội dung an toàn hơn trước khi hiển thị nhưng tăng độ trễ chunk. |
| Asynchronous | Chunk được gửi ngay khi có; guardrail tiếp tục đánh giá nền và có thể chặn các chunk tiếp theo khi phát hiện vi phạm. | Độ trễ thấp hơn nhưng chunk đã gửi có thể chứa nội dung chưa được đánh giá xong. |

Asynchronous mode không thể thu hồi chunk đã tới browser và không hỗ trợ masking sensitive information như synchronous mode. Nếu ứng dụng cần bảo đảm nội dung được kiểm tra trước khi hiển thị, hãy chọn synchronous processing.

Với ConverseStream, guardrail configuration dùng GuardrailStreamConfiguration. Với InvokeModelWithResponseStream, cấu hình guardrail được truyền theo request fields/headers tương ứng. Cần kiểm tra model support và guardrail policy trước khi triển khai.

Guardrails không thay thế authorization, output validation hoặc business rules. Ví dụ, một câu trả lời có thể không vi phạm safety policy nhưng vẫn chứa order ID của user khác nếu backend không kiểm tra quyền truy cập dữ liệu.

Khi dùng tool calling, guardrail không tự đánh giá mọi thành phần của tool interaction. Tool definitions, tool-use arguments do model tạo và tool results do ứng dụng trả về có thể nằm ngoài phạm vi đánh giá tự động. Backend phải tự validate tool schema, kiểm tra quyền và lọc dữ liệu tool result trước khi gửi lại cho model.

Nếu bật guardrail trace để điều tra, cần bảo vệ trace như dữ liệu nhạy cảm. Trace có thể chứa giá trị gốc trước khi masking; không ghi trace đầy đủ vào log thông thường hoặc chia sẻ rộng rãi.

## 14. IAM permission cho Java application

Các IAM action chính:

| API | IAM action |
|---|---|
| Converse | bedrock:InvokeModel |
| ConverseStream | bedrock:InvokeModelWithResponseStream |
| InvokeModel | bedrock:InvokeModel |
| InvokeModelWithResponseStream | bedrock:InvokeModelWithResponseStream |
| Dùng inference profile | Có thể cần bedrock:GetInferenceProfile theo tài nguyên và luồng truy cập. |
| Dùng Guardrails | Cấp bedrock:GetGuardrail và bedrock:ApplyGuardrail cùng quyền trên guardrail ARN theo cấu hình và hướng dẫn AWS. |

Cấp quyền theo model ARN hoặc inference profile và các resource liên quan theo quy tắc authorization hiện hành. Nếu dùng cross-Region inference, IAM/SCP cần cho phép các destination Regions của profile.

Không dùng AmazonBedrockFullAccess cho runtime application nếu chỉ cần gọi một vài model. Tách role theo môi trường và workload; giới hạn model, profile và API action trong phạm vi phù hợp.

Khi dùng Guardrails, Prompt management hoặc các tài nguyên Bedrock khác, bổ sung quyền cần thiết cho từng capability thay vì mở rộng quyền vô hạn.

## 15. Inference profile và cross-Region inference

Inference profile cho phép gọi model qua một resource profile. Cross-Region inference có thể định tuyến request từ source Region tới một trong các destination Regions được profile xác định.

Trong Java, modelId có thể là inference profile ID hoặc ARN:

~~~java
String modelId = System.getenv("BEDROCK_INFERENCE_PROFILE_ID");

ConverseStreamRequest request = ConverseStreamRequest.builder()
    .modelId(modelId)
    .messages(userMessage)
    .build();
~~~

Trước khi dùng cross-Region inference, cần:

- Kiểm tra source Region có hỗ trợ profile không.
- Đọc danh sách destination Regions của profile.
- Cho phép các inference actions tại mọi destination Region cần thiết trong IAM/SCP.
- Xem xét data residency và chính sách xử lý dữ liệu.
- Đánh giá latency, throughput và chi phí theo profile.

Destination Regions có thể gồm opt-in Regions. Request có thể được route tới các Region này dù account chưa bật Region đó theo cách thông thường; prompt và output có thể được lưu tại opt-in Region cho mục đích abuse detection. Nếu SCP chặn một destination Region trong profile, request có thể thất bại dù các destination khác vẫn được cho phép.

Không giả định profile ID hoặc destination list cố định mãi mãi. AWS có thể cập nhật profile Global khi thêm Region thương mại mới; profile theo geography có quy tắc ổn định riêng. Hãy kiểm tra model detail page và GetInferenceProfile trước khi thay đổi routing policy.

## 16. Timeout, retry và xử lý lỗi

Streaming có thể kéo dài hơn một request inference ngắn. Timeout cần phản ánh thời gian kết nối, thời gian chờ token đầu tiên, thời gian giữa các chunk và tổng thời gian sinh output.

AWS SDK for Java 2.x có hai lớp timeout chính:

- API call attempt timeout: giới hạn thời gian cho một lần thử.
- API call timeout: giới hạn toàn bộ operation, bao gồm retry và thời gian backoff.

SDK không đặt API call timeout và attempt timeout mặc định. Với streaming, API call timeout phải đủ dài cho toàn bộ generation. Không đặt read timeout ngắn hơn khoảng im lặng hợp lệ giữa các chunk; nếu không, stream dài có thể bị ngắt giữa chừng.

### 16.1. Lỗi thường gặp

| Lỗi | HTTP | Nguyên nhân thường gặp | Hướng xử lý |
|---|---:|---|---|
| AccessDeniedException | 403 | IAM, SCP hoặc model/profile permission thiếu | Kiểm tra action, resource ARN và Region. |
| ResourceNotFoundException | 404 | Model ID/profile không đúng hoặc không tồn tại ở Region | Kiểm tra model catalog và profile. |
| ValidationException | 400 | Payload, parameter hoặc message schema không hợp lệ | Kiểm tra request theo model/API schema. |
| ThrottlingException | 429 | Vượt quota hoặc throughput | Backoff, giảm concurrency, xem quota hoặc capacity. |
| ServiceQuotaExceededException | 400 | Vượt service quota cụ thể | Xem Service Quotas và cấu hình account. |
| ModelTimeoutException | 408 | Model xử lý quá thời gian cho phép | Giảm prompt/output, kiểm tra model latency và request limits. |
| ModelStreamErrorException | 424 | Lỗi xảy ra trong lúc stream | Ghi nhận partial output, điều tra model error và quyết định retry. |
| InternalServerException | 500 | Lỗi nội bộ tạm thời | Retry theo standard strategy và backoff. |
| ServiceUnavailableException | 503 | Bedrock tạm thời thiếu capacity hoặc không khả dụng | Backoff có jitter, cân nhắc inference profile phù hợp. |

### 16.2. Retry không được làm hỏng output

AWS SDK có retry strategy cho các lỗi retryable như throttling, timeout mạng và lỗi dịch vụ tạm thời. Standard retry strategy là lựa chọn mặc định phù hợp cho phần lớn workload.

Với streaming, có một điểm cần chú ý: nếu một phần output đã được gửi tới browser rồi kết nối lỗi, retry toàn bộ request có thể tạo một câu trả lời mới từ đầu. Nếu ứng dụng nối response mới vào response cũ, user sẽ thấy nội dung lặp hoặc sai ngữ cảnh.

Cách xử lý:

- Phân biệt lỗi trước khi nhận chunk và lỗi sau khi đã phát chunk.
- Nếu chưa phát nội dung, retry có thể an toàn theo policy.
- Nếu đã phát partial output, đánh dấu stream incomplete.
- Chỉ restart generation khi ứng dụng có thể reset UI hoặc tạo một attempt mới rõ ràng.
- Không tự động nối output của lần retry vào partial output cũ.
- Dùng request/session ID và attempt ID để ghi nhận trạng thái.
- Với thao tác tool hoặc business action, dùng idempotency và authorization riêng.

Không retry ValidationException hoặc AccessDeniedException một cách mù quáng. Những lỗi này cần sửa request hoặc policy.

## 17. Observability và token usage

Một ứng dụng production nên đo cả hiệu năng model lẫn trải nghiệm người dùng.

| Metric | Ý nghĩa |
|---|---|
| Time to first token | Thời gian từ lúc gửi request đến chunk text đầu tiên. |
| Inter-token/chunk latency | Khoảng thời gian giữa các chunk. |
| Total generation time | Thời gian từ request đến messageStop. |
| Input tokens | Token của prompt và conversation context. |
| Output tokens | Token được model sinh ra. |
| Stop reason | Lý do model dừng generation. |
| Error rate | Tỷ lệ lỗi theo API, model, Region và tenant. |
| Throttle rate | Tỷ lệ request bị giới hạn quota. |
| Cancellation rate | Số stream bị user/client hủy. |
| Partial completion rate | Số response bị ngắt sau khi đã gửi một phần output. |

ConverseStream metadata event có usage và metrics. Dùng dữ liệu này để tính cost estimate, kiểm soát token budget và phân tích latency. Không suy ra output token count bằng cách đếm số delta; một delta có thể chứa nhiều token hoặc chỉ một phần token.

### 17.1. Model invocation logging

Bedrock model invocation logging có thể ghi request, response và metadata vào Amazon S3 hoặc CloudWatch Logs. Logging mặc định tắt; khi bật, dữ liệu được lưu theo cấu hình destination.

Invocation logs có thể chứa prompt, nội dung tài liệu, response và thông tin nhận diện. Trước khi bật:

- Xác định data classification.
- Giới hạn quyền đọc log.
- Chọn retention và encryption.
- Không ghi secrets hoặc credential vào prompt.
- Xem xét masking hoặc redaction trước khi gửi nội dung.
- Kiểm tra yêu cầu pháp lý và chính sách tổ chức.

Không bật logging toàn bộ nội dung chỉ để debug mà không đánh giá tác động dữ liệu.

## 18. Bảo mật prompt và output

Prompt có thể chứa thông tin người dùng, tài liệu nội bộ hoặc dữ liệu nghiệp vụ. Response có thể chứa thông tin không chính xác hoặc nội dung vượt quyền nếu backend thiết kế sai.

Best practices:

- Xác thực người dùng trước khi gọi model.
- Kiểm tra quyền truy cập dữ liệu trước khi đưa dữ liệu vào prompt.
- Không coi nội dung do model sinh là nguồn sự thật.
- Dùng Guardrails theo policy phù hợp.
- Validate JSON hoặc structured output theo schema.
- Không thực thi câu lệnh SQL, shell hoặc tool call trực tiếp từ text output.
- Không để model quyết định quyền truy cập.
- Ghi audit metadata mà không lộ prompt nhạy cảm.
- Áp quota, rate limit và token budget theo user/tenant.
- Có cơ chế timeout và cancel cho request kéo dài.

Streaming làm tăng yêu cầu an toàn vì output có thể được hiển thị trước khi toàn bộ message hoàn tất. Nếu ứng dụng cần moderation trước khi hiển thị, chọn guardrail synchronous mode hoặc buffer nội dung đến khi kiểm tra xong.

## 19. Tình huống thực hành: Java support assistant

Một doanh nghiệp muốn xây dựng trợ lý hỗ trợ kỹ thuật cho nhân viên. Người dùng đặt câu hỏi về AWS; ứng dụng lấy tài liệu nội bộ được phép truy cập, gửi context tới Bedrock và stream câu trả lời tới giao diện chat.

### 19.1. Luồng xử lý

1. Browser gửi câu hỏi và conversation ID tới Java backend.
2. Backend xác thực nhân viên và kiểm tra quyền truy cập tài liệu.
3. Retrieval service tìm các đoạn tài liệu phù hợp.
4. Backend xây dựng system prompt và user message.
5. Backend gọi ConverseStream bằng BedrockRuntimeAsyncClient.
6. Text deltas được gửi tới browser qua SSE.
7. messageStop và metadata được ghi nhận.
8. Assistant message hoàn chỉnh được lưu vào conversation history.
9. Backend ghi token usage, latency và error status.

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

### 19.2. Yêu cầu production

- Mỗi session có owner và authorization scope.
- Retrieved documents phải được lọc theo quyền user trước khi đưa vào prompt.
- Có giới hạn số tài liệu và token context.
- Có timeout cho retrieval và Bedrock request.
- Có cancel khi browser disconnect.
- Không lưu partial output như final assistant answer.
- Có retry policy và handling riêng cho lỗi sau partial chunks.
- Có guardrail và output validation.
- Có token budget và rate limit theo tenant.
- Có log correlation ID để điều tra mà không cần ghi toàn bộ prompt.

## 20. Những lỗi thiết kế thường gặp

1. **Dùng BedrockClient để gọi ConverseStream.** Streaming inference thuộc Bedrock Runtime async client.
2. **Nhầm control plane và runtime endpoint.** GetFoundationModel thuộc control plane; ConverseStream thuộc runtime.
3. **Giả định model nào cũng hỗ trợ streaming.** Phải kiểm tra responseStreamingSupported và API compatibility.
4. **Dùng model ID ở sai Region.** Model/profile availability phụ thuộc Region.
5. **Nhúng access key vào source.** Dùng DefaultCredentialsProvider và IAM role.
6. **Dùng InvokeModel payload của một model cho model khác.** Invoke request body phụ thuộc provider/model.
7. **Giả định mỗi delta là một từ hoặc một token.** Delta là một phần content, không phải token boundary.
8. **Chỉ xử lý text delta.** Stream có thể chứa tool-use hoặc reasoning blocks.
9. **Parse tool JSON khi chưa đủ chunk.** Gom theo contentBlockIndex và chờ contentBlockStop.
10. **Coi messageStop là luôn end_turn.** Kiểm tra stopReason, đặc biệt khi có tool_use hoặc max_tokens.
11. **Lưu partial output như câu trả lời hoàn chỉnh.** Chỉ commit assistant message khi stream hoàn tất theo policy.
12. **Retry và nối output mới vào output cũ.** Có thể tạo nội dung lặp hoặc sai.
13. **Block event-loop trong callback.** Chuyển dữ liệu sang queue hoặc reactive pipeline.
14. **Đặt timeout quá ngắn.** Có thể ngắt stream khi model đang tạo output.
15. **Bỏ qua cross-Region destination.** SCP có thể chặn một destination và làm profile request thất bại.
16. **Bật asynchronous guardrail mà vẫn kỳ vọng chặn nội dung trước khi hiển thị.** Chunk đã gửi không thể thu hồi.
17. **Ghi toàn bộ prompt vào log không kiểm soát.** Invocation logs có thể chứa dữ liệu nhạy cảm.
18. **Cho rằng Bedrock giữ conversation history.** Ứng dụng phải gửi và lưu messages cần thiết.
19. **Không kiểm soát token usage.** Prompt history dài và output lớn làm tăng latency/cost.
20. **Không đóng client.** Có thể gây rò rỉ thread và connection pool.

## 21. Câu hỏi tự kiểm tra

**1. Bedrock Runtime khác Bedrock control plane thế nào?**

Control plane dùng để khám phá/quản lý tài nguyên; Runtime thực hiện model inference.

**2. ConverseStream cần client Java nào?**

BedrockRuntimeAsyncClient của AWS SDK for Java 2.x.

**3. Khi nào nên dùng ConverseStream?**

Khi model hỗ trợ messages và streaming, ứng dụng cần một API hội thoại thống nhất và muốn nhận output từng phần.

**4. Khi nào nên dùng InvokeModelWithResponseStream?**

Khi cần request/response schema riêng của model hoặc capability không được Converse expose.

**5. IAM action nào cho ConverseStream?**

bedrock:InvokeModelWithResponseStream.

**6. Event contentBlockDelta có thể chứa gì?**

Text, reasoning content hoặc một phần tool-use input.

**7. Vì sao phải dùng contentBlockIndex?**

Để ghép các event thuộc cùng content block khi một message có nhiều block.

**8. messageStop cung cấp thông tin gì?**

Nó đánh dấu kết thúc message và mang stopReason.

**9. Bedrock có lưu conversation history tự động không?**

Không. Ứng dụng quản lý và gửi các messages cần thiết cho mỗi lượt.

**10. Vì sao không nên thực thi tool khi mới nhận một phần JSON?**

Input chưa hoàn chỉnh; cần chờ block kết thúc, parse, validate và authorize trước khi thực thi.

**11. API call timeout khác attempt timeout thế nào?**

Attempt timeout giới hạn một lần gọi; API call timeout giới hạn toàn bộ operation gồm retry và backoff.

**12. Vì sao retry sau partial output cần xử lý riêng?**

Request mới có thể sinh câu trả lời khác từ đầu; nối vào output cũ có thể tạo nội dung lặp hoặc sai.

**13. Cross-Region inference ảnh hưởng IAM/SCP thế nào?**

Các destination Regions trong profile phải được cho phép; chặn một destination có thể làm request thất bại.

**14. Guardrail synchronous và asynchronous khác nhau thế nào?**

Synchronous kiểm tra chunk trước khi gửi, tăng latency; asynchronous gửi nhanh hơn nhưng có thể để lọt chunk chưa được kiểm tra xong.

**15. Vì sao invocation logging cần kiểm soát?**

Log có thể chứa prompt, response và dữ liệu nhạy cảm; cần encryption, retention và quyền truy cập phù hợp.

## 22. Checklist production

- [ ] SDK for Java 2.x và bedrockruntime dependency được quản lý bằng BOM.
- [ ] Client dùng DefaultCredentialsProvider hoặc credential provider phù hợp.
- [ ] Region, model ID và streaming support đã được xác minh.
- [ ] Model access/EULA/first-time-use requirements đã hoàn tất.
- [ ] Converse hay Invoke API được chọn theo capability của model.
- [ ] IAM role chỉ có inference actions và resource cần thiết.
- [ ] Cross-Region profile destination Regions đã được rà soát với SCP/IAM.
- [ ] Async client được tái sử dụng và đóng đúng vòng đời.
- [ ] Callback không block event-loop.
- [ ] Chunk được ghép theo contentBlockIndex và content type.
- [ ] Tool-use JSON chỉ được xử lý sau khi block hoàn tất.
- [ ] stopReason và usage metadata được ghi nhận.
- [ ] Conversation history được quản lý ở application layer.
- [ ] API call timeout và attempt timeout phù hợp với thời gian generation.
- [ ] Retry không làm nối trùng partial output.
- [ ] Client disconnect/cancellation có xử lý.
- [ ] Guardrail streaming mode phù hợp yêu cầu moderation.
- [ ] Prompt/output không bị ghi log ngoài policy.
- [ ] Token budget, concurrency và rate limit được cấu hình.
- [ ] Có dashboard time-to-first-token, total latency, token usage và error rate.
- [ ] Có runbook cho AccessDenied, throttling, timeout và stream failure.
- [ ] Có kiểm thử multi-turn, tool use, long response và partial stream failure.

## Tài liệu tham khảo

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

