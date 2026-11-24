# Observability trong vòng đời ứng dụng

Một ứng dụng Spring Boot có thể chạy tốt trên máy lập trình viên nhưng phản hồi chậm, lỗi từng phần hoặc hoạt động khác thường khi phục vụ người dùng thật. Để hiểu *vì sao* điều đó xảy ra, đội phát triển cần có dữ liệu về hành vi bên trong hệ thống, kể cả khi chưa biết trước câu hỏi cần điều tra. Đó là mục đích của **observability**.

Observability không chỉ xuất hiện sau khi ứng dụng lên production. Nó là một năng lực được thiết kế, hiện thực, kiểm thử, triển khai, sử dụng và cải tiến xuyên suốt vòng đời phần mềm. Với Spring Boot, **Micrometer Observation**, **metrics**, **logs** và **distributed tracing** giúp biến những hoạt động trong mã nguồn thành tín hiệu có thể liên kết để xác định lỗi, phân tích độ trễ và hiểu hành vi thực tế của ứng dụng.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vai trò của observability tại từng giai đoạn từ thiết kế đến xử lý sự cố và cải tiến.
- Chuyển hành trình người dùng thành SLI, SLO, tín hiệu đo lường và yêu cầu kiểm thử.
- Phân biệt metrics, logs và traces, đồng thời biết cách liên kết chúng khi điều tra một yêu cầu bị lỗi hoặc chậm.
- Vận dụng Micrometer Observation và cơ chế truyền ngữ cảnh trong ứng dụng Spring Boot.
- Nhận biết những quyết định ảnh hưởng đến chi phí và chất lượng dữ liệu: tag/cardinality, sampling, exporter, bảo mật và khả năng chịu lỗi.
- Xác định tiêu chí nghiệm thu observability trước khi triển khai và cách sử dụng dữ liệu để cải tiến hệ thống.

## 1. Từ monitoring đến observability trong vòng đời phần mềm

**Monitoring** thường bắt đầu bằng những câu hỏi đã biết: CPU có quá 80% không, số lỗi HTTP 5xx có tăng không, dịch vụ có còn sẵn sàng không? **Observability** cho phép tiếp tục tìm hiểu các hiện tượng chưa lường trước: vì sao chỉ một nhóm request chậm, chậm ở bước nào, có liên quan đến bản phát hành mới hay một dịch vụ phụ thuộc hay không?

Ba loại tín hiệu thường bổ sung cho nhau:

| Tín hiệu | Trả lời tốt câu hỏi | Ví dụ trong dịch vụ đặt hàng | Giới hạn cần nhớ |
| --- | --- | --- | --- |
| **Metrics** | Có bao nhiêu, nhanh/chậm đến mức nào, xu hướng thay đổi ra sao? | Số request, tỷ lệ 5xx, p95 thời gian xử lý, số kết nối đang dùng | Dữ liệu tổng hợp khó cho biết chuyện gì xảy ra trong *một* request cụ thể |
| **Logs** | Tại thời điểm đó ứng dụng ghi nhận sự kiện hoặc quyết định gì? | Từ chối đơn do hết hàng, timeout khi gọi kho, lỗi xác thực | Log thiếu cấu trúc hoặc thiếu ngữ cảnh khó tìm kiếm và ghép nối |
| **Distributed traces** | Một request đi qua các thành phần nào và mất thời gian ở đâu? | API đặt hàng → kiểm tra tồn kho → tính phí → lưu đơn | Sampling có thể khiến một số request không có trace lưu lại |

Một **Observation** trong Micrometer là cách biểu diễn một hoạt động cần quan sát. Tùy các handler và thư viện đã cấu hình, cùng một observation có thể tạo ra phép đo thời gian cho metrics và span cho tracing. Logs thường được phát sinh riêng qua thư viện logging, rồi liên kết với traces nhờ ngữ cảnh như **trace ID** và **span ID**.

Vòng đời áp dụng observability có dạng:

~~~mermaid
flowchart LR
    A["Thiết kế mục tiêu và SLO"] --> B["Phát triển và instrument"]
    B --> C["Kiểm thử và xác minh tín hiệu"]
    C --> D["Triển khai và đánh giá thay đổi"]
    D --> E["Vận hành và cảnh báo"]
    E --> F["Điều tra, khắc phục, cải tiến"]
    F --> A
~~~

Mỗi vòng lặp tạo ra hiểu biết mới: một sự cố có thể dẫn đến thêm chỉ số về hàng đợi; một bài kiểm thử tải có thể cho thấy tag quá nhiều giá trị; một lần rollback có thể làm rõ tín hiệu nào thực sự dự báo rủi ro.

