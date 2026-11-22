# Escape \s để giữ dấu cách cần thiết trong Java text block

Trong Java, **text block** là cách khai báo một chuỗi `String` nhiều dòng bằng dấu mở và dấu đóng `"""`. Java tự bỏ phần thụt lề phụ và khoảng trắng thừa ở cuối dòng trong text block. Khi văn bản **thực sự cần một hoặc nhiều dấu cách ở vị trí đó**, escape `\s` giúp biểu diễn chúng một cách tường minh và ổn định.

Quy tắc này là một phần của Java 15 và vẫn áp dụng trong các phiên bản Java hiện đại. Bài học tập trung vào tác dụng thực tế của `\s`, thứ tự xử lý khoảng trắng và cách kiểm chứng giá trị chuỗi.

## 1. Chính xác thì \s có nghĩa gì?

Trong mã nguồn Java, escape `\s` gồm hai ký tự viết liền nhau: dấu gạch chéo ngược `\${T} và chữ thường `s`. Khi trình biên dịch diễn giải escape, hai ký tự này trở thành **một dấu cách thông thường**:

- Ký tự đầu ra là **SPACE**, mã Unicode `U+0020` (giá trị ASCII 32).
- `\s` không tạo tab, không tạo xuống dòng và không tạo ký tự khoảng trắng đặc biệt như *non-breaking space* (`U+00A0`).
- `\s\s\s` tạo **ba dấu cách**, vì mỗi `\s` tạo đúng một dấu cách.
- Escape `\s` được hỗ trợ trong cả text block **và** string literal thông thường của Java 15+, nhưng đặc biệt có ích trong text block vì trình biên dịch tự xử lý khoảng trắng.

Hai biểu thức Java sau có cùng nội dung:

```java
String a = "A\sB";
String b = "A B";
System.out.println(a.equals(b)); // true
```

Mỗi chuỗi là `"A B"`, có đúng một dấu cách giữa `A` và `B`. Trong trường hợp một dòng bình thường như thế này, viết dấu cách trực tiếp vẫn dễ đọc; mục đích chính của `\s` trong text block là làm **dấu cách cần giữ** trở nên rõ ràng, nhất là ở cuối dòng.

## 2. Vì sao phải dùng \s ở cuối dòng?

Giả sử bạn muốn một dòng văn bản kết thúc bằng dấu cách ngay **trước** ký tự xuống dòng. Việc gõ dấu cách thật ở cuối dòng mã nguồn có hai vấn đề:

1. Trình biên dịch Java tự loại bỏ khoảng trắng *incidental* ở cuối mỗi dòng text block, nên các dấu cách gõ trực tiếp có thể không còn trong giá trị `String`.
2. Nhiều trình soạn thảo tự xóa khoảng trắng cuối dòng; phần này cũng khó nhận biết bằng mắt.

Ví dụ **đúng và dễ đọc**:

```java
String message = """
        Hello\s
        World
        """;
