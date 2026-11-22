# Distributed lock cho worker gửi mail

Trong hệ thống **Spring Framework Mail**, việc gửi email thường được chuyển sang một worker chạy theo lịch để HTTP request không phải chờ SMTP, đồng thời dễ áp dụng retry khi nhà cung cấp tạm thời lỗi. Khi ứng dụng chỉ có một instance, một phương thức gắn **@Scheduled** có vẻ đủ. Nhưng khi triển khai nhiều instance để tăng khả dụng hoặc mở rộng tải, **cùng một lịch có thể chạy đồng thời trên nhiều node** và mỗi node có thể cùng đọc một email đang chờ.

Nếu hai worker đều thấy một outbox record trạng thái PENDING rồi gọi **JavaMailSender.send(...)**, người nhận có thể nhận hai email. Vấn đề trở nên khó hơn khi worker chết giữa chừng, khóa hết hạn, mạng bị chia cắt hoặc SMTP relay đã chấp nhận message nhưng database chưa cập nhật trạng thái.

**Distributed lock cho worker gửi mail** là một nhóm kỹ thuật nhằm phối hợp nhiều tiến trình trên những máy khác nhau, xác định ai được chạy một công việc và khi nào quyền đó hết hiệu lực. Trong hệ thống gửi mail, cần đặc biệt phân biệt:

1. **Distributed scheduler lock**: tránh nhiều instance cùng thực hiện một đợt điều phối/lấy việc từ scheduler.
2. **Per-job claim hoặc lease**: bảo đảm một outbox job chỉ có một chủ sở hữu hợp lệ trong một khoảng thời gian.
3. **SMTP submission và nghiệp vụ gửi mail**: side effect qua mạng không thuộc transaction database; lock không tự mang lại exactly-once delivery.

Hai lớp khóa đầu giải quyết cạnh tranh xử lý; lớp thứ ba liên quan **tính đúng đắn khi hệ thống gặp lỗi** và cần thiết kế retry, idempotency, reconciliation, observability.

Bài học trình bày các mô hình này trong bối cảnh **Lập lịch gửi** với Spring Framework Mail: **@Scheduled**, ShedLock, PostgreSQL **FOR UPDATE SKIP LOCKED**, lease/claim token, fencing, Redis lock, transaction boundary, SMTP duplicate window, dead-letter, monitoring và kiểm thử cạnh tranh.

## 1. Vì sao @Scheduled trên nhiều instance có thể gửi trùng?

Giả sử có hai application instances dùng chung database:

~~~text
                 Shared database
                 mail_outbox
                     |
          +----------+----------+
          |                     |
          v                     v
    Application A         Application B
    @Scheduled            @Scheduled
          |                     |
          v                     v
    SELECT PENDING        SELECT PENDING
          |                     |
          +----------+----------+
                     |
               Same mail ID
                     |
          +----------+----------+
          v                     v
   JavaMailSender A      JavaMailSender B
          |                     |
          v                     v
       SMTP relay accepts two submissions
~~~

Nếu các worker chỉ:

~~~sql
SELECT *
FROM mail_outbox
WHERE status = 'PENDING'
ORDER BY created_at
LIMIT 100;
~~~

rồi gửi và cập nhật SENT sau đó, cả A và B đều có thể đọc cùng những dòng PENDING trước khi bất kỳ node nào ghi trạng thái mới.

### 1.1. Ví dụ timeline có race condition

~~~text
10:00:00.000 A reads job #42 -> PENDING
10:00:00.010 B reads job #42 -> PENDING
10:00:00.100 A sends job #42 through SMTP
10:00:00.120 B sends job #42 through SMTP
10:00:00.300 A marks job #42 SENT
10:00:00.310 B marks job #42 SENT
~~~

Database cuối cùng có thể ghi **SENT** và không cho biết đã có hai SMTP submissions, trừ khi ứng dụng lưu lịch sử attempts.

### 1.2. @Scheduled không phải distributed mutex

Spring **@Scheduled** giúp kích hoạt một method theo cron/fixed delay/fixed rate trong từng process ứng dụng. Nó không tự bảo đảm chỉ một trong nhiều process được chạy.

### 1.3. synchronized, ReentrantLock cũng chưa đủ

~~~java
synchronized void dispatch() {
    // ...
}
~~~

hoặc một **ReentrantLock** chỉ phối hợp những thread dùng chung lock trong **cùng JVM**. Application B có JVM riêng nên không nhìn thấy mutex của A.

## 2. Hai loại độc quyền cần quyết định

Không phải mọi hệ thống đều cần một **global lock** cho toàn bộ lượt scheduler. Có hai chiến lược phổ biến:

| Chiến lược | Đơn vị độc quyền | Lợi ích | Giới hạn |
| --- | --- | --- | --- |
| **Khóa scheduler toàn cục** | Một job trigger, ví dụ mail-dispatch | Dễ thêm cho batch job chạy ngắn | Có thể giới hạn throughput và tạo bottleneck |
| **Claim theo outbox row** | Mỗi mail event/job | Nhiều worker xử lý các job khác nhau song song | Cần state machine/lease/recovery rõ |
| **Kết hợp** | Scheduler trigger + từng job | Chủ động kiểm soát cả dispatch và ownership | Tăng độ phức tạp; không phải lúc nào cần |
| **Broker delivery/consumer groups** | Partition/message ownership theo broker | Tận dụng cơ chế broker | Vẫn cần ack, retry và chống side effect trùng |

### 2.1. Khi nào khóa scheduler đủ?

Nếu một đợt chạy ngắn chỉ làm việc quản trị, như quét backlog và tạo các job khác, global lock có thể hữu ích. Nhưng nếu scheduler giữ khóa suốt quá trình gửi hàng nghìn email, tất cả mail throughput có thể bị bó buộc vào một node.

### 2.2. Khi nào claim theo row phù hợp hơn?

Nếu có hàng chục nghìn outbox jobs, nhiều worker có thể claim **những hàng khác nhau** để gửi song song. Khi đó, atomic claim per row thường là cơ chế phối hợp chính, không cần buộc chỉ một scheduler được chạy.

### 2.3. Lựa chọn theo yêu cầu nghiệp vụ

- Muốn mỗi batch scheduler chạy một lần: cân nhắc ShedLock.
- Muốn nhiều node cùng lấy việc nhưng không trùng job: dùng atomic row claim.
- Muốn xử lý gửi mail tin cậy sau database commit: dùng outbox/durable queue.
- Muốn exactly-once SMTP: cần hiểu rằng những cơ chế trên **không tự cung cấp bảo đảm này**.

## 3. Distributed lock thực sự gồm những gì?

Một thiết kế lock đáng tin cậy thường cần:

- **Lock key**: xác định phạm vi độc quyền.
- **Owner identity**: ai đang giữ quyền xử lý.
- **Acquisition**: thao tác giành khóa nguyên tử.
- **Lease/expiration**: khóa có thời hạn để có thể phục hồi khi owner chết.
- **Renewal/heartbeat**: gia hạn khi công việc còn chạy.
- **Release**: chỉ đúng owner còn hiệu lực mới được thả khóa.
- **Ownership check/fencing**: hạn chế owner cũ cập nhật kết quả khi quyền đã bị chuyển.
- **Recovery policy**: xử lý job còn PROCESSING nhưng lease hết hạn.
- **Observability**: biết có bao nhiêu lock acquire được, bị bỏ qua, hết hạn và lấy lại.

### 3.1. Lock key cần chính xác

Một khóa:

~~~text
mail:dispatcher
~~~

phù hợp để chỉ cho phép một scheduler dispatcher chạy.

Một khóa:

~~~text
mail:job:42
~~~

gắn với một mail job. Nhưng **không nên tạo một distributed lock object không giới hạn cho từng message** nếu database row claim đã cung cấp cùng tác dụng hiệu quả hơn.

### 3.2. Lease khác mutex vô hạn

Một lease có thời hạn. Nếu worker chết, các node khác có thể tiếp quản sau expiration. Điều này tăng availability nhưng tạo nguy cơ **owner cũ vẫn đang chạy sau khi lease hết hạn**.

### 3.3. Không nhầm “khóa đã có” với “quyền thực thi SMTP chắc chắn chỉ có một”

Mạng có thể chậm, process có thể bị pause, lease có thể hết hạn trước khi SMTP send kết thúc. Một lock từng hợp lệ không bảo đảm nó còn hợp lệ tại thời điểm side effect diễn ra.

## 4. Không dùng SELECT rồi UPDATE rời rạc

Một anti-pattern:

~~~java
List<MailJob> jobs = repository.findPending();

for (MailJob job : jobs) {
    repository.markProcessing(job.id());
    mailSender.send(build(job));
}
~~~

Tại thời điểm **findPending()**, cả hai node có thể đọc cùng record. Việc **markProcessing()** sau đó không ngăn được race nếu update không kiểm tra state cũ và quyền sở hữu.

### 4.1. Cần thao tác claim nguyên tử

Bản chất thao tác cần là:

~~~text
IF job is eligible and not owned
THEN atomically assign it to this worker
ELSE this worker does not process it
~~~

Có thể thực hiện bằng:

- Database UPDATE có điều kiện và kiểm tra số dòng affected.
- Transaction với **SELECT ... FOR UPDATE SKIP LOCKED** rồi update.
- Atomic queue claim/ack từ broker.
- Lock manager được triển khai đúng semantics.

### 4.2. Không chỉ dựa vào trạng thái PROCESSING

