# Dừng lịch gửi an toàn khi bảo trì

Một ứng dụng sử dụng **Spring Framework Mail** có thể vận hành nhiều loại email theo lịch: hóa đơn hằng ngày, nhắc hạn thanh toán, thông báo khuyến mại, báo cáo định kỳ hoặc email xác minh chỉ còn giá trị trong vài phút. Khi cần bảo trì ứng dụng, database, SMTP relay hoặc hạ tầng mạng, việc “dừng gửi” tưởng như chỉ cần tắt `@Scheduled`. Nhưng nếu làm vậy, một số worker vẫn có thể đang gửi, một số message đã rời hàng đợi, nhiều lịch lặp có thể không được tạo trong thời gian dừng, và những job quá hạn có thể đổ dồn ra SMTP provider ngay khi hệ thống khởi động lại.

**Dừng lịch gửi an toàn khi bảo trì** cần là một quy trình có trạng thái, áp dụng trên toàn bộ instances, xử lý các submission đang diễn ra và có chính sách tiếp tục sau bảo trì. Dừng lịch không đồng nghĩa hủy email, không đồng nghĩa thu hồi thư đã được SMTP server chấp nhận và cũng không bảo đảm provider sẽ dừng giao những thư đã nằm trong hàng đợi của họ.

Bài học trình bày cách thiết kế **pause → drain → maintenance → resume** trong một hệ thống Spring Boot/Spring Mail có scheduler, worker, transactional outbox và nhiều replicas. Nội dung gồm mô hình trạng thái, cơ chế chặn atomic claim ở database, graceful shutdown, quản lý thư đang gửi, xử lý kết quả `UNKNOWN`, chính sách catch-up, kiểm thử và runbook vận hành.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt dừng **tạo lịch**, dừng **claim job**, dừng **SMTP submission** và hủy một lịch gửi.
2. Giải thích vì sao `@Scheduled` bị tắt trên một pod chưa bảo đảm toàn hệ thống ngừng gửi.
3. Thiết kế cờ bảo trì bền vững và dùng chung giữa các instances.
4. Chặn atomic claim sau khi một lệnh pause được commit.
5. Xác định tiêu chí **drained**: không còn worker nào đang gửi hoặc có trạng thái chưa được phân giải.
6. Áp dụng graceful shutdown khi triển khai hoặc bảo trì.
7. Giữ nguyên outbox, retry deadline, message key và lịch sử attempt khi tạm dừng.
8. Phân loại email `PENDING`, `RETRY_WAIT`, `SENDING`, `SMTP_ACCEPTED` và `UNKNOWN` trong thời gian bảo trì.
9. Khôi phục lịch sau downtime mà không tạo trùng recurring occurrences.
10. Xử lý các job đã quá hạn, hết hạn hoặc không còn đủ điều kiện khi resume.
11. Kết hợp pause toàn cục với pause theo provider, tenant hoặc loại email.
12. Kiểm thử race giữa lệnh pause, claim, SMTP submission và database commit.

## 2. Bối cảnh: có những điểm nào có thể phát sinh email?

Một hệ thống thực tế thường có nhiều thành phần chạy song song:

```text
                    Business events
                          |
                          v
             Scheduled job / Outbox writer
                          |
                          v
                 Database outbox
                          |
                     Due-job poller
                          |
                          v
                  Dispatcher / claim
                          |
                     Queue / worker
                          |
                          v
                   MIME renderer
                          |
                          v
                   JavaMailSender
                          |
                          v
                    SMTP provider
                          |
                          v
               Recipient mail systems
```

Bên cạnh đó có thể có:

- `@Scheduled` tạo email báo cáo hằng ngày.
- Quartz hoặc Spring Integration poller tìm job đến hạn.
- RabbitMQ/Kafka consumers xử lý email commands.
- REST endpoint gửi email ngay khi người dùng thao tác.
- Retry worker xử lý các job thất bại.
- Nhiều application pods cùng truy cập một outbox.
- Provider tự retry việc giao email sau khi đã nhận submission.

**Một nút “Pause scheduler” chỉ kiểm soát được những luồng đã thực sự được nối vào cơ chế pause.** Nếu code còn đường gọi `JavaMailSender.send(...)` trực tiếp ngoài dispatcher, phải xác định đường đó có nằm trong phạm vi bảo trì hay không.

### 2.1. Định nghĩa phạm vi trước khi thao tác

Cần trả lời rõ:

- Dừng **mọi email** hay chỉ email marketing?
- Dừng theo **SMTP provider**, **tenant**, **region** hay toàn hệ thống?
- Cho phép tạo yêu cầu mới nhưng chưa gửi, hay tạm từ chối request?
- Đang gửi dở có được hoàn tất không?
- Email được provider accepted trước thời điểm pause có tiếp tục được giao không?
- Sau resume, gửi bù toàn bộ hay bỏ những thông báo đã quá hạn?

Không có một chế độ dừng phù hợp với mọi mục đích bảo trì.

## 3. Bốn thao tác thường bị gọi chung là “dừng lịch”

| Thao tác | Tác động chính | Không tự làm được |
|---|---|---|
| **Pause schedule creation** | Không tạo thêm recurring jobs mới | Không ngăn job đã tồn tại được gửi |
| **Pause dispatch/claim** | Không cho worker nhận thêm job đến hạn | Không dừng submission đã bắt đầu |
| **Drain active submissions** | Cho các attempt đang chạy kết thúc, chờ đến mức an toàn | Không thu hồi email đã được relay chấp nhận |
| **Cancel scheduled job** | Hủy một email/lịch cụ thể chưa thực hiện | Không thay thế pause toàn hệ thống |

Ví dụ một lịch có 500 job `PENDING`, trong đó 10 job đã được claim:

- Tắt cron tạo lịch mới: 500 job hiện có vẫn có thể được dispatcher xử lý.
- Dừng poller: 10 job đang `SENDING` vẫn có thể gọi SMTP.
- Pause dispatch và drain: 490 job không bị claim mới; 10 job có thời gian kết thúc/được xử lý trạng thái.
- Cancel: thay đổi nghiệp vụ của một hoặc nhiều job, không phải một biện pháp bảo trì tạm thời.

**Pause ≠ Cancel ≠ SMTP delivery stop.** Phân biệt ngay từ API, cơ sở dữ liệu và giao diện vận hành.

## 4. Mục tiêu an toàn và những bảo đảm có thể cam kết

Một thiết kế bảo trì hợp lý đặt ra các bất biến:

1. Khi **pause gate** được commit, các giao dịch claim bắt đầu **sau đó** không nhận job mới trong phạm vi bị pause.
2. Những job chưa claim vẫn được lưu bền vững, không tự chuyển thành `FAILED` hoặc `CANCELLED`.
3. Attempt đã bắt đầu có trạng thái và lịch sử rõ ràng.
4. Không gửi lại job đã `SMTP_ACCEPTED` chỉ vì một lần restart.
5. Không tự retry các attempt có kết quả `UNKNOWN` nếu có nguy cơ relay đã nhận email.
6. Lệnh resume không tạo hai email logic cho cùng một business event/recurring occurrence.
7. Chỉ job còn hợp lệ về deadline, consent, token và recipient policy mới được gửi bù.
8. Quá trình bảo trì có audit: ai pause/resume, khi nào, vì sao và trong phạm vi nào.

### 4.1. Phân biệt PAUSED và DRAINED

- **PAUSED:** điều khiển claim đã bị chặn; **có thể vẫn còn submission đang chạy**.
- **DRAINING:** chờ các submission/attempt đã bắt đầu hoàn thành hoặc được đưa vào trạng thái cần đối soát.
- **DRAINED:** không còn lượt gửi đang chạy trong phạm vi mà ứng dụng kiểm soát, theo các nguồn đo/ownership được định nghĩa; trạng thái chưa rõ được ghi nhận riêng.
- **RESUMED:** cho phép claim job mới trở lại.

Một phản hồi HTTP `200 PAUSED` không nên được mô tả là “không còn email nào đang gửi”. Nếu cần bảo đảm trước khi ngắt mạng SMTP, phải có bước drain và kiểm tra điều kiện hoàn tất.

### 4.2. Ranh giới không kiểm soát được

Sau SMTP `250` cuối tương ứng với submission thành công, email có thể đã nằm trong queue của provider. Bảo trì ứng dụng **không dừng provider chuyển email tới máy chủ đích**. Nếu nghiệp vụ cần thu hồi thông báo, phải dựa vào khả năng đặc thù của provider (nếu có) và vẫn không nên hứa có thể thu hồi mọi email.

## 5. Chiến lược pause phù hợp với loại bảo trì

| Tình huống | Chiến lược gợi ý | Điểm cần kiểm tra |
|---|---|---|
| Deploy phiên bản ứng dụng | Drain worker/pod, rolling update | Job đang claim, termination grace, idempotency |
| Bảo trì database outbox | Pause claim, drain, dừng writer/dispatcher theo kế hoạch | Không để commit dở, backup/migration |
| Thay đổi SMTP credential | Pause profile, drain, thay sender/secret, smoke test | Active AUTH sessions, TLS, quyền From |
| SMTP provider outage | Tạm pause route/provider hoặc circuit breaker | Retry backlog, UNKNOWN, rate limit |
| Bảo trì marketing campaign | Pause theo category/campaign | Consent và expiry trước resume |
| Bảo trì hệ thống lịch lặp | Pause materializer, vẫn lưu schedule definition | Missed occurrences, catch-up |
| Sự cố nghi gửi nhầm recipient | Emergency stop theo scope liên quan, drain/kiểm tra | Các đường gửi trực tiếp ngoài outbox |
| Nhà cung cấp nhận mail bảo trì | Pause route có tác động; không giả định các provider khác an toàn | Failover và domain verification |

