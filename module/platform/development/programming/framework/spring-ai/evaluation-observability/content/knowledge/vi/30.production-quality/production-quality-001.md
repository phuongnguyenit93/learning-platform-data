# Chất lượng khi vận hành: Thu thập phản hồi người dùng cùng ngữ cảnh cần thiết

## 1. Phản hồi chỉ có giá trị khi biết nó nói về lượt trả lời nào

Một nút 👍 hoặc 👎 cho biết người dùng có phản ứng với câu trả lời, nhưng tự nó chưa giải thích được điều gì đã xảy ra. Người dùng có thể chê câu trả lời vì sai sự thật, thiếu một bước, không liên quan, dùng sai công cụ, trình bày khó hiểu hoặc không phù hợp với mục đích của họ. Cùng một câu trả lời còn có thể được tạo bởi prompt, model, retriever và tập tài liệu khác nhau ở từng phiên bản.

Nếu chỉ lưu rating, nhóm phát triển khó tái hiện lỗi. Nếu lưu toàn bộ hội thoại, prompt, tài liệu RAG và kết quả tool một cách mặc định, hệ thống có thể thu thập quá nhiều dữ liệu nhạy cảm. Một hệ thống production cần thu thập **phản hồi gắn với đúng lượt tương tác và một bản chụp ngữ cảnh đủ để giải thích kết quả**, có kiểm soát quyền truy cập và thời hạn lưu giữ.

Bài học thuộc chương **Chất lượng khi vận hành** của module **SPRING_AI_EVALUATION_OBSERVABILITY**. Module đánh giá ứng dụng Spring AI bằng dataset, tiêu chí relevance, fact checking và kiểm thử RAG/tool calling; đồng thời đo metrics, traces, chi phí và độ trễ để phát hiện nguyên nhân suy giảm qua các phiên bản prompt, model và pipeline.

Sau bài học, bạn có thể:

- Thiết kế feedback UI cho một câu trả lời cụ thể, không mơ hồ theo cả cuộc hội thoại.
- Phân biệt phản hồi tường minh, tín hiệu hành vi và kết quả nghiệp vụ.
- Xác định context tối thiểu cần lưu cho mỗi assistant turn.
- Liên kết feedback với trace, model, prompt, retriever, tài liệu và tool execution.
- Thiết kế API nhận feedback có xác thực, kiểm tra quyền sở hữu và idempotency.
- Bảo vệ prompt, response, RAG context, tool arguments và thông tin cá nhân.
- Đưa feedback đã được xem xét vào evaluation dataset có provenance.
- Phân tích xu hướng chất lượng mà không nhầm feedback rate với accuracy.

## 2. Ba loại tín hiệu chất lượng cần phân biệt

### 2.1. Phản hồi tường minh

Người dùng chủ động đánh giá một câu trả lời, ví dụ:

- 👍 Câu trả lời hữu ích.
- 👎 Câu trả lời chưa hữu ích.
- Chọn lý do: sai sự thật, thiếu thông tin, không liên quan, lỗi công cụ hoặc định dạng không phù hợp.
- Gửi nhận xét hoặc nội dung sửa lại nếu muốn.

Đây là tín hiệu trực tiếp nhất về trải nghiệm người dùng, nhưng vẫn là **ý kiến của người đánh giá**, chưa tự động trở thành nhãn ground truth. Một câu trả lời đúng theo tài liệu có thể không phù hợp với nhu cầu riêng; ngược lại, người dùng có thể đánh giá tích cực một câu trả lời tự tin nhưng sai.

### 2.2. Tín hiệu hành vi

Ứng dụng có thể quan sát người dùng:

- Yêu cầu tạo lại câu trả lời.
- Đặt câu hỏi sửa lỗi hoặc yêu cầu làm rõ.
- Sao chép, tải xuống hoặc chia sẻ câu trả lời.
- Chỉnh sửa nội dung được sinh.
- Thoát khỏi luồng hoặc chuyển sang nhân viên hỗ trợ.

Các hành vi này là **proxy**, không phải rating. Người dùng có thể sao chép để kiểm tra, rời đi vì bận, hoặc tạo lại câu trả lời chỉ vì muốn cách diễn đạt khác. Không tự động gán nhãn “đúng” cho hành động copy hay “sai” cho hành động regenerate.

### 2.3. Kết quả nghiệp vụ

Một số ứng dụng có thể xác định công việc đã hoàn tất, đơn hàng được xử lý, yêu cầu được giải quyết hay ticket phải mở lại. Đây là tín hiệu có ích để đánh giá kết quả cuối, nhưng cần nối với đúng AI interaction và hiểu các yếu tố ngoài mô hình có thể ảnh hưởng.

| Loại tín hiệu | Ví dụ | Dùng để làm gì | Giới hạn |
| --- | --- | --- | --- |
| Tường minh | 👍/👎, lý do, nhận xét | Phát hiện vấn đề theo cảm nhận người dùng | Có thiên lệch lựa chọn và khác biệt kỳ vọng |
| Hành vi | Regenerate, sửa câu hỏi, escalation | Phát hiện friction và luồng cần điều tra | Không chứng minh đúng/sai |
| Nghiệp vụ | Task completed, ticket reopened | Đo kết quả sau khi dùng AI | Có thể bị ảnh hưởng bởi hệ thống và con người khác |

Giữ các loại tín hiệu thành những trường riêng. Không gộp chúng thành một điểm “user satisfaction” nếu chưa định nghĩa cách tính và độ tin cậy.

## 3. Gắn feedback với đúng assistant turn

