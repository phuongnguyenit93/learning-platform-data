# Cấu hình phân vị, histogram và ngưỡng cho từng tên meter

Spring Boot cho phép cấu hình thống kê phân phối của Micrometer theo tên meter ngay trong `application.yml` hoặc `application.properties`. Nhờ vậy, ứng dụng có thể bật histogram cho những Timer cần tính p95 trên nhiều instance, chọn một vài percentile cho dashboard, hoặc khai báo các ngưỡng SLO cho một nhóm meter cụ thể mà không phải sửa từng lời gọi builder.

Các thuộc tính này được Spring Boot áp dụng thông qua **PropertiesMeterFilter**. Quy tắc quan trọng là cấu hình được ghép theo **tiền tố của tên meter**: tên meter phải bắt đầu bằng khóa cấu hình, khóa khớp dài nhất được ưu tiên và khóa đặc biệt `all` có thể dùng làm mặc định chung. Cấu hình per-meter không tạo meter mới; nó chỉ điều chỉnh cách thống kê cho những meter được đăng ký với tên phù hợp.

## 1. Vì sao cần cấu hình theo từng tên meter?

Timer và DistributionSummary có thể ghi nhận count, tổng giá trị và thống kê phân phối. Nhưng không phải meter nào cũng cần cùng một mức chi tiết.

Ví dụ:

- `http.server.requests` cần histogram để tính p95/p99 sau khi tổng hợp dữ liệu từ nhiều instance.
- `orders.checkout.duration` cần các bucket tại 100 ms, 300 ms và 1 giây để theo dõi ngưỡng xử lý.
- `message.payload.size` cần các ngưỡng theo byte để biết bao nhiêu payload nằm trong giới hạn.
- Một Timer nội bộ chỉ cần count và total time, không cần thêm percentile hoặc histogram.

Nếu bật histogram và percentile cho mọi meter, ứng dụng có thể tốn thêm bộ nhớ cho cấu trúc phân phối và backend phải lưu nhiều chuỗi thời gian hơn. Cấu hình theo tên giúp áp dụng chi tiết ở nơi có câu hỏi vận hành cụ thể.

Spring Boot hỗ trợ các nhóm thuộc tính sau:

| Thuộc tính | Mục đích |
|---|---|
| `percentiles` | Tính và công bố các percentile ở phía ứng dụng |
| `percentiles-histogram` | Công bố histogram để backend tính percentile có thể tổng hợp |
| `slo` | Tạo bucket tại các ngưỡng Service Level Objective đã chọn |
| `minimum-expected-value` | Giới hạn cận dưới của miền giá trị kỳ vọng |
| `maximum-expected-value` | Giới hạn cận trên của miền giá trị kỳ vọng |
| `expiry` | Thời gian tích lũy của một cửa sổ thống kê |
| `buffer-length` | Số cửa sổ được giữ trong ring buffer |

Các thuộc tính này tác động chủ yếu đến Timer, LongTaskTimer và DistributionSummary. Một Counter thông thường không có phân phối thời lượng hoặc histogram để cấu hình theo cách tương tự.

## 2. Quy tắc khớp tên meter

Per-meter properties áp dụng cho các meter ID có tên bắt đầu bằng khóa cấu hình. Khóa không phải biểu thức chính quy và cũng không phải tên tag.

Giả sử ứng dụng đăng ký các meter:

- `http.server.requests`
- `http.server.requests.internal`
- `http.client.requests`
- `orders.checkout.duration`

Cấu hình với khóa `http.server.requests` sẽ áp dụng cho meter có tên bắt đầu bằng tiền tố đó, bao gồm cả `http.server.requests.internal`. Nó không áp dụng cho `http.client.requests`.

Nếu nhiều khóa cùng khớp một tên meter, **khóa có tiền tố dài nhất thắng**. Ví dụ:

~~~yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        all: false
        http.server.requests: true
        http.server.requests.internal: false
~~~

Trong ví dụ này:

- Mặc định mọi meter không xuất percentile histogram.
- Các meter bắt đầu bằng `http.server.requests` bật histogram.
- Các meter bắt đầu bằng `http.server.requests.internal` khớp khóa dài hơn nên tắt histogram.

Khóa `all` là cách đặt cấu hình chung cho mọi meter. Có thể dùng nó làm mặc định rồi ghi đè một số nhóm meter bằng các tiền tố cụ thể. Quy tắc khớp tiền tố và ưu tiên khóa dài nhất cũng áp dụng cho các thuộc tính per-meter khác như `percentiles`, `slo` và expected value.

