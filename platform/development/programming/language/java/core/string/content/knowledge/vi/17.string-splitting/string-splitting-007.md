# `String.splitWithDelimiters()` — tách chuỗi và giữ dấu phân cách (Java 21)

Khi cần chia một chuỗi thành các phần, `String.split(regex)` thường đủ dùng. Nhưng nếu muốn **giữ nguyên ký tự hoặc đoạn ký tự đã dùng để tách** (dấu phẩy, dấu hai chấm, khoảng trắng, dấu phân cách nhiều ký tự...), Java 21 cung cấp `String.splitWithDelimiters(regex, limit)`. Phương thức trả về cả phần nội dung và phần khớp biểu thức chính quy theo đúng thứ tự xuất hiện.

## 1. API và ý nghĩa

```java
public String[] splitWithDelimiters(String regex, int limit)
```

- `regex`: **biểu thức chính quy (regular expression)** mô tả dấu phân cách cần tìm; đây không mặc nhiên là chuỗi ký tự thông thường.
- `limit`: điều khiển số lần tách và việc giữ/bỏ những chuỗi rỗng ở cuối kết quả.
- Giá trị trả về: `String[]` lần lượt chứa **đoạn nội dung, dấu phân cách khớp regex, đoạn nội dung, dấu phân cách, ...**; dấu phân cách giữ chính xác những ký tự thật sự khớp.
- Phương thức có từ **Java 21**. Không có phiên bản `splitWithDelimiters(regex)` chỉ nhận một tham số như `split(regex)`; phải truyền `limit`.

Ví dụ, với `"red:::green::blue"` và regex `":+"`, kết quả là `["red", ":::", "green", "::", "blue"]`. Hai dấu phân cách `":::"` và `"::"` được giữ ở các phần tử riêng, do `:+` khớp **một hoặc nhiều** dấu hai chấm liên tiếp.

`String.splitWithDelimiters(regex, limit)` có cùng ý nghĩa với `Pattern.compile(regex).splitWithDelimiters(input, limit)`. Bản `Pattern` hữu ích khi phải tái sử dụng một regex nhiều lần.

## 2. Khác gì `split()`?

| Phép gọi với `s = "a::b:c"` | Kết quả |
| --- | --- |
| `s.split(":+", -1)` | `["a", "b", "c"]` |
| `s.splitWithDelimiters(":+", -1)` | `["a", "::", "b", ":", "c"]` |

`split()` bỏ các đoạn khớp regex; `splitWithDelimiters()` lưu chúng trong mảng. Vì vậy phương thức mới phù hợp khi muốn dựng lại nguyên văn chuỗi ban đầu, phân tích log, giữ nguyên dấu câu hoặc nhận biết từng loại ký tự phân cách.

Hình dung luồng xử lý:

```text
Chuỗi:        red ::: green :: blue
Đoạn trả về: [red][:::][green][::][blue]
Loại:        [NỘI DUNG][NGĂN CÁCH][NỘI DUNG][NGĂN CÁCH][NỘI DUNG]
```

Mỗi lần tìm thấy dấu phân cách, kết quả thêm phần nội dung **đứng trước** rồi đến chính phần khớp. Nếu không có dấu phân cách nào khớp, mảng chỉ có một phần tử là toàn bộ chuỗi đầu vào.

## 3. Ví dụ Java 21 chạy độc lập

Tạo file `SplitWithDelimitersDemo.java`:

```java
import java.util.Arrays;
import java.util.regex.Pattern;

public class SplitWithDelimitersDemo {
    public static void main(String[] args) {
        String input = "red:::green::blue";

        System.out.println("split       = "
                + Arrays.toString(input.split(":+", -1)));
        System.out.println("with        = "
                + Arrays.toString(input.splitWithDelimiters(":+", -1)));
        System.out.println("limit 2     = "
                + Arrays.toString(input.splitWithDelimiters(":+", 2)));

        String[] parts = input.splitWithDelimiters(":+", -1);
        System.out.println("round-trip  = "
                + input.equals(String.join("", parts)));

        // Dấu chấm theo nghĩa ký tự thật, không phải wildcard regex.
        System.out.println("literal dot = "
                + Arrays.toString(
                        "a.b.c".splitWithDelimiters(Pattern.quote("."), -1)));
    }
}
```

Biên dịch và chạy bằng JDK 21 trở lên:

```bash
javac --release 21 SplitWithDelimitersDemo.java
java SplitWithDelimitersDemo
```

Kết quả chuẩn:

```text
split       = [red, green, blue]
with        = [red, :::, green, ::, blue]
limit 2     = [red, :::, green::blue]
round-trip  = true
literal dot = [a, ., b, ., c]
```

