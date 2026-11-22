# Múi giờ của lịch gửi

Một ứng dụng dùng **Spring Framework Mail** có thể gửi email xác nhận đơn hàng ngay lập tức, nhưng cũng có thể phải gửi báo cáo lúc **09:00 sáng theo giờ người dùng**, nhắc lịch trước một cuộc họp hoặc triển khai chiến dịch tại nhiều quốc gia. Khi đó, bài toán không còn chỉ là gọi `JavaMailSender.send(...)`. Cần định nghĩa **09:00 là ở múi giờ nào**, lưu thời điểm gửi theo cách không bị thay đổi bởi timezone của máy chủ, xử lý những ngày có **Daylight Saving Time (DST)**, khôi phục lịch sau khi ứng dụng restart và tránh gửi lặp khi nhiều worker cùng chạy.

Ví dụ, “09:00 ngày 01/12/2026” không đủ để xác định một thời điểm trên dòng thời gian toàn cầu. Cùng chuỗi này có thể là:

- 09:00 tại **Asia/Ho_Chi_Minh**: 02:00 UTC.
- 09:00 tại **Europe/Berlin** vào mùa đông: 08:00 UTC.
- 09:00 tại **America/New_York** vào mùa đông: 14:00 UTC.

Một hệ thống chỉ lưu `LocalDateTime` rồi giả định timezone mặc định của server có thể gửi sai hàng giờ. Một hệ thống chỉ lưu UTC có thể tính đúng **lần gửi cụ thể**, nhưng vẫn thiếu thông tin để tiếp tục một lịch **lặp vào 09:00 theo giờ địa phương** khi offset thay đổi theo mùa.

Bài học này trình bày mô hình thời gian của Java (`java.time`), sự khác biệt giữa **instant, offset và time zone**, cách phân giải thời gian local có DST, thiết kế dữ liệu lịch gửi cho Spring Mail, `@Scheduled`/cron, transactional outbox, retry/expiration, kiểm thử có đồng hồ giả lập và vận hành trên nhiều khu vực.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích `Instant`, `LocalDateTime`, `OffsetDateTime`, `ZonedDateTime`, `ZoneId` và `Clock`.
2. Phân biệt **mốc thời gian tuyệt đối** với **giờ địa phương theo quy tắc múi giờ**.
3. Lưu một lịch gửi một lần mà không phụ thuộc timezone của JVM hoặc database session.
4. Lưu lịch gửi lặp với **IANA time-zone ID** thay vì chỉ lưu offset hiện tại.
5. Xác định cách xử lý giờ địa phương **không tồn tại** hoặc **xuất hiện hai lần** khi DST chuyển đổi.
6. Cấu hình `@Scheduled(cron = ..., zone = ...)` và biết giới hạn của cron trong hệ thống nhiều replicas.
7. Tính các lần gửi tiếp theo dựa trên lịch địa phương theo timezone của người dùng.
8. Dùng một **due-job poller** để tìm job `send_at <= now` rồi gửi bằng `JavaMailSender`.
9. Thiết kế các trạng thái `PENDING`, `SENDING`, `SMTP_ACCEPTED`, `RETRY_WAIT`, `CANCELLED` và `UNKNOWN`.
10. Phân biệt **thời điểm được phép bắt đầu submission** với **thời điểm email được provider giao đến người nhận**.
11. Kiểm thử các biên DST, lệch đồng hồ, chênh timezone và restart bằng `Clock.fixed(...)`.
12. Xử lý cập nhật timezone, chính sách giờ yên tĩnh, deadline, hủy lịch và thay đổi quy định múi giờ.

## 2. Múi giờ ảnh hưởng tới những phần nào của quy trình gửi?

```text
Người dùng:
"Ngày 01/12/2026 lúc 09:00 ở Việt Nam"
                    |
                    v
Schedule API:
localDateTime + ZoneId + policy
                    |
                    v
Resolve to Instant:
2026-12-01T02:00:00Z
                    |
                    v
Database scheduled_email:
due_at (UTC instant)
zone_id + local input (giữ ý định)
                    |
                    v
Due-job dispatcher:
WHERE due_at <= now
                    |
                    v
Claim job + worker
                    |
                    v
JavaMailSender / SMTP relay
                    |
                    v
SMTP submission accepted
                    |
                    v
Provider delivery (có thể muộn)
```

Có **ba lớp thời gian** cần giữ riêng:

- **Ý định của người dùng:** “09:00 sáng ở Thành phố Hồ Chí Minh”, “mỗi thứ Hai lúc 09:00 theo giờ Berlin”.
- **Thời điểm kỹ thuật để thực thi:** một `Instant` cụ thể, ví dụ `2026-12-01T02:00:00Z`.
- **Thời điểm thực tế xảy ra sự kiện:** worker bắt đầu gửi, SMTP accepted, provider delivered; các mốc này có thể trễ so với lịch.

Một lịch gửi chính xác phải lưu được ý định và thời điểm thực thi, đồng thời ghi lại khi nào submission thật sự diễn ra. Không được coi “email được xếp lịch lúc 09:00” là bảo đảm người nhận nhận đúng 09:00.

## 3. Nền tảng java.time: chọn đúng kiểu

Java 8+ cung cấp API `java.time` để xử lý ngày giờ. Dùng các kiểu rõ nghĩa sẽ giảm lỗi chuyển múi giờ.

| Kiểu | Chứa gì? | Có xác định một instant? | Dùng trong lịch gửi |
|---|---|---|---|
| `Instant` | Mốc tuyệt đối trên UTC timeline | Có | `sendAt`, `createdAt`, `claimedAt`, `nextAttemptAt` |
| `LocalDate` | Ngày theo lịch, không có giờ/zone | Không | Ngày business hoặc ngày bắt đầu lịch lặp |
| `LocalTime` | Giờ-phút-giây, không có ngày/zone | Không | “09:00 hằng ngày” |
| `LocalDateTime` | Ngày và giờ local, **không có zone/offset** | Không | Ý định “01/12/2026 09:00” trước khi resolve |
| `ZoneOffset` | Chênh lệch UTC, ví dụ `+07:00` | Đủ cùng local datetime | Một offset tại một thời điểm; không chứa quy tắc DST tương lai |
| `OffsetDateTime` | Local datetime + offset | Có | API nhận một mốc cụ thể kèm offset |
| `ZoneId` | Vùng quy tắc như `Europe/Berlin` | Không, nếu đứng một mình | Giữ timezone của người dùng/lịch lặp |
| `ZonedDateTime` | Local datetime + ZoneId + offset đã chọn | Có | Hiển thị và tính toán một lần gửi trong zone |
| `Clock` | Nguồn thời gian có thể thay thế | Tùy `instant()` | Test due time, deadline, retry và scheduler |

### 3.1. Instant là mốc thống nhất

```java
import java.time.Instant;

Instant dueAt = Instant.parse("2026-12-01T02:00:00Z");
```

Một `Instant` không có “giờ Berlin” hay “giờ Sài Gòn” bên trong. Nó biểu diễn cùng một mốc cho tất cả hệ thống.

### 3.2. LocalDateTime không hàm ý UTC

```java
import java.time.LocalDateTime;

LocalDateTime requested =
    LocalDateTime.of(2026, 12, 1, 9, 0);
```

Giá trị này **chưa đủ để gửi**. Nó không tự biết 09:00 là ở Việt Nam, Đức hay Mỹ. Đừng gọi `toInstant(ZoneOffset.UTC)` cho mọi `LocalDateTime` nếu người dùng không thực sự chọn UTC.

### 3.3. ZoneId giữ quy tắc thời gian

```java
import java.time.ZoneId;

ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
ZoneId berlin = ZoneId.of("Europe/Berlin");
ZoneId newYork = ZoneId.of("America/New_York");
```

Các ID này lấy từ **IANA Time Zone Database (tzdb)** mà Java runtime sử dụng. Một ZoneId mang các quy tắc về offset và các đợt chuyển DST tại những thời điểm khác nhau.

### 3.4. Offset không thay thế ZoneId

`Europe/Berlin` có thể dùng:
- `+01:00` vào mùa đông;
- `+02:00` vào mùa hè.

Nếu chỉ lưu `+01:00` cho lịch “09:00 giờ Berlin mỗi ngày”, đến mùa hè hệ thống sẽ vẫn gửi theo `+01:00` và kết quả không còn là 09:00 Berlin.

**Dùng offset cho một mốc đã xác định; dùng ZoneId cho ý định lịch địa phương cần sống qua thay đổi quy tắc.**

## 4. Ví dụ chuyển đổi một lịch gửi ở Việt Nam

Người dùng chọn “01/12/2026, 09:00” ở `Asia/Ho_Chi_Minh`.

```java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

LocalDateTime local = LocalDateTime.of(
    2026, 12, 1, 9, 0
);

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime zoned = local.atZone(zone);
Instant sendAt = zoned.toInstant();

System.out.println(sendAt);
// 2026-12-01T02:00:00Z
```

Việt Nam hiện dùng UTC+07:00 quanh năm và không áp dụng DST, nên trường hợp hiện hành tương đối đơn giản. Tuy vậy, vẫn nên lưu `Asia/Ho_Chi_Minh` thay vì giả định mọi lịch luôn có `+07:00`: tên vùng diễn đạt ý định người dùng và hỗ trợ quy tắc lịch sử hoặc thay đổi pháp lý trong tương lai.

### 4.1. Cùng một instant, nhiều cách hiển thị

