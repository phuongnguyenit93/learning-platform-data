# Max về không hoặc dữ liệu chỉ đổi sau khi chuyển cửa sổ

Khi quan sát Timer hoặc DistributionSummary, có thể gặp hai hiện tượng dễ bị xem nhầm là lỗi instrumentation:

- Giá trị **max** từng tăng cao rồi giảm về 0 dù ứng dụng vẫn chạy.
- Count hoặc total time của một registry chỉ thay đổi sau khi kết thúc một chu kỳ publish, còn giữa chu kỳ thì giữ nguyên.

Hai hiện tượng này thường đến từ hai cơ chế khác nhau của Micrometer. **TimeWindowMax** giữ giá trị lớn nhất trong một cửa sổ thời gian có thể hết hạn. **Step-based registry** tích lũy dữ liệu của kỳ hiện tại rồi chuyển sang kỳ trước khi bước thời gian kết thúc. Cần xác định đang nhìn loại meter, loại registry và chu kỳ nào trước khi thay đổi cấu hình.

## 1. Phân biệt ba loại cửa sổ

Micrometer có nhiều mốc thời gian cùng tồn tại:

| Mốc | Vai trò | Ví dụ |
|---|---|---|
| Distribution statistic expiry | Thời gian một bucket của ring buffer giữ mẫu trước khi xoay | 10 giây |
| Distribution buffer length | Số bucket được giữ trong ring buffer | 3 bucket |
| Registry step | Chu kỳ tổng hợp và publish của step-based registry | 60 giây |
| Backend scrape interval | Tần suất Prometheus đọc endpoint | 15 giây |
| Dashboard query step/range | Khoảng lấy mẫu hoặc cửa sổ truy vấn khi vẽ biểu đồ | 30 giây / 15 phút |

Các mốc này không đồng nghĩa. Scrape interval không tự thay đổi expiry của Timer. Dashboard refresh cũng không làm registry hoàn tất một step. Khi các chu kỳ không được căn chỉnh, dữ liệu có thể trông như bị trễ hoặc biến mất.

## 2. Max của Timer và DistributionSummary là time-window max

Với các implementation Timer cơ bản như CumulativeTimer và StepTimer, giá trị max được tính bằng **TimeWindowMax**. Nó phản ánh mẫu lớn nhất trong một cửa sổ thời gian gần đây, không phải giá trị lớn nhất kể từ lúc ứng dụng khởi động.

Ví dụ:

1. Một request mất 2,4 giây và được ghi vào Timer.
2. Max tăng lên 2,4 giây.
3. Sau đó không có request nào được ghi vào Timer.
4. Các bucket trong ring buffer lần lượt hết hạn.
5. Khi toàn bộ mẫu cũ đã hết hạn, max trở về 0.

Đây là hành vi được thiết kế để max mô tả áp lực gần đây. Nếu một đợt latency cao xảy ra rồi hệ thống hoạt động bình thường trở lại, max sẽ dần hết hạn thay vì giữ mãi giá trị cũ.

DistributionSummary có cùng nguyên tắc cho max. Ví dụ summary đo kích thước payload có thể trả max bằng 0 sau khi không có payload mới trong đủ thời gian hết hạn.

## 3. Expiry và bufferLength quyết định thời gian giữ max

Thời gian hết hạn đầy đủ của ring buffer được tính theo:

~~~text
full expiry window = expiry x bufferLength
~~~

Trong cấu hình mặc định:

- Expiry mặc định lấy từ step size của registry nếu không được cấu hình riêng.
- Buffer length mặc định là 3.

Ví dụ registry có step 30 giây và Timer không override expiry:

| Thuộc tính | Giá trị minh họa |
|---|---:|
| Registry step | 30 giây |
| Expiry mặc định | 30 giây |
| Buffer length mặc định | 3 |
| Thời gian hết hạn đầy đủ | Khoảng 90 giây |

Sau khi mẫu lớn nhất được ghi, max có thể tồn tại trong ring buffer một khoảng thời gian rồi giảm khi các bucket cũ được xoay và xóa. Nếu không có mẫu mới, sau khi toàn bộ ring buffer hết hạn, giá trị max trở về 0.

