# Vai trò JMS provider, broker và ứng dụng khách

## 1. Nhìn toàn cảnh: ai làm việc gì?

JMS (Java Message Service, hiện thuộc chuẩn **Jakarta Messaging**) là bộ API cho phép ứng dụng Java gửi và nhận thông điệp mà không phải gọi trực tiếp nhau tại cùng thời điểm. JMS quy định **cách ứng dụng lập trình với hệ thống nhắn tin**; nó không quy định một phần mềm broker hay một giao thức truyền tin duy nhất. Với Spring Framework 6+ và Spring Boot 3+, API thuộc namespace `jakarta.jms.*`; nhiều tài liệu cũ dùng `javax.jms.*`.

Hãy tưởng tượng hệ thống bán hàng: `OrderService` phát sự kiện đơn hàng mới; `InventoryService` nhận sự kiện để xử lý kho. Ba vai trò chính là:

| Vai trò | Trách nhiệm cốt lõi | Ví dụ |
| --- | --- | --- |
| **JMS provider** | Cung cấp **bản triển khai** của các hợp đồng JMS: thư viện client, `ConnectionFactory`, cơ chế kết nối, gửi/nhận thông điệp và các thành phần hạ tầng liên quan. | Apache ActiveMQ Artemis, IBM MQ và các giải pháp có hỗ trợ JMS |
| **Message broker** | Là **thành phần tiếp nhận, lưu giữ (tùy cấu hình), định tuyến và phân phối** thông điệp tới queue/topic và các consumer; thường là một server hay cụm server. | Một Artemis broker đang chạy ở `tcp://localhost:61616` |
| **Ứng dụng khách (JMS client)** | Chứa nghiệp vụ, **gửi** thông điệp (producer), **nhận/xử lý** thông điệp (consumer), hoặc làm cả hai; gọi JMS API trực tiếp hoặc qua Spring. | `OrderService` gửi; `InventoryService` nhận qua `@JmsListener` |

**Phân biệt mấu chốt:** *provider* là giải pháp triển khai JMS ở cấp sản phẩm/thư viện/giao tiếp; *broker* là thành phần hạ tầng thực thi việc trung chuyển thông điệp. Chúng có quan hệ chặt chẽ nhưng **không đồng nghĩa**. Một hệ thống thường có cả thư viện JMS client của provider trong ứng dụng và một broker chạy ở nơi khác. JMS cũng không yêu cầu mọi provider phải có một broker độc lập; sản phẩm có thể hỗ trợ broker nhúng hoặc kiến trúc khác.

## 2. Hành trình của một thông điệp

~~~text
Ứng dụng A: OrderService                         Ứng dụng B: InventoryService
  nghiệp vụ tạo đơn                                    nghiệp vụ xử lý kho
         |                                                     ^
         v                                                     |
  Spring JmsTemplate                                    Spring @JmsListener
         |                                                     ^
         v                                                     |
  JMS client library  <---- provider-specific ---->  JMS client library
         |                                                     ^
         | kết nối, xác thực, gửi                               | nhận, acknowledge
         v                                                     |
  +------------------------- JMS BROKER ------------------------+
  |         Destination: queue "orders.created"                |
  |  nhận -> định tuyến -> lưu/chờ (theo chính sách) -> giao    |
  +-------------------------------------------------------------+
~~~

Luồng cơ bản, với queue `orders.created`:

1. **Producer** tạo payload (ví dụ mã đơn `order-123`), chọn destination và gọi `JmsTemplate.convertAndSend(...)` hoặc JMS API.
2. **Client library của provider** dùng `ConnectionFactory` và kết nối đã cấu hình để chuyển lời gọi gửi thành giao tiếp với hệ thống messaging.
3. **Broker** nhận thông điệp, kiểm tra quyền/chính sách, định tuyến vào queue. Việc ghi bền vững, giới hạn dung lượng, thời gian sống và xử lý khi lỗi phụ thuộc cấu hình và khả năng của provider.
4. **Consumer** đã đăng ký nhận thông điệp từ queue. Trong Spring, listener container quản lý kết nối, session, việc nhận và gọi phương thức gắn `@JmsListener`.
5. **Consumer** thực thi nghiệp vụ; sau đó thông điệp được xác nhận (acknowledge) hoặc transaction JMS được commit theo chế độ đã cấu hình. Nếu xử lý thất bại, hệ thống có thể redeliver, retry hoặc đưa sang dead-letter queue theo chính sách.

