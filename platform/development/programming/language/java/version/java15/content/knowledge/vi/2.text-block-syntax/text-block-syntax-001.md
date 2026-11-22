# Text block và biểu diễn chuỗi nhiều dòng trong Java 15+

## Mục tiêu bài học

Sau bài này, bạn có thể đọc và viết text block (khối văn bản) để biểu diễn chuỗi nhiều dòng trong Java; dự đoán chính xác ký tự xuống dòng, khoảng trắng và dấu nháy được lưu vào `String`; lựa chọn giữa text block, string literal thông thường và cách tạo chuỗi động; đồng thời tránh các lỗi thường gặp khi nhúng JSON, SQL, HTML hoặc dữ liệu kiểm thử.

**Phạm vi phiên bản:** Text block là cú pháp Java chính thức từ **Java 15 (JEP 378)** và vẫn được hỗ trợ trong các phiên bản Java hiện đại. Đây là một cách viết giá trị `java.lang.String`, không phải kiểu dữ liệu mới, không phải raw string và không tự động nội suy biến.

## 1. Text block giải quyết vấn đề gì?

Với dấu nháy kép thông thường (`"..."`), một chuỗi trải qua nhiều dòng phải biểu diễn dấu xuống dòng bằng `\n` và thường phải escape `"` nằm bên trong. Ví dụ sau đặt trong một phương thức:

```java
String traditional = "{\n" +
                     "  \"name\": \"Lan\"\n" +
                     "}\n";

String textBlock = """
        {
          "name": "Lan"
        }
        """;

System.out.println(traditional.equals(textBlock)); // true
```

Cả hai tạo ra **cùng một `String`**: `"{\n  \"name\": \"Lan\"\n}\n"`. Text block giúp giữ cấu trúc nhiều dòng ngay trong mã nguồn, đặc biệt hữu ích cho JSON, HTML, SQL, XML, thông báo dài và dữ liệu mẫu. Nó chỉ thay đổi cách *biểu diễn* chuỗi trong source code; các thao tác như `length()`, `equals()`, `contains()` hay truyền vào phương thức đều hoạt động như với `String` thông thường.

## 2. Cú pháp mở và đóng text block

```java
String greeting = """
        Xin chào,
        Chào mừng đến với Java!
        """;
```

Một text block có ba thành phần:

1. **Dấu mở** `"""`, theo sau chỉ bởi khoảng trắng ngang tùy chọn rồi **bắt buộc xuống dòng**. Vì vậy `String s = """hello""";` là cú pháp sai.
2. **Nội dung** từ dòng kế tiếp, có thể gồm nhiều dòng và dấu `"` thông thường mà không cần `\"`.
3. **Dấu đóng** `"""`. Vị trí của nó ảnh hưởng đến khoảng trắng đầu dòng và dấu xuống dòng cuối.

Dấu xuống dòng ngay sau dấu mở chỉ kết thúc dòng cú pháp, **không tạo thêm một dòng trống ở đầu giá trị**. Ở ví dụ trên, chuỗi thực tế là `"Xin chào,\nChào mừng đến với Java!\n"`: có đúng một `\n` giữa hai dòng và một `\n` sau dấu chấm than.

Một text block cũng có thể chứa chuỗi rỗng:

```java
String empty = """
        """;
System.out.println(empty.isEmpty()); // true
```

Với chuỗi chỉ có một dòng ngắn, `String name = "Lan";` thường dễ đọc hơn text block.

## 3. Ba bước Java xử lý nội dung text block

Khi biên dịch, Java xác định giá trị text block về cơ bản theo thứ tự:

1. **Chuẩn hóa dấu kết thúc dòng** trong nội dung nguồn (`CRLF` hay `CR` thành `LF`, tức `\n`). Vì vậy giá trị text block không tự đổi thành `\r\n` khi chạy trên Windows.
2. **Loại khoảng trắng thụt lề phụ (incidental indentation) và khoảng trắng thừa cuối dòng**. Java xét lề chung của những dòng nội dung không rỗng và vị trí dấu đóng để tách lề dùng định dạng source khỏi lề cần giữ trong dữ liệu.
3. **Xử lý escape sequence** như `\n`, `\t`, `\\`, `\s` và ký tự nối dòng `\`. Escape được xử lý sau bước tước khoảng trắng, vì thế có thể dùng nó để cố ý giữ khoảng trắng cuối dòng.

Thứ tự này quan trọng: một dấu cách thường ở cuối dòng có thể bị loại bỏ, còn `\s` được biến thành dấu cách ở bước cuối nên được giữ lại.

### 3.1. Lề chung không trở thành nội dung chuỗi

```java
String tree = """
        root
          child
            leaf
        """;

System.out.println(tree.equals("root\n  child\n    leaf\n")); // true
```

Kết quả lưu trong `tree` là:

```text
root
  child
    leaf
```

Dòng `root` không có khoảng trắng đầu; `child` giữ hai khoảng trắng và `leaf` giữ bốn khoảng trắng theo cấp phân cấp. Các khoảng trắng dùng để canh mã Java bên trái được loại bỏ.

**Lưu ý về dấu đóng:** Lề của dòng chứa `"""` cũng ảnh hưởng đến lượng khoảng trắng bị loại. Thông thường hãy đặt dấu đóng cùng mức lề với các dòng nội dung ít thụt lề nhất. Nếu cố ý đưa dấu đóng sang trái, phần lề đầu các dòng có thể trở thành dữ liệu. Tránh trộn tab và space trong lề của cùng text block vì chiều rộng hiển thị của tab có thể gây nhầm lẫn.

### 3.2. Có hay không có `\n` ở cuối chuỗi?

**Có dấu xuống dòng cuối** khi dấu đóng đứng riêng ở dòng sau nội dung:

```java
String withFinalNewline = """
        first
        second
        """;

System.out.println(withFinalNewline.equals("first\nsecond\n")); // true
```

**Không có dấu xuống dòng cuối** nếu dấu đóng đứng ngay sau ký tự cuối:

```java
String withoutFinalNewline = """
        first
        second""";

System.out.println(withoutFinalNewline.equals("first\nsecond")); // true
```

Cách khác, giữ dấu đóng trên một dòng riêng và dùng **backslash cuối dòng** để bỏ `\n` đó:

```java
String alsoWithoutFinalNewline = """
        first
        second\
        """;

System.out.println(alsoWithoutFinalNewline.equals("first\nsecond")); // true
```

Dấu `\` phải là ký tự cuối của dòng nội dung; không đặt ký tự khác phía sau nó. Khác biệt một `\n` có thể làm kiểm thử `equals()` thất bại hoặc khiến định dạng tệp, request body hay snapshot bị lệch.

### 3.3. Nối dòng nguồn nhưng không chèn dấu xuống dòng

Ký tự `\` ngay trước dấu xuống dòng cho phép chia một dòng dài trong mã nguồn mà vẫn tạo **một dòng văn bản**:

```java
String sentence = """
        Học Java \
        từ ví dụ thực tế.\
        """;

System.out.println(sentence.equals("Học Java từ ví dụ thực tế.")); // true
```

Các dấu cách giữa hai cụm từ ở kết quả trên đến từ dấu cách trước `\` ở dòng thứ nhất. Khi không cần nối dòng đặc biệt, hãy để các dòng xuất hiện tự nhiên.

### 3.4. Giữ khoảng trắng ở cuối dòng bằng `\s`

Khoảng trắng gõ trực tiếp ở cuối dòng text block thường bị loại. Nếu một định dạng thật sự cần dấu cách cuối dòng, dùng escape `\s`, biểu diễn đúng một dấu cách:

```java
String padded = """
        X\s
        Y\s
        """;

System.out.println(padded.equals("X \nY \n")); // true
```

Trong các trường hợp cần nhiều dấu cách, có thể viết nhiều `\s` hoặc dùng escape dấu cách dạng octal `\040`. Không dùng `\u0020` để thay thế cho trường hợp này: Unicode escape của Java được xử lý quá sớm để bảo vệ khoảng trắng cuối dòng.

## 4. Dấu nháy kép, backslash và các escape còn hiệu lực

Text block giúp giảm escape, nhưng **không phải raw string**:

- Các dấu `"` đơn hoặc đôi nằm trong nội dung thường có thể viết trực tiếp, rất tiện cho HTML/JSON.
- Nếu muốn thể hiện ba dấu nháy kép liên tiếp mà không kết thúc text block, hãy escape ít nhất một dấu nháy trong chuỗi ba dấu đó; viết `\"\"\"` là một cách tường minh.
- Các escape Java vẫn hoạt động: `\n` (LF), `\r` (CR), `\t` (tab), `\\` (backslash), `\"` (dấu nháy kép), `\s` (dấu cách) và `\` trước line terminator (bỏ xuống dòng).
- Khi cần ký tự backslash thực sự, phải escape thành `\\`. Ví dụ nguồn Java `"C:\\temp\\logs"` và text block chứa `C:\\temp\\logs` đều tạo các ký tự backslash, nhưng text block thường không phải lựa chọn tốt cho một đường dẫn ngắn.

Ví dụ nhúng dấu nháy mà không cần escape phần HTML:

```java
String html = """
        <a href="https://example.com" title="Java">Đọc thêm</a>
        """;
```

Ví dụ thực sự cần ba dấu nháy kép trong nội dung:

```java
String threeQuotes = """
        Ba dấu nháy kép: \"\"\"
        """;

System.out.println(threeQuotes.endsWith("\"\"\"\n")); // true
```

Phải phân biệt hai thứ: dấu `"` của nội dung thông thường với bộ ba `"""` có thể bị hiểu thành dấu đóng.

## 5. Ứng dụng thực tế

### 5.1. Nhúng JSON hoặc HTML có cấu trúc

```java
String json = """
        {
          "id": 101,
          "name": "Lan",
          "roles": ["reader", "writer"],
          "active": true
        }
        """;
```

Các dấu nháy kép JSON dễ đọc hơn nhiều so với cách nối literal bằng `+`. Nội dung vẫn là `String`, chưa được parse hay xác thực là JSON. Nếu JSON chứa **dữ liệu động hoặc không đáng tin**, hãy dùng thư viện JSON để serialize và escape đúng dữ liệu, thay vì tự ghép giá trị vào dấu nháy.

### 5.2. Viết câu lệnh SQL nhiều dòng

```java
String sql = """
        SELECT id, title
        FROM books
        WHERE category_id = ?
        ORDER BY title
        """;
```

Cách trình bày giữ nguyên bố cục truy vấn. Khi truyền giá trị người dùng vào SQL, hãy dùng `PreparedStatement` và bind tham số cho dấu `?`. Text block chỉ cải thiện khả năng đọc mã; bản thân nó **không** ngăn SQL injection.

### 5.3. Tạo thông báo có chỗ điền dữ liệu

```java
String message = """
        Xin chào, %s!
        Bạn có %d thông báo mới.\
        """.formatted("Lan", 3);

System.out.println(message.equals(
        "Xin chào, Lan!\nBạn có 3 thông báo mới.")); // true
```

`String.formatted(...)` là phương pháp thay chỗ dành sẵn theo quy tắc định dạng, khác với nội suy biến tự động. Kiểm soát dữ liệu đầu vào khi tạo JSON, HTML, SQL hoặc văn bản thuộc định dạng đặc biệt vì `formatted` không tự escape theo từng định dạng.

### 5.4. Khi nội dung cần tạo từ nhiều dòng động

Nếu các dòng đến từ danh sách, file hoặc kết quả tính toán lúc chạy, hãy dùng API thích hợp như `String.join("\n", lines)` hoặc `StringBuilder`. Text block phù hợp nhất khi **bố cục phần lớn đã biết tại thời điểm viết mã nguồn**.

## 6. Ví dụ hoàn chỉnh có thể biên dịch/chạy

Lưu mã sau thành tệp `TextBlockDemo.java` (UTF-8). Chương trình kiểm tra các khác biệt dễ bị nhầm thay vì phụ thuộc vào cách terminal hiển thị khoảng trắng.

```java
public class TextBlockDemo {
    public static void main(String[] args) {
        String traditional = "{\n  \"name\": \"Lan\"\n}\n";
        String json = """
                {
                  "name": "Lan"
                }
                """;

        String noFinalNewline = """
                line 1
                line 2\
                """;

        String trailingSpace = """
                X\s
                """;

        String greeting = """
                Hello, %s!\
                """.formatted("Lan");

        System.out.println("same=" + traditional.equals(json));
        System.out.println("endsNL=" + json.endsWith("\n"));
        System.out.println("noFinalNL="
                + noFinalNewline.equals("line 1\nline 2"));
        System.out.println("trailingSpace="
                + trailingSpace.equals("X \n"));
        System.out.println("greeting=" + greeting);
    }
}
```

Biên dịch/chạy bằng JDK 15 trở lên (ví dụ JDK 17, 21 hoặc mới hơn):

```bash
javac -encoding UTF-8 TextBlockDemo.java
java TextBlockDemo
```

**Stdout chính xác:**

```text
same=true
endsNL=true
noFinalNL=true
trailingSpace=true
greeting=Hello, Lan!
```

Ý nghĩa kiểm thử: `same=true` chứng tỏ text block và literal có thể tạo cùng giá trị; `endsNL=true` thể hiện dấu xuống dòng cuối khi dấu đóng đứng riêng; `noFinalNL=true` xác nhận `\` bỏ dấu xuống dòng cuối; `trailingSpace=true` xác nhận `\s` giữ một dấu cách. Không cần bật preview flag vì text block đã là tính năng chính thức từ Java 15.

## 7. Lỗi thường gặp và cách kiểm tra

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `String s = """abc""";` báo lỗi cú pháp | Sau dấu mở `"""` phải có line terminator | Đưa nội dung xuống dòng sau dấu mở hoặc dùng literal `"abc"` |
| So sánh nội dung khác dù nhìn giống nhau | Có hoặc thiếu `\n` ở cuối | Kiểm tra `endsWith("\n")` hoặc `equals(...)`; chọn vị trí dấu đóng/`\` có chủ đích |
| Chuỗi có quá nhiều/thiếu khoảng trắng đầu dòng | Lề chung và lề dấu đóng được tính vào phép loại khoảng trắng | Căn dấu đóng theo lề nội dung, dùng space nhất quán; kiểm tra giá trị thật |
| Dấu cách cuối dòng bị mất | Java loại trailing whitespace của text block | Dùng `\s` hoặc `\040` khi đúng là cần giữ |
| Đường dẫn chứa `\t` hoặc `\n` không như mong đợi | Text block vẫn xử lý escape | Escape backslash thành `\\` hoặc dùng literal thích hợp |
| Muốn nhúng ba dấu `"` liên tiếp | Bộ ba `"""` có thể đóng text block | Escape ít nhất một dấu nháy trong chuỗi đó |
| Nội dung JSON/SQL động bị lỗi hoặc không an toàn | Text block không tự serialize/escape/bind | Dùng thư viện JSON hoặc `PreparedStatement` phù hợp |
| Kết quả không phù hợp khi di chuyển giữa hệ điều hành | Text block chuẩn hóa newline thành `\n` | Xác định định dạng đầu ra cần LF hay CRLF; nếu thật sự cần, chuyển đổi tại ranh giới xuất dữ liệu |

Khi muốn phát hiện lề không nhất quán hoặc trailing space bị tước ngoài ý muốn, có thể biên dịch với cảnh báo của `javac`:

```bash
javac -Xlint:text-blocks -encoding UTF-8 TextBlockDemo.java
```

**Mẹo tự kiểm tra:** Đối với dữ liệu mà byte/ký tự có ý nghĩa (snapshot, chuỗi ký, payload, file xuất), hãy so sánh `equals` với giá trị kỳ vọng hoặc viết unit test; chỉ `println` có thể che dấu space cuối dòng. Khi tạo dữ liệu xuất ra file, xác định yêu cầu newline rõ ràng thay vì dựa vào hình thức trong trình soạn thảo.

## 8. Chọn cách biểu diễn chuỗi phù hợp

| Nhu cầu | Gợi ý |
| --- | --- |
| Chuỗi ngắn, một dòng | Literal `"..."` |
| Nội dung cố định nhiều dòng, có JSON/HTML/SQL dễ đọc | Text block `""" ... """` |
| Nhiều dòng phát sinh động từ danh sách | `String.join`, `StringBuilder` hoặc API chuyên biệt |
| Chèn một số chỗ dành sẵn vào mẫu văn bản đơn giản | Text block kết hợp `.formatted(...)`; kiểm soát quy tắc escape |
| Tạo JSON/SQL có dữ liệu từ bên ngoài | JSON serializer hoặc truy vấn tham số hóa; text block chỉ giữ vai trò trình bày mẫu |

## Ghi nhớ

**Text block = một cách khai báo `String` nhiều dòng đã ổn định từ Java 15.** Hãy luôn tự hỏi: chuỗi có `\n` ở cuối hay không, phần lề nào được giữ, có escape nào được diễn giải và nội dung động có cần API xử lý riêng không. Trả lời đúng bốn câu hỏi đó sẽ giúp sử dụng text block nhất quán trong mã Java hiện đại.

### Tài liệu chính thức

- [OpenJDK JEP 378 — Text Blocks](https://openjdk.org/jeps/378)
- [Oracle — Programmer's Guide to Text Blocks](https://docs.oracle.com/en/java/javase/25/text-blocks/index.html)
- [Oracle — Text Blocks trong Java](https://docs.oracle.com/en/java/javase/25/language/text-blocks.html)
- [Java Language Specification — Text Blocks, §3.10.6](https://docs.oracle.com/javase/specs/jls/se26/html/jls-3.html#jls-3.10.6)
