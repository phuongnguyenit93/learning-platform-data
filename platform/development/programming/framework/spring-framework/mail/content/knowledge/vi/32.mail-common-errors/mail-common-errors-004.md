# Gọi send trong transaction rồi giả định rollback được email

Một lỗi rất thường gặp khi tích hợp **Spring Framework Mail** vào nghiệp vụ là gọi `JavaMailSender.send(...)` trong một phương thức có `@Transactional`, rồi tin rằng nếu transaction database bị rollback thì email cũng sẽ được “thu hồi”. Suy nghĩ ấy xuất phát từ một giả định sai: **transaction của Spring quản lý database (hoặc tài nguyên giao dịch đã cấu hình), không tự biến một SMTP server bên ngoài thành thành viên của transaction**.

Kết quả có thể nghiêm trọng: khách hàng nhận thư “Đặt hàng thành công” trong khi đơn hàng đã rollback; hệ thống gửi email kích hoạt tài khoản nhưng tài khoản không tồn tại; hoặc một lần retry do database lỗi khiến người nhận nhận hai email. Ở chiều ngược lại, nếu trì hoãn gửi tới sau commit nhưng không lưu ý định gửi bền vững, process có thể chết giữa commit và send, khiến email không bao giờ được gửi.

Bài học thuộc chương **Lỗi thường gặp** của *Spring Framework Mail*, tập trung vào lỗi **“Gọi send trong transaction rồi giả định rollback được email”**. Ta sẽ phân tích ranh giới ACID, thứ tự failure, ví dụ Spring/Java/Jakarta Mail, các giải pháp phù hợp ở nhiều mức độ tin cậy, cách kiểm thử để chứng minh rollback không thu hồi email, cùng checklist vận hành production.

> **Kết luận cốt lõi:** `@Transactional` không khiến SMTP send trở thành một hành động có thể rollback. Ngay cả khi `JavaMailSender.send(...)` không ném exception, điều đó chủ yếu phản ánh **kết quả SMTP submission theo transport**, không bảo đảm thư đã tới Inbox.

## 1. Ví dụ sai: email gửi thành công nhưng đơn hàng biến mất

Xét một Spring service xử lý đặt hàng:

```java
package com.example.orders;

import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderRepository orders;
    private final JavaMailSender mailSender;

    public OrderService(
            OrderRepository orders,
            JavaMailSender mailSender) {
        this.orders = orders;
        this.mailSender = mailSender;
    }

    @Transactional
    public Order placeOrder(CreateOrderCommand command) {
        Order order = orders.save(Order.from(command));

        SimpleMailMessage email = new SimpleMailMessage();
        email.setFrom("orders@example.test");
        email.setTo(command.customerEmail());
        email.setSubject("Đặt hàng thành công");
        email.setText("Mã đơn: " + order.getId());

        mailSender.send(email);

        // Ví dụ lỗi xảy ra SAU khi SMTP đã nhận thư:
        if (command.failForDemonstration()) {
            throw new IllegalStateException("Simulated DB rollback");
        }

        return order;
    }
}
```

Giả sử service được gọi qua Spring proxy và transaction manager đã bắt đầu database transaction. Nếu SMTP relay chấp nhận thư, sau đó `IllegalStateException` lan ra khỏi method, transaction thường rollback theo mặc định đối với unchecked exception. Tuy nhiên, SMTP relay **không nhận được lệnh rollback tương ứng**. Thư vẫn có thể được tiếp tục giao tới người nhận.

```mermaid
sequenceDiagram
    participant R as HTTP request
    participant S as Spring service
    participant DB as Business database
    participant SMTP as SMTP relay
    R->>S: placeOrder()
    S->>DB: BEGIN, INSERT order
    S->>SMTP: Send email over SMTP
    SMTP-->>S: 250 Accepted after DATA
    S->>S: Exception thrown
    S->>DB: ROLLBACK
    S-->>R: Request failed
    Note over DB,SMTP: Order rolled back; SMTP mail not rolled back
```

Không có phép “undo send” đối với một email SMTP đã được relay chấp nhận. Người nhận có thể đã thấy email hoặc relay đang tiếp tục chuyển tiếp thư trong khi business database không chứa đơn hàng.

### 1.1. Lỗi nằm ở đâu?

Không phải Spring `@Transactional` “bị hỏng”. Nó đang làm đúng hợp đồng: rollback **database work** mà transaction manager sở hữu. Lỗi thuộc về **giả định của code nghiệp vụ** rằng tất cả side effects trong lexical scope của một annotated method đều tham gia transaction.

### 1.2. Vòng đời transaction không đồng nghĩa ranh giới method

Trong cấu hình proxy-based thông thường, một lời gọi qua proxy tới method `@Transactional` sẽ:

1. Mở hoặc tham gia transaction phù hợp.
2. Thực thi method.
3. Commit nếu điều kiện thành công.
4. Rollback hoặc đánh dấu rollback-only khi cần.

Những gì nằm trong method có thể bao gồm database writes, logging, HTTP calls, SMTP calls, file writes, cache updates và event publishing. **Spring transaction manager không tự động đảo ngược mọi loại side effect**. Muốn hai tài nguyên cùng được commit nguyên tử cần một giao thức/phối hợp riêng được hai bên hỗ trợ; SMTP thông thường không tham gia giao dịch phân tán XA/2PC.

## 2. Database transaction và SMTP là hai hệ thống khác nhau

### 2.1. ACID bảo vệ tài nguyên giao dịch nào?

Một JDBC/JPA transaction điều phối database connection và các thay đổi do connection/transaction manager đó thực hiện. Nó cung cấp các bảo đảm ACID theo mức isolation và tính năng database:

- **Atomicity:** nhóm database changes commit cùng nhau hoặc rollback cùng nhau.
- **Consistency:** các constraint/quy tắc dữ liệu được giữ theo contract.
- **Isolation:** các transaction đồng thời quan sát nhau theo isolation level.
- **Durability:** thay đổi đã commit tồn tại qua crash theo bảo đảm của database.

Trong khi đó, SMTP là protocol gửi thư giữa client và server qua network. `JavaMailSenderImpl` sử dụng Jakarta Mail để gửi SMTP commands, MIME content và nhận replies. SMTP không chấp nhận `ROLLBACK` của JDBC như một phần của cùng transaction.

### 2.2. “Gửi thư” gồm nhiều pha, không phải một bước nguyên tử

Một phiên SMTP đơn giản có thể đi qua:

```text
TCP connect / TLS / AUTH
EHLO
MAIL FROM
RCPT TO
DATA
[MIME content ending with SMTP terminator]
250 2.0.0 accepted by relay
```

Các mã có ý nghĩa khác nhau:

| Phản hồi/pha | Ý nghĩa | Có chắc email đã giao tới Inbox không? |
|---|---|---|
| `235` sau AUTH | Đăng nhập SMTP thành công | Không |
| `250` sau MAIL FROM | Envelope sender được chấp nhận | Không |
| `250` sau RCPT TO | Recipient được chấp nhận cho transaction hiện tại | Không |
| `354` sau DATA | Server sẵn sàng nhận nội dung | Không |
| `250` **sau toàn bộ DATA** | Relay chấp nhận message theo SMTP submission | **Vẫn không** |
| Delivery webhook/event | Provider báo trạng thái downstream theo contract | Không tự chứng minh Inbox placement |

Một send call trả bình thường thường có thể được hiểu là submit thành công tới SMTP relay đã cấu hình theo semantics client/transport. Nhưng quá trình giao thư sau đó còn phụ thuộc relay tiếp theo, mailbox đích, bounce, policy chống spam và các điều kiện khác.

### 2.3. Giao dịch database không thể thu hồi bản sao ở SMTP relay

Ngay khi relay đã accepted, nó có thể đã lưu hoặc chuyển tiếp thư. Database có rollback `orders`, `payments` hoặc `user_accounts` cũng không điều khiển được hàng đợi SMTP của provider.

Một thủ thuật như “gửi email hủy đơn sau rollback” **không phải rollback**: nó là một compensating action mới, có thể lỗi, đến chậm hoặc bị người nhận bỏ qua. Không nên biến thư đính chính thành một lời bảo đảm về tính nguyên tử.

## 3. Những failure windows dẫn đến sai lệch

### 3.1. Gửi trước commit, rồi rollback

```text
T0  BEGIN DB transaction
T1  INSERT order
T2  SMTP returns accepted
T3  UPDATE inventory fails
T4  DB ROLLBACK
T5  Customer receives confirmation
```

Đây là trường hợp rõ nhất: **email có thể tồn tại, dữ liệu nghiệp vụ không tồn tại**.

### 3.2. SMTP chậm làm transaction database kéo dài

```text
BEGIN
  insert order
  read customer
  connect SMTP ...
  wait TLS/AUTH ...
  upload attachment ...
  wait server reply ...
COMMIT
```

Nếu SMTP mất 10 giây, database connection và một số locks có thể bị giữ lâu thêm 10 giây. Khi traffic tăng:

- Connection pool dễ bị cạn.
- Row locks kéo dài, tăng contention/deadlock.
- Request p95/p99 tăng.
- API gateway có thể timeout.
- Người dùng retry request, gây thêm duplicate events.
- SMTP relay outage có thể lan thành incident của database/API.

Không dùng DB transaction như một container chung cho network I/O lâu dài.

### 3.3. SMTP ném exception rồi business transaction rollback

```text
T0  BEGIN
T1  INSERT order
T2  SMTP connection timeout
T3  MailSendException propagates
T4  ROLLBACK order
```

Lúc này, một lỗi ở dịch vụ email có thể ngăn cả đơn hàng được tạo, dù product requirement có thể chỉ yêu cầu tạo đơn và gửi mail sau. Đây là **coupling giữa availability của SMTP và nghiệp vụ chính**.

Tùy nghiệp vụ, có trường hợp phải fail toàn thao tác nếu không thể bảo đảm notification được tiếp nhận; nhưng yêu cầu ấy nên được đáp ứng bằng việc **commit intent bền vững** hoặc trả lỗi rõ ràng, không mặc định phụ thuộc synchronous SMTP.

### 3.4. Send accepted nhưng client không nhận phản hồi cuối

```mermaid
sequenceDiagram
    participant App as Spring mail client
    participant Relay as SMTP relay
    App->>Relay: DATA + message content
    Relay->>Relay: Accept message
    Relay--xApp: Final 250 lost
    Note over App,Relay: Client sees timeout; relay may have accepted
```

