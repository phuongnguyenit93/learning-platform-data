# Định dạng boolean, ký tự và chuỗi

## 1. Chọn conversion theo ý nghĩa muốn hiển thị

`Formatter` và `printf` có ba nhóm conversion thường gặp khi tạo thông báo:

| Conversion | Mục đích |
| --- | --- |
| `%b`, `%B` | Tạo biểu diễn boolean theo quy tắc của formatter |
| `%c`, `%C` | Tạo biểu diễn ký tự từ kiểu ký tự hoặc mã Unicode phù hợp |
| `%s`, `%S` | Tạo biểu diễn chuỗi của đối số |

Bản chữ hoa là biến thể viết hoa của bản tương ứng. Các quy tắc này áp dụng trong `System.out.printf`, `String.format`, `Formatter.format` và các API dùng cùng cú pháp formatter.

Điều cần chú ý là **conversion không chỉ là nhãn gợi ý**. `%b` không phân tích mọi dữ liệu thành một giá trị logic; `%c` không nhận mọi kiểu trông giống ký tự; `%s` không tự biết cách in nội dung mọi cấu trúc.

Xem hợp đồng General và Character conversions trong [Formatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Formatter.html).

## 2. %b: không phải kiểm tra “đúng/sai” theo nội dung bất kỳ

Quy tắc của `%b` gồm ba trường hợp:

1. Đối số là `null` → `false`.
2. Đối số là `Boolean` → biểu diễn giá trị của Boolean đó.
3. Đối số khác null và không phải Boolean → `true`.

Trong lời gọi varargs, `boolean` nguyên thủy được đóng gói thành `Boolean`, nên `true` và `false` có kết quả như mong đợi.

| Đối số | Kết quả %b | Lý do |
| --- | --- | --- |
| `true` | `true` | Giá trị Boolean |
| `false` | `false` | Giá trị Boolean |
| `null` | `false` | Trường hợp null |
| `0` | `true` | Integer khác null |
| `"false"` | `true` | String khác null |
| `""` | `true` | Chuỗi rỗng vẫn khác null |

Ví dụ minh họa:

```java
System.out.printf(Locale.ROOT, "%b | %b%n", 0, "false");
```

Dòng in:

```text
true | true
```

Đây không phải lỗi formatter. Mẫu đã yêu cầu một phép biểu diễn có hợp đồng như trên.

### Khi nào cần tính điều kiện trước?

Nếu muốn hiển thị “số lượng bằng 0 hay không”, hãy truyền chính kết quả điều kiện:

```java
int count = 0;
System.out.printf(Locale.ROOT, "empty=%b%n", count == 0);
```

Nếu muốn hiển thị nội dung của một chuỗi nhập vào, dùng `%s` hoặc phân tích dữ liệu theo quy tắc nghiệp vụ trước. Đừng dùng `%b` với chuỗi `"false"` rồi coi kết quả là boolean đã phân tích.

Tương tự, `%b` với một danh sách khác null không nói danh sách có rỗng hay không. Hãy truyền `list.isEmpty()` nếu đó mới là điều cần biểu diễn.

## 3. %c: ký tự khác với chuỗi một ký tự

`%c` nhận:

- `char` hoặc `Character`.
- `byte`, `short`, `int` hoặc kiểu bao tương ứng, nếu giá trị là mã Unicode được chấp nhận.
- `null` theo quy tắc null của formatter.

Với một số nguyên phù hợp, formatter coi số đó là **mã ký tự**, không in biểu diễn số thập phân.

```java
System.out.printf(Locale.ROOT, "%c | %c%n", 'A', 66);
```

Dòng in:

```text
A | B
```

Số 66 tương ứng với ký tự B. Nếu muốn in `66`, chọn conversion số như `%d`, hoặc `%s` khi cần biểu diễn chuỗi thông thường của số.

Không phải mọi giá trị số đều cho một ký tự nhìn thấy. Một số mã là ký tự điều khiển. Ví dụ, truyền số 9 cho `%c` không có nghĩa in chữ số `9`; mã đó biểu diễn ký tự tab.

### Kiểu dữ liệu vẫn phải phù hợp

Hai trường hợp sau không hợp lệ:

```java
// Ví dụ lỗi: String không phải kiểu được %c chấp nhận.
String.format(Locale.ROOT, "%c", "A");

// Ví dụ lỗi: Long không nằm trong các kiểu số được %c chấp nhận.
String.format(Locale.ROOT, "%c", 65L);
```

