# Document metric name và tag chính
## 1. Mục tiêu

Một ứng dụng Spring Boot theo modular monolith có thể có các application module như `orders`, `inventory` và `payments`. Mỗi module phát event, xử lý request hoặc thực hiện tác vụ nền. Micrometer và Spring Modulith ghi nhận những hoạt động này thành metrics. Khi số lượng meter tăng, nhóm vận hành cần biết mỗi metric đo điều gì, được tạo ở đâu và có thể phân tích theo những chiều nào.

**Document metric name và tag chính** là ghi lại hợp đồng của metric: tên, ý nghĩa, loại dữ liệu, đơn vị, nguồn tạo, các chiều phân loại quan trọng, giới hạn cardinality và cách sử dụng. Hợp đồng này giúp developer, platform engineer và người trực vận hành hiểu cùng một cách về dữ liệu giám sát.

Bài học thuộc chương **Tài liệu vận hành** của học phần **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Học phần dùng Spring Modulith để sinh tài liệu ranh giới application module và quan sát tương tác giữa các phần trong ứng dụng Spring Boot qua module graph, Actuator, event metrics, tracing và context propagation.

Sau bài này, bạn có thể:

1. Viết metric name có ý nghĩa và ổn định.
2. Phân biệt metric name, meter type, unit, tag key, tag value và scrape label.
3. Xác định primary tags cho metric của module và event.
4. Đọc hai họ event publication counters của Spring Modulith.
5. Tạo metric catalog và quản lý thay đổi schema.
6. Phân biệt tên Micrometer với tên đã chuẩn hóa trong Prometheus.
7. Đánh giá cardinality trước khi thêm tag mới.
8. Dùng Actuator xác minh meter name và tag values thực tế.

> **Phạm vi:** Ví dụ dùng Spring Modulith 2.2, Spring Boot 4.2, Micrometer và Prometheus. Tên metric trong backend có thể thay đổi theo registry/naming convention; hãy xác minh scrape output của ứng dụng.

## 2. Metric contract gồm những gì?

### 2.1. Metric name và ý nghĩa

Metric name là định danh của một meter. Tên tốt giúp người đọc hiểu đại lượng ngay cả khi chưa nhìn thấy tags.

| Tên metric | Có thể hiểu được gì? | Nhận xét |
| --- | --- | --- |
| `orders.created` | Số đơn hàng được tạo | Cần mô tả chính xác thời điểm tăng |
| `http.server.requests` | Các request HTTP phía server | Tên phổ biến trong Spring Boot |
| `payment.failure.count` | Số lần thất bại | Hậu tố `.count` có thể không cần thiết nếu meter đã là Counter |
| `value` | Không rõ đại lượng | Tên quá chung |
| `orders.processing.duration` | Thời lượng xử lý đơn hàng | Cần ghi unit và meter type |

Tên metric không thay thế phần mô tả. Ví dụ `orders.created` có thể tăng khi entity được lưu, khi transaction commit hoặc khi domain event được publish. Ba thời điểm này có ý nghĩa nghiệp vụ khác nhau. Catalog phải ghi rõ điểm đo.

### 2.2. Meter type và unit

| Type | Dùng để đo | Cách đọc |
| --- | --- | --- |
| Counter | Số lần một việc xảy ra | Giá trị tích lũy, thường chỉ tăng |
| Gauge | Giá trị hiện tại tại một thời điểm | Có thể tăng hoặc giảm |
| Timer | Số lần thực hiện và phân phối thời lượng | Count, total time, histogram/percentile tùy registry |
| DistributionSummary | Phân phối của giá trị không phải thời lượng | Count, total amount và phân phối |
| LongTaskTimer | Thời lượng của tác vụ còn đang chạy | Theo dõi tác vụ dài chưa kết thúc |

Counter không phải Gauge. Không nên tạo Counter để biểu diễn số đơn đang chờ vì giá trị đó có thể giảm khi xử lý xong. Trường hợp đó cần Gauge hoặc phép đo trạng thái hiện tại.

Unit cho biết giá trị đo theo đơn vị nào: seconds, bytes, ratio, publications hoặc connections. Với Prometheus, nên dùng base units như seconds và bytes. Không trộn milliseconds với seconds trong cùng một metric.
### 2.3. Tag key và tag value

Tag là cặp key-value bổ sung ngữ cảnh cho cùng một metric:

```text
orders.created{
  module.identifier="orders",
  channel="web",
  environment="staging"
}
```

- Metric name `orders.created` nói rằng đang đo số đơn được tạo.
- `module.identifier=orders` cho biết module liên quan.
- `channel=web` cho biết kênh bán hàng.
- `environment=staging` cho biết môi trường.

Metric name là đại lượng; tags là các chiều phân tích đại lượng đó. Khi muốn so sánh kênh bán hàng, group theo `channel`. Khi muốn lọc môi trường, chọn `environment`.

### 2.4. Primary tags và common tags

