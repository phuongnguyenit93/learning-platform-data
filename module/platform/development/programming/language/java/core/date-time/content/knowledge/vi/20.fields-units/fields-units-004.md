# get(), getLong(), range() và giới hạn của trường

## 1. Một đối tượng ngày giờ cung cấp những trường nào?

Một **trường thời gian** (`TemporalField`) là một thông tin có thể đọc dưới dạng số: năm, tháng, ngày trong tháng, giờ trong ngày hoặc số ngày tính từ mốc. `ChronoField` chứa các trường chuẩn như `YEAR`, `MONTH_OF_YEAR`, `DAY_OF_MONTH` và `EPOCH_DAY`.

Ví dụ, trong `LocalDate.of(2024, 2, 29)`:

| Trường | Ý nghĩa | Giá trị |
| --- | --- | --- |
| `YEAR` | Năm theo lịch ISO mở rộng | `2024` |
| `MONTH_OF_YEAR` | Tháng trong năm | `2` |
| `DAY_OF_MONTH` | Ngày trong tháng | `29` |
| `EPOCH_DAY` | Số ngày tính từ ngày 01/01/1970 của lịch ISO | `19782` |

`DAY_OF_MONTH` không phải số ngày đã trôi qua từ một mốc; `EPOCH_DAY` không phải ngày thứ bao nhiêu trong tháng. Cùng kiểu trả về là số không có nghĩa là cùng cách diễn giải.

`TemporalAccessor` là giao diện đọc thông tin này. Nhiều kiểu quen thuộc như `LocalDate`, `LocalTime` và `YearMonth` triển khai nó. Theo [hợp đồng TemporalAccessor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/TemporalAccessor.html), `get` trả `int`, `getLong` trả `long`, còn `range` trả khoảng giá trị của trường đối với đối tượng.

Trong mã ứng dụng đã biết kiểu cụ thể, `date.getDayOfMonth()` thường dễ đọc hơn `date.get(ChronoField.DAY_OF_MONTH)`. Cách đọc qua trường hữu ích khi cần xử lý một trường được lựa chọn lúc chạy hoặc viết một thành phần chung cho nhiều kiểu ngày giờ. Không cần đổi mọi getter cụ thể sang giao diện tổng quát.

## 2. Ba câu hỏi phải tách riêng

Trước khi đọc một trường, cần phân biệt:

1. **Đối tượng có hỗ trợ trường đó không?** Dùng `isSupported(field)`.
2. **Muốn đọc bằng kiểu số nào?** Dùng `get(field)` hoặc `getLong(field)` theo hợp đồng của trường.
3. **Khoảng giá trị nào hợp lệ trong ngữ cảnh hiện tại?** Dùng `range(field)`.

Ví dụ `LocalDate` hỗ trợ ngày trong tháng nhưng không hỗ trợ giờ trong ngày. Đổi từ `get(HOUR_OF_DAY)` sang `getLong(HOUR_OF_DAY)` không tạo ra thông tin giờ còn thiếu.

Ngược lại, `LocalDate` có hỗ trợ `EPOCH_DAY`, nhưng phải đọc bằng `getLong`. `isSupported` trả `true` không bảo đảm `get` thành công vì khả năng hỗ trợ trường và khả năng biểu diễn trường qua `int` là hai điều kiện riêng.

| Trường hợp | `isSupported` | `get` | `getLong` |
| --- | --- | --- | --- |
| `LocalDate` với `DAY_OF_MONTH` | `true` | Đọc được | Đọc được |
| `LocalDate` với `EPOCH_DAY` | `true` | Không đọc được qua `int` | Đọc được |
| `LocalDate` với `HOUR_OF_DAY` | `false` | Không hỗ trợ | Không hỗ trợ |
| `LocalTime` với `NANO_OF_DAY` | `true` | Không đọc được qua `int` | Đọc được |
| `YearMonth` với `DAY_OF_MONTH` | `false` | Không hỗ trợ | Không hỗ trợ |

Bảng này nói về các kiểu chuẩn và trường `ChronoField` được nêu, không phải lời bảo đảm cho mọi hiện thực `TemporalField` tùy biến.

## 3. get(): đọc một trường theo hợp đồng int

Ví dụ ngắn sau giả sử đã có biến `date` kiểu `LocalDate`:

```java
int year = date.get(ChronoField.YEAR);
int month = date.get(ChronoField.MONTH_OF_YEAR);
int day = date.get(ChronoField.DAY_OF_MONTH);
```