Lưu ý: tiền tố là tên meter trong mã ứng dụng, ví dụ `http.server.requests`. Không dùng tên đã được exporter đổi theo NamingConvention, chẳng hạn `http_server_requests_seconds` của Prometheus. Tên meter trong `/actuator/metrics` cũng là tên gốc trước khi chuẩn hóa cho backend.

## 3. Ví dụ cấu hình đầy đủ trong application.yml

Ví dụ sau cấu hình histogram, percentile, SLO và miền giá trị cho một số meter:

~~~yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        all: false
        http.server.requests: true
        orders.checkout.duration: true

      percentiles:
        http.server.requests:
          - 0.50
          - 0.95
          - 0.99

      slo:
        http.server.requests:
          - 100ms
          - 300ms
          - 1s
        orders.checkout.duration:
          - 100ms
          - 300ms
          - 1s

      minimum-expected-value:
        http.server.requests: 1ms
        orders.checkout.duration: 1ms

      maximum-expected-value:
        http.server.requests: 10s
        orders.checkout.duration: 10s

      expiry:
        http.server.requests: 1m
        orders.checkout.duration: 1m

      buffer-length:
        http.server.requests: 3
        orders.checkout.duration: 3
~~~

Cấu hình có ý nghĩa như sau:

- Chỉ hai nhóm meter được bật percentile histogram.
- `http.server.requests` có thêm percentile p50, p95 và p99 được tính ở phía ứng dụng.
- Cả hai Timer có bucket tại 100 ms, 300 ms và 1 giây.
- Miền giá trị kỳ vọng nằm từ 1 ms đến 10 giây.
- Các thống kê dạng time-window dùng cửa sổ một phút và giữ ba cửa sổ.

Các khóa có dấu chấm trong YAML là tên meter. Có thể dùng dạng `application.properties` tương đương:

~~~properties
management.metrics.distribution.percentiles-histogram.all=false
management.metrics.distribution.percentiles-histogram.http.server.requests=true
management.metrics.distribution.percentiles-histogram.orders.checkout.duration=true
management.metrics.distribution.percentiles.http.server.requests=0.50,0.95,0.99
management.metrics.distribution.slo.http.server.requests=100ms,300ms,1s
management.metrics.distribution.minimum-expected-value.http.server.requests=1ms
management.metrics.distribution.maximum-expected-value.http.server.requests=10s
management.metrics.distribution.expiry.http.server.requests=1m
management.metrics.distribution.buffer-length.http.server.requests=3
~~~

Tên property và khả năng binding cần được kiểm tra theo phiên bản Spring Boot mà dự án đang dùng. Các nhóm per-meter này có trong tài liệu thuộc các nhánh Spring Boot 3.x và 4.x hiện hành.

## 4. Phân biệt percentiles và percentile histogram

Hai thuộc tính thường bị nhầm lẫn vì cùng liên quan đến p50, p95 hoặc p99, nhưng chúng tạo ra hai dạng dữ liệu khác nhau.

### Percentile phía ứng dụng

Cấu hình `percentiles` yêu cầu Micrometer tính các phân vị trong ứng dụng và công bố kết quả:

~~~yaml
management:
  metrics:
    distribution:
      percentiles:
        orders.checkout.duration:
          - 0.50
          - 0.95
          - 0.99
~~~

Cách này hữu ích khi backend không hỗ trợ tính percentile từ histogram hoặc dashboard chỉ cần một tập quantile cố định. Tuy nhiên, percentile được tính riêng cho từng meter ID, tức từng tên và tổ hợp tag. Không thể lấy trung bình p95 của các instance để suy ra p95 chính xác của toàn dịch vụ.

### Histogram phía backend

Cấu hình `percentiles-histogram` yêu cầu Micrometer công bố các bucket để backend tính percentile:

~~~yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        orders.checkout.duration: true
~~~

Histogram phù hợp khi backend có thể tổng hợp bucket giữa nhiều instance hoặc nhiều chiều tag trước khi tính percentile. Với Prometheus, truy vấn thường dùng `histogram_quantile` trên các bucket đã được cộng gộp.

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(orders_checkout_duration_seconds_bucket[5m])
  )
)
~~~

Tên metric và đơn vị trong truy vấn là ví dụ. Tên thực tế phụ thuộc meter name, base unit và NamingConvention của registry.

