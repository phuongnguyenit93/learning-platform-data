# Đối chiếu dữ liệu giữa các instance, phiên bản và môi trường

Metrics chỉ có thể so sánh khi chúng mô tả cùng một đại lượng theo cùng một quy ước. Hai instance có thể cùng chạy một service nhưng dùng cấu hình histogram khác nhau; hai phiên bản có thể đổi tên meter hoặc tag; môi trường staging và production có thể dùng đơn vị, tải hoặc scrape interval khác nhau. Nếu không chuẩn hóa những yếu tố này, dashboard dễ tạo ra kết luận sai dù dữ liệu từng instance đều hợp lệ.

Đối chiếu metrics cần ba lớp định danh: service đang được đo, instance cụ thể và môi trường/phiên bản triển khai. Sau đó phải bảo đảm metric schema, đơn vị, tags, temporality và cách tổng hợp có cùng semantics. Micrometer cung cấp meter và tags; registry/exporter cùng hệ thống thu thập quyết định cách các thông tin đó được biểu diễn và lưu trữ.

## 1. Ba cấp độ cần phân biệt

| Cấp độ | Ý nghĩa | Ví dụ định danh |
| --- | --- | --- |
| Service | Một năng lực hoặc ứng dụng logic | service=order-service |
| Instance | Một tiến trình/container cụ thể đang chạy service | instance=10.0.4.21:8080 |
| Deployment context | Môi trường, phiên bản, vùng hoặc cụm triển khai | environment=production, version=2.8.1, region=ap-southeast-1 |

Một service có thể có nhiều instance và nhiều phiên bản cùng tồn tại trong thời gian rolling deployment. Khi cần so sánh hiệu năng giữa các instance, giữ chiều instance. Khi cần xem toàn service, tổng hợp qua instance nhưng giữ các chiều service, environment và version cần phân tích.

~~~mermaid
flowchart TD
    A["Service: order-service"] --> B["Environment: production"]
    B --> C["Version: 2.8.1"]
    C --> D["Instance A"]
    C --> E["Instance B"]
    B --> F["Version: 2.9.0"]
    F --> G["Instance C"]
    D --> H["Metrics series"]
    E --> H
    G --> H
~~~

Trong lúc triển khai phiên bản mới, dữ liệu của 2.8.1 và 2.9.0 có thể cùng tồn tại. Đây là điều cần thiết để so sánh hành vi trước và sau release. Nếu chỉ gắn nhãn service mà bỏ version, dashboard không thể tách hai nhóm dữ liệu trong giai đoạn rollout.

## 2. Xác định bộ nhãn định danh ổn định

Một bộ nhãn thường hữu ích cho metrics của service:

| Key | Ví dụ | Quy tắc |
| --- | --- | --- |
| service | order-service | Tên logic ổn định của service |
| environment | production, staging | Tập giá trị hữu hạn theo môi trường |
| version | 2.9.0 | Phiên bản phát hành có ý nghĩa so sánh |
| region | ap-southeast-1 | Vùng triển khai, nếu cần đối chiếu địa lý |
| instance | pod-7f9d hoặc target address | Định danh instance, thường do hệ thống scrape/collector bổ sung |

Tên key nên nhất quán giữa các service và môi trường. Không để service A dùng env, service B dùng environment, service C dùng deployment cho cùng một khái niệm nếu backend cần truy vấn chung.

### Service, version và environment trong Micrometer

Có thể thêm common tags vào registry bằng MeterRegistryCustomizer trong Spring Boot:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.actuate.autoconfigure.metrics.MeterRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration
class MetricsIdentityConfiguration {

    @Bean
    MeterRegistryCustomizer<MeterRegistry> commonMetricTags(
        Environment environment
    ) {
        return registry -> registry.config().commonTags(
            "service", environment.getRequiredProperty("app.identity.service"),
            "environment", environment.getRequiredProperty("app.identity.environment"),
            "version", environment.getRequiredProperty("app.identity.version")
        );
    }
}
~~~

