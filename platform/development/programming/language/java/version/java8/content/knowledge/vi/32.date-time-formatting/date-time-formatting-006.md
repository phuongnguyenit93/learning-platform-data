# ResolverStyle.STRICT, SMART và LENIENT trong định dạng ngày giờ Java

## 1. Mục tiêu học tập

Khi đọc ngày giờ dạng text trong Java, việc chuỗi **đúng khuôn dạng** chưa có nghĩa nó biểu diễn **ngày giờ hợp lệ**. Ví dụ, `2023-02-29` có đúng cấu trúc `năm-tháng-ngày` nhưng năm 2023 không nhuận. `2024-02-30` cũng có cấu trúc hợp lệ, song tháng 2/2024 chỉ có 29 ngày.

Từ Java 8, `java.time.format.ResolverStyle` cho phép chọn **chính sách chuyển các trường đã đọc thành ngày giờ có ý nghĩa**:

- **`ResolverStyle.STRICT`:** đối chiếu chính xác giới hạn và sự nhất quán của các trường; từ chối ngày giờ không hợp lệ.
- **`ResolverStyle.SMART`:** áp dụng một số điều chỉnh hợp lý theo từng trường và hệ lịch; với ISO date, có thể đưa ngày vượt cuối tháng nhưng vẫn trong 1–31 về **ngày cuối tháng**.
- **`ResolverStyle.LENIENT`:** chuẩn hóa phần dư bằng phép toán lịch; tháng 13 hay ngày 40 có thể chuyển thành một ngày khác thay vì bị từ chối.

**Quy tắc chính:** đây là ba **cách giải quyết trường ngày giờ đã được parse**, không phải ba mức “cho phép mọi chuỗi đầu vào”. `LENIENT` không có nghĩa parser bỏ qua mọi dấu phân cách hay tự đoán mọi định dạng. `SMART` không phải validation nghiêm ngặt: nó có thể **thay đổi ngày** mà người dùng nhập.

Bài tập trung vào `DateTimeFormatter`, `DateTimeFormatterBuilder`, `LocalDate` và `LocalDateTime` của Java hiện hành. Các API này đều còn hiệu lực trong Java 17+ và các JDK mới; chúng là kiến thức của Java 8, không dựa vào thư viện ngày giờ legacy.

Sau bài bạn sẽ có khả năng:

1. Phân biệt hai giai đoạn parsing và **resolver style**.
2. Chọn policy cho biểu mẫu, dữ liệu nhập hàng loạt và format nội bộ.
3. Dự đoán kết quả cụ thể của ngày sai, overflow tháng/ngày và `24:00`.
4. Tránh lỗi `yyyy` so với `uuuu` khi dùng STRICT.
5. Hiểu vì sao ISO formatter định nghĩa sẵn có thể STRICT nhưng pattern formatter mặc định SMART.
6. Phân biệt `DateTimeFormatterBuilder.parseLenient()` với `ResolverStyle.LENIENT`.
7. Kiểm tra nhiều tập trường ngày bị mâu thuẫn, tìm hiểu `withResolverFields(...)`.
8. Biết phạm vi resolver style: **không thay thế validation múi giờ/DST**.
9. Viết các ví dụ Java chạy được và unit test xác định.

## 2. Parsing gồm **hai giai đoạn**

Theo tài liệu `DateTimeFormatter` của Oracle, quá trình phân tích chuỗi ngày giờ gồm hai bước:

**Giai đoạn 1 — Đọc văn bản (lexical parse):**

- Áp dụng format/pattern đã định nghĩa để nhận diện dấu `-`, `/`, chữ, số, phần optional, zone/offset nếu có.
- Tạo tập giá trị trường, ví dụ `YEAR=2023`, `MONTH_OF_YEAR=2`, `DAY_OF_MONTH=29`.
- Có thể nhận diện đầy đủ cấu trúc chuỗi dù tổ hợp trường chưa biểu diễn được `LocalDate` thực sự.

**Giai đoạn 2 — Giải quyết các trường (resolution):**

- Kiểm tra và kết hợp các trường thành một ngày, giờ hoặc datetime.
- Áp dụng chính sách `ResolverStyle.STRICT`, `SMART` hoặc `LENIENT`.
- Khi có nhiều tổ hợp trường có thể đại diện cùng một ngày, kiểm tra sự nhất quán theo các quy tắc resolution.

Sơ đồ:

```text
"2023-02-29"
      |
      v
[Pattern: uuuu-MM-dd]      Giai đoạn 1: đọc chữ số / dấu '-'
      |
      v
{YEAR=2023, MONTH=2, DAY=29}
      |
      v
[ResolverStyle]            Giai đoạn 2: xác minh/chuẩn hóa
      |
      +--> STRICT  : lỗi (năm 2023 không nhuận)
      |
      +--> SMART   : LocalDate 2023-02-28
      |
      +--> LENIENT : LocalDate 2023-03-01
```

Với input `2023/02/29`, formatter pattern `uuuu-MM-dd` yêu cầu dấu `-`: chuỗi thất bại **ngay giai đoạn 1** trong các điều kiện parse chữ thông thường, bất kể resolver style. Không được nói rằng “LENIENT thì dấu phân cách nào cũng chấp nhận”.

`DateTimeFormatter.parseUnresolved(text, ParsePosition)` có thể lấy dữ liệu chỉ sau giai đoạn 1 nhưng là API mức thấp, không nên dùng thay cho `LocalDate.parse` trong validation thông thường.

## 3. So sánh ba phong cách ở cấp hợp đồng

| Đặc điểm | `STRICT` | `SMART` | `LENIENT` |
| --- | --- | --- | --- |
| Ngày có trong tháng? | Phải chính xác | Với ISO, day 1–31 vượt cuối tháng có thể được **clamp** về cuối tháng | Có thể **cộng/trừ ngày dư** sang tháng khác |
| Tháng ngoài `1..12` (ISO) | Từ chối | Từ chối | Có thể chuẩn hóa tháng 0/13/... |
| `2023-02-29` | Từ chối | `2023-02-28` | `2023-03-01` |
| `2024-02-30` | Từ chối | `2024-02-29` | `2024-03-01` |
| `2024-13-40` | Từ chối | Từ chối | `2025-02-09` |
| `24:00` theo `HH:mm` | Từ chối | Trường hợp đặc biệt có thể chuyển thành `00:00` + 1 ngày | Chuẩn hóa thành `00:00` + 1 ngày |
| `25:61` theo `HH:mm` | Từ chối | Từ chối | Chuẩn hóa phần dư giờ/phút |
| Mục đích thường gặp | Kiểm tra input chặt chẽ | UX linh hoạt **khi điều chỉnh được chấp nhận** | Nhập dữ liệu có quy tắc normalize rõ ràng |

Đây là **các ví dụ cụ thể cho ISO chronology và trường tương ứng**, không có lời hứa rằng mọi lịch/field đều xử lý hệt nhau. Javadoc quy định SMART là chính sách thông minh **theo từng trường**, có thể tương đương STRICT, LENIENT hoặc một hành vi thứ ba. Đừng mô tả SMART chung chung là “LENIENT nhẹ”.

