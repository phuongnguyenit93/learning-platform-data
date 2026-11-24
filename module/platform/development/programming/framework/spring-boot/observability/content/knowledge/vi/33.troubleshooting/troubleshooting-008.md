# Cardinality tăng bất thường

Trong chương **Chẩn đoán sự cố** của mô-đun **SPRING_BOOT_OBSERVABILITY**, cardinality tăng bất thường là tình trạng số lượng time series hoặc số giá trị label/tag của metrics tăng nhanh vượt baseline hay budget. Trong Spring Boot, nguyên nhân thường gặp là tag chứa raw URI, request/user/tenant ID, exception message, SQL text hoặc dimension mới được thêm vào Observation convention. Histogram mới bật, số replicas tăng và thay đổi instrumentation sau khi nâng cấp cũng có thể làm series count tăng mà không phải do một tag bị lỗi.

Cardinality spike có thể làm Prometheus hoặc metrics backend tiêu thụ nhiều RAM, index và ingestion capacity; query chậm, scrape/export bị drop hoặc chạm giới hạn tenant. Chẩn đoán hiệu quả cần xác định metric family nào tạo thêm series, label nào có tập giá trị tăng, thay đổi nào xuất hiện trước thời điểm spike và liệu mức tăng đến từ replicas/histogram hay values động. Sau đó cần chặn nguồn phát sinh, chuẩn hóa instrumentation và xác minh dữ liệu sau deploy.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:
1. Nhận biết cardinality spike qua active series, churn và backend symptoms.
2. Phân biệt tăng series với tăng samples/second.
3. Khoanh vùng metric family và label gây tăng.
4. Phân biệt tag explosion với replica scaling, histogram và deployment changes.
5. Truy nguồn tag từ Micrometer binders, Observation conventions và custom instrumentation.
6. Chuẩn hóa URI, dependency, SQL operation và error categories.
7. Dùng MeterFilter như lớp containment có giới hạn.
8. Ước lượng tác động của series count tới backend và histogram.
9. Xác minh fix bằng integration/load tests và theo dõi sau deploy.
10. Cập nhật budget, ownership và runbook để tránh tái diễn.

## 2. Dấu hiệu nhận biết cardinality spike

Cardinality spike thường biểu hiện qua một hoặc nhiều dấu hiệu:
- Active series tăng nhanh trong thời gian ngắn.
- Số series mới mỗi phút tăng mạnh dù traffic không đổi nhiều.
- Prometheus head memory hoặc TSDB index tăng.
- Metrics backend báo series/tenant limit, ingestion rejection hoặc metadata pressure.
- Dashboard và PromQL queries chậm hơn.
- Scrape/export duration tăng hoặc samples bị drop.
- Một metric family có nhiều label values bất thường.
- Một release gần đây thêm route, tag, binder hoặc histogram configuration.

Phân biệt các tín hiệu:

| Tín hiệu | Ý nghĩa | Ví dụ nguyên nhân |
| --- | --- | --- |
| Active time series | Số chuỗi metric/label set đang hoạt động. | Thêm tag requestId với mỗi request một giá trị. |
| Samples per second | Tốc độ samples được ingest. | Scrape interval ngắn hơn hoặc traffic tăng. |
| Series churn | Tốc độ tạo và ngừng hoạt động của series. | Raw path IDs hoặc ephemeral tenant IDs. |
| Histogram bucket series | Số chuỗi phát sinh từ mỗi histogram label set. | Bật thêm buckets hoặc thêm tag vào Timer. |

Traffic tăng có thể làm samples/second tăng nhưng không nhất thiết làm cardinality tăng. Nếu active series tăng tuyến tính theo số request hoặc số entity khác nhau, hãy nghi ngờ một tag đang nhận dynamic values.

## 3. Quy trình khoanh vùng nhanh

~~~mermaid
flowchart TD
    Spike["Cardinality spike detected"]
    Spike --> Time["Mark first-seen time / release"]
    Time --> Families["Rank metric families by series"]
    Families --> Labels["Inspect label names and value counts"]
    Labels --> Cause{"Likely cause?"}
    Cause -->|Dynamic values| Source["Trace tag to instrumentation"]
    Cause -->|Histogram| Buckets["Check buckets and distribution config"]
    Cause -->|Replica growth| Replicas["Compare per-instance series"]
    Cause -->|Backend/query| Backend["Check ingestion and TSDB limits"]
    Source --> Fix["Contain and normalize tags"]
    Buckets --> Fix
    Replicas --> Fix
    Backend --> Fix
    Fix --> Verify["Test budget and verify after deploy"]
