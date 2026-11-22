# with() và plus() qua giao diện temporal

## 1. Từ thao tác cụ thể đến hợp đồng dùng chung

Một chương trình có thể cần áp dụng cùng một kiểu thao tác cho nhiều kiểu ngày giờ: cộng ngày cho `LocalDate`, cộng giờ cho `LocalTime`, hoặc điều chỉnh ngày trong `LocalDateTime`. Viết mọi phép tính bằng phương thức riêng như `plusDays`, `plusHours` sẽ thuận tiện khi đã biết kiểu, nhưng chưa tạo được một đầu vào chung cho công cụ xử lý tổng quát.

Giao diện `Temporal` trong `java.time.temporal` cung cấp hợp đồng đọc và thao tác trên những giá trị ngày giờ đủ thông tin. Hai nhóm phương thức trọng tâm là:

- `with(...)`: tạo kết quả bằng cách **đặt một trường** hoặc **áp dụng một quy tắc điều chỉnh**.
- `plus(...)`: tạo kết quả bằng cách **cộng một lượng theo đơn vị** hoặc **cộng một đối tượng mô tả lượng thời gian**.

Ví dụ với ngày `2024-02-20`, đặt ngày trong tháng thành 1 cho `2024-02-01`; cộng một ngày cho `2024-02-21`. Cả hai đều tạo ngày hợp lệ, nhưng trả lời hai yêu cầu khác nhau. Đây là điểm phải hiểu trước khi dùng các overload.

`TemporalAccessor` là giao diện đọc dữ liệu. `Temporal` mở rộng nó để có thêm các phép thao tác như `with`, `plus`, `minus` và `until`. Những kiểu thường gặp triển khai `Temporal` gồm `LocalDate`, `LocalTime`, `LocalDateTime`, `YearMonth`, `Instant` và các kiểu có offset/múi giờ.

Không phải mọi kiểu mang thông tin ngày giờ đều triển khai `Temporal`. Chẳng hạn `MonthDay` không có năm, nên chưa đủ thông tin để biết tháng 2 dài bao nhiêu ngày trong mọi phép cộng; nó không có cùng hợp đồng cộng/trừ với `LocalDate`. Xem mô hình và phạm vi sử dụng ở [Temporal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/Temporal.html).

## 2. Bốn overload cần phân biệt

Các chữ ký dưới đây được viết theo kiểu trả về nhìn thấy từ giao diện `Temporal`:

| Chữ ký | Ý nghĩa tham số | Ví dụ |
| --- | --- | --- |
| `Temporal with(TemporalField field, long newValue)` | Đặt trường thành một giá trị | `value.with(DAY_OF_MONTH, 1)` |
| `Temporal with(TemporalAdjuster adjuster)` | Áp một quy tắc điều chỉnh | `value.with(lastDayOfMonth())` |
| `Temporal plus(long amount, TemporalUnit unit)` | Cộng lượng theo một đơn vị | `value.plus(7, DAYS)` |
| `Temporal plus(TemporalAmount amount)` | Cộng lượng được đóng gói trong đối tượng | `value.plus(Period.ofDays(7))` |

Trong ví dụ, `DAY_OF_MONTH` là `ChronoField.DAY_OF_MONTH`, `DAYS` là `ChronoUnit.DAYS`, và `lastDayOfMonth()` đến từ `TemporalAdjusters`.

Các vai trò không được trộn lẫn:

- `TemporalField` mô tả một thành phần, chẳng hạn ngày trong tháng.
- `TemporalAdjuster` đóng gói thuật toán tìm kết quả điều chỉnh.
- `TemporalUnit` mô tả đơn vị, chẳng hạn ngày hoặc giờ.
- `TemporalAmount` mô tả lượng, chẳng hạn 7 ngày hoặc 2 giờ.

`ChronoUnit.DAYS` chỉ là đơn vị, chưa có lượng. `Period.ofDays(7)` đã có cả đơn vị và lượng nên dùng được với overload một tham số của `plus`.

## 3. with(): đặt trường hoặc áp quy tắc

### 3.1. with(field, value) thay một thành phần

Với `Temporal value = LocalDate.of(2024, 2, 20)`, biểu thức `value.with(ChronoField.DAY_OF_MONTH, 1)` cho ngày 1/2/2024. Phần năm và tháng vẫn được giữ theo quy tắc của thao tác này.

