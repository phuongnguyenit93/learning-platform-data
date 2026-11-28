# Kiểm soát nội dung truy vấn và tài liệu trong telemetry

> **Chương:** Quan sát VectorStore  
> **Module:** SPRING_AI_EVALUATION_OBSERVABILITY — đánh giá chất lượng ứng dụng Spring AI bằng tập dữ liệu, tiêu chí relevance, fact checking và kiểm thử luồng RAG hoặc gọi công cụ; đồng thời đo metrics, traces, chi phí và độ trễ để phát hiện nguyên nhân suy giảm qua từng phiên bản prompt, model và pipeline.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Nhận diện dữ liệu nhạy cảm có thể xuất hiện trong query, filter, document, prompt, tool arguments và exception của một pipeline Spring AI.
2. Phân biệt metrics, traces và logs; hiểu vì sao high-cardinality attributes không đồng nghĩa với dữ liệu an toàn.
3. Thiết kế chính sách thu thập telemetry theo phân loại dữ liệu, mục đích sử dụng, quyền truy cập và thời hạn lưu.
4. Kiểm soát các thuộc tính VectorStore như **db.vector.query.content**, **db.vector.query.filter** và **db.vector.query.response.documents**.
5. Áp dụng allowlist, redaction, pseudonymization, data minimization và kiểm thử rò rỉ trước khi export.
6. Viết service Java dùng Spring AI/Micrometer để quan sát thao tác tìm kiếm mà không ghi raw query, raw filter hay nội dung tài liệu vào metrics.
7. Xây dựng quy trình điều tra sự cố và đánh giá chất lượng RAG vẫn giữ được evidence cần thiết mà không thu thập dư thừa dữ liệu nhạy cảm.

## 1. Vì sao telemetry của VectorStore có thể làm lộ dữ liệu?

Một truy vấn RAG có thể chứa thông tin riêng tư ngay từ câu hỏi:

~~~text
Tìm hợp đồng của Nguyễn Văn A, số 0098-1234,
và cho biết số tài khoản nhận tiền hoàn lại.
~~~

Ứng dụng chuyển câu hỏi qua embedding, tìm tài liệu trong VectorStore, ghép context vào prompt và gọi ChatModel. Nếu instrumentation tự động ghi nội dung query, filter hoặc documents trả về vào trace, những dữ liệu này có thể được gửi tới collector/APM bên ngoài ứng dụng.

Một trace tưởng như chỉ phục vụ debug có thể vô tình chứa:

- Tên, email, số điện thoại, địa chỉ hoặc mã định danh cá nhân.
- Số hợp đồng, thông tin tài khoản, giao dịch và dữ liệu khách hàng.
- Nội dung nội bộ, tài liệu chưa công bố, chính sách hoặc mã nguồn.
- Query text, metadata filter, document content, prompt và model response.
- Tool arguments, exception messages, stack traces hoặc URL có token.
- API key, access token, connection string hoặc secret nếu lỗi bị ghi nguyên văn.

**Telemetry là một đường đi của dữ liệu ứng dụng.** Khi query và document đi vào trace/log, chúng phải chịu cùng yêu cầu về phân loại, quyền truy cập, lưu trữ, chia sẻ và xóa dữ liệu như những hệ thống khác.

### 1.1. Ví dụ đường đi của dữ liệu

~~~mermaid
flowchart TD
  A["User question"] --> B["Spring AI SearchRequest"]
  B --> C["EmbeddingModel"]
  C --> D["VectorStore query"]
  D --> E["Retrieved documents"]
  E --> F["Prompt assembly"]
  F --> G["ChatModel"]
  G --> H["Answer"]
  B -.-> T["Observation / trace"]
  D -.-> T
  E -.-> T
  F -.-> T
  G -.-> T
  T --> R["Collector / APM / log store"]
  R --> U["Dashboard, search, export, retention"]
  U --> X["Người có quyền hoặc người được cấp quyền"]
~~~

Nếu trace giữ raw query hoặc toàn bộ documents, dữ liệu có thể đi xa hơn phạm vi ban đầu của VectorStore: collector, vendor APM, dashboard, alert payload, bản export, ticket hỗ trợ và bản sao lưu. Vì vậy cần quyết định **trước khi capture** trường nào được phép xuất.

### 1.2. Quan sát được nhiều hơn điều cần thiết

Một đội vận hành thường cần biết:

- Query thuộc store role nào và operation có thành công không?
- Backend mất bao lâu, trả bao nhiêu document?
- Filter profile/version nào được sử dụng?
- Lỗi thuộc nhóm timeout, rate limit hay cấu hình?
- Một evaluation run có đủ evidence để chấm không?

Những câu hỏi này không nhất thiết cần raw query, raw filter hoặc nội dung tài liệu. Hãy ưu tiên metadata có mục đích rõ ràng, rồi chỉ mở evidence chi tiết khi có lý do và quyền truy cập.

## 2. Phân loại dữ liệu trước khi thiết kế telemetry

Không nên phân loại dữ liệu chỉ dựa trên việc nó có phải high-cardinality hay không. Một trường có vài giá trị vẫn có thể nhạy cảm; một trường có nhiều giá trị không nhất thiết là PII, nhưng có thể gây rủi ro chi phí và liên kết danh tính.

### 2.1. Bốn nhóm dữ liệu tham khảo

| Nhóm | Ví dụ | Cách xử lý telemetry |
|---|---|---|
| **Public / operational** | Tên operation, backend family, trạng thái kỹ thuật | Có thể dùng làm metric labels nếu tập giá trị ổn định |
| **Internal** | Store role, retrieval profile, index version, pipeline version | Dùng theo allowlist; kiểm soát số phiên bản và quyền xem |
| **Confidential / personal** | Query, raw filter, tenant/user ID, document text, prompt, response | Không thu thập mặc định; redaction hoặc lưu ở evidence store có ACL nếu thực sự cần |
| **Secrets / credentials** | API key, bearer token, password, connection string, session cookie | Không đưa vào telemetry; phải loại bỏ trước export và xử lý sự cố nếu đã lộ |