| Tiêu chí | `percentiles` | `percentiles-histogram` |
|---|---|---|
| Nơi tính percentile | Trong ứng dụng | Trong backend |
| Dữ liệu công bố | Giá trị p50/p95/p99 đã tính | Các bucket histogram |
| Tổng hợp nhiều instance | Không thể gộp percentile riêng một cách chính xác | Có thể cộng bucket rồi tính percentile |
| Linh hoạt truy vấn | Chỉ các quantile đã cấu hình | Có thể tính các quantile khác từ histogram |
| Chi phí | Các chuỗi percentile và bộ đệm thống kê | Nhiều bucket, bộ nhớ và chuỗi backend |

Có thể bật cả hai, nhưng chỉ nên làm vậy khi có nhu cầu riêng cho cả dashboard percentile cố định lẫn truy vấn histogram. Nếu backend hỗ trợ histogram tổng hợp, histogram thường là lựa chọn linh hoạt hơn.

## 5. Cấu hình ngưỡng SLO bằng slo

Thuộc tính `slo` khai báo các ranh giới bucket theo mục tiêu vận hành. Với Timer, giá trị là thời lượng; với DistributionSummary, giá trị là số theo đơn vị mà ứng dụng ghi nhận.

Ví dụ Timer:

~~~yaml
management:
  metrics:
    distribution:
      slo:
        orders.checkout.duration:
          - 100ms
          - 300ms
          - 1s
~~~

Các bucket này giúp trả lời những câu hỏi như có bao nhiêu lần checkout hoàn tất trong 300 ms. Histogram SLO là histogram tích lũy tại những boundary được chỉ định. Khi dùng Prometheus, bucket có giới hạn 300 ms chứa số quan sát không vượt quá giới hạn đó.

Ví dụ DistributionSummary đo kích thước payload bằng byte:

~~~yaml
management:
  metrics:
    distribution:
      slo:
        message.payload.size:
          - 1024
          - 16384
          - 65536
~~~

Các giá trị trên tương ứng 1 KiB, 16 KiB và 64 KiB nếu mã ứng dụng ghi số byte. Spring Boot nhận giá trị DistributionSummary dưới dạng số; nó không tự biết đơn vị nghiệp vụ nếu ứng dụng không mô tả rõ meter.

SLO bucket cung cấp dữ liệu để tính tỷ lệ đáp ứng ngưỡng. Chúng không tự tạo cảnh báo, không tự đặt mục tiêu phần trăm thành công và cũng không tự tính error budget. Hệ thống truy vấn và cảnh báo vẫn phải định nghĩa mẫu số, cửa sổ đánh giá và tỷ lệ mục tiêu.

Ví dụ PromQL minh họa tỷ lệ request có thời lượng không vượt quá 300 ms:

~~~promql
sum(rate(orders_checkout_duration_seconds_bucket{le="0.3"}[5m]))
/
sum(rate(orders_checkout_duration_seconds_count[5m]))
~~~

Cần xác minh tên metric, nhãn bucket và đơn vị xuất thực tế trước khi sử dụng truy vấn. Với Timer có base unit là giây, 300 ms tương ứng 0,3 giây.

## 6. Giới hạn miền giá trị bằng minimum và maximum

Khi bật percentile histogram, Micrometer cần biết miền giá trị cần quan sát để chọn bucket phù hợp. Hai thuộc tính sau giới hạn miền đó:

- `minimum-expected-value`: cận dưới của giá trị kỳ vọng.
- `maximum-expected-value`: cận trên của giá trị kỳ vọng.

Ví dụ cho Timer:

~~~yaml
management:
  metrics:
    distribution:
      minimum-expected-value:
        database.query.duration: 1ms
      maximum-expected-value:
        database.query.duration: 5s
      percentiles-histogram:
        database.query.duration: true
~~~

Với Timer và LongTaskTimer, giá trị có thể được viết dưới dạng Duration. Nếu bỏ đơn vị, Spring Boot diễn giải Duration theo millisecond. Nên ghi rõ đơn vị để cấu hình dễ đọc và tránh sai lệch.

Với DistributionSummary, giá trị là số thực theo đại lượng mà meter ghi nhận:

~~~yaml
management:
  metrics:
    distribution:
      minimum-expected-value:
        message.payload.size: 1
      maximum-expected-value:
        message.payload.size: 1048576
      percentiles-histogram:
        message.payload.size: true
~~~