Dù `"A"` chỉ có một ký tự, nó vẫn là `String`. Dù số 65L có giá trị trông phù hợp, nó vẫn là `long` được đóng gói thành `Long`.

### Mã Unicode và giới hạn char

Một `char` Java là một đơn vị mã UTF-16. Không phải mọi mã Unicode đều vừa trong một `char`. Khi cần biểu diễn một mã bổ sung nằm ngoài phạm vi một đơn vị char, có thể truyền mã đó dưới dạng `int` hợp lệ cho `%c`.

Giá trị ngoài miền mà `Character.isValidCodePoint(int)` chấp nhận, chẳng hạn `0x110000`, dẫn tới `IllegalFormatCodePointException`. Xem [hợp đồng ngoại lệ mã Unicode](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/IllegalFormatCodePointException.html).

Việc in ra đúng hình dạng còn phụ thuộc mã hóa của đích xuất và font. Một mã hợp lệ không tự bảo đảm terminal có glyph để hiển thị nó.

## 4. %s: biểu diễn chuỗi của đối số

Với các đối tượng thông thường:

- Nếu đối số là null, `%s` tạo `"null"`.
- Nếu đối số khác null và không triển khai cơ chế định dạng tùy chỉnh, `%s` dùng kết quả `toString()`.

Ví dụ:

```java
String text = String.format(Locale.ROOT, "name=%s, count=%s", "Lan", 7);
```

Giá trị của `text`:

```text
name=Lan, count=7
```

`%s` không chỉ nhận String. Nó cũng có thể biểu diễn số hoặc một đối tượng có `toString()` phù hợp.

Tuy nhiên, `%s` không áp dụng yêu cầu định dạng số như `%.2f`. Nếu cần luôn hai chữ số sau dấu thập phân, hãy dùng conversion số phù hợp thay vì kỳ vọng `%s` tự thêm quy tắc đó.

### Cách biểu diễn đối tượng do lớp quyết định

Một lớp có thể ghi đè `toString()`:

```java
// Mã minh họa.
final class Item {
    @Override
    public String toString() {
        return "Book#7";
    }
}
```

Khi truyền một `Item` cho `%s`, kết quả là `Book#7`.

Nếu lớp không cung cấp cách biểu diễn có ý nghĩa, output có thể chỉ là biểu diễn mặc định của đối tượng. Formatter không tự tìm tên sản phẩm, mã đơn hàng hay các trường mà ứng dụng muốn hiển thị.

### Trường hợp Formattable

Nếu đối tượng triển khai `Formattable`, conversion `s` có thể chuyển trách nhiệm định dạng sang `formatTo(Formatter, flags, width, precision)`. Vì thế không nên nói “`%s` luôn chỉ gọi `toString()`” cho mọi đối tượng.

Cơ chế này cho phép kiểu tự xử lý cờ, độ rộng và precision theo hợp đồng phù hợp. Xem [Formattable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Formattable.html). Chỉ cần biết ngoại lệ này khi đọc hoặc thiết kế kiểu có hành vi định dạng riêng; không cần triển khai nó để in một chuỗi bình thường.

## 5. Null không có cùng kết quả ở cả ba nhóm

```java
System.out.printf(Locale.ROOT, "%s | %b | %c%n", null, null, null);
```

Dòng in:

```text
null | false | null
```

Đây là hợp đồng của từng conversion, không phải phép gọi phương thức trên null nên không tự gây `NullPointerException` trong ví dụ.

Nếu muốn hiển thị dữ liệu vắng mặt bằng một nhãn khác:

```java
String displayedName = name == null ? "(missing)" : name;
System.out.printf(Locale.ROOT, "name=%s%n", displayedName);
```

Chọn nhãn thay thế là quyết định của ứng dụng. Không nên dùng `%b` chỉ để che việc dữ liệu chưa có nếu output cần phân biệt “false” với “không có giá trị”.

Khi chỉ truyền một đối số null cho một API varargs và muốn thể hiện rõ đó là **một đối số null**, có thể viết:

```java
System.out.printf(Locale.ROOT, "%s%n", (Object) null);
```

Ép kiểu như vậy giúp người đọc phân biệt với việc truyền một mảng đối số null.

## 6. Bản chữ hoa và locale

Các conversion chữ hoa yêu cầu biểu diễn viết hoa:

```java
System.out.printf(Locale.ROOT, "%B | %C | %S%n", true, 'a', "java");
```

Dòng in:

```text
TRUE | A | JAVA
```

Việc đổi hoa có thể phụ thuộc locale. Với văn bản ngôn ngữ tự nhiên, không nên giả định mọi ngôn ngữ đều có cùng quy tắc với ASCII.

