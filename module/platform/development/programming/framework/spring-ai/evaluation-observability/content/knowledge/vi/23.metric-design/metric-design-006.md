# Thiết kế nhãn ổn định và giới hạn cardinality

Một ứng dụng Spring AI có thể phục vụ hàng nghìn người dùng, nhiều model, nhiều công cụ và nhiều luồng RAG. Khi nhóm phát triển thêm metric, việc gắn các thuộc tính như user_id, conversation_id, order_id, tool_call_id, prompt hoặc câu hỏi vào tag có vẻ rất tiện: chỉ cần lọc dashboard là tìm được đúng request. Nhưng trong Prometheus, **mỗi tổ hợp tên metric và toàn bộ label values tạo ra một time series riêng**. Nếu mỗi request sinh ra một giá trị mới, số series có thể tăng rất nhanh, làm tăng bộ nhớ, chi phí lưu trữ, tải scrape và độ khó vận hành.

Thiết kế nhãn (label/tag) tốt cần giải quyết hai mục tiêu cùng lúc: **phân nhóm đủ để trả lời câu hỏi vận hành** và **giữ số tổ hợp giá trị hữu hạn, ổn định**. Metrics dùng để tổng hợp theo nhóm; traces, logs và kho kết quả đánh giá giữ chi tiết của từng request/case. Tách đúng vai trò giúp dashboard có ích mà không biến hệ thống metrics thành cơ sở dữ liệu sự kiện.

Bài học này thuộc chương **Thiết kế metric** của module **SPRING_AI_EVALUATION_OBSERVABILITY**. Module đánh giá chất lượng ứng dụng Spring AI bằng dataset, tiêu chí relevance, fact checking và kiểm thử luồng RAG hoặc gọi công cụ; đồng thời đo metrics, traces, chi phí và độ trễ để tìm nguyên nhân suy giảm qua các phiên bản prompt, model và pipeline. Nhãn ổn định là nền tảng để so sánh những chỉ số này một cách tin cậy.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích cardinality là gì và vì sao một label có nhiều giá trị có thể làm tăng số time series rất nhanh.
2. Tính ước lượng cardinality từ số metric, số label keys, số giá trị mỗi label và số series mà meter tạo ra.
3. Phân biệt tags trong Micrometer với labels trong Prometheus và hiểu cách chúng định danh time series.
4. Thiết kế taxonomy labels ổn định cho model, tool, RAG, evaluator, outcome và error class.
5. Phân biệt chiều phân nhóm có số giá trị hữu hạn với dữ liệu định danh/request-specific cần giữ trong traces hoặc logs.
6. Chuẩn hóa giá trị đầu vào bằng allowlist, mapping và fallback other/unknown.
7. Dùng Micrometer MeterFilter như một lớp bảo vệ bổ sung và hiểu giới hạn của nó.
8. Tính tác động của histogram buckets, tag combinations, version labels và label churn.
9. Viết PromQL tổng hợp đúng theo labels và tránh làm mất mẫu số hoặc trộn ngữ nghĩa.
10. Thiết kế cardinality budget, kiểm thử và quy trình migration khi taxonomy thay đổi.

## 2. Cardinality là gì?

Trong Prometheus, một **time series** được xác định bởi tên metric và toàn bộ tập labels cùng giá trị tương ứng.

Ví dụ:

~~~text
app_ai_tool_execution_duration_seconds_count{
  tool_family="retrieval",
  outcome="success",
  region="ap-southeast"
}
~~~

Nếu đổi tool_family thành order, đây là một series khác. Nếu giữ tên và các labels khác nhưng đổi outcome từ success sang timeout, cũng là một series khác.

**Cardinality của metric** là số series phân biệt mà metric đó có thể tạo ra hoặc đang tạo ra. Cardinality có thể tăng vì:

- Thêm một label mới.
- Thêm giá trị mới cho label hiện có.
- Kết hợp nhiều label values với nhau.
- Histogram hoặc Summary tạo thêm nhiều sample series cho mỗi tổ hợp labels.
- Giá trị label thay đổi liên tục theo request, người dùng hoặc dữ liệu nghiệp vụ.

### 2.1. Một ví dụ nhỏ

Giả sử metric app.ai.request.completed có hai labels:

| Label | Giá trị có thể có | Số giá trị |
| --- | --- | ---: |
| route_family | chat, rag, tool | 3 |
| outcome | success, error, timeout | 3 |

Số tổ hợp tối đa:

\[
3\times 3=9
\]

Metric có tối đa 9 series theo thiết kế này, nếu mọi tổ hợp xuất hiện.

Nếu thêm region với 4 giá trị:

\[
3\times 3\times 4=36
\]

Nếu tiếp tục thêm user_id có 100.000 giá trị:

\[
3\times 3\times 4\times 100.000=3.600.000
\]

Chỉ một metric đã có thể tạo ra hàng triệu series tiềm năng. Đây là lý do **không dùng ID duy nhất làm label**.

### 2.2. Công thức ước lượng

Với một metric có các label độc lập, ước lượng số tổ hợp tối đa:

\[
C_{\text{labels}}=\prod_{i=1}^{n}V_i
\]

Trong đó V_i là số giá trị có thể có của label thứ i.

Đây là ước lượng bảo thủ. Không phải mọi tổ hợp đều chắc chắn xuất hiện; một số chiều có thể phụ thuộc nhau. Tuy nhiên, thiết kế hệ thống nên dựa trên **khả năng tạo ra tổ hợp**, không dựa vào hy vọng rằng dữ liệu thực tế sẽ không chạm tới.

### 2.3. Cardinality không chỉ là số label keys

Metric có 8 label keys nhưng mỗi key chỉ có 2 giá trị có thể ít series hơn metric có 2 keys, trong đó một key chứa hàng trăm nghìn ID. Số lượng keys chỉ là một phần; **số giá trị và tổ hợp** mới quyết định cardinality.

Thêm label cũng không luôn làm số series nhân đúng với toàn bộ giá trị mới nếu các tổ hợp không xuất hiện, nhưng upper bound thường tăng theo tích. Vì vậy, cần ước lượng trước khi đưa chiều mới vào dashboard production.

## 3. Vì sao cardinality cao gây hại?

Prometheus phải quản lý metadata, samples, index và chuỗi dữ liệu cho mỗi series. Cardinality cao có thể gây:

1. **Tăng RAM:** nhiều series đang hoạt động cần được quản lý trong bộ nhớ.
2. **Tăng dung lượng lưu trữ:** mỗi series tạo samples theo từng lần scrape và retention.
3. **Tăng tải scrape và ingestion:** exporter, network và Prometheus xử lý nhiều dòng dữ liệu hơn.
4. **Tăng thời gian truy vấn:** PromQL phải chọn và tổng hợp nhiều series.
5. **Tăng label churn:** những giá trị liên tục thay đổi tạo series mới và để lại series cũ trong khoảng retention.
6. **Khó vận hành:** dashboard, alert và giới hạn tài nguyên khó dự đoán.
7. **Rủi ro riêng tư:** ID hoặc nội dung nhạy cảm có thể bị xuất vào hệ thống metrics có phạm vi truy cập rộng.