`with` không có nghĩa “cộng”. Đặt ngày thành 1 khác cộng một ngày. Tương tự, đặt `MONTH_OF_YEAR` thành 3 khác cộng ba tháng.

Giá trị mới phải được xử lý theo hợp đồng của trường và kiểu cụ thể. Với ngày thuộc tháng 2/2024, đặt `DAY_OF_MONTH = 30` báo `DateTimeException`. Không được tự suy ra rằng mọi giá trị sai sẽ được lùi về ngày hợp lệ; một số thao tác có quy tắc điều chỉnh riêng, một số thao tác từ chối đầu vào.

### 3.2. with(adjuster) áp một thuật toán điều chỉnh

“Ngày cuối cùng của tháng” không phải một giá trị cố định: có thể là 28, 29, 30 hoặc 31. `TemporalAdjusters.lastDayOfMonth()` đóng gói quy tắc đó. Dùng `value.with(adjuster)` giúp mã diễn đạt yêu cầu mà không phải viết lại nhánh xử lý tháng.

Đối tượng điều chỉnh (adjuster) nhận `Temporal` rồi tạo kết quả. Về cơ chế, overload này ủy quyền cho `adjuster.adjustInto(value)`. Cách gọi `value.with(adjuster)` thường thuận chiều đọc hơn vì giá trị cần điều chỉnh nằm ở đầu biểu thức. Hợp đồng được mô tả tại [TemporalAdjuster](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/TemporalAdjuster.html).

Một adjuster không nhất thiết chỉ thay một trường. Nó có thể kết hợp nhiều bước, chẳng hạn “đưa về ngày đầu tháng, rồi sang tháng tiếp theo”. Dù vậy, nó phải có phạm vi áp dụng rõ ràng; quy tắc cần trường ngày không thể áp dụng cho `LocalTime`.

## 4. plus(): lượng cộng và đơn vị phải phù hợp dữ liệu

### 4.1. plus(amount, unit)

`value.plus(7, ChronoUnit.DAYS)` yêu cầu đối tượng thực hiện phép cộng 7 ngày theo quy tắc của kiểu đó. Với `LocalDate`, phép này tương ứng `plusDays(7)`.

Đơn vị chuẩn thường là `ChronoUnit`. Nhưng giao diện nhận `TemporalUnit`, nên có thể nhận đơn vị khác nếu kiểu và đơn vị phối hợp hỗ trợ. Với đơn vị tùy chỉnh, lớp thời gian có thể chuyển việc xử lý sang `unit.addTo(...)`; không nên hiểu rằng mọi phép cộng đều được cài đặt trong chính enum `ChronoUnit`. Xem cơ chế tại [TemporalUnit](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/TemporalUnit.html).

Hỗ trợ thao tác không đồng nghĩa mọi kiểu có cùng ý nghĩa lưu trữ. Cộng hai giờ vào `LocalTime` lúc 23:30 cho 01:30; kiểu này không giữ thông tin ngày hôm sau. Nếu yêu cầu cần cả ngày và giờ, phải chọn kiểu chứa đủ hai thành phần ngay từ đầu.

### 4.2. plus(TemporalAmount)

Hai triển khai phổ biến của `TemporalAmount` là:

- `Period`: lượng theo lịch, gồm năm, tháng và ngày.
- `Duration`: lượng theo thời gian, lưu giây và nano giây.

Overload này ủy quyền cho `amount.addTo(value)`. Đối tượng lượng quyết định cách cộng các thành phần của nó; nó không phải một con số vô hướng dùng được trên mọi kiểu. Xem hợp đồng ở [TemporalAmount](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/TemporalAmount.html).

Với `LocalDate`, `plus(Period.ofDays(7))` cộng được 7 ngày. Nhưng `plus(Duration.ofDays(1))` báo không hỗ trợ: lượng `Duration` đó được biểu diễn bằng giây, còn `LocalDate` không hỗ trợ cộng giây. Tên phương thức tạo lượng có chữ “Days” chưa đủ để kết luận nó tương thích với ngày lịch.

Với `LocalDateTime`, cộng `Duration.ofHours(2)` là phù hợp vì kiểu có phần giờ. Với dữ liệu có múi giờ, lựa chọn lượng theo lịch hay lượng theo thời gian còn có thể ảnh hưởng kết quả khi độ lệch UTC thay đổi; không tự coi một ngày lịch luôn tương đương 24 giờ trong mọi ngữ cảnh.

