# Chọn `LocalDate` cho ngày sinh, ngày hóa đơn và ngày hiệu lực

**`LocalDate` là lựa chọn đúng khi nghiệp vụ hỏi “ngày nào trên lịch?” mà không cần giờ, phút, giây hoặc một thời điểm tuyệt đối trên dòng thời gian.** Ngày sinh, ngày ghi trên hóa đơn và ngày bắt đầu có hiệu lực của chính sách/hợp đồng thường thuộc nhóm này.

Ví dụ:

- Ngày sinh: **29/02/2000**. Người đó sinh vào ngày lịch này; đây không phải một timestamp UTC cần chuyển đổi theo múi giờ người xem.
- Ngày hóa đơn: **31/01/2026**. Đây là ngày phát hành được ghi nhận theo quy tắc nghiệp vụ, không nhất thiết trùng với thời điểm hệ thống tạo bản ghi.
- Ngày hiệu lực: **01/11/2026**. Đây có thể là ngày bắt đầu áp dụng giá hoặc chính sách, còn chính xác “bắt đầu lúc nào” chỉ cần xác định thêm khi hệ thống thực thi theo một vùng múi giờ cụ thể.

Trong Java 17+, `java.time.LocalDate` lưu **năm, tháng, ngày theo hệ lịch ISO-8601**. Nó **không chứa giờ, offset, `ZoneId`, hay `Instant`**. Tính chất này phù hợp để bảo vệ ý nghĩa “ngày dân sự” của dữ liệu khỏi việc tự dịch sang một ngày khác khi đổi múi giờ.

## 1. Chọn kiểu thời gian theo câu hỏi nghiệp vụ

| Câu hỏi | Kiểu Java thích hợp | Giải thích |
| --- | --- | --- |
| Người dùng sinh **ngày nào**? | `LocalDate` | Chỉ cần ngày lịch |
| Ngày phát hành, ngày đến hạn ghi trên hóa đơn? | `LocalDate` | Mốc ngày theo quy tắc kế toán/hợp đồng |
| Chính sách có hiệu lực từ **ngày nào**? | `LocalDate` | Ngày đầu áp dụng; cần thỏa thuận rõ tính bao gồm biên |
| Lịch hẹn diễn ra **09:00 tại Hà Nội**? | `LocalDateTime` + `ZoneId` | Có giờ địa phương; muốn instant phải dùng quy tắc vùng |
| Giao dịch được xác nhận **lúc nào**? | `Instant` | Một thời điểm tuyệt đối để so sánh/sắp thứ tự |
| Ngày giờ cụ thể kèm offset `+07:00`? | `OffsetDateTime` | Có ngày giờ và offset, xác định được instant |
| Lịch phát sinh lúc 09:00 tại một vùng có DST? | `ZonedDateTime` hoặc local date-time + zone và chính sách | Cần nắm quy tắc vùng, nhất là gap/overlap |

Điểm mấu chốt: **ngày lịch và thời điểm tuyệt đối là hai loại dữ liệu khác nhau**. Không tự thay `LocalDate` bằng `Instant` chỉ vì database hoặc API quen lưu timestamp.

### Ngày sinh minh họa cho vấn đề

Nếu hệ thống lưu ngày sinh `2000-02-29` dưới dạng “`2000-02-29T00:00:00Z`” rồi chuyển để hiển thị tại một vùng UTC-05:00, đồng hồ địa phương sẽ hiển thị **19:00 ngày 28/02/2000**. Nếu giao diện chỉ lấy phần ngày từ timestamp đã chuyển, **ngày sinh bị sai một ngày**. `LocalDate` tránh biến một ngày sinh thành thời điểm UTC giả tạo.

Tương tự, **ngày trên hóa đơn** và **ngày hiệu lực** thường phải giữ nguyên giá trị lịch đã quy định khi người xem ở vùng khác.

## 2. Khởi tạo, đọc và biến đổi `LocalDate`

~~~java
import java.time.LocalDate;

LocalDate birthDate = LocalDate.of(2000, 2, 29);
LocalDate invoiceDate = LocalDate.parse("2026-01-31");
LocalDate effectiveDate = LocalDate.of(2026, 11, 1);

System.out.println(birthDate);    // 2000-02-29
System.out.println(invoiceDate);  // 2026-01-31
System.out.println(effectiveDate);// 2026-11-01
~~~