**Mặc định không đồng nghĩa an toàn:** `DateTimeFormatter.ofPattern("uuuu-MM-dd")` mặc định có `ResolverStyle.SMART`. Nếu nghiệp vụ yêu cầu ngày người dùng nhập phải tồn tại đúng như vậy, hãy **cài `withResolverStyle(STRICT)` một cách tường minh**.

## 4. Ví dụ hoàn chỉnh: cùng chuỗi, ba kết quả khác nhau

Lưu `ResolverStylesDatesDemo.java`:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.List;

public class ResolverStylesDatesDemo {
    private static String resolve(String text,
                                  ResolverStyle style) {
        DateTimeFormatter formatter = DateTimeFormatter
                .ofPattern("uuuu-MM-dd")
                .withResolverStyle(style);
        try {
            return LocalDate.parse(text, formatter).toString();
        } catch (DateTimeParseException ex) {
            return "INVALID";
        }
    }

    public static void main(String[] args) {
        List<String> inputs = List.of(
                "2023-02-29", "2024-02-30", "2024-13-40");

        for (String input : inputs) {
            System.out.println(input
                    + " | STRICT=" +
                    resolve(input, ResolverStyle.STRICT)
                    + " | SMART=" +
                    resolve(input, ResolverStyle.SMART)
                    + " | LENIENT=" +
                    resolve(input, ResolverStyle.LENIENT));
        }
    }
}
```

Biên dịch và chạy:

```bash
javac ResolverStylesDatesDemo.java
java ResolverStylesDatesDemo
```

Stdout:

```text
2023-02-29 | STRICT=INVALID | SMART=2023-02-28 | LENIENT=2023-03-01
2024-02-30 | STRICT=INVALID | SMART=2024-02-29 | LENIENT=2024-03-01
2024-13-40 | STRICT=INVALID | SMART=INVALID | LENIENT=2025-02-09
```

Dòng thứ nhất thể hiện rõ nhất:

- **STRICT** không chấp nhận ngày không tồn tại.
- **SMART** trong ISO giữ ý định “tháng 2/2023” nhưng giới hạn ngày về 28/02.
- **LENIENT** bắt đầu từ đầu tháng rồi cộng phần dư: ngày 29/02/2023 trở thành 01/03.

Dòng thứ ba cho thấy LENIENT có thể biến input sai hẳn tháng/ngày thành một ngày hợp lệ trong **năm khác**. Nếu đang parse ngày sinh, ngày đến hạn, ngày giao dịch hoặc giấy tờ pháp lý, việc tự chuẩn hóa như vậy có thể tạo **dữ liệu sai nghiệp vụ** dù code không ném exception.

### 4.1. Khi nào lỗi được ném?

`LocalDate.parse(text, formatter)` sẽ ném `DateTimeParseException` nếu chuỗi không hợp lệ hoặc không thể resolve thành ngày. Ngoại lệ có thể mang vị trí lỗi, chuỗi đã parse và nguyên nhân cụ thể. Trong hệ thống production, phản hồi lỗi nên nói rõ input có vấn đề, không dựa vào nguyên văn mọi message exception (nội dung thông báo có thể thay đổi theo implementation).

Với dữ liệu người dùng, hãy bắt **`DateTimeParseException` có chủ đích**, thay vì bắt `RuntimeException` rồi im lặng thay bằng ngày mặc định. `LENIENT` không phải cơ chế cứu mọi input: nó có thể tạo ngày khác mà không báo người dùng biết.

## 5. STRICT: xác thực ngày lịch, năm nhuận và giới hạn thực tế

`ResolverStyle.STRICT` yêu cầu ngày, tháng và năm tạo thành một tổ hợp hợp lệ trong hệ lịch được chọn. Với ISO chronology:

- Năm nhuận chia hết cho 4, trừ trường hợp năm thế kỷ không chia hết cho 400; 2024 nhuận, 2023 không nhuận.
- Tháng 2 có 28 hoặc 29 ngày; tháng 4 có 30; tháng 1 có 31.
- Ngày 0, ngày 32 hoặc tháng 13 không phải ngày ISO hợp lệ và bị từ chối.
- `2024-02-29` hợp lệ; `2024-02-30` không hợp lệ.

Lưu `StrictCalendarDemo.java`:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.List;

public class StrictCalendarDemo {
    public static void main(String[] args) {
        DateTimeFormatter strict = DateTimeFormatter
                .ofPattern("uuuu-MM-dd")
                .withResolverStyle(ResolverStyle.STRICT);

        for (String text : List.of(
                "2024-02-29",
                "2023-02-29",
                "2024-02-30",
                "2023-04-31",
                "2024-02-00")) {
            try {
                LocalDate result = LocalDate.parse(text, strict);
                System.out.println(text + " -> " + result);
            } catch (DateTimeParseException ex) {
                System.out.println(text + " -> rejected");
            }
        }
    }
}
```

```bash
javac StrictCalendarDemo.java
java StrictCalendarDemo
```

```text
2024-02-29 -> 2024-02-29
2023-02-29 -> rejected
2024-02-30 -> rejected
2023-04-31 -> rejected
2024-02-00 -> rejected
```

**Cách dùng nên ưu tiên:** parse dữ liệu mà ngày người nhập phải **đúng từng chữ số** (ví dụ ngày trên chứng từ, ngày hết hạn hộ chiếu, khóa giao dịch theo ngày) bằng STRICT, kết hợp các quy tắc nghiệp vụ khác như ngày không vượt hôm nay, giới hạn tuổi hoặc khoảng thời gian cho phép. STRICT chỉ giải quyết **tính hợp lệ lịch**; nó không tự xác minh ngày đó có được phép theo nghiệp vụ.

`LocalDate.of(2023, 2, 29)` cũng ném `DateTimeException` vì tạo đối tượng ngày trực tiếp bằng factory vốn đòi hỏi hợp lệ; `ResolverStyle` chỉ áp dụng khi đi qua formatter parse, không tự thay đổi cách hoạt động của `LocalDate.of`.

## 6. SMART: điều chỉnh *ngày cuối tháng* có chủ đích

`ResolverStyle.SMART` không đơn giản là bỏ qua lỗi. Trong ISO chronology, nếu day-of-month từ `1` đến `31` nhưng vượt số ngày thật của tháng, formatter có thể đặt thành **ngày cuối tháng**.

Ví dụ:

- `2023-02-29` → `2023-02-28`.
- `2024-02-30` → `2024-02-29`.
- `2023-04-31` → `2023-04-30`.
- `2023-04-32` → lỗi vì ngày 32 ngoài phạm vi cho trường day-of-month.
- `2024-13-01` → lỗi vì tháng 13 không phù hợp với SMART.

Lưu `SmartCalendarDemo.java`:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.List;

