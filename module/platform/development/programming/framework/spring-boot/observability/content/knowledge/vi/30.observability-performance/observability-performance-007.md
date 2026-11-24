# Cardinality budget

Trong chương **Hiệu năng observability** của mô-đun **SPRING_BOOT_OBSERVABILITY**, cardinality budget là giới hạn có chủ đích cho số lượng time series mà metrics của một service được phép tạo ra. Mỗi tổ hợp metric name và label/tag values có thể trở thành một series riêng trong metrics backend. Khi tags chứa user ID, request ID, URL động hoặc SQL text, số tổ hợp tăng nhanh, kéo theo chi phí bộ nhớ, CPU, network, indexing và truy vấn.

Micrometer giúp chuẩn hóa meter và tags, nhưng không tự biết cardinality nào phù hợp với workload hay ngân sách hạ tầng. Đội phát triển cần quyết định dimensions nào có giá trị vận hành, giới hạn số giá trị cho mỗi dimension và theo dõi mức sử dụng theo thời gian. Cardinality budget biến yêu cầu "đừng tạo quá nhiều tags" thành một quy tắc có thể review, test và alert.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:
1. Giải thích cardinality và tác động của nó tới metrics backend.
2. Ước lượng số time series từ metric names, tags và histogram buckets.
3. Phân biệt low-cardinality metric dimensions với high-cardinality trace/log attributes.
4. Xây dựng cardinality budget theo service và metric family.
5. Phát hiện các nguồn cardinality tăng như URL, exception, tenant và SQL.
6. Chuẩn hóa route, dependency và outcome thành tập giá trị hữu hạn.
7. Dùng MeterFilter để giới hạn hoặc từ chối tag values theo policy.
8. Đánh giá chi phí của histogram, percentiles và nhiều registry.
9. Kiểm thử cardinality bằng dữ liệu đại diện và load test.
10. Theo dõi budget và xử lý sự cố khi series tăng bất thường.

## 2. Cardinality là gì?

Cardinality của một metric dimension là số giá trị khác nhau mà dimension đó có thể nhận. Với một metric có nhiều tags, số tổ hợp tag values có thể tạo thành số time series.

Ví dụ metric HTTP có các dimensions:
- method: GET, POST, PUT, DELETE (4 giá trị).
- status: 200, 400, 404, 500 (4 giá trị).
- uri: 20 route templates.
- outcome: SUCCESS, CLIENT_ERROR, SERVER_ERROR (3 giá trị).

Ước lượng tổ hợp tối đa:

~~~text
4 * 4 * 20 * 3 = 960 time series
~~~

Đây là upper bound đơn giản nếu mọi tổ hợp đều xuất hiện. Thực tế có thể thấp hơn do một số tổ hợp không hợp lệ, nhưng budget nên dựa trên khả năng tổ hợp lớn nhất có thể phát sinh, không dựa trên traffic của một ngày yên tĩnh.

Nếu thêm customerId với 100.000 giá trị, upper bound trở thành:

~~~text
4 * 4 * 20 * 3 * 100000 = 96,000,000 time series
~~~

Một tag có vẻ tiện để debug có thể làm metric family tăng từ hàng trăm lên hàng chục triệu series.

## 3. Time series và chi phí backend

Trong Prometheus-style metrics, một time series được xác định bởi metric name và toàn bộ label set. Khi bất kỳ label value nào thay đổi, một series khác được tạo.

~~~text
http_server_requests_seconds_count{method="GET",uri="/orders/{id}",status="200"}
http_server_requests_seconds_count{method="GET",uri="/orders/{id}",status="404"}
http_server_requests_seconds_count{method="POST",uri="/orders",status="201"}
~~~

Các series có cùng metric name nhưng label values khác nhau là các series riêng biệt. Backend phải lưu metadata và samples cho từng series, xử lý ingestion, index labels và phục vụ queries.

Cardinality cao có thể gây:
- Tăng RAM và disk usage.
- Tăng chi phí ingestion/network.
- Tăng thời gian index và query.
- Tăng số lượng active series và churn.
- Dashboard chậm hoặc query timeout.
- Backend đạt giới hạn series/tenant và từ chối samples.
- Chi phí cao khó dự báo khi traffic hoặc số identifiers tăng.