Feedback thường đến sau khi người dùng đọc câu trả lời. Trong khoảng thời gian đó, ứng dụng có thể đã xử lý thêm nhiều lượt hội thoại. Vì vậy cần có định danh riêng cho từng tương tác:

- **interactionId**: định danh một lần xử lý AI ở tầng ứng dụng.
- **assistantTurnId**: định danh chính xác câu trả lời mà người dùng đang đánh giá.
- **conversationId**: định danh cuộc hội thoại hoặc phiên memory.
- **traceId**: định danh trace để điều tra các spans liên quan.
- **feedbackEventId**: định danh một lần gửi feedback, dùng cho idempotency và audit.

Không dùng riêng conversationId để gắn feedback. Một conversation có thể có hàng chục câu trả lời, nhiều model calls, tool calls và lần retry. Người dùng phải có thể đánh giá câu trả lời cụ thể đang hiển thị.

~~~mermaid
sequenceDiagram
    participant UI as Chat UI
    participant API as Application API
    participant AI as Spring AI
    participant DB as Interaction store
    participant FB as Feedback API
    participant Q as Review / evaluation queue

    UI->>API: Gửi câu hỏi
    API->>API: Tạo interactionId và assistantTurnId
    API->>AI: Gọi ChatClient / RAG / tools
    AI-->>API: Response + observations
    API->>DB: Lưu interaction snapshot
    API-->>UI: Trả answer + opaque IDs
    UI->>FB: Gửi rating cho assistantTurnId
    FB->>DB: Xác thực quyền và tải snapshot
    FB->>DB: Lưu feedback event
    FB->>Q: Phát event cần triage
~~~

Tạo các ID ở server trước hoặc trong lúc bắt đầu xử lý. Trả opaque IDs cần thiết cho UI cùng câu trả lời. Client không cần biết toàn bộ trace metadata.

## 4. Bản chụp ngữ cảnh cần thiết là gì?

Ngữ cảnh phục vụ điều tra nên được ghi nhận **tại thời điểm tạo câu trả lời**. Nếu chờ tới khi người dùng gửi feedback rồi mới truy vấn lại vector store hoặc model configuration, dữ liệu có thể đã thay đổi. Khi đó nhóm phát triển sẽ không tái hiện được đúng điều kiện ban đầu.

Một interaction snapshot có thể gồm các nhóm sau:

| Nhóm | Trường gợi ý | Mục đích |
| --- | --- | --- |
| Định danh | interactionId, assistantTurnId, conversationId, tenantRef | Gắn feedback đúng lượt và đúng phạm vi dữ liệu |
| Tracing | traceId, rootSpanId hoặc trace reference | Mở trace để xem các bước thực thi |
| Model | provider, requestedModel, reportedModel, modelRevision | Xác định model thực sự đã chạy |
| Prompt | promptTemplateId, promptVersion, systemPolicyVersion | Xác định cấu hình prompt |
| Generation | temperature, topP, maxTokens, responseMode | So sánh điều kiện sinh nội dung |
| RAG | retrieverVersion, indexVersion, topK, filters, rerankerVersion | Tái hiện quá trình truy xuất |
| Nguồn truy xuất | documentId, documentVersion, chunkId, rank, score | Xác định evidence đã đưa vào context |
| Tools | toolName, toolVersion, executionStatus, duration | Điều tra lỗi chọn hoặc chạy công cụ |
| Evaluation | evaluatorVersion, relevanceScore, factCheckResult, safetyDecision | Đối chiếu phản hồi với kết quả tự động |
| Runtime | latency, TTFT, tokenUsage, usageStatus, estimatedCost | Điều tra độ trễ và chi phí |
| Thời gian | startedAt, completedAt, snapshotCreatedAt | Xác định thứ tự sự kiện và thời điểm cấu hình |

Không phải bài toán nào cũng cần mọi trường. Hãy chọn các trường đủ để trả lời những câu hỏi điều tra mà sản phẩm thực sự cần.

### 4.1. Lưu nguồn RAG theo định danh và phiên bản

Khi người dùng nói “câu trả lời không có căn cứ”, nhóm phát triển cần biết tài liệu nào đã được truy xuất:

- Document ID và version.
- Chunk ID hoặc content hash.
- Rank và retrieval score.
- Retriever/index version.
- Filter hoặc tenant scope đã áp dụng.
- Reranker version và score nếu có.

Mặc định ưu tiên lưu định danh, phiên bản, score và tham chiếu tới kho tài liệu được kiểm soát. Không sao chép toàn bộ nội dung tài liệu hoặc đoạn văn chứa thông tin riêng tư vào feedback event. Nếu cần lưu evidence text để tái hiện, hãy áp dụng quyền truy cập, mã hóa, redaction và retention riêng.

### 4.2. Lưu tool execution dưới dạng summary

Để điều tra agent, thường cần biết:

- Tool nào được chọn.
- Tool version hoặc schema version.
- Thời điểm bắt đầu/kết thúc và trạng thái thành công/thất bại.
- Error category đã chuẩn hóa.
- Kết quả có được sử dụng trong câu trả lời cuối hay không.

Không mặc định lưu raw arguments, access token, query chứa dữ liệu cá nhân hoặc toàn bộ tool result. Nếu lỗi phụ thuộc một giá trị đầu vào cụ thể, lưu một bản đã redaction hoặc reference tới evidence store có kiểm soát.

### 4.3. Phân biệt requested model và reported model

