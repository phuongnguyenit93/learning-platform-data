# Kiểm tra thay đổi tên, tag, đơn vị và dữ liệu công bố trước khi nâng cấp

Metrics là một hợp đồng dữ liệu giữa ứng dụng, hệ thống thu thập và người sử dụng dữ liệu. Dashboard, alert, recording rule và báo cáo đều phụ thuộc vào tên meter, loại dữ liệu, tag, đơn vị và cách exporter công bố sample. Một thay đổi code có thể không làm hỏng ứng dụng nhưng vẫn khiến dashboard trống, alert không chạy hoặc hai phiên bản bị gộp thành một chuỗi dữ liệu sai nghĩa.

Trước khi nâng cấp Micrometer, Spring Boot, exporter hoặc instrumentation, hãy kiểm tra metric contract hiện tại và so sánh với contract sau nâng cấp. Mục tiêu là xác định thay đổi nào tương thích, thay đổi nào tạo series mới và cách chuyển dashboard/query mà không làm mất khả năng quan sát trong lúc rollout.

## 1. Metric contract gồm những gì?

Một meter không chỉ có tên. Khi đánh giá thay đổi, cần kiểm tra toàn bộ các thuộc tính ảnh hưởng đến identity và cách dữ liệu được diễn giải:

| Thuộc tính | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Name | Tên canonical có đổi không? | business.checkout.duration |
| Type | Counter, Gauge, Timer hay DistributionSummary? | Timer |
| Tags | Key/value có đổi, bị bỏ hoặc thêm không? | outcome=success |
| Base unit | Đại lượng được đo bằng đơn vị nào? | seconds, bytes |
| Description | Ý nghĩa nghiệp vụ có còn đúng không? | Thời gian hoàn tất checkout |
| Distribution | Histogram, percentile và SLO boundaries có đổi không? | 100 ms, 300 ms, 1 s |
| Naming convention | Tên được exporter chuẩn hóa ra sao? | business_checkout_duration_seconds |
| Temporality | Dữ liệu tích lũy hay delta? | cumulative counter |
| Publication | Endpoint, protocol và resource attributes có đổi không? | /actuator/prometheus |

Meter identity trong registry thường dựa trên tên và tập tags. Cùng một tên nhưng tag key hoặc tag value khác sẽ tạo series khác. Một meter có cùng identity nhưng đổi type hoặc semantics có thể gây xung đột hoặc làm dữ liệu không thể diễn giải nhất quán.

Metric contract cần được quản lý như API contract: có chủ sở hữu, mô tả, thay đổi có kiểm soát và kiểm thử tương thích.

## 2. Kiểm kê metric schema trước khi nâng cấp

Trước khi thay dependency hoặc code instrumentation, lưu lại baseline của phiên bản hiện tại:

1. Danh sách meter name.
2. Meter type và base unit.
3. Tag keys cùng các giá trị đại diện.
4. Description và ý nghĩa nghiệp vụ.
5. Histogram buckets, percentile và SLO boundaries.
6. Tên metric sau NamingConvention của từng exporter.
7. Endpoint hoặc giao thức công bố dữ liệu.
8. Dashboard, alert, recording rule và query đang tham chiếu.

Có thể lấy danh sách meter trong registry ở môi trường phát triển:

~~~java
registry.getMeters().stream()
    .map(Meter::getId)
    .sorted(Comparator.comparing(Meter.Id::getName))
    .forEach(id -> System.out.println(
        id.getName() + " " + id.getType() + " " + id.getTags()
    ));
~~~

Đoạn code minh họa việc kiểm kê trong bộ nhớ. Với hệ thống đang chạy, Actuator Metrics hoặc endpoint exposition có thể cung cấp góc nhìn gần với dữ liệu người vận hành sử dụng hơn.

Prometheus endpoint:

~~~text
GET /actuator/prometheus
~~~

Actuator Metrics endpoint:

~~~text
GET /actuator/metrics
GET /actuator/metrics/business.checkout.duration
~~~

Hai endpoint phục vụ mục đích khác nhau. Metrics endpoint cho phép tra cứu meter theo tên canonical của Micrometer; Prometheus endpoint thể hiện tên và labels sau khi áp dụng Prometheus NamingConvention. Không lấy tên từ một endpoint rồi giả định tên ở endpoint kia giống hệt.

