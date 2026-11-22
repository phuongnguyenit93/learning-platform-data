# JMSRedelivered, số lần giao lại và thông điệp lỗi lặp

## Mục tiêu

Trong JMS, một message có thể được giao cho consumer nhưng chưa được xác nhận hoàn tất. Khi transaction rollback, session recover hoặc kết nối gặp sự cố, provider có thể giao lại message. Hiện tượng này gọi là redelivery.

Jakarta Messaging cung cấp hai thông tin giúp consumer nhận biết redelivery:

- `JMSRedelivered`: header boolean do provider đặt để báo message đang được giao lại.
- `JMSXDeliveryCount`: property số nguyên cho biết số lần provider đã giao message.

Khi một message liên tục thất bại vì payload không hợp lệ hoặc lỗi nghiệp vụ cố định, nó có thể trở thành poison message (thông điệp lỗi lặp). Nếu consumer cứ rollback và nhận lại vô hạn, một message có thể chiếm tài nguyên, làm giảm throughput và gây vòng lặp lỗi.

Sau bài này, bạn có thể:

- Phân biệt redelivery với producer gửi trùng một event.
- Đọc và diễn giải `JMSRedelivered` cùng `JMSXDeliveryCount`.
- Hiểu acknowledgement, rollback và cấu hình `sessionTransacted` trong Spring JMS.
- Phân loại lỗi tạm thời và lỗi không thể khắc phục bằng retry.
- Thiết kế retry có giới hạn, dead-letter queue (DLQ), quarantine và idempotency.
- Giám sát số lần giao lại và điều tra message gây lỗi.

## 1. Redelivery là gì?

Redelivery xảy ra khi provider đã giao message cho consumer nhưng message chưa được xác nhận hoàn tất. Tùy acknowledgement mode và transaction, message có thể được giao lại sau rollback, recover hoặc sự cố khiến acknowledgement không hoàn tất.

Ví dụ với Queue:

~~~text
orders.queue
     |
     v
Consumer nhận OrderCreated
     |
     v
Xử lý thất bại
     |
     v
JMS transaction rollback
     |
     v
Broker giao lại message
     |
     v
Consumer nhận lại cùng message
~~~

Các nguyên nhân phổ biến:

- Listener ném exception trong một JMS transaction và container rollback session.
- Ứng dụng gọi `Session.rollback()` hoặc `Session.recover()` theo acknowledgement mode tương ứng.
- Process hoặc kết nối gặp sự cố trước khi acknowledgement được xác nhận.
- Transaction commit thất bại sau khi nghiệp vụ đã thực hiện một phần.
- Consumer bị dừng trong lúc message chưa được xác nhận.

Redelivery không có nghĩa producer đã gửi một message mới. Nó thường là lần giao tiếp theo của message đã có trong broker.

## 2. JMSRedelivered

`JMSRedelivered` là header boolean trong `jakarta.jms.Message`. Provider đặt header này trước khi giao message cho consumer.

~~~java
boolean redelivered = message.getJMSRedelivered();
~~~

Ý nghĩa:

- `false`: provider không đánh dấu lần giao hiện tại là redelivery.
- `true`: provider cho biết message đang được giao lại; consumer nên đề phòng việc xử lý trước đó đã chạy nhưng acknowledgement chưa hoàn tất.

Theo Jakarta Messaging, khi provider giao lại một message, nhìn chung provider phải đặt `JMSRedelivered=true`. Giá trị `true` cho biết message có khả năng đã được giao trước đó và chưa được xác nhận; header không cho biết nguyên nhân, exception hay consumer trước đó.

Header này do provider quản lý. Ứng dụng không được dùng `setJMSRedelivered()` để tự đánh dấu message gửi đi. Header không có ý nghĩa do client thiết lập khi send.

