# Cảnh báo event publication tăng bất thường

> **Chương:** Alerting  
> **Module học tập:** `SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY`  
> **Định hướng:** Dùng Spring Modulith để sinh tài liệu ranh giới application module và quan sát tương tác giữa các phần trong ứng dụng Spring Boot. Học module graph, Actuator, event metrics, tracing và context propagation để kiểm chứng kiến trúc mô-đun khi hệ thống vận hành.

## 1. Vì sao cần cảnh báo event publication?

Trong một ứng dụng Spring Modulith, các application module có thể giao tiếp bằng domain event. Ví dụ, module `order` phát `OrderCompleted` sau khi đơn hàng được hoàn tất. Các listener thuộc module `inventory`, `payment` hoặc `notification` có thể tiếp tục xử lý event đó.

~~~mermaid
flowchart LR
    Order["order module"]
    Event["OrderCompleted"]
    Inventory["inventory listener"]
    Notification["notification listener"]
    Metrics["module.events.published"]
    Alert["Prometheus alert"]
    Order --> Event
    Event --> Inventory
    Event --> Notification
    Event --> Metrics --> Alert
~~~

Khi số event publication tăng nhanh bất thường, hệ thống có thể đang gặp một trong các tình huống:

- Lưu lượng nghiệp vụ tăng đột biến theo chiến dịch hoặc giờ cao điểm.
- Một request hoặc transaction vô tình phát cùng một event nhiều lần.
- Hai listener hoặc module tạo thành vòng lặp event.
- Một listener phát event tiếp theo theo cách khuếch đại số lượng event.
- Consumer chậm khiến publication tích lũy trong registry hoặc broker.
- Retry/resubmission tạo thêm nhiều lượt xử lý.
- Một thay đổi code khiến event được phát ở nhiều nhánh nghiệp vụ hơn dự kiến.

Một cảnh báo tốt giúp nhóm vận hành nhận ra thay đổi trước khi backlog, độ trễ xử lý hoặc lỗi nghiệp vụ trở nên nghiêm trọng. Tuy nhiên, **số event được phát tăng không tự chứng minh listener thất bại hoặc publication đang tồn đọng**. Cần kết hợp event metrics với publication state, traces, log và chỉ số nghiệp vụ.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Hiểu metric event publication do Spring Modulith cung cấp.
2. Phân biệt event publication rate với số publication đang chờ, đang xử lý hoặc thất bại.
3. Thu thập Micrometer metrics bằng Spring Boot Actuator và Prometheus.
4. Viết PromQL để phát hiện lưu lượng event tăng bất thường.
5. Thiết kế alert theo module và event type, có ngưỡng tuyệt đối và baseline.
6. Bổ sung custom metrics cho backlog, publication age và failure state.
7. Dùng Prometheus alert rules, Alertmanager và runbook để xử lý cảnh báo.
8. Tránh cảnh báo nhiễu, vòng lặp event và metric cardinality quá cao.

## 2. Spring Modulith cung cấp những event metrics nào?

Spring Modulith observability đăng ký metrics cho domain event được publish trong ứng dụng. Metric tổng hợp quan trọng là:

- `module.events.published` — counter tổng hợp các event publication.
- `module.events.published.$moduleIdentifier.$simpleEventTypeName` — counter cho từng loại event của module, có thể được bổ sung tags riêng.

Metric tổng hợp có các low-cardinality keys:

| Tag | Ý nghĩa |
|---|---|
| `module.event.type` | Tên loại event được phát |
| `module.identifier` | Định danh module phát event |
| `module.name` | Tên hiển thị của module |

Các tag này giúp lọc và nhóm event publication theo module hoặc event type. Metric theo từng event có thể được tùy chỉnh bằng `ModulithEventMetricsCustomizer`.

### 2.1. Phân biệt counter và publication registry

Hai cơ chế này trả lời hai câu hỏi khác nhau:

| Cơ chế | Trả lời câu hỏi | Dữ liệu |
|---|---|---|
| `module.events.published` | Có bao nhiêu domain event được phát? | Counter tích lũy, dùng để tính rate hoặc số event trong một khoảng thời gian |
| Event Publication Registry | Event đã được giao cho transactional listener nào, và listener xử lý đến đâu? | Publication record và trạng thái xử lý |
| Trace/span | Request hoặc listener đã thực thi những bước nào, mất bao lâu? | Timeline của operation được instrument |
| Business metrics | Bao nhiêu đơn hàng, thanh toán hoặc giao dịch thực sự thành công? | Chỉ số nghiệp vụ |

Một event được phát có thể tạo nhiều publication records nếu có nhiều transactional listeners cần nhận event đó. Do đó, số event và số publication records không nhất thiết bằng nhau.

Counter `module.events.published` cũng không phải số lượng event đang chờ xử lý. Không dùng counter này để kết luận backlog tăng, listener thất bại hoặc event đã được xử lý thành công.