## 3. Kiểm tra thay đổi tên meter

Đổi tên meter làm thay đổi identity và thường tạo một time series mới ở backend. Ví dụ:

| Trước nâng cấp | Sau nâng cấp | Tác động |
| --- | --- | --- |
| orders.created | business.orders.created | Query cũ không còn thấy series mới |
| http.client.requests | http.client.request | Dashboard có thể mất dữ liệu nếu chỉ truy vấn tên cũ |
| checkout.duration | business.checkout.duration | Tên mới cần cập nhật alert và recording rule |

Tên canonical của Micrometer và tên xuất ra backend có thể khác nhau do NamingConvention. Prometheus thường chuyển dấu chấm thành dấu gạch dưới và bổ sung hậu tố đơn vị hoặc type phù hợp. Vì vậy, khi nâng cấp registry/exporter, hãy kiểm tra cả hai lớp:

- Tên canonical được code đăng ký.
- Tên thực tế trong exposition hoặc backend.

Không đổi tên chỉ để làm tên đẹp hơn nếu không có lợi ích rõ ràng. Nếu cần đổi, hãy xác định dashboard và consumer nào đang dùng tên cũ, rồi lên kế hoạch chuyển tiếp.

### Đổi tên có giữ nguyên semantics

Nếu tên mới chỉ là cách gọi mới của cùng đại lượng, có thể công bố cả hai tên trong giai đoạn chuyển tiếp hoặc tạo recording rule tương thích ở backend. Không cộng dữ liệu cũ và mới với nhau nếu cả hai đang đo cùng một event; điều đó sẽ đếm đôi.

Một cách chuyển tiếp an toàn:

1. Xác định tên cũ và tên mới cùng đo một đại lượng.
2. Kiểm tra hai meter không cùng ghi nhận một event vào cùng query tổng hợp.
3. Cập nhật dashboard để ưu tiên tên mới và có fallback cho dữ liệu cũ nếu cần.
4. Giữ query tương thích trong khoảng thời gian dữ liệu cũ còn được lưu.
5. Loại bỏ tên cũ sau khi consumer đã chuyển và retention không còn cần series cũ.

Nếu semantics thay đổi, ví dụ meter cũ đếm đơn được tạo còn meter mới đếm đơn được chấp nhận sau kiểm tra rủi ro, hãy dùng tên mới và mô tả mới. Không giả vờ hai chuỗi dữ liệu tương đương chỉ vì cùng đơn vị.

## 4. Kiểm tra thay đổi tag key

Tag key là một phần của schema. Đổi key có thể tạo series khác:

| Trước | Sau | Hệ quả |
| --- | --- | --- |
| status=200 | http.status=200 | Query filter theo status không còn khớp |
| env=production | environment=production | Dashboard có thể tách thành hai nhóm |
| result=ok | outcome=success | Cần cập nhật group/filter và mapping |

Tag key mới không tự động thay thế key cũ trong dữ liệu đã lưu. Trong thời gian rollout, instance cũ có thể phát key cũ và instance mới phát key mới.

Hãy kiểm tra:

- Tag key có đúng chính tả và cùng casing không?
- Tag value có giữ cùng vocabulary không?
- Tag có bị chuyển từ low-cardinality sang high-cardinality không?
- Có tag nào bị bỏ khiến các series trước đây tách biệt nay bị gộp không?
- Có tag mới làm tăng số lượng series không?
- Naming convention hoặc exporter có đổi tên tag không?

Nếu cần đổi key, nên dùng một giai đoạn tương thích. Có thể bổ sung key mới trong instrumentation hoặc chuẩn hóa ở collector/query, sau đó chuyển consumer và cuối cùng bỏ key cũ.

Không giữ hai key chỉ để tương thích nếu chúng có thể mang giá trị mâu thuẫn. Ví dụ status=200 và outcome=error trong cùng một sample khiến người dùng dashboard khó biết chiều nào là nguồn chính. Hãy định nghĩa quy tắc mapping và nguồn authoritative.

## 5. Kiểm tra thay đổi tag value

Giữ nguyên tag key nhưng đổi vocabulary cũng là thay đổi contract:

| Giá trị cũ | Giá trị mới | Vấn đề cần xử lý |
| --- | --- | --- |
| ok | success | Query và dashboard đang filter ok |
| fail | error | Cần mapping hoặc chuyển query |
| prod | production | Có thể tạo hai nhóm môi trường |
| GET | get | Backend phân biệt giá trị theo ký tự |

Tag value nên là tập hữu hạn, ổn định và có ý nghĩa rõ ràng. Không đổi chữ hoa/thường, dấu gạch hoặc cách viết tùy tiện giữa các release.

Nếu thay vocabulary, hãy thống kê các giá trị đang được phát, xác định mapping một-một hoặc nhiều-một và cập nhật query. Trường hợp nhiều giá trị cũ được gộp thành một giá trị mới có thể làm mất khả năng phân tích lịch sử ở mức chi tiết.

Không đưa dữ liệu động như user ID, order ID, request ID, exception message hoặc URL đầy đủ vào tags. Một thay đổi tưởng như nhỏ, chẳng hạn chuyển uri template thành raw URL, có thể làm cardinality tăng theo số request.

## 6. Kiểm tra thêm hoặc bỏ tag và tác động cardinality

Mỗi tổ hợp tên meter và tag values có thể tạo một time series. Thêm tag có thể nhân số series; bỏ tag có thể gộp các series vốn được phân biệt.

Ví dụ một meter có:

- 4 giá trị channel.
- 5 giá trị outcome.
- 3 vùng.

Số tổ hợp tối đa là 4 × 5 × 3 = 60 series cho mỗi instance và meter name, chưa tính các tag định danh khác.

Trước khi thêm tag:

1. Ước lượng số giá trị có thể xuất hiện.
2. Tính tác động nhân với các tags hiện tại và số instance.
3. Xác định tag có thực sự cần cho truy vấn hoặc alert không.
4. Xác nhận tag không chứa định danh riêng của từng request.
5. Đánh giá memory, scrape payload, ingestion và storage cost.

Khi bỏ tag, kiểm tra liệu các series có bị gộp với nhau và query có còn phân tích được theo chiều cũ không. Không coi bỏ tag là thay đổi vô hại chỉ vì cardinality giảm.

## 7. Kiểm tra thay đổi đơn vị và base unit

Đơn vị phải phản ánh đại lượng được đo. Micrometer Timer đo thời lượng và exporter có thể chuẩn hóa về đơn vị backend; DistributionSummary có thể mô tả số byte, số item hoặc kích thước payload.

Ví dụ cùng một đại lượng thời gian:

| Biểu diễn | Giá trị tương đương |
| --- | ---: |
| 250 milliseconds | 250 ms |
| 0.25 seconds | 0.25 s |
| 250000 microseconds | 250000 µs |

Giá trị tương đương về vật lý nhưng không thể so sánh trực tiếp nếu query không chuyển đổi đơn vị. Khi đổi từ millisecond sang second, phải kiểm tra:

- Code ghi nhận duration bằng API có đơn vị rõ ràng.
- Base unit của meter và metadata mô tả.
- Tên xuất ra backend, đặc biệt hậu tố _seconds hoặc _bytes.
- Dashboard có chia/nhân hệ số đúng không.
- Alert threshold có được chuyển đổi không.
- Recording rule và SLO có cùng đơn vị không.

Ví dụ khai báo Timer:

~~~java
Timer.builder("business.checkout.duration")
    .description("Thời gian hoàn tất checkout")
    .register(registry)
    .record(() -> checkoutService.execute(command));
~~~

Timer nhận thời lượng theo API của Micrometer và registry xuất theo đơn vị mà backend quy định. Với Prometheus, Timer thường được biểu diễn bằng seconds. Không tự nhân/chia giá trị trước khi record nếu registry đã chuẩn hóa đơn vị.

Ví dụ DistributionSummary có base unit:

~~~java
DistributionSummary payloadSize = DistributionSummary.builder(
        "http.request.payload.size"
    )
    .baseUnit("bytes")
    .description("Kích thước payload request")
    .register(registry);

payloadSize.record(payloadBytes);
~~~

Khi đổi base unit hoặc đổi cách record từ bytes sang kilobytes, cần chuyển đổi giá trị đầu vào và cập nhật contract. Chỉ đổi metadata base unit mà không đổi giá trị ghi nhận sẽ làm dữ liệu sai hệ số.

