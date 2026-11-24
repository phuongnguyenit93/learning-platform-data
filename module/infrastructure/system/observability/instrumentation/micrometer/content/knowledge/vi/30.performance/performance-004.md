# Chi phí histogram, số bucket và phân vị tính tại ứng dụng

Histogram và percentile giúp hiểu phân phối độ trễ hoặc kích thước dữ liệu, đặc biệt ở phần đuôi như p95 và p99. Nhưng mỗi cách thu thập có chi phí riêng: histogram tạo nhiều bucket và time series; percentile tính tại ứng dụng cần cấu trúc dữ liệu để xấp xỉ phân phối và xuất thêm series cho từng percentile. Khi bật chúng cho hàng trăm meter ID, chi phí bộ nhớ, CPU, scrape, ingest và lưu trữ có thể tăng đáng kể.

Micrometer cung cấp hai hướng chính để quan sát phân vị của Timer và DistributionSummary: percentile histogram để backend tính phân vị từ bucket, và client-side percentiles để ứng dụng tính trước rồi xuất giá trị. Chọn đúng hướng, giới hạn miền giá trị và chỉ bật cho meter thực sự cần sẽ giúp cân bằng độ chính xác, khả năng tổng hợp và chi phí.

## 1. Histogram và percentile giải quyết câu hỏi gì?

Một Timer hoặc DistributionSummary cơ bản thường cung cấp count, tổng giá trị và max. Các số đo này hữu ích nhưng chưa mô tả được phân phối:

- Count cho biết có bao nhiêu lần ghi nhận.
- Sum cho biết tổng thời gian hoặc tổng giá trị.
- Max cho biết giá trị lớn nhất trong cửa sổ thống kê tương ứng.
- Percentile cho biết một tỷ lệ quan sát nằm dưới một ngưỡng xấp xỉ.
- Histogram cho biết số quan sát rơi vào các khoảng giá trị.

Ví dụ, p95 = 250 ms có nghĩa khoảng 95% lần gọi có thời gian không vượt quá xấp xỉ 250 ms trong tập dữ liệu và cửa sổ được xét. Nó không có nghĩa mọi request mất 250 ms, cũng không có nghĩa 5% request còn lại đều chậm như nhau.

Histogram chia miền giá trị thành các bucket có ranh giới xác định. Khi ghi một quan sát, bucket tương ứng được cập nhật. Backend có thể dùng các bucket đó để xấp xỉ percentile hoặc đếm số quan sát nằm trong giới hạn SLO.

## 2. Hai cách công bố percentile trong Micrometer

Micrometer hỗ trợ hai cách:

| Cách | Nơi tính percentile | Dữ liệu xuất | Có thể tổng hợp giữa instance/tag? |
| --- | --- | --- | --- |
| Percentile histogram | Backend tính từ bucket. | Nhiều bucket, cùng count/sum và dữ liệu liên quan. | Có thể tổng hợp histogram rồi tính percentile xấp xỉ. |
| Client-side percentiles | Ứng dụng tính từ dữ liệu cục bộ của từng Meter ID. | Một series cho mỗi percentile được yêu cầu. | Không thể cộng các percentile riêng lẻ để tạo percentile toàn hệ thống. |

Meter ID là tổ hợp tên meter và toàn bộ tag. Vì vậy, client-side p95 của route A trên instance 1 và p95 của route A trên instance 2 là hai kết quả riêng. Không thể lấy trung bình hai p95 đó để suy ra p95 toàn service.

Với Prometheus hoặc Atlas, histogram thường là lựa chọn phù hợp hơn khi cần tổng hợp qua nhiều instance hoặc dimensions. Backend dùng PromQL histogram_quantile hoặc phép tính percentile tương ứng để tính phân vị từ bucket.

Client-side percentiles vẫn hữu ích khi backend không hỗ trợ tính percentile từ histogram. Khi đó, ứng dụng xuất sẵn một số phân vị, nhưng dashboard phải giữ chúng ở đúng Meter ID và không gộp theo các chiều khác.

publishPercentileHistogram chỉ có tác dụng với registry/backend hỗ trợ percentile aggregation từ histogram. Nếu backend không hỗ trợ, Micrometer không xuất percentile histogram theo cấu hình này. Hãy kiểm tra khả năng của registry đang dùng trước khi bật.

## 3. Cấu hình hai cách trong Timer

