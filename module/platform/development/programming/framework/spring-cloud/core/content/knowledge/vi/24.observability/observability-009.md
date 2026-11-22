# Theo dõi lỗi khởi động, lỗi refresh và thời gian lấy cấu hình

Trong ứng dụng Spring Cloud, ba giai đoạn thường gây gián đoạn vận hành là khởi động ứng dụng, tải cấu hình từ nguồn bên ngoài và refresh cấu hình khi ứng dụng đang chạy. Chúng có liên quan nhưng xảy ra ở các thời điểm khác nhau. Nếu chỉ nhìn một dòng log hoặc trạng thái health, rất dễ nhầm lỗi kết nối Config Server với lỗi tạo bean, hoặc nhầm refresh thành công với việc mọi bean đã sử dụng cấu hình mới.

Cách quan sát hiệu quả là kết hợp log theo vòng đời, startup steps, metrics, health indicator và dấu vết HTTP. Mỗi tín hiệu trả lời một câu hỏi riêng: ứng dụng dừng ở giai đoạn nào, remote configuration mất bao lâu để trả lời, property nào thay đổi, bean nào không thể khởi tạo lại và instance nào chưa nhận được refresh.

Bài học thuộc chương **Quan sát** của module **SPRING_CLOUD_CORE**. Nội dung hướng dẫn thu thập bằng chứng cho startup failure, refresh failure và Config Client latency; dùng Spring Boot Actuator, Micrometer và Spring Cloud Context; đồng thời xây dựng quy trình điều tra có thể áp dụng trong môi trường container hoặc nhiều replica.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Phân biệt thời gian ứng dụng bắt đầu, hoàn tất khởi động và sẵn sàng nhận request.
- Dùng **ApplicationStartup** và Actuator **startup** để xem các bước khởi động.
- Thu thập log ngay cả khi ApplicationContext chưa được tạo thành công.
- Xác định giai đoạn Config Client tải cấu hình và giải thích vì sao có nhiều request.
- Đo thời gian Config Server xử lý request bằng HTTP server metrics.
- Phân biệt **application.started.time**, **application.ready.time**, **http.server.requests** và **http.client.requests**.
- Theo dõi **EnvironmentChangeEvent**, **RefreshScope** và lỗi khởi tạo lại target bean.
- Dùng Config Client Health Indicator và RefreshScope Health Indicator đúng mục đích.
- Tạo metric riêng để đo thao tác refresh do ứng dụng điều khiển.
- Bảo vệ Actuator endpoint và tránh làm lộ giá trị cấu hình nhạy cảm.

## 2. Ba giai đoạn cần quan sát riêng

| Giai đoạn | Điều cần biết | Tín hiệu phù hợp |
| --- | --- | --- |
| Khởi động | Ứng dụng dừng ở bước nào? Bao lâu mới sẵn sàng? | ApplicationFailedEvent, startup steps, application.started.time, application.ready.time |
| Lấy cấu hình | Client gửi request nào, server phản hồi bao lâu, có retry hoặc discovery lookup không? | Config Client logs, Config Server http.server.requests, access log/proxy log, Config Client Health Indicator |
| Refresh | Property nào thay đổi? Bean nào được rebind hoặc tạo lại? Refresh có lỗi ở replica nào? | EnvironmentChangeEvent, /actuator/refresh, configprops, RefreshScope Health Indicator, log và metric refresh |

Không có một endpoint duy nhất trả lời cả ba câu hỏi. Ví dụ, **GET /actuator/health** có thể báo trạng thái Config Server nhưng không cho biết lần khởi động trước đã mất bao lâu để tải cấu hình. Tương tự, startup endpoint chỉ ghi lại quá trình khởi động; nó không phải lịch sử của các lần refresh sau đó.

Để dùng các management endpoint, ứng dụng cần **spring-boot-starter-actuator**. Nếu tải remote properties qua Spring Cloud Config, cần Config Client tương ứng, thường là **spring-cloud-starter-config**. Muốn export metrics sang Prometheus, bổ sung Micrometer Prometheus registry; chỉ expose endpoint **prometheus** khi registry đã được cấu hình.

## 3. Hiểu vòng đời khởi động của Spring Boot

Một ứng dụng Spring Boot đi qua các mốc sự kiện chính:

```text
ApplicationStartingEvent
        |
ApplicationEnvironmentPreparedEvent
        |
ApplicationContextInitializedEvent
        |
ApplicationPreparedEvent
        |
ApplicationStartedEvent
        |
ApplicationReadyEvent

Nếu khởi động thất bại:
ApplicationFailedEvent
```

Ý nghĩa thực tế:

- **ApplicationStartingEvent**: SpringApplication vừa bắt đầu; ApplicationContext chưa sẵn sàng.
- **ApplicationEnvironmentPreparedEvent**: Environment đã được chuẩn bị; các nguồn cấu hình và profile đang được thiết lập.
- **ApplicationContextInitializedEvent**: context đã được khởi tạo nhưng chưa refresh.
- **ApplicationPreparedEvent**: bean definitions đã được nạp; context chuẩn bị refresh.
- **ApplicationStartedEvent**: context đã refresh; các ApplicationRunner và CommandLineRunner sắp được gọi.
- **ApplicationReadyEvent**: ứng dụng đã sẵn sàng nhận request.
- **ApplicationFailedEvent**: quá trình khởi động gặp lỗi.

Config Data import của Spring Boot diễn ra trong giai đoạn chuẩn bị Environment, trước khi phần lớn bean của ứng dụng được tạo. Vì vậy, Config Server chậm có thể kéo dài startup trước khi Actuator HTTP endpoint tồn tại.

## 4. Ghi lại startup steps bằng BufferingApplicationStartup

Spring Boot cung cấp **BufferingApplicationStartup** để lưu các **StartupStep** trong bộ nhớ. Actuator **startup** có thể trả về timeline của các bước này, bao gồm thời điểm bắt đầu, kết thúc, duration và tag.

Cấu hình trong class main:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;

@SpringBootApplication
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication application =
            new SpringApplication(OrdersApplication.class);

        application.setApplicationStartup(
            new BufferingApplicationStartup(2048)
        );

        application.run(args);
    }
}
```

Số **2048** là dung lượng buffer ví dụ. Tăng dung lượng nếu ứng dụng có nhiều startup steps; tránh đặt quá lớn mà không có lý do vì dữ liệu được giữ trong bộ nhớ.

Mở endpoint trong môi trường chẩn đoán:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,startup
  endpoint:
    health:
      show-details: when-authorized
```

Sau khi ứng dụng đã khởi động, lấy snapshot:

```bash
curl -sS http://localhost:8080/actuator/startup
```

**GET /actuator/startup** trả về snapshot của buffer. **POST /actuator/startup** trả dữ liệu rồi drain buffer, tức là lấy và xóa các bước đã ghi. Dùng GET khi muốn đọc mà vẫn giữ dữ liệu; chỉ dùng POST khi chủ động muốn drain.

### 4.1. Đọc timeline để tìm nút thắt

Mỗi event có thể có:

- **startupStep.name**: tên bước khởi động.
- **startupStep.id** và **parentId**: quan hệ giữa bước cha và bước con.
- **startupStep.tags**: thông tin bổ sung như bean name.
- **startTime**, **endTime**, **duration**: thời gian thực hiện.

Hãy tìm bước có duration lớn bất thường, sau đó kiểm tra các bước con và tag. Ví dụ:

- Một bean khởi tạo lâu có thể đang gọi database hoặc API ngoài trong constructor.
- Một bước tạo bean có nhiều child steps có thể cho thấy dependency chain lớn.
- Environment preparation kéo dài có thể liên quan đến Config Data, profile activation, DNS hoặc truy cập Config Server.

Startup timeline không bảo đảm mỗi HTTP request của Config Client xuất hiện thành một step riêng. Dùng nó để định vị giai đoạn chậm, rồi đối chiếu Config Client logs và log/metrics ở Config Server để đo request mạng cụ thể.

## 5. Theo dõi thời gian started và ready

Spring Boot tự đăng ký hai application startup metrics:

| Metric | Ý nghĩa |
| --- | --- |
| **application.started.time** | Thời gian từ lúc bắt đầu đến mốc ứng dụng đã started |
| **application.ready.time** | Thời gian từ lúc bắt đầu đến khi ứng dụng sẵn sàng nhận request |

Đọc metric qua Actuator:

```bash
curl -sS http://localhost:8080/actuator/metrics/application.started.time
curl -sS http://localhost:8080/actuator/metrics/application.ready.time
```

