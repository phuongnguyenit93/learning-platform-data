# DateTimeException và dữ liệu không hợp lệ trong java.time

## 1. Mục tiêu

Khi làm việc với ngày giờ trong ứng dụng Java, một chuỗi có dạng giống ngày tháng chưa chắc biểu diễn **ngày hợp lệ**. Người dùng có thể nhập `2023-02-29`, `2024-13-01`, `24:15`, hoặc một local date-time rơi đúng khoảng chuyển đổi giờ mùa hè tại một múi giờ cụ thể. Java cung cấp những công cụ xác thực các trường hợp này và báo lỗi qua nhóm **`DateTimeException`**.

`java.time.DateTimeException` kế thừa `RuntimeException`. Nó được dùng khi quá trình **tạo**, **truy vấn** hoặc **thao tác** các đối tượng ngày giờ gặp giá trị không hợp lệ hay thao tác không hỗ trợ. `DateTimeParseException`, `ZoneRulesException` và `UnsupportedTemporalTypeException` là những subclass quan trọng.

Bài học tập trung vào:

- Những đầu vào ngày/giờ nào gây `DateTimeException` hoặc `DateTimeParseException`.
- Khác biệt giữa **chuỗi sai cú pháp**, **ngày không tồn tại** và **dữ liệu thiếu**.
- Vai trò của `DateTimeFormatter` cùng `ResolverStyle.STRICT`, `SMART` và `LENIENT`.
- Cạm bẫy từ `uuuu`, `yyyy`, pattern mặc định và việc “tự sửa” ngày sai.
- Những trường hợp DST *gap/overlap* khiến local date-time hợp lệ về mặt số học nhưng không xác định một thời điểm duy nhất.
- Những thao tác ngày giờ tự điều chỉnh có chủ đích như `plusMonths`, phân biệt với exception.
- Thiết kế validation trả mã lỗi ổn định, kiểm thử biên, và bắt lỗi đúng phạm vi.

Đây là các kiến thức từ Java 8 **vẫn áp dụng trong Java hiện đại, không phải kỹ thuật legacy**. Những chương trình đầy đủ bên dưới chạy với **JDK 17+**; nơi dùng tính năng xuất hiện sau Java 8 sẽ được ghi chú.

## 2. Phân loại DateTimeException và các lỗi liên quan

Sơ đồ kế thừa rút gọn:

```text
RuntimeException
    |
    +-- java.time.DateTimeException
          |
          +-- java.time.format.DateTimeParseException
          +-- java.time.temporal.UnsupportedTemporalTypeException
          +-- java.time.zone.ZoneRulesException
```

| Loại | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `DateTimeException` | Giá trị/thao tác date-time không hợp lệ | `LocalDate.of(2023, 2, 29)` |
| `DateTimeParseException` | Thất bại khi đọc/resolve chuỗi vào kiểu temporal | `LocalDate.parse("2023-02-29")` |
| `UnsupportedTemporalTypeException` | Truy vấn field/unit không được kiểu temporal hỗ trợ | Hỏi `HOUR_OF_DAY` từ `LocalDate` |
| `ZoneRulesException` | Thiếu hoặc không truy xuất được quy tắc timezone | `ZoneId.of("Mars/Phobos")` trên TZDB thông thường |
| `NullPointerException` | Đưa `null` vào tham số bắt buộc non-null | `LocalDate.parse(null)` |
| `IllegalArgumentException` | Tham số cấu hình API không hợp lệ | `DateTimeFormatter.ofPattern("QQQQQQ")` |
| `ArithmeticException` | Một số phép cộng/trừ ngày giờ xảy ra tràn số học | Tùy overload và giá trị lượng tăng rất lớn |

**Hai điểm phải phân biệt:**

1. `DateTimeException` là **unchecked exception**; nó không bắt buộc method khai báo `throws`.
2. **Không phải mọi lỗi khi thao tác ngày giờ đều thuộc DateTimeException**. `null`, pattern cấu hình sai hoặc overflow toán học có thể mang loại exception khác. Đừng catch `DateTimeException` rồi kết luận tất cả đều là lỗi của người nhập.

Nếu cùng một khối `try` xử lý cả lỗi parse và các lỗi date-time khác, thứ tự catch phải từ **subclass tới superclass**. `DateTimeParseException` kế thừa `DateTimeException`, nên phải đứng trước.

## 3. Dữ liệu không hợp lệ khi tạo ngày giờ

### 3.1. LocalDate.of kiểm tra tổ hợp ngày-tháng-năm

`LocalDate.of(year, month, dayOfMonth)` không chỉ kiểm tra từng trường độc lập, mà còn xác thực liệu tổ hợp đó tồn tại trong lịch ISO:

```java
// Mã minh họa; cần import java.time.LocalDate.
LocalDate leap = LocalDate.of(2024, 2, 29); // Hợp lệ.
LocalDate invalid = LocalDate.of(2023, 2, 29); // DateTimeException.
```

Ví dụ sai thường gặp:

| Đầu vào | Kết quả |
| --- | --- |
| `LocalDate.of(2024, 2, 29)` | Hợp lệ: năm nhuận |
| `LocalDate.of(2023, 2, 29)` | Lỗi: tháng 2/2023 có 28 ngày |
| `LocalDate.of(2024, 4, 31)` | Lỗi: tháng 4 chỉ có 30 ngày |
| `LocalDate.of(2024, 13, 1)` | Lỗi: tháng 13 không tồn tại |
| `LocalDate.of(2024, 1, 0)` | Lỗi: ngày trong tháng phải bắt đầu từ 1 |

**Lưu ý về năm nhuận:** Việc chia hết cho 4 không phải quy tắc đầy đủ trong lịch Gregorian. Năm chia hết cho 100 không nhuận, trừ khi chia hết cho 400. Dùng `LocalDate` và `Year.isLeap(year)` thay vì tự viết điều kiện thiếu nhánh.

### 3.2. LocalTime, ZoneOffset và giới hạn trường