**Không dùng cờ này làm cơ chế idempotency duy nhất.** Một event nghiệp vụ có thể được producer gửi lại thành một JMS message mới; message mới có thể có `JMSRedelivered=false` dù cùng event đã được xử lý trước đó. Consumer vẫn cần event ID ổn định và deduplication.

## 3. JMSXDeliveryCount

`JMSXDeliveryCount` là property chuẩn do provider đặt khi nhận message. Trong Jakarta Messaging 2.0 trở lên, property này là bắt buộc.

~~~java
int deliveryCount = message.getIntProperty("JMSXDeliveryCount");
~~~

Quy ước theo Jakarta Messaging:

| Giá trị | Ý nghĩa |
|---:|---|
| `1` | Lần giao đầu tiên |
| `2` | Message đã được giao lại ít nhất một lần |
| `3` trở lên | Message đã trải qua nhiều lần giao |

Nếu `JMSRedelivered=true`, `JMSXDeliveryCount` phải có giá trị từ 2 trở lên.

Property này hữu ích để phát hiện message bị giao lại nhiều lần, ghi log và metric, phân tích message có xu hướng trở thành poison message, và hỗ trợ quyết định vận hành khi phối hợp với retry policy của broker.

### 3.1. Delivery count không phải bộ đếm lịch sử tuyệt đối

Jakarta Messaging không bảo đảm `JMSXDeliveryCount` luôn chính xác tuyệt đối. Provider không bắt buộc phải ghi bền vững giá trị này qua mọi sự cố; sau một số loại failure hoặc broker recovery, số đếm có thể không phản ánh đầy đủ mọi lần giao trước đó.

Vì vậy:

- Dùng count để quan sát và hỗ trợ quyết định retry.
- Không dùng count như số lần xử lý nghiệp vụ chính xác để tính tiền hoặc quota.
- Không dùng count làm bằng chứng rằng một event chưa từng được xử lý.
- Dùng application event ID và bảng inbox/unique constraint để bảo vệ nghiệp vụ khỏi duplicate.

Property này được provider đặt khi receive. Jakarta Messaging không định nghĩa hành vi portable khi dùng property đó trong message selector; đừng dựa vào selector trên delivery count để xây dựng giới hạn retry. Hãy cấu hình maximum redelivery attempts bằng policy của broker hoặc thực hiện quarantine có kiểm soát.

## 4. Redelivery khác duplicate publication như thế nào?

Hai tình huống có thể tạo ra cùng một event nghiệp vụ nhiều lần nhưng có nguyên nhân khác nhau:

| Tình huống | Bản chất | Dấu hiệu thường gặp |
|---|---|---|
| Redelivery | Broker giao lại một message vì lần giao trước chưa được xác nhận | `JMSRedelivered=true`, count từ 2 trở lên |
| Duplicate publication | Producer gửi lại cùng event nghiệp vụ thành một message mới | Message mới có thể có count = 1 và redelivered = false |
| Consumer xử lý lặp do retry nội bộ | Listener tự gọi lại nghiệp vụ mà không nhận message mới | Delivery metadata có thể không đổi |

`JMSMessageID` do provider cấp cho từng message được gửi. Nếu producer retry bằng cách gửi lại payload, message mới có thể có `JMSMessageID` khác. Vì vậy, hãy thêm application event ID ổn định, ví dụ `eventId`, vào payload hoặc property.

~~~java
jmsTemplate.convertAndSend(
    "orders.queue",
    orderCreated,
    message -> {
        message.setStringProperty("eventId", orderCreated.eventId());
        return message;
    }
);
~~~

Nếu producer gửi lại cùng một event, nó phải giữ nguyên `eventId`. Consumer dùng ID đó để nhận diện cùng một nghiệp vụ dù provider tạo message mới.

## 5. Acknowledgement và rollback quyết định redelivery

Redelivery phụ thuộc cách consumer xác nhận message.

### 5.1. AUTO_ACKNOWLEDGE