Cardinality không giống sample rate. Một series được scrape thường xuyên tạo nhiều samples; hàng triệu series được scrape thưa vẫn tạo chi phí lớn về metadata/index và active-series tracking.

## 4. Tính budget theo metric family

Liệt kê metric families quan trọng và dimensions của chúng. Ước lượng upper bound bằng tích số giá trị được phép ở từng dimension:

~~~text
series_budget(metric) =
    product(allowed_values_per_tag)
    * series_multiplier(metric_type)
~~~

Với counter/gauge đơn giản, multiplier thường là 1 cho mỗi label set. Với histogram, cần tính thêm buckets và các series tổng hợp như count/sum theo exporter format. Cách biểu diễn cụ thể tùy registry.

Ví dụ budget ban đầu cho HTTP request metrics:

| Dimension | Allowed values | Giới hạn |
| --- | ---: | --- |
| method | 5 | GET, POST, PUT, PATCH, DELETE |
| route | 30 | Route templates đã đăng ký |
| status | 8 | Status codes/nhóm được phép |
| outcome | 4 | SUCCESS, CLIENT_ERROR, SERVER_ERROR, UNKNOWN |

Upper bound:

~~~text
5 * 30 * 8 * 4 = 4,800 label combinations
~~~

Đây là con số thiết kế bảo thủ. Nếu method/status/outcome có quan hệ loại trừ, số tổ hợp thực tế thấp hơn. Khi lập budget, ghi rõ giả định và nguồn số lượng route/status để reviewer xác minh.

Không nên chỉ đặt một budget toàn service. Chia theo metric family giúp phát hiện metric nào gây tăng series, đồng thời cho phép ưu tiên budget lớn hơn ở metric thực sự cần nhiều dimensions.

## 5. Dimension nào nên nằm trong metrics?

Metrics dùng để trả lời câu hỏi tổng hợp: request nào đang chậm, dependency nào lỗi, throughput thay đổi ra sao, pool có cạn không? Chọn dimensions có tập giá trị hữu hạn và ổn định.

| Dimension | Metrics? | Cách dùng |
| --- | --- | --- |
| HTTP method | Có | Tập method hữu hạn. |
| Route template | Có | /orders/{orderId}, không dùng raw path. |
| Status/outcome | Có | Tập status/outcome được kiểm soát. |
| Service/dependency name | Có nếu danh sách ổn định | Chuẩn hóa thành logical service name. |
| Region/zone | Có nếu tập triển khai hữu hạn | Chỉ dùng khi phục vụ phân tích vận hành. |
| Tenant ID | Thường không | Dùng logs/traces có kiểm soát hoặc nhóm tenant tier. |
| User/customer ID | Không | Identifier theo từng người tạo cardinality lớn. |
| Request/trace ID | Không | Correlation trong logs/traces; exemplar nếu backend hỗ trợ. |
| Full URL/query string | Không | Dùng route template và bỏ query values. |
| Raw SQL/exception message | Không | Dùng operation/error type hoặc query fingerprint hữu hạn. |

Một dimension có số giá trị hữu hạn về lý thuyết vẫn có thể quá lớn trong thực tế. Ví dụ tenant ID có thể là tập hữu hạn nhưng tăng lên hàng trăm nghìn. Budget cần xét số lượng và tốc độ tăng, không chỉ việc giá trị có "finite" hay không.

## 6. Cardinality tăng theo phép nhân

Nhiều tag có cardinality vừa phải vẫn có thể tạo tổ hợp rất lớn khi nhân với nhau.

~~~text
route:       40 values
method:       5 values
status:      10 values
region:       8 values
tenant:     500 values
--------------------------------
upper bound = 8,000,000 combinations
~~~

Khi review một metric, hãy hỏi:
- Tag này có cần thiết cho dashboard/alert nào?
- Nó có nhân với dimensions hiện tại không?
- Giá trị mới có thể xuất hiện liên tục không?
- Có thể chuẩn hóa thành nhóm nhỏ hơn không?
- Có thể chuyển chi tiết sang logs/traces không?