Hai metric này chỉ có sau khi quá trình startup đi đến các mốc tương ứng. Chúng không thay thế log của process khởi động thất bại.

So sánh giữa các lần triển khai:

- **application.started.time** tăng mạnh: kiểm tra Config Data, bean initialization, classpath scanning và các dependency được khởi tạo sớm.
- **application.ready.time** tăng nhưng started time ít thay đổi: kiểm tra ApplicationRunner, CommandLineRunner, tác vụ sau refresh context hoặc các bước readiness.
- Cả hai tăng: kiểm tra tài nguyên CPU/memory, DNS, TLS, Config Server và các dependency ngoài.

Không so sánh số liệu giữa các phiên bản mà bỏ qua thay đổi JDK, số bean, cấu hình retry hoặc số lần gọi remote configuration.

## 6. Bắt lỗi khi ứng dụng chưa tạo được ApplicationContext

Nếu ứng dụng thất bại trước khi web server bắt đầu lắng nghe, **/actuator/health** và **/actuator/startup** có thể không truy cập được. Khi đó, cần quan sát từ process/container logs và listener được đăng ký trước khi gọi **SpringApplication.run()**.

Ví dụ ghi nhận **ApplicationFailedEvent** sớm:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;
import org.springframework.context.ApplicationListener;

@SpringBootApplication
public class OrdersApplicationLauncher {

    private static final Logger log =
        LoggerFactory.getLogger(OrdersApplicationLauncher.class);

    public static void main(String[] args) {
        SpringApplication application =
            new SpringApplication(OrdersApplicationLauncher.class);

        application.addListeners(
            (ApplicationListener<ApplicationFailedEvent>) event ->
                log.error(
                    "Application startup failed",
                    event.getException()
                )
        );

        application.setApplicationStartup(
            new BufferingApplicationStartup(2048)
        );

        application.run(args);
    }
}
```

Listener được đăng ký trước **run()** nên có thể nhận lỗi ở những giai đoạn mà một bean **@Component** hoặc **@EventListener** trong ApplicationContext chưa tồn tại.

Khi đọc lỗi, đi từ exception ngoài cùng đến root cause. Phân loại nguyên nhân trước khi sửa:

- **ConfigDataLocationNotFoundException** hoặc lỗi import: kiểm tra **spring.config.import**.
- **ConfigClientFailFastException** hoặc lỗi kết nối: kiểm tra Config Server, DNS, TLS, authentication và timeout.
- **BindException**/validation failure: kiểm tra property name, kiểu dữ liệu và giá trị bắt buộc.
- **BeanCreationException**: kiểm tra bean được tạo trong context và dependency chain.
- Port binding failure: kiểm tra cổng ứng dụng đã được process khác sử dụng chưa.

Spring Boot thường cung cấp Failure Analyzer để in phần mô tả và hướng xử lý cho các lỗi phổ biến. Hãy giữ cả phần phân tích lẫn stack trace đầy đủ trong log chẩn đoán.

## 7. Bật log đúng package khi điều tra startup

Không cần bật TRACE cho toàn bộ ứng dụng. Tạm thời tăng log level ở các package liên quan:

```yaml
logging:
  level:
    org.springframework.boot.context.config: TRACE
    org.springframework.cloud.config.client: DEBUG
    org.springframework.cloud.context.refresh: DEBUG
    org.springframework.cloud.context.scope.refresh: DEBUG
```

Các nhóm log giúp quan sát:

- **org.springframework.boot.context.config**: quá trình đọc Config Data, profile và import.
- **org.springframework.cloud.config.client**: request lấy cấu hình từ Config Server và kết quả xử lý.
- **org.springframework.cloud.context.refresh**: quá trình refresh Environment.
- **org.springframework.cloud.context.scope.refresh**: hoạt động của refresh scope và target bean.

Nếu dùng cấu hình logging để bắt cả các sự kiện rất sớm, hãy đặt log level ở nguồn cấu hình có hiệu lực trước giai đoạn cần quan sát, chẳng hạn biến môi trường hoặc tham số JVM. Một giá trị logging chỉ được lấy từ Config Server thì không thể giúp ghi log request đầu tiên dùng để tải chính giá trị đó.

Chỉ bật log chi tiết trong khoảng thời gian điều tra. Không ghi giá trị secret, password, token, private key hoặc toàn bộ Environment vào log.

## 8. Theo dõi quá trình Config Client lấy cấu hình

Với Config Data import, ví dụ:

```yaml
spring:
  application:
    name: orders
  config:
    import: "configserver:https://config.internal"
