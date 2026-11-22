# Giới hạn bảo đảm khi chỉ bật lưu trữ bền vững

> **Chủ đề:** Chất lượng gửi trong Spring Framework – JMS. Cấu hình `DeliveryMode.PERSISTENT` (persistent delivery) là một phần quan trọng của độ tin cậy, **nhưng không đủ để cam kết “không mất message trong mọi trường hợp”, “không bao giờ xử lý trùng” hay “cập nhật database chính xác một lần”**. Bài này phân tách rõ bảo đảm của Jakarta Messaging, điều kiện của broker và trách nhiệm của ứng dụng, rồi hướng dẫn một thí nghiệm Java 17/Spring Boot/ActiveMQ Artemis để tự quan sát.

## 1. Định nghĩa chính xác: “bật lưu trữ bền vững” là bật cái gì?

Trong Jakarta Messaging (JMS), producer có hai chế độ delivery:

| Chế độ | Giá trị chuẩn | Ý nghĩa theo JMS | Trường hợp thường dùng |
| --- | --- | --- | --- |
| `DeliveryMode.PERSISTENT` | `2` | Yêu cầu JMS provider sử dụng phương thức truyền/giao đủ bền để message không bị mất chỉ vì **provider failure**, dưới các điều kiện về destination, retention và tài nguyên | Lệnh quan trọng, sự kiện nghiệp vụ cần xử lý |
| `DeliveryMode.NON_PERSISTENT` | `1` | Không bắt buộc lưu trên stable storage; provider failure có thể làm mất message | Telemetry/tín hiệu có thể bỏ lỡ hoặc tạo lại |

`PERSISTENT` là **mặc định của JMS producer**. Nó thường kéo theo việc broker ghi message vào journal hoặc storage phù hợp, nhưng **không có nghĩa** ứng dụng Java đã bật chế độ ghi bền vững cho database, không tự động cấu hình replication và không ngăn quản trị viên xóa queue.

Đặc tả Jakarta Messaging 3.1 dùng hai khái niệm: `NON_PERSISTENT` có **at-most-once delivery** trong phạm vi JMS provider, còn `PERSISTENT` có **once-and-only-once delivery** trong phạm vi provider, khi chính sách lưu giữ và tài nguyên đáp ứng điều kiện. Đặc tả đồng thời lưu ý giới hạn quan trọng: **message có thể bị hết hạn, bị loại theo chính sách quản trị hoặc giới hạn tài nguyên**; việc một message được giao lại do session recovery **không được xem là duplicate message** theo cách định nghĩa của đặc tả.

Vì vậy, câu nói “PERSISTENT đảm bảo exactly-once” là **quá rộng và dễ gây hiểu lầm**. Phải luôn nói rõ: *exactly-once của thành phần nào, ở ranh giới nào, và đối với kết quả nào?*

## 2. Phân rã thành bốn ranh giới bảo đảm

Một luồng gửi đơn hàng thường có các bước:

~~~text
[1] Database của Order Service
     INSERT order, COMMIT
            |
            v
[2] JMS Producer
     JmsTemplate.convertAndSend(...)
            |
            v
[3] JMS Broker / Queue
     nhận, định tuyến, lưu message, giao cho consumer
            |
            v
[4] Consumer / Worker
     nhận -> cập nhật database / gọi API ngoài -> ACK hoặc JMS COMMIT
~~~

Ở mỗi ranh giới, `PERSISTENT` chỉ giải quyết **một phần**:

| Ranh giới | Rủi ro | PERSISTENT giúp gì? | Còn thiếu gì? |
| --- | --- | --- | --- |
| (1) Database → producer | DB commit xong, ứng dụng chết trước khi gửi event | Không giúp: message còn chưa được tạo/gửi | Transactional outbox hoặc cơ chế phối hợp DB + message |
| (2) Producer → broker | Network mất đúng lúc gửi; client không biết broker đã ghi chưa | Broker tuân thủ hợp đồng persistent nếu thật sự tiếp nhận/ghi bền | Phân biệt kết quả mơ hồ, retry có ID ổn định, chống event trùng |
| (3) Broker storage → consumer | Broker restart khi message còn trong queue | Có khả năng khôi phục message đã lưu bền, nếu destination, journal và tài nguyên đúng | Durable queue/subscription, persistence config, storage/HA, quota, TTL |
| (4) Consumer → database | DB commit thành công, client chết trước JMS ACK | Broker có thể giao lại message chưa ack/commit | Idempotency hoặc giao dịch phối hợp phù hợp |
| (4) Consumer ACK → side effect | ACK quá sớm, worker chết trước khi làm xong | Không giúp; broker đã coi message được xử lý | Chỉ ACK/commit sau xử lý cần thiết, có transaction/retry |

**Cách đọc đúng:** `PERSISTENT` là một **yêu cầu về quality of service của message trong JMS provider**, không phải transaction trải rộng từ database của producer đến database của consumer.

## 3. Bảo đảm của JMS thực sự nói gì?

### 3.1. Phạm vi của “once-and-only-once”

Jakarta Messaging 3.1, mục *Message delivery mode* và *Reliability*, quy định persistent messages phải được provider bảo vệ trước lỗi của provider, với lưu ý về retention/resource. Một message persistent đã được provider quản lý đúng sẽ không bị broker failure biến thành message tự ý mất hoặc tạo bản sao do chính provider.

