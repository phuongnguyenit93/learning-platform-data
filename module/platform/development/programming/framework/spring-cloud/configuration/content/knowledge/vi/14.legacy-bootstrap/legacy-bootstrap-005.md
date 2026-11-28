# Tìm Config Server qua Service Discovery và chi phí khởi động

Trong mô hình Config First Bootstrap cũ, Config Client cần biết địa chỉ Config Server trước khi tạo application context chính. Nếu địa chỉ máy chủ thay đổi theo môi trường hoặc có nhiều instance, việc ghi cứng `spring.cloud.config.uri` trong từng ứng dụng làm tăng công việc vận hành. Discovery First Bootstrap giải quyết vấn đề này bằng cách dùng `DiscoveryClient` để tìm Config Server qua service registry như Eureka hoặc Consul.

Đổi lại, client phải liên hệ service registry trước khi gọi Config Server. Spring Cloud mô tả đây là một network round trip bổ sung trong quá trình khởi động. Vì vậy, discovery-first giúp tách client khỏi địa chỉ host/port cố định, nhưng cũng đưa registry vào đường khởi động và làm tăng độ trễ ban đầu.

## 1. Config First và Discovery First khác nhau thế nào?

Hai cách đều lấy cấu hình từ Config Server, nhưng khác nhau ở cách xác định địa chỉ máy chủ:

| Cách khởi động | Cách tìm Config Server | Ưu điểm | Chi phí/điều kiện |
|---|---|---|---|
| Config First | Client dùng URI cố định trong `bootstrap.yml`, biến môi trường hoặc system property | Đường đi đơn giản, không cần tra cứu registry | Phải quản lý địa chỉ khi host/port thay đổi; cần cơ chế riêng nếu có nhiều instance |
| Discovery First | Client dùng `DiscoveryClient` tra cứu service ID trong Eureka, Consul hoặc registry tương thích | Config Server có thể đổi địa chỉ mà client không phải cập nhật URI | Thêm một lần tra cứu mạng khi khởi động; registry phải sẵn sàng và có thể truy cập |

Với Config First, client thường gọi trực tiếp `http://config-server:8888`. Với Discovery First, client hỏi registry: “Có instance nào đăng ký dưới service ID `configserver`?” Sau khi nhận thông tin instance, client mới gọi endpoint cấu hình của instance đó.

Discovery First không thay thế Config Server. Service registry chỉ giúp tìm địa chỉ và metadata của máy chủ. Cấu hình ứng dụng vẫn được đọc từ Environment Repository mà Config Server đang sử dụng, chẳng hạn Git.

## 2. Discovery First trong legacy bootstrap

Legacy bootstrap là cơ chế khởi tạo cấu hình từ xa trước application context chính. Ở các phiên bản Spring Cloud hiện đại, bootstrap không còn tự bật chỉ vì có Config Client trên classpath. Có thể kích hoạt bằng cách thêm `spring-cloud-starter-bootstrap` hoặc đặt `spring.cloud.bootstrap.enabled=true` bằng biến môi trường hay Java system property.

Ví dụ dependency Maven ở phía Config Client, không ghi phiên bản riêng khi dự án đã dùng Spring Cloud BOM:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-config</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-bootstrap</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
    </dependency>
</dependencies>
```

Nếu dùng Consul, thay Eureka Discovery Client bằng starter discovery tương ứng. Không thêm đồng thời nhiều implementation nếu không có chủ đích kết hợp chúng.

Khi bootstrap đã được bật, `bootstrap.yml` được nạp sớm để cung cấp các thông tin cần thiết cho việc tìm Config Server. Đây là nơi thích hợp để khai báo service registry mà client cần liên hệ trước khi nhận cấu hình từ xa.

## 3. Cấu hình Config Client tìm Config Server qua Eureka

Ví dụ `bootstrap.yml` ở phía `order-service`:

```yaml
spring:
  application:
    name: order-service
  cloud:
    config:
      discovery:
        enabled: true
        service-id: configserver
      fail-fast: true
      request-connect-timeout: 2000
      request-read-timeout: 5000

eureka:
  client:
    serviceUrl:
      defaultZone: http://eureka-server:8761/eureka/
