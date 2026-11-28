# Chi phí ghi event metrics

> **Chương:** Hiệu năng  
> **Bối cảnh:** Spring Modulith có thể tự ghi nhận số lần application event được publish bằng Micrometer counters. Các counter giúp theo dõi hoạt động giữa các module, nhưng mỗi lần ghi metric và mỗi time series đều có chi phí CPU, memory, scrape, network và lưu trữ. Bài này phân tích đường đi của event metrics, cách ước lượng cardinality và chi phí, cách đo overhead trong ứng dụng Spring Boot, cùng các lựa chọn tối ưu an toàn.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích hai metric event publication mặc định của Spring Modulith.
2. Phân biệt chi phí tăng counter với chi phí tạo time series và scrape metrics.
3. Ước lượng số counter updates, time series và sample volume theo event rate.
4. Nhận diện custom tag có cardinality cao và nguy cơ làm Prometheus/backend quá tải.
5. Phân biệt event metrics với module spans và Event Publication Registry.
6. Đo overhead bằng workload thực tế, so sánh CPU, latency, allocation, series và scrape payload.
7. Chọn cách instrument và dashboard phù hợp với lưu lượng của từng module.

## 1. Spring Modulith ghi nhận event metrics như thế nào?

Từ Spring Modulith 1.4, observability support có thể tự đăng ký counters cho application events được publish. Tài liệu Spring Modulith hiện hành mô tả hai metric:

| Metric | Ý nghĩa |
| --- | --- |
| **module.events.published** | Counter tổng hợp tất cả event publication |
| **module.events.published.$moduleIdentifier.$simpleEventTypeName** | Counter riêng cho từng event type thuộc module, có thể được bổ sung domain-specific tags |

Metric tổng có các low-cardinality keys:

| Tag key | Ý nghĩa |
| --- | --- |
| **module.event.type** | Loại event được publish |
| **module.identifier** | Technical identifier của module |
| **module.name** | Tên hiển thị của module |

Metric riêng theo event có các low-cardinality keys:

| Tag key | Ý nghĩa |
| --- | --- |
| **module.identifier** | Technical identifier của module |
| **module.name** | Tên hiển thị của module |

Metric tổng giúp so sánh hoạt động event giữa các module/type. Metric riêng giúp theo dõi một loại event cụ thể và cho phép thêm tag tùy biến khi có nhu cầu.

### 1.1. Kích hoạt observability support

Nếu dự án cần cả module Actuator và observability, cách thuận tiện là dùng Insight starter:

~~~groovy
dependencies {
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'
}
~~~

Nếu chỉ cần module observability:

~~~groovy
dependencies {
    runtimeOnly 'org.springframework.modulith:spring-modulith-observability-core'
}
~~~

Khi muốn triển khai customizer cho event metrics, cần thêm API artifact ở compile scope:

~~~groovy
dependencies {
    implementation 'org.springframework.modulith:spring-modulith-observability-api'
}
~~~

Các ví dụ giả định dự án đã quản lý version Spring Modulith bằng BOM hoặc dependency management tương thích với Spring Boot. Insight starter không tự cấu hình mọi monitoring backend; registry/exporter và hạ tầng scrape vẫn tùy công cụ được chọn.

## 2. Đường đi của một event metric

Một lần publish event có thể đi qua các bước:

~~~mermaid
flowchart TD
    A["ApplicationEventPublisher.publishEvent()"] --> B["Spring Modulith observability"]
    B --> C["Tăng counter tổng"]
    B --> D["Tăng counter theo event type"]
    C --> E["Micrometer MeterRegistry"]
    D --> E
    E --> F["Actuator /actuator/metrics"]
    E --> G["Prometheus registry"]
    G --> H["Prometheus scrape"]
    H --> I["TSDB, query, dashboard, alert"]
~~~

Có ba loại chi phí khác nhau:

1. **Chi phí tại thời điểm publish:** thực thi logic quan sát, tìm counter và tăng giá trị.
2. **Chi phí quản lý time series:** đăng ký meter, giữ meter/label set và duy trì dữ liệu theo từng bộ tag.
3. **Chi phí export và lưu trữ:** render endpoint, scrape, truyền sample, ingest, index và giữ dữ liệu theo retention.

