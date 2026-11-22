# Refresh cục bộ và giới hạn lan truyền sang instance khác

Trong một hệ thống Spring Cloud chạy nhiều replica, cập nhật cấu hình ở một nơi không có nghĩa mọi instance tự động nhận giá trị mới. Có hai việc riêng biệt cần phối hợp: **refresh cục bộ** để một `ApplicationContext` nạp lại cấu hình và làm mới các bean của chính nó; **lan truyền tín hiệu** để những instance khác biết rằng chúng cũng cần refresh.

Spring Cloud Context cung cấp cơ chế refresh trong một ứng dụng. Spring Cloud Bus có thể phát sự kiện refresh qua message broker để nhiều ứng dụng/instance nhận được tín hiệu. Bus không biến nhiều JVM thành một `ApplicationContext` chung và cũng không tạo ra giao dịch cập nhật cấu hình nguyên tử trên toàn cụm. Mỗi instance vẫn thực hiện bước refresh cục bộ theo lifecycle của nó.

Bài học thuộc chương **Làm mới cấu hình** của module **SPRING_CLOUD_CORE**. Người học tìm hiểu các abstraction cốt lõi của Spring Cloud, cấu hình bên ngoài, refresh scope, discovery và cách kiểm thử/vận hành khi cấu hình cần thay đổi trên nhiều instance.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt cập nhật `Environment`, refresh bean trong một context và phát tán refresh tới nhiều instance.
2. Mô tả luồng local refresh với `ContextRefresher`, `EnvironmentChangeEvent` và `RefreshScope`.
3. Kích hoạt refresh cục bộ qua Actuator và xác định bean nào được rebind hoặc tạo lại.
4. Giải thích vai trò của Spring Cloud Bus, message broker và remote refresh event.
5. Phân biệt sự kiện refresh với nội dung cấu hình; hiểu vì sao mỗi instance cần đọc lại nguồn cấu hình.
6. Cấu hình bus refresh theo phạm vi toàn cụm hoặc một nhóm instance.
7. Hiểu vai trò của Spring Cloud Config Monitor khi nhận webhook từ hệ thống quản lý cấu hình.
8. Thiết kế kiểm tra sau refresh, xử lý instance offline, broker lỗi và trạng thái cập nhật không đồng đều.
9. Bảo vệ endpoint quản trị và tránh đưa secret vào event hoặc log.
10. Viết kiểm thử cho local refresh và kiểm thử tích hợp cho luồng nhiều instance.

## 2. Ba cấp độ cần phân biệt

### 2.1. Cập nhật nguồn cấu hình

Giá trị có thể được thay đổi trong Git repository, Config Server, file mount, biến môi trường hoặc một nguồn cấu hình tùy biến. Đây mới là **thay đổi ở nguồn**. Một ứng dụng đang chạy không nhất thiết tự biết nguồn đó đã thay đổi.

### 2.2. Refresh cục bộ

Một instance nhận lệnh refresh và cập nhật `Environment` trong `ApplicationContext` của nó. Spring Cloud có thể phát `EnvironmentChangeEvent`, rebind các bean cấu hình phù hợp và xóa target cache của `RefreshScope`.

Refresh cục bộ chỉ tác động đến context đang xử lý lệnh. Nếu ứng dụng có năm replica, gọi `/actuator/refresh` trên một replica không tự làm bốn replica còn lại refresh.

### 2.3. Lan truyền tín hiệu refresh

Spring Cloud Bus cung cấp cơ chế gửi sự kiện qua broker để nhiều instance nhận cùng một tín hiệu. Mỗi instance nhận event sẽ thực hiện refresh cục bộ của chính nó.

~~~mermaid
flowchart TD
    A[Config source thay đổi] --> B[Refresh trigger]
    B --> C{Phạm vi trigger}
    C -->|Local| D[Instance A]
    C -->|Distributed| E[Spring Cloud Bus]
    E --> F[Message broker]
    F --> G[Instance A]
    F --> H[Instance B]
    F --> I[Instance C]
    D --> J[Refresh Environment và bean trong context]
    G --> J
    H --> K[Refresh Environment và bean trong context B]
    I --> L[Refresh Environment và bean trong context C]
~~~

Sơ đồ thể hiện quan hệ logic. Bus event không truyền một `ApplicationContext` qua mạng; nó chuyển một thông điệp để các ứng dụng phù hợp tự xử lý.

| Cấp độ | Phạm vi | Thành phần tiêu biểu | Kết quả |
| --- | --- | --- | --- |
| Cập nhật nguồn | Kho cấu hình hoặc file bên ngoài | Git, Config Server, secret/config store | Nguồn có dữ liệu mới |
| Refresh cục bộ | Một `ApplicationContext` | Spring Cloud Context, `ContextRefresher`, `RefreshScope` | Một instance nạp lại cấu hình và cập nhật bean phù hợp |
| Refresh phân tán | Nhiều instance được định tuyến | Spring Cloud Bus và broker | Nhiều instance nhận tín hiệu rồi refresh cục bộ |

## 3. Refresh cục bộ trong Spring Cloud Context

### 3.1. `ContextRefresher` làm gì?

