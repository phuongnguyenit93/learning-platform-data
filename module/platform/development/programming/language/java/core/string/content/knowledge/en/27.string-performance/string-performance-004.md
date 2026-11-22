# Tránh tạo nhiều chuỗi trung gian khi xử lý theo từng bước trong Java

## Mục tiêu

Khi chuẩn hóa dữ liệu, tạo thông báo, dựng CSV, ghép nhiều trường hoặc biến đổi văn bản trong vòng lặp, một chương trình Java có thể tạo ra nhiều đối tượng `String` chỉ để sử dụng trong thời gian rất ngắn. Bài học này giúp bạn xác định khi nào các chuỗi trung gian làm tăng cấp phát bộ nhớ, chọn kỹ thuật giảm số lần sao chép/nối chuỗi, và giữ nguyên ngữ nghĩa của phép biến đổi. Mục tiêu là giảm công việc không cần thiết ở đoạn mã thực sự cần tối ưu, chứ không loại bỏ mọi `String` tạm bằng mọi giá.

## 1. Vì sao phát sinh chuỗi trung gian?

`String` trong Java là **bất biến** (immutable): sau khi tạo, nội dung của một đối tượng `String` không bị sửa trực tiếp. Các phương thức như `replace(...)`, `toUpperCase(...)`, `substring(...)` hoặc thao tác nối chuỗi có thể trả về một chuỗi mới để biểu diễn kết quả. Tùy trường hợp, một số phương thức được phép trả về chính đối tượng cũ nếu nội dung không đổi; do đó không nên tuyên bố “mỗi lời gọi đều chắc chắn tạo một `String` mới”.

Ví dụ:

```java
String source = "  Java-Core  ";
String a = source.trim();
String b = a.replace('-', ' ');
String c = b.toUpperCase(java.util.Locale.ROOT);
System.out.println(c);
```

Kết quả:

```text
JAVA CORE
```

`a` và `b` là các giá trị trung gian phục vụ bước tiếp theo. Cách viết trên dễ đọc, đúng chức năng và hoàn toàn có thể là lựa chọn tốt đối với dữ liệu nhỏ hoặc xử lý ít lần. Nhưng nếu đoạn xử lý này chạy hàng triệu lần hoặc trên văn bản rất dài, các bản sao và đối tượng tạm có thể gây thêm **allocation**, lưu lượng bộ nhớ và áp lực cho garbage collector (GC). Chúng cũng có thể phải duyệt qua nội dung nhiều lần.

Phân biệt ba chi phí:
- **Cấp phát:** tạo các đối tượng `String` hoặc bộ đệm phụ, đặc biệt khi lặp lại rất nhiều lần.
- **Sao chép/duyệt:** chuyển nội dung từ đầu vào sang kết quả mới hoặc kiểm tra lại từng ký tự qua nhiều công đoạn.
- **Giữ bộ nhớ:** lưu tham chiếu đến nhiều kết quả tạm hoặc dùng bộ đệm có dung lượng quá lớn trong thời gian dài.

JVM có tối ưu hóa khi chạy, chẳng hạn tối ưu nối chuỗi hoặc loại bỏ một số cấp phát trong trường hợp phù hợp. Tuy vậy, không thể dựa vào suy đoán rằng JIT luôn loại bỏ mọi chuỗi trung gian. Khi hiệu năng quan trọng, cần đo trên đúng bản JDK và workload.

## 2. Nhận diện chuỗi trung gian trong vòng lặp

Với vòng lặp `result += part`, mỗi kết quả bất biến có thể chứa lại toàn bộ tiền tố trước đó; nếu chuỗi tăng đều, tổng dữ liệu phải tạo theo mô hình nối tuần tự có thể tăng bậc hai theo số lượt. `StringBuilder` cho phép tích lũy bằng một vùng đệm rồi gọi `toString()` khi hoàn tất. Bài về nối lặp `+=` đã phân tích công thức chi phí này; ở đây cần nhận diện **những giá trị tạm chỉ được tạo ra để lập tức chép vào một kết quả khác**.

Các câu hỏi hữu ích khi xem xét một pipeline:

- Có đang tạo chuỗi định dạng bằng `prefix + value + suffix` chỉ để đưa ngay vào `builder.append(...)` không? Nếu có, có thể append từng thành phần trực tiếp.
- Có tạo `text.substring(begin, end)` chỉ để append đoạn đó vào bộ đệm không? Overload `append(text, begin, end)` có thể tránh giá trị trung gian này.
- Có thật sự cần giữ một `String` sau mỗi bước không? Nếu các kết quả chỉ phục vụ bước tiếp theo, cân nhắc gộp các thao tác xây dựng đầu ra; nếu là biến đổi Unicode, chuẩn hóa hoặc escaping phức tạp, vẫn phải giữ ngữ nghĩa chuẩn.

Không thể kết luận nhanh hơn chỉ từ việc số biến tạm giảm. Sau khi bảo đảm kết quả tương đương, hãy đo allocation và thời gian trên dữ liệu đại diện. Những ví dụ ở phần tiếp theo tập trung trực tiếp vào cách bỏ chuỗi tạm khi định dạng hoặc sao chép một đoạn.

## 3. Gộp nhiều bước xây dựng đầu ra vào cùng một `StringBuilder`

Giả sử chương trình cần nối các phần dưới dạng `[value]`. Cách sau tạo chuỗi trình bày cho từng phần rồi mới nối kết quả:

```java
StringBuilder out = new StringBuilder();
for (String value : values) {
    String formatted = "[" + value + "]";
    out.append(formatted);
}
```

Có thể append trực tiếp từng phần vào bộ đệm:

```java
StringBuilder out = new StringBuilder();
for (String value : values) {
    out.append('[').append(value).append(']');
}
String result = out.toString();
```

Lúc này, phần định dạng `formatted` không còn cần thiết. `append(char)` thêm ký tự, còn `append(String)` thêm nội dung chuỗi mà không cần tạo chuỗi kết hợp mới ở tầng mã nguồn.

Ví dụ đầy đủ — lưu thành `DirectAppendDemo.java`:

```java
public class DirectAppendDemo {
    public static void main(String[] args) {
        String[] values = {"A", "B", "C"};

        StringBuilder out = new StringBuilder();
        for (String value : values) {
            out.append('[').append(value).append(']');
        }

        System.out.println(out.toString());
    }
}
```

```bash
javac -encoding UTF-8 DirectAppendDemo.java
java DirectAppendDemo
```

```text
[A][B][C]
```

Cách tiếp cận tương tự phù hợp khi dựng phần thân thông báo, command line, định dạng log có điều kiện, template đơn giản hoặc xuất dữ liệu dạng văn bản. Một builder nên có chủ sở hữu rõ ràng và chỉ tạo kết quả bất biến khi một bước thực sự cần nó.

## 4. Tránh tạo `substring` nếu chỉ cần chép một đoạn vào kết quả

Giả sử có văn bản chứa phần cần lấy trong một khoảng chỉ số. Cách sau tạo chuỗi tạm để chèn vào builder:

```java
String fragment = text.substring(begin, end);
builder.append(fragment);
```

Nếu chỉ cần chép các ký tự từ `text`, dùng overload:

```java
builder.append(text, begin, end);
```

`StringBuilder.append(CharSequence, int start, int end)` chép nội dung ở khoảng **[start, end)** trực tiếp vào builder, tránh yêu cầu tạo đối tượng `String` từ `substring`. Chỉ số được tính bằng **đơn vị mã UTF-16**, giống `String.length()` và `String.substring(...)`.

Ví dụ chạy độc lập — lưu thành `AppendRangeDemo.java`:

```java
public class AppendRangeDemo {
    public static void main(String[] args) {
        String source = "prefix:payload:suffix";
        int begin = "prefix:".length();
        int end = source.indexOf(":suffix");

        StringBuilder builder = new StringBuilder();
        builder.append("value=");
        builder.append(source, begin, end);

        System.out.println(builder.toString());
    }
}
```

```bash
javac -encoding UTF-8 AppendRangeDemo.java
java AppendRangeDemo
```

```text
value=payload
```

Kiểm tra `begin` và `end` trước khi append khi chỉ số lấy từ dữ liệu không tin cậy (ví dụ `indexOf` có thể trả về `-1`). Nếu thao tác cắt có thể nằm giữa cặp surrogate của một ký tự bổ sung Unicode, cần chọn ranh giới theo code point để tránh tạo chuỗi chứa surrogate lẻ. Khi API yêu cầu một `String` độc lập ở chính bước đó, không thể loại bỏ mọi chuyển đổi thành `String`.

## 5. Khi nào nên xử lý trực tiếp một lượt duyệt?

Một pipeline quen thuộc:

```java
String output = input.trim()
        .toLowerCase(java.util.Locale.ROOT)
        .replace('-', '_')
        .replace(' ', '_');
```

Mỗi bước có thể tạo kết quả mới và quét nội dung lại. Nếu nghiệp vụ chỉ yêu cầu một bộ quy tắc nhỏ, có thể duyệt đầu vào một lần và ghi thẳng kết quả vào `StringBuilder`. Tuy nhiên, **không được đổi thuật toán rồi vô tình đổi kết quả**: `trim()`, `strip()`, xử lý hoa/thường Unicode và thao tác `char` không tương đương nhau trong mọi trường hợp.

Ví dụ sau có phạm vi được định nghĩa rõ: chỉ đổi **chữ ASCII A–Z thành a–z** và thay khoảng trắng ASCII cùng dấu gạch nối bằng `_`. Đây **không phải** cách viết lại tổng quát của `toLowerCase(Locale.ROOT)` hay `strip()` đối với mọi văn bản Unicode.

Lưu thành `SinglePassAsciiDemo.java`:

```java
public class SinglePassAsciiDemo {
    static String normalizeAscii(String input) {
        StringBuilder out = new StringBuilder(input.length());
        for (int i = 0; i < input.length(); i++) {
            char ch = input.charAt(i);
            if (ch == '-' || ch == ' ') {
                out.append('_');
            } else if (ch >= 'A' && ch <= 'Z') {
                out.append((char) (ch + ('a' - 'A')));
            } else {
                out.append(ch);
            }
        }
        return out.toString();
    }

    public static void main(String[] args) {
        System.out.println(normalizeAscii("A-B C"));
        System.out.println(normalizeAscii("Java 17"));
    }
}
```

```bash
javac -encoding UTF-8 SinglePassAsciiDemo.java
java SinglePassAsciiDemo
```

```text
a_b_c
java_17
```

**Ưu điểm:** một vòng duyệt và một builder, không tạo chuỗi riêng ở từng bước biến đổi. **Giới hạn:** hàm này giữ nguyên các ký tự Unicode khác ngoài ASCII, không loại bỏ khoảng trắng đầu/cuối, không xử lý quy tắc viết thường đặc biệt của ngôn ngữ và không xử lý token/locale. Nếu cần quy tắc Unicode đầy đủ, hãy dùng các API chuẩn hoặc thiết kế thuật toán theo code point/locale và kiểm thử thật kỹ. Tối ưu bộ nhớ không cho phép làm sai kết quả nghiệp vụ.

Một cách tối ưu thường an toàn hơn viết lại toàn bộ pipeline là **gộp riêng những bước tạo đầu ra**: vừa duyệt/tokenize đầu vào, vừa nối delimiter và phần cần thiết vào một builder. Giữ các phép biến đổi Unicode khó ở API chuẩn nếu chi phí của chúng chưa được đo là nút thắt.

## 6. Chọn đúng công cụ cho nhu cầu nối chuỗi

| Nhu cầu | Công cụ hợp lý | Lưu ý |
| --- | --- | --- |
| Nối vài giá trị trong một biểu thức | Toán tử `+` | Ngắn gọn, JVM hiện đại có tối ưu nối chuỗi |
| Tích lũy dữ liệu trong vòng lặp hoặc nhiều nhánh | `StringBuilder` | Tạo builder cho một đơn vị công việc; `toString()` một lần khi xong |
| Nối các phần có dấu phân cách | `String.join(...)` hoặc `StringJoiner` | Tốt khi cần các chuỗi có sẵn; cân bằng tính dễ đọc và cấp phát |
| Nối phần tử từ stream | `Collectors.joining(...)` | Dễ đọc; mỗi phép `map(...)` tạo `String` vẫn có thể sinh trung gian |
| Định dạng nhiều giá trị theo mẫu phức tạp | `String.format(...)` / `formatted(...)` | Mạnh về định dạng; có chi phí parse/format, nên đo nếu ở hot path |
| Ghi lượng văn bản lớn ra file/network | `Writer`, `BufferedWriter` hoặc API streaming thích hợp | Ghi dần để tránh giữ toàn bộ chuỗi kết quả trong RAM |
| Bộ đệm có thao tác trên nhiều luồng | Phân định sở hữu và đồng bộ hóa | `StringBuilder` không thread-safe; `StringBuffer` đồng bộ từng phương thức nhưng không tự bảo đảm tính nguyên tử của cả quy trình nhiều bước |