### 3.1. Ví dụ về tác động của scrape

Giả sử có 200.000 series hoạt động và scrape mỗi 15 giây:

\[
\frac{60}{15}\times 200.000=800.000
\]

Prometheus nhận khoảng **800.000 samples mỗi phút** từ target đó, chưa tính các target khác, histogram phụ và các series phát sinh thêm. Nếu số series tăng lên 2 triệu, tải ingest tăng tương ứng.

Phép tính chỉ là ước lượng tốc độ sample; dung lượng thực còn phụ thuộc compression, label lengths, retention, scrape failures và các chi tiết triển khai.

### 3.2. Cardinality và churn khác nhau

- **Cardinality:** số series phân biệt tồn tại trong một phạm vi.
- **Churn:** tốc độ series mới xuất hiện và series cũ ngừng được scrape.

Một metric có cardinality trung bình nhưng mỗi request tạo label mới có thể tạo churn rất lớn. Ví dụ prompt_version dùng Git SHA mới mỗi lần build khiến series liên tục thay đổi dù số phiên bản đồng thời ít.

Không chỉ giới hạn số series đang hoạt động; cần kiểm soát cả **vòng đời và tốc độ thay đổi của label values**.

## 4. Tags Micrometer và labels Prometheus

Trong Micrometer, các chiều phân nhóm thường được gọi là **tags**. Khi export sang Prometheus, chúng trở thành **labels**.

Ví dụ:

~~~java
Timer.builder("app.ai.tool.execution.duration")
        .tag("tool_family", "retrieval")
        .tag("outcome", "success")
        .register(registry);
~~~

Một dạng series Prometheus có thể là:

~~~text
app_ai_tool_execution_duration_seconds_count{
  tool_family="retrieval",
  outcome="success"
}
~~~

Tên metric và toàn bộ cặp label/value xác định series. **Thứ tự labels không tạo series khác**; thay một giá trị label thì tạo series khác.

### 4.1. Label key ổn định

Label key nên:

- Có tên rõ ràng, snake_case và nhất quán.
- Biểu diễn một chiều phân nhóm duy nhất.
- Có cùng nghĩa trên mọi instance và phiên bản.
- Không đổi tên theo cách viết của từng team.
- Không chứa dữ liệu của từng request.

Ví dụ tên key tốt:

~~~text
component
model_family
tool_family
route_family
case_type
outcome
error_class
limiter_source
region
environment
~~~

Không dùng những key mơ hồ như name, type, value, data, info nếu không có định nghĩa cụ thể.

### 4.2. Label value ổn định

Value nên:

- Dùng chữ thường và tập giá trị được quản lý.
- Có taxonomy rõ ràng.
- Không nhúng timestamp, ID, nội dung request hoặc exception message.
- Có quy tắc cho dữ liệu thiếu/không nhận diện được.
- Được giữ nhất quán qua các phiên bản.

Ví dụ:

~~~text
outcome = success | error | timeout | rate_limited | cancelled
component = model | tool | retrieval | evaluator
case_type = rag | tool | multi_turn | no_tool | other
~~~

Không tạo các giá trị Success, SUCCESS, success có dấu cách cuối và success-v2 cho cùng một ý nghĩa. Chuẩn hóa value ở điểm instrumentation.

## 5. Nhãn nào nên dùng và nhãn nào cần tránh?

### 5.1. Nhãn có cardinality hữu hạn

Những chiều sau thường phù hợp nếu danh sách được kiểm soát:

| Label | Ví dụ values | Lý do |
| --- | --- | --- |
| component | model, tool, retrieval, evaluator | Số thành phần hữu hạn |
| outcome | success, error, timeout, cancelled | Taxonomy ổn định |
| error_class | validation, auth, provider, transient, business, other | Nhóm nguyên nhân |
| tool_family | retrieval, order, payment, other | Nhóm công cụ được quản lý |
| model_family | chat_standard, chat_fast, embedding, other | Nhóm model có chủ đích |
| case_type | rag, tool, multi_turn, no_tool | Nhóm ca đánh giá |
| limiter_source | application, provider, retriever, tool_backend | Nguồn giới hạn |
| limit_type | rpm, tpm, concurrency, tenant_quota | Loại quota |
| environment | dev, staging, production | Môi trường triển khai |
| region | ap_southeast, eu_west, us_east | Vùng hạ tầng hữu hạn |

Ngay cả những chiều này cũng cần giới hạn. Nếu tool_family được lấy trực tiếp từ plugin do người dùng tự đăng ký, số giá trị có thể tăng không kiểm soát; phải map vào danh mục nhóm hữu hạn.

### 5.2. Nhãn thường không nên dùng

| Giá trị | Vì sao nguy hiểm | Nơi phù hợp hơn |
| --- | --- | --- |
| user_id | Mỗi người dùng tạo series mới | Trace/log có phân quyền |
| tenant_id | Có thể có hàng nghìn/hàng triệu tenant | Tenant tier hoặc cohort hữu hạn |
| conversation_id | Mỗi hội thoại là một giá trị mới | Trace và kho hội thoại |
| request_id | Gần như duy nhất mỗi request | Trace/span hoặc log |
| trace_id, span_id | ID có cardinality rất cao | Trace và exemplar nếu hỗ trợ |
| order_id | Dữ liệu nghiệp vụ riêng lẻ | Audit/business database |
| tool_call_id | Mỗi lần gọi khác nhau | Trace event |
| case_id, run_id | Mỗi ca/lần chạy riêng | Evaluation result store |
| document_id, chunk_id | Có thể rất nhiều tài liệu/đoạn | Retrieval trace/result |
| raw_prompt, query | Giá trị gần như vô hạn, có thể nhạy cảm | Prompt store, trace/log bảo vệ |
| exception_message | Nội dung thay đổi theo request | error_class hữu hạn |
| timestamp, date_time | Mỗi thời điểm tạo series mới | Sample timestamp vốn đã có |

**Nguyên tắc:** nếu giá trị có thể khác nhau ở mỗi request hoặc mỗi bản ghi nghiệp vụ, đừng đưa nó vào label metrics.

### 5.3. Tenant và người dùng: dùng phân nhóm thay cho ID

Nếu cần phân tích theo nhóm khách hàng, dùng chiều có số giá trị hữu hạn, ví dụ:

~~~text
tenant_tier = free | standard | enterprise
traffic_class = interactive | batch | internal
customer_region = apac | emea | americas | other
~~~

Không dùng tenant ID thật làm label. Nếu một nhóm enterprise cụ thể cần điều tra, dùng log/trace hoặc báo cáo tổng hợp có quyền truy cập phù hợp. Đừng hy sinh toàn bộ hệ thống metrics chỉ để truy vấn một tenant.

## 6. Cardinality của histogram và Summary

Một Timer có histogram thường xuất nhiều series cho mỗi tổ hợp label: các bucket, _count, _sum và có thể các series phụ tùy registry.

