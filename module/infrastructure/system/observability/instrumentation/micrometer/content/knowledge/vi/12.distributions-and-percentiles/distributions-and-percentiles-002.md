# publishPercentiles để tính phân vị tại ứng dụng

Khi theo dõi độ trễ hoặc kích thước dữ liệu, giá trị trung bình thường không đủ để mô tả trải nghiệm thực tế. Một API có thể có thời gian xử lý trung bình 80 ms nhưng một nhóm request vẫn mất vài giây. Percentile giúp nhìn vào phần đuôi của phân phối: p95 là ngưỡng mà khoảng 95% quan sát nằm ở mức bằng hoặc thấp hơn, còn khoảng 5% quan sát nằm phía trên ngưỡng đó.

Micrometer cho phép công bố các phân vị được tính ngay trong ứng dụng bằng publishPercentiles(...). Cấu hình này hữu ích khi cần xem p50, p95 hoặc p99 cho từng meter và từng tập tag. Tuy nhiên, các phân vị tính tại ứng dụng không thể cộng gộp chính xác giữa nhiều instance. Nếu cần một p95 chung cho toàn bộ service, đặc biệt trong Prometheus, histogram thường là lựa chọn phù hợp hơn.

## 1. Percentile biểu diễn điều gì?

Percentile là một điểm cắt trong phân phối quan sát. Với thời gian xử lý request:

- **p50** là trung vị: khoảng một nửa request có thời gian không vượt quá giá trị này.
- **p90** cho biết khoảng 90% request có thời gian không vượt quá ngưỡng.
- **p95** cho biết khoảng 95% request có thời gian không vượt quá ngưỡng.
- **p99** cho biết khoảng 99% request có thời gian không vượt quá ngưỡng; đây là góc nhìn về phần đuôi rất chậm.

Ví dụ, nếu p95 của API là 420 ms trong cửa sổ quan sát, có thể diễn giải rằng khoảng 95% lần xử lý trong phân phối được đo có thời lượng không vượt quá khoảng 420 ms. Khoảng 5% còn lại chậm hơn. Đây là mô tả phân phối, không phải lời khẳng định mọi request đều hoàn tất trong 420 ms.

Percentile không phải là giá trị lớn nhất, cũng không phải trung bình. Một vài request cực chậm có thể làm max tăng mạnh nhưng ít ảnh hưởng đến p95; ngược lại, nếu một phần đáng kể request chậm, p95 sẽ phản ánh sự suy giảm đó.

### Vì sao trung bình có thể che khuất vấn đề?

Giả sử có 100 request:

- 90 request hoàn tất trong 50 ms.
- 9 request hoàn tất trong 200 ms.
- 1 request hoàn tất trong 5 giây.

Trung bình có thể trông chấp nhận được so với request chậm nhất, nhưng p95 sẽ cho thấy vùng mà nhóm request chậm bắt đầu ảnh hưởng. Khi điều tra trải nghiệm người dùng, nên xem nhiều phân vị cùng với throughput, error rate và các chỉ số tài nguyên.

## 2. publishPercentiles hoạt động ở đâu?

publishPercentiles(...) yêu cầu Micrometer tính các phân vị trong tiến trình ứng dụng. Phân phối được theo dõi cho từng meter identity, tức tên meter kết hợp với các tag. Khi registry xuất số liệu, các giá trị percentile được công bố cùng metric tương ứng.

Ví dụ, ứng dụng chọn công bố p50, p95 và p99 cho một Timer. Mỗi instance sẽ tính các phân vị dựa trên các quan sát mà instance đó ghi nhận cho meter đó. Nếu có nhiều tag-value, mỗi tổ hợp tag có thể có bộ số liệu percentile riêng.

Điều này có nghĩa:

- Tính toán diễn ra ở phía ứng dụng, không chờ backend nhận toàn bộ mẫu thô.
- Kết quả được gắn với meter và tag cụ thể.
- Backend nhận các giá trị percentile đã tính, không nhận toàn bộ phân phối để tự ghép lại.
- Các giá trị này không thể tổng hợp chính xác thành percentile toàn cục bằng cách lấy trung bình hoặc max giữa các instance.