Ví dụ bật cả hai cách để minh họa API:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.time.Duration;

Timer requestTimer = Timer.builder("checkout.request")
        .description("Checkout request duration")
        .publishPercentiles(0.50, 0.95, 0.99)
        .publishPercentileHistogram()
        .serviceLevelObjectives(
                Duration.ofMillis(100),
                Duration.ofMillis(300),
                Duration.ofSeconds(1))
        .minimumExpectedValue(Duration.ofMillis(1))
        .maximumExpectedValue(Duration.ofSeconds(5))
        .register(registry);

requestTimer.record(() -> checkoutService.process());
~~~

Trong triển khai thực tế, không nên bật cả client-side percentiles và percentile histogram một cách mặc định. Với backend hỗ trợ histogram aggregation, histogram thường đã cung cấp dữ liệu để tính percentile và có thể tổng hợp qua instance. Client-side percentile khi đó thường dư thừa, làm tăng series và tiêu thụ thêm bộ nhớ.

Nếu chỉ cần percentile ở từng instance và backend không hỗ trợ histogram query, có thể bỏ publishPercentileHistogram và chỉ dùng publishPercentiles. Nếu cần SLO bucket nhưng không cần percentile histogram đầy đủ, có thể chỉ cấu hình serviceLevelObjectives.

## 4. Số bucket được tạo như thế nào?

Với percentile histogram, Micrometer dùng một tập ranh giới bucket được chọn sẵn. Tài liệu Micrometer hiện hành mô tả bộ sinh có 276 ranh giới tiềm năng. Chỉ những bucket nằm trong khoảng minimumExpectedValue đến maximumExpectedValue được đưa vào histogram công bố.

Hai giới hạn này có hai tác động:

- Giới hạn số bucket được gửi đến backend.
- Giới hạn miền giá trị mà cấu trúc histogram nội bộ cần hỗ trợ, ảnh hưởng đến bộ nhớ và độ chính xác.

Không nên đặt miền quá rộng nếu nghiệp vụ chỉ ghi nhận giá trị trong một khoảng hẹp. Ngược lại, đặt maximumExpectedValue quá thấp so với dữ liệu thực tế có thể khiến phân phối ở vùng đuôi không còn được mô tả đủ tốt.

Timer và DistributionSummary có miền giá trị khác nhau:

- Timer ghi thời lượng và dùng Duration cho các cấu hình expected value.
- DistributionSummary ghi số liệu không phải thời gian, chẳng hạn payload size, số item hoặc tỷ lệ đã scale; expected value dùng cùng đơn vị với giá trị được record.

Đặc biệt, DistributionSummary mặc định không có min/max expected value như Timer. Nếu bật percentile histogram cho DistributionSummary mà không đặt giới hạn, Micrometer có thể công bố toàn bộ 276 bucket được chọn sẵn. Hãy luôn giới hạn miền giá trị cho summary khi có chủ đích bật percentile histogram.

## 5. SLO bucket và percentile histogram khác nhau

SLO bucket là những ranh giới do đội phát triển lựa chọn theo mục tiêu vận hành. Ví dụ, API cần hoàn thành trong 100 ms, 300 ms hoặc 1 giây. Percentile histogram dùng một tập bucket rộng hơn để backend xấp xỉ phân phối và percentile.

| Cấu hình | Kết quả |
| --- | --- |
| Chỉ serviceLevelObjectives | Histogram chỉ cần các ranh giới SLO được khai báo. |
| Chỉ publishPercentileHistogram | Micrometer chọn các bucket trong miền expected value. |
| Cả hai | Bucket percentile được công bố cùng các ranh giới SLO bổ sung. |

Nếu câu hỏi chính là tỷ lệ request đạt ngưỡng 300 ms, SLO bucket tại 300 ms có thể đủ. Nếu cần xem p50, p95, p99 hoặc thay đổi percentile theo nhiều dimensions, histogram rộng hơn thường phù hợp hơn.

Không thêm hàng chục SLO boundary chỉ để tăng độ mịn của histogram. Mỗi ranh giới bổ sung có thể làm tăng số series và chi phí ingest. Chọn boundary theo mục tiêu dịch vụ và câu hỏi cần trả lời.

## 6. Histogram làm tăng số time series như thế nào?

