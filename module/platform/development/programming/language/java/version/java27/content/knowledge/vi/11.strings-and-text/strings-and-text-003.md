# StringBuilder và lựa chọn cách ghép chuỗi trong Java 27

Ghép chuỗi là thao tác thường xuyên khi xây dựng thông báo, tạo nội dung báo cáo, hiển thị danh sách hoặc dựng văn bản từ nhiều phần dữ liệu. Trong **Java 27**, một biểu thức `"Xin chào, " + name` thường là lựa chọn đơn giản, rõ ràng. Nhưng khi phải thêm hàng nghìn đoạn văn bản trong vòng lặp, một `StringBuilder` có thể phù hợp hơn. Còn khi ghép danh sách với dấu phân cách, `String.join` hoặc `Collectors.joining` thường biểu đạt ý định tốt nhất.

Bài học thuộc chương **Chuỗi và dữ liệu văn bản**. Mục tiêu không phải là luôn chọn một API “nhanh nhất”, mà là **chọn công cụ đúng theo cấu trúc dữ liệu, phạm vi thay đổi và khả năng đọc hiểu**. Các ví dụ sử dụng API ổn định, còn được hỗ trợ trong Java SE 27; không dựa trên thủ thuật tối ưu hóa lỗi thời hoặc chi tiết nội bộ của JVM.

## 1. Nền tảng: `String` bất biến, `StringBuilder` có thể thay đổi

`String` là một chuỗi ký tự **bất biến** (*immutable*): sau khi đối tượng được tạo, nội dung của chính đối tượng đó không thay đổi. Mọi thao tác có vẻ “sửa” chuỗi thực chất tạo ra hoặc trả về một `String` khác.

```java
String message = "Xin chào";
String original = message;

message = message + ", Java 27";

System.out.println(original); // Xin chào
System.out.println(message);  // Xin chào, Java 27
```

Biến `message` được **gán lại** để tham chiếu tới chuỗi mới; đối tượng mà `original` đang tham chiếu vẫn có nội dung ban đầu.

`StringBuilder` lại là một **chuỗi ký tự có thể thay đổi** (*mutable sequence of characters*). Thay vì tạo một `String` mới sau mỗi thao tác nối, ta có thể xây dựng dần nội dung trong cùng một builder:

```java
StringBuilder builder = new StringBuilder();

builder.append("Xin chào");
builder.append(", ");
builder.append("Java 27");

String message = builder.toString();

System.out.println(message); // Xin chào, Java 27
```

Các lời gọi `append` làm thay đổi nội dung của `builder`. Lời gọi `toString()` tạo kết quả kiểu `String`; thay đổi builder sau đó **không làm thay đổi** chuỗi đã nhận:

```java
StringBuilder builder = new StringBuilder("A");
String snapshot = builder.toString();

builder.append("B");

System.out.println(snapshot);         // A
System.out.println(builder.toString()); // AB
```

Tóm lại:

| Thuộc tính | `String` | `StringBuilder` |
| --- | --- | --- |
| Nội dung sau khi tạo | Bất biến | Có thể bổ sung, xóa, chèn, thay thế |
| Cách ghép phổ biến | `+`, `+=`, `concat` | `append(...)` |
| Kết quả sử dụng rộng rãi | Đã là `String` | Gọi `toString()` khi cần chuỗi kết quả |
| Phù hợp | Giá trị văn bản, tham số API, vài đoạn nối đơn giản | Xây dựng văn bản từng bước, nhất là trong vòng lặp |
| Chia sẻ giữa các luồng | Nội dung bất biến; việc công bố tham chiếu vẫn tuân theo quy tắc đồng thời Java | **Không an toàn** nếu nhiều luồng cùng sửa mà không đồng bộ |

Không nên dùng `StringBuilder` thay cho mọi `String`: builder là công cụ để **xây dựng**, còn `String` thường là dạng **giá trị cuối cùng** nên trả về, lưu trữ hoặc truyền qua API.

## 2. Toán tử `+`: ưu tiên cho những phép ghép ngắn, dễ đọc

Với ít thành phần, cú pháp `+` dễ hiểu và ít mã hơn:

```java
String user = "Lan";
int unread = 3;

String message = "Chào " + user + ", bạn có " + unread + " tin nhắn.";
System.out.println(message);
// Chào Lan, bạn có 3 tin nhắn.
```

Khi một toán hạng của `+` là `String`, Java thực hiện phép nối chuỗi; các giá trị khác được chuyển sang biểu diễn dạng văn bản phù hợp. Giá trị tham chiếu `null` được biểu diễn thành chuỗi `"null"` trong phép nối.

```java
String name = null;
System.out.println("Tên: " + name); // Tên: null
```

Điều này **không có nghĩa** `"null"` là cách hiển thị đúng về mặt nghiệp vụ. Nếu dữ liệu không có tên, hãy chọn nội dung thay thế rõ ràng:

```java
String displayName = name == null ? "(chưa có tên)" : name;
String label = "Tên: " + displayName;
```

### 2.1. Thứ tự đánh giá của `+` rất quan trọng

`+` được kết hợp từ trái sang phải. Khi hai toán hạng đầu vẫn là số, Java thực hiện phép cộng số trước khi gặp một `String`:

```java
System.out.println(1 + 2 + " mục"); // 3 mục
System.out.println("Mục " + 1 + 2); // Mục 12
System.out.println("Mục " + (1 + 2)); // Mục 3
```

Nếu kết quả toán học là một thành phần văn bản, dùng dấu ngoặc để tránh việc vô tình nối chữ số.

### 2.2. Compiler có thể tối ưu phép ghép chuỗi

Biểu thức hằng như:

```java
String title = "Java " + "27";
```

có thể được xử lý như một hằng chuỗi ngay khi biên dịch.

Với biểu thức có dữ liệu động, compiler/JVM hiện đại có chiến lược tối ưu phép nối chuỗi. Từ Java 9, cơ chế triển khai mặc định của `javac` đã chuyển sang cách biên dịch nối chuỗi có thể dùng `invokedynamic`; **mã bytecode và chiến lược cấp phát cụ thể không phải là phần mà ứng dụng nên phụ thuộc**.

Hệ quả thực tế: **không cần viết `new StringBuilder(...)` bằng tay cho từng biểu thức `"A" + value + "B"`** chỉ vì nghĩ rằng mọi dấu `+` đều tạo một chuỗi trung gian độc lập. Ưu tiên tính rõ ràng; chỉ thay đổi nếu cấu trúc lặp hoặc phép đo thực tế cho thấy cần thiết.

## 3. Vấn đề thường gặp: dùng `+=` liên tục trong vòng lặp

Xét đoạn tạo danh sách số:

```java
String result = "";

for (int i = 1; i <= 5; i++) {
    result += i + " ";
}

System.out.println(result); // In: "1 2 3 4 5 " (có dấu cách ở cuối)
```

Đoạn mã đúng, nhưng ở mỗi lượt, `result` được gán một `String` mới. Khi kết quả tích lũy ngày càng dài, các phép nối có thể phải xử lý nhiều nội dung cũ nhiều lần. Với số lượt lớn, chi phí cấp phát và sao chép có thể trở nên đáng kể.

Dùng một builder tích lũy thay vì cộng dồn nhiều `String`:

```java
StringBuilder result = new StringBuilder();

for (int i = 1; i <= 5; i++) {
    result.append(i).append(' ');
}

System.out.println(result.toString()); // In: "1 2 3 4 5 " (có dấu cách ở cuối)
```

Dấu `+` trong một **biểu thức ngắn** khác với `+=` lặp lại trên **một biến chuỗi ngày càng dài**. Trường hợp thứ hai là tình huống nên cân nhắc `StringBuilder` đầu tiên.

Không nên kết luận mọi vòng lặp dùng `+=` luôn chậm một mức cố định: độ dài dữ liệu, số lượt, compiler, JIT, GC và mục tiêu môi trường chạy đều ảnh hưởng. Nếu hiệu năng quan trọng, đo bằng bài benchmark phù hợp trên JDK và workload thực tế (ví dụ JMH), không chỉ dựa vào vài lần đo `System.nanoTime()`.

## 4. Cách dùng `StringBuilder` đúng và rõ ràng

### 4.1. Tạo builder

```java
StringBuilder empty = new StringBuilder();
StringBuilder fromText = new StringBuilder("Xin chào");
StringBuilder reserved = new StringBuilder(128);
```

- `new StringBuilder()` tạo builder rỗng, sức chứa (*capacity*) ban đầu là **16** đơn vị `char`.
- `new StringBuilder("Xin chào")` khởi tạo builder từ nội dung chuỗi có sẵn.
- `new StringBuilder(128)` tạo builder rỗng với sức chứa ban đầu bằng **128** đơn vị `char`; đây là dung lượng dự phòng, không phải nội dung có sẵn dài 128 ký tự.

### 4.2. `append` có nhiều overload

`StringBuilder.append(...)` nhận `String`, `CharSequence`, `char`, số, `boolean`, `Object`, mảng `char[]` và một số kiểu khác:

```java
StringBuilder sb = new StringBuilder();

sb.append("Mã ")
  .append(27)
  .append(": ")
  .append(true);

System.out.println(sb); // Mã 27: true
```

Mỗi lời gọi `append` trả về **chính builder đó**, nhờ vậy có thể viết thành chuỗi lời gọi (*method chaining*) theo thứ tự mong muốn.

```java
StringBuilder sb = new StringBuilder("A");
System.out.println(sb.append("B") == sb); // true
```

Cách đặt xuống dòng nên giúp người đọc nhận ra các thành phần nội dung:

```java
StringBuilder message = new StringBuilder();
message.append("Người dùng: ").append(userName).append('\n')
       .append("Số lượng: ").append(quantity).append('\n')
       .append("Trạng thái: ").append(status);
```

### 4.3. Chuyển thành chuỗi khi hoàn tất

Khi kết quả phải đi vào API nhận `String`, gọi `toString()` ở cuối quá trình dựng:

```java
static String buildGreeting(String name) {
    StringBuilder sb = new StringBuilder();
    sb.append("Xin chào, ").append(name).append('!');
    return sb.toString();
}
```

Đừng gọi `toString()` sau **mỗi** lần `append` nếu mục tiêu là tích lũy trong cùng một builder. Điều đó không làm sai kết quả, nhưng có thể tạo ra các chuỗi trung gian không cần thiết.

## 5. Những phương thức thao tác chuỗi của `StringBuilder`

`StringBuilder` không chỉ có `append`. Nó hỗ trợ chèn, xóa, thay thế và đọc nội dung:

| Phương thức | Tác dụng | Lưu ý |
| --- | --- | --- |
| `append(value)` | Thêm nội dung vào cuối | Có thể nối nhiều lần |
| `insert(index, value)` | Chèn tại vị trí | Chỉ số phải hợp lệ |
| `delete(start, end)` | Xóa đoạn `[start, end)` | `end` không thuộc đoạn xóa |
| `deleteCharAt(index)` | Xóa một đơn vị `char` | Cẩn thận với cặp surrogate |
| `replace(start, end, text)` | Thay đoạn `[start, end)` | Thay đổi nội dung builder |
| `setCharAt(index, ch)` | Gán một `char` tại vị trí | Có thể phá một cặp surrogate |
| `charAt(index)` | Đọc một `char` | Trả về đơn vị UTF-16 |
| `length()` | Độ dài hiện tại | Tính theo đơn vị UTF-16 |
| `capacity()` | Sức chứa hiện tại | Không phải độ dài nội dung |
| `ensureCapacity(n)` | Yêu cầu sức chứa tối thiểu | Dùng khi ước lượng được kích thước |
| `setLength(n)` | Đổi độ dài logic của builder | `setLength(0)` thường dùng để xóa nội dung logic |
| `toString()` | Lấy kết quả `String` | Kết quả không đổi theo các lần sửa builder sau |

Ví dụ:

```java
StringBuilder sb = new StringBuilder("Java Text");

sb.insert(5, "27 ");
System.out.println(sb); // Java 27 Text

sb.replace(8, 12, "String");
System.out.println(sb); // Java 27 String

sb.delete(4, 7);
System.out.println(sb); // Java String
```

Trong ví dụ, các chỉ số là vị trí trong chuỗi hiện tại, không phải vị trí cố định của nội dung ban đầu. Với văn bản Unicode có ký tự ngoài BMP, phải phân biệt chỉ số `char` với vị trí ký tự người dùng nhìn thấy (xem mục Unicode).

### 5.1. `length()` khác `capacity()`

```java
StringBuilder sb = new StringBuilder(64);

System.out.println(sb.length());        // 0
System.out.println(sb.capacity() >= 64); // true

sb.append("abc");
System.out.println(sb.length()); // 3
```

- `length` là số đơn vị UTF-16 **đang có nội dung**.
- `capacity` là lượng đơn vị UTF-16 builder có thể chứa trước khi cần mở rộng.
- Khi thêm vượt sức chứa, builder tự mở rộng. Không cần gọi `ensureCapacity` trước mỗi `append`.
- Nếu biết trước văn bản rất dài, dự trù một capacity hợp lý có thể giảm số lần mở rộng. Đừng cấp phát một capacity rất lớn chỉ theo dự đoán mơ hồ.

Có thể dùng `setLength(0)` để làm rỗng về mặt logic và tái sử dụng builder:

```java
StringBuilder sb = new StringBuilder(256);
sb.append("Báo cáo lần 1");

// Sau khi đã sử dụng xong kết quả lần 1:
sb.setLength(0);
sb.append("Báo cáo lần 2");
```

Tuy nhiên, builder vẫn có thể giữ vùng chứa lớn trong bộ nhớ. `setLength(0)` **không phải cơ chế xóa sạch thông tin bí mật khỏi bộ nhớ** và không phù hợp để dùng như giải pháp an toàn dữ liệu nhạy cảm. Với phần lớn ứng dụng, tạo builder cục bộ mới cho mỗi tác vụ dễ hiểu và ít rủi ro hơn.

## 6. Chọn cách ghép chuỗi theo bài toán

| Bài toán | Lựa chọn nên cân nhắc | Vì sao |
| --- | --- | --- |
| Nối vài thành phần có thứ tự rõ ràng | `+` | Dễ đọc, compiler/JVM có thể tối ưu |
| Sinh nội dung dần trong vòng lặp hoặc theo nhiều nhánh | `StringBuilder` | Tích lũy trên một đối tượng mutable |
| Ghép danh sách chuỗi bằng dấu phân cách | `String.join(delimiter, ...)` | Không phải tự kiểm tra “phần tử cuối” |
| Thêm phần tử theo thời gian, cần prefix/suffix | `StringJoiner` | Dấu phân cách, tiền tố và hậu tố được quản lý tập trung |
| Có sẵn `Stream<CharSequence>` hoặc cần lọc, map rồi nối | `Collectors.joining(...)` | Ghép như một bước trong pipeline |
| Cần bố cục số, ngày, độ rộng, dấu thập phân theo locale | `String.format(locale, format, args...)` hoặc API formatter chuyên biệt | Phân biệt **định dạng dữ liệu** với **nối chuỗi** |
| Đoạn văn bản nhiều dòng cố định | Text block `"""..."""` | Dễ đọc hơn nhiều phép nối literal |
| Xây dựng văn bản ghi ra đích `Appendable`/`Writer` | Ghi từng phần trực tiếp khi phù hợp | Không nhất thiết giữ toàn bộ văn bản thành một `String` |

Quy tắc kinh nghiệm: chọn cách viết **đọc vào là hiểu yêu cầu nghiệp vụ** trước, rồi cân nhắc hiệu năng khi có lượng dữ liệu đủ lớn hoặc yêu cầu đo đạc rõ ràng.

## 7. `String.join`: ghép các phần tử với dấu phân cách

Nếu đã có các phần tử chuỗi, `String.join` rất phù hợp:

```java
import java.util.List;

List<String> languages = List.of("Java", "Kotlin", "Scala");

String names = String.join(", ", languages);
System.out.println(names); // Java, Kotlin, Scala
```

Dùng varargs khi số phần tử đã biết:

```java
String path = String.join("/", "api", "v1", "users");
System.out.println(path); // api/v1/users
```

`String.join` xử lý dấu phân cách **giữa** các phần tử, không thêm dấu phân cách ở đầu hoặc cuối. Nó hữu ích khi yêu cầu là một danh sách tuyến tính.

Một số điều cần nhớ:

- API nhận các phần tử có kiểu `CharSequence` (ví dụ `String`, `StringBuilder`); không nhận trực tiếp mọi loại đối tượng tùy ý mà không chuyển đổi.
- Phần tử `null` có thể được biểu diễn dưới dạng `"null"`; đừng để dữ liệu thiếu đi vào đầu ra mà không có chủ đích.
- Không thể dùng `String.join(", ", numbers)` nếu `numbers` là `List<Integer>`: chuyển số thành chuỗi trước.
- `String.join` chỉ thêm dấu phân cách, **không** tự escape dấu phẩy, dấu ngoặc kép hay newline bên trong dữ liệu CSV.

Nếu muốn coi `null` là giá trị trống, có thể xử lý tại bước chuẩn bị dữ liệu:

```java
String displayName = userName == null ? "(không rõ)" : userName;
String row = String.join(" | ", userId, displayName);
```

## 8. `StringJoiner`: dựng danh sách từng bước, có tiền tố/hậu tố

Khi số lượng phần tử chưa có sẵn thành một collection hoặc cần kết quả dạng `[a, b, c]`, `StringJoiner` là lựa chọn rõ ràng:

```java
import java.util.StringJoiner;

StringJoiner joiner = new StringJoiner(", ", "[", "]");

joiner.add("red");
joiner.add("green");
joiner.add("blue");

System.out.println(joiner); // [red, green, blue]
```

Khác với cách viết thủ công bằng builder, người viết không cần tự kiểm tra có nên thêm dấu phẩy trước phần tử tiếp theo hay không.

```java
StringJoiner labels = new StringJoiner(" | ");
labels.add("đang xử lý").add("ưu tiên cao");
System.out.println(labels.toString()); // đang xử lý | ưu tiên cao
```

Với `new StringJoiner(", ", "[", "]")`, nếu chưa thêm phần tử nào, `toString()` mặc định trả về `"[]"`. Có thể thay chuỗi biểu diễn trạng thái rỗng:

```java
StringJoiner joiner = new StringJoiner(", ", "[", "]");
joiner.setEmptyValue("(không có dữ liệu)");
System.out.println(joiner.toString()); // (không có dữ liệu)
```

Khi dữ liệu không phải một danh sách mà là cấu trúc nhiều dòng, xen kẽ tiêu đề/tổng cộng/thành phần tùy chọn, `StringBuilder` vẫn linh hoạt hơn.

## 9. `Collectors.joining`: ghép sau `map` hoặc `filter`

Nếu các phần tử đang được xử lý trong stream, dùng collector `Collectors.joining`:

```java
import java.util.List;
import java.util.stream.Collectors;

List<String> tags = List.of(" Java ", " ", "JDK27", " StringBuilder ");

String result = tags.stream()
        .map(String::strip)
        .filter(tag -> !tag.isEmpty())
        .collect(Collectors.joining(" | ", "[", "]"));

System.out.println(result); // [Java | JDK27 | StringBuilder]
```

Có các overload:

- `Collectors.joining()`: nối không có dấu phân cách.
- `Collectors.joining(delimiter)`: thêm dấu phân cách.
- `Collectors.joining(delimiter, prefix, suffix)`: thêm cả tiền tố và hậu tố.

Đối với stream chưa phải chuỗi, chuyển sang chuỗi trước:

```java
import java.util.List;
import java.util.stream.Collectors;

List<Integer> ids = List.of(10, 20, 30);

String csvLike = ids.stream()
        .map(String::valueOf)
        .collect(Collectors.joining(", "));

System.out.println(csvLike); // 10, 20, 30
```

Ví dụ này tạo chuỗi phân tách bởi dấu phẩy, nhưng **chưa phải serializer CSV đầy đủ** khi dữ liệu đầu vào có dấu phân cách, dấu quote hoặc xuống dòng.

Dùng stream khi đã có pipeline hoặc cần lọc/biến đổi. Nếu chỉ muốn ghép ba chuỗi tĩnh, tạo stream riêng để ghép có thể làm mã dài hơn mà không có lợi ích.

## 10. `String.format` và `formatted`: khi yêu cầu chính là định dạng

Không phải bài toán nào cũng chỉ là “nối vài chuỗi”. Khi cần hiển thị số với số chữ số thập phân cụ thể, độ rộng cột hay nhiều placeholder, dùng formatter thường dễ kiểm soát hơn.

```java
import java.util.Locale;

String line = String.format(
        Locale.ROOT,
        "Sản phẩm: %s | Số lượng: %d | Giá: %.2f",
        "Sổ tay",
        3,
        12.5
);

System.out.println(line);
// Sản phẩm: Sổ tay | Số lượng: 3 | Giá: 12.50
```

`String.format` hỗ trợ các conversion như `%s`, `%d`, `%f` và cú pháp độ rộng, độ chính xác. Với định dạng phụ thuộc locale, hãy chọn `Locale` theo đối tượng người dùng hoặc yêu cầu hệ thống:

```java
Locale displayLocale = Locale.forLanguageTag("vi-VN");
String text = String.format(displayLocale, "Số lượng: %,d", 12000);
```

Chọn locale một cách tường minh đặc biệt quan trọng với định dạng dùng trong xuất báo cáo hoặc dữ liệu có yêu cầu ổn định. Đừng giả định dấu phân tách hàng nghìn giống nhau trên mọi môi trường.

Với biểu thức format ngắn, `String.formatted(Object...)` cũng là API hiện hành:

```java
String message = "Xin chào %s, bạn có %d thông báo."
        .formatted("Lan", 3);
```

`formatted` dùng định dạng theo locale mặc định của môi trường. Nếu cần điều khiển locale, dùng overload của `String.format(Locale, ...)`.

**Phân biệt ý định:** `+` và `StringBuilder` chủ yếu nối thành phần, còn `String.format` cung cấp **ngôn ngữ định dạng**. Formatter có thể có chi phí nhiều hơn nối đơn giản; không nên dùng cho mọi thông điệp ngắn nếu cú pháp `+` đã rõ.

Với ngày/giờ, tiền tệ hoặc con số cần định dạng theo chuẩn nghiệp vụ, cân nhắc các API chuyên biệt như `DateTimeFormatter` hoặc `NumberFormat` thay vì tự nối chuỗi và giả định quy tắc locale.

## 11. Text block và đoạn văn bản nhiều dòng

Java hỗ trợ *text block* ổn định cho literal nhiều dòng:

```java
String instructions = """
        Hướng dẫn:
        1. Đăng nhập.
        2. Chọn tài liệu.
        3. Xác nhận.
        """;
```

Text block vẫn tạo ra một `String` bất biến; nó **không phải** một builder và không tự chèn biến động.

Khi cần chèn một vài giá trị vào văn bản nhiều dòng, có thể kết hợp text block với `formatted`:

```java
String summary = """
        Tài khoản: %s
        Trạng thái: %s
        """.formatted(accountId, status);
```

Nếu nội dung nhiều dòng được tạo từ một số lượng bản ghi thay đổi, dùng `StringBuilder` hoặc ghi từng phần trực tiếp vào `Writer` sẽ linh hoạt hơn là cố khai báo nhiều placeholder tĩnh.

Không nhầm text block với các đề xuất string template từng xuất hiện dưới dạng preview trong các bản JDK trước và không trở thành cú pháp ổn định. Bài học chỉ dùng các cơ chế được hỗ trợ chính thức trong Java 27.

## 12. Ví dụ hoàn chỉnh: sinh hóa đơn từ danh sách sản phẩm

Giả sử ứng dụng nhận danh sách dòng hàng và cần xuất một chuỗi văn bản gồm tiêu đề, từng dòng và tổng cộng. Số lượng dòng thay đổi, nên `StringBuilder` thể hiện ý định tốt; `Collectors.joining` phục vụ riêng cho danh sách nhãn.

Tạo file `StringCompositionDemo.java`:

```java
import java.util.List;
import java.util.Locale;
import java.util.stream.Collectors;

public class StringCompositionDemo {

    record LineItem(String name, int quantity, long unitPrice) {}

    static String buildReceipt(List<LineItem> items) {
        StringBuilder sb = new StringBuilder(128);
        sb.append("HÓA ĐƠN").append('\n');

        long total = 0;

        for (LineItem item : items) {
            long amount = Math.multiplyExact(item.quantity(), item.unitPrice());
            total = Math.addExact(total, amount);

            sb.append("- ")
              .append(item.name())
              .append(" x ")
              .append(item.quantity())
              .append(": ")
              .append(amount)
              .append(" VND")
              .append('\n');
        }

        sb.append("Tổng: ").append(total).append(" VND");
        return sb.toString();
    }

    static String formatTags(List<String> tags) {
        return tags.stream()
                .map(String::strip)
                .filter(tag -> !tag.isEmpty())
                .collect(Collectors.joining(" | ", "[", "]"));
    }

    public static void main(String[] args) {
        List<LineItem> items = List.of(
                new LineItem("Bút", 2, 5_000),
                new LineItem("Sổ", 1, 18_000)
        );

        System.out.println(buildReceipt(items));
        System.out.println(formatTags(List.of("java", " text ", "", "JDK27")));

        String footer = String.format(
                Locale.ROOT, "Có %d dòng hàng.", items.size()
        );
        System.out.println(footer);
    }
}
```

Chạy với JDK 27, lưu file ở UTF-8:

```bash
javac -encoding UTF-8 StringCompositionDemo.java
java StringCompositionDemo
```

Kết quả:

```text
HÓA ĐƠN
- Bút x 2: 10000 VND
- Sổ x 1: 18000 VND
Tổng: 28000 VND
[java | text | JDK27]
Có 2 dòng hàng.
```

Phân tích cách chọn công cụ:

1. `StringBuilder(128)` dành sẵn một sức chứa khởi đầu hợp lý cho báo cáo nhỏ. Giá trị 128 chỉ là ví dụ; không có nghĩa mọi báo cáo cần capacity này.
2. Vòng `for` thêm từng dòng bằng `append`, không thực hiện `receipt += line` liên tục.
3. Phương thức trả về `String` qua `toString()` để người gọi nhận một giá trị văn bản ổn định.
4. `formatTags` có sẵn dữ liệu dạng list cần lọc và biến đổi, nên `Collectors.joining` phù hợp hơn builder thủ công.
5. Footer có placeholder số lượng nên `String.format` làm rõ ý định định dạng.
6. `Math.multiplyExact` và `Math.addExact` được dùng để phát hiện tràn `long` thay vì âm thầm sai tổng. Trong sản phẩm thực, cần thêm ràng buộc số lượng, đơn giá không âm, đơn vị tiền và chiến lược xử lý lỗi.

Ví dụ dùng ba công cụ trong cùng một chương trình vì **mỗi công cụ giải quyết một hình dạng bài toán khác nhau**, không phải vì ứng dụng phải chọn duy nhất một phong cách ghép chuỗi.

## 13. Ghép chuỗi và Unicode: `length()` không đếm “ký tự nhìn thấy”

Cả `String` và `StringBuilder` đều làm việc với chuỗi ký tự theo cách biểu diễn UTF-16 của Java. Vì vậy:

- `length()` trả về số **đơn vị mã UTF-16** (*UTF-16 code units*), không nhất thiết bằng số Unicode code point.
- Ký tự ở ngoài *Basic Multilingual Plane* (BMP) thường cần **hai** đơn vị UTF-16 (*surrogate pair*).
- Một ký tự người dùng nhìn thấy có thể gồm **nhiều code point**, ví dụ chữ có dấu kết hợp hoặc chuỗi emoji có liên kết.

Ví dụ với emoji tên lửa:

```java
StringBuilder sb = new StringBuilder("A");
sb.appendCodePoint(0x1F680); // 🚀

System.out.println(sb);                         // A🚀
System.out.println(sb.length());                // 3 đơn vị UTF-16
System.out.println(sb.codePointCount(0, sb.length())); // 2 code point
```

Ở đây `A` chiếm một đơn vị UTF-16, emoji chiếm hai; tổng `length()` bằng 3, nhưng tổng code point bằng 2.

Khi ghép văn bản, `append` xử lý các đơn vị ký tự; điều này thường đủ an toàn cho ghép toàn bộ chuỗi. Nhưng khi chèn, xóa hoặc cắt theo **chỉ số `char`**, tránh tách đôi một surrogate pair hoặc phá cụm ký tự hiển thị. Với thao tác văn bản theo *grapheme cluster*, cần thêm thuật toán/phân đoạn Unicode phù hợp; `length()` đơn thuần không giải quyết yêu cầu này.

### 13.1. `append(CharSequence, start, end)` tránh tạo substring trung gian khi phù hợp

```java
CharSequence source = "ABCDE";
StringBuilder sb = new StringBuilder();

sb.append(source, 1, 4);
System.out.println(sb); // BCD
```

Với overload nhận `CharSequence`, `start` là chỉ số đầu, `end` là chỉ số **loại trừ**. Còn với overload nhận `char[]` ba tham số, đối số thứ ba là **độ dài** chứ không phải chỉ số kết thúc:

```java
char[] chars = {'A', 'B', 'C', 'D', 'E'};
StringBuilder sb = new StringBuilder();

sb.append(chars, 1, 3);
System.out.println(sb); // BCD: offset=1, len=3
```

Khi thao tác với UTF-16, cả hai overload đều cần chỉ số hợp lệ, đồng thời lập trình viên phải tự bảo vệ ranh giới Unicode nếu muốn không cắt giữa cặp surrogate.

## 14. Các trường hợp `null` và overload dễ gây ngạc nhiên

### 14.1. `append` không phải phương pháp xác minh dữ liệu đầu vào

Với một số overload, `null` được biểu diễn thành bốn ký tự `"null"`:

```java
String text = null;
StringBuilder sb = new StringBuilder();

sb.append("Giá trị: ").append(text);
System.out.println(sb); // Giá trị: null
```

Khi dữ liệu đầu vào có thể thiếu, nên quyết định rõ giá trị thay thế:

```java
String label = text == null ? "(trống)" : text;
sb.append(" / ").append(label);
```

Đừng suy diễn rằng **mọi** overload hoặc constructor của `StringBuilder` nhận `null` như nhau: một số lời gọi khác có thể ném `NullPointerException`. Hãy dựa vào chữ ký và tài liệu API thực tế.

### 14.2. `append(char[])` khác `append(Object)`

```java
char[] letters = {'J', 'D', 'K'};

System.out.println(new StringBuilder().append(letters));          // JDK
System.out.println(new StringBuilder().append((Object) letters)); // Dạng như [C@...
```

Khi đối số là `char[]`, overload tương ứng thêm **nội dung mảng ký tự**. Khi ép thành `Object`, Java sử dụng cách biểu diễn đối tượng mảng, thường không phải văn bản người đọc muốn thấy.

Nếu dữ liệu có kiểu `Object` nhưng thực chất chứa `char[]`, cần xử lý kiểu trước, không chỉ `append(obj)` và mong nó tự hiển thị đẹp. Vấn đề tương tự có thể gặp với mảng khác: khi cần hiển thị nội dung, hãy dùng `Arrays.toString` hoặc `Arrays.deepToString` theo cấu trúc dữ liệu.

### 14.3. `StringBuilder` không ghi đè `equals` theo nội dung

`StringBuilder` triển khai `Comparable<StringBuilder>` nhưng **không ghi đè `Object.equals`**. Đừng dùng `builderA.equals(builderB)` để so sánh văn bản:

```java
StringBuilder a = new StringBuilder("abc");
StringBuilder b = new StringBuilder("abc");

System.out.println(a.equals(b)); // false: hai object riêng biệt
System.out.println(a.toString().equals(b.toString())); // true
```

Khi cần lưu khóa trong `HashMap` hoặc so sánh nội dung, dùng `String` đã hoàn tất thường hợp lý hơn builder mutable. Đặc biệt thận trọng khi đưa `StringBuilder` vào các collection có quy tắc sắp xếp hay so sánh: `compareTo` so sánh nội dung, còn `equals` vẫn giữ ngữ nghĩa identity.

## 15. An toàn luồng và vòng đời của builder

`StringBuilder` **không bảo đảm đồng bộ hóa**. Hai luồng cùng `append`, `delete` hoặc `toString` trên cùng một builder mà không có điều phối phù hợp có thể tạo hành vi không nhất quán.

**Thiết kế khuyến nghị:** sử dụng builder **cục bộ**, thuộc phạm vi một lần gọi hàm hoặc một tác vụ; không chia sẻ builder mutable cho các luồng khác.

```java
static String makeMessage(String user, int count) {
    StringBuilder sb = new StringBuilder();
    sb.append(user).append(": ").append(count);
    return sb.toString();
}
```

Trong ví dụ này mỗi lần gọi tạo builder riêng. Dù nhiều luồng gọi `makeMessage` cùng lúc, chúng không cùng sửa một builder.

API `StringBuffer` vẫn được hỗ trợ và có cơ chế đồng bộ hóa trên các phương thức thích hợp. Tuy nhiên, không nên mặc định dùng `StringBuffer` cho code mới khi builder chỉ dùng trong một luồng; nếu có trạng thái chia sẻ giữa nhiều luồng, phải thiết kế đồng bộ hóa của **toàn bộ quy trình** cho đúng, không dựa vào một lớp mutable để giải quyết mọi vấn đề đồng thời.

Một lưu ý khác: nếu đối tượng nguồn (chẳng hạn một `CharSequence` mutable) bị luồng khác sửa ngay trong lúc builder đọc dữ liệu từ nó, việc đồng bộ hóa trên builder **không đủ** để bảo đảm nội dung nguồn nhất quán.

## 16. Ghép văn bản không đồng nghĩa với escape dữ liệu

Nhiều lỗi an toàn xuất hiện khi ghép chuỗi thành một **ngôn ngữ khác**:

- **SQL:** Không nối dữ liệu người dùng vào câu SQL. Dùng `PreparedStatement` với tham số.
- **HTML:** Escape nội dung người dùng theo ngữ cảnh HTML trước khi đưa vào trang.
- **JSON:** Dùng công cụ serialize JSON phù hợp, không tự nối dấu ngoặc kép và dấu phẩy.
- **CSV:** Xử lý dấu phẩy, xuống dòng và dấu ngoặc kép theo quy tắc CSV; `String.join` không tự thực hiện.
- **URL:** Dùng API mã hóa hoặc xây dựng URI theo đúng từng thành phần, không nối thô dữ liệu đầu vào.

`StringBuilder` có thể là công cụ hiệu quả để dựng văn bản, nhưng **không tự làm sạch dữ liệu**. Chọn đúng API biểu diễn/escape chuyên biệt quan trọng hơn việc nối bằng `+` hay `append`.

## 17. Các lỗi lựa chọn API thường gặp

| Cách làm | Vấn đề | Cách làm phù hợp hơn |
| --- | --- | --- |
| Dùng `StringBuilder` cho mọi `"A" + value + "B"` | Mã dài, khó đọc mà chưa chắc nhanh hơn | Dùng `+` cho biểu thức ngắn |
| Dùng `result += part` hàng nghìn lần | Tạo giá trị chuỗi mới liên tục khi tích lũy | Một `StringBuilder` cho cả quá trình |
| Tự viết logic “thêm dấu phẩy trừ phần tử cuối” | Dễ lỗi biên và tăng mã | `String.join`, `StringJoiner` hoặc `Collectors.joining` |
| Dùng `String.format` để nối vài chuỗi thường | Cú pháp phức tạp không cần thiết | Dùng `+` |
| Gọi `builder.toString()` ở mọi vòng lặp | Có thể tạo nhiều bản chuỗi trung gian | Chuyển thành `String` khi cần kết quả |
| Dùng `builder.length()` để đếm ký tự hiển thị | `length` đếm đơn vị UTF-16 | Xem xét code point/grapheme tùy yêu cầu |
| Chia sẻ một builder cho nhiều luồng | Không có bảo đảm thread safety | Tạo builder cục bộ hoặc thiết kế đồng bộ hóa |
| Dùng `builder.equals(otherBuilder)` để so văn bản | `equals` vẫn theo identity | So sánh `String` hoặc dùng API nội dung phù hợp |
| Đưa `StringBuilder` vào khóa định danh | Mutable, không có value equality | Hoàn tất và dùng `String` bất biến |
| Coi `String.join` là serializer CSV/JSON | Không xử lý escape và schema | Dùng API chuyên biệt |
| Cấp phát capacity rất lớn cho mọi yêu cầu | Giữ bộ nhớ không cần thiết | Chỉ dự trù khi có kích thước ước lượng đáng tin cậy |
| Dùng `setLength(0)` để “xóa bí mật” | Không cam kết xóa sạch bộ đệm | Áp dụng mô hình xử lý dữ liệu nhạy cảm thích hợp |

## 18. Một quy trình lựa chọn nhanh

Khi cần tạo văn bản trong Java 27, có thể tự hỏi theo thứ tự:

1. **Chỉ ghép hai đến vài giá trị?** Dùng `+` nếu dễ đọc.
2. **Có tập phần tử và dấu phân cách?** Dùng `String.join`.
3. **Có pipeline xử lý `Stream`?** Dùng `Collectors.joining`.
4. **Thêm dần phần tử kèm dấu phân cách và dấu bao?** Dùng `StringJoiner`.
5. **Xây dựng nhiều đoạn theo vòng lặp/nhánh điều kiện?** Dùng `StringBuilder`.
6. **Cần số, ngày, tiền tệ hoặc cột có định dạng?** Dùng formatter tương ứng với loại dữ liệu.
7. **Chỉ có văn bản nhiều dòng cố định?** Dùng text block.
8. **Dữ liệu đầu ra là SQL, HTML, JSON, CSV hoặc URL?** Dùng API chuyên biệt cho ngữ cảnh và escape.
9. **Đầu ra rất lớn hoặc gửi đến stream/file?** Cân nhắc ghi từng phần vào `Writer`/`Appendable` để tránh giữ toàn bộ trong RAM.
10. **Hiệu năng thực sự là vấn đề?** Đo trên workload và JDK được triển khai, rồi mới tối ưu chi tiết.

Một nguyên tắc có thể nhớ ngắn gọn: **`String` dùng để biểu diễn giá trị văn bản; `StringBuilder` dùng để tích lũy văn bản; các API `join`/`format` dùng để biểu đạt cấu trúc và định dạng của văn bản**.

## 19. Tài liệu Java SE 27

- [`java.lang.StringBuilder` — API Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/StringBuilder.html): builder mutable, `append`, `insert`, `capacity`, `ensureCapacity`, `appendCodePoint`, vấn đề đa luồng và so sánh.
- [`java.lang.String` — API Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/String.html): tính bất biến, `join`, `formatted`, `format`, chuyển thành chuỗi.
- [`java.util.StringJoiner` — API Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/StringJoiner.html): dấu phân cách, tiền tố/hậu tố và giá trị rỗng.
- [`java.util.stream.Collectors` — API Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Collectors.html): các overload `joining` dùng với stream.
- [`java.util.Formatter` — API Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Formatter.html): quy tắc định dạng số, chuỗi và locale.
- [`java.io.Writer` — API Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/io/Writer.html): ghi dữ liệu ký tự tới đích thay vì luôn dựng một chuỗi hoàn chỉnh.
- [Java Language Specification 27 — §15.18.1, String Concatenation Operator `+`](https://docs.oracle.com/javase/specs/jls/se27/html/jls-15.html#jls-15.18.1): semantics của `+` khi nối chuỗi.
- [JEP 280 — Indify String Concatenation](https://openjdk.org/jeps/280): bối cảnh cơ chế biên dịch phép nối chuỗi hiện đại; chi tiết bytecode không nên trở thành giả định của ứng dụng.