public class SmartCalendarDemo {
    public static void main(String[] args) {
        DateTimeFormatter smart = DateTimeFormatter
                .ofPattern("uuuu-MM-dd")
                .withResolverStyle(ResolverStyle.SMART);

        for (String input : List.of(
                "2023-02-29",
                "2024-02-30",
                "2023-04-31",
                "2023-04-32",
                "2024-13-01")) {
            try {
                System.out.println(input + " -> " +
                        LocalDate.parse(input, smart));
            } catch (DateTimeParseException e) {
                System.out.println(input + " -> rejected");
            }
        }
    }
}
```

```bash
javac SmartCalendarDemo.java
java SmartCalendarDemo
```

```text
2023-02-29 -> 2023-02-28
2024-02-30 -> 2024-02-29
2023-04-31 -> 2023-04-30
2023-04-32 -> rejected
2024-13-01 -> rejected
```

**Câu hỏi nghiệp vụ:** nếu user yêu cầu thanh toán vào `31/04`, có được phép tự chuyển thành `30/04` không? Nếu nghiệp vụ không nêu rõ, **không** nên mặc định SMART. Với lịch lặp lại như “ngày cuối cùng của mỗi tháng”, tốt hơn lưu ý định *last day of month* rồi dùng `TemporalAdjusters.lastDayOfMonth()` khi tạo ngày, thay vì chờ SMART ngầm “sửa” một ngày giả.

### 6.1. SMART không sửa mọi trường

SMART áp dụng logic theo từng field. Đối với nhiều trường, hành vi có thể như STRICT; ví dụ tháng 13 vẫn bị từ chối trong ISO date. Với giờ, có trường hợp đặc biệt `24:00` được biểu diễn như kết thúc ngày, nhưng không có nghĩa `25:61` cũng hợp lệ. Học API cụ thể thay vì suy ra “SMART luôn clamp mọi giá trị về max”.

## 7. LENIENT: normalize overflow bằng phép toán lịch

`ResolverStyle.LENIENT` có thể diễn giải một tổ hợp field ngoài phạm vi thành **một ngày khác hợp lệ**. Đối với ISO year–month–day, có thể hiểu bằng cách lấy ngày đầu tháng/năm phù hợp rồi cộng số tháng/ngày dư.

Ví dụ:

- `2024-02-30` → 01/03/2024 vì năm 2024 có 29 ngày tháng 2.
- `2023-02-29` → 01/03/2023 vì tháng 2/2023 có 28 ngày.
- `2024-13-40` → 09/02/2025.
- `2024-00-00` → 30/11/2023: tháng 0 và ngày 0 được chuẩn hóa lùi về trước.

Lưu `LenientNormalizationDemo.java`:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.List;

public class LenientNormalizationDemo {
    public static void main(String[] args) {
        DateTimeFormatter lenient = DateTimeFormatter
                .ofPattern("uuuu-MM-dd")
                .withResolverStyle(ResolverStyle.LENIENT);

        for (String text : List.of(
                "2023-02-29",
                "2024-02-30",
                "2024-13-40",
                "2024-00-00")) {
            LocalDate result = LocalDate.parse(text, lenient);
            System.out.println(text + " -> " + result);
        }
    }
}
```

```bash
javac LenientNormalizationDemo.java
java LenientNormalizationDemo
```

```text
2023-02-29 -> 2023-03-01
2024-02-30 -> 2024-03-01
2024-13-40 -> 2025-02-09
2024-00-00 -> 2023-11-30
```

**LENIENT không tự đoán ý định.** `2024-13-40` trở thành một ngày thật theo phép tính, nhưng điều đó không chứng minh người dùng *muốn* ngày 09/02/2025. Sử dụng LENIENT chỉ khi nguồn dữ liệu cố ý dùng phép tràn số như một phần của quy ước (ví dụ dữ liệu trung gian khi cộng trừ trường ngày), và cần ghi rõ kết quả đã được normalize.

Nếu chuyển dữ liệu lịch sử sang format mới, hãy tách **kiểm tra tính chính xác gốc** và **chuẩn hóa theo quy tắc đã được phê duyệt**. Một pipeline import nguy hiểm là áp dụng LENIENT toàn bộ rồi vứt bỏ raw input; nếu xuất hiện một ngày lạ, sẽ không còn dấu vết để điều tra.

## 8. `24:00` là tình huống đặc biệt của SMART

Đối với giờ trong ngày, `24:00` đôi khi được dùng để chỉ **kết thúc một ngày**, tức `00:00` **ngày hôm sau**. `ResolverStyle.SMART` có xử lý trường hợp `24:00` khi phút/giây phần còn lại bằng 0; `STRICT` không chấp nhận `HOUR_OF_DAY=24`. LENIENT có thể xử lý thêm số giờ/phút tràn.

Lưu `TimeResolverDemo.java`:

```java
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.List;

public class TimeResolverDemo {
    private static String parse(String value,
                                ResolverStyle style) {
        DateTimeFormatter f = DateTimeFormatter
                .ofPattern("uuuu-MM-dd HH:mm")
                .withResolverStyle(style);
        try {
            return LocalDateTime.parse(value, f).toString();
        } catch (DateTimeParseException ex) {
            return "INVALID";
        }
    }

    public static void main(String[] args) {
        for (String value : List.of(
                "2024-03-31 24:00",
                "2024-03-31 25:61")) {
            for (ResolverStyle style : ResolverStyle.values()) {
                System.out.println(style + " " + value
                        + " -> " + parse(value, style));
            }
        }
    }
}
```

```bash
javac TimeResolverDemo.java
java TimeResolverDemo
```

```text
STRICT 2024-03-31 24:00 -> INVALID
SMART 2024-03-31 24:00 -> 2024-04-01T00:00
LENIENT 2024-03-31 24:00 -> 2024-04-01T00:00
STRICT 2024-03-31 25:61 -> INVALID
SMART 2024-03-31 25:61 -> INVALID
LENIENT 2024-03-31 25:61 -> 2024-04-01T02:01
```

Hai bài học:

1. Có **ngày đi kèm** thì phần giờ dư được cộng sang ngày. Vì vậy SMART với `24:00` thực sự đã chuyển ngày, không chỉ sửa chữ số giờ.
2. Không đem cách parse `24:00` làm lý do chấp nhận mọi giờ ngoài phạm vi. `25:61` chỉ được LENIENT chuẩn hóa trong ví dụ này.

**Không nhầm với DST:** ví dụ trên parse **LocalDateTime không có zone**. `2024-03-31` có trùng ngày DST ở Paris nhưng `ResolverStyle` không biết Paris; nó chỉ tính field ngày giờ theo ISO chronology. DST được xử lý bằng `ZoneId` và `ZoneRules` sau khi có ngữ cảnh vùng (xem mục 15).

## 9. `parsedExcessDays()`: giờ tràn nhưng không có ngày

Nếu formatter chỉ parse giờ và không có ngày, SMART `24:00` hoặc LENIENT `49:30` có thể tạo:

- Một `LocalTime` đã normalize trong khoảng `00:00..23:59...`.
- Một giá trị `Period` “ngày dư” truy vấn bằng `DateTimeFormatter.parsedExcessDays()`.

Khi bạn gọi duy nhất `LocalTime.parse(...)`, **thông tin ngày dư không nằm trong LocalTime**. Với pipeline cần phát hiện người nhập “kết thúc ngày kế tiếp”, phải truy vấn temporal parse result thay vì chỉ giữ LocalTime.