Với Prometheus, mỗi tổ hợp tên meter và tag tạo một Meter ID. Histogram thêm series theo bucket boundary. Ngoài bucket, Timer còn công bố count, sum và max theo cấu hình registry.

Ước lượng sơ bộ:

\[
\text{Series} \approx
\text{Meter ID} \times
(\text{bucket count} + \text{count/sum/max})
\]

Đây là ước lượng để lập ngân sách. Exposition cụ thể có thể có thêm bucket +Inf hoặc khác biệt giữa registry/client, nên cần kiểm tra endpoint scrape thực tế.

Ví dụ một Timer có:

- 10 route đã chuẩn hóa.
- 3 method.
- 5 outcome.
- 66 bucket được công bố.

Số Meter ID là:

\[
10 \times 3 \times 5 = 150
\]

Ước lượng series nếu tính 66 bucket và 3 series count/sum/max:

\[
150 \times (66 + 3) = 10.350
\]

Chưa tính bucket +Inf nếu exporter biểu diễn nó thành một series riêng. Một Timer duy nhất trong code có thể tạo ra hàng nghìn series khi kết hợp histogram với nhiều tag value.

Nếu thêm client-side p50, p95 và p99, ứng dụng còn xuất thêm ba series cho mỗi Meter ID. Số series tăng theo số percentile được yêu cầu và số tag combination.

## 7. Cardinality khuếch đại chi phí histogram

Histogram không chỉ tốn chi phí theo số bucket. Nó nhân chi phí theo số Meter ID. Mỗi tag value mới có thể tạo thêm một Meter ID và do đó thêm cả nhóm bucket.

Ví dụ:

| Thiết kế tag | Số tổ hợp tag | Ảnh hưởng |
| --- | ---: | --- |
| method + route template + outcome | Thường giới hạn được | Dễ dự toán số Meter ID. |
| Thêm customerId | Có thể tăng theo số khách hàng | Nhân toàn bộ bucket theo khách hàng. |
| Thêm requestId hoặc orderId | Gần như không giới hạn | Cardinality và chi phí có thể bùng nổ. |
| Dùng URL đầy đủ thay route template | Có thể chứa ID/path động | Tạo nhiều series không cần thiết. |

Không đưa user ID, order ID, request ID, email hoặc chuỗi exception vào tag của Timer/DistributionSummary. Nếu cần liên kết metric với một request cụ thể, cân nhắc trace/span hoặc exemplar thay vì tạo dimension mới cho metric.

Nên chuẩn hóa route thành template như /orders/{id}, outcome thành một tập hữu hạn như success/error, và method thành GET/POST/PUT/DELETE. Tag cần phản ánh chiều phân tích có giá trị vận hành.

## 8. Chi phí bộ nhớ của histogram nội bộ

Micrometer duy trì cấu trúc dữ liệu trong ứng dụng để cập nhật histogram khi record. Chi phí phụ thuộc:

- Số Meter ID.
- Số bucket.
- Ring buffer length.
- Loại histogram.
- Có bật client-side percentiles hay không.
- Percentile precision.
- Cấu hình pause detection đối với Timer.
- Registry và implementation cụ thể.

Với fixed-boundary histogram, tài liệu Micrometer mô tả chi phí gần đúng theo công thức:

\[
\text{Fixed boundary storage} \approx 8 \times B \times R\ \text{bytes}
\]

Trong đó B là số bucket, R là ring buffer length. Đây là phần cấu trúc bucket, chưa phải toàn bộ footprint của meter.

Client-side percentiles dùng HdrHistogram để tính xấp xỉ phân vị. Precision càng cao thì bộ nhớ càng tăng. Micrometer mặc định dùng percentile precision 1; phạm vi thường được dùng là 0 đến 3.

Các thống kê theo cửa sổ như max và client-side percentile có thể hết hạn theo expiry nhân với bufferLength. expiry mặc định theo step của registry nếu không cấu hình riêng; bufferLength mặc định là 3. Histogram bucket vẫn là cumulative đối với backend như Prometheus vốn yêu cầu bucket không reset theo cửa sổ.

### Ví dụ footprint tham khảo

Các số dưới đây là ước lượng trong tài liệu Micrometer cho một meter không có tag, ring buffer length 3; implementation và registry có thể làm con số thay đổi:

| Cấu hình DistributionSummary | Bộ nhớ xấp xỉ |
| --- | ---: |
| Không histogram, không client-side percentile | 0,1 KB |
| Histogram được giới hạn khoảng 66 bucket | 6 KB |
| Histogram và thêm một client-side p95 | 12,6 KB |