Client có thể thấy `MailSendException` hoặc nested timeout, nhưng **không biết chắc** relay đã nhận message hay chưa nếu response mất ở thời điểm nhạy cảm. Retry ngay có thể tạo hai email. Trong khi đó, `@Transactional` có thể rollback database vì exception, dẫn đến tổ hợp phức tạp: không có order, có thể đã có mail, và client tưởng mọi thứ thất bại.

Không phân loại mọi timeout thành `NOT_SENT`. Cần bảo lưu outcome **UNKNOWN** khi không đủ bằng chứng.

### 3.5. Commit trước rồi gửi trực tiếp: cửa sổ mất email

Để tránh “gửi trước commit”, một số code đổi thứ tự:

```text
DB COMMIT order
  |
  | process crashes before SMTP send
  v
Email never submitted
```

Tránh được “thư về đơn hàng rollback” nhưng xuất hiện lỗi ngược lại: **order đã tồn tại, email intent không được lưu**. Nếu send chỉ tồn tại trong RAM/call stack, restart không biết cần gửi thư.

### 3.6. Gửi thành công rồi không ghi được status

Ngay cả khi worker tách ra:

```text
SMTP accepted
  -> DB update status=SENT fails
  -> worker crashes
  -> recovery sees pending job
  -> SMTP send might be attempted again
```

Đây là cửa sổ quan trọng của mọi kiến trúc email. Transactional outbox ngăn **mất intent** nhưng không tự bảo đảm exactly-once SMTP submission. Cần attempt tracking, idempotency ở tầng nghiệp vụ và recovery theo mức chắc chắn của kết quả.

## 4. @Transactional kiểm soát rollback theo loại exception

Theo mặc định trong Spring declarative transaction phổ biến, unchecked exceptions và `Error` khiến transaction rollback, còn checked exceptions không mặc định luôn gây rollback (có thể cấu hình `rollbackFor` hoặc rollback rules khác). Điều này ảnh hưởng trực tiếp tới lỗi gửi thư:

```java
@Transactional
public Order placeOrder(CreateOrderCommand command) {
    Order order = orders.save(...);
    mailSender.send(...); // MailException là unchecked exception
    return order;
}
```

Nếu `MailException` lan ra khỏi method qua transaction interceptor, transaction có thể rollback theo rule mặc định. Nhưng nếu code bắt và nuốt exception:

```java
@Transactional
public Order placeOrder(CreateOrderCommand command) {
    Order order = orders.save(...);
    try {
        mailSender.send(...);
    } catch (MailException failure) {
        logger.warn("Mail failed");
    }
    return order;
}
```

transaction có thể **commit** mặc dù mail failed hoặc outcome unknown. Điều này không nhất thiết sai nếu yêu cầu cho phép email best-effort, nhưng cần có cơ chế ghi lỗi/retry khi email quan trọng. Một dòng `catch` không tự tạo ra durable retry.

### 4.1. “Lỗi nằm trong transaction” không luôn nghĩa đã rollback

Phụ thuộc vào:

- Exception có lan ra qua transactional proxy hay không.
- Rollback rules của annotation/transaction manager.
- Transaction đã bị mark rollback-only bởi tài nguyên khác chưa.
- Propagation (REQUIRED, REQUIRES_NEW, NESTED...).
- Gọi method qua Spring proxy hay self-invocation.

Đừng dùng câu “trong method có `@Transactional` thì bất cứ lỗi gì cũng rollback” làm quy tắc tuyệt đối. Điều đúng trong bài học này là **dù database có rollback thật, SMTP vẫn không rollback theo**.

### 4.2. Flush không phải commit

JPA `saveAndFlush(...)` hoặc `EntityManager.flush()` có thể đẩy SQL xuống database sớm hơn, nhưng transaction vẫn chưa commit. Nếu gọi SMTP sau flush mà transaction rollback, email vẫn có thể được relay accepted trong khi dữ liệu bị hủy.

```text
INSERT/FLUSH != COMMIT
SMTP accepted != DB commit
```

Không dùng `flush()` làm giải pháp cho ranh giới giao dịch này.

### 4.3. Không sử dụng REQUIRES_NEW như thuốc giải

Đổi `propagation=REQUIRES_NEW` ở một method có gửi SMTP không biến SMTP thành tài nguyên transactional. Nó chỉ tạo một **database transaction mới** khi được gọi qua proxy thích hợp. Nếu transaction ngoài rollback, transaction trong đã commit vẫn tồn tại; SMTP accepted cũng vẫn tồn tại. Điều này có thể khiến business data không nhất quán hơn.

Tương tự, nested transaction/savepoint của JDBC không thể rollback một SMTP message đã được chấp nhận. Hãy dùng propagation khi có lý do transaction rõ ràng, không dùng để giải quyết vấn đề undo external email.

## 5. Những “cách sửa nhanh” không giải quyết triệt để

### 5.1. Chỉ đổi sang @Async

Một phương án thường thấy:

```java
@Transactional
public Order placeOrder(CreateOrderCommand command) {
    Order order = orders.save(...);
    asyncMailService.sendOrderEmail(order.id());
    return order;
}
```

```java
@Async("mailExecutor")
public void sendOrderEmail(Long orderId) {
    mailSender.send(...);
}
```

Mục tiêu tránh block request có thể đạt được khi asynchronous method execution hoạt động. Nhưng có ít nhất bốn rủi ro:

1. Worker có thể bắt đầu **trước khi DB transaction của caller commit**, khiến việc load order bằng connection khác không thấy row hoặc thấy trạng thái cũ.
2. Transaction của worker không được truyền tự động qua thread; `@Transactional` của request không biến SMTP call ở worker thành một phần của transaction.
3. Task lưu trong executor queue RAM có thể mất khi process crash sau business commit.
4. Exception ở `void @Async` không quay lại caller như synchronous exception; cần `AsyncUncaughtExceptionHandler`/future/error handling riêng, và vẫn chưa có durable retry.

`@Async` hữu ích để chuyển CPU/I/O khỏi request thread nhưng không thay thế **atomic persistence of intent**.

### 5.2. Chỉ dùng @TransactionalEventListener(AFTER_COMMIT)

Spring hỗ trợ listener gắn với pha transaction:

```java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.event.TransactionPhase;

@Component
public class OrderMailListener {

    private final JavaMailSender mailSender;

    public OrderMailListener(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCreated(OrderCreated event) {
        mailSender.send(buildMessage(event));
    }
}
```

Mặc định, khi listener được đăng ký trong một transaction có pha commit, callback AFTER_COMMIT sẽ chạy sau commit thành công. Nếu transaction rollback, listener loại này không được gọi cho event đó. Đây là cải thiện so với **gửi trước commit**, nhưng chưa có bảo đảm bền vững:

```text
DB commits order
   |
   | JVM crash / OS kill
   v
AFTER_COMMIT listener never runs
```

Ngoài ra, trong cấu hình listener đồng bộ, callback có thể chạy trên thread đang hoàn tất transaction; gửi SMTP ở đó vẫn khiến request bị kéo dài. Nếu chuyển listener sang `@Async` thì có thể giảm blocking nhưng task vẫn có thể mất khi restart.

**Điều quan trọng:** AFTER_COMMIT nghĩa “đã qua mốc commit”, không phải “đã được thêm vào một durable queue”.

### 5.3. Tại sao cần cẩn trọng khi listener ghi database sau commit?

Trong Spring transaction synchronization, ở pha `afterCommit`, một số transactional resources có thể vẫn còn được bound tới thread trong quá trình hoàn tất transaction. Nếu callback muốn thực hiện một **database write mới phải commit độc lập**, nên gọi service khác qua Spring proxy với `PROPAGATION_REQUIRES_NEW` để tạo transaction mới, theo hướng dẫn lifecycle của Spring.

Ví dụ:

```java
@Service
public class MailAuditWriter {

    @Transactional(
            propagation = Propagation.REQUIRES_NEW)
    public void recordAttemptStarted(UUID notificationId) {
        auditRepository.insert(notificationId);
    }
}
```

Nhưng việc tạo một transaction mới cho audit **không làm email tham gia transaction** và không loại bỏ crash window giữa business commit và callback. Giải pháp production vẫn nên ghi outbox intent trong transaction gốc nếu yêu cầu không mất việc.

### 5.4. TransactionSynchronization.afterCommit cũng có giới hạn

Một phiên bản dùng callback trực tiếp:

```java
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public void scheduleAfterCommit(OrderCreated event) {
    TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                mailSender.send(buildMessage(event));
            }
        });
}
```

Nó cho phép kiểm soát thời điểm thực thi trong transaction lifecycle. Tuy nhiên:

- Chỉ đăng ký được khi transaction synchronization đang active; không gọi tùy tiện khi không có transaction hợp lệ.
- Callback không được persist bền vững chỉ vì được đăng ký.
- SMTP lỗi vẫn có thể làm callback ném exception khi DB đã commit.
- Một callback gửi mail chậm có thể kéo dài response nếu chạy đồng bộ.
- Các side effects của callback không tự rollback theo database commit đã hoàn tất.

Không dùng callback này như cơ chế guaranteed delivery.

### 5.5. @TransactionalEventListener không tự fallback ngoài transaction

Theo contract thông thường, một `@TransactionalEventListener` với `fallbackExecution=false` (mặc định) chỉ xử lý khi event được publish trong transaction phù hợp. Nếu gọi publisher ngoài transaction, listener có thể không chạy. Bật `fallbackExecution=true` cho phép thực thi ngoài transaction nhưng không giải quyết crash window hoặc duplicate.

Nếu muốn listener chỉ đóng vai trò **đánh thức worker** sau commit, có thể dùng event AFTER_COMMIT để kích hoạt polling sớm, song worker vẫn cần quét outbox định kỳ để phục hồi trường hợp event bị mất.

### 5.6. “Gửi mail hủy” không phải rollback

Một số hệ thống cố sửa sai bằng cách:

```text
Send "Order confirmed"
DB rollback
Send "Sorry, order cancelled"
```

Email thứ hai là một **compensating notification** chứ không xóa email đầu tiên. Nó có thể bị trễ, thất bại hoặc đến trước email xác nhận do các hệ thống downstream. Với dữ liệu nhạy cảm như mã kích hoạt hoặc password reset, hậu quả không chỉ là hiểu nhầm. Cần tránh gửi thông tin chưa commit ngay từ đầu.