```java
Instant sendAt = Instant.parse(
    "2026-12-01T02:00:00Z"
);

System.out.println(
    sendAt.atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
);
// 2026-12-01T09:00+07:00[Asia/Ho_Chi_Minh]

System.out.println(
    sendAt.atZone(ZoneId.of("Europe/Berlin"))
);
// 2026-12-01T03:00+01:00[Europe/Berlin]
```

Cả hai biểu diễn là **cùng một thời điểm**. Nếu giao diện hiển thị theo timezone người nhận mà không ghi rõ zone, người dùng có thể tưởng lịch bị thay đổi.

### 4.2. Nguyên tắc cho database

Để thực thi một lần gửi, hãy lưu một mốc tuyệt đối như `Instant`. Để giải thích hoặc cập nhật lịch, cũng lưu:
- `local_send_time`;
- `zone_id`;
- chính sách xử lý DST;
- thông tin người tạo và loại lịch.

Đừng chỉ lưu chuỗi “09:00” hoặc chỉ lưu offset hiện tại.

## 5. Múi giờ ở các lớp: máy chủ, JVM, database, trình duyệt

Một hệ thống có thể đồng thời có:

```text
Browser: America/New_York
API server JVM: UTC
Worker JVM: Asia/Ho_Chi_Minh
Database connection session: UTC
SMTP relay: Europe/Berlin
Recipient: Asia/Tokyo
```

Các múi giờ này **không bắt buộc phải giống nhau**. Vấn đề phát sinh khi code lặng lẽ lấy “default zone” của một tầng làm nguồn sự thật:

```java
// Có thể thay đổi ý nghĩa theo cấu hình máy chạy:
ZoneId zone = ZoneId.systemDefault();
```

Nếu business requirement là “giờ địa phương người dùng”, `systemDefault()` không có cơ sở để xác định lựa chọn đó.

### 5.1. Browser timezone không phải luôn là lựa chọn đã được xác nhận

Trình duyệt có thể cung cấp timezone máy đang dùng, nhưng:
- người dùng có thể đi du lịch;
- thiết bị có timezone sai;
- lịch có thể gắn với cửa hàng/chi nhánh thay vì người tạo;
- một admin có thể đặt lịch thay người ở quốc gia khác.

Nên hiển thị rõ múi giờ tại UI và lưu giá trị đã được chọn/được phép sử dụng.

### 5.2. Server và database chạy UTC là một chiến lược vận hành tốt

Đặt timezone mặc định của hạ tầng về UTC thường giúp logs, monitoring và giao tiếp giữa các nodes nhất quán hơn. Nhưng **dù tất cả server đều chạy UTC, business scheduling vẫn cần ZoneId của người dùng**.

### 5.3. Email recipient timezone không suy ra từ email address

Không thể kết luận một địa chỉ `user@example.com` thuộc một timezone nhất định. Cũng không nên suy ra timezone chỉ từ ngôn ngữ giao diện hoặc quốc tịch. Hãy lấy từ preference, location/business setting được cung cấp có chủ đích hoặc lựa chọn rõ trong yêu cầu.

## 6. Hai loại lịch: một lần và lặp lại

Đây là quyết định thiết kế quan trọng nhất.

### 6.1. Lịch gửi một lần

> Gửi email lúc 09:00 ngày 01/12/2026 theo giờ Việt Nam.

Sau khi resolve, có đúng một `Instant`:

```text
local = 2026-12-01T09:00
zone = Asia/Ho_Chi_Minh
sendAt = 2026-12-01T02:00:00Z
```

Nếu người dùng đổi timezone hiển thị sau khi đã lên lịch, có thể vẫn giữ nguyên mốc `sendAt`. Đây là **một cuộc hẹn tại một instant đã chốt**, trừ khi sản phẩm cho phép chỉnh sửa lịch.

### 6.2. Lịch lặp theo giờ địa phương

> Gửi báo cáo mỗi ngày làm việc lúc 09:00 theo giờ Berlin.

Không nên chỉ cộng `Duration.ofDays(1)` vào `Instant` trước. Khi Berlin đổi offset từ +01 sang +02, mỗi ngày lịch địa phương vẫn là 09:00, còn instant UTC sẽ dịch một giờ.

```text
Winter (Berlin +01):
09:00 local -> 08:00 UTC

Summer (Berlin +02):
09:00 local -> 07:00 UTC
```

Cần lưu một **recurrence rule** và `ZoneId`, rồi sinh mỗi occurrence từ **ngày local** của vùng đó.

### 6.3. Lịch định kỳ theo khoảng thời gian tuyệt đối

> Gửi một báo cáo kỹ thuật mỗi 24 giờ, tính từ lần đầu.

Đây là một **fixed duration** khác “mỗi ngày lúc 09:00”. Cộng `Duration.ofHours(24)` là phù hợp khi requirement chính là khoảng cách 24 giờ, không phải wall-clock time.

**Phải ghi rõ contract: “mỗi 24 giờ” và “mỗi ngày 09:00” khác nhau ở nơi có DST.**

## 7. Hiểu Daylight Saving Time (DST)

Một số quốc gia điều chỉnh đồng hồ vào mùa xuân và mùa thu. Điều này tạo ra hai tình huống khó:

1. **Gap:** một khoảng giờ địa phương **không tồn tại** khi đồng hồ nhảy tới.
2. **Overlap:** một khoảng giờ địa phương **xuất hiện hai lần** khi đồng hồ quay lùi.

Tại `Europe/Berlin` năm 2026:

- Ngày **29/03/2026**, đồng hồ nhảy từ 02:00 lên 03:00. `02:30` không tồn tại.
- Ngày **25/10/2026**, đồng hồ quay từ 03:00 xuống 02:00. `02:30` xuất hiện hai lần.

### 7.1. Spring forward: giờ không tồn tại

```text
Europe/Berlin — 29/03/2026

01:58 +01
01:59 +01
03:00 +02   <-- 02:00 đến 02:59 không tồn tại
03:01 +02
```

Lịch “29/03/2026 02:30 Berlin” không thể được biểu diễn bằng một `ZonedDateTime` giữ nguyên wall time 02:30 trong zone đó.

Bạn phải có chính sách rõ:
- **REJECT:** từ chối một lịch một lần tại giờ không tồn tại.
- **SKIP:** bỏ occurrence của lịch lặp trong ngày đó.
- **NEXT_VALID_TIME:** gửi tại thời điểm local hợp lệ đầu tiên sau gap, ví dụ 03:00.
- **SHIFT_BY_GAP:** dịch giờ qua khoảng gap, ví dụ 02:30 → 03:30.

Các lựa chọn tạo kết quả khác nhau. Đừng cho thư viện tự quyết mà không biết requirement.

### 7.2. Fall back: giờ xuất hiện hai lần

```text
Europe/Berlin — 25/10/2026

02:30 +02 -> 2026-10-25T00:30:00Z
...
02:30 +01 -> 2026-10-25T01:30:00Z
```

Nếu người dùng chọn “02:30”, có hai instants hợp lệ. Các chính sách có thể là:
- **EARLIER_OFFSET:** lần xuất hiện đầu.
- **LATER_OFFSET:** lần xuất hiện thứ hai.
- **BOTH:** gửi hai lần (chỉ khi yêu cầu thực sự như vậy).
- **REJECT:** yêu cầu người dùng chọn rõ.

Với email giao dịch hoặc báo cáo định kỳ, **gửi hai lần do overlap thường là lỗi**, nên cần quy tắc xử lý trước khi dispatch.

### 7.3. LocalDateTime.atZone có chính sách mặc định

```java
LocalDateTime local =
    LocalDateTime.of(2026, 3, 29, 2, 30);

ZonedDateTime result = local.atZone(
    ZoneId.of("Europe/Berlin")
);
```

Với giờ trong gap, `atZone` thường tự đẩy tới một thời điểm hợp lệ sau gap. Với giờ trong overlap, nó thường chọn offset trước của quy tắc chuyển đổi. Đây là behavior tiện lợi của Java, nhưng **không nên ngầm coi là business policy** nếu sản phẩm cần xác nhận, skip hoặc chọn occurrence khác.

## 8. Kiểm tra gap và overlap bằng ZoneRules

`ZoneRules.getValidOffsets(local)` cho biết một giờ địa phương có bao nhiêu offset hợp lệ:

- `1 offset`: bình thường.
- `0 offsets`: gap.
- `2 offsets`: overlap (trong những chuyển đổi thông thường).

```java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.zone.ZoneRules;
import java.util.List;

ZoneId zone = ZoneId.of("Europe/Berlin");
ZoneRules rules = zone.getRules();

LocalDateTime gap =
    LocalDateTime.of(2026, 3, 29, 2, 30);

LocalDateTime overlap =
    LocalDateTime.of(2026, 10, 25, 2, 30);

List<ZoneOffset> gapOffsets =
    rules.getValidOffsets(gap);       // empty

List<ZoneOffset> overlapOffsets =
    rules.getValidOffsets(overlap);   // +02:00, +01:00
```

### 8.1. Định nghĩa chính sách tường minh

```java
public enum GapPolicy {
    REJECT,
    SKIP,
    NEXT_VALID_TIME,
    SHIFT_BY_GAP
}

public enum OverlapPolicy {
    EARLIER_OFFSET,
    LATER_OFFSET,
    REJECT
}
```

Đối với lịch **một lần**, `REJECT` cho giờ không tồn tại có thể dễ hiểu nhất vì UI có thể yêu cầu chọn lại. Đối với lịch **lặp**, bạn cần định nghĩa một policy dùng ổn định cho mọi lần chuyển DST.

