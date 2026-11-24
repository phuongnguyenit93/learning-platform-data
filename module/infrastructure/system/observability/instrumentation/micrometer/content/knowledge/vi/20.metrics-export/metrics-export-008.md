# Quản lý lịch công bố, kết nối và tài nguyên khi đóng ứng dụng

Xuất metrics không chỉ là đăng ký meter và mở một endpoint. Một registry có thể gửi dữ liệu định kỳ đến backend, hoặc chờ Prometheus chủ động scrape endpoint. Với registry push, lịch công bố, cửa sổ thống kê, kết nối mạng và việc dừng scheduler đều ảnh hưởng đến độ tin cậy của dữ liệu. Với registry pull, vòng đời endpoint và thời điểm target rời service discovery quyết định Prometheus có lấy được những mẫu cuối cùng hay không.

Khi ứng dụng đóng, các tài nguyên liên quan đến metrics cũng cần được xử lý theo thứ tự: ngừng nhận công việc mới, hoàn tất hoặc hủy có kiểm soát các tác vụ đang chạy, cho phép lần công bố cuối nếu registry hỗ trợ, rồi đóng registry và client do ứng dụng sở hữu. Không nên giả định mọi registry đều tự gửi một bản cuối cùng khi close; hành vi đó phụ thuộc loại registry và phiên bản triển khai.

## 1. Phân biệt mô hình push và pull

Micrometer hỗ trợ nhiều registry với cách chuyển dữ liệu khác nhau. Hai mô hình phổ biến là push và pull:

| Đặc điểm | Push registry | Pull registry |
| --- | --- | --- |
| Bên chủ động | Ứng dụng gửi dữ liệu đến backend. | Backend như Prometheus gọi endpoint của ứng dụng. |
| Lịch thu thập | Registry thường có lịch publish định kỳ. | Prometheus quyết định scrape interval. |
| Kết nối | Ứng dụng cần kết nối ra backend, thường qua HTTP hoặc giao thức riêng. | Prometheus cần kết nối vào endpoint metrics của ứng dụng. |
| Khi ứng dụng đóng | Cần dừng lịch publish và giải phóng tài nguyên gửi dữ liệu. | Cần phối hợp thời điểm endpoint ngừng phục vụ và target rời service discovery. |
| Ví dụ | Datadog, Graphite, Influx hoặc một số exporter push. | Prometheus registry được scrape qua endpoint. |

Không nên áp dụng một lịch publish cho mọi registry. Với Prometheus pull, ứng dụng không cần tự gửi metrics theo chu kỳ; Prometheus scrape endpoint theo cấu hình của nó. Với push registry, chu kỳ publish thường được cấu hình trong registry hoặc client tương ứng.

## 2. Hiểu lịch publish và step window

Push registry thường gửi dữ liệu theo một chu kỳ. Với các registry dựa trên StepMeterRegistry, cấu hình step xác định khoảng thời gian thống kê mà dữ liệu tích lũy được chốt và công bố. Ví dụ step 30 giây có nghĩa backend nhận một lượt công bố theo chu kỳ xấp xỉ 30 giây, tùy lịch khởi động và cơ chế đồng bộ của registry.

Step không đơn giản là thời gian chờ trước lần gửi đầu tiên. Nó còn liên quan đến cách registry tính toán Counter, Timer, DistributionSummary và các thống kê theo cửa sổ:

- Counter dạng step có thể phản ánh số tăng trong một step thay vì tổng tích lũy từ khi tiến trình khởi động.
- Timer và DistributionSummary có thể công bố count, tổng và phân phối của các quan sát thuộc step.
- Giá trị của một step có thể được chốt khi chuyển sang cửa sổ kế tiếp.
- Khi ứng dụng đóng giữa step, một phần dữ liệu chưa đến thời điểm công bố có thể chưa được gửi.

Không phải mọi registry đều dùng cùng một mô hình step. Hãy kiểm tra tài liệu của registry và cấu hình cụ thể trước khi diễn giải dữ liệu. Đặc biệt, không giả định step của push registry có cùng ngữ nghĩa với scrape interval của Prometheus.

### Chọn chu kỳ phù hợp

| Chu kỳ | Ưu điểm | Chi phí hoặc rủi ro |
| --- | --- | --- |
| Quá ngắn | Dữ liệu đến backend nhanh hơn. | Tăng số request, overhead mạng, chi phí ingest và áp lực lên backend. |
| Quá dài | Ít request và giảm overhead. | Dashboard và cảnh báo chậm phản ứng; dữ liệu chưa công bố có thể mất khi tiến trình dừng đột ngột. |
| Phù hợp với mục tiêu vận hành | Cân bằng độ trễ quan sát và chi phí. | Cần đo tải, số meter và khả năng backend trước khi chốt. |