Không dùng lệnh dừng một pod để thay cho pause toàn cục. Trong môi trường nhiều replicas, pod khác có thể tiếp tục gửi như bình thường.

## 6. Mô hình trạng thái mail job khi bảo trì

Một outbox có thể dùng:

```text
PENDING ────────────────> SENDING ───────> SMTP_ACCEPTED
   |                          |
   |                          +─────────> RETRY_WAIT
   |                          |
   |                          +─────────> DEAD_LETTER
   |                          |
   |                          +─────────> UNKNOWN
   |
   +── on pause: remain PENDING
   |
   +── if expired: EXPIRED
   |
   +── user cancellation: CANCELLED

RETRY_WAIT ─ on pause: remain RETRY_WAIT
```

**Pause là trạng thái điều khiển dispatcher**, không nhất thiết là trạng thái của từng email.

Tránh quét hàng triệu rows và đổi tất cả `PENDING` thành `PAUSED` nếu chỉ cần chặn worker. Cách đó:
- làm tăng số writes/locks;
- khiến resume tốn kém;
- làm mất ý nghĩa của trạng thái gốc;
- khó phân biệt job do user pause riêng với pause toàn hệ thống.

Có thể tạo trạng thái job `PAUSED_BY_USER` trong các sản phẩm có tính năng pause từng lịch, nhưng nó không thay thế cờ điều khiển hệ thống dùng khi bảo trì.

### 6.1. SMTP_ACCEPTED không thay đổi do pause

Không “rollback” job đã accepted về `PENDING` sau bảo trì. Một lần gửi lại có thể tạo bản trùng.

### 6.2. RETRY_WAIT giữ nguyên lịch retry

Nếu retry dự kiến lúc 10:05 nhưng bảo trì kéo dài đến 10:30:
- `next_attempt_at` có thể vẫn là 10:05;
- job đủ điều kiện khi resume;
- dispatcher phải áp dụng rate limit/backpressure thay vì xử lý ồ ạt;
- không tăng `attempt_count` chỉ vì job đã quá hạn trong thời gian pause.

### 6.3. UNKNOWN cần reconciliation

Một attempt timeout sau SMTP DATA có thể đã được provider nhận. Không dùng pause/resume như lý do reset nó về `PENDING`.

## 7. Vì sao một boolean trong bộ nhớ không đủ?

Cách triển khai dễ gặp:

```java
private volatile boolean maintenanceMode = false;

@Scheduled(fixedDelay = 1000)
void dispatch() {
    if (maintenanceMode) {
        return;
    }
    sendDueMails();
}
```

Vấn đề:
- Biến chỉ có tác dụng trên một process.
- Restart làm biến trở về giá trị mặc định.
- Trong cluster, pod A paused nhưng pod B vẫn gửi.
- Một worker đã vượt qua câu lệnh `if` có thể tiếp tục gửi.
- Tình huống pause xảy ra giữa `SELECT` và `UPDATE` có thể tạo job claim mới.
- Không có audit, ownership hoặc thông tin lý do bảo trì.

`volatile` chỉ giúp khả năng nhìn thấy giá trị giữa threads trong một JVM; nó **không tạo giao thức pause an toàn** xuyên nhiều workers và database transactions.

### 7.1. Feature flag bên ngoài có đủ không?

Feature flag tập trung có thể điều khiển nhiều pods, nhưng nếu mỗi worker cache flag vài giây:
- lệnh pause có độ trễ truyền;
- một số worker có thể claim trong thời gian chưa cập nhật;
- mất kết nối flag provider có thể dẫn tới fallback sai.

Nếu cần ranh giới chặt với persistence, kết hợp feature flag cho UX/triển khai và **gate được kiểm tra cùng transaction claim**. Xác định rõ hệ thống có fail-closed khi không đọc được trạng thái bảo trì hay không.

## 8. Bảng điều khiển pause bền vững

Ví dụ PostgreSQL:

```sql
CREATE TABLE mail_dispatch_control (
    scope VARCHAR(128) PRIMARY KEY,
    paused BOOLEAN NOT NULL DEFAULT FALSE,
    generation BIGINT NOT NULL DEFAULT 0,
    paused_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL,
    updated_by VARCHAR(128) NOT NULL,
    reason VARCHAR(256)
);

INSERT INTO mail_dispatch_control (
    scope, paused, generation, paused_at,
    updated_at, updated_by, reason
)
VALUES (
    'GLOBAL', FALSE, 0, NULL,
    CURRENT_TIMESTAMP, 'bootstrap', NULL
);
```

Các trường:
- `scope`: `GLOBAL`, hoặc `PROVIDER:transactional`, `TENANT:tenant-123`.
- `paused`: gate được bật/tắt.
- `generation`: số phiên bản giúp trace và phát hiện điều khiển đã thay đổi.
- `paused_at`: thời điểm bắt đầu pause gần nhất.
- `updated_by` và `reason`: dữ liệu audit cơ bản.

### 8.1. Không đặt mặc định “mất database thì cứ gửi”

Nếu worker không kiểm tra được control row hoặc database không khả dụng, **không được tự coi `paused=false`** rồi gọi SMTP. Với hệ thống bảo trì cần chặn gửi, policy phù hợp là fail closed tại bước claim.

Nếu job đã được claim trước khi DB hỏng, đó là một tình huống riêng về in-flight/UNKNOWN; cần xử lý theo runbook thay vì ngầm gửi tiếp mọi thứ.

### 8.2. Nhiều scopes

Nếu cần pause theo provider/tenant, cách đơn giản là mỗi scope có một row. Khi claim một job, policy phải xét tất cả scopes liên quan. Quy định thứ tự khóa nhất quán, ví dụ:
1. `GLOBAL`.
2. `PROVIDER:<providerKey>`.
3. `TENANT:<tenantId>`.

Không để các worker lấy khóa theo thứ tự khác nhau dẫn đến deadlock.

### 8.3. Khóa row toàn cục có đánh đổi throughput

Một gate row có khóa `FOR UPDATE` trong mỗi claim transaction sẽ **serialize các lượt claim**, có thể thành bottleneck khi workload lớn. Đây là lựa chọn đơn giản, dễ lý luận cho correctness. Với lưu lượng cao, có thể thiết kế generation/fencing protocol hoặc phân vùng claim gates theo scope, nhưng vẫn phải có bằng chứng rằng pause và claim tạo một ranh giới nhất quán.

Không bỏ atomicity chỉ vì một phép đọc boolean nhanh hơn.

## 9. Pause và claim phải được đồng bộ bằng transaction

Giả sử:

```text
Worker A                       Operator
   |                              |
   | read paused=false            |
   |                              | pause=true, commit
   | select due job               |
   | update SENDING               |
   |                              |
   v                              v
   SMTP submission continues after pause
```

Nếu đọc flag không có giao thức đồng bộ với claim, thông điệp mới vẫn có thể được claim sau thời điểm operator nghĩ pause đã hoàn tất.

### 9.1. Một phương án đơn giản: lock gate row

Mỗi claim transaction thực hiện:

```sql
BEGIN;

SELECT paused, generation
FROM mail_dispatch_control
WHERE scope = 'GLOBAL'
FOR UPDATE;

-- Nếu paused = TRUE:
--   COMMIT, không claim gì.

-- Nếu paused = FALSE, tiếp tục claim due jobs:
WITH next_jobs AS (
    SELECT message_key
    FROM scheduled_email
    WHERE status IN ('PENDING', 'RETRY_WAIT')
      AND send_at <= CURRENT_TIMESTAMP
      AND next_attempt_at <= CURRENT_TIMESTAMP
    ORDER BY next_attempt_at, send_at, created_at
    FOR UPDATE SKIP LOCKED
    LIMIT :batchSize
)
UPDATE scheduled_email e
SET status = 'SENDING',
    attempt_count = attempt_count + 1,
    lease_token = :leaseToken,
    lease_expires_at = :leaseExpiresAt,
    updated_at = CURRENT_TIMESTAMP
FROM next_jobs n
WHERE e.message_key = n.message_key
RETURNING e.message_key, e.attempt_count,
          e.lease_token;

-- Insert attempt history tương ứng trong cùng transaction.
COMMIT;
```

Đây là **skeleton**: ứng dụng phải kiểm tra `paused` trước khi thực hiện phần claim. Không chạy cả script một mạch bất kể giá trị flag.

### 9.2. Lệnh pause ghi cùng gate row

```sql
BEGIN;

UPDATE mail_dispatch_control
SET paused = TRUE,
    generation = generation + 1,
    paused_at = CURRENT_TIMESTAMP,
    updated_at = CURRENT_TIMESTAMP,
    updated_by = :operatorId,
    reason = :reason
WHERE scope = 'GLOBAL';

COMMIT;
```

Vì claim transaction đang giữ khóa row `GLOBAL`, lệnh pause sẽ đợi claim đang diễn ra commit. Ngược lại, sau khi pause đã commit, các claim tiếp theo sẽ thấy `paused=true` và không nhận job mới.

**Bảo đảm ở đây là “không claim mới sau điểm commit của pause”**, không phải “không có SMTP call nào đang chạy”.

### 9.3. Vì sao không giữ lock tới khi SMTP hoàn tất?

Không nên giữ database transaction/row lock qua lời gọi SMTP có thể kéo dài nhiều giây hoặc timeout. Cách làm đúng:
1. Transaction claim ngắn, commit.
2. SMTP submission ngoài transaction.
3. Transaction ngắn để ghi outcome.