Ví dụ nối delimiter bằng `StringJoiner`:

```java
java.util.StringJoiner joiner = new java.util.StringJoiner(", ", "[", "]");
joiner.add("red").add("green").add("blue");
System.out.println(joiner.toString());
```

```text
[red, green, blue]
```

`StringJoiner` phù hợp khi phần tử đã là chuỗi. Nhưng `String.join` hay `Collectors.joining` không tự loại bỏ các chuỗi tạm sinh bởi những bước trước đó như `stream.map(x -> expensiveTransform(x))`. Với dữ liệu rất lớn, có thể ghi trực tiếp từng bản ghi ra `Writer` thay vì dồn tất cả vào `StringBuilder`.

## 7. Quản lý dung lượng của `StringBuilder`

`StringBuilder` có `capacity()` là dung lượng bộ đệm hiện tại và `length()` là số đơn vị mã UTF-16 đang chứa. Khi append vượt capacity, bộ đệm phải mở rộng; việc mở rộng có thể đòi hỏi cấp phát và sao chép. Nếu có ước lượng đáng tin cậy về kích thước đầu ra, có thể khởi tạo dung lượng:

```java
int estimatedChars = 128;
StringBuilder builder = new StringBuilder(estimatedChars);
builder.append("prefix:").append("data");
```

Chọn capacity dựa trên dữ liệu thực tế, chẳng hạn tổng chiều dài các phần và delimiter. Nếu chỉ biết số phần tử mà không biết độ dài từng phần, đừng nhân một hằng số quá lớn dẫn đến cấp phát dư thừa. `capacity()` có đơn vị UTF-16, không phải số Unicode code point hoặc số byte UTF-8. `StringBuilder.length()` cũng không bằng số ký tự người dùng cảm nhận trong mọi ngôn ngữ.

Những lưu ý thực tế:

- `new StringBuilder()` đã có khả năng tăng dung lượng; không phải mọi trường hợp đều cần dự đoán capacity.
- `ensureCapacity(...)` có thể hữu ích khi nhu cầu tăng đáng kể đã được biết trước.
- `setLength(0)` xóa nội dung logic để tái sử dụng bộ đệm **nhưng có thể giữ nguyên vùng nhớ lớn đã cấp phát**. Tái sử dụng builder từng phình rất lớn trong cache dài hạn có thể giữ bộ nhớ quá lâu.
- `toString()` trả về một `String` bất biến. Không gọi lặp đi lặp lại `toString()` trong vòng lặp chỉ để kiểm tra độ dài hoặc nội dung đơn giản; dùng `builder.length()`, `charAt(...)` hoặc trạng thái riêng khi phù hợp.
- Đừng giữ một `StringBuilder` tĩnh dùng chung giữa các request/luồng. Ngoài nguy cơ race condition, nó có thể giữ dung lượng không mong muốn; ưu tiên builder cục bộ.

## 8. Tránh tạo chuỗi trung gian ở các ranh giới xử lý

### 8.1. Chỉ tạo thông báo khi thật sự cần

Ví dụ logger hỗ trợ tham số hóa thường cho phép:

```java
logger.debug("Processed id={}, size={}", id, size);
```

Khi mức DEBUG bị tắt, framework có thể tránh định dạng văn bản cuối cùng. Cú pháp cụ thể tùy thư viện log đang dùng. Với các thao tác nặng trước khi gọi logger (ví dụ `expensiveToString()`), tham số hóa không mặc nhiên ngăn phương thức đó được đánh giá trước; hãy kiểm tra API lazy/supplier hoặc điều kiện enabled theo framework.

### 8.2. Đọc/ghi theo luồng nếu đầu ra rất lớn

Tạo một `StringBuilder` khổng lồ cho hàng triệu bản ghi có thể giảm số lượng `String` trung gian nhưng vẫn giữ toàn bộ kết quả trong RAM. Nếu đích cuối là tệp hoặc socket, dùng `BufferedWriter` (với charset rõ ràng) để ghi từng phần:

```java
try (java.io.BufferedWriter writer = java.nio.file.Files.newBufferedWriter(
        path, java.nio.charset.StandardCharsets.UTF_8)) {
    for (String value : values) {
        writer.write(value);
        writer.newLine();
    }
}
```

Đoạn trên **là mẫu đặt trong một phương thức** đã có biến `Path path` và nguồn `Iterable<String> values`, không phải một chương trình độc lập. Cần xử lý lỗi I/O, quyền truy cập và đóng tài nguyên theo yêu cầu ứng dụng. Việc ghi streaming tránh tạo một `String` kết quả chứa cả tệp; API writer vẫn có thể dùng bộ đệm nội bộ.

