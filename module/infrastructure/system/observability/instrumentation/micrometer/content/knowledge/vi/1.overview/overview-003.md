# Phân biệt thư viện đo, bộ thu thập, hệ thống lưu trữ và dashboard

Trong một hệ thống quan sát (observability), metric thường đi qua nhiều thành phần trước khi xuất hiện trên biểu đồ. Ứng dụng tạo ra số đo; một thành phần thu thập lấy hoặc nhận số đo; hệ thống lưu trữ giữ dữ liệu theo thời gian; dashboard truy vấn và trình bày dữ liệu để người vận hành hiểu tình trạng dịch vụ. Bốn vai trò này liên quan chặt chẽ nhưng giải quyết những bài toán khác nhau.

Trong module **OBSERVABILITY_INSTRUMENTATION_MICROMETER**, trọng tâm là dùng Micrometer để đo lường ứng dụng Java bằng **Counter**, **Gauge**, **Timer**, **Distribution Summary** và các nhãn (tag) có kiểm soát. Khi tích hợp Spring Boot, các số đo được xuất đến hệ giám sát để theo dõi, kiểm thử instrumentation và diễn giải hoạt động của ứng dụng. Muốn thiết kế đúng luồng metrics, trước hết cần biết Micrometer đứng ở đâu và các thành phần phía sau chịu trách nhiệm gì.

## 1. Bốn vai trò trong một luồng metrics

### Thư viện đo lường: tạo số đo bên trong ứng dụng

Thư viện đo lường được tích hợp vào mã nguồn hoặc framework của ứng dụng. Nó cung cấp API để ghi nhận những sự kiện và trạng thái có ý nghĩa: số yêu cầu đã xử lý, số tác vụ đang chờ, thời gian xử lý, kích thước payload hoặc số lần một nghiệp vụ thất bại.

**Micrometer** là một facade cho metrics trên JVM. Ứng dụng sử dụng API nhất quán của Micrometer để đăng ký và cập nhật meter, thay vì gắn chặt logic nghiệp vụ với định dạng riêng của một hệ thống giám sát. Những meter thường gặp gồm:

- **Counter**: đếm số sự kiện tích lũy, chẳng hạn số đơn hàng hoàn tất. Counter tăng dần; muốn biết tốc độ sự kiện thường tính mức tăng trong một khoảng thời gian.
- **Gauge**: quan sát giá trị tại thời điểm đọc, chẳng hạn số tác vụ đang nằm trong hàng đợi hoặc số kết nối đang được sử dụng. Giá trị có thể tăng hoặc giảm.
- **Timer**: đo thời lượng và số lần một thao tác được thực hiện. Timer thường cung cấp tổng thời gian, số lần ghi nhận và có thể cung cấp histogram hoặc percentile tùy cấu hình.
- **Distribution Summary**: ghi nhận phân phối của các giá trị không nhất thiết là thời gian, chẳng hạn kích thước phản hồi hoặc số byte xử lý mỗi lần.

Micrometer còn quản lý **MeterRegistry** và các registry triển khai cho từng hệ thống xuất metrics. Registry chuyển meter sang dạng dữ liệu mà đích xuất có thể hiểu. Ví dụ, Prometheus registry trình bày metrics ở định dạng Prometheus để Prometheus server đọc; OTLP registry có thể gửi metrics theo giao thức OTLP đến một endpoint tương thích.

Vì vậy, Micrometer chịu trách nhiệm đo và chuẩn hóa việc xuất số đo ở phía ứng dụng. Nó không phải nơi lưu trữ metrics tập trung trong nhiều ngày, cũng không phải công cụ tạo dashboard.

### Bộ thu thập: lấy metrics từ các ứng dụng hoặc nguồn dữ liệu

Bộ thu thập (collector) đưa metrics từ các nguồn về một luồng giám sát tập trung. Tùy kiến trúc, nó có thể chủ động đọc endpoint theo chu kỳ (pull/scrape), nhận dữ liệu do ứng dụng hoặc agent gửi đến (push/receive), rồi chuyển tiếp hoặc xử lý dữ liệu.

Hai ví dụ thường gặp:

- **Prometheus server** định kỳ scrape endpoint metrics của ứng dụng. Với Spring Boot và Micrometer Prometheus registry, endpoint thường là /actuator/prometheus. Prometheus đọc nội dung endpoint và gắn timestamp cho mẫu dữ liệu được thu thập.
- **OpenTelemetry Collector** có thể nhận metrics qua OTLP hoặc các receiver được cấu hình, áp dụng processor để lọc, đổi tên, bổ sung thuộc tính hay gom lô, sau đó gửi dữ liệu đến một hoặc nhiều backend thông qua exporter.