Với Timer, phần pause detection nếu được bật có thêm interval estimator khoảng 1,7 KB trong ví dụ tài liệu. Một cấu hình Timer có pause detection, histogram và client-side percentile có thể lên khoảng 14,3 KB trong bảng ước lượng tương ứng.

Đây không phải cam kết dung lượng cho mọi ứng dụng. Thẻ tag, ring buffer, precision, registry implementation và số Meter ID đều làm tổng bộ nhớ thay đổi. Khi có 1.000 Meter ID, chi phí của một meter phải được nhân theo số ID trước khi cộng thêm overhead chung.

Với Prometheus, Micrometer dùng ring buffer length bằng 1 cho histogram cumulative vì Prometheus mong bucket tích lũy không bị reset theo vòng đời cửa sổ. Vì vậy không lấy R=3 trong bảng ví dụ rồi áp dụng máy móc cho mọi cấu hình Prometheus.

## 9. Client-side percentile và HdrHistogram

Khi gọi publishPercentiles(0.50, 0.95, 0.99), Micrometer tính các percentile xấp xỉ trong ứng dụng cho từng Meter ID. Cấu trúc HdrHistogram lưu thông tin phân phối với độ chính xác có thể cấu hình.

Các yếu tố ảnh hưởng:

- Percentile precision: số chữ số có ý nghĩa mà histogram cố giữ; precision cao tốn thêm bộ nhớ.
- Miền giá trị: khoảng min/max cần hỗ trợ ảnh hưởng cấu trúc histogram.
- Ring buffer: số cửa sổ được giữ để các thống kê time-window hết hạn dần.
- Số Meter ID: mỗi tổ hợp tên và tag có cấu trúc phân phối riêng.

Client-side percentiles yêu cầu HdrHistogram trên runtime classpath. Nếu chỉ dùng percentile histogram để backend tính percentile và không dùng client-side percentile, có thể không cần HdrHistogram chỉ vì tính năng này.

Percentile là giá trị gauge-like theo cửa sổ thống kê, không phải Counter. Không dùng rate() trên series p95/p99 như cách dùng với counter. Hãy đọc giá trị percentile theo thời gian hoặc giữ từng Meter ID riêng biệt.

## 10. Cấu hình có chọn lọc cho Timer

Không nên cấu hình histogram cho mọi Timer chỉ vì thư viện instrumentation hỗ trợ nó. Chọn các operation quan trọng như API có SLO, truy vấn database trọng yếu hoặc message processing có yêu cầu latency rõ ràng.

Ví dụ:

~~~java
Timer httpTimer = Timer.builder("http.server.requests.custom")
        .tag("route", "/orders/{id}")
        .tag("method", "GET")
        .publishPercentileHistogram()
        .minimumExpectedValue(Duration.ofMillis(1))
        .maximumExpectedValue(Duration.ofSeconds(3))
        .serviceLevelObjectives(
                Duration.ofMillis(100),
                Duration.ofMillis(300),
                Duration.ofSeconds(1))
        .register(registry);
~~~

Miền 1 ms đến 3 giây là ví dụ cho API có mục tiêu phản hồi ngắn. Hãy thay bằng phân phối thực tế và giới hạn SLO của dịch vụ. Nếu hệ thống có tác vụ kéo dài nhiều phút, cần chọn miền khác và xác định liệu Timer có phải meter phù hợp cho operation đó.

## 11. Cấu hình DistributionSummary có giới hạn

DistributionSummary dùng cho giá trị không phải thời gian, ví dụ payload size theo byte:

~~~java
import io.micrometer.core.instrument.DistributionSummary;

DistributionSummary payloadSize = DistributionSummary
        .builder("http.request.payload.size")
        .baseUnit("bytes")
        .publishPercentileHistogram()
        .minimumExpectedValue(1.0)
        .maximumExpectedValue(1_000_000.0)
        .serviceLevelObjectives(
                10_000.0,
                100_000.0,
                500_000.0)
        .register(registry);

payloadSize.record(requestBody.length);
~~~

Ví dụ giới hạn miền payload từ 1 byte đến 1 MB. Nếu ứng dụng thực tế cho phép payload lớn hơn, cần điều chỉnh max expected value. Không đặt min/max theo cảm tính; hãy dùng giới hạn được xác định từ hợp đồng API, validation và dữ liệu tải thực tế.

