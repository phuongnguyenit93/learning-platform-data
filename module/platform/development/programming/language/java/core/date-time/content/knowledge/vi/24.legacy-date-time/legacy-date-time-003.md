# Calendar, GregorianCalendar và TimeZone

## 1. Mô hình cần nắm trước khi đọc mã cũ

Một hệ thống cũ nhận “09:00 ngày 31/01/2024 ở Việt Nam”. Muốn biến thông tin này thành thời điểm có thể lưu hoặc so sánh, chương trình cần cả ngày giờ trên lịch lẫn quy tắc múi giờ. Trong nhóm API cũ của Java, ba lớp sau cùng tham gia công việc đó:

| Thành phần | Trách nhiệm | Câu hỏi nó giúp trả lời |
| --- | --- | --- |
| `Calendar` | Lớp trừu tượng chuyển đổi giữa thời điểm tính bằng mili giây từ epoch và tập trường như năm, tháng, ngày, giờ | “Thời điểm này có những trường lịch nào, và sửa chúng ra sao?” |
| `GregorianCalendar` | Một lớp triển khai cụ thể của `Calendar`, với quy tắc lịch Julian/Gregorian | “Độ dài tháng và năm nhuận được xác định theo lịch nào?” |
| `TimeZone` | Biểu diễn múi giờ, độ lệch và quy tắc giờ mùa hè nếu có | “Tại thời điểm này, giờ địa phương lệch UTC bao nhiêu?” |

Một đối tượng `Calendar` kết hợp thời điểm, trường lịch và cấu hình như múi giờ, quy tắc tuần, chế độ kiểm tra dữ liệu. Vì vậy, chỉ nhìn một giá trị `YEAR` hoặc `HOUR_OF_DAY` chưa đủ hiểu toàn bộ đối tượng. Vai trò chuyển đổi của `Calendar` được mô tả trong [Java SE 21 Calendar](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Calendar.html).

Ví dụ tư duy: cùng thời điểm `2024-01-31T02:00:00Z`, đồng hồ tại múi giờ `Asia/Ho_Chi_Minh` chỉ 09:00. Khi đổi cách quan sát sang UTC và giữ thời điểm, giờ đọc được thành 02:00. Không có bảy giờ nào trôi qua trong thao tác đổi múi giờ đó.

Sau bài này, bạn cần đọc được mã dùng các trường `Calendar`, chủ động kiểm tra ngày không hợp lệ, phân biệt `set`, `add`, `roll`, và đặt việc chuyển sang `java.time` đúng ở ranh giới giao tiếp với thư viện cũ.

## 2. Vì sao vẫn học nhóm API này?

Trong mã mới, các kiểu như `LocalDate`, `Instant`, `ZonedDateTime` giúp biểu đạt mục đích rõ hơn. Tuy nhiên, nhiều thư viện, hợp đồng dữ liệu và chương trình tồn tại lâu năm vẫn dùng `Date`, `Calendar`, `GregorianCalendar`, `TimeZone`. Đọc hiểu chúng giúp sửa lỗi có kiểm soát và viết lớp chuyển đổi mà không thay đổi ý nghĩa dữ liệu.

`Calendar`, `GregorianCalendar`, `TimeZone` không đồng nghĩa với “toàn bộ API đã bị đánh dấu deprecated”. Đây là nhóm API lâu đời; một số phương thức của `Date` bị deprecated là chuyện riêng. Khi sửa mã, hãy xem đúng phương thức đang dùng.

Một cách đặt ranh giới dễ quản lý là:

```text
Thư viện cũ trả Calendar/Date
          ↓ chuyển đổi ngay ở đầu vào
Instant hoặc kiểu java.time phù hợp
          ↓ xử lý nghiệp vụ
Chuyển lại kiểu cũ khi hợp đồng đầu ra bắt buộc
```

Ví dụ, dấu thời gian của một giao dịch phù hợp với `Instant`. Lịch hẹn theo địa phương cần giữ thông tin múi giờ thích hợp. Ngày sinh chỉ cần ngày trên lịch; việc ép thành `Calendar` rồi chọn 00:00 ở múi giờ bất kỳ có thể tạo thêm giả định không thuộc dữ liệu gốc.