**Primary tags** là những tag key mà dashboard, alert và truy vấn thường dùng để phân nhóm hoặc lọc một metric. Ví dụ với event publication:

- `module.event.type`: loại event được công bố.
- `module.identifier`: technical identifier của module phát event.
- `module.name`: tên hiển thị của module.

**Common tags** được gắn vào tất cả meters để mô tả môi trường vận hành. Ví dụ:

```yaml
management:
  metrics:
    tags:
      application: shop-service
      environment: staging
      region: ap-southeast-1
```

Chỉ chọn common tags thật sự có ý nghĩa chung. Không thêm `module.identifier` như common tag nếu một meter trong cùng registry có thể đại diện cho nhiều module và đã mang module tag riêng.

### 2.5. Meter tags khác scrape target labels

Prometheus có thể thêm labels như `job` và `instance` khi scrape target. Đây không nhất thiết là tag được tạo trong Micrometer.

```text
module_events_published_total{
  module_event_type="OrderPlaced",
  module_identifier="orders",
  module_name="Orders",
  job="shop-service",
  instance="10.0.2.14:8080"
}
```

Trong catalog, ghi rõ nguồn:

- `module_event_type`, `module_identifier`, `module_name`: tags từ meter.
- `job`, `instance`: labels do cấu hình scrape/service discovery thêm.

Nếu đã có `environment` trong scrape target labels, tránh thêm một common tag trùng tên nhưng khác nguồn và khác giá trị.

### 2.6. Trường của metric catalog

| Trường | Nội dung cần ghi |
| --- | --- |
| Metric name | Tên meter gốc trong Micrometer |
| Backend name | Tên sau khi registry chuẩn hóa, nếu có |
| Description | Metric đo điều gì và tăng/đổi khi nào |
| Type / Unit | Counter, Gauge, Timer... và đơn vị |
| Source | Spring Boot, Spring Modulith hay code ứng dụng |
| Owner | Team/module chịu trách nhiệm |
| Primary tags | Tag key quan trọng, ý nghĩa và tập giá trị |
| Other labels | Common tags và labels do scrape target thêm |
| Cardinality | Giá trị dự kiến và rủi ro tăng |
| Dashboard / Alert | Panel, query và điều kiện cảnh báo |
| Lifecycle | Thời điểm ghi nhận và hành vi khi restart |
| Change policy | Quy tắc khi đổi tên, tag hoặc semantics |
## 3. Quy tắc đặt metric name và tag

### 3.1. Dùng convention thống nhất

Micrometer khuyến nghị tên meter theo lowercase dot notation:

```java
registry.counter("orders.created");
registry.timer("orders.processing");
registry.gauge("inventory.items.available", inventory, Inventory::availableItems);
```

Các từ được phân tách bằng dấu chấm. Naming convention của registry chuyển tên này sang định dạng phù hợp với backend.

| Backend | Tên minh họa |
| --- | --- |
| Micrometer | `http.server.requests` |
| Prometheus | `http_server_requests_duration_seconds` |
| Graphite | `http.server.requests` |

Không nên ghi duy nhất tên Prometheus trong catalog nếu code tạo meter bằng Micrometer name khác. Lưu cả tên gốc và tên backend khi cần hỗ trợ nhiều registry.

### 3.2. Một metric đo một đại lượng

Không trộn các đại lượng không cùng bản chất vào một meter:

```java
// Không nên: metric không rõ đang đếm hoạt động nào.
registry.counter("shop.activity");

// Nên: từng meter có một ý nghĩa rõ.
registry.counter("orders.created");
registry.counter("payments.authorized");
registry.counter("database.calls");
```

Khi các phép đo cùng một đại lượng chỉ khác chiều phân loại, dùng một metric với tags. Ví dụ counter `http.responses` có tag `status` thay vì tạo nhiều tên `http.responses.200` và `http.responses.500` theo cách thủ công.

### 3.3. Không nhúng tag value động vào tên

Không tạo tên mới cho mỗi order hoặc event instance:

```java
// Không nên: tên meter thay đổi theo từng đơn hàng.
registry.counter("orders." + orderId + ".created");

// Nên: meter ổn định, tag có tập giá trị hữu hạn.
registry.counter("orders.created", "channel", channel.name());
```

Spring Modulith có một trường hợp framework-defined riêng: counter theo từng event có tên chứa module identifier và simple event type name. Đây là convention của thư viện; không dùng nó làm lý do để tự tạo metric names từ giá trị runtime tùy ý.

### 3.4. Unit và suffix theo convention backend

Prometheus khuyến nghị tên metric thể hiện base unit và loại counter khi phù hợp:

- Thời lượng: hậu tố `_seconds`.
- Dung lượng: hậu tố `_bytes`.
- Counter tích lũy: hậu tố `_total`.