Tránh nhân dimensions chỉ vì muốn có mọi bộ lọc trong dashboard. Mỗi label là một lựa chọn về chi phí lưu trữ và vận hành.

## 7. Route và URI normalization

HTTP metrics là nguồn cardinality cao phổ biến khi tag uri chứa raw path:

~~~text
/orders/1001
/orders/1002
/orders/1003
~~~

Dùng route template:

~~~text
/orders/{orderId}
~~~

Spring MVC/WebFlux instrumentation thường có khả năng sử dụng route pattern khi request đã được mapping. Với custom filters, gateway metrics hoặc client calls, cần kiểm tra giá trị thực tế. Nếu route không xác định, dùng nhóm an toàn như UNKNOWN hoặc NOT_FOUND, không fallback raw URI.

Đối với HTTP client, gọi URI bằng template API và chuẩn hóa destination thành service name. Không đưa query parameters chứa search terms, email, tokens hoặc IDs vào tags.

Các bước kiểm tra:
1. Tạo requests với nhiều IDs khác nhau.
2. Truy vấn available tag values của meter.
3. Xác nhận uri vẫn là route template.
4. Gửi path không match route và kiểm tra fallback.
5. Kiểm tra gateway/client instrumentation riêng biệt.

## 8. Exception, SQL và business identifiers

Không dùng exception class name nếu có hàng trăm dynamic proxy/generated class names; ưu tiên error category hoặc nhóm exception ổn định. Không dùng exception message vì message có thể chứa host, SQL, input hoặc identifiers.

Đối với SQL, dùng operation như SELECT/INSERT/UPDATE và datasource name. Nếu cần query-level analysis, dùng query fingerprint đã normalize và có giới hạn số lượng; không dùng raw SQL text hoặc bind values làm metric dimensions.

Với business identifiers, chuyển câu hỏi từ "tenant cụ thể nào?" sang "nhóm tenant nào?" nếu mục tiêu dashboard là capacity. Ví dụ tier free/standard/enterprise có thể phù hợp nếu số nhóm nhỏ và được quản lý. Điều tra một request/tenant cụ thể nên dựa vào trace/log search có quyền truy cập, retention và sampling policy phù hợp.

## 9. Histogram làm tăng series count

Histogram tạo nhiều series cho mỗi label set. Với Prometheus classic histogram, mỗi bucket là một series riêng; thường có thêm _count và _sum. Nếu histogram có 12 finite buckets cộng bucket +Inf, mỗi label set có thể tạo 14 series (13 bucket series và count/sum), tùy exposition format.

Ví dụ:

~~~text
base label combinations = 4,800
finite buckets           = 12
+Inf bucket              = 1
_count and _sum          = 2

approx series = 4,800 * (12 + 1 + 2)
              = 72,000
~~~

Đây là cách ước lượng classic histogram; native histograms hoặc registry khác có semantics khác. Kiểm tra exposition format và backend thực tế.

Nếu bật histogram cho nhiều metrics và mỗi metric có nhiều tag combinations, series count tăng theo cả hai chiều. Chỉ bật histogram cho latency metrics cần percentile/SLO; chọn bucket boundaries phù hợp; đánh giá chi phí khi thêm tag mới; dùng histogram buckets để aggregate percentile ở backend khi cần. Không cộng client-side percentiles.

## 10. Cardinality budget cho metrics và chi tiết cho traces/logs

Không phải mọi thông tin high-cardinality đều cần bị loại bỏ khỏi observability. Cần đặt đúng tín hiệu:

- **Metrics**: dimensions hữu hạn để aggregate và alert.
- **Traces**: attributes có thể chứa request-specific context nếu được phép, có sampling và retention phù hợp.
- **Logs**: structured fields để tìm sự kiện cụ thể, với access control và masking.
- **Exemplars**: liên kết một sample metric với trace ID khi registry/backend hỗ trợ, giúp chuyển từ metric spike sang trace mà không tạo trace ID thành metric label.

Thay vì thêm traceId vào mỗi metric series, dùng exemplar hoặc correlation field trong log. Điều này giữ metric cardinality ổn định mà vẫn hỗ trợ điều tra chi tiết. Traces/logs vẫn cần privacy review, masking, sampling, access control và retention.