## 2. Thiết kế: bắt đầu từ hành vi người dùng và mục tiêu dịch vụ

### 2.1. Xác định hành trình và điểm có thể thất bại

Giả sử một hệ thống gồm **order-service** (Spring Boot), **inventory-service**, cơ sở dữ liệu và hàng đợi sự kiện. Hành trình chính là:

1. Client gửi yêu cầu tạo đơn.
2. order-service xác thực và kiểm tra dữ liệu.
3. order-service gọi inventory-service để giữ hàng.
4. Ứng dụng lưu đơn vào cơ sở dữ liệu.
5. Ứng dụng trả kết quả và phát sự kiện cần thiết.

Các câu hỏi thiết kế observability nên xuất phát từ tác động đến người dùng:

- Khi tạo đơn thất bại, ta phân biệt lỗi đầu vào (4xx), lỗi nội bộ (5xx) và lỗi từ dịch vụ phụ thuộc như thế nào?
- Nếu request mất 3 giây, thời gian chủ yếu nằm ở xác thực, gọi tồn kho, chờ kết nối hay truy vấn cơ sở dữ liệu?
- Nếu đã trả HTTP 200/201 nhưng phát sự kiện thất bại, dấu hiệu nào cho biết quy trình nghiệp vụ chưa hoàn tất?
- Một request chậm có làm tăng độ sâu hàng đợi hoặc khiến connection pool cạn kiệt không?

Không phải hành trình nào cũng đo bằng trạng thái HTTP. Với xử lý bất đồng bộ, cần đo cả **độ trễ hoàn tất công việc**, **số lần retry**, **tuổi thông điệp cũ nhất**, **dead-letter queue** và trạng thái nghiệp vụ phù hợp.

### 2.2. Chuyển nhu cầu thành SLI, SLO và tiêu chí chấp nhận

- **SLI (Service Level Indicator)**: đại lượng đo trải nghiệm hoặc độ tin cậy, ví dụ tỷ lệ request tạo đơn thành công hoặc tỷ lệ request hoàn thành trong 800 ms.
- **SLO (Service Level Objective)**: mục tiêu của SLI trong một khoảng thời gian, ví dụ ít nhất 99,9% request hợp lệ hoàn thành thành công trong 30 ngày.
- **Error budget**: phần sai lệch được phép so với SLO. Tốc độ tiêu thụ error budget giúp cân bằng phát hành tính năng và xử lý độ tin cậy.

Ví dụ một bảng thiết kế cho API tạo đơn:

| Mối quan tâm | SLI minh họa | Tín hiệu cần có | Chú ý |
| --- | --- | --- | --- |
| Khả dụng | Số request hợp lệ hoàn thành thành công / tổng request hợp lệ | Request count theo route, method, status/outcome | Xác định rõ 4xx nào do người dùng, trường hợp nào là lỗi dịch vụ |
| Độ trễ | Tỷ lệ request hoàn thành dưới 800 ms; thêm p95 để chẩn đoán | Histogram thời gian HTTP và thời gian từng phụ thuộc | Đo ở ranh giới mà người dùng thực sự cảm nhận |
| Xử lý nền | Tỷ lệ sự kiện được xử lý trước hạn | Counter kết quả, histogram thời gian, queue age | HTTP thành công không bảo đảm công việc nền đã hoàn tất |
| Năng lực hệ thống | Độ sâu hàng đợi, mức bận của thread/connection pool | Gauge và metric hạ tầng phù hợp | Đây là chỉ báo hỗ trợ, không thay thế SLI trải nghiệm |

**Quan trọng:** SLO cần quy định cách tính, phạm vi request, mốc thời gian, hệ thống đo và việc xử lý dữ liệu bị thiếu. Nếu không, các nhóm có thể cùng nói “99,9%” nhưng tính ra những kết quả khác nhau.

### 2.3. Lập hợp đồng tín hiệu trước khi viết mã

Với mỗi phép đo hoặc sự kiện, nên xác định:

- **Tên ổn định và đơn vị:** thời gian dùng giây ở phía Prometheus, số lượng dùng counter, giá trị hiện thời dùng gauge khi thích hợp.
- **Các thuộc tính/tags:** ví dụ route đã chuẩn hóa, phương thức HTTP, outcome, loại phụ thuộc.
- **Độ phân giải và thời gian lưu:** phân biệt dữ liệu dùng cho cảnh báo ngắn hạn với dữ liệu dùng phân tích dài hạn.
- **Ngữ cảnh liên kết:** trace ID, span ID, service name, môi trường, phiên bản triển khai.
- **Chủ sở hữu và hành động:** ai đọc dashboard, ai nhận cảnh báo, tín hiệu nào dẫn đến rollback hoặc điều tra.

