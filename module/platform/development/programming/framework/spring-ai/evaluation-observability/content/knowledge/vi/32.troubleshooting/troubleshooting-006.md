# Cardinality tăng do nhãn chứa định danh hoặc nội dung động

> **Chương:** Chẩn đoán sự cố  
> **Module:** SPRING_AI_EVALUATION_OBSERVABILITY — đánh giá chất lượng ứng dụng Spring AI bằng tập dữ liệu, tiêu chí relevance, fact checking và kiểm thử luồng RAG hoặc gọi công cụ; đồng thời đo metrics, traces, chi phí và độ trễ để phát hiện nguyên nhân suy giảm qua từng phiên bản prompt, model và pipeline.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích time series được định danh bởi metric name và toàn bộ tập label như thế nào.
2. Ước lượng tác động của số lượng giá trị label và tổ hợp label lên cardinality.
3. Phát hiện label không giới hạn như user ID, session ID, trace ID, request ID, document ID, prompt hoặc URL động.
4. Phân biệt low-cardinality và high-cardinality values trong Micrometer Observation/Spring AI.
5. Thiết kế metric dimensions hữu hạn, giữ định danh request ở trace/log và dùng exemplar khi phù hợp.
6. Dùng MeterFilter làm hàng rào bảo vệ và hiểu giới hạn của filter, relabeling, scrape limits.
7. Chẩn đoán cardinality bằng PromQL, Prometheus self-metrics và kiểm tra registry.
8. Lập kế hoạch khắc phục, kiểm thử và đặt ngân sách cardinality cho ứng dụng Spring AI.

## 1. Triệu chứng: số time series tăng nhanh

Một ứng dụng Spring AI ban đầu chỉ có vài nghìn time series. Sau khi bổ sung metric cho RAG, ChatModel và VectorStore, số series tăng lên hàng triệu. Prometheus tốn RAM, scrape chậm, compaction nặng, remote write backlog tăng và dashboard truy vấn ngày càng chậm.

Nguyên nhân thường gặp là đưa giá trị thay đổi theo từng request vào label:

- user ID, tenant ID, conversation ID, session ID.
- request ID, invocation ID, trace ID, span ID.
- document ID, chunk ID, vector ID, collection key không giới hạn.
- raw prompt, câu hỏi, retrieved text, tool arguments.
- URL đầy đủ có path parameter hoặc query string.
- SQL statement, exception message, error detail.
- tên model hoặc tool được nhận tự do từ input.
- giá trị timestamp, UUID hoặc hash gần như duy nhất cho mỗi request.

Mỗi tổ hợp label mới có thể tạo một time series mới. Khi traffic tăng, số series không chỉ tăng theo số metric mà còn theo số giá trị khác nhau của từng label.

**Cardinality cao là vấn đề về số lượng tổ hợp time series, không đơn thuần là số label trên một metric.** Một metric có ít label nhưng một label chứa hàng triệu giá trị vẫn có thể tạo hàng triệu series.

### 1.1. Time series được định danh như thế nào?

Trong Prometheus, một time series được nhận diện bởi metric name và tập label/value. Ví dụ:

~~~text
app_ai_tokens_total{
  provider="provider-a",
  model="chat-small",
  operation="answer",
  direction="input"
}
~~~

Mỗi khi một label value thay đổi, tổ hợp mới có thể tạo series mới. Ví dụ thêm request ID:

~~~text
app_ai_tokens_total{
  provider="provider-a",
  model="chat-small",
  operation="answer",
  direction="input",
  request_id="req-001"
}

app_ai_tokens_total{
  provider="provider-a",
  model="chat-small",
  operation="answer",
  direction="input",
  request_id="req-002"
}
~~~

Hai request có cùng loại operation nhưng đã tạo hai series riêng. Nếu mỗi request có ID duy nhất, series sẽ tăng gần theo số request.

### 1.2. Cardinality không giống số lượng label

| Metric | Labels | Cardinality có thể phát sinh |
|---|---|---:|
| request count | method, route, status | Thấp nếu các giá trị được chuẩn hóa |
| token usage | provider, model, operation, direction | Thấp nếu dùng alias hữu hạn |
| token usage | provider, model, request_id | Tăng theo số request |
| retrieval | store, operation, outcome | Thấp nếu danh mục hữu hạn |
| retrieval | store, document_id, query_text | Có thể rất cao hoặc gần như không giới hạn |

Một metric có 5 label không mặc nhiên xấu. Vấn đề là số giá trị có thể xuất hiện ở từng label và số tổ hợp thực tế.

## 2. Ước lượng cardinality trước khi triển khai

### 2.1. Công thức ước lượng

Với một metric, số tổ hợp tối đa có thể hình thành được ước lượng bằng tích số giá trị của từng label:

~~~text
possible_series ≈
  metric_families
  × cardinality(label_1)
  × cardinality(label_2)
  × ...
  × cardinality(label_n)
~~~

Đây là cận trên gần đúng; không phải mọi tổ hợp đều nhất thiết xuất hiện. Tuy nhiên, chỉ một label không giới hạn có thể làm cận trên tăng rất nhanh.

### 2.2. Ví dụ RAG

Giả sử metric token có các dimension:

| Label | Số giá trị dự kiến |
|---|---:|
| provider | 3 |
| model | 4 |
| operation | 6 |
| outcome | 4 |
| environment | 3 |

Số tổ hợp tối đa:

~~~text
3 × 4 × 6 × 4 × 3 = 864 series
~~~

Nếu thêm label request_id với 100.000 giá trị trong cùng khoảng lưu trữ:

~~~text
864 × 100,000 = 86,400,000 series
~~~

Ví dụ cho thấy một định danh động có thể làm thay đổi quy mô dữ liệu nhiều bậc độ lớn. Dùng request ID trong trace hoặc log correlation vẫn có ích; đưa nó vào metric label thường không cần thiết.

### 2.3. Histogram làm tăng số series

Histogram tạo nhiều series theo bucket, ngoài các series tổng/count. Mỗi tổ hợp label lại có một bộ bucket tương ứng. Vì vậy:

~~~text
histogram_series ≈
  label_combinations × (bucket_series + sum_series + count_series)
~~~

Số bucket phụ thuộc cấu hình và cách exporter biểu diễn histogram. Nếu một histogram có nhiều bucket và thêm label request ID, tác động nhân lên rất nhanh.

Timer có thể export count/sum/max và histogram buckets tùy cấu hình. Không chỉ tính số series của một counter rồi áp dụng kết quả đó cho toàn bộ metrics.

### 2.4. Đặt ngân sách cardinality

Trước khi thêm metric, ghi rõ:

- Metric name và mục đích vận hành.
- Danh sách label được phép.
- Số giá trị tối đa dự kiến của mỗi label.
- Số tổ hợp series tối đa.
- Số bucket nếu là histogram.
- Tốc độ tạo series mới theo ngày/giờ.
- Nhóm dashboard/alert thực sự cần dimension đó.

Một label chỉ nên tồn tại khi nó giúp phân nhóm, so sánh hoặc kích hoạt hành động cụ thể. Nếu một giá trị chỉ hữu ích để tìm một request, hãy đặt nó ở trace/log hoặc ledger có quyền truy cập.

## 3. Những label nguy hiểm trong ứng dụng Spring AI

### 3.1. Định danh request và người dùng

Không đưa các giá trị sau vào metric tags:

- user_id, account_id, tenant_id.
- conversation_id, session_id.
- request_id, invocation_id, evaluation_run_id.
- trace_id, span_id.
- provider request ID nếu mỗi request có giá trị riêng.

Các định danh này hữu ích để điều tra một lần gọi, nhưng không phải dimension tổng hợp ổn định. Đặc biệt, trace ID có thể gần như duy nhất cho mỗi request.

Nếu cần so sánh theo tenant, cân nhắc nhóm theo plan/tier/region hoặc một tập phân loại được quản lý. Nếu bắt buộc có tenant dimension, phải đánh giá cardinality thực tế, retention, số tenant tăng trưởng và ngân sách; không mặc định rằng tenant ID là an toàn.

### 3.2. Nội dung người dùng và prompt

Không dùng các giá trị sau làm metric label:

- raw prompt hoặc câu hỏi.
- nội dung retrieved documents.
- document title hoặc chunk text.
- tool arguments hoặc tool result.
- SQL/query string.
- exception message hoặc stack trace.
- URL query string.

Ngoài cardinality, những giá trị này có thể chứa dữ liệu cá nhân, bí mật hoặc nội dung nghiệp vụ. Metrics thường được giữ lâu, được nhiều nhóm truy cập và được tổng hợp rộng hơn trace/log.

Nếu cần phân tích nội dung, dùng evaluation dataset đã kiểm soát, trace span attributes có policy redaction hoặc kho dữ liệu chuyên biệt có ACL/retention phù hợp. Không biến nội dung thành label chỉ vì dashboard cần bộ lọc.

### 3.3. URL động

Không gắn path đầy đủ có ID:

~~~text
uri="/documents/8f4a.../chunks/0192"
~~~

Chuẩn hóa thành route template:

~~~text
uri="/documents/{documentId}/chunks/{chunkId}"
~~~

Với Spring MVC/WebFlux, ưu tiên route pattern/template do framework cung cấp thay vì raw request URI. Với API tự định nghĩa, chuẩn hóa route ở nơi tạo metric.

### 3.4. Model và tool name

Model name thường có tập giá trị hữu hạn nếu ứng dụng dùng alias cấu hình:

~~~text
model="chat-small"
model="chat-large"
model="embedding-v2"
~~~

Nhưng nếu lấy model name tùy ý từ request hoặc cho phép người dùng nhập model ID, cardinality có thể tăng không kiểm soát. Chuẩn hóa model thành alias đã đăng ký.

Tool name cũng nên thuộc danh sách công cụ được cấu hình. Không dùng tool arguments hoặc tên tool do nội dung model tự sinh làm metric tag nếu không có allowlist.

### 3.5. Error và status

Không dùng exception message làm label vì mỗi lỗi có thể chứa ID, URL, SQL hoặc payload khác nhau. Dùng nhóm lỗi hữu hạn:

- timeout.
- rate_limited.
- authentication.
- invalid_request.
- provider_unavailable.
- internal_error.

Tương tự, outcome nên là một tập giá trị như success/error/cancelled; không đưa exception class kèm message hoặc stack trace vào tag.

## 4. Low-cardinality và high-cardinality trong Micrometer Observation

Micrometer Observation phân biệt key-values theo mục đích sử dụng:

- **Low-cardinality values:** phù hợp làm metric dimensions/tags và cũng có thể được đưa vào tracing.
- **High-cardinality values:** phục vụ trace/span context, không nên biến thành metric dimensions.

