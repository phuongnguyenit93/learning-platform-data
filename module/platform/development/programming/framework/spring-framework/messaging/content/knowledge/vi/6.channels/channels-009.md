# Ranh giới của kênh trong bộ nhớ đối với độ bền và giao dịch

## 1. Kênh trong bộ nhớ giải quyết điều gì?

Kênh trong bộ nhớ (in-memory channel) chuyển message giữa các thành phần trong cùng tiến trình ứng dụng. Nó giúp tách producer khỏi consumer, điều phối luồng xử lý và có thể đệm message trong thời gian ngắn mà không cần một broker bên ngoài.

Đổi lại, message thường chỉ tồn tại trong heap hoặc cấu trúc dữ liệu của process. Khi JVM dừng đột ngột, container bị thay thế, máy chủ mất điện hoặc ứng dụng restart, message đang chờ có thể biến mất. Kênh trong bộ nhớ cũng không tự tạo một giao dịch nguyên tử giữa việc cập nhật database và việc gửi message.

Vì vậy cần tách ba câu hỏi:

1. **Message được chuyển đi như thế nào?** Đồng bộ trong thread hiện tại, qua executor hay qua hàng đợi trong bộ nhớ?
2. **Message tồn tại được bao lâu?** Chỉ trong bộ nhớ của process hay được lưu bền vững ở một kho/broker?
3. **Những thay đổi nào cùng commit hoặc rollback?** Chỉ database, hay cả database và message delivery?

Độ bất đồng bộ, độ bền và tính nguyên tử là ba thuộc tính khác nhau. Một channel có thể bất đồng bộ nhưng không bền vững; một broker có thể lưu message bền vững nhưng consumer vẫn xử lý lặp; một lời gọi đồng bộ có thể tham gia transaction database nhưng side effect bên ngoài database vẫn không tự rollback.

## 2. Các kiểu channel trong bộ nhớ thường gặp

Trong hệ sinh thái Spring, có nhiều implementation với cách dispatch khác nhau. Cần xác định đúng module vì một số channel thuộc Spring Framework, còn các channel quen thuộc khác thuộc Spring Integration.

| Channel | Module | Cách hoạt động | Ranh giới độ bền |
| --- | --- | --- | --- |
| `DirectChannel` | Spring Integration | Dispatch tới subscriber đồng bộ trong thread gửi | Không có durable storage mặc định |
| `QueueChannel` | Spring Integration | Giữ message trong queue để consumer nhận/poll | Queue mặc định trong bộ nhớ; restart có thể làm mất message |
| `PublishSubscribeChannel` | Spring Integration | Phát tới nhiều subscriber; có thể cấu hình executor | Không tự lưu message bền vững |
| `ExecutorChannel` | Spring Integration | Dispatch subscriber thông qua executor | Executor/queue của process không phải broker bền vững |
| `PriorityChannel` | Spring Integration | Queue trong bộ nhớ có thứ tự ưu tiên | Không tự lưu qua restart |
| `ExecutorSubscribableChannel` | Spring Framework Messaging | Gửi tới subscriber qua `Executor` | Không tự cung cấp persistence hoặc broker acknowledgement |

`DirectChannel` thường phù hợp khi muốn lời gọi service-to-service trong cùng process và cần kết quả xử lý ngay. `QueueChannel` phù hợp khi muốn producer và consumer tách thời điểm xử lý trong cùng ứng dụng. Channel dùng executor giúp tách thread, nhưng không biến tác vụ thành công việc có thể phục hồi sau khi process chết.

Không nên suy ra độ bền từ tên `QueueChannel`. Từ “queue” mô tả cấu trúc nhận message; nó không đảm bảo queue đã được ghi xuống disk hoặc replicate sang node khác.

## 3. Điều gì xảy ra khi process dừng?

Giả sử producer gửi một message vào `QueueChannel` và `send()` trả về `true`. Điều đó cho biết implementation đã chấp nhận message theo semantics của channel. Với queue mặc định trong bộ nhớ, message nằm trong bộ nhớ của ứng dụng.