Các giá trị percentile là kết quả ước lượng từ cơ chế thống kê phân phối của Micrometer; độ chính xác và cách duy trì mẫu phụ thuộc implementation cùng cấu hình. Không nên coi một giá trị p95/p99 là phép tính chính xác tuyệt đối trên toàn bộ request lịch sử.

Micrometer dùng cấu hình thống kê phân phối để quản lý việc công bố percentile. Phạm vi thời gian và cách duy trì dữ liệu phụ thuộc cấu hình distribution statistics cùng phiên bản thư viện. Vì vậy, không nên hiểu giá trị percentile là thống kê tích lũy từ lúc ứng dụng khởi động hoặc toàn bộ lịch sử vô hạn. Khi thiết kế dashboard và cảnh báo, cần xác định cửa sổ thời gian mà dữ liệu đại diện và kiểm tra hành vi thực tế của phiên bản đang dùng.

## 3. Cấu hình publishPercentiles cho Timer

Timer phù hợp để đo thời lượng thực thi. Có thể chọn các percentile ngay khi đăng ký meter:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

@Component
public class OrderMetrics {

    private final Timer processingTimer;

    public OrderMetrics(MeterRegistry registry) {
        this.processingTimer = Timer.builder("orders.processing")
                .description("Time spent processing an order")
                .publishPercentiles(0.50, 0.95, 0.99)
                .register(registry);
    }

    public void recordProcessing(Runnable operation) {
        processingTimer.record(operation);
    }
}
~~~

Mỗi lần recordProcessing được gọi, Timer ghi nhận thời lượng của thao tác. Micrometer cập nhật phân phối và tính các percentile đã yêu cầu. Nên đăng ký Timer một lần trong bean rồi tái sử dụng; không tạo meter mới cho mỗi request.

Có thể dùng Timer.Sample khi cần quyết định thời điểm kết thúc hoặc ghi nhận kết quả ở một nhánh xử lý cụ thể:

~~~java
Timer.Sample sample = Timer.start(registry);
try {
    processOrder(order);
} finally {
    sample.stop(processingTimer);
}
~~~

Sample đo thời lượng từ lúc bắt đầu đến khi dừng. finally giúp ghi nhận thời gian ngay cả khi thao tác phát sinh exception. Nếu chỉ muốn đo một đoạn code đồng bộ đơn giản, Timer.record(...) thường ngắn gọn hơn.

Timer chuẩn hóa thời lượng theo đơn vị mà registry đích sử dụng. Với Prometheus, thời lượng thường được biểu diễn bằng giây; không tự đổi giá trị percentile sang mili giây trong code nếu backend đã công bố theo đơn vị khác.

## 4. Cấu hình publishPercentiles cho DistributionSummary

DistributionSummary phù hợp với phân phối của các đại lượng số không nhất thiết là thời gian, chẳng hạn kích thước payload, số bản ghi trong một batch hoặc số byte trong một lần ghi.

~~~java
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class PayloadMetrics {

    private final DistributionSummary payloadSize;

    public PayloadMetrics(MeterRegistry registry) {
        this.payloadSize = DistributionSummary.builder("http.request.payload")
                .description("Request payload size")
                .baseUnit("bytes")
                .publishPercentiles(0.50, 0.95, 0.99)
                .register(registry);
    }

    public void recordPayload(long bytes) {
        payloadSize.record(bytes);
    }
}
~~~

Mỗi lần ghi nhận, record(bytes) thêm một quan sát vào phân phối. p95 của payload size cho biết ngưỡng kích thước mà khoảng 95% payload được ghi nhận không vượt quá. Đây là thông tin khác với tổng byte đã truyền; nếu cần tổng lượng byte, hãy dùng Counter riêng.

Không ghi cùng một đại lượng vào DistributionSummary với đơn vị không nhất quán. Ví dụ, nếu một số lần ghi dùng byte còn lần khác dùng kilobyte, percentile không còn ý nghĩa. Hãy chuẩn hóa đơn vị trước khi gọi record.

## 5. Cấu hình bằng Spring Boot

Với ứng dụng Spring Boot có Micrometer registry phù hợp, có thể cấu hình percentile theo tên meter trong application.yml:

~~~yaml
management:
  metrics:
    distribution:
      percentiles:
        orders.processing: 0.5, 0.95, 0.99
        http.server.requests: 0.5, 0.95, 0.99