Không nên kết luận rằng max luôn reset đúng tại một mốc step duy nhất. Việc xoay ring buffer được kích hoạt khi registry đọc hoặc ghi statistic và dựa trên clock của registry. Hãy kiểm tra thời điểm thực tế và cấu hình expiry/bufferLength.

## 4. Ví dụ cấu hình expiry riêng cho Timer

Có thể đặt expiry và buffer length trực tiếp trên builder:

~~~java
Timer requestTimer = Timer.builder("http.server.request.duration")
        .description("HTTP request duration")
        .distributionStatisticExpiry(Duration.ofSeconds(20))
        .distributionStatisticBufferLength(3)
        .register(registry);
~~~

Với cấu hình này, các thống kê phân phối có expiry 20 giây và ring buffer gồm 3 bucket. Thời gian giữ mẫu đầy đủ xấp xỉ 60 giây.

Đặt expiry riêng có các tác động:

- Max và các percentile time-window có thể giữ dữ liệu gần đây lâu hơn hoặc ngắn hơn.
- Bộ nhớ dùng cho ring buffer tăng khi buffer length tăng.
- Cửa sổ này không thay đổi chu kỳ publish của registry.
- Nó không biến max thành giá trị tích lũy suốt vòng đời ứng dụng.

Không tăng buffer length chỉ để giữ max vô thời hạn. Nếu mục tiêu là phân tích phân phối latency trong khoảng dài, histogram và truy vấn backend thường phù hợp hơn.

## 5. Ví dụ cấu hình expiry riêng cho DistributionSummary

~~~java
DistributionSummary payloadSize = DistributionSummary
        .builder("http.request.payload.size")
        .baseUnit("bytes")
        .distributionStatisticExpiry(Duration.ofMinutes(1))
        .distributionStatisticBufferLength(4)
        .register(registry);
~~~

Với expiry một phút và bốn bucket, dữ liệu max được giữ trong ring buffer khoảng bốn phút trước khi hết hạn hoàn toàn nếu không có mẫu mới. Các giá trị count và total amount vẫn phụ thuộc loại registry: registry cumulative giữ tổng tích lũy, còn step-based registry xuất dữ liệu theo từng kỳ.

## 6. Max bằng 0 không có nghĩa Timer chưa ghi nhận request

Khi max đã hết hạn, hãy kiểm tra thêm count và total time:

| Max | Count | Total time | Cách diễn giải |
|---:|---:|---:|---|
| 0 | 0 | 0 | Chưa có quan sát trong phạm vi meter hoặc meter chưa được ghi |
| 0 | Lớn hơn 0 | Lớn hơn 0 | Có dữ liệu count/sum nhưng max window hiện tại đã hết hạn hoặc không còn mẫu trong cửa sổ |
| Lớn hơn 0 | Lớn hơn 0 | Lớn hơn 0 | Có mẫu trong cửa sổ max hiện tại |
| Không có series | Không có series | Không có series | Meter chưa được export, bị filter, sai tên/tag hoặc scrape không đọc được |

Với Prometheus Timer, thường có các series:

- Tên metric kết thúc bằng _seconds_count: tổng số lần ghi.
- Tên metric kết thúc bằng _seconds_sum: tổng thời gian.
- Tên metric kết thúc bằng _seconds_max: max trong cửa sổ cấu hình.

Với registry cumulative, count và sum vẫn giữ tổng các lần ghi trước đó nên có thể lớn hơn 0 dù max window đã hết hạn về 0. Nếu có quan sát mới với duration dương, max sẽ được cập nhật lại. Vì vậy không dùng max làm bằng chứng duy nhất để xác định instrumentation có chạy hay không.

## 7. Step-based registry hoạt động theo kỳ publish

Một số registry dùng step aggregation để chuẩn bị dữ liệu cho backend. Micrometer tích lũy dữ liệu trong kỳ hiện tại. Khi kỳ kết thúc, dữ liệu hiện tại được chuyển sang trạng thái kỳ trước và trở thành giá trị được báo cáo cho lần publish.

Ví dụ registry có step 60 giây:

~~~text
12:00:00  Bắt đầu step A
12:00:10  Có 4 request hoàn tất
12:00:30  Có thêm 6 request hoàn tất
12:00:45  Có thêm 5 request hoàn tất
12:01:00  Step A kết thúc, dữ liệu được chuyển sang trạng thái previous
12:01:00  Step B bắt đầu tích lũy
12:01:10  Giá trị báo cáo của step A vẫn là 15
12:02:00  Step B kết thúc và previous được thay bằng dữ liệu của step B
~~~

