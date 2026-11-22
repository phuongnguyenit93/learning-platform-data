# Delivery delay và thời điểm giao sớm nhất trong Spring JMS

## 1. Delivery delay giải quyết vấn đề gì?

Trong hệ thống bất đồng bộ, đôi khi producer cần **gửi message ngay bây giờ nhưng chưa cho consumer nhận ngay**. Ví dụ: sau khi gửi email xác nhận, ứng dụng muốn chờ 10 giây rồi mới kiểm tra trạng thái; sau khi tạo đơn hàng, hệ thống muốn phát lệnh nhắc thanh toán sau vài phút; một công việc có thể được xếp hàng trước khi cửa sổ xử lý mở.

**Delivery delay** là khoảng thời gian tối thiểu (mili giây) từ lúc gửi message đến lúc provider **được phép** cung cấp message cho consumer. Đặc tính này là một phần của JMS 2.0, tiếp tục có trong Jakarta Messaging 3.x. Nó hỗ trợ lập lịch tương đối mà không bắt producer giữ kết nối, gọi `Thread.sleep(...)` rồi mới gửi.

Điểm cần nhớ nhất:

> **Thời điểm giao sớm nhất không phải thời điểm xử lý chính xác.** Sau mốc đó, message chỉ *đủ điều kiện* được giao; consumer có thể nhận muộn hơn vì tải broker, thứ tự ưu tiên, backlog, transaction, network, scheduler, throttling hoặc consumer đang offline.

Bài học thuộc nhóm **Chất lượng gửi** trong Spring Framework – JMS. Sau bài này bạn sẽ hiểu:
- Delivery delay khác gì với time-to-live (TTL), expiration, priority, redelivery delay và job scheduler.
- Ý nghĩa header `JMSDeliveryTime`; cách tính mốc sớm nhất khi gửi, kể cả trong transaction.
- Cách dùng `MessageProducer.setDeliveryDelay(...)`, `JMSProducer.setDeliveryDelay(...)` và `JmsTemplate.setDeliveryDelay(...)`.
- Cách cấu hình delay ổn định và delay thay đổi theo từng message mà không làm hỏng singleton `JmsTemplate`.
- Cách kiểm chứng bằng ví dụ Java 17, Spring Boot, Artemis và các tình huống lỗi thường gặp.

## 2. Phân biệt bốn mốc thời gian

Giả sử một message được **gửi** lúc 10:00:00.000 và producer thiết lập:

~~~text
deliveryDelay = 5_000 ms
timeToLive    = 12_000 ms

10:00:00.000            10:00:05.000             10:00:12.000
     |                        |                         |
  GỬI MESSAGE           ĐƯỢC PHÉP GIAO             HẾT HẠN
     |------------------------|-------------------------|
       chưa được deliver         có thể được deliver
       cho consumer              (nếu còn tồn tại)

Provider có thể giao lúc 10:00:05.100 hoặc 10:00:07.000...
nhưng không được giao trước 10:00:05.000.
~~~

| Khái niệm | Giá trị/ý nghĩa | Liên quan header |
|---|---|---|
| **Send time** | Thời điểm provider/client gửi message theo quy tắc JMS. | `JMSTimestamp` thường ghi timestamp gửi, nhưng có thể bị disable. |
| **Delivery delay** | Độ trễ tối thiểu, ví dụ 5.000 ms. | Thiết lập trên `MessageProducer` hoặc `JMSProducer`, không phải một field tùy ý trên payload. |
| **Earliest delivery time** | Send time + delay, ví dụ 10:00:05.000. | `JMSDeliveryTime` chứa thời điểm này dưới dạng epoch milliseconds. |
| **Expiration time** | Send time + TTL, ví dụ 10:00:12.000; TTL=0 biểu thị không hết hạn theo TTL. | `JMSExpiration` là epoch milliseconds, hoặc 0 nếu TTL=0. |

**Công thức với TTL dương:**

~~~text
earliestDeliveryTime = sendTime + deliveryDelay
expirationTime       = sendTime + timeToLive
availableWindow      = [earliestDeliveryTime, expirationTime)
~~~

Dấu khoảng trong công thức chỉ thể hiện *cửa sổ thời gian có thể giao*, không có nghĩa broker bảo đảm sẽ giao trong cửa sổ. Với TTL=0, `JMSExpiration=0`; không có expiration do TTL, nhưng vẫn có chính sách quản trị khác như quota, retention, DLQ hoặc xóa message.

**Nguy cơ rất quan trọng:** nếu `timeToLive <= deliveryDelay` và TTL dương, message có thể **hết hạn trước hoặc đúng lúc nó đủ điều kiện được nhận**. Ví dụ delay=10 giây, TTL=3 giây: message có thể hết hạn ở giây thứ ba trong khi phải chờ tới giây thứ mười. Đây không phải lỗi của scheduler; đó là cấu hình mâu thuẫn.

### Delivery delay dùng mốc tương đối

`setDeliveryDelay(5_000L)` nghĩa là chờ ít nhất 5 giây kể từ *send time*, **không** phải “hẹn gửi lúc 5 giờ chiều”. Khi bài toán yêu cầu một lịch cố định theo múi giờ (ví dụ ngày làm việc tiếp theo lúc 08:00 Asia/Ho_Chi_Minh), nên tính khoảng trì hoãn từ đồng hồ hệ thống đáng tin cậy, kiểm tra DST/múi giờ và thời gian tối đa broker cho phép; với nghiệp vụ phức tạp nên dùng scheduler/outbox/workflow engine thay vì giả định JMS tương đương một dịch vụ lịch nghiệp vụ.