~~~

Thu thập tối thiểu:
1. Thời điểm bắt đầu tăng và release/config thay đổi gần nhất.
2. Active series hiện tại so với baseline.
3. Top metric names theo số series.
4. Label names và số distinct values của metric nghi vấn.
5. Số replicas/targets và scrape interval.
6. Histogram bucket configuration.
7. Backend warnings, dropped samples và ingestion errors.

Đừng bắt đầu bằng cách tăng giới hạn backend. Trước tiên cần tìm dimension gây tăng để tránh làm chi phí và blast radius lớn hơn.

## 4. Kiểm tra Prometheus và metrics backend

Với Prometheus, có thể bắt đầu bằng self-metric của TSDB:

~~~promql
prometheus_tsdb_head_series
~~~

Metric này cho biết số series trong head block; tên và availability có thể phụ thuộc version. Xem thêm self-metrics liên quan tới series creation/removal, memory, WAL và scrape samples nếu deployment expose chúng.

Để xem target scrape:

~~~promql
up{job="spring-boot"}
~~~

Để ước lượng số series theo metric name trong phạm vi selector:

~~~promql
count by (__name__) ({job="spring-boot"})
~~~

Selector và query semantics cần điều chỉnh theo labels thực tế. Với backend lớn, dùng cardinality explorer/TSDB status API phù hợp thay vì chạy query cực rộng liên tục.

Đối với remote-write/managed metrics backends, kiểm tra active series per tenant/project, ingestion rate và rejected samples, cardinality/series limit events, top metrics và top label names, cùng per-service/per-job breakdown nếu backend hỗ trợ.

Không giả định metric nội bộ Prometheus có cùng tên ở mọi phiên bản hoặc managed backend. Kiểm tra self-metrics đang được scrape trong chính môi trường.

## 5. Xác định metric family gây tăng

Tìm metric names có series count tăng mạnh so với baseline. Các family thường đáng kiểm tra trong Spring Boot:
- http.server.requests hoặc tên export tương đương.
- http.client.requests.
- JDBC/data source và connection pool metrics.
- Business timers/counters có custom tags.
- Messaging, scheduler và executor metrics.
- Metrics được tạo từ Observation conventions.
- Histogram families có buckets.

Khi tìm được family, so sánh label set giữa thời điểm trước và sau spike. Ví dụ một metric HTTP trước đây có method, uri, status; sau release xuất hiện thêm tenantId. Hoặc uri chuyển từ route template sang raw path.

Cần xem distinct values theo từng label, không chỉ tổng số series. Một label có 10.000 values thường dễ nhận diện hơn một metric có 10.000 tổ hợp từ nhiều labels nhỏ.

## 6. Phát hiện các tag có dynamic values

Các tag sau thường là nguồn cardinality không kiểm soát:

| Tag/value source | Dấu hiệu | Cách sửa |
| --- | --- | --- |
| uri raw path | /orders/1001, /orders/1002 | Dùng route template /orders/{id}. |
| requestId / traceId | UUID khác nhau theo request | Loại khỏi metric tags; dùng logs/traces/exemplars. |
| userId / tenantId | Mỗi user/tenant một series | Dùng nhóm/tier hữu hạn nếu cần aggregate. |
| exception.message | Message chứa input, host hoặc SQL | Map sang error category ổn định. |
| Raw SQL | Literal values khác nhau | Dùng operation hoặc fingerprint đã normalize và giới hạn. |
| Full URL/query | Query string có search terms/IDs | Dùng route template và bỏ query values. |
| Dynamic dependency host | Pod/IP/host thay đổi | Dùng logical dependency/service name. |

Kiểm tra cả tag key aliases như user_id, user-id, customer, tenant. Một blacklist chỉ khớp đúng một spelling có thể bỏ sót convention khác.

## 7. Truy nguồn tag trong Spring Boot và Micrometer

Khi đã xác định label gây tăng, tìm nơi value được gắn vào meter:
- MeterRegistry.counter/timer/gauge và Tags.of(...).
- MeterFilter hoặc custom registry configuration.
- ObservationConvention.getLowCardinalityKeyValues(...).
- Observation.lowCardinalityKeyValue(...).
- @Timed extra tags và custom aspects.
- Web MVC/WebFlux filters, interceptors và HTTP client instrumentation.
- Database, messaging và executor instrumentation.
- Auto-configured binders sau khi nâng Spring Boot/Micrometer version.