Micrometer giữ meter name ở dạng dot notation rồi registry chuyển sang naming convention của backend. Ví dụ Counter `module.events.published` có thể được Prometheus exporter biểu diễn thành `module_events_published_total`. Hãy xem scrape output thật trước khi ghi tên backend vào tài liệu.

### 3.5. Cardinality phải có giới hạn

Mỗi tổ hợp duy nhất của metric name và tag key-value tạo một time series riêng. Nếu metric có 8 modules, 12 event types, 3 environments, 4 regions và 6 instances, số tổ hợp tối đa là:

```text
8 × 12 × 3 × 4 × 6 = 6,912 time series
```

Không đưa những giá trị gần như duy nhất cho từng request/event vào metric tags:

- `user.id`, `customer.id`, `order.id`.
- `request.id`, `trace.id`, `span.id`.
- Email, số điện thoại, session ID.
- Timestamp chính xác.
- Raw URL có path variable như `/orders/12345`.
- Exception message, event UUID hoặc idempotency key.

Với HTTP URI, dùng route template `/orders/{id}` thay vì URL thực tế `/orders/12345`. Với exception, dùng class hoặc nhóm lỗi ổn định thay vì message chứa dữ liệu động.

Cardinality phụ thuộc tổ hợp tags, không chỉ từng tag riêng lẻ. Hãy ước tính số series trước khi thêm chiều mới. Dùng logs/traces để tìm từng giao dịch; dùng metrics để phân tích số lượng, tốc độ và xu hướng.
## 4. Metric catalog của Spring Modulith

### 4.1. Hai họ event publication metrics

Spring Modulith 2.2 cung cấp hai metric counters cho domain events được công bố:

| Metric name trong Micrometer | Ý nghĩa | Primary tags |
| --- | --- | --- |
| `module.events.published` | Counter tổng hợp tất cả event publications | `module.event.type`, `module.identifier`, `module.name` |
| `module.events.published.<moduleIdentifier>.<simpleEventTypeName>` | Counter riêng cho một event type trong module | `module.identifier`, `module.name` |

Metric tổng hợp phù hợp cho dashboard cần phân nhóm theo event type. Event type được thể hiện bằng tag `module.event.type`.

Metric riêng cho từng event type đưa module identifier và simple event type name vào **metric name**. Nó có thể được bổ sung tags domain-specific bằng `ModulithEventMetricsCustomizer`.

### 4.2. Ý nghĩa primary tags

| Tag key | Ý nghĩa | Ví dụ | Cách dùng |
| --- | --- | --- | --- |
| `module.event.type` | Type của event được phát | `OrderPlaced` | Group/filter theo event type trên metric tổng hợp |
| `module.identifier` | Technical identifier của module | `orders` | Lọc hoặc group theo module |
| `module.name` | Tên hiển thị của module | `Orders` | Hiển thị tên dễ đọc trong dashboard |

`module.identifier` thường là lựa chọn ổn định cho truy vấn kỹ thuật. `module.name` hữu ích cho người đọc dashboard. Nếu tên hiển thị thay đổi, hãy kiểm tra dashboard có dùng nó làm label selector hay không.

### 4.3. Metric tổng hợp và metric riêng không có cùng bộ tags

Metric tổng hợp có tag `module.event.type`. Metric riêng có event type nằm trong meter name và tags mặc định chỉ gồm `module.identifier` và `module.name`.

Không viết catalog rằng metric riêng có sẵn tag `module.event.type` nếu ứng dụng chưa tự thêm tag đó. Đây là khác biệt quan trọng khi tạo Grafana variables hoặc PromQL groupings.

### 4.4. Không cộng hai họ metric để tính tổng

Một event publication có thể được phản ánh trong counter tổng hợp và counter riêng tương ứng. Nếu cộng cả hai họ, dashboard có thể đếm trùng.

Chọn một metric family làm nguồn cho từng phép đo:

- Dashboard tổng event theo type: dùng `module.events.published`.
- Drill-down counter riêng theo một event/module: dùng meter riêng.
- Không cộng hai nguồn thành một “total publications” duy nhất.

### 4.5. Publication không phải listener completion

Metric `module.events.published` đếm event publications. Nó không chứng minh listener đã chạy thành công hoặc transaction đã commit.

Nếu cần ghi nhận listener completion/failure, dùng Event Publication Registry hoặc metric nghiệp vụ khác có semantics riêng. Tài liệu metric phải ghi rõ metric đo ở thời điểm publish hay ở thời điểm xử lý hoàn tất.

### 4.6. Ví dụ metric catalog

| Trường | Metric tổng hợp |
| --- | --- |
| Metric name | `module.events.published` |
| Backend name | Ví dụ `module_events_published_total`, xác minh theo registry |
| Type | Counter |
| Unit | Publications (count) |
| Description | Tổng số lần domain events được công bố trong ứng dụng |
| Source | Spring Modulith observability |
| Primary tags | `module.event.type`, `module.identifier`, `module.name` |
| Cardinality | Bị giới hạn bởi tập module và event types đã định nghĩa |
| Aggregation | Sum; rate/increase theo thời gian |
| Owner | Team sở hữu application module và observability |
| Semantic boundary | Publication count; không phải listener success |
## 5. Tùy chỉnh tags cho metric riêng của event