## 5. Gọi qua giao diện vẫn chạy hành vi của đối tượng cụ thể

Xét đoạn minh họa dùng trong một phương thức Java:

```java
LocalDate concrete = LocalDate.of(2024, 2, 20);
Temporal general = concrete;

LocalDate a = concrete.plus(1, ChronoUnit.DAYS);
Temporal b = general.plus(1, ChronoUnit.DAYS);
```

Cả `a` và `b` đều mang ngày `2024-02-21`. Trong trường hợp này, đối tượng kết quả thực tế của cả hai vẫn là `LocalDate`.

Khác biệt nằm ở kiểu tĩnh của biểu thức:

- Từ biến `LocalDate`, trình biên dịch thấy overload được lớp cụ thể khai báo với kiểu trả về `LocalDate`.
- Từ biến `Temporal`, trình biên dịch chỉ bảo đảm kết quả là `Temporal`.

Vì vậy, không thể gán trực tiếp `general.plus(1, DAYS)` vào biến `LocalDate` chỉ vì biết đối tượng đầu vào lúc chạy là `LocalDate`. Tương tự, biến `Temporal` không có phương thức tiện ích `plusDays` hay `getYear` trong hợp đồng của nó.

Nếu miền nghiệp vụ đã chắc chắn là ngày ISO, có thể giữ kiểu cụ thể ngay từ đầu. Khi nhận kết quả tổng quát mà thực sự cần chuyển sang ngày, `LocalDate.from(result)` diễn đạt một phép trích/chuyển rõ ràng. Tuy nhiên, phép chuyển này cũng chấp nhận một số kiểu khác có thông tin ngày, chẳng hạn `LocalDateTime`, và bỏ phần giờ. Không dùng nó để che việc thiết kế sai kiểu hoặc thay cho kiểm tra rằng kiểu kết quả thực tế đúng điều đã cam kết.

Dùng giao diện không mở thêm khả năng cho đối tượng: một `LocalDate` được tham chiếu qua `Temporal` vẫn không có giờ và không cộng được `HOURS`.

## 6. Bất biến, kiểu trả về và việc giữ kết quả

Các kiểu chuẩn đang dùng của `java.time` như `LocalDate`, `LocalTime`, `LocalDateTime` là bất biến. Chúng không bị sửa sau lời gọi `with` hoặc `plus`.

Đoạn minh họa sau bỏ mất kết quả:

```java
Temporal value = LocalDate.of(2024, 2, 20);
value.plus(1, ChronoUnit.DAYS);
// value vẫn biểu diễn 2024-02-20.
```

Nếu cần biến trỏ đến giá trị mới, phải gán lại:

```java
value = value.plus(1, ChronoUnit.DAYS);
// value nay biểu diễn 2024-02-21.
```

Không đồng nhất hai điều: “gán lại biến” và “thay đổi đối tượng”. Sau phép gán, biến tham chiếu kết quả mới; giá trị ngày ban đầu vẫn giữ nguyên.

Bản thân giao diện `Temporal` không ép mọi triển khai tự viết phải bất biến. Do đó, không diễn giải từ khóa “read-write” trong tài liệu thành cam kết rằng mọi thao tác đều sửa đối tượng tại chỗ. Với các kiểu chuẩn, hãy làm việc theo mô hình nhận giá trị trả về; với kiểu tự triển khai, đọc đúng hợp đồng của kiểu đó.

Hợp đồng của `with`/`plus` yêu cầu kết quả có cùng kiểu quan sát được với đầu vào. Riêng adjuster hoặc amount tự viết cũng phải giữ kiểu đó và không sửa đầu vào. Không viết một adjuster nhận `LocalDateTime` nhưng trả `LocalDate`, vì như vậy vừa đổi kiểu vừa làm mất phần giờ. Khi thao tác không thay đổi giá trị, thư viện cũng có thể trả lại chính đối tượng đang có; so sánh giá trị bằng `equals`, không dựa vào `==`.

## 7. Ghép thao tác: thứ tự là một phần của quy tắc

Từ `2024-02-20`, hai chuỗi dưới đây khác nhau:

```text
with(lastDayOfMonth()) rồi plus(1, DAYS)
2024-02-20 → 2024-02-29 → 2024-03-01

plus(1, DAYS) rồi with(lastDayOfMonth())
2024-02-20 → 2024-02-21 → 2024-02-29
```

Mỗi bước dùng kết quả của bước ngay trước nó. Đưa về cuối tháng trước rồi cộng ngày có nghĩa khác với cộng ngày trước rồi tìm cuối tháng mới.

Khi viết một chuỗi, hãy phát biểu quy tắc theo đúng thứ tự và dùng ca kiểm tra mà hai thứ tự có thể tạo kết quả khác nhau. Không chỉ kiểm tra “ngày cuối cùng nhận được vẫn hợp lệ”, bởi cả 1/3 và 29/2 đều hợp lệ nhưng chỉ một ngày đúng với yêu cầu cụ thể.

## 8. Một tiện ích Temporal cần hợp đồng hẹp và rõ

Chữ ký `shift(Temporal value, long amount, TemporalUnit unit)` cho phép nhận nhiều kiểu, nhưng không có nghĩa cho phép mọi kết hợp đầu vào.

Một tiện ích như vậy nên:

1. Yêu cầu đầu vào và đơn vị khác `null`.
2. Kiểm tra `value.isSupported(unit)` nếu đơn vị được chọn động.
3. Gọi phép cộng và giữ kết quả.
4. Cho lỗi giá trị ngoài miền hoặc tràn số được thể hiện rõ; không biến mọi lỗi thành “không hỗ trợ”.
5. Trả `Temporal` nếu đó là hợp đồng thực sự, hoặc dùng kiểu cụ thể khi miền nghiệp vụ đã xác định.

Với `with(field, value)`, phép kiểm tra tương ứng là `isSupported(field)`. Nó chỉ cho biết loại trường được hỗ trợ; nó không xác nhận mọi giá trị đặt vào đều hợp lệ.

Không có phép `isSupported(adjuster)` hay `isSupported(amount)` tổng quát trên `Temporal`. Một adjuster có thể cần nhiều trường/đơn vị, còn một amount có thể chứa nhiều thành phần. Cần biết yêu cầu của đối tượng chiến lược hoặc xử lý lỗi đúng hợp đồng. Không chỉ kiểm tra một hằng `DAYS` rồi suy ra mọi `Duration` đều dùng được.

## 9. Chương trình Java 17+ chạy độc lập

Lưu mã sau thành `TemporalOperations.java`. Nó minh họa đủ bốn overload, gọi qua giao diện, việc bỏ/giữ kết quả, thứ tự chuỗi, điều chỉnh tự viết và các trường hợp lỗi. Chương trình không cần thư viện ngoài.

`FIRST_OF_NEXT_MONTH` là quy tắc “ngày đầu tháng tiếp theo”. Lambda chỉ dùng `with` và `plus` trên đầu vào nên giữ được kiểu thời gian cụ thể. Bài này kiểm chứng nó với `LocalDate` và `LocalDateTime`; nó không được quảng bá như một quy tắc tương thích với mọi kiểu hay mọi hệ lịch.