```

Ý nghĩa các thuộc tính:

- `spring.application.name` là tên dịch vụ client. Config Server thường dùng tên này để chọn file cấu hình như `order-service.yml` và `order-service-prod.yml`.
- `spring.cloud.config.discovery.enabled: true` bật tra cứu Config Server qua `DiscoveryClient`; mặc định thuộc tính này là `false`.
- `spring.cloud.config.discovery.service-id` là tên dịch vụ mà client yêu cầu registry tìm. Giá trị mặc định là `configserver`.
- `eureka.client.serviceUrl.defaultZone` cung cấp địa chỉ registry. Địa chỉ này phải có sẵn trong bootstrap hoặc nguồn cục bộ trước khi client tải cấu hình từ Config Server. Với Eureka, `defaultZone` là khóa map phân biệt chữ hoa/chữ thường; giữ đúng camelCase này.
- `fail-fast: true` yêu cầu client dừng khởi động nếu không lấy được cấu hình từ xa.
- `request-connect-timeout` và `request-read-timeout` đặt giới hạn cho kết nối/đọc phản hồi Config Server; chúng không nên được hiểu là timeout của mọi thao tác trong Eureka.

Nếu Config Server đăng ký bằng tên khác, ví dụ `central-config`, client phải dùng `service-id: central-config`. Service ID cần khớp với tên đăng ký thực tế của server, thường được xác định bởi `spring.application.name` trên Config Server.

Không đặt duy nhất địa chỉ Eureka trong cấu hình từ xa của Config Server. Client cần địa chỉ registry để tìm Config Server; nếu chính địa chỉ registry lại phải lấy từ Config Server thì sẽ tạo vòng phụ thuộc không thể khởi động.

## 4. Đăng ký Config Server vào service registry

Config Server cũng cần có Discovery Client và đăng ký với cùng registry. Ví dụ dependency Eureka ở phía Config Server:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
</dependency>
```

Ví dụ cấu hình ứng dụng Config Server:

```yaml
server:
  port: 8888

spring:
  application:
    name: configserver
  cloud:
    config:
      server:
        git:
          uri: https://git.example.com/platform/config-repository.git

eureka:
  client:
    serviceUrl:
      defaultZone: http://eureka-server:8761/eureka/
```

Ở đây `spring.application.name: configserver` làm tên đăng ký mặc định trùng với `service-id` phía client. Nếu Config Server chạy dưới context path, hoặc cần cung cấp thông tin kết nối bổ sung, có thể khai báo metadata trong service registration.

Ví dụ Config Server phục vụ API dưới context path `/config`:

```yaml
server:
  servlet:
    context-path: /config

eureka:
  instance:
    metadataMap:
      configPath: /config
```

Config Client có thể đọc `configPath` từ metadata để gọi đúng đường dẫn. Nếu Config Server dùng HTTP Basic Authentication, Spring Cloud Config cũng hỗ trợ metadata `user` và `password` để cung cấp thông tin xác thực cho client. Chỉ sử dụng cách này khi registry được bảo vệ chặt chẽ và metadata không bị lộ cho các client không liên quan; ưu tiên cơ chế secret và xác thực phù hợp với nền tảng.

Metadata của registry có thể được nhiều service consumer đọc. Không đưa password hoặc token dạng rõ vào metadata nếu quyền truy cập registry không được giới hạn. Với cơ chế xác thực phức tạp hơn, có thể cần tùy chỉnh HTTP client của Config Client để cấp header hoặc bearer token.

### Độ trễ đăng ký và trạng thái health trong Eureka

Một Config Server vừa khởi động có thể chưa xuất hiện ngay trong kết quả tra cứu của mọi Eureka client. Eureka dùng heartbeat và registry cache để đồng bộ registration; tài liệu Spring Cloud Netflix lưu ý quá trình này có thể mất vài chu kỳ heartbeat (mặc định heartbeat là 30 giây). Vì vậy, nếu client khởi động ngay sau server, lần tra cứu đầu tiên có thể chưa thấy instance dù Config Server đã mở cổng.

