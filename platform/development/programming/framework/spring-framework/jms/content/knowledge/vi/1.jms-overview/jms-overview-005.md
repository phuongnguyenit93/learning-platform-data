# Quan hệ giữa JMS, Jakarta Messaging và Spring JMS

> **Mục tiêu:** Phân biệt chính xác chuẩn messaging, API Java, hệ thống môi giới thông điệp và lớp tích hợp Spring; hiểu vì sao cùng một ứng dụng có thể dùng cả Jakarta Messaging lẫn Spring JMS; triển khai được luồng gửi–nhận đơn giản trên Java 17+ và tránh nhầm lẫn khi chuyển từ `javax.jms` sang `jakarta.jms`.

## 1. Ba tên gọi, ba vai trò khác nhau

**JMS (Java Message Service)** là tên lịch sử của chuẩn API nhắn tin dành cho Java. Nó mô tả cách ứng dụng tạo, gửi, nhận, xác nhận và giao dịch với thông điệp qua một hệ thống messaging. Trong nhiều tài liệu và tên lớp, “JMS” vẫn được dùng để gọi chung công nghệ này.

**Jakarta Messaging** là tên chính thức hiện nay của đặc tả từng được gọi là JMS. Bản Jakarta Messaging 3.0 chuyển namespace API từ `javax.jms` sang `jakarta.jms`; Jakarta Messaging 3.1 tiếp tục dùng `jakarta.jms`. Đặc tả định nghĩa giao diện và các quy tắc hành vi, nhưng **không tự chạy broker** hay quyết định giao thức mạng cụ thể mà broker dùng.

**Spring JMS** là phần tích hợp của Spring Framework xây trên API Jakarta Messaging trong các thế hệ Spring hiện đại. Nó giúp ứng dụng dễ gửi tin, xử lý nhận tin và quản lý tài nguyên, lỗi, chuyển đổi payload, listener container, transaction. Nó **không thay thế** Jakarta Messaging và **không phải** một message broker.

| Thành phần | Trả lời câu hỏi gì? | Ví dụ |
| --- | --- | --- |
| JMS / Jakarta Messaging | “Ứng dụng Java giao tiếp với hệ thống nhắn tin bằng hợp đồng API nào?” | `ConnectionFactory`, `Destination`, `Queue`, `Topic`, `Message`, `JMSContext` |
| JMS provider / message broker | “Ai thực sự nhận, lưu, định tuyến và phân phối message?” | Apache ActiveMQ Artemis hoặc nhà cung cấp hỗ trợ Jakarta Messaging tương thích |
| Spring JMS | “Làm sao viết mã ứng dụng Java/Spring gọn hơn trên API đó?” | `JmsTemplate`, `@JmsListener`, `DefaultMessageListenerContainer`, `MessageConverter` |
| Spring Boot JMS auto-configuration | “Ai tạo và cấu hình các bean Spring từ dependency/properties?” | `ConnectionFactory`, `JmsTemplate`, listener factory khi điều kiện phù hợp |

**Quan hệ bao hàm:** Ứng dụng Spring có thể dùng Spring JMS → Spring JMS gọi Jakarta Messaging API → client/provider nói chuyện với broker → broker chuyển message cho consumer. Spring Boot là lớp hỗ trợ cấu hình (tùy chọn), không phải một chuẩn messaging thứ tư.

~~~text
[Producer trong ứng dụng Spring]                 [Consumer trong ứng dụng Spring]
     Business Service                                  @JmsListener
           |                                                ^
           v                                                |
       JmsTemplate                                Listener container
           |                                                ^
           v                                                |
   Jakarta Messaging API                         Jakarta Messaging API
           |                                                ^
           +-- provider client --> [ Broker ] --> provider client --+
                                  Queue / Topic
~~~

Một broker có thể cung cấp nhiều giao thức/client API. Việc broker có hỗ trợ AMQP, STOMP hay giao thức nội bộ **không đồng nghĩa** mọi client đều dùng Jakarta Messaging; ngược lại, chuẩn Jakarta Messaging không quy định broker phải dùng một wire protocol cụ thể.