Trong step-based registry, một số phép đo được xuất theo từng khoảng thay vì thay đổi tức thì theo từng lần record. Giá trị có thể giữ nguyên giữa hai lần chuyển step; điều này là bình thường.

Step aggregation giúp backend nhận dữ liệu đã được chuẩn hóa theo chu kỳ. Nó đặc biệt hữu ích với hệ thống nhận rate hoặc delta đã tính ở phía client.

## 8. Những statistic nào có thể thay đổi theo step?

Với Timer và DistributionSummary, cần phân biệt các statistic:

| Statistic | Ý nghĩa | Hành vi thường gặp |
|---|---|---|
| Timer count | Số lần ghi | Cumulative hoặc số lần trong step, tùy registry |
| Timer totalTime | Tổng thời gian | Cumulative hoặc tổng trong step |
| Summary count | Số quan sát | Cumulative hoặc số quan sát trong step |
| Summary totalAmount | Tổng giá trị | Cumulative hoặc tổng trong step |
| Max | Giá trị lớn nhất | Time-window max, có thể hết hạn |
| Percentile | Phân vị | Time-window percentile |
| Histogram buckets | Số mẫu trong bucket | Cumulative ở backend yêu cầu cumulative; có thể là rate/delta ở backend khác |
| Gauge | Giá trị hiện tại của một đối tượng hoặc hàm đọc | Được lấy mẫu khi publish/scrape; không phải tổng của step |

Không áp dụng một quy tắc cho mọi statistic. Với registry cumulative, count/sum vẫn giữ tổng các lần ghi trước đó sau khi max hết hạn. Với step registry, count/sum thường chỉ đổi khi chuyển kỳ.

## 9. Phân biệt Cumulative registry và Step registry

**Cumulative registry** thường giữ giá trị tích lũy từ khi ứng dụng khởi động. Backend pull như Prometheus có thể lấy các giá trị tuyệt đối định kỳ rồi dùng hàm rate trong truy vấn.

**Step-based registry** thường tích lũy dữ liệu trong một khoảng và publish giá trị của khoảng đã hoàn tất. Giá trị trả về có thể giữ nguyên đến khi step kế tiếp được chốt.

| Đặc điểm | Cumulative | Step-based |
|---|---|---|
| Count | Tăng theo vòng đời process | Thường là count của step vừa hoàn tất |
| Total time/amount | Tích lũy | Thường là tổng trong step |
| Max | Time-window max | Time-window max |
| Thời điểm giá trị đổi | Sau mỗi lần record hoặc lần đọc tương ứng | Theo chu kỳ step đối với step statistic |
| Phân tích rate | Thường tính ở backend | Có thể được chuẩn hóa trước khi publish |

Không xác định loại registry chỉ dựa vào tên backend hoặc dashboard. Kiểm tra implementation registry đang được ứng dụng tạo và cấu hình thực tế.

## 10. Prometheus pull không giống push registry theo step

Prometheus thường scrape endpoint theo chu kỳ. Micrometer Prometheus registry xuất count và sum theo dạng cumulative; Prometheus dùng PromQL để tính rate trên các mẫu scrape.

Throughput (requests mỗi giây) trong cửa sổ năm phút:

~~~promql
rate(http_server_request_duration_seconds_count[5m])
~~~

Average latency trong cửa sổ:

~~~promql
rate(http_server_request_duration_seconds_sum[5m])
/
rate(http_server_request_duration_seconds_count[5m])
~~~

Series max của Prometheus Timer vẫn là max trong time window của Micrometer. Nó không phải max tích lũy từ lúc process khởi động.

Nếu scrape mỗi 15 giây nhưng expiry của max là 60 giây, dashboard có thể thấy max giữ nguyên qua một số lần scrape rồi về 0 khi không có mẫu mới đủ lâu. Scrape interval chỉ quyết định tần suất backend quan sát; nó không kéo dài thời gian sống của max.

## 11. Truy vấn max trong Prometheus

Series max của Timer thường có hậu tố _seconds_max. Có thể hiển thị trực tiếp:

~~~promql
http_server_request_duration_seconds_max
~~~