Chọn step dựa trên độ trễ cảnh báo mong muốn, số lượng series, giới hạn backend và khả năng chịu tải của ứng dụng. Không đặt step cực ngắn chỉ để biểu đồ trông cập nhật liên tục.

## 3. Phân biệt thời điểm ghi nhận, step và scrape

Ba thời điểm sau có ý nghĩa khác nhau:

1. **Ghi nhận sự kiện:** code gọi increment, record hoặc cập nhật trạng thái Gauge.
2. **Publish step:** push registry chuyển dữ liệu trong cửa sổ và gửi đến backend.
3. **Scrape:** Prometheus đọc dữ liệu đang có trên endpoint.

Một sự kiện có thể được ghi nhận ngay nhưng chưa xuất hiện ở backend push cho đến lần publish kế tiếp. Tương tự, với Prometheus pull, giá trị đã có trong registry nhưng Prometheus chỉ lưu nó ở lần scrape kế tiếp.

Ví dụ:

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant Registry as Micrometer registry
    participant Backend as Backend metrics
    App->>Registry: Counter.increment()
    Note over Registry: Giá trị được cập nhật trong bộ nhớ
    Registry->>Backend: Publish theo step
    Note over Backend: Backend lưu mẫu đã công bố
~~~

Với Prometheus, thay bước publish bằng một request scrape từ Prometheus đến endpoint. Khi điều tra độ trễ dữ liệu, hãy xác định đang nói đến thời điểm ghi nhận, publish hay scrape.

## 4. Cấu hình lịch publish cho push registry

Mỗi registry có cấu hình riêng cho step, endpoint, xác thực và timeout. Ví dụ cấu hình khái quát:

~~~yaml
metrics:
  export:
    push:
      enabled: true
      step: 30s
      connect-timeout: 2s
      read-timeout: 5s
~~~

Đây là cấu trúc minh họa cho ứng dụng; tên property thực tế phải theo registry và Spring Boot integration đang dùng. Không sao chép nguyên các khóa trên vào application.yml nếu thư viện không định nghĩa chúng.

Trong Micrometer, cấu hình của registry thường cung cấp các thuộc tính như URI/endpoint, step hoặc publish interval, connect timeout, read timeout và thông tin xác thực. Nên đưa các giá trị theo môi trường vào configuration thay vì hard-code trong binder hoặc logic nghiệp vụ.

Một số registry khởi động lịch publish trong quá trình khởi tạo; một số API cho phép điều khiển lifecycle riêng. Hãy theo đúng tài liệu của implementation đang dùng. Không tự tạo thêm ScheduledExecutorService để gọi publish nếu registry đã quản lý scheduler của nó.

## 5. Timeout và quản lý kết nối

Kết nối đến backend metrics vẫn là kết nối mạng thông thường và có thể gặp DNS lỗi, TLS handshake chậm, xác thực thất bại, timeout hoặc backend quá tải. Cấu hình timeout giúp giới hạn thời gian một lần publish chiếm tài nguyên.

| Thành phần | Mục đích | Cách chọn |
| --- | --- | --- |
| Connect timeout | Giới hạn thời gian thiết lập kết nối. | Đủ cho DNS, TCP và TLS trong môi trường triển khai; không quá dài khiến scheduler bị giữ lâu. |
| Read/response timeout | Giới hạn thời gian chờ backend phản hồi. | Dựa trên độ trễ thực tế và SLA của backend. |
| Publish step | Quyết định tần suất gửi dữ liệu. | Không nên ngắn hơn khả năng xử lý bền vững của backend. |
| Retry/backoff | Xử lý lỗi tạm thời. | Có giới hạn, tránh retry liên tục hoặc tạo hàng đợi không giới hạn. |
| Connection pool | Tái sử dụng kết nối HTTP nếu client hỗ trợ. | Giới hạn pool và giải phóng khi registry/client đóng. |

Nếu publish bị chậm lâu hơn chu kỳ, các lần gửi có thể chồng lấn hoặc scheduler bị trì hoãn tùy implementation. Hãy kiểm tra hành vi của registry cụ thể, log lỗi publish và các metric về thời gian gửi. Không tự giả định mọi registry đều bỏ qua, xếp hàng hoặc chạy song song theo cùng một cách.