~~~

Phần cấu hình này yêu cầu Spring Boot áp dụng các percentile cho những meter có tên tương ứng. Tên meter cần khớp với tên được đăng ký trong registry; hãy kiểm tra tên thực tế khi dùng instrumentation tự động của framework vì tên có thể khác với tên tự đặt trong mã nghiệp vụ.

Nếu cấu hình trong code và cấu hình bên ngoài cùng áp dụng cho một meter, hãy kiểm tra quy tắc kết hợp của phiên bản Spring Boot/Micrometer đang dùng. Tránh duy trì hai nguồn cấu hình không thống nhất khiến nhóm vận hành khó biết percentile nào thực sự được công bố.

Chỉ bật các percentile cần dùng. Việc công bố nhiều quantile cho nhiều meter và nhiều tổ hợp tag làm tăng số time series, kích thước payload scrape và chi phí lưu trữ.

## 6. Đọc percentile được xuất sang Prometheus

Với Prometheus registry, percentile tính tại ứng dụng thường được xuất theo dạng summary quantile, tức có label quantile trên metric tương ứng. Tên chính xác phụ thuộc meter và quy tắc chuẩn hóa tên của registry.

Ví dụ minh họa một metric Timer đã được xuất với tên orders_processing_seconds:

~~~promql
orders_processing_seconds{quantile="0.95"}
~~~

Truy vấn này đọc giá trị p95 do từng instance công bố. Nếu có label instance, mỗi instance có thể trả về một chuỗi percentile riêng. Có thể xem riêng từng instance để tìm node có độ trễ cao.

Không dùng avg() để lấy p95 toàn service từ các p95 riêng lẻ. Trung bình của các percentile không phải percentile của tập dữ liệu gộp. max() cũng chỉ cho biết percentile lớn nhất giữa các instance, không phải p95 toàn cục.

Nếu cần so sánh percentile theo route hoặc service, hãy giữ các chiều tag cần thiết và kiểm soát cardinality. Tránh thêm tag động như user ID hoặc URL đầy đủ chỉ để chia nhỏ biểu đồ.

## 7. Giới hạn quan trọng: không thể gộp percentile tại ứng dụng

Giả sử service có hai instance:

- Instance A xử lý 10.000 request và có p95 là 100 ms.
- Instance B xử lý 100 request và có p95 là 1.000 ms.

Lấy trung bình hai giá trị p95 sẽ cho 550 ms, nhưng 550 ms không phải p95 của 10.100 request. Phép tính đó bỏ qua số lượng quan sát của mỗi instance và cấu trúc phân phối bên trong từng instance.

Ngay cả khi biết số lượng request, không thể khôi phục chính xác phân phối gốc chỉ từ p95 của từng nhóm. Percentile là điểm cắt đã tóm tắt phân phối; thông tin về các quan sát còn lại đã bị mất.

Do đó:

- Dùng publishPercentiles khi cần percentile cục bộ theo instance hoặc theo một meter identity cụ thể.
- Không cộng, lấy trung bình hoặc lấy max các quantile rồi gọi đó là percentile toàn service.
- Dùng histogram khi cần tổng hợp phân phối từ nhiều instance hoặc nhiều chiều tag.

## 8. So sánh publishPercentiles với percentile histogram

Micrometer hỗ trợ hai cách phổ biến để công bố thông tin phân phối:

| Tiêu chí | publishPercentiles(...) | publishPercentileHistogram() |
| --- | --- | --- |
| Nơi tính percentile | Trong ứng dụng, cho từng meter identity. | Backend có thể tính percentile từ các bucket histogram được xuất. |
| Dữ liệu xuất | Các giá trị quantile đã tính. | Các bucket histogram cùng số lượng quan sát tích lũy theo bucket. |
| Gộp nhiều instance | Không thể gộp chính xác các quantile đã tính. | Có thể gộp bucket từ nhiều instance rồi tính percentile. |
| Hỗ trợ truy vấn | Đọc trực tiếp quantile được công bố. | Dùng hàm như histogram_quantile trong Prometheus. |
| Chi phí | Tạo thêm chuỗi cho mỗi quantile và meter identity. | Có thể tạo nhiều chuỗi bucket cho mỗi meter identity. |
| Trường hợp phù hợp | Xem phân vị cục bộ theo instance. | Dashboard và cảnh báo percentile ở cấp service hoặc nhóm nhiều instance. |