Nếu dashboard muốn hiển thị giá trị max lớn nhất từng được scrape trong 15 phút:

~~~promql
max_over_time(http_server_request_duration_seconds_max[15m])
~~~

max_over_time giữ lại giá trị lớn nhất trong các mẫu đã scrape ở cửa sổ truy vấn. Nó không khôi phục một spike xảy ra giữa hai lần scrape nếu spike đó không xuất hiện trong bất kỳ mẫu nào.

Nếu cần phân tích phân phối latency có thể tổng hợp giữa nhiều instance, bật histogram và dùng bucket phù hợp. Ví dụ:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_request_duration_seconds_bucket[5m])
  )
)
~~~

Histogram bucket cumulative của Prometheus không hết hạn theo cùng cách max time-window. Chúng phù hợp hơn cho truy vấn percentile có thể tổng hợp giữa instance.

## 12. Vì sao dữ liệu có vẻ chỉ đổi khi chuyển cửa sổ?

Có một số nguyên nhân phổ biến:

1. Registry dùng step aggregation và chỉ công bố dữ liệu của kỳ vừa hoàn tất.
2. Dashboard dùng query step lớn hơn khoảng cập nhật thực tế.
3. Exporter publish theo chu kỳ nhưng dashboard refresh nhanh hơn chu kỳ publish.
4. Max và percentile được tính theo ring buffer, nên thay đổi khi bucket được xoay.
5. Backend giữ mẫu cũ hoặc nội suy dữ liệu giữa các điểm scrape.

Để phân biệt, ghi lại thời điểm record, thời điểm registry publish, timestamp scrape và timestamp điểm dữ liệu trong backend. Nếu giá trị thay đổi đúng tại ranh giới step, đó là dấu hiệu step aggregation. Nếu chỉ max hết hạn sau một khoảng không có record, đó là dấu hiệu time-window statistic.

## 13. Quy trình chẩn đoán nhanh

Thực hiện theo thứ tự:

1. Xác định meter là Timer hay DistributionSummary.
2. Xác định statistic đang có vấn đề là max, count, sum, percentile hay bucket.
3. Xác định loại registry: cumulative hay step-based.
4. Đọc step size của registry.
5. Đọc expiry và buffer length của meter.
6. Kiểm tra scrape interval hoặc push interval.
7. So sánh dữ liệu thô ở endpoint/exporter với dữ liệu đã được dashboard biến đổi.
8. Kiểm tra tag và meter name để chắc chắn đang xem đúng chuỗi thời gian.
9. Ghi một sample có giá trị đã biết và theo dõi qua nhiều lần đọc.
10. Dùng MockClock để tái hiện hết hạn hoặc ranh giới thời gian trong test.

Không thay đổi đồng thời step, expiry, scrape interval và dashboard range. Hãy thay từng tham số để biết chính xác cơ chế nào làm dữ liệu đổi.

## 14. Kiểm tra raw metric trước khi kiểm tra dashboard

Với Prometheus registry, kiểm tra trực tiếp scrape output:

~~~java
PrometheusMeterRegistry registry =
        new PrometheusMeterRegistry(PrometheusConfig.DEFAULT);

Timer timer = Timer.builder("http.server.request.duration")
        .register(registry);

timer.record(Duration.ofMillis(850));

String scrape = registry.scrape();
System.out.println(scrape);
~~~

Tìm các series count, sum và max của meter. Tên thực tế phụ thuộc naming convention và exporter version.

Với Spring Boot, có thể kiểm tra endpoint Prometheus Actuator nếu endpoint được expose. Nếu raw scrape đã có giá trị đúng nhưng dashboard sai, tập trung vào PromQL, label matching, recording rule, query step và cách panel hiển thị.

Nếu raw scrape không có meter, kiểm tra registry có được inject đúng vào instrumentation, meter có được tạo, MeterFilter có chặn hay không và endpoint có scrape đúng registry hay không.

## 15. Kiểm thử TimeWindowMax bằng MockClock

Không cần chờ thật 60 hoặc 90 giây trong unit test. Dùng MockClock để điều khiển thời gian:

~~~java
import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.core.instrument.simple.SimpleConfig;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;

class TimerMaxWindowTest {

    @Test
    void maxExpiresAfterAllWindowBucketsRotate() {
        MockClock clock = new MockClock();
        SimpleMeterRegistry registry =
                new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);

