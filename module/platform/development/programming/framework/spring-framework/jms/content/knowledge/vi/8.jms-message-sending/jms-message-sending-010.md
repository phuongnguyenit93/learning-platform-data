# Xác nhận gửi thành công khác với xử lý nghiệp vụ thành công trong Spring JMS

**Bối cảnh:** Spring Framework – JMS, nhóm **Gửi thông điệp**. Bài giải thích các mức “đã thành công” của producer, JMS provider/broker, consumer, transaction và nghiệp vụ. Ví dụ áp dụng cho Java 17+, Spring Framework 6.x / Spring Boot 3.x cùng Jakarta Messaging (`jakarta.jms`). Broker minh họa là Apache ActiveMQ Artemis; chi tiết retry, DLQ, persistence và failover luôn phải đối chiếu với phiên bản/cấu hình broker được dùng.

**Luận điểm:** `JmsTemplate.send(...)` hoặc `convertAndSend(...)` trả về bình thường nghĩa là thao tác gửi JMS đã hoàn tất theo ngữ cảnh transaction và mức bảo đảm của provider; **nó không phải xác nhận rằng nghiệp vụ ở consumer đã hoàn thành**. Nếu producer muốn biết đơn hàng đã được lập hóa đơn, kho đã giữ hàng hay khoản thanh toán đã được thu, hệ thống phải có một **nguồn kết quả nghiệp vụ và cơ chế thông báo/tra cứu kết quả** riêng.

## 1. Hai câu khẳng định trông giống nhau nhưng hoàn toàn khác

Trong hệ thống bán hàng, Order Service phát lệnh `CreateInvoice` sang Billing Service.

- **“Đã gửi thành công”**: bên gửi đã gọi JMS API và thao tác gửi hoàn tất theo hợp đồng JMS/provider (hoặc transaction JMS đã được commit, nếu có). Điều này nói về **message transport**, có thể chưa có consumer online.
- **“Đã xử lý nghiệp vụ thành công”**: Billing Service đã xác thực yêu cầu, áp dụng đúng rule, bảo vệ khỏi trùng, và ghi nhận hóa đơn thành công theo **transaction ở hệ thống có thẩm quyền**. Điều này nói về **business state**.
- **“Bên gửi đã biết kết quả”**: bên gửi nhận một business completion event, một reply có hợp đồng rõ, hoặc tra cứu trạng thái từ nguồn đáng tin cậy. Đây là **một bước khác nữa**: kết quả có thể đã xong nhưng thông báo về đến producer bị mất.

~~~text
Order Service / Producer
  T1  build message: eventId=evt-42
  T2  JmsTemplate.convertAndSend("billing.commands", ...)
  T3  send returns                    ← publish acknowledgment
                   │
                   ▼
JMS Provider / Broker
  T4  accept / persist / route theo QoS & transaction
  T5  deliver cho consumer            ← delivery
                   │
                   ▼
Billing Service / Consumer
  T6  @JmsListener receives           ← listener bắt đầu
  T7  validate + deduplicate
  T8  DB COMMIT invoice               ← business transaction
  T9  JMS receive ACK / COMMIT        ← consumption acknowledgment
                   │
                   ▼
Business outcome protocol
  T10 lưu COMPLETED hoặc phát InvoiceCreated
  T11 Order Service nhận biết kết quả ← caller-visible business result
~~~

**Thứ tự thực tế không phải lúc nào cũng khớp thứ tự dòng log.** Consumer có thể xử lý ngay khi broker giao message, thậm chí trước khi thread producer ghi log sau `send`. Từng transaction và message callback còn có thể hoàn tất muộn hơn. Sơ đồ tách **ý nghĩa của các mốc**, không cam kết broker tự lưu đủ T1–T11.

## 2. Bảng tín hiệu: bằng chứng nào cho phép kết luận điều gì?

| Tín hiệu | Bằng chứng hợp lệ | Không được suy diễn |
| --- | --- | --- |
| Tạo `TextMessage`/`MapMessage` | Message object đã được tạo trong JVM | Broker đã nhận |
| `JmsTemplate.send` trả về bình thường ngoài transaction | Send đã hoàn tất theo semantics của provider và QoS | Consumer nhận, nghiệp vụ thành công |
| `JmsTemplate.convertAndSend` trả về | Converter và send thành công theo ngữ cảnh JMS | Conversion là xử lý nghiệp vụ; consumer đã commit |
| `MessageProducer.send(..., CompletionListener)` mới return | Một async send đã bắt đầu và chưa throw lỗi đồng bộ | Async send đã hoàn tất |
| `CompletionListener.onCompletion` | Async send hoàn tất với mức bảo đảm tương ứng sync send | Business processing hoàn tất |
| `JmsTemplate.send` return **bên trong** local JMS transaction | Send được thực hiện trong session đang tham gia transaction | JMS transaction chắc chắn đã COMMIT |
| `Session.commit` / transaction manager commit thành công | Nhóm thao tác JMS trong transaction được commit | DB/consumer đã hoàn thành |
| Queue depth tăng | Broker có message chờ ở thời điểm đo | Message sẽ được xử lý ngay hoặc không hết hạn |
| Consumer `@JmsListener` bắt đầu | Có một lần delivery đến consumer | Handler chạy hết, DB commit |
| Handler log `DONE` trước return | Code đi qua một nhánh log | DB hoặc JMS commit chắc chắn thành công |
| DB transaction commit | Business data đã commit trong database đó | JMS ACK/commit cũng hoàn tất |
| JMS ACK/receive commit | Broker ghi nhận việc tiêu thụ theo ACK/transaction config | Side effect SQL, email, payment đã được commit nguyên tử |
| Outcome store báo `COMPLETED` sau business commit | Nghiệp vụ đạt tiêu chí hoàn thành đã định nghĩa | Caller ở mọi hệ thống đã nhận thông báo |
| Caller nhận completion event/reply hợp lệ | Caller nhận kết quả do consumer công bố theo contract | Không tồn tại message duplicate hay notification trùng |