Nếu UPDATE có dạng:

~~~sql
UPDATE mail_outbox
SET status = 'PROCESSING'
WHERE id = :id;
~~~

thì cả worker A và B đều có thể update thành công cùng row, vì không kiểm tra status và owner trước đó.

Tối thiểu phải có điều kiện:

~~~sql
UPDATE mail_outbox
SET status = 'PROCESSING'
WHERE id = :id
  AND status = 'PENDING';
~~~

và **chỉ worker nhận affectedRows = 1 mới được xử lý**. Tuy vậy, để hỗ trợ recovery, còn cần token/lease/state hoàn chỉnh.

## 5. State machine cho mail outbox

Một state model gợi ý:

~~~text
PENDING
   |
   v
PROCESSING
   |
   +-- SMTP call returned successfully --> SENT
   |
   +-- retryable known failure ---------> RETRY_WAIT
   |
   +-- permanent failure ---------------> FAILED
   |
   +-- ambiguous outcome --------------> UNKNOWN_OUTCOME
   |
   +-- worker crashed / lease expired --> ELIGIBLE_FOR_RECOVERY
                                            |
                                            v
                                       PROCESSING
~~~

**ELIGIBLE_FOR_RECOVERY** có thể là trạng thái suy ra từ **PROCESSING + claim_until đã hết**, không nhất thiết là enum lưu trong database.

### 5.1. Phân biệt PENDING và RETRY_WAIT

- **PENDING**: job chưa được attempt hoặc đã sẵn sàng gửi lần đầu.
- **RETRY_WAIT**: job từng lỗi, được phép thử lại từ nextAttemptAt.
- **PROCESSING**: worker hiện đang nắm quyền lease.
- **SENT**: lần submit được caller quan sát là thành công, tùy quy ước hệ thống.
- **FAILED**: lỗi vĩnh viễn/hết retry.
- **UNKNOWN_OUTCOME**: không chắc SMTP relay đã chấp nhận hay chưa.

### 5.2. SENT không có nghĩa inbox delivered

**JavaMailSender.send(...)** trả bình thường thường cho biết SMTP submission hoàn tất theo transport; không chứng minh thư đã vào inbox hay được người nhận đọc.

### 5.3. Phải giữ lịch sử attempts

Một hàng outbox với trạng thái cuối không đủ để biết email đã từng thử bao nhiêu lần, provider nào đã sử dụng và có duplicate window hay không. Có thể dùng bảng **mail_attempts** hoặc structured audit events.

## 6. Schema PostgreSQL minh họa

Một schema dùng cho bài học:

~~~sql
CREATE TABLE mail_outbox (
    id UUID PRIMARY KEY,
    mail_kind VARCHAR(64) NOT NULL,
    recipient VARCHAR(320) NOT NULL,
    subject TEXT NOT NULL,
    body_text TEXT NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    attempts INTEGER NOT NULL DEFAULT 0,
    claim_owner VARCHAR(128),
    claim_token UUID,
    claim_version BIGINT NOT NULL DEFAULT 0,
    claim_until TIMESTAMPTZ,
    last_error_category VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_mail_outbox_ready
    ON mail_outbox(status, next_attempt_at, id);

CREATE INDEX idx_mail_outbox_expired
    ON mail_outbox(status, claim_until, id);
~~~

Đây là schema **minh họa**. Trong sản phẩm, những cột lưu nội dung email có thể chứa thông tin riêng tư; cần encryption/retention/access control phù hợp. Với attachment, thường lưu reference tới storage được bảo vệ thay vì giữ raw bytes trực tiếp trong bảng job.

### 6.1. claim_owner

Định danh worker, ví dụ một alias instance kết hợp random UUID của process. Không dùng một hostname chung cho mọi pod restart nếu cần xác định owner từng phiên.

### 6.2. claim_token

Một token khó đoán được tạo cho **mỗi lượt claim**, được dùng trong câu UPDATE có điều kiện. Không được phép worker bất kỳ cập nhật SENT chỉ bằng ID của job.

### 6.3. claim_version

Số phiên tăng dần theo mỗi lượt claim. Đây có thể làm **fencing token** đối với các thao tác database/nguồn đích có hỗ trợ kiểm tra thứ tự.

### 6.4. claim_until

Thời điểm lease hết hạn. Worker không được mặc định mình còn sở hữu job mãi mãi chỉ vì từng được claim.

### 6.5. Timestamp database

Dùng **now()** của PostgreSQL trong thao tác claim/renew/update giúp các tiến trình không phải tự so sánh đồng hồ của những host có thể lệch nhau.

## 7. Claim hàng loạt bằng FOR UPDATE SKIP LOCKED

Với PostgreSQL, có thể claim một nhóm job trong **một transaction ngắn**.

Ví dụ SQL:

~~~sql
WITH picked AS (
    SELECT id
    FROM mail_outbox
    WHERE (
        status IN ('PENDING', 'RETRY_WAIT')
        AND next_attempt_at <= now()
    )
    OR (
        status = 'PROCESSING'
        AND claim_until < now()
    )
    ORDER BY next_attempt_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT :batch_size
)
UPDATE mail_outbox AS m
SET status = 'PROCESSING',
    claim_owner = :owner,
    claim_token = :token,
    claim_version = m.claim_version + 1,
    claim_until = now() +
        (:lease_seconds * INTERVAL '1 second'),
    attempts = m.attempts + 1,
    updated_at = now()
FROM picked
WHERE m.id = picked.id
RETURNING
    m.id,
    m.recipient,
    m.subject,
    m.body_text,
    m.claim_token,
    m.claim_version;
~~~

Câu lệnh sử dụng cú pháp PostgreSQL; không sao chép sang MySQL/SQL Server/Oracle mà không kiểm tra khả năng tương ứng.

### 7.1. Vai trò của FOR UPDATE

Nó yêu cầu khóa các rows được chọn trong transaction. Các transaction đồng thời không thể đơn giản cùng claim một row khi query được thiết kế đúng.

### 7.2. Vai trò của SKIP LOCKED

Nếu worker A đã khóa một row, worker B **bỏ qua row đang bị khóa** thay vì đợi rồi cùng lấy. Điều này phù hợp với hàng đợi nhiều consumer, nơi thứ tự tuyệt đối không phải mục tiêu duy nhất.

### 7.3. Vì sao phải là một transaction ngắn?

Transaction nên:

1. Chọn những job đủ điều kiện.
2. Update status/owner/token/version/lease.
3. Nhận kết quả claimed rows.
4. Commit.

**Không giữ transaction row lock trong lúc gọi SMTP**. SMTP có thể mất nhiều giây, timeout hoặc treo theo điều kiện mạng; giữ khóa database lâu làm giảm throughput và tăng contention.

### 7.4. Expired PROCESSING cũng phải đủ điều kiện recovery

Nếu query chỉ chọn PENDING/RETRY_WAIT, job bị crash ở PROCESSING sẽ kẹt mãi mãi. Nhánh **status = PROCESSING AND claim_until < now()** giúp worker mới lấy lại sau khi lease hết.

### 7.5. Điều kiện expired không có nghĩa chưa gửi

Job PROCESSING hết hạn có thể đã được SMTP relay chấp nhận nhưng worker crash trước khi ghi SENT. Khi claim lại, cần chính sách xử lý khả năng gửi trùng; lock chỉ giải quyết ownership ở database.

## 8. Ghi chú về SQL claim và throughput

### 8.1. ORDER BY không bảo đảm thứ tự tuyệt đối

Khi dùng SKIP LOCKED, rows đang khóa bị bỏ qua. Trong cạnh tranh, thứ tự thực thi job có thể khác thứ tự created_at/next_attempt_at.

Nếu một loại thông báo yêu cầu thứ tự nghiêm ngặt, cần thiết kế ordering/partitioning riêng; không coi SKIP LOCKED là FIFO tuyệt đối.

### 8.2. Batch size

Nếu claim hàng nghìn jobs nhưng chỉ có vài SMTP worker threads, phần lớn jobs sẽ nằm PROCESSING mà không được gửi kịp trước lease expiry. Hãy giới hạn batch size theo năng lực thực tế và mức concurrency cho phép.

### 8.3. Index cần phù hợp truy vấn

Chỉ mục status, next_attempt_at, claim_until hỗ trợ truy vấn chọn job; kích thước bảng, phân phối trạng thái và workload thực tế quyết định cách tối ưu. Không tạo index chỉ theo cảm tính khi chưa có kế hoạch database operation.

### 8.4. Không claim quá xa trước lúc xử lý

Một node chỉ nên claim số lượng mà nó có thể bắt đầu xử lý trong cửa sổ lease phù hợp. Nếu cần buffer lớn, thiết kế queue/worker riêng thay vì chiếm lease của hàng nghìn jobs đang nằm chờ trong memory.

## 9. Service claim với Spring transaction

Khái niệm Java:

~~~java
import java.util.List;
import java.util.UUID;

import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class MailOutboxClaimRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public MailOutboxClaimRepository(
            NamedParameterJdbcTemplate jdbc
    ) {
        this.jdbc = jdbc;
    }

    @Transactional
    public List<ClaimedMail> claimBatch(
            String owner,
            UUID claimToken,
            int batchSize,
            int leaseSeconds
    ) {
        String sql = """
            WITH picked AS (
                SELECT id
                FROM mail_outbox
                WHERE (
                    status IN ('PENDING', 'RETRY_WAIT')
                    AND next_attempt_at <= now()
                )
                OR (
                    status = 'PROCESSING'
                    AND claim_until < now()
                )
                ORDER BY next_attempt_at, id
                FOR UPDATE SKIP LOCKED
                LIMIT :batch_size
            )
            UPDATE mail_outbox m
            SET status = 'PROCESSING',
                claim_owner = :owner,
                claim_token = :token,
                claim_version = m.claim_version + 1,
                claim_until = now() +
                    (:lease_seconds * INTERVAL '1 second'),
                attempts = m.attempts + 1,
                updated_at = now()
            FROM picked
            WHERE m.id = picked.id
            RETURNING
                m.id,
                m.recipient,
                m.subject,
                m.body_text,
                m.claim_token,
                m.claim_version
            """;

        var params = new MapSqlParameterSource()
                .addValue("owner", owner)
                .addValue("token", claimToken)
                .addValue("batch_size", batchSize)
                .addValue("lease_seconds", leaseSeconds);

        return jdbc.query(
                sql,
                params,
                (rs, rowNum) -> new ClaimedMail(
                        rs.getObject("id", UUID.class),
                        rs.getString("recipient"),
                        rs.getString("subject"),
                        rs.getString("body_text"),
                        rs.getObject("claim_token", UUID.class),
                        rs.getLong("claim_version")
                )
        );
    }
}

