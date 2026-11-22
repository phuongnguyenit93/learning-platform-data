# Nội dung chứa dấu nháy kép hoặc dấu phân cách trong Java text blocks

## 1. Text block và quy tắc trọng tâm

**Text block** là cú pháp biểu diễn `String` nhiều dòng trong Java, hữu ích khi dữ liệu có nhiều dấu nháy kép như JSON, HTML, SQL hoặc mã nguồn cần hiển thị. So với việc ghép nhiều string literal thông thường, text block thường dễ viết và đọc hơn:

```java
String json = """
    {
      "name": "An",
      "active": true
    }
    """;
```

Các dấu `"` bao quanh `name`, `An` và `active` là **nội dung bình thường**, không cần viết thêm `\"`. Text block **vẫn có kiểu `String`**, không tạo kiểu dữ liệu mới và không tự phân tích JSON.

Text block được giới hạn bởi:

- **Dấu mở:** ba dấu nháy kép liên tiếp `"""`, theo sau bởi một ký tự xuống dòng (có thể có khoảng trắng hợp lệ trước xuống dòng).
- **Dấu đóng:** ba dấu nháy kép liên tiếp `"""`, có thể đặt trên dòng riêng hoặc ngay sau ký tự nội dung cuối cùng.

**Quy tắc quan trọng:** Một hoặc hai dấu `"` liên tiếp trong nội dung thường không cần escape. Nếu cần chứa **ba dấu `"""` liên tiếp**, phải escape ít nhất một dấu để tránh bị hiểu là dấu đóng. Khuyến nghị của Oracle là escape **dấu đầu tiên** trong từng chuỗi ba dấu nháy kép.

**Phiên bản:** Text blocks từng được giới thiệu dưới dạng preview trong Java 13/14 và **được chuẩn hóa từ Java 15** (JEP 378). Bài này chỉ áp dụng những quy tắc vẫn hiện hành với Java 17 trở lên, không cần dùng các cờ preview cũ.

## 2. Một hoặc hai dấu nháy kép nằm trong nội dung

Trong chuỗi thông thường, muốn chứa dấu `"` cần escape:

```java
String ordinary = "She said \"Hello\".";
```

Trong text block, viết trực tiếp là đủ:

```java
String quoted = """
    She said "Hello".
    """;
```

Giá trị `quoted` chứa `She said "Hello".` và một ký tự xuống dòng ở cuối. Dấu `"` đứng lẻ trong dòng không phải là dấu phân cách đóng của text block.

Hai dấu liền nhau `""` cũng không đóng khối:

```java
String html = """
    <input type="text" name="search" value="">
    <a href="https://example.com" title="Open">Link</a>
    """;
```

Đây là lý do text block đặc biệt thuận tiện khi nội dung chứa các thuộc tính HTML/XML hoặc dấu nháy kép trong JSON.

### Có được viết `\"` không?

Có. `\"` vẫn là escape sequence hợp lệ của Java, nhưng không bắt buộc trong phần lớn tình huống với text block:

```java
String plain = """
    She said "Hi".
    """;

String escaped = """
    She said \"Hi\".
    """;

boolean same = plain.equals(escaped); // true
```

Hai giá trị bằng nhau. Escape `\"` được chuyển thành đúng một ký tự dấu nháy kép trong chuỗi kết quả; dấu gạch chéo ngược không được giữ lại. Đừng escape mọi dấu `"` theo thói quen nếu không có lý do, vì làm thế thường giảm lợi ích dễ đọc của text block.

## 3. Khi nội dung chứa đúng ba dấu `"""`

Giả sử cần tạo chuỗi chứa dòng sau:

```text
Triple: """
```

Đoạn sau **không hợp lệ** vì Java sẽ nhận ra ba dấu nháy kép trong nội dung là dấu đóng quá sớm:

```java
// KHÔNG biên dịch: delimiter bị đóng sớm.
String broken = """
    Triple: """
    """;
```

Đoạn đúng:

```java
String triple = """
    Triple: \"""
    """;
```

Dãy `\"""` trong **mã nguồn** có một dấu gạch chéo ngược trước dấu nháy kép đầu tiên; `\"` sẽ tạo một dấu `"` thực ở runtime, và hai dấu `"` còn lại cũng nằm trong nội dung. Kết quả cuối **có đúng ba dấu `"""`, không có backslash trước chúng**.

Khi dữ liệu có nhiều chuỗi từ ba dấu nháy kép trở lên, xử lý từng dãy để tránh tạo dấu đóng ngoài ý muốn. Cách dễ đọc nhất là escape **dấu đầu của mỗi dãy ba dấu nháy kép**.

