# Vai trò và phụ thuộc của các mô-đun messaging, jms và websocket

Spring Framework chia chức năng messaging thành nhiều module nhỏ. Ba artifact thường gặp là spring-messaging, spring-jms và spring-websocket. Chúng có thể phối hợp trong cùng một ứng dụng, nhưng mỗi module giải quyết một lớp riêng: mô hình message, tích hợp với JMS provider và giao tiếp WebSocket với client.

Khi thiết kế dependency, cần phân biệt ba loại thành phần:

1. **Spring integration module:** thư viện Spring cung cấp abstraction, template, listener và cấu hình.
2. **Protocol API và runtime:** API chuẩn mà integration module gọi, cùng implementation tương ứng.
3. **Hạ tầng bên ngoài:** broker, servlet container, WebSocket endpoint hoặc client kết nối với ứng dụng.

Thêm một Spring module chỉ đưa code tích hợp vào classpath. Nó không tự cài đặt hoặc khởi chạy mọi broker, server hay dịch vụ mà ứng dụng cần.

## 1. Vai trò của từng artifact

### 1.1. spring-messaging

Artifact: org.springframework:spring-messaging.

Đây là lớp nền tảng cho messaging trong Spring. Module định nghĩa mô hình message và các hợp đồng để các thành phần trao đổi dữ liệu mà không phụ thuộc trực tiếp vào một transport cụ thể.

Các kiểu API quan trọng:

- Message<T>: message có payload và headers.
- MessageHeaders: metadata gắn với message.
- MessageChannel: hợp đồng gửi message.
- MessageHandler: hợp đồng xử lý message.
- SubscribableChannel và PollableChannel: hai kiểu channel với cách nhận message khác nhau.
- MessageBuilder: xây dựng message.
- MessageConverter: chuyển payload giữa message và kiểu Java.
- MessageSendingOperations và MessageReceivingOperations: các hợp đồng thao tác gửi/nhận.
- GenericMessagingTemplate: template làm việc với destination là MessageChannel.
- Các abstraction trong package simp: hỗ trợ Simple Messaging Protocol, bao gồm STOMP.

spring-messaging không yêu cầu ứng dụng phải kết nối JMS broker hoặc mở WebSocket. Có thể dùng các abstraction này để tổ chức luồng message bên trong ứng dụng. Khi tích hợp với transport, module chuyên biệt sẽ kết nối abstraction đó với giao thức tương ứng.

### 1.2. spring-jms

Artifact: org.springframework:spring-jms.

Module này tích hợp ứng dụng Spring với Jakarta Messaging (JMS). JMS cung cấp API chuẩn cho giao tiếp message giữa ứng dụng và một JMS provider. Spring bổ sung các tiện ích để gửi, nhận, chuyển đổi message, quản lý listener container và tham gia transaction.

Các API tiêu biểu:

- JmsTemplate: gửi và nhận message theo kiểu đồng bộ.
- JmsMessagingTemplate: adapter để dùng Spring Messaging abstraction khi làm việc với JMS.
- @JmsListener: khai báo method nhận message.
- @EnableJms: bật xử lý listener annotation trong cấu hình Spring Framework thuần.
- DefaultJmsListenerContainerFactory và SimpleJmsListenerContainerFactory: cấu hình listener container.
- JmsTransactionManager: transaction manager cục bộ cho một JMS ConnectionFactory.
- MessageConverter: chuyển đổi giữa JMS message và đối tượng Java.

spring-jms cần một jakarta.jms.ConnectionFactory thực sự. ConnectionFactory này thường do client library của nhà cung cấp broker tạo ra. Các ví dụ provider có thể dùng gồm ActiveMQ Artemis hoặc ActiveMQ Classic phiên bản hỗ trợ Jakarta Messaging tương thích.

Spring không phải JMS provider. Nếu chỉ thêm spring-jms mà không có implementation phù hợp và cấu hình kết nối, ứng dụng chưa thể gửi hoặc nhận message qua broker.

### 1.3. spring-websocket

