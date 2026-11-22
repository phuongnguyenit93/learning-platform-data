# `Pattern.quote()`: tách chuỗi bằng dấu phân cách nguyên văn

## 1. Vì sao cần `Pattern.quote`?

`String.split(String regex)` của Java luôn diễn giải tham số theo **biểu thức chính quy** (regex). Vì vậy, chuỗi `"."` không có nghĩa là dấu chấm: trong regex, `.` đại diện cho một ký tự bất kỳ (thông thường ngoại trừ ký tự kết thúc dòng). Tương tự, `|` là phép lựa chọn, `*`, `+`, `?` là các lượng từ, còn `\\` là ký tự escape. Nếu dấu phân cách do cấu hình, người dùng hoặc dữ liệu đầu vào cung cấp chứa các ký tự này, `split(delimiter)` có thể tách sai hoặc gây `PatternSyntaxException`.

`java.util.regex.Pattern.quote(String s)` chuyển chuỗi `s` thành **một regex khớp đúng toàn bộ chuỗi theo nghĩa nguyên văn**. Do đó, khi dấu phân cách là dữ liệu chứ không phải một quy luật regex, hãy viết:

```java
import java.util.regex.Pattern;

String[] parts = text.split(Pattern.quote(delimiter));
```

Ví dụ `"a.b".split(".")` cho mảng rỗng do `.` lần lượt khớp các ký tự và `split` mặc định loại các phần tử rỗng ở cuối. Trái lại, `"a.b".split(Pattern.quote("."))` cho `["a", "b"]`.

Bên trong regex, vùng trích dẫn thường có dạng `\\Q...\\E`, nhưng **không tự ghép thủ công** `"\\Q" + delimiter + "\\E"`: `Pattern.quote` còn xử lý đúng trường hợp dữ liệu chứa chính `\\E`.

## 2. Ví dụ Java 17+ chạy độc lập

Tạo file `LiteralDelimiterSplitDemo.java` với nội dung:

```java
import java.util.Arrays;
import java.util.regex.Pattern;

public class LiteralDelimiterSplitDemo {
    public static void main(String[] args) {
        // Dấu chấm: toán tử regex khác dấu chấm nguyên văn.
        String dotText = "a.b";
        System.out.println("Regex dot: "
                + Arrays.toString(dotText.split(".")));
        System.out.println("Literal dot: "
                + Arrays.toString(dotText.split(Pattern.quote("."))));

        // Dấu phân cách nhiều ký tự, có chứa toán tử regex.
        String delimiter = ".$.";
        String compositeText = "red.$.green.$.blue";
        System.out.println("Composite delimiter: "
                + Arrays.toString(compositeText.split(Pattern.quote(delimiter))));

        // Dấu gạch đứng cùng các giá trị limit.
        String pipeText = "a|b||";
        String pipeRegex = Pattern.quote("|");
        System.out.println("Default limit: "
                + Arrays.toString(pipeText.split(pipeRegex)));
        System.out.println("Keep trailing: "
                + Arrays.toString(pipeText.split(pipeRegex, -1)));
        System.out.println("At most two: "
                + Arrays.toString("a|b|c".split(pipeRegex, 2)));

        // Gạch chéo ngược: ký tự đặc biệt của cả Java literal và regex.
        String windowsPath = "C:\\temp\\docs";
        System.out.println("Backslash: "
                + Arrays.toString(windowsPath.split(Pattern.quote("\\"))));

        // Khi tách nhiều chuỗi bằng cùng một dấu phân cách.
        Pattern marker = Pattern.compile(Pattern.quote("<E>"));
        System.out.println("Compiled: "
                + Arrays.toString(marker.split("A<E>B<E>C")));
    }
}
```

Biên dịch và chạy:

```bash
javac LiteralDelimiterSplitDemo.java
java LiteralDelimiterSplitDemo
```

Đầu ra:

```text
Regex dot: []
Literal dot: [a, b]
Composite delimiter: [red, green, blue]
Default limit: [a, b]
Keep trailing: [a, b, , ]
At most two: [a, b|c]
Backslash: [C:, temp, docs]
Compiled: [A, B, C]
```