Giả sử một histogram có:

- 12 bucket series (đã tính cả +Inf).
- 1 series _count.
- 1 series _sum.

Tổng cộng khoảng **14 series cho mỗi tổ hợp label**, chưa tính những series phụ khác.

Nếu labels có:

| Label | Số giá trị |
| --- | ---: |
| tool_family | 5 |
| outcome | 5 |
| region | 3 |
| model_family | 4 |

Số tổ hợp:

\[
5\times 5\times 3\times 4=300
\]

Số series histogram ước tính:

\[
300\times(12+1+1)=4.200
\]

Nếu thêm user_id có 50.000 giá trị:

\[
5\times5\times3\times4\times50.000\times14
=210.000.000
\]

Đây là upper bound lý thuyết nếu mọi tổ hợp xuất hiện, nhưng cho thấy tại sao histogram + label ID là một tổ hợp nguy hiểm.

### 6.1. Bucket count làm nhân số series

Khi tăng số buckets để cải thiện độ phân giải p95/p99, số series trên mỗi label combination cũng tăng. Trước khi bật histogram:

1. Xác định câu hỏi percentile hoặc SLO cần trả lời.
2. Chọn số buckets đủ quanh ngưỡng quan trọng.
3. Ước lượng label combinations.
4. Tính series cho mỗi meter.
5. Kiểm tra scrape và tài nguyên ở staging.

Không bật histogram cho mọi metric chỉ vì API hỗ trợ.

### 6.2. Summary cũng có thể tạo nhiều series

DistributionSummary/Timer có thể xuất _count, _sum, histogram buckets hoặc percentiles tùy cấu hình và registry. Cần tính **số sample series thực tế** của exporter đang dùng; đừng chỉ lấy số label combinations rồi coi đó là tổng series.

## 7. Thiết kế taxonomy labels cho Spring AI

Một taxonomy tốt cho ứng dụng Spring AI cần đủ chiều để phân biệt các lớp xử lý nhưng tránh đưa thông tin riêng lẻ vào metrics.

### 7.1. Taxonomy nền tảng

| Label key | Tập giá trị đề xuất | Áp dụng |
| --- | --- | --- |
| component | model, tool, retrieval, memory, evaluator, application | Phân tầng pipeline |
| operation | chat, embedding, tool_call, search, grade | Loại operation hữu hạn |
| outcome | success, error, timeout, rate_limited, cancelled | Kết quả thực thi |
| error_class | validation, auth, provider, backend, transient, business, other | Nhóm lỗi |
| model_family | Nhóm model do ứng dụng quản lý | Model latency/usage |
| tool_family | retrieval, order, payment, other | Tool latency/calls |
| case_type | rag, tool, multi_turn, no_tool, other | Evaluation cases |
| verdict | pass, fail, inconclusive | Oracle/evaluator |
| source_family | policy, knowledge, orders, other | Nguồn RAG |
| limiter_source | application, provider, retriever, tool_backend | Nguồn rate limit |
| limit_type | rpm, tpm, concurrency, tenant_quota, queue_capacity | Loại giới hạn |

Không phải metric nào cũng cần tất cả labels. Một Timer model request không cần tool_family; một Counter fact-check không nhất thiết cần region nếu dashboard không phân tích theo vùng.

### 7.2. Model version và prompt version

Có thể cần phân tích theo model/prompt version khi so sánh rollout, nhưng giá trị phải được kiểm soát:

- model_family có thể là chat_standard, chat_fast, embedding.
- model_release có thể là release_a, release_b nếu số bản đồng thời hữu hạn và có thời gian lưu rõ.
- prompt_variant có thể là baseline, grounded_v2, tool_guard_v3.

Tránh:

- Git SHA hoặc build ID mới trên từng deploy nếu không cần phân tích trực tiếp bằng metrics.
- Toàn bộ prompt text.
- Hash của prompt cho mọi chỉnh sửa nhỏ.
- Model ID do người dùng truyền tùy ý.

Với phân tích chi tiết từng lần chạy evaluation, hãy lưu prompt_version, model_version, dataset_version và evaluator_version trong **evaluation result store**. Metrics production chỉ giữ chiều rollout hữu hạn khi thực sự cần so sánh trong dashboard.

### 7.3. Dataset và case ID

case_type như rag, tool, multi_turn thường phù hợp. dataset_version có thể có cardinality tăng theo thời gian; chỉ dùng nếu số phiên bản được giữ ở mức hữu hạn và cần dashboard theo cohort. case_id và run_id không phù hợp làm labels vì gần như mỗi sample tạo một giá trị mới.

Đối với báo cáo offline, có thể tạo metrics riêng theo **evaluation batch** và xuất kết quả từ kho báo cáo thay vì đẩy mọi case/run ID vào Prometheus lâu dài.

## 8. Giá trị other, unknown và not_applicable

Chuẩn hóa labels cần quy tắc cho giá trị không nằm trong taxonomy. Không nên để raw input đi thẳng vào tag.

### 8.1. Phân biệt ba giá trị

| Giá trị | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| other | Có dữ liệu, nhưng loại cụ thể không thuộc danh sách được theo dõi | Tool mới chưa được phân nhóm |
| unknown | Không xác định được giá trị do thiếu hoặc lỗi nguồn | Provider không trả model family |
| not_applicable | Chiều đó không áp dụng cho sự kiện này | Tool family trên một model-only event |

Không phải metric nào cũng cần cả ba. Chọn tập values phù hợp và giữ nhất quán. Nếu other tăng đột ngột, đó có thể là dấu hiệu taxonomy cần cập nhật; nếu unknown tăng, có thể instrumentation hoặc upstream metadata bị thiếu.

### 8.2. Không tạo value mới từ chuỗi lỗi

Không dùng exception message đầy đủ làm label. Ví dụ chuỗi có class, URL, thời gian timeout và thông tin request có thể khác nhau ở mỗi lần lỗi.

Nên map thành một nhóm hữu hạn:

~~~text
error_class = timeout
~~~

Chi tiết exception class, message, stack trace và dependency endpoint nên nằm trong log/trace có phân quyền. Metric chỉ giữ nhóm nguyên nhân ổn định.

### 8.3. Không biến giá trị thiếu thành chuỗi rỗng tùy tiện

Một label có value rỗng hoặc thiếu có thể được exporter xử lý khác nhau; quan trọng hơn, người đọc không biết đó là thiếu dữ liệu hay không áp dụng. Hãy normalize thành một trong những giá trị taxonomy đã định nghĩa trước.

## 9. Chuẩn hóa labels ở ranh giới instrumentation

Tốt nhất là **allowlist các giá trị được phép**. Không cần lọc raw string bằng một loạt quy tắc tùy ý ở mọi nơi; hãy tạo một bộ mapping dùng chung.

Ví dụ:

~~~java
import java.util.Locale;

public enum ToolFamily {
    RETRIEVAL("retrieval"),
    ORDER("order"),
    PAYMENT("payment"),
    OTHER("other");

