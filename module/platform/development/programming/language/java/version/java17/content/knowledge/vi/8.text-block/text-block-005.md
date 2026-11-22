# Escape `\s` và nối dòng bằng dấu gạch chéo ngược trong text block Java 17

**Chủ đề:** Java 17  
**Chương:** Text block  
**Bài học:** Escape `\s` và nối dòng bằng dấu gạch chéo ngược

Text block giúp khai báo chuỗi nhiều dòng trong Java bằng cặp dấu `"""`, rất hữu ích khi lưu đoạn JSON, SQL, HTML, thông báo nhiều dòng hoặc dữ liệu mẫu. Ngoài việc tự xử lý phần thụt lề không cần thiết, text block còn hỗ trợ hai escape đặc biệt để **kiểm soát chính xác khoảng trắng và ký tự xuống dòng**:

- **`\s`:** Chèn **một dấu cách thông thường** (Unicode U+0020) vào chuỗi kết quả. Đặc biệt hữu ích khi cần giữ dấu cách ở **cuối dòng**, nơi các khoảng trắng viết trực tiếp dễ bị loại bỏ trong quá trình xử lý text block.
- **`\` ngay trước ký tự kết thúc dòng nguồn:** Là *line continuation* — **bỏ ký tự xuống dòng đó khỏi chuỗi kết quả**, để nội dung của dòng nguồn tiếp theo nối ngay vào dòng trước.

Hai escape này có mặt trong tính năng text block được chuẩn hóa từ **Java 15** (JEP 378), vì vậy trên **Java 17** chúng là cú pháp ổn định, không cần bật `--enable-preview`.

> **Ghi nhớ:** `\s` tạo **dấu cách**, còn `\` cuối dòng **loại bỏ một lần xuống dòng**. Dấu gạch chéo ngược ở đây là ký tự `\` (backslash), không phải dấu gạch chéo xuôi `/`.

## 1. Ôn lại cấu trúc text block

Một text block mở đầu bằng ba dấu nháy kép, sau đó **bắt buộc có ký tự kết thúc dòng**; phần nội dung bắt đầu từ dòng tiếp theo:

```java
String message = """
        Xin chào,
        Đây là Java 17.
        """;
```

Giá trị chuỗi thực tế tương đương:

```java
String message = "Xin chào,\nĐây là Java 17.\n";
```

Có ba điểm đáng chú ý:

1. Các khoảng trắng ở đầu dòng trong ví dụ là độ thụt lề phục vụ định dạng mã nguồn. Phần thụt lề chung không trở thành nội dung chuỗi.
2. Ký tự xuống dòng trong text block được chuẩn hóa về **LF (`\n`)** khi xử lý nội dung nguồn, bất kể cách biểu diễn kết thúc dòng của file Java.
3. Vì dấu `"""` đóng nằm ở một dòng riêng, sau `Đây là Java 17.` còn có một ký tự `\n` trong chuỗi kết quả.

Text block vẫn có kiểu **`java.lang.String`**. Nó không tạo một kiểu dữ liệu đặc biệt và cũng không tự động ghép dữ liệu như template string.

### 1.1. Vì sao cần hai escape này?

Hãy tưởng tượng cần tạo kết quả:

```text
A··
B
```

Trong minh họa này, mỗi ký tự `·` tượng trưng cho **một dấu cách thật**. Tức sau chữ `A` có hai dấu cách trước ký tự xuống dòng. Nếu viết hai dấu cách trực tiếp ở cuối dòng text block, chúng có thể bị xóa khi Java xử lý khoảng trắng cuối dòng.

Tương tự, nếu viết:

```java
String text = """
        Java
        17
        """;
```

kết quả chứa `Java\n17\n`. Nhưng đôi khi ta muốn **nguồn vẫn trình bày trên hai dòng** để dễ đọc, còn giá trị chuỗi phải là `Java17\n` hoặc `Java 17\n`. Escape nối dòng giúp kiểm soát điều đó.

## 2. Thứ tự xử lý nội dung text block

Muốn hiểu `\s` và line continuation, cần biết Java không lấy nguyên xi tất cả ký tự nằm giữa `"""`.

Với nội dung text block, compiler xử lý theo ý tưởng gồm ba bước chính:

1. **Chuẩn hóa ký tự kết thúc dòng:** Các dạng xuống dòng trong nguồn, như CR và CRLF, được chuẩn hóa thành LF.
2. **Xử lý khoảng trắng ngẫu nhiên (*incidental white space*):** Loại phần thụt lề chung không cần thiết ở đầu dòng và các khoảng trắng cuối dòng.
3. **Diễn giải escape sequences:** Lúc này mới thay `\s` thành dấu cách, thay `\n` thành ký tự xuống dòng, và xử lý `\` + kết thúc dòng để loại bỏ ký tự xuống dòng đó.

Sơ đồ:

```text
Nội dung giữa """ ... """
          |
          v
