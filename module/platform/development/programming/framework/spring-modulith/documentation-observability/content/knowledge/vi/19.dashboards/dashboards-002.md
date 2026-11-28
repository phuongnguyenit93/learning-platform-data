# Dashboard số lần công bố domain event

Trong ứng dụng Spring Modulith, domain event giúp các application module trao đổi với nhau mà không cần phụ thuộc trực tiếp vào implementation của module phát hoặc nhận. Khi hệ thống chạy, đội vận hành cần biết **event nào đang được công bố, module nào phát nhiều event, lưu lượng thay đổi theo thời gian ra sao**. Dashboard số lần công bố domain event trả lời các câu hỏi đó bằng metrics của Spring Modulith và biểu đồ Prometheus/Grafana.

Spring Modulith cung cấp counter tổng hợp `module.events.published` cho các event publication được instrumentation theo dõi, cùng counter riêng cho từng loại event. Counter tổng hợp có thể phân nhóm bằng metadata ít biến thể như module identifier, module name và event type. Đây là cơ sở để dựng dashboard mà không phải tự đếm từng event trong code nghiệp vụ.

Bài thuộc chương **Dashboard** của mô-đun **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Mô-đun hướng dẫn dùng Spring Modulith để sinh tài liệu ranh giới application module và quan sát tương tác giữa các phần trong Spring Boot qua module graph, Actuator, event metrics, tracing và context propagation. Bài này tập trung vào dashboard publication count; trạng thái xử lý listener là một câu hỏi vận hành riêng.

> Ví dụ dựa trên Spring Modulith 2.2, Micrometer, Spring Boot Actuator, Prometheus và Grafana. Tên metric/label sau khi scrape có thể được chuẩn hóa theo naming convention của registry. Luôn kiểm tra endpoint `/actuator/prometheus` của ứng dụng trước khi sao chép nguyên PromQL.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích counter publication metrics được Spring Modulith cung cấp.
2. Phân biệt counter tổng hợp với counter riêng cho từng event type.
3. Cấu hình Spring Modulith Insight, Actuator và Prometheus registry.
4. Xác nhận metric và tags qua `/actuator/metrics` và `/actuator/prometheus`.
5. Cấu hình Prometheus scrape endpoint của Spring Boot.
6. Tạo Grafana dashboard hiển thị tổng publication, publication theo module và event type.
7. Dùng `rate()` và `increase()` đúng với counter tích lũy.
8. Tổng hợp dữ liệu từ nhiều instance mà không đếm nhầm metric.
9. Tránh cardinality cao khi bổ sung tags.
10. Phân biệt số lần publish với số listener hoàn tất, thất bại hoặc retry.

## 2. Dashboard cần trả lời câu hỏi nào?

Một dashboard vận hành tốt nên giúp người xem trả lời các câu hỏi cụ thể:

- Trong khoảng thời gian đang chọn, ứng dụng công bố bao nhiêu event?
- Publication rate hiện tại là bao nhiêu event/giây?
- Module `orders`, `payments`, `inventory` đang phát event với nhịp độ thế nào?
- Event type nào được phát nhiều nhất?
- Có event type nào tăng đột biến so với baseline?
- Một module có ngừng phát event trong khi nghiệp vụ vẫn đang diễn ra không?
- Khi chạy nhiều replica, tổng publication của cả service là bao nhiêu?

Dashboard **không tự trả lời** các câu hỏi:

- Listener đã xử lý thành công bao nhiêu publication?
- Publication nào đang `FAILED`, `PROCESSING` hay `ABANDONED`?
- Một event cụ thể có payload gì?
- Request nào đã phát event đó?
- Module có dependency kiến trúc hợp lệ hay không?

Các câu hỏi trên cần Event Publication Registry, logs, tracing hoặc module graph tùy trường hợp.

## 3. Các metric publication của Spring Modulith

Spring Modulith đăng ký metrics cho các domain event publication mà observability support theo dõi. Tài liệu Spring Modulith mô tả hai dạng counter:

| Meter name trong Micrometer | Loại | Ý nghĩa |
| --- | --- | --- |
| `module.events.published` | Counter tổng hợp | Tổng số event publications được theo dõi |
| `module.events.published.$moduleIdentifier.$simpleEventTypeName` | Counter riêng | Số lần publication của một loại event cụ thể trong một module |

### 3.1. Counter tổng hợp

`module.events.published` là counter tổng hợp. Các low-cardinality keys được Spring Modulith tài liệu hóa:

| Key trong Micrometer | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `module.event.type` | Loại event được phát | `OrderPlaced` |
| `module.identifier` | Technical identifier của module | `orders` |
| `module.name` | Tên hiển thị của module | `Orders` |

Với counter tổng hợp, ta có thể tạo dashboard:

- Tổng event publication của toàn ứng dụng.
- Publication theo module.
- Publication theo event type.
- Publication theo cặp module và event type.

### 3.2. Counter riêng theo event type

Spring Modulith còn tạo counter có tên theo cấu trúc:

~~~text
module.events.published.<moduleIdentifier>.<simpleEventTypeName>
~~~

Ví dụ minh họa:

~~~text
module.events.published.orders.OrderPlaced
module.events.published.orders.OrderCancelled
module.events.published.inventory.StockReserved
~~~

Các counter riêng này có low-cardinality keys `module.identifier` và `module.name`. Có thể bổ sung domain-specific tags cho individual event counters bằng `ModulithEventMetricsCustomizer`.

### 3.3. Chọn counter nào cho dashboard?

**Ưu tiên counter tổng hợp** khi muốn dashboard linh hoạt theo module/event type bằng Grafana variables. Một metric name có nhiều chuỗi tag giúp truy vấn động.

Counter riêng hữu ích khi:

- Chỉ cần theo dõi một event type quan trọng.
- Muốn thêm tag nghiệp vụ hữu hạn qua customizer.
- Muốn truy vấn trực tiếp một meter đã biết.

Không cộng cả counter tổng hợp và các counter riêng trong cùng một panel tổng. Chúng là hai cách biểu diễn cùng hoạt động publication ở các mức tổng hợp khác nhau; cộng cả hai sẽ **đếm trùng**.

## 4. Chuẩn bị Spring Boot Actuator và Prometheus

### 4.1. Dependency

Với Spring Boot và Spring Modulith được quản lý version qua BOM tương thích:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    // Actuator support và Spring Modulith observability.
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'

    // Prometheus MeterRegistry.
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

`spring-modulith-starter-insight` cung cấp Actuator và observability support của Spring Modulith. Prometheus registry là dependency riêng để xuất metrics theo định dạng Prometheus. Nếu dự án đã có Actuator hoặc starter insight thông qua dependency khác, tránh khai báo trùng không cần thiết.

### 4.2. Expose các endpoint cần dùng

Ví dụ `application.yml` cho lab:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - metrics
          - prometheus
          - modulith
~~~

Trong production, chỉ expose endpoint mà monitoring thực sự cần. Endpoint `metrics` có thể giúp khám phá meter; endpoint `prometheus` phục vụ scrape; endpoint `modulith` cung cấp cấu trúc module. Bảo vệ các endpoint này bằng management network và authorization phù hợp.

### 4.3. Cấu hình tên service

~~~yaml
spring:
  application:
    name: shop-modulith
~~~

Tên service giúp Prometheus/Grafana phân biệt target khi có nhiều ứng dụng. Nếu scrape nhiều môi trường, thêm label `environment` từ cấu hình Prometheus hoặc service discovery; không đưa môi trường vào metric name.

## 5. Xác nhận metric trước khi viết PromQL

Không nên dựng dashboard dựa trên tên metric suy đoán. Kiểm tra dữ liệu ứng dụng thực sự xuất ra.

### 5.1. Khám phá bằng Actuator metrics endpoint

Gọi:

~~~bash
curl -s http://localhost:8080/actuator/metrics
~~~

Tìm metric:

~~~bash
curl -s http://localhost:8080/actuator/metrics/module.events.published
~~~

Một response minh họa:

~~~json
{
  "name": "module.events.published",
  "measurements": [
    {
      "statistic": "COUNT",
      "value": 1250.0
    }
  ],
  "availableTags": [
    {
      "tag": "module.identifier",
      "values": ["orders", "payments", "inventory"]
    },
    {
      "tag": "module.name",
      "values": ["Orders", "Payments", "Inventory"]
    },
    {
      "tag": "module.event.type",
      "values": ["OrderPlaced", "OrderCancelled", "StockReserved"]
    }
  ]
}
~~~

Các giá trị chỉ là dữ liệu minh họa. Response thật phụ thuộc các event đã được phát trong tiến trình, phiên bản Spring Modulith và customizations.

Có thể lọc một module để kiểm tra:

~~~bash
curl -s "http://localhost:8080/actuator/metrics/module.events.published?tag=module.identifier:orders"
~~~

Actuator metrics endpoint sử dụng tên meter và tag key của Micrometer; đây không nhất thiết là tên label sau khi chuyển sang Prometheus.

### 5.2. Kiểm tra Prometheus scrape output

Gọi:

~~~bash
curl -s http://localhost:8080/actuator/prometheus
~~~

Tìm dòng có metric name tương ứng với `module.events.published`. Với Prometheus naming convention thường gặp, counter có thể được xuất dưới dạng:

~~~text
module_events_published_total{
  module_identifier="orders",
  module_name="Orders",
  module_event_type="OrderPlaced"
} 1250.0
~~~

Đây là **ví dụ định dạng**, không phải cam kết rằng mọi phiên bản hoặc registry luôn xuất đúng tên label này. Micrometer chuyển tên meter/tag sang quy ước Prometheus; kiểm tra output thực tế để xác định tên cuối cùng, suffix `_total` và các labels.

### 5.3. Đối chiếu hai endpoint

| Nơi kiểm tra | Dùng để xác minh |
| --- | --- |
| `/actuator/metrics/module.events.published` | Meter Micrometer, COUNT và availableTags |
| `/actuator/prometheus` | Metric name, suffix và label names thực sự được scrape |
| Prometheus expression browser | Series đã được ingest và có thể truy vấn |
| Grafana Explore | Query, label values và khoảng thời gian hiển thị |

Nếu Actuator metrics có counter nhưng Prometheus không thấy, kiểm tra registry, exposure, scrape target và thời điểm scrape. Nếu không thấy ở cả hai, kiểm tra dependency, instrumentation và liệu event đã được phát hay chưa.

## 6. Cấu hình Prometheus scrape

Một cấu hình tối thiểu cho môi trường local:

~~~yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: shop-modulith
    metrics_path: /actuator/prometheus
    static_configs:
      - targets:
          - shop-modulith:8080
        labels:
          environment: local
~~~

Nếu Prometheus chạy trực tiếp trên host, target có thể là `localhost:8080`. Nếu chạy trong Docker Compose, dùng tên service/container mà Prometheus có thể phân giải qua network Docker.

Nếu Actuator chạy ở port riêng hoặc base path riêng, sửa target/path cho khớp. Ví dụ management port 8081 và base path `/manage`:

~~~yaml
scrape_configs:
  - job_name: shop-modulith
    metrics_path: /manage/prometheus
    static_configs:
      - targets: ["shop-modulith:8081"]
~~~

**Không expose endpoint Prometheus công khai** chỉ để Prometheus scrape. Hãy đặt Prometheus và management endpoint trong mạng quản trị phù hợp, giới hạn firewall/NetworkPolicy và xác thực theo kiến trúc triển khai.

### 6.1. Xác minh Prometheus target

Mở trang Targets của Prometheus và kiểm tra:

- Job `shop-modulith` đã được phát hiện.
- Target có trạng thái `UP`.
- Last scrape và scrape duration hợp lý.
- Không có lỗi HTTP, timeout hoặc parse exposition format.

Sau đó chạy query:

~~~promql
module_events_published_total
~~~

Nếu query không trả series, kiểm tra lại metric name ở `/actuator/prometheus`. Đừng đổi tên meter trong code chỉ để khớp một PromQL giả định.

## 7. Thiết kế bố cục dashboard

Một dashboard có thể chia thành ba hàng:

| Vị trí | Panel | Cách hiển thị | Câu hỏi |
| --- | --- | --- | --- |
| Hàng 1 | Total publications | Stat | Có bao nhiêu event trong khoảng đang chọn? |
| Hàng 1 | Publication rate | Stat hoặc Time series | Hiện tại có bao nhiêu event/giây? |
| Hàng 2 | Rate by module | Time series hoặc stacked area | Module nào đang phát event? |
| Hàng 2 | Event type distribution | Bar hoặc pie | Loại event nào phổ biến? |
| Hàng 3 | Top event types | Bar chart | Top 10 event type theo số lượng? |
| Hàng 3 | Publication trend | Time series | Có tăng/giảm bất thường theo thời gian? |

Ví dụ dữ liệu giả lập cho biểu đồ rate theo module:

| Module | Event/s |
| --- | ---: |
| `orders` | 2.8 |
| `payments` | 1.4 |
| `inventory` | 2.1 |