Đây là taxonomy gợi ý cho ứng dụng; tổ chức cần ánh xạ vào chính sách phân loại dữ liệu thực tế, nghĩa vụ pháp lý và hợp đồng với nhà cung cấp.

### 2.2. Phân biệt nội dung, định danh và cấu hình

| Trường | Có thể nhạy cảm? | Cardinality thường gặp | Gợi ý |
|---|---|---|---|
| **db.operation.name** | Thấp | Thấp | Giữ lại cho metrics |
| **db.system** | Thấp | Thấp | Giữ backend family đã chuẩn hóa |
| **app.store.role** | Thường thấp | Thấp nếu allowlist | Giữ role logic hữu hạn |
| **db.vector.query.top_k** | Thường thấp | Có thể tăng nếu tự do | Có thể giữ trong trace; metric nên dùng bucket/profile |
| **db.vector.query.similarity_threshold** | Thường thấp | Có thể tăng nếu nhiều giá trị | Giữ profile/version hoặc giá trị đã kiểm soát |
| **db.vector.query.content** | Có thể cao | Cao | Không xuất raw query mặc định |
| **db.vector.query.filter** | Có thể cao | Cao | Chỉ ghi filter profile/version; bảo vệ raw expression |
| **db.vector.query.response.documents** | Rất có thể cao | Rất cao | Tắt capture nội dung mặc định |
| **db.collection.name / db.namespace** | Có thể tiết lộ khách hàng/dự án | Có thể cao | Chỉ giữ khi có mục đích và ACL phù hợp |
| **traceId / runId** | Có thể liên kết một lượt chạy | Cao | Có thể dùng làm correlation reference trong trace/evidence; không làm metric label |

**High cardinality không đồng nghĩa với confidential.** Cardinality là thuộc tính về số lượng giá trị; sensitivity là thuộc tính về tác động nếu dữ liệu bị tiết lộ. Cần đánh giá hai chiều riêng.

### 2.3. Xác định mục đích cho từng trường

Trước khi thêm một attribute vào telemetry, trả lời:

1. Câu hỏi vận hành hoặc đánh giá nào cần trường này?
2. Có trường ít nhạy cảm hơn trả lời cùng câu hỏi không?
3. Trường sẽ đi vào metric, span, log hay evidence store?
4. Ai có thể xem, tìm kiếm, tải xuống hoặc chia sẻ?
5. Cần giữ trong bao lâu?
6. Nếu trường bị lộ, tác động tới người dùng/tổ chức là gì?
7. Có thể kiểm thử rằng trường đã được redaction đúng không?

Nếu không có mục đích cụ thể, không thu thập trường đó.

## 3. Metrics, traces và logs có rủi ro khác nhau

### 3.1. Metrics: tổng hợp, cardinality phải thấp

Metrics thường được lưu thành time series. Một tập nhãn có nhiều giá trị sẽ tạo nhiều series, tăng RAM, dung lượng, chi phí truy vấn và độ phức tạp dashboard.

Ví dụ metric an toàn hơn:

~~~text
app.vector.query.duration
  store.role = policy-search
  backend.family = pg_vector
  outcome = success
~~~

Không dùng các label:

~~~text
query = "Hợp đồng của Nguyễn Văn A..."
tenant.id = "customer-94821"
document.id = "private-contract-001"
filter = "tenant == 'customer-94821'"
~~~

Metric labels thường tồn tại lâu và có thể được nhiều người dùng chung. Raw query/filter/ID vừa gây cardinality lớn vừa tạo rủi ro tiết lộ dữ liệu.

### 3.2. Traces: nhiều ngữ cảnh hơn nhưng không phải kho chứa payload

Trace hữu ích để liên kết các span:

~~~text
app.rag.answer
  ├── app.rag.retrieve
  │     └── db.vector.client.operation [query]
  ├── app.rag.prompt_assembly
  └── ChatModel generation
~~~

Các span có thể giữ operation, duration, backend, outcome, model/version và reference đến evidence. Không mặc định đưa raw query, filter, document text, prompt hoặc answer vào span chỉ vì tracing hỗ trợ high-cardinality attributes.

Trace có thể được sample, gửi sang nhiều exporter, lưu ở vendor APM và cho phép tìm kiếm rộng. **Sampling không phải biện pháp bảo vệ dữ liệu**: một trace đã được sample vẫn có thể chứa nguyên văn nội dung nhạy cảm.

### 3.3. Logs: chi tiết hữu ích nhưng dễ bị sao chép

Logs có thể được chuyển tiếp sang nhiều hệ thống, đính kèm vào ticket hoặc tải xuống để hỗ trợ. Tránh log:

- Request/response object đầy đủ.
- Document.toString() hoặc toàn bộ metadata/document content.
- Raw prompt, tool arguments và model response.
- Exception message nguyên văn nếu có thể chứa query, URL hoặc credentials.
- HTTP headers, authorization và cookie.

Nên log một sự kiện có cấu trúc với operation, reason code, store role, duration và một correlation reference ngẫu nhiên nếu cần.

## 4. Các thuộc tính telemetry của Spring AI VectorStore

Spring AI mô tả observation cho operation VectorStore với tên:

~~~text
db.vector.client.operation
~~~

Các thuộc tính operation/backend thường gặp:

| Attribute | Ý nghĩa |
|---|---|
| **db.operation.name** | add, query, delete, upsert tùy thao tác |
| **db.system** | Họ hệ lưu trữ vector |
| **spring.ai.kind** | Loại thành phần Spring AI |
| **db.collection.name** | Collection/index nếu implementation cung cấp |
| **db.namespace** | Namespace nếu backend/implementation hỗ trợ |

Các thuộc tính query có thể chứa dữ liệu cần bảo vệ:

| Attribute | Nội dung | Rủi ro |
|---|---|---|
| **db.vector.query.content** | Nội dung câu truy vấn | Có thể chứa PII, hợp đồng, dữ liệu kinh doanh |
| **db.vector.query.filter** | Biểu thức metadata filter | Có thể chứa tenant, user ID, trạng thái hồ sơ |
| **db.vector.query.top_k** | Số kết quả yêu cầu | Thường ít nhạy cảm, nhưng cần kiểm soát cardinality |
| **db.vector.query.similarity_threshold** | Ngưỡng similarity | Có thể hữu ích để phân tích cấu hình |
| **db.vector.query.response.documents** | Nội dung tài liệu trả về nếu được ghi | Có thể chứa toàn bộ dữ liệu nguồn nhạy cảm |

Việc attribute có xuất hiện hay không phụ thuộc phiên bản Spring AI, VectorStore adapter, cấu hình observations và exporter. Không giả định mọi backend đều cung cấp cùng một tập trường.

### 4.1. Tắt ghi nội dung response mặc định

Spring AI có cấu hình cho việc ghi response của VectorStore observation. Có thể đặt tường minh:

~~~yaml
spring:
  ai:
    vectorstore:
      observations:
        log-query-response: false
~~~

Giữ giá trị **false** trong môi trường thông thường. Property này kiểm soát việc ghi query response documents theo hỗ trợ của phiên bản Spring AI; **không được coi là công tắc tự động xóa mọi query content, filter, prompt, log hoặc custom attributes**.

Trước khi dựa vào property, xác minh tên và hành vi của nó trong đúng phiên bản dependency đang chạy. Kiểm tra trace export sau cấu hình để bảo đảm nội dung response không xuất hiện.

### 4.2. Raw query và filter cần chính sách riêng

Raw query/filter có thể được ghi thành high-cardinality span attributes theo convention hoặc implementation. Đừng suy luận rằng high-cardinality nghĩa là tự động không được export. Nếu ứng dụng không cần raw content để vận hành, hãy:

- Không tự thêm raw query/filter vào custom Observation.
- Chọn instrumentation/convention có thể bỏ hoặc thay thế các field đó nếu phiên bản hỗ trợ.
- Áp dụng redaction processor ở ranh giới telemetry trước khi export ra hệ thống bên ngoài.
- Kiểm thử bằng query/filter giả có chuỗi canary để chắc chắn field không còn trong metric/span/log.

Một collector ở phía sau là lớp phòng vệ bổ sung. Nếu raw content đã được ghi vào application log hoặc exporter khác, chỉ redaction ở một collector không xử lý được các bản sao còn lại.

## 5. Chính sách thu thập: allowlist trước, redaction sau

### 5.1. Allowlist an toàn hơn blocklist đơn thuần

Blocklist cố gắng loại các trường đã biết như password, token, email. Nhưng dữ liệu nhạy cảm có thể nằm trong trường tên bất ngờ như notes, description, query, payload hoặc exception message.

Allowlist xác định trước các trường được phép:

~~~yaml
telemetryPolicy:
  version: vector-telemetry-policy-v2
  defaultAction: DROP
  metrics:
    allow:
      - db.operation.name
      - db.system
      - app.store.role
      - app.operation.outcome
      - app.filter.profile
      - app.environment
  traces:
    allow:
      - db.operation.name
      - db.system
      - app.store.role
      - app.filter.profile
      - app.retrieval.config.version
      - app.error.category
      - app.result.count
      - app.evidence.reference
  deny:
    - db.vector.query.content
    - db.vector.query.filter
    - db.vector.query.response.documents
    - user.id
    - tenant.id
    - authorization
    - cookie
    - api.key
    - access.token
  responseCapture:
    enabled: false
  rawQueryCapture:
    enabled: false
  rawFilterCapture:
    enabled: false
~~~

Đây là policy schema do ứng dụng đề xuất, không phải file cấu hình Spring AI native. Tên field và cơ chế thực thi cần được ánh xạ vào ObservationConvention, filter, exporter processor hoặc logging framework đang dùng.

**Allowlist không miễn trừ việc phân loại dữ liệu.** Một trường có tên app.store.role vẫn cần bảo đảm chỉ chứa các giá trị nội bộ đã duyệt, không cho caller tự đặt chuỗi tùy ý.

### 5.2. Redaction cần xử lý cả giá trị lẫn cấu trúc

Một chính sách redaction tốt nên:

1. Xác định trường được phép giữ.
2. Loại bỏ secret và dữ liệu cá nhân theo policy.
3. Chuẩn hóa error category thay vì lưu exception message.
4. Giới hạn kích thước attribute và số lượng nested fields.
5. Ngăn log injection (newline, control characters, cấu trúc giả).
6. Kiểm soát URL/query parameters và headers.
7. Kiểm tra nội dung tài liệu và tool output, không chỉ tên trường.

Regex đơn giản có thể giúp phát hiện một số email hoặc số điện thoại nhưng không thể chứng minh một đoạn văn đã sạch dữ liệu nhạy cảm. Cần kết hợp schema allowlist, secret scanning, PII detector phù hợp ngôn ngữ, kiểm duyệt theo policy và test fixtures.

### 5.3. Redaction phải xảy ra trước khi dữ liệu rời khỏi vùng tin cậy

Một pipeline tham khảo:

~~~text
Application
  -> safe Observation / structured logging
  -> in-process redaction or approved instrumentation
  -> local collector / gateway
  -> second redaction and validation
  -> telemetry exporter
  -> approved backend with RBAC and retention
~~~

Nếu application gửi raw query tới SaaS collector rồi mới redaction ở dashboard, dữ liệu đã rời khỏi ranh giới tin cậy. Đặt kiểm soát ở phía ứng dụng/in-process hoặc gateway do tổ chức quản lý trước exporter bên ngoài.