Chuẩn hóa line terminators thành LF
          |
          v
Bỏ incidental indentation và trailing whitespace
          |
          v
Diễn giải escape sequences:
  \s        --> dấu cách U+0020
  \ + LF    --> không thêm ký tự xuống dòng
          |
          v
Giá trị String cuối cùng
```

**Hệ quả quan trọng:** `\s` được diễn giải **sau** bước loại khoảng trắng cuối dòng. Khi compiler xét trailing whitespace, ký tự trong mã nguồn vẫn là chuỗi escape `\s` với dấu `\` và chữ `s`, nên phần dấu cách được tạo ra sau đó sẽ được **giữ lại**.

Tương tự, dấu `\` dùng để nối dòng được diễn giải sau khi Java đã xác định và loại phần thụt lề chung. Nhờ vậy, có thể viết hai dòng nguồn có cùng mức thụt lề mà phần thụt lề không len vào giữa chuỗi kết quả.

## 3. Escape `\s`: một dấu cách chính xác

Trong Java 17:

```java
String oneSpace = "\s";
System.out.println(oneSpace.length());     // 1
System.out.println(oneSpace.equals(" ")); // true
```

`\s` đại diện cho **một ký tự space U+0020**. Nó không phải tab, không phải ký tự xuống dòng, và không phải cách viết tắt cho “mọi khoảng trắng”.

Có thể lặp escape nhiều lần:

```java
String twoSpaces = "\s\s";
String threeSpaces = "\s\s\s";

System.out.println(twoSpaces.length());   // 2
System.out.println(threeSpaces.length()); // 3
```

### 3.1. Giữ dấu cách ở cuối dòng text block

```java
String value = """
        A\s\s
        B
        """;
```

Giá trị chính xác tương đương:

```java
String value = "A  \nB\n";
```

Hai `\s` sau `A` tạo **hai dấu cách cuối dòng** trong kết quả. Chúng không bị xóa bởi quy tắc loại trailing whitespace của text block.

Bảng minh họa (ký tự `·` chỉ dùng để dễ nhìn):

| Dòng nguồn trong text block | Dòng của chuỗi kết quả |
|---|---|
| `A\s\s` rồi xuống dòng | `A··` rồi xuống dòng |
| `B` rồi xuống dòng | `B` rồi xuống dòng |

Nếu thay bằng **hai dấu cách gõ trực tiếp** sau chữ `A` trong mã nguồn, chúng sẽ bị coi là trailing whitespace khi xử lý text block. Việc dùng `\s` thể hiện rõ: “đây là những dấu cách có chủ ý, cần tồn tại trong giá trị cuối cùng”.

### 3.2. Giữ một dấu cách phân tách nội dung

```java
String address = """
        Số nhà:\s42
        Đường: Hoa Mai
        """;