### 8.3. Tận dụng dữ liệu sẵn có

Khi chỉ cần kiểm tra tiền tố, hậu tố, ký tự ở một vị trí hoặc tìm chuỗi con, ưu tiên `startsWith`, `endsWith`, `charAt`, `indexOf` thay vì cắt ra nhiều `substring` để so sánh. Ví dụ:

```java
if (value.startsWith("ID:")) {
    // Xử lý tiếp theo tùy nghiệp vụ.
}
```

Với phần có thể lấy theo khoảng chỉ số, `append(value, begin, end)` giúp không tạo `substring` trung gian. Tuy vậy, không nên giữ tham chiếu đến nguồn rất lớn chỉ để tránh tạo một chuỗi nhỏ nếu nhu cầu lưu trữ lâu dài đòi một bản sao độc lập.

## 9. Khi nhiều phương thức biến đổi nối tiếp vẫn là lựa chọn đúng

Các phép xử lý như chuẩn hóa Unicode, case folding theo ngôn ngữ, escaping JSON/XML, regex phức tạp, phân tích ngữ pháp hoặc an toàn injection có các quy tắc tinh vi. Viết một bộ duyệt thủ công chỉ vì muốn dùng `StringBuilder` có thể làm mất tính đúng đắn. Ví dụ:

- `String.toLowerCase(Locale.ROOT)` có thể xử lý ánh xạ Unicode không tương đương với cộng một khoảng số trên `char`.
- `String.strip()` dùng tiêu chí Unicode whitespace khác `trim()`; hai phương thức không thể hoán đổi tùy tiện.
- Biểu thức chính quy có semantics đặc thù; `replaceAll(...)`, `replace(...)` và so khớp với `Pattern` biên dịch sẵn không tương đương nhau trong mọi trường hợp.
- Escaping dữ liệu cấu trúc nên giao cho serializer/library phù hợp để tránh lỗi bảo mật, dù thao tác này có tạo chuỗi hoặc bộ đệm phụ.
- Dãy Unicode có thể có surrogate pair và combining marks; từng `char` không nhất thiết là một code point, càng không tương đương một grapheme mà người dùng nhìn thấy.

Hãy giữ pipeline dễ hiểu khi nó đã đủ nhanh hoặc khi phép biến đổi khó. Nếu profile cho thấy chi phí ở một bước, tối ưu đúng bước đó trước. Các lời gọi `replace(...)` không tìm thấy gì có thể trả về chuỗi gốc; số cấp phát thực tế phải được xác nhận bằng công cụ đo.

## 10. Đo hiệu năng và cấp phát đúng cách

Một đoạn thử đơn giản bằng `System.nanoTime()` dễ bị sai lệch bởi JIT warmup, GC, cache, kích thước dữ liệu, dead-code elimination và cách chuẩn bị đầu vào. Để so sánh các cách xử lý chuỗi:

1. **Xác nhận kết quả bằng nhau trước:** kiểm thử trường hợp rỗng, `null` nếu API cho phép, delimiter, đầu/cuối chuỗi, dấu tiếng Việt, ký tự bổ sung Unicode và dữ liệu lớn. Nếu thay đổi ngữ nghĩa, số liệu tốc độ không còn so sánh cùng chức năng.
2. **Xác định workload:** số phần tử, chiều dài trung bình, phân bố chuỗi ASCII/Unicode, tần suất chạy, giới hạn heap và tỷ lệ dữ liệu cần biến đổi thực sự.
3. **Profile ứng dụng:** dùng Java Flight Recorder (JFR), profiler hoặc công cụ đo cấp phát để tìm nơi sinh đối tượng; quan sát throughput, latency, allocation rate và GC pauses.
4. **Benchmark đoạn nóng:** dùng JMH với warmup, nhiều lần đo và tiêu thụ kết quả để tránh tối ưu bỏ mã; so trên cùng phiên bản Java, phần cứng và dữ liệu. Theo dõi cả đơn vị `ops/s` hoặc `ns/op` và số byte cấp phát trên mỗi thao tác khi có thể.
5. **Đưa thay đổi nhỏ vào ứng dụng thực:** đo lại end-to-end. Cải thiện microbenchmark không chắc cải thiện request latency nếu thời gian chủ yếu nằm ở I/O, lock hoặc database.