Trong Spring Cloud Context, `ContextRefresher` điều phối việc cập nhật môi trường cấu hình của một ứng dụng. Ở mức khái quát, quá trình refresh gồm:

1. Lấy lại hoặc làm mới các property source theo cơ chế cấu hình đang dùng.
2. So sánh tập thuộc tính trước và sau để xác định key thay đổi.
3. Cập nhật `Environment` của context.
4. Phát `EnvironmentChangeEvent` với tập key thay đổi.
5. Làm mới các target thuộc `RefreshScope`, để target cũ bị loại khỏi cache và được tạo lại khi cần.

Chi tiết nội bộ và cách tải lại property source phụ thuộc phiên bản Spring Cloud, Config Data hay bootstrap mode và các integration đã cài đặt. `ContextRefresher` không tự biến mọi file trên đĩa thành nguồn có khả năng hot reload.

### 3.2. `EnvironmentChangeEvent` và rebind

`EnvironmentChangeEvent` thông báo rằng một tập thuộc tính trong Environment đã thay đổi. Các thành phần tích hợp có thể lắng nghe event để cập nhật trạng thái.

Một trong những tác động thường gặp là rebind các bean `@ConfigurationProperties` phù hợp. Bean mutable có thể nhận giá trị mới theo cơ chế rebinding. Tuy nhiên, không phải mọi object đã được tạo từ cấu hình đều tự cập nhật.

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "partner.api")
public class PartnerApiProperties {
    private URI baseUrl;
    private Duration readTimeout = Duration.ofSeconds(2);

    public URI getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(URI baseUrl) {
        this.baseUrl = baseUrl;
    }

    public Duration getReadTimeout() {
        return readTimeout;
    }

    public void setReadTimeout(Duration readTimeout) {
        this.readTimeout = readTimeout;
    }
}
~~~

Bean này có thể được rebind theo cơ chế Spring Cloud Context. Nhưng nếu một HTTP client đã đọc `baseUrl` và `readTimeout` trong constructor rồi giữ chúng trong field riêng, client đó không tự thay đổi theo bean properties. Cần thiết kế client refreshable hoặc một cách đọc cấu hình động phù hợp.

### 3.3. `RefreshScope` làm mới target

Một bean cần được tạo lại khi cấu hình thay đổi có thể dùng `@RefreshScope`:

~~~java
@Component
@RefreshScope
public class PartnerClient {
    private final PartnerTransport transport;

    public PartnerClient(PartnerApiProperties properties) {
        this.transport = PartnerTransport.open(
                properties.getBaseUrl(),
                properties.getReadTimeout()
        );
    }

    public PartnerResponse send(PartnerRequest request) {
        return transport.send(request);
    }

    @PreDestroy
    public void close() {
        transport.close();
    }
}
~~~

Khi local refresh làm mới scope, target `PartnerClient` cũ được hủy và callback đóng transport được gọi. Scoped proxy vẫn được consumer giữ; lần gọi sau sẽ tạo target mới từ cấu hình hiện tại.

`PartnerTransport` là lớp ví dụ của ứng dụng. Mã thực tế phải đóng đúng tài nguyên do target sở hữu, đồng thời bảo đảm tác vụ bất đồng bộ không còn dùng transport sau khi đóng.

### 3.4. Refresh không đồng nghĩa restart

| Hành vi | Refresh | Restart |
| --- | --- | --- |
| JVM/process | Giữ nguyên | Tạo process mới hoặc khởi động lại process |
| `ApplicationContext` | Tiếp tục tồn tại; một số state/bean được cập nhật hoặc tạo lại | Context thường được tạo lại |
| `@RefreshScope` target | Có thể bị loại khỏi cache và tạo lại | Được tạo lại trong context mới |
| Static state và thread ngoài scope | Thường còn tồn tại | Có thể được tạo lại cùng process mới |
| Thay đổi không hỗ trợ refresh | Có thể vẫn giữ giá trị cũ | Có cơ hội nhận giá trị mới khi khởi động |
| Rủi ro | Bean chỉ cập nhật một phần, trạng thái cũ còn tồn tại | Gián đoạn hoặc cần rolling restart |

Không dùng refresh để thay thế restart khi thay đổi cần tác động tới những thành phần chỉ đọc cấu hình lúc khởi động, cấu hình logging đặc biệt, classpath, JVM flags hoặc các resource không thể thay thế an toàn.

## 4. Kích hoạt refresh cục bộ bằng Actuator

Khi ứng dụng có Spring Boot Actuator và Spring Cloud Context phù hợp, endpoint refresh có thể được bật để quản trị cấu hình runtime.

Ví dụ cấu hình:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,refresh
~~~

Gửi HTTP POST tới:

~~~http
POST /actuator/refresh
~~~

Có thể dùng curl:

~~~bash
curl -X POST http://localhost:8080/actuator/refresh
~~~

Endpoint trả về tập key thay đổi theo phiên bản và implementation đang dùng. Hãy đọc kết quả cùng log của ứng dụng; phản hồi HTTP thành công không tự chứng minh mọi bean mới đã khởi tạo và mọi dependency đều hoạt động.

