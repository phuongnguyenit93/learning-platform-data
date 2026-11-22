# Nhiều consumer cùng nhận từ một Queue

## Mục tiêu học tập

Sau bài này, bạn có thể giải thích vì sao nhiều consumer cùng lắng nghe một JMS Queue nhưng mỗi lần phát một message chỉ có một consumer nhận; phân biệt xử lý song song với phát bản sao cho mọi người nhận; cấu hình số consumer bằng Spring JMS; và thiết kế xử lý an toàn trước lỗi, phát lại, lệch tải và mất thứ tự hoàn thành.

## 1. Mô hình competing consumers

Trong mô hình **point-to-point**, producer gửi message vào một `Queue` trên broker. Có thể có nhiều consumer cùng đăng ký Queue đó. Với một lần phát thông thường, broker chọn **một** consumer đủ điều kiện để nhận mỗi message; các consumer còn lại không đồng thời nhận một bản sao của message ấy. Đây là mô hình **competing consumers** (các consumer cạnh tranh nhận việc).

```text
Producer A ----\
                >---- [orders.queue] ----+---- Consumer 1
Producer B ----/                        +---- Consumer 2
                                        +---- Consumer 3
```

Ví dụ producer gửi sáu message `M1..M6`; kết quả *có thể* là:

| Consumer | Các message nhận trong một lần chạy giả định |
| --- | --- |
| C1 | M1, M4 |
| C2 | M2, M5 |
| C3 | M3, M6 |

Bảng chỉ mô tả **một phân phối minh họa**, không cam kết broker chia đều hay theo vòng tròn. Nếu C1 nhanh hơn, khởi động trước, có bộ đệm nhận trước (`prefetch`) lớn hoặc C2 bận, C1 có thể nhận nhiều message hơn. Chuẩn Jakarta Messaging không quy định thuật toán chọn consumer khi có nhiều consumer trên cùng Queue.

Điểm cần nhớ: “một message được phát cho một consumer” **không có nghĩa** nghiệp vụ chắc chắn được thực thi đúng một lần trong mọi tình huống. Message chưa được xác nhận/commit có thể được gửi lại sau lỗi; cùng một công việc nghiệp vụ có thể đi qua nhiều lần xử lý.

### So với Topic

| Cùng gửi một message | Queue có nhiều consumer | Topic có nhiều subscription độc lập |
| --- | --- | --- |
| Mục đích thường gặp | Chia việc để tăng năng lực xử lý | Phân phối sự kiện đến nhiều nhóm quan tâm |
| Ai nhận? | Một consumer đủ điều kiện cho mỗi lần phát đến Queue | Mỗi subscription đủ điều kiện có thể nhận một bản sao |
| Tăng số consumer | Tăng số bên cùng chia tải của Queue | Phụ thuộc cách tổ chức subscription; shared subscription cũng có thể chia tải trong chính subscription đó |

Vì vậy, “ba worker đều phải biết về đơn hàng mới” thường cần các subscription khác nhau trên Topic hoặc cơ chế fan-out; còn “ba worker cùng chia nhau xử lý đơn hàng” phù hợp với **một Queue có ba consumer**.

## 2. Message đi qua Queue như thế nào?

Một vòng đời điển hình:

1. Producer gửi message với payload và các thuộc tính cần thiết; broker tiếp nhận và lưu/định tuyến theo cấu hình độ bền, giao dịch và nhà cung cấp.
2. Một consumer đủ điều kiện nhận message từ Queue. Broker có thể đã đẩy trước nhiều message vào vùng `in-flight` của consumer này.
3. Listener xử lý công việc. Consumer khác có thể đồng thời xử lý *message khác*.
4. Khi phiên nhận xác nhận thành công hoặc transaction JMS commit, broker coi lần nhận đã hoàn tất.
5. Nếu consumer mất kết nối, rollback hoặc chưa xác nhận thành công, broker có thể phát lại message cho **cùng consumer hoặc consumer khác**, tùy cấu hình và trạng thái.

