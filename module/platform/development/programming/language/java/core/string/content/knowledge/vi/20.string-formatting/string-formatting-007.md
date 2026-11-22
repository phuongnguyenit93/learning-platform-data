# Đối số `null` và các `IllegalFormatException` thường gặp trong Java

## Mục tiêu

Sau bài này, bạn có thể dự đoán cách `String.format()` xử lý đối số `null`, phân biệt lỗi do giá trị đối số với lỗi do chuỗi định dạng, nhận diện các ngoại lệ định dạng thường gặp và chọn cách xử lý thích hợp khi tạo thông báo, log hoặc chuỗi hiển thị.

## 1. Vì sao định dạng chuỗi có thể thất bại?

`String.format()`, `System.out.printf()`, `Formatter.format()` và `String.formatted()` sử dụng các quy tắc của `java.util.Formatter`. Một đặc tả thường có dạng:

```text
%[argument_index$][flags][width][.precision]conversion
```

Ví dụ: `%2$-10.3s` lấy đối số thứ hai, canh trái trong độ rộng tối thiểu 10 và lấy tối đa 3 ký tự chuỗi. `%d` dành cho số nguyên, `%f` dành cho số thực, `%s` biểu diễn chuỗi của đối tượng, `%b` biểu diễn logic; `%tY` định dạng năm của giá trị ngày/giờ. Hai đặc tả `%%` (ký tự phần trăm) và `%n` (dấu xuống dòng theo nền tảng) không tiêu thụ đối số.

`Formatter` kiểm tra cú pháp, cờ, độ rộng, độ chính xác, chỉ số đối số và tính tương thích của kiểu dữ liệu. Nếu không hợp lệ, nó ném một lớp con của `IllegalFormatException` (ngoại lệ unchecked, thuộc họ `IllegalArgumentException`). Trường hợp riêng là chuỗi format bằng `null`: ví dụ `String.format((String) null, "x")` ném `NullPointerException`, không phải `IllegalFormatException`.

## 2. Đối số `null`: kết quả cụ thể

Một hiểu lầm phổ biến là mọi đối số `null` đều gây `NullPointerException` hoặc `IllegalFormatConversionException`. Theo đặc tả `Formatter`, đối với các phép chuyển đổi tổng quát, ký tự, số và ngày/giờ, `null` thường được biểu diễn bằng chữ `null`; `%b`/`%B` là ngoại lệ đáng chú ý vì `null` được biểu diễn thành `false`/`FALSE`.

| Đặc tả | Đối số thực sự là `null` | Kết quả |
| --- | --- | --- |
| `%s` / `%S` | `(Object) null` | `null` / `NULL` |
| `%b` / `%B` | `(Object) null` | `false` / `FALSE` |
| `%h` / `%H` | `(Object) null` | `null` / `NULL` |
| `%d`, `%f`, `%c`, `%tY` | `(Object) null` | `null` |

Ví dụ đầy đủ, chạy được trên Java 17+:

```java
import java.util.Locale;

public class FormatterNullDemo {
    public static void main(String[] args) {
        Object absent = null;

        System.out.println("string=[" + String.format(Locale.ROOT, "%s", absent) + "]");
        System.out.println("boolean=[" + String.format(Locale.ROOT, "%b", absent) + "]");
        System.out.println("hash=[" + String.format(Locale.ROOT, "%h", absent) + "]");
        System.out.println("integer=[" + String.format(Locale.ROOT, "%d", absent) + "]");
        System.out.println("decimal=[" + String.format(Locale.ROOT, "%f", absent) + "]");
        System.out.println("char=[" + String.format(Locale.ROOT, "%c", absent) + "]");
        System.out.println("year=[" + String.format(Locale.ROOT, "%tY", absent) + "]");
        System.out.println("uppercase=[" + String.format(Locale.ROOT, "%S", absent) + "]");
    }
}
```

Lưu dưới tên `FormatterNullDemo.java`, rồi chạy:

```bash
javac FormatterNullDemo.java
java FormatterNullDemo
```

Kết quả:

```text
string=[null]
boolean=[false]
hash=[null]
integer=[null]
decimal=[null]
char=[null]
year=[null]
uppercase=[NULL]
```

Cần phân biệt ba điều:

- `null` **không phải** một số nguyên, số thực hay ngày hợp lệ; `Formatter` dùng quy tắc biểu diễn đặc biệt cho giá trị vắng mặt. Giá trị **khác `null` nhưng sai kiểu** vẫn có thể gây lỗi: `String.format("%d", "42")` ném `IllegalFormatConversionException` vì `"42"` là `String`, không phải kiểu số nguyên được `%d` chấp nhận.
- `%b` không thực hiện ép kiểu chuỗi sang boolean. Với đối số `Boolean.TRUE`, kết quả là `true`; với `Boolean.FALSE` hoặc `null`, kết quả là `false`; **mọi đối tượng khác `null` mà không thuộc kiểu `Boolean`** cũng được biểu diễn thành `true`. Vì vậy `String.format("%b", "false")` cho ra `true`.
- `null` có thể che giấu dữ liệu bị thiếu. Ví dụ một cột số tiền hiển thị `null` hoặc cờ tùy chọn hiển thị `false` không chứng minh dữ liệu nguồn hợp lệ.

### Lưu ý varargs: `null` đơn lẻ và mảng đối số `null`

Chữ ký `String.format(String format, Object... args)` sử dụng varargs. Khi cần **một đối số** có giá trị `null`, viết rõ `(Object) null` hoặc truyền một biến `Object` bằng `null`:

```java
String oneNull = String.format("%s", (Object) null);
String twoNulls = String.format("%s|%s", (Object[]) null);
```

`oneNull` là `"null"`. Trong `Formatter`, mảng varargs `null` ở ví dụ thứ hai được xử lý như các đối số đều `null`, nên `twoNulls` là `"null|null"`. Dù kết quả trông tương tự, **`(Object) null` và `(Object[]) null` không biểu đạt cùng một ý định ở cấp lời gọi**. Viết `String.format("%s", null)` trực tiếp có thể tạo cảnh báo của trình biên dịch về lời gọi varargs không rõ ràng; ép kiểu hoặc dùng biến rõ ràng giúp loại bỏ sự nhập nhằng.

## 3. Nhận diện các `IllegalFormatException` thường gặp

Các lớp dưới đây thuộc `java.util`; tên lớp con thường cho biết phần nào của đặc tả sai. Bảng dùng các ví dụ cố ý thất bại, độc lập với nhau.

| Ngoại lệ | Ví dụ | Nguyên nhân và hướng sửa |
| --- | --- | --- |
| `IllegalFormatConversionException` | `String.format("%d", "42")` | Chuyển đổi không chấp nhận kiểu đối số; đổi sang số `42` hoặc sử dụng `%s`. |
| `MissingFormatArgumentException` | `String.format("%s %s", "A")` | Đặc tả cần thêm đối số; truyền đủ hoặc sửa số placeholder. |
| `UnknownFormatConversionException` | `String.format("%q", 1)` | `q` không phải ký tự chuyển đổi hợp lệ; dùng `%s` hoặc loại hợp lệ khác. |
| `FormatFlagsConversionMismatchException` | `String.format("%#s", "A")` | Cờ `#` không được hỗ trợ cho `%s` với `String` thông thường; bỏ cờ. |
| `DuplicateFormatFlagsException` | `String.format("%--5s", "A")` | Cờ `-` bị lặp; đổi thành `%-5s`. |
| `IllegalFormatFlagsException` | `String.format("%-05d", 42)` | Hai cờ `-` và `0` xung đột; chỉ dùng một cách căn chỉnh. |
| `MissingFormatWidthException` | `String.format("%0d", 42)` | Cờ `0` cần độ rộng; ví dụ dùng `%05d`. |
| `IllegalFormatPrecisionException` | `String.format("%.2d", 42)` | `%d` không hỗ trợ precision; dùng `%d` hoặc tự định dạng giá trị trước. |
| `IllegalFormatWidthException` | `String.format("%5n")` | `%n` không chấp nhận width; dùng `%n`. |
| `IllegalFormatCodePointException` | `String.format("%c", 0x110000)` | Mã Unicode nằm ngoài phạm vi code point hợp lệ; kiểm tra bằng `Character.isValidCodePoint()`. |

Không nên cho rằng tên lớp ngoại lệ luôn thể hiện mọi chi tiết nguyên nhân: cùng một chuỗi định dạng có thể mắc nhiều lỗi và `Formatter` sẽ báo lỗi đầu tiên theo quá trình kiểm tra của nó. `IllegalFormatException` cũng có các lớp con ít gặp hơn như `UnknownFormatFlagsException`; không cần tự tạo các lớp ngoại lệ này khi chỉ định dạng chuỗi.

### Chạy thử và đọc đúng tên ngoại lệ