Dữ liệu trên chỉ minh họa cách đọc biểu đồ; dashboard thật phải truy vấn Prometheus. Với event type, nên dùng bar chart khi có nhiều loại; pie chart chỉ phù hợp khi số nhóm ít và cần xem tỷ trọng.

## 8. PromQL cho các panel

Các ví dụ sau giả định Prometheus scrape counter tổng hợp dưới tên `module_events_published_total` với labels `module_identifier`, `module_name`, `module_event_type`. Nếu exposition thực tế khác, thay bằng tên và labels đã xác minh.

### 8.1. Stat: tổng số event trong khoảng thời gian

~~~promql
sum(increase(module_events_published_total[$__range]))
~~~

- `increase()` ước lượng số lần counter tăng trong range được chọn.
- `sum()` cộng qua module, event type và instance.
- Grafana `$__range` thay bằng khoảng thời gian đang chọn trên dashboard.

Panel nên đặt unit là `events` hoặc `short`, không đặt unit là events/second vì đây là tổng tăng trong range.

### 8.2. Time series: publication rate toàn ứng dụng

~~~promql
sum(rate(module_events_published_total[$__rate_interval]))
~~~

`rate()` tính tốc độ trung bình mỗi giây từ counter trong cửa sổ. Dùng `$__rate_interval` để Grafana chọn khoảng rate phù hợp với scrape interval và thời gian hiển thị.

Panel unit: `events/sec`.

### 8.3. Time series: publication rate theo module

~~~promql
sum by (module_identifier) (
  rate(module_events_published_total[$__rate_interval])
)
~~~

Query này tính rate cho từng series trước, sau đó cộng theo module. Không cộng counter thô trước rồi mới tính rate khi muốn xử lý counter reset trên từng instance.

Nếu muốn hiển thị tên thân thiện, có thể dùng label `module_name` nếu output Prometheus thực tế có label đó:

~~~promql
sum by (module_name) (
  rate(module_events_published_total[$__rate_interval])
)
~~~

### 8.4. Time series: theo module và event type

~~~promql
sum by (module_identifier, module_event_type) (
  rate(module_events_published_total[$__rate_interval])
)
~~~

Dùng panel dạng multi-series hoặc stacked area. Nếu có quá nhiều event type, dùng dashboard variable hoặc chỉ hiển thị Top N để giữ biểu đồ dễ đọc.

### 8.5. Top 10 event type được công bố nhiều nhất

~~~promql
topk(
  10,
  sum by (module_event_type) (
    increase(module_events_published_total[$__range])
  )
)
~~~

Panel dạng bar chart phù hợp để so sánh lượng event trong khoảng thời gian. Đây là Top 10 theo số lượng publication, không phải theo độ trễ hoặc tỷ lệ lỗi listener.

### 8.6. Tỷ trọng publication theo module

~~~promql
100 *
sum by (module_identifier) (
  increase(module_events_published_total[$__range])
)
/
scalar(sum(increase(module_events_published_total[$__range])))
~~~

Kết quả là tỷ trọng phần trăm của mỗi module trên tổng publication trong range, nếu tổng khác 0. Panel unit là percent (0–100). Khi không có publication trong range, biểu thức có thể không có giá trị; cấu hình Grafana hiển thị `No data` thay vì diễn giải thành 0% một cách gây hiểu nhầm.

## 9. Tạo dashboard và variables trong Grafana

### 9.1. Tạo dashboard

1. Mở Grafana và thêm Prometheus làm data source.
2. Chọn **New dashboard**.
3. Tạo các panel theo truy vấn ở phần trước.
4. Đặt dashboard time range mặc định phù hợp, ví dụ `Last 6 hours`.
5. Đặt refresh interval vừa phải, ví dụ `30s` hoặc `1m`.
6. Ghi rõ unit, legend và mô tả mỗi panel.
7. Lưu dashboard với tên `Spring Modulith — Domain Event Publications`.

### 9.2. Tạo variable chọn module

Tạo dashboard variable:

| Trường | Giá trị |
| --- | --- |
| Name | `module` |
| Type | Query |
| Data source | Prometheus |
| Query | `label_values(module_events_published_total, module_identifier)` |
| Multi-value | Bật nếu muốn chọn nhiều module |
| Include All | Bật nếu dashboard cần xem toàn ứng dụng |

Sử dụng variable trong query:

~~~promql
sum by (module_identifier) (
  rate(module_events_published_total{module_identifier=~"$module"}[$__rate_interval])
)
~~~