## 6. Pseudonymization và correlation an toàn

Đôi khi đội phát triển cần biết nhiều span thuộc cùng một evaluation run hoặc cùng một nhóm dữ liệu mà không cần lưu định danh thật.

### 6.1. Ưu tiên opaque correlation reference

Tạo một runId ngẫu nhiên, không mang thông tin cá nhân:

~~~text
runId = 7e4b9a21-6a13-4a...
traceId = 4f8d...
~~~

Reference này có thể nối trace với evidence store có ACL. Không mã hóa tenant ID bằng Base64 rồi coi là ẩn danh; Base64 chỉ là encoding.

### 6.2. Hash không tự động ẩn danh

Nếu query có ít khả năng biến thể, hash không khóa có thể bị dò bằng dictionary. HMAC với secret được quản lý và luân chuyển key có thể giảm nguy cơ đoán trực tiếp, nhưng kết quả vẫn là dữ liệu giả danh có khả năng liên kết.

Nguyên tắc:

- Không hash raw query để làm metric label.
- Không dùng hash ổn định của email/tenant ID làm nhãn công khai.
- Nếu cần pseudonymous join key, xác định mục đích, quản lý key, thời hạn, quyền truy cập và rủi ro tái nhận dạng.
- Không xem pseudonymization là thay thế authorization, encryption hoặc retention policy.

### 6.3. Không dùng identifier có thể đoán

Các giá trị như số hợp đồng tuần tự, email, username hoặc ID khách hàng có thể bị suy ra từ hash hoặc một phần chuỗi. Correlation ID nên ngẫu nhiên, không tái sử dụng giữa môi trường nếu không cần và không chứa dữ liệu nghiệp vụ.

## 7. Java: quan sát VectorStore mà không ghi raw content

Ví dụ sau minh họa một service Spring AI dùng VectorStore, SearchRequest, ObservationRegistry và MeterRegistry. Service chỉ ghi:

- Store role thuộc danh mục hữu hạn.
- Filter profile đã được policy duyệt.
- Operation outcome.
- Số tài liệu trả về.
- Một version cấu hình có kiểm soát trong span.

Raw query và raw filter vẫn được dùng trong request thực thi, nhưng không được đưa vào custom Observation, metric tags hoặc log.

### 7.1. Policy và cấu hình truy vấn

~~~java
import java.util.Set;

public record SafeRetrievalPolicy(
        int topK,
        double similarityThreshold,
        String filterProfile,
        String trustedFilterExpression,
        String configVersion) {

    private static final Set<String> ALLOWED_FILTER_PROFILES =
            Set.of("public-policy", "tenant-policy", "no-filter");

    public SafeRetrievalPolicy {
        if (topK < 1 || topK > 50) {
            throw new IllegalArgumentException("topK ngoài giới hạn");
        }
        if (!Double.isFinite(similarityThreshold)
                || similarityThreshold < 0
                || similarityThreshold > 1) {
            throw new IllegalArgumentException("threshold không hợp lệ");
        }
        if (!ALLOWED_FILTER_PROFILES.contains(filterProfile)) {
            throw new IllegalArgumentException("filter profile không hợp lệ");
        }
        if (configVersion == null || configVersion.isBlank()) {
            throw new IllegalArgumentException("Thiếu config version");
        }
        if ("no-filter".equals(filterProfile)
                && trustedFilterExpression != null) {
            throw new IllegalArgumentException(
                    "no-filter không được chứa filter expression");
        }
        if (!"no-filter".equals(filterProfile)
                && (trustedFilterExpression == null
                || trustedFilterExpression.isBlank())) {
            throw new IllegalArgumentException("Thiếu filter expression");
        }
    }
}
~~~

trustedFilterExpression phải được tạo bởi tầng policy/security đáng tin cậy từ danh tính đã xác thực. Không nhận raw expression từ prompt, ChatModel hoặc tham số người dùng. Kiểm tra [0,1] chỉ là giả định minh họa cho adapter có thang điểm tương ứng; cần xác minh semantics của backend.

### 7.2. Service tạo observation an toàn

~~~java
import java.util.List;
import java.util.Objects;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.ai.document.Document;
import org.springframework.ai.vectorstore.SearchRequest;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.stereotype.Service;

@Service
public final class SafeVectorSearchService {
    private final VectorStore vectorStore;
    private final ObservationRegistry observations;
    private final Counter querySuccess;
    private final Counter queryError;
    private final DistributionSummary resultCount;
    private final String storeRole;

    public SafeVectorSearchService(
            VectorStore vectorStore,
            ObservationRegistry observations,
            MeterRegistry meters) {
        this.vectorStore = Objects.requireNonNull(vectorStore);
        this.observations = Objects.requireNonNull(observations);
        this.storeRole = "policy-search"; // giá trị từ allowlist cấu hình

        this.querySuccess = Counter.builder("app.vector.query.outcomes")
                .tag("store.role", storeRole)
                .tag("outcome", "success")
                .register(meters);
        this.queryError = Counter.builder("app.vector.query.outcomes")
                .tag("store.role", storeRole)
                .tag("outcome", "error")
                .register(meters);
        this.resultCount = DistributionSummary
                .builder("app.vector.query.result.count")
                .tag("store.role", storeRole)
                .register(meters);
    }