```

`\s` giữa `:` và `42` tạo một dấu cách giống ký tự ` ` thông thường:

```text
Số nhà: 42
Đường: Hoa Mai
```

Trong trường hợp dấu cách **nằm giữa** các từ trên cùng dòng, ta vẫn có thể gõ dấu cách trực tiếp. `\s` phát huy giá trị rõ nhất khi dấu cách xuất hiện ở **cuối dòng** hoặc khi muốn thể hiện số lượng dấu cách chính xác và có chủ ý.

### 3.3. `\s` không đại diện cho whitespace của regex

Đây là nhầm lẫn dễ gặp khi dùng Java 17:

```java
String javaSpace = "\s";  // Một dấu cách U+0020
String regexText = "\\s"; // Hai ký tự: backslash và chữ s
```

Trong **regex**, biểu thức `\s` thường đại diện cho nhóm whitespace theo quy tắc của biểu thức chính quy. Nhưng nếu viết literal Java `"\s"`, Java đã **diễn giải escape trước**, regex chỉ nhận được một dấu cách.

Muốn Java `Pattern` nhận biểu thức regex `\s+` để tìm một hoặc nhiều ký tự whitespace:

```java
String normalized = "A\tB\nC".replaceAll("\\s+", " ");
System.out.println(normalized); // A B C
```

Nếu viết `replaceAll("\s+", " ")`, tham số regex trở thành `" +"` — một hoặc nhiều **dấu cách thật**, không xử lý tab và newline theo cách mà regex `\s+` thường làm.

**Phân biệt ba mục đích:**

| Mã Java | Chuỗi thực tế được tạo | Dùng khi |
|---|---|---|
| `"\s"` | Một dấu cách | Cần chèn space U+0020 |
| `"\\s"` | Backslash + chữ `s` | Cần gửi cú pháp `\s` cho regex hoặc dữ liệu văn bản |
| `"\t"` | Một ký tự tab | Cần chèn tab |
| `"\n"` | Một ký tự LF | Cần chèn xuống dòng |

Các quy tắc này áp dụng cho `String` nói chung, không riêng text block.

## 4. Nối dòng bằng `\` ở cuối dòng nguồn

Một dấu gạch chéo ngược ngay trước ký tự kết thúc dòng nguồn tạo **line continuation**: Java không đưa ký tự kết thúc dòng đó vào chuỗi cuối cùng.

Ví dụ:

```java
String joined = """
        Java\
        17
        """;
```

Giá trị thực tế:

```java
String joined = "Java17\n";
```

Mặc dù từ `Java` và `17` nằm trên **hai dòng trong mã nguồn**, chúng trở thành **một dòng nội dung** trong chuỗi kết quả. Vì dấu đóng `"""` nằm ở dòng kế tiếp, chuỗi vẫn kết thúc bằng `\n` sau `17`.

Sơ đồ:

```text
DÒNG NGUỒN                  GIÁ TRỊ CHUỖI

Java\                       Java17\n
17
"""
```

Không có ký tự `\` trong kết quả: dấu gạch chéo ngược là ký hiệu điều khiển việc nối dòng, không phải một ký tự mà ta muốn in ra.

### 4.1. Ghép hai dòng mà không có dấu cách

```java
String code = """
        ABC\
        DEF
        """;

System.out.println(code.equals("ABCDEF\n")); // true
```

Vì không có dấu cách được chèn vào giữa hai phần, kết quả là `ABCDEF`.

### 4.2. Ghép hai dòng nhưng cần một dấu cách

Nối dòng **không tự thêm dấu cách**. Nếu muốn có dấu cách phân tách, hãy ghi rõ:

```java
String sentence = """
        Java\s\
        17
        """;

System.out.println(sentence.equals("Java 17\n")); // true
```

Cách đọc đoạn `Java\s\` ở cuối dòng:

1. `Java` — bốn ký tự chữ.
2. `\s` — chèn **một dấu cách**.
3. `\` ngay trước newline — bỏ newline.
4. Dòng kế tiếp có `17` — được nối vào sau dấu cách.

Vậy kết quả là `Java 17\n`.

Đây là cách kết hợp hai escape rất hữu ích: **`\s` quyết định số dấu cách còn lại; `\` quyết định chỗ nào không được xuống dòng.**

### 4.3. Nối nhiều dòng nguồn thành một dòng chuỗi

```java
String query = """
        SELECT id, name\s\
        FROM users\s\
        WHERE active = true
        """;
```

Giá trị tương đương:

```java
String query =
        "SELECT id, name FROM users WHERE active = true\n";
```

Người đọc mã nguồn vẫn thấy ba phần rõ ràng của câu SQL, còn chuỗi kết quả chỉ có **một dòng** SQL (với một newline cuối chuỗi do vị trí dấu đóng). Việc có newline cuối thường không ảnh hưởng đến câu SQL, nhưng cần xét cụ thể khi truyền chuỗi cho hệ thống bên ngoài.

### 4.4. Dấu `\` phải sát ký tự kết thúc dòng

Phép nối dòng xảy ra khi escape có dạng **backslash ngay sau đó là line terminator**. Vì vậy:

```java
String joined = """
        Hello\
        World
        """;
