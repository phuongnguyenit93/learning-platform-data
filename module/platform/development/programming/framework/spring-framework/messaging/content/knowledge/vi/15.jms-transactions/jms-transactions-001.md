# Phân biệt xác nhận nhận thông điệp với hoàn tất nghiệp vụ

> Mục tiêu: phân biệt thời điểm broker xem một lần giao message đã được xác nhận với thời điểm nghiệp vụ thực sự hoàn tất; hiểu acknowledgement mode và JMS transaction; thiết kế listener Spring an toàn khi database hoặc hệ thống downstream gặp lỗi; áp dụng idempotency, inbox/outbox và kiểm thử các khoảng lỗi.

## 1. Ba mốc khác nhau trong một luồng messaging

Trong một luồng JMS, cụm từ “message đã thành công” có thể nói đến ba sự kiện khác nhau:

1. **Producer gửi thành công:** JMS provider đã chấp nhận thao tác gửi theo hợp đồng của `send()`/transaction. Điều này không chứng minh consumer đã nhận hoặc xử lý message.
2. **Consumer acknowledgement:** broker/provider ghi nhận lần giao message đã được xác nhận. Với queue, message thường không còn chờ consumer khác nhận theo chính sách của provider. Đây là trạng thái giao nhận ở tầng messaging.
3. **Business completion:** các thay đổi nghiệp vụ cần thiết đã được lưu bền vững và các bước bắt buộc theo hợp đồng nghiệp vụ đã đạt trạng thái hoàn tất.

Ba mốc có thể xảy ra ở các thời điểm khác nhau. Producer có thể gửi thành công nhưng consumer chưa chạy. Consumer có thể acknowledge message trước khi ghi database. Database có thể commit xong nhưng JMS transaction lại thất bại khi commit, khiến broker giao message lần nữa.

Vì vậy, **acknowledgement là xác nhận giao nhận ở tầng broker; business completion là kết quả nghiệp vụ đã được lưu và xác nhận ở các hệ thống có liên quan.** Không dùng một trạng thái để suy ra trạng thái còn lại.

## 2. Vòng đời xử lý message và điểm xác nhận

Một listener thường trải qua các bước:

```text
Broker có message
      |
      v
JMS consumer nhận message
      |
      v
Listener bắt đầu xử lý
      |
      v
Validate và thực hiện nghiệp vụ
      |
      v
Commit thay đổi nghiệp vụ
      |
      v
JMS acknowledge / commit session
      |
      v
Broker ghi nhận message đã được xử lý ở tầng giao nhận
```

Sơ đồ trên thể hiện thứ tự mong muốn khi database và JMS được quản lý riêng: lưu kết quả nghiệp vụ trước, sau đó mới xác nhận message. Tuy nhiên, giữa hai thao tác vẫn có một khoảng lỗi. Nếu database đã commit nhưng JMS commit thất bại, broker có thể giao lại message. Listener phải nhận diện message đã xử lý để không lặp side effect.

Nếu acknowledgement xảy ra trước khi nghiệp vụ được lưu, ứng dụng có thể mất message khi tiến trình dừng giữa hai bước. Nếu acknowledgement chỉ xảy ra sau khi nghiệp vụ đã commit, hệ thống có thể nhận duplicate khi acknowledgement thất bại hoặc kết quả commit không rõ ràng. Thiết kế đáng tin cậy phải xử lý được cả hai tình huống.

## 3. JMS acknowledgement mode có ý nghĩa gì?

JMS cung cấp ba acknowledgement mode cho session không transacted và một mô hình xác nhận bằng transaction:

| Chế độ | Cách xác nhận | Hành vi khi có lỗi |
|---|---|---|
| `AUTO_ACKNOWLEDGE` | Provider tự xác nhận theo quy tắc JMS sau khi `receive()` trả về thành công hoặc listener được gọi kết thúc thành công | Thời điểm cụ thể còn phụ thuộc cách container thực thi; không nên dựa vào mode mặc định của Spring listener container để bảo đảm redelivery |
| `CLIENT_ACKNOWLEDGE` | Client gọi `Message.acknowledge()` | Một lần acknowledge xác nhận tất cả message đã được session đó tiêu thụ trước thời điểm gọi |
| `DUPS_OK_ACKNOWLEDGE` | Provider xác nhận lười hoặc theo lô | Có thể có duplicate khi provider/client gặp lỗi; consumer phải chịu được việc giao lặp |
| Transacted `Session` | `commit()` xác nhận message đã nhận và commit các message gửi trong cùng session; `rollback()` phục hồi message đã nhận và hủy các message gửi chưa commit | Listener thất bại làm transaction rollback và broker có thể redeliver |