Đây là các lệnh đặt trong một method, không phải một chương trình độc lập. `LocalDate.parse(...)` mặc định đọc chuỗi ngày ISO `uuuu-MM-dd`; `LocalDate.of(year,month,day)` yêu cầu ngày hợp lệ. Ví dụ `LocalDate.of(2026, 2, 29)` ném `DateTimeException` vì 2026 không phải năm nhuận.

Các thao tác phổ biến:

- `getYear()`, `getMonthValue()`, `getDayOfMonth()`: đọc năm/tháng/ngày.
- `isBefore(other)`, `isAfter(other)`, `isEqual(other)`: so sánh ngày theo lịch.
- `plusDays(n)`, `minusDays(n)`, `plusMonths(n)`: tính ngày mới.
- `withDayOfMonth(n)`, `withYear(n)`, `with(TemporalAdjusters...)`: điều chỉnh theo quy tắc.
- `Period.between(start, end)`: khoảng cách theo **năm, tháng, ngày của lịch**.
- `format(formatter)`: tạo chuỗi hiển thị theo định dạng quy định.

`LocalDate` **bất biến**: `invoiceDate.plusDays(30)` không sửa `invoiceDate`; phải **nhận giá trị trả về** vào biến khác hoặc gán lại. Ví dụ `LocalDate dueDate = invoiceDate.plusDays(30);`.

Lưu ý: `plusMonths(1)` có thể điều chỉnh cuối tháng, ví dụ `2026-01-31.plusMonths(1)` là `2026-02-28`. Phép cộng tháng không có nghĩa mỗi tháng luôn có số ngày bằng nhau.

## 3. Trường hợp 1: Ngày sinh (`birthDate`)

Ngày sinh là thuộc tính nhân thân theo **ngày lịch**, nên khai báo rõ là `LocalDate`:

~~~java
LocalDate birthDate = LocalDate.of(2000, 2, 29);
LocalDate referenceDate = LocalDate.of(2026, 10, 24);

int completedYears =
        java.time.Period.between(birthDate, referenceDate).getYears();
// 26
~~~

Đoạn này đặt trong method với `import java.time.LocalDate;`. `Period.between(...).getYears()` đọc **số năm hoàn chỉnh trong khoảng thời gian lịch** cho hai ngày đã biết, hữu ích để tính tuổi trong các trường hợp thông thường.

**Không dùng `Duration.between` để tính tuổi từ hai `LocalDate`**: `Duration` mô tả khoảng thời gian chính xác theo giây/nano giây giữa các temporal thích hợp. Tuổi theo năm là phép tính **theo lịch**, không phải lấy số giây chia cho 365 ngày. Nếu muốn tuổi tính đến hôm nay, phải xác định “hôm nay” thuộc **múi giờ nghiệp vụ nào** trước khi lấy `LocalDate.now(zone)` hoặc dùng `Clock` được truyền vào.

**Ngày sinh 29/02 là trường hợp nghiệp vụ đặc biệt.** Các tổ chức/pháp luật có thể quy định ngày kỷ niệm sinh nhật hay ngưỡng đủ tuổi trong năm không nhuận là **28/02 hoặc 01/03**. `Period.between` tuân theo thuật toán lịch của Java; nó không thay thế quy tắc pháp lý riêng. Nếu quyết định quyền lợi hay điều kiện tuổi có tính pháp lý, hãy ghi rõ quy tắc cho 29/02, thiết kế một phép kiểm riêng theo nghiệp vụ và kiểm thử ngày biên.

**Không đồng nhất ngày sinh với ngày giờ sự kiện sinh:** Một hồ sơ có thể chỉ biết ngày sinh, trong khi bản ghi bệnh viện có thể biết chính xác giờ và vùng. Nếu nghiệp vụ cần cả hai, mô hình hóa **hai trường riêng** (ngày sinh đã xác nhận và thời điểm sinh, nếu có), thay vì bắt buộc mọi người phải có timestamp hoặc thêm giờ `00:00` giả.

## 4. Trường hợp 2: Ngày hóa đơn và ngày đến hạn

Một hóa đơn có thể mang ít nhất ba ý nghĩa thời gian khác nhau:

| Trường | Ví dụ Java | Ý nghĩa |
| --- | --- | --- |
| `invoiceDate` | `LocalDate` | Ngày phát hành/ngày hóa đơn được nghiệp vụ xác định |
| `dueDate` | `LocalDate` | Ngày đến hạn thanh toán theo điều khoản |
| `createdAt`, `issuedAt` hoặc `paidAt` | `Instant` | Thời điểm hệ thống tạo, phát hành chính thức hoặc nhận thanh toán |

Ví dụ một nhân viên ở Việt Nam phát hành hóa đơn có ngày `2026-01-31`. Người nhận ở vùng múi giờ khác vẫn phải thấy **31/01/2026** trong trường `invoiceDate`. Tuy nhiên, `createdAt` có thể là `2026-01-30T17:30:00Z`, đại diện cho một sự kiện cụ thể. Ngày nghiệp vụ và timestamp phục vụ **hai mục đích khác nhau**; không nên suy một trường từ trường kia nếu không có quy tắc rõ ràng.

### Tính ngày đến hạn: đọc đúng điều khoản

~~~java
LocalDate invoiceDate = LocalDate.of(2026, 1, 31);

// Chỉ đúng khi hợp đồng nói "30 ngày theo lịch" sau ngày hóa đơn.
LocalDate dueAfter30CalendarDays = invoiceDate.plusDays(30);
// 2026-03-02

// Nếu hợp đồng nói "tháng tiếp theo" thì có quy tắc khác:
LocalDate nextMonth = invoiceDate.plusMonths(1);
// 2026-02-28
~~~

Đoạn này nằm trong method với `import java.time.LocalDate;`. **“30 ngày”, “một tháng”, “ngày làm việc thứ 30”, “cuối tháng tiếp theo” không tương đương**. `plusDays(30)` cộng đúng 30 **ngày lịch**; không tự loại trừ thứ Bảy, Chủ nhật hoặc ngày lễ. Nếu điều khoản dùng **ngày làm việc**, cần lịch ngày nghỉ và quy tắc xử lý ngày không làm việc của doanh nghiệp/quốc gia; `LocalDate` vẫn là kiểu phù hợp để biểu diễn ngày kết quả.

Nếu văn bản quy định “thanh toán đến hết ngày 02/03/2026 tại Việt Nam”, trường `dueDate = 2026-03-02` chưa tự xác định **một instant hết hạn**. Khi cần chạy tác vụ khóa thanh toán tự động, mới phải chuyển ngày giới hạn theo `ZoneId` nghiệp vụ và quy ước biên (ví dụ kết thúc **trước đầu ngày kế tiếp**).

## 5. Trường hợp 3: Ngày hiệu lực của hợp đồng, chính sách hoặc mức giá

`effectiveFrom` là ngày bắt đầu chính sách có hiệu lực. `effectiveUntil` hay `effectiveTo` cần được định nghĩa rõ là ngày cuối còn hiệu lực (**inclusive**) hay ngày đầu tiên không còn hiệu lực (**exclusive**). Một quy ước an toàn, dễ ghép các phiên bản là khoảng **nửa mở**:

`[effectiveFrom, effectiveUntilExclusive)`

Điều này nghĩa là **bao gồm ngày bắt đầu, không bao gồm ngày kết thúc**. Ví dụ chính sách áp dụng từ 01/11/2026 đến hết 31/12/2026 thì lưu:

~~~java
LocalDate effectiveFrom = LocalDate.of(2026, 11, 1);
LocalDate effectiveUntilExclusive = LocalDate.of(2027, 1, 1);

LocalDate checkDate = LocalDate.of(2026, 11, 15);
boolean active =
        !checkDate.isBefore(effectiveFrom)
        && checkDate.isBefore(effectiveUntilExclusive);
// true; checkDate = 2027-01-01 sẽ là false.
~~~

Ưu điểm của quy ước này là hai phiên bản liên tiếp có thể dùng `[2026-11-01, 2027-01-01)` và `[2027-01-01, 2027-04-01)` mà không chồng lấn hoặc bỏ trống ngày ranh giới. **Không mặc định đổi đặc tả đang dùng biên inclusive thành exclusive mà không chuyển dữ liệu/đồng thuận hợp đồng.** Tên thuộc tính và tài liệu API phải nói rõ quy ước.

