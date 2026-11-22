# Chọn kiểu ngày giờ theo ý nghĩa nghiệp vụ trong Java 8

Một lỗi thiết kế phổ biến là dùng **một kiểu ngày giờ duy nhất** cho mọi thông tin: ngày sinh, giờ mở cửa, lịch hẹn, thời điểm thanh toán, kỳ hóa đơn và thời lượng thực hiện. Dù các giá trị đều “liên quan đến thời gian”, chúng có **ý nghĩa nghiệp vụ khác nhau**. Việc chọn sai kiểu có thể khiến ngày sinh dịch sang ngày hôm trước khi đổi múi giờ, lịch họp bị lệch khi chuyển giờ mùa hè (DST), kỳ thanh toán bị hiểu thành một timestamp, hoặc thời lượng “một ngày” vô tình bị coi là đúng 24 giờ.

Từ Java 8, gói **`java.time`** cung cấp các kiểu chuyên biệt, bất biến và có hợp đồng rõ: `LocalDate`, `LocalTime`, `LocalDateTime`, `Instant`, `OffsetDateTime`, `ZonedDateTime`, `YearMonth`, `MonthDay`, `Duration`, `Period`, `ZoneId`, `ZoneOffset` và `Clock`. Những API này **vẫn được sử dụng trong Java hiện hành**, không phải cách làm đã lỗi thời.

**Nguyên tắc trung tâm:** chọn kiểu theo **điều mà dữ liệu biểu thị**, trước khi nghĩ tới định dạng hiển thị, cơ sở dữ liệu, JSON hay phương thức chuyển đổi. Đừng thêm múi giờ vào một giá trị chỉ là ngày lịch; cũng đừng xóa múi giờ của một sự kiện phải diễn ra ở một thời điểm xác định trên toàn thế giới.

## 1. Bốn câu hỏi phải trả lời trước khi chọn kiểu

1. **Dữ liệu là ngày/giờ trên lịch hay một thời điểm trên dòng thời gian?** “Ngày sinh 6/11” là khái niệm lịch; “giao dịch hoàn tất lúc 02:30 UTC” là sự kiện tuyệt đối.
2. **Múi giờ hoặc quy tắc vùng có thuộc ý nghĩa nghiệp vụ không?** “Họp lúc 09:30 tại Hà Nội” có thể cần `ZoneId`; “09:30” cho một đồng hồ báo thức cục bộ chưa nhất thiết là timestamp.
3. **Giá trị cần biểu diễn thời lượng thực tế hay lượng lịch?** “Timeout 90 phút” là `Duration`; “gia hạn một tháng lịch” là `Period` hoặc phép `plusMonths`.
4. **Cần giữ gì khi lưu và truyền dữ liệu?** Một `Instant` xác định thời điểm nhưng không ghi nhớ nơi sự kiện được tạo; một `OffsetDateTime` có offset nhưng không chứa toàn bộ quy tắc chuyển giờ của khu vực; một `ZonedDateTime` có ZoneId và thông tin thời điểm sau khi được giải quyết.

Trả lời các câu hỏi đó **trước khi** chọn kiểu dữ liệu của entity, API hoặc cột database. Không nên chọn `String` chỉ vì màn hình hiển thị một chuỗi “06/11/2026 09:30”.

## 2. Bảng chọn kiểu nhanh theo tình huống

| Ý nghĩa nghiệp vụ | Kiểu Java 8 nên cân nhắc | Vì sao |
| --- | --- | --- |
| Ngày sinh đầy đủ, ngày nghỉ, ngày hóa đơn, ngày giao dự kiến | `LocalDate` | Chỉ là ngày theo lịch, **không** chứa thời điểm hay múi giờ |
| Giờ mở cửa 09:30, giờ nhắc nhở theo đồng hồ địa phương | `LocalTime` | Chỉ là giờ trong một ngày, không gắn ngày hoặc vùng |
| Ngày và giờ trên đồng hồ, chưa xác định vùng | `LocalDateTime` | Chứa ngày + giờ nhưng **chưa** là thời điểm toàn cầu |
| Thời điểm event thực sự xảy ra, createdAt, processedAt, loggedAt | `Instant` | Điểm trên trục thời gian; dễ so sánh/trao đổi giữa các vùng |
| Timestamp API có độ lệch `+07:00` hoặc `Z` | `OffsetDateTime` | Ngày giờ gắn **offset cố định**; có thể xác định một Instant |
| Lịch họp 09:30 theo quy tắc vùng `Europe/Berlin` | `ZonedDateTime` hoặc `LocalDateTime + ZoneId` | Cần quy tắc vùng, kể cả DST; lựa chọn phụ thuộc chính sách lịch hẹn |
| Kỳ hóa đơn 2026-11, tháng lương, tháng báo cáo | `YearMonth` | Tháng và năm, không ngụ ý ngày 1 hoặc giờ 00:00 |
| Ngày kỷ niệm 29/02 lặp theo năm | `MonthDay` | Tháng/ngày không có năm; cần chính sách cho năm không nhuận |
| Năm tài chính chỉ biểu diễn năm `2026` | `Year` | Không cần tự đặt ngày 1/1 để biểu diễn năm |
| Timeout 90 phút, thời gian xử lý 250 ms, TTL 24 giờ | `Duration` | Thời lượng theo giây/nano trên dòng thời gian |
| Gia hạn 1 tháng lịch, chênh lệch 2 năm 3 tháng | `Period` | Lượng ngày/tháng/năm theo lịch, không cố định số giây |
| Danh tính vùng như `Asia/Ho_Chi_Minh` | `ZoneId` | Chứa vùng và cho phép áp dụng quy tắc múi giờ của vùng |
| Độ lệch cố định `+07:00` | `ZoneOffset` | Không mang toàn bộ lịch sử/quy tắc DST của một vùng |
| Muốn test “hôm nay” hoặc “bây giờ” một cách lặp lại | `Clock` | Nguồn thời gian có thể tiêm vào, ví dụ `Clock.fixed` |
| Chỉ có giờ và offset, chẳng hạn `09:30+07:00` | `OffsetTime` | Có giờ + offset nhưng **không có ngày**, nên không là Instant |

**Đừng coi bảng là luật cứng** cho mọi hệ thống. Chẳng hạn một cuộc hẹn ở thời điểm xác định có thể lưu `Instant` **kèm ZoneId gốc** để vừa giữ thời điểm thực thi vừa giữ ngữ cảnh hiển thị. Một lịch hẹn trong tương lai phải giữ *giờ trên đồng hồ địa phương* thường cần thêm ngày/giờ cục bộ và ZoneId để tính toán lại theo chính sách khi quy tắc DST thay đổi.

## 3. LocalDate: khi người dùng quan tâm ngày, không quan tâm thời điểm

`LocalDate` lưu năm, tháng, ngày theo lịch ISO-8601; ví dụ `2026-11-06`. Nó **không chứa giờ, offset hay timezone**.

Ứng dụng điển hình:

- Ngày sinh, ngày tốt nghiệp, ngày hóa đơn, ngày giao hàng dự kiến theo địa phương.
- Ngày nghỉ lễ của một khu vực khi hệ thống đã xác định lịch áp dụng.
- Hạn cuối được diễn đạt “đến hết ngày 30/11” — cần bổ sung quy tắc giờ kết thúc nếu chuyển thành một Instant để thực thi.
- Chọn ngày trên lịch trong giao diện người dùng.

Ví dụ:

```java
// Đoạn minh họa Java 8, đặt trong phương thức có import java.time.*.
LocalDate dueDate = LocalDate.of(2026, 11, 6);
LocalDate nextMonth = dueDate.plusMonths(1);
boolean overdueByDate = LocalDate.of(2026, 11, 7).isAfter(dueDate);
```

Đừng tự biến ngày sinh thành `Instant` tại **00:00 UTC** rồi hiển thị ở tất cả múi giờ. Cùng một Instant có thể rơi vào ngày trước đó đối với người ở vùng giờ âm. Nếu nghiệp vụ chỉ là ngày sinh, **giữ LocalDate như ngày lịch**.