### 5.1. Khi nào cần custom tag?

Một event có thể mang thuộc tính domain hữu ích để phân tích, ví dụ channel `web`, `store` hoặc `partner`. Nếu tập giá trị nhỏ và có ý nghĩa vận hành, có thể bổ sung tag cho counter riêng theo event type.

Ví dụ:

```java
public enum SalesChannel {
    WEB,
    STORE,
    PARTNER
}

@Configuration(proxyBeanMethods = false)
class ModulithMetricsConfiguration {

    @Bean
    ModulithEventMetricsCustomizer eventMetricsCustomizer() {
        return metrics -> metrics.customize(
            OrderPlaced.class,
            (event, meter) -> meter.tags(
                "sales.channel",
                event.channel().name().toLowerCase()
            )
        );
    }
}
```

Đây là ví dụ dùng extension point của Spring Modulith. Dự án cần khai báo observability API dependency ở compile scope khi tự viết customizer, theo tài liệu phiên bản đang sử dụng.

### 5.2. Chọn tag có tập giá trị hữu hạn

`sales.channel` có ba giá trị đã định nghĩa: `web`, `store` và `partner`. Dashboard có thể group theo channel mà số series vẫn kiểm soát được.

Không thay bằng `orderNumber` hoặc `customerId`. Các giá trị này gần như duy nhất cho từng event và có thể tạo cardinality tăng theo số giao dịch.

### 5.3. Customizer áp dụng cho metric riêng

Spring Modulith cho phép bổ sung tags domain-specific vào **individual event metrics**. Không mặc định rằng custom tag được thêm vào metric tổng hợp `module.events.published`.

Nếu dashboard cần dimension đó trên metric tổng hợp, phải xác minh API/convention hỗ trợ trên version đang dùng và thiết kế riêng; đừng ghi tài liệu rằng mọi metric family đều tự có tag.

## 6. Khám phá metric trong Spring Boot

### 6.1. Dependency observability

Spring Modulith Insight starter cung cấp actuator và observability support:

```groovy
dependencies {
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

Dùng Spring Boot BOM và Spring Modulith BOM tương thích. Prometheus registry là thành phần riêng để xuất metrics sang Prometheus. Insight starter không thay thế mọi dependency kết nối monitoring backend.

### 6.2. Expose metrics endpoint

Ví dụ local/staging:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,metrics,prometheus,modulith"
```

- `/actuator/metrics`: khám phá meter names và drill-down theo tags.
- `/actuator/prometheus`: scrape format dành cho Prometheus.
- `/actuator/modulith`: thông tin cấu trúc module nếu actuator support được bật.

Endpoint metrics không được expose mặc định trong mọi cấu hình. Chỉ expose endpoint cần thiết và bảo vệ bằng network policy/Spring Security.

### 6.3. Liệt kê meter names

Gọi:

```bash
curl -s http://localhost:8080/actuator/metrics
curl -s http://localhost:8080/actuator/metrics/module.events.published
```

Response minh họa:

```json
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
      "tag": "module.event.type",
      "values": ["OrderPlaced", "StockReserved"]
    },
    {
      "tag": "module.identifier",
      "values": ["orders", "inventory"]
    },
    {
      "tag": "module.name",
      "values": ["Orders", "Inventory"]
    }
  ]
}
```

Đây là output minh họa. Các tag values chỉ xuất hiện khi meter tương ứng đã được đăng ký trong runtime.

### 6.4. Drill-down theo primary tags

Lọc theo event type:

```bash
curl -s "http://localhost:8080/actuator/metrics/module.events.published?tag=module.event.type:OrderPlaced"
```

Lọc theo event type và module:

```bash
curl -s "http://localhost:8080/actuator/metrics/module.events.published?tag=module.event.type:OrderPlaced&tag=module.identifier:orders"
```

Actuator selector dùng **meter name gốc trong code**. Không thay bằng tên Prometheus đã chuẩn hóa.

### 6.5. Kiểm tra Prometheus scrape output

Gọi:

```bash
curl -s http://localhost:8080/actuator/prometheus
```

Ví dụ output:

```text
# TYPE module_events_published_total counter
module_events_published_total{
  module_event_type="OrderPlaced",
  module_identifier="orders",
  module_name="Orders"
} 1250.0
```

Ví dụ trên giả định Prometheus naming convention thông dụng:

| Micrometer | Prometheus thường gặp |
| --- | --- |
| `module.events.published` | `module_events_published_total` |
| `module.event.type` | `module_event_type` |
| `module.identifier` | `module_identifier` |
| `module.name` | `module_name` |