Một số lưu ý nghiệp vụ:

- Nếu ngày hết hiệu lực **không có** (hiệu lực vô thời hạn), dùng `null` hoặc kiểu dữ liệu mô hình hóa khoảng mở đầu cuối theo quy ước của ứng dụng; **không tự bịa một ngày cực lớn** nếu không có hợp đồng dữ liệu.
- Nếu ngày bắt đầu lớn hơn hoặc bằng ngày kết thúc exclusive, khoảng rỗng hoặc không hợp lệ; nên kiểm tra đầu vào.
- Nếu hệ thống lựa chọn chính sách theo **ngày địa phương của khách hàng/cơ sở**, cần chọn `ZoneId` tương ứng khi lấy ngày hiện hành.
- Nếu thực thi thay đổi giá trên toàn cầu tại **một thời điểm UTC đồng loạt**, mô hình có thể cần `Instant effectiveAt` chứ không chỉ `LocalDate`. Đừng ép `LocalDate` phục vụ một yêu cầu vốn chính xác đến giây.

## 6. Ví dụ Java 17+ chạy được: ba loại ngày và ranh giới theo zone

Tạo tệp `LocalDateBusinessDemo.java`:

~~~java
import java.time.Duration;
import java.time.LocalDate;
import java.time.Period;
import java.time.ZoneId;

public class LocalDateBusinessDemo {
    public static void main(String[] args) {
        // 1. Ngày sinh: ngày lịch, không kèm giờ/múi giờ.
        LocalDate birth = LocalDate.of(2000, 2, 29);
        LocalDate reference = LocalDate.of(2026, 10, 24);

        System.out.println("birthDate = " + birth);
        System.out.println("ageOnReference = "
                + Period.between(birth, reference).getYears());

        // 2. Ngày hóa đơn và hạn 30 ngày lịch.
        LocalDate issue = LocalDate.of(2026, 1, 31);
        System.out.println("invoiceDate = " + issue);
        System.out.println("dueAfter30CalendarDays = "
                + issue.plusDays(30));

        // 3. Hiệu lực theo khoảng [from, untilExclusive).
        LocalDate effectiveFrom = LocalDate.of(2026, 11, 1);
        LocalDate effectiveUntilExclusive = LocalDate.of(2027, 1, 1);
        System.out.println("activeOn2026-11-15 = "
                + isActive(
                    LocalDate.of(2026, 11, 15),
                    effectiveFrom, effectiveUntilExclusive));
        System.out.println("activeOn2027-01-01 = "
                + isActive(
                    LocalDate.of(2027, 1, 1),
                    effectiveFrom, effectiveUntilExclusive));

        // Chỉ lúc cần instant của biên ngày mới áp múi giờ.
        LocalDate vietnamDay = LocalDate.of(2026, 1, 15);
        System.out.println("vietnamDayStartsAtUtc = "
                + vietnamDay
                    .atStartOfDay(ZoneId.of("Asia/Ho_Chi_Minh"))
                    .toInstant());

        // DST: một ngày lịch không nhất thiết dài 24 giờ.
        LocalDate parisDate = LocalDate.of(2024, 3, 31);
        ZoneId paris = ZoneId.of("Europe/Paris");
        System.out.println("parisDayLengthHours = "
                + Duration.between(
                    parisDate.atStartOfDay(paris).toInstant(),
                    parisDate.plusDays(1).atStartOfDay(paris).toInstant()
                ).toHours());
    }