Tìm kiếm source theo tag key và metric name, sau đó lần theo caller để hiểu value đến từ request/context nào. Với Observation, kiểm tra rõ key-value nào là low-cardinality và key-value nào là high-cardinality; không đưa request-specific values vào low-cardinality values.

Một convention an toàn chỉ thêm giá trị hữu hạn:

~~~java
class OrderObservationConvention
        implements ObservationConvention<Observation.Context> {

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context.getName() != null
                && context.getName().startsWith("order.");
    }

    @Override
    public KeyValues getLowCardinalityKeyValues(
            Observation.Context context) {
        return KeyValues.of(
                KeyValue.of("operation", "order.process"),
                KeyValue.of("outcome", "success")
        );
    }
}
~~~

Ví dụ minh họa cần điều chỉnh context/convention theo instrumentation thực tế. Không đọc principal, request ID, raw URL hoặc entity ID để tạo low-cardinality tags.

## 8. Kiểm tra URI và HTTP instrumentation

Raw URI là nguyên nhân phổ biến vì mỗi resource ID có thể tạo một label value. So sánh:

~~~text
/orders/1001
/orders/1002
/orders/1003
~~~

với route template:

~~~text
/orders/{orderId}
~~~

Gửi nhiều requests với IDs khác nhau và kiểm tra uri tag trong MeterRegistry. Nếu framework instrumentation đã dùng route pattern, giữ behavior đó; nếu custom filter tự tạo meter, lấy route template từ mapping metadata thay vì raw request URI.

Đối với unknown routes, dùng fallback ổn định như UNKNOWN hoặc NOT_FOUND; không ghi raw path. Không đưa query string, email hoặc search terms vào tag values.

Kiểm tra HTTP client riêng biệt: destination nên là logical service name hoặc URI template đã chuẩn hóa, không phải host/IP động hay full URL với query parameters.

## 9. Kiểm tra exception, SQL và business tags

Nếu spike bắt đầu cùng lúc một custom error metric được thêm, kiểm tra tag exception, error, message hoặc sql. Exception messages có thể chứa SQL statement/literals, hostname/port, user input, UUID/request IDs hoặc downstream response text.

Map các lỗi vào taxonomy nhỏ, ví dụ timeout, validation, dependency, database, unexpected. Dùng exception family ổn định nếu taxonomy phù hợp; tránh class names được generate động.

Với database, dùng operation như SELECT/INSERT/UPDATE, datasource name ổn định và query fingerprint đã normalize nếu có nhu cầu. Không dùng raw SQL hoặc bind values làm metric tags.

Với tenant, cân nhắc dimension tenant_tier có tập giá trị nhỏ như standard/enterprise nếu thực sự phục vụ dashboard. Điều tra tenant cụ thể nên dùng logs/traces được bảo vệ.

## 10. Histogram và replica multiplication

Series count không chỉ tăng vì tag values. Classic Prometheus histogram tạo nhiều series cho mỗi label set: một series cho mỗi bucket, cộng _count và _sum.

Ví dụ 10 finite buckets, một +Inf, count và sum tạo khoảng 13 series cho mỗi label combination. Nếu base combinations là 2.000:

~~~text
2,000 * (10 + 1 + 2) = 26,000 series
~~~

Nếu thêm một tag với 100 values, ước lượng thành 2.600.000 series theo cùng giả định. Kiểm tra exporter format vì native histograms/OTLP có representation khác.

Số replicas cũng có thể làm tổng series tăng. Mỗi replica có thể export cùng metric family với label instance khác nhau. So sánh series per instance, số active targets/replicas, series count trước/sau autoscaling, tag values mới trong từng instance và histogram configuration giữa environments.

Replica scaling tạo mức tăng gần tuyến tính theo số instances; tag explosion thường làm series trên từng instance tăng theo input diversity. Phân biệt hai nguồn này trước khi thay đổi code.

## 11. Dùng MeterFilter để containment

Micrometer MeterFilter.maximumAllowableTags có thể ngăn một meter tạo thêm values sau ngưỡng:

~~~java
@Bean
MeterFilter uriCardinalityGuard() {
    return MeterFilter.maximumAllowableTags(
            "http.server.requests",
            "uri",
            100,
            MeterFilter.deny()
    );
}
~~~