Không đưa email, access token, địa chỉ cá nhân, order ID, user ID hay đường dẫn có định danh tự do vào **metric tag**. Một nhãn có hàng triệu giá trị có thể làm tăng số time series và chi phí thu thập rất nhanh. Chỉ giữ tập nhãn có số lượng giá trị hữu hạn và có ích để tổng hợp.

## 3. Phát triển: instrument tại ranh giới có ý nghĩa

Spring Boot kết hợp Actuator và Micrometer có thể tự tạo nhiều metric và observation cho HTTP server/client, JVM và một số thành phần được hỗ trợ. Tuy nhiên, instrumentation tự động không tự hiểu các bước nghiệp vụ như “giữ hàng thành công” hoặc “đơn đã được phát sự kiện”.

### 3.1. Luồng tín hiệu đi ra khỏi ứng dụng

~~~mermaid
flowchart TB
    App["Spring Boot: HTTP, nghiệp vụ, dữ liệu"] --> Obs["Micrometer Observation"]
    Obs --> Met["MeterRegistry / metrics"]
    Obs --> Tra["Tracing bridge / spans"]
    App --> Log["Application logs có trace ID"]
    Met --> Prom["/actuator/prometheus → Prometheus → Grafana"]
    Tra --> OTLP["OTLP exporter → Collector → trace backend"]
    Log --> Logs["Log collector → log backend"]
~~~

Ba nhánh cần được cấu hình và xác minh riêng. Ví dụ trace gửi qua OTLP không đồng nghĩa logs tự động đi tới hệ thống lưu log; trace ID xuất hiện trong logs cũng không chứng minh trace đã được exporter gửi thành công.

### 3.2. Cấu hình tham khảo với Spring Boot 3.x

Ví dụ Gradle sử dụng dependency management của Spring Boot:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'
}
~~~

Ví dụ cấu hình cho một môi trường phát triển có OTLP Collector tại localhost:

~~~yaml
spring:
  application:
    name: order-service

management:
  endpoints:
    web:
      exposure:
        include: "health,info,prometheus"
  metrics:
    tags:
      application: order-service
    distribution:
      percentiles-histogram:
        http.server.requests: true
  tracing:
    sampling:
      probability: 0.1
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces

logging:
  pattern:
    level: "%5p [traceId=%X{traceId:-},spanId=%X{spanId:-}]"
~~~

Ý nghĩa và giới hạn của ví dụ:

- **Actuator** cung cấp các endpoint quản trị; khi có Prometheus registry, endpoint **/actuator/prometheus** phơi bày metric để Prometheus scrape. Endpoint phải được giới hạn truy cập phù hợp, đặc biệt ở production.
- **Tracing bridge** kết nối Micrometer Tracing với OpenTelemetry. **OTLP exporter** gửi span đến đích đã cấu hình; Collector và trace backend phải đang chạy thì dữ liệu mới được lưu và truy vấn.
- **Sampling probability = 0.1** lấy mẫu khoảng 10% trace theo cấu hình xác suất. Metrics HTTP tiếp tục được tổng hợp độc lập với việc trace có được lấy mẫu hay không.
- **Histogram** làm tăng số series và dung lượng lưu trữ, nhưng cần cho phép tính phân vị phía Prometheus. Chỉ bật cho những phép đo thực sự cần truy vấn phân vị.
- Mẫu logging cho thấy cách bổ sung trace ID và span ID từ MDC. Nếu dự án dùng cấu hình Logback hoặc JSON logging tùy chỉnh, phải kiểm tra output thực tế vì layout mặc định có thể đã thay đổi.

Các tên artifact, thuộc tính và cơ chế tự cấu hình có thể thay đổi giữa các dòng Spring Boot; khi triển khai vào dự án cụ thể, cần đối chiếu phiên bản Boot/Micrometer đang sử dụng. Trong production, đích OTLP, quyền truy cập Actuator, cấu hình TLS, credentials, resource attributes và tần suất sampling phải được quản lý theo môi trường.

### 3.3. Tạo Observation cho một thao tác nghiệp vụ