Eureka mặc định xác định instance còn sống dựa trên heartbeat; trạng thái Actuator không tự động được truyền sang registry. Nếu cần Eureka phản ánh health indicator của ứng dụng, có thể bật `eureka.client.healthcheck.enabled: true` trong `application.yml` của Config Server. Không đặt thuộc tính này trong `bootstrap.yml`, vì cấu hình health check quá sớm có thể khiến instance được đăng ký với trạng thái `UNKNOWN`.

Khi điều tra lỗi “No instances available”, hãy kiểm tra service ID, registration, heartbeat, registry fetch/cache và health status. Với Consul hoặc registry khác, thời gian cập nhật catalog và health check có cơ chế riêng; không áp dụng máy móc chu kỳ của Eureka.

## 5. Luồng khởi động Discovery First

Thứ tự khái quát khi một client dùng legacy bootstrap và Discovery First:

```text
JVM khởi chạy
      |
      v
Kích hoạt legacy bootstrap
      |
      v
Đọc bootstrap.yml / biến môi trường / system property
      |
      v
Khởi tạo DiscoveryClient với địa chỉ registry
      |
      v
Tra cứu service ID: configserver
      |
      v
Nhận host, port và metadata của Config Server
      |
      v
Gọi Config Server lấy Environment từ application/profile/label
      |
      v
Thêm remote property sources vào Environment
      |
      v
Khởi tạo application context chính
      |
      v
Ứng dụng sẵn sàng phục vụ
```

Các bước chi tiết và cách khởi tạo Discovery Client có thể khác nhau theo implementation và phiên bản, nhưng điểm cốt lõi không đổi: client phải biết cách truy cập registry trước khi registry có thể chỉ cho nó địa chỉ Config Server.

## 6. Chi phí khởi động phát sinh ở đâu?

Với Config First, client đã có URI nên có thể bắt đầu kết nối Config Server trực tiếp. Với Discovery First, client cần thêm bước tra cứu service registration. Tài liệu Spring Cloud mô tả chi phí này là một network round trip bổ sung khi khởi động.

Thời gian khởi động có thể hình dung bằng mô hình:

\[
T_{startup} \approx T_{bootstrap} + T_{registry} + T_{config-fetch} + T_{backend} + T_{retry} + T_{context}
\]

Trong đó:

- `T_bootstrap`: đọc và khởi tạo bootstrap context cùng các client cần thiết.
- `T_registry`: kết nối và tra cứu service registration.
- `T_config-fetch`: gọi HTTP đến Config Server và nhận Environment.
- `T_backend`: thời gian Config Server đọc backend, ví dụ Git fetch/clone nếu cache chưa sẵn sàng.
- `T_retry`: thời gian chờ cộng dồn nếu có lỗi tạm thời và retry được bật.
- `T_context`: phần còn lại để tạo bean, chạy kiểm tra khởi động và sẵn sàng phục vụ.

Đây là mô hình phân tích, không phải công thức đo thời gian chính xác. Một số thao tác có thể chồng lấp hoặc được cache. Phần tăng thêm do discovery phụ thuộc độ trễ mạng, thời gian phản hồi registry, số lần thử và trạng thái kết nối.

### Các nguồn gây chậm thường gặp

1. **Registry phản hồi chậm:** DNS, TLS, mạng nội bộ hoặc registry đang quá tải làm tra cứu instance mất thời gian.
2. **Không tìm thấy service ID:** client chờ registry cập nhật registration hoặc retry đến khi hết thời gian.
3. **Config Server chưa sẵn sàng:** registry đã trả instance nhưng server chưa phục vụ HTTP hoặc chưa đọc xong Git repository.
4. **Git backend lạnh:** Config Server cần clone/fetch repository hoặc truy cập Git host chậm.
5. **Nhiều client khởi động đồng thời:** sau khi triển khai, nhiều instance cùng tra cứu registry và gọi Config Server, tạo tải tăng đột biến.
6. **Retry/backoff quá dài:** retry cải thiện khả năng chịu lỗi tạm thời nhưng kéo dài thời gian khởi động khi dependency vẫn lỗi.