Đây là ranh giới quan trọng khi instrument Spring AI.

### 4.1. Ví dụ Observation có dimension an toàn

~~~java
Observation.createNotStarted("app.rag.retrieve", registry)
        .lowCardinalityKeyValue("vector.store", "pgvector")
        .lowCardinalityKeyValue("operation", "query")
        .lowCardinalityKeyValue("outcome", "success")
        .observe(() -> vectorStore.similaritySearch(request));
~~~

Các giá trị trên nên đến từ cấu hình hoặc enum có tập giá trị hữu hạn. Nếu có nhiều backend, dùng alias như pgvector, redis hoặc opensearch thay vì URL kết nối hoặc tên cluster động.

### 4.2. Định danh invocation ở trace

Nếu có lý do vận hành để liên kết một invocation cụ thể, có thể thêm opaque reference vào high-cardinality Observation value theo policy:

~~~java
Observation.createNotStarted("app.rag.retrieve", registry)
        .lowCardinalityKeyValue("vector.store", "pgvector")
        .lowCardinalityKeyValue("operation", "query")
        .highCardinalityKeyValue("invocation.ref", opaqueInvocationRef)
        .observe(() -> vectorStore.similaritySearch(request));
~~~

High-cardinality value có thể xuất hiện trong span attributes tùy tracing handler. Nó không tự động an toàn về privacy. Chỉ dùng định danh opaque, không chứa PII/secret, và kiểm soát quyền truy cập/retention của trace backend.

Không đưa prompt, document content hoặc user identity vào high-cardinality value nếu không có yêu cầu được phê duyệt và biện pháp bảo vệ tương ứng.

### 4.3. Không nhầm high-cardinality với miễn phí

Đưa ID vào trace thay vì metric giúp tránh tạo hàng loạt time series, nhưng trace storage vẫn có chi phí và rủi ro dữ liệu. High-cardinality không có nghĩa là được phép ghi mọi dữ liệu. Dùng attributes có chọn lọc, redaction và sampling.

### 4.4. Spring AI Observation conventions

Spring AI sử dụng Observation cho các thành phần như ChatClient, ChatModel, EmbeddingModel và VectorStore theo instrumentation của phiên bản. Khi mở rộng convention:

1. Kiểm tra key-values hiện có của adapter.
2. Phân loại từng field là low-cardinality hay high-cardinality.
3. Đặt low-cardinality chỉ cho operation, provider/model alias, store alias, outcome và các nhóm hữu hạn.
4. Đặt high-cardinality chỉ cho trace correlation cần thiết và đã được kiểm soát.
5. Không copy query, prompt, document hoặc tool payload vào metric tags.
6. Kiểm thử meter IDs và span attributes sau khi thay convention.

Tên observation, key và default behavior có thể thay đổi theo Spring AI version/adapter. Xem reference đúng dependency đang dùng; không giả định mọi VectorStore/provider phát cùng tag set.

## 5. Thiết kế metric dimensions hữu hạn

### 5.1. Một bộ dimension phù hợp cho token usage

Ví dụ:

| Dimension | Giá trị được phép |
|---|---|
| provider | provider-a, provider-b, provider-c |
| model | chat-small, chat-large, embedding-v2 |
| operation | rewrite, embedding, answer, tool_followup |
| direction | input, output |
| outcome | success, error, cancelled |
| environment | dev, staging, prod |

Những danh mục này có thể được quản lý trong cấu hình và review khi thêm model/provider mới.

### 5.2. Dimension phù hợp cho VectorStore

| Dimension | Ví dụ |
|---|---|
| store | pgvector, redis, opensearch |
| operation | query, add, delete |
| outcome | success, error |
| query_type | similarity, hybrid, metadata_filter |
| result_bucket | zero, one_to_five, six_to_twenty, over_twenty |

Không dùng document ID, raw query, filter JSON hoặc collection URL làm tag. Nếu số collection rất lớn, cân nhắc nhóm theo backend/collection class hoặc đo riêng ở trace/ledger.

### 5.3. Dimension cho latency

Đối với timer, chọn dimension giúp tìm bottleneck:

- operation.
- provider/model alias.
- store alias.
- outcome.
- environment.

Không cần request ID trong mỗi timer. Một histogram theo operation/model có thể cho p50/p95/p99 tổng hợp; trace exemplar hoặc log correlation giúp đi tới request cụ thể.

### 5.4. Nhóm giá trị thay vì lưu giá trị gốc

Thay vì đưa số lượng retrieved documents chính xác vào label, dùng bucket:

~~~text
result_count_bucket="zero"
result_count_bucket="one_to_five"
result_count_bucket="six_to_twenty"
result_count_bucket="over_twenty"
~~~

Tương tự:

- token_count_bucket: 0_1k, 1k_4k, 4k_16k, over_16k.
- latency_bucket: fast, normal, slow, very_slow nếu là dimension phân loại; với latency distribution nên ưu tiên histogram.
- retry_bucket: zero, one, two_or_more.

Bucket boundaries phải phản ánh use case và không thay thế số đo histogram khi cần percentile.

## 6. Dùng MeterFilter làm hàng rào bảo vệ

Giảm cardinality ở nơi tạo meter là biện pháp quan trọng nhất. Micrometer MeterFilter có thể giới hạn số tag values hoặc số meter để tránh một lỗi cấu hình làm registry tăng không kiểm soát.