### Text block nằm bên trong mã nguồn được lưu bằng text block

Một ứng dụng có thể dùng text block để tạo đoạn mã Java chứa chính một text block khác:

```java
String sourceCode = """
    String inner = \"""
        hello
        \""";
    """;
```

Ở mã nguồn **bên ngoài**, các dãy `\"""` là nội dung đã escape. Trong `sourceCode` ở runtime, chúng trở thành ký tự `"""` mở/đóng **text block bên trong đoạn mã được tạo**. Chỉ `"""` cuối cùng, không escape, mới đóng text block ngoài.

Hãy phân biệt **ký tự cần có trong kết quả** và **ký tự dùng để viết cú pháp Java ở nguồn**. Đây là nguồn gốc của nhiều lỗi khi nhúng code, định dạng văn bản hoặc tài liệu kỹ thuật.

## 4. Vị trí dấu mở và dấu đóng cũng quan trọng

### 4.1. Sau dấu mở phải xuống dòng

Sai:

```java
String invalid = """Hello"""; // Lỗi biên dịch
```

Đúng:

```java
String valid = """
    Hello
    """;
```

Không thể đặt nội dung ngay sau dấu mở trên cùng một dòng như string literal đơn giản. Dấu mở `"""` yêu cầu xuống dòng tiếp theo.

### 4.2. Dấu đóng trên dòng riêng và ký tự `\n` cuối

```java
String withNewline = """
    done
    """;
```

Giá trị là `"done\n"`. Dấu xuống dòng sau `done` được giữ ở cuối chuỗi.

### 4.3. Dấu đóng cùng dòng với nội dung cuối

```java
String withoutNewline = """
    done""";
```

Giá trị là `"done"`. Hai biểu thức trên đều hợp lệ nhưng **không tạo chuỗi bằng nhau** vì khác ký tự xuống dòng cuối. Cần xác định rõ điều này khi tạo dữ liệu để so sánh chính xác, ký nội dung hoặc gửi tới API.

Nếu một dòng nội dung kết thúc bằng dấu nháy kép rồi dấu đóng đặt sát ngay phía sau, dãy dấu nháy kép có thể dài và khó phân biệt. Để mã dễ bảo trì, hãy cân nhắc đặt dấu đóng ở dòng riêng hoặc escape ký tự nội dung phù hợp.

### 4.4. Thụt lề được chuẩn hóa

```java
String lines = """
    first
    second
    """;
```

Giá trị tương đương `"first\nsecond\n"`. Các khoảng trắng chung dùng để thụt lề mã nguồn không mặc nhiên được giữ nguyên. Vị trí, đặc biệt **độ thụt lề của dấu đóng**, góp phần xác định phần khoảng trắng phụ sẽ bị loại bỏ.

Java xử lý text block theo thứ tự: **chuẩn hóa kết thúc dòng thành LF → bỏ incidental whitespace → diễn giải escape sequence**. Khi kiểm thử dữ liệu nhạy whitespace, nên dùng `String.equals` hoặc so độ dài và ký tự thực tế, thay vì suy luận chỉ từ hình thức trong editor.

## 5. Text block không phải raw string: escape vẫn có hiệu lực

Text block cho phép viết nhiều dấu `"` trực tiếp, nhưng vẫn diễn giải các escape Java:

| Ký hiệu trong nguồn | Ý nghĩa ở runtime |
| --- | --- |
| `"`, `""` | Một hoặc hai dấu nháy kép làm nội dung |
| `\"` | Một dấu nháy kép |
| Hai dấu gạch chéo ngược liền nhau | Một dấu gạch chéo ngược |
| `\n` | Một ký tự xuống dòng |
| `\t` | Một ký tự tab |
| `\s` | Một dấu cách, hữu ích khi muốn giữ khoảng trắng cuối dòng |
| Dấu gạch chéo ngược ngay trước line terminator | Nối dòng nguồn, không đưa line terminator đó vào kết quả |

Đặc biệt, text block **không có nghĩa mọi backslash được giữ nguyên**. Ví dụ đường dẫn Windows:

```java
String path = """
    C:\\data\\report.txt
    """;
```

Giá trị `path` là dòng `C:\data\report.txt`, sau đó có `\n` cuối. Mỗi cặp hai ký tự gạch chéo ngược ở nguồn tạo một ký tự gạch chéo ngược trong kết quả. Viết trực tiếp `C:\temp\new` là nguy hiểm vì `\t` hoặc `\n` sẽ được xử lý như escape.