## 3. Hợp đồng chuẩn Jakarta Messaging

### 3.1. API cổ điển: MessageProducer.setDeliveryDelay

~~~java
import jakarta.jms.MessageProducer;
import jakarta.jms.Session;
import jakarta.jms.TextMessage;

// Mảnh mã: cần Session và MessageProducer thực từ provider.
producer.setDeliveryDelay(5_000L);
TextMessage message = session.createTextMessage("generate-invoice");
producer.send(message);
~~~

`MessageProducer` có thể cài đặt một delivery delay mặc định cho các message tiếp theo được gửi bằng producer đó. Theo Jakarta Messaging:
- Đơn vị là **mili giây**; mặc định `Message.DEFAULT_DELIVERY_DELAY=0L`.
- `setDeliveryDelay(long)` đã có từ JMS 2.0.
- Phương thức `send(message, deliveryMode, priority, timeToLive)` chỉ nhận **ba** thông số QoS bổ sung; nó **không có tham số delivery delay riêng**. Vì vậy delay được thiết lập trên producer.
- Một provider được phép có chính sách quản trị ghi đè các tùy chọn gửi; cần đọc `JMSDeliveryTime` thực tế và kiểm tra cách hoạt động của broker.

Trong ứng dụng nhiều luồng, không chia sẻ `Session`/`MessageProducer` tùy tiện. Với `JmsTemplate`, để Spring quản lý tài nguyên và giữ cấu hình template ổn định sau khi khởi tạo.

### 3.2. API đơn giản hóa: JMSContext và JMSProducer

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;

public final class SimplifiedApiExample {
    public static void schedule(ConnectionFactory factory) {
        try (JMSContext context = factory.createContext()) {
            context.createProducer()
                    .setDeliveryDelay(5_000L)
                    .send(context.createQueue("billing.invoice.jobs"),
                            "generate-invoice");
        }
    }
}
~~~

Đây là **lớp biên dịch được với Jakarta Messaging API**, nhưng cần `ConnectionFactory` và broker hỗ trợ để chạy. `JMSProducer#setDeliveryDelay(...)` trả về producer để có thể chain các thao tác, khác với `MessageProducer#setDeliveryDelay(...)` trả về `void`. `JMSContext`/`JMSProducer` có thể ném `JMSRuntimeException`, còn API cổ điển có checked `JMSException`; không nhầm với Spring `JmsException`.

### 3.3. Header JMSDeliveryTime là kết quả, không phải API lập lịch

Đọc thời gian giao sớm nhất qua:

~~~java
long earliestEpochMillis = receivedMessage.getJMSDeliveryTime();
~~~

Giá trị là số mili giây kể từ 1970-01-01T00:00:00Z; bạn có thể đổi sang `java.time.Instant` hoặc múi giờ hiển thị. Theo chuẩn, provider đặt header `JMSDeliveryTime` khi gửi; client **không dùng** `message.setJMSDeliveryTime(...)` để hẹn giờ. Các setter header do provider quản lý có thể bị ghi đè trong send.

Không dùng:
- `message.setJMSTimestamp(...)` để giả lập delay.
- `message.setJMSExpiration(...)` để hẹn thời điểm nhận.
- Một application property tự đặt tên `deliveryTime` rồi kỳ vọng provider hiểu, trừ khi bạn đã tự triển khai logic riêng.
- `Thread.sleep(5_000)` trong request HTTP để “đợi trước khi gửi”: cách này giữ thread, không xử lý tốt process crash và không còn là send-now-deliver-later.

## 4. Spring JmsTemplate hỗ trợ delivery delay thế nào?

Spring Framework 6.x có phương thức:

~~~java
JmsTemplate template = new JmsTemplate(connectionFactory);
template.setDeliveryDelay(5_000L);
template.convertAndSend("billing.invoice.jobs", "generate-invoice");
~~~

Đây là mảnh mã minh họa trong một ứng dụng có `jakarta.jms.ConnectionFactory` thật. `JmsTemplate` quản lý session/connection và gọi `MessageProducer.setDeliveryDelay(...)` trước khi gửi message. Giá trị là chính sách **cho các lần gửi dùng cùng template**.

Chi tiết dễ nhầm:
- `JmsTemplate#setDeliveryDelay(...)` mặc định là **-1**: Spring **không truyền delivery delay** xuống producer. Khi provider dùng mặc định theo chuẩn thì delay bằng 0.
- `setDeliveryDelay(0L)` là **tường minh gửi không trì hoãn**; khác với sentinel `-1` của Spring, vốn để provider tự dùng default/cấu hình quản trị.
- `setExplicitQosEnabled(true)` liên quan `deliveryMode`, `priority`, `timeToLive` của template. **Delivery delay được cấu hình riêng**; không cần bật flag đó chỉ để gọi `setDeliveryDelay`.
- Vì template được dùng lại giữa nhiều thread sau khi cấu hình, **không đổi `setDeliveryDelay(...)` theo từng request**. Tùy chỉnh bất đồng bộ như vậy có thể khiến message của service khác cũng bị trì hoãn.