**Queue rỗng không đồng nghĩa business thành công:** message có thể đang in-flight, đã bị ACK sớm, hết hạn, vào DLQ, bị consumer khác lấy hoặc bị quản trị viên xóa. Cần xác minh **kết quả trong hệ thống nghiệp vụ**.

## 3. `JmsTemplate` xác nhận điều gì khi send trả về?

### 3.1. Đường gửi đồng bộ thường gặp

~~~java
jmsTemplate.convertAndSend("billing.commands", "CreateInvoice:O-42");
System.out.println("JMS send operation returned");
~~~

Trong một Spring bean đã inject `JmsTemplate`, nếu không có transaction đang chờ commit và `convertAndSend` không ném lỗi, Spring đã thực hiện lời gọi gửi JMS theo provider tương ứng. `send` và `convertAndSend` đều trả `void`. `send` cho phép code tự tạo JMS `Message` qua `MessageCreator`; `convertAndSend` dùng `MessageConverter` chuyển Java object sang JMS Message. **Không có nhóm nào tự chờ Billing Service làm xong hóa đơn.**

Ví dụ xử lý exception:

~~~java
try {
    jmsTemplate.convertAndSend("billing.commands", command);
    markPublishAttemptReturned(operationId);
} catch (org.springframework.jms.JmsException ex) {
    markPublishAttemptUncertain(operationId, ex);
    throw ex;
}
~~~

Đây là **pseudocode Java đặt trong business service**: `command`, `operationId` và hai hàm `mark...` phải được ứng dụng tự định nghĩa; không phải class `main` độc lập. `JmsException` có thể phản ánh lỗi network/provider/destination/conversion. Với một số lỗi truyền thông, broker **có thể đã nhận message dù client thấy exception**. Do đó status “UNCERTAIN” thường chính xác hơn “chắc chắn chưa gửi” cho trường hợp mất phản hồi ở ranh giới send.

### 3.2. Gửi trong local JMS transaction

~~~text
@Transactional(transactionManager="jmsTransactionManager")
    ├─ JmsTemplate.send / convertAndSend → send nằm trong JMS Session
    ├─ code khác tiếp tục chạy
    └─ method return → transaction manager cố commit Session
                                      ├─ thành công
                                      └─ exception / kết quả không chắc
~~~

Với `JmsTransactionManager`, `JmsTemplate` tự phát hiện session đang được Spring gắn với thread. **Lời gọi send trả về trước transaction commit** không đủ xác nhận message đã committed. Ngay cả lúc JMS commit gặp failure, client có thể không biết transaction đã commit hay rollback nếu mất phản hồi đúng thời điểm.

`JmsTransactionManager` điều phối **một tài nguyên JMS**; local JMS transaction không tự gộp cùng SQL database, HTTP API hoặc email. `@Transactional` chỉ có nghĩa khi biết **transaction manager nào** và tài nguyên nào thực sự tham gia. Dùng JTA/XA đòi XA-capable connection factory, coordinator và vận hành riêng; không phải mặc định.

### 3.3. API gửi bất đồng bộ cấp JMS

`jakarta.jms.MessageProducer` có thể gửi với `CompletionListener`:

~~~java
producer.send(message, new jakarta.jms.CompletionListener() {
    @Override
    public void onCompletion(jakarta.jms.Message sent) {
        System.out.println("Provider completed async send");
    }

    @Override
    public void onException(jakarta.jms.Message failed, Exception cause) {
        System.err.println("Async send failed: " + cause);
    }
});
~~~

Đây là snippet bên trong phương thức đã có `MessageProducer producer`, `Message message` và session/connection thích hợp. Nó thuộc **classic Jakarta Messaging API**, **không** phải overload của `JmsTemplate`.

Khi async `send(..., listener)` vừa return, operation có thể **chưa xong**. Chỉ sau callback `onCompletion` có thể xem send thành công với độ tin cậy tương đương một sync send. Exception lúc gọi hoặc `onException` có thể để lại trạng thái broker **không xác định**. Không sửa/đọc body/header của object `Message` sau async send trước callback. Không gọi `close` hoặc `commit/rollback` trên session sở hữu producer từ callback.

**Phân biệt hai chữ “asynchronous”:** async *sending completion* nói về phản hồi send; consumer xử lý độc lập theo thời gian là một vấn đề khác. Cả hai đều không tự cung cấp business success event.

## 4. Broker đã nhận message vẫn có thể chưa giao

Sau send thành công, message có thể chờ lâu hoặc không được giao cho một consumer mong muốn vì:

1. **Consumer offline** hoặc có backlog lớn, concurrency thấp, xử lý chậm.
2. **Queue và topic subscription khác nhau**: queue có consumer cạnh tranh; topic non-durable subscriber offline có thể bỏ lỡ event; durable subscription chịu retention/expiry.
3. **Delivery delay** được provider áp dụng, yêu cầu chưa giao trước một mốc.
4. **Time-to-live (TTL)**: hết hạn trước khi được giao, kể cả khi producer từng send thành công; TTL tính từ send, không bắt đầu lại từ lúc consumer sẵn sàng.
5. **Selector hoặc routing**: consumer lọc sai property, khác destination, topic-vs-queue mismatch, ACL/role hoặc sai broker.
6. **Quy tắc broker**: persistent storage, quota, address-full policy, expiry/DLQ, HA/failover không phù hợp.

`DeliveryMode.PERSISTENT` mặc định yêu cầu mức bảo vệ message trước lỗi provider theo chuẩn/cấu hình. Nó **không** bảo vệ người gửi khỏi duplicate business execution, không sửa được schema lỗi, không tự hoàn thành DB transaction và không chống được mọi cấu hình storage/retention không phù hợp. `NON_PERSISTENT` có thể cho semantics yếu hơn khi provider lỗi.

**Không suy diễn từ số lượng message:** queue depth = 0 không chứng minh hóa đơn được tạo. Queue depth = 100 không có nghĩa 100 hóa đơn lỗi; có thể đơn giản là đang chờ xử lý.

## 5. Consumer đã nhận chưa phải là consumer đã thành công

