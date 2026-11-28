# Ghi sự kiện nghiệp vụ, cấu hình và lỗi có thể xử lý

Một evaluation run của ứng dụng Spring AI kết thúc với 12 case thất bại. Dashboard chỉ cho biết tỷ lệ lỗi tăng, còn log ghi những dòng chung chung như “Request failed” hoặc “Invalid response”. Người trực vận hành không biết case nào bị ảnh hưởng, lỗi xảy ra ở retrieval hay model, có thể retry hay phải can thiệp cấu hình, và ai cần xử lý tiếp theo.

Một hệ thống logging tốt cần ghi lại ba nhóm thông tin có ý nghĩa khác nhau: **sự kiện nghiệp vụ** mô tả trạng thái và quyết định của ứng dụng; **sự kiện cấu hình** giải thích hệ thống đang chạy với thiết lập nào và thiết lập đó thay đổi ra sao; **sự kiện lỗi có thể xử lý** cho biết điều gì hỏng, mức độ ảnh hưởng và bước tiếp theo cần thực hiện.

Với Spring AI, ba nhóm này giúp nối kết quả đánh giá với prompt/model/pipeline version, theo dõi việc kích hoạt cấu hình, giải thích tool authorization, phân loại provider errors và đưa cảnh báo tới đúng người xử lý. Log phải có cấu trúc và correlation IDs, nhưng không nên trở thành nơi lưu raw prompt, secrets hoặc toàn bộ payload của người dùng.

Bài học thuộc module **SPRING_AI_EVALUATION_OBSERVABILITY**. Nội dung tập trung vào thiết kế event contract, ghi nhận business lifecycle, cấu hình hiệu lực, error taxonomy, retry semantics, outbox, Spring Boot/SLF4J và kiểm thử. Các ví dụ sử dụng Java và Spring theo hướng trung lập với provider; tên property hoặc event schema là quy ước của ứng dụng mẫu, không phải API bắt buộc của Spring AI.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt business event, diagnostic log, configuration event, audit event, metric và trace.
2. Thiết kế event envelope có event ID, schema version, timestamp, producer và correlation metadata.
3. Ghi lại các chuyển trạng thái nghiệp vụ của evaluation run, case, prompt rollout và tool operation.
4. Phân biệt log để quan sát với event cần lưu bền vững và phát cho consumer.
5. Dùng transactional outbox để tránh mất business event khi transaction commit.
6. Ghi nhận cấu hình khởi động và cấu hình thay đổi mà không lộ secret.
7. Phân biệt desired configuration với effective configuration thực sự đang chạy.
8. Xây error taxonomy có severity, stage, retry disposition và operator action.
9. Phân loại lỗi transient, permanent, quota, authorization, timeout và unknown outcome.
10. Thiết kế log an toàn bằng SLF4J, Logback và allowlisted fields.
11. Nối event với run/case/attempt, trace ID, span ID và evidence reference.
12. Kiểm thử event schema, redaction, outbox idempotency và error classification.
13. Tạo quy trình điều tra có thể chuyển từ log tới hành động xử lý cụ thể.

## 2. Bốn loại sự kiện cần phân biệt

Từ “event” thường được dùng cho nhiều loại dữ liệu. Nếu không phân biệt mục đích, nhóm phát triển dễ dùng log thay message queue, dùng metric thay business history hoặc coi một lỗi chất lượng là lỗi kỹ thuật.

| Loại | Mục đích | Ví dụ | Cách lưu phù hợp |
| --- | --- | --- | --- |
| Diagnostic log | Giải thích một thao tác nội bộ | Vector search mất 120 ms | Log backend |
| Business event | Ghi một sự kiện nghiệp vụ đã xảy ra | Evaluation run hoàn tất | Event store/outbox hoặc domain event pipeline |
| Configuration event | Ghi cấu hình được nạp/thay đổi | Prompt release v8 được kích hoạt | Audit/config event store và structured log |
| Error event | Ghi sự cố và hướng xử lý | Provider trả 429, có thể retry sau 2 giây | Structured log, error stream hoặc incident system |
| Audit event | Chứng minh một hành động nhạy cảm/được kiểm soát | Người có quyền phê duyệt prompt release | Kho audit có quyền và retention riêng |

Metrics và traces là hai loại telemetry khác:

- Metric tổng hợp số lượng, tỷ lệ, histogram hoặc trạng thái theo thời gian.
- Trace mô tả request đi qua các operation và spans nào.
- Event/log ghi lại một sự kiện cụ thể và metadata để điều tra.

### 2.1. Business event khác log message

Một business event mô tả sự thật đã xảy ra trong domain, ví dụ EvaluationRunCompleted. Consumer có thể dùng nó để cập nhật report, gửi thông báo hoặc kích hoạt bước tiếp theo.

Một log message như “Finished evaluation run” chỉ là thông tin chẩn đoán. Nó có thể bị sampling, hết retention hoặc mất khi log collector gặp sự cố. Không dùng log message làm hợp đồng tích hợp giữa các service.

### 2.2. Error event không phải lúc nào cũng là business event

Một case có verdict FAIL là kết quả đánh giá hợp lệ. Một tool authorization DENY có thể là hành vi bảo mật đúng. Provider timeout là lỗi kỹ thuật. Ba trường hợp này không nên được gộp thành một event ERROR duy nhất.

Tách outcome theo ý nghĩa:

- execution outcome: thao tác có hoàn tất hay không.
- business outcome: trạng thái nghiệp vụ đã đạt tới đâu.
- quality verdict: nội dung AI PASS/FAIL/NOT_EVALUATED.
- security decision: ALLOW/DENY.
- technical failure: lỗi hệ thống hoặc dependency.

## 3. Event envelope thống nhất

Mỗi event nên có một envelope chung để consumer biết ai tạo, tạo khi nào, thuộc luồng nào và cần diễn giải theo schema version nào.

| Field | Kiểu | Ý nghĩa |
| --- | --- | --- |
| eventId | UUID/ULID | Định danh duy nhất của event |
| eventName | string | Tên event ổn định |
| eventVersion | integer | Version của schema |
| occurredAt | timestamp UTC | Thời điểm sự kiện thực sự xảy ra |
| recordedAt | timestamp UTC | Thời điểm hệ thống ghi nhận |
| producer | string | Service/component phát event |
| environment | string | Môi trường chạy |
| subjectType | string | Loại aggregate/entity liên quan |
| subjectId | string | ID của aggregate/entity |
| runId/caseId/attemptId | string | Correlation nghiệp vụ nếu có |
| traceId/spanId | string | Distributed tracing context nếu có |
| causationId | string | Event/command trực tiếp gây ra event này |
| correlationId | string | Nhóm các message cùng một workflow |
| payload | object | Dữ liệu nghiệp vụ đã được allowlist |

Ví dụ envelope:

~~~json
{
  "eventId": "01JVB8K8M4Y7W8N1",
  "eventName": "evaluation.run.completed",
  "eventVersion": 1,
  "occurredAt": "2026-05-18T10:30:00Z",
  "recordedAt": "2026-05-18T10:30:00.018Z",
  "producer": "evaluation-service",
  "environment": "staging",
  "subjectType": "EvaluationRun",
  "subjectId": "support-eval-v5",
  "correlationId": "workflow-81",
  "causationId": "evaluation-command-81",
  "traceId": "actual-trace-id",
  "spanId": "actual-span-id",
  "payload": {
    "status": "COMPLETED",
    "selectedCases": 100,
    "completedCases": 100,
    "reportRef": "artifact://reports/support-eval-v5"
  }
}
~~~

Giá trị minh họa. Không phải mọi event đều cần đủ mọi field. Schema có thể cho phép trace IDs vắng mặt nếu tracing không được bật hoặc event được tạo ngoài request context. Không tự tạo trace ID giả để lấp field.

### 3.1. occurredAt và recordedAt

occurredAt mô tả lúc domain event xảy ra; recordedAt mô tả lúc event được ghi vào store hoặc broker. Hai thời điểm có thể khác nhau khi outbox dispatcher chạy trễ hoặc event được replay.

Dùng timestamp UTC và đồng bộ clock giữa các node. Nếu cần thứ tự trong cùng aggregate, dùng aggregate sequence/version; không chỉ dựa vào timestamp vì clock skew và concurrency có thể đảo thứ tự.

### 3.2. eventId và idempotency

eventId phải ổn định khi cùng một outbox record được publish lại. Consumer dùng eventId để chống xử lý trùng. Nếu producer tạo event mới cho cùng một business transition, eventId mới là hợp lý; idempotency key của command/operation là khái niệm riêng.

### 3.3. Event version

Thêm field optional tương thích thường không cần đổi major event version nếu contract cho phép. Đổi type, đổi semantics hoặc xóa required field là breaking change; tạo version mới và có kế hoạch chuyển consumer.

Không giữ version cũ nhưng âm thầm đổi ý nghĩa của status hoặc timestamp.