Nếu một hạn thanh toán hết hiệu lực vào cuối ngày ở Hà Nội, bạn cần định nghĩa **ZoneId**, ví dụ `Asia/Ho_Chi_Minh`, rồi xác định **ngưỡng bắt đầu của ngày tiếp theo** trong vùng đó. Đó là bước chuyển đổi ở ranh giới thực thi; không biến bản thân ngày hạn thành một timestamp giả.

## 4. LocalTime: khi nghiệp vụ chỉ nói tới giờ trong ngày

`LocalTime` phù hợp cho “cửa hàng mở lúc 09:30”, “nhắc uống nước lúc 15:00”, “giờ bắt đầu một ca làm theo đồng hồ địa phương”. Nó có giờ/phút/giây/nano nhưng không có ngày hoặc vùng.

```java
LocalTime opens = LocalTime.of(9, 30);
LocalTime closes = LocalTime.of(18, 0);
boolean isAfterOpen = LocalTime.of(10, 0).isAfter(opens);
```

Lưu ý:

- `LocalTime` không thể tự trả lời “09:30 đó là khi nào theo UTC?”, vì thiếu **ngày và vùng**.
- Giờ mở cửa **định kỳ theo địa phương** thường nên lưu `LocalTime` cùng ZoneId của địa điểm, cộng quy tắc ngày trong tuần, ngày nghỉ và lịch đặc biệt.
- Một ca **qua nửa đêm** như 22:00–06:00 không thể dùng phép so sánh `start < now < end` đơn giản; phải xác định ngày tương ứng của điểm kết thúc.
- Nếu một vùng có DST, có ngày một số giờ không tồn tại hoặc xảy ra hai lần. Quy tắc xử lý phải được xác định khi kết hợp ngày + LocalTime + ZoneId.

`OffsetTime` có thể lưu `09:30+07:00`, nhưng **không có ngày**, nên không dùng làm một thời điểm thực thi tuyệt đối. Với lịch mở cửa lặp lại ở vùng có DST, một offset cố định không thay thế cho ZoneId.

## 5. LocalDateTime: ngày và giờ tường minh, nhưng chưa biết Instant

`LocalDateTime` kết hợp `LocalDate` và `LocalTime`. Ví dụ `2026-11-06T09:30` nói rõ đồng hồ hiển thị gì nhưng **không nói đang ở múi giờ nào**.

```java
LocalDateTime appointmentWall =
    LocalDateTime.of(2026, 11, 6, 9, 30);
```

Có thể dùng cho:

- Thời gian người dùng chọn trên màn hình **trước khi** biết/áp dụng vùng.
- Lịch hẹn dân sự trong tương lai khi hệ thống lưu **giờ trên đồng hồ mong muốn** và giữ ZoneId ở một trường riêng.
- Ngày giờ “local” trong một hệ thống đã có ngữ cảnh timezone rõ và được quản lý chặt.

**Không dùng riêng LocalDateTime để ghi lại sự kiện đã diễn ra ở nhiều vùng**. Hai `LocalDateTime` đều là 09:30 ở Hà Nội và Berlin **không** biểu thị cùng một Instant. Nếu server mặc định có múi giờ khác client, việc tùy ý gọi `atZone(ZoneId.systemDefault())` có thể đổi ý nghĩa dữ liệu.

Muốn chuyển sang Instant, phải có vùng hoặc offset phù hợp và **chính sách xử lý DST**:

```java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime meeting = appointmentWall.atZone(zone);
Instant startInstant = meeting.toInstant();
```

Với `Asia/Ho_Chi_Minh` vào ngày trong ví dụ, kết quả rõ ràng. Với vùng có DST, một giờ địa phương có thể **vắng mặt hoặc lặp lại**, nên không được cho rằng `atZone` luôn là phép chuyển đổi 1–1.

## 6. Instant: điểm trên dòng thời gian dùng cho sự kiện thực tế

`Instant` biểu diễn một **thời điểm** trên dòng thời gian, thường được trao đổi dưới dạng ISO-8601 UTC với `Z`:

```java
Instant completedAt =
    Instant.parse("2026-11-06T02:30:00Z");
```

Dùng cho:

- Thời điểm thanh toán đã hoàn tất; timestamp tạo/sửa record.
- Log event từ nhiều service hoặc nhiều múi giờ.
- Đo khoảng cách thời gian giữa các sự kiện bằng `Duration.between`.
- Mốc hết hạn theo thời lượng thực tế: `Instant expiresAt = now.plus(Duration.ofHours(2))`.

Một Instant **không ghi nhớ** người dùng ở vùng nào, đồng hồ local khi nhập là mấy giờ hay múi giờ của buổi họp. Muốn hiển thị:

```java
ZonedDateTime display = completedAt.atZone(
    ZoneId.of("Asia/Ho_Chi_Minh"));
```

Do đó với một event xảy ra tại một thời điểm, `Instant` là cách biểu diễn cốt lõi hợp lý. Nếu cần lưu **bối cảnh địa phương ban đầu**, lưu thêm ZoneId hay offset theo nhu cầu báo cáo.

**Chú ý khi tích hợp dữ liệu số:** epoch seconds, epoch milliseconds và nanoseconds là **ba đơn vị khác nhau**. Không dùng `Instant.ofEpochMilli(x)` khi `x` thực ra là giây. Một lỗi đơn vị thường đẩy timestamp sang năm hoàn toàn sai dù kiểu Java vẫn hợp lệ.

## 7. OffsetDateTime và ZonedDateTime: offset không phải toàn bộ múi giờ

### OffsetDateTime

`OffsetDateTime` chứa ngày + giờ + **ZoneOffset cố định** so với UTC. Ví dụ:

```java
OffsetDateTime apiTime =
    OffsetDateTime.parse("2026-11-06T09:30:00+07:00");
Instant sameMoment = apiTime.toInstant();
```

Nó hợp với API yêu cầu một timestamp có offset, ví dụ `2026-11-06T09:30:00+07:00`. Từ offset và ngày giờ, có thể xác định một Instant.

Nhưng offset `+01:00` không tương đương với vùng `Europe/Berlin` trong mọi ngày: Berlin có thể áp dụng `+01:00` hoặc `+02:00` tùy quy tắc DST. Offset là **độ lệch**, không phải danh tính vùng với quy tắc lịch sử/tương lai.

### ZonedDateTime

`ZonedDateTime` chứa ngày giờ địa phương, offset đã được giải quyết và **ZoneId** như `Europe/Berlin` hoặc `Asia/Ho_Chi_Minh`. Nó thích hợp khi ứng dụng cần hiển thị, tính toán hoặc giải quyết lịch hẹn **theo quy tắc của khu vực**.

```java
ZoneId berlin = ZoneId.of("Europe/Berlin");
ZonedDateTime localEvent =
    LocalDateTime.of(2026, 10, 25, 2, 30)
        .atZone(berlin);
```

Ví dụ ở Berlin này rơi vào ngày đồng hồ lùi, nên 02:30 xuất hiện **hai lần**. `atZone` chọn một offset theo quy tắc mặc định; ứng dụng đặt lịch có thể cần hỏi người dùng chọn lần sớm hay muộn.

**Quyết định lưu lịch hẹn trong tương lai:**

- Nếu đã cam kết một **thời điểm chính xác** (ví dụ event đã bán vé với Instant cố định), lưu Instant và lưu thêm ZoneId để hiển thị khi cần.
- Nếu cam kết “đúng **09:30 giờ địa phương** tại chi nhánh Berlin” trong tương lai, giữ **LocalDateTime + ZoneId** cùng chính sách resolve DST. Nếu quy tắc nhà nước thay đổi, có thể cần tính lại Instant từ giờ dân sự đã đặt.
- Nếu phải giữ cả **offset người dùng đã xác nhận**, lưu offset/Instant tương ứng và các trường lịch hẹn cần thiết. Không đánh đổi ngầm một cam kết lấy một cam kết khác.

Các quy tắc vùng được cung cấp bởi dữ liệu tzdb của JDK và có thể thay đổi khi luật địa phương hoặc cơ sở dữ liệu múi giờ thay đổi. Do vậy dữ liệu có thể được diễn giải khác khi chính sách/timezone data thay đổi; hãy xác định nghĩa cần bảo toàn cho nghiệp vụ.