## 2. Tên và namespace thay đổi qua các thế hệ

| Hệ sinh thái | Namespace Java thường gặp | Ý nghĩa thực tế |
| --- | --- | --- |
| Java EE / JMS 1.x–2.0 | `javax.jms.*` | Mã và thư viện Java EE cũ |
| Jakarta EE 8 / Jakarta Messaging 2.0 | `javax.jms.*` | Đặc tả mang tên Jakarta nhưng API vẫn thuộc namespace cũ |
| Jakarta Messaging 3.0+ (ví dụ 3.1) | `jakarta.jms.*` | Namespace mới dùng trong stack Spring Framework 6+ |
| Spring Framework 5.x | Tích hợp với API `javax.jms` | Cần client/provider tương thích thế hệ `javax` |
| Spring Framework 6.x/7.x | Tích hợp với API `jakarta.jms` | Cần dependency và provider client tương thích thế hệ `jakarta` |

Những tên như `JmsTemplate`, `JmsListener`, `JMSContext` vẫn chứa “JMS”; việc đổi tên đặc tả **không yêu cầu** đổi tên mọi class có chữ JMS. Phân biệt **tên thương hiệu/đặc tả** với **tên package thực tế**.

Hai kiểu import sau mô tả những thế hệ khác nhau:

~~~java
// Ứng dụng cũ, API javax.jms:
import javax.jms.ConnectionFactory;
import javax.jms.Message;

// Ứng dụng Spring Framework 6+ / Jakarta Messaging 3.x:
import jakarta.jms.ConnectionFactory;
import jakarta.jms.Message;
~~~

Đây là **minh họa so sánh import**, không phải một file Java độc lập: không đặt cả hai cặp import có class trùng tên trong cùng một source file. Khi nâng cấp, phải kiểm tra đồng thời imports, JMS API dependency, client/provider library, cấu hình broker và Spring version. Chỉ sửa `javax.jms` thành `jakarta.jms` trong code mà giữ driver cũ có thể gây lỗi biên dịch hoặc thiếu class lúc chạy.

## 3. Jakarta Messaging chuẩn hóa những gì?

### 3.1 Các đối tượng cốt lõi

- **`ConnectionFactory`:** điểm xuất phát để lấy connection/session hoặc `JMSContext`, do provider cung cấp hoặc được DI/JNDI cấp.
- **`Destination`:** đích logic; hai loại điển hình là `Queue` và `Topic`. Tên destination và cách cấp phát/quản trị đích thực tế thường tùy broker.
- **`Message`:** envelope gồm header chuẩn, properties tùy biến và body. Ví dụ `TextMessage`, `BytesMessage`; ưu tiên định dạng payload có schema và tương thích nhiều phiên bản.
- **`Connection` + `Session`:** API cổ điển cho kết nối, transaction, producer/consumer và quản lý việc xác nhận message.
- **`JMSContext` + `JMSProducer`/`JMSConsumer`:** API rút gọn xuất hiện từ JMS 2.0, giảm thao tác lifecycle ở mã Java trực tiếp.
- **Headers:** `JMSMessageID` giúp định danh thông điệp, `JMSCorrelationID` liên kết request/reply, `JMSReplyTo` chỉ nơi nhận phản hồi, bên cạnh thông tin thời gian/độ ưu tiên/đích.

`JMSContext` là một API của Jakarta Messaging; nó **không phải** API độc quyền của Spring. Ngược lại, `JmsTemplate` là một lớp của Spring, hoạt động nhờ `ConnectionFactory` và API messaging bên dưới.

### 3.2 Queue và Topic