`LocalTime.of(hour, minute)` chấp nhận giờ từ `0` đến `23`, phút từ `0` đến `59`. Vì vậy `LocalTime.of(24, 15)` ném `DateTimeException`.

`ZoneOffset` có phạm vi hợp lệ tối đa ±18 giờ. `ZoneOffset.ofHours(19)` ném `DateTimeException`. Không nên tự chấp nhận offset ngoài phạm vi rồi cố “ép” về một offset gần nhất.

### Ví dụ 1 — DateConstructDemo.java

Tạo file **DateConstructDemo.java**:

```java
import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.ZoneOffset;

public class DateConstructDemo {
    static void test(String name, Runnable action) {
        try {
            action.run();
            System.out.println(name + "=OK");
        } catch (DateTimeException ex) {
            System.out.println(name + "=" +
                ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        System.out.println("validLeap=" +
            LocalDate.of(2024, 2, 29));

        test("notLeap",
            () -> LocalDate.of(2023, 2, 29));

        test("month13",
            () -> LocalDate.of(2024, 13, 1));

        test("hour24",
            () -> LocalTime.of(24, 15));

        test("offset19",
            () -> ZoneOffset.ofHours(19));
    }
}
```

```bash
javac DateConstructDemo.java
java DateConstructDemo
```

Stdout:

```text
validLeap=2024-02-29
notLeap=DateTimeException
month13=DateTimeException
hour24=DateTimeException
offset19=DateTimeException
```

Hàm `test` chỉ là công cụ **minh họa và kiểm thử** các hành vi từ API. Code production không nên chỉ bắt mọi `DateTimeException` rồi bỏ qua nguyên nhân. Với từng field đầu vào, cần cung cấp phản hồi rõ ràng cho người dùng.

## 4. DateTimeParseException: lỗi khi chuyển chuỗi sang ngày giờ

`DateTimeParseException` ở `java.time.format` được ném khi việc parse không thể hoàn tất. Hai trường hợp thường gặp:

- **Sai cú pháp**: `"2024/02/29"` không khớp định dạng ISO `uuuu-MM-dd`.
- **Sai ngữ nghĩa ngày**: `"2023-02-29"` trông đúng định dạng nhưng ngày không tồn tại.

`LocalDate.parse(text)` sử dụng `DateTimeFormatter.ISO_LOCAL_DATE`, một formatter với quy tắc resolve **STRICT**.

```java
// Các dòng minh họa độc lập về ý nghĩa; dòng sai sẽ ném exception.
LocalDate.parse("2024-02-29"); // 2024-02-29.
LocalDate.parse("2023-02-29"); // DateTimeParseException.
LocalDate.parse("2024/02/29"); // DateTimeParseException.
```

### 4.1. Phân biệt parse với tạo ngày bằng số

| Đầu vào | Method | Loại lỗi khi thất bại |
| --- | --- | --- |
| `2023, 2, 29` | `LocalDate.of` | `DateTimeException` |
| `"2023-02-29"` | `LocalDate.parse` | `DateTimeParseException` |
| `"2024/02/29"` | `LocalDate.parse` | `DateTimeParseException` |
| `null` | `LocalDate.parse(null)` | `NullPointerException` |
| `2023, 366` | `LocalDate.ofYearDay` | `DateTimeException` |

**Không dựa vào tên method `parse` để cho rằng nó sẽ biến null thành một ngày rỗng.** Với `null`, caller phải xác thực input trước theo contract.

### 4.2. getParsedString và getErrorIndex

`DateTimeParseException` bổ sung các thông tin:

```java
// Chữ ký minh họa.
String getParsedString();
int getErrorIndex();
```

- `getParsedString()` trả lại chuỗi đang được parse.
- `getErrorIndex()` cho biết chỉ số nơi parser ghi nhận lỗi, tính từ `0`.

Ví dụ ký tự `/` đầu tiên trong `"2024/02/29"` nằm ở index `4`. Tuy nhiên khi lỗi xuất phát từ **resolve ngữ nghĩa ngày** (như năm không nhuận), error index không nhất thiết chỉ đúng field “ngày”. Đây là vị trí parser báo lỗi, không phải hệ thống xác định nguyên nhân nghiệp vụ hoàn chỉnh.

Cần lưu ý **quyền riêng tư**: `getParsedString()` chứa nguyên input, có thể là ngày sinh hoặc thông tin cá nhân. Chỉ log dữ liệu phù hợp với chính sách bảo mật. Không dùng `ex.getMessage()` làm chuỗi API contract cố định; message dành cho chẩn đoán và có thể thay đổi theo JDK.

## 5. ResolverStyle: STRICT, SMART và LENIENT

Parse với `DateTimeFormatter` có hai công đoạn chính:

1. **Đọc văn bản** theo pattern/formatter thành các cặp field–value.
2. **Resolve** các field thành ngày/giờ có ý nghĩa theo lịch, có thể xác thực hoặc điều chỉnh.

`ResolverStyle` điều khiển công đoạn thứ **hai**.

| Chế độ | Ý nghĩa | `2023-02-29` với pattern `uuuu-MM-dd` |
| --- | --- | --- |
| `STRICT` | Yêu cầu ngày chính xác và tồn tại | Từ chối |
| `SMART` | Có thể điều chỉnh theo quy tắc thông minh | `2023-02-28` |
| `LENIENT` | Cho phép mang số ngày vượt sang tháng kế tiếp | `2023-03-01` |

Điểm rất dễ bỏ sót:

- `DateTimeFormatter.ofPattern("uuuu-MM-dd")` mặc định dùng **`ResolverStyle.SMART`**.
- `DateTimeFormatter.ISO_LOCAL_DATE` dùng **`ResolverStyle.STRICT`**.
- `LocalDate.parse(text)` mặc định dùng ISO formatter nghiêm ngặt.

Nếu ngày do người dùng nhập **phải tồn tại đúng như đã nhập**, đừng vô tình dùng `ofPattern(...)` mặc định rồi chấp nhận ngày đã được tự sửa.