~~~java
@JmsListener(destination = "billing.commands")
public void onCommand(String content) {
    validateCommand(content);
    createInvoice(content);
}
~~~

Snippet trên chỉ mô tả logic; `validateCommand` và `createInvoice` do ứng dụng implement. Ngay khi Spring gọi listener, ta mới biết có **một lần giao message**. Sau đó:

- Validate có thể thất bại do dữ liệu không hợp contract hoặc schema version.
- DB có thể unavailable, timeout hoặc vi phạm unique/FK constraint.
- Gọi dịch vụ ngoài (payment/email) có thể thất bại hoặc trả kết quả không chắc chắn.
- Handler có thể ghi log “done” rồi transaction commit thực tế ném exception.
- Message có thể đến **lần thứ hai** do rollback hoặc producer retry, dù business đã ghi DB ở lần đầu.

Một hệ thống cần tách `MESSAGE_RECEIVED`, `HANDLER_RETURNED`, `BUSINESS_COMMITTED` và `JMS_RECEIVE_COMMITTED`. Đây là những sự kiện **khác nhau**, không tự thay thế nhau.

### Chế độ ACK làm thay đổi ý nghĩa “listener thành công”

| Cấu hình listener | Tác động đến ACK/rollback | Giới hạn |
| --- | --- | --- |
| `AUTO_ACKNOWLEDGE` | Container/provider tự ACK theo semantics implementation | Với Spring `DefaultMessageListenerContainer`, ACK có thể diễn ra **trước** listener execution: handler exception không bảo đảm redelivery |
| `CLIENT_ACKNOWLEDGE` | Consumer/session chủ động hoặc Spring container quản lý ACK sau thành công | Không gộp commit SQL với JMS |
| `DUPS_OK_ACKNOWLEDGE` | Cho phép ACK trì hoãn và khả năng redelivery | Không có exactly-once nghiệp vụ |
| `sessionTransacted=true` | Listener chạy trong local JMS transaction; exception phù hợp rollback, cho phép redelivery | DB/calls ngoài JMS vẫn ở transaction riêng nếu không có thiết kế phối hợp |

Không chỉ nhìn `@JmsListener` mà cho rằng được bảo đảm retry. Trong Spring Framework thuần, phải kiểm tra `DefaultJmsListenerContainerFactory`. Spring Boot 3.x khi auto-configure default listener factory thường tạo transactional listener: JTA nếu có `JtaTransactionManager`, nếu không bật `sessionTransacted`. Tự tạo bean factory khác có thể làm đổi behavior; kiểm tra bean runtime và thử lỗi thực tế.

**Lưu ý:** ACK của consumer nói với broker về **việc xử lý message trên JMS**. Nó không tự chứng minh database, email hay payment đã commit. Nếu một handler tự ACK quá sớm rồi chết trước DB commit, message có thể không được giao lại trong khi nghiệp vụ chưa xong.

## 6. Cửa sổ lỗi quan trọng nhất: DB commit trước JMS commit

Giả sử message có `eventId=evt-42` yêu cầu tạo hóa đơn:

~~~text
t0  JMS consumer nhận message M
t1  INSERT INTO invoices(...) trong DB transaction
t2  DB COMMIT thành công
t3  Consumer chết/mất kết nối broker
t4  JMS ACK/COMMIT chưa hoàn tất
t5  Broker phục hồi và redeliver message M
t6  Handler xử lý lại cùng evt-42
~~~

Nếu code chỉ tạo invoice mới rồi commit mà **không chống trùng**, hai lần nhận có thể tạo hai invoice hoặc hai side effects. Ngay cả `sessionTransacted=true` cũng chỉ giữ transaction JMS. Spring Framework lưu ý rõ việc DB commit xong nhưng JMS commit lỗi có thể dẫn tới redelivery và nhu cầu duplicate detection.

**Điều cần bảo đảm ở business layer:** với một yêu cầu nghiệp vụ hợp lệ có cùng idempotency key, kết quả nghiệp vụ mong muốn được áp dụng **một lần** dù message có thể gửi/giao lại.

Một cách thường dùng:

- Producer tạo `eventId`/`commandId` **một lần** cho cùng business operation, giữ nguyên qua retry.
- Consumer lưu khóa ấy vào bảng `processed_inbox` với **unique constraint**.
- Ghi khóa và thực hiện thay đổi nghiệp vụ trong **cùng một DB transaction**.
- Nếu khóa đã tồn tại, consumer kết thúc bình thường, không thực hiện side effect lần hai, để JMS receive được commit/ack.
- Nếu chưa có khóa nhưng có lỗi thật, DB rollback, JMS rollback/retry theo provider policy.

**Không** chỉ dùng `HashSet` hoặc một cờ trong RAM: restart mất state, nhiều replica race, và kiểm tra-trước-ghi không atomic.

## 7. Phân biệt “gửi lặp” với “giao lại”

~~~text
Producer attempt A: eventId=evt-42 → JMSMessageID=ID:a
Producer không nhận được phản hồi đúng hạn
Producer attempt B: eventId=evt-42 → JMSMessageID=ID:b

Consumer nhận A và B: hai JMS Message, cùng một nghiệp vụ.
~~~

Đây là **duplicate publish**. `JMSMessageID` do provider gán có thể khác giữa hai send. Nếu broker giao lại *cùng* một message do consumer rollback, JMS message ID thường vẫn mô tả cùng message, còn `JMSRedelivered`/`JMSXDeliveryCount` giúp quan sát các lần nhận. Nhưng chúng **không chứng minh** nghiệp vụ chưa từng commit.

Bảng phân biệt:

| ID / cờ | Bên cấp | Mục đích | Không thay được |
| --- | --- | --- | --- |
| `JMSMessageID` | JMS provider khi send | Truy vết message trong broker/JMS | Stable business event ID xuyên retry publish |
| `eventId` / `operationId` | Ứng dụng | Idempotency, correlation nghiệp vụ | Chính sách gửi/lưu của broker |
| `JMSCorrelationID` | Ứng dụng | Ghép request–reply và workflow | Unique constraint dữ liệu nghiệp vụ |
| `JMSRedelivered` | Provider trước delivery | Gợi ý đã giao lại một message | Chứng minh side effect DB chưa chạy |
| `JMSXDeliveryCount` | Provider trên receive | Quan sát số lần giao theo JMS (có giới hạn trong failure) | Số lần invoice đã được commit |

