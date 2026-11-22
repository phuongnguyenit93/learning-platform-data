# Xử lý email quá hạn hoặc bị bỏ qua

## 1. Vì sao email đã được lập lịch vẫn có thể không nên gửi?

Trong ứng dụng **Spring Framework Mail**, chức năng lập lịch gửi giúp tạo một ý định gửi email ở thời điểm hiện tại nhưng thực hiện **JavaMailSender.send(...)** vào thời điểm khác. Một số email phải được gửi sau một khoảng chờ; một số được gom thành chiến dịch; một số phụ thuộc lịch làm việc, quota hoặc trạng thái nghiệp vụ.

Việc có một job trong queue không đồng nghĩa **job đó còn hợp lệ khi worker đến lượt**.

Ví dụ:

- Mã OTP có hiệu lực trong 5 phút, nhưng hàng đợi bị kẹt 12 phút. Gửi mã đã hết hạn chỉ gây nhầm lẫn.
- Email nhắc thanh toán dự kiến gửi lúc 09:00, nhưng người dùng đã thanh toán lúc 08:55. Email không còn phù hợp.
- Email nhắc sự kiện lẽ ra gửi trước giờ bắt đầu. Khi worker phục hồi sau outage, sự kiện đã kết thúc.
- Khách hàng hủy đăng ký nhận email marketing trước giờ gửi. Thư phải bị loại khỏi lịch theo chính sách.
- Một email đang chờ retry, nhưng lần retry tiếp theo rơi sau **deadline**.
- Tenant hết quota hoặc thiếu capacity. Email có thể cần chờ, nhưng không được chờ vô hạn.
- Một chiến dịch được quản trị viên tạm dừng hoặc hủy. Những job chưa gửi không được tự động chạy lại khi scheduler khởi động.
- Một notification bị phân loại là **bỏ qua có chủ đích** vì trùng, không có recipient hợp lệ hoặc bị chặn bởi rule nghiệp vụ.

Vì vậy, **xử lý email quá hạn hoặc bị bỏ qua** là một phần quan trọng của luồng **lập lịch gửi**: hệ thống cần xác định khi nào một email còn được phép gửi, khi nào phải ngừng thử, khi nào được chuyển lịch và phải lưu lý do ra sao.

Một nguyên tắc quan trọng:

> **Không gửi email chỉ vì nó còn nằm trong queue. Gửi khi và chỉ khi trạng thái, thời gian, quyền gửi và điều kiện nghiệp vụ vẫn hợp lệ tại thời điểm thực hiện.**

Spring Mail cung cấp công cụ tạo/gửi thư, còn **deadline, skip policy, trạng thái outbox và tính an toàn khi retry** là thiết kế của ứng dụng.

## 2. Phân biệt thời gian lập lịch, thời gian đến hạn và thời gian hết hiệu lực

Một notification có thể cần nhiều mốc thời gian:

| Trường | Ý nghĩa |
|---|---|
| **created_at** | Thời điểm ý định gửi được tạo |
| **scheduled_at** | Thời điểm nghiệp vụ mong muốn thư được gửi |
| **not_before_at** | Thời điểm sớm nhất được phép thử gửi |
| **next_attempt_at** | Thời điểm sớm nhất worker được thử lần tiếp theo |
| **expires_at** | Deadline sau đó không được **bắt đầu submission mới** |
| **claimed_at** | Thời điểm worker nhận quyền xử lý |
| **attempt_started_at** | Thời điểm bắt đầu một SMTP attempt |
| **submitted_at** | Thời điểm SMTP provider xác nhận chấp nhận message |
| **completed_at** | Thời điểm workflow xử lý notification kết thúc |
| **cancelled_at / skipped_at / expired_at** | Thời điểm hệ thống ghi nhận trạng thái kết thúc tương ứng |

Đừng trộn ba khái niệm:

1. **scheduled_at**: mong muốn gửi khi nào.
2. **next_attempt_at**: scheduler được đánh thức để thử khi nào, có thể đổi vì backoff hoặc quota.
3. **expires_at**: sau mốc nào không nên bắt đầu một SMTP attempt mới.

Ví dụ:

~~~text
created_at       08:00
scheduled_at     09:00
not_before_at    09:00
next_attempt_at  09:00
expires_at       09:15

09:00  provider tạm lỗi
09:01  retry 1 không thành công
09:05  next_attempt_at cập nhật thành 09:10
09:10  thử lại nếu còn hợp lệ
09:15  không khởi động SMTP attempt mới
~~~

Một email có thể **đến hạn gửi nhưng chưa quá hạn**, hoặc **chưa đến lịch gửi nhưng đã bị hủy**. Trạng thái cần phản ánh đúng nguyên nhân, không quy tất cả về FAILED.

## 3. Email quá hạn khác email bị bỏ qua như thế nào?

Nên dùng tên trạng thái và lý do rõ ràng:

| Kết quả | Ý nghĩa | Ví dụ |
|---|---|---|
| **EXPIRED** | Không còn được phép gửi vì đã qua deadline | OTP quá 5 phút, nhắc họp sau khi họp kết thúc |
| **SKIPPED** | Hệ thống chủ động không gửi vì rule nghiệp vụ/policy | Đơn đã thanh toán, recipient không hợp lệ |
| **CANCELLED** | Chủ thể được phép đã hủy ý định gửi | User hủy chiến dịch trước giờ gửi |
| **SUPPRESSED** | Recipient/email bị chặn theo chính sách gửi | Người nhận unsubscribe, suppression list hợp lệ |
| **FAILED** | Đã thử xử lý/gửi nhưng gặp lỗi được xác định theo policy | MIME preparation lỗi vĩnh viễn, SMTP 5xx xác định |
| **RETRY_WAIT** | Chưa gửi được nhưng còn cơ hội hợp lệ | SMTP 451, provider throttle tạm thời |
| **UNKNOWN** | Không xác định được SMTP đã chấp nhận message chưa | Mất final SMTP reply sau DATA |
| **SUBMITTED** | Provider/server ở chặng SMTP đã chấp nhận | send(...) hoàn thành theo transport contract |

Không bắt buộc ứng dụng phải dùng tất cả tên trên, nhưng cần giữ **ngữ nghĩa khác nhau**.

Ví dụ, một email bị skip vì đơn đã thanh toán không phải lỗi SMTP. Nếu ghi là FAILED, dashboard transport error sẽ bị thổi phồng và worker có thể retry sai.

Một email đã SUBMITTED rồi mới phát hiện deadline đi qua cũng không thể đổi thành **EXPIRED_NOT_SENT**, vì thư có thể đã rời hệ thống. Cần phân biệt thời điểm **bắt đầu submission**, **kết quả SMTP** và **deadline nghiệp vụ**.

## 4. Chọn chính sách: gửi muộn hay bỏ gửi?

Không phải mọi email trễ lịch đều phải bỏ. Trước khi triển khai scheduler, cần xác định **late-delivery policy** cho từng loại thông báo.

| Loại email | Nếu trễ 2 phút | Nếu trễ 2 giờ | Hướng chính sách |
|---|---|---|---|
| OTP hoặc magic link | Có thể đã vô nghĩa tùy TTL | Không gửi | Deadline cứng |
| Cảnh báo bảo mật quan trọng | Có thể vẫn cần gửi | Có thể vẫn hữu ích nhưng phải nói đúng thời điểm | Kiểm tra trạng thái và nội dung |
| Nhắc cuộc họp trước 15 phút | Có thể gửi nếu còn trước giờ họp | Không gửi nhắc trước họp đã qua | Gắn deadline với sự kiện |
| Nhắc thanh toán | Phải đối chiếu đã thanh toán chưa | Chỉ gửi nếu khoản còn đến hạn | Business revalidation |
| Xác nhận đơn hàng | Thường vẫn có giá trị | Vẫn có thể gửi muộn nhưng không nên mô tả “vừa đặt” | Cho gửi muộn có giới hạn |
| Hóa đơn hợp lệ | Có thể gửi | Có thể cần gửi dù trễ, tùy nghĩa vụ | Ưu tiên đảm bảo gửi, có SLA |
| Marketing promotion | Có thể chấp nhận | Bỏ nếu khuyến mại hết hạn | Campaign window |
| Daily digest | Có thể chấp nhận trong khoảng grace | Có thể dời sang kỳ kế tiếp hoặc bỏ | Policy theo kỳ |

**Tất cả con số trong bảng là ví dụ nghiệp vụ**, không phải giá trị mặc định của Spring Framework Mail.

Một hệ thống có thể định nghĩa:

~~~java
public enum LateSendPolicy {
    DROP_AFTER_DEADLINE,
    SEND_WITHIN_GRACE_PERIOD,
    REVALIDATE_BEFORE_SEND,
    ROLL_TO_NEXT_WINDOW,
    SEND_WHEN_AVAILABLE
}
~~~

Với **SEND_WHEN_AVAILABLE**, vẫn cần giới hạn retention, retry budget và điều kiện nghiệp vụ. Không được dùng policy này để giữ vô hạn một email chứa link/token đã hết hạn.

## 5. Những câu hỏi cần giải quyết khi thiết kế policy

Trước khi viết code, hãy trả lời:

1. Email nào **không còn ý nghĩa** sau một thời điểm?
2. Thời điểm hết hiệu lực đến từ **token TTL**, sự kiện, campaign, user preference hay hợp đồng?
3. Có **grace period** sau scheduled_at không?
4. Email đến hạn nhưng chưa đủ quota sẽ **chờ hay bị skip**?
5. Trước khi gửi có cần đọc lại trạng thái đơn hàng, subscription hoặc consent không?
6. Ai được quyền hủy/lên lịch lại?
7. Một email đã được worker claim nhưng chưa SMTP submit thì hủy được đến đâu?
8. Gặp **UNKNOWN** sau DATA thì ghi trạng thái và retry thế nào?
9. Nếu job hết hạn lúc worker đang gửi thì kết quả được diễn giải ra sao?
10. Người dùng và đội vận hành cần xem **lý do cuối cùng** nào?

Tài liệu hóa các câu trả lời thành **policy của từng notification type**, thay vì để mọi worker tự suy đoán từ timestamp hoặc Subject.

## 6. State machine cho email được lập lịch

Một state machine minh họa:

~~~text
                 +----------------+
                 |   SCHEDULED    |
                 +----------------+
                       |
               đến next_attempt_at
                       |
                       v
                +--------------+
                |    READY     |
                +--------------+
                  |    |     |
     quá hạn -----+    |     +----- policy không hợp lệ
                  |    |                 |
                  v    v                 v
              EXPIRED CLAIMED          SKIPPED
                        |
                        +---- hủy trước SMTP ----> CANCELLED
                        |
                        v
                   SENDING
                     |
        +------------+-------------+-------------+
        |            |             |             |
        v            v             v             v
    SUBMITTED     RETRY_WAIT      FAILED        UNKNOWN
                      |
                      +--> READY nếu chưa hết hạn
                      |
                      +--> EXPIRED nếu hết thời gian thử
~~~

Các state chỉ minh họa. Trong một database production có thể gộp **SCHEDULED/READY** thành **PENDING** với next_attempt_at, hoặc dùng **PROCESSING** cùng lease.

Điều quan trọng là các **terminal states** (SUBMITTED, EXPIRED, SKIPPED, CANCELLED, FAILED theo contract) có quy tắc cập nhật rõ ràng; không cho scheduler tự biến một terminal state về PENDING chỉ vì đến cron.

**UNKNOWN không được mặc định là FAILED hoặc EXPIRED.** Đó là trạng thái cần đối soát vì có thể server đã nhận email.

## 7. Deadline là ranh giới bắt đầu attempt, không phải phép thu hồi email

Giả sử:

~~~text
expires_at = 10:00:00

09:59:59.700  Worker bắt đầu SMTP submission
10:00:02.400  SMTP server trả 250 Accepted
~~~

Nếu policy quy định “không **bắt đầu** attempt sau expires_at”, attempt đã bắt đầu lúc 09:59:59.700 có thể hợp lệ. Không được thay kết quả SUBMITTED thành EXPIRED chỉ vì accepted_at sau 10:00.

Ngược lại:

~~~text
10:00:01.000  Worker bắt đầu SMTP attempt mới
~~~

Lần gửi này đã vi phạm deadline theo policy nếu expires_at là 10:00:00.

Cần ghi rõ **deadline kiểm tra tại thời điểm nào**:

- Trước khi claim?
- Trước khi tạo MimeMessage?
- Ngay trước khi gọi JavaMailSender.send(...)?
- Ngay trước khi truyền SMTP DATA?