Nhưng có ít nhất **ba loại “trùng” khác nhau**:

1. **Provider tự tạo duplicate do failure**, loại trùng mà hợp đồng JMS persistent phải tránh trong phạm vi đã nêu.
2. **Redelivery sau rollback/recover**, nghĩa là cùng logical message được giao lại khi lần xử lý trước chưa được hoàn tất/ack theo JMS; đây là hành vi cần thiết để ứng dụng có cơ hội xử lý lại, không bị JMS định nghĩa là duplicate sai chuẩn.
3. **Producer phát hai message nghiệp vụ tương đương** vì một lần `send`/`commit` có kết quả mơ hồ rồi retry. Với JMS provider, đây có thể là **hai send riêng biệt**, mỗi message tuân thủ delivery contract nhưng ứng dụng nhận hai sự kiện `order-paid` cùng `orderId`.

Do đó, ngay cả khi provider tuân thủ persistent delivery, hệ thống nghiệp vụ vẫn có thể **thấy sự kiện lặp hoặc xử lý side effect nhiều lần** nếu thiếu idempotency.

### 3.2. Điều kiện của destination

Persistent message gửi đến **queue bền vững** là tình huống phổ biến. Đối với **topic**, subscriber muốn nhận message được publish khi nó offline phải dùng **durable subscription** với định danh subscription/client phù hợp; một **non-durable subscription** có thể bỏ lỡ message khi không hoạt động, cho dù publisher dùng `PERSISTENT`.

Với temporary destination, đừng xem persistent mode là hợp đồng lưu giữ sau khi connection/destination bị hủy. Durable message **không tự biến** mọi queue/subscription thành đối tượng bền vững.

### 3.3. Các giới hạn được đặc tả nêu rõ

- **Expiration/TTL:** message có `JMSExpiration` đã qua hạn có thể bị loại và không được giao mới. `PERSISTENT` không ghi đè TTL.
- **Administrative deletion:** purge queue, xóa subscription/address hoặc chính sách quản trị có thể hủy message.
- **Resource restrictions:** hết dung lượng đĩa, queue quota, capacity/flow control, thiếu tài nguyên xử lý có thể phá vỡ giả định “mọi message đều được giữ”.
- **Unresponsive clients:** khi consumer không đủ khả năng xử lý, message backlog và latency tăng; việc lưu được message không bảo đảm nó được xử lý đúng hạn.
- **Provider implementation/configuration:** storage, sync, HA, paging, routing và xác nhận gửi là những điều phải kiểm tra với broker thực tế.

## 4. Gửi thành công có nghĩa gì — và không có nghĩa gì?

Xét:

~~~java
// Snippet: jmsTemplate là bean Spring đã được cấu hình.
jmsTemplate.convertAndSend("orders.queue", "order-created");
System.out.println("send returned");
~~~

Nếu lời gọi trả về bình thường, code đã hoàn thành thao tác gửi theo cấu hình hiện tại của `JmsTemplate`, provider và session. Tuy nhiên:

- Nó **không** bảo đảm một consumer đã nhận message.
- Nó **không** bảo đảm consumer đã commit database.
- Nó **không** bảo đảm destination/subscription có retention phù hợp.
- Nó **không** tự chứng minh storage được fsync hoặc đã replicate sang site khác.
- Nếu có transaction đang mở, message có thể **chưa khả dụng** cho consumer cho đến khi JMS transaction commit.
- Nếu dùng asynchronous sending/cấu hình client không đợi xác nhận đầy đủ, thời điểm phương thức trả về có thể khác với thời điểm broker đã durable-commit. Phải hiểu chính sách xác nhận của provider.

Ở phía ngược lại, nếu `send` ném exception do mất kết nối, **cũng không thể mặc định** message đã không tới broker. Jakarta Messaging mô tả rõ tình huống lỗi xảy ra **sau khi broker nhận/commit nhưng trước khi client nhận kết quả**. Đây là vấn đề *ambiguous outcome*.

### 4.1. Minh họa mất kết nối ở thời điểm khó nhất

~~~text
Producer                              Broker
   |                                     |
   |---- SEND eventId=evt-001 ---------->|
   |                                     |-- Persist event
   |                [network breaks]     |
   X<--- ACK/response không tới --------|
   |
   +-- Producer báo timeout/exception
   +-- Không biết event đã tồn tại chưa
   +-- Retry eventId=evt-001
                 |
                 +--> Broker có thể nhận thêm một lần gửi
~~~

Nếu producer tạo `eventId` mới ở mỗi retry, consumer gần như không thể biết hai sự kiện tương đương. Dùng **ID nghiệp vụ ổn định** là điều kiện tiên quyết cho deduplication. Một số provider, như Artemis, có cơ chế duplicate detection riêng, nhưng đó là tính năng **cần cấu hình/áp dụng đúng**, không tự động xuất hiện chỉ vì đặt `PERSISTENT`.

### 4.2. Kết quả mơ hồ của commit

Tương tự, khi gọi `Session.commit()`:
- Nếu nhận thông báo commit thành công, có căn cứ transaction JMS đã hoàn tất theo contract và cấu hình.
- Nếu client mất kết nối **giữa lúc gửi commit và lúc nhận phản hồi**, không thể biết chắc broker đã commit hay rollback chỉ dựa vào exception.
- Retry toàn bộ nghiệp vụ mà không có event ID/idempotency có thể tạo duplicate nghiệp vụ.