Đó là lý do **pause + drain** luôn cần hai bước: chặn claim mới và quản lý những attempt đã rời transaction claim.

### 9.4. Paused không có nghĩa xóa job khỏi due query

Job còn `PENDING` hoặc `RETRY_WAIT` vẫn nằm trong DB với mốc `send_at`/`next_attempt_at`. Gate ngăn việc claim. Khi resume, dispatcher lại xét tính hợp lệ và lịch đến hạn.

## 10. Cài đặt gate bằng Spring service

Ví dụ contract:

```java
package com.example.mail.maintenance;

public record DispatchGate(
    boolean paused,
    long generation
) {}

public interface DispatchControlRepository {

    // SELECT ... FOR UPDATE, tham gia transaction hiện tại.
    DispatchGate lockGlobal();

    // UPDATE gate row trong transaction.
    void updateGlobal(
        boolean paused,
        String operatorId,
        String reason
    );
}
```

Coordinator:

```java
package com.example.mail.maintenance;

import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class MailClaimCoordinator {

    private final DispatchControlRepository controls;
    private final ScheduledMailRepository mailRepository;

    public MailClaimCoordinator(
            DispatchControlRepository controls,
            ScheduledMailRepository mailRepository) {
        this.controls = controls;
        this.mailRepository = mailRepository;
    }

    @Transactional
    public List<ClaimedMail> claimDue(int maxJobs) {
        DispatchGate gate = controls.lockGlobal();

        if (gate.paused()) {
            return List.of();
        }

        // Repository dùng atomic SELECT ... FOR UPDATE SKIP LOCKED
        // và ghi mail attempts trong cùng transaction.
        return mailRepository.claimDueBatch(maxJobs);
    }
}
```

`ScheduledMailRepository` và `ClaimedMail` là interfaces/model do ứng dụng định nghĩa, không phải API có sẵn trong Spring Mail. Repository phải có implementation dùng database thật.

### 10.1. Pause service cùng transaction discipline

```java
package com.example.mail.maintenance;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class MailMaintenanceService {

    private final DispatchControlRepository controls;

    public MailMaintenanceService(
            DispatchControlRepository controls) {
        this.controls = controls;
    }

    @Transactional
    public void pauseGlobal(
            String operatorId,
            String reason) {

        controls.updateGlobal(true, operatorId, reason);
    }

    @Transactional
    public void resumeGlobal(
            String operatorId,
            String reason) {

        controls.updateGlobal(false, operatorId, reason);
    }
}
```

Điều kiện:
- Cả hai phương thức phải đi qua Spring transaction proxy thực sự.
- Không gọi self-invocation rồi tưởng `@Transactional` tự được áp dụng.
- Repository phải dùng cùng data source/transaction manager với outbox claim.
- Chỉ operator/service được phân quyền mới gọi pause/resume.
- Cần audit độc lập với row trạng thái hiện tại nếu yêu cầu lưu lịch sử nhiều lần bảo trì.

### 10.2. “Pause thành công” phải có nghĩa cụ thể

API `POST /ops/mail/pause` có thể trả:
- `PAUSED`: gate được commit, không còn claim mới.
- `DRAINING`: vẫn có active attempts.
- `DRAINED`: đã thỏa tiêu chí quiescence của scope.

Không gọi cả ba trạng thái này là “mail stopped” vì mức bảo đảm khác nhau.

## 11. DRAIN: chờ những lượt gửi đang diễn ra

Khi pause được commit, vẫn có những job đã claim và đang:

```text
SENDING:
   |
   +--> render MIME
   +--> connect SMTP
   +--> TLS handshake / AUTH
   +--> MAIL FROM / RCPT TO / DATA
   +--> wait for server reply
   +--> persist outcome
```

Nếu ngắt process đúng giữa DATA, server có thể đã nhận message nhưng client không thấy kết quả. Việc dừng gấp có thể tạo nhiều attempt `UNKNOWN` và tăng rủi ro duplicate khi recover.

### 11.1. Quy trình drain điển hình

1. Commit pause gate.
2. Tạm ngừng các dispatcher/consumer mới (hoặc để chúng chạy nhưng claim trả rỗng).
3. Đợi các worker đã claim hoàn tất trong một khoảng chờ có giới hạn.
4. Quan sát `active_submissions`, `SENDING` và số leases còn sống.
5. Nếu còn attempts chậm, điều tra và quyết định gia hạn drain hay đưa vào trạng thái cần reconciliation.
6. Chỉ sau đó mới ngắt SMTP network/rotate credential/terminate worker.
7. Lưu bằng chứng và trạng thái cuối của đợt bảo trì.

### 11.2. Phải định nghĩa thế nào là drained

Một tiêu chí hữu ích cho scope:
- không còn submission task thực sự đang chạy trên các worker instances được quản lý;
- các kết quả đã hoàn tất được persist;
- những attempts không rõ kết quả được liệt kê và xử lý theo `UNKNOWN`;
- không có worker cũ đang giữ quyền gửi mà operator chưa kiểm soát.

Chỉ query:

```sql
SELECT COUNT(*)
FROM scheduled_email
WHERE status = 'SENDING';
```

là một tín hiệu, **chưa chắc đủ**: row có thể bị kẹt sau process crash, hoặc hệ thống có send task ngoài outbox. Cần đối chiếu lease ownership, health/worker heartbeat và in-flight counters.

### 11.3. Drain timeout

Nếu có một SMTP call treo, không nên chờ vô hạn. Phải có:
- SMTP connect/read/write timeouts;
- tổng deadline phù hợp cho một attempt;
- lease renewal hoặc thời gian lease đủ lớn;
- thời hạn drain;
- chính sách escalation nếu không hoàn tất.

Không ghi `FAILED` chắc chắn chỉ vì operator buộc dừng một tiến trình đang gửi; outcome có thể không biết.

## 12. Chốt ranh giới “không gửi mới” trong khi drain

Một cơ chế kiểm tra gate ngay trước `send(...)` có ích:

```java
if (maintenanceGuard.isPausedFor(job)) {
    // Không gọi SMTP; trả job về trạng thái chờ phù hợp,
    // vẫn giữ nguyên attempt history và lease discipline.
    return;
}

mailSender.send(mime);
```

Nhưng đây **không phải chứng minh tuyệt đối** không có SMTP sau pause:

```text
Worker: read paused=false
Operator: pause commit
Worker: call mailSender.send(...)
```

Vẫn có race giữa việc đọc flag và side effect không thể rollback. Cách xử lý:
- gate atomic ở bước claim;
- định nghĩa những job claim trước pause là in-flight;
- drain tất cả workers trước thao tác bảo trì thật;
- nếu yêu cầu cực kỳ nghiêm ngặt, triển khai permit/handshake hoặc fencing phối hợp gửi, không chỉ một câu `if`;
- giới hạn rõ phạm vi bảo đảm trong runbook.

**Đừng hứa “không có email nào được gửi sau API pause trả về” nếu vẫn cho phép các in-flight jobs hoàn tất.** Hãy dùng cụm “đã chặn claim mới; đang drain” cho đúng.

## 13. Không dùng @ConditionalOnProperty như runtime pause switch

Ví dụ:

```java
@ConditionalOnProperty(
    name = "app.mail.dispatch.enabled",
    havingValue = "true"
)
@Component
public class DueMailScheduler {
    // ...
}
```

`@ConditionalOnProperty` thường được đánh giá khi Spring context được tạo. Việc đổi config file hoặc environment variable **không mặc nhiên làm bean hiện có dừng chạy**.

Đây là lựa chọn tốt cho:
- vô hiệu hóa worker khi deploy một loại instance chỉ phục vụ API;
- cấu hình static theo môi trường;
- tách app role.

Nhưng nó **không phải công tắc pause/resume runtime có ranh giới nhất quán** trên cluster.

### 13.1. @Scheduled chỉ là trigger kỹ thuật

```java
@Scheduled(fixedDelayString = "${app.mail.dispatch.delay-ms:1000}")
public void dispatch() {
    coordinator.claimAndDispatch();
}
```

Một cron/fixedDelay trigger có thể vẫn chạy trong maintenance và nhận danh sách rỗng do gate. Điều đó chấp nhận được nếu tốn rất ít tài nguyên. Có thể dừng trigger để giảm tải sau khi pause, nhưng correctness phải dựa vào gate bền vững, không chỉ lịch trigger.

### 13.2. Dừng một scheduled task bằng SchedulingConfigurer?

Spring hỗ trợ nhiều cách cấu hình scheduler hoặc quản lý lifecycle, nhưng hủy `ScheduledFuture`/endpoint trên một instance:
- không có tác dụng trên instance khác;
- có thể không chờ callback đang chạy hoàn tất;
- không ghi trạng thái durable để restart biết phải dừng;
- không xử lý in-flight SMTP.

Dùng task lifecycle management như một phần của shutdown, không thay thế pause control toàn cục.

## 14. Graceful shutdown trong Spring Boot

Khi deploy hoặc dừng ứng dụng:

1. Báo workload không còn sẵn sàng nhận **công việc mới** theo cơ chế thích hợp.
2. Chặn job claim mới trong phạm vi cần dừng.
3. Cho in-flight operations kết thúc có timeout.
4. Persist outcomes.
5. Đóng queue consumers, executor và resources.
6. Thoát process có kiểm soát.

### 14.1. HTTP graceful shutdown không tự dừng email worker

Spring Boot có cấu hình graceful shutdown cho web server:

```yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
```