Một ứng dụng thông thường có thể kiểm tra **trước claim và ngay trước send**, nhưng không thể bảo đảm message không ra khỏi hệ thống sau deadline nếu send đang thực hiện, trừ khi hạ tầng/provider hỗ trợ lịch gửi và hủy tương ứng.

## 8. Không đánh đồng business deadline với SMTP timeout

Hai thông số khác nhau:

~~~text
Business deadline:
  expires_at = thời điểm không được bắt đầu gửi nữa

SMTP transport timeout:
  mail.smtp.connectiontimeout = giới hạn chờ TCP connect
  mail.smtp.timeout           = giới hạn socket read
  mail.smtp.writetimeout      = giới hạn socket write
~~~

SMTP timeout giúp tránh thread bị treo quá lâu, nhưng **không tự hủy một notification quá hạn**. Ngược lại, expires_at không tự ngắt một socket đã mở và không tự giới hạn DNS/TCP/TLS.

Nếu một email chỉ còn 2 giây hiệu lực, việc cho phép bắt đầu send với socket timeout tổng cộng lâu hơn 2 giây cần được cân nhắc theo policy. Một chiến lược là đặt **minimum remaining validity**:

~~~text
remaining = expires_at - now

if remaining < minimumSendBudget:
    EXPIRE_OR_DEFER_BY_POLICY
else:
    ALLOW_ATTEMPT
~~~

**minimumSendBudget** là ngưỡng an toàn do ứng dụng chọn, không bảo đảm SMTP hoàn thành trong đúng thời gian đó. Nếu email/token đã hết hiệu lực khi người nhận mở thư, nội dung nên chỉ rõ cách yêu cầu lại mã hoặc hành động mới.

## 9. Những nguyên nhân làm email bị trễ hoặc bỏ qua

Nên phân loại nguyên nhân vận hành:

| Nhóm | Ví dụ | Dạng xử lý |
|---|---|---|
| **SCHEDULER_DELAY** | Scheduler không chạy, cron sai | Khôi phục scheduler và đối chiếu hàng đợi |
| **CAPACITY_BACKLOG** | Worker thiếu thread/slot | Scale/cân bằng tải, giám sát tuổi hàng chờ |
| **PROVIDER_THROTTLE** | ESP giới hạn recipients/s | Backoff, defer theo quota |
| **PROVIDER_OUTAGE** | DNS/TCP/TLS/SMTP lỗi | Retry có giới hạn và deadline |
| **BUSINESS_OBSOLETE** | Đơn đã thanh toán, event kết thúc | SKIPPED |
| **CONSENT_REVOKED** | Người nhận unsubscribe | SUPPRESSED/SKIPPED theo policy |
| **REQUEST_CANCELLED** | User hoặc admin hủy | CANCELLED |
| **INVALID_RECIPIENT** | Địa chỉ không hợp lệ theo validation | SKIPPED hoặc FAILED_VALIDATION |
| **DUPLICATE_INTENT** | Event bị gửi lại | Dedup, không tạo job mới |
| **MISCONFIGURED_WINDOW** | scheduled_at vượt expires_at | Từ chối hoặc đánh trạng thái không hợp lệ |
| **LEASE_STUCK** | Worker chết sau claim | Reclaim theo lease và đánh giá deadline |
| **UNKNOWN_SUBMISSION** | Mất phản hồi sau DATA | Reconcile, không tự kết luận chưa gửi |

Không dùng một **skip_reason = OTHER** cho tất cả trường hợp. Một bộ reason code hữu hạn giúp dashboard, hỗ trợ khách hàng và runbook phân biệt lỗi cấu hình với quyết định nghiệp vụ.

## 10. Email bị bỏ qua có thể là kết quả chính xác

Một tỷ lệ SKIPPED cao không tự động chứng minh hệ thống gửi mail hỏng.

Ví dụ:

~~~text
08:00  Đơn hàng ORD-100 được tạo
08:05  Lập lịch nhắc thanh toán lúc 09:00
08:30  Khách hàng thanh toán thành công
09:00  Worker nhìn thấy đơn đã thanh toán
09:00  Notification chuyển SKIPPED/BUSINESS_OBSOLETE
~~~

Ở đây **không gửi email** là hành vi đúng. Nên ghi nhận:

- Notification nào bị bỏ qua.
- Policy nào đã áp dụng.
- Lý do **ORDER_ALREADY_PAID** hoặc một mã tương đương.
- Thời điểm quyết định.
- Không có SMTP attempt nào được tạo nếu đã skip trước send.

Ngược lại, một email bị skip do **worker thiếu capacity cho đến hết deadline** là tín hiệu chất lượng dịch vụ cần được giám sát. Cùng trạng thái EXPIRED, nhưng lý do **CAPACITY_BACKLOG** khác với **USER_CANCELLED** hoặc **TOKEN_TTL_ENDED**.

## 11. Kiến trúc lập lịch với transactional outbox

Một kiến trúc thực tế có thể như sau:

~~~text
Business transaction
      |
      +-- Save business state
      +-- Insert email intent with schedule/deadline
      |
      v
Commit database transaction
      |
      v
Scheduled outbox storage
      |
      +-- Expiration scanner -> mark EXPIRED
      |
      +-- Cancellation/business changes -> mark SKIPPED/CANCELLED
      |
      +-- Due-job scheduler -> claim eligible jobs
                                     |
                                     v
                             Revalidate policy
                                     |
                                     v
                          SMTP attempt via JavaMailSender
                                     |
                +--------------------+-------------------+
                |                    |                   |
                v                    v                   v
            SUBMITTED            RETRY_WAIT            UNKNOWN
                |
                v
           Provider feedback
~~~

Tách **business transaction** khỏi **SMTP submission** giúp tránh giữ database transaction mở trong lúc DNS, TCP, TLS, authentication và DATA đang diễn ra.

Khi worker restart, dữ liệu outbox vẫn tồn tại để:

- Nhặt lại những job đến hạn chưa được xử lý.
- Hết hạn những job quá deadline.
- Retry có backoff nếu còn hiệu lực.
- Đối soát job bị kẹt trạng thái PROCESSING.
- Giải thích vì sao một email không được gửi.

**@Scheduled** chỉ kích hoạt công việc theo thời gian; nó không tự cung cấp outbox, tính bền vững, transaction, idempotency hoặc lịch sử skip.

## 12. Thiết kế bảng outbox có deadline và reason code

Một schema PostgreSQL minh họa:

~~~sql
CREATE TABLE email_outbox (
    id                  UUID PRIMARY KEY,
    tenant_id           VARCHAR(120) NOT NULL,
    notification_type   VARCHAR(80) NOT NULL,
    business_key        VARCHAR(240) NOT NULL,
    recipient_ref       VARCHAR(240) NOT NULL,
    payload_ref         TEXT NOT NULL,

    status              VARCHAR(40) NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL,
    scheduled_at        TIMESTAMPTZ NOT NULL,
    next_attempt_at     TIMESTAMPTZ NOT NULL,
    expires_at          TIMESTAMPTZ,

    attempt_count       INTEGER NOT NULL DEFAULT 0,
    claim_token         UUID,
    claimed_at          TIMESTAMPTZ,
    lease_until         TIMESTAMPTZ,

    submitted_at        TIMESTAMPTZ,
    finished_at         TIMESTAMPTZ,
    outcome_reason      VARCHAR(100),
    last_error_category VARCHAR(100),
    version             BIGINT NOT NULL DEFAULT 0,

    CHECK (attempt_count >= 0),
    CHECK (
        expires_at IS NULL
        OR scheduled_at < expires_at
    )
);

CREATE UNIQUE INDEX uq_email_intent
ON email_outbox (
    tenant_id,
    notification_type,
    business_key,
    recipient_ref
);

CREATE INDEX ix_email_outbox_due
ON email_outbox (next_attempt_at, id)
WHERE status IN ('PENDING', 'RETRY_WAIT');

CREATE INDEX ix_email_outbox_expiration
ON email_outbox (expires_at, id)
WHERE status IN ('PENDING', 'RETRY_WAIT');
~~~

Schema này là **ví dụ do ứng dụng định nghĩa**, không phải bảng mặc định của Spring Mail.

Các quyết định cần làm rõ:

- **expires_at nullable** có nghĩa job không có business expiry, nhưng vẫn phải có retention/retry policy.
- **scheduled_at < expires_at** là rule nghiêm ngặt minh họa. Nếu sản phẩm muốn cho phép deadline bằng scheduled_at, cần định nghĩa semantics khác thay vì sửa âm thầm constraint.
- **recipient_ref** có thể tham chiếu một record recipient bảo vệ PII thay vì lưu email thô trong hàng đợi.
- Unique intent key phải đúng đơn vị idempotency. Hai email khác nhau về kỳ gửi/campaign có thể cần key khác.
- **claim_token** và **lease_until** giúp quản lý quyền xử lý khi chạy nhiều worker.
- **outcome_reason** phải được chuẩn hóa, không chứa exception text hoặc dữ liệu cá nhân.

Nếu dùng **PostgreSQL**, có thể dựa vào index theo status và thời gian để quét nhanh những job chưa kết thúc. Cần điều chỉnh chỉ mục theo lượng dữ liệu, partitioning và truy vấn thật của ứng dụng.

## 13. Giữ bất biến thời gian và trạng thái

Trước khi ghi outbox, nên kiểm tra:

~~~text
scheduled_at >= created_at?       (nếu policy không cho lịch quá khứ)
expires_at > scheduled_at?        (nếu có deadline)
next_attempt_at >= scheduled_at?  (trừ các trường hợp cần retry ngay)
tenant and recipient authorized?
notification still relevant?
~~~

Không phải mọi thông báo đều cần **scheduled_at >= created_at**. Một dữ liệu legacy được đồng bộ muộn có thể có lịch gốc trong quá khứ và policy cho phép gửi bù. Quan trọng là **định nghĩa cách xử lý** thay vì không kiểm tra.

Một số invariant quan trọng:

1. Job **SUBMITTED** không bị scanner chuyển thành EXPIRED.
2. Job **CANCELLED/SKIPPED** không được worker tự chạy lại.
3. Job quá hạn không được claim cho một **SMTP attempt mới**.
4. Job có **UNKNOWN outcome** không được coi chắc chắn chưa gửi.
5. Job có claim token/lease chỉ được worker sở hữu cập nhật kết quả.
6. Một intent bị replay không tạo thêm một job cùng business key.
7. Khi thay đổi deadline, cần kiểm tra phiên bản policy và quyền thay đổi.
8. Nếu notification có nhiều recipient, có thể cần state/deadline theo từng recipient chứ không chỉ một row tổng.

**Invariant phải được bảo vệ tại database/state transition boundary**, không chỉ bằng một if trước khi gọi service. Giữa lúc đọc điều kiện và lúc ghi, các thread/worker khác có thể thay đổi dữ liệu.

## 14. Chọn job đến hạn: due không có nghĩa gửi ngay

Một job đủ điều kiện bắt đầu xử lý khi:

~~~text
status in (PENDING, RETRY_WAIT)
AND next_attempt_at <= now
AND (expires_at IS NULL OR expires_at > now)
AND tenant/campaign/recipient policy allows
AND capacity available
~~~

Ví dụ truy vấn chỉ để quan sát những job đến hạn:

~~~sql
SELECT
    id,
    tenant_id,
    notification_type,
    scheduled_at,
    next_attempt_at,
    expires_at
FROM email_outbox
WHERE status IN ('PENDING', 'RETRY_WAIT')
  AND next_attempt_at <= statement_timestamp()
  AND (
      expires_at IS NULL
      OR expires_at > statement_timestamp()
  )
ORDER BY next_attempt_at, id
LIMIT 100;
~~~

**Không dùng riêng câu SELECT này làm cơ chế claim trong môi trường đa worker**, vì hai worker có thể đọc cùng một row rồi cùng gửi.

Ngoài điều kiện thời gian trong SQL, worker vẫn cần kiểm tra policy động: một đơn hàng có thể đã thanh toán, user đã unsubscribe hoặc tenant bị vô hiệu hóa ngay trước khi job đến lượt.

## 15. Hết hạn job chờ bằng cập nhật nguyên tử

Một scanner có thể chuyển các job chưa gửi đã hết hạn sang EXPIRED:

~~~sql
UPDATE email_outbox
SET
    status = 'EXPIRED',
    outcome_reason = 'DEADLINE_REACHED',
    finished_at = statement_timestamp(),
    version = version + 1