Với tỷ lệ nằm trong khoảng 0 đến 1, có thể scale giá trị lên 0 đến 100 trước khi chọn expected value và SLO boundaries. Ví dụ:

~~~java
DistributionSummary.builder("cache.hit.ratio")
        .scale(100)
        .publishPercentileHistogram()
        .minimumExpectedValue(0.0)
        .maximumExpectedValue(100.0)
        .serviceLevelObjectives(70.0, 80.0, 90.0)
        .register(registry);
~~~

Scale chỉ thay đổi giá trị được record vào DistributionSummary. Hãy đặt tên/baseUnit và dashboard theo đơn vị đã scale để tránh nhầm lẫn.

## 12. Bật thống kê bằng MeterFilter cho một nhóm meter

Khi instrumentation nằm trong thư viện dùng chung, thư viện có thể đăng ký Timer cơ bản. Ứng dụng chủ quản chọn meter nào cần histogram bằng MeterFilter:

~~~java
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.config.MeterFilter;
import io.micrometer.core.instrument.distribution.DistributionStatisticConfig;

registry.config().meterFilter(new MeterFilter() {
    @Override
    public DistributionStatisticConfig configure(
            Meter.Id id,
            DistributionStatisticConfig config) {

        if (id.getType() == Meter.Type.TIMER
                && id.getName().startsWith("checkout.critical.")) {
            return DistributionStatisticConfig.builder()
                    .percentilesHistogram(true)
                    .minimumExpectedValue(1_000_000.0)
                    .maximumExpectedValue(5_000_000_000.0)
                    .serviceLevelObjectives(
                            100_000_000.0,
                            300_000_000.0,
                            1_000_000_000.0)
                    .build()
                    .merge(config);
        }

        return config;
    }
});
~~~

Với Timer, các giá trị số trong DistributionStatisticConfig được biểu diễn bằng nanosecond. Ví dụ trên tương ứng min 1 ms, max 5 giây và các SLO 100 ms, 300 ms, 1 giây. Với Timer.Builder trực tiếp, nên ưu tiên Duration API để tránh nhầm đơn vị. Với DistributionSummary, giá trị cấu hình dùng cùng đơn vị với sample được record.

MeterFilter chỉ áp dụng cho tên có prefix checkout.critical. Các meter khác tiếp tục dùng cấu hình hiện có. Cách này giúp đội ứng dụng bật phân phối chi tiết cho nhóm operation cần thiết mà không buộc mọi consumer của thư viện phải trả cùng một chi phí.

Spring Boot cũng hỗ trợ property-based distribution configuration theo meter name/prefix. Hãy dùng một cơ chế cấu hình rõ ràng, tránh cùng lúc cấu hình ở builder, MeterFilter và application properties mà không biết giá trị nào thắng.

## 13. PromQL để tính percentile từ histogram

Với Prometheus, percentile histogram được xuất thành bucket series. Để tính p95 của request duration và gộp qua các instance, dùng:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, route) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
~~~

Phép sum gộp bucket theo le và route trước khi histogram_quantile tính percentile. Nếu giữ thêm method hoặc outcome, đưa các chiều đó vào cả phép sum by và dashboard theo câu hỏi cần trả lời.

Nếu chỉ tính percentile từng instance, giữ instance trong phép nhóm:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, instance, route) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
~~~

Không lấy trung bình p95 của từng instance để tạo p95 toàn service. Hãy cộng bucket trước rồi tính percentile.

Tên metric thực tế phụ thuộc instrumentation và Prometheus naming convention. Kiểm tra endpoint scrape trước khi sao chép query.

## 14. Đếm tỷ lệ request đạt SLO bằng bucket

Nếu histogram có SLO boundary 300 ms, bucket le="0.3" có thể dùng để đếm số request hoàn tất không quá 300 ms:

~~~promql
sum by (route) (
  rate(http_server_requests_seconds_bucket{le="0.3"}[5m])
)
/
sum by (route) (
  rate(http_server_requests_seconds_count[5m])
)
~~~

Kết quả là tỷ lệ request đạt ngưỡng 300 ms theo route trong cửa sổ 5 phút. Nếu cần tỷ lệ phần trăm, nhân với 100.

