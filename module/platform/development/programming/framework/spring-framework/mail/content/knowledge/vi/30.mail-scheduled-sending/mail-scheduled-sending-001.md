# Gửi ngay và gửi vào thời điểm được yêu cầu trong Spring Framework Mail

Một ứng dụng không phải lúc nào cũng gửi email vào cùng thời điểm người dùng bấm nút. Có thông điệp cần gửi **ngay khi có một sự kiện nghiệp vụ**, như email xác nhận đăng ký, OTP hoặc thông báo thanh toán. Nhưng cũng có thông điệp người dùng muốn **gửi vào một thời điểm xác định**, như lời nhắc ngày mai lúc 9 giờ, email chăm sóc sau 7 ngày hoặc một báo cáo định kỳ đã chọn giờ phát hành.

Trong **Spring Framework Mail**, `JavaMailSender` chịu trách nhiệm tạo kết nối và **submit** thư tới SMTP relay; nó không phải một kho lưu trữ lịch gửi. Do đó, vấn đề “gửi ngay hay gửi vào thời điểm được yêu cầu” phải được giải quyết **trước lời gọi SMTP**: tiếp nhận yêu cầu, xác định thời điểm, lưu trạng thái bền vững, điều phối worker tới hạn, kiểm tra điều kiện còn hợp lệ và chỉ sau đó gọi `JavaMailSender.send(...)`.

Bài này trình bày từ yêu cầu nghiệp vụ đến triển khai trong Spring Boot: phân biệt gửi ngay và gửi theo lịch; xử lý `Instant`, timezone và DST; thiết kế API; `TaskScheduler` và `@Scheduled`; transactional outbox, database polling và nhiều instance; hủy/đổi lịch; SMTP timeout, retry và tránh gửi trùng; kiểm thử và vận hành.

> Nguyên tắc nền tảng: **“Gửi ngay” nghĩa là đưa yêu cầu hợp lệ vào luồng gửi với độ ưu tiên phù hợp; “gửi lúc 09:00” nghĩa là không bắt đầu submit trước thời điểm đã thỏa thuận.** Cả hai đều không bảo đảm email xuất hiện trong Inbox chính xác tại thời điểm đó, vì SMTP relay và hệ thống nhận vẫn có thể xếp hàng hoặc trì hoãn giao thư.

## 1. Hai loại yêu cầu gửi thư

### 1.1. Gửi ngay (send now)

Người dùng hoặc một sự kiện nghiệp vụ yêu cầu gửi càng sớm càng phù hợp:

- Gửi mã xác minh đăng nhập.
- Gửi thông báo xác nhận đơn hàng sau khi giao dịch commit.
- Gửi email đặt lại mật khẩu.
- Gửi biên nhận khi phát sinh thanh toán.
- Gửi thông báo khẩn theo quy tắc hệ thống.

“Ngay” không nhất thiết là gọi SMTP trực tiếp trong HTTP request. Một thiết kế tốt thường **ghi yêu cầu vào outbox**, trả phản hồi cho người dùng và để worker gửi trong thời gian ngắn. Điều này giúp hệ thống vẫn ghi nhận giao dịch khi SMTP provider bị lỗi.

### 1.2. Gửi vào thời điểm được yêu cầu (send at)

Người dùng hoặc business service cung cấp một thời điểm có ý nghĩa:

- “Gửi lời nhắc lúc 09:00 ngày mai theo giờ của người nhận”.
- “Gửi báo cáo khi kỳ kế toán kết thúc”.
- “Gửi email nhắc hẹn trước cuộc họp 30 phút”.
- “Gửi chiến dịch lúc 08:30 ở múi giờ của từng khu vực”.
- “Gửi bản nháp đã duyệt vào ngày công bố”.

Khác với send now, điều phối viên phải **không phát hành job trước thời điểm đến hạn**, đồng thời có chính sách khi worker đang trễ, ứng dụng restart, ngày giờ được đổi hoặc thông điệp hết hiệu lực.

### 1.3. Bảng so sánh

| Tiêu chí | Gửi ngay | Gửi theo thời điểm |
| --- | --- | --- |
| Thời điểm bắt đầu được phép gửi | Ngay khi yêu cầu hợp lệ và đã commit | Không sớm hơn `scheduledAt` |
| Cần lưu lịch? | Có thể lưu outbox với thời điểm hiện tại | Cần thời điểm UTC/Instant và ngữ cảnh thời gian |
| Phụ thuộc SMTP đồng bộ trong HTTP? | Không nên bắt buộc | Không |
| Có thể bị queue chậm? | Có | Có |
| Có hủy/đổi lịch? | Phụ thuộc trạng thái; cửa sổ rất ngắn | Nên có API hủy/đổi trước khi dispatch |
| Khi ứng dụng restart | Yêu cầu phải được giữ | Lịch phải được giữ |
| Khi mất kết nối SMTP | Retry hoặc hold theo policy | Retry hoặc hold, nhưng xét deadline/expiry |
| Ý nghĩa thành công của `send()` | Relay accepted submission | Relay accepted submission, không phải delivered |
| Mốc kiểm chứng chính | Thời gian từ enqueue đến submit | Không submit sớm và độ trễ so với thời điểm dự kiến |

Không coi một HTTP response `202 Accepted` là email đã được gửi. Nó chỉ xác nhận hệ thống đã **tiếp nhận yêu cầu**, tùy hợp đồng API.

## 2. Ba thời điểm thường bị nhầm

Một email có ít nhất ba mốc thời gian:

~~~text
T0: Người dùng yêu cầu gửi (requestedAt)
    |
    v
T1: Đến hạn và worker bắt đầu gửi (dispatchStartedAt)
    |
    v
T2: SMTP relay accepted sau DATA (submittedAt)
    |
    v
T3: Provider/remote MX giao tiếp, retry và có thể báo delivered/bounced
~~~

Với send now, `scheduledAt` có thể bằng thời điểm yêu cầu được ghi nhận (`requestedAt`). Với send later, `scheduledAt` có thể cách `requestedAt` vài phút hoặc nhiều tuần. **Không đồng nhất `scheduledAt`, `submittedAt` và `deliveredAt`**.

### Điều có thể bảo đảm

Ứng dụng có thể thiết kế để:

- Không tự bắt đầu gửi một message có `scheduledAt` ở tương lai.
- Lưu lịch gửi và phục hồi sau restart.
- Đánh dấu rõ job đến hạn, được claim và kết quả submit.
- Đặt giới hạn thời gian trễ, retry và expiry.
- Đảm bảo chỉ một worker giữ lease của job tại một thời điểm.

### Điều không thể bảo đảm tuyệt đối chỉ bằng Spring Mail

- Email tới hộp thư người nhận đúng mili giây.
- Relay không xếp hàng hoặc không có deferred/bounce.
- Chính xác một lần giao email đầu-cuối trong mọi tình huống mất kết nối.
- Người nhận thực sự đã đọc email.

SMTP là hệ thống phân tán có những thời điểm kết quả không xác định. Nếu mất final reply sau DATA, relay có thể đã accepted dù ứng dụng nhìn thấy exception. Vấn đề này phải được đưa vào thiết kế retry và lịch gửi.

## 3. Xác định ý nghĩa của “đúng thời điểm”

Người dùng có thể đưa ra những yêu cầu khác nhau:

| Cách diễn đạt | Ý nghĩa cần xác định |
| --- | --- |
| “Gửi ngay” | Hàng đợi sẵn sàng xử lý ở thời điểm hiện tại |
| “Gửi ngày 20/11/2026 lúc 09:00 giờ Việt Nam” | Một local date-time cùng timezone `Asia/Ho_Chi_Minh` |
| “Gửi sau 30 phút” | Relative delay tính từ mốc được định nghĩa |
| “Gửi trước cuộc hẹn 15 phút” | Thời điểm được suy ra từ sự kiện nguồn; cần cập nhật khi sự kiện đổi |
| “Gửi 08:00 theo giờ của người nhận” | Tính riêng `Instant` theo zone của mỗi recipient |
| “Gửi vào ngày cuối tháng” | Quy tắc lịch; cần calendar/business timezone |
| “Gửi trước hoặc không gửi” | Có deadline/expiry, có thể hủy nếu trễ |

Một hệ thống nên quy định rõ:

1. `scheduledAt` là **thời điểm sớm nhất được phép submit**, không phải cam kết Inbox delivery.
2. Có chấp nhận gửi muộn không, và muộn tối đa bao lâu?
3. Có chấp nhận lịch trong quá khứ không?
4. Thời gian theo múi giờ nào?
5. Có cho đổi/hủy khi message đã được claim không?
6. Nếu SMTP đang lỗi, retry có vượt thời hạn có ích của nội dung không?
7. Ai được quyền tạo/sửa/hủy lịch gửi cho tenant hoặc người nhận?

Việc trả lời trước những câu hỏi này sẽ quyết định cách thiết kế API và database, không chỉ là chọn một annotation Spring.

## 4. Dùng Instant để lưu mốc gửi tuyệt đối

Các kiểu Java Time có vai trò khác nhau:

| Kiểu | Biểu diễn | Dùng khi |
| --- | --- | --- |
| `Instant` | Một thời điểm trên trục UTC | Lưu `scheduledAt`, so sánh job đến hạn |
| `OffsetDateTime` | Local date-time kèm offset như `+07:00` | API gửi mốc thời gian có offset rõ |
| `ZonedDateTime` | Date-time gắn zone rules như `Asia/Ho_Chi_Minh` | Diễn giải giờ địa phương, quy tắc lịch |
| `LocalDateTime` | Ngày giờ không có timezone/offset | Form UI khi gửi kèm timezone riêng |
| `LocalDate` | Ngày lịch | Nhắc theo ngày, kỳ hạn |
| `Duration` | Khoảng thời gian tuyệt đối | “Sau 30 phút”, retry backoff |
| `Period` | Khoảng thời gian theo lịch | “Sau 1 tháng”, không bằng số giây cố định |
| `Clock` | Nguồn thời gian có thể inject | Logic và kiểm thử không phụ thuộc clock hệ thống |

**Khuyến nghị:** lưu một mốc thực thi duy nhất là `Instant` trong database (bằng một kiểu timestamp/driver có semantics UTC được kiểm chứng), đồng thời lưu `zoneId` và local date-time gốc nếu cần hiển thị hoặc cập nhật theo quy tắc lịch.

### Ví dụ gửi lúc 09:00 tại Việt Nam

~~~java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;

ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDateTime requested =
        LocalDateTime.of(2026, 11, 20, 9, 0);

Instant scheduledAt =
        requested.atZone(vietnam).toInstant();

System.out.println(scheduledAt);
// 2026-11-20T02:00:00Z
~~~

Việc lưu `2026-11-20T02:00:00Z` có nghĩa worker ở bất kỳ múi giờ server nào cũng có thể so sánh `Instant.now(clock)` với cùng một mốc.

### Không suy luận timezone từ server

Nếu API nhận `2026-11-20T09:00:00` (không offset), ứng dụng **không thể biết** đó là 9 giờ tại Việt Nam, UTC hay New York nếu không có hợp đồng khác. Không tự dùng `ZoneId.systemDefault()` để giải nghĩa lịch người dùng; một deployment sang region khác có thể làm lịch gửi bị lệch.

### API dạng một Instant xác định

~~~json
{
  "mode": "AT",
  "scheduledAt": "2026-11-20T02:00:00Z",
  "recipientId": "recipient-42",
  "templateKey": "appointment-reminder",
  "idempotencyKey": "reminder-appointment-184-v1"
}
~~~

Cách này phù hợp khi client đã chuyển local date-time + timezone thành mốc UTC đúng. API nên trả thêm `zoneId`/định dạng địa phương để user biết lịch đã đặt.

## 5. Múi giờ và DST: một giờ địa phương có thể mơ hồ

Không phải múi giờ nào cũng có offset cố định quanh năm. Một số nơi áp dụng **Daylight Saving Time (DST)**, khiến:

- Một khoảng giờ địa phương **không tồn tại** khi đồng hồ nhảy lên.
- Một khoảng giờ địa phương **xuất hiện hai lần** khi đồng hồ lùi.

Ví dụ tại `America/New_York` năm 2026 (với quy tắc DST hiện hành):

- `2026-03-08 02:30` không tồn tại theo giờ địa phương vì đồng hồ nhảy từ 02:00 lên 03:00.
- `2026-11-01 01:30` có thể ánh xạ tới hai mốc UTC khác nhau.

Nếu chỉ gọi `localDateTime.atZone(zone)`, Java sẽ áp dụng quy tắc mặc định để điều chỉnh trong gap/overlap; đây không nhất thiết đúng ý người dùng. Với lịch cần chính xác, nên **bắt UI/API làm rõ**.

### Kiểm tra một local date-time có hợp lệ hay không

~~~java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.List;

public final class ScheduleTimeResolver {

    public static Instant resolve(
            LocalDateTime local,
            ZoneId zone,
            ZoneOffset selectedOffset) {

        List<ZoneOffset> valid =
                zone.getRules().getValidOffsets(local);

        if (valid.isEmpty()) {
            throw new IllegalArgumentException(
                    "Local time does not exist in selected zone");
        }

        if (valid.size() > 1 && selectedOffset == null) {
            throw new IllegalArgumentException(
                    "Local time is ambiguous; select offset");
        }

        ZoneOffset offset =
                selectedOffset == null ? valid.get(0) : selectedOffset;

        if (!valid.contains(offset)) {
            throw new IllegalArgumentException(
                    "Offset is invalid for this local time");
        }

        return local.atOffset(offset).toInstant();
    }
}
~~~

Đối với giờ Việt Nam hiện nay, DST không phải vấn đề thường ngày; nhưng một dịch vụ gửi email toàn cầu không nên dựa vào giả định mọi recipient đều có UTC+7.

### Relative delay và lịch theo ngày khác nhau

`Duration.ofHours(24)` luôn là 24 giờ tuyệt đối. “Cùng giờ ngày mai theo local time” có thể không cách đúng 24 giờ ở múi giờ có DST. Với “ngày mai lúc 9 giờ”, dùng ngày/giờ địa phương cộng quy tắc timezone; với “sau đúng 24 giờ”, dùng `Instant.plus(Duration.ofHours(24))`.

## 6. Chọn hợp đồng API: NOW hay AT

Một API nên biểu diễn rõ lựa chọn của người dùng, thay vì dùng `null` không có ý nghĩa:

~~~json
{
  "mode": "NOW",
  "recipientId": "recipient-42",
  "templateKey": "payment-confirmed",
  "templateData": {
    "orderId": "ord-184"
  },
  "idempotencyKey": "payment-confirmed-ord-184"
}
~~~

Với lịch theo giờ địa phương:

~~~json
{
  "mode": "AT",
  "recipientId": "recipient-42",
  "templateKey": "appointment-reminder",
  "localDateTime": "2026-11-20T09:00:00",
  "zoneId": "Asia/Ho_Chi_Minh",
  "idempotencyKey": "reminder-appointment-184-v1"
}
~~~

Server giải nghĩa `localDateTime` bằng `zoneId`, xác minh quy tắc DST, chuyển thành `Instant` và lưu cả mốc gốc nếu nghiệp vụ yêu cầu.

### Validate đầu vào

