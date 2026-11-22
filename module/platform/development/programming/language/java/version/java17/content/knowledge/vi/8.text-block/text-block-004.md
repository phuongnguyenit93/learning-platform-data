# Dòng trống, khoảng trắng cuối dòng và ký tự xuống dòng trong Java 17 Text Block

Khi viết chuỗi nhiều dòng bằng **text block** (`"""`) trong Java 17, hình thức của mã nguồn ảnh hưởng trực tiếp đến giá trị `String` được tạo ra. Một dòng trống có thể tạo thêm ký tự xuống dòng; khoảng trắng ở cuối dòng thường bị loại bỏ; vị trí dấu `"""` đóng quyết định chuỗi có kết thúc bằng xuống dòng hay không.

Những khác biệt này đặc biệt quan trọng với **HTML, SQL, JSON, CSV, email, định dạng văn bản, file cấu hình và các giao thức nhạy cảm với dấu cách/ký tự xuống dòng**. Nếu chỉ nhìn kết quả bằng `System.out.println`, người học rất dễ không nhận ra một dấu cách hoặc một ký tự `\n` bị thừa hay thiếu.

**Text block là tính năng chính thức trong Java 17**, đã được chuẩn hóa từ Java 15 (JEP 378). Các ví dụ dưới đây biên dịch bằng JDK 17 bình thường, không cần `--enable-preview`.

## 1. Nhắc lại cú pháp text block

Một text block bắt đầu bằng ba dấu nháy kép và **phải có ký tự kết thúc dòng sau dấu mở**:

~~~java
String message = """
        Xin chào,
        Java 17!
        """;
~~~

Chuỗi tạo ra tương đương với:

~~~java
String message = "Xin chào,\nJava 17!\n";
~~~

Trong ví dụ, phần thụt lề dùng để trình bày mã Java **không tự động trở thành** những khoảng trắng đứng đầu chuỗi; Java xử lý phần thụt lề ngẫu nhiên (*incidental indentation*) trước khi tạo `String`.

Cú pháp sau **không hợp lệ** vì có nội dung ngay sau dấu mở thay vì xuống dòng:

~~~java
// Sai cú pháp text block:
// String message = """Xin chào!""";
~~~

Nếu nội dung chỉ có một dòng, có thể dùng string literal thông thường:

~~~java
String message = "Xin chào!";
~~~

Hoặc vẫn dùng text block với dấu mở ở dòng riêng:

~~~java
String message = """
        Xin chào!""";
~~~

Cả hai trường hợp cuối đều có nội dung `Xin chào!` và **không có** ký tự xuống dòng cuối chuỗi.

## 2. Ba bước Java xử lý nội dung text block

Có thể hiểu cách Java 17 tạo nội dung `String` từ text block qua ba giai đoạn:

1. **Chuẩn hóa dấu kết thúc dòng:** các dấu kết thúc dòng vật lý trong mã nguồn `CRLF` (`\r\n`) và `CR` (`\r`) được chuẩn hóa thành `LF` (`\n`) trong nội dung text block.
2. **Loại bỏ khoảng trắng ngẫu nhiên:** Java xác định phần thụt lề chung cần xóa, đồng thời loại bỏ khoảng trắng thừa cuối mỗi dòng theo quy tắc text block.
3. **Diễn giải các escape sequence:** chẳng hạn `\n`, `\t`, `\s` và dấu `\` dùng để nối dòng được xử lý sau bước loại bỏ khoảng trắng.

**Thứ tự xử lý rất quan trọng.** Đặc biệt, `\s` là chuỗi ký tự `\` và `s` ở giai đoạn loại bỏ khoảng trắng; đến giai đoạn diễn giải escape, nó mới trở thành **một dấu cách thật**. Vì vậy `\s` có thể giữ khoảng trắng cuối dòng mà dấu cách gõ trực tiếp không giữ được.

Ví dụ:

~~~java
String text = """
        Java\s
        17
        """;
~~~

Giá trị thu được là:

~~~text
"Java \n17\n"
~~~

Trong chuỗi trên, ngay trước `\n` đầu tiên có **một dấu cách U+0020**, được tạo bởi `\s`.

Trong tài liệu này, khi cần thể hiện chính xác giá trị chuỗi, ta dùng ký hiệu:

| Ký hiệu trong phần giải thích | Ý nghĩa |
| --- | --- |
| `\n` | Một ký tự xuống dòng LF (U+000A) |
| `\r` | Một ký tự carriage return (U+000D) |
| `\t` | Một ký tự tab (U+0009) |
| `␠` | Một dấu cách U+0020; chỉ là ký hiệu để nhìn, không nằm trong chuỗi |
| `⏎` | Vị trí kết thúc dòng; chỉ là ký hiệu trực quan |

Khi viết `"A\nB\n"` trong phần giải thích, đó là **cách ghi giá trị chuỗi bằng string literal Java**, không có nghĩa text block chứa hai ký tự in được `\` và `n`.

## 3. Dấu xuống dòng cuối chuỗi: phụ thuộc vị trí `"""` đóng

Đây là khác biệt đầu tiên cần nắm khi soạn text block.

### 3.1. Dấu đóng ở dòng riêng: thường có `\n` cuối

~~~java
String withFinalNewline = """
        alpha
        beta
        """;
~~~

Giá trị:

~~~java
"alpha\nbeta\n"
~~~

Có hai ký tự `\n`: một sau `alpha`, một sau `beta`. Dấu `\n` cuối xuất hiện vì dòng chứa `beta` kết thúc trước khi đến dòng đặt dấu `"""` đóng.

### 3.2. Dấu đóng ngay sau nội dung: không tự thêm `\n` cuối

~~~java
String withoutFinalNewline = """
        alpha
        beta""";
~~~

Giá trị:

~~~java
"alpha\nbeta"
~~~

Ở đây, `beta` nằm cùng dòng với dấu `"""` đóng. Không có một line terminator vật lý nằm giữa `beta` và dấu đóng, nên chuỗi không có `\n` cuối.

### 3.3. So sánh bằng chương trình

~~~java
public class ClosingDelimiterDemo {
    public static void main(String[] args) {
        String a = """
                alpha
                beta
                """;

        String b = """
                alpha
                beta""";

        System.out.println(a.equals("alpha\nbeta\n")); // true
        System.out.println(b.equals("alpha\nbeta"));    // true
        System.out.println(a.length()); // 11
        System.out.println(b.length()); // 10
    }
}
~~~

Lưu thành `ClosingDelimiterDemo.java` và chạy:

~~~bash
javac --release 17 -encoding UTF-8 ClosingDelimiterDemo.java
java ClosingDelimiterDemo
~~~

Kết quả:

~~~text
true
true
11
10
~~~

Đối với ví dụ trên, chênh lệch chiều dài đúng một ký tự vì chuỗi `a` có thêm `\n` cuối.

### 3.4. Dấu xuống dòng cuối có ý nghĩa nghiệp vụ

| Tình huống | Thường cần gì? | Cách viết |
| --- | --- | --- |
| File văn bản theo quy ước kết thúc mỗi dòng bằng LF | Có `\n` cuối | Đặt `"""` đóng ở dòng mới |
| Thông điệp ngắn, cần trùng khớp chuỗi chính xác | Có thể không có `\n` cuối | Đặt `"""` đóng ngay sau nội dung |
| SQL gửi cho JDBC | Nhiều trường hợp có/không có LF cuối đều được parser chấp nhận | Chọn nhất quán, kiểm tra khi so sánh chuỗi |
| Nội dung ký số, checksum, snapshot test | Mọi byte đều quan trọng | Xác định rõ ký tự cuối và charset |

**Không nên tùy tiện gọi `strip()` chỉ để “xóa newline dư”**: `strip()` xóa cả khoảng trắng đầu và cuối của *toàn bộ chuỗi*, có thể làm mất ký tự có ý nghĩa. Nếu hợp đồng chỉ yêu cầu bỏ đúng một `\n` cuối, xử lý có mục tiêu hoặc đặt dấu đóng đúng vị trí ngay từ mã nguồn.

## 4. Dòng trống bên trong text block

**Dòng trống** là một dòng không có nội dung hiển thị giữa hai line terminator. Khi viết một dòng trống thật trong text block, dòng đó vẫn tham gia vào giá trị chuỗi.

~~~java
String paragraph = """
        Đoạn thứ nhất.

        Đoạn thứ hai.
        """;
~~~

Giá trị tương đương:

~~~java
"Đoạn thứ nhất.\n\nĐoạn thứ hai.\n"
~~~

Hai `\n` liên tiếp giữa hai đoạn văn tạo một dòng trống. Để tạo **hai dòng trống** giữa chúng, cần ba `\n` liên tiếp.

### 4.1. Một dòng trống khác một dấu cách

Các giá trị dưới đây không giống nhau:

~~~java
String blankLine = "A\n\nB";
String spaceLine = "A\n \nB";

System.out.println(blankLine.equals(spaceLine)); // false
~~~

Giá trị thứ hai có một dấu cách trên dòng ở giữa. Nhưng nếu bạn **gõ dấu cách trực tiếp trên một dòng trống trong nguồn text block**, quá trình xử lý khoảng trắng có thể loại bỏ chúng. Do đó, đừng dùng những dấu cách vô hình để biểu diễn dữ liệu quan trọng.

### 4.2. Dòng trống có khoảng trắng thật khi cần

Nếu định dạng bắt buộc một dòng chứa một dấu cách, có thể dùng escape `\s` trên dòng đó:

~~~java
String lineWithSpace = """
        A
        \s
        B
        """;
~~~

Giá trị:

~~~java
"A\n \nB\n"
~~~

Dòng ở giữa không còn là chuỗi độ dài 0: nó chứa đúng một ký tự space. Việc dùng `\s` giúp người đọc nhận ra có chủ đích một dấu cách và tránh editor tự xóa.

### 4.3. Nhầm lẫn khi hiển thị dòng trống

~~~java
String content = """
        A

        B
        """;

System.out.print(content);
~~~

Console hiển thị:

~~~text
A

B
~~~

Nhưng việc nhìn terminal khó phân biệt một chuỗi **có LF cuối** và một chuỗi **không có LF cuối**, vì cả hai có thể trông như cùng một đoạn hiển thị. Khi cần kiểm tra chính xác, hãy dùng `equals()`, `length()` hoặc một cách hiển thị escape như phần sau; đừng dựa vào mắt nhìn khoảng cách trên terminal.

## 5. Khoảng trắng ở cuối dòng thường bị loại bỏ

Một đặc điểm của text block là Java xử lý **trailing whitespace** trong nguồn. Những dấu cách và tab gõ trực tiếp ở cuối dòng có thể bị xóa khi text block được biến thành `String`.

Ví dụ ý nghĩa của đoạn sau:

~~~java
String text = """
        left
        right
        """;
~~~

Là:

~~~java
"left\nright\n"
~~~

Nếu người viết thêm vài dấu cách sau `left` rồi mới bấm Enter, Java vẫn loại bỏ khoảng trắng cuối dòng trong quá trình xử lý text block thông thường. Vì vậy không nên cố tạo nội dung `"left  \n"` bằng cách gõ hai dấu cách vô hình sau chữ `left`.

**Tác động thực tế:**

- Trong Markdown, hai dấu cách cuối dòng đôi khi mang nghĩa xuống dòng cưỡng bức.
- Trong định dạng cố định cột (*fixed-width*), dấu cách ở cuối trường có thể là dữ liệu.
- Trong email hoặc giao thức truyền văn bản, khoảng trắng cuối dòng có thể ảnh hưởng đến so sánh byte, chữ ký hoặc checksum.
- Trong kiểm thử, expected string có thể sai nếu người viết tưởng rằng những dấu cách vô hình đã được giữ lại.

Nếu dấu cách cuối dòng cần thiết, sử dụng escape `\s`.

## 6. Giữ dấu cách cuối dòng bằng `\s`

Trong Java 17, `\s` là escape biểu diễn **một dấu cách thường** (U+0020). Escape này hợp lệ trong string literal và text block.

~~~java
String text = """
        item:\s
        next
        """;
~~~

Kết quả:

~~~java
"item: \nnext\n"
~~~

Có một dấu cách ngay sau dấu `:` và ngay trước ký tự LF.

### 6.1. Giữ nhiều dấu cách

~~~java
String twoSpaces = """
        value\s\s
        next
        """;

System.out.println(twoSpaces.equals("value  \nnext\n")); // true
~~~

Hai `\s` tạo hai dấu cách ở cuối dòng. Cách ghi này rõ ý định hơn việc chèn hai dấu cách vô hình trong mã nguồn.

### 6.2. Dùng `\s` để giữ khoảng trắng sau một từ

~~~java
String aligned = """
        code:\s\s
        17
        """;
~~~

Giá trị:

~~~java
"code:  \n17\n"
~~~

Chú ý dấu cách do `\s` tạo ra **không phải ký tự xuống dòng**. Nó chỉ là ký tự U+0020. Dấu xuống dòng vẫn đến từ việc kết thúc dòng vật lý trong text block.

### 6.3. Tab và dấu cách không giống nhau

Java có `\t` cho ký tự tab U+0009; `\s` cho dấu cách U+0020.

~~~java
String withTab = """
        A\tB
        """;

String withSpaces = """
        A\s\s\s\sB
        """;

System.out.println(withTab.equals(withSpaces)); // false
~~~

Dù ở terminal chúng có thể trông gần giống nhau, dữ liệu thực tế khác nhau. Đối với định dạng cố định cột, nên xác định yêu cầu dùng tab hay space thay vì dựa vào độ rộng hiển thị của editor.

### 6.4. Vì sao `\s` có thể sống sót qua bước loại bỏ khoảng trắng?

Trong mã nguồn, đoạn `value\s` kết thúc bằng ký tự `s`, không phải một dấu cách thật. Java bỏ trailing whitespace **trước** khi diễn giải escape. Sau bước bỏ whitespace, `\s` mới được chuyển thành một dấu cách trong chuỗi kết quả.

Thứ tự này giải thích tại sao việc viết `\s` ở cuối dòng hoạt động, trong khi gõ trực tiếp một dấu cách ở cuối dòng có thể không.

## 7. Thụt lề chung và thụt lề có chủ đích

Phần thụt lề ở đầu dòng thường được thêm để mã Java dễ đọc. Text block cố gắng xóa lượng thụt lề **ngẫu nhiên** đó, đồng thời giữ lại phần thụt lề **có ý nghĩa**.

~~~java
String text = """
        first
          second
        third
        """;
~~~

Giá trị tương đương:

~~~java
"first\n  second\nthird\n"
~~~

Hai dấu cách trước `second` là **chênh lệch thụt lề có chủ đích** so với `first` và `third`, nên được giữ lại.

### 7.1. Vị trí dấu đóng cũng tác động thụt lề

Xét:

~~~java
String normal = """
        A
          B
        """;
~~~

Giá trị:

~~~java
"A\n  B\n"
~~~

Nhưng nếu đưa dấu đóng về gần lề trái hơn:

~~~java
String padded = """
        A
          B
    """;
~~~

Giá trị:

~~~java
"    A\n      B\n"
~~~

Khi dấu đóng ở dòng riêng, độ thụt lề của nó tham gia vào việc xác định phần thụt lề ngẫu nhiên cần xóa. Ở ví dụ thứ hai, dấu đóng chỉ thụt bốn dấu cách nên mỗi dòng nội dung giữ lại thêm bốn dấu cách so với ví dụ đầu.

Vì thế, **thay đổi vị trí dấu `"""` đóng có thể làm thay đổi cả nội dung chuỗi**, không chỉ hình thức mã nguồn. Điều này rất đáng lưu ý khi IDE tự căn lề hoặc người viết dịch chuyển block mã.

### 7.2. Dòng trống không dùng để giữ indentation

Dòng trống hoặc dòng chỉ chứa khoảng trắng được xử lý riêng khi tính incidental indentation. Việc gõ nhiều dấu cách trên một dòng trống không phải cách đáng tin cậy để tạo indentation trong dữ liệu kết quả.

Nếu cần một dòng “trống” nhưng chứa khoảng trắng, dùng `\s` như mục 4; nếu cần indentation đặc biệt cho một dòng có nội dung, thể hiện khoảng cách tương đối rõ ràng.

## 8. Chuẩn hóa kiểu xuống dòng về LF

Hệ điều hành hoặc editor có thể lưu line ending trong file nguồn theo nhiều cách:

| Cách kết thúc dòng trong source | Ký tự/chuỗi thường gặp | Nội dung text block sau chuẩn hóa |
| --- | --- | --- |
| LF | `\n` | `\n` |
| CRLF | `\r\n` | `\n` |
| CR | `\r` | `\n` |

Do đó, text block Java 17 tạo nội dung với ký tự xuống dòng LF, dù file nguồn được lưu theo CRLF ở Windows.

Ví dụ với một text block gồm hai dòng và có dấu đóng ở dòng riêng:

~~~java
String text = """
        A
        B
        """;
~~~

Giá trị kỳ vọng là:

~~~java
"A\nB\n"
~~~

Điều này giúp những chuỗi văn bản nhiều dòng từ text block ít phụ thuộc hơn vào line ending vật lý của hệ điều hành.

### 8.1. Nếu hệ thống bên ngoài bắt buộc CRLF

Một số giao thức yêu cầu chuỗi `\r\n`. Đừng giả định text block tự dùng CRLF khi chạy trên Windows. Hãy quyết định rõ việc chuyển đổi tại **ranh giới xuất dữ liệu**:

~~~java
String message = """
        Line 1
        Line 2
        """;

String withCrlf = message.replace("\n", "\r\n");

System.out.println(withCrlf.equals("Line 1\r\nLine 2\r\n"));
// true
~~~

Đoạn chuyển đổi trên phù hợp khi đầu vào đã được chuẩn hóa về LF, như text block này. Nếu dữ liệu đầu vào có thể chứa CRLF từ trước, cần chuẩn hóa trước khi thay thế để tránh biến `\r\n` thành `\r\r\n`.

Khi ghi file, nên chọn charset rõ ràng:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

String content = """
        Line 1
        Line 2
        """;

Files.writeString(
        Path.of("output.txt"),
        content,
        StandardCharsets.UTF_8
);
~~~

Đoạn trên ghi các ký tự LF có sẵn trong `content` dưới dạng UTF-8; `Files.writeString` không tự biến các LF này thành CRLF chỉ vì hệ điều hành là Windows.

### 8.2. Phân biệt xuống dòng của dữ liệu với xuống dòng để hiển thị

`System.out.println(text)` luôn thêm một dấu xuống dòng **sau toàn bộ chuỗi được in**. Nếu `text` đã có LF cuối, lời gọi có thể tạo cảm giác xuất hiện thêm một dòng trống.

~~~java
String text = """
        Hello
        """;

System.out.println(text);
~~~

`text` đã tương đương `"Hello\n"`; `println` thêm thêm một dấu kết thúc dòng do phương thức in, nên hiển thị có thể xuất hiện một dòng trống.

Khi muốn xem chính xác nội dung text block mà không thêm ký tự xuống dòng của API in, dùng:

~~~java
System.out.print(text);
~~~

Điểm khác biệt ở đây là giữa **dữ liệu của `String`** và **ký tự do lệnh in thêm vào**.

## 9. Nối hai dòng mã nguồn thành một dòng chuỗi bằng dấu `\`

Đôi khi muốn xuống dòng trong **mã Java** cho dễ đọc nhưng không muốn xuống dòng trong **giá trị String**. Trong text block Java 17, đặt một dấu `\` ngay trước line terminator có thể biểu diễn **line continuation**.

~~~java
String joined = """
        Hello, \
        Java 17!
        """;
~~~

Giá trị:

~~~java
"Hello, Java 17!\n"
~~~

Dấu `\` cuối dòng thứ nhất làm cho ký tự xuống dòng vật lý giữa `Hello, ` và `Java 17!` **không xuất hiện** trong kết quả.

So sánh:

~~~java
String separate = """
        Hello,
        Java 17!
        """;

String joined = """
        Hello, \
        Java 17!
        """;

System.out.println(separate.equals("Hello,\nJava 17!\n")); // true
System.out.println(joined.equals("Hello, Java 17!\n"));    // true
~~~

### 9.1. Dấu cách trước `\` vẫn có ý nghĩa

Ở ví dụ `Hello, \` có một dấu cách giữa dấu phẩy và dấu `\`. Dấu cách đó nằm trước dấu escape, không phải dấu cách cuối dòng bị bỏ, nên trong kết quả còn lại `Hello, Java 17!`.

Nếu viết:

~~~java
String joined = """
        Hello,\
        Java 17!
        """;
~~~

Thì kết quả là:

~~~java
"Hello,Java 17!\n"
~~~

Không có dấu cách giữa `Hello,` và `Java`.

### 9.2. `\` nối dòng khác `\n` thêm dòng

| Cách viết bên trong text block | Tác động |
| --- | --- |
| Nhấn Enter kết thúc dòng | Tạo LF trong chuỗi |
| Viết `\n` ở một vị trí | Tạo thêm ký tự LF tại vị trí escape |
| Viết `\` ngay trước kết thúc dòng | Không tạo LF ở vị trí kết thúc dòng đó |
| Viết `\s` | Chèn một dấu cách thường |

Phân biệt rõ hai vai trò trái ngược:

- `\n` **thêm** ký tự newline vào chuỗi.
- `\` nối dòng **loại bỏ** newline do kết thúc dòng nguồn.

Một lỗi thường gặp là dùng `\n` ở cuối một dòng đã có xuống dòng vật lý, vô tình tạo **hai LF liên tiếp**.

~~~java
String text = """
        A\n
        B
        """;

System.out.println(text.equals("A\n\nB\n")); // true
~~~

Trong trường hợp cần một dòng trống giữa `A` và `B`, cách dễ đọc hơn thường là gõ **một dòng trống thật** trong text block (mục 4), thay vì thêm escape `\n` ở cuối dòng rồi lại Enter.

### 9.3. Đừng thêm ký tự sau backslash nối dòng

Để `\` nối dòng có tác dụng, dấu này phải đứng trực tiếp trước line terminator được escape. Nếu có khoảng trắng vô hình sau `\`, nó không còn là cùng một escape nối dòng như mong muốn và có thể gây lỗi cú pháp hoặc tạo kết quả ngoài dự kiến.

Nên để công cụ định dạng và quy tắc editor hiển thị rõ trailing whitespace, đồng thời viết test cho các chuỗi mà newline có ý nghĩa.

## 10. Kết hợp dòng trống, `\s` và dấu đóng trong ví dụ thực tế

Xét một mẫu nội dung Markdown:

~~~java
String markdown = """
        # Release notes

        Version: 17

        - Fixed bug
        - Added feature
        """;
~~~

Kết quả chứa các dòng:

~~~text
# Release notes
[trống]
Version: 17
[trống]
- Fixed bug
- Added feature
[LF cuối]
~~~

Các ký hiệu trong dấu ngoặc vuông ở sơ đồ trên chỉ dùng để giải thích, không thuộc chuỗi thật.

Nếu muốn giữ hai dấu cách Markdown ở cuối dòng nhằm tạo hard line break:

~~~java
String markdown = """
        Dòng một\s\s
        Dòng hai
        """;
~~~

Giá trị:

~~~java
"Dòng một  \nDòng hai\n"
~~~

Hai dấu cách cuối `Dòng một` được tạo có chủ đích. Nếu chỉ gõ hai space trực tiếp cuối dòng trong mã nguồn, kết quả text block có thể bị bỏ mất chúng.

### 10.1. SQL nhiều dòng

~~~java
String sql = """
        SELECT id, full_name
        FROM customers
        WHERE status = ?
        ORDER BY id
        """;
~~~

Giá trị có LF sau mỗi dòng, kể cả dòng `ORDER BY id`. Đây là cách trình bày dễ đọc cho SQL trong mã Java 17. Khi dùng `PreparedStatement`, dấu `?` là parameter marker để bind giá trị; không ghép dữ liệu người dùng trực tiếp vào SQL bằng nội suy chuỗi.

Nếu thư viện hoặc test snapshot yêu cầu SQL **không có LF cuối**, đặt dấu `"""` ngay sau dòng cuối:

~~~java
String sql = """
        SELECT id, full_name
        FROM customers
        WHERE status = ?
        ORDER BY id""";
~~~

Hai biến trên không bằng nhau theo `String.equals()` vì biến đầu có LF cuối. Trong một số bộ kiểm thử kiểm tra nguyên văn SQL, khác biệt này cần được tính đến.

### 10.2. Nội dung căn cột

~~~java
String report = """
        ITEM      QTY
        Apple       2
        Orange      10
        """;
~~~

Khoảng trắng **ở giữa** các token vẫn được giữ theo nội dung có ý nghĩa sau khi Java bỏ thụt lề chung; text block không tự co mọi khoảng trắng liên tiếp thành một dấu cách. Chỉ khoảng trắng ngẫu nhiên ở đầu dòng và trailing whitespace mới cần lưu ý.

### 10.3. Một ví dụ kết hợp có giá trị chính xác

~~~java
String payload = """
        BEGIN\s
       
        DATA=17\s\s
        END""";
~~~

Trong nguồn ở trên, dòng nằm giữa `BEGIN` và `DATA=17` được để trống; người đọc không cần đặt space vô hình ở đó. Giá trị cần hiểu là:

~~~java
"BEGIN \n\nDATA=17  \nEND"
~~~

- Sau `BEGIN` có **một space** nhờ `\s`.
- Giữa `BEGIN` và `DATA=17` có **một dòng trống**.
- Sau `DATA=17` có **hai space** nhờ `\s\s`.
- Sau `END` **không** có LF cuối vì dấu đóng đi cùng dòng.

Nếu chuỗi dùng để ký số hoặc so sánh byte, cả bốn điểm này đều ảnh hưởng kết quả.

## 11. Cách quan sát chính xác ký tự ẩn

### 11.1. So sánh với string literal chuẩn

Đơn giản nhất là kiểm tra:

~~~java
String text = """
        A

        B
        """;

System.out.println(text.equals("A\n\nB\n")); // true
~~~

Đoạn kiểm tra này đồng thời xác minh số dòng trống và dấu newline cuối.

### 11.2. Hiển thị các ký tự theo dạng dễ nhìn

Tạo file **`TextBlockInspector.java`**:

~~~java
public final class TextBlockInspector {

    private TextBlockInspector() {
    }

    static String visible(String value) {
        return value
                .replace(" ", "␠")
                .replace("\t", "\\t")
                .replace("\r", "\\r")
                .replace("\n", "\\n\n");
    }

    public static void main(String[] args) {
        String text = """
                A\s\s

                B
                """;

        System.out.print(visible(text));
        System.out.println("length=" + text.length());
    }
}
~~~

Chạy với Java 17:

~~~bash
javac --release 17 -encoding UTF-8 TextBlockInspector.java
java TextBlockInspector
~~~

Đầu ra mong đợi:

~~~text
A␠␠\n
\n
B\n
length=7
~~~

Chuỗi có bảy ký tự: `A` (1), hai space (2), hai LF trước `B` (2), `B` (1) và LF cuối (1). Trong output, chuỗi `\n` được in bằng hai ký tự nhìn thấy được, còn ký tự LF thật dùng để chuyển sang dòng hiển thị tiếp theo.

**Lưu ý:** `visible()` ở trên là công cụ minh họa, không phải định dạng escape tổng quát: chuỗi gốc có dấu `␠` thật sẽ khó phân biệt với dấu cách đã được thay thế. Để đối chiếu byte trong giao thức, nên xem byte array bằng công cụ hex hoặc bộ test chuyên dụng.

### 11.3. Đếm ký tự LF

~~~java
String text = """
        one

        two
        """;

long count = text.chars()
        .filter(c -> c == '\n')
        .count();

System.out.println(count); // 3
~~~

Đếm LF giúp phát hiện dòng trống và newline cuối mà không phụ thuộc cách terminal hiển thị.

### 11.4. Hiểu giới hạn của `String.lines()`

`String.lines()` tách chuỗi thành stream các dòng nội dung; nó không phải công cụ bảo toàn nguyên vẹn mọi dấu phân cách dòng. Chẳng hạn:

~~~java
String text = "A\nB\n";

System.out.println(text.lines().toList()); // [A, B]
~~~

Kết quả danh sách không thể cho biết ban đầu có LF cuối hay không nếu chỉ nhìn hai phần tử. Khi mục tiêu là kiểm tra **dữ liệu gốc chính xác**, hãy dùng `equals()`, đếm ký tự hoặc `split("\n", -1)` để giữ phần tử cuối rỗng:

~~~java
String text = "A\nB\n";

String[] pieces = text.split("\n", -1);
System.out.println(pieces.length); // 3
System.out.println(pieces[2].isEmpty()); // true
~~~

Đây là cách làm hữu ích trong unit test của serializer, parser hoặc template nhạy cảm với ký tự xuống dòng.

## 12. Những lỗi dễ gặp

| Hiện tượng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Text block không biên dịch | Có nội dung ngay sau dấu `"""` mở, không có line terminator | Xuống dòng ngay sau dấu mở |
| Chuỗi có LF cuối dù không muốn | Dấu `"""` đóng đặt ở dòng riêng | Đưa dấu đóng ngay sau ký tự nội dung cuối |
| Chuỗi thiếu LF cuối | Dấu đóng nằm cùng dòng nội dung cuối | Chuyển dấu đóng sang dòng riêng hoặc thêm LF có chủ đích |
| Hai dòng bị tách khi chỉ muốn một dòng | Có newline vật lý giữa chúng | Dùng line continuation `\` hoặc một chuỗi một dòng |
| Hai dòng bị dính liền | Dùng `\` nối dòng nhưng không để dấu cách cần thiết | Thêm dấu cách trước `\` hoặc cấu trúc lại câu |
| Dấu cách cuối dòng biến mất | Trailing whitespace bị Java loại bỏ | Dùng `\s` cho mỗi dấu cách cần giữ |
| Xuất hiện thêm dòng trống | Có một dòng trống thật hoặc thêm `\n` trên dòng đã kết thúc bằng newline | Kiểm tra chuỗi bằng `equals`, giảm newline thừa |
| Chuỗi bị thụt lề không mong muốn | Dấu đóng được chuyển về lề trái hoặc indentation không đều | Kiểm tra thụt lề chung và vị trí dấu đóng |
| Trên Windows muốn CRLF nhưng nhận LF | Text block chuẩn hóa line ending thành LF | Chuyển đổi có chủ đích ở ranh giới xuất dữ liệu |
| `println` tạo khoảng trắng lớn ở cuối | Chuỗi đã có LF cuối, `println` thêm line terminator nữa | Dùng `print` hoặc chủ động kiểm soát LF cuối |
| Test snapshot thất bại dù màn hình nhìn giống nhau | Khác space, tab hoặc newline | Kiểm tra độ dài, mã ký tự, escape hoặc byte thực tế |
| Editor tự xóa trailing spaces | Các space vốn không ổn định khi viết cuối dòng nguồn | Thể hiện dữ liệu quan trọng bằng `\s` |

Đối với nội dung text block nhạy cảm với byte, tránh dùng các thao tác “dọn dẹp” tùy tiện như `trim()`, `strip()` hoặc `stripTrailing()` sau mỗi lần tạo chuỗi. Những phương thức đó có mục đích riêng nhưng có thể xóa cả dấu cách có nghĩa và line terminator cần thiết.

## 13. Bài tập thực hành

### Bài 1 — Xác định newline cuối

Cho hai text block:

~~~java
String first = """
        A
        B
        """;

String second = """
        A
        B""";
~~~

Hãy viết các string literal thông thường tương đương, tính `length()` và giải thích vì sao hai chuỗi khác nhau dù các dòng chữ nhìn thấy đều là `A` và `B`.

### Bài 2 — Dòng trống

Tạo một text block chứa ba tiêu đề `Title`, `Body` và `Footer`, với **một dòng trống** giữa mỗi cặp; giữ LF cuối. Dùng `equals()` để đối chiếu với:

~~~java
"Title\n\nBody\n\nFooter\n"
~~~

Sau đó thay mỗi dòng trống bằng một dòng chứa `\s` và quan sát sự khác biệt về giá trị String.

### Bài 3 — Khoảng trắng cuối dòng

Viết một text block có giá trị chính xác:

~~~java
"Name: An  \nAge: 17 \n"
~~~

Yêu cầu: dùng `\s` để giữ hai space sau `An` và một space sau `17`, không chèn những dấu cách vô hình trực tiếp ở cuối dòng nguồn.

### Bài 4 — Điều chỉnh dấu đóng và indentation

Tạo text block với hai dòng, trong đó dòng thứ hai thụt sâu hơn dòng đầu **ba dấu cách**. Chuyển dấu đóng từ mức thụt lề ngang các dòng nội dung sang gần lề trái hơn. Dùng `equals()` để giải thích giá trị thay đổi như thế nào.

### Bài 5 — CRLF cho output giao thức

Tạo một text block nội dung:

~~~text
HEADER
BODY
END
~~~

Có LF cuối. Chuyển toàn bộ LF thành CRLF trước khi ghi UTF-8. Viết điều kiện xác nhận chuỗi sau chuyển đổi bằng:

~~~java
"HEADER\r\nBODY\r\nEND\r\n"
~~~

### Bài 6 — Loại bỏ một newline bằng line continuation

Dùng `\` ở cuối dòng nguồn để tạo giá trị:

~~~java
"Hello, Java 17!\n"
~~~

từ text block có từ `Hello,` và `Java 17!` ở **hai dòng mã nguồn khác nhau**. Giải thích tại sao vẫn giữ một LF cuối dù newline giữa hai phần câu đã bị loại.

## 14. Nguyên tắc cần nhớ

Một text block Java 17 là một `String` thông thường ở runtime, nhưng giá trị đó được tạo từ mã nguồn sau các bước **chuẩn hóa line ending**, **xử lý incidental/trailing whitespace** và **diễn giải escape sequence**.

- Dòng trống thật tạo ra những LF liên tiếp; đừng nhầm dòng trống với một dòng chứa space.
- Dấu đóng `"""` ở dòng riêng thường làm chuỗi có LF cuối; đặt ngay sau nội dung cuối sẽ không thêm LF đó.
- Dấu cách/tab gõ trực tiếp ở cuối dòng có thể bị loại; dùng `\s` để giữ space có ý nghĩa.
- Text block chuẩn hóa CR/CRLF vật lý thành LF; muốn CRLF cho giao thức thì chuyển đổi rõ ràng lúc xuất.
- `\` ở cuối dòng nguồn bỏ newline của chính dòng đó, còn `\n` thêm một ký tự newline.
- Khi độ chính xác từng ký tự quan trọng, dùng điều kiện so sánh, kiểm tra độ dài hoặc quan sát byte thay vì chỉ nhìn nội dung in trên console.

Nắm chắc các quy tắc này giúp tận dụng độ dễ đọc của text block trong Java 17 mà vẫn kiểm soát chính xác khoảng trắng, dòng trống và ký tự xuống dòng trong dữ liệu cuối cùng.