### 2.2. Publication Registry theo dõi từng listener

Event Publication Registry ghi nhận publication cho các transactional event listeners. Mặc định, các listener được annotate bằng `@TransactionalEventListener` hoặc meta-annotation phù hợp được theo dõi. Registry lưu publication record trong transaction nghiệp vụ ban đầu; khi listener hoàn tất thành công, record được đánh dấu completed. Nếu listener thất bại, record còn lại để hệ thống có thể phục hồi.

Từ Spring Modulith 2.0, publication lifecycle phân biệt các trạng thái:

| Status | Ý nghĩa |
|---|---|
| `PUBLISHED` | Publication đã được ghi và đang chờ listener xử lý |
| `PROCESSING` | Listener đã nhận publication và đang thực thi |
| `COMPLETED` | Listener hoàn tất thành công |
| `FAILED` | Listener ném exception hoặc publication bị đánh dấu stale |
| `RESUBMITTED` | Publication thất bại đã được gửi xử lý lại |
| `ABANDONED` | Publication bị policy quyết định dừng retry; có từ Spring Modulith 2.2 |

Các trạng thái giúp xác định chính xác backlog và lỗi. Với version trước 2.0, không có đầy đủ status lifecycle này; hãy đối chiếu API và tài liệu đúng version dự án đang dùng.

## 3. Hiểu đúng dấu hiệu event publication tăng bất thường

Một counter chỉ tăng theo thời gian. Khi xem giá trị tích lũy, nó thường tăng ngay cả khi hệ thống vận hành bình thường. Cảnh báo nên dựa trên tốc độ tăng hoặc số lượng event phát sinh trong một cửa sổ thời gian.

| Thời điểm | Counter tích lũy | Event tăng trong 5 phút | Nhận xét |
|---|---:|---:|---|
| 09:00 | 10.000 | — | Giá trị tại thời điểm bắt đầu |
| 09:05 | 10.250 | 250 | 50 event/phút |
| 09:10 | 10.500 | 250 | Nhịp ổn định |
| 09:15 | 12.000 | 1.500 | Tăng lên 300 event/phút |
| 09:20 | 13.800 | 1.800 | Tăng cao tiếp diễn |

Trong ví dụ, counter không có vấn đề vì giá trị tích lũy tăng. Dấu hiệu cần điều tra là tốc độ phát event tăng từ 50 lên 300 event/phút và kéo dài qua nhiều cửa sổ đo.

### 3.1. Rate và increase

Với Prometheus:

- `rate(counter[5m])` tính tốc độ tăng trung bình mỗi giây trong cửa sổ 5 phút và xử lý counter reset.
- `increase(counter[5m])` ước tính tổng số lần counter tăng trong cửa sổ 5 phút.
- `sum by (...)` tổng hợp các series theo những nhãn cần giữ lại.

Dùng `rate` khi muốn so sánh event/giây. Dùng `increase` khi muốn cảnh báo theo tổng số event trong một khoảng thời gian. Không dùng trực tiếp giá trị counter tích lũy để đặt ngưỡng spike.

### 3.2. Một spike có thể là hợp lệ

Ví dụ, chiến dịch flash sale khiến số đơn hàng tăng gấp bốn lần. Nếu mỗi đơn hàng phát một `OrderCompleted` event, event rate tăng theo lưu lượng nghiệp vụ là điều bình thường.

Ngược lại, nếu request rate không tăng nhưng `OrderCompleted` tăng gấp bốn lần, cần kiểm tra:

- Một use case có phát event nhiều lần không?
- Có listener nào phát lại event gốc không?
- Có vòng lặp giữa các module không?
- Có retry hoặc resubmission ngoài dự kiến không?
- Một event có bị phát cho nhiều trạng thái trung gian không?

Để giảm cảnh báo sai, nên so sánh event rate với lưu lượng nghiệp vụ liên quan, ví dụ số order được tạo hoặc số transaction hoàn tất. Tỷ lệ event trên một giao dịch thường có ý nghĩa hơn một ngưỡng event toàn hệ thống.

## 4. Thu thập metrics qua Spring Boot Actuator

Spring Modulith Insight starter là cách thuận tiện để kích hoạt actuator và observability support. Để Prometheus scrape Micrometer metrics, ứng dụng cần registry Prometheus phù hợp với Spring Boot/Micrometer version.