## 6. Khi nào AFTER_COMMIT có thể chấp nhận được?

Không phải mọi email đều đòi cơ chế outbox phức tạp. Với email best-effort có thể bỏ qua khi process restart, business có thể chấp nhận:

```text
DB commit
  -> AFTER_COMMIT + bounded @Async
  -> SMTP best effort
```

Điều kiện là:

- Yêu cầu nghiệp vụ **chấp nhận được** việc mail đôi khi không được gửi.
- Người dùng không bị ảnh hưởng nghiêm trọng nếu mất mail.
- Không có cam kết audit/retry qua restart.
- Có giám sát lỗi và giới hạn executor.
- Nội dung không chứa thông tin đã hết hạn hoặc dữ liệu không được phép gửi.
- API không tuyên bố guaranteed/delivered khi chưa có bằng chứng.

Ví dụ một email trang trí ít quan trọng có thể best-effort, nhưng OTP, thông báo bảo mật, hóa đơn hoặc email bắt buộc theo quy trình thường cần reliability cao hơn. Quyết định dựa vào business SLA, không đơn giản dùng `@Async` cho mọi tình huống.

### 6.1. So sánh các mức độ giải pháp

| Giải pháp | Tránh send trước commit? | Tách khỏi request thread? | Bền vững qua crash? | Retry có audit? |
|---|---|---|---|---|
| Send trực tiếp trong `@Transactional` | Không | Không | Không | Không mặc định |
| `@Async` từ method transactional | Không chắc | Có khi proxy đúng | Không | Không mặc định |
| `AFTER_COMMIT` listener đồng bộ | Có cho event gắn transaction | Không | Không | Không mặc định |
| `AFTER_COMMIT + @Async` | Có cho listener đúng pha | Có | Không | Không mặc định |
| Transactional outbox + worker | Có, khi thiết kế đúng | Có | **Có sau DB commit** | Có thể xây đầy đủ |
| Outbox → durable broker → worker | Có, nếu relay thực hiện đúng | Có | Có theo broker/storage contract | Có, vẫn cần consumer idempotency |

Không có một annotation đơn lẻ nào cung cấp atomic commit giữa database và SMTP relay.

## 7. Transactional outbox: ghi ý định gửi cùng nghiệp vụ

Giải pháp thường phù hợp nhất cho email nghiệp vụ quan trọng là **transactional outbox**. Tư tưởng:

> Trong transaction database, không gửi email. Hãy ghi **một bản ghi ý định gửi** cùng thay đổi nghiệp vụ. Sau commit, worker độc lập đọc bản ghi và thực hiện SMTP submission.

```mermaid
sequenceDiagram
    participant Client as HTTP Client
    participant App as Spring service
    participant DB as Database
    participant Worker as Mail worker
    participant Relay as SMTP relay
    Client->>App: Create order request
    App->>DB: BEGIN
    App->>DB: INSERT order
    App->>DB: INSERT mail_outbox(QUEUED)
    App->>DB: COMMIT
    App-->>Client: Order created; mail QUEUED
    Worker->>DB: Claim due outbox job
    DB-->>Worker: Job + lease token
    Worker->>Relay: Send SMTP message
    Relay-->>Worker: Accepted / rejected / unknown
    Worker->>DB: Record attempt and outcome
```

Trong mô hình này:

- Nếu transaction nghiệp vụ rollback, **order và outbox intent cùng rollback**. Worker không có job để gửi.
- Nếu transaction commit, **order và intent cùng tồn tại bền vững**.
- Nếu SMTP down, job vẫn chờ để retry.
- Nếu worker crash trước khi bắt đầu gửi, job có thể được recovery.
- Nếu SMTP accepted nhưng worker crash trước khi ghi result, outcome vẫn có thể không chắc và phải xử lý riêng.

Outbox giải quyết **atomicity của business state và intent**, không khẳng định atomicity của intent và SMTP delivery.

### 7.1. Mô hình outbox tối thiểu

Một bảng PostgreSQL minh họa:

```sql
CREATE TABLE mail_outbox (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(100) NOT NULL,
    business_event_key VARCHAR(240) NOT NULL,
    recipient_ref VARCHAR(200) NOT NULL,
    template_key VARCHAR(120) NOT NULL,
    template_version VARCHAR(50) NOT NULL,
    payload_ref VARCHAR(300) NOT NULL,
    state VARCHAR(32) NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    lease_owner VARCHAR(120),
    lease_token UUID,
    lease_until TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    accepted_at TIMESTAMPTZ,
    last_error_code VARCHAR(80),
    UNIQUE (tenant_id, business_event_key),
    CONSTRAINT ck_mail_outbox_state CHECK (
        state IN ('QUEUED', 'SENDING', 'RETRY_WAIT',
                  'SUBMISSION_ACCEPTED', 'UNKNOWN',
                  'FAILED', 'DEAD_LETTER')
    )
);

CREATE INDEX ix_mail_outbox_due
ON mail_outbox (next_attempt_at, created_at)
WHERE state IN ('QUEUED', 'RETRY_WAIT');
```

Đây là mẫu schema, không phải DDL bắt buộc. Tùy hệ thống có thể cần `expires_at`, retry category, priority, provider ID, ack/reconciliation flags và bảng attempt riêng. `recipient_ref` và `payload_ref` nên dẫn tới dữ liệu an toàn/versioned; không để một URL tạm hết hạn giữa lúc job chờ nhiều giờ.

**Unique business event key** giúp không enqueue hai email vì cùng request/event được phát lại. Nó không bảo đảm hai lần SMTP attempts sẽ được relay deduplicate.

### 7.2. Application service chỉ ghi DB, không gọi JavaMailSender

```java
package com.example.orders;

import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final OrderRepository orders;
    private final MailOutboxRepository mailOutbox;

    public OrderApplicationService(
            OrderRepository orders,
            MailOutboxRepository mailOutbox) {
        this.orders = orders;
        this.mailOutbox = mailOutbox;
    }

    @Transactional
    public OrderCreatedResponse placeOrder(
            CreateOrderCommand command) {

        Order order = orders.insertIdempotently(command);

        UUID notificationId = mailOutbox.insertIfAbsent(
                order.getTenantId(),
                "order-created:" + order.getId(),
                order.getCustomerRef(),
                "ORDER_CONFIRMED",
                "v1",
                order.getConfirmationPayloadRef());

        return new OrderCreatedResponse(
                order.getId(),
                notificationId,
                "QUEUED");
    }
}
```

`OrderRepository`, `MailOutboxRepository` và DTO là interfaces/classes do dự án định nghĩa. `insertIfAbsent` cần dùng unique constraint và **trả về ID row đã tồn tại** khi có conflict, chứ không được trả UUID mới không lưu. Tất cả database writes cần tham gia cùng transaction manager nếu muốn đạt atomicity.

### 7.3. Lưu gì trong payload?

Với hóa đơn, email có thể cần giá trị tiền và chi tiết đơn tại thời điểm phát hành. Nếu worker chỉ đọc trạng thái order hiện tại nhiều giờ sau, nội dung có thể khác business event đã commit.

Một số lựa chọn:

- Lưu immutable snapshot đã được validate và versioned trong outbox.
- Lưu reference tới bản hóa đơn/tệp đính kèm bất biến.
- Lưu template key/version, locale, tenant identity và recipient reference.
- Với email có TTL như OTP, lưu expiry và kiểm tra trước send.

Không serialize live JPA entity, `HttpServletRequest`, `InputStream` hoặc user session vào queue để “sử dụng sau”. Chúng không có vòng đời bền vững qua transaction/request và có thể rò rỉ dữ liệu.

### 7.4. Không xóa intent ngay khi worker thấy nó

Nếu worker xóa outbox row **trước khi send**, crash làm mất việc. Nếu xóa row sau send nhưng trước khi có đủ result/attempt audit, recovery khó xác định đã xảy ra gì.

Nên giữ trạng thái và retention rõ ràng:

```text
QUEUED
  -> SENDING
  -> SUBMISSION_ACCEPTED
  -> RETRY_WAIT -> SENDING
  -> FAILED / DEAD_LETTER
  -> UNKNOWN (when outcome cannot be determined)
```

Các chuyển trạng thái có điều kiện để không cho một worker stale ghi đè kết quả của worker mới. Job đã accepted có thể được compact theo retention policy về sau, không phải xóa ngay trong một HTTP handler.

## 8. Worker xử lý outbox với transaction ngắn

Mail worker có thể chạy trong cùng Spring Boot application nhưng ở một thread/executor riêng hoặc trong một deployment độc lập. Điều cần bảo đảm là **request path chỉ ghi durable intent**, còn worker được phép mở SMTP connection và quản lý attempts.

Một chu kỳ điển hình:

```text
1. Query due jobs from mail_outbox.
2. Claim a small batch atomically.
3. Commit claim transaction.
4. Resolve payload and compose MIME.
5. Acquire provider rate/connection permit.
6. Call JavaMailSender.send(...) outside DB transaction.
7. Classify SMTP outcome.
8. Commit attempt record and outbox state.
9. Release worker/connection capacity.
```

### 8.1. Vì sao phải claim thay vì SELECT rồi gửi?

Giả sử hai replicas cùng chạy scheduled job:

```text
Worker A -> SELECT mail_outbox WHERE state='QUEUED'
Worker B -> SELECT mail_outbox WHERE state='QUEUED'
Worker A -> SMTP send mail M
Worker B -> SMTP send mail M
```

Nếu không có một thao tác claim nguyên tử, cả hai đều có thể gửi cùng một email. `synchronized` trong một JVM không đủ khi có nhiều pods.

Một ví dụ claim với PostgreSQL:

```sql
WITH candidate AS (
    SELECT id
    FROM mail_outbox
    WHERE state IN ('QUEUED', 'RETRY_WAIT')
      AND next_attempt_at <= NOW()
    ORDER BY next_attempt_at, created_at
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
UPDATE mail_outbox AS job
SET state = 'SENDING',
    lease_owner = :workerId,
    lease_token = :leaseToken,
    lease_until = NOW() + INTERVAL '2 minutes',
    attempts = attempts + 1
FROM candidate
WHERE job.id = candidate.id
RETURNING job.*;
```