## 11. Đặt giới hạn với Micrometer MeterFilter

Micrometer MeterFilter có thể giới hạn tag values hoặc loại bỏ tags/meter theo policy. Ví dụ dùng maximumAllowableTags để giới hạn số giá trị uri cho một meter name:

~~~java
@Configuration(proxyBeanMethods = false)
class MetricsCardinalityConfiguration {

    @Bean
    MeterFilter httpUriCardinalityLimit() {
        return MeterFilter.maximumAllowableTags(
                "http.server.requests",
                "uri",
                100,
                MeterFilter.deny());
    }
}
~~~

Filter này minh họa một giới hạn bảo vệ: khi vượt số tag values cho phép, meter mới có tag value vượt ngưỡng sẽ bị deny. Hành vi cụ thể phụ thuộc thứ tự filters và registry. Nó không thay thế việc chuẩn hóa route; nếu 100 raw paths đầu tiên đã lọt vào registry, cardinality vẫn không tốt.

Có thể dùng filter để loại bỏ tag không cần thiết:

~~~java
@Bean
MeterFilter removeUserTag() {
    return MeterFilter.ignoreTags("userId", "customerId", "requestId");
}
~~~

Tên API/behavior cần xác nhận theo Micrometer version được Boot quản lý. Filters nên được cấu hình tập trung và kiểm thử với registry thật. Không dựa vào filter để che lỗi thiết kế ở instrumentation source nếu có thể sửa nguồn tag.

Giới hạn cần hiểu:
- Filter có thể deny meter mới nhưng không nhất thiết xóa series đã được đăng ký trước đó.
- Registry có thể đã giữ meter và state trong memory.
- Backend có thể tiếp tục lưu series cũ đến khi hết retention/staleness policy.
- Filter không tự sanitize logs, spans hoặc baggage.
- Một filter limit không bảo đảm mọi metric families đều có budget hợp lý.

Khi cần thay đổi cardinality, ưu tiên sửa instrumentation/tag source, sau đó triển khai và theo dõi series churn.

## 12. Budget theo service và ownership

Một budget vận hành nên có owner và review cadence. Ví dụ:

| Metric family | Budget mục tiêu | Owner | Điều kiện review |
| --- | ---: | --- | --- |
| HTTP request timers | 5,000 label combinations | API team | Thêm route/tag mới. |
| HTTP client timers | 2,000 | Integration team | Thêm dependency/destination. |
| JDBC operation metrics | 500 | Data team | Thêm datasource/operation. |
| Scheduler/task metrics | 300 | Platform team | Thêm task type/outcome. |
| JVM/runtime metrics | Theo binder baseline | Platform team | Nâng binder/Boot version. |

Các số trên chỉ là ví dụ minh họa, không phải giới hạn phổ quát. Budget thực tế cần dựa trên backend capacity, scrape interval, retention, replica count, histogram configuration và nhu cầu truy vấn.

Đặt ownership rõ:
- Team sở hữu instrumentation chịu trách nhiệm tags.
- Platform/observability team theo dõi active series và backend capacity.
- Reviewer kiểm tra budget khi thêm metric/tag/route.
- Release process có thể yêu cầu so sánh cardinality trước/sau thay đổi.

## 13. Đo và giám sát cardinality thực tế

Đừng chỉ tin vào phép tính thiết kế. Theo dõi active series và series churn ở backend. Với Prometheus, có thể dùng self-metrics như TSDB series count và head series; tên metrics phụ thuộc version và deployment.

Ví dụ query minh họa:

~~~promql
prometheus_tsdb_head_series
~~~

Theo dõi số series theo job/tenant/backend nếu metrics backend cung cấp dimensions tương ứng. Phân biệt:
- Active series hiện tại.
- New series rate/churn.
- Total series trong retention.
- Ingestion samples/second.
- Cardinality theo metric name và label.

Một metric family có thể tạo nhiều series dù samples/second thấp. Ngược lại, một số ít series có scrape rate cao vẫn tạo ingestion load đáng kể.