Với Spring listener container, không nên mặc định `AUTO_ACKNOWLEDGE` là đủ tin cậy cho xử lý nghiệp vụ. Hành vi acknowledgement của container có thể khiến message được xác nhận trước khi listener hoàn tất. Khi listener thất bại, message có thể không được giao lại.

Spring cảnh báo rằng chế độ mặc định này không cung cấp bảo đảm reliability phù hợp cho listener cần xử lý tin cậy. Với các trường hợp đó, nên dùng transacted session.

### 5.2. CLIENT_ACKNOWLEDGE

Ở chế độ client acknowledgement, ứng dụng hoặc container xác nhận message theo cấu hình. `Session.recover()` có thể yêu cầu giao lại các message chưa xác nhận.

Acknowledgement áp dụng theo semantics của Session; nó không phải transaction phối hợp tự động với database. Việc gửi response message và các thao tác khác trên Session cũng không có cùng phạm vi nguyên tử như một transacted Session.

### 5.3. Transacted JMS Session

Với Spring listener container, đặt `sessionTransacted=true` để mỗi lần gọi listener chạy trong một local JMS transaction:

~~~java
import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Bean
DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory) {
    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setSessionTransacted(true);
    factory.setConcurrency("2-6");
    return factory;
}
~~~

Khi listener hoàn tất bình thường, container commit JMS transaction. Khi listener execution thất bại, Spring rollback việc nhận message; broker có thể giao lại message.

~~~text
Listener nhận message trong JMS transaction
             |
             v
       Thực hiện xử lý
          /       \
         /         \
      Thành công   Exception
         |            |
         v            v
      COMMIT        ROLLBACK
         |            |
         v            v
  Message được    Broker có thể
  xác nhận        redeliver message
~~~

Đây là local JMS transaction. Nếu listener còn cập nhật database, database transaction là tài nguyên riêng trừ khi ứng dụng dùng XA/JTA. Database có thể đã commit trong khi JMS transaction rollback; vì vậy cần idempotency hoặc inbox/deduplication.

## 6. Đọc redelivery metadata trong @JmsListener

Nếu method chỉ nhận payload như `String` hoặc domain object, code không trực tiếp truy cập được toàn bộ JMS headers và properties. Khi cần đọc redelivery metadata, nhận `jakarta.jms.Message`:

~~~java
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {

    private final OrderProcessor processor;

    public OrderListener(OrderProcessor processor) {
        this.processor = processor;
    }

    @JmsListener(destination = "orders.queue")
    public void consume(Message message) {
        try {
            boolean redelivered = message.getJMSRedelivered();
            int deliveryCount = message.getIntProperty("JMSXDeliveryCount");
            String eventId = message.getStringProperty("eventId");

            if (!(message instanceof TextMessage textMessage)) {
                throw new IllegalArgumentException("Expected TextMessage");
            }

            String payload = textMessage.getText();

            System.out.printf(
                "eventId=%s redelivered=%s deliveryCount=%d%n",
                eventId, redelivered, deliveryCount
            );

            processor.process(eventId, payload);
        }
        catch (JMSException ex) {
            throw new IllegalStateException("Cannot inspect JMS message", ex);
        }
    }
}
~~~

Đây là đoạn tích hợp trong ứng dụng Spring; `OrderProcessor` là service nghiệp vụ. Khi `processor.process` ném runtime exception, exception được truyền ra để container xử lý theo transaction policy. Không bắt exception rồi chỉ ghi log và return nếu muốn broker retry, vì return bình thường khiến container có thể commit message.

Nếu cần xử lý payload đã chuyển đổi tự động, có thể dùng converter và method argument phù hợp. Tuy nhiên, hãy giữ một cách truy cập JMS `Message` khi cần metadata do provider đặt.

## 7. Spring ErrorHandler không phải retry policy của broker

Spring listener container có thể cấu hình `ErrorHandler` để nhận các exception chưa được xử lý trong quá trình listener execution:

~~~java
factory.setErrorHandler(error ->
    System.err.println("JMS listener failed: " + error.getMessage())
);
~~~

`ErrorHandler` hữu ích cho logging, alert và tích hợp quan sát lỗi. Nó không tự định nghĩa số lần broker giao lại message, delay giữa các lần giao hay DLQ.

Cần phân biệt ba lớp:

| Cơ chế | Trách nhiệm |
|---|---|
| Listener exception + transacted Session | Làm transaction nhận message rollback |
| Spring `ErrorHandler` | Quan sát/xử lý exception chưa được listener xử lý |
| Broker redelivery policy | Quyết định số lần giao lại, delay và xử lý sau khi hết lần thử |

Spring listener container có thể bắt exception và ghi log thay vì truyền exception trực tiếp tới JMS provider. Với transacted session, container vẫn rollback theo chính sách xử lý listener failure. Do đó, không nên dựa vào việc broker nhìn thấy exception Java để quyết định retry; hãy cấu hình transaction và broker policy rõ ràng.

## 8. Thông điệp lỗi lặp (poison message)

Poison message là message khiến consumer thất bại lặp lại mỗi lần được giao. Nguyên nhân thường mang tính cố định:

- Payload sai schema hoặc thiếu trường bắt buộc.
- Giá trị enum hoặc version không được consumer hỗ trợ.
- Dữ liệu tham chiếu không tồn tại và không thể tự xuất hiện.
- Message vượt giới hạn kích thước hoặc không đúng loại.
- Lỗi nghiệp vụ không thể sửa bằng cách thử lại.
- Bug trong code khiến cùng một message luôn kích hoạt exception.

Nếu mọi exception đều làm rollback, broker có thể liên tục giao lại poison message. Hậu quả:

- Một consumer liên tục xử lý cùng một message.
- Message hợp lệ phía sau bị chậm hoặc bị đói, tùy broker và concurrency.
- Log và alert bị lặp với tốc độ cao.
- CPU, database và downstream service bị tiêu hao.
- Queue backlog tăng và thời gian xử lý message hợp lệ kéo dài.

Không phải mọi lỗi đều là poison message. Database timeout hoặc dịch vụ phụ thuộc tạm ngừng thường có thể khắc phục bằng retry. Payload không hợp lệ hoặc lỗi logic cố định thường cần quarantine hoặc xử lý thủ công.

## 9. Phân loại lỗi trước khi retry

| Loại lỗi | Ví dụ | Hành động phù hợp |
|---|---|---|
| Tạm thời (transient) | Broker hoặc database chập chờn, HTTP 503, timeout ngắn | Rollback và retry có delay |
| Có thể khắc phục sau | Dịch vụ tham chiếu đang khởi động, tài nguyên chưa sẵn sàng | Retry có giới hạn và backoff |
| Không thể khắc phục bằng retry | JSON sai cú pháp, thiếu event ID, payload sai schema | Chuyển quarantine/DLQ và cảnh báo |
| Lỗi lập trình | Null handling sai, mapping bug | Sửa code; giới hạn redelivery để không lặp vô hạn |
| Duplicate nghiệp vụ | Event đã được áp dụng trước đó | Deduplicate rồi hoàn tất message bình thường |

Đừng retry mọi exception theo cùng một cách. Retry lỗi vĩnh viễn chỉ kéo dài thời gian xử lý và tạo thêm tải. Ngược lại, đưa lỗi tạm thời vào DLQ quá sớm có thể làm gián đoạn nghiệp vụ không cần thiết.

## 10. Giới hạn redelivery và dead-letter queue

Jakarta Messaging không chuẩn hóa một chính sách chung cho:

- Số lần giao lại tối đa.
- Delay hoặc backoff giữa các lần giao.
- Dead-letter queue và tên destination dead-letter.
- Quy tắc chuyển message khi hết số lần thử.
- Chính sách giữ, hết hạn và replay message trong DLQ.