public record ClaimedMail(
        UUID id,
        String recipient,
        String subject,
        String bodyText,
        UUID claimToken,
        long claimVersion
) {}
~~~

Ví dụ tập trung vào **claim nguyên tử và transaction**, không bao gồm toàn bộ security, validation, outbox schema migration hay chính sách xử lý trạng thái.

### 9.1. Mỗi claim batch cần token mới

~~~java
UUID claimToken = UUID.randomUUID();
~~~

Token có thể gắn với một batch và được kiểm tra kết hợp với **job ID + claim_version**; nếu muốn định danh riêng từng job, cũng có thể tạo một token cho mỗi row.

### 9.2. Transaction proxy

Đặt claim trong repository/service Spring bean riêng để @Transactional được kích hoạt qua Spring proxy. Gọi một method annotated từ một method khác **trong cùng instance** có thể bỏ qua proxy theo cơ chế AOP thông thường.

### 9.3. Không biến transaction thành nơi gọi sender

claimBatch() chỉ lấy quyền sở hữu rồi commit. Sau đó worker mới tạo MIME và gọi JavaMailSender, không giữ database row lock xuyên qua SMTP.

## 10. Worker xử lý sau khi claim

Một orchestration minh họa:

~~~java
import java.util.List;
import java.util.UUID;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class MailOutboxWorker {

    private final MailOutboxClaimRepository claims;
    private final MailOutboxStateRepository states;
    private final JavaMailSender mailSender;

    private final String owner =
            "mail-worker-" + UUID.randomUUID();

    public MailOutboxWorker(
            MailOutboxClaimRepository claims,
            MailOutboxStateRepository states,
            JavaMailSender mailSender
    ) {
        this.claims = claims;
        this.states = states;
        this.mailSender = mailSender;
    }

    @Scheduled(fixedDelayString = "5000")
    public void dispatch() {
        UUID token = UUID.randomUUID();

        List<ClaimedMail> jobs =
                claims.claimBatch(
                        owner,
                        token,
                        10,
                        120
                );

        for (ClaimedMail job : jobs) {
            processOne(job);
        }
    }

    private void processOne(ClaimedMail job) {
        try {
            SimpleMailMessage message =
                    new SimpleMailMessage();

            message.setFrom("notifications@example.org");
            message.setTo(job.recipient());
            message.setSubject(job.subject());
            message.setText(job.bodyText());

            mailSender.send(message);

            states.markSentIfOwned(job);

        } catch (RuntimeException ex) {
            states.handleFailureIfOwned(job, ex);
        }
    }
}
~~~

**MailOutboxStateRepository** là thành phần minh họa do ứng dụng xây dựng, có trách nhiệm cập nhật trạng thái bằng owner token/version, phân loại lỗi và retry. Code này chủ động đơn giản hóa luồng xử lý để nhấn mạnh ranh giới claim–send–ack.

### 10.1. Điều kiện cần có trong sản phẩm

- Không dùng raw exception message làm error category.
- Không đánh dấu SENT nếu owner/token/version không còn hợp lệ.
- Nếu lease sắp hết, cân nhắc heartbeat trước khi xử lý tiếp.
- Không tiếp tục lặp vô hạn khi SMTP bị outage.
- Không đưa credential/PII vào log metrics.
- Không dùng fixedDelay làm cơ chế đảm bảo chỉ một node chạy.
- Không bắt RuntimeException rồi luôn retry ngay.
- Theo dõi kết quả update affected row để phát hiện mất quyền sở hữu.

### 10.2. Vấn đề của batch xử lý tuần tự

Nếu claim 10 jobs với lease 120 giây, nhưng mỗi send timeout 30 giây, job thứ 10 có thể bắt đầu sau khi lease đã hết. Khi đó worker khác có thể reclaim job trong khi worker ban đầu vẫn xử lý.

Giải pháp: batch nhỏ, concurrency phù hợp, lease renewal hoặc claim ngay trước mỗi lần xử lý, thay vì giả định batch sẽ luôn hoàn tất đủ nhanh.

### 10.3. FixedDelay không bảo đảm SLA

@Scheduled fixed delay chạy lại sau khi method trước kết thúc trên scheduler đó; nếu process crash hoặc bị giữ bởi một send lâu, nhịp xử lý bị ảnh hưởng. Hệ thống cần đo oldest pending age và có đủ worker capacity.

## 11. Update SENT bằng compare-and-set

Sau khi send trả bình thường, worker chỉ được cập nhật nếu **vẫn là owner hợp lệ**.

Ví dụ PostgreSQL:

~~~sql
UPDATE mail_outbox
SET status = 'SENT',
    claim_owner = NULL,
    claim_token = NULL,
    claim_until = NULL,
    updated_at = now()
WHERE id = :id
  AND status = 'PROCESSING'
  AND claim_token = :claim_token
  AND claim_version = :claim_version
  AND claim_until > now();
~~~

### 11.1. Kiểm tra affectedRows

Nếu affectedRows = 1, database xác nhận đúng version/token được cập nhật.

Nếu affectedRows = 0, có thể:

- Lease đã hết hạn.
- Một worker khác reclaim job và tăng version.
- Job đã bị hủy hoặc chuyển trạng thái.
- Một thao tác điều phối khác thay quyền sở hữu.
- Job ID/token không khớp.

Không báo “đã hoàn tất và an toàn” khi câu update không tác động dòng nào.

### 11.2. Ownership check bảo vệ database, không đảo ngược SMTP

Ngay cả khi update trả 0, **mailSender.send có thể đã thực hiện side effect gửi email**. CAS ngăn owner cũ ghi trạng thái sai, nhưng không lấy email đã gửi về được.

### 11.3. Không báo cáo SENT dựa trên log trước update

Một log “smtp submit success” có nghĩa client quan sát send trả bình thường; còn “outbox state SENT” chỉ nên xuất hiện sau khi update hợp lệ thành công. Đây là hai mốc riêng.

## 12. Fencing token và stale worker

Một nguy cơ kinh điển:

~~~text
T0  Worker A claims job #42 with lease until T0+60s
T1  Worker A pauses due to long GC/network stall
T2  Lease expires
T3  Worker B reclaims #42, claim_version becomes 8
T4  Worker B starts work
T5  Worker A resumes with old claim_version 7
~~~

Worker A **từng sở hữu hợp lệ**, nhưng giờ là stale owner.

### 12.1. UUID token

Một UUID ngẫu nhiên giúp nhận biết owner cụ thể và tránh worker khác vô tình release/update job bằng định danh cũ.

### 12.2. Fencing version

Một **claim_version tăng đơn điệu** giúp hệ thống kiểm tra version mới phải được ưu tiên hơn version cũ.

Ví dụ:

~~~text
Worker A claim_version = 7
Worker B claim_version = 8
Database rejects A's state update
~~~

### 12.3. Phải có nguồn đích tôn trọng fencing

Fencing chỉ ngăn stale writes nếu **nguồn đích kiểm tra token/version**. Database update với WHERE claim_version=... có thể làm được điều đó.

Nhưng SMTP relay thông thường **không cung cấp giao thức xác minh claim_version của outbox**. Gắn version vào header email cũng không buộc relay từ chối attempt cũ.

### 12.4. Không quảng cáo fencing là exactly-once SMTP

Fencing bảo vệ các update hoặc side effect trên hệ thống có kiểm tra version; nó **không tự khóa được SMTP side effect**. Đây là giới hạn quan trọng của distributed lock trong bài toán gửi mail.

## 13. Heartbeat gia hạn lease

Nếu công việc có thể dài hơn thời gian lease, worker có thể gia hạn trong lúc còn xử lý.

Ví dụ:

~~~sql
UPDATE mail_outbox
SET claim_until =
        now() + INTERVAL '90 seconds',
    updated_at = now()
WHERE id = :id
  AND status = 'PROCESSING'
  AND claim_token = :claim_token
  AND claim_version = :claim_version
  AND claim_until > now();
~~~

### 13.1. Chỉ owner hiện tại được renew

Kiểm tra ID, token, version và lease chưa hết. Không renew job đã bị reclaim.

### 13.2. Không gia hạn lease vô hạn

Nếu worker bị treo, lease renew loop độc lập có thể tiếp tục giữ job dù SMTP đang không tiến triển. Cần **overall attempt deadline**, thời gian tối đa xử lý và monitoring tiến độ.