Khi gọi giữ hàng là một điểm có giá trị để điều tra độ trễ, có thể bao quanh nó bằng một observation:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class ReservationService {
    private final ObservationRegistry observationRegistry;
    private final InventoryClient inventoryClient;

    public ReservationService(
            ObservationRegistry observationRegistry,
            InventoryClient inventoryClient) {
        this.observationRegistry = observationRegistry;
        this.inventoryClient = inventoryClient;
    }

    public void reserve(String sku, int quantity) {
        Observation.createNotStarted("inventory.reserve", observationRegistry)
                .lowCardinalityKeyValue("operation", "reserve")
                .observe(() -> inventoryClient.reserve(sku, quantity));
    }
}
~~~

Trong ví dụ, **InventoryClient** là thành phần do ứng dụng định nghĩa, có phương thức **reserve(sku, quantity)**. Phương thức **observe** quản lý thời điểm bắt đầu/kết thúc observation và ghi nhận lỗi nếu thao tác ném exception. Khi registry có các handler thích hợp, hoạt động này có thể xuất hiện trong metrics và tracing.

Một observation nên đại diện cho thao tác có ý nghĩa và ranh giới rõ ràng. Không tạo span cho mọi dòng mã, mọi phép gán biến hoặc mỗi phần tử trong vòng lặp lớn: tín hiệu quá chi tiết vừa tốn tài nguyên vừa che khuất bước xử lý quan trọng.

### 3.4. Truyền ngữ cảnh giữa service và tác vụ bất đồng bộ

Một trace có thể bao gồm nhiều span. **Trace ID** nhận diện toàn bộ chuỗi xử lý; **span ID** nhận diện một bước. Khi service A gọi service B, ngữ cảnh phải được truyền qua HTTP headers hoặc cơ chế tương đương để hai service thuộc cùng trace. Chuẩn phổ biến là **W3C Trace Context**, với header **traceparent** và có thể có **tracestate**.

Trong Spring Boot, hãy ưu tiên HTTP client được tạo từ builder do Spring tự cấu hình, ví dụ **RestClient.Builder** hoặc **WebClient.Builder**, để nhận instrumentation/propagation tương ứng. Tự tạo client ngoài cơ chế cấu hình có thể làm mất observation hoặc header truyền trace.

Với thread pool, callback hoặc **@Async**, ngữ cảnh hiện tại không mặc nhiên xuất hiện trên một thread khác. Ví dụ sau minh họa cách gắn **ContextPropagatingTaskDecorator** vào executor riêng trên Spring Framework 6.1+ (thường đi cùng Spring Boot 3.2+):

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
class AsyncConfiguration {
    @Bean("observedExecutor")
    ThreadPoolTaskExecutor observedExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        executor.initialize();
        return executor;
    }
}
~~~

Một phương thức gắn **@Async("observedExecutor")** sử dụng executor này. Với Reactor, messaging hoặc thư viện thực thi khác, phải kiểm tra cơ chế truyền ngữ cảnh tương ứng. Khi trace bị đứt ở ranh giới async, hãy kiểm tra propagation, cấu hình client và sự khác biệt giữa **không ghi nhận span** với **span bị sampling bỏ qua** trước khi kết luận dịch vụ không chạy.

### 3.5. Logs có cấu trúc và mối liên kết với trace

Log hữu ích khi lưu được **sự kiện nghiệp vụ**, **mức độ nghiêm trọng**, **mã lỗi**, **dịch vụ**, **môi trường**, **thời điểm** và các ID tương quan cần thiết. Ví dụ một log giả định:

~~~text
2026-11-22T10:15:23Z WARN [traceId=2b7a...,spanId=8c1e...]
event=inventory_reservation_failed reason=upstream_timeout
dependency=inventory-service duration_ms=2400
~~~

Khi điều tra, kỹ sư có thể lấy trace ID từ log để mở trace, hoặc từ trace tìm ngược đến log cùng ngữ cảnh. Thực tế, backend log/trace cần có cấu hình field mapping và truy vấn tương quan thì thao tác chuyển qua lại mới thuận tiện.

Không log token, thông tin thanh toán, mật khẩu hoặc toàn bộ request body theo mặc định. Nếu cần định danh giao dịch để điều tra, hãy dùng một trường được phê duyệt về bảo mật và quy định lưu trữ; đừng đưa định danh đó thành metric tag. Tránh log cùng một exception ở mọi lớp rồi lại log lần cuối tại controller vì dễ gây nhiễu và tăng chi phí.

## 4. Kiểm thử: observability cũng cần tiêu chí nghiệm thu