Đây là lớp bảo vệ, không phải giải pháp chuẩn hóa. Nếu 100 raw URI đầu tiên đã được đăng ký, registry vẫn giữ các meters đó. Filter cũng không xóa series lịch sử trong backend và không áp dụng cho logs/traces.

Dùng filter khi cần giới hạn blast radius trong lúc sửa nguồn tag. Theo dõi meter registration/rejection nếu implementation cung cấp diagnostics. Đặt filter trước khi meters được tạo và xác minh đúng meter name/tag key cùng filter order.

Không tăng ngưỡng chỉ để làm alert biến mất. Chọn limit dựa trên budget được duyệt và ghi nhận lý do.

## 12. Biện pháp containment khi sự cố đang diễn ra

Khi backend gần chạm limit:
1. Xác định metric family và label value gây tăng.
2. Nếu có thể, disable instrumentation hoặc tag source gây spike qua cấu hình an toàn.
3. Áp dụng MeterFilter limit phù hợp để ngăn series mới, nếu đã kiểm thử hành vi.
4. Tạm dừng rollout/release vừa đưa tag mới vào production.
5. Tránh tăng scrape frequency hoặc bật thêm histogram trong lúc điều tra.
6. Theo dõi active series, ingestion rejection và backend memory.
7. Đánh giá dashboards/alerts có phụ thuộc tag cần loại bỏ.
8. Không xóa dữ liệu hoặc restart toàn bộ monitoring stack khi chưa hiểu tác động.

Containment cần phối hợp với platform/observability owner vì một thay đổi filter có thể làm mất meter cần cho alerting. Ưu tiên giữ các tín hiệu cốt lõi như request rate, error rate và latency với bounded dimensions.

## 13. Kiểm thử fix và xác minh sau deploy

Trước khi deploy fix:
- Tạo generated user/tenant/order/request IDs.
- Gửi nhiều requests qua route thật.
- Assert số URI tag values bằng số route templates.
- Assert không có request/user/tenant/trace IDs trong metric tags.
- Assert error categories thuộc allowlist.
- Kiểm tra MeterFilter behavior khi vượt ngưỡng.
- Tính lại histogram multiplier và per-replica series budget.
- Kiểm tra Prometheus exposition hoặc exporter output.

Sau deploy, theo dõi active series và new-series rate, top metric families/labels, series per instance và số replicas, scrape/export errors và rejected samples, Prometheus memory/TSDB head growth, query latency và dashboards/alerts.

Không kết luận fix thành công chỉ vì tổng series giảm trong vài phút; backend có thể giữ series cũ cho tới khi stale/retention policy xử lý. So sánh trend và series mới phát sinh sau release.

## 14. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Active series tăng nhưng traffic ổn định | Tag value động hoặc histogram mới. | Top metric families và distinct label values. |
| Series tăng gần đúng theo replica count | Autoscaling hoặc instance label mới. | So sánh series per instance và target count. |
| Một metric HTTP tăng đột biến | Raw URI/query hoặc tag mới. | Kiểm tra uri, method, status và custom conventions. |
| uri chứa resource IDs | Custom instrumentation dùng raw path. | Lấy route template từ framework mapping. |
| Series chỉ tăng trên error path | Exception message/class được dùng làm tag. | Map error thành taxonomy bounded. |
| Series tăng sau nâng Boot/Micrometer | Binder/convention/default tags thay đổi. | So sánh meter metadata trước/sau upgrade. |
| Histogram series tăng mạnh | Thêm buckets hoặc bật histogram cho nhiều meters. | Kiểm tra distribution configuration và exposition format. |
| MeterFilter không chặn | Sai meter name/key, filter đăng ký muộn hoặc order sai. | Kiểm tra registry config và exact meter ID. |
| Backend vẫn có series cũ sau fix | Staleness/retention chưa hết hoặc registry giữ meters. | Theo dõi series churn và backend retention. |
| Scrape/export bị drop | Backend limit, network hoặc exporter queue pressure. | Kiểm tra target status, dropped samples và exporter diagnostics. |
| Query chậm dù active series không tăng | Samples/second, query scope hoặc backend contention. | Phân biệt ingestion rate với cardinality. |

## 15. Runbook: cardinality tăng bất thường