Artifact: org.springframework:spring-websocket.

Module này cung cấp hỗ trợ WebSocket ở phía server trên Servlet stack, gồm:

- API xử lý WebSocket frame trực tiếp qua WebSocketHandler.
- Cấu hình endpoint và handshake.
- SockJS fallback cho môi trường không hỗ trợ WebSocket đầy đủ.
- STOMP messaging chạy trên WebSocket.
- Các thành phần hỗ trợ session, transport và kết nối broker.

Khi chỉ dùng raw WebSocket, ứng dụng có thể xử lý frame bằng handler riêng. Khi dùng STOMP, spring-websocket phối hợp với spring-messaging để biểu diễn frame thành Message, định tuyến qua channel và gọi method có annotation như @MessageMapping.

spring-websocket không thay thế servlet container. Ứng dụng vẫn cần môi trường server có hỗ trợ WebSocket, chẳng hạn embedded Tomcat hoặc Jetty trong ứng dụng Spring Boot, hoặc một standalone container được cấu hình đúng.

Với ứng dụng reactive WebFlux, cần phân biệt API WebSocket reactive thuộc spring-webflux với API Servlet WebSocket thuộc spring-websocket. Không nên chọn artifact chỉ dựa trên tên giao thức.

## 2. Quan hệ phụ thuộc giữa các module

Các module Spring dùng chung những nền tảng như spring-core, spring-beans và spring-context. Trong đó spring-context phụ thuộc spring-beans, còn spring-beans phụ thuộc spring-core.

Một phần đồ thị phụ thuộc quan trọng của Spring Framework 6.x có thể mô tả như sau:

~~~text
Application
├── spring-jms
│   ├── spring-messaging
│   ├── spring-tx
│   └── spring-beans / spring-core
│
├── spring-websocket
│   ├── spring-context
│   ├── spring-web
│   └── spring-messaging (optional; needed for STOMP)
│
└── spring-messaging
    ├── spring-beans
    └── spring-core

spring-context
└── spring-beans
    └── spring-core
~~~

Đây là sơ đồ các cạnh chính có ý nghĩa với ba module, không phải bản liệt kê đầy đủ mọi dependency của từng phiên bản. Một số dependency là optional hoặc chỉ cần khi bật một capability cụ thể. Hãy kiểm tra POM và Gradle module metadata của đúng phiên bản khi cần biết classpath chính xác.

Có ba điểm cần hiểu:

1. **spring-jms phụ thuộc spring-messaging.** JmsMessagingTemplate dùng abstraction messaging của Spring. Vì vậy khi thêm spring-jms, spring-messaging thường xuất hiện trong dependency graph dưới dạng transitive dependency.
2. **spring-websocket có thể dùng spring-messaging.** Phần STOMP messaging dựa trên spring-messaging. Dependency này có tính optional trong module để ứng dụng dùng raw WebSocket không nhất thiết phải kéo toàn bộ messaging abstraction.
3. **spring-messaging không phụ thuộc vào JMS hoặc WebSocket.** Nó là lớp abstraction có thể được dùng độc lập hoặc được các module tích hợp khác sử dụng.

Nếu code của ứng dụng trực tiếp import class thuộc một module, nên khai báo dependency trực tiếp cho module đó. Không nên dựa vào việc một thư viện khác vô tình kéo module cần thiết vào classpath, vì dependency graph có thể thay đổi khi nâng cấp.

## 3. Dependency ngoài Spring cần cho từng trường hợp

### 3.1. Dùng spring-messaging độc lập

Nếu chỉ dùng Message, MessageChannel, MessageHandler, MessageBuilder hoặc GenericMessagingTemplate để tổ chức xử lý message trong ứng dụng, dependency chính là spring-messaging cùng các dependency nền tảng do nó khai báo.

Không cần cài JMS provider, broker hay WebSocket server cho trường hợp này.

Ví dụ:

~~~groovy
dependencies {
    implementation("org.springframework:spring-messaging")
}
~~~