        try {
            Timer timer = Timer.builder("request.duration")
                    .distributionStatisticExpiry(Duration.ofSeconds(10))
                    .distributionStatisticBufferLength(3)
                    .register(registry);

            timer.record(Duration.ofMillis(850));

            assertThat(timer.max(TimeUnit.MILLISECONDS))
                    .isEqualTo(850.0);
            assertThat(timer.count()).isEqualTo(1);

            clock.add(Duration.ofSeconds(31));

            assertThat(timer.max(TimeUnit.MILLISECONDS))
                    .isEqualTo(0.0);
            assertThat(timer.count()).isEqualTo(1);
        } finally {
            registry.close();
        }
    }
}
~~~

Test chứng minh max có thể hết hạn trong khi count vẫn giữ lại quan sát đã ghi. Thời gian 31 giây được chọn lớn hơn expiry 10 giây nhân buffer length 3. Nếu thay đổi phiên bản hoặc cấu hình, hãy giữ assertion dựa trên hợp đồng hết hạn đầy đủ thay vì giả định một mốc reset chính xác giữa các bucket.

## 16. Kiểm thử DistributionSummary max

DistributionSummary có cùng time-window max:

~~~java
MockClock clock = new MockClock();
SimpleMeterRegistry registry =
        new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);

try {
    DistributionSummary summary = DistributionSummary
            .builder("request.payload.size")
            .distributionStatisticExpiry(Duration.ofSeconds(5))
            .distributionStatisticBufferLength(2)
            .register(registry);

    summary.record(4096);
    assertThat(summary.max()).isEqualTo(4096.0);

    clock.add(Duration.ofSeconds(11));

    assertThat(summary.max()).isEqualTo(0.0);
    assertThat(summary.count()).isEqualTo(1);
} finally {
    registry.close();
}
~~~

Giá trị max phản ánh mẫu trong cửa sổ; count vẫn phản ánh số lần ghi theo implementation cumulative đang dùng trong test.

## 17. Kiểm tra step-based registry

Không dùng SimpleMeterRegistry để kết luận về hành vi step của registry push. SimpleMeterRegistry chủ yếu là registry tối giản cho test; nó không mô phỏng chu kỳ publish của mọi backend.

Để kiểm tra step:

- Dùng registry implementation thực tế của backend, ví dụ registry push mà ứng dụng đang cấu hình.
- Cấp clock có thể điều khiển nếu constructor của registry cho phép.
- Ghi một số mẫu trong step hiện tại.
- Poll hoặc publish trước ranh giới step và xác minh dữ liệu của kỳ trước vẫn được báo cáo.
- Advance clock qua ranh giới step.
- Xác minh dữ liệu của kỳ vừa hoàn tất xuất hiện và kỳ mới bắt đầu tích lũy.

Với integration test, có thể dùng mock server hoặc exporter test hook để thu payload. Không dựa vào thời gian ngủ thực nếu registry cho phép dùng clock giả.

## 18. Cấu hình step ở đâu?

Step size thuộc cấu hình của từng registry implementation. Tùy backend, nó có thể được đặt qua constructor/config object của registry hoặc thuộc tính Spring Boot dành riêng cho exporter đó.

Không có một property duy nhất áp dụng cho mọi registry. Hãy kiểm tra:

- Registry class đang được tạo.
- Config object truyền vào constructor.
- Spring Boot configuration properties của exporter tương ứng.
- Giá trị step thực tế sau khi cấu hình được bind.

Nếu thay step size, hãy đánh giá lại expiry mặc định của Timer/DistributionSummary vì expiry mặc định thường lấy từ step size của registry. Việc thay step có thể đồng thời thay đổi độ dài cửa sổ max nếu meter không override expiry.

## 19. Cấu hình expiry không thay đổi step publish

Ví dụ:

~~~java
Timer timer = Timer.builder("payment.duration")
        .distributionStatisticExpiry(Duration.ofSeconds(15))
        .distributionStatisticBufferLength(4)
        .register(registry);
~~~

Với cấu hình trên:

- Ring buffer max có expiry 15 giây.
- Full expiry window khoảng 60 giây.
- Registry vẫn publish theo step riêng của nó, ví dụ 30 giây.

Do đó có thể xảy ra:

- Max thay đổi hoặc hết hạn theo cửa sổ 15 giây.
- Count/total time step chỉ được xuất khi step 30 giây hoàn tất.

Đây là hai nhịp cập nhật khác nhau. Không tăng expiry chỉ vì count của step registry chưa đổi; cũng không giảm step chỉ vì max hết hạn nhanh.

## 20. Nếu muốn max tồn tại lâu hơn

Trước tiên xác định nhu cầu:

| Nhu cầu | Cách phù hợp |
|---|---|
| Max gần đây trong một khoảng ngắn | Giữ TimeWindowMax mặc định hoặc chỉnh expiry |
| Max của một khoảng dashboard dài hơn | Dùng max_over_time trên các mẫu max đã scrape |
| Percentile có thể tổng hợp giữa instance | Bật histogram và truy vấn bucket |
| SLO latency | Dùng service-level objective boundaries/histogram |
| Giá trị lớn nhất từ khi process khởi động | Tự duy trì một Gauge có ngữ nghĩa lifetime max, đồng thời chấp nhận reset khi process restart |

Tăng buffer length chỉ kéo dài thời gian giữ dữ liệu trong ring buffer; nó không biến max thành lifetime maximum. Nếu cần lifetime max, hãy định nghĩa rõ phạm vi vòng đời, xử lý restart và khả năng tổng hợp nhiều instance.

## 21. Khi max bằng 0 nhưng histogram vẫn có dữ liệu

Histogram bucket và max có semantics khác nhau. Với backend như Prometheus, histogram bucket thường là counter cumulative; chúng không bị reset theo time-window max.

Vì vậy có thể thấy:

- _max bằng 0 sau khi max hết hạn.
- _count và _sum vẫn tích lũy.
- _bucket vẫn tăng theo tổng số quan sát trong từng bucket.

Đừng cố suy ra max từ một bucket riêng lẻ. Histogram bucket biểu diễn số quan sát nhỏ hơn hoặc bằng ranh giới; để suy ra percentile cần dùng truy vấn histogram phù hợp.

Với backend push khác, histogram count có thể được xuất dưới dạng rate/delta theo step. Hãy kiểm tra semantics của exporter và backend trước khi so sánh số liệu.

## 22. Những nguyên nhân khác khiến dữ liệu có vẻ bị trễ

Không phải mọi dữ liệu cập nhật theo cửa sổ đều do StepMeterRegistry:

**Scrape interval dài:** Backend chỉ nhìn thấy dữ liệu ở các lần scrape. Spike ngắn giữa hai lần scrape có thể không xuất hiện.

**Push interval dài:** Registry push chỉ gửi dữ liệu theo chu kỳ. Dashboard có thể giữ điểm cũ cho đến lần publish tiếp theo.

**Dashboard query step lớn:** Panel lấy mẫu thưa hơn, khiến thay đổi nhỏ giữa các điểm không hiển thị.

**Recording rule chạy theo lịch:** Kết quả rule có thể cập nhật chậm hơn raw series.

**Aggregation theo tag:** Query sum/max theo một tập label có thể làm một series thay đổi khác với series gốc.

**Sai timezone hoặc clock:** Clock lệch giữa ứng dụng, collector và backend có thể khiến dữ liệu được nhóm vào cửa sổ khác.

**Meter không được ghi liên tục:** Nếu không có sample mới, max có thể hết hạn đúng như thiết kế.

## 23. Bảng phân biệt triệu chứng

| Triệu chứng | Nguyên nhân có khả năng | Cách xác minh |
|---|---|---|
| Max từng lớn rồi về 0 | TimeWindowMax hết hạn | Kiểm tra expiry, bufferLength và thời điểm record cuối |
| Max bằng 0 nhưng count/sum vẫn lớn | Max window hết hạn, count/sum có semantics khác | So sánh raw max, count và sum |
| Count/sum giữ nguyên rồi nhảy theo step | Step-based aggregation | Đối chiếu registry step và publish timestamp |
| Gauge đổi ngay khi scrape | Gauge được đọc tại thời điểm scrape | Kiểm tra registry và endpoint |
| Raw scrape đúng, dashboard chậm | Query step, panel refresh hoặc recording rule | Chạy query trực tiếp trên raw series |
| Không có series nào | Meter chưa tạo, bị filter hoặc exporter không expose | Kiểm tra registry.getMeters và scrape endpoint |
| Histogram bucket còn dữ liệu nhưng max bằng 0 | Bucket cumulative, max time-window | So sánh semantics từng statistic |