Đoạn SQL chỉ minh họa semantics của PostgreSQL; cú pháp cụ thể có thể thay đổi theo database. Một transaction ngắn thực hiện claim, phát hành `leaseToken` mới và commit **trước** khi SMTP call bắt đầu. Nếu cần attempt ID/audit chính xác, hãy insert `mail_attempt` cùng transaction claim.

### 8.2. Ghi kết quả có điều kiện lease token

Khi worker nhận SMTP accepted, có thể update:

```sql
UPDATE mail_outbox
SET state = 'SUBMISSION_ACCEPTED',
    accepted_at = NOW(),
    lease_owner = NULL,
    lease_token = NULL,
    lease_until = NULL
WHERE id = :id
  AND state = 'SENDING'
  AND lease_token = :leaseToken;
```

Nếu update trả 0 rows, worker đã mất ownership hoặc job đổi state; không ghi đè bừa. Điều này gọi là **fencing** ở tầng DB state.

Tuy vậy, fencing **không ngăn** một SMTP request của worker cũ đã được relay accepted. Nếu lease hết hạn trong lúc worker A vẫn truyền DATA, worker B có thể claim và gửi lại, dù update của A bị từ chối. Cần timeout/lease phù hợp, heartbeats có điều kiện và recovery thận trọng.

### 8.3. Không giữ transaction trong lúc send

Sai:

```text
BEGIN
SELECT FOR UPDATE outbox row
mailSender.send(...)
UPDATE outbox
COMMIT
```

Đúng hơn:

```text
DB transaction A: claim + attempt start -> COMMIT

SMTP network call outside DB transaction

DB transaction B: attempt outcome + job state -> COMMIT
```

Cách này tránh giữ row locks/database connections suốt network timeout, nhưng không loại bỏ uncertainty giữa các lần commit và side effect. Cần chấp nhận giới hạn này một cách có thiết kế.

### 8.4. Mô hình attempt

Ngoài outbox row, nên ghi attempts để phân biệt “notification này” và “lần gửi này”:

```sql
CREATE TABLE mail_attempt (
    id UUID PRIMARY KEY,
    outbox_id UUID NOT NULL REFERENCES mail_outbox(id),
    attempt_number INTEGER NOT NULL,
    provider_id VARCHAR(120),
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    category VARCHAR(64),
    smtp_code INTEGER,
    enhanced_code VARCHAR(32),
    provider_message_id VARCHAR(240),
    safe_error_code VARCHAR(100),
    UNIQUE (outbox_id, attempt_number)
);
```

Không lưu raw SMTP transcript gồm AUTH payload, recipient list/PII hoặc MIME body vào bảng attempt chỉ để debug. Các mã lỗi/chứng cứ cần được lọc và giữ trong phạm vi truy cập được kiểm soát.

## 9. Worker gửi email bằng JavaMailSender

Phần transport có thể vẫn dùng Spring Framework Mail bình thường. Việc tách worker không buộc phải viết lại một SMTP protocol client hoặc dùng reactive/nonblocking framework.

```java
package com.example.mailworker;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Component;

@Component
public class OrderMailComposer {

    private final JavaMailSender sender;
    private final MailTemplateRenderer templates;

    public OrderMailComposer(
            JavaMailSender sender,
            MailTemplateRenderer templates) {
        this.sender = sender;
        this.templates = templates;
    }

    public MimeMessage compose(OrderMailPayload payload)
            throws MessagingException {
        MimeMessage mime = sender.createMimeMessage();

        MimeMessageHelper helper =
                new MimeMessageHelper(mime, true, "UTF-8");

        helper.setFrom("orders@example.test");
        helper.setTo(payload.recipientEmail());
        helper.setSubject(templates.renderSubject(payload));
        helper.setText(
                templates.renderPlainText(payload),
                templates.renderHtml(payload));

        return mime;
    }
}
```

`MailTemplateRenderer` và `OrderMailPayload` là abstraction ứng dụng. Worker có thể compose rồi gọi `JavaMailSender.send(mime)` trong một method riêng.

Điều quan trọng:

- Compose lỗi khác SMTP lỗi; không retry sai template vô hạn.
- Worker được quyền dùng SMTP credentials của provider thích hợp, không lấy secrets từ request.
- Nếu dùng attachment, resource/stream phải còn hợp lệ khi Jakarta Mail serialize và có thể mở lại khi retry.
- Không giữ `MimeMessage` hoặc attachment bytes lớn cho hàng nghìn job đang chờ trong RAM queue.
- Với template/version hoặc invoice snapshot, nội dung cần nhất quán với business intent đã commit.

### 9.1. Gửi đồng bộ bên trong worker là hợp lệ

Một worker đã chạy trên thread tách khỏi HTTP có thể **gọi đồng bộ**:

```java
public void submit(MimeMessage mime) {
    mailSender.send(mime);
}
```

Không cần thêm một lớp `@Async` lồng nhau chỉ để SMTP trở thành asynchronous hai lần. Nó có thể khiến worker tưởng send hoàn tất khi task con còn chờ; làm ownership/lease, attempt outcome và shutdown khó kiểm soát. Tách request-thread boundary ở dispatcher/worker là đủ khi số worker được giới hạn.

### 9.2. SMTP timeout phải được đặt rõ

Một ví dụ Spring Boot:

```yaml
spring:
  mail:
    host: smtp.example.test
    port: 587
    username: ${MAIL_SMTP_USER}
    password: ${MAIL_SMTP_PASSWORD}
    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.starttls.enable]": "true"
      "[mail.smtp.starttls.required]": "true"
      "[mail.smtp.ssl.checkserveridentity]": "true"
      "[mail.smtp.connectiontimeout]": "5000"
      "[mail.smtp.timeout]": "10000"
      "[mail.smtp.writetimeout]": "10000"
```

Port và security mode phải theo provider thực tế: STARTTLS submission thường dùng 587, implicit TLS thường dùng 465; không giả định hai kiểu handshake giống nhau. Các property timeout làm hạn chế blocking ở một số bước socket nhưng không tự đặt deadline tổng cho render/attachment/network/DB update.

### 9.3. Không dùng request context của người dùng trong worker

Worker có thể chạy sau request nhiều phút, thậm chí ở một process khác. Không dựa vào:

- `HttpServletRequest` hoặc HTTP session.
- JPA entity đã detached/lazy-loading dựa trên transaction request.
- `SecurityContextHolder` vốn gắn với thread/request.
- Live `InputStream` từ multipart upload hoặc file tạm.
- MDC/correlation context cũ không được truyền và cleanup.

Thay vào đó, lưu immutable DTO/payload reference, tenant ID và quyền truy cập thích hợp. Worker dùng service identity, kiểm tra tenant scope và lưu correlation ID để audit; đừng serialize authentication principal/JWT dài hạn vào queue.

## 10. Retry sau lỗi: phân loại đúng trước khi gửi lại

Spring `JavaMailSender` có thể ném những `MailException` thường gặp:

| Exception/tín hiệu | Ý nghĩa ban đầu | Quyết định phù hợp |
|---|---|---|
| `MailParseException` | Message/address không hợp lệ | Sửa input, không retry nguyên payload vô hạn |
| `MailPreparationException` | Lỗi build MIME/resource | Phân biệt template/config và storage tạm thời |
| `MailAuthenticationException` | SMTP AUTH thất bại | Pause provider account, kiểm tra credentials |
| `MailSendException` | SMTP submission failed một/một số messages | Đọc nested SMTP details, phân loại theo phase |
| SMTP 4xx có bằng chứng | Temporary rejection | Retry có backoff/quota policy |
| SMTP 5xx rõ permanent | Rejection/config/recipient | Phân loại scope trước khi suppress |
| Timeout sau DATA | Có thể accepted nhưng reply mất | `UNKNOWN_OUTCOME`/reconciliation |

Không nên gọi `exception.getMessage().contains("550")` rồi hard-suppress mọi recipient. Mã `550 5.1.1` ở RCPT TO thường khác lỗi `550 5.7.1` relaying/sender restriction. Cùng một primary code có thể mang ý nghĩa khác tùy provider, phase và enhanced status code.

### 10.1. Retry không phải giữ thread ngủ

Anti-pattern:

```java
while (true) {
    try {
        mailSender.send(mime);
        break;
    } catch (MailException failure) {
        Thread.sleep(60_000);
    }
}
```

Đoạn trên không có retry budget, không phân biệt lỗi vĩnh viễn và giữ worker suốt thời gian chờ. Nếu hàng nghìn jobs cùng bị 451, hệ thống dễ hết threads và gây retry storm.

Mẫu worker tốt hơn:

```text
attempt #1 -> SMTP 451 temporary
  -> record attempt
  -> state RETRY_WAIT
  -> nextAttemptAt = now + backoff + jitter
  -> free worker slot

later dispatcher -> claim when due -> attempt #2
```

Có `maxAttempts`, TTL/deadline, exponential backoff có trần, jitter và provider quota. Nếu provider đã hết quota một ngày, retry vài giây một lần là vô ích. Khi SMTP accepted, không tiếp tục retry chỉ vì chưa có delivery webhook.

### 10.2. UNKNOWN không phải FAILED chắc chắn

Tách riêng:

- `NOT_STARTED`: chưa mở SMTP, có bằng chứng không có attempt.
- `TEMPORARY_REJECTED`: relay từ chối tạm, có code và phase.
- `PERMANENT_REJECTED`: relay từ chối theo bằng chứng phù hợp.
- `SUBMISSION_ACCEPTED`: relay đã accepted ở ranh giới submit.
- `UNKNOWN_OUTCOME`: không thể kết luận accepted hay rejected.

Khi outcome UNKNOWN, hành động tùy duplicate tolerance. Có thể dùng provider lookup API nếu có ID và contract phù hợp; nếu không, đánh dấu cần reconciliation/manual review hoặc retry có chấp nhận rủi ro. `Message-ID` không là cơ chế exactly-once giữa các SMTP relays.

### 10.3. Durable retry khác in-memory retry

Một `RetryTemplate` hoặc `@Retryable` có thể hữu ích cho một số lỗi transient ngắn, nhưng không tự tồn tại qua process restart và có thể lặp lại thao tác đã gây side effect. Với retry dài, nên lưu `nextAttemptAt` trong outbox. Dùng retry chỉ bao quanh bước có semantics rõ và an toàn để chạy lại.

### 10.4. Khi provider có quota