### 6.1. Giới hạn số giá trị của tag

Ví dụ giới hạn model tag của metric token:

~~~java
import io.micrometer.core.instrument.config.MeterFilter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.actuate.metrics.MeterRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class MetricsCardinalityConfiguration {

    @Bean
    MeterRegistryCustomizer<MeterRegistry> aiCardinalityGuard() {
        return registry -> registry.config()
                .meterFilter(MeterFilter.maximumAllowableTags(
                        "app.ai.tokens",
                        "model",
                        8,
                        MeterFilter.deny()));
    }
}
~~~

Filter trên giới hạn số giá trị model cho meter name có prefix tương ứng. Khi vượt ngưỡng, meter mới khớp điều kiện có thể bị deny theo filter đã chọn. API/package phải khớp phiên bản Micrometer và Spring Boot của dự án.

Đây là hàng rào bảo vệ, không phải cách thiết kế label. Khi chạm ngưỡng, một phần meter mới bị từ chối và dashboard có thể mất dữ liệu theo giá trị. Hãy cảnh báo khi gần ngưỡng và sửa nguồn tạo giá trị động.

### 6.2. Giới hạn số meter

Có thể đặt thêm giới hạn tổng số meter:

~~~java
registry.config().meterFilter(
        MeterFilter.maximumAllowableMetrics(
                5000,
                MeterFilter.deny()));
~~~

Giới hạn tổng số meter giúp tránh registry bị phình bất thường, nhưng không thay thế allowlist label. Một metric name với nhiều tag combinations vẫn có thể tạo nhiều meter IDs.

### 6.3. Chuẩn hóa model/provider alias trước khi ghi

~~~java
import java.util.Set;

final class MetricDimensions {
    private static final Set<String> MODELS =
            Set.of("chat-small", "chat-large", "embedding-v2");

    private MetricDimensions() {
    }

    static String model(String configuredAlias) {
        return MODELS.contains(configuredAlias)
                ? configuredAlias
                : "other";
    }
}
~~~

Chỉ lấy alias từ cấu hình đã được quản lý. Giá trị lạ được gom vào `other` và nên có log/metric riêng báo số lần fallback vào nhóm này. Không dùng raw model ID làm tag chỉ vì model được chọn động.

### 6.4. Vì sao không nên chỉ dựa vào MeterFilter?

- Filter không sửa semantics của metric; nó chỉ deny hoặc biến đổi meter theo cấu hình.
- Khi vượt ngưỡng, dữ liệu của những giá trị mới có thể không được ghi.
- Filter theo một meter prefix không bảo vệ các metric name khác.
- Một label động khác vẫn có thể tạo cardinality cao.
- Nếu meter đã được tạo từ trước, filter mới không tự xóa lịch sử trong registry/backend.

Thiết kế allowlist và bounded dimensions ở service/Observation convention vẫn là biện pháp chính.

## 7. Đặt định danh ở đúng nơi

### 7.1. Metrics: trả lời câu hỏi tổng hợp

Metrics phù hợp cho:

- Token input/output theo model.
- Latency theo operation/provider.
- Error rate theo error category.
- Số document retrieved theo bucket.
- Retry count theo operation.
- Cost estimate theo model/operation.

Các dimension nên có tập giá trị hữu hạn, ổn định và giúp phân nhóm.

### 7.2. Traces: điều tra một request

Trace phù hợp để tìm:

- Một invocation cụ thể.
- Chuỗi ChatModel → EmbeddingModel → VectorStore → tool.
- Span nào chậm hoặc lỗi.
- Quan hệ parent-child.
- Opaque request/invocation reference đã được cho phép.

High-cardinality span attributes có thể được dùng có chọn lọc, nhưng vẫn phải áp dụng privacy, access control và retention.

### 7.3. Logs: correlation và chi tiết có kiểm soát

Structured logs có thể chứa:

- trace_id và span_id do tracing integration đưa vào MDC.
- opaque request reference.
- operation và outcome.
- error category.
- model/provider alias.

Không log raw prompt, retrieved document, tool arguments hoặc secret chỉ để hỗ trợ correlation. Dùng trace ID/span ID do instrumentation cung cấp thay vì tự thêm trace ID vào metric tags.

### 7.4. Exemplars nối metric với trace

Prometheus exemplar có thể gắn một trace reference với sample của histogram/counter mà không biến trace ID thành label của mọi time series. Khi hệ thống hỗ trợ exemplar end-to-end, người vận hành có thể chọn một sample rồi mở trace tương ứng.

Exemplar có thể bị sampling/giới hạn và không lưu mọi request. Nó là đường dẫn điều tra từ metric tới một trace mẫu, không phải kho lưu tất cả request IDs. Cần cấu hình registry, scrape/storage và dashboard hỗ trợ exemplar.

## 8. Chẩn đoán cardinality bằng Prometheus

### 8.1. Tổng số series đang hoạt động

Trên Prometheus server, metric self-monitoring thường dùng để quan sát số series trong head:

~~~promql
prometheus_tsdb_head_series
~~~

Theo dõi thay đổi theo thời gian:

~~~promql
deriv(prometheus_tsdb_head_series[15m])
~~~

Đây là số liệu toàn Prometheus server, không chỉ một ứng dụng. Khi điều tra một job, kết hợp với scrape sample metrics và query theo label job.

### 8.2. Đếm series theo metric name

~~~promql
topk(
  20,
  count by (__name__) ({job="spring-ai-evaluation"})
)
~~~