```

là ví dụ chuẩn. Nếu chèn các dấu cách **sau** `\` và **trước** khi xuống dòng, ta không còn cùng một escape `\` + line terminator. Mã có thể không hợp lệ hoặc tạo hành vi ngoài ý muốn; tránh định dạng lại vùng đó bằng cách thêm khoảng trắng sau dấu gạch chéo ngược.

**Thực hành:** Khi muốn nối dòng, hãy đặt `\` làm ký tự cuối cùng của dòng nguồn, ngay sát newline.

## 5. Nối dòng không đồng nghĩa với bỏ toàn bộ các newline

Dấu `\` ở cuối dòng chỉ loại bỏ **line terminator trực tiếp theo sau nó**.

```java
String text = """
        First\
        Second
        Third
        """;
```

Giá trị:

```java
String text = "FirstSecond\nThird\n";
```

- Newline giữa `First` và `Second` bị bỏ bởi `\`.
- Newline sau `Second` vẫn còn.
- Newline sau `Third` vẫn còn vì dấu đóng ở dòng mới.

Nếu cần nối cả ba phần:

```java
String text = """
        First\
        Second\
        Third
        """;

System.out.println(text.equals("FirstSecondThird\n")); // true
```

Đừng nhầm line continuation với một lệnh “xóa mọi newline có trong text block”.

### 5.1. Loại newline cuối cùng bằng `\`

Mặc định, dấu đóng nằm trên dòng riêng sẽ để lại một `\n` sau dòng nội dung cuối. Nếu không muốn có newline cuối:

```java
String noFinalNewline = """
        Done\
        """;

System.out.println(noFinalNewline.equals("Done")); // true
```

Dấu `\` ngay sau `Done` loại bỏ ký tự xuống dòng nối đến dòng chứa dấu đóng, nên kết quả chỉ có `Done`.

Một cách khác là đặt dấu đóng ngay sau nội dung cuối:

```java
String alsoNoFinalNewline = """
        Done""";

System.out.println(alsoNoFinalNewline.equals("Done")); // true
```

Cả hai hợp lệ. Dùng cách thứ nhất khi muốn **giữ bố cục dấu đóng trên dòng riêng** mà không thêm newline vào giá trị.

## 6. So sánh `\s`, `\n` và line continuation

Ba escape này giải quyết ba nhu cầu khác nhau:

| Cú pháp trong Java source | Tác động lên chuỗi kết quả | Mục đích |
|---|---|---|
| `\s` | Thêm một dấu cách `U+0020` | Giữ/chèn dấu cách |
| `\n` | Thêm một newline `LF` | Chủ động chèn xuống dòng |
| `\` + newline vật lý của source | **Không thêm** newline đó | Nối hai dòng nguồn thành một dòng kết quả |
| `\\` | Thêm một ký tự backslash thật | Muốn chuỗi có dấu `\` |
| Xuống dòng vật lý trong text block, không có `\` | Thêm newline (LF) | Giữ cấu trúc nhiều dòng |

Ví dụ quan sát khác biệt:

```java
String withSpace = """
        A\sB
        """;

String withNewline = """
        A\nB
        """;

String continued = """
        A\
        B
        """;

System.out.println(withSpace.equals("A B\n"));     // true
System.out.println(withNewline.equals("A\nB\n"));  // true
System.out.println(continued.equals("AB\n"));      // true
```

**Điểm dễ nhầm:** Trong `withNewline`, `\n` được viết bên trong cùng một dòng của text block; ngoài ký tự xuống dòng do escape tạo ra, dòng nguồn chứa `B` còn kết thúc bằng một newline vật lý nữa. Bởi vậy kết quả có newline sau `B`.

## 7. Quan hệ với xử lý incidental indentation

Text block được thiết kế để mã nguồn có thể thụt lề theo cấu trúc Java mà giá trị String không bị thụt lề ngoài ý muốn.

```java
String html = """
        <section>
            <h1>Title</h1>
        </section>
        """;
```

Các khoảng trắng chung trước `<section>`, `<h1>`, `</section>` bị loại. Tuy nhiên, phần thụt lề **có chủ ý** của thẻ `<h1>` so với `<section>` vẫn được giữ.

Với line continuation:

```java
String joined = """
        Alpha\
        Beta
        """;
