# `String.split(regex)`: regex là quy tắc tìm dấu phân cách

Trong Java, `String.split(...)` tìm **những đoạn khớp biểu thức chính quy (regex)** rồi tách chuỗi tại các đoạn đó. Tham số không nhất thiết là một ký tự phân cách nguyên văn. Vì vậy, `"a.b.c".split(".")` **không** cho `["a", "b", "c"]`: trong regex, `.` là wildcard khớp gần như mọi ký tự.

Bài này tập trung vào **cách viết regex** và **hai tầng escape của Java**. Các bài tiếp theo khai thác riêng `limit`, phần tử rỗng, zero-width, `Pattern.quote`, stream và dữ liệu CSV.

## 1. Hợp đồng của `String.split`

Hai overload:

```java
public String[] split(String regex)
public String[] split(String regex, int limit)
```

Cả hai trả `String[]` gồm những đoạn nằm **giữa các lần regex khớp**; đoạn khớp đóng vai trò dấu phân cách không được giữ thành token riêng. Overload một tham số tương đương `split(regex, 0)`: mặc định bỏ toàn bộ phần tử rỗng **ở cuối**. Nếu cần kiểm soát số phần hoặc giữ trường cuối rỗng, dùng overload có `limit`.

```java
String[] colors = "red,green,blue".split(",");
// ["red", "green", "blue"]
```

Dấu phẩy không phải metacharacter của Java regex, nên mẫu `","` cũng là dấu phẩy nguyên văn. Nhưng nhiều ký tự khác mang nghĩa cú pháp:

| Mục tiêu | Đối số trong source Java | Regex nhận được |
| --- | --- | --- |
| Dấu phẩy literal | `","` | `,` |
| Dấu chấm literal | `"\\."` | `\.` |
| Dấu gạch đứng literal | `"\\|"` | `\|` |
| Một hoặc nhiều whitespace | `"\\s+"` | `\s+` |
| Dấu phẩy hoặc chấm phẩy | `"[,;]"` | Character class |
| Một hay nhiều dấu hai chấm | `":+"` | `:+` |
| Dấu phân cách nguyên văn động | `Pattern.quote(delimiter)` | Khớp chính xác chuỗi cấu hình |

Các ký hiệu như `.`, `|`, `+`, `*`, `?`, `[ ]`, `( )`, `\` có vai trò đặc biệt ở những ngữ cảnh regex nhất định. Đừng đưa thẳng delimiter nhận từ bên ngoài vào `split` nếu mục tiêu là khớp nguyên văn.

## 2. Hai tầng escape của Java

Để khớp một **dấu chấm thật**, regex engine cần `\.`. Nhưng dấu `\` cũng là ký tự escape trong string literal Java; để chuỗi Java chứa `\` phải viết `\\`. Vậy mã Java cần `split("\\.")`.

- `split(".")`: Java hợp lệ, regex khớp nhiều ký tự thường, sai mục tiêu dấu chấm.
- `split("\\.")`: Java hợp lệ, regex khớp đúng ký tự `.`.
- `split("\.")`: Java source không hợp lệ vì escape `\.` của literal không tồn tại.
- `split("\\s+")`: Java truyền regex `\s+`, khớp một hoặc nhiều whitespace tùy chế độ regex.

Lưu ý: Java 15+ có **escape chuỗi literal** `\s` mang nghĩa một dấu cách. Vì vậy viết `split("\s+")` trong Java hiện đại sẽ tạo regex ` +` (một hay nhiều dấu cách) thay vì nhóm whitespace `\s+` mà người viết thường mong đợi.

## 3. Chạy ví dụ để kiểm tra regex

Lưu `RegexSplitDemo.java` rồi biên dịch bằng JDK 17+:

```java
import java.util.Arrays;
import java.util.regex.Pattern;

public class RegexSplitDemo {
    public static void main(String[] args) {
        String dots = "a.b.c";
        System.out.println(dots.split(".").length);
        System.out.println(Arrays.toString(dots.split("\\.")));

        String pipes = "red|green|blue";
        System.out.println(Arrays.toString(pipes.split("\\|")));
        System.out.println(Arrays.toString("red   green\tblue".split("\\s+")));
        System.out.println(Arrays.toString("a,b;c".split("[,;]")));

        String delimiter = "|+|";
        String input = "left|+|middle|+|right";
        System.out.println(Arrays.toString(
                input.split(Pattern.quote(delimiter))));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 RegexSplitDemo.java
java RegexSplitDemo
```

```text
0
[a, b, c]
[red, green, blue]
[red, green, blue]
[a, b, c]
[left, middle, right]
```

Dòng đầu là `0` vì regex `.` khớp mọi ký tự trong chuỗi ví dụ và `limit=0` mặc định bỏ tất cả phần rỗng cuối. Đó là ví dụ **mẫu hợp lệ nhưng sai nghĩa dữ liệu**.

Với `"a,,b"`, `split(",")` giữ phần rỗng ở giữa, còn `split(",+")` xem cụm hai dấu phẩy là **một** lần khớp và không tạo cột rỗng ở giữa. Cách nào đúng tùy dữ liệu: nhóm whitespace giữa từ có thể gộp, còn hai dấu phẩy trong dữ liệu cột thường biểu thị một trường rỗng.

## 4. Giới hạn và cách xử lý lỗi

- Regex chưa đóng, ví dụ `"["`, khiến `split` ném `PatternSyntaxException`; không trả mảng rỗng để báo lỗi.
- `"a,b".split(null)` hoặc gọi `split` trên tham chiếu chuỗi nguồn `null` gây `NullPointerException`.
- Regex `\s` mặc định của Java không nhất thiết bao phủ mọi whitespace Unicode. Khi cần phạm vi Unicode rộng, cân nhắc `Pattern.UNICODE_CHARACTER_CLASS` và kiểm thử chính xác tập ký tự.
- Regex quá phức tạp từ đầu vào không tin cậy có thể gây backtracking tốn CPU. Khi delimiter là văn bản nguyên vẹn, `Pattern.quote` giúp tránh diễn giải nhầm thành cú pháp regex.
- `split("")` không phải bộ tách grapheme cluster Unicode; ký tự người dùng nhìn thấy có thể chứa nhiều code point hoặc UTF-16 code unit.
- `String.split(",")` không hiểu dấu nháy của CSV, dù có dùng `limit=-1`. Với CSV thực, cần parser hiểu trạng thái nháy và dòng nhiều dòng.

Khi cùng mẫu được dùng thường xuyên, `Pattern.compile(regex).split(input, limit)` cho phép tái sử dụng `Pattern`. Các quy tắc về `limit` tương tự `String.split`.

## 5. Tự kiểm tra

1. Vì sao `"api.example.org".split(".")` không tách theo dấu chấm? Viết hai cách sửa.
2. Regex nào tách `"one;two,three"` tại `;` hoặc `,`?
3. Vì sao `"a,,b".split(",+")` có ít token hơn `split(",")`?
4. Nếu dấu phân cách từ cấu hình có giá trị `"|+|"`, nên chuẩn bị regex như thế nào?

**Đáp án:** (1) `.` là wildcard; dùng `"\\."` hoặc `Pattern.quote(".")`. (2) `"[,;]"`. (3) `+` gộp các dấu liên tiếp; có thể làm mất trường rỗng. (4) Dùng `Pattern.quote(delimiter)`.

**Ghi nhớ:** Trước khi đếm token, phải biết **chính xác vùng nào trong đầu vào sẽ khớp regex**.