# Đọc outbox và gửi mail ngoài transaction chính

## 1. Vì sao cần đọc outbox để gửi email?

Trong ứng dụng Spring, một thao tác nghiệp vụ thường vừa cập nhật database vừa cần gửi email. Ví dụ:

- Đơn hàng chuyển sang trạng thái **SHIPPED**, người mua cần nhận mã theo dõi.
- Thanh toán được xác nhận, khách hàng cần nhận biên nhận.
- Tài khoản được kích hoạt, người dùng cần nhận thông báo.
- Yêu cầu hoàn tiền được tiếp nhận, khách hàng cần biết tiến độ.

Nếu gửi email trực tiếp bên trong transaction nghiệp vụ, thời gian transaction sẽ phụ thuộc vào mạng SMTP. Khi SMTP chậm hoặc mất kết nối, transaction database có thể phải mở lâu hơn, giữ lock lâu hơn và làm giảm khả năng xử lý đồng thời.

Một cách tổ chức phù hợp hơn là **transactional outbox**:

1. Trong transaction nghiệp vụ, cập nhật dữ liệu và ghi một bản ghi outbox mô tả email cần gửi.
2. Commit transaction database.
3. Một worker độc lập đọc các bản ghi outbox đến hạn.
4. Worker nhận quyền xử lý một bản ghi, commit việc claim.
5. Worker tạo và gửi email qua **JavaMailSender** ngoài transaction database chính.
6. Sau khi gửi hoặc gặp lỗi, worker mở transaction riêng để cập nhật kết quả xử lý.

Luồng tổng quát:

~~~text
Request / Business event
          |
          v
   Business transaction
      |           |
      |           +--> INSERT notification_outbox
      |
      +--> UPDATE business data
          |
        COMMIT
          |
          v
    Outbox polling worker
          |
          v
     Claim due records
          |
        COMMIT
          |
          v
   Render + JavaMailSender
      (không giữ transaction DB)
          |
          v
   SMTP/provider response
          |
          v
  Result transaction riêng
          |
          v
  SUBMITTED / RETRY / FAILED / UNKNOWN
~~~

Outbox giải quyết việc **lưu ý định gửi email một cách nguyên tử với thay đổi nghiệp vụ**. Worker tách thời gian gửi mail khỏi transaction cập nhật trạng thái chính.

## 2. Vấn đề khi gọi SMTP bên trong transaction chính

Ví dụ cách làm dễ gặp:

~~~java
@Transactional
public void markOrderShipped(String orderId, ShipmentInfo shipment) {
    Order order = orderRepository.findById(orderId)
            .orElseThrow();

    order.markShipped(shipment);
    orderRepository.save(order);

    mailService.sendShippedEmail(order, shipment);
}
~~~

Trong đoạn code này, transaction database vẫn mở trong lúc sendShippedEmail kết nối SMTP và truyền thông điệp.

Các vấn đề có thể xảy ra:

- **Transaction kéo dài:** thời gian SMTP không ổn định, có thể từ vài mili giây đến vài giây hoặc lâu hơn.
- **Giữ lock lâu:** các transaction khác phải chờ nếu cần cập nhật cùng bản ghi.
- **Rollback không đồng bộ:** SMTP có thể đã chấp nhận email nhưng database rollback sau đó. Người nhận nhận email “đã gửi hàng” trong khi trạng thái đơn vẫn chưa được commit.
- **Mất thông báo:** database commit thành công nhưng SMTP lỗi; trạng thái đã thay đổi mà email chưa được gửi.
- **Khó retry:** nếu toàn bộ phương thức rollback, ứng dụng không có bản ghi bền vững mô tả email cần gửi.
- **Khó điều tiết tải:** một đợt cập nhật nghiệp vụ lớn có thể đồng thời tạo ra nhiều kết nối SMTP.

SMTP không tham gia transaction database. Không thể giả định **@Transactional** sẽ rollback email đã được SMTP chấp nhận.

### Tách transaction không có nghĩa bỏ tính nhất quán

Nếu chỉ cập nhật database rồi gọi email ở một thread khác, vẫn có một khoảng hở: process có thể dừng sau khi database commit nhưng trước khi task gửi được lưu bền vững. Outbox giải quyết khoảng hở đó bằng cách ghi ý định gửi vào database trong **cùng transaction** với thay đổi nghiệp vụ.

## 3. Transactional outbox là gì?

Transactional outbox là một bảng hoặc cấu trúc lưu trữ trong database, ghi lại các sự kiện hoặc notification cần được chuyển tới hệ thống bên ngoài. Với email, mỗi bản ghi có thể đại diện cho một thông báo cần gửi.

Ví dụ bảng **notification_outbox**:

| Cột | Ý nghĩa |
|---|---|
| **id** | Khóa chính của bản ghi |
| **event_id** | Định danh duy nhất của sự kiện nguồn |
| **event_type** | Loại sự kiện, ví dụ ORDER_SHIPPED |
| **aggregate_id** | ID đơn hàng/tài khoản liên quan |
| **payload** | Snapshot dữ liệu cần để tạo email |
| **recipient** | Người nhận hoặc tham chiếu tới người nhận |
| **template_key** | Template cần render |
| **locale** | Ngôn ngữ của nội dung |
| **status** | PENDING, PROCESSING, RETRY, SUBMITTED, FAILED... |
| **attempts** | Số lần worker đã claim/thử gửi |
| **next_attempt_at** | Thời điểm được phép thử lại |
| **locked_by** | Worker đang giữ quyền xử lý |
| **claim_token** | Token xác nhận quyền sở hữu lần claim |
| **locked_until** | Hạn lease của lần claim |
| **last_error** | Mô tả lỗi đã được làm sạch |
| **created_at** | Thời điểm tạo outbox |
| **updated_at** | Thời điểm cập nhật gần nhất |
| **submitted_at** | Thời điểm SMTP/provider chấp nhận, nếu biết |

Một DDL minh họa theo PostgreSQL:

~~~sql
CREATE TABLE notification_outbox (
    id                UUID PRIMARY KEY,
    event_id          UUID NOT NULL,
    event_type        VARCHAR(100) NOT NULL,
    aggregate_id      VARCHAR(150) NOT NULL,
    recipient         VARCHAR(320) NOT NULL,
    template_key      VARCHAR(150) NOT NULL,
    locale            VARCHAR(20) NOT NULL,
    payload           JSONB NOT NULL,
    status            VARCHAR(30) NOT NULL,
    attempts          INTEGER NOT NULL DEFAULT 0,
    next_attempt_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    locked_by         VARCHAR(150),
    claim_token       UUID,
    locked_until      TIMESTAMPTZ,
    last_error        TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    submitted_at      TIMESTAMPTZ,
    CONSTRAINT uq_notification_outbox_event UNIQUE (event_id)
);