| Trường | Điều kiện |
| --- | --- |
| `mode` | Chỉ `NOW` hoặc `AT` trong API này |
| `recipientId` | Có thật, đúng tenant, người gọi có quyền gửi |
| `templateKey` | Thuộc allowlist và được phép theo loại thông điệp |
| `templateData` | Đúng schema, không chứa secret hoặc tùy ý HTML |
| `localDateTime` và `zoneId` | Bắt buộc ở AT, không mơ hồ |
| `idempotencyKey` | Unique theo tenant/nguồn nghiệp vụ, kích thước hợp lý |
| Khoảng đặt lịch | Không ở quá khứ nếu policy cấm; không quá xa |
| `expiresAt` | Nếu cần, phải muộn hơn `scheduledAt` |
| Recipient preference | Không bị suppress hoặc thiếu consent tại lúc đặt lịch |

### Không biến AT trong quá khứ thành NOW một cách âm thầm

Nếu người dùng chọn lịch đã qua, lựa chọn rõ ràng là:

- Trả lỗi validation để người dùng sửa.
- Hoặc cho phép một khoảng sai lệch nhỏ theo policy (ví dụ trễ do mạng/client) và ghi nhận rằng đã gửi dưới dạng “gửi muộn”.
- Với job import/recovery, dùng API riêng có quyền và audit.

Không tự đổi một lịch “thứ Hai tuần trước” sang gửi ngay vì có thể đó là nhầm múi giờ hoặc thao tác sai.

## 7. Gửi ngay có nên gọi JavaMailSender trực tiếp trong HTTP?

Một ví dụ đồng bộ dễ hiểu:

~~~java
@PostMapping("/mail/send-now")
public ResponseEntity<Void> sendNow(@RequestBody MailRequest request) {
    mailService.send(request);
    return ResponseEntity.noContent().build();
}
~~~

Nhưng nó có nhiều rủi ro:

- SMTP connect/read/write có thể mất nhiều giây hoặc timeout.
- Nếu SMTP outage, HTTP request thất bại dù giao dịch nghiệp vụ đã thành công.
- Retry ở HTTP client có thể tạo nhiều email.
- Nếu database transaction đang mở, nó có thể giữ locks khi chờ mạng.
- Nếu relay accepted nhưng client chưa nhận phản hồi, kết quả trở nên không xác định.

### Hướng thiết kế phù hợp hơn cho nghiệp vụ

~~~text
HTTP request / business event
        |
        v
Validate + authorize
        |
        v
Persist notification/outbox in transaction
        |
        v
HTTP 202 Accepted / business transaction committed
        |
        v
Background dispatcher selects due jobs
        |
        v
JavaMailSender.send(...)
        |
        v
Persist submission result / retry policy
~~~

`202 Accepted` có thể kèm ID và endpoint xem trạng thái. Nếu yêu cầu gửi gắn với một transaction như thanh toán, record yêu cầu email nên được ghi **trong cùng transaction** với thay đổi nghiệp vụ để tránh ghi nhận thanh toán thành công nhưng quên yêu cầu gửi mail.

### Khi nào gửi trực tiếp vẫn có thể phù hợp?

Với công cụ nội bộ nhỏ, không yêu cầu durable scheduling, số lượng mail thấp và có chấp nhận việc HTTP chờ SMTP, gọi trực tiếp có thể đủ. Khi đó vẫn cần timeout, giới hạn concurrency, cách diễn giải lỗi và tránh client retry mù. Tuy nhiên mô hình synchronous không giải quyết bài toán **gửi sau khi server restart** hoặc **hẹn lịch theo ngày**.

## 8. `TaskScheduler` và `@Scheduled`: nhiệm vụ khác nhau

Spring có nhiều cơ chế scheduling; cần chọn đúng:

| Công cụ | Phù hợp | Giới hạn cần hiểu |
| --- | --- | --- |
| `TaskScheduler.schedule(Runnable, Instant)` | Đặt một tác vụ trong process vào một thời điểm | Nếu process restart, lịch trong memory biến mất |
| `@Scheduled(fixedDelay=...)` | Poll đều đặn các job đến hạn | Không tự lưu job; cần durable repository |
| `@Scheduled(cron=...)` | Tác vụ lặp có lịch cố định | Không phù hợp để lưu hàng triệu thời điểm người dùng khác nhau |
| Quartz với JDBC JobStore | Lịch bền vững, trigger/recovery phức tạp | Cần thiết kế JobStore, clustering và hành vi task |
| Delayed message queue | Giao message chậm theo broker | Cần xác minh giới hạn delay, durability, redelivery |
| Database outbox + polling | Gửi ngay và gửi theo lịch với persistence | Cần polling, claim/lease và retry |

Với yêu cầu **gửi một email duy nhất tại thời điểm do người dùng chọn**, `@Scheduled(cron="0 0 9 * * *")` không biểu diễn được mỗi recipient một `scheduledAt` riêng. Cron phù hợp cho **scheduler lặp**, không phải bản ghi lịch user-specific có thể hủy/đổi giờ.

### Minh họa in-memory TaskScheduler

~~~java
import java.time.Instant;
import org.springframework.scheduling.TaskScheduler;

public final class InMemoryMailSchedule {
    private final TaskScheduler scheduler;
    private final Runnable mailTask;

    public InMemoryMailSchedule(
            TaskScheduler scheduler, Runnable mailTask) {
        this.scheduler = scheduler;
        this.mailTask = mailTask;
    }

    public void scheduleOnce(Instant when) {
        scheduler.schedule(mailTask, when);
    }
}
~~~

Code này chỉ minh họa API lập lịch một lần; **không nên dùng nó làm nơi lưu duy nhất cho yêu cầu email quan trọng**. Nếu JVM dừng trước `when`, không có cơ chế mặc định khôi phục lịch. Trong multi-instance, mỗi instance còn có scheduler riêng và có thể gây trùng nếu đăng ký lại cùng job.

## 9. Mô hình khuyến nghị: một outbox cho NOW và AT

Thay vì hai hệ thống độc lập, có thể dùng **cùng một bảng yêu cầu gửi**:

~~~text
Send NOW:
    scheduledAt = clock.instant()
           |
           v
      durable outbox

Send AT:
    scheduledAt = user-selected Instant
           |
           v
      same durable outbox

Worker:
    find records with scheduledAt <= now
    and state is dispatchable
           |
           v
    claim -> validate -> send -> persist result
~~~

Lợi ích:

- Cùng validation, idempotency, retry, suppression và metrics.
- Lịch trong tương lai không mất khi process restart.
- Có thể hủy/đổi lịch qua database trước khi dispatch.
- Một worker xử lý cả email “ngay” và “đặt lịch” theo priority.
- Có thể triển khai nhiều instance khi có cơ chế claim an toàn.

### Phân biệt `scheduledAt` và `nextAttemptAt`

`scheduledAt` là thời điểm nghiệp vụ cho phép **lần gửi đầu tiên**. `nextAttemptAt` là thời điểm worker có thể thử lại sau một lỗi tạm thời.

Một job gửi ngày 20/11 lúc 09:00 có thể có:

~~~text
scheduledAt     = 2026-11-20T02:00:00Z
firstAttemptAt  = 2026-11-20T02:00:05Z
result          = temporary SMTP error
nextAttemptAt   = 2026-11-20T02:02:05Z
~~~

Không ghi đè `scheduledAt` bằng thời điểm retry nếu muốn đo đúng lịch do người dùng yêu cầu. Worker có thể dùng `availableAt = max(scheduledAt, nextAttemptAt)` hoặc lưu một trường `availableAt` riêng để truy vấn job đến hạn.

## 10. Thiết kế bảng lịch gửi bền vững

Một mô hình quan hệ tối thiểu cần lưu:

- Ai tạo yêu cầu, thuộc tenant/loại thông điệp nào.
- Đối tượng nhận và nội dung/template cần gửi.
- Chế độ NOW/AT, thời điểm gốc do người dùng chọn và thời điểm UTC.
- Trạng thái chưa gửi/đang gửi/đã submit/tạm lỗi/đã hủy/hết hạn.
- Idempotency key.
- Lần gửi gần nhất, thời điểm thử lại, lease owner và version.
- Kết quả SMTP và lý do không thể gửi (khi có).

### Ví dụ schema PostgreSQL

~~~sql
CREATE TABLE mail_schedule (
    id                  UUID PRIMARY KEY,
    tenant_id           VARCHAR(100) NOT NULL,
    idempotency_key     VARCHAR(250) NOT NULL,
    recipient_id        VARCHAR(100) NOT NULL,
    template_key        VARCHAR(150) NOT NULL,
    payload_json        JSONB NOT NULL,
    payload_version     INTEGER NOT NULL DEFAULT 1,

    mode                VARCHAR(10) NOT NULL,
    scheduled_at        TIMESTAMPTZ NOT NULL,
    requested_local_at  TIMESTAMP,
    requested_zone_id   VARCHAR(100),
    available_at        TIMESTAMPTZ NOT NULL,
    expires_at          TIMESTAMPTZ,

    status              VARCHAR(40) NOT NULL,
    priority            INTEGER NOT NULL DEFAULT 0,
    attempts            INTEGER NOT NULL DEFAULT 0,
    max_attempts        INTEGER NOT NULL DEFAULT 5,
    lease_owner         VARCHAR(150),
    lease_until         TIMESTAMPTZ,
    generation          BIGINT NOT NULL DEFAULT 0,
    stop_reason         VARCHAR(100),

    created_at          TIMESTAMPTZ NOT NULL,
    updated_at          TIMESTAMPTZ NOT NULL,
    submitted_at        TIMESTAMPTZ,

    CONSTRAINT mail_schedule_idempotent
        UNIQUE (tenant_id, idempotency_key),
    CONSTRAINT mail_schedule_mode_chk
        CHECK (mode IN ('NOW', 'AT')),
    CONSTRAINT mail_schedule_attempts_chk
        CHECK (attempts >= 0 AND max_attempts > 0),
    CONSTRAINT mail_schedule_expiry_chk
        CHECK (expires_at IS NULL OR expires_at > scheduled_at)
);

CREATE INDEX idx_mail_schedule_due
    ON mail_schedule (available_at, priority DESC, created_at)
    WHERE status IN ('PENDING', 'RETRY_PENDING');
~~~

Đây là **schema minh họa**, không phải schema Spring Mail tự tạo. Cần bổ sung authorization/audit, encryption, indexes, retention và constraint phù hợp hệ thống thật. `TIMESTAMPTZ` của PostgreSQL biểu diễn instant có nhận biết timezone; nó **không lưu lại tên múi giờ IANA gốc**, vì vậy muốn hiển thị “09:00 Asia/Ho_Chi_Minh” cần lưu `requested_zone_id` và local time nếu đó là requirement.

### Không lưu raw email vô hạn trong `payload_json`

Nếu payload chứa PII, OTP, reset URL, thông tin nhạy cảm hoặc các attachment, cần cân nhắc:

- Lưu template ID và business reference thay vì toàn bộ bí mật.
- Mã hóa payload khi cần, phân quyền và retention rõ ràng.
- Tách attachment thành immutable object storage, kiểm tra có quyền và kích thước.
- Không lưu plaintext password/token.
- Tránh render lại dữ liệu có thể thay đổi mà làm sai nội dung nghiệp vụ.

Ví dụ một yêu cầu gửi hóa đơn có thể tham chiếu `invoiceVersion` và tài liệu bất biến; không nên tham chiếu một file tạm sẽ tự xóa trước `scheduledAt`.

### Lưu thời điểm với độ chính xác nhất quán

Database, Java và frontend có thể có độ chính xác khác nhau (mili giây, micro giây...). Khi test “không gửi sớm”, nên xác định quy tắc làm tròn và so sánh. Không để frontend hiển thị chính xác tới phút nhưng database lưu một thời điểm đã vô tình làm tròn xuống nhiều phút.

## 11. State machine: từ yêu cầu gửi đến kết quả SMTP

Một lịch gửi thường cần nhiều trạng thái hơn `SCHEDULED/SENT`:

~~~mermaid
flowchart TD
    A["PENDING"] --> B["PROCESSING"]
    A --> C["CANCELLED"]
    A --> D["EXPIRED"]
    B --> E{"Submission result"}
    E -- "SMTP accepted" --> F["SUBMITTED"]
    E -- "Temporary failure, safe to retry" --> G["RETRY_PENDING"]
    E -- "Permanent failure" --> H["FAILED_PERMANENT"]
    E -- "Outcome unclear" --> I["SUBMISSION_UNKNOWN"]
    G --> B
    G --> C
    G --> D
    I --> J["Reconciliation / manual decision"]
~~~

Các trạng thái là **ứng dụng tự định nghĩa**, không phải status mặc định của Spring Mail. Có thể dùng `SCHEDULED` để diễn đạt `PENDING` có `scheduledAt > now`, nhưng việc lưu một enum chung và timestamp thường đơn giản hơn.

### Quy tắc chuyển trạng thái

| Trạng thái hiện tại | Hành động | Kết quả |
| --- | --- | --- |
| PENDING, chưa tới hạn | Worker poll | Không claim |
| PENDING, đến hạn | Worker claim atomically | PROCESSING |
| PENDING, người dùng hủy | Hủy có quyền | CANCELLED |
| PENDING, đổi lịch | Cập nhật timestamp có version | Vẫn PENDING |
| RETRY_PENDING, chưa đến hạn retry | Worker poll | Không claim |
| RETRY_PENDING, đến hạn | Worker claim | PROCESSING |
| PROCESSING, SMTP accepted | Ghi final 250 hoặc kết quả provider rõ | SUBMITTED |
| PROCESSING, lỗi tạm trước submit | Retry policy | RETRY_PENDING |
| PROCESSING, lỗi recipient/content permanent | Stop | FAILED_PERMANENT |
| PROCESSING, mất final reply sau DATA | Không xác định | SUBMISSION_UNKNOWN |
| PENDING/RETRY_PENDING, đã hết hạn | Expiry policy | EXPIRED |
| SUBMITTED, có request cancel | Không thể hứa thu hồi | Trả conflict / trạng thái đã gửi |

Một số cơ sở dữ liệu và provider có khả năng hủy/chỉnh job đã nhận nhưng chưa thực sự gửi; khi không có bằng chứng như vậy, **không được báo “đã hủy chắc chắn” sau khi worker bắt đầu SMTP**.

## 12. Tạo yêu cầu gửi trong transaction

Một service tạo lịch nên:

1. Xác thực người gọi và tenant.
2. Kiểm tra quyền gửi tới recipient, template và loại email.
3. Giải nghĩa NOW/AT, timezone, expiry và giới hạn đặt trước.
4. Chọn payload version hoặc template dữ liệu phải được bảo toàn.
5. Tạo idempotency key/kiểm tra trùng.
6. Lưu một record `PENDING` trong transaction.
7. Commit trước khi worker có thể dispatch.
8. Trả ID/trạng thái đã tiếp nhận.

### Java domain command

~~~java
package com.example.mail.schedule;

import java.time.Instant;
import java.util.Map;

public enum ScheduleMode { NOW, AT }

public record CreateMailSchedule(
        String tenantId,
        String recipientId,
        String templateKey,
        Map<String, Object> templateData,
        ScheduleMode mode,
        Instant scheduledAt,
        Instant expiresAt,
        String idempotencyKey) {
}
~~~

`scheduledAt` trong record trên đã được chuyển từ local date-time sang `Instant` ở API boundary. Với mode NOW, service sẽ dùng thời điểm từ `Clock` thay vì tin một thời gian client tự gửi. `Map<String,Object>` chỉ để minh họa; production nên dùng DTO/schema có giới hạn và không nhận mọi object tùy ý.

### Tách logic tính thời điểm

~~~java
package com.example.mail.schedule;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

public final class ScheduleValidator {

    private final Clock clock;
    private final Duration maxAdvance;

    public ScheduleValidator(Clock clock, Duration maxAdvance) {
        this.clock = clock;
        this.maxAdvance = maxAdvance;
    }