Ứng dụng có thể yêu cầu một alias như tên deployment, trong khi server trả tên model hoặc revision khác. Lưu cả requested model và reported model nếu adapter cung cấp. Nếu runtime có digest, deployment revision hoặc quantization, lưu chúng ở context snapshot.

Không giả định prompt version hoặc model name là đủ để tái hiện kết quả. Retriever, corpus, tool schema, policy và runtime cũng có thể thay đổi.

## 5. Liên kết với Spring AI observations và trace

Spring AI tạo observations cho các thành phần như ChatClient, Advisor, ChatModel, EmbeddingModel và VectorStore. Observation của ChatClient ghi nhận call/stream, đo thời gian và truyền tracing context. Các low-cardinality keys phù hợp cho metrics và traces; high-cardinality keys chỉ được thêm vào traces.

Ở tầng ChatClient, các thuộc tính hữu ích gồm:

- **spring.ai.chat.client.stream**: call hay stream.
- **spring.ai.chat.client.conversation.id**: conversation ID khi sử dụng chat memory.
- **spring.ai.chat.client.advisors**: danh sách advisors.
- **spring.ai.chat.client.tool.names**: tên tools được truyền cho ChatClient.

Những thuộc tính này giúp xác định execution path. Tuy nhiên, conversation ID không thay thế interactionId hoặc assistantTurnId của ứng dụng. Feedback cần trỏ đến đúng câu trả lời, còn trace cho biết những spans nào đã tham gia tạo ra câu trả lời đó.

### 5.1. Tạo liên kết trace ở server

Một cách làm là đọc trace ID từ Micrometer Tracing khi interaction đang được xử lý, rồi lưu nó vào interaction snapshot:

~~~java
import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;

public final class TraceReferenceFactory {

    private final Tracer tracer;

    public TraceReferenceFactory(Tracer tracer) {
        this.tracer = tracer;
    }

    public String currentTraceId() {
        Span span = tracer.currentSpan();
        return span != null ? span.context().traceId() : null;
    }
}
~~~

Đây là ví dụ đọc trace đang hoạt động; cần gọi trong đúng execution context. Với reactive pipeline hoặc executor chuyển thread, cấu hình context propagation để trace hiện tại được khôi phục ở nơi cần đọc. Không tự tạo một traceId ngẫu nhiên rồi coi nó là trace ID do tracing system cấp.

Lưu trace ID trong interaction store hoặc feedback record để tra cứu khi cần. Không đưa traceId, interactionId hay user ID thành metric labels vì mỗi giá trị thường có cardinality cao.

### 5.2. Không đưa nội dung prompt và completion vào trace chỉ để thu feedback

Spring AI không export prompt/completion mặc định vì dữ liệu này có thể lớn và nhạy cảm. Các thuộc tính cấu hình logging prompt/completion được tắt mặc định. Bật chúng làm tăng rủi ro lộ thông tin trong log hoặc trace backend.

Nếu cần xem nội dung để xử lý một feedback cụ thể, hãy dùng evidence store có quyền truy cập hạn chế và audit. Trace nên chứa metadata cần thiết và liên kết tới evidence, thay vì biến trace backend thành nơi lưu toàn bộ hội thoại.

### 5.3. Truyền correlation qua các service

Nếu feedback API, AI service và worker xử lý event nằm ở các service khác nhau, W3C Trace Context có thể nối trace qua HTTP. Micrometer Tracing cũng hỗ trợ baggage; W3C propagation có thể tự truyền baggage qua các transport được instrument.

Chỉ truyền giá trị correlation cần thiết, không đưa email, số điện thoại, nội dung prompt hoặc định danh nhạy cảm vào baggage. Baggage có thể trở thành HTTP headers ở downstream services; hãy coi nó là dữ liệu được chia sẻ giữa các service và kiểm soát rõ remote fields.

## 6. Thiết kế giao diện phản hồi

Một giao diện feedback tốt nên xuất hiện gần câu trả lời mà người dùng vừa đọc. Không nên yêu cầu người dùng viết một báo cáo dài cho mọi lần đánh giá.

Một luồng cơ bản:

1. Người dùng chọn 👍 hoặc 👎.
2. Nếu chọn 👎, giao diện hiển thị danh sách lý do ngắn.
3. Người dùng có thể nhập nhận xét hoặc câu trả lời mong đợi.
4. Giao diện gửi feedback cho đúng assistantTurnId.
5. Hệ thống xác nhận đã nhận và cho phép người dùng sửa feedback theo chính sách sản phẩm.

Ví dụ taxonomy:

| Reason code | Ý nghĩa | Nhóm xử lý gợi ý |
| --- | --- | --- |
| IRRELEVANT | Không trả lời đúng câu hỏi | Prompt, routing hoặc retrieval |
| FACTUALLY_INCORRECT | Có thông tin sai | Grounding, source quality, model |
| UNSUPPORTED_CLAIM | Khẳng định không có evidence | RAG context, citation, fact checking |
| INCOMPLETE | Thiếu bước hoặc chi tiết cần thiết | Prompt, context hoặc response budget |
| OUTDATED | Thông tin đã cũ | Corpus freshness, indexing |
| MISUNDERSTOOD_INTENT | Hiểu sai yêu cầu | Conversation context, query rewrite |
| TOOL_FAILURE | Chọn sai tool hoặc thực thi lỗi | Tool schema, permissions, retry |
| UNSAFE_OR_POLICY | Nội dung không an toàn hoặc vi phạm policy | Guardrail, policy, review |
| FORMAT_OR_LANGUAGE | Sai định dạng hoặc ngôn ngữ | Prompt, output validation |
| OTHER | Lý do khác | Triage thủ công |