**Bất biến nghiệp vụ thường tốt hơn số lần gửi:** nếu invoice chỉ được tạo một lần trên `(orderId, invoiceType)` thì unique constraint ngay ở bảng invoice có thể bảo vệ invariant. Nếu một đơn có nhiều nghiệp vụ hợp lệ, dùng idempotency key ở phạm vi thích hợp, không gộp nhầm các sự kiện khác nhau.

## 8. Ma trận failure window

| Lỗi xảy ra ở đâu | Send có thể thành công? | Business có thể thành công? | Điều cần kiểm chứng |
| --- | --- | --- | --- |
| Payload không chuyển được thành JMS Message | Chưa gửi qua lần gọi đó | Chưa có bằng chứng | Exception conversion; sửa dữ liệu |
| Broker down trước send | Thường không | Chưa có bằng chứng | Network/credentials, retry policy |
| Broker đã nhận, phản hồi send bị mất | **Có thể** | **Có thể** trong tương lai | Retry giữ event ID; xem broker/consumer |
| `JmsTemplate` send trong JMS transaction chưa commit | Chưa biết JMS commit | Chưa biết | Kết quả transaction boundary |
| JMS commit thành công, consumer chưa chạy | Có | Chưa | Queue/topic, backlog, TTL, subscriber |
| Consumer đã nhận, validation fail | Có | Chưa | Rollback, retry hoặc DLQ theo loại lỗi |
| DB commit xong nhưng JMS receive commit bị mất | Có | **Có** hoặc chưa quan sát rõ | Inbox/idempotency, trạng thái DB, redelivery |
| Consumer ACK sớm, DB fail | Có | Không | Nguy cơ mất công việc do ACK mode |
| Handler xong nhưng response kết quả bị mất | Có | **Có thể** | Tra cứu outcome store theo operation ID |
| Message vào DLQ sau retry | Có thể | Thường chưa đạt contract | Alert, replay và cập nhật business outcome |
| TTL hết trước delivery | Có thể đã gửi thành công | Chưa qua consumer này | Expiry metrics, timeout contract |
| Producer và consumer cùng restart | Có thể | Chưa rõ | Journal/outbox/inbox, recovery, dedupe |

**Timeout không tự đồng nghĩa failure:** một bên có thể không nhận được phản hồi dù bên kia đã hoàn tất. Thiết kế retry phải chịu được cả hai trạng thái “chưa được gửi” và “đã gửi nhưng response bị mất”.

## 9. Tại sao cả lỗi `send` lẫn lỗi `commit` có thể mơ hồ?

Jakarta Messaging nêu rõ với một số lỗi ngay ranh giới non-transacted `PERSISTENT` send hoặc `Session.commit()`, client không thể phân biệt broker đã accept/commit hay chưa. Với async `MessageProducer`, exception khi gọi hoặc callback lỗi cũng có thể không cho biết message đã tới broker chưa.

Điều này dẫn tới hai lỗi thiết kế phổ biến:

1. **Retry bằng ID mới mỗi lần:** cùng một ý định nghiệp vụ tạo ra nhiều eventId, khiến consumer không biết đó là một operation, dẫn tới double charge/double invoice.
2. **Bỏ retry hoàn toàn vì sợ duplicate:** nếu broker thực sự chưa nhận, nghiệp vụ có thể bị quên.

Cách tiếp cận tốt hơn là **retry có giới hạn + stable idempotency key + lưu trạng thái có thể phục hồi + consumer idempotent**. Chọn backoff và alert phù hợp; không retry vô hạn với lỗi dữ liệu/schema không thay đổi.

## 10. Outbox: đảm bảo ý định gửi không mất sau DB commit

Nếu Order Service làm:

~~~text
BEGIN DB
INSERT orders...
COMMIT DB
JmsTemplate.convertAndSend("billing.commands", event)
~~~

thì crash giữa `COMMIT DB` và `send` làm đơn hàng đã có nhưng command lập hóa đơn không được publish. Nếu đảo thứ tự send trước DB commit, Billing có thể nhận command về một đơn chưa được commit hoặc sẽ rollback.

**Transactional outbox** dùng một DB transaction ghi cả business data và event cần gửi. Minh họa PostgreSQL:

~~~sql
CREATE TABLE orders (
    order_id TEXT PRIMARY KEY,
    status TEXT NOT NULL
);

CREATE TABLE event_outbox (
    event_id UUID PRIMARY KEY,
    aggregate_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ
);

BEGIN;

INSERT INTO orders (order_id, status)
VALUES ('O-42', 'CREATED');

INSERT INTO event_outbox (
    event_id, aggregate_id, event_type, payload
) VALUES (
    '88888888-8888-4888-8888-888888888888',
    'O-42',
    'CreateInvoice',
    '{"eventId":"88888888-8888-4888-8888-888888888888",
      "type":"CreateInvoice","orderId":"O-42","schemaVersion":1}'::jsonb
);

COMMIT;
~~~

Đây là mô hình SQL cho PostgreSQL, yêu cầu DB và quyền tạo bảng; **không phải bảng do Spring JMS tự tạo**.

Publisher outbox sau đó:

~~~text
Đọc event_outbox chưa published (claim/lock có kiểm soát)
    → gửi JMS giữ nguyên eventId
    → quan sát send/transaction JMS hoàn tất
    → đánh dấu published_at
    → retry sau restart nếu chưa chắc chắn
~~~

Nếu broker đã nhận nhưng publisher chết trước khi cập nhật `published_at` thì sẽ gửi lại. Outbox vì vậy hỗ trợ **at-least-once publish**, không tự mang exactly-once delivery. Producer cần giữ event ID ổn định và consumer cần chống trùng. Với nhiều worker outbox, phải dùng claim/lease/lock hoặc `SKIP LOCKED` thích hợp; không dựa vào vòng `SELECT` không khóa.