## 3. Khởi tạo và đọc trường: tránh các giả định ngầm

### 3.1 Calendar là kiểu trừu tượng

Có thể lấy một đối tượng qua `Calendar.getInstance(zone, locale)`. Khi cần chắc chắn đang dùng quy tắc `GregorianCalendar`, hãy tạo trực tiếp lớp đó. Không nên viết mã ép kiểu mọi kết quả `Calendar.getInstance()` thành `GregorianCalendar`: loại lịch còn có thể phụ thuộc cấu hình locale.

```java
TimeZone zone = TimeZone.getTimeZone("Asia/Ho_Chi_Minh");
GregorianCalendar calendar = new GregorianCalendar(zone, Locale.ROOT);
calendar.clear();
calendar.setLenient(false);
calendar.set(2024, Calendar.JANUARY, 31, 9, 0, 0);
calendar.set(Calendar.MILLISECOND, 0);
long epochMillis = calendar.getTimeInMillis();
```

Đoạn này giả định đã import các lớp `java.util` tương ứng. Chương trình đầy đủ nằm ở phần minh chứng.

Constructor khởi tạo đối tượng theo thời gian hiện tại. `clear()` đưa các trường về trạng thái chưa được đặt, giúp lần dựng dữ liệu mới không mang theo trường của lần trước. Sau đó ta đặt rõ những thành phần đầu vào cần sử dụng. `clear()` không xóa cấu hình múi giờ và không có nghĩa “gán mọi trường bằng số 0”; khi cần tính thời điểm, lớp lịch cung cấp giá trị mặc định cho những trường chưa đặt.

Thao tác đặt thêm mili giây bằng 0 trong ví dụ làm ý định chính xác tới giây hiện rõ. Khi đã `clear()`, trường mili giây chưa đặt của `GregorianCalendar` cũng có mặc định 0.

### 3.2 Không dùng một quy tắc đánh số cho mọi trường

| Trường trong GregorianCalendar | Cách hiểu |
| --- | --- |
| `MONTH` | Tháng Một là `JANUARY = 0`, tháng Mười Hai là `DECEMBER = 11` |
| `DAY_OF_MONTH` | Ngày trong tháng bắt đầu từ 1 |
| `DAY_OF_WEEK` | Dùng hằng `SUNDAY` đến `SATURDAY`; Chủ nhật có giá trị 1 |
| `HOUR_OF_DAY` | Giờ theo hệ 24 giờ, từ 0 đến 23 |
| `HOUR` | Giờ theo hệ 12 giờ, từ 0 đến 11; phải xét cùng `AM_PM` |
| `MILLISECOND` | Phần mili giây trong giây, từ 0 đến 999 |

Hãy viết `Calendar.JANUARY` thay vì số 0 trong đầu vào. Khi hiển thị tháng theo số thông thường, dùng `calendar.get(Calendar.MONTH) + 1`. Không cộng 1 vào `DAY_OF_MONTH`.

Ví dụ, 15:00 có `HOUR_OF_DAY = 15`, nhưng `HOUR = 3` và `AM_PM = PM`. Nếu đọc `HOUR` rồi bỏ `AM_PM`, dữ liệu buổi chiều dễ biến thành buổi sáng.

Với `DAY_OF_WEEK`, đừng lấy số rồi chuyển trực tiếp sang `DayOfWeek.of(...)`: `java.time.DayOfWeek` đánh số thứ Hai bằng 1. Chuyển qua kiểu ngày hiện đại hoặc ánh xạ bằng tên hằng để tránh nhầm quy ước.

### 3.3 Locale và múi giờ có tác dụng khác nhau

Múi giờ giúp chuyển giữa thời điểm và giờ địa phương. Locale có thể ảnh hưởng lựa chọn lịch qua factory và cấu hình tuần như ngày bắt đầu tuần, số ngày tối thiểu của tuần đầu tiên. Chọn locale Việt Nam không tự thay thế việc chọn `Asia/Ho_Chi_Minh`.

