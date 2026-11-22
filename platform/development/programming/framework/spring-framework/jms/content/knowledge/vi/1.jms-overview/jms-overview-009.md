# Trách nhiệm của ứng dụng, Spring và broker trong JMS

Trong một hệ thống dùng **Jakarta Messaging (JMS)** với **Spring Framework**, ba thành phần cùng tham gia vào một luồng thông điệp nhưng chịu trách nhiệm khác nhau:

- **Ứng dụng (producer/consumer)** quyết định *vì sao* gửi thông điệp, thông điệp có ý nghĩa nghiệp vụ gì, xử lý thành công là gì và làm sao tránh tạo tác dụng phụ trùng lặp.
- **Spring JMS** cung cấp lớp tích hợp trong tiến trình Java: quản lý tài nguyên JMS, chuyển đổi dữ liệu, gửi/nhận thông điệp, gọi mã xử lý, cấu hình container, acknowledgment và ranh giới giao dịch JMS.
- **JMS provider/broker** triển khai hạ tầng vận chuyển: nhận, định tuyến, lưu trữ và phân phối thông điệp tới queue/topic cùng các chính sách vận hành cụ thể.

**JMS là một hợp đồng API**, không phải bản thân broker. Với Spring Boot 3.x/Spring Framework 6.x, API dùng gói **jakarta.jms**. Một broker như Apache ActiveMQ Artemis là một *provider* triển khai hợp đồng đó; Spring không thay thế broker.

## 1. Sơ đồ luồng và ranh giới sở hữu

~~~text
ỨNG DỤNG GỬI                  SPRING / JMS CLIENT                  BROKER
Tạo sự kiện nghiệp vụ  ──>  JmsTemplate + converter  ──>  Queue hoặc Topic
                                                         │
                                                         │ lưu/định tuyến/phân phối
                                                         ▼
ỨNG DỤNG NHẬN             SPRING / JMS CLIENT           JMS Consumer
Xử lý @JmsListener    <── container + converter    <── delivery từ broker
        │
        ├── thành công: hoàn tất xử lý, commit/ack theo cấu hình
        └── thất bại: exception/rollback; broker quyết định redelivery theo chính sách
~~~

Sơ đồ cố ý tách **mã nghiệp vụ** khỏi **cơ chế tích hợp** và **nơi lưu/định tuyến message**. Broker không tự hiểu rằng một đơn hàng đã thanh toán đúng; Spring cũng không tự quyết định sự kiện nào là hợp lệ trong nghiệp vụ.

| Việc cần làm | Ứng dụng sở hữu | Spring JMS hỗ trợ | Broker/provider sở hữu |
| --- | --- | --- | --- |
| Khi nào phát sinh sự kiện, tên sự kiện, ý nghĩa payload | Thiết kế và thực thi | Chuyển POJO/String thành JMS Message nếu cấu hình converter | Chỉ mang dữ liệu và metadata |
| Gửi đến đâu | Chọn đích theo hợp đồng nghiệp vụ | JmsTemplate, DestinationResolver, ConnectionFactory | Cung cấp queue/topic và tuyến phân phối thực tế |
| Kết nối, session, consumer | Khai báo cấu hình, thông số mong muốn | Tạo/sử dụng/đóng hoặc cache tài nguyên; listener container | Cung cấp giao thức và endpoint tương ứng |
| Phân phối cho consumer | Chọn queue/topic và nhóm consumer phù hợp | Nhận rồi gọi listener, quản lý concurrency | Queue cạnh tranh người nhận; topic theo subscription; lưu và giao lại theo chính sách |
| Dữ liệu hợp lệ, quyền thực hiện hành động | Validate, ủy quyền nghiệp vụ, chống xử lý trùng | Có thể gọi validation/conversion do ứng dụng cấu hình | Kiểm soát kết nối, ACL tới destination; không kiểm tra quy tắc nghiệp vụ |
| Ack/transaction | Chọn yêu cầu an toàn và xử lý lỗi | Điều khiển session/transaction của listener | Ghi nhận commit/ack, redelivery và retention theo cấu hình |
| Retry và thông điệp lỗi lâu dài | Quyết định lỗi nào retry, idempotency, xử lý poison message | Có thể rollback/throw, backoff phục hồi kết nối; tích hợp error handler | Chính sách redelivery delay, số lần thử, DLQ/expiry tùy provider |
| Quan sát và vận hành | Log, trace, SLA, cảnh báo nghiệp vụ | Expose trạng thái listener, lỗi ứng dụng | Queue depth, consumer count, disk, DLQ, kết nối, cảnh báo hạ tầng |