Tối ưu có ý nghĩa khi **giữ đúng chức năng, giảm được chi phí đo thấy và không làm mã khó bảo trì vượt lợi ích**. Nên ưu tiên thay thế vòng `result += item` chạy nhiều lần bằng một builder hoặc ghi trực tiếp ra writer trước khi tối ưu các biểu thức nhỏ.

## 11. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| `result += part` bên trong vòng lặp lớn | Tạo chuỗi kết quả tích lũy mới nhiều lần | Dùng `StringBuilder` hoặc `Writer` |
| `builder.append(prefix + value + suffix)` ở mỗi vòng | Có thể tạo chuỗi `prefix + value + suffix` trước khi append | Gọi `append(prefix).append(value).append(suffix)` |
| `builder.toString().isEmpty()` mỗi vòng | Yêu cầu tạo/kiểm tra chuỗi kết quả nhiều lần | Dùng `builder.length() == 0` |
| `builder.append(text.substring(a, b))` chỉ để chép đoạn | Có thể tạo bản `String` tạm | Dùng `builder.append(text, a, b)` |
| Tái sử dụng builder toàn cục hoặc builder khổng lồ | Race condition, dữ liệu lẫn nhau, giữ bộ nhớ | Dùng builder cục bộ theo công việc |
| Tự viết lại xử lý Unicode để “nhanh hơn” | Sai ánh xạ chữ, sai whitespace, tách surrogate | Giữ API Unicode chuẩn; tối ưu khi có bằng chứng |
| Dự đoán capacity quá lớn | Cấp phát RAM không cần thiết | Dùng ước lượng thực tế hoặc để builder tự tăng |
| Dùng `StringBuilder` cho mọi phép `+` | Mã dài hơn nhưng lợi ích chưa chắc có | Chỉ sửa các đoạn code nóng đã xác định |

Một mẹo nhỏ: nếu muốn thêm delimiter giữa các phần, hãy kiểm tra builder trước khi append:

```java
if (builder.length() > 0) {
    builder.append(", ");
}
builder.append(value);
```

Cách này tránh tạo chuỗi trung gian và tránh delimiter thừa ở đầu; tuy nhiên cần chính sách rõ ràng khi `value` là chuỗi rỗng, `null` hoặc phần tử cần lọc.

## 12. Bài tập thực hành

**Bài 1 — nối kết quả:** từ mảng 10.000 chuỗi, tạo văn bản phân cách bằng dấu phẩy với hai cách: vòng lặp `+=` và `StringBuilder`. So sánh kết quả bằng `equals`, sau đó benchmark đúng cách; phân biệt “hai kết quả bằng nhau” với “đã chứng minh cách nào nhanh hơn”.

**Bài 2 — bỏ chuỗi định dạng tạm:** viết lại mẫu `builder.append("(" + id + ":" + value + ")")` thành các lời gọi `append(...)` nối tiếp. Kiểm thử trường hợp `id` âm, `value` rỗng và ký tự Unicode.

**Bài 3 — tránh `substring`:** với chuỗi `"before[content]after"`, tìm vị trí giữa dấu `[` và `]` rồi thêm trực tiếp vào builder bằng `append(source, start, end)`. Kiểm thử trường hợp thiếu dấu đóng.

**Bài 4 — pipeline:** định nghĩa tập quy tắc ASCII của riêng bạn, viết một hàm duyệt một lần tạo đầu ra tương đương chuỗi các phép `replace`. Viết test so sánh cho nhiều đầu vào trước khi đo cấp phát.

**Bài 5 — dữ liệu lớn:** thay mô hình xây dựng một chuỗi CSV cực lớn bằng ghi từng hàng qua `BufferedWriter`. Đo mức sử dụng heap và thời gian ghi cho cả hai trên bộ dữ liệu có kiểm soát.

### Kết luận thực hành

Đối với các bước xây dựng văn bản lặp lại, hãy nghĩ đến việc **append trực tiếp từng phần vào một `StringBuilder`**, dùng khoảng chỉ số để tránh `substring` chỉ nhằm sao chép, và chuyển sang ghi streaming khi đầu ra quá lớn. Những phép biến đổi Unicode phức tạp cần ưu tiên tính đúng đắn. Chọn nơi tối ưu dựa trên profiler, kiểm thử kết quả và đo cấp phát, không chỉ dựa vào số dấu `+` xuất hiện trong mã.