```java
import java.util.IllegalFormatException;
import java.util.List;
import java.util.Locale;

public class FormatErrorsDemo {
    private record Sample(String label, String format, Object[] args) {}

    public static void main(String[] args) {
        List<Sample> examples = List.of(
                new Sample("wrong-type", "%d", new Object[]{"42"}),
                new Sample("missing-arg", "%s %s", new Object[]{"A"}),
                new Sample("unknown-conversion", "%q", new Object[]{1}),
                new Sample("flag-mismatch", "%#s", new Object[]{"A"}),
                new Sample("duplicate-flag", "%--5s", new Object[]{"A"}),
                new Sample("conflicting-flags", "%-05d", new Object[]{42}),
                new Sample("missing-width", "%0d", new Object[]{42}),
                new Sample("invalid-precision", "%.2d", new Object[]{42}),
                new Sample("invalid-width", "%5n", new Object[]{}),
                new Sample("invalid-codepoint", "%c", new Object[]{0x110000})
        );

        for (Sample example : examples) {
            try {
                String.format(Locale.ROOT, example.format(), example.args());
                System.out.println(example.label() + " => OK");
            } catch (IllegalFormatException error) {
                System.out.println(example.label() + " => "
                        + error.getClass().getSimpleName());
            }
        }
    }
}
```

Lưu thành `FormatErrorsDemo.java`, biên dịch và chạy:

```bash
javac FormatErrorsDemo.java
java FormatErrorsDemo
```

Kết quả xác định:

```text
wrong-type => IllegalFormatConversionException
missing-arg => MissingFormatArgumentException
unknown-conversion => UnknownFormatConversionException
flag-mismatch => FormatFlagsConversionMismatchException
duplicate-flag => DuplicateFormatFlagsException
conflicting-flags => IllegalFormatFlagsException
missing-width => MissingFormatWidthException
invalid-precision => IllegalFormatPrecisionException
invalid-width => IllegalFormatWidthException
invalid-codepoint => IllegalFormatCodePointException
```

Chương trình trên chỉ bắt `IllegalFormatException` để phục vụ việc học. Trong ứng dụng thực tế, thường nên sửa chuỗi format ngay tại nơi viết code; không nên bắt rộng rồi âm thầm nuốt ngoại lệ khiến dữ liệu sai tiếp tục đi qua hệ thống.

## 4. Lỗi do đếm và chọn đối số

Chú ý `%s`, `%d`, `%f` đều tiêu thụ đối số; `%%` và `%n` thì không. `Formatter` có ba cách chọn đối số:

- **Tuần tự**: `"%s %d"` lần lượt dùng đối số 1 và 2.
- **Theo vị trí**: `"%2$s %1$s"` lấy đối số thứ hai trước, rồi thứ nhất; thứ tự chỉ số bắt đầu từ 1.
- **Tái dùng đối số trước**: `"%s %<s"` dùng một đối số hai lần; `%<s` đứng đầu, khi chưa có đối số trước đó, gây `MissingFormatArgumentException`.

`String.format("%s", "A", "B")` chỉ cho ra `"A"`: đối số thừa bị bỏ qua, **không** gây ngoại lệ. Ngược lại, `String.format("%2$s", "A")` ném `MissingFormatArgumentException` vì chỉ số thứ hai không tồn tại. Việc truyền `null` và việc **không truyền đủ đối số** là hai tình huống khác nhau; chỉ tình huống thứ hai tạo lỗi thiếu đối số.

Khi kiểm tra thông báo nhiều placeholder, hãy ghi số lượng, kiểu dữ liệu và chỉ số của từng đối số rồi so sánh với đặc tả. Nếu cần dấu `%` trong lời văn, dùng `%%`; nếu cần kết thúc dòng theo nền tảng, dùng `%n`; nếu đầu ra yêu cầu LF cố định, dùng ký tự `\n` trong chuỗi Java.

## 5. Cách xử lý an toàn trong code thực tế

### Xác định chính sách khi dữ liệu có thể `null`

Nếu `null` không hợp lệ về nghiệp vụ, kiểm tra nó trước khi định dạng thay vì để `Formatter` in chữ `null`:

```java
import java.util.Locale;
import java.util.Objects;

public class RequiredAmount {
    public static String label(Integer amount) {
        int present = Objects.requireNonNull(amount, "amount is required");
        return String.format(Locale.ROOT, "Amount: %d", present);
    }
}
```

Đây là phương thức minh họa (không có `main`). `Objects.requireNonNull` báo lỗi sớm bằng `NullPointerException` có thông điệp rõ ràng; nó thể hiện yêu cầu **bắt buộc có dữ liệu**, khác với một lỗi cú pháp format. Nếu `null` là trạng thái hợp lệ, hãy biểu diễn nó một cách có chủ đích:

```java
import java.util.Locale;

public class OptionalAmount {
    public static String label(Integer amount) {
        return amount == null
                ? "Amount: chưa có dữ liệu"
                : String.format(Locale.ROOT, "Amount: %d", amount);
    }
}
```

Nếu cần chuỗi từ một đối tượng bất kỳ, `String.valueOf(value)` cũng trả về `"null"` khi `value == null`; chỉ dùng nó khi biểu diễn ấy thực sự phù hợp. Với cờ logic ba trạng thái (`true`, `false`, `null`), không sử dụng `%b` để bảo toàn phân biệt giữa "chưa biết" và `false`.

### Giữ chuỗi định dạng cố định và đúng kiểu

Thay vì coi dữ liệu nhập từ bên ngoài là chính chuỗi format:

```java
// Dữ liệu nhập là nội dung, không phải cú pháp định dạng.
String userText = "giảm 20%";
String message = String.format(Locale.ROOT, "Ghi chú: %s", userText);
```

`message` là `"Ghi chú: giảm 20%"`. `%s` sẽ không diễn giải ký tự `%` bên trong `userText` thành placeholder mới. Cách này dễ kiểm soát hơn so với dùng `userText` như đối số `format`, vốn có thể dẫn tới placeholder ngoài ý muốn hoặc ngoại lệ nếu đầu vào chứa `%`.

Ưu tiên constant hoặc chuỗi format có thể kiểm tra bằng test. Dùng `Locale.ROOT`/`Locale.US` khi muốn đầu ra ổn định; dùng `Locale` thực tế của người dùng cho văn bản hiển thị có định dạng số/ngày theo vùng. Nhớ rằng `%f` áp dụng cho kiểu số thực phù hợp, trong khi `%d` áp dụng cho kiểu số nguyên phù hợp; `Formatter` không tự parse `"42"` thành số.

### Xử lý ngoại lệ ở ranh giới thích hợp

Trong thư viện tạo nội dung động thực sự phải nhận mẫu format từ cấu hình, có thể bắt `IllegalFormatException` tại ranh giới nhận cấu hình để trả về lỗi có ngữ cảnh (mẫu format, danh sách kiểu đối số, vị trí cấu hình). Tránh ghi nội dung nhạy cảm của đối số vào log. Khi lỗi phát sinh từ chuỗi format hard-code, sửa tại nguồn và bổ sung kiểm thử tốt hơn là dùng `catch` để tự động thay bằng `"null"`.

## 6. Những nhầm lẫn cần tránh

1. **“`%d` gặp `null` sẽ luôn ném `IllegalFormatConversionException`.”** Sai: `null` được biểu diễn thành `"null"`; đối số **khác null nhưng không tương thích** như `"42"` mới gây ngoại lệ này.
2. **“`%b` sẽ parse chuỗi `"false"`.”** Sai: mọi đối tượng không phải `Boolean`, nếu khác `null`, đều dẫn đến `true`.
3. **“Thêm đối số thừa sẽ gây lỗi.”** Sai: đối số không được tham chiếu bị bỏ qua, có thể khiến lỗi logic khó phát hiện.
4. **“`%n` và `%%` mỗi cái cần một đối số.”** Sai: chúng không tiêu thụ đối số.
5. **“`%.2d` có nghĩa là in số nguyên với hai chữ số.”** Sai: precision không áp dụng cho `%d`; `%02d` mới yêu cầu độ rộng tối thiểu 2 và đệm bằng số 0.
6. **“Bắt `IllegalFormatException` sẽ bắt mọi lỗi format.”** Sai: ví dụ format string bằng `null` gây `NullPointerException`; các lỗi khác của code cũng không nhất thiết thuộc họ ngoại lệ này.

## 7. Tự kiểm tra

Dự đoán đầu ra hoặc ngoại lệ của mỗi lời gọi sau, rồi kiểm chứng với `jshell`:

```java
String.format("%s", (Object) null)
String.format("%b", "false")
String.format("%d", (Object) null)
String.format("%d", "12")
String.format("%s %s", "A")
String.format("%2$s-%1$s", "A", "B")
String.format("100%% %s", "OK")
String.format("%05d", 42)
```

Đáp án theo thứ tự: `"null"`; `"true"`; `"null"`; `IllegalFormatConversionException`; `MissingFormatArgumentException`; `"B-A"`; `"100% OK"`; `"00042"`.

Tài liệu chuẩn để tra cứu thêm: [`java.util.Formatter` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Formatter.html) và [`java.util.IllegalFormatException` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IllegalFormatException.html).