    public List<Document> search(
            String rawQuestion,
            SafeRetrievalPolicy policy) {

        Objects.requireNonNull(rawQuestion);
        Objects.requireNonNull(policy);

        SearchRequest.Builder requestBuilder = SearchRequest.builder()
                .query(rawQuestion)
                .topK(policy.topK())
                .similarityThreshold(policy.similarityThreshold());

        if (policy.trustedFilterExpression() != null) {
            requestBuilder.filterExpression(
                    policy.trustedFilterExpression());
        }
        SearchRequest request = requestBuilder.build();

        Observation observation = Observation.createNotStarted(
                        "app.vector.search", observations)
                .lowCardinalityKeyValue("store.role", storeRole)
                .lowCardinalityKeyValue(
                        "filter.profile", policy.filterProfile())
                .highCardinalityKeyValue(
                        "retrieval.config.version", policy.configVersion());

        observation.start();
        try {
            List<Document> documents = Objects.requireNonNull(
                    vectorStore.similaritySearch(request),
                    "VectorStore trả về null");
            querySuccess.increment();
            resultCount.record(documents.size());
            return documents;
        }
        catch (RuntimeException original) {
            queryError.increment();
            // Chỉ ghi reason code đã chuẩn hóa vào span ứng dụng.
            observation.error(new IllegalStateException(
                    classifyError(original)));
            throw original;
        }
        finally {
            observation.stop();
        }
    }

    private String classifyError(RuntimeException error) {
        // Ví dụ tối giản. Production cần phân loại theo exception type
        // của adapter/provider, không dựa vào message chứa dữ liệu.
        if (error instanceof IllegalArgumentException) {
            return "INVALID_REQUEST";
        }
        return "VECTOR_QUERY_FAILED";
    }
}
~~~

**Các điểm an toàn trong ví dụ:**

- rawQuestion và trustedFilterExpression chỉ được truyền vào SearchRequest; không gắn chúng vào Observation hoặc metrics.
- Metric labels là store.role và outcome, có tập giá trị hữu hạn.
- Span ứng dụng chỉ ghi filter.profile, retrieval.config.version và lỗi đã phân loại.
- Không log Document, request, filter hoặc exception message nguyên văn.
- Không ghi document content trong custom span.

**Giới hạn quan trọng:** Spring AI có thể tạo observation con cho chính VectorStore. Những span framework này có thể chứa query/filter attributes tùy phiên bản và cấu hình. Ví dụ chỉ kiểm soát observation do ứng dụng tự tạo; cần thêm cấu hình/convention/collector redaction và kiểm thử exporter cho span framework.

### 7.3. Vì sao không log exception message?

Một exception có thể chứa:

~~~text
Invalid query for tenant=customer-94821:
filter "email == 'person@example.com'"
~~~

Nếu log nguyên văn hoặc gọi observation.error(original) trong một nơi tự động ghi message/stack trace, dữ liệu nhạy cảm có thể xuất hiện ngoài ý muốn. Hãy giữ reason code hữu hạn trong telemetry thông thường; lưu exception đầy đủ trong log bảo vệ riêng chỉ khi cần, có redaction, ACL và retention rõ ràng.

Không nuốt lỗi chỉ để tránh log. Ứng dụng vẫn phải xử lý/propagate lỗi theo hợp đồng; chính sách telemetry quyết định nội dung được export, không thay đổi semantics của operation.

## 8. Kiểm soát span và collector

### 8.1. Các lớp phòng vệ

| Lớp | Nhiệm vụ | Ví dụ |
|---|---|---|
| Application boundary | Chỉ tạo safe attributes | Không đưa raw query/filter vào custom Observation |
| Spring AI instrumentation | Cấu hình các observation mặc định | Tắt response capture theo property được hỗ trợ |
| Observation convention/filter | Bỏ hoặc thay thế thuộc tính nhạy cảm | Allowlist fields, normalize error |
| Collector/gateway | Kiểm tra và redaction trước export | Xóa raw content attributes |
| Backend APM/log | Phân quyền, encryption, retention, audit | RBAC, restricted search, short retention |
| CI/test | Phát hiện trường nhạy cảm bị export | Canary values và assertion trên captured spans |

Không dựa vào duy nhất một lớp. Nếu custom code sạch nhưng framework span ghi raw query, dữ liệu vẫn có thể rò. Nếu collector sạch nhưng ứng dụng ghi raw query vào file log khác, vẫn có bản sao.

### 8.2. Redaction theo key và allowlist

Ví dụ các key cần loại khỏi span trước export nếu policy không cho phép:

~~~text
db.vector.query.content
db.vector.query.filter
db.vector.query.response.documents
http.request.header.authorization
http.request.header.cookie
enduser.id
user.id
tenant.id
~~~

Tên key cụ thể tùy instrumentation và semantic convention version. Collector transform processor, exporter filter hoặc ObservationFilter có API/cú pháp khác nhau; phải kiểm tra đúng phiên bản trước khi áp dụng. Ưu tiên **xóa field hoàn toàn** khi không cần, thay vì chỉ che một phần nhưng vẫn giữ dữ liệu có thể nhận dạng.

Nếu tổ chức cần lưu raw evidence cho evaluation, lưu ở kho riêng có quyền và retention riêng; không đưa nó vào trace thông thường chỉ vì collector có thể redaction.

### 8.3. Không nhầm sampling với redaction

Sampling quyết định trace nào được giữ. Nó không làm sạch trace được giữ lại. Một chính sách lấy 1% trace vẫn có thể tiết lộ query đầy đủ của 1% request.

Redaction phải áp dụng trước khi export. Sampling có thể giảm dung lượng và chọn trace phục vụ phân tích, nhưng không thay thế phân loại, allowlist hoặc quyền truy cập.

### 8.4. Tránh log injection và payload phình to

Raw document có thể chứa newline, control characters, markup hoặc nội dung được người dùng cố tình tạo để làm sai lệch log viewer. Nếu cần log giá trị đã cho phép:

- Dùng structured logging thay vì nối chuỗi tự do.
- Giới hạn độ dài trường.
- Escape control characters theo format.
- Không render HTML/Markdown từ document như nội dung đáng tin.
- Không lưu toàn bộ payload trong exception message.
- Đặt quota cho số attributes và kích thước span.

## 9. Lưu evidence đánh giá mà không làm lộ dữ liệu trong telemetry

Đánh giá relevance/fact checking cần bằng chứng; điều đó không có nghĩa mọi bằng chứng phải nằm trong trace.