## 8. Ví dụ hoàn chỉnh 1 — Chọn nhiều kiểu cho những nhu cầu khác nhau

Tệp **`BusinessTimeTypesDemo.java`** chạy độc lập trên Java 8, minh họa ngày hóa đơn, kỳ báo cáo, sinh nhật lặp, giờ mở cửa, giờ hẹn, Instant, offset, thời lượng, lượng lịch và Clock cố định dùng trong test.

```java
import java.time.*;
import java.util.*;

public class BusinessTimeTypesDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    public static void main(String[] args) {
        LocalDate invoiceDate = LocalDate.of(2026, 11, 6);
        YearMonth billingPeriod = YearMonth.from(invoiceDate);
        MonthDay birthday = MonthDay.of(2, 29);
        LocalTime storeOpens = LocalTime.of(9, 30);
        LocalDateTime meetingWall =
            LocalDateTime.of(invoiceDate, storeOpens);

        ZoneId businessZone =
            ZoneId.of("Asia/Ho_Chi_Minh");
        ZonedDateTime meeting =
            meetingWall.atZone(businessZone);
        Instant meetingInstant = meeting.toInstant();

        OffsetDateTime apiTimestamp =
            meetingInstant.atOffset(ZoneOffset.UTC);
        OffsetTime localOffsetTime =
            OffsetTime.of(storeOpens, ZoneOffset.ofHours(7));

        Period calendarTerm =
            Period.between(LocalDate.of(2026, 10, 6),
                           invoiceDate);
        Duration timeout = Duration.ofMinutes(90);

        Clock fixed = Clock.fixed(
            Instant.parse("2026-11-06T02:30:00Z"),
            businessZone);
        LocalDate todayForTest = LocalDate.now(fixed);

        check(meetingInstant.equals(
            Instant.parse("2026-11-06T02:30:00Z")),
            "instant");
        check(billingPeriod.equals(
            YearMonth.of(2026, 11)), "month");
        check(calendarTerm.equals(
            Period.ofMonths(1)), "period");
        check(todayForTest.equals(invoiceDate), "clock");

        System.out.println("invoiceDate=" + invoiceDate);
        System.out.println("billingPeriod=" + billingPeriod);
        System.out.println("birthday=" + birthday);
        System.out.println("storeOpens=" + storeOpens);
        System.out.println("meetingWall=" + meetingWall);
        System.out.println("meeting=" + meeting);
        System.out.println("instant=" + meetingInstant);
        System.out.println("apiTimestamp=" + apiTimestamp);
        System.out.println("localOffsetTime=" + localOffsetTime);
        System.out.println("calendarTerm=" + calendarTerm);
        System.out.println("timeout=" + timeout);
        System.out.println("todayForTest=" + todayForTest);
        System.out.println("PASS");
    }
}
```

Chạy trên JDK 8 trở lên:

```bash
javac -encoding UTF-8 BusinessTimeTypesDemo.java
java BusinessTimeTypesDemo
```

Khi dùng JDK mới, có thể xác minh mã chỉ gọi API Java 8:

```bash
javac --release 8 -encoding UTF-8 BusinessTimeTypesDemo.java
java BusinessTimeTypesDemo
```

**Stdout đã kiểm chứng:**

```text
invoiceDate=2026-11-06
billingPeriod=2026-11
birthday=--02-29
storeOpens=09:30
meetingWall=2026-11-06T09:30
meeting=2026-11-06T09:30+07:00[Asia/Ho_Chi_Minh]
instant=2026-11-06T02:30:00Z
apiTimestamp=2026-11-06T02:30Z
localOffsetTime=09:30+07:00
calendarTerm=P1M
timeout=PT1H30M
todayForTest=2026-11-06
PASS
```

**Giải thích:**

- `invoiceDate` là LocalDate nên **không có giờ**.
- `billingPeriod` là YearMonth, có chính xác nghĩa “kỳ 11/2026”, không lén đặt ngày đầu tháng.
- `birthday` là MonthDay; 29/02 là giá trị hợp lệ cho một ngày kỷ niệm lặp **theo quy tắc do nghiệp vụ định nghĩa**. Năm không nhuận phải có chính sách xử lý riêng.
- `meetingWall` mới chỉ là ngày giờ dân sự; khi áp dụng ZoneId của chi nhánh, `meeting` mới xác định được một Instant.
- Instant của 09:30 tại vùng ví dụ bằng 02:30Z; biểu diễn `OffsetDateTime` UTC của cùng Instant cho thấy offset `Z`.
- `calendarTerm=P1M` là **một tháng lịch**; `timeout=PT1H30M` là **90 phút thực tế**.
- `Clock.fixed` cho phép test `LocalDate.now(fixed)` có đầu ra ổn định, không phụ thuộc ngày hiện tại khi chạy test.

Đây là ví dụ các kiểu khác nhau cùng xuất hiện hợp lý trong một mô hình nghiệp vụ, không phải khuyến nghị lưu toàn bộ những trường này cho mọi entity.

## 9. YearMonth, MonthDay và Year: tránh invent một ngày không có trong nghiệp vụ

### YearMonth

Nếu dữ liệu là “kỳ lương tháng 11/2026”, chọn `YearMonth.of(2026, 11)`. Dùng LocalDate “01/11/2026” có thể khiến các lập trình viên khác lầm tưởng **ngày 1 thực sự có ý nghĩa**, trong khi nó chỉ là giá trị giả để chứa tháng.

Các thao tác điển hình:

```java
YearMonth period = YearMonth.of(2026, 11);
YearMonth next = period.plusMonths(1);
LocalDate first = period.atDay(1);
LocalDate last = period.atEndOfMonth();
```

Chỉ chuyển sang LocalDate khi **cần** ngày đầu/cuối tháng để lập khoảng truy vấn hoặc giải quyết một quy tắc thanh toán.

### MonthDay

`MonthDay.of(2, 29)` có nghĩa “ngày 29/02 không gắn năm”. Có thể dùng làm thông tin kỷ niệm lặp hằng năm, nhưng:

- 29/02 không tồn tại ở mọi năm; cần quy tắc nghiệp vụ: chọn ngày 28/02, 01/03, bỏ năm không nhuận, hay dùng chính sách riêng.
- Không nên tự áp dụng một phép chuyển năm mà không hỏi yêu cầu; các cơ quan/nghiệp vụ có thể có quy định khác nhau.
- Nếu cần **ngày sinh thật đầy đủ**, nên lưu `LocalDate` có năm, không chỉ MonthDay.

### Year

`Year.of(2026)` phù hợp khi dữ liệu thực sự chỉ là **năm**. Nhưng “năm tài chính” có thể bắt đầu từ tháng khác 1, nên một `Year` đơn thuần chưa đủ nếu cần định nghĩa **kỳ tài chính khác năm dương lịch**. Hãy bổ sung quy tắc fiscal period hoặc kiểu domain riêng nếu cần.

## 10. Duration và Period: khác nhau giữa thời gian thực và thời gian lịch

Một yêu cầu “thêm một ngày” có **ít nhất hai nghĩa**:

- **Đúng 24 giờ trôi qua:** `Duration.ofDays(1)` = 86.400 giây; phù hợp TTL, timeout và phép đo elapsed time.
- **Cùng giờ đồng hồ vào ngày lịch tiếp theo:** `Period.ofDays(1)` hoặc `ZonedDateTime.plusDays(1)`; khoảng cách Instant có thể 23, 24 hoặc 25 giờ do DST.

Ví dụ tưởng tượng một lịch hẹn lúc 12:00 ở New York vào ngày trước khi đổi giờ mùa xuân. Sang **ngày lịch tiếp theo**, đồng hồ vẫn 12:00 nhưng chỉ **23 giờ thực tế** đã trôi qua vì đồng hồ nhảy qua một giờ. Ngược lại, cộng 24 giờ thực tế có thể là 13:00 local sau khi chuyển giờ.