Theo Jakarta Messaging specification, với synchronous `receive`, `AUTO_ACKNOWLEDGE` xác nhận khi lời gọi receive trả về thành công. Với asynchronous `MessageListener`, đặc tả quy định xác nhận khi listener được gọi kết thúc thành công. `CLIENT_ACKNOWLEDGE` có phạm vi theo session: gọi `acknowledge()` trên một message sẽ xác nhận các message mà session đã giao trước đó. `DUPS_OK_ACKNOWLEDGE` cho phép xác nhận lười nên có thể phát sinh duplicate.

Trong Spring, cần chú ý cách listener container thực thi. Tài liệu Spring cảnh báo `AUTO_ACKNOWLEDGE` mặc định không bảo đảm reliability: lỗi trong listener hoặc lúc container shutdown có thể làm message bị mất mà không được redeliver. Với `DefaultMessageListenerContainer`, acknowledgement tự động có thể diễn ra trước khi listener thực thi. Hãy cấu hình transacted session khi cần xử lý tin cậy.

Không coi `CLIENT_ACKNOWLEDGE` là transaction database. Nó chỉ điều khiển acknowledgement của các message thuộc một JMS session. Nếu session đã nhận nhiều message, acknowledge một message có thể xác nhận cả các message trước đó trong session; vì vậy cần hiểu rõ concurrency và cách container sử dụng session.

## 4. JMS transaction xác nhận những gì?

Một transacted JMS session nhóm các thao tác gửi và nhận thuộc cùng session thành một đơn vị công việc:

- `commit()` xác nhận các message đã nhận trong transaction và hoàn tất các message được gửi trong transaction.
- `rollback()` hủy các message gửi chưa commit và phục hồi các message đã nhận để provider có thể giao lại.

Trong Spring listener container, đặt `sessionTransacted=true` để mỗi lần gọi listener chạy trong một JMS transaction cục bộ. Nếu listener hoàn tất bình thường, container commit; nếu listener ném exception, container rollback và message có thể được redeliver.

Ví dụ cấu hình listener container:

```java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
class JmsListenerConfiguration {

    @Bean
    DefaultJmsListenerContainerFactory ordersListenerFactory(
            ConnectionFactory connectionFactory) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("2-8");
        return factory;
    }
}
```

Ví dụ dùng `jakarta.jms`, phù hợp với Spring Framework 6/7. Với Spring Framework 5, dùng namespace `javax.jms`. `setSessionTransacted(true)` làm acknowledgement gắn với commit/rollback của session. Concurrency cần được đặt theo khả năng broker, database và downstream service.