**Điểm dễ nhầm:** phương thức `send` trả về thành công **không có nghĩa** consumer đã chạy xong nghiệp vụ. Nó chỉ thể hiện việc gửi đã hoàn tất theo hợp đồng và cách cấu hình provider/send. Muốn biết nghiệp vụ thành công cần cơ chế riêng, chẳng hạn trạng thái trong cơ sở dữ liệu, thông điệp kết quả hoặc mô hình request/reply.

## 3. JMS provider: người hiện thực hợp đồng lập trình

JMS/Jakarta Messaging mô tả các khái niệm và giao diện chuẩn, còn provider cung cấp bản triển khai có thể kết nối được. Các thành phần tiêu biểu:

- `jakarta.jms.ConnectionFactory`: điểm vào để tạo kết nối/JMS context. Đối tượng thực tế do provider hoặc môi trường Spring/Java EE cấu hình; nó biết thông tin như địa chỉ broker, xác thực, giao thức, TLS.
- `Connection`, `Session` hoặc API rút gọn `JMSContext`: quản lý ngữ cảnh gửi/nhận, transaction và acknowledgment theo JMS.
- `Destination` (`Queue`/`Topic`), `Message` (ví dụ `TextMessage`), `MessageProducer`/`JMSProducer` và `MessageConsumer`/`JMSConsumer`: các đối tượng mà mã Java sử dụng theo hợp đồng JMS.
- **Client driver và cơ chế transport**: phần riêng của provider chuyển các lời gọi Java thành trao đổi với hạ tầng tương ứng.

Ví dụ: khi chọn Artemis, ứng dụng dùng thư viện Artemis JMS client tương thích với phiên bản Jakarta Messaging của dự án; `ConnectionFactory` được cấu hình để nói chuyện với Artemis broker. Khi chọn provider khác, **ý tưởng producer/consumer, queue/topic và nhiều JMS API vẫn giữ nguyên**, nhưng dependency, cách tạo `ConnectionFactory`, giao thức, bảo mật và vận hành có thể thay đổi.

JMS là **chuẩn API**, không phải giao thức mạng phổ quát. Hai broker của hai hãng khác nhau không tự động giao tiếp với nhau chỉ vì đều hỗ trợ JMS; nếu cần tích hợp liên broker phải kiểm tra giao thức/bridge cụ thể.

## 4. Broker: nơi thông điệp được trung chuyển

Broker là thành phần trung gian **độc lập với mã nghiệp vụ**. Thay vì `OrderService` biết địa chỉ `InventoryService`, producer biết tên destination và cách kết nối broker. Broker chịu trách nhiệm cho các việc hạ tầng như:

- **Tiếp nhận và định tuyến:** map thông điệp tới queue/topic/subscription phù hợp.
- **Tạm giữ thông điệp:** cho phép producer và consumer không nhất thiết hoạt động đồng thời; thời gian giữ còn tùy kiểu destination, chế độ delivery, TTL và chính sách broker.
- **Phân phối và điều tiết:** giao thông điệp cho consumer sẵn sàng; quản lý tình trạng chậm, giới hạn tài nguyên, số consumer và luồng thông điệp.
- **Tin cậy và vận hành:** xử lý xác nhận, redelivery, dead-letter routing, lưu trữ bền vững, giám sát, phân quyền, mã hóa đường truyền, HA/cluster... theo cấu hình và tính năng sản phẩm.