Discovery First vì thế có thể làm thời gian khởi động dài hơn Config First, nhất là khi registry và Config Server nằm ở các vùng mạng khác nhau. Lợi ích là client không phải biết địa chỉ cố định của từng instance Config Server.

## 7. Fail-fast, timeout và retry

Ứng dụng cần quyết định có được phép khởi động khi không lấy được cấu hình hay không. Nếu endpoint database, khóa bảo mật hoặc giới hạn nghiệp vụ bắt buộc phải lấy từ Config Server, tiếp tục khởi động với cấu hình thiếu có thể tạo lỗi khó phát hiện. Khi đó, `spring.cloud.config.fail-fast: true` giúp dừng startup nếu không lấy được cấu hình.

Ví dụ giới hạn thời gian kết nối và đọc phản hồi:

```yaml
spring:
  cloud:
    config:
      fail-fast: true
      request-connect-timeout: 2000
      request-read-timeout: 5000
```

Các giá trị trong ví dụ tính bằng mili giây và chỉ là điểm bắt đầu để minh họa. Cần đo độ trễ thực tế và đặt timeout theo SLO của hệ thống. Timeout Config Server không tự động cấu hình timeout cho Eureka hoặc Consul; registry có cấu hình kết nối và retry riêng.

Nếu Config Server có thể tạm thời chưa sẵn sàng trong lúc triển khai, retry có giới hạn giúp client thử lại trước khi thất bại. Cách cấu hình retry phụ thuộc phiên bản Spring Cloud Config:

**Với Spring Cloud Config 5.1 trở lên**, retry dùng hỗ trợ của Spring Framework, không cần thêm Spring Retry dependency, và có thể bật như sau:

```yaml
spring:
  cloud:
    config:
      fail-fast: true
      retry:
        enabled: true
        max-attempts: 6
        initial-interval: 1000
        max-interval: 5000
        multiplier: 1.5
```

`max-attempts` tính cả lần gọi đầu tiên. Với sáu lần thử, client gọi ban đầu một lần và có tối đa năm lần retry. Backoff tăng dần giúp giảm áp lực lên server khi nhiều client cùng gặp lỗi.

**Với các phiên bản trước 5.1**, retry truyền thống cần Spring Retry trên classpath; tài liệu của các phiên bản này yêu cầu thêm `spring-retry` và `spring-boot-starter-aop`, cùng `fail-fast: true`. Hãy dùng hướng dẫn đúng với release train đang quản lý trong BOM; không chép cấu hình dependency của phiên bản cũ sang phiên bản mới mà không kiểm tra.

Retry của Config Client tập trung vào quá trình lấy cấu hình. Tra cứu registry có timeout và cơ chế thử lại riêng theo Discovery Client. Cần đo cả hai đoạn để biết startup chậm do service registry hay do HTTP request tới Config Server.

## 8. Service ID, nhiều instance và metadata

Service ID là tên logic, không phải hostname hoặc IP. Ví dụ client yêu cầu `configserver`, registry trả về một hoặc nhiều instance đã đăng ký dưới tên đó. Khi chuyển Config Server sang máy khác hoặc thay đổi port, client vẫn có thể tìm thấy nó nếu registration được cập nhật đúng.

Nếu Config Server có nhiều instance, registry có thể trả về nhiều service instance. Việc chọn instance, cân bằng tải, lọc instance chưa healthy và failover phụ thuộc Discovery Client, tích hợp load balancer và phiên bản thư viện. Không nên giả định rằng chỉ cần đăng ký nhiều instance là mọi client sẽ tự động retry sang instance khác trong mọi lỗi HTTP.

Metadata giúp client hoàn thiện địa chỉ kết nối. Các khóa thường gặp gồm:

| Metadata | Mục đích |
|---|---|
| `configPath` | Context path của Config Server nếu API không nằm ở root |
| `user` | Username HTTP Basic khi server yêu cầu |
| `password` | Password HTTP Basic khi server yêu cầu |

Metadata key và cách đọc phụ thuộc Discovery Client. Với Eureka, các giá trị này thường được đặt trong `eureka.instance.metadataMap`. Với Consul, cách khai báo metadata và cách Config Client đọc có thể khác. Luôn xác minh metadata mà client nhận được trong registry thay vì giả định mọi implementation giống nhau.