| Khía cạnh | Queue (point-to-point) | Topic (publish/subscribe) |
| --- | --- | --- |
| Ý định | Phân việc cho một trong các consumer | Phát sự kiện đến nhiều subscription |
| Nhận một message | Mỗi lần phân phối vào queue thuộc về một consumer, dù có nhiều consumer cạnh tranh | Mỗi subscription đủ điều kiện có bản sao message riêng |
| Kết nối muộn | Message còn trong queue nếu chưa được lấy/đã hết hạn theo cấu hình | Non-durable subscriber có thể bỏ lỡ message lúc offline; durable subscription lưu theo quy tắc cấu hình |
| Tình huống | Xử lý đơn hàng, tác vụ nền, phân phối công việc | Nhiều dịch vụ cùng quan tâm đến một sự kiện |

“Đến **một** consumer trên queue” không có nghĩa là luôn xử lý **đúng một lần**: nếu chưa commit/ack và message được giao lại, consumer khác hoặc cùng consumer có thể xử lý lần nữa. Với topic, một message được phát đến các **subscription**, không nhất thiết mọi process đang tồn tại đều nhận khi chưa đăng ký/không đủ điều kiện.

**Persistent delivery** (độ bền khi gửi/lưu message) và **durable topic subscription** (giữ thông điệp cho subscriber tạm offline) là hai khái niệm khác nhau. Broker, expiration, quota và chính sách lỗi vẫn quyết định khả năng lưu giữ thực tế.

### 3.3 Đồng bộ, bất đồng bộ, transaction

API có thể `receive(...)` chặn thread cho đến khi có dữ liệu/hết timeout, hoặc xử lý callback/listener khi message đến. “Messaging bất đồng bộ” nói đến sự tách rời producer/consumer, **không** có nghĩa mọi lệnh `send` đều trả về ngay không cần broker xác nhận.

Các chế độ xác nhận và transaction xác định thời điểm nhận được coi là hoàn thành. Với một `Session` giao dịch, `commit` xác nhận việc nhận/gửi trong transaction JMS; `rollback` có thể dẫn đến redelivery theo quy tắc broker. Trong xử lý thực tế cần xét cả crash, retry, dead-letter và tính idempotent.

## 4. Spring JMS bổ sung điều gì so với gọi API trực tiếp?

| Nhu cầu | API Jakarta Messaging | Cách thường dùng với Spring JMS |
| --- | --- | --- |
| Tạo/đóng connection, session, producer | Ứng dụng quản lý qua `ConnectionFactory`, `JMSContext` / `Session` | `JmsTemplate` quản lý phần lớn boilerplate |
| Gửi chuỗi hoặc đối tượng | Tạo `Message` và gọi producer | `convertAndSend(...)` hoặc `send(...)` |
| Nhận đồng bộ | `JMSConsumer.receive(...)` | `JmsTemplate.receive(...)` hoặc `receiveAndConvert(...)` |
| Nhận bằng callback | `MessageListener` và lifecycle của consumer | `@JmsListener` + listener container |
| Chuyển đổi object ↔ message | Ứng dụng tự encode/decode | `MessageConverter`, ví dụ JSON converter |
| Chuẩn hóa exception | `JMSException` checked / `JMSRuntimeException` | Spring chuyển lỗi JMS thành hệ `JmsException` unchecked |
| Quản lý nhận tin / concurrency | Tự tổ chức connection, session và thread | `DefaultJmsListenerContainerFactory` và container |
| Transaction | Transaction của `Session` hoặc JTA theo môi trường | Transacted listener session, `JmsTransactionManager`, JTA khi cần |

**`JmsTemplate`** ở package `org.springframework.jms.core` giống ý tưởng `JdbcTemplate`: nhận `ConnectionFactory`, mở/sử dụng/giải phóng tài nguyên, cung cấp callback khi cần tinh chỉnh, giúp mã gửi tin tập trung vào dữ liệu.

**`@JmsListener`** ở `org.springframework.jms.annotation` đánh dấu phương thức nhận tin. Spring cần hạ tầng listener để đăng ký phương thức đó; `DefaultJmsListenerContainerFactory` cấu hình container, còn `DefaultMessageListenerContainer` là container nhận và gọi listener trong runtime. `@EnableJms` bật cơ chế annotation trong cấu hình Spring thủ công; Spring Boot có thể tự cấu hình hạ tầng này khi đủ dependency.