## 4. Đặt tên business event theo sự thật đã xảy ra

Tên event nên diễn tả sự kiện đã xảy ra, thường dùng past tense hoặc dạng completed/activated/denied. Tránh tên mơ hồ như process, update hoặc doAction.

Ví dụ cho hệ thống evaluation:

| Event name | Sự thật được ghi nhận |
| --- | --- |
| evaluation.run.started | Một run đã bắt đầu |
| evaluation.case.started | Một case attempt đã bắt đầu |
| evaluation.case.completed | Case execution đã kết thúc |
| evaluation.verdict.recorded | Một evaluator verdict đã được lưu |
| evaluation.report.published | Report artifact đã được phát hành |
| prompt.version.activated | Prompt version mới đã được kích hoạt |
| model.route.changed | Model routing policy đã đổi |
| tool.authorization.denied | Một tool operation bị từ chối |
| tool.operation.reconciled | Unknown outcome đã được đối soát |
| evaluation.run.cancelled | Run đã bị hủy |

### 4.1. Không ghi ý định thành sự thật

evaluation.run.started chỉ phát sau khi run được tạo và chuyển sang trạng thái bắt đầu theo domain contract. evaluation.report.published chỉ phát sau khi report artifact đã được persist và có thể truy cập theo policy.

Nếu thao tác mới được yêu cầu nhưng chưa thực hiện, dùng command/request event hoặc log nhận yêu cầu. Đừng phát event completed trước khi transaction hoặc side effect hoàn tất.

### 4.2. Event payload tối thiểu

Một business event chỉ nên chứa dữ liệu consumer cần. Ví dụ evaluation.verdict.recorded cần run/case/attempt IDs, metric name, status, rubric version, judge version và evidence refs đã được phép. Không cần nhúng toàn bộ prompt, answer hay context vào broker message.

### 4.3. Một verdict mới không ghi đè verdict cũ

Nếu judge/rubric thay đổi và chấm lại answer, tạo evaluation ID và verdict event mới. Event history phải giữ được verdict trước đó để giải thích report đã phát hành.

## 5. Luồng event trong một ứng dụng Spring AI

Một pipeline evaluation có thể tạo diagnostic logs, metrics, traces, evidence artifacts và business events cùng lúc.

~~~mermaid
flowchart TD
    A["Evaluation command"] --> B["Run service"]
    B --> C["Case / attempt processing"]
    C --> D["Spring AI: retrieval, model, tools"]
    D --> E["Evaluator + verdict"]
    E --> F["Report persistence"]
    B --> G["Transaction + outbox row"]
    E --> G
    F --> G
    G --> H["Outbox dispatcher"]
    H --> I["Event broker / consumers"]
    C --> J["Structured diagnostic logs"]
    D --> J
    E --> J
    D --> K["Metrics + traces"]
    D --> L["Evidence store"]
    I --> M["Reporting / notification / workflow"]
~~~

Sơ đồ minh họa kiến trúc logic. Một ứng dụng đơn giản có thể chưa cần broker; outbox/event store vẫn giúp phân biệt durable business history với diagnostic logs.

### 5.1. Diagnostic log có thể best-effort

Log như “retrieval completed in 46 ms” phục vụ điều tra. Nếu log collector tạm thời không nhận được record, business transaction vẫn có thể thành công. Metrics/traces cũng có export pipeline và sampling riêng.

### 5.2. Business event cần durability theo hợp đồng

Nếu consumer phải biết run nào đã hoàn tất, event không được mất chỉ vì log sink down. Ghi event cùng transaction với thay đổi trạng thái, thường qua transactional outbox. Nếu event chỉ là local UI notification không quan trọng, in-memory Spring application event có thể đủ; phải xác định rõ guarantee.

## 6. Các business events quan trọng của evaluation workflow

### 6.1. Run lifecycle

Các event run thường gồm:

- evaluation.run.created
- evaluation.run.started
- evaluation.run.paused
- evaluation.run.resumed
- evaluation.run.completed
- evaluation.run.failed
- evaluation.run.cancelled

Payload nên chứa run ID, suite/dataset snapshot, run type, selected case count, initiator/service actor, started/ended timestamps, outcome và report ref khi có.

Không ghi toàn bộ dataset vào event. Dùng immutable dataset snapshot reference/version.

### 6.2. Case lifecycle

Một case có thể retry nhiều lần. Event cần phân biệt case ID với attempt ID:

~~~json
{
  "eventId": "event-case-017",
  "eventName": "evaluation.case.completed",
  "eventVersion": 1,
  "subjectType": "EvaluationCase",
  "subjectId": "POLICY-017",
  "correlationId": "support-eval-v5",
  "payload": {
    "runId": "support-eval-v5",
    "caseId": "POLICY-017",
    "attemptId": "POLICY-017-attempt-2",
    "executionStatus": "COMPLETED",
    "qualityStatus": "FAIL",
    "durationMs": 1430,
    "verdictRef": "artifact://verdicts/verdict-17"
  }
}
~~~

Case execution completed nhưng quality FAIL là một trạng thái hợp lệ. Không phát evaluation.case.failed chỉ vì nội dung answer không đạt rubric.

### 6.3. Prompt/model rollout

Khi prompt version hoặc model routing thay đổi, ghi:

- Version cũ và mới (hoặc fingerprint).
- Environment/tenant/scope áp dụng.
- Người hoặc service khởi tạo thay đổi.
- Approval/change request reference nếu có.
- Thời điểm effective.
- Kết quả validation/activation.
- Rollback event nếu thay đổi bị đảo ngược.

Không ghi raw prompt vào event. Dùng prompt artifact ref/digest, access policy và version.

### 6.4. Tool operation

Tool calling có thể tạo side effect. Business event nên ghi operation ID, tool name/schema version, authorization decision, idempotency reference, backend result status và reconciliation state. Arguments nhạy cảm phải được redact hoặc lưu trong secure evidence store.

## 7. Spring ApplicationEventPublisher và giới hạn của in-memory events

Spring cung cấp ApplicationEventPublisher để một component phát application event cho listener trong cùng application context.

Ví dụ:

~~~java
import java.time.Instant;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

public record EvaluationRunCompleted(
        String runId,
        String reportRef,
        int completedCases,
        Instant occurredAt) {}

@Service
public class EvaluationRunService {

    private final ApplicationEventPublisher publisher;

    public EvaluationRunService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @Transactional
    public void markCompleted(
            String runId,
            String reportRef,
            int completedCases) {

        // Persist run state and report before announcing completion.
        publisher.publishEvent(new EvaluationRunCompleted(
                runId,
                reportRef,
                completedCases,
                Instant.now()));
    }
}
~~~

Đây là ví dụ local event đơn giản. ApplicationEventPublisher không tự tạo durable queue, không đảm bảo consumer khác service nhận event và không tự cung cấp replay sau process crash.

### 7.1. Transaction-bound listener

Nếu listener cần chạy sau khi transaction commit, có thể dùng @TransactionalEventListener với phase AFTER_COMMIT. Cách này tránh listener chạy trước khi transaction commit thành công, nhưng event in-memory vẫn có thể mất nếu process dừng sau commit trước khi listener thực thi.

Ví dụ listener chỉ cập nhật projection sau khi transaction của service commit:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class EvaluationProjectionListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onRunCompleted(EvaluationRunCompleted event) {
        // Update a local projection; use an outbox for durable cross-service delivery.
        updateProjection(event.runId(), event.reportRef());
    }

    private void updateProjection(String runId, String reportRef) {
        // Projection persistence is application-specific.
    }
}
~~~

Với event quan trọng, transactional outbox là lựa chọn bền vững hơn.

### 7.2. Không thực hiện side effect nặng trong transaction

Không gọi provider, gửi email hoặc publish HTTP request dài bên trong database transaction chỉ để phát event. Transaction kéo dài sẽ giữ lock/connection và có thể rollback DB trong khi side effect bên ngoài đã thành công.

Persist business state + outbox record trong một transaction ngắn; dispatcher thực hiện publish sau commit.

## 8. Transactional outbox: không để event biến mất sau commit

Vấn đề dual-write xảy ra khi service vừa commit database vừa publish message tới broker:

1. DB commit thành công.
2. Process crash trước khi publish.
3. Consumer không nhận event dù trạng thái đã đổi.

Đảo thứ tự cũng có vấn đề: publish thành công rồi DB rollback sẽ phát một event cho trạng thái chưa tồn tại.

Transactional outbox ghi business state và event record trong cùng một database transaction. Một dispatcher đọc outbox và publish sau commit.

~~~mermaid
sequenceDiagram
    participant S as Evaluation Service
    participant DB as Database
    participant O as Outbox Dispatcher
    participant B as Broker
    participant C as Consumer
    S->>DB: Update run state + insert outbox row
    DB-->>S: Commit both atomically
    O->>DB: Claim pending outbox row
    DB-->>O: Event payload + eventId
    O->>B: Publish event
    B-->>O: Broker acknowledgement
    O->>DB: Mark row published
    B->>C: Deliver event (possibly more than once)
    C->>C: Deduplicate by eventId