Lưu `ExcessDaysDemo.java`:

```java
import java.time.LocalTime;
import java.time.Period;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.time.temporal.TemporalAccessor;

public class ExcessDaysDemo {
    private static void show(String value,
                             ResolverStyle style) {
        DateTimeFormatter f = DateTimeFormatter
                .ofPattern("HH:mm")
                .withResolverStyle(style);

        TemporalAccessor parsed = f.parse(value);
        LocalTime time = LocalTime.from(parsed);
        Period excess = parsed.query(
                DateTimeFormatter.parsedExcessDays());

        System.out.println(style + " " + value +
                " -> " + time + " + " + excess);
    }

    public static void main(String[] args) {
        show("24:00", ResolverStyle.SMART);
        show("49:30", ResolverStyle.LENIENT);
    }
}
```

```bash
javac ExcessDaysDemo.java
java ExcessDaysDemo
```

```text
SMART 24:00 -> 00:00 + P1D
LENIENT 49:30 -> 01:30 + P2D
```

Ý nghĩa: `24:00` là `00:00` **cộng một ngày**, còn `49:30` là `01:30` **cộng hai ngày**. Khi chuỗi đã có **ngày hoàn chỉnh**, ngày dư được cộng vào date part; `parsedExcessDays` thường trở về 0 sau khi date-time đã được giải quyết, vì phần dư đã phản ánh trong ngày kết quả.

**Bài toán thực tế:** trong lịch trực đêm, nếu hệ thống cho phép nhập `24:00` như “cuối ngày”, cần biểu diễn nghiệp vụ bằng **LocalDateTime** hoặc bằng **LocalTime + day offset**, không chỉ `LocalTime.MIN`. Nếu chỉ lưu `00:00`, hai ý định “đầu ngày” và “cuối ngày trước” có thể bị trộn lẫn.

## 10. Bẫy quan trọng của STRICT: `yyyy` khác `uuuu`

Trong `DateTimeFormatter` pattern:

- `u`/`uuuu`: **proleptic year** (`ChronoField.YEAR`); phù hợp khi muốn parse ISO date bằng STRICT mà không có trường kỷ nguyên.
- `y`/`yyyy`: **year-of-era** (`ChronoField.YEAR_OF_ERA`), cần một giá trị **ERA** để xác định năm proleptic trong STRICT.
- `G`: ký hiệu **era**, ví dụ `AD` hoặc `BC` theo locale/hệ lịch.

Rất nhiều người thử:

```java
DateTimeFormatter wrong = DateTimeFormatter
        .ofPattern("yyyy-MM-dd")
        .withResolverStyle(ResolverStyle.STRICT);
LocalDate.parse("2024-02-29", wrong);
```

*Đây là snippet thể hiện bẫy, sẽ ném `DateTimeParseException` khi resolve sang LocalDate dù năm 2024 nhuận và ngày hợp lệ.*

Nguyên nhân không phải ngày 29/02 bị từ chối vì sai lịch. Formatter đọc được `YEAR_OF_ERA=2024` nhưng thiếu `ERA`; dưới STRICT, không thể tự biến nó thành `LocalDate` đầy đủ. SMART có thể giả định era hiện hành phù hợp trong ISO chronology ở trường hợp thông thường, vì thế cùng pattern đôi khi “chạy được” trong SMART và bất ngờ thất bại khi bật STRICT.

Lưu `YearPatternStrictDemo.java`:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.time.temporal.ChronoField;
import java.util.Locale;

public class YearPatternStrictDemo {
    public static void main(String[] args) {
        DateTimeFormatter yearOfEra = DateTimeFormatter
                .ofPattern("yyyy-MM-dd")
                .withResolverStyle(ResolverStyle.STRICT);
        DateTimeFormatter proleptic = DateTimeFormatter
                .ofPattern("uuuu-MM-dd")
                .withResolverStyle(ResolverStyle.STRICT);
        DateTimeFormatter explicitEra = DateTimeFormatter
                .ofPattern("G yyyy-MM-dd", Locale.ENGLISH)
                .withResolverStyle(ResolverStyle.STRICT);

        DateTimeFormatter defaultEra =
                new DateTimeFormatterBuilder()
                .appendPattern("yyyy-MM-dd")
                .parseDefaulting(ChronoField.ERA, 1)
                .toFormatter(Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);

        try {
            System.out.println("yyyy = " +
                    LocalDate.parse("2024-02-29", yearOfEra));
        } catch (DateTimeParseException e) {
            System.out.println("yyyy = unresolved era");
        }

        System.out.println("uuuu = " +
                LocalDate.parse("2024-02-29", proleptic));
        System.out.println("G yyyy = " +
                LocalDate.parse("AD 2024-02-29", explicitEra));
        System.out.println("defaultEra = " +
                LocalDate.parse("2024-02-29", defaultEra));
    }
}
```

```bash
javac YearPatternStrictDemo.java
java YearPatternStrictDemo
```

```text
yyyy = unresolved era
uuuu = 2024-02-29
G yyyy = 2024-02-29
defaultEra = 2024-02-29
```

**Lựa chọn nên dùng cho ISO date nhập phổ biến:** `uuuu-MM-dd` kết hợp `ResolverStyle.STRICT`. Khi thật sự quản lý hệ kỷ nguyên, dùng `G` và `yyyy` hoặc thêm ERA mặc định **nếu hợp đồng dữ liệu thực sự bảo đảm era đó**. Đừng “chữa” lỗi `yyyy` bằng việc đổi sang SMART nếu nghiệp vụ cần STRICT; như vậy sẽ mở thêm khả năng tự điều chỉnh ngày.

### 10.1. `YYYY` không phải `yyyy`

`Y`/`YYYY` là **week-based year** theo cách tính tuần, **không phải năm lịch thông thường**. `YYYY-MM-dd` là một tổ hợp trường không phù hợp cho biểu diễn ISO calendar date tiêu chuẩn; thứ tự tuần có thể lệch quanh cuối/năm đầu và phụ thuộc locale. Khi muốn ngày `2024-12-31` dùng `uuuu-MM-dd` (hoặc `yyyy-MM-dd` với xử lý era rõ ràng) thay vì `YYYY-MM-dd`.

Đây là lỗi độc lập với việc chọn STRICT/SMART/LENIENT; resolver style không thể biến một pattern dùng sai trường thành một hợp đồng dữ liệu đúng.

## 11. Mặc định của formatter: `ISO_LOCAL_DATE` khác `ofPattern`

Một nguồn sai sót là cho rằng **mọi** `DateTimeFormatter` mặc định SMART hoặc STRICT giống nhau.

- `DateTimeFormatter.ofPattern("uuuu-MM-dd")` mặc định **SMART**.
- `DateTimeFormatter.ISO_LOCAL_DATE` là formatter ISO ngày có resolver **STRICT**.
- `DateTimeFormatter.ISO_DATE` và các formatter ISO định nghĩa sẵn khác có hợp đồng riêng; cần kiểm tra đúng API thay vì suy từ một constant bất kỳ.
- `DateTimeFormatterBuilder.toFormatter()` thông thường tạo formatter với resolver style SMART nếu chưa đổi, nhưng builder còn có cấu hình parsing riêng ở giai đoạn 1.
- `formatter.withResolverStyle(ResolverStyle.STRICT)` trả một **formatter mới**. Formatter cũ không bị sửa.

Lưu `FormatterDefaultsDemo.java`:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;

public class FormatterDefaultsDemo {
    public static void main(String[] args) {
        DateTimeFormatter pattern =
                DateTimeFormatter.ofPattern("uuuu-MM-dd");
        DateTimeFormatter strict =
                pattern.withResolverStyle(ResolverStyle.STRICT);
        DateTimeFormatter iso =
                DateTimeFormatter.ISO_LOCAL_DATE;

        System.out.println("patternStyle = " +
                pattern.getResolverStyle());
        System.out.println("strictStyle = " +
                strict.getResolverStyle());
        System.out.println("isoStyle = " +
                iso.getResolverStyle());
        System.out.println("patternResult = " +
                LocalDate.parse("2023-02-29", pattern));

        try {
            LocalDate.parse("2023-02-29", iso);
        } catch (DateTimeParseException ex) {
            System.out.println("iso rejected invalid date");
        }

        System.out.println("unchanged = " +
                (pattern.getResolverStyle() == ResolverStyle.SMART));
    }
}
```