CREATE INDEX ix_notification_outbox_due
    ON notification_outbox (status, next_attempt_at, created_at);
~~~

Đây là schema khởi đầu để minh họa. Ứng dụng có thể dùng tên cột, kiểu JSON, index hoặc trạng thái khác theo database và quy mô thực tế. Nếu một event tạo nhiều notification cho các audience khác nhau, khóa duy nhất nên dựa trên một notification key phù hợp, chẳng hạn event ID + notification type + audience, thay vì chỉ event ID.

## 4. Ghi outbox trong cùng transaction nghiệp vụ

Nguyên tắc cốt lõi:

**Thay đổi dữ liệu nghiệp vụ và bản ghi outbox phải commit hoặc rollback cùng nhau.**

Ví dụ, khi đơn hàng được bàn giao cho đơn vị vận chuyển:

~~~java
public record OrderShippedPayload(
        String orderId,
        String orderCode,
        String customerName,
        String recipientEmail,
        String trackingNumber,
        String trackingUrl,
        Instant shippedAt
) {
}
~~~

Application service:

~~~java
@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final NotificationOutboxRepository outboxRepository;

    public OrderApplicationService(
            OrderRepository orderRepository,
            NotificationOutboxRepository outboxRepository
    ) {
        this.orderRepository = orderRepository;
        this.outboxRepository = outboxRepository;
    }

    @Transactional
    public void shipOrder(String orderId, ShipmentInfo shipment) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));

        order.markShipped(shipment);
        orderRepository.save(order);

        OrderShippedPayload payload = new OrderShippedPayload(
                order.getId(),
                order.getCode(),
                order.getCustomerName(),
                order.getCustomerEmail(),
                shipment.trackingNumber(),
                shipment.trackingUrl(),
                Instant.now()
        );

        outboxRepository.insert(
                UUID.randomUUID(),
                UUID.randomUUID(),
                "ORDER_SHIPPED",
                order.getId(),
                payload
        );
    }
}
~~~

Các repository và kiểu Order, ShipmentInfo là thành phần do ứng dụng định nghĩa. Ví dụ cho thấy cả orderRepository.save(...) và outboxRepository.insert(...) tham gia cùng transaction Spring.

Kết quả:

- Nếu transition hoặc insert outbox thất bại, transaction rollback; không có đơn hàng đã gửi đi mà thiếu ý định thông báo.
- Nếu commit thành công, cả thay đổi đơn hàng và outbox record đều tồn tại để worker xử lý.
- Nếu SMTP ngừng hoạt động, outbox vẫn còn và worker có thể thử lại theo chính sách.

Trong ứng dụng thực, event ID nên được tạo ổn định từ sự kiện đã được xác thực hoặc có unique constraint để chống xử lý trùng. Không tạo một outbox record mới mỗi lần webhook giống nhau được gửi lại.

### Vì sao không gọi mailService.send() ở đây?

Phương thức nghiệp vụ chỉ lưu dữ liệu và ý định gửi. Nó không cần mở kết nối SMTP, serialize MIME hoặc chờ server bên ngoài. Nhờ vậy transaction chính ngắn và có thể rollback nguyên tử trên database.

## 5. Payload nên lưu những gì?

Worker thường chạy sau thời điểm event xảy ra. Nếu payload chỉ chứa orderId, worker có thể đọc trạng thái mới nhất rồi tạo email không còn khớp với sự kiện cũ.

Ví dụ:

1. Đơn hàng chuyển PAID sang SHIPPED; outbox được ghi.
2. Email bị trì hoãn vì SMTP đang lỗi.
3. Đơn hàng chuyển tiếp sang DELIVERED.
4. Worker đọc orderId, truy vấn trạng thái hiện tại và chỉ thấy DELIVERED.
5. Worker gửi nội dung giao hàng trong khi bản ghi outbox ban đầu đại diện cho sự kiện đã gửi đi.

Để tránh điều đó, payload nên giữ **snapshot tối thiểu cần thiết tại thời điểm event xảy ra**, chẳng hạn:

- Event type và event ID.
- Aggregate ID và version.
- Trạng thái trước/sau nếu cần.
- Tên hiển thị, mã đơn và các dữ liệu được phép đưa vào email.
- Recipient hoặc recipient reference đã được xác thực.
- Tracking number, URL nghiệp vụ hoặc thông tin giao dịch cần thiết.
- Template key và locale.

Không nhất thiết lưu toàn bộ entity. Chỉ giữ các trường cần cho notification, hoặc giữ ID cùng version/snapshot có thể truy xuất nhất quán. Payload càng lớn và càng chứa dữ liệu cá nhân thì càng cần chính sách mã hóa, quyền đọc và thời hạn lưu trữ.

### Snapshot hay truy vấn lại?

| Cách | Khi phù hợp | Rủi ro cần xử lý |
|---|---|---|
| Snapshot đầy đủ các trường cần render | Email phải phản ánh đúng thời điểm event | Payload có thể chứa PII và cần retention |
| Chỉ lưu ID rồi truy vấn lại | Dữ liệu không đổi hoặc cần thông tin mới nhất theo chính sách | Nội dung có thể lệch khỏi event ban đầu |
| Lưu ID và version/snapshot reference | Dữ liệu lớn, cần truy xuất phiên bản | Cần kho dữ liệu hỗ trợ version và giữ phiên bản đủ lâu |

Đối với email xác nhận sự kiện, snapshot thường dễ đảm bảo tính nhất quán hơn. Đối với email nhắc nhở trạng thái hiện tại, truy vấn mới nhất có thể đúng mục đích hơn. Hãy quyết định theo ý nghĩa nghiệp vụ, không theo sự tiện lợi của repository.

## 6. Worker đọc các bản ghi outbox đến hạn

Worker định kỳ tìm những record có thể xử lý, ví dụ:

- PENDING và đã đến thời điểm xử lý.
- RETRY với next_attempt_at đã đến.
- PROCESSING nhưng lease đã hết hạn vì worker trước có thể đã dừng bất thường.

Không nên tải toàn bộ bảng outbox vào bộ nhớ rồi lọc bằng Java. Dùng query có điều kiện, sắp xếp và giới hạn batch.

Một truy vấn chọn ứng viên có thể có dạng:

~~~sql
SELECT id
FROM notification_outbox
WHERE
      (status = 'PENDING' AND next_attempt_at <= CURRENT_TIMESTAMP)
   OR (status = 'RETRY' AND next_attempt_at <= CURRENT_TIMESTAMP)
   OR (status = 'PROCESSING' AND locked_until < CURRENT_TIMESTAMP)
