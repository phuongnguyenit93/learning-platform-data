# Tách cấu hình kết nối khỏi mã xử lý nghiệp vụ trong Spring Messaging

## 1. Mục tiêu của việc tách biệt

Trong một ứng dụng messaging, mã nghiệp vụ cần tập trung vào câu hỏi **message có ý nghĩa gì và cần xử lý ra sao**. Thông tin để kết nối tới hạ tầng cần được quản lý ở một lớp cấu hình riêng.

Ví dụ, handler xử lý lệnh tạo đơn hàng cần biết cách gọi dịch vụ tạo đơn và kết quả nào cần phát đi. Handler không nên phải biết broker đang chạy ở hostname nào, port nào, dùng tài khoản gì, TLS được bật ra sao hoặc kết nối cần retry bao lâu.

Tách hai nhóm trách nhiệm này giúp:

- Chuyển môi trường local, test, staging và production mà không sửa logic nghiệp vụ.
- Thay broker hoặc endpoint hạ tầng với phạm vi thay đổi nhỏ hơn.
- Quản lý thông tin nhạy cảm qua biến môi trường hoặc secret manager.
- Kiểm thử nghiệp vụ mà không cần khởi động broker thật.
- Tập trung timeout, heartbeat, pool, concurrency và bảo mật tại một nơi dễ kiểm soát.
- Tránh việc mỗi handler tự tạo kết nối với cấu hình khác nhau.

Cần xác định ranh giới giữa **hợp đồng message**, **logic nghiệp vụ**, **cấu hình kết nối** và **môi trường triển khai**.

## 2. Phân chia trách nhiệm

Một thiết kế dễ bảo trì thường có bốn phần:

| Phần | Trách nhiệm | Ví dụ |
|---|---|---|
| Hợp đồng message | Định nghĩa payload, header, destination và kiểu dữ liệu | CreateOrder, OrderCreated, /topic/orders |
| Xử lý nghiệp vụ | Kiểm tra và thực hiện quy tắc nghiệp vụ | OrderApplicationService |
| Cấu hình messaging | Tạo adapter, connection factory, listener, channel và broker relay | WebSocketMessagingConfiguration |
| Cấu hình môi trường | Cung cấp host, port, credentials, TLS và tham số vận hành | application.yml, environment variables, secret manager |

**Hợp đồng message** có thể chứa destination như `/app/orders` hoặc `/topic/orders` vì đó là một phần của cách ứng dụng giao tiếp. Host, port, username, password, virtual host, certificate và thông tin kết nối broker thuộc cấu hình hạ tầng.

**Xử lý nghiệp vụ** nhận dữ liệu đã được giải mã và chuyển đổi theo hợp đồng ứng dụng. Nó không tự mở socket, tạo connection factory hoặc ghép URL broker từ các chuỗi hard-code.

## 3. Externalize các tham số kết nối

Các giá trị thường nên đưa ra khỏi mã nguồn gồm:

- Địa chỉ broker, hostname, port và virtual host.
- Username, password, token và thông tin xác thực khác.
- TLS, truststore, keystore và tùy chọn xác minh chứng thư.
- Client ID, heartbeat, connection timeout và reconnect policy.
- Pool size, consumer concurrency, prefetch và giới hạn tài nguyên.
- Retry, acknowledgement và timeout có thể thay đổi theo môi trường.

Không commit password hoặc token thật vào Git, file cấu hình mẫu, log hay thông báo lỗi. Có thể commit tên biến môi trường và giá trị mặc định an toàn cho môi trường local; thông tin thật nên được cấp qua môi trường triển khai hoặc secret manager.

Ví dụ cấu hình Spring Boot:

~~~yaml
app:
  messaging:
    stomp:
      relay-host: ${STOMP_RELAY_HOST:localhost}
      relay-port: ${STOMP_RELAY_PORT:61613}
      client-login: ${STOMP_CLIENT_LOGIN}
      client-passcode: ${STOMP_CLIENT_PASSCODE}
      system-login: ${STOMP_SYSTEM_LOGIN}
      system-passcode: ${STOMP_SYSTEM_PASSCODE}
~~~

Host và port có giá trị mặc định cho local. Credentials không có giá trị mặc định; môi trường chạy phải cung cấp chúng. Nếu dùng secret manager, nền tảng triển khai có thể đưa secret vào environment hoặc tích hợp trực tiếp theo cơ chế của nền tảng.

Không dùng credential production trong profile local hoặc test. Mỗi môi trường cần quyền truy cập và secret phù hợp với phạm vi của nó.