~~~

### 8.1. Bảng outbox gợi ý

~~~sql
CREATE TABLE event_outbox (
    event_id          VARCHAR(64) PRIMARY KEY,
    event_name        VARCHAR(160) NOT NULL,
    event_version     INTEGER NOT NULL,
    aggregate_type    VARCHAR(80) NOT NULL,
    aggregate_id      VARCHAR(160) NOT NULL,
    aggregate_version BIGINT,
    occurred_at       TIMESTAMP WITH TIME ZONE NOT NULL,
    payload_json      TEXT NOT NULL,
    publish_status    VARCHAR(24) NOT NULL,
    attempt_count     INTEGER NOT NULL DEFAULT 0,
    next_attempt_at   TIMESTAMP WITH TIME ZONE,
    created_at        TIMESTAMP WITH TIME ZONE NOT NULL,
    published_at      TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_outbox_pending
    ON event_outbox (publish_status, next_attempt_at, created_at);
~~~

Schema minh họa. Với PostgreSQL có thể dùng JSONB; với database khác chọn kiểu phù hợp. Không đưa secrets hoặc raw prompts vào payload_json.

### 8.2. Publish ít nhất một lần và consumer idempotent

Outbox dispatcher có thể publish thành công rồi crash trước khi đánh dấu row PUBLISHED. Khi chạy lại, nó publish lần nữa. Vì vậy, outbox thường cung cấp at-least-once delivery; consumer phải deduplicate bằng eventId hoặc xử lý idempotent.

Không tuyên bố exactly-once chỉ vì có transaction. Exactly-once end-to-end phụ thuộc broker, consumer transaction và side effects; thường vẫn cần idempotency.

### 8.3. Ordering theo aggregate

Nếu thứ tự event quan trọng, lưu aggregate version/sequence và đảm bảo dispatcher/consumer xử lý đúng thứ tự trong cùng aggregate. Không giả định nhiều worker poll song song sẽ tự giữ ordering.

### 8.4. Retention và cleanup

Chỉ xóa outbox rows đã publish và hết retention theo policy. Giữ đủ metadata để đối soát và replay nếu yêu cầu nghiệp vụ cần. Event store, broker retention và audit store có thể có thời hạn khác nhau.

## 9. Ghi cấu hình khởi động và cấu hình hiệu lực

Một ứng dụng Spring AI có thể dùng cấu hình từ application.yaml, profile, environment variables, command-line args, secret manager hoặc config server. Giá trị hiệu lực thường là kết quả của precedence giữa các property sources.

Để điều tra một run cũ, cần biết **cấu hình hiệu lực** khi run bắt đầu, không chỉ biết file cấu hình mặc định trong repository.

### 9.1. Cấu hình nào nên được ghi?

Với pipeline AI, các trường có ích thường gồm:

| Nhóm | Metadata cần ghi |
| --- | --- |
| Application | build/commit ID, Spring Boot/Spring AI versions |
| Model | provider, requested/resolved model ID, operation |
| Generation | temperature, max output tokens, response format |
| Prompt | template version/digest, system instruction version |
| Retrieval | VectorStore/index/corpus version, top-k, filter version |
| Embedding | embedding model/version, dimensions nếu biết |
| Tool | tool schema version, authorization policy version |
| Evaluation | rubric, judge model/prompt version, aggregation policy |
| Runtime | timeout, retry policy, concurrency/queue limits |

Không phải mọi field đều phải log ở mọi request. Ghi startup/config snapshot theo version, sau đó liên kết run với snapshot ID. Khi cấu hình thay đổi, tạo event mới.

### 9.2. Desired config và effective config

- Desired config: giá trị khai báo trong deployment, config repository hoặc control plane.
- Effective config: giá trị ứng dụng thực sự bind và sử dụng sau precedence, validation, defaulting và runtime overrides.

Ví dụ desired model là chat-model-stable nhưng provider adapter resolve sang revision khác. Ghi cả requested và resolved nếu provider cho phép. Nếu không có resolved revision, ghi trạng thái NOT_EXPOSED.

### 9.3. Không dump toàn bộ Environment

Spring Environment có thể chứa password, API key, bearer token, database URL, proxy credentials và secret references. Không log tất cả property sources hoặc /actuator/env/configprops output vào log thường.

Dùng typed configuration snapshot với allowlist các field an toàn. Secret chỉ ghi logical secret name/version/reference nếu policy cho phép; tuyệt đối không ghi secret value.

## 10. Configuration fingerprint và snapshot

Một config snapshot giúp xác định run dùng cấu hình nào. Có thể tạo fingerprint từ các trường đã chọn và canonicalized.

Ví dụ:

~~~json
{
  "configSnapshotId": "cfg-support-v5-20260518",
  "configSchemaVersion": 2,
  "effectiveAt": "2026-05-18T10:00:00Z",
  "sourceSummary": [
    "application-defaults",
    "staging-profile",
    "deployment-environment"
  ],
  "fingerprint": "sha256:...",
  "ai": {
    "provider": "example-provider",
    "requestedModel": "chat-model-stable",
    "promptVersion": "support-prompt-v7",
    "temperature": 0,
    "maxOutputTokens": 800,
    "corpusVersion": "policy-v3",
    "retrievalTopK": 5,
    "rubricVersion": "support-rubric-v3"
  },
  "secrets": {
    "providerCredential": {
      "reference": "secret://ai/provider-credential",
      "version": "rotation-42",
      "valueCaptured": false
    }
  }
}
~~~

### 10.1. Fingerprint không thay thế snapshot

Fingerprint giúp so sánh nhanh nhưng không thể khôi phục cấu hình. Lưu snapshot hoặc immutable reference tới snapshot; fingerprint chỉ là kiểm tra/tìm kiếm bổ sung.

### 10.2. Canonicalization

Trước khi hash, serialize field theo thứ tự ổn định, encoding xác định và loại bỏ volatile metadata không thuộc config identity. Ghi canonicalization version. Không hash một Map có thứ tự iteration không xác định rồi mong digest ổn định.

### 10.3. Không hash trực tiếp secret để làm fingerprint

Hash API key hoặc password có thể tạo oracle để kiểm tra secret guesses. Loại secret value khỏi snapshot/fingerprint. Nếu cần biết credential rotation, lưu secret reference/version do secret manager cấp, không lưu digest của secret.

## 11. Java: typed configuration properties và startup event

Ví dụ dùng application-owned configuration prefix để minh họa. Prefix app.ai.* dưới đây là quy ước của ứng dụng mẫu; không phải tên property mặc định của Spring AI.

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.ai")
public record AiRuntimeProperties(
        @NotBlank String provider,
        @NotBlank String model,
        @NotBlank String promptVersion,
        @Min(1) @Max(4096) int maxOutputTokens,
        @Min(0) @Max(2) double temperature,
        @NotBlank String corpusVersion,
        @Min(1) @Max(50) int retrievalTopK,
        @NotBlank String rubricVersion) {}
~~~

Đăng ký properties bằng @ConfigurationPropertiesScan hoặc @EnableConfigurationProperties theo cấu trúc ứng dụng.

### 11.1. Log startup snapshot

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class AiConfigurationStartupLogger {

    private static final Logger log =
            LoggerFactory.getLogger(AiConfigurationStartupLogger.class);

    private final AiRuntimeProperties properties;

    public AiConfigurationStartupLogger(AiRuntimeProperties properties) {
        this.properties = properties;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void logEffectiveConfiguration() {
        log.atInfo()
                .addKeyValue("event.name", "ai.configuration.loaded")
                .addKeyValue("event.version", 1)
                .addKeyValue("ai.provider", properties.provider())
                .addKeyValue("ai.model.requested", properties.model())
                .addKeyValue("prompt.version", properties.promptVersion())
                .addKeyValue("ai.max_output_tokens",
                        properties.maxOutputTokens())
                .addKeyValue("ai.temperature", properties.temperature())
                .addKeyValue("rag.corpus.version", properties.corpusVersion())
                .addKeyValue("rag.top_k", properties.retrievalTopK())
                .addKeyValue("evaluation.rubric.version",
                        properties.rubricVersion())
                .log("Effective AI configuration loaded");
    }
}
~~~

Đoạn code chỉ log allowlisted values từ typed properties. Nó không truy cập toàn bộ Environment và không log credential. Với nhiều model routes/tenants, snapshot nên được tạo theo scope cấu hình và gắn configSnapshotId vào run.

### 11.2. Validation phải xảy ra trước khi nhận traffic

Nếu model ID, timeout hoặc top-k không hợp lệ, ứng dụng nên fail startup hoặc từ chối activation thay vì chạy với giá trị ngầm định sai. Configuration loaded event chỉ được ghi sau khi cấu hình đã validate và ứng dụng sẵn sàng.

## 12. Ghi nhận cấu hình thay đổi khi runtime

Một số hệ thống hỗ trợ dynamic refresh hoặc model routing thay đổi mà không restart. Khi đó cần ghi ai/what/when/scope và kết quả apply.

Ví dụ config change event:

~~~json
{
  "eventId": "config-change-71",
  "eventName": "ai.configuration.changed",
  "eventVersion": 1,
  "occurredAt": "2026-05-18T12:00:00Z",
  "producer": "configuration-service",
  "payload": {
    "changeId": "change-71",
    "actorRef": "service:release-controller",
    "environment": "staging",
    "scope": "support-assistant",
    "configSnapshotBefore": "cfg-v7",
    "configSnapshotAfter": "cfg-v8",
    "changedKeys": [
      "app.ai.model",
      "app.ai.prompt-version"
    ],
    "approvalRef": "change-request-71",
    "applyStatus": "APPLIED"
  }
}
~~~

### 12.1. Chỉ ghi changed keys đã allowlist

Không dump old/new values cho mọi property. Một số field có thể là secret hoặc dữ liệu nhạy cảm. Với giá trị an toàn, có thể ghi old/new values; với secret, ghi reference/version hoặc chỉ ghi “rotated”.

### 12.2. Phân biệt requested, validated và applied

- REQUESTED: thay đổi được gửi tới hệ thống.
- VALIDATED: schema/policy checks đã thành công.
- APPLIED: runtime thực sự sử dụng cấu hình mới.
- REJECTED: validation/policy từ chối.
- ROLLED_BACK: đã quay về snapshot trước.

Không phát APPLIED khi chỉ mới ghi config file hoặc gọi refresh endpoint.

### 12.3. Config refresh phải có version

Mỗi config snapshot có ID/fingerprint mới. Một evaluation run ghi configSnapshotId khi bắt đầu; các case trong cùng run phải tuân theo policy nhất quán. Nếu dynamic change giữa run được phép, record snapshot theo attempt và đánh dấu run không còn single-config.

### 12.4. Rollback là event riêng

Rollback không xóa event change trước đó. Ghi ai rollback, từ snapshot nào về snapshot nào, reason code và activation result. Lịch sử bất biến giúp điều tra regression sau deployment.

## 13. Configuration events trong Spring AI

Các thay đổi cấu hình có thể tác động trực tiếp đến chất lượng và chi phí.

| Thay đổi | Tác động cần quan sát |
| --- | --- |
| Model/provider route | Answer quality, latency, token pricing, rate limit |
| Prompt template | Relevance, instruction following, format |
| Temperature/max tokens | Variance, truncation, cost |
| Corpus/index snapshot | Recall, freshness, groundedness |
| Embedding model/chunking | Retrieval quality, vector compatibility |
| Top-k/filter/reranker | Context size, relevance, latency |
| Tool schema | Tool selection, argument validity |
| Authorization policy | ALLOW/DENY, access control |
| Rubric/judge prompt | Score distribution, evaluator consistency |
| Retry/timeout | Error rate, latency, duplicate side effects |

### 13.1. Snapshot theo run và theo attempt

Run-level snapshot đủ khi config bất biến trong suốt run. Nếu runtime cho phép per-tenant routing hoặc config refresh giữa chừng, ghi snapshot ID ở attempt level để mỗi kết quả có provenance chính xác.

### 13.2. Model alias và resolved revision

Lưu requested model ID và resolved model ID nếu provider cung cấp. Nếu provider chỉ cung cấp alias, ghi rõ resolution status. Không giả định alias stable luôn trỏ tới cùng implementation.

### 13.3. Không coi config file là nguồn sự thật duy nhất

Environment variables, command-line args, remote config và secret manager có thể override file. Hãy ghi source summary hoặc property origin cho các field đã allowlist, nhưng tránh log toàn bộ environment.

## 14. Thiết kế lỗi có thể xử lý

Một error log hữu ích không chỉ chứa exception. Người trực vận hành cần biết:

- Lỗi ở stage nào?
- Service/case/attempt nào bị ảnh hưởng?
- Mã lỗi chuẩn hóa là gì?
- Có thể retry không? Nếu có, khi nào và với điều kiện gì?
- Có side effect chưa rõ trạng thái không?
- Cần người vận hành làm gì?
- Ai/team nào sở hữu vấn đề?
- Có runbook/incident reference nào?
- Error đã được xử lý, retry, reconcile hay vẫn mở?

Một error event có thể dùng schema:

~~~json
{
  "eventName": "ai.operation.failed",
  "eventVersion": 1,
  "error": {
    "code": "AI_PROVIDER_RATE_LIMITED",
    "category": "DEPENDENCY",
    "severity": "WARN",
    "stage": "MODEL_CALL",
    "retryDisposition": "AFTER_RETRY_AFTER",
    "retryable": true,
    "safeMessage": "Provider rate limit reached",
    "operatorAction": "Wait for the retry window and inspect provider quota",
    "owner": "ai-platform"
  },
  "context": {
    "runId": "support-eval-v5",
    "caseId": "POLICY-017",
    "attemptId": "POLICY-017-attempt-1",
    "modelCallId": "model-call-8f31"
  },
  "retry": {
    "attemptNumber": 1,
    "retryAfterMs": 2000,
    "budgetRemaining": 2
  },
  "traceId": "actual-trace-id"
}
~~~

### 14.1. Error code phải ổn định

Không dùng exception message làm error code. Message có thể đổi theo SDK version, chứa dynamic values hoặc locale. Error code thuộc contract của ứng dụng, ví dụ AI_PROVIDER_RATE_LIMITED hoặc AI_EVIDENCE_PERSISTENCE_FAILED.

### 14.2. Severity khác retryability

Một lỗi WARN vẫn có thể retryable. Một lỗi ERROR có thể không retry được. Severity biểu thị mức ảnh hưởng/vận hành; retry disposition biểu thị hành động kỹ thuật.

### 14.3. Operator action phải cụ thể

Tránh message “Please investigate”. Hành động tốt hơn là “Kiểm tra quota của provider; nếu Retry-After còn hiệu lực, giữ case ở trạng thái retry-pending”. Action phải dựa trên lỗi đã phân loại, không đưa ra chỉ dẫn nguy hiểm hoặc thay đổi quyền không cần thiết.

## 15. Error taxonomy cho Spring AI

Một taxonomy ứng dụng có thể gồm các nhóm sau:

| Error code | Nhóm | Retry disposition | Hành động |
| --- | --- | --- | --- |
| AI_INPUT_INVALID | INPUT | NEVER | Sửa dataset/request schema |
| AI_CONFIGURATION_INVALID | CONFIGURATION | NEVER | Sửa config rồi validate lại |
| AI_AUTHENTICATION_FAILED | SECURITY/CONFIG | NEVER | Kiểm tra credential reference/rotation |
| AI_PERMISSION_DENIED | SECURITY | NEVER | Xác minh policy và scope |
| AI_PROVIDER_RATE_LIMITED | DEPENDENCY | AFTER_RETRY_AFTER | Tuân thủ Retry-After/quota |
| AI_PROVIDER_UNAVAILABLE | DEPENDENCY | IF_IDEMPOTENT | Retry có budget/backoff |
| AI_PROVIDER_TIMEOUT | DEPENDENCY | RECONCILE_FIRST hoặc IF_IDEMPOTENT | Kiểm tra unknown outcome |
| AI_PROVIDER_QUOTA_EXCEEDED | QUOTA | NEVER hoặc DEFER | Kiểm tra billing/quota window |
| AI_RESPONSE_MALFORMED | OUTPUT | POLICY_DEPENDENT | Kiểm schema/model response |
| AI_RETRIEVAL_EMPTY | BUSINESS/QUALITY | NEVER mặc định | Kiểm query/corpus/filter |
| AI_VECTOR_STORE_UNAVAILABLE | DEPENDENCY | IF_IDEMPOTENT | Kiểm VectorStore/service |
| AI_TOOL_ARGUMENT_INVALID | TOOL/INPUT | NEVER hoặc model-correction flow | Kiểm schema/tool prompt |
| AI_TOOL_AUTHORIZATION_DENIED | SECURITY | NEVER | Kiểm quyền theo policy |
| AI_TOOL_UNKNOWN_OUTCOME | TOOL/DEPENDENCY | RECONCILE_FIRST | Đối soát operation ID |
| AI_EVALUATOR_TIMEOUT | EVALUATION | IF_IDEMPOTENT | Retry judge trong budget |
| AI_EVIDENCE_PERSISTENCE_FAILED | PERSISTENCE | POLICY_DEPENDENT | Không publish report thiếu evidence |
| AI_RUN_CANCELLED | CONTROL | NEVER | Giữ trạng thái cancelled |

Các mã là ví dụ của service. Retrieval empty thường là kết quả nghiệp vụ cần đánh giá, không phải dependency exception. Một query có thể hợp lệ nhưng không tìm thấy tài liệu.

## 16. Retry disposition và unknown outcome

Không phải mọi exception đều có thể retry. Retry an toàn cần xem tính tạm thời, idempotency, deadline, budget và side effects.

| Disposition | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| NEVER | Không retry tự động | Input invalid, 401/403 |
| IF_IDEMPOTENT | Retry nếu operation an toàn lặp lại | Read-only model call, vector search |
| AFTER_RETRY_AFTER | Chờ thời điểm provider cho phép | HTTP 429 |
| RECONCILE_FIRST | Đối soát trạng thái trước retry | Tool tạo đơn bị timeout |
| DEFER | Chuyển sang hàng đợi/lịch sau | Quota reset sau một khoảng thời gian |

### 16.1. Timeout không chứng minh operation thất bại

Nếu client timeout sau khi gửi tool request, backend có thể đã commit side effect. Retry ngay có thể tạo đơn/hoàn tiền hai lần. Ghi UNKNOWN_OUTCOME, operation ID và idempotency reference; thực hiện reconciliation trước.

### 16.2. Provider Retry-After

Khi provider trả Retry-After, tôn trọng header sau khi parse/validate. Nếu delay vượt deadline hoặc retry budget, chuyển trạng thái deferred/exhausted và ghi operator action.

Nếu provider 429 không gửi Retry-After, retry coordinator có thể dùng backoff policy đã cấu hình; không giả định delay bằng 0.

### 16.3. Retry budget và deadline

Ghi attempt number, maximum attempts, budget remaining, next eligible time và total elapsed time. Không retry chỉ vì exception là RuntimeException. Error classifier phải có provider-specific adapter để phân loại mã status và exception wrapper chính xác.

### 16.4. Log một lỗi ở đúng boundary

Các tầng dưới có thể thêm context rồi rethrow; không cần mỗi tầng ghi cùng stack trace. Ghi event đầy đủ ở boundary chịu trách nhiệm quyết định retry/fail/return. Nếu tầng thấp ghi debug, hãy tránh duplicate ERROR events.

## 17. Java: mô hình failure có kiểu rõ ràng

~~~java
import java.time.Duration;
import java.util.Objects;

public enum RetryDisposition {
    NEVER,
    IF_IDEMPOTENT,
    AFTER_RETRY_AFTER,
    RECONCILE_FIRST,
    DEFER
}

public enum FailureSeverity {
    INFO,
    WARN,
    ERROR,
    CRITICAL
}

public record AiFailure(
        String code,
        String category,
        FailureSeverity severity,
        String stage,
        RetryDisposition retryDisposition,
        String safeMessage,
        String operatorAction,
        String owner,
        Duration retryAfter,
        boolean customerVisible) {

    public AiFailure {
        Objects.requireNonNull(code);
        Objects.requireNonNull(category);
        Objects.requireNonNull(severity);
        Objects.requireNonNull(stage);
        Objects.requireNonNull(retryDisposition);
        Objects.requireNonNull(safeMessage);
        Objects.requireNonNull(operatorAction);

        if (retryAfter != null && retryAfter.isNegative()) {
            throw new IllegalArgumentException(
                    "retryAfter must not be negative");
        }
    }
}
~~~

Record không chứa exception message nguyên trạng hoặc request payload. Exception gốc có thể được giữ trong memory để xử lý, nhưng khi tạo event/log cần chọn safe fields rõ ràng.

### 17.1. Provider adapter phân loại lỗi

Không nên để domain layer phụ thuộc trực tiếp vào mọi SDK provider. Tạo adapter chuẩn hóa response metadata:

~~~java
public record ProviderFailureDetails(
        Integer httpStatus,
        String providerCode,
        boolean requestMayHaveReachedProvider,
        boolean operationHasSideEffect,
        String retryAfterHeader) {}
~~~

Adapter chịu trách nhiệm lấy metadata từ SDK exception, chuẩn hóa header và loại bỏ secrets. Domain classifier dùng dữ liệu này để quyết định disposition.

~~~java
import java.time.Duration;

public final class ProviderFailureClassifier {

    public AiFailure classify(ProviderFailureDetails details) {
        Integer status = details.httpStatus();

        if (status == null) {
            return new AiFailure(
                    "AI_PROVIDER_FAILURE_UNKNOWN",
                    "DEPENDENCY",
                    FailureSeverity.ERROR,
                    "MODEL_CALL",
                    details.operationHasSideEffect()
                            && details.requestMayHaveReachedProvider()
                            ? RetryDisposition.RECONCILE_FIRST
                            : RetryDisposition.IF_IDEMPOTENT,
                    "Provider request failed without a known status",
                    "Inspect provider diagnostics and request correlation",
                    "ai-platform",
                    null,
                    false);
        }

        if (status == 429) {
            return new AiFailure(
                    "AI_PROVIDER_RATE_LIMITED",
                    "DEPENDENCY",
                    FailureSeverity.WARN,
                    "MODEL_CALL",
                    RetryDisposition.AFTER_RETRY_AFTER,
                    "Provider rate limit reached",
                    "Respect Retry-After and inspect provider quota",
                    "ai-platform",
                    parseRetryAfter(details.retryAfterHeader()),
                    false);
        }

        if (status >= 500) {
            return new AiFailure(
                    "AI_PROVIDER_UNAVAILABLE",
                    "DEPENDENCY",
                    FailureSeverity.ERROR,
                    "MODEL_CALL",
                    details.operationHasSideEffect()
                            && details.requestMayHaveReachedProvider()
                            ? RetryDisposition.RECONCILE_FIRST
                            : RetryDisposition.IF_IDEMPOTENT,
                    "Provider service is temporarily unavailable",
                    "Check provider status and retry budget",
                    "ai-platform",
                    null,
                    false);
        }

        if (status == 401 || status == 403) {
            return new AiFailure(
                    "AI_AUTHENTICATION_OR_PERMISSION_FAILED",
                    "SECURITY",
                    FailureSeverity.ERROR,
                    "MODEL_CALL",
                    RetryDisposition.NEVER,
                    "Provider rejected authentication or permission",
                    "Verify credential reference and provider access policy",
                    "platform-security",
                    null,
                    false);
        }

        if (status >= 400) {
            return new AiFailure(
                    "AI_PROVIDER_REQUEST_REJECTED",
                    "INPUT_OR_CONFIGURATION",
                    FailureSeverity.ERROR,
                    "MODEL_CALL",
                    RetryDisposition.NEVER,
                    "Provider rejected the request",
                    "Inspect sanitized request metadata and model parameters",
                    "ai-platform",
                    null,
                    false);
        }

        return new AiFailure(
                "AI_PROVIDER_FAILURE_UNCLASSIFIED",
                "DEPENDENCY",
                FailureSeverity.ERROR,
                "MODEL_CALL",
                RetryDisposition.NEVER,
                "Provider failure could not be classified",
                "Review provider adapter and sanitized diagnostics",
                "ai-platform",
                null,
                false);
    }

    private Duration parseRetryAfter(String value) {
        if (value == null || value.isBlank()) return null;

        try {
            long seconds = Long.parseLong(value.trim());
            if (seconds < 0 || seconds > 3600) return null;
            return Duration.ofSeconds(seconds);
        } catch (NumberFormatException ignored) {
            // HTTP-date form should be parsed by a dedicated adapter.
            return null;
        }
    }
}
~~~

Ví dụ trên chỉ minh họa Retry-After dạng số giây. HTTP cũng cho phép dạng HTTP-date; adapter thực tế nên hỗ trợ cả hai, kiểm tra clock skew và giới hạn delay theo deadline/budget. Không dùng classifier này thay provider-specific error mapping.

Hai enum và record public trong ví dụ nên được đặt ở các file Java riêng trong dự án. Classifier chỉ parse dạng Retry-After là số giây để giữ ví dụ ngắn; adapter production phải hỗ trợ cả dạng HTTP-date.

## 18. Structured logging cho actionable errors

SLF4J 2.x fluent API hỗ trợ key-value fields. Log event nên ghi error code, stage, retry disposition và operator action đã sanitize.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class AiFailureLogger {

    private static final Logger log =
            LoggerFactory.getLogger(AiFailureLogger.class);

    public void logFailure(
            AiFailure failure,
            String runId,
            String caseId,
            String attemptId,
            int attemptNumber,
            int budgetRemaining) {

        var builder = log.atLevel(toSlf4jLevel(failure.severity()))
                .addKeyValue("event.name", "ai.operation.failed")
                .addKeyValue("event.version", 1)
                .addKeyValue("error.code", failure.code())
                .addKeyValue("error.category", failure.category())
                .addKeyValue("error.stage", failure.stage())
                .addKeyValue("error.retry_disposition",
                        failure.retryDisposition().name())
                .addKeyValue("error.safe_message", failure.safeMessage())
                .addKeyValue("error.operator_action",
                        failure.operatorAction())
                .addKeyValue("error.owner", failure.owner())
                .addKeyValue("run.id", runId)
                .addKeyValue("case.id", caseId)
                .addKeyValue("attempt.id", attemptId)
                .addKeyValue("attempt.number", attemptNumber)
                .addKeyValue("retry.budget_remaining", budgetRemaining);

        if (failure.retryAfter() != null) {
            builder.addKeyValue(
                    "retry.after_ms",
                    failure.retryAfter().toMillis());
        }

        builder.log("AI operation failed");
    }

    private org.slf4j.event.Level toSlf4jLevel(
            FailureSeverity severity) {
        return switch (severity) {
            case INFO -> org.slf4j.event.Level.INFO;
            case WARN -> org.slf4j.event.Level.WARN;
            case ERROR, CRITICAL -> org.slf4j.event.Level.ERROR;
        };
    }
}
~~~

Ví dụ không truyền raw exception vào logger. Nếu cần stack trace để debug unexpected exception, dùng sink có quyền phù hợp và sanitizer kiểm tra exception messages/causes. Không log API headers, request body hoặc secret.

### 18.1. Một event, một quyết định

Log một event khi classifier và retry coordinator đã đưa ra quyết định. Nếu cùng exception bị log ở HTTP client, service, controller và global handler, một sự cố có thể tạo bốn alert. Các tầng có thể enrich context nhưng chỉ boundary chịu trách nhiệm xử lý nên phát actionable error event chính.

### 18.2. User-facing message khác operator action

Người dùng có thể chỉ cần biết “Yêu cầu hiện chưa hoàn tất; vui lòng thử lại sau”. Operator cần biết “Provider trả 429; đợi Retry-After, kiểm quota và retry budget”. Không trả stack trace hoặc internal hostnames cho người dùng.

## 19. Configuration errors và validation failures

Lỗi cấu hình thường xuất hiện khi startup hoặc lúc refresh. Cần chỉ ra property key/scope và cách sửa mà không lộ giá trị bí mật.

Ví dụ:

~~~json
{
  "eventName": "ai.configuration.rejected",
  "eventVersion": 1,
  "payload": {
    "configChangeId": "change-91",
    "configSnapshotCandidate": "cfg-v9-candidate",
    "validationStatus": "REJECTED",
    "errorCode": "AI_CONFIGURATION_INVALID",
    "invalidKeys": [
      "app.ai.retrieval-top-k",
      "app.ai.model"
    ],
    "safeReason": "retrieval-top-k must be positive and model must be configured",
    "operatorAction": "Correct the typed configuration and rerun validation"
  }
}
~~~

### 19.1. Fail fast với config bắt buộc

Nếu model, provider, corpus version hoặc rubric là bắt buộc, validate trước khi nhận traffic. Không âm thầm fallback sang model mặc định vì sẽ làm thay đổi kết quả evaluation mà không có provenance.

### 19.2. Không log invalid secret values

Nếu secret reference không resolve, log logical key, secret manager, version/reference và error code. Không log giá trị nhận được, kể cả giá trị có vẻ đã bị mask một phần.

### 19.3. Config drift

So sánh desired snapshot với effective snapshot theo field đã allowlist. Khi drift được phát hiện, ghi event có expected/actual version refs, scope, detection time và severity. Không dump toàn bộ config để chứng minh drift.

## 20. Business event và error event có thể cùng xuất hiện

Một workflow có thể tạo business event và diagnostic/error event khác nhau.

Ví dụ provider timeout trong một attempt:

1. ai.model.call.failed: diagnostic error với provider code, duration và retry disposition.
2. evaluation.case.retry_scheduled: business event khi scheduler đã thực sự lên lịch attempt tiếp theo.
3. evaluation.case.completed: business event sau khi case có kết quả cuối.
4. evaluation.verdict.recorded: business event khi verdict được lưu.
5. evaluation.run.completed: business event khi toàn run hoàn tất.

Không phát retry_scheduled chỉ vì classifier nói lỗi có thể retry. Phải đợi scheduler ghi nhận lịch retry. Nếu budget hết, phát event retry_exhausted hoặc case execution failed theo domain contract.

### 20.1. Một lỗi có thể không làm business operation thất bại

Model call đầu tiên có thể timeout nhưng retry thứ hai thành công. Run cuối cùng vẫn COMPLETED. Giữ attempt failure history và run completion history; không xóa error event đầu tiên.

### 20.2. Một business event có thể không có error log

Run hoàn tất bình thường vẫn cần business event nếu consumer cần biết. Không ép mọi event thành log ERROR/INFO dựa vào severity; event stream và logging level phục vụ hai mục đích khác nhau.

## 21. Audit event và hành động nhạy cảm

Một số hành động cần bằng chứng về actor và authorization:

- Ai kích hoạt prompt/model version?
- Ai thay đổi tool authorization policy?
- Ai truy cập raw evidence?
- Ai phê duyệt report cho release?
- Ai yêu cầu retention deletion hoặc rollback?

Audit event nên chứa actor reference, action, target, policy/version, decision, timestamp và change/approval reference. Dùng identity ID đã được hệ thống quản lý; không cần đưa email cá nhân hoặc raw identity token vào log.

### 21.1. Audit store khác operational log

Operational logs có thể sampling/retention ngắn. Audit events thường cần integrity, access control và retention theo policy riêng. Không tuyên bố application log là audit trail đầy đủ nếu chưa có durability và tamper controls.

### 21.2. Append-only và correction event

Không sửa event lịch sử để thay quyết định cũ. Nếu phát hiện sai, tạo correction/reversal event trỏ event trước và ghi lý do/actor. Consumer có thể xây current view từ history nhưng lịch sử vẫn giữ nguyên.

## 22. Correlation với trace, span và evidence

Business/error/config events cần nối được với telemetry và evidence liên quan.

Các field có thể dùng:

- run.id, case.id, attempt.id cho correlation nghiệp vụ.
- model.call.id, tool.call.id, evaluation.id cho invocation cụ thể.
- trace.id/span.id lấy từ OpenTelemetry context.
- evidence.ref cho artifact đã được persist.
- config.snapshot.id cho cấu hình hiệu lực.
- event.id/causation.id/correlation.id cho event workflow.

### 22.1. Không tự tạo trace ID

Trace ID phải đến từ tracing context đang hoạt động hoặc instrumentation đã cấu hình. Event được tạo ngoài trace có thể không có trace ID. Để field vắng mặt hoặc ghi trace status phù hợp; không tạo chuỗi ngẫu nhiên và gọi đó là trace ID.

### 22.2. Span ID là phạm vi operation

Một trace thường chứa nhiều spans. Model call, retrieval và tool operation có thể nằm ở các spans khác nhau. Log event nên gắn span đang bao quanh đúng operation nếu có. Không copy root span ID vào tất cả event nếu nó làm mất khả năng xác định stage cụ thể.

### 22.3. Trace không thay event history

Trace có thể bị sampling hoặc hết retention. Business event/outbox cần durability theo contract; log event và evidence refs có retention riêng. Khi trace không có, vẫn phải truy được trạng thái nghiệp vụ.

### 22.4. Evidence reference không phải bearer URL

Dùng opaque artifact ID hoặc reference được kiểm quyền khi truy cập. Không log signed URL có token dài hạn. Người xem report phải được authorization ở thời điểm mở evidence.

## 23. Bảo vệ dữ liệu trong business/config/error events

Event payload có thể bị nhân bản sang broker, consumer, search index và archive. Chỉ đưa dữ liệu cần thiết.

| Dữ liệu | Chính sách |
| --- | --- |
| Prompt/answer/context raw | Secure evidence store nếu được phép; không log mặc định |
| API keys/passwords/bearer tokens | Tuyệt đối không ghi |
| Secret values | Không ghi; chỉ secret reference/version |
| Tool arguments | Allowlist hoặc redacted reference |
| User identity | Pseudonymized reference theo policy |
| Document IDs | Đánh giá sensitivity/tenant exposure |
| Error code/stage/retry disposition | Nên ghi |
| Config version/fingerprint | Nên ghi nếu không chứa secret-derived data |
| Approval/actor reference | Ghi theo audit policy |
| Evidence reference | Opaque reference có access control |

### 23.1. Allowlist theo event type

Không dùng một event DTO khổng lồ cho mọi loại sự kiện. Prompt event, tool event, config event và error event có trường hợp lệ khác nhau. Typed DTO giúp review privacy và schema dễ hơn.

### 23.2. Không serialize exception hoặc config object nguyên trạng

Gọi toString() trên exception/config object có thể đưa secrets, URLs hoặc raw payload vào message. Chuyển thành safe error record và config snapshot allowlist trước khi serialize.

### 23.3. Retention theo mục đích

Business history, operational log, config audit và raw evidence có thể có retention khác nhau. Khi evidence hết hạn, event có thể giữ trạng thái EXPIRED nếu policy cho phép; không giữ payload raw hoặc token reference nhằm né yêu cầu xóa.

## 24. Java: business event envelope và outbox record

Một model tối thiểu:

~~~java
import java.time.Instant;
import java.util.Map;
import java.util.Objects;

public record BusinessEventEnvelope(
        String eventId,
        String eventName,
        int eventVersion,
        Instant occurredAt,
        String producer,
        String subjectType,
        String subjectId,
        String correlationId,
        String causationId,
        String traceId,
        String spanId,
        Map<String, Object> payload) {

    public BusinessEventEnvelope {
        Objects.requireNonNull(eventId);
        Objects.requireNonNull(eventName);
        Objects.requireNonNull(occurredAt);
        Objects.requireNonNull(producer);
        Objects.requireNonNull(subjectType);
        Objects.requireNonNull(subjectId);
        if (eventVersion < 1) {
            throw new IllegalArgumentException("eventVersion must be >= 1");
        }
        payload = Map.copyOf(payload);
    }
}
~~~

Map.copyOf tạo shallow immutable copy; payload lồng nhau vẫn cần immutable/canonical serialization trong implementation thật. Schema validation phải được thực hiện trước khi ghi outbox.

### 24.1. Repository contract cho outbox

~~~java
public interface OutboxWriter {
    void append(BusinessEventEnvelope event);
}
~~~

Service gọi OutboxWriter trong cùng transaction với cập nhật domain state. Adapter persistence chịu trách nhiệm serialize schema version đã validate và lưu event ID duy nhất.

### 24.2. Transactional service minh họa

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class EvaluationCompletionService {

    private final EvaluationRunRepository runs;
    private final OutboxWriter outbox;

    public EvaluationCompletionService(
            EvaluationRunRepository runs,
            OutboxWriter outbox) {
        this.runs = runs;
        this.outbox = outbox;
    }

    @Transactional
    public void complete(
            String runId,
            String reportRef,
            int completedCases,
            BusinessEventEnvelope event) {

        var run = runs.getRequired(runId);
        run.markCompleted(reportRef, completedCases);
        runs.save(run);

        // Persist the event in the same transaction as the state change.
        outbox.append(event);
    }
}
~~~

Repository và outbox adapter là abstraction của ví dụ. Không publish trực tiếp ra broker bên trong transaction này. Dispatcher sẽ publish sau commit.

## 25. Java: consumer idempotency

Consumer cần ghi nhận event ID đã xử lý trong cùng transaction với side effect nội bộ.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class EvaluationReportConsumer {

    private final ProcessedEventRepository processed;
    private final ReportProjectionRepository reports;

    public EvaluationReportConsumer(
            ProcessedEventRepository processed,
            ReportProjectionRepository reports) {
        this.processed = processed;
        this.reports = reports;
    }

    @Transactional
    public void onRunCompleted(BusinessEventEnvelope event) {
        if (processed.exists(event.eventId())) {
            return;
        }

        String runId = event.subjectId();
        reports.markCompleted(runId, event.payload());

        processed.insert(event.eventId());
    }
}
~~~

Trong hệ thống thực, uniqueness constraint trên event ID là lớp bảo vệ cuối cùng trước concurrent duplicate delivery. Kiểm tra tồn tại rồi insert riêng lẻ có race condition; dùng insert-on-conflict/unique constraint và xử lý duplicate key trong transaction.

## 26. JUnit: kiểm error classification và event contract

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import org.junit.jupiter.api.Test;

class ProviderFailureClassifierTest {

    private final ProviderFailureClassifier classifier =
            new ProviderFailureClassifier();

    @Test
    void rateLimitUsesRetryAfterDisposition() {
        var failure = classifier.classify(
                new ProviderFailureDetails(
                        429, "rate_limited", true, false, "2"));

        assertEquals("AI_PROVIDER_RATE_LIMITED", failure.code());
        assertEquals(
                RetryDisposition.AFTER_RETRY_AFTER,
                failure.retryDisposition());
        assertEquals(Duration.ofSeconds(2), failure.retryAfter());
    }

    @Test
    void authenticationFailureIsNeverRetried() {
        var failure = classifier.classify(
                new ProviderFailureDetails(
                        401, "unauthorized", true, false, null));

        assertEquals(
                RetryDisposition.NEVER,
                failure.retryDisposition());
        assertEquals(FailureSeverity.ERROR, failure.severity());
    }

    @Test
    void sideEffectTimeoutRequiresReconciliation() {
        var failure = classifier.classify(
                new ProviderFailureDetails(
                        null, null, true, true, null));

        assertEquals(
                RetryDisposition.RECONCILE_FIRST,
                failure.retryDisposition());
    }

    @Test
    void negativeRetryAfterIsNeverAccepted() {
        var failure = classifier.classify(
                new ProviderFailureDetails(
                        429, "rate_limited", true, false, "-1"));

        assertNull(failure.retryAfter());
    }
}
~~~

Các test kiểm classification minh họa. Integration tests cần xác nhận provider adapter đọc status/header thực tế, outbox insert cùng transaction, dispatcher publish/ack, consumer deduplicate và log encoder serialize đúng field.

### 26.1. Kiểm event payload không chứa secrets

Test contract nên serialize event DTO mẫu và assert không có field/giá trị nhạy cảm. Đừng chỉ kiểm một regex; hãy kiểm schema allowlist và kiểm soát nơi raw data được tạo.

### 26.2. Kiểm outbox rollback

Một integration test nên làm transaction thất bại sau khi domain state được cập nhật trong memory và xác nhận cả domain row lẫn outbox row rollback. Đây là bằng chứng outbox writer tham gia đúng transaction manager.

## 27. Alert và operator workflow

Actionable error chỉ hữu ích khi event được nối với quy trình xử lý.

Một error event nên giúp hệ thống alert xác định:

- Severity/impact.
- Error code và stage.
- Provider/model/tool dependency.
- Số lần xảy ra và phạm vi affected runs/cases.
- Retryability và retry budget.
- Owner/team.
- Operator action hoặc runbook reference.
- First seen/last seen và recovery state.

### 27.1. Không alert theo mọi log ERROR

Một evaluation batch có thể có nhiều case quality FAIL theo chủ đích. Alert vận hành nên dựa vào error category, rate, impact, SLO và persistence/integrity failures. Dùng metric counter/histogram để phát hiện xu hướng; log cung cấp chi tiết cho incident.

### 27.2. Alert deduplication

Dùng error code, service, provider, environment và incident fingerprint để gộp alert lặp. Không dùng raw user/case ID làm alert group key cho hàng nghìn case độc lập nếu không cần.

### 27.3. Recovery event

Khi dependency phục hồi hoặc config được sửa, ghi recovery/config applied event và đóng incident theo quy trình. Không xóa error history cũ.

### 27.4. Error budget và evaluation quality gate

Technical SLO (availability/latency) và quality gate (factual correctness/relevance/tool correctness) có thể cùng chặn release nhưng là hai policy khác nhau. Report cần tách technical errors khỏi quality FAIL/NOT_EVALUATED để không làm sai denominator.

## 28. Điều tra một incident từ business/config/error events

Ví dụ factual correctness giảm sau một model rollout.

1. Mở evaluation.run.completed để xác định run, dataset snapshot và report.
2. Lọc evaluation.verdict.recorded có status FAIL.
3. Mở case/attempt IDs và đối chiếu prompt/model/config snapshot IDs.
4. Tìm ai.configuration.changed và prompt.version.activated trong thời điểm rollout.
5. Xác nhận event APPLIED và effective snapshot thực sự được run sử dụng.
6. Mở retrieval/model events và traces để xác định stage.
7. Mở evidence refs cho effective context, answer và reference facts.
8. Kiểm error events: timeout, rate limit, malformed response hoặc persistence failures.
9. So sánh với baseline run dùng snapshot trước.
10. Ghi root cause đã xác minh, corrective action và event rollback nếu cần.

### 28.1. Ví dụ timeline

| Thời điểm | Event | Ý nghĩa |
| --- | --- | --- |
| 10:00 | ai.configuration.loaded | Service khởi động với cfg-v7 |
| 10:15 | ai.configuration.changed | Config change yêu cầu cfg-v8 |
| 10:16 | ai.configuration.applied | Runtime xác nhận cfg-v8 hiệu lực |
| 10:20 | evaluation.run.started | Run candidate-v5 bắt đầu với cfg-v8 |
| 10:22 | ai.operation.failed | Provider 429 ở một attempt |
| 10:22 | evaluation.case.retry_scheduled | Scheduler lên lịch retry |
| 10:25 | evaluation.verdict.recorded | Case có factual FAIL |
| 10:30 | evaluation.run.completed | Report được tạo |

Timeline minh họa; khi điều tra phải dùng timestamp/event IDs thực tế và xem xét clock skew. Không suy ra config gây lỗi chỉ vì config event đứng trước regression.

### 28.2. Xác định hành động tiếp theo

Nếu error là 429, xem quota, Retry-After và concurrency. Nếu config invalid, rollback hoặc sửa config rồi validate. Nếu retrieval empty, kiểm query/filter/corpus. Nếu evidence persistence fail, giữ report ở trạng thái incomplete và xử lý kho lưu trữ. Nếu tool unknown outcome, reconcile backend operation trước retry.

## 29. Những sai lầm thường gặp

**Dùng log message làm business event.** Log có thể mất, bị sampling và không có contract cho consumer.

**Publish event trước khi transaction commit.** Consumer có thể thấy trạng thái chưa tồn tại.

**Dùng ApplicationEventPublisher như durable broker.** In-memory event không bảo đảm replay sau crash.

**Ghi event completed trước khi thao tác hoàn tất.** Tạo lịch sử nghiệp vụ sai.

**Dùng exception message làm error code.** Message không ổn định và có thể chứa secret.

**Gộp quality FAIL vào technical ERROR.** Làm sai alert và metric denominator.

**Retry mọi RuntimeException.** Có thể lặp side effect hoặc che lỗi cấu hình.

**Coi timeout là chắc chắn thất bại.** Backend có thể đã commit; cần unknown outcome và reconciliation.

**Dump toàn bộ Spring Environment.** Có nguy cơ lộ credentials và secrets.

**Hash secret để chứng minh rotation.** Có thể tạo oracle kiểm tra secret; dùng secret reference/version.

**Chỉ log desired config.** Không biết effective configuration sau precedence.

**Ghi old/new config values không redaction.** Có thể lộ secret hoặc dữ liệu nhạy cảm.

**Không version event schema.** Consumer diễn giải sai payload sau deploy.

**Không deduplicate consumer.** Outbox at-least-once có thể xử lý event nhiều lần.

**Không ghi recovery event.** Incident vẫn khó đóng và khó biết thời điểm phục hồi.

**Alert theo mọi ERROR log.** Quality test failures bình thường có thể tạo alert noise.

## 30. Bài thực hành: ghi business, config và actionable error events

**Bối cảnh:** một evaluation service Spring AI chạy RAG, model calls và tool getOrderStatus. Prompt/model có thể được rollout runtime. Provider đôi khi trả 429/timeout. Team cần audit cấu hình, theo dõi trạng thái run và hướng dẫn xử lý lỗi.

### Phần A — Định nghĩa event catalog

Tạo schema cho:

- evaluation.run.started/completed
- evaluation.case.completed
- evaluation.verdict.recorded
- ai.configuration.loaded/changed/applied/rejected
- ai.operation.failed
- ai.retry.scheduled/exhausted
- tool.operation.reconciled

Mỗi schema có event ID, version, timestamp, producer, subject, correlation và payload allowlist.

**Đầu ra:** event catalog và JSON examples.

### Phần B — Ghi business lifecycle

Tạo service cập nhật run state và ghi outbox event trong cùng transaction. Thêm dispatcher publish sau commit. Consumer deduplicate theo event ID.

**Đầu ra:** transactional outbox và consumer idempotency test.

### Phần C — Ghi configuration snapshot

Tạo typed configuration properties cho provider/model/prompt/corpus/rubric. Log startup snapshot và config change event. Ghi desired/effective versions, changed keys và source summary. Không log secrets.

**Đầu ra:** configuration snapshot, fingerprint và redaction tests.

### Phần D — Chuẩn hóa actionable errors

Định nghĩa error codes, severity, stage, retry disposition, operator action và owner. Implement provider adapter cho 400/401/403/429/5xx/timeout. Phân biệt retryable với reconcile-first.

**Đầu ra:** error classifier và JUnit tests.

### Phần E — Nối telemetry và evidence

Gắn run/case/attempt, trace/span IDs thực tế, config snapshot ID và evidence refs. Không tạo trace ID giả; không đưa raw payload vào business event.

**Đầu ra:** incident timeline có thể drill-down.

### Phần F — Diễn tập incident

Mô phỏng config rollout gây regression, provider 429, timeout ở tool side effect, evidence persistence failure và rollback. Xác nhận operator action phù hợp, alert không trùng và recovery event được ghi.

**Đầu ra:** runbook, event history và report điều tra.

### Checklist nghiệm thu

- [ ] Phân biệt business event, diagnostic log, config event, error event và audit event.
- [ ] Event envelope có ID, version, timestamp và producer.
- [ ] Business event chỉ phát sau khi sự thật nghiệp vụ đã xảy ra.
- [ ] Domain state và outbox row được commit cùng transaction.
- [ ] Consumer deduplicate theo event ID.
- [ ] Event ordering/aggregate version được xác định khi cần.
- [ ] Run/case/attempt IDs được giữ xuyên workflow.
- [ ] Config snapshot mô tả effective configuration.
- [ ] Config event ghi changed keys, actor/scope và apply status.
- [ ] Secrets chỉ có reference/version, không có raw values.
- [ ] Error code ổn định và không lấy từ exception message.
- [ ] Severity tách khỏi retry disposition.
- [ ] Quality FAIL tách khỏi technical failure.
- [ ] Timeout side effect có unknown outcome/reconciliation.
- [ ] Retry-After và retry budget được ghi đúng.
- [ ] Operator action và owner có thể hiểu và thực hiện.
- [ ] Trace/span IDs lấy từ tracing context thật.
- [ ] Evidence refs có access control và retention.
- [ ] Consumer/dispatcher có metrics và recovery handling.
- [ ] JUnit/integration tests kiểm schema, transaction và idempotency.

### Câu hỏi tự kiểm tra

1. Business event khác diagnostic log như thế nào?
2. Vì sao ApplicationEventPublisher không phải durable event broker?
3. Transactional outbox giải quyết dual-write ra sao?
4. Vì sao outbox thường cần at-least-once và consumer idempotency?
5. occurredAt khác recordedAt như thế nào?
6. Khi nào event schema cần tăng version?
7. Desired config khác effective config ở đâu?
8. Vì sao không được dump toàn bộ Spring Environment?
9. Configuration fingerprint có thể thay thế snapshot không?
10. Vì sao secret value không nên được hash để tạo fingerprint?
11. Một model timeout có luôn retry được không?
12. Khi nào tool timeout cần RECONCILE_FIRST?
13. Severity khác retry disposition như thế nào?
14. Vì sao quality FAIL không phải technical ERROR?
15. Một actionable error cần những trường nào để operator biết phải làm gì?
16. Khi nào config change được xem là APPLIED?
17. Vì sao rollback phải là event mới?
18. Làm sao liên kết business event với trace/span và evidence?
19. Vì sao không dùng raw exception message làm error code?
20. Làm sao phân biệt lỗi provider 429 với quota exhausted?

## 31. Tổng kết

Ghi sự kiện nghiệp vụ, cấu hình và lỗi có thể xử lý giúp ứng dụng Spring AI tạo ra lịch sử có ý nghĩa cho cả developer, evaluator và operator. Business event mô tả trạng thái thực sự đã xảy ra; configuration event ghi lại snapshot hiệu lực và thay đổi; actionable error cho biết lỗi, mức độ ảnh hưởng, retry disposition, owner và bước xử lý.

Business event cần contract ổn định, event ID, schema version và durability theo yêu cầu. Với sự kiện quan trọng, transactional outbox ghi domain state và event trong cùng transaction; dispatcher publish sau commit; consumer xử lý idempotent vì delivery có thể lặp. ApplicationEventPublisher hữu ích cho local in-memory events nhưng không tự bảo đảm durability.

Configuration snapshot phải phản ánh giá trị hiệu lực sau precedence, validation và runtime overrides. Chỉ ghi field đã allowlist, version/fingerprint và secret references; không dump Environment hoặc secret values. Error taxonomy cần tách severity, retryability, business outcome và quality verdict. Timeout của side effect có thể tạo unknown outcome nên phải đối soát trước retry.

Khi business/config/error events liên kết với run/case/attempt IDs, trace/span IDs thật và evidence references có quyền truy cập, đội vận hành có thể xác định điều gì đã xảy ra, cấu hình nào có hiệu lực và bước xử lý nào tiếp theo. Log khi đó trở thành một phần của quy trình vận hành có thể kiểm tra, thay vì chỉ là các dòng thông báo rời rạc.

### Tài liệu tham khảo

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Framework — Application Events and Listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
- [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/)
- [Spring AI — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [SLF4J — Manual](https://www.slf4j.org/manual.html)
- [Logback — Architecture](https://logback.qos.ch/manual/architecture.html)
- [Micrometer — Observation](https://docs.micrometer.io/micrometer/reference/observation.html)
- [OpenTelemetry — Logs](https://opentelemetry.io/docs/specs/otel/logs/)
- [OpenTelemetry — Trace API](https://opentelemetry.io/docs/specs/otel/trace/api/)
- [JUnit 5 — User Guide](https://junit.org/junit5/docs/current/user-guide/)