### 4.1. Điều kiện để endpoint hoạt động

- Có dependency Actuator.
- Có Spring Cloud Context và auto-configuration refresh phù hợp.
- Endpoint được expose qua management configuration.
- Security cho phép caller có quyền thực hiện thao tác.
- Ứng dụng có nguồn cấu hình có thể được cập nhật hoặc đọc lại.

Chỉ thêm `refresh` vào `management.endpoints.web.exposure.include` không tạo ra implementation nếu dependency cần thiết không có trên classpath.

### 4.2. Bảo vệ endpoint quản trị

Refresh có thể thay đổi hành vi của instance đang phục vụ request. Không mở endpoint này cho người dùng cuối hoặc mạng công khai.

Nên:

- Dùng authentication và authorization.
- Giới hạn management interface/port và network policy.
- Chỉ cấp quyền cho pipeline hoặc operator được phép thay đổi cấu hình.
- Ghi audit ai đã refresh, lúc nào và ở môi trường nào.
- Không log secret hoặc toàn bộ nội dung Environment.
- Dùng cơ chế phê duyệt/rollout phù hợp với mức độ ảnh hưởng của cấu hình.

Nếu endpoint được expose qua mạng nội bộ, vẫn cần xác thực và phân quyền. “Nội bộ” không đồng nghĩa mọi workload đều được quyền refresh.

## 5. Vì sao local refresh không lan sang replica khác?

Mỗi replica thường chạy trong một JVM và có `ApplicationContext`, `Environment`, bean cache và resource riêng.

Giả sử `orders-service` có ba instance:

~~~text
orders-service-1  -> JVM 1 -> ApplicationContext 1
orders-service-2  -> JVM 2 -> ApplicationContext 2
orders-service-3  -> JVM 3 -> ApplicationContext 3
~~~

Gọi:

~~~http
POST http://orders-service-1/actuator/refresh
~~~

chỉ yêu cầu instance 1 refresh context của nó. Hai instance còn lại không nhận được lệnh này chỉ vì chúng dùng cùng Config Server hoặc cùng service name.

Những lý do chính:

- `ApplicationContext` là đối tượng trong bộ nhớ của một process.
- Scoped proxy và target cache thuộc scope của context đó.
- `EnvironmentChangeEvent` là event nội bộ của Spring context, không phải message broker event tự động phát ra mạng.
- Config Server lưu/cung cấp cấu hình; nó không mặc định gửi tín hiệu tới mọi client khi Git thay đổi.
- Service discovery giúp tìm địa chỉ instance; nó không phải kênh broadcast refresh.

Nếu muốn tất cả replica cập nhật, cần một cơ chế lan truyền như Spring Cloud Bus, orchestration rollout hoặc một hệ thống điều phối riêng.

## 6. Spring Cloud Bus lan truyền refresh như thế nào?

Spring Cloud Bus liên kết các ứng dụng Spring Cloud với một message broker để phát và nhận event giữa các node. Các binder phổ biến tích hợp với RabbitMQ hoặc Kafka.

### 6.1. Luồng xử lý tổng quát

~~~mermaid
sequenceDiagram
    participant Operator as Operator / CI
    participant A as Instance A
    participant Broker as RabbitMQ / Kafka
    participant B as Instance B
    participant C as Instance C
    participant Config as Config Server

    Operator->>A: POST /actuator/busrefresh
    A->>Broker: Publish RefreshRemoteApplicationEvent
    Broker-->>A: Deliver event
    Broker-->>B: Deliver event
    Broker-->>C: Deliver event
    A->>Config: Load current configuration
    B->>Config: Load current configuration
    C->>Config: Load current configuration
    A->>A: Refresh local Environment and beans
    B->>B: Refresh local Environment and beans
    C->>C: Refresh local Environment and beans
~~~

Luồng minh họa:

1. Operator hoặc pipeline gọi endpoint bus refresh ở một instance.
2. Instance đó tạo remote refresh event.
3. Spring Cloud Bus gửi event qua binder tới broker.
4. Những ứng dụng nằm trong phạm vi định tuyến nhận event.
5. Mỗi ứng dụng thực hiện refresh cục bộ.
6. Config Client hoặc integration tương ứng lấy cấu hình mới từ nguồn của instance đó.
7. Các bean được rebind hoặc refresh theo chính sách cục bộ.

Bus event chủ yếu là **tín hiệu yêu cầu refresh**. Không nên giả định event mang toàn bộ file cấu hình hoặc secret mới. Mỗi instance cần có quyền truy cập nguồn cấu hình và phải tự nạp dữ liệu mới.

### 6.2. Dependency cho Bus

Với Maven, ví dụ dùng RabbitMQ binder:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-bus-amqp</artifactId>
</dependency>
~~~

Với Kafka binder:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-bus-kafka</artifactId>
</dependency>
~~~

Tên artifact và khả năng tương thích cần được kiểm tra theo Spring Cloud release train đang dùng. Quản lý version qua `spring-cloud-dependencies` BOM tương thích với Spring Boot; không tự ghép phiên bản Bus, Stream binder và Boot.

### 6.3. Cấu hình broker