    private static boolean isActive(
            LocalDate date, LocalDate from,
            LocalDate untilExclusive) {
        return !date.isBefore(from)
                && date.isBefore(untilExclusive);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac LocalDateBusinessDemo.java
java LocalDateBusinessDemo
~~~

Kết quả:

~~~text
birthDate = 2000-02-29
ageOnReference = 26
invoiceDate = 2026-01-31
dueAfter30CalendarDays = 2026-03-02
activeOn2026-11-15 = true
activeOn2027-01-01 = false
vietnamDayStartsAtUtc = 2026-01-14T17:00:00Z
parisDayLengthHours = 23
~~~

Đã kiểm chứng các phép tính trên trong Java: `Period` là số năm theo lịch giữa hai ngày, `plusDays(30)` vượt qua tháng Hai, hai dòng `active` kiểm tra đúng biên exclusive, và đầu ngày 15/01/2026 tại Việt Nam tương ứng 17:00Z **ngày hôm trước**. Ngày 31/03/2024 ở Paris có một lần chuyển DST, vì thế khoảng giữa hai đầu ngày liên tiếp dài **23 giờ**.

Điều quan trọng không nằm ở việc `LocalDate` “bị mất timezone”: **`LocalDate` vốn có chủ đích không mang timezone**. Chỉ khi chuyển **một ngày thành khoảng các instant** để lọc log/thực thi lịch, bạn mới cần zone của nghiệp vụ.

## 7. Khi buộc phải đổi một ngày thành khoảng thời gian

Giả sử hệ thống muốn tìm mọi thanh toán phát sinh **trong ngày 15/01/2026 tại Việt Nam**. Một ngày lịch xác định **khoảng**, không phải một instant duy nhất:

~~~java
LocalDate businessDate = LocalDate.of(2026, 1, 15);
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant startInclusive =
        businessDate.atStartOfDay(businessZone).toInstant();
Instant endExclusive =
        businessDate.plusDays(1)
                    .atStartOfDay(businessZone).toInstant();

// Lọc timestamp t:
// !t.isBefore(startInclusive) && t.isBefore(endExclusive)
~~~

Đoạn mã đặt trong method với import `java.time.LocalDate`, `java.time.ZoneId`, `java.time.Instant`. Kết quả biên trong ví dụ:

- `startInclusive` = `2026-01-14T17:00:00Z`.
- `endExclusive` = `2026-01-15T17:00:00Z`.

Lọc bằng **`[startInclusive, endExclusive)`** cho phép ghép hai ngày liên tiếp mà không trùng sự kiện chính xác ở ranh giới. Cách này thích hợp cho truy vấn timestamp (đặc biệt nếu timestamp được chuẩn hóa UTC), miễn là kiểu cột/driver và zone đã được xác định rõ.

**Không dùng một cách máy móc `start.plus(Duration.ofDays(1))` để tìm cuối ngày địa phương.** Vào ngày đổi DST, hai đầu ngày ở một vùng có thể cách nhau 23 hoặc 25 giờ. Tính biên kết thúc bằng **`date.plusDays(1).atStartOfDay(zone)`** theo lịch địa phương. `atStartOfDay(zone)` chọn thời điểm hợp lệ sớm nhất của ngày; ở một số thay đổi múi giờ lịch sử, đúng 00:00 có thể không tồn tại. Đây là lý do cần quy tắc vùng thay vì tự coi mỗi ngày dài 86.400 giây.

Đối với ngày hiệu lực, chỉ chuyển sang instant khi cần thực thi tại một thời điểm: ví dụ chính sách “có hiệu lực từ đầu ngày theo giờ Hà Nội”. Nếu cơ sở ở nhiều quốc gia, ngày hiệu lực có thể xảy ra ở **những instant khác nhau** cho từng cơ sở. Phải quyết định zone từ quy tắc hợp đồng, không lấy theo múi giờ bất kỳ của máy chủ.

## 8. Lưu trữ database, API và hiển thị

### Cơ sở dữ liệu: dùng kiểu ngày khi nghĩa là ngày

Trong SQL, cột kiểu `DATE` thường phù hợp để lưu `birth_date`, `invoice_date`, `effective_from` và `effective_until_exclusive`. Tránh lưu các trường này bằng timestamp rồi giả định giờ `00:00 UTC`: khi đổi timezone trong driver, database session hoặc giao diện, phần ngày có thể đổi theo.

Với JDBC 4.2 và driver hỗ trợ ánh xạ `java.time`, ví dụ:

~~~java
// ps và rs là PreparedStatement/ResultSet đã được khởi tạo
// trong code JDBC của ứng dụng.
ps.setObject(1, LocalDate.of(2026, 1, 31));
LocalDate invoiceDate =
        rs.getObject("invoice_date", LocalDate.class);
~~~

Đây chỉ là đoạn API minh họa trong một workflow JDBC đang có; chưa bao gồm cấu hình kết nối/truy vấn. Hãy kiểm tra khả năng hỗ trợ `LocalDate` của JDBC driver và mapping ORM thực tế. Nếu dùng JPA/Hibernate, thuộc tính `LocalDate` thông thường ánh xạ sang ngày SQL; xem cấu hình dialect/schema để xác nhận chính xác. **`DATE` không có nhiệm vụ ghi nhận instant tạo bản ghi**, nên giữ `created_at` với kiểu dữ liệu timestamp phù hợp riêng.

### REST/JSON: thống nhất chuỗi ngày ISO

Ưu tiên biểu diễn ngày dạng:

~~~json
{
  "birthDate": "2000-02-29",
  "invoiceDate": "2026-01-31",
  "dueDate": "2026-03-02",
  "effectiveFrom": "2026-11-01",
  "effectiveUntilExclusive": "2027-01-01"
}
~~~

`yyyy-MM-dd` là cách diễn đạt quen thuộc của ngày ISO; trong `java.time`, mẫu được khuyến nghị khi tự khai báo formatter nghiêm ngặt là `uuuu-MM-dd` (năm trong lịch ISO, hỗ trợ quy tắc resolver), hoặc đơn giản dùng `DateTimeFormatter.ISO_LOCAL_DATE`. Dữ liệu API trên **không có hậu tố `Z`** vì đây là **ngày lịch**, không phải instant. Nếu một serializer tự thêm `T00:00:00Z`, cần rà lại mapping; nó đang thay đổi hợp đồng dữ liệu.

Đối với input theo giao diện Việt Nam `31/01/2026`, parse bằng formatter được quy định rõ:

~~~java
DateTimeFormatter vn =
        DateTimeFormatter.ofPattern("dd/MM/uuuu")
                .withResolverStyle(ResolverStyle.STRICT);
LocalDate invoiceDate = LocalDate.parse("31/01/2026", vn);
~~~

Đoạn minh họa dùng các import `java.time.LocalDate`, `java.time.format.DateTimeFormatter` và `java.time.format.ResolverStyle`. Formatter nghiêm ngặt từ chối ngày không tồn tại (ví dụ 31/02). Giao diện có thể hiển thị `dd/MM/uuuu`, nhưng JSON/API nên thống nhất ISO để giảm hiểu nhầm ngày/tháng.

### Giải quyết “hôm nay” đúng nơi

`LocalDate.now()` sử dụng **timezone mặc định của JVM**, nên ngày hiện hành có thể khác giữa các máy trong khoảng gần nửa đêm. Nếu nghiệp vụ dựa vào ngày Việt Nam, viết:

~~~java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate todayInVietnam = LocalDate.now(zone);
~~~

Đây là đoạn method với import `java.time.ZoneId` và `java.time.LocalDate`. Trong code cần test ổn định, có thể truyền `Clock` và dùng `LocalDate.now(clock)`, ví dụ:

~~~java
Clock clock = Clock.fixed(
        Instant.parse("2026-10-24T16:30:00Z"),
        ZoneId.of("Asia/Ho_Chi_Minh"));
LocalDate today = LocalDate.now(clock);
// 2026-10-24, theo vùng được gắn trong Clock.
~~~

Đoạn này dùng `Clock`, `Instant`, `ZoneId`, `LocalDate` của `java.time`. Nhờ đó unit test không phụ thuộc ngày thực tế và múi giờ máy chạy.

## 9. Những quyết định thiết kế cần nói rõ

| Tình huống | Quyết định cần có |
| --- | --- |
| Ngày sinh 29/02 trong năm không nhuận | Cách xét ngày kỷ niệm/đủ tuổi theo quy tắc nghiệp vụ, pháp luật |
| Ngày phát hành trên hóa đơn | Ngày do người dùng nhập, ngày tại cơ sở hay ngày tự động theo zone quy định? |
| Hạn “30 ngày” | Ngày lịch, ngày làm việc, hay tháng lịch? Có tính ngày bắt đầu không? |
| Hạn “đến hết ngày X” | Vùng địa phương áp dụng và biên kết thúc exclusive |
| Ngày hiệu lực và hết hiệu lực | Biên inclusive hay exclusive; có cho phép ngày kết thúc trống không? |
| Giá/chính sách áp dụng ở nhiều nước | Mỗi cơ sở tính theo ngày địa phương hay một instant toàn cầu? |
| Hiển thị ở vùng múi giờ khác | Giữ nguyên `LocalDate` của nghiệp vụ, chỉ format biểu diễn |
| Lọc dữ liệu timestamp theo ngày | Tạo hai instant từ đầu ngày và đầu ngày kế tiếp theo zone |

Nhiều lỗi “lệch một ngày” không bắt nguồn từ `LocalDate` mà từ việc **chuyển nhầm ngày thành instant hoặc đổi timezone không có quy tắc nghiệp vụ**.

## 10. Lỗi thường gặp và tự kiểm tra

1. **Sai:** lưu ngày sinh thành `Instant` ở nửa đêm UTC rồi lấy phần ngày sau khi chuyển timezone. **Đúng:** lưu ngày sinh bằng `LocalDate`; chỉ lưu instant nếu có sự kiện giờ sinh riêng.
2. **Sai:** coi `LocalDate` là thời điểm đúng 00:00 UTC. **Đúng:** bản thân nó không có offset hay giờ; cần zone khi muốn xây dựng một biên ngày trên timeline.
3. **Sai:** dùng `Instant.now()` làm ngày hóa đơn rồi tự cắt bỏ ngày UTC. **Đúng:** xác định zone và quy tắc phát hành trước khi lấy `LocalDate` nghiệp vụ.
4. **Sai:** `date.plusDays(30);` rồi mong `date` thay đổi. **Đúng:** `LocalDate due = date.plusDays(30);` vì đối tượng bất biến.
5. **Sai:** coi “30 ngày” và “một tháng” như nhau, hoặc tự bỏ qua ngày nghỉ. **Đúng:** dùng phép tính lịch tương ứng và lịch ngày làm việc nếu có quy định.
6. **Sai:** kiểm tra `date.isAfter(effectiveFrom)` để xác định “có hiệu lực từ ngày X” khiến ngày X bị loại. **Đúng:** dùng `!date.isBefore(effectiveFrom)` với biên bắt đầu inclusive.
7. **Sai:** luôn cộng 24 giờ từ đầu ngày để tìm cuối ngày. **Đúng:** tính đầu ngày kế tiếp theo `ZoneId` do nghiệp vụ chỉ định.
8. **Sai:** mặc định ngày sinh 29/02 có quy tắc tuổi hợp pháp như mọi ngày khác. **Đúng:** làm rõ quy định áp dụng cho năm không nhuận.
9. **Sai:** truyền ngày `01/02/2026` mà không nói chuẩn ngày/tháng. **Đúng:** API dùng ISO `2026-02-01`; UI locale riêng với formatter rõ ràng.

**Câu hỏi tự đánh giá:**

- “Sinh ngày 29/02/2000” nên lưu bằng kiểu nào? **`LocalDate`**, vì câu hỏi là ngày lịch.
- “Hóa đơn được phát hành ngày 31/01, ghi log phát hành lúc 23:30 tại Việt Nam” có cần một hay hai trường? **Thường cần `LocalDate invoiceDate` và `Instant issuedAt`**, nếu nghiệp vụ muốn giữ cả ngày in trên hóa đơn lẫn mốc phát hành chính xác.
- “Giá mới áp dụng từ 01/11/2026, cho đến trước 01/01/2027” biểu diễn thế nào? **Khoảng ngày nửa mở** với `effectiveFrom = 2026-11-01`, `effectiveUntilExclusive = 2027-01-01`.
- Ngày 31/03/2024 tại Paris có luôn dài 24 giờ không? **Không**; trong năm đó ngày này dài 23 giờ do đổi DST.
- `LocalDate.now()` và `LocalDate.now(ZoneId.of("Asia/Ho_Chi_Minh"))` luôn cùng giá trị? **Không** nếu timezone mặc định của JVM khác zone đã chọn và thời điểm rơi quanh ranh giới ngày.

**Ghi nhớ:** Hãy chọn `LocalDate` theo **ý nghĩa nghiệp vụ**: ngày sinh, ngày trên hóa đơn và ngày hiệu lực đều là các ngày trên lịch, có thể được so sánh/tính toán độc lập với timestamp. Khi cần sự kiện xảy ra “lúc nào”, bổ sung `Instant` riêng; khi cần biến một ngày thành ranh giới thực thi, áp `ZoneId` và quy tắc inclusive/exclusive được thỏa thuận rõ.