| Nhu cầu | Chọn kiểu/phép toán |
| --- | --- |
| “Token hết hạn 90 phút sau khi phát” | `Instant.plus(Duration.ofMinutes(90))` |
| “Bài kiểm tra tối đa 45 giây” | `Duration.ofSeconds(45)` |
| “Đăng ký kéo dài thêm một tháng lịch” | `LocalDate.plusMonths(1)` hoặc `Period.ofMonths(1)` |
| “Dời cuộc hẹn sang đúng 09:00 ngày mai tại cùng vùng” | `ZonedDateTime.plusDays(1)`, kèm DST policy |
| “Đo latency request” | `Duration.between(startInstant, endInstant)` hoặc đồng hồ đo monotonic cho elapsed runtime |
| “Tuổi theo năm/tháng/ngày giữa hai ngày sinh và ngày xét” | `Period.between(startDate, endDate)` |
| “Mở quyền truy cập 24 giờ từ lúc kích hoạt” | `Duration.ofHours(24)` |

**Đừng lấy `Period.ofMonths(1)` đổi sang một số giây cố định**: mỗi tháng có độ dài khác nhau. Tương tự, phép cộng tháng ở ngày cuối tháng có thể điều chỉnh ngày xuống ngày cuối cùng hợp lệ của tháng đích; cần test quy tắc nghiệp vụ.

**Đo hiệu năng và timeout runtime:** `Instant.now()` và system wall clock không bảo đảm monotonic khi đồng hồ hệ thống được điều chỉnh. Với elapsed time bên trong một JVM, `System.nanoTime()` (lấy hiệu, không suy ra epoch) thường phù hợp hơn. Tuy nhiên để lưu timestamp sự kiện, dùng Instant/Clock. Chọn clock theo ý nghĩa đo lường thay vì dùng cùng một đồng hồ cho mọi mục đích.

## 11. Ví dụ hoàn chỉnh 2 — 23 giờ, 24 giờ và 25 giờ

Tệp **`CalendarVsElapsedDemo.java`** kiểm tra DST ở New York năm 2026 và cách xử lý cuối tháng.

```java
import java.time.*;
import java.util.*;

public class CalendarVsElapsedDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    public static void main(String[] args) {
        ZoneId ny = ZoneId.of("America/New_York");

        ZonedDateTime beforeSpring =
            ZonedDateTime.of(
                2026, 3, 7, 12, 0, 0, 0, ny);

        ZonedDateTime calendarNext =
            beforeSpring.plusDays(1);

        ZonedDateTime elapsedNext =
            beforeSpring.plus(Duration.ofHours(24));

        Duration wallElapsed =
            Duration.between(
                beforeSpring.toInstant(),
                calendarNext.toInstant());

        ZonedDateTime beforeFall =
            ZonedDateTime.of(
                2026, 10, 31, 12, 0, 0, 0, ny);

        ZonedDateTime fallCalendarNext =
            beforeFall.plusDays(1);

        Duration fallElapsed =
            Duration.between(
                beforeFall.toInstant(),
                fallCalendarNext.toInstant());

        LocalDate lastDayOfJanuary =
            LocalDate.of(2026, 1, 31);

        LocalDate nextMonth =
            lastDayOfJanuary.plus(
                Period.ofMonths(1));

        check(wallElapsed.equals(
            Duration.ofHours(23)), "spring elapsed");

        check(elapsedNext.toLocalTime().equals(
            LocalTime.of(13, 0)), "24 actual hours");

        check(fallElapsed.equals(
            Duration.ofHours(25)), "fall elapsed");

        check(nextMonth.equals(
            LocalDate.of(2026, 2, 28)),
            "end-of-month rule");

        System.out.println(
            "springStart=" + beforeSpring);
        System.out.println(
            "calendarNext=" + calendarNext);
        System.out.println(
            "elapsedNext=" + elapsedNext);
        System.out.println(
            "calendarElapsed=" + wallElapsed);
        System.out.println(
            "fallCalendarElapsed=" + fallElapsed);
        System.out.println(
            "oneMonthFromJan31=" + nextMonth);
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 CalendarVsElapsedDemo.java
java CalendarVsElapsedDemo
```

Stdout đã kiểm chứng với quy tắc múi giờ 2026 trong JDK dùng để chạy:

```text
springStart=2026-03-07T12:00-05:00[America/New_York]
calendarNext=2026-03-08T12:00-04:00[America/New_York]
elapsedNext=2026-03-08T13:00-04:00[America/New_York]
calendarElapsed=PT23H
fallCalendarElapsed=PT25H
oneMonthFromJan31=2026-02-28
PASS
```

**Phân tích:**

- Ngày 8/3/2026 ở New York đổi giờ mùa xuân: đồng hồ bỏ qua một giờ. `plusDays(1)` giữ 12:00 local nhưng Instant chỉ tăng 23 giờ.
- `plus(Duration.ofHours(24))` tăng đúng 24 giờ thật, vì vậy đồng hồ local hiển thị 13:00 sau khi chuyển sang offset mùa hè.
- Vào lần đổi giờ mùa thu, một ngày lịch 12:00 → 12:00 hôm sau có thể dài 25 giờ.
- `LocalDate.of(2026,1,31).plus(Period.ofMonths(1))` cho 28/02/2026 theo quy tắc điều chỉnh ngày không hợp lệ. Nếu nghiệp vụ “gia hạn 1 tháng” cần ý nghĩa khác, chẳng hạn hết hạn đầu tháng kế tiếp hay ngày cố định, phải viết quy tắc riêng và test.

Đây không phải lý do tránh `Period` hoặc `Duration`, mà là lý do phải **chọn đúng nghĩa** trước khi dùng.

## 12. DST: giờ địa phương có thể không tồn tại hoặc xuất hiện hai lần

Khi định nghĩa một lịch họp “02:30 tại Berlin”, bạn chưa thể chắc chắn có đúng một thời điểm. Ở một số ngày:

- **Gap:** đồng hồ nhảy từ một giờ trước đến một giờ sau; ví dụ 02:30 **không tồn tại**.
- **Overlap:** đồng hồ lùi lại; 02:30 xuất hiện **hai lần**, tương ứng hai offset và hai Instant khác nhau.
- **Normal:** một giờ local tương ứng với một offset hợp lệ.

Java 8 cung cấp `ZoneRules.getValidOffsets(localDateTime)` để kiểm tra:

| Số offset hợp lệ | Ý nghĩa | Quyết định cần có |
| ---: | --- | --- |
| 0 | Gap — giờ local không tồn tại | Từ chối đặt lịch, yêu cầu giờ khác hoặc dịch chuyển có chủ đích |
| 1 | Thời gian bình thường | Có thể resolve thành đúng một Instant |
| 2 | Overlap — giờ local mơ hồ | Chọn offset sớm/muộn hoặc yêu cầu người dùng xác nhận |

`LocalDateTime.atZone(zone)` có **quy tắc mặc định** để resolve: trong gap, nó dịch local time về phía trước tương ứng độ dài gap; trong overlap, nó thường chọn offset sớm hơn theo quy tắc API. Đối với nghiệp vụ có hậu quả thực tế như vé, thanh toán, lịch bay hoặc chạy job chính xác, **đừng để default này vô tình trở thành chính sách doanh nghiệp**.

Có thể sử dụng `ZonedDateTime.ofStrict(localDateTime, offset, zone)` khi muốn bắt buộc một offset thực sự hợp lệ; nó ném `DateTimeException` nếu thông tin không tương thích. Với overlap, có thể dùng `withLaterOffsetAtOverlap()` để chọn lần xuất hiện muộn hơn.

## 13. Ví dụ hoàn chỉnh 3 — kiểm thử gap và overlap ở Berlin

Tệp **`DSTResolutionDemo.java`** minh họa hai trường hợp của năm 2026, với mã assert để phát hiện thay đổi so với kỳ vọng.