Một **queue** hoặc **topic** là *destination logic* trong mô hình JMS, không phải một tiến trình Java consumer. `Queue`/`Topic` object ở phía client đại diện cho destination; việc tạo và quản trị destination vật lý thường do broker hoặc cơ chế provider-specific quyết định. Gọi `createQueue("orders.created")` trong JMS API không đồng nghĩa đã tạo một queue bền vững ở broker trong mọi sản phẩm.

### Queue và topic ảnh hưởng cách broker phân phối

| Tiêu chí | Queue (point-to-point) | Topic (publish/subscribe) |
| --- | --- | --- |
| Ý định | Chia việc giữa các worker; một thông điệp được xử lý bởi **một** consumer thuộc queue | Phát một sự kiện tới **nhiều subscription** |
| Nhiều consumer | Cạnh tranh nhận trên cùng queue; một message chỉ giao cho một consumer trong một lượt delivery thông thường (có thể redelivery khi lỗi) | Mỗi subscription đủ điều kiện nhận một bản sao riêng; nhiều consumer có thể chia tải trong shared subscription |
| Consumer offline | Thông điệp có thể chờ trong queue theo TTL/quota/chính sách | Subscription **non-durable** thường không giữ các message xuất hiện khi subscriber vắng mặt; **durable subscription** được thiết kế để giữ message theo quy tắc của nó |
| Ví dụ | `orders.to-fulfill`: nhóm worker xử lý đơn | `orders.events`: kho, thông báo và phân tích mỗi hệ thống cần một bản sao |