Tên thực tế phụ thuộc registry/version. Dùng scrape output làm nguồn sự thật trước khi ghi backend name vào catalog hoặc viết PromQL.

### 6.6. Không nhầm tên meter với tên Prometheus

Spring Boot metrics endpoint yêu cầu meter name như trong code, ví dụ `module.events.published`. Prometheus có thể nhìn thấy tên đã chuyển thành snake_case và có hậu tố counter như `module_events_published_total`.

Catalog nên có cả hai trường nếu nhóm vận hành thường dùng cả Actuator và Prometheus:

- `micrometerName`: tên gốc để gọi `/actuator/metrics`.
- `prometheusName`: tên thực tế trong scrape output.
## 7. Tạo metric catalog cho ứng dụng

### 7.1. Mẫu bảng catalog

| Metric name | Type / Unit | Description | Primary tags | Owner |
| --- | --- | --- | --- | --- |
| `module.events.published` | Counter / publications | Số event được công bố | event type, module identifier, module name | Modulith/platform |
| `orders.created` | Counter / orders | Số đơn được tạo theo điểm đo đã định nghĩa | channel, outcome | Orders |
| `payments.authorization.duration` | Timer / seconds | Thời lượng authorize payment | provider, outcome | Payments |
| `inventory.items.available` | Gauge / items | Số lượng item hiện có tại thời điểm đọc | warehouse, category | Inventory |

Các metric ví dụ do ứng dụng tự định nghĩa cần được kiểm tra semantics và implementation trước khi đưa vào catalog thật.

### 7.2. Mẫu YAML cho một bản ghi tài liệu

Ví dụ nội dung một record trong tài liệu catalog nội bộ:

```yaml
metric:
  micrometerName: orders.created
  prometheusName: orders_created_total
  type: counter
  unit: orders
  description: >
    Số đơn hàng được ghi nhận sau khi use case tạo đơn
    hoàn tất thành công.
  source:
    kind: application
    module: orders
    owner: orders-team
  primaryTags:
    - key: sales.channel
      description: Kênh bán hàng
      values: [web, store, partner]
    - key: outcome
      description: Kết quả của use case
      values: [success]
  commonTags: [application, environment, region]
  cardinality:
    expectedSeriesPerInstance: bounded
    forbiddenValues: [orderId, customerId, requestId]
  usage:
    dashboard: Orders overview
    alert: Orders creation rate anomaly
  lifecycle:
    incrementWhen: Use case tạo đơn hoàn tất thành công
    reset: Process restart resets in-memory counter
  compatibility:
    changePolicy: Review dashboards and alerts before renaming
```

Đây là schema tài liệu minh họa, không phải cấu hình tự động được Spring Boot đọc. Nhóm có thể lưu catalog trong Markdown, YAML, wiki hoặc hệ thống docs hiện có; điều quan trọng là giữ đủ các trường cần thiết.

### 7.3. Mô tả semantics chính xác

Không viết description chung chung như “Số đơn hàng”. Viết rõ:

- Đơn được đếm khi nào?
- Đơn thất bại có được tính không?
- Retry có thể làm tăng counter nhiều lần không?
- Counter theo process hay được lưu bền vững?
- Khi restart, giá trị có reset không?
- Nếu nhiều instance, cách tổng hợp là gì?

Với event publication metric, description phải nói rõ đó là số lần **publish event**, không phải số listener thành công.

### 7.4. Ghi rõ owner và consumer

Metric có owner chịu trách nhiệm định nghĩa semantics và thay đổi schema. Consumer là dashboard, alert, autoscaler hoặc runbook đang dùng metric.

Nếu metric được framework tạo, ghi source là Spring Modulith/Spring Boot và chỉ định team chịu trách nhiệm vận hành tích hợp. Nếu metric do module tự tạo, module owner cần chịu trách nhiệm chính.

## 8. Dashboard, alert và thay đổi schema

### 8.1. Dashboard dùng đúng primary tags

Với metric tổng hợp Spring Modulith, dashboard có thể group theo event type:

```promql
sum by (module_event_type) (
  rate(module_events_published_total[5m])
)
```

Group theo module và event type:

```promql
sum by (module_identifier, module_event_type) (
  rate(module_events_published_total[5m])
)
```

Các query giả định scrape output có tên/labels như ví dụ. Nếu backend dùng tên khác, thay theo scrape output thực tế.

### 8.2. Counter phải được đọc theo delta/rate

Counter là giá trị tích lũy. Để xem số event trong một khoảng:

```promql
sum by (module_event_type) (
  increase(module_events_published_total[1h])
)
```

Để xem tốc độ tăng:

```promql
sum by (module_event_type) (
  rate(module_events_published_total[5m])
)
```

Không lấy counter thô làm tốc độ. Khi nhiều instance chạy song song, áp dụng rate/increase trên từng series trước rồi mới sum để xử lý counter reset.

### 8.3. Alert cần có ngữ nghĩa và kỳ vọng