```bash
javac FormatterDefaultsDemo.java
java FormatterDefaultsDemo
```

```text
patternStyle = SMART
strictStyle = STRICT
isoStyle = STRICT
patternResult = 2023-02-28
iso rejected invalid date
unchanged = true
```

**Thực hành tốt:** tạo formatter dùng lại như một hằng số:

```java
private static final DateTimeFormatter INPUT_DATE =
        DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);
```

*Đây là snippet khai báo field trong class cần import `DateTimeFormatter`, `Locale` và `ResolverStyle`. Các formatter `java.time` là immutable và thread-safe, có thể chia sẻ khi đã cấu hình xong.*

Không lẫn giữa **default parser behavior** và **default vùng/hệ lịch/locale**. Nếu cần parse chữ tháng hoặc ký hiệu era, cấu hình `Locale` tường minh; nếu cần ngày ISO, chọn chronology, pattern và resolver style phù hợp hợp đồng.

## 12. `parseLenient()` của builder **không phải** `ResolverStyle.LENIENT`

Đây là một khác biệt quan trọng cần phân biệt chính xác:

**`DateTimeFormatterBuilder.parseLenient()`** ảnh hưởng **giai đoạn 1**, tức độ linh hoạt của việc khớp văn bản, số chữ số, ký hiệu dấu và một số quy tắc lexical. `parseStrict()` của builder cũng ở **giai đoạn 1**, và là chế độ mặc định của builder nếu chưa thay đổi.

**`formatter.withResolverStyle(ResolverStyle.LENIENT)`** ảnh hưởng **giai đoạn 2**, tức cách ngày/tháng/giờ đã đọc được chuẩn hóa thành đối tượng thời gian.

Vì chúng ở hai giai đoạn khác nhau, bạn có thể:

- Dùng lexical lenient nhưng resolver STRICT: nhận `2024-2-3` với pattern yêu cầu `MM-dd` sau khi builder nới chữ số, **nhưng vẫn từ chối `2024-02-30`**.
- Dùng lexical strict và resolver LENIENT: vẫn yêu cầu dấu `-` theo pattern, nhưng có thể chuẩn hóa `2024-13-40` khi đủ trường số được đọc.
- Cần linh hoạt ký hiệu tháng? Xem `parseCaseInsensitive()`, `Locale` và pattern; không mặc định `parseLenient` tự bỏ qua mọi chữ hoa/thường.

Lưu `ParsePhasesDemo.java`:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.List;
import java.util.Locale;

public class ParsePhasesDemo {
    public static void main(String[] args) {
        DateTimeFormatter lexicalLenientResolverStrict =
                new DateTimeFormatterBuilder()
                        .parseLenient()
                        .appendPattern("uuuu-MM-dd")
                        .toFormatter(Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);

        for (String input : List.of(
                "2024-2-3",
                "2024-02-30",
                "2024/02/29")) {
            try {
                System.out.println(input + " -> " +
                        LocalDate.parse(
                                input,
                                lexicalLenientResolverStrict));
            } catch (DateTimeParseException e) {
                System.out.println(input + " -> rejected");
            }
        }

        System.out.println("resolver = " +
                lexicalLenientResolverStrict.getResolverStyle());
    }
}
```

```bash
javac ParsePhasesDemo.java
java ParsePhasesDemo
```

```text
2024-2-3 -> 2024-02-03
2024-02-30 -> rejected
2024/02/29 -> rejected
resolver = STRICT
```

Cả ba kết quả đều dễ kiểm chứng:

- Parser có thể chấp nhận một hoặc hai chữ số trong tháng/ngày khi đã bật `parseLenient`.
- Date resolver vẫn **STRICT**, nên ngày 30/02 bị từ chối.
- Dấu `/` không khớp literal `-` của pattern, vì thế lexical lenient **không** tự chấp nhận ký tự phân tách khác.

**Nguyên tắc thiết kế:** khi yêu cầu “người dùng có thể nhập 2/3 hoặc 02/03” nhưng ngày vẫn phải thực sự tồn tại, giải pháp là cấu hình **lexical flexibility** ở format chứ không cần giảm độ chặt của **calendar validation**.

## 13. Nhiều trường ngày cùng lúc: kiểm tra tính nhất quán

Một text có thể chứa cả `YEAR-MONTH-DAY` và `DAY_OF_YEAR`. Với năm nhuận 2024:

- `2024-03-01` là ngày thứ **61**.
- `2024-02-29` là ngày thứ **60**.

Nếu cùng một chuỗi chứa hai cách mô tả **mâu thuẫn**, resolution phải biết cách xử lý. Với formatter mặc định không lọc trường, hai cách giải quyết bị so sánh để tìm mâu thuẫn; ngay cả một resolver STRICT hợp lệ về từng field vẫn có thể thất bại nếu chúng không nhất quán.

`DateTimeFormatter.withResolverFields(...)` có thể chọn tập trường đưa sang giai đoạn resolution, ví dụ chỉ giữ `YEAR` và `DAY_OF_YEAR`. Đây là **công cụ lọc dữ liệu**, không phải thủ thuật sửa input sai mà không cần suy nghĩ.

Lưu `CrossFieldResolutionDemo.java`:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.time.temporal.ChronoField;
import java.util.Locale;

public class CrossFieldResolutionDemo {
    public static void main(String[] args) {
        DateTimeFormatter allFields = DateTimeFormatter
                .ofPattern("uuuu-MM-dd DDD", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);

        System.out.println("consistent = " +
                LocalDate.parse("2024-03-01 061", allFields));

        try {
            LocalDate.parse("2024-03-01 060", allFields);
            System.out.println("unexpected");
        } catch (DateTimeParseException ex) {
            System.out.println("conflict rejected");
        }

        DateTimeFormatter dayOfYearOnly =
                allFields.withResolverFields(
                        ChronoField.YEAR,
                        ChronoField.DAY_OF_YEAR);

        System.out.println("filtered = " +
                LocalDate.parse(
                        "2024-03-01 060", dayOfYearOnly));
    }
}
```