Bucket histogram là cumulative: bucket tại 300 ms chứa số quan sát nhỏ hơn hoặc bằng 300 ms, bao gồm các bucket thấp hơn. Không cộng tất cả bucket để tính số request vì sẽ đếm lặp quan sát.

## 15. Client-side percentile trong Prometheus

Khi dùng publishPercentiles(0.50, 0.95), Micrometer xuất percentile đã tính ở phía ứng dụng. Exposition thường gắn label quantile cho từng giá trị, nhưng tên metric và format phụ thuộc registry.

Có thể truy vấn p95 của từng Meter ID:

~~~promql
checkout_request_seconds{quantile="0.95"}
~~~

Không sum hoặc avg các series quantile qua instance để suy ra p95 toàn service. Nếu cần phân vị toàn cụm, chuyển sang percentile histogram và dùng histogram_quantile.

Client-side percentile phù hợp để xem phân phối cục bộ hoặc dùng backend không hỗ trợ percentile từ histogram. Hãy ghi rõ trên dashboard rằng đây là percentile của từng Meter ID.

## 16. Chọn histogram hay client-side percentile

| Yêu cầu | Lựa chọn thường phù hợp |
| --- | --- |
| Tổng hợp p95/p99 qua nhiều pod hoặc region. | Percentile histogram. |
| Tính percentile tại Prometheus/Atlas. | Percentile histogram. |
| Backend không hỗ trợ histogram quantile. | Client-side percentile. |
| Chỉ cần tỷ lệ đạt ngưỡng SLO cụ thể. | SLO buckets có thể đã đủ. |
| Chỉ cần count, sum, max và average. | Không bật percentile/histogram. |
| Cần percentile cục bộ của từng Meter ID. | Client-side percentile. |
| Cần nhiều chiều tag để phân tích. | Histogram có tag cardinality được kiểm soát. |

Với Prometheus/Atlas, không bật client-side percentile song song với histogram trừ khi có câu hỏi riêng cần percentile cục bộ. Prometheus Java Client 1.x không hỗ trợ công bố đồng thời hai dạng này dưới cùng một metric name.

## 17. Đo chi phí thực tế thay vì chỉ dựa vào bảng ước lượng

Footprint tài liệu giúp ước lượng ban đầu, nhưng cần đo trong môi trường ứng dụng vì chi phí thực tế còn phụ thuộc JDK, số Meter ID, tag, registry và tải ghi nhận.

Một thử nghiệm có kiểm soát nên so sánh các cấu hình:

1. Timer cơ bản không histogram, không client-side percentile.
2. Histogram với miền min/max hẹp.
3. Histogram với miền min/max rộng.
4. Client-side p95 và p99.
5. Histogram cùng nhiều tag combinations.

Đo các chỉ số:

- Heap sau khi warm-up và sau khi tạo đủ Meter ID.
- Allocation rate và GC pressure.
- CPU khi record ở cùng throughput.
- Kích thước exposition hoặc số sample mỗi lần scrape.
- Thời gian scrape và thời gian xử lý ở Prometheus.
- Ingestion rate và số active series tại backend.
- Số meter bị từ chối do cardinality limit hoặc cấu hình filter.

Không benchmark chỉ với một Meter ID rồi ngoại suy cho production có hàng trăm route, method, outcome và instance. Cardinality là hệ số nhân chính của chi phí.

## 18. Chi phí khi scrape và lưu trữ ở backend

Histogram làm tăng số sample trong mỗi lần scrape. Với Prometheus pull, endpoint cần tạo và serialize nhiều bucket series hơn. Prometheus sau đó phải nhận, index, nén và lưu từng time series theo scrape interval.

Nếu số series tăng gấp 10, chi phí không chỉ tăng ở ứng dụng. Backend cũng phải xử lý thêm:

- Samples được ingest ở mỗi lần scrape.
- Active time series và label index.
- Dung lượng block và compaction.
- Chi phí query khi sum nhiều bucket.
- Kích thước response và thời gian dựng dashboard.

Một histogram có 66 bucket trên 150 Meter ID đã có khoảng hơn 10 nghìn series theo phép ước lượng trước khi tính các bucket đặc biệt. Nếu có 20 instance và 15 giây scrape interval, lượng sample tích lũy sẽ tăng nhanh theo cả số instance lẫn số series.