Các chính sách này phụ thuộc JMS provider/broker. Cần cấu hình bằng broker console, CLI, management API hoặc file cấu hình tương ứng với sản phẩm đang dùng.

Một chính sách thường có các thành phần:

1. Maximum delivery attempts: số lần giao tối đa theo cách đếm của broker.
2. Redelivery delay: khoảng chờ trước lần giao lại.
3. Backoff: tăng dần khoảng chờ khi thất bại liên tục.
4. Dead-letter destination: nơi broker chuyển message sau khi hết số lần thử.
5. Expiry/retention: thời gian giữ message trong DLQ.
6. Alert/monitoring: cảnh báo khi DLQ có message mới hoặc tăng bất thường.

Hãy kiểm tra cách broker tính số lần thử: có tính lần giao đầu tiên hay chỉ tính retry. Không giả định `JMSXDeliveryCount` và cấu hình maximum attempts của broker luôn có cùng cách đếm hoặc luôn khớp tuyệt đối.

### 10.1. Dead-letter queue và quarantine

DLQ là nơi giữ message không thể tiếp tục xử lý theo luồng thông thường sau khi broker áp dụng redelivery policy. Quarantine queue có thể là một destination do ứng dụng hoặc đội vận hành thiết kế để giữ message cần kiểm tra.

Khi chuyển message sang DLQ/quarantine, cần bảo toàn metadata:

- Application event ID.
- Destination nguồn.
- Thời điểm lỗi đầu tiên và gần nhất.
- Loại exception hoặc mã lỗi.
- Số lần giao lại quan sát được.
- Consumer/service đã xử lý.
- Correlation ID hoặc trace ID.

Không ghi payload nhạy cảm đầy đủ vào log nếu không cần thiết. DLQ thường chứa dữ liệu nghiệp vụ thật và cần quyền truy cập, retention, audit phù hợp.

## 11. Chuyển poison message sang quarantine an toàn

Có hai cách phổ biến:

**Broker-managed dead lettering:** broker tự chuyển message khi đạt giới hạn redelivery. Đây thường là lựa chọn dễ quản lý nhất vì broker điều phối việc giao lại và chuyển DLQ theo policy.

**Application-managed quarantine:** listener phân loại lỗi vĩnh viễn rồi gửi message sang quarantine destination. Nếu ứng dụng tự thực hiện, việc gửi bản quarantine và xác nhận message gốc cần được phối hợp an toàn. Nếu hai thao tác không nằm trong cùng JMS transaction hoặc cơ chế atomic được hỗ trợ, crash giữa chừng có thể làm mất hoặc nhân đôi message.

Một quy trình quarantine nên:

1. Xác định lỗi là permanent, không phải lỗi hạ tầng tạm thời.
2. Ghi lại event ID, message ID, payload cần thiết và thông tin lỗi.
3. Gửi message sang quarantine destination hoặc gọi broker-supported dead-letter mechanism.
4. Chỉ hoàn tất message gốc sau khi thao tác quarantine được xác nhận an toàn.
5. Tạo alert để người vận hành kiểm tra, sửa dữ liệu hoặc replay.

Không nên bắt exception rồi return bình thường mà không lưu/quarantine message. Trong transacted listener, return bình thường có thể commit receipt và loại message khỏi luồng retry.

## 12. Retry có backoff

Retry liên tục không có delay có thể tạo hot loop: consumer nhận message, thất bại, rollback và nhận lại ngay, lặp nhanh trong khi nguyên nhân chưa thay đổi.

Backoff làm chậm nhịp retry. Một chiến lược thường dùng:

| Lần thử | Khoảng chờ ví dụ |
|---:|---:|
| 1 | 1 giây |
| 2 | 2 giây |
| 3 | 4 giây |
| 4 | 8 giây |
| 5 | Chuyển DLQ/quarantine theo policy |