### Bean cấu hình một lần

~~~java
package example.jms;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

@Configuration
public class DelayedMessagingConfiguration {
    @Bean("delayedJobsTemplate")
    JmsTemplate delayedJobsTemplate(ConnectionFactory factory) {
        JmsTemplate template = new JmsTemplate(factory);
        template.setDefaultDestinationName("billing.invoice.jobs");
        template.setDeliveryDelay(5_000L);
        return template;
    }

    @Bean("immediateJobsTemplate")
    JmsTemplate immediateJobsTemplate(ConnectionFactory factory) {
        JmsTemplate template = new JmsTemplate(factory);
        template.setDefaultDestinationName("billing.invoice.jobs");
        template.setDeliveryDelay(0L);
        return template;
    }
}
~~~

Hai bean dùng cùng `ConnectionFactory` và Queue, nhưng có **hai chính sách send ổn định khác nhau**. Service inject bằng `@Qualifier("delayedJobsTemplate")` hoặc `@Qualifier("immediateJobsTemplate")`. Nếu không đặt qualifier khi có nhiều `JmsTemplate`, dependency injection có thể mơ hồ.

Lưu ý: `setDefaultDestinationName` là tên Queue theo cấu hình `pubSubDomain=false` mặc định. Với Topic phải khai báo đúng `pubSubDomain=true`/destination tương ứng. Tên destination không tự xác định loại Queue/Topic.

## 5. Demo Spring Boot + Artemis embedded: gửi ngay, nhận sau

Ví dụ này nhằm **kiểm thử chức năng delivery delay** chứ không mô phỏng một hệ thống production. Nó dùng:
- Java 17.
- Spring Boot 3.5.16 (nhánh Spring Framework 6, phiên bản cụ thể để tái lập lab).
- Apache ActiveMQ Artemis embedded, không cần cài broker riêng.
- Một `JmsTemplate` gửi có delay và một `JmsTemplate` nhận đồng bộ có timeout.

Spring Boot 3.5.16 là bản cuối nhận OSS support của nhánh 3.5; hãy dùng nhánh còn được hỗ trợ và theo advisories khi triển khai production. Demo này dùng phiên bản cố định để có thể đọc, biên dịch và thử lại cùng môi trường.

### 5.1. Cấu trúc dự án

~~~text
jms-delivery-delay-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/jms/DeliveryDelayDemo.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-delivery-delay-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

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

    // Chỉ cần Artemis server nhúng cho ví dụ local.
    runtimeOnly 'org.apache.activemq:artemis-jakarta-server'
}
~~~