```

Sau khi Java loại phần thụt lề chung, mỗi dòng nội dung thực còn lần lượt `Alpha\` và `Beta`. Bước diễn giải escape bỏ newline giữa chúng, cho kết quả `AlphaBeta\n`.

### 7.1. Không dựa vào dấu cách cuối dòng được gõ thủ công

Một trình soạn thảo có thể tự xóa trailing whitespace khi lưu file. Java cũng có quy tắc loại trailing whitespace trong text block. Vì thế, nếu giá trị chuỗi phải có một số dấu cách **cuối dòng cụ thể**, hãy viết `\s` rõ ràng:

```java
String table = """
        Item:\s\s
        Price:
        """;
```

Điều này giúp người đọc mã và công cụ định dạng dễ nhận ra những dấu cách có ý nghĩa.

### 7.2. Khi cần khoảng trắng đầu dòng có chủ ý

`\s` cũng có thể được dùng để chèn dấu cách ở đầu dòng:

```java
String indented = """
        \s\sChild
        Parent
        """;

System.out.println(indented.equals("  Child\nParent\n")); // true
```

Trong trường hợp này, hai `\s` là **nội dung** cần giữ; không bị xem như độ thụt lề chung của mã nguồn ở bước trước khi xử lý escape.

Tuy nhiên, nếu mục đích là biểu diễn thụt lề cấu trúc thông thường, có thể dùng độ thụt lề tương đối của chính text block cho dễ đọc. `\s` phù hợp khi cần thể hiện rõ số dấu cách cố định.

## 8. Ví dụ hoàn chỉnh quan sát ký tự thật trong Java 17

Khi kết quả có dấu cách cuối dòng hoặc nhiều newline, `System.out.println` đôi khi khó giúp phân biệt chính xác. Ta có thể hiển thị ký tự bằng ký hiệu dễ đọc:

- `·` biểu diễn **một dấu cách**.
- `↵` biểu diễn **một newline**.

Lưu chương trình thành **`TextBlockEscapeDemo.java`**:

```java
public class TextBlockEscapeDemo {

    static String visible(String text) {
        return text
                .replace(" ", "·")
                .replace("\n", "↵\n");
    }

    public static void main(String[] args) {
        String trailingSpaces = """
                A\s\s
                B
                """;

        String joinedWithoutSpace = """
                Java\
                17
                """;

        String joinedWithSpace = """
                Java\s\
                17
                """;

        String joinedSql = """
                SELECT id, name\s\
                FROM users\s\
                WHERE active = true
                """;

        String noFinalNewline = """
                Done\
                """;

        System.out.println("1. " + visible(trailingSpaces));
        System.out.println("2. " + visible(joinedWithoutSpace));
        System.out.println("3. " + visible(joinedWithSpace));
        System.out.println("4. " + visible(joinedSql));
        System.out.println("5. " + visible(noFinalNewline));

        System.out.println(trailingSpaces.equals("A  \nB\n"));
        System.out.println(joinedWithoutSpace.equals("Java17\n"));
        System.out.println(joinedWithSpace.equals("Java 17\n"));
        System.out.println(noFinalNewline.equals("Done"));
    }
}
```

Biên dịch và chạy với JDK 17:

```bash
javac --release 17 TextBlockEscapeDemo.java
java TextBlockEscapeDemo
```

Kết quả dự kiến:

```text
1. A··↵
B↵

2. Java17↵

3. Java·17↵

4. SELECT·id,·name·FROM·users·WHERE·active·=·true↵

5. Done
true
true
true
true
```

Hai dòng trống sau kết quả 1 đến 4 xuất hiện vì `visible` vẫn giữ `\n` và `println` thêm một lần xuống dòng khi in xong. Đây chỉ là **cách trình bày output**, không phải text block tự thêm hai newline.

### 8.1. Đối chiếu bằng `String.equals`

Thay vì dựa vào khoảng trắng hiển thị trong terminal, các câu lệnh `equals` kiểm tra **chuỗi thực tế**:

- `"A  \nB\n"` có hai dấu cách trước newline.
- `"Java17\n"` không có dấu cách giữa hai phần.
- `"Java 17\n"` có một dấu cách giữa hai phần.
- `"Done"` không có newline cuối.

Đây là cách xác nhận kỳ vọng khi viết test cho mã xử lý text block. Trong bài học này, việc nêu kết quả chỉ nhằm giải thích hành vi của ngôn ngữ Java 17.

## 9. Ứng dụng thực tế

### 9.1. Định dạng dòng văn bản cần trailing spaces

Một số giao thức văn bản hoặc định dạng markdown có thể coi dấu cách cuối dòng là có ý nghĩa. Ví dụ, trong một chuỗi dùng để tạo tài liệu Markdown, **hai dấu cách cuối dòng** được một số renderer diễn giải thành ngắt dòng mềm theo cú pháp Markdown:

```java
String markdown = """
        Tên: Minh\s\s
        Vai trò: Developer
        """;