Không nên gộp cả ba thành một con số "chi phí metrics". Tối ưu tăng counter không đồng nghĩa giảm số time series hoặc giảm chi phí scrape.

## 3. Chi phí runtime trên mỗi lần publish

### 3.1. Counter update là thao tác thường xuyên

Với mỗi event publication, Spring Modulith ghi nhận counter tổng và counter riêng theo event type. Có thể dùng mô hình sơ bộ:

~~~text
counter updates / second
  ≈ event publications / second × 2
~~~

Ví dụ 2.000 event publications/giây tương ứng khoảng 4.000 counter increments/giây cho hai counter mặc định, chưa tính custom metrics hoặc các instrumentation khác.

Đây là mô hình để ước lượng tải, không phải cam kết về số lời gọi nội bộ của mọi phiên bản. Chi tiết thực thi có thể thay đổi theo release và registry.

### 3.2. Chi phí steady state và lần đầu khác nhau

Khi event type và tag set đã được đăng ký, các lần publish tiếp theo thường cập nhật meter đã tồn tại. Lần đầu xuất hiện một meter hoặc một tổ hợp tag mới có thể tốn thêm chi phí tạo/register meter.

Do đó cần phân biệt:

- **Steady state:** counter đã được đăng ký, event chỉ cập nhật giá trị.
- **First-seen event/tag set:** registry có thể phải tạo meter/time series mới.
- **High-cardinality stream:** mỗi giá trị tag mới có thể tiếp tục tạo thêm meter/time series.

Nếu event customizer gắn order ID vào tag, mỗi đơn hàng mới có thể tạo một series mới. Chi phí lúc này không còn chỉ là counter increment.

### 3.3. CPU và allocation

Chi phí CPU có thể đến từ:

- Lấy event type/module metadata.
- Tạo hoặc tra cứu meter theo tên và tag set.
- Thực thi counter increment.
- Tạo KeyValues, tag arrays hoặc object phụ trợ trong đường ghi metric.
- Registry synchronization và quản lý meter khi có tag set mới.

Không thể suy ra số microsecond cho mỗi event chỉ từ tài liệu. Chi phí phụ thuộc JDK, Micrometer version, registry, concurrency, số meter, tag set, CPU và workload. Cần đo trên ứng dụng thực tế.

### 3.4. Metrics không tự ghi event vào database

Hai counters event metrics là số liệu quan sát trong Micrometer registry. Bản thân thao tác tăng counter không tương đương với việc lưu một bản ghi event vào database.

Nếu ứng dụng bật Spring Modulith Event Publication Registry, đó là cơ chế riêng: registry có thể ghi publication entry cho từng transactional listener trong transaction nghiệp vụ. Chi phí database của registry gồm insert/update/delete, index, transaction và dọn dữ liệu; không nên quy toàn bộ chi phí đó cho event metrics.

## 4. Chi phí cardinality: yếu tố dễ tăng nhanh nhất

Trong Prometheus, một time series được xác định bởi metric name và toàn bộ bộ label values. Mỗi tổ hợp label khác nhau có thể tạo một series riêng.

Spring Modulith thiết kế các tag mặc định theo hướng low cardinality: module identifier, module name và event type là các giá trị hữu hạn theo cấu trúc ứng dụng. Rủi ro thường xuất hiện khi customizer thêm giá trị lấy từ dữ liệu runtime.

### 4.1. Công thức ước lượng

Gọi:

- **P** là số tổ hợp module/event type xuất hiện trong metric tổng.
- **C_e** là số tổ hợp custom tag khác nhau của event type **e**.

Số series xấp xỉ:

~~~text
series_total ≈ P + Σ C_e
~~~

Đây là mô hình đơn giản cho hai metric mặc định. Số series thực tế phụ thuộc số module/event type, registry, tag set đã xuất hiện, filter và cách backend chuẩn hóa metric.

Không lấy event publications/giây làm cardinality. Một event type có thể publish hàng triệu lần nhưng vẫn giữ một số series cố định nếu bộ tag không thay đổi.

### 4.2. Ví dụ tag có cardinality thấp

Giả sử event OrderPlaced có thuộc tính channel là enum gồm ba giá trị:

~~~java
enum OrderChannel {
    WEB, MOBILE, STORE
}
~~~