WHERE status IN ('PENDING', 'RETRY_WAIT')
  AND expires_at IS NOT NULL
  AND expires_at <= statement_timestamp();
~~~

Điều kiện **status IN ('PENDING', 'RETRY_WAIT')** rất quan trọng:

- Không sửa job đã SUBMITTED.
- Không ghi đè job đã CANCELLED hoặc SKIPPED.
- Không tự động chuyển job đang SENDING thành EXPIRED, vì SMTP có thể đang chạy.
- Không tự chuyển UNKNOWN thành EXPIRED trước khi đối soát.

Nếu lượng row lớn, không nên update hàng triệu bản ghi trong một transaction kéo dài. Có thể phân batch:

~~~sql
WITH expired_batch AS (
    SELECT id
    FROM email_outbox
    WHERE status IN ('PENDING', 'RETRY_WAIT')
      AND expires_at IS NOT NULL
      AND expires_at <= statement_timestamp()
    ORDER BY expires_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT 500
)
UPDATE email_outbox AS o
SET
    status = 'EXPIRED',
    outcome_reason = 'DEADLINE_REACHED',
    finished_at = statement_timestamp(),
    version = o.version + 1
FROM expired_batch AS b
WHERE o.id = b.id
RETURNING o.id, o.tenant_id, o.notification_type;
~~~

**FOR UPDATE SKIP LOCKED** tránh đợi những row đang được transaction khác khóa, phù hợp với worker/scanner cạnh tranh. Cần hiểu rằng một row bị skip có thể vẫn còn và cần được quét lại ở lượt tiếp theo.

Đây là ví dụ PostgreSQL. Không giả định cú pháp **RETURNING / SKIP LOCKED** giống nhau trên mọi database.

## 16. Claim job đồng thời: chặn hai worker gửi cùng một row

Khi có nhiều worker:

~~~text
Worker A: thấy N100 đến hạn
Worker B: thấy N100 đến hạn
Worker A: gửi SMTP
Worker B: gửi SMTP
~~~

Để tránh hai worker claim một row, có thể thực hiện một transaction ngắn:

~~~sql
WITH due_batch AS (
    SELECT id
    FROM email_outbox
    WHERE status IN ('PENDING', 'RETRY_WAIT')
      AND next_attempt_at <= statement_timestamp()
      AND (
          expires_at IS NULL
          OR expires_at > statement_timestamp()
      )
    ORDER BY next_attempt_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT 100
)
UPDATE email_outbox AS o
SET
    status = 'CLAIMED',
    claim_token = gen_random_uuid(),
    claimed_at = statement_timestamp(),
    lease_until = statement_timestamp() + INTERVAL '2 minutes',
    version = o.version + 1
FROM due_batch AS b
WHERE o.id = b.id
RETURNING
    o.id,
    o.tenant_id,
    o.claim_token,
    o.expires_at,
    o.next_attempt_at;
~~~

Khi transaction commit, worker có một **claim token duy nhất** cho mỗi row. Token được dùng trong các update sau để tránh worker cũ ghi đè kết quả của worker mới.

**Claim không đồng nghĩa đã gửi.** Sau claim, worker cần kiểm tra trạng thái nghiệp vụ, deadline, recipient permission, cancellation và năng lực provider trước khi mở SMTP session.

**Lưu ý:** Hàm **gen_random_uuid()** phụ thuộc khả năng PostgreSQL phiên bản đang triển khai; có thể dùng một UUID do ứng dụng cấp nếu không có hàm này. Lease 2 phút chỉ minh họa, không phải thời hạn mặc định.

## 17. Khi scanner và worker cạnh tranh cùng một job

Giả sử N100 có:

~~~text
status = PENDING
expires_at = 10:00
~~~

Tại thời điểm 10:00, hai tác vụ có thể xảy ra:

~~~text
ExpirationScanner       SendingWorker
      |                        |
      |  UPDATE EXPIRED        |  CLAIM due job
      |                        |
      +------------+-----------+
                   |
             Database row lock
~~~

Với cập nhật có điều kiện:

- Nếu scanner khóa/update trước, worker không claim được N100 như PENDING nữa.
- Nếu worker claim trước deadline, N100 chuyển CLAIMED. Scanner không được tùy ý đánh dấu EXPIRED như thể chưa ai xử lý.
- Worker sau claim vẫn phải kiểm tra deadline ngay trước send. Nếu deadline đã tới, chuyển EXPIRED có điều kiện theo claim token.

Không chỉ dựa vào một kiểm tra thời gian lúc đọc object: trạng thái có thể thay đổi bởi admin/user hoặc scanner trong thời gian worker xử lý.

### Đừng giữ database transaction trong lúc gửi SMTP

Claim cần transaction ngắn và commit trước khi bắt đầu I/O mạng. Gọi **JavaMailSender.send(...)** trong một transaction giữ row lock nhiều giây hoặc phút làm tăng lock contention, đồng thời email đã gửi không được tự thu hồi nếu transaction rollback.

## 18. Kiểm tra deadline lần nữa trước khi send

Giữa lúc claim và lúc bắt đầu SMTP có thể xảy ra:

- Render template mất nhiều giây.
- Attachment cần tải từ object storage.
- Worker chờ semaphore hoặc provider rate token.
- Người dùng hủy request.
- Campaign bị tạm dừng.
- Deadline đã tới.

Vì vậy nên có **final admission gate**:

~~~text
CLAIMED
   |
   +-- expires_at <= now --> EXPIRED
   +-- cancellation --> CANCELLED
   +-- business condition false --> SKIPPED
   +-- no capacity --> DEFER (nếu còn hạn)
   |
   v
Transition to SENDING with claim_token
   |
   v
JavaMailSender.send(...)
~~~

Ví dụ update có điều kiện:

~~~sql
UPDATE email_outbox
SET
    status = 'SENDING',
    version = version + 1
WHERE id = :id
  AND status = 'CLAIMED'
  AND claim_token = :claimToken
  AND (
      expires_at IS NULL
      OR expires_at > statement_timestamp()
  )
RETURNING id;
~~~

Nếu không trả row, worker không được gửi ngay; cần đọc lại trạng thái để xác định **hết hạn, bị hủy, mất claim hoặc xung đột**.

**Giới hạn cần nói rõ:** luôn có một khoảng giữa DB transition và network call. Một cancellation tới ngay sau khi chuyển SENDING có thể không ngăn được email. Nếu yêu cầu không gửi sau thời điểm hủy với độ chính xác tuyệt đối, cần cơ chế kiểm soát ngay ở tầng provider/transport và chấp nhận giới hạn của SMTP. Application state guard giảm race, không tạo phép thu hồi vô điều kiện.

## 19. Java Clock giúp logic deadline có thể dự đoán

Đừng gọi **Instant.now()** rải rác trong tất cả service; điều đó làm test ở ranh giới thời gian khó ổn định.

Trong Spring, có thể inject **Clock**:

~~~java
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class NotificationTimeConfiguration {

    @Bean
    public Clock notificationClock() {
        return Clock.systemUTC();
    }
}
~~~

Một policy service:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Optional;
import org.springframework.stereotype.Component;

@Component
public class SendDeadlinePolicy {

    private final Clock clock;

    public SendDeadlinePolicy(Clock clock) {
        this.clock = clock;
    }

    public boolean mayStartAttempt(Instant expiresAt) {
        return expiresAt == null
                || clock.instant().isBefore(expiresAt);
    }

    public Optional<java.time.Duration> remaining(
            Instant expiresAt
    ) {
        if (expiresAt == null) {
            return Optional.empty();
        }
        return Optional.of(
                java.time.Duration.between(
                        clock.instant(), expiresAt
                )
        );
    }
}
~~~

**Optional.empty()** biểu thị không có deadline thay vì dùng một Duration giả rất dài. Duration âm nghĩa là deadline đã qua. Ở ranh giới chính xác **now == expiresAt**, phương thức **mayStartAttempt** trả false.

**Quan trọng:** code Java dùng Clock inject, còn SQL phía trên dùng **statement_timestamp()** của database. Hai đồng hồ có thể lệch. Với các quyết định state transition quan trọng, nên chọn một nguồn thời gian có chủ đích (thường DB time cho atomic updates) và giám sát clock skew; không cho rằng check ở JVM và check ở DB luôn xảy ra tại cùng một Instant.

## 20. @Scheduled quét expiration và công việc đến hạn

Spring Scheduling có thể kích hoạt scanner:

~~~java
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableScheduling
public class NotificationSchedulingConfiguration {
}
~~~

Một scheduled component:

~~~java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class ExpirationSweepJob {

    private final ExpirationService expirationService;

    public ExpirationSweepJob(
            ExpirationService expirationService
    ) {
        this.expirationService = expirationService;
    }

    @Scheduled(fixedDelay = 30000)
    public void sweepExpired() {
        expirationService.expireEligibleBatches();
    }
}
~~~

**ExpirationService** là service ứng dụng thực hiện các câu lệnh update có điều kiện, phân batch và ghi event/audit phù hợp. Chọn delay 30 giây chỉ minh họa.

Một scanner chạy mỗi 30 giây **không bảo đảm job hết hạn được đánh dấu đúng tới mili giây**; có thể bị trễ do scheduler, tải máy hoặc process outage. Vì vậy **send worker vẫn phải chặn quá hạn tại admission gate**. Scanner phục vụ dọn trạng thái và quan sát, không phải lớp bảo vệ duy nhất.

### Scheduler chạy trên nhiều instance

Nếu cùng một @Scheduled method chạy ở 5 pod, nó có thể quét 5 lần. Cập nhật trạng thái có điều kiện giúp giảm nguy cơ ghi đè nhưng vẫn tăng tải database.

Có thể dùng:

- Leader election/distributed lock có lease phù hợp.
- Database batching với **SKIP LOCKED**.
- Một scheduler service duy nhất có failover.
- Partition/shard hàng đợi theo tenant hoặc time bucket.

Không dựa vào một **static boolean** hoặc khóa trong bộ nhớ một JVM để điều phối toàn cluster.

## 21. Múi giờ và daylight saving time (DST)

Người dùng có thể chọn gửi:

~~~text
“09:00 sáng theo giờ của tôi, ngày 20/11”
~~~

Ứng dụng cần tách:

- **LocalDateTime** do người dùng nhập.
- **ZoneId** IANA của người dùng, ví dụ **Asia/Ho_Chi_Minh**.
- **Instant** được chuẩn hóa để lưu và so sánh trong scheduler.

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.Instant;

LocalDateTime local =
        LocalDateTime.of(2026, 11, 20, 9, 0);

ZoneId zone =
        ZoneId.of("Asia/Ho_Chi_Minh");

Instant scheduledAt =
        local.atZone(zone).toInstant();
~~~

**Instant** phù hợp để so sánh deadline và lưu ở TIMESTAMPTZ/UTC. **ZoneId** vẫn cần được giữ nếu người dùng muốn lịch định kỳ theo giờ địa phương.

Ở các timezone có DST, một local time có thể **không tồn tại hoặc xảy ra hai lần**. Nếu ứng dụng lên lịch theo giờ địa phương, phải định nghĩa cách xử lý gap/overlap; không giả định **local.atZone(zone)** luôn phản ánh đúng kỳ vọng nếu policy chưa được quyết định.

### Deadline gắn với sự kiện

Với một cuộc họp bắt đầu lúc 10:00 theo ZoneId, email nhắc trước 15 phút có thể có:

~~~text
scheduled_at = meeting_start_instant - 15 minutes
expires_at   = meeting_start_instant
~~~

Nếu cuộc họp được dời lịch, scheduler cần cập nhật cả scheduled_at và expires_at hoặc hủy intent cũ và tạo intent mới theo idempotency policy. Không chỉ sửa Subject mà giữ deadline lỗi thời.

## 22. Ví dụ Spring JDBC quét và hết hạn theo batch

Với **NamedParameterJdbcTemplate**, có thể triển khai repository quét những job PENDING/RETRY_WAIT đã qua deadline:

~~~java
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class EmailExpirationRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public EmailExpirationRepository(
            NamedParameterJdbcTemplate jdbc
    ) {
        this.jdbc = jdbc;
    }

    @Transactional
    public List<UUID> expireBatch(int batchSize) {
        if (batchSize < 1 || batchSize > 1000) {
            throw new IllegalArgumentException(
                    "batchSize must be between 1 and 1000"
            );
        }

        String sql = """
            WITH due AS (
                SELECT id
                FROM email_outbox
                WHERE status IN ('PENDING', 'RETRY_WAIT')
                  AND expires_at IS NOT NULL
                  AND expires_at <= statement_timestamp()
                ORDER BY expires_at, id
                FOR UPDATE SKIP LOCKED
                LIMIT :limit
            )
            UPDATE email_outbox AS o
            SET status = 'EXPIRED',
                outcome_reason = 'DEADLINE_REACHED',
                finished_at = statement_timestamp(),
                version = o.version + 1
            FROM due
            WHERE o.id = due.id
            RETURNING o.id
            """;

        return jdbc.query(
                sql,
                Map.of("limit", batchSize),
                (rs, rowNum) -> (UUID) rs.getObject("id")
        );
    }
}
~~~

Đoạn code sử dụng **text block của Java** và **PostgreSQL**. Nó chỉ chuyển trạng thái những row chưa bị claim/gửi; không xử lý các trạng thái SENDING/UNKNOWN.

Để phục vụ audit, một triển khai có thể ghi các ID vừa chuyển trạng thái vào **outcome event table** trong cùng transaction. Không tạo một email thông báo thứ hai cho user chỉ vì scanner vừa đánh dấu EXPIRED, trừ khi chính sách rõ ràng yêu cầu; bản thân email thông báo lỗi cũng có thể cần deadline riêng.

### Không quét toàn bộ backlog trong một transaction dài

Một service có thể gọi nhiều lần **expireBatch(500)**, mỗi lần qua một public repository method có transaction riêng:

~~~java
import org.springframework.stereotype.Service;

@Service
public class ExpirationService {

    private final EmailExpirationRepository repository;

    public ExpirationService(
            EmailExpirationRepository repository
    ) {
        this.repository = repository;
    }

    public void expireEligibleBatches() {
        for (int i = 0; i < 20; i++) {
            int expired = repository.expireBatch(500).size();
            if (expired == 0) {
                break;
            }
        }
    }
}
~~~

Với cách này, một lượt scheduler có thể xử lý tối đa 10.000 row theo lô nhỏ. Các giới hạn 500/20 chỉ là ví dụ; cần đo database load và giới hạn runtime thực tế.

**Điểm Spring transaction cần chú ý:** nếu đặt **@Transactional** lên một method rồi gọi method đó bằng **this.method()** trong cùng object, proxy transaction của Spring có thể không được áp dụng như mong đợi. Ở ví dụ trên, service gọi public method trên một bean repository riêng.

## 23. SKIPPED do trạng thái nghiệp vụ: phải kiểm tra gần thời điểm gửi

Ví dụ nhắc thanh toán:

~~~text
Tạo đơn ORD-200 lúc 08:00
Đặt lịch reminder 09:00
Khách thanh toán lúc 08:59:58
Worker lấy job lúc 09:00:00
~~~

Nếu payload lưu một snapshot:

~~~json
{
  "orderId": "ORD-200",
  "paymentStatus": "UNPAID"
}
~~~

thì trạng thái snapshot đã lỗi thời. **Payload snapshot** vẫn hữu ích để dựng nội dung ổn định, nhưng một số điều kiện gửi phải được xác minh theo **business state hiện tại**.

Một policy checker:

~~~java
public interface NotificationEligibilityPolicy {
    EligibilityDecision evaluate(
            String tenantId,
            String notificationType,
            String businessKey
    );
}

public record EligibilityDecision(
        boolean allowed,
        String reasonCode
) {
    public static EligibilityDecision allow() {
        return new EligibilityDecision(true, "ELIGIBLE");
    }

    public static EligibilityDecision skip(String reason) {
        return new EligibilityDecision(false, reason);
    }
}
~~~

Ví dụ **PAYMENT_REMINDER**:

~~~text
if order does not exist:
    SKIP: ORDER_NOT_FOUND
else if order paid:
    SKIP: ORDER_ALREADY_PAID
else if order cancelled:
    SKIP: ORDER_CANCELLED
else:
    ALLOW
~~~

Lưu ý **time-of-check/time-of-use**: một đơn có thể được thanh toán ngay sau khi worker kiểm tra nhưng trước khi SMTP được gọi. Nếu nghiệp vụ yêu cầu ngăn chặn mạnh, cần phối hợp transaction/conditional outbox update với luồng cập nhật order. Với trạng thái ở một dịch vụ ngoài, không có transaction chung nên phải định nghĩa rõ mức bảo đảm và cách xử lý race.

## 24. Cập nhật SKIPPED có điều kiện, không ghi đè trạng thái khác

Giả sử worker đã claim một notification và policy xác định không còn cần gửi. Nó chỉ nên đổi trạng thái khi vẫn sở hữu job:

~~~sql
UPDATE email_outbox
SET
    status = 'SKIPPED',
    outcome_reason = :reason,
    finished_at = statement_timestamp(),
    claim_token = NULL,
    lease_until = NULL,
    version = version + 1
WHERE id = :id
  AND status = 'CLAIMED'
  AND claim_token = :claimToken
RETURNING id;
~~~

Nếu không có row được trả về:

- Worker có thể đã mất lease/ownership.
- Người dùng đã hủy notification.
- Worker khác đã hoàn tất.
- Một transition khác đã xảy ra.

Không tự retry câu update mà bỏ điều kiện status/token. Hãy đọc lại trạng thái và áp dụng state machine.

### Reason code nên là một allowlist

Ví dụ:

~~~java
public enum SkipReason {
    ORDER_ALREADY_PAID,
    ORDER_CANCELLED,
    EVENT_ALREADY_FINISHED,
    RECIPIENT_SUPPRESSED,
    USER_PREFERENCE_CHANGED,
    CAMPAIGN_CANCELLED,
    DUPLICATE_INTENT,
    INVALID_RECIPIENT,
    POLICY_NOT_ELIGIBLE
}
~~~

Không lưu nguyên nội dung lỗi, Subject, email người nhận hoặc dữ liệu nhạy cảm vào **outcome_reason**. Các bằng chứng chi tiết, nếu cần, phải lưu ở audit store có kiểm soát quyền và retention.

## 25. Grace period và cửa sổ gửi cho phép

Một email có thể cần gửi tại một thời điểm cụ thể nhưng vẫn được phép trễ trong một cửa sổ.

Ví dụ:

~~~text
scheduled_at = 09:00
grace_period = 15 minutes
expires_at   = 09:15
~~~

Một policy có thể tính:

~~~java
import java.time.Duration;
import java.time.Instant;

public Instant deadlineFromSchedule(
        Instant scheduledAt,
        Duration grace
) {
    if (grace.isNegative() || grace.isZero()) {
        throw new IllegalArgumentException(
                "Grace period must be positive"
        );
    }
    return scheduledAt.plus(grace);
}
~~~

Không nên áp dụng một grace period cho mọi loại:

- OTP có expiry dựa trên token, có thể chỉ vài phút.
- Nhắc cuộc họp nên hết hạn theo event start.
- Daily digest có thể cần bỏ khi kỳ tiếp theo đã tạo digest mới.
- Hóa đơn có thể có SLA tối đa nhưng không nên bị xóa nếu nghĩa vụ pháp lý còn.

**Grace period không phải phần kéo dài tự động của token TTL.** Một email chứa link hết hạn lúc 09:05 không trở nên hữu ích khi scheduler cho phép gửi tới 09:15.

## 26. Retry phải tôn trọng deadline

Giả sử SMTP bị lỗi tạm thời lúc 09:03 và worker muốn retry sau 10 phút:

~~~text
expires_at = 09:10
now = 09:03
backoff = 10 minutes
next_attempt_at = 09:13
~~~

Không nên lên lịch retry 09:13 rồi để worker sau đó mới phát hiện đã quá hạn, nếu policy cho phép quyết định ngay:

~~~java
import java.time.Duration;
import java.time.Instant;

public boolean canRetryBeforeDeadline(
        Instant now,
        Duration backoff,
        Instant expiresAt
) {
    Instant next = now.plus(backoff);
    return expiresAt == null || next.isBefore(expiresAt);
}
~~~

Ở ví dụ:

~~~text
09:03 + 10 minutes = 09:13
09:13 >= 09:10
=> Không lên một SMTP attempt mới sau deadline.
~~~

Có thể chuyển sang EXPIRED với reason **RETRY_WINDOW_EXHAUSTED**, hoặc giữ một trạng thái terminal như **FAILED_DEADLINE** theo policy.

### Đừng retry mãi bằng cách giảm backoff về 0

Một implementation cố “nhét” retry cuối vào thời gian còn lại bằng cách giảm backoff xuống vài mili giây có thể tạo **retry storm** khi provider đang lỗi. Cần kết hợp:

- Max attempts.
- Min backoff.
- Jitter.
- Provider Retry-After khi có.
- Per-tenant và global retry budget.
- Deadline và minimum remaining validity.

Nếu không đủ thời gian để retry an toàn, **ngừng thử** có thể là quyết định đúng.

## 27. Sự khác biệt giữa lỗi retryable và hết hạn

Giả sử:

~~~text
N100: SMTP 451 lúc 09:00, expires_at 10:00
N101: SMTP 451 lúc 09:59, expires_at 10:00
~~~

Lỗi 451 có thể là **tạm thời**, nhưng N101 có thể không đủ thời gian cho backoff.

Do đó quyết định:

~~~text
shouldRetry =
    errorIsTransient
    AND attemptCount < maxAttempts
    AND deadlineAllowsAnotherAttempt
    AND tenantAndProviderPolicyAllows
~~~

Kết quả nên phân biệt:

| Điều kiện | Trạng thái |
|---|---|
| Lỗi tạm thời, còn thời gian | RETRY_WAIT |
| Lỗi tạm thời nhưng hết deadline | EXPIRED/RETRY_WINDOW_EXHAUSTED |
| Lỗi không phục hồi theo policy | FAILED |
| Không chắc provider đã accepted | UNKNOWN |
| Job bị hủy khi đang chờ retry | CANCELLED |

Việc trộn mọi tình huống thành FAILED làm mất khả năng hiểu vì sao email không tới người nhận: do provider từ chối, do timeout mơ hồ hay do deadline nghiệp vụ đã hết.

## 28. Email bị hủy bởi người dùng hoặc quản trị viên

**Cancellation** khác với **expiration**:

- Expiration xảy ra vì thời gian có hiệu lực đã trôi qua.
- Cancellation là một hành động được ủy quyền để ngừng ý định gửi.

Một API hủy nên:

1. Xác thực actor và tenant.
2. Kiểm tra actor có quyền hủy notification/campaign.
3. Xác định trạng thái hiện tại.
4. Thực hiện transition có điều kiện.
5. Ghi actor, reason và timestamp vào audit.
6. Trả kết quả có ngữ nghĩa đúng nếu email đã SENDING hoặc SUBMITTED.

Ví dụ hủy job chưa được worker claim:

~~~sql
UPDATE email_outbox
SET
    status = 'CANCELLED',
    outcome_reason = 'USER_CANCELLED',
    finished_at = statement_timestamp(),
    version = version + 1
WHERE id = :id
  AND tenant_id = :tenantId
  AND status IN ('PENDING', 'RETRY_WAIT')
RETURNING id;
~~~

Nếu status đang CLAIMED, có thể dùng một **cancellation_requested_at** hoặc flag để worker nhìn thấy trước final gate. Nhưng nếu đã SENDING hoặc SUBMITTED, không thể hứa chắc hủy thành công.

**Không trả “đã thu hồi email” chỉ vì database được cập nhật CANCELLED**, nếu SMTP DATA có thể đã được chấp nhận.

## 29. Race giữa cancellation, expiry và SMTP submission

Một timeline:

~~~text
09:59:59.800  Worker kiểm tra deadline và claim token
09:59:59.900  Worker chuyển SENDING
10:00:00.000  Hết hạn
10:00:00.050  User yêu cầu CANCEL
10:00:00.100  SMTP DATA đang truyền
~~~

Có ba nguyên tắc:

1. **Không được chuyển SUBMITTED hoặc SENDING về CANCELLED một cách mù quáng.** Hệ thống phải biết cancel đã tới trước hay sau khi có thể ngăn việc gửi.
2. **Không dùng một kết quả “cancel success” chung cho mọi state.** Có thể trả CANCELLED_BEFORE_SUBMISSION, CANCEL_REQUESTED_TOO_LATE hoặc ALREADY_SUBMITTED tùy hợp đồng API.
3. **Không dùng deadline để phủ nhận một submission đã thực sự xảy ra.** Nếu SMTP accepted, phải giữ bằng chứng acceptance và gắn thêm annotation như SENT_AFTER_REQUESTED_CANCELLATION nếu có race.