Các setting này giúp lifecycle quản lý shutdown theo hỗ trợ của framework, nhưng **không bảo đảm mọi custom `@Scheduled` hoặc background email worker của ứng dụng sẽ drain đúng**.

Nếu bạn tự tạo `ExecutorService`, `Thread`, queue consumer hoặc scheduler:
- tham gia Spring lifecycle đúng cách;
- ngừng nhận job mới;
- chờ in-flight theo thời hạn;
- xử lý interruption;
- lưu trạng thái bền vững.

### 14.2. SmartLifecycle và controlled stop

Có thể thiết kế một component `SmartLifecycle` hoặc shutdown orchestrator để ngừng dispatcher và chờ worker pool. Tuy nhiên, nếu dùng đồng thời nhiều phases, phải xác định thứ tự:
- dispatcher dừng trước;
- active senders hoàn tất;
- persistence/connection pools còn hoạt động đủ lâu để ghi outcome;
- sau cùng mới đóng datasource/network dependencies.

Nếu database bị đóng trước khi worker persist submission result, các attempts có thể trở thành `UNKNOWN` dù SMTP đã nhận thư.

### 14.3. @PreDestroy không đủ để chờ tác vụ bất đồng bộ

`@PreDestroy` hữu ích để cleanup nhưng không nên chỉ gọi một flag rồi lập tức return nếu còn worker threads. Cần một cơ chế join/await termination có timeout, đồng thời tuân thủ thứ tự shutdown của Spring context.

Không kéo dài shutdown vô hạn làm orchestration platform buộc kill process.

## 15. Kubernetes rolling maintenance và preStop

Một deployment Kubernetes có thể gồm nhiều pods đang gửi email.

```text
Pod A -> worker/email outbox
Pod B -> worker/email outbox
Pod C -> worker/email outbox
             |
             v
          Database
             |
             v
          SMTP relay
```

Khi Kubernetes terminate pod A:
- pod B/C vẫn có thể claim nếu không có **global pause**;
- pod A có thể đang gọi SMTP;
- termination grace period có giới hạn;
- readiness không tự vô hiệu background `@Scheduled`;
- preStop hook chỉ chạy trong ngữ cảnh pod, không thay đổi global DB control nếu không được thiết kế.

### 15.1. Phân biệt pod drain và global pause

**Pod drain** dành cho rolling deployment:
- node/pod cụ thể ngừng claim;
- những pods khác tiếp tục xử lý;
- lease/worker ownership được quản lý;
- pod exit sau khi worker local hoàn tất.

**Global pause** dành cho bảo trì toàn bộ SMTP/database hoặc một đợt cần ngừng submission:
- mọi pods cùng tuân theo gate;
- in-flight trên tất cả pods phải được drain;
- chỉ resume sau kiểm tra hệ thống chung.

### 15.2. Termination grace period

Thời gian grace cần đủ cho attempt đang chạy hoặc timeout đã cấu hình, nhưng không nên kéo dài không giới hạn. Khi pod hết grace và bị kill giữa SMTP:
- không tự đánh dấu chắc chắn chưa gửi;
- chờ lease recovery và reconciliation;
- không resend mù.

### 15.3. Readiness không phải một kill switch cho scheduler

Cho readiness probe trả thất bại thường khiến service bị rút khỏi HTTP load balancer, **không bảo đảm thread định kỳ bên trong pod dừng chạy**. Cần điều khiển dispatcher riêng.

## 16. Bảo trì database và transactional outbox

Nếu chuẩn bị chạy migration/backup database:

1. Xác định cửa sổ bảo trì và loại thao tác DB.
2. Pause claim mới khi cần.
3. Đợi in-flight gửi xong và persist outcome.
4. Có thể ngừng tạo jobs mới, hoặc chuyển API sang chế độ từ chối/queue an toàn theo yêu cầu.
5. Chỉ sau khi đảm bảo writer/worker không còn thao tác schema liên quan mới chạy migration phá tương thích.
6. Sau bảo trì, kiểm tra schema, constraints, datasource và outbox consistency.
7. Resume có kiểm soát.

### 16.1. Không thể ghi job khi database unavailable

Nếu API vẫn nhận request rồi trả “đã xếp lịch” nhưng không thể persist outbox, job có thể bị mất. Chọn một trong hai:
- từ chối tạm thời với trạng thái phù hợp;
- ghi vào durable upstream khác đã được thiết kế, nếu có;
- chỉ trả thành công sau khi durable commit.

Không thay bằng một list trong bộ nhớ rồi coi nó có độ bền ngang database.

### 16.2. Migration có thể làm hỏng worker cũ

Nếu rolling migration thay cột/trạng thái outbox mà worker cũ vẫn chạy, nó có thể:
- không hiểu status mới;
- claim sai job;
- ghi outcome không tương thích.

Nên dùng chiến lược expand/contract schema, versioning và drain đúng thời điểm. Pause chỉ bảo vệ việc dispatch theo gate, không tự giải quyết mọi incompatibility giữa producer và consumer versions.

### 16.3. Khi DB outage sau SMTP accepted

Luồng:

```text
Worker                  SMTP relay              Database
   |--- DATA accepted ---->|
   |<------ 250 -----------|
   |                       |---- UPDATE outcome --> X
   |
   +-- cannot persist acceptance
```

Nếu worker crash, outbox có thể vẫn ở `SENDING`. Recovery phải xem đây là **kết quả chưa được lưu chắc chắn**, không tự gửi lại chỉ vì database chưa có `SMTP_ACCEPTED`.

## 17. Bảo trì SMTP provider hoặc xoay vòng credential

Khi thay host, TLS certificate, SMTP account hoặc credential:
- pause các jobs đi qua **provider/profile đó**;
- drain active sends sử dụng account cũ;
- chuẩn bị sender/profile mới;
- xác minh TLS hostname, CA chain, AUTH và verified From;
- chạy smoke test tới mailbox/sandbox được phép;
- bật gửi lại theo quota;
- giữ account cũ trong khoảng chuyển giao nếu cần xử lý kết nối/lượt gửi đã bắt đầu.

### 17.1. Đừng sửa JavaMailSender singleton khi đang được dùng

Không nên:

```java
sharedSender.setHost(newHost);
sharedSender.setUsername(newUser);
sharedSender.setPassword(newPassword);
```

trong lúc worker khác gửi. Cấu hình mutable có thể bị xen kẽ giữa các requests và account. Nếu cần thay đổi runtime, dựng profile/sender mới và chuyển ownership có kiểm soát sau khi drain hoặc theo cơ chế versioned registry.

### 17.2. Failover không phải pause

Chuyển job từ provider A sang B là một quyết định routing và delivery riêng. Chỉ được làm khi:
- B đã được verified domain/DKIM/SPF/DMARC alignment;
- quyền gửi/consent/suppression được giữ;
- quota B cho phép;
- attempt A chắc chắn chưa accepted hoặc có idempotency/reconciliation;
- không có `UNKNOWN` được resend mù.

Pause A không tự cấp quyền gửi qua B.

## 18. Pause theo scope: global, provider, category, tenant

Một hệ thống lớn có thể cần nhiều lớp điều khiển:

```text
GLOBAL gate
   |
   +--> PROVIDER:transactional
   |
   +--> PROVIDER:marketing
   |
   +--> CATEGORY:MARKETING
   |
   +--> TENANT:enterprise-42
```

Một job chỉ eligible nếu **tất cả scopes áp dụng cho job đều không bị pause**.

### 18.1. Xác định provider trước khi claim

Nếu pause theo provider, job phải có provider route được quyết định tại thời điểm claim hoặc trước đó. Nếu router đổi provider sau khi gate đã được kiểm tra, cần xác nhận gate của provider mới cũng được áp dụng.

### 18.2. Khóa theo thứ tự nhất quán

Ví dụ khi đọc control rows có khóa:
1. GLOBAL.
2. PROVIDER theo key chuẩn hóa.
3. CATEGORY.
4. TENANT.

Giữ thứ tự ở mọi worker/admin operations để giảm nguy cơ deadlock. Việc khóa nhiều rows tăng contention nên cần benchmark, nhưng không được làm mất bảo đảm rằng operator pause đã được tôn trọng.

### 18.3. Tenant có được tự pause không?

Một API tự phục vụ có thể cho tenant pause chiến dịch của chính họ, nhưng:
- backend xác định tenant từ authentication;
- không cho tenant A sửa global/provider controls;
- có rate limit và audit;
- không để một header của email nhận quyết định tenant;
- resume tenant riêng không được vượt qua global pause.

## 19. Retry, deadline và thời gian dừng dài

Giả sử:
- Email A đáng ra gửi lúc 09:00.
- Bảo trì từ 08:55 đến 10:30.
- Retry của email B đã tới hạn lúc 09:15.
- Email C chứa token sẽ hết hạn lúc 09:20.

Khi resume lúc 10:30:
- A có thể gửi bù nếu vẫn hữu ích.
- B có thể retry theo policy, có backoff/quota.
- C **không nên gửi** nếu token đã hết hạn.

### 19.1. Ba mốc thời gian phải tách biệt

| Trường | Ý nghĩa |
|---|---|
| `send_at` | Thời điểm sớm nhất để submit email theo lịch |
| `next_attempt_at` | Thời điểm sớm nhất được thử lại sau lỗi |
| `expires_at` | Giới hạn thời gian còn được phép gửi |

Tất cả các mốc thực thi này nên được lưu như **absolute instants** (ví dụ `TIMESTAMPTZ` trong PostgreSQL); timezone của lịch được giữ riêng nếu cần tính recurrence.

### 19.2. Pause không làm tăng attempt_count