## 24. Các lỗi thường gặp

**Coi max là lifetime maximum.** Max của Timer/DistributionSummary cơ bản là time-window max và có thể về 0 khi mẫu cũ hết hạn.

**Cho rằng max reset sau đúng một expiry.** Ring buffer có nhiều bucket; full expiry phụ thuộc expiry nhân buffer length.

**Nhầm expiry với registry step.** Expiry điều khiển ring buffer statistic; step điều khiển kỳ publish/aggregation của step registry.

**Nhầm scrape interval với expiry.** Scrape interval là tần suất backend đọc; nó không quyết định vòng đời mẫu max.

**Cho rằng mọi statistic đều hết hạn giống max.** Count, total time/amount và histogram bucket có semantics khác nhau tùy registry/backend.

**Tăng buffer length để giữ lifetime max.** Buffer dài hơn chỉ kéo dài cửa sổ giữ mẫu và tăng bộ nhớ.

**Dùng SimpleMeterRegistry để kiểm tra step behavior.** Dùng registry step-based thật hoặc test clock/publisher của registry đó.

**Chỉ nhìn dashboard.** Panel có thể dùng query range, step hoặc aggregation khiến dữ liệu trông bị trễ. Kiểm tra raw scrape trước.

**Không phân biệt 0 với series vắng mặt.** Giá trị 0 có thể là max hết hạn; series vắng mặt có thể là meter không được export hoặc query sai.

**Thay nhiều chu kỳ cùng lúc.** Thay step, expiry, scrape interval và dashboard range đồng thời làm mất khả năng tìm nguyên nhân.

## 25. Checklist điều tra

Khi max về 0 hoặc dữ liệu chỉ đổi sau khi chuyển cửa sổ, hãy kiểm tra:

- [ ] Đang xem Timer hay DistributionSummary.
- [ ] Statistic gặp vấn đề là max, count, sum, percentile hay histogram bucket.
- [ ] Registry là cumulative hay step-based.
- [ ] Registry step size thực tế.
- [ ] Meter expiry thực tế.
- [ ] Distribution statistic buffer length.
- [ ] Thời điểm ghi sample cuối cùng.
- [ ] Scrape interval hoặc push interval.
- [ ] Raw metric ở exporter có đúng không.
- [ ] Dashboard query có dùng max_over_time, rate, aggregation hoặc recording rule không.
- [ ] Tag và meter name có khớp giữa instrumentation và query không.
- [ ] Test MockClock tái hiện được hành vi hết hạn.
- [ ] Test step dùng đúng registry implementation.

## 26. Kết luận

Max về 0 thường là hành vi đúng của TimeWindowMax: Timer và DistributionSummary giữ max trong ring buffer có expiry và buffer length; khi toàn bộ mẫu cũ hết hạn mà không có mẫu mới, max trở về 0. Count, total time/amount và histogram bucket có semantics khác; ở registry cumulative, chúng vẫn giữ tổng các lần ghi trước đó. Khi có quan sát mới với duration dương, max được cập nhật trở lại.

Dữ liệu chỉ đổi sau khi chuyển cửa sổ thường liên quan step-based registry: registry tích lũy trong kỳ hiện tại rồi báo cáo kỳ đã hoàn tất. Hãy phân biệt expiry, registry step, scrape interval và dashboard query step. Kiểm tra raw metrics, so sánh max với count/sum, và dùng MockClock để tái hiện expiry. Khi hiểu đúng từng cửa sổ, có thể chọn cấu hình phù hợp mà không làm sai semantics của dữ liệu.

## Tài liệu tham khảo

- [Micrometer – Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer – Distribution Summaries](https://docs.micrometer.io/micrometer/reference/concepts/distribution-summaries.html)
- [Micrometer – Rate Aggregation](https://docs.micrometer.io/micrometer/reference/concepts/rate-aggregation.html)
- [Micrometer – Prometheus Registry](https://docs.micrometer.io/micrometer/reference/implementations/prometheus.html)
- [Micrometer – Timer.Builder API](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/Timer.Builder.html)
- [Micrometer – MockClock API](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/MockClock.html)