```

Trong kết quả:

```text
Tên: Minh··↵
Vai trò: Developer↵
```

Lưu ý renderer Markdown có thể có cách xử lý riêng; mục đích ví dụ là cho thấy Java đã **giữ đúng hai dấu cách**.

### 9.2. Viết câu SQL dễ đọc trong source, một dòng trong kết quả

```java
String sql = """
        SELECT id, username\s\
        FROM accounts\s\
        WHERE enabled = true\s\
        ORDER BY id
        """;
```

Chuỗi nhận được:

```text
SELECT id, username FROM accounts WHERE enabled = true ORDER BY id↵
```

Nếu câu SQL hoàn toàn ổn khi chứa newline, có thể giữ nguyên các dòng nguồn mà **không cần** line continuation. Hãy dùng `\` khi hệ thống nhận dữ liệu cần một dòng hoặc khi tính nhất quán của định dạng chuỗi là yêu cầu thực sự.

**An toàn SQL:** Text block chỉ giúp biểu diễn chuỗi. Các giá trị đến từ người dùng vẫn cần truyền qua cơ chế tham số hóa như `PreparedStatement`; việc nối dòng không làm dữ liệu SQL an toàn hơn.

### 9.3. Ghép câu thông báo dài không có newline giữa các phần

```java
String notice = """
        Hệ thống sẽ bảo trì vào cuối tuần này.\s\
        Vui lòng hoàn tất công việc trước thời gian thông báo.
        """;
```

Giá trị gần như một dòng thông thường:

```text
Hệ thống sẽ bảo trì vào cuối tuần này. Vui lòng hoàn tất công việc trước thời gian thông báo.
```

Chuỗi thực tế vẫn có newline cuối vì dấu đóng ở dòng tiếp theo. Nếu gọi API cần **đúng một dòng không có newline cuối**, thêm `\` ở dòng nội dung cuối hoặc chủ động quyết định cách loại newline cuối.

### 9.4. Phân biệt định dạng source và định dạng dữ liệu

Đôi khi, dòng nguồn và dòng dữ liệu **nên giống nhau**:

```java
String json = """
        {
          "id": 17,
          "status": "ok"
        }
        """;
```

Việc giữ newline ở đây giúp đọc nội dung JSON dễ hơn; không cần dùng line continuation. Escape là công cụ **điều khiển chính xác khi cần**, không phải quy tắc phải áp dụng cho mọi text block.

## 10. Các lỗi và hiểu nhầm thường gặp

### Lỗi 1. Cho rằng `\s` có nghĩa “mọi whitespace”

`\s` trong Java string literal và text block là **một dấu cách U+0020**. Đó không phải regex `\s` khi Java đã diễn giải string escape. Với regex, biểu diễn đúng bằng `"\\s"` hoặc `"\\s+"` nếu cần toán tử lặp.

### Lỗi 2. Nghĩ dấu `\` cuối dòng tự chèn một dấu cách

```java
String result = """
        Hello\
        World
        """;
```

Kết quả là `HelloWorld\n`, **không phải** `Hello World\n`. Nếu cần khoảng cách, dùng `Hello\s\` hoặc thiết kế dấu cách rõ ràng ở một vị trí phù hợp.

### Lỗi 3. Nhầm dấu `\` cuối dòng với `\n`

- `\n` **tạo** một newline.
- `\` ngay trước newline nguồn **loại bỏ** newline đó.

Hai escape có tác dụng ngược nhau đối với việc xuống dòng ở vị trí tương ứng.

### Lỗi 4. Dùng dấu cách thực ở cuối dòng khi cần giá trị chính xác

```java
// Mục tiêu: hai dấu cách sau A, trước newline.
String correct = """
        A\s\s
        B
        """;