Một job nằm ở `RETRY_WAIT` suốt 2 giờ bảo trì không đồng nghĩa đã thất bại thêm lần nữa. `attempt_count` chỉ tăng khi một attempt thật sự bắt đầu theo contract; không tăng theo số lần poller thấy paused.

### 19.3. Business retry deadline khác SMTP socket timeout

SMTP read timeout 10 giây không có nghĩa email có thể retry vô hạn mỗi 10 giây. Retry policy còn cần giới hạn:
- tổng số attempts;
- thời gian tối đa;
- deadline;
- provider rate limit;
- status `UNKNOWN`.

## 20. Khi resume: không gửi bù toàn bộ một cách mù quáng

Sau bảo trì, có thể có hàng chục nghìn jobs đã quá hạn. Nếu `paused=false` và 100 workers cùng khởi động, chúng có thể:
- dồn hàng nghìn kết nối vào SMTP provider;
- vượt quota/rate limit;
- tăng 421/451;
- gây retry storm;
- gửi các thông báo đã hết giá trị;
- tạo email trùng nếu old attempts chưa reconcile.

### 20.1. Chính sách backlog

Phân loại trước khi resume:

| Nhóm | Ví dụ | Hành động gợi ý |
|---|---|---|
| **Gửi bù hợp lệ** | Hóa đơn đã phát hành, vẫn cần gửi | Giữ job, điều tiết theo quota |
| **Hết hiệu lực** | OTP/reset link đã hết hạn | EXPIRED hoặc tạo flow mới hợp lệ |
| **Không còn consent** | Marketing user opt-out trong bảo trì | Suppress/cancel |
| **Đã được xử lý bên ngoài** | Provider accepted trước pause | Không resubmit |
| **UNKNOWN** | Timeout trước khi persist outcome | Reconcile |
| **Recurring missed runs** | Báo cáo ngày cũ | Theo catch-up policy |
| **Một phần deadline còn lại** | Nhắc sự kiện sắp diễn ra | Gửi nếu còn ý nghĩa, không quá hạn |

### 20.2. Resume theo từng đợt

Có thể:
1. Resume chỉ một provider/tenant canary.
2. Giới hạn worker concurrency.
3. Áp dụng rate limit và jitter.
4. Giám sát 4xx/5xx, timeout, lag và backlog.
5. Tăng throughput khi ổn định.
6. Mở rộng sang các scopes còn lại.

Thứ tự ưu tiên cần theo business criticality; không mặc định tất cả email cũ đều quan trọng như nhau.

### 20.3. Không “đẩy giờ gửi lên hiện tại” để xử lý backlog

Không cần sửa mọi `send_at` thành `now()`. Job đã quá hạn vốn đủ điều kiện theo query `send_at <= now`. Thay đổi hàng loạt send_at làm mất dữ liệu ý định, khó tính schedule lag và có thể gây tranh chấp database không cần thiết.

## 21. Lịch lặp, cron và khoảng thời gian bảo trì

Một bài toán khác: **không có outbox row nào được tạo** trong thời gian hệ thống tắt.

Ví dụ lịch:
> Gửi báo cáo mỗi ngày lúc 09:00 theo giờ người dùng.

Nếu ứng dụng dừng 3 ngày, chỉ dựa vào `@Scheduled` có thể làm **mất ba lần trigger**.

### 21.1. Tách schedule definition và occurrences

```text
recurring_schedule:
   scheduleId
   zoneId
   localTime
   recurrenceRule
   status
         |
         v
occurrence materializer
         |
         v
scheduled_email:
   scheduleId
   occurrenceDate
   sendAt
   status
```

Khi resume:
- tìm các occurrences chưa được materialize;
- áp dụng policy catch-up;
- insert với unique business key;
- chỉ gửi những occurrences còn hợp lệ;
- không tạo trùng khi materializer chạy lại.

### 21.2. Pausing materializer hay dispatcher?

Hai lựa chọn:
- **Chỉ pause dispatcher:** cron/materializer vẫn tạo jobs vào DB trong bảo trì, miễn DB còn khả dụng. Resume xử lý backlog.
- **Pause cả materializer:** cần catch-up để tái tạo những occurrences bị bỏ lỡ sau bảo trì.

Chọn theo loại bảo trì. Nếu DB downtime, materializer không thể persist, nên phải có logic tính bù.

### 21.3. Múi giờ và DST vẫn có hiệu lực

Lịch “09:00 mỗi ngày theo giờ Berlin” phải tiếp tục tạo đúng local occurrence sau DST. Không lấy `Instant` cuối rồi cộng 24 giờ cố định nếu contract là giờ địa phương. Sau downtime, tính ngày local/ZoneId và áp dụng gap/overlap policy.

### 21.4. Unique occurrence key

Ví dụ:

```text
tenantId | scheduleId | localDate | occurrenceSlot
```

Một unique constraint giúp hai materializer cùng chạy catch-up không tạo hai email logic cho cùng kỳ. Nếu policy cho phép hai occurrences trong ngày DST overlap, key cần phân biệt slot/offset.

## 22. Múi giờ không được thay đổi vì bảo trì

Một lịch đã được resolve:

```text
local: 2026-12-01T09:00
zone: Asia/Ho_Chi_Minh
send_at: 2026-12-01T02:00:00Z
```

Khi bảo trì từ 01:50Z tới 02:30Z:
- `send_at` vẫn là 02:00Z;
- khi resume 02:30Z, job đã quá hạn 30 phút;
- hệ thống có thể gửi bù nếu còn hợp lệ;
- audit ghi actual submission time tách với planned time.

Không chuyển thành `09:00 server timezone` khi restart và không tính lại một instant đã chốt chỉ vì server deploy ở khu vực khác.

### 22.1. Khi nào cần tính lại?

Chỉ khi business schedule được định nghĩa theo **wall time** và có thay đổi được phép, ví dụ:
- người dùng đổi timezone của lịch;
- recurrence rule thay đổi;
- quy định múi giờ được cập nhật và future occurrences chưa thực thi phải phản ánh luật mới.

Bảo trì không tự là lý do đổi semantics của lịch.

### 22.2. Catch-up không đồng nghĩa “cứ chạy cron một lần”

Nếu mất nhiều occurrences, một lần gọi `@Scheduled` sau restart có thể chỉ tạo job cho ngày hiện tại. Materializer cần đọc schedule definition và khoảng thời gian chưa được materialize, tránh dựa duy nhất vào trigger đang chạy.

## 23. QueueChannel, RabbitMQ và Kafka khi bảo trì

Không phải mọi hệ thống dùng SQL outbox trực tiếp. Có thể có:

```text
Business service -> Broker -> Mail consumer -> SMTP
```

Khi pause:
- có thể dừng consumer;
- giảm prefetch;
- ngừng ack/claim thêm messages;
- cho các deliveries đã nhận xử lý xong;
- duy trì backlog bền vững trên broker.

### 23.1. QueueChannel in-memory

`QueueChannel` mặc định trong Spring Integration có thể nằm trong bộ nhớ. Nếu app restart:
- các messages chưa xử lý có thể mất;
- drain chỉ xử lý messages đang trong queue và in-flight của process;
- không có đảm bảo durable chỉ vì tên có chữ “Queue”.

Nếu lịch gửi quan trọng, dùng outbox, persistent MessageStore hoặc broker bền vững với transaction/recovery được thiết kế đúng.

### 23.2. Broker consumer pause

Dừng hoặc pause broker listeners có thể ngăn nhận mới, nhưng:
- messages đã prefetch vẫn đang nằm trong consumer;
- ack/nack semantics khác nhau;
- Kafka offset commit và RabbitMQ delivery ack không giống nhau;
- in-flight SMTP không rollback được;
- restart có thể redeliver, tạo rủi ro duplicate.

Dùng contract của broker để drain, ack và replay; **không coi pause listener là đã chắc chắn không còn send**.

### 23.3. Không chuyển broker message sang DLQ chỉ vì maintenance

Bảo trì là trạng thái hệ thống, thường không phải lỗi dữ liệu. Nếu chỉ tạm dừng, nên để job trong queue/outbox. Dead letter dành cho trường hợp policy xác định không thể tiếp tục tự động hoặc hết retry budget.

## 24. Chuyển trạng thái in-flight khi lỗi hoặc bị kill

Một worker có thể chết ở nhiều thời điểm:

| Thời điểm chết | Khả năng SMTP accepted? | Cách recovery |
|---|---|---|
| Trước khi claim | Chưa | Job còn pending |
| Claim thành công, chưa bắt đầu gửi | Có thể chưa, nếu có bằng chứng rõ | Recovery theo lease/attempt log |
| Sau kết nối, trước DATA | Thường chưa có nội dung được accepted, nhưng cần bằng chứng protocol | Retry khi được phân loại an toàn |
| Trong DATA | Không chắc | Giữ `UNKNOWN` nếu không xác minh được |
| Sau end-of-DATA, mất response | Có thể đã accepted | `UNKNOWN`, reconciliation |
| Nhận `250` thành công, DB update lỗi | Có | Không resend mù |
| DB đã commit `SMTP_ACCEPTED` | Có bằng chứng submission | Không tạo attempt mới |

### 24.1. Lease expiry không đồng nghĩa chưa gửi

Nếu row `SENDING` có `lease_expires_at < now`:
- worker có thể đã chết trước submission;
- hoặc SMTP đã accepted nhưng chưa persist;
- hoặc một worker cũ vẫn đang gửi dù lease hết hạn.

Không tự động đổi mọi row như vậy về `PENDING` rồi resend khi resume. Đưa qua recovery classifier và reconciliation, dùng fencing khi cập nhật database.