Cấu hình tương ứng:

~~~yaml
app:
  identity:
    service: order-service
    environment: production
    version: 2.9.0
~~~

Giá trị phải đến từ cấu hình triển khai hoặc metadata build đáng tin cậy. Không hardcode production trong mã vì cùng artifact cần có thể chạy ở staging và môi trường test.

MeterRegistryCustomizer áp dụng common tags cho meter trong registry được cấu hình. Nếu ứng dụng có nhiều registry, xác minh customizer được áp dụng cho từng registry cần export.

### Instance label nên được quản lý ở đâu?

Với Prometheus pull model, Prometheus thường tự gắn label instance từ scrape target. Cách này giúp phân biệt target mà không phải thêm instance ID vào mọi meter trong code. Service, environment và version có thể là common tags hoặc target labels tùy kiến trúc discovery.

Với hệ thống push/OTLP, định danh instance thường được truyền dưới dạng resource attribute như service.instance.id. Hãy chọn một nguồn authoritative và tránh gắn hai giá trị instance khác nhau vào cùng dữ liệu.

Không dùng request ID, user ID, order ID hoặc job ID làm định danh chung của metrics. Những giá trị này thay đổi theo từng sự kiện và làm số time series tăng không giới hạn.

## 3. Metric schema phải giữ cùng semantics

Để so sánh hai tập metrics, cần kiểm tra các thuộc tính sau:

- Tên meter và ý nghĩa nghiệp vụ.
- Loại meter: Counter, Gauge, Timer hoặc DistributionSummary.
- Đơn vị đo và quy tắc chuyển đổi.
- Tên tag, kiểu giá trị và tập giá trị có thể xuất hiện.
- Histogram bucket/SLO boundaries nếu cần tổng hợp phân phối.
- Cách exporter biểu diễn cumulative hoặc delta.
- Khoảng thời gian scrape/flush và chính sách lưu trữ.

Ví dụ, orders.created là số đơn hàng được tạo thành công. Nếu phiên bản mới đổi thành orders.accepted nhưng semantics vẫn giống nhau, dashboard cần một giai đoạn tương thích hoặc phép chuyển đổi. Nếu semantics thay đổi, không nên gộp hai metric như thể chúng giống nhau.

### Đơn vị phải nhất quán

Micrometer Timer ghi thời gian bằng Duration hoặc các đơn vị thời gian được hỗ trợ, nhưng registry có thể xuất theo đơn vị chuẩn của backend. Prometheus thường biểu diễn Timer theo giây với hậu tố _seconds. DistributionSummary có thể khai báo base unit như bytes.

Không so sánh trực tiếp:

- Millisecond với second.
- Byte với kilobyte nếu chưa chuyển đổi.
- Số request với số operation nghiệp vụ nếu phạm vi đếm khác nhau.
- Một Timer đo toàn bộ use case với Timer chỉ đo một dependency.

Khi đổi unit hoặc phạm vi đo, hãy coi đó là thay đổi metric contract và cập nhật dashboard/query có kiểm soát.

## 4. So sánh Counter giữa các instance và phiên bản

Counter biểu diễn tổng tích lũy và thường reset khi process khởi động lại. Vì vậy, raw counter value của hai instance không phản ánh trực tiếp tốc độ xử lý.

Ví dụ:

| Instance | Counter hiện tại |
| --- | ---: |
| A | 1.200.000 |
| B | 80.000 |

Không thể kết luận A xử lý nhanh hơn B chỉ từ hai con số này. Instance A có thể chạy lâu hơn nhiều. Hãy dùng tốc độ tăng theo thời gian hoặc mức tăng trong một cửa sổ quan sát.

Với Prometheus:

~~~promql
sum by (service, environment, version) (
  rate(orders_created_total[5m])
)
~~~

Query này tính tốc độ tăng trung bình trong cửa sổ 5 phút rồi tổng hợp qua các instance, giữ lại service, environment và version để so sánh.

Để xem từng instance:

~~~promql
sum by (service, environment, version, instance) (
  rate(orders_created_total[5m])
)
~~~

rate() xử lý counter reset theo semantics của Prometheus. Không lấy raw value của counter để so sánh giữa process có uptime khác nhau. Nếu muốn tổng số event trong một khoảng thời gian, dùng increase():

~~~promql
sum by (environment, version) (
  increase(orders_created_total[1h])
)
~~~

Khi rollout, hãy so sánh rate trên cùng cửa sổ và cùng nhóm workload. Phiên bản mới có thể nhận ít traffic hơn nên tổng số request thấp hơn dù latency tốt hơn.

## 5. So sánh latency bằng histogram tương thích

Timer có thể xuất count, sum, max và histogram buckets tùy cấu hình registry. Histogram cho phép tổng hợp quan sát từ nhiều instance rồi tính quantile trên phân phối chung.

Ví dụ cấu hình Timer:

~~~java
Timer checkout = Timer.builder("business.checkout.duration")
    .description("Thời gian hoàn thành checkout")
    .publishPercentileHistogram()
    .serviceLevelObjectives(
        Duration.ofMillis(100),
        Duration.ofMillis(300),
        Duration.ofSeconds(1)
    )
    .register(registry);
~~~

Các bucket/SLO ở đây chỉ là ví dụ. Chọn boundaries dựa trên yêu cầu sản phẩm và giữ cấu hình tương thích giữa các instance/phiên bản cần so sánh.

Với Prometheus classic histogram, bucket là bộ đếm tích lũy theo label le. Có thể tính p95 toàn service theo version:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, service, environment, version) (
    rate(business_checkout_duration_seconds_bucket[5m])
  )
)
~~~

Query tổng hợp bucket từ các instance có cùng schema trước khi tính quantile. Nếu muốn xem từng instance, thêm instance vào by (...).

### Bucket boundaries phải tương thích

Nếu version cũ có bucket 100 ms, 300 ms, 1 s nhưng version mới dùng 200 ms, 500 ms, 2 s, không nên coi hai histogram là cùng một schema. Có thể so sánh trong một khoảng rollout nếu backend vẫn có các bucket tương thích chung, nhưng độ chính xác và cách diễn giải phải được kiểm tra.

Thay đổi bucket có thể làm dashboard percentile hoặc SLO bị sai trong giai đoạn có nhiều version. Hãy triển khai schema mới có kế hoạch, giữ bucket chung cần thiết hoặc tách query theo schema/version.

### Không tổng hợp percentile đã tính sẵn theo instance

Percentile client-side được tính riêng trên từng instance thường không thể cộng hoặc lấy trung bình để ra percentile toàn service. Ví dụ trung bình p95 của A và B không phải p95 của toàn bộ request A+B.

Nếu cần percentile toàn service, ưu tiên histogram buckets có thể tổng hợp rồi dùng histogram_quantile. Chỉ so sánh percentile per-instance khi mục tiêu thực sự là phát hiện instance lệch chuẩn.

## 6. So sánh throughput, latency và error rate cùng nhau

Một phiên bản có latency thấp hơn chưa chắc tốt hơn nếu nó xử lý ít request hơn hoặc trả lỗi nhiều hơn. Khi đánh giá release, cần xem nhiều tín hiệu:

| Chỉ số | Câu hỏi |
| --- | --- |
| Throughput | Phiên bản xử lý bao nhiêu request/operation mỗi giây? |
| p50/p95/p99 latency | Người dùng chờ bao lâu, đặc biệt ở phần đuôi phân phối? |
| Error rate | Tỷ lệ request lỗi có tăng không? |
| Saturation | CPU, memory, thread pool, connection pool có gần giới hạn không? |
| Instance count | Hai version đang chạy bao nhiêu instance và nhận bao nhiêu traffic? |

Ví dụ throughput HTTP theo version:

~~~promql
sum by (service, environment, version) (
  rate(http_server_requests_seconds_count[5m])
)
~~~

Ví dụ tỷ lệ response 5xx:

~~~promql
sum by (service, environment, version) (
  rate(http_server_requests_seconds_count{status=~"5.."}[5m])
)
/
sum by (service, environment, version) (
  rate(http_server_requests_seconds_count[5m])
)
~~~

Tên metric và tag status ở đây là ví dụ phổ biến của Prometheus naming từ HTTP server Timer; hãy xác minh exposition thực tế của ứng dụng trước khi dùng query. Cần xử lý trường hợp mẫu số bằng 0 và không có series.

## 7. Đối chiếu giữa môi trường

Production, staging, test và development thường có tải, tài nguyên và cấu hình khác nhau. So sánh raw metrics giữa chúng có thể dẫn đến kết luận sai.

Trước khi so sánh, ghi nhận:

- CPU/memory request và limit của container.
- Số instance và chiến lược autoscaling.
- JDK, framework, Micrometer và exporter versions.
- Database, cache, connection pool và dependency endpoint.
- Traffic volume, request mix, payload size và concurrency.
- Sampling, scrape interval, step/flush interval và retention.
- Feature flags hoặc cấu hình nghiệp vụ có ảnh hưởng thời gian xử lý.

Ví dụ, staging có p95 40 ms và production có p95 180 ms chưa chứng minh production code chậm hơn. Production có thể có payload lớn hơn, nhiều tenant hơn, dependency ở vùng khác hoặc tải cạnh tranh cao hơn.

### Chuẩn hóa theo workload

Khi có thể, so sánh các nhóm request tương đương:

- Cùng route hoặc operation.
- Cùng HTTP method và status/outcome.
- Cùng loại workload hoặc kích thước payload.
- Cùng khoảng thời gian và vùng địa lý.
- Cùng mức tải hoặc cùng throughput range.

Không gom mọi request vào một p95 nếu cơ cấu traffic giữa các môi trường khác nhau đáng kể. Một môi trường có nhiều request cache hit có thể có latency thấp hơn dù đường cache miss không thay đổi.

## 8. Rollout nhiều version và kiểm tra tương thích

Trong rolling deployment, dữ liệu của nhiều version cùng tồn tại. Hãy gắn version vào metrics từ lúc process bắt đầu để mỗi sample được phân loại nhất quán.

Quy trình rollout:

1. Xác nhận version hiện tại và version mới đều xuất cùng metric names hoặc có migration query.
2. So sánh common labels và metric units.
3. So sánh histogram boundaries và tag dimensions.
4. Deploy một phần traffic vào version mới.
5. So sánh throughput, latency, errors và saturation theo version.
6. Kiểm tra instance count và traffic share để tránh so sánh nhóm quá nhỏ.
7. Tăng traffic nếu các tín hiệu đạt tiêu chí release.
8. Sau rollout, bỏ query tương thích tạm thời khi dữ liệu version cũ đã hết retention.

Không thay đổi ý nghĩa của một metric name giữa các version. Nếu metric mới đo một khái niệm khác, dùng tên mới. Nếu chỉ đổi cách đặt tên nhưng semantics giữ nguyên, có thể duy trì cả hai trong một giai đoạn và chuẩn hóa ở dashboard/recording rule.

### Thay đổi tag schema

Thêm tag mới làm tăng số series và có thể khiến query cũ bỏ sót dữ liệu nếu đang group hoặc filter theo schema cố định. Đổi tag key, ví dụ từ env sang environment, có thể tạo hai nhóm series riêng.

Khi đổi schema:

- Ưu tiên thêm nhãn mới theo cách tương thích trước khi loại bỏ nhãn cũ.
- Không đổi tag value format giữa chừng nếu dashboard phụ thuộc giá trị.
- Cập nhật recording rules, alerts và dashboards.
- Theo dõi cardinality sau rollout.
- Ghi rõ mốc version bắt đầu schema mới.

## 9. Temporality và khoảng lấy mẫu phải tương thích

Không phải backend nào cũng biểu diễn counter và distribution theo cùng một cách:

| Cơ chế | Đặc điểm | Khi đối chiếu |
| --- | --- | --- |
| Prometheus scrape | Thu thập snapshot định kỳ; counter thường là cumulative | Dùng rate()/increase() và cùng scrape interval |
| Micrometer step registry | Có thể xuất thống kê theo cửa sổ step | Căn chỉnh step interval và thời điểm quan sát |
| OTLP cumulative temporality | Giá trị tích lũy từ điểm bắt đầu của series | Xử lý reset và resource identity |
| OTLP delta temporality | Giá trị chỉ cho khoảng thời gian vừa qua | Cộng các delta theo đúng cửa sổ, tránh coi như cumulative |
| StatsD aggregation | Agent có thể gom dữ liệu theo flush interval | Căn chỉnh flush interval và semantics từng metric type |

Không so sánh trực tiếp một delta sample với một cumulative counter. Exporter hoặc collector có thể chuyển đổi temporality, nhưng phải xác minh cấu hình và semantics sau chuyển đổi.

Scrape interval, step interval và flush interval cũng ảnh hưởng độ mịn của dữ liệu. Nếu staging scrape mỗi 15 giây còn production scrape mỗi 60 giây, các spike ngắn có thể xuất hiện khác nhau. Dùng cùng cửa sổ truy vấn và hiểu độ phân giải dữ liệu trước khi kết luận.

## 10. Gauge, max và dữ liệu theo thời điểm

Gauge thường biểu diễn trạng thái tại thời điểm đọc, ví dụ số connection active hoặc queue depth. Nó không có semantics tích lũy như Counter.

Khi so sánh gauge:

- Cùng đơn vị và cùng nguồn trạng thái.
- Cùng thời điểm hoặc cùng cửa sổ lấy mẫu.
- Cùng định nghĩa thời điểm cập nhật.
- Phân biệt giá trị hiện tại, trung bình và max trong một cửa sổ.

Timer max có thể được giữ theo cửa sổ hoặc implementation cụ thể của registry. Không giả định max của hai backend có cùng cửa sổ thống kê. Khi cần so sánh tail latency, histogram thường cung cấp semantics rõ ràng hơn.

Nếu một Gauge không có sample ở một thời điểm, đó không nhất thiết là giá trị 0. Có thể meter chưa được đăng ký, instance không scrape được hoặc dữ liệu đã stale.

## 11. Phân biệt zero, missing và stale series

Ba tình trạng này có ý nghĩa khác nhau:

- Zero: series tồn tại và giá trị được ghi nhận là 0.
- Missing: không có series trong kết quả query, có thể do meter chưa tạo, label không khớp hoặc không có sample.
- Stale: series từng tồn tại nhưng target hoặc meter không còn được thu thập; backend có thể đánh dấu stale theo cơ chế riêng.

Không thay missing bằng zero trong dashboard mà không có chủ đích. Nếu version mới không xuất metric do đổi tên, query có thể trả về rỗng; hiển thị 0 sẽ che giấu lỗi schema.

Khi query theo version, dùng inventory/deployment metrics để xác nhận version đó thực sự có instance đang chạy. Nếu có instance nhưng không có metric, kiểm tra instrumentation và exporter.

## 12. PromQL để đối chiếu nhiều chiều

Các ví dụ sau giả định Prometheus exposition có các tên và labels minh họa. Luôn xác minh tên thực tế tại /actuator/prometheus.

### Throughput theo version, bỏ qua instance

~~~promql
sum by (service, environment, version) (
  rate(orders_created_total[5m])
)
~~~

### Throughput từng instance

~~~promql
sum by (service, environment, version, instance) (
  rate(orders_created_total[5m])
)
~~~

### p95 theo version từ histogram

~~~promql
histogram_quantile(
  0.95,
  sum by (le, service, environment, version) (
    rate(business_checkout_duration_seconds_bucket[5m])
  )
)
~~~

### So sánh error rate theo môi trường