Ví dụ RabbitMQ:

~~~yaml
spring:
  rabbitmq:
    host: rabbitmq.internal
    port: 5672
    username: ${RABBITMQ_USERNAME}
    password: ${RABBITMQ_PASSWORD}
~~~

Ví dụ Kafka:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1.internal:9092,kafka-2.internal:9092
~~~

Đây chỉ là cấu hình kết nối tối thiểu. Production cần TLS, xác thực, quyền publish/consume, network policy, retry/backoff và cấu hình broker phù hợp. Không commit credential thật vào repository.

### 6.4. Expose busrefresh endpoint

Ví dụ:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,busrefresh
~~~

Gọi:

~~~http
POST /actuator/busrefresh
~~~

Trong các phiên bản hỗ trợ, có thể định tuyến tới destination cụ thể bằng path tương ứng, ví dụ endpoint có phần destination sau `/actuator/busrefresh/`. Cú pháp pattern, cách khớp `serviceId` và `bus id` cần đối chiếu tài liệu release train đang dùng.

Không nên expose endpoint này rộng rãi. Một lần gọi có thể làm nhiều instance hủy và tạo lại resource cùng lúc, tạo spike lên Config Server, database, HTTP dependency hoặc connection broker.

## 7. Refresh toàn cụm và refresh có chọn lọc

Không phải thay đổi nào cũng cần refresh tất cả instance. Có thể phân biệt phạm vi:

| Phạm vi | Ví dụ | Cách xử lý |
| --- | --- | --- |
| Một instance | Kiểm thử cấu hình mới trên canary | Local refresh hoặc destination trỏ tới một bus id |
| Một service | Tất cả replica của `orders-service` | Bus destination theo service ID/pattern |
| Nhiều service | Thay đổi cấu hình dùng chung | Bus refresh toàn nhóm phù hợp hoặc rollout có điều phối |
| Toàn cụm | Thay đổi platform config ảnh hưởng nhiều ứng dụng | Phát event có phạm vi rộng, theo dõi rollout và tải hệ thống |

### 7.1. Destination và định danh instance

Bus cần định danh các application instance để định tuyến và tránh xử lý lặp event của chính sender. Bus ID thường được xây dựng từ các thuộc tính như application name, profile và thông tin instance/port; cấu hình cụ thể có thể khác theo phiên bản.

Các instance cần có ID duy nhất trong phạm vi bus. Nếu hai node dùng cùng định danh, routing và loại trừ event có thể hoạt động sai hoặc gây khó khăn khi theo dõi.

Có thể cấu hình rõ bus ID khi cần:

~~~yaml
spring:
  cloud:
    bus:
      id: ${spring.application.name}:${HOSTNAME:${random.value}}
~~~

Biểu thức trên là ví dụ minh họa cách tạo ID khác nhau theo host hoặc giá trị ngẫu nhiên; cần xác nhận placeholder có sẵn trong môi trường và cách triển khai container. Tránh dùng ID giống nhau cho mọi replica.

### 7.2. Chọn destination cẩn thận

Destination pattern giúp giới hạn ứng dụng nhận event. Trước khi dùng pattern, hãy xác nhận:

- ID của từng instance thực tế.
- Quy tắc matching của Bus trong release train.
- Có bao nhiêu node sẽ nhận event.
- Sender có nhận lại event của chính nó hay không.
- Những instance offline sẽ xử lý thế nào khi quay lại.

Không dùng wildcard rộng nếu thay đổi chỉ liên quan một service. Refresh diện rộng có thể làm nhiều connection pool hoặc client cùng khởi tạo lại, gây tải đột biến lên backend.

## 8. Config Server Monitor và webhook

Khi cấu hình được quản lý trong Git hoặc một hệ thống repository, pipeline có thể gọi webhook sau khi cấu hình thay đổi. Spring Cloud Config Monitor hỗ trợ nhận thông báo thay đổi và kết hợp với Spring Cloud Bus để gửi refresh event tới các ứng dụng liên quan.

Luồng khái quát:

~~~mermaid
flowchart LR
    A[Git repository changed] --> B[Webhook]
    B --> C[Config Server Monitor]
    C --> D[RefreshRemoteApplicationEvent]
    D --> E[Message broker]
    E --> F[Config Client instances]
    F --> G[Fetch current config and refresh locally]
~~~

Các thành phần thường cần có:

- Spring Cloud Config Server.
- Config Monitor integration tương thích.
- Spring Cloud Bus trên Config Server.
- Message broker được cấu hình.
- Các Config Client cần refresh cũng tham gia Bus.
- Webhook được cấu hình ở Git provider hoặc hệ thống quản lý cấu hình.

Endpoint monitor thường là `/monitor` trên Config Server. Cách gửi payload, mapping file thay đổi sang application name và việc định tuyến event phụ thuộc provider webhook, phiên bản và cấu hình monitor. Hãy kiểm tra tài liệu Spring Cloud Config Monitor thay vì giả định mọi webhook JSON đều có cùng format.

### 8.1. Monitor không phải cơ chế polling