### 9.1. Chia dữ liệu thành hai luồng

~~~mermaid
flowchart TD
  A["RAG request"] --> B["Safe telemetry"]
  A --> C["Evaluation evidence"]
  B --> D["Metrics / traces / logs"]
  D --> E["APM backend: metadata, duration, status"]
  C --> F["Restricted evidence store"]
  F --> G["ACL + encryption + retention"]
  G --> H["Authorized evaluator / reviewer"]
  E --> I["Trace reference"]
  I --> H
~~~

**Safe telemetry** giữ metadata vận hành đã được duyệt. **Evaluation evidence** có thể giữ query, retrieved IDs, provided context, answer và gold labels nếu thật sự cần, nhưng phải có quyền truy cập và mục đích riêng.

### 9.2. Evidence receipt tối thiểu

Một receipt có thể chỉ chứa metadata và reference:

~~~json
{
  "runId": "random-run-reference",
  "traceId": "trace-reference",
  "datasetVersion": "support-rag-v8",
  "pipelineVersion": "rag-pipeline-v7",
  "indexVersion": "policy-index-v5",
  "embeddingModelVersion": "embedding-model-b",
  "promptVersion": "refund-prompt-v6",
  "chatModelVersion": "chat-model-b",
  "storeRole": "policy-search",
  "filterProfile": "tenant-policy",
  "topK": 5,
  "returnedCount": 3,
  "providedDocumentCount": 2,
  "evidenceRef": "restricted://evaluation/runs/random-run-reference",
  "capturePolicyVersion": "vector-telemetry-policy-v2"
}
~~~

Đây là schema do ứng dụng đề xuất. evidenceRef phải là reference thật do evidence store cấp, không phải chuỗi tự tạo rồi coi là artifact đã tồn tại. Nếu không có quyền capture raw context, receipt chỉ ghi trạng thái capture bị từ chối hoặc thiếu, không tự tạo evidence.

### 9.3. Khi evidence thiếu

Phân biệt:

- **PASS:** evaluator có đủ evidence và tiêu chí đạt.
- **FAIL:** evidence đầy đủ nhưng nội dung/behavior không đạt.
- **ERROR:** cần evidence để chấm nhưng capture hoặc evaluator gặp lỗi.
- **NOT_APPLICABLE:** tiêu chí không áp dụng theo rubric.
- **REDACTED:** dữ liệu đã được loại theo policy; cần xem tiêu chí có thể chấm bằng metadata còn lại không.

Không biến REDACTED thành PASS. Nếu criterion cần nội dung tài liệu để xác minh fact, nhưng policy không cho evaluator xem nội dung, phải đánh dấu ERROR/NOT_APPLICABLE theo quy tắc đánh giá đã định trước. Không hạ mức bảo vệ dữ liệu một cách ngầm định chỉ để tăng coverage.

### 9.4. Tách quyền vận hành và quyền xem nội dung

Người trực dashboard có thể cần xem:

- Query rate, latency, error rate, store role và index version.
- Error category và trace reference.

Người đánh giá nội dung có thể cần:

- Query, source documents, provided context và answer.
- Dataset gold labels và rubric.

Hai nhóm không nhất thiết cần cùng quyền. Dùng role/ACL riêng, audit việc xem evidence và thời hạn truy cập có kiểm soát. Không cấp quyền đọc toàn bộ raw trace cho mọi người chỉ vì họ cần xem p95.

## 10. Kiểm thử không rò rỉ dữ liệu

Chính sách chỉ có ý nghĩa khi được kiểm tra trên dữ liệu thực tế của instrumentation và exporter.

### 10.1. Canary test

Tạo fixture tổng hợp có chuỗi dễ nhận biết:

~~~text
query: CANARY_QUERY_SECRET_7F91
filter: customerRef == 'CANARY_TENANT_42'
document: CANARY_DOCUMENT_PRIVATE_6B2A
prompt: CANARY_PROMPT_INTERNAL_91AC
~~~

Chạy một truy vấn qua pipeline thử nghiệm, capture:

- Micrometer observations và span attributes.
- Metrics đã đăng ký.
- Structured application logs.
- Exported OTLP/trace payload ở test collector.

Sau đó assert các canary không xuất hiện ở bất kỳ sink telemetry thông thường nào. Nếu evidence store được phép giữ nội dung theo test policy, xác minh chỉ artifact được bảo vệ mới chứa chúng.

### 10.2. Kiểm tra allowlist và denylist

Test nên xác nhận:

1. db.operation.name, db.system, store.role được giữ đúng.
2. Raw query, raw filter, document content không xuất hiện.
3. Authorization, cookies, API keys và secrets không xuất hiện.
4. Exception message có canary không bị export.
5. Metrics không có label query, tenant.id, document.id hoặc traceId.
6. Trace reference không chứa user/tenant identifier.
7. Attributes dài hoặc nested payload vượt giới hạn bị loại/giảm theo policy.
8. Cấu hình tắt response logging vẫn hoạt động sau khi nâng Spring AI version.

### 10.3. Test thay đổi dependency

Khi nâng Spring AI, Micrometer, OpenTelemetry agent hoặc collector:

- So sánh danh sách span names và attribute keys trước/sau.
- Kiểm tra field mới có thể chứa raw content.
- Chạy lại canary test.
- Xác minh log-query-response vẫn có hiệu lực theo version.
- Kiểm tra exporter và backend không tạo thêm bản sao ngoài policy.
- Chỉ phát hành sau khi privacy regression tests PASS.

Một dependency mới có thể bổ sung attribute hoặc thay đổi convention. Không giả định chính sách cũ vẫn đầy đủ sau mỗi lần nâng cấp.

## 11. Java: kiểm thử policy thu thập và metric tags

Một test đơn vị cho wrapper có thể xác minh service chỉ đăng ký các tag đã cho phép. Ví dụ:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import java.util.List;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.observation.ObservationRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.ai.document.Document;
import org.springframework.ai.vectorstore.SearchRequest;
import org.springframework.ai.vectorstore.VectorStore;

