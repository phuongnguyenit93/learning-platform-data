# Zone, offset và ký hiệu trong mẫu DateTimeFormatter của Java

## 1. Mục tiêu và phạm vi

Khi định dạng ngày giờ bằng `java.time.format.DateTimeFormatter`, rất dễ nhầm ba thứ:

- **UTC offset:** chênh lệch so với UTC, chẳng hạn `+07:00`, `-04:00` hoặc `Z`.
- **Zone ID:** định danh múi giờ theo vùng, chẳng hạn `Asia/Ho_Chi_Minh` hoặc `Europe/Paris`, có quy tắc thay đổi offset theo thời gian.
- **Tên múi giờ hiển thị:** tên ngắn/dài phụ thuộc ngôn ngữ và quy tắc mùa hè, chẳng hạn `CET`, `CEST` hoặc `Central European Time` trong một môi trường dùng tiếng Anh.

DateTimeFormatter có các ký hiệu chuyên biệt:

- **`X`, `x`, `Z` và `O`**: in hoặc đọc **offset**.
- **`V`**: in hoặc đọc **zone ID** (trên thực tế phải viết **`VV`**).
- **`z`**: in/đọc **tên múi giờ** có phân biệt standard/daylight khi đủ thông tin.
- **`v`**: in/đọc **tên múi giờ tổng quát**, không chia theo daylight saving.
- **`[` và `]`**: phần **tùy chọn** của pattern, khác với ký tự ngoặc vuông thật cần được escape.

Các API này đã có từ Java 8 và vẫn còn được hỗ trợ trong **Java hiện đại**. Bài sử dụng `java.time` và các ví dụ chạy được với **JDK 17+**, không dựa vào các cách định dạng ngày giờ legacy. Khi sử dụng trong dự án Java 8, các phương thức được minh họa của `DateTimeFormatter`, `ZonedDateTime`, `OffsetDateTime` và `ZoneId` vẫn áp dụng; riêng ví dụ không dùng tính năng ngôn ngữ mới hơn Java 8.

**Kết quả cần đạt:** tự đọc đúng các pattern như `XXX`, `xxxxx`, `ZZZZ`, `VV`, `zzzz`, chọn kiểu dữ liệu nguồn phù hợp, và biết vì sao một chuỗi có đủ offset và zone ID vẫn có thể cần **kiểm tra ngữ nghĩa bổ sung**.

## 2. Phân biệt LocalDateTime, OffsetDateTime, ZonedDateTime và Instant

Trước khi học ký hiệu pattern, phải hiểu đối tượng đang được định dạng **có những thông tin nào**.

| Kiểu dữ liệu | Ngày giờ địa phương | Offset | Zone ID vùng | Mốc thời gian tuyệt đối |
| --- | --- | --- | --- | --- |
| `LocalDateTime` | Có | Không | Không | Chưa xác định |
| `OffsetDateTime` | Có | Có | **Không lưu region ID** | Xác định được |
| `ZonedDateTime` | Có | Có | Có, khi tạo từ vùng | Xác định được |
| `Instant` | Không mang local clock/zone | Không tự lưu offset | Không | Có |
| `ZoneOffset` | Không có ngày giờ | Chính nó là offset | Không có vùng địa lý | Không phải timestamp |
| `ZoneId` | Không có ngày giờ | Quy tắc xác định offset theo thời điểm | Có thể là region ID hoặc dạng offset | Không phải timestamp |

Ví dụ cùng một sự kiện:

```text
Instant:         2024-06-10T13:00:00Z

OffsetDateTime:  2024-06-10T20:00:00+07:00

ZonedDateTime:   2024-06-10T20:00:00+07:00[Asia/Ho_Chi_Minh]
```

Ba biểu diễn này có thể xác định **cùng một Instant**, nhưng chỉ biểu diễn cuối có tên vùng `Asia/Ho_Chi_Minh`.

**Quy tắc dễ nhớ:**

- Muốn in `+07:00`: dùng pattern offset như `XXX`.
- Muốn in `Asia/Ho_Chi_Minh`: dùng `VV` trên nguồn có ZoneId.
- Muốn in tên thân thiện theo locale: dùng `z` hoặc `v`, đồng thời hiểu rằng tên đó có thể thay đổi.
- Chỉ có `Instant`? Cần cung cấp zone hoặc offset vào formatter qua `withZone(...)` để in các trường ngày/giờ địa phương.

## 3. DateTimeFormatter.ofPattern hoạt động thế nào?

Một formatter có thể được tạo bằng:

```java
// Đoạn minh họa; import java.time.format.DateTimeFormatter.
DateTimeFormatter formatter =
    DateTimeFormatter.ofPattern(
        "uuuu-MM-dd'T'HH:mm:ssXXX"
    );
```

Mỗi chữ cái pattern có ý nghĩa riêng:

| Ký hiệu | Ý nghĩa |
| --- | --- |
| `u` / `uuuu` | Năm proleptic (đặc biệt phù hợp khi parse ISO strict) |
| `y` / `yyyy` | Năm trong kỷ nguyên (*year-of-era*) |
| `Y` | Năm theo tuần (*week-based year*), không phải năm lịch thông thường |
| `M` / `MM` | Tháng |
| `d` / `dd` | Ngày trong tháng |
| `H` / `HH` | Giờ trong ngày, 0–23 |
| `m` / `mm` | Phút, không phải tháng |
| `s` / `ss` | Giây |
| `S` / `SSS` | Phần giây theo số chữ số đã yêu cầu |
| `X`, `x`, `Z`, `O` | UTC offset theo các quy tắc riêng |
| `V` / `VV` | Zone ID; chỉ đúng **hai** chữ `V` hợp lệ |
| `z` | Tên múi giờ theo standard/daylight khi đủ thông tin |
| `v` | Tên múi giờ tổng quát |

Ký tự `'` dùng để quote văn bản literal. Trong:

```java
// Chữ T được quote vì T không phải một pattern letter hợp lệ.
"uuuu-MM-dd'T'HH:mm:ssXXX"
```

`'T'` có nghĩa in đúng chữ `T` ở giữa ngày và giờ.

Trong khi đó, các dấu `[` và `]` **không được quote** mang nghĩa **bắt đầu/kết thúc đoạn tùy chọn**; chúng không tự in dấu ngoặc vuông ra chuỗi. Muốn in `[Europe/Paris]`, cần quote dấu ngoặc thật, ví dụ:

```java
// Đoạn minh họa.
"uuuu-MM-dd'T'HH:mm:ssXXX'['VV']'"
```

Pattern này in ngày/giờ, offset, sau đó **ngoặc vuông literal**, zone ID, rồi ngoặc đóng literal. Dấu `'` bao quanh `[` và `]` là thiết yếu.

### 3.1. Pattern có phân biệt chữ hoa và thường

Các cặp sau **không hoán đổi**:

- `X` và `x`: khác cách in offset zero.
- `M` và `m`: tháng và phút.
- `y`, `u` và `Y`: ba ý nghĩa năm khác nhau.
- `z` và `v`: tên zone có xét daylight saving và tên zone tổng quát.
- `H` và `h`: 24-hour clock và 12-hour clock.

Đừng đổi hoa/thường chỉ để “nhìn đẹp hơn”. Một ký tự khác có thể cho ra dữ liệu sai về mặt ngữ nghĩa nhưng không gây lỗi cú pháp.

### 3.2. Số lần lặp ký hiệu rất quan trọng

`X`, `XX`, `XXX`, `XXXX` và `XXXXX` có output khác nhau. Nhưng `VV` là **cách viết duy nhất hợp lệ** cho zone ID trong pattern; `V` và `VVV` làm `ofPattern` ném `IllegalArgumentException`.

Với `z`, một đến ba ký tự dùng tên ngắn; `zzzz` dùng tên đầy đủ. `v` chỉ cho phép **một hoặc bốn** ký tự. `O` cũng chỉ cho phép **một hoặc bốn** ký tự.

## 4. X và x: UTC offset kiểu ISO

Hai ký hiệu thường gặp nhất khi tạo chuỗi giao tiếp giữa các hệ thống là `X` và `x`.

