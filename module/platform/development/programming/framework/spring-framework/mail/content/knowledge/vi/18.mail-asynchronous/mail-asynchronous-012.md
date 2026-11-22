# Đảm bảo transaction không bị hiểu nhầm là kéo dài qua task

Khi tách gửi email sang tác vụ bất đồng bộ trong Spring, một nhầm lẫn thường gặp là cho rằng transaction của method gọi `@Async` sẽ tiếp tục tồn tại trong task nền, hoặc rằng task đã được gọi bên trong `@Transactional` thì chắc chắn chỉ bắt đầu sau khi transaction commit.

**Cả hai giả định đều không đúng.** Transaction database thông thường được gắn với ngữ cảnh thực thi của thread; tác vụ `@Async` chạy ở thread khác và có vòng đời riêng. Hơn nữa, một task có thể bắt đầu ngay khi được executor tiếp nhận, trước khi method nghiệp vụ ở thread gọi kết thúc hoặc commit.

Trong module **Spring Framework Mail**, khác biệt này rất quan trọng. Nếu worker gửi email xác nhận đơn hàng quá sớm, người nhận có thể nhận thông báo về một đơn hàng sau đó bị rollback. Nếu worker đọc dữ liệu khi transaction gốc chưa commit, nó có thể không thấy thay đổi mới. Nếu ứng dụng chết giữa commit và việc lên lịch gửi email, yêu cầu gửi có thể mất. Giải pháp không phải kéo dài transaction qua SMTP, mà là **thiết kế ranh giới transaction, thời điểm phát sinh yêu cầu gửi và cơ chế lưu công việc thật rõ ràng**.

## 1. Ba khái niệm cần phân biệt

| Khái niệm | Vai trò | Điều không nên suy diễn |
| --- | --- | --- |
| `@Transactional` | Xác định phạm vi transaction của thao tác database trong luồng thực thi được intercept | Không khiến mọi thread khác dùng chung transaction |
| `@Async` | Chuyển việc thực thi method sang `TaskExecutor`, thường là một thread khác | Không đợi transaction của caller commit |
| `JavaMailSender.send(...)` | Gửi MIME message qua SMTP theo cấu hình transport | Không tham gia commit/rollback của database |

Một transaction do `PlatformTransactionManager` quản lý thường gắn tài nguyên như JDBC connection hoặc JPA `EntityManager` với thread thông qua `TransactionSynchronizationManager`. Khi method `@Transactional` kết thúc, transaction manager commit hoặc rollback và dọn ngữ cảnh tương ứng.

`@Async` không phải cơ chế chuyển một JDBC transaction đang mở từ thread A sang thread B. Nếu task nền cần đọc hoặc cập nhật database, nó phải làm việc với transaction riêng hoặc các thao tác database theo cấu hình phù hợp trong **chính thread của task**.

### Hai trục độc lập

Hãy tưởng tượng có hai trục:

- **Trục transaction:** bắt đầu, thực hiện các thao tác DB, commit/rollback.
- **Trục thực thi bất đồng bộ:** nhận task, xếp hàng, chạy trên worker, kết thúc hoặc lỗi.

Không có quy tắc mặc định nào bảo đảm hai trục này kết thúc cùng nhau.

```text
Thread HTTP                         Thread mail executor
    |                                      |
    | BEGIN TX A                           |
    | update order                         |
    | gọi asyncMailService.send(...)       |
    |---------------- submit task -------->|
    |                                      | bắt đầu render email
    |                                      | có thể gọi SMTP
    | COMMIT TX A                           |
    |                                      | kết thúc task
    | trả HTTP response                    |
```

Đường submit task chỉ có nghĩa executor được yêu cầu thực hiện công việc. Nó không tạo quan hệ “sau commit” giữa hai thread.

## 2. Transaction của caller không kéo dài sang worker

Giả sử method nghiệp vụ:

```java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final AsyncMailService asyncMailService;

    public OrderService(
            OrderRepository orderRepository,
            AsyncMailService asyncMailService
    ) {
        this.orderRepository = orderRepository;
        this.asyncMailService = asyncMailService;
    }

    @Transactional
    public void confirmOrder(UUID orderId) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow();
        order.confirm();

        asyncMailService.sendConfirmation(order.getId());
    }
}
```

Service gửi:

```java
@Service
public class AsyncMailService {

    @Async("mailExecutor")
    public void sendConfirmation(UUID orderId) {
        // Thực thi ở worker thread, không nằm trong TX của confirmOrder().
    }
}
```

`confirmOrder()` có transaction **A**; `sendConfirmation()` được executor chạy trong một thread khác. Task không tự thừa hưởng transaction A, dù nó nhận cùng `orderId` và dù lời gọi được thực hiện trước khi method `confirmOrder()` trả về.

### Điều gì xảy ra nếu worker truy vấn database?

Worker có thể thực hiện:

```java
@Async("mailExecutor")
public void sendConfirmation(UUID orderId) {
    Order order = orderRepository.findById(orderId)
            .orElseThrow();
    // Render email từ order.
}
```

Nếu TX A chưa commit, truy vấn từ worker dùng transaction/connection riêng có thể:

- Đọc **giá trị cũ** thay vì thay đổi vừa được TX A thực hiện.
- Không tìm thấy một bản ghi vừa được insert trong TX A.
- Phải chờ khóa hoặc gặp lỗi tùy database, isolation level và câu truy vấn.
- Đọc được dữ liệu khác với snapshot mà caller đang sử dụng.

Không nên phụ thuộc vào một lịch chạy may mắn như “SMTP thường chậm nên chắc transaction đã commit trước”. Khi tải thay đổi, worker có thể chạy ngay và bộc lộ race condition.

## 3. Timeline thực tế: async có thể chạy trước commit

Xét thao tác xác nhận đơn:

```text
Thời gian  | Thread HTTP / TX A             | Thread mail / task
-----------+--------------------------------+------------------------------
T0         | BEGIN TX A                     |
T1         | UPDATE orders SET confirmed    |
T2         | submit async task              |
T3         |                                | Đọc order: thấy trạng thái cũ
T4         |                                | Gửi email từ dữ liệu đã đọc
T5         | COMMIT TX A                    |
T6         | HTTP response                  | Task đã hoàn tất
```

Đây là một lịch chạy hợp lệ. Có một lịch khác nguy hiểm hơn:

```text
T0  BEGIN TX A
T1  cập nhật đơn hàng
T2  submit async mail
T3  worker gửi email "Đơn hàng đã được xác nhận"
T4  transaction gặp lỗi kiểm tra ràng buộc
T5  ROLLBACK TX A
```