    private final String tagValue;

    ToolFamily(String tagValue) {
        this.tagValue = tagValue;
    }

    public String tagValue() {
        return tagValue;
    }

    public static ToolFamily from(String raw) {
        if (raw == null) {
            return OTHER;
        }
        return switch (raw.trim().toLowerCase(Locale.ROOT)) {
            case "retrieval", "search_policy", "search_knowledge" ->
                    RETRIEVAL;
            case "order", "get_order_status" -> ORDER;
            case "payment", "refund_order" -> PAYMENT;
            default -> OTHER;
        };
    }
}
~~~

Taxonomy outcome có thể được biểu diễn tương tự:

~~~java
public enum MetricOutcome {
    SUCCESS("success"),
    ERROR("error"),
    TIMEOUT("timeout"),
    RATE_LIMITED("rate_limited"),
    CANCELLED("cancelled");

    private final String tagValue;

    MetricOutcome(String tagValue) {
        this.tagValue = tagValue;
    }

    public String tagValue() {
        return tagValue;
    }
}
~~~

Khi ghi:

~~~java
Timer.builder("app.ai.tool.execution.duration")
        .tag("tool_family", ToolFamily.from(rawToolName).tagValue())
        .tag("outcome", MetricOutcome.TIMEOUT.tagValue())
        .register(registry)
        .record(Duration.ofSeconds(2));
~~~

### 9.1. Vì sao normalize trước khi tạo meter?

- Mọi nơi trong ứng dụng dùng cùng taxonomy.
- Giá trị lạ không tạo thêm series tùy ý.
- Có thể test mapping độc lập.
- Không phụ thuộc người gọi có trim/case-normalize đúng hay không.
- Có thể đo số giá trị rơi vào other để phát hiện taxonomy mới.

### 9.2. Không normalize bằng cách cắt chuỗi

Một cách làm nguy hiểm là lấy 20 ký tự đầu của prompt hoặc exception để làm label. Dù số ký tự có giới hạn, số chuỗi khác nhau vẫn rất lớn và có thể chứa dữ liệu nhạy cảm. **Giới hạn độ dài không đồng nghĩa giới hạn cardinality**.

## 10. MeterFilter: bảo vệ registry khi có tag vượt giới hạn

Micrometer hỗ trợ MeterFilter để áp dụng chính sách cho meter khi đăng ký. Có thể giới hạn số giá trị khác nhau của một tag trong phạm vi tên metric prefix.

Ví dụ cấu hình Spring Boot:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.boot.actuate.autoconfigure.metrics.MeterRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MetricsConfiguration {

    @Bean
    MeterRegistryCustomizer<MeterRegistry> metricFilters() {
        return registry -> registry.config()
                .meterFilter(MeterFilter.maximumAllowableTags(
                        "app.ai.",
                        "tool_family",
                        8,
                        MeterFilter.deny()))
                .meterFilter(MeterFilter.maximumAllowableTags(
                        "app.ai.",
                        "outcome",
                        8,
                        MeterFilter.deny()));
    }
}
~~~

Filter này giới hạn số giá trị khác nhau của tag key trong phạm vi prefix đã chọn. Khi vượt ngưỡng, filter được cung cấp quyết định hành vi; ví dụ MeterFilter.deny() từ chối meter mới vi phạm.

**Đây là hàng rào bảo vệ, không phải taxonomy chính.** Nếu để hàng nghìn user IDs đi vào một tag rồi hy vọng filter cứu hệ thống, các meter vượt ngưỡng có thể bị từ chối và dữ liệu quan sát bị thiếu. Hãy normalize ở điểm ghi trước, dùng filter để phát hiện vi phạm.

### 10.1. Giới hạn không thay thế allowlist

Filter chỉ giới hạn số giá trị, không tự biết giá trị nào đúng về nghiệp vụ. Ví dụ tool_family có tối đa 8 values vẫn có thể nhận customer_123, customer_124... cho tới khi chạm giới hạn. Những values đầu tiên được đăng ký có thể chiếm slot, tạo kết quả phụ thuộc thứ tự.

Quy trình phù hợp:

1. Allowlist/mapping ở code.
2. Filter ở registry để bảo vệ.
3. Theo dõi tỷ lệ other/unknown và meter bị từ chối.
4. Review taxonomy khi có giá trị mới.

### 10.2. Common tags cũng nhân cardinality

Common tags có thể thêm service, environment, region hoặc cluster cho tất cả meter. Chỉ dùng những giá trị có tập hữu hạn và được quản lý. Một common tag region có 4 values có thể nhân tổng series của mọi metric gần bốn lần.

Không đưa deployment ID thay đổi mỗi lần build thành common tag cho toàn bộ metrics nếu không cần giữ mỗi release thành một series riêng.

### 10.3. Metric relabeling không thay thế chuẩn hóa ở nguồn

Prometheus có thể dùng metric relabeling để loại bỏ hoặc sửa labels trước khi lưu samples vào TSDB. Cách này có thể giảm số series được lưu, nhưng **Prometheus vẫn phải scrape và xử lý payload được exporter gửi tới**. Nó không ngăn ứng dụng tạo meter có cardinality cao và không giải quyết việc lộ dữ liệu nhạy cảm ở endpoint scrape.

Ưu tiên normalize và loại bỏ labels không cần thiết ngay tại instrumentation. Dùng relabeling như lớp kiểm soát bổ sung ở pipeline thu thập, không làm giải pháp chính cho raw IDs hoặc prompt labels.

## 11. Ước lượng cardinality budget

Trước khi thêm labels vào một metric, lập bảng ước lượng.

Ví dụ một Timer tool execution:

| Label | Số values dự kiến | Ghi chú |
| --- | ---: | --- |
| tool_family | 4 | retrieval, order, payment, other |
| outcome | 5 | success, error, timeout, rate_limited, cancelled |
| region | 3 | vùng triển khai |
| model_family | 4 | Chỉ giữ nếu thực sự cần chiều model cho tool latency |

Tối đa:

\[
4\times5\times3\times4=240\text{ label combinations}
\]

Nếu histogram có 12 buckets + _count + _sum, ước tính:

\[
240\times14=3.360\text{ series}
\]

Nếu không cần phân tích tool latency theo model family, bỏ label đó:

\[
4\times5\times3\times14=840\text{ series}
\]

Một label không cần thiết có thể làm cardinality tăng gấp bốn lần. Hãy hỏi **dashboard hoặc alert nào cần chiều này?** Nếu không có câu trả lời cụ thể, đừng thêm.

### 11.1. Cardinality budget theo service

Nhóm có thể đặt ngân sách nội bộ:

| Phạm vi | Ví dụ budget minh họa |
| --- | ---: |
| Một Counter đơn giản | Dưới 100 series |
| Một Timer histogram | Dưới 1.000–3.000 series |
| Một service | Dưới 50.000 active series |
| Một cohort dimension | Dưới 5–10 values |