Config Monitor nhận thông báo từ webhook; nó không mặc định poll Git liên tục. Nếu webhook không tới, không hợp lệ hoặc Config Server không thể publish event, các client có thể tiếp tục dùng cấu hình cũ.

Nên có bước xác minh độc lập sau pipeline cập nhật: kiểm tra revision/version cấu hình, gọi health hoặc kiểm tra giá trị đã nạp trên các instance.

### 8.2. Không gửi secret trong webhook

Webhook chỉ nên cung cấp thông tin cần để xác định cấu hình thay đổi. Không đưa password, token hoặc nội dung secret vào payload nếu không có yêu cầu và cơ chế bảo vệ rõ ràng. Mỗi client nên lấy dữ liệu qua Config Client/secret integration với quyền riêng.

## 9. Giới hạn nhất quán trong môi trường phân tán

### 9.1. Không có atomic refresh toàn cụm

Khi một event được phát, các instance có thể nhận và xử lý ở thời điểm khác nhau. Trong một khoảng thời gian:

- Instance A đã dùng cấu hình mới.
- Instance B vẫn dùng cấu hình cũ.
- Instance C đang refresh hoặc đang tạo lại target.
- Instance D offline và chưa nhận event.

Đây là trạng thái **eventual consistency**. Spring Cloud Bus không cung cấp một giao dịch phân tán bảo đảm mọi instance đổi cấu hình cùng một thời điểm.

Nếu nghiệp vụ không chịu được hai phiên bản cấu hình chạy đồng thời, cần một chiến lược rollout có điều phối, drain traffic hoặc restart/blue-green thay vì dựa vào bus refresh đơn thuần.

### 9.2. Event được giao không có nghĩa refresh thành công

Có thể phân biệt các mốc:

1. Event được sender publish.
2. Broker nhận và lưu/chuyển tiếp event.
3. Instance nhận event.
4. Instance bắt đầu refresh.
5. Instance nạp được cấu hình mới.
6. Bean được rebind hoặc target được tạo lại.
7. Instance phục vụ request thành công bằng cấu hình mới.

Một dashboard chỉ thấy message broker nhận event chưa chứng minh bước 5-7 đã thành công. Cần quan sát ở phía instance.

### 9.3. Instance offline

Nếu một instance offline trong lúc event được phát, kết quả khi nó quay lại phụ thuộc broker, consumer group/subscription, persistence, retention và cách ứng dụng đăng ký nhận event. Không nên mặc định mọi broker/binder sẽ lưu một event refresh đủ lâu cho mọi node offline.

Khi instance khởi động lại, Config Client thường lấy cấu hình hiện tại trong quá trình startup theo cơ chế đã cấu hình. Đây là lý do startup verification và config revision tracking vẫn cần thiết ngay cả khi đã dùng Bus.

### 9.4. Event trùng lặp hoặc đến trễ

Một hệ thống phân tán có thể gặp event lặp, retry hoặc xử lý chậm. Refresh thường được thiết kế như một thao tác có thể lặp, nhưng việc tạo lại resource vẫn có chi phí.

- Tránh callback hủy gây tác dụng phụ không thể lặp an toàn.
- Đảm bảo `close()` và khởi tạo target mới có xử lý lỗi rõ ràng.
- Theo dõi event ID, origin và thời điểm nhận.
- Tránh kích hoạt refresh liên tục cho mỗi commit nhỏ.
- Gom nhiều thay đổi thành một lần phát event khi phù hợp.

## 10. Quản lý thay đổi cấu hình có kiểm soát

### 10.1. Gắn revision hoặc version cho cấu hình

Để xác minh instance đã nạp cùng một bộ cấu hình, có thể cung cấp metadata không nhạy cảm như:

~~~yaml
app:
  config:
    revision: "release-2026-11-18.3"
~~~

Sau refresh, mỗi instance có thể expose revision qua một endpoint nội bộ hoặc metric an toàn. Điều này giúp biết instance nào đã cập nhật, instance nào còn cũ và instance nào thất bại.

Không dùng hash có thể suy ra secret hoặc ghi toàn bộ cấu hình vào log. Revision chỉ nên định danh bản cấu hình, không chứa nội dung bí mật.

### 10.2. Canary trước khi refresh toàn cụm

Một quy trình an toàn hơn cho thay đổi rủi ro cao:

1. Cập nhật cấu hình tại nguồn và gắn revision.
2. Chọn một canary instance hoặc một nhóm nhỏ.
3. Refresh canary.
4. Kiểm tra giá trị mới, health, error rate và hành vi nghiệp vụ.
5. Nếu đạt yêu cầu, phát refresh cho nhóm còn lại.
6. Xác minh revision và health trên từng instance.
7. Nếu có lỗi, dừng rollout và thực hiện rollback cấu hình có kiểm soát.

Không phải mọi thay đổi đều cần canary; với thay đổi đơn giản và đã được kiểm thử có thể dùng quy trình gọn hơn. Nhưng với timeout, endpoint, credential hoặc chính sách truy cập, kiểm tra từng bước giúp giới hạn phạm vi ảnh hưởng.

### 10.3. Rollback cũng là một lần thay đổi cấu hình