Người nhận đã được báo đơn hàng xác nhận, nhưng dữ liệu chính thức không ghi nhận điều đó. **SMTP là side effect bên ngoài transaction DB**, vì vậy rollback không thể thu hồi email đã được mail server nhận.

Nguyên tắc: nếu email mô tả một thay đổi nghiệp vụ chỉ có hiệu lực sau commit, yêu cầu gửi phải được điều phối theo commit, không chỉ được gọi từ bên trong method transaction.

## 4. @Async không tự chờ @Transactional kết thúc

Một vài ngộ nhận điển hình:

| Ngộ nhận | Thực tế |
| --- | --- |
| “Gọi `@Async` từ `@Transactional` thì worker đợi commit.” | Executor có thể chạy worker trước commit. |
| “Worker nhận entity nên nó thấy dữ liệu chưa commit.” | Không; transaction của caller không được chia sẻ mặc định. |
| “Thêm `@Transactional` vào worker là nối dài transaction cũ.” | Worker mở phạm vi transaction độc lập theo cơ chế proxy/transaction manager. |
| “`@Transactional(propagation = REQUIRES_NEW)` giúp chạy tiếp TX gốc.” | `REQUIRES_NEW` tạo transaction mới, không kế thừa transaction gốc. |
| “Lỗi gửi email trong worker sẽ rollback transaction của caller.” | Nếu caller đã commit, lỗi async sau đó không thể rollback nó. |
| “Method có `@Async` trả về nghĩa là email đã gửi.” | Nó có thể chỉ mới được xếp vào executor. |
| “`@TransactionalEventListener(AFTER_COMMIT)` làm event được lưu bền vững.” | Nó chỉ đặt thời điểm gọi listener, không tự tạo durable queue. |

### Có cần chuyển transaction context sang task?

Thông thường **không**. Chuyển thủ công JDBC connection, `EntityManager`, transaction synchronization hoặc thread-local transaction state sang worker có thể gây lỗi đồng thời và phá vỡ giới hạn transaction. Những tài nguyên này không được thiết kế để dùng tùy ý trên nhiều thread.

Nếu cần dữ liệu sau commit, hãy để task truy vấn lại trong transaction riêng sau commit hoặc truyền một snapshot/DTO đã được chuẩn bị có chủ đích. Nếu cần độ bền, dùng outbox.

## 5. @Transactional trong chính worker có ý nghĩa gì?

Một method async có thể được đánh dấu `@Transactional`:

```java
@Service
public class AsyncOrderReader {

    private final OrderRepository orderRepository;

    public AsyncOrderReader(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Async("mailExecutor")
    @Transactional(readOnly = true)
    public CompletableFuture<OrderMailData> loadData(UUID orderId) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow();

        OrderMailData data = new OrderMailData(
                order.getCustomerEmail(),
                order.getCode(),
                order.getCustomerName()
        );

        return CompletableFuture.completedFuture(data);
    }
}
```

Với việc intercept được cấu hình đúng, phần đọc database của method chạy trong **transaction B ở worker thread**. Transaction B không phải TX A của caller. Nó có thời điểm bắt đầu/commit riêng và nhìn thấy dữ liệu theo isolation level của database.

### Tại sao không bọc gửi SMTP trong transaction dài?

Giả sử:

```java
@Async("mailExecutor")
@Transactional
public void sendMailAndUpdateStatus(UUID notificationId) {
    MailNotification n = repository.findById(notificationId)
            .orElseThrow();

    mailSender.send(buildMessage(n)); // I/O mạng bên trong DB transaction.

    n.markSubmitted();
}
```

Code này làm DB transaction có thể bị giữ mở trong suốt thời gian chờ SMTP. Nó không làm gửi mail có thể rollback và còn có thể gây:

- Giữ connection và lock lâu.
- Tăng contention khi nhiều worker.
- Giảm throughput khi SMTP chậm.
- Nếu database rollback sau SMTP thành công, trạng thái DB và thực tế gửi không đồng nhất.

Nên **tách transaction ngắn để claim**, **gửi SMTP ngoài transaction**, rồi **transaction ngắn khác để ghi kết quả**.

## 6. REQUIRES_NEW không làm transaction vượt qua ranh giới task

`Propagation.REQUIRES_NEW` chỉ định Spring bắt đầu một transaction mới khi method được intercept trong một phạm vi thực thi phù hợp. Khi một caller đang ở transaction A và gọi một method `REQUIRES_NEW` qua proxy trong cùng thread, Spring có thể tạm ngưng A và chạy B. Nhưng điều đó không đồng nghĩa A được chuyển sang thread khác.

Ví dụ:

```java
@Service
public class MailStatusService {

    private final MailStatusRepository repository;

    public MailStatusService(MailStatusRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void markSubmitted(UUID notificationId) {
        repository.updateStatus(notificationId, "SUBMITTED");
    }
}
```

Khi worker gọi method này qua Spring bean proxy, nó chạy trong transaction mới phục vụ cập nhật status. Không liên quan đến transaction HTTP đã đóng.

**Cần phân biệt hai mục tiêu:**

- Muốn **thực hiện DB write độc lập trong worker**: transaction mới có thể phù hợp.
- Muốn **bảo đảm email chỉ được gửi sau commit nghiệp vụ**: chỉ có `REQUIRES_NEW` không giải quyết được; vẫn cần after-commit coordination hoặc outbox.

Nếu class tự gọi method `@Transactional` của chính nó, proxy có thể bị bỏ qua. Hãy tổ chức transaction boundary ở bean riêng và kiểm tra cấu hình proxy.

## 7. Tách trách nhiệm theo ranh giới transaction

Một kiến trúc dễ hiểu chia thành ba trách nhiệm:

1. **Business service:** thay đổi nghiệp vụ và ghi yêu cầu gửi theo một transaction.
2. **Mail worker:** thực hiện render và SMTP I/O ngoài transaction kéo dài.
3. **Mail status service:** cập nhật kết quả bằng transaction ngắn độc lập.

Sơ đồ:

```text
Business thread                       Mail worker thread
----------------------------          ----------------------------
BEGIN TX A
  update business data
  insert notification PENDING
COMMIT TX A
         |
         | notification có thể đọc sau commit
         +----------------------------> BEGIN TX B
                                        claim notification
                                        COMMIT TX B
                                              |
                                              v
                                        render + SMTP send
                                        (không giữ DB TX)
                                              |
                                              v
                                        BEGIN TX C
                                        update status
                                        COMMIT TX C
```

Đây là mô hình để giảm transaction dài và làm rõ trạng thái. Transaction A, B và C là các transaction **khác nhau**, có thể chạy ở các thread/process khác nhau.

## 8. Có thể dùng @TransactionalEventListener(AFTER_COMMIT) khi nào?

Nếu muốn điều phối tác vụ chạy **sau khi commit** mà không dựng hàng đợi bền vững, Spring có `@TransactionalEventListener`:

```java
public record OrderConfirmedEvent(
        UUID orderId,
        String recipient,
        String orderCode
) {}
```

Trong service nghiệp vụ:

```java
@Service
public class OrderApplicationService {

    private final ApplicationEventPublisher publisher;
    private final OrderRepository orderRepository;

    public OrderApplicationService(
            ApplicationEventPublisher publisher,
            OrderRepository orderRepository
    ) {
        this.publisher = publisher;
        this.orderRepository = orderRepository;
    }

    @Transactional
    public void confirm(UUID id) {
        Order order = orderRepository.findById(id).orElseThrow();
        order.confirm();

        publisher.publishEvent(new OrderConfirmedEvent(
                order.getId(),
                order.getCustomerEmail(),
                order.getCode()
        ));
    }
}
```

Listener nhận sự kiện sau commit và chuyển tới một bean async:

```java
@Component
public class OrderMailEventListener {

    private final AsyncMailSender asyncMailSender;

    public OrderMailEventListener(AsyncMailSender asyncMailSender) {
        this.asyncMailSender = asyncMailSender;
    }

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT
    )
    public void onConfirmed(OrderConfirmedEvent event) {
        asyncMailSender.sendConfirmation(event);
    }
}
```

Task nằm ở bean khác:

```java
@Service
public class AsyncMailSender {

    private final JavaMailSender mailSender;

    public AsyncMailSender(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    @Async("mailExecutor")
    public void sendConfirmation(OrderConfirmedEvent event) {
        // Render message và gửi SMTP.
    }
}
```

Với transaction thông thường đã được Spring quản lý:

- Nếu TX commit, listener `AFTER_COMMIT` được gọi.
- Nếu TX rollback, listener `AFTER_COMMIT` không được gọi.
- Khi listener gọi async sender, task có thể chạy ở worker thread.
- Worker vẫn không thừa hưởng transaction đã commit.

### Giới hạn quan trọng của AFTER_COMMIT

**Sau commit không đồng nghĩa bền vững.** Một application event thông thường tồn tại trong memory. Nếu process crash sau commit nhưng trước khi event được xử lý hoặc task được thực thi, email có thể bị mất.

Ngoài ra:

- Listener không tự bảo đảm retry nếu executor từ chối task.
- Lỗi SMTP xảy ra sau commit không thể rollback đơn hàng.
- Một event có thể thiếu transaction đang hoạt động; mặc định listener transaction-bound không chạy trong trường hợp đó, trừ khi cấu hình fallback phù hợp.
- Việc viết database ngay trong callback after-commit có thể gặp vấn đề vì tài nguyên của transaction cũ vẫn còn được bind trong giai đoạn hoàn tất; nếu cần ghi dữ liệu mới ở callback, hãy dùng transaction mới rõ ràng, ví dụ một service `REQUIRES_NEW`.

`AFTER_COMMIT` phù hợp khi chỉ cần đúng thứ tự commit rồi dispatch và có thể chấp nhận giới hạn mất task. Email quan trọng cần cân nhắc transactional outbox.

## 9. Không dùng after-commit callback như một transaction mới

Spring có `TransactionSynchronization` với callback `afterCommit()`. Có thể đăng ký callback sau commit:

```java
TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                asyncMailSender.sendConfirmation(event);
            }
        }
);
```

Đây là cơ chế thấp hơn so với `@TransactionalEventListener`; nó không mặc định lưu event trong database. Chỉ đăng ký khi có transaction synchronization đang hoạt động và có chủ đích.

Không nên hiểu callback này như một transaction mới. Giai đoạn callback diễn ra sau quyết định commit; nếu callback lỗi, không thể “quay lại” undo commit database đã hoàn tất.

Nếu cần lưu trạng thái mới sau commit, gọi một bean `@Transactional(propagation = REQUIRES_NEW)` hoặc đặt công việc vào worker transaction riêng. Đối với độ tin cậy cao, cách rõ ràng hơn vẫn là **ghi mail request vào outbox trước commit** thay vì phát hành công việc chỉ từ callback.

## 10. Transactional outbox: giải quyết khoảng trống giữa commit và task

Giả sử dùng after-commit event:

```text
COMMIT order ----------- [process crash] ----------> submit async
```

Nếu crash ở khoảng trống này, database đã lưu đơn hàng nhưng task gửi mail chưa được lưu ở đâu. Graceful shutdown hoặc retry tại executor không thể phục hồi một task chưa được ghi nhận.

**Transactional outbox** dùng cùng một database transaction để lưu thay đổi nghiệp vụ và yêu cầu gửi:

```text
BEGIN TX A
  UPDATE orders...
  INSERT mail_notification(status=PENDING)...
COMMIT TX A
       |
       v
Worker đọc notification đã commit
       |
       v
Gửi SMTP và ghi kết quả
```

Nếu TX A rollback, cả thay đổi đơn hàng lẫn notification đều rollback. Nếu TX A commit rồi process crash, notification vẫn có trong database và worker khác có thể tiếp tục xử lý.

### Ví dụ schema tối giản

```sql
CREATE TABLE mail_notification (
    id                 UUID PRIMARY KEY,
    business_event_id  VARCHAR(200) NOT NULL,
    notification_type  VARCHAR(100) NOT NULL,
    recipient          VARCHAR(320) NOT NULL,
    template_key       VARCHAR(150) NOT NULL,
    payload_json       TEXT NOT NULL,
    status             VARCHAR(30) NOT NULL,
    attempts           INTEGER NOT NULL DEFAULT 0,
    next_attempt_at    TIMESTAMP WITH TIME ZONE,
    claim_token        UUID,
    lease_until        TIMESTAMP WITH TIME ZONE,
    created_at         TIMESTAMP WITH TIME ZONE NOT NULL,
    submitted_at       TIMESTAMP WITH TIME ZONE,
    CONSTRAINT uq_mail_event
        UNIQUE (business_event_id, notification_type)
);
```

Bảng này vừa lưu yêu cầu gửi vừa đóng vai trò hàng đợi database. Hệ thống lớn có thể tách outbox event và notification record riêng, nhưng nguyên lý vẫn là ghi chúng cùng transaction với nghiệp vụ.

Unique constraint theo business event giúp ngăn hai lời gọi lặp tạo hai notification cho cùng một sự kiện, khi policy quy định một email mỗi sự kiện.

### Ví dụ ghi notification cùng nghiệp vụ