Kỹ thuật phù hợp tùy yêu cầu: kiểm tra trạng thái theo ID, transactional outbox cho DB→message, deduplication ở consumer và broker duplicate detection nếu được hỗ trợ.

## 5. Consumer: persistent không thay thế ACK hoặc transaction

### 5.1. Vì sao nhận được message chưa đồng nghĩa xử lý xong?

Consumer thường làm nhiều việc:

~~~text
Broker -> Consumer.receive()
           |
           +--> Validate payload
           +--> Ghi dữ liệu vào DB
           +--> Gọi dịch vụ bên ngoài
           +--> Acknowledge hoặc commit JMS
~~~

Nếu thứ tự ACK và side effect không được quản lý cẩn thận:

| Kịch bản | Diễn biến | Hệ quả |
| --- | --- | --- |
| ACK sớm | Consumer acknowledge trước, DB write sau, rồi process crash | Broker có thể không phát lại; tác vụ DB bị mất |
| DB commit trước, ACK sau | DB ghi thành công, process crash trước ACK | Broker có thể redeliver; DB side effect có nguy cơ lặp |
| JMS transaction rollback | Listener lỗi trước `commit()`, session rollback | Message chưa hoàn tất và có thể được giao lại |
| Redelivery liên tục | Payload độc hoặc DB luôn lỗi, listener rollback mãi | Backlog/tăng retry; cần DLQ và giới hạn lần thử |
| AUTO_ACKNOWLEDGE trong listener container | ACK semantics phụ thuộc container/provider và thời điểm callback | Không mặc nhiên bảo đảm “xử lý DB xong rồi mới ACK chắc chắn” |

Jakarta Messaging cung cấp session transaction và acknowledge modes. Spring JMS cung cấp listener container với cấu hình transaction; **không nên chỉ đổi delivery mode phía producer rồi coi consumer reliability đã được xử lý**.

### 5.2. Local JMS transaction và phạm vi của nó

Một consumer dùng Jakarta JMS thuần có thể xử lý trong session transacted:

~~~java
// Snippet trong code đã có Connection, Queue và quyền consume.
try (Session session = connection.createSession(Session.SESSION_TRANSACTED);
     MessageConsumer consumer = session.createConsumer(queue)) {

    connection.start();
    Message message = consumer.receive(5_000L);

    if (message != null) {
        try {
            // Thực hiện xử lý có thể ném lỗi.
            processMessage(message);
            session.commit();  // Commit JMS local transaction.
        } catch (Exception ex) {
            session.rollback(); // Cho phép JMS recovery/redelivery.
            throw ex;
        }
    }
}
~~~

Đoạn này **không độc lập**: các biến `connection`, `queue`, phương thức `processMessage` phải tồn tại trong ứng dụng, cùng imports `jakarta.jms.*`. Mục đích là minh họa nơi gọi `commit/rollback`. **Local JMS transaction không tự động quản lý database transaction**: nếu `processMessage` đã commit DB rồi JMS `commit` thất bại, message có thể được nhận lại.

Với Spring `DefaultMessageListenerContainer`, bật `sessionTransacted=true` để rollback JMS khi listener ném exception. Trong môi trường có Spring transaction manager bên ngoài, phải xem xét tương tác với transaction manager, caching, session ownership và cách listener container được cấu hình.

### 5.3. Redelivery là tín hiệu, không phải ID chống trùng

Khi provider giao lại message chưa xử lý hoàn tất, header `JMSRedelivered` được đánh dấu và thuộc tính `JMSXDeliveryCount` tăng theo yêu cầu đặc tả. Chúng hữu ích để log, điều chỉnh retry và vận hành.

Nhưng **không** dùng `JMSRedelivered=false` để kết luận “chưa từng thực hiện side effect”; sự cố commit DB/JMS có thể xảy ra ngoài phạm vi thông tin này. Và `JMSMessageID` thường định danh **mỗi JMS send**, không nhất thiết định danh **một thao tác nghiệp vụ qua nhiều lần producer retry**. Dùng `eventId` hoặc `commandId` riêng ổn định.

## 6. Giới hạn thực tế của broker storage và HA

Một queue chứa persistent messages có thể khôi phục sau broker restart **chỉ khi cấu hình, dữ liệu và tài nguyên cần thiết thực sự tồn tại**. Không đánh đồng một bit delivery mode với thiết kế storage tổng thể.

### 6.1. Với Apache ActiveMQ Artemis

Artemis hỗ trợ **file journal** hoặc **JDBC store** cho persistence; journal mặc định là dạng append-only. Những điểm cần kiểm tra trong cấu hình thực tế:

| Cấu hình/vấn đề | Vì sao quan trọng |
| --- | --- |
| `persistence-enabled` | Broker có bật chế độ lưu bền hay không |
| Durable queue / durable subscription | Message có được lưu và giữ cho đúng destination/subscriber hay không |
| `journal-sync-non-transactional` | Với send/ack không dùng transaction, có đồng bộ journal trước khi xác nhận theo chính sách |
| `journal-sync-transactional` | Với transaction, có đồng bộ dữ liệu commit/rollback trước khi phản hồi |
| `journal-datasync` và loại journal | Độ bền trước process crash so với power failure; phụ thuộc filesystem/OS |
| Storage volume/replication/HA | Dữ liệu có còn truy cập sau container/máy chủ/disk failure không |
| Address full policy, disk/memory limits, paging | Broker xử lý thế nào khi cạn tài nguyên hoặc backlog lớn |
| Message expiry, dead-letter, purge policy | Những lý do message có thể bị loại không do broker crash |

Tài liệu *Guarantees of Sends and Commits* của Artemis mô tả: với durable message trên **ít nhất một durable queue**, send không transaction và `journal-sync-non-transactional=true`, broker xác nhận sau khi persist theo cơ chế tương ứng. Cấu hình `blockOnDurableSend` của Core client quyết định có chờ phản hồi cho durable send hay không. Các mặc định và khả năng tương thích phải xác minh với **phiên bản và client protocol** đang sử dụng.

**Điều này không bảo đảm mọi hardware failure:** nếu volume bị xóa, snapshot thiếu dữ liệu, controller/disk báo ghi thành công nhưng thực tế lỗi, replication không đúng hoặc HA failover cấu hình sai thì không thể suy ra không mất dữ liệu chỉ từ `PERSISTENT`.

### 6.2. Container và storage ephemeral

Một broker chạy bằng container **không gắn persistent volume**, sau khi container bị xóa và tạo lại có thể mất journal. Điều đó khác với việc restart **cùng broker instance trên cùng vùng lưu trữ**. Để thử durability sau restart một cách có ý nghĩa:

1. Chọn broker test; xác minh persistence bật và queue durable đã tạo.
2. Xác định **đường dữ liệu thực** và volume bền vững.
3. Gửi persistent message, **chưa nhận/ACK**.
4. Restart broker theo quy trình vận hành; **không xóa journal/volume**.
5. Kết nối lại và nhận message đúng event ID.
6. Ghi lại broker version, storage setting, kết quả và logs.

Không thực hiện `docker rm`/xóa volume rồi mong message phục hồi. Không áp dụng quy trình phá hoại lên production queue.

### 6.3. Availability khác durability

- **Durability:** dữ liệu đã được cam kết lưu có thể khôi phục theo hợp đồng.
- **Availability:** dịch vụ có thể gửi/nhận tại thời điểm cần thiết.
- **RPO:** mức dữ liệu chấp nhận mất trong kịch bản disaster/failover.
- **RTO:** thời gian phục hồi dịch vụ.
- **Correctness:** xử lý nghiệp vụ không thiếu/lặp/hỏng dữ liệu.

Một broker single-node có disk bền vẫn có thể **không sẵn sàng trong nhiều phút/giờ** sau sự cố. Ngược lại, cluster hoạt động trở lại rất nhanh không tự động chứng minh RPO=0 nếu chính sách replication/ack chưa đủ. Phải thiết kế HA, backup, phục hồi và test theo mức rủi ro thực.

## 7. Ví dụ chạy được: persistent gửi/nhận trên Spring Boot

Dùng **Java 17**, **Spring Boot 3.3.5**, **ActiveMQ Artemis client** và `JmsTemplate`. Ví dụ tách thành hai chế độ chạy **send** và **receive** để bạn có thể khởi động lại broker giữa hai lần chạy. Nó kiểm tra tầng JMS, **không giả vờ chứng minh exactly-once database**.

**Điều kiện tiên quyết:** có Artemis broker tại `tcp://localhost:61616`, credential `demo/demo`, đã provision queue **durable anycast** tên `demo.durable` với quyền send/consume, broker bật persistence và lưu dữ liệu trên volume bền. Nếu broker cho phép auto-create queue, vẫn nên kiểm tra queue được tạo **durable**. Giá trị `demo/demo` chỉ là ví dụ local; không sử dụng trong production. Demo không cung cấp Docker command phá hủy dữ liệu vì thư mục volume có thể khác theo image/bản cài.

### 7.1. Cấu trúc dự án

~~~text
persistent-jms-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/PersistentProbeApplication.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'persistent-jms-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
~~~

`src/main/resources/application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: demo
    password: demo
~~~

Ở môi trường thật dùng `SPRING_ARTEMIS_USER`, `SPRING_ARTEMIS_PASSWORD` và `SPRING_ARTEMIS_BROKER_URL` hoặc secret management để thay các giá trị demo; không commit mật khẩu thật.

### 7.2. Chương trình Java độc lập trong project

`src/main/java/demo/PersistentProbeApplication.java`:

~~~java
package demo;

import java.util.List;
import java.util.UUID;

import jakarta.jms.DeliveryMode;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class PersistentProbeApplication {

    private static final String QUEUE = "demo.durable";

    public static void main(String[] args) {
        SpringApplication.run(PersistentProbeApplication.class, args);
    }

    @Bean
    ApplicationRunner probe(JmsTemplate template) {
        return args -> {
            String mode = option(args, "probe.mode", "send");
            String eventId = option(
                    args, "probe.id", UUID.randomUUID().toString());

            // ID an toàn cho JMS selector và dễ liên kết logs.
            if (!eventId.matches("[A-Za-z0-9._-]{1,80}")) {
                throw new IllegalArgumentException("Invalid probe.id");
            }

            if ("send".equals(mode)) {
                // Chỉ cấu hình một lần cho chương trình demo một luồng.
                template.setExplicitQosEnabled(true);
                template.setDeliveryMode(DeliveryMode.PERSISTENT);
                template.setTimeToLive(0L); // Không hết hạn theo TTL.

                template.convertAndSend(
                        QUEUE,
                        "event:" + eventId,
                        message -> {
                            message.setStringProperty("eventId", eventId);
                            return message;
                        });

                // In sau khi lời gọi send trở về bình thường.
                System.out.println("SEND_RETURNED eventId=" + eventId);
                return;
            }

            if ("receive".equals(mode)) {
                template.setReceiveTimeout(5_000L);
                String selector = "eventId = '" + eventId + "'";
                Message message = template.receiveSelected(QUEUE, selector);

                if (message == null) {
                    System.out.println(
                            "NO_MESSAGE_WITHIN_5000MS eventId=" + eventId);
                    return;
                }

                if (!(message instanceof TextMessage text)) {
                    throw new IllegalStateException(
                            "Expected TextMessage");
                }

                String expectedBody = "event:" + eventId;
                if (!expectedBody.equals(text.getText())) {
                    throw new IllegalStateException(
                            "Unexpected message body");
                }
                if (message.getJMSDeliveryMode()
                        != DeliveryMode.PERSISTENT) {
                    throw new IllegalStateException(
                            "Unexpected delivery mode");
                }

                System.out.println(
                        "RECEIVE_OK eventId=" + eventId
                        + " body=" + text.getText()
                        + " mode=PERSISTENT");
                return;
            }

            throw new IllegalArgumentException(
                    "probe.mode must be send or receive");
        };
    }

    private static String option(
            ApplicationArguments args,
            String name,
            String fallback) {
        List<String> values = args.getOptionValues(name);
        if (values == null || values.isEmpty()
                || values.get(0) == null
                || values.get(0).isBlank()) {
            return fallback;
        }
        return values.get(0);
    }
}
~~~

**Vì sao đây là ví dụ phù hợp?**

1. `JmsTemplate` do Spring Boot cấu hình từ `ConnectionFactory` Artemis, không yêu cầu tự quản lý Session/Connection thủ công.
2. `setExplicitQosEnabled(true)` buộc template truyền QoS đã đặt cho producer send; nếu không, `setDeliveryMode` trên template không được chủ động áp dụng theo cách mong muốn.
3. `DeliveryMode.PERSISTENT` yêu cầu provider sử dụng persistent delivery; `timeToLive=0` nghĩa là không hết hạn **theo JMS TTL**, chứ không vô hiệu hóa retention/quota.
4. `eventId` được ghi thành message property và selector ở consumer để nhận chính xác message thử, tránh nhận nhầm message cũ.
5. `send` và `receive` là **hai lần chạy tách biệt**, nhờ vậy có thể restart broker sau send mà không vô tình ACK/consume message.
6. Sau `SEND_RETURNED`, broker vẫn có thể chưa giao message cho consumer; chương trình cố ý không tuyên bố “ORDER_PROCESSED”.
7. `receiveSelected` là cách nhận đồng bộ cho demo; với ứng dụng thật, nên dùng listener có transaction/acknowledgement được thiết kế rõ ràng.

Trong chương trình demo đơn luồng, các setter trên `JmsTemplate` đặt một lần rồi dùng. **Không chỉnh delivery mode/priority/TTL của singleton JmsTemplate theo từng HTTP request** trong ứng dụng concurrent; các request có thể làm nhiễu cấu hình của nhau.

### 7.3. Chạy: send trước, receive sau

Tại thư mục dự án với JDK 17+, Gradle và broker đã sẵn sàng:

~~~bash
gradle bootRun --args="--probe.mode=send --probe.id=evt-1001"
~~~

Với broker và quyền send hợp lệ, dòng ứng dụng in ra:

~~~text
SEND_RETURNED eventId=evt-1001
~~~

Không chạy consumer vội nếu muốn kiểm tra restart. Trên broker test, xác minh queue `demo.durable` tồn tại/durable và message còn pending; sau đó restart **cùng instance, giữ nguyên journal và volume** theo công cụ vận hành. Khi broker đã sẵn sàng:

~~~bash
gradle bootRun --args="--probe.mode=receive --probe.id=evt-1001"
~~~

Nếu message còn nguyên trong queue và user có quyền consume:

~~~text
RECEIVE_OK eventId=evt-1001 body=event:evt-1001 mode=PERSISTENT
~~~

Spring Boot/Artemis có thể in thêm log. Nếu chỉ thấy `NO_MESSAGE_WITHIN_5000MS`, không vội kết luận persistent “không hoạt động”: kiểm tra queue durability, broker instance, journal volume, expiration, selector, tài khoản, competing consumers, message đã ack từ lần chạy khác và chính sách quản trị. Nếu chạy receive lần hai cùng ID, message có thể đã được xác nhận/tiêu thụ ở lần đầu, nên lần hai timeout là hành vi bình thường.

**Giới hạn của phép thử:** nó có thể cho thấy message sống sót qua một lần restart có kiểm soát. Nó **không** mô phỏng disk loss, crash giữa journal write và response, network partition, DB transaction, consumer rollback hay tính exactly-once end-to-end.

### 7.4. Bài thử đối chứng: đâu là bằng chứng thực sự?

| Thử nghiệm | Cách tiến hành | Kết luận tối đa |
| --- | --- | --- |
| Persistent, chưa receive, restart giữ volume | Gửi `evt-1001`, restart broker, nhận đúng ID | Với điều kiện test, broker phục hồi message chưa tiêu thụ |
| Gửi `NON_PERSISTENT` rồi restart | Thay mode trong **bản thử riêng** | Message có thể mất; không bắt buộc phải mất trong mọi lần thử |
| Gửi persistent rồi purge queue | Quản trị viên purge queue **test** | Persistent không bảo vệ trước administrative deletion |
| Gửi persistent có TTL rất ngắn | Đặt TTL trước send, đợi quá hạn | Message có thể bị loại vì expiration |
| Gửi đến topic không có durable subscriber đang hoạt động | Publish rồi đăng ký subscriber sau | Persistent không cứu message đã bỏ lỡ của non-durable subscription |
| Crash consumer sau DB commit, trước JMS ACK | Integration test riêng với DB/test queue | Redelivery có thể gây side effect trùng nếu không idempotent |
| Crash producer sau DB commit, trước send | Integration test riêng DB + outbox | Persistent không thể bảo vệ event chưa được publish |
| Mất response sau broker nhận send | Tạo failure injection ở môi trường test | Producer phải xử lý ambiguous outcome; không thể suy từ exception rằng broker không có message |

Không thử purge, xóa volume hoặc kill broker trong môi trường production. Với non-persistent mode, việc một message **vẫn còn** sau restart **không phải lỗi**; hợp đồng cho phép provider lưu tốt hơn mức tối thiểu.

## 8. Lỗ hổng DB → JMS: transactional outbox

Một tình huống điển hình:

~~~text
BEGIN DB TRANSACTION
  UPDATE orders SET status='PAID'
COMMIT DB
      |
      X Process chết trước jmsTemplate.convertAndSend(...)
      |
      +--> DB: PAID
      +--> Broker: KHÔNG CÓ event
~~~

`PERSISTENT` chỉ áp dụng **khi đã gửi message**; nó không can thiệp được vào khoảng trống giữa DB commit và producer send.

### 8.1. Cấu trúc outbox

Giải pháp phổ biến là viết **dữ liệu nghiệp vụ và bản ghi outbox trong cùng DB transaction**:

~~~sql
-- Ví dụ PostgreSQL, minh họa lược đồ tối thiểu.
CREATE TABLE outbox_event (
    event_id       VARCHAR(80) PRIMARY KEY,
    event_type     VARCHAR(100) NOT NULL,
    payload_json   TEXT NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at   TIMESTAMPTZ NULL
);
~~~

Luồng ghi:

~~~text
Order Service / DB transaction
  |
  +-- UPDATE orders ...
  +-- INSERT outbox_event(event_id, event_type, payload_json)
  +-- COMMIT --> cả order và outbox cùng tồn tại
                    |
                    v
       Outbox relay (polling/CDC)
          |
          +-- Publish persistent JMS message, eventId cố định
          +-- Đánh dấu published_at sau khi nhận kết quả đủ tin cậy
          +-- Retry khi lỗi hoặc trạng thái mơ hồ
                    |
                    v
             JMS broker / Queue
~~~

Relay có thể gửi lại nếu broker đã nhận message nhưng relay chết trước khi đánh dấu published. **Outbox không tự đạt exactly-once delivery**. Nó bảo vệ sự kiện khỏi việc “DB commit nhưng không có bản ghi để gửi”, đổi lại phải thiết kế **at-least-once publishing + idempotent consumer** hoặc một cơ chế deduplication tương đương.

### 8.2. Chi tiết không được bỏ qua

- `event_id` được tạo một lần cho **logical business event**, không tạo lại mỗi lần relay retry.
- Dùng khóa, lease hoặc cơ chế claim thích hợp để nhiều relay không cùng phát một outbox event ngoài ý muốn.
- Không đánh dấu outbox `published` **trước** khi send/commit JMS thành công theo mức xác nhận đã chọn.
- Đặt giới hạn retry/backoff, retention của outbox, cảnh báo backlog và khả năng khôi phục khi relay chết.
- Nếu payload thay đổi sau khi DB commit, relay cần đọc **snapshot đã ghi trong outbox** chứ không tái tạo thiếu nhất quán từ DB.
- Khi cần nhiều broker/destination, thiết kế trạng thái phát riêng cho từng mục tiêu hoặc chiến lược reconciliation.

Spring `@Transactional` trên DB không tự động gộp transaction JDBC với JMS. Muốn transaction phân tán cần hạ tầng XA/JTA và cấu hình chuẩn; nhiều hệ thống ưu tiên outbox vì đơn giản vận hành hơn, nhưng lựa chọn phải cân nhắc yêu cầu nhất quán và platform.

## 9. Lỗ hổng JMS → DB: idempotent consumer

Một cửa sổ lỗi khác:

~~~text
Broker phát eventId=evt-1001
  |
Consumer BEGIN DB
  |-- INSERT payment_transaction ...
  |-- COMMIT DB (thành công)
  |
  X Consumer chết / mất mạng trước JMS ACK/COMMIT
  |
Broker thấy message chưa hoàn tất
  |-- Redeliver evt-1001
  |
Consumer chạy lại
  |-- Nếu không chống trùng: có thể tạo side effect thêm lần nữa
~~~

Giải pháp thông dụng: lưu lại `eventId` đã xử lý trong **cùng DB transaction với side effect**. Mô hình PostgreSQL minh họa:

~~~sql
CREATE TABLE processed_message (
    consumer_name VARCHAR(100) NOT NULL,
    event_id      VARCHAR(80) NOT NULL,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Pseudo-flow chuẩn cần được hiện thực hóa trong service:

~~~text
Khi JMS listener nhận event:
    BEGIN DB TRANSACTION
        INSERT INTO processed_message(consumer_name, event_id)
        ON CONFLICT DO NOTHING

        Nếu có dòng mới:
            Thực hiện UPDATE/INSERT nghiệp vụ
        Nếu eventId đã tồn tại:
            Bỏ qua side effect (coi là đã xử lý)
    COMMIT DB
    Sau đó hoàn tất JMS ACK / JMS COMMIT

Nếu DB thất bại:
    ROLLBACK DB
    ROLLBACK hoặc không ACK JMS để cho phép redelivery
~~~

**Lưu ý:** việc INSERT dedupe và cập nhật nghiệp vụ phải **cùng một transaction DB**; nếu chỉ ghi flag “đã xử lý” mà side effect nằm ngoài transaction, crash có thể khiến message bị bỏ qua dù tác vụ chưa hoàn thành. Với các lệnh gọi API bên ngoài, hãy cân nhắc idempotency key của bên nhận hoặc một saga/state machine để tránh side effect lặp.

### 9.1. Trong Spring JMS listener

Spring hỗ trợ listener container với **local JMS transaction**, chẳng hạn `sessionTransacted=true` trên `DefaultJmsListenerContainerFactory`/container. Nếu method listener ném exception, JMS transaction có thể rollback, message được redeliver theo policy; nhưng **DB transaction của Spring Data/JDBC không tự nằm trong cùng JMS transaction đó**.

Trong ứng dụng dùng JMS và DB, cần xác định thứ tự commit, exception propagation, transaction manager và xử lý trường hợp “DB commit xong, JMS commit chưa xong”. Idempotent consumer giúp giảm rủi ro duplicate side effect khi redelivery.

### 9.2. Không coi flag redelivery là cơ chế chống trùng

`JMSRedelivered` và `JMSXDeliveryCount` dùng để nhận diện các lần giao lại của cùng message, nhưng không đủ:
- Một producer retry có thể tạo **message mới** mang business event giống hệt mà cả hai đều có `JMSRedelivered=false`.
- Một message đã từng gây side effect có thể được phát lại sau timeout hoặc rollback.
- Các property broker-specific và số lần nhận không thay thế khóa `eventId` nghiệp vụ.

Dedupe ID nên thuộc **domain/event contract** và được giữ nguyên qua retry phía producer.

## 10. Retry, DLQ và retention phải có chiến lược riêng

Persistent message **không** giải quyết poison message (payload luôn làm consumer lỗi). Nếu listener cứ rollback, broker có thể redeliver nhiều lần:

~~~text
Queue
  |
  +--> Consumer nhận -> lỗi -> rollback
  |                     |
  +<--------------------+
  |
  +--> Sau N lần theo broker policy -> Dead Letter Queue
~~~

Cần cấu hình theo broker:
- Giới hạn số lần giao lại và delay/backoff, tránh vòng lặp nóng.
- Dead-letter address/queue phù hợp, quyền truy cập và cảnh báo.
- Phân loại lỗi tạm thời (DB timeout) và lỗi dữ liệu vĩnh viễn (schema/payload sai).
- Có thao tác reprocess an toàn với idempotency key ổn định.
- Giới hạn tuổi message, kích thước queue, disk capacity và chính sách expiry rõ ràng.

**DLQ không phải nơi lưu vô hạn.** Nó cũng có TTL/quota/cleanup; nếu muốn audit lâu dài, cần lưu dữ liệu nghiệp vụ/đối soát ở một hệ thống thích hợp. Message ở DLQ không đồng nghĩa đã được xử lý thành công.

## 11. Vì sao “PERSISTENT + TTL=0” vẫn có thể không thấy message?

Chọn `PERSISTENT`, TTL `0` và gọi `send` thành công có thể vẫn khiến consumer không thấy message mong đợi do:

| Nguyên nhân | Cách xác minh |
| --- | --- |
| Gửi sai destination hoặc routing type | Kiểm tra exact address/queue, anycast/multicast và broker thực |
| Topic chỉ có non-durable subscriber đã offline | Kiểm tra durable subscription và client/subscription identity |
| Broker policy xóa/purge hoặc move message | Kiểm tra audit log, expiry address, DLQ, retention policy |
| Consumer khác đã nhận/ACK message | Kiểm tra consumer count, queue browse/metrics, application logs |
| Selector không khớp property/type | Kiểm tra selector và property được ghi lúc send |
| Producer send nằm trong transaction chưa commit | Kiểm tra transaction boundary; commit thành công trước khi kết luận |
| Broker storage bị xóa/không bền | Kiểm tra volume, journal, backup, logs và restart procedure |
| Disk full/quota hoặc flow-control | Kiểm tra address full policy, paging, quota, broker alerts |
| Receive timeout quá ngắn | Đo backlog/latency, kiểm tra listener đang start và quyền consume |
| Provider/broker gặp lỗi sau khi ứng dụng báo OK theo config async | Kiểm tra send acknowledgement policy và journal sync |

Một `receive(timeout)` trả `null` **không** đủ để kết luận “JMS persistent thất bại”. Chỉ khi biết đúng message ID, đúng broker/destination, trạng thái journal, tình trạng consumer và thời điểm gửi, ta mới có cơ sở phân tích.

## 12. Checklist thiết kế độ tin cậy đầu-cuối

Trước khi tuyên bố “sự kiện không bị mất và không xử lý trùng”, hãy trả lời được các câu hỏi sau:

### Producer
- [ ] Sự kiện được sinh ra trước hay sau DB commit? Có **outbox** hoặc giải pháp nhất quán khác?
- [ ] Mỗi sự kiện có `eventId` ổn định qua retry không?
- [ ] Producer đã chọn `PERSISTENT` và kiểm tra mode thực tế chưa?
- [ ] Nếu dùng `JmsTemplate.setDeliveryMode(...)`, đã bật `setExplicitQosEnabled(true)` chưa?
- [ ] Send có đồng bộ xác nhận đúng mức không? Nếu bị timeout, xử lý **ambiguous outcome** thế nào?
- [ ] Có retry/backoff, rate limit, alert, tracing và chính sách khôi phục sau restart?

### Broker
- [ ] Destination là durable queue hoặc durable topic subscription phù hợp?
- [ ] Persistence thực sự bật; journal/JDBC store và fsync/sync config đã kiểm tra?
- [ ] Storage dùng volume/đĩa bền; sao lưu, phục hồi và quyền truy cập được vận hành an toàn?
- [ ] RPO/RTO, HA/failover được đo trong failure injection test?
- [ ] Disk quota, address full policy, paging, TTL, retention, purge và DLQ được quản lý?
- [ ] Có metric queue depth, oldest message age, expired/removed count, journal/disk health?

### Consumer
- [ ] Dùng ACK/transaction theo mức reliability cần thiết thay vì phụ thuộc vào persistent mode?
- [ ] DB side effect và bảng dedupe được commit nguyên tử trong DB?
- [ ] Lỗi consumer có rollback/không ACK phù hợp; exceptions có được propagate?
- [ ] Duplicate business event được nhận diện bằng `eventId` ổn định?
- [ ] Retry/DLQ không tạo vòng lặp, có alert và cơ chế replay an toàn?
- [ ] Có test crash sau DB commit nhưng trước JMS ACK/commit?

### Vận hành
- [ ] Kết quả test restart broker **giữ journal** đã được ghi lại?
- [ ] Có test message chưa nhận và message đang xử lý khi consumer crash?
- [ ] Có phân biệt process crash, power failure, disk loss và site failure?
- [ ] Có dashboard end-to-end: outbox lag, send failure, queue age, redelivery, duplicate count, consumer lag và DLQ?
- [ ] Nhóm vận hành biết khi nào phải đối soát hoặc tái phát hành message theo event ID?

## 13. Câu hỏi tự kiểm tra

1. Vì sao `DeliveryMode.PERSISTENT` không giúp khi database commit đã thành công nhưng chương trình chết trước lần gọi `convertAndSend`?
2. Theo Jakarta Messaging, once-and-only-once của persistent message áp dụng cho **provider delivery** hay cho side effect của database ứng dụng?
3. Hai lần producer gửi cùng `orderId` sau timeout có thể tạo hai message hợp lệ không? Làm sao consumer nhận diện trùng nghiệp vụ?
4. Vì sao message persistent vẫn có thể bị loại khi TTL hết hạn hoặc admin purge queue?
5. Vì sao topic non-durable subscription có thể bỏ lỡ message được publish bằng persistent mode khi subscriber offline?
6. Vì sao local JMS transaction không mặc nhiên bảo vệ transaction của PostgreSQL?
7. Trong trình tự “DB commit → crash → chưa JMS ACK”, vì sao broker có thể giao lại và làm sao ngăn DB update lần hai?
8. `journal-sync-non-transactional`, `blockOnDurableSend` và persistent queue liên quan thế nào đến mức chắc chắn khi `send` trả về?
9. Restart broker bằng cách xóa container và volume có phải bài test đúng cho khả năng khôi phục message không?
10. Nếu một hệ thống cần cam kết không mất command và không thực hiện tác vụ hai lần, ngoài persistent mode phải thiết kế những thành phần nào?

**Ghi nhớ:** `PERSISTENT` bảo vệ message **trong hợp đồng giao của JMS provider** dưới những điều kiện rõ ràng. Nó không tạo transaction xuyên DB–broker, không thay thế ACK/commit, không giải quyết kết quả send mơ hồ và không loại bỏ duplicate side effect. Để nâng độ tin cậy đầu-cuối, phải phối hợp **durable destination + broker persistence/HA + send acknowledgement + transaction/ACK + stable event ID + idempotency + outbox + retry/DLQ + observability** theo mức rủi ro thực tế.

## Tài liệu tham khảo

1. Jakarta Messaging 3.1 Specification — `7.7 Message delivery mode`, `9.1 Reliability` và `6.2.9 Sessions/Commit`: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
2. Apache ActiveMQ Artemis — *Persistence* (journal, JDBC store, sync): https://artemis.apache.org/components/artemis/documentation/latest/persistence
3. Apache ActiveMQ Artemis — *Guarantees of Sends and Commits*: https://artemis.apache.org/components/artemis/documentation/latest/send-guarantees.html
4. Spring Framework — *Using Spring JMS* (JmsTemplate, transaction management): https://docs.spring.io/spring-framework/reference/integration/jms/using.html
5. Spring Framework — *Receiving a Message* (transacted listener containers): https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html
6. Spring Boot 3.3 — *JMS and ActiveMQ Artemis*: https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html