```java
import java.time.*;
import java.time.zone.*;
import java.util.*;

public class DSTResolutionDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    public static void main(String[] args) {
        ZoneId berlin = ZoneId.of("Europe/Berlin");

        LocalDateTime gap =
            LocalDateTime.of(2026, 3, 29, 2, 30);

        List<ZoneOffset> gapOffsets =
            berlin.getRules().getValidOffsets(gap);

        ZonedDateTime shifted = gap.atZone(berlin);

        LocalDateTime overlap =
            LocalDateTime.of(2026, 10, 25, 2, 30);

        List<ZoneOffset> offsets =
            berlin.getRules().getValidOffsets(overlap);

        ZonedDateTime earlier = overlap.atZone(berlin);
        ZonedDateTime later =
            earlier.withLaterOffsetAtOverlap();

        Duration difference =
            Duration.between(
                earlier.toInstant(), later.toInstant());

        check(gapOffsets.size() == 0, "spring gap");
        check(shifted.toLocalTime().equals(
            LocalTime.of(3, 30)), "shifted time");
        check(offsets.size() == 2, "autumn overlap");
        check(difference.equals(
            Duration.ofHours(1)), "one-hour ambiguity");

        boolean strictRejected = false;
        try {
            ZonedDateTime.ofStrict(
                gap, ZoneOffset.ofHours(1), berlin);
        } catch (DateTimeException expected) {
            strictRejected = true;
        }
        check(strictRejected, "strict gap rejected");

        System.out.println(
            "gapValidOffsets=" + gapOffsets);
        System.out.println("gapAtZone=" + shifted);
        System.out.println(
            "overlapValidOffsets=" + offsets);
        System.out.println("earlier=" + earlier);
        System.out.println("later=" + later);
        System.out.println("difference=" + difference);
        System.out.println(
            "strictGapRejected=" + strictRejected);
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 DSTResolutionDemo.java
java DSTResolutionDemo
```

Stdout đã kiểm chứng:

```text
gapValidOffsets=[]
gapAtZone=2026-03-29T03:30+02:00[Europe/Berlin]
overlapValidOffsets=[+02:00, +01:00]
earlier=2026-10-25T02:30+02:00[Europe/Berlin]
later=2026-10-25T02:30+01:00[Europe/Berlin]
difference=PT1H
strictGapRejected=true
PASS
```

**Kết luận của ví dụ:**

1. Lúc 02:30 ngày 29/03/2026 không có offset hợp lệ ở Berlin; `atZone` chuyển thành 03:30 theo mặc định, nhưng bài toán đặt lịch có thể muốn **từ chối** thay vì dịch.
2. Lúc 02:30 ngày 25/10/2026 có hai offset `+02:00` và `+01:00`. Cùng ngày/giờ local nhưng hai Instant cách nhau 1 giờ.
3. Dữ liệu `LocalDateTime.of(2026,10,25,2,30)` **không đủ** để quyết định cuộc hẹn nào trong hai thời điểm.
4. `ofStrict` là cách xác minh rằng bộ ba local date-time, offset, zone có hợp lệ hay không.

**Lưu ý về dữ liệu múi giờ:** các ví dụ sử dụng các quy tắc IANA hiện hành được JDK thử nghiệm cung cấp. Nếu pháp luật hoặc tzdb thay đổi trong tương lai, một số offset của một ngày tương lai có thể khác. Khi triển khai hệ thống đặt lịch lâu dài, cần có test với timezone database của phiên bản runtime và chính sách nâng cấp rõ ràng.

## 14. Chuyển đổi giữa các kiểu: chỉ chuyển khi đã đủ ngữ cảnh

Sơ đồ hợp đồng:

```text
LocalDate + LocalTime
        │
        ▼
  LocalDateTime                 chưa là thời điểm tuyệt đối
        │
        ├── + ZoneId + quy tắc resolve DST
        ▼
  ZonedDateTime
        │              └── toLocalDateTime(): mất zone/offset
        ├── toInstant()
        ▼
      Instant ── atZone(zone) ──► ZonedDateTime
        │
        └── atOffset(offset) ──► OffsetDateTime

OffsetDateTime ── toInstant() ──► Instant

YearMonth / MonthDay / Year: là lượng thông tin lịch khác nhau
Period: lượng ngày-tháng-năm
Duration: lượng giây-nanosecond
```

**Không có phép chuyển LocalDateTime → Instant an toàn khi thiếu ZoneId/offset.** Nếu ứng dụng tự thêm timezone hệ thống mà không nêu ra, đó là một giả định nghiệp vụ ẩn có thể sai trên server khác.

### Tính ngày local của một event

Nếu log chứa một `Instant`, câu hỏi “event xảy ra vào ngày nào ở Hà Nội?” phải được trả lời theo ZoneId:

```java
Instant event = Instant.parse("2026-11-06T02:30:00Z");
LocalDate dateInHanoi =
    event.atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
         .toLocalDate();
```

Cùng event có thể rơi vào **ngày lịch khác** ở một ZoneId khác. Điều đó không phải dữ liệu mâu thuẫn; nó là hệ quả của các múi giờ.

### Tính đầu ngày

`LocalDate.atStartOfDay(zone)` trả **thời điểm sớm nhất hợp lệ của ngày đó theo quy tắc vùng**. Không được mặc định kết quả luôn là đúng `00:00` local vì một số vùng có transition đúng lúc nửa đêm. Nếu tạo khoảng thời gian của một ngày để truy vấn timestamp, thường xét:

```java
ZonedDateTime start = day.atStartOfDay(zone);
ZonedDateTime end = day.plusDays(1).atStartOfDay(zone);
// Dùng khoảng [start.toInstant(), end.toInstant()).
```

Khoảng **nửa mở** giúp tránh công thức “23:59:59.999...” phụ thuộc độ chính xác của database và tự xử lý đúng ngày dài/ngắn do DST.

## 15. API, JSON và database: lưu đúng ngữ nghĩa trước khi chọn format

### 15.1. Format hiển thị không phải kiểu dữ liệu

`"06/11/2026"` là một chuỗi định dạng cho người dùng; nó có thể đại diện cho `LocalDate`. Chuỗi `"2026-11-06T09:30:00+07:00"` là một biểu diễn của `OffsetDateTime`. Còn `"2026-11-06T02:30:00Z"` biểu diễn một Instant.

Đừng dùng String trong domain chỉ vì JSON hoặc form là String. Hãy **parse tại ranh giới vào**, xử lý nghiệp vụ bằng kiểu `java.time`, rồi format tại ranh giới ra.

### 15.2. Chọn định dạng máy và định dạng người dùng khác nhau

| Mục đích | Định dạng thường phù hợp |
| --- | --- |
| LocalDate trong API | `2026-11-06` (ISO local date) |
| YearMonth trong API | `2026-11` |
| Instant trong API/log | `2026-11-06T02:30:00Z` |
| OffsetDateTime trong API | `2026-11-06T09:30:00+07:00` |
| ZonedDateTime cần zone ID | Có thể dùng định dạng lưu rõ region ID, ví dụ `[Europe/Berlin]`, tùy hợp đồng API |
| Hiển thị cho người dùng Việt | `06/11/2026`, theo locale và yêu cầu UI |

**Không giả định mọi client parse được ZonedDateTime với phần `[Region/City]` theo cùng định dạng.** Hợp đồng API nên quy định trường timestamp và zone rõ ràng, thay vì dựa vào cách `toString()` của một object.

### 15.3. Mapping database

Tùy database, schema và JDBC driver, có những định hướng thường gặp:

- Cột **DATE** → `LocalDate` cho ngày lịch.
- Cột **TIME WITHOUT TIME ZONE** → `LocalTime` cho giờ trong ngày.
- Cột **TIMESTAMP WITHOUT TIME ZONE** → `LocalDateTime` khi schema thực sự biểu thị local date-time.
- Timestamp dùng để lưu **một Instant** → cần quy ước rõ UTC/offset/kiểu timestamp của database, mapping driver và cách serialize.
- **TIMESTAMP WITH TIME ZONE** có ngữ nghĩa khác nhau theo hệ quản trị; không được khẳng định cột này luôn giữ **ZoneId khu vực** như `Europe/Berlin`. Nhiều hệ thống chỉ giữ offset hoặc chuẩn hóa thời điểm.

Với JDBC 4.2/JDK 8, các kiểu `java.time` có hỗ trợ mapping theo đặc tả và driver, nhưng khả năng thực tế còn tùy nhà cung cấp. **Kiểm tra schema và driver cụ thể**, nhất là khi đọc/ghi `OffsetDateTime`, `Instant` hoặc zone ID.