Ví dụ C1 đã trừ tồn kho trong database nhưng JVM chết trước khi transaction JMS commit. Khi message phát lại cho C2, nếu code không chống xử lý trùng, tồn kho có thể bị trừ lần nữa. Cơ chế “một consumer nhận message” không tự giải quyết tính nguyên tử giữa JMS và database.

**Một consumer là một thực thể nhận JMS**, gắn với `Session`/`MessageConsumer` hoặc một listener container tương ứng. Nó không đồng nghĩa tuyệt đối với “một máy”, “một instance ứng dụng” hay “một thread dùng chung”. Spring quản lý các consumer và session trong listener container để xử lý đồng thời.

## 3. Những cách tạo nhiều consumer

- **Nhiều consumer trong một JVM:** một Spring `@JmsListener` dùng listener container với `concurrency` lớn hơn 1. Container mở các JMS session/consumer thích hợp; nhiều lời gọi đến cùng listener có thể chạy song song.
- **Nhiều instance ứng dụng:** nhiều process/pod cùng cấu hình `destination = "orders.queue"` và kết nối **cùng broker/Queue logic**. Chúng chia việc, kể cả khi không biết nhau.
- **Kết hợp cả hai:** nếu có hai replica, mỗi replica khởi tạo 3–5 consumer cho listener này, tổng có thể là khoảng 6–10 consumer khi tất cả hoạt động, tùy điều kiện tải và trạng thái container.

Không phải tạo ba phương thức `@JmsListener` khác nhau chỉ để có ba worker. Với một nghiệp vụ, cấu hình `concurrency` trên một listener thường rõ ràng hơn. Nhiều listener cùng trỏ đến một Queue vẫn cạnh tranh nhận message, nhưng phải bảo đảm chúng hiểu cùng định dạng và cùng quy tắc xử lý.

Trong Jakarta Messaging, `Session`, `MessageConsumer` và `JMSContext` không được dùng tùy ý đồng thời giữa nhiều thread. Muốn tăng song song, tạo nhiều session/consumer phù hợp hoặc để Spring listener container làm việc đó. Không tự chia sẻ một `Session` cho một pool thread rồi gọi nhận đồng thời.

## 4. Ví dụ Spring JMS: nhiều consumer trên một Queue

Ví dụ dưới đây dùng **Java 17+**, **Spring Boot 4.0.6** và một **Apache ActiveMQ Artemis broker đang chạy bên ngoài**. Đây là một ứng dụng thử nghiệm độc lập; broker phải cho phép sử dụng Queue `orders.queue` (tạo sẵn hoặc bật tự tạo Queue). Cấu hình tài khoản phải khớp với broker thực tế.

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.0.6</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>queue-consumers</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/resources/application.properties`**

```properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
# Nếu broker yêu cầu xác thực, cung cấp đúng tài khoản thực tế:
# spring.artemis.user=...
# spring.artemis.password=...
```

**`src/main/java/example/jms/QueueConsumersApplication.java`**

```java
package example.jms;

import jakarta.jms.ConnectionFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableJms
public class QueueConsumersApplication {

    public static void main(String[] args) {
        SpringApplication.run(QueueConsumersApplication.class, args);
    }