Giữ taxonomy nhỏ và có định nghĩa rõ. Nếu danh sách quá dài, người dùng khó chọn và dữ liệu trở nên thiếu nhất quán. Có thể cho phép OTHER kèm comment.

### 6.1. Hỏi thêm điều người dùng cần, không hỏi lại toàn bộ lịch sử

Một số câu hỏi có ích:

- “Phần nào chưa chính xác?”
- “Bạn mong đợi kết quả nào?”
- “Câu trả lời thiếu nguồn hoặc bước nào?”
- “Tool nào đã không hoạt động như mong đợi?”

Chỉ hỏi thêm khi cần. Không bắt buộc người dùng gửi lại prompt hoặc dán toàn bộ hội thoại nếu ứng dụng đã có interaction reference.

## 7. Thiết kế feedback event và API

Feedback event nên là bản ghi riêng, có thể append-only để giữ lịch sử thay đổi. Interaction snapshot được lưu riêng; feedback event tham chiếu đến snapshot đó.

Ví dụ payload từ UI:

~~~json
{
  "feedbackEventId": "b87b1f7e-75de-4db7-a8cf-8a12a3c8a041",
  "interactionId": "a42a7c50-5b65-4f9c-b41a-2e3d1b8b22f4",
  "assistantTurnId": "b1d82a7a-4d7e-4e2f-99b2-0a24b3f88ac7",
  "rating": "NEGATIVE",
  "reasonCode": "UNSUPPORTED_CLAIM",
  "comment": "Kết luận chưa có nguồn hỗ trợ.",
  "correction": null
}
~~~

Đây là ví dụ minh họa. Client chỉ gửi các trường feedback và opaque identifiers mà UI đã nhận từ server. Server tự gắn tenant, actor, trace, model và version từ dữ liệu đã lưu; không tin metadata do client tự khai báo.

### 7.1. DTO Java

~~~java
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.util.UUID;

public enum FeedbackRating {
    POSITIVE,
    NEGATIVE
}

public enum FeedbackReason {
    IRRELEVANT,
    FACTUALLY_INCORRECT,
    UNSUPPORTED_CLAIM,
    INCOMPLETE,
    OUTDATED,
    MISUNDERSTOOD_INTENT,
    TOOL_FAILURE,
    UNSAFE_OR_POLICY,
    FORMAT_OR_LANGUAGE,
    OTHER
}

public record FeedbackRequest(
        @NotNull UUID feedbackEventId,
        @NotNull UUID interactionId,
        @NotNull UUID assistantTurnId,
        @NotNull FeedbackRating rating,
        FeedbackReason reasonCode,
        @Size(max = 1200) String comment,
        @Size(max = 2400) String correction
) {}
~~~

Trong sản phẩm thực tế, đặt mỗi public type ở file Java riêng. Với feedback âm, có thể yêu cầu reasonCode theo validation rule của ứng dụng. Giới hạn độ dài comment/correction giúp giảm payload quá lớn; vẫn cần redaction và chính sách dữ liệu.

### 7.2. Controller minh họa

~~~java
@RestController
@RequestMapping("/api/feedback")
public class FeedbackController {

    private final FeedbackService feedbackService;

    public FeedbackController(FeedbackService feedbackService) {
        this.feedbackService = feedbackService;
    }

    @PostMapping
    public ResponseEntity<Void> submit(
            @Valid @RequestBody FeedbackRequest request,
            @AuthenticationPrincipal AppPrincipal actor) {

        feedbackService.submit(actor, request);
        return ResponseEntity.accepted().build();
    }
}
~~~

AppPrincipal là principal do ứng dụng định nghĩa. Controller phải lấy actor và tenant từ authentication context, không lấy từ JSON do browser gửi. Endpoint cần authentication phù hợp, CSRF protection nếu dùng cookie session, rate limiting và kiểm tra quyền sở hữu interaction.

### 7.3. Service phải resolve context ở server

~~~java
@Transactional
public void submit(AppPrincipal actor, FeedbackRequest request) {

    InteractionSnapshot snapshot = interactionRepository
            .findByTenantAndInteractionAndTurn(
                    actor.tenantId(),
                    request.interactionId(),
                    request.assistantTurnId())
            .orElseThrow(InteractionNotFoundException::new);

    if (!snapshot.isFeedbackAllowedBy(actor)) {
        throw new AccessDeniedException("Feedback is not allowed");
    }

    FeedbackEvent event = FeedbackEvent.from(
            request,
            actor.subjectReference(),
            snapshot);

    feedbackRepository.insertIfAbsent(event);
    outboxRepository.enqueueFeedbackReceived(event.id());
}
~~~

Đây là service skeleton; tên repository và principal là kiểu ứng dụng tự định nghĩa. Điểm quan trọng:

- Query snapshot theo tenant và đúng assistant turn.
- Kiểm tra actor có quyền xem/đánh giá interaction.
- Lấy trace/model/prompt/RAG/tool metadata từ snapshot server-side.
- Không chấp nhận traceId hoặc userId do client tự gửi.
- Lưu feedback và outbox event trong cùng transaction để tránh mất event khi publish lỗi.

### 7.4. Idempotency và thay đổi feedback

Người dùng có thể bấm hai lần hoặc client gửi lại request do timeout. Dùng feedbackEventId làm idempotency key và đặt unique constraint trong storage. Nếu sản phẩm cho phép người dùng đổi rating, ghi một event mới tham chiếu event trước hoặc đánh dấu event mới là superseding; không âm thầm ghi đè lịch sử.