Các con số này **không phải giới hạn kỹ thuật của Prometheus**. Budget thực tế phụ thuộc RAM, retention, scrape interval, số target, số metric, backend và tải truy vấn. Dùng con số như ngưỡng review nội bộ, sau đó xác nhận bằng thử nghiệm tải.

### 11.2. Series budget và sample budget

Cardinality budget kiểm soát số series. Sample ingestion còn phụ thuộc scrape interval và số target. Ví dụ 20.000 series scrape mỗi 15 giây tạo khoảng 80.000 samples/phút. Khi giảm scrape interval từ 30 giây xuống 5 giây, số samples mỗi phút tăng gấp sáu dù cardinality không đổi.

Quản lý riêng:

- Active series.
- Series churn.
- Samples ingested per second.
- Histogram bucket count.
- Scrape interval.
- Retention và dung lượng.

## 12. Labels ổn định qua phiên bản và rollout

Labels là một phần identity của time series. Thay đổi value hoặc key tạo series khác, ngay cả khi tên metric giữ nguyên.

### 12.1. Thay taxonomy value

Bản cũ:

~~~text
outcome="throttled"
~~~

Bản mới:

~~~text
outcome="rate_limited"
~~~

Prometheus coi đây là hai series khác nhau. Query và dashboard chỉ lọc throttled sẽ không thấy dữ liệu mới.

Trước khi đổi:

1. Xác định ngữ nghĩa cũ và mới có thật sự tương đương không.
2. Cập nhật metric dictionary và dashboard/alert.
3. Nếu cần tương thích, có giai đoạn chuyển tiếp có thời hạn.
4. Không ghi đồng thời hai nhãn khác nhau cho cùng sự kiện nếu việc đó làm tăng đếm đôi.
5. Chốt thời điểm ngừng series cũ.

### 12.2. Prompt/model version labels

Nếu dashboard cần so sánh rollout A/B, có thể dùng tag hữu hạn như prompt_variant=baseline|grounded_v2. Nhưng cần giới hạn số cohort hoạt động và có kế hoạch kết thúc.

Tránh:

- prompt_hash khác nhau mỗi lần chỉnh sửa.
- git_commit mới cho mọi deploy trên mọi meter.
- model_instance_id riêng cho mỗi container.
- deployment_timestamp làm label.

Thông tin build, commit và prompt version chi tiết phù hợp hơn với release metadata, traces hoặc evaluation report. Nếu dùng version label để phân tích rollout, hãy dùng **release group hữu hạn**, không phải ID vô hạn.

### 12.3. Blue/green và canary

Khi chạy hai cohort song song:

~~~text
deployment_cohort = stable | canary
~~~

Đây là dimension hữu hạn, hữu ích để so error rate/latency trong thời gian rollout. Sau khi rollout kết thúc, series canary ngừng được scrape; đó là bình thường. Không cần giữ từng pod ID làm label để theo dõi canary.

## 13. Metrics không phải nơi lưu dữ liệu từng request

Metrics trả lời câu hỏi tổng hợp: bao nhiêu request lỗi, p95 là bao nhiêu, model family nào tốn nhiều token, tool family nào timeout. Khi cần biết **request nào**, **prompt nào**, **case ID nào** hoặc **tài liệu nào**, hãy dùng trace/log/evaluation store.

### 13.1. Phân chia vai trò

| Hệ thống | Lưu gì? | Truy vấn điển hình |
| --- | --- | --- |
| **Metrics** | Số đếm, tổng, phân bố và trạng thái tổng hợp | p95 theo tool_family; error rate theo model_family |
| **Traces** | Span và quan hệ giữa các bước trong một request | Tại sao task A123 chậm? |
| **Logs** | Sự kiện chi tiết và exception | Backend trả lỗi gì? |
| **Evaluation store** | Dataset, case/run ID, prompt/model/rubric version, verdict và evidence | Ca nào FAIL sau khi đổi prompt? |
| **Business database/audit** | Trạng thái nghiệp vụ có thẩm quyền | Refund operation đã hoàn tất chưa? |

### 13.2. Dùng exemplars để liên kết metrics với traces

Một số backend và instrumentation hỗ trợ **exemplars**: sample metric có thể đính kèm tham chiếu trace context để người vận hành nhảy từ một điểm trên histogram sang trace đại diện.

Exemplar không giống label thường:

- Không tạo một time series mới cho mỗi trace ID.
- Không nên đưa trace_id vào label set.
- Cần backend, exporter và tracing integration hỗ trợ.
- Không phải mọi sample đều có exemplar; sampling và cấu hình quyết định.

Nếu exemplar không khả dụng, có thể dùng trace links trong logs hoặc evaluation result store. Đừng tạo label trace_id để thay thế.

### 13.3. Ví dụ một ca điều tra

Dashboard cho thấy tool execution p95 tăng với tool_family=order và outcome=timeout. Metric giúp biết **nhóm tool order** đang có đuôi timeout. Người điều tra mở traces hoặc logs đại diện để xem:

1. Tool nào được dispatcher chọn?
2. Handler bắt đầu lúc nào và deadline là bao nhiêu?
3. Backend connection/read span nào chậm?
4. Có retry hay request bị queue?
5. Operation ID có trạng thái gì ở source of truth?

Các ID chi tiết được giữ trong trace/audit; metrics chỉ giữ nhóm tool_family và outcome.

## 14. PromQL: tổng hợp theo labels ổn định

Giả sử metric có series với labels:

~~~text
app_ai_attempt_completed_attempts_total{
  component="model",
  outcome="timeout",
  model_family="chat_fast"
}
~~~

### 14.1. Error rate theo component

~~~promql
sum by (component) (
  rate(app_ai_attempt_completed_attempts_total{
    outcome=~"error|timeout|cancelled"
  }[5m])
)
/
sum by (component) (
  rate(app_ai_attempt_completed_attempts_total[5m])
)
~~~

Kết quả là tỷ lệ attempts không thành công theo component, theo định nghĩa outcome đã chọn. Nếu muốn coi rate_limited là lỗi, thêm nó vào selector; nếu muốn theo dõi riêng, giữ một panel khác.

### 14.2. Timeout rate theo model family

~~~promql
sum by (model_family) (
  rate(app_ai_attempt_completed_attempts_total{outcome="timeout"}[5m])
)
/
sum by (model_family) (
  rate(app_ai_attempt_completed_attempts_total[5m])
)
~~~

Đừng thêm request_id vào by(...); làm vậy sẽ tạo một chuỗi kết quả cho mỗi request và tái tạo vấn đề cardinality trong kết quả truy vấn.

### 14.3. Tool latency p95 theo family

~~~promql
histogram_quantile(
  0.95,
  sum by (le, tool_family) (
    rate(app_ai_tool_execution_duration_seconds_bucket[5m])
  )
)
~~~

Giữ le để Prometheus hiểu bucket; giữ tool_family để so sánh nhóm. Không cần group theo tool_call_id, order_id hoặc trace_id.

### 14.4. Relevance score trung bình theo case type

Nếu score được ghi bằng DistributionSummary và exporter phát _sum/_count:

~~~promql
sum by (case_type) (
  rate(app_ai_eval_relevance_score_sum[15m])
)
/
sum by (case_type) (
  rate(app_ai_eval_relevance_score_count[15m])
)
~~~

Kết quả là mean score theo case_type. Chỉ so sánh khi cùng rubric, cùng miền score và cùng định nghĩa sample. Không thêm case_id vào labels để tìm một ca riêng; xem evaluation store.

### 14.5. Tỷ lệ other để phát hiện taxonomy drift

~~~promql
sum(rate(app_ai_tool_execution_completed_calls_total{tool_family="other"}[15m]))
/
sum(rate(app_ai_tool_execution_completed_calls_total[15m]))
~~~

Nếu tỷ lệ other tăng đột ngột, có thể ứng dụng bắt đầu phát một tool family mới hoặc mapping bị hỏng. Metric này giúp phát hiện taxonomy drift mà không tạo series cho mọi tên tool lạ.

Truy vấn giả định ứng dụng có Counter logic cho tool execution completed với baseUnit là calls; tên series có hậu tố tương ứng phải được xác minh qua Prometheus scrape của phiên bản registry đang dùng.

### 14.6. Mẫu số bằng 0

Nếu không có sample trong cửa sổ, tỷ lệ có thể không xác định. Dashboard nên thể hiện **N/A/no data**, không tự gán 0% hoặc 100%. Đừng dùng fallback khiến thiếu telemetry trông giống trạng thái khỏe mạnh.

## 15. Migration nhãn mà không làm hỏng dashboard

Thay đổi taxonomy có thể cần thiết khi thêm tool family, đổi outcome hoặc chuẩn hóa model group. Nhưng vì label values tham gia định danh time series, migration phải được xem như thay đổi hợp đồng telemetry.

### 15.1. Thêm một giá trị mới

Giả sử taxonomy tool_family hiện có:

~~~text
retrieval | order | payment | other
~~~

Ứng dụng sắp bổ sung tool family shipping. Quy trình:

1. Xác định shipping là một nhóm nghiệp vụ ổn định hay chỉ là tên một tool riêng lẻ.
2. Ước lượng số tổ hợp labels và tác động lên histogram.
3. Thêm shipping vào enum/mapping trong cùng release.
4. Cập nhật metric dictionary và dashboard nếu cần phân tích riêng.
5. Kiểm tra các instance không chạy cùng phiên bản có tiếp tục map giá trị nhất quán không.
6. Theo dõi tỷ lệ other trước và sau deploy.

Không để một instance map shipping thành other còn instance khác phát shipping nếu muốn so sánh series nhất quán trong rollout.

### 15.2. Đổi tên label key

Ví dụ đổi route thành route_family. Đây không chỉ là đổi tên trong Java; nó làm thay đổi label set ở backend. Các query cũ sẽ không thấy series mới.

Nếu cần chuyển đổi an toàn:

- Cập nhật query/dashboard/alert cùng đợt.
- Nếu backend và registry cho phép, có thể duy trì một khoảng chuyển tiếp có thời hạn với quy tắc không đếm đôi.
- Theo dõi cả hai schema trong staging.
- Xác định ngày kết thúc schema cũ.
- Xóa tương thích cũ sau khi dashboard/alert đã được chuyển.

Tránh phát đồng thời hai meter cùng ngữ nghĩa chỉ để giữ dashboard cũ nếu điều đó làm tăng gấp đôi số liệu hoặc cardinality. Nếu cần chuyển tiếp, mô tả rõ nguồn nào là chuẩn cho từng giai đoạn.

### 15.3. Gộp values cũ vào taxonomy mới

Giả sử trước đây có các values:

~~~text
tool_name="search_policy"
tool_name="search_knowledge"
tool_name="search_contract"
~~~

Taxonomy mới muốn gộp thành:

~~~text
tool_family="retrieval"
~~~

Đây là thay đổi từ **tool identity** sang **tool family**. Dữ liệu cũ không thể tự biến thành dữ liệu mới mà không mất chi tiết. Cần:

1. Chọn metric name mới nếu ngữ nghĩa quan sát thay đổi.
2. Ghi rõ ngày bắt đầu dữ liệu theo taxonomy mới.
3. Cập nhật dashboard và báo cáo để không nối hai chuỗi như cùng một phân bố.
4. Giữ tool name chi tiết trong trace/log hoặc evaluation store nếu vẫn cần điều tra.

### 15.4. Prompt variant và canary

Một rollout có thể dùng:

~~~text
prompt_variant="baseline"
prompt_variant="grounded_v2"
~~~

Khi thử nghiệm xong, ngừng variant cũ và giữ kết quả chi tiết trong evaluation report. Không tạo prompt_variant bằng toàn bộ nội dung prompt hoặc hash không giới hạn. Với đánh giá offline, báo cáo theo run/version thường phù hợp hơn metrics production lâu dài.

## 16. Quyền riêng tư và dữ liệu nhạy cảm trong labels

Cardinality không phải rủi ro duy nhất. Labels có thể được hiển thị trong dashboard, alert, API và hệ thống lưu trữ telemetry với phạm vi người truy cập rộng hơn hệ thống nghiệp vụ.

Không đưa vào labels:

- Tên, email, số điện thoại hoặc thông tin nhận diện người dùng.
- User ID, tenant ID hoặc account ID nếu chúng có thể xác định cá nhân/tổ chức.
- Nội dung prompt, câu hỏi, tài liệu truy xuất hoặc câu trả lời.
- Order ID, payment ID, operation ID hoặc mã giao dịch.
- API key, credential, access token hoặc secret.
- Exception message có thể chứa URL, query hoặc dữ liệu request.

### 16.1. Dùng cohort và classification

Thay vì tenant_id, có thể dùng tenant_tier hoặc traffic_class nếu nghiệp vụ cần phân nhóm. Thay vì raw prompt, dùng prompt_variant hữu hạn. Thay vì error message, dùng error_class. Thay vì document_id, dùng source_family.

Các nhóm này vẫn cần review quyền riêng tư và cardinality; một cohort có thể vô tình tiết lộ thông tin nếu chỉ có một khách hàng trong nhóm.

### 16.2. Hash ID không giải quyết cardinality

Hash user ID hoặc conversation ID không làm giảm số giá trị phân biệt. Nếu mỗi ID gốc là duy nhất, hash của chúng cũng gần như duy nhất. Hash còn có thể trở thành dữ liệu có thể liên kết lại với nguồn khác.

**Không dùng hash thay cho allowlist.** Giữ ID ở trace/log/audit được bảo vệ và chỉ đưa nhóm hữu hạn vào metrics.

## 17. Theo dõi chính cardinality và label drift

Thiết kế labels cần có khả năng tự giám sát. Một taxonomy tốt hôm nay có thể bị phá vỡ khi plugin mới, provider mới hoặc code path mới đưa raw value vào instrumentation.

### 17.1. Những tín hiệu cần theo dõi