Khi scale horizontal, mỗi instance thường xuất cùng nhóm series cho meter đó. Do đó, chi phí tổng ở backend tăng theo số instance, dù cấu hình meter không đổi.

## 19. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Bật histogram cho mọi Timer | Số bucket và series tăng trên toàn ứng dụng. | Chọn meter có nhu cầu phân tích percentile/SLO. |
| Bật cả histogram và client-side percentiles mặc định | Tăng memory và series, thường có dữ liệu dư thừa. | Chọn một cách theo khả năng backend. |
| Không giới hạn DistributionSummary min/max | Có thể xuất toàn bộ tập bucket mặc định. | Luôn đặt expected range khi bật percentile histogram. |
| Đặt max expected value quá thấp | Phân phối ở vùng đuôi không còn được mô tả phù hợp. | Chọn range từ hợp đồng và dữ liệu thực tế. |
| Dùng ID động làm tag | Mỗi ID tạo thêm Meter ID và toàn bộ bucket. | Chuẩn hóa tag về tập giá trị hữu hạn. |
| Cộng p95 giữa các pod | Kết quả không phải percentile toàn cụm. | Tổng hợp histogram bucket rồi tính percentile. |
| Cộng các bucket với nhau | Một quan sát bị đếm ở nhiều bucket cumulative. | Dùng đúng bucket le cần xét hoặc histogram_quantile. |
| Dùng rate() trên client-side percentile | Đọc percentile gauge-like như counter. | Quan sát giá trị percentile trực tiếp theo Meter ID. |
| Tăng percentile precision quá cao | Tăng bộ nhớ cho HdrHistogram. | Chỉ tăng precision khi đo đạc chứng minh cần thiết. |
| Thêm SLO boundary quá dày | Tăng bucket và sample không cần thiết. | Chọn ranh giới theo SLO thực tế. |
| Không kiểm tra backend capability | Bật histogram nhưng backend không xuất hoặc không query được. | Xác minh registry hỗ trợ aggregable percentile. |

## 20. Checklist trước khi bật histogram hoặc percentile

- [ ] Đã xác định câu hỏi vận hành cần trả lời: percentile, SLO hay chỉ count/sum.
- [ ] Đã xác nhận backend hỗ trợ tính percentile từ histogram.
- [ ] Đã chọn histogram hoặc client-side percentile theo nhu cầu.
- [ ] Đã tránh bật cả hai nếu không có lý do cụ thể.
- [ ] Đã đặt minimumExpectedValue và maximumExpectedValue phù hợp.
- [ ] DistributionSummary có expected range rõ ràng trước khi bật histogram.
- [ ] SLO boundaries được chọn theo mục tiêu dịch vụ.
- [ ] Tag dùng tập giá trị hữu hạn và route đã chuẩn hóa.
- [ ] Đã ước lượng số Meter ID và số bucket.
- [ ] Đã tính ảnh hưởng của số instance và scrape interval.
- [ ] Đã đánh giá memory, CPU, allocation và GC.
- [ ] Đã kiểm tra kích thước exposition và active series ở backend.
- [ ] Đã dùng histogram bucket để tổng hợp p95/p99 giữa instance.
- [ ] Đã không dùng rate() trên client-side percentile.
- [ ] Đã kiểm thử dashboard và alert với dữ liệu tải thực tế.

Histogram và client-side percentile cung cấp góc nhìn sâu hơn về phân phối, nhưng chi phí tăng theo số bucket, số Meter ID, precision và số instance. Hãy bắt đầu từ câu hỏi vận hành, chọn đúng cách tính percentile, giới hạn miền giá trị và tag, rồi đo footprint thực tế. Với Prometheus/Atlas, histogram thường là lựa chọn phù hợp khi cần tổng hợp percentile; client-side percentile chỉ nên bật khi cần giá trị cục bộ hoặc backend không có khả năng tính từ bucket.

## Tài liệu tham khảo

- [Micrometer - Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html)
- [Micrometer - Timers and Memory Footprint](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer - Distribution Summaries and Memory Footprint](https://docs.micrometer.io/micrometer/reference/concepts/distribution-summaries.html)
- [Micrometer - Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html)
- [Micrometer - Prometheus Implementation](https://docs.micrometer.io/micrometer/reference/implementations/prometheus.html)
- [Micrometer Concepts and Runtime Dependencies](https://docs.micrometer.io/micrometer/reference/concepts.html)