Phản hồi API chỉ nên xác nhận đã nhận event. Việc triage, adjudication hoặc cập nhật evaluation dataset có thể chạy bất đồng bộ.

## 8. Interaction snapshot mẫu

Một snapshot nội bộ có thể được biểu diễn như sau:

~~~json
{
  "interactionId": "a42a7c50-5b65-4f9c-b41a-2e3d1b8b22f4",
  "assistantTurnId": "b1d82a7a-4d7e-4e2f-99b2-0a24b3f88ac7",
  "conversationRef": "conv_opaque_92",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "provider": "openai",
  "requestedModel": "model-alias",
  "reportedModel": "model-revision",
  "promptVersion": "support-answer-v12",
  "retrieverVersion": "knowledge-search-v5",
  "indexVersion": "kb-2026-11-20",
  "sources": [
    {
      "documentId": "policy-104",
      "documentVersion": "7",
      "chunkId": "policy-104-03",
      "rank": 1,
      "score": 0.91
    }
  ],
  "tools": [
    {
      "name": "lookupOrder",
      "version": "3",
      "status": "SUCCESS",
      "durationMs": 84
    }
  ],
  "usage": {
    "inputTokens": 620,
    "outputTokens": 210,
    "status": "REPORTED"
  },
  "latencyMs": 1420,
  "evaluator": {
    "version": "grounding-v4",
    "relevance": 0.88,
    "factCheck": "PASS"
  }
}
~~~

Các ID và số liệu trong ví dụ đều là giả lập. Snapshot không chứa raw prompt, full completion, document text hay tool arguments. TraceId và các định danh được lưu trong backend có kiểm soát; chúng không phải metric labels.

### 8.1. Lưu snapshot bất biến

Không cập nhật snapshot cũ khi prompt, model hoặc corpus thay đổi. Một feedback event cần trỏ đến đúng trạng thái lúc câu trả lời được tạo. Nếu cần bổ sung metadata về sau, tạo enrichment record có timestamp và provenance riêng.

Với dữ liệu không thể lưu trực tiếp, có thể lưu reference tới encrypted evidence store. Reference phải có quyền truy cập và retention giống dữ liệu gốc; chỉ có URL nội bộ không tự tạo ra bảo vệ.

## 9. Bảo vệ dữ liệu người dùng và ngữ cảnh AI

Feedback thường chứa nội dung người dùng tự nhập. Họ có thể vô tình gửi tên, email, số tài khoản, nội dung hợp đồng hoặc dữ liệu khách hàng. Context snapshot còn có thể chứa prompt, tài liệu RAG, lịch sử hội thoại và tool outputs.

Áp dụng nguyên tắc data minimization:

- Chỉ lưu các trường cần cho mục đích điều tra đã xác định.
- Ưu tiên IDs, hashes, versions, scores và status thay cho raw content.
- Redact PII, credentials, API keys và secrets trước khi lưu.
- Mã hóa dữ liệu khi truyền và khi lưu.
- Phân quyền riêng cho feedback, interaction snapshots và raw evidence.
- Audit việc xem hoặc tải nội dung nhạy cảm.
- Đặt retention period theo loại dữ liệu và mục đích.
- Hỗ trợ xóa hoặc ẩn danh dữ liệu theo chính sách sản phẩm và nghĩa vụ áp dụng.
- Không dùng feedback chứa dữ liệu riêng tư để huấn luyện hoặc chia sẻ ra ngoài nếu chưa có căn cứ và quyền phù hợp.

### 9.1. Không biến trace backend thành kho hội thoại

Spring AI không export prompt/completion mặc định vì chúng có thể chứa dữ liệu nhạy cảm. Giữ mặc định này giúp trace tập trung vào metadata vận hành. Nếu cần raw content để xử lý một sự cố, dùng luồng lưu trữ riêng với quyền truy cập hạn chế, redaction, audit và thời hạn lưu.

### 9.2. Không truyền dữ liệu nhạy cảm qua baggage

Baggage có thể được truyền thành HTTP headers tới downstream services. Không đưa prompt, email, số điện thoại, user ID trực tiếp hoặc thông tin xác thực vào baggage. Nếu cần correlation xuyên service, dùng opaque correlation reference có phạm vi và thời hạn hợp lý.

### 9.3. Tenant isolation

Với ứng dụng đa tenant, mọi truy vấn interaction snapshot và feedback phải bao gồm tenant scope từ authentication context. Không cho phép client gửi một interactionId của tenant khác rồi truy xuất feedback hoặc trace. Kiểm tra quyền ở cả API, service và lớp truy cập dữ liệu.

## 10. Từ feedback tới evaluation dataset

Không đưa trực tiếp mọi feedback vào benchmark mà không qua xem xét. Một feedback event có thể không rõ ràng, thiên về sở thích cá nhân hoặc thiếu evidence.

~~~mermaid
flowchart TD
    F["Feedback event"] --> T["Triage and deduplicate"]
    T --> R{"Can be interpreted?"}
    R -->|No| Q["Request clarification / close"]
    R -->|Yes| H["Human review / evidence check"]
    H --> D{"Confirmed issue?"}
    D -->|No| P["Preference / false positive / unresolved"]
    D -->|Yes| C["Create evaluation case"]
    C --> V["Version dataset and rubric"]
    V --> E["Replay against candidate versions"]
    E --> A["Compare quality, latency and cost"]
    A --> M["Release decision / monitor"]
~~~

### 10.1. Các bước xử lý