Listener có thể được khai báo bằng `@JmsListener`: 

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class OrderListener {

    @JmsListener(
            destination = "orders.created",
            containerFactory = "ordersListenerFactory"
    )
    public void receive(OrderCreated event) {
        orderService.process(event);
    }
}
```

Ví dụ này chỉ cho thấy listener được gắn với factory có transaction JMS. `OrderCreated` là DTO và `orderService` là service nghiệp vụ do ứng dụng cung cấp. Nếu xử lý thất bại, exception phải được truyền ra ngoài listener để container rollback transaction; không bắt exception rồi trả về bình thường nếu công việc chưa hoàn tất.

## 5. JMS transaction không tự động commit database

Đây là điểm quan trọng nhất khi phân biệt acknowledgement và business completion. `sessionTransacted=true` chỉ quản lý các thao tác JMS trong session. Nó không tự động đưa JDBC/JPA transaction, Redis, HTTP API hoặc filesystem vào cùng transaction.

Giả sử listener thực hiện hai thao tác:

1. Cập nhật trạng thái đơn hàng trong database.
2. Commit JMS session để xác nhận message.

Nếu database commit thành công nhưng JMS commit thất bại, broker có thể giao lại message. Nếu listener xử lý lại từ đầu, đơn hàng có thể bị cập nhật hoặc thanh toán hai lần. Ngược lại, nếu message bị acknowledge trước khi database commit và ứng dụng dừng, broker có thể không giao lại message dù nghiệp vụ chưa được lưu.

Spring mô tả rõ trường hợp database processing đã commit nhưng JMS processing không commit: listener cần có duplicate detection. Vì vậy, việc dùng transaction cho từng resource vẫn cần một chiến lược idempotency ở tầng nghiệp vụ.

### Ví dụ các khoảng lỗi

| Thời điểm lỗi | Trạng thái có thể xảy ra | Cách bảo vệ |
|---|---|---|
| Message được acknowledge trước khi DB commit, process dừng | Broker không giao lại; thay đổi nghiệp vụ chưa tồn tại | Dùng transacted JMS session và commit sau khi listener hoàn tất |
| DB commit xong, JMS commit chưa thành công | Broker redeliver; nghiệp vụ có thể chạy lần hai | Inbox/deduplication key và thao tác nghiệp vụ idempotent |
| Gọi HTTP thanh toán thành công, sau đó listener rollback | Message được giao lại; API có thể bị gọi lần nữa | Idempotency key do hệ thống thanh toán hỗ trợ hoặc outbox/workflow có trạng thái |
| Listener đưa task vào executor trong bộ nhớ rồi trả về | JMS có thể commit dù task chưa chạy; process dừng làm mất task | Lưu job bền vững trước khi trả về hoặc dùng outbox |
| Broker nhận message gửi đi nhưng producer mất phản hồi | Producer không biết send đã thành công hay chưa | Dùng event ID ổn định và consumer deduplicate |

## 6. Định nghĩa business completion trước khi acknowledge

“Hoàn tất nghiệp vụ” phải được định nghĩa theo hợp đồng của từng use case. Ví dụ:

- Với sự kiện tạo đơn hàng, completion có thể là đơn hàng và các dòng chi tiết đã được commit trong database.
- Với yêu cầu thanh toán, completion có thể là trạng thái thanh toán đã được provider xác nhận và lưu vào hệ thống.
- Với tác vụ gửi email, completion có thể chỉ là nhà cung cấp email đã chấp nhận yêu cầu; điều đó chưa chứng minh email đã đến inbox người nhận.
- Với workflow nhiều bước, listener có thể hoàn tất trách nhiệm của mình khi đã ghi trạng thái `ACCEPTED` và tạo các task tiếp theo một cách bền vững. Khi đó không nên hiển thị trạng thái cuối là `COMPLETED` nếu các bước downstream còn đang chạy.

Nên phân biệt các trạng thái như `RECEIVED`, `ACCEPTED`, `PROCESSING`, `COMPLETED`, `FAILED` và `REQUIRES_REVIEW` theo nhu cầu nghiệp vụ. Acknowledgement của JMS là metadata giao nhận; nó không thay thế trạng thái workflow.

## 7. Idempotency: xử lý message lặp mà không lặp tác dụng phụ

Với giao nhận kiểu at-least-once, một message có thể được giao nhiều lần khi listener rollback, mất kết nối hoặc commit không rõ kết quả. Idempotency bảo đảm việc xử lý lại cùng một yêu cầu không tạo thêm tác dụng phụ ngoài kết quả mong muốn.

Producer nên gắn một `eventId` hoặc `commandId` ổn định vào payload/property. Consumer dùng ID đó để nhận diện cùng một sự kiện qua các lần redelivery. Có thể dùng `JMSMessageID` để truy vết ở tầng broker, nhưng với deduplication nghiệp vụ nên ưu tiên ID do ứng dụng tạo và duy trì ổn định qua các lần publish/retry.

Các cách thường dùng:

- Lưu event ID đã xử lý trong bảng inbox có unique constraint.
- Dùng business key và unique constraint để ngăn tạo bản ghi trùng.
- Cập nhật trạng thái nghiệp vụ và ghi nhận event ID trong cùng database transaction.
- Dùng idempotency key khi gọi API bên ngoài nếu nhà cung cấp hỗ trợ.
- Nếu nhận duplicate đã hoàn tất, trả về bình thường để JMS transaction có thể commit và broker ngừng redelivery.

Header `JMSRedelivered` cho biết provider có khả năng đã giao message trước đó; `JMSXDeliveryCount` cho biết số lần giao theo provider. Đây là tín hiệu quan sát và quyết định retry/DLQ, không thay thế khóa idempotency ổn định. Không dùng delivery count làm ID nghiệp vụ.

## 8. Inbox pattern cho message đi vào

Inbox pattern lưu dấu message đã được xử lý cùng transaction với thay đổi nghiệp vụ. Khi broker redeliver sau khi database đã commit, consumer nhận ra event ID đã tồn tại và không chạy lại side effect.

Một bảng inbox có thể có cấu trúc:

| Cột | Mục đích |
|---|---|
| `event_id` | ID ổn định từ producer, có unique constraint |
| `event_type` | Loại sự kiện |
| `received_at` | Thời điểm ghi nhận |
| `processed_at` | Thời điểm hoàn tất bước xử lý |
| `result_status` | Kết quả nghiệp vụ hoặc trạng thái xử lý |

Luồng xử lý:

1. Bắt đầu database transaction.
2. Thử ghi `event_id` vào inbox bằng thao tác atomic có unique constraint.
3. Nếu ID đã tồn tại và đã xử lý, bỏ qua side effect và kết thúc listener thành công.
4. Nếu ID mới, áp dụng thay đổi nghiệp vụ.
5. Ghi outbox event nếu cần phát sự kiện tiếp theo.
6. Commit database transaction.
7. Listener trả về; listener container commit JMS transaction và acknowledge message.

Ví dụ pseudocode Spring:

```java
@JmsListener(
        destination = "orders.created",
        containerFactory = "ordersListenerFactory"
)
public void receive(OrderCreated event) {
    databaseTransaction.executeWithoutResult(status -> {
        // tryInsert phải atomic và dựa trên unique constraint của event_id.
        boolean firstDelivery = inboxRepository.tryInsert(event.eventId());
        if (!firstDelivery) {
            return; // Đã xử lý: listener kết thúc bình thường.
        }

        orderService.apply(event);
        outboxRepository.save(OrderProcessed.from(event));
    });
}
```

Đây là pseudocode minh họa ranh giới transaction; `databaseTransaction` là `TransactionTemplate` dùng transaction manager của database, còn `inboxRepository.tryInsert` cần được triển khai bằng câu lệnh insert atomic và unique constraint. Không triển khai bằng chuỗi `exists()` rồi `save()` không có ràng buộc duy nhất, vì hai consumer có thể cùng kiểm tra trước khi một bên ghi.

Trong ví dụ, database transaction commit trước khi phương thức listener trả về. Sau đó JMS transaction mới commit. Nếu process dừng trong khoảng giữa hai commit, broker có thể redeliver; inbox nhận diện duplicate và listener trả về bình thường. Nhờ vậy thay đổi nghiệp vụ không bị áp dụng hai lần.

## 9. Outbox pattern cho message đi ra

Một nghiệp vụ thường vừa cập nhật database vừa cần phát message cho hệ thống khác. Nếu cập nhật database rồi gửi JMS trực tiếp, có hai khoảng lỗi:

- Database commit thành công nhưng gửi JMS thất bại: trạng thái đã đổi nhưng event không được phát.
- Gửi JMS thành công nhưng database rollback: consumer nhận event mô tả một thay đổi chưa tồn tại.

Transactional outbox giải quyết vấn đề bằng cách ghi thay đổi nghiệp vụ và bản ghi outbox trong cùng một database transaction:

1. Cập nhật dữ liệu nghiệp vụ.
2. Thêm event vào bảng outbox.
3. Commit database transaction.
4. Một relay/publisher đọc outbox và gửi event sang JMS.
5. Sau khi gửi được xác nhận theo hợp đồng, relay đánh dấu bản ghi đã phát.

Nếu relay gửi thành công nhưng dừng trước khi đánh dấu outbox, nó có thể gửi lại event. Consumer vẫn cần inbox/idempotency. Outbox bảo đảm sự kiện được lưu cùng thay đổi nghiệp vụ và có thể phát lại sau lỗi; nó không tự tạo exactly-once delivery đến mọi hệ thống.

## 10. Khi nào cần JTA/XA?

Nếu yêu cầu là JMS acknowledgement và database commit phải thành một giao dịch nguyên tử, có thể dùng distributed transaction JTA/XA:

- Listener container tham gia transaction manager bên ngoài, thường là `JtaTransactionManager`.
- JMS provider phải cung cấp XA-capable `ConnectionFactory` và được đăng ký với transaction coordinator.
- Database phải dùng XA datasource nếu cập nhật database cũng cần tham gia transaction.
- Transaction coordinator quản lý prepare/commit/rollback giữa các resource.

Với XA, nếu một resource không commit được, coordinator có thể yêu cầu rollback các resource tham gia theo protocol. Điều này giảm cửa sổ không nhất quán giữa JMS và database, nhưng tăng độ phức tạp, chi phí transaction log và công việc vận hành recovery.

Không phải JMS provider nào cũng hỗ trợ XA; không thể có atomic transaction chỉ bằng cách đặt `@Transactional` trên listener. Spring khuyến nghị cân nhắc local JMS transaction cùng duplicate detection nếu hệ thống chấp nhận xử lý duplicate có kiểm soát. Dùng XA khi yêu cầu atomic thực sự cần thiết và hạ tầng hỗ trợ đầy đủ.

## 11. Retry, redelivery và dead-letter

Retry phù hợp với lỗi tạm thời như database timeout hoặc downstream service tạm mất kết nối. Lỗi dữ liệu vĩnh viễn như JSON sai, schema không hỗ trợ hoặc business rejection không nên bị retry vô hạn.

Một chính sách vận hành thường gồm:

- Giới hạn số lần retry hoặc redelivery.
- Dùng delay/backoff nếu broker/provider hỗ trợ.
- Ghi nhận event ID, `JMSMessageID`, correlation ID, destination, delivery count và exception.
- Chuyển poison message sang dead-letter queue hoặc quarantine sau ngưỡng đã định.
- Cung cấp quy trình điều tra, sửa dữ liệu và phát lại message.

Trong Spring, khi listener ném exception trong `sessionTransacted=true`, container rollback JMS session. Broker có thể redeliver theo chính sách của provider. Nếu listener bắt exception rồi ghi log nhưng không ném lại, container có thể coi invocation thành công và commit message dù nghiệp vụ chưa hoàn tất.

Không dùng `JMSRedelivered` hoặc delivery count để quyết định rằng side effect chắc chắn đã xảy ra. Chúng cho biết lịch sử giao nhận, còn inbox/business key mới xác định trạng thái nghiệp vụ đã được commit hay chưa.

## 12. Quan sát trạng thái và truy vết

Để phân biệt giao nhận và nghiệp vụ, cần ghi nhận hai nhóm thông tin:

**Tầng messaging:**

- Destination và consumer/listener ID.
- `JMSMessageID`, `JMSCorrelationID`, `JMSRedelivered`, `JMSXDeliveryCount`.
- Thời điểm nhận, commit/rollback, retry và DLQ.
- Queue depth, tuổi message cũ nhất và tốc độ tiêu thụ.

**Tầng nghiệp vụ:**

- `eventId`/`commandId` ổn định.
- Business entity ID như `orderId` hoặc `paymentId`.
- Trạng thái `ACCEPTED`, `PROCESSING`, `COMPLETED` hoặc `FAILED`.
- Thời điểm database commit và outbox publish.
- Lý do thất bại và hệ thống downstream liên quan.

Dùng correlation ID để nối log qua nhiều service; dùng event ID để deduplicate; dùng business ID để tra cứu trạng thái nghiệp vụ. Ba ID này có thể trùng theo quy ước hệ thống nhưng có mục đích khác nhau.

Không ghi toàn bộ payload nhạy cảm hoặc secret vào log. Metrics nên phân biệt số message đã nhận, số listener invocation thành công, số JMS commit/rollback, số nghiệp vụ hoàn tất và số message vào DLQ.

## 13. Kiểm thử các ranh giới xác nhận

Kiểm thử đơn vị listener chưa đủ để chứng minh giao nhận tin cậy. Cần kiểm thử integration với JMS provider hoặc broker phù hợp và database thực tế:

1. Listener thành công: database commit, JMS transaction commit, message không còn redelivery.
2. Listener ném exception trước DB commit: DB rollback, JMS rollback, broker redeliver.
3. Database commit thành công rồi mô phỏng lỗi trước JMS commit: message redeliver nhưng inbox ngăn side effect lặp.
4. Gửi message downstream thành công rồi relay dừng trước khi đánh dấu outbox: event được gửi lại nhưng consumer downstream deduplicate.
5. Gửi message sai schema: listener thất bại theo chính sách và message cuối cùng đi vào DLQ/quarantine.
6. Gửi hai message có cùng event ID đồng thời: unique constraint chỉ cho một transaction xử lý nghiệp vụ.
7. Broker restart trong lúc listener đang xử lý: transaction chưa commit được phục hồi hoặc redeliver theo provider.
8. Shutdown container trong lúc xử lý: message chưa commit không bị coi là business completion.

Khi kiểm thử failure window, nên tạo điểm dừng rõ ràng giữa database commit và JMS commit. Chỉ kiểm tra happy path sẽ không phát hiện được lỗi duplicate hoặc mất message ở hai ranh giới này.

## 14. Lỗi thiết kế thường gặp

- **Coi broker acknowledgement là business completion:** message có thể được xác nhận dù database hoặc downstream chưa hoàn tất.
- **Dùng `AUTO_ACKNOWLEDGE` cho luồng cần reliability:** Spring cảnh báo mode mặc định không bảo đảm redelivery khi listener lỗi hoặc container dừng.
- **Cho rằng `sessionTransacted=true` bao gồm database:** local JMS transaction chỉ quản lý thao tác JMS trong session.
- **Dùng `@Transactional` rồi giả định JMS và DB atomic:** cần transaction manager chung phù hợp hoặc XA; hai local transaction có thể commit độc lập.
- **Commit database rồi không có inbox:** redelivery có thể lặp side effect sau khi JMS commit thất bại.
- **Gọi HTTP/payment trong listener mà không idempotency:** rollback có thể khiến API bị gọi lại.
- **Ack sau khi chỉ đẩy task vào executor in-memory:** process dừng có thể làm mất công việc chưa được lưu bền vững.
- **Dùng `JMSMessageID` làm business key duy nhất:** provider ID phục vụ truy vết; event ID của ứng dụng phù hợp hơn cho deduplication xuyên lần publish.
- **Bắt exception rồi trả về bình thường:** container có thể commit message trong khi nghiệp vụ chưa xong.
- **Cho rằng redelivery nghĩa là lần trước chắc chắn đã chạy:** broker có thể giao lại message trước khi listener bắt đầu hoặc sau một lỗi chưa tạo side effect.
- **Gọi một workflow đang chạy là `COMPLETED` ngay khi đã enqueue bước tiếp theo:** trạng thái nghiệp vụ cần phản ánh đúng mức hoàn tất đã cam kết.

## 15. Quy trình thiết kế listener đáng tin cậy

1. Định nghĩa chính xác business completion của use case và trạng thái nào được phép công bố cho hệ thống khác.
2. Chọn `sessionTransacted=true` hoặc transaction manager phù hợp cho listener cần redelivery đáng tin cậy.
3. Xác định resource nào nằm trong JMS transaction và resource nào có transaction riêng.
4. Tạo event ID ổn định và thiết kế inbox/unique constraint cho message đầu vào.
5. Ghi thay đổi nghiệp vụ và outbox event trong cùng database transaction nếu cần phát message tiếp theo.
6. Để listener chỉ trả về thành công sau khi trách nhiệm bền vững của nó hoàn tất.
7. Thiết kế retry có giới hạn, DLQ và quy trình phát lại.
8. Nếu bắt buộc atomic giữa JMS và database, đánh giá JTA/XA với resource XA thực sự.
9. Kiểm thử các điểm lỗi giữa DB commit, JMS commit, external API và outbox publish.
10. Theo dõi acknowledgement/rollback riêng với trạng thái nghiệp vụ và thời gian hoàn tất.

## 16. Kết luận

Acknowledgement xác nhận việc giao nhận message ở tầng JMS. Business completion xác nhận kết quả nghiệp vụ đã được lưu và đạt điều kiện hoàn tất đã định nghĩa. Hai mốc này chỉ được bảo vệ cùng nhau khi transaction boundary bao phủ đúng các resource hoặc ứng dụng có cơ chế xử lý khoảng lỗi.

Với Spring JMS, `sessionTransacted=true` giúp listener rollback message khi xử lý thất bại và cho phép broker redeliver. Database local transaction vẫn độc lập, nên cần inbox/idempotency để chống duplicate và outbox để phát sự kiện sau khi dữ liệu đã commit. Dùng JTA/XA khi cần atomic giữa nhiều resource và hạ tầng hỗ trợ. Hãy kiểm thử rõ các failure window thay vì chỉ kiểm tra listener chạy thành công.

## Tài liệu tham khảo

- [Jakarta Messaging 3.1 — Message acknowledgment and transactions](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
- [Spring Framework Reference — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
- [Spring Framework Reference — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)