Trong bài, `Locale.ROOT` giữ cấu hình ví dụ rõ ràng và không phụ thuộc locale mặc định của máy. Chúng ta không suy ra tuần ISO từ locale này. Nếu mã cũ cần tuần ISO với `GregorianCalendar`, phải xem cả `firstDayOfWeek`, `minimalDaysInFirstWeek` và năm theo tuần.

## 4. set không bảo đảm dữ liệu đã hợp lệ

### 4.1 Chế độ lenient có thể sửa ngày ngoài phạm vi

Theo mặc định, lịch mới dùng chế độ dễ dãi, gọi là `lenient`. Trong chế độ này, một giá trị vượt phạm vi có thể được chuẩn hóa. Chẳng hạn, ngày 32 tháng Một trở thành ngày 1 tháng Hai.

Điều này có ích khi mã cũ cố tình biểu diễn phép dịch chuyển bằng trường vượt phạm vi. Nhưng với dữ liệu người dùng, việc tự chuyển “31/02” sang tháng Ba thường che giấu lỗi nhập.

```java
calendar.clear();
calendar.setLenient(false);
calendar.set(2024, Calendar.FEBRUARY, 31, 0, 0, 0);
calendar.getTimeInMillis(); // IllegalArgumentException
```

Điểm quan trọng nằm ở dòng cuối: `set(...)` ghi các trường, còn việc diễn giải chúng thành thời điểm có thể xảy ra muộn. `getTimeInMillis()`, `getTime()` hoặc việc đọc trường có thể kích hoạt tính toán và phát hiện lỗi. Vì vậy, đặt `try/catch` chỉ quanh `set(...)` chưa chắc bắt được ngày sai.

Với đầu vào cần kiểm tra nghiêm ngặt, đặt `setLenient(false)` rồi chủ động gọi `getTimeInMillis()` trong cùng phạm vi xử lý lỗi. Khi tính thất bại, không tiếp tục coi đối tượng đang chứa một ngày đã được kiểm chứng. Mỗi lần thử có thể tạo đối tượng mới hoặc xóa và đặt lại đầy đủ.

### 4.2 Thứ tự thao tác có ý nghĩa

Giả sử một lịch đang ở ngày 31/01/2024. Gọi `set(MONTH, FEBRUARY)` tạo tổ hợp trường “31 tháng Hai” trước khi tính lại. Trong chế độ dễ dãi, nếu đọc thời điểm ngay, kết quả có thể sang tháng Ba. Nếu đặt tiếp ngày về 29 trước khi đọc, tổ hợp đầu vào lại khác.