```

Spring Boot tải cấu hình theo hai giai đoạn:

1. Tải cấu hình với profile **default** để tìm các property có thể kích hoạt profile bổ sung.
2. Sau khi biết các profile đang hoạt động, tải cấu hình tương ứng với những profile đó.

Do đó, một lần khởi động có thể tạo nhiều request đến Config Server. Đây là hành vi bình thường, không tự động có nghĩa client đang retry hoặc bị lặp request.

Nếu dùng discovery-first lookup để tìm Config Server qua **DiscoveryClient**, startup còn có một network round trip để tìm registration của Config Server. Khi phân tích thời gian, hãy tách thời gian tìm server khỏi thời gian lấy property source.

### 8.1. Kiểm tra application, profile và label

Config Server cung cấp cấu hình theo đường dẫn:

```text
/{application}/{profile}/{label}
```

Client mặc định dùng:

- **application**: giá trị của **spring.application.name**.
- **profile**: các profile đang hoạt động.
- **label**: nhánh, tag hoặc revision cấu hình theo backend.

Khi request đến sai path, kiểm tra tên ứng dụng, profile, label và cấu hình **spring.cloud.config.name**, **spring.cloud.config.profile**, **spring.cloud.config.label** nếu đã override.

Ghi nhận metadata không nhạy cảm trong log vận hành:

- application name.
- profile đang dùng.
- config label hoặc revision.
- Config Server host/service ID.
- thời điểm bắt đầu request và thời điểm hoàn tất.
- số lần thử và kết quả cuối cùng.

Không log nội dung các property source chỉ để xác nhận client đã nhận response.

## 9. Đo thời gian xử lý ở Config Server

Spring Boot Actuator tự tạo metric **http.server.requests** cho request được xử lý bởi Spring MVC hoặc WebFlux. Trên Config Server, metric này giúp đo thời gian HTTP server xử lý các request lấy cấu hình.

Đọc danh sách metric:

```bash
curl -sS http://config-server:8888/actuator/metrics
```

Đọc metric request:

```bash
curl -sS http://config-server:8888/actuator/metrics/http.server.requests
```

Các tag thường dùng để phân tích gồm:

- **method**: HTTP method.
- **uri**: URI template nếu framework nhận diện được.
- **status**: HTTP status.
- **outcome**: nhóm kết quả.
- **exception**: loại exception nếu được ghi nhận.

Khi Config Server trả lời chậm, hãy đối chiếu latency theo URI, status và thời điểm request. Nếu server xử lý nhanh nhưng client vẫn chậm, kiểm tra DNS, TLS handshake, network route, proxy, service discovery và retry ở phía client.

### 9.1. Phân biệt metric HTTP client và thời gian Config Data import

Spring Boot có metric **http.client.requests** cho **RestTemplate**, **WebClient** và **RestClient** được tạo từ builder/customizer có instrumentation của Boot.

Tuy nhiên, không nên mặc định rằng request bootstrap nội bộ của Config Client sẽ xuất hiện như một **http.client.requests** metric trong ứng dụng. Config Data được tải trước khi ApplicationContext chính hoàn tất, và client nội bộ không nhất thiết dùng builder HTTP mà ứng dụng tạo sau đó.

Để đo lần lấy cấu hình một cách đáng tin cậy, kết hợp:

1. Config Client DEBUG/TRACE logs để xác định request, profile và retry.
2. **http.server.requests** ở Config Server để đo thời gian xử lý.
3. Access log của reverse proxy/load balancer nếu có.
4. Startup metrics để đo ảnh hưởng tổng thể lên thời gian khởi động.

Không cộng thời gian server xử lý với thời gian client ghi nhận nếu hai số liệu đo cùng một khoảng. Hãy xác định rõ điểm bắt đầu/kết thúc của từng phép đo.

## 10. Theo dõi retry và fail-fast khi Config Server không sẵn sàng

Nếu Config Server là nguồn cấu hình bắt buộc, bỏ prefix **optional:** trong Config Data import để ứng dụng thất bại khi không tải được cấu hình:

```yaml
spring:
  config:
    import: "configserver:https://config.internal"
  cloud:
    config:
      fail-fast: true
      retry:
        max-attempts: 6
        initial-interval: 1000
        multiplier: 1.1