**`MessageConverter`** thuộc `org.springframework.jms.support.converter`. Chuỗi `String` có thể thành `TextMessage`; với POJO, nên cấu hình converter JSON rõ ràng và thống nhất cả bên gửi/nhận. Spring không mặc nhiên biết schema hoặc đảm bảo tương thích dữ liệu giữa các service.

**Spring Boot** có thể cấu hình `ConnectionFactory`, `JmsTemplate` và listener factory khi thấy starter/provider phù hợp. Trong ứng dụng Spring Framework thuần túy, bạn phải cung cấp các bean tương ứng; chỉ thêm Spring JMS mà không có JMS provider/ConnectionFactory thì chưa gửi nhận được message nào.

## 5. Ví dụ Java 17+: gửi và nhận một message bằng Spring JMS

Đây là bài lab **Spring Boot + ActiveMQ Artemis embedded** để học quan hệ giữa ba lớp. Embedded broker chỉ phù hợp minh họa/phát triển; khi triển khai nhiều tiến trình hoặc production, kết nối broker được quản lý độc lập.

### 5.1 Tạo project và dependency

1. Dùng **Spring Initializr** (https://start.spring.io/), chọn Maven, Java, Java 17+, group `com.example`, artifact `jmsdemo`, và dependency **Spring for Apache ActiveMQ Artemis**. Dùng phiên bản Spring Boot ổn định tương thích Java của bạn.
2. Starter tạo dependency `org.springframework.boot:spring-boot-starter-artemis`. Để chạy broker nhúng trong bài lab, thêm dependency bên dưới vào `pom.xml` (đặt trong thẻ `<dependencies>` có sẵn):

~~~xml
<dependency>
    <groupId>org.apache.activemq</groupId>
    <artifactId>artemis-jakarta-server</artifactId>
</dependency>
~~~

Không đặt version cho dependency này nếu dự án dùng BOM/parent do Spring Initializr cung cấp: BOM sẽ chọn phiên bản Artemis tương thích. Với ứng dụng sản xuất dùng broker bên ngoài, không cần phụ thuộc server embedded ở trên.

### 5.2 Cấu hình broker nhúng

Nội dung `src/main/resources/application.properties`:

~~~properties
spring.artemis.mode=embedded
spring.artemis.embedded.queues=orders.in
spring.jms.pub-sub-domain=false
~~~

`orders.in` là tên queue của ví dụ. `spring.jms.pub-sub-domain=false` thể hiện rõ ngữ cảnh Queue (đây cũng là hướng cấu hình mặc định phổ biến); nếu đổi sang Topic phải cấu hình đúng cả producer, listener và subscription.

### 5.3 Một file Java đầy đủ

Thay lớp application được tạo bởi Initializr bằng file `src/main/java/com/example/jmsdemo/JmsDemoApplication.java`:

~~~java
package com.example.jmsdemo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableJms
public class JmsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmsDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner publishOnStartup(JmsTemplate jmsTemplate) {
        return args -> {
            jmsTemplate.convertAndSend("orders.in", "ORDER-42");
            System.out.println("Published order: ORDER-42");
        };
    }

    @Component
    public static class OrderListener {
        @JmsListener(destination = "orders.in")
        public void onOrder(String orderId) {
            System.out.println("Received order: " + orderId);
        }
    }
}
~~~

Từ thư mục gốc project (có Maven wrapper), chạy:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows PowerShell dùng `.\mvnw.cmd spring-boot:run`. Khi thành công, bên cạnh log Spring/Artemis, bạn sẽ thấy **hai dòng**:

~~~text
Published order: ORDER-42
Received order: ORDER-42
~~~