Nếu lịch hẹn tương lai phải giữ ZoneId, hãy **lưu riêng zone ID** nếu schema timestamp không bảo toàn thông tin đó. Khi chỉ cần record một event đã xảy ra, cần đảm bảo database lưu và trả lại đúng Instant, không bị ứng dụng/driver áp timezone mặc định hai lần.

## 16. Ví dụ hoàn chỉnh 4 — Parse, format, so sánh Instant và Clock

Tệp **`TemporalParsingDemo.java`** xác nhận rằng hai OffsetDateTime có local time và offset khác nhau vẫn có thể biểu thị **cùng một Instant**, cách parse LocalDate nghiêm ngặt, và cách test “hôm nay” mà không phụ thuộc đồng hồ thật.

```java
import java.time.*;
import java.time.format.*;
import java.util.*;

public class TemporalParsingDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    public static void main(String[] args) {
        OffsetDateTime vietnam =
            OffsetDateTime.parse(
                "2026-11-06T09:00:00+07:00");

        OffsetDateTime tokyo =
            OffsetDateTime.parse(
                "2026-11-06T11:00:00+09:00");

        Instant expected =
            Instant.parse("2026-11-06T02:00:00Z");

        boolean sameInstant =
            vietnam.toInstant().equals(tokyo.toInstant());

        LocalDate invoiceDate =
            LocalDate.parse("2026-11-06",
                DateTimeFormatter.ISO_LOCAL_DATE);

        DateTimeFormatter vietnamese =
            DateTimeFormatter.ofPattern(
                "dd/MM/uuuu", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);

        String formatted =
            invoiceDate.format(vietnamese);

        boolean invalidRejected = false;
        try {
            LocalDate.parse("31/02/2026", vietnamese);
        } catch (DateTimeParseException ex) {
            invalidRejected = true;
        }

        Clock fixed = Clock.fixed(
            expected,
            ZoneId.of("Asia/Ho_Chi_Minh"));

        LocalDate businessToday = LocalDate.now(fixed);

        check(sameInstant &&
              expected.equals(vietnam.toInstant()),
              "same moment");
        check("06/11/2026".equals(formatted),
              "format");
        check(invalidRejected, "strict date");
        check(businessToday.equals(
            LocalDate.of(2026, 11, 6)),
            "clock time zone");

        System.out.println("vietnam=" + vietnam);
        System.out.println("tokyo=" + tokyo);
        System.out.println("sameInstant=" + sameInstant);
        System.out.println("instant=" + expected);
        System.out.println("formatted=" + formatted);
        System.out.println(
            "invalidRejected=" + invalidRejected);
        System.out.println(
            "businessToday=" + businessToday);
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 TemporalParsingDemo.java
java TemporalParsingDemo
```

Stdout đã kiểm chứng:

```text
vietnam=2026-11-06T09:00+07:00
tokyo=2026-11-06T11:00+09:00
sameInstant=true
instant=2026-11-06T02:00:00Z
formatted=06/11/2026
invalidRejected=true
businessToday=2026-11-06
PASS
```

**Điểm quan trọng:**

1. Hai OffsetDateTime có offset khác nhau vẫn có thể cùng một thời điểm. Dùng `toInstant().equals(...)` khi bài toán muốn so **cùng thời điểm**, thay vì chỉ so chuỗi hoặc LocalDateTime.
2. `DateTimeFormatter` giúp tách kiểu dữ liệu khỏi kiểu hiển thị. Nó bất biến và có thể tái sử dụng an toàn giữa các luồng theo hợp đồng Java 8.
3. `ResolverStyle.STRICT` giúp từ chối ngày không tồn tại như 31/02/2026. Mẫu `uuuu` với STRICT phù hợp cho năm proleptic ISO; đừng lấy parsing lenient mặc định làm tiêu chuẩn validation.
4. `Clock.fixed` làm test chạy ở mọi ngày vẫn cho một “hôm nay” xác định trong vùng nghiệp vụ.

## 17. Clock: làm cho logic “hiện tại” kiểm thử được

Để tránh viết một logic phụ thuộc trực tiếp vào đồng hồ của máy:

```java
// Không tiện test vì kết quả phụ thuộc thời điểm chạy:
LocalDate today = LocalDate.now();
Instant now = Instant.now();
```

có thể nhận `Clock` từ bên ngoài:

```java
// Minh họa phương thức thuộc một service.
static boolean isPastDue(LocalDate dueDate, Clock clock) {
    return LocalDate.now(clock).isAfter(dueDate);
}
```

Trong code ứng dụng:

```java
Clock clock = Clock.system(
    ZoneId.of("Asia/Ho_Chi_Minh"));
```

Trong unit test:

```java
Clock clock = Clock.fixed(
    Instant.parse("2026-11-06T02:30:00Z"),
    ZoneId.of("Asia/Ho_Chi_Minh"));
```

Điểm cần chọn đúng: `LocalDate.now(clock)` dùng **zone gắn với Clock** để suy ra ngày địa phương, còn `Instant.now(clock)` trả thời điểm tuyệt đối. Nếu nghiệp vụ yêu cầu “hôm nay tại chi nhánh”, nên truyền Clock/ZoneId của chi nhánh thay vì dựa vào máy chủ.

**Không suy ra ZoneId của khách hàng từ ZoneId.systemDefault()** nếu đó chỉ là cấu hình server. Nguồn timezone phải xuất phát từ hợp đồng dữ liệu, hồ sơ địa điểm hoặc lựa chọn người dùng đã được xác định rõ.

## 18. Những quyết định khó: giữ wall time hay giữ Instant?

### Một cuộc họp trong tương lai

Người dùng chọn “09:00 ngày 30/10 tại Berlin”. Có hai cách hiểu:

**A. Cam kết đúng thời điểm tuyệt đối:** bạn đã resolve lịch hẹn thành một Instant và tất cả người tham gia phải tham dự đúng thời điểm đó. Sau này luật timezone thay đổi, giờ trên đồng hồ Berlin khi hiển thị có thể khác, nhưng **Instant không thay đổi**.

**B. Cam kết đúng 09:00 theo giờ địa phương:** người dùng muốn đến lúc đồng hồ Berlin chỉ 09:00 của ngày đã định, bất kể các quy tắc vùng có cập nhật. Khi đó phải bảo toàn **LocalDateTime + ZoneId** (và policy DST), và có thể cần **recompute Instant** khi tzdb thay đổi.

Một số ứng dụng phải lưu **cả hai** cùng ý nghĩa và chính sách update rõ ràng. Đừng xóa local time/ZoneId sau khi tính Instant rồi kỳ vọng vẫn có thể biết ý định ban đầu của người dùng.

### Ngày hết hạn sản phẩm

“Thẻ thành viên hết hạn ngày 31/12 theo Hà Nội” có thể là **LocalDate với ZoneId nghiệp vụ**. Khi thực thi tại một mốc thời gian, có thể lấy Instant ở **đầu ngày 01/01 tiếp theo** để tạo khoảng hiệu lực nửa mở.

“Phiên đăng nhập hết hạn sau 30 phút” không phải LocalDate. Chọn `Duration.ofMinutes(30)` cộng vào Instant phát hành.

### Giờ nhắc việc lặp

“Nhắc lúc 08:00 mỗi ngày ở Paris” thường là **LocalTime + ZoneId + quy tắc lặp ngày**, không phải một Instant duy nhất (vì mỗi ngày có một Instant mới) và không phải OffsetTime cố định qua cả năm (vì Paris có thể đổi offset).

Với ngày DST gap/overlap, cần xác định xử lý bỏ qua, dời lịch, chạy một lần hay chạy hai lần. Đó là **quy tắc scheduler** cần thiết kế riêng, không phải hành vi tự động được LocalTime bảo đảm.

## 19. Chọn kiểu trong mô hình domain: ví dụ thiết kế trường

Một hệ thống có thể có:

```java
// Mô hình chữ ký minh họa, không phải class Java độc lập.
class Order {
    LocalDate promisedDeliveryDate;
    Instant createdAt;
    Instant paidAt;
}

class Meeting {
    LocalDateTime requestedLocalStart;
    ZoneId locationZone;
    Instant resolvedStart;
    Duration reservedLength;
}

class PayrollCycle {
    YearMonth month;
    LocalDate payoutDate;
}

class OpeningHours {
    LocalTime opens;
    LocalTime closes;
    ZoneId branchZone;
}
```