So sánh baseline theo service/release. Khi thêm tag hoặc route mới, đo trước và sau deploy; kiểm tra số series, memory và query latency.

## 14. Kiểm thử cardinality budget

Kiểm thử nên tạo nhiều input khác nhau nhưng cùng thuộc một logical route/operation để xác nhận tags được normalize.

Ví dụ test ý tưởng với SimpleMeterRegistry:

~~~java
@Test
void uriTagUsesRouteTemplate() {
    MeterRegistry registry = new SimpleMeterRegistry();

    // Ghi nhận các request với IDs khác nhau.
    recordRequest(registry, "/orders/{orderId}", "GET");
    recordRequest(registry, "/orders/{orderId}", "GET");
    recordRequest(registry, "/orders/{orderId}", "GET");

    Set<String> uriValues = registry.find("http.server.requests")
            .meters()
            .stream()
            .flatMap(meter -> meter.getId().getTags().stream())
            .filter(tag -> tag.getKey().equals("uri"))
            .map(Tag::getValue)
            .collect(Collectors.toSet());

    assertThat(uriValues).containsExactly("/orders/{orderId}");
}
~~~

Đây là skeleton minh họa; helper recordRequest cần dùng đúng instrumentation của ứng dụng, không chỉ tự thêm tag template để test luôn pass. Integration test nên gửi HTTP requests thật tới nhiều path IDs và kiểm tra meter registry sau khi framework đã resolve route.

Các test cần có:
1. Nhiều IDs trên cùng route chỉ tạo một uri tag value.
2. Raw query parameters không xuất hiện trong tags.
3. User/request/tenant IDs không có trong metric tags.
4. Exception messages không được dùng làm dimensions.
5. Số tag values không vượt limit đã cấu hình.
6. Histogram bucket count nằm trong dự toán.
7. Meter filters hoạt động theo đúng version.
8. Load test tạo route/destination distribution đại diện production.

## 15. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Active series tăng đột biến | Tag mới chứa IDs, URL hoặc exception messages. | Phân tích series theo metric name và labels. |
| uri có hàng nghìn values | Raw path được dùng thay route template. | Kiểm tra MVC/WebFlux/gateway/client instrumentation. |
| Metrics backend từ chối samples | Series/tenant limit hoặc ingestion capacity bị vượt. | Kiểm tra backend limits và series churn. |
| Histogram tạo series nhiều hơn dự kiến | Bucket count nhân với label combinations. | Kiểm tra exposition format và bucket configuration. |
| Meter bị deny sau ngưỡng | maximumAllowableTags đã chặn tag values mới. | Xác định nguồn tag và normalize tại source. |
| Dashboard query chậm | Query scan quá nhiều series/label combinations. | Giảm dimensions và scope query. |
| Series cũ vẫn còn sau khi sửa tag | Backend retention/staleness và registry lifecycle. | Theo dõi expiry; không kỳ vọng filter xóa historical data. |
| Chỉ một replica có cardinality cao | Input distribution hoặc config khác giữa replicas. | So sánh build/config và tag values theo instance. |
| Trace/log search khó sau khi bỏ ID tag | Correlation chưa được thiết kế. | Dùng trace IDs, structured logs hoặc exemplars. |
| Budget tăng sau nâng cấp | Instrumentation/binder thêm tags hoặc routes. | So sánh metric metadata và series baseline trước/sau. |

## 16. Runbook: cardinality vượt budget

1. Xác định backend, tenant và service có active series tăng.
2. Tìm metric families đóng góp nhiều series nhất.
3. So sánh label names/values với budget đã phê duyệt.
4. Xác định tag mới hoặc tag value tăng liên tục.
5. Kiểm tra route normalization, destination naming và exception mapping.
6. Tạm ngăn nguồn tạo thêm series nếu có thể bằng filter/config phù hợp.
7. Sửa instrumentation source để bỏ ID/raw URL/SQL hoặc chuẩn hóa thành nhóm hữu hạn.
8. Kiểm thử với dữ liệu đại diện và xác minh upper bound mới.
9. Deploy theo rollout có theo dõi active series, ingestion và memory.
10. Đánh giá ảnh hưởng tới dashboards/alerts cần dimensions đã loại bỏ.
11. Chờ backend retention/staleness xử lý series cũ; kiểm tra chính sách deletion nếu cần.
12. Cập nhật budget, owner và regression tests để tránh tái diễn.