Nếu process dừng trước khi consumer lấy message, queue không có bản sao bền vững để khôi phục. Nếu consumer đã lấy message khỏi queue nhưng dừng trước khi hoàn thành công việc, message cũng có thể không còn trong queue để giao lại.

Các failure window điển hình:

| Thời điểm lỗi | Hệ quả có thể xảy ra với channel trong bộ nhớ |
| --- | --- |
| Producer tạo message nhưng chưa gửi | Message chưa được channel chấp nhận; producer phải quyết định retry |
| `send()` đã trả `true`, consumer chưa nhận | Message có thể mất khi process restart |
| Consumer đã nhận, chưa commit database | Message có thể mất sau khi bị lấy khỏi queue; thay đổi database có thể rollback |
| Consumer commit database, process dừng trước khi ghi nhận hoàn tất ở hệ thống khác | Hệ thống khác có thể không biết nghiệp vụ đã hoàn tất; retry có thể gây tác động lặp |
| Ứng dụng deploy/restart khi còn message chờ | Queue trong heap bị tạo lại rỗng |

Do đó, nếu message đại diện cho việc bắt buộc phải thực hiện như thu tiền, giữ hàng, phát hóa đơn hoặc gửi thông báo pháp lý, không nên dựa duy nhất vào queue trong bộ nhớ làm nơi lưu duy nhất.

## 4. `send()` thành công không có nghĩa là dữ liệu đã bền vững

API `MessageChannel.send(...)` trả về boolean. Ý nghĩa của `true` phụ thuộc implementation:

- Với channel dispatch đồng bộ, handler có thể đã chạy trong thread gửi trước khi `send()` trả về.
- Với channel dùng executor, message có thể đã được giao cho executor hoặc task queue, trong khi handler chưa chạy xong.
- Với `QueueChannel`, message có thể đã được đưa vào queue và đang chờ consumer.

Trong cả ba trường hợp, `true` không tự chứng minh message đã được ghi xuống disk, replicate, hoặc có thể khôi phục sau khi process chết.

Ngược lại, `false` thường cho biết message không được chấp nhận theo chính sách timeout/capacity của implementation. Exception có thể biểu thị lỗi nghiêm trọng hơn. Producer cần xử lý kết quả gửi rõ ràng; không được bỏ qua `false` rồi coi như công việc đã được giao.

Với queue có capacity hữu hạn, cần lựa chọn timeout phù hợp. `send(message)` có thể dùng timeout mặc định vô hạn theo hợp đồng `MessageChannel`; nếu queue đầy, producer có nguy cơ chờ lâu. `send(message, 0)` thường được dùng để thử gửi ngay và không chờ capacity, nhưng hành vi chính xác cần được xác nhận trên implementation cụ thể.

## 5. Transaction database và channel trong bộ nhớ là hai ranh giới khác nhau

Spring `@Transactional` thường quản lý transaction của một transaction manager và các resource mà transaction manager đó hỗ trợ, chẳng hạn một kết nối JDBC tới database. Nó không tự biến một channel trong bộ nhớ thành transactional resource có khả năng rollback message.

Ví dụ, một service thực hiện:

1. Cập nhật trạng thái đơn hàng trong database.
2. Gửi `OrderPlaced` vào `QueueChannel`.
3. Transaction database sau đó rollback.

Message có thể đã nằm trong queue và consumer vẫn nhận được, dù thay đổi đơn hàng chưa commit. Kết quả là consumer xử lý một sự kiện “đơn đã đặt” cho dữ liệu đã rollback.

Chiều ngược lại cũng nguy hiểm: database commit thành công, nhưng process dừng trước khi gửi message. Dữ liệu nghiệp vụ đã tồn tại nhưng các consumer không nhận được sự kiện.

Đây là khoảng trống giữa hai hệ thống quản lý trạng thái. Chỉ đặt `@Transactional` quanh đoạn code không làm cho database commit và thao tác gửi vào in-memory channel trở thành một thao tác nguyên tử.

## 6. Khi nào channel đồng bộ có thể tham gia cùng transaction?

Với channel dispatch đồng bộ như `DirectChannel`, handler được gọi trong cùng thread gửi. Nếu producer và handler cùng sử dụng một transaction manager và cùng một transactional resource, các thao tác database trong handler có thể tham gia transaction đang mở theo propagation mặc định `REQUIRED`.