**Outbox giải quyết “DB đã commit nhưng publisher quên gửi”, không giải quyết “Billing đã tạo hóa đơn chưa”.** Hai câu hỏi cần hai nguồn bằng chứng khác nhau.

## 11. Inbox: xử lý nghiệp vụ một lần dù nhận lặp

Một bảng nhận diện đã xử lý và một bảng business:

~~~sql
CREATE TABLE processed_inbox (
    consumer_name TEXT NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE invoices (
    invoice_id BIGSERIAL PRIMARY KEY,
    order_id TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Một DB transaction được consumer điều phối:

~~~sql
BEGIN;

INSERT INTO processed_inbox (consumer_name, event_id)
VALUES ('invoice-worker', '88888888-8888-4888-8888-888888888888')
ON CONFLICT (consumer_name, event_id) DO NOTHING
RETURNING event_id;

-- Nếu trả về 1 dòng, đây là lần xử lý đầu của consumer:
-- INSERT INTO invoices(order_id) VALUES ('O-42');
-- Nếu trả về 0 dòng, BỎ QUA business insert để tránh lặp.

COMMIT;
~~~

Đoạn `INSERT INTO invoices` được để ở comment vì ứng dụng phải **rẽ nhánh theo kết quả `RETURNING`**. Khi thật sự triển khai, câu insert business và inbox insert phải ở **cùng transaction**; không commit inbox trước rồi mới làm nghiệp vụ. Unique constraint xử lý race giữa các replica tốt hơn một check trong RAM.

Khi một message lặp được nhận mà inbox đã xác nhận business commit xong, handler nên **return thành công** (không gọi invoice lần hai), để listener container có thể commit JMS receive. Nếu ném exception chỉ vì “đã xử lý”, broker có thể retry mãi một message hợp lệ.

**Giới hạn:** inbox trong DB không làm một HTTP payment call trở nên atomic. Nếu side effect nằm ở service khác, dùng idempotency key phía service đó hoặc workflow reconciliation/compensation phù hợp.

## 12. Làm sao producer biết nghiệp vụ đã hoàn thành?

Cần phân biệt **xác nhận nhận lệnh** với **thông báo hoàn tất lệnh**. Ba cơ chế phổ biến:

### 12.1. Tra cứu outcome store

Consumer ghi kết quả tại nơi sở hữu nghiệp vụ, chẳng hạn:

| Trạng thái | Contract nên hiểu |
| --- | --- |
| `ACCEPTED` | Yêu cầu đã được ghi nhận trong nguồn có khả năng phục hồi |
| `PROCESSING` | Đang xử lý; chưa phải kết quả cuối |
| `COMPLETED` | Transaction nghiệp vụ đã commit theo định nghĩa hoàn tất |
| `REJECTED` | Không được chấp nhận theo rule nghiệp vụ; không tự retry |
| `RETRYING` | Lỗi tạm thời và dự kiến xử lý lại |
| `FAILED_FINAL` | Đã dừng tự động, cần người hoặc workflow can thiệp |

Giao diện Order Service có thể gọi `GET /operations/{operationId}` tới nguồn outcome hợp lệ; không dùng queue depth để tính trạng thái. Cần phân biệt retry attempt và final result. Outcome store phải được cập nhật theo transaction/thiết kế mà bạn có thể chứng minh, không chỉ dựa trên log.

### 12.2. Completion event

~~~text
OrderService outbox → CreateInvoice(eventId=evt-42)
                          │
                          ▼
BillingService xử lý + COMMIT invoice
                          │
                          ▼
Billing outbox → InvoiceCreated(eventId, invoiceId)
                          │
                          ▼
OrderService nhận completion event → cập nhật outcome
~~~

Completion event **phải phản ánh DB commit đã thành công**; có thể ghi vào outbox của Billing trong cùng transaction business để tránh crash sau DB commit nhưng trước publish. Caller nhận completion cũng phải idempotent: event phản hồi có thể được publish lại hoặc redeliver.

### 12.3. Request–reply với JMSReplyTo và JMSCorrelationID

Request có thể mang `JMSReplyTo` chỉ queue phản hồi; consumer gửi reply có `JMSCorrelationID` để producer ghép kết quả. Nhưng contract phải nói reply có nghĩa gì:

- `REQUEST_ACCEPTED` chỉ nói consumer hoặc hạ tầng đã nhận/đăng ký yêu cầu, **không** nói invoice đã có.
- `INVOICE_CREATED` cần phát sau khi kết quả nghiệp vụ được commit; nếu kết quả quan trọng, cân nhắc reply qua outbox.
- Reply bị mất hoặc timeout ⇒ **UNKNOWN_RESULT_TO_CALLER**; không tự tạo invoice mới với ID mới.
- `JMSMessageID` của request và reply là hai ID do provider cấp; correlation ID phục vụ ghép luồng, không thay idempotency key nghiệp vụ.

Nếu một workflow có nhiều bước (hóa đơn xong, email chưa gửi), trạng thái “hoàn thành” phải định nghĩa theo đúng business SLA, tránh trộn `invoiceCommitted` với `emailDelivered` thành một boolean không rõ ràng.

## 13. Spring Boot Java 17: demo thấy send trả về dù handler sắp lỗi

Ví dụ tối thiểu dùng **Spring Boot 3.5.0** (phiên bản đã phát hành), Java 17+ và **Apache ActiveMQ Artemis broker chạy bên ngoài**. Đó là phiên bản minh họa API; dự án production chọn release còn được đội ngũ hỗ trợ. Broker cần queue `demo.business-stages` có thể nhận/giao message (hoặc bật auto-create queue), user có quyền tương ứng.

### 13.1. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-business-stages'
~~~

### 13.2. application.yaml

`src/main/resources/application.yaml`:

~~~yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: demo
  jms:
    pub-sub-domain: false
~~~

Mật khẩu lấy từ biến môi trường `SPRING_ARTEMIS_PASSWORD` hoặc secret store; sửa user, URL và credentials theo broker thật. Không commit password vào source control. Boot tạo `ConnectionFactory`/`JmsTemplate` khi starter và điều kiện auto-config đáp ứng; broker **không** tự xuất hiện chỉ vì có dependency client. Trong setup Boot 3.x chuẩn, default listener factory transactional; nếu dự án tự thay bean, phải kiểm tra mode thật trước khi thử redelivery.

### 13.3. Mã Java một tệp

`src/main/java/example/jmsstages/JmsStagesApplication.java`:

~~~java
package example.jmsstages;

import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class JmsStagesApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmsStagesApplication.class, args);
    }

    @Bean
    ApplicationRunner sendSample(JmsTemplate template) {
        return args -> {
            String eventId = UUID.randomUUID().toString();
            System.out.println("PUBLISH_BEGIN eventId=" + eventId);

            template.send("demo.business-stages", session -> {
                TextMessage message =
                        session.createTextMessage("CreateInvoice:O-42");
                message.setStringProperty("eventId", eventId);
                return message;
            });

            System.out.println("SEND_RETURNED eventId=" + eventId
                    + " businessOutcome=NOT_VERIFIED");
        };
    }
}