Ở dòng `Keep trailing`, mảng thực tế gồm bốn phần tử: `"a"`, `"b"`, `""`, `""`. `Arrays.toString` biểu diễn chuỗi rỗng bằng vị trí trống giữa các dấu phẩy. `String.split` không chèn thêm ký tự vào kết quả.

## 3. `limit` quyết định có giữ phần tử rỗng hay không

`Pattern.quote` chỉ làm cho dấu phân cách được so khớp **nguyên văn**; nó không thay đổi quy tắc `limit` của `String.split(regex, limit)`.

| Lệnh với chuỗi `"a|b||"` | Các phần tử thu được | Cơ chế |
| --- | --- | --- |
| `split(Pattern.quote("|"))` | `["a", "b"]` | Mặc định như `limit = 0`, bỏ các phần tử rỗng cuối. |
| `split(Pattern.quote("|"), 0)` | `["a", "b"]` | Cũng bỏ các phần tử rỗng cuối. |
| `split(Pattern.quote("|"), -1)` | `["a", "b", "", ""]` | Giữ đầy đủ các phần tử rỗng cuối. |
| `split(Pattern.quote("|"), 2)` | `["a", "b||"]` | Tách tối đa thành hai phần; phần cuối giữ phần còn lại. |

Khi `limit > 0`, có tối đa `limit - 1` lần tách. Khi `limit = 0` hoặc âm, phép tách có thể thực hiện nhiều lần; điểm khác nhau là `limit = 0` bỏ phần tử rỗng ở cuối, còn `limit < 0` giữ lại. Các phần tử rỗng **ở giữa** dấu phân cách liên tiếp vẫn có thể được giữ.

Nếu dữ liệu mang các cột có thể rỗng ở cuối, chẳng hạn `"id|name||"`, nên dùng `split(Pattern.quote("|"), -1)` để bảo toàn số trường; nếu dùng mặc định, có nguy cơ mất các trường cuối.

## 4. Các dấu phân cách dễ gặp lỗi

| Dữ liệu làm dấu phân cách | Cách gọi phù hợp | Vấn đề khi coi là regex |
| --- | --- | --- |
| Dấu chấm `.` | `split(Pattern.quote("."))` | `.` khớp ký tự bất kỳ. |
| Dấu gạch đứng `|` | `split(Pattern.quote("|"))` | `|` là phép lựa chọn. |
| Dấu sao `*` hoặc dấu cộng `+` | `split(Pattern.quote(delimiter))` | Lượng từ có thể gây lỗi cú pháp regex. |
| Chuỗi `.$.` | `split(Pattern.quote(".$."))` | Có nhiều toán tử regex cùng lúc. |
| Gạch chéo ngược `\\` | `split(Pattern.quote("\\"))` | Gạch chéo ngược còn là escape của regex. |
| Chuỗi `<END>` | `split(Pattern.quote("<END>"))` | Mẫu nguyên văn thể hiện đúng ý định dù dữ liệu thay đổi. |

Khi ký tự đặc biệt nằm trong **literal chuỗi Java**, còn có lớp escape của ngôn ngữ Java. Chẳng hạn, để biểu diễn **một** gạch chéo ngược trong chuỗi Java phải viết `"\\"`; để biến chính chuỗi này thành regex nguyên văn, dùng `Pattern.quote("\\")`. Escape của Java source và escape của regex là hai việc khác nhau.

`Pattern.quote` không thay đổi chữ hoa/thường, không bỏ khoảng trắng và không chuẩn hóa Unicode. Nó tìm đúng chuỗi phân cách được đưa vào. Nếu chuỗi đó không có trong văn bản, `split` thông thường trả về mảng một phần tử chứa nguyên văn bản.

## 5. Khi nào không dùng `Pattern.quote`?

Nếu mục tiêu là tách bằng **quy tắc**, ví dụ một hoặc nhiều ký tự trắng, hãy dùng regex đúng nghĩa:

```java
String line = "Java   regex\tbasics";
String[] words = line.split("\\s+");  // Một hoặc nhiều whitespace
```