Khi cấu hình mới gây lỗi, rollback nguồn cấu hình chưa đủ. Các instance đang chạy vẫn có thể giữ giá trị mới cho đến khi nhận refresh hoặc restart. Quy trình rollback cần:

- Khôi phục revision trước ở nguồn.
- Phát tín hiệu refresh phù hợp.
- Xác minh từng instance đã quay lại revision cũ.
- Kiểm tra resource được tạo lại và kết nối thành công.
- Theo dõi request lỗi cho đến khi hệ thống ổn định.

## 11. Những loại cấu hình không nên refresh tùy tiện

Một số thay đổi có thể không an toàn khi thay trực tiếp trong runtime:

| Nhóm cấu hình | Rủi ro | Chiến lược cân nhắc |
| --- | --- | --- |
| Timeout của HTTP client | Client có thể giữ giá trị constructor cũ | Refresh/recreate client hoặc hỗ trợ cấu hình động |
| Endpoint downstream | Target cũ cần đóng, target mới phải kết nối được | Canary, health probe và rollback |
| Database URL/credential | Connection pool hiện tại có thể không thể rebind an toàn | Pool replacement/drain hoặc rolling restart |
| Thread/connection pool size | Thay đổi có thể gây cạn tài nguyên hoặc spike | Giới hạn, đo tải và rollout theo nhóm |
| JVM flags, heap, GC | Không thể thay bằng refresh bean | Restart với cấu hình khởi động mới |
| Classpath/auto-configuration | Cần dependency mới hoặc thay đổi cấu trúc bean | Build và deploy artifact mới |
| Secret rotation | Client cũ có thể còn giữ credential cũ | Phối hợp rotation, refresh và xác minh quyền truy cập |
| Feature flag | Có thể làm thay đổi hành vi nghiệp vụ tức thì | Kiểm thử tương thích và rollout theo nhóm người dùng |

HikariDataSource là ví dụ thường được loại khỏi danh sách refreshable mặc định trong Spring Cloud. Không coi `@RefreshScope` là cách thay thế datasource an toàn; cần thiết kế vòng đời pool cụ thể.

## 12. Kiểm thử local refresh và distributed refresh

### 12.1. Unit/integration test cho local refresh

Một test local nên xác nhận:

- Environment nhận giá trị mới.
- `EnvironmentChangeEvent` được phát cho key thay đổi nếu dùng cơ chế tương ứng.
- Bean `@ConfigurationProperties` được cập nhật theo khả năng của nó.
- Target `@RefreshScope` cũ bị hủy.
- Target mới được tạo ở lần truy cập proxy tiếp theo.
- Callback giải phóng tài nguyên được gọi.

Ví dụ test logic target:

~~~java
@Test
void refreshRecreatesScopedTarget() {
    int oldId = partnerClient.id();

    assertThat(refreshScope.refresh("partnerClient")).isTrue();

    int newId = partnerClient.id();

    assertThat(newId).isNotEqualTo(oldId);
}
~~~

Test cần Spring Cloud Context, scope `refresh` và bean được inject qua scoped proxy. Để chứng minh callback hủy, dùng bộ đếm `created`/`destroyed` như bài về vòng đời Refresh Scope.

### 12.2. Integration test cho Bus

Kiểm thử Bus cần tối thiểu hai application instance và broker thật hoặc container/test environment phù hợp.

Kịch bản:

1. Khởi động hai instance cùng service hoặc hai ứng dụng có bus ID riêng.
2. Xác nhận cả hai đã kết nối broker và có revision cấu hình ban đầu.
3. Cập nhật cấu hình ở Config Server hoặc test source.
4. Gửi bus refresh từ một instance.
5. Chờ event tới instance còn lại.
6. Kiểm tra mỗi instance đã nạp revision mới.
7. Xác nhận target cũ đã được đóng và target mới được tạo khi truy cập.
8. Kiểm tra một instance tạm dừng hoặc broker bị ngắt để quan sát khả năng phục hồi.

Không dùng `Thread.sleep` cố định làm bằng chứng duy nhất. Dùng polling có timeout hoặc điều kiện đồng bộ để chờ revision/health đạt giá trị mong đợi.

### 12.3. Kiểm thử phạm vi destination

Nếu dùng destination pattern, hãy xác minh:

- Instance ngoài phạm vi không refresh.
- Instance trong phạm vi đều nhận event.
- ID duy nhất và mapping service/profile đúng.
- Event do sender phát không gây xử lý lặp ngoài ý muốn.
- Pattern không vô tình khớp một service khác.

### 12.4. Kiểm thử lỗi và rollback

Cần thử ít nhất:

| Kịch bản | Điều cần xác nhận |
| --- | --- |
| Config Server không truy cập được | Local refresh xử lý theo chính sách fail-fast/optional |
| Broker không sẵn sàng | Sender biết publish thất bại; instance không được coi là đã cập nhật |
| Instance offline | Có kế hoạch startup lấy cấu hình mới hoặc refresh bù |
| Target mới tạo thất bại | Lỗi được log/health phản ánh; không đánh dấu instance healthy chỉ vì event đã nhận |
| Callback đóng chậm | Thời gian refresh có giới hạn và được quan sát |
| Event lặp | Cleanup và recreation không tạo resource leak |
| Revision sai | Rollout dừng và rollback được xác minh |