### Ký tự escape thuộc nhiều ngôn ngữ lồng nhau

Text block chỉ xử lý **escape của Java**. Nếu nội dung cuối là JSON có chuỗi chứa dấu nháy kép ở giữa, bản thân **JSON** cũng yêu cầu escape. Ví dụ muốn tạo đúng dữ liệu JSON:

```json
{"message":"Say \"Hi\" now"}
```

Mã Java có thể viết:

```java
String json = """
    {"message":"Say \\\"Hi\\\" now"}
    """;
```

Trong mã nguồn Java, `\\\"` được diễn giải để chuỗi kết quả có ký tự backslash trước dấu nháy kép, đúng theo escape của JSON. Ngược lại, nếu chỉ viết `\"` trong nguồn Java, dấu backslash bị Java tiêu thụ và không còn trong dữ liệu JSON.

Cần ghi nhớ **hai tầng xử lý**: trước hết Java tạo `String`; sau đó parser JSON/SQL/regex mới hiểu nội dung. Text block không tự đảm bảo JSON hợp lệ, không tự ngăn SQL injection và không thay thế thư viện serialize/escape phù hợp. Với câu lệnh SQL lấy dữ liệu người dùng, hãy dùng `PreparedStatement` và bind tham số thay vì nối chuỗi trực tiếp.

## 6. Chương trình Java 17+ có đầu ra kiểm chứng

Lưu chương trình hoàn chỉnh vào **`TextBlockDelimiterDemo.java`**:

```java
public class TextBlockDelimiterDemo {
    public static void main(String[] args) {
        String single = """
            She said "Hi".
            """;
        String doubleQuotes = """
            Two quotes: "".
            """;
        String triple = """
            Triple: \"""
            """;
        String escaped = """
            She said \"Hi\".
            """;
        String json = """
            {"message":"Hi","count":2}
            """;
        String path = """
            C:\\data\\report.txt
            """;
        String embedded = """
            String inner = \"""
                hello
                \""";
            """;
        String noFinalNewline = """
            done""";
        String withFinalNewline = """
            done
            """;

        System.out.println("single=" +
                single.equals("She said \"Hi\".\n"));
        System.out.println("double=" +
                doubleQuotes.equals("Two quotes: \"\".\n"));
        System.out.println("triple=" +
                triple.equals("Triple: \"\"\"\n"));
        System.out.println("escapedSame=" + escaped.equals(single));
        System.out.println("json=" +
                json.equals("{\"message\":\"Hi\",\"count\":2}\n"));
        System.out.println("path=" +
                path.equals("C:\\data\\report.txt\n"));
        System.out.println("nested=" +
                (embedded.contains("String inner = \"\"\"")
                 && embedded.contains("\"\"\";")));
        System.out.println("noFinalNewline=" +
                noFinalNewline.equals("done"));
        System.out.println("withFinalNewline=" +
                withFinalNewline.equals("done\n"));
    }
}
```

Dùng JDK 17 trở lên và biên dịch theo chuẩn ngôn ngữ Java 17:

```bash
javac --release 17 TextBlockDelimiterDemo.java
java TextBlockDelimiterDemo
```

**Đầu ra chính xác:**

```text
single=true
double=true
triple=true
escapedSame=true
json=true
path=true
nested=true
noFinalNewline=true
withFinalNewline=true
```

Ý nghĩa từng phép kiểm:

1. `single` cho thấy dấu `"` đơn không cần escape.
2. `double` cho thấy `""` nằm trong nội dung bình thường.
3. `triple` xác nhận escape dấu đầu của `"""` vẫn giữ ba dấu đó trong chuỗi.
4. `escapedSame` xác nhận `\"` và dấu `"` viết trực tiếp có thể tạo cùng giá trị.
5. `json` xác nhận các dấu nháy kép JSON đơn lẻ không cần escape trong nguồn text block.
6. `path` xác nhận quy tắc backslash của Java.
7. `nested` xác nhận delimiter của text block nằm trong **đoạn mã nhúng** không đóng khối bên ngoài.
8. Hai dòng cuối kiểm tra sự khác nhau giữa dấu đóng ở dòng riêng và dấu đóng ngay sau nội dung.

Ví dụ được kiểm tra bằng JDK có hỗ trợ `--release 17`; tất cả chín kết quả in ra `true`. Dùng phép `equals` giúp kiểm chứng cả xuống dòng cuối, vốn khó nhìn thấy nếu chỉ `println` chuỗi.

## 7. Lỗi thường gặp và cách tránh