`get` không thực hiện phép ép kiểu cắt bớt từ một giá trị `long` bất kỳ. Nó đọc theo hợp đồng truy cập `int` của trường. Các trường có miền giá trị rộng hơn `int` có thể bị từ chối ngay cả khi giá trị của đối tượng cụ thể đang nhỏ.

Ví dụ ngày 29/02/2024 có `EPOCH_DAY = 19782`, hoàn toàn vừa `int`. Tuy nhiên:

```java
LocalDate date = LocalDate.of(2024, 2, 29);

long epoch = date.getLong(ChronoField.EPOCH_DAY); // 19782
// date.get(ChronoField.EPOCH_DAY) se nem ngoai le.
```

`LocalDate.get(EPOCH_DAY)` ném `UnsupportedTemporalTypeException` và yêu cầu dùng `getLong`. Toàn bộ miền `EPOCH_DAY` của `LocalDate` không nằm trong miền `int`; việc một ngày hiện tại có giá trị nhỏ không thay đổi hợp đồng truy cập đó.

Tương tự, `NANO_OF_DAY` là số nano giây từ đầu ngày. Nó có thể lớn hơn rất nhiều so với `Integer.MAX_VALUE`. Ngay cả khi thời gian đang gần đầu ngày và giá trị nhỏ, hãy sử dụng `getLong(NANO_OF_DAY)` theo hợp đồng của `LocalTime`.

## 4. getLong(): miền số rộng hơn, không phải quyền truy cập rộng hơn

`getLong` là lựa chọn phù hợp khi viết bộ đọc trường tổng quát vì nhiều trường được mô hình hóa bằng `long`. Nó cũng đọc được những trường vốn vừa `int`, chẳng hạn `DAY_OF_MONTH`.

Nhưng `getLong` vẫn cần đối tượng hỗ trợ trường:

```java
LocalDate date = LocalDate.of(2024, 2, 29);

long day = date.getLong(ChronoField.DAY_OF_MONTH); // 29
// date.getLong(ChronoField.HOUR_OF_DAY) van khong hop le.
```

`LocalDate` chỉ có ngày, không có giờ. Nó cũng không tự suy ra `INSTANT_SECONDS`: để xác định một thời điểm trên dòng thời gian còn cần thông tin thích hợp về giờ và độ lệch hoặc múi giờ. Không nên hiểu `getLong` là cách “buộc” đối tượng cung cấp bất kỳ trường nào.

Nếu thực sự cần đưa một giá trị `long` vào hệ thống chỉ nhận `int`, đây phải là quyết định chuyển đổi riêng:

```java
long value = date.getLong(ChronoField.EPOCH_DAY);
int narrowed = Math.toIntExact(value);
```

`Math.toIntExact` kiểm tra **giá trị đang có**, ném `ArithmeticException` nếu vượt miền `int`. Nó không thay đổi miền giá trị của trường và không khiến `date.get(EPOCH_DAY)` trở nên hợp lệ.

Tránh `(int) value` khi không có bảo đảm miền dữ liệu: phép ép kiểu số nguyên có thể làm mất các bit cao và trả một số khác. Một lỗi đọc trường không nên được “sửa” bằng cách tạo ra giá trị bị cắt.

## 5. range(): khoảng chung và khoảng đã biết ngữ cảnh

`ValueRange` mô tả các giới hạn của một trường. Có hai nguồn khoảng thường gặp:

| Lời gọi | Câu hỏi |
| --- | --- |
| `ChronoField.DAY_OF_MONTH.range()` | Trường ngày trong tháng nói chung có giới hạn nào? |
| `date.range(ChronoField.DAY_OF_MONTH)` | Với ngày cụ thể này, giới hạn ngày trong tháng là gì? |

[ChronoField](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/ChronoField.html) định nghĩa ý nghĩa các trường chuẩn. Khoảng chung của `DAY_OF_MONTH` được in là `1 - 28/31`: cận dưới là `1`, cận trên thay đổi từ `28` đến `31` tùy tháng và năm. Đây không phải phép chia `28/31` và không phải một danh sách chỉ gồm ba số 1, 28, 31.

Với `LocalDate`, đối tượng có đủ tháng và năm để thu hẹp khoảng:

| Ngữ cảnh | `range(DAY_OF_MONTH)` |
| --- | --- |
| Tháng 02/2024, năm nhuận | `1 - 29` |
| Tháng 02/2023 | `1 - 28` |
| Tháng 04/2024 | `1 - 30` |
| Tháng 01/2024 | `1 - 31` |

Ngày đang chọn trong tháng không làm cận trên bằng chính ngày đó. Ví dụ `2024-02-01` vẫn có khoảng ngày trong tháng là `1 - 29`, vì toàn tháng 02/2024 có 29 ngày.

Với các kiểu hoặc trường khác, mức độ thu hẹp phụ thuộc thông tin mà đối tượng thực sự có và hợp đồng hiện thực. Không được mặc định `range` luôn tạo ra khoảng chính xác cho một ngày đầy đủ nếu đối tượng chưa biểu diễn ngày đó.

### 5.1. Các phương thức đọc giới hạn

Với `ValueRange range`:

- `getMinimum()`: cận dưới nhỏ nhất.
- `getLargestMinimum()`: cận dưới lớn nhất có thể có khi cận dưới thay đổi.
- `getSmallestMaximum()`: cận trên nhỏ nhất có thể có.
- `getMaximum()`: cận trên lớn nhất.
- `isFixed()`: cận dưới và cận trên đều đã cố định.

Đối với khoảng chung của `DAY_OF_MONTH`, hai cận dưới đều là `1`; cận trên nhỏ nhất là `28`, lớn nhất là `31`; `isFixed()` là `false`. Với khoảng đã thu hẹp cho tháng 02/2024, hai cận trên đều là `29` nên `isFixed()` là `true`.

`isFixed()` không hỏi đối tượng có bất biến hay không. Cả một khoảng có cận trên thay đổi và một khoảng cố định đều là các giá trị `ValueRange` bất biến; phương thức này chỉ mô tả cấu trúc của khoảng.

### 5.2. Kiểm tra một giá trị và kiểm tra miền int

[ValueRange](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/ValueRange.html) cung cấp các phép kiểm tra có chủ đích khác nhau:

| Phương thức | Ý nghĩa |
| --- | --- |
| `isValidValue(value)` | Giá trị có nằm giữa các cận ngoài của khoảng không? |
| `checkValidValue(value, field)` | Kiểm tra như trên; trả `long` hoặc ném lỗi |
| `isIntValue()` | Toàn bộ khoảng có nằm trong miền `int` không? |
| `isValidIntValue(value)` | Khoảng phù hợp với `int` và giá trị nằm trong khoảng không? |
| `checkValidIntValue(value, field)` | Kiểm tra hợp đồng `int` nói trên; trả `int` hoặc ném lỗi |

Điểm dễ nhầm: `isValidIntValue` không chỉ kiểm tra bản thân số đó có vừa `int` không. Nó còn yêu cầu `isIntValue()` của cả khoảng là `true`.

Vì thế, đối với `EPOCH_DAY` của ngày 29/02/2024:

- `range.isValidValue(19782)` là `true`.
- `range.isIntValue()` là `false`.
- `range.isValidIntValue(19782)` là `false`.
- `Math.toIntExact(19782L)` vẫn thành công vì đó là kiểm tra chuyển đổi của một giá trị riêng lẻ.

Tham số `field` trong `checkValidValue` và `checkValidIntValue` giúp mô tả lỗi theo trường; nó không tự bổ sung một tháng hoặc năm để thu hẹp khoảng. Phải lấy đúng `ValueRange` trước khi kiểm tra.

## 6. Chương trình Java 17+ đầy đủ

Lưu tệp thành `TemporalFieldReadDemo.java`:

```java
import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.YearMonth;
import java.time.temporal.ChronoField;
import java.time.temporal.TemporalAccessor;
import java.time.temporal.ValueRange;
import java.util.function.LongSupplier;

public class TemporalFieldReadDemo {
    static void attempt(String label, LongSupplier operation) {
        try {
            System.out.println(label + " = " + operation.getAsLong());
        } catch (DateTimeException ex) {
            System.out.println(label + " -> "
                    + ex.getClass().getSimpleName());
        }
    }

    static void describe(TemporalAccessor temporal, ChronoField field) {
        if (!temporal.isSupported(field)) {
            System.out.println(field + " = unsupported");
            return;
        }
        System.out.println(field + " = " + temporal.getLong(field)
                + "; range=" + temporal.range(field));
    }

    public static void main(String[] args) {
        LocalDate leap = LocalDate.of(2024, 2, 29);
        ValueRange general = ChronoField.DAY_OF_MONTH.range();
        ValueRange refined = leap.range(ChronoField.DAY_OF_MONTH);

        System.out.println("day = " + leap.get(ChronoField.DAY_OF_MONTH));
        System.out.println("epoch supported = "
                + leap.isSupported(ChronoField.EPOCH_DAY));
        attempt("epoch getLong", () -> leap.getLong(ChronoField.EPOCH_DAY));
        attempt("epoch get", () -> leap.get(ChronoField.EPOCH_DAY));
        attempt("hour getLong", () -> leap.getLong(ChronoField.HOUR_OF_DAY));

        System.out.println("general day range = " + general);
        System.out.println("leap day range = " + refined);
        System.out.println("common February range = "
                + LocalDate.of(2023, 2, 1).range(ChronoField.DAY_OF_MONTH));
        System.out.println("April range = "
                + LocalDate.of(2024, 4, 1).range(ChronoField.DAY_OF_MONTH));
        System.out.println("general fixed = " + general.isFixed());
        System.out.println("refined fixed = " + refined.isFixed());
        System.out.println("general accepts 31 = " + general.isValidValue(31));
        System.out.println("refined accepts 31 = " + refined.isValidValue(31));

        ValueRange epochRange = leap.range(ChronoField.EPOCH_DAY);
        long epoch = leap.getLong(ChronoField.EPOCH_DAY);
        System.out.println("epoch range fits int = " + epochRange.isIntValue());
        System.out.println("epoch valid as long = "
                + epochRange.isValidValue(epoch));
        System.out.println("epoch valid for int range = "
                + epochRange.isValidIntValue(epoch));
        System.out.println("explicit exact narrowing = "
                + Math.toIntExact(epoch));

        LocalTime time = LocalTime.of(12, 34, 56, 789);
        attempt("nano getLong", () -> time.getLong(ChronoField.NANO_OF_DAY));
        attempt("nano get", () -> time.get(ChronoField.NANO_OF_DAY));

        YearMonth month = YearMonth.of(2024, 2);
        describe(month, ChronoField.MONTH_OF_YEAR);
        describe(month, ChronoField.DAY_OF_MONTH);
        System.out.println("month length = " + month.lengthOfMonth());
        System.out.println("original date = " + leap);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 TemporalFieldReadDemo.java
java TemporalFieldReadDemo
```

Stdout:

```text
day = 29
epoch supported = true
epoch getLong = 19782
epoch get -> UnsupportedTemporalTypeException
hour getLong -> UnsupportedTemporalTypeException
general day range = 1 - 28/31
leap day range = 1 - 29
common February range = 1 - 28
April range = 1 - 30
general fixed = false
refined fixed = true
general accepts 31 = true
refined accepts 31 = false
epoch range fits int = false
epoch valid as long = true
epoch valid for int range = false
explicit exact narrowing = 19782
nano getLong = 45296000000789
nano get -> UnsupportedTemporalTypeException
MonthOfYear = 2; range=1 - 12
DayOfMonth = unsupported
month length = 29
original date = 2024-02-29
```

Chương trình bắt `DateTimeException` trong hàm `attempt` để quan sát các lần đọc không hợp lệ mà vẫn chạy những ví dụ tiếp theo. Nó chỉ in tên lớp ngoại lệ; không phụ thuộc nguyên văn thông báo lỗi của một bản JDK.

Hàm `describe` kiểm tra hỗ trợ trước, sau đó đọc `getLong` và `range`. Nếu trường không được hỗ trợ, nó ghi rõ trạng thái, không thay giá trị bằng `0`. Số `0` có thể là giá trị hợp lệ của nhiều trường, nên dùng nó để biểu diễn “không có thông tin” sẽ làm mất phân biệt.

Dòng cuối cho thấy ngày ban đầu vẫn là `2024-02-29`. Đọc trường và đọc khoảng không sửa đối tượng.

## 7. Giới hạn của range(): không thay thế mọi phép xác thực

### 7.1. Khoảng chung chưa đủ để xác thực một ngày

Giả sử đang xử lý dữ liệu `year = 2024`, `month = 2` và `day = 31`. Khoảng chung của `DAY_OF_MONTH` chấp nhận `31` vì có những tháng dài 31 ngày. Điều đó không làm `2024-02-31` thành ngày hợp lệ.