## 6. Xử lý lỗi publish mà không làm ảnh hưởng ứng dụng

Metrics là dữ liệu quan sát, nên lỗi gửi metrics không nên làm hỏng luồng nghiệp vụ chính. Một lần publish thất bại cần được ghi log hoặc theo dõi bằng cơ chế sức khỏe phù hợp, nhưng không nên làm request nghiệp vụ thất bại chỉ vì backend metrics tạm thời không phản hồi.

Các nguyên tắc nên áp dụng:

- Đặt connect/read timeout hữu hạn.
- Giới hạn số lần retry và dùng backoff nếu client hỗ trợ.
- Tránh retry đồng bộ ngay trong thread xử lý request nghiệp vụ.
- Không để queue gửi dữ liệu tăng vô hạn khi backend ngừng hoạt động.
- Theo dõi lỗi export bằng log, health indicator hoặc metric độc lập nếu có thể.
- Tránh ghi lỗi export vào chính một meter cũng đang phụ thuộc hoàn toàn vào backend export bị lỗi.

Không phải mọi backend đều có thể khôi phục dữ liệu đã mất sau một lần publish thất bại. Hãy kiểm tra liệu registry giữ lại dữ liệu để gửi lại, bỏ cửa sổ bị lỗi hay tiếp tục với cửa sổ kế tiếp. Đây là khác biệt quan trọng khi đánh giá mức độ mất dữ liệu có thể chấp nhận.

## 7. Đóng registry và giải phóng tài nguyên

Registry có thể sở hữu hoặc tham chiếu đến scheduler, HTTP client, connection pool, thread và bộ đệm. Nếu ứng dụng tự tạo registry, ứng dụng phải bảo đảm lifecycle của nó được kết thúc đúng cách.

Các bước thường cần xem xét:

1. Ngừng nhận công việc mới để số liệu không tiếp tục tăng trong lúc đóng.
2. Chờ các request hoặc job đang chạy hoàn tất trong giới hạn thời gian cho phép.
3. Ghi nhận trạng thái cuối cùng của các thao tác đã hoàn tất.
4. Nếu registry hỗ trợ flush/publish cuối, gọi theo API và thứ tự mà tài liệu quy định.
5. Dừng scheduler hoặc publisher để không còn lần gửi mới.
6. Đóng registry và các client/tài nguyên mà ứng dụng tự sở hữu.
7. Xác nhận tiến trình kết thúc trong termination grace period của môi trường triển khai.

Không phải registry nào cũng thực hiện một lần publish cuối khi close. Một số registry dừng scheduler và giải phóng tài nguyên; dữ liệu chưa đến step có thể không được gửi. Nếu cần bảo đảm flush cuối, phải kiểm tra API riêng của registry và thực hiện trước khi đóng tài nguyên mạng.

Không gọi close lặp lại từ nhiều component sở hữu khác nhau. Hãy xác định rõ registry được tạo bởi Spring Boot, bởi cấu hình tùy chỉnh hay bởi code thủ công, rồi để đúng một lifecycle owner chịu trách nhiệm đóng nó.

## 8. Spring Boot quản lý registry theo lifecycle bean

Trong ứng dụng Spring Boot, registry được auto-configuration tạo và quản lý như một bean. Khi ApplicationContext đóng, Spring thực hiện callback hủy bean; registry có thể dừng tài nguyên nền và đóng các thành phần thuộc lifecycle của nó.

Nếu dùng registry do Spring Boot tự cấu hình, không cần tạo thêm shutdown hook thủ công để đóng cùng registry. Việc đóng hai lần từ nhiều nơi có thể gây lỗi hoặc làm khó xác định thứ tự lifecycle.

Nếu tự khai báo một registry bean, có thể khai báo destroy method rõ ràng:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MetricsExportConfiguration {

    @Bean(destroyMethod = "close")
    MeterRegistry customMeterRegistry() {
        return createConfiguredRegistry();
    }

    private MeterRegistry createConfiguredRegistry() {
        // Create and configure the registry for the selected backend.
        throw new UnsupportedOperationException("Provide backend configuration");
    }
}
~~~

Đây là khung minh họa; thay phần tạo registry bằng implementation và cấu hình backend thực tế. Nếu bean được quản lý bởi một auto-configuration khác hoặc đã có lifecycle callback riêng, không thêm một đường close thứ hai.

Với bean client do ứng dụng tạo riêng, hãy để Spring quản lý client đó bằng destroy method hoặc lifecycle interface tương ứng. Đảm bảo registry và client có thứ tự đóng hợp lý: publisher phải ngừng sử dụng client trước khi client bị đóng.