1. Ghi nhận thời điểm spike, service, environment và release gần nhất.
2. Xác minh active series, churn và samples/second để phân biệt cardinality với ingestion volume.
3. Xếp hạng metric families theo series count.
4. Tìm label có distinct values tăng mạnh.
5. So sánh với thay đổi tags, routes, binders, histograms và replica count.
6. Truy nguồn tag về MeterRegistry, MeterFilter, ObservationConvention hoặc instrumentation cụ thể.
7. Xác định tag có chứa ID, raw URI, query, SQL, exception message hay host động không.
8. Contain nguồn tạo series mới; cân nhắc MeterFilter và tạm dừng rollout.
9. Chuẩn hóa values thành route template, logical dependency name hoặc bounded error category.
10. Cập nhật integration/property-based tests và cardinality budget.
11. Deploy có theo dõi; xác minh active series mới ổn định và exporter không drop.
12. Cập nhật dashboard, alert, owner và incident record.

## 16. Bài tập tự kiểm tra

### Bài 1 — Traffic hay cardinality?

Traffic tăng gấp đôi nhưng active series gần như không đổi; samples/second tăng gấp đôi. Đây có phải cardinality spike không?

**Đáp án:** Không nhất thiết. Đây chủ yếu là ingestion/sample volume tăng. Cardinality đo số label sets khác nhau, cần kiểm tra active series và churn.

### Bài 2 — Raw URI

http.server.requests tăng hàng triệu series và uri có /orders/12345. Nguyên nhân và cách sửa?

**Đáp án:** Raw path chứa resource ID đang trở thành tag value. Dùng route template /orders/{id} hoặc fallback bounded cho unknown routes.

### Bài 3 — Replica scaling

Series count tăng từ 10.000 lên 20.000 cùng lúc replicas tăng từ 5 lên 10, trong khi series per instance không đổi. Điều này gợi ý điều gì?

**Đáp án:** Mức tăng có thể do replica multiplication. Kiểm tra label instance, target count và tổng budget theo số replicas.

### Bài 4 — Histogram

Base label combinations là 2.000; classic histogram có 10 finite buckets, một +Inf, _count và _sum. Ước lượng series?

**Đáp án:** 2.000 × (10 + 1 + 2) = 26.000 series theo exposition format giả định.

### Bài 5 — MeterFilter

Sau khi thêm maximumAllowableTags, series cũ vẫn tồn tại. Filter có hỏng không?

**Đáp án:** Không nhất thiết. Filter ngăn meter mới vượt ngưỡng; nó không xóa meters đã tạo hoặc dữ liệu lịch sử trong backend.

### Bài 6 — Exception tag

Metric app.operation có tag error với values là nguyên exception messages. Nên sửa thế nào?

**Đáp án:** Map lỗi về nhóm bounded như timeout, validation, dependency hoặc unexpected; giữ chi tiết cần thiết trong logs/traces đã được kiểm soát.

## 17. Checklist phòng ngừa tái diễn

- [ ] Có baseline active series và churn theo service/metric family.
- [ ] Mỗi metric family có cardinality budget và owner.
- [ ] Không dùng request/user/tenant/trace IDs làm metric tags.
- [ ] HTTP metrics dùng route templates và bỏ query parameters.
- [ ] Dependency tags dùng logical names ổn định.
- [ ] Exception/error tags dùng taxonomy bounded.
- [ ] Raw SQL và bind values không xuất hiện trong metric labels.
- [ ] Histogram buckets được tính vào series budget.
- [ ] Replica count và per-instance series được theo dõi riêng.
- [ ] MeterFilter guardrails được cấu hình trước khi meter tạo và có test.
- [ ] Integration tests gửi nhiều identifiers qua instrumentation thật.
- [ ] Có regression test cho route normalization và error categories.
- [ ] Theo dõi backend active series, churn, ingestion rejection và query latency.
- [ ] Có runbook containment và owner phối hợp khi backend gần limit.
- [ ] Sau deploy, xác minh series mới ổn định; không chỉ nhìn tổng series tức thời.
- [ ] Review cardinality khi nâng Boot/Micrometer hoặc thêm binder/tag/histogram.

**Ghi nhớ:** Khi cardinality tăng bất thường, tìm metric family và label values trước, rồi phân biệt tag explosion với histogram, replica scaling và sample volume. Truy nguồn tag về instrumentation của Spring Boot/Micrometer, chuẩn hóa dynamic values, dùng MeterFilter để containment và xác minh fix bằng tests cùng dữ liệu backend sau deploy. Đừng chỉ tăng giới hạn metrics backend khi chưa loại bỏ nguồn tạo series ngoài kiểm soát.