### 8.2. Resolver ví dụ cho một mốc gửi

```java
package com.example.mail.schedule;

import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.zone.ZoneOffsetTransition;
import java.time.zone.ZoneRules;
import java.util.List;

public final class MailScheduleTimeResolver {

    public Instant resolve(
            LocalDateTime requestedLocal,
            ZoneId zone,
            GapPolicy gapPolicy,
            OverlapPolicy overlapPolicy) {

        ZoneRules rules = zone.getRules();
        List<ZoneOffset> offsets =
            rules.getValidOffsets(requestedLocal);

        if (offsets.size() == 1) {
            return ZonedDateTime.ofLocal(
                requestedLocal, zone, offsets.get(0)
            ).toInstant();
        }

        if (offsets.isEmpty()) {
            ZoneOffsetTransition transition =
                rules.getTransition(requestedLocal);

            if (gapPolicy == GapPolicy.REJECT
                    || gapPolicy == GapPolicy.SKIP) {
                throw new IllegalArgumentException(
                    "Scheduled local time does not exist"
                );
            }

            LocalDateTime adjusted;

            if (gapPolicy == GapPolicy.NEXT_VALID_TIME) {
                adjusted = transition.getDateTimeAfter();
            } else {
                adjusted = requestedLocal.plus(
                    transition.getDuration()
                );
            }

            return adjusted.atZone(zone).toInstant();
        }

        if (overlapPolicy == OverlapPolicy.REJECT) {
            throw new IllegalArgumentException(
                "Scheduled local time is ambiguous"
            );
        }

        ZoneOffset chosen =
            overlapPolicy == OverlapPolicy.EARLIER_OFFSET
                ? offsets.get(0)
                : offsets.get(offsets.size() - 1);

        return ZonedDateTime.ofLocal(
            requestedLocal, zone, chosen
        ).toInstant();
    }
}
```

Ý nghĩa:
- `NEXT_VALID_TIME` chọn mốc local hợp lệ đầu tiên sau gap.
- `SHIFT_BY_GAP` cộng độ dài gap vào local time, giữ tương đối vị trí phút nếu gap một giờ.
- `EARLIER_OFFSET`/`LATER_OFFSET` chọn một occurrence rõ ràng.
- `SKIP` trong ví dụ được báo không có instant; tầng recurrence nên bắt và **bỏ occurrence của ngày đó**, không coi đó là failure cần retry SMTP.

Với `BOTH` ở overlap, resolver cần trả **danh sách hai instants** thay vì một `Instant`; chỉ triển khai khi sản phẩm thực sự yêu cầu hai lần gửi.

### 8.3. Một thư viện quy tắc múi giờ vẫn không biết ý định kinh doanh

Java giúp giải toán “các offset nào hợp lệ”, nhưng không biết:
- báo cáo cần skip ngày DST hay gửi lúc 03:00;
- thông báo khẩn cấp nên gửi ở occurrence đầu hay cuối;
- người dùng có cho phép hai email trong overlap không.

Các quyết định phải được ghi trong **schedule policy**, được test và thể hiện rõ trong UI khi cần.

## 9. Thiết kế API đặt lịch gửi

Một API dễ dùng cho một lần gửi bằng giờ local:

```json
{
  "recipient": "customer@example.net",
  "templateId": "order-reminder",
  "localSendTime": "2026-12-01T09:00:00",
  "timeZone": "Asia/Ho_Chi_Minh",
  "gapPolicy": "REJECT",
  "overlapPolicy": "EARLIER_OFFSET",
  "idempotencyKey": "order-123-reminder-1"
}
```

Backend cần:
1. Xác thực người gọi và quyền gửi tới recipient.
2. Validate `localSendTime` và `timeZone`.
3. Parse `ZoneId.of(timeZone)`; không đoán timezone khi thiếu.
4. Dùng resolver chuyển thành `Instant`.
5. Kiểm tra mốc gửi hợp lệ, chưa quá hạn, nằm trong giới hạn scheduling.
6. Kiểm tra idempotency.
7. Persist job và trả message key + thời gian đã resolve.

### 9.1. DTO Java

```java
package com.example.mail.schedule;

import java.time.LocalDateTime;

public record CreateScheduledMailRequest(
    String recipient,
    String templateId,
    LocalDateTime localSendTime,
    String timeZone,
    GapPolicy gapPolicy,
    OverlapPolicy overlapPolicy,
    String idempotencyKey
) {}
```

Có thể dùng Jakarta Bean Validation để kiểm tra field bắt buộc/độ dài, nhưng **business validation về timezone** vẫn cần logic riêng.

### 9.2. Không nhận timezone abbreviation mơ hồ

Các chuỗi như `CST`, `IST`, `PST` có thể mang nhiều nghĩa hoặc bị hiểu theo quy tắc vùng khác. Ưu tiên IANA IDs:
- `Asia/Ho_Chi_Minh`;
- `Europe/Berlin`;
- `America/New_York`;
- `Asia/Tokyo`.

Không nhận arbitrary string rồi fallback sang timezone server khi parse lỗi. Nếu timezone invalid, trả validation error rõ ràng.

### 9.3. Một instant ISO 8601 cũng có thể là input

Một API tích hợp giữa hệ thống có thể nhận:

```json
{
  "sendAt": "2026-12-01T02:00:00Z"
}
```

Điều này rõ một mốc tuyệt đối. Tuy nhiên, nếu người dùng cần **đổi lịch theo giờ địa phương** hoặc **lịch lặp**, API vẫn cần biết ZoneId/recurrence policy tương ứng. Không dùng input instant-only rồi cố đoán ý định giờ địa phương từ IP hoặc locale.

## 10. Validate timezone, mốc gửi và thời hạn

Những kiểm tra hữu ích:

| Điều kiện | Quy tắc gợi ý |
|---|---|
| ZoneId không có trong tzdb | Trả lỗi, không fallback im lặng |
| Lịch trong quá khứ | Từ chối hoặc theo policy “send immediately” được xác nhận |
| Lịch quá xa tương lai | Đặt giới hạn phù hợp sản phẩm |
| Local time không tồn tại | Áp dụng gap policy |
| Local time xuất hiện hai lần | Áp dụng overlap policy |
| Recipient chưa được phép gửi | Từ chối trước khi persist |
| Marketing chưa có consent | Không tạo job gửi |
| Token xác minh sẽ hết hạn trước sendAt | Từ chối hoặc tạo token đúng lúc |
| User có quiet hours | Điều chỉnh/hoãn theo policy |
| Thời điểm đã hủy hoặc job đã accepted | Không sửa lịch như thể chưa gửi |

Đừng chỉ kiểm tra `sendAt.isAfter(Instant.now())` trong controller rồi bỏ qua các giới hạn nghiệp vụ còn lại.

### 10.1. Cần bảo vệ đồng thời khỏi clock skew

Một request ở sát thời điểm hiện tại có thể được validate lúc 08:59:59.900 nhưng commit lúc 09:00:00.200. Nếu yêu cầu là “không gửi trước”, có thể chấp nhận job đã đến hạn ngay; nếu API không chấp nhận lịch quá gần, cần quy tắc min lead-time rõ ràng.

### 10.2. Lưu snapshot quyết định

Sau khi resolve, có thể ghi:
- người dùng chọn ngày giờ nào;
- timezone nào;
- offset tại thời điểm tính;
- gap/overlap policy;
- resolved UTC instant;
- schedule version.

Điều này giúp giải thích sau này vì sao job gửi lúc một UTC instant cụ thể.

## 11. Lưu thời gian trong PostgreSQL

Với PostgreSQL, kiểu `TIMESTAMPTZ` là lựa chọn phù hợp cho một thời điểm tuyệt đối. Nó **không lưu nguyên tên ZoneId**.

Ví dụ schema:

```sql
CREATE TABLE scheduled_mail (
    message_key UUID PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    recipient VARCHAR(320) NOT NULL,
    template_id VARCHAR(120) NOT NULL,
    schedule_kind VARCHAR(24) NOT NULL,
    local_send_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    zone_id VARCHAR(100) NOT NULL,
    gap_policy VARCHAR(32) NOT NULL,
    overlap_policy VARCHAR(32) NOT NULL,
    send_at TIMESTAMPTZ NOT NULL,
    next_attempt_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(32) NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    lease_token UUID,
    lease_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_scheduled_mail_due
    ON scheduled_mail(next_attempt_at, send_at)
    WHERE status IN ('PENDING', 'RETRY_WAIT');
```

Đây là schema tối giản để minh họa. Trong production có thể cần:
- unique constraint cho business idempotency key;
- audit và lịch sử thay đổi;
- expiration/deadline;
- provider/tenant routing;
- bảng attempt và dead-letter;
- encryption và retention cho recipient/payload;
- recurrence definition ở bảng riêng.

### 11.1. TIMESTAMPTZ không có nghĩa “lưu múi giờ”

PostgreSQL `TIMESTAMPTZ` lưu thời điểm tuyệt đối và có thể **hiển thị** theo timezone của database session. Nó không lưu chuỗi `Asia/Ho_Chi_Minh`, `Europe/Berlin` hoặc offset mà người dùng đã nhập.

Ví dụ cùng một `send_at` có thể được hiển thị là 02:00 UTC hoặc 09:00 +07 tùy session timezone. Hai cách hiển thị vẫn là cùng mốc.

Vì vậy nếu muốn bảo toàn lịch địa phương, lưu **cột `zone_id` riêng** và `local_send_time` như dữ liệu ý định, không chỉ một `TIMESTAMPTZ`.