## 9. Thứ tự shutdown khi có công việc đang chạy

Nếu đóng registry quá sớm, các request hoặc job còn lại có thể tiếp tục ghi meter sau khi exporter đã dừng. Nếu đợi vô hạn cho mọi công việc, ứng dụng có thể vượt thời gian shutdown mà nền tảng cho phép.

Một thứ tự tổng quát:

~~~mermaid
flowchart TD
    A[Nhận tín hiệu shutdown] --> B[Ngừng nhận công việc mới]
    B --> C[Drain request và job đang chạy]
    C --> D[Ghi nhận kết quả cuối]
    D --> E[Flush nếu registry hỗ trợ]
    E --> F[Đóng registry và publisher]
    F --> G[Đóng client/tài nguyên còn lại]
    G --> H[Tiến trình kết thúc]
~~~

Các bước có thể được điều chỉnh theo framework và registry, nhưng nguyên tắc là không đóng client trước publisher đang sử dụng client. Cũng không nên dừng MeterRegistry trong khi các component khác vẫn cần ghi nhận số liệu cuối.

Đặt thời hạn drain phù hợp. Nếu hết thời gian, cần có chính sách rõ ràng: hủy tác vụ còn lại, ghi log, kết thúc shutdown và chấp nhận phần metrics chưa được công bố. Metrics không nên khiến tiến trình vượt quá thời hạn kết thúc của nền tảng.

## 10. Xử lý lần publish cuối

Lần publish cuối có thể hữu ích khi ứng dụng kết thúc bình thường và cần gửi phần dữ liệu đã tích lũy. Tuy nhiên, có ba điều cần xác minh:

- Registry có API flush/publish thủ công hay không.
- API đó có gửi cả dữ liệu chưa đến step hay chỉ đẩy dữ liệu đã được chốt.
- API có đồng bộ và chờ backend phản hồi hay chỉ lên lịch công việc bất đồng bộ.

Không gọi một phương thức publish giả định trên MeterRegistry chung. Các API flush/publish là đặc thù của implementation; dùng sai có thể không biên dịch hoặc tạo hành vi khác kỳ vọng.

Nếu registry không hỗ trợ flush cuối, hãy chọn step và termination policy sao cho phần dữ liệu có thể mất khi shutdown nằm trong giới hạn chấp nhận được. Nếu cần lưu chính xác từng sự kiện, metrics không thay thế event log hoặc cơ sở dữ liệu bền vững.

## 11. Prometheus pull khi ứng dụng shutdown

Prometheus registry thường không có lịch gửi định kỳ từ ứng dụng. Ứng dụng expose endpoint để Prometheus scrape. Khi shutdown, điều cần phối hợp là endpoint còn phục vụ trong khoảng thời gian target vẫn được service discovery xem là tồn tại.

Trong môi trường orchestrator:

- Đánh dấu instance không còn nhận traffic mới qua readiness hoặc cơ chế tương đương.
- Cho phép request đang chạy hoàn tất trong thời hạn drain.
- Giữ endpoint metrics hoạt động trong thời gian cần thiết nếu Prometheus vẫn có thể scrape target.
- Sau đó mới kết thúc tiến trình và để service discovery loại target.

Không nên dựa vào một lần scrape cuối như một bảo đảm tuyệt đối. Prometheus có lịch scrape riêng; ứng dụng có thể kết thúc trước lần scrape kế tiếp. Nếu cần theo dõi sự kiện shutdown, có thể công bố trạng thái lifecycle hoặc thời điểm bắt đầu tiến trình trong thời gian ứng dụng còn hoạt động, đồng thời dựa vào up và service discovery để nhận biết target đã dừng.

Khi target không còn scrape được, Prometheus sẽ đánh dấu các series của target là stale và đặt up bằng 0 trong lúc target vẫn được theo dõi. Nếu target bị loại khỏi service discovery hoàn toàn, series up tương ứng cũng có thể biến mất; cảnh báo cần tính đến cả hai trường hợp.

## 12. Đóng CompositeMeterRegistry và nhiều registry

CompositeMeterRegistry chuyển các meter đến registry con đã được thêm vào composite. Khi dùng nhiều backend, cần xác định ai sở hữu từng registry con và ai chịu trách nhiệm đóng chúng.

Các nguyên tắc:

- Không đóng một registry con trong khi composite hoặc component khác vẫn cần sử dụng nó.
- Tránh để hai bean cùng chịu trách nhiệm close một registry.
- Nếu ứng dụng tự tạo registry con, khai báo lifecycle rõ ràng.
- Đóng publisher và client theo thứ tự phụ thuộc.
- Kiểm tra cách CompositeMeterRegistry xử lý registry con khi close trong phiên bản Micrometer đang dùng; không giả định mọi registry con đều được đóng tự động theo cùng một chính sách.

Nếu một registry được chia sẻ ngoài ApplicationContext, cần có owner ở cấp cao hơn quản lý vòng đời. Không đóng tài nguyên dùng chung chỉ vì một component riêng lẻ kết thúc.

## 13. Ví dụ quản lý registry thủ công

Với ứng dụng Java không dùng Spring Boot, nơi code tự tạo registry, dùng một lifecycle owner duy nhất:

~~~java
import io.micrometer.core.instrument.MeterRegistry;

public final class MetricsRuntime implements AutoCloseable {

    private final MeterRegistry registry;

    public MetricsRuntime(MeterRegistry registry) {
        this.registry = registry;
    }

    public MeterRegistry registry() {
        return registry;
    }

    @Override
    public void close() {
        registry.close();
    }
}
~~~

Sử dụng trong phạm vi có vòng đời rõ ràng:

~~~java
try (MetricsRuntime metrics = new MetricsRuntime(createRegistry())) {
    runApplication(metrics.registry());
}
~~~

Ví dụ này thể hiện quyền sở hữu: MetricsRuntime chịu trách nhiệm đóng registry đã được truyền vào. Chỉ dùng mô hình này khi đối tượng thật sự sở hữu registry. Nếu registry được chia sẻ hoặc được framework quản lý, không bọc nó trong owner thứ hai có thể đóng tài nguyên quá sớm.

Đối với ứng dụng có công việc bất đồng bộ, runApplication phải hoàn tất hoặc drain các tác vụ cần thiết trước khi khối try kết thúc. Nếu không, registry có thể bị đóng khi worker vẫn đang ghi meter.

## 14. Tránh tạo scheduler và HTTP client trùng lặp

Một lỗi thiết kế là tự tạo scheduler hoặc HTTP client mới cho mỗi lần khởi tạo binder hoặc mỗi meter. Điều này có thể làm số thread, connection pool và tài nguyên socket tăng theo số component.

Nên:

- Để registry quản lý scheduler publish của nó.
- Dùng client được cấu hình và quản lý theo lifecycle rõ ràng.
- Tái sử dụng connection pool khi implementation hỗ trợ.
- Không tạo một publisher riêng cho từng meter.
- Không gọi bindTo hoặc đăng ký registry lặp lại chỉ để kích hoạt lịch gửi.
- Đóng client sau khi publisher đã dừng.

MeterBinder chỉ đăng ký meter; nó không nên trở thành nơi tạo scheduler, khởi động thread nền hoặc quản lý kết nối backend.

## 15. Kiểm thử lịch publish và shutdown

Kiểm thử lifecycle cần xác minh hành vi quan sát được thay vì phụ thuộc vào sleep dài hoặc timing ngẫu nhiên. Có thể dùng fake HTTP server, mock transport hoặc registry test phù hợp với implementation.

Các tình huống nên kiểm tra:

1. Registry push công bố theo chu kỳ đã cấu hình.
2. Publish thất bại do timeout không làm request nghiệp vụ thất bại.
3. Lỗi tạm thời được xử lý theo retry/backoff có giới hạn.
4. Đóng registry dừng scheduler và không phát sinh lần gửi mới sau khi shutdown hoàn tất.
5. Nếu có API flush cuối, xác minh nó được gọi trước khi client bị đóng.
6. Registry pull tiếp tục expose metrics trong thời gian drain dự kiến.
7. Nhiều registry không đóng nhầm client hoặc registry con đang được chia sẻ.
8. Shutdown có thời hạn và không chờ vô hạn khi backend metrics không phản hồi.

Ví dụ kiểm thử quyền sở hữu registry thủ công:

~~~java
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

import io.micrometer.core.instrument.MeterRegistry;
import org.junit.jupiter.api.Test;

class MetricsRuntimeTest {

    @Test
    void closesTheRegistryItOwns() {
        MeterRegistry registry = mock(MeterRegistry.class);

        try (MetricsRuntime runtime = new MetricsRuntime(registry)) {
            // Application work uses runtime.registry().
        }

        verify(registry).close();
    }
}
~~~

