# Dashboard theo module identifier

> **Chương:** Dashboard  
> **Bối cảnh:** Spring Modulith Documentation & Observability — xây dựng dashboard theo từng application module để nhìn thấy tần suất invocation, latency, lỗi và domain event publication trong ứng dụng Spring Boot.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao **module.identifier** là dimension trung tâm khi quan sát ứng dụng Spring Modulith.
2. Phân biệt module entry Timer với event publication counters.
3. Bật metrics cho module invocation, cấu hình Prometheus scrape và kiểm tra số liệu bằng Actuator.
4. Viết PromQL để so sánh throughput, p95 latency, error ratio và event publication rate theo module.
5. Tạo Grafana dashboard có biến chọn module, môi trường và ứng dụng.
6. Chọn panel và alert có ý nghĩa vận hành, tránh cảnh báo sai khi module không có traffic.
7. Kiểm soát cardinality và nhận biết khi nào cần dùng trace thay cho metric.
8. Đối chiếu dashboard runtime với module graph để kiểm chứng kiến trúc và hành vi thực tế.

## 2. Vì sao dashboard cần một chiều theo module?

Trong ứng dụng Spring Modulith, mỗi application module chịu trách nhiệm cho một phần nghiệp vụ. Một request có thể đi qua nhiều module:

~~~mermaid
flowchart LR
    Client["Client"] --> API["HTTP API"]
    API --> Orders["orders"]
    Orders --> Inventory["inventory"]
    Orders --> Payments["payments"]
    Orders --> Events["Domain events"]
    Events --> Notifications["notifications"]
~~~

Dashboard chỉ tổng hợp theo toàn ứng dụng thường che khuất vấn đề cục bộ. Ví dụ:

- Tổng latency của service vẫn ổn định nhưng module payments bắt đầu chậm.
- Số request không đổi nhưng module inventory nhận nhiều invocation hơn do một luồng retry.
- Module orders phát event bình thường nhưng notifications có lỗi khi xử lý event.
- Một module có tỷ lệ lỗi cao trong khi các module còn lại vẫn hoạt động tốt.

**module.identifier** cho phép nhóm dữ liệu theo định danh kỹ thuật ổn định của application module. Dashboard từ đó trả lời:

| Câu hỏi vận hành | Panel phù hợp |
| --- | --- |
| Module nào đang nhận nhiều invocation nhất? | Invocation rate by module |
| Module nào xử lý chậm? | p95/p99 latency by module |
| Lỗi đang tập trung ở đâu? | Error ratio by module |
| Module nào đang phát nhiều domain events? | Event publication rate by module/type |
| Sự thay đổi bắt đầu từ thời điểm nào? | Time series theo module và deployment |

## 3. Dùng module identifier làm dimension chính

Spring Modulith quan sát các lời gọi đi vào những Spring component thuộc API của application module. Với module entry observation, các metadata mặc định gồm:

| Key | Cardinality | Ý nghĩa | Dùng trên dashboard |
| --- | --- | --- | --- |
| **module.identifier** | Low | Định danh kỹ thuật của module | **Dimension chính** |
| **module.name** | Low | Tên hiển thị của module | Nhãn dễ đọc hoặc biến chọn |
| **module.invocation-type** | Low | Kiểu invocation, ví dụ bean hoặc event listener | Bộ lọc/phân nhóm phụ |
| **module.method** | High | Method được gọi trên module | Dùng để điều tra trong trace |

Theo convention Spring Modulith hiện hành, module.identifier, module.name và module.invocation-type là low-cardinality keys; module.method là high-cardinality key. Vì vậy method metadata có thể hữu ích trên span nhưng không nên trở thành metric label.

**Nên dùng module.identifier làm khóa nhóm chính**, bởi nó là định danh kỹ thuật của module. module.name phù hợp cho hiển thị. Nếu đổi tên hiển thị, dashboard vẫn có thể nhóm theo identifier ổn định.

Không dùng orderId, customerId, requestId, traceId hoặc tên method động làm metric labels. Mỗi giá trị mới có thể tạo một time series mới, làm tăng bộ nhớ, chi phí ingest và độ khó truy vấn.

## 4. Hai nhóm metrics cần có trên dashboard

Dashboard theo module nên tách hai loại tín hiệu.

### 4.1. Module invocation Timer

Observation module entry có tên mặc định **module.invocations**. Khi DefaultMeterObservationHandler được đăng ký trên ObservationRegistry (Spring Boot tự đăng ký handler này trong cấu hình metrics mặc định), một observation hoàn tất được chuyển thành Timer:

- Meter name: **module.invocations**.
- Đo số lần observation hoàn tất và thời gian thực thi.
- Tags gồm low-cardinality key-values và tag **error**.
- Với module entry convention mặc định, các chiều hữu ích là **module.identifier**, **module.name** và **module.invocation-type**.
- **module.method** là high-cardinality nên không được dùng làm Timer tag mặc định.

Timer phù hợp để dựng panel throughput, latency và error ratio cho từng module. Nó đo thời gian của module entry operation đã được instrument, không phải toàn bộ thời gian mọi method nội bộ của module.

### 4.2. Domain event publication counters

Spring Modulith cung cấp hai counter cho event publication:

| Meter | Ý nghĩa | Tag chính |
| --- | --- | --- |
| **module.events.published** | Tổng hợp các domain event được publish | module.event.type, module.identifier, module.name |
| **module.events.published.$moduleIdentifier.$simpleEventTypeName** | Counter riêng cho một loại event | module.identifier, module.name |

Nhóm này cho biết module nào đang phát domain event và phát loại nào. Counter publication không chứng minh listener đã xử lý thành công hoặc hoàn tất. Muốn quan sát listener, xem module entry invocation/span tương ứng và Event Publication Registry khi cần theo dõi trạng thái publication.

Không trộn event publication count với module invocation count trong cùng một đại lượng: một lần publish có thể kích hoạt không, một hoặc nhiều listener tùy cấu trúc ứng dụng.

## 5. Dependency và cấu hình metrics

### 5.1. Thêm Spring Modulith Insight và Prometheus registry

Với BOM tương thích của dự án, có thể dùng Spring Modulith Insight starter để có Actuator module metadata và observability support:

~~~xml
<!-- pom.xml: version do Spring Modulith BOM quản lý -->
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-starter-insight</artifactId>
    <scope>runtime</scope>
</dependency>

<!-- Export Micrometer metrics theo định dạng Prometheus -->
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Insight starter bao gồm hỗ trợ Actuator và observability của Spring Modulith; vẫn cần registry/exporter phù hợp để gửi metrics tới hệ thống monitoring. Nếu không dùng Insight starter, cần khai báo riêng các dependency Actuator và Modulith observability cần thiết.

### 5.2. Expose endpoint và bật histogram cho module invocation

Ví dụ cấu hình profile monitoring:

~~~yaml
spring:
  application:
    name: shop-service

management:
  endpoints:
    web:
      exposure:
        include: "health,metrics,prometheus,modulith"

  metrics:
    tags:
      application: shop-service
      environment: local
    distribution:
      percentiles-histogram:
        module.invocations: true
~~~

Giải thích:

- spring.application.name xác định tên ứng dụng; tag application giúp lọc nhiều ứng dụng dùng chung Prometheus.
- environment là tag chung có tập giá trị hữu hạn như local, staging, production.
- metrics cho phép chẩn đoán meter trong /actuator/metrics.
- prometheus cung cấp định dạng scrape tại /actuator/prometheus.
- modulith công bố metadata application module tại /actuator/modulith.
- percentiles-histogram.module.invocations bật histogram để Prometheus có thể tính percentile tổng hợp từ bucket.

Chỉ bật histogram khi dashboard cần p95/p99 hoặc SLO buckets; histogram tạo thêm series cho mỗi tổ hợp label. Nếu không bật histogram, Timer vẫn có thể cung cấp count và sum để tính throughput/trung bình, nhưng truy vấn p95 từ classic histogram sẽ không có dữ liệu bucket.

Các endpoint Actuator không nên mở công khai không xác thực. Chỉ expose những endpoint cần thiết và giới hạn truy cập theo mạng, authentication/authorization và chính sách quản trị của môi trường.

## 6. Prometheus scrape metrics từ Spring Boot

Prometheus thường scrape từng instance của ứng dụng qua /actuator/prometheus.

~~~yaml
# prometheus.yml — ví dụ cho môi trường thử nghiệm
scrape_configs:
  - job_name: "spring-modulith"
    metrics_path: "/actuator/prometheus"
    scrape_interval: 15s
    static_configs:
      - targets:
          - "shop-service:8080"
~~~

Trong Kubernetes hoặc môi trường autoscaling, dùng service discovery/relabeling thay cho danh sách target tĩnh. Đảm bảo Prometheus truy cập được management port/path và có credentials/TLS nếu endpoint được bảo vệ.

Tên meter trong Micrometer và tên series Prometheus có thể khác nhau do naming convention. Ví dụ meter module.invocations có thể được chuẩn hóa thành:

~~~text
module_invocations_seconds_count
module_invocations_seconds_sum
module_invocations_seconds_bucket
~~~

Đây là tên series dự kiến với Prometheus Timer dùng đơn vị giây và histogram classic; hãy xác nhận output thực tế trong /actuator/prometheus trước khi viết dashboard.

## 7. Kiểm tra metrics bằng Actuator trước khi tạo panel

Đầu tiên xem danh sách meter:

~~~bash
curl -i http://localhost:8080/actuator/metrics
~~~

Sau đó xem module invocation Timer:

~~~bash
curl -i http://localhost:8080/actuator/metrics/module.invocations
~~~

Lọc theo module:

~~~bash
curl -i "http://localhost:8080/actuator/metrics/module.invocations?tag=module.identifier:orders"
~~~

Nếu cần lọc theo kiểu invocation và meter thực sự có tag này:

~~~bash
curl -i "http://localhost:8080/actuator/metrics/module.invocations?tag=module.identifier:payments&tag=module.invocation-type:bean"
~~~

Actuator dùng tên meter gốc (module.invocations), không dùng tên đã chuẩn hóa cho Prometheus (module_invocations_seconds_count). Tham số tag=KEY:VALUE cho phép lọc theo các tag có trong availableTags.

Kiểm tra event publication counter:

~~~bash
curl -i http://localhost:8080/actuator/metrics/module.events.published
~~~

Nếu không có meter, hãy kiểm tra ứng dụng đã thực sự thực thi module API hoặc publish domain event chưa, Insight/observability runtime đã được cài chưa, metrics registry có hoạt động không và endpoint có được expose hay không.

## 8. Bố cục dashboard theo module

Một dashboard hữu ích nên đi từ trạng thái tổng quan đến chi tiết:

| Hàng | Panel | Loại hiển thị | Câu hỏi |
| --- | --- | --- | --- |
| 1 | Invocation rate by module | Time series | Module nào đang nhận nhiều operation? |
| 1 | p95 latency by module | Time series | Module nào đang chậm? |
| 1 | Error ratio by module | Time series / stat | Lỗi tập trung ở đâu? |
| 2 | Invocation volume by module | Bar chart | So sánh tải giữa các module |
| 2 | Event publication rate | Time series | Module nào đang phát event? |
| 2 | Event type by producer module | Bar/table | Event type nào tăng bất thường? |
| 3 | Invocation type split | Stacked time series | Tải đến từ bean hay event listener? |
| 3 | JVM / executor / datasource context | Time series | Có dấu hiệu tài nguyên nền gây chậm không? |

Đặt biến chọn application, environment và module ở đầu dashboard. Khi người vận hành chọn một module, các panel liên quan cùng thay đổi theo lựa chọn đó.

~~~mermaid
flowchart TB
    Variables["Dashboard variables<br/>application / environment / module"]
    Variables --> A["Invocation rate"]
    Variables --> B["p95 latency"]
    Variables --> C["Error ratio"]
    Variables --> D["Event publication rate"]
    Variables --> E["Invocation type split"]
    A --> F["Chọn module bất thường"]
    B --> F
    C --> F
    D --> F
    E --> F
    F --> G["Mở trace hoặc log để điều tra"]
~~~

Không nên cố biến dashboard thành module graph động bằng cách lấy mọi tag từ metrics. Module graph là dữ liệu kiến trúc; dashboard metrics là dữ liệu runtime. Có thể đặt link tới /actuator/modulith hoặc tài liệu graph cạnh dashboard để đối chiếu hai góc nhìn.

## 9. PromQL: invocation rate theo module

Timer Prometheus cung cấp _count để đếm số observation đã hoàn tất. Dùng rate() để tính tốc độ trên cửa sổ thời gian:

~~~promql
sum by (module_identifier) (
  rate(module_invocations_seconds_count[$__rate_interval])
)
~~~

Nếu cần lọc một application/environment có common tags:

~~~promql
sum by (module_identifier) (
  rate(module_invocations_seconds_count{
    application="$application",
    environment="$environment",
    module_identifier=~"$module"
  }[$__rate_interval])
)
~~~

Trong Grafana:

- $__rate_interval tự chọn cửa sổ phù hợp với scrape interval và khoảng thời gian dashboard.
- =~"$module" cho phép biến multi-value hoặc All dùng biểu thức regular expression.
- Bỏ các selector application/environment nếu registry của bạn chưa gắn các common tags tương ứng.
- sum by (module_identifier) gộp các instance của cùng module, tránh mỗi replica thành một đường riêng.

Đơn vị kết quả là invocation/giây. Đây là tốc độ các module entry observations hoàn tất, không phải số HTTP request nếu một request có thể gọi module nhiều lần.

## 10. PromQL: p95 latency theo module

Để tính p95 tổng hợp trên nhiều instance, dùng histogram bucket và histogram_quantile():

~~~promql
histogram_quantile(
  0.95,
  sum by (le, module_identifier) (
    rate(module_invocations_seconds_bucket{
      module_identifier=~"$module"
    }[$__rate_interval])
  )
)
~~~

Điều kiện:

1. Histogram đã được bật cho meter module.invocations.
2. Prometheus scrape các series _bucket.
3. Label le còn nguyên để Prometheus tính percentile cho classic histogram.
4. Aggregation cộng bucket trên các instance trước khi tính quantile.

Kết quả là p95 duration theo giây cho từng module. Có thể thay 0.95 bằng 0.50 để xem median hoặc 0.99 để xem p99.

Không lấy trung bình các p95 của từng instance để suy ra p95 toàn ứng dụng. Với classic histogram, hãy cộng rate của các bucket theo le và module trước khi gọi histogram_quantile().

### 10.1. Trung bình latency khi chưa bật histogram

Nếu chưa có bucket, có thể tính trung bình từ tổng thời gian và số lần observation:

~~~promql
sum by (module_identifier) (
  rate(module_invocations_seconds_sum[$__rate_interval])
)
/
sum by (module_identifier) (
  rate(module_invocations_seconds_count[$__rate_interval])
)
~~~

Đơn vị là giây. Average hữu ích để theo dõi xu hướng, nhưng có thể che khuất một số ít operation rất chậm. Với dashboard SLO, histogram và p95/p99 thường cung cấp góc nhìn tốt hơn.

## 11. PromQL: error ratio theo module

Micrometer Timer từ Observation có tag error: giá trị thường là none khi không ghi nhận lỗi hoặc tên exception khi observation báo lỗi.

~~~promql
sum by (module_identifier) (
  rate(module_invocations_seconds_count{error!="none"}[$__rate_interval])
)
/
sum by (module_identifier) (
  rate(module_invocations_seconds_count[$__rate_interval])
)
~~~

Định dạng panel theo phần trăm. Nếu meter của ứng dụng có quy ước error tag khác, hãy kiểm tra label thực tế và điều chỉnh điều kiện lọc.

Để xem tốc độ lỗi tuyệt đối:

~~~promql
sum by (module_identifier) (
  rate(module_invocations_seconds_count{error!="none"}[$__rate_interval])
)
~~~

Tỷ lệ lỗi có thể không ổn định khi module có rất ít invocation. Nên đặt ngưỡng tối thiểu về traffic hoặc kết hợp với số lượng request trước khi kích hoạt cảnh báo.

## 12. PromQL: domain event publication rate

Với counter tổng hợp module.events.published, Prometheus thường chuẩn hóa thành module_events_published_total. Tag module.event.type được chuẩn hóa thành label module_event_type.

Tốc độ event publication theo module:

~~~promql
sum by (module_identifier) (
  rate(module_events_published_total[$__rate_interval])
)
~~~

Phân tách theo module và event type:

~~~promql
sum by (module_identifier, module_event_type) (
  rate(module_events_published_total[$__rate_interval])
)
~~~

Nếu output scrape của registry có tên metric hoặc label khác, dùng tên thực tế thay cho các tên chuẩn hóa minh họa ở trên. Đặc biệt, counter riêng theo event type có thể được xuất dưới meter name động; panel tổng hợp nên ưu tiên counter module.events.published nếu nó có đầy đủ low-cardinality tags.

Event publication rate giúp phát hiện:

- Module bất ngờ phát event nhiều hơn baseline.
- Một loại event gần như ngừng xuất hiện trong giờ hoạt động bình thường.
- Thay đổi phân bố event giữa các producer module.

Không diễn giải số publish là số listener xử lý thành công. Muốn theo dõi listener, xem module entry invocation observations có module.invocation-type=event listener, trace và trạng thái publication tương ứng.

## 13. Tạo biến chọn module trong Grafana

Grafana Prometheus datasource hỗ trợ query variables lấy giá trị label từ metric. Tạo biến:

| Thuộc tính | Giá trị gợi ý |
| --- | --- |
| Name | module |
| Type | Query |
| Data source | Prometheus |
| Query type | Label values |
| Metric | module_invocations_seconds_count |
| Label | module_identifier |
| Multi-value | Bật nếu cần chọn nhiều module |
| Include All | Bật nếu dashboard cần xem toàn bộ |

Khi bật Multi-value hoặc Include All, dùng selector =~ thay cho =:

~~~promql
module_invocations_seconds_count{
  module_identifier=~"$module"
}
~~~

Có thể tạo thêm biến application, environment hoặc module_name nếu các label đó đã được gắn vào metrics. Đừng lấy module.method làm biến metric nếu nó là high-cardinality key; method detail nên được xem trong trace backend.

## 14. Thiết kế alert theo module

Dashboard giúp phát hiện và điều tra; alert cần tập trung vào điều kiện có ý nghĩa đối với người vận hành.

| Alert | Điều kiện tham khảo | Lưu ý |
| --- | --- | --- |
| Module p95 latency cao | p95 vượt SLO trong một khoảng thời gian liên tục | Chỉ hoạt động khi histogram đã bật |
| Module error ratio cao | Tỷ lệ lỗi vượt ngưỡng và có đủ invocation | Tránh cảnh báo theo tỷ lệ khi denominator quá nhỏ |
| Event publication tăng đột biến | Rate cao hơn baseline nhiều lần | Kiểm tra retry hoặc vòng lặp publish |
| Event publication giảm về 0 | Không có event trong khung giờ đáng lẽ có hoạt động | Module có thể không phát event theo mọi request |
| Prometheus scrape thất bại | Target up bằng 0 | Đây là cảnh báo hạ tầng scrape, không phải module business |

Ví dụ biểu thức p95 vượt 500 ms:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, module_identifier) (
    rate(module_invocations_seconds_bucket[5m])
  )
) > 0.5
~~~

0.5 là ngưỡng ví dụ, không phải SLO mặc định. Chọn ngưỡng theo yêu cầu latency của nghiệp vụ và thời gian đánh giá; thêm for trong alert rule để tránh cảnh báo do một spike ngắn.

Ví dụ error ratio trên 2%:

~~~promql
(
  sum by (module_identifier) (
    rate(module_invocations_seconds_count{error!="none"}[5m])
  )
  /
  sum by (module_identifier) (
    rate(module_invocations_seconds_count[5m])
  )
) > 0.02
~~~

Trước khi dùng alert, xác nhận module có đủ traffic trong cửa sổ truy vấn. Nếu không có invocation, tỷ lệ lỗi có thể là NaN hoặc không có series; đó không nhất thiết là sự cố.

## 15. Cardinality, tên module và dimension bổ sung

Dashboard tốt không có nghĩa là thêm càng nhiều labels càng tốt.

| Dimension | Khuyến nghị | Lý do |
| --- | --- | --- |
| module.identifier | Dùng | Tập module có giới hạn và là dimension chính |
| module.name | Có thể dùng cho hiển thị | Tập giá trị nhỏ, dễ đọc |
| module.invocation-type | Dùng khi cần tách bean/event listener | Tập giá trị nhỏ |
| module.method | Không dùng làm metric tag mặc định | High cardinality theo convention |
| traceId, spanId | Không dùng | Mỗi request/span có ID riêng |
| orderId, customerId, requestId | Không dùng | Số giá trị tăng theo traffic |
| environment, application, region | Dùng có kiểm soát | Phục vụ phân vùng vận hành |

Nếu cần tìm method chậm, hãy:

1. Chọn module có p95 tăng trên dashboard.
2. Mở trace đại diện trong cùng khoảng thời gian.
3. Lọc module entry spans theo module.identifier.
4. Đọc module.method trên span để tìm operation cụ thể.
5. Dùng log/trace ID để xem lỗi hoặc nhánh xử lý.

Đó là cách giữ metrics gọn trong khi vẫn có chiều sâu chẩn đoán từ tracing.

## 16. Phân biệt dashboard runtime và module graph

Spring Modulith cung cấp endpoint /actuator/modulith để xem cấu trúc module được nhận diện và các dependency giữa chúng. Đây là thông tin kiến trúc, khác với metrics:

| Nguồn | Thể hiện | Thay đổi khi nào? |
| --- | --- | --- |
| /actuator/modulith | Module, base package, dependency target và dependency type | Khi cấu trúc code/config module thay đổi |
| module.invocations | Invocation và duration của module entry observations | Theo hoạt động runtime |
| module.events.published | Domain event publication theo module/type | Khi event được publish |
| Trace backend | Chuỗi span của một lần thực thi | Theo từng trace được sample/export |

Một module không xuất hiện trên dashboard trong khoảng thời gian có thể đơn giản là không có invocation. Điều đó không có nghĩa module đã bị xóa hoặc dependency graph bị thay đổi.

Ngược lại, một module xuất hiện nhiều trên dashboard không tự chứng minh dependency tĩnh của nó sai. Dùng module graph để kiểm tra quan hệ kiến trúc, dùng dashboard và traces để kiểm tra hành vi lúc chạy.

## 17. Chẩn đoán dashboard khi thiếu hoặc sai dữ liệu

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Không có module.invocations | Chưa cài Modulith observability hoặc chưa gọi điểm vào module được instrument | Kiểm tra Insight/runtime dependency và request thực tế |
| Có Timer nhưng không có tag module | Convention/handler khác mặc định hoặc meter không phải module entry observation | Xem availableTags và span attributes |
| Không có _bucket series | Chưa bật histogram hoặc registry không xuất classic buckets | Kiểm tra percentiles-histogram và scrape output |
| Event counter không tăng | Chưa publish event trong khoảng thời gian đó | Kiểm tra event publisher và counter qua Actuator |
| Tên metric không khớp PromQL | Naming convention chuẩn hóa tên hoặc registry khác | Đọc /actuator/prometheus để lấy tên series thật |
| Panel trống khi chọn một module | Variable value không khớp label hoặc dùng = với multi-value | Kiểm tra variable và dùng =~ |
| p95 cao nhưng average thấp | Một số ít invocation rất chậm | Mở trace mẫu và xem span duration |
| Error ratio nhảy cao với traffic rất thấp | Denominator nhỏ | Thêm ngưỡng invocation tối thiểu |
| Event publish rate tăng nhưng listener không chạy | Counter đo publication, không đo listener completion | Xem listener invocation span và Event Publication Registry |
| Mỗi instance có một đường riêng | Query chưa aggregate theo module | Dùng sum by (module_identifier) |
| Dashboard có quá nhiều series | Dùng tag cardinality cao hoặc quá nhiều dimension | Bỏ method/ID khỏi metric labels, giảm dimension |
| Endpoint trả 401/403/404 | Security, exposure hoặc management path/port | Kiểm tra quyền truy cập và endpoint config |

## 18. Bài thực hành: dựng dashboard cho orders, payments và inventory

**Bối cảnh:** ứng dụng có ba module orders, payments và inventory. Module orders nhận request, gọi inventory để giữ hàng, gọi payments để thanh toán và publish OrderPlaced.

Thực hiện:

1. Thêm Spring Modulith Insight starter và Prometheus registry theo BOM tương thích.
2. Bật Actuator metrics, Prometheus và Modulith endpoints; bảo vệ management endpoints.
3. Bật histogram cho module.invocations trong profile học tập.
4. Chạy một số request thành công và một số request có lỗi giả lập ở payments.
5. Publish domain event OrderPlaced từ orders và xác nhận counter module.events.published tăng.
6. Kiểm tra meter names/tags ở /actuator/metrics và series đã chuẩn hóa ở /actuator/prometheus.
7. Cấu hình Prometheus scrape ứng dụng.
8. Tạo Grafana dashboard với biến application, environment và module.
9. Thêm panel invocation rate, p95 latency, average latency, error ratio và event publication rate bằng các truy vấn ở trên.
10. Chọn riêng module payments, xác nhận panel chỉ hiển thị dữ liệu module đó.
11. Tạo alert thử nghiệm khi p95 vượt ngưỡng trong một khoảng thời gian.
12. Mở trace của một invocation chậm để xem module.method và các span downstream.
13. Đối chiếu /actuator/modulith để phân biệt dependency tĩnh orders → inventory/payments với invocation đã xảy ra trong khoảng dashboard.

Mẫu bảng nghiệm thu:

| Kiểm tra | Kết quả cần đạt |
| --- | --- |
| Invocation Timer | Có module.invocations và count tăng sau module entry call |
| Module identifier | Có thể lọc riêng orders, payments, inventory |
| Histogram | Có bucket để tính p95/p99 |
| Error ratio | Tăng khi tạo lỗi giả lập trong payments |
| Event publication | Counter tăng khi OrderPlaced được publish |
| Grafana variable | Chọn một hoặc nhiều module làm thay đổi các panel |
| Trace drill-down | Mở được trace để xem method và downstream operation |
| Cardinality | Không có order ID, trace ID hoặc customer ID trong metric labels |

**Tiêu chí hoàn thành:** dashboard cho biết module nào đang nhận tải, chậm hoặc lỗi; phân biệt invocation với event publication; lọc được theo module identifier; và chuyển được từ panel bất thường sang trace để điều tra chi tiết.

## 19. Ghi nhớ

Một dashboard theo module identifier nên giữ ba nhóm câu hỏi rõ ràng:

~~~text
MODULE INVOCATIONS
  module.invocations
  → throughput, latency, error ratio theo module.identifier

DOMAIN EVENT PUBLICATIONS
  module.events.published
  → event rate theo module.identifier và module.event.type

ARCHITECTURE / DIAGNOSTICS
  /actuator/modulith + traces + logs
  → dependency tĩnh và chi tiết của từng lần thực thi
~~~

module.identifier là dimension chính để nhóm dữ liệu runtime. module.method và các ID riêng từng request thuộc đường trace/log, không phải metric labels. Kết hợp dashboard với module graph, event publication metrics và module entry spans để kiểm chứng ranh giới application module trong lúc hệ thống vận hành.

### Tài liệu tham khảo

- [Spring Modulith 2.2 — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html) — Insight starter, /actuator/modulith, module entry spans và event publication counters.
- [Spring Modulith 2.2 — ModulithObservations.LowKeys API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithObservations.LowKeys.html) — low-cardinality keys của module entry observation.
- [Spring Modulith 2.2 — ModulithObservations.HighKeys API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithObservations.HighKeys.html) — high-cardinality module.method.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) — registry, Prometheus endpoint, histogram và Actuator metrics endpoint.
- [Micrometer — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html) — DefaultMeterObservationHandler, Timer và low-cardinality tags.
- [Prometheus — Histograms and summaries](https://prometheus.io/docs/practices/histograms/) — histogram aggregation và percentile queries.
- [Grafana — Prometheus template variables](https://grafana.com/docs/grafana/latest/datasources/prometheus/template-variables/) — biến chọn module từ label values.

> **Lưu ý phiên bản:** tên meter, label sau chuẩn hóa và output histogram phụ thuộc Micrometer registry và cấu hình Spring Boot. Các truy vấn trong bài dùng tên Prometheus phổ biến để minh họa; luôn xác minh /actuator/prometheus trước khi đưa vào dashboard production. Bài được soạn trong STEP 4; Content QA chuyên môn thuộc bước riêng.