### 5.1. uuuu và yyyy không phải lúc nào cũng tương đương

Pattern trong `DateTimeFormatter` có các ký tự khác nhau:

- `u`: proleptic year.
- `y`: year-of-era, tức năm trong kỷ nguyên.
- `Y`: week-based-year, năm theo tuần.
- `M`: tháng; `m`: phút.
- `d`: ngày trong tháng; `D`: ngày trong năm.

Khi cần parse một ngày ISO strict không kèm era, `"uuuu-MM-dd"` là lựa chọn rõ ràng. Với `"yyyy-MM-dd"` cùng `ResolverStyle.STRICT`, năm có thể chỉ được đọc thành `YEAR_OF_ERA`; nếu không có era để resolve, một chuỗi ngày tưởng hợp lệ như `"2024-02-29"` vẫn có thể bị từ chối. Ví dụ này đã được kiểm thử với JDK.

**Không tự chọn pattern theo thói quen từ các API formatting khác**, vì `DateTimeFormatter` có semantics riêng cho từng chữ.

### Ví dụ 2 — ResolverStylesDemo.java

Tạo file **ResolverStylesDemo.java**:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;

public class ResolverStylesDemo {
    private static final DateTimeFormatter BASE =
        DateTimeFormatter.ofPattern("uuuu-MM-dd");

    static void strictParse(String raw) {
        try {
            System.out.println("strict=" +
                LocalDate.parse(
                    raw,
                    BASE.withResolverStyle(ResolverStyle.STRICT)
                ));
        } catch (DateTimeParseException e) {
            System.out.println("strict=REJECTED");
        }
    }

    public static void main(String[] args) {
        System.out.println("patternDefault=" +
            BASE.getResolverStyle());

        System.out.println("isoStyle=" +
            DateTimeFormatter.ISO_LOCAL_DATE.getResolverStyle());

        strictParse("2023-02-29");

        System.out.println("smart=" +
            LocalDate.parse(
                "2023-02-29",
                BASE.withResolverStyle(ResolverStyle.SMART)
            ));

        System.out.println("lenient=" +
            LocalDate.parse(
                "2023-02-29",
                BASE.withResolverStyle(ResolverStyle.LENIENT)
            ));

        System.out.println("valid=" +
            LocalDate.parse(
                "2024-02-29",
                BASE.withResolverStyle(ResolverStyle.STRICT)
            ));

        try {
            LocalDate.parse(
                "2024/02/29",
                DateTimeFormatter.ISO_LOCAL_DATE
            );
        } catch (DateTimeParseException ex) {
            System.out.println("syntax=REJECTED");
            System.out.println("index=" + ex.getErrorIndex());
        }
    }
}
```

```bash
javac ResolverStylesDemo.java
java ResolverStylesDemo
```

Stdout:

```text
patternDefault=SMART
isoStyle=STRICT
strict=REJECTED
smart=2023-02-28
lenient=2023-03-01
valid=2024-02-29
syntax=REJECTED
index=4
```

**Diễn giải:** cùng dữ liệu sai `2023-02-29`, STRICT từ chối, SMART sửa thành ngày cuối tháng và LENIENT chuyển sang tháng kế tiếp. Hành vi không tạo lỗi không nhất thiết đồng nghĩa đúng yêu cầu nghiệp vụ. Ngày sinh, ngày pháp lý, hạn thanh toán thường cần **không tự động sửa** dữ liệu nhập ngoài ý muốn.

`DateTimeFormatterBuilder.parseStrict()` là một lựa chọn khác liên quan tới **quy tắc đọc ký tự**; nó không thay thế `withResolverStyle(ResolverStyle.STRICT)` trong bước resolve lịch. Cần phân biệt hai cấp này khi xây formatter tùy biến.

## 6. Thiết kế xác thực dữ liệu từ người dùng

Dữ liệu nhập nên được chia thành các trường hợp có ý nghĩa:

1. **MISSING:** chưa nhập, `null` hoặc chuỗi blank theo contract.
2. **INVALID_DATE:** chuỗi không parse được theo định dạng quy định hoặc không tồn tại trong lịch.
3. **VALID:** ngày có thể tạo thành `LocalDate`.
4. **BUSINESS_INVALID:** ngày hợp lệ theo lịch nhưng không đáp ứng quy tắc ứng dụng, ví dụ ngày kết thúc trước ngày bắt đầu.

Ứng dụng có thể tách riêng `INVALID_FORMAT` và `INVALID_CALENDAR_DATE` nếu cần thông báo cụ thể. Tuy nhiên, không nên cố suy ra chính xác từng trường từ `DateTimeParseException.getErrorIndex()` trong mọi trường hợp.

### 6.1. Vì sao không trả LocalDate.now() khi parse sai?

Mẫu sai:

```java
// KHÔNG NÊN: dữ liệu sai bị biến thành ngày hiện tại.
try {
    return LocalDate.parse(raw);
} catch (DateTimeParseException ex) {
    return LocalDate.now();
}
```

Đây chỉ là đoạn minh họa nằm trong một method có biến `raw`. Nó làm mất dữ liệu gốc, tạo ngày hợp lệ giả, và có thể thay đổi ý nghĩa hóa đơn, ngày đặt chỗ, ngày đến hạn hoặc lịch hẹn.

Thay vào đó, hãy trả một kiểu kết quả với **mã lỗi ổn định**, hoặc ném exception miền nghiệp vụ được giải thích rõ.

### Ví dụ 3 — InputParsingDemo.java

Tạo file **InputParsingDemo.java**:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.Arrays;

public class InputParsingDemo {
    record ParseResult(
        String input,
        LocalDate value,
        String error
    ) {
        String label() {
            return error == null ? value.toString() : error;
        }
    }

    static ParseResult parse(String raw) {
        if (raw == null || raw.isBlank()) {
            return new ParseResult(raw, null, "MISSING");
        }

        try {
            return new ParseResult(
                raw,
                LocalDate.parse(
                    raw,
                    DateTimeFormatter.ISO_LOCAL_DATE
                ),
                null
            );
        } catch (DateTimeParseException ex) {
            return new ParseResult(raw, null, "INVALID_DATE");
        }
    }

    public static void main(String[] args) {
        for (String raw : Arrays.asList(
            null,
            "",
            "2024-02-29",
            "2023-02-29",
            "2024/02/29"
        )) {
            ParseResult result = parse(raw);

            System.out.println(
                "input=" + (raw == null ? "<null>" : raw) +
                " -> " + result.label()
            );
        }
    }
}
```