```java
import java.time.DateTimeException;
import java.time.Duration;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.Period;
import java.time.temporal.ChronoField;
import java.time.temporal.ChronoUnit;
import java.time.temporal.Temporal;
import java.time.temporal.TemporalAdjuster;
import java.time.temporal.TemporalAdjusters;
import java.time.temporal.TemporalUnit;
import java.time.temporal.UnsupportedTemporalTypeException;
import java.util.Objects;

public class TemporalOperations {
    private static int checks;

    private static final TemporalAdjuster FIRST_OF_NEXT_MONTH =
            value -> value.with(ChronoField.DAY_OF_MONTH, 1)
                          .plus(1, ChronoUnit.MONTHS);

    private static Temporal shift(Temporal value, long amount, TemporalUnit unit) {
        Objects.requireNonNull(value, "value");
        Objects.requireNonNull(unit, "unit");
        if (!value.isSupported(unit)) {
            throw new IllegalArgumentException("Unsupported unit: " + unit);
        }
        return value.plus(amount, unit);
    }

    private static void eq(Object actual, Object expected) {
        if (!Objects.equals(actual, expected)) {
            throw new AssertionError("expected=" + expected + ", actual=" + actual);
        }
        checks++;
    }

    private static void rejects(Class<? extends RuntimeException> type,
                                Runnable action) {
        try {
            action.run();
        } catch (RuntimeException ex) {
            if (!type.isInstance(ex)) {
                throw new AssertionError("Unexpected exception", ex);
            }
            checks++;
            return;
        }
        throw new AssertionError("Expected " + type.getSimpleName());
    }

    public static void main(String[] args) {
        LocalDate original = LocalDate.of(2024, 2, 20);
        Temporal value = original;
        Temporal first = value.with(ChronoField.DAY_OF_MONTH, 1);
        Temporal monthEnd = value.with(TemporalAdjusters.lastDayOfMonth());
        Temporal nextWeek = value.plus(7, ChronoUnit.DAYS);
        Temporal plusPeriod = value.plus(Period.ofDays(7));
        eq(first, LocalDate.of(2024, 2, 1));
        eq(monthEnd, LocalDate.of(2024, 2, 29));
        eq(nextWeek, LocalDate.of(2024, 2, 27));
        eq(plusPeriod, nextWeek);
        eq(first.getClass(), LocalDate.class);
        eq(value, original);
        value.plus(1, ChronoUnit.DAYS); // Result intentionally discarded.
        eq(value, LocalDate.of(2024, 2, 20));

        Temporal reassigned = value;
        reassigned = reassigned.plus(1, ChronoUnit.DAYS);
        eq(reassigned, LocalDate.of(2024, 2, 21));
        eq(LocalDate.from(reassigned), LocalDate.of(2024, 2, 21));

        Temporal monthThenDay = value.with(TemporalAdjusters.lastDayOfMonth())
                .plus(1, ChronoUnit.DAYS);
        Temporal dayThenMonth = value.plus(1, ChronoUnit.DAYS)
                .with(TemporalAdjusters.lastDayOfMonth());
        eq(monthThenDay, LocalDate.of(2024, 3, 1));
        eq(dayThenMonth, LocalDate.of(2024, 2, 29));

        Temporal nextMonth = value.with(FIRST_OF_NEXT_MONTH);
        eq(nextMonth, LocalDate.of(2024, 3, 1));
        LocalDateTime dateTime = LocalDateTime.of(2024, 2, 20, 10, 15);
        Temporal adjustedDateTime = dateTime.with(FIRST_OF_NEXT_MONTH);
        eq(adjustedDateTime, LocalDateTime.of(2024, 3, 1, 10, 15));
        eq(adjustedDateTime.getClass(), LocalDateTime.class);
        eq(dateTime.plus(Duration.ofHours(2)),
                LocalDateTime.of(2024, 2, 20, 12, 15));

        eq(shift(original, 2, ChronoUnit.DAYS), LocalDate.of(2024, 2, 22));
        eq(shift(LocalTime.of(23, 30), 2, ChronoUnit.HOURS),
                LocalTime.of(1, 30));
        eq(value.isSupported(ChronoUnit.HOURS), false);
        rejects(UnsupportedTemporalTypeException.class,
                () -> value.plus(1, ChronoUnit.HOURS));
        rejects(UnsupportedTemporalTypeException.class,
                () -> value.with(ChronoField.HOUR_OF_DAY, 9));
        rejects(UnsupportedTemporalTypeException.class,
                () -> value.plus(Duration.ofDays(1)));
        rejects(UnsupportedTemporalTypeException.class,
                () -> LocalTime.NOON.with(FIRST_OF_NEXT_MONTH));
        rejects(IllegalArgumentException.class,
                () -> shift(original, 1, ChronoUnit.HOURS));
        rejects(DateTimeException.class,
                () -> value.with(ChronoField.DAY_OF_MONTH, 30));

        System.out.println("original=" + original);
        System.out.println("first=" + first);
        System.out.println("monthEnd=" + monthEnd);
        System.out.println("nextWeek=" + nextWeek);
        System.out.println("monthThenDay=" + monthThenDay);
        System.out.println("dayThenMonth=" + dayThenMonth);
        System.out.println("adjustedDateTime=" + adjustedDateTime);
        System.out.println("PASS checks=" + checks);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 TemporalOperations.java
java TemporalOperations
```

Stdout:

```text
original=2024-02-20
first=2024-02-01
monthEnd=2024-02-29
nextWeek=2024-02-27
monthThenDay=2024-03-01
dayThenMonth=2024-02-29
adjustedDateTime=2024-03-01T10:15
PASS checks=24
```