@Component
class DemoInvoiceListener {

    // Demo: cố tình lỗi đúng một lần trong tiến trình.
    private final AtomicBoolean failOnce = new AtomicBoolean(true);

    @JmsListener(destination = "demo.business-stages")
    public void handle(Message message) throws JMSException {
        String eventId = message.getStringProperty("eventId");
        int count = message.getIntProperty("JMSXDeliveryCount");

        System.out.println("CONSUMER_DELIVERED eventId=" + eventId
                + " count=" + count);

        if (failOnce.compareAndSet(true, false)) {
            System.out.println("HANDLER_THROWING eventId=" + eventId);
            throw new IllegalStateException("Demo transient failure");
        }

        // Production: transaction DB + idempotency và trạng thái nghiệp vụ.
        System.out.println("HANDLER_RETURNED eventId=" + eventId);
    }
}
~~~

### 13.4. Cách chạy và quan sát

Sau khi đã có Gradle wrapper, broker test, credential và queue hợp lệ:

~~~bash
./gradlew bootRun
~~~

Các dòng sau **có thể xuất hiện**, với ID và thứ tự thay đổi:

~~~text
PUBLISH_BEGIN eventId=<uuid>
SEND_RETURNED eventId=<uuid> businessOutcome=NOT_VERIFIED
CONSUMER_DELIVERED eventId=<uuid> count=1
HANDLER_THROWING eventId=<uuid>
CONSUMER_DELIVERED eventId=<uuid> count=2
HANDLER_RETURNED eventId=<uuid>
~~~

Trong đó `<uuid>` chỉ là ký hiệu minh họa; không phải stdout chính xác. Listener có thể nhận **trước khi** log `SEND_RETURNED`; nếu retry delay lâu hoặc broker chuyển DLQ theo policy, có thể không xuất hiện lần delivery thứ hai ngay. Lần receive thứ nhất ném exception; với transactional listener, JMS receive rollback. `AtomicBoolean` chỉ mô phỏng lỗi một lần **trong RAM**, reset khi restart và không phải idempotency.

**Quan trọng:** demo không thực hiện SQL insert nên `HANDLER_RETURNED` **không phải bằng chứng hóa đơn đã tạo**. Nó cho thấy rõ ba ranh giới độc lập: send return, listener invocation và listener method return. Muốn thử business commit thực sự, kết nối database và triển khai inbox ở mục 11.

### 13.5. Với Spring Framework thuần

Nếu không dùng Boot auto-configuration, bạn cần tự cấu hình `ConnectionFactory`, `JmsTemplate`, `@EnableJms` và listener factory. Snippet:

~~~java
@Bean
DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory) {
    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setSessionTransacted(true);
    factory.setConcurrency("1");
    return factory;
}
~~~

Đây là code đặt trong class `@Configuration` có `@EnableJms` và imports phù hợp từ `jakarta.jms.ConnectionFactory`, `org.springframework.jms.config.DefaultJmsListenerContainerFactory` và `org.springframework.context.annotation.Bean`. Không phải chương trình chạy độc lập. Các broker-specific retry attempts, delay và DLQ phải được cấu hình/thử nghiệm tại provider.

## 14. HTTP API nên biểu đạt kết quả đang chờ thế nào?

Nếu HTTP endpoint chỉ ghi nhận yêu cầu rồi enqueue JMS, contract có thể trả:

~~~http
HTTP/1.1 202 Accepted
Location: /operations/op-42
Content-Type: application/json

{"operationId":"op-42","status":"ACCEPTED"}
~~~

`202 Accepted` cho biết server đã nhận yêu cầu để xử lý tiếp **theo định nghĩa contract**; không tự khẳng định invoice đã commit. Client truy vấn `GET /operations/op-42` để xem `PROCESSING`, `COMPLETED`, `REJECTED` hoặc `FAILED_FINAL`. Khi outcome store có trạng thái đã commit, response có thể là:

~~~json
{
  "operationId": "op-42",
  "status": "COMPLETED",
  "invoiceId": "INV-1001"
}
~~~

Đây là API ví dụ do ứng dụng tự thiết kế, không phải HTTP response tự động của JMS.

**Tránh:** trả `200 OK` với `invoiceCreated=true` ngay sau `JmsTemplate.send`; hoặc khi timeout thì tạo yêu cầu mới/ID mới không tra cứu trạng thái cũ. Timeout nên được hiểu là **chưa nhận được kết quả đúng hạn**, không phải chắc chắn nghiệp vụ thất bại. Sử dụng operation ID/idempotency key xuyên HTTP retry và JMS retry.

## 15. Retry, DLQ và lỗi nghiệp vụ

### 15.1. Retry không phải bằng chứng thành công