Đây là kiểm thử đơn vị cho trách nhiệm đóng tài nguyên. Với push registry thật, cần thêm kiểm thử tích hợp để xác minh scheduler, HTTP client và hành vi gửi dữ liệu theo tài liệu của implementation.

## 16. Quan sát chính publisher

Để vận hành export đáng tin cậy, nên theo dõi chính đường xuất dữ liệu:

- Thời gian mỗi lần publish.
- Số lần publish thành công và thất bại.
- Lỗi kết nối, timeout, xác thực và phản hồi backend.
- Số lần retry và độ trễ backoff.
- Trạng thái scheduler hoặc lần publish thành công gần nhất.
- Số lượng meter/series được xuất.

Không tạo tag động từ exception message, URL có token hoặc request ID cho metric export. Dùng loại lỗi đã chuẩn hóa như timeout, connection, authentication hoặc server_error để giữ cardinality thấp.

Nếu publisher bị lỗi và backend nhận metrics không còn hoạt động, hãy bảo đảm vẫn có đường chẩn đoán khác như log cục bộ, health endpoint hoặc telemetry của nền tảng. Không thể dựa hoàn toàn vào chính backend đang lỗi để báo rằng export bị lỗi.

## 17. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Nhầm scrape interval với push step | Đọc sai độ trễ cập nhật và cửa sổ thống kê. | Phân biệt lịch scrape của Prometheus với lịch publish của push registry. |
| Đặt step quá ngắn | Tăng request, overhead và chi phí ingest. | Chọn chu kỳ theo mục tiêu vận hành và khả năng backend. |
| Timeout không giới hạn | Thread publish có thể bị giữ lâu và làm chậm shutdown. | Cấu hình connect/read timeout hữu hạn. |
| Retry không giới hạn | Tạo tải dây chuyền hoặc hàng đợi gửi tăng vô hạn. | Giới hạn retry, dùng backoff và giới hạn queue. |
| Giả định close luôn gửi dữ liệu cuối | Dữ liệu của step chưa hoàn tất có thể bị bỏ qua. | Kiểm tra API flush của registry và thiết kế termination policy. |
| Đóng HTTP client trước registry | Publisher không còn client để gửi dữ liệu cuối. | Dừng/flush publisher trước rồi mới đóng client. |
| Đóng registry quá sớm | Tác vụ còn chạy ghi metrics vào registry đã đóng. | Ngừng nhận việc mới và drain tác vụ trước. |
| Đóng registry hai lần từ nhiều bean | Lifecycle khó đoán và có thể gây lỗi. | Chỉ định một owner duy nhất. |
| Tạo scheduler/client trong mỗi binder | Tăng thread, socket và tài nguyên. | Để registry hoặc một component lifecycle quản lý dùng chung. |
| Chờ scrape cuối khi target đã bị gỡ | Prometheus không còn target để scrape. | Phối hợp readiness, drain và service discovery. |

## 18. Checklist trước khi phát hành

- [ ] Đã xác định registry dùng push hay pull.
- [ ] Step/publish interval không bị nhầm với scrape interval.
- [ ] Chu kỳ publish phù hợp với độ trễ quan sát và chi phí backend.
- [ ] Connect timeout và read timeout là hữu hạn.
- [ ] Retry/backoff có giới hạn và không tạo hàng đợi vô hạn.
- [ ] Đã hiểu registry có giữ dữ liệu khi publish thất bại hay không.
- [ ] Đã xác minh hành vi close và khả năng flush cuối của registry.
- [ ] Chỉ một component sở hữu trách nhiệm đóng từng registry.
- [ ] Spring Boot auto-managed registry không bị đóng thủ công lần thứ hai.
- [ ] Tác vụ đang chạy được drain trước khi registry dừng.
- [ ] Publisher dừng trước khi HTTP client/connection pool bị đóng.
- [ ] Prometheus endpoint còn phục vụ trong thời gian target cần được scrape.
- [ ] Shutdown hoàn tất trong thời hạn nền tảng cho phép.
- [ ] Có log hoặc health signal để chẩn đoán lỗi export.

Quản lý lịch công bố và shutdown tốt giúp metrics phản ánh đúng dữ liệu đã ghi nhận, hạn chế mất dữ liệu ở cuối vòng đời và không để scheduler hoặc kết nối tồn tại sau khi ứng dụng dừng. Hãy bắt đầu bằng việc xác định push hay pull, sau đó quản lý step, timeout, retry và lifecycle theo đúng registry cụ thể đang sử dụng.