Đoạn này giả định phiên bản được quản lý bởi BOM hoặc dependency management ở cấp dự án.

### 3.2. Dùng spring-jms

Một ứng dụng JMS cần ít nhất:

- spring-jms để dùng JmsTemplate, listener container và các integration API.
- Jakarta Messaging API với package jakarta.jms.
- JMS provider client tương thích để tạo ConnectionFactory.
- Broker hoặc dịch vụ JMS mà provider client có thể kết nối đến.
- spring-tx nếu ứng dụng cần transaction abstraction; spring-jms đã khai báo phụ thuộc Spring transaction module trong dependency graph thông thường.

Các provider có thể được phân phối thành nhiều artifact. Ví dụ, một client library dùng để kết nối broker từ xa khác với server library dùng để nhúng broker vào cùng JVM. Không thêm server artifact vào production application chỉ để giải quyết lỗi thiếu ConnectionFactory.

Một JMS ConnectionFactory chứa thông tin và khả năng tạo connection đến provider. Nó có thể được tạo trực tiếp bằng code, được cấu hình thành Spring bean hoặc được cung cấp từ JNDI của application server.

### 3.3. Dùng raw WebSocket

Một ứng dụng Servlet dùng raw WebSocket thường cần:

- spring-websocket.
- spring-web và spring-context theo dependency graph của Spring.
- Servlet container có triển khai WebSocket API tương thích.
- Các API Jakarta Servlet/WebSocket mà container hoặc build environment cung cấp theo cấu hình triển khai.

Ứng dụng còn cần endpoint handler và cấu hình handshake. Nếu chạy embedded server, dependency starter của Spring Boot thường giúp thiết lập runtime. Nếu triển khai WAR vào standalone server, phải kiểm tra WebSocket support của container đích.

### 3.4. Dùng STOMP trên WebSocket

Để sử dụng @EnableWebSocketMessageBroker, @MessageMapping, SimpMessagingTemplate và broker messaging, cần cả:

- spring-websocket.
- spring-messaging.
- Servlet/WebSocket runtime tương thích.

STOMP là sub-protocol trên WebSocket. Spring có thể dùng simple broker nội bộ cho subscription và broadcast, hoặc cấu hình broker relay đến một STOMP broker bên ngoài.

Simple broker không cần cài broker ngoài. Broker relay cần một broker có hỗ trợ STOMP và cấu hình kết nối riêng. Một JMS provider không mặc định hỗ trợ STOMP; cần xác minh protocol support của sản phẩm và bật plugin/module tương ứng nếu muốn dùng chung broker.

SockJS cũng cần client JavaScript tương ứng ở phía trình duyệt khi ứng dụng dùng SockJS fallback. Đây là dependency frontend, không phải dependency Java thay thế cho spring-websocket.

## 4. Chọn dependency theo use case

| Use case | Spring artifact | Dependency hoặc hạ tầng bổ sung |
|---|---|---|
| Tạo Message và channel nội bộ | spring-messaging | Spring core dependencies |
| Gửi/nhận JMS bằng JmsTemplate | spring-jms | Jakarta JMS API, provider client, ConnectionFactory |
| Nhận JMS bất đồng bộ bằng @JmsListener | spring-jms | Provider, listener container factory, broker |
| Raw WebSocket trên Servlet stack | spring-websocket | Servlet container và WebSocket runtime |
| STOMP qua WebSocket | spring-websocket + spring-messaging | WebSocket runtime; simple broker hoặc STOMP broker relay |
| JMS nhận sự kiện rồi phát tới WebSocket client | spring-jms + spring-websocket + spring-messaging | JMS provider và WebSocket runtime; thêm STOMP broker nếu dùng relay |
| Kafka | Spring for Apache Kafka | Kafka client và Kafka broker |
| RabbitMQ qua AMQP | Spring AMQP | AMQP client và RabbitMQ broker |

Không dùng spring-jms chỉ vì tên bài toán có chữ message. Kafka, AMQP, MQTT và STOMP là những protocol hoặc integration khác nhau. Hãy dùng module chuyên biệt cho protocol cần kết nối.