### 9.3. Tạo variable chọn event type

| Trường | Giá trị |
| --- | --- |
| Name | `event_type` |
| Type | Query |
| Query | `label_values(module_events_published_total, module_event_type)` |

Lọc trong PromQL:

~~~promql
sum by (module_event_type) (
  increase(module_events_published_total{module_identifier=~"$module", module_event_type=~"$event_type"}[$__range])
)
~~~

Tên label `module_identifier` và `module_event_type` là cách chuẩn hóa thường gặp. Nếu output `/actuator/prometheus` của phiên bản hiện tại khác, sửa variable/query theo label thực tế.

### 9.4. Chọn legend

Để legend ngắn, dùng:

- `{{module_identifier}}` cho panel theo module.
- `{{module_identifier}} / {{module_event_type}}` cho panel theo module và event.
- `{{module_name}}` nếu muốn tên hiển thị và label có sẵn.

Không đưa payload, order ID hoặc publication ID vào legend; dashboard nên tổng hợp theo nhóm hữu hạn.

## 10. Counter, rate và increase

Counter của Micrometer là giá trị tích lũy, thường tăng theo mỗi event publication và được reset khi tiến trình tạo meter khởi động lại.

| Hàm PromQL | Ý nghĩa | Dùng trong dashboard |
| --- | --- | --- |
| Counter trực tiếp | Giá trị tích lũy từ lần khởi tạo/reset | Ít hữu ích để so sánh tốc độ giữa các instance |
| `rate(counter[5m])` | Tốc độ tăng trung bình mỗi giây trong cửa sổ 5 phút | Time series event/s |
| `increase(counter[1h])` | Mức tăng ước lượng trong một giờ | Tổng event trong khoảng |
| `irate(counter[5m])` | Tốc độ tức thời dựa trên hai sample gần nhất | Debug biến động ngắn; dễ nhiễu |

### 10.1. Vì sao dùng rate trước khi sum?

Với nhiều replica, mỗi replica có counter riêng. Khi một replica restart, counter của nó quay về giá trị ban đầu. Prometheus `rate()` nhận biết counter reset trên từng series.

Nên viết:

~~~promql
sum by (module_identifier) (
  rate(module_events_published_total[5m])
)
~~~

Quy tắc thực hành là **rate từng counter series rồi mới aggregate** để xử lý counter reset trên từng instance.

### 10.2. Scrape interval ảnh hưởng biểu đồ

Nếu Prometheus scrape mỗi 15 giây, một cửa sổ rate quá ngắn có thể không đủ sample, đặc biệt khi dashboard refresh liên tục hoặc scrape bị trễ. Dùng `$__rate_interval` trong Grafana thường an toàn hơn hard-code `[15s]`.

Nếu event rất ít, rate có thể bằng 0 trong phần lớn thời gian dù hệ thống hoạt động đúng. Với event hiếm, panel `increase()` theo khoảng 1 giờ hoặc 24 giờ có thể dễ đọc hơn.

### 10.3. Counter reset và restart

Counter reset sau restart là hành vi bình thường. Dùng `rate()`/`increase()` để Prometheus điều chỉnh reset. Nếu dashboard hiển thị giá trị giảm đột ngột, đừng mặc định đó là event publication âm; kiểm tra instance restart và raw series.

## 11. Nhiều instance và cách tổng hợp

Khi service chạy nhiều replica, Prometheus tạo một series cho mỗi tổ hợp labels, trong đó thường có thêm `instance`, `job`, `pod` hoặc labels do service discovery thêm vào.

Ví dụ:

~~~text
module_events_published_total{
  job="shop-modulith",
  instance="10.0.0.11:8080",
  module_identifier="orders",
  module_event_type="OrderPlaced"
} 120

module_events_published_total{
  job="shop-modulith",
  instance="10.0.0.12:8080",
  module_identifier="orders",
  module_event_type="OrderPlaced"
} 85
~~~

Dashboard toàn service nên tổng hợp qua instance:

~~~promql
sum by (module_identifier, module_event_type) (
  rate(module_events_published_total[$__rate_interval])
)
~~~

Dashboard từng replica có thể giữ `instance` trong group:

~~~promql
sum by (instance, module_identifier) (
  rate(module_events_published_total[$__rate_interval])
)
~~~