Ví dụ cấu hình Timer xuất histogram:

~~~java
Timer.builder("orders.processing")
        .description("Time spent processing an order")
        .publishPercentileHistogram()
        .register(registry);
~~~

Với Prometheus, truy vấn p95 từ histogram có dạng:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(orders_processing_seconds_bucket[5m])
  )
)
~~~

Truy vấn trên gộp tốc độ quan sát theo bucket le từ các series được chọn rồi ước lượng p95. Trong thực tế, cần giữ lại các label phân nhóm mà dashboard cần, chẳng hạn service hoặc route:

~~~promql
histogram_quantile(
  0.95,
  sum by (service, route, le) (
    rate(orders_processing_seconds_bucket[5m])
  )
)
~~~

Tên metric trong ví dụ cần được thay bằng tên thực tế từ endpoint Prometheus của ứng dụng. Nếu cần các bucket tại những ngưỡng cụ thể phục vụ SLA, có thể cấu hình service level objectives (SLO boundaries) thay vì chỉ dựa vào bucket mặc định.

Có thể bật cả percentile và histogram nếu có nhu cầu rõ ràng cho hai mục đích khác nhau, nhưng cách này làm tăng chi phí. Hãy ưu tiên một cơ chế phù hợp với cách truy vấn chính của hệ thống.

## 9. Chọn percentile nào?

Không nên công bố mọi percentile chỉ vì API cho phép. Mỗi quantile tạo thêm dữ liệu và dashboard có thể trở nên khó đọc. Hãy chọn theo câu hỏi:

| Percentile | Cách dùng thường gặp |
| --- | --- |
| p50 | Theo dõi trải nghiệm điển hình ở giữa phân phối. |
| p90 | Quan sát nhóm request chậm hơn phần lớn request. |
| p95 | Theo dõi tail latency cho nhiều API và SLO. |
| p99 | Phát hiện phần đuôi rất chậm khi lưu lượng đủ lớn. |
| p99.9 | Chỉ dùng khi hệ thống có đủ volume và yêu cầu phân tích tail latency rất cao. |

Percentile cao cần nhiều quan sát để ổn định. Với lưu lượng thấp, p99 có thể thay đổi mạnh chỉ vì một vài request. Trong trường hợp đó, p95 hoặc histogram theo cửa sổ dài hơn có thể hữu ích hơn.

Hãy gắn percentile với mục tiêu vận hành. Nếu SLO quy định 95% request phải hoàn tất dưới 300 ms, p95 là chỉ số trực tiếp để theo dõi mục tiêu đó. Nếu mục tiêu quan tâm số lượng request vượt ngưỡng, histogram với bucket tại ngưỡng SLO có thể hỗ trợ truy vấn tỷ lệ vi phạm tốt hơn.

## 10. Cửa sổ thống kê và độ ổn định của kết quả

Percentile được tính từ phân phối mà meter duy trì trong ứng dụng. Phạm vi quan sát không mặc nhiên là toàn bộ lịch sử kể từ khi ứng dụng khởi động. Cấu hình distribution statistics có thể điều khiển thời hạn và số cửa sổ dữ liệu được giữ; các chi tiết mặc định phụ thuộc phiên bản Micrometer và registry.

Khi diễn giải dashboard:

- Xác định percentile đại diện cho cửa sổ thống kê nào.
- Dùng cùng cấu hình ở các instance để so sánh có ý nghĩa.
- Không so sánh một percentile tính trên cửa sổ ngắn với một percentile tính trên cửa sổ dài mà không ghi rõ khác biệt.
- Đảm bảo lưu lượng trong cửa sổ đủ lớn để percentile cần theo dõi có ý nghĩa.
- Kiểm tra hành vi khi ứng dụng khởi động lại hoặc meter không có quan sát mới.

Một percentile có thể không có giá trị hữu ích khi chưa có đủ quan sát. Dashboard nên thể hiện trạng thái không có dữ liệu thay vì tự thay thế bằng số 0, vì 0 ms có thể bị hiểu nhầm là hệ thống hoạt động rất nhanh.