`src/main/resources/application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none
  artemis:
    mode: embedded
    embedded:
      queues: demo.delivery.delay
      persistent: false
~~~

`src/main/java/example/jms/DeliveryDelayDemo.java`:

~~~java
package example.jms;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class DeliveryDelayDemo {

    private static final long DELAY_MS = 2_000L;

    public static void main(String[] args) {
        SpringApplication.run(DeliveryDelayDemo.class, args);
    }

    @Bean
    ApplicationRunner demonstrate(ConnectionFactory connectionFactory) {
        return args -> {
            JmsTemplate sender = new JmsTemplate(connectionFactory);
            sender.setDefaultDestinationName("demo.delivery.delay");
            sender.setDeliveryDelay(DELAY_MS);

            // TTL > delay, tránh message hết hạn trước khi đến hạn giao.
            sender.setExplicitQosEnabled(true);
            sender.setTimeToLive(15_000L);

            JmsTemplate receiver = new JmsTemplate(connectionFactory);
            receiver.setReceiveTimeout(8_000L);

            long beforeSend = System.currentTimeMillis();
            sender.convertAndSend("delayed-message");

            Message received = receiver.receive("demo.delivery.delay");
            if (!(received instanceof TextMessage text)) {
                throw new IllegalStateException(
                        "No TextMessage received within 8 seconds");
            }

            long eligibleAt = text.getJMSDeliveryTime();
            long receivedAt = System.currentTimeMillis();

            if (eligibleAt < beforeSend + DELAY_MS) {
                throw new IllegalStateException(
                        "Broker did not respect requested delivery delay");
            }
            if (receivedAt < eligibleAt) {
                throw new IllegalStateException(
                        "Message delivered before JMSDeliveryTime");
            }

            System.out.println("BODY=" + text.getText());
            System.out.println("NOT_BEFORE_DELIVERY_TIME=true");
        };
    }
}
~~~

Vì `ApplicationRunner.run` có thể ném `Exception`, các lời gọi `TextMessage.getText()` và `getJMSDeliveryTime()` với checked `JMSException` ở đây hợp lệ. Chỉ có một Runner tiêu thụ Queue, không có listener cạnh tranh nên phép thử dễ tái lập. `persistent: false` là quyết định cho lab, không chứng minh khả năng lưu message qua broker restart.

### 5.2. Cách chạy

Tại thư mục dự án, cài JDK 17+ và Gradle tương thích với plugin Spring Boot đã chọn. Nếu có Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

Nếu chưa có Wrapper, với Gradle được cài sẵn:

~~~bash
gradle bootRun
~~~

Trong PowerShell, với Wrapper:

~~~powershell
.\gradlew.bat bootRun
~~~

Sau log Spring Boot/Artemis, hai dòng do ứng dụng in khi kiểm tra thành công:

~~~text
BODY=delayed-message
NOT_BEFORE_DELIVERY_TIME=true
~~~

Ứng dụng không in số mili giây tuyệt đối vì giá trị đó phụ thuộc thời gian chạy. Kiểm tra `receivedAt >= JMSDeliveryTime` bảo đảm phép đo không vi phạm mốc do provider thông báo; điều kiện `eligibleAt >= beforeSend + DELAY_MS` kiểm tra rằng header phù hợp delay yêu cầu trong lab cùng đồng hồ máy. **Không diễn giải kết quả thành bảo đảm consumer sẽ chạy đúng ở mili giây thứ 2.000**. Trong môi trường mạng nhiều máy, đồng hồ lệch có thể làm phép so sánh thời gian client/server kém chính xác; nên ưu tiên header do provider trả về và metric được đồng bộ giờ.

### 5.3. Thử biến thể để hiểu nguyên lý

- Đổi `DELAY_MS` thành `0L`: provider được phép giao ngay sau send/commit, nhưng vẫn có thể chậm.
- Đổi `sender.setTimeToLive(15_000L)` thành `sender.setTimeToLive(1_000L)` trong khi delay vẫn 2 giây: message có thể hết hạn trước khi nhận; Runner sẽ báo không có TextMessage trong timeout. Đây là **thí nghiệm cố ý tạo cấu hình không hợp lý**, không phải lỗi Gradle.
- Đổi `setDeliveryDelay` thành một giá trị lớn hơn thời gian nhận 8 giây: receive có thể trả `null` sau timeout vì message chưa đủ điều kiện; việc nhận lại sau đó phải được thực hiện bởi một lời receive khác.
- Nếu thay broker Artemis bằng provider khác, kiểm tra hỗ trợ JMS 2.0 delivery delay và policy của provider trước khi thử; **có API method không bảo đảm implementation hỗ trợ**.

## 6. Bài Java 17 độc lập: kiểm tra cửa sổ thời gian

Có thể học chính xác mối quan hệ giữa delivery delay và TTL mà **không cần broker**. Tạo một file `DeliveryWindow.java`:

~~~java
public final class DeliveryWindow {
    private DeliveryWindow() {}

    static long earliest(long sentAt, long delayMillis) {
        if (delayMillis < 0) {
            throw new IllegalArgumentException("negative delay");
        }
        return Math.addExact(sentAt, delayMillis);
    }

    static long expiration(long sentAt, long ttlMillis) {
        if (ttlMillis < 0) {
            throw new IllegalArgumentException("negative ttl");
        }
        return ttlMillis == 0L ? 0L
                : Math.addExact(sentAt, ttlMillis);
    }

    public static void main(String[] args) {
        long sentAt = 100_000L;
        long delay = 5_000L;
        long ttl = 12_000L;

        long ready = earliest(sentAt, delay);
        long expires = expiration(sentAt, ttl);

        System.out.println("earliest=" + ready);
        System.out.println("expiration=" + expires);
        System.out.println("windowMillis=" + (expires - ready));

        long tooShort = expiration(sentAt, 3_000L);
        System.out.println("shortTtlCanDeliver="
                + (tooShort > ready));

        System.out.println("noExpiration="
                + (expiration(sentAt, 0L) == 0L));
    }
}
~~~

Biên dịch/chạy từ thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 DeliveryWindow.java
java DeliveryWindow
~~~

**Standard output xác định**:

~~~text
earliest=105000
expiration=112000
windowMillis=7000
shortTtlCanDeliver=false
noExpiration=true
~~~

Mục đích phép thử là kiểm tra **công thức**; nó không đo network/broker, không giải quyết queue backlog và không chứng minh chính sách expiration của provider. `Math.addExact` giúp phát hiện overflow trong phép cộng số `long`; ở production, dữ liệu TTL/delay nhận từ API nên được giới hạn bằng quy tắc nghiệp vụ trước khi truyền vào JMS.

## 7. Delivery delay khác gì với TTL, priority và scheduler?

| Tính năng | Câu hỏi nó trả lời | Kết quả |
|---|---|---|
| **Delivery delay** | “Sớm nhất khi nào message được giao?” | Chặn delivery trước `JMSDeliveryTime`; không bảo đảm giao đúng thời điểm. |
| **TTL / expiration** | “Message còn được giữ hợp lệ đến bao giờ?” | Hết hạn theo `JMSExpiration`; có thể không bao giờ đến consumer nếu TTL quá ngắn. |
| **Priority** | “Message nào ưu tiên hơn khi đủ điều kiện?” | Giá trị 0–9 là gợi ý sắp xếp tùy provider/policy; không vượt qua thời gian chưa đủ điều kiện giao. |
| **Persistent delivery** | “Provider cần nỗ lực bảo đảm lưu message ra sao?” | Tính bền vững độc lập với mốc sớm nhất; không thay thế transaction/idempotency. |
| **Redelivery delay** | “Sau một lần xử lý thất bại, chờ bao lâu để gửi lại?” | Do listener transaction/retry broker/policy điều khiển; không đồng nhất với delay **lần đầu**. |
| **Cron/job scheduler** | “Đúng lịch nghiệp vụ nào sẽ kích hoạt?” | Hỗ trợ lịch, calendar, timezone, reschedule/cancel; thường phù hợp workflow dài hoặc phức tạp. |

### Ví dụ không nên dùng delivery delay

Nếu cần chạy một công việc vào **08:00 mỗi ngày làm việc**, đổi lịch khi có nghỉ lễ và cho phép người dùng hủy job, dùng Spring Scheduler, Quartz hoặc workflow engine kết hợp message/outbox có thể thích hợp hơn. JMS delivery delay tự thân không cung cấp hợp đồng cron, timezone calendar, quản lý lịch hoặc cơ chế sửa lịch sau khi gửi.

Nếu muốn chờ 10 giây trước khi **retry một message thất bại**, không nên gửi lại thủ công vô hạn vào một Queue khác chỉ vì biết `setDeliveryDelay`. Trước hết đánh giá broker redelivery delay, max delivery attempts, DLQ và idempotency; nếu dùng delayed requeue có chủ ý, cần tránh vòng lặp và giữ delivery count/correlation ID.

## 8. Transaction: mốc đếm không bắt đầu từ lúc commit

Một chi tiết dễ sai trong thiết kế là **delivery delay và TTL được tính từ thời điểm client gửi, không phải lúc transaction commit** theo Jakarta Messaging.

Giả sử một JMS transaction:

~~~text
10:00:00  producer.send(message); deliveryDelay=5s, TTL=12s
10:00:05  đã tới earliest delivery time
10:00:07  JMS transaction commit
10:00:07+ message mới có thể được cung cấp sau commit
10:00:12  TTL expiration
~~~

Ở đây **commit lúc 10:00:07 không tạo delivery time mới 10:00:12**. Message chỉ có thể đến consumer sau cả hai điều kiện: đã đủ mốc delivery time **và** giao dịch đã commit. Nếu commit quá muộn, TTL có thể hết hạn trước khi message được tiêu thụ.

Nếu transaction rollback, message gửi trong transaction không được commit để delivery; delivery delay không “cứu” message của giao dịch rollback.

Một transaction Spring/DB và một JMS transaction thường là **hai tài nguyên khác nhau**. Không coi một `@Transactional` chung là cam kết atomicity giữa database và broker nếu chưa cấu hình transaction manager đúng. Với publish phải theo sau DB commit, cân nhắc outbox/transaction boundary thay vì sử dụng delivery delay làm mẹo né race condition.

## 9. Queue và Topic: cùng delay nhưng khác cách phân phối

### Queue

Message được đưa đến Queue nhưng chỉ đủ điều kiện giao sau earliest delivery time. Sau mốc, provider chọn consumer hợp lệ theo semantics của Queue, priority và policy; số consumer, backlog và concurrency có thể khiến xử lý muộn.

Ví dụ lệnh tạo báo cáo: gửi lúc 09:00 với delay 30 giây, consumer không nên nhận trước 09:00:30. Nếu worker đang bận tới 09:05, việc nhận lúc 09:05 vẫn phù hợp với khái niệm “sớm nhất”.

### Topic

Message publish đến Topic có nhiều subscription. Delivery delay ảnh hưởng **thời điểm giao đến consumer**, không biến event thành “sự kiện chỉ xuất hiện khi đến hạn”. Theo Jakarta Messaging, message publish tới Topic chỉ được thêm vào durable/non-durable subscription **nếu subscription tồn tại tại thời điểm send**.

Do đó, không thể phát một Topic message trì hoãn 1 giờ rồi tạo subscription sau 30 phút và mặc định subscription mới chắc chắn sẽ nhận message đó. Muốn bắt event khi consumer offline, phải tạo durable subscription đúng lúc và kiểm tra persistence/retention của broker, kể cả khi delay dài.

### Ordering

Delay có thể làm đảo thứ tự consumer quan sát. Ví dụ producer gửi A trước B nhưng A delay 10 giây còn B delay 0, B có thể đến trước A; JMS ordering có những ngoại lệ và điều kiện cụ thể cho delayed messages. Không dựa vào thứ tự gửi tuyệt đối để thực hiện workflow phụ thuộc dữ liệu nếu có nhiều delay, priority hoặc consumer cạnh tranh. Dùng business sequence, correlation ID, idempotency và trạng thái nghiệp vụ khi cần.

## 10. Delay cố định và delay theo từng thao tác

### Delay cố định: nhiều lần gửi cùng chính sách

Một bean `JmsTemplate` với `setDeliveryDelay(5_000L)` là hợp lý khi toàn bộ Queue “nhắc thanh toán sau 5 giây” có cùng chính sách. Khi cần gửi một command không trễ, sử dụng template thứ hai với `deliveryDelay=0` hoặc không cấu hình delay, tránh gọi setter để sửa singleton đang được nhiều thread sử dụng.

### Delay động: dùng ProducerCallback có phạm vi rõ ràng

`JmsTemplate` không có overload `convertAndSend(payload, delayMillis)`. Khi phải chọn delay theo request, có thể dùng `ProducerCallback` để truy cập `MessageProducer`:

~~~java
// Mảnh mã: jmsTemplate là bean đã inject, và provider hỗ trợ JMS 2.0.
jmsTemplate.execute("billing.invoice.jobs", (session, producer) -> {
    long oldDelay = producer.getDeliveryDelay();
    try {
        producer.setDeliveryDelay(8_000L);
        producer.send(session.createTextMessage("send-once-later"));
        return null;
    } finally {
        producer.setDeliveryDelay(oldDelay);
    }
});
~~~

Điều quan trọng:
- `execute(String, ProducerCallback)` cung cấp một `Session` và `MessageProducer` trong phạm vi callback do template quản lý.
- Callback đặt delay trên producer **không làm đổi `JmsTemplate.getDeliveryDelay()`** của singleton; việc restore trong `finally` tránh để lại trạng thái cũ nếu connection/session/producer được cache để tái sử dụng.
- Một số provider không hỗ trợ `getDeliveryDelay`/`setDeliveryDelay` đầy đủ. Đoạn này phải được kiểm chứng với provider/client đã chọn; khi provider không hỗ trợ, gọi có thể ném exception.
- Đừng giữ producer/session vào field để dùng ngoài callback; tránh cache một producer mutable và chia sẻ trực tiếp qua threads.
- Nếu nhu cầu delay rất đa dạng, khối lượng lớn hoặc yêu cầu hủy/đổi lịch, cân nhắc một scheduling service chuyên biệt, không biến việc cập nhật producer mutable thành kiến trúc chính.

Nếu có thể, nhiều template với policy ổn định thường dễ kiểm thử hơn thay đổi producer per-call. Cũng có thể viết một adapter chỉ sở hữu producer trong **một** `SessionCallback` rồi đóng producer ở cuối callback; việc chọn cách nào phụ thuộc quản lý tài nguyên của provider và connection pool.

### Vì sao MessagePostProcessor không thay thế setDeliveryDelay?

`MessagePostProcessor` chủ yếu sửa một `Message` được tạo từ converter (correlation ID, application properties...). `JMSDeliveryTime` do provider thiết lập khi gửi, vì vậy đừng viết:

~~~java
// Sai về ý nghĩa: không phải cách tiêu chuẩn để yêu cầu delay.
jmsTemplate.convertAndSend("billing.invoice.jobs", "job", m -> {
    m.setJMSDeliveryTime(System.currentTimeMillis() + 8_000L);
    return m;
});
~~~

Setter header có tồn tại vì provider cần API để điền giá trị; **ứng dụng không được dùng làm công cụ lập lịch theo chuẩn**. Cách đúng là yêu cầu producer/template set delay, hoặc dùng extension scheduling của broker khi đã chấp nhận phụ thuộc vendor.

## 11. Chênh lệch chuẩn và tính năng theo provider

Một lớp Java triển khai `jakarta.jms.MessageProducer` không đủ để kết luận mọi tính năng JMS 2.0 đều hoạt động đầy đủ trên mọi broker/client/version.

| Provider / cách gửi | Lưu ý |
|---|---|
| **Apache ActiveMQ Artemis** | Hỗ trợ scheduled delivery; Java JMS client triển khai `setDeliveryDelay`. Với hệ Artemis dùng riêng, broker còn có property `_AMQ_SCHED_DELIVERY` để chỉ định **epoch millisecond** dự kiến; đây là extension, không phải tên property JMS chuẩn. |
| **Apache ActiveMQ Classic** | Một số dòng/version chỉ triển khai một phần JMS 2.0; theo bảng tính năng của ActiveMQ Classic, `MessageProducer.setDeliveryDelay` có các giới hạn và có thể ném `UnsupportedOperationException`. Phải xác minh **version cụ thể**, không mặc định hoạt động vì compile được. |
| **Qpid JMS / AMQP 1.0 / managed broker** | Việc map `setDeliveryDelay` sang scheduler/AMQP annotations phụ thuộc client và khả năng broker; thử end-to-end trên protocol thực. |
| **JMS provider khác** | Đọc compatibility matrix/JMS version, cấu hình scheduler, quota và quyền; kiểm tra TTL, timestamp, delivery time trong các lần gửi thử. |

Ví dụ extension Artemis (không portable):

~~~java
// Mảnh code chỉ dành cho Artemis khi chủ động dùng property riêng.
long deliverAtEpochMillis = System.currentTimeMillis() + 5_000L;
jmsTemplate.convertAndSend("billing.invoice.jobs", "artemis-job", m -> {
    m.setLongProperty("_AMQ_SCHED_DELIVERY", deliverAtEpochMillis);
    return m;
});
~~~

Đoạn này đặt property scheduling riêng của Artemis, **không dùng `setJMSDeliveryTime`**. Chỉ sử dụng một trong các cơ chế standard/provider-specific đã được thử; tránh vừa set `JmsTemplate.deliveryDelay` vừa set `_AMQ_SCHED_DELIVERY` trong cùng message vì precedence có thể tùy phiên bản và cách map protocol.

Khi chuyển broker, nên ưu tiên chuẩn `MessageProducer.setDeliveryDelay` trên provider có hỗ trợ thật, đồng thời bỏ extension vendor nếu không còn phù hợp. Đừng nhầm scheduled delivery của broker với delayed retry của broker: cấu hình và observability có thể hoàn toàn khác nhau.

## 12. Hệ thống chậm, consumer offline và nguyên tắc không bảo đảm đúng giờ

Số 5.000 trong `setDeliveryDelay(5_000L)` chỉ là **cận dưới**. Những lý do message có thể đến muộn:
- Broker bị backlog hoặc scheduler không có deadline độ chính xác cao.
- Message chưa commit, destination bị khóa/pause, chưa có consumer/subscription phù hợp.
- Queue có priority, selector, load balancing, throttling, TTL/expiration hoặc giới hạn số kết nối.
- Network, clock skew giữa máy client/broker, bảo trì broker, failover hoặc mất kết nối.
- Consumer bận, thread pool/handler không còn capacity.

Thiết kế cần theo dõi cả `JMSDeliveryTime` và **thời điểm consumer thực sự bắt đầu xử lý**. Nếu SLA đòi hỏi job bắt đầu không trễ quá một ngưỡng, cần capacity planning, monitoring/alerting, overload strategy và đôi khi là scheduler chuyên nghiệp. JMS delivery delay không có hợp đồng hard real-time.

### Mất message và xử lý trùng

Một message delayed với `DeliveryMode.NON_PERSISTENT` có thể mất nếu broker lỗi; message persistent có thể sống qua failure nhưng còn phụ thuộc broker persistence và policy. Producer timeout lúc send không chứng minh broker chưa nhận; retry có thể tạo duplicate. Nên gắn event/job ID, kiểm tra trạng thái nghiệp vụ và thiết kế idempotent consumer.

Delay không phải giải pháp bảo đảm “chỉ chạy đúng một lần” cho toàn bộ hệ thống. Consumer vẫn cần transaction, acknowledgement/redelivery, dead-letter policy và deduplication phù hợp.

## 13. Quan sát và kiểm thử thực tế

Với hệ thống production, test trên **bản broker/client/transport thật**, ngoài demo embedded:

| Bài kiểm tra | Bằng chứng cần lưu |
|---|---|
| Delay = 0 | Có thể nhận khi send/commit xong, không có thời gian chặn do cấu hình delay. |
| Delay = 3.000 ms | `JMSDeliveryTime` đúng mốc; consumer không nhận **trước** mốc đó. |
| Delay > receive timeout | Receive trả `null` trong thời gian ngắn, một receive tiếp theo có thể nhận sau khi đến hạn. |
| TTL < delay | Message có thể hết hạn, không được giao; kiểm tra expiry queue/metrics. |
| TTL > delay | Có khoảng thời gian hợp lệ để được giao; kiểm tra cả expiration. |
| Transaction commit muộn | Delivery time không bị cộng delay **lần hai** từ lúc commit; không giao trước commit. |
| Rollback transaction | Message chưa commit không được deliver. |
| Topic subscription muộn | Không kỳ vọng subscription tạo sau send tự nhận lịch sử. |
| Failover/restart | Kiểm tra persistence của scheduled message và thời điểm sau phục hồi. |
| Provider không hỗ trợ | Đảm bảo ứng dụng fail rõ hoặc dùng phương án đã thiết kế, không silently mất delay. |

Có thể ghi log/metric theo các trường:
- `JMSMessageID`/business event ID/correlation ID.
- `JMSDeliveryTime` và `JMSExpiration` (epoch millis).
- Thời gian broker nhận, thời gian consumer nhận, thời gian xử lý, backlog/scheduled count.
- Delay yêu cầu, loại Queue/Topic, transaction commit latency và số lần redelivery.

Không log payload chứa dữ liệu nhạy cảm, token hoặc mật khẩu. Để đối chiếu mốc thời gian giữa client và broker, đồng bộ đồng hồ NTP/clock và dùng UTC trong log; chuyển timezone chỉ ở tầng trình bày.

## 14. Các lỗi phổ biến

| Sai lầm | Vì sao sai | Cách đúng |
|---|---|---|
| “Delay 5 giây nghĩa là chạy đúng sau 5 giây.” | JMS chỉ bảo đảm **không giao sớm hơn** mốc. | Viết SLA có tolerance, đo drift từ earliest đến actual consumption. |
| “setDeliveryDelay trì hoãn việc gọi send.” | Producer gửi vào broker ngay, việc nhận mới bị hoãn theo hợp đồng. | Phân biệt send acceptance và consumer delivery. |
| “TTL 3 giây và delay 10 giây thì nhận ở giây thứ 10.” | Message có thể hết hạn ở giây thứ 3. | Chọn TTL dài hơn delay + đủ thời gian backlog xử lý, hoặc TTL 0 khi thích hợp. |
| “JmsTemplate.setDeliveryDelay mặc định là 0.” | Spring mặc định **-1** để không truyền setting cho provider. | Xem `getDeliveryDelay()`; phân biệt -1 sentinel và 0 explicit. |
| “Phải bật explicitQosEnabled mới có delivery delay.” | Flag đó quản lý delivery mode/priority/TTL của template. | Cấu hình delay riêng; test API đúng provider. |
| “Đặt JMSDeliveryTime trên Message là hẹn giờ.” | Đây là header do provider đặt khi send. | Dùng `setDeliveryDelay` trên producer/template. |
| “JMS send có overload delay theo từng message.” | API cổ điển có overload mode/priority/TTL, **không** có argument delay. | `MessageProducer.setDeliveryDelay` hoặc adapter callback phù hợp. |
| “Delay được đếm lại khi transaction commit.” | Chuẩn tính từ send time. | Xem cả delay, TTL và thời gian commit. |
| “Message Topic publish hôm nay sẽ vào subscriber tạo sau 1 giờ.” | Subscription cần tồn tại khi message được publish theo quy tắc chuẩn. | Dùng durable subscription/retention theo thiết kế và provision trước send. |
| “Có chữ JMS 2.0 thì provider chắc chắn hỗ trợ.” | Implementation có thể chưa đầy đủ. | Thử tính năng trên version broker/client thật. |
| “Sửa setter của singleton trước mỗi send là an toàn.” | Có race condition giữa các thread. | Template theo policy hoặc callback có phạm vi rõ ràng. |
| “Delivery delay thay thế retry/backoff.” | Delay cho initial send, không tự xử lý retry/redelivery/DLQ. | Thiết kế retry với max attempts, DLQ và idempotency. |

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Gửi message lúc 14:00:00.000, delay 8 giây, TTL 30 giây. Provider được phép giao sớm nhất lúc nào, và message hết hạn lúc nào?

**Đáp án:** Sớm nhất 14:00:08.000; expiration 14:00:30.000. Đây là cửa sổ giao khả dĩ, không phải hứa sẽ xử lý trước 14:00:30.

**Câu 2.** Nếu TTL = 2 giây và delivery delay = 5 giây, có thể bảo đảm consumer nhận sau 5 giây không?

**Đáp án:** Không. Message có thể đã hết hạn trước earliest delivery time. Sửa TTL/chính sách expiry hoặc thay cách lên lịch.

**Câu 3.** Sau send lúc 10:00:00 với delay 10 giây, transaction được commit lúc 10:00:12. Message có phải đợi tới 10:00:22 không?

**Đáp án:** Không. Earliest theo chuẩn là 10:00:10; sau commit 10:00:12 message có thể đủ điều kiện giao ngay nếu chưa hết hạn và broker/consumer sẵn sàng.

**Câu 4.** Vì sao không dùng `message.setJMSDeliveryTime(now + delay)`?

**Đáp án:** `JMSDeliveryTime` được provider đặt khi send, client không dùng setter đó làm API scheduling. Dùng `MessageProducer#setDeliveryDelay`, `JMSProducer#setDeliveryDelay` hoặc `JmsTemplate#setDeliveryDelay`.