Nếu đã có `LocalDate` đại diện cho tháng đang quan tâm, dùng khoảng đã thu hẹp của nó. Nếu đang nhận ba thành phần từ bên ngoài, có thể để `LocalDate.of(year, month, day)` kiểm tra tính hợp lệ của tổ hợp. Không nên tự coi việc từng trường vượt qua khoảng chung là bằng chứng toàn bộ ngày hợp lệ.

Việc kiểm tra còn phụ thuộc thứ tự và ngữ cảnh. Một biểu mẫu đang chọn tháng 01 có thể cho phép ngày 31; khi người dùng đổi sang tháng 02, phải cập nhật giới hạn hoặc báo đầu vào không hợp lệ. Khoảng gắn với ngữ cảnh cũ không tự cập nhật theo biến khác.

### 7.2. Có thông tin để suy ra độ dài tháng chưa có nghĩa là hỗ trợ ngày trong tháng

`YearMonth.of(2024, 2)` biết tháng đó dài 29 ngày qua `lengthOfMonth()`. Tuy nhiên, nó không chứa một ngày trong tháng đang được chọn; `DAY_OF_MONTH` không phải trường được `YearMonth` hỗ trợ để truy cập.

Vì vậy, `month.get(DAY_OF_MONTH)`, `month.getLong(DAY_OF_MONTH)` và `month.range(DAY_OF_MONTH)` đều không phải cách phù hợp để lấy thông tin đó. Dùng `lengthOfMonth()` nếu cần số ngày; dùng `month.atDay(day)` nếu cần tạo một ngày cụ thể có kiểm tra hợp lệ.

Đây là lý do phải đọc hợp đồng của kiểu, không chỉ suy luận “có năm và tháng thì chắc chắn đọc được mọi trường ngày”.

### 7.3. Khoảng số không diễn tả mọi quy tắc nghiệp vụ

Một trường tùy biến có thể chỉ chấp nhận một vài giá trị rời rạc trong khoảng cận dưới–cận trên. `ValueRange` mô tả các cận, không lưu đầy đủ mọi giá trị bị loại ở giữa. Tương tự, khoảng `DAY_OF_MONTH` không nói ngày đó có phải ngày nghỉ hay có được phép đặt lịch hay không.

Kiểm tra khoảng trả lời một phần của bài toán hợp lệ. Ràng buộc giữa nhiều trường, quy tắc của lịch cụ thể và quy tắc nghiệp vụ vẫn cần phép kiểm tra tương ứng.

### 7.4. Miền số và ý nghĩa lịch không được tách rời

Hai số năm có thể thuộc hai hệ lịch khác nhau; `YEAR` và `YEAR_OF_ERA` cũng không hoàn toàn thay thế nhau. Một hàm nhận `TemporalAccessor` tổng quát nên nêu rõ nó mong đợi kiểu/lịch nào khi điều đó ảnh hưởng nghiệp vụ.

Không cần đưa mọi thông tin thành một `Map<TemporalField, Long>` rồi bỏ mất kiểu gốc. Trong nhiều tình huống, giữ `LocalDate` hoặc `YearMonth` ở biên của hàm giúp biểu đạt rõ đầu vào có đủ thông tin gì.

## 8. Ngoại lệ và cách xử lý có ý nghĩa

Với các kiểu chuẩn đã dùng:

| Tình huống | Hành vi điển hình |
| --- | --- |
| `LocalDate.getLong(HOUR_OF_DAY)` | `UnsupportedTemporalTypeException` vì thiếu trường |
| `LocalDate.get(EPOCH_DAY)` | `UnsupportedTemporalTypeException` vì cần cách đọc `long` |
| Kiểm tra số vượt `ValueRange` bằng phương thức `check...` | `DateTimeException` |
| Tạo ngày không tồn tại bằng `LocalDate.of` | `DateTimeException` |
| `Math.toIntExact` với số vượt miền `int` | `ArithmeticException` |

`UnsupportedTemporalTypeException` là một lớp con của `DateTimeException`. Bắt lớp cha trong chương trình giúp tiếp tục thí nghiệm, nhưng khi thiết kế ứng dụng, không nên gom mọi lỗi thành “ngày không hợp lệ” nếu cần phân biệt lỗi lựa chọn trường với lỗi dữ liệu nhập.