Trong ví dụ này, miền kỳ vọng là 1 đến 1.048.576 byte nếu ứng dụng ghi byte. Đừng dùng `1ms` hoặc `5s` cho DistributionSummary chỉ vì tên property giống cấu hình Timer.

Giới hạn miền giúp giảm số bucket histogram và chi phí bộ nhớ. Nếu cận trên quá thấp, các giá trị hợp lệ lớn hơn vẫn có thể xuất hiện nhưng histogram không còn độ chi tiết như mong đợi ở vùng đó. Nếu cận dưới hoặc cận trên không phản ánh dữ liệu thực tế, phân tích phân phối sẽ kém hữu ích. Hãy dựa vào dữ liệu vận hành và giới hạn nghiệp vụ để chọn khoảng.

## 7. Điều chỉnh expiry và buffer-length

Một số thống kê phân phối của Micrometer là thống kê theo cửa sổ thời gian. Hai thuộc tính điều khiển ring buffer:

- `expiry`: thời gian của mỗi cửa sổ con.
- `buffer-length`: số cửa sổ con được giữ.

Ví dụ:

~~~yaml
management:
  metrics:
    distribution:
      expiry:
        orders.checkout.duration: 1m
      buffer-length:
        orders.checkout.duration: 3
~~~

Với expiry một phút và buffer length bằng ba, phạm vi lưu giữ của các thống kê time-window xấp xỉ ba phút. Các percentile hoặc max theo cửa sổ phản ánh dữ liệu gần đây, không phải lịch sử vô hạn của toàn bộ vòng đời ứng dụng.

Cửa sổ ngắn giúp phản ứng nhanh với thay đổi nhưng có thể dao động mạnh khi số mẫu ít. Cửa sổ dài làm số liệu ổn định hơn nhưng có thể phản ứng chậm khi độ trễ thay đổi đột ngột.

Giá trị mặc định của expiry có thể phụ thuộc step của registry; buffer length mặc định của các cấu hình Micrometer phổ biến là ba. Hãy xác nhận registry và phiên bản đang sử dụng trước khi dựa vào mặc định. Cũng cần phân biệt cửa sổ thống kê trong ứng dụng với cửa sổ truy vấn ở backend, ví dụ Prometheus `rate(...[5m])`.

## 8. Cấu hình theo từng loại meter

Các meter khác nhau cần giá trị ngưỡng và đơn vị khác nhau.

| Meter | Cấu hình phù hợp | Ví dụ |
|---|---|---|
| Timer | Percentile, histogram, SLO theo Duration, expected range theo Duration | `orders.checkout.duration` |
| LongTaskTimer | Histogram/percentile và ngưỡng thời lượng dài | `jobs.reconciliation.active` |
| DistributionSummary | Percentile, histogram, SLO theo số và expected range theo số | `message.payload.size` |
| Counter | Thông thường không dùng các cấu hình phân phối này | `orders.created` |
| Gauge | Thông thường không dùng histogram phân phối của Timer/Summary | `jobs.queue.size` |

Ví dụ khai báo meter trong Java:

~~~java
Timer checkoutTimer = Timer.builder("orders.checkout.duration")
    .description("Thời gian xử lý checkout")
    .register(meterRegistry);

DistributionSummary payloadSize = DistributionSummary
    .builder("message.payload.size")
    .description("Kích thước payload")
    .baseUnit("bytes")
    .register(meterRegistry);
~~~

Các property trong `application.yml` được áp dụng khi những meter này được đăng ký vào registry Spring quản lý. Nếu meter không được tạo, cấu hình per-meter không tự tạo meter đó.

Không nên thêm `publishPercentiles`, `publishPercentileHistogram` hoặc `serviceLevelObjectives` trong builder chỉ để lặp lại cấu hình đã đặt trong Spring Boot properties. Hãy chọn một nơi làm nguồn cấu hình chính để tránh khó hiểu khi nhiều lớp cùng tùy chỉnh distribution statistics.

## 9. Cấu hình theo tên không phải theo tag

Per-meter properties chọn meter theo tiền tố tên. Chúng không chọn riêng một tổ hợp tag.

Ví dụ, cấu hình:

~~~yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
~~~

áp dụng cho mọi meter có tên bắt đầu bằng `http.server.requests`, bất kể tag `method`, `uri`, `status` hoặc `outcome` có giá trị nào. Nếu cần bật histogram chỉ cho một nhóm tag cụ thể, có thể dùng MeterFilter và kiểm tra Meter.Id cùng tags trong cấu hình Java.