Query này giúp tìm metric family có nhiều series nhất trong job được chọn. Một metric family có số series tăng bất thường thường là nơi cần kiểm tra label set.

### 8.3. Đếm số giá trị duy nhất của một label

Ví dụ đếm số request_id khác nhau:

~~~promql
count(
  count by (request_id) ({job="spring-ai-evaluation"})
)
~~~

Nếu metric không có label request_id, query sẽ không cho kết quả hữu ích. Thay bằng label đang nghi ngờ như session_id, document_id, trace_id hoặc uri.

### 8.4. Đếm series theo model/operation

~~~promql
count by (model, operation) (
  {job="spring-ai-evaluation"}
)
~~~

Dùng để xem nhóm model/operation nào tạo nhiều series. Nếu mỗi model/operation chỉ có vài series nhưng tổng vẫn cao, kiểm tra các label khác trong cùng metric family.

### 8.5. Kiểm tra scrape sample count

~~~promql
scrape_samples_scraped{job="spring-ai-evaluation"}
~~~

~~~promql
scrape_samples_post_metric_relabeling{job="spring-ai-evaluation"}
~~~

Hai số liệu giúp phát hiện sample bị loại sau khi scrape. Chúng không thay thế số series đang lưu và không cho biết label nào là nguồn cardinality.

### 8.6. Xác định label đáng nghi

Quy trình:

1. Dùng topk để tìm metric family có nhiều series.
2. Mở một số series của family và liệt kê toàn bộ label names.
3. Đếm số giá trị duy nhất của từng label nghi ngờ.
4. So sánh label values với request volume và thời gian deploy.
5. Kiểm tra code tạo Meter/Observation và convention tương ứng.
6. Đối chiếu thời điểm cardinality bắt đầu tăng với release/config change.

Không chỉ xem dashboard tổng; hãy kiểm tra raw series để thấy label set thực tế.

## 9. Khắc phục ở các tầng khác nhau

### 9.1. Sửa tại nguồn ứng dụng

Ưu tiên:

1. Xóa request/session/user/document/trace ID khỏi metric tags.
2. Xóa raw prompt/query/document/tool payload khỏi tags.
3. Chuẩn hóa URL thành route template.
4. Dùng provider/model/tool alias từ allowlist.
5. Dùng error category hữu hạn thay cho exception message.
6. Dùng bucket cho giá trị số có nhiều khả năng thay đổi.
7. Giữ định danh chi tiết ở trace/log/ledger theo policy.

Đây là cách giảm cardinality bền vững nhất vì tránh tạo meter/series ngay từ đầu.

### 9.2. MeterFilter ở Micrometer

MeterFilter có thể deny meter khi tag vượt ngân sách hoặc giới hạn tổng số meter. Dùng nó làm guardrail và tạo alert cho trường hợp filter chạm ngưỡng. Không dựa vào filter để chấp nhận label không giới hạn.

### 9.3. metric_relabel_configs ở Prometheus

Prometheus có thể drop sample trước khi ingest vào TSDB:

~~~yaml
scrape_configs:
  - job_name: spring-ai-evaluation
    metrics_path: /actuator/prometheus
    static_configs:
      - targets: ["app-host:8081"]
    metric_relabel_configs:
      - source_labels: [__name__]
        action: drop
        regex: "app_debug_request_detail_.*"
~~~

Rule này có thể giảm series được lưu ở Prometheus local, nhưng Prometheus vẫn phải scrape và parse payload từ ứng dụng. Nó không giảm số meter đang được tạo trong process và không giải quyết nguồn cardinality.

### 9.4. Cẩn thận với labeldrop

Drop một label có thể làm nhiều series khác nhau trở thành cùng một metric name và label set. Điều này có thể tạo collision hoặc làm mất ý nghĩa counter/gauge. Không xóa label định danh hàng loạt mà không kiểm tra liệu các series sau khi xóa có bị trùng hay không.

Nếu mục tiêu là tổng hợp, hãy aggregate có chủ đích bằng PromQL/recording rule hoặc tạo metric đã chuẩn hóa tại nguồn. Recording rule không tự xóa series gốc khỏi TSDB.

### 9.5. write_relabel_configs và remote backend

write relabel có thể drop series trước khi gửi sang remote backend. Nó giảm dữ liệu ở remote destination, nhưng local Prometheus vẫn lưu series nếu đã ingest.

Nếu dashboard đọc remote backend, có thể thấy cardinality giảm ở đó trong khi Prometheus local vẫn tốn tài nguyên. Phải xác định backend nào đang chịu tải.

### 9.6. Scrape limits không phải giải pháp thiết kế

sample_limit và các label limits giúp bảo vệ Prometheus khỏi scrape quá lớn. Khi vượt ngưỡng, scrape có thể thất bại và toàn bộ dữ liệu của scrape đó không được ingest theo semantics của phiên bản/cấu hình.

Không tăng limit hoặc dựa vào limit để kiểm soát cardinality thay cho việc sửa label. Giới hạn là hàng rào cuối, không phải chiến lược metric dimensions.

### 9.7. Dữ liệu cũ không biến mất ngay

Sau khi deploy sửa label:

- Ứng dụng ngừng tạo series mới từ label đã loại.
- Prometheus vẫn có thể giữ series cũ trong TSDB cho tới khi stale/retention xử lý.
- Remote backend có retention riêng và có thể tiếp tục giữ dữ liệu lịch sử.
- Dashboard có thể còn thấy series cũ trong khoảng thời gian truy vấn.