Không xử lý bằng cách tăng backend limit trước khi xác định nguồn cardinality. Tăng limit có thể trì hoãn sự cố và làm chi phí tăng nhanh hơn.

## 17. Bài tập tự kiểm tra

### Bài 1 — Tính series

Một metric có 6 method values, 12 route values và 5 status values. Upper bound label combinations là bao nhiêu?

**Đáp án:** 6 × 12 × 5 = 360 combinations, giả định mọi tổ hợp đều có thể xuất hiện.

### Bài 2 — Thêm tenant ID

Metric trên thêm tag tenant với 2.000 values. Upper bound mới là bao nhiêu?

**Đáp án:** 360 × 2.000 = 720.000 combinations. Một dimension tăng cardinality mạnh dù ba dimensions ban đầu khá nhỏ.

### Bài 3 — Raw URI

Requests tới /orders/1, /orders/2, /orders/3 tạo ba uri values. Cách sửa?

**Đáp án:** Dùng route template /orders/{orderId} hoặc fallback route ổn định. Không dùng raw path làm metric tag.

### Bài 4 — Histogram

Metric có 1.000 label combinations và classic histogram gồm 10 finite buckets, một +Inf, _count và _sum. Ước lượng series?

**Đáp án:** 1.000 × (10 + 1 + 2) = 13.000 series, theo cách export classic histogram đang giả định.

### Bài 5 — Cần tìm một request cụ thể

Đội vận hành muốn lọc metric theo trace ID. Nên thêm trace ID làm tag?

**Đáp án:** Không. Dùng trace backend, structured logs hoặc exemplars nếu hỗ trợ để liên kết metric sample với trace.

### Bài 6 — Filter đã chặn

Sau khi thêm maximumAllowableTags, backend vẫn còn series cũ. Đây có phải filter không hoạt động?

**Đáp án:** Không nhất thiết. Filter ngăn meter mới vượt ngưỡng; nó không tự xóa series đã được tạo hoặc dữ liệu lịch sử trong backend.

## 18. Checklist triển khai

- [ ] Mỗi metric family có danh sách dimensions và upper-bound budget.
- [ ] Budget tính theo tích các tag values, không chỉ từng tag riêng.
- [ ] Histogram buckets/count/sum được tính vào series estimate.
- [ ] HTTP metrics dùng route templates thay raw paths/query strings.
- [ ] Dependency/datasource/task names được chuẩn hóa và có tập giá trị hữu hạn.
- [ ] Không dùng user, tenant, request, trace, order IDs hoặc timestamps làm metric tags.
- [ ] Không dùng raw SQL hoặc exception messages làm dimensions.
- [ ] High-cardinality details được đặt trong logs/traces có masking, sampling và access policy.
- [ ] Exemplar được cân nhắc cho metric-to-trace correlation khi backend hỗ trợ.
- [ ] MeterFilter limits được cấu hình và kiểm thử; không xem chúng là thay thế normalization.
- [ ] Histogram chỉ bật ở metric cần phân tích latency/SLO.
- [ ] Budget có owner và được review khi thêm metric/tag/route.
- [ ] Integration/load tests dùng input distribution đại diện production.
- [ ] Active series, churn, ingestion và backend limits được theo dõi.
- [ ] Có runbook để xác định metric family/tag gây tăng cardinality.
- [ ] Dashboard/alert được rà soát khi loại bỏ dimensions.

**Ghi nhớ:** Cardinality budget kiểm soát số series bằng cách giới hạn tổ hợp metric name và tag values. Ước lượng bằng phép nhân dimensions, tính thêm histogram buckets, chuẩn hóa route/destination/error values và giữ identifiers ở logs/traces thay vì metric labels. Dùng MeterFilter như lớp bảo vệ, kiểm thử với dữ liệu đại diện và theo dõi active series/churn để phát hiện budget bị vượt trước khi backend quá tải.