Ở đây, `\\s+` là cú pháp regex chủ đích. Nếu gọi `Pattern.quote("\\s+")`, mẫu sẽ tìm đúng ba ký tự `\\`, `s`, `+` trong văn bản, không còn tìm khoảng trắng.

Hai cách dùng có mục đích khác nhau:

- **Dấu phân cách là một chuỗi cụ thể:** `text.split(Pattern.quote(delimiter))`.
- **Dấu phân cách mô tả một nhóm mẫu:** `text.split(regex)`, khi regex đã được tạo một cách có chủ đích.

Khi cùng một dấu phân cách nguyên văn được dùng nhiều lần, có thể biên dịch sẵn:

```java
Pattern literalDelimiter = Pattern.compile(Pattern.quote(delimiter));
String[] first = literalDelimiter.split(firstText, -1);
String[] second = literalDelimiter.split(secondText, -1);
```

Đây là đoạn minh họa sử dụng các biến `delimiter`, `firstText`, `secondText` do chương trình cung cấp, không phải file có thể chạy độc lập. `Pattern.split(input, limit)` có quy tắc `limit` tương tự `String.split(regex, limit)`. Biên dịch sẵn hữu ích khi dùng đi dùng lại một mẫu.

## 6. Lỗi thường gặp và giới hạn

**Tự escape vài ký tự riêng lẻ.** Chỉ thay `.` thành `\\.` sẽ bỏ sót `|`, `[`, `(`, `*` và các trường hợp khác. Việc tự xây dựng `\\Q...\\E` cũng có rủi ro nếu dữ liệu chứa `\\E`. `Pattern.quote` giải quyết cả chuỗi một cách nhất quán.

**Mặc định làm mất trường rỗng cuối.** `Pattern.quote` không sửa quy tắc này. Khi thứ tự hoặc số cột quan trọng, cần `limit = -1` và kiểm tra `array.length` trong chương trình, thay vì chỉ quan sát chuỗi `Arrays.toString`.

**Dấu phân cách rỗng hoặc `null`.** `Pattern.quote(null)` gây `NullPointerException`. Với `delimiter = ""`, mẫu nguyên văn có độ rộng bằng 0 nên việc tách trở thành tách tại các vị trí, khác ý nghĩa tách tại một dấu phân cách cụ thể. Nếu API chỉ chấp nhận dấu phân cách không rỗng, hãy kiểm tra `delimiter != null && !delimiter.isEmpty()`. Tránh `isBlank()` cho yêu cầu này: một dấu cách `" "` vẫn có thể là dấu phân cách hợp lệ.

**Lầm tưởng tách nguyên văn là phân tích CSV.** Với chuỗi `a,"b,c",d`, `split(Pattern.quote(","))` vẫn tách tại dấu phẩy bên trong cặp dấu nháy của `"b,c"`. CSV có quy tắc về dấu nháy, escape và xuống dòng; cần dùng trình phân tích CSV phù hợp nếu phải tuân thủ định dạng đó.

**Dùng nhầm cho phần thay thế regex.** `Pattern.quote` chỉ dành cho **pattern**. Khi chuỗi thay thế của `Matcher.replaceAll` chứa `$` hoặc `\\` và cần xử lý nguyên văn, API tương ứng là `Matcher.quoteReplacement`, có mục đích khác.

## 7. Tự kiểm tra

1. Để tách `"left.$.middle.$.right"` thành `["left", "middle", "right"]`, dùng `"left.$.middle.$.right".split(Pattern.quote(".$."))`.
2. Để giữ đủ bốn trường của `"name|email||"`, dùng `"name|email||".split(Pattern.quote("|"), -1)`.
3. Khi cấu hình chứa `"."`, `split(delimiter)` coi nó là toán tử regex; `split(Pattern.quote(delimiter))` khớp đúng dấu chấm.

**Điều cần nhớ:** Tham số đầu tiên của `String.split` là regex. Dấu phân cách đến từ **dữ liệu nguyên văn** thì dùng `Pattern.quote`; các phần tử rỗng ở cuối cần được bảo toàn thì thêm `limit = -1`.