Một alert dựa trên metric phải ghi rõ điều kiện, cửa sổ thời gian, event type/module, mức độ nghiêm trọng, cách xử lý No data, người nhận và hành động đề xuất.

Ví dụ cảnh báo event `OrderPlaced` không được công bố trong 15 phút chỉ hợp lý nếu nghiệp vụ kỳ vọng event đó phải xuất hiện trong mọi cửa sổ như vậy. Với event theo lịch, cần điều kiện lịch hoặc alert riêng.

### 8.4. Quản lý thay đổi metric schema

Đổi metric name có thể làm dashboard/alert trả No data. Trước khi đổi:

1. Tìm dashboard, alert, recording rule và runbook dùng tên cũ.
2. Xác định thời điểm chuyển đổi.
3. Cân nhắc publish metric mới song song trong giai đoạn tương thích.
4. Cập nhật consumer và xác minh trên staging.
5. Ghi ngày ngừng metric cũ vào catalog.
6. Chỉ xóa metric cũ khi consumer đã chuyển xong.

Đổi tag key cũng là thay đổi schema. Ví dụ `module` thành `module.identifier` sẽ làm query selector cũ không match. Hãy cập nhật catalog, dashboard variables, alert labels và docs cùng lúc.

Thay đổi semantics nhưng giữ nguyên tên cũng là breaking change. Dashboard vẫn có dữ liệu nhưng ý nghĩa đã đổi. Cập nhật description, catalog, dashboard/alert và cân nhắc metric name mới để không ghép hai giai đoạn dữ liệu khác nghĩa.
## 9. Kiểm tra chất lượng metric catalog

### 9.1. Checklist cho từng metric

- [ ] Metric name ổn định và có ý nghĩa.
- [ ] Description nói rõ thời điểm đo và semantics.
- [ ] Meter type đúng với đại lượng.
- [ ] Unit được ghi rõ và thống nhất.
- [ ] Primary tags có key/value convention nhất quán.
- [ ] Tag values có giới hạn và được chuẩn hóa.
- [ ] Không có ID duy nhất hoặc dữ liệu nhạy cảm trong tags.
- [ ] Common tags không trùng hoặc mâu thuẫn với primary tags.
- [ ] Owner và consumer được ghi rõ.
- [ ] Dashboard/alert queries được liệt kê.
- [ ] Backend name đã được xác minh bằng scrape output.
- [ ] Có change policy khi đổi name/tag/semantics.

### 9.2. Kiểm tra trực tiếp trong Actuator

1. Mở `/actuator/metrics`.
2. Xác nhận meter name gốc xuất hiện.
3. Mở meter cụ thể.
4. Đối chiếu `availableTags` với catalog.
5. Lọc theo từng primary tag.
6. Kiểm tra measurement và type có đúng semantics.
7. Đối chiếu Prometheus scrape output nếu backend là Prometheus.

Actuator metrics endpoint là công cụ chẩn đoán. Nó không thay thế monitoring backend có lịch sử và dashboard.

### 9.3. Kiểm tra cardinality trước khi merge

Với mỗi tag mới, liệt kê tập giá trị hợp lệ, ước tính số tổ hợp tags, kiểm tra giá trị có tăng theo từng request/event/user không, xác nhận tag không chứa PII/secret và xem có thể dùng logs/traces thay cho metric dimension không.

Micrometer có High Cardinality Tags Detector ở các phiên bản hỗ trợ, có thể giúp phát hiện meter name có số lượng meter tăng bất thường. Detector là tín hiệu chẩn đoán, không thay thế thiết kế tags có giới hạn.

## 10. Tình huống thực tế: tài liệu hóa event metrics

### 10.1. Bối cảnh

Ứng dụng cửa hàng có ba module:

```text
orders
  - OrderPlaced
  - OrderCancelled
inventory
  - StockReserved
  - StockRejected
payments
  - PaymentAuthorized
  - PaymentDeclined
```

Nhóm vận hành cần tài liệu hóa event metrics để xây dashboard và điều tra khi một loại event không còn được publish.

### 10.2. Ghi catalog metric tổng hợp

```yaml
metric:
  micrometerName: module.events.published
  type: counter
  unit: publications
  description: >
    Số lần domain event được công bố bởi các application modules.
  source:
    kind: spring-modulith
    owner: platform-observability
  primaryTags:
    - key: module.event.type
      values: [OrderPlaced, OrderCancelled, StockReserved, StockRejected, PaymentAuthorized, PaymentDeclined]
    - key: module.identifier
      values: [orders, inventory, payments]
    - key: module.name
      values: [Orders, Inventory, Payments]
  semantics:
    measures: event publication
    doesNotMeasure: [listener completion, transaction outcome]
  usage:
    dashboard: Event publications by type
    queries:
      - rate grouped by module.event.type
      - increase grouped by module.identifier
```