## 13. Quan sát và vận hành production

Nên theo dõi các tín hiệu ở cả pipeline, broker và instance:

| Tầng | Chỉ số/log nên quan sát |
| --- | --- |
| Config repository/Config Server | Revision, thời điểm cập nhật, lỗi lấy cấu hình, request theo application/profile |
| Refresh trigger | Người gọi, destination, thời điểm, kết quả HTTP |
| Bus/broker | Publish/consume rate, queue lag, connection, retry và lỗi delivery |
| Mỗi instance | Revision hiện tại, event nhận được, thời gian refresh, key thay đổi ở mức an toàn |
| Bean/resource | Target creation/destruction, lỗi callback, connection pool và client health |
| Ứng dụng | Readiness, request error rate, p95/p99 latency, dependency failures |

Không ghi toàn bộ cấu hình hoặc secret để debug. Dùng revision, tên nguồn, số lượng key thay đổi và correlation/event ID khi cần truy vết.

### 13.1. Health không đồng nghĩa đồng bộ cấu hình

Một instance có thể báo health UP nhưng vẫn đang dùng revision cũ nếu health check không kiểm tra cấu hình. Nếu đồng bộ revision là yêu cầu nghiệp vụ, cần một chỉ báo riêng và quy tắc readiness rõ ràng.

Ví dụ, có thể xem instance sẵn sàng khi:

- Đã nạp revision tối thiểu được triển khai.
- Target client quan trọng đã khởi tạo thành công.
- Các dependency bắt buộc có thể truy cập.
- Không còn refresh đang xử lý.

Không nên làm readiness phụ thuộc vào một dependency tùy chọn nếu ứng dụng vẫn có thể phục vụ phần nghiệp vụ cốt lõi.

### 13.2. Tránh refresh storm

Nếu nhiều commit hoặc webhook phát liên tiếp, mọi instance có thể đồng loạt hủy và tạo lại client/pool. Hậu quả là:

- Config Server nhận nhiều request đồng thời.
- Broker có queue lag.
- Dependency nhận spike kết nối mới.
- Các request đang chạy có thể gặp lỗi khi target/resource chuyển đổi.

Có thể debounce hoặc gom thay đổi ở pipeline, giới hạn tần suất, rollout theo nhóm và dùng jitter cho bước xác minh/retry. Không retry publish vô hạn khi broker lỗi.

## 14. Bảo mật và quyền kiểm soát

Refresh là thao tác quản trị có tác động tới hành vi runtime. Cần kiểm soát cả đường local lẫn đường bus:

- Chỉ operator/pipeline có quyền gọi `/actuator/refresh` hoặc `/actuator/busrefresh`.
- Bảo vệ endpoint Config Server Monitor và webhook bằng secret/signature hoặc cơ chế xác thực của nền tảng.
- Dùng broker credential riêng, quyền publish/consume tối thiểu và TLS.
- Phân tách bus destination theo môi trường để dev không phát event sang production.
- Không đưa secret vào Bus event; event chỉ nên là tín hiệu.
- Audit người phát lệnh, service/destination và revision mong muốn.
- Giới hạn quyền rollback và refresh toàn cụm.
- Kiểm thử quyền truy cập endpoint và broker trong pipeline.

Nếu nhiều môi trường dùng chung broker, cần namespace/vhost/topic và credential tách biệt. Chỉ khác `spring.application.name` chưa chắc đủ để cô lập event giữa các môi trường.

## 15. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Gọi `/actuator/refresh` chỉ một replica đổi cấu hình | Đây là local refresh | Dùng Bus hoặc orchestration rollout cho các replica còn lại |
| `/actuator/busrefresh` không tồn tại | Thiếu Bus starter, Actuator hoặc endpoint chưa expose | Kiểm tra dependency và management configuration |
| Sender trả thành công nhưng instance khác không đổi | Broker/binder hoặc destination sai; instance không consume | Kiểm tra bus ID, broker connection, queue lag và log từng node |
| Event nhận được nhưng giá trị vẫn cũ | Config Client chưa tải nguồn mới hoặc Config Server còn revision cũ | Kiểm tra Config Server, application/profile/label và property source |
| Một số instance cập nhật, số khác không | Event chưa tới, instance offline hoặc lỗi refresh cục bộ | Theo dõi revision theo từng instance và thực hiện refresh bù |
| Refresh target lỗi sau khi nhận event | Cấu hình mới không hợp lệ hoặc dependency không sẵn sàng | Kiểm tra target initialization và health |
| Refresh lặp làm hệ thống chậm | Webhook/event storm hoặc callback tốn thời gian | Debounce, giới hạn tần suất và rollout theo nhóm |
| Config Server Monitor không phát event | Webhook sai endpoint/payload hoặc thiếu Bus integration | Kiểm tra monitor dependency, webhook auth và log Config Server |
| Event đi nhầm môi trường | Các môi trường dùng chung bus destination | Cô lập broker namespace/vhost/topic và credentials |
| Rollback nguồn nhưng instance vẫn dùng config mới | Chưa phát refresh hoặc chưa xác minh mọi instance | Phát tín hiệu rollback và kiểm tra revision trên từng node |