## 5. Cấu hình dependency với Gradle

### 5.1. Ứng dụng dùng Spring Framework trực tiếp

Nếu dự án không dùng Spring Boot dependency management, có thể import Spring Framework BOM để đồng bộ version:

~~~groovy
ext {
    springFrameworkVersion = "6.1.21"
}

dependencies {
    implementation(platform(
        "org.springframework:spring-framework-bom:${springFrameworkVersion}"
    ))

    implementation("org.springframework:spring-messaging")
    implementation("org.springframework:spring-jms")
    implementation("org.springframework:spring-websocket")
}
~~~

Ví dụ trên cố định phiên bản BOM để minh họa. Trong dự án thực tế, chọn phiên bản phù hợp với Java, Jakarta EE baseline và các thư viện liên quan. Không đặt ba phiên bản khác nhau cho ba artifact Spring Framework.

Chỉ khai báo module thực sự dùng. Ví dụ:

- Ứng dụng chỉ tạo Message nội bộ: giữ spring-messaging.
- Ứng dụng chỉ nhận JMS: thêm spring-jms và provider client.
- Ứng dụng chỉ dùng raw WebSocket: thêm spring-websocket và runtime cần thiết.
- Ứng dụng dùng STOMP: khai báo cả spring-websocket và spring-messaging để thể hiện rõ API mà code đang sử dụng.

### 5.2. Ứng dụng dùng Spring Boot

Với Spring Boot, nên để Spring Boot BOM quản lý phiên bản Spring Framework. Starter gom các dependency và cấu hình tự động phù hợp cho use case.

Ví dụ một ứng dụng Servlet sử dụng WebSocket và JMS qua ActiveMQ Artemis:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-websocket")
    implementation("org.springframework.boot:spring-boot-starter-artemis")
}
~~~

Nếu dùng ActiveMQ Classic, starter tương ứng là spring-boot-starter-activemq. Các starter JMS cung cấp dependency provider cần thiết và Spring infrastructure để tích hợp JMS. Hãy chọn đúng provider mà môi trường triển khai đang sử dụng.

Với STOMP, starter WebSocket cung cấp hạ tầng WebSocket cho ứng dụng MVC; phần messaging abstraction được sử dụng trong luồng STOMP. Nếu code trực tiếp dùng API spring-messaging, có thể khai báo spring-messaging trực tiếp để thể hiện dependency của source code.

Không tự thêm một version Spring Framework khác vào từng dependency khi Spring Boot đã quản lý BOM. Nếu cần override, phải hiểu tác động đến toàn bộ Spring Framework module và tương thích của Spring Boot version đang dùng.

### 5.3. Ví dụ Maven thuần