`String.join("", parts)` nối tuần tự tất cả phần nội dung và dấu phân cách, không chèn thêm gì. Với regex tách thông thường, cách này giúp kiểm tra đã giữ được nguyên văn đầu vào. Kết quả `limit 2` cho thấy chỉ dấu `:::` đầu tiên được tách ra; phần `green::blue` còn lại giữ nguyên.

## 4. Hiểu chính xác tham số `limit`

`limit` **không phải số phần tử tối đa** của mảng, cũng không phải độ dài tối đa của từng phần tử.

| `limit` | Cách xử lý | Hệ quả |
| --- | --- | --- |
| `> 0` | Áp dụng regex tối đa `limit - 1` lần | Mảng dài tối đa `2 * limit - 1` phần tử; phần tử cuối chứa toàn bộ phần còn lại |
| `= 0` | Tách tối đa | Bỏ **các chuỗi rỗng ở cuối** mảng, gồm phần nội dung rỗng hoặc dấu phân cách rỗng |
| `< 0` | Tách tối đa | Giữ cả các chuỗi rỗng ở cuối |

Với chuỗi `"a,b,"`, regex `","`:

| Lệnh | Mảng trả về (dùng ký hiệu dấu ngoặc kép để nhìn rõ chuỗi rỗng) |
| --- | --- |
| `splitWithDelimiters(",", 1)` | `["a,b,"]` |
| `splitWithDelimiters(",", 2)` | `["a", ",", "b,"]` |
| `splitWithDelimiters(",", 0)` | `["a", ",", "b", ","]` |
| `splitWithDelimiters(",", -1)` | `["a", ",", "b", ",", ""]` |

Lưu ý ở `limit = 0`: **dấu phẩy cuối vẫn còn** vì đó là chuỗi `","`, không rỗng; chỉ phần nội dung `""` sau dấu phẩy bị bỏ. `limit = -1` sẽ giữ phần tử `""` để phân biệt kết thúc ngay sau dấu phân cách.

Với `limit = 1`, không thực hiện lần tách nào, nên kết quả là mảng một phần tử chứa cả chuỗi. Với `limit > 1`, số lần tách tối đa là `limit - 1`, mỗi lần tách có thể tạo thêm **hai phần tử** (nội dung và dấu phân cách); do đó giới hạn độ dài là `2 * limit - 1`, khác `String.split(regex, limit)`.

## 5. Regex quyết định dấu phân cách được giữ như thế nào

- Regex `","` chỉ khớp một dấu phẩy. Với `"a,,b"` và `limit = -1`, nhận `["a", ",", "", ",", "b"]`. Phần nội dung rỗng ở giữa là thông tin có ý nghĩa: hai dấu phẩy liên tiếp.
- Regex `",+"` khớp cả nhóm dấu phẩy liên tiếp. Cùng chuỗi `"a,,b"` sẽ thành `["a", ",,", "b"]`. Hãy chọn `","` hay `",+"` theo việc muốn phân biệt từng dấu riêng hay gộp cả cụm.
- Regex `"[,;]\\s*"` khớp một dấu phẩy **hoặc** chấm phẩy, sau đó là mọi khoảng trắng liền kề. `"milk, bread; eggs".splitWithDelimiters("[,;]\\s*", -1)` trả về `["milk", ", ", "bread", "; ", "eggs"]`. Khoảng trắng cũng nằm trong dấu phân cách nên không bị mất.
- Các ký tự `.`, `|`, `*`, `+`, `?`, `(`, `)`, `[`, `]`... có ý nghĩa đặc biệt trong regex. Để tách theo **ký tự dấu chấm thật**, dùng `"\\."` trong source Java, hoặc `Pattern.quote(".")`; truyền `"."` sẽ khớp gần như mọi ký tự đơn lẻ.

Nếu regex có thể khớp **chuỗi rỗng** (zero-width match), kết quả có các quy tắc biên cần chú ý. Cụ thể, một match **không rỗng** ngay đầu chuỗi sẽ tạo phần nội dung rỗng ở đầu; còn match **độ rộng bằng 0** ngay đầu chuỗi **không** tạo phần nội dung rỗng hoặc phần dấu phân cách rỗng mở đầu. Không nên mặc định mọi regex đều tạo cùng kiểu mảng như ví dụ chỉ dùng dấu phân cách thật.

## 6. Trường hợp biên quan trọng

| Input | Regex | `limit` | Kết quả |
| --- | --- | --- | --- |
| `",A"` | `","` | `-1` | `["", ",", "A"]` |
| `"A,"` | `","` | `-1` | `["A", ",", ""]` |
| `"A,"` | `","` | `0` | `["A", ","]` |
| `"A,,B"` | `","` | `-1` | `["A", ",", "", ",", "B"]` |
| `"ABC"` | `","` | `-1` | `["ABC"]` |