Panel theo instance hữu ích để phát hiện một replica không phát event trong khi các replica khác vẫn hoạt động. Nhưng một instance không có publication chưa chắc lỗi; traffic có thể không được route tới nó hoặc event chỉ được phát ở một số node.

Nếu Prometheus HA hoặc Thanos/Mimir có cơ chế replica labels, dùng cấu hình deduplication tương ứng để tránh đếm hai lần cùng một scrape stream. Không xóa `instance` bằng relabeling nếu vẫn cần phân biệt nguồn scrape.

## 12. Dashboard và cảnh báo vận hành

Dashboard cho người vận hành nhìn xu hướng; alert cần có **điều kiện và kỳ vọng nghiệp vụ rõ ràng**.

### 12.1. Cảnh báo publication tăng đột biến

Ví dụ cảnh báo khi publication rate của một module vượt ngưỡng:

~~~promql
sum by (module_identifier) (
  rate(module_events_published_total[5m])
) > 100
~~~

Ngưỡng `100 events/s` chỉ là ví dụ. Hãy chọn ngưỡng theo baseline, tải dự kiến và module cụ thể. Tăng publication có thể là traffic tăng bình thường, batch chạy hoặc event loop; cần đối chiếu với business metrics và logs.

### 12.2. Cảnh báo module ngừng phát event

Không nên cảnh báo chỉ vì một counter đứng yên: module có thể không có event trong khoảng đó. Nếu nghiệp vụ yêu cầu module phải phát event liên tục, có thể dùng:

~~~promql
sum by (module_identifier) (
  increase(module_events_published_total{module_identifier="orders"}[15m])
) == 0
~~~

Chỉ áp dụng khi có một kỳ vọng vận hành rằng `orders` phải phát event trong mọi cửa sổ 15 phút. Nếu không, alert sẽ báo giả khi hệ thống nhàn rỗi. Có thể kết hợp với traffic/request counter để chỉ cảnh báo khi có đơn hàng được xử lý nhưng event không được publish.

### 12.3. Đừng tạo alert lỗi listener từ publication counter

`module.events.published` đếm **publication**, không phải listener success/failure. Không viết alert “listener failure rate” từ counter này. Muốn theo dõi listener completion cần:

- Event Publication Registry để kiểm tra publication status và retry.
- Metrics processing riêng có tag `module`, `listener`, `outcome` với tập giá trị hữu hạn.
- Logs/traces để điều tra một lần xử lý cụ thể.

## 13. Bổ sung tag nghiệp vụ có kiểm soát

Spring Modulith cho phép tùy biến individual event counters bằng `ModulithEventMetricsCustomizer`. Ví dụ event có channel là enum hữu hạn:

~~~java
package com.example.shop.orders;

public enum OrderChannel {
    WEB, MOBILE, PARTNER
}
~~~

Event:

~~~java
package com.example.shop.orders;

import java.util.UUID;

public record OrderPlaced(UUID orderId, OrderChannel channel) {}
~~~

Customizer:

~~~java
package com.example.shop.config;

import com.example.shop.orders.OrderPlaced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.modulith.observability.ModulithEventMetricsCustomizer;

@Configuration
class EventMetricsConfiguration {

    @Bean
    ModulithEventMetricsCustomizer eventMetricsCustomizer() {
        return metrics -> metrics.customize(OrderPlaced.class, (event, builder) -> {
            builder.tags("order.channel", event.channel().name());
        });
    }
}
~~~

Customizer thêm `order.channel` vào **counter riêng cho `OrderPlaced`**. Nó không có nghĩa tag đó tự xuất hiện trên mọi metric hoặc counter tổng hợp. Nếu viết customizer trong source code, thêm `spring-modulith-observability-api` ở compile scope theo tài liệu Spring Modulith.

### 13.1. Chọn tag low-cardinality

Tag phù hợp:

- `order.channel=WEB|MOBILE|PARTNER`
- `payment.method=CARD|BANK_TRANSFER`
- `outcome=SUCCESS|FAILED` nếu metric thực sự đo outcome
- `region=NORTH|CENTRAL|SOUTH` nếu danh sách được kiểm soát

Tránh:

- `order.id` (UUID riêng cho từng đơn).
- `customer.email`.
- `trace.id`.
- Event payload hoặc exception message.
- Giá trị tự do từ HTTP request.

Mỗi tổ hợp tag tạo một time series. Một dashboard event có 10 module × 20 event types × 4 channel values đã có thể tạo tới 800 tổ hợp trước khi tính instance và metric families.