### 11.2. TIMESTAMP WITHOUT TIME ZONE dùng khi nào?

`TIMESTAMP WITHOUT TIME ZONE` chỉ lưu ngày giờ local không có offset. Nó phù hợp để lưu **ý định local** hoặc một trường local event, nhưng **không tự đủ** cho query “job nào đã tới hạn trên timeline toàn cầu”.

Đừng viết:

```sql
WHERE local_send_time <= NOW()
```

mà không quy định conversion/timezone vì hai phía có semantics khác nhau.

### 11.3. Mapping trong Java

`Instant` phù hợp cho `send_at` ở tầng domain. Với JDBC, có thể truyền `OffsetDateTime` ở UTC để mapping `TIMESTAMPTZ` rõ ràng:

```java
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

OffsetDateTime utcDateTime =
    sendAt.atOffset(ZoneOffset.UTC);
```

Khi đọc, chuyển về `Instant`. Cần đảm bảo driver/ORM mapping theo phiên bản thực tế, test với database production type, không suy diễn từ H2.

### 11.4. Database timezone và JDBC

Cấu hình JVM UTC, database session UTC và serialization ISO 8601 giúp vận hành nhất quán, nhưng điều quan trọng nhất là **không chuyển `LocalDateTime` sang instant bằng timezone mặc định không được ghi rõ**.

## 12. Schema riêng cho lịch lặp

Một lịch “mỗi thứ Hai lúc 09:00 theo giờ Berlin” là **schedule definition**; mỗi lần gửi tương ứng một **occurrence**. Tách hai loại dữ liệu giúp tính lại lịch khi timezone rule thay đổi.

```sql
CREATE TABLE recurring_mail_schedule (
    schedule_id UUID PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    template_id VARCHAR(120) NOT NULL,
    zone_id VARCHAR(100) NOT NULL,
    local_time TIME WITHOUT TIME ZONE NOT NULL,
    recurrence_rule VARCHAR(180) NOT NULL,
    gap_policy VARCHAR(32) NOT NULL,
    overlap_policy VARCHAR(32) NOT NULL,
    start_local_date DATE NOT NULL,
    end_local_date DATE,
    status VARCHAR(24) NOT NULL,
    schedule_version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE mail_occurrence (
    occurrence_id UUID PRIMARY KEY,
    schedule_id UUID NOT NULL
        REFERENCES recurring_mail_schedule(schedule_id),
    occurrence_local_date DATE NOT NULL,
    occurrence_slot VARCHAR(40) NOT NULL,
    send_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(24) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_mail_occurrence
        UNIQUE (
            schedule_id,
            occurrence_local_date,
            occurrence_slot
        )
);
```

`recurrence_rule` có thể là một enum đơn giản như `WEEKDAYS` hoặc một rule DSL/cron được ứng dụng hỗ trợ. Không nhận arbitrary cron expression từ người dùng nếu sản phẩm không kiểm soát được chi phí và semantics.

### 12.1. Tại sao cần occurrence riêng?

- Không tạo lại email của ngày cũ sau restart.
- Có trạng thái riêng cho một kỳ gửi.
- Cho phép hủy một kỳ mà không hủy toàn bộ lịch.
- Cho phép retry một kỳ khi SMTP lỗi.
- Giữ lịch sử những gì đã thực sự lên kế hoạch.
- Có unique key để ngăn nhiều scheduler replicas tạo hai jobs cùng một kỳ.

### 12.2. Overlap policy BOTH cần key khác

Nếu lịch cho phép **gửi hai lần** trong một ngày DST overlap, unique key chỉ gồm `(schedule_id, local_date)` sẽ ngăn occurrence thứ hai. Cần một slot/offset/occurrence index được định nghĩa rõ như `first` và `second`.

Với policy gửi một lần, `occurrence_slot="single"` có thể đủ.

## 13. Tính một occurrence từ ngày local

Ví dụ lịch gửi báo cáo vào 09:00 mỗi ngày:

```java
import java.time.*;

public final class DailyScheduleCalculator {

    private final MailScheduleTimeResolver resolver;

    public DailyScheduleCalculator(
            MailScheduleTimeResolver resolver) {
        this.resolver = resolver;
    }

    public Instant occurrenceAt(
            LocalDate localDate,
            LocalTime localTime,
            ZoneId zone,
            GapPolicy gapPolicy,
            OverlapPolicy overlapPolicy) {

        LocalDateTime localDateTime =
            LocalDateTime.of(localDate, localTime);

        return resolver.resolve(
            localDateTime,
            zone,
            gapPolicy,
            overlapPolicy
        );
    }
}
```

Nếu lịch chỉ chạy ngày làm việc, cần một bộ lọc ngày theo `DayOfWeek`/holiday calendar phù hợp. Đừng cố thực hiện lịch lặp chỉ bằng:

```java
// Sai mục tiêu nếu cần giữ 09:00 giờ địa phương:
Instant next = previous.plus(Duration.ofDays(1));
```

### 13.1. Đúng cách tính “ngày tiếp theo”

```java
LocalDate nextLocalDate =
    previousLocalDate.plusDays(1);

Instant nextDue = calculator.occurrenceAt(
    nextLocalDate,
    LocalTime.of(9, 0),
    ZoneId.of("Europe/Berlin"),
    GapPolicy.NEXT_VALID_TIME,
    OverlapPolicy.EARLIER_OFFSET
);
```

Ứng dụng lấy **ngày local tiếp theo** rồi resolve lại bằng timezone rules của ngày đó. Vì vậy UTC offset tự thay đổi khi DST đổi.

### 13.2. Không chỉ cộng tháng trong Instant

Với lịch “ngày đầu mỗi tháng lúc 09:00”, hãy tăng `YearMonth` hoặc `LocalDate.plusMonths(...)` theo policy, rồi resolve mốc mới. Không cộng một số cố định 30 ngày vào Instant: tháng có 28–31 ngày và DST có thể thay đổi.

### 13.3. Các lịch cuối tháng

Một lịch “ngày 31 hằng tháng” không có occurrence trong tháng 2, 4, 6, 9 và 11. Quy tắc có thể là:
- skip tháng không có ngày 31;
- dời sang ngày cuối tháng;
- reject khi user tạo lịch.

Đây là **business calendar policy** khác với DST nhưng cũng phải được ghi rõ và kiểm thử.

## 14. Spring @Scheduled với cron và zone

Spring hỗ trợ định nghĩa timezone cho cron trigger:

```java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class VietnamMorningDigestTrigger {

    private final DigestJobCreator creator;

    public VietnamMorningDigestTrigger(
            DigestJobCreator creator) {
        this.creator = creator;
    }

    @Scheduled(
        cron = "0 0 9 * * MON-FRI",
        zone = "Asia/Ho_Chi_Minh"
    )
    public void createDailyDigest() {
        creator.createForCurrentBusinessDate();
    }
}
```

`DigestJobCreator` là service do ứng dụng định nghĩa, có nhiệm vụ kiểm tra ngày nghiệp vụ và **persist một email occurrence/job có idempotency key**, không nên gửi email thật ngay trong method cron.

### 14.1. Cần bật scheduling

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration
@EnableScheduling
public class SchedulingConfiguration {}
```

Một số auto-configuration hoặc component khác có thể đã bật scheduling; phải thống nhất cấu hình hiện có để tránh trùng cơ chế trigger.

### 14.2. Cron của Spring thường có sáu trường

Ví dụ:

```text
0 0 9 * * MON-FRI
| | | | | |
| | | | | +--- day of week
| | | | +----- month
| | | +------- day of month
| | +--------- hour
| +----------- minute
+------------- second
```

Đừng copy một cron năm trường từ hệ thống khác mà không xem parser của Spring sử dụng định dạng nào.

### 14.3. zone áp dụng cho **trigger**, không đổi timezone server

`zone = "Asia/Ho_Chi_Minh"` khiến cron được tính theo zone đó. Nó không:
- thay đổi `ZoneId.systemDefault()`;
- thay đổi timezone của database;
- thay đổi timezone của người nhận;
- làm email được giao đúng giờ;
- tự lưu lịch vào database.

### 14.4. Cron không tự chạy bù khi downtime

Nếu service ngừng hoạt động đúng thời điểm cron:
- không được giả định lần gửi bị bỏ lỡ sẽ tự xuất hiện sau restart;
- cần một **catch-up scheduler** hoặc recurrence materializer query business dates chưa tạo occurrence;
- kiểm soát quá hạn, quota và tránh gửi đồng loạt thông báo cũ.

## 15. Không dùng một cron cố định cho từng user vô hạn

Một sản phẩm SaaS có 100.000 users, mỗi người chọn timezone và lịch riêng. Không nên tạo một method `@Scheduled` hoặc một bean TaskScheduler cho **mỗi user** mà không có lifecycle, persistence và giới hạn tài nguyên rõ ràng.

Mô hình phù hợp hơn:

```text
recurring_mail_schedule (user-defined)
            |
            v
Materializer / periodic scheduler
            |
            | create occurrences for next interval
            v
mail_occurrence / scheduled_mail
            |
            v
Due-job dispatcher
            |
            v