Các event type values là tập giả định cho ứng dụng mẫu. Trong ứng dụng thật, lấy values từ Actuator `availableTags` hoặc Prometheus scrape output.

### 10.3. Ghi catalog cho counter riêng

Metric riêng cho event `OrderPlaced` của module `orders` có meter name dạng:

```text
module.events.published.orders.OrderPlaced
```

Primary tags mặc định:

```text
module.identifier="orders"
module.name="Orders"
```

Nếu customizer thêm `sales.channel`, ghi tag đó cùng danh sách values hợp lệ. Đừng ghi `module.event.type` là tag mặc định của metric riêng.

### 10.4. Chẩn đoán khi event volume giảm

Khi `OrderPlaced` giảm về 0, người trực cần kiểm tra:

- Luồng nghiệp vụ có còn tạo đơn không?
- Prometheus target có được scrape không?
- Tag event type có đổi tên sau deploy không?
- Module orders có thay đổi event contract không?
- Dashboard có đang lọc sai module/environment không?
- Listener có lỗi hay không? Nếu câu hỏi là listener, kiểm tra publication registry/traces riêng.

Metric catalog giúp người trực biết phép đo phản ánh bước nào và nơi cần điều tra tiếp.

## 11. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Dashboard không tìm thấy metric sau deploy | Metric name đã đổi | So sánh catalog và scrape output |
| Actuator query trả 404 | Dùng Prometheus name thay cho Micrometer name | Dùng meter name gốc có dấu chấm |
| Metric tổng hợp không có event type label | Đang xem counter riêng | Kiểm tra đúng meter family |
| Tag value có nhiều cách viết | Không chuẩn hóa enum/status | Chuẩn hóa value trước khi ghi |
| Số series tăng đột biến | Tag chứa ID, timestamp hoặc raw input | Bỏ tag động, chuyển dữ liệu sang logs/traces |
| Metric name có nhiều biến thể | Đưa tag value vào tên | Dùng meter name ổn định và tags |
| Hai dashboard cho hai tổng khác nhau | Cộng cả aggregate và individual counters | Chọn một metric family cho phép đo |
| Dashboard vẫn có số liệu nhưng nghĩa đã sai | Semantics thay đổi mà name giữ nguyên | Version hóa schema, đổi tên hoặc migration |
| Tag module không khớp module graph | Dùng display name làm technical key hoặc mapping lỗi | Kiểm tra `module.identifier` và `module.name` |
| Alert không kích hoạt sau refactor | Alert selector còn tag value cũ | Cập nhật dashboard/alert cùng metric contract |
| Không thấy metric trong Prometheus | Registry thiếu hoặc endpoint chưa scrape | Kiểm tra dependency, expose và target |
| Common tag bị trùng | Thêm tag môi trường đã có từ scrape labels | Xác định nguồn label và giữ một convention |

### 11.1. Thứ tự chẩn đoán

1. Xác nhận meter name gốc qua `/actuator/metrics`.
2. Xem `availableTags` để biết tag keys và values.
3. Kiểm tra scrape output để biết tên backend và label mapping.
4. So sánh với metric catalog và version deploy.
5. Kiểm tra query selectors trong dashboard/alert.
6. Đánh giá cardinality nếu số series tăng.
7. Đối chiếu logs/traces/event publication registry khi cần biết outcome.

Không sửa dashboard bằng cách thêm tag giả nếu meter source đang tạo sai schema. Hãy sửa tại nơi định nghĩa meter hoặc mapping có chủ đích.
## 12. Quy trình duy trì metric documentation

### Khi thêm metric mới

- Xác định câu hỏi vận hành cần trả lời.
- Chọn meter type và unit.
- Chọn tên metric ổn định.
- Chọn primary tags có tập giá trị hữu hạn.
- Xác định owner và consumers.
- Ước tính cardinality.
- Viết catalog trước hoặc cùng thay đổi code.
- Thêm dashboard/alert có semantics rõ.
- Kiểm tra Actuator và scrape output.

### Khi thêm tag mới

- Ghi lý do cần dimension và liệt kê allowed values.
- Ước tính số series tăng thêm.
- Kiểm tra tag không chứa ID/PII/secret.
- Kiểm tra label key không trùng common/scrape label.
- Cập nhật catalog, dashboard variables và alert rules.
- Kiểm thử trên staging.

### Khi nâng Spring Boot hoặc Spring Modulith

- Kiểm tra dependency management và phiên bản registry.
- Xem lại meter names và tags thực tế.
- So sánh với catalog phiên bản trước.
- Xác minh Actuator selector và Prometheus naming convention.
- Chạy dashboard/alert smoke checks.
- Ghi lại breaking changes nếu có.

### Khi ngừng metric

- Tìm tất cả consumers.
- Thông báo owner/dashboard maintainers.
- Chuyển sang metric thay thế.
- Đặt thời hạn ngừng phát và theo dõi việc sử dụng tên cũ.
- Gỡ catalog entry cũ sau khi migration hoàn tất.