Ví dụ về luồng:

~~~text
@Transactional service
       |
       v
DirectChannel.send(message)
       |
       v
MessageHandler (cùng thread)
       |
       v
Repository/JDBC dùng cùng transaction manager
       |
       v
Commit hoặc rollback cùng transaction database
~~~

Trong trường hợp đó, nếu handler ném exception làm transaction rollback, các thay đổi database tham gia cùng transaction có thể rollback theo.

Tuy nhiên, điều này **không có nghĩa bản thân message send đã được ghi vào transaction log**. Việc dispatch tới handler là lời gọi trong process. Các side effect không thuộc transactional resource đó—ví dụ gọi HTTP service, gửi email, ghi file hoặc phát message ra broker khác—không tự được hoàn tác khi database rollback.

Cũng cần kiểm tra propagation. Nếu handler dùng `REQUIRES_NEW`, transaction riêng có thể commit độc lập với transaction ngoài. Nếu dùng transaction manager khác hoặc datasource khác, không thể mặc định chúng cùng commit/rollback. Nếu handler bắt exception và không truyền lỗi ra ngoài, transaction ngoài có thể không biết rằng bước xử lý đã thất bại.

Vì thế, channel đồng bộ có thể hữu ích để chia module và thực thi logic trong cùng transaction database, nhưng nó không thay thế outbox khi cần phát message bền vững ra khỏi process.

## 7. Channel bất đồng bộ làm thay đổi ranh giới transaction

Với channel dispatch qua executor, handler thường chạy trên thread khác. Transaction imperative của Spring thường gắn với thread hiện tại; transaction context không tự động được truyền sang thread executor.

Điều đó có nghĩa:

- Transaction của producer không tự bao trùm các thao tác database trong handler bất đồng bộ.
- Nếu handler cần transaction, hãy mở transaction riêng ở handler/service xử lý, ví dụ qua method được proxy `@Transactional` gọi đúng cách.
- Producer có thể commit trước khi handler bắt đầu; handler có thể chạy sau đó hoặc không chạy nếu process dừng.
- Exception ở handler thường xảy ra sau khi `send()` đã trả về, nên caller không thể dựa vào return value để biết kết quả nghiệp vụ.

Không nên truyền một transaction object hoặc JDBC connection qua thread để cố nối hai luồng. Hãy để mỗi thread dùng transaction boundary được quản lý đúng cách và dùng một cơ chế giao nhận bền vững nếu cần phục hồi công việc.

Context khác như security context, MDC logging hoặc tracing context cũng cần cơ chế propagation riêng. Đừng giả định executor tự sao chép mọi ThreadLocal từ producer sang consumer.

## 8. QueueChannel: buffer trong process và giới hạn capacity

`QueueChannel` của Spring Integration cho phép producer gửi message vào queue và consumer nhận bằng `receive()`. Có thể đặt capacity để giới hạn số message chờ trong bộ nhớ.

Capacity hữu hạn giúp tránh queue tăng không giới hạn, nhưng khi queue đầy, producer phải chờ hoặc bị từ chối theo timeout. Đây là backpressure trong phạm vi process, không phải cơ chế lưu trữ bền vững.

Ví dụ về chính sách:

- Queue còn chỗ: nhận message ngay.
- Queue đầy, timeout bằng zero: trả kết quả không nhận nếu không thể enqueue ngay.
- Queue đầy, timeout dương: chờ tối đa khoảng thời gian được cấu hình để có chỗ.
- Queue đầy, timeout vô hạn: caller có thể chờ cho đến khi có chỗ hoặc bị interrupt.

Không nên tăng capacity vô hạn chỉ để tránh `send()` thất bại. Queue lớn có thể làm tăng heap usage, thời gian chờ và độ trễ xử lý. Theo dõi queue depth, tuổi message cũ nhất, số lần từ chối, thời gian send/receive và tốc độ consumer.

## 9. Transactional outbox: nối database commit với việc phát message