## 11. Kiểm thử cấu hình percentile

Có thể dùng SimpleMeterRegistry để xác minh meter được tạo với đúng tên, tag và ghi nhận các quan sát. Tuy nhiên, việc kiểm tra giá trị percentile cụ thể có thể phụ thuộc implementation thống kê và cấu hình cửa sổ; tránh viết kiểm thử mong đợi một kết quả chính xác nếu thuật toán chỉ cung cấp ước lượng.

Ví dụ kiểm tra meter và ghi nhận Timer:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class PercentileTimerTest {

    @Test
    void registersTimerWithRequestedPercentiles() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();

        Timer timer = Timer.builder("orders.processing")
                .publishPercentiles(0.50, 0.95, 0.99)
                .register(registry);

        timer.record(() -> {
            // Simulate one completed operation.
        });

        assertThat(registry.find("orders.processing").timer()).isNotNull();
        assertThat(timer.count()).isEqualTo(1);
    }
}
~~~

Để kiểm tra dữ liệu percentile được xuất đúng định dạng, nên có kiểm thử tích hợp với registry thực tế mà ứng dụng triển khai. Với Prometheus, kiểm tra endpoint exposition để xác nhận quantile label xuất hiện và tên metric đúng như truy vấn/dashboard đang dùng.

## 12. Lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Nghĩ p95 là giá trị lớn nhất | Đánh giá sai tail latency. | Hiểu p95 là điểm cắt của phân phối, không phải max. |
| Lấy trung bình p95 giữa các instance | Kết quả không phải p95 toàn service. | Dùng histogram để gộp phân phối. |
| Bật quá nhiều quantile | Tăng số series và chi phí scrape/lưu trữ. | Chọn percentile theo SLO và câu hỏi vận hành. |
| Dùng p99 với lưu lượng quá thấp | Kết quả dao động mạnh và khó diễn giải. | Xem volume, chọn percentile phù hợp hoặc cửa sổ quan sát khác. |
| Dùng percentile local để so sánh tổng thể nhiều pod | Không phản ánh phân phối request đã gộp. | Dùng percentile histogram và truy vấn ở backend. |
| Nhầm percentile với histogram | Chọn sai cơ chế xuất dữ liệu và truy vấn. | Phân biệt quantile đã tính với bucket histogram. |
| Không kiểm tra đơn vị Timer | Đọc mili giây thành giây hoặc ngược lại. | Xác minh đơn vị trong exposition và tên metric. |
| Giả định percentile là lịch sử vô hạn | Dashboard diễn giải sai phạm vi thời gian. | Kiểm tra cấu hình cửa sổ distribution statistics. |
| Dùng tag có cardinality cao | Tạo nhiều bộ percentile và tăng chi phí. | Giới hạn tag vào tập giá trị hữu hạn. |

## 13. Checklist trước khi bật publishPercentiles

- [ ] Đã xác định câu hỏi cần trả lời và percentile phù hợp.
- [ ] Đã chọn đúng meter: Timer cho thời lượng, DistributionSummary cho đại lượng số.
- [ ] Chỉ công bố những percentile thực sự cần dùng.
- [ ] Đã xác định phạm vi thời gian của thống kê phân phối.
- [ ] Đã đánh giá số lượng meter identity và tag-value.
- [ ] Đã hiểu percentile được tính tại từng instance không thể gộp chính xác.
- [ ] Nếu cần percentile toàn service, đã chọn histogram và truy vấn bucket phù hợp.
- [ ] Đã xác minh tên metric, quantile label và đơn vị ở endpoint thực tế.
- [ ] Dashboard phân biệt rõ percentile với max và average.
- [ ] Kiểm thử xác nhận meter ghi nhận quan sát và registry xuất dữ liệu như mong đợi.

publishPercentiles(...) phù hợp khi cần các phân vị được tính ngay tại ứng dụng cho từng meter identity. Cơ chế này cung cấp góc nhìn nhanh về p50, p95 hoặc p99 ở từng instance. Khi câu hỏi yêu cầu một percentile chung sau khi gộp dữ liệu từ nhiều instance, hãy xuất histogram để backend có đủ bucket dữ liệu tính toán phân vị toàn cục.