ORDER BY next_attempt_at, created_at
LIMIT 25;
~~~

Truy vấn này chỉ minh họa tiêu chí chọn record. Nếu nhiều worker cùng chạy, chỉ SELECT như vậy **không đủ để phân phối độc quyền**: hai worker có thể đọc cùng một ID trước khi bên nào cập nhật trạng thái.

Cần có bước claim nguyên tử hoặc cơ chế khóa/lease để chỉ một worker sở hữu một lần xử lý tại một thời điểm.

## 7. Claim record rồi commit trước khi gửi mail

Một chiến lược phổ biến với database hỗ trợ **FOR UPDATE SKIP LOCKED**:

1. Mở transaction ngắn.
2. Chọn một batch record đến hạn bằng SELECT ... FOR UPDATE SKIP LOCKED.
3. Đổi chúng sang PROCESSING, tăng attempt, đặt locked_by, claim_token và locked_until.
4. Trả các record đã claim ra khỏi phương thức.
5. Transaction claim commit khi phương thức kết thúc.
6. Worker bắt đầu render và gửi email sau khi transaction claim đã commit.

SKIP LOCKED cho phép worker khác bỏ qua các dòng đang bị worker hiện tại khóa và lấy dòng khác. Đây là cách thường dùng để xây dựng hàng đợi polling trên PostgreSQL và một số hệ quản trị khác; cú pháp và mức hỗ trợ cần điều chỉnh theo database thực tế.

Sơ đồ:

~~~text
Worker A                         Worker B
   |                                |
   v                                v
BEGIN claim                     BEGIN claim
   |                                |
SELECT ... FOR UPDATE           SELECT ... SKIP LOCKED
   |                                |
claim row 101                    skip row 101
   |                             claim row 102
UPDATE row 101                      |
   |                             UPDATE row 102
COMMIT                              |
   |                             COMMIT
   v                                v
Send email 101                  Send email 102
~~~

### Ví dụ SQL theo PostgreSQL

Một transaction có thể chọn batch:

~~~sql
SELECT id, event_type, aggregate_id, recipient, template_key,
       locale, payload, attempts
FROM notification_outbox
WHERE
      (status IN ('PENDING', 'RETRY')
       AND next_attempt_at <= CURRENT_TIMESTAMP)
   OR (status = 'PROCESSING'
       AND locked_until < CURRENT_TIMESTAMP)
ORDER BY next_attempt_at, created_at
FOR UPDATE SKIP LOCKED
LIMIT 25;
~~~

Sau khi chọn, cập nhật từng dòng trong cùng transaction:

~~~sql
UPDATE notification_outbox
SET status = 'PROCESSING',
    attempts = attempts + 1,
    locked_by = :workerId,
    claim_token = :claimToken,
    locked_until = :lockedUntil,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :id;
~~~

claimToken nên là UUID mới cho từng lần claim. Khi transaction commit, lock database được nhả nhưng lease và token vẫn ghi lại quyền xử lý tạm thời. Worker chỉ được cập nhật kết quả nếu token còn khớp.

**Không giữ transaction chứa FOR UPDATE trong suốt lúc gửi email.** Transaction claim phải kết thúc trước khi worker gọi SMTP.

## 8. Ví dụ Claim service với Spring transaction

Có thể dùng JdbcTemplate để triển khai query khóa theo cú pháp của database. Phần dưới là skeleton minh họa:

~~~java
public record ClaimedNotification(
        UUID id,
        UUID claimToken,
        String eventType,
        String aggregateId,
        String recipient,
        String templateKey,
        String locale,
        String payload,
        int attempts
) {
}
~~~

Claim service:

~~~java
@Service
public class OutboxClaimService {

    private final JdbcTemplate jdbcTemplate;
    private final String workerId;

    public OutboxClaimService(
            JdbcTemplate jdbcTemplate,
            WorkerIdentity workerIdentity
    ) {
        this.jdbcTemplate = jdbcTemplate;
        this.workerId = workerIdentity.id();
    }