Kiểm thử chức năng trả về HTTP 201 chỉ chứng minh một phần hành vi. Đối với hệ thống có observability, bộ kiểm thử và bước nghiệm thu còn phải chứng minh dữ liệu đủ để giải thích kết quả khi hệ thống vận hành.

| Giai đoạn | Kiểm tra observability | Câu hỏi đạt/chưa đạt |
| --- | --- | --- |
| **Local development** | Gửi request thành công, request 4xx và giả lập lỗi phụ thuộc | Metrics có tăng đúng không? Logs có trace ID khi context hiện diện không? |
| **Integration/CI** | Gọi qua hai service và một tác vụ bất đồng bộ | Trace có nối các span đúng không? Một phép đo quan trọng có tồn tại và dùng tag ổn định không? |
| **Performance test** | Tải đều, burst, timeout, retry | Percentile, histogram, saturation có phản ánh tải không? Instrumentation tạo overhead chấp nhận được không? |
| **Staging** | Pipeline telemetry tương tự production | Exporter, collector và backend có nhận được dữ liệu không? Dashboard và alert có hoạt động như dự định không? |
| **Pre-release** | So sánh với baseline của bản hiện tại | Có thể đo ngay lỗi, độ trễ, tài nguyên và tác động tới SLO sau khi triển khai không? |

Ví dụ xác minh local khi chạy ứng dụng:

~~~bash
curl -i http://localhost:8080/actuator/health
curl -s http://localhost:8080/actuator/prometheus
~~~

Đầu ra Prometheus chỉ có dữ liệu HTTP sau khi đã phát sinh các request tương ứng; tên metric cụ thể phụ thuộc phiên bản và instrumentation. Việc endpoint trả dữ liệu không chứng minh rằng Prometheus đã scrape thành công hoặc trace exporter đang hoạt động, nên cần kiểm tra ở backend đích.

Một bài kiểm thử tích hợp có ý nghĩa nên chủ động tạo một request có **mã tương quan đã biết**, kiểm tra dấu vết ở service nhận và bảo đảm ít nhất một đường dẫn kết thúc trong log/trace. Nếu sampling được bật, dùng cấu hình kiểm thử có khả năng quan sát đầy đủ hoặc cơ chế xác minh thích hợp; đừng viết test giả định mọi request production đều được giữ trace.

### 4.1. Kiểm thử trường hợp xấu

Các tình huống cần thử bao gồm: phụ thuộc timeout, pool cạn kết nối, queue backlog, request bị retry, rollout phiên bản mới, lỗi collector/exporter và backend observability chậm hoặc gián đoạn. Ứng dụng không nên làm thất bại nghiệp vụ chỉ vì exporter tạm thời không nhận dữ liệu; đồng thời đội vận hành phải có tín hiệu riêng để phát hiện **mất telemetry**.

Với dữ liệu giả lập, kiểm tra số lượng giá trị khác nhau của tags. Một route như **/orders/{id}** phải được ghi nhận dưới dạng route template hoặc nhãn đã chuẩn hóa, tránh biến mỗi ID thành một time series.

## 5. Triển khai: dùng tín hiệu để quyết định giữ hay quay lại phiên bản

Observability cần xuất hiện trong checklist phát hành và chính sách rollout, không chỉ trong dashboard vận hành:

1. **Trước phát hành:** xác định baseline của request rate, error rate, p95/p99, mức sử dụng tài nguyên và các SLI nghiệp vụ quan trọng; chú thích thời điểm phát hành.
2. **Trong canary/rolling deployment:** so sánh bản mới với bản ổn định trên cùng loại traffic khi có thể; kiểm tra phiên bản, instance và nhãn môi trường.
3. **Khi xuất hiện suy giảm:** dùng trace để khoanh vùng bước chậm, logs để biết điều kiện lỗi, metrics để ước lượng phạm vi; áp dụng rollback hoặc giảm traffic theo tiêu chí đã thống nhất.
4. **Sau phát hành:** theo dõi thêm các tác động trễ như backlog, retry, tiêu thụ error budget; cập nhật runbook với những dấu hiệu mới.

So sánh phải tính đến lưu lượng và đặc tính request. Bản canary xử lý ít traffic hoặc traffic rất khác có thể có p95 biến động mạnh; một trace đơn lẻ không đủ để kết luận cả bản phát hành có lỗi.

Khi phát hành cũng phải triển khai và kiểm tra **cấu hình telemetry**: địa chỉ exporter, secret, quota, retention, nhãn service/version và quyền truy cập. Một bản release có thể hoạt động đúng nhưng quan sát kém vì mất exporter, sai service name hoặc timestamp không đồng bộ.