### 13.2. Không thay event type bằng payload

Event type là tên class/loại event, tập giá trị hữu hạn trong code. Payload là dữ liệu của từng lần phát event, có thể chứa ID hoặc thông tin cá nhân. Dashboard nên phân nhóm theo **type**, không theo nội dung payload.

## 14. Publication count không phải listener completion

Đây là phân biệt quan trọng nhất khi đọc dashboard:

~~~mermaid
flowchart LR
    A["Module phát domain event"] --> B["module.events.published<br/>Counter tăng"]
    A --> C["Event Publication Registry<br/>ghi publication cho listener"]
    C --> D["Listener thực thi"]
    D --> E["COMPLETED"]
    D --> F["FAILED / retry"]
~~~

Counter publication tăng khi event được publish theo instrumentation. Event Publication Registry theo dõi trạng thái xử lý của publication tới transactional listener theo cơ chế riêng.

| Tín hiệu | Trả lời câu hỏi |
| --- | --- |
| `module.events.published` | Có bao nhiêu lần event publication được ghi nhận? |
| Module entry span | Lần thực thi được sample đã đi vào module nào? |
| Event Publication Registry | Publication/listener đang chờ, xử lý, hoàn tất hay thất bại? |
| Custom listener metrics | Listener có bao nhiêu attempt, success/failure và duration? |
| Logs | Vì sao một lần xử lý cụ thể thất bại? |

Một event có thể được publish và counter tăng, nhưng listener vẫn thất bại. Ngược lại, một event có thể được xử lý bởi nhiều listener; publication count không bằng số listener invocation.

Không suy ra `COMPLETED` bằng cách lấy số publication trừ số lỗi nếu không có metrics đầy đủ và cùng định nghĩa/mẫu số.

## 15. Kiểm tra dashboard khi dữ liệu không đúng

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Không thấy `module.events.published` ở Actuator | Thiếu Modulith observability support hoặc chưa có event được theo dõi | Kiểm tra Insight starter và phát một event cross-module |
| Actuator có metric nhưng Prometheus không có | Registry thiếu, endpoint không expose hoặc scrape lỗi | Kiểm tra dependency, `/actuator/prometheus` và Prometheus Targets |
| Metric name khác query | Naming convention đổi dấu chấm/suffix | Dùng exposition output làm nguồn chuẩn |
| Query không thấy label event type | Dùng counter riêng thay counter tổng hợp hoặc label name khác | Kiểm tra meter và labels thực tế |
| Counter đứng yên | Không có event publication mới, instrumentation không hoạt động hoặc scrape cũ | Gọi luồng nghiệp vụ phát event, kiểm tra last scrape |
| Rate bằng 0 trong khoảng ngắn | Event ít hoặc cửa sổ rate không đủ sample | Tăng range, dùng `increase()` theo khoảng dài hơn |
| Tổng dashboard gấp đôi | Cộng cả aggregate và per-event counters hoặc scrape trùng | Chỉ dùng một loại counter; kiểm tra HA/dedup |
| Tổng theo module không khớp kỳ vọng | Label filter sai, replica thiếu scrape hoặc event được phát từ module khác | Kiểm tra `availableTags`, instance và event ownership |
| Publication tăng nhưng listener lỗi | Counter chỉ đo publication | Kiểm tra Event Publication Registry và listener logs |
| Grafana variable trống | Label chưa có series hoặc dùng sai label key | Chạy metric không lọc, xem `label_values` và scrape output |

### 15.1. Checklist chẩn đoán

1. Event đã thực sự được publish chưa?
2. Spring Modulith observability instrumentation có trong runtime classpath không?
3. `/actuator/metrics/module.events.published` có meter không?
4. `availableTags` có module/event type như mong đợi không?
5. `/actuator/prometheus` xuất metric name và label names nào?
6. Prometheus target có trạng thái `UP` không?
7. Query có dùng đúng metric name và label keys không?
8. Grafana time range và refresh interval có phù hợp không?
9. Có cộng trùng aggregate counter và individual counter không?
10. Nếu cần biết listener outcome, đã kiểm tra Event Publication Registry chưa?

## 16. Bài thực hành

### Bài 1 — Khởi tạo publication metrics

Thêm `spring-modulith-starter-insight` và Prometheus registry. Expose `metrics` và `prometheus`. Phát các event `OrderPlaced`, `OrderCancelled` và `StockReserved`. Xác nhận counter tổng hợp xuất hiện ở Actuator.