## 16. Quy trình triển khai refresh phân tán

Một quy trình thực tế cho `orders-service` có thể như sau:

1. **Chuẩn bị:** kiểm tra release train, Config Client, Bus binder, broker, endpoint bảo mật và health check.
2. **Cập nhật nguồn:** commit cấu hình mới và ghi nhận revision.
3. **Kích hoạt:** dùng pipeline gọi Config Server Monitor webhook hoặc gọi bus refresh theo quyền được cấp.
4. **Lan truyền:** Bus publish event tới các instance đúng destination.
5. **Refresh cục bộ:** mỗi instance tự nạp cấu hình, phát event nội bộ, rebind và làm mới target phù hợp.
6. **Xác minh:** thu thập revision, health, target recreation và request error rate theo từng instance.
7. **Mở rộng:** nếu canary đạt, tiếp tục nhóm còn lại hoặc hoàn tất rollout.
8. **Rollback:** nếu lỗi, khôi phục revision trước, phát refresh mới và xác minh từng node.

Với thay đổi có tính phá vỡ hoặc cần đồng bộ nghiêm ngặt, dùng rolling deployment hoặc blue-green deployment có thể phù hợp hơn refresh runtime.

## 17. Bài tập vận dụng

**Bài tập 1 — Local hay distributed?** Một service có bốn replica. Operator gọi `POST /actuator/refresh` trên một replica. Hãy mô tả trạng thái cấu hình của bốn instance và đề xuất cơ chế để cập nhật các replica còn lại.

**Bài tập 2 — Bus flow.** Vẽ luồng từ Config Server Monitor webhook đến broker và ba Config Client. Đánh dấu bước nào tải nội dung cấu hình và bước nào chỉ phát tín hiệu.

**Bài tập 3 — Cấu hình Bus.** Thêm Bus AMQP hoặc Kafka starter, cấu hình broker và expose `busrefresh`. Xác nhận hai instance có bus ID riêng và nhận event.

**Bài tập 4 — Destination.** Phát event tới một service cụ thể. Chứng minh instance ngoài destination không refresh và instance trong destination đều nhận được tín hiệu.

**Bài tập 5 — Offline instance.** Tắt một replica trước khi phát event, sau đó bật lại. Xác định broker có lưu event cho consumer offline không và vì sao startup phải nạp revision mới nhất.

**Bài tập 6 — Event đã tới nhưng target lỗi.** Cấu hình endpoint mới sai, phát bus refresh và theo dõi target creation. Thiết kế health check để không đánh dấu instance sẵn sàng chỉ vì event được nhận.

**Bài tập 7 — Canary và rollback.** Cập nhật timeout hoặc endpoint của Inventory. Refresh một canary, đo error rate/latency, sau đó rollout toàn cụm hoặc rollback theo revision.

**Bài tập 8 — Security.** Kiểm tra quyền gọi local refresh, bus refresh, Config Server Monitor và quyền publish/consume broker. Chứng minh workload không có quyền không thể kích hoạt refresh production.

## 18. Ghi nhớ và nguồn tra cứu

- **Local refresh** chỉ cập nhật `Environment` và bean trong `ApplicationContext` đang xử lý lệnh.
- `EnvironmentChangeEvent` hỗ trợ thông báo key thay đổi và rebind bean cấu hình phù hợp.
- `RefreshScope` loại target khỏi cache; proxy vẫn tồn tại và target mới được tạo khi cần.
- **Spring Cloud Bus** lan truyền tín hiệu qua broker; mỗi instance nhận event phải tự refresh cục bộ.
- Bus event không phải bản sao `ApplicationContext` và không nên chứa secret/config payload.
- **Config Server Monitor** có thể nhận webhook rồi kết hợp Bus để phát tín hiệu refresh; nó không mặc định poll Git.
- Distributed refresh có tính eventual consistency; không có atomic update trên toàn cụm.
- Instance offline, broker lỗi, event trùng hoặc target khởi tạo thất bại đều cần kế hoạch quan sát và phục hồi.
- Theo dõi revision và health từng instance; không kết luận thành công chỉ từ HTTP response của sender.
- Với thay đổi không hỗ trợ refresh hoặc cần đồng bộ nghiêm ngặt, cân nhắc rolling restart/blue-green deployment.

Nguồn chính thức để đối chiếu theo phiên bản Spring Boot/Spring Cloud của dự án:

1. [Spring Cloud Context – Refresh Scope và Context Refresh](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
2. [Spring Cloud Bus – Reference Guide](https://docs.spring.io/spring-cloud-bus/reference/)
3. [Spring Cloud Config – Client Side Usage và Config Data](https://docs.spring.io/spring-cloud-config/reference/client.html)
4. [Spring Cloud Config – Monitor](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/monitor.html)
5. [Spring Boot Actuator – Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
6. [Spring Cloud – Release train và tương thích Spring Boot](https://spring.io/projects/spring-cloud/)