Nếu thêm tag channel, event metric có tối đa ba tổ hợp tag cho loại event đó. Đây là cardinality hữu hạn và có thể dự báo.

### 4.3. Ví dụ tag có cardinality cao

Không nên thêm các giá trị sau vào metric:

~~~text
order.id = "ORD-2026-000001"
customer.id = "customer-..."
request.id = "..."
email = "..."
full.url = "/orders/ORD-..."
~~~

Nếu mỗi đơn hàng có một ID mới, series có thể tăng theo số đơn hàng. Khi có hàng triệu ID, Prometheus phải quản lý hàng triệu label sets; RAM, index, WAL, scrape và query cost đều tăng.

**Nguyên tắc:** tag mô tả nhóm hữu hạn; trace/log chứa định danh một lần thực thi khi chính sách dữ liệu cho phép.

## 5. Custom event metrics an toàn

Spring Modulith cung cấp ModulithEventMetricsCustomizer để bổ sung tag cho metric riêng theo event type.

Ví dụ event có channel là enum:

~~~java
public record OrderPlaced(
        java.util.UUID orderId,
        OrderChannel channel
) {}
~~~

Customizer:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.modulith.observability.ModulithEventMetricsCustomizer;

@Configuration(proxyBeanMethods = false)
class ObservabilityConfiguration {

    @Bean
    ModulithEventMetricsCustomizer eventMetricsCustomizer() {
        return metrics -> metrics.customize(OrderPlaced.class, (event, builder) -> {
            builder.tags("channel", event.channel().name());
        });
    }
}
~~~

Tag channel có ba giá trị cố định. orderId không được thêm vào metric, dù nó có sẵn trên event object.

### 5.1. Quy tắc khi customizer đọc event data

- Chỉ dùng enum hoặc tập giá trị đã giới hạn.
- Chuẩn hóa các giá trị không biết về OTHER thay vì tạo tag mới cho mỗi giá trị.
- Không dùng ID nghiệp vụ, token, email hoặc URL động.
- Không đưa nội dung exception/message vào tag.
- Xem xét việc tag có thể tiết lộ dữ liệu nghiệp vụ hay không.
- Đo số series trước và sau khi thêm tag.

### 5.2. Giới hạn của customizer

Customizer chỉ thay đổi cách tạo counter và tag. Nó không biến event metric thành event store, không cung cấp lịch sử từng event và không chứng minh listener đã hoàn tất.

Nếu cần truy vấn từng event hoặc kiểm tra listener publication state, dùng Event Publication Registry hoặc hệ thống lưu trữ nghiệp vụ phù hợp.

## 6. Chi phí scrape, export và storage

Counter được tăng khi event được publish, còn Prometheus đọc giá trị theo scrape interval. Hai tần suất này độc lập.

Ví dụ:

- 2.000 event publications/giây làm counter tăng liên tục.
- Prometheus scrape mỗi 15 giây chỉ đọc snapshot counter ở mỗi lần scrape.
- Tăng scrape frequency không làm ứng dụng tăng số lần publish event, nhưng làm backend nhận nhiều samples hơn trên mỗi series.

### 6.1. Sample volume

Ước lượng số sample/ngày:

~~~text
samples/day ≈ active time series × (86,400 / scrape interval seconds)
~~~

Ví dụ có 500 active series, scrape mỗi 15 giây:

~~~text
500 × (86,400 / 15) = 2,880,000 samples/day
~~~

Con số này chưa tính series từ các meter khác và không phản ánh chính xác bytes lưu trữ. Backend còn phụ thuộc encoding, compression, labels, index và retention.

### 6.2. Scrape payload

Khi số series tăng:

- Endpoint /actuator/prometheus phải render nhiều sample hơn.
- Response body lớn hơn.
- Scraper tốn network và thời gian parse.
- Prometheus ingest nhiều samples hơn.
- Dashboard query cần xử lý nhiều series hơn.

Nếu chỉ có một counter nhưng hàng nghìn tag combinations, payload vẫn lớn dù số event metric names ít.

### 6.3. Retention

Retention kéo dài số ngày giữ sample của mỗi series. Nếu cardinality tăng gấp 10, chi phí lưu trữ có thể tăng đáng kể ngay cả khi event rate không đổi.