Hai dòng có thể xuất hiện **theo thứ tự ngược lại** do listener xử lý ở thread khác; không viết test phụ thuộc thứ tự log. Cần Maven/JDK, dependency tải được và cổng/tài nguyên broker nhúng khả dụng.

**Dòng dữ liệu thực sự:**

1. `ApplicationRunner` gọi `JmsTemplate.convertAndSend`. Template dùng converter phù hợp để đưa chuỗi thành message.
2. `JmsTemplate` sử dụng `jakarta.jms.ConnectionFactory` được Boot cấu hình cho Artemis; provider client đưa message đến queue `orders.in`.
3. Broker giữ và phân phối message tới JMS consumer của listener container.
4. Container gọi `OrderListener.onOrder(String)` với payload đã được chuyển đổi. Trong ví dụ này nghiệp vụ chỉ in log.

Không cần tự `new Connection`, `Session`, `MessageProducer` ở lớp nghiệp vụ; Spring JMS giúp quản lý phần đó. Tuy nhiên message **vẫn đi qua broker và API Jakarta Messaging** như sơ đồ phần đầu.

### 5.4 Nếu dùng broker bên ngoài

Bỏ dependency `artemis-jakarta-server` của embedded lab, cấu hình kết nối provider tương ứng. Với Artemis chạy ngoài ứng dụng, một cấu hình minh họa là:

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=demo
spring.artemis.password=local-demo-password
~~~

Giá trị user/password ở đây **chỉ minh họa**; phải khớp tài khoản đã tạo trong broker thực tế và dùng secret/config phù hợp môi trường. Kết nối và khả năng tự tạo queue phụ thuộc cấu hình Artemis. Không giả định một port, credential hoặc tên queue sẽ hoạt động trên mọi nhà cung cấp JMS.

## 6. So sánh với Jakarta Messaging API thuần

Đoạn sau cho thấy **cùng ý tưởng** mà không dùng `JmsTemplate`. Đây là hai phương thức minh họa đặt trong một class có import `jakarta.jms.*`, và `cf` phải là `ConnectionFactory` đã cấu hình từ provider; đoạn mã **không tự tạo broker/ConnectionFactory**:

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;

public static void send(ConnectionFactory cf) {
    try (JMSContext context = cf.createContext()) {
        Queue orders = context.createQueue("orders.in");
        context.createProducer().send(orders, "ORDER-42");
    }
}

public static String receive(ConnectionFactory cf) {
    try (JMSContext context = cf.createContext()) {
        Queue orders = context.createQueue("orders.in");
        return context.createConsumer(orders)
                      .receiveBody(String.class, 5_000);
    }
}
~~~

`receiveBody` chờ tối đa 5 giây và có thể trả về `null` khi hết thời gian. Phương thức `receive` chỉ phù hợp minh họa nhận **đồng bộ**; với dịch vụ chạy lâu dài, listener container thường quản lý polling/đăng ký, recovery và concurrency tốt hơn. Mã thuần này và Spring JMS cùng dựa trên **Jakarta Messaging**, nên là hai cách dùng chung chuẩn chứ không phải hai giao thức riêng.

## 7. Phân biệt đảm bảo của chuẩn, broker và ứng dụng

### 7.1 Khi nào một message được coi là xử lý xong?

Hãy tách bốn giai đoạn: **producer gửi** → **broker chấp nhận** → **consumer nhận** → **nghiệp vụ hoàn tất và ack/commit**. Không thể coi một lần gọi `convertAndSend` thành công là bằng chứng consumer đã ghi database hay hoàn tất nghiệp vụ.

- **ACK:** cho broker biết tình trạng nhận. Các chế độ như `AUTO_ACKNOWLEDGE`, `CLIENT_ACKNOWLEDGE` hay session transaction có ngữ nghĩa khác nhau.
- **Transaction JMS cục bộ:** nhóm thao tác JMS của một session, cho phép commit/rollback; trong Spring có thể dùng listener factory `setSessionTransacted(true)` hoặc `JmsTransactionManager` khi phù hợp.
- **Redelivery:** lỗi/rollback có thể khiến message quay lại; chính sách số lần thử, delay và dead-letter queue thường do broker cấu hình.
- **Idempotency:** ứng dụng phải xử lý an toàn khi cùng business event/ID đến lại. Không dùng riêng `JMSMessageID` như một lời hứa rằng không có duplicate trong toàn bộ chuỗi xử lý.