```

Retry của Config Client cần **spring-retry** và **spring-boot-starter-aop** trên classpath. Các thuộc tính **spring.cloud.config.retry.*** điều chỉnh số lần thử và backoff. Với import được khai báo trong profile-specific file, cấu hình retry cần đặt dưới dạng URL parameter trên import theo hướng dẫn của phiên bản đang dùng.

### 10.1. Đặt ngưỡng kết nối và đọc response

Config Client có hai timeout riêng: thời gian chờ kết nối tới Config Server và thời gian chờ đọc response. Ví dụ dưới đây dùng milliseconds:

```yaml
spring:
  cloud:
    config:
      request-connect-timeout: 2000
      request-read-timeout: 5000
```

Timeout kết nối giúp phát hiện sớm DNS/route/server không nhận kết nối; read timeout giới hạn thời gian chờ server trả dữ liệu sau khi kết nối đã được thiết lập. Chọn giá trị theo latency bình thường và ngân sách startup của hệ thống. Retry backoff cộng thêm thời gian chờ của từng request, vì vậy tổng startup delay có thể lớn hơn một timeout đơn lẻ.

Khi quan sát retry, phân biệt:

- Một request cho **default** và một request cho active profile: có thể là hai giai đoạn Config Data bình thường.
- Nhiều request lặp lại cùng path sau lỗi kết nối: có thể là retry.
- Một lần discovery lookup trước request cấu hình: có thể là discovery-first lookup.
- Nhiều Config Server URL: client có thể thử các địa chỉ theo thứ tự để tìm server khả dụng.

Ghi lại số lần thử, khoảng backoff và lỗi gốc. Đừng tăng **max-attempts** để che một Config Server thường xuyên lỗi hoặc có latency vượt ngân sách startup.

## 11. Dùng Config Client Health Indicator đúng mục đích

Spring Cloud Config Client cung cấp Health Indicator thử tải cấu hình từ Config Server. Indicator này hữu ích để kiểm tra Config Server có thể được truy cập hay không.

Mặc định, kết quả health được cache trong 5 phút. Có thể điều chỉnh TTL bằng:

```yaml
health:
  config:
    time-to-live: 30000
```

Giá trị trên là 30 giây, tính bằng milliseconds. Có thể tắt indicator nếu không cần:

```properties
management.health.config.enabled=false
```

Một trạng thái **UP** có thể đến từ kết quả đã cache, không chứng minh rằng request cấu hình vừa thực hiện thành công ở thời điểm hiện tại. Health Indicator cũng không chứng minh remote property đã được áp dụng vào Environment của tất cả replica.

Khi cần xác nhận cấu hình đã được nạp, kiểm tra thêm profile, label/revision, property source và bean đã bind. Không chỉ dựa vào một màu xanh trên health dashboard.

## 12. Quan sát refresh Environment và EnvironmentChangeEvent

Khi Environment thay đổi, Spring Cloud phát **EnvironmentChangeEvent**. Các thành phần chuẩn có thể:

- Rebind bean **@ConfigurationProperties**.
- Cập nhật logger level từ các property **logging.level.***.
- Khi refresh flow được thực hiện qua ContextRefresher, các target thuộc RefreshScope có thể bị invalidate để tạo lại ở lần gọi tiếp theo.

Một listener có thể ghi lại danh sách key thay đổi:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.context.environment.EnvironmentChangeEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class RefreshAuditListener {

    private static final Logger log =
        LoggerFactory.getLogger(RefreshAuditListener.class);

    @EventListener
    public void onEnvironmentChange(EnvironmentChangeEvent event) {
        log.info("Environment changed; keys={}", event.getKeys());
    }
}
```

Chỉ ghi tên key, không ghi giá trị. Một số key có thể tiết lộ tên hệ thống nội bộ; hãy giới hạn quyền truy cập log theo chính sách vận hành.

Config Client không tự polling Config Server để tìm thay đổi theo mặc định. Trong hệ thống nhiều replica, có thể dùng Spring Cloud Bus để broadcast refresh event tới các instance thay vì để từng instance tự polling.

## 13. Theo dõi thao tác refresh qua Actuator

Spring Cloud Context cung cấp Refresh endpoint. Khi endpoint được expose, có thể gọi:

```bash
curl -i -X POST http://localhost:8080/actuator/refresh
```