Các kết quả này minh họa sự khác nhau giữa **đoạn nội dung rỗng** và **dấu phân cách**. Với `limit = 0`, chỉ phần tử rỗng nằm **ở tận cuối** bị loại; phần nội dung rỗng giữa hai dấu phân cách vẫn được giữ.

## 7. Ứng dụng thực tế: xử lý token nhưng giữ dấu nối

Giả sử muốn tô màu từng phần của chuỗi mà vẫn giữ nguyên dấu phẩy, dấu chấm phẩy và khoảng trắng sau chúng:

```java
String input = "milk, bread; eggs";
String[] tokens = input.splitWithDelimiters("[,;]\\s*", -1);

for (int i = 0; i < tokens.length; i++) {
    boolean isDelimiter = (i % 2 == 1);
    System.out.printf("%s: <%s>%n",
            isDelimiter ? "DELIMITER" : "TEXT",
            tokens[i]);
}
```

Đây là **đoạn mã dùng bên trong phương thức hoặc JShell**, không phải một file Java độc lập. Kết quả:

```text
TEXT: <milk>
DELIMITER: <, >
TEXT: <bread>
DELIMITER: <; >
TEXT: <eggs>
```

Với cách tách giữ delimiter này, các phần tử ở chỉ số chẵn (`0, 2, 4...`) là phần nội dung, chỉ số lẻ (`1, 3, 5...`) là dấu phân cách. Khi regex có thể khớp chuỗi rỗng, phải xét thêm quy tắc zero-width; khi `limit = 0` làm mất phần nội dung rỗng cuối, mảng có thể kết thúc ngay sau một delimiter.

Các phần tử có thể dùng để dựng giao diện highlight, chuẩn hóa một số kiểu log, đếm hoặc nhận diện từng dấu phân cách. Nếu muốn giữ nguyên dữ liệu gốc để xử lý tiếp, thường chọn `limit = -1`.

## 8. Các lỗi thường gặp và cách chọn API

1. **Nhầm regex với chuỗi literal:** `"."` là ký tự đại diện trong regex; dùng `Pattern.quote(".")` hoặc `"\\."` khi tìm dấu chấm thực sự.
2. **Tưởng `limit = 2` nghĩa là hai phần tử:** phương thức có thể trả về ba phần tử `[trước, delimiter, còn_lại]`.
3. **Tưởng `limit = 0` xóa dấu phân cách cuối:** nó chỉ xóa **chuỗi rỗng** ở cuối, không xóa ký tự phân cách thật.
4. **Bỏ quên phần nội dung rỗng giữa hai delimiter:** `"a,,b"` khác `"a,b"` nếu quy tắc dữ liệu coi trường rỗng là quan trọng.
5. **Dùng regex phức tạp cho dữ liệu có cấu trúc:** phương thức này **không thay thế parser CSV chuẩn** (đặc biệt khi có chuỗi trong ngoặc kép, dấu phân cách được escape) hay parser cho cú pháp lồng nhau.
6. **Lặp lại regex nhiều lần trên lượng dữ liệu lớn:** có thể biên dịch một `Pattern` trước rồi dùng `pattern.splitWithDelimiters(input, limit)` để tái sử dụng; tránh regex có backtracking tốn kém.

**Chọn `split()`** khi chỉ cần các giá trị sau khi loại dấu phân cách. **Chọn `splitWithDelimiters()`** khi vị trí và nguyên văn dấu phân cách cũng là thông tin cần giữ.

## 9. Tự kiểm tra

- `"x|y".splitWithDelimiters("\\|", -1)` trả về gì? → `["x", "|", "y"]`.
- Vì sao `"x,,y".splitWithDelimiters(",", -1)` có phần tử `""`? → Hai lần khớp dấu phẩy liên tiếp, không có nội dung giữa chúng.
- Khi muốn giữ cả trường rỗng cuối chuỗi, chọn `limit` nào? → Giá trị âm, thường là `-1`.
- Với `limit = 3`, chiều dài mảng lớn nhất là bao nhiêu? → `2 * 3 - 1 = 5`.
- Khi không có dấu nào khớp, kết quả là gì? → Mảng gồm duy nhất chuỗi ban đầu.

**Tham khảo API chính thức:** [`String.splitWithDelimiters` trong Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html#splitWithDelimiters(java.lang.String,int)) và [`Pattern.splitWithDelimiters` trong Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/regex/Pattern.html#splitWithDelimiters(java.lang.CharSequence,int)).