### 24.2. Lưu attempt history

Một record nên có:
- message key;
- attempt ID;
- worker/lease token;
- provider/profile;
- startedAt;
- trạng thái từng giai đoạn nếu ứng dụng có thể quan sát;
- outcome/safe error code;
- acceptedAt hoặc unknownReason;
- correlation metadata phù hợp.

Không log password, SMTP AUTH traffic, full MIME body, reset token hoặc attachment để phục vụ điều tra thông thường.

## 25. Điều kiện readiness và health khi resume

Trước khi bỏ pause, nên kiểm tra:

- Database schema/connection và migrations hoàn tất.
- Outbox status/indexes/constraints có thể query.
- Worker deployments ở phiên bản tương thích.
- SMTP provider endpoint reachable theo chính sách.
- TLS certificate/hostname validation không lỗi.
- Credential đã được xoay vòng và còn quyền gửi.
- From identity/domain đã verified.
- Queue/broker và storage liên quan có khả năng phục hồi.
- Các attempts `UNKNOWN` có kế hoạch xử lý.
- Backlog, deadline và rate-limit budget được ước lượng.
- Monitoring và on-call hoạt động.

### 25.1. Smoke test có kiểm soát

Một email thử nghiệm tới mailbox được cho phép có thể xác minh submission route. Nếu hệ thống đang pause global:
- dùng một cơ chế smoke test **được ủy quyền và cách ly** rõ ràng, chẳng hạn SMTP sandbox hoặc một route test được bật riêng;
- không bypass pause bừa bãi trong production code;
- không dùng recipient khách hàng thật;
- sau smoke test mới resume traffic thật.

### 25.2. SMTP test thành công không chứng minh delivery

Một relay trả success không đồng nghĩa thư vào Inbox. Nếu đang thay provider, còn cần xác minh SPF/DKIM/DMARC, bounce/webhook/suppression và quota theo yêu cầu vận hành.

## 26. Bảo mật của lệnh pause/resume

Một endpoint vận hành có khả năng dừng gửi toàn hệ thống là hành động nhạy cảm.

Yêu cầu:
- Xác thực operator và phân quyền tối thiểu.
- Chỉ nhân sự/automation được phép mới có thể pause global.
- Audit mọi lệnh và phạm vi.
- Lý do bảo trì không chứa secret.
- Bảo vệ khỏi CSRF nếu dùng cookie/browser session.
- Giới hạn API chỉ trong mạng/kênh quản trị phù hợp.
- Có rate limiting và idempotent command semantics.
- Có quy trình hai người xác nhận nếu SLA/chính sách yêu cầu.
- Không cho người dùng tenant A pause provider của tenant B.
- Có cách xem trạng thái mà không cần quyền thực hiện pause/resume.

### 26.1. API contract gợi ý

```text
POST /ops/mail-dispatch/pause
{
  "scope": "GLOBAL",
  "reason": "database-migration",
  "requestId": "maintenance-2026-11-12"
}

Response:
{
  "state": "PAUSED",
  "generation": 42,
  "activeAttempts": 7,
  "drained": false
}
```

Lệnh này có nghĩa gate đã commit; các attempt trước đó vẫn có thể hoàn tất.

```text
GET /ops/mail-dispatch/status?scope=GLOBAL

{
  "state": "DRAINING",
  "generation": 42,
  "activeAttempts": 3,
  "unknownAttempts": 1
}
```

Đây là **API minh họa do ứng dụng tự thiết kế**, không phải endpoints có sẵn của Spring Framework Mail.

### 26.2. Idempotent pause/resume

Gửi lặp lại cùng yêu cầu pause không nên tạo những thay đổi nghiệp vụ trái ý hoặc đảo trạng thái. Cần xem xét:
- chỉ tăng generation khi trạng thái thực sự đổi hay khi operator phát lệnh mới;
- request ID để tránh ghi duplicate audit events;
- optimistic version nếu nhiều operators thao tác đồng thời;
- cảnh báo khi có lệnh resume ngoài maintenance window.

### 26.3. Tránh automatic resume khi process restart

Nếu cờ pause được lưu trong DB, restart app không nên tự đặt nó về false. Resume phải là một hành động vận hành được cho phép khi điều kiện đã sẵn sàng.

## 27. Observability: biết chắc đang ở bước nào

Các metric gợi ý:

| Metric | Mục đích |
|---|---|
| `mail_dispatch_paused{scope}` | Gate đang bật hay tắt |
| `mail_maintenance_generation{scope}` | Phiên bản điều khiển |
| `mail_active_submissions{provider}` | Lượt SMTP gửi đang chạy |
| `mail_outbox_pending_count` | Job chưa gửi |
| `mail_outbox_retry_wait_count` | Job đang chờ retry |
| `mail_outbox_unknown_count` | Attempt cần reconciliation |
| `mail_outbox_expired_count` | Job hết hạn |
| `mail_outbox_oldest_due_age_seconds` | Backlog đã quá hạn bao lâu |
| `mail_dispatch_claims_total` | Số job claim |
| `mail_dispatch_claim_blocked_total{scope}` | Số lần claim bị chặn vì pause |
| `mail_smtp_submit_duration_seconds` | Độ trễ SMTP submission |
| `mail_smtp_outcomes_total{outcome}` | Thành công/lỗi/unknown |
| `mail_maintenance_drain_seconds` | Thời gian drain |
| `mail_recovery_stale_leases_total` | Lease cần xử lý sau lỗi |
| `mail_schedule_catchup_created_total` | Occurrences được tạo bù |

Metric names ở đây chỉ minh họa. Không dùng message key, recipient hoặc raw tenant identifier làm labels cardinality cao trong Prometheus.

### 27.1. Structured logs

```json
{
  "event": "mail.dispatch.paused",
  "scope": "GLOBAL",
  "generation": 42,
  "reasonCode": "DB_MIGRATION",
  "operatorRole": "MAIL_OPERATOR",
  "activeAttemptsAtPause": 7
}
```

Và khi drained:

```json
{
  "event": "mail.dispatch.drained",
  "scope": "GLOBAL",
  "generation": 42,
  "activeAttempts": 0,
  "unknownAttemptsPendingReview": 1,
  "durationMs": 21820
}
```

**`activeAttempts=0` không đồng nghĩa `unknownAttempts=0`.** Có thể không còn network call đang chạy nhưng vẫn có một số kết quả cần đối soát trước khi resume những job liên quan.

### 27.2. Alert quan trọng

- Gate đã pause lâu hơn maintenance window dự kiến.
- Drain không hoàn tất trước timeout.
- Có claim mới sau pause commit (lỗi phối hợp).
- Active worker vẫn submit trong khi operator đã xác nhận DRAINED.
- `UNKNOWN` tăng trong quá trình restart.
- Backlog age vượt SLA.
- Resume gây SMTP 4xx/rate-limit spike.
- Có job hết hạn nhưng vẫn được submit.
- Recurring occurrences bị thiếu hoặc tạo trùng.

## 28. Runbook trước khi bảo trì

Một runbook rõ ràng giúp hạn chế thao tác theo cảm tính.

### Bước 1 — Xác định phạm vi

Ghi lại:
- Mục đích và thời lượng dự kiến.
- Provider/tenant/category bị ảnh hưởng.
- Những email được phép tiếp tục gửi.
- Có dừng schedule creation hay chỉ dispatch.
- Các sender đường tắt gọi trực tiếp ngoài outbox.
- Business deadline, SLA và quiet hours.
- Người chịu trách nhiệm pause/resume.

### Bước 2 — Kiểm tra trạng thái ban đầu

Đo:
- due backlog và oldest due age;
- active attempts;
- retries và UNKNOWN;
- throughput/quota;
- các recurring schedules sắp đến kỳ;
- DB/schema readiness;
- các pods/consumers đang chạy.

### Bước 3 — Thông báo phạm vi và kỳ vọng

Nếu user-facing API nhận lịch mới trong bảo trì, UI/API phải thông báo:
- yêu cầu vẫn được lưu hay tạm từ chối;
- khả năng bị gửi trễ;
- điều kiện hủy/đổi lịch;
- thông báo quá hạn có thể bị bỏ theo policy.

Không hứa mọi thư chắc chắn được gửi đúng giờ nếu hệ thống chủ động dừng dispatch.

### Bước 4 — Chuẩn bị rollback

Xác định ai có quyền:
- kéo dài pause;
- rollback migration;
- phục hồi secret cũ;
- resume canary;
- tạm dừng lại nếu provider errors tăng.

## 29. Runbook pause và drain

### Bước 1 — Commit pause gate

Gọi API quản trị hoặc transaction cập nhật control row. Xác nhận version/generation và thời điểm commit.

### Bước 2 — Xác nhận không claim mới

Quan sát claim rate và kiểm thử/query rằng dispatcher trả rỗng trong scope bị pause. Không chỉ kiểm tra một JVM flag.

### Bước 3 — Cho in-flight hoàn tất

Theo dõi:
- active SMTP submissions;
- job `SENDING`;
- lease ownership;
- lỗi timeout/TLS;
- number of attempts cần reconciliation.

### Bước 4 — Chốt trạng thái các attempt bất thường

Nếu worker bị crash hoặc outcome không chắc chắn:
- ghi `UNKNOWN`/reconciliation task theo policy;
- không biến hàng loạt thành `PENDING`;
- ghi lại message keys cần điều tra;
- tránh gửi lại trước khi có quyết định.

### Bước 5 — Xác nhận DRAINED theo contract