`Locale.ROOT` phù hợp trong các ví dụ hoặc đầu ra kỹ thuật cần tránh phụ thuộc locale mặc định. Với giao diện ngôn ngữ cụ thể, chọn locale theo yêu cầu hiển thị.

`%S` không có nghĩa biến đối tượng gốc thành một chuỗi mới được gán lại vào biến. Nó chỉ ảnh hưởng biểu diễn được ghi ra. Tương tự, `%C` không sửa giá trị `char` nguồn.

Đối tượng triển khai `Formattable` sẽ nhận cờ tương ứng cho yêu cầu chữ hoa và phải xử lý theo hợp đồng của nó.

## 7. Width, precision và cờ phải phù hợp từng nhóm

### Chuỗi và boolean

Với các biểu diễn thông thường, width dành khoảng tối thiểu; `-` căn trái; precision giới hạn số ký tự biểu diễn:

```java
String text = String.format(Locale.ROOT, "[%8.3s]", "JavaLearning");
```

Kết quả:

```text
[     Jav]
```

Với boolean, precision áp dụng lên chữ được tạo:

```java
String text = String.format(Locale.ROOT, "[%.2b]", true);
```

Kết quả là `[tr]`. Đây không phải một boolean bị đổi thành dạng mới; đó chỉ là phần văn bản được giới hạn.

Trừ khi có yêu cầu trình bày rõ ràng, cắt `true` thành `tr` có thể làm thông báo khó hiểu.

### Ký tự

`%c` hỗ trợ căn lề và width phù hợp, nhưng không nhận precision:

```java
// Ví dụ lỗi: precision không áp dụng cho conversion ký tự.
String.format(Locale.ROOT, "%.2c", 'A');
```

Đừng dùng precision của `c` để yêu cầu “hai ký tự”. Nếu dữ liệu là một chuỗi nhiều ký tự, chọn `s`.

### Không sao chép cờ số sang chuỗi

Cờ đệm số 0 hoặc dấu số không tự có nghĩa cho mọi conversion. Ví dụ `%#s` với một String thường không phải yêu cầu thêm tiền tố và ném `FormatFlagsConversionMismatchException`.

Dấu `#` có thể có ý nghĩa cho đối tượng `Formattable` xử lý dạng thay thế, nhưng không làm String thông thường tự có dạng đó.

## 8. Ví dụ đầy đủ và output đã xác định

Tệp `GeneralFormatDemo.java`, chạy trên JDK 17 trở lên:

```java
import java.util.Arrays;
import java.util.Locale;

public class GeneralFormatDemo {
    private static final class Item {
        @Override
        public String toString() {
            return "Book#7";
        }
    }

    private static void showError(String pattern, Object value) {
        try {
            String.format(Locale.ROOT, pattern, value);
        } catch (IllegalArgumentException expected) {
            System.out.println(pattern + " -> "
                    + expected.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        System.out.printf(Locale.ROOT,
                "boolean=%b|%b|%b|%b|%b|%b%n",
                true, false, null, 0, "false", "");
        System.out.printf(Locale.ROOT,
                "null=%s|%b|%c%n", null, null, null);
        System.out.printf(Locale.ROOT,
                "characters=%c|%c|%c%n", 'A', 66, (byte) 67);
        System.out.printf(Locale.ROOT,
                "uppercase=%B|%C|%S%n", true, 'a', "java");
        System.out.printf(Locale.ROOT,
                "string=[%8.3s]%n", "JavaLearning");
        System.out.printf(Locale.ROOT,
                "booleanText=[%.2b]%n", true);
        System.out.printf(Locale.ROOT,
                "object=%s%n", new Item());
        System.out.printf(Locale.ROOT,
                "array=%s%n", Arrays.toString(new int[]{1, 2, 3}));

        showError("%c", "A");
        showError("%c", 65L);
        showError("%c", 0x110000);
        showError("%.2c", 'A');
        showError("%#s", "Java");
    }
}
```

Biên dịch và chạy:

```shell
javac GeneralFormatDemo.java
java GeneralFormatDemo
```

Kết quả:

```text
boolean=true|false|false|true|true|true
null=null|false|null
characters=A|B|C
uppercase=TRUE|A|JAVA
string=[     Jav]
booleanText=[tr]
object=Book#7
array=[1, 2, 3]
%c -> IllegalFormatConversionException
%c -> IllegalFormatConversionException
%c -> IllegalFormatCodePointException
%.2c -> IllegalFormatPrecisionException
%#s -> FormatFlagsConversionMismatchException
```