## 6. Production: từ cảnh báo đến điều tra nguyên nhân

### 6.1. Dashboard và alert theo hành động

Một dashboard vận hành thường cần những tín hiệu gần với trải nghiệm người dùng:

- **Traffic:** request rate hoặc số sự kiện được xử lý mỗi giây.
- **Errors:** tỷ lệ lỗi 5xx, timeout, từ chối nghiệp vụ bất thường, lỗi tiêu thụ sự kiện.
- **Duration:** phân bố thời gian và p95/p99 cho những hành trình quan trọng.
- **Saturation:** CPU, bộ nhớ, connection pool, thread pool, độ sâu hàng đợi và thời gian chờ.

Đây là cách thực dụng để dùng các nhóm tín hiệu **RED** (Rate, Errors, Duration) và nguồn lực/saturation. Không nên cảnh báo chỉ vì CPU tăng nếu không có hành động rõ ràng; nên ưu tiên cảnh báo dựa trên SLO, lỗi ảnh hưởng người dùng hoặc tình trạng có nguy cơ gây sự cố.

Ví dụ truy vấn PromQL tham khảo cho HTTP server metrics được xuất từ Micrometer qua Prometheus:

~~~promql
# Tỷ lệ HTTP 5xx trong 5 phút (thay bộ lọc nhãn theo hệ thống thực tế)
sum(rate(http_server_requests_seconds_count{status=~"5.."}[5m]))
/
clamp_min(sum(rate(http_server_requests_seconds_count[5m])), 1e-9)
~~~

Khi bật histogram cho HTTP server timer, có thể tính p95 từ bucket:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{uri="/orders",method="POST"}[5m])
  )
)
~~~

Đây là ví dụ cần điều chỉnh theo label thực có, tên metric, lượng traffic, cửa sổ quan sát và cách tổng hợp. Nếu đo SLO cho một route, hãy lọc **cả tử và mẫu** của tỷ lệ lỗi theo cùng phạm vi. Tính phân vị từ histogram phải bảo đảm các instance dùng bucket tương thích; với traffic thấp, phân vị ngắn hạn dễ nhiễu. Nếu không bật histogram, truy vấn **_bucket** tương ứng có thể không tồn tại.

Cảnh báo nên có ngưỡng, khoảng duy trì, mức nghiêm trọng, chủ sở hữu, liên kết dashboard/runbook và ngữ cảnh service/environment. Với SLO, có thể dùng cảnh báo theo **tốc độ tiêu thụ error budget** trên nhiều cửa sổ thay vì đặt một ngưỡng 5xx cố định cho mọi dịch vụ.

### 6.2. Tình huống điều tra xuyên ba tín hiệu

Giả sử sau một lần triển khai, request tạo đơn có p95 tăng từ 450 ms lên 2,8 giây và tỷ lệ 5xx tăng. Các con số sau chỉ nhằm minh họa cách phân tích.

~~~mermaid
sequenceDiagram
    participant Client
    participant Order as order-service
    participant Inventory as inventory-service
    participant DB as Database
    Client->>Order: POST /orders
    Order->>Inventory: reserve inventory (traceparent)
    Inventory-->>Order: timeout sau 2,4 s
    Note over Order: span inventory.reserve ghi lỗi
    Order-->>Client: 503 / timeout
    Note over Order,DB: Không đến bước lưu đơn
~~~

Quy trình điều tra:

1. **Metrics phát hiện diện rộng:** đối chiếu error rate, p95, request rate và thời điểm phát hành. Xác nhận đây là hiện tượng thực, không phải mất scraper hay thiếu số liệu.
2. **Traces chỉ ra đường đi:** chọn một trace chậm nếu trace đã được lấy mẫu và lưu; xem span của order-service chờ inventory-service khoảng 2,4 giây. So sánh với trace bình thường để xác định bước tăng thời gian.
3. **Logs cung cấp nguyên nhân gần:** lọc log theo trace ID và khoảng thời gian để tìm mã lỗi **upstream_timeout**, số lần retry, thông tin pool/connection và phiên bản triển khai.
4. **Metrics phụ thuộc xác nhận xu hướng:** kiểm tra tỷ lệ timeout của inventory-service, độ sâu hàng đợi và tình trạng tài nguyên; xem các service khác có cùng chịu ảnh hưởng không.
5. **Khắc phục và xác minh:** giảm tải, rollback, điều chỉnh timeout/circuit breaker hoặc sửa lỗi phụ thuộc theo nguyên nhân thực. Theo dõi lại SLI, trace và log sau thay đổi.
6. **Rút kinh nghiệm:** bổ sung bài kiểm thử timeout, dashboard hoặc cảnh báo còn thiếu; cập nhật runbook và giới hạn của phương án fallback.