Do đó, một câu lệnh ghi log gọi `getTime()` nằm giữa hai lần `set(...)` có thể làm quá trình chuẩn hóa diễn ra sớm hơn người đọc mong đợi. Cách an toàn là dựng đầy đủ các trường từ đầu và xác thực tại một chỗ rõ ràng. Quy tắc tính toán trì hoãn và chuẩn hóa được trình bày trong [Calendar: đặt và điều chỉnh trường](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Calendar.html#field-manipulation).

## 5. set, add và roll trả lời ba nhu cầu khác nhau

Cả ba đều thay đổi chính đối tượng đang giữ. Nếu cần giữ bản gốc, tạo bản sao trước khi thao tác.

| Lệnh từ ngày 31/01/2024 | Ý nghĩa cần hiểu | Kết quả trong ví dụ |
| --- | --- | --- |
| `set(DAY_OF_MONTH, 1)` | Gán trường ngày thành một giá trị | 01/01/2024 |
| `add(DAY_OF_MONTH, 1)` | Cộng một ngày theo lịch; cho phép chuyển tháng | 01/02/2024 |
| `roll(DAY_OF_MONTH, 1)` | Quay vòng trường ngày trong phạm vi tháng đang xét | 01/01/2024 |
| `add(MONTH, 1)` | Cộng một tháng và điều chỉnh ngày cho hợp lệ | 29/02/2024 |

Ví dụ `roll` cho thấy cùng tăng trường ngày nhưng tháng không tăng như `add`. Đừng dùng `roll` để tính “ngày mai”. Với các trường khác, tác động lên trường nhỏ hơn cần đọc hợp đồng riêng; không suy diễn từ một ví dụ ngày trong tháng thành quy tắc đơn giản cho mọi trường.

Từ 31/01, cộng một tháng ra 29/02 trong năm nhuận 2024. Nếu sau đó cộng tiếp một tháng, kết quả là 29/03; ngày 31 ban đầu không tự được nhớ lại. Nếu nghiệp vụ yêu cầu “luôn là ngày cuối tháng”, cần biểu đạt quy tắc đó riêng.

Phép cộng ngày trên lịch cũng không nên được thay bằng cộng `86_400_000L` mili giây. Tại nơi đổi giờ mùa hè, một ngày địa phương có thể không dài đúng 24 giờ. Muốn tăng ngày trên lịch hay tăng thời lượng thực là hai lựa chọn cần được xác định trước khi viết phép tính.

## 6. TimeZone: tên múi giờ, độ lệch và lỗi cấu hình

### 6.1 Ưu tiên tên vùng rõ ràng

`Asia/Ho_Chi_Minh` và `America/New_York` là các tên vùng. Độ lệch của vùng được xác định theo thời điểm và dữ liệu quy tắc mà JDK cung cấp. Một cấu hình cố định như `GMT+07:00` chỉ biểu đạt độ lệch cố định; nó không mang cùng ý nghĩa lịch sử với tên vùng.

Các tên viết tắt như `CST` dễ gây hiểu lầm giữa các khu vực. Dùng tên vùng đầy đủ khi yêu cầu nghiệp vụ là giờ tại một địa phương.

Bẫy đáng nhớ: `TimeZone.getTimeZone(String)` có thể trả về GMT khi không hiểu tên được đưa vào. Ví dụ gõ nhầm `Asia/Ho_Chi_Min` có thể âm thầm làm lệch giờ. Hành vi trả GMT và sự khác nhau giữa độ lệch gốc với độ lệch tại thời điểm được ghi trong [Java SE 21 TimeZone](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TimeZone.html).

Khi cấu hình đầu vào dùng tên vùng được `java.time` hỗ trợ, có thể xác thực trước:

```java
ZoneId zoneId = ZoneId.of(configuredZoneId);
TimeZone legacyZone = TimeZone.getTimeZone(zoneId);
```

`ZoneId.of(...)` từ chối tên không hợp lệ hoặc không có quy tắc tương ứng bằng ngoại lệ thay vì âm thầm trả GMT. Đây là lựa chọn xác thực cho cấu hình theo hợp đồng `ZoneId`; không tự động coi mọi cú pháp tùy biến cũ đều tương đương. Xem [ZoneId.of](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZoneId.html#of(java.lang.String)).

### 6.2 getRawOffset khác getOffset(epochMillis)

`getRawOffset()` không tính phần thay đổi do giờ mùa hè. `getOffset(epochMillis)` trả độ lệch áp dụng tại thời điểm đầu vào. Đơn vị của cả hai là mili giây.

Trong phép thử ở phần sau, New York tại `2024-07-01T12:00:00Z` có độ lệch -4 giờ; độ lệch gốc trong dữ liệu JDK thử nghiệm là -5 giờ. Nếu dùng độ lệch gốc để tính giờ mùa hè, kết quả sai một giờ. Đừng dùng kết quả này làm cam kết quy tắc cho mọi năm tương lai: dữ liệu múi giờ còn phụ thuộc bản JDK/TZDB.

Tương tự, việc đổi tên qua `TimeZone.setID(...)` không có nghĩa tải lại bộ quy tắc của múi giờ mới. Khi cần một múi giờ khác, tạo đúng `TimeZone` từ ID đã xác thực.

### 6.3 Đổi múi giờ có giữ nguyên thời điểm không?

Nếu đã có thời điểm hợp lệ trong `Calendar`, đổi múi giờ bằng `setTimeZone(...)` cho phép đọc các trường địa phương theo múi giờ mới mà giữ thời điểm đó. Ví dụ, 09:00 ở Việt Nam thành 02:00 UTC.

Nếu yêu cầu là “giữ nguyên 09:00 trên mặt đồng hồ nhưng chuyển lịch hẹn sang múi giờ khác”, đó là một thao tác khác: phải lấy các trường địa phương và dựng thời điểm mới theo quy tắc múi giờ đích, đồng thời quyết định cách xử lý khoảng giờ không tồn tại hoặc lặp lại. Không dùng việc đổi cấu hình múi giờ làm đại diện cho yêu cầu này.

## 7. GregorianCalendar và ranh giới lịch sử

Tên `GregorianCalendar` dễ khiến người đọc tưởng mọi ngày đều theo lịch Gregorian kéo dài vô hạn. Cấu hình mặc định thực tế có điểm chuyển: trước đó dùng Julian, từ đó dùng Gregorian; mốc mặc định là ngày 15/10/1582 theo Gregorian. Đây là mô hình chuyển lịch của API, không phải tuyên bố mọi quốc gia đều đổi lịch cùng ngày.

`LocalDate` và `ZonedDateTime` dùng lịch ISO theo quy tắc Gregorian kéo dài về quá khứ. Với dữ liệu hiện đại trong ví dụ, khác biệt này không gây đổi nhãn ngày. Với hồ sơ cổ, cùng thời điểm chuyển sang hệ lịch khác có thể mang nhãn ngày khác.

`GregorianCalendar.toZonedDateTime()` giữ thời điểm và dùng hệ lịch ISO ở kết quả. Chiều ngược lại, `GregorianCalendar.from(zdt)` tạo lịch Gregorian thuần và cấu hình tuần theo ISO; nó không phục hồi tự động mọi thuộc tính lịch ban đầu. Hợp đồng được mô tả trong [GregorianCalendar: chuyển đổi và điểm đổi lịch](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/GregorianCalendar.html).

Nếu dữ liệu yêu cầu Gregorian thuần khi vẫn phải dùng lớp cũ, có thể cấu hình `setGregorianChange(new Date(Long.MIN_VALUE))`. Chỉ làm khi đó là quy tắc được chọn cho dữ liệu. Không âm thầm thay điểm chuyển trong một đợt sửa lỗi thông thường vì có thể đổi cách hiểu ngày lịch sử.

## 8. Minh chứng chạy được

Chương trình sau dùng ngày giờ cố định, múi giờ chỉ định rõ và không đọc đồng hồ hiện tại để tạo kết quả nghiệp vụ. Nó kiểm tra tháng bắt đầu từ 0, kiểm tra nghiêm ngặt, phép cộng/quay vòng, đổi múi giờ và cầu nối sang `java.time`.

Lưu thành `LegacyCalendarDemo.java`, biên dịch và chạy bằng Java 17 trở lên:

```text
javac --release 17 LegacyCalendarDemo.java
java LegacyCalendarDemo
```

```java
import java.util.Calendar;
import java.util.Date;
import java.util.GregorianCalendar;
import java.util.Locale;
import java.util.TimeZone;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.zone.ZoneRulesException;

public class LegacyCalendarDemo {
    private static GregorianCalendar create(
            int year, int month, int day, int hour, TimeZone zone) {
        GregorianCalendar c = new GregorianCalendar(zone, Locale.ROOT);
        c.clear();
        c.setLenient(false);
        c.set(year, month, day, hour, 0, 0);
        c.set(Calendar.MILLISECOND, 0);
        c.getTimeInMillis();
        return c;
    }

    private static String date(Calendar c) {
        return String.format(Locale.ROOT, "%04d-%02d-%02d",
                c.get(Calendar.YEAR), c.get(Calendar.MONTH) + 1,
                c.get(Calendar.DAY_OF_MONTH));
    }

    private static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        TimeZone vietnam = TimeZone.getTimeZone(
                ZoneId.of("Asia/Ho_Chi_Minh"));
        GregorianCalendar original = create(
                2024, Calendar.JANUARY, 31, 9, vietnam);

        System.out.println("month-index=" + original.get(Calendar.MONTH));
        System.out.println("original=" + date(original));
        check(original.get(Calendar.MONTH) == 0, "January index");

        GregorianCalendar added = (GregorianCalendar) original.clone();
        added.add(Calendar.DAY_OF_MONTH, 1);
        GregorianCalendar rolled = (GregorianCalendar) original.clone();
        rolled.roll(Calendar.DAY_OF_MONTH, 1);
        GregorianCalendar nextMonth = (GregorianCalendar) original.clone();
        nextMonth.add(Calendar.MONTH, 1);
        check(date(added).equals("2024-02-01"), "add day");
        check(date(rolled).equals("2024-01-01"), "roll day");
        check(date(nextMonth).equals("2024-02-29"), "add month");
        check(date(original).equals("2024-01-31"), "original unchanged");
        System.out.println("add-day=" + date(added));
        System.out.println("roll-day=" + date(rolled));
        System.out.println("add-month=" + date(nextMonth));

        GregorianCalendar invalid = new GregorianCalendar(
                TimeZone.getTimeZone("UTC"), Locale.ROOT);
        invalid.clear();
        invalid.setLenient(false);
        invalid.set(2024, Calendar.FEBRUARY, 31, 0, 0, 0);
        boolean rejected = false;
        try {
            invalid.getTimeInMillis();
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        check(rejected, "invalid date rejected");
        System.out.println("strict-rejected=" + rejected);

        GregorianCalendar normalized = new GregorianCalendar(
                TimeZone.getTimeZone("UTC"), Locale.ROOT);
        normalized.clear();
        normalized.setLenient(true);
        normalized.set(2024, Calendar.JANUARY, 32, 0, 0, 0);
        check(date(normalized).equals("2024-02-01"), "lenient date");
        System.out.println("lenient=" + date(normalized));

        long millis = original.getTimeInMillis();
        GregorianCalendar utcView = (GregorianCalendar) original.clone();
        utcView.setTimeZone(TimeZone.getTimeZone("UTC"));
        check(utcView.getTimeInMillis() == millis, "same instant");
        check(utcView.get(Calendar.HOUR_OF_DAY) == 2, "UTC hour");
        System.out.println("utc-hour=" + utcView.get(Calendar.HOUR_OF_DAY));
        System.out.println("instant=" + Instant.ofEpochMilli(millis));

        Date oldDate = original.getTime();
        ZonedDateTime modern = original.toZonedDateTime();
        GregorianCalendar restored = GregorianCalendar.from(modern);
        check(oldDate.toInstant().equals(modern.toInstant()), "Date bridge");
        check(restored.getTimeInMillis() == millis, "round trip millis");
        check(modern.getZone().equals(vietnam.toZoneId()), "zone bridge");
        System.out.println("bridge-instant=" + modern.toInstant());

        String unknown = "Invalid/DefinitelyMissing";
        check(TimeZone.getTimeZone(unknown).getID().equals("GMT"),
                "legacy fallback");
        boolean zoneRejected = false;
        try {
            ZoneId.of(unknown);
        } catch (ZoneRulesException expected) {
            zoneRejected = true;
        }
        check(zoneRejected, "unknown zone rejected");
        System.out.println("unknown-zone="
                + TimeZone.getTimeZone(unknown).getID());
        System.out.println("modern-zone-rejected=" + zoneRejected);

        TimeZone newYork = TimeZone.getTimeZone(
                ZoneId.of("America/New_York"));
        long summer = Instant.parse("2024-07-01T12:00:00Z").toEpochMilli();
        int offsetHours = newYork.getOffset(summer) / 3_600_000;
        int rawHours = newYork.getRawOffset() / 3_600_000;
        check(offsetHours == -4, "summer offset");
        check(rawHours == -5, "raw offset in test JDK");
        System.out.println("new-york-summer-offset=" + offsetHours);
        System.out.println("new-york-raw-offset=" + rawHours);
        System.out.println("PASS");
    }
}
```

Kết quả:

```text
month-index=0
original=2024-01-31
add-day=2024-02-01
roll-day=2024-01-01
add-month=2024-02-29
strict-rejected=true
lenient=2024-02-01
utc-hour=2
instant=2024-01-31T02:00:00Z
bridge-instant=2024-01-31T02:00:00Z
unknown-zone=GMT
modern-zone-rejected=true
new-york-summer-offset=-4
new-york-raw-offset=-5
PASS
```

Các bản sao trong chương trình cho phép mỗi phép thử bắt đầu từ cùng ngày gốc. Hàm `check` ném `AssertionError` trực tiếp, nên chương trình không phụ thuộc tùy chọn `-ea`. Việc chuyển sang `Instant` để in đầu ra cũng tránh phụ thuộc múi giờ mặc định khi gọi `Date.toString()`.

## 9. Chuyển đổi mà vẫn giữ đúng ý nghĩa

### 9.1 Calendar sang Instant

Với một `Calendar` bất kỳ đã hợp lệ, dùng `calendar.toInstant()` hoặc `Instant.ofEpochMilli(calendar.getTimeInMillis())`. Nếu cần giữ cả vùng quan sát, lấy thêm `calendar.getTimeZone().toZoneId()` rồi dùng `instant.atZone(zoneId)`.

`toZonedDateTime()` là phương thức của `GregorianCalendar`. Đừng gọi nó trên biến khai báo kiểu `Calendar` hoặc ép kiểu không kiểm tra chỉ để chuyển đổi; đường đi qua `Instant` thường đủ cho một giá trị dấu thời gian.

### 9.2 Date không mang múi giờ riêng

`calendar.getTime()` trả một `Date` biểu diễn thời điểm theo mili giây. Múi giờ của lịch không được đóng gói thành một thuộc tính vùng riêng trong `Date`. Khi cần giữ múi giờ cho một lịch hẹn, truyền hoặc lưu thông tin vùng theo hợp đồng khác.

`Date.toInstant()` chuyển thời điểm đó sang kiểu hiện đại. Các phương thức chuyển đổi chính thức nằm trong [Java SE 21 Date](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Date.html#toInstant()).

### 9.3 Chiều về có thể mất độ chính xác và cấu hình

`GregorianCalendar` lưu thời điểm tới mili giây; `ZonedDateTime` có thể biểu diễn phần nano giây. Nếu chuyển một giá trị có phần nhỏ hơn mili giây sang `GregorianCalendar`, phần đó không được bảo toàn. Phép thử ở trên bắt đầu với đúng mili giây nên so sánh round-trip theo mili giây là phù hợp.

Cùng thời điểm không đồng nghĩa mọi thuộc tính hai lịch bằng nhau. `GregorianCalendar.from(...)` còn lựa chọn cấu hình lịch và tuần theo hợp đồng của nó. Đừng dùng một lần chuyển đi rồi chuyển về làm bằng chứng rằng `lenient`, điểm chuyển Julian/Gregorian và mọi cấu hình cũ đều được khôi phục.

## 10. Trạng thái thay đổi và phạm vi sở hữu

`Calendar` và `TimeZone` có các phương thức thay đổi trạng thái. Không chia sẻ một đối tượng lịch có thể bị sửa như biến dùng chung rồi để nhiều luồng đồng thời gọi `set`, `add`, `getTime` mà không có cơ chế phối hợp.

Một quy ước thực tế là mỗi thao tác sở hữu đối tượng cũ của riêng nó và chuyển sang giá trị `java.time` bất biến khi đi vào phần xử lý nội bộ. Nếu API nhận một `Calendar` của bên gọi nhưng cần sửa trường, hãy cân nhắc sao chép trước và ghi rõ hợp đồng.

Ngay cả một lệnh `get` cũng có thể kích hoạt tính toán các trường đang chờ. Vì thế, việc xem nó là “chỉ đọc một con số độc lập” bỏ qua mô hình trạng thái của lớp này.

Không sửa múi giờ mặc định toàn JVM để chữa một trường hợp nghiệp vụ. Truyền cấu hình múi giờ vào đúng đối tượng cần dùng giúp yêu cầu của thao tác hiện ra trong mã và tránh ảnh hưởng những phần khác.

## 11. Bài tập và lời giải gợi ý

### Bài 1 — Sửa lỗi tháng

Một phương thức muốn dựng ngày 10/01/2024 nhưng gọi `calendar.set(2024, 1, 10)`. Kết quả thuộc tháng nào trong `GregorianCalendar`?

**Gợi ý giải:** số 1 là tháng Hai. Đổi thành `Calendar.JANUARY`. Nếu đầu vào từ giao diện đánh số tháng 1–12, xác thực khoảng trước rồi chuyển sang quy ước API tại ranh giới nhận dữ liệu.

### Bài 2 — Bắt lỗi đúng chỗ

Đoạn mã gọi `setLenient(false)`, đặt ngày 31/02, ra khỏi `try`, rồi gọi `getTime()` để lưu. Vì sao vẫn có ngoại lệ ngoài phạm vi mong đợi?

**Gợi ý giải:** tính toán có thể trì hoãn đến khi đọc thời điểm. Đặt cả bước dựng trường và `getTimeInMillis()` trong phạm vi xử lý lỗi. Chỉ chuyển sang bước lưu sau khi bước xác thực thành công.

### Bài 3 — Kiểm tra phép cộng

Từ 31/12/2024, dự đoán `add(DAY_OF_MONTH, 1)` và `roll(DAY_OF_MONTH, 1)`.

**Gợi ý giải:** phép cộng ra 01/01/2025. Quay vòng ngày trong tháng Mười Hai ra 01/12/2024. Viết hai bản sao riêng và kiểm tra cả năm, tháng, ngày để thấy rõ phần nào chuyển.

### Bài 4 — Phát hiện cấu hình múi giờ sai

Một ứng dụng nhận `Asia/Ho_Chi_Min` rồi trực tiếp gọi `TimeZone.getTimeZone(...)`. Không có ngoại lệ nhưng thời điểm tính ra sai bảy giờ. Cần kiểm tra điều gì?

**Gợi ý giải:** xem ID trả về có phải GMT do tên bị gõ sai. Với cấu hình theo tên vùng `ZoneId`, xác thực bằng `ZoneId.of(...)` trước khi tạo `TimeZone`. Không quy kết lỗi dữ liệu cho server chỉ vì phương thức không ném ngoại lệ.

### Bài 5 — Chọn đại lượng để bảo toàn

Bạn đổi một lịch 09:00 ở Việt Nam sang UTC. Yêu cầu A là giữ thời điểm giao dịch; yêu cầu B là giữ lịch hẹn lúc 09:00 tại địa phương mới. Có cùng cách thực hiện không?

**Gợi ý giải:** A giữ epoch millis, kết quả đọc giờ UTC là 02:00 trong ví dụ. B giữ các trường ngày giờ địa phương rồi tạo thời điểm mới ở vùng đích; cần quy tắc xử lý trường hợp giờ địa phương không tồn tại hoặc lặp lại.

### Bài 6 — So sánh sau chuyển đổi

Một `ZonedDateTime` có nano giây `123456789` được chuyển sang `GregorianCalendar` rồi trở về. Có nên so sánh bằng tuyệt đối tới nano giây?

**Gợi ý giải:** không nếu hợp đồng đích chỉ lưu mili giây. Phần nhỏ hơn mili giây không còn được giữ. Chốt yêu cầu độ chính xác trước; nếu bắt buộc bảo toàn nano giây, thay đổi hợp đồng lưu/truyền thay vì mong API cũ giữ được.

## 12. Tự kiểm tra trước khi sửa mã cũ

Bạn đã hiểu bài khi giải thích được vì sao tháng Một có chỉ số 0, vì sao `set(...)` chưa chứng minh ngày hợp lệ, vì sao `roll` không phải phép tính ngày mai, và vì sao đổi múi giờ có thể đổi số giờ đọc được mà không đổi thời điểm.

Khi áp dụng, xác định rõ loại lịch, múi giờ và dữ liệu cần bảo toàn; dựng đủ trường, buộc kiểm tra tại điểm nhận dữ liệu, rồi chuyển sang kiểu hiện đại phù hợp. Với ngày lịch sử hoặc dữ liệu có độ chính xác dưới mili giây, bổ sung kiểm thử riêng theo hợp đồng thực tế.