### 13.3. Đừng dùng heartbeat để che timeout thiếu

Cần cấu hình mail.smtp.connectiontimeout, mail.smtp.timeout, mail.smtp.writetimeout phù hợp. Nếu socket có thể treo rất lâu, việc tăng lease mãi chỉ làm backlog kẹt.

### 13.4. Bounded send vs renewal

Không dễ cắt một SMTP send đang block chỉ bằng một flag. Một worker hợp lệ có thể đã mất lease mà vẫn đang gửi. Vì thế thiết kế job claims phải chấp nhận và xử lý **ambiguous outcome/duplicate window** thay vì giả định heartbeat hoàn toàn ngăn trùng.

## 14. Phục hồi PROCESSING hết hạn

Một job ở PROCESSING nhưng claim_until < now() là ứng viên cần phục hồi. Có hai cách:

1. **Claim lại trực tiếp** bằng SQL có điều kiện expired PROCESSING.
2. **Recovery sweeper** chuyển các job hết lease sang trạng thái chờ mới sau khi đánh giá attempt lịch sử.

### 14.1. Không reset tất cả PROCESSING một cách mù quáng

Một batch job:

~~~sql
UPDATE mail_outbox
SET status = 'PENDING'
WHERE status = 'PROCESSING';
~~~

có thể phá quyền sở hữu của các worker đang hoạt động bình thường. Phải có điều kiện lease expiry và trạng thái tương ứng.

### 14.2. Recovery cần phân biệt failure window

Nếu biết worker chưa mở SMTP connection, retry có thể ít rủi ro hơn. Nếu worker biến mất sau khi đã truyền DATA, kết quả không chắc chắn.

Không phải ứng dụng nào cũng có telemetry xác định chính xác phase trước khi crash. Vì vậy, có thể phải áp dụng recovery policy dựa trên xác suất, đặc điểm email và khả năng đối soát.

### 14.3. Sự kiện nhạy cảm với thời hạn

Một email OTP hoặc reset password có thể đã hết giá trị trong lúc job kẹt. Recovery cần kiểm tra deadline/TTL, không gửi nội dung đã vô dụng chỉ vì lease hết.

## 15. ShedLock: khóa lịch chạy trên nhiều node

**ShedLock** là một thư viện thường được dùng với Spring Scheduling để bảo đảm một scheduled task có cùng tên không chạy đồng thời qua các instance có chung lock store.

Nó phù hợp khi mục tiêu là **chỉ cho một node thực hiện một scheduler execution tại một thời điểm**.

### 15.1. Ý tưởng

~~~text
             @Scheduled on Node A
                       |
                       v
                Acquire ShedLock?
                       |
                  YES  |  NO
                       |    |
                       v    v
                Run job  Skip run

             @Scheduled on Node B
                       |
                       v
                Acquire ShedLock?
                       |
                    NO | YES
                       |   |
                       v   v
                  Skip  Run job
~~~

Đây là mô hình minh họa: một scheduled execution không lấy được lock thường **bị bỏ qua**, không phải tự động đưa vào queue để chờ đến lượt.

### 15.2. Dependency và version

Dự án Spring Boot có thể dùng module ShedLock hỗ trợ Spring scheduling và một lock provider tương ứng (ví dụ JDBC). Chọn phiên bản tương thích với Spring Boot/Java của dự án.

Ví dụ Gradle với **version do dependency management của dự án xác định**:

~~~groovy
dependencies {
    implementation "net.javacrumbs.shedlock:shedlock-spring"
    implementation "net.javacrumbs.shedlock:shedlock-provider-jdbc-template"
}
~~~

Nếu dự án không quản lý versions cho hai module này, phải khai báo version cụ thể tương thích khi triển khai. Bài học không chọn một version giả định cho mọi dự án.

## 16. ShedLock JDBC schema

Một schema phổ biến:

~~~sql
CREATE TABLE shedlock (
    name VARCHAR(64) NOT NULL PRIMARY KEY,
    lock_until TIMESTAMP(3) NOT NULL,
    locked_at TIMESTAMP(3) NOT NULL,
    locked_by VARCHAR(255) NOT NULL
);
~~~

Bảng này khác với **mail_outbox**. Nó quản lý **scheduler-level lock names**, không quản lý một hàng cho mỗi email.

### 16.1. Một lock name ổn định

Ví dụ:

~~~text
mail-outbox-dispatcher
~~~

Mọi instance chạy cùng scheduled task cần dùng **cùng lock name** và cùng lock store để cạnh tranh quyền chạy.

### 16.2. Nếu hai node dùng database khác nhau?

Nếu mỗi node trỏ tới một bảng ShedLock riêng, mỗi node có thể tự lấy khóa của nó; khi đó không có distributed coordination thực sự.

### 16.3. DB time

ShedLock JDBC provider có khả năng sử dụng database time để hạn chế lệch clock giữa các instances. Khi triển khai, ưu tiên cấu hình sử dụng nguồn thời gian nhất quán nếu provider hỗ trợ.

## 17. Cấu hình ShedLock với Spring Scheduling

Ví dụ Java:

~~~java
import javax.sql.DataSource;

import net.javacrumbs.shedlock.core.LockProvider;
import net.javacrumbs.shedlock.provider.jdbctemplate.JdbcTemplateLockProvider;
import net.javacrumbs.shedlock.spring.annotation.EnableSchedulerLock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration
@EnableScheduling
@EnableSchedulerLock(defaultLockAtMostFor = "PT2M")
public class MailSchedulerLockConfiguration {

    @Bean
    public LockProvider lockProvider(
            DataSource dataSource
    ) {
        return new JdbcTemplateLockProvider(
                JdbcTemplateLockProvider.Configuration
                        .builder()
                        .withJdbcTemplate(
                                new org.springframework.jdbc.core
                                        .JdbcTemplate(dataSource)
                        )
                        .usingDbTime()
                        .build()
        );
    }
}
~~~

### 17.1. Tên class và package

- **@EnableScheduling**: kích hoạt scheduler của Spring.
- **@EnableSchedulerLock**: cấu hình lock cho scheduled tasks được annotated.
- **LockProvider**: abstraction lưu/truy xuất distributed lock.
- **JdbcTemplateLockProvider**: implementation sử dụng database qua JDBC.
- **usingDbTime()**: ưu tiên DB clock theo khả năng và cách triển khai JDBC provider.

### 17.2. Bảng phải tồn tại

Ứng dụng không nhất thiết tự tạo bảng shedlock. Hãy tạo qua migration/DDL của môi trường triển khai trước khi scheduler chạy.

### 17.3. Chọn lockAtMostFor theo ranh giới xử lý

Nếu scheduled job có thể chạy lâu hơn 2 phút, một lockAtMostFor chỉ 2 phút sẽ cho phép instance khác lấy lock khi worker trước **vẫn còn chạy**. Thiết kế phải tính worst-case hợp lý và không dựa vào lock vĩnh viễn.

## 18. Scheduled method với @SchedulerLock

Ví dụ:

~~~java
import net.javacrumbs.shedlock.spring.annotation.SchedulerLock;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class MailOutboxSchedule {

    private final MailOutboxDispatcher dispatcher;

    public MailOutboxSchedule(
            MailOutboxDispatcher dispatcher
    ) {
        this.dispatcher = dispatcher;
    }

    @Scheduled(fixedDelayString = "5000")
    @SchedulerLock(
            name = "mail-outbox-dispatcher",
            lockAtMostFor = "PT2M",
            lockAtLeastFor = "PT3S"
    )
    public void run() {
        dispatcher.dispatchAvailableJobs();
    }
}
~~~

**MailOutboxDispatcher** ở đây là application service tự định nghĩa; ShedLock không tự gửi email.

### 18.1. lockAtMostFor

Thời hạn tối đa mà lock được giữ trong trường hợp node chết/không thể release. Đây là cơ chế phục hồi, **không phải timeout tự động hủy method**.

### 18.2. lockAtLeastFor

Thời gian tối thiểu giữ lock nhằm hạn chế chạy lại quá sát nhau trong một số cấu hình. Nó **không phải lịch gửi retry** và không nên được dùng thay nextAttemptAt trong outbox.

### 18.3. Không lấy được lock thì sao?

Lần scheduled execution đó thường bị **skip**, không phải xếp hàng chờ lock. Lần @Scheduled tiếp theo lại có cơ hội thử.

### 18.4. Dispatcher cần có execution time bounded

Nếu lockAtMostFor = 2 phút nhưng method dispatchAvailableJobs có thể giữ thread 10 phút để gửi email hàng loạt, lớp ShedLock không còn ngăn overlap sau expiry. Nên giới hạn thời gian batch hoặc chỉ khóa bước lấy/điều phối công việc ngắn.

## 19. ShedLock có thay thế row-level claim không?

Không nhất thiết.

Giả sử ShedLock bảo đảm chỉ một scheduler chạy:

~~~text
Node A holds scheduler lock
        |
        v
Fetch 100 pending emails
        |
        v
Publish tasks to executor
        |
        v
Scheduler releases lock
        |
        v
Node B scheduler starts
        |
        v
Fetch same rows still PENDING
~~~

Nếu A mới **enqueue vào executor** nhưng chưa cập nhật ownership trong database, B có thể lấy cùng rows sau khi lock được release.

### 19.1. Khóa đúng phạm vi side effect