## 4. Bind cấu hình thành object có kiểu

Với Spring Boot 3 trở lên, `@ConfigurationProperties` là cách phù hợp để gom một nhóm thuộc tính liên quan vào object có kiểu. Ví dụ dùng Java record:

~~~java
package com.example.messaging.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.messaging.stomp")
public record StompRelayProperties(
        String relayHost,
        int relayPort,
        String clientLogin,
        String clientPasscode,
        String systemLogin,
        String systemPasscode
) {
}
~~~

Các thuộc tính YAML được bind vào record:

- `relay-host` → `relayHost`
- `relay-port` → `relayPort`
- `client-login` → `clientLogin`
- `client-passcode` → `clientPasscode`
- `system-login` → `systemLogin`
- `system-passcode` → `systemPasscode`

Đăng ký record bằng `@EnableConfigurationProperties(StompRelayProperties.class)` trên lớp cấu hình, hoặc dùng `@ConfigurationPropertiesScan` ở ứng dụng. Đây là cơ chế của Spring Boot. Nếu chỉ dùng Spring Framework mà không dùng Boot, hãy lấy giá trị từ `Environment` hoặc property source do ứng dụng cấu hình rồi truyền qua constructor hoặc factory method; `@ConfigurationProperties` không thuộc Spring Framework core.

Với cấu hình quan trọng, nên kiểm tra giá trị ngay khi ứng dụng khởi động. Có thể dùng Bean Validation cùng `@Validated`, `@NotBlank`, `@Min` và `@Max` để từ chối host rỗng, credentials thiếu hoặc port ngoài phạm vi hợp lệ. Cách này cần dependency validation tương ứng. Hãy bảo đảm secret đã được cấp trước khi khởi động ứng dụng.

## 5. Tập trung kết nối STOMP trong lớp cấu hình

Ví dụ sau cấu hình Spring WebSocket messaging với STOMP broker relay. Connection details chỉ xuất hiện trong lớp cấu hình.

~~~java
package com.example.messaging.config;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration(proxyBeanMethods = false)
@EnableWebSocketMessageBroker
@EnableConfigurationProperties(StompRelayProperties.class)
public class WebSocketMessagingConfiguration
        implements WebSocketMessageBrokerConfigurer {

    private final StompRelayProperties properties;

    public WebSocketMessagingConfiguration(
            StompRelayProperties properties) {
        this.properties = properties;
    }

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");

        registry.enableStompBrokerRelay("/topic", "/queue")
                .setRelayHost(properties.relayHost())
                .setRelayPort(properties.relayPort())
                .setClientLogin(properties.clientLogin())
                .setClientPasscode(properties.clientPasscode())
                .setSystemLogin(properties.systemLogin())
                .setSystemPasscode(properties.systemPasscode());
    }
}
~~~

Các phần chính:

- `@EnableWebSocketMessageBroker` bật hạ tầng WebSocket messaging.
- `registerStompEndpoints` đăng ký endpoint WebSocket mà client dùng để kết nối.
- `setApplicationDestinationPrefixes("/app")` khai báo prefix dành cho message đi vào các method xử lý của ứng dụng.
- `enableStompBrokerRelay("/topic", "/queue")` cấu hình relay để chuyển message tới broker STOMP bên ngoài.
- `setRelayHost` và `setRelayPort` lấy địa chỉ kết nối từ properties.
- Client credentials và system credentials được cấp riêng theo cấu hình của relay.

Trong STOMP broker relay, kết nối phục vụ các phiên client và kết nối hệ thống của relay có vai trò khác nhau. Cần cấp quyền broker tương ứng cho từng loại tài khoản. Không dùng một tài khoản có quyền quản trị rộng cho mọi kết nối ứng dụng.

Ví dụ này dùng broker relay nên cần một broker STOMP bên ngoài đang chạy và có thể truy cập được. Với môi trường thử nghiệm đơn giản, Spring hỗ trợ simple broker trong bộ nhớ qua `enableSimpleBroker`; cách đó không có cùng khả năng vận hành, lưu trữ hay mở rộng như broker bên ngoài. Chọn theo yêu cầu triển khai, không xem hai lựa chọn có bảo đảm giống nhau.

## 6. Giữ handler tập trung vào nghiệp vụ

Khi hạ tầng kết nối đã được cấu hình riêng, controller hoặc handler chỉ cần nhận dữ liệu theo hợp đồng message và gọi service nghiệp vụ.

~~~java
package com.example.messaging.orders;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Controller;