```java
@Service
public class OrderConfirmationService {

    private final OrderRepository orderRepository;
    private final MailNotificationRepository notificationRepository;

    public OrderConfirmationService(
            OrderRepository orderRepository,
            MailNotificationRepository notificationRepository
    ) {
        this.orderRepository = orderRepository;
        this.notificationRepository = notificationRepository;
    }

    @Transactional
    public UUID confirmOrder(UUID orderId) {
        Order order = orderRepository.findById(orderId).orElseThrow();
        order.confirm();

        UUID notificationId = UUID.randomUUID();
        notificationRepository.insertPending(
                notificationId,
                order.getId().toString(),
                "ORDER_CONFIRMED",
                order.getCustomerEmail(),
                "order-confirmation",
                createMailPayload(order)
        );

        return notificationId;
    }
}
```

`insertPending(...)` là repository method do ứng dụng triển khai. Trong thực tế cần giải quyết request/event lặp bằng atomic insert/upsert và đọc lại notification đã tồn tại. Không chỉ kiểm tra tồn tại rồi insert mà bỏ qua race condition.

## 11. Worker nên dùng transaction nào?

Một worker lấy notification đã commit, tạo email và gửi qua SMTP. Nên tách ba giai đoạn:

1. **Claim:** transaction ngắn A/B để nhận một notification và đánh dấu `PROCESSING`.
2. **Send:** I/O SMTP ngoài transaction DB.
3. **Record:** transaction ngắn khác để ghi `SUBMITTED`, `RETRY_WAIT`, `FAILED` hoặc `UNKNOWN`.

```text
Worker                    Database                       SMTP
  |                           |                            |
  |-- BEGIN TX claim -------->|                            |
  |-- lock + mark PROCESSING->|                            |
  |-- COMMIT claim ---------->|                            |
  |                           |                            |
  |-- render MIME ------------------------------------------|
  |-- send ------------------------------------------------>|
  |<----------------------------- accepted / rejected / ? --|
  |                           |                            |
  |-- BEGIN TX status ------->|                            |
  |-- mark outcome ---------->|                            |
  |-- COMMIT status --------->|                            |
```

Không giữ transaction claim mở trong thời gian SMTP trả lời. Nếu worker chết, cần có lease để xác định claim đã hết hạn và một chính sách phục hồi rõ ràng.

### Atomic claim với PostgreSQL

Một ví dụ dùng `FOR UPDATE SKIP LOCKED` trong một transaction ngắn:

```sql
BEGIN;

SELECT id
FROM mail_notification
WHERE status IN ('PENDING', 'RETRY_WAIT')
  AND (next_attempt_at IS NULL
       OR next_attempt_at <= CURRENT_TIMESTAMP)
ORDER BY created_at
FOR UPDATE SKIP LOCKED
LIMIT 10;

-- Đánh dấu chính các row đã chọn thành PROCESSING,
-- tạo claim_token/lease_until và lấy payload cần xử lý.
COMMIT;
```

Trong code production, thao tác select và update cần thực hiện **cùng transaction**, hoặc dùng câu lệnh claim nguyên tử tương đương. Worker chỉ xử lý các row nó đã claim thành công.

Nếu có nhiều instance, mỗi instance có thể claim những row khác nhau thay vì cùng gửi một email. Khi cập nhật trạng thái, cần dùng `claim_token` để ngăn worker cũ ghi đè kết quả sau khi lease đã chuyển.

## 12. Ví dụ phân tách thành các bean rõ transaction boundary

Ba bean minh họa:

```java
@Service
public class MailClaimService {

    private final MailNotificationRepository repository;

    public MailClaimService(MailNotificationRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public List<ClaimedMail> claimBatch(int batchSize) {
        return repository.claimPending(batchSize);
    }
}
```

```java
@Service
public class MailOutcomeService {

    private final MailNotificationRepository repository;

    public MailOutcomeService(MailNotificationRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void submitted(UUID id, UUID claimToken) {
        repository.markSubmittedIfClaimMatches(id, claimToken);
    }

    @Transactional
    public void failure(
            UUID id,
            UUID claimToken,
            MailFailureKind kind
    ) {
        repository.recordFailureIfClaimMatches(id, claimToken, kind);
    }
}
```

Bean worker:

```java
@Component
public class MailPollingWorker {

    private final MailClaimService claimService;
    private final MailOutcomeService outcomeService;
    private final MailComposer composer;
    private final JavaMailSender mailSender;

    public MailPollingWorker(
            MailClaimService claimService,
            MailOutcomeService outcomeService,
            MailComposer composer,
            JavaMailSender mailSender
    ) {
        this.claimService = claimService;
        this.outcomeService = outcomeService;
        this.composer = composer;
        this.mailSender = mailSender;
    }

    @Scheduled(fixedDelayString = "5000")
    public void poll() {
        List<ClaimedMail> batch = claimService.claimBatch(10);
        for (ClaimedMail item : batch) {
            sendOne(item);
        }
    }

    private void sendOne(ClaimedMail item) {
        try {
            MimeMessage mimeMessage = composer.compose(item);
            mailSender.send(mimeMessage); // Không nằm trong transaction DB claim.
            outcomeService.submitted(item.id(), item.claimToken());
        } catch (MailException ex) {
            outcomeService.failure(
                    item.id(),
                    item.claimToken(),
                    classifySendFailure(ex)
            );
        } catch (MessagingException ex) {
            outcomeService.failure(
                    item.id(),
                    item.claimToken(),
                    MailFailureKind.MESSAGE_BUILD_ERROR
            );
        }
    }
}
```

Các kiểu `ClaimedMail`, `MailComposer`, `MailFailureKind` và các repository methods là abstractions minh họa cho kiến trúc. `classifySendFailure` phải phân loại cẩn thận dựa trên giai đoạn SMTP và bằng chứng có sẵn, không mặc định mọi exception đều có thể retry an toàn.

**Vì sao tách bean?** Method `claimBatch()` và `submitted()` được gọi qua các Spring bean proxy, nên transaction annotation có ranh giới dễ quan sát. Worker không bị bọc bởi một `@Transactional` kéo dài qua lời gọi SMTP.

## 13. Một task có thể thất bại sau khi business transaction đã commit

Khi TX nghiệp vụ đã commit, task gửi mail có thể:

- Gặp lỗi template.
- Không đọc được attachment.
- Timeout SMTP.
- Bị SMTP từ chối vì sender/recipient.
- Bị executor từ chối do queue đầy.
- Bị process crash.

Những lỗi này **không làm rollback transaction nghiệp vụ đã commit**. Cần diễn đạt kết quả của ứng dụng đúng cách:

| Kết quả | Điều đã xảy ra | Hành vi phù hợp |
| --- | --- | --- |
| Business commit thành công, task chưa chạy | Nghiệp vụ đã lưu; mail đang chờ | Trả receipt/trạng thái `PENDING` |
| Business commit thành công, SMTP chấp nhận | Nghiệp vụ đã lưu; mail được nhận để chuyển tiếp | Ghi `SUBMITTED` |
| Business commit thành công, SMTP từ chối rõ | Nghiệp vụ vẫn lưu; mail lỗi | `RETRY_WAIT` hoặc `FAILED` theo loại lỗi |
| Business commit thành công, SMTP outcome chưa rõ | Không biết server đã nhận mail hay chưa | `UNKNOWN` và reconciliation |
| Business transaction rollback | Nghiệp vụ không commit | Không phát notification có hiệu lực |

Không trả thông báo “email đã giao thành công” ngay khi method `@Async` được gọi. Với API bất đồng bộ, `202 Accepted` thường phù hợp khi yêu cầu gửi **đã được ghi nhận bền vững**; trạng thái giao thư cần xem riêng.

## 14. SMTP không tham gia transaction của database

Gửi mail và ghi database là hai side effect thuộc hai hệ thống khác nhau. Không có transaction ACID chung cho một commit database và SMTP submission thông thường.

Xét tình huống:

```text
Worker               SMTP server                Database
  |                        |                         |
  |---- send message ----->|                         |
  |<--- 250 accepted ------|                         |
  |                        |                         |
  X crash trước khi ghi DB |                         |
  |                        |                  status=PROCESSING
```

Database chưa biết message đã được SMTP chấp nhận. Nếu restart rồi gửi lại ngay, người nhận có thể nhận trùng.

Ngược lại, nếu cập nhật `SUBMITTED` **trước** khi gửi SMTP và crash sau đó, hệ thống có thể không gửi email mà vẫn ghi đã gửi.

Vì vậy:

- `SUBMITTED` chỉ phản ánh kết quả SMTP/provider đã quan sát được, không bảo đảm giao tới Inbox.
- Khi kết quả mơ hồ, dùng trạng thái `UNKNOWN` và quy trình đối chiếu.
- Retry chỉ nên thực hiện tự động với lỗi đã phân loại phù hợp.
- Provider có API idempotency thì dùng theo hợp đồng của provider; SMTP thuần không có idempotency key chuẩn chung cho mọi server.

Outbox giúp không mất **yêu cầu gửi** sau commit, nhưng nó không biến SMTP thành exactly-once delivery.

## 15. Exception trong task không rollback caller

Ví dụ:

```java
@Transactional
public void updateAccount(Account account) {
    accountRepository.save(account);
    asyncMailService.sendWelcome(account.getEmail());
}
```

Nếu `sendWelcome` thật sự chạy async, caller thường đã tiếp tục mà không biết SMTP có lỗi hay không. Lỗi trong worker sau commit không thể làm transaction `updateAccount()` rollback.

Với method trả `void`, một `AsyncUncaughtExceptionHandler` có thể giúp quan sát lỗi:

```java
@Configuration
public class AsyncErrorConfig implements AsyncConfigurer {

    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (error, method, args) -> {
            // Log theo notification ID/correlation ID, không log PII.
        };
    }
}
```

Với method trả `CompletableFuture`, caller có thể đăng ký callback xử lý exception:

```java
CompletableFuture<Void> future =
        asyncMailService.sendWelcome(data);

future.whenComplete((result, error) -> {
    if (error != null) {
        // Ghi nhận lỗi hoặc kích hoạt quy trình xử lý.
    }
});
```

Nhưng `CompletableFuture` chỉ giữ kết quả trong memory của process; nó không thay thế notification record/outbox bền vững. Không chờ `future.join()` ngay trong HTTP request nếu mục tiêu là giảm thời gian phản hồi.

### Phân biệt hai loại exception

- **Dispatch exception:** executor không nhận task, có thể xuất hiện ở caller ngay khi submit.
- **Execution exception:** lỗi xảy ra trong quá trình worker chạy, thường được xử lý qua future/handler hoặc trạng thái notification.

Hai loại lỗi có thời điểm và ảnh hưởng transaction khác nhau. Nếu business đã commit rồi executor mới từ chối dispatch trong callback sau commit, không có rollback tự động; đây là lý do cần durable outbox cho email quan trọng.

## 16. Không truyền entity được quản lý giữa các thread

Một lỗi khác không phải do SMTP mà do JPA:

```java
@Transactional
public void confirmOrder(UUID orderId) {
    Order order = orderRepository.findById(orderId).orElseThrow();
    order.confirm();
    asyncMailService.sendConfirmation(order);
}
```

Trong worker:

```java
@Async("mailExecutor")
public void sendConfirmation(Order order) {
    String name = order.getCustomer().getDisplayName();
    // Quan hệ lazy có thể không còn persistence context hợp lệ.
}
```

Không nên truyền JPA entity còn gắn với persistence context của thread gọi sang worker. Rủi ro bao gồm:

- `LazyInitializationException` khi truy cập dữ liệu lazy.
- Worker nhìn thấy trạng thái object in-memory chưa được commit.
- Object mutable bị thay đổi trong lúc worker đọc.
- Hiểu nhầm rằng entity vẫn được quản lý bởi transaction của caller.

Hai lựa chọn rõ ràng hơn:

1. Tạo một **DTO bất biến** chứa các trường cần gửi khi làm việc với nghiệp vụ, rồi lưu DTO/snapshot vào outbox.
2. Truyền **ID** và để worker truy vấn lại trong transaction đọc riêng **sau khi dữ liệu đã commit**.

### Ví dụ DTO bất biến

```java
public record OrderConfirmedMailData(
        UUID orderId,
        String recipient,
        String recipientName,
        String orderCode,
        String amountLabel
) {}
```

DTO mô tả dữ liệu truyền qua ranh giới thread. Nếu dữ liệu có thể thay đổi sau khi commit, cần quyết định email phải phản ánh **snapshot tại thời điểm nghiệp vụ** hay **trạng thái mới nhất** khi worker chạy.

Ví dụ, email xác nhận giá tiền thường nên dùng snapshot đã commit phù hợp với sự kiện, thay vì đọc tổng tiền có thể đã thay đổi trong thời gian chờ.

## 17. Context propagation không phải transaction propagation

Một ứng dụng có thể cần mang qua worker:

- Correlation ID và MDC phục vụ log.
- Tenant ID.
- Locale và timezone.
- Trace/span context.
- Một số thông tin bảo mật đã được kiểm soát.

Các ngữ cảnh này có thể được truyền bằng DTO, `TaskDecorator` hoặc tích hợp context propagation phù hợp. Nhưng **không được nhầm việc truyền MDC/SecurityContext với việc truyền transaction**.

Ví dụ `TaskDecorator` cho MDC:

```java
public final class MailMdcTaskDecorator implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable task) {
        Map<String, String> captured = MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previous = MDC.getCopyOfContextMap();
            try {
                if (captured == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(captured);
                }
                task.run();
            } finally {
                if (previous == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(previous);
                }
            }
        };
    }
}
```