```bash
javac CrossFieldResolutionDemo.java
java CrossFieldResolutionDemo
```

```text
consistent = 2024-03-01
conflict rejected
filtered = 2024-02-29
```

Dòng `filtered` không có nghĩa input chứa `2024-03-01` là đúng. Ta đã **cố ý bỏ qua** các trường tháng/ngày rồi dùng số ngày trong năm (`060`) để dựng một LocalDate. Với form có dữ liệu dư cần kiểm soát nhất quán, tốt hơn nên **giữ toàn bộ trường và bắt lỗi mâu thuẫn**. Chỉ dùng `withResolverFields` khi giao thức quy định một tập trường là nguồn sự thật và những trường khác không được dùng để xác định ngày.

### 13.1. `parseUnresolved` để điều tra lỗi, không thay validation chuẩn

Nếu cần debug parser, `parseUnresolved` chỉ giải quyết giai đoạn 1 và trả một `TemporalAccessor` với các trường đọc được. API này cần `ParsePosition` và người gọi tự kiểm tra phần văn bản đã tiêu thụ; nó không tạo `LocalDate` đã được validate.

Cần tránh nhầm một lần `parseUnresolved` thành công với chứng minh ngày thật sự hợp lệ. Đối với request bình thường, dùng `LocalDate.parse(text, formatter)`/`LocalDateTime.parse(...)` là cách đầy đủ cả hai giai đoạn.

## 14. Resolver style có giới hạn: không tự giải quyết DST gap/overlap

`ResolverStyle` kiểm soát resolution của **trường thời gian được parse**. Nó không tự biến một `LocalDateTime` hợp lệ về mặt lịch thành một instant hợp lệ ở mọi `ZoneId`.

Ví dụ `2024-03-31T02:30` có **ngày và giờ hợp lệ** theo ISO calendar. Nhưng tại vùng `Europe/Paris` theo quy tắc lịch sử năm 2024, giờ địa phương 02:30 ngày 31/03 **không tồn tại** vì đồng hồ nhảy từ 02:00 tới 03:00.

Sau khi parse STRICT thành công, `local.atZone(paris)` có thể **đẩy giờ lên** để giải quyết gap theo chính sách của `ZonedDateTime`. Nếu nghiệp vụ muốn từ chối một local time không tồn tại, phải dùng **ZoneRules** hoặc `ZonedDateTime.ofStrict` ở bước giải vùng.

Lưu `ResolverVsZoneRulesDemo.java`:

```java
import java.time.DateTimeException;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;

public class ResolverVsZoneRulesDemo {
    public static void main(String[] args) {
        DateTimeFormatter strict = DateTimeFormatter
                .ofPattern("uuuu-MM-dd HH:mm")
                .withResolverStyle(ResolverStyle.STRICT);

        LocalDateTime local = LocalDateTime.parse(
                "2024-03-31 02:30", strict);
        ZoneId paris = ZoneId.of("Europe/Paris");

        System.out.println("parsed = " + local);
        System.out.println("validOffsets = " +
                paris.getRules().getValidOffsets(local));
        System.out.println("atZone = " + local.atZone(paris));

        try {
            ZonedDateTime.ofStrict(
                    local, ZoneOffset.ofHours(1), paris);
            System.out.println("unexpected");
        } catch (DateTimeException ex) {
            System.out.println("zoneStrict rejected gap");
        }
    }
}
```

```bash
javac ResolverVsZoneRulesDemo.java
java ResolverVsZoneRulesDemo
```

```text
parsed = 2024-03-31T02:30
validOffsets = []
atZone = 2024-03-31T03:30+02:00[Europe/Paris]
zoneStrict rejected gap
```

Phân tách rõ hai policy:

1. **Calendar parse policy:** ngày/tháng/giờ có nằm trong phạm vi và đúng lịch không? `ResolverStyle`.
2. **Time-zone resolution policy:** giờ địa phương có tồn tại ở zone không, hay rơi vào gap/overlap? `ZoneRules`, `ZonedDateTime` và lựa chọn offset.

Ngay cả `ResolverStyle.STRICT` cũng không thay thế kiểm tra “giờ 02:30 tại Paris có tồn tại hay không”. Với overlap, có **hai** offset hợp lệ; ứng dụng cần quy tắc chọn lần trước/lần sau hoặc yêu cầu user chọn rõ ràng. Nếu làm lịch hẹn quốc tế, cả hai tầng validation đều quan trọng.

## 15. Formatter parse gì và parse sang loại đối tượng nào?

`DateTimeFormatter` không tự quyết định bạn cần `LocalDate`, `LocalDateTime`, `LocalTime` hay `OffsetDateTime`. Kiểu truy vấn của caller ảnh hưởng yêu cầu đủ trường:

- `LocalDate.parse(text, formatter)` đòi có đủ dữ liệu để xác định ngày.
- `LocalDateTime.parse(text, formatter)` cần cả ngày và giờ.
- `LocalTime.parse(text, formatter)` cần giờ; không chứa ngày dư.
- `OffsetDateTime.parse(text, formatter)` đòi offset để xác định instant.
- `formatter.parseBest(...)` có thể thử các truy vấn theo thứ tự ưu tiên, hữu ích với pattern có phần giờ optional.

Một pattern chỉ chứa `HH:mm` không tự dựng thành LocalDate vì thiếu năm/tháng/ngày; `ResolverStyle.LENIENT` không “tự đoán hôm nay” để lấp dữ liệu. Nếu giao thức có mặc định được tài liệu hóa (ví dụ ngày chỉ có tháng/ngày nhưng năm được cung cấp từ một field khác), hãy dùng `DateTimeFormatterBuilder.parseDefaulting(...)` có chủ đích hoặc kết hợp từ object chuyên biệt, thay vì tự động chọn ngày của hệ thống.

### 15.1. Số giây nhuận và các lịch khác

Múi giờ, lịch ISO, leap second và hệ lịch không phải là cùng khái niệm. `ResolverStyle` không thay thế logic đồng bộ UTC hay phát hiện leap second ở mọi dữ liệu. `DateTimeFormatter.parsedLeapSecond()` chỉ hữu ích trong các trường hợp parser/formatter hỗ trợ leap second theo hợp đồng, không phải câu trả lời chung cho mọi dạng ISO text.

Với chronology không phải ISO (`JapaneseChronology`, `HijrahChronology`...), behavior cụ thể khi resolve có thể khác ISO. Các ví dụ STRICT/SMART/LENIENT ở đây nêu cho **ISO calendar**, không được suy ra rằng tất cả hệ lịch có cùng quy tắc năm nhuận, số ngày tháng hay era. Khi cần lịch khác, cấu hình chronology minh bạch và kiểm thử riêng.

## 16. Chọn STRICT, SMART hay LENIENT theo nghiệp vụ