```bash
javac InputParsingDemo.java
java InputParsingDemo
```

Stdout:

```text
input=<null> -> MISSING
input= -> MISSING
input=2024-02-29 -> 2024-02-29
input=2023-02-29 -> INVALID_DATE
input=2024/02/29 -> INVALID_DATE
```

**Lưu ý phiên bản:** `record` là tính năng chính thức từ Java 16, và `String.isBlank()` có từ Java 11. Code trên dành cho JDK 17+. Trong code base phải biên dịch với Java 8, thay `record` bằng một class bất biến, và thay `isBlank()` bằng điều kiện tương ứng với yêu cầu blank (ví dụ `trim().isEmpty()`, nhưng không hoàn toàn tương đương với `isBlank()` cho mọi khoảng trắng Unicode). `LocalDate.parse` và `DateTimeFormatter.ISO_LOCAL_DATE` vẫn dùng được trong Java 8.

**Thiết kế input:** Ví dụ giữ nguyên `raw` thay vì trim trước parse. Nếu business cho phép khoảng trắng trước/sau, có thể chuẩn hóa có chủ đích rồi parse. Nhưng cần ghi rõ quy tắc đó, không âm thầm chấp nhận format không công bố.

**Bảo mật logging:** Ví dụ in dữ liệu giả an toàn. Với input thật, đặc biệt là ngày sinh và dữ liệu cá nhân, không tự động ghi nguyên chuỗi vào log. Ưu tiên mã lỗi và metadata được phép.

## 7. LocalDateTime hợp lệ chưa chắc hợp lệ trong timezone

`LocalDateTime` lưu **ngày và giờ địa phương** nhưng không chứa `ZoneId` hoặc UTC offset. Các trường `2024-03-31T02:30` hợp lệ về mặt số học, nhưng khi dùng `Europe/Paris`, thời điểm đó có thể nằm trong khoảng **DST gap** và không tồn tại.

### 7.1. Gap và overlap

*Gap* là khoảng giờ địa phương bị nhảy qua khi offset tiến lên. Ví dụ vào ngày 31/03/2024 tại Paris, khoảng `02:30` không tồn tại do chuyển giờ mùa hè.

*Overlap* là khoảng giờ địa phương xảy ra hai lần khi offset lùi lại. Ví dụ `2024-10-27T02:30` tại Paris có thể biểu diễn **hai Instant** khác nhau, một với `+02:00` và một với `+01:00`.

Một `ZonedDateTime` kết hợp local date-time với quy tắc của `ZoneId`. Một số factory/conversion có chính sách giải quyết gap/overlap tự động, không nhất thiết ném exception:

- `local.atZone(zone)` trong gap thường **đẩy thời gian địa phương về sau** theo độ dài gap.
- Trong overlap, nếu không có offset ưu tiên, thường chọn **offset sớm hơn** theo contract.
- `withLaterOffsetAtOverlap()` chọn offset muộn hơn trong overlap khi khả dụng.
- `ZonedDateTime.ofStrict(local, offset, zone)` yêu cầu offset hợp lệ cho local date-time và zone; nếu không hợp lệ, ném `DateTimeException`.

**Chính sách nghiệp vụ:** Với đặt lịch cần độ chính xác tuyệt đối, không được coi việc `atZone` chạy thành công là bằng chứng local time người dùng nhập tồn tại duy nhất.

### 7.2. Kiểm tra ZoneRules.getValidOffsets

`zone.getRules().getValidOffsets(localDateTime)` cho biết các offset hợp lệ cho local time:

| Số offset | Ý nghĩa thường gặp |
| --- | --- |
| `0` | Gap: local time không tồn tại |
| `1` | Thời điểm thông thường |
| `2` | Overlap: local time mơ hồ, hai offset |

Khi ứng dụng cần validation nghiêm ngặt, hãy kiểm tra kết quả này rồi **chọn chính sách**: từ chối gap, chọn một offset trong overlap hoặc hỏi người dùng.

### Ví dụ 4 — ZoneTransitionDemo.java

Tạo file **ZoneTransitionDemo.java**:

```java
import java.time.DateTimeException;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;

public class ZoneTransitionDemo {
    public static void main(String[] args) {
        ZoneId paris = ZoneId.of("Europe/Paris");

        LocalDateTime gap =
            LocalDateTime.of(2024, 3, 31, 2, 30);

        LocalDateTime overlap =
            LocalDateTime.of(2024, 10, 27, 2, 30);

        System.out.println("gapOffsets=" +
            paris.getRules().getValidOffsets(gap).size());

        System.out.println("gapResolved=" +
            gap.atZone(paris));

        try {
            ZonedDateTime.ofStrict(
                gap,
                ZoneOffset.ofHours(1),
                paris
            );
            System.out.println("strictGap=OK");
        } catch (DateTimeException ex) {
            System.out.println("strictGap=REJECTED");
        }

        System.out.println("overlapOffsets=" +
            paris.getRules().getValidOffsets(overlap).size());

        ZonedDateTime early = overlap.atZone(paris);

        System.out.println("overlapEarlier=" + early);
        System.out.println("overlapLater=" +
            early.withLaterOffsetAtOverlap());
    }
}
```

```bash
javac ZoneTransitionDemo.java
java ZoneTransitionDemo
```

Stdout đã kiểm tra với quy tắc timezone lịch sử hiện hành cho năm 2024:

```text
gapOffsets=0
gapResolved=2024-03-31T03:30+02:00[Europe/Paris]
strictGap=REJECTED
overlapOffsets=2
overlapEarlier=2024-10-27T02:30+02:00[Europe/Paris]
overlapLater=2024-10-27T02:30+01:00[Europe/Paris]
```

**Bốn bài học quan trọng:**

1. Gap có `0` valid offsets nhưng `atZone` vẫn có thể **điều chỉnh sang 03:30**, không ném exception. Đây là behavior đã được định nghĩa, không phải chứng cứ cho thấy `02:30` tồn tại.
2. `ofStrict` có thể dùng khi cần từ chối offset không hợp lệ thay vì tự điều chỉnh.
3. Overlap có hai offset nên phải phân định thời điểm mong muốn. Cùng `LocalDateTime` không đồng nghĩa cùng `Instant`.
4. Lịch sử timezone phụ thuộc cơ sở dữ liệu quy tắc TZDB mà JDK cung cấp. Khi kiểm thử, dùng zone và ngày cố định, quản lý phiên bản timezone data phù hợp; không suy ra mọi zone luôn có quy tắc DST giống Paris.

`ZoneId.of("Europe/Paris")` định danh **vùng có quy tắc lịch sử**, khác `ZoneOffset.of("+02:00")` là một offset cố định. Không thay thế vùng địa lý bằng offset cố định nếu lịch hẹn cần tuân thủ DST trong tương lai.

## 8. Phép toán ngày giờ có thể điều chỉnh hợp lệ mà không báo lỗi

Một lỗi tư duy khác là cho rằng nếu phép tính không ném `DateTimeException` thì kết quả chính xác bằng những field gốc cộng số học thông thường.

`LocalDate.plusMonths` và `plusYears` có **quy tắc điều chỉnh ngày trong tháng** để kết quả hợp lệ:

```java
// Mã minh họa.
LocalDate jan31 = LocalDate.of(2024, 1, 31);
LocalDate feb = jan31.plusMonths(1);
// feb = 2024-02-29

LocalDate leap = LocalDate.of(2024, 2, 29);
LocalDate nextYear = leap.plusYears(1);
// nextYear = 2025-02-28
```

`LocalDate.of(2024, 2, 31)` lại ném exception. Điều này không mâu thuẫn:

- `of` cố tạo **đúng ngày được yêu cầu**, nên từ chối ngày không tồn tại.
- `plusMonths` và `plusYears` định nghĩa **cách tính** khi ngày ở tháng/năm đích ngắn hơn: chọn ngày hợp lệ cuối cùng.

**Nếu nghiệp vụ nói “tăng đúng một tháng nhưng phải giữ số ngày trong tháng”, chính sách điều chỉnh này có thể không thỏa mãn.** Cần xác định bằng luật nghiệp vụ chứ không trông chờ exception.

### Ví dụ 5 — DateManipulationDemo.java

Tạo file **DateManipulationDemo.java**:

```java
import java.time.DateTimeException;
import java.time.LocalDate;

public class DateManipulationDemo {
    public static void main(String[] args) {
        LocalDate jan31 = LocalDate.of(2024, 1, 31);

        System.out.println("plusMonth=" +
            jan31.plusMonths(1));

        System.out.println("plusYear=" +
            LocalDate.of(2024, 2, 29).plusYears(1));

        try {
            LocalDate.of(2024, 4, 30)
                .withDayOfMonth(31);
        } catch (DateTimeException ex) {
            System.out.println("invalidDay=REJECTED");
        }

        System.out.println("yearDay=" +
            LocalDate.ofYearDay(2024, 60));

        try {
            LocalDate.ofYearDay(2023, 366);
        } catch (DateTimeException ex) {
            System.out.println("invalidYearDay=REJECTED");
        }
    }
}
```

```bash
javac DateManipulationDemo.java
java DateManipulationDemo
```

Stdout:

```text
plusMonth=2024-02-29
plusYear=2025-02-28
invalidDay=REJECTED
yearDay=2024-02-29
invalidYearDay=REJECTED
```

`withDayOfMonth(31)` trên tháng 4 yêu cầu một ngày không tồn tại nên bị từ chối. Ngày thứ `60` của năm nhuận 2024 là `29/02`; ngày thứ `366` của năm 2023 không tồn tại.

Đối với hóa đơn/lịch đặt định kỳ, hãy viết test rõ quy tắc cuối tháng, chu kỳ năm nhuận, giờ mùa hè và xử lý khi kết quả vượt phạm vi `LocalDate`.

## 9. Bắt đúng exception: DateTimeParseException trước DateTimeException

`DateTimeParseException` là subclass của `DateTimeException`. Nếu cùng một `try` có nhiều catch, phải bắt subclass trước:

```java
// Mã minh họa đặt trong method có String input.
try {
    return LocalDate.parse(input);
} catch (DateTimeParseException ex) {
    // Chuỗi input không parse được.
    throw new IllegalArgumentException("Invalid date", ex);
} catch (DateTimeException ex) {
    // Vấn đề date-time khác, tùy thao tác trong try.
    throw ex;
}
```

Nếu đảo thứ tự để catch `DateTimeException` trước, catch subclass phía sau sẽ trở thành **unreachable** và code không biên dịch.

Trong code nghiệp vụ, chọn phạm vi `try` **nhỏ**; catch ngoại lệ dự kiến và trả lỗi có ý nghĩa, để các lỗi cấu hình hoặc bug không bị coi nhầm là lỗi người dùng.

### Ví dụ 6 — ExceptionHierarchyDemo.java

Tạo file **ExceptionHierarchyDemo.java**:

```java
import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;

public class ExceptionHierarchyDemo {
    static String type(Runnable action) {
        try {
            action.run();
            return "OK";
        } catch (DateTimeParseException e) {
            return "DateTimeParseException";
        } catch (DateTimeException e) {
            return e.getClass().getSimpleName();
        } catch (IllegalArgumentException e) {
            return "IllegalArgumentException";
        } catch (NullPointerException e) {
            return "NullPointerException";
        }
    }

    public static void main(String[] args) {
        System.out.println("parse=" +
            type(() -> LocalDate.parse("oops")));

        System.out.println("construct=" +
            type(() -> LocalDate.of(2023, 2, 29)));

        System.out.println("zone=" +
            type(() -> ZoneId.of("Mars/Phobos")));

        System.out.println("pattern=" +
            type(() ->
                DateTimeFormatter.ofPattern("QQQQQQ")));

        System.out.println("nullInput=" +
            type(() -> LocalDate.parse(null)));
    }
}
```

```bash
javac ExceptionHierarchyDemo.java
java ExceptionHierarchyDemo
```

Stdout:

```text
parse=DateTimeParseException
construct=DateTimeException
zone=ZoneRulesException
pattern=IllegalArgumentException
nullInput=NullPointerException
```

Các ví dụ này chứng minh rằng một method date-time có thể vấp **các loại lỗi khác nhau**. `ZoneRulesException` là một `DateTimeException` về cấu hình/rules của múi giờ; `IllegalArgumentException` trong ví dụ là lỗi pattern từ code; `NullPointerException` phản ánh caller truyền giá trị không hợp lệ theo contract.

**Đừng biến lỗi cấu hình ứng dụng thành “ngày nhập sai”**. Cần dùng error code miền nghiệp vụ cho input, log/giám sát nội bộ cho lỗi chương trình và dữ liệu timezone. Hàm `type` chỉ dành cho demo.

### 9.1. UnsupportedTemporalTypeException

`LocalDate` chỉ chứa ngày, không có giờ. Vì vậy:

```java
// Đoạn minh họa; import java.time.* và java.time.temporal.*.
LocalDate date = LocalDate.of(2024, 1, 1);

date.get(ChronoField.HOUR_OF_DAY);
// UnsupportedTemporalTypeException.
```

Đây là lỗi **dùng sai kiểu dữ liệu/trường dữ liệu**, không phải lỗi parse chuỗi. Nếu cần giờ, hãy dùng `LocalTime`, `LocalDateTime` hoặc kiểu temporal có field phù hợp.

### 9.2. Không chỉ có DateTimeException

`DateTimeFormatter.ofPattern("QQQQQQ")` ném `IllegalArgumentException` vì pattern không hợp lệ. `LocalDate.parse(null)` ném `NullPointerException`. Một số phép tính khi lượng rất lớn có thể ném `ArithmeticException` bên cạnh các lỗi phạm vi ngày giờ. Hãy đọc Javadoc method cụ thể; không áp dụng `catch (DateTimeException)` như một bộ lọc mọi sai sót thời gian.

## 10. Quy tắc chọn kiểu ngày giờ ngay từ đầu

| Ý nghĩa dữ liệu | Kiểu gợi ý | Cạm bẫy |
| --- | --- | --- |
| Một ngày theo lịch | `LocalDate` | Không chứa múi giờ hoặc thời điểm tuyệt đối |
| Một giờ trong ngày | `LocalTime` | Không có thông tin ngày/zone |
| Ngày và giờ địa phương | `LocalDateTime` | Có thể rơi trong DST gap/overlap khi gắn zone |
| Thời điểm trên timeline | `Instant` | Hiển thị cho người dùng cần zone thích hợp |
| Ngày giờ cùng offset | `OffsetDateTime` | Offset không tương đương zone địa lý qua DST |
| Ngày giờ cùng vùng timezone | `ZonedDateTime` | Cần hiểu quy tắc offset, gap/overlap và TZDB |

Đừng lấy một `LocalDateTime` rồi gán một offset tùy ý để gọi đó là “thời điểm UTC”. Phải xác định zone/offset đúng với dữ liệu. Cũng không dùng `ZoneId.systemDefault()` trong test đòi hỏi kết quả tái lập nếu zone cụ thể là phần của bài toán.

Một ngày hợp lệ theo lịch vẫn có thể **không hợp lệ theo nghiệp vụ**: ngày sinh ở tương lai, ngày kết thúc trước ngày bắt đầu, ngày hẹn thuộc khoảng cấm, hoặc ngày thanh toán trước khi mở tài khoản. Kiểm tra business rules **sau** khi parse/validate cú pháp và lịch.

## 11. Cách tổ chức validation đúng tầng

Một thiết kế có thể chia:

1. **Input boundary:** kiểm tra null/blank, format, độ dài, và mã lỗi cho người dùng.
2. **Calendar validation:** dùng `LocalDate.parse`/`LocalDate.of`, formatter và resolver style đúng chính sách.
3. **Timezone validation:** nếu cần `ZonedDateTime`, xác nhận zone, các offset hợp lệ, xử lý gap/overlap.
4. **Business validation:** kiểm tra hạn, quan hệ ngày bắt đầu-kết thúc, ngày được phép...
5. **Persistence/transport:** quyết định biểu diễn `Instant`/ngày địa phương và metadata zone theo contract.

Không nhất thiết phải dùng exception để kiểm tra mọi điều kiện, nhưng **parse ở boundary** với `try/catch DateTimeParseException` là hợp lý khi input đến từ nguồn không tin cậy.

### 11.1. Mã lỗi ổn định

Thay vì trả `ex.getMessage()` nguyên văn, có thể dùng các mã như:

| Mã | Ý nghĩa |
| --- | --- |
| `MISSING_DATE` | Không có giá trị đầu vào |
| `INVALID_FORMAT` | Không khớp format được công bố |
| `INVALID_DATE` | Ngày không tồn tại hoặc parse không thể hoàn tất |
| `INVALID_ZONE` | Zone không được phép hoặc không có rules |
| `NONEXISTENT_LOCAL_TIME` | Giờ địa phương nằm trong DST gap |
| `AMBIGUOUS_LOCAL_TIME` | Giờ địa phương có nhiều offset trong overlap |
| `BUSINESS_RULE_FAILED` | Hợp lệ theo lịch nhưng không đạt điều kiện nghiệp vụ |