Endpoint thực hiện refresh Environment và trả về các key được thay đổi theo cơ chế refresh. Để expose endpoint:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,refresh
```

Trong môi trường thực tế, phải bảo vệ endpoint bằng Spring Security, network policy hoặc management interface riêng. Không expose thao tác refresh cho client công khai.

Khi refresh thất bại, đối chiếu:

1. HTTP status và response của endpoint.
2. Config Client logs để xem có tải được remote source hay không.
3. Danh sách key thay đổi.
4. Property source có precedence cao hơn đang ghi đè giá trị mới hay không.
5. Bean nào được rebind hoặc refresh.
6. Health indicator của refresh scope sau thao tác.

### 13.1. Refresh target không giống tải lại cấu hình

**RefreshScope** quản lý target bean theo cơ chế proxy/cache. Khi target bị invalidate, lần gọi tiếp theo sẽ tạo target mới. Nhưng thao tác invalidate target không tự chứng minh Config Server vừa được gọi hoặc Environment đã nhận giá trị mới.

Hãy tách hai câu hỏi:

- Remote property source đã được tải/cập nhật chưa?
- Bean sử dụng property đó đã được rebind hoặc tạo lại thành công chưa?

Nếu chỉ kiểm tra câu hỏi thứ hai, bạn có thể thấy bean vẫn nhận giá trị cũ vì Environment chưa thay đổi. Nếu chỉ kiểm tra câu hỏi thứ nhất, một bean không thuộc refresh scope vẫn có thể tiếp tục giữ state cũ.

## 14. Theo dõi lỗi khởi tạo lại bean sau refresh

Spring Cloud cung cấp **RefreshScopeHealthIndicator**. Nếu một bean không thể re-initialize hoặc rebind sau context refresh, indicator có thể chuyển trạng thái **DOWN** và đưa exception liên quan vào health details.

Kiểm tra:

```bash
curl -sS http://localhost:8080/actuator/health
```

Khi được cấp quyền xem chi tiết, tìm component refresh scope và exception tương ứng. Phân biệt lỗi trong lúc nạp cấu hình với lỗi trong lúc tạo lại target bean.

Một số nguyên nhân thường gặp:

- Bean cần property mới nhưng property không tồn tại.
- Constructor hoặc factory method ném exception khi nhận giá trị mới.
- Kết nối database/client cũ chưa được đóng đúng vòng đời.
- Bean có dependency không refresh nhưng caller giả định dependency đã đổi.
- Bean không thực sự nằm trong **@RefreshScope**.
- Cấu hình mới hợp lệ về kiểu nhưng không hợp lệ về nghiệp vụ.

Lưu ý: **@ConfigurationProperties** constructor-bound, bao gồm Java record, không thể được refresh theo cách rebind thông thường. Nếu cần thay đổi cấu hình runtime, chọn mô hình bean và binding phù hợp với yêu cầu refresh.

## 15. Đo thời gian refresh do ứng dụng điều khiển

Nếu ứng dụng có một service riêng chịu trách nhiệm gọi **ContextRefresher**, có thể đo duration bằng Micrometer **Timer**. Ví dụ:

```java
import java.util.Set;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import org.springframework.cloud.context.refresh.ContextRefresher;
import org.springframework.stereotype.Component;

@Component
public class TimedConfigRefresh {

    private final ContextRefresher contextRefresher;
    private final MeterRegistry meterRegistry;

    public TimedConfigRefresh(
            ContextRefresher contextRefresher,
            MeterRegistry meterRegistry) {
        this.contextRefresher = contextRefresher;
        this.meterRegistry = meterRegistry;
    }