Nếu dùng ShedLock chỉ bao quanh công việc enqueue, cần một cách bền vững để đánh dấu job đã claim trước khi thả khóa.

### 19.2. Với multi-worker throughput cao

Nên ưu tiên **atomic outbox claim**. Các node có thể chạy scheduler đồng thời và claim jobs khác nhau nhờ SKIP LOCKED; không cần ép toàn hệ thống còn một dispatcher duy nhất.

### 19.3. Khi nào kết hợp hợp lý?

Ví dụ một scheduler độc quyền làm **batch reconciliation hoặc phân bổ quota**, còn các worker gửi email thật dùng claim per row. Đây là hai phạm vi khác nhau.

## 20. Redis distributed lock: SET NX PX

Một chiến lược khác là dùng Redis để lưu một lock có TTL.

Ví dụ command:

~~~redis
SET mail:dispatcher:lock random-owner-token NX PX 30000
~~~

Ý nghĩa:

- **NX**: chỉ set key nếu nó chưa tồn tại.
- **PX 30000**: TTL theo milliseconds.
- **random-owner-token**: token riêng cho owner đang giữ quyền.

Nếu kết quả là OK, client đã nhận lock trong thời hạn lease theo Redis.

### 20.1. Không dùng SETNX không TTL rồi quên cleanup

Nếu worker chết khi giữ khóa không hết hạn, toàn bộ scheduler có thể bị kẹt. Cần TTL/lease.

### 20.2. Không dùng DEL mù quáng để release

Nếu A lấy lock, TTL hết, B lấy khóa mới cùng tên, rồi A chạy DEL, A có thể xóa khóa hợp lệ của B.

### 20.3. Thả khóa theo token

Một Lua script minh họa:

~~~lua
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
~~~

Client phải truyền key và **token của chính lần acquire**. Nếu token không còn khớp, không xóa khóa của owner khác.

### 20.4. Gia hạn cũng phải kiểm tra token

Không tự PEXPIRE một lock bất kỳ chỉ vì cùng tên key. Renewal phải xác nhận token hiện tại vẫn đúng; nếu không, stale worker có thể gia hạn khóa của owner mới.

## 21. Giới hạn của Redis lock

Redis lock với TTL có ích cho một số thao tác điều phối, nhưng cần hiểu rõ những tình huống:

- Worker bị pause vượt TTL.
- Network partition giữa client và Redis.
- Redis primary failover với replication chưa đồng bộ.
- Client mất response và không biết acquire/release thành công chưa.
- Một worker cũ tiếp tục side effect sau khi lock bị cấp cho worker mới.

### 21.1. Không coi SET NX PX là exactly-once mail

Một lock chỉ kiểm soát quyền xử lý trong một khoảng thời gian. SMTP relay không tham gia kiểm tra Redis token.

### 21.2. Redlock không phải câu trả lời mặc định

Các thuật toán multi-node Redis locking có những giả định riêng về clocks, fault model và latency. Dù áp dụng Redlock, vẫn phải giải quyết stale owner, fencing và **SMTP duplicate side effect**. Đừng coi tên thuật toán là bằng chứng gửi email đúng một lần.

### 21.3. Chọn một nguồn sự thật

Nếu job đã nằm trong relational outbox database, row claim qua chính database thường giúp đơn giản hóa ownership và state transition. Thêm Redis chỉ để giữ một khóa khác với database có thể tạo vấn đề nhất quán giữa hai hệ thống.

## 22. Database advisory lock có phù hợp không?

Một số database hỗ trợ advisory locks (chẳng hạn PostgreSQL). Chúng có thể hữu ích cho **một thao tác điều phối ngắn** nhưng cần chú ý:

- Advisory lock có semantics theo session hoặc transaction tùy API.
- Connection pooling ảnh hưởng vòng đời session.
- Nếu giữ lock khi gửi SMTP, kết nối database có thể bị giữ lâu.
- Advisory lock không thay thế durable job status.
- Worker crash và send không tạo transaction nguyên tử.

### 22.1. Không dùng advisory lock để giấu thiếu state machine

Nếu cần recovery, retry, attempt history và ownership từng job, các trường **status/claim token/lease** trong outbox vẫn rất hữu ích.

### 22.2. Khóa scheduler và khóa row giải quyết phạm vi khác

Advisory lock có thể đóng vai trò scheduler-level lock; atomic row claim vẫn phù hợp khi cần xử lý hàng nghìn mail jobs song song.

## 23. Không giữ database transaction mở khi gửi SMTP

Một anti-pattern nghiêm trọng:

~~~java
@Transactional
public void processOne(UUID id) {
    MailJob job = repository.lockById(id);

    mailSender.send(buildMime(job));

    repository.markSent(id);
}
~~~

Nếu SMTP mất 15 giây:

- Transaction có thể giữ connection/row lock trong 15 giây.
- Các worker khác bị chặn hoặc skip hàng.
- Database deadlocks/timeout và throughput có thể xấu đi.
- Nếu database transaction rollback sau khi SMTP accept, email vẫn đã gửi.

### 23.1. Luồng nên tách

~~~text
Transaction A: claim job atomically
              COMMIT
                     |
                     v
               SMTP send
                     |
                     v
Transaction B: update outcome if still owned
              COMMIT
~~~

### 23.2. Hai transaction không tạo atomicity với SMTP

SMTP send nằm ở giữa hai database transactions. Có một khoảng crash/timeout mà database không chắc relay đã chấp nhận message chưa.

### 23.3. Transaction boundary phải rõ khi dùng Spring AOP

Cần gọi các method transactional qua bean/proxy phù hợp. Tránh giả định một method @Transactional được gọi nội bộ trong cùng class luôn mở transaction riêng.

## 24. Crash windows và khả năng gửi trùng

Bảng các điểm lỗi:

| Thời điểm worker chết | Database có gì? | SMTP có thể ra sao? | Hệ quả |
| --- | --- | --- | --- |
| Trước claim commit | Job vẫn eligible | Chưa gửi | Worker khác có thể claim |
| Sau claim commit, trước build | PROCESSING | Chưa gửi | Recovery sau lease |
| Trong render/prepare | PROCESSING | Chưa gửi nếu send chưa gọi | Retry/failed tùy lỗi |
| Trước kết nối SMTP | PROCESSING | Thường chưa transmit | Có thể retry sau xác minh |
| Trong SMTP DATA | PROCESSING | Không chắc relay accept | Nguy cơ duplicate |
| Sau relay accept, trước update SENT | PROCESSING | Có thể đã gửi | Retry có thể gửi trùng |
| Sau update SENT commit | SENT | Đã có kết quả submit success phía caller | Không retry outbox theo trạng thái này |

### 24.1. Distributed lock không xóa được khoảng crash

Khóa chỉ giảm concurrent processing. Nó không thể làm database update và SMTP relay acceptance thành một commit nguyên tử.

### 24.2. Phải xác định ngưỡng retry chấp nhận được

Thông báo ít quan trọng có thể chấp nhận xác suất trùng nhỏ; email thanh toán hay bảo mật có thể cần đối soát/manual intervention khi outcome không rõ.

### 24.3. Exactly-once processing và exactly-once external effect

Ngay cả khi chỉ một worker nhận job tại một thời điểm, cùng job vẫn có thể được xử lý lại sau crash. Vì vậy, **at-least-once processing** và **best-effort deduplication** thường là các mục tiêu thực tế hơn.

## 25. Idempotency trong mail outbox

Để tránh tạo nhiều ý định gửi cho cùng một sự kiện nghiệp vụ, dùng một khóa duy nhất:

~~~text
business_event_id = ORDER_CONFIRMED:ORDER-1001:VERSION-2
mail_kind         = order_confirmation
recipient_ref     = customer-42
~~~

Có thể dùng unique constraint phù hợp với domain:

~~~sql
CREATE UNIQUE INDEX ux_mail_business_intent
ON mail_outbox(business_event_id, mail_kind, recipient_key);
~~~

Ví dụ này giả định bảng có thêm các cột **business_event_id** và **recipient_key** theo schema của ứng dụng. Nó minh họa **idempotency business intent**, không phải SQL có thể chạy nguyên văn trên schema rút gọn ở phần 6.

### 25.1. Idempotent enqueue

Nếu event listener nhận cùng sự kiện nhiều lần, unique key giúp tránh tạo hai outbox rows đại diện cùng ý định gửi.

### 25.2. Không tự bảo đảm SMTP idempotency

Một unique index ngăn tạo nhiều jobs, nhưng không ngăn một job có nhiều send attempts sau timeout/crash.

### 25.3. Message-ID không phải SMTP idempotency key

MIME **Message-ID** có thể giúp đối soát và một số client threading, nhưng SMTP relay thông thường không có hợp đồng sẽ từ chối message có cùng Message-ID. Không dùng header này thay chính sách xử lý duplicate.

## 26. Lỗi SMTP và chiến lược retry

Một worker có lock hợp lệ vẫn cần phân loại lỗi.

| Nhóm lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| **Invalid address** | Recipient sai syntax | FAILED/DATA_ERROR, không retry mù |
| **Missing attachment** | Resource không tồn tại | Sửa nguồn hoặc terminal |
| **AUTH error** | 535 sai credential | Dừng retry dồn dập, sửa account |
| **TLS error** | Certificate/hostname không hợp lệ | Sửa cấu hình, không bypass TLS |
| **SMTP temporary** | Một số 421/450 | RETRY_WAIT với backoff |
| **Provider throttling** | Rate limit/quota | Điều tiết, backoff |
| **Permanent rejection** | Reply 5xx phù hợp | Phân loại theo enhanced code |
| **Timeout before connect** | Không thể mở connection | Có thể retry giới hạn |
| **Timeout after DATA** | Không nhận được final reply | UNKNOWN_OUTCOME/đối soát |
| **Worker crash** | Lease expired | Recovery policy theo mức chắc chắn |

