# Khả năng phát lại và xử lý bản ghi lỗi trong Spring Framework Mail

Trong một hệ thống gửi email dựa trên sự kiện, việc gọi \`JavaMailSender.send(...)\` chỉ là một bước trong vòng đời thông điệp. Một sự kiện đơn hàng có thể đã được ghi vào database nhưng worker chưa kịp gửi email; SMTP có thể tạm thời từ chối kết nối; template có thể lỗi; hoặc relay đã nhận email nhưng kết nối bị ngắt trước khi ứng dụng nhận được phản hồi cuối. Nếu hệ thống chỉ ghi log rồi bỏ qua, thông điệp có thể biến mất. Nếu retry hoặc phát lại một cách mù quáng, người nhận có thể nhận nhiều email giống nhau.

**Khả năng phát lại (replay) là khả năng đưa một bản ghi đã lưu trở lại luồng xử lý theo một chính sách có kiểm soát.** Nó giúp khôi phục những thông điệp bị lỗi, xử lý lại sau khi sửa cấu hình hoặc template, và hỗ trợ vận hành mà vẫn giữ được lịch sử. Replay cần phân biệt với retry tự động: retry là lần thử tiếp theo trong chính sách giao hàng; replay thường là hành động có chủ đích để đưa một bản ghi lỗi hoặc đã bị cách ly trở lại luồng xử lý.

Trong Spring Framework Mail, JavaMailSender không cung cấp một kho lưu trữ bền vững cho các email thất bại và cũng không tự phát lại thông điệp. Ứng dụng phải lưu yêu cầu gửi, trạng thái, số lần thử, nguyên nhân lỗi và dữ liệu cần thiết để tạo lại email. Với thông báo gắn với giao dịch nghiệp vụ, transactional outbox là một mẫu thiết kế thường dùng.

## 1. Replay giải quyết vấn đề gì?

Hãy xét luồng tạo đơn hàng:

1. Người dùng đặt hàng.
2. Ứng dụng lưu đơn hàng trong database.
3. Ứng dụng cần gửi email xác nhận.
4. SMTP tạm thời không khả dụng.

Nếu ứng dụng chỉ gửi email trong request rồi bỏ exception, đơn hàng vẫn có thể được tạo nhưng email xác nhận bị mất. Người vận hành không có bản ghi đáng tin cậy để biết thông điệp nào cần xử lý lại.

Một hệ thống có replay lưu yêu cầu gửi cùng dữ liệu nghiệp vụ. Worker có thể thử lại sau khi SMTP phục hồi. Nếu lỗi do template thiếu, người vận hành có thể sửa template rồi phát lại đúng bản ghi đã thất bại. Nếu địa chỉ người nhận sai, bản ghi có thể được chuyển sang trạng thái cần sửa dữ liệu hoặc bị đóng theo chính sách.

### Các tình huống thường cần replay

- SMTP relay tạm ngừng hoạt động hoặc từ chối kết nối.
- Provider áp dụng rate limit và yêu cầu thử lại sau.
- Worker bị dừng trong lúc xử lý và bản ghi hết thời gian lease.
- Template hoặc cấu hình được sửa sau khi một nhóm thông điệp thất bại.
- Một lỗi phần mềm trong mail dispatcher đã được khắc phục.
- Bản ghi bị đưa vào dead-letter để điều tra và nay đã đủ điều kiện xử lý lại.
- Một tác vụ vận hành cần phát lại một tập bản ghi có chọn lọc sau khi sự cố được giải quyết.

Replay không nên được dùng để gửi lại mọi email đã gửi thành công chỉ vì muốn chạy lại một sự kiện. Gửi lại email là một hành động có thể tạo tác động bên ngoài và không thể thu hồi sau khi SMTP relay đã chấp nhận.

## 2. Phân biệt retry, replay và resend

Ba khái niệm này thường bị dùng lẫn nhau, nhưng có ý nghĩa vận hành khác nhau:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Retry | Worker tự động thực hiện lần thử tiếp theo theo lịch đã định | SMTP trả lỗi tạm thời, bản ghi được thử lại sau 2 phút |
| Replay | Đưa một bản ghi đã lưu hoặc đã thất bại trở lại luồng xử lý có kiểm soát | Operator replay bản ghi DEAD_LETTER sau khi sửa template |
| Resend | Tạo một lần gửi mới có chủ đích cho người nhận | Người dùng yêu cầu gửi lại biên nhận |
| Re-drive | Đưa message từ dead-letter queue hoặc kho lỗi trở lại queue xử lý | Chuyển một nhóm message đã điều tra về hàng đợi chính |
| Event replay | Phát lại sự kiện nghiệp vụ hoặc event log để consumer xử lý lại | Đọc lại OrderPlaced event từ event store |

Một retry thường giữ nguyên notification ID và tăng attempt count. Replay có thể tiếp tục cùng notification ID hoặc tạo một delivery generation mới tùy chính sách. Resend thường là một yêu cầu nghiệp vụ mới, có ID mới và lý do riêng. Event replay có thể kích hoạt nhiều consumer khác ngoài email, nên không được coi là thao tác resend đơn thuần.

### Vì sao không phát lại sự kiện nghiệp vụ một cách tùy tiện?

Giả sử \`OrderPlaced\` được nhiều consumer xử lý:

- Email confirmation.
- Trừ tồn kho.
- Tạo hóa đơn.
- Gửi dữ liệu sang hệ thống phân tích.

Nếu operator phát lại toàn bộ event chỉ để gửi lại email, các side effect khác có thể chạy lần nữa. Thay vào đó, hãy replay **bản ghi giao hàng email** hoặc một command chuyên biệt cho notification cần xử lý.

Event replay chỉ phù hợp khi toàn bộ consumer có idempotency và việc phát lại event là hành vi được thiết kế trước. Không nên dùng event bus như nút “gửi lại email” nếu event đó còn điều khiển các nghiệp vụ khác.

## 3. Lưu yêu cầu gửi email bền vững bằng transactional outbox

Transactional outbox lưu bản ghi yêu cầu gửi email trong cùng transaction database với thay đổi nghiệp vụ. Điều này giúp tránh tình huống đơn hàng đã commit nhưng yêu cầu gửi email chưa được lưu.

Ví dụ:

~~~java
@Transactional
public Order placeOrder(CreateOrderCommand command) {
    Order order = orderRepository.save(createOrder(command));

    EmailOutboxMessage message = EmailOutboxMessage.pending(
            UUID.randomUUID(),
            "ORDER_CONFIRMED",
            order.getCustomerId(),
            order.getId());

    outboxRepository.save(message);
    return order;
}
~~~

Nếu transaction commit, đơn hàng và outbox record cùng tồn tại. Nếu transaction rollback, cả hai đều rollback. Một worker độc lập đọc outbox và gửi email sau commit.

Luồng tổng quát:

~~~mermaid
flowchart TD
    A["Business command"] --> B["Database transaction"]
    B --> C["Save domain data"]
    B --> D["Save email outbox record"]
    C --> E["Commit"]
    D --> E
    E --> F["Outbox worker"]
    F --> G["Render email"]
    G --> H["JavaMailSender"]
    H --> I["Update delivery state"]
    I --> J{"Failure?"}
    J -- "Temporary" --> K["Retry schedule"]
    J -- "Permanent" --> L["Failed / dead-letter"]
    K --> F
    L --> M["Operator review and replay"]
~~~

Outbox không làm SMTP trở thành một phần của transaction database. Nó bảo đảm **yêu cầu cần gửi được lưu bền vững cùng thay đổi nghiệp vụ**. Việc gửi ra ngoài vẫn là một thao tác độc lập có thể thất bại hoặc có kết quả không chắc chắn.

### Không gửi SMTP trong transaction nghiệp vụ

Ví dụ không nên:

~~~java
@Transactional
public Order placeOrder(CreateOrderCommand command) {
    Order order = orderRepository.save(createOrder(command));
    mailSender.send(buildConfirmation(order));
    return order;
}
~~~

Nếu SMTP mất nhiều giây, transaction database bị giữ mở trong thời gian chờ mạng. Nếu SMTP chấp nhận email rồi database rollback, người nhận có thể nhận xác nhận cho đơn hàng không tồn tại. Nếu database commit nhưng process dừng trước khi gửi, email có thể bị mất.

Hãy ghi outbox trong transaction và để worker gửi sau commit. Không giữ row lock hoặc transaction database mở trong lúc gọi SMTP.

## 4. Thiết kế bản ghi outbox cho khả năng phát lại

Một bản ghi cần có đủ dữ liệu để xác định thông điệp, kiểm soát trạng thái và tái tạo nội dung theo chính sách. Ví dụ mô hình:

~~~java
public enum EmailDeliveryStatus {
    PENDING,
    PROCESSING,
    RETRY_PENDING,
    SUBMITTED,
    SUBMISSION_UNKNOWN,
    FAILED_PERMANENT,
    DEAD_LETTER,
    SUPPRESSED,
    CANCELLED,
    EXPIRED
}
~~~

Một record có thể chứa:

| Trường | Mục đích |
| --- | --- |
| id | ID duy nhất của notification |
| idempotency_key | Khóa nhận diện cùng yêu cầu nghiệp vụ |
| event_type | Loại sự kiện nguồn, ví dụ ORDER_CONFIRMED |
| recipient_id | ID người nhận trong hệ thống |
| recipient_snapshot | Địa chỉ đã được xác định tại thời điểm tạo nếu policy yêu cầu |
| payload | Dữ liệu tối thiểu để render email |
| template_key | Tên template cần dùng |
| template_version | Phiên bản template đã chọn nếu cần tái lập nội dung |
| status | Trạng thái hiện tại |
| attempts | Số lần worker đã thử |
| next_attempt_at | Thời điểm được phép thử tiếp |
| lease_owner | Worker đang giữ quyền xử lý |
| lease_until | Thời điểm hết hạn lease |
| last_error_code | Mã lỗi đã chuẩn hóa |
| last_error_at | Thời điểm lỗi gần nhất |
| created_at / updated_at | Dấu thời gian quản lý |
| expires_at | Hạn xử lý, hữu ích với thông điệp có thời hạn |

Không nhất thiết lưu toàn bộ HTML đã render. Có thể lưu payload và template key/version rồi render khi worker xử lý. Với thông báo pháp lý hoặc giao dịch cần tái lập chính xác, có thể lưu snapshot đã render hoặc tham chiếu đến artifact version theo chính sách bảo vệ dữ liệu.

### Lưu attempt history riêng

Một cột \`attempts\` và \`last_error_code\` chỉ cho biết trạng thái gần nhất. Khi cần điều tra, nên lưu lịch sử từng lần thử:

~~~java
public record EmailDeliveryAttempt(
        UUID id,
        UUID outboxMessageId,
        int attemptNumber,
        Instant startedAt,
        Instant finishedAt,
        String outcome,
        String errorCode,
        String providerMessageId
) {
}
~~~

Bảng attempt history có thể ghi:

- Thời điểm bắt đầu/kết thúc.
- Worker hoặc instance xử lý.
- Kết quả: SUBMITTED, RETRYABLE_FAILURE, PERMANENT_FAILURE hoặc UNKNOWN.
- Mã lỗi đã chuẩn hóa.
- Provider message ID nếu có.
- Correlation ID.

Không lưu SMTP password, token, toàn bộ body email hoặc attachment bytes trong attempt history. Giữ dữ liệu đủ để truy vết nhưng không biến bảng log thành bản sao không kiểm soát của email.

## 5. Mô hình trạng thái và chuyển trạng thái

Trạng thái cần thể hiện rõ bản ghi đang chờ, đang được xử lý, đã submit, lỗi tạm thời hay lỗi cần can thiệp.

~~~text
PENDING
   |
   v
PROCESSING
   |
   +---- SMTP accepted ------------> SUBMITTED
   |
   +---- Temporary failure --------> RETRY_PENDING
   |                                    |
   |                                    v
   |                                 PROCESSING
   |
   +---- Permanent failure --------> FAILED_PERMANENT
   |                                    |
   |                                    v
   |                                 DEAD_LETTER
   |                                    |
   |                                    v
   |                               Manual replay
   |                                    |
   |                                    v
   |                                  PENDING
   |
   +---- Unknown SMTP outcome ------> SUBMISSION_UNKNOWN
   |
   +---- Preference disabled -------> SUPPRESSED
   |
   +---- Expired/cancelled ----------> EXPIRED / CANCELLED
~~~

Không phải mọi trạng thái đều cần có trong mọi dự án. Điều quan trọng là không gộp lỗi tạm thời, lỗi vĩnh viễn và kết quả SMTP không xác định vào cùng một trạng thái FAILED chung chung.

### Ý nghĩa các trạng thái

| Trạng thái | Ý nghĩa | Hành động thường dùng |
| --- | --- | --- |
| PENDING | Đã lưu, chưa được worker claim | Chờ xử lý |
| PROCESSING | Worker đang giữ lease | Đợi worker hoàn tất hoặc lease hết hạn |
| RETRY_PENDING | Lỗi có thể phục hồi, đã lên lịch thử lại | Worker xử lý khi đến hạn |
| SUBMITTED | SMTP relay đã chấp nhận message theo phản hồi nhận được | Không tự động gửi lại |
| SUBMISSION_UNKNOWN | Không biết relay đã nhận hay chưa | Đối soát hoặc xử lý theo policy duplicate |
| FAILED_PERMANENT | Lỗi cần sửa dữ liệu/cấu hình trước khi thử lại | Điều tra |
| DEAD_LETTER | Bản ghi đã vượt retry policy hoặc được chuyển cách ly | Operator review |
| SUPPRESSED | Không gửi theo preference/consent/suppression policy | Giữ audit, không retry |
| CANCELLED | Bị hủy trước khi submit | Không gửi |
| EXPIRED | Đã quá hạn gửi | Không gửi trừ khi có quyết định nghiệp vụ mới |

### Không chuyển trạng thái tùy ý

Ví dụ:

- SUBMITTED không nên trở lại PENDING chỉ vì operator muốn “thử lại cho chắc”.
- SUPPRESSED không nên replay nếu consent vẫn chưa cho phép.
- FAILED_PERMANENT chỉ nên về PENDING sau khi nguyên nhân được sửa và có audit replay.
- PROCESSING hết lease có thể được claim lại, nhưng cần xem xét liệu lần xử lý trước đã gửi SMTP hay chưa.
- SUBMISSION_UNKNOWN cần chính sách riêng; tự động retry có thể gửi trùng.

Nên dùng một state transition service để kiểm tra trạng thái hiện tại và điều kiện chuyển trạng thái thay vì cho nhiều nơi cập nhật status trực tiếp.

## 6. Phân loại lỗi để quyết định retry

Không phải lỗi nào cũng nên retry. Cần phân biệt lỗi tạm thời, lỗi vĩnh viễn và kết quả không xác định.

| Nhóm lỗi | Ví dụ | Hành động |
| --- | --- | --- |
| Kết nối tạm thời | Connection timeout, SMTP host tạm unavailable | Retry có backoff |
| SMTP temporary response | Server trả mã 4xx | Thường retry theo policy/provider |
| Rate limit | Provider giới hạn tốc độ hoặc quota ngắn hạn | Giảm tốc độ, retry sau |
| Authentication | Username/password sai hoặc credential hết hạn | Dừng retry mù, sửa secret |
| Recipient permanent failure | Địa chỉ không hợp lệ hoặc mailbox bị từ chối vĩnh viễn | FAILED_PERMANENT hoặc suppression |
| Sender/relay policy | Sender không được phép relay | Sửa cấu hình hoặc quyền |
| Template/resource error | Không tìm thấy template, parse error, thiếu resource | Sửa artifact/template rồi replay |
| Dữ liệu nghiệp vụ sai | Payload thiếu recipient hoặc trường bắt buộc | Sửa dữ liệu theo quy trình, không retry mù |
| MIME construction error | Attachment/resource không đọc được | Sửa dữ liệu hoặc resource |
| SMTP outcome unknown | Mất kết nối sau khi gửi DATA, không nhận phản hồi cuối | Đối soát hoặc xử lý theo policy duplicate |

### SMTP 4xx và 5xx

SMTP response 4xx thường biểu thị lỗi tạm thời; 5xx thường biểu thị lỗi vĩnh viễn đối với yêu cầu hiện tại. Đây là quy tắc phân loại hữu ích nhưng ứng dụng cần xem cả ngữ cảnh và tài liệu provider. Một số provider có mã riêng hoặc chính sách quota đặc thù.

Không nên chỉ đọc chuỗi exception message để quyết định retry. Spring Mail có thể bọc exception từ Jakarta Mail; hãy chuẩn hóa lỗi ở tầng transport adapter, giữ cause và lấy response code nếu thư viện cung cấp đáng tin cậy.

### Lỗi trước khi gửi và lỗi sau khi gửi

Nếu template không render được, chắc chắn email chưa được submit qua SMTP. Đây thường là lỗi có thể khắc phục rồi replay.

Nếu kết nối SMTP bị ngắt sau khi client đã gửi nội dung DATA nhưng trước khi nhận phản hồi cuối, ứng dụng có thể không biết server đã nhận message hay chưa. Đây là tình huống khác với timeout khi kết nối chưa được thiết lập. Cần phân biệt để tránh gửi duplicate.

## 7. Retry tự động với exponential backoff

Retry policy cần giới hạn số lần thử, thời gian chờ và thời hạn thông điệp. Một công thức thường dùng:

~~~text
delay = min(maxDelay, initialDelay * 2^attempt) + jitter
~~~

Ví dụ:

| Lần thử | Thời gian chờ minh họa |
| --- | --- |
| Lần đầu | Xử lý ngay khi worker claim |
| Lần 2 | 30 giây |
| Lần 3 | 2 phút |
| Lần 4 | 10 phút |
| Lần 5 | 30 phút |

Jitter giúp các worker không đồng loạt retry vào cùng một thời điểm sau sự cố. Các giá trị cần điều chỉnh theo SLA, provider và mức độ khẩn cấp của email.

### Lưu thời điểm retry vào bản ghi

Không cần giữ thread ngủ bằng \`Thread.sleep(...)\`. Worker có thể cập nhật:

~~~text
status = RETRY_PENDING
attempts = attempts + 1
next_attempt_at = now + calculated_delay
last_error_code = SMTP_TEMPORARY
~~~

Sau đó scheduler/queue chỉ claim các bản ghi đến hạn. Cách này không giữ worker thread trong lúc chờ và giúp trạng thái retry có thể quan sát.

### Retry policy theo loại thông điệp

| Loại email | Chính sách gợi ý |
| --- | --- |
| OTP hoặc reset link | Thời hạn ngắn, giới hạn số lần thử; retry cùng challenge còn hiệu lực |
| Xác nhận đơn hàng | Retry bền vững; không bỏ âm thầm |
| Biên nhận/hóa đơn | Retry theo SLA, theo dõi lỗi đến trạng thái cuối |
| Newsletter | Có expiry, kiểm tra unsubscribe trước mỗi lần gửi |
| Khuyến mại | Có expiry, frequency cap và suppression |

Không retry email tùy chọn sau khi chiến dịch hết hạn. Không retry OTP sau khi challenge hết hiệu lực. Với thông báo giao dịch bắt buộc, có thể retry lâu hơn nhưng cần cảnh báo khi vượt SLA.

### Giới hạn retry và dead-letter

Sau số lần thử tối đa hoặc khi gặp lỗi permanent, bản ghi có thể chuyển DEAD_LETTER. Không xóa record. Dead-letter là nơi cách ly để điều tra, sửa nguyên nhân và quyết định replay hoặc đóng bản ghi.

Dead-letter cần lưu:

- ID thông điệp và category.
- Template key/version.
- Số lần thử và thời điểm gần nhất.
- Mã lỗi đã chuẩn hóa.
- Correlation ID.
- Thông tin provider cần thiết nếu có.

## 8. Claim bản ghi và tránh nhiều worker gửi cùng lúc

Nếu có nhiều instance ứng dụng, hai worker có thể cùng đọc một record PENDING và cùng gửi email. Cần cơ chế claim nguyên tử.

Một cách phổ biến là lease:

1. Worker claim bản ghi và ghi PROCESSING, lease_owner, lease_until.
2. Transaction claim commit.
3. Worker gọi SMTP bên ngoài transaction.
4. Worker cập nhật kết quả và xóa lease.
5. Nếu process dừng, lease hết hạn và bản ghi có thể được xử lý lại theo chính sách.

~~~mermaid
sequenceDiagram
    participant W1 as Worker A
    participant DB as Outbox DB
    participant SMTP as SMTP
    participant W2 as Worker B

    W1->>DB: Claim record + lease
    DB-->>W1: PROCESSING
    W1->>SMTP: Send message
    Note over W1,SMTP: Network call outside DB transaction
    SMTP-->>W1: Accepted
    W1->>DB: Mark SUBMITTED
    W2->>DB: Claim due records
    DB-->>W2: Record already claimed, skip
~~~

### Không giữ transaction hoặc row lock trong lúc gọi SMTP

Không nên đặt toàn bộ thao tác sau trong một method @Transactional:

~~~java
@Transactional
public void process(EmailOutboxMessage message) {
    message.markProcessing();
    repository.save(message);
    mailSender.send(buildMimeMessage(message));
    message.markSubmitted();
}
~~~

Transaction có thể giữ lock trong lúc mạng chậm. Nếu SMTP gửi thành công nhưng database rollback, bản ghi vẫn có thể ở trạng thái cũ và được gửi lại. Cần chia thành các bước transaction ngắn:

- Claim record trong transaction.
- Commit claim.
- Gửi SMTP ngoài transaction.
- Cập nhật kết quả trong transaction mới.

### Lease và xử lý worker bị chết

Lease nên dài hơn thời gian xử lý dự kiến nhưng có giới hạn. Nếu email có attachment lớn hoặc provider chậm, có thể cần gia hạn lease khi worker còn hoạt động. Khi lease hết hạn, một worker khác có thể claim lại.

Tuy nhiên, lease hết hạn không chứng minh SMTP chưa nhận email. Nếu worker cũ bị pause sau khi SMTP đã chấp nhận, worker mới có thể gửi lại. Vì vậy, lease giúp tránh concurrent processing thông thường nhưng **không tự bảo đảm exactly-once**.

## 9. Ví dụ repository claim bản ghi

Chi tiết khóa phụ thuộc database. Với PostgreSQL, có thể dùng \`FOR UPDATE SKIP LOCKED\` trong một transaction để nhiều worker claim các nhóm record khác nhau:

~~~sql
SELECT id
FROM email_outbox
WHERE status IN ('PENDING', 'RETRY_PENDING')
  AND next_attempt_at <= CURRENT_TIMESTAMP
ORDER BY created_at
FOR UPDATE SKIP LOCKED
LIMIT 50;
~~~

Sau khi chọn, cập nhật các ID được claim thành PROCESSING, ghi lease_owner và lease_until rồi commit. \`SKIP LOCKED\` là cú pháp phụ thuộc database; với hệ quản trị khác, dùng cơ chế claim tương đương như optimistic locking, update có điều kiện hoặc queue broker.

Một repository interface minh họa:

~~~java
public interface EmailOutboxRepository
        extends JpaRepository<EmailOutboxEntity, UUID> {

    @Query(value = """
            SELECT *
            FROM email_outbox
            WHERE status IN ('PENDING', 'RETRY_PENDING')
              AND next_attempt_at <= CURRENT_TIMESTAMP
            ORDER BY created_at
            FOR UPDATE SKIP LOCKED
            LIMIT :batchSize
            """, nativeQuery = true)
    List<EmailOutboxEntity> lockDueMessages(
            @Param("batchSize") int batchSize);
}
~~~

Đây là ví dụ PostgreSQL-oriented. Cần triển khai claim/update trong cùng transaction, cập nhật lease và đảm bảo các bản ghi đã chọn không còn đủ điều kiện cho worker khác. Kiểm tra cú pháp và giới hạn của database đang dùng trước khi áp dụng.

## 10. Worker gửi email và cập nhật trạng thái

Nên tách component claim, dispatcher và sender để ranh giới transaction rõ ràng.

### Bước claim

~~~java
@Service
public class EmailOutboxClaimer {

    private final EmailOutboxRepository repository;

    public EmailOutboxClaimer(EmailOutboxRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public List<ClaimedEmail> claimBatch(
            String workerId,
            int batchSize,
            Instant leaseUntil) {

        List<EmailOutboxEntity> due =
                repository.lockDueMessages(batchSize);

        return due.stream()
                .map(entity -> {
                    entity.markProcessing(workerId, leaseUntil);
                    return ClaimedEmail.from(entity);
                })
                .toList();
    }
}
~~~

Transaction của claim kết thúc khi method trả về qua Spring proxy. Dispatcher gọi method này từ một bean khác, sau đó thực hiện SMTP bên ngoài transaction.

### Bước dispatch

~~~java
@Component
public class EmailOutboxScheduler {

    private final EmailOutboxClaimer claimer;
    private final EmailDispatcher dispatcher;

    public EmailOutboxScheduler(
            EmailOutboxClaimer claimer,
            EmailDispatcher dispatcher) {
        this.claimer = claimer;
        this.dispatcher = dispatcher;
    }

    @Scheduled(fixedDelay = 1000)
    public void dispatchBatch() {
        List<ClaimedEmail> batch = claimer.claimBatch(
                "mail-worker-1",
                50,
                Instant.now().plusSeconds(60));

        for (ClaimedEmail message : batch) {
            dispatcher.dispatch(message);
        }
    }
}
~~~

Worker ID cần duy nhất theo instance/process, không nên hardcode một giá trị chung cho mọi replica. Ví dụ dùng hostname/pod ID cộng với một UUID của process. Batch size, poll delay và lease duration nên là cấu hình.

### Bước gửi và ghi kết quả

~~~java
@Service
public class EmailDispatcher {

    private final EmailRenderer renderer;
    private final JavaMailSender mailSender;
    private final EmailOutboxStateService stateService;

    public EmailDispatcher(
            EmailRenderer renderer,
            JavaMailSender mailSender,
            EmailOutboxStateService stateService) {
        this.renderer = renderer;
        this.mailSender = mailSender;
        this.stateService = stateService;
    }

    public void dispatch(ClaimedEmail record) {
        try {
            MimeMessage message = renderer.render(record);
            mailSender.send(message);
            stateService.markSubmitted(record.id());
        } catch (MailException exception) {
            stateService.recordFailure(
                    record.id(),
                    classify(exception));
        } catch (MailContentException exception) {
            stateService.markPermanentFailure(
                    record.id(),
                    "CONTENT_ERROR");
        }
    }
}
~~~

Đây là cấu trúc minh họa; các method của stateService nên mở transaction riêng. Trong ứng dụng thật, cần giữ nguyên exception cause, phân loại lỗi transport cẩn thận và có nhánh cho kết quả SMTP không xác định. Không bắt mọi RuntimeException rồi biến thành một lỗi tạm thời chung.

### Lưu ý về transaction proxy

Trong Spring, gọi một method @Transactional từ method khác trong cùng instance (self-invocation) thường không đi qua proxy transaction. Vì vậy, tách claimer/state service thành bean riêng hoặc dùng cơ chế transaction rõ ràng. Đừng giả định mọi annotation trong cùng class đều tạo transaction mới.

## 11. Xử lý kết quả SMTP không xác định

Một trường hợp khó:

1. Ứng dụng kết nối SMTP.
2. Ứng dụng gửi phần DATA.
3. SMTP relay chấp nhận email.
4. Kết nối bị ngắt trước khi client nhận phản hồi cuối.

Ứng dụng không biết chắc email đã được nhận hay chưa. Nếu đánh dấu FAILED rồi retry ngay, người nhận có thể nhận hai bản. Nếu đánh dấu SUBMITTED, email có thể bị mất nếu relay chưa nhận.

Không có cách tổng quát để đạt exactly-once khi gọi SMTP trực tiếp vì database và SMTP không cùng một transaction.

### Trạng thái SUBMISSION_UNKNOWN

Với lỗi xảy ra ở giai đoạn không xác định, có thể ghi:

~~~text
status = SUBMISSION_UNKNOWN
last_error_code = SMTP_FINAL_RESPONSE_MISSING
attempts = attempts + 1
~~~

Sau đó:

- Nếu provider có API/event để tra cứu message ID, thực hiện đối soát.
- Nếu provider hỗ trợ idempotency key, dùng key ổn định theo notification.
- Nếu không thể xác minh, áp dụng chính sách duplicate đã được nghiệp vụ chấp nhận.
- Với email rất quan trọng, có thể chuyển manual review thay vì retry tự động ngay.

### Message-ID có giúp chống trùng không?

Có thể đặt Message-ID ổn định để hỗ trợ trace:

~~~java
message.setHeader(
        "Message-ID",
        "<notification-" + notificationId + "@mail.example.com>");
~~~

Nhưng Message-ID không phải cơ chế idempotency bắt buộc của SMTP. Provider hoặc mailbox có thể vẫn chấp nhận hai message cùng Message-ID. Dùng nó để đối chiếu log/provider event, không tuyên bố nó bảo đảm loại duplicate.

## 12. Idempotency và chống gửi trùng

Một notification nên có khóa idempotency đại diện cho sự kiện nghiệp vụ và người nhận:

~~~text
ORDER_CONFIRMED:order-184:customer-42
~~~

Database có thể đặt unique constraint trên idempotency_key để tránh tạo nhiều outbox record cho cùng yêu cầu. Ví dụ:

~~~sql
CREATE UNIQUE INDEX uq_email_outbox_idempotency
ON email_outbox(idempotency_key);
~~~

Nếu cùng event được xử lý lại, ứng dụng tìm record hiện có thay vì tạo notification mới ngoài ý muốn.

### Idempotency không giống deduplicate SMTP

Unique constraint bảo vệ việc tạo outbox record trong database. Nó không thể ngăn provider gửi hai message nếu cùng một record bị submit hai lần sau một kết quả không xác định.

Có thể giảm duplicate bằng:

- Claim record nguyên tử.
- Lease và heartbeat phù hợp.
- Không gửi lại SUBMITTED.
- Giữ notification ID ổn định.
- Dùng provider idempotency khi có.
- Đối soát SUBMISSION_UNKNOWN.
- Lưu attempt history.

Tuy vậy, cần hiểu hệ thống thường đạt **at-least-once processing** với khả năng gửi trùng trong một số tình huống, chứ không có exactly-once delivery phổ quát.

### Retry và replay cùng notification hay tạo notification mới?

| Tình huống | Cách dùng ID |
| --- | --- |
| SMTP lỗi tạm thời và chưa submit | Giữ notification ID, tăng attempt |
| Template được sửa và bản ghi chắc chắn chưa submit | Có thể replay cùng notification ID, ghi replay audit |
| SUBMISSION_UNKNOWN | Giữ ID để đối soát; không tạo bản ghi mới ngay |
| Người dùng yêu cầu gửi lại biên nhận đã SUBMITTED | Tạo resend request mới có liên kết tới notification cũ |
| Gửi một chiến dịch mới | Tạo notification ID mới theo campaign |

Không reset attempts về 0 chỉ để làm cho bản ghi trông như mới. Nếu cần một delivery generation mới, lưu generation/replay ID riêng và giữ lịch sử cũ.

## 13. Replay bản ghi lỗi sau khi sửa nguyên nhân

Một bản ghi DEAD_LETTER không nên tự động quay về PENDING chỉ vì có người nhấn nút replay. Trước tiên cần xác định lỗi đã được khắc phục chưa.

Ví dụ:

- Template not found: artifact/template đã được deploy đúng.
- Invalid recipient: địa chỉ đã được sửa hoặc có recipient hợp lệ theo nghiệp vụ.
- SMTP authentication: secret/quyền SMTP đã được khôi phục.
- Attachment read error: resource đã được khôi phục và kiểm tra lại.
- Scanner unavailable: có kết quả scan CLEAN cho đúng file version.

### Quy trình replay

1. Chọn bản ghi theo notification ID hoặc điều kiện tìm kiếm có giới hạn.
2. Xem category, recipient, template version, trạng thái và lịch sử attempt.
3. Xác định bản ghi chưa SUBMITTED hoặc có quyết định rõ ràng về resend.
4. Xác minh nguyên nhân lỗi đã được sửa.
5. Kiểm tra consent/preferences, suppression, expiry và quyền recipient hiện tại.
6. Kiểm tra payload và template version sẽ dùng.
7. Ghi audit về operator, thời điểm, lý do và replay generation.
8. Chuyển bản ghi đủ điều kiện sang PENDING hoặc tạo delivery generation mới theo policy.
9. Worker xử lý qua luồng bình thường.
10. Theo dõi kết quả và không xóa lịch sử lần thử trước.

### Replay không phải là sửa trực tiếp mọi cột

Không nên cho operator tự sửa status, attempts, recipient hoặc payload trong database bằng SQL tùy tiện. Tạo một service replay có validation và audit để bảo đảm state transition đúng.

Ví dụ API nội bộ:

~~~http
POST /internal/mail-outbox/{notificationId}/replay
Content-Type: application/json

{
  "reason": "SMTP credential đã được khôi phục",
  "expectedStatus": "DEAD_LETTER"
}
~~~

API này cần authentication, authorization theo vai trò, CSRF protection nếu dùng cookie session, rate limit và audit. Không mở endpoint replay công khai cho người dùng cuối nếu nghiệp vụ không yêu cầu.

### Ví dụ service replay

~~~java
@Service
public class EmailReplayService {

    private final EmailOutboxRepository repository;
    private final ReplayAuditRepository auditRepository;
    private final EmailPolicyService policyService;

    public EmailReplayService(
            EmailOutboxRepository repository,
            ReplayAuditRepository auditRepository,
            EmailPolicyService policyService) {
        this.repository = repository;
        this.auditRepository = auditRepository;
        this.policyService = policyService;
    }

    @Transactional
    public void replay(
            UUID notificationId,
            String operatorId,
            String reason,
            EmailDeliveryStatus expectedStatus) {

        EmailOutboxEntity record = repository
                .findByIdForUpdate(notificationId)
                .orElseThrow(() ->
                        new IllegalArgumentException("Record not found"));

        if (record.getStatus() != expectedStatus) {
            throw new IllegalStateException(
                    "Record status changed; refresh before replay");
        }

        if (record.getStatus() != EmailDeliveryStatus.DEAD_LETTER
                && record.getStatus() != EmailDeliveryStatus.FAILED_PERMANENT) {
            throw new IllegalStateException(
                    "Only failed records can be replayed by this operation");
        }

        policyService.assertReplayAllowed(record);

        record.scheduleReplay();
        auditRepository.save(ReplayAuditEntry.created(
                notificationId, operatorId, reason));
    }
}
~~~

Đây là ví dụ service nội bộ. \`findByIdForUpdate\` cần khóa bản ghi trong transaction; \`assertReplayAllowed\` phải kiểm tra category, recipient, consent, expiry, suppression và điều kiện nghiệp vụ. \`scheduleReplay()\` không nên xóa attempt history hoặc đổi payload ngoài ý muốn. Lý do replay và operator ID cần được validate.

### Không replay SUBMITTED theo API này

Nếu bản ghi đã SUBMITTED, việc gửi lại là một yêu cầu resend mới. Hãy yêu cầu lý do nghiệp vụ và tạo notification mới có liên kết tới notification gốc. Điều này giúp phân biệt “gửi lại do người dùng yêu cầu” với “khôi phục lần gửi thất bại”.

## 14. Replay hàng loạt có kiểm soát

Sau sự cố SMTP hoặc lỗi template, có thể có hàng trăm bản ghi DEAD_LETTER. Replay hàng loạt cần giới hạn phạm vi:

- Chọn một template key/version cụ thể.
- Chọn lỗi đã được phân loại và khắc phục.
- Chọn khoảng thời gian hoặc campaign.
- Loại trừ bản ghi SUBMITTED, SUPPRESSED, CANCELLED, EXPIRED và SUBMISSION_UNKNOWN chưa được đối soát.
- Áp dụng rate limit để không tạo burst gửi email.
- Chạy dry-run trước khi thực hiện.
- Lưu audit cho batch ID, operator, filter và số record được chọn.

### Dry-run

Dry-run chỉ tính toán và hiển thị:

- Số bản ghi đủ điều kiện.
- Số bản ghi bị loại và lý do.
- Category/recipient domain/template version.
- Số bản ghi đã hết hạn hoặc đã submit.
- Tổng dung lượng/ước lượng tốc độ gửi nếu có attachment.

Dry-run không thay đổi trạng thái và không gọi SMTP. Sau khi xem kết quả, operator có thể thực hiện replay theo batch đã xác định.

### Không replay toàn bộ bảng lỗi

Một lệnh kiểu “đưa tất cả FAILED về PENDING” rất nguy hiểm. Nó có thể:

- Gửi lại thông điệp đã submit nhưng trạng thái cập nhật bị lỗi.
- Gửi email tùy chọn cho người đã unsubscribe.
- Gửi OTP đã hết hạn.
- Gửi template chưa được sửa.
- Tạo tải đột biến lên SMTP provider.
- Phát lại message thuộc tenant hoặc recipient không còn hợp lệ.

Replay hàng loạt phải có filter, giới hạn số lượng, quyền vận hành và audit.

## 15. Xử lý bản ghi lỗi theo loại nguyên nhân

Không nên dùng một thao tác replay chung cho mọi lỗi. Bảng dưới đây gợi ý hành vi:

| Nguyên nhân | Hành động trước replay | Có thể replay? |
| --- | --- | --- |
| SMTP timeout trước khi submit | Xác nhận provider đã phục hồi | Có, theo retry policy |
| SMTP 4xx | Tuân theo Retry-After/quota và backoff | Có |
| SMTP 5xx recipient | Kiểm tra địa chỉ và suppression | Chỉ sau khi sửa hoặc có quyết định mới |
| SMTP AUTH failure | Sửa credential/quyền và xác nhận kết nối | Có |
| Template missing/parse error | Deploy template đúng và kiểm tra render | Có nếu chưa submit |
| Payload thiếu dữ liệu | Sửa nguồn dữ liệu theo audit | Có sau khi xác nhận đúng recipient/content |
| Attachment không đọc được | Khôi phục đúng object, kiểm tra hash và scan lại | Có |
| Consent đã bị rút | Không thay đổi để gửi marketing | Không; giữ SUPPRESSED |
| Campaign hết hạn | Tạo campaign/resend mới nếu có cơ sở | Không replay campaign cũ |
| SUBMISSION_UNKNOWN | Đối soát provider hoặc quyết định duplicate | Không tự replay ngay |
| SUBMITTED | Chỉ gửi lại bằng một resend request mới | Không qua failed-record replay |

### Template đã được sửa

Nếu lỗi do template, bản ghi có thể giữ template key và version ban đầu. Khi replay, cần quyết định:

- Render lại bằng template version mới nhất đã phê duyệt.
- Render bằng version đã gắn với notification ban đầu.
- Tạo delivery generation mới và ghi rõ version mới.

Với email giao dịch thông thường, dùng template mới sau khi sửa có thể phù hợp. Với nội dung pháp lý hoặc kiểm toán, việc đổi template có thể thay đổi nội dung đã cam kết; cần policy rõ và lưu version.

### Dữ liệu recipient đã thay đổi

Nếu địa chỉ email người nhận thay đổi sau khi notification được tạo, không tự động dùng địa chỉ mới cho mọi replay. Cần quyết định:

- Dùng recipient snapshot tại thời điểm phát sinh sự kiện.
- Dùng địa chỉ đã xác minh hiện tại.
- Hủy notification cũ và tạo notification mới theo nghiệp vụ.

Với OTP/reset link, không gửi token cũ tới địa chỉ mới nếu challenge không được thiết kế cho trường hợp đó. Với hóa đơn, địa chỉ nhận có thể cần theo hồ sơ giao dịch tại thời điểm phát sinh.

## 16. Dữ liệu snapshot, template version và tính tái lập

Replay có thể diễn ra nhiều giờ hoặc nhiều ngày sau sự kiện. Trong thời gian đó, tên khách hàng, địa chỉ, giá trị đơn hàng hoặc template có thể đã thay đổi.

Có hai cách lưu payload:

### Snapshot tại thời điểm sự kiện

Lưu dữ liệu cần thiết tại thời điểm tạo notification:

~~~json
{
  "orderId": "ORD-184",
  "customerDisplayName": "An",
  "orderTotal": "1250000",
  "currency": "VND",
  "locale": "vi-VN"
}
~~~

Ưu điểm là replay có thể tái tạo nội dung gần với thời điểm sự kiện. Nhược điểm là bản ghi chứa dữ liệu cá nhân/tài chính cần được bảo vệ và có thời hạn lưu.

### Tham chiếu dữ liệu hiện tại

Lưu aggregate ID rồi đọc lại dữ liệu khi worker xử lý. Cách này giảm payload nhưng email có thể phản ánh trạng thái hiện tại thay vì trạng thái lúc sự kiện xảy ra. Nếu đơn hàng thay đổi sau đó, email replay có thể khác email ban đầu dự kiến.

### Chọn theo ý nghĩa nghiệp vụ

| Nội dung | Cách lưu thường phù hợp |
| --- | --- |
| Biên nhận/hóa đơn | Snapshot hoặc dữ liệu giao dịch bất biến |
| Thông báo trạng thái hiện tại | Có thể đọc trạng thái mới nhất nếu nội dung được định nghĩa như vậy |
| OTP/reset challenge | Lưu tham chiếu challenge có expiry, không lưu token thô trong log |
| Newsletter/marketing | Lưu campaign/version và kiểm tra preference hiện tại khi gửi |
| Cảnh báo bảo mật | Lưu sự kiện tối thiểu và recipient policy rõ |

### Template version

Lưu template key và version giúp biết bản ghi đã được render bằng mẫu nào. Nếu chỉ lưu template key, replay sau deploy có thể dùng template mới mà không ai nhận ra nội dung đã thay đổi.

Một record có thể chứa:

~~~text
template_key = order-confirmed
template_version = mail-templates-2026.11.12.3
payload_version = 2
~~~

Nếu template version cũ không còn được giữ, policy replay phải cho phép nâng version hoặc đánh dấu cần can thiệp. Không âm thầm đổi nội dung cho một thông điệp cần tái lập chính xác.

## 17. Replay và quyền của người nhận

Một bản ghi được tạo hợp lệ hôm qua không nhất thiết còn được phép gửi hôm nay. Trước replay cần kiểm tra lại các policy có thể thay đổi:

- Người nhận đã unsubscribe khỏi loại email tùy chọn chưa?
- Consent có còn hiệu lực cho campaign đó không?
- Địa chỉ email có bị bounce/suppress không?
- Notification đã hết hạn chưa?
- Recipient có còn thuộc tenant hoặc giao dịch tương ứng không?
- Người nhận có quyền nhận attachment hoặc dữ liệu nhạy cảm đó không?
- Có yêu cầu xóa dữ liệu hoặc hạn chế xử lý nào áp dụng không?

Với email bắt buộc, không nên dùng cùng một boolean preference như marketing. Tuy vậy, địa chỉ sai, bị bounce vĩnh viễn hoặc không còn thuộc recipient hợp lệ vẫn cần xử lý.

Với email tùy chọn, replay phải tôn trọng trạng thái preference **tại thời điểm gửi**. Operator không được dùng replay để vượt qua unsubscribe/suppression.

## 18. Audit và bảo vệ thao tác vận hành

Replay là hành động có tác động bên ngoài, nên cần kiểm soát:

- Vai trò nào được xem, replay hoặc hủy bản ghi.
- Replay cần một reason bắt buộc.
- Có cần phê duyệt hai người cho batch lớn hay không.
- Những category nào không được replay thủ công.
- Giới hạn số bản ghi mỗi batch.
- Rate limit và thời gian gửi.
- Cách xử lý SUBMISSION_UNKNOWN.
- Cách audit resend đã gửi thành công.

Một audit record có thể gồm:

| Trường | Nội dung |
| --- | --- |
| audit_id | ID của thao tác |
| notification_id | Bản ghi được tác động |
| action | REPLAY_REQUESTED, REPLAY_APPROVED, REPLAY_REJECTED hoặc CANCELLED |
| operator_id | Người thực hiện |
| reason | Lý do có thể đọc được |
| previous_status | Trạng thái trước |
| new_status | Trạng thái sau |
| replay_generation | Lần replay/generation |
| occurred_at | Thời điểm |
| correlation_id | Liên kết log và sự cố |

Không cho phép sửa/xóa audit history bằng giao diện replay thông thường. Audit cũng không nên lưu body email, token hoặc attachment content.

### Quyền hạn theo thao tác

| Vai trò | Quyền phù hợp |
| --- | --- |
| Support | Xem trạng thái tổng quát và mã lỗi đã làm sạch |
| Mail operator | Retry/replay bản ghi theo phạm vi được cấp |
| Security/admin | Xử lý suppression, incident hoặc dữ liệu nhạy cảm theo quy trình |
| Application worker | Claim và cập nhật trạng thái qua service được cấp quyền |

Đây chỉ là ví dụ phân quyền. Phân quyền thực tế cần theo mô hình tổ chức và môi trường triển khai.

## 19. Dead-letter queue và quy trình vận hành

Dead-letter queue (DLQ) là nơi giữ message không thể tiếp tục xử lý theo chính sách retry bình thường. Với outbox trong database, DEAD_LETTER có thể là một trạng thái; với message broker, DLQ có thể là queue riêng.

### Khi nào đưa vào dead-letter?

- Vượt số lần retry tối đa.
- Lỗi permanent không thể tự phục hồi.
- Payload không hợp lệ.
- Template/version không tồn tại sau thời gian chờ.
- Worker không xử lý được message theo schema hiện tại.
- Operator chủ động cách ly để điều tra.

### Runbook xử lý

1. Nhận alert về số lượng DEAD_LETTER hoặc tỷ lệ lỗi tăng.
2. Nhóm theo error code, template key, provider và thời điểm.
3. Xác định lỗi diện rộng hay chỉ một recipient/notification.
4. Kiểm tra provider status, deployment, template version và cấu hình.
5. Sửa nguyên nhân ở môi trường thích hợp.
6. Chạy dry-run trên tập bản ghi có filter rõ.
7. Loại các bản ghi đã SUBMITTED, SUPPRESSED, EXPIRED hoặc SUBMISSION_UNKNOWN chưa đối soát.
8. Replay batch nhỏ trước, quan sát kết quả.
9. Mở rộng batch và rate limit khi hệ thống ổn định.
10. Ghi incident ID và kết quả xử lý vào audit.

Không replay toàn bộ DLQ ngay sau khi SMTP vừa phục hồi. Một đợt burst lớn có thể tiếp tục làm provider rate-limit và gây thêm lỗi.

### Các chỉ số vận hành

| Metric | Cách sử dụng |
| --- | --- |
| Outbox pending count | Theo dõi backlog |
| Oldest pending age | Phát hiện thông điệp bị tồn quá lâu |
| Retry count theo error code | Tìm lỗi lặp lại |
| Dead-letter count | Đo lượng bản ghi cần can thiệp |
| Submission unknown count | Theo dõi kết quả không xác định |
| Replay count/operator | Kiểm soát hoạt động vận hành |
| Duplicate suspicion rate | Phát hiện worker/transport có vấn đề |
| SMTP success/temporary/permanent rate | Theo dõi provider |

Alert nên dựa trên độ tuổi backlog và tỷ lệ lỗi, không chỉ số lượng tuyệt đối. Một queue có 100 record trong một hệ thống gửi hàng triệu email có thể bình thường; một notification bảo mật tồn 10 phút có thể đã là sự cố.

## 20. Replay an toàn với Spring Retry hoặc scheduler

Spring Retry có thể hỗ trợ retry trong một lần thực thi, nhưng nó không thay thế outbox. Nếu process dừng, trạng thái retry trong bộ nhớ có thể mất. Với khả năng replay sau restart, cần lưu trạng thái trong database hoặc message broker.

### Retry tại method

Một ví dụ khái niệm:

~~~java
@Retryable(
        retryFor = TemporaryMailException.class,
        maxAttempts = 4,
        backoff = @Backoff(delay = 1000, multiplier = 2))
public void submit(MimeMessage message) {
    mailSender.send(message);
}
~~~

Đoạn code minh họa annotation của Spring Retry nếu dependency và cấu hình tương ứng đã được thêm. Nó retry trong lời gọi hiện tại và không tự lưu attempt history vào outbox. Không dùng retry annotation cho mọi MailException; chỉ retry exception đã được phân loại tạm thời.

### Retry bền vững bằng outbox

Với outbox, sau lỗi tạm thời:

~~~java
@Transactional
public void scheduleRetry(
        UUID notificationId,
        Instant nextAttemptAt,
        String errorCode) {

    EmailOutboxEntity record = repository
            .findByIdForUpdate(notificationId)
            .orElseThrow();

    record.markRetryPending(nextAttemptAt, errorCode);
    attemptRepository.save(
            EmailAttemptEntity.retryableFailure(
                    notificationId, record.getAttempts(), errorCode));
}
~~~

Scheduler sau đó claim các bản ghi đến hạn. Retry state tồn tại qua process restart và có thể được theo dõi bằng query/metrics.

### Kết hợp hai lớp đúng cách

Có thể dùng retry ngắn trong transport adapter cho một lỗi kết nối có thể phục hồi nhanh, nhưng vẫn cần outbox làm cơ chế bền vững cho lần thử sau. Cần giới hạn tổng số lần retry giữa các lớp để tránh nhân số lần thử ngoài dự kiến. Ví dụ 3 lần retry trong adapter nhân với 5 attempt outbox có thể thành 15 lần gửi.

## 21. Hủy và chỉnh sửa bản ghi trước khi replay

Không phải bản ghi lỗi nào cũng nên được replay. Có thể cần hủy:

- Người dùng đã xóa tài khoản.
- Đơn hàng đã bị hủy và thông báo cũ không còn phù hợp.
- Campaign hết hạn.
- Recipient không còn hợp lệ.
- Sự kiện đã được thay thế bằng một thông báo mới hơn.

Hủy nên là một trạng thái riêng như CANCELLED hoặc EXPIRED, kèm reason. Không xóa record để tránh mất dấu vết.

### Không sửa payload tùy tiện

Nếu nội dung sai, có thể cần tạo notification mới thay vì sửa payload cũ. Sửa trực tiếp record có thể làm mất khả năng chứng minh bản ghi ban đầu chứa gì. Nếu policy cho phép sửa recipient/template/payload, ghi rõ:

- Giá trị trước và sau ở mức không nhạy cảm.
- Ai thực hiện và vì sao.
- Version payload/template mới.
- Có cần approval hay không.
- Bản ghi có từng được submit hay chưa.

Với record SUBMITTED, không sửa nội dung lịch sử; tạo resend request mới nếu nghiệp vụ yêu cầu.

## 22. Bảo vệ dữ liệu và retention của bản ghi lỗi

Outbox và DLQ có thể lưu email address, tên, ID giao dịch, nội dung render hoặc tham chiếu attachment. Đây là dữ liệu cần được quản lý.

- Chỉ lưu payload tối thiểu cần để replay.
- Mã hóa dữ liệu nhạy cảm khi lưu theo chính sách hạ tầng.
- Giới hạn quyền đọc outbox và DLQ.
- Không log OTP, reset token, password hoặc toàn bộ body.
- Đặt retention cho record đã SUBMITTED, FAILED và DEAD_LETTER.
- Xóa hoặc ẩn dữ liệu cá nhân khi hết thời hạn được phép.
- Không giữ attachment bytes trong bảng outbox nếu có thể lưu object reference an toàn.
- Khi replay, xác nhận object version và quyền truy cập vẫn hợp lệ.

Retention cần cân bằng giữa khả năng điều tra, yêu cầu kiểm toán và nguyên tắc giảm thiểu dữ liệu. Một bản ghi lỗi không nên tồn tại vô thời hạn chỉ vì có thể sẽ replay một ngày nào đó.

## 23. Kiểm thử retry và replay

Kiểm thử cần bao phủ cả thành công, lỗi tạm thời, lỗi vĩnh viễn, crash và thao tác vận hành.

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Outbox record được commit cùng đơn hàng | Cả hai cùng tồn tại sau commit |
| Transaction nghiệp vụ rollback | Không có outbox record |
| SMTP trả lỗi tạm thời | RETRY_PENDING và next_attempt_at được lưu |
| SMTP lỗi permanent | FAILED_PERMANENT hoặc DEAD_LETTER |
| Worker dừng khi đang PROCESSING | Lease hết hạn; record được phục hồi theo policy |
| Hai worker claim cùng lúc | Chỉ một worker nhận record |
| SMTP accepted rồi process dừng trước cập nhật DB | Kết quả được xử lý như unknown/reconciliation; duplicate risk được kiểm soát |
| Replay bản ghi DEAD_LETTER hợp lệ | Tạo audit và chuyển trạng thái theo policy |
| Replay bản ghi SUBMITTED | Bị từ chối; cần resend request mới |
| Replay khi preference đã tắt | SUPPRESSED, không gọi SMTP |
| Replay campaign đã hết hạn | EXPIRED, không gửi |
| Replay batch lớn | Dry-run, filter, limit và rate limit được áp dụng |
| Payload/template version không còn | Không gửi nội dung ngoài dự kiến; chuyển xử lý |

### Test lỗi SMTP tạm thời

~~~java
@Test
void schedulesRetryForTemporaryMailFailure() {
    doThrow(new TemporaryMailException("SMTP unavailable"))
            .when(transport).send(any());

    dispatcher.dispatch(claimedEmail);

    verify(stateService).recordRetryableFailure(
            eq(claimedEmail.id()),
            any(Instant.class),
            eq("SMTP_TEMPORARY"));
}
~~~

Test minh họa xác nhận lỗi tạm thời được chuyển thành retry state. Trong test thật, không phụ thuộc chuỗi message để phân loại; dùng exception type/mã lỗi đã chuẩn hóa.

### Test replay không được phép

~~~java
@Test
void doesNotReplaySubmittedRecord() {
    when(repository.findByIdForUpdate(notificationId))
            .thenReturn(Optional.of(submittedRecord));

    assertThrows(
            IllegalStateException.class,
            () -> replayService.replay(
                    notificationId,
                    "operator-7",
                    "Retry request",
                    EmailDeliveryStatus.SUBMITTED));

    verifyNoInteractions(auditRepository);
}
~~~

Đây là test minh họa cho policy chỉ replay bản ghi lỗi. Nếu sản phẩm hỗ trợ resend sau SUBMITTED, cần test một use case riêng tạo notification mới có liên kết tới bản ghi gốc.

### Test worker claim đồng thời

Với database thật hoặc môi trường integration, chạy hai worker đồng thời và xác nhận cùng một record không được claim cho cả hai. Mock repository không đủ để chứng minh locking/skip-locked hoạt động đúng trong database.

## 24. Các lỗi thiết kế thường gặp

### 24.1. Chỉ log lỗi rồi bỏ bản ghi

Log không phải hàng đợi bền vững. Nếu không có outbox hoặc failed-record store, thông điệp khó được retry có kiểm soát và có thể bị mất.

### 24.2. Retry mọi exception

Template sai, recipient không hợp lệ và SMTP authentication sai không tự khắc phục sau vài giây. Phân loại lỗi và retry có điều kiện.

### 24.3. Reset status của toàn bộ FAILED thành PENDING

Có thể gửi trùng, vượt consent, gửi email hết hạn hoặc phát lại nội dung chưa sửa. Dùng replay service có filter và audit.

### 24.4. Phát lại domain event để gửi lại một email

Các consumer khác có thể chạy lại side effect. Replay outbox record hoặc command notification chuyên biệt.

### 24.5. Giữ transaction database trong lúc gọi SMTP

Tăng thời gian giữ lock và không giải quyết được sự không chắc chắn giữa database với SMTP. Claim, send và update state bằng các giai đoạn riêng.

### 24.6. Không có lease hoặc claim nguyên tử

Nhiều worker có thể gửi cùng một bản ghi. Dùng locking/lease hoặc cơ chế queue claim tương đương.

### 24.7. Coi lease hết hạn là bằng chứng email chưa gửi

Worker cũ có thể đã submit email trước khi chết. Xem xét SUBMISSION_UNKNOWN và duplicate risk.

### 24.8. Không giữ attempt history

Chỉ có last_error không đủ điều tra lỗi theo thời gian. Lưu từng attempt với mã lỗi, thời điểm và correlation.

### 24.9. Replay bản ghi SUBMITTED

Có thể gửi duplicate. Resend phải là một yêu cầu mới và có liên kết tới notification gốc.

### 24.10. Replay mà không kiểm tra preference

Một email marketing có thể được gửi sau khi người nhận unsubscribe. Kiểm tra policy hiện tại ngay trước submit.

### 24.11. Replay bằng template mới mà không ghi version

Nội dung gửi lại có thể khác nội dung dự kiến. Lưu template version hoặc ghi rõ generation mới.

### 24.12. Không giới hạn replay hàng loạt

Một thao tác có thể tạo burst email lớn và khiến provider tiếp tục rate-limit. Dry-run, batch nhỏ và rate limit.

### 24.13. Coi JavaMailSender thành công là delivered

Đó là trạng thái SMTP submission theo phản hồi, không phải xác nhận mailbox đã nhận. Cần provider event/bounce nếu cần delivery status.

### 24.14. Xóa dead-letter sau khi replay

Mất lịch sử điều tra. Giữ attempt và replay audit; cập nhật trạng thái hiện tại và generation.

## 25. Quy trình vận hành phát lại một bản ghi lỗi

Một runbook có thể đi theo thứ tự:

1. Tìm notification ID và category.
2. Xem trạng thái, attempt history, error code và thời điểm.
3. Xác định bản ghi có từng SUBMITTED hoặc SUBMISSION_UNKNOWN chưa.
4. Kiểm tra nguyên nhân lỗi và trạng thái SMTP/provider.
5. Kiểm tra template key/version và payload.
6. Kiểm tra recipient, preference, suppression và expiry.
7. Kiểm tra attachment/resource nếu có.
8. Sửa nguyên nhân ở ứng dụng/provider trước.
9. Chạy dry-run hoặc kiểm tra render không gửi.
10. Replay một bản ghi thử theo policy.
11. Theo dõi SUBMITTED/FAILED/RETRY_PENDING và provider event nếu có.
12. Mở rộng replay batch có giới hạn nếu kết quả ổn định.
13. Ghi audit và đóng incident.

### Khi nào không nên replay?

- Bản ghi đã SUBMITTED và không có yêu cầu resend mới.
- Kết quả SMTP chưa rõ và chưa đối soát được.
- Email tùy chọn đã bị unsubscribe/suppress.
- Campaign hoặc challenge đã hết hạn.
- Payload không còn đúng với trạng thái nghiệp vụ.
- Recipient hoặc quyền truy cập chưa được xác nhận.
- Attachment đã thay đổi hoặc scan result không còn áp dụng.
- Template version cần thiết không còn và chưa có policy thay thế.

## 26. Câu hỏi tự kiểm tra

**1. Replay khác retry thế nào?**

Retry là lần thử tiếp theo theo lịch tự động. Replay là hành động đưa bản ghi lỗi/cách ly trở lại luồng xử lý có kiểm soát, thường sau khi đã điều tra hoặc sửa nguyên nhân.

**2. Vì sao nên dùng transactional outbox cho email giao dịch?**

Vì yêu cầu gửi được lưu trong cùng transaction với thay đổi nghiệp vụ, tránh đơn hàng commit nhưng không có bản ghi yêu cầu email.

**3. Outbox có bảo đảm email được gửi đúng một lần không?**

Không. Nó bảo đảm lưu yêu cầu bền vững. SMTP có thể nhận message nhưng ứng dụng không nhận được phản hồi; retry khi đó có thể tạo duplicate.

**4. Vì sao không nên phát lại toàn bộ domain event chỉ để gửi lại email?**

Event có thể có nhiều consumer và side effect. Replay event có thể chạy lại tồn kho, hóa đơn hoặc tích hợp khác. Hãy replay notification/outbox record chuyên biệt.

**5. Bản ghi cần lưu những thông tin nào để replay?**

Notification ID, category/event type, recipient reference, payload hoặc snapshot, template key/version, status, attempts, next attempt, error code và audit metadata.

**6. Tại sao cần attempt history riêng?**

Để biết từng lần thử xảy ra khi nào, do worker nào, kết quả gì và provider trả mã lỗi nào, thay vì chỉ thấy lỗi cuối.

**7. SMTP 4xx và 5xx thường được xử lý thế nào?**

4xx thường là lỗi tạm thời có thể retry; 5xx thường là lỗi permanent cho yêu cầu hiện tại. Cần đối chiếu mã và policy cụ thể của provider.

**8. Vì sao không giữ transaction database mở khi gọi SMTP?**

SMTP là mạng ngoài database; giữ transaction lâu làm tăng lock contention và không bảo đảm rollback được email đã được relay chấp nhận.

**9. Lease giúp điều gì và không giải quyết điều gì?**

Lease giúp tránh nhiều worker xử lý cùng record trong điều kiện bình thường. Nó không chứng minh email chưa được submit khi worker chết hoặc bị pause.

**10. SUBMISSION_UNKNOWN có nghĩa gì?**

Ứng dụng không biết chắc SMTP relay đã nhận message hay chưa. Cần đối soát hoặc áp dụng policy duplicate trước khi retry.

**11. Có nên replay bản ghi SUBMITTED không?**

Không qua luồng failed-record replay. Nếu cần gửi lại, tạo resend request mới có ID và audit riêng.

**12. Vì sao replay email marketing phải kiểm tra preference lại?**

Người nhận có thể unsubscribe sau khi email được enqueue. Replay phải tôn trọng consent/suppression tại thời điểm gửi.

**13. Vì sao cần template version?**

Replay sau deploy có thể dùng nội dung khác. Version giúp tái lập hoặc ghi rõ nội dung nào được dùng cho lần phát lại.

**14. Dead-letter có nên bị xóa sau khi replay?**

Không nên xóa lịch sử. Giữ attempt/audit và cập nhật trạng thái/generation để có thể truy vết.

## Kết luận

**Khả năng phát lại giúp hệ thống Spring Mail khôi phục các thông điệp lỗi mà vẫn giữ được lịch sử và kiểm soát tác động gửi trùng.** Hãy lưu yêu cầu email bằng transactional outbox, phân loại lỗi tạm thời/vĩnh viễn/không xác định, lưu attempt history và dùng claim/lease để điều phối worker. Retry tự động cần backoff, giới hạn số lần và thời hạn; replay thủ công cần xác minh nguyên nhân đã được sửa, kiểm tra recipient/preferences/template version, ghi audit và giới hạn batch. Không phát lại domain event tùy tiện, không reset toàn bộ bản ghi lỗi về PENDING và không coi SUBMITTED là delivered. Với kết quả SMTP không xác định, phải cân nhắc đối soát và duplicate risk trước khi gửi lại. **Một quy trình retry, dead-letter và replay rõ ràng giúp email giao dịch không bị mất âm thầm, đồng thời tránh gửi lặp hoặc gửi sai nội dung khi hệ thống phục hồi sau sự cố.**