Đăng ký với executor:

```java
executor.setTaskDecorator(new MailMdcTaskDecorator());
```

Decorator này hỗ trợ correlation trong log; nó **không** chuyển transaction/JDBC connection từ HTTP thread sang mail worker.

Với email nghiệp vụ, không nên phụ thuộc vào request-scoped object hoặc SecurityContext còn sống trong thread khác. Kiểm tra quyền khi tạo notification và lưu các giá trị cần thiết; worker xử lý theo quyền đã xác định và theo policy riêng.

## 18. Cấu hình executor và thời điểm task bắt đầu

Executor riêng giúp giới hạn số task gửi đồng thời:

```java
@Configuration
@EnableAsync
public class MailAsyncConfig {

    @Bean("mailExecutor")
    public ThreadPoolTaskExecutor mailExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(6);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("mail-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy()
        );
        return executor;
    }
}
```

`@Async("mailExecutor")` chỉ định executor. Nhưng dù executor có queue, **không thể dựa vào thời gian chờ queue để bảo đảm transaction caller đã commit**. Nếu lúc đó executor rảnh, task có thể chạy ngay; nếu quá tải, task có thể chạy muộn hoặc bị từ chối.

Nếu queue đầy:

- `AbortPolicy` ném lỗi khi không nhận task.
- `CallerRunsPolicy` có thể chạy task ngay ở thread gọi, khiến request phải chờ và làm giả định “luôn chạy ở thread khác” không còn đúng khi quá tải.
- Các chính sách discard có thể làm mất email mà không được phát hiện.

Với notification quan trọng, lưu công việc vào database **trước** khi giao cho executor. Executor là công cụ thực thi, không phải nguồn dữ liệu đáng tin cậy để khôi phục task.

## 19. Khi có nhiều instance hoặc nhiều worker

Một database outbox có thể được nhiều worker cùng đọc. Nếu worker A và B cùng lấy một notification `PENDING` rồi gửi, email có thể bị gửi trùng.

Do đó cần:

- Claim nguyên tử bằng row lock/update có điều kiện.
- Lease để theo dõi quyền xử lý của worker.
- Claim token hoặc fencing token khi ghi kết quả.
- Không giữ DB lock qua SMTP I/O.
- Phân loại notification `PROCESSING` hết lease cẩn thận, vì có thể SMTP đã nhận message trước khi worker chết.

```text
Worker A -> claim notification N-123, token T1
Worker B -> không claim được N-123

Nếu A chết:
  lease hết hạn -> reconciliation / recovery policy
  worker mới có thể nhận token T2

Khi A còn sống nhưng chậm:
  update với T1 phải bị từ chối nếu token hiện tại đã là T2
```

Việc này giúp giảm tranh chấp trạng thái. Nó vẫn không giải quyết tuyệt đối chuyện SMTP có thể đã nhận message trước khi worker chết.

## 20. Thiết kế retry và idempotency trong async mail

Việc xử lý lại notification có thể xảy ra do:

- Client gửi lại HTTP request.
- Event broker giao lại message.
- Worker retry sau lỗi tạm thời.
- Process restart sau khi gửi mail nhưng chưa ghi status.

Để giảm duplicate:

1. Cấp một `notificationId` ổn định cho một sự kiện gửi.
2. Dùng unique constraint theo business event khi chính sách chỉ cho phép một notification/sự kiện.
3. Không tạo notification mới mỗi lần worker retry.
4. Dùng claim/lease để nhiều worker không gửi cùng lúc.
5. Lưu attempt và trạng thái gửi.
6. Với lỗi kết quả mơ hồ, xử lý `UNKNOWN` và reconciliation thay vì retry mù.

**Message-ID** trong MIME không phải idempotency key được mọi SMTP server dùng để chống gửi trùng. Nếu provider có API idempotency chính thức, hãy dùng notification key theo hợp đồng của provider.

### Phân biệt retry và resend

- **Retry:** thử xử lý lại notification cũ, thường vì lỗi kỹ thuật.
- **Resend:** một thao tác nghiệp vụ mới có chủ đích, ví dụ người dùng yêu cầu gửi lại hóa đơn.

Resend có thể tạo notification mới liên kết với notification gốc, nhưng không được bị đồng nhất với retry kỹ thuật.

## 21. Trạng thái notification nên thể hiện điều gì?

Một state machine tối thiểu:

```text
PENDING
   |
   v
PROCESSING
   |
   +-- accepted ----------> SUBMITTED
   |
   +-- retryable error ---> RETRY_WAIT ---> PROCESSING
   |
   +-- permanent error --> FAILED
   |
   +-- ambiguous result -> UNKNOWN
                              |
                              v
                         reconcile
```

| Trạng thái | Ý nghĩa |
| --- | --- |
| `PENDING` | Notification đã được commit, đang chờ worker |
| `PROCESSING` | Một worker đã claim và đang xử lý |
| `SUBMITTED` | SMTP/provider chấp nhận message theo kết quả quan sát được |
| `RETRY_WAIT` | Chờ thời điểm thử lại sau lỗi phù hợp |
| `FAILED` | Không gửi tiếp theo policy hoặc lỗi vĩnh viễn |
| `UNKNOWN` | Chưa xác định được SMTP/provider đã nhận message hay chưa |

Không đặt tên `SUBMITTED` thành `DELIVERED` nếu chỉ có kết quả `JavaMailSender.send(...)` thành công. Delivery, bounce hoặc spam filtering có thể xảy ra sau đó và được theo dõi bằng provider event nếu có.

## 22. Một ví dụ Spring Mail gửi message tách khỏi transaction DB

Mail composer chỉ dựng message; nó không cần bắt đầu DB transaction để gọi SMTP:

```java
@Component
public class MailComposer {

    private final JavaMailSender mailSender;

    public MailComposer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public MimeMessage compose(ClaimedMail item)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                true,
                StandardCharsets.UTF_8.name()
        );

        helper.setFrom("notifications@example.org");
        helper.setTo(item.recipient());
        helper.setSubject("Xác nhận đơn hàng " + item.orderCode());

        String plain = "Đơn hàng " + item.orderCode()
                + " đã được xác nhận.";
        String html = "<p>Đơn hàng <strong>"
                + escapeHtml(item.orderCode())
                + "</strong> đã được xác nhận.</p>";

        helper.setText(plain, html);
        return message;
    }
}
```

`escapeHtml(...)` trong ví dụ biểu thị chức năng HTML escaping do ứng dụng cung cấp. Trong ứng dụng thực tế, nên dùng template engine như Thymeleaf và `th:text` cho dữ liệu động. Địa chỉ From phải thuộc miền được provider cấp quyền gửi.