| Pattern | Offset `+05:30` | Offset zero | Dạng chính |
| --- | --- | --- | --- |
| `X` | `+0530` | `Z` | Giờ; thêm phút nếu phút khác zero |
| `XX` | `+0530` | `Z` | Giờ và phút, **không dấu hai chấm** |
| `XXX` | `+05:30` | `Z` | Giờ và phút, **có dấu hai chấm** |
| `XXXX` | `+0530` nếu giây zero | `Z` | Có thể thêm giây, không dấu hai chấm |
| `XXXXX` | `+05:30` nếu giây zero | `Z` | Có thể thêm giây, có dấu hai chấm |
| `x` | `+0530` | `+00` | Giống `X` nhưng không dùng chữ `Z` cho zero |
| `xx` | `+0530` | `+0000` | Không dấu hai chấm |
| `xxx` | `+05:30` | `+00:00` | Có dấu hai chấm |
| `xxxx` | `+0530` nếu giây zero | `+0000` | Có thể thêm giây |
| `xxxxx` | `+05:30` nếu giây zero | `+00:00` | Có thể thêm giây và dấu hai chấm |

**Lưu ý cho độ rộng 1:** Nếu offset chỉ là số giờ tròn, `X` có thể in `+07`. Nếu phần phút khác zero như +05:30, nó in cả phút `+0530`. Vì thế không nên giả định `X` luôn tạo chuỗi đúng ba ký tự.

**Giới hạn:** `X`/`x` chỉ cho phép 1–5 ký tự. `XXXXXX` và `xxxxxx` là pattern không hợp lệ, thường gây `IllegalArgumentException` ngay khi xây formatter.

### 4.1. Khi offset có giây

Phần lớn múi giờ dân dụng ngày nay dùng offset theo phút, nhưng `ZoneOffset` có thể biểu diễn một offset gồm phần giây. Ví dụ `+05:30:45`:

```text
X       -> +0530
XX      -> +0530
XXX     -> +05:30
XXXX    -> +053045
XXXXX   -> +05:30:45
```

Độ rộng 4–5 hỗ trợ **phần giây nếu khác zero**. Các độ rộng ngắn hơn có thể **không biểu diễn toàn bộ độ chính xác của offset**. Vì thế không mặc định mọi pattern có thể round-trip lossless đối với offset chứa giây.

### 4.2. Khi nào dùng XXX hay xxx?

- `XXX` thuận tiện cho ISO-like text có offset, đặc biệt khi muốn zero là `Z`.
- `xxx` phù hợp khi schema yêu cầu offset zero phải được in thành `+00:00`, không thành `Z`.
- `XX` hoặc `xx` dùng khi format của bên nhận yêu cầu offset không có dấu hai chấm.
- Với API trao đổi timestamp nói chung, ưu tiên formatter ISO dựng sẵn nếu không cần format riêng.

Dù `Z` và `+00:00` cùng chỉ offset zero, chúng **khác nhau về chuỗi**. Nếu hệ thống so sánh string hoặc xác thực schema chữ, phải chọn định dạng nhất quán.

## 5. Ví dụ 1 — quan sát X, x, Z, O với offset khác zero và UTC

Tạo file **OffsetLettersDemo.java**:

```java
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.time.format.DateTimeFormatter;

public class OffsetLettersDemo {
    static void dump(OffsetDateTime value) {
        List<String> patterns = Arrays.asList(
            "X", "XX", "XXX", "XXXX", "XXXXX",
            "x", "xx", "xxx", "xxxx", "xxxxx",
            "Z", "ZZ", "ZZZ", "ZZZZ", "ZZZZZ",
            "O", "OOOO"
        );

        for (String pattern : patterns) {
            String result = DateTimeFormatter
                .ofPattern(pattern, Locale.US)
                .format(value);

            System.out.println(pattern + "=" + result);
        }
    }

    public static void main(String[] args) {
        OffsetDateTime value = OffsetDateTime.of(
            2024, 6, 10, 20, 15, 30, 0,
            ZoneOffset.ofHoursMinutes(5, 30)
        );

        OffsetDateTime utc =
            value.withOffsetSameInstant(ZoneOffset.UTC);

        System.out.println("nonzero");
        dump(value);

        System.out.println("zero");

        for (String pattern : Arrays.asList(
            "X", "XX", "XXX",
            "x", "xx", "xxx",
            "Z", "ZZZZ", "ZZZZZ",
            "O", "OOOO"
        )) {
            System.out.println(
                pattern + "=" +
                DateTimeFormatter
                    .ofPattern(pattern, Locale.US)
                    .format(utc)
            );
        }
    }
}
```

Chạy:

```bash
javac OffsetLettersDemo.java
java OffsetLettersDemo
```

Đầu ra đã kiểm thử với `Locale.US`:

```text
nonzero
X=+0530
XX=+0530
XXX=+05:30
XXXX=+0530
XXXXX=+05:30
x=+0530
xx=+0530
xxx=+05:30
xxxx=+0530
xxxxx=+05:30
Z=+0530
ZZ=+0530
ZZZ=+0530
ZZZZ=GMT+05:30
ZZZZZ=+05:30
O=GMT+5:30
OOOO=GMT+05:30
zero
X=Z
XX=Z
XXX=Z
x=+00
xx=+0000
xxx=+00:00
Z=+0000
ZZZZ=GMT
ZZZZZ=Z
O=GMT
OOOO=GMT
```

**Các điểm quan trọng:**

1. `X` và `x` giống nhau trong ví dụ +05:30, nhưng khác nhau tại offset zero.
2. `XXX` in `+05:30` và `Z` khi UTC; `xxx` in `+05:30` và `+00:00`.
3. `Z` độ rộng 1–3 in offset có phút và **không có dấu hai chấm**.
4. `ZZZZ` và `OOOO` là các **dạng offset địa phương hóa**, trong môi trường `Locale.US` ở ví dụ hiển thị `GMT+05:30`.
5. `O` dùng dạng ngắn như `GMT+5:30`, khác `OOOO` có số giờ hai chữ số.
6. `Locale` ảnh hưởng những chuỗi được địa phương hóa. Không hardcode kết quả `GMT...` của locale US như thể mọi locale/JDK buộc phải giống hệt.

Các output có zero đặc biệt hữu ích để kiểm tra hợp đồng của API ngoài. Nếu phía nhận cần `+00:00`, đừng dùng `XXX` chỉ vì hai cách viết cùng biểu thị UTC.

## 6. Z: offset dạng lịch sử/RFC và localized

`Z` là một ký hiệu offset riêng, **không phải đồng nghĩa với chữ `Z` literal** trong mọi trường hợp.

| Pattern | Khi offset `+05:30` | Khi offset zero | Ghi chú |
| --- | --- | --- | --- |
| `Z` | `+0530` | `+0000` | Độ rộng 1–3 có cùng kiểu chung |
| `ZZ` | `+0530` | `+0000` | Không có dấu hai chấm |
| `ZZZ` | `+0530` | `+0000` | Không có dấu hai chấm |
| `ZZZZ` | `GMT+05:30` trong Locale.US | `GMT` trong Locale.US | Dạng localized offset đầy đủ |
| `ZZZZZ` | `+05:30` | `Z` | Dạng có dấu hai chấm, giây tùy chọn |

`Z` cho phép 1–5 ký tự. Sáu ký tự trở lên sẽ gây `IllegalArgumentException`.

Mặc dù ký tự `Z` thường được dùng trong văn bản ISO để biểu thị UTC, **pattern `Z` có một chữ** tại offset zero lại cho `+0000`. Nếu bạn muốn ký tự `Z` khi offset zero, hãy cân nhắc `X`/`XXX`, `ZZZZZ` hoặc formatter ISO dựng sẵn tương ứng.

### 6.1. Z không chứa ZoneId vùng

Chuỗi `+0530` chỉ xác định chênh lệch +05:30; không thể suy ra tên vùng hay lịch sử DST. Nếu cần nhận dạng `Asia/Kolkata` hoặc bất kỳ region khác, phải dùng `ZoneId` phù hợp; không thể tạo thông tin vùng bằng cách đổi `Z` thành `VV` trên một `OffsetDateTime` thiếu region ID.

## 7. O: offset được địa phương hóa

`O` là **localized zone-offset**:

- `O`: dạng ngắn; ví dụ `GMT+5:30` ở Locale.US.
- `OOOO`: dạng đầy đủ; ví dụ `GMT+05:30` ở Locale.US.
- `OO`, `OOO` và năm ký tự trở lên **không hợp lệ**.