Nếu người dùng được chọn trường lúc chạy, `isSupported` giúp trả trạng thái “không áp dụng với kiểu này”. Nếu một hàm đã yêu cầu chắc chắn `LocalDate` và `DAY_OF_MONTH`, việc đọc thất bại bất ngờ có thể là lỗi lập trình, không nên âm thầm che bằng một giá trị mặc định.

Với trường tùy biến, `isSupported` chỉ là bước kiểm tra hỗ trợ; việc lấy giá trị vẫn thực hiện theo hợp đồng của trường và kiểu tương ứng. Không coi nó là bảo đảm rằng mọi phép đọc tiếp theo sẽ không thể ném lỗi.

## 9. Những lỗi thường gặp

| Lỗi | Vì sao sai | Cách làm phù hợp |
| --- | --- | --- |
| Dùng `get` cho mọi trường | Có trường cần miền `long` | Dùng `getLong` khi xử lý trường tổng quát |
| Thấy `isSupported = true` rồi chắc chắn `get` chạy | Chưa xét hợp đồng `int` | Xét miền trường hoặc đọc `getLong` |
| Dùng `getLong` để đọc giờ từ `LocalDate` | Miền số rộng không tạo ra giờ | Chọn kiểu có thông tin cần đọc |
| Coi `1 - 28/31` là tháng nào cũng có 31 ngày | Đó là khoảng chung | Lấy khoảng từ ngữ cảnh cụ thể |
| Coi `range.getMaximum()` là giá trị hiện tại | Đây là giới hạn của trường | Dùng `get` hoặc `getLong` để đọc giá trị |
| Lấy `DAY_OF_MONTH.range()` rồi xác nhận 31/02 hợp lệ | Từng trường chưa kiểm tra tổ hợp | Tạo `LocalDate` hoặc dùng ngữ cảnh đúng |
| Dùng `isValidIntValue` như phép kiểm tra chuyển kiểu đơn lẻ | Phương thức còn xét cả miền khoảng | Dùng `Math.toIntExact` nếu thật sự cần chuyển giá trị |
| Gán `0` khi trường không được hỗ trợ | Có thể nhầm với giá trị hợp lệ | Biểu diễn thiếu thông tin rõ ràng |
| Dùng `range(DAY_OF_MONTH)` trên `YearMonth` | Trường này không được hỗ trợ để truy cập | Dùng `lengthOfMonth` hoặc `atDay` |

## 10. Tự kiểm chứng và thực hành

1. Đổi ngày trong ví dụ từ `2024-02-29` sang `2024-02-01`. Giá trị `get(DAY_OF_MONTH)` trở thành `1` nhưng khoảng ngày trong tháng vẫn là `1 - 29`. Giải thích sự khác nhau giữa giá trị hiện tại và giới hạn.
2. Đổi sang `2023-02-01`. Cận trên thu hẹp thành `28`. Thuật toán không cần bảng tháng do người viết tự duy trì.
3. Dùng `LocalTime.MIDNIGHT` với `NANO_OF_DAY`. Giá trị `getLong` là `0` nhưng `get` vẫn bị từ chối theo hợp đồng trường của `LocalTime`. Đây là phép thử quan trọng để bác bỏ cách hiểu “chỉ cần giá trị hiện tại nhỏ là được”.
4. So sánh `isValidValue(31)` trên khoảng chung với khoảng của tháng 02/2024. Dự đoán kết quả trước khi chạy.
5. Viết hàm nhận `TemporalAccessor` và `ChronoField`, trả giá trị `long` nếu được hỗ trợ, hoặc một trạng thái thiếu thông tin có tên rõ ràng. Thử với `LocalDate`, `LocalTime` và `YearMonth`; tránh dùng `0` làm tín hiệu lỗi.
6. Thử `ValueRange.of(0, Long.MAX_VALUE)`. So sánh `isValidValue(1)`, `isIntValue()` và `isValidIntValue(1)`. Giải thích vì sao số `1` vừa `int` nhưng phép kiểm tra thứ ba vẫn trả `false`.
7. Nhận đầu vào năm, tháng, ngày từ ba số riêng biệt và kiểm tra bằng `LocalDate.of`. So sánh với cách chỉ kiểm tra ba khoảng chung để thấy những tổ hợp mà kiểm tra rời rạc bỏ sót.

Khi đọc thông tin ngày giờ, hãy luôn giữ rõ ba điều: đối tượng có trường hay không, cách đọc số có phù hợp với miền trường hay không, và giới hạn đang dùng là giới hạn chung hay đã được thu hẹp theo ngữ cảnh.