JavaMailSender
```

Một scheduler ít job kỹ thuật có thể xử lý rất nhiều business schedules thông qua database.

### 15.1. Materialize bao xa?

Ví dụ sinh occurrences cho 7 ngày tới:
- đủ để due dispatcher làm việc;
- không tạo hàng triệu future jobs không cần thiết;
- có thể tính lại những future occurrences khi user đổi timezone/rule;
- vẫn cần chạy materializer bù sau downtime.

Chọn horizon theo khối lượng, tính ổn định của quy tắc múi giờ và nhu cầu vận hành. Với lịch marketing có thể cho phép sửa kế hoạch thường xuyên, materialize quá xa dễ làm tốn dữ liệu và phức tạp khi hủy.

### 15.2. Khi rule timezone thay đổi

Nếu tzdb được cập nhật, occurrences **chưa thực thi** của lịch “09:00 địa phương” có thể cần tính lại UTC instant. Đây là khác biệt với lịch “gửi tại Instant X đã chốt”, thường không nên tự dịch chỉ vì tzdb thay đổi.

Ứng dụng cần ghi rõ:
- lịch được định nghĩa theo wall time hay instant;
- có cho cập nhật future occurrences không;
- schedule version và audit;
- cách rollout khi nhiều JVM đang chạy các phiên bản tzdb khác nhau.

## 16. Due-job dispatcher: kiểm tra Instant, không so giờ string

Worker chỉ cần biết “mốc này đã đến hạn chưa?” sau khi lịch đã được resolve:

```java
Instant now = clock.instant();

boolean due = !job.sendAt().isAfter(now);
```

Không so:
- chuỗi `"09:00"`;
- `LocalDateTime.now()` không có zone rõ;
- giờ của browser;
- giờ đã format theo locale;
- timestamp kiểu text.

### 16.1. Polling query

```sql
SELECT message_key
FROM scheduled_mail
WHERE status IN ('PENDING', 'RETRY_WAIT')
  AND send_at <= :now
  AND next_attempt_at <= :now