Khi offset bằng zero, dạng localized có thể chỉ còn chuỗi như `GMT` tùy locale.

**Chức năng chính của O là phục vụ hiển thị dễ đọc theo locale**, không phải cách phù hợp nhất cho một schema timestamp machine-to-machine. Nếu API yêu cầu định dạng ổn định, thường nên dùng `ISO_OFFSET_DATE_TIME`, `XXX` hoặc một format được công bố rõ.

### 7.1. Không cắt tiền tố GMT để lấy offset

Đừng lấy string `"GMT+5:30"` rồi chỉ xử lý bằng `substring` hoặc phép tìm ký tự thủ công. `O` mang nghĩa localized; tiền tố và cách viết có thể phụ thuộc locale. Khi dữ liệu cần được xử lý máy móc, lưu `ZoneOffset`/`ZoneId` hoặc parse bằng formatter đúng pattern/locale, không viết parser chuỗi giả định một ngôn ngữ.

## 8. VV: zone ID, không phải offset

Để in tên vùng IANA/region ID:

```java
// Mã minh họa.
DateTimeFormatter idFormatter =
    DateTimeFormatter.ofPattern("VV");
```

Với `ZonedDateTime` chứa `ZoneId.of("Europe/Paris")`, kết quả của `VV` là `Europe/Paris`. Đây là **ID vùng**, không phải bản dịch tên thân thiện.

**Quy tắc số ký tự:** Chỉ có `VV` hợp lệ cho pattern chữ `V`. `V`, `VVV` hoặc `VVVV` gây `IllegalArgumentException` ngay ở `DateTimeFormatter.ofPattern(...)`.

### 8.1. Vì sao không dùng VV thay XXX trên OffsetDateTime?

`OffsetDateTime` lưu ngày/giờ + offset, không lưu định danh region ID. Khi format một `OffsetDateTime` thông thường:

- `XXX` thành công vì nguồn chứa offset.
- `VV` có thể ném `DateTimeException` do thiếu zone ID để truy vấn.
- `z` và `v` cũng có thể không format được vì không có region zone để lấy tên hiển thị.

Nếu muốn lưu cả offset và vùng, `ZonedDateTime` (hoặc một record có `ZoneId` riêng) phù hợp hơn.

### 8.2. VV có thể in offset-based ID khi nguồn mang ID đó

`ZoneId` trong Java bao gồm cả ID dạng vùng và dạng offset. Vì thế `VV` **không cam kết mọi output đều là tên thành phố**; nếu nguồn dùng `ZoneOffset` như zone, nó có thể in ID offset như `+07:00` hoặc `Z`. Không lấy một chuỗi nhìn giống `+07:00` rồi suy ngược rằng đã có vùng địa lý.

## 9. z và v: tên múi giờ theo locale

### 9.1. z: tên có xét DST khi đủ thông tin

`z` chọn tên múi giờ theo ngày/giờ cụ thể; nếu zone vào standard time thì có thể dùng tên standard, còn vào daylight saving time thì dùng tên daylight.

Với `Europe/Paris` và `Locale.US` trong môi trường được kiểm thử:

```text
Mùa đông 2024:
z      -> CET
zzzz   -> Central European Standard Time

Mùa hè 2024:
z      -> CEST
zzzz   -> Central European Summer Time
```

Số ký tự:

- `z`, `zz`, `zzz`: tên ngắn.
- `zzzz`: tên đầy đủ.
- `zzzzz` hoặc nhiều hơn: không hợp lệ.

Nếu dữ liệu temporal không đủ để xác định có đang áp dụng DST không, Java có thể dùng tên vùng tổng quát thay thế. Tên hiển thị thực tế phụ thuộc **Locale**, dữ liệu locale của JDK, và quy tắc timezone.

### 9.2. v: generic zone name, không thay đổi tên theo DST

`v` dùng **generic time-zone name**, bỏ qua phân biệt standard/daylight trong tên hiển thị.

Với `Europe/Paris`, `Locale.US` trong môi trường thử nghiệm:

```text
v     -> CET
vvvv  -> Central European Time
```

Hai kết quả trên **giống nhau trong mùa đông và mùa hè** đối với vùng đã chọn. Điều đó không có nghĩa offset thực tế ở hai mùa giống nhau; nếu in kèm `XXX`, mùa đông `+01:00` còn mùa hè `+02:00`.

Chỉ `v` và `vvvv` hợp lệ. `vv`, `vvv` và năm ký tự trở lên gây `IllegalArgumentException`.

### 9.3. Tại sao không lưu tên z/v làm định danh vùng?

Các tên như `CET`, `CEST`, `Pacific Time`, `PT` hoặc một bản dịch trong ngôn ngữ khác:

- Có thể thay đổi theo ngôn ngữ/locale.
- Có thể thay đổi theo phiên bản dữ liệu địa phương hóa trong JDK.
- Có thể mơ hồ hoặc không xác định duy nhất region mong muốn.
- Không phải cách lưu rõ ràng các quy tắc timezone của một vùng.

**Khuyến nghị:** Dùng `VV`/`ZoneId.getId()` khi cần lưu định danh vùng; dùng `z`/`v` cho **hiển thị cho con người**. Khi parse dữ liệu bên ngoài, ưu tiên region ID rõ ràng hoặc offset theo format công bố, không phụ thuộc abbreviation tự do.

## 10. Ví dụ 2 — zone ID, tên mùa đông/mùa hè, offset thực tế

Tạo file **ZoneNamesDemo.java**:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

public class ZoneNamesDemo {
    public static void main(String[] args) {
        ZoneId paris = ZoneId.of("Europe/Paris");

        ZonedDateTime winter = Instant
            .parse("2024-01-15T12:00:00Z")
            .atZone(paris);

        ZonedDateTime summer = Instant
            .parse("2024-07-15T12:00:00Z")
            .atZone(paris);

        List<String> patterns = Arrays.asList(
            "VV", "z", "zzzz", "v", "vvvv",
            "XXX", "O", "OOOO"
        );

        for (String pattern : patterns) {
            DateTimeFormatter formatter =
                DateTimeFormatter.ofPattern(
                    pattern, Locale.US
                );

            System.out.println(
                pattern + " Winter=" +
                formatter.format(winter) +
                " Summer=" +
                formatter.format(summer)
            );
        }
    }
}
```

```bash
javac ZoneNamesDemo.java
java ZoneNamesDemo
```

Đầu ra đã xác nhận trong môi trường JDK thử nghiệm, `Locale.US`:

```text
VV Winter=Europe/Paris Summer=Europe/Paris
z Winter=CET Summer=CEST
zzzz Winter=Central European Standard Time Summer=Central European Summer Time
v Winter=CET Summer=CET
vvvv Winter=Central European Time Summer=Central European Time
XXX Winter=+01:00 Summer=+02:00
O Winter=GMT+1 Summer=GMT+2
OOOO Winter=GMT+01:00 Summer=GMT+02:00
```

**Diễn giải:**

1. `VV` luôn là `Europe/Paris` vì region ID được lưu trong `ZonedDateTime`.
2. `z` và `zzzz` phản ánh nhãn standard/daylight ở hai mùa trong locale và bộ dữ liệu thử nghiệm.
3. `v` và `vvvv` dùng nhãn tổng quát, không đổi tên theo DST.
4. `XXX` in offset **thực tế** tại từng `Instant`: `+01:00` và `+02:00`.
5. `O`/`OOOO` hiển thị offset có tiền tố `GMT` theo Locale.US.

**Độ ổn định:** Tên/abbreviation của `z`, `v` không nên hardcode trong test chạy xuyên mọi phiên bản CLDR/JDK và locale. Nếu cần test có tính bất biến mạnh, test `ZoneId`, `ZoneOffset`, `Instant` và các quan hệ của chúng; các output tên hiển thị có thể được kiểm thử riêng theo bộ dữ liệu locale/runtime bạn hỗ trợ.

## 11. Các pattern cần dữ liệu nào?

Một formatter chỉ có thể in những trường mà đối tượng temporal cung cấp, trừ khi bạn bổ sung ngữ cảnh qua formatter.

| Pattern | `LocalDateTime` | `OffsetDateTime` | `ZonedDateTime` | `Instant` trực tiếp |
| --- | --- | --- | --- | --- |
| `uuuu-MM-dd HH:mm` | Có | Có | Có | Không có field local để format trực tiếp |
| `XXX` | Không có offset | Có | Có | Không có offset để format trực tiếp |
| `VV` | Không có ZoneId | Không có region ID | Có khi nguồn chứa zone | Không có ZoneId |
| `z` / `v` | Không có zone | Không có region zone | Có khi nguồn chứa zone | Không có zone |
| `uuuu-MM-dd HH:mm XXX VV` | Không có đủ trường | Không có region zone | Có | Không nếu chưa cấp zone |

**Ví dụ lỗi thực tế:** `DateTimeFormatter.ofPattern("XXX").format(LocalDateTime.now())` có thể ném `UnsupportedTemporalTypeException` vì `LocalDateTime` không giữ `OFFSET_SECONDS`. Tương tự, format `"VV"` trên `LocalDateTime` hoặc `OffsetDateTime` có thể ném `DateTimeException` vì không có ZoneId.

### 11.1. Muốn format Instant theo ngày giờ của vùng? Dùng withZone

`Instant` chỉ cung cấp một mốc trên timeline, không có các trường năm-tháng-ngày-giờ theo địa phương. Với formatter muốn in ngày/giờ và offset/zone:

```java
// Đoạn minh họa.
Instant time = Instant.parse("2024-06-10T13:00:00Z");