class SafeVectorSearchServiceTest {
    @Test
    void metricsUseOnlyApprovedLowCardinalityTags() {
        VectorStore store = mock(VectorStore.class);
        when(store.similaritySearch(any(SearchRequest.class)))
                .thenReturn(List.of(Document.builder()
                        .id("fixture-doc")
                        .text("Fixture content")
                        .build()));

        try (var meters = new SimpleMeterRegistry()) {
            var service = new SafeVectorSearchService(
                    store, ObservationRegistry.create(), meters);
            var policy = new SafeRetrievalPolicy(
                    5, 0.70, "no-filter", null, "retrieval-v3");

            service.search("CANARY_QUERY_SECRET_7F91", policy);

            var counter = meters.get("app.vector.query.outcomes")
                    .tag("store.role", "policy-search")
                    .tag("outcome", "success")
                    .counter();
            assertEquals(1.0, counter.count());

            assertTrue(meters.getMeters().stream()
                    .filter(m -> m.getId().getName()
                            .startsWith("app.vector."))
                    .flatMap(m -> m.getId().getTags().stream())
                    .noneMatch(tag ->
                            tag.getKey().equalsIgnoreCase("query")
                            || tag.getKey().equalsIgnoreCase("tenant.id")
                            || tag.getKey().equalsIgnoreCase("document.id")));
        }
    }
}
~~~

Đây là ví dụ unit test cho metric do wrapper tạo. Nó **không chứng minh** span mặc định của Spring AI hoặc collector đã được redaction; cần integration test dùng test exporter/collector để kiểm tra toàn bộ payload sau instrumentation.

### 11.1. Integration test với test exporter

Một integration test nên:

1. Dùng VectorStore stub trả document có canary content.
2. Gửi query có canary text.
3. Tạo filter fixture có canary tenant.
4. Thu toàn bộ observations/spans qua test handler/exporter.
5. Serialize metric/span/log payload theo cách exporter thực dùng.
6. Assert raw canary không có trong telemetry sinks.
7. Assert các trường vận hành được phép vẫn còn.
8. Kiểm tra evidence store riêng theo quyền và policy fixture nếu được bật.

Không chỉ assert object Java trước exporter. Redaction phải được xác minh ở **payload cuối cùng** vì exporter, agent hoặc collector có thể thêm attribute.

## 12. Runbook khi phát hiện raw content trong trace/log

Nếu phát hiện query, filter, document hoặc secret xuất hiện trong telemetry:

1. Xác định field, sink, thời gian bắt đầu và các bản sao có thể tồn tại.
2. Xác định nội dung là PII, confidential hay credential; đánh giá phạm vi ảnh hưởng theo policy tổ chức.
3. Tắt capture/route có liên quan hoặc áp dụng redaction tại điểm trước export; không làm mất metrics vận hành cần thiết.
4. Xác định exporter, collector, APM, log search, alert, dashboard, ticket và backup đã nhận dữ liệu.
5. Hạn chế quyền xem/search/export; bảo toàn audit evidence theo quy trình ứng phó của tổ chức.
6. Thực hiện quy trình xử lý credential nếu secret bị lộ; không chỉ xóa một span rồi coi sự cố đã kết thúc.
7. Xử lý bản sao và retention theo quy định/chính sách; ghi nhận những nơi chưa thể xóa hoặc đã hết thời hạn lưu.
8. Thêm canary regression test và kiểm tra lại sau khi deploy.
9. Ghi lại root cause: custom logging, framework observation, agent, exporter hay collector.

Nếu có credential thật trong telemetry, coi đó là sự cố bảo mật và làm theo quy trình ứng phó/rotation của tổ chức. Không sao chép secret vào ticket hoặc báo cáo để minh họa.

## 13. Những sai lầm thường gặp

1. **Cho rằng high-cardinality đồng nghĩa với không nhạy cảm.** Query/filter/document content vẫn có thể là dữ liệu mật.
2. **Chỉ redaction ở dashboard.** Raw data đã được gửi và lưu ở collector/backend.
3. **Chỉ dùng blocklist tên trường.** PII có thể nằm trong description, payload hoặc exception message.
4. **Ghi toàn bộ Document.toString().** Có thể xuất content và metadata nhạy cảm.
5. **Bật log query response để debug production.** Có thể ghi toàn bộ tài liệu được truy xuất.
6. **Coi log-query-response=false là bảo vệ mọi trường.** Raw query/filter/log tùy instrumentation vẫn cần policy riêng.
7. **Hash email/tenant ID rồi đưa vào metric tag.** Hash có thể bị dò và vẫn tạo cardinality lớn.
8. **Dùng Base64 như mã hóa.** Base64 chỉ là encoding.
9. **Dùng sampling thay redaction.** Trace được giữ vẫn có thể lộ dữ liệu.
10. **Log exception nguyên văn.** Message/URL/stack trace có thể chứa filter hoặc secret.
11. **Cho mọi kỹ sư xem raw traces.** Quyền dashboard không đồng nghĩa quyền xem nội dung khách hàng.
12. **Chỉ test object trước exporter.** Agent/collector có thể thêm hoặc biến đổi attribute.
13. **Không kiểm tra sau nâng dependency.** Convention/attribute có thể thay đổi.
14. **Xóa evidence để tránh rủi ro rồi vẫn báo evaluation PASS.** Thiếu dữ liệu cần chấm phải được biểu diễn trung thực.
15. **Coi vector embedding là dữ liệu vô danh.** Vector có thể tiết lộ thông tin từ nội dung gốc và cần bảo vệ theo chính sách.

## 14. Bài thực hành tự luyện