Import BOM trong dependencyManagement:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-framework-bom</artifactId>
            <version>${spring-framework.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Sau đó khai báo các module:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-messaging</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-jms</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-websocket</artifactId>
    </dependency>
</dependencies>
~~~

Trong ví dụ này, property spring-framework.version phải được định nghĩa ở phần properties hoặc profile của dự án. Nếu dùng Spring Boot parent hoặc BOM, tuân theo cơ chế quản lý phiên bản của Boot thay vì import thêm một BOM độc lập có thể gây xung đột.

## 6. Ví dụ cấu hình Spring Boot cho JMS và WebSocket

### 6.1. JMS với ActiveMQ Artemis

Với starter Artemis, Spring Boot có thể tự cấu hình ConnectionFactory và các bean JMS khi provider dependency có mặt trên classpath.

Ví dụ cấu hình kết nối broker từ xa:

~~~yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: ${ARTEMIS_USER}
    password: ${ARTEMIS_PASSWORD}
~~~

Giá trị trên chỉ là cấu hình minh họa cho môi trường local. Production cần dùng secret manager hoặc biến môi trường được quản lý an toàn; không commit credential vào source control.

Khi JMS infrastructure đã được cấu hình, ứng dụng có thể inject JmsTemplate để gửi message hoặc dùng @JmsListener để nhận message. Spring Boot thường tự cấu hình listener container factory mặc định và phát hiện listener annotation khi JMS infrastructure hiện diện.

### 6.2. WebSocket với STOMP

Một cấu hình STOMP điển hình:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Cấu hình này dùng simple broker nội bộ. Khi cần broker ngoài, thay cách enable simple broker bằng enableStompBrokerRelay và cung cấp thông tin kết nối, xác thực, heartbeat cùng các giới hạn vận hành.

### 6.3. Một luồng phối hợp JMS → WebSocket

Ví dụ service nhận event từ JMS rồi phát cho các WebSocket subscriber:

~~~java
@Component
public class OrderEventBridge {

    private final SimpMessagingTemplate messagingTemplate;

    public OrderEventBridge(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    @JmsListener(destination = "orders.events")
    public void onOrderEvent(OrderEvent event) {
        messagingTemplate.convertAndSend("/topic/orders", event);
    }
}
~~~

Trong luồng này, hai integration module vẫn hoạt động theo hai giao thức riêng:

1. JMS provider chuyển event đến listener container.
2. Listener nhận payload Java qua spring-jms.
3. SimpMessagingTemplate gửi message vào broker channel của Spring.
4. STOMP broker định tuyến message đến subscription phù hợp.
5. WebSocket transport chuyển frame đến trình duyệt.

Bridge này do ứng dụng tạo. Spring không tự ánh xạ mọi JMS queue sang STOMP destination. Cũng không có transaction nguyên tử bao trùm cả JMS acknowledgement và việc gửi frame tới mọi WebSocket client. Nếu dữ liệu có ý nghĩa nghiệp vụ, nên lưu trạng thái bền vững và để client đọc lại khi reconnect.

## 7. Jakarta namespace và tương thích phiên bản

Spring Framework 6.x dùng Jakarta EE 9+ namespace. Điều này ảnh hưởng trực tiếp đến dependency JMS và WebSocket.

Ví dụ:

| API cũ | API dùng trong Spring Framework 6.x |
|---|---|
| javax.jms.ConnectionFactory | jakarta.jms.ConnectionFactory |
| javax.servlet.Servlet | jakarta.servlet.Servlet |
| javax.websocket.Session | jakarta.websocket.Session |

Không thể chỉ đổi import trong code nếu provider client hoặc application server vẫn cung cấp API javax.* cũ. Các thành phần trong cùng ứng dụng phải tương thích với Jakarta namespace mà Spring Framework version yêu cầu.

Các nguyên tắc khi nâng cấp:

- Kiểm tra Java baseline của Spring Framework version.
- Kiểm tra Jakarta Messaging API và provider client.
- Kiểm tra Servlet container và WebSocket implementation.
- Kiểm tra phiên bản Spring Boot tương ứng với Spring Framework.
- Kiểm tra dependency graph để tránh cùng lúc có API javax và jakarta cho một protocol.
- Đọc upgrade guide của Spring khi thay đổi major/minor version.

Spring Framework 6.x yêu cầu Java 17 trở lên và chuyển sang Jakarta namespace. Một provider cũ chỉ triển khai javax.jms có thể gây lỗi compile hoặc runtime dù spring-jms đã nằm trong classpath.

## 8. Kiểm tra dependency graph khi gặp lỗi

Khi ứng dụng không tìm thấy class, lỗi NoClassDefFoundError, ClassNotFoundException, NoSuchMethodError hoặc lỗi khởi tạo ConnectionFactory, hãy kiểm tra dependency graph trước khi thêm thư viện ngẫu nhiên.

### 8.1. Gradle

Xem toàn bộ runtime dependency:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Tìm dependency cụ thể và lý do chọn version:

~~~bash
./gradlew dependencyInsight --dependency spring-messaging --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-jms --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-websocket --configuration runtimeClasspath
~~~

Các lệnh này giúp phát hiện:
- module không được đưa vào classpath;
- nhiều version Spring Framework cùng xuất hiện;
- dependency bị exclude;
- provider client không được khai báo;
- version được chọn do conflict resolution hoặc constraint.

### 8.2. Maven

Xem dependency tree:

~~~bash
mvn dependency:tree -Dincludes=org.springframework
~~~

Có thể lọc theo groupId hoặc artifactId của provider để tìm version và scope đang được sử dụng.

### 8.3. Phân biệt lỗi thiếu class với lỗi kết nối

| Triệu chứng | Nhóm nguyên nhân cần kiểm tra |
|---|---|
| ClassNotFoundException cho jakarta.jms.* | Thiếu Jakarta Messaging API hoặc provider client tương thích |
| ClassNotFoundException cho org.springframework.messaging.* | Thiếu spring-messaging hoặc dependency bị exclude |
| Không tạo được ConnectionFactory | Provider dependency, cấu hình URL, credential hoặc class factory không phù hợp |
| Connection refused / timeout | Broker chưa chạy, host/port sai, firewall hoặc TLS |
| Không upgrade được WebSocket | Container, reverse proxy, endpoint hoặc handshake |
| STOMP CONNECT thành công nhưng SEND không đến handler | Destination prefix, @MessageMapping, channel hoặc broker configuration |
| NoSuchMethodError trong Spring | Các Spring module không đồng bộ version hoặc thư viện tương thích sai |

Lỗi classpath và lỗi network cần xử lý theo hai hướng khác nhau. Thêm một broker dependency không sửa được URL sai; sửa URL cũng không giải quyết được Jakarta namespace mismatch.

## 9. Lỗi dependency và cách phòng tránh

### 9.1. Trộn version các Spring module

Ví dụ spring-core ở một version nhưng spring-messaging hoặc spring-websocket ở version khác có thể dẫn đến NoSuchMethodError hoặc lỗi khởi tạo bean.

Cách phòng tránh là dùng Spring Framework BOM hoặc Spring Boot BOM và kiểm tra dependencyInsight khi có version conflict.

### 9.2. Dựa vào transitive dependency

Một module có thể kéo spring-messaging vào classpath. Tuy nhiên nếu source code trực tiếp dùng Message, GenericMessagingTemplate hoặc SimpMessagingTemplate thì nên khai báo spring-messaging trực tiếp.

Điều này làm rõ dependency thực sự của module và tránh code vô tình phụ thuộc vào implementation detail của một starter hoặc integration module khác.

### 9.3. Thiếu provider hoặc nhầm provider

spring-jms cung cấp lớp tích hợp, còn provider client tạo ConnectionFactory và giao tiếp với broker. Chọn đúng client artifact và API namespace theo provider. Không trộn các thư viện client của nhiều broker chỉ để thử xem class nào khởi tạo được.

### 9.4. Dùng sai module cho protocol

- RabbitMQ AMQP thường dùng Spring AMQP.
- Kafka dùng Spring for Apache Kafka.
- JMS dùng spring-jms.
- STOMP over WebSocket dùng spring-websocket và spring-messaging.

Các protocol có thể cùng xuất hiện trong một hệ thống nhưng không có nghĩa chúng dùng chung một dependency hoặc một loại destination.

### 9.5. Quên hạ tầng khi triển khai

Một ứng dụng chạy được trong IDE chưa chắc đã có đủ hạ tầng khi đóng gói:

- JMS broker có thể chưa được provision hoặc không truy cập được từ runtime.
- Servlet container có thể không bật WebSocket support.
- Reverse proxy có thể không chuyển tiếp HTTP Upgrade.
- STOMP broker relay có thể không mở được TCP connection đến broker.
- Container image có thể thiếu provider client do dependency scope sai.

Hãy kiểm tra runtimeClasspath, cấu hình triển khai và connectivity trong môi trường gần production.

## 10. Chiến lược kiểm thử theo module

### 10.1. spring-messaging

Có thể kiểm thử MessageBuilder, header, channel và handler mà không cần broker bên ngoài. Đây là các unit test nhanh để xác nhận contract và logic định tuyến nội bộ.

### 10.2. spring-jms

Unit test có thể mock abstraction hoặc service gọi JmsTemplate. Tuy nhiên, các hành vi như acknowledgement, redelivery, selector và transaction nên được kiểm thử với JMS provider thực tế hoặc broker test phù hợp.

Kiểm tra cả tình huống listener xử lý thành công, listener ném exception, message bị redeliver, provider mất kết nối và transaction rollback.

### 10.3. spring-websocket

Kiểm thử handler và message mapping riêng biệt. Với STOMP, nên có integration test xác minh handshake, CONNECT, SUBSCRIBE, SEND, message routing và session đóng.

Kiểm tra cả reconnect, authorization theo destination, payload không hợp lệ và timeout. Nếu triển khai qua reverse proxy, cần một kiểm thử ở đúng topology triển khai vì unit test không xác nhận được proxy có chuyển tiếp WebSocket Upgrade hay không.

### 10.4. Kiểm thử bridge JMS và WebSocket

Kiểm thử luồng tích hợp cần xác minh:

1. JMS event được nhận.
2. Payload được chuyển đổi đúng.
3. Message được phát đến STOMP destination.
4. Subscriber nhận được message.
5. Lỗi ở một bước được ghi nhận và xử lý theo chính sách.
6. Client offline có thể đọc lại trạng thái nghiệp vụ nếu yêu cầu dữ liệu không được phép mất.

Không nên coi việc method listener được gọi là bằng chứng toàn bộ bridge đã giao message thành công đến client.

## 11. Quy trình chọn và thêm dependency

Khi bắt đầu một tính năng messaging, hãy đi theo thứ tự sau:

1. Xác định transport/protocol: nội bộ, JMS, WebSocket/STOMP, Kafka hay AMQP.
2. Xác định API Spring mà source code sẽ import.
3. Chọn Spring artifact tương ứng.
4. Xác định provider hoặc runtime ngoài Spring cần có.
5. Dùng BOM để đồng bộ version.
6. Kiểm tra dependency graph và runtime classpath.
7. Cấu hình connection, destination, transaction, security và timeout.
8. Viết unit test cho contract và integration test cho transport.
9. Xác minh hành vi trong môi trường triển khai thực tế.

Cách làm này giúp dependency phản ánh đúng kiến trúc. Một ứng dụng có thể chỉ cần một trong ba module; chỉ khi có nhiều loại giao tiếp thì mới cần kết hợp chúng.

## 12. Tài liệu tham khảo

- [Spring Framework Artifacts](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-Artifacts) — danh sách artifact, dependency management và BOM.
- [Spring Framework Reference — Messaging](https://docs.spring.io/spring-framework/reference/integration.html) — abstraction và API messaging.
- [Spring Framework Reference — JMS](https://docs.spring.io/spring-framework/reference/integration/jms.html) — JmsTemplate, listener container và transaction.
- [Spring Framework Reference — WebSocket](https://docs.spring.io/spring-framework/reference/web/websocket.html) — raw WebSocket và SockJS.
- [Spring Framework Reference — STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp.html) — message flow, simple broker và broker relay.
- [Spring Boot Reference — JMS](https://docs.spring.io/spring-boot/reference/messaging/jms.html) — ActiveMQ, Artemis và ConnectionFactory auto-configuration.
- [Spring Boot Reference — WebSockets](https://docs.spring.io/spring-boot/reference/messaging/websockets.html) — WebSocket starter và runtime.
- [Spring Framework 6.1 Javadoc — org.springframework.messaging](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/package-summary.html)
- [Spring Framework 6.1 Javadoc — org.springframework.jms](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jms/package-summary.html)

Khi tra cứu dependency, luôn đối chiếu đúng phiên bản Spring Framework và Spring Boot của dự án. Tên artifact có thể giữ nguyên qua nhiều phiên bản nhưng dependency graph, baseline Jakarta và auto-configuration có thể thay đổi.