DateTimeFormatter formatter = DateTimeFormatter
    .ofPattern("uuuu-MM-dd HH:mm XXX VV")
    .withZone(ZoneId.of("Asia/Ho_Chi_Minh"));

String output = formatter.format(time);
// 2024-06-10 20:00 +07:00 Asia/Ho_Chi_Minh
```

`withZone(...)` thiết lập **override zone của formatter**, để Java có đủ dữ liệu hiển thị ngày giờ theo vùng. Nó **không thay đổi Instant gốc**.

### 11.2. withZone không biến LocalDateTime thành một timestamp rõ ràng

Nếu dữ liệu xuất phát từ `LocalDateTime` chưa có zone, việc dùng formatter có `withZone(...)` để **in một zone ID** không tự chứng minh local time đó tồn tại hay có offset duy nhất trong zone. Khi một local time phải xác định một Instant thực sự, cần **resolve** theo `ZoneRules` và chính sách gap/overlap.

## 12. Ví dụ 3 — thiếu field, lỗi format và withZone

Tạo file **SupportedFieldsDemo.java**:

```java
import java.time.DateTimeException;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class SupportedFieldsDemo {
    public static void main(String[] args) {
        Instant instant =
            Instant.parse("2024-06-10T13:00:00Z");

        DateTimeFormatter full =
            DateTimeFormatter.ofPattern(
                "uuuu-MM-dd HH:mm XXX VV",
                Locale.US
            );

        try {
            System.out.println("rawInstant=" +
                full.format(instant));
        } catch (DateTimeException ex) {
            System.out.println("rawInstant=" +
                ex.getClass().getSimpleName());
        }

        System.out.println("withZone=" +
            full.withZone(
                ZoneId.of("Asia/Ho_Chi_Minh")
            ).format(instant));

        LocalDateTime local =
            LocalDateTime.of(2024, 6, 10, 20, 0);

        try {
            System.out.println("localOffset=" +
                DateTimeFormatter.ofPattern("XXX")
                    .format(local));
        } catch (DateTimeException ex) {
            System.out.println("localOffset=" +
                ex.getClass().getSimpleName());
        }

        try {
            System.out.println("localZone=" +
                DateTimeFormatter.ofPattern("VV")
                    .format(local));
        } catch (DateTimeException ex) {
            System.out.println("localZone=" +
                ex.getClass().getSimpleName());
        }
    }
}
```

```bash
javac SupportedFieldsDemo.java
java SupportedFieldsDemo
```

Stdout:

```text
rawInstant=UnsupportedTemporalTypeException
withZone=2024-06-10 20:00 +07:00 Asia/Ho_Chi_Minh
localOffset=UnsupportedTemporalTypeException
localZone=DateTimeException
```

Đọc đúng kết quả: `rawInstant` không có field năm/tháng/giờ địa phương mà pattern yêu cầu. Sau `withZone`, formatter chuyển cách trình bày theo vùng và in được cả ngày giờ, offset và region. `LocalDateTime` không có offset và zone ID nên các pattern `XXX` và `VV` không thể lấy trường tương ứng.

### 12.1. OffsetDateTime vẫn khác ZonedDateTime

Với một `OffsetDateTime` có offset `+07:00`:

```java
// Đoạn minh họa.
OffsetDateTime odt =
    OffsetDateTime.parse("2024-06-10T20:15+07:00");

// Có thể in offset:
String offsetText =
    DateTimeFormatter.ofPattern("XXX").format(odt);

// Không thể giả định odt có region ID cho:
DateTimeFormatter.ofPattern("VV").format(odt);
// DateTimeException: không có ZoneId được cung cấp.
```

Người dùng đôi khi thấy offset `+07:00` và nghĩ đó là vùng `Asia/Ho_Chi_Minh`. Không có phép ánh xạ một-một như vậy; nhiều vùng có thể dùng cùng offset tại một thời điểm.

## 13. Offset có phần giây và số chữ X/x

`ZoneOffset` có thể biểu diễn giờ, phút và giây (trong phạm vi API). Khi offset chứa phần giây, pattern độ rộng 1–3 thường không in giây, còn độ rộng 4–5 có thể giữ phần đó.

### Ví dụ 4 — OffsetSecondsDemo.java

Tạo file **OffsetSecondsDemo.java**:

```java
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.Arrays;
import java.util.List;

public class OffsetSecondsDemo {
    public static void main(String[] args) {
        ZoneOffset offset =
            ZoneOffset.ofHoursMinutesSeconds(5, 30, 45);

        OffsetDateTime dateTime = OffsetDateTime.of(
            2024, 6, 10, 12, 0, 0, 0, offset
        );

        List<String> patterns = Arrays.asList(
            "X", "XX", "XXX", "XXXX", "XXXXX",
            "x", "xx", "xxx", "xxxx", "xxxxx",
            "Z", "ZZZZZ"
        );

        for (String pattern : patterns) {
            System.out.println(
                pattern + "=" +
                DateTimeFormatter.ofPattern(pattern)
                    .format(dateTime)
            );
        }
    }
}
```

```bash
javac OffsetSecondsDemo.java
java OffsetSecondsDemo
```

Stdout:

```text
X=+0530
XX=+0530
XXX=+05:30
XXXX=+053045
XXXXX=+05:30:45
x=+0530
xx=+0530
xxx=+05:30
xxxx=+053045
xxxxx=+05:30:45
Z=+0530
ZZZZZ=+05:30:45
```

**Bài học về round-trip:** Nếu bạn format offset `+05:30:45` bằng `XXX`, output chỉ là `+05:30`; parse chuỗi đó không thể suy ngược rằng offset gốc từng có `45` giây. Nếu yêu cầu giữ chính xác offset có giây, dùng formatter hỗ trợ giây hoặc dạng built-in thích hợp, và kiểm thử theo schema.

## 14. Phần optional: khác với dấu ngoặc vuông literal

`DateTimeFormatter` dùng `[` và `]` để đánh dấu **đoạn có thể có hoặc không có** khi format/parse. Việc “tùy chọn” có thể giúp một formatter chấp nhận:

- Chuỗi chỉ có local date-time.
- Chuỗi local date-time kèm offset.
- Chuỗi local date-time kèm offset và ZoneId.
- Trong một số format, chuỗi có local date-time và ZoneId nhưng không có offset.

Pattern minh họa:

```java
// Đây là một String pattern hợp lệ:
"uuuu-MM-dd'T'HH:mm:ss[XXX]['['VV']']"
```

Giải thích cấu trúc:

- `uuuu-MM-dd'T'HH:mm:ss`: phần bắt buộc ngày giờ.
- `[XXX]`: phần offset tùy chọn.
- `['['VV']']`: phần zone tùy chọn, gồm dấu `[`/`]` literal được quote và vùng `VV`.

**Đặc biệt:** `parseBest(...)` rất hữu ích khi format đầu vào có phần tùy chọn. Chỉ gọi `OffsetDateTime.parse(...)` trên mọi đầu vào là sai nếu một số chuỗi **không có offset**; `LocalDateTime` hoặc `ZonedDateTime` có thể phù hợp tùy thông tin được cung cấp.

### 14.1. parseBest thử truy vấn theo thứ tự

`parseBest(text, ZonedDateTime::from, OffsetDateTime::from, LocalDateTime::from)` thử các truy vấn theo thứ tự bạn đưa vào và trả kiểu đầu tiên tạo được từ dữ liệu parse.

Không giả định kiểu trả về chỉ phụ thuộc vào việc có **region ID** hay không. `ZoneOffset` cũng là một `ZoneId` trong hệ kiểu Java; vì thế một chuỗi có **offset nhưng không có region ID** vẫn có thể được dựng thành `ZonedDateTime` với zone dạng offset. Quyết định chấp nhận hay từ chối thông tin thiếu region là **quy tắc API**, không phải điều `parseBest` tự thực thi.

### Ví dụ 5 — OptionalZoneParseDemo.java

Tạo file **OptionalZoneParseDemo.java**:

```java
import java.time.DateTimeException;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.time.temporal.TemporalAccessor;
import java.util.Locale;