### 26.1. Không coi mọi 4xx/5xx giống nhau

Một 550 có thể do recipient không tồn tại hoặc sender policy; một 421 có thể là nhà cung cấp tạm không sẵn sàng. Cần dựa trên thông tin SMTP reply/cause chain.

### 26.2. Retry có giới hạn

Thiết kế:

- maxAttempts.
- Exponential backoff.
- Jitter.
- nextAttemptAt.
- Deadline/TTL theo mail kind.
- Terminal FAILED/dead-letter.
- Manual reconciliation khi outcome mơ hồ.

### 26.3. Retry không phụ thuộc việc lock vẫn còn

Sau khi update RETRY_WAIT và release ownership hợp lệ, worker khác có thể claim lại khi nextAttemptAt đã tới. Không giữ lock trong thời gian backoff nhiều phút.

## 27. Cập nhật RETRY_WAIT hoặc FAILED bằng token

Ví dụ khái niệm:

~~~sql
UPDATE mail_outbox
SET status = 'RETRY_WAIT',
    next_attempt_at = :next_attempt_at,
    last_error_category = :category,
    claim_owner = NULL,
    claim_token = NULL,
    claim_until = NULL,
    updated_at = now()
WHERE id = :id
  AND status = 'PROCESSING'
  AND claim_token = :claim_token
  AND claim_version = :claim_version
  AND claim_until > now();
~~~

Để terminal failure, chuyển **status = FAILED** theo policy tương tự.

### 27.1. Đừng update bằng ID đơn lẻ

Một stale worker không được quyền ghi RETRY_WAIT đè lên SENT hoặc PROCESSING version mới của worker khác.

### 27.2. Update 0 rows cần log/metric

Nếu đã mất lease, không tự gọi một UPDATE không điều kiện để “sửa lại trạng thái”. Cần ghi lost_ownership và để cơ chế recovery/state machine xử lý.

### 27.3. UNKNOWN_OUTCOME nên có policy riêng

Không tự chuyển mọi lỗi transport sang RETRY_WAIT. Khi SMTP relay có thể đã chấp nhận message, hệ thống cần cân nhắc đối soát và duplicate risk.

## 28. Scheduler không nên claim khi quá năng lực

Một hệ thống gồm 10 workers nhưng SMTP provider chỉ cho phép 5 connections song song cần đồng thời:

- Bound số worker threads.
- Bound queue capacity.
- Rate limit theo provider/account/tenant.
- Claim batch theo số slot thực sự có.
- Không giữ lease cho hàng trăm job chưa được bắt đầu.

### 28.1. Global scheduler lock không phải rate limiter

Khóa scheduler chỉ ngăn một số execution đồng thời, không kiểm soát số SMTP messages mỗi giây trong một batch.

### 28.2. Rate limit phân tán cần phạm vi rõ

Nếu mỗi node cho phép 10 emails/giây nhưng có 5 nodes, tổng có thể đạt 50 emails/giây. Nếu provider quota là 10 toàn hệ thống, cần shared budget/token bucket hoặc thiết kế phân phối công suất.

### 28.3. Provider-specific concurrency

Khi có nhiều SMTP providers, worker có thể chọn route riêng, mỗi provider/account có quota khác nhau. Claim logic và rate limiter cần đồng bộ trên phạm vi thực sự áp dụng, không mặc định một global lock là đủ.

## 29. Lock contention và throughput

Nếu một global ShedLock buộc mỗi lần chỉ một node gửi toàn bộ mail, các node còn lại đứng chờ hoặc skip scheduler runs.

~~~text
3 application nodes
     |
     +-- 1 node holds global lock and sends 100 mails
     +-- 2 nodes skip
~~~

Với atomic row claim:

~~~text
3 application nodes
     |
     +-- Node A claims jobs 1..10
     +-- Node B claims jobs 11..20
     +-- Node C claims jobs 21..30
~~~

### 29.1. Horizontal scaling có điều kiện

Claim per row giúp nhiều node tăng throughput khi database và SMTP provider còn capacity. Nó không tự vượt quota SMTP hoặc bandwidth/attachment constraints.

### 29.2. Global lock có thể vẫn hữu ích

Một job điều phối ngắn, như tính quota toàn hệ thống hoặc chạy reconciliation định kỳ, có thể cần một scheduler lock để tránh thực hiện trùng công việc quản trị.

### 29.3. Không tạo một lock cho từng recipient nếu không cần

Per-job ownership có thể do database row claim thực hiện hiệu quả. Tạo một Redis lock/key cho hàng triệu email có thể tăng chi phí và phức tạp mà không tăng tính đúng đắn tương xứng.

## 30. Tránh clock skew và lệch thời gian

Trong distributed systems, node A có thể nhanh hơn node B vài giây do đồng bộ clock.

### 30.1. DB-based lease

Đối với claim/release qua PostgreSQL, dùng **now()** trong SQL cho việc so sánh claim_until sẽ giảm phụ thuộc vào clock mỗi node.

### 30.2. ShedLock usingDbTime

Cấu hình dùng DB time khi provider hỗ trợ giúp các node thống nhất thời gian hết hạn theo nguồn dữ liệu chung.

### 30.3. Redis TTL

Redis quản lý TTL tại server, nhưng application vẫn cần xử lý network delay, pause và việc không biết lock còn thuộc mình hay không.

### 30.4. Không trừ System.nanoTime giữa hai nodes

System.nanoTime thích hợp đo elapsed duration trong một JVM, không dùng làm timestamp so sánh lease giữa các máy. Dùng clock/timestamp phù hợp với store.

## 31. Monitoring và metrics cho distributed locks

Các metric gợi ý:

| Metric | Ý nghĩa |
| --- | --- |
| **mail.scheduler.lock.acquired** | Scheduler acquisition thành công |
| **mail.scheduler.lock.skipped** | Scheduled run bỏ qua vì lock bận |
| **mail.outbox.claimed** | Số jobs claim thành công |
| **mail.outbox.claim.conflicts** | Lượt claim/update không còn ownership |
| **mail.outbox.expired_leases** | Số PROCESSING quá claim_until |
| **mail.outbox.pending** | Jobs PENDING/RETRY_WAIT đến hạn |
| **mail.outbox.oldest_pending_age** | Tuổi job chờ lâu nhất |
| **mail.worker.active** | Workers đang gửi |
| **mail.worker.lease_renew.failures** | Heartbeat bị từ chối/lỗi |
| **mail.smtp.submit.attempts** | SMTP attempts thực |
| **mail.smtp.submit.call.duration** | Duration lời gọi send |
| **mail.outbox.unknown_outcomes** | Kết quả SMTP mơ hồ |
| **mail.outbox.terminal_failures** | Jobs lỗi cuối |
| **mail.outbox.recovered_jobs** | Jobs được reclaim sau hết lease |

Tên metric do ứng dụng tự đặt; không mặc định Spring Framework Mail hoặc ShedLock xuất mọi metric nêu trên.

### 31.1. Tách lock metrics khỏi SMTP metrics

Một job được claim không đồng nghĩa đã gửi SMTP. Một send timeout có thể xảy ra dù claim thành công; một scheduler skipped không có nghĩa email bị mất.

### 31.2. Nhãn low cardinality

Có thể dùng **worker_pool**, **mail_kind**, **outcome**, **provider_alias** nếu có tập giá trị hữu hạn.

Không đưa recipient, mailEventId, claimToken, token UUID hoặc raw exception message vào metric labels.

### 31.3. Structured log cho từng job

Ví dụ:

~~~text
event=mail.outbox.claimed
mailEventId=mail-42
ownerAlias=worker-pool-a
claimVersion=8
claimUntil=...
attempt=2
~~~

Thông tin event ID có thể được ghi trong log có phân quyền; không cần lưu body email hoặc credentials.

## 32. Dashboard và cảnh báo

Một dashboard dành cho worker có thể gồm:

1. Số pending jobs và tuổi pending lâu nhất.
2. Số jobs PROCESSING và tuổi lease gần hết.
3. Số expired leases.
4. Throughput claim và SMTP submit.
5. Tỷ lệ SMTP success/failure/unknown.
6. Số lần lock acquisition bị skip.
7. p95/p99 thời gian send.
8. Tần suất lost ownership/fencing failures.
9. Retry backlog và time-to-relay accept.
10. Tải worker/concurrency và provider quota.

### 32.1. Alert expired leases tăng

Nếu claim_until liên tục hết trước khi job hoàn tất, có thể do batch quá lớn, SMTP timeout cao, worker pause hoặc renewal không chạy đúng.

### 32.2. Alert pending tuổi cao

Pending count có thể thấp nhưng một email quan trọng bị kẹt lâu. **Oldest pending age** giúp phát hiện sự cố riêng hoặc starved jobs.

### 32.3. Alert lock skipped không phải luôn là sự cố

Trong mô hình ShedLock có nhiều nodes, scheduled runs bị skip vì một node khác đang giữ lock là hành vi bình thường. Quan trọng là backlog vẫn được xử lý trong SLA.

### 32.4. Alert unknown outcome