~~~promql
sum by (service, environment, version) (
  rate(http_server_requests_seconds_count{status=~"5.."}[5m])
)
/
sum by (service, environment, version) (
  rate(http_server_requests_seconds_count[5m])
)
~~~

### Số instance đang xuất dữ liệu

~~~promql
count by (service, environment, version) (
  up{job="order-service"}
)
~~~

Query up phụ thuộc cấu hình scrape job và labels của Prometheus. Nó cho biết target scrape có phản hồi, không chứng minh từng meter nghiệp vụ đang được tạo.

## 13. Tránh so sánh sai do tổng hợp nhãn

Aggregation phải giữ lại các chiều cần so sánh và bỏ các chiều không cần thiết.

| Mục tiêu | Giữ lại | Thường bỏ |
| --- | --- | --- |
| Toàn service theo version | service, environment, version | instance |
| So sánh instance trong một version | service, environment, version, instance | Không bỏ instance |
| So sánh region | service, environment, region | instance nếu cần tổng hợp vùng |
| So sánh route | service, environment, version, uri/route | instance nếu xem toàn service |

Nếu bỏ version khi tổng hợp, dữ liệu version cũ và mới sẽ bị trộn. Nếu giữ instance khi muốn p95 toàn service, query sẽ tạo p95 riêng từng instance thay vì p95 của toàn bộ traffic.

Với histogram, tổng hợp bucket trước khi tính quantile. Với counter, tính rate trước rồi mới tổng hợp để mỗi instance được xử lý reset đúng. Không lấy trung bình raw counter hoặc trung bình p95 của các instance để suy ra service-level value.

## 14. Kiểm soát cardinality của nhãn định danh

Nhãn service, environment, version và region thường có tập giá trị hữu hạn và phù hợp để phân tích. Nhãn instance có thể tăng theo autoscaling nhưng phản ánh target đang scrape; cần theo dõi số lượng series và retention.

Tránh các nhãn có giá trị thay đổi theo từng request hoặc bản ghi:

- user ID, customer ID, order ID.
- request ID, trace ID, span ID.
- URL thô có path parameter.
- exception message hoặc SQL query động.
- timestamp, UUID hoặc build UUID mới cho từng process.

Version label nên đại diện cho release có ý nghĩa vận hành, không phải chuỗi ngẫu nhiên thay đổi mỗi lần process restart. Nếu dùng commit SHA, hãy cân nhắc retention và số lượng release cùng tồn tại.

Mỗi nhãn bổ sung nhân số series theo số giá trị của nhãn đó. Ví dụ 4 environment × 5 version × 3 region × 20 instance đã tạo đến 1.200 tổ hợp cho mỗi metric/tag combination trước khi tính các tags nghiệp vụ khác.

## 15. Bảo mật khi đối chiếu giữa môi trường

Metrics từ production và non-production có thể chứa metadata về service topology, version, dependency, tải và lỗi. Chỉ cấp quyền truy cập dashboard/query theo vai trò.

Một số nguyên tắc:

- Không đưa token, password, email hoặc dữ liệu cá nhân vào tag/label.
- Không expose /actuator/prometheus công khai nếu endpoint chứa thông tin nội bộ.
- Dùng authentication/network policy cho scrape endpoint hoặc collector.
- Giới hạn quyền truy cập giữa môi trường nếu dữ liệu production cần tách biệt.
- Không gửi baggage hoặc high-cardinality attributes nhạy cảm sang hệ thống telemetry dùng chung.
- Không dùng metrics làm kênh truyền dữ liệu nghiệp vụ chi tiết.

Nếu dùng chung Prometheus/collector cho nhiều môi trường, labels phải phân biệt rõ environment và quyền truy cập phải được áp dụng ở lớp backend hoặc gateway hỗ trợ.

## 16. Kiểm thử metric contract trước khi release

Khi thay đổi code, dependency hoặc phiên bản Micrometer, nên kiểm tra metric contract ở cả lớp registry và lớp export:

1. Xác nhận meter name và type.
2. Xác nhận base unit.
3. Xác nhận tag keys và giá trị đại diện.
4. Xác nhận common tags service/environment/version.
5. Xác nhận histogram boundaries nếu dùng percentile/SLO.
6. Xác nhận tên exposition sau NamingConvention.
7. Xác nhận không có collision sau chuẩn hóa.
8. Xác nhận query/recording rule còn đọc được schema mới.

Ví dụ kiểm tra common tags trong registry:

~~~java
Counter counter = registry.counter(
    "orders.created",
    "channel", "web"
);

assertThat(counter.getId().getTag("service"))
    .isEqualTo("order-service");
assertThat(counter.getId().getTag("environment"))
    .isEqualTo("staging");
assertThat(counter.getId().getTag("version"))
    .isEqualTo("2.9.0");
~~~

Với Prometheus, kiểm tra exposition:

~~~java
String exposition = prometheusRegistry.scrape();

assertThat(exposition)
    .contains("orders_created_total")
    .contains("service=\"order-service\"")
    .contains("environment=\"staging\"")
    .contains("version=\"2.9.0\"");
~~~

Test nên dùng giá trị fixture rõ ràng và kiểm tra đúng registry/exporter đang chạy. Một test SimpleMeterRegistry không xác minh Prometheus naming hoặc bucket exposition.

## 17. Quy trình đối chiếu khi phát hành phiên bản mới

Khi cần xác định version mới có làm thay đổi chất lượng service:

1. Chọn cùng service, environment và khoảng thời gian so sánh.
2. Xác nhận hai version đang có instance healthy và nhận traffic.
3. Kiểm tra metric names, units, tags và histogram schema tương thích.
4. So sánh throughput theo version bằng rate/increase.
5. So sánh p50/p95/p99 từ histogram tương thích.
6. So sánh error rate và outcome distribution.
7. Kiểm tra CPU, memory, thread pool, connection pool và queue depth.
8. Chuẩn hóa theo route/workload mix và traffic volume.
9. Kiểm tra scrape gap, counter reset, stale series và sampling.
10. Chỉ kết luận khi có đủ mẫu và nhóm traffic tương đương.
11. Ghi nhận thay đổi schema nếu version mới đổi semantics.

Nếu version mới nhận quá ít traffic hoặc chỉ chạy trên một instance, percentile có thể không ổn định. Hãy xem sample count và traffic share trước khi kết luận.

## 18. Checklist

- [ ] Mỗi metric có tên, type, unit và semantics được định nghĩa.
- [ ] Service identity nhất quán giữa instance.
- [ ] Environment và version được gắn từ nguồn cấu hình đáng tin cậy.
- [ ] Instance identity được quản lý nhất quán bởi scrape target hoặc resource attribute.
- [ ] Không có request ID/user ID/order ID trong metric labels.
- [ ] Counter được so sánh bằng rate/increase, có xét reset.
- [ ] Histogram buckets tương thích trước khi tổng hợp quantile.
- [ ] Percentile được tính từ histogram tổng hợp, không lấy trung bình percentile instance.
- [ ] Temporality, scrape interval, step/flush interval đã được đối chiếu.
- [ ] Workload mix và số instance được xem xét khi so sánh môi trường/version.
- [ ] Missing, zero và stale series được phân biệt.
- [ ] Dashboard, alert và recording rules đã được cập nhật khi schema thay đổi.
- [ ] Endpoint và dữ liệu metrics được bảo vệ theo môi trường.
- [ ] Integration test xác nhận metric contract và exposition.

Đối chiếu metrics có ý nghĩa khi mọi nhóm dữ liệu cùng nói về một đại lượng, cùng đơn vị và cùng quy ước nhãn. Hãy giữ định danh service, instance, environment và version rõ ràng; so sánh counter bằng rate, percentile bằng histogram tương thích và luôn xét workload cùng khoảng lấy mẫu. Khi metric schema được quản lý như một hợp đồng qua các lần release, dashboard mới có thể so sánh instance, version và môi trường mà không trộn những dữ liệu khác semantics.