~~~text
QUEUE:  Producer -> [ Q ] -> Consumer A  (message #1)
                           -> Consumer B  (message #2)
        Hai consumer cạnh tranh; một message không broadcast cho cả hai.

TOPIC:  Producer -> [ T ] -> Subscription kho        -> Consumer kho
                           -> Subscription thông báo -> Consumer thông báo
        Mỗi subscription phù hợp nhận bản sao của sự kiện.
~~~

Không nên suy luận rằng topic luôn lưu vĩnh viễn cho mọi ứng dụng chưa từng subscribe; độ bền và khả năng nhận sau khi offline phụ thuộc việc tạo subscription và cấu hình. Với queue, thứ tự xử lý *toàn hệ thống* cũng không được đảm bảo tuyệt đối nếu có nhiều consumer, priority, redelivery hoặc xử lý song song.

## 5. Ứng dụng khách: producer và consumer

**Producer** quyết định *khi nào phát* thông điệp và *payload có nghĩa gì*. Nó không cần biết consumer nào đang online. Ví dụ: `OrderService` phát thông báo đơn mới sau khi một đơn hàng được ghi nhận theo luồng nghiệp vụ đã thiết kế.

**Consumer** quyết định *phải làm gì* khi nhận payload. Ví dụ: `InventoryService` kiểm tra mã đơn và giữ tồn kho. Một ứng dụng có thể vừa nhận thông điệp từ queue A, vừa phát kết quả sang queue B; producer/consumer là **vai trò trong một luồng**, không nhất thiết là hai service hay hai máy chủ.

Ứng dụng cần thống nhất **hợp đồng thông điệp** với các bên liên quan: tên destination, định dạng (String/JSON/bytes...), schema/version, key định danh, cách xử lý trùng lặp và lỗi. Provider giúp truyền thông điệp, nhưng không tự hiểu nghiệp vụ "đơn hàng" hoặc xác nhận quy trình kho đã thành công.

### Spring nằm ở đâu?

- `JmsTemplate` là **thư viện phía ứng dụng** giúp gửi/nhận bằng JMS, quản lý boilerplate như lấy và đóng tài nguyên; **không phải broker**.
- `@JmsListener` đánh dấu phương thức xử lý thông điệp. Spring tạo listener endpoint/container để nhận message và gọi phương thức; annotation **không tự tạo broker**.
- `DefaultMessageListenerContainer`, `DefaultJmsListenerContainerFactory` và các abstraction tương tự quản lý vòng đời, concurrency, transaction/recovery ở phía **ứng dụng**.
- `ConnectionFactory` là cầu nối giữa Spring/JMS client và provider. Spring Boot thường tự cấu hình bean này khi có starter phù hợp và đủ thông số kết nối.

~~~text
Nghiệp vụ Java
      |
Spring JMS (JmsTemplate / @JmsListener / listener container)
      |
JMS API (jakarta.jms.*)
      |
Provider-specific JMS client / ConnectionFactory
      |
[network / provider transport]
      |
Broker và queue/topic/subscription
~~~

Spring giảm khối lượng mã kết nối/nhận/gửi, nhưng **không thay thế trách nhiệm của provider và broker**. Khai báo `@JmsListener` khi broker chưa chạy hoặc sai thông tin kết nối vẫn có thể gây lỗi kết nối/recovery.

## 6. Ví dụ Spring Boot: một ứng dụng đóng cả hai vai trò client

Ví dụ minh họa với **Java 17+**, Spring Boot 3.x (hoặc phiên bản tương thích với Jakarta JMS) và **Apache ActiveMQ Artemis**. Trong thực tế, producer và consumer có thể nằm ở hai service riêng; đặt chung một ứng dụng ở đây để thấy luồng hoàn chỉnh.

**Điều kiện chạy:**

1. Tạo dự án Java/Maven từ [Spring Initializr](https://start.spring.io/) với dependency **Spring for Apache ActiveMQ Artemis** (starter Maven: `org.springframework.boot:spring-boot-starter-artemis`).
2. Chạy một **Artemis broker bên ngoài ứng dụng**, có cổng chấp nhận JMS ở `localhost:61616`. Cấu hình queue `orders.created` hoặc bật cơ chế tự tạo destination phù hợp với broker. Tên queue được thống nhất giữa bên gửi và bên nhận.
3. Đặt thông tin tài khoản broker qua biến môi trường `ARTEMIS_USER` và `ARTEMIS_PASSWORD`, hoặc điều chỉnh cấu hình kết nối cho đúng môi trường.

Tệp `src/main/resources/application.properties`:

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=${ARTEMIS_USER}
spring.artemis.password=${ARTEMIS_PASSWORD}
spring.jms.pub-sub-domain=false
~~~

`mode=native` nghĩa là ứng dụng kết nối tới broker đã chạy riêng; `pub-sub-domain=false` dùng queue cho ví dụ này. Cấu hình trên không tạo hoặc khởi động broker trong ứng dụng.

Tệp `src/main/java/com/example/jms/JmsRoleDemoApplication.java`:

~~~java
package com.example.jms;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class JmsRoleDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmsRoleDemoApplication.class, args);
    }

    // Producer: gửi một TextMessage sau khi ứng dụng khởi động.
    @Bean
    ApplicationRunner publishOnce(JmsTemplate jmsTemplate) {
        return args -> {
            String orderId = "order-123";
            jmsTemplate.convertAndSend("orders.created", orderId);
            System.out.println("PRODUCER -> sent " + orderId);
        };
    }
}

// Consumer: Spring tạo listener container cho method này.
@Component
class OrderConsumer {

    @JmsListener(destination = "orders.created")
    public void onOrder(String orderId) {
        System.out.println("CONSUMER <- received " + orderId);
    }
}
~~~

Với Spring Boot đã auto-configure JMS từ starter, các bean `JmsTemplate`, `ConnectionFactory` và listener infrastructure được chuẩn bị theo cấu hình. Với ứng dụng **Spring Framework thuần** không dùng Boot, cần tự cấu hình `ConnectionFactory`, `JmsTemplate` và listener container/factory, thường kèm `@EnableJms`.

Tại thư mục dự án Maven, sau khi broker và biến môi trường sẵn sàng:

~~~bash
mvn spring-boot:run
~~~

Khi broker hoạt động, thông tin đăng nhập hợp lệ, destination có sẵn và queue không còn thông điệp cũ, log có hai dòng nghiệp vụ tiêu biểu:

~~~text
PRODUCER -> sent order-123
CONSUMER <- received order-123
~~~

Hai dòng **có thể xuất hiện khác thứ tự** vì consumer nhận bất đồng bộ; các dòng startup/log khác của Spring cũng sẽ có. Mỗi lần chạy ứng dụng producer gửi thêm một thông điệp mới. Nếu chạy nhiều instance consumer cùng đọc queue, một thông điệp sẽ được giao cho một instance mỗi lần delivery, theo cơ chế của broker.

**Xác định vai trò từ mã:**

- `JmsRoleDemoApplication.publishOnce` là **producer client**, gọi `JmsTemplate` để gửi.
- `OrderConsumer.onOrder` là **consumer client**, được Spring gọi khi có message.
- Dependency Artemis và `ConnectionFactory` là phần **kết nối/triển khai JMS của provider ở phía ứng dụng**.
- Tiến trình Artemis nghe ở `localhost:61616` là **broker**; queue `orders.created` là destination logic tại broker.
- Spring nằm trong client app, điều phối JMS API và business method, không tự đóng vai trò broker khi dùng `mode=native`.

## 7. Ranh giới trách nhiệm khi thành công, lỗi và scale

| Tình huống | Ai chịu trách nhiệm chính? | Hệ quả cần hiểu |
| --- | --- | --- |
| Không kết nối được `localhost:61616`, sai credentials/TLS | Client config + provider driver + broker/network | Kiểm tra broker sống, endpoint, cổng, auth, firewall; thêm mã `@JmsListener` không khắc phục kết nối sai |
| Gửi message thành công nhưng chưa thấy xử lý | Kiểm tra destination, broker queue/subscription, consumer và processing | Gửi thành công không đồng nghĩa xử lý nghiệp vụ đã commit |
| Consumer chậm, backlog tăng | Consumer throughput và broker quota/flow control | Scale consumer cho queue, theo dõi độ sâu queue, thời gian chờ và tài nguyên |
| Consumer throw exception | Logic consumer + cấu hình transaction/ack + chính sách broker | Có thể redelivery; thiết kế retry, parking queue/DLQ theo provider |
| Cần cả kho lẫn thông báo nhận cùng một sự kiện | Kiến trúc destination/subscription | Dùng topic với subscription phù hợp, không đặt hai nhóm độc lập cạnh tranh cùng một queue |
| Thay broker/provider | Provider driver/config + kiểm thử tích hợp | JMS API chung giúp giảm phụ thuộc nhưng không bảo đảm cấu hình, protocol và tính năng vendor tương đương |

### Ack, transaction và thông điệp trùng lặp

- **Acknowledgment** xác nhận một lần delivery đã được client tiếp nhận theo chế độ dùng. Với session không transaction, `AUTO_ACKNOWLEDGE`, `CLIENT_ACKNOWLEDGE`... có ngữ nghĩa riêng; với session transaction, `commit`/`rollback` chi phối việc xác nhận. Spring listener container có thể quản lý thay mã ứng dụng.
- **Redelivery** có thể xảy ra khi consumer xử lý lỗi, rollback hoặc lỗi kết nối. Vì vậy ứng dụng thường phải **idempotent**: xử lý lại cùng `orderId`/event ID không tạo ra hai lần trừ kho hoặc hai bản ghi không mong muốn.
- `DeliveryMode.PERSISTENT` là yêu cầu về độ bền delivery của JMS, **không phải lời hứa rằng mọi lỗi hạ tầng đều không làm mất dữ liệu**. TTL, hạn ngạch, cấu hình lưu trữ, broker failover và policy vẫn phải được xem xét.
- Một transaction JMS **không tự động** làm thao tác ghi database và acknowledgment JMS trở thành một transaction nguyên tử xuyên hai hệ thống. Cần cân nhắc transaction coordinator/XA khi phù hợp, hoặc outbox/inbox, idempotency và xử lý bù tùy yêu cầu nghiệp vụ.