Các field có chủ đích khác nhau:

- Order: `promisedDeliveryDate` là ngày hiển thị theo lịch; `createdAt/paidAt` là điểm thời gian thật.
- Meeting: `requestedLocalStart` lưu ý định giờ trên đồng hồ, `locationZone` lưu quy tắc khu vực, `resolvedStart` là thời điểm sau khi xử lý chính sách DST; cần định nghĩa cách cập nhật để các trường không mâu thuẫn.
- PayrollCycle: `YearMonth` biểu diễn tháng tính lương; `payoutDate` là ngày trả lương thực.
- OpeningHours: giờ mở và đóng là LocalTime, zone là vùng của chi nhánh; nếu giờ đóng qua nửa đêm thì cần thêm quy tắc liên kết ngày.

Đây là **mẫu tư duy domain**, không phải yêu cầu mọi entity phải có đúng các field này. Quy tắc cơ bản là **mỗi trường phải mang thông tin thực sự tồn tại trong nghiệp vụ**, không chứa một ngày/giờ giả chỉ để phù hợp với kiểu lưu trữ.

## 20. Các lỗi phổ biến khi chọn sai kiểu

| Lỗi | Tại sao nguy hiểm | Hướng sửa |
| --- | --- | --- |
| Dùng `Instant` cho ngày sinh | Hiển thị ở múi giờ khác có thể đổi ngày | `LocalDate` |
| Dùng `LocalDateTime` cho log từ nhiều vùng | Không biết các event xảy ra khi nào trên timeline | `Instant`, giữ zone hiển thị nếu cần |
| Lưu offset thay cho zone ID của lịch hẹn tương lai | Offset không chứa quy tắc DST/lịch sử | `ZoneId` và local appointment policy |
| Lưu `ZonedDateTime` nhưng nghĩ timezone rules không bao giờ đổi | Tzdb và luật địa phương có thể cập nhật | Xác định nghĩa cần bảo toàn; version/test |
| Dùng `Duration.ofDays(1)` cho “cùng giờ ngày mai” | Có thể lệch 1 giờ qua DST | Phép lịch `plusDays(1)` hoặc `Period` |
| Dùng `Period.ofDays(1)` cho TTL đúng 24 giờ | Một ngày lịch có thể 23/25 giờ | `Duration.ofHours(24)` |
| Dùng LocalDate “ngày 01” làm kỳ tháng | Tạo ý nghĩa ngày không tồn tại | `YearMonth` |
| Dùng `LocalTime` để biểu diễn một event đã xảy ra | Không có ngày/zone để xác định Instant | `Instant` hoặc kiểu có ngữ cảnh |
| Gọi `LocalDateTime.atZone(systemDefault)` vô điều kiện | Server/CI khác múi giờ người dùng | `ZoneId` rõ ràng từ domain |
| Nghĩ `atZone` sẽ từ chối mọi DST gap | API có thể tự dịch local time | Kiểm `getValidOffsets`, chọn policy |
| Nghĩ 02:30 trong overlap chỉ có một Instant | Có hai offset hợp lệ | Xác định offset sớm/muộn |
| Dùng `OffsetDateTime.equals` để hỏi “cùng Instant?” | Giá trị local/offset khác nhau không nhất thiết equals | So `toInstant` hoặc `isEqual` theo hợp đồng |
| Dùng millisecond như second trong epoch | Timestamp lệch rất xa | Định nghĩa và kiểm đơn vị |
| Tạo String rồi nối chuỗi để tính ngày | Không xử lý tháng/ngày nhuận và DST | `java.time` + DateTimeFormatter |
| Dùng `now()` trực tiếp trong mọi unit test | Test phụ thuộc giờ/ngày máy chạy | Tiêm `Clock.fixed` |
| Dùng parsing không strict cho dữ liệu cần validation | Ngày sai có thể được chuẩn hóa ngoài ý muốn | `DateTimeFormatter` STRICT và test |
| Giả định SQL TIMESTAMP WITH TIME ZONE giữ region ID | Nhiều DB/driver không lưu region ID | Kiểm mapping, lưu ZoneId riêng nếu cần |
| Dùng String cho cả domain ngày giờ | Mất phép toán và validation kiểu an toàn | Parse tại biên, dùng kiểu chuyên biệt |

## 21. Ma trận kiểm thử cho logic ngày giờ

Một bộ test tốt không chỉ thử một timestamp hợp lệ. Tùy nghiệp vụ, cần kiểm:

| Trường hợp | Tại sao cần |
| --- | --- |
| Ngày thường trong một vùng đơn giản | Xác nhận đường thành công |
| 29/02 ở năm nhuận và năm không nhuận | Ngày sinh, lịch lặp, xử lý validation |
| Ngày cuối tháng 31/01 + một tháng | Quy tắc điều chỉnh ngày |
| Đổi năm 31/12 → 01/01 | Biên năm |
| Local time trước/sau nửa đêm | Ca làm và giờ mở cửa qua ngày |
| DST gap tại một vùng có chuyển giờ | Thời điểm local không tồn tại |
| DST overlap tại một vùng có chuyển giờ | Thời điểm local mơ hồ |
| Hai offset khác nhau cùng Instant | So sánh sự kiện giữa các vùng |
| Một Instant hiển thị ở hai ZoneId | Ngày local có thể khác |
| Ngày lịch cộng 1 vs thời lượng 24 giờ | Tránh nhầm Period/Duration |
| Clock.fixed với nhiều time zone | Không phụ thuộc giờ hệ thống/CI |
| Parse ISO hợp lệ và chuỗi sai định dạng | Validation ranh giới |
| Ngày không tồn tại 31/02 | STRICT parser |
| Epoch giây vs mili giây | Kiểm hợp đồng đơn vị |
| Database read/write round-trip | Không bị mất offset, precision, zone ID |
| Tzdb/runtime được nâng cấp | Lịch hẹn tương lai không đổi nghĩa ngoài ý muốn |

**Nguyên tắc kiểm thử:** viết expected theo **ý nghĩa nghiệp vụ** trước khi dùng `java.time` làm oracle. Ví dụ "một ngày lịch" phải được test bằng **cùng giờ địa phương ngày kế tiếp**, không phải bằng số 86.400 giây trừ khi đó là yêu cầu thật.

### Test không phụ thuộc thời gian hiện tại

Tránh:

```java
// Dễ thất bại lúc qua nửa đêm hoặc trên CI timezone khác.
LocalDate expected = LocalDate.of(2026, 11, 6);
if (!LocalDate.now().equals(expected)) {
    throw new AssertionError();
}
```

Thay bằng Clock cố định và ZoneId nghiệp vụ. Dữ liệu DST cố định trong ví dụ cũng hữu ích để kiểm logic, nhưng khi timezone database thay đổi trong tương lai, cần phân biệt **thay đổi rule hợp lệ** với **bug code**.

## 22. Bài tập ứng dụng

**Bài 1 — Ngày sinh và giờ đăng ký**

Một hồ sơ người dùng có ngày sinh 06/11/2000 và thời điểm tạo tài khoản 2026-11-06T02:30:00Z. Hai trường nên có kiểu nào?

**Đáp án:** ngày sinh là `LocalDate`; thời điểm tạo tài khoản là `Instant`. Ngày sinh không thay đổi khi người dùng di chuyển múi giờ; Instant có thể được hiển thị ở vùng của người dùng.

**Bài 2 — Giờ mở cửa chi nhánh**

Chi nhánh Paris mở cửa lúc 09:00 hàng ngày, kể cả sau khi đổi giờ mùa hè. Lưu `OffsetTime.of(9,0,+01:00)` có đủ không?

**Đáp án:** không. Offset cố định không chứa quy tắc vùng; dùng `LocalTime.of(9,0)` cùng `ZoneId.of("Europe/Paris")`, cộng lịch ngày hoạt động và chính sách DST.

**Bài 3 — Giao dịch đã thanh toán**

Backend nhận timestamp `2026-11-06T09:00:00+07:00` và cần so sánh thứ tự thanh toán từ nhiều vùng. Nên chuẩn hóa về gì?