    @Bean
    DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(false);       // Queue, không phải Topic
        factory.setConcurrency("3-5");        // 3 consumer nền, tối đa 5
        factory.setSessionTransacted(true);   // Commit/rollback JMS
        return factory;
    }

    // Chỉ dùng cho demo: mỗi lần khởi động sẽ gửi 12 message mới.
    @Bean
    ApplicationRunner sendDemo(JmsTemplate jmsTemplate) {
        return args -> {
            for (int i = 1; i <= 12; i++) {
                jmsTemplate.convertAndSend("orders.queue", "order-" + i);
            }
        };
    }

    @Component
    public static class OrderListener {
        @JmsListener(destination = "orders.queue")
        public void onOrder(String orderId) {
            System.out.printf(
                    "consumer=%s | message=%s%n",
                    Thread.currentThread().getName(),
                    orderId
            );
        }
    }
}
```

Chạy khi broker đã sẵn sàng:

```bash
mvn spring-boot:run
```

Thử nghiệm có thể in các dòng dạng `consumer=<tên-thread> | message=order-1` cho đến `order-12`. **Không có một stdout cố định**: thread nào xử lý message nào, thứ tự các dòng và có thật sự dùng hết năm consumer hay không đều phụ thuộc lịch chạy và broker. Mỗi chuỗi `order-1` đến `order-12` chỉ được ứng dụng gửi một lần trong một lần khởi động demo; không suy ra từ log rằng hệ thống bảo đảm đúng một lần xử lý nghiệp vụ khi có lỗi.

**Giải thích những dòng quan trọng:**

- `@EnableJms` bật hạ tầng endpoint `@JmsListener` của Spring.
- `jmsListenerContainerFactory` là tên factory mặc định mà endpoint không khai báo `containerFactory` sẽ dùng. Nó tạo listener container thuộc họ `DefaultMessageListenerContainer`.
- `setConcurrency("3-5")` yêu cầu khoảng concurrency từ 3 đến 5 cho **endpoint này**; mỗi consumer vận hành với session phù hợp. Có thể thay bằng `setConcurrency("1")` để quan sát xử lý gần như tuần tự.
- `setPubSubDomain(false)` chỉ rõ destination được hiểu là Queue. Đây cũng thường là mặc định, nhưng viết ra giúp thấy chủ đích.
- `setSessionTransacted(true)` yêu cầu transaction **JMS cục bộ**: listener thành công thì commit việc nhận; lỗi runtime phát ra khỏi listener thì container rollback việc nhận. Điều này không tự biến thao tác database thành cùng transaction.
- `JmsTemplate.convertAndSend` dùng chuyển đổi thông điệp mặc định phù hợp cho `String`, phía nhận ánh xạ thành tham số `String orderId`.
- Spring có thể dùng một instance `OrderListener` cho nhiều lượt gọi song song. Vì thế listener nên không giữ trạng thái thay đổi được dùng chung theo cách thiếu đồng bộ.

Nếu muốn thấy nhiều process tranh nhau nhận việc, tách `sendDemo` thành publisher chạy một lần, rồi chạy hai hoặc ba instance chỉ có listener với cùng broker và cùng Queue. **Không giữ bean seed demo ở tất cả replica**: mỗi replica khởi động lại sẽ tự tạo thêm 12 message, dễ nhầm với message bị xử lý trùng.

## 5. Concurrency tăng thông lượng nhưng không bảo đảm chia đều

Giả sử trung bình một message cần 50 ms công việc và không bị nghẽn tài nguyên khác. Một consumer có thông lượng lý thuyết khoảng `1 / 0,05 = 20 message/giây`. Sáu consumer có thể đạt gần `120 message/giây` trong điều kiện lý tưởng; thực tế còn chi phí kết nối, I/O, broker, database, cạnh tranh khóa và độ biến thiên thời gian xử lý.

Nếu tốc độ message đến (`λ`) lớn hơn tổng tốc độ xử lý bền vững, độ sâu Queue tăng dần. Cần chọn concurrency dựa vào thông lượng đến, thời gian xử lý, mức dùng CPU, giới hạn database và số message đang `in-flight`; tăng số consumer vô hạn không làm một database quá tải trở nên nhanh hơn.

**Vì sao ba consumer không nhận đúng 1/3 message?**

1. **Prefetch/buffering:** broker có thể cấp nhiều message cho một consumer trước khi consumer khác sẵn sàng. Consumer mới đến có thể thấy ít việc dù Queue từng có hàng chờ.
2. **Tốc độ từng consumer:** consumer xử lý nhanh, mạng tốt hoặc ít phải chờ I/O thường có cơ hội nhận thêm.
3. **Thời điểm kết nối:** consumer khởi động trước có thể đã nhận nhiều message.
4. **Selector, priority và policy broker:** một message có thể chỉ phù hợp với một nhóm consumer; ưu tiên, grouping, dispatch policy thay đổi phân phối.
5. **Giới hạn tài nguyên:** session pool, connection pool, thread, transaction, broker quota hoặc giới hạn của dịch vụ downstream làm concurrency thực tế thấp hơn cấu hình.

Prefetch lớn có thể cải thiện thông lượng khi công việc rất nhanh; ngược lại nó có thể gây mất cân bằng tải hoặc khiến nhiều message nằm chờ ở một consumer chậm. Điều chỉnh prefetch/consumer window theo **broker cụ thể**, không coi một tham số chung là chuẩn của mọi JMS provider. Khi đo hiệu năng, kiểm tra cả Queue pending và message đã dispatch nhưng chưa acknowledge.

## 6. Thứ tự: FIFO ở Queue không đồng nghĩa hoàn tất đúng thứ tự

Một Queue có khái niệm thứ tự message, nhưng khi nhiều consumer xử lý song song, **thứ tự kết thúc nghiệp vụ không được bảo đảm**.

Ví dụ:

```text
M1 (cập nhật đơn A) -> C1 xử lý 800 ms
M2 (hủy đơn A)     -> C2 xử lý  50 ms
Kết quả: M2 có thể hoàn tất trước M1
```

Rollback/redelivery, priority và selector còn có thể làm thứ tự giao nhận quan sát được phức tạp hơn. Vì vậy không nên dựa vào thứ tự các dòng log hoặc thứ tự commit database khi dùng nhiều consumer.

Nếu các message cùng `orderId` phải xử lý tuần tự, cân nhắc:

- Giảm concurrency xuống 1 cho Queue thực sự yêu cầu xử lý toàn cục theo thứ tự (đổi lại mất throughput).
- Phân vùng công việc theo business key (ví dụ mỗi đơn hoặc khách hàng), để các message liên quan được đưa đến một luồng xử lý tuần tự.
- Dùng **message groups** nếu broker hỗ trợ: chẳng hạn ActiveMQ Artemis hỗ trợ thuộc tính JMS `JMSXGroupID` để ghim các message cùng group vào một consumer. Cần hiểu giới hạn throughput, rebalancing và xử lý consumer mất kết nối.
- Thiết kế trạng thái nghiệp vụ với version/sequence và từ chối thao tác cũ, nếu bài toán cần tính đúng bất chấp xử lý ngoài thứ tự.

`JMSXGroupID` là ví dụ tính năng/triển khai broker cụ thể; không giả định mọi provider đều có cùng chính sách grouping và phục hồi.

## 7. Lỗi, rollback, redelivery và xử lý trùng

Cấu hình `sessionTransacted(true)` trong ví dụ là lựa chọn phù hợp cho luồng xử lý Queue cần độ tin cậy ở mức nhận JMS:

| Tình huống | Ý nghĩa thường gặp |
| --- | --- |
| Listener trả về thành công | Container commit transaction JMS; message được xác nhận ở broker |
| Listener ném exception và không bị nuốt | Container rollback JMS; broker có thể phát lại theo chính sách |
| Listener bắt exception rồi chỉ log và trả về bình thường | Container có thể coi là thành công và commit; lỗi nghiệp vụ bị che |
| JVM chết sau khi side effect database commit nhưng trước commit JMS | Message có thể redeliver; side effect có nguy cơ lặp |
| Message lỗi liên tục | Cần chính sách giới hạn retry, thời gian chờ/backoff và dead-letter queue do broker quản lý |

**Không đánh đồng local JMS transaction và database transaction.** Khi listener cập nhật database, chúng thường là **hai tài nguyên và hai transaction khác nhau**. `@Transactional` cho database không tự tạo commit nguyên tử với JMS; kể cả khi DB transaction hoàn tất trước khi JMS acknowledgment, vẫn có khoảng thời gian xảy ra lỗi. Distributed/XA transaction chỉ nên chọn khi nhu cầu, nền tảng và chi phí vận hành thực sự biện minh.

Cách phòng vệ thường dùng là **idempotent consumer**:

1. Producer gắn một `eventId` ổn định cho mỗi sự kiện nghiệp vụ. Không tạo ID mới mỗi lần broker phát lại cùng một message.
2. Ở database, tạo unique constraint trên `processed_event(event_id)`.
3. Trong **cùng transaction DB**, kiểm tra/ghi nhận `eventId` và thực hiện thay đổi nghiệp vụ. Nếu ID đã xử lý thì bỏ qua side effect và trả về thành công.
4. Chỉ để listener trả về thành công khi giao dịch DB hoàn tất; nếu lỗi tạm thời, để lỗi đi ra ngoài nhằm rollback JMS và retry có kiểm soát.
5. Đối với side effect ra dịch vụ bên ngoài (email, thanh toán...), áp dụng idempotency key/cơ chế phù hợp ở dịch vụ đích, vì unique constraint nội bộ không tự bảo đảm một lệnh ngoài hệ thống không bị lặp.

Ví dụ SQL định hướng thiết kế (không phải script đủ chạy vì schema/SQL dialect phụ thuộc hệ thống):

```sql
-- processed_event.event_id có UNIQUE constraint.
-- Cả việc ghi event_id và cập nhật nghiệp vụ phải cùng DB transaction.
BEGIN;
INSERT INTO processed_event(event_id) VALUES (:event_id);
-- Nếu INSERT thành công thì mới áp dụng thay đổi nghiệp vụ.
UPDATE orders SET processed = TRUE WHERE order_id = :order_id;
COMMIT;
```

Nếu gặp duplicate key, nhánh xử lý trùng phải kết thúc an toàn (và xử lý trạng thái transaction DB phù hợp với driver/dialect), **không chạy lại UPDATE**. Có thể dùng `INSERT ... ON CONFLICT DO NOTHING` trên PostgreSQL và chỉ cập nhật khi insert thực sự thêm hàng. Đây là cơ chế chịu lỗi chủ động, không phụ thuộc message có được redeliver cho cùng consumer hay consumer khác.

Với lỗi lặp mãi (poison message), cấu hình broker để phát lại hữu hạn lần và chuyển sang **DLQ (dead-letter queue)**. Việc “retry mấy lần”, “chậm bao lâu” và “DLQ ở đâu” thuộc policy broker; không mặc định mọi broker giống nhau. Theo dõi DLQ và có quy trình sửa dữ liệu rồi phát lại có kiểm soát.

## 8. Chọn mức song song và bảo vệ tài nguyên

Một chiến lược thực tế:

1. Bắt đầu ở concurrency nhỏ, chẳng hạn `2-4`, với baseline của một consumer; đo số message/giây, thời gian xử lý và độ sâu Queue.
2. Tăng từng bước khi Queue tăng liên tục và CPU/I/O/database còn đủ khả năng; kiểm tra tình trạng connection/session, độ trễ, lock contention và redelivery.
3. Giới hạn pool kết nối DB/HTTP sao cho số tác vụ đồng thời không gây bão kết nối hoặc timeout dây chuyền.
4. Theo dõi `queue depth`, `in-flight/unacknowledged`, `active consumers`, `oldest message age`, `retry/redelivery`, `DLQ`, throughput và p95/p99 xử lý; không chỉ nhìn CPU.
5. Đặt chính sách shutdown để các tác vụ đang xử lý có cơ hội kết thúc; kiểm thử khi một replica bị kill để biết message chưa commit được phát lại như thế nào.
6. Với message có phụ thuộc thứ tự, chọn thiết kế giữ thứ tự theo business key trước khi nâng concurrency.

Nếu workload chủ yếu gọi một API ngoài bị giới hạn 30 request/giây, tăng từ 5 lên 50 consumers có thể chỉ làm API trả 429 và tăng retry. Cần backpressure, rate limiting hoặc quota phù hợp, không chỉ tăng số listener.

## 9. Kiểm thử hành vi đúng

Một bài thực hành có ý nghĩa cần kiểm tra **nghiệp vụ**, không chỉ số dòng log:

| Phép thử | Thiết lập | Điều cần quan sát |
| --- | --- | --- |
| Chia tải bình thường | Gửi 100 message có `eventId` khác nhau; chạy 3 consumer | Mỗi ID hoàn tất một lần ở tầng nghiệp vụ, việc phân phối có thể không đều |
| Thêm consumer | Tăng concurrency hoặc thêm replica trong khi Queue có backlog | Throughput/queue age thay đổi ra sao; không giả định consumer mới lập tức nhận một nửa |
| Consumer bị kill | Dừng cưỡng bức consumer khi đang xử lý message trước commit JMS | Message có thể phát lại; eventId vẫn không tạo side effect trùng |
| Lỗi tạm thời | Chủ động ném lỗi có kiểm soát ở listener rồi cho lần sau thành công | Có rollback/redelivery đúng policy, không nuốt exception |
| Poison message | Tạo message luôn gây lỗi và cấu hình redelivery hữu hạn | Message đến DLQ, Queue chính không bị kẹt vô thời hạn |
| Phụ thuộc thứ tự | Gửi hai thao tác cùng business key có thời gian xử lý khác nhau | Phát hiện sai thứ tự; áp dụng grouping/partition nếu cần |

Để test “không có bản sao đồng thời đến hai consumer”, cần phân biệt **message delivery** và **effect**: broker có thể phát lại sau failure hoặc timeout, nên log ứng dụng với cùng `eventId` xuất hiện hai lần không chứng minh đã có hai consumer nhận cùng một lần phát. Hãy xem message ID, delivery count (nếu broker có), transaction outcome và ID nghiệp vụ.

## 10. Những nhầm lẫn thường gặp

- **“Ba consumer thì một message được cả ba nhận.”** Sai với Queue competing consumers; mỗi lần phát chọn một người nhận, không broadcast.
- **“Phân phối chắc chắn round-robin 1–2–3.”** Không được JMS chuẩn bảo đảm; prefetch và chính sách dispatch có thể làm lệch tải.
- **“Queue bảo đảm code chạy đúng một lần.”** Không; retry/redelivery có thể lặp side effect nếu không idempotent.
- **“Cứ tăng concurrency sẽ nhanh.”** Sai khi bottleneck ở broker, database, external API hoặc lock.
- **“Xử lý song song vẫn đảm bảo đơn A được cập nhật rồi mới hủy.”** Không; dùng thứ tự theo key hoặc sequencing khi có phụ thuộc.
- **“Bắt exception rồi log là retry.”** Nếu listener trả về bình thường trong transaction JMS, message có thể được commit thay vì retry.
- **“Tạo nhiều thread cùng dùng chung JMS Session.”** Sai quy tắc threading; dùng nhiều session hoặc listener container.
- **“Transaction JMS tự bao hết database.”** Không; cần thiết kế idempotency, quy tắc transaction hoặc XA có chủ đích.

## Tóm tắt cần ghi nhớ

Một Queue có thể có nhiều consumer để **chia công việc**: ở mỗi lần phát, một message được chuyển đến một consumer phù hợp, trong khi các message khác được xử lý song song. Spring JMS dùng `@JmsListener` và `DefaultJmsListenerContainerFactory#setConcurrency` để cấu hình số consumer; có thể mở rộng qua nhiều JVM/replica. Khi tăng concurrency, cần đồng thời xử lý **mất thứ tự hoàn thành**, **phân phối lệch do broker/prefetch**, **redelivery** và **side effect trùng**. Với ứng dụng nghiệp vụ, session JMS transacted + idempotency theo business ID + retry/DLQ + giám sát Queue là nền tảng đáng tin cậy.

## Tài liệu tham khảo

- Jakarta Messaging 3.1 — Queue semantics, multiple consumers, session threading: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Spring Framework — Annotation-driven listener endpoints: https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html
- Spring Framework — Message listener containers và transactions: https://docs.spring.io/spring-framework/reference/integration/jms/using.html
- Spring Boot — JMS / ActiveMQ Artemis: https://docs.spring.io/spring-boot/4.0/reference/messaging/jms.html
- Apache ActiveMQ Artemis — Messaging concepts: https://artemis.apache.org/components/artemis/documentation/latest/messaging-concepts.html
- Apache ActiveMQ Artemis — Message grouping: https://artemis.apache.org/components/artemis/documentation/latest/message-grouping.html