1. **Triage:** kiểm tra duplicate, spam, feedback thiếu mục tiêu hoặc không thuộc sản phẩm.
2. **Phân loại:** map reason code vào nhóm prompt, retrieval, model, tool, policy hoặc UX.
3. **Xem evidence:** mở interaction snapshot và trace; kiểm tra tài liệu, tool status và output đã redacted.
4. **Adjudication:** xác định lỗi thực, sở thích người dùng, false positive hoặc thiếu thông tin.
5. **Tạo evaluation case:** lưu input cần thiết, expected behavior, source of truth và rubric.
6. **Versioning:** ghi dataset version, reviewer, thời gian, provenance và lý do thay đổi.
7. **Replay:** chạy case trên prompt/model/retriever candidate.
8. **So sánh:** relevance, factuality, safety, latency, token usage và chi phí.
9. **Quyết định:** sửa, thử nghiệm, rollout hoặc theo dõi thêm.

### 10.2. Không làm rò rỉ test set

Nếu feedback được dùng để cải tiến prompt hoặc model, đừng đồng thời để cùng case nằm trong tập test dùng báo cáo chất lượng cuối cùng mà không ghi nhận việc tái sử dụng. Tách development cases, validation cases và held-out test cases; lưu provenance để biết case nào đã được dùng cho prompt tuning hoặc rule changes.

### 10.3. Giữ nhãn người dùng và nhãn evaluator riêng

Ví dụ một user đánh giá 👎 nhưng relevance evaluator chấm 0.95. Có thể câu trả lời liên quan nhưng không giải quyết yêu cầu; hoặc rubric evaluator chưa bao quát kỳ vọng của người dùng. Giữ riêng:

- userRating và userReason.
- reviewerVerdict.
- evaluatorScore và evaluatorVersion.
- groundTruthStatus và evidence references.

Sau đó mới phân tích sự khác biệt. Không ghi đè rating người dùng bằng điểm LLM-as-judge.

## 11. Metrics để theo dõi feedback

Metrics cần đo cả **mức độ gửi feedback** và **tỷ lệ vấn đề**, nhưng phải giữ đúng mẫu số.

Một số metric ứng dụng có thể định nghĩa:

| Metric | Ý nghĩa |
| --- | --- |
| ai_feedback_submissions_total | Tổng feedback events đã nhận |
| ai_feedback_exposed_interactions_total | Số lượt trả lời có hiển thị cơ chế feedback |
| ai_feedback_reason_total | Số feedback theo reason code |
| ai_feedback_triage_total | Số feedback đã được phân loại |
| ai_feedback_confirmed_defects_total | Số defect được reviewer xác nhận |
| ai_feedback_resolution_seconds | Thời gian từ nhận feedback tới khi xử lý |
| ai_feedback_coverage_ratio | Tỷ lệ interaction có feedback trên tổng interaction đủ điều kiện |

Đây là tên metric do ứng dụng tự định nghĩa, không phải metric mặc định Spring AI.

### 11.1. Tỷ lệ feedback âm trong số feedback đã gửi

~~~promql
sum(rate(ai_feedback_submissions_total{rating="NEGATIVE"}[1h]))
/
sum(rate(ai_feedback_submissions_total[1h]))
~~~

Query này đo tỷ lệ âm trong **những feedback đã gửi**, không phải tỷ lệ câu trả lời sai trên toàn bộ traffic.

### 11.2. Feedback coverage trên số interaction có hiển thị nút đánh giá

~~~promql
sum(rate(ai_feedback_submissions_total[1h]))
/
sum(rate(ai_feedback_exposed_interactions_total[1h]))
~~~

Coverage thấp có thể do người dùng không muốn đánh giá, UI khó thấy hoặc thời điểm hỏi chưa phù hợp. Không thể kết luận chất lượng tốt khi feedback rate thấp.

### 11.3. Chọn label có cardinality thấp

Có thể phân nhóm metrics theo provider, model family, prompt family, channel hoặc reason code với số lượng hữu hạn. Không dùng các trường sau làm metric labels:

- traceId, interactionId, assistantTurnId hoặc feedbackEventId.
- user ID, email, tenant ID nếu có số lượng lớn.
- Raw prompt, response, document ID hoặc tool arguments.
- URL, session token hoặc chuỗi lỗi tùy biến không giới hạn.

Các định danh chi tiết nên nằm trong event store hoặc trace backend để truy vấn theo từng case. Metrics chỉ phục vụ tổng hợp và cảnh báo.

## 12. Dashboard và cảnh báo cần đọc cùng nhau

Một dashboard production có thể chia thành bốn vùng:

| Vùng | Chỉ số | Câu hỏi |
| --- | --- | --- |
| Feedback volume | Submissions, exposure, coverage | Có đủ phản hồi để phân tích không? |
| Feedback quality | Negative rate, reason distribution, confirmed defects | Vấn đề nào đang tăng? |
| Operational context | Latency, errors, token usage, tool failures | Hệ thống có thay đổi vận hành không? |
| Evaluation | Relevance, fact-check, safety, dataset pass rate | Chất lượng có được xác nhận bằng test không? |

Khi tỷ lệ feedback âm tăng, kiểm tra đồng thời:

- Model hoặc model revision mới có vừa được rollout?
- Prompt template hoặc policy có thay đổi?
- Retrieval index, chunking, topK hoặc reranker có đổi?
- Tool schema, permission hoặc downstream API có lỗi?
- Latency/timeout có khiến câu trả lời bị thiếu?
- Nhóm người dùng hoặc loại tác vụ có thay đổi?