**Đáp án:** chuyển thành `Instant` để so sánh thời điểm thực tế; lưu offset/ZoneId gốc riêng nếu có nhu cầu hiển thị/báo cáo nguồn.

**Bài 4 — Kỳ lương**

Yêu cầu chỉ ghi “tháng lương 11/2026”. Có nên lưu `LocalDate.of(2026,11,1)` không?

**Đáp án:** `YearMonth.of(2026,11)` diễn đạt đúng hơn, không tạo ngày 1 giả. Nếu cần tính ngày trả lương, lưu một LocalDate riêng hoặc áp quy tắc chuyển đổi khi thực hiện.

**Bài 5 — Token 24 giờ và lịch họp một ngày sau**

Một token hết hạn đúng 24 giờ sau khi tạo; một lịch họp phải diễn ra cùng giờ địa phương vào ngày hôm sau. Có dùng cùng phép cộng không?

**Đáp án:** không. Token dùng `Instant.plus(Duration.ofHours(24))`; lịch họp gắn vùng dùng phép lịch `ZonedDateTime.plusDays(1)` với quy tắc DST phù hợp.

**Bài 6 — Xác định giờ trong overlap**

Người dùng chọn 02:30 ngày 25/10/2026 ở Berlin. Chỉ dùng LocalDateTime để lưu có đủ xác định Instant không?

**Đáp án:** không. Có hai offset hợp lệ, tạo hai Instant cách nhau một giờ. Cần ZoneId và policy chọn offset, hoặc yêu cầu người dùng chọn rõ lần sớm/muộn.

**Bài 7 — Hạn cuối ngày**

“Đơn hết hiệu lực sau ngày 06/11/2026 ở Hà Nội” nên được kiểm như thế nào?

**Gợi ý:** biểu diễn ngày hạn bằng `LocalDate`. Nếu muốn mốc hết hạn là đầu ngày 07/11/2026 ở Hà Nội, chuyển `dueDate.plusDays(1).atStartOfDay(zone).toInstant()`, sau đó dùng so sánh Instant với mốc hiện tại. Tránh phép “23:59:59.999” tùy độ chính xác.

**Bài 8 — Nhiều server có timezone khác nhau**

Một service đặt lịch nhận LocalDateTime và dùng `ZoneId.systemDefault()` để tính Instant. Vì sao cùng request có thể ra kết quả khác giữa hai server?

**Đáp án:** vì timezone mặc định của server có thể khác nhau. Phải lấy ZoneId từ hợp đồng nghiệp vụ/chi nhánh hoặc trường truyền vào, không dựa vào cấu hình ẩn của runtime.

## 23. Câu hỏi tự kiểm tra

**1. LocalDateTime có thể so sánh hai sự kiện ở hai múi giờ để biết sự kiện nào xảy ra trước không?**  
Không đủ thông tin. Cần resolve mỗi local time bằng ZoneId/offset đúng rồi so các Instant.

**2. Vì sao OffsetDateTime không đồng nghĩa với ZonedDateTime?**  
OffsetDateTime có offset cố định; ZonedDateTime có danh tính vùng và quy tắc múi giờ, gồm DST.

**3. Một ngày lịch luôn dài 24 giờ không?**  
Không. Ở vùng có DST, một ngày có thể ngắn hơn hoặc dài hơn 24 giờ; Duration.ofDays(1) vẫn là đúng 24 giờ.

**4. YearMonth có lợi gì so với LocalDate đặt ngày 1?**  
Nó giữ đúng mức độ thông tin thật: chỉ tháng và năm, tránh tạo ý nghĩa ngày không tồn tại.

**5. Instant có nhớ địa điểm hoặc timezone người dùng không?**  
Không. Nếu cần bối cảnh vùng, lưu thêm ZoneId/offset hoặc thông tin domain phù hợp.

**6. Có thể giải quyết 02:30 giờ local trong DST overlap bằng một ZoneId duy nhất mà không chọn offset không?**  
Java có default, nhưng nghiệp vụ có thể cần chọn rõ hai lần xuất hiện khác nhau; ZoneId + LocalDateTime có thể mơ hồ.

**7. Với ngày sinh 29/02, cần quy tắc gì cho năm không nhuận?**  
Cần quyết định nghiệp vụ về ngày kỷ niệm/đủ tuổi; Java type không tự quyết định chính sách cho mọi hệ thống.

**8. Vì sao Clock.fixed giúp unit test đáng tin hơn?**  
Vì “bây giờ/hôm nay” được cố định theo Instant và ZoneId, không phụ thuộc ngày/giờ chạy test.

**9. Có nên lưu ZoneId dưới dạng offset như +07:00 cho lịch hẹn tương lai ở khu vực có DST không?**  
Không nếu cần theo quy tắc giờ dân sự của vùng; offset không mang đầy đủ các chuyển đổi trong tương lai.

**10. “Đúng 90 phút” và “thêm một tháng” nên dùng kiểu gì?**  
90 phút là Duration; một tháng lịch là Period hoặc phép tính lịch như plusMonths.

## Tài liệu tham khảo chính thức

- [Java SE 8 — java.time](https://docs.oracle.com/javase/8/docs/api/java/time/package-summary.html): tổng quan mô hình ngày giờ bất biến và các kiểu domain.
- [Java SE 8 — LocalDate](https://docs.oracle.com/javase/8/docs/api/java/time/LocalDate.html), [LocalTime](https://docs.oracle.com/javase/8/docs/api/java/time/LocalTime.html), [LocalDateTime](https://docs.oracle.com/javase/8/docs/api/java/time/LocalDateTime.html): các kiểu lịch không mang thông tin múi giờ.
- [Java SE 8 — Instant](https://docs.oracle.com/javase/8/docs/api/java/time/Instant.html): thời điểm trên dòng thời gian.
- [Java SE 8 — OffsetDateTime](https://docs.oracle.com/javase/8/docs/api/java/time/OffsetDateTime.html), [ZonedDateTime](https://docs.oracle.com/javase/8/docs/api/java/time/ZonedDateTime.html): offset và quy tắc vùng.
- [Java SE 8 — YearMonth](https://docs.oracle.com/javase/8/docs/api/java/time/YearMonth.html), [MonthDay](https://docs.oracle.com/javase/8/docs/api/java/time/MonthDay.html), [Year](https://docs.oracle.com/javase/8/docs/api/java/time/Year.html): các mức độ chi tiết khác nhau của lịch.
- [Java SE 8 — Duration](https://docs.oracle.com/javase/8/docs/api/java/time/Duration.html), [Period](https://docs.oracle.com/javase/8/docs/api/java/time/Period.html): thời lượng thực và lượng ngày-tháng-năm.
- [Java SE 8 — ZoneId](https://docs.oracle.com/javase/8/docs/api/java/time/ZoneId.html), [ZoneRules](https://docs.oracle.com/javase/8/docs/api/java/time/zone/ZoneRules.html): zone, gap/overlap và offset hợp lệ.
- [Java SE 8 — Clock](https://docs.oracle.com/javase/8/docs/api/java/time/Clock.html): nguồn thời gian có thể kiểm thử.
- [Java SE 8 — DateTimeFormatter](https://docs.oracle.com/javase/8/docs/api/java/time/format/DateTimeFormatter.html): parsing/formatting và các quy tắc resolver.

**Ghi nhớ:** đừng hỏi “dữ liệu này có hiển thị ngày và giờ không?” mà hãy hỏi **“người dùng và hệ thống đang cam kết điều gì?”**. Chọn `LocalDate` cho ngày lịch, `LocalTime` cho giờ trong ngày, `LocalDateTime` cho ngày giờ chưa resolve, `Instant` cho thời điểm tuyệt đối, `OffsetDateTime` cho timestamp có offset, `ZonedDateTime`/`ZoneId` khi cần quy tắc vùng, `YearMonth`/`MonthDay` khi mức độ lịch phù hợp, và phân biệt `Duration` với `Period`. Kiểm thử DST, quy tắc tháng, timezone và Clock giúp các quyết định này giữ đúng ý nghĩa nghiệp vụ trong thực tế.