**Bối cảnh:** Một ứng dụng Spring AI dùng VectorStore lưu hồ sơ hỗ trợ khách hàng. Đội vận hành muốn bật tracing để tìm nguyên nhân retrieval chậm, trong khi nhóm đánh giá cần query, tài liệu được truy xuất và context để chấm relevance/fact checking.

Yêu cầu:

1. Phân loại các trường db.vector.query.content, db.vector.query.filter, db.vector.query.response.documents, db.system, db.operation.name, tenant ID, document ID và trace ID.
2. Xây policy allowlist cho metrics, spans và logs; đặt defaultAction: DROP cho các custom attributes.
3. Cấu hình tắt ghi response documents theo property Spring AI được hỗ trợ; xác minh đúng phiên bản.
4. Viết SafeVectorSearchService chỉ ghi store role, filter profile, config version, outcome và result count.
5. Tạo canary query, filter và document content; chạy qua instrumentation đầy đủ.
6. Thu payload từ test exporter/collector và kiểm tra canary không xuất hiện trong metrics, traces và logs thông thường.
7. Tạo evidence store riêng có ACL để evaluator được phép đọc context; liên kết bằng opaque runId.
8. Kiểm thử raw query/filter không được thêm vào metric labels hoặc custom spans.
9. Tạo một exception có canary trong message và xác minh reason code được export thay vì message nguyên văn.
10. Nâng phiên bản Spring AI/Micrometer trong môi trường test và chạy lại privacy regression tests.
11. Thiết kế quyền riêng cho vận hành và người đánh giá nội dung; ghi retention và audit.
12. Viết runbook xử lý trường hợp raw document content đã xuất hiện trong APM.

**Câu hỏi tự kiểm tra:**

- Vì sao query content là high-cardinality nhưng còn có thể là dữ liệu confidential?
- Metrics, traces và logs có các rủi ro lưu trữ/khả năng tìm kiếm khác nhau thế nào?
- Vì sao allowlist thường an toàn hơn chỉ dùng blocklist?
- log-query-response=false kiểm soát điều gì và không kiểm soát điều gì?
- Vì sao sampling không thay thế redaction?
- Hash raw query có bảo đảm ẩn danh không?
- Khi evaluator không có quyền đọc context đã redaction, trạng thái đánh giá nào phù hợp?
- Vì sao phải kiểm thử payload sau exporter thay vì chỉ kiểm tra Observation object?

## 15. Checklist triển khai

- [ ] Có phân loại dữ liệu cho query, filter, document, prompt, response, tool arguments và exception.
- [ ] Phân biệt cardinality với sensitivity; không dùng high-cardinality như lý do tự động cho phép capture.
- [ ] Metrics chỉ chứa labels hữu hạn, đã duyệt.
- [ ] Raw query, raw filter, document content và prompt không được thu thập mặc định.
- [ ] spring.ai.vectorstore.observations.log-query-response được đặt/kiểm tra theo phiên bản phù hợp khi cần tắt response capture.
- [ ] Kiểm tra các span framework của Spring AI, không chỉ custom Observation.
- [ ] Có allowlist và default drop cho custom telemetry attributes.
- [ ] Redaction xảy ra trước khi dữ liệu rời vùng tin cậy; collector là lớp phòng vệ bổ sung.
- [ ] Không export secrets, credentials, authorization headers hoặc cookie.
- [ ] Không dùng Base64/hash thường như biện pháp ẩn danh; pseudonymous IDs có policy riêng.
- [ ] Evidence phục vụ evaluation nằm trong kho có ACL, encryption, retention và audit.
- [ ] Có phân quyền khác nhau cho vận hành và người đánh giá nội dung.
- [ ] Có canary tests cho query/filter/document/exception qua metrics, traces, logs và exporter.
- [ ] Chạy privacy regression tests sau khi nâng Spring AI, Micrometer, agent hoặc collector.
- [ ] Sampling không được dùng thay redaction.
- [ ] Thiếu evidence được báo ERROR/REDACTED theo rubric, không tự xem là PASS.
- [ ] Có runbook xử lý raw content/secret đã xuất hiện trong telemetry.

## Tổng kết

Telemetry của VectorStore có thể chứa nhiều hơn thông tin hiệu năng. Query, filter, document, prompt, response và exception đều có thể mang dữ liệu cá nhân, nội dung nội bộ hoặc credential. High-cardinality chỉ mô tả số lượng giá trị, không nói dữ liệu có an toàn hay không. Vì vậy cần phân loại dữ liệu, xác định mục đích, ưu tiên allowlist, loại bỏ raw content mặc định và kiểm tra toàn bộ đường export.

Spring AI cung cấp observation cho hoạt động VectorStore và các thuộc tính query/response tùy implementation. Cấu hình response logging có thể giúp ngăn capture nội dung tài liệu trả về, nhưng không thay thế chính sách cho query, filter, logs và custom attributes. Một kiến trúc an toàn giữ metadata vận hành trong metrics/traces, còn evidence cần cho relevance/fact checking được lưu riêng trong kho có ACL, encryption, retention và audit. Canary tests trên payload cuối cùng giúp phát hiện hồi quy bảo mật khi thay đổi code hoặc dependency.

## Tài liệu tham khảo

- [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/): observation của VectorStore và các thuộc tính query/response.
- [Spring AI — Vector Databases](https://docs.spring.io/spring-ai/reference/api/vectordbs.html): VectorStore, SearchRequest, metadata filtering và kết quả truy xuất.
- [Micrometer — Observation](https://docs.micrometer.io/micrometer/reference/observation.html): low/high-cardinality key values và liên kết metrics/traces.
- [OpenTelemetry — Sensitive Data](https://opentelemetry.io/docs/security/handling-sensitive-data/): kiểm soát dữ liệu nhạy cảm trong telemetry.
- [OpenTelemetry — Collector Transform Processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/transformprocessor): biến đổi/xóa attributes trước khi export.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): dữ liệu không nên ghi log, sanitization và bảo vệ log.
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): quản lý và bảo vệ secrets.