Đó là ví dụ các mã ứng dụng **tự thiết kế**, không phải enum có sẵn của `java.time`. Chọn độ chi tiết vừa đủ cho API và tránh để lộ chi tiết hạ tầng không cần thiết cho người dùng.

### 11.2. Clock để test phụ thuộc “hôm nay”

Nếu validation quy định “ngày phải từ hôm nay trở đi”, hãy inject `Clock` hoặc truyền rõ ngày tham chiếu thay vì gọi `LocalDate.now()` ở nhiều chỗ không kiểm soát:

```java
// Đoạn minh họa trong ngữ cảnh có import java.time.*.
Clock clock = Clock.fixed(
    Instant.parse("2024-01-01T00:00:00Z"),
    ZoneId.of("UTC")
);

LocalDate today = LocalDate.now(clock);
// 2024-01-01
```

Sử dụng `Clock` cố định giúp test không phụ thuộc thời gian chạy, timezone CI hoặc thay đổi giờ hệ thống.

## 12. Ma trận kiểm thử quan trọng

| Trường hợp | Input | Kỳ vọng với định dạng ISO strict |
| --- | --- | --- |
| Ngày hợp lệ | `2024-03-15` | Chấp nhận |
| Năm nhuận | `2024-02-29` | Chấp nhận |
| Năm không nhuận | `2023-02-29` | Từ chối |
| Tháng 13 | `2024-13-01` | Từ chối |
| Ngày 31 tháng 4 | `2024-04-31` | Từ chối |
| Ngày bằng 0 | `2024-01-00` | Từ chối |
| Dấu phân cách sai | `2024/02/29` | Từ chối khi chỉ nhận ISO |
| Chuỗi rỗng | `""` | MISSING theo contract |
| Null | `null` | MISSING trước khi parse |
| Khoảng trắng thừa | `" 2024-02-29 "` | Từ chối nếu không cho phép trim |
| Giờ bằng 24 | `24:15` | Từ chối theo `LocalTime.of` |
| Offset +19 giờ | `+19:00` | Từ chối |
| Zone không tồn tại | `Mars/Phobos` | Báo lỗi vùng/rules |
| Gap Paris | `2024-03-31T02:30` | `0` valid offsets |
| Overlap Paris | `2024-10-27T02:30` | `2` valid offsets |
| Tháng tiếp theo từ 31/01 | `2024-01-31 + 1 tháng` | `2024-02-29` |
| Năm tiếp theo từ 29/02 | `2024-02-29 + 1 năm` | `2025-02-28` |

**Bẫy quan trọng:** Test cả trường hợp **không ném exception nhưng tự điều chỉnh**: `SMART` parsing, `plusMonths` và `atZone` trong DST gap. Một pipeline hoàn tất không có exception vẫn có thể mang kết quả không đúng chính sách nghiệp vụ.

### 12.1. Kiểm tra round-trip

Với giá trị hợp lệ và formatter đúng:

```java
// Đoạn minh họa.
LocalDate original = LocalDate.of(2024, 2, 29);
String text = original.format(DateTimeFormatter.ISO_LOCAL_DATE);
LocalDate parsed = LocalDate.parse(
    text,
    DateTimeFormatter.ISO_LOCAL_DATE
);

boolean equal = original.equals(parsed); // true.
```

Round-trip chỉ chứng minh một mẫu hợp lệ có thể được encode/decode. Nó không thay thế các test invalid input, DST, ngày nhuận hoặc business rules.

## 13. Những sai lầm thường gặp

### Sai lầm 1 — chỉ kiểm tra ngày bằng regex

Regex có thể xác nhận hình dạng chuỗi, không đủ để kiểm tra số ngày của tháng và năm nhuận.

**Khắc phục:** dùng `LocalDate.parse` với formatter và resolver style đúng.

### Sai lầm 2 — nghĩ ofPattern mặc định là STRICT

Formatter dựng từ `ofPattern` thường mặc định `SMART` và có thể tự sửa ngày không tồn tại.

**Khắc phục:** `DateTimeFormatter.ISO_LOCAL_DATE` hoặc `withResolverStyle(ResolverStyle.STRICT)` khi input phải đúng chính xác.

### Sai lầm 3 — nhầm yyyy, uuuu, Y hoặc MM, mm

`yyyy` là year-of-era, `uuuu` là proleptic year, `Y` là week-based-year, `MM` là tháng và `mm` là phút.

**Khắc phục:** thiết kế và test pattern với giá trị biên, nhất là đầu/cuối năm.

### Sai lầm 4 — cho rằng parse thành công có nghĩa ngày được giữ nguyên

SMART/LENIENT có thể điều chỉnh ngày được nhập.

**Khắc phục:** chọn resolver style có chủ đích; nếu cần bảo toàn input, dùng STRICT.

### Sai lầm 5 — coi null là lỗi parse

`LocalDate.parse(null)` là lỗi tham số null, không phải `DateTimeParseException`.

**Khắc phục:** xác thực null/blank trước khi gọi parser.

### Sai lầm 6 — bắt DateTimeException rồi biến mọi lỗi thành INVALID_DATE

Điều này có thể che `ZoneRulesException`, `UnsupportedTemporalTypeException` hoặc lỗi hạ tầng.

**Khắc phục:** catch type cụ thể ở boundary, không che bug và configuration error.

### Sai lầm 7 — dùng getErrorIndex như chỉ số field chắc chắn bị sai

Index parser báo không nhất thiết cho biết đầy đủ nguyên nhân lỗi lịch.

**Khắc phục:** dùng thông tin chẩn đoán có kiểm chứng và mã lỗi miền nghiệp vụ.

### Sai lầm 8 — log getParsedString một cách tùy tiện

Nó có thể chứa nguyên chuỗi ngày sinh hoặc dữ liệu cá nhân.

**Khắc phục:** hạn chế log, làm sạch dữ liệu và sử dụng error codes phù hợp.

### Sai lầm 9 — nghĩ LocalDateTime có timezone