Các giá trị chỉ là ví dụ thiết kế, không phải mặc định của JMS. Hãy cấu hình theo SLA, khả năng chịu tải của broker và thời gian phục hồi dự kiến của dependency.

**Phân biệt Spring BackOff với message redelivery policy:** `DefaultMessageListenerContainer.setBackOff(...)` điều khiển khoảng chờ giữa các lần container phục hồi kết nối hoặc thiết lập listener thất bại. Nó không tự đặt số lần retry cho một poison message. Message-level redelivery delay và maximum attempts thường được cấu hình tại broker/provider.

## 13. Idempotency khi message được giao lại

Một listener tin cậy phải giả định cùng một event có thể được xử lý nhiều lần. Redelivery có thể xảy ra sau khi nghiệp vụ đã hoàn tất nhưng acknowledgement/commit chưa hoàn tất.

Dùng application event ID ổn định:

~~~java
@Transactional(transactionManager = "dbTransactionManager")
public void apply(OrderCreated event) {
    boolean firstDelivery = inboxRepository.tryInsert(event.eventId());

    if (!firstDelivery) {
        return;
    }

    orderProjection.apply(event);
}
~~~

Đây là service fragment. `tryInsert` cần dựa trên unique constraint hoặc câu lệnh insert-if-absent nguyên tử. Ghi inbox và cập nhật dữ liệu nghiệp vụ phải cùng database transaction.

Nếu cùng event đến lại:

- Inbox insert bị unique constraint từ chối hoặc báo đã tồn tại.
- Listener bỏ qua tác động nghiệp vụ đã áp dụng.
- Listener trả về bình thường.
- JMS transaction có thể commit để message không bị retry thêm.

Idempotency bảo vệ nghiệp vụ khỏi redelivery và duplicate publication. Nó không thay thế retry policy hoặc DLQ; message lỗi vĩnh viễn vẫn cần được quarantine.

## 14. Phân biệt lỗi xử lý message với lỗi kết nối broker

Spring `DefaultMessageListenerContainer` có cơ chế recovery khi kết nối hoặc listener setup thất bại. Có thể cấu hình recovery interval hoặc `BackOff` để điều chỉnh thời gian container thử kết nối lại.

Đây là một loại retry khác:

| Tình huống | Thành phần chịu trách nhiệm |
|---|---|
| Broker ngừng hoạt động, container không tạo được consumer | Spring listener container recovery |
| Listener xử lý một message và ném exception trong transacted session | JMS rollback và broker redelivery |
| Message lỗi lặp vượt maximum attempts | Broker redelivery policy và DLQ |
| Event nghiệp vụ được gửi lại thành message mới | Producer retry/idempotency |
| Cùng event được xử lý lại sau redelivery | Consumer inbox/deduplication |

Khi vận hành, đừng tăng connection recovery BackOff để xử lý poison message. Hai cơ chế có trigger và mục đích khác nhau.

## 15. Quan sát và điều tra redelivery

Nên ghi nhận các trường sau khi listener bắt đầu xử lý:

- `JMSMessageID`: ID do provider cấp cho message.
- `JMSCorrelationID`: ID liên kết request/reply hoặc luồng nghiệp vụ.
- `JMSRedelivered`: cờ redelivery.
- `JMSXDeliveryCount`: số lần giao do provider báo.
- `eventId`: ID ổn định do ứng dụng tạo.
- Destination và consumer/service.
- Thời gian xử lý, kết quả và mã lỗi.

Các metric nên theo dõi:

- Tổng số message nhận.
- Tỷ lệ message redelivered.
- Phân bố `JMSXDeliveryCount`.
- Số message trong DLQ/quarantine.
- Tuổi của message cũ nhất.
- Tỷ lệ xử lý thành công/thất bại.
- Số lần rollback theo listener.
- Số lần kết nối broker recovery.

Cảnh báo khi delivery count tăng bất thường, DLQ xuất hiện message mới, hoặc một event ID lặp lại liên tục. Log nên có correlation ID để nối được producer, consumer và các lần thử.

## 16. Lỗi thường gặp

- **Chỉ đọc `JMSRedelivered` rồi cho rằng đã chống duplicate:** cờ chỉ báo redelivery; producer vẫn có thể gửi lại cùng event thành message mới.
- **Dùng `JMSXDeliveryCount` làm event ID:** delivery count không duy nhất và có thể không chính xác tuyệt đối sau failure.
- **Cho rằng count từ 2 nghĩa là listener chắc chắn đã xử lý nghiệp vụ:** nó chỉ nói provider đã giao message nhiều lần; không chứng minh phần xử lý trước đó đã commit.
- **Cho rằng count = 1 chứng minh event chưa từng được xử lý:** producer có thể gửi cùng event thành message mới.
- **Dùng AUTO_ACKNOWLEDGE cho listener cần reliability mà không kiểm tra container semantics:** message có thể bị xác nhận trước listener execution.
- **Bắt exception rồi return bình thường khi muốn retry:** container có thể commit message.
- **Retry vô hạn với lỗi payload vĩnh viễn:** tạo poison-message loop và làm tăng backlog.
- **Chuyển DLQ ngay khi gặp lỗi timeout tạm thời:** message có thể bị loại khỏi luồng xử lý dù dependency sớm phục hồi.
- **Cho rằng Spring `setBackOff` là maximum message retry:** nó phục vụ recovery của listener container, không phải broker delivery policy.
- **Tự gửi quarantine rồi ack message gốc bằng hai thao tác không atomic:** crash giữa hai thao tác có thể làm mất hoặc nhân đôi message.
- **Xóa message khỏi DLQ mà không lưu dấu vết:** làm mất dữ liệu điều tra và khả năng replay.
- **Log toàn bộ payload nhạy cảm:** có thể làm lộ dữ liệu nghiệp vụ hoặc thông tin cá nhân.

## 17. Checklist triển khai

- [ ] Listener có thể đọc `JMSRedelivered` và `JMSXDeliveryCount` khi cần.
- [ ] Đã hiểu lần giao đầu tiên có count = 1; từ 2 trở lên là redelivery.
- [ ] Không dùng delivery count làm ID hoặc bằng chứng chính xác về số lần nghiệp vụ đã chạy.
- [ ] Producer tạo application event ID ổn định và giữ nguyên khi retry.
- [ ] Consumer có inbox/deduplication hoặc xử lý idempotent.
- [ ] Listener cần reliability dùng transacted JMS Session hoặc transaction phù hợp.
- [ ] Exception cần retry được truyền ra để container rollback.
- [ ] Lỗi transient và permanent được phân loại riêng.
- [ ] Broker có maximum redelivery attempts và delay/backoff phù hợp.
- [ ] Có DLQ/quarantine destination và quy trình xử lý/replay.
- [ ] Đã phân biệt broker redelivery policy với Spring connection recovery BackOff.
- [ ] Việc chuyển quarantine và xác nhận message gốc được phối hợp an toàn.
- [ ] Có metric và alert cho redelivery, rollback, backlog và DLQ.
- [ ] Đã kiểm thử listener exception, rollback, broker restart, redelivery, poison message và duplicate publication.

## 18. Tài liệu tham khảo

- [Jakarta Messaging 3.1 — JMSRedelivered](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html#jmsredelivered)
- [Jakarta Messaging 3.1 — JMSXDeliveryCount](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html#jmsxdeliverycount)
- [Jakarta Messaging 3.1 — Receiving messages asynchronously](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html#receiving-messages-asynchronously)
- [Jakarta Messaging 3.1 — Reliability](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html#reliability)
- [Spring Framework 7 — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
- [Spring Framework 7 — AbstractMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html)
- [Spring Framework 7 — DefaultMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)
- [Spring Framework 7 — DefaultJmsListenerContainerFactory Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html)