Nếu nhiều attempts mất phản hồi sau DATA, hệ thống cần điều tra mạng/provider và nguy cơ duplicate, không chỉ tăng số retry.

## 33. Kiểm thử concurrency bằng nhiều worker

Unit test một worker không chứng minh atomic claim hoạt động khi hai nodes cùng chạy. Cần integration test với database có semantics tương ứng.

Một kịch bản:

~~~text
Prepare 100 PENDING outbox rows
Start worker A and B concurrently
Both call claimBatch in separate transactions
Collect claimed IDs from each
Assert no overlap between A and B
Assert each claimed row has valid token/version
~~~

### 33.1. Dùng cùng engine database trong test

Nếu production dùng PostgreSQL **FOR UPDATE SKIP LOCKED**, nên test với PostgreSQL thực trong môi trường kiểm soát, ví dụ Testcontainers, vì H2 hoặc mock JDBC có thể không phản ánh semantics lock.

### 33.2. Barrier để tạo cạnh tranh thật

Sử dụng CountDownLatch/CyclicBarrier để hai worker bắt đầu gần như đồng thời thay vì chạy tuần tự rồi giả định đã test race.

### 33.3. Không cần SMTP thật trong concurrency test

Mock JavaMailSender hoặc dùng fake transport để kiểm tra claim không trùng. Chỉ khi test network semantics mới cần SMTP capture server.

### 33.4. Assertion về điều gì?

- Mỗi job đang claim có một owner/version hợp lệ.
- Không có hai active claims cùng row ở cùng epoch/version.
- Khi transaction chưa commit, worker khác skip locked row.
- Sau commit, các trạng thái và lease đúng.
- Cập nhật stale token ảnh hưởng 0 rows.

**Không khẳng định test này chứng minh exactly-once SMTP**, vì crash window nằm ngoài row claim.

## 34. Test crash và lease expiration

Một ma trận:

| Tình huống | Mong đợi |
| --- | --- |
| Worker chết trước claim commit | Row vẫn eligible |
| Worker chết sau claim commit, trước send | Recovery sau lease expiry |
| Worker đang xử lý, lease chưa hết | Worker khác không claim |
| Worker pause quá lease | Job có thể được reclaim; owner cũ bị từ chối state update |
| Worker renew hợp lệ | claim_until kéo dài |
| Worker renew token sai | 0 rows affected |
| Worker gửi thành công, update SENT hợp lệ | Job chuyển SENT |
| Worker gửi thành công nhưng lease hết | Update owner cũ bị từ chối, có duplicate risk |
| Worker thất bại tạm thời | RETRY_WAIT và nextAttemptAt |
| Worker gặp lỗi vĩnh viễn | FAILED theo policy |
| Timeout sau DATA | UNKNOWN_OUTCOME/đối soát |
| Scheduler lock không lấy được | Skip execution, không gửi job trùng |

### 34.1. Test stale ownership

1. A claim row và nhận version 1.
2. Làm lease hết hạn trong test bằng DB time phù hợp hoặc dữ liệu fixture.
3. B reclaim và nhận version 2.
4. A gọi markSent với version 1.
5. Assert affectedRows = 0.
6. B có thể cập nhật khi owner hợp lệ.

### 34.2. Test lease renewal

A renew trước expiration thành công. B không được claim trong thời gian lease còn hợp lệ. Nếu A mất quyền, renewal phải thất bại.

### 34.3. Test SMTP duplicate window bằng fake

Cho fake mail transport báo submit đã hoàn thành rồi giả lập crash trước update SENT. Sau khi lease hết, recovery có thể gửi lại. Test phải chứng minh hệ thống nhận diện/định nghĩa được rủi ro, không khẳng định không thể trùng.

## 35. Test ShedLock nhiều scheduler instances

Để kiểm tra scheduler-level locking:

- Hai application contexts dùng cùng bảng ShedLock.
- Cùng lock name và provider store.
- Dùng task có barrier/latch để tạo overlap.
- Xác nhận chỉ một task chạy trong khoảng lock còn hiệu lực.
- Xác nhận task không có lock bị skip theo behavior mong đợi.
- Giả lập node chết hoặc lockAtMostFor hết hạn.
- Xem task thứ hai có thể thực hiện ở lần schedule sau.
- Kiểm tra clock và lockAtMostFor không quá ngắn.

### 35.1. Không chỉ test annotation hiện diện

Một test reflection thấy @SchedulerLock không chứng minh kết nối lock store, AOP/proxy và scheduler thực sự phối hợp giữa hai nodes.

### 35.2. Không dùng Thread.sleep với ngưỡng tuyệt đối nhỏ

Các test dựa vào sleep 100 ms rồi assert chính xác race order dễ flaky trên CI. Dùng latches, clocks có kiểm soát và thời gian bảo vệ đủ biên.

### 35.3. Kiểm tra gọi method qua proxy

Nếu test trực tiếp gọi method của object tự tạo bằng new, có thể bỏ qua sự tích hợp scheduler locking. Test cần đi qua Spring context/proxy tương ứng.

## 36. Test lỗi database và Redis

Khi lock store không hoạt động:

- Worker không nên tự giả định có độc quyền.
- Scheduler có thể skip/fail theo chính sách.
- Outbox state vẫn là nguồn để recovery.
- Error phải được quan sát.
- Không tự chuyển sang gửi không lock nếu điều đó tạo duplicate risk.

### 36.1. Database unavailable

Nếu không claim được row, worker **không nên gọi SMTP** trên danh sách jobs chỉ được đọc nhưng chưa có ownership.

### 36.2. Lock provider unavailable

Nếu ShedLock không acquire được vì store lỗi, một “fail open” tự chế có thể khiến các nodes cùng chạy. Cần chính sách failure rõ, ưu tiên không thực hiện công việc cần độc quyền khi không chứng minh được lock.

### 36.3. Redis failover

Với Redis lock, kiểm thử TTL, release token, renewal và tình huống owner cũ tiếp tục chạy. Các kết quả test phải dẫn đến thiết kế ownership/recovery thực tế, không chỉ xác minh SET NX PX trả OK.

## 37. Tối ưu hóa số worker và lease duration

Các thông số liên quan:

| Tham số | Ảnh hưởng |
| --- | --- |
| **Worker threads** | Số attempts SMTP đồng thời |
| **Batch size** | Số jobs claim mỗi lượt |
| **Lease duration** | Cửa sổ owner hợp lệ |
| **Heartbeat interval** | Tần suất renew lease |
| **SMTP timeouts** | Giới hạn chờ các thao tác network |
| **Retry backoff** | Mức tải khi provider lỗi |
| **Schedule interval** | Độ trễ tìm job mới |
| **Provider rate limit** | Giới hạn throughput |
| **Oldest pending SLA** | Mức chậm nghiệp vụ chấp nhận |

### 37.1. Lease không nên quá ngắn

Nếu send p99 mất 20 giây, batch có nhiều messages hoặc worker có thể bị pause, lease 5 giây dễ tạo reclaim không mong muốn.

### 37.2. Lease quá dài cũng có hại

Nếu worker chết ngay sau claim và lease kéo dài một giờ, job có thể bị kẹt một giờ trước khi worker khác phục hồi. Chọn lease dựa trên worst-case và heartbeat thay vì một giá trị khổng lồ.

### 37.3. Heartbeat là sự đánh đổi

Heartbeat giúp kéo dài lease khi làm việc bình thường nhưng tăng I/O database/Redis. Nó không ngăn tuyệt đối duplicate side effects; cần watchdog, deadlines và state transitions.

### 37.4. Batch nhỏ có thể có throughput tốt hơn

Khi mỗi batch claim nhiều hơn khả năng xử lý trước expiration, hệ thống phát sinh reclaim, duplicate và contention. Batch vừa với capacity thường dễ vận hành hơn batch cực lớn.

## 38. So sánh các chiến lược

| Tiêu chí | ShedLock scheduler | DB row claim SKIP LOCKED | Redis lease |
| --- | --- | --- | --- |
| Phạm vi phổ biến | Một scheduled execution | Từng mail job | Theo lock key |
| Có lịch sử job? | Không | Tự lưu trong outbox | Không tự có |
| Cho nhiều worker xử lý job khác nhau? | Không nếu khóa toàn dispatcher gửi | Có | Có nếu key theo job, nhưng tốn quản lý |
| Khôi phục sau crash? | Sau lock timeout | Sau lease expiry/recovery | Sau TTL |
| Sử dụng transaction DB? | Lock store riêng | Có, claim ngắn | Không gắn transaction DB |
| Kiểm tra stale owner? | Cần thiết kế thêm | Token/version trong state update | Token + fencing nếu nguồn đích hỗ trợ |
| Exactly-once SMTP? | Không | Không | Không |
| Phù hợp khi | Chỉ một scheduler task | Outbox parallel workers | Điều phối riêng có Redis |
| Nguồn sự thật về SENT/RETRY? | Không | Outbox database | Không |

### 38.1. Không có một giải pháp đúng cho mọi hệ thống

Ứng dụng ít mail, một cron batch ngắn có thể bắt đầu bằng ShedLock. Hệ thống giao dịch với tải lớn thường cần outbox và atomic per-job claim. Redis có thể phù hợp khi đã có hạ tầng/case use riêng, nhưng không tự đơn giản hơn nếu state nghiệp vụ vẫn ở SQL.

### 38.2. Chọn theo correctness, không theo tên thư viện

Điều quan trọng là test được các invariant: chỉ owner hợp lệ được update row, không gửi trước commit, không mất job sau crash, retry đúng policy và quan sát unknown outcome.