~~~groovy
dependencies {
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Quản lý version bằng Spring Boot và Spring Modulith BOM tương thích. Nếu dự án đã có Insight starter hoặc Prometheus registry qua dependency khác, không cần khai báo trùng.

Cấu hình expose health và Prometheus endpoint:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
~~~

Sau khi ứng dụng khởi động, kiểm tra:

- `GET /actuator/metrics/module.events.published` — xem meter, measurements và tags của Micrometer.
- `GET /actuator/prometheus` — xem định dạng scrape dành cho Prometheus.

Không expose actuator endpoint không cần thiết ra public network. Trong production, giới hạn quyền truy cập endpoint bằng network policy, authentication hoặc management interface phù hợp.

### 4.1. Xác minh tên metric thực tế

Với Prometheus registry, tên meter Micrometer thường được chuyển sang dạng Prometheus, ví dụ:

~~~text
module.events.published
    -> module_events_published_total
~~~

Tên chính xác phụ thuộc registry và naming convention. Kiểm tra `/actuator/prometheus` trước khi viết PromQL. Ví dụ minh họa bên dưới giả định metric được xuất thành `module_events_published_total` và các tag được chuyển thành `module_identifier`, `module_event_type` và `module_name`. Nếu endpoint thực tế dùng label khác, hãy thay đúng tên label trong truy vấn.

~~~text
module_events_published_total{
  module_identifier="order",
  module_event_type="OrderCompleted",
  module_name="Order"
} 18240
~~~

Giá trị `18240` là counter tích lũy, không phải event rate và không phải số publication chưa hoàn tất.

### 4.2. Cấu hình Prometheus scrape

~~~yaml
scrape_configs:
  - job_name: shop-service
    metrics_path: /actuator/prometheus
    scrape_interval: 30s
    static_configs:
      - targets:
          - shop-service:8080
~~~

Trong Kubernetes hoặc môi trường service discovery, thay static target bằng cơ chế discovery đang sử dụng. Đảm bảo Prometheus có thể truy cập endpoint từ mạng nội bộ.

Trước khi tạo alert, xác nhận target của ứng dụng ở trạng thái UP, metric xuất hiện, label có giá trị như mong đợi và counter tăng khi ứng dụng thực sự publish event.

## 5. Viết PromQL để phát hiện spike

### 5.1. Xem event rate theo module và event type

~~~promql
sum by (module_identifier, module_event_type) (
  rate(module_events_published_total[5m])
)
~~~

Kết quả là event/giây theo từng module và event type. Đây là truy vấn cơ bản để xây dựng dashboard hoặc kiểm tra trước khi đặt alert.

Nếu muốn xem tổng số event trong 5 phút:

~~~promql
sum by (module_identifier, module_event_type) (
  increase(module_events_published_total[5m])
)
~~~

### 5.2. Cảnh báo theo ngưỡng tuyệt đối

Ví dụ, cảnh báo khi một module phát hơn 10 event/giây trong ít nhất 10 phút:

~~~promql
sum by (module_identifier, module_event_type) (
  rate(module_events_published_total[5m])
) > 10
~~~

Ngưỡng 10 event/giây chỉ là ví dụ. Hãy đo traffic thực tế và đặt ngưỡng riêng cho từng event type. Event `OrderCompleted` có thể có volume khác xa event `PaymentCaptured`.

### 5.3. Cảnh báo theo mức tăng so với baseline

Ví dụ so sánh rate hiện tại với cùng thời điểm ngày trước:

~~~promql
(
  sum by (module_identifier, module_event_type) (
    rate(module_events_published_total[5m])
  ) > 5
)
and
(
  sum by (module_identifier, module_event_type) (
    rate(module_events_published_total[5m])
  )
  >
  3 *
  sum by (module_identifier, module_event_type) (
    rate(module_events_published_total[5m] offset 1d)
  )
)
~~~

Truy vấn này yêu cầu rate hiện tại lớn hơn 5 event/giây và lớn hơn ba lần rate của cửa sổ tương ứng một ngày trước. Hai ngưỡng đều là ví dụ cần hiệu chỉnh.

Điều kiện baseline có thể không trả kết quả nếu series chưa tồn tại ở khoảng thời gian offset. Với ứng dụng mới hoặc event type mới, hãy bắt đầu bằng ngưỡng tuyệt đối; chỉ bật so sánh baseline khi đã có đủ lịch sử. Hệ thống có chu kỳ tuần hoặc mùa vụ nên cân nhắc baseline theo cùng ngày trong tuần hoặc cùng khung giờ thay vì chỉ offset một ngày.

### 5.4. Chuẩn hóa theo lưu lượng nghiệp vụ

Một spike event có thể chỉ phản ánh việc số đơn hàng tăng. Nếu đã có counter nghiệp vụ như số order được tạo, có thể theo dõi tỷ lệ:

~~~promql
sum(rate(module_events_published_total{module_event_type="OrderCompleted"}[5m]))
/
clamp_min(
  sum(rate(shop_orders_completed_total[5m])),
  1
)
~~~

Truy vấn trên chỉ minh họa ý tưởng. Metric `shop_orders_completed_total` là metric nghiệp vụ do ứng dụng tự định nghĩa; nó không phải metric mặc định của Spring Modulith.

Tỷ lệ event trên transaction tăng bất thường có thể chỉ ra event bị phát lặp hoặc thay đổi logic. Chọn đúng mẫu số theo ý nghĩa nghiệp vụ: event hoàn tất đơn hàng nên so với số đơn hàng hoàn tất, không nên so với tổng HTTP requests không liên quan.

## 6. Tạo Prometheus alert rules

Prometheus alert rule chuyển PromQL thành trạng thái cảnh báo. Trường `for` yêu cầu điều kiện tiếp tục đúng trong một khoảng thời gian trước khi alert chuyển sang firing; điều này giúp giảm cảnh báo do spike ngắn. Alertmanager xử lý grouping, routing, silencing và gửi notification.

Ví dụ file `spring-modulith-alerts.yml`:

~~~yaml
groups:
  - name: spring-modulith-event-publications
    interval: 30s
    rules:
      - alert: SpringModulithEventPublicationSpike
        expr: |
          (
            sum by (module_identifier, module_event_type) (
              rate(module_events_published_total[5m])
            ) > 10
          )
          and
          (
            sum by (module_identifier, module_event_type) (
              rate(module_events_published_total[5m])
            )
            >
            3 *
            sum by (module_identifier, module_event_type) (
              rate(module_events_published_total[5m] offset 1d)
            )
          )
        for: 10m
        labels:
          severity: warning
          team: application-platform
        annotations:
          summary: "Event publication tăng bất thường ở module {{ $labels.module_identifier }}"
          description: "Event {{ $labels.module_event_type }} đang được publish với rate {{ $value }} event/giây."
          runbook_url: "https://runbooks.example.invalid/spring-modulith/event-publication-spike"
~~~

Trong ví dụ, `expr` yêu cầu event rate vượt ngưỡng tuyệt đối và lớn hơn ba lần baseline. `for: 10m` chỉ chuyển alert sang firing khi điều kiện duy trì liên tục 10 phút. `severity` và `team` giúp Alertmanager định tuyến. `summary`, `description` và `runbook_url` cung cấp ngữ cảnh để người nhận xử lý.

Thay URL runbook minh họa bằng địa chỉ nội bộ thật của nhóm vận hành. Không sao chép nguyên các ngưỡng ví dụ vào production nếu chưa kiểm tra traffic.

### 6.1. Phân biệt pending và firing

Prometheus có hai trạng thái thường gặp:

- **Pending:** điều kiện alert đúng nhưng chưa đủ thời gian `for`.
- **Firing:** điều kiện tiếp tục đúng đủ thời gian và alert cần được gửi đi.

Nếu điều kiện mất trước khi hết `for`, alert có thể trở lại inactive mà không gửi notification. Trường `keep_firing_for` có thể giữ alert firing thêm một khoảng thời gian sau khi điều kiện hết, giúp tránh thông báo chập chờn trong một số tình huống.

### 6.2. Dùng Alertmanager để quản lý notification

Prometheus đánh giá điều kiện. Alertmanager chịu trách nhiệm gửi notification và quản lý grouping, routing, silencing, inhibit và giới hạn tần suất gửi để tránh spam.

Không gửi một notification cho mỗi event hoặc mỗi order ID. Alert nên nhóm theo service, module và event type để người trực nhận diện phạm vi sự cố.

## 7. Cảnh báo backlog và publication thất bại

Event rate cao chỉ cho biết có nhiều event được phát. Để phát hiện listener không xử lý kịp, cần quan sát Event Publication Registry hoặc một nguồn dữ liệu trạng thái tương đương.

### 7.1. Các chỉ số nên theo dõi

| Chỉ số | Ý nghĩa | Cảnh báo khi |
|---|---|---|
| Publication count theo status | Số record PUBLISHED, PROCESSING, FAILED, RESUBMITTED | FAILED tăng hoặc backlog liên tục tăng |
| Oldest publication age | Tuổi của record chưa hoàn tất lâu nhất | Vượt SLA xử lý event |
| Completion latency | Thời gian từ publish đến complete | p95/p99 tăng cao |
| Completion attempts | Số lần listener đã được thử | Tăng vượt mức retry dự kiến |
| Abandoned publications | Publication đã bị dừng retry theo policy | Có record mới bị abandoned |
| Event rate | Tốc độ event được phát | Tăng đột biến so với baseline |

Các metric trạng thái ở bảng trên là metric vận hành nên bổ sung cho ứng dụng hoặc hệ thống lưu trữ. Chúng **không phải tên metric mặc định do Spring Modulith cung cấp**.

### 7.2. Thiết kế custom metrics cho publication registry

Có thể định nghĩa một bộ metric riêng, ví dụ:

~~~text
app_modulith_event_publications{
  module_identifier="order",
  event_type="OrderCompleted",
  status="FAILED"
} 4

app_modulith_event_publication_oldest_age_seconds{
  module_identifier="notification",
  event_type="OrderCompleted",
  status="PUBLISHED"
} 420
~~~

Hai metric này là quy ước do ứng dụng tự xây dựng:

- `app_modulith_event_publications` là gauge số publication theo status.
- `app_modulith_event_publication_oldest_age_seconds` là tuổi của publication cũ nhất theo nhóm.

Nguồn dữ liệu có thể là Event Publication Registry/API hoặc một truy vấn aggregate hiệu quả trên publication store. Với backlog lớn, không nên tải toàn bộ event payload và materialize mọi record mỗi lần Prometheus scrape. Hãy tính aggregate theo chu kỳ có kiểm soát hoặc dùng truy vấn dữ liệu chỉ đọc phù hợp.

Trong triển khai nhiều replica dùng chung một publication store, tránh cộng cùng một số đếm toàn cục từ mọi Pod. Có thể xuất metric từ một collector/job duy nhất hoặc chọn phép tổng hợp phù hợp để không nhân số backlog theo số replica.

### 7.3. Alert khi có failed publication

~~~promql
sum by (module_identifier, event_type) (
  app_modulith_event_publications{status="FAILED"}
) > 0
~~~

Một failed publication có thể đáng điều tra ngay, nhất là với event thanh toán hoặc hoàn tất đơn hàng. Với event có thể retry tự động và không ảnh hưởng SLA, nhóm có thể dùng ngưỡng số lượng hoặc thời gian trước khi paging.

### 7.4. Alert khi publication quá cũ

~~~promql
max by (module_identifier, event_type) (
  app_modulith_event_publication_oldest_age_seconds{
    status=~"PUBLISHED|PROCESSING|RESUBMITTED"
  }
) > 300
~~~

Ví dụ trên cảnh báo khi publication chưa hoàn tất cũ hơn 300 giây. Ngưỡng phải dựa trên SLA listener; một listener xử lý batch hợp lệ trong 8 phút không nên bị cảnh báo ở mốc 5 phút.

### 7.5. Cấu hình Staleness Monitor

Từ Spring Modulith 2.0, Staleness Monitor có thể đánh dấu publication ở các trạng thái `PUBLISHED`, `PROCESSING` hoặc `RESUBMITTED` thành `FAILED` khi chúng cũ hơn duration được cấu hình.

~~~yaml
spring:
  modulith:
    events:
      staleness:
        check-interval: 1m
        published: 3m
        processing: 10m
        resubmitted: 5m
~~~

Các giá trị là ví dụ. Mặc định, ba duration `published`, `processing` và `resubmitted` đều bằng zero; khi tất cả bằng zero, Staleness Monitor không đăng ký scheduled task. Khi ít nhất một duration khác zero, monitor chạy theo `check-interval` và đánh dấu publication stale thành FAILED.

Staleness Monitor **đánh dấu FAILED, không đồng nghĩa tự động resubmit mọi publication**. Việc phục hồi cần cơ chế resubmission và policy phù hợp.

Không đặt `processing` ngắn hơn thời gian listener hợp lệ. Nếu listener vẫn đang chạy nhưng publication bị đánh dấu stale, một lần resubmission có thể khiến side effect bị thực thi lặp. Listener cần idempotency và ngưỡng staleness phải dựa trên thời gian xử lý thực tế.

## 8. Dùng ModulithEventMetricsCustomizer đúng cách

Spring Modulith cho phép bổ sung tags vào metric riêng của một loại event thông qua `ModulithEventMetricsCustomizer`.

~~~java
@Configuration
class EventMetricsConfiguration {

    @Bean
    ModulithEventMetricsCustomizer eventMetricsCustomizer() {
        return metrics -> metrics.customize(
                OrderCompleted.class,
                (event, meter) -> meter.tags(
                        "sales-channel", event.salesChannel()
                )
        );
    }
}
~~~

Tag `sales-channel` phù hợp nếu miền giá trị nhỏ và được kiểm soát, ví dụ `web`, `mobile`, `partner`.

Không thêm các giá trị thay đổi liên tục như order ID, customer ID, email, transaction UUID, timestamp chính xác, raw exception message hoặc nội dung event. Những giá trị đó tạo ra rất nhiều time series, làm tăng bộ nhớ và chi phí Prometheus, đồng thời khiến dashboard và alert khó tổng hợp.

Nếu cần điều tra một order cụ thể, dùng trace ID, log có correlation ID hoặc hệ thống tra cứu nghiệp vụ thay vì metric label.

## 9. Thiết kế ngưỡng và mức độ cảnh báo

Một ngưỡng tốt dựa trên đặc điểm event, tải bình thường và tác động nghiệp vụ. Không nên dùng cùng một threshold cho mọi module.

| Severity | Điều kiện ví dụ | Hành động |
|---|---|---|
| Info | Event rate tăng nhẹ trong giờ cao điểm | Theo dõi dashboard |
| Warning | Event rate cao hơn baseline trong 10 phút | Kiểm tra traffic, event type và traces |
| Critical | FAILED publication tăng hoặc oldest age vượt SLA nghiêm trọng | On-call điều tra listener/store và quyết định phục hồi |
| Page | Event quan trọng không hoàn tất, ảnh hưởng trực tiếp tới giao dịch | Kích hoạt quy trình incident |

Không phải mọi spike đều cần page. Alert chỉ nên paging khi có khả năng ảnh hưởng tới người dùng, dữ liệu hoặc SLA.

### 9.1. Chọn baseline

Có thể dùng ngưỡng cố định theo module/event type, so sánh cùng khung giờ ngày trước, cùng thứ trong tuần, rolling average/percentile của 7 hoặc 28 ngày, hoặc tỷ lệ event trên một business transaction.

Khi hệ thống có mùa vụ, baseline cần phản ánh chu kỳ thực tế. Một spike vào ngày chạy chiến dịch có thể là bình thường; một spike nhỏ nhưng kéo dài ở event thanh toán lại có thể đáng cảnh báo hơn.

### 9.2. Dùng nhiều tín hiệu để giảm false positive

Ví dụ, chỉ cảnh báo spike nếu đồng thời có event rate cao hơn ngưỡng tuyệt đối, event rate cao hơn baseline, tỷ lệ event trên business transaction tăng hoặc backlog/oldest age tăng theo sau.

Nếu event rate tăng nhưng business transaction tăng cùng tỷ lệ, listener hoàn tất đúng SLA và backlog không tăng, đây có thể là lưu lượng hợp lệ.

### 9.3. Theo dõi missing data

Metric không xuất hiện có thể do ứng dụng chưa publish event nào, Prometheus không scrape được endpoint, registry chưa được cấu hình, target bị mất kết nối hoặc series mới chưa được tạo.

Không diễn giải việc thiếu event metric là “không có lỗi” hoặc “không có event bị mất”. Theo dõi riêng target availability bằng `up` và cân nhắc heartbeat/metric dự kiến có mặt nếu cần cảnh báo missing telemetry.

## 10. Dashboard cho event publication

Một dashboard vận hành nên có các panel giúp trả lời nhanh: event nào đang tăng, module nào phát nhiều, listener có theo kịp không?

| Panel | Truy vấn hoặc dữ liệu |
|---|---|
| Event publication rate | `rate(module_events_published_total[5m])` |
| Event count theo 5 phút | `increase(module_events_published_total[5m])` |
| Rate theo module | `sum by (module_identifier)` |
| Rate theo event type | `sum by (module_event_type)` |
| Failed publication | Custom gauge theo status FAILED |
| Oldest incomplete publication | Custom oldest-age gauge |
| Completion latency | Custom histogram hoặc timer |
| Business throughput | Order/payment completed metrics |
| Listener traces | Trace backend với module invocation spans |

Một panel chỉ hiển thị event rate có thể khiến người xem khó phân biệt tăng trưởng hợp lệ và bất thường. Nên đặt cạnh HTTP request rate, business throughput, backlog, failed publications, listener duration, dependency errors và trace timeline của một request mẫu.

## 11. Runbook: xử lý cảnh báo event publication spike

Khi nhận `SpringModulithEventPublicationSpike`, làm theo trình tự dưới đây.

### Bước 1 — Xác định phạm vi

Từ alert labels, ghi nhận module phát event, event type, event rate hiện tại, mức tăng so với baseline, service/environment và thời điểm bắt đầu.

Không bắt đầu bằng việc resubmit event hoặc restart service khi chưa biết nguyên nhân.

### Bước 2 — So sánh với lưu lượng nghiệp vụ

Kiểm tra request rate, order/payment throughput và business metrics. Nếu event rate tăng cùng business throughput, spike có thể hợp lệ.

Nếu event rate tăng nhưng số transaction không đổi, điều tra duplicate publication hoặc event loop.

### Bước 3 — Kiểm tra event producer

Tìm trace và log của module phát event:

- Một use case có phát event nhiều lần không?
- Có nhánh retry nào publish lại event gốc không?
- Một listener có phát event mới dẫn tới listener cũ chạy lại không?
- Có thay đổi gần đây làm một event được phát ở nhiều trạng thái không?
- Có batch job hoặc scheduler vừa được bật lại không?

### Bước 4 — Kiểm tra publication registry

Nếu registry được cấu hình, kiểm tra status:

- PUBLISHED tăng: listener chưa nhận hoặc chưa xử lý kịp.
- PROCESSING tăng lâu: listener có thể chậm, bị treo hoặc đang chạy tác vụ dài.
- FAILED tăng: listener ném exception hoặc publication bị đánh dấu stale.
- RESUBMITTED tăng: có hoạt động phục hồi/retry.
- ABANDONED tăng: policy đã dừng retry; cần xác minh nghiệp vụ và lý do.

Không nhầm một publication đang PROCESSING với publication FAILED. Cũng không coi mọi publication chưa COMPLETED là mất dữ liệu; listener có thể đang thực thi hợp lệ.

### Bước 5 — Tìm listener chậm hoặc lỗi

Dùng trace backend để tìm module-entry spans và listener spans. Đối chiếu thời gian thực thi, exception/status, external calls, lock contention, database latency, số lần retry và context propagation nếu listener chạy bất đồng bộ.

Nếu trace thiếu, kiểm tra sampling/exporter và log correlation. Thiếu trace không chứng minh listener chưa chạy.

### Bước 6 — Quyết định phục hồi

Chỉ resubmit sau khi xác định lỗi tạm thời đã được khắc phục hoặc có khả năng xử lý lại, listener có idempotency, batch size/concurrency phù hợp, không có instance khác đang xử lý cùng publication và việc resubmit không làm backend quá tải thêm.

Spring Modulith 2.0 cung cấp API `FailedEventPublications` và `ResubmissionOptions` để resubmit failed publications có chọn lọc. Không dùng resubmit hàng loạt như phản xạ đầu tiên khi chưa kiểm tra nguyên nhân.

### Bước 7 — Xác nhận khôi phục

Sau khi xử lý, xác nhận event rate trở về mức hợp lý, failed publication không tăng thêm, oldest incomplete age giảm, listener completion trở lại bình thường, business transaction thành công và alert chuyển resolved.

Ghi lại nguyên nhân, thời điểm, module/event type, hành động phục hồi và thay đổi cần thực hiện để tránh tái diễn.

## 12. Những lỗi alerting thường gặp

### 12.1. Cảnh báo trên counter tích lũy

Biểu thức `module_events_published_total > 100000` sẽ đúng mãi sau khi counter vượt 100.000. Hãy dùng `rate` hoặc `increase` để phát hiện thay đổi theo thời gian.

### 12.2. Dùng event rate làm backlog

Event rate đo số event được phát. Backlog là số publication chưa hoàn tất hoặc thời gian chờ của chúng. Cần custom metrics từ registry/store hoặc nguồn queue tương ứng.

### 12.3. Dùng một threshold cho tất cả event

Một event hiếm như `RefundRequested` và event phổ biến như `OrderItemViewed` có phân phối rất khác nhau. Tách alert theo module/event type hoặc business criticality.

### 12.4. Không đặt for

Một spike 30 giây có thể không cần đánh thức on-call. Dùng trường `for` để yêu cầu điều kiện tồn tại đủ lâu, trừ khi event critical cần phản ứng tức thì.

### 12.5. Đưa ID vào metric labels

Order ID hoặc customer ID tạo ra một series cho từng giá trị. Dùng trace/log để tìm entity cụ thể; metric chỉ giữ các dimension có miền giá trị nhỏ.

### 12.6. Resubmit trước khi xử lý nguyên nhân

Nếu listener lỗi vì downstream vẫn đang outage, resubmit liên tục chỉ làm tăng tải và số completion attempts. Khắc phục dependency, giới hạn batch/concurrency và sau đó resubmit có kiểm soát.

### 12.7. Không giám sát publication age

Một listener có thể không ném exception nhưng vẫn bị treo hoặc xử lý quá lâu. Theo dõi tuổi của PUBLISHED/PROCESSING/RESUBMITTED để phát hiện tình trạng này.

### 12.8. Coi ABANDONED là COMPLETED

ABANDONED có nghĩa policy quyết định ngừng retry. Đây không phải thành công. Với event ảnh hưởng tới nghiệp vụ quan trọng, cần cảnh báo và có quy trình xử lý thủ công.

## 13. Thực hành: tạo alert cho OrderCompleted

Dựng ứng dụng Spring Modulith có module `order`, `inventory` và `notification`. Module `order` publish event `OrderCompleted`; hai module còn lại xử lý event qua listener.

### Phần A — Quan sát metric

1. Thêm Insight starter và Prometheus registry tương thích.
2. Expose `/actuator/prometheus`.
3. Gửi một số request hoàn tất đơn hàng.
4. Kiểm tra counter `module.events.published`.
5. Xác nhận tag module và event type.
6. Dùng PromQL `rate` và `increase` để xem volume theo cửa sổ 5 phút.

### Phần B — Tạo spike có kiểm soát

1. Gửi request với tốc độ ổn định để tạo baseline.
2. Tăng tốc độ tạo order trong môi trường test.
3. Quan sát event rate theo module và event type.
4. So sánh event rate với số order thực tế.
5. Thay đổi code test để phát cùng event hai lần cho một use case.
6. Quan sát tỷ lệ event trên business transaction và xác định dấu hiệu duplicate.

### Phần C — Mô phỏng listener chậm hoặc lỗi

1. Thêm độ trễ có kiểm soát trong listener test.
2. Quan sát PUBLISHED/PROCESSING và oldest age nếu đã có custom registry metrics.
3. Làm listener ném exception trong test.
4. Kiểm tra FAILED publication nếu dùng Spring Modulith version có lifecycle status.
5. Khôi phục listener và thực hiện resubmission chọn lọc.
6. Xác nhận completion và business state đúng, không tạo side effect trùng.

### Phần D — Kiểm tra alert lifecycle

1. Nạp alert rule vào Prometheus.
2. Tạo event rate vượt threshold.
3. Xác nhận alert ở pending trong khoảng for.
4. Giữ điều kiện đủ lâu để chuyển firing.
5. Kiểm tra labels, annotations và Alertmanager routing.
6. Dừng spike và xác nhận alert resolved.
7. Điều chỉnh threshold để tránh cảnh báo trong giờ cao điểm bình thường.

### Bảng kết quả mong đợi

| Tình huống | Event rate | Registry/backlog | Alert |
|---|---|---|---|
| Lưu lượng bình thường | Ổn định | Thấp | Inactive |
| Business traffic tăng hợp lệ | Tăng tương ứng | Listener theo kịp | Có thể inactive nếu baseline/ratio bình thường |
| Duplicate event | Tăng nhanh hơn business throughput | Có thể tăng publication records | Warning nếu vượt rule |
| Listener chậm | Có thể bình thường | PROCESSING/PUBLISHED age tăng | Backlog/age alert |
| Listener lỗi | Có thể bình thường | FAILED tăng | Failed publication alert |
| Resubmit có kiểm soát | Có thể có burst ngắn | RESUBMITTED rồi PROCESSING | Theo dõi trong thời gian phục hồi |
| Listener phục hồi | Trở lại baseline | Oldest age giảm, FAILED ổn định | Resolved |

Đây là kết quả kỳ vọng của bài thực hành, không phải báo cáo một Prometheus server hoặc ứng dụng đã được chạy trong repository.

## 14. Checklist triển khai production

- [ ] Spring Modulith observability được bật và metrics xuất hiện trong Actuator.
- [ ] Prometheus scrape đúng endpoint `/actuator/prometheus`.
- [ ] Đã xác nhận tên metric và label thực tế trước khi viết PromQL.
- [ ] Event rate được tính bằng `rate` hoặc `increase`, không dùng counter tích lũy làm threshold.
- [ ] Alert được phân nhóm theo module và event type.
- [ ] Có threshold tuyệt đối và baseline phù hợp với traffic.
- [ ] Đã so sánh event rate với business transaction rate.
- [ ] Có metric riêng cho failed publication và oldest incomplete age nếu cần.
- [ ] Status lifecycle và Staleness Monitor tương thích với Spring Modulith version đang dùng.
- [ ] Staleness duration lớn hơn thời gian listener hợp lệ theo SLA.
- [ ] Listener có idempotency trước khi bật resubmission tự động hoặc thủ công.
- [ ] Alert có for, severity, owner và runbook.
- [ ] Alertmanager grouping, routing, silence và rate limiting đã được cấu hình.
- [ ] Metric labels không chứa order ID, customer ID hoặc dữ liệu biến đổi liên tục.
- [ ] Có dashboard ghép event rate, business throughput, backlog, errors và traces.
- [ ] Có quy trình xác minh sau resubmission và theo dõi side effect trùng lặp.

## 15. Ghi nhớ

- `module.events.published` là counter số event được phát, không phải backlog hoặc số listener thất bại.
- Một event có thể tạo nhiều publication records vì registry theo dõi từng transactional listener.
- Dùng `rate` hoặc `increase` để phát hiện spike; so sánh với baseline và business throughput để giảm false positive.
- Từ Spring Modulith 2.0, publication status giúp phân biệt PUBLISHED, PROCESSING, COMPLETED, FAILED và RESUBMITTED; ABANDONED có từ 2.2.
- Staleness Monitor mặc định không chạy vì các duration mặc định bằng zero. Khi bật, nó đánh dấu publication stale thành FAILED; việc resubmit cần policy và hành động phục hồi riêng.
- Alert cần cung cấp module, event type, rate, baseline và runbook để người trực xác định nguyên nhân.
- Không dùng metric labels để chứa ID nghiệp vụ; dùng trace và log khi cần điều tra từng giao dịch.

## Tài liệu tham khảo

1. [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html) — Insight starter, module observability spans và event metrics.
2. [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html) — Event Publication Registry, publication lifecycle, staleness monitor và resubmission.
3. [Spring Modulith — Configuration Properties](https://docs.spring.io/spring-modulith/reference/appendix.html) — Các thuộc tính `spring.modulith.events.staleness.*`, completion mode và registry trigger.
4. [Spring Modulith — EventPublication API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/EventPublication.html) — Publication status, publication date và completion attempts.
5. [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) — Micrometer metrics và Actuator endpoint.
6. [Prometheus — Querying Basics](https://prometheus.io/docs/prometheus/latest/querying/basics/) — Time series, selectors và PromQL.
7. [Prometheus — Query Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/) — `rate`, `increase` và các hàm phân tích time series.
8. [Prometheus — Alerting Rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/) — `for`, `keep_firing_for`, labels, annotations và alert states.
9. [Prometheus — Alertmanager](https://prometheus.io/docs/alerting/latest/alertmanager/) — Grouping, routing, silencing và notification handling.