```

Gõ dấu cách trực tiếp sau `A` khó quan sát và sẽ bị xử lý trailing whitespace. `\s` rõ nghĩa và ổn định hơn cho mục đích này.

### Lỗi 5. Đặt ký tự khác sau backslash trước newline

Line continuation cần **`\` theo sát line terminator**. Nếu gõ dấu cách phía sau `\`, escape nối dòng không còn đúng dạng. Hãy để `\` là ký tự cuối cùng của dòng nguồn.

### Lỗi 6. Nghĩ line continuation xóa newline cuối chuỗi

```java
String text = """
        A\
        B
        """;
```

Kết quả vẫn là `AB\n`, bởi newline **sau `B`** không có escape nối dòng. Muốn loại newline cuối, cần xử lý ở **dòng cuối** hoặc thay vị trí dấu đóng.

### Lỗi 7. Nghĩ text block tự thêm khoảng trắng giữa các đoạn

Text block chỉ thực hiện các quy tắc newline, indentation, escape. Nếu nối `foo\` rồi `bar`, kết quả là `foobar`. Java không đoán ranh giới từ hay thêm dấu cách theo ngữ nghĩa tiếng tự nhiên.

### Lỗi 8. Dùng `trim()` hoặc `strip()` sau đó rồi bất ngờ mất khoảng trắng

```java
String text = """
        A\s\s
        """;

String stripped = text.stripTrailing();
```

`text` giữ hai dấu cách cuối dòng và newline cuối; nhưng `stripTrailing()` **chủ động loại whitespace ở cuối toàn bộ chuỗi**. Nếu cần giữ những ký tự ấy, đừng gọi hàm loại khoảng trắng trên kết quả theo cách mâu thuẫn với yêu cầu.

Lưu ý `stripTrailing()` loại whitespace ở **cuối chuỗi**, không phải tự động loại mọi whitespace cuối **mọi dòng** ở giữa chuỗi. Hãy phân biệt việc xử lý text block của compiler với các thao tác `String` do chương trình gọi sau đó.

### Lỗi 9. Dùng `\s` để biểu diễn tab hoặc xuống dòng

- Dùng `\t` nếu cần tab.
- Dùng `\n` nếu cần LF.
- Dùng `\s` nếu cần một dấu cách thông thường.

### Lỗi 10. Cho rằng text block chỉ dùng được trên Java 17

Text block đã ổn định từ Java 15. Java 17 **kế thừa** tính năng; không nên mô tả nó như cú pháp lần đầu xuất hiện ở Java 17. Hãy kiểm tra cấu hình `--release` của dự án nếu dùng JDK mới nhưng cần biên dịch xuống Java cũ.

## 11. Cách chọn nhanh theo kết quả mong muốn

Giả sử mã nguồn được trình bày trên nhiều dòng; hãy chọn cách viết theo nội dung chuỗi đầu ra:

| Muốn nhận được chuỗi | Cách viết ở cuối dòng nguồn | Lý do |
|---|---|---|
| `"A\nB\n"` | `A` rồi xuống dòng bình thường | Giữ newline |
| `"AB\n"` | `A\` rồi xuống dòng `B` | Bỏ newline giữa A và B |
| `"A B\n"` | `A\s\` rồi xuống dòng `B` | Chèn một dấu cách, bỏ newline |
| `"A  \nB\n"` | `A\s\s` rồi xuống dòng `B` | Giữ hai dấu cách trước newline |
| `"A"` | `A\` rồi xuống dòng chứa `"""` | Bỏ newline cuối |
| `"A\n"` | `A` rồi xuống dòng chứa `"""` | Giữ newline cuối |

### Hai câu hỏi cần tự đặt

**1. Mình cần khoảng trắng hay cần newline?**  
Nếu cần **space U+0020**, dùng `\s`. Nếu cần giữ newline, để dòng nguồn xuống dòng bình thường hoặc dùng `\n`. Nếu cần **không có newline ở ranh giới nguồn**, dùng `\` cuối dòng.

**2. Định dạng chỉ để mã dễ đọc hay có ý nghĩa đối với dữ liệu?**  
Nếu newline/khoảng trắng có ý nghĩa trong giao thức, template, kiểm thử hay dữ liệu đầu ra, hãy mô tả chúng bằng escape tường minh và dùng `String.equals` khi cần xác nhận giá trị mong muốn.

## 12. Bài tập thực hành có lời giải

### Bài 1. Đoán chính xác giá trị

```java
String text = """
        X\s\s
        Y
        """;