Đừng kết luận bản sửa thất bại chỉ vì series cũ còn hiển thị. Theo dõi tốc độ tạo series mới và head series sau deploy. Xóa dữ liệu lịch sử chỉ theo quy trình vận hành/retention đã được phê duyệt; không xóa bừa toàn bộ TSDB.

## 10. Kiểm thử chống cardinality regression

### 10.1. Kiểm thử danh mục dimension

Tạo test cho metric builder và xác minh mọi tag value đến từ danh mục hữu hạn:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class MetricDimensionsTest {
    @Test
    void unknownModelIsMappedToOther() {
        assertThat(MetricDimensions.model("chat-small"))
                .isEqualTo("chat-small");
        assertThat(MetricDimensions.model("user-selected-model-123"))
                .isEqualTo("other");
    }
}
~~~

Test cần khớp allowlist thật của ứng dụng. Có thể thêm test tương tự cho provider, operation, outcome, store và environment.

### 10.2. Kiểm thử MeterFilter

Ví dụ với SimpleMeterRegistry:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.config.MeterFilter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class MeterCardinalityGuardTest {
    @Test
    void modelTagValuesAreBounded() {
        try (var registry = new SimpleMeterRegistry()) {
            registry.config().meterFilter(
                    MeterFilter.maximumAllowableTags(
                            "app.ai.tokens", "model", 2,
                            MeterFilter.deny()));

            registry.counter(
                    "app.ai.tokens", "model", "chat-small");
            registry.counter(
                    "app.ai.tokens", "model", "chat-large");
            registry.counter(
                    "app.ai.tokens", "model", "unexpected-model");

            long accepted = registry.getMeters().stream()
                    .filter(meter -> meter.getId().getName()
                            .equals("app.ai.tokens"))
                    .count();

            assertThat(accepted).isEqualTo(2);
        }
    }
}
~~~

Test này minh họa guardrail cho một tag key và meter prefix. Xác minh API/filter behavior với phiên bản Micrometer đang dùng. Trong ứng dụng thực, kiểm tra thêm các tag khác và xác nhận metric bị deny có log/alert phù hợp.

### 10.3. Kiểm thử series budget

Trong integration test:

1. Tạo nhiều request fixture với user/request/document IDs khác nhau.
2. Gọi cùng một số operation/model alias.
3. Lấy meter IDs từ test registry.
4. Xác minh số meter tăng theo số dimension hữu hạn, không tăng tuyến tính theo request ID.
5. Kiểm tra không có label chứa prompt, trace ID, user ID hoặc document ID.
6. Kiểm tra histogram có số bucket đúng ngân sách.

Một test hữu ích phải mô phỏng nhiều request có định danh khác nhau; test một request đơn lẻ khó phát hiện cardinality leak.

### 10.4. Kiểm thử Observation convention

Nếu custom ObservationConvention:

- Assert low-cardinality key set chỉ chứa các dimension được duyệt.
- Assert high-cardinality values không bị chuyển sang meter tags.
- Assert không có raw prompt/document/query.
- Chạy test qua ChatModel, EmbeddingModel và VectorStore adapter.
- Kiểm tra exporter metrics thực tế sau convention change.

## 11. Dashboard và cảnh báo cardinality

### 11.1. Dashboard nên có

| Panel | Mục đích |
|---|---|
| Prometheus head series | Quy mô time series hiện tại |
| Series theo job | Tìm service/job tăng bất thường |
| Series theo metric name | Tìm metric family gây cardinality |
| Unique values theo label nghi ngờ | Xác định request_id/user_id/document_id/uri |
| Scrape samples per target | Theo dõi payload scrape |
| New series rate | Phát hiện label mới xuất hiện nhanh |
| MeterFilter denied count/log | Phát hiện guardrail bị chạm |
| Histogram series count | Theo dõi tác động bucket × label combinations |

### 11.2. Cảnh báo

Đặt cảnh báo theo:

- Head series tăng nhanh vượt baseline.
- Số series của job tăng đột biến sau deploy.
- Scrape sample count vượt ngân sách.
- MeterFilter deny bắt đầu tăng.
- Scrape duration tăng hoặc scrape timeout.
- Prometheus memory/TSDB head block tăng nhanh.
- Remote write queue/backlog tăng.

Ngưỡng phải dựa trên baseline, capacity và retention thực tế. Không dùng một ngưỡng series chung cho mọi Prometheus cluster.

## 12. Ma trận chẩn đoán nhanh

| Triệu chứng | Nguyên nhân có khả năng | Bằng chứng cần xem |
|---|---|---|
| Series tăng gần theo request volume | request_id/trace_id/session_id là label | Unique values theo label |
| Cardinality tăng sau thêm RAG metrics | document/chunk/query labels hoặc tool arguments | Metric IDs, Observation conventions |
| Chỉ một metric family tăng | Label động trong một Meter builder | topk series by metric name |
| Histogram tăng nhanh hơn counter | Nhiều buckets nhân với label combinations | Bucket count và label set |
| App memory tăng trước Prometheus | Nhiều meter IDs trong registry | Registry meter count, MeterFilter |
| Prometheus sample count lớn nhưng app registry bình thường | Scrape nhiều targets/instances hoặc duplicate labels | Targets, scrape samples, job labels |
| Series local nhiều, remote ít | write relabel drop hoặc remote policy | Local query, remote_write config |
| Series cũ còn sau deploy | TSDB/remote retention chưa hết | Timestamp, stale markers, retention |
| Scrape fail sau khi cardinality tăng | sample/label/body limit bị vượt | Target last error, scrape logs |
| Dashboard chậm dù request rate ổn định | Cardinality và query fan-out cao | Query stats, series count, label matchers |