```

Sau xử lý, giá trị chính xác của `message` là `"Hello \nWorld\n"`. Cụ thể:

- Sau `Hello` còn **một dấu cách thực** do `\s` tạo ra.
- Sau dấu cách ấy là ký tự xuống dòng `\n` được giữ từ cuối dòng văn bản.
- Dấu xuống dòng cuối chuỗi vẫn có vì dấu đóng `"""` nằm trên dòng riêng.

Nếu bỏ `\s` trong ví dụ, dòng đầu sẽ có giá trị `"Hello\n"` khi ghép với phần còn lại. **`\s` không thay thế `\n` và không tự xóa dòng mới.**

## 3. Vì sao \s không bị Java xóa như dấu cách thường?

Giá trị text block trải qua các bước sau, theo đúng thứ tự của Java Language Specification:

1. **Chuẩn hóa ký tự kết thúc dòng:** những cách xuống dòng trong mã nguồn như CRLF và CR được chuẩn hóa về LF (`\n`).
2. **Loại bỏ khoảng trắng phụ:** Java xử lý thụt lề chung và loại bỏ khoảng trắng ở cuối dòng. Ở giai đoạn này, đoạn mã `\s` **vẫn là hai ký tự** `\${T} và `s`; chữ `s` không phải khoảng trắng nên không bị cắt đi.
3. **Diễn giải escape:** sau khi loại khoảng trắng phụ, Java mới chuyển `\s` thành **một dấu cách thật**. Vì bước loại khoảng trắng đã xong, dấu cách vừa tạo sẽ được giữ lại.

Có thể hình dung dòng `Hello\s` như sau:

```text
Mã nguồn (sau phần thụt lề):   Hello\s
Sau bước loại khoảng trắng:   Hello\s
Sau bước diễn giải escape:    Hello·
```

Ở đây ký hiệu `·` chỉ dùng để **minh họa một dấu cách**; nó không xuất hiện trong `String` thực tế.

Điểm then chốt là `\s` được chuyển thành dấu cách **sau khi** Java hoàn tất quá trình xóa khoảng trắng ở cuối dòng. Đây cũng là lý do escape này giúp giữ khoảng trắng một cách đáng tin cậy.

## 4. Giữ một hoặc nhiều dấu cách

### Cách 1: Một \s cho một dấu cách

```java
String one = """
        red\s
        green
        """;
```

Giá trị: `"red \ngreen\n"`. Sau `red` có đúng **một** dấu cách.

### Cách 2: Lặp \s để giữ số dấu cách chính xác

```java
String three = """
        red\s\s\s
        """;
```

Giá trị: `"red   \n"`. Sau `red` có **ba** dấu cách trước `\n`. Cách này rất tường minh khi cần số lượng dấu cách cố định.

### Cách 3: Dùng \s làm điểm chặn (*fence*) ở cuối dòng

```java
String fenced = """
        red  \s
        """;
```

Giá trị cũng là `"red   \n"`. Trong mã nguồn có **hai dấu cách thông thường** giữa `red` và `\s`; chính `\s` tạo dấu cách thứ ba. Vì dòng kết thúc bằng chữ `s` của escape, hai dấu cách trước nó không còn nằm **cuối dòng mã nguồn** để bị xóa ở bước xử lý khoảng trắng.

Điều này hữu ích khi muốn viết một vài dấu cách dễ nhìn bên cạnh dấu chặn `\s`. Tuy nhiên, nếu quy trình format mã nguồn có thể thay đổi độ rộng khoảng trắng bên trong text block, viết `\s\s\s` sẽ diễn đạt số lượng dấu cách một cách ít mơ hồ hơn.

### So sánh ba biến

| Cách viết trước dấu xuống dòng | Số dấu cách sau `red` | Biểu diễn kết quả |
| --- | ---: | --- |
| `red` | 0 | `red\n` |
| `red\s` | 1 | `red \n` |
| `red\s\s\s` | 3 | `red   \n` |
| `red  \s` (2 dấu cách thật + 1 escape) | 3 | `red   \n` |

Trong bảng, đoạn `\n` biểu diễn **một ký tự xuống dòng**, không phải hai ký tự chữ `\${T} và `n` trong giá trị.

## 5. Dùng \s ở đầu dòng hoặc bên trong dòng

Mặc dù bài toán phổ biến nhất là **giữ dấu cách cuối dòng**, `\s` cũng có thể dùng ở vị trí khác.

Ví dụ dấu cách đầu nội dung:

```java
String leading = """
        \sred
        """;
```

Giá trị: `" red\n"`. Java loại bỏ phần thụt lề phụ của mã nguồn, sau đó mới chuyển `\s` đứng trước chữ `r` thành **một dấu cách có ý nghĩa**.

Với khoảng trắng giữa các từ:

```java
String middle = """
        red\sgreen
        """;
```

Giá trị: `"red green\n"`. Viết `red green` trực tiếp cũng cho giá trị này và thường dễ đọc hơn. Chỉ dùng `\s` tại vị trí có lý do rõ ràng, ví dụ cần phân biệt chính xác ký tự khoảng trắng trong đoạn dữ liệu hoặc ở cuối dòng.

**Phân biệt với điều chỉnh thụt lề:** `\s` có thể thêm dấu cách tường minh sau khi Java bỏ lề, nhưng nó không tự thay đổi thuật toán tính mức thụt lề chung của text block. Thụt lề chung vẫn được xác định từ các dòng nội dung và vị trí dấu đóng.

## 6. Đặt dấu đóng ở đâu khi cần dấu cách cuối chuỗi?

Escape `\s` chỉ tạo dấu cách; dấu đóng text block quyết định có giữ ký tự xuống dòng cuối hay không.

```java
String withFinalNewline = """
        End\s
        """;

String withoutFinalNewline = """
        End\s""";
```

Hai giá trị:

- `withFinalNewline` = `"End \n"`, độ dài **5** (3 chữ, 1 dấu cách, 1 newline).
- `withoutFinalNewline` = `"End "`, độ dài **4** (3 chữ, 1 dấu cách).

Vì vậy, nếu cần chuỗi kết thúc bằng **dấu cách nhưng không có newline**, đặt dấu đóng sát sau escape `\s`. Nếu cần dấu cách trước một newline cuối, đặt dấu đóng trên dòng riêng.

Trong dữ liệu có yêu cầu số byte chính xác, hãy kiểm tra cả khoảng trắng **và** newline để tránh khác biệt do vị trí dấu đóng.

## 7. Ví dụ Java 17+ đầy đủ và kết quả kiểm chứng

Lưu mã sau thành file `TextBlockSpaceEscapeDemo.java` với UTF-8:

```java
public class TextBlockSpaceEscapeDemo {
    private static String visible(String text) {
        // Ký hiệu · thay một dấu cách và \n hiển thị ký tự xuống dòng.
        return text.replace(" ", "·").replace("\n", "\\n");
    }

    public static void main(String[] args) {
        String plain = """
                red
                green
                """;

        String one = """
                red\s
                green
                """;

        String three = """
                red\s\s\s
                """;

        String fenced = """
                red  \s
                """;

        String leading = """
                \sred
                """;

        String inlineClosing = """
                red\s""";

        // \s cũng hợp lệ trong string literal Java thông thường.
        String regularString = "red\s";

        // Hai dấu gạch chéo trong mã nguồn giữ lại một dấu \ thật.
        String literalBackslashS = "red\\s";

        System.out.println("plain=" + visible(plain));
        System.out.println("one=" + visible(one));
        System.out.println("three=" + visible(three));
        System.out.println("fenced=" + visible(fenced));
        System.out.println("leading=" + visible(leading));
        System.out.println("inlineClosing=" + visible(inlineClosing));
        System.out.println("regularString=" + visible(regularString));
        System.out.println("literalBackslashS=" + visible(literalBackslashS));
        System.out.println("sameThreeSpaces=" + three.equals(fenced));
    }
}
```

Biên dịch và chạy trên JDK 17 hoặc mới hơn:

```bash
javac -encoding UTF-8 TextBlockSpaceEscapeDemo.java
java TextBlockSpaceEscapeDemo
```

Đầu ra chính xác, trong đó `·` đại diện một dấu cách, còn `\n` được in thành hai ký tự để nhìn rõ:

```text
plain=red\ngreen\n
one=red·\ngreen\n
three=red···\n
fenced=red···\n
leading=·red\n
inlineClosing=red·
regularString=red·
literalBackslashS=red\s
sameThreeSpaces=true
```

Cách đọc kết quả:

- `plain` không chứa dấu cách sau `red`.
- `one` chứa một dấu cách trước newline; `three` và `fenced` cùng chứa ba dấu cách.
- `leading` giữ dấu cách ở đầu nội dung.
- `inlineClosing` chứa dấu cách cuối nhưng **không chứa newline cuối**.
- `regularString` chứng minh `\s` không bị giới hạn ở text block.
- `literalBackslashS` chứng minh `\\s` trong mã nguồn tạo ra dấu `\${T} và chữ `s`, không chuyển chúng thành dấu cách.

Hàm `visible` chỉ để quan sát ký tự vô hình; nó không thuộc cách Java tự xử lý text block.

## 8. Các nhầm lẫn thường gặp

| Nhầm lẫn | Giải thích đúng | Cách xử lý |
| --- | --- | --- |
| `\s` đại diện một tab | Escape này luôn biểu diễn **một dấu cách U+0020** | Dùng `\t` nếu thực sự cần tab |
| `\s` tạo ra hai ký tự gạch chéo và chữ s trong chuỗi | `\s` được diễn giải thành **một dấu cách** | Nếu muốn giữ nguyên `\s` dạng chữ, viết `\\s` trong source |
| Dấu cách thật gõ cuối dòng luôn được giữ | Java loại bỏ khoảng trắng cuối dòng của text block trước khi diễn giải escape | Đặt `\s` ở cuối dòng |
| `\s\s\s` chỉ tạo một dấu cách | Mỗi escape tương ứng **một dấu cách** | Đếm số escape hoặc kiểm tra độ dài chuỗi |
| Thêm `\s` là mất `\n` sau đó | Escape này không xóa newline | Xem vị trí dấu đóng, hoặc dùng escape nối dòng nếu thực sự muốn bỏ newline |
| Dùng `\u0020` để tránh xóa khoảng trắng cuối dòng | Unicode escape được xử lý **sớm hơn** bước xử lý text block; dấu cách tạo ra có thể bị loại bỏ | Dùng `\s` (hoặc escape bát phân `\040` khi phù hợp) |
| Escape `\s` làm thay đổi cách xác định lề chung | Lề chung được xử lý **trước** khi diễn giải `\s` | Phân biệt dấu cách thêm vào và lề mã nguồn |
| Dùng `\s` mọi nơi cho đẹp | Khi vị trí không nhạy cảm, dấu cách thông thường dễ đọc hơn | Ưu tiên `\s` nơi cần cố định số dấu cách, đặc biệt cuối dòng |

Không nên phụ thuộc vào dấu cách cuối dòng khi các bước xử lý dữ liệu về sau có thể dùng `trim()`, `strip()`, `stripTrailing()` hoặc chuẩn hóa văn bản: những thao tác ấy **có thể xóa dấu cách sau khi chuỗi đã được tạo**. `\s` đảm bảo dấu cách xuất hiện trong giá trị text block lúc biên dịch, không ngăn thao tác khác xóa nó về sau.

## 9. Tự kiểm tra

Xem hai text block sau:

```java
String first = """
        A \s
        """;

String second = """
        A\s\s
        """;
```

Hãy trả lời:

1. Mỗi chuỗi có bao nhiêu dấu cách ngay sau chữ `A`?
2. Cả hai có chứa ký tự xuống dòng cuối chuỗi không?
3. `first.equals(second)` cho kết quả gì?

**Đáp án:** (1) Mỗi chuỗi có **hai dấu cách**: `first` có một dấu cách thường trước `\s` và một dấu cách do escape tạo ra; `second` có hai escape. (2) Có, vì cả hai đặt dấu đóng trên dòng riêng. (3) `true`, vì cả hai đều là `"A  \n"`.

**Tài liệu tham khảo:** [Oracle — Programmer's Guide to Text Blocks: Trailing White Space và The \s Escape Sequence](https://docs.oracle.com/en/java/javase/25/text-blocks/index.html); [Java Language Specification §3.10.6 — Text Blocks](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.6); [Oracle — Text Blocks](https://docs.oracle.com/en/java/javase/25/language/text-blocks.html).