Nó không chứa zone/offset; khi gắn zone có thể xuất hiện gap hoặc overlap.

**Khắc phục:** xác định ZoneId và chính sách xử lý thời gian mơ hồ.

### Sai lầm 10 — coi atZone luôn ném lỗi khi gặp DST gap

`atZone` thường điều chỉnh local time forward theo gap.

**Khắc phục:** kiểm tra `ZoneRules.getValidOffsets` hoặc dùng `ZonedDateTime.ofStrict` nếu muốn từ chối.

### Sai lầm 11 — dùng offset cố định như một timezone địa lý

`+02:00` không mô tả toàn bộ quy tắc DST của `Europe/Paris`.

**Khắc phục:** dùng `ZoneId` vùng khi cần lịch địa phương qua thời gian.

### Sai lầm 12 — cho rằng phép cộng ngày sai luôn ném exception

`plusMonths`/`plusYears` có thể tự điều chỉnh về ngày cuối tháng.

**Khắc phục:** đọc contract của method, test cuối tháng/ngày nhuận.

### Sai lầm 13 — fallback tự động về hôm nay

Trả `LocalDate.now()` khi parse lỗi khiến input sai bị biến thành ngày hợp lệ giả.

**Khắc phục:** trả validation error, yêu cầu nhập lại hoặc chỉ dùng fallback nếu nghiệp vụ công bố rõ ràng.

### Sai lầm 14 — lẫn lỗi hệ thống với lỗi người dùng

Thiếu timezone rules hoặc pattern không hợp lệ có thể do cấu hình, không phải do input.

**Khắc phục:** phân loại error boundary và cơ chế giám sát.

### Sai lầm 15 — phụ thuộc system default zone trong test

CI, laptop và server có thể có timezone khác nhau.

**Khắc phục:** cố định `Clock` và `ZoneId` khi tính đúng đắn không nên phụ thuộc môi trường.

## 14. Câu hỏi ôn tập

**Câu 1.** `DateTimeException` có phải checked exception không?

**Đáp án:** Không. Nó là `RuntimeException`.

**Câu 2.** `LocalDate.of(2023, 2, 29)` ném gì?

**Đáp án:** `DateTimeException` vì 2023 không nhuận.

**Câu 3.** `LocalDate.parse("2023-02-29")` ném gì?

**Đáp án:** `DateTimeParseException` theo formatter ISO strict.

**Câu 4.** Vì sao `LocalDate.parse(null)` không được xử lý chỉ bằng catch `DateTimeParseException`?

**Đáp án:** Nó ném `NullPointerException` khi input null, phải kiểm tra ở boundary.

**Câu 5.** `DateTimeFormatter.ofPattern("uuuu-MM-dd")` mặc định dùng style gì?

**Đáp án:** `SMART`.

**Câu 6.** `2023-02-29` được resolve thế nào với SMART?

**Đáp án:** `2023-02-28`.

**Câu 7.** Cùng input với LENIENT?

**Đáp án:** `2023-03-01`.

**Câu 8.** Khi phải từ chối mọi ngày không tồn tại thay vì sửa ngầm, chọn style gì?

**Đáp án:** `STRICT`.

**Câu 9.** Tại sao `yyyy` và `uuuu` có thể cho kết quả khác khi parse strict?

**Đáp án:** `yyyy` là year-of-era, `uuuu` là proleptic year; thiếu era có thể không resolve được năm-of-era.

**Câu 10.** `LocalDateTime` hợp lệ có bảo đảm local time tồn tại trong một zone không?

**Đáp án:** Không. DST gap/overlap cần được kiểm tra khi gắn zone.

**Câu 11.** `getValidOffsets(local)` trả `0` phần tử nghĩa là gì?

**Đáp án:** Local time nằm trong gap; không có offset hợp lệ cho zone đó.

**Câu 12.** Một overlap thông thường có mấy offset hợp lệ?

**Đáp án:** Hai; phải quyết định chọn offset nào.

**Câu 13.** Vì sao `LocalDate.of(2024,1,31).plusMonths(1)` không ném lỗi?

**Đáp án:** `plusMonths` điều chỉnh về ngày cuối tháng đích, thành `2024-02-29`.

**Câu 14.** Có nên bắt `DateTimeException` rồi trả “ngày nhập sai” cho mọi trường hợp không?

**Đáp án:** Không. Cần phân biệt parse input, cấu hình timezone, field unsupported và lỗi code.

## 15. Tài liệu Java chính thức hiện hành

- [Oracle Java SE 25 — DateTimeException](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/DateTimeException.html): exception cơ sở khi tạo, truy vấn hoặc thao tác date-time.
- [Oracle Java SE 25 — DateTimeParseException](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/DateTimeParseException.html): `getParsedString()`, `getErrorIndex()`, kế thừa `DateTimeException`.
- [Oracle Java SE 25 — LocalDate](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/LocalDate.html): validation và quy tắc `plusMonths`/`plusYears`.
- [Oracle Java SE 25 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/DateTimeFormatter.html): pattern, parse/resolve và formatter ISO.
- [Oracle Java SE 25 — ResolverStyle](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/ResolverStyle.html): `STRICT`/`SMART`/`LENIENT`.
- [Oracle Java SE 25 — ZonedDateTime](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/ZonedDateTime.html): gap, overlap và `ofStrict`.
- [Oracle Java SE 25 — ZoneRules](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/zone/ZoneRules.html): kiểm tra valid offsets.

**Kết luận:** `DateTimeException` cho biết một thao tác ngày giờ không hợp lệ, còn `DateTimeParseException` chuyên cho lỗi parse. Hãy phân biệt **sai format**, **sai ngày lịch**, **thiếu dữ liệu**, **sai timezone** và **quy tắc nghiệp vụ**. Khi độ chính xác quan trọng, dùng formatter với `STRICT`, chủ động phát hiện DST gap/overlap, bắt exception đúng tầng, và nhớ rằng nhiều API hợp lệ vẫn **điều chỉnh giá trị mà không ném lỗi**.