### Quan sát và vận hành

Ứng dụng nên ghi log/correlation ID và đo latency, lỗi xử lý, số lần redelivery. Hệ thống broker nên được giám sát kết nối, số message chờ, mức tiêu thụ, age của message, lỗi xác thực và dead-letter queue. Nhóm sở hữu ứng dụng xử lý **lỗi nghiệp vụ**; nhóm vận hành messaging/provider theo dõi **hạ tầng gửi nhận**; cả hai phải thống nhất SLO và quy trình xử lý sự cố.

## 8. Những ngộ nhận thường gặp

1. **“JMS là tên một broker.”** Sai. JMS là chuẩn API. Artemis hay IBM MQ là giải pháp triển khai/hệ thống messaging hỗ trợ JMS.
2. **“JMS provider luôn là đúng một tiến trình broker.”** Sai. Provider bao gồm các thành phần triển khai và giao tiếp JMS; broker là một vai trò triển khai phổ biến, có thể chạy tách biệt hoặc nhúng.
3. **“`JmsTemplate` tự lưu message.”** Sai. Nó là abstraction ở phía ứng dụng; việc giữ và phân phối message thuộc hệ thống messaging/broker theo cấu hình.
4. **“Hai consumer của cùng queue đều nhận mỗi message.”** Sai. Họ cạnh tranh nhận. Muốn fan-out cho nhiều nhóm chức năng, dùng topic cùng subscription phù hợp hoặc thiết kế định tuyến riêng.
5. **“Topic tự phát lại message cũ cho mọi subscriber mới.”** Sai. Cần hiểu thời điểm subscription được tạo, durable/non-durable và chính sách broker.
6. **“Gửi xong là xử lý xong, không thể trùng message.”** Sai. Lúc gửi xong thường chưa biết nghiệp vụ của consumer, và retry/redelivery có thể gây xử lý lặp.
7. **“Đổi provider chỉ cần thay một JAR.”** Không chắc. API chuẩn hỗ trợ tính di động, nhưng `ConnectionFactory`, giao thức, credentials, destination provisioning, subscription, retry, DLQ và HA cần kiểm thử lại.
8. **“Chỉ dùng Spring thì không cần broker.”** Sai trong mô hình broker ngoài: Spring xử lý kết nối và listener ở client, provider/broker vẫn phải tồn tại và được cấu hình.

## 9. Tự kiểm tra kiến thức

- **Tại sao producer không cần biết địa chỉ consumer?** Vì producer gửi tới một destination qua provider; broker nhận và định tuyến tới consumer/subscription thích hợp.
- **Một Spring service dùng cả `JmsTemplate` và `@JmsListener` có là hai JMS client không?** Đó là **một ứng dụng** đang đảm nhiệm cả hai vai trò producer và consumer (có thể dùng nhiều kết nối/session tùy cấu hình), không bắt buộc tách hai service.
- **Broker đã nhận message nhưng consumer xử lý lỗi, ai làm gì?** Listener/client báo lỗi hoặc rollback theo chính sách; broker/provider có thể phát lại/đưa vào DLQ; ứng dụng phải xử lý an toàn khi nhận lại.
- **Vì sao không dùng một queue để fan-out cho kho và email?** Vì các consumer của cùng queue cạnh tranh nhận, không có bảo đảm mỗi nhóm nhận một bản; topic/subscription mới phù hợp với sự kiện cần nhiều nhóm nhận.

## Tài liệu đối chiếu

- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html) — định nghĩa provider/client, mô hình queue/topic, subscription, acknowledge và transaction.
- [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html) — `JmsTemplate`, `ConnectionFactory`, listener container.
- [Spring guide — Messaging with JMS](https://spring.io/guides/gs/messaging-jms/) — ví dụ `JmsTemplate` và `@JmsListener`.
- [Spring Boot — JMS, Apache ActiveMQ Artemis](https://docs.spring.io/spring-boot/reference/messaging/jms.html) — tự cấu hình provider client và broker connection.