    public Set<String> refresh() {
        Timer.Sample sample = Timer.start(meterRegistry);
        String outcome = "success";

        try {
            return contextRefresher.refresh();
        }
        catch (RuntimeException exception) {
            outcome = "failure";
            throw exception;
        }
        finally {
            sample.stop(
                Timer.builder("app.config.refresh")
                    .tag("outcome", outcome)
                    .register(meterRegistry)
            );
        }
    }
}
```

Metric **app.config.refresh** cho biết duration và outcome của các lần refresh đi qua service này. Có thể truy vấn qua **/actuator/metrics/app.config.refresh**.

Nếu ứng dụng gọi trực tiếp Actuator Refresh endpoint, wrapper trên không tự động đo request đó. Muốn đo cả endpoint, hãy tích hợp timer ở đúng đường xử lý refresh hoặc dùng observation phù hợp với phiên bản Spring Cloud đang triển khai. Không tạo một endpoint refresh thứ hai mà không có chính sách phân quyền và audit thống nhất.

Không thêm **changedKeys**, exception message, user ID hoặc giá trị property làm metric tag. Những dữ liệu thay đổi liên tục có thể tạo cardinality rất lớn và làm hệ thống metrics quá tải.

## 16. Thiết kế log để nối các sự kiện

Một dòng log hữu ích cần đủ dữ liệu để nối sự kiện giữa các giai đoạn mà không làm lộ cấu hình.

Các trường nên cân nhắc:

| Trường | Mục đích |
| --- | --- |
| service | Tên service |
| environment | Môi trường triển khai |
| instance | Pod/instance ID |
| profile | Profile đang hoạt động |
| configLabel hoặc configVersion | Revision cấu hình |
| operation | startup, config-fetch, refresh |
| outcome | success hoặc failure |
| durationMs | Thời gian thao tác |
| changedKeys | Danh sách key thay đổi, không kèm value |
| traceId/spanId | Liên kết log với trace khi tracing được cấu hình |

Ví dụ log ứng dụng:

```text
event=config-refresh
service=orders
instance=orders-7f9d
configVersion=release-2026-11-18
outcome=success
durationMs=184
changedKeys=[catalog.timeout,feature.checkout.enabled]
```

Với startup failure, ghi root cause, service, instance, profile và config label nếu đã biết. Không ghi access token, password, private key, nội dung secret hoặc toàn bộ response Config Server.

Khi dùng Micrometer Tracing, trace ID và span ID có thể được đưa vào logging context để nối log với trace. Tuy nhiên, không phải mọi hoạt động bootstrap đều có trace request như HTTP traffic thông thường; cần giữ log thời gian và correlation metadata riêng cho giai đoạn startup.

## 17. Bảo vệ Actuator endpoint trong quá trình chẩn đoán

Một cấu hình tối thiểu cho metrics và startup có thể là:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,startup
  endpoint:
    health:
      show-details: when-authorized
```

Nếu dùng Prometheus, thêm registry dependency tương ứng và expose **prometheus** khi đã cấu hình scraper.

Các endpoint như **env**, **configprops**, **loggers** và **refresh** cần được mở có kiểm soát:

- **env** và **configprops** có thể tiết lộ cấu trúc cấu hình nội bộ.
- **loggers** cho phép thay đổi log level runtime.
- **refresh** thay đổi Environment và có thể làm nhiều bean khởi tạo lại.
- **startup** có thể tiết lộ tên bean, class và cấu trúc nội bộ.

Đặt management port/interface riêng nếu phù hợp, yêu cầu xác thực và giới hạn network access. Chỉ mở endpoint cần thiết trong thời gian điều tra rồi thu hồi cấu hình chẩn đoán.

## 18. Quy trình điều tra theo triệu chứng

| Triệu chứng | Bằng chứng đầu tiên | Bước tiếp theo |
| --- | --- | --- |
| Process thoát trước khi web server chạy | Container/process logs, ApplicationFailedEvent | Xem root cause, Config Data logs, bind/bean errors |
| Startup lâu nhưng cuối cùng thành công | application.started.time, application.ready.time, startup timeline | Tìm bước Environment preparation hoặc bean initialization kéo dài |
| Config Client timeout | Client logs, Config Server http.server.requests, proxy access log | Kiểm tra DNS, TLS, auth, route, server load và retry |
| Config Client gửi nhiều request | Request path và profile trong log | Xác định lượt default, active profile, discovery lookup hay retry |
| Health Config Server vẫn UP nhưng config cũ | Health indicator cache, property source và config version | Kiểm tra TTL, refresh event và Environment thực tế |
| POST refresh thành công nhưng bean vẫn cũ | Changed keys, configprops, bean scope | Kiểm tra property precedence và target có được refresh không |
| Refresh endpoint lỗi | HTTP response, refresh logs, RefreshScope Health Indicator | Tìm bean rebind/reinitialize exception |
| Một replica nhận config mới, replica khác không | Instance ID, config version và refresh event theo instance | Kiểm tra broadcast qua Spring Cloud Bus và health của từng replica |
| Sau refresh, request đầu tiên chậm | Lazy target initialization của RefreshScope | Quan sát thời gian tạo lại bean và dependency khởi tạo bên trong |
| Metric HTTP client không có request Config Server | Instrumentation của client bootstrap | Dùng server-side metric, client logs và proxy logs |