    @Transactional
    public List<ClaimedNotification> claimBatch(int batchSize) {
        List<OutboxCandidate> candidates = jdbcTemplate.query(
                """
                SELECT id, event_type, aggregate_id, recipient,
                       template_key, locale, payload, attempts
                FROM notification_outbox
                WHERE
                      (status IN ('PENDING', 'RETRY')
                       AND next_attempt_at <= CURRENT_TIMESTAMP)
                   OR (status = 'PROCESSING'
                       AND locked_until < CURRENT_TIMESTAMP)
                ORDER BY next_attempt_at, created_at
                FOR UPDATE SKIP LOCKED
                LIMIT ?
                """,
                outboxCandidateRowMapper(),
                batchSize
        );

        List<ClaimedNotification> claimed = new ArrayList<>();

        for (OutboxCandidate candidate : candidates) {
            UUID token = UUID.randomUUID();
            Instant leaseUntil = Instant.now().plus(Duration.ofMinutes(3));

            jdbcTemplate.update(
                    """
                    UPDATE notification_outbox
                    SET status = 'PROCESSING',
                        attempts = attempts + 1,
                        locked_by = ?,
                        claim_token = ?,
                        locked_until = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    workerId,
                    token,
                    Timestamp.from(leaseUntil),
                    candidate.id()
            );

            claimed.add(candidate.toClaimed(token));
        }

        return List.copyOf(claimed);
    }
}
~~~

OutboxCandidate, outboxCandidateRowMapper() và WorkerIdentity là các thành phần ứng dụng cần triển khai. Ví dụ dùng Instant để biểu diễn lease, còn database lưu timestamp. Với hệ thống có nhiều máy và đồng hồ có thể lệch, nên tính thời gian lease dựa trên đồng hồ database hoặc đồng bộ thời gian đáng tin cậy.

Đoạn SQL là kiểu PostgreSQL; LIMIT/FOR UPDATE SKIP LOCKED, kiểu JSON và binding tham số có thể khác theo hệ quản trị. Cần dùng cú pháp tương ứng và kiểm tra query plan/index khi triển khai.

### Vì sao phương thức claim nằm trong bean riêng?

Worker gọi claimService.claimBatch(...). Khi lời gọi đi qua Spring proxy, transaction được mở trước khi method chạy và commit khi method trả về. Worker nhận danh sách sau khi transaction claim hoàn tất, rồi mới xử lý SMTP.

Nếu gọi một phương thức @Transactional khác bằng this.claimBatch() trong cùng object, Spring proxy có thể không được kích hoạt theo cơ chế proxy mặc định. Tách claim service thành bean riêng làm ranh giới transaction rõ ràng.

## 9. Gửi mail sau khi claim transaction đã kết thúc

Worker điều phối việc claim và gửi:

~~~java
@Component
public class OutboxMailWorker {

    private final OutboxClaimService claimService;
    private final OutboxMailProcessor processor;

    public OutboxMailWorker(
            OutboxClaimService claimService,
            OutboxMailProcessor processor
    ) {
        this.claimService = claimService;
        this.processor = processor;
    }

    @Scheduled(fixedDelay = 2000)
    public void poll() {
        List<ClaimedNotification> batch =
                claimService.claimBatch(25);

        for (ClaimedNotification notification : batch) {
            processor.process(notification);
        }
    }
}
~~~

Worker không cần @Transactional. claimBatch(...) đã kết thúc transaction trước khi trả về; mỗi processor.process(...) gọi mail sender ngoài transaction claim và ngoài transaction nghiệp vụ ban đầu.

Nếu xử lý batch tuần tự, một email chậm sẽ làm chậm các email còn lại trong batch. Có thể tăng số worker hoặc dùng executor có giới hạn, nhưng cần kiểm soát concurrency để không vượt connection limit và quota của SMTP provider.

## 10. Tạo MIME và gửi bằng JavaMailSender

Processor nhận một bản ghi đã claim, giải mã payload, chọn template và gửi:

~~~java
@Service
public class OutboxMailProcessor {

    private final EmailTemplateRenderer renderer;
    private final JavaMailSender mailSender;
    private final OutboxResultService resultService;
    private final OutboxFailureService failureService;

    public OutboxMailProcessor(
            EmailTemplateRenderer renderer,
            JavaMailSender mailSender,
            OutboxResultService resultService,
            OutboxFailureService failureService
    ) {
        this.renderer = renderer;
        this.mailSender = mailSender;
        this.resultService = resultService;
        this.failureService = failureService;
    }

    public void process(ClaimedNotification notification) {
        try {
            RenderedEmail content = renderer.render(notification);

            MimeMessage message = mailSender.createMimeMessage();
            MimeMessageHelper helper = new MimeMessageHelper(
                    message,
                    true,
                    StandardCharsets.UTF_8.name()
            );

            helper.setFrom("notifications@example.com");
            helper.setTo(notification.recipient());
            helper.setSubject(content.subject());
            helper.setText(content.plainText(), content.htmlText());

            mailSender.send(message);

            resultService.markSubmitted(
                    notification.id(),
                    notification.claimToken()
            );
        } catch (Exception exception) {
            failureService.recordFailure(
                    notification,
                    exception
            );
        }
    }
}
~~~

RenderedEmail, EmailTemplateRenderer, OutboxResultService và OutboxFailureService là abstraction của ứng dụng. Ví dụ dùng một địa chỉ From cố định để minh họa; hệ thống thật cần cấu hình sender hợp lệ. Trong triển khai thực tế, nên phân loại exception cụ thể thay vì bắt mọi Exception rồi áp dụng cùng một chính sách retry.

Điểm cần chú ý: method process(...) không có @Transactional. Việc tạo MIME và gọi mailSender.send(...) không giữ transaction database mở. Hai service cập nhật trạng thái kết quả được gọi riêng và có transaction ngắn của chúng.

## 11. Cập nhật kết quả trong transaction riêng

Sau khi SMTP/provider chấp nhận message, worker cập nhật outbox:

~~~java
@Service
public class OutboxResultService {

    private final JdbcTemplate jdbcTemplate;

    public OutboxResultService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void markSubmitted(UUID id, UUID claimToken) {
        int updated = jdbcTemplate.update(
                """
                UPDATE notification_outbox
                SET status = 'SUBMITTED',
                    submitted_at = CURRENT_TIMESTAMP,
                    locked_by = NULL,
                    claim_token = NULL,
                    locked_until = NULL,
                    last_error = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                  AND status = 'PROCESSING'
                  AND claim_token = ?
                """,
                id,
                claimToken
        );

        if (updated != 1) {
            throw new IllegalStateException(
                    "Outbox claim is no longer owned by this worker"
            );
        }
    }
}
~~~

REQUIRES_NEW tạo transaction độc lập cho thao tác cập nhật kết quả nếu có transaction đang tồn tại. Vì processor không mở transaction ngoài, nó tạo một transaction ngắn rồi commit.

Điều kiện claim_token = ? rất quan trọng. Nếu lease hết hạn và worker khác đã claim lại record, token cũ không còn hợp lệ. Worker cũ không được ghi đè kết quả của worker mới.

Nếu update trả về 0 dòng, cần ghi nhận tình huống claim đã mất quyền và điều tra. Không nên bỏ qua âm thầm vì điều đó có thể che giấu race condition hoặc lease quá ngắn.

### SUBMITTED không có nghĩa đã vào Inbox

Tên SUBMITTED biểu thị ứng dụng đã nhận kết quả thành công ở chặng gửi tới SMTP/provider. Nó không chứng minh thư đã được mailbox nhận, không vào Spam và đã được người dùng đọc. Nếu provider có webhook/event delivery, có thể lưu thêm trạng thái chuyển phát riêng.

## 12. Xử lý lỗi và retry

Nếu tạo template, tạo MIME hoặc gửi SMTP thất bại, worker cần ghi kết quả vào outbox trong transaction riêng. Không để exception làm mất bản ghi pending.

Một số nhóm lỗi:

| Nhóm lỗi | Ví dụ | Chính sách thường dùng |
|---|---|---|
| Lỗi dữ liệu | Payload thiếu trường, template key không tồn tại | Đưa vào FAILED hoặc dead-letter để xử lý thủ công |
| Lỗi cấu hình | SMTP credential sai, sender không được phép | Báo động, dừng retry nhanh hoặc giới hạn retry |
| Lỗi tạm thời | SMTP 4xx, rate limit, kết nối tạm gián đoạn | Retry với backoff |
| Lỗi recipient | Địa chỉ không hợp lệ, mailbox bị từ chối vĩnh viễn | Đánh dấu lỗi vĩnh viễn theo phản hồi |
| Lỗi không rõ kết quả | Timeout sau khi gửi DATA | Đánh dấu UNKNOWN hoặc áp dụng chính sách đối soát |
| Lỗi hạ tầng cục bộ | Database tạm thời không truy cập được khi cập nhật kết quả | Cần phục hồi trạng thái bằng lease/reconciliation |

Không phải mọi MailException đều có thể phân loại chỉ bằng class exception. Khi có thể, đọc SMTP response code hoặc metadata từ provider. Không lưu nguyên exception message nếu nó có thể chứa địa chỉ, URL token hoặc dữ liệu nhạy cảm.

### Backoff theo cấp số nhân

Một chính sách đơn giản:

~~~text
delay = min(maxDelay, baseDelay * 2^(attempt - 1)) + jitter
~~~

Ví dụ với base delay 30 giây, max delay 30 phút:

| Attempt | Delay cơ sở trước jitter |
|---:|---:|
| 1 | 30 giây |
| 2 | 60 giây |
| 3 | 120 giây |
| 4 | 240 giây |
| 5 | 480 giây |

Jitter ngẫu nhiên giúp nhiều worker không cùng retry vào một thời điểm sau khi SMTP provider phục hồi. Cần giới hạn số lần thử, tổng thời gian và chính sách xử lý khi vượt giới hạn.

Ví dụ cập nhật retry:

~~~java
@Service
public class OutboxFailureService {

    private final JdbcTemplate jdbcTemplate;

    public OutboxFailureService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void scheduleRetry(
            UUID id,
            UUID claimToken,
            Instant nextAttemptAt,
            String safeError
    ) {
        int updated = jdbcTemplate.update(
                """
                UPDATE notification_outbox
                SET status = 'RETRY',
                    next_attempt_at = ?,
                    locked_by = NULL,
                    claim_token = NULL,
                    locked_until = NULL,
                    last_error = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                  AND status = 'PROCESSING'
                  AND claim_token = ?
                """,
                Timestamp.from(nextAttemptAt),
                safeError,
                id,
                claimToken
        );

        if (updated != 1) {
            throw new IllegalStateException("Outbox claim was lost");
        }
    }
}
~~~

safeError cần được rút gọn và làm sạch. Hàm phân loại exception và tính nextAttemptAt được đặt ở tầng chính sách retry; không lấy nội dung lỗi tùy ý rồi ghi nguyên văn vào database.

## 13. Số lần thử và trạng thái cuối

Một record không nên retry vô hạn. Có thể định nghĩa:

~~~text
PENDING
   |
   v
PROCESSING
   |
   +---- gửi thành công ------> SUBMITTED
   |
   +---- lỗi tạm thời --------> RETRY
   |                              |
   |                              v
   |                          PROCESSING
   |
   +---- lỗi vĩnh viễn -------> FAILED
   |
   +---- kết quả không rõ ----> UNKNOWN
~~~

Khi số attempt vượt ngưỡng:

- Đánh dấu FAILED hoặc DEAD_LETTER.
- Lưu mã lỗi đã làm sạch và thông tin truy vết.
- Phát metric/alert để vận hành kiểm tra.
- Có quy trình sửa dữ liệu và replay có kiểm soát nếu nghiệp vụ cho phép.

Không nên tự động chuyển mọi lỗi sang FAILED sau một lần. Lỗi SMTP tạm thời cần cơ hội retry; lỗi template không thể sửa bằng retry liên tục.

## 14. Kết quả không rõ và giới hạn exactly-once

Outbox giúp bảo đảm **ý định gửi email được lưu bền vững**, nhưng không thể tạo exactly-once delivery qua SMTP chỉ bằng transaction database.

Một tình huống khó:

1. Worker gửi toàn bộ DATA cho SMTP server.
2. SMTP server nhận và chấp nhận message.
3. Kết nối bị ngắt trước khi worker nhận phản hồi cuối.
4. Worker thấy timeout và không biết server đã chấp nhận hay chưa.
5. Nếu retry, email có thể được gửi hai lần.

Đây là trạng thái **UNKNOWN**, không phải chắc chắn FAILED.

Các biện pháp giảm rủi ro:

- Lưu event ID, notification ID và attempt ID.
- Dùng idempotency key nếu email provider có API hỗ trợ và cam kết semantics rõ ràng.
- Lưu provider message ID khi nhận được.
- Đối soát trạng thái qua API/webhook provider nếu có.
- Giới hạn retry và có chính sách riêng cho lỗi không rõ.
- Nội dung email có thể hiển thị mã thông báo để hỗ trợ điều tra, nhưng không dựa vào đó để giả định mailbox tự deduplicate.

**SMTP Message-ID không phải cam kết chống trùng.** Việc gửi lại cùng Message-ID không bảo đảm mọi server hoặc mailbox sẽ loại bỏ email thứ hai.

Transactional outbox thường cung cấp mô hình **at-least-once processing/attempt**: record bền vững sẽ được thử lại cho tới khi được xử lý theo chính sách. Ứng dụng phải chấp nhận khả năng gửi trùng trong một số tình huống không thể xác định kết quả.

## 15. Lease, worker chết và thu hồi record PROCESSING

Worker có thể dừng bất ngờ sau khi claim:

- Process bị kill.
- Container restart.
- Máy chủ mất điện.
- Thread bị kẹt.
- SMTP client treo lâu hơn dự kiến.

Nếu record đã đổi sang PROCESSING nhưng không bao giờ được trả lại, nó sẽ bị kẹt vĩnh viễn. Vì vậy cần **lease**:

- Khi claim, đặt locked_until ở tương lai.
- Worker xử lý trong khoảng thời gian lease.
- Nếu xử lý xong, cập nhật trạng thái và xóa lock.
- Nếu worker chết, lease hết hạn; worker khác có thể claim lại.

### Chọn thời hạn lease

Lease cần dài hơn thời gian xử lý dự kiến, bao gồm render và gửi SMTP. Nếu email có attachment lớn hoặc provider thường chậm, lease vài phút có thể phù hợp hơn vài giây.

Nếu một thao tác có thể kéo dài hơn lease, worker cần gia hạn lease bằng heartbeat:

~~~sql
UPDATE notification_outbox
SET locked_until = :newLockedUntil,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :id
  AND status = 'PROCESSING'
  AND claim_token = :claimToken;
~~~

Gia hạn chỉ thành công khi token còn hợp lệ. Không gia hạn bằng ID đơn thuần vì worker cũ có thể vô tình kéo dài lease của worker mới.

Lease không hủy một SMTP request đang chạy. Nếu worker cũ vẫn gửi sau khi lease hết hạn và worker mới đã claim, có thể xuất hiện hai lần gửi. Chọn lease hợp lý, timeout SMTP rõ ràng và có cơ chế heartbeat khi cần.

## 16. Xử lý nhiều worker đồng thời

Trong production, có thể chạy nhiều instance ứng dụng hoặc nhiều worker để tăng throughput. Cần phối hợp để không gửi cùng record đồng thời.

### SELECT FOR UPDATE SKIP LOCKED

Phù hợp với database hỗ trợ row-level lock và cú pháp tương ứng. Mỗi worker khóa các dòng riêng trong transaction claim ngắn, cập nhật lease rồi commit.

### Atomic compare-and-set

Với database không có SKIP LOCKED, có thể dùng câu UPDATE có điều kiện để chỉ một worker chuyển record từ trạng thái có thể claim sang PROCESSING. Worker chỉ xử lý khi số dòng cập nhật bằng 1. Cần thiết kế batch/claim token cẩn thận và kiểm tra isolation level.

### Message broker

Outbox publisher có thể chuyển event sang broker như Kafka hoặc RabbitMQ; consumer gửi mail. Khi đó cần thiết kế ack, retry, dead-letter và idempotency ở cả hai chặng. Broker không xóa nhu cầu lưu outbox nguyên tử với database nếu event bắt nguồn từ transaction nghiệp vụ.

Không dùng một biến Java synchronized làm cơ chế khóa duy nhất trong hệ thống nhiều instance. Mỗi process có monitor riêng, không chia sẻ lock với instance khác.

## 17. Giữ thứ tự thông báo cho cùng một đối tượng

Nhiều worker có thể xử lý các event của cùng một đơn hàng song song. Ví dụ:

~~~text
Event 1: ORDER_PAID
Event 2: ORDER_SHIPPED
Event 3: ORDER_DELIVERED
~~~

Nếu event 2 gửi chậm hơn event 3, người nhận có thể nhận email “đã giao” trước “đã gửi đi”.

Nếu thứ tự quan trọng, cần chọn một chiến lược:

- Partition theo aggregate_id để các event cùng đối tượng đi qua một luồng tuần tự.
- Chỉ claim event tiếp theo khi event trước của cùng aggregate đã hoàn thành theo chính sách.
- Lưu sequence/version và phát hiện event đến sai thứ tự.
- Gộp các notification cũ nếu trạng thái mới làm nội dung cũ không còn hữu ích, theo quy tắc nghiệp vụ.

Không phải email nào cũng cần đảm bảo thứ tự tuyệt đối. Với thông báo giao dịch quan trọng, cần xác định rõ yêu cầu và chấp nhận trade-off throughput.

## 18. Lịch polling và điều tiết tải

Worker có thể chạy bằng **@Scheduled**:

~~~java
@Scheduled(fixedDelay = 2000)
public void poll() {
    List<ClaimedNotification> batch = claimService.claimBatch(25);
    batch.forEach(processor::process);
}
~~~

fixedDelay tính khoảng nghỉ sau khi lần chạy trước hoàn thành. Nếu một batch mất nhiều thời gian, lần polling kế tiếp sẽ bắt đầu muộn hơn. Có thể dùng fixedRate hoặc scheduler khác, nhưng cần hiểu cách overlap và khóa.

Một số cấu hình vận hành:

~~~yaml
mail:
  outbox:
    poll-delay: 2000
    batch-size: 25
    max-attempts: 8
    lease-seconds: 180
    base-backoff-seconds: 30
    max-backoff-seconds: 1800
~~~

Các giá trị trên là ví dụ. Cần điều chỉnh theo quota SMTP, thời gian phản hồi, dung lượng email, số instance và yêu cầu nghiệp vụ.

### Giới hạn concurrency

- Dùng executor có giới hạn thread và queue.
- Không claim nhiều record hơn khả năng xử lý trong lease.
- Đặt timeout kết nối/đọc/ghi SMTP.
- Tôn trọng rate limit và quota của provider.
- Theo dõi tuổi của record pending và số record retry.
- Có backpressure khi SMTP chậm để không làm đầy heap hoặc queue.

Không nên tăng batch size và số thread mà không theo dõi tài nguyên SMTP/database. Throughput cao hơn có thể đổi lấy nhiều timeout và retry hơn.

## 19. Tách transaction bằng các Spring bean riêng

Một thiết kế dễ hiểu thường có ít nhất ba ranh giới:

| Bean | Method | Transaction |
|---|---|---|
| OrderApplicationService | Cập nhật đơn + insert outbox | Transaction nghiệp vụ |
| OutboxClaimService | Claim batch và đặt lease | Transaction claim ngắn |
| OutboxMailProcessor | Render và gửi SMTP | Không giữ transaction DB |
| OutboxResultService | Đánh dấu submitted | Transaction kết quả riêng |
| OutboxFailureService | Đặt retry/failed/unknown | Transaction kết quả riêng |

Ví dụ:

~~~text
OrderApplicationService
  @Transactional
      UPDATE order
      INSERT outbox
      COMMIT

OutboxMailWorker
  gọi claimService.claimBatch(...)
      OutboxClaimService @Transactional
          SELECT ... FOR UPDATE SKIP LOCKED
          UPDATE PROCESSING + lease
          COMMIT

  gọi processor.process(...)
      render template
      JavaMailSender.send(...)     <-- ngoài transaction DB
      gọi resultService.markSubmitted(...)
          @Transactional(REQUIRES_NEW)
          UPDATE SUBMITTED
          COMMIT
~~~

Spring transaction thông thường được quản lý qua proxy. Một lời gọi nội bộ cùng object tới method @Transactional có thể không đi qua proxy. Tách service thành bean riêng hoặc dùng cách quản lý transaction tường minh để ranh giới hoạt động đúng.

### REQUIRES_NEW có cần ở mọi method không?

Không nhất thiết. Nếu worker không có transaction bao ngoài, method @Transactional mặc định REQUIRED cũng sẽ mở transaction mới. REQUIRES_NEW thể hiện rõ ý định độc lập và hữu ích khi method có thể được gọi từ một transaction khác. Không nên lạm dụng nó để che giấu ranh giới transaction không rõ ràng.

## 20. Vì sao @Async hoặc AFTER_COMMIT chưa thay thế hoàn toàn outbox?

Spring có các cơ chế như **@Async** và **@TransactionalEventListener(phase = AFTER_COMMIT)**. Chúng có ích trong một số trường hợp nhưng không tự cung cấp độ bền như outbox.

### @Async

~~~java
@Async
public void sendEmailAsync(...) {
    mailSender.send(...);
}
~~~

Phương thức được thực thi trên executor khi cấu hình phù hợp. Nhưng nếu process dừng trước khi task được thực thi hoặc executor queue mất dữ liệu, ý định gửi có thể biến mất. @Async cũng không tự ghi trạng thái retry bền vững.

### @TransactionalEventListener(AFTER_COMMIT)

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderShipped(OrderShippedEvent event) {
    mailService.send(event);
}
~~~

Listener chỉ chạy sau khi transaction commit, tránh gửi trước khi dữ liệu nghiệp vụ được commit. Tuy nhiên, event trong bộ nhớ không tự trở thành durable message. Process có thể dừng sau commit nhưng trước khi listener hoàn tất.

### Outbox

Outbox ghi notification intent trong database cùng transaction nghiệp vụ. Worker có thể đọc lại sau restart, theo dõi trạng thái, retry và quan sát tuổi của message.

Có thể dùng @TransactionalEventListener để đánh thức worker sau commit cho độ trễ thấp, nhưng polling outbox vẫn là cơ chế phục hồi bền vững. Không phụ thuộc duy nhất vào tín hiệu đánh thức trong bộ nhớ.

## 21. Kiểm soát recipient, template và payload

Outbox là dữ liệu bền vững; một lỗi phân quyền hoặc payload sai có thể được gửi lại nhiều lần. Trước khi render/gửi, cần xác nhận:

- Recipient thuộc đúng người dùng/tenant của event.
- Địa chỉ email đã được xác thực theo yêu cầu nghiệp vụ.
- Template key nằm trong danh sách được phép, không lấy đường dẫn template tùy ý từ request.
- Locale được kiểm tra và có fallback.
- Payload version được hỗ trợ.
- URL dùng HTTPS và domain được kiểm soát.
- HTML được escape theo ngữ cảnh.
- Token hoặc dữ liệu riêng không bị ghi vào log.

Không lưu HTML tùy ý do client gửi lên trong outbox rồi render/gửi trực tiếp. Payload nên chứa dữ liệu nghiệp vụ đã xác thực; template do ứng dụng kiểm soát.

### Version hóa payload

Khi schema event thay đổi, worker mới có thể gặp record cũ:

~~~json
{
  "schemaVersion": 2,
  "orderId": "ORD-123",
  "orderCode": "ORD-2026-015",
  "trackingNumber": "VN123456"
}
~~~

Ví dụ JSON chỉ minh họa hình thức. Worker nên đọc schemaVersion và chuyển đổi payload cũ bằng adapter hoặc giữ compatibility trong thời hạn lưu outbox. Không đổi cấu trúc payload rồi giả định tất cả record cũ đã biến mất.

## 22. Bảo mật và retention của outbox

Outbox có thể chứa recipient, tên khách hàng, số đơn, link tracking và dữ liệu khác. Cần đối xử với bảng này như dữ liệu nghiệp vụ:

- Chỉ worker/service có quyền cần thiết mới được đọc payload.
- Mã hóa dữ liệu nhạy cảm khi yêu cầu bảo mật của hệ thống đòi hỏi.
- Hạn chế payload ở các trường thật sự cần render.
- Không lưu mật khẩu SMTP, access token hoặc thông tin thanh toán nhạy cảm.
- Làm sạch error message trước khi lưu.
- Đặt thời hạn giữ record đã gửi và dead-letter.
- Có chính sách xóa/ẩn danh phù hợp với retention và audit.
- Bảo vệ backup và môi trường debug vì chúng cũng có thể chứa payload.

Nếu recipient thay đổi sau khi event được tạo, ứng dụng cần quy tắc rõ ràng: gửi tới địa chỉ snapshot tại thời điểm event hay địa chỉ hiện tại đã được xác minh. Đây là quyết định nghiệp vụ và quyền riêng tư, không nên để worker tự chọn tùy tiện.

## 23. Xử lý bản ghi lỗi và dead-letter

Một record có thể không thể xử lý vì:

- Template key đã bị xóa.
- Payload thiếu trường bắt buộc.
- Recipient không hợp lệ.
- File đính kèm đã bị xóa.
- Quy tắc bảo mật từ chối gửi.
- Provider từ chối vĩnh viễn.

Sau số lần thử tối đa, chuyển record sang FAILED hoặc DEAD_LETTER, giữ thông tin chẩn đoán đã làm sạch và tạo cảnh báo.

Quy trình xử lý:

1. Nhân viên vận hành xem notification ID và mã lỗi.
2. Xác định lỗi dữ liệu, template, quyền hay provider.
3. Sửa nguyên nhân hoặc tạo một notification mới theo quy trình nghiệp vụ.
4. Nếu replay record cũ, xác minh recipient và payload trước.
5. Ghi người thực hiện, thời điểm và lý do replay.

Không sửa trực tiếp payload của record đã gửi hoặc replay hàng loạt mà không có kiểm soát. Việc gửi lại một email có thể tạo hành động lặp ở phía người nhận.

## 24. Quan sát và cảnh báo worker

Các metric hữu ích:

| Metric | Ý nghĩa |
|---|---|
| outbox_pending_count | Số record đang chờ |
| outbox_oldest_pending_age | Tuổi của record chờ lâu nhất |
| outbox_processing_count | Số record đang được claim |
| outbox_expired_lease_count | Số lease hết hạn |
| outbox_retry_count | Số record đang retry |
| outbox_failed_count | Số record dead-letter/failed |
| mail_send_duration | Thời gian tạo và gửi message |
| mail_send_success_total | Số lần SMTP/provider chấp nhận |
| mail_send_failure_total | Số lần gửi thất bại |
| mail_unknown_outcome_total | Số lần kết quả không rõ |

Log có thể chứa:

- Outbox ID và event ID.
- Worker ID và claim token đã được rút gọn/ẩn nếu cần.
- Attempt number.
- Event type và template key.
- Thời gian claim, render, gửi và cập nhật kết quả.
- Provider message ID nếu có.
- Error category/code đã làm sạch.

Không log toàn bộ MIME message, body, attachment hoặc token. Các dữ liệu này có thể chứa thông tin cá nhân và bí mật.

### Cảnh báo nên có

- Pending record quá tuổi SLA.
- Số record retry tăng liên tục.
- Lease hết hạn nhiều bất thường.
- Worker không polling hoặc không xử lý được batch.
- SMTP latency hoặc lỗi vượt ngưỡng.
- Dead-letter tăng đột biến.

## 25. Kiểm thử transactional outbox

Không chỉ kiểm tra mailSender.send(...) được gọi. Cần kiểm tra ranh giới transaction và vòng đời outbox.

### Domain/application test

- Transition hợp lệ cập nhật trạng thái và tạo đúng outbox record.
- Transition không hợp lệ không tạo notification.
- Rollback transaction không để lại outbox record.
- Event ID/notification key chống tạo bản ghi trùng.

### Claim test

- Một record chỉ được một worker claim tại một thời điểm.
- Hai worker đồng thời claim được các batch khác nhau.
- Record RETRY chỉ được claim sau next_attempt_at.
- Record PROCESSING có lease hết hạn có thể được thu hồi.
- Token cũ không thể cập nhật kết quả sau khi record đã được claim lại.

### Processor test

- Worker render đúng template và gọi mail sender.
- Gửi thành công cập nhật SUBMITTED.
- Lỗi tạm thời tạo RETRY với thời gian tiếp theo.
- Lỗi vĩnh viễn tạo FAILED.
- Lỗi không rõ được xử lý theo chính sách UNKNOWN.
- Không có transaction DB bao quanh lời gọi SMTP.

### Integration test

Có thể dùng database test và SMTP server giả lập/sandbox để kiểm tra:

- Business update và outbox insert cùng commit/rollback.
- Query claim với lock và concurrency.
- MIME message có đúng recipient, subject, plain text/HTML, attachment.
- SMTP response được ánh xạ thành trạng thái phù hợp.
- Worker khởi động lại có thể tiếp tục xử lý record pending/expired.

Mock JavaMailSender giúp kiểm tra logic processor nhưng không chứng minh SMTP thực tế hoặc hành vi chuyển phát. Không gửi email thử tới người nhận production.

## 26. Ví dụ luồng worker với transaction tách biệt

Tổng hợp các thành phần:

~~~java
@Component
public class OutboxPollingJob {

    private final OutboxClaimService claimService;
    private final OutboxMailProcessor processor;

    public OutboxPollingJob(
            OutboxClaimService claimService,
            OutboxMailProcessor processor
    ) {
        this.claimService = claimService;
        this.processor = processor;
    }

    @Scheduled(fixedDelay = 2000)
    public void poll() {
        List<ClaimedNotification> batch =
                claimService.claimBatch(25);

        for (ClaimedNotification item : batch) {
            processor.process(item);
        }
    }
}
~~~

Trình tự gọi:

1. poll() gọi claimBatch(...).
2. Spring mở transaction cho OutboxClaimService.
3. Claim service khóa các dòng, cập nhật PROCESSING, tạo token/lease và trả batch.
4. Transaction claim commit khi method trả về.
5. poll() gọi processor.process(...).
6. Processor render, tạo MimeMessage và gọi SMTP ngoài transaction claim.
7. Processor gọi result/failure service để mở transaction riêng cập nhật trạng thái.
8. Worker chuyển sang record kế tiếp.

Nếu worker dừng ở bước 6, lease hết hạn và record có thể được claim lại. Nếu SMTP đã chấp nhận nhưng worker dừng trước bước 7, trạng thái có thể không rõ và lần xử lý sau có nguy cơ gửi trùng. Đây là giới hạn cần quản lý bằng idempotency/đối soát, không phải điều outbox tự loại bỏ.

## 27. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Gửi SMTP bên trong transaction nghiệp vụ | Transaction kéo dài, rollback không đồng bộ | Chỉ ghi outbox trong transaction chính |
| Commit business data rồi mới insert outbox ở transaction khác | Có thể mất notification nếu process dừng giữa hai bước | Ghi outbox cùng transaction |
| Worker chỉ SELECT mà không claim | Nhiều worker gửi cùng một record | Row lock/skip locked hoặc atomic claim |
| Giữ row lock trong lúc SMTP | DB lock kéo dài theo mạng | Commit transaction claim trước khi gửi |
| Không có lease | Record kẹt PROCESSING khi worker chết | Lease và reclaim |
| Không có claim token | Worker cũ ghi đè kết quả của worker mới | Cập nhật có điều kiện theo token |
| Retry vô hạn | Queue tăng và provider bị quá tải | Backoff, max attempts và dead-letter |
| Retry ngay sau timeout không rõ | Email có thể bị gửi trùng | UNKNOWN và đối soát |
| Gọi @Transactional qua self-invocation | Transaction boundary có thể không hoạt động như mong đợi | Tách bean hoặc dùng transaction template |
| Đánh dấu DELIVERED ngay sau send | Trạng thái báo cáo sai | Dùng SUBMITTED và xử lý delivery event riêng |
| Payload chỉ có ID, worker đọc current state | Email có thể mô tả sai event cũ | Snapshot hoặc version |
| Nhiều worker không giới hạn | Vượt quota SMTP/DB, tăng timeout | Giới hạn concurrency và batch |
| Không có index theo trạng thái/thời điểm | Polling chậm khi outbox lớn | Index phù hợp query và retention |
| Lưu payload nhạy cảm vô thời hạn | Tăng rủi ro dữ liệu | Tối thiểu hóa, phân quyền và retention |

## 28. Khi nào nên dùng outbox?

Outbox đặc biệt hữu ích khi:

- Email phải được gửi sau khi thay đổi nghiệp vụ commit.
- Thông báo quan trọng không được mất chỉ vì process restart.
- SMTP có thể lỗi tạm thời và cần retry.
- Có nhiều instance/worker.
- Cần quan sát pending, retry, failed và lịch sử attempt.
- Nội dung email cần phản ánh snapshot của sự kiện.

Với email không quan trọng, không cần retry bền vững và chấp nhận mất khi process dừng, một listener AFTER_COMMIT hoặc tác vụ async có thể đủ. Đừng thêm outbox chỉ vì muốn code phức tạp hơn; hãy dùng khi yêu cầu độ tin cậy và khả năng vận hành xứng đáng với chi phí lưu trữ, polling, retry và cleanup.

## 29. Ghi nhớ

Đọc outbox và gửi mail ngoài transaction chính là cách tách **thay đổi nghiệp vụ**, **ý định gửi notification** và **giao tiếp SMTP** thành các giai đoạn có ranh giới rõ ràng. Transaction chính cập nhật dữ liệu và insert outbox atomically. Worker claim record trong transaction ngắn, commit lease, sau đó render và gọi JavaMailSender khi không giữ transaction database. Kết quả gửi hoặc lỗi được ghi trong transaction riêng.

Transactional outbox giúp không mất ý định gửi khi ứng dụng restart và hỗ trợ retry có kiểm soát. Nó không tự bảo đảm exactly-once delivery: timeout sau khi SMTP có thể đã nhận message vẫn có thể tạo kết quả không rõ và gửi trùng. Vì vậy cần event ID, claim token, lease, backoff, giới hạn attempt, dead-letter, đối soát và metric.

**Giữ transaction database ngắn, không giữ row lock trong lúc chờ SMTP, và chỉ đánh dấu record bằng claim token còn hiệu lực.** Đây là nền tảng để worker gửi email bền vững mà không kéo dài transaction nghiệp vụ.