| Lỗi hoặc hiểu nhầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Escape mọi dấu `"` trong text block | Mã rối và kém dễ đọc | Viết trực tiếp dấu `"` đơn, cặp `""` |
| Viết `"""` trực tiếp khi muốn nó là nội dung | Delimiter có thể đóng sớm | Escape dấu đầu bằng `\"""` |
| Viết `String s = """abc""";` | Lỗi cú pháp vì thiếu xuống dòng sau dấu mở | Đặt nội dung từ dòng tiếp theo |
| Đóng text block ở dòng riêng nhưng mong không có `\n` cuối | Kết quả khác chuỗi mong muốn | Đóng ngay sau nội dung cuối khi cần |
| Nghĩ khoảng trắng nguồn được giữ toàn bộ | Kết quả bị strip indent | Xem vị trí delimiter đóng, kiểm thử chuỗi |
| Nghĩ text block là raw string | Escape `\n`, `\t`, backslash vẫn được diễn giải | Phân biệt ký tự nguồn với ký tự kết quả |
| Viết `C:\temp\new` trực tiếp | `\t`, `\n` có thể làm sai dữ liệu | Escape backslash trong nguồn |
| JSON cần `\"` nhưng nguồn Java chỉ dùng `\"` | Java loại dấu backslash | Giữ backslash bằng `\\\"` |
| Nhúng mã có dấu `"""` nhưng không escape delimiter nội bộ | Text block ngoài đóng sai vị trí | Escape dấu đầu của từng delimiter nhúng |
| Tin rằng text block tự bảo đảm JSON/SQL hợp lệ | Lỗi parse hoặc bảo mật | Dùng parser/serializer và bind tham số |

## 8. Bài tập và đáp án

**Câu 1.** Text block chứa `<p title="Hi">Hello</p>` có cần escape dấu `"` không?  
**Đáp án:** Không. Chúng không tạo ba dấu nháy kép liên tiếp.

**Câu 2.** Muốn kết quả chứa đúng ba dấu `"""`, phải viết thế nào trong dòng nội dung?  
**Đáp án:** Một cách rõ ràng là `\"""`, escape dấu đầu tiên.

**Câu 3.** `String s = """abc""";` có hợp lệ không?  
**Đáp án:** Không, vì thiếu ký tự xuống dòng sau delimiter mở.

**Câu 4.** Dấu đóng đặt ở dòng riêng sau `abc` làm kết quả khác gì so với đóng ngay sau `abc`?  
**Đáp án:** Dòng riêng tạo `"abc\n"`; đóng sát nội dung tạo `"abc"`, giả sử cách căn lề thông thường.

**Câu 5.** Dùng `\"` có giữ lại backslash ở runtime không?  
**Đáp án:** Không. Nó tạo dấu `"`; để giữ backslash cần escape thêm ở mã Java.

**Câu 6.** Vì sao JSON có `\"` trong giá trị cần xử lý riêng?  
**Đáp án:** Vì đó là escape **của JSON**, không chỉ của Java. Cần tạo đúng các ký tự backslash và dấu nháy kép trong chuỗi kết quả.

**Câu 7.** Có nên dùng text block để ghép trực tiếp input người dùng thành SQL không?  
**Đáp án:** Không. Text block không ngăn injection; dùng câu lệnh có tham số và API phù hợp.

## 9. Tổng kết và nguồn chính thức

- **Một hay hai dấu nháy kép** thường có thể xuất hiện trực tiếp trong text block.
- **Ba dấu `"""`** thuộc nội dung phải escape ít nhất một dấu, nên escape dấu đầu: `\"""`.
- **Dấu mở phải có xuống dòng**; vị trí dấu đóng ảnh hưởng tới `\n` cuối và cách tính thụt lề.
- **Text block vẫn diễn giải escape sequence** của Java; dữ liệu JSON/SQL/regex nhúng có thể có thêm quy tắc riêng.
- Những quy tắc này **đã ổn định từ Java 15 và vẫn còn hiệu lực** trong Java 17+.

Tài liệu chính thức:
- [Oracle Java 17 — Programmer's Guide to Text Blocks](https://docs.oracle.com/en/java/javase/17/text-blocks/index.html): dấu phân cách, escape của ba dấu nháy kép, thụt lề và hướng dẫn thực hành G8.
- [JLS Java SE 17 `3.10.6 — Text Blocks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.6): cú pháp delimiter, escape và xử lý whitespace.
- [OpenJDK JEP 378 — Text Blocks](https://openjdk.org/jeps/378): tính năng được chuẩn hóa từ Java 15.