## 8. Kiểm tra thay đổi meter type

Đổi type thường nguy hiểm hơn đổi tên vì cùng một tên và tags có thể bị người dùng hiểu là cùng một đại lượng:

| Trước | Sau | Rủi ro |
| --- | --- | --- |
| Counter | Gauge | Từ tổng tích lũy thành trạng thái hiện tại |
| Timer | DistributionSummary | Mất semantics thời gian và cách chuẩn hóa unit |
| Gauge | Counter | Không còn phản ánh trạng thái hiện tại |
| Timer | Timer nhưng đổi ranh giới | Tên giữ nguyên nhưng ý nghĩa thời lượng đổi |

Không thay type dưới cùng một metric contract mà không có kế hoạch. Nếu đại lượng thay đổi bản chất, hãy đặt tên mới và cập nhật mô tả, query, dashboard cùng alert.

Ví dụ:

- Counter phù hợp đếm số lần một sự kiện xảy ra.
- Gauge phù hợp đọc trạng thái tại thời điểm quan sát.
- Timer phù hợp đo thời lượng và cung cấp count/total time/distribution.
- DistributionSummary phù hợp đo phân phối của các giá trị số như payload size.

Timer và DistributionSummary đều có thể tạo count, sum và histogram, nhưng semantics và đơn vị khác nhau. Không thay thế chúng cho nhau chỉ vì exposition có cấu trúc tương tự.

## 9. Kiểm tra Histogram, Percentile và SLO boundaries

Histogram là một phần quan trọng của metric schema. Thay đổi percentile histogram, bucket boundaries hoặc SLO boundaries có thể ảnh hưởng query p95/p99 và alert.

Ví dụ cấu hình:

~~~java
Timer.builder("business.checkout.duration")
    .publishPercentileHistogram()
    .serviceLevelObjectives(
        Duration.ofMillis(100),
        Duration.ofMillis(300),
        Duration.ofSeconds(1)
    )
    .register(registry);
~~~

Trước khi nâng cấp, so sánh:

- Histogram có được bật ở cả hai phiên bản không?
- Bucket boundaries có giống nhau không?
- SLO thresholds có giữ nguyên không?
- Percentile client-side có thay đổi cấu hình hoặc window không?
- Exporter có thay đổi loại histogram hoặc cách đặt tên bucket không?
- Query có tổng hợp bucket trước khi tính quantile không?

Với Prometheus classic histogram, các bucket được biểu diễn bằng series có label le. Để tính quantile toàn service, cần tổng hợp bucket tương thích trước:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, service, environment, version) (
    rate(business_checkout_duration_seconds_bucket[5m])
  )
)
~~~

Không lấy trung bình p95 đã tính riêng trên từng instance để suy ra p95 toàn service.

### Khi bucket thay đổi giữa các phiên bản

Nếu instance cũ phát bucket 100 ms, 300 ms, 1 s và instance mới phát 200 ms, 500 ms, 2 s, query gộp có thể thiếu các bucket cần thiết hoặc cho phân phối không đồng nhất. Trong giai đoạn rollout:

1. Giữ bucket chung nếu có thể.
2. Nếu schema không tương thích, tách query theo version hoặc schema.
3. Không gộp hai phân phối như thể cùng cấu hình.
4. Chuyển dashboard sau khi toàn bộ instance dùng schema mới.
5. Ghi nhận mốc cutover để so sánh lịch sử đúng cách.

## 10. Kiểm tra NamingConvention và dữ liệu exposition

Micrometer giữ tên canonical ở lớp API; từng registry áp dụng NamingConvention để xuất tên phù hợp backend. Vì vậy, một tên meter có thể có biểu diễn khác nhau ở Prometheus, Graphite hoặc hệ thống khác.

Ví dụ tên canonical:

~~~text
business.checkout.duration
~~~

Ví dụ Prometheus exposition có thể chuẩn hóa tên và đơn vị:

~~~text
business_checkout_duration_seconds_count
business_checkout_duration_seconds_sum
business_checkout_duration_seconds_bucket
~~~

Tên chính xác phụ thuộc meter type, base unit, registry version và convention đang dùng. Hãy lấy exposition thực tế làm bằng chứng thay vì đoán hậu tố.