Collector giúp tách việc lấy dữ liệu khỏi từng ứng dụng. Nhờ đó, nhóm vận hành có thể quản lý chu kỳ thu thập, định tuyến và một số bước xử lý ở tầng hạ tầng. Tuy nhiên, collector không tự tạo ra ý nghĩa nghiệp vụ của metric: ứng dụng vẫn cần instrument đúng chỗ và đặt tên, đơn vị, tag hợp lý.

Không phải kiến trúc nào cũng có một dịch vụ collector riêng. Prometheus server là một ví dụ quan trọng vì cùng một tiến trình có thể vừa scrape metrics vừa lưu chúng vào TSDB tích hợp sẵn.

### Hệ thống lưu trữ: giữ chuỗi thời gian và phục vụ truy vấn

Hệ thống lưu trữ metrics giữ các mẫu số liệu theo thời gian. Một chuỗi thời gian (time series) thường được xác định bởi tên metric cùng tập nhãn, và mỗi mẫu có giá trị gắn với một thời điểm. Hệ thống lưu trữ chịu trách nhiệm ghi dữ liệu, lập chỉ mục, duy trì thời hạn lưu (retention) và cung cấp khả năng truy vấn.

**Prometheus TSDB** là kho chuỗi thời gian tích hợp trong Prometheus server. Với quy mô hoặc yêu cầu lưu trữ dài hạn lớn hơn, tổ chức có thể gửi dữ liệu sang các backend chuyên dụng hoặc mở rộng như Thanos, Grafana Mimir hay VictoriaMetrics. Cách triển khai cụ thể quyết định nơi dữ liệu được giữ, thời gian lưu và cách truy vấn.

Cần phân biệt việc **thu thập** với việc **lưu trữ**, dù một sản phẩm có thể đảm nhiệm cả hai. Nếu Prometheus server scrape ứng dụng rồi ghi mẫu vào TSDB của chính nó, Prometheus đang thực hiện hai vai trò. Nếu dùng OpenTelemetry Collector để nhận và chuyển metrics đến một backend khác, Collector thường làm nhiệm vụ tiếp nhận và chuyển tiếp; backend mới là nơi lưu trữ lâu dài.

### Dashboard: truy vấn và trình bày số liệu cho con người

Dashboard biến kết quả truy vấn thành biểu đồ, bảng, thống kê và các góc nhìn phục vụ vận hành. Người dùng có thể theo dõi xu hướng, so sánh các phiên bản triển khai, lọc theo dịch vụ hoặc môi trường, và phát hiện thay đổi bất thường.

**Grafana** thường được dùng làm dashboard cho metrics. Grafana kết nối đến một data source như Prometheus, gửi truy vấn đến nguồn đó rồi hiển thị kết quả thành panel. Ví dụ, một dashboard của dịch vụ thanh toán có thể gồm:

- Tốc độ giao dịch hoàn tất theo phút.
- Tỷ lệ giao dịch lỗi.
- Độ trễ p95 hoặc p99.
- Số request đang hoạt động hoặc độ sâu hàng đợi.

Grafana không tự đo thời gian xử lý trong mã Java và cũng không mặc nhiên là kho metrics. Nó hiển thị kết quả do data source cung cấp. Grafana có thể hỗ trợ cảnh báo, nhưng việc tạo metric và lưu dữ liệu vẫn thuộc các thành phần khác trong pipeline.

## 2. Luồng dữ liệu điển hình với Micrometer, Prometheus và Grafana

Một cấu hình phổ biến trong ứng dụng Spring Boot dùng Micrometer Prometheus registry có luồng như sau:

~~~mermaid
flowchart LR
    A["Mã Java / Spring Boot"] --> B["Micrometer MeterRegistry"]
    B --> C["Endpoint /actuator/prometheus"]
    D["Prometheus server"] -->|"Scrape định kỳ"| C
    D --> E[("Prometheus TSDB")]
    F["Grafana"] -->|"Truy vấn PromQL"| D
    D -->|"Kết quả truy vấn"| F
~~~

Các bước diễn ra theo thứ tự:

1. Mã ứng dụng cập nhật meter thông qua API Micrometer. Ví dụ, khi một giao dịch thành công, Counter tăng một đơn vị; khi một thao tác kết thúc, Timer ghi nhận thời lượng.
2. Prometheus registry chuyển meter sang định dạng Prometheus. Khi bật Spring Boot Actuator và cấu hình endpoint tương ứng, ứng dụng cung cấp dữ liệu tại /actuator/prometheus.
3. Prometheus server chủ động gọi endpoint theo chu kỳ scrape đã cấu hình. Nếu scrape thành công, các mẫu metrics được ghi vào TSDB của Prometheus.
4. Grafana kết nối đến Prometheus data source và gửi truy vấn PromQL. Kết quả được hiển thị thành panel trên dashboard.