Một trace chậm là **bằng chứng cho request đó**, không tự động đại diện cho toàn bộ traffic. Metrics cho biết quy mô và xu hướng; traces giúp tìm đoạn xử lý; logs giải thích điều kiện cụ thể. Sự kết hợp làm cho kết luận có cơ sở hơn.

### 6.3. Nếu trace bị thiếu thì sao?

Không thấy trace trong backend không đồng nghĩa request không tồn tại. Cần kiểm tra lần lượt:

- Request có tạo observation/span ở ranh giới đó hay không?
- Sampling ở SDK/ứng dụng và Collector có giữ request này hay không?
- **traceparent** có được truyền qua proxy, HTTP client, queue và thread pool không?
- Exporter, Collector và backend có bị lỗi, nghẽn hoặc áp dụng quota không?
- Tên service, môi trường, thời gian và phạm vi tìm kiếm có chính xác không?

**Head-based sampling** quyết định sớm, thường có chi phí thấp nhưng có thể bỏ sót request lỗi hiếm. **Tail-based sampling** có thể giữ trace dựa trên kết quả hoặc độ trễ sau khi thu thập các span, đổi lại yêu cầu kiến trúc Collector và tài nguyên phù hợp. Với tỷ lệ lấy mẫu thấp, cần dựa thêm vào metrics và logs để phát hiện sự cố. Cũng cần chú ý các thành phần dùng chính sách sampling khác nhau có thể tạo trace không đầy đủ.

## 7. Quản lý chất lượng telemetry như một phần của chất lượng phần mềm

Observability tạo ra giá trị khi tín hiệu **đúng, đủ, có thể liên kết và vận hành được**. Những vấn đề thường gặp:

| Dấu hiệu | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Số time series tăng mạnh | Gắn user ID, order ID, URL nguyên bản vào metric label | Chuẩn hóa route; dùng tập label hữu hạn; rà cardinality trước release |
| Có metric chậm nhưng không biết chậm ở đâu | Thiếu span tại ranh giới nghiệp vụ hoặc phụ thuộc | Thêm observation cho bước có ý nghĩa; kiểm tra instrumented clients |
| Trace bị tách giữa các service | Thiếu truyền trace context hoặc đổi thread không bảo toàn context | Kiểm tra W3C headers, client auto-configuration và executor/context propagation |
| Có trace ID trong logs nhưng không mở được trace | Trace bị sampling bỏ, exporter lỗi hoặc backend không nhận | Kiểm tra sampling, queue/exporter, Collector và thời gian lưu |
| Alert quá ồn | Dựa vào ngưỡng tĩnh và tín hiệu không gắn hành động | Thiết kế theo SLO, error budget, ngưỡng duy trì và runbook |
| Dashboard mất dữ liệu sau release | Đổi metric/label, sai service name hoặc exporter | Kiểm tra contract telemetry trong CI/staging và version hóa dashboard |
| Telemetry chứa dữ liệu nhạy cảm | Ghi request body, token hoặc nhãn định danh | Phân loại dữ liệu, lọc/redact, giới hạn quyền truy cập và retention |
| Chi phí quan sát tăng | Sampling, histogram hoặc log volume quá lớn | Điều chỉnh theo giá trị truy vấn; giảm log trùng lặp, cardinality và retention |

**Exporter và pipeline telemetry** cũng cần được giám sát: tỉ lệ xuất lỗi, số bản ghi bị loại, độ trễ ingest, bộ nhớ hàng đợi và mức dùng quota. Khi pipeline gián đoạn, ứng dụng có thể vẫn phục vụ request nhưng khả năng điều tra suy giảm. Nên giữ cấu hình có giới hạn bộ nhớ/hàng đợi và biết trước hành vi khi mất kết nối đến backend.

**Bảo mật và quyền riêng tư** phải đi cùng thiết kế: không đưa dữ liệu nhạy cảm vào tag/span/log; tách quyền truy cập dashboard, logs và traces; cấu hình TLS, secret, retention và chính sách xóa dữ liệu phù hợp. Trace ID là công cụ tương quan chứ không phải cơ chế xác thực hay giấy phép xem toàn bộ dữ liệu liên quan.