Một worker gọi composer và sender **sau khi đã claim notification**, nhưng bên ngoài transaction claim:

```java
ClaimedMail item = claimService.claimOne();
if (item != null) {
    MimeMessage message = composer.compose(item);
    mailSender.send(message);
    outcomeService.submitted(item.id(), item.claimToken());
}
```

Đoạn ngắn trên chỉ minh họa ranh giới; triển khai thật cần bắt lỗi render/SMTP, ghi trạng thái và xử lý kết quả mơ hồ. Không thêm `@Transactional` bao quanh cả khối chỉ để tiện cập nhật status.

## 23. Kiểm thử ranh giới transaction và task

Để xác nhận thiết kế, cần kiểm tra những tình huống chạy khác thứ tự và lỗi thực tế.

### Test A — Task bắt đầu trước commit

Tạo một transaction đang mở; cho worker chạy ngay và thử đọc dữ liệu mới. Kỳ vọng thiết kế không phụ thuộc vào việc worker thấy dữ liệu chưa commit. Nếu cần dữ liệu commit, dùng after-commit coordination hoặc outbox.

### Test B — Business rollback

Trong service nghiệp vụ, phát sinh exception làm TX rollback sau khi dự định gửi email.

**Kỳ vọng với outbox:** không có notification được commit và không có worker xử lý email cho sự kiện đã rollback.

### Test C — Business commit rồi application crash

Sau khi commit outbox, dừng process trước khi worker xử lý.

**Kỳ vọng:** notification vẫn ở database; khi worker khởi động lại, công việc có thể được claim và gửi theo policy.

### Test D — Email gửi xong nhưng cập nhật status thất bại

Mô phỏng SMTP chấp nhận message nhưng worker không ghi được `SUBMITTED`.

**Kỳ vọng:** hệ thống không kết luận chắc chắn email chưa gửi. Cần ghi nhận/recover kết quả `UNKNOWN` hoặc đối chiếu provider trước retry.

### Test E — Hai worker cùng chạy

Cho hai worker claim đồng thời một notification.

**Kỳ vọng:** chỉ một worker nhận claim hợp lệ tại một thời điểm; update status phải kiểm tra claim token.

### Test F — Self-invocation

Gọi một method `@Async` từ method khác trong cùng object thay vì qua Spring proxy.

**Kỳ vọng:** nhận biết annotation không được intercept theo cơ chế proxy mặc định; sửa kiến trúc bằng cách gọi qua bean riêng.

### Test G — AFTER_COMMIT không có transaction

Phát event khi không có transaction đang hoạt động và dùng `@TransactionalEventListener` với cấu hình mặc định.

**Kỳ vọng:** listener phụ thuộc transaction không được gọi; cần xác định rõ policy thay vì tưởng email sẽ luôn được gửi.

### Test H — Executor từ chối task

Làm đầy thread pool và queue rồi dispatch mail.

**Kỳ vọng:** có log/trạng thái lỗi hoặc outbox giữ công việc; không mất notification một cách im lặng.

## 24. Cách điều tra khi thấy “transaction vẫn còn” trong log

Đôi khi log khiến người phát triển tưởng task đang dùng cùng transaction vì:

- Cả hai thread đều in cùng business ID hoặc trace ID.
- Worker bắt đầu trong lúc caller chưa commit.
- Cả hai method đều có `@Transactional`.
- Có log “transaction active” ở worker.
- Entity trong memory vẫn chứa giá trị vừa thay đổi.

Không có dấu hiệu nào chứng minh hai thread đang dùng **cùng một database transaction**.

Khi điều tra, hãy ghi:

| Thông tin | Mục đích |
| --- | --- |
| Thread name/ID | Biết lời gọi chạy ở thread nào |
| Notification ID | Liên kết nghiệp vụ với worker |
| Transaction start/commit/rollback | Xác định thứ tự của caller và worker |
| Order/business ID | Liên kết dữ liệu |
| Time/attempt | Phân biệt lần xử lý |
| Worker claim token | Xác định quyền cập nhật trạng thái |
| Provider message ID | Đối chiếu SMTP/provider nếu có |

Trong ứng dụng dùng transaction manager kiểu imperative, `TransactionSynchronizationManager.isActualTransactionActive()` có thể cho biết thread hiện tại có transaction đang hoạt động theo thông tin Spring quản lý. Nhưng nếu hàm này trả `true` trong worker, điều đó chỉ cho biết **worker có transaction**, không chứng minh nó là transaction của caller.

Không dùng hàm kiểm tra trạng thái thread-local làm cơ chế đồng bộ thay cho outbox/after-commit logic.

## 25. So sánh các cách triển khai

| Cách triển khai | Có chạy sau commit chắc chắn? | Công việc bền vững qua crash? | Phù hợp |
| --- | --- | --- | --- |
| Gọi `@Async` trực tiếp trong `@Transactional` | Không | Không, nếu chỉ ở executor memory | Không nên dùng cho email phụ thuộc commit |
| `@TransactionalEventListener(AFTER_COMMIT)` rồi gọi `@Async` | Có, khi event gắn với transaction và listener được gọi | Không tự bảo đảm | Thông báo ít quan trọng, chấp nhận mất task |
| Ghi notification trong business transaction, worker polling | Worker chỉ thấy row đã commit theo cơ chế đọc DB phù hợp | Có, nếu database bền vững | Email giao dịch cần độ tin cậy |
| Transactional outbox + message broker | Có, nếu publisher chỉ lấy outbox đã commit | Theo cấu hình lưu trữ/broker | Hệ thống nhiều service, throughput lớn |
| Gửi SMTP ngay trong method `@Transactional` | Không tách khỏi request; SMTP không rollback theo DB | Không giải quyết atomicity | Chỉ dùng khi chấp nhận giới hạn rõ ràng |

**Quy tắc lựa chọn:** ranh giới transaction được quyết định bởi yêu cầu nhất quán của nghiệp vụ; ranh giới task được quyết định bởi latency, concurrency và durability. Đừng dùng `@Async` để giải quyết yêu cầu mà thật ra cần outbox.