Trong luồng này, ứng dụng không cần gọi Grafana. Prometheus cũng không cần biết cách vẽ biểu đồ. Mỗi thành phần trao đổi dữ liệu qua giao diện hoặc giao thức phù hợp với vai trò của nó.

## 3. Ví dụ tích hợp Micrometer trong Spring Boot

Với Gradle, ứng dụng Spring Boot thường cần Actuator và registry tương ứng. Spring Boot quản lý phiên bản tương thích khi sử dụng dependency management của dự án:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
~~~

Một lớp nhỏ có thể ghi nhận số giao dịch thành công và thời gian xử lý:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

@Component
public class PaymentMetrics {
    private final Counter paymentCompleted;
    private final Timer paymentProcessing;

    public PaymentMetrics(MeterRegistry registry) {
        this.paymentCompleted = Counter.builder("payment.completed")
                .description("So giao dich thanh cong")
                .tag("channel", "web")
                .register(registry);

        this.paymentProcessing = Timer.builder("payment.processing")
                .description("Thoi gian xu ly giao dich")
                .publishPercentileHistogram()
                .register(registry);
    }

    public void recordSuccessfulPayment(Runnable operation) {
        paymentProcessing.record(operation);
        paymentCompleted.increment();
    }
}
~~~

Ví dụ trên minh họa ba điểm:

- Ứng dụng chỉ thao tác với API Micrometer và MeterRegistry được Spring Boot cung cấp.
- Timer đo thời gian thực thi của operation; Counter chỉ tăng sau khi operation chạy thành công.
- Tag channel có tập giá trị hữu hạn. Trong hệ thống thực tế, tag nên mô tả nhóm hoặc trạng thái có số lượng giá trị giới hạn.

Để Prometheus có thể scrape endpoint, cấu hình exposure của Actuator có thể bao gồm:

~~~properties
management.endpoints.web.exposure.include=health,prometheus
~~~

Việc endpoint có thể truy cập được còn phụ thuộc cấu hình bảo mật, cổng quản trị và môi trường triển khai. Không nên mở endpoint metrics ra mạng công cộng nếu chưa có kiểm soát truy cập phù hợp.

Ví dụ cấu hình scrape tối giản cho Prometheus:

~~~yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: checkout-service
    metrics_path: /actuator/prometheus
    static_configs:
      - targets:
          - checkout-service:8080
~~~

Tên host và cổng phải trỏ đến địa chỉ mà Prometheus có thể truy cập từ môi trường chạy của nó. Khi ứng dụng chạy trong container hoặc Kubernetes, target thường được cấu hình bằng DNS service hoặc cơ chế discovery phù hợp thay vì giả định localhost.

Sau khi thêm Prometheus làm data source trong Grafana, có thể tạo panel bằng các truy vấn ví dụ sau. Tên metric bên dưới là dạng Prometheus thường được tạo từ tên meter trong ví dụ; tên cuối cùng cần được xác minh trên endpoint thực tế.

~~~promql
sum(rate(payment_completed_total[5m]))
~~~

Truy vấn này tính tốc độ giao dịch hoàn tất trung bình mỗi giây trong cửa sổ năm phút, cộng gộp qua các chuỗi thời gian.

Nếu histogram của Timer đã được xuất, truy vấn sau ước lượng độ trễ p95:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (rate(payment_processing_seconds_bucket[5m]))
)
~~~

Truy vấn percentile cần histogram bucket. Nếu chỉ xuất count và sum thì không thể suy ra p95 chính xác từ hai giá trị đó. Cấu hình histogram và cách tổng hợp bucket cần nhất quán giữa các instance để kết quả có ý nghĩa.

## 4. Khi nào các vai trò được gộp trong cùng một sản phẩm?

Tên sản phẩm không phải lúc nào cũng tương ứng một-một với vai trò kiến trúc:

| Sản phẩm hoặc thành phần | Vai trò chính | Có thể kiêm nhiệm |
|---|---|---|
| Micrometer | Instrumentation và registry ở phía ứng dụng | Xuất metrics qua định dạng hoặc giao thức của registry |
| Prometheus server | Scrape và thu thập metrics | Lưu trữ chuỗi thời gian bằng TSDB tích hợp, truy vấn bằng PromQL |
| OpenTelemetry Collector | Nhận, xử lý và chuyển tiếp telemetry | Có thể scrape một số nguồn thông qua receiver được cấu hình |
| Prometheus TSDB, Thanos, Mimir, VictoriaMetrics | Lưu trữ và truy vấn metrics | Khả năng mở rộng, liên kết hoặc lưu trữ dài hạn tùy sản phẩm |
| Grafana | Truy vấn và trực quan hóa | Cảnh báo và quản lý dashboard |

Hai kiểu triển khai thường gặp:

**Pull với Prometheus:** Micrometer Prometheus registry phơi bày endpoint; Prometheus chủ động scrape và lưu dữ liệu; Grafana truy vấn Prometheus. Đây là cách đơn giản để bắt đầu với một ứng dụng Spring Boot.

**Đẩy qua OpenTelemetry Collector:** ứng dụng dùng registry hoặc exporter tương thích OTLP để gửi metrics đến Collector; Collector nhận, xử lý và chuyển dữ liệu đến backend lưu trữ; Grafana truy vấn backend đó. Kiểu này hữu ích khi cần chuẩn hóa hoặc định tuyến telemetry qua một tầng trung gian.

Khi thiết kế, hãy xác định rõ thành phần nào đang nhận dữ liệu, thành phần nào giữ dữ liệu và dashboard truy vấn nguồn nào. Việc một sản phẩm có nhiều chức năng không làm mất đi sự khác biệt giữa các trách nhiệm đó.

## 5. Kiểm soát cardinality từ lúc instrument

Mỗi tổ hợp tên metric và tập tag khác nhau có thể tạo thành một chuỗi thời gian riêng. Nếu tag nhận quá nhiều giá trị, số chuỗi thời gian tăng nhanh, làm tăng bộ nhớ, dung lượng lưu trữ và chi phí truy vấn. Hiện tượng này gọi là cardinality cao.

Ví dụ, các tag có tập giá trị nhỏ thường phù hợp:

- method: GET, POST, PUT, DELETE.
- status: success, failure.
- region: các vùng triển khai đã xác định.
- payment_type: card, bank_transfer, wallet.

Các giá trị như userId, orderId, sessionId, email, requestId hoặc URL chứa mã định danh thường không phù hợp làm tag metric. Chúng có thể tạo ra một chuỗi thời gian mới cho gần như mỗi người dùng hoặc mỗi request. Nếu cần điều tra từng sự kiện, log hoặc trace thường phù hợp hơn.

Micrometer cho phép gắn tag ở lúc đăng ký meter hoặc ghi nhận dữ liệu, nhưng quyền kiểm soát cardinality bắt đầu từ thiết kế instrumentation. Không nên đợi đến backend mới xử lý hậu quả của tag có số lượng giá trị không giới hạn.

## 6. Xác định đúng thành phần khi metrics không hiển thị

Khi một panel trống hoặc số liệu không như mong đợi, kiểm tra theo đường đi của dữ liệu sẽ giúp khoanh vùng nhanh hơn:

1. **Ứng dụng có ghi nhận meter không?** Kiểm tra code instrumentation, điều kiện cập nhật Counter/Gauge/Timer và đơn vị đo.
2. **Registry có xuất metric không?** Kiểm tra registry dependency, cấu hình và nội dung endpoint metrics của ứng dụng.
3. **Collector có lấy được dữ liệu không?** Với Prometheus, kiểm tra target, trạng thái scrape và lỗi kết nối. Metric up của target thường giúp xác định scrape có thành công hay không.
4. **Dữ liệu có được lưu không?** Chạy truy vấn trực tiếp trên backend để xác nhận metric và chuỗi thời gian tồn tại trong khoảng cần xem.
5. **Dashboard có truy vấn đúng nguồn không?** Kiểm tra data source, khoảng thời gian, biến lọc, tên metric và biểu thức truy vấn của panel.

Cần phân biệt lỗi thiếu dữ liệu với lỗi hiển thị. Nếu truy vấn trực tiếp trên backend đã có kết quả nhưng panel trống, hãy kiểm tra cấu hình Grafana. Nếu backend không có mẫu dữ liệu, cần quay lại registry, endpoint, collector hoặc cấu hình lưu trữ.

## 7. Cách ghi nhớ ranh giới trách nhiệm

Có thể dùng bốn câu hỏi để xác định thành phần phù hợp:

- **Ứng dụng đo điều gì và đo ở đâu?** Dùng Micrometer để instrument Counter, Gauge, Timer, Distribution Summary và tag.
- **Ai lấy hoặc nhận số đo?** Dùng Prometheus scrape endpoint hoặc OpenTelemetry Collector nhận và chuyển tiếp dữ liệu.
- **Dữ liệu được giữ và truy vấn ở đâu?** Xác định TSDB hoặc metrics backend, retention và khả năng truy vấn.
- **Người vận hành xem số liệu bằng cách nào?** Dùng Grafana hoặc dashboard tương đương kết nối đến backend.

Khi các ranh giới này rõ ràng, việc tích hợp Micrometer trong Java trở nên dễ kiểm soát hơn: mã ứng dụng tập trung tạo ra số đo đúng nghĩa, tầng thu thập đảm nhiệm việc lấy dữ liệu, backend quản lý vòng đời chuỗi thời gian và dashboard giúp diễn giải số liệu vận hành.