## 8. Bộ tiêu chí nghiệm thu observability cho một tính năng mới

Trước khi tuyên bố một API hoặc luồng xử lý đã sẵn sàng vận hành, đội phát triển có thể tự đối chiếu:

| Tiêu chí | Bằng chứng đạt |
| --- | --- |
| Đã mô tả hành trình quan trọng và SLI/SLO | Có định nghĩa rõ kết quả tốt/xấu, khoảng đo, phạm vi traffic |
| Metrics phản ánh thành công, lỗi và độ trễ | Có thể truy vấn các metric qua backend, so khớp số request kiểm thử |
| Có tracing qua ranh giới quan trọng | Xem được một trace nối HTTP, nghiệp vụ và dịch vụ phụ thuộc trong môi trường kiểm thử |
| Logs có tương quan và an toàn dữ liệu | Tra log theo trace ID; không ghi secret/PII không cần thiết |
| Tags và histogram có chi phí chấp nhận được | Đã rà số giá trị nhãn, lượng series và lưu lượng telemetry |
| Sampling được chủ động lựa chọn | Hiểu tỷ lệ lấy mẫu và giới hạn của việc tìm trace khi có lỗi |
| Exporter và backend được xác minh | Tín hiệu xuất hiện tại nơi người vận hành thực sự tìm kiếm |
| Có dashboard, alert và runbook | Người trực biết lúc nào hành động, tìm tín hiệu ở đâu và bước kiểm tra đầu tiên |
| Có quy trình sử dụng tín hiệu khi phát hành | Baseline trước triển khai, theo dõi canary, tiêu chí rollback và kiểm tra sau triển khai |

Không cần instrument mọi dòng mã để đạt tiêu chí trên. Nên ưu tiên hành trình ảnh hưởng người dùng, ranh giới mạng/bất đồng bộ, các bước nghiệp vụ có thể thất bại và những thành phần dễ tạo độ trễ.

## 9. Bài thực hành: theo dõi vòng đời một luồng đặt hàng

**Bối cảnh:** bạn sở hữu một dịch vụ Spring Boot nhận **POST /orders**, gọi inventory-service và ghi cơ sở dữ liệu. Đội muốn tự tin phát hành một thay đổi đối với bước giữ hàng.

**Yêu cầu thực hành:**

1. Viết một SLI khả dụng và một SLI độ trễ cho API, nêu cách xác định request hợp lệ và request tốt.
2. Dùng Spring Boot Actuator và Micrometer để quan sát HTTP requests; thêm một observation quanh bước gọi giữ hàng.
3. Chọn ba nhãn metric có số giá trị hữu hạn. Giải thích vì sao không dùng order ID làm nhãn.
4. Xác minh một request tạo đơn có đường đi qua order-service và inventory-service. Thử một đường đi dùng **@Async** rồi kiểm tra trace context có được giữ hay không.
5. Giả lập inventory-service timeout. Tìm tín hiệu lỗi trong metrics, mở trace nếu có, tra log bằng trace ID và ghi lại nhận định.
6. Đề xuất ngưỡng theo dõi cho canary và tiêu chí rollback dựa trên SLI/SLO của hệ thống.

**Kết quả mong đợi:** một mô tả ngắn về SLI/SLO, cấu hình metrics/traces/logging, ảnh hoặc kết quả truy vấn dashboard, một trace minh họa và bản ghi điều tra timeout. Nếu trace không xuất hiện do sampling, hãy ghi rõ giới hạn đó và chứng minh lỗi bằng những tín hiệu còn lại.

## 10. Ghi nhớ khi đưa vào dự án thực

Observability là một phần của **vòng phản hồi kỹ thuật**: yêu cầu vận hành được xác định ở thiết kế; instrumentation được thêm trong mã nguồn; tín hiệu được xác minh khi kiểm thử; dữ liệu hỗ trợ quyết định lúc phát hành; và bài học từ production quay trở lại thành test, SLO và cách thiết kế hệ thống.

Trong Spring Boot, điểm khởi đầu thực dụng là **Actuator + Micrometer Observation**, sau đó kết nối **metrics**, **structured/correlated logs** và **distributed tracing** qua exporter/backend phù hợp. Chất lượng câu trả lời khi có sự cố phụ thuộc đồng thời vào việc chọn tín hiệu, giữ ngữ cảnh xuyên service/thread, kiểm soát tag/cardinality, hiểu sampling và bảo đảm pipeline telemetry hoạt động.