JMS provider có thể redeliver message khi consumer rollback/failure; số lần, delay/backoff, max attempts và DLQ là **cấu hình broker**, không có một giá trị mặc định chung ở mọi JMS implementation. Poison message liên tục lỗi do schema có thể gây vòng retry và đẩy backlog tăng.

Một lần send thành công rồi cuối cùng message nằm trong DLQ nghĩa là **publish từng thành công nhưng business processing chưa đạt contract**, trừ khi có state/outcome khác chứng minh điều ngược lại. Cần cảnh báo DLQ, phân loại lỗi, giữ event ID, ghi outcome chưa hoàn tất và quy trình replay có kiểm soát.

### 15.2. Phân loại lỗi

| Lỗi | Quy tắc xử lý |
| --- | --- |
| Broker unavailable, timeout tạm thời | Retry có giới hạn, exponential backoff, giữ eventId; outbox giúp sống qua restart |
| Malformed payload, unknown schema, permission sai | Sửa contract/config; không retry vô hạn nguyên payload |
| DB unavailable/lock timeout | Rollback transaction, retry theo policy |
| Vi phạm business rule cố định | Đánh dấu `REJECTED` hoặc một trạng thái cuối có contract; đừng để poison message lặp mãi |
| DB đã xử lý nhưng message giao lại | Dedupe, không làm nghiệp vụ lần hai, return success để JMS commit |
| External API trả outcome không rõ | Tra cứu theo idempotency key/request ID của hệ thống đích; không gọi lại mù quáng |
| Completion reply không tới caller | Caller tra outcome store; không suy diễn timeout = business failed |

**Không dùng log “sent” để dừng giám sát.** Nên có đối chiếu giữa number of accepted operations, number of completed/rejected operations, pending age và DLQ/retry count.

## 16. Mô hình trạng thái dùng chung giữa các hệ thống

Tách **publish status** và **business outcome** là cách giảm nhầm lẫn:

| Publish status | Ý nghĩa |
| --- | --- |
| `NOT_ATTEMPTED` | Có yêu cầu/outbox record nhưng chưa thử JMS send |
| `SEND_IN_PROGRESS` | Đang thực hiện lời gọi send |
| `SEND_RETURNED` | Send hoàn tất theo provider/transaction đã xác minh |
| `SEND_UNCERTAIN` | Mất phản hồi, không biết broker đã nhận chưa |
| `PUBLISH_RETRYING` | Sẽ thử lại bằng cùng business ID |

| Business status | Ý nghĩa |
| --- | --- |
| `PENDING` | Chưa có kết quả cuối |
| `PROCESSING` | Consumer đã bắt đầu hoặc operation được claim |
| `COMPLETED` | Business transaction đạt invariant và commit |
| `REJECTED` | Bị từ chối theo rule có xác định |
| `FAILED_FINAL` | Dừng xử lý tự động, cần can thiệp/reconciliation |

**Không vẽ một mũi tên tự động** `SEND_RETURNED → COMPLETED`. Hai trục trạng thái có thể cập nhật không đồng bộ. Một operation business `COMPLETED` còn có thể tồn tại trong khi caller chỉ thấy `SEND_UNCERTAIN` vì phản hồi network bị mất.

Khi hệ thống có nhiều công đoạn, hãy làm rõ “COMPLETED” là **đã tạo invoice**, **đã thu tiền**, hay **đã gửi email**. Không gom các side effect khác nhau thành một boolean không định nghĩa.

## 17. Observability và điều kiện chấp nhận hệ thống

Các metric cần tách theo từng ranh giới:

| Nơi đo | Metric / log | Vì sao |
| --- | --- | --- |
| Producer | `publish_attempt_total`, `send_returned_total`, `send_error_total`, latency | Cho biết đường gửi khỏe hay không |
| Outbox | backlog, oldest unpublished age, retry count | Đã commit DB nhưng chưa publish |
| Broker | queue depth, in-flight, oldest message age, expiry/DLQ | Chậm, lỗi, mất kết nối hoặc message hết hạn |
| Consumer | received/started/handler_failed, processing duration | Workload và lỗi handler |
| JMS transaction | commit/rollback/redelivery, `JMSXDeliveryCount` | Bằng chứng consumer retries |
| Business DB | invoice_committed, rejected, dedupe hit, unique violations | Trạng thái nghiệp vụ |
| Completion | completion event lag, unobserved outcomes | Đã xong nhưng chưa thông báo |
| End-to-end | accepted-to-completed latency | SLA nghiệp vụ |

Log nên gắn `eventId`/`operationId` ổn định, `JMSMessageID` để truy message ở broker, `JMSCorrelationID` để nối request/reply, attempt ID, destination và result. Không in password, token, thông tin thanh toán hay payload nhạy cảm.

`JMSTimestamp` là thời điểm gửi do JMS provider đặt, **không phải business completion timestamp**. Khi nhiều máy lệch đồng hồ, phép trừ timestamp chỉ là latency xấp xỉ; cần metric/tracing phù hợp.

### Ma trận kiểm thử tối thiểu

1. **Broker down trước publish:** xác minh send lỗi/được retry, không ghi sai `COMPLETED`.
2. **Consumer offline:** producer send thành công, queue chờ (nếu policy giữ), business vẫn pending.
3. **Handler ném lỗi:** với transacted listener, quan sát rollback/redelivery/DLQ theo broker.
4. **DB lỗi trước commit:** không có invoice, không ghi `COMPLETED`, JMS có cơ hội redelivery.
5. **Crash sau DB commit trước JMS commit:** có thể redelivery; kiểm chứng DB **không** tạo invoice lần hai.
6. **Duplicate publish:** hai JMS message cùng `eventId`; consumer dedupe trong DB transaction.
7. **Broker response mất:** producer thấy `SEND_UNCERTAIN` dù broker có thể đã nhận; retry cùng ID.
8. **TTL hết trước delivery:** send return có thể thành công, business chưa được làm.
9. **Reply bị mất:** caller timeout, tra outcome store thấy `COMPLETED` mà không gửi yêu cầu mới.
10. **Outbox publisher restart:** broker từng nhận nhưng `published_at` chưa ghi, publisher gửi lại; consumer chống trùng.
11. **Poison message:** retry hữu hạn, DLQ có alert, business status và replay policy rõ ràng.
12. **Nhiều consumer:** race trên cùng business key bị DB unique constraint chặn; không phụ thuộc cờ RAM.

