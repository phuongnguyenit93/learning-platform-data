# Chuyển Date với Instant, Calendar với ZonedDateTime

## 1. Chuyển kiểu phải bắt đầu từ ý nghĩa dữ liệu

Một thư viện cũ trả về `java.util.Date`; phần nghiệp vụ mới dùng `Instant`. Một thư viện khác yêu cầu `Calendar`, trong khi ứng dụng đang giữ `ZonedDateTime`. Các phương thức chuyển đổi giúp nối hai thế hệ API, nhưng không bảo đảm mọi thông tin đều đi qua nguyên vẹn.

Trước khi viết mã, cần trả lời: dữ liệu biểu diễn **một thời điểm**, **ngày giờ tại một múi giờ**, hay chỉ **một ngày trên lịch**? Sau đó xác định độ chính xác và những cấu hình nào thật sự thuộc hợp đồng.

| Kiểu | Thông tin chính | Đặc điểm liên quan đến chuyển đổi |
| --- | --- | --- |
| `java.util.Date` | Một thời điểm, độ chính xác mili giây | Có thể thay đổi bằng `setTime`; không mang ID múi giờ riêng |
| `Instant` | Một thời điểm trên dòng thời gian | Bất biến, có thể mang phần nano giây |
| `Calendar` | Thời điểm và các trường lịch cùng cấu hình lịch/múi giờ | Có thể thay đổi; là lớp trừu tượng |
| `GregorianCalendar` | Một triển khai của `Calendar` | Có cầu nối trực tiếp với `ZonedDateTime` |
| `ZonedDateTime` | Ngày giờ theo lịch ISO, múi giờ và độ lệch đã xác định | Bất biến, có thể mang phần nano giây |

Ví dụ, `2024-06-15T03:20:30.123Z` và `2024-06-15T10:20:30.123+07:00[Asia/Ho_Chi_Minh]` mô tả cùng thời điểm. Giá trị đầu không tự mang thông tin rằng người dùng đang xem giờ tại Việt Nam. Thông tin đó được bổ sung khi chọn vùng.

Sau bài này, bạn cần dùng được các cầu nối chính thức, giải thích được điều kiện khứ hồi giữ nguyên dữ liệu và viết kiểm thử theo đúng đại lượng cần bảo toàn.

## 2. Vì sao cần một ranh giới chuyển đổi rõ ràng?

Nếu phần nghiệp vụ nhận và truyền `Date` ở khắp nơi, một lần gọi `setTime` ở xa có thể đổi giá trị mà nơi khác đang giữ. Nếu mỗi lớp tự chọn `systemDefault()` để chuyển đổi, giờ địa phương lại phụ thuộc máy triển khai.

Một cách tổ chức dễ kiểm soát là chuyển dữ liệu ngay khi qua ranh giới thư viện:

```text
Đầu vào từ API cũ
      ↓ kiểm tra hợp đồng, null và loại thực tế
Kiểu java.time phù hợp
      ↓ xử lý nghiệp vụ
Chuyển sang kiểu cũ khi API đầu ra yêu cầu
```

Với dấu thời gian của giao dịch, `Instant` thường thể hiện đúng nhu cầu. Khi cần hiển thị hoặc xử lý theo giờ địa phương, bổ sung `ZoneId` đã được chọn rõ. Nếu dữ liệu chỉ là ngày sinh, không tự thêm giờ và múi giờ rồi tuyên bố đó là một thời điểm vốn có.

Chuyển đổi đối tượng nên thực hiện trực tiếp. Đường vòng “format thành chuỗi rồi parse trở lại” tạo thêm phụ thuộc vào mẫu định dạng, locale và múi giờ, trong khi bản thân bài toán không cần văn bản.

## 3. Date → Instant: lấy thời điểm đang có

Với một đối tượng `java.util.Date` thông thường:

```java
Instant instant = legacyDate.toInstant();
```

Nếu `legacyDate.getTime()` bằng `1_718_421_630_123L`, kết quả giữ đúng thời điểm biểu diễn bởi số mili giây đó. Việc chuyển đổi không yêu cầu chọn `ZoneId`, vì `Date` và `Instant` đều đang biểu diễn thời điểm.

Có thể viết tương đương về thời điểm ở độ chính xác mili giây:

```java
Instant instant = Instant.ofEpochMilli(legacyDate.getTime());
```