    public Instant computeScheduledAt(CreateMailSchedule command) {
        Instant now = clock.instant();

        if (command.mode() == ScheduleMode.NOW) {
            return now;
        }
        if (command.mode() != ScheduleMode.AT
                || command.scheduledAt() == null) {
            throw new IllegalArgumentException(
                    "AT mode requires scheduledAt");
        }

        Instant requested = command.scheduledAt();
        if (requested.isBefore(now)) {
            throw new IllegalArgumentException(
                    "Cannot schedule in the past");
        }
        if (requested.isAfter(now.plus(maxAdvance))) {
            throw new IllegalArgumentException(
                    "Requested time is too far away");
        }
        if (command.expiresAt() != null
                && !command.expiresAt().isAfter(requested)) {
            throw new IllegalArgumentException(
                    "expiresAt must be after scheduledAt");
        }
        return requested;
    }
}
~~~

Code sử dụng `Clock` giúp test các thời điểm biên không cần `Thread.sleep()`. Với mode NOW, cũng cần kiểm tra `expiresAt` và các preconditions nghiệp vụ ở service ngoài `computeScheduledAt`; ví dụ này cố ý chỉ minh họa cách tính lịch.

### Ghi outbox cùng nghiệp vụ

~~~java
@Transactional
public Order confirmPayment(PaymentEvent event) {
    Order order = orderRepository.markPaid(
            event.orderId(), event.paymentId());

    mailScheduleRepository.insertPending(
            MailSchedule.pendingNow(
                    order.getTenantId(),
                    order.getCustomerId(),
                    "payment-confirmed",
                    order.getId().toString(),
                    clock.instant()));

    return order;
}
~~~

Tên `MailSchedule` và `MailScheduleRepository` trong ví dụ là types của ứng dụng. Ý chính là **ghi dữ liệu nghiệp vụ và yêu cầu gửi trong cùng database transaction**, không gọi SMTP trong transaction rồi hy vọng hai hệ thống commit cùng nhau.

### Nếu email đặt lịch từ hành động độc lập

Với một email marketing do người dùng đặt giờ, API có thể chỉ ghi record `mail_schedule` rồi trả `202 Accepted`. Với một email xác nhận thanh toán, outbox record phải đồng bộ với transaction thanh toán; không cần tạo transaction riêng chỉ để HTTP request trả nhanh.

## 13. Idempotency khi tạo lịch

Một client có thể gửi lại cùng HTTP request vì timeout; nếu mỗi lần tạo một lịch mới, người nhận sẽ nhận nhiều email.

Ví dụ request:

~~~http
POST /api/mail-schedules
Idempotency-Key: receipt-order-184
Content-Type: application/json

{"mode":"NOW","recipientId":"recipient-42","templateKey":"receipt"}
~~~

Quy tắc phù hợp:

- Unique key trong phạm vi tenant/operation.
- Nếu cùng key và cùng payload đã tiếp nhận, trả ID của record cũ.
- Nếu cùng key nhưng payload khác, trả conflict (ví dụ HTTP 409).
- Không dùng một key duy nhất cho tất cả người dùng/tenant.
- Lưu hash của request hợp lệ hoặc version logic cần kiểm tra.
- Nếu job đã `SUBMITTED`, API trùng key không tạo lần gửi mới.

**Unique constraint** ở database là tuyến phòng thủ cuối khi hai request đến đồng thời. Một bước `findByKey()` trước `insert()` không đủ chống race nếu không có unique constraint/atomic upsert.

### Idempotency không phải exactly-once SMTP

Khóa này ngăn tạo trùng yêu cầu nghiệp vụ, nhưng nếu worker đã submit SMTP và process chết trước khi ghi trạng thái, việc submit có thể bị lặp khi phục hồi. Cần attempt tracking và chính sách `SUBMISSION_UNKNOWN` riêng.

## 14. Một endpoint Spring REST cho NOW/AT

Ví dụ interface API dùng thời điểm UTC đã xác định:

~~~java
package com.example.mail.schedule;

import java.time.Instant;
import java.util.UUID;

public record ScheduleMailRequest(
        ScheduleMode mode,
        Instant scheduledAt,
        String recipientId,
        String templateKey,
        String idempotencyKey) {
}

public record ScheduleMailResponse(
        UUID id,
        String status,
        Instant scheduledAt) {
}
~~~

~~~java
package com.example.mail.schedule;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/mail-schedules")
public class MailScheduleController {

    private final MailScheduleService service;