## 19. Bài tập vận dụng

Một hệ thống gồm **orders-service** và Config Server. Sau khi triển khai bản mới:

- orders-service mất 18 giây mới sẵn sàng.
- Config Server ghi nhận nhiều request cho cùng service.
- Lệnh **POST /actuator/refresh** trả về danh sách key thay đổi.
- Một replica chuyển health refresh scope sang **DOWN**.
- Replica còn lại vẫn trả response với timeout cũ.

Hãy điều tra theo thứ tự:

1. Lấy **application.started.time** và **application.ready.time** của các lần triển khai trước/sau.
2. Bật **BufferingApplicationStartup** và lấy **/actuator/startup**.
3. Đối chiếu Environment preparation với Config Client logs.
4. Phân loại các request Config Server theo **default**, active profile, discovery lookup và retry.
5. Đọc **http.server.requests** trên Config Server để đo thời gian xử lý.
6. Kiểm tra Config Client Health Indicator và TTL để xác định trạng thái health có cũ không.
7. Gọi refresh và ghi lại changed keys, config label và thời gian xử lý.
8. Kiểm tra **configprops** và RefreshScope Health Indicator của từng replica.
9. Tìm exception khiến target bean của replica đầu tiên không khởi tạo lại.
10. Xác minh replica thứ hai đã nhận event và target bean thực sự sử dụng timeout mới.
11. Đề xuất cách broadcast refresh event và bổ sung log/metric theo instance.

**Tiêu chí hoàn thành:** xác định được phần thời gian nằm ở startup, Config Server request hay bean initialization; giải thích được số request Config Client; tìm ra nguyên nhân refresh thất bại ở một replica; có bằng chứng cho thấy mọi replica đã áp dụng config version mong đợi.

## 20. Ghi nhớ

- **application.started.time** và **application.ready.time** đo hai mốc khác nhau của startup.
- Actuator **startup** cần **BufferingApplicationStartup**; GET lấy snapshot, POST drain buffer.
- Nếu ApplicationContext không khởi động, Actuator endpoint có thể chưa tồn tại; dùng process logs và listener **ApplicationFailedEvent**.
- Config Data import có thể tải cấu hình cho **default** rồi các active profile, nên nhiều request không nhất thiết là retry.
- Discovery-first lookup thêm một network round trip để tìm Config Server.
- **http.server.requests** trên Config Server giúp đo thời gian xử lý; không giả định bootstrap Config Client luôn xuất hiện trong **http.client.requests**.
- Config Client Health Indicator cache kết quả mặc định 5 phút; trạng thái UP không chứng minh lần refresh mới nhất thành công.
- **EnvironmentChangeEvent** rebind **@ConfigurationProperties** và cập nhật logger levels; Config Client mặc định không polling.
- **RefreshScopeHealthIndicator** giúp phát hiện lỗi rebind/reinitialize sau context refresh.
- Đo refresh duration bằng timer riêng nếu ứng dụng cần theo dõi latency của thao tác refresh.
- Log key và metadata, không log giá trị secret; giới hạn cardinality của metric tags.
- Bảo vệ Actuator endpoints, đặc biệt **env**, **configprops**, **loggers** và **refresh**.

## 21. Tài liệu tham khảo

- [Spring Boot — Application Startup](https://docs.spring.io/spring-boot/reference/features/spring-application.html): **ApplicationStartup**, **BufferingApplicationStartup** và startup event.
- [Spring Boot — Actuator Startup Endpoint](https://docs.spring.io/spring-boot/api/rest/actuator/startup.html): đọc snapshot và drain startup steps.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): **application.started.time**, **application.ready.time**, **http.server.requests**, **http.client.requests**.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): exposure, endpoint access và bảo vệ management endpoints.
- [Spring Cloud Config Client](https://docs.spring.io/spring-cloud-config/reference/client.html): Config Data import, default/active profile requests, discovery-first lookup, retry và Config Client Health Indicator.
- [Spring Cloud Commons — Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): **EnvironmentChangeEvent**, **@RefreshScope**, refresh endpoint và RefreshScope Health Indicator.
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): đo duration, count và phân phối thời gian thao tác.