public class OptionalZoneParseDemo {
    public static void main(String[] args) {
        DateTimeFormatter formatter =
            DateTimeFormatter.ofPattern(
                "uuuu-MM-dd'T'HH:mm:ss[XXX]['['VV']']",
                Locale.US
            ).withResolverStyle(ResolverStyle.STRICT);

        String[] inputs = {
            "2024-06-10T09:00:00",
            "2024-06-10T09:00:00-04:00",
            "2024-06-10T09:00:00-04:00[America/New_York]",
            "2024-06-10T09:00:00[America/New_York]"
        };

        for (String input : inputs) {
            try {
                TemporalAccessor parsed = formatter.parseBest(
                    input,
                    ZonedDateTime::from,
                    OffsetDateTime::from,
                    LocalDateTime::from
                );

                System.out.println(
                    input + " -> " +
                    parsed.getClass().getSimpleName() +
                    " " + parsed
                );
            } catch (DateTimeException ex) {
                System.out.println(
                    input + " -> ERROR " +
                    ex.getClass().getSimpleName()
                );
            }
        }

        System.out.println("formatLocal=" +
            formatter.format(
                LocalDateTime.of(2024, 6, 10, 9, 0)
            ));

        System.out.println("formatOffset=" +
            formatter.format(
                OffsetDateTime.of(
                    2024, 6, 10, 9, 0, 0, 0,
                    ZoneOffset.ofHours(-4)
                )
            ));
    }
}
```

```bash
javac OptionalZoneParseDemo.java
java OptionalZoneParseDemo
```

Stdout:

```text
2024-06-10T09:00:00 -> LocalDateTime 2024-06-10T09:00
2024-06-10T09:00:00-04:00 -> ZonedDateTime 2024-06-10T09:00-04:00
2024-06-10T09:00:00-04:00[America/New_York] -> ZonedDateTime 2024-06-10T09:00-04:00[America/New_York]
2024-06-10T09:00:00[America/New_York] -> ZonedDateTime 2024-06-10T09:00-04:00[America/New_York]
formatLocal=2024-06-10T09:00:00
formatOffset=2024-06-10T09:00:00-04:00
```

**Những điều cần nắm:**

1. Chuỗi không có offset/zone chỉ cho `LocalDateTime`.
2. Chuỗi có offset nhưng thiếu region có thể trở thành `ZonedDateTime` với zone dựa trên offset.
3. Chuỗi có region rõ ràng trở thành `ZonedDateTime` với region đó.
4. Trong trường hợp chỉ có region và local date-time, resolver của Java chọn offset theo zone rules để dựng `ZonedDateTime`. Điều đó **có thể cần xem xét lại** trong DST gap/overlap.
5. Khi format `LocalDateTime`, cả hai đoạn tùy chọn bị bỏ qua vì không có thông tin tương ứng. Khi format `OffsetDateTime`, đoạn offset xuất hiện còn đoạn region ID bị bỏ qua.

**Lưu ý thiết kế:** Một formatter có thể chấp nhận nhiều biến thể, nhưng API production không nhất thiết nên cho phép tất cả. Nếu trường `offset` là bắt buộc, hãy **từ chối** biến thể chỉ có local date-time thay vì dùng optional parse và suy diễn từ timezone server.

## 15. Pattern không hợp lệ bị phát hiện khi tạo formatter

`DateTimeFormatter.ofPattern(pattern)` có thể ném `IllegalArgumentException` ngay nếu số lượng chữ cái pattern không đúng. Đây thường là **lỗi cấu hình/coding** chứ không phải lỗi dữ liệu người dùng.

### 15.1. Số lượng hợp lệ cần ghi nhớ

| Ký hiệu | Số ký tự hợp lệ | Ví dụ sai |
| --- | --- | --- |
| `V` | **Chỉ 2** | `V`, `VVV` |
| `v` | **1 hoặc 4** | `vv`, `vvv` |
| `z` | **1, 2, 3, 4** | `zzzzz` |
| `O` | **1 hoặc 4** | `OO`, `OOO` |
| `X` / `x` | **1 đến 5** | `XXXXXX` |
| `Z` | **1 đến 5** | `ZZZZZZ` |

Đừng biến một biến `pattern` không tin cậy thành cấu hình tự do mà không kiểm tra. Ứng dụng nên dùng các formatter được khai báo sẵn, kiểm thử và thống nhất schema.

### Ví dụ 6 — PatternLimitsDemo.java

Tạo file **PatternLimitsDemo.java**:

```java
import java.time.format.DateTimeFormatter;
import java.util.Arrays;
import java.util.List;

public class PatternLimitsDemo {
    static void check(String pattern) {
        try {
            DateTimeFormatter.ofPattern(pattern);
            System.out.println(pattern + "=VALID");
        } catch (IllegalArgumentException ex) {
            System.out.println(pattern + "=INVALID");
        }
    }