## 9. Bảo mật kết nối Discovery First

Discovery First thêm một nguồn thông tin quan trọng vào luồng cấu hình: service registry. Cần bảo vệ cả kết nối registry lẫn kết nối Config Server.

- Cấp quyền đọc service registration theo danh tính ứng dụng nếu registry hỗ trợ ACL.
- Bảo vệ endpoint registry bằng TLS và xác thực; không để mọi workload đọc toàn bộ metadata nếu không cần thiết.
- Không lưu secret dạng rõ trong `bootstrap.yml`, source control hoặc metadata công khai.
- Nếu phải dùng metadata `user`/`password` theo cơ chế HTTP Basic của Config Client, hạn chế quyền đọc registry và dùng biến môi trường/secret store để cấp giá trị.
- Bảo vệ Config Server bằng TLS, xác thực và phân quyền cho từng client.
- Không coi việc service ID khó đoán là một cơ chế bảo mật.
- Theo dõi thay đổi registration để phát hiện instance lạ hoặc địa chỉ không mong đợi.

Vì bootstrap xảy ra trước khi lấy cấu hình từ xa, thông tin cần thiết để kết nối registry và xác thực ban đầu phải có sẵn từ nguồn cục bộ được bảo vệ. Không thể dùng một secret chỉ tồn tại trong Config Server để xác thực lần đầu tới chính Config Server đó.

## 10. Đo và tối ưu chi phí khởi động

Không nên chỉ đo tổng thời gian từ lúc chạy JVM đến lúc ứng dụng báo ready. Hãy tách các mốc để biết phần nào đang chiếm thời gian:

1. JVM bắt đầu và bootstrap context được tạo.
2. Discovery Client kết nối registry.
3. Request tìm service ID hoàn tất và trả instance.
4. Config Client kết nối Config Server.
5. Config Server hoàn thành request lấy Environment.
6. Application context chính hoàn tất và health/readiness chuyển sang trạng thái sẵn sàng.

Có thể dùng log thời gian của Spring Boot, log Discovery Client, HTTP access log của Config Server và metric của registry để đối chiếu. Gắn correlation/request ID nếu hệ thống hỗ trợ để nối các sự kiện qua nhiều service.

Một số cách giảm thời gian:

- Đặt registry gần các workload client và Config Server theo topology mạng.
- Dùng DNS, connection pool và TLS configuration phù hợp; tránh lookup lặp lại do cấu hình registry sai.
- Đảm bảo Config Server đăng ký trạng thái healthy trước khi client phụ thuộc vào nó.
- Với Eureka, tính đến thời gian heartbeat và registry cache trước khi cho client khởi động; chỉ bật health propagation trong `application.yml` nếu cần.
- Giữ Git repository có kích thước hợp lý và dùng chiến lược cache/clone phù hợp trên Config Server.
- Đặt timeout rõ ràng, retry có giới hạn và backoff tăng dần.
- Tránh để nhiều client restart đồng loạt; dùng rolling deployment hoặc phân tán thời điểm khởi động.
- Đo riêng thời gian discovery và config fetch trước khi thay đổi kiến trúc.

Không nên tối ưu bằng cách bỏ fail-fast nếu cấu hình từ xa là bắt buộc. Nếu cho phép khởi động khi Config Server không sẵn sàng, phải có default an toàn, validation và cảnh báo khi ứng dụng chạy mà thiếu property source từ xa.

## 11. Khi nào nên dùng Discovery First?

Discovery First thường phù hợp khi:

- Config Server có thể thay đổi host/port hoặc chạy nhiều instance.
- Hệ thống đã vận hành Eureka, Consul hoặc service registry ổn định.
- Các ứng dụng cần tự tìm endpoint theo tên logic thay vì cấu hình địa chỉ từng môi trường.
- Tổ chức có quy trình đăng ký, health check, bảo mật và giám sát registry rõ ràng.

Config First thường đơn giản hơn khi:

- Config Server có endpoint ổn định qua DNS, load balancer hoặc Kubernetes Service.
- Không có service registry hoặc registry không nằm trong đường khởi động.
- Yêu cầu startup latency rất chặt và một địa chỉ ổn định là đủ.
- Hệ thống muốn giảm số dependency cần sẵn sàng trước khi ứng dụng khởi động.

Trong Kubernetes, một Service DNS ổn định như `config-server.default.svc` có thể cung cấp địa chỉ cố định cho client. Khi đó, discovery client riêng có thể không đem lại lợi ích tương xứng với chi phí và dependency bổ sung. Quyết định cần dựa trên cách nền tảng định vị service và yêu cầu vận hành thực tế.

## 12. Checklist triển khai

| Hạng mục | Điều kiện cần xác nhận |
|---|---|
| Legacy bootstrap | Bootstrap được bật bằng starter hoặc property ở system/environment |
| Discovery dependency | Config Client có đúng Discovery Client implementation |
| Registry bootstrap | Địa chỉ, credential và TLS của registry có sẵn cục bộ trước khi tải remote config |
| Config Server registration | Server đăng ký với đúng service ID và trạng thái health phù hợp |
| Service ID | `spring.cloud.config.discovery.service-id` khớp tên đăng ký; mặc định là `configserver` |
| Metadata | `configPath` và thông tin auth được khai báo đúng nếu cần |
| Timeout | Timeout discovery và Config Server được cấu hình, đo riêng |
| Fail-fast | Có quyết định rõ về việc ứng dụng được phép khởi động khi thiếu remote config hay không |
| Retry | Retry có giới hạn, backoff và cấu hình tương thích với phiên bản Spring Cloud |
| Startup metrics | Có mốc thời gian cho registry lookup, config fetch và application readiness |
| Security | Registry và Config Server đều có xác thực, TLS và quyền truy cập phù hợp |

## 13. Nguyên tắc cần ghi nhớ

- Discovery First dùng `DiscoveryClient` để tìm Config Server qua service ID; thuộc tính `spring.cloud.config.discovery.enabled` mặc định là `false`.
- Service ID mặc định là `configserver`; có thể đổi bằng `spring.cloud.config.discovery.service-id` và phải khớp tên đăng ký của Config Server.
- Legacy bootstrap phải được bật rõ ràng bằng `spring-cloud-starter-bootstrap` hoặc `spring.cloud.bootstrap.enabled=true`.
- Địa chỉ và thông tin xác thực của registry phải có sẵn trước khi Config Client lấy cấu hình từ xa.
- Discovery First thêm một network round trip lúc startup nhưng giúp Config Server đổi host/port mà client không cần sửa URI.
- `fail-fast` quyết định ứng dụng có dừng khi không lấy được cấu hình hay không; retry giúp chịu lỗi tạm thời nhưng làm startup kéo dài.
- Timeout của Config Server và timeout của service registry là hai nhóm cấu hình khác nhau.
- Metadata `configPath`, `user` và `password` có thể hỗ trợ xây dựng URL và xác thực; phải bảo vệ registry để tránh lộ dữ liệu nhạy cảm.
- Đo riêng thời gian tra cứu registry, lấy cấu hình và tạo application context trước khi tối ưu startup.

Discovery First Bootstrap đổi một địa chỉ Config Server cố định thành tên dịch vụ được tra cứu tại thời điểm khởi động. Cách này tăng tính linh hoạt khi triển khai nhiều instance hoặc thay đổi vị trí server, đồng thời thêm registry vào đường phụ thuộc khởi động. Khi bootstrap data, service ID, metadata, timeout và retry được thiết kế rõ ràng, nhóm có thể cân bằng giữa khả năng tìm dịch vụ, độ sẵn sàng và thời gian đưa ứng dụng vào trạng thái ready.

## Tài liệu tham khảo

- [Spring Cloud Config Client — Config First Bootstrap và Discovery First Lookup](https://docs.spring.io/spring-cloud-config/reference/client.html)
- [Spring Cloud Config Client 4.3 — Discovery First và retry](https://docs.spring.io/spring-cloud-config/reference/4.3/client.html)
- [Spring Cloud Netflix Eureka — Service Discovery](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