Khi nghiệp vụ yêu cầu “nếu dữ liệu được commit thì sự kiện phải được phát”, transactional outbox là một mẫu thiết kế phổ biến.

### 9.1. Cách hoạt động

Trong cùng transaction database:

1. Cập nhật dữ liệu nghiệp vụ, ví dụ tạo đơn hàng.
2. Ghi một bản ghi outbox chứa event ID, loại sự kiện, payload, schema version và thời điểm tạo.
3. Commit transaction.

Sau đó một publisher riêng đọc các bản ghi outbox chưa phát và gửi lên broker. Khi nhận xác nhận publish theo chính sách của broker, publisher đánh dấu bản ghi đã gửi hoặc lưu trạng thái giao nhận.

~~~text
Producer service
     |
     v
DB transaction
  |-- update Order
  |-- insert OutboxEvent
     |
     v
Commit DB
     |
     v
Outbox publisher
     |
     v
Durable broker
     |
     v
Consumer + Inbox/Dedup + DB transaction
~~~

Điểm quan trọng là thay đổi nghiệp vụ và bản ghi outbox cùng nằm trong một transaction database. Nếu transaction rollback, cả hai đều rollback. Nếu commit, publisher có thể tìm thấy bản ghi outbox để tiếp tục gửi kể cả sau khi process khởi động lại.

### 9.2. Vì sao consumer vẫn cần idempotency?

Publisher có thể gửi message lên broker thành công rồi process dừng trước khi đánh dấu bản ghi outbox là đã gửi. Khi chạy lại, publisher có thể gửi cùng event lần nữa.

Vì vậy outbox thường cung cấp khả năng phát lại theo hướng at-least-once, không tự đảm bảo mỗi consumer chỉ thấy message một lần. Consumer cần `eventId` ổn định và inbox/dedup record. Việc ghi inbox record và cập nhật dữ liệu nghiệp vụ nên nằm trong cùng transaction của consumer.

### 9.3. Vận hành outbox

Cần có:

- Index để publisher tìm bản ghi chưa gửi hiệu quả.
- Lease/locking hoặc cơ chế claim để nhiều publisher không xử lý cùng bản ghi một cách tùy tiện.
- Retry có backoff và cảnh báo khi bản ghi tồn đọng quá lâu.
- Publisher confirm hoặc acknowledgement phù hợp với broker.
- Chính sách dọn bản ghi đã gửi và lưu lịch sử đủ để điều tra.
- Schema/versioning và giới hạn kích thước payload.
- Idempotent consumer và quy trình xử lý poison event.

Outbox là một cơ chế lưu bền vững trong database cộng với publisher; nó không phải tính năng tự động có được chỉ bằng cách đổi `DirectChannel` thành `QueueChannel`.

## 10. `@TransactionalEventListener` có giải quyết được không?

`@TransactionalEventListener` có thể chạy listener ở một transaction phase như `AFTER_COMMIT`. Điều này hữu ích khi muốn listener chỉ được gọi sau khi transaction đã commit, tránh phát tín hiệu cho thay đổi bị rollback.

Tuy nhiên, listener `AFTER_COMMIT` vẫn chạy trong cùng process. Nếu process dừng sau khi database commit nhưng trước khi listener hoàn tất, sự kiện có thể không được xử lý. Vì vậy đây là cách điều phối theo transaction lifecycle, không phải durable outbox.

Dùng `AFTER_COMMIT` cho side effect nội bộ có thể chấp nhận mất hoặc có thể tái tạo. Dùng outbox/broker bền vững khi yêu cầu nghiệp vụ đòi hỏi khôi phục sau crash.

## 11. Broker bền vững và transactional messaging

Khi cần giao message qua process hoặc node khác, một broker bền vững thường phù hợp hơn in-memory channel. Tuy nhiên “dùng broker” cũng chưa đủ; cần cấu hình và kiểm tra semantics:

- Destination/queue/topic được khai báo durable theo khả năng của broker.
- Message được publish ở chế độ persistence phù hợp.
- Producer kiểm tra publisher confirm hoặc acknowledgement thay vì giả định send đã được ghi.
- Consumer ack sau khi xử lý và commit thay đổi nghiệp vụ cần thiết.
- Replication/quorum, retention, disk và failover phù hợp với failure model.
- Retry, dead-letter queue và quy trình replay được thiết kế.
- Consumer có idempotency để chịu được redelivery.