ORDER BY next_attempt_at, send_at
LIMIT :batchSize;
```

Trên một database production có nhiều workers, query `SELECT` đơn lẻ chưa đủ để ngăn hai worker cùng lấy job. Cần atomic claim hoặc broker semantics tương ứng.

### 16.2. Spring scheduler để đánh thức due dispatcher

```java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class DueMailTick {

    private final ScheduledMailDispatcher dispatcher;

    public DueMailTick(
            ScheduledMailDispatcher dispatcher) {
        this.dispatcher = dispatcher;
    }

    @Scheduled(
        fixedDelayString =
            "${app.mail.dispatch.fixed-delay-ms:1000}"
    )
    public void dispatch() {
        dispatcher.dispatchDueBatch();
    }
}
```

`ScheduledMailDispatcher` là service do ứng dụng định nghĩa. Cấu hình `fixedDelay` ở đây không phải timezone của business schedule; nó chỉ là khoảng nghỉ kỹ thuật giữa các lần quét.

### 16.3. Send-at là thời điểm **không gửi trước**

Có thể thiết kế contract:
- Job không được submit **trước** `send_at`.
- Khi đã đến hạn, worker cố gắng submit trong SLA có điều kiện.
- Kết quả SMTP có thể accepted muộn do queue/network.
- Không bảo đảm provider delivered cùng instant.

Cần nêu rõ semantics này trong UI và API.

## 17. Atomic claim và tránh gửi trùng khi nhiều instances

Một ví dụ PostgreSQL:

```sql
WITH due AS (
    SELECT message_key
    FROM scheduled_mail
    WHERE status IN ('PENDING', 'RETRY_WAIT')
      AND send_at <= :now
      AND next_attempt_at <= :now
    ORDER BY next_attempt_at, send_at, created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE scheduled_mail s
SET status = 'SENDING',
    attempt_count = attempt_count + 1,
    lease_token = :leaseToken,
    lease_expires_at = :leaseExpiresAt,
    updated_at = :now
FROM due
WHERE s.message_key = due.message_key
RETURNING
    s.message_key, s.send_at, s.attempt_count,
    s.lease_token;
```

Claim nên chạy trong **transaction ngắn** và commit trước khi gọi SMTP. Tạo attempt history trong cùng transaction claim nếu cần bảo đảm tương ứng.

### 17.1. Không giữ row lock suốt khi gửi SMTP

`JavaMailSender.send(...)` có thể mất nhiều giây hoặc timeout. Giữ DB transaction trong thời gian mạng có thể:
- giữ locks;
- tăng contention;
- làm thread pool cạn;
- gây rollback sau khi SMTP đã nhận thư;
- khiến retry gửi trùng.

Mô hình:

```text
TX 1: claim + attempt (commit)
    |
    v
SMTP submission (no DB transaction)
    |
    v
TX 2: save outcome (commit)
```

### 17.2. Lease token và fencing

Khi lưu outcome, cập nhật chỉ khi worker vẫn sở hữu lease:

```sql
UPDATE scheduled_mail
SET status = 'SMTP_ACCEPTED',
    lease_token = NULL,
    lease_expires_at = NULL,
    updated_at = :now
WHERE message_key = :messageKey
  AND status = 'SENDING'
  AND lease_token = :leaseToken;
```

Nếu update 0 rows, worker có thể đã mất quyền. Không im lặng ghi đè job đã được worker khác xử lý.

Fencing chỉ bảo vệ **database state**. Nếu SMTP đã nhận email, một database rollback hoặc lease expiry **không thể thu hồi** nó.

## 18. Worker gửi email sau khi đến hạn

Một worker có thể dùng Spring `JavaMailSender`:

```java
package com.example.mail.schedule;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class ScheduledMailSubmitter {

    private final JavaMailSender sender;

    public ScheduledMailSubmitter(JavaMailSender sender) {
        this.sender = sender;
    }

    public void submit(ScheduledMailContent content)
            throws MessagingException {

        MimeMessage mime = sender.createMimeMessage();

        MimeMessageHelper helper =
            new MimeMessageHelper(mime, true, "UTF-8");

        helper.setFrom(content.from());
        helper.setTo(content.recipient());
        helper.setSubject(content.subject());
        helper.setText(
            content.plainText(),
            content.htmlText()
        );

        mime.setHeader(
            "X-Application-Message-Key",
            content.messageKey()
        );

        sender.send(mime);
    }
}
```

`ScheduledMailContent` là DTO do ứng dụng định nghĩa chứa các field tương ứng, không phải API của Spring.

Phần xử lý timezone **không nằm trong SMTP adapter**: trước khi tới adapter, scheduler và due dispatcher đã xác định job eligible. SMTP sender chỉ submit content.

### 18.1. Không gửi email trong HTTP request để “chờ đến giờ”

Tránh:

```java
// Không làm trong request handler:
Thread.sleep(durationUntilSendAt);
mailSender.send(message);
```

Vì:
- giữ thread rất lâu;
- process restart làm mất lịch;
- không có cancellation/reschedule bền vững;
- khó quản lý timezone/DST;
- không xử lý backpressure;
- không có audit/retry đáng tin.

Lưu job vào DB và để worker xử lý sau.

### 18.2. Không tạo MimeMessage quá sớm cho lịch dài

Nếu email được lên lịch trước một tháng, không cần giữ một `MimeMessage` mutable trong bộ nhớ một tháng. Lưu template/content snapshot và attachment references có lifecycle rõ, rồi dựng MIME gần thời điểm submission.

Với email xác minh có token có hạn, phải xác định lúc nào token được tạo. Nếu tạo token lúc lên lịch nhưng gửi sau thời điểm token hết hạn, email nhận được sẽ vô dụng.

## 19. Retry vẫn phải tuân thủ deadline và timezone

Giả sử người dùng đặt thông báo lúc 09:00:
- 09:00: worker thử gửi, SMTP trả lỗi tạm thời.
- 09:05: retry.
- 09:15: retry tiếp.
- 10:00: email đã quá hạn giá trị nghiệp vụ.

Cần phân biệt:

- `send_at`: thời điểm sớm nhất được submit lần đầu.
- `next_attempt_at`: thời điểm sớm nhất được retry.
- `expires_at`: thời điểm email không còn hữu ích hoặc không được gửi nữa.

Tất cả các mốc thực thi nên là `Instant`/`TIMESTAMPTZ`.

### 19.1. Retry không thay đổi ý định lịch gốc

Một lần retry lúc 09:05 không làm `send_at` trở thành 09:05. Nó là attempt tiếp theo của **cùng email logic**. Lưu attempt ID và lịch sử để giải thích sự khác biệt giữa giờ mong muốn và giờ SMTP thực tế.

### 19.2. Không retry mọi timeout mù quáng

Nếu mất kết nối sau khi SMTP relay có thể đã nhận DATA, kết quả có thể là `UNKNOWN`. Retry lúc 09:05 có thể tạo hai email, đặc biệt nguy hiểm với xác minh thanh toán, hóa đơn hoặc nhắc lịch.

Cần:
- phân loại lỗi;
- retry có giới hạn và backoff với lỗi an toàn;
- reconciliation đối với `UNKNOWN`;
- dead letter hoặc manual review cho lỗi không phục hồi;
- idempotency business key để tránh tạo hai email logic.

## 20. Quiet hours và gửi theo giờ thuận tiện

Nhiều sản phẩm cần tránh gửi email marketing hoặc thông báo không khẩn cấp ngoài giờ phù hợp:

```text
Allowed window (user zone):
09:00–20:00
```

Nếu job đến hạn lúc 23:30 theo giờ người nhận, policy có thể hoãn sang 09:00 ngày hôm sau. Nhưng phải phân biệt:
- email giao dịch quan trọng có được gửi xuyên đêm không;
- marketing có consent/suppression nào;
- window theo tenant hay theo recipient;
- ngày nghỉ/lễ theo vùng nào;
- tình huống biên DST gap/overlap.

### 20.1. Xét quiet hours trong ZoneId của recipient

```java
import java.time.*;

Instant now = clock.instant();
ZoneId recipientZone =
    ZoneId.of("America/New_York");

LocalTime localNow =
    now.atZone(recipientZone).toLocalTime();

boolean insideWindow =
    !localNow.isBefore(LocalTime.of(9, 0))
    && localNow.isBefore(LocalTime.of(20, 0));
```

Ví dụ chỉ đúng với một window **không đi qua nửa đêm**. Với window như 22:00–06:00 phải dùng logic khác, xét ngày local, và có thể phát sinh boundary DST.

### 20.2. Tính lại next-eligible instant

Nếu cần hoãn:
1. Chuyển hiện tại sang local time của recipient.
2. Tìm local date/time sớm nhất hợp lệ.
3. Áp dụng weekend/holiday/business policy.
4. Resolve qua `ZoneRules` và gap/overlap policy.
5. Lưu next eligible `Instant`.
6. Không gửi trước mốc mới.

Không “cộng 8 giờ” hoặc “cộng một ngày UTC” rồi cho rằng sẽ vào đúng 09:00 địa phương.

### 20.3. Không suy ra quiet hours từ quốc gia

Một người đang làm việc ca đêm có thể chọn lịch khác. Nếu sản phẩm hỗ trợ, hãy để người dùng định nghĩa preference và giải thích ràng buộc mặc định, thay vì áp một giờ cứng cho mọi người trong một nước.

## 21. Hủy lịch, đổi giờ và đổi timezone

Một job đã tạo có thể được:
- hủy trước khi gửi;
- dời sang ngày/giờ khác;
- chuyển timezone hiển thị mà không đổi instant;
- thay đổi timezone của chính lịch;
- thay đổi recurrence rule.

Các hành động trên **khác nhau**.

### 21.1. Đổi timezone hiển thị

Ví dụ job có:

```text
sendAt = 2026-12-01T02:00Z
```

Người dùng chuyển giao diện từ `Asia/Ho_Chi_Minh` sang `Europe/Berlin`:
- UI hiển thị 03:00 Berlin;
- `sendAt` vẫn là 02:00Z;
- email không bị dời lịch.

### 21.2. Đổi timezone của lịch theo wall time

Nếu người dùng muốn “vẫn gửi 09:00 nhưng theo giờ Berlin thay vì Việt Nam”:
- giữ local time 09:00;
- thay `ZoneId` thành `Europe/Berlin`;
- resolve lại instant;
- cập nhật schedule version;
- audit lý do và mốc cũ/mới.

Một lần đổi timezone như vậy **thật sự thay đổi sendAt**.

### 21.3. Cancel và worker claim race

Nếu user hủy đúng lúc worker claim:
- transaction cancellation phải kiểm tra status/version;
- worker kiểm tra quyền gửi trước side effect;
- nếu đã accepted SMTP, không thể thu hồi bằng cách đổi DB status;
- phải trả kết quả API chính xác “đã hủy trước khi gửi” hoặc “đã gửi/đang gửi, không thể đảm bảo hủy”.

Đừng ghi `CANCELLED` nếu SMTP đã accepted rồi hiển thị như thư chưa rời hệ thống.

## 22. Lịch gửi và nhiều SMTP providers

Một scheduled job có thể được route tới provider A hoặc B. Timezone tính **khi job eligible**, còn provider routing quyết định **gửi qua đâu**.

```text
schedule(local + zone)
         |
         v
resolve/sendAt instant
         |
         v
due-job dispatcher
         |
         v
route by tenant + category + policy
         |
         +--> SMTP A
         |
         +--> SMTP B
```

Lưu ý:
- provider có quota/rate limit, nên accepted time có thể trễ `sendAt`;
- failover sang provider B không làm thay timezone mong muốn;
- SMTP AUTH thành công không chứng minh SPF/DKIM/DMARC đúng;
- khi A trả `UNKNOWN`, không tự gửi sang B để “bắt kịp giờ”;
- provider A có thể đã accepted nhưng còn retry delivery ở phía họ.

Cần phân biệt scheduling SLA với deliverability SLA.

## 23. Clock injection: nền tảng của test ổn định

Không dùng `Instant.now()` rải rác trong controller/repository/worker nếu cần kiểm thử sát giờ gửi hoặc retry. Hãy inject `Clock`.

### 23.1. Bean Clock production

```java
import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ClockConfig {

    @Bean
    public Clock applicationClock() {
        return Clock.systemUTC();
    }
}
```

Service:

```java
import java.time.Clock;
import java.time.Instant;

public class DuePredicate {

    private final Clock clock;

    public DuePredicate(Clock clock) {
        this.clock = clock;
    }

    public boolean isDue(Instant sendAt) {
        return !sendAt.isAfter(clock.instant());
    }
}
```

Không cần đổi timezone của system clock để kiểm tra giờ Berlin; vì `Instant` luôn là mốc tuyệt đối, ta chỉ cần test resolver và dùng fixed instant.

### 23.2. Clock.fixed cho due-time test

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

class DuePredicateTest {

    @Test
    void jobIsNotDueBeforeItsInstant() {
        Clock clock = Clock.fixed(
            Instant.parse("2026-12-01T01:59:59Z"),
            ZoneOffset.UTC
        );

        DuePredicate predicate = new DuePredicate(clock);

        assertThat(predicate.isDue(
            Instant.parse("2026-12-01T02:00:00Z")
        )).isFalse();
    }

    @Test
    void jobIsDueExactlyAtSendAt() {
        Clock clock = Clock.fixed(
            Instant.parse("2026-12-01T02:00:00Z"),
            ZoneOffset.UTC
        );

        DuePredicate predicate = new DuePredicate(clock);

        assertThat(predicate.isDue(
            Instant.parse("2026-12-01T02:00:00Z")
        )).isTrue();
    }
}
```

Các test trên không cần SMTP server, không chờ thời gian thật và không phụ thuộc timezone của CI.

## 24. Test chuyển đổi Việt Nam sang UTC

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.*;
import org.junit.jupiter.api.Test;

class VietnamScheduleTest {

    private final MailScheduleTimeResolver resolver =
        new MailScheduleTimeResolver();

    @Test
    void nineAmVietnamIsTwoAmUtc() {
        Instant sendAt = resolver.resolve(
            LocalDateTime.of(2026, 12, 1, 9, 0),
            ZoneId.of("Asia/Ho_Chi_Minh"),
            GapPolicy.REJECT,
            OverlapPolicy.EARLIER_OFFSET
        );

        assertThat(sendAt).isEqualTo(
            Instant.parse("2026-12-01T02:00:00Z")
        );
    }
}
```

Test cần xác minh **giá trị mốc**; đừng chỉ assert chuỗi được format chứa “09:00” vì nó chưa chứng minh conversion đúng.

## 25. Test DST gap và overlap

### 25.1. Không chấp nhận giờ không tồn tại

```java
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Test
void rejectsNonexistentBerlinTime() {
    assertThatThrownBy(() -> resolver.resolve(
        LocalDateTime.of(2026, 3, 29, 2, 30),
        ZoneId.of("Europe/Berlin"),
        GapPolicy.REJECT,
        OverlapPolicy.EARLIER_OFFSET
    )).isInstanceOf(IllegalArgumentException.class);
}
```

### 25.2. Đưa tới giờ hợp lệ đầu tiên

```java
@Test
void gapCanMoveToFirstValidLocalTime() {
    Instant due = resolver.resolve(
        LocalDateTime.of(2026, 3, 29, 2, 30),
        ZoneId.of("Europe/Berlin"),
        GapPolicy.NEXT_VALID_TIME,
        OverlapPolicy.EARLIER_OFFSET
    );

    assertThat(due).isEqualTo(
        Instant.parse("2026-03-29T01:00:00Z")
    );
}
```

Lưu ý mốc này biểu diễn **03:00 Berlin** sau khi chuyển sang +02. Nếu sản phẩm chọn `SHIFT_BY_GAP`, kết quả sẽ là 03:30 Berlin, tương ứng `2026-03-29T01:30:00Z`. Cả hai hợp lệ nếu business policy đã định nghĩa.

### 25.3. Chọn lần xuất hiện đầu và cuối

```java
@Test
void overlapHasTwoDistinctInstants() {
    LocalDateTime local =
        LocalDateTime.of(2026, 10, 25, 2, 30);

    ZoneId zone = ZoneId.of("Europe/Berlin");

    Instant first = resolver.resolve(
        local, zone,
        GapPolicy.REJECT,
        OverlapPolicy.EARLIER_OFFSET
    );

    Instant second = resolver.resolve(
        local, zone,
        GapPolicy.REJECT,
        OverlapPolicy.LATER_OFFSET
    );

    assertThat(first).isEqualTo(
        Instant.parse("2026-10-25T00:30:00Z")
    );

    assertThat(second).isEqualTo(
        Instant.parse("2026-10-25T01:30:00Z")
    );
}
```

Mục tiêu của test là bảo vệ **quy tắc chọn occurrence**, tránh vô tình gửi hai email khi một local time lặp lại.

## 26. Test lịch lặp theo giờ địa phương

Với `Europe/Berlin`:
- 28/03/2026 lúc 09:00 là 08:00 UTC (CET +01).
- 29/03/2026 lúc 09:00 là 07:00 UTC (CEST +02).

```java
@Test
void dailyNineAmKeepsWallTimeAcrossDst() {
    ZoneId berlin = ZoneId.of("Europe/Berlin");

    Instant beforeChange = resolver.resolve(
        LocalDateTime.of(2026, 3, 28, 9, 0),
        berlin,
        GapPolicy.REJECT,
        OverlapPolicy.EARLIER_OFFSET
    );

    Instant afterChange = resolver.resolve(
        LocalDateTime.of(2026, 3, 29, 9, 0),
        berlin,
        GapPolicy.REJECT,
        OverlapPolicy.EARLIER_OFFSET
    );

    assertThat(beforeChange).isEqualTo(
        Instant.parse("2026-03-28T08:00:00Z")
    );

    assertThat(afterChange).isEqualTo(
        Instant.parse("2026-03-29T07:00:00Z")
    );

    assertThat(
        Duration.between(beforeChange, afterChange)
    ).isEqualTo(Duration.ofHours(23));
}
```

**23 giờ giữa hai lần gửi vẫn là “mỗi ngày lúc 09:00”** trong vùng có spring-forward DST. Tương tự, khi fall-back, khoảng cách giữa hai ngày có thể là 25 giờ.

Một test ép mọi occurrence cách nhau đúng 24 giờ sẽ sai requirement nếu lịch là **daily wall time**.

## 27. Integration test database: timezone và due predicate

Unit test resolver có thể pass nhưng database vẫn xử lý sai nếu:
- driver chuyển `Instant` qua JVM default zone không mong muốn;
- schema dùng `TIMESTAMP WITHOUT TIME ZONE` cho mốc tuyệt đối;
- query so local timestamp với `now()` sai timezone;
- `next_attempt_at` không được áp dụng;
- nhiều workers cùng claim job.

Với PostgreSQL Testcontainers, nên kiểm tra:

1. Persist `send_at = 2026-12-01T02:00:00Z`.
2. Đọc lại từ database qua repository đúng bằng cùng `Instant`.
3. Đổi database session timezone giữa UTC và `Asia/Ho_Chi_Minh`.
4. Chứng minh stored instant không thay đổi.
5. Tại T−1 giây: không claim.
6. Tại T: claim thành công đúng một lần.
7. Hai workers đồng thời: không cùng claim.
8. Sau restart: job chưa tới hạn vẫn tồn tại.
9. Sau cancel: không được claim.
10. Nếu `SMTP_ACCEPTED`: không được claim lần nữa.

Không cần SMTP provider thật để kiểm tra timezone persistence và claim logic. Thay sender bằng mock/test gateway; kiểm thử SMTP riêng với sandbox.

### 27.1. Test query dùng Clock hay DB clock?

Có hai thiết kế:

- Application truyền `clock.instant()` vào query, thuận tiện cho test deterministic.
- Database dùng `CURRENT_TIMESTAMP` làm nguồn thời gian claim.

Cả hai có thể dùng, nhưng phải chọn một nguồn **thống nhất** cho điều kiện due và lease. Nếu dùng DB clock, integration tests cần có cách kiểm soát lịch bằng dữ liệu tương đối hoặc test clock strategy phù hợp; không trộn application now với DB now một cách khó quan sát.

### 27.2. Clock skew giữa nodes

Nếu worker A nhanh hơn thời gian thực 3 phút, nó có thể gửi email trước `sendAt`. Đồng bộ thời gian NTP/PTP phù hợp và quan sát clock skew là yêu cầu hạ tầng.

Đối với hệ thống nhạy cảm:
- dùng DB server time cho claim;
- cấu hình time synchronization cho tất cả nodes;
- có giám sát drift;
- ghi `claimedAt`/`sentAt` để audit.

## 28. Idempotency của lịch lặp và nhiều replicas

Một lịch chạy hàng ngày có thể được tính đồng thời bởi nhiều scheduler instances.

Không đủ nếu chỉ có:

```java
@Scheduled(cron = "0 0 9 * * *", zone = "Asia/Ho_Chi_Minh")
public void sendDigest() {
    mailSender.send(...);
}
```

Với ba pods, method có thể chạy trên cả ba, tạo ba submissions.

### 28.1. Sinh job với business key duy nhất

```text
tenantId + scheduleId + occurrenceLocalDate + slot
```

Ví dụ:

```text
tenant-9|digest-weekdays|2026-12-01|single
```

DB unique constraint bảo đảm cùng một occurrence được tạo một lần theo policy. Sau đó due dispatcher claim job atomic để chỉ một worker thực hiện attempt.

### 28.2. Idempotency không có nghĩa SMTP tự dedupe

Cùng `messageKey` trong custom header không khiến SMTP tự chặn email trùng. Idempotency ở database hạn chế duplicate **job creation/claim**; lỗi mạng `UNKNOWN` sau SMTP DATA vẫn cần reconciliation.

### 28.3. Bù lịch sau downtime

Nếu scheduler tắt trong ba ngày:
- tính các occurrence chưa tạo từ recurrence rule và local date range;
- áp dụng catch-up policy;
- chỉ insert những occurrence còn hợp lệ;
- không gửi 3 ngày báo cáo cũ nếu chúng không còn giá trị;
- dùng unique key để việc catch-up có thể chạy lại an toàn.

Một cron tick không phải event log bền vững; ứng dụng phải tự thiết kế cơ chế khôi phục.

## 29. Tzdb cập nhật: vì sao ZoneId quan trọng lâu dài?

Quy định DST và timezone có thể thay đổi theo quyết định của từng quốc gia. Java runtime sử dụng tzdb để chuyển local time ↔ instant.

Nếu một lịch lặp được lưu trước nhiều tháng:
- tzdb có thể được cập nhật;
- UTC instant của occurrence chưa tới có thể thay đổi;
- ZoneId vẫn diễn tả “09:00 giờ địa phương”;
- một offset cố định được lưu lúc tạo lịch không thể phản ánh quy tắc mới.

### 29.1. Phân biệt hai hợp đồng thời gian

**Hợp đồng A: Mốc tuyệt đối**
> Gửi tại 2027-01-01T02:00:00Z.

Khi tzdb cập nhật, thường **không tính lại** instant đã chốt.

**Hợp đồng B: Giờ địa phương**
> Gửi 09:00 mỗi ngày theo giờ chính thức của khu vực.

Khi quy tắc vùng thay đổi, occurrence tương lai cần dùng quy tắc mới. Nếu đã materialize xa tương lai, có thể cần **recalculate** những job chưa accepted/đang pending.

### 29.2. Multi-region dùng nhiều phiên bản tzdb

Nếu pod A chạy JDK với tzdb cũ, pod B dùng tzdb mới, cùng một local future time có thể resolve ra hai instants khác nhau.

Biện pháp:
- thống nhất JDK/tzdb version trong rollout;
- ghi schedule version hoặc resolved-at metadata;
- dùng một service chính cho materialization;
- audit khi thay đổi rule;
- test những timezone quan trọng sau nâng cấp runtime.

Không nên chỉ dựa vào `ZoneId.of` để cho rằng mọi pod ở mọi thời điểm dùng cùng phiên bản rules.

## 30. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Email gửi lệch 7 giờ | LocalDateTime bị coi là UTC | Resolve bằng ZoneId người dùng trước khi lưu Instant |
| Lịch Berlin lệch một giờ vào mùa hè | Chỉ lưu `+01:00` | Lưu `Europe/Berlin` và tính occurrence theo ngày local |
| Gửi hai lần ở ngày DST fall-back | Cron/logic không có overlap policy | Chọn EARLIER/LATER hoặc unique occurrence key |
| Bỏ qua email vì 02:30 không tồn tại | Không có gap policy | REJECT/SKIP/SHIFT rõ ràng |
| Đổi timezone UI làm dời lịch | UI dùng local string làm nguồn sự thật | Giữ Instant nếu chỉ đổi cách hiển thị |
| Lịch mỗi ngày bị cách đúng 24h nhưng lệch giờ địa phương | Cộng Duration(24h) cho wall-clock schedule | Sinh từ local date + ZoneId |
| Cron chạy nhiều bản | Nhiều pods cùng chạy `@Scheduled` | Durable job + unique key/distributed owner |
| Missed run sau deploy | Cron không tự bù kỳ bị bỏ | Catch-up materialization |
| Job mất khi restart | Chỉ dùng timer hoặc memory queue | Durable outbox/database |
| Gửi trước giờ mong muốn | App clock fast hoặc query thiếu due predicate | Clock sync, authoritative time, SQL condition |
| Retry gửi sau khi link hết hạn | Không có `expiresAt` | Deadline/expiration policy |
| SMTP accepted muộn dù sendAt đúng | Provider/network/backlog | Phân biệt scheduled vs accepted; giám sát lag |
| Lịch hủy vẫn gửi | Race với worker claim | Conditional update, version/lease, recheck |
| UTC trong DB khác UI | Database session timezone thay đổi hiển thị | Lưu Instant và ZoneId riêng, format tại UI |
| Timezone parse lỗi rồi fallback UTC | Error handling không rõ | Trả validation error |
| User chọn 09:00 tại nơi đang du lịch | Suy timezone từ browser | Hiển thị và xác nhận ZoneId |
| Cùng daily digest tạo hai jobs | Thiếu occurrence idempotency | Unique(schedule,date,slot) |
| Provider A timeout rồi thử B | Không giữ UNKNOWN | Reconcile, không retry mù |
| Log timestamp khó đối chiếu | Tự format local không kèm offset/zone | Structured UTC timestamps và schedule zone metadata |
| Sau nâng cấp JDK lịch tương lai đổi | tzdb rules thay đổi | Quản lý tzdb/version và future occurrence recalculation |

## 31. Checklist thiết kế lịch gửi đa múi giờ

### 31.1. Input và ý định

- [ ] UI/API xác định timezone rõ ràng, ưu tiên IANA `ZoneId`.
- [ ] Phân biệt lịch tại instant cố định với lịch theo giờ địa phương.
- [ ] Lưu local input, zone ID và gap/overlap policies khi cần.
- [ ] Không đoán zone từ server, email address hoặc locale.
- [ ] Kiểm tra giới hạn thời gian, recipient permission và consent.
- [ ] Có chính sách cho ngày không tồn tại/trùng do DST.
- [ ] Có quiet-hours/holiday rules nếu nghiệp vụ yêu cầu.

### 31.2. Persistence và dispatch

- [ ] `send_at` và `next_attempt_at` lưu như absolute instants.
- [ ] ZoneId được lưu ở cột riêng.
- [ ] Không dùng local timestamp đơn độc làm due predicate.
- [ ] Có unique business/occurrence idempotency key.
- [ ] Atomic claim với lease/fencing nếu có nhiều workers.
- [ ] SMTP call không giữ DB transaction dài.
- [ ] Có deadline, cancellation/reschedule và lịch sử audit.
- [ ] Các trạng thái retry/unknown/dead-letter được định nghĩa rõ.

### 31.3. Recurrence và cron

- [ ] Mỗi occurrence được tính từ local date/time theo ZoneId.
- [ ] Không cộng 24h UTC cho lịch “mỗi ngày cùng giờ”.
- [ ] Cron có `zone` được xác định.
- [ ] Không tạo một scheduler bean vô hạn cho từng user.
- [ ] Có catch-up policy khi downtime.
- [ ] Tránh nhiều pods tạo cùng occurrence.
- [ ] Quy định rõ overlap: một hay hai lần.
- [ ] Có quy trình xử lý tzdb upgrade và materialized future jobs.

### 31.4. Kiểm thử và vận hành

- [ ] Inject `Clock` và dùng fixed/mutable clock trong tests.
- [ ] Test Việt Nam UTC+07 và ít nhất một timezone có DST.
- [ ] Test gap, overlap và các ngày xung quanh DST.
- [ ] Test persisted Instant qua DB session timezones khác nhau.
- [ ] Test due boundary T−1s/T và không gửi sớm.
- [ ] Test restart, catch-up và concurrency.
- [ ] Test cancel/reschedule race, expiration và retry.
- [ ] Theo dõi schedule lag, SMTP submit time và delivery events.
- [ ] Không kết luận delivered chỉ từ `JavaMailSender.send(...)`.

## 32. Bài tập thực hành

### Bài 1 — Một lần gửi tại Việt Nam

Cho `localSendTime=2026-12-01T09:00` và `zone=Asia/Ho_Chi_Minh`. Tính `Instant`, lưu DB rồi hiển thị lại bằng ZoneId gốc.

### Bài 2 — Hai timezone cùng một ngày

Hai người cùng chọn 09:00 ngày 01/12/2026, một ở Berlin và một ở Việt Nam. Xác định hai `sendAt` UTC khác nhau và giải thích vì sao không thể chỉ lưu `LocalDateTime`.

### Bài 3 — Offset so với ZoneId

So sánh `ZoneOffset.ofHours(1)` và `ZoneId.of("Europe/Berlin")` cho lịch lặp ngày 28/03 và 29/03/2026. Chứng minh offset cố định làm lệch giờ địa phương sau DST.

### Bài 4 — DST gap

Yêu cầu gửi 02:30 Berlin ngày 29/03/2026. Thử `REJECT`, `NEXT_VALID_TIME`, `SHIFT_BY_GAP` và ghi rõ các instant dự kiến.

### Bài 5 — DST overlap

Yêu cầu gửi 02:30 Berlin ngày 25/10/2026. Tạo hai instants hợp lệ và chọn một theo `EARLIER_OFFSET`/`LATER_OFFSET`; test tránh gửi hai lần ngoài ý muốn.

### Bài 6 — Clock.fixed

Viết `DuePredicate` với `Clock` inject. Test T−1s chưa due, T chính xác due, T+1s vẫn due.

### Bài 7 — Lịch mỗi ngày 09:00

Tạo các occurrences cho một tuần trước/sau DST ở Berlin. Assert local time của tất cả luôn 09:00 và khoảng UTC giữa hai ngày đôi khi 23/25 giờ.

### Bài 8 — Lịch mỗi 24 giờ

Tạo schedule khác: “24 giờ một lần từ Instant đầu”. So sánh kết quả với daily wall time và xác định requirement nào chọn mỗi kiểu.

### Bài 9 — PostgreSQL TIMESTAMPTZ

Lưu một `Instant` vào `TIMESTAMPTZ`, đọc lại với database session timezone UTC và `Asia/Ho_Chi_Minh`. Xác nhận instant không đổi, nhưng string hiển thị có thể khác.

### Bài 10 — Hủy một lần gửi

Tạo job `PENDING`, hủy trước `sendAt`, rồi chạy due dispatcher. Xác nhận `CANCELLED` không thể claim. Thử trường hợp worker claim đồng thời và xác định API trả kết quả nào.

### Bài 11 — Daily digest nhiều replicas

Dùng `@Scheduled(cron, zone)` tạo job theo business date. Chạy hai instances và dùng unique `(tenant, schedule, localDate, slot)` để bảo đảm chỉ một occurrence được tạo.

### Bài 12 — Catch-up sau downtime

Ứng dụng tắt 3 ngày. Thiết kế policy gửi bù cho báo cáo tuần, bỏ qua thông báo đã quá hạn và không tạo job trùng khi catch-up chạy hai lần.

### Bài 13 — Quiet hours

Một user ở New York chỉ muốn nhận thông báo 09:00–20:00. Job đến hạn lúc 23:30 local. Tính next eligible local time và resolve qua ZoneId; test cả ngày DST.

### Bài 14 — Deadline của token

Email xác minh có token hết hạn 15 phút sau khi tạo. User đặt lịch gửi sau một giờ. Thiết kế validation hoặc cơ chế tạo token gần lúc submission để email không chứa token hết hạn.

### Bài 15 — Multi-tenant timezone

Tenant A có zone `Asia/Tokyo`, tenant B `America/New_York`. Viết resolver chọn ZoneId theo cấu hình đã được xác thực, không cho client tùy ý lấy zone của tenant khác.

### Bài 16 — Retry và UNKNOWN

Giả lập SMTP timeout sau DATA vào giờ gửi đã chọn. Kiểm tra job chuyển `UNKNOWN`, không tự failover/resend, và vẫn giữ `sendAt` gốc để audit.

### Bài 17 — Tzdb update

Một quốc gia đổi luật DST trong khi hệ thống đã materialize lịch lặp ba tháng tới. Thiết kế quy trình xác định jobs nào phải tính lại, jobs nào giữ Instant, và cách ghi audit/version.

### Bài 18 — Quan sát lịch gửi

Thiết kế metrics cho `dueAt → claimedAt → smtpAcceptedAt → deliveredAt`, tách scheduler lag khỏi provider delivery lag. Đề xuất alert khi job đến hạn nhưng không được claim trong SLA.

## 33. Tổng kết

**Múi giờ của lịch gửi** là phần của **business contract**, không chỉ là cách format ngày giờ khi hiển thị. Trong Spring Framework Mail, `JavaMailSender` thực hiện submission, còn ứng dụng phải quyết định thời điểm gửi theo đúng ý định người dùng trước khi SMTP được gọi.

Các nguyên tắc cần nhớ:

1. **Lưu `Instant` cho một lần gửi cụ thể**, và lưu `ZoneId`/local time khi cần giải thích hoặc tiếp tục lịch theo giờ địa phương.
2. **`LocalDateTime` không có timezone**; không được tự coi là UTC hoặc timezone của server.
3. **IANA ZoneId khác offset cố định**: quy tắc DST và thay đổi luật múi giờ có thể làm offset tương lai khác hiện tại.
4. **DST gap/overlap phải có policy rõ ràng**: từ chối, bỏ occurrence, chuyển tới giờ hợp lệ hoặc chọn một trong hai lần xuất hiện.
5. **Lịch lặp theo wall time** phải tính mỗi occurrence từ local date/time + ZoneId; không chỉ cộng 24 giờ vào UTC instant.
6. **`@Scheduled(cron, zone)` là trigger**, không thay thế durable scheduling, catch-up và idempotency khi nhiều replicas.
7. **Persist job trong outbox**, atomic claim theo `send_at <= now` và chỉ submit khi đủ điều kiện; không dùng sleep hoặc in-memory timer cho lịch dài quan trọng.
8. **Phân biệt `sendAt`, `nextAttemptAt` và `expiresAt`** để retry không gửi quá sớm hoặc sau deadline.
9. **Không nhầm lịch với delivery**: SMTP accepted có thể chậm hơn sendAt và không chứng minh email vào Inbox.
10. **Kiểm thử bằng Clock và timezone có DST**, kiểm chứng database, restart, concurrency, cancellation và thay đổi tzdb.

Khi biểu diễn rõ **ý định giờ địa phương**, **mốc UTC để xử lý** và **trạng thái thực tế của SMTP submission**, ứng dụng Spring có thể gửi đúng lịch trên nhiều quốc gia, hạn chế sai lệch DST và phục hồi đáng tin cậy sau sự cố.