Với listener có yêu cầu xử lý đáng tin cậy, tài liệu Spring cảnh báo `AUTO_ACKNOWLEDGE` mặc định của một số container không bảo đảm redelivery như mong đợi khi listener lỗi; cân nhắc **transacted session**. Ví dụ cấu hình Spring Framework thủ công:

~~~java
@Bean
DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        jakarta.jms.ConnectionFactory connectionFactory) {
    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setSessionTransacted(true);
    factory.setConcurrency("1-3");
    return factory;
}
~~~

Đây là **mảnh cấu hình** đặt trong một `@Configuration`, cần import `@Bean` và `org.springframework.jms.config.DefaultJmsListenerContainerFactory`; không phải file Java độc lập. Nếu đã dùng auto-configuration Boot, việc tự định nghĩa factory mặc định có thể thay đổi các setting mà Boot lẽ ra áp dụng; nên dùng `DefaultJmsListenerContainerFactoryConfigurer` của Boot khi muốn giữ toàn bộ thiết lập tự động rồi tinh chỉnh.

**Transaction JMS không tự động gộp cùng transaction SQL.** Ví dụ handler ghi database rồi lỗi trước khi ack có thể nhận lại message; handler ack trước khi database commit lại có rủi ro ngược. Để xử lý hai tài nguyên, thiết kế idempotent/inbox, transactional outbox hoặc XA/JTA trong trường hợp cần và đã đánh giá tradeoff. `@Transactional` cho database không tự biến broker và database thành một transaction phân tán.

### 7.2 Các yếu tố quyết định độ tin cậy

- **Delivery mode và hạn sử dụng:** persistent/non-persistent, TTL và expiration cần hiểu cùng cấu hình lưu trữ thực tế của broker.
- **Queue/topic:** cùng nội dung gửi vào queue khác topic về người nhận, fan-out và cách giữ message.
- **Listener concurrency:** tăng worker có thể tăng throughput, nhưng ảnh hưởng thứ tự và khả năng cạnh tranh tài nguyên; không tự giả định FIFO toàn cục khi nhiều consumer.
- **Retry và poison message:** giới hạn số lần thử, backoff, DLQ/quarantine và thao tác replay cần có chủ đích để tránh vòng lặp vô hạn.
- **Monitoring:** theo dõi queue depth, age/lag, tỷ lệ thất bại/redelivery, consumer throughput, DLQ, connection và tình trạng broker.
- **Security:** credential, phân quyền theo destination, TLS, hạn chế quyền publish/consume và tránh ghi payload nhạy cảm vào log.

## 8. Những điều thường nhầm lẫn

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “JMS và Jakarta Messaging là hai protocol cạnh tranh.” | Là cùng dòng đặc tả, đã đổi tên/namespace; cần phân biệt thế hệ API. |
| “Spring JMS đã thay thế JMS.” | Spring cung cấp abstraction/automation trên Jakarta Messaging, không thay thế hợp đồng API. |
| “Thêm dependency Spring JMS là có broker.” | Cần provider client, `ConnectionFactory` và broker khả dụng; Boot hỗ trợ cấu hình nếu dependency phù hợp. |
| “`@JmsListener` là cơ chế độc lập broker.” | Annotation cần listener container và provider kết nối đến đích. |
| “Queue đảm bảo mỗi business action chạy đúng một lần.” | Redelivery/duplicate vẫn có thể xảy ra; business handler nên idempotent. |
| “Topic luôn gửi được message cho mọi service kể cả khi offline.” | Tùy subscription durable/non-durable, thời điểm subscribe và retention của broker. |
| “`JMSContext` là thư viện Spring.” | Đây là API của JMS/Jakarta Messaging; `JmsTemplate` mới là API Spring. |
| “Chỉ đổi import từ `javax` sang `jakarta` là đủ nâng cấp.” | Phải đồng bộ cả framework, Jakarta API, provider client và dependencies. |
| “Chỉ cần bật `@Transactional` là JMS và DB commit đồng thời.” | Local transactions của JMS và DB không tự có atomicity chung. |
| “JMS đồng nghĩa Kafka/RabbitMQ/HTTP.” | Đây là API/semantics Java; Kafka API, AMQP và HTTP có hợp đồng, vận hành và tradeoff khác. Một broker có thể hỗ trợ nhiều cách giao tiếp. |