| Bài toán | Chính sách gợi ý | Lý do |
| --- | --- | --- |
| Ngày sinh, ngày cấp giấy tờ, ngày trên hóa đơn | `STRICT` | Không được âm thầm chuyển ngày khác |
| Ngày giao dịch hoặc hạn thanh toán từ API | `STRICT` | Giữ đúng nghĩa input, lỗi phải được báo |
| File dữ liệu import có thể gõ nhầm `2024-02-30` | `STRICT` + báo dòng lỗi | Tránh tạo giao dịch sang ngày khác |
| Bài toán có chủ đích “ngày cuối tháng” | Logic nghiệp vụ tường minh, có thể dùng SMART **nếu đã chấp nhận clamp** | Phải lưu ý định; SMART chỉ là một policy kỹ thuật |
| UI nhận ngày cuối tháng và tự chuẩn hóa theo quy tắc rõ ràng | `SMART` với kiểm tra/thông báo thay đổi | Cho phép nhưng không giấu kết quả đã đổi |
| Hệ thống tính date từ phần dư tháng/ngày | `LENIENT` theo contract riêng | Cho phép phép tràn lịch một cách có chủ đích |
| Giờ `24:00` chỉ “kết thúc ngày” | SMART + `parsedExcessDays`/LocalDateTime | Cần giữ ngày dư |
| Chuỗi chứa nhiều cách diễn giải xung đột | `STRICT`, không lọc trường bừa bãi | Phải phát hiện mâu thuẫn |
| Input lẫn dấu phân cách và độ dài chữ số | Cấu hình parser/formatter ở giai đoạn 1 | Không dùng LENIENT resolver để đoán định dạng |
| Lịch hẹn theo vùng có DST | STRICT calendar + `ZoneRules` policy | Hai tầng kiểm tra độc lập |

**Điểm thiết kế quan trọng:** STRICT kiểm tra tính hợp lệ của một date, **không phải toàn bộ quy tắc nghiệp vụ**. Ví dụ `2024-02-29` hợp lệ, nhưng vẫn có thể không được phép nếu form yêu cầu “ngày không nằm trong tương lai”. Sau khi parse STRICT, bạn còn cần kiểm tra range và constraints của domain.

Khi chọn SMART/LENIENT, nên ghi log raw input và kết quả normalized hoặc thông báo cho người dùng. Không được đổi ngày “thành công” mà không để người nhập nhận biết nếu ngày mang ý nghĩa pháp lý, thanh toán hoặc an toàn vận hành.

## 17. Code ứng dụng: hàm parse chặt chẽ và phản hồi lỗi rõ ràng

Một service xử lý chuỗi ngày có thể tạo formatter **immutable, thread-safe** dùng lại, cùng một phương thức parse có contract rõ ràng. Đừng tạo một formatter mới cho mọi lần gọi nếu format giống nhau; nhưng cũng đừng dùng field cấu hình toàn cục mutable để thay đổi resolver style trong lúc nhiều request chạy.

Lưu `StrictDateInputDemo.java`:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.List;
import java.util.Locale;

public class StrictDateInputDemo {
    private static final DateTimeFormatter INPUT =
            DateTimeFormatter.ofPattern(
                    "uuuu-MM-dd", Locale.ROOT)
                    .withResolverStyle(ResolverStyle.STRICT);

    private static String validate(String text) {
        try {
            LocalDate date = LocalDate.parse(text, INPUT);
            if (date.isBefore(LocalDate.of(2000, 1, 1))) {
                return "outside allowed range";
            }
            return "accepted " + date;
        } catch (DateTimeParseException ex) {
            return "invalid date";
        }
    }

    public static void main(String[] args) {
        for (String input : List.of(
                "2024-02-29",
                "2023-02-29",
                "1999-12-31",
                "2024/02/29")) {
            System.out.println(input + " => " +
                    validate(input));
        }
    }
}
```

```bash
javac StrictDateInputDemo.java
java StrictDateInputDemo
```

```text
2024-02-29 => accepted 2024-02-29
2023-02-29 => invalid date
1999-12-31 => outside allowed range
2024/02/29 => invalid date
```

Cần tách hai loại lỗi:

- `DateTimeParseException`: không đọc được hoặc không resolve được một ngày đúng contract.
- **Domain violation**: ngày parse thành công nhưng nằm ngoài khoảng nghiệp vụ cho phép.

Đây là code minh họa tập trung vào ngày nhập, chưa xử lý HTTP status, message localization hoặc lỗi null. Trong sản phẩm, validate input null/empty trước khi parse, dùng cấu trúc kết quả hoặc exception domain rõ ràng và đừng in stack trace của người dùng ra ngoài.

### 17.1. Có phải mọi input phải dùng STRICT?

Không phải. `ResolverStyle.LENIENT` và `SMART` là API hợp pháp còn hiệu lực, hữu ích khi **có một quy ước dữ liệu yêu cầu chúng**. Lỗi không nằm ở việc dùng SMART/LENIENT, mà ở việc không biết chúng đang chuẩn hóa gì. Một câu hỏi review tốt là “Nếu người dùng gõ 30/02, hệ thống có được phép biến thành 29/02 hay 01/03 không?”.

Nếu câu trả lời là **không**, dùng STRICT. Nếu câu trả lời là **có theo chính sách X**, nên mô tả và kiểm tra chính sách X trong code/test, kể cả nếu việc triển khai dựa trên SMART/LENIENT.

## 18. Checklist kiểm thử

Một bộ test chất lượng cho formatter cần bao phủ ít nhất:

- Ngày hợp lệ ở năm nhuận và không nhuận.
- `29/02` ở năm không nhuận; `30/02` trong năm nhuận; `31/04`; ngày 0, ngày 32.
- Tháng 0, tháng 13; năm chuyển mốc 31/12 → 01/01 nếu dùng LENIENT.
- `24:00` và giờ/phút tràn, cùng **thông tin excess days**.
- Pattern `uuuu` so với `yyyy` khi dùng STRICT; có/không có `ERA`.
- Formatter mặc định SMART vs formatter ISO mặc định STRICT.
- Cấu hình builder `parseLenient()`/`parseStrict()` ở giai đoạn lexical.
- Dấu phân cách, độ dài chữ số, chữ tháng và Locale.
- Nhiều trường cùng chỉ một ngày nhưng mâu thuẫn (`MONTH/DAY` vs `DAY_OF_YEAR`).
- Input thiếu trường: chỉ có giờ mà cần ngày, chỉ có ngày mà cần timestamp kèm offset.
- Input local datetime ở zone có DST gap/overlap; kiểm tra bằng `ZoneRules` **riêng**.
- Các domain constraints, ví dụ ngày phải nằm trong một khoảng.
- Round-trip: format rồi parse có giữ đúng ý nghĩa cần thiết không; nếu formatter cố ý bỏ trường thì không yêu cầu giữ dữ liệu đã bỏ.

**Không viết test chỉ dựa vào text exception đầy đủ.** Dòng lỗi có thể chứa chi tiết implementation; kiểm tra loại exception hoặc một kết quả domain rõ ràng sẽ bền hơn. Các ví dụ trên in chữ `INVALID`/`rejected` cố định nên stdout không lệ thuộc vào thông điệp JDK.

### 18.1. Bài tập

**Bài 1:** Dự đoán `STRICT`, `SMART`, `LENIENT` với `2023-02-29` và `2024-02-30`. Giải thích vì sao SMART và LENIENT có ngày kết quả khác nhau.

**Bài 2:** Parse `2024-03-31 24:00` bằng ba style. Cần giữ thông tin nào nếu input chỉ là `24:00` mà không có ngày?

**Bài 3:** Tại sao `yyyy-MM-dd` + STRICT có thể không tạo được LocalDate dù ngày hợp lệ, trong khi `uuuu-MM-dd` + STRICT lại được? Nêu hai cách xử lý hợp lệ.

**Bài 4:** Một import file có input `2024/02/29` nhưng formatter là `uuuu-MM-dd`. Đổi resolver sang LENIENT có giải quyết lỗi literal `/` không? Bạn sẽ sửa phần nào của pipeline?

**Bài 5:** Một giao thức gửi `2024-03-01` và day-of-year `060`. Chọn STRICT với tất cả trường hay lọc trường bằng `withResolverFields`? Hãy giải thích theo contract nghiệp vụ.

**Bài 6:** `2024-03-31 02:30` có thể parse STRICT thành `LocalDateTime`, nhưng ở `Europe/Paris` nó không tồn tại. Vì sao? Bạn sẽ dùng API nào để từ chối lịch hẹn này?

### 18.2. Lời giải thực hành

Lưu `ResolverStylePractice.java`:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;

public class ResolverStylePractice {
    private static String result(String text,
                                 ResolverStyle style) {
        DateTimeFormatter formatter =
                DateTimeFormatter.ofPattern("uuuu-MM-dd")
                        .withResolverStyle(style);
        try {
            return LocalDate.parse(text, formatter).toString();
        } catch (DateTimeParseException e) {
            return "INVALID";
        }
    }

    public static void main(String[] args) {
        String value = "2024-02-30";

        System.out.println("strict = " +
                result(value, ResolverStyle.STRICT));
        System.out.println("smart = " +
                result(value, ResolverStyle.SMART));
        System.out.println("lenient = " +
                result(value, ResolverStyle.LENIENT));

        System.out.println("leapDayValid = " +
                LocalDate.of(2024, 2, 29).isLeapYear());
    }
}
```