| Tín hiệu | Phát hiện điều gì? | Hành động |
| --- | --- | --- |
| Active series theo job/service | Cardinality tổng tăng | Tìm metric/label tạo nhiều series |
| Series churn | Giá trị thay đổi liên tục | Kiểm tra version, timestamp, ID labels |
| Samples ingested/sec | Tải scrape tăng | Xem scrape interval và histogram |
| Tỷ lệ tool_family=other | Tool mới hoặc mapping thiếu | Review taxonomy |
| Tỷ lệ model_family=unknown | Thiếu metadata hoặc parser lỗi | Sửa nguồn metadata |
| Meter bị MeterFilter deny | Vượt giới hạn tag values | Kiểm tra raw tag và mapping |
| Số label values theo key | Một chiều phát sinh values mới | Xác định nguồn tạo values |
| Histogram series count | Buckets/labels nhân cardinality | Review cấu hình histogram |

### 17.2. Kiểm tra từ Prometheus

Prometheus cung cấp các metric nội bộ cho số series, samples và hoạt động TSDB; tên và khả năng có sẵn phụ thuộc phiên bản. Có thể dùng các metric nội bộ như:

~~~promql
prometheus_tsdb_head_series
~~~

để quan sát số series trong head block của Prometheus nếu metric này được expose ở phiên bản đang chạy. Có thể xem thêm:

~~~promql
scrape_samples_post_metric_relabeling
~~~

để quan sát số samples sau metric relabeling theo target. Những metric nội bộ này **không thay thế việc tìm series gây cardinality**; chúng chỉ báo quy mô hoặc điểm bất thường. Hãy xác minh tên metric nội bộ thực tế trong endpoint Prometheus của phiên bản đang dùng.

### 17.3. Tìm label values bất thường

Khi cardinality tăng:

1. Xác định job/service có active series tăng.
2. Liệt kê metric families mới hoặc tăng nhanh.
3. Kiểm tra các label keys có nhiều values nhất.
4. Tìm values có dạng ID, timestamp, hash hoặc chuỗi tự do.
5. Truy ngược code instrumentation tạo meter.
6. Chuẩn hóa value, loại label không cần thiết và triển khai migration.

Không nên chỉ tăng giới hạn Prometheus hoặc tăng RAM trước khi biết nguồn tạo series. Làm vậy có thể trì hoãn sự cố nhưng giữ nguyên nguyên nhân.

## 18. Kiểm thử taxonomy và cardinality

Nhãn là một phần hợp đồng dữ liệu. Cần kiểm thử mapping và tác động series trước khi merge instrumentation.

### 18.1. Unit test cho mapping

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class ToolFamilyTest {

    @Test
    void mapsKnownToolNamesToStableFamilies() {
        assertEquals("retrieval",
                ToolFamily.from("search_policy").tagValue());
        assertEquals("order",
                ToolFamily.from("get_order_status").tagValue());
        assertEquals("payment",
                ToolFamily.from("refund_order").tagValue());
    }

    @Test
    void mapsUnknownAndNullValuesToOther() {
        assertEquals("other",
                ToolFamily.from("new_dynamic_plugin").tagValue());
        assertEquals("other",
                ToolFamily.from(null).tagValue());
    }
}
~~~

Test này xác minh raw tool names không trở thành tag values mới ngoài taxonomy.

### 18.2. Kiểm tra MeterRegistry

Với SimpleMeterRegistry, ghi nhiều tool names khác nhau nhưng cùng family rồi xác minh chỉ có số meter/tags dự kiến:

~~~java
import java.time.Duration;

import static org.junit.jupiter.api.Assertions.assertEquals;

import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

var registry = new SimpleMeterRegistry();

Timer.builder("app.ai.tool.execution.duration")
        .tag("tool_family",
                ToolFamily.from("get_order_status").tagValue())
        .tag("outcome", "success")
        .register(registry)
        .record(Duration.ofMillis(100));
Timer.builder("app.ai.tool.execution.duration")
        .tag("tool_family",
                ToolFamily.from("read_order_history").tagValue())
        .tag("outcome", "success")
        .register(registry)
        .record(Duration.ofMillis(120));
Timer.builder("app.ai.tool.execution.duration")
        .tag("tool_family",
                ToolFamily.from("plugin_tool_generated_123").tagValue())
        .tag("outcome", "error")
        .register(registry)
        .record(Duration.ofMillis(200));

var orderTimer = registry.find(
                "app.ai.tool.execution.duration")
        .tag("tool_family", "order")
        .timer();
var otherTimer = registry.find(
                "app.ai.tool.execution.duration")
        .tag("tool_family", "other")
        .timer();

assertEquals(2, orderTimer.count());
assertEquals(1, otherTimer.count());
~~~

Đoạn gọi này sử dụng enum ToolFamily đã định nghĩa ở mục 9. Các imports và package cần được điều chỉnh theo cấu trúc project thực tế.

### 18.3. Kiểm tra cardinality theo tổ hợp

Tạo fixture với:

- 4 tool families.
- 5 outcomes.
- 3 regions.

Upper bound là 60 tổ hợp labels cho một meter đơn giản. Kiểm tra registry chỉ phát các values thuộc allowlist và không có user_id, request_id hoặc trace_id.

Nếu bật histogram 12 buckets cùng count/sum, ước lượng 60 × 14 = 840 series cho metric này, trước khi tính các series phụ của registry.

### 18.4. Kiểm tra MeterFilter

Test filter bằng registry được cấu hình để xác minh:

1. Giá trị hợp lệ vẫn đăng ký được.
2. Giá trị mới ngoài mapping được đưa về other trước khi tới registry.
3. Nếu code cố tạo quá nhiều giá trị khác nhau cho một tag, filter có hành vi deny theo cấu hình.
4. Việc deny được ghi nhận/quan sát trong môi trường test để tránh mất metric âm thầm.

### 18.5. Kiểm tra schema sau exporter

Nếu dùng Prometheus registry:

- Lấy scrape text sau khi ghi fixture.
- Kiểm tra tên series và labels thực tế.
- Xác nhận không xuất ID hoặc nội dung nhạy cảm.
- Đếm số sample series cho histogram.
- So sánh schema trước/sau khi đổi taxonomy.

SimpleMeterRegistry kiểm tra logic Micrometer nhưng không chứng minh naming convention và series count ở Prometheus. Cần integration test exporter cho phần đó.

## 19. Bài thực hành

**Bối cảnh:** một ứng dụng Spring AI có ChatClient, tool tra cứu đơn hàng, tool hoàn tiền, retriever chính sách và evaluator relevance/fact checking. Nhóm vận hành muốn phân tích error rate, latency, token usage và chất lượng theo nhóm, đồng thời giữ hệ thống Prometheus ổn định khi thêm model/tool mới.

### Phần A — Phân loại labels

Với từng thuộc tính sau, quyết định nên là metric label, trace/log attribute hay evaluation metadata:

1. component = model/tool/retrieval/evaluator.
2. outcome = success/error/timeout.
3. tool_call_id.
4. tool_family = order/payment/retrieval.
5. raw tool name do plugin tự đăng ký.
6. prompt_variant = baseline/grounded_v2.
7. prompt_hash.
8. case_type = rag/tool/multi_turn.
9. case_id và run_id.
10. tenant_tier và tenant_id.
11. error_class và exception_message.
12. trace_id và region.

Giải thích lựa chọn bằng **số giá trị dự kiến**, mục tiêu truy vấn và rủi ro riêng tư.

### Phần B — Tính cardinality

Một Timer histogram có:

- tool_family: 4 values.
- outcome: 5 values.
- region: 3 values.
- model_family: 4 values.
- 12 bucket series, một _count và một _sum.

1. Tính số label combinations tối đa.
2. Tính số series histogram ước tính.
3. Bỏ model_family nếu không cần chiều này và tính lại.
4. Thêm user_id có 50.000 values và tính upper bound mới.
5. Giải thích vì sao đây là ước lượng và vì sao cần kiểm tra series thực tế.

**Đáp án kiểm tra nhanh:** 4 × 5 × 3 × 4 = **240 combinations**; 240 × 14 = **3.360 series**. Bỏ model_family: 4 × 5 × 3 × 14 = **840 series**. Thêm user_id: 240 × 50.000 × 14 = **168.000.000 series**.

### Phần C — Xây taxonomy

1. Định nghĩa values cho component, outcome, error_class, tool_family, model_family, case_type và verdict.
2. Tạo mapping raw tool names về tool_family.
3. Map provider model identifiers về model_family.
4. Map exception categories về error_class.
5. Định nghĩa other, unknown và not_applicable.
6. Viết unit tests để xác nhận mọi raw input không nằm trong allowlist được map về fallback.

### Phần D — Kiểm tra MeterFilter và exporter

1. Tạo một Timer có labels tool_family và outcome.
2. Cấu hình MeterFilter.maximumAllowableTags cho tool_family.
3. Thử đăng ký nhiều giá trị tag khác nhau và xác nhận hành vi khi vượt giới hạn.
4. Dùng Prometheus registry để xem scrape thực tế.
5. Bật histogram và tính số sample series theo số buckets.
6. Kiểm tra không có user_id, trace_id, prompt hoặc exception message trong labels.

### Phần E — Migration và dashboard

1. Đổi outcome throttled thành rate_limited. Viết kế hoạch migration dashboard và alert.
2. Thêm tool_family shipping. Tính cardinality mới và cập nhật mapping.
3. Chạy canary với prompt_variant baseline và grounded_v2. Xác định khi nào ngừng label cũ.
4. Viết PromQL error rate theo component và p95 theo tool_family.
5. Đề xuất panel theo dõi active series, series churn và tỷ lệ other.
6. Chỉ ra thông tin nào cần xem trong traces/evaluation store thay vì metrics.

### Câu hỏi tự kiểm tra

- Một time series được định danh bởi những thành phần nào?
- Vì sao thêm một label có 10 values có thể nhân số series gần 10 lần?
- Vì sao histogram làm tăng cardinality so với Counter đơn giản?
- Vì sao hash user ID vẫn là cardinality cao?
- other khác unknown và not_applicable ở điểm nào?
- Khi nào model_family hoặc prompt_variant có thể là label hợp lý?
- Vì sao git SHA thường không nên là common tag trên mọi metric?
- MeterFilter có thể thay thế allowlist hay không?
- Vì sao đổi label value tạo series mới dù tên metric không đổi?
- Khi nào dùng exemplars thay vì trace_id label?
- Làm sao nhận biết taxonomy drift qua tỷ lệ other?
- Vì sao metrics không nên dùng để truy vấn một case_id riêng lẻ?

## 20. Những điều cần ghi nhớ

1. **Một time series được xác định bởi metric name và toàn bộ label set.** Mỗi tổ hợp values khác nhau tạo một series khác.
2. **Cardinality tăng theo tích của các chiều labels.** Đừng đánh giá rủi ro chỉ bằng số lượng label keys.
3. **Histogram nhân số series trên mỗi label combination.** Bucket count, _count, _sum và sample phụ đều cần nằm trong budget.
4. **Labels phải có taxonomy hữu hạn và ổn định.** Dùng component, outcome, tool_family, model_family, case_type và error_class được quản lý.
5. **Không đưa ID hoặc nội dung request vào metric labels.** user_id, tenant_id, trace_id, case_id, prompt và exception message thuộc trace/log/evaluation store.
6. **Normalize bằng allowlist trước khi ghi meter.** Map giá trị lạ về other hoặc unknown thay vì tạo series tùy ý.
7. **MeterFilter là hàng rào bảo vệ.** Nó không thay thế mapping và có thể làm meter bị từ chối nếu taxonomy không được kiểm soát.
8. **Cardinality budget phải tính cả buckets, common tags và rollout dimensions.** Kiểm tra active series, churn và sample ingestion.
9. **Thay đổi labels là thay đổi hợp đồng telemetry.** Cần migration dashboard, alert và quy tắc tương thích có thời hạn.
10. **Metrics và traces bổ sung nhau.** Metrics tổng hợp theo nhóm; traces/logs/evaluation store giữ bằng chứng chi tiết của từng request/case.

## Tài liệu tham khảo

- [Prometheus — Metric and Label Naming](https://prometheus.io/docs/practices/naming/): quy tắc tên metric và labels.
- [Prometheus — Data Model](https://prometheus.io/docs/concepts/data_model/): time series, metric names và label sets.
- [Prometheus — Instrumentation Practices](https://prometheus.io/docs/practices/instrumentation/): thiết kế metrics và cardinality.
- [Prometheus — Histograms and Summaries](https://prometheus.io/docs/practices/histograms/): buckets, count, sum và ảnh hưởng của histogram.
- [Prometheus — Querying Basics](https://prometheus.io/docs/prometheus/latest/querying/basics/): selector, label matching và aggregation.
- [Micrometer Reference — Meter Concepts](https://docs.micrometer.io/micrometer/reference/concepts.html): meter, tags, registry và naming.
- [Micrometer Reference — Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html): lọc và giới hạn meter/tag values.
- [Micrometer Reference — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html): histogram configuration và cardinality trade-offs.
- [Spring Boot Reference — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): MeterRegistry, common tags và Actuator metrics.
- [Spring AI Reference — Observability](https://docs.spring.io/spring-ai/reference/observability/): quan sát ChatClient, model và tool trong Spring AI.
- [OpenTelemetry — Exemplars](https://opentelemetry.io/docs/specs/otel/metrics/data-model/#exemplars): liên kết mẫu metric với trace context.

**Lưu ý phiên bản:** API MeterFilter, naming convention, số series của Timer/DistributionSummary và khả năng exemplars phụ thuộc phiên bản Micrometer, Prometheus client, Spring Boot và backend. Các tên app.ai trong bài là ví dụ tự định nghĩa. Trước khi triển khai, xác minh API của phiên bản đang dùng, scrape thực tế và cardinality budget của môi trường.