Lưu:
- scope;
- generation;
- thời điểm drained;
- active count = 0 theo nguồn quan sát;
- danh sách UNKNOWN chưa phân giải;
- operator/approval nếu có.

### Bước 6 — Thực hiện bảo trì

Chỉ sau khi đạt mức an toàn cần thiết mới:
- ngắt SMTP route;
- restart workers;
- migrate database;
- thay TLS/credential;
- cập nhật hạ tầng.

Nếu quy trình phải dừng gấp trước khi drained, cần ghi rõ đã sử dụng **emergency stop** và khả năng tăng UNKNOWN/duplicate risk.

## 30. Runbook resume và xử lý tồn đọng

### Bước 1 — Kiểm tra hạ tầng

- Ứng dụng đúng version.
- Database/migration hoàn tất.
- SMTP kết nối/credential/TLS hợp lệ.
- Queue/broker/worker healthy.
- Không có pod cũ vẫn chạy logic không tương thích.

### Bước 2 — Phân loại backlog

- Pending còn hợp lệ.
- Retry due.
- Expired/Cancelled.
- UNKNOWN cần reconciliation.
- Recurring missed occurrences cần catch-up.
- Jobs bị suppress hoặc thay đổi consent.

### Bước 3 — Materialize/catch-up nếu có lịch lặp

Tạo bù occurrences theo timezone/recurrence policy. Dùng unique keys để không tạo trùng.

### Bước 4 — Resume canary

Bỏ pause ở một phạm vi kiểm soát hoặc giới hạn worker concurrency/rate. Theo dõi accepted/4xx/unknown và queue lag.

### Bước 5 — Resume phạm vi đầy đủ

Khi metrics ổn định:
- unpause các scopes còn lại;
- giữ quota/bounded concurrency;
- không reset attempts;
- giám sát backlog giảm.

### Bước 6 — Chốt incident/maintenance report

Ghi lại:
- total paused duration;
- số jobs được gửi bù;
- số jobs expired/cancelled;
- các attempts UNKNOWN;
- errors/retries;
- có lịch lặp nào bị thiếu;
- sự kiện cần cải thiện runbook.

## 31. Các tình huống lỗi cần phân biệt

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Đã pause nhưng SMTP vẫn có một số calls | In-flight jobs claim trước pause | Drain, kiểm tra ownership |
| Pod A dừng nhưng B vẫn gửi | Pause local thay vì cluster-wide | Gate chung/claim atomic |
| Restart xong tự gửi lại tất cả | Cờ pause memory mất, due backlog | Persist gate, resume có kiểm soát |
| Lịch mất sau bảo trì | Chỉ dùng in-memory scheduler/queue | Durable outbox/recurrence |
| Bảo trì xong email OTP cũ được gửi | Không kiểm tra `expires_at` | Expire trước submission |
| Gửi trùng khi recovery | Lease hết hạn bị coi là chưa gửi | UNKNOWN/reconciliation |
| Dừng claim nhưng cron vẫn tạo job | Pause dispatch không pause materializer | Đây có thể là chủ đích; phân định rõ |
| Không có job cho các ngày downtime | Materializer cũng dừng | Catch-up theo recurrence |
| Database migration kẹt | Worker vẫn giữ transaction/lock | Drain, transaction ngắn |
| Claim sau pause commit | Read flag không atomic với claim | DB lock gate/fencing protocol |
| Resume nhưng worker vẫn dừng | Scheduled task đã bị cancel, chưa khởi động lại | Quản lý lifecycle đồng bộ với gate |
| QueueChannel đầy khi resume | Producer nhanh hơn consumer | Backpressure/rate limit, durable storage |
| Provider 451 tăng mạnh | Backlog burst vượt quota | Gradual resume, jitter/concurrency |
| Lịch gửi lệch timezone | Tính lại bằng system default zone | Lưu Instant/ZoneId, test DST |
| Marketing bị gửi dù user đã opt-out | Không revalidate consent trước gửi | Suppression policy ở dispatch |
| Operator nhầm “PAUSED” là “DRAINED” | API không phân biệt hai trạng thái | Phân cấp response và dashboards |
| Lệnh resume bị ghi đè | Nhiều operators/automations race | Version/CAS, audit |
| Bảo trì SMTP xong lỗi TLS | Credential/cert/hostname thay | Smoke test đúng TLS policy |
| Log chứa nguyên email body | Debug/exception logging quá mức | Redaction và hạn chế quyền log |
| Pause scope A nhưng job route sang B | Routing diễn ra sau gate check | Check scope của route thực tế |

## 32. Kiểm thử unit cho cơ chế pause

Test lớp coordinator mà không cần SMTP thật:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;

import java.util.List;
import org.junit.jupiter.api.Test;

class MailClaimCoordinatorTest {

    @Test
    void pausedGateDoesNotClaimJobs() {
        DispatchControlRepository controls =
            mock(DispatchControlRepository.class);

        ScheduledMailRepository repository =
            mock(ScheduledMailRepository.class);

        when(controls.lockGlobal())
            .thenReturn(new DispatchGate(true, 42));

        MailClaimCoordinator coordinator =
            new MailClaimCoordinator(controls, repository);

        List<ClaimedMail> claimed =
            coordinator.claimDue(20);

        assertThat(claimed).isEmpty();
        verifyNoInteractions(repository);
    }

    @Test
    void unpausedGateAllowsClaim() {
        DispatchControlRepository controls =
            mock(DispatchControlRepository.class);

        ScheduledMailRepository repository =
            mock(ScheduledMailRepository.class);

        when(controls.lockGlobal())
            .thenReturn(new DispatchGate(false, 43));

        when(repository.claimDueBatch(5))
            .thenReturn(List.of());

        MailClaimCoordinator coordinator =
            new MailClaimCoordinator(controls, repository);

        coordinator.claimDue(5);

        verify(repository).claimDueBatch(5);
    }
}
```

Các test này xác minh branch logic, **không chứng minh row locking hoặc concurrency trên database thật**. Phần đó cần integration tests.

### 32.1. Test producer không mất dữ liệu khi paused

Nếu business service vẫn chấp nhận yêu cầu trong thời gian bảo trì, test rằng:
- outbox job được persist;
- `status=PENDING`;
- không có attempt mới;
- không gọi `JavaMailSender`;
- API trả ý nghĩa “queued/pending”, không “delivered”.

### 32.2. Test cancellation không phá pause

Nếu user hủy một job đã queued trong maintenance, khi resume job đó phải ở `CANCELLED` và không được claim. Tính năng pause global và cancel từng job phải tương tác đúng.

## 33. Integration test với PostgreSQL Testcontainers

Để kiểm tra atomicity của gate, cần chạy repository thật trên database có semantics tương thích với production.

### 33.1. Bối cảnh test

- PostgreSQL trong Testcontainers.
- Migration/schema của application.
- Spring transaction manager và repository thật.
- Hai coordinator instances/threads dùng database connections riêng.
- Gateway SMTP là test double, để không gửi email ra ngoài.
- `Clock` có thể điều khiển để test due time.
- Test cleanup/isolation rõ ràng.

### 33.2. Kịch bản: pause commit trước claim

1. Tạo một job `PENDING` đã đến hạn.
2. Commit `paused=true`.
3. Gọi `claimDue(1)`.
4. Assert kết quả rỗng.
5. Assert job vẫn `PENDING`, `attempt_count=0`.
6. Assert không có lời gọi SMTP.

### 33.3. Kịch bản: claim và pause cạnh tranh

Dùng `CountDownLatch`/transaction barriers:
- Worker A bắt đầu claim và giữ lock control row.
- Operator B gọi pause trong transaction khác.
- Xác nhận B chưa commit trước khi A nhả lock.
- Sau A commit, B commit pause.
- Worker C bắt đầu claim sau B commit và trả rỗng.
- Các jobs A claim được tính là in-flight hợp lệ.

Điều quan trọng là **thứ tự commit**, không chỉ thứ tự log statements. Không dùng `Thread.sleep` ngẫu nhiên để hy vọng tạo race.

### 33.4. Kịch bản: 2 nodes cùng pause

Hai operators cùng yêu cầu pause hoặc một automation retry request. Kiểm tra:
- state cuối là paused;
- không có chuyển trạng thái bất ngờ sang resume;
- generation/audit đúng contract;
- không tạo hai email attempts do hệ quả của pause.

### 33.5. Kịch bản: resume sau restart

1. Pause trong database.
2. Tạo worker mới/restart Spring context trên cùng database.
3. Xác minh vẫn không claim.
4. Resume bằng authorized command.
5. Claim các jobs đủ điều kiện.
6. Không gửi job đã `CANCELLED`/`EXPIRED`/`SMTP_ACCEPTED`.

### 33.6. Kịch bản: DB failure sau SMTP accepted

Để gateway giả lập accepted, sau đó ép repository update outcome lỗi. Xác minh hệ thống **không** đơn giản biến job về pending và gửi lại trong lần poll sau. Nó phải đi qua recovery/reconciliation.

## 34. Kiểm thử graceful shutdown và in-flight drain

Một integration test hữu ích có **blocking fake gateway**:

```text
Test starts one email submission
       |
       v
Fake gateway signals "send started"
       |
       +--> blocks on latch
       |
Test calls pause
       |
       v
No new claims allowed
       |
Release gateway latch
       |
       v
Worker persists outcome
       |
       v