## 9. Khi nào nên dùng gì?

**Dùng Jakarta Messaging API trực tiếp** khi làm client Java gọn, không dùng Spring, cần truy cập tính năng API chuẩn hoặc muốn tự kiểm soát vòng đời session/consumer. Đổi lại phải tự xử lý nhiều tài nguyên và luồng nhận.

**Dùng Spring JMS** khi hệ thống đã sử dụng Spring và cần gửi/nhận message JMS, annotation listener, conversion, cấu hình concurrency, exception/transaction integration. Nó giảm mã lặp, nhưng quyết định về queue/topic, schema, nghiệp vụ idempotent và vận hành broker vẫn thuộc về thiết kế ứng dụng.

**Chọn công nghệ messaging theo hạ tầng và yêu cầu**: nếu môi trường tích hợp dùng broker hỗ trợ JMS và muốn hợp đồng API Java chuẩn, JMS/Spring JMS là lựa chọn tự nhiên. Nếu hệ thống dùng Kafka, RabbitMQ qua Spring AMQP, hoặc công nghệ khác, hãy dùng thư viện phù hợp với API/protocol đó; không nên coi Spring JMS là adapter tổng quát cho mọi message broker.

## 10. Checklist để tự kiểm tra một dự án Spring có JMS

1. **Stack tương thích:** Spring Framework 5/6/7, package `javax.jms`/`jakarta.jms`, phiên bản provider client và Java runtime có khớp?
2. **Kết nối:** Bean `ConnectionFactory` đến đúng broker, protocol, credentials, TLS và destination đã có/có quyền tạo?
3. **Ngữ nghĩa:** Producer và consumer đều đang coi destination là Queue hay Topic? Có cần durable subscription không?
4. **Payload:** Kiểu `Message` và converter có thống nhất? Có schema/versioning và giới hạn kích thước?
5. **Hoàn tất xử lý:** Ack/transaction/retry/redelivery/DLQ cấu hình ra sao? Handler có idempotent khi nhận lại?
6. **Vận hành:** Có giới hạn concurrency, đo queue backlog, báo động lỗi và runbook xử lý DLQ?

**Bài tập thực hành:** chạy ví dụ queue rồi thử (a) gửi 3 ID khác nhau; (b) thêm một listener khác cùng queue và quan sát phân chia message; (c) thử lỗi có chủ đích khi sử dụng transacted listener để quan sát redelivery của broker; (d) thiết kế chuyển sang Topic với hai subscription riêng. Mô tả rõ ràng khi nào nhận được nhiều bản sao và khi nào không — đó là cách kiểm tra bạn đã phân biệt API, Spring abstraction và broker semantics.

## Tài liệu chuẩn để tra cứu

- Jakarta Messaging 3.1 Specification: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Spring Framework — JMS: https://docs.spring.io/spring-framework/reference/integration/jms.html
- Spring Framework — Using Spring JMS: https://docs.spring.io/spring-framework/reference/integration/jms/using.html
- Spring Framework — Annotation-driven Listener Endpoints: https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html
- Spring Boot — JMS: https://docs.spring.io/spring-boot/reference/messaging/jms.html
- Spring Guide — Messaging with JMS: https://spring.io/guides/gs/messaging-jms/