Tài liệu vận hành nên ghi:

- Số active series theo service.
- Scrape interval.
- Samples ingested/second.
- Retention và replication.
- Chi phí lưu trữ/index theo backend.
- Ngưỡng cardinality và quy trình khi vượt ngưỡng.

## 7. Đo overhead thực tế

Không có một con số cố định áp dụng cho mọi Spring Boot application. Đo trên workload gần production là cách đáng tin cậy hơn.

### 7.1. Thiết kế ba kịch bản

| Kịch bản | Instrumentation | Mục đích |
| --- | --- | --- |
| A — Baseline | Không bật event metrics của Modulith | Mốc tham chiếu |
| B — Default metrics | Bật hai counters mặc định, không custom tag | Đo chi phí cơ bản |
| C — Custom metrics | Bật counters và tag hữu hạn như channel | Đo tác động của customization |

Nếu có kịch bản D để kiểm tra tag cardinality cao, chỉ chạy trong local/staging với dữ liệu giả. Không đưa ID động vào production chỉ để benchmark.

### 7.2. Giữ workload tương đương

Trong từng kịch bản:

1. Dùng cùng event type và cùng tỷ lệ event/module.
2. Giữ số listener và logic nghiệp vụ không đổi.
3. Dùng cùng JDK, heap, CPU quota và database.
4. Warm-up trước khi đo.
5. Chạy đủ lâu để registry và JIT ổn định.
6. Lặp lại nhiều lần và so sánh median/percentile.

Không so sánh một lần chạy cold start với một lần chạy warm-up rồi kết luận phần chênh lệch hoàn toàn do metrics.

### 7.3. Các chỉ số cần thu thập

| Nhóm | Chỉ số |
| --- | --- |
| Throughput | Event publications/second, business requests/second |
| Latency | p50, p95, p99 của đường publish và request bao quanh |
| CPU | Process CPU, CPU time theo workload |
| Memory | Heap used, allocation rate, GC count/pause |
| Registry | Số meter và active time series |
| Export | /actuator/prometheus response size và latency |
| Backend | Scrape duration, samples ingested/second, active series |
| Storage | Bytes/day, index size và retention footprint |

### 7.4. Không benchmark bằng một vòng lặp rỗng

Đo riêng Counter.increment() bằng một vòng lặp có thể hữu ích để so sánh registry implementations, nhưng không phản ánh toàn bộ chi phí trong ứng dụng. Đường publish thật còn có event dispatch, transaction, listener, module instrumentation và các meter khác.

Hãy dùng một integration/load test chạy qua ApplicationEventPublisher và giữ nguyên logic listener. Nếu cần microbenchmark riêng, tách nó thành một phép đo bổ sung thay vì thay thế workload ứng dụng.

### 7.5. Tách tác động của scrape

Để đo riêng scrape cost:

- Giữ event rate cố định.
- So sánh scrape interval khác nhau.
- Đo response time và response bytes của /actuator/prometheus.
- Quan sát CPU của ứng dụng và Prometheus.
- Giữ số active series không đổi trong từng lần so sánh.

Scrape quá thường xuyên có thể tạo overhead ở cả ứng dụng lẫn backend, ngay cả khi event counter update cost không đổi.

## 8. Ví dụ ước lượng tải

Giả sử:

- 2.000 event publications/giây.
- Mỗi event cập nhật hai counters mặc định.
- Có 40 tổ hợp module/event type.
- Mỗi event type thêm tag channel với ba giá trị hữu hạn.

Counter update rate ước lượng:

~~~text
2,000 × 2 = 4,000 counter increments/second
~~~

Series count minh họa:

~~~text
all-events metric:       40 series
individual event metric: 40 × 3 = 120 series
total:                   about 160 series
~~~

Giả định mỗi event type chỉ thuộc một module và mọi channel đều đã xuất hiện. Series count thực tế phụ thuộc số tổ hợp tag đã được đăng ký và registry/backend.

Nếu thêm orderId với 100.000 giá trị duy nhất trong cửa sổ quan sát, metric riêng có thể tạo gần 100.000 series chỉ cho dimension đó, thay vì ba series của channel. Đây là lý do cần review custom tags trước khi triển khai.