    public MailScheduleController(MailScheduleService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<ScheduleMailResponse> create(
            @RequestBody ScheduleMailRequest request) {

        ScheduleMailResponse result = service.create(request);
        return ResponseEntity.accepted().body(result);
    }
}
~~~

`MailScheduleService` là lớp ứng dụng chưa được định nghĩa trong ví dụ. Trong triển khai thật, `tenantId` phải được suy ra từ context đã xác thực, không tin một tenant ID tự gửi trong body. Bổ sung Bean Validation, authorization, `Idempotency-Key` policy, giới hạn request size và xử lý exception thành HTTP status có ý nghĩa.

### Response có ý nghĩa

~~~json
{
  "id": "a1a6d179-3cb2-47e7-bb2f-d34eebeb5ac1",
  "status": "PENDING",
  "scheduledAt": "2026-11-20T02:00:00Z"
}
~~~

Với NOW, response vẫn có thể là `PENDING` trong một khoảng ngắn cho tới khi worker gửi. UI nên hiển thị “Đã lên lịch gửi” hoặc “Đang chờ gửi”, không hiển thị “Đã giao thành công” chỉ từ HTTP 202.

## 15. Polling worker: tìm job đã đến hạn

Một cách đơn giản là dùng `@Scheduled(fixedDelayString=...)` để chạy worker định kỳ:

~~~java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class DueMailPoller {

    private final MailDispatchService dispatcher;

    public DueMailPoller(MailDispatchService dispatcher) {
        this.dispatcher = dispatcher;
    }

    @Scheduled(fixedDelayString = "PT1S")
    public void dispatchDueMail() {
        dispatcher.dispatchDueBatch();
    }
}
~~~

Với Spring scheduling, phải bật scheduling trong cấu hình Spring phù hợp (ví dụ `@EnableScheduling`) nếu ứng dụng chưa có. Dạng duration string và các thuộc tính `@Scheduled` cần kiểm tra theo phiên bản Spring đang dùng; có thể thay bằng cấu hình milliseconds `fixedDelayString = "1000"` để rõ đơn vị. **Đây chỉ là timer gọi dispatcher**, không phải nơi chứa lịch email.

### Fixed delay và fixed rate

- `fixedDelay`: đợi một khoảng sau khi lần chạy trước kết thúc.
- `fixedRate`: cố chạy theo nhịp từ thời điểm bắt đầu, phụ thuộc scheduler/executor.
- `cron`: lịch lặp theo calendar, có timezone semantics.

Nếu một poll kéo dài vì gửi SMTP đồng bộ, `fixedDelay` có thể khiến việc phát hiện job đến hạn bị chậm. Thiết kế tốt là poll để **claim một batch có giới hạn**, sau đó giao việc cho executor/worker pool được giới hạn, không giữ transaction database trong quá trình gọi SMTP.

### Poll mỗi giây không đồng nghĩa gửi chính xác từng giây

Độ trễ phụ thuộc:

- Poll interval.
- Scheduler thread pool và CPU.
- Database query/lock contention.
- Số job cùng đến hạn.
- Worker concurrency và provider quota.
- Kết nối SMTP và network.

Nếu yêu cầu chặt hơn, phải xác định SLO và kiến trúc queue/scheduler phù hợp. Một timer 100 ms không thể bảo đảm Inbox delivery trong 100 ms.

## 16. Tránh hai worker gửi cùng một job

Trong production thường có nhiều replica. Nếu mỗi instance chạy truy vấn:

~~~sql
SELECT *
FROM mail_schedule
WHERE status = 'PENDING'
  AND scheduled_at <= CURRENT_TIMESTAMP;
~~~

rồi gọi SMTP, **hai worker có thể đọc cùng record và cùng gửi**. Cần claim atomically ở database.

### PostgreSQL `FOR UPDATE SKIP LOCKED`

Một cách lấy batch có thể là:

~~~sql
BEGIN;

WITH due AS (
    SELECT id
    FROM mail_schedule
    WHERE status IN ('PENDING', 'RETRY_PENDING')
      AND available_at <= CURRENT_TIMESTAMP
      AND scheduled_at <= CURRENT_TIMESTAMP
      AND (expires_at IS NULL
           OR expires_at > CURRENT_TIMESTAMP)
    ORDER BY priority DESC, available_at, created_at
    LIMIT 20
    FOR UPDATE SKIP LOCKED
)
UPDATE mail_schedule AS m
SET status = 'PROCESSING',
    lease_owner = 'worker-17',
    lease_until = CURRENT_TIMESTAMP + INTERVAL '45 seconds',
    generation = generation + 1,
    updated_at = CURRENT_TIMESTAMP
FROM due
WHERE m.id = due.id
RETURNING m.id,
          m.tenant_id,
          m.recipient_id,
          m.scheduled_at,
          m.generation;

COMMIT;
~~~

Đây là PostgreSQL-specific SQL. Các cơ sở dữ liệu khác có cơ chế locking khác. Trong production, `worker-17` phải là identity của instance hiện tại; không hardcode một tên giống nhau cho mọi worker.

### Vì sao transaction claim phải ngắn?

1. Bắt đầu transaction.
2. Chọn và update records theo lease.
3. Commit transaction.
4. **Sau commit**, gọi SMTP ngoài database transaction.
5. Ghi kết quả trong transaction riêng.

Không giữ row lock và transaction mở trong khi kết nối SMTP. SMTP có thể timeout; giữ transaction khiến lock contention và database connection pool bị cạn.

### SKIP LOCKED không tự tạo exactly-once

Nó giúp tránh **claim cùng một record đồng thời** trong transaction. Nhưng nếu worker gửi thành công rồi chết trước khi cập nhật `SUBMITTED`, việc phục hồi vẫn có thể tạo duplicate. Lease, trạng thái `SUBMISSION_UNKNOWN` và reconciliation cần được thiết kế riêng.

## 17. Lease, fencing và việc phục hồi worker

Một job `PROCESSING` có thể bị bỏ dở khi:

- JVM/pod bị kill hoặc restart.
- SMTP socket treo quá lâu.
- Worker lỗi trước khi ghi kết quả.
- Database tạm unavailable sau khi SMTP đã trả kết quả.
- Worker mất quyền sở hữu lease vì chạy quá deadline.

Một lease cho phép hệ thống phát hiện job không còn worker chủ động, nhưng **không có nghĩa tất cả job hết lease được phép gửi lại ngay**.

### Một failure window quan trọng

~~~text
Worker A                   SMTP relay
   |                           |
   |---- message DATA -------->|
   |<--- 250 accepted ---------|
   |                           |
   X process crashes           |
   |                           |
Database still says PROCESSING
   |
Lease expires
   |
Worker B wants to resend
~~~

Nếu worker B chuyển record thành PENDING rồi gọi SMTP mà không đối soát, email có thể bị gửi hai lần. Để giảm rủi ro:

- Lưu **một attempt record cho mỗi lời gọi transport**.
- Gắn `startedAt`, `providerKey`, attempt ID và `submissionPhase` nếu adapter có thể theo dõi.
- Khi phục hồi record PROCESSING cũ, phân loại “chưa gọi send” và “có thể đã gọi send”.
- Với attempt đã có khả năng submit, chuyển `SUBMISSION_UNKNOWN` hoặc quy trình reconciliation trước khi tự retry.
- Nếu provider hỗ trợ message status lookup/idempotency API, tận dụng theo đúng hợp đồng.

### Fencing token bảo vệ database, không thu hồi email

`generation` có thể đóng vai trò fencing token. Khi worker ghi kết quả, cần điều kiện:

~~~sql
UPDATE mail_schedule
SET status = 'SUBMITTED',
    submitted_at = CURRENT_TIMESTAMP,
    updated_at = CURRENT_TIMESTAMP,
    lease_owner = NULL,
    lease_until = NULL
WHERE id = :id
  AND status = 'PROCESSING'
  AND lease_owner = :workerId
  AND generation = :generation;
~~~

Nếu số row update bằng 0, worker **không được ghi đè** trạng thái mới. Tuy nhiên nếu worker đã gửi email ra SMTP, token không thể làm “thu hồi” lần gửi. Chính vì vậy fencing và exactly-once external effect là hai khái niệm khác nhau.

### Lease phải đủ dài nhưng không che giấu worker lỗi

Nếu SMTP timeout có thể kéo dài 20 giây, lease 5 giây sẽ hết trong khi worker còn đang gửi. Có thể dùng lease đủ dài hoặc heartbeat có kiểm soát. Nếu heartbeat cũng bị lỗi database, đừng để worker mất lease rồi một worker khác đồng thời gửi cùng message. Khi không thể bảo đảm ownership trước khi gọi transport, nên dừng/defer thay vì tạo nguy cơ duplicate.

## 18. Java worker: kiểm tra lần cuối trước SMTP

Worker không được chỉ dựa vào validation lúc tạo lịch. Giữa thời điểm `PENDING` và thời điểm submit, nhiều điều kiện có thể thay đổi:

- User hủy lịch hoặc đổi giờ.
- Recipient unsubscribe/complain.
- Email address bị cập nhật hoặc xác minh không còn hợp lệ.
- OTP/reset token đã hết hạn.
- Template hoặc attachment source bị thu hồi.
- Provider/account bị khóa, rate limit cạn.
- Quyền người tạo lịch hoặc tenant thay đổi.

Một quy trình worker có thể như sau:

~~~java
public void dispatch(MailScheduleJob job) {
    // Job đã được claim atomically và có lease/fencing.
    if (clock.instant().isBefore(job.scheduledAt())) {
        scheduleRepository.deferWithoutAttempt(job.id());
        return;
    }

    if (job.expiresAt() != null
            && !clock.instant().isBefore(job.expiresAt())) {
        scheduleRepository.markExpired(job.id());
        return;
    }

    if (!recipientPolicy.isAllowed(
            job.tenantId(), job.recipientId(), job.category())) {
        scheduleRepository.markSuppressed(job.id());
        return;
    }

    if (!providerLimiter.tryAcquire(job.providerKey())) {
        scheduleRepository.deferForRateLimit(job.id());
        return;
    }

    // Bên dưới chỉ là ví dụ về trình tự.
    // Production cần fencing/attempt ledger, xử lý lock và timeout.
    try {
        MimeMessage message = renderer.prepare(job);
        mailSenderRegistry.get(job.providerKey()).send(message);
        scheduleRepository.markSubmitted(job.id());
    } catch (MailException error) {
        failureHandler.recordAndDecide(job, error);
    }
}
~~~

**Đây là pseudocode kiểu Java**: các lớp `MailScheduleJob`, repository, `recipientPolicy`, `providerLimiter`, renderer, sender registry và failure handler là thành phần của ứng dụng. Phương thức `send(MimeMessage)` hợp lệ trên `JavaMailSender`; nếu dùng `MimeMessage` thì cần `jakarta.mail.internet.MimeMessage` và các import phù hợp. Ví dụ cố ý không hứa mọi lỗi `MailException` có thể phân loại đủ chỉ từ class.

### Cần áp dụng cùng fencing cho mọi state update

Trong code production, các lệnh `markExpired`, `markSuppressed`, `deferForRateLimit`, `markSubmitted` và `failureHandler` phải ràng buộc `leaseOwner/generation`; không dùng `UPDATE ... WHERE id=?` trần. Nếu không, một worker cũ có thể ghi đè quyết định hủy/đổi lịch của người dùng.

### Giới hạn race giữa “revalidate” và “send”

Ngay cả khi kiểm tra suppression xong trước lời gọi SMTP, người dùng có thể unsubscribe trong vài mili giây tiếp theo. Cần một mô hình nhất quán về quyền gửi:

- Quy định rõ thời điểm bắt đầu dispatch/claim là ranh giới “đang gửi”.
- Đồng bộ thay đổi status qua transaction và fencing.
- Nếu yêu cầu consent chặt hơn, dùng một quyết định permit có version/revalidation tức thời.
- Khi đã bắt đầu gửi và external side effect có thể xảy ra, API không được hứa hủy tuyệt đối.

Không có cách đơn giản để dùng cùng một database transaction khóa cả email permission và SMTP socket mà có thể rollback external send; cần chấp nhận, đo và truyền đạt giới hạn này.

## 19. Lỗi SMTP và retry khi gửi theo lịch

Một message đến hạn có thể lỗi vì:

| Lỗi | Ví dụ | Quyết định điển hình |
| --- | --- | --- |
| Transport chưa kết nối được | DNS, TCP refused, connect timeout | Retry có backoff nếu còn hạn |
| SMTP server chưa phản hồi ở EHLO | Read timeout trước envelope | Retry có backoff, giám sát provider |
| SMTP `421` / `451` | Service tạm unavailable | Retry có giới hạn, throttling |
| AUTH `535` | Credential sai/quyền account | Hold provider lane; không retry mọi job liên tục |
| RCPT `550 5.1.1` | Recipient không tồn tại theo bằng chứng | Permanent failure/suppression theo policy |
| DATA `554` rõ ràng | Content/policy rejected | Điều tra; không retry mù |
| Mất final reply sau DATA | Không biết chắc relay accepted | `SUBMISSION_UNKNOWN`, đối soát |
| SMTP `250` sau DATA | Relay accepted | `SUBMITTED`, theo dõi delivery |
| Rate limiter không cấp permit | Chưa gọi SMTP | Defer, không tính physical SMTP attempt |
| Message hết hạn | OTP/offer không còn hiệu lực | EXPIRED, không gửi |

### Một lịch gửi bị trễ vì retry

Ví dụ:

~~~text
User requested: 2026-11-20 09:00 Asia/Ho_Chi_Minh
Scheduled UTC:  2026-11-20T02:00:00Z

09:00:00  worker dispatch, SMTP returns temporary 451
09:02:00  retry eligible
09:02:05  relay accepts

requested send time = 09:00
submitted time      = 09:02:05
lateness            = 2 min 05 s
~~~

Không sửa lịch gốc thành 09:02:05. Dashboard cần hiển thị người dùng đã yêu cầu 09:00 và hệ thống submit muộn vì lỗi tạm thời.

### Retry policy phải có expiry

Email OTP có thể chỉ có hiệu lực 5 phút; gửi sau 2 giờ là sai nghiệp vụ. Một thư nhắc cuộc họp có thể vô ích nếu cuộc họp đã bắt đầu. Một email hóa đơn có thể retry lâu hơn. Không dùng cùng retry TTL cho mọi category.

~~~java
public boolean mayRetry(
        Instant nextAttempt,
        Instant expiresAt,
        int attempts,
        int maxAttempts) {

    if (attempts >= maxAttempts) {
        return false;
    }
    return expiresAt == null
            || nextAttempt.isBefore(expiresAt);
}
~~~

Đây chỉ là một phần của policy. Cần xét loại lỗi, consent, suppression, provider/account health và kết quả submit trước đó. Một lỗi `SUBMISSION_UNKNOWN` không được tự chuyển sang nhánh retry chỉ vì vẫn còn attempts.

## 20. Backoff và jitter cho lịch gửi bị lỗi

Một công thức phổ biến:

\[
d_n=\min(d_{\max}, d_0\cdot 2^{n-1})+\text{jitter}
\]

Trong đó `n` là lần thất bại có thể retry; `d0` là khoảng chờ ban đầu và `dmax` là giới hạn. Jitter giảm việc hàng nghìn message cùng retry một lúc sau outage.

Ví dụ minh họa:

| Lần submit | Kết quả | Lịch retry |
| --- | --- | --- |
| 1 | Temporary SMTP failure | Chờ 30–45 giây |
| 2 | Temporary SMTP failure | Chờ 60–90 giây |
| 3 | Temporary SMTP failure | Chờ 2–3 phút |
| 4 | Success | Dừng retry, SUBMITTED |
| Hết ngân sách | Không tự gửi nữa | DEAD_LETTER hoặc HOLD theo policy |

Các giá trị chỉ minh họa; thực tế cần theo provider quota, SLA và expiry. Jitter nên có nguồn ngẫu nhiên có thể kiểm soát trong unit test; không assert timestamp chính xác khi chạy random production.

### Không sleep trong worker để chờ retry

Không làm:

~~~java
try {
    mailSender.send(message);
} catch (MailException exception) {
    Thread.sleep(60_000);
    mailSender.send(message);
}
~~~

Đoạn này giữ thread 60 giây, có thể bỏ qua hủy lịch/expiry, mất lịch khi JVM restart và không kiểm soát toàn bộ retry budget. Thay vào đó, persist `availableAt` cho attempt kế tiếp rồi giải phóng worker.

### Retry nhiều tầng

Nếu adapter tự retry 3 lần, dispatcher lại retry 4 lần, queue cũng redeliver, số SMTP calls thực có thể vượt 12. Định nghĩa một ngân sách tổng theo notification và quan sát số physical submit attempts. Nếu dùng provider đã accepted và đang retry downstream, **không tạo thêm một SMTP submission** chỉ vì thấy event `DEFERRED`.

## 21. Hủy lịch trước thời điểm gửi

Người dùng có thể tạo một email gửi vào ngày mai rồi hủy trước khi đến hạn. Cần một API:

~~~http
DELETE /api/mail-schedules/{scheduleId}
~~~

Nhưng phải xác định rõ trạng thái nào cho phép hủy:

| Trạng thái | Hủy ngay? | Phản hồi hợp lý |
| --- | --- | --- |
| PENDING | Có, nếu caller có quyền | CANCELLED |
| RETRY_PENDING | Có, nếu chưa claim lại | CANCELLED |
| PROCESSING | Không hứa chắc | Conflict, “đang gửi” hoặc cancellation pending có semantics rõ |
| SUBMITTED | Không thu hồi qua SMTP | Already submitted |
| SUBMISSION_UNKNOWN | Không hứa an toàn | Reconciliation required |
| CANCELLED | Idempotent no-op | Already cancelled |
| EXPIRED | Không cần gửi nữa | Already expired |

### Atomic cancellation trong SQL

~~~sql
UPDATE mail_schedule
SET status = 'CANCELLED',
    stop_reason = 'USER_CANCELLED',
    generation = generation + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :scheduleId
  AND tenant_id = :tenantId
  AND status IN ('PENDING', 'RETRY_PENDING')
RETURNING id;
~~~

Nếu update trả một row, request đã được hủy khi job còn dispatchable. Nếu trả 0 row, cần đọc trạng thái mới nhất **trong quyền tenant** để phân biệt không tồn tại, đã gửi, đang gửi hay đã hủy. Không trả “hủy thành công” chỉ vì HTTP đã nhận DELETE.

### Race với worker claim

Worker và API hủy cùng update một record:

~~~text
Time ->

API cancel:  UPDATE status=PENDING -> CANCELLED
Worker:      UPDATE status=PENDING -> PROCESSING
~~~

Chỉ một chuyển trạng thái có thể thắng nếu database operation atomic và điều kiện status được dùng đúng. Nếu hủy thắng, worker không được claim record đó. Nếu worker claim thắng, API phải báo đang xử lý thay vì hứa có thể thu hồi SMTP.

### Không dùng `ScheduledFuture.cancel()` làm bằng chứng duy nhất

Với `TaskScheduler` in-memory, `ScheduledFuture.cancel(false)` có thể giúp hủy task chưa chạy trên một JVM. Nhưng trong distributed/durable scheduler, hủy phải cập nhật **nguồn sự thật bền vững**; một future đã bị hủy ở một instance không chứng minh worker ở instance khác không còn job.

## 22. Đổi lịch gửi (reschedule)

Người dùng có thể yêu cầu dời từ 9 giờ sang 11 giờ. Một API:

~~~http
PATCH /api/mail-schedules/{scheduleId}
Content-Type: application/json

{"scheduledAt":"2026-11-20T04:00:00Z"}
~~~

Với lịch cũ 09:00 ở Việt Nam (02:00Z), giá trị mới 04:00Z tương đương 11:00. Thay đổi cần:

1. Authorization đúng tenant/owner.
2. Kiểm tra job chưa `PROCESSING` hoặc `SUBMITTED`.
3. Kiểm tra thời điểm mới không quá khứ/quá xa.
4. Kiểm tra timezone/DST nếu người dùng sửa bằng local time.
5. Kiểm tra expiry vẫn sau lịch mới.
6. Cập nhật `scheduledAt` và `availableAt` đồng bộ.
7. Tăng `generation` hoặc row version.
8. Ghi audit lịch cũ, lịch mới, người thay đổi.

### SQL optimistic update

~~~sql
UPDATE mail_schedule
SET scheduled_at = :newScheduledAt,
    available_at = :newScheduledAt,
    status = 'PENDING',
    generation = generation + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :scheduleId
  AND tenant_id = :tenantId
  AND generation = :expectedGeneration
  AND status = 'PENDING'
RETURNING id, generation, scheduled_at;
~~~

Ở đây chỉ cho đổi lịch khi PENDING; nếu muốn đổi `RETRY_PENDING`, phải xác định có reset attempt count hay không. **Không mặc định reset lịch retry và xóa lịch sử lỗi**, vì có thể tạo nhiều attempts hơn ngân sách hoặc gửi lại khi outcome chưa chắc chắn.

### Đổi lịch không tạo lịch mới ngoài ý muốn

Một request PATCH bị client gửi lại vì timeout không nên tạo nhiều schedules. Lưu một record duy nhất và dùng `If-Match`/generation để chống cập nhật trên dữ liệu cũ; trả conflict nếu người dùng đang sửa một phiên bản đã thay.

## 23. Hủy sau khi người dùng đã thấy trạng thái “đang gửi”

Ngay sau khi worker claim, có một cửa sổ trước khi thực sự mở socket SMTP. Một hệ thống có thể hỗ trợ **cancellation requested** và worker kiểm tra flag lần cuối. Nhưng cần giải thích rõ:

- Nếu worker chưa bắt đầu external send, có thể hủy.
- Nếu socket SMTP đã bắt đầu, có thể không biết thư đã được relay accepted hay chưa.
- Việc đóng socket không bảo đảm relay chưa xử lý DATA.
- Nếu SMTP đã accepted, hủy trong database không làm email biến mất khỏi relay.

**Không thiết kế UI hiển thị “Email đã được hủy và chắc chắn sẽ không tới” khi đã có attempt đang gửi.** Nếu cần hành vi gần “thu hồi”, phải dùng tính năng provider hỗ trợ cùng điều kiện cụ thể; SMTP không có API thu hồi phổ quát.

## 24. Đổi múi giờ của người dùng sau khi đã đặt lịch

Một kịch bản khó:

1. Người dùng đặt “gửi lúc 09:00 ngày 20/11 theo `Asia/Ho_Chi_Minh`”.
2. Sau đó họ đổi timezone profile thành `America/Los_Angeles`.
3. Lịch cũ có nên chuyển sang 09:00 Los Angeles không?

Không có câu trả lời duy nhất. Phải quyết định ở tầng nghiệp vụ:

**Lịch theo Instant cố định:** `scheduledAt` không đổi; UI có thể hiển thị theo timezone mới. Phù hợp một lần gửi đã hẹn tại thời điểm xác định.

**Lịch gắn với local civil time:** quy tắc “gửi lúc 09:00 giờ địa phương hiện tại của người nhận” có thể cần tính lại khi timezone thay đổi. Phù hợp reminders recurring hoặc quy tắc dài hạn.

Lưu cả `Instant`, `requestedZoneId`, `requestedLocalDateTime` và policy để tránh tự thay lịch trong im lặng. Với **một email một lần**, nhiều hệ thống chọn giữ `Instant` đã được xác nhận; với lịch lặp theo local time, cần đánh giá lại từng lần phát sinh.

## 25. Người nhận ở nhiều timezone

Một chiến dịch muốn gửi “08:00 giờ địa phương của mỗi người nhận” thực chất có **nhiều Instant khác nhau**:

~~~text
Recipient A: Asia/Ho_Chi_Minh, 2026-11-20 08:00
Recipient B: Europe/London,     2026-11-20 08:00
Recipient C: America/New_York,  2026-11-20 08:00
~~~

Nếu tính một `Instant` duy nhất từ timezone của admin rồi áp cho tất cả, email sẽ đến vào các giờ địa phương khác nhau.

### Cách tổ chức

- Quy định timezone nguồn của recipient được xác minh từ đâu.
- Giải nghĩa local 08:00 cho từng recipient theo IANA zone.
- Tạo một record `scheduledAt` per recipient hoặc chia cohort theo thời điểm UTC.
- Cố định quy tắc DST gap/overlap.
- Giới hạn batch/throughput vì nhiều recipient có thể cùng đến hạn.
- Trước send, kiểm tra consent và suppression ở recipient level.

### Không gửi sớm để đỡ tắc hàng đợi

Nếu nhiều thư cùng đến hạn lúc 08:00, worker có thể bắt đầu xử lý theo quota và một số thư gửi muộn. **Không tự gửi từ 07:45** để bảo đảm tất cả thư được nhận trong 08:00 nếu hợp đồng yêu cầu không submit trước giờ.

Nếu nhu cầu là “tất cả email đến Inbox quanh 08:00”, SMTP không có bảo đảm này; cần truyền đạt SLA thực tế và xem cách thiết kế chiến dịch/nhà cung cấp.

## 26. Quy tắc gửi lặp không giống một lần gửi theo lịch

“Gửi đúng một lần vào 09:00 ngày 20/11” và “gửi 09:00 mỗi thứ Hai” là hai loại dữ liệu:

- **One-shot schedule:** một mốc `Instant` duy nhất, sau khi submit thành công thì kết thúc lịch đó.
- **Recurring rule:** một quy tắc sinh ra nhiều occurrences, thường có timezone, lịch nghỉ, ngày hết hạn và chính sách DST.

Ví dụ:

~~~text
Recurring rule:
  tenantId      = t-01
  template      = weekly-report
  dayOfWeek     = MONDAY
  localTime     = 09:00
  zoneId        = Asia/Ho_Chi_Minh

Generated occurrences:
  report-2026-11-16 -> scheduledAt=2026-11-16T02:00:00Z
  report-2026-11-23 -> scheduledAt=2026-11-23T02:00:00Z
  report-2026-11-30 -> scheduledAt=2026-11-30T02:00:00Z
~~~

Một kiến trúc có thể sinh **các one-shot records** từ recurring rule và dùng lại dispatcher. Mỗi occurrence có idempotency key riêng để không tạo lại khi scheduler restart.

### Không dùng cron của server làm timezone của người dùng

Nếu dùng `@Scheduled(cron = "...", zone = "...")` trong Spring, timezone được chọn cho việc chạy cron của **ứng dụng**. Nó không tự tạo lịch 09:00 theo từng recipient zone. Với người dùng toàn cầu, cần tính occurrences riêng hoặc cohort riêng.

### Bỏ qua, gửi bù hay tạo lại occurrence khi ứng dụng outage?

Giả sử app ngừng từ 08:50 tới 11:00, trong đó có một recurring occurrence 09:00. Khi hồi phục, hệ thống phải có policy:

- **Catch-up:** vẫn gửi nếu còn trong grace period.
- **Skip missed:** bỏ và ghi `MISSED`.
- **Latest only:** chỉ gửi kỳ mới nhất thay vì dồn các kỳ cũ.
- **Hold for review:** đối với mail nhạy cảm.

Không để `@Scheduled` quyết định bằng hành vi tình cờ khi missed execution; lưu nguyên tắc nghiệp vụ vào cấu hình và trạng thái.

## 27. Nội dung email được chốt khi đặt lịch hay lúc gửi?

Một lịch đặt trước nhiều ngày tạo câu hỏi: **payload nào sẽ được gửi vào ngày đó?**

### Render ngay khi tạo lịch

Ưu điểm:

- Nội dung được “đóng băng” theo đúng thứ người dùng đã duyệt.
- Tránh template/dữ liệu thay đổi làm lệch ý nghĩa.
- Dễ kiểm toán bản nháp đã phê duyệt.

Nhược điểm:

- Phải lưu HTML/plain text và metadata có thể nhạy cảm lâu ngày.
- Link/token có thể hết hạn trước ngày gửi.
- Nội dung động như “giá trị hiện tại” trở nên cũ.
- Attachment đã render có thể chiếm nhiều storage.

### Render vào thời điểm gửi

Ưu điểm:

- Dữ liệu và template có thể cập nhật gần thời điểm submit.
- Có thể tạo link/token mới theo chính sách.
- Giảm thời gian lưu nội dung đã render.

Nhược điểm:

- Thứ người nhận đọc có thể khác bản người gửi đã xem trước.
- Template đã bị xóa, model thay đổi hoặc resource không còn truy cập được.
- Nếu business data thay đổi, mail có thể không còn phản ánh sự kiện gốc.

### Một lựa chọn kết hợp

Lưu `templateKey`, `templateVersion`, `businessSnapshotId` và attachment object reference bất biến. Tại lúc gửi:

1. Nạp đúng version đã duyệt.
2. Kiểm tra người nhận và tính hợp lệ hiện tại.
3. Chỉ đưa vào các dữ liệu động đã được định nghĩa rõ.
4. Render và validate trước submit.
5. Lưu hash/version nội dung gửi để audit.

Không tự lấy mọi giá trị mới nhất nếu đó là hóa đơn đã chốt: một thay đổi dữ liệu sau khi đặt lịch có thể làm email không khớp giao dịch được ghi nhận.

### Token nhạy cảm và expiry

Không tạo OTP hoặc reset token một tuần trước rồi đặt gửi sau một tuần khi token chỉ có hiệu lực 5 phút. Có thể thiết kế:

- Sinh token tại thời điểm gửi nếu workflow cho phép và có transaction/authorization tương ứng.
- Hoặc chỉ cho lên lịch trong cửa sổ mà token còn hiệu lực.
- Hoặc hủy và yêu cầu người dùng tạo hành động mới khi lịch vượt validity.

Một email chứa token đã hết hạn nên được `EXPIRED`, không cố gửi với hy vọng người dùng hiểu.

## 28. Attachment của email đặt lịch

Gửi sau nhiều ngày thường gặp lỗi attachment đã bị xóa hoặc đường dẫn file thay đổi.

### Không dùng đường dẫn tạm

~~~text
Job created today:
    attachmentPath = /tmp/upload-123.pdf

Scheduled next week:
    /tmp was cleaned
    -> dispatch fails
~~~

Nên lưu attachment vào storage có retention đủ lâu, object key bất biến và quyền truy cập đúng tenant:

~~~text
attachmentRef:
  objectId: documents/receipt-184/version-3
  contentSha256: ...
  sizeBytes: ...
  allowedMimeType: application/pdf
  expiresAt: after scheduled send + retry window
~~~

Ví dụ trên là metadata khái niệm. Đến hạn, worker kiểm tra object tồn tại, được phép truy cập, không vượt size limit, đã qua kiểm tra bảo mật khi cần và hash/version khớp. Nếu object không còn hoặc không được phép, **không gửi email thiếu attachment bắt buộc rồi đánh dấu thành công**.

### Retention phù hợp với retry

Nếu email được lên lịch sau 30 ngày và có thể retry 3 ngày, attachment không được xóa sau 7 ngày chỉ vì đó là TTL mặc định của upload tạm. Chính sách xóa dữ liệu vẫn phải tuân thủ quyền riêng tư; không giữ vô hạn chỉ để phòng trường hợp scheduler lỗi.

## 29. Bảo đảm không gửi sớm nhưng xử lý trễ minh bạch

Một yêu cầu AT có thể đi qua nhiều bộ điều phối. Tại **điểm thực thi**, worker vẫn phải so sánh `clock.instant()` với `scheduledAt`, dù SQL đã lọc `scheduled_at <= now()`.

### Vì sao cần kiểm tra lại?

- Worker có thể nhận job qua queue trước giờ.
- Clock giữa application và database có thể lệch.
- Người dùng vừa đổi lịch nhưng worker có snapshot cũ.
- Một queue delay/visibility mechanism có thể giao sớm trong tình huống bất thường.

Để đạt semantics tốt hơn:

1. Cấu hình đồng bộ thời gian hệ thống (NTP hoặc cơ chế platform).
2. Có một nguồn canonical cho quyết định due, ví dụ DB clock hoặc app `Clock` đã được đồng bộ.
3. Dùng version/fencing khi worker chuyển trạng thái.
4. Từ chối gửi nếu phát hiện job vẫn ở tương lai.
5. Theo dõi **early-send violations** như một lỗi nghiêm trọng.

### Clock skew

Nếu DB trả giờ 09:00:00 còn worker chậm 20 giây, một job đến hạn theo DB có thể bị worker coi là còn tương lai. Nếu worker nhanh 20 giây so với DB thì rủi ro ngược lại. Không cố “sửa” bằng cách cho gửi sớm 20 giây. Cần time synchronization và chính sách nhất quán.

### Grace period khi worker bị trễ

Ví dụ email nhắc lịch:

~~~text
scheduledAt       = 09:00
maxAllowedLateness = 10 minutes

worker starts 09:04 -> allowed late send
worker starts 09:35 -> mark MISSED / EXPIRED
~~~

Một report dài hạn có thể được phép gửi muộn nhiều giờ; OTP có thể hết hiệu lực chỉ sau vài phút. `maxAllowedLateness` phải được định nghĩa theo notification category.

## 30. Phân loại ưu tiên và công bằng trong hàng đợi

Nếu hàng trăm nghìn email marketing cùng đến hạn, các email OTP “gửi ngay” không nên bị chặn phía sau. Có thể thiết kế:

- Priority tiers: security, transactional, marketing.
- Worker pools hoặc queue partitions riêng.
- Reserved throughput cho OTP/security.
- Quota provider/account/tenant.
- Công bằng giữa tenant để một tenant không độc chiếm.
- Backpressure khi provider trả 4xx/quota.

### Priority không được làm job cũ chết đói

Nếu luôn `ORDER BY priority DESC`, liên tục có job ưu tiên cao có thể khiến job ưu tiên thấp không bao giờ chạy. Có thể dùng weighted fair queue, quota theo class hoặc aging policy. Tuy nhiên, aging cũng không được cho phép **gửi sau expiry** hoặc bypass suppression.

### Ví dụ query chọn batch

~~~sql
SELECT id
FROM mail_schedule
WHERE status IN ('PENDING', 'RETRY_PENDING')
  AND available_at <= CURRENT_TIMESTAMP
  AND scheduled_at <= CURRENT_TIMESTAMP
  AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
ORDER BY priority DESC, available_at, created_at
LIMIT 100;
~~~

Query này giúp minh họa thứ tự ưu tiên, **không phải cơ chế claim an toàn đa worker**. Để dispatch thật cần locking/lease như phần trước. Nếu lưu `availableAt` và `scheduledAt`, index phải phù hợp với query/pattern dữ liệu đang dùng.

### “Gửi ngay” không có đặc quyền vượt quy định

Email có priority cao vẫn phải:

- Được phép gửi cho recipient.
- Có sender identity đúng.
- Không vượt quota/legal constraints.
- Nội dung còn hợp lệ.
- Không gửi trùng một notification đã SUBMITTED.

Priority là thứ tự phục vụ trong tập yêu cầu **hợp lệ**, không phải lý do bỏ kiểm tra.

## 31. Rate limit và concurrency trước SMTP

Một scheduler không chỉ chịu trách nhiệm “đánh thức đúng giờ”; nó còn phải bảo đảm hệ thống không làm quá tải SMTP provider.

### Giới hạn phổ biến

| Giới hạn | Ví dụ sử dụng |
| --- | --- |
| Max in-flight connections | Bảo vệ SMTP socket và thread |
| Max messages/sec | Theo provider quota |
| Max messages/day | Theo account/contract |
| Per-domain throttling | Tránh tập trung quá nhiều mail vào một receiving domain |
| Per-tenant quota | Tránh một tenant làm nghẽn người khác |
| Per-recipient frequency | Hạn chế spam/notification fatigue |
| Category reserved capacity | Ưu tiên OTP/security khi có chiến dịch lớn |

Khi limiter từ chối một job:

1. Không gọi SMTP.
2. Không tăng physical SMTP attempt count.
3. Đặt `availableAt` mới hoặc chuyển sang queue tương ứng.
4. Giữ `scheduledAt` gốc.
5. Đo `rate_limit_deferred` và lateness.

### Nhiều instance cần limiter dùng chung

Một `Semaphore(5)` trong mỗi pod không giới hạn toàn hệ thống ở 5 kết nối nếu có 10 pod; tổng có thể là 50. Với quota cấp account/provider, cần limiter phân tán hoặc phân chia quota đã được chứng minh không vượt tổng ngân sách.

## 32. Khi có nhiều SMTP providers

Một hệ thống có thể chọn provider dự phòng khi tuyến chính gặp outage, nhưng **lịch gửi không tự cho phép failover mọi lỗi**.

Nếu `RCPT TO` trả một permanent error xác nhận mailbox không tồn tại, gửi qua provider B thường không sửa được địa chỉ. Nếu template/MIME invalid, đổi provider không sửa được payload. Nếu sender đã unsubscribe, chuyển route để tiếp tục gửi là sai chính sách.

Failover chỉ nên được cân nhắc khi:

- Lỗi thật sự ở hạ tầng/route cụ thể.
- Provider B được phê duyệt cho tenant, category, sender domain, region và dữ liệu.
- Thông điệp còn hạn và recipient vẫn được phép nhận.
- Chưa có accepted submission hoặc unknown outcome cần đối soát.
- Còn budget và quota của B.

Nếu provider A đã accepted và báo `DEFERRED` downstream, A có thể vẫn đang retry. Không gửi thêm qua B chỉ vì lịch đã trễ so với `scheduledAt` hoặc chưa thấy delivered event.

## 33. SMTP accepted không phải email đã tới

Khi `JavaMailSender.send(...)` trả về bình thường, có thể ghi nhận **submission thành công theo phản hồi transport**, không được gán ngay “đã giao vào Inbox”.

~~~text
09:00:00  scheduledAt reached
09:00:02  worker calls JavaMailSender.send()
09:00:03  relay final 250 accepted
09:00:04  application marks SUBMITTED
09:03:18  provider reports DEFERRED
09:07:40  provider reports DELIVERED
~~~

User-facing status có thể phân biệt:

| Trạng thái | Nội dung hiển thị |
| --- | --- |
| PENDING (future) | Đã đặt lịch |
| PENDING (due) | Đang chờ gửi |
| PROCESSING | Đang gửi |
| SUBMITTED | Đã gửi tới hệ thống chuyển phát |
| DELIVERED (provider event) | Nhà cung cấp báo đã giao |
| BOUNCED | Không giao được theo provider |
| RETRY_PENDING | Gửi tạm lỗi, sẽ thử lại nếu còn hạn |
| CANCELLED | Lịch đã hủy trước khi gửi |
| EXPIRED/MISSED | Bỏ gửi vì quá thời hạn |
| SUBMISSION_UNKNOWN | Cần xác minh kết quả gửi |

Trong nhiều hệ thống, Delivered chỉ là thuật ngữ được provider định nghĩa, không chứng minh người nhận thực sự đọc thư. Đừng đồng nhất open tracking (có thể bị proxy/cache/chặn ảnh) với read receipt chắc chắn.

## 34. Dùng Clock trong kiểm thử thay vì chờ thời gian thật

Kiểm thử lịch gửi không nên `Thread.sleep(60_000)` để chờ đến một phút. Test cần điều khiển thời gian:

~~~java
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TimeConfiguration {
    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

Trong test, có thể thay bằng `Clock.fixed(...)` hoặc một mutable fake clock. Với Spring test context, cần tránh tạo hai `Clock` bean gây ambiguity; dùng `@Primary`, profile hoặc cấu hình test được kiểm soát.

### Unit test gửi NOW và AT

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Map;
import org.junit.jupiter.api.Test;

class ScheduleValidatorTest {
    private static final Instant NOW =
            Instant.parse("2026-11-12T10:00:00Z");

    private final ScheduleValidator validator =
            new ScheduleValidator(
                    Clock.fixed(NOW, ZoneOffset.UTC),
                    Duration.ofDays(90));

    @Test
    void nowModeStartsAsSoonAsEligible() {
        CreateMailSchedule command = new CreateMailSchedule(
                "t1", "recipient-42", "receipt", Map.of(),
                ScheduleMode.NOW, null, null, "receipt-184");

        assertEquals(NOW,
                validator.computeScheduledAt(command));
    }

    @Test
    void atModePreservesFutureInstant() {
        Instant requested =
                Instant.parse("2026-11-20T02:00:00Z");
        CreateMailSchedule command = new CreateMailSchedule(
                "t1", "recipient-42", "reminder", Map.of(),
                ScheduleMode.AT, requested, null, "reminder-184");

        assertEquals(requested,
                validator.computeScheduledAt(command));
    }

    @Test
    void atModeRejectsPastTime() {
        CreateMailSchedule command = new CreateMailSchedule(
                "t1", "recipient-42", "reminder", Map.of(),
                ScheduleMode.AT, NOW.minusSeconds(1),
                null, "reminder-old");

        assertThrows(IllegalArgumentException.class,
                () -> validator.computeScheduledAt(command));
    }

    @Test
    void atModeRejectsTimeBeyondBookingWindow() {
        CreateMailSchedule command = new CreateMailSchedule(
                "t1", "recipient-42", "reminder", Map.of(),
                ScheduleMode.AT, NOW.plus(Duration.ofDays(91)),
                null, "reminder-too-far");

        assertThrows(IllegalArgumentException.class,
                () -> validator.computeScheduledAt(command));
    }
}
~~~

Đây là ví dụ JUnit 5 cho thành phần `ScheduleValidator` đã trình bày, không có SMTP hoặc database. Nó chứng minh logic tính `scheduledAt`, **chưa chứng minh worker thật sẽ không gửi sớm**.

### Test DST gap và overlap

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.*;
import org.junit.jupiter.api.Test;

class ScheduleTimeResolverTest {

    private static final ZoneId NEW_YORK =
            ZoneId.of("America/New_York");

    @Test
    void rejectsNonexistentLocalTime() {
        LocalDateTime gap =
                LocalDateTime.of(2026, 3, 8, 2, 30);

        assertThrows(IllegalArgumentException.class,
                () -> ScheduleTimeResolver.resolve(
                        gap, NEW_YORK, null));
    }

    @Test
    void requiresDisambiguationForOverlap() {
        LocalDateTime overlap =
                LocalDateTime.of(2026, 11, 1, 1, 30);

        assertThrows(IllegalArgumentException.class,
                () -> ScheduleTimeResolver.resolve(
                        overlap, NEW_YORK, null));
    }

    @Test
    void selectedOffsetsProduceDifferentInstants() {
        LocalDateTime overlap =
                LocalDateTime.of(2026, 11, 1, 1, 30);

        Instant earlier = ScheduleTimeResolver.resolve(
                overlap, NEW_YORK, ZoneOffset.ofHours(-4));
        Instant later = ScheduleTimeResolver.resolve(
                overlap, NEW_YORK, ZoneOffset.ofHours(-5));

        assertEquals(Duration.ofHours(1),
                Duration.between(earlier, later));
    }
}
~~~

Test kiểm tra timezone rules của Java ở một ngày cụ thể; quy tắc IANA có thể được cập nhật trong tương lai. Nếu ứng dụng có yêu cầu lập lịch nhiều năm, cần chiến lược quản lý thay đổi timezone database và giao tiếp với người dùng khi quy định địa phương đổi.

## 35. Integration test: không dispatch trước giờ

Để tin tưởng cơ chế end-to-end, cần tạo một record trong database test, chạy worker và theo dõi số lần gọi SMTP fake:

~~~text
Given:
  application Clock = 2026-11-12T10:00:00Z
  job.scheduledAt   = 2026-11-12T10:05:00Z
  job.status        = PENDING

When:
  dispatcher.dispatchDueBatch()

Then:
  no SMTP connection attempted
  job remains PENDING
  attempts remains 0

When:
  controlled Clock advances to 10:05:00Z
  dispatcher.dispatchDueBatch()

Then:
  exactly one job is claimed
  exactly one SMTP submission attempt starts
  result is persisted according to server response
~~~

Ở test transport, fake SMTP có thể trả final 250; đó là bằng chứng **submission thành công**, không phải Inbox delivery.

### Không chỉ nhìn trạng thái cuối

Nếu assert một job cuối cùng là SUBMITTED, code lỗi vẫn có thể đã gửi sớm rồi sửa status về đúng sau. Test phải ghi nhận **thời điểm kết nối/attempt** hoặc spy transport và kiểm tra không có lời gọi trước hạn.

### Test clock skew

Một suite sâu hơn có thể mô phỏng app clock khác DB clock và xác minh hệ thống theo một nguồn thời gian canonical, không dispatch trước `scheduledAt`. Đây là test phối hợp infrastructure chứ không chỉ unit test `Clock`.

## 36. Integration test: ứng dụng restart trước giờ gửi

Đây là lý do quan trọng nhất không dùng `TaskScheduler` in-memory làm nguồn lịch duy nhất:

~~~text
09:00  User schedules mail for 10:00
09:01  DB commits PENDING record
09:30  Application stops
09:50  Application starts
10:00  Worker claims due record
10:00+ SMTP relay accepted
~~~

Test cần:

1. Tạo schedule trong database thật hoặc Testcontainers.
2. Dừng instance/scheduler.
3. Khởi động lại với cùng database.
4. Xác nhận record không mất và `scheduledAt` giữ nguyên.
5. Chạy poller đến hạn.
6. Quan sát SMTP fake nhận đúng một logical attempt.
7. Xác nhận status sau submit.

Không dựa vào queue trong memory hoặc một `ScheduledFuture` đã đăng ký trước restart. Nếu đang dùng một broker delay queue, bài test phải xác nhận broker có persistence và recovery theo cấu hình hiện tại.

## 37. Integration test: hai worker đến hạn cùng lúc

Hai replica có thể chạy poller gần như đồng thời:

~~~text
Worker A -> find due notification N
Worker B -> find due notification N
~~~

Nếu code chỉ SELECT rồi SEND, cả hai có thể gửi. Test đúng cần:

- Dùng database thật với transaction isolation/row locking tương đương production.
- Cho hai worker chạy song song, mỗi worker có ID riêng.
- Có barrier/latch để chúng đến bước claim cùng lúc.
- Xác minh **một logical claim thắng**.
- SMTP fake nhận một submit attempt nếu worker không crash.
- Ghi kết quả kèm lease owner/generation.

Mockito repository không chứng minh `FOR UPDATE SKIP LOCKED` hoạt động; phải test với database engine đủ gần thực tế.

### Worker mất lease nhưng vẫn đang chạy

Một test nâng cao có thể làm worker A bị chậm trước send, để lease hết rồi worker B bắt đầu recovery. Tình huống phải được thiết kế sao cho không cả hai cùng gửi. Cơ chế heartbeat/fencing/unknown state cần chứng minh bằng integration test, không suy ra từ việc lock trong một transaction ngắn.

## 38. Integration test: hủy và đổi lịch

### Hủy trước khi đến hạn

~~~text
User creates AT=10:00
User cancels at 09:50
Worker runs at 10:00
Expected: no SMTP submission, state=CANCELLED
~~~

### Đổi lịch sang muộn hơn

~~~text
User creates AT=10:00
User updates AT=11:00 at 09:55
Worker runs at 10:00
Expected: no SMTP submission
Worker runs at 11:00
Expected: one SMTP submission
~~~

### Race giữa cancel và claim

Cho API DELETE và worker UPDATE claim cùng record trong test concurrency. Một operation thắng:

- Nếu DELETE thắng: status CANCELLED, SMTP không được gọi.
- Nếu claim thắng: DELETE không được báo “hủy chắc chắn”; trạng thái PROCESSING và kết quả sau đó được xử lý theo hợp đồng.

Trong trường hợp claim thắng, test không nên tự hứa message đã chắc chắn được gửi; chỉ xác nhận cancellation semantics trung thực và không có trạng thái không thể giải thích.

### Đổi lịch khi đang retry

Nếu user được phép chỉnh một email `RETRY_PENDING`, cần xác định đó là “đổi thời gian lần thử tiếp theo” hay “đổi ý nghĩa lịch gốc” và attempts có được reset không. Một API không rõ có thể khiến người dùng thấy “đổi lịch” nhưng hệ thống vẫn retry từ lỗi cũ.

## 39. Integration test SMTP: temporary, permanent và unknown

Một SMTP test server có thể trả:

| Kịch bản | Vị trí phản hồi | Kỳ vọng |
| --- | --- | --- |
| 250 sau DATA | Accepted | SUBMITTED; không retry |
| 421 khi bắt đầu session | Server temporary unavailable | Retry nếu safe và còn hạn |
| 451 ở RCPT TO | Temporary refusal | Backoff, không đánh dấu DELIVERED |
| 550 5.1.1 ở RCPT TO | Recipient invalid | Permanent/suppression theo policy |
| 535 tại AUTH | Account credentials invalid | Hold provider lane, không retry storm |
| Timeout trước MAIL FROM | Chưa submit body | Retry policy với backoff |
| 554 sau DATA | Explicit rejection | Điều tra content/policy, không retry mù |
| Connection lost sau DATA trước final reply | Outcome unknown | Reconcile, không tự tạo bản gửi mới |

Với integration test sử dụng `JavaMailSenderImpl` thật, có thể dùng scripted SMTP server lắng nghe loopback, kiểm soát EHLO/MAIL FROM/RCPT TO/DATA. Test của phần lịch cần phối hợp **trạng thái database** và **transport attempts**: một record đặt lịch vẫn phải phản ứng đúng khi SMTP trả các mã này.

### Vì sao timeout sau DATA quan trọng?

Giả sử:

~~~text
09:00:00 worker sends message body
09:00:01 relay receives last DATA marker
09:00:01 connection drops before final reply
09:00:02 JavaMailSender throws
~~~

Không biết relay đã nhận hay chưa. Nếu worker lập tức retry, cùng email có thể tới hai lần. Hệ thống nên lưu attempt ở trạng thái cần đối soát; `MailException` class đơn thuần thường không cung cấp toàn bộ phase semantics, nên có thể cần SMTP instrumentation hoặc provider status lookup.

## 40. Ma trận kiểm thử tổng thể

| ID | Kịch bản | Kỳ vọng chính |
| --- | --- | --- |
| S01 | NOW request hợp lệ | Persist PENDING với scheduledAt hiện tại |
| S02 | AT với UTC Instant | Lưu đúng instant |
| S03 | AT theo Asia/Ho_Chi_Minh | Quy đổi đúng local time và zone |
| S04 | AT thiếu zone khi dùng local time | Reject validation |
| S05 | DST gap | Reject hoặc quy tắc được phê duyệt, không chuyển âm thầm |
| S06 | DST overlap không chọn offset | Yêu cầu làm rõ |
| S07 | AT ở quá khứ | Reject hoặc explicit grace policy |
| S08 | AT quá xa so với max advance | Reject |
| S09 | Idempotency key trùng cùng payload | Trả record cũ, không tạo lần gửi mới |
| S10 | Key trùng nhưng payload khác | Conflict |
| S11 | Worker trước scheduledAt | Không gọi SMTP |
| S12 | Worker đúng scheduledAt | Có thể claim và submit |
| S13 | Worker chạy trễ nhưng còn grace | Send late, đo lateness |
| S14 | Worker chạy trễ quá expiry | EXPIRED/MISSED, không gửi |
| S15 | App restart trước AT | Lịch được giữ |
| S16 | Hai worker claim cùng job | Một logical owner |
| S17 | Lease hết khi worker còn send | Không tự tạo duplicate |
| S18 | SMTP accepted nhưng DB update fail | Reconcile/unknown, không resend mù |
| S19 | User cancel trước claim | CANCELLED, không gửi |
| S20 | Cancel đồng thời claim | Atomic transition, response trung thực |
| S21 | Reschedule tương lai | Giờ cũ không gửi, giờ mới gửi |
| S22 | PATCH với generation cũ | Conflict, không ghi đè |
| S23 | Recipient unsubscribe trước giờ gửi | SUPPRESSED, không gọi SMTP |
| S24 | OTP hết hạn | EXPIRED, không gửi |
| S25 | Attachment object bị xóa | HOLD/FAIL, không gửi thiếu tệp bắt buộc |
| S26 | Template version bị thiếu | Không tự gửi nội dung thay thế |
| S27 | SMTP 451 | RETRY_PENDING theo backoff |
| S28 | SMTP 550 permanent | Không retry |
| S29 | SMTP AUTH lỗi diện rộng | Account lane được hold, không storm |
| S30 | Mất final reply sau DATA | SUBMISSION_UNKNOWN |
| S31 | Provider A báo deferred sau accepted | Không tạo submit mới |
| S32 | Rate limit permit thiếu | Defer, không tăng physical attempts |
| S33 | Nhiều email marketing cùng hạn | Không làm đói OTP lane |
| S34 | Tenant không có quyền gửi | Reject trước enqueue/send |
| S35 | Crash giữa business transaction | Không commit outbox sai ranh giới |
| S36 | Cron recurring generator chạy lặp | Không tạo trùng occurrence |
| S37 | Timezone profile đổi | Hành vi theo policy đã định nghĩa |
| S38 | Notification đã SUBMITTED bị replay | Không gửi lại |
| S39 | Webhook provider đến trễ | Không làm status hồi quy hoặc resend |
| S40 | Quota provider cạn lúc AT | Defer đúng policy, đo lateness |

Mỗi test chỉ nên tuyên bố những điều mà nguồn giả lập hỗ trợ. Một fake SMTP trả final 250 chứng minh submission vào fake relay, **không chứng minh thư thật đi tới Inbox**.

## 41. Monitoring: độ trễ gửi ngay và gửi theo lịch

“Gửi ngay” và “gửi lúc người dùng yêu cầu” có SLO khác nhau:

- Với NOW, đo **queue wait time** và **time to submission** từ khi yêu cầu được commit.
- Với AT, đo **lateness** khi worker bắt đầu submit và khi SMTP accepted so với `scheduledAt`.
- Cả hai cần đo error rate, retry/unknown outcome, backlog và provider latency.

### Những công thức nên định nghĩa rõ

\[
\text{queueWait} =
\text{dispatchStartedAt} - \max(\text{createdAt},\text{scheduledAt})
\]

\[
\text{submissionLateness} =
\text{submittedAt} - \text{scheduledAt}
\]

\[
\text{timeToSubmitNow} =
\text{submittedAt} - \text{createdAt}
\]

Các công thức trên là ví dụ ở mức notification; với AT, `submissionLateness` dương khi đã gửi muộn, bằng 0 khi đúng thời điểm. Nếu không có `submittedAt` vì message thất bại thì **không đặt lateness bằng 0**; theo dõi riêng outcome và tuổi backlog.

### Metric gợi ý

| Metric | Ý nghĩa |
| --- | --- |
| `mail_schedule_requests_total` | NOW/AT requests được tiếp nhận |
| `mail_schedule_created_total` | Lịch được persist |
| `mail_schedule_validation_failures_total` | Input/timezone/permission invalid |
| `mail_schedule_due` | Số job đã đến hạn chưa xử lý |
| `mail_schedule_future` | Số job ở tương lai |
| `mail_schedule_pending_oldest_age_seconds` | Tuổi job quá hạn lâu nhất |
| `mail_dispatch_delay_seconds` | Độ trễ từ đến hạn đến bắt đầu dispatch |
| `mail_submission_lateness_seconds` | Độ lệch từ requestedAt/scheduledAt tới accepted submission |
| `mail_submission_attempts_total` | Physical SMTP/API attempts |
| `mail_submission_failures_total` | Lỗi theo provider/category/phase |
| `mail_schedule_retries_total` | Lần retry đã lên lịch |
| `mail_schedule_cancelled_total` | Số lịch được hủy |
| `mail_schedule_rescheduled_total` | Số lần đổi lịch |
| `mail_schedule_expired_total` | Số lịch không còn được phép gửi |
| `mail_submission_unknown_total` | Số attempt cần đối soát |
| `mail_schedule_claim_conflicts_total` | Cạnh tranh claim/fencing |
| `mail_rate_limit_deferred_total` | Đã defer do quota trước SMTP |
| `mail_worker_inflight` | Số SMTP submissions đang thực hiện |

Tên metric ở trên do ứng dụng tự triển khai bằng Micrometer/Actuator hoặc hệ thống quan sát khác; **Spring Mail không tự cung cấp đầy đủ các metric đó**.

### Label nên có và nên tránh

Label hữu hạn có thể gồm `mode=NOW|AT`, `category`, `providerKey`, `region`, `failureKind`. Không đưa full recipient email, notification UUID, subject, idempotency key hoặc token vào metric labels: vừa làm tăng cardinality vừa có thể lộ dữ liệu.

### Cảnh báo quan trọng

| Tín hiệu | Vấn đề khả dĩ | Hành động |
| --- | --- | --- |
| AT bị submit sớm | Clock skew, query lọc sai, stale schedule | Cô lập worker, kiểm tra thời gian/claim |
| NOW time-to-submit tăng | Queue nghẽn, provider chậm, limiter quá chặt | Kiểm tra throughput và backlog |
| AT lateness tăng | Poller không chạy, quá nhiều job cùng hạn | Kiểm tra scheduler và capacity |
| Oldest due age vượt SLO | Stuck jobs hoặc retry không tiến triển | Kiểm tra trạng thái, leases, errors |
| PROCESSING lease expired tăng | Worker crash/socket timeout | Không replay mù; reconcile |
| CANCELLED vẫn có SMTP attempt | Race hoặc worker thiếu recheck | Dừng route bị ảnh hưởng và điều tra |
| SUBMITTED bị gửi lần nữa | Idempotency/lease recovery lỗi | Cô lập resend, xem attempt ledger |
| Nhiều EXPIRED | Scheduling vượt khả năng xử lý hoặc TTL quá ngắn | Điều chỉnh SLA/quota/UX |
| Một template version lỗi hàng loạt | Render-at-send thiếu tài nguyên | Hold category, sửa template có kiểm soát |

### SLO minh họa

Một sản phẩm có thể đặt:

- 99% NOW transactional jobs bắt đầu submit trong một khoảng tối đa đã thống nhất.
- 99% AT jobs không bắt đầu trước `scheduledAt`.
- Một tỷ lệ cao AT jobs được submit trong grace period sau `scheduledAt`, trừ lỗi provider hoặc yêu cầu đã bị hủy.
- Không có job CANCELLED được tự động gửi mới.

Ngưỡng cụ thể phải dựa trên tải, chi phí, provider quota và mục tiêu nghiệp vụ. **Không chọn số phần trăm chỉ vì đẹp trên dashboard**, và không tính job CANCELLED/EXPIRED như một SMTP failure nếu chưa từng submit.

## 42. Logs và audit trail cho lịch gửi

Một email đặt lịch thay đổi qua nhiều hành động:

~~~text
2026-11-12T10:00:00Z CREATE AT=2026-11-20T02:00:00Z
2026-11-18T09:00:00Z RESCHEDULE to 2026-11-20T04:00:00Z
2026-11-20T04:00:03Z CLAIM by worker-2
2026-11-20T04:00:05Z SUBMISSION_ACCEPTED by smtp-primary
~~~

Một audit record nên có:

- `scheduleId`, tenant, actor ID/role.
- Event name: CREATED, RESCHEDULED, CANCELLED, CLAIMED, RETRIED, SUBMITTED, EXPIRED.
- Trạng thái và mốc thời gian cũ/mới.
- `generation`/version thay đổi.
- Provider key, attempt ID và lỗi đã chuẩn hóa nếu có.
- Timestamp của sự kiện theo UTC.
- Correlation business ID.

### Structured log minh họa

~~~json
{
  "event": "mail_schedule_rescheduled",
  "scheduleId": "a1a6d179-3cb2-47e7-bb2f-d34eebeb5ac1",
  "tenantKey": "tenant-01",
  "actorType": "USER",
  "fromScheduledAt": "2026-11-20T02:00:00Z",
  "toScheduledAt": "2026-11-20T04:00:00Z",
  "newGeneration": 3
}
~~~

Không log raw email body, OTP, password reset token, SMTP password, full recipient address hoặc dữ liệu đính kèm không cần thiết. Nếu cần forensic/audit chi tiết, dùng storage có phân quyền và retention.

## 43. Bảo mật API đặt lịch gửi

Nếu bất kỳ người dùng nào cũng có thể gọi endpoint schedule với recipient và template tùy ý, ứng dụng có nguy cơ trở thành **open relay ở tầng nghiệp vụ**, dù SMTP relay vẫn yêu cầu authentication.

### Các chốt kiểm tra

1. Xác thực người gọi, tenant và quyền thao tác.
2. Chỉ cho gửi tới recipient nằm trong phạm vi được phép.
3. Chỉ cho dùng sender identity/template mà người dùng có quyền.
4. Validate nội dung và attachment theo schema/size limit.
5. Kiểm tra consent và unsubscribe theo loại email.
6. Giới hạn số lịch gửi tương lai, thời gian đặt trước và tần suất.
7. Rate limit API `CREATE`, `PATCH` và `CANCEL`.
8. Không cho một tenant sửa schedule của tenant khác, kể cả đoán được UUID.
9. Audit hành động đặt lịch, sửa và hủy.
10. Kiểm tra lại suppression/expiry ngay trước SMTP.

### Authorization không chỉ ở controller

Worker chạy nền không có HTTP user context. Do đó record phải mang tenant/business scope đủ để service **xác minh tính hợp lệ** trước khi dispatch, không tin dữ liệu đã tồn tại trong database mãi mãi là được phép. Mọi API xem/hủy/sửa lịch đều phải query theo tenant/owner, không chỉ `WHERE id = ...`.

### Recipient data retention

Một lịch gửi sau 6 tháng có thể lưu email address, template data và attachment nhiều tháng. Cần retention/encryption/consent phù hợp; nếu người dùng yêu cầu xóa dữ liệu hoặc quyền nhận thay đổi, lịch chờ có thể phải bị hủy hoặc cập nhật theo policy.

## 44. Runbook: lịch đã đến hạn nhưng không gửi

Khi on-call nhận phản ánh “Tôi hẹn 9 giờ nhưng tới 9 giờ 30 vẫn chưa gửi”, thực hiện:

1. Xác định `scheduleId` hoặc business correlation ID.
2. Xem `scheduledAt` UTC và local time/zone đã được xác nhận lúc đặt lịch.
3. Kiểm tra status: PENDING, RETRY_PENDING, PROCESSING, SUBMITTED, EXPIRED, CANCELLED, UNKNOWN.
4. Nếu PENDING: xem `availableAt`, query index, polling scheduler và permissions.
5. Nếu RETRY_PENDING: xem lỗi SMTP và `nextAttemptAt`/retry budget.
6. Nếu PROCESSING: xem lease owner, lease age, worker heartbeat và socket timeout.
7. Nếu SUBMITTED: xem provider event/queue, không gửi lại chỉ vì chưa delivered.
8. Nếu EXPIRED: kiểm tra expiry/late-send policy; không reset tự động.
9. Nếu CANCELLED: xem actor và audit, không khởi chạy lại.
10. Nếu SUBMISSION_UNKNOWN: đối soát relay trước khi replay.
11. Đo backlog các job cùng category/tenant/provider.
12. Sửa nguyên nhân và khôi phục với rate limiter, không xả hết backlog cùng lúc.

### Đừng sửa bằng cách đặt mọi availableAt = NOW

Lệnh mass update như vậy có thể:

- Gửi email chưa đến hạn.
- Gửi message đã hết hiệu lực.
- Bỏ qua consent/suppression.
- Gây tải đột biến lên provider.
- Tạo duplicate với job đã được relay accepted.

Nếu phải replay sau incident, tạo một danh sách lọc theo **trạng thái và lý do đã biết**, có preview/dry-run, audit và phê duyệt phù hợp.

## 45. Runbook: phát hiện email được gửi sớm

Đây là lỗi đặc biệt quan trọng vì có thể vi phạm lựa chọn rõ ràng của người dùng.

1. Xác định requested local time, zone, UTC instant đã persist.
2. Đối chiếu event CREATE/RESCHEDULE/CLAIM/SUBMITTED.
3. Kiểm tra code chuyển `LocalDateTime` sang `Instant`, đặc biệt có dùng `systemDefault()` không.
4. Kiểm tra clock skew giữa DB và workers.
5. Kiểm tra stale cache/job snapshot sau PATCH.
6. Xem có TaskScheduler in-memory vẫn chứa future cũ sau reschedule không.
7. Kiểm tra query thiếu `scheduled_at <= now`.
8. Xem có đường gửi trực tiếp bypass outbox không.
9. Cô lập đường thực thi sai nếu còn tác động; không tự gửi “bản sửa” để bù.
10. Bổ sung test no-early-send và race cancel/reschedule.

Khi code dùng UTC đúng, lỗi này vẫn có thể đến từ việc **một nhánh bypass worker** gọi trực tiếp `mailSender.send()` mà không kiểm tra lịch.

## 46. Runbook: gửi trùng sau restart

Một incident điển hình:

~~~text
09:00:00 Worker A sends to SMTP
09:00:01 Relay replies 250
09:00:02 Worker A crashes before DB update
09:02:00 Lease expires
09:02:01 Worker B retries same record
09:02:02 Recipient may receive a duplicate
~~~

Hướng xử lý:

1. Tạm dừng re-dispatch tự động cho cohort nghi ngờ.
2. Lưu attempt/provider IDs và timestamp.
3. Đối soát provider logs/events hoặc API khi có.
4. Không lấy việc DB còn PROCESSING làm bằng chứng chắc chắn chưa gửi.
5. Cập nhật record bằng trạng thái phù hợp theo bằng chứng.
6. Nếu buộc resend khi outcome chưa rõ, dùng quyết định nghiệp vụ có audit.
7. Xem lease, heartbeat, fencing và transaction boundary của worker.
8. Kiểm tra có retry lồng trong adapter/broker khiến attempts tăng không.
9. Bổ sung integration test crash-window.

**Không cam kết exactly-once SMTP** chỉ nhờ dùng database locking. Có thể đạt idempotent enqueue/claim, nhưng external submission vẫn có cửa sổ trạng thái không xác định.

## 47. Runbook: backlog lớn sau downtime

Giả sử ứng dụng ngừng 2 giờ và hàng chục nghìn lịch gửi đã đến hạn. Khi khởi động lại:

- Không gửi tất cả trong một giây chỉ vì `scheduledAt <= now`.
- Ưu tiên loại email cần thiết, áp dụng fairness và quota.
- Loại `EXPIRED` theo deadline trước khi gọi SMTP.
- Không gửi marketing bị unsubscribe trong lúc downtime.
- Không render mọi attachment cùng lúc làm đầy memory/disk.
- Giữ `scheduledAt` gốc để đo mức trễ.
- Dùng batch/claim có giới hạn, rate limiter phân tán.
- Quan sát `pendingOldestAge`, SMTP response và completion throughput.

### Catch-up policy rõ ràng

| Loại email | Khi đã trễ 2 giờ |
| --- | --- |
| OTP/reset token ngắn hạn | Thường EXPIRED, không gửi mã cũ |
| Nhắc trước lịch hẹn | Có thể bỏ nếu thời điểm hẹn đã qua |
| Hóa đơn giao dịch | Có thể gửi trễ nếu còn hợp lệ |
| Báo cáo định kỳ | Theo chính sách skip/catch-up/latest |
| Chiến dịch marketing | Kiểm tra campaign window và consent |

Không có một câu trả lời chung. Business rule phải được định nghĩa trước khi triển khai hệ thống scheduling.

## 48. Các lỗi thường gặp khi lập lịch email

### 48.1. Dùng `Thread.sleep()` để chờ giờ gửi

Giữ thread, không bền vững qua restart và khó hủy. Lưu lịch trong database, dùng poller/queue.

### 48.2. Tạo một `ScheduledFuture` cho mỗi email và không lưu DB

Process restart làm mất lịch; multi-instance khó đồng bộ. TaskScheduler có thể dùng như bộ kích hoạt, không nên là nguồn sự thật duy nhất cho email quan trọng.

### 48.3. Dùng cron cho mỗi người dùng

Cron lặp không biểu diễn tốt một lần gửi bất kỳ theo từng `Instant`. Dùng records one-shot và dispatcher.

### 48.4. Lưu `LocalDateTime` mà không có timezone

Người dùng ở nhiều vùng hoặc server thay timezone sẽ làm thời điểm bị hiểu sai. Lưu `Instant` và zone metadata.

### 48.5. Không xử lý DST gap/overlap

Giờ địa phương có thể không tồn tại hoặc trùng. Xác định policy/offset thay vì âm thầm chọn một mốc.

### 48.6. Chấp nhận lịch trong quá khứ rồi gửi ngay

Có thể gây gửi ngoài ý muốn. Trả validation error hoặc dùng explicit grace policy.

### 48.7. Gọi SMTP trực tiếp trong transaction đặt hàng

Network timeout kéo dài transaction; rollback không thu hồi SMTP đã accepted. Dùng transactional outbox.

### 48.8. Hai replica SELECT rồi cùng SEND

Không có atomic claim sẽ gây duplicate. Dùng transaction/lease/fencing.

### 48.9. Hết lease là tự gửi lại

Worker có thể đã submit thành công nhưng chưa ghi DB. Xử lý unknown outcome, không replay mù.

### 48.10. Hủy một ScheduledFuture rồi báo đã hủy toàn hệ thống

Không đủ với distributed/durable scheduler. Hủy phải cập nhật trạng thái nguồn sự thật và xét race.

### 48.11. Đổi lịch nhưng để task cũ vẫn chạy

Trong in-memory scheduler, phải hủy future cũ; với outbox, claim cần kiểm tra version/scheduledAt mới. Một nguồn lịch duy nhất giảm lỗi.

### 48.12. Không revalidate consent lúc gửi

Người nhận có thể unsubscribe sau khi đặt lịch. Không dùng quyết định consent cũ để bypass.

### 48.13. Dùng `send()` thành công để hiển thị DELIVERED

Chỉ phản ánh SMTP submission; downstream cần provider event.

### 48.14. Retry mọi `MailException` theo cùng cách

SMTP AUTH, permanent RCPT 550, temporary 451 và unknown after DATA cần xử lý khác nhau.

### 48.15. Gửi OTP đã hết hạn do backlog

Gây trải nghiệm sai và tăng nguy cơ rối loạn xác thực. Cần expiry/retry deadline.

### 48.16. Chỉ kiểm tra kích thước attachment khi tạo lịch

File có thể thay đổi hoặc hết retention trước ngày gửi. Dùng immutable storage/version và validate lúc dispatch.

### 48.17. Không có idempotency key khi tạo NOW

HTTP client retry do timeout có thể tạo nhiều lịch và nhiều email.

### 48.18. Giới hạn concurrency chỉ trong từng pod

Nhiều pod cộng lại có thể vượt provider quota. Dùng limiter có phạm vi đúng.

### 48.19. Khi queue chậm thì tự gửi sớm hơn scheduledAt

Vi phạm điều kiện người dùng đã chọn. Chấp nhận độ trễ, mở rộng capacity hoặc thương lượng SLA khác.

### 48.20. Không đo lateness hoặc backlog

Chỉ đo số email `SUBMITTED` không cho biết người dùng có nhận đúng thời điểm hay không. Đo cả queue delay, expiry, retry và outcome.

## 49. Checklist triển khai tính năng gửi ngay và gửi theo lịch

### Thời gian và API

- [ ] Hợp đồng API phân biệt NOW và AT.
- [ ] AT chỉ nhận `Instant` đã xác định hoặc local date-time kèm `zoneId` rõ.
- [ ] Không dùng timezone mặc định của server để đoán giờ người dùng.
- [ ] Có chính sách với DST gap/overlap.
- [ ] Có validation lịch quá khứ, quá xa và trễ tối đa.
- [ ] Có Clock injectable cho logic tính thời gian.
- [ ] Response chỉ xác nhận yêu cầu đã lưu, không tự ghi DELIVERED.
- [ ] Có API xem trạng thái, hủy, đổi lịch theo quyền.
- [ ] Đổi lịch/hủy có kiểm soát race qua status và generation/version.

### Persistence và dispatcher

- [ ] Yêu cầu gửi được persist bền vững, không chỉ ở bộ nhớ JVM.
- [ ] NOW và AT dùng chung pipeline hoặc một policy nhất quán.
- [ ] `scheduledAt` giữ nghĩa nghiệp vụ; `availableAt` giữ nghĩa thời gian retry.
- [ ] Outbox được commit cùng business transaction khi cần.
- [ ] Có unique idempotency key trong phạm vi tenant/nghiệp vụ.
- [ ] Có index cho due jobs và query không gửi trước giờ.
- [ ] Có atomic claim/lease giữa nhiều worker.
- [ ] Có fencing/optimistic update cho kết quả của worker.
- [ ] Không giữ transaction DB mở trong SMTP send.
- [ ] Có thiết kế khi worker chết sau send nhưng trước DB update.
- [ ] Có cơ chế reconciliation cho `SUBMISSION_UNKNOWN`.
- [ ] Có kiểm tra lại status/time ngay trước gửi.

### Nội dung và chính sách gửi

- [ ] Recipient, consent, suppression và quyền gửi được kiểm tra ở thời điểm dispatch.
- [ ] Token/OTP có expiry phù hợp với lịch.
- [ ] Template và payload version được quản lý.
- [ ] Attachment tồn tại, đúng phiên bản và đủ retention tới thời điểm gửi.
- [ ] Nội dung không bị thay đổi trái phép khi template/data đổi.
- [ ] Hủy hoặc hết hạn không kích hoạt SMTP attempt.
- [ ] Hệ thống không gửi lại thư đã SUBMITTED vì thiếu delivered event.
- [ ] Có phân loại SMTP temporary/permanent/AUTH/unknown.

### Công suất và vận hành

- [ ] Scheduler/poller chạy được sau restart.
- [ ] Batch size và worker concurrency được giới hạn.
- [ ] Rate limiter áp dụng đúng cấp provider/account/cluster.
- [ ] Có backoff, jitter và retry budget.
- [ ] Có ưu tiên và fairness theo category/tenant.
- [ ] Có grace/catch-up/skip policy cho lịch bị bỏ lỡ.
- [ ] Có metric cho queue wait, submit delay, lateness, overdue count.
- [ ] Có alert khi gửi sớm, mất lịch, quá hạn và duplicate suspected.
- [ ] Có audit CREATE/RESCHEDULE/CANCEL/SUBMIT.
- [ ] Có test thời gian bằng fake Clock, test DB claim và SMTP fake.
- [ ] Có runbook phục hồi backlog mà không gửi quá hạn hoặc tạo duplicate.

Checklist trên là hướng triển khai, không phải bằng chứng hệ thống đã chạy đúng. Những bất biến quan trọng như **không gửi sớm**, **không gửi job đã hủy**, **không tạo duplicate khi hai worker claim cùng một record** và **không retry mù sau SMTP outcome không xác định** cần được kiểm thử bằng môi trường tương ứng.

## 50. Quy trình xây dựng từ phiên bản đơn giản tới production

Một nhóm có thể triển khai tuần tự thay vì đưa toàn bộ distributed scheduler vào ứng dụng từ ngày đầu.

### Giai đoạn 1 — Lưu yêu cầu rõ ràng

1. Định nghĩa NOW/AT và validation timezone.
2. Tạo `mail_schedule` với `scheduledAt`, `status`, idempotency key.
3. Dùng `Clock` injectable.
4. Thêm API tạo/xem trạng thái/hủy trước dispatch.
5. Xác định policy expiry và người được phép gửi.

Ở giai đoạn này, chưa cần thay `JavaMailSender`; nó vẫn là transport adapter. Thay đổi chính là **cách ứng dụng tạo và lưu yêu cầu**.

### Giai đoạn 2 — Một worker bền vững

1. Thêm poller với `@Scheduled`.
2. Chọn job đến hạn theo `scheduledAt`.
3. Claim bằng transaction và lưu trạng thái.
4. Dispatch ngoài transaction.
5. Lưu accepted/failure/unknown outcome.
6. Retry bằng `availableAt` và giới hạn số attempts.
7. Test restart, timeout và gửi không sớm.

Đối với môi trường chỉ chạy một worker, claim/lease vẫn hữu ích để chuẩn bị scale và phục hồi sau crash.

### Giai đoạn 3 — Nhiều replica và công suất lớn

1. Claim atomically và fencing.
2. Distributed rate limiter hoặc quota partition.
3. Priority/fairness giữa các loại email.
4. Attempt ledger/reconciliation.
5. Cơ chế đo queue lateness và SLA.
6. Runbook khi backlog/circuit breaker/provider outage.
7. Thử các race cancellation/restart, clock skew và worker lease expiry.

### Giai đoạn 4 — Quy tắc lịch nâng cao

Nếu có recurring, timezone recipient, lịch nghỉ hoặc reschedule theo sự kiện nguồn:

- Lưu recurring rule và tạo occurrences bền vững.
- Idempotency key cho từng occurrence.
- Có DST policy.
- Có quy tắc bỏ qua các occurrences đã quá hạn.
- Có phiên bản rule và audit khi user sửa.

Không cần Cron/Quartz cho mọi bài toán: lựa chọn dựa trên tính phức tạp và yêu cầu độ chính xác, không dựa vào việc “có thư viện lịch nghe có vẻ mạnh”.

## 51. Ví dụ đầy đủ theo thời gian: gửi ngay sau thanh toán

Giả sử một dịch vụ nhận sự kiện thanh toán `payment-184` lúc 09:00:00.

~~~text
09:00:00.000  payment transaction begins
09:00:00.030  payment marked PAID
09:00:00.035  mail_schedule inserted:
                mode=NOW
                scheduledAt=09:00:00.035
                status=PENDING
                idempotencyKey=payment-receipt-184
09:00:00.040  COMMIT
09:00:00.100  API returns success
09:00:00.950  worker polls due jobs
09:00:00.965  one worker claims record
09:00:01.010  SMTP submit starts
09:00:01.300  relay replies 250
09:00:01.340  status=SUBMITTED
~~~

Điểm quan trọng:

- Không gửi trước khi transaction được commit.
- Client retry request với cùng payment ID không tạo lịch thứ hai.
- Nếu SMTP outage, giao dịch thanh toán vẫn tồn tại và mail outbox giữ yêu cầu.
- API success về thanh toán không được diễn giải là Inbox delivery.
- Nếu relay accepted nhưng DB update thất bại, cần reconciliation/unknown state.

### Trải nghiệm người dùng

UI có thể hiển thị:

~~~text
Thanh toán thành công.
Hệ thống đang gửi biên nhận tới email đã xác minh.
~~~

Sau khi nhận kết quả provider tương ứng, UI/cổng hỗ trợ có thể cập nhật trạng thái. Không nên nói “Đã giao email” chỉ từ việc payment transaction commit.

## 52. Ví dụ đầy đủ theo thời gian: gửi nhắc hẹn

Người dùng muốn gửi email vào 09:00 ngày 20/11/2026 tại Việt Nam:

~~~text
Request created: 2026-11-12
Local request:   2026-11-20 09:00
Zone:            Asia/Ho_Chi_Minh
scheduledAt:     2026-11-20T02:00:00Z
mode:            AT
status:          PENDING
~~~

### Trường hợp bình thường

~~~text
20/11 08:59 local -> polling sees scheduledAt in future, no send
20/11 09:00 local -> record becomes due, worker claims
20/11 09:00+      -> SMTP submits, status SUBMITTED
~~~

### Người dùng đổi sang 11:00

~~~text
18/11 16:00 local -> PATCH new scheduledAt=2026-11-20T04:00:00Z
                     version increments
20/11 09:00 local -> no SMTP attempt
20/11 11:00 local -> dispatch if still eligible
~~~

### Người dùng hủy

~~~text
19/11 -> DELETE schedule while PENDING
20/11 -> worker does not claim CANCELLED record
~~~

### Ứng dụng bị downtime đến 11:30

Trường hợp này phụ thuộc **grace period**:

- Nếu lời nhắc chỉ còn hữu ích trước cuộc hẹn lúc 10:00, record nên được EXPIRED/MISSED.
- Nếu đây là một thông báo không có deadline nghiêm ngặt, có thể gửi muộn và ghi lateness.
- Không tự gửi “đúng 11:30” rồi che lịch gốc 09:00.

Các trường hợp trên sử dụng cùng `mail_schedule` và cùng worker; sự khác nhau là **trạng thái và quy tắc nghiệp vụ**, không phải phải xây một SMTP sender khác.

## 53. Câu hỏi tự kiểm tra

**1. `JavaMailSender.send()` có tự hỗ trợ gửi vào ngày mai không?**

Không. Nó submit email khi được gọi. Thời điểm gọi cần do scheduler/queue/outbox của ứng dụng kiểm soát.

**2. Gửi ngay có nhất thiết gọi SMTP trong HTTP request không?**

Không. Có thể lưu outbox với `scheduledAt = now`, trả trạng thái tiếp nhận và worker gửi sớm theo SLA.

**3. Dùng `@Scheduled` có làm từng lịch người dùng được lưu bền vững không?**

Không. `@Scheduled` kích hoạt một phương thức theo thời gian; job dữ liệu phải được lưu ở nơi bền vững nếu cần phục hồi.

**4. `TaskScheduler.schedule(Runnable, Instant)` có đảm bảo lịch vẫn chạy sau JVM restart không?**

Không nếu chỉ dùng scheduler trong memory. Cần persistence/rehydration hoặc một scheduler có durable job store.

**5. Vì sao nên lưu `Instant`?**

Nó biểu diễn một thời điểm UTC tuyệt đối, tránh việc server ở timezone khác hiểu sai lúc dispatch.

**6. Vì sao vẫn lưu `zoneId`?**

Để hiển thị đúng lịch địa phương và giải thích/chỉnh các quy tắc thời gian, đặc biệt với lịch lặp hoặc thay đổi timezone.

**7. Nếu API nhận `2026-11-20T09:00:00` mà không có zone, server nên làm gì?**

Không tự đoán timezone. Yêu cầu thêm `zoneId`/offset hoặc dùng hợp đồng API quy định rõ.

**8. DST gap là gì?**

Là local time không tồn tại khi đồng hồ dịch lên. Hệ thống cần reject hoặc dùng policy được phê duyệt, không lặng lẽ đổi giờ.

**9. DST overlap là gì?**

Là local time xuất hiện hai lần với hai UTC offset. Nếu một lần gửi cần chính xác, yêu cầu chọn offset hoặc quy tắc rõ.

**10. Khi người dùng chọn NOW, nên dùng thời gian của client hay server?**

Thường dùng `Clock` của hệ thống khi ghi nhận yêu cầu, không tin một timestamp client tùy ý để quyết định giờ gửi.

**11. Vì sao cần `scheduledAt` và `availableAt` riêng?**

`scheduledAt` giữ lịch người dùng yêu cầu; `availableAt` cho phép trì hoãn theo retry, quota hoặc backoff mà không thay đổi lịch gốc.

**12. Khi SMTP trả 451 đúng giờ đã hẹn, có được đánh dấu SUBMITTED không?**

Không. Đó là lỗi tạm thời của lần submit; có thể retry theo backoff khi còn hạn, còn `scheduledAt` gốc được giữ.

**13. Một worker có được gửi trước 09:00 để kịp giao vào Inbox lúc 09:00 không?**

Không nếu hợp đồng yêu cầu không submit trước 09:00. SMTP cũng không bảo đảm khi nào Inbox nhận.

**14. Vì sao dùng transactional outbox trong luồng thanh toán?**

Để ghi yêu cầu gửi trong cùng transaction nghiệp vụ và chỉ gọi SMTP sau commit, tránh mất yêu cầu hoặc rollback không đồng nhất.

**15. HTTP trả 202 Accepted có nghĩa email đã giao không?**

Không. Nó thường chỉ cho biết yêu cầu gửi đã được tiếp nhận/lưu, tùy API contract.

**16. Hai worker cùng SELECT một record đến hạn có thể xảy ra gì?**

Cả hai có thể gọi SMTP. Cần atomic claim, lease và xử lý trạng thái có fencing.

**17. `FOR UPDATE SKIP LOCKED` có bảo đảm exactly-once SMTP không?**

Không. Nó giúp claim atomically trong database, nhưng không loại cửa sổ worker đã send rồi crash trước DB update.

**18. Có được hủy job đã PROCESSING và hứa email sẽ không đến không?**

Không nếu external send đã có thể bắt đầu. Hủy chắc chắn chỉ trong những trạng thái và ranh giới được hệ thống bảo đảm.

**19. Khi PATCH đổi lịch, vì sao cần generation?**

Để tránh ghi đè lịch mới bằng request cũ và hỗ trợ kiểm soát race giữa user update và worker.

**20. Khi recipient unsubscribe sau lúc đặt lịch, phải làm gì?**

Kiểm tra lại ngay trước dispatch; nếu không được phép nhận, chuyển SUPPRESSED và không gọi SMTP.

**21. Lịch OTP hết hạn do downtime có nên gửi bù không?**

Thường không. Phải theo policy/expiry của token, có thể yêu cầu một OTP mới.

**22. Nếu worker bị trễ 2 phút, nên sửa scheduledAt thành thời điểm thực gửi không?**

Không. Lưu `submittedAt` riêng và đo lateness; lịch gốc là bằng chứng lựa chọn của người dùng.

**23. Email gửi thành công qua SMTP có phải đã vào Inbox không?**

Không. Submission accepted và delivery là các mốc khác nhau; có thể có deferred/bounced downstream.

**24. Nếu provider báo DEFERRED, có nên tạo một SMTP submission mới không?**

Không tự động nếu provider đã accepted và đang retry giao downstream. Có thể gây gửi trùng.

**25. Vì sao cần lưu template version hoặc snapshot?**

Để nội dung lúc gửi vẫn đúng ý nghĩa được người dùng/nghiệp vụ phê duyệt, không vô tình thay đổi vì template hoặc data đã đổi.

**26. Có thể dùng file trong thư mục tạm cho email hẹn sau một tháng không?**

Không nên. File có thể bị xóa hoặc đổi; dùng immutable storage với retention phù hợp.

**27. Nếu rate limiter không cấp permit thì attempts có tăng không?**

Không nên tăng physical SMTP attempts khi chưa gọi transport; lưu defer reason và thời điểm thử lại.

**28. Lịch lặp hằng tuần khác AT một lần thế nào?**

Lịch lặp là quy tắc sinh nhiều occurrences; mỗi lần gửi có một mốc và idempotency key. AT một lần chỉ có một occurrence.

**29. Làm sao kiểm thử lịch mà không chờ nhiều ngày?**

Dùng `Clock.fixed`/mutable clock, test DB claim, fake SMTP và điều khiển thời gian trong test.

**30. Khi nhiều email marketing đến hạn, làm sao tránh ảnh hưởng OTP?**

Áp dụng priority tiers, reserved throughput, fairness, rate limiter và giới hạn concurrency trên cấp phù hợp.

## Kết luận

**Gửi ngay và gửi vào thời điểm được yêu cầu là bài toán điều phối trước khi gọi Spring Mail, không phải hai kiểu SMTP message khác nhau.** `JavaMailSender` gửi khi được gọi; ứng dụng phải quyết định **khi nào được gọi**, dựa trên `scheduledAt`, timezone, trạng thái và quyền gửi. Với NOW, nên ghi nhận yêu cầu bền vững và dispatch sớm sau commit. Với AT, phải xác định một `Instant` hợp lệ từ lựa chọn của người dùng, không gửi trước giờ, giữ lịch qua restart và công khai chính sách gửi muộn/hết hạn.

Một thiết kế đáng tin cậy sử dụng transactional outbox, `@Scheduled` làm bộ kích hoạt poll job đến hạn, atomic claim/lease/fencing cho nhiều worker, retry có backoff và `availableAt` riêng, cùng API hủy/đổi lịch có version. Trước mỗi lần submit cần kiểm tra lại consent, recipient, token expiry, template/attachment và quota. Khi SMTP đã accepted, không coi “chưa delivered” là lý do gửi lại; khi mất final reply, phải xử lý `SUBMISSION_UNKNOWN` và nguy cơ duplicate. Cuối cùng, dùng `Clock` trong kiểm thử, đo queue delay/submission lateness và có runbook cho outage, backlog và race condition.

**Một hệ thống lập lịch email tốt không chỉ kích hoạt lời gọi `send()` đúng lúc, mà còn giữ đúng lựa chọn thời gian của người dùng, không làm mất yêu cầu, không gửi khi đã hủy/hết hạn và không tạo thư trùng trong quá trình phục hồi.**