Đặt cảnh báo dựa trên cả volume và tỷ lệ. Một vài feedback âm trong traffic rất thấp có thể làm tỷ lệ dao động mạnh. Theo dõi cửa sổ thời gian, sample size và baseline trước khi kết luận regression.

## 13. Sampling và độ thiên lệch của feedback

Người dùng chủ động gửi feedback thường có trải nghiệm rất tốt hoặc rất xấu; những trường hợp bình thường ít được đánh giá hơn. Đây là selection bias.

Các nguyên tắc hữu ích:

- Không sample bỏ các feedback event đã được gửi tường minh.
- Ghi số interaction đủ điều kiện và số interaction có feedback để biết coverage.
- Nếu sample interaction snapshot tốn kém, vẫn giữ một metadata envelope nhẹ cho mọi interaction để feedback có thể liên kết được.
- Chọn một mẫu ngẫu nhiên các interaction để review độc lập nhằm ước lượng chất lượng ngoài nhóm tự nguyện gửi feedback.
- Phân tích theo cohort, tác vụ, channel và phiên bản thay vì chỉ nhìn toàn bộ traffic.
- Không diễn giải một tỷ lệ feedback âm như accuracy hoặc error rate nếu chưa có adjudication.

Nếu UI yêu cầu đánh giá quá thường xuyên, người dùng có thể mệt mỏi và chọn ngẫu nhiên. Hãy chọn thời điểm có ý nghĩa, cho phép bỏ qua và hạn chế lặp lại lời nhắc.

## 14. Xử lý feedback trễ và nhiều lần chỉnh sửa

Feedback có thể được gửi ngay sau câu trả lời hoặc nhiều ngày sau. Trong thời gian đó, model, prompt, corpus và tool đã thay đổi. Vì vậy:

- Giữ timestamp của interaction và timestamp của feedback riêng.
- Feedback luôn trỏ đến snapshot ban đầu.
- Nếu người dùng sửa rating, lưu lịch sử thay đổi hoặc event superseding.
- Không cập nhật model/prompt version trong snapshot cũ.
- Nếu interaction đã hết retention, trả thông báo phù hợp và không tái tạo context từ cấu hình hiện tại rồi gắn nhầm vào câu trả lời cũ.

Nếu cần nhắc người dùng đánh giá sau một mốc thời gian, chỉ gửi theo cơ chế thông báo mà người dùng đã chấp thuận và theo chính sách sản phẩm. Tránh gây phiền bằng nhắc nhở lặp lại.

## 15. Các lỗi thiết kế thường gặp

| Thiết kế lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Gắn feedback chỉ với conversationId | Không biết câu trả lời nào bị đánh giá | Dùng assistantTurnId và interactionId |
| Tin traceId do browser gửi | Có thể liên kết sai hoặc truy cập trace không thuộc actor | Server resolve trace từ snapshot |
| Chỉ lưu rating | Không biết prompt/model/context gây ra kết quả | Lưu metadata và evidence references tối thiểu |
| Lưu toàn bộ hội thoại mặc định | Tăng rủi ro dữ liệu nhạy cảm | Data minimization, redaction và retention |
| Chỉ log model name | Không tái hiện được prompt/retriever/tool version | Lưu version và configuration snapshot |
| Lưu raw RAG documents vào feedback | Lộ tài liệu nội bộ hoặc dữ liệu tenant khác | Lưu IDs, hashes, scores và secure references |
| Gộp copy thành positive | Tạo nhãn chất lượng sai | Giữ behavioral signals riêng |
| Gộp mọi 👎 thành hallucination | Chẩn đoán sai nguyên nhân | Dùng reason taxonomy và review |
| Gọi feedback là ground truth | Dataset nhiễu và benchmark lệch | Adjudication và provenance |
| Đếm negative rate trên mọi request | Mẫu số không đúng | Tách feedback rate và exposure |
| Dùng traceId làm metric label | Cardinality bùng nổ | Lưu ID trong event store, metric dùng label hữu hạn |
| Ghi đè feedback cũ | Mất lịch sử và audit | Append event hoặc superseding reference |
| Dùng case tuning làm held-out test | Rò rỉ test set | Tách dataset split và lưu provenance |

## 16. Quy trình triển khai từng bước

1. Xác định các màn hình và loại câu trả lời có thể nhận feedback.
2. Tạo interactionId và assistantTurnId ở server.
3. Chọn context fields cần thiết cho các câu hỏi điều tra thực tế.
4. Lưu interaction snapshot bất biến sau khi response được tạo.
5. Trả opaque IDs cho UI cùng câu trả lời.
6. Thiết kế rating, reason taxonomy và comment/correction tùy chọn.
7. Xây feedback API với authentication, tenant authorization, validation và idempotency.
8. Resolve snapshot và trace metadata từ server-side store.
9. Lưu feedback event và publish outbox event trong transaction.
10. Redact, encrypt, audit và áp retention cho context/evidence.
11. Tạo triage queue để reviewer xác nhận hoặc phân loại phản hồi.
12. Chuyển confirmed defects thành evaluation cases có version và provenance.
13. Replay dataset trên prompt/model/retriever candidates.
14. Xây dashboard phân biệt feedback coverage, negative rate, confirmed defects và evaluator metrics.
15. Kiểm tra tenant isolation, duplicate submission, delayed feedback và data deletion flow.

## 17. Checklist kiểm thử production