Drain eventually reaches 0
```

Các assertions:
- Attempt đầu có thể hoàn tất.
- Attempt khác chưa claim sau pause.
- Drain không báo hoàn tất khi gateway còn block.
- Khi gateway release, state được persist.
- Nếu worker chết hoặc timeout, drain báo unresolved/UNKNOWN theo contract.
- Không cần SMTP provider thật để kiểm tra orchestration.

### 34.1. Bounded waits thay vì ngủ tùy ý

Dùng:
- `CountDownLatch` để đồng bộ;
- `Future.get(timeout, unit)` để tránh test treo;
- test scheduler/clock để điều khiển mốc thời gian;
- polling assertion có giới hạn khi test async;
- cleanup threads/resources giữa tests.

Không dựa vào `Thread.sleep(10000)` rồi kết luận “drain chắc đã xong”.

### 34.2. Test process termination

Một bộ test deployment chuyên biệt có thể:
- gửi SIGTERM đến worker;
- kiểm tra nó ngừng claim;
- chờ in-flight trong grace period;
- restart worker trên cùng DB;
- xác minh no job loss;
- xử lý stale leases/UNKNOWN.

Đây là integration/system test, không phải unit test của một method.

## 35. Test backlog, catch-up và deadline

Sau một maintenance window dài, test cần nhiều loại jobs:

```text
Job A: PENDING, due 08:00, expires tomorrow
Job B: PENDING, due 08:30, expired 09:00
Job C: RETRY_WAIT, next attempt due 08:45
Job D: SMTP_ACCEPTED
Job E: UNKNOWN
Job F: CANCELLED
```

Khi resume lúc 10:00:
- A eligible.
- B bị xử lý expired, không gửi.
- C eligible theo retry budget nếu còn hợp lệ.
- D không resubmit.
- E không auto resubmit.
- F không gửi.

Thêm recurring schedule:
- Có các occurrences của ba ngày downtime.
- Catch-up chỉ tạo những kỳ phù hợp policy.
- Mỗi occurrence có unique key để tránh trùng dù chạy materializer hai lần.
- Các mốc `sendAt` được tính từ local date/time + ZoneId, không chỉ cộng một số giờ UTC.

### 35.1. Test gradual resume

Dùng giả lập quota/provider:
- giới hạn concurrent sends;
- giới hạn submissions per second;
- assert backlog giảm theo nhịp;
- assert không vượt budget;
- khi provider trả rate limit, job được backoff, không tạo storm.

### 35.2. Test bảo trì kéo qua DST

Một recurring schedule `Europe/Berlin` có kỳ gửi nằm trong ngày đổi DST:
- áp dụng gap/overlap policy đã lưu;
- không tạo hai occurrences ngoài ý định;
- không bỏ sót kỳ hợp lệ;
- resume không thay đổi ZoneId đã lựa chọn.

## 36. Bài tập thực hành

### Bài 1 — Phân biệt pause và cancel

Viết mô tả contract cho `PAUSED`, `DRAINING`, `DRAINED`, `CANCELLED`, `SMTP_ACCEPTED` và `UNKNOWN`. Xác định trạng thái nào là global control, trạng thái nào thuộc từng job.

### Bài 2 — Gate in-memory không đủ

Cho ba pods cùng có `volatile boolean paused`. Giải thích vì sao thay đổi trên pod A không bảo đảm B/C dừng gửi và vì sao restart có thể reset flag.

### Bài 3 — Bảng điều khiển

Tạo `mail_dispatch_control` có scope, paused, generation và audit fields. Viết migration tạo row `GLOBAL` ban đầu.

### Bài 4 — Atomic pause/claim

Dùng PostgreSQL `SELECT ... FOR UPDATE` cho control row, rồi `FOR UPDATE SKIP LOCKED` claim due jobs. Test khi pause commit trước claim thì job không bị lấy.

### Bài 5 — Lệnh pause và drain

Viết API quản trị:
- `pauseGlobal` cập nhật gate;
- `getDrainStatus` trả active attempts;
- `resumeGlobal` chỉ cho phép operator đã xác thực.

Phân biệt response `PAUSED` với `DRAINED`.

### Bài 6 — Race giữa send và pause

Dùng blocking fake SMTP gateway và latch. Pause trong lúc send đang block. Xác minh job đã claim có thể hoàn tất nhưng job mới không được claim.

### Bài 7 — Graceful shutdown

Thiết kế shutdown sequence trong Spring Boot: dừng dispatcher, chờ worker pool, persist outcomes, rồi mới đóng datasource. Giải thích vì sao `@PreDestroy` đơn giản chưa đủ.

### Bài 8 — Kubernetes

Một deployment có ba replicas và terminationGracePeriod 30 giây. Thiết kế global pause trước khi bảo trì SMTP, khác với pod-local drain trong rolling deploy.

### Bài 9 — Retry qua bảo trì

Job có `next_attempt_at=09:05` nhưng hệ thống pause 09:00–10:00. Sau resume, nó phải được retry theo budget, không tăng attempt count vì các poller trong bảo trì.

### Bài 10 — Token hết hạn

Email xác minh có `expires_at=09:30`, pause đến 10:00. Chứng minh job không được submit sau resume và có trạng thái EXPIRED rõ ràng.

### Bài 11 — UNKNOWN

Giả lập SMTP accepted nhưng database update lỗi. Sau restart và resume, test worker không tự gửi lại khi outcome chưa được đối soát.

### Bài 12 — Multi-provider pause

Pause `PROVIDER:A` nhưng cho `PROVIDER:B` tiếp tục. Viết rule chọn route và kiểm tra scopes sao cho một email không bị gửi sai provider do thay route sau gate check.

### Bài 13 — Recurring catch-up

Ứng dụng mất hai lần trigger báo cáo hằng ngày. Tạo occurrences từ recurrence definition và unique `(scheduleId,localDate,slot)`. Chạy catch-up hai lần và assert không trùng.

### Bài 14 — Pause cả materializer

So sánh hai chế độ: pause dispatch nhưng tiếp tục tạo jobs, và pause cả schedule materializer. Phân tích cách khôi phục sau DB downtime.

### Bài 15 — Backlog sau resume

Có 20.000 due jobs, provider có quota chặt. Thiết kế gradual resume bằng worker concurrency, rate limit, jitter và metric theo dõi.

### Bài 16 — Cancellation race

Người dùng hủy mail đúng lúc worker claim. Thiết kế optimistic lock hoặc conditional update để xác định chính xác liệu cancellation đã thành công trước side effect hay chưa.

### Bài 17 — Lịch gửi qua DST

Bảo trì kéo qua ngày 29/03/2026 ở Berlin. Lịch lặp tại 02:30 có gap; chọn chính sách SKIP hoặc SHIFT, rồi chứng minh catch-up không tự tạo một email sai giờ.

### Bài 18 — Thay SMTP credential

Pause profile, drain, thay sender instance có credential mới, smoke test mailbox test và resume. Không mutate một `JavaMailSenderImpl` singleton đang được dùng.

### Bài 19 — Audit bảo trì

Thiết kế bảng audit chứa operator, scope, generation, reason, pause/resume timestamps và trạng thái drain. Không ghi SMTP password hoặc nội dung email.

### Bài 20 — Reconciliation report

Cho ba attempts: `SMTP_ACCEPTED`, `DEAD_LETTER`, `UNKNOWN`. Lập báo cáo bảo trì chỉ cho phép gửi lại những job đã được phân loại an toàn; giải thích vì sao UNKNOWN không thể coi là chắc chắn chưa gửi.

## 37. Tổng kết

**Dừng lịch gửi an toàn khi bảo trì** trong Spring Framework Mail không chỉ là tắt `@Scheduled` hoặc đặt một biến boolean. Đó là một quy trình điều phối trạng thái trên toàn hệ thống, có điểm chặn job mới, cơ chế drain những lượt gửi đã bắt đầu, dữ liệu bền vững để phục hồi và chính sách resume để xử lý backlog.

Những nguyên tắc cốt lõi:

1. **Phân biệt pause, drain và cancel.** Pause chặn claim mới; drain quản lý in-flight; cancel hủy job theo nghiệp vụ.
2. Với nhiều worker/pods, cần **gate bền vững, dùng chung và đồng bộ với atomic claim**. Cờ local không đủ.
3. **Không giữ DB transaction qua SMTP.** Claim và persist outcome là các transaction ngắn, tách khỏi side effect mạng.
4. Sau khi pause commit, các job **đã claim trước đó có thể vẫn gửi**. Muốn ngừng an toàn, phải chờ đến trạng thái DRAINED hoặc ghi nhận những attempts chưa giải quyết.
5. **Đừng resend mù khi lease hết hạn hoặc SMTP outcome UNKNOWN.** Relay có thể đã chấp nhận email trước khi worker bị kill.
6. Dùng **durable outbox/recurring schedule definitions** để bảo toàn job qua restart, không dựa vào timer hoặc QueueChannel in-memory.
7. Khi resume, **kiểm tra deadline, consent, cancel, retry budget và backlog**, rồi mở lại theo quota thay vì bơm toàn bộ jobs ra provider.
8. Nếu pause tác động tới **recurring materialization**, cần catch-up idempotent theo ngày giờ local/ZoneId, kể cả những ngày có DST.
9. **Thời điểm lịch gửi không phải thời điểm delivery.** `JavaMailSender.send(...)` thành công không bảo đảm email đã vào Inbox.
10. Vận hành phải có **phân quyền, audit, metrics, runbook, khả năng rollback và integration tests cho race/persistence**.

Khi thiết kế rõ ràng ranh giới **không claim mới → hoàn tất hoặc đối soát attempts đang gửi → bảo trì → khôi phục có kiểm soát**, ứng dụng có thể ngừng và tiếp tục lịch gửi một cách dự đoán được, hạn chế mất job, hạn chế gửi trùng và không làm sai ý định thời gian của người dùng.