Ba lần lỗi `%c` có nguyên nhân khác nhau:

1. Đưa String `"A"`: sai kiểu.
2. Đưa Long `65L`: sai kiểu.
3. Đưa Integer ngoài miền mã Unicode: kiểu có thể dùng nhưng giá trị không hợp lệ.

Phương thức `showError` chỉ dùng trong minh họa để thấy loại lỗi rồi tiếp tục chương trình. Với mẫu cố định của ứng dụng, cần sửa lỗi định dạng và có kiểm tra kết quả mong đợi.

## 9. Mảng và varargs: đừng nhầm nội dung với đối tượng chứa nội dung

Truyền `int[]` trực tiếp cho `%s` không yêu cầu formatter duyệt từng phần tử. Mảng dùng biểu diễn đối tượng của nó.

Để in nội dung mảng số:

```java
int[] values = {1, 2, 3};
System.out.printf(Locale.ROOT, "%s%n", Arrays.toString(values));
```

Dòng in:

```text
[1, 2, 3]
```

Với mảng nhiều chiều hoặc cấu trúc mảng lồng phù hợp, `Arrays.deepToString` giúp biểu diễn nội dung lồng nhau thay vì chỉ các tham chiếu mảng. Xem [Arrays.toString và các hàm biểu diễn mảng](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Arrays.html).

Cũng cần chú ý một `Object[]` có thể được dùng làm chính mảng varargs:

```java
String[] names = {"Lan", "Minh"};
String text = String.format(Locale.ROOT, "%s / %s", (Object[]) names);
```

Ở đây hai phần tử là hai đối số cho hai chỉ thị.

Nếu muốn xem mảng như một đối số duy nhất, có thể ép `(Object) names`, nhưng `%s` vẫn không tự duyệt nội dung mảng. Khi mục tiêu là danh sách tên dễ đọc, dùng `Arrays.toString(names)` hoặc tự ghép theo định dạng ứng dụng cần.

Tương tự, với `char[]`, nếu cần văn bản của các ký tự thì tạo `new String(chars)`; không mặc định `printf("%s", chars)` có cùng cách xử lý riêng như một overload in mảng ký tự khác.

## 10. Các lỗi lựa chọn conversion thường gặp

| Mong muốn | Cách dùng dễ sai | Cách diễn đạt phù hợp hơn |
| --- | --- | --- |
| In số 0 | `%b` với 0 | `%d` hoặc `%s` theo nhu cầu |
| In nội dung chuỗi `"false"` | `%b` với chuỗi | `%s` |
| Kiểm tra danh sách rỗng | `%b` với danh sách | Tính `list.isEmpty()` rồi định dạng boolean |
| In một String một ký tự | `%c` với `"A"` | `%s`, hoặc lấy char nếu miền dữ liệu thật sự là char |
| In mã số 66 | `%c` với 66 | `%d` |
| In ký tự có mã 66 | `%d` với 66 | `%c` |
| In nội dung mảng | `%s` trực tiếp với mảng | Chuyển nội dung bằng `Arrays.toString` phù hợp |
| In số có hai chữ số phần lẻ | `%s` với số | Conversion số thích hợp như `%.2f` |

Một mẫu không ném ngoại lệ vẫn có thể sai ý nghĩa. `%b` với chuỗi `"false"` là ví dụ điển hình: chương trình chạy, nhưng output không đại diện cho dữ liệu người viết muốn truyền đạt.

## 11. Tự kiểm tra

1. Vì sao `%b` với `""` cho true? Vì chuỗi rỗng vẫn là đối tượng khác null, không phải Boolean.
2. Vì sao `%c` với `65` và `65L` khác nhau? Formatter kiểm tra cả kiểu đối số, không chỉ giá trị số.
3. `%s` với một đối tượng có tự in tất cả trường không? Không; nó đi theo cơ chế biểu diễn của đối tượng, thông thường là `toString()`.
4. `%B` có thay đổi giá trị boolean gốc không? Không; nó chỉ tạo biểu diễn chữ hoa.
5. Vì sao định dạng một mảng cần bước xử lý riêng nếu muốn thấy nội dung? Bản thân mảng không cung cấp `toString()` duyệt phần tử theo cách đó.

Trước khi chọn mẫu, hãy xác định dữ liệu đang biểu diễn **một điều kiện**, **một ký tự/mã ký tự** hay **một văn bản**. Chọn đúng ý nghĩa trước rồi mới thêm cờ, độ rộng và precision.