Một số hệ thống hỗ trợ transaction phân tán hoặc XA/JTA để phối hợp nhiều resource như database và JMS broker. Cách này có thể cung cấp atomic commit trong phạm vi resource manager hỗ trợ, nhưng làm tăng độ phức tạp, chi phí vận hành và các failure mode liên quan tới coordinator. Không nên mặc định Spring Messaging channel hoặc một broker bất kỳ tự tham gia transaction database.

Với nhiều hệ thống ứng dụng, outbox + durable broker + idempotent consumer là lựa chọn dễ kiểm soát hơn một transaction phân tán xuyên qua nhiều dịch vụ.

## 12. Ví dụ chạy được: QueueChannel trong bộ nhớ

Ví dụ này dùng `QueueChannel` của Spring Integration để thấy rõ rằng `send()` enqueue message và `receive()` lấy message ra. Queue được tạo trong heap với capacity 2; không có broker hoặc persistence.

Tạo Maven project:

~~~text
in-memory-channel-demo/
  pom.xml
  src/main/java/com/example/messaging/InMemoryQueueDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>in-memory-channel-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring-integration.version>6.4.6</spring-integration.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.integration</groupId>
            <artifactId>spring-integration-core</artifactId>
            <version>${spring-integration.version}</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`src/main/java/com/example/messaging/InMemoryQueueDemo.java`:

~~~java
package com.example.messaging;

import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public final class InMemoryQueueDemo {
    private InMemoryQueueDemo() {
    }

    public static void main(String[] args) {
        QueueChannel channel = new QueueChannel(2);

        Message<String> message = MessageBuilder
                .withPayload("order-42")
                .setHeader("eventType", "OrderPlaced")
                .build();

        boolean accepted = channel.send(message, 0);
        System.out.println("accepted=" + accepted);

        Message<?> received = channel.receive(0);
        System.out.println("received=" + received.getPayload());

        System.out.println("queueEmpty=" + (channel.receive(0) == null));
    }
}
~~~

Biên dịch và chạy từ thư mục chứa `pom.xml` bằng JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.messaging.InMemoryQueueDemo
~~~

Stdout:

~~~text
accepted=true
received=order-42
queueEmpty=true
~~~

Trong ví dụ:

- `new QueueChannel(2)` tạo queue có capacity hai message trong bộ nhớ.
- `send(message, 0)` thử enqueue ngay, không chờ nếu queue đầy.
- `receive(0)` lấy message đang chờ mà không đợi message mới.
- Sau khi nhận message, queue không còn message nên lần `receive(0)` tiếp theo trả `null`.

Để quan sát giới hạn capacity, có thể gửi hai message mà không nhận rồi thử gửi message thứ ba với timeout zero; lần gửi thứ ba sẽ không được chấp nhận khi queue đầy. Ví dụ chính không làm bước đó để giữ stdout ngắn và xác định.

Việc chương trình in `accepted=true` chỉ chứng minh queue trong process đã nhận message. Nếu dừng JVM trước `receive()`, message chờ trong queue sẽ không được khôi phục từ disk.

## 13. Kiểm thử failure window thay vì chỉ kiểm thử happy path

Để đánh giá đúng semantics, hãy thử các tình huống:

1. Gửi message vào queue rồi kill process trước khi consumer nhận; xác nhận message không được khôi phục từ queue mặc định trong bộ nhớ.
2. Consumer nhận message rồi ném exception trước khi commit database; xác định message có được redeliver hay đã bị lấy khỏi queue.
3. Gửi message trong một transaction database rồi rollback; kiểm tra consumer có còn nhìn thấy message hay không.
4. Commit database rồi dừng process trước khi publish; kiểm tra outbox có giữ được công việc chờ phát không.
5. Publisher gửi thành công nhưng dừng trước khi đánh dấu outbox; xác nhận consumer chịu được event được phát lại.
6. Làm queue đầy; xác nhận producer block, timeout hoặc nhận `false` theo chính sách.
7. Tăng tải producer vượt tốc độ consumer; đo queue depth, tuổi message và memory usage.
8. Restart broker hoặc ngắt mạng; xác nhận publisher confirm, retry, DLQ và recovery hoạt động như thiết kế.