Kiểm tra trước và sau nâng cấp:

- Tên metric đã chuẩn hóa.
- Suffix của counter, timer và histogram.
- Tag keys sau chuyển đổi.
- Escaping hoặc chuẩn hóa ký tự đặc biệt.
- Collision khi hai tên canonical trở thành cùng một tên backend.
- Metadata HELP/TYPE/UNIT nếu backend hỗ trợ.

Hai meter canonical khác nhau có thể bị chuẩn hóa thành tên giống nhau ở một backend. Đây là lý do cần kiểm tra exposition, không chỉ danh sách Meter.Id trong registry.

## 11. Kiểm tra dữ liệu công bố: endpoint, protocol và resource

Nâng cấp có thể thay đổi cách dữ liệu được công bố:

| Hình thức | Điều cần xác minh |
| --- | --- |
| Prometheus scrape | Endpoint, content type, metric names, labels và scrape target |
| OTLP metrics | Endpoint, protocol HTTP/gRPC, resource attributes và temporality |
| StatsD | Host/port, flavor, prefix và flush interval |
| JMX | ObjectName, attribute names và exporter mapping |
| Step registry | Step interval, scheduler và thời điểm publish |

Không chỉ xác minh ứng dụng có meter. Cần xác nhận dữ liệu thực sự rời khỏi registry theo định dạng backend mong đợi.

Với Prometheus, kiểm tra endpoint:

~~~bash
curl -i http://localhost:8080/actuator/prometheus
~~~

Với OTLP, kiểm tra endpoint receiver, protocol, TLS/authentication và log export. HTTP endpoint và gRPC endpoint không thể thay thế nhau chỉ bằng cách đổi port.

Với push/step registry, xác minh lịch flush và thời điểm publish. Dữ liệu có thể không xuất ngay khi Counter increment hoặc Timer stop nếu registry gom dữ liệu theo step.

## 12. Cumulative và delta temporality

Một số exporter/backend biểu diễn dữ liệu tích lũy, một số dùng delta theo khoảng thời gian. Đây là khác biệt về semantics, không chỉ là định dạng.

| Temporality | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| Cumulative | Giá trị tích lũy kể từ điểm bắt đầu của series | Cần xử lý reset khi process restart |
| Delta | Giá trị phát sinh trong một khoảng thời gian | Cần cộng các khoảng đúng cách, tránh cộng lặp |

Khi nâng cấp exporter hoặc collector, kiểm tra:

- Temporality đầu ra có đổi không?
- Collector có chuyển đổi delta/cumulative không?
- Resource identity có giữ ổn định qua các lần export không?
- Restart có tạo reset hoặc start timestamp mới không?
- Backend có hiểu đúng loại dữ liệu và aggregation temporality không?

Không dùng query dành cho cumulative counter lên dữ liệu delta nếu backend chưa chuyển đổi phù hợp. Điều này có thể làm rate sai hoặc đếm trùng.

## 13. Đánh giá tác động lên dashboard, alert và recording rules

Mọi consumer của metrics cần được kiểm kê trước khi đổi schema:

- Dashboard panels và template variables.
- Alert rules và threshold.
- Recording rules.
- SLO/error budget calculations.
- Autoscaling rules dựa trên metrics.
- Báo cáo vận hành hoặc pipeline dữ liệu bên ngoài.

Một thay đổi tag có thể làm query không còn match. Một thay đổi unit có thể khiến threshold sai theo hệ số 1000. Một thay đổi type có thể làm rate hoặc aggregation không còn đúng.

Tạo bảng mapping:

| Consumer hiện tại | Metric cũ | Metric mới | Hành động |
| --- | --- | --- | --- |
| Dashboard checkout latency | checkout_duration_seconds | business_checkout_duration_seconds | Chuyển query và đơn vị |
| Alert error rate | requests_total{status="5xx"} | http_requests_total{outcome="error"} | Mapping tag và xác minh semantics |
| Recording rule throughput | orders_created_total | business_orders_created_total | Chuyển tên, giữ rate window |

Các tên trong bảng là ví dụ. Dùng tên thực tế của hệ thống để lập mapping. Không cập nhật query chỉ dựa trên phỏng đoán về naming convention.

## 14. Chiến lược chuyển đổi an toàn