@Controller
public class OrderMessagingController {

    private final OrderApplicationService orderService;

    public OrderMessagingController(OrderApplicationService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("/orders")
    @SendTo("/topic/orders")
    public OrderStatus create(@Payload CreateOrderCommand command) {
        return orderService.create(command);
    }
}
~~~

`OrderApplicationService`, `CreateOrderCommand` và `OrderStatus` là kiểu thuộc ứng dụng, cần được định nghĩa theo mô hình nghiệp vụ của dự án.

Với prefix `/app` trong cấu hình, client gửi message tới destination `/app/orders`. Spring định tuyến tới method `create`. Kết quả trả về được gửi tới destination `/topic/orders` theo `@SendTo`.

Controller không biết broker nằm ở đâu, dùng port nào hay đăng nhập bằng tài khoản gì. Khi chuyển broker từ máy local sang production, lớp cấu hình và nguồn properties thay đổi; quy tắc tạo đơn vẫn nằm trong service nghiệp vụ.

Cần phân biệt destination với địa chỉ kết nối. `/app/orders` và `/topic/orders` là destination trong hợp đồng messaging của ứng dụng, không phải hostname hoặc URL broker. Nếu destination cần thay đổi theo môi trường, có thể đưa nó vào một nhóm cấu hình riêng, nhưng tránh rải chuỗi định tuyến tùy tiện khắp các handler.

## 7. Áp dụng nguyên tắc cho các broker khác

Mỗi công nghệ có API và semantics riêng. Cấu hình kết nối vẫn nên nằm trong lớp hạ tầng, còn listener hoặc publisher chỉ chuyển dữ liệu tới service nghiệp vụ.

| Tích hợp | Thuộc tính Spring Boot thường gặp | API ứng dụng thường dùng |
|---|---|---|
| ActiveMQ Classic qua JMS | `spring.activemq.broker-url`, `spring.activemq.user`, `spring.activemq.password` | `JmsTemplate`, `@JmsListener` |
| ActiveMQ Artemis qua JMS | `spring.artemis.broker-url` và thuộc tính xác thực tương ứng | `JmsTemplate`, `@JmsListener` |
| RabbitMQ qua AMQP | `spring.rabbitmq.host`, `spring.rabbitmq.port`, `spring.rabbitmq.username`, `spring.rabbitmq.password` | `RabbitTemplate`, `@RabbitListener` |
| Apache Kafka | `spring.kafka.bootstrap-servers` và thuộc tính producer/consumer | `KafkaTemplate`, `@KafkaListener` |

Các prefix trên là thuộc tính auto-configuration của Spring Boot và có thể khác theo provider, phiên bản hoặc cách cấu hình. Trong ứng dụng Spring Framework thuần, cần tự khai báo connection factory, client hoặc adapter bằng các bean phù hợp.

Ví dụ về cách phân chia trách nhiệm:

- Lớp cấu hình tạo và cấu hình connection factory, template, listener container hoặc adapter.
- Publisher dùng template đã được inject để gửi message.
- Listener nhận message, kiểm tra hợp đồng đầu vào rồi gọi service nghiệp vụ.
- Service nghiệp vụ không tự đọc hostname, password hay tự tạo kết nối broker.

Với Spring Integration, áp dụng cùng ranh giới: cấu hình channel, inbound/outbound adapter, connection factory và endpoint ở lớp tích hợp; service activator gọi logic nghiệp vụ. Các channel trong bộ nhớ và adapter kết nối broker có semantics khác nhau, vì vậy cần đọc rõ loại endpoint đang sử dụng.

## 8. Quản lý môi trường và secret

### 8.1 Tách cấu hình theo môi trường

Spring Boot hỗ trợ profile để đặt các giá trị khác nhau cho local, test, staging và production:

~~~text
application.yml
application-local.yml
application-test.yml
application-prod.yml
~~~

Profile local có thể trỏ tới broker chạy trên máy phát triển. Profile test có thể dùng broker riêng hoặc broker do Testcontainers khởi tạo. Production lấy địa chỉ và secret từ hệ thống triển khai.

Không cần nhân bản toàn bộ file cấu hình cho mỗi profile. Giữ các giá trị chung trong file cơ sở và chỉ override những giá trị thực sự khác biệt.

### 8.2 Quản lý secret

- Không lưu credentials thật trong repository.
- Không ghi password, token hoặc connection string có chứa secret vào log.
- Cấp quyền tối thiểu cho tài khoản ứng dụng trên broker.
- Dùng secret riêng cho client connection, system connection và từng môi trường khi kiến trúc yêu cầu.
- Có quy trình luân chuyển credentials và cập nhật secret mà không cần sửa mã nghiệp vụ.
- Không đưa secret vào exception message, metric label hoặc trace attribute.

Biến môi trường là một cách cấp cấu hình phổ biến, nhưng hệ thống production có thể dùng secret manager hoặc cơ chế identity/workload credential của nền tảng. Chọn cách phù hợp với hạ tầng đang vận hành và bảo vệ quyền đọc secret.

## 9. Kiểm thử khi cấu hình và nghiệp vụ đã tách biệt

Ranh giới rõ ràng giúp chia kiểm thử theo mục đích:

1. **Unit test nghiệp vụ:** gọi trực tiếp service hoặc handler với dữ liệu đầu vào; dùng mock/fake cho dependency cần thiết. Không cần broker thật để kiểm tra quy tắc tạo đơn.
2. **Kiểm thử binding cấu hình:** xác nhận property được bind đúng kiểu, giá trị bắt buộc được kiểm tra và cấu hình sai bị phát hiện khi khởi động.
3. **Kiểm thử cấu hình messaging:** khởi tạo application context để xác nhận bean, endpoint và adapter được đăng ký đúng.
4. **Integration test:** dùng broker thử nghiệm hoặc Testcontainers để xác minh kết nối, gửi/nhận, routing, acknowledgement và lỗi thực tế.
5. **Kiểm thử theo môi trường:** kiểm tra cấu hình production đã nhận đúng host, TLS, secret và quyền truy cập mà không in secret ra log.

Không nên dùng unit test nghiệp vụ để kiểm tra hostname broker. Ngược lại, kiểm thử kết nối broker không thay thế kiểm thử quy tắc nghiệp vụ. Mỗi loại test cần xác minh đúng trách nhiệm của lớp tương ứng.

## 10. Các lỗi thường gặp

- **Hard-code host và port trong handler:** thay môi trường buộc phải sửa logic xử lý hoặc build lại ứng dụng.
- **Tạo connection trong mỗi lần xử lý message:** gây tốn tài nguyên, tăng độ trễ và khó kiểm soát vòng đời kết nối.
- **Đọc environment trực tiếp ở nhiều lớp nghiệp vụ:** làm cấu hình phân tán và khó kiểm thử.
- **Để credentials trong YAML được commit:** secret có thể bị lộ qua lịch sử Git và bản build.
- **Gộp toàn bộ cấu hình vào một object không có cấu trúc:** thuộc tính của nhiều broker dễ nhầm lẫn và khó kiểm tra.
- **Dùng chung credential có quyền quá rộng:** tăng ảnh hưởng nếu một service hoặc secret bị lộ.
- **Nhầm simple broker với broker production:** simple broker trong bộ nhớ không tự cung cấp persistence hoặc khả năng mở rộng phân tán.
- **Đặt mọi destination vào cấu hình kết nối:** destination là hợp đồng định tuyến của ứng dụng; chỉ externalize khi có lý do thay đổi theo môi trường.
- **Không validate cấu hình khi startup:** ứng dụng có thể chỉ phát hiện host, port hoặc credentials sai khi có message đầu tiên.
- **Không có kiểm thử tích hợp:** binding đúng không chứng minh broker có thể kết nối hoặc quyền publish/subscribe là hợp lệ.

## 11. Checklist thiết kế

Trước khi đưa một tích hợp messaging vào vận hành, hãy kiểm tra:

- Handler có chỉ xử lý payload và gọi service nghiệp vụ không?
- Host, port, credentials, TLS và timeout có nằm ở lớp cấu hình không?
- Thuộc tính kết nối có được bind thành object có kiểu hoặc bean cấu hình rõ ràng không?
- Mỗi môi trường có endpoint và secret riêng phù hợp không?
- Secret có được quản lý ngoài repository và log không?
- Connection factory, template, listener và adapter có vòng đời do container quản lý không?
- Destination có được định nghĩa như một hợp đồng định tuyến nhất quán không?
- Cấu hình sai có được phát hiện khi ứng dụng khởi động không?
- Unit test nghiệp vụ có chạy mà không cần broker không?
- Integration test có xác minh được kết nối và giao nhận với broker thực tế không?

Khi các câu trả lời rõ ràng, ứng dụng có thể thay đổi hạ tầng kết nối với phạm vi nhỏ, trong khi handler và service tiếp tục phản ánh đúng nghiệp vụ.