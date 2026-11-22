# Định dạng 12 giờ, 24 giờ và ký hiệu kỳ trong ngày với Java

## 1. Vấn đề: cùng một thời điểm nhưng có nhiều cách viết giờ

Một thời điểm 13 giờ 05 phút theo hệ 24 giờ có thể được viết là **13:05**, **1:05 PM** hoặc một biểu thức có kỳ trong ngày được bản địa hóa như **1:05 in the afternoon**. Các cách viết này không nhất thiết có cùng ngôn ngữ, nhưng đều có thể mô tả **13:05 trong cùng múi giờ**.

Với ứng dụng quốc tế hóa (*localization*), cần trả lời ba câu hỏi khác nhau:

1. Người dùng quen **đồng hồ 12 giờ hay 24 giờ**?
2. Nếu dùng đồng hồ 12 giờ, **ký hiệu AM/PM** hoặc cách nói “sáng”, “chiều”, “tối” sẽ được trình bày theo **locale** nào?
3. Số giờ đang format là **giờ địa phương tại vùng nào**? Locale không tự xác định múi giờ.

Java 17+ sử dụng `java.time.format.DateTimeFormatter` để biểu diễn giờ. Các pattern `H`, `h`, `k`, `K`, `a` và `B` giúp giải quyết hai câu hỏi đầu. `ZoneId` và những temporal như `ZonedDateTime` giải quyết câu hỏi thứ ba.

**Mục tiêu:** phân biệt rõ các kiểu giờ, chọn pattern phù hợp, biết dùng `Locale` tường minh, kiểm tra nửa đêm/chính trưa, hiểu ký hiệu kỳ trong ngày, parse an toàn, và tránh biến cách hiển thị thành quy tắc nghiệp vụ.

## 2. Hai cách đánh số giờ

### Hệ 24 giờ

Hệ 24 giờ thường biểu diễn giờ trong ngày từ **00** đến **23**:

| Giá trị giờ trong `LocalTime` | Viết theo `HH:mm` |
| ---: | --- |
| `00:00` | `00:00` |
| `09:30` | `09:30` |
| `12:00` | `12:00` |
| `13:05` | `13:05` |
| `23:45` | `23:45` |

`HH` tạo hai chữ số: `09` thay vì `9`. `H` không bắt buộc thêm số 0 ở đầu. Ví dụ: `"H:mm"` có thể in `"9:30"`, trong khi `"HH:mm"` in `"09:30"`.

### Hệ 12 giờ

Đồng hồ 12 giờ dùng các số **1 đến 12**, kết hợp ký hiệu kỳ trong ngày:

| Thời gian thực | `hh:mm a` với `Locale.US` |
| --- | --- |
| `00:00` | `12:00 AM` |
| `00:05` | `12:05 AM` |
| `09:30` | `09:30 AM` |
| `11:59` | `11:59 AM` |
| `12:00` | `12:00 PM` |
| `13:05` | `01:05 PM` |
| `23:45` | `11:45 PM` |

Trong đồng hồ 12 giờ, `12:00 AM` là **nửa đêm**, còn `12:00 PM` là **chính trưa**. Đây là cặp dễ nhầm, nên khi người dùng ít quen hệ 12 giờ, giao diện có thể chọn `00:00`, `12:00` hoặc những lời diễn đạt rõ hơn.

`hh` cũng thêm số 0 ở đầu: `01:05 PM`; `h` in `1:05 PM`. Cả hai đều biểu diễn giờ đồng hồ 12 giờ, nhưng độ rộng hiển thị khác nhau.

## 3. Bảng ký tự pattern quan trọng của DateTimeFormatter

| Pattern | Trường `java.time` | Phạm vi ý nghĩa | Ví dụ với 00:00 |
| --- | --- | --- | --- |
| `H` / `HH` | Hour of day | 0–23 | `0` / `00` |
| `k` / `kk` | Clock-hour of day | 1–24 | `24` / `24` |
| `h` / `hh` | Clock-hour of AM/PM | 1–12 | `12` / `12` |
| `K` / `KK` | Hour of AM/PM | 0–11 | `0` / `00` |
| `a` | AM/PM of day | Ký hiệu hai nửa ngày | `AM` với `Locale.US` |
| `B` | Period of day | Kỳ trong ngày theo locale | Có thể là `midnight` ở US |
| `m` / `mm` | Minute of hour | Phút 0–59 | `0` / `00` |
| `s` / `ss` | Second of minute | Giây 0–59 | `0` / `00` |