**Phân biệt trách nhiệm thiết kế và thực thi:** ứng dụng quyết định yêu cầu (ví dụ cần xử lý được khi nhận lại message), còn broker thực thi cơ chế phân phối và lưu trữ theo những bảo đảm mà provider/cấu hình cụ thể cung cấp.

## 2. Theo dấu một thông điệp từ đầu tới cuối

Giả sử dịch vụ đặt hàng phát ra sự kiện **OrderCreated** vào queue **orders.events** để dịch vụ xử lý tiếp nhận.

1. **Ứng dụng producer** hoàn tất quyết định nghiệp vụ, chuẩn bị payload có hợp đồng rõ ràng (mã đơn, loại sự kiện, phiên bản schema, eventId). Nó xác định khi nào được phát thông điệp, cách xử lý lỗi gửi và có cần transactional outbox để gắn việc tạo sự kiện với giao dịch DB hay không.
2. **Spring** nhận lệnh qua **JmsTemplate.convertAndSend** hoặc **send**. Nếu dùng converter, Spring tạo một JMS Message thích hợp; qua **ConnectionFactory** của provider, nó lấy tài nguyên JMS và chuyển lệnh gửi. Spring giải phóng/quản lý tài nguyên theo cấu hình.
3. **Broker** nhận message ở destination đã định, áp dụng quyền truy cập, định tuyến, persistence và QoS theo giao thức/chính sách. Việc lệnh gửi trả về thành công **không đồng nghĩa** mã consumer đã chạy thành công. Với gửi trong một JMS transaction, khả năng message nhìn thấy được còn phụ thuộc **commit** của transaction đó.
4. **Broker** chọn một consumer đủ điều kiện của queue. Nếu là topic, broker phân phối tới các subscription đủ điều kiện; subscriber bền vững/non-durable có quy tắc khác nhau khi offline.
5. **Spring listener container** giữ consumer/session, lấy message, thực hiện conversion và gọi method đánh dấu **@JmsListener**. Khi method hoàn tất hoặc ném exception, container áp dụng acknowledgment/transaction đã cấu hình.
6. **Ứng dụng consumer** kiểm tra payload, thực hiện thao tác nghiệp vụ và lưu dấu **eventId đã xử lý** theo cách chống trùng. Nếu processing lỗi, nó phải để lỗi biểu hiện theo hợp đồng listener (thường throw exception) để transaction JMS có thể rollback.
7. **Broker** hoàn tất ack/commit, hoặc đưa message trở lại luồng giao nhận khi rollback và policy cho phép. Một message thất bại nhiều lần có thể được chuyển sang dead-letter queue (DLQ) **nếu broker đã cấu hình**.

Điểm cần nhớ: thành công ở một lớp không chứng minh thành công ở các lớp sau. **Producer send thành công ≠ consumer xử lý xong ≠ cập nhật cơ sở dữ liệu đã an toàn.**

## 3. Trách nhiệm cụ thể của ứng dụng

### 3.1. Hợp đồng sự kiện

Ứng dụng sở hữu schema và ý nghĩa nghiệp vụ. Một payload tối thiểu nên có định danh nghiệp vụ, **eventId** ổn định, **eventType**, phiên bản schema và các trường đủ để consumer hiểu sự kiện. Đặt tiêu chuẩn cho khả năng tương thích khi thêm trường, bỏ trường hoặc đổi kiểu dữ liệu.

- **eventId** là khóa chống trùng do ứng dụng thiết kế; khác với **JMSMessageID** do provider gán cho một JMS message cụ thể.
- **JMSCorrelationID** hữu ích cho liên kết request/reply và trace; nếu cần liên kết nghiệp vụ xuyên hệ thống, ứng dụng phải chủ động đặt và truyền metadata phù hợp.
- Header/property JMS dùng cho routing và filter; **message selector không đọc nội dung body**, chỉ dùng header/property.
- Chọn định dạng có thể kiểm thử và quản lý phiên bản (thường JSON trong TextMessage). Không mặc nhiên dùng ObjectMessage để deserialize đối tượng Java từ nguồn không đáng tin.

### 3.2. Tính đúng đắn và idempotency

Một consumer phải chịu được việc **cùng một sự kiện nghiệp vụ xuất hiện lại**. Với queue và transaction thông thường, sự cố giữa lúc ghi DB và lúc xác nhận JMS vẫn có thể làm message được giao lại. Chiến lược phổ biến:

1. Gắn mỗi sự kiện một eventId duy nhất, ổn định giữa các lần thử gửi.
2. Tạo bảng **processed_messages(event_id PRIMARY KEY, ...)** hoặc unique constraint tương đương.
3. Trong **cùng một DB transaction**, kiểm tra/ghi dấu eventId và thay đổi nghiệp vụ. Xử lý xung đột khóa duy nhất khi có nhiều consumer cạnh tranh; chỉ một lần tạo tác dụng phụ.
4. Chỉ để listener hoàn tất thành công sau khi xử lý nghiệp vụ đã commit. Nếu lỗi trước đó, throw exception để giao dịch JMS rollback.

Ví dụ mã giả (chỉ minh họa logic; tên repository/service do ứng dụng tự triển khai):

~~~java
@Transactional // Transaction của cơ sở dữ liệu, không tự biến thành JMS transaction
public void applyOrderCreated(OrderCreated event) {
    if (processedMessages.existsByEventId(event.eventId())) {
        return; // Đã xử lý: có thể acknowledge thông điệp giao lại
    }
    orders.markCreated(event.orderId());
    processedMessages.insert(event.eventId()); // UNIQUE/PRIMARY KEY
}
~~~

**Chú ý:** thao tác kiểm tra và ghi dấu phải an toàn khi chạy đồng thời; chỉ gọi exists rồi insert trong hai bước không có ràng buộc unique là chưa đủ. Nếu tạo side effect bên ngoài DB (gửi email, gọi API thanh toán), cần cơ chế idempotency của bên nhận hoặc outbox cho side effect đó.

### 3.3. Xử lý lỗi có chủ đích

Phân biệt lỗi **tạm thời** (DB tạm mất kết nối), lỗi **vĩnh viễn** (schema không hiểu, thiếu trường bắt buộc) và lỗi **nghiệp vụ** (đơn hàng không tồn tại). Ứng dụng quyết định thông điệp nào nên thử lại, thông điệp nào cần ghi nhận/điều tra. Không được nuốt exception rồi coi như thành công khi đang kỳ vọng JMS rollback.

## 4. Trách nhiệm cụ thể của Spring JMS

Spring làm cho ứng dụng ít phải tự quản lý các đối tượng JMS mức thấp nhưng **không tạo ra một broker**:

- **ConnectionFactory:** điểm vào JMS do provider/Boot cấu hình; chứa thông tin endpoint, xác thực, kết nối, có thể đi cùng caching/pooling. Trong Spring Boot, starter JMS phù hợp thường cấu hình bean này và **JmsTemplate**.
- **JmsTemplate:** API gửi và nhận đồng bộ, tạo/sử dụng session/producer rồi quản lý tài nguyên. Method **convertAndSend** chạy qua MessageConverter; **send** dùng MessageCreator để tạo message trực tiếp.
- **MessageConverter:** đổi giữa kiểu dữ liệu Java và JMS Message. Mặc định kiểu String thường thành TextMessage; POJO JSON cần converter và quy ước schema rõ ràng.
- **@JmsListener:** khai báo destination/method nhận; Spring tạo endpoint và đưa vào **message listener container** để xử lý bất đồng bộ so với caller producer.
- **DefaultMessageListenerContainer / DefaultJmsListenerContainerFactory:** tạo consumer, quản lý session, vòng lặp nhận, concurrency, recovery kết nối và ranh giới ack/transaction theo cấu hình. Một instance listener có thể được gọi đồng thời, vì vậy code xử lý phải thread-safe.
- **Transaction integration:** session JMS có thể là local transaction; JmsTransactionManager quản lý transaction trên một ConnectionFactory. Với tài nguyên ngoài JMS như database, local JMS transaction **không tự động** biến hai tài nguyên thành một giao dịch nguyên tử.
- **Exception handling:** với container/session phù hợp, exception từ listener dẫn đến rollback; xử lý hoặc log lỗi phải bảo toàn cơ chế mong muốn. Cấu hình recovery của container khác với chính sách redelivery/poison-message ở broker.

Spring Boot có thể tự cấu hình một số bean/default, nhưng người thiết kế vẫn phải **xem rõ session transacted, converter, concurrency, queue/topic, destination, timeout, credentials**. Đừng dựa vào suy đoán rằng chỉ có annotation là mọi trường hợp lỗi sẽ được xử lý an toàn.

## 5. Trách nhiệm cụ thể của broker và phạm vi của chuẩn JMS

Broker triển khai những phần có tính hạ tầng: địa chỉ/queue/topic, phân phối cho consumer, lưu trữ thông điệp, persistence, giới hạn tài nguyên, ACL/TLS, quản trị người dùng, consumer/subscription, backpressure, expiry và vận hành. **DLQ, backoff, redelivery limit và tên địa chỉ lỗi** thường là chính sách của provider/broker chứ không phải một thuật toán chuẩn do Spring tự làm cho mọi JMS provider.

| Khái niệm | Ý nghĩa và người chịu trách nhiệm |
| --- | --- |
| **Queue** | Một message được giao cho **một** consumer trong nhóm consumer của queue (có thể được giao lại sau lỗi). Ứng dụng chọn mô hình work-queue; broker phân phối. |
| **Topic** | Mỗi subscription phù hợp nhận bản sao riêng. Với subscriber không bền vững, mất kết nối có thể bỏ lỡ message; durable/shared subscriptions có quy tắc khác và cần định danh/cấu hình đúng. |
| **PERSISTENT delivery** | Yêu cầu độ bền phân phối theo hợp đồng JMS và provider; không đảm bảo handler nghiệp vụ đã commit DB. Nhà vận hành phải hiểu cấu hình storage, replication, failover và expiry. |
| **Ack/commit** | Báo cho provider rằng việc nhận đã hoàn tất theo mode/transaction; broker cập nhật trạng thái delivery. Ack không kiểm chứng ý nghĩa nghiệp vụ. |
| **Redelivery** | Khi một delivery không được xác nhận hoặc transaction rollback, provider có thể giao lại theo quy tắc; cờ **JMSRedelivered** và property **JMSXDeliveryCount** giúp chẩn đoán nhưng không thay cho eventId nghiệp vụ. |
| **TTL/expiration** | Message có thể hết hạn trước khi được xử lý. Ứng dụng định nghĩa hạn sử dụng; broker thực thi loại bỏ/định tuyến expiry theo tính năng và cấu hình. |
| **Ordering** | JMS có một số bảo đảm thứ tự trong phạm vi session/consumer; nhiều consumer, priority, redelivery, selector và nhiều destination làm thay đổi thứ tự quan sát. Không giả định FIFO toàn cục. |
| **DLQ** | Đích chứa thông điệp không xử lý được theo chính sách broker. Cần giám sát, phân loại, cách reprocess và kiểm soát vòng lặp lỗi. |

**Không nhầm queue với topic:** tăng số consumer của cùng một queue thường tăng khả năng xử lý công việc; tăng subscription của topic có thể làm tăng số bản sao mỗi sự kiện được xử lý. Cả hai mô hình đều đòi hỏi thiết kế idempotency riêng.

## 6. Ví dụ Spring Boot 3.x: ai thực hiện điều gì?

Ví dụ sau dùng **Java 17+**, Spring Boot 3.3.x và **broker Apache ActiveMQ Artemis chạy bên ngoài ứng dụng**. Broker phải sẵn sàng ở localhost:61616, tài khoản/password trùng cấu hình và queue **orders.events** phải tồn tại hoặc được broker cho phép tự tạo. Đây là một ứng dụng mẫu đầy đủ ở phía Spring; nó **không cài/khởi động broker**.

**build.gradle** (trong project Gradle có Gradle Wrapper phù hợp):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
~~~

**src/main/resources/application.properties:**

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=demo
spring.artemis.password=demo
spring.jms.pub-sub-domain=false
spring.jms.listener.session.transacted=true
~~~

**src/main/java/example/jms/JmsDemoApplication.java:**

~~~java
package example.jms;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class JmsDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(JmsDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner publishOneEvent(JmsTemplate jmsTemplate) {
        return args -> jmsTemplate.convertAndSend(
                "orders.events",
                "order-42",
                message -> {
                    message.setStringProperty("eventType", "OrderCreated");
                    message.setStringProperty("eventId", "evt-42");
                    return message;
                });
    }
}
~~~

**src/main/java/example/jms/OrderListener.java:**

~~~java
package example.jms;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {
    @JmsListener(destination = "orders.events")
    public void onOrder(String payload) {
        // Demo: ứng dụng thực tế cần validate + transaction DB + idempotency.
        System.out.println("Received order: " + payload);
    }
}
~~~

Chạy khi broker đã có sẵn: **./gradlew bootRun** (Linux/macOS) hoặc **gradlew.bat bootRun** (Windows). Ở lần nhận message thành công, output của ứng dụng có dòng:

~~~text
Received order: order-42
~~~

Đây là output **kỳ vọng trong đường đi thành công**, không phải bảo đảm chính xác một dòng trong mọi môi trường: queue có thể chứa message cũ, broker có thể trả message sau reconnect, và startup còn có log của Spring.

**Phân tích từng dòng quan trọng:**

1. **JmsDemoApplication** (ứng dụng) quyết định tên destination, payload và thuộc tính eventType/eventId. Dữ liệu mẫu là String; default converter chuyển nó thành **TextMessage**.
2. **JmsTemplate.convertAndSend** (Spring) tạo/gửi message bằng ConnectionFactory mà Spring Boot cấu hình từ starter và thuộc tính Artemis.
3. **Artemis** (broker) phải cho phép kết nối, tiếp nhận địa chỉ và chuyển message cho consumer phù hợp. Spring không thể tạo ra tính bền vững của message nếu broker/config không hỗ trợ.
4. **@JmsListener** (Spring) nối message tới **onOrder**; **onOrder** (ứng dụng) xử lý nghiệp vụ. Ở ví dụ đơn giản, method chỉ in ra console nên **chưa chứng minh xử lý idempotent hay transaction DB**.
5. Thuộc tính **spring.jms.listener.session.transacted=true** yêu cầu listener container dùng JMS transaction cục bộ. Nếu **onOrder** ném exception, message receipt sẽ rollback theo container và broker có thể redeliver theo policy. Giao dịch DB, nếu bổ sung, vẫn là ranh giới riêng.

## 7. Ai chịu trách nhiệm khi có lỗi?

| Sự cố | Hành vi có thể xảy ra | Việc cần làm |
| --- | --- | --- |
| Broker không kết nối được lúc gửi | Spring chuyển lỗi JMS ra exception; producer chưa biết chắc trạng thái nếu đứt kết nối quanh thời điểm broker nhận | Ứng dụng quản lý retry có giới hạn, eventId ổn định, outbox nếu cần; hạ tầng phục hồi broker/kết nối |
| Listener ném exception với JMS session transacted | Container rollback; broker có thể giao lại message | Ứng dụng phân loại lỗi và giữ idempotency; broker có redelivery/DLQ policy |
| DB commit rồi JVM chết trước JMS commit | Cùng message có thể được giao lại, dù thay đổi DB đã thành công | Idempotent consumer và dấu eventId trong DB transaction; không giả định JMS local tx bao trùm DB |
| Message lỗi dữ liệu liên tục | Redelivery lặp lại gây chặn queue, tăng tải | Ứng dụng validate/phân loại; broker giới hạn retry, delay, DLQ; vận hành điều tra/quy trình xử lý lại |
| Broker đầy disk hoặc consumer xử lý chậm | Tồn đọng tăng, producer có thể bị chặn/thất bại tùy policy | Theo dõi queue depth/age, throughput, memory/disk, backpressure; tối ưu consumer và capacity |
| Consumer thêm concurrency nhưng nghiệp vụ yêu cầu thứ tự | Hoàn tất xử lý lệch thứ tự theo nhiều worker | Thiết kế khóa phân vùng/serialization ở nghiệp vụ; không coi tăng concurrency là miễn phí |
| Message hết TTL | Không đến consumer dù producer gửi được | Chọn TTL theo SLA, cảnh báo expiry/age, quy trình reconcile nghiệp vụ |
| Consumer nuốt lỗi rồi return | Container coi method thành công; ack/commit có thể diễn ra | Chỉ bắt lỗi khi đã xử lý đạt hợp đồng, hoặc ném lỗi để rollback; ghi log đủ correlation |

### Ranh giới giao dịch quan trọng

**JMS transaction** quản lý các thao tác trên JMS session. **Database transaction** quản lý cập nhật DB. Dùng **@Transactional** với DataSourceTransactionManager/JpaTransactionManager **không tự động** làm commit JMS và commit DB trở thành một giao dịch nguyên tử. Nếu xử lý cần tác dụng đồng thời lên DB và JMS:

- Cân nhắc **transactional outbox** khi phát thông điệp cùng một thay đổi DB; một relay riêng xuất sự kiện rồi đánh dấu đã gửi, có thể gửi lặp và do đó consumer cần idempotency.
- Với consumer, dùng **inbox/processed_messages** hoặc ràng buộc duy nhất cho eventId trong cùng DB transaction với nghiệp vụ.
- **XA/JTA** chỉ khi thật sự cần atomicity đa tài nguyên và cả provider/tài nguyên đều hỗ trợ, chấp nhận độ phức tạp và chi phí vận hành; không mặc định mọi @Transactional đều là XA.

### Ack không có nghĩa là xử lý nghiệp vụ thành công

Với JMS session **transacted**, commit bao gồm acknowledgment của phần nhận message; rollback cho phép recovery/redelivery theo provider. Với session không giao dịch:

- **AUTO_ACKNOWLEDGE:** theo quy tắc JMS, ack tự động; khi dùng **DefaultMessageListenerContainer**, cách Spring quản lý ack khiến nó không phải lựa chọn đáng tin cậy cho việc rollback/redelivery khi listener lỗi.
- **CLIENT_ACKNOWLEDGE:** ứng dụng có thể gọi acknowledge, nhưng một lần acknowledge có thể xác nhận **mọi message đã được session giao** chứ không đơn giản chỉ một eventId.
- **DUPS_OK_ACKNOWLEDGE:** cho phép lazy acknowledgment và có khả năng duplicate, đòi hỏi consumer chịu được lặp.

Với yêu cầu reliability, nên cân nhắc **transacted listener session** và đọc cấu hình thực tế thay vì suy ra behavior từ tên annotation.

## 8. Quan sát hệ thống và xử lý sự cố

Một giao dịch thành công nên truy vết được qua ba lớp:

- **Ứng dụng:** eventId, businessId, eventType, kết quả xử lý, thời gian xử lý, lỗi có retry được không, idempotency hit/miss và business SLA. Không log payload nhạy cảm tùy tiện.
- **Spring:** lỗi producer/consumer, trạng thái container, số consumer/concurrency, kết nối được phục hồi, timeout, thời gian xử lý listener, số lần listener ném exception.
- **Broker:** queue depth, message age, số consumer, tốc độ enqueue/dequeue/ack, DLQ và expiry, connection/session, disk/memory, replication/failover, ACL/TLS.

Ví dụ khi message **OrderCreated** không được xử lý: trước tiên xem **eventId có được gửi/ghi outbox chưa** (ứng dụng), kế đó xem **JmsTemplate và listener container có kết nối/lỗi conversion không** (Spring), rồi kiểm tra **queue depth, DLQ, expiry, subscriber và ACL** (broker). Đọc cả ba lớp sẽ tránh việc quy kết sai rằng broker lỗi chỉ vì consumer chưa cập nhật DB.

## 9. Những hiểu lầm cần tránh

1. **“Dùng @JmsListener là Spring tự bảo đảm exactly-once nghiệp vụ.”** Sai: Spring kích hoạt listener; redelivery và race giữa DB/JMS vẫn yêu cầu idempotency.
2. **“Broker nhận message nghĩa là đơn hàng đã được xử lý.”** Sai: chỉ biết điểm nào trong quá trình gửi/commit đã thành công; kết quả nghiệp vụ cần xác nhận riêng.
3. **“Đặt @Transactional cho consumer là JMS và DB commit cùng nhau.”** Sai trong trường hợp transaction manager chỉ quản lý một tài nguyên.
4. **“Có lỗi thì Spring tự đưa message vào DLQ.”** Không có quy tắc DLQ chung như vậy; DLQ/retry phụ thuộc broker và cấu hình.
5. **“Queue luôn xử lý FIFO dù có nhiều consumer và retry.”** Không bảo đảm thứ tự hoàn tất toàn cục trong những tình huống đó.
6. **“Dùng persistent message là không bao giờ mất dữ liệu.”** Độ bền phụ thuộc contract JMS, cấu hình provider, storage/failover/retention và cả cách producer xử lý lỗi.
7. **“Consumer throw exception thì mọi mode acknowledge đều tự redeliver giống nhau.”** Sai: mode/container/transaction khác nhau có hành vi khác nhau; kiểm tra cấu hình và thử bằng fault injection.

## 10. Checklist phân công khi thiết kế một luồng JMS

- **Nhóm ứng dụng:** chốt schema/version/eventId; queue hay topic; tính idempotent; thứ tự xử lý; retryable vs non-retryable; khi nào gửi; outbox/inbox; business timeout; log/trace và phương án reconcile.
- **Nhóm tích hợp Spring:** xác nhận Jakarta JMS và starter/provider tương thích; ConnectionFactory; converter; JmsTemplate; @JmsListener/container; ack/transaction; concurrency; kết nối/recovery; integration test cho rollback và nhận trùng.
- **Nhóm broker/vận hành:** tạo/provision destination; queue/topic và subscription; ACL/TLS/secrets; persistence/replication; giới hạn bộ nhớ/disk; TTL; redelivery delay/max attempts; DLQ; giám sát depth/age/delivery/DLQ; sao lưu và diễn tập failover.

**Tiêu chí hiểu đúng:** giải thích được tại sao **JmsTemplate gửi được** nhưng **consumer có thể chưa chạy**; tại sao **consumer ghi DB xong** vẫn **có thể nhận lại message**; và xác định chính xác lớp nào cần sửa trong từng tình huống.

### Tài liệu đối chiếu

- Spring Framework, *Using Spring JMS*: https://docs.spring.io/spring-framework/reference/integration/jms/using.html
- Spring Framework, *@JmsListener annotation-driven endpoints*: https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html
- Spring Boot, *Messaging with JMS*: https://spring.io/guides/gs/messaging-jms/
- Jakarta Messaging 3.1 specification (đặc biệt queue/topic, session, acknowledgment, transaction): https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