## 13. Runbook xử lý cardinality tăng

1. **Xác định phạm vi:** Prometheus local, remote backend, Collector hay registry trong process?
2. **Đo baseline:** ghi head series, series theo job, scrape samples và registry meter count.
3. **Tìm metric family:** dùng topk count by __name__ cho job của Spring AI.
4. **Liệt kê label:** xem raw series của metric family gây tăng.
5. **Đếm unique values:** kiểm tra request_id, trace_id, user_id, document_id, uri, prompt hoặc exception.
6. **Đối chiếu release:** tìm thay đổi metric builder, ObservationConvention, advisor hoặc instrumentation.
7. **Sửa ở nguồn:** xóa ID/nội dung động, chuẩn hóa alias/route/error và bucket hóa số liệu.
8. **Thêm guardrail:** MeterFilter giới hạn tag values/total meters và cảnh báo khi chạm ngưỡng.
9. **Kiểm thử tải:** tạo nhiều request có ID khác nhau và xác nhận series count không tăng theo request count.
10. **Triển khai có theo dõi:** so new-series rate, scrape duration, registry size và backend memory.
11. **Xử lý dữ liệu lịch sử:** để retention xử lý hoặc dùng quy trình xóa series được phê duyệt.
12. **Cập nhật ngân sách:** ghi lại label allowlist, số giá trị dự kiến và owner của metric.

### 13.1. Ví dụ quyết định theo label

| Label đang dùng | Quyết định | Dimension thay thế |
|---|---|---|
| trace_id | Bỏ khỏi metric | Trace correlation/exemplar |
| request_id | Bỏ khỏi metric | Structured log hoặc trace |
| user_id | Bỏ khỏi metric | User cohort/tier đã chuẩn hóa nếu thực sự cần |
| tenant_id | Tránh mặc định | Plan/region hoặc hệ thống phân tích riêng có ACL |
| document_id | Bỏ khỏi metric | store alias, document type hoặc result bucket |
| prompt_text | Bỏ khỏi metric và tránh đưa vào trace nếu không được duyệt | prompt version theo danh mục hữu hạn, nếu phù hợp |
| full_url | Chuẩn hóa | Route template |
| exception_message | Chuẩn hóa | Error category |
| model ID tùy ý | Chuẩn hóa | Model alias allowlist |
| retrieved_count | Bucket hóa hoặc histogram | result_count_bucket / distribution |

Prompt hash vẫn có thể có cardinality rất cao nếu mỗi prompt khác nhau. Chỉ dùng prompt version từ danh mục release hữu hạn làm metric dimension; không dùng hash của prompt nội dung tùy ý.

## 14. Những sai lầm thường gặp

1. **Cho rằng ít label thì cardinality thấp.** Một label có hàng triệu giá trị vẫn tạo hàng triệu series.
2. **Đưa trace ID/request ID vào metric để drill down.** Dùng trace/log correlation hoặc exemplar.
3. **Đưa prompt, query hoặc document text vào label.** Vừa cardinality cao vừa có rủi ro dữ liệu.
4. **Dùng user/tenant ID làm dimension mặc định.** Số định danh có thể tăng liên tục.
5. **Dùng raw URL thay route template.** Path parameter và query string tạo giá trị mới.
6. **Dùng exception message làm error tag.** Nội dung lỗi thay đổi theo request.
7. **Cho model/tool name tự do từ input.** Chuẩn hóa qua allowlist.
8. **Quên histogram bucket multiplier.** Mỗi tổ hợp label có thể tạo nhiều bucket series.
9. **Chỉ dựa vào MeterFilter.** Filter là guardrail; thiết kế label ở nguồn mới là giải pháp.
10. **Nghĩ metric_relabel_configs giảm meter trong ứng dụng.** Nó chỉ tác động sample ở bước scrape/ingest.
11. **Nghĩ write_relabel_configs xóa series khỏi local TSDB.** Nó chỉ ảnh hưởng remote write.
12. **Dùng labeldrop mà không kiểm tra collision.** Nhiều series có thể nhập thành cùng label set.
13. **Dùng recording rule để nghĩ rằng raw series đã biến mất.** Recording rule tạo series tổng hợp nhưng không tự xóa series gốc.
14. **Tăng sample_limit để che cardinality.** Scrape có thể vẫn thất bại và tải backend tiếp tục tăng.
15. **Kết luận bản sửa không hoạt động vì series cũ còn.** Retention và stale handling có độ trễ.

## 15. Bài thực hành tự luyện

**Bối cảnh:** Sau khi thêm metric cho Spring AI RAG, Prometheus head series tăng từ 80.000 lên 2 triệu trong một ngày. Dashboard token usage có các label provider, model, operation, user_id và request_id. Trace backend vẫn hoạt động bình thường.

Yêu cầu:

1. Query top metric families theo số series trong job Spring AI.
2. Liệt kê toàn bộ labels của metric token usage.
3. Đếm số giá trị duy nhất của user_id và request_id.
4. Ước lượng series combinations trước/sau khi thêm hai label này.
5. Xác định trace/log correlation thay thế request_id/trace_id trong metrics.
6. Chuẩn hóa model/provider/operation bằng alias allowlist.
7. Xóa raw user/request identifiers khỏi Meter/Observation low-cardinality values.
8. Nếu cần invocation reference, đưa vào trace high-cardinality attribute theo privacy policy.
9. Thêm MeterFilter guard cho model và operation tags.
10. Kiểm thử nhiều request IDs khác nhau nhưng số meter IDs vẫn nằm trong ngân sách.
11. Kiểm tra histogram bucket count và series growth.
12. Deploy staging, so head series, scrape samples, new-series rate và registry meter count.
13. Kiểm tra local/remote retention để giải thích vì sao series cũ còn.
14. Viết policy metric label allowlist và yêu cầu review khi thêm dimension.

**Câu hỏi tự kiểm tra:**

- Một time series được định danh bởi những thành phần nào?
- Vì sao cardinality gần với tích số giá trị của các label?
- Vì sao request_id và trace_id không phù hợp làm metric label?
- Low-cardinality và high-cardinality Observation values khác nhau thế nào?
- Vì sao high-cardinality trace attribute vẫn cần privacy control?
- Histogram làm số series tăng ra sao?
- MeterFilter.maximumAllowableTags có tác dụng và giới hạn gì?
- metric_relabel_configs và write_relabel_configs tác động ở đâu?
- Vì sao labeldrop có thể làm series collision?
- Làm thế nào phân biệt series cũ còn do retention với series mới tiếp tục được tạo?

## 16. Checklist triển khai

- [ ] Mỗi metric có mục đích vận hành và owner rõ ràng.
- [ ] Có allowlist label names và value domains.
- [ ] Ước lượng cardinality theo tích số label values.
- [ ] Tính cả histogram bucket multiplier.
- [ ] Không có request/user/session/tenant/document/trace/span ID trong metric tags nếu không có ngoại lệ được duyệt.
- [ ] Không có raw prompt, query, document, tool arguments, SQL hoặc exception message trong metric tags.
- [ ] URL dùng route template, không dùng raw path/query.
- [ ] Provider/model/tool/operation/outcome dùng danh mục hữu hạn.
- [ ] ObservationConvention phân biệt low-cardinality và high-cardinality đúng mục đích.
- [ ] High-cardinality trace attributes tuân thủ redaction, ACL và retention.
- [ ] Có MeterFilter guard cho tag values và tổng số meters.
- [ ] Có cảnh báo khi MeterFilter deny hoặc series growth vượt baseline.
- [ ] PromQL dashboard hiển thị series theo job/metric/label.
- [ ] Không dùng relabeling như biện pháp thay thế sửa nguồn.
- [ ] Kiểm tra collision trước khi labeldrop.
- [ ] Hiểu rõ local TSDB và remote backend có retention riêng.
- [ ] Có test nhiều request IDs để phát hiện cardinality tăng theo traffic.
- [ ] Có regression check cho metric dimensions khi thêm Spring AI instrumentation.

## Tổng kết

Cardinality tăng khi metric name kết hợp với nhiều tập label values tạo ra quá nhiều time series. Một dimension hữu hạn như provider/model/operation/outcome thường hữu ích; request ID, trace ID, user ID, document ID, raw prompt, URL hoặc exception message có thể tạo một series mới cho gần như mỗi request. Histogram còn nhân số series theo bucket.

Với Spring AI, hãy thiết kế Observation và Micrometer metrics theo nguyên tắc low-cardinality cho metric dimensions, còn định danh invocation cần thiết được đặt ở trace/log hoặc exemplar theo policy. Chuẩn hóa model/provider/tool/route/error thành danh mục hữu hạn, dùng MeterFilter làm guardrail và kiểm tra cardinality bằng PromQL. Relabeling có thể giảm dữ liệu ở một tầng thu thập nhưng không thay thế sửa nguồn; recording rules không tự xóa series gốc và dữ liệu lịch sử chỉ biến mất theo retention hoặc quy trình xóa riêng. Cuối cùng, kiểm thử nhiều request có ID khác nhau để chứng minh số meter/series không tăng tuyến tính theo traffic.

## Tài liệu tham khảo

- [Prometheus — Data Model](https://prometheus.io/docs/concepts/data_model/): metric names, labels và time series identity.
- [Prometheus — Naming Practices](https://prometheus.io/docs/practices/naming/): quy ước đặt tên metric và labels.
- [Prometheus — Instrumentation Practices](https://prometheus.io/docs/practices/instrumentation/): cardinality và thiết kế instrumentation.
- [Prometheus — Configuration](https://prometheus.io/docs/prometheus/latest/configuration/configuration/): metric relabeling, scrape limits và remote write.
- [Micrometer — Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html): deny/accept, maximum allowable tags và meter limits.
- [Micrometer — Observation](https://docs.micrometer.io/micrometer/reference/observation.html): low-cardinality/high-cardinality key-values và handlers.
- [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/): Observation conventions của ChatClient, ChatModel, EmbeddingModel và VectorStore.
- [OpenTelemetry — Metrics Data Model](https://opentelemetry.io/docs/specs/otel/metrics/data-model/): metric attributes và aggregation.
- [OpenTelemetry — Exemplars](https://opentelemetry.io/docs/specs/otel/metrics/data-model/#exemplars): liên kết sample metrics với trace context.