## 9. Metrics, tracing và Event Publication Registry khác nhau

Ba cơ chế này có mục tiêu và chi phí riêng:

| Cơ chế | Dữ liệu ghi nhận | Chi phí chính | Có chịu trace sampling không? |
| --- | --- | --- | --- |
| Event metrics | Số lần publish theo module/event type | Counter update, meter, series, scrape và storage | Không |
| Module spans/traces | Đường thực thi qua module và thời gian invocation | Span creation, context, export, sampling và backend | Có |
| Event Publication Registry | Publication entry gắn với transactional listener và trạng thái xử lý | Transaction, database write/update/delete, index và cleanup | Không |

### 9.1. Event metric không đếm listener completion

Counter module.events.published đo event publication. Một event có thể được nhiều listener nhận, nhưng counter publication không phải bộ đếm số listener hoàn tất.

Muốn theo dõi trạng thái listener, cần dùng Event Publication Registry hoặc metric riêng cho listener success/failure. Không diễn giải counter publish tăng là tất cả consumer đã xử lý thành công.

### 9.2. Event metrics không bị trace sampling loại bỏ

Nếu trace sampling chỉ giữ 10% trace, counters event metrics vẫn được cập nhật theo event publications. Vì vậy:

- Dùng metrics để xem xu hướng và số lượng tổng hợp.
- Dùng traces để điều tra một số lần thực thi được lấy mẫu.
- Dùng publication registry để theo dõi trạng thái transactional listener khi đã cấu hình registry.

Không suy ra event volume từ trace count hoặc trace count từ metric count.

### 9.3. Registry persistence có thể là nguồn chi phí lớn hơn

Spring Modulith Event Publication Registry có thể ghi một entry cho mỗi transactional listener nhận event. Nếu một event có nhiều listener, số bản ghi persistence có thể lớn hơn số event publish.

Nếu completion mode giữ lại publication đã hoàn tất, cần có quy trình purge dữ liệu cũ. Bảng publication không được dọn có thể tăng không giới hạn, làm thao tác ghi/hoàn tất chậm dần. Đây là chi phí persistence của registry, không phải chi phí Micrometer counter.

## 10. Quan sát event metrics bằng Actuator

Nếu có Spring Boot Actuator, kiểm tra danh sách meter:

~~~http
GET /actuator/metrics
~~~

Đọc counter tổng:

~~~http
GET /actuator/metrics/module.events.published
~~~

Response của endpoint metrics có thể cung cấp:

- name: tên meter.
- measurements: giá trị hiện tại và statistic.
- availableTags: các tag key và value đang có.

Để lọc một module, dùng đúng tag được endpoint trả về:

~~~http
GET /actuator/metrics/module.events.published?tag=module.identifier:orders
~~~

Tên tag chính xác là module.identifier trong Micrometer meter; Prometheus có thể chuyển tên thành dạng label hợp lệ như module_identifier. Hãy kiểm tra /actuator/prometheus thay vì đoán tên sau khi chuẩn hóa.

### 10.1. Expose Prometheus endpoint

Nếu dùng Prometheus registry:

~~~groovy
dependencies {
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Cấu hình exposure:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
~~~

Endpoint:

~~~http
GET /actuator/prometheus
~~~

Chỉ expose endpoint metrics cho mạng monitoring hoặc principal được phép. Không cần expose toàn bộ Actuator endpoints để scrape counters.

### 10.2. PromQL minh họa

Tên counter Prometheus thường được chuẩn hóa từ meter name:

~~~promql
sum(rate(module_events_published_total[5m]))
~~~

Phân tích theo module/event type:

~~~promql
sum by (module_identifier, module_event_type) (
  rate(module_events_published_total[5m])
)
~~~

Đây là PromQL minh họa. Tên metric và label thực tế phụ thuộc registry/version và dữ liệu scrape; kiểm tra output /actuator/prometheus trước khi đưa query vào dashboard.

Counter là giá trị tích lũy, nên dùng rate() hoặc increase() để xem tốc độ/số lượng trong một cửa sổ. Process restart có thể reset counter trong bộ nhớ; Prometheus xử lý counter reset khi tính rate/increase.

## 11. Tối ưu chi phí event metrics

### 11.1. Giữ tag set nhỏ và ổn định

- Dùng module identifier và event type cố định.
- Chỉ thêm enum hoặc nhóm giá trị hữu hạn.
- Chuẩn hóa giá trị lạ về OTHER.
- Không thêm ID nghiệp vụ hoặc dữ liệu cá nhân.
- Review mọi customizer như một thay đổi schema metrics.

### 11.2. Đừng tạo metric name động từ dữ liệu runtime

Metric name riêng của Spring Modulith đã bao gồm module identifier và simple event type name. Không tự xây thêm tên metric có chứa order ID, customer ID hoặc timestamp.

Tên metric nên mô tả loại dữ liệu; tag nên biểu diễn các dimension có tập giá trị hữu hạn.

### 11.3. Chọn scrape interval theo nhu cầu

Scrape interval thấp giúp dashboard cập nhật nhanh nhưng tăng sample ingestion, network và scrape load. Event counter thường dùng để xem xu hướng theo phút; không phải lúc nào cũng cần scrape mỗi giây.

Chọn interval dựa trên:

- Độ trễ phát hiện sự cố mong muốn.
- Số active series của toàn bộ ứng dụng.
- Scrape duration và timeout.
- Prometheus ingestion capacity.
- Chi phí lưu trữ/retention.

### 11.4. Giới hạn custom tag ngay tại nguồn

Đừng dựa hoàn toàn vào backend để sửa cardinality sau khi series đã được tạo. Hãy thiết kế tag hữu hạn ngay trong ModulithEventMetricsCustomizer.

Nếu cần dữ liệu chi tiết theo từng order/event, dùng log có cấu trúc, trace attribute phù hợp hoặc event store. Không dùng Prometheus counter làm bảng tra cứu từng entity.

### 11.5. Chỉ bật đúng instrumentation cần thiết

Insight starter cung cấp nhiều khả năng production-ready, gồm Actuator và observability. Nếu dự án chỉ cần event metrics hoặc chỉ cần module spans, cân nhắc dependency phù hợp theo mục đích và version. Không thêm exporter hoặc backend registry không sử dụng.

Không tự giả định có property chung để tắt riêng event metrics nếu tài liệu version đang dùng không công bố property đó. Nếu muốn loại meter khỏi một registry, kiểm tra khả năng MeterFilter của Micrometer và xác nhận meter thực sự bị deny/no-op theo đúng registry.

## 12. Alert và dashboard cho event metrics

### 12.1. Dashboard nên hiển thị

- Event publications/second tổng.
- Event publications/second theo module.
- Top event types theo tốc độ publish.
- Tỷ lệ tăng bất thường so với baseline.
- Active time series và cardinality theo service.
- Scrape duration, scrape errors và samples ingested.

### 12.2. Không alert theo giá trị counter thô

Counter là giá trị tích lũy. Alert theo một ngưỡng cố định như module_events_published_total > 1000000 có thể luôn firing sau một thời gian và không mô tả tốc độ hiện tại.

Dùng rate hoặc increase:

~~~promql
sum(rate(module_events_published_total[5m]))
~~~

Để phát hiện tăng đột biến, so sánh với baseline hoặc ngưỡng theo nghiệp vụ. Một event volume cao có thể là tải bình thường trong campaign; không tạo alert chỉ từ một con số chung cho mọi thời điểm.

### 12.3. Theo dõi cardinality riêng

Event rate bình thường nhưng active series tăng nhanh có thể báo hiệu custom tag bị mở rộng ngoài dự kiến. Theo dõi số active series, scrape payload và ingestion rate độc lập với event rate.

## 13. Checklist đo và review trước production

- [ ] Đã xác định có cần cả hai event counters mặc định không.
- [ ] Đã ghi rõ Spring Modulith và Micrometer versions.
- [ ] Đã kiểm tra tên meter/tag qua Actuator.
- [ ] Đã tính event publications/second và counter update rate dự kiến.
- [ ] Đã ước lượng số module/event type combinations.
- [ ] Đã review custom tags và xác nhận cardinality hữu hạn.
- [ ] Không có order ID, customer ID, request ID, email hoặc token trong metric tags.
- [ ] Đã đo CPU, latency, allocation và GC với workload tương đương.
- [ ] Đã đo /actuator/prometheus response size và scrape duration.
- [ ] Đã xác nhận active series và samples ingested nằm trong budget.
- [ ] Đã phân biệt event metrics với module spans và Event Publication Registry.
- [ ] Đã có dashboard/query dùng rate() hoặc increase().
- [ ] Đã xác nhận metrics không bị nhầm với listener success/completion.
- [ ] Đã review access control cho metrics endpoint.

## 14. Bài tập tự kiểm tra

**Câu 1.** Spring Modulith có hai counters event publication mặc định. Với 1.500 event publications/giây, ước lượng số counter increments/giây theo mô hình hai counters.

**Câu 2.** Một event type được publish 10 triệu lần/ngày nhưng chỉ có module identifier và event type cố định. Cardinality có nhất thiết tăng theo 10 triệu event không?

**Câu 3.** Một customizer thêm orderId làm tag. Vì sao điều này nguy hiểm với Prometheus?

**Câu 4.** Prometheus scrape mỗi 15 giây. Nếu tăng scrape lên mỗi 5 giây, event counter có tăng số lần update trong ứng dụng không? Chi phí nào tăng?

**Câu 5.** Vì sao event metric tăng không chứng minh ApplicationModuleListener đã xử lý thành công?

**Câu 6.** Phân biệt chi phí của Micrometer counter với chi phí của Spring Modulith Event Publication Registry.

**Câu 7.** Vì sao không thể dùng trace sampling 10% để giảm event metrics xuống 10%?

**Câu 8.** Một dashboard thấy event rate ổn định nhưng active series tăng mạnh. Hãy nêu nguyên nhân khả dĩ và bước điều tra.

### Gợi ý đáp án

1. Khoảng 1.500 × 2 = 3.000 counter increments/giây, theo mô hình có counter tổng và counter riêng.
2. Không. Event count làm counter value tăng, nhưng series count giữ ổn định nếu metric name và bộ tag không thay đổi.
3. Mỗi order ID có thể tạo một label set/time series mới; cardinality, RAM, index, WAL, scrape và query cost tăng theo số ID.
4. Không. Counter vẫn được tăng theo event publications. Scrape thường xuyên hơn làm tăng samples/giây, network, render/parse và backend ingestion.
5. Metric đo publication, không đo trạng thái hoàn tất của từng listener. Dùng Event Publication Registry hoặc metric riêng cho listener.
6. Counter là cập nhật số liệu trong Micrometer registry; Event Publication Registry ghi publication entry bền vững trong database theo transactional listener, có transaction/index/cleanup cost.
7. Event metrics là counters độc lập với trace sampling; sampling chỉ quyết định trace/span được ghi lại.
8. Có thể custom tag dùng ID động, URL động hoặc exception message. Kiểm tra meter tags, registry series count và customizer vừa thay đổi.

## 15. Ghi nhớ

Spring Modulith ghi hai counters cho event publication: một counter tổng và một counter theo module/event type. Chi phí runtime gồm logic quan sát và counter increments; chi phí hệ thống thường tăng mạnh hơn khi có nhiều tag combinations, series, scrape samples và dữ liệu phải lưu.

Giữ tag mặc định hoặc bổ sung dimension hữu hạn như enum. Không dùng order ID, customer ID, request ID, email hay payload làm metric tag. Đo overhead bằng workload tương đương và theo dõi CPU, latency, allocation, active series, scrape payload cùng ingestion rate. Event metrics độc lập với trace sampling và không chứng minh listener hoàn tất; Event Publication Registry là cơ chế persistence riêng với chi phí database riêng.

### Tài liệu tham khảo

- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): hai event counters, low-cardinality keys và ModulithEventMetricsCustomizer.
- [Spring Modulith — ModulithEventMetrics API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithEventMetrics.html): SPI tùy chỉnh counter cho cross-module events.
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): Event Publication Registry, lifecycle, completion và cleanup.
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html): Micrometer Observation, low/high cardinality key values và metrics/traces.
- [Micrometer — Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html): lọc và giới hạn meter/tag.
- [Prometheus — Data Model](https://prometheus.io/docs/concepts/data_model/): time series, metric names và label sets.
- [Prometheus — Metric Types](https://prometheus.io/docs/concepts/metric_types/): counter semantics và cách diễn giải counter.