Giới hạn có thể gồm messages/s, recipients/s, concurrent SMTP connections, daily quota và MIME size. Số worker không tự biểu diễn tất cả những limits đó.

Ví dụ một provider giả định:

```text
messagesPerSecond        = 10
maxConcurrentConnections = 4
```

Ngay cả khi worker pool chỉ có 4 threads, có thể gửi hơn 10/s khi mỗi call nhanh. Ngược lại, limiter 10/s vẫn có thể mở quá 4 connections nếu mỗi call chậm. Cần **rate limiter và concurrency cap riêng** khi provider áp dụng hai loại giới hạn. Nhiều pods dùng cùng account phải áp dụng quota **cấp cluster**, không chỉ trong từng JVM.

## 11. Vì sao transactional outbox vẫn cần idempotency?

Mẫu outbox thường mang ngữ nghĩa “intent được lưu ít nhất một lần, attempts có thể được thực thi lại”. Nó giải quyết rủi ro mất intent, nhưng vẫn có thể gửi lặp:

```text
Worker A CLAIMS outbox M
Worker A SENDS M
Relay ACCEPTS M
Worker A crashes before storing SENT
Lease expires
Worker B retries M
Recipient may receive another copy
```

Từ góc độ hệ thống, SMTP send và DB write không có atomic commit chung, nên không thể tuyên bố exactly-once chỉ bằng outbox.

### 11.1. Hai lớp dedupe cần khác nhau

| Lớp | Khóa | Ngăn được gì? |
|---|---|---|
| HTTP request | `(tenantId, idempotencyKey)` | Client retry tạo duplicate business action |
| Business event | `(tenantId, orderId, eventType)` | Cùng sự kiện enqueue hai notifications |
| Mail outbox attempt | `(notificationId, attemptNumber)` | Ghi attempt history nhất quán |
| SMTP provider API (nếu hỗ trợ) | Provider-defined idempotency key | Có thể dedupe submission theo contract riêng |
| Người dùng/consumer | Business semantics của email | Giảm tác hại nếu một thông báo xuất hiện nhiều lần |

Không lấy attempt ID ngẫu nhiên làm business idempotency key: mỗi retry sẽ có ID mới, nên không chống trùng event. Với email xác nhận đơn hàng, nên dựa trên order ID/event type đã được xác thực và bảo đảm unique ở database.

### 11.2. Partial recipients

Một SMTP message có thể chứa nhiều RCPT TO; provider/client có thể chấp nhận một phần recipient và từ chối phần còn lại. Nếu retry nguyên batch, một số người nhận có thể nhận trùng. Khi cần retry chính xác per recipient, dùng một notification/recipient hoặc theo dõi recipient-level SMTP outcomes với contract rõ.

### 11.3. Business command an toàn khi người nhận nhận hai thư

Một số email chứa link có thể bị click nhiều lần. Link kích hoạt đơn hàng/thanh toán không nên thực hiện side effect mỗi lần click nếu business chỉ cho phép một lần. Token và endpoint nhận link cũng cần idempotent, expiry, authorization và replay protection phù hợp. Đây là một lớp an toàn khác ngoài mail transport.

## 12. Tách request thread và bounded worker pool

Sau khi application service ghi outbox, worker không cần nằm trong cùng HTTP request. Một cấu hình Spring Boot thường dùng executor riêng:

```java
package com.example.mailworker;

import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableScheduling
public class MailWorkerConfiguration {

    @Bean(name = "mailWorkerExecutor")
    ThreadPoolTaskExecutor mailWorkerExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setThreadNamePrefix("mail-worker-");
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.initialize();

        return executor;
    }
}
```

Đây là ví dụ có 4 worker và 16 queue slots, **không phải** khuyến nghị capacity cho mọi provider. Nếu tác vụ có retry backoff dài, chúng không nên ngủ chiếm những slots này. Khi executor đầy, phải có policy rõ: job vẫn tồn tại trong DB, dispatcher không làm mất durable intent.

### 12.1. Không claim nhiều hơn khả năng xử lý

Một lỗi khác là claim 10.000 rows từ outbox rồi mới submit vào executor 4 workers. Các jobs nằm lâu trong JVM queue, lease có thể hết hạn trước khi thực sự bắt đầu SMTP, dẫn đến duplicate claim.

Dispatcher nên:

1. Chỉ claim khi còn permit/in-flight capacity.
2. Dùng batch nhỏ phù hợp concurrency.
3. Commit claim trước khi submit hoặc có transaction/compensation nhất quán.
4. Khi executor reject, release/retry job bằng lease token.
5. Khi process chết sau claim, lease/recovery đảm bảo job không mất.

Một semaphore local có thể giới hạn số job của một dispatcher, nhưng không kiểm soát tổng concurrency giữa các replicas. Rate limiter theo SMTP account cần được áp dụng ở scope thực tế, có thể trên toàn cluster.

### 12.2. Giới hạn memory của queue

Queue 100 tasks không hẳn nhỏ nếu mỗi task capture một attachment 8 MB, vì riêng bytes có thể gần 800 MB chưa kể MIME encoding/buffers và phần còn lại của heap. Nên queue **job IDs hoặc immutable references**, không chứa `MimeMessage`/request/session/attachment bytes lớn.

### 12.3. API response phản ánh điều gì?

Nếu request tạo đơn hàng, có thể trả:

```text
HTTP/1.1 201 Created
Content-Type: application/json

{
  "orderId": "ORDER-1042",
  "notificationId": "MAIL-8821",
  "emailStatus": "QUEUED"
}
```

Nếu API chỉ tiếp nhận yêu cầu gửi notification bất đồng bộ, HTTP `202 Accepted` kèm tracking ID có thể phù hợp. Không trả `emailStatus=DELIVERED` ngay sau khi insert outbox.

Một status endpoint có thể thể hiện:

```text
QUEUED -> SENDING -> SUBMISSION_ACCEPTED
                  -> RETRY_WAIT -> SENDING
                  -> FAILED / DEAD_LETTER
                  -> UNKNOWN
```

Nếu provider hỗ trợ webhook, có thể lưu delivery status riêng, ví dụ delivered/bounced/deferred, với semantics theo provider. “Delivered” từ provider chưa chắc là vào Inbox.

### 12.4. Web và worker có thể tách deployment

Giai đoạn đầu có thể dùng cùng Spring Boot app nhưng executor riêng. Khi lưu lượng hoặc yêu cầu cô lập tăng:

```text
Web nodes:
  validate request
  commit order + mail intent
  return HTTP response
  no SMTP credentials needed when separated

Mail worker nodes:
  claim outbox jobs
  compose and submit SMTP
  persist attempt results
  monitor quotas and retries
```

Một worker deployment riêng cho phép scale theo backlog/SMTP quota, cấp credential và network egress hạn chế cho web nodes, và restart worker mà không tác động trực tiếp tới API. Tuy nhiên, **tách service** không thay đổi bản chất lack of atomicity giữa SMTP và DB; nó chỉ làm ranh giới rõ hơn.

## 13. Graceful shutdown và hard kill

Khi triển khai hoặc scale down, worker có thể đang:

```text
3 SMTP sends active
20 jobs in local executor queue
5000 jobs pending in database
```

Một shutdown an toàn nên:

1. Dừng nhận claim mới.
2. Cho active attempts kết thúc trong grace period hợp lý.
3. Cập nhật result khi có thể; nếu không, để lease/recovery xử lý.
4. Không loại bỏ pending outbox jobs.
5. Khi restart, worker recheck status và quota trước attempt mới.

Spring `ThreadPoolTaskExecutor` có các cấu hình chờ task hoàn tất và await termination, nhưng **không** bảo đảm khi OS kill, OOM, mất nguồn hoặc process bị terminate cứng. Do đó, durability thuộc về outbox database, không thuộc shutdown hook.

### 13.1. Recovery không phải đặt mọi SENDING về QUEUED

Một scheduled reaper có thể tìm `SENDING` với `lease_until < NOW()`. Nhưng nếu worker chết sau SMTP accepted mà trước DB update, retry mù có thể gửi trùng.

Phân loại dựa trên attempt history:

| Trạng thái nhận biết | Recovery có thể thực hiện |
|---|---|
| Claimed nhưng có bằng chứng chưa mở SMTP | Requeue sau lease expiry |
| SMTP AUTH bị từ chối rõ ràng | Pause account, sửa cấu hình |
| SMTP 451 tạm thời có response | Backoff/retry theo policy |
| SMTP 250 accepted và result đã commit | Không gửi lại |
| Mất response cuối hoặc result DB mất | UNKNOWN, reconciliation/duplicate policy |

Trạng thái network từ một attempt không phải lúc nào cũng quan sát được đầy đủ. Khi không có bằng chứng, giữ uncertainty thay vì dựng một “not sent” certainty giả.

### 13.2. Rolling deploy có thể đổi template và payload schema

Nếu outbox job được tạo bởi web app version A nhưng worker version B xử lý sau deploy, cần:

- Template key/version rõ ràng.
- Payload schema version.
- Attachment reference còn tồn tại và có quyền truy cập.
- Migration DB tương thích với các jobs cũ.
- Không xóa template cũ khi backlog chưa hết.
- Chiến lược rollback worker không làm gửi trùng.

Đừng coi outbox row là một function call lưu tạm: đó là **hợp đồng dữ liệu** giữa các phiên bản producer/consumer.

## 14. Các phương án khác và khi nào chọn

### 14.1. Message broker với durable consumer

Một số hệ thống đẩy mail jobs qua RabbitMQ, Kafka hoặc hạ tầng queue tương đương. Đây là lựa chọn hợp lý cho workload lớn hoặc hệ thống đã có broker. Nhưng phải giải quyết hai vấn đề:

- **DB → broker boundary:** nếu business DB commit rồi publish broker thất bại, event có thể mất. Transactional outbox + relay/CDC là một giải pháp.
- **Broker → SMTP boundary:** consumer có thể gửi SMTP accepted rồi chết trước ack broker, khiến message redeliver. Vẫn có duplicate risk và cần idempotency/reconciliation.

Không nhầm broker durability với exactly-once end-to-end SMTP.

### 14.2. Synchronous send có bao giờ phù hợp?

Có, trong một số công cụ nội bộ/kiểm thử, ví dụ giao diện admin yêu cầu gửi một email test và muốn hiển thị ngay SMTP acceptance/rejection. Tuy nhiên:

- Không gọi trong business database transaction đang mở.
- Có timeout, rate limit và audit.
- Trả kết quả đúng là SMTP submission, không phải delivery.
- Cân nhắc khả năng user bấm gửi lại khi timeout.

Nếu nghiệp vụ bắt buộc blocking send trước khi trả response, hãy thiết kế bù sai lệch giữa DB và SMTP một cách tường minh; không giả định có rollback tự động.

### 14.3. Outbox bằng database hay durable queue?

Tiêu chí lựa chọn:

| Tiêu chí | DB outbox | Durable broker/queue |
|---|---|---|
| Atomic với business DB writes | Tự nhiên khi cùng transaction | Cần outbox relay hoặc giao thức phối hợp |
| Retry schedule/state | Tự thiết kế SQL/poller | Phụ thuộc broker tính năng/delay queue |
| Audit theo business key | Dễ join trong DB | Cần metadata/store bổ sung |
| Scale throughput | Phụ thuộc DB và tối ưu claim | Broker thường thuận tiện cho fan-out/load cao |
| Redelivery | Lease/reclaim | Broker ack/nack/rebalance |
| SMTP exactly-once | Không tự có | Không tự có |

Không có một lựa chọn “tốt cho mọi trường hợp”. Nhưng với đề bài lỗi *send trong DB transaction rồi giả định rollback*, điều bất biến là **không coi SMTP là thao tác DB có thể đảo ngược**.

## 15. Kiểm thử chứng minh rollback không thu hồi email

Đây là bài học dễ hiểu hơn khi kiểm thử hai sự thật độc lập:

1. Database rollback sau exception.
2. SMTP test relay đã nhận message trước khi rollback.

### 15.1. Test bằng SMTP sandbox thay vì mail thật

Dùng SMTP test server như **GreenMail** hoặc **Mailpit**, cấu hình `JavaMailSenderImpl` trỏ tới local test port. Mục tiêu:

```text
BEGIN DB transaction
INSERT order
JavaMailSender.send(test email)
SMTP sandbox accepts email
throw RuntimeException
DB ROLLBACK

Assertions:
  DB has no new order
  SMTP sandbox received one email
```

Không gửi mail tới địa chỉ khách hàng thật để chứng minh lỗi này. Sandbox/localhost giúp thí nghiệm có kiểm soát và lặp lại được.

### 15.2. Ví dụ dùng TransactionTemplate cho ranh giới rõ ràng

```java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.transaction.support.TransactionTemplate;

class SendInTransactionRollbackIT {

    private final TransactionTemplate tx;
    private final OrderRepository orders;
    private final JavaMailSender sender;
    private final TestSmtpInbox smtpInbox;

    SendInTransactionRollbackIT(
            TransactionTemplate tx,
            OrderRepository orders,
            JavaMailSender sender,
            TestSmtpInbox smtpInbox) {
        this.tx = tx;
        this.orders = orders;
        this.sender = sender;
        this.smtpInbox = smtpInbox;
    }

    @Test
    void rollbackDoesNotRetractAcceptedSmtpMail() {
        assertThrows(IllegalStateException.class, () ->
                tx.executeWithoutResult(status -> {
                    orders.insertTestOrder("ORDER-1");

                    SimpleMailMessage mail = new SimpleMailMessage();
                    mail.setFrom("test@example.test");
                    mail.setTo("recipient@example.test");
                    mail.setSubject("Order created");
                    mail.setText("ORDER-1");
                    sender.send(mail);

                    throw new IllegalStateException("rollback");
                }));

        assertFalse(orders.exists("ORDER-1"));
        assertEquals(1, smtpInbox.receivedCount());
    }
}
```

Đây là **khung integration test minh họa**: `OrderRepository` và `TestSmtpInbox` là fixture do dự án triển khai; cần chạy với Spring test context, database transaction manager thật và SMTP sandbox, chờ bounded cho SMTP server ghi nhận message khi cần. Nếu `smtpInbox` chỉ là mock, test không chứng minh hoạt động wire-level của SMTP.

Test không nên bị bọc bởi một transaction `@Transactional` ở test method làm khó quan sát commit/rollback thực; chọn setup/cleanup và transaction boundaries rõ ràng.

### 15.3. Test ngược: SMTP exception nhưng DB có commit hay không?

Với code ban đầu, nếu `MailSendException` lan ra khỏi `@Transactional`, database có thể rollback theo default unchecked-exception rule. Nếu code `catch` rồi return bình thường, database có thể commit.

Hai test nên xác nhận **policy của ứng dụng**, thay vì dựa vào assumption:

```text
Case A: mail exception propagates
  DB rows = 0 (when rollback rule applies)
  Email accepted? may be UNKNOWN depending on phase

Case B: mail exception caught and swallowed
  DB row = 1 (unless marked rollback-only)
  Durable mail retry? none unless implemented
```

Đừng biến case B thành giải pháp production bằng cách chỉ thêm log. Nếu email quan trọng, cần outbox/job status, retry và alert.

### 15.4. Test AFTER_COMMIT vẫn có crash window

Một integration test có thể xác minh listener không được gọi khi transaction rollback và được gọi sau successful commit. Nhưng nó **không chứng minh** callback bền vững qua process crash. Để kiểm thử durability, hãy dừng tiến trình sau DB commit trước callback/worker dispatch ở môi trường kiểm soát, restart và kiểm tra outbox job vẫn tồn tại.

Không đồng nhất “listener chạy trong test bình thường” với guaranteed delivery khi host bị kill.

## 16. Kiểm thử transactional outbox như một hệ thống độc lập

Một test của outbox cần chứng minh điều **cốt lõi khác** với test SMTP rollback:

> Khi transaction nghiệp vụ rollback, không có email intent nào được commit; khi transaction commit, intent tồn tại để worker xử lý kể cả khi SMTP đang lỗi hoặc JVM restart.

### 16.1. Rollback order và outbox cùng nhau

Kịch bản:

```text
BEGIN transaction
INSERT orders(order_id=ORDER-2)
INSERT mail_outbox(business_event_key=order-created:ORDER-2)
THROW RuntimeException
ROLLBACK
```

Sau rollback:

```text
orders row count for ORDER-2 = 0
mail_outbox row count for event = 0
SMTP attempts = 0
```

Đây mới là cách đạt bảo đảm “không gửi xác nhận về dữ liệu chưa commit” ở phía outbox, với điều kiện dispatcher chỉ xử lý job **đã commit** và không có luồng gửi đồng bộ cũ cùng chạy.

### 16.2. Commit intent rồi làm SMTP unavailable

Kịch bản:

1. Cho business transaction commit order và outbox.
2. Dừng SMTP test server hoặc fake transport trả lỗi kết nối.
3. Worker claim và thử gửi một lần.
4. Kiểm tra job được ghi `RETRY_WAIT` (hoặc trạng thái policy xác định), có attempt record và `nextAttemptAt`.
5. Khởi động lại worker hoặc SMTP server.
6. Chỉ khi đến hạn, worker claim lại; API tạo order **không** phải chạy lại.

Một SMTP outage không nên làm order đã commit biến mất hoặc khiến API phải giam request thread tới khi email gửi thành công.

### 16.3. Two-worker claim test

Chạy hai worker instances cùng truy cập PostgreSQL database:

```text
Exactly one outbox row is due.
Worker A and Worker B try claim concurrently.
Only one receives valid lease token.
Other sees no eligible row or a different row.
```

Không dùng chỉ `synchronized` hoặc fake repository in-memory để chứng minh multi-replica safety. Test atomic claim trên database production-equivalent, với unique constraints và transaction isolation thực.

### 16.4. Fault injection theo thời điểm

| Thời điểm giả lập crash | Điều cần xác nhận |
|---|---|
| Trước business DB commit | Không có business record hoặc outbox intent mới |
| Sau business commit trước worker wakeup | Outbox job vẫn QUEUED qua restart |
| Sau claim trước SMTP connect | Lease/recovery có thể retry khi an toàn |
| Trong quá trình SMTP DATA | Không thể luôn khẳng định NOT_SENT |
| Sau SMTP accepted trước DB result commit | UNKNOWN risk/attempt history, không xóa job |
| Sau SUBMISSION_ACCEPTED commit | Restart không gửi lại notification đó |
| Sau provider downstream bounce | Submission history vẫn accepted; delivery outcome riêng |
| Khi dispatcher executor reject | Job vẫn trong durable storage, không thất lạc |
| Khi worker hard kill | Lease recovery/alert; không phụ thuộc graceful shutdown |

Điểm đo quan trọng là **số business effects và số notification intents**, không chỉ số lần một Java method được gọi. Một worker có thể thực thi lại cùng job, nhưng database business key phải tránh duplicate theo policy.

### 16.5. Không nhầm kiểm thử với bảo đảm exactly-once

Test chạy mười nghìn lần không có duplicate chỉ chứng minh các kịch bản kiểm thử không lộ ra vấn đề. Nó không làm biến mất giới hạn nguyên lý của SMTP. Khi socket timeout sau DATA và reply cuối bị mất, client không có cách chung của SMTP để chứng minh chắc chắn “đã gửi” hoặc “chưa gửi”. Test phải giữ được trạng thái UNKNOWN khi đó.

## 17. Observability: điều tra sai lệch giữa DB và email

Khi gặp báo cáo “khách nhận thư dù đơn hàng không tồn tại”, hệ thống phải truy vết từ business key tới transaction outcome và SMTP attempt:

```text
httpRequestId
  -> orderId / businessEventKey
  -> outboxNotificationId
  -> attemptId + providerId
  -> SMTP response phase/code
  -> downstream delivery events
```

Nếu code cũ gửi mail trong transaction không có outbox, có thể thiếu notification ID. Khi đó cần logs và SMTP test/provider trace để tái dựng sự kiện, nhưng không được gán “commit thành công” chỉ vì relay accepted.

### 17.1. Metrics cần theo dõi