Không phải mọi thay đổi đều cần dual-publish. Chọn chiến lược theo mức độ tương thích và khả năng cập nhật consumer.

### Giữ nguyên contract

Nếu nâng cấp không thay đổi metric name, type, tags, unit, distribution hoặc exposition, chỉ cần kiểm tra contract và xác nhận dữ liệu sau nâng cấp tương đương.

### Dual-publish có thời hạn

Nếu đổi tên hoặc tag nhưng semantics giữ nguyên, có thể phát cả schema cũ và mới trong một giai đoạn:

1. Định nghĩa metric mới và giữ metric cũ.
2. Đảm bảo hai meter không làm cùng một query tổng hợp đếm đôi.
3. Chuyển dashboard, alert và consumer sang metric mới.
4. Kiểm tra kết quả hai bên tương đương trong cửa sổ đủ dài.
5. Dừng metric cũ sau khi consumer đã chuyển.

Dual-publish làm tăng số series và chi phí ingestion. Chỉ giữ trong thời gian cần thiết và đặt thời hạn loại bỏ.

### Cutover theo version

Nếu không thể phát cả hai schema, gắn version vào dữ liệu và tách query theo version. Khi rollout hoàn tất, cập nhật dashboard để dùng schema mới và giữ query lịch sử cho dữ liệu cũ.

### Thay đổi semantics

Nếu metric mới đo một đại lượng khác, tạo metric name mới, description mới và query mới. Không dual-publish như hai tên của cùng một đại lượng nếu chúng không tương đương.

## 15. Kiểm thử metric contract trước khi rollout

Có thể kiểm tra Meter.Id trong registry:

~~~java
Meter meter = registry.find("business.checkout.duration")
    .tag("outcome", "success")
    .timer();

assertThat(meter).isNotNull();
assertThat(meter.getId().getName())
    .isEqualTo("business.checkout.duration");
assertThat(meter.getId().getTag("outcome"))
    .isEqualTo("success");
~~~

Kiểm tra Prometheus exposition:

~~~java
String exposition = prometheusRegistry.scrape();

assertThat(exposition)
    .contains("business_checkout_duration_seconds_count")
    .contains("outcome=\"success\"");
~~~

Đây là ví dụ kiểm tra contract của registry cụ thể. Test cần dùng cùng loại registry/exporter với production nếu muốn xác minh naming convention và exposition.

### So sánh baseline với candidate

Trong pipeline nâng cấp, có thể lưu một snapshot metric schema từ bản hiện tại và so sánh với candidate:

| Kiểm tra | Kết quả mong đợi |
| --- | --- |
| Meter names | Không đổi ngoài danh sách migration đã duyệt |
| Meter types | Không đổi ngoài thay đổi có chủ đích |
| Tag keys | Không mất key hoặc thêm key ngoài dự kiến |
| Tag values | Vocabulary được kiểm soát |
| Units | Cùng đại lượng và scale |
| Histogram | Boundaries và SLO đã được đối chiếu |
| Exposition | Tên, suffix và labels đúng |
| Endpoint | Scrape/export hoạt động |
| Query | Dashboard/alert trả dữ liệu đúng |

Không nhất thiết snapshot toàn bộ meter động của một ứng dụng production. Tập trung vào metric contract quan trọng: request rate, error rate, latency, saturation và các business metrics dùng cho SLO.

## 16. Quy trình nâng cấp theo từng bước

1. Ghi nhận phiên bản Micrometer, Spring Boot, registry và exporter hiện tại.
2. Thu thập metric schema từ registry và exposition.
3. Kiểm kê dashboard, alerts, recording rules và consumer bên ngoài.
4. So sánh dependency release notes và migration notes để xác định thay đổi có thể ảnh hưởng.
5. Chạy ứng dụng candidate trong môi trường test với cùng cấu hình metrics.
6. So sánh name, type, tags, unit, histogram và temporality.
7. Kiểm tra endpoint hoặc protocol công bố dữ liệu.
8. Chạy query/dashboard test với dữ liệu candidate.
9. Triển khai canary hoặc một nhóm instance nhỏ.
10. So sánh throughput, latency, error rate, cardinality và export failures.
11. Chuyển consumer theo kế hoạch dual-publish hoặc versioned cutover.
12. Theo dõi sau rollout và loại bỏ compatibility path khi hết thời hạn.