Kiểm thử không chỉ cần xác nhận message đến handler. Cần xác nhận message có bị mất, bị lặp, bị xử lý sai thứ tự hoặc tạo tác động nghiệp vụ trùng trong từng failure window.

## 14. Chọn giải pháp theo yêu cầu

| Yêu cầu | Giải pháp thường phù hợp | Lý do |
| --- | --- | --- |
| Chia logic giữa các module trong cùng ứng dụng; xử lý ngay | `DirectChannel` hoặc gọi service trực tiếp | Ít overhead, có thể cùng thread và cùng transaction database |
| Đệm tạm thời trong process; mất khi restart chấp nhận được | `QueueChannel` có capacity hữu hạn | Tách thời điểm gửi/nhận, không cần broker |
| Chạy handler ở thread khác; tác vụ phụ trợ | Executor-based channel | Giảm thời gian chờ caller; cần quản lý executor và lỗi async |
| Phát tín hiệu sau khi transaction commit; mất khi process crash chấp nhận được | `@TransactionalEventListener(AFTER_COMMIT)` | Listener chỉ chạy sau commit nhưng không durable |
| Database commit phải đi cùng sự kiện sẽ được phát | Transactional outbox + publisher | Domain data và outbox row commit nguyên tử trong cùng database |
| Giao message qua process/node và cần khôi phục sau restart | Durable broker + publisher confirm + consumer ack | Có storage, replication và giao nhận theo cấu hình broker |
| Consumer có thể nhận message nhiều lần | Stable event ID + inbox/idempotent handler | Chống tác động nghiệp vụ trùng |

Không chọn công nghệ chỉ vì nó hỗ trợ async. Hãy xác định trước việc mất message có được phép hay không, kết quả nào phải commit cùng nhau và ai chịu trách nhiệm retry.

## 15. Checklist thiết kế và review

1. Channel đang dùng là synchronous, executor-based hay pollable queue?
2. Message nằm ở heap, database hay broker? Có thể phục hồi sau restart không?
3. `send() == true` có nghĩa là dispatch xong, enqueue xong hay broker đã xác nhận ghi?
4. Queue có capacity hữu hạn không? Hành vi khi đầy và timeout đã rõ chưa?
5. Database transaction có cùng thread/resource manager với handler không?
6. Handler có chạy trên executor thread khiến transaction context không được kế thừa không?
7. Side effect ngoài database có thể xảy ra trước khi transaction rollback không?
8. Có failure window giữa database commit và publish message không?
9. Có cần transactional outbox/inbox hoặc broker transaction không?
10. Consumer có idempotent khi redelivery/replay không?
11. Có retry giới hạn, DLQ, alert và quy trình replay không?
12. Có đo queue depth, message age, send timeout, consumer lag và memory usage không?
13. Shutdown/deploy có drain công việc hoặc ghi lại trạng thái cần thiết không?
14. Đã kiểm thử process crash ở từng điểm trước/sau enqueue, receive, commit và ack chưa?

## 16. Ghi nhớ

Kênh trong bộ nhớ giúp truyền message và điều phối xử lý trong một process, nhưng không tự lưu dữ liệu bền vững qua restart. `send()` thành công chỉ có ý nghĩa theo implementation; nó không chứng minh consumer đã hoàn tất hoặc message đã được ghi xuống disk. Channel đồng bộ có thể cho phép handler tham gia cùng transaction database nếu cùng thread, transaction manager và resource, nhưng các side effect ngoài transaction không tự rollback. Channel executor tạo ranh giới thread mới nên transaction context không tự truyền sang handler. Khi database commit phải đi cùng việc phát message, dùng transactional outbox; khi message đi qua broker, cấu hình persistence/confirm/ack phù hợp và thiết kế consumer idempotent. Hãy quyết định theo failure semantics của nghiệp vụ, không chỉ theo việc xử lý có đồng bộ hay bất đồng bộ.