Cách này hữu ích khi hợp đồng thực sự truyền epoch millis. Không nhân thêm 1.000: `Date.getTime()` đã dùng mili giây, còn `Instant.ofEpochSecond(...)` nhận giây.

Phương thức `Date.toInstant()` và `Date.from(Instant)` là cầu nối có từ Java 8. Hợp đồng nằm trong [Java SE 21 Date](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Date.html#toInstant()).

### 3.1 Không cần “trừ bảy giờ” khi chuyển

Một lỗi thường gặp là nhận `Date`, thấy `toString()` hiển thị giờ Việt Nam, rồi trừ bảy giờ trước khi gọi `toInstant()`. Làm vậy đổi thời điểm.

Chuỗi hiển thị có thể phụ thuộc múi giờ dùng để trình bày; nó không chứng minh rằng bản thân `Date` đã lưu một “giờ địa phương sai cần sửa”. Hãy so sánh bằng `getTime()` hoặc `Instant` khi điều tra thời điểm.

Nếu dữ liệu đầu vào trước đó đã bị diễn giải sai múi giờ, cần sửa ở bước diễn giải ấy theo hợp đồng gốc. Một lần chuyển kiểu đúng không thể tự đoán và sửa sai lệch do bước nhập dữ liệu trước đó.

### 3.2 Kết quả là một giá trị độc lập

Sau khi lấy `Instant`, sửa `Date` bằng `setTime(...)` không sửa `Instant` đã tạo. Ngược lại, tạo `Date` mới từ một `Instant` rồi sửa `Date` cũng không làm thay đổi `Instant`.

Điều này giúp ranh giới chuyển đổi trở thành nơi chụp lại giá trị. Tuy nhiên, đừng đọc đối tượng cũ trong khi một luồng khác đang sửa nó mà không có cơ chế phối hợp; tính bất biến của kết quả không làm thao tác đọc nguồn tự động an toàn trước mọi thay đổi đồng thời.

## 4. Instant → Date: chấp nhận giới hạn mili giây

Dùng phương thức chuẩn:

```java
Date legacyDate = Date.from(instant);
```

Với `instant = 2024-06-15T03:20:30.123456789Z`, `Date` chỉ giữ tới mili giây. Chuyển trở lại thu được:

```text
2024-06-15T03:20:30.123Z
```

Đây là bỏ phần nhỏ hơn mili giây, không làm tròn lên `.124`. Nếu cần so sánh sau khứ hồi, xác định hợp đồng mong đợi trước:

```java
Instant expected = instant.truncatedTo(ChronoUnit.MILLIS);
boolean ok = Date.from(instant).toInstant().equals(expected);
```

Ví dụ trên cần import `java.time.temporal.ChronoUnit` và giả định `instant` nằm trong phạm vi của `Date`.

### 4.1 Cẩn thận với thời điểm trước epoch

Xét `1969-12-31T23:59:59.999999999Z`, chỉ sớm hơn epoch một nano giây. Sau khi chuyển sang `Date`, epoch millis là `-1`, không phải 0; khi trở lại, kết quả là `1969-12-31T23:59:59.999Z`.

Đừng tự tính bằng cách lấy tổng nano giây âm rồi chia nguyên cho một triệu và mặc định đó là cùng quy tắc. Phép chia nguyên có thể hướng về 0, gây lệch tại giá trị âm. Dùng phương thức chuẩn thay vì tự xây lại phép chuyển đổi.

`Instant.toEpochMilli()` có thể ném `ArithmeticException` nếu giá trị không biểu diễn được bằng `long`. Hợp đồng độ chính xác và phạm vi được mô tả trong [Java SE 21 Instant](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html#toEpochMilli()).

### 4.2 Không phải mọi Instant đều chuyển được

Phạm vi của `Instant` rộng hơn phạm vi epoch millis của `Date`. `Date.from(...)` từ chối giá trị vượt phạm vi bằng `IllegalArgumentException`. Ngoài kiểm tra `null`, một lớp chuyển đổi nhận thời điểm rất xa cần có chính sách báo lỗi phạm vi.

Trong dữ liệu nghiệp vụ hiện đại, giới hạn phạm vi thường ít gặp hơn mất phần nano giây, nhưng hai vấn đề khác nhau. Không dùng một phép thử ở năm 2024 để suy ra mọi giá trị hợp lệ của `Instant` đều chuyển được.

## 5. Calendar → ZonedDateTime: hai đường đi

### 5.1 Khi có GregorianCalendar

Lớp này có phương thức trực tiếp:

```java
ZonedDateTime modern = gregorianCalendar.toZonedDateTime();
```

Đường đi này chuyển thời điểm sang hệ lịch ISO và dùng múi giờ của lịch nguồn. Nó không yêu cầu chép thủ công năm, tháng, ngày, giờ.

Không nên dựng lại bằng `ZonedDateTime.of(calendar.get(YEAR), ...)` chỉ để chuyển một thời điểm đã có. Làm vậy dễ sai chỉ số tháng, bỏ sót mili giây và diễn giải lại giờ địa phương trong vùng có giờ lặp.

### 5.2 Khi biến chỉ có kiểu Calendar

`Calendar` có `toInstant()`, nhưng không khai báo `toZonedDateTime()`. Dùng thời điểm và múi giờ:

```java
Instant instant = calendar.toInstant();
ZoneId zone = calendar.getTimeZone().toZoneId();
ZonedDateTime modern = instant.atZone(zone);
```

Các phương thức `Calendar.toInstant()` và chuyển `TimeZone` sang `ZoneId` cung cấp đường nối mà không cần ép mọi `Calendar` thành `GregorianCalendar`. Xem [Calendar.toInstant](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Calendar.html#toInstant()) và [TimeZone.toZoneId](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TimeZone.html#toZoneId()).

Đường đi qua `Instant` giữ thời điểm rồi chọn cách nhìn theo lịch ISO tại vùng đó. Nó không bảo toàn hệ lịch khác của một lớp con `Calendar` và không tự sao chép các quy tắc tuần.

Nếu yêu cầu đích muốn vùng khác với nguồn, hãy chỉ định vùng đích:

```java
ZonedDateTime utc = calendar.toInstant().atZone(ZoneId.of("UTC"));
```

Thời điểm vẫn được giữ; số giờ địa phương có thể đổi. Nếu muốn giữ số giờ trên mặt đồng hồ và đổi vùng, đó là một yêu cầu nghiệp vụ khác, cần dựng thời điểm mới và giải quyết giờ không tồn tại hoặc lặp lại.

### 5.3 Calendar cần biểu diễn được một thời điểm hợp lệ

Một lịch ở chế độ nghiêm ngặt có thể đang chứa tổ hợp trường chưa hợp lệ do các lần `set(...)` trước đó. Chuyển đổi sẽ cần tính thời điểm và có thể phát hiện lỗi. Đừng xem cầu nối là công cụ tự sửa mọi trường sai.

Đối tượng nên được xác thực khi nhận dữ liệu. Nếu dữ liệu cũ cố ý dùng chế độ dễ dãi, việc chuẩn hóa là một phần của hợp đồng phải hiểu trước khi chuyển.

## 6. ZonedDateTime → Calendar: phương thức nằm ở GregorianCalendar

Dùng:

```java
GregorianCalendar legacy = GregorianCalendar.from(modern);
Calendar requiredByOldApi = legacy;
```

Kiểu trả về cụ thể là `GregorianCalendar`, có thể truyền vào nơi nhận `Calendar`. Không có phương thức `Calendar.from(ZonedDateTime)` tương ứng.

Khi chuyển, thời điểm được đưa về độ chính xác mili giây. Trong các vùng chuẩn thông dụng, múi giờ được nối qua `TimeZone`. Hãy kiểm tra việc chuyển ID nếu dùng vùng tùy biến hoặc độ lệch cố định có độ chính xác đến giây với JDK/API đích; không giả định mọi khả năng biểu diễn của `java.time` đều có bản tương đương trong mọi môi trường cũ.

`GregorianCalendar.from(...)` tạo lịch Gregorian thuần, với thứ Hai là ngày bắt đầu tuần và bốn ngày tối thiểu cho tuần đầu tiên theo ISO. Nó không có nhiệm vụ khôi phục cấu hình một đối tượng `Calendar` trước đó. Đầu vào vượt khả năng biểu diễn của lịch cũ có thể gây `IllegalArgumentException`. Xem [GregorianCalendar.from và toZonedDateTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/GregorianCalendar.html#from(java.time.ZonedDateTime)).

Nếu API cũ cần một cấu hình tuần hoặc chế độ kiểm tra riêng, đặt cấu hình đó sau khi chuyển và kiểm thử theo yêu cầu API. Không biến nó thành giả định ẩn của mọi lần chuyển.

## 7. Khứ hồi: cần nói rõ “giữ nguyên” ở mức nào

Có ít nhất bốn mức so sánh khác nhau:

| Đại lượng cần kiểm tra | Cách kiểm tra phù hợp |
| --- | --- |
| Cùng thời điểm đầy đủ | So sánh hai `Instant` |
| Cùng thời điểm ở mili giây | So sánh epoch millis hoặc Instant đã hạ chính xác theo hợp đồng |
| Giữ vùng quan sát | So sánh `ZoneId`, hoặc quy tắc/độ lệch nếu hợp đồng cho phép ID tương đương |
| Giữ toàn bộ cấu hình lịch cũ | Kiểm tra riêng chế độ lenient, quy tắc tuần, hệ lịch và điểm chuyển lịch |

Một `GregorianCalendar` đổi sang `ZonedDateTime` rồi quay lại có thể giữ epoch millis nhưng `equals` vẫn trả `false`. Ví dụ, lịch nguồn dùng Chủ nhật là ngày đầu tuần và chế độ nghiêm ngặt; lịch tạo từ kiểu hiện đại dùng cấu hình khác.

Tương tự, hai `ZonedDateTime` có thể cùng `Instant` nhưng khác vùng. Nếu kiểm thử chỉ so sánh chuỗi hiển thị hoặc chỉ so sánh ngày, nó có thể bỏ qua thông tin hợp đồng cần giữ.

### 7.1 Lịch sử có thể đổi nhãn ngày

Một `GregorianCalendar` mặc định dùng điểm chuyển Julian/Gregorian ở năm 1582, còn `ZonedDateTime` dùng lịch ISO theo quy tắc Gregorian kéo dài về quá khứ. Vì thế, chuyển đổi có thể giữ thời điểm nhưng thay năm/tháng/ngày hiển thị với dữ liệu lịch sử.

Không sao chép trường ngày để “sửa lại cho giống” khi mục tiêu là giữ thời điểm. Nếu mục tiêu thật sự là giữ một nhãn ngày lịch sử trong hệ lịch nguồn, cần mô hình dữ liệu và quy tắc chuyển hệ lịch riêng.

## 8. Chương trình kiểm chứng đầy đủ

Chương trình sau dùng giá trị cố định và vùng được chỉ định rõ. Nó kiểm tra chuyển hai chiều, mất phần nhỏ hơn mili giây, trường hợp trước epoch, sự độc lập với đối tượng cũ và khác biệt cấu hình sau khứ hồi.

Lưu thành `LegacyTimeBridgeDemo.java` rồi chạy bằng Java 17 trở lên:

```text
javac --release 17 LegacyTimeBridgeDemo.java
java LegacyTimeBridgeDemo
```

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.temporal.ChronoUnit;
import java.util.Calendar;
import java.util.Date;
import java.util.GregorianCalendar;
import java.util.Locale;
import java.util.TimeZone;

public class LegacyTimeBridgeDemo {
    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        Instant precise = Instant.parse("2024-06-15T03:20:30.123456789Z");
        Instant millisPrecision = precise.truncatedTo(ChronoUnit.MILLIS);
        Date oldDate = Date.from(precise);
        Instant returned = oldDate.toInstant();
        check(returned.equals(millisPrecision), "Date millisecond precision");
        check(!returned.equals(precise), "sub-millisecond part lost");
        check(oldDate.getTime() == precise.toEpochMilli(), "same epoch millis");
        System.out.println("instant-original=" + precise);
        System.out.println("date-round-trip=" + returned);

        oldDate.setTime(0);
        check(returned.equals(millisPrecision), "Instant is independent");
        System.out.println("date-after-mutation=" + oldDate.toInstant());
        System.out.println("snapshot-after-mutation=" + returned);

        Date anotherDate = Date.from(returned);
        check(anotherDate.toInstant().equals(returned), "exact Date round trip");
        Instant beforeEpoch = Instant.parse("1969-12-31T23:59:59.999999999Z");
        Date oldBeforeEpoch = Date.from(beforeEpoch);
        check(oldBeforeEpoch.getTime() == -1L, "negative epoch millis");
        check(oldBeforeEpoch.toInstant().equals(
                beforeEpoch.truncatedTo(ChronoUnit.MILLIS)), "negative precision");
        System.out.println("before-epoch-millis=" + oldBeforeEpoch.getTime());
        System.out.println("before-epoch-returned=" + oldBeforeEpoch.toInstant());

        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
        ZonedDateTime zoned = precise.atZone(vietnam);
        GregorianCalendar oldCalendar = GregorianCalendar.from(zoned);
        check(oldCalendar.toInstant().equals(millisPrecision), "calendar precision");
        check(oldCalendar.getTimeZone().toZoneId().equals(vietnam), "zone retained");
        check(oldCalendar.get(Calendar.MONTH) == Calendar.JUNE, "month index");
        ZonedDateTime zonedReturned = oldCalendar.toZonedDateTime();
        check(zonedReturned.equals(millisPrecision.atZone(vietnam)), "zoned result");
        System.out.println("zoned-original=" + zoned);
        System.out.println("calendar-round-trip=" + zonedReturned);

        Calendar generic = oldCalendar;
        ZonedDateTime genericReturned = generic.toInstant()
                .atZone(generic.getTimeZone().toZoneId());
        check(genericReturned.equals(zonedReturned), "generic Calendar bridge");
        ZonedDateTime utcView = generic.toInstant().atZone(ZoneId.of("UTC"));
        check(utcView.toInstant().equals(genericReturned.toInstant()), "same instant");
        check(utcView.getHour() == 3, "UTC hour");
        check(genericReturned.getHour() == 10, "Vietnam hour");
        System.out.println("generic-path-matches=" + genericReturned.equals(zonedReturned));
        System.out.println("utc-view=" + utcView);

        GregorianCalendar configured = new GregorianCalendar(
                TimeZone.getTimeZone(vietnam), Locale.ROOT);
        configured.setTimeInMillis(millisPrecision.toEpochMilli());
        configured.setLenient(false);
        configured.setFirstDayOfWeek(Calendar.SUNDAY);
        configured.setMinimalDaysInFirstWeek(1);
        GregorianCalendar rebuilt = GregorianCalendar.from(
                configured.toZonedDateTime());
        boolean sameMillis = configured.getTimeInMillis()
                == rebuilt.getTimeInMillis();
        boolean equalCalendars = configured.equals(rebuilt);
        check(sameMillis, "same millis after rebuilding");
        check(!equalCalendars, "configuration differs");
        check(rebuilt.getFirstDayOfWeek() == Calendar.MONDAY, "ISO first weekday");
        check(rebuilt.getMinimalDaysInFirstWeek() == 4, "ISO first week");
        check(rebuilt.getGregorianChange().getTime() == Long.MIN_VALUE,
                "pure Gregorian calendar");
        System.out.println("rebuilt-same-millis=" + sameMillis);
        System.out.println("rebuilt-calendar-equals=" + equalCalendars);

        Instant snapshot = configured.toInstant();
        configured.add(Calendar.DAY_OF_MONTH, 1);
        check(snapshot.equals(millisPrecision), "calendar snapshot independent");
        check(!configured.toInstant().equals(snapshot), "calendar changed");
        System.out.println("calendar-snapshot=" + snapshot);

        boolean rangeRejected = false;
        try {
            Date.from(Instant.MAX);
        } catch (IllegalArgumentException expected) {
            rangeRejected = true;
        }
        check(rangeRejected, "Date range checked");
        System.out.println("date-range-rejected=" + rangeRejected);
        System.out.println("PASS");
    }
}
```

Đầu ra:

```text
instant-original=2024-06-15T03:20:30.123456789Z
date-round-trip=2024-06-15T03:20:30.123Z
date-after-mutation=1970-01-01T00:00:00Z
snapshot-after-mutation=2024-06-15T03:20:30.123Z
before-epoch-millis=-1
before-epoch-returned=1969-12-31T23:59:59.999Z
zoned-original=2024-06-15T10:20:30.123456789+07:00[Asia/Ho_Chi_Minh]
calendar-round-trip=2024-06-15T10:20:30.123+07:00[Asia/Ho_Chi_Minh]
generic-path-matches=true
utc-view=2024-06-15T03:20:30.123Z[UTC]
rebuilt-same-millis=true
rebuilt-calendar-equals=false
calendar-snapshot=2024-06-15T03:20:30.123Z
date-range-rejected=true
PASS
```

Hàm `check` chủ động ném `AssertionError`, nên không cần bật `-ea`. Chương trình in `Instant` và `ZonedDateTime` thay vì dùng chuỗi `Date.toString()` phụ thuộc cách trình bày theo múi giờ mặc định.

Đặc biệt, dòng `rebuilt-calendar-equals=false` không báo chuyển sai thời điểm: dòng trước đã xác nhận epoch millis giống nhau. Nó minh họa việc mất/đổi cấu hình khi chuyển qua một kiểu không mang toàn bộ cấu hình lịch nguồn.

## 9. Những tên Date dễ bị nhập nhằng

Trong bài, tên `Date` chủ yếu chỉ `java.util.Date` thông thường. JDBC có những lớp khác kế thừa nó nhưng hợp đồng khác.

### 9.1 java.sql.Date là ngày SQL

`java.sql.Date.toInstant()` luôn ném `UnsupportedOperationException`, vì SQL DATE biểu diễn ngày, không có thành phần thời gian theo hợp đồng của kiểu. Dùng `toLocalDate()` và chiều về `java.sql.Date.valueOf(localDate)` cho dữ liệu ngày.

Ngay cả khi biến được khai báo là `java.util.Date`, đối tượng thực tế là `java.sql.Date` vẫn gọi phương thức override. Vì vậy, một hàm “nhận mọi Date rồi gọi toInstant” cần được xem lại nếu dữ liệu đến từ JDBC. Xem [java.sql.Date.toInstant](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Date.html#toInstant()).

Đừng dùng `Instant.ofEpochMilli(sqlDate.getTime())` chỉ để né ngoại lệ rồi coi đó là chuyển đổi đúng ngữ nghĩa ngày SQL. Nó đưa vào giả định về một thời điểm mà dữ liệu ngày có thể không hề định nghĩa.

### 9.2 Timestamp có thể giữ nano giây

`java.sql.Timestamp` hỗ trợ thành phần nano giây và có `toInstant()`/`from(Instant)` riêng. Không tự hạ mọi `Timestamp` về `new java.util.Date(timestamp.getTime())` nếu hợp đồng cần độ chính xác cao hơn mili giây. Xem [Java SE 21 Timestamp](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Timestamp.html#toInstant()).

Với cơ sở dữ liệu, còn phải hiểu kiểu cột, driver và hợp đồng múi giờ của dữ liệu. Cầu nối trong bài không tự quyết định ý nghĩa của một cột SQL chỉ dựa vào tên lớp Java.

## 10. Lỗi thường gặp và cách sửa có chủ đích

| Lỗi | Vì sao sai hoặc dễ gây lỗi | Hướng sửa |
| --- | --- | --- |
| Format `Date` ra chuỗi rồi parse thành `Instant` | Thêm mẫu, locale và quy tắc múi giờ không cần thiết | Gọi `toInstant()` khi đúng loại dữ liệu |
| Trừ/cộng độ lệch để “đổi Date sang UTC” | Thay đổi thời điểm vốn đã có | Chuyển thẳng; chỉ chọn vùng khi trình bày |
| Dùng `ofEpochSecond(date.getTime())` | Nhầm mili giây với giây | Dùng `ofEpochMilli` |
| Gọi `calendar.toZonedDateTime()` | Phương thức không thuộc kiểu `Calendar` | Dùng `toInstant().atZone(...)` hoặc đúng `GregorianCalendar` |
| Ép mọi `Calendar` thành `GregorianCalendar` | Lớp thực tế có thể khác | Dùng đường chuyển chung nếu chỉ cần thời điểm và vùng |
| So sánh tuyệt đối nano giây sau khi qua `Date` | Đích chỉ giữ mili giây | Kiểm tra theo độ chính xác đã chốt |
| Chỉ so sánh `Calendar.equals` khi cần kiểm tra thời điểm | Cấu hình cũng tham gia phép bằng | So sánh `toInstant()` hoặc epoch millis |
| Dùng múi giờ mặc định của máy cho mọi lịch nguồn | Có thể làm thay đổi vùng nghiệp vụ | Giữ vùng nguồn hoặc chỉ rõ vùng đích |
| Chuyển `java.sql.Date` như dấu thời gian | Sai hợp đồng ngày SQL; có thể ném ngoại lệ | Dùng `LocalDate` cho hợp đồng chỉ có ngày |

Với `null`, chọn chính sách rõ: từ chối ở ranh giới, dùng `Optional` nếu phù hợp, hoặc biểu diễn giá trị thiếu theo quy ước đã thống nhất. Không biến `null` thành “bây giờ” hay epoch nếu hợp đồng không yêu cầu; điều đó tạo ra dữ liệu có vẻ hợp lệ nhưng sai ý nghĩa.

## 11. Bài tập thực hành

### Bài 1 — Chọn đúng cầu nối

Một phương thức trả `java.util.Date` của thời điểm thanh toán. Phần nghiệp vụ chỉ cần thứ tự xảy ra các sự kiện, chưa cần hiển thị giờ địa phương. Chọn kiểu đích và cách chuyển.

**Gợi ý giải:** dùng `Instant` và gọi `date.toInstant()`. Không cần chọn múi giờ ở bước này. Nếu nguồn có thể là lớp JDBC, xác định loại và hợp đồng trước.

### Bài 2 — Tìm lỗi mất chính xác

Một kiểm thử lấy `Instant.parse("2024-01-01T00:00:00.000000001Z")`, chuyển sang `Date` rồi lại thành `Instant`, sau đó so sánh bằng tuyệt đối. Vì sao thất bại?

**Gợi ý giải:** một nano giây không thể hiện được trong mili giây của `Date`. Kết quả về `2024-01-01T00:00:00Z`. Kiểm thử phải xác nhận việc hạ chính xác đúng hợp đồng, hoặc yêu cầu hệ thống dùng kiểu đích giữ được nano giây.

### Bài 3 — Kiểm tra chiều âm

Dự đoán epoch millis khi chuyển `1969-12-31T23:59:59.999999999Z` sang `Date`.

**Gợi ý giải:** `-1`. Thêm phép thử cho đúng epoch và một mili giây trước epoch; nhóm giá trị này phát hiện lỗi chia nguyên tự viết ở phần âm.

### Bài 4 — Giữ vùng nguồn

Bạn có biến kiểu `Calendar` ở múi giờ `Asia/Ho_Chi_Minh` và muốn giữ vùng này trong kết quả hiện đại. Viết biểu thức không ép kiểu.

**Gợi ý giải:** `calendar.toInstant().atZone(calendar.getTimeZone().toZoneId())`. Đảm bảo nguồn không bị sửa đồng thời trong lúc lấy thời điểm và vùng. Nếu hợp đồng yêu cầu chụp nhất quán khi có nhiều luồng, dùng cơ chế sở hữu/đồng bộ đã chọn.

### Bài 5 — Xác định điều kiện khứ hồi

Một lịch nguồn nghiêm ngặt, bắt đầu tuần Chủ nhật, được chuyển sang `ZonedDateTime` rồi trở về bằng `GregorianCalendar.from(...)`. `equals` trả `false`. Có kết luận được thời điểm bị đổi không?

**Gợi ý giải:** chưa. So sánh epoch millis riêng. Sau đó kiểm tra cấu hình tuần, lenient và điểm chuyển lịch. Phân biệt thất bại về dữ liệu thời điểm với khác biệt cấu hình.

### Bài 6 — Phân biệt ngày và thời điểm

Một giá trị `java.sql.Date` là ngày sinh. Có nên bọc lại thành `java.util.Date` để gọi `toInstant()` không?

**Gợi ý giải:** không khi yêu cầu chỉ có ngày. Chọn `toLocalDate()`. Nếu hệ thống bắt buộc chuyển ngày thành thời điểm, cần quy định thêm múi giờ và giờ trong ngày; đó là một quyết định nghiệp vụ bổ sung.

## 12. Tiêu chí áp dụng đúng

Một phép chuyển đổi tốt cho biết rõ kiểu nguồn thực tế, ý nghĩa dữ liệu, múi giờ cần dùng và độ chính xác có thể bị mất. Kiểm thử nên đối chiếu thời điểm, vùng và cấu hình theo từng yêu cầu riêng.

Khi phải nối API cũ với mới, dùng các phương thức chuyển đổi trực tiếp và đặt chúng tại ranh giới giao tiếp. Với `Date`/lịch cũ thông thường, thời điểm ở mili giây là nền tảng chung; mọi yêu cầu bảo toàn cao hơn cần được xác định và kiểm tra thêm.