## 39. Những anti-pattern cần tránh

| Anti-pattern | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ dùng @Scheduled trên mọi node | Cùng job được đọc/gửi trùng | Distributed coordination |
| Dùng synchronized giữa nhiều JVM | Không khóa được các node khác | DB/lock store chung |
| SELECT PENDING rồi gửi ngay | Race condition | Atomic claim |
| UPDATE PROCESSING không WHERE status | Nhiều owner thành công | Conditional update + affected rows |
| Claim nhưng không lưu token/version | Stale worker có thể update | Owner token/fencing |
| Giữ transaction trong SMTP send | Row locks/DB connections kéo dài | Claim/commit trước send |
| Không có lease expiry | Job kẹt sau crash | Lease/recovery |
| Lease quá ngắn | Hai workers cùng gửi | Bound execution/renewal |
| Batch vượt năng lực | Nhiều leases hết trước xử lý | Claim gần thời điểm send |
| ShedLock lockAtMostFor quá nhỏ | Scheduled executions overlap | Thiết kế duration phù hợp |
| Dùng ShedLock thay durable outbox | Có thể mất mail khi crash | Outbox/broker bền vững |
| Redis DEL không kiểm tra token | Xóa khóa owner mới | Compare-and-delete |
| Lock Redis không TTL | Hệ thống kẹt khi owner chết | TTL và recovery |
| Tưởng Redlock bảo đảm exactly once | Vẫn có stale owner/SMTP window | Fencing/reconciliation |
| Mark SENT khi enqueue async | SMTP chưa chạy | Ack theo actual submit result |
| Retry mọi timeout ngay lập tức | Duplicate sau DATA | UNKNOWN_OUTCOME policy |
| Coi Message-ID là idempotency guarantee | Relay có thể nhận message lặp | Domain dedup/reconciliation |
| Heartbeat vô hạn | Worker treo giữ lease mãi | Overall deadline/watchdog |
| Gắn job ID vào metric labels | High cardinality/PII | Low-cardinality tags |
| Không test concurrency trên DB thật | Bỏ sót lock semantics | PostgreSQL integration test |
| Cho worker fail open khi lock store lỗi | Dễ gửi trùng | Không gửi khi không có ownership |

## 40. Câu hỏi thường gặp

**1. Distributed lock có cần khi ứng dụng chỉ chạy một node không?**

Nếu chắc chắn chỉ một process xử lý và không có cạnh tranh từ nhiều worker threads, có thể chưa cần distributed scheduler lock. Nhưng atomic claim/state machine vẫn hữu ích cho retry/restart và khi mở rộng nhiều instances.

**2. @Scheduled có tự bảo đảm chỉ một node chạy không?**

Không. Mỗi instance có scheduler riêng.

**3. synchronized có giải quyết được không?**

Không giữa các JVM khác nhau. Nó chỉ khóa những thread cùng chia sẻ monitor trong process.

**4. ShedLock dùng để làm gì?**

Thường dùng để tránh scheduled task cùng tên chạy đồng thời trên nhiều instances khi chúng dùng cùng lock store.

**5. ShedLock có tự xếp hàng những scheduled runs bị skip không?**

Không nên giả định. Lần chạy không lấy được lock thường bị bỏ qua, không phải giữ để thực hiện sau.

**6. lockAtMostFor có tự hủy method sau thời hạn không?**

Không. Đó là giới hạn giữ khóa trong store, không phải cancellation của method đang chạy.

**7. Vì sao ShedLock không thay thế outbox claim?**

Scheduler lock có thể chỉ bảo vệ bước lấy/enqueue việc. Nếu các jobs chưa được claim bền vững, worker khác vẫn có thể xử lý trùng sau khi khóa thả.

**8. SKIP LOCKED có tác dụng gì?**

Nó giúp transaction lấy các rows chưa bị transaction khác khóa, phù hợp cho nhiều worker cùng claim queue jobs.

**9. Tại sao không giữ SELECT FOR UPDATE lock cho đến khi gửi xong?**

Vì SMTP là network side effect có thể rất chậm và không rollback theo transaction DB; giữ transaction mở gây contention/timeout.

**10. Lease là gì?**

Là quyền sở hữu có hạn. Khi lease hết, job có thể được worker khác reclaim theo policy.

**11. Vì sao cần claim_token và claim_version?**

Để phân biệt owner hiện tại và ngăn stale owner update state khi job đã được reclaim.

**12. Fencing có ngăn SMTP gửi trùng hoàn toàn không?**

Không. SMTP relay thông thường không xác minh token/version của outbox; fencing chỉ có hiệu lực ở nguồn đích thực sự kiểm tra nó.

**13. Có nên heartbeat lease không?**

Có thể khi job lâu và có tiến độ đáng tin. Nhưng renewal phải kiểm tra owner/token/version và không chạy vô hạn khi worker bị treo.

**14. Redis SET NX PX có đủ an toàn không?**

Nó tạo atomic acquisition có TTL trong một Redis instance, nhưng vẫn có các vấn đề failover, stale owner và external side effects. Cần hiểu fault model và chính sách recovery.

**15. Vì sao không DEL lock Redis trực tiếp?**

Vì khóa có thể đã hết TTL và được owner khác lấy. Compare token rồi delete giúp tránh xóa nhầm khóa của chủ mới.

**16. Redlock có bảo đảm gửi email exactly once không?**

Không. Nó không biến SMTP submit thành transaction đồng nhất với database/outbox.

**17. Outbox có tự ngăn email trùng không?**

Nó giúp lưu bền ý định gửi và giảm duplicate event bằng unique keys, nhưng khi SMTP accept rồi worker crash, retry vẫn có thể tạo email trùng.

**18. Message-ID có phải idempotency key được SMTP tôn trọng không?**

Không có bảo đảm tổng quát như vậy. Không dựa vào Message-ID để chứng minh relay sẽ bỏ message trùng.

**19. Gửi email thành công có nghĩa đã đến inbox chưa?**

Không. Nó là kết quả SMTP submission phía client; delivery/bounce/read cần tín hiệu downstream riêng.

**20. Nếu lease hết ngay khi đang send thì sao?**

Worker khác có thể reclaim job. Worker cũ có thể vẫn đang send; CAS bảo vệ update DB nhưng không undo SMTP. Cần chọn lease, heartbeat, deadlines và duplicate policy phù hợp.

**21. Batch size nên chọn bao nhiêu?**

Theo concurrency, thời gian mỗi send, lease duration và quota; không claim nhiều hơn khả năng xử lý trong cửa sổ ownership.

**22. Khi dùng nhiều SMTP providers, khóa có cần theo provider không?**

Per-job ownership vẫn theo mail event; quota/concurrency có thể theo provider/account. Đừng dùng global lock thay rate limiter khi có quota độc lập.

**23. Redis lock và DB outbox có thể dùng chung không?**

Có thể, nhưng thêm hai hệ thống phối hợp cần xử lý inconsistency. Nếu relational DB đã giữ outbox, atomic row claim thường là điểm bắt đầu đơn giản hơn.

**24. Test cạnh tranh bằng H2 có đủ không?**

Không nên giả định tương đương PostgreSQL SKIP LOCKED. Nên dùng PostgreSQL thực trong integration tests nếu production phụ thuộc semantics đó.

**25. Nên alert gì để phát hiện distributed lock lỗi?**

Expired leases tăng, lost ownership, pending age, lock acquisition failures, retry backlog, unknown outcomes và sự chênh giữa claimed jobs với SMTP attempts/completions.

## 41. Ghi nhớ về distributed lock cho worker gửi mail

**Distributed lock là cơ chế phối hợp nhiều tiến trình, không phải bảo đảm gửi email đúng một lần.** Với Spring Framework Mail chạy theo lịch, hãy xác định chính xác phạm vi cần độc quyền: **ShedLock** có thể hữu ích để tránh nhiều node chạy cùng một scheduled task, còn **atomic per-job claim** bằng database row locks/conditional updates phù hợp hơn khi nhiều worker cần xử lý các mail outbox jobs khác nhau song song.

Nếu dùng PostgreSQL, một transaction ngắn với **FOR UPDATE SKIP LOCKED** có thể chọn và claim jobs; sau đó commit trước khi gọi **JavaMailSender.send(...)**. Lưu **claim_token, claim_version, claim_until** và kiểm tra ownership khi renew hoặc cập nhật SENT/RETRY_WAIT/FAILED. Khi lease hết, stale worker phải bị từ chối cập nhật trạng thái; nhưng đừng lầm tưởng fencing có thể ngăn SMTP relay nhận message đã gửi.

Với Redis, một lock cần atomic acquisition, TTL và release theo owner token; vẫn phải xử lý worker pause, failover và stale ownership. Với mọi cơ chế, hãy cấu hình timeout, batch size, concurrency, retry/backoff, recovery và telemetry phù hợp. Đặc biệt, **SMTP có thể đã chấp nhận DATA nhưng worker crash trước khi database ghi SENT**, nên hệ thống phải có chính sách **UNKNOWN_OUTCOME**, idempotent business events và đối soát khi cần.

Mục tiêu đúng không phải “có khóa là không bao giờ trùng”, mà là **không xử lý đồng thời cùng job trong điều kiện bình thường, phục hồi sau lỗi, giữ đúng ownership của state và quản lý minh bạch nguy cơ duplicate side effect**. Một thiết kế tốt phải đo được, kiểm thử được và mở rộng được khi số worker tăng.