Các hàm kiểm tra chủ động ném `AssertionError` khi sai nên không cần cờ `-ea`. Hàm `rejects` không bỏ qua mọi ngoại lệ: nó xác nhận đúng lớp lỗi mong muốn, và làm chương trình thất bại nếu lời gọi không báo lỗi.

Những bằng chứng cần đọc từ ví dụ:

- `first.getClass()` là `LocalDate.class` dù biến `first` được khai báo `Temporal`.
- Gọi `plus` mà bỏ kết quả không làm biến `value` đổi ngày.
- Quy tắc đầu tháng tiếp theo giữ 10:15 khi áp vào `LocalDateTime`.
- `LocalTime` không áp dụng được quy tắc cần ngày trong tháng.
- `LocalDate` không cộng được giờ hoặc `Duration.ofDays(1)`.
- Kiểm tra hỗ trợ đơn vị trong `shift` không thay thế việc kiểm tra giá trị hợp lệ của một trường.

## 10. Lỗi phổ biến và cách tránh

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Dùng `with(DAY_OF_MONTH, 1)` để tăng một ngày | Đây là đặt trường thành 1 | Dùng `plus(1, DAYS)` |
| Bỏ giá trị trả về | Các kiểu chuẩn bất biến | Gán lại hoặc trả kết quả cho bên gọi |
| Dùng `Temporal` rồi gọi `plusDays` | Phương thức không thuộc giao diện | Dùng `plus(amount, DAYS)`, hoặc giữ kiểu `LocalDate` |
| Cho rằng giao diện giúp `LocalDate` cộng giờ | Kiểu thực tế vẫn thiếu phần giờ | Chọn `LocalDateTime` nếu miền yêu cầu ngày và giờ |
| Trả `LocalDate` từ adjuster nhận `LocalDateTime` | Vi phạm hợp đồng giữ kiểu, mất giờ | Điều chỉnh qua đầu vào và giữ kiểu của nó |
| Ép cùng một adjuster vào mọi `Temporal` | Không phải kiểu nào cũng có trường cần thiết | Công bố kiểu/khả năng cần có |
| Bắt mọi `RuntimeException` rồi trả đầu vào | Che cả lỗi quy tắc và tràn số | Xử lý loại lỗi có chủ đích hoặc để lỗi truyền ra |
| Đổi thứ tự chuỗi vì cho rằng tương đương | Mỗi bước phụ thuộc ngày của bước trước | Viết ca kiểm tra phân biệt hai thứ tự |

## 11. Thực hành kiểm tra sự hiểu đúng

1. **Đổi ngày gốc thành `2024-12-20` rồi áp `FIRST_OF_NEXT_MONTH`.** Kết quả phải là `2025-01-01`. Đây là ca kiểm tra việc quy tắc đi qua ranh giới năm.

2. **Áp cùng quy tắc vào `2024-12-20T23:45`.** Kết quả phải là `2025-01-01T23:45`. Phần giờ được giữ; không chuyển đầu vào thành `LocalDate` giữa chừng.

3. **Nhận kết quả từ `shift` trong biến `Temporal`.** Giải thích vì sao không thể gọi `getYear()` trực tiếp trên biến đó dù đối tượng thực tế là `LocalDate`: trình biên dịch chỉ cho dùng hợp đồng của kiểu khai báo.

4. **Thử đặt ngày 30 trong tháng 2/2024.** `isSupported(DAY_OF_MONTH)` vẫn đúng, nhưng thao tác phải báo lỗi giá trị ngày không hợp lệ. Phân biệt “có hỗ trợ trường” với “có chấp nhận giá trị”.

5. **Thiết kế hàm chỉ dành cho hạn thanh toán theo ngày ISO.** Nếu đầu vào/đầu ra luôn là `LocalDate`, hãy dùng chữ ký cụ thể. Chỉ mở rộng sang `Temporal` khi có nhu cầu xử lý nhiều kiểu và đã xác định rõ các khả năng bắt buộc.

Khi đọc một lời gọi qua `Temporal`, hãy kiểm tra bốn điều: overload nào được chọn, kiểu thực tế có hỗ trợ thao tác không, kết quả có được giữ lại không, và thứ tự thao tác có đúng quy tắc cần thực hiện không.