Các mẫu thường dùng:

```text
HH:mm        13:05
H:mm         13:05
hh:mm a      01:05 PM
h:mm a       1:05 PM
h:mm B       1:05 in the afternoon   (Locale.US)
kk:mm        13:05
KK:mm a      01:05 PM               (không phải biểu diễn h thông dụng)
```

**Đặc biệt lưu ý:** `K` và `h` **không phải tương đương**. Ở 13:05, `h` là `1`, nhưng `K` cũng là `1`; chỉ nhìn một ví dụ rất dễ nhầm. Tại 12:00, `h` là `12`, còn `K` là `0`. Tương tự, `k` là **24** lúc `00:00`, trong khi `H` là **0**.

Không dùng `a` một mình để suy giờ chính xác; nó chỉ cung cấp nhóm AM/PM. Không dùng `h` để hiển thị giờ không kèm `a`/ký hiệu kỳ nếu người dùng cần phân biệt sáng hay chiều: “1:05” một mình có thể mơ hồ.

## 4. Chương trình Java 17+ minh họa 12 giờ và 24 giờ

Tạo tệp `ClockFormatDemo.java`:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class ClockFormatDemo {
    public static void main(String[] args) {
        DateTimeFormatter twentyFour =
                DateTimeFormatter.ofPattern("HH:mm", Locale.US);
        DateTimeFormatter twelve =
                DateTimeFormatter.ofPattern("hh:mm a", Locale.US);

        LocalTime[] times = {
                LocalTime.MIDNIGHT,
                LocalTime.of(9, 30),
                LocalTime.NOON,
                LocalTime.of(13, 5),
                LocalTime.of(23, 45)
        };

        for (LocalTime time : times) {
            System.out.println(
                    twentyFour.format(time)
                    + " -> " + twelve.format(time));
        }
    }
}
```

Lưu dưới UTF-8 và chạy:

```bash
javac -encoding UTF-8 ClockFormatDemo.java
java ClockFormatDemo
```

Stdout:

```text
00:00 -> 12:00 AM
09:30 -> 09:30 AM
12:00 -> 12:00 PM
13:05 -> 01:05 PM
23:45 -> 11:45 PM
```

`LocalTime` chứa **giờ và phút**, không chứa cách viết 12/24 giờ. `DateTimeFormatter` thay đổi biểu diễn mà không chỉnh sửa `LocalTime`. Nhờ dùng `Locale.US` tường minh, ví dụ không phụ thuộc locale mặc định của hệ điều hành khi hiển thị `AM` và `PM`.

Nếu dùng `DateTimeFormatter.ofPattern("hh:mm a")` không có `Locale`, Java dùng locale mặc định thích hợp tại thời điểm tạo formatter. Một máy chủ có locale khác có thể tạo chuỗi khác. Trong ứng dụng đa người dùng, việc truyền `Locale` cho từng ngữ cảnh hiển thị là quan trọng.

## 5. So sánh bốn kiểu biểu diễn giờ: H, k, h, K

Bốn chữ này dễ gây lỗi logic hơn lỗi cú pháp. Cần biết rõ miền giá trị:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class HourFieldsDemo {
    public static void main(String[] args) {
        DateTimeFormatter fields =
                DateTimeFormatter.ofPattern("H k K h a", Locale.US);

        for (LocalTime time : new LocalTime[] {
                LocalTime.MIDNIGHT,
                LocalTime.NOON,
                LocalTime.of(23, 45)}) {
            System.out.println(time + " -> "
                    + fields.format(time));
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 HourFieldsDemo.java
java HourFieldsDemo
```

Stdout:

```text
00:00 -> 0 24 0 12 AM
12:00 -> 12 12 0 12 PM
23:45 -> 23 23 11 11 PM
```

Bản chất:

- **`H`** — số giờ kể từ nửa đêm theo hệ 0–23. Đây là lựa chọn phổ biến cho đồng hồ 24 giờ.
- **`k`** — clock-hour-of-day 1–24, hiển thị nửa đêm thành `24`; nhiều giao diện thông thường **không** dùng kiểu này vì `24:00` có thể bị hiểu là mốc ngày kế tiếp.
- **`h`** — clock-hour-of-am-pm 1–12, hiển thị nửa đêm và trưa đều là 12; cần ký hiệu AM/PM hoặc ngữ cảnh khác để phân biệt.
- **`K`** — hour-of-am-pm 0–11; nửa đêm và trưa đều là 0. Đây không phải lựa chọn thường thấy trong nhãn đồng hồ 12 giờ cho người dùng.

Nếu cần đồng hồ **24 giờ kiểu 00:00**, dùng `HH:mm`, không dùng `kk:mm`. Nếu cần **12 giờ kiểu 1:05 PM**, dùng `h:mm a`; nếu cần cố định hai chữ số giờ, dùng `hh:mm a`.

## 6. Ký hiệu AM/PM được bản địa hóa qua Locale

Ký tự pattern `a` biểu diễn **AM/PM of day**, nhưng chữ in ra **không nhất thiết là hai từ tiếng Anh AM/PM** ở mọi locale.

Chương trình `AmPmLocaleDemo.java`:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class AmPmLocaleDemo {
    public static void main(String[] args) {
        DateTimeFormatter us =
                DateTimeFormatter.ofPattern("hh:mm a", Locale.US);
        DateTimeFormatter vi =
                us.withLocale(Locale.forLanguageTag("vi-VN"));

        LocalTime morning = LocalTime.of(9, 30);
        LocalTime afternoon = LocalTime.of(13, 5);

        System.out.println("US morning: " + us.format(morning));
        System.out.println("US afternoon: " + us.format(afternoon));
        System.out.println("VI morning: " + vi.format(morning));
        System.out.println("VI afternoon: " + vi.format(afternoon));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 AmPmLocaleDemo.java
java AmPmLocaleDemo
```

Ví dụ stdout với dữ liệu locale trên OpenJDK 24 đã kiểm tra:

```text
US morning: 09:30 AM
US afternoon: 01:05 PM
VI morning: 09:30 SA
VI afternoon: 01:05 CH
```

Trong ví dụ này, dữ liệu locale Việt Nam dùng `SA` và `CH` tương ứng sáng/chiều. Dữ liệu bản địa hóa có thể khác theo phiên bản JDK, nguồn CLDR hoặc locale provider, vì vậy không nên biến đúng hai chữ viết tắt trên thành hợp đồng cố định cho mọi bản Java.

`withLocale` tạo một **formatter mới**; nó không sửa formatter `us`. `DateTimeFormatter` immutable và thread-safe, nên việc giữ một formatter base và tạo bản sao theo locale an toàn hơn thay đổi trạng thái mặc định JVM mỗi khi phục vụ request.

**Phân biệt:** ký hiệu `a` là AM/PM, tức **hai nửa ngày**. Nó không mang toàn bộ ý nghĩa “sáng, trưa, chiều, tối, đêm” trong ngôn ngữ tự nhiên.

## 7. Ký hiệu kỳ trong ngày linh hoạt: `B`

Trong `DateTimeFormatter`, ký tự pattern **`B`** biểu diễn *period-of-day* theo locale: có thể cho văn bản như “midnight”, “in the morning”, “noon”, “in the afternoon” hoặc “at night” với dữ liệu tiếng Anh. Đây là mô hình phong phú hơn `a` (AM/PM).

Ví dụ chạy được bằng Java 17+:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class DayPeriodDemo {
    public static void main(String[] args) {
        DateTimeFormatter us =
                DateTimeFormatter.ofPattern("h:mm B", Locale.US);
        DateTimeFormatter vi = us.withLocale(
                Locale.forLanguageTag("vi-VN"));

        for (LocalTime time : new LocalTime[] {
                LocalTime.MIDNIGHT,
                LocalTime.of(9, 30),
                LocalTime.NOON,
                LocalTime.of(13, 5),
                LocalTime.of(23, 45)}) {

            System.out.println(time + " | "
                    + us.format(time) + " | "
                    + vi.format(time));
        }
    }
}
```

Lưu thành `DayPeriodDemo.java`, sau đó chạy:

```bash
javac -encoding UTF-8 DayPeriodDemo.java
java DayPeriodDemo
```

Một stdout đã được kiểm tra với OpenJDK 24/CLDR:

```text
00:00 | 12:00 midnight | 12:00 nửa đêm
09:30 | 9:30 in the morning | 9:30 sáng
12:00 | 12:00 noon | 12:00 trưa
13:05 | 1:05 in the afternoon | 1:05 chiều
23:45 | 11:45 at night | 11:45 đêm
```

Ở đây `B` là văn bản **do dữ liệu locale cung cấp**. Mốc phân loại “sáng”, “trưa”, “chiều”, “tối”, “đêm” có thể khác nhau giữa các ngôn ngữ và dữ liệu CLDR; không tự viết `if (hour < 12) "morning" else "evening"` rồi cho rằng đúng mọi ngôn ngữ.

Một chuỗi như `12:00 noon` có thể đọc hơi dư nếu người dùng đã hiểu 12 giờ; sản phẩm có thể chọn `h B` hoặc một localized style tùy ngữ cảnh. Đừng ép một pattern cho mọi thông báo và mọi thiết bị mà không thử với người dùng thực tế.

**Quan trọng:** `B` không phải cam kết rằng mọi locale cung cấp cùng số loại kỳ trong ngày hoặc cùng ranh giới giờ. Nếu ứng dụng thực hiện nghiệp vụ như “chỉ được đặt phòng vào buổi sáng”, không dùng kết quả formatter `B` để quyết định ràng buộc; hãy lưu giờ bắt đầu/kết thúc theo quy tắc riêng.

## 8. Dùng kiểu thời gian bản địa hóa: không nhất thiết phải tự đặt h, H, a

Khi muốn hiển thị giờ **theo quy ước của locale**, `DateTimeFormatter.ofLocalizedTime(style).withLocale(locale)` thường phù hợp hơn tự viết `"hh:mm a"` hay `"HH:mm"`.

Ví dụ:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class LocalizedClockDemo {
    public static void main(String[] args) {
        LocalTime time = LocalTime.of(13, 5);

        DateTimeFormatter base =
                DateTimeFormatter.ofLocalizedTime(FormatStyle.SHORT);

        Locale[] locales = {
                Locale.US,
                Locale.UK,
                Locale.forLanguageTag("vi-VN"),
                Locale.FRANCE
        };

        for (Locale locale : locales) {
            System.out.println(locale.toLanguageTag() + ": "
                    + base.withLocale(locale).format(time));
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 LocalizedClockDemo.java
java LocalizedClockDemo
```

Ví dụ kết quả từ OpenJDK 24:

```text
en-US: 1:05 PM
en-GB: 13:05
vi-VN: 13:05
fr-FR: 13:05
```

Trong dòng `en-US`, khoảng trắng trước `PM` có thể là **narrow no-break space** U+202F, không phải dấu cách ASCII. Đây là chi tiết bản địa hóa hợp lệ; không nên dựa vào phép so sánh chuỗi cứng nếu không kiểm soát provider/JDK. Dữ liệu locale có thể thay đổi theo runtime và các chuẩn bản địa hóa cập nhật.

`FormatStyle.SHORT` yêu cầu kiểu trình bày ngắn. `MEDIUM`, `LONG`, `FULL` có thể thêm giây, ký hiệu vùng giờ hoặc thông tin khác tùy dữ liệu locale; với một số style cần temporal có đủ trường múi giờ, nên không mặc định mọi `LocalTime` đều format được ở mọi style.

**Thực hành được khuyến nghị:**

- Dùng `ofLocalizedTime(FormatStyle.SHORT).withLocale(locale)` cho giao diện cần tuân theo quy ước 12/24 giờ của locale.
- Dùng `ofPattern("HH:mm", locale)` nếu sản phẩm **bắt buộc** giao diện 24 giờ, ví dụ một số bảng điều khiển vận hành.
- Dùng `ofPattern("h:mm a", locale)` nếu thiết kế bắt buộc hệ 12 giờ với AM/PM.
- Dùng `ofPattern("h:mm B", locale)` khi muốn biểu thức kỳ trong ngày tự nhiên theo dữ liệu locale và đã kiểm thử.

Không phải mọi người trong cùng một locale đều chọn cùng kiểu đồng hồ. Nếu sản phẩm cung cấp tùy chọn cá nhân “12 giờ/24 giờ”, hãy ưu tiên lựa chọn đó, chỉ dùng locale để suy ra mặc định khi chưa có thiết lập của người dùng.

## 9. Parse chuỗi 12 giờ: phải có kỳ trong ngày

Đầu vào `"1:05"` không chứa AM/PM thì chưa đủ để xác định 01:05 hay 13:05. Nếu bạn parse dữ liệu người dùng ở dạng 12 giờ, cần có `a` (hoặc quy tắc rõ ràng tương đương) và locale phù hợp.

Ví dụ độc lập `ParseClockDemo.java`:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.time.format.DateTimeParseException;
import java.util.Locale;

public class ParseClockDemo {
    public static void main(String[] args) {
        DateTimeFormatter twelve =
                DateTimeFormatter.ofPattern("h:mm a", Locale.US)
                        .withResolverStyle(ResolverStyle.STRICT);

        System.out.println(
                "12 AM -> " + LocalTime.parse("12:00 AM", twelve));
        System.out.println(
                "12 PM -> " + LocalTime.parse("12:00 PM", twelve));
        System.out.println(
                "1 PM -> " + LocalTime.parse("1:05 PM", twelve));

        try {
            LocalTime.parse("00:30 AM", twelve);
        } catch (DateTimeParseException error) {
            System.out.println("Invalid 12-hour input");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 ParseClockDemo.java
java ParseClockDemo
```

Stdout:

```text
12 AM -> 00:00
12 PM -> 12:00
1 PM -> 13:05
Invalid 12-hour input
```

Đây là ví dụ quan trọng về nửa đêm/chính trưa:

- `12:00 AM` là `LocalTime.MIDNIGHT`.
- `12:00 PM` là `LocalTime.NOON`.
- `1:05 PM` là `13:05`.
- `00:30 AM` **không phải** số giờ hợp lệ của clock-hour 12 giờ trong `STRICT`; đầu vào 00 giờ nên dùng hệ `H`/`HH`.

Nếu parse AM/PM trong chuỗi tiếng Việt, phải dùng đúng locale và cách viết ký hiệu mà parser của JDK hỗ trợ, thay vì luôn gửi `"AM"`, `"PM"` của tiếng Anh.

Khi đọc dữ liệu từ API, không dùng một chuỗi theo locale kiểu `1:05 PM` nếu hợp đồng API có thể dùng `13:05:00` ISO. Cách trình bày dành cho con người không cần trở thành định dạng của giao thức.

## 10. Đọc giờ 24:00: phân biệt `H` và `k` khi parse

Đặc điểm `k` là miền **1–24**. Khi format `LocalTime.MIDNIGHT`, pattern `kk:mm` tạo `24:00`, nhưng `HH:mm` tạo `00:00`.

Với `ResolverStyle.STRICT`, formatter `HH:mm` không chấp nhận `24:00` như một giờ có giá trị `HOUR_OF_DAY` trong phạm vi 0–23. Formatter `kk:mm` có thể parse `24:00` thành `LocalTime.MIDNIGHT`.

Ví dụ:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class MidnightParseDemo {
    public static void main(String[] args) {
        DateTimeFormatter hourOfDay =
                DateTimeFormatter.ofPattern("HH:mm", Locale.US)
                        .withResolverStyle(ResolverStyle.STRICT);

        DateTimeFormatter clockHour =
                DateTimeFormatter.ofPattern("kk:mm", Locale.US)
                        .withResolverStyle(ResolverStyle.STRICT);

        System.out.println(
                "k: " + LocalTime.parse("24:00", clockHour));

        try {
            LocalTime.parse("24:00", hourOfDay);
        } catch (DateTimeParseException error) {
            System.out.println("H: Invalid hour");
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 MidnightParseDemo.java
java MidnightParseDemo
```

Stdout:

```text
k: 00:00
H: Invalid hour
```

Dù `24:00` có thể xuất hiện trong một số quy ước lịch trình để nói hết ngày, không được tự cho rằng `LocalTime` đã giữ thông tin “ngày tiếp theo”. `LocalTime` chỉ lưu giờ-phút trong một ngày và giá trị `00:00` không mang ngày. Nếu nghiệp vụ phân biệt **cuối ngày 24:00** và **đầu ngày 00:00**, cần một mô hình có ngày, quy tắc ranh giới hoặc đối tượng nghiệp vụ riêng.

Trong API Java có những chế độ parse khác nhau: đừng trộn kết luận từ `ResolverStyle.STRICT` với các kiểu mặc định `SMART`/`LENIENT` mà không kiểm thử. Quy tắc đầu vào nên được định nghĩa rõ và test tại điểm nhận dữ liệu.

## 11. Locale không phải múi giờ: tránh đổi 13:05 thành giờ sai

Một `Instant` là thời điểm trên trục UTC; muốn biết nó là mấy giờ ở Việt Nam hay nước khác, cần múi giờ:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class TimeZoneClockDemo {
    public static void main(String[] args) {
        Instant instant = Instant.parse("2026-10-28T03:30:00Z");

        DateTimeFormatter clock =
                DateTimeFormatter.ofPattern(
                        "uuuu-MM-dd HH:mm XXX", Locale.US);

        System.out.println("UTC: " + clock
                .withZone(ZoneId.of("UTC")).format(instant));

        System.out.println("HCM: " + clock
                .withZone(ZoneId.of("Asia/Ho_Chi_Minh"))
                .format(instant));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 TimeZoneClockDemo.java
java TimeZoneClockDemo
```

Stdout:

```text
UTC: 2026-10-28 03:30 Z
HCM: 2026-10-28 10:30 +07:00
```

`Locale.US` ở đây chỉ liên quan đến diễn đạt văn bản; các chữ số của pattern và offset vẫn rõ nghĩa. Thay `Locale.US` thành `vi-VN` **không tự quy đổi** `Instant` từ UTC sang `Asia/Ho_Chi_Minh`. Chính lời gọi `withZone` xác định múi giờ thực tế.

Ngược lại, `LocalTime.of(13, 5)` **không** chứa vùng giờ hay ngày, nên không thể tự suy ra nó tương ứng với thời điểm nào trên UTC. Nếu quản lý giờ họp quốc tế, nên lưu một thời điểm/zone đủ thông tin, rồi mới định dạng thành đồng hồ 12 hoặc 24 giờ theo lựa chọn người xem.

## 12. Lựa chọn 12/24 giờ trong UI và nghiệp vụ

Một thiết kế tốt tách ba tầng:

1. **Dữ liệu:** lưu `LocalTime`, `ZonedDateTime` hoặc `Instant` theo nghĩa nghiệp vụ; không lưu đơn thuần chuỗi `"1:05 PM"` làm nguồn sự thật.
2. **Cấu hình người xem:** locale, múi giờ và tùy chọn 12/24 giờ (nếu có).
3. **Trình bày:** chọn formatter tương ứng, rồi render kết quả.

Ví dụ hàm có thể biên dịch, không có `main`:

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public final class ClockView {
    private ClockView() {}

    public static String display(
            LocalTime time, Locale locale, boolean use24Hour) {

        if (time == null || locale == null) {
            throw new IllegalArgumentException(
                    "time and locale must not be null");
        }

        String pattern = use24Hour ? "HH:mm" : "h:mm a";
        return DateTimeFormatter.ofPattern(pattern, locale)
                .format(time);
    }
}
```

Lưu `ClockView.java` rồi biên dịch:

```bash
javac -encoding UTF-8 ClockView.java
```

Đây là **utility class** không có `main`, nên không có stdout và không chạy bằng `java ClockView`. Nếu chưa có lựa chọn cá nhân, có thể dùng `ofLocalizedTime(FormatStyle.SHORT)` để lấy mặc định theo locale; nếu có lựa chọn tường minh, dùng nó.

Không viết trong request handler:

```java
Locale.setDefault(userLocale); // Tránh cách này.
```

`Locale.setDefault` thay cấu hình toàn JVM và có thể ảnh hưởng request khác trong môi trường nhiều luồng. `DateTimeFormatter.ofPattern(pattern, locale)` và `withLocale(locale)` cho phép chọn riêng từng lần dùng mà không đụng tới global state.

Với sản phẩm có lựa chọn 12/24 giờ, nên dùng **giá trị cài đặt của người dùng** làm ưu tiên; locale là một gợi ý mặc định, không phải quy tắc tuyệt đối cho sở thích của từng cá nhân.

## 13. Những lỗi thường gặp

| Sai lầm | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Dùng `hh:mm` không có `a` | Không biết giờ sáng hay chiều | Thêm `a` hoặc dùng 24 giờ |
| Nhầm `hh` với `HH` | 13 giờ thành 01 giờ, hoặc ngược lại | Chọn rõ 12/24 giờ |
| Nhầm `k` với `H` | Nửa đêm hiển thị `24:00` thay `00:00` | Dùng `HH` cho đồng hồ 00–23 |
| Nhầm `K` với `h` | Chính trưa/nửa đêm hiển thị `0` thay `12` | Dùng `h` cho đồng hồ 1–12 |
| Tưởng `a` luôn in chữ `AM`/`PM` | Hiển thị không phù hợp bản địa hóa | Truyền `Locale` tường minh |
| Tưởng `B` là hai nửa AM/PM | Phân loại sáng/trưa/chiều/đêm sai | Hiểu `B` là period-of-day locale-aware |
| Dùng `B` để quyết định giờ hoạt động | Chính sách thay đổi theo dữ liệu CLDR | Lưu quy tắc giờ nghiệp vụ riêng |
| Dùng `ofPattern(pattern)` không truyền locale | Dựa vào locale mặc định JVM | Dùng overload nhận `Locale` |
| Cố định `"1:05 PM"` trong API JSON | Giao thức phụ thuộc ngôn ngữ | Dùng dạng ISO/thời gian có cấu trúc |
| Parse `12:00 AM` thành 12:00 | Sai 12 giờ tại nửa đêm | Test cặp `12 AM` và `12 PM` |
| Parse `24:00` như ngày tiếp theo mà chỉ lưu `LocalTime` | Mất thông tin ngày | Dùng kiểu dữ liệu/cấu trúc bao gồm ngày |
| Nghĩ Locale tự đổi múi giờ | Hiển thị lệch thời gian | Chọn `ZoneId` riêng |
| Tự ép AM/PM vào mọi ngôn ngữ | Không tự nhiên, sai tùy chọn người dùng | Dùng localized style hoặc cấu hình 12/24 |
| Hard-code chuỗi localized output trong test mọi runtime | Lỗi giả khi CLDR cập nhật | Test trên runtime mục tiêu hoặc so sánh semantic |

**Cần nhớ:** ký hiệu kỳ trong ngày là **dữ liệu hiển thị**, không phải mã nghiệp vụ. Một cửa hàng “mở cửa buổi sáng” cần giờ bắt đầu/kết thúc và vùng giờ cụ thể, không nên kiểm tra một chuỗi `"sáng"` do `DateTimeFormatter` sinh ra.

## 14. Chiến lược kiểm thử cho ứng dụng đa ngôn ngữ

Dùng dữ liệu cố định, không dùng `LocalTime.now()` nếu muốn stdout và các assert có thể tái lập.

Một bộ test cơ bản nên gồm:

- **Ranh giới:** `00:00`, `00:05`, `11:59`, `12:00`, `12:01`, `13:05`, `23:45`.
- **12 giờ:** `00:00` -> `12:00 AM`, `12:00` -> `12:00 PM`, `13:05` -> `01:05 PM` với `Locale.US`.
- **24 giờ:** `00:00` -> `00:00`, `13:05` -> `13:05` với `HH:mm`.
- **Khác biệt `H/k/h/K`:** xác nhận đầu ra của chương trình `HourFieldsDemo` tại nửa đêm và trưa.
- **Locale:** `a` và `B` được hiển thị theo ngôn ngữ dữ liệu JDK cho `en-US`, `vi-VN` và các locale được sản phẩm hỗ trợ.
- **Localized style:** một locale có thể dùng 12 giờ, locale khác dùng 24 giờ; không giả định mọi bản JDK trả đúng cùng ký tự khoảng trắng.
- **Parse:** `12:00 AM` -> `00:00`, `12:00 PM` -> `12:00`; loại `00:30 AM` trong strict 12-hour parsing.
- **`24:00`:** kiểm tra `HH:mm` vs `kk:mm` và chính sách nghiệp vụ cho ngày tiếp theo.
- **Múi giờ:** cùng `Instant` hiển thị khác với `UTC` và `Asia/Ho_Chi_Minh`; không phụ thuộc locale.
- **Đa luồng:** không đổi `Locale.setDefault` trong request; formatter immutable có thể dùng lại.
- **Tính dễ đọc:** tham khảo lựa chọn 12/24 của người dùng, đặc biệt ở vùng có nhiều thói quen hiển thị khác nhau.

Đối với test so sánh output localized trực tiếp, ghim phiên bản JDK/locale provider hoặc kiểm tra theo môi trường triển khai. Dữ liệu CLDR có thể điều chỉnh tên kỳ trong ngày và khoảng trắng; một thay đổi nhỏ trong dữ liệu bản địa hóa không đồng nghĩa bug về tính toán giờ.

## 15. Bài tập thực hành

1. Chạy `ClockFormatDemo`, thêm `LocalTime.of(0, 5)` và `LocalTime.of(11, 59)`. Giải thích vì sao `00:05` thành `12:05 AM`.
2. So sánh `HH:mm`, `H:mm`, `hh:mm a`, `h:mm a` trên cùng `LocalTime.of(9, 3)` và `LocalTime.of(21, 3)`. Xác định ảnh hưởng của số lượng ký tự pattern.
3. Kiểm tra `HourFieldsDemo` với `LocalTime.NOON`. Vì sao `K=0`, `h=12` và `a=PM`?
4. Thử `B` với `LocalTime.of(0, 0)`, `LocalTime.of(12, 0)` và `LocalTime.of(20, 0)` cho `Locale.US` và `vi-VN`. Đối chiếu dữ liệu JDK đang dùng.
5. Thay `FormatStyle.SHORT` bằng `MEDIUM` ở `LocalizedClockDemo`; quan sát các locale có hiện giây hay không.
6. Parse `"01:05 PM"` và `"1:05 PM"` bằng `DateTimeFormatter.ofPattern("h:mm a", Locale.US)` (độ rộng của pattern và các trường liên quan), rồi so sánh với `"hh:mm a"`.
7. Tạo một ứng dụng nhỏ có tùy chọn `use24Hour` và `Locale`. Khi chuyển 12/24, kiểm tra dữ liệu `LocalTime` không đổi; chỉ chuỗi xuất ra khác.
8. Tạo một `Instant` cố định, chuyển qua ít nhất hai `ZoneId`, rồi dùng cùng một locale để chứng minh khác biệt giờ thuộc về múi giờ, không phải ngôn ngữ.

## 16. Tổng kết

Để biểu diễn **24 giờ**, dùng `H`/`HH` cho miền 0–23; `k` là kiểu 1–24 nên nửa đêm có thể hiện `24:00`. Để biểu diễn **12 giờ**, dùng `h`/`hh` cho miền 1–12 và bổ sung `a` khi cần phân biệt AM/PM; `K` là trường 0–11, không thay thế `h` một cách tùy tiện.

`a` biểu thị **AM/PM**, còn `B` biểu thị **kỳ trong ngày linh hoạt theo locale**. Khi giao diện muốn tuân thói quen địa phương, dùng `DateTimeFormatter.ofLocalizedTime(FormatStyle.SHORT).withLocale(locale)`; nếu người dùng đã chọn chế độ 12/24 rõ ràng, ưu tiên lựa chọn đó. Cuối cùng, nhớ rằng **locale ảnh hưởng cách viết**, **múi giờ ảnh hưởng giờ địa phương**, còn dữ liệu ngày giờ phải được giữ bằng kiểu dữ liệu có ngữ nghĩa phù hợp.

## Tài liệu tham khảo

- [Oracle JDK 21 — DateTimeFormatter: Pattern Letters và Localized Styles](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [Oracle JDK 21 — LocalTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalTime.html)
- [Oracle JDK 21 — ResolverStyle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/ResolverStyle.html)
- [Oracle JDK 21 — Locale](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html)
- [Oracle JDK 21 — ZoneId](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZoneId.html)