```bash
javac ResolverStylePractice.java
java ResolverStylePractice
```

```text
strict = INVALID
smart = 2024-02-29
lenient = 2024-03-01
leapDayValid = true
```

Đáp án tóm tắt: bài 2 xem `TimeResolverDemo`/`ExcessDaysDemo`; bài 3 dùng `uuuu` hoặc cung cấp `ERA` hợp lệ; bài 4 sửa cấu hình lexical formatter hoặc chấp nhận hai định dạng rõ ràng, không dùng resolver để thay dấu; bài 5 giữ tất cả trường nếu muốn phát hiện inconsistency; bài 6 kiểm tra `ZoneRules.getValidOffsets` hoặc dựng `ZonedDateTime.ofStrict` theo quy tắc vùng.

## 19. Lỗi phổ biến cần loại bỏ

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Nghĩ pattern đúng nghĩa ngày hợp lệ | Parsing có hai giai đoạn | Chọn resolver style và test lịch |
| Tin rằng `ofPattern` mặc định STRICT | Nó mặc định SMART | Gọi `withResolverStyle(STRICT)` tường minh |
| Dùng SMART cho input nghiệp vụ cần ngày nguyên bản | SMART có thể clamp xuống cuối tháng | STRICT nếu phải từ chối ngày sai |
| Dùng LENIENT để xử lý dấu `/` thay vì `-` | Resolver không kiểm soát literal lexical | Sửa format/parser |
| Dùng `yyyy` với STRICT mà không có ERA | YEAR_OF_ERA chưa đủ resolve | Dùng `uuuu` hoặc era rõ ràng |
| Dùng `YYYY` thay `uuuu` cho ngày thông thường | Week-based year khác calendar year | Chọn pattern đúng |
| Cho rằng SMART sửa mọi giá trị ngoài giới hạn | SMART xử lý theo từng field | Test case, đọc Javadoc |
| Cho rằng `24:00` bằng `00:00` không khác gì | Có thể mang **một ngày dư** | Giữ date hoặc `parsedExcessDays` |
| Cho rằng parse STRICT không thể rơi vào DST gap | Calendar validity khác time-zone validity | Thêm `ZoneRules` validation |
| Dùng `parseLenient` để mong nhận ngày 30/02 dưới STRICT | Hai giai đoạn tách biệt | Đổi resolver policy nếu thật sự muốn normalize |
| Dùng `parseUnresolved` thành kết quả valid | Chỉ giai đoạn 1 | Resolve qua `LocalDate.parse` |
| Lọc mâu thuẫn bằng `withResolverFields` mà không có contract | Có thể bỏ trường lỗi âm thầm | Giữ consistency check nếu yêu cầu |
| Quên xử lý chronology ngoài ISO | Quy tắc lịch khác nhau | Cấu hình chronology, test riêng |
| Nhầm parse exception với domain constraint | Ngày hợp lệ vẫn có thể bị cấm | Tách validation ngày và nghiệp vụ |
| Dùng `==` để so formatter/date objects | Kiểm tra identity không phù hợp | Dùng `equals` hoặc so sánh giá trị |
| Biến formatter dùng chung thành mutable config | Gây giả định sai về state | `DateTimeFormatter` immutable; tạo bản copy bằng `withResolverStyle` |

## 20. Tài liệu Java API hiện hành

- Oracle Java SE 26 — `ResolverStyle`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/ResolverStyle.html
- Oracle Java SE 26 — `DateTimeFormatter`, hai giai đoạn parse/resolve, mặc định SMART và các formatter ISO: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeFormatter.html
- Oracle Java SE 26 — `DateTimeFormatterBuilder`, `parseLenient`/`parseStrict`, `parseDefaulting`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html
- Oracle Java SE 26 — `ChronoField`, `YEAR`/`YEAR_OF_ERA`/`DAY_OF_YEAR`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/temporal/ChronoField.html
- Oracle Java SE 26 — `LocalDate`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/LocalDate.html
- Oracle Java SE 26 — `LocalDateTime`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/LocalDateTime.html
- Oracle Java SE 26 — `ZoneRules`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/zone/ZoneRules.html

**Ghi nhớ:** **STRICT** kiểm tra ngày giờ chặt chẽ; **SMART** có một số điều chỉnh hợp lý (như clamp về cuối tháng); **LENIENT** thực hiện chuẩn hóa phần dư. Đây là chính sách **giai đoạn 2** của `DateTimeFormatter`. `parseLenient()` của builder là chuyện khác — thuộc **giai đoạn 1**. Đối với ngày ISO cần xác thực đúng như nhập, dùng `uuuu-MM-dd` kết hợp `withResolverStyle(STRICT)` và kiểm tra thêm các quy tắc nghiệp vụ. Nếu input có zone, hãy kiểm tra DST gap/overlap riêng bằng `ZoneRules`.