Dù chọn cách nào, hãy kiểm soát cardinality. Histogram nhân số bucket với từng tổ hợp tag và từng instance. Không dùng request ID, user ID, order ID hoặc URL chứa định danh làm tag.

Một tên meter có thể được xuất thành nhiều chuỗi thời gian do tag. Bật histogram cho meter có nhiều tổ hợp tag sẽ làm số chuỗi tăng đáng kể. Cấu hình theo tên giúp giới hạn phạm vi meter; nó không tự giới hạn số giá trị tag.

## 10. Kiểm tra tên meter và cấu hình đã áp dụng

Có thể dùng Actuator metrics endpoint để xác nhận meter tồn tại:

~~~text
GET /actuator/metrics/http.server.requests
GET /actuator/metrics/orders.checkout.duration
~~~

Endpoint này cần được expose theo cấu hình Actuator. Tên selector là tên meter trong mã ứng dụng, không phải tên đã chuẩn hóa cho backend. Có thể thêm query parameter `tag=KEY:VALUE` để lọc một tổ hợp tag.

Metrics endpoint hữu ích để kiểm tra meter và measurements cơ bản. Để xác minh histogram bucket hoặc SLO bucket thực sự được xuất, hãy kiểm tra endpoint/exporter của registry hoặc dữ liệu trong backend. Ví dụ, với Prometheus có thể xem `/actuator/prometheus` và tìm chuỗi `_bucket`, `_count`, `_sum` theo tên đã chuẩn hóa.

Nếu không thấy histogram, kiểm tra lần lượt:

1. Meter đã được đăng ký và tên trong cấu hình có khớp tiền tố hay chưa.
2. Histogram property có được bật cho đúng meter hay bị khóa cụ thể dài hơn ghi đè.
3. Registry/backend có hỗ trợ xuất histogram hay không.
4. Meter có bị MeterFilter khác từ chối hoặc thay đổi cấu hình hay không.
5. Có đang xem tên metric đã chuẩn hóa thay vì tên gốc khi gọi Actuator metrics endpoint hay không.

## 11. Kiểm thử cấu hình bằng Spring Boot

Một kiểm thử tích hợp có thể khởi động ApplicationContext với per-meter properties rồi kiểm tra snapshot của Timer:

~~~java
@SpringBootTest(properties = {
    "management.metrics.distribution.percentiles-histogram.orders.checkout.duration=true",
    "management.metrics.distribution.slo.orders.checkout.duration=100ms,300ms"
})
class DistributionPropertiesTest {

    @Autowired
    MeterRegistry registry;

    @Test
    void appliesHistogramConfigurationToNamedTimer() {
        Timer timer = Timer.builder("orders.checkout.duration")
            .register(registry);

        timer.record(Duration.ofMillis(80));
        timer.record(Duration.ofMillis(250));
        timer.record(Duration.ofMillis(700));

        HistogramSnapshot snapshot = timer.takeSnapshot();

        assertEquals(3, timer.count());
        assertTrue(snapshot.histogramCounts().length > 0);
    }
}
~~~

Kiểm thử dùng đúng tên meter đã khai báo trong properties. Nó xác nhận Timer nhận được dữ liệu và snapshot có bucket. Tùy registry, cách biểu diễn snapshot và histogram có thể khác; nếu cần kiểm chứng chính xác các boundary được xuất, hãy kiểm tra payload của registry đích hoặc dùng kiểm thử tích hợp exporter.

Có thể bổ sung các trường hợp:

- Một meter có tên không khớp tiền tố không nhận cấu hình đó.
- Tiền tố cụ thể hơn ghi đè tiền tố tổng quát.
- `all` áp dụng làm cấu hình chung.
- Timer nhận SLO theo Duration.
- DistributionSummary nhận SLO theo giá trị số.
- Thay đổi expiry và buffer length không làm thay đổi count tích lũy cơ bản.
- MeterFilter tùy chỉnh không vô tình ghi đè cấu hình dự kiến.

## 12. Phân biệt properties, MeterFilter và builder

Spring Boot cung cấp ba nơi thường dùng để cấu hình meter:

| Cách cấu hình | Phạm vi phù hợp |
|---|---|
| Per-meter properties | Chọn theo tiền tố tên meter, thuận tiện cho cấu hình môi trường |
| MeterFilter | Logic chọn lọc nâng cao, ví dụ dựa vào tag hoặc điều kiện tùy chỉnh |
| Meter builder | Cấu hình ngay tại nơi tạo meter, phù hợp khi cấu hình thuộc về instrumentation cụ thể |

Properties phù hợp khi đội vận hành muốn điều chỉnh percentile hoặc SLO mà không sửa mã nguồn. MeterFilter phù hợp khi quy tắc phụ thuộc tag hoặc cần xử lý có điều kiện. Builder phù hợp khi meter tự mang một cấu hình cố định theo thiết kế component.

Spring Boot tự động áp dụng các MeterFilter bean cho registry được quản lý. Khi sử dụng Spring Boot, hãy inject MeterRegistry do Spring quản lý thay vì đăng ký meter qua global static registry nếu muốn các customizer và filter của ứng dụng có hiệu lực.

## 13. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng tên exporter thay cho tên meter trong property | Cấu hình không khớp | Dùng tên gốc trong mã Java |
| Nghĩ khóa cấu hình là tên chính xác tuyệt đối | Bật cấu hình cho cả meter có tên bắt đầu bằng tiền tố đó | Thiết kế tiền tố có chủ đích |
| Không biết khóa dài nhất thắng | Một cấu hình cụ thể âm thầm ghi đè cấu hình chung | Kiểm tra toàn bộ các tiền tố đang khớp |
| Bật histogram cho `all` | Tăng bộ nhớ và số chuỗi không cần thiết | Chỉ bật cho meter cần phân tích phân phối |
| Dùng percentiles khi cần tổng hợp nhiều instance | Không thể gộp percentile phía ứng dụng chính xác | Dùng percentile histogram |
| Nhầm SLO bucket là cảnh báo hoàn chỉnh | Không có tỷ lệ mục tiêu hoặc error budget | Viết truy vấn và chính sách cảnh báo riêng |
| Dùng Duration cho DistributionSummary | Sai đơn vị hoặc lỗi binding | Dùng giá trị số theo đơn vị đã chọn |
| Đặt expected range quá rộng | Tăng số bucket và chi phí | Chọn miền giá trị dựa trên dữ liệu thực tế |
| Đặt expected range quá hẹp | Thiếu độ chi tiết ở vùng quan trọng | Kiểm tra cả giá trị lớn/nhỏ hợp lệ |
| Bật histogram cho meter có tag cardinality cao | Số chuỗi backend tăng mạnh | Giới hạn tag và phạm vi meter |
| Cấu hình properties nhưng meter chưa được tạo | Không có dữ liệu để xuất | Đăng ký meter và xác minh qua Actuator |

## 14. Checklist triển khai

- [ ] Xác định đúng tên meter được dùng trong mã ứng dụng.
- [ ] Dùng tiền tố có chủ đích và hiểu quy tắc longest match wins.
- [ ] Dùng `all` làm mặc định chỉ khi thực sự cần.
- [ ] Chọn percentile phía ứng dụng hoặc histogram backend theo khả năng tổng hợp.
- [ ] Khai báo SLO boundary theo câu hỏi vận hành cần trả lời.
- [ ] Dùng Duration cho Timer/LongTaskTimer và giá trị số cho DistributionSummary.
- [ ] Giới hạn minimum/maximum expected value theo miền dữ liệu hợp lệ.
- [ ] Chọn expiry và buffer length theo cửa sổ quan sát.
- [ ] Ước lượng bộ nhớ và số chuỗi khi bật histogram.
- [ ] Kiểm soát tag cardinality.
- [ ] Xác minh meter qua Actuator metrics endpoint.
- [ ] Kiểm tra bucket và percentile ở exporter/backend đích.
- [ ] Kiểm thử các trường hợp prefix tổng quát và prefix cụ thể ghi đè nhau.

Spring Boot per-meter distribution properties cho phép điều chỉnh thống kê theo tên meter mà không phải lặp cấu hình trong từng builder. Hãy chọn percentile, histogram và SLO dựa trên câu hỏi cần trả lời; dùng tiền tố tên rõ ràng, hiểu quy tắc ưu tiên khóa dài nhất và giới hạn miền giá trị để kiểm soát chi phí. Cuối cùng, xác minh meter và bucket thực tế tại registry/backend, vì cấu hình chỉ có tác dụng khi meter tương ứng được đăng ký và exporter hỗ trợ dạng dữ liệu đó.

## Tài liệu tham khảo

- [Spring Boot Metrics — Per-meter Properties](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html)
- [Micrometer Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html)
- [Micrometer Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer Distribution Summaries](https://docs.micrometer.io/micrometer/reference/concepts/distribution-summaries.html)