| Kịch bản | Kết quả cần xác minh |
| --- | --- |
| Feedback cho câu trả lời đầu tiên trong conversation | Gắn đúng assistantTurnId |
| Feedback cho câu trả lời thứ ba | Không bị gắn nhầm vào lượt gần nhất |
| Browser gửi interactionId của tenant khác | Bị từ chối, không tiết lộ dữ liệu |
| Browser gửi traceId giả | Bị bỏ qua; trace được resolve từ snapshot |
| Gửi lại cùng feedbackEventId | Không tạo duplicate |
| Người dùng sửa rating | Lưu lịch sử hoặc superseding event |
| Feedback đến sau khi prompt được rollout | Vẫn tham chiếu prompt version cũ |
| RAG document đã được cập nhật | Snapshot vẫn giữ document/chunk version ban đầu |
| Tool call thất bại | Tool status và error category được liên kết |
| Stream bị cancel | Usage/TTFT được đánh dấu partial hoặc missing đúng contract |
| Comment chứa PII | Redaction hoặc policy xử lý trước khi lưu |
| Feedback bị xóa theo yêu cầu | Event và evidence references được xử lý theo retention/deletion policy |
| Trace backend không sẵn sàng | Feedback vẫn lưu được; trace reference có trạng thái unavailable |
| Feedback rate thấp | Dashboard hiển thị coverage và sample size |
| Dataset case được dùng để tuning | Không âm thầm đưa vào held-out test set |

## 18. Bài tập thực hành

### Bài 1. Gắn feedback vào một assistant turn

Tạo chat UI có nút 👍/👎 cho từng câu trả lời. Gửi interactionId, assistantTurnId và feedbackEventId. Thử gửi feedback sau khi đã có thêm nhiều lượt chat để xác minh không bị gắn nhầm.

### Bài 2. Lưu interaction snapshot cho RAG

Mỗi response lưu prompt version, model revision, retriever/index version, document/chunk IDs, rank và scores. Gửi một feedback “không có căn cứ”, sau đó mở đúng snapshot và trace để kiểm tra nguồn được truy xuất.

### Bài 3. Theo dõi tool failures

Tạo một câu hỏi cần gọi tool. Lưu tool name, version, status và duration. Gửi feedback TOOL_FAILURE khi tool thất bại; xác định lỗi ở model routing, tool schema hay downstream API.

### Bài 4. Kiểm thử bảo vệ tenant

Tạo hai tenant và thử dùng interactionId của tenant A từ tài khoản tenant B. Xác minh API không trả context, traceId hoặc thông tin feedback của tenant A.

### Bài 5. Phân biệt feedback với ground truth

Tạo một feedback negative nhưng evaluator chấm relevance cao. Đưa event vào triage, ghi reviewer verdict và giải thích sự khác nhau giữa trải nghiệm người dùng, rubric evaluator và evidence.

### Bài 6. Usage coverage và feedback dashboard

Tạo dashboard gồm exposure, feedback submissions, negative rate, reason distribution, confirmed defects và token usage coverage. Kiểm tra trường hợp không có feedback để tránh hiển thị 0% negative như một dấu hiệu chất lượng tốt.

### Bài 7. Tạo evaluation case

Chọn một feedback đã được reviewer xác nhận. Tạo case gồm input cần thiết, expected behavior, source references, rubric version và provenance. Replay trên prompt/model mới và so sánh relevance, factuality, latency và cost.

## 19. Tổng kết

Một feedback loop production cần nối **ý kiến người dùng với đúng câu trả lời và trạng thái hệ thống lúc câu trả lời được tạo**:

- Dùng interactionId và assistantTurnId để xác định đúng lượt; conversationId chỉ là ngữ cảnh rộng hơn.
- Lưu snapshot bất biến chứa model, prompt, retriever, nguồn RAG, tools, evaluation results và trace reference ở mức cần thiết.
- Feedback API chỉ nhận rating/reason/comment cùng opaque IDs; server tự resolve actor, tenant và context.
- Giữ feedback tường minh, hành vi và kết quả nghiệp vụ thành các tín hiệu riêng.
- Không mặc định lưu toàn bộ prompt, completion, tài liệu RAG hoặc tool arguments; áp dụng data minimization, redaction, authorization, audit và retention.
- Feedback là tín hiệu cần triage; chỉ chuyển thành evaluation case sau khi có evidence, reviewer verdict và provenance.
- Dashboard phải hiển thị coverage, sample size và negative rate đúng mẫu số.
- Giữ dataset split để feedback dùng cho tuning không làm nhiễm held-out evaluation.

Khi feedback được nối với traces, versions, retrieval evidence, tool execution và evaluator results, nhóm phát triển có thể tái hiện vấn đề, xác định tầng gây lỗi và biến phản hồi thực tế thành bộ kiểm thử chất lượng có thể chạy lại.

## Tài liệu tham khảo

- [Spring AI 2.1.0 Reference — Observability](https://docs.spring.io/spring-ai/reference/observability/index.html): ChatClient/Advisor/ChatModel observations, conversation ID, tool names, cardinality và mặc định không export prompt/completion.
- [Spring Boot Reference — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): Micrometer Tracing, trace context và baggage propagation.
- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): context propagation qua thread và reactive pipelines.
- [OWASP GenAI Security — Prompt Injection](https://genai.owasp.org/llm2026/llm012026-prompt-injection/): rủi ro từ user input, retrieved content, tool output và persistent memory.
- [OWASP GenAI Incident Response Guide](https://genai.owasp.org/download/49068/): evidence sources, user-interaction logs và các cân nhắc riêng tư khi lưu prompts.
- [OWASP Prompt Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html): monitoring metadata, loại credentials/secrets và dữ liệu prompt/response nhạy cảm không cần thiết.