    public static void main(String[] args) {
        List<String> patterns = Arrays.asList(
            "V", "VV", "VVV",
            "v", "vv", "vvvv",
            "z", "zzzz", "zzzzz",
            "O", "OO", "OOOO",
            "X", "XXXXX", "XXXXXX",
            "Z", "ZZZZZ", "ZZZZZZ"
        );

        for (String pattern : patterns) {
            check(pattern);
        }
    }
}
```

```bash
javac PatternLimitsDemo.java
java PatternLimitsDemo
```

Stdout:

```text
V=INVALID
VV=VALID
VVV=INVALID
v=VALID
vv=INVALID
vvvv=VALID
z=VALID
zzzz=VALID
zzzzz=INVALID
O=VALID
OO=INVALID
OOOO=VALID
X=VALID
XXXXX=VALID
XXXXXX=INVALID
Z=VALID
ZZZZZ=VALID
ZZZZZZ=INVALID
```

Tại đây, một `INVALID` nghĩa là **formatter không xây được từ pattern**, khác hoàn toàn việc một formatter hợp lệ nhưng **không format được temporal thiếu field**. Hai lỗi có vị trí và nguyên nhân khác nhau:

- `IllegalArgumentException` ngay khi `ofPattern`: pattern không hợp lệ.
- `DateTimeException` hoặc `UnsupportedTemporalTypeException` khi `format`: thiếu thông tin temporal mà pattern yêu cầu.

## 16. ISO formatter dựng sẵn và pattern tự viết

Java cung cấp các formatter ISO có tên rõ ràng:

| Formatter | Mục đích | Ví dụ output |
| --- | --- | --- |
| `ISO_LOCAL_DATE_TIME` | Local date-time **không offset** | `2024-07-15T14:30:00` |
| `ISO_OFFSET_DATE_TIME` | Local date-time **có offset** | `2024-07-15T14:30:00+02:00` |
| `ISO_ZONED_DATE_TIME` | Có offset, thêm region zone khi có | `2024-07-15T14:30:00+02:00[Europe/Paris]` |
| `ISO_INSTANT` | Instant theo UTC | `2024-07-15T12:30:00Z` |
| `ISO_DATE_TIME` | Các thành phần offset và zone **có thể tùy chọn** | Có thể nhận nhiều dạng local/offset/zoned |

Với trao đổi dữ liệu giữa các service, chọn một formatter built-in hợp với **contract thực sự** thường dễ duy trì hơn tự viết pattern. Ví dụ, khi API quy định truyền UTC Instant, dùng `DateTimeFormatter.ISO_INSTANT`/`Instant.toString()`; nếu cần truyền offset, dùng `ISO_OFFSET_DATE_TIME`; nếu cần region ID, dùng `ISO_ZONED_DATE_TIME` hoặc một schema có zone ID riêng.

**Lưu ý:** Phần `[Europe/Paris]` ở biểu diễn ISO zoned là một **mở rộng ISO-like của Java**, không phải thành phần bắt buộc của mọi chuẩn ISO-8601 bên ngoài. Đừng giả định mọi client hoặc database đều hiểu bracketed zone ID.

### Ví dụ 7 — IsoFormatterDemo.java

Tạo file **IsoFormatterDemo.java**:

```java
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class IsoFormatterDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("Europe/Paris");

        ZonedDateTime dateTime = ZonedDateTime.of(
            2024, 7, 15, 14, 30, 0, 0, zone
        );

        System.out.println("isoZoned=" +
            DateTimeFormatter.ISO_ZONED_DATE_TIME
                .format(dateTime));

        System.out.println("isoOffset=" +
            DateTimeFormatter.ISO_OFFSET_DATE_TIME
                .format(dateTime));

        System.out.println("isoInstant=" +
            DateTimeFormatter.ISO_INSTANT
                .format(dateTime));

        DateTimeFormatter custom = DateTimeFormatter
            .ofPattern(
                "uuuu-MM-dd HH:mm XXX '['VV']'",
                Locale.US
            );

        System.out.println("custom=" +
            custom.format(dateTime));

        String encoded =
            DateTimeFormatter.ISO_ZONED_DATE_TIME
                .format(dateTime);

        System.out.println("parsedSameInstant=" +
            ZonedDateTime.parse(encoded)
                .toInstant()
                .equals(dateTime.toInstant()));
    }
}
```

```bash
javac IsoFormatterDemo.java
java IsoFormatterDemo
```

Stdout:

```text
isoZoned=2024-07-15T14:30:00+02:00[Europe/Paris]
isoOffset=2024-07-15T14:30:00+02:00
isoInstant=2024-07-15T12:30:00Z
custom=2024-07-15 14:30 +02:00 [Europe/Paris]
parsedSameInstant=true
```

**Phân tích:**

1. `ISO_ZONED_DATE_TIME` giữ region ID ở cách biểu diễn.
2. `ISO_OFFSET_DATE_TIME` có timestamp và offset nhưng **không bảo toàn region ID**.
3. `ISO_INSTANT` đưa thời điểm về UTC, không hiển thị zone địa phương.
4. Pattern custom in dấu `[`/`]` literal nhờ `'['` và `']'`.
5. Chuỗi ISO zoned trong ví dụ parse lại cho đúng Instant ban đầu.

Tính đúng đắn của một phép round-trip không chỉ là `parse` chạy thành công: phải xác định bạn cần giữ **cùng Instant**, **cùng local time**, **cùng offset** hay **cùng region ID**. Chuyển sang ISO instant có thể giữ Instant hoàn hảo nhưng cố ý **không giữ biểu diễn vùng**.

## 17. Parsing offset: format đúng và resolver đúng

Một formatter dùng `XXX` có thể đọc chuỗi offset có dấu hai chấm như `+05:30`, và dùng `Z` khi offset zero. Ví dụ pattern:

```java
// Mã minh họa:
DateTimeFormatter formatter = DateTimeFormatter
    .ofPattern("uuuu-MM-dd HH:mm XXX", Locale.US)
    .withResolverStyle(ResolverStyle.STRICT);
```

Cần lưu ý hai cơ chế của `DateTimeFormatter`:

1. **Lexical parsing:** đọc ký tự theo pattern, ví dụ dấu cách, dấu `-` và vị trí offset.
2. **Resolving:** kết hợp các field năm-tháng-ngày-giờ thành giá trị temporal hợp lệ.

`DateTimeFormatter.ofPattern(...)` mặc định dùng `ResolverStyle.SMART`. Với input quan trọng yêu cầu **không tự sửa ngày không tồn tại**, nên đặt `ResolverStyle.STRICT` rõ ràng hoặc dùng ISO formatter có hợp đồng phù hợp.

Khi dùng strict resolver và parse ISO-like year, `uuuu` (proleptic year) thường đơn giản hơn `yyyy` (year-of-era) nếu pattern không bao gồm era. Không thay `uuuu` bằng `YYYY`: chữ `Y` là năm theo tuần, có thể tạo khác biệt ở cuối năm.

### Ví dụ 8 — OffsetParseDemo.java

Tạo file **OffsetParseDemo.java**:

```java
import java.time.OffsetDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class OffsetParseDemo {
    public static void main(String[] args) {
        DateTimeFormatter formatter = DateTimeFormatter
            .ofPattern(
                "uuuu-MM-dd HH:mm XXX",
                Locale.US
            )
            .withResolverStyle(ResolverStyle.STRICT);

        OffsetDateTime dateTime = OffsetDateTime.parse(
            "2024-06-10 20:15 +05:30",
            formatter
        );

        System.out.println("parsed=" + dateTime);

        OffsetDateTime utc = OffsetDateTime.parse(
            "2024-06-10 20:15 Z",
            formatter
        );

        System.out.println("utc=" + utc);

        try {
            OffsetDateTime.parse(
                "2024-06-10 20:15",
                formatter
            );
        } catch (DateTimeParseException ex) {
            System.out.println("missingOffset=REJECTED");
        }
    }
}
```

```bash
javac OffsetParseDemo.java
java OffsetParseDemo
```

Stdout:

```text
parsed=2024-06-10T20:15+05:30
utc=2024-06-10T20:15Z
missingOffset=REJECTED
```

**Ý nghĩa:** Khi offset là một phần **bắt buộc** của contract, thiếu offset phải bị từ chối. Đừng tự thêm `Z` hoặc lấy timezone hệ thống để hoàn thiện input, trừ khi hợp đồng API đã nói rõ. `OffsetDateTime` biểu diễn được một Instant vì nó có offset; `LocalDateTime` không đủ dữ liệu để biết cùng Instant.

### 17.1. Không parse tên z/v như một định danh vùng duy nhất

Ví dụ chuỗi `"CST"` có thể được hiểu khác nhau trong các hệ thống/địa phương. Ngay cả nếu formatter parse được một tên ngắn, không nên dựa vào tên đó để thay cho một region ID do ứng dụng chủ động chọn. Với dữ liệu cần tính đúng timestamp, nên yêu cầu `ZoneId`/offset có contract rõ, và kiểm tra quy tắc vùng ở ngày liên quan.

### 17.2. Case sensitivity và region ID

Các formatter built-in ISO có thể áp dụng cách xử lý case khác nhau tùy phần cấu trúc; ví dụ zone ID ở phần ngoặc của `ISO_ZONED_DATE_TIME` được xử lý theo cơ chế case-sensitive. Không tự lower-case một tên như `America/New_York` rồi cho rằng mọi parser và JDK đều đồng ý.

Nếu UI có thể nhận tên vùng từ người dùng, tốt nhất cung cấp danh sách ID vùng hợp lệ hoặc đối chiếu với dữ liệu `ZoneId.getAvailableZoneIds()` theo chính sách hệ thống, thay vì tự chuyển đổi chuỗi không kiểm tra.

## 18. Khi cả offset và ZoneId cùng xuất hiện: kiểm tra tính nhất quán

Một chuỗi có thể chứa **hai thông tin độc lập**:

```text
2024-06-10T09:00-04:00[America/New_York]
                  |          |
             offset        region ID
```

Trong ví dụ này, offset `-04:00` phù hợp với New York vào ngày đó. Nhưng người dùng có thể gửi:

```text
2024-06-10T09:00+02:00[America/New_York]
```

Offset `+02:00` không phù hợp với 09:00 ở New York vào ngày 10/06/2024. `ZonedDateTime.parse(...)` trong những tình huống như vậy **có thể xác định Instant từ offset và điều chỉnh lại local clock theo zone**, thay vì từ chối ba trường ban đầu.

Khi hợp đồng nghiệp vụ là “local time, offset và zone ID phải **cùng đúng** tại một thời điểm”, việc parser không ném lỗi **chưa đủ** để xác thực. Dùng:

```java
// Đoạn minh họa:
ZonedDateTime.ofStrict(
    LocalDateTime.of(2024, 6, 10, 9, 0),
    ZoneOffset.ofHours(2),
    ZoneId.of("America/New_York")
);
// DateTimeException: offset không hợp lệ cho local time/zone này.
```

`ZonedDateTime.ofStrict` chỉ chấp nhận offset **có hiệu lực tại local time** theo ZoneRules. Đặc biệt, với DST gap không có offset hợp lệ; với DST overlap có thể có hơn một offset hợp lệ.

### Ví dụ 9 — StrictZonePairDemo.java

Tạo file **StrictZonePairDemo.java**:

```java
import java.time.DateTimeException;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;