## 17. Rollback và xử lý khi dữ liệu sau nâng cấp sai

Nếu sau rollout phát hiện dashboard trống, label mất hoặc đơn vị sai:

- Xác định lỗi nằm ở instrumentation, registry, exporter, collector hay query.
- So sánh exposition của instance cũ và mới.
- Kiểm tra instance nào đang phát schema nào.
- Kiểm tra unit conversion và histogram boundaries.
- Khôi phục cấu hình exporter hoặc metric schema tương thích nếu có thể.
- Rollback ứng dụng nếu semantics bị sai và không có cách sửa an toàn tại consumer.
- Giữ dữ liệu cũ để đối chiếu; không xóa series hoặc dashboard lịch sử một cách vội vàng.

Rollback code không tự xóa series mới đã được backend thu thập. Dashboard cần tiếp tục xử lý dữ liệu của cả hai version trong thời gian chúng cùng tồn tại.

Nếu thay đổi chỉ là tên/tag và dữ liệu đã được lưu riêng, có thể duy trì query tương thích. Nếu đơn vị hoặc semantics sai, không nên ghép dữ liệu cũ và mới trong cùng một phép tính nếu chưa chuẩn hóa.

## 18. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách phòng tránh |
| --- | --- | --- |
| Chỉ kiểm tra code compile | Dashboard có thể mất series sau deploy | Kiểm tra exposition thực tế |
| Đổi tên meter mà không cập nhật query | Dashboard/alert không có dữ liệu | Lập mapping consumer trước migration |
| Đổi tag key/value không có giai đoạn chuyển tiếp | Series bị tách hoặc query mất dữ liệu | Chuẩn hóa vocabulary và cutover |
| Đổi unit nhưng giữ threshold cũ | Alert sai theo hệ số | Chuyển đổi unit và threshold cùng nhau |
| Đổi Timer thành DistributionSummary | Mất semantics thời gian | Đánh giá type và dùng metric name mới |
| Thay histogram buckets giữa rollout | Quantile tổng hợp không đáng tin | Giữ schema chung hoặc tách query theo version |
| Dual-publish rồi cộng hai meter | Đếm đôi cùng một sự kiện | Chỉ chọn một nguồn trong mỗi query |
| Chỉ test SimpleMeterRegistry | Bỏ sót NamingConvention/exporter | Test registry/exporter production dùng |
| Bỏ qua temporality | Rate hoặc increase sai | Xác minh cumulative/delta end-to-end |
| Xóa metric cũ ngay khi release mới | Mất khả năng so sánh và rollback | Giữ compatibility window có thời hạn |

## 19. Checklist trước khi nâng cấp

- [ ] Đã lưu baseline metric names, types, tags và units.
- [ ] Đã kiểm tra cả canonical meter name và tên exposition.
- [ ] Đã đối chiếu tag keys, tag values và cardinality.
- [ ] Đã xác nhận type và semantics không đổi ngoài chủ đích.
- [ ] Đã kiểm tra base unit, scale và threshold.
- [ ] Đã so sánh histogram buckets, percentile và SLO boundaries.
- [ ] Đã kiểm tra cumulative/delta temporality.
- [ ] Đã xác minh endpoint, protocol, authentication và export receiver.
- [ ] Đã lập mapping cho dashboard, alert, recording rule và consumer.
- [ ] Đã chọn giữ contract, dual-publish hay versioned cutover.
- [ ] Đã kiểm tra không có query đếm đôi trong giai đoạn chuyển tiếp.
- [ ] Đã chạy metric contract tests và exposition tests.
- [ ] Đã xác định canary signals và rollback criteria.
- [ ] Đã đặt thời hạn loại bỏ metric/schema cũ.

Một lần nâng cấp chỉ an toàn với observability khi dữ liệu sau nâng cấp vẫn giữ đúng ý nghĩa và được công bố theo contract mà consumer hiểu. Hãy kiểm tra tên, type, tags, unit, histogram, temporality và exposition trước khi deploy; sau đó chuyển dashboard và alert theo kế hoạch có thời hạn. Việc so sánh baseline với candidate ở cả registry lẫn endpoint giúp phát hiện thay đổi schema trước khi nó trở thành sự cố vận hành.