Nếu provider cung cấp **scheduled send + cancel API**, có thể xây cơ chế hủy bên provider. Nhưng cần hiểu giới hạn và trạng thái provider trả về; việc gọi cancel không bảo đảm recall mọi email đã được relay tới mail server phía nhận.

## 30. Bỏ qua email khi recipient không còn được phép nhận

Một số điều kiện không nằm trong lịch mà nằm trong **quyền gửi tới người nhận**:

- Người dùng rút consent hoặc unsubscribe.
- Địa chỉ được đưa vào suppression list do hard bounce/spam complaint.
- Tài khoản bị khóa hoặc không còn tồn tại.
- Người dùng tắt loại thông báo không bắt buộc.
- Recipient bị xóa khỏi tenant hoặc không còn quyền truy cập nội dung.
- Một tenant/account bị vô hiệu hóa theo chính sách.

Ví dụ:

~~~text
08:00  User đăng ký nhận newsletter
08:10  Lập lịch marketing lúc 15:00
14:45  User unsubscribe
15:00  Scheduler chạy
       -> Bỏ qua newsletter
       -> SKIPPED/RECIPIENT_UNSUBSCRIBED
~~~

**Không được dùng consent snapshot từ lúc tạo job** như bằng chứng cuối cùng để gửi email marketing sau nhiều giờ hoặc nhiều ngày.

Nên kiểm tra lại consent/suppression ở giai đoạn phù hợp ngay trước gửi, đồng thời áp dụng chính sách riêng cho các email bắt buộc/quan trọng được pháp luật và sản phẩm cho phép. Không mặc định “transactional” có nghĩa được miễn mọi quy tắc quyền riêng tư hoặc anti-spam.

### Nhiều người nhận trong cùng message

Nếu một MimeMessage chứa 10 To/Cc/Bcc mà 2 recipient bị suppress trước giờ gửi:

- Không gửi tới 2 người đã bị chặn.
- Phải cập nhật danh sách recipient đã được phép tại thời điểm gửi.
- Cân nhắc việc thay đổi To/Cc/Bcc có làm lộ danh sách người nhận hay không.
- Quota/metrics phải tính theo số người nhận hợp lệ theo contract.
- Nên lưu trạng thái riêng cho từng **notification-recipient** khi cần delivery feedback và retry chính xác.

Với luồng cá nhân hóa hoặc nhạy cảm, **mỗi recipient một notification** thường đơn giản hơn để cô lập skip, expiration và outcome.

## 31. Thay đổi business state: skip hay gửi phiên bản mới?

Không phải mọi thay đổi nghiệp vụ đều có nghĩa bỏ gửi. Có thể cần thay đổi **nội dung hoặc loại email**.

Ví dụ đơn hàng:

~~~text
08:00  Order status = PREPARING
08:05  Schedule "Đơn đang được chuẩn bị" lúc 09:00
08:50  Order status = SHIPPED
09:00  Worker đến lượt
~~~

Nếu gửi email “Đơn đang được chuẩn bị” thì nội dung đã sai. Có thể chọn:

1. **SKIP obsolete notification** và để sự kiện SHIPPED tạo một email riêng.
2. **REPLACE notification** theo rule versioning, hủy job cũ và tạo job mới.
3. **RENDER CURRENT STATE** nếu email được thiết kế để phản ánh trạng thái hiện tại và semantics cho phép.

Không nên âm thầm biến nội dung của một notification đã được audit thành nội dung hoàn toàn khác mà vẫn giữ cùng business event ID, vì người vận hành sẽ khó đối soát.

Nếu chọn **replace**:

~~~text
Old intent N100 -> SKIPPED/SUPERSEDED
New intent N101 -> PENDING with new schedule/content
~~~

Cần có **supersedes_id** hoặc metadata tương đương để biết hai notification liên quan. Không được gửi cả N100 và N101 nếu nghiệp vụ xác định chúng loại trừ nhau.

## 32. Lập lịch định kỳ: xử lý những kỳ bị bỏ lỡ

Một cron job có thể chạy theo giờ/ngày:

~~~text
Every day at 08:00 -> send daily digest
~~~

Nếu dịch vụ ngừng hoạt động từ 07:50 đến 11:30, khi khởi động lại cần quyết định:

- **SKIP_MISSED**: bỏ kỳ 08:00 đã lỡ, chờ kỳ ngày sau.
- **CATCH_UP_ONCE**: chạy bù một kỳ nếu vẫn còn giá trị.
- **CATCH_UP_ALL**: chạy đủ các kỳ đã lỡ, nếu cần lưu báo cáo.
- **COALESCE**: gom các kỳ đã lỡ thành một bản tổng hợp.
- **ROLL_FORWARD**: dời job chưa gửi sang cửa sổ hợp lệ kế tiếp.

Đó là **misfire policy do ứng dụng/scheduler framework xác định**, không phải hành vi mặc định thống nhất của Spring **@Scheduled**.

### @Scheduled không phải lịch sử bền vững của mọi lần kích hoạt

Giả sử:

~~~java
@Scheduled(cron = "0 0 8 * * *", zone = "Asia/Ho_Chi_Minh")
public void createDailyDigest() {
    // create scheduled intent
}
~~~

Trong cấu hình đơn giản, **@Scheduled** chạy khi ứng dụng đang hoạt động; nó không tự lưu một record cho mọi lần cron dự kiến chạy trong thời gian application down.

Nếu sản phẩm yêu cầu chạy bù những kỳ bị bỏ lỡ, cần tạo một **schedule ledger** hoặc dùng một scheduler bền vững được cấu hình misfire policy rõ ràng.

Ví dụ key của một kỳ:

~~~text
(tenant_id, notification_kind, recipient_id, period_start)
~~~

Nhờ vậy một lần restart không tạo hai digest cho cùng ngày khi cron bị trigger/retried trùng.

## 33. Skip missed occurrence khác expire một job đã tồn tại

Hai trường hợp:

**A. Job đã được lưu trước outage**

~~~text
07:50  PENDING notification trong DB
08:00  Dự kiến gửi
08:05  expires_at
11:30  Service phục hồi
~~~

Scanner có thể chuyển record đó thành **EXPIRED**, vì có bằng chứng một intent đã được tạo và không còn hợp lệ.

**B. Chưa có job vì cron service down**

~~~text
08:00  Dự kiến cron tạo một notification
11:30  Service phục hồi
~~~

Không có record nào để scanner “expire”. Hệ thống cần **reconcile lịch định kỳ**:

- Xác định kỳ lẽ ra chạy.
- Kiểm tra có intent chưa (unique period key).
- Áp dụng misfire policy.
- Tạo job bù hoặc ghi **SKIPPED_MISSED_OCCURRENCE** trong schedule ledger nếu cần audit.

**Đừng nhầm “không có record” với “đã xử lý thành công”**. Đối với notification quan trọng theo chu kỳ, cần đo **expected occurrences vs actual created intents**.

## 34. Daily digest: bỏ kỳ hay gom nội dung?

Một digest có thể chứa dữ liệu trong khoảng:

~~~text
Ngày D:
  activity 00:00 - 23:59

Lịch:
  gửi lúc 08:00 ngày D+1
~~~

Nếu không gửi kịp tới 12:00:

- Có thể **gửi muộn** vì nội dung vẫn có giá trị.
- Có thể **bỏ kỳ** nếu notification kế tiếp sẽ tổng hợp lại nội dung.
- Có thể **gộp** các kỳ chưa gửi trong một bản báo cáo.
- Có thể chuyển sang **download center** nếu email quá dài hoặc nhiều kỳ dồn.

Điểm quan trọng là phải quản lý **coverage period** riêng với **scheduled_at**.

~~~text
digest_period_start = 2026-11-11T00:00:00Z
digest_period_end   = 2026-11-12T00:00:00Z
scheduled_at        = 2026-11-12T01:00:00Z
expires_at          = ...
~~~

Nếu scheduler bị trễ và tạo lại digest ở thời điểm khác, không nên truy vấn “24 giờ gần nhất tính từ lúc gửi” rồi làm sai nội dung kỳ. Dùng **period cố định** và idempotency theo kỳ.

## 35. Chiến dịch marketing: pause, cancel và kết thúc window

Một campaign có thể có trạng thái:

~~~text
DRAFT -> APPROVED -> SCHEDULED -> RUNNING
                           |
                           +-> PAUSED
                           +-> CANCELLED
                           +-> COMPLETED
~~~

Email thuộc campaign cần kiểm tra:

- Campaign đang RUNNING hay PAUSED?
- Giờ địa phương có nằm trong sending window không?
- Consent của recipient còn hợp lệ không?
- Ưu đãi/content có còn hiệu lực không?
- Tenant/provider quota có đủ không?
- Email đã gửi trong campaign này trước đó chưa?

**PAUSED** khác **CANCELLED**:

- PAUSED: tạm ngừng bắt đầu attempts mới; job có thể tiếp tục khi resume nếu còn hạn.
- CANCELLED: dừng vĩnh viễn những intents chưa submit theo chính sách.
- COMPLETED: đã hoàn thành hoặc kết thúc campaign; không tự phát sinh thêm intents.

Không đổi toàn bộ job thành SKIPPED khi chỉ PAUSED nếu sản phẩm muốn resume. Nhưng nếu thời gian PAUSED kéo dài qua expires_at, khi resume những job đó có thể phải EXPIRED.

### Dừng chiến dịch không chắc thu hồi được thư đã gửi

Provider có thể đã nhận và đưa email vào hàng chờ relay. Dù database đổi trạng thái campaign, các message đã SUBMITTED vẫn có thể tới người nhận. UI/admin nên hiển thị rõ số đã submitted, số còn chờ, số bị hủy và số chưa rõ.

## 36. Quota và rate limit: defer đến khi nào?

Một job đến hạn có thể chưa gửi vì:

~~~text
Tenant A rate: 20 recipients/second
Provider rate: 100 recipients/second
Global SMTP concurrency: 15
~~~

Nếu chưa được cấp rate token hoặc slot, worker có thể đặt lại:

~~~text
status = RETRY_WAIT hoặc DEFERRED_CAPACITY
next_attempt_at = proposed_retry_time
outcome_reason = CAPACITY_THROTTLED
~~~

Nhưng cần so sánh với deadline:

~~~text
if proposed_retry_time >= expires_at:
    EXPIRE (không thử SMTP mới)
else:
    DEFER
~~~

Một marketing campaign có thể chờ sang giờ tiếp theo; OTP có thể không. **Quy tắc defer phải dựa trên notification policy**, không chỉ “rate limiter bảo chờ 1 giờ thì cứ chờ”.

### Không chiếm worker slot khi chỉ đang chờ rate

Hàng nghìn job thiếu rate token không nên giữ hàng nghìn thread ngủ **Thread.sleep(...)** hoặc giữ DB transaction mở.

Nên:

1. Tính thời điểm thử lại.
2. Ghi trạng thái chờ và next_attempt_at.
3. Giải phóng slot/lease.
4. Để scheduler lấy lại khi đến hạn và vẫn hợp lệ.

Nếu job chờ nhiều lần tới hết deadline, kết quả EXPIRED nên có reason phản ánh **CAPACITY_BACKLOG/PROVIDER_THROTTLE**, để biết hệ thống đã không đáp ứng SLA thay vì gộp mọi thứ là lỗi business.

## 37. Ưu tiên email quan trọng khi backlog lớn

Giả sử:

~~~text
Tenant A:
   20.000 marketing emails pending
   10 OTP pending
~~~

Nếu worker lấy tất cả theo FIFO, 10 OTP có thể quá hạn trước khi được gửi.

Các biện pháp:

- **Priority class**: security/transactional/marketing.
- **Reserved capacity** cho notification TTL ngắn.
- **Earliest-deadline-first** trong một lớp phù hợp.
- **Fair scheduling** theo tenant, tránh tenant lớn chiếm hết queue.
- **Per-stream rate/concurrency**.
- **Admission control** khi chiến dịch quá lớn.
- **Backpressure** tới producer để không tạo backlog không thể xử lý.

Tuy nhiên, ưu tiên tuyệt đối mọi email security không giới hạn cũng có thể bị lạm dụng. Cần quota và xác thực stream, tránh caller tự gắn priority=security để vượt giới hạn.

### Độ ưu tiên không thay thế policy hết hạn