## 26. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Worker không tìm thấy order vừa insert | TX caller chưa commit | Đợi sau commit hoặc đọc notification từ outbox |
| Email được gửi dù nghiệp vụ rollback | Task được dispatch trước commit | Ghi yêu cầu gửi trong cùng transaction DB |
| `@Async` chạy đồng bộ | Self-invocation hoặc chưa bật async | Gọi qua proxy/bean riêng, cấu hình `@EnableAsync` |
| Worker có transaction nhưng đọc dữ liệu cũ | TX riêng với thời điểm/isolation khác | Rà soát commit timing và dữ liệu đầu vào |
| Lỗi mail không làm API rollback | Task lỗi sau khi business commit | Ghi trạng thái riêng, retry/reconcile |
| Listener AFTER_COMMIT không chạy | Event phát ngoài transaction hoặc listener/config chưa phù hợp | Xác định transaction-bound event và fallback policy |
| Database write trong AFTER_COMMIT không được persist như mong đợi | Dùng tài nguyên transaction vừa commit mà không có transaction mới | Gọi service `REQUIRES_NEW` hoặc dùng outbox |
| Mail mất sau restart | Công việc chỉ nằm trong executor memory | Persistent notification/outbox/broker |
| Nhiều worker gửi trùng | Claim không nguyên tử hoặc lease không được xử lý đúng | Row lock/atomic claim, fencing token, idempotency |
| SMTP timeout rồi gửi trùng | Retry mù trong tình huống outcome mơ hồ | `UNKNOWN` và provider reconciliation |
| DB lock giữ lâu | Bao SMTP I/O trong `@Transactional` | Tách claim/send/status thành các bước |
| API báo SENT ngay sau submit task | Nhầm acceptance của executor với SMTP submission | Trả `PENDING` và theo dõi kết quả |
| Task đọc JPA lazy relation lỗi | Entity/persistence context không còn phù hợp | Truyền DTO snapshot hoặc truy vấn lại sau commit |
| Tracing giống nhau nên tưởng cùng TX | Correlation ID được propagate | Phân biệt trace context và transaction context |

## 27. Tình huống tự luyện

### Tình huống 1 — Email welcome từ service tạo tài khoản

`createAccount()` được đánh dấu `@Transactional`. Ngay sau khi gọi `repository.save(account)`, service gọi `@Async sendWelcome(account.getId())`. Đôi khi worker không thấy tài khoản vừa tạo.

**Giải thích:** worker truy vấn bằng transaction/connection riêng trước khi TX tạo tài khoản commit. Không có bảo đảm worker sẽ thấy dữ liệu chưa commit.

**Hướng xử lý:** dùng event after-commit nếu chấp nhận mất task, hoặc lưu welcome notification/outbox trong cùng transaction để worker xử lý sau commit.

### Tình huống 2 — SMTP báo thành công rồi database rollback

`confirmOrder()` gọi gửi mail đồng bộ bên trong transaction, sau đó một lệnh database thất bại. Mail server đã nhận email nhưng TX rollback.

**Giải thích:** SMTP không tham gia transaction database. Rollback không thu hồi message.

**Hướng xử lý:** ghi request gửi vào outbox trong TX nghiệp vụ và gửi sau commit.

### Tình huống 3 — Thêm @Transactional vào sendAsync()

Người phát triển thêm `@Transactional` vào method `@Async` và nghĩ rằng worker sẽ dùng transaction của request.

**Giải thích:** task thực thi trên thread riêng; transaction annotation được áp dụng trong worker sẽ tạo/quản lý transaction riêng, không “tiếp tục” caller TX.

**Hướng xử lý:** quyết định transaction worker cần làm gì (đọc/ghi DB), nhưng không dùng nó để thay thế after-commit/outbox coordination.

### Tình huống 4 — Dùng AFTER_COMMIT nhưng vẫn mất mail

Database commit thành công. Process crash ngay trước khi listener dispatch task.

**Giải thích:** application event và executor không tự tạo persistent record.

**Hướng xử lý:** transactional outbox với notification `PENDING` đã commit.

### Tình huống 5 — Gửi lại sau SMTP timeout

Worker đã gửi message nhưng mất kết nối trước khi nhận response SMTP cuối. Worker không biết server có nhận hay chưa.

**Giải thích:** kết quả vận chuyển có thể mơ hồ, không liên quan đến transaction DB của caller.

**Hướng xử lý:** ghi `UNKNOWN`, đối chiếu provider nếu có, rồi áp dụng retry policy cân nhắc nguy cơ duplicate.

### Tình huống 6 — Ba instance cùng chạy mail scheduler

Mỗi instance đọc những notification `PENDING` từ cùng database và gửi.

**Giải thích:** có nhiều worker độc lập; transaction riêng của mỗi worker không tự chống trùng nếu cùng đọc một row.

**Hướng xử lý:** atomic claim với row lock/unique status transition và claim token, không giữ transaction mở khi gửi SMTP.

## 28. Nguyên tắc cần nhớ

1. **Transaction thuộc phạm vi thực thi được quản lý, không thuộc “ý tưởng nghiệp vụ” một cách tự động.**
2. **`@Async` không đợi commit và không thừa hưởng transaction imperative của caller.**
3. **`@Transactional` trên worker tạo phạm vi giao dịch riêng; `REQUIRES_NEW` cũng không kéo TX cũ qua thread.**
4. **SMTP không rollback cùng database.** Gửi email trong transaction không tạo atomicity xuyên hệ thống.
5. **Tách claim, send và status update.** Giữ transaction DB ngắn, không bao bọc network I/O lâu.
6. **Dùng `AFTER_COMMIT` khi cần đúng thời điểm và chấp nhận giới hạn memory event.**
7. **Dùng transactional outbox khi không được mất yêu cầu gửi sau commit.**
8. **Không truyền JPA entity hoặc transaction context qua worker;** ưu tiên DTO snapshot hoặc ID và transaction đọc riêng.
9. **Ghi trạng thái trung thực:** `PENDING` khác `SUBMITTED`, `SUBMITTED` khác `DELIVERED`, và timeout có thể là `UNKNOWN`.
10. **Thử các lịch chạy và điểm lỗi khác nhau** để tránh phụ thuộc vào timing may mắn.

## 29. Kết luận

Khi gửi email được tách sang tác vụ bất đồng bộ, transaction ở thread nghiệp vụ **không kéo dài qua task**. Worker có vòng đời thực thi và transaction database riêng; nó có thể bắt đầu trước khi caller commit. Vì thế, chỉ thêm `@Async` hoặc `@Transactional` không đủ để bảo đảm email được gửi sau commit và không bị mất.

Đối với thông báo ít quan trọng, `@TransactionalEventListener(AFTER_COMMIT)` kết hợp một service `@Async` có thể là giải pháp gọn nếu chấp nhận rủi ro task trong memory. Đối với email gắn với nghiệp vụ quan trọng, hãy ghi notification/outbox trong cùng transaction với thay đổi dữ liệu, rồi để worker đọc những công việc đã commit. Worker claim trong transaction ngắn, gửi SMTP ngoài transaction và ghi kết quả trong transaction khác. Thiết kế này làm rõ ranh giới commit, tránh hiểu nhầm transaction bắc cầu qua thread và giúp hệ thống có thể phục hồi, retry và điều tra lỗi gửi email một cách có kiểm soát.