## 13. Những hiểu lầm cần tránh

1. **Metric name và tag là cùng một thứ.** Name xác định đại lượng; tags phân loại đại lượng đó.
2. **Mọi tag đều là primary tag.** Primary tags là những chiều quan trọng đã chọn; common tags và scrape labels có nguồn khác.
3. **Tên Prometheus là tên gọi trong Actuator.** Actuator dùng Micrometer name gốc.
4. **Metric tổng hợp và metric riêng là hai phép đo độc lập.** Chúng có thể cùng phản ánh một publication theo hai cách; không cộng bừa.
5. **Counter publication đo listener success.** Nó đo việc event được công bố.
6. **Một tag có ít giá trị nghĩa toàn metric ít cardinality.** Cardinality là số tổ hợp của tất cả labels.
7. **Đưa ID vào tag giúp tìm giao dịch dễ hơn.** Logs/traces phù hợp hơn cho từng giao dịch.
8. **Đổi display name không ảnh hưởng dashboard.** Nếu display name là tag selector, query có thể bị ảnh hưởng.
9. **Giữ metric name nhưng đổi semantics là an toàn.** Dashboard vẫn có dữ liệu nhưng ý nghĩa đã khác.
10. **Catalog chỉ cần tên và mô tả.** Cần cả type, unit, tags, source, owner, cardinality và consumers.
11. **Common tags có thể thêm tùy ý.** Common tags được áp dụng lên mọi meter và có thể gây trùng dimension.
12. **Metric có trong code thì backend chắc chắn có.** Registry, exporter, endpoint exposure và scrape đều phải hoạt động.

## 14. Câu hỏi tự đánh giá

1. Metric contract cần ghi những trường nào?
2. Metric name, meter type, unit và tags khác nhau ra sao?
3. Vì sao nên dùng lowercase dot notation cho Micrometer names?
4. Khi nào nên dùng một metric với tags thay vì nhiều metric names?
5. Ba primary tags mặc định của `module.events.published` là gì?
6. Vì sao metric riêng của event không có `module.event.type` tag mặc định?
7. Tại sao không cộng aggregate counter và individual counters?
8. Vì sao event publication counter không xác nhận listener completion?
9. `module.identifier` và `module.name` phục vụ mục đích khác nhau nào?
10. Vì sao không đưa order ID hoặc trace ID vào metric tags?
11. Common tags khác scrape target labels như thế nào?
12. Tại sao Actuator dùng meter name gốc trong khi Prometheus có thể chuẩn hóa tên?
13. Khi nào dùng `ModulithEventMetricsCustomizer`?
14. Làm sao xác định tag mới có làm tăng cardinality quá mức?
15. Khi đổi tag key, những dashboard/alert nào cần được cập nhật?
16. Vì sao thay đổi semantics cần được xem là breaking change dù metric name không đổi?
17. Làm thế nào dùng Actuator `availableTags` để xác minh metric catalog?
18. Khi event volume giảm về 0, cần kiểm tra nguồn metric, scrape và nghiệp vụ theo thứ tự nào?

## 15. Tài liệu tham khảo chính thức

- [Spring Modulith 2.2 — Production-ready Features](https://docs.spring.io/spring-modulith/reference/2.2/production-ready.html): event publication counters, primary tags, individual event metrics và `ModulithEventMetricsCustomizer`.
- [Spring Boot 4.2 — Metrics](https://docs.spring.io/spring-boot/4.2/reference/actuator/metrics.html): MeterRegistry, common tags, Actuator metrics endpoint, Prometheus registry và naming.
- [Micrometer — Naming Meters](https://docs.micrometer.io/micrometer/reference/concepts/naming.html): lowercase dot notation, registry naming conventions, tag naming và tag values.
- [Micrometer — High Cardinality Tags Detector](https://docs.micrometer.io/micrometer/reference/concepts/high-cardinality-tags-detector.html): nhận diện tag values không giới hạn và số lượng meters tăng bất thường.
- [Prometheus — Metric and Label Naming](https://prometheus.io/docs/practices/naming/): metric prefixes, base units, suffixes, label dimensions và cardinality.
- [Prometheus — Instrumentation](https://prometheus.io/docs/practices/instrumentation/): chọn metric và sử dụng labels hợp lý.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/4.2/reference/actuator/endpoints.html): expose và bảo vệ Actuator endpoints.

> **Ghi nhớ:** Metric catalog là hợp đồng giữa code và người vận hành. Ghi rõ **metric name, type, unit, semantics, primary tags, source, owner và cardinality**. Với Spring Modulith, dùng `module.events.published` khi cần phân tích theo `module.event.type`; hiểu rằng counter riêng theo event đưa event type vào metric name và có thể được custom tags. Xác minh tên/tag qua Actuator và scrape output, rồi cập nhật dashboard, alert và runbook mỗi khi schema thay đổi.