| Nhóm | Metric/tín hiệu | Để trả lời câu hỏi |
|---|---|---|
| HTTP | Request latency p50/p95/p99, 5xx | SMTP có đang kéo dài request? |
| DB | Transaction rollback count, lock wait, connection pool usage | Transaction có bị giữ mở? |
| Outbox | QUEUED/RETRY_WAIT/SENDING counts | Backlog đang ở trạng thái nào? |
| Outbox | Oldest due age | Email có trễ quá SLA? |
| Dispatcher | Claims/s, conflicts, failed claims | Worker có tiến triển? |
| Worker | Active threads, queue depth, rejections | Capacity có bão hòa? |
| SMTP | Attempts/s, p95 duration, 4xx/5xx/auth/timeout | Relay có đang khỏe? |
| Retry | Attempts per notification, next-attempt delay | Retry storm hoặc lỗi kéo dài? |
| Recovery | Lease expired và UNKNOWN outcomes | Crash/uncertain windows có tăng? |
| Downstream | Deferred/bounce/complaint theo provider | Thư bị lỗi sau submit? |
| Business | Duplicate event conflict count | Idempotency có đang chặn requests trùng? |

### 17.2. Log tránh dữ liệu nhạy cảm

```text
event=mail_attempt_finished
notificationId=MAIL-8821
attemptId=ATT-3
businessEventType=ORDER_CREATED
providerId=primary
smtpPhase=AFTER_DATA
outcome=UNKNOWN
safeReasonCode=SMTP_REPLY_TIMEOUT
```

Không log raw MIME body, Bcc list, OTP, reset links, attachment bytes hoặc SMTP AUTH exchange. SMTP debug có thể in protocol data ngoài logging framework; chỉ bật khi có phạm vi, thời gian, quyền truy cập và che dữ liệu phù hợp.

Thông tin `notificationId` và `attemptId` phù hợp cho log/traces nhưng thường không nên làm Prometheus metric labels vì cardinality cao.

### 17.3. Alert có ý nghĩa nghiệp vụ

Một error SMTP 451 đơn lẻ thường không đáng báo động. Nhưng:

- SMTP 451 tăng liên tục và oldest due age vượt SLA.
- Nhiều requests rollback sau khi đã gọi SMTP đồng bộ.
- Nhiều SENDING leases hết hạn và UNKNOWN attempts.
- Provider auth fail trên toàn account.
- Worker ngừng claim nhưng outbox tồn tại nhiều jobs đến hạn.
- Executor rejection tăng và API có fallback chạy SMTP trên request thread.

là những tín hiệu cần điều tra. Alert nên tách scope account/provider/tenant và ưu tiên tác động thực.

## 18. Runbook: khách nhận email cho đơn hàng đã rollback

### Bước 1 — Xác minh hai sự kiện độc lập

Tìm bằng chứng:

- Business record đã commit hay rollback? Có transaction rollback log/DB audit?
- SMTP relay đã accepted submission hay chỉ bắt đầu DATA?
- Có provider downstream event nào và correlation ID không?
- Email có phải từ lần request trước, một retry khác hoặc một luồng cũ không?

Không mặc định email chứng minh order tồn tại hay log rollback chứng minh mail chưa gửi.

### Bước 2 — Tìm code path thực sự gọi send

Kiểm tra call graph ở tầng ứng dụng:

```text
Controller
 -> Service @Transactional
 -> Repository writes
 -> JavaMailSender.send
 -> more DB writes / commit
```

Nếu `send(...)` nằm trước commit, đây là failure mode cốt lõi. Nếu send ở listener AFTER_COMMIT, lỗi có thể là missing durability hoặc client timeout sau commit; phân tích khác.

### Bước 3 — Đọc timeline bằng ID

Sắp xếp:

```text
request_received
db_transaction_started
smtp_attempt_started
smtp_accepted
db_transaction_rolled_back
request_failed
```

Nếu có nhiều replicas, cần đồng bộ clock ở mức vận hành và dùng trace/transaction IDs khi có; log timestamps không phải bằng chứng duy nhất của ordering khi clock lệch.

### Bước 4 — Ngăn sự cố tiếp tục

Tùy mức độ nghiêm trọng:

- Disable code path gửi trong transaction bằng feature flag có kiểm soát.
- Tạm pause luồng email có nội dung nhạy cảm/misleading.
- Không retry các request lỗi bừa bãi khi idempotency chưa được bảo đảm.
- Gắn giám sát business-state/email mismatch.
- Nếu có nghĩa vụ thông báo cho khách, thực hiện communication đã duyệt, không tự gửi hàng loạt một mẫu “xin lỗi” mà chưa xác minh recipients.

### Bước 5 — Khắc phục kiến trúc

Chuyển sang:

```text
Business transaction:
  apply business changes
  insert outbox intent
  commit

Worker:
  claim after commit
  compose/send SMTP
  track outcomes
```

Tạo tests cho rollback, commit, crash, retries và unknown outcomes trước rollout. Khi migrate, cần đảm bảo **không có hai routes (synchronous cũ + worker mới) gửi cùng event**.

### Bước 6 — Hậu kiểm

Xác nhận số business events, số outbox intents và SMTP attempts khớp theo policy; xem các trường hợp bị duplicate/unknown và kết quả hỗ trợ người dùng. Ghi lại nguyên nhân gốc, phạm vi tác động và các guardrails mới.

## 19. Một số tình huống phân tích cụ thể

### Tình huống A — Đăng ký tài khoản thất bại sau gửi email

```text
User registration BEGIN
INSERT pending user
Send verification link -> relay accepts
Unique constraint violation in later DB update
ROLLBACK
```

Người dùng nhận link tới tài khoản không tồn tại. Link không nên tạo tài khoản ngoài ý muốn chỉ vì email được mở; endpoint verify phải kiểm tra business state và token theo policy. Sửa bằng cách commit user + email intent nguyên tử, worker gửi sau commit.

### Tình huống B — Gửi hóa đơn rồi transaction bị deadlock

```text
BEGIN
INSERT invoice
SMTP accepted invoice PDF
Database deadlock -> rollback
Request retry -> new send attempt
```

Khách có thể nhận hai hóa đơn trong khi invoice ban đầu rollback. Không khắc phục bằng cách chỉ tăng retry count cho DB; cần tách SMTP ra khỏi transaction, unique business key và outbox.

### Tình huống C — Đặt hàng commit thành công nhưng response lỗi

```text
BEGIN
INSERT order + outbox intent
COMMIT succeeds
HTTP connection closes before client receives response
Client retries POST
```

Outbox giúp intent không mất, nhưng request retry vẫn cần idempotency key để không tạo thêm order/event. Đây là lỗi ở ranh giới **HTTP ↔ DB**, khác với SMTP ↔ DB, và có thể giải quyết bằng application idempotency.

### Tình huống D — AFTER_COMMIT listener ném MailSendException

```text
Business transaction COMMIT successful
AFTER_COMMIT listener calls SMTP
SMTP failure -> exception
Caller sees error, may retry request
```

Business transaction **đã commit**; một exception ở callback không biến commit trước đó thành rollback. Cần ghi nhận trạng thái đúng, không để caller hiểu nhầm “đơn hàng chưa tạo”. Với mail cần reliability, ghi outbox trong transaction và worker retry thay vì dựa hoàn toàn vào callback đồng bộ.

### Tình huống E — @Async chạy trước khi caller commit

```text
Request: INSERT order within transaction
Request: schedule async send(orderId)
Worker: SELECT order by ID -> not found
Request: COMMIT order
```

Worker có thể không thấy uncommitted row do isolation. Thêm sleep 500ms vào worker chỉ che race condition, không bảo đảm commit sẽ hoàn tất. AFTER_COMMIT tránh race này nhưng không có durability; outbox giải quyết cả timing và crash-loss theo contract.

### Tình huống F — Gửi OTP sau khi đã hết hạn

```text
DB commits OTP + email outbox
SMTP provider throttled for 10 minutes
OTP TTL = 5 minutes
```

Worker cần kiểm tra expiry trước submission; nếu mã đã hết hạn, mark EXPIRED và cho người dùng yêu cầu mã mới theo cơ chế an toàn. Outbox không có nghĩa phải gửi **mọi thứ** bất kể đã lỗi thời.

### Tình huống G — SMTP accepted nhưng status DB chưa cập nhật

```text
Worker sends mail
Relay returns 250 accepted
DB unavailable before update accepted_at
Worker terminates
```

Recovery không biết chắc status. Nếu gửi lại, có thể duplicate. Nếu bỏ qua, có thể bỏ sót trong các trường hợp reply hiểu sai. Cần attempt state, reconciliation/duplicate-risk policy và audit; không có một quyết định đúng chung cho mọi nghiệp vụ.

## 20. Các ngộ nhận phổ biến

**“Bất cứ thứ gì gọi trong @Transactional đều rollback được.”** Sai. Transaction manager quản lý những resources tham gia transaction; SMTP relay không tự tham gia JDBC/JPA transaction.

**“SMTP trả 250 rồi DB rollback sẽ gửi lệnh thu hồi email.”** Không có cơ chế rollback email SMTP tương đương JDBC ROLLBACK sau khi relay accepted.

**“Gửi thư trước commit để chắc chắn email đến rồi mới lưu đơn.”** Đó là cách tạo trạng thái email đã được gửi nhưng đơn hàng không tồn tại. Nếu DB không commit, SMTP không thể tự xóa kết quả.

**“Nếu MailSendException xảy ra thì email chắc chắn chưa gửi.”** Sau DATA, response có thể bị mất trong khi relay đã accepted; outcome có thể UNKNOWN.

**“Nếu send không ném exception thì người nhận chắc chắn thấy Inbox.”** Send accepted không bảo đảm downstream delivery hoặc Inbox placement.

**“Flush database trước send nghĩa DB đã commit.”** JPA flush không thay thế commit. Transaction vẫn có thể rollback sau flush.

**“Đổi propagation thành REQUIRES_NEW để SMTP tham gia transaction.”** Propagation chỉ điều phối database transaction theo contract; SMTP không vì thế có rollback.

**“Catch MailException rồi return là đủ.”** Có thể cho DB commit nhưng mail intent không bền vững; mất khả năng retry/audit khi process restart.

**“@Async luôn chạy sau commit.”** Worker có thể được schedule trước khi transaction caller commit, phụ thuộc thời điểm executor chạy.

**“@Async chuyển transaction sang worker thread.”** Spring thread-bound transaction không tự truyền qua thread khác; external SMTP vẫn không tham gia DB transaction.

**“@TransactionalEventListener(AFTER_COMMIT) bảo đảm mail không mất.”** Nó tránh gửi trước commit nhưng vẫn có crash window sau commit trước callback. Gửi đồng bộ trong listener còn có thể kéo dài response.