```

**Câu hỏi:** Chuỗi có bao nhiêu dấu cách sau `X`? Có newline sau `Y` không?

**Đáp án:** Có **hai dấu cách** sau `X` trước newline; có **một newline** sau `Y`. Giá trị tương đương `"X  \nY\n"`.

### Bài 2. Nối từ không có dấu cách

```java
String text = """
        micro\
        service
        """;
```

**Câu hỏi:** `text.equals("microservice\n")` trả về gì?

**Đáp án:** `true`, vì backslash cuối dòng loại newline giữa `micro` và `service`. Newline cuối sau `service` vẫn còn.

### Bài 3. Nối từ có một dấu cách

**Yêu cầu:** Hoàn thiện text block sao cho giá trị bằng `"Hello World\n"`, trong khi `Hello` và `World` nằm trên hai dòng nguồn khác nhau.

**Một lời giải:**

```java
String text = """
        Hello\s\
        World
        """;
```

`\s` tạo dấu cách; `\` bỏ newline.

### Bài 4. Không có newline cuối

**Yêu cầu:** Mã nguồn có dấu đóng `"""` trên dòng riêng, nhưng chuỗi kết quả phải bằng chính xác `"READY"`.

**Đáp án:**

```java
String text = """
        READY\
        """;
```

Dòng cuối dùng line continuation để loại newline ngay trước dấu đóng.

### Bài 5. Tìm lỗi khi dùng regex

```java
String text = "A\tB C";
String result = text.replaceAll("\s+", "_");
```

**Câu hỏi:** Tại sao mã này không thay tab như dự kiến?

**Đáp án:** Java diễn giải `"\s+"` thành regex `" +"`, chỉ khớp các dấu cách thường. Muốn truyền regex `\s+` để khớp whitespace, dùng `"\\s+"`:

```java
String result = text.replaceAll("\\s+", "_");
```

### Bài 6. Phân biệt dấu gạch chéo ngược thật với line continuation

**Yêu cầu:** Text block chứa hai dòng: dòng đầu là `C:\temp` (có một dấu `\` thật), dòng thứ hai là `Done`; giữ newline giữa hai dòng.

**Một lời giải:**

```java
String pathInfo = """
        C:\\temp
        Done
        """;
```

`\\` là escape cho **một backslash thật** trong chuỗi, khác với `\` cuối dòng dùng để nối dòng.

### Bài 7. Phân tích ba newline

```java
String text = """
        A\
        B
        C\
        D
        """;
```

**Câu hỏi:** Giá trị chuỗi tương đương chuỗi một dòng nào trong source Java?

**Đáp án:**

```java
String expected = "AB\nCD\n";
```

Hai newline bị loại: giữa A–B và giữa C–D. Newline giữa B–C và newline sau D vẫn còn.

## 13. Tài liệu tham khảo chính thức

- [Oracle Java 17 — Text Blocks](https://docs.oracle.com/en/java/javase/17/language/text-blocks.html): cấu trúc text block, xử lý khoảng trắng, escape `\s` và line continuation.
- [OpenJDK JEP 378 — Text Blocks](https://openjdk.org/jeps/378): mô tả thiết kế, thứ tự xử lý và hai escape mới được chuẩn hóa ở Java 15.
- [Java Language Specification 17 — `3.10.6 Text Blocks`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.6): cú pháp và cách xác định giá trị của text block.
- [Java Language Specification 17 — `3.10.7 Escape Sequences`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.7): các escape được hỗ trợ, bao gồm `\s` và `\` + line terminator.
- [JDK 17 API — `String`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): các phương thức chuỗi liên quan đến xử lý khoảng trắng như `stripIndent()` và `translateEscapes()`.

**Điểm cốt lõi:** `\s` trong Java 17 chèn **một dấu cách U+0020**, đặc biệt giúp bảo toàn dấu cách ở cuối dòng text block. `\` đặt ngay trước ký tự xuống dòng của mã nguồn **nối hai dòng nội dung** mà không chèn newline. Kết hợp `\s\` khi cần nối dòng nhưng vẫn giữ đúng một dấu cách ở ranh giới hai phần.