Mỗi thí nghiệm cần ghi provider/version, queue/destination, listener ACK/transaction mode, ID nghiệp vụ, broker logs, DB rows và kết quả cuối. Chỉ “message không còn trong queue” **không đủ** để tuyên bố test thành công.

## 18. Những nhầm lẫn cần loại bỏ

1. **“`send()` thành công nghĩa là khách hàng đã được lập hóa đơn.”** Không: producer không quan sát business DB của consumer.
2. **“`convertAndSend` có nghĩa convert xong nghiệp vụ.”** Không: convert chỉ chuyển Java object thành JMS Message.
3. **“Broker ACK cho producer chính là consumer ACK.”** Không: các bên và ranh giới khác nhau.
4. **“Có `JMSMessageID` nghĩa là DB đã commit.”** Không: ID do provider cấp cho message.
5. **“Queue depth bằng 0 là mọi việc đã hoàn tất.”** Không: in-flight, expiry, DLQ và ACK sớm còn tồn tại.
6. **“`PERSISTENT` đảm bảo exactly-once invoice.”** Không: persistence liên quan transport, không giải quyết side effect trùng.
7. **“Handler log DONE thì transaction chắc chắn đã commit.”** Log có thể xuất hiện trước commit hoặc bị mất khi crash.
8. **“`sessionTransacted=true` gộp JMS và SQL.”** Không: local JMS transaction chỉ quản lý JMS.
9. **“`@Transactional` tự làm JMS + HTTP + DB atomic.”** Không: phải biết transaction manager và resource scope.
10. **“Lỗi send nghĩa là broker không hề nhận.”** Sai với kết quả mạng/commit không chắc chắn.
11. **“Retry một sự kiện thì phải sinh eventId mới.”** Đó là cách phá idempotency.
12. **“`JMSRedelivered=false` nghĩa là không có duplicate.”** Producer có thể gửi hai message cùng business event.
13. **“DLQ là nghiệp vụ đã bị xóa khỏi hệ thống.”** Không: operation/outcome có thể vẫn tồn tại và cần xử lý.
14. **“Timeout reply là nghiệp vụ failed.”** Không: chỉ nói caller chưa nhận kết quả đúng hạn.
15. **“Thêm outbox là đã biết consumer thành công.”** Outbox bảo vệ ý định publish; business outcome do consumer xác nhận.
16. **“Thêm inbox là API thanh toán bên ngoài được exactly-once.”** Không: hệ thống đích cần hỗ trợ idempotency/reconciliation.
17. **“Spring Boot có @JmsListener nên luôn retry.”** Cần xem factory thực tế và broker redelivery settings.
18. **“Dùng JMS request–reply sẽ hết bất định.”** Reply vẫn có thể mất/đến muộn/trùng; cần operation ID và result store.

## 19. Checklist ra quyết định

- [ ] Mỗi chữ “success” ghi rõ **producer send**, **JMS transaction commit**, **consumer delivery**, **DB commit**, hay **caller observed result**.
- [ ] `eventId`/`operationId` ổn định xuyên retry; không dùng JMSMessageID làm business key.
- [ ] Hiểu `PERSISTENT`, TTL, queue/topic, subscriber, broker journal, redelivery và DLQ.
- [ ] Listener ACK/transaction thực tế được xác minh bằng bean config và fault injection.
- [ ] Business transaction có invariant và unique constraint/idempotency trong cùng DB transaction.
- [ ] Có phương án cho side effects ở hệ thống ngoài DB.
- [ ] Khi producer DB → JMS, xem xét transactional outbox; khi consumer JMS → DB, áp dụng inbox/dedupe khi cần.
- [ ] Có outcome store/completion event được gắn với business commit.
- [ ] Caller hiểu timeout = chưa biết kết quả, có thể tra lại bằng operation ID.
- [ ] Phân biệt publish metrics với business completion metrics; có alert backlog, DLQ và outcome pending quá hạn.
- [ ] Thử broker outage, duplicate publish, poison message, restart consumer và crash giữa DB commit/JMS commit.
- [ ] Không trả `COMPLETED` khi mới chỉ có `SEND_RETURNED`.

**Câu hỏi tự kiểm tra:** nếu Order Service log “JMS send successful” còn người dùng hỏi “Hóa đơn của tôi đã được tạo chưa?”, câu trả lời chính xác dựa trên log ấy là **chưa thể kết luận**. Muốn trả lời “đã tạo”, phải xem trạng thái invoice đã commit hoặc business completion message có hợp đồng phản ánh commit.

## Tài liệu đối chiếu

1. [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html) — send, JMS transaction, ambiguity khi failure, asynchronous completion và redelivery.
2. [Jakarta Messaging 3.1 MessageProducer API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/messageproducer) — ý nghĩa sync/async send và `CompletionListener`.
3. [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html) — `JmsTemplate`, `JmsTransactionManager` và tài nguyên transaction.
4. [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html) — transaction của listener và nhu cầu duplicate detection khi DB và JMS commit tách biệt.
5. [Spring Framework 6.2 — AbstractMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html) — ACK mode của các listener container.
6. [Spring Boot 3.4 — JMS Reference](https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html) — Artemis, `JmsTemplate` và transactional listener default.
7. [Spring Guide — Messaging with JMS](https://spring.io/guides/gs/messaging-jms/) — tích hợp gửi/nhận bằng Spring Boot.

**Kết luận cần ghi nhớ:** `SEND_RETURNED` là **tín hiệu phía gửi**; `BUSINESS_COMMITTED` là **tín hiệu của nguồn dữ liệu nghiệp vụ**. Nối hai mốc đó thành một cam kết đáng tin đòi hỏi transaction boundaries rõ ràng, stable ID, retry/outbox, idempotent consumer và cơ chế theo dõi/tra cứu kết quả.