public class StrictZonePairDemo {
    public static void main(String[] args) {
        String valid =
            "2024-06-10T09:00-04:00[America/New_York]";

        String mismatch =
            "2024-06-10T09:00+02:00[America/New_York]";

        System.out.println("valid=" +
            ZonedDateTime.parse(valid));

        System.out.println("mismatchParsed=" +
            ZonedDateTime.parse(mismatch));

        try {
            ZonedDateTime.ofStrict(
                LocalDateTime.of(2024, 6, 10, 9, 0),
                ZoneOffset.ofHours(2),
                ZoneId.of("America/New_York")
            );
            System.out.println("strict=OK");
        } catch (DateTimeException ex) {
            System.out.println("strict=REJECTED");
        }

        ZoneId paris = ZoneId.of("Europe/Paris");
        LocalDateTime overlap =
            LocalDateTime.of(2024, 10, 27, 2, 30);

        System.out.println("overlapOffsets=" +
            paris.getRules().getValidOffsets(overlap));
    }
}
```

```bash
javac StrictZonePairDemo.java
java StrictZonePairDemo
```

Stdout đã kiểm thử:

```text
valid=2024-06-10T09:00-04:00[America/New_York]
mismatchParsed=2024-06-10T03:00-04:00[America/New_York]
strict=REJECTED
overlapOffsets=[+02:00, +01:00]
```

**Diễn giải:**

1. Chuỗi `valid` mô tả cặp local time/offset/zone phù hợp ở New York.
2. Chuỗi `mismatch` vẫn được `ZonedDateTime.parse` chuyển thành một ZonedDateTime nhưng **giờ địa phương thành 03:00**, không còn 09:00 như input. Đây là hậu quả dễ bị bỏ qua nếu coi “parse được” = “ba trường đầu vào nhất quán”.
3. `ofStrict` từ chối offset `+02:00` với 09:00 New York vì offset này không có hiệu lực tại local time đó.
4. Paris vào 02:30 ngày 27/10/2024 có hai offset hợp lệ do đồng hồ lùi, cho thấy việc chọn một giờ địa phương và một region ID đôi khi **chưa đủ để biết một Instant duy nhất**.

**Chọn chính sách sản phẩm:** Nếu API nhận **một timestamp theo offset** làm nguồn sự thật, điều chỉnh local clock theo zone có thể có ngữ nghĩa chấp nhận được. Nếu API nhận **giờ người dùng chọn ở một địa phương**, phải xác thực local time/offset/zone đúng theo contract và không điều chỉnh âm thầm.

## 19. Các lỗi thường gặp và cách sửa

### Lỗi 1 — dùng X và x như thể giống nhau mọi trường hợp

Khác biệt rõ ở offset zero: `X` in `Z`, `x` in `+00`/`+0000`/`+00:00`.

**Sửa:** Chọn `X`/`XXX` hoặc `x`/`xxx` theo schema đầu ra; kiểm thử riêng offset zero.

### Lỗi 2 — nghĩ `Z` luôn in chữ Z

Pattern `Z` một ký tự thường cho `+0000` tại UTC; `ZZZZZ` mới có cách in zero là `Z`.

**Sửa:** Đọc đúng số ký tự hoặc dùng ISO formatter.

### Lỗi 3 — nghĩ `XXX` là tên timezone

`XXX` chỉ in offset như `+07:00`, không có region ID.

**Sửa:** Dùng `VV` trên `ZonedDateTime` khi cần region.

### Lỗi 4 — dùng `V` một ký tự

Pattern zone ID yêu cầu **`VV` đúng hai chữ V**.

**Sửa:** `DateTimeFormatter.ofPattern("VV")`.

### Lỗi 5 — dùng `vv` hoặc `OO`

`v` và `O` chỉ chấp nhận số ký tự 1 hoặc 4.

**Sửa:** `v`/`vvvv`; `O`/`OOOO`.

### Lỗi 6 — dùng `zzzzz` và nghĩ nó là tên hẹp

Đối với zone names, `z` chỉ cho phép 1–4 ký tự; 5+ không hợp lệ.

**Sửa:** Chọn `z` hoặc `zzzz` khi cần short/full display name.

### Lỗi 7 — dùng `X` quá sáu ký tự

`X`/`x` chỉ cho phép 1–5 ký tự; dài hơn ném `IllegalArgumentException` khi tạo formatter.

**Sửa:** Chọn width phù hợp với dấu hai chấm và độ chính xác offset.

### Lỗi 8 — áp dụng VV/z/v trên OffsetDateTime

`OffsetDateTime` có offset nhưng không giữ region ZoneId; formatter có thể ném `DateTimeException` vì thiếu zone.

**Sửa:** Dùng `ZonedDateTime` nếu cần region hoặc lưu ZoneId riêng.

### Lỗi 9 — format Instant trực tiếp bằng pattern ngày giờ

`Instant` không cung cấp local date/time fields cho pattern thông thường.

**Sửa:** Dùng `formatter.withZone(zone).format(instant)` hoặc `instant.atZone(zone)` trước.

### Lỗi 10 — nhầm tên localized với ID ổn định

`CET`, `Pacific Time` hay các bản dịch có thể phụ thuộc locale/JDK hoặc mơ hồ.

**Sửa:** Lưu/trao đổi `ZoneId.getId()`; dùng `z`/`v` cho giao diện.

### Lỗi 11 — nhầm ngoặc vuông literal với optional

`[XXX]` là optional; không in ngoặc thật. Khi muốn `[Europe/Paris]`, phải quote dấu ngoặc `'['VV']'`.

**Sửa:** Test format lẫn parse đối với pattern có optional/literal.

### Lỗi 12 — cho rằng parseBest luôn trả OffsetDateTime nếu chuỗi chỉ có offset

`ZoneOffset` cũng là `ZoneId`; thứ tự query quyết định loại kết quả có thể tạo được.

**Sửa:** Đặt các query theo loại dữ liệu thực sự chấp nhận, sau đó validate fields bắt buộc.

### Lỗi 13 — dùng tên z làm nguồn sự thật cho giao dịch

Tên zone có thể thay đổi theo DST, locale hoặc dữ liệu ngôn ngữ.

**Sửa:** Lưu Instant cùng offset/ZoneId theo nhu cầu, không chỉ display label.

### Lỗi 14 — chọn pattern thiếu giây cho offset thực sự có giây

`XXX` không giữ hết phần seconds của một `+05:30:45`.

**Sửa:** Kiểm tra precision và chọn `XXXXX`/format phù hợp khi cần.

### Lỗi 15 — dùng ofPattern mặc định khi cần validate ngày strict

`ofPattern` mặc định `SMART`, có thể điều chỉnh ngày không tồn tại khi resolve.

**Sửa:** `withResolverStyle(ResolverStyle.STRICT)` và chọn pattern `uuuu` phù hợp.

### Lỗi 16 — dùng yyyy và YYYY như thể giống nhau

`yyyy` là year-of-era; `YYYY` là week-based year, có thể khác ở ranh giới năm.

**Sửa:** Dùng `uuuu` cho ISO proleptic year khi mục tiêu là ngày lịch thông thường.

### Lỗi 17 — nghĩ ZonedDateTime.parse tự xác nhận cặp zone/offset đầu vào

Parser có thể resolve lại local clock khi offset và region mâu thuẫn.

**Sửa:** Với contract yêu cầu ba trường nhất quán, parse các thành phần rồi dùng `ZonedDateTime.ofStrict`.

### Lỗi 18 — dùng GMT+... localized output như chuỗi API chuẩn duy nhất

`O`/`ZZZZ` chịu ảnh hưởng locale và dữ liệu hiển thị.

**Sửa:** Ưu tiên ISO formatter/offset dạng `XXX` khi giao tiếp máy-máy.

### Lỗi 19 — thêm zone mặc định của server khi đầu vào thiếu zone

Dẫn đến lệch lịch hẹn ở môi trường có timezone khác hoặc khi DST đổi.

**Sửa:** Yêu cầu zone rõ, hoặc công bố chính sách mặc định có căn cứ; không âm thầm dựa vào `ZoneId.systemDefault()`.

### Lỗi 20 — hardcode output z/v của một JDK làm luật toàn cầu

Dữ liệu display names có thể được cập nhật.

**Sửa:** Test ngữ nghĩa ZoneId/Instant/offset độc lập, và quản lý snapshot dữ liệu locale nếu phải so sánh chính xác text.

## 20. Quy tắc chọn pattern theo mục đích

| Mục đích | Pattern/API nên bắt đầu với | Lý do |
| --- | --- | --- |
| Timestamp ISO có offset | `DateTimeFormatter.ISO_OFFSET_DATE_TIME` | Không cần tự viết pattern nếu schema phù hợp |
| Timestamp UTC | `DateTimeFormatter.ISO_INSTANT` | UTC theo Instant, có `Z` |
| Timestamp có region zone | `DateTimeFormatter.ISO_ZONED_DATE_TIME` | Giữ offset và zone ID khi có |
| Chỉ in `+07:00` hoặc `Z` | `XXX` | Offset với dấu hai chấm và zero `Z` |
| Chỉ in `+07:00` hoặc `+00:00` | `xxx` | Giữ zero dạng số |
| In `+0700` / `+0000` | `ZZZ` hoặc `xx` theo contract | Không có dấu hai chấm |
| In localized GMT+... ngắn | `O` | Output giao diện địa phương hóa |
| In localized GMT+... đầy đủ | `OOOO` / `ZZZZ` | Output giao diện địa phương hóa |
| In region ID | `VV` | In định danh theo nguồn có ZoneId |
| In short zone name theo DST | `z` | Dùng cho UI |
| In tên zone đầy đủ theo DST | `zzzz` | Dùng cho UI |
| In tên zone tổng quát | `v` / `vvvv` | Dùng cho UI, không phụ thuộc daylight label |
| Format Instant theo vùng | `formatter.withZone(zone)` | Bổ sung ngữ cảnh thời gian địa phương |
| Parse input có offset tùy chọn | `parseBest` với queries phù hợp | Phân biệt kiểu kết quả và chính sách field bắt buộc |

**Quy tắc thực tế:** Với dữ liệu kỹ thuật và liên hệ đa hệ thống, chọn các ISO formatter dựng sẵn trước. Dùng pattern tùy biến khi có **hợp đồng format cụ thể** hoặc nhu cầu UI có locale. Tên hiển thị không thay cho ID vùng.

## 21. Câu hỏi tự kiểm tra

**Câu 1.** `XXX` in offset `+05:30` thành gì?

**Đáp án:** `+05:30`.

**Câu 2.** `XXX` và `xxx` in offset zero khác nhau thế nào?

**Đáp án:** `XXX` in `Z`; `xxx` in `+00:00`.

**Câu 3.** `Z` một ký tự in zero thành chữ Z không?

**Đáp án:** Không; theo quy tắc độ rộng 1–3, nó in `+0000`.

**Câu 4.** Muốn in region `Europe/Paris`, pattern nào?

**Đáp án:** `VV` trên một temporal có ZoneId.

**Câu 5.** Vì sao `DateTimeFormatter.ofPattern("V")` không hợp lệ?

**Đáp án:** Chữ `V` yêu cầu đúng hai ký tự `VV`.

**Câu 6.** `v` và `z` khác nhau ở điểm nào?

**Đáp án:** `z` chọn tên standard/daylight khi có đủ thông tin; `v` là tên tổng quát không phân biệt daylight label.

**Câu 7.** Những độ rộng nào hợp lệ cho `O`?

**Đáp án:** `O` hoặc `OOOO`.

**Câu 8.** `z` có cho phép năm ký tự không?

**Đáp án:** Không. `z`/`zz`/`zzz` là short, `zzzz` là full, 5+ không hợp lệ.

**Câu 9.** Vì sao `OffsetDateTime` có thể in `XXX` nhưng không in được `VV`?

**Đáp án:** Vì nó giữ offset, không giữ region ZoneId.

**Câu 10.** Format một `Instant` bằng pattern `"uuuu-MM-dd HH:mm XXX VV"` phải làm gì trước?

**Đáp án:** Chọn ZoneId để format bằng `withZone(zone)` hoặc chuyển `instant.atZone(zone)`.

**Câu 11.** `"uuuu-MM-dd'T'HH:mm:ss[XXX]"` có bắt buộc có offset không?

**Đáp án:** Không. `[XXX]` là đoạn tùy chọn; cần validation riêng nếu schema bắt buộc offset.

**Câu 12.** Muốn in dấu `[` và `]` bao quanh ZoneId trong pattern, phải làm sao?

**Đáp án:** Quote dấu ngoặc: `'['VV']'`.

**Câu 13.** `parseBest` với `ZonedDateTime::from` đầu tiên có thể trả ZonedDateTime cho chuỗi chỉ có offset không?

**Đáp án:** Có. `ZoneOffset` cũng là một `ZoneId`, đủ để dựng ZonedDateTime có fixed-offset zone.

**Câu 14.** Tại sao không nên lưu `CET` làm timezone ID cố định của user?

**Đáp án:** Vì tên ngắn có thể mơ hồ và phụ thuộc locale/nguồn dữ liệu; cần region ID rõ ràng.

**Câu 15.** Pattern `XXX` có giữ giây của offset `+05:30:45` không?

**Đáp án:** Không. Muốn hỗ trợ giây, chọn độ rộng phù hợp như `XXXXX` khi cần.

**Câu 16.** Nếu `ZonedDateTime.parse` thành công với chuỗi offset và zone mâu thuẫn, dữ liệu đầu vào có nhất thiết nhất quán không?

**Đáp án:** Không. Parser có thể điều chỉnh local clock theo zone. Dùng `ZonedDateTime.ofStrict` nếu phải kiểm tra ba thành phần.

**Câu 17.** Tại sao một ví dụ `z` ở Locale.US có thể khác hiển thị ở Locale.FRANCE?

**Đáp án:** Vì tên múi giờ được địa phương hóa và có thể khác theo locale/JDK data.

**Câu 18.** `DateTimeFormatter.ofPattern` mặc định có resolver style gì?

**Đáp án:** `SMART`. Khi yêu cầu strict calendar validation, đặt `ResolverStyle.STRICT`.

## 22. Tài liệu chính thức hiện hành

- [Oracle Java SE 26 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeFormatter.html): bảng pattern letters `V`/`z`/`v`/`O`/`X`/`x`/`Z`, độ rộng, optional sections và các ISO formatter.
- [Oracle Java SE 26 — DateTimeFormatterBuilder](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html): tạo formatter mức thấp, optional start/end, appendZoneId, appendOffset, xử lý parse.
- [Oracle Java SE 26 — ZonedDateTime](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZonedDateTime.html): `parse`, `ofStrict`, zone và offset.
- [Oracle Java SE 26 — OffsetDateTime](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/OffsetDateTime.html): offset date-time không lưu region ID.
- [Oracle Java SE 26 — ZoneId](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZoneId.html): ID vùng và quy tắc múi giờ.
- [Oracle Java SE 26 — ZoneOffset](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZoneOffset.html): biểu diễn và giới hạn offset.
- [Oracle Java SE 26 — ResolverStyle](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/ResolverStyle.html): `STRICT`, `SMART`, `LENIENT` trong parse.

**Ghi nhớ:** `X`/`x`/`Z`/`O` định dạng **offset** theo những quy tắc khác nhau về số ký tự và offset zero; `VV` định dạng **zone ID**; `z`/`v` định dạng **tên múi giờ cho giao diện** và phụ thuộc locale/DST. Khi format, phải chọn temporal có đủ field hoặc bổ sung zone cho Instant; khi parse, phải hiểu optional sections, resolver style, yêu cầu field bắt buộc và tính nhất quán giữa local time, offset và zone. Để trao đổi timestamp ổn định, hãy ưu tiên formatter ISO dựng sẵn và giữ ZoneId/Instant trong dữ liệu, thay vì coi một tên hiển thị là định danh múi giờ.