Ngay cả khi scheduler ưu tiên OTP, nếu OTP đã quá hạn thì vẫn không nên gửi. Không dùng ưu tiên cao như lý do bỏ qua expires_at.

## 38. Worker chết sau claim: lease hết hạn không chứng minh chưa gửi

Một worker có thể:

~~~text
09:00:00  Claim N100, lease_until = 09:02
09:00:01  Status = SENDING
09:00:02  Đã truyền SMTP DATA
09:00:03  Process crash trước khi lưu SUBMITTED
09:02:00  Lease hết hạn
~~~

Nếu scanner thấy lease hết hạn và chuyển N100 về PENDING để gửi lại ngay, email có thể được gửi trùng.

Cần phân biệt hai trường hợp:

**CLAIMED nhưng chưa SENDING:**

- Worker đã claim, nhưng chưa bắt đầu SMTP.
- Nếu lease hết hạn và có đủ bằng chứng chưa gọi send, có thể đánh giá để reclaim hoặc expire theo deadline.
- Dùng **claim_token** mới khi worker khác nhận quyền xử lý.

**SENDING và không có kết quả bền vững:**

- SMTP có thể đã accepted trước khi worker chết.
- Không thể suy từ lease expired rằng message chưa được gửi.
- Nên chuyển sang **UNKNOWN/NEEDS_RECONCILIATION** hoặc trạng thái chờ đối soát khi policy yêu cầu.
- Không replay mù chỉ vì expires_at cũng đã qua.

### Fencing token và giới hạn của nó

Claim token giúp bảo vệ database: worker cũ không được cập nhật outbox sau khi mất quyền.

Tuy nhiên, token **không chặn được một TCP connection đã mở** ở worker cũ gửi dữ liệu tới SMTP server. Đây là giới hạn của việc dùng lease với side effect bên ngoài transaction.

Khi thiết kế lease TTL, cần đo SMTP connect/read/write timeout, attachment rendering và heartbeat. Nhưng ngay cả lease được chọn tốt cũng không tạo ra bảo đảm exactly-once delivery.

## 39. SMTP accepted nhưng lưu trạng thái thất bại

Một timeline điển hình:

~~~text
Worker:
    |
    +-- JavaMailSender.send(message)
    |         |
    |         v
    |      SMTP 250 Accepted
    |
    +-- UPDATE email_outbox SET status='SUBMITTED'
              |
              X database unavailable
~~~

Email có thể đã rời ứng dụng, nhưng row database vẫn còn SENDING. Nếu worker restart và retry nó, người nhận có thể nhận bản thứ hai.

Biện pháp:

1. Có **attempt record** trước khi bắt đầu SMTP.
2. Nếu provider hỗ trợ, gắn **provider correlation ID** hoặc custom idempotency metadata được phép.
3. Sau khi send accepted, ghi kết quả qua transaction ngắn với claim token.
4. Nếu update thất bại, giữ attempt ở trạng thái cần đối soát thay vì xóa dấu vết.
5. Có worker reconciliation với chính sách không gửi trùng bừa bãi.
6. Nếu phải replay, ghi rõ rủi ro duplicate và loại notification được phép.

Không có transaction ACID nào bao phủ cả database ứng dụng và SMTP server trong mô hình thông thường. **Outbox giải quyết việc tạo ý định gửi bền vững; nó không biến SMTP thành exactly-once.**

## 40. UNKNOWN sau timeout: không được đánh EXPIRED_NOT_SENT

Một attempt bắt đầu trước deadline nhưng socket timeout ở giai đoạn chờ phản hồi cuối:

~~~text
09:59  expires_at = 10:00
09:59  Bắt đầu SMTP DATA
10:00  SMTP server đã có thể chấp nhận DATA
10:01  Client timeout, không nhận được final reply
~~~

Ứng dụng không biết server đã chấp nhận hay chưa. Kết quả đúng theo chứng cứ có thể là **UNKNOWN**, không phải FAILED chắc chắn và cũng không phải EXPIRED_NOT_SENT.

Mô hình xử lý:

~~~text
UNKNOWN attempt
      |
      +-- Provider confirms accepted -> SUBMITTED
      |
      +-- Provider confirms rejected -> FAILED hoặc EXPIRED
      |                                tùy deadline/policy
      |
      +-- No authoritative evidence -> UNKNOWN_REVIEW
      |
      +-- Retry explicitly allowed -> new attempt
                                      with duplicate risk noted
~~~

Một số provider cho phép tra cứu submission/delivery theo message ID hoặc API. SMTP tiêu chuẩn không bảo đảm một cơ chế truy vấn idempotency thống nhất cho mọi nhà cung cấp.

Nếu đến lúc hết hạn trong khi attempt UNKNOWN, **không nên tự gửi lại một attempt mới sau expires_at**, nhưng vẫn cần đối soát attempt cũ. Hết hạn **quyền gửi tiếp** không xóa khả năng email đã được gửi.

### Đừng suy ra delivery từ send()

Ngay cả khi JavaMailSender.send(...) trả về bình thường, thường chỉ biết message đã được **SMTP server chấp nhận ở chặng submission**. Không thể khẳng định người nhận đã mở thư hoặc email chắc chắn tới Inbox.

Các **bounce, defer, spam complaint hoặc delivery report** có thể đến bất đồng bộ qua ESP webhook hoặc DSN.

## 41. Idempotency key cho notification được lập lịch

Một event hoặc API request có thể được retry:

~~~text
POST /schedule-email
    -> DB insert thành công
    -> response bị mất

Client retry POST /schedule-email
    -> không được tạo thêm một ý định gửi giống hệt
~~~

Nên xác định key theo nghiệp vụ:

~~~text
(tenant_id, notification_kind, business_event_id, recipient_key)
~~~

Với thông báo theo kỳ:

~~~text
(tenant_id, digest_kind, period_start, recipient_key)
~~~

Với một campaign:

~~~text
(tenant_id, campaign_id, campaign_version, recipient_key)
~~~

Không dùng mỗi Subject hoặc địa chỉ To làm idempotency key: hai email hợp lệ có thể giống Subject/recipient nhưng thuộc hai sự kiện khác nhau.

### Cùng key, lịch gửi thay đổi

Nếu client gửi lại cùng idempotency key nhưng muốn đổi scheduled_at/expires_at, ứng dụng phải định nghĩa:

- Trả về intent cũ vì đây là duplicate request.
- Cho phép một thao tác **reschedule** riêng, có expected version.
- Tạo phiên bản/intent mới theo business rule và hủy phiên bản cũ.

Không âm thầm cập nhật thời gian của một job đã được claim hoặc SENDING chỉ vì request replay mang dữ liệu khác.

## 42. Lên lịch lại một email đã bị bỏ qua

Một email SKIPPED/EXPIRED có thể được người dùng yêu cầu gửi lại. Nhưng **đổi status trực tiếp về PENDING** thường làm mất lịch sử và có thể phá idempotency.

Lựa chọn an toàn hơn:

~~~text
N100:
  status = EXPIRED
  reason = DEADLINE_REACHED
  finished_at = 10:00

N101:
  source_intent_id = N100
  reason = MANUAL_RESCHEDULE
  status = PENDING
  scheduled_at = 10:15
  expires_at = 10:45
~~~

Từ đó:

- N100 giữ nguyên audit.
- N101 có version/intent mới, deadline mới.
- Có thể kiểm tra user/tenant quyền gửi lại.
- Có thể ngăn tạo quá nhiều lần reschedule bằng idempotency riêng.
- Không cần đoán N100 đã từng gửi hay chưa.

**Ngoại lệ:** nếu hệ thống chọn mô hình cập nhật cùng một row cho job chưa bắt đầu, phải có version/locking và audit transition. Không reschedule một message có outcome UNKNOWN như thể chắc chắn chưa gửi.

## 43. Lưu lý do kết thúc và lịch sử attempt

Một trạng thái EXPIRED đơn lẻ không giải thích được vì sao nó xảy ra. Nên có **outcome_reason** và một bảng lịch sử riêng:

~~~sql
CREATE TABLE email_attempt (
    id                 UUID PRIMARY KEY,
    outbox_id          UUID NOT NULL,
    claim_token        UUID NOT NULL,
    attempt_number     INTEGER NOT NULL,
    started_at         TIMESTAMPTZ NOT NULL,
    completed_at       TIMESTAMPTZ,
    result             VARCHAR(40),
    error_category     VARCHAR(100),
    smtp_phase         VARCHAR(40),
    provider_message_ref VARCHAR(500),
    FOREIGN KEY (outbox_id) REFERENCES email_outbox(id)
);
~~~

Ví dụ history:

~~~text
N100 created      08:00
N100 scheduled    09:00
Attempt 1         09:00 -> SMTP 451
Retry scheduled   09:05
Attempt 2         09:05 -> connect_timeout
Retry proposed    09:20
Deadline          09:10
N100 EXPIRED      09:05 (RETRY_WINDOW_EXHAUSTED)
~~~

Ở đây **status terminal** được quyết định lúc 09:05 vì đã biết retry tiếp theo sẽ vượt deadline, không phải đợi scanner tới 09:10. Trường **finished_at** là lúc quyết định kết thúc; **expires_at** vẫn là deadline nghiệp vụ. Hai mốc này có thể khác nhau mà không mâu thuẫn.

Một notification chưa bao giờ được gửi cũng nên có lịch sử kết thúc, ví dụ:

~~~text
status=SKIPPED
reason=ORDER_ALREADY_PAID
attempt_count=0
~~~

Đừng tự tạo một SMTP attempt “giả” để ghi skip. Số attempt chỉ nên phản ánh những lần thử thực sự theo định nghĩa transport.

### Audit phải có quyền và retention

Lịch sử có thể chứa message ID, domain, provider response và correlation identifiers. Cần giới hạn truy cập theo tenant/quyền, không lưu password/SMTP protocol trace hoặc nội dung email thô vào bảng lỗi.

## 44. Metrics: phân biệt số email hết hạn với số email thất bại

Một hệ thống có thể có 1.000 notifications trong ngày:

~~~text
SUBMITTED: 850
EXPIRED:    70
SKIPPED:    50
CANCELLED:  20
FAILED:     10
~~~

Nếu gộp 150 record chưa submitted vào “SMTP failure”, dashboard sẽ sai. Phần lớn chưa hề bắt đầu SMTP attempt.

Nên dùng các metric theo ngữ nghĩa:

| Metric logic | Loại | Đơn vị đo |
|---|---|---|
| **mail.outbox.created** | Counter | Số notification intent mới |
| **mail.outbox.outcome** | Counter | Unique notification đi vào trạng thái terminal |
| **mail.outbox.expired** | Counter | Số notification hết deadline |
| **mail.outbox.skipped** | Counter | Số notification bị bỏ do policy |
| **mail.outbox.cancelled** | Counter | Số notification bị hủy |
| **mail.smtp.attempts** | Counter | Số SMTP submission attempts thực tế |
| **mail.outbox.pending** | Gauge | Số notification còn chờ |
| **mail.outbox.oldest.due.age** | Gauge | Thời gian chờ của notification đã đến hạn lâu nhất |
| **mail.outbox.schedule.lag** | Timer/Histogram | Độ trễ từ scheduled_at tới lúc bắt đầu attempt |
| **mail.outbox.expiration.lag** | Timer/Histogram | Độ trễ từ expires_at tới lúc status EXPIRED được lưu |
| **mail.worker.claims** | Counter | Số job được claim |
| **mail.worker.stale.leases** | Gauge/Counter | Số claim hết lease hoặc được phát hiện hết lease |
| **mail.smtp.unknown** | Counter/Gauge | Số attempt hoặc job chưa rõ kết quả, theo định nghĩa |
| **mail.schedule.missed** | Counter | Số occurrence theo lịch định kỳ bị bỏ lỡ |

**Counter Micrometer không phải sổ cái transaction.** Một process có thể crash giữa DB commit và Counter.increment(). Khi cần số liệu chính xác phục vụ billing/audit, dùng bảng outbox/attempt và reconciliation.

## 45. Gắn label đúng mức, tránh cardinality cao

Các chiều hữu ích:

~~~text
notification_type=OTP|ORDER_REMINDER|DIGEST|MARKETING
outcome=EXPIRED|SKIPPED|CANCELLED|SUBMITTED|FAILED
reason=DEADLINE_REACHED|ORDER_ALREADY_PAID|...
provider=primary|backup
stream=security|transactional|marketing
environment=production|staging
~~~

Chỉ dùng label có **tập giá trị hữu hạn, được chuẩn hóa**. Không dùng địa chỉ email người nhận, Subject, notification/attempt ID, business key, exception message thô, URL có token hoặc timestamp lịch gửi của từng email làm label.

Một metric gắn notification_id khác nhau cho hàng triệu emails sẽ tạo hàng triệu time series và rủi ro PII. Dùng **structured logs, trace và database** để tra cứu email cụ thể, bảo vệ theo tenant/quyền.

### Ví dụ Micrometer cho terminal outcome

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class MailOutcomeMetrics {

    private final MeterRegistry registry;

    public MailOutcomeMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void record(
            String notificationType,
            String outcome,
            String reason
    ) {
        registry.counter(
                "mail.outbox.outcome",
                "notification_type", notificationType,
                "outcome", outcome,
                "reason", reason
        ).increment();
    }
}
~~~

Giả định **notificationType/outcome/reason** đã được validate theo enum/allowlist. Nếu cùng job được xử lý lại, increment lặp sẽ làm metric lệch. Để giữ semantics “unique terminal outcome”, chỉ ghi từ transition thành công hoặc tổng hợp số liệu từ ledger; không gọi record(...) ở mỗi vòng poll khi job đã terminal.

## 46. Alert: nhận biết job hết hạn vì hệ thống nghẽn

Một email OTP hết hạn do người dùng không sử dụng token là chuyện bình thường. Nhưng **OTP hết hạn trước khi bắt đầu gửi** do backlog là tín hiệu hệ thống không đáp ứng mục tiêu.

Ví dụ policy:

~~~text
Nếu trong 10 phút:
  expired_due_to_capacity / all created OTP notifications > 1%
và đủ tối thiểu 100 notifications
  -> Warning
~~~

Một số rule khác:

| Alert | Tín hiệu | Hành động đầu tiên |
|---|---|---|
| **HighExpiryDueToBacklog** | EXPIRED do capacity/worker lag tăng | Kiểm tra queue, worker, quota |
| **OldestDueAgeHigh** | Pending job đến hạn chờ quá lâu | Kiểm tra scheduler, DB, provider |
| **ExpiredScannerStopped** | Không có sweep heartbeat khi cần | Kiểm tra scheduler/liveness |
| **UnknownSubmissionGrowing** | Job UNKNOWN tăng | Đối soát provider, xử lý outage |
| **MissedScheduleOccurrences** | Lịch kỳ vọng không có intent | Kiểm tra cron/schedule ledger |
| **CancellationAfterSendSpike** | User cancel khi job đã gửi nhiều | UX/schedule guard/race |
| **SkipReasonDistributionChanged** | Business skip tăng bất thường | Điều tra policy hoặc dữ liệu |

Không chỉ cảnh báo tỷ lệ vì **1/1 = 100%** nhưng mẫu quá nhỏ có thể gây nhiễu. Kết hợp ngưỡng tỷ lệ, **minimum volume**, thời gian kéo dài và mức quan trọng của stream.

### Ví dụ PromQL

Giả sử exporter tạo counter:

~~~text
mail_outbox_outcome_total{
  outcome="EXPIRED",
  reason="CAPACITY_BACKLOG",
  stream="security"
}

mail_outbox_created_total{
  stream="security"
}
~~~

Một tỷ lệ theo cửa sổ:

~~~promql
sum by (stream) (
  increase(
    mail_outbox_outcome_total{
      outcome="EXPIRED",
      reason="CAPACITY_BACKLOG"
    }[10m]
  )
)
/
clamp_min(
  sum by (stream) (
    increase(mail_outbox_created_total[10m])
  ),
  1
)
~~~

**Lưu ý mẫu số:** các email created và expired trong cùng khoảng đồng hồ không nhất thiết thuộc cùng cohort, vì expiration xảy ra sau creation. Truy vấn là **operational proxy** để phát hiện spike, không phải tỷ lệ thất bại chính xác theo cohort. Nếu cần SLA chính xác, dùng analytics từ outbox theo scheduled_at và observed outcome.

Khi áp dụng alert, phải xác minh tên metric exporter/labels thực tế và thêm điều kiện đủ volume. Nếu metric biến mất vì worker chết, cần alert scrape/liveness riêng thay vì hiểu missing series là 0 lỗi.

## 47. Thời gian chờ và sai lệch giữa lịch dự kiến với SMTP attempt

Ba metric thời gian có ý nghĩa khác nhau:

~~~text
schedule_lag =
    attempt_started_at - scheduled_at

outbox_wait_age =
    now - next_attempt_at
    (với job đến hạn chưa được xử lý)

expiration_mark_lag =
    expired_at - expires_at
    (với scanner đánh EXPIRED sau deadline)
~~~

Không dùng **expiration_mark_lag** để kết luận “email đã gửi muộn”. Một scanner dừng 3 giờ có thể đánh trạng thái EXPIRED muộn, nhưng worker guard đã ngăn email gửi trong suốt thời gian đó.

Ngược lại, **schedule_lag** cao trước deadline có thể làm notification trễ SLA dù chưa EXPIRED.

### Phân tích bằng cohort

Để đánh giá tỷ lệ deadline missed:

~~~text
Cohort = tất cả notification có scheduled_at trong ngày D

Numerator = số notification của cohort không khởi động
            submission attempt hợp lệ trước expires_at
            vì capacity/scheduler/provider

Denominator = số notification trong cohort có nghĩa vụ
              được thử/gửi theo policy
~~~

Phải loại hoặc ghi riêng những notification được skip hợp lệ vì user thanh toán, hủy yêu cầu hoặc rút consent. Chúng không phải SLA failure của hệ thống gửi email.

### Chọn SLI/SLO có thể kiểm chứng

Ví dụ:

> 99,9% OTP notifications hợp lệ phải bắt đầu SMTP submission trong vòng 10 giây sau scheduled_at, trước thời điểm expires_at.

Đây là **SLI submission timeliness**, không phải tỷ lệ người dùng thực sự nhận OTP trong 10 giây. Delivery có thể phụ thuộc vào provider, receiving server và spam filtering.

## 48. Khả năng điều tra từng notification

Khi người dùng hỏi “Tại sao tôi không nhận email nhắc?”, hệ thống nên có câu trả lời dựa trên bằng chứng:

~~~text
Notification: N100
Type: PAYMENT_REMINDER
Scheduled: 2026-11-12T02:00:00Z
Deadline:  2026-11-12T02:15:00Z
Status: SKIPPED
Reason: ORDER_ALREADY_PAID
Attempts: 0
Decision time: 2026-11-12T02:00:03Z
~~~

Hoặc:

~~~text
Notification: N101
Type: OTP
Status: EXPIRED
Reason: CAPACITY_BACKLOG
Scheduled: 2026-11-12T02:00:00Z
Deadline:  2026-11-12T02:05:00Z
Attempts: 0
~~~

Hoặc:

~~~text
Notification: N102
Type: ORDER_CONFIRMATION
Status: UNKNOWN
Attempts: 1
Last phase: SMTP_FINAL_REPLY
Reconciliation: pending
~~~

Trong trường hợp N102, UI không được khẳng định “email chắc chắn chưa gửi”. Cần hiển thị trạng thái chưa xác định và dùng provider data để đối soát.

**Không trả raw recipient email, payload hoặc trace SMTP cho người không có quyền xem**. Endpoint tra cứu phải kiểm tra tenant/user authorization.

## 49. Unit test các ranh giới thời gian bằng Clock.fixed

Kiểm thử deadline nên tránh phụ thuộc đồng hồ hệ thống thật:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class SendDeadlinePolicyTest {

    private static Clock at(String timestamp) {
        return Clock.fixed(
                Instant.parse(timestamp),
                ZoneOffset.UTC
        );
    }

    @Test
    void beforeDeadlineMaySend() {
        SendDeadlinePolicy policy = new SendDeadlinePolicy(
                at("2026-11-12T09:59:59Z")
        );

        assertTrue(
                policy.mayStartAttempt(
                        Instant.parse("2026-11-12T10:00:00Z")
                )
        );
    }

    @Test
    void exactlyAtDeadlineMustNotStartAttempt() {
        SendDeadlinePolicy policy = new SendDeadlinePolicy(
                at("2026-11-12T10:00:00Z")
        );

        assertFalse(
                policy.mayStartAttempt(
                        Instant.parse("2026-11-12T10:00:00Z")
                )
        );
    }

    @Test
    void pastDeadlineMustNotSend() {
        SendDeadlinePolicy policy = new SendDeadlinePolicy(
                at("2026-11-12T10:00:01Z")
        );

        assertFalse(
                policy.mayStartAttempt(
                        Instant.parse("2026-11-12T10:00:00Z")
                )
        );
    }

    @Test
    void noBusinessDeadlineAllowsAttempt() {
        SendDeadlinePolicy policy = new SendDeadlinePolicy(
                at("2026-11-12T10:00:00Z")
        );

        assertTrue(policy.mayStartAttempt(null));
    }
}
~~~

Những test này kiểm tra **policy thuần Java**, không chứng minh transaction SQL hoặc scheduler thật chạy đúng. Vì SQL dùng statement_timestamp(), kiểm thử ranh giới **database state transition** cần môi trường database thật hoặc một cơ chế kiểm soát thời điểm được thiết kế cho test.

### Bảng các test thời gian nên có

| Tình huống | Kỳ vọng |
|---|---|
| now trước expires_at 1 ns | Được phép nếu policy không có minimum budget |
| now bằng expires_at | Không bắt đầu attempt mới |
| now sau expires_at | EXPIRED nếu còn chưa gửi |
| scheduled_at trong tương lai | Chưa được claim |
| next_attempt_at sau expires_at | Không schedule một retry vô nghĩa |
| expires_at null | Dựa vào policy không expiry và retry/retention khác |
| scheduled_at > expires_at | Reject input hoặc xử lý invalid theo rule |
| user hủy trước send | Không gửi |
| hủy sau khi đã SUBMITTED | Không tuyên bố đã thu hồi email |
| time zone có DST gap/overlap | Theo quy tắc timezone đã định nghĩa |
| event được đổi lịch | Deadline và notification version nhất quán |
| cron bỏ lỡ một kỳ do downtime | Misfire policy được áp dụng |

## 50. Kiểm thử concurrency ở ranh giới expiration

Để chứng minh scanner và worker không ghi đè trạng thái của nhau, nên có **database integration test** với cùng loại PostgreSQL/transaction isolation dùng ở production.

### Kịch bản: worker và scanner cùng tranh một row

~~~text
Given:
  N100: PENDING, expires_at rất gần

Thread A:
  expire batch

Thread B:
  claim due batch

Assert:
  N100 chỉ có một transition thắng
  không xuất hiện vừa EXPIRED vừa CLAIMED hợp lệ
  không có hai worker cùng sở hữu cùng claim token/state
~~~

### Kịch bản: cancellation và claim

~~~text
Thread A: CANCEL if PENDING
Thread B: CLAIM if PENDING and before deadline
~~~

Kết quả được phép:

- CANCEL thắng, worker không send.
- CLAIM thắng, worker sau đó quan sát cancellation request tại final admission gate nếu có cơ chế hỗ trợ.

Không được có kết quả **cancel trả thành công, rồi worker vẫn gửi trong khi trạng thái còn PENDING** do một update không kiểm tra state/version.

### Kịch bản: lease hết hạn

1. Worker A claim N100.
2. A ngừng heartbeat.
3. Lease hết hạn.
4. Worker B được xem xét reclaim.
5. Worker A xuất hiện lại và thử cập nhật kết quả bằng token cũ.

Hệ thống phải từ chối **stale DB update** của A. Đồng thời phải nhận diện việc A có thể đã gọi SMTP, nên không được kết luận B cứ gửi lại là an toàn.

### Kịch bản: batch expiration

- Tạo 1.500 PENDING đã hết hạn.
- Có 300 RETRY_WAIT đã hết hạn.
- Có 30 SENDING đã hết hạn.
- Có 20 SUBMITTED đã qua deadline.
- Quét theo batch.

Kỳ vọng scanner chỉ expire những row thuộc **eligible unsent states**, để nguyên SENDING/SUBMITTED theo chính sách và không bỏ sót row khi có lock tranh chấp.

**Không dùng một test chỉ chạy tuần tự với HashMap trong bộ nhớ để suy ra tính nguyên tử của SQL khi chạy nhiều worker.**

## 51. Kiểm thử tích hợp với SMTP server thử nghiệm

Một integration test có thể dùng **GreenMail**, **Mailpit** hoặc một SMTP capture server phù hợp để xác minh **không có submission thực sự** ở các trường hợp skip/expire.

~~~text
JUnit / Spring test
      |
      +-- Start SMTP test server
      |
      +-- Insert scheduled notifications
      |
      +-- Trigger scheduler/worker
      |
      +-- Read captured SMTP messages
      |
      +-- Assert DB statuses and attempts
~~~

Những ca nên thực hiện:

| Case | DB outcome | SMTP server nhận gì? |
|---|---|---|
| Job chưa tới scheduled_at | PENDING | Không nhận |
| Job đã expired trước claim | EXPIRED | Không nhận |
| Đơn đã thanh toán trước gửi | SKIPPED | Không nhận |
| Recipient đã unsubscribe | SKIPPED/SUPPRESSED | Không nhận |
| User hủy trước claim | CANCELLED | Không nhận |
| Job còn hạn và đủ điều kiện | SUBMITTED nếu accepted | Một message theo intent |
| SMTP từ chối rõ, còn deadline | RETRY_WAIT | Theo phản hồi server |
| SMTP từ chối rõ, hết retry window | EXPIRED/FAILED theo policy | Không có attempt tiếp sau deadline |
| SMTP timeout sau DATA | UNKNOWN | Có thể đã nhận; không suy đoán |
| Job chưa gửi được vì quota | DEFERRED/RETRY_WAIT | Không nhận tới khi có capacity |

Với **UNKNOWN**, test phải mô phỏng tình huống phản hồi cuối bị mất hoặc không đọc được. Không được assert “0 messages captured” nếu transport có thể đã nhận DATA trước khi mất phản hồi.

Đối với những case không gửi, assertion nên chứng minh:

1. Worker không gọi sender hoặc SMTP server không nhận message.
2. Outbox có đúng terminal status/reason.
3. Không có attempt record giả.
4. Retry/restart không gửi lại terminal intent.

Không gửi test email tới mailbox thật chỉ để kiểm thử hết hạn.

## 52. Runbook: email không được gửi theo lịch

Khi có phản ánh “đã đến giờ nhưng không thấy email”, đội vận hành có thể điều tra:

### Bước 1 — Xác định notification intent

- Tìm bằng **tenant, business event ID, notification type, recipient reference** có quyền.
- Có outbox record không?
- Nếu không có, đây có thể là **missed schedule occurrence** chứ không phải một outbox record bị expire.
- Kiểm tra idempotency key xem request đã được tạo trước đó chưa.

### Bước 2 — Kiểm tra thời gian

- scheduled_at đúng Instant/ZoneId không?
- next_attempt_at đang là mấy giờ?
- expires_at có được tính từ TTL/event đúng không?
- Có DST ambiguity hoặc timezone conversion sai không?
- Clock skew giữa application và database có bất thường không?

### Bước 3 — Xem trạng thái

| Status | Hướng điều tra |
|---|---|
| **PENDING** | Chưa đến hạn, hoặc scheduler chưa lấy |
| **RETRY_WAIT** | Lỗi tạm thời, rate/next_attempt_at |
| **CLAIMED** | Worker giữ claim, lease có còn không |
| **SENDING** | SMTP in-flight hoặc result update kẹt |
| **EXPIRED** | Deadline và reason; xác định business hay capacity |
| **SKIPPED** | Policy decision, consent, business state |
| **CANCELLED** | Actor, thời điểm, audit cancellation |
| **FAILED** | Error category và retry policy |
| **UNKNOWN** | Provider reconciliation, không tự replay |
| **SUBMITTED** | Đối chiếu provider/delivery events; không khẳng định delivered |

### Bước 4 — Xác định nguyên nhân gốc

- Scheduler heartbeat/cron có hoạt động?
- Queue depth, oldest due age và worker throughput có bất thường?
- Provider SMTP có lỗi DNS/TCP/TLS/AUTH/throttle?
- Có đợt campaign khiến OTP bị starvation?
- Có policy/consent thay đổi?
- Có batch job hoặc deploy làm kẹt lease?
- Database có lock contention hoặc index/query chậm?

### Bước 5 — Phục hồi an toàn

- **PENDING còn hạn:** có thể cho scheduler lấy lại theo rule.
- **RETRY_WAIT còn hạn:** cân nhắc retry khi provider phục hồi, không bỏ backoff.
- **EXPIRED:** không gửi bù nếu nội dung đã vô nghĩa; nếu cần, tạo **intent mới** theo policy.
- **SKIPPED:** chỉ gửi lại khi rule nghiệp vụ thay đổi và actor có quyền.
- **CANCELLED:** không tự reverse cancellation.
- **UNKNOWN/SENDING mất kết quả:** đối soát provider trước khi replay.
- **SUBMITTED:** xem delivery/bounce thay vì gửi trùng.

### Bước 6 — Xác nhận đã khôi phục

Theo dõi tỷ lệ expiry do backlog, pending age, retries, unknown outcomes, throughput và số scheduled occurrences mới được tạo đúng kỳ.

## 53. Những sai lầm dễ gặp

| Sai lầm | Hậu quả | Cách tốt hơn |
|---|---|---|
| Chỉ dựa vào @Scheduled để lưu lịch | Restart mất kỳ dự kiến | Durable schedule/outbox ledger |
| Không có expires_at | OTP/campaign cũ vẫn gửi | Deadline theo loại notification |
| Dùng một TTL cho mọi email | Hóa đơn bị bỏ hoặc OTP gửi trễ | Policy theo notification type |
| Chỉ expire ở scanner, không kiểm tra tại worker | Scanner trễ khiến email quá hạn vẫn gửi | Guard trước claim và trước send |
| So sánh LocalDateTime không có ZoneId | Sai múi giờ, DST | Convert sang Instant với ZoneId rõ |
| Dùng SELECT rồi send không claim | Nhiều worker gửi trùng | Atomic claim + token/lease |
| Scanner đổi mọi row có expires_at cũ | Ghi đè SUBMITTED/UNKNOWN | Filter eligible statuses |
| Coi lease expired nghĩa là chưa gửi | Retry trùng sau crash | Phân biệt CLAIMED và SENDING |
| Timeout sau DATA = thất bại chắc chắn | Gửi trùng | UNKNOWN và reconciliation |
| Gộp SKIPPED vào SMTP FAILED | Dashboard lỗi giả | Outcome taxonomy rõ |
| Chỉ dùng dữ liệu lúc tạo job | Gửi nhắc thanh toán sau khi đã trả | Revalidate business state |
| Không kiểm tra lại suppression/consent | Gửi email không được phép | Policy check gần lúc gửi |
| Không có idempotency key cho cron | Tạo nhiều digest cùng kỳ | Unique period/business key |
| Bỏ lỡ cron nhưng không có ledger | Không biết kỳ nào bị thiếu | Misfire reconciliation |
| Mỗi lần retry tự tăng business quota | Hết ngân sách do provider lỗi | Tách intent quota và attempt capacity |
| Cứ lỗi thì retry không giới hạn | Retry storm và gửi sau deadline | Backoff, max attempts, cutoff |
| Đổi EXPIRED về PENDING khi user nhấn resend | Mất audit, phá idempotency | Intent mới/versioned reschedule |
| Hủy job bằng cách xóa record | Mất lịch sử và khó đối soát | CANCELLED với audit |
| UI báo “đã hủy” sau khi SMTP accepted | Người dùng hiểu nhầm có thể recall | Phân biệt cancellation request vs acceptance |
| Gửi cả batch tới nhiều recipient rồi skip toàn batch khi một người rút consent | Kết quả sai theo từng recipient | Per-recipient eligibility/outcome |
| Bỏ qua quota/provider lag khi đo email trễ | Không biết root cause | Metrics oldest age/reason |
| Dùng raw exception/recipient làm metrics label | PII, cardinality cao | Enum reason và logs có kiểm soát |

## 54. Checklist triển khai

**Policy và thời gian**

1. Mỗi notification type có late-send policy rõ chưa?
2. Có phân biệt scheduled_at, next_attempt_at và expires_at không?
3. Deadline có dựa trên TTL token/event/campaign đúng không?
4. Có quy tắc timezone/DST cho lịch địa phương không?
5. Email đến hạn nhưng business state thay đổi sẽ SKIP/REPLACE/SEND_CURRENT như thế nào?
6. Đã định nghĩa misfire policy cho cron downtime chưa?

**Trạng thái và transaction**

7. Có các terminal states EXPIRED, SKIPPED, CANCELLED và SUBMITTED không?
8. Có reason code, actor, timestamps và audit không?
9. Scanner chỉ expire những row eligible unsent không?
10. Worker có claim atomic và token/lease không?
11. Có kiểm tra deadline lần cuối trước SMTP không?
12. Có tránh giữ DB transaction trong lúc gửi không?
13. Có xử lý stale worker và lease hết hạn không?
14. Có idempotency key chống duplicate intents không?

**Retry và provider**

15. Retry có tính deadline, backoff, min delay và max attempts không?
16. Có phân biệt SMTP rejection với UNKNOWN sau DATA không?
17. Khi update DB thất bại sau accepted, có reconciliation không?
18. Cancellation có trả trạng thái trung thực nếu đã SENDING/SUBMITTED không?
19. Có tính per-recipient eligibility và suppression khi cần không?
20. Provider failover có kiểm soát nguy cơ duplicate không?

**Vận hành và bảo mật**

21. Có đo expiry do capacity, skip theo reason và oldest due age không?
22. Có cảnh báo missed occurrences, worker liveness và unknown backlog không?
23. Có phân biệt metrics theo attempt và notification không?
24. Không đưa email/Subject/token vào metrics labels hoặc log thông thường chứ?
25. UI/API tra cứu đã kiểm tra tenant authorization chưa?
26. Có runbook replay/reschedule có kiểm soát không?

**Kiểm thử**

27. Đã kiểm thử thời điểm trước/bằng/sau deadline với Clock.fixed chưa?
28. Đã kiểm thử scanner và worker tranh cùng một row chưa?
29. Đã kiểm thử user cancel trong lúc claim/send chưa?
30. Đã kiểm thử retry vượt expires_at chưa?
31. Đã kiểm thử cron misfire và unique period key chưa?
32. Đã kiểm thử SMTP accepted nhưng DB result update lỗi chưa?
33. Đã kiểm thử không gửi tới recipient bị suppress hoặc job quá hạn chưa?

## 55. Ghi nhớ

**Xử lý email quá hạn hoặc bị bỏ qua** là việc xác định một notification được phép tiếp tục gửi tới đâu trong vòng đời lập lịch, và ghi lại chính xác vì sao nó không được gửi khi điều kiện đã thay đổi.

Các nguyên tắc chính:

1. **scheduled_at, next_attempt_at và expires_at có vai trò khác nhau**. Hãy dùng Instant/ZoneId và deadline nghiệp vụ thay vì chỉ một timestamp.
2. **EXPIRED, SKIPPED, CANCELLED, FAILED, UNKNOWN và SUBMITTED không tương đương**. Chúng cần state transitions và reason codes rõ ràng.
3. **Scanner không phải lớp chặn duy nhất**. Worker phải kiểm tra trạng thái/deadline có điều kiện trước khi bắt đầu SMTP attempt.
4. **Outbox và claim atomic** giúp phục hồi sau restart, ngăn nhiều worker cùng lấy một job và lưu audit; chúng không làm SMTP exactly-once.
5. **Retry phải tôn trọng hạn cuối**. Không tiếp tục thử chỉ vì lỗi tạm thời nếu notification đã không còn giá trị.
6. **Kiểm tra lại business state, consent và suppression** trước gửi các thông báo có thể trở nên không phù hợp.
7. **Cron misfire** khác job đã tồn tại nhưng hết hạn; cần schedule ledger/catch-up policy khi có yêu cầu chạy bù.
8. **UNKNOWN sau SMTP DATA** cần đối soát, không được gán nhãn “chắc chắn chưa gửi” rồi replay tùy tiện.
9. **Đo nguyên nhân bỏ gửi theo notification cohort**, đừng gộp business skips với SMTP failures.
10. **Kiểm thử ranh giới thời gian, concurrency, cancellation và crash recovery** bằng Clock cố định, database/test SMTP server phù hợp.

**Một hệ thống lập lịch gửi email đáng tin cậy không phải hệ thống cố gửi mọi job bằng mọi giá, mà là hệ thống chỉ gửi những thông báo còn hợp lệ, dừng đúng lý do khi không nên gửi và giữ đủ bằng chứng để giải thích hoặc phục hồi an toàn.**