**“AFTER_COMMIT callback ném lỗi có thể rollback commit vừa hoàn tất.”** Transaction đã commit; caller có thể thấy lỗi nhưng database không trở lại trạng thái trước.

**“Chỉ cần một in-memory queue là durable.”** Task có thể mất khi JVM crash, restart hoặc process bị hard kill.

**“Message broker tự biến DB+SMTP thành exactly-once.”** DB→broker và broker→SMTP đều có các failure boundaries cần giải quyết; broker redelivery là bình thường.

**“Transactional outbox đảm bảo mỗi người chỉ nhận một email.”** Nó đảm bảo intent được commit cùng nghiệp vụ; SMTP outcome uncertainty vẫn có thể tạo duplicate attempts.

**“Có lease và fencing là không thể gửi trùng.”** Lease/fencing không thu hồi được SMTP DATA đã được relay tiếp nhận bởi worker cũ.

**“Chỉ cần tăng retry đến vô hạn.”** Permanent errors, invalid recipients, AUTH failures và expired OTP cần hành động khác. Retry storm còn có thể khiến provider throttle mạnh hơn.

**“Một queue hàng trăm nghìn MimeMessage là tốt vì chứa được nhiều.”** Task RAM có thể giữ attachment bytes khổng lồ và bị mất khi process chết; durable backlog nên nằm trong DB/broker.

**“Nếu executor đầy dùng CallerRuns sẽ không mất mail.”** CallerRuns có thể chạy SMTP ngay trên HTTP thread, khôi phục vấn đề blocking ban đầu. Với durable outbox, hãy dùng backpressure/capacity planning đúng chỗ.

**“Mọi SMTP provider dùng một quota/giải thích 550 giống nhau.”** Rate, connection, enhanced status và policy khác nhau; cần provider-aware classification.

**“Đã có SMTP accepted thì outbox nên xóa ngay.”** Cần retention/attempt audit và downstream lifecycle, tùy business contract.

**“Unit test mock JavaMailSender chứng minh rollback thu hồi email.”** Mock chỉ xác nhận method được gọi; không mô phỏng relay accepted và protocol boundary. Dùng SMTP sandbox cho integration test.

## 21. Bài thực hành

### Bài 1 — Chứng minh ranh giới rollback

Tạo Spring Boot application với bảng `orders`, `@Transactional OrderService` và `JavaMailSenderImpl` trỏ tới SMTP sandbox. Trong method, insert order, gọi send, rồi ném unchecked exception. Assert:

```text
DB order count = 0
SMTP sandbox received messages = 1
```

Giải thích vì sao hai kết quả không mâu thuẫn.

### Bài 2 — So sánh rollback rules

Thử ba biến thể:

1. `MailException` lan ra khỏi transaction method.
2. `MailException` được catch và nuốt.
3. Method ném checked exception, có và không có `rollbackFor` phù hợp.

Ghi lại DB outcome theo cấu hình và nhớ rằng SMTP side effect độc lập với mỗi outcome.

### Bài 3 — Kiểm tra JPA flush

Gọi `saveAndFlush(...)` rồi gửi email, sau đó rollback transaction. Xác minh order vẫn rollback nhưng sandbox nhận message. Viết giải thích khác biệt giữa flush và commit.

### Bài 4 — AFTER_COMMIT

Chuyển send sang `@TransactionalEventListener(AFTER_COMMIT)`. Test transaction rollback không kích hoạt listener; commit thành công kích hoạt. Sau đó mô phỏng crash window sau commit và nêu vì sao callback vẫn chưa guaranteed.

### Bài 5 — Tạo transactional outbox

Thiết kế bảng `mail_outbox` có business event unique key, state, attempts và nextAttemptAt. Ghi business order và outbox cùng transaction. Test rollback xóa cả hai; commit giữ cả hai.

### Bài 6 — Idempotency khi HTTP retry

Client gửi hai yêu cầu cùng idempotency key sau khi lần đầu mất HTTP response. Dùng unique key và payload comparison để chỉ tạo một order và một mail intent.

### Bài 7 — Worker claim đồng thời

Chạy hai worker instances claim cùng một job bằng PostgreSQL. Chỉ một worker nhận lease token hợp lệ. Trình bày vì sao một `synchronized` Java không đủ với nhiều pods.

### Bài 8 — Retry temporary

SMTP test server trả 451. Worker ghi RETRY_WAIT/nextAttemptAt và release slot thay vì `Thread.sleep`. Test maxAttempts, backoff, jitter và expiry của job.

### Bài 9 — SMTP accepted rồi DB result fail

Cho SMTP sandbox nhận thư, sau đó cố ý làm DB result update thất bại. Mô tả trạng thái UNKNOWN và các lựa chọn reconciliation. Không tuyên bố chắc chắn lần gửi tiếp theo không thể tạo duplicate.

### Bài 10 — Worker shutdown

Enqueue 100 jobs, cho 4 attempts đang chạy, rồi dừng worker. Xác nhận các job chưa claim vẫn trong DB; các job chưa xác định outcome được recovery bằng lease/reconciliation khi restart.

### Bài 11 — Provider quota

Giả sử SMTP account cho tối đa 4 concurrent connections và 10 attempts/s, trong khi chạy 3 pods mỗi pod 5 workers. Thiết kế concurrency cap/rate limiter toàn account để không vượt cả hai quota.

### Bài 12 — Tách web/worker deployment

Tạo hai Spring profiles:

```text
web:
  HTTP + business DB + outbox writer

mail-worker:
  outbox dispatcher + composer + JavaMailSender
```

Kiểm tra khi worker bị dừng, web vẫn commit order và outbox; khi worker lên lại, backlog tiến triển.

### Bài 13 — Phân biệt submission và delivery

Gửi một email tới SMTP sandbox rồi assert relay accepted. Thêm mô hình provider webhook event để biểu diễn delivered/bounced sau đó. Trả lời vì sao không thể gán `DELIVERED_TO_INBOX` ngay khi send không ném exception.

### Bài 14 — Runbook sự cố

Xây timeline cho ca khách nhận email về một hóa đơn đã rollback. Liệt kê dữ liệu cần truy vết, thay đổi code cần thực hiện và phép thử bảo vệ không tái phát.

## 22. Checklist trước khi dùng Spring Mail trong business transaction

### Transaction boundary

- Có `JavaMailSender.send(...)` trong method `@Transactional` hoặc code được gọi bởi nó không?
- Transaction manager đang bảo vệ những database/tài nguyên nào?
- Có external SMTP/HTTP/file side effect xảy ra trước commit không?
- Có hiểu default rollback rules, catch/throw, self-invocation và propagation không?
- Có nhầm `flush()` với commit không?
- Một exception sau SMTP accepted có thể rollback database và tạo email sai trạng thái không?
- SMTP timeout có được phân loại UNKNOWN khi không đủ bằng chứng không?

### Đảm bảo ý định gửi

- Business transaction có insert outbox intent cùng business change không?
- Outbox có unique business event key và request idempotency policy không?
- Khi DB rollback, worker có chắc chắn không nhận intent chưa commit không?
- Khi DB commit, intent có tồn tại qua process crash/deploy không?
- Payload/attachment/template có version và vẫn truy xuất được sau một thời gian chờ không?
- Có tách submission accepted khỏi downstream delivery status không?
- Có tránh khẳng định exactly-once SMTP khi chưa có contract như vậy không?

### Worker và retry

- Worker có claim nguyên tử, lease token và update state có điều kiện không?
- Có commit claim trước SMTP call, không giữ DB transaction mở trong lúc network I/O không?
- Có attempt history để phân biệt notification với mỗi lần gửi không?
- Có retry backoff, jitter, max attempts và TTL không?
- Có phân loại permanent recipient/config errors khác temporary provider errors không?
- Có recovery cho SENDING hết lease, không requeue mù khi outcome có thể UNKNOWN không?
- Executor/queue có bounded và không fallback sang request thread ngoài ý muốn không?
- Provider quota được giới hạn trên toàn account/multiple replicas không?

### Testing và vận hành

- Đã có test chứng minh DB rollback không thu hồi mail đã accepted ở SMTP sandbox chưa?
- Có test rollback business + outbox và commit cùng nhau không?
- Có test concurrent claim, DB result failure, SMTP timeout và restart không?
- Có đo HTTP latency, DB lock waits, oldest outbox age và SMTP attempt duration không?
- Có log request/business/notification/attempt IDs mà không tiết lộ PII/secrets không?
- Có quy trình pause/replay/dead-letter/incident response không?
- Có bảo vệ khách khỏi mail sai nội dung khi business record chưa commit không?
- Có kế hoạch bỏ hoàn toàn code path gửi đồng bộ cũ sau khi chuyển sang worker không?

## 23. Tổng kết

**Gọi `JavaMailSender.send(...)` trong một transaction Spring rồi tin rằng rollback database sẽ thu hồi email là một lỗi thiết kế.** Transaction của JDBC/JPA không điều khiển SMTP relay. Nếu relay accepted trước khi database rollback, người nhận vẫn có thể nhận email; nếu SMTP chậm, database transaction và HTTP request cũng bị giữ mở không cần thiết.

Chuyển send sang `@Async` giúp đổi thread nhưng không bảo đảm chạy sau commit hay bền vững qua restart. `@TransactionalEventListener(AFTER_COMMIT)` tránh gửi trước successful commit, song vẫn có crash window giữa commit và callback; nó không phải durable queue. Với email quan trọng, kiến trúc phù hợp hơn là **ghi business state và outbox intent trong cùng database transaction**, sau đó để worker độc lập claim, tạo MIME, gửi SMTP và lưu attempt outcome.

Transactional outbox giải quyết việc **không mất ý định gửi sau commit** và tránh gửi về dữ liệu đã rollback, nhưng **không tự bảo đảm exactly-once submission**. Kết quả SMTP có thể UNKNOWN khi mất phản hồi sau DATA hoặc worker không lưu được accepted status. Vì vậy hệ thống phải có idempotency theo business key, attempt history, lease/fencing, backoff, reconciliation và policy duplicate rõ ràng.

Khi thiết kế đúng, database rollback chỉ điều khiển các business changes và outbox row thuộc cùng transaction; SMTP được xử lý như một external side effect độc lập. **Đó là ranh giới cần hiểu chính xác để Spring Framework Mail vận hành đáng tin cậy trong production.**