**Câu 5.** Cấu hình `JmsTemplate.setDeliveryDelay(5000)` nhưng `setExplicitQosEnabled(false)`. Có nhất thiết Spring bỏ qua delay không?

**Đáp án:** Không. Delivery delay được quản lý độc lập với ba thuộc tính explicit QoS của template; vẫn phải bảo đảm provider triển khai `MessageProducer#setDeliveryDelay`.

**Câu 6.** Producer gửi event Topic rồi subscriber mới được tạo trước khi hết delay. Subscriber đó có chắc nhận event không?

**Đáp án:** Không. Theo Jakarta Messaging, membership của durable/non-durable subscription áp dụng tại thời điểm message được publish/sent, không phải tại thời điểm hết delivery delay.

**Câu 7.** Khi broker phát lại message sau một lần listener fail, `setDeliveryDelay` ở producer có tự đặt lại delay cho từng retry không?

**Đáp án:** Không có bảo đảm đó. Redelivery delay/rollback/retry là chính sách riêng của broker/consumer container; cần kiểm tra và cấu hình cụ thể.

## 16. Checklist triển khai

- [ ] Đã hiểu rõ “earliest delivery time” không đồng nghĩa một lịch thực thi chính xác.
- [ ] Đã xác minh producer/client/broker hỗ trợ JMS 2.0 delivery delay thực sự.
- [ ] Dùng đúng `setDeliveryDelay` trên producer/template, không sửa `JMSDeliveryTime` trực tiếp.
- [ ] Có chính sách TTL hợp lý, không hết hạn trước earliest delivery time.
- [ ] Đã kiểm tra transaction send/commit/rollback và publisher/consumer behavior.
- [ ] Nếu dùng Topic, subscription được thiết lập đúng trước publish khi cần.
- [ ] Không thay setter của singleton `JmsTemplate` giữa các request song song.
- [ ] Đã thử với Queue/Topic thật, TLS, broker restart, backlog và trường hợp provider không hỗ trợ.
- [ ] Có retry/DLQ và idempotency tách biệt với initial delivery delay.
- [ ] Có metric/log cho `JMSDeliveryTime`, actual receive time và độ trễ.

## 17. Tài liệu chính thức

- [Jakarta Messaging 3.1 Specification — JMSDeliveryTime, TTL và delivery delay](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html).
- [Jakarta Messaging 3.1 — MessageProducer#setDeliveryDelay](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer).
- [Jakarta Messaging 3.1 — Message#getJMSDeliveryTime](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message).
- [Spring Framework 6.2.14 — JmsTemplate#setDeliveryDelay](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html).
- [Spring Framework 6.2 — Using JmsTemplate và QoS](https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html).
- [Spring Boot 3.5 — Artemis và JMS configuration](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html).
- [Apache ActiveMQ Artemis — Scheduled Messages](https://artemis.apache.org/components/artemis/documentation/latest/scheduled-messages).
- [Apache ActiveMQ Classic — JMS 2.0 và Jakarta Messaging feature support](https://activemq.apache.org/components/classic/documentation/jms2).