### Bài 2 — Phân biệt hai counter

Đọc meter `module.events.published` và một meter riêng theo event type. Giải thích vì sao không cộng cả hai vào cùng một Stat panel.

### Bài 3 — Tạo panel theo module

Dùng PromQL:

~~~promql
sum by (module_identifier) (
  rate(module_events_published_total[5m])
)
~~~

Tạo time series panel với unit events/sec. Nếu label thực tế khác, chỉnh query dựa trên scrape output.

### Bài 4 — Tạo panel Top event types

Dùng `topk(10, sum by (module_event_type) (increase(...)))`. Chọn khoảng 1 giờ và giải thích event type nào đang chiếm nhiều publication nhất.

### Bài 5 — Thêm dashboard variables

Tạo variable `$module` và `$event_type`. Cho phép chọn một hoặc nhiều module; xác minh panel cập nhật đúng khi đổi selection.

### Bài 6 — Thử nhiều replica

Chạy hai instance của ứng dụng hoặc dùng dữ liệu test có label `instance` khác nhau. Xác minh `sum by (module_identifier)` tổng hợp cả hai, còn panel có `instance` tách được từng replica.

### Bài 7 — Phân biệt publication và completion

Làm một listener cố ý thất bại trong môi trường test. Quan sát publication counter vẫn ghi nhận event đã phát; kiểm tra registry để thấy trạng thái xử lý. Giải thích vì sao dashboard publication không thể thay dashboard listener outcome.

## 17. Câu hỏi ôn tập

1. Spring Modulith cung cấp hai dạng counter publication nào?
2. Ba low-cardinality keys của `module.events.published` là gì?
3. Individual event counter có thể được tùy biến bằng API nào?
4. Vì sao dashboard linh hoạt thường ưu tiên counter tổng hợp?
5. Vì sao không cộng counter tổng hợp với các counter riêng?
6. `/actuator/metrics` khác `/actuator/prometheus` như thế nào?
7. Vì sao phải xác nhận tên label sau Prometheus naming convention?
8. `rate()` và `increase()` khác nhau thế nào?
9. Vì sao cần tính `rate()` trước khi `sum()` trên nhiều instance?
10. `module.events.published` có đo listener success không?
11. Làm thế nào phát hiện module ngừng publish mà không alert giả khi traffic bằng 0?
12. Vì sao không đưa `order.id` hoặc `trace.id` vào metric tags?
13. Khi dashboard không có data, nên kiểm tra theo thứ tự nào?
14. Sampling tracing có làm giảm publication counter không?

## 18. Ghi nhớ

**Dashboard số lần công bố domain event nên dùng counter tổng hợp `module.events.published` làm nguồn chính.** Counter này có thể được phân nhóm theo `module.identifier`, `module.name` và `module.event.type`, từ đó tạo panel tổng, rate theo module, phân bố event type và Top N.

Micrometer counter là số tích lũy; dùng `rate()` cho events/second và `increase()` cho tổng trong khoảng thời gian. Khi có nhiều replica, tính rate trên từng series rồi mới aggregate. Xác minh tên metric và labels qua `/actuator/prometheus` trước khi viết PromQL, vì naming convention có thể chuẩn hóa dấu chấm và suffix.

Cuối cùng, **publication không đồng nghĩa listener completion**. Dùng Event Publication Registry để kiểm tra trạng thái xử lý, tracing để lần theo tương tác được sample và module Actuator để xem cấu trúc module. Giữ tags hữu hạn để dashboard vận hành ổn định khi lưu lượng tăng.

### Tài liệu tham khảo chính thức

- [Spring Modulith 2.2 — Production-ready Features: Observability Metrics và Low Cardinality Keys](https://docs.spring.io/spring-modulith/reference/2.2/production-ready.html).
- [Spring Modulith — ModulithEventMetricsCustomizer JavaDoc](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithEventMetricsCustomizer.html).
- [Spring Modulith — Working with Application Events và Event Publication Registry](https://docs.spring.io/spring-modulith/reference/events.html).
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html).
- [Micrometer — Prometheus registry](https://docs.micrometer.io/micrometer/reference/implementations/prometheus.html).
- [Prometheus — Querying basics và rate/increase functions](https://prometheus.io/docs/prometheus/latest/querying/basics/).
- [Grafana — Prometheus data source](https://grafana.com/docs/grafana/latest/datasources/prometheus/).
