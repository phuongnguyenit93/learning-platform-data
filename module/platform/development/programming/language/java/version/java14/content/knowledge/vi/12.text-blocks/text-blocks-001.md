# Chuỗi nhiều dòng và mục tiêu giảm escape thủ công bằng Text Blocks (Java 15+)

## 1. Text blocks giải quyết vấn đề gì?

Trong Java, một chuỗi truyền thống dùng dấu nháy kép `"..."`. Khi nhúng JSON, HTML, SQL, XML hoặc một đoạn văn dài, lập trình viên thường phải viết nhiều `\n`, `\"` và toán tử nối `+`:

```java
String json = "{\n" +
        "  \"id\": \"BK-42\",\n" +
        "  \"active\": true\n" +
        "}";
```

Cách này vẫn **hoàn toàn hợp lệ**, nhưng phần cú pháp Java che khuất định dạng thật của dữ liệu. Sửa một dòng JSON có thể phải sửa đồng thời dấu escape, vị trí `\n` và dấu `+`. Khi review code, rất khó nhìn ngay được nội dung cuối cùng của chuỗi.

**Text block** là cú pháp khai báo **`String` nhiều dòng** sử dụng ba dấu nháy kép `"""`. Cùng JSON trên được viết:

```java
String json = """
        {
          "id": "BK-42",
          "active": true
        }""";
```

Hai đoạn là **hai cách thay thế** cho cùng một biến; không đặt cả hai khai báo `json` trong một phạm vi. Giá trị `String` tạo ra **bằng nhau từng ký tự**. Phiên bản text block dễ đọc vì nội dung được trình bày gần với JSON thực, không còn phải escape các dấu `"` đơn lẻ hoặc nối từng dòng bằng `+`.

**Mục tiêu của text blocks không phải “không bao giờ cần escape”**, mà là **giảm các escape và phép nối vô ích**, để mã nguồn dễ đọc, dễ sửa, ít lỗi định dạng hơn.

### Mốc phiên bản còn áp dụng

Text blocks từng xuất hiện ở dạng *preview* trong **Java 13 và Java 14**, sau đó được **chuẩn hóa từ Java 15** theo [JEP 378](https://openjdk.org/jeps/378). Trong **Java 15+**, cú pháp này là một tính năng chính thức, không cần `--enable-preview`. Bài này trình bày cách sử dụng **vẫn áp dụng trong Java hiện đại**; các mốc preview chỉ là thông tin lịch sử. Ví dụ chạy trên **Java 17+**, phù hợp với dự án sử dụng các bản JDK hiện hành.

## 2. Cú pháp: ba dấu nháy và quy tắc xuống dòng

Một text block phổ biến:

```java
String greeting = """
        Chào bạn,
        Đây là Java text block.
        Hẹn gặp lại!
        """;
```

Cấu trúc gồm:

1. **Dấu mở `"""`** phải được theo sau bởi **kết thúc dòng nguồn** trước khi nội dung bắt đầu. Không đặt ký tự nội dung ngay sau ba dấu nháy mở.
2. **Thân** có thể chứa nhiều dòng với dấu `"` thông thường mà không cần `\"`.
3. **Dấu đóng `"""`** xác định điểm kết thúc. Vị trí của nó ảnh hưởng đến ký tự newline cuối và cách loại bỏ thụt lề.
4. **Giá trị** luôn là một đối tượng thuộc kiểu `java.lang.String`: dùng được `equals`, `length`, `lines`, `formatted` và tất cả API nhận `String`.

### Cú pháp sai và đúng

```java
// SAI: thiếu xuống dòng sau dấu mở.
// String a = """hello""";

// SAI: có chữ trên cùng dòng với dấu mở.
// String b = """hello
//             world""";

// ĐÚNG:
String c = """
        hello
        world
        """;
```

Các ví dụ không hợp lệ đã được chú thích nhằm minh họa. Ký tự newline ngay sau dấu mở là **bắt buộc về cú pháp** nhưng không tự tạo ra dòng trống ở đầu nội dung.

### Có hay không một `\n` ở cuối?

Dấu đóng đứng **trên dòng riêng**:

```java
String a = """
        one
        two
        """;
```

Giá trị `a` tương đương `"one\ntwo\n"`, **có newline cuối**.

Dấu đóng ở **cuối dòng nội dung cuối**:

```java
String b = """
        one
        two""";
```

Giá trị `b` tương đương `"one\ntwo"`, **không có newline cuối**. Cả hai đều hợp lệ. Khi chuyển từ literal cũ sang text block, đây là chỗ dễ làm thay đổi giá trị `String` ngoài ý muốn.

## 3. Chương trình Java 17+ hoàn chỉnh và kết quả đã kiểm thử

Tạo tệp **`TextBlockDemo.java`** đúng nội dung sau:

```java
public class TextBlockDemo {
    private static void check(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        String escaped = "{\n  \"id\": \"BK-42\",\n  \"active\": true\n}";
        String textBlock = """
                {
                  "id": "BK-42",
                  "active": true
                }""";

        check(escaped.equals(textBlock), "old and new JSON differ");
        System.out.println("equivalent=" + escaped.equals(textBlock));
        System.out.println("startsWithBrace=" + textBlock.startsWith("{"));
        System.out.println("endsWithBrace=" + textBlock.endsWith("}"));
        System.out.println("containsQuotes=" + textBlock.contains("\"BK-42\""));

        String paragraph = """
                line one
                line two
                """;
        String inlineClose = """
                line one
                line two""";
        check(paragraph.equals("line one\nline two\n"),
                "expected trailing newline");
        check(inlineClose.equals("line one\nline two"),
                "unexpected trailing newline");
        System.out.println("trailingNewline=" + paragraph.endsWith("\n"));
        System.out.println("paragraphLines=" + paragraph.lines().count());
        System.out.println("inlineCloseNewline=" + inlineClose.endsWith("\n"));

        String joined = """
                alpha \
                beta
                """;
        check(joined.equals("alpha beta\n"), "line continuation failed");
        System.out.println("joined=" + joined.stripTrailing());

        String spaces = """
                A\s\s
                B
                """;
        check(spaces.equals("A  \nB\n"), "space escapes failed");
        System.out.println("spacesFirstLineLength="
                + spaces.substring(0, spaces.indexOf('\n')).length());

        String sql = """
                SELECT id, title
                FROM lesson
                WHERE active = ?
                """;
        System.out.println("sqlLines=" + sql.lines().count());

        String formatted = """
                Hello, %s!
                """.formatted("Java");
        System.out.println("formatted=" + formatted.strip());

        String path = """
                C:\\workspace\\java
                """;
        check(path.strip().equals("C:\\workspace\\java"),
                "backslash escaping failed");
        System.out.println("path=" + path.strip());

        String html = """
                <tag key="value">Text</tag>
                """;
        System.out.println("quoteEscapesNeeded="
                + !html.contains("key=\"value\""));
    }
}
```

**Biên dịch và chạy** bằng JDK 17 hoặc cao hơn:

```bash
javac --release 17 -encoding UTF-8 TextBlockDemo.java
java TextBlockDemo
```

Không cần preview flag. Chương trình dùng các phép `check` để ném `AssertionError` nếu nội dung không như mong muốn; các phép kiểm tra này được thực thi ngay cả khi không bật `-ea`.

**Standard output chính xác:**

```text
equivalent=true
startsWithBrace=true
endsWithBrace=true
containsQuotes=true
trailingNewline=true
paragraphLines=2
inlineCloseNewline=false
joined=alpha beta
spacesFirstLineLength=3
sqlLines=3
formatted=Hello, Java!
path=C:\workspace\java
quoteEscapesNeeded=false
```

### Vì sao có những kết quả đó?

- `equivalent=true`: chuỗi viết bằng `\n`, `\"` và chuỗi text block cùng một giá trị. `startsWithBrace=true` và `endsWithBrace=true` xác nhận không có dòng trống thừa ở đầu hay ký tự `\n` thừa sau dấu `}`.
- `containsQuotes=true`: dấu nháy kép trong JSON được giữ làm dữ liệu, dù ở mã nguồn text block không cần escape.
- `trailingNewline=true` và `inlineCloseNewline=false`: chính vị trí dấu đóng làm khác ký tự cuối của chuỗi. `String.lines().count()` cho 2 với hai dòng nội dung; newline cuối không sinh ra một dòng rỗng thứ ba khi duyệt bằng `lines()`.
- `joined=alpha beta`: dấu backslash ở cuối dòng nguồn ngăn sinh ra newline giữa hai phần. Dấu cách trước backslash được giữ, nên có đúng một space giữa `alpha` và `beta`.
- `spacesFirstLineLength=3`: `A\s\s` có độ dài ba ký tự trước `\n`, gồm `A` và hai khoảng trắng.
- `sqlLines=3`: câu lệnh SQL trong ví dụ trải ba dòng; bản thân text block không tự thực thi truy vấn.
- `formatted=Hello, Java!`: text block vẫn là `String` nên gọi `formatted("Java")` được. `strip()` chỉ dùng ở lúc in để không còn newline cuối.
- `path=C:\workspace\java`: backslash muốn xuất hiện trong giá trị vẫn cần biểu diễn bằng `\\` trong mã Java.
- `quoteEscapesNeeded=false`: `"` đơn lẻ trong HTML không cần `\"` khi viết text block.

## 4. Thụt lề tự động: giữ bố cục hữu ích, bỏ phần thừa

Text block **không chỉ copy nguyên từng dấu cách từ editor**. Trình biên dịch thực hiện bước xử lý *incidental indentation* (khoảng trắng thụt lề vô tình), để có thể đặt text block bên trong method hoặc khối lệnh mà giá trị thực không bị thêm toàn bộ thụt lề của mã nguồn.

```java
static String html() {
    return """
            <main>
              <h1>Java</h1>
            </main>
            """;
}
```

Giá trị của phương thức có dạng:

```text
<main>
  <h1>Java</h1>
</main>
```

Phần indent chung của mã nguồn được loại bỏ, nhưng **indent tương đối** của `<h1>` vẫn giữ. Khi dấu đóng `"""` đặt trên dòng riêng, **vị trí thụt lề của dấu đóng có tham gia xác định mức khoảng trắng được cắt**. Nếu dịch dấu đóng trái/phải, giá trị `String` có thể thay đổi.

**Thực hành tốt:**

- Duy trì kiểu indentation nhất quán, tránh trộn tab và space vì độ rộng tab phụ thuộc editor nhưng quy tắc ngôn ngữ không phụ thuộc cách editor hiển thị.
- Đừng chỉ nhìn số dấu cách trong source code để khẳng định đầu ra có bấy nhiêu dấu cách.
- Với dữ liệu đòi khoảng trắng chính xác, viết kiểm thử `equals` hoặc kiểm tra `length` từng dòng.
- Có thể dùng tùy chọn trình biên dịch `javac -Xlint:text-blocks` để nhận cảnh báo về định dạng whitespace bất thường trong text block.
- Nếu thật sự muốn thêm mức thụt lề vào chuỗi, xem xét `String.indent(int)` với test rõ ràng; tránh thêm space rồi mong trình biên dịch giữ tất cả.

### Trailing whitespace khác indentation

Khoảng trắng **cuối mỗi dòng** trong text block thường được trình biên dịch coi là khoảng trắng vô tình và loại bỏ. Điều này giúp mã nguồn ít nhạy với editor tự xóa trailing spaces, nhưng cần chú ý với định dạng bảng text theo độ rộng cố định.

Nếu bắt buộc có dấu cách cuối dòng, dùng escape `\s`:

```java
String value = """
        A\s\s
        B
        """;
```

Giá trị là `"A  \nB\n"`. Escape `\s` được chuyển thành dấu cách **sau** khi xử lý whitespace, nên hai khoảng trắng này được giữ. Cách khác là `\040` (octal escape), nhưng `\s` dễ hiểu hơn cho mục đích biểu diễn một dấu cách.

**Không thay `\s` bằng Unicode escape `\u0020` với mong đợi tương đương:** Unicode escape được xử lý sớm hơn trong quá trình đọc source code, không có cùng tác dụng bảo vệ trailing whitespace.

## 5. Text block vẫn xử lý escape của Java

Một text block **không phải raw string**. Vì vậy, hãy phân biệt: những gì Java cho phép viết trực tiếp dễ hơn, và những gì Java vẫn diễn giải như escape.

| Dạng trong nguồn Java | Ý nghĩa trong giá trị `String` | Khi cần |
| --- | --- | --- |
| Dấu `"` bình thường | Một dấu nháy kép | Có thể viết thẳng trong JSON/HTML/XML |
| `\n` | Newline tường minh | Khi cần ký tự xuống dòng tại vị trí khác với xuống dòng trong nguồn |
| `\t` | Tab | Khi định dạng yêu cầu ký tự tab thật |
| `\\` | Một backslash | Đường dẫn, regex hoặc dữ liệu cần `\` |
| `\s` | Một space | Để giữ trailing whitespace có chủ ý |
| Backslash ngay trước xuống dòng nguồn | **Không có newline tại ranh giới đó** | Chia một dòng giá trị dài thành nhiều dòng source |
| `\"` | Dấu nháy kép đã escape | Có thể hữu ích khi nội dung chứa nhiều dấu nháy kép liên tiếp |

### Kết thúc dòng bằng backslash để nối nội dung

```java
String sentence = """
        part one \
        part two
        """;
```

Giá trị tương đương `"part one part two\n"`: dấu backslash ở cuối dòng bỏ newline tại vị trí đó. Cơ chế này hữu ích khi **mã nguồn dài phải xuống dòng** nhưng dữ liệu đích phải liên tục; không dùng khi thực tế cần newline, chẳng hạn một dòng mới trong JSON hoặc SQL.

### Đường dẫn và regex vẫn cần backslash escape

```java
String path = """
        C:\\workspace\\java
        """;
```

Giá trị có một backslash tại từng vị trí `C:\workspace\java` (và có newline cuối do dấu đóng riêng dòng). Viết `C:\workspace\java` nguyên xi vào source sẽ khiến Java hiểu một số tổ hợp dấu gạch chéo như escape hoặc gây lỗi cú pháp.

Tương tự, một biểu thức chính quy cần dấu `\` trong **giá trị regex** vẫn phải được thể hiện đúng khi viết literal Java (ví dụ `"\\d+"` nếu muốn regex `\d+`). Không thể bỏ hết escape chỉ vì dùng text block.

### Ba dấu nháy kép liên tiếp là trường hợp đặc biệt

Dấu `"""` có nghĩa là kết thúc text block. Một dấu nháy kép `"` hay hai dấu liên tiếp trong nội dung thường không cần escape; nhưng **ba dấu liên tiếp** có thể bị trình biên dịch nhận là dấu đóng. Khi chính dữ liệu cần ba dấu nháy kép liền nhau, hãy escape thích hợp một trong các dấu nháy kép hoặc đổi cách xây chuỗi. Điều này khác hẳn tình huống JSON/HTML có nhiều dấu nháy kép **không liền nhau**.

## 6. Ứng dụng thực tế: JSON, SQL, HTML và template đơn giản

### JSON dễ đọc, nhưng vẫn phải tạo dữ liệu JSON đúng

```java
String json = """
        {
          "user": {
            "id": 42,
            "active": true
          },
          "roles": ["reader", "editor"]
        }
        """;
```

Cấu trúc JSON giờ gần giống một tệp JSON thực tế, hữu ích cho ví dụ, fixture hoặc tài liệu. Tuy nhiên **javac không kiểm tra JSON schema**. Khi giá trị đến từ người dùng, đừng ghép trực tiếp mà bỏ qua cách escape ký tự đúng quy tắc JSON; dùng serializer hoặc JSON builder khi phù hợp.

Nếu yêu cầu là **tương đương dữ liệu JSON** thay vì tương đương chuỗi byte/ký tự, hãy parse và kiểm tra cấu trúc. Hai JSON có thể cùng ý nghĩa nhưng khác whitespace; `String.equals` sẽ trả `false`.

### SQL nhìn rõ định dạng, nhưng không bảo vệ khỏi injection

```java
String sql = """
        SELECT id, title
        FROM lessons
        WHERE owner_id = ?
          AND active = ?
        ORDER BY id
        """;
```

Đây chỉ là một `String` chứa SQL; chưa có kết nối database hoặc thực thi truy vấn. Khi dùng JDBC, truyền giá trị qua `PreparedStatement`, chẳng hạn:

```java
// Snippet: giả định đã có Connection connection và long ownerId.
try (java.sql.PreparedStatement statement =
             connection.prepareStatement(sql)) {
    statement.setLong(1, ownerId);
    statement.setBoolean(2, true);
    try (java.sql.ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong("id"));
        }
    }
}
```

Đoạn JDBC là **mã minh họa**, không phải chương trình chạy độc lập. Cần kết nối, driver, bảng và dữ liệu phù hợp. **Text block không ngăn SQL injection**. Parameter binding vẫn là yêu cầu an toàn khi có giá trị động.

### HTML giữ dấu nháy kép và cấu trúc dễ xem

```java
String html = """
        <section class="lesson">
          <h2>Text blocks</h2>
          <p>Java 15+</p>
        </section>
        """;
```

Không cần `\"` cho thuộc tính `class="lesson"`. Nhưng text block **không tự HTML-escape dữ liệu người dùng**. Nếu cần nội suy dữ liệu động, hãy dùng cơ chế escape hoặc template engine thích hợp để tránh lỗi hiển thị và các rủi ro chèn HTML/script.

### Text blocks không tự nội suy biến

```java
String name = "Java";
String greeting = """
        Hello, %s!
        """.formatted(name);

System.out.println(greeting.strip()); // Hello, Java!
```

`%s` chỉ được thay khi gọi `String.formatted(...)`; nó **không được thay tự động** do cú pháp text block. Khi muốn điền dữ liệu vào JSON, SQL hoặc HTML, vẫn phải tuân thủ quy tắc escaping/serialization/binding của định dạng đích. `formatted` là công cụ định dạng `String`, không phải giải pháp tự động bảo đảm an toàn.

## 7. Refactor chuỗi cũ sang text block mà không đổi hành vi

Quy trình nên áp dụng cho một đoạn mã chứa nhiều `"..." + ` và `\n`:

1. **Chụp giá trị chuỗi cũ** qua unit test hoặc phép so sánh. Xác định đúng dấu nháy kép, newline, backslash, khoảng trắng, Unicode và việc có newline cuối hay không.
2. **Thay bằng một text block** có phần nội dung dễ đọc. Dùng dấu nháy kép trực tiếp khi có thể.
3. **Đặt dấu đóng đúng vị trí** để giữ hoặc bỏ `\n` cuối. Không mặc định đóng trên dòng riêng luôn đúng với dữ liệu cũ.
4. **Soát indentation** mà trình biên dịch sẽ loại bỏ. Nếu có dữ liệu fixed-width, viết thêm test về độ dài và thụt lề.
5. **Giữ các escape cần thiết** như `\\`, `\t`, `\s` và những chỗ phải xử lý ba dấu nháy kép liên tiếp.
6. **Biên dịch và so sánh** chuỗi mới với chuỗi cũ bằng `String.equals` nếu mục tiêu là giữ giá trị chính xác; không chỉ nhìn xem các dòng trông tương tự nhau.
7. **Kiểm tra theo định dạng đích**: parse JSON, thử SQL với parameter binding, hoặc render HTML/XML nếu sản phẩm phụ thuộc nội dung thực.
8. **Không thay đổi cách xử lý dữ liệu động** một cách vô thức. Di chuyển từ literal cũ sang text block không làm thay đổi các yêu cầu về bảo mật hay validation.

Một phép kiểm tra hồi quy đơn giản:

```java
// Snippet đặt trong method.
String oldValue = "row1\nrow2";
String newValue = """
        row1
        row2""";

if (!oldValue.equals(newValue)) {
    throw new AssertionError("Text block changed the string");
}
```

Ở đây hai chuỗi bằng nhau từng ký tự. Chỉ cần dịch dấu đóng của `newValue` sang dòng riêng là giá trị khác `oldValue` do thêm newline cuối.

## 8. Các hiểu nhầm và lỗi thường gặp

| Nhận định / lỗi | Vì sao không đúng | Cách sửa |
| --- | --- | --- |
| Viết `"""hello"""` trên một dòng | Sai cú pháp mở text block | Đặt newline sau `"""` mở |
| Tưởng text block là raw string | Java vẫn diễn giải escape | Giữ `\\` cho backslash, kiểm tra `\n` và `\t` |
| Đóng trên dòng riêng nhưng muốn không có newline cuối | Java thêm `\n` cuối | Đóng ngay sau nội dung cuối hoặc điều chỉnh có kiểm chứng |
| Dời dấu đóng trái/phải mà không test | Có thể đổi incidental indentation | So sánh giá trị chuỗi và kiểm tra whitespace |
| Dùng dấu cách cuối dòng trong editor để giữ trailing spaces | Java có thể xóa chúng | Dùng `\s` hoặc biểu diễn tường minh |
| Cho rằng dấu `"` trong text block luôn cần `\"` | Dấu nháy kép đơn lẻ không cần escape | Viết JSON/HTML trực tiếp |
| Đưa ba dấu nháy kép liên tiếp vào thân | Có thể bị hiểu là dấu đóng | Escape một dấu hoặc đổi cấu trúc |
| Nghĩ text block kiểm tra JSON/SQL | javac chỉ kiểm tra cú pháp literal Java | Parse hoặc validate định dạng riêng |
| Ghép trực tiếp dữ liệu không tin cậy vào SQL | SQL injection vẫn xảy ra | Dùng `PreparedStatement` |
| Mong biến được nội suy tự động | Text block không có nội suy biến mặc định | Dùng `formatted` hoặc API chuyên dụng |
| Dùng text block cho một chuỗi ngắn không có layout | Có thể làm mã dài thêm | Tiếp tục dùng literal `"..."` nếu rõ hơn |
| Chỉ nhìn source rồi khẳng định chuỗi giống bản cũ | Bỏ sót newline/indentation/escape | Test `equals` và ngữ nghĩa format đích |

## 9. Câu hỏi tự kiểm tra

**1.** Tại sao `"""hello"""` không hợp lệ dù `"hello"` hợp lệ?

Vì text block yêu cầu ký tự kết thúc dòng ngay sau dấu `"""` mở. Literal `"hello"` thông thường không có yêu cầu này.

**2.** Hai đoạn sau có bằng nhau không?

```java
String a = "hello\nworld";
String b = """
        hello
        world""";
```

Có. Cả hai là `"hello\nworld"`. Nếu dấu đóng của `b` chuyển xuống dòng riêng, `b` sẽ có thêm newline cuối.

**3.** Vì sao `List` dữ liệu chuỗi trong JSON có thể viết như mã JSON thật, nhưng đường dẫn Windows vẫn phải lưu ý `\\`?

Dấu nháy kép và xuống dòng thường đã hiện diện trực tiếp trong text block, nhưng backslash vẫn là ký tự bắt đầu escape Java. Text block không phải raw string.

**4.** `\s` giải quyết điều gì?

Nó tạo một dấu cách được xử lý sau bước loại bỏ khoảng trắng vô tình, hữu ích để giữ trailing spaces khi cần chính xác dữ liệu.

**5.** Chèn một giá trị người dùng vào SQL text block qua `formatted` đã đủ an toàn chưa?

Chưa. Dùng parameter binding qua `PreparedStatement` thay vì ghép thẳng input vào câu SQL. Cú pháp text block không thay đổi quy tắc chống injection.

**6.** Khi thay `"..." + ` bằng text block, phép kiểm tra nào trực tiếp nhất nếu yêu cầu giữ nguyên giá trị?

Tạo hai `String` (cũ và mới) rồi dùng `oldValue.equals(newValue)`, kết hợp kiểm thử các tình huống dữ liệu đích quan tâm đến newline, whitespace hoặc encoding.

## 10. Nguồn chính thức và tài liệu hiện hành

- [OpenJDK JEP 378 — Text Blocks](https://openjdk.org/jeps/378): chuẩn hóa text blocks từ Java 15.
- [Oracle — Programmer's Guide to Text Blocks (Java 17)](https://docs.oracle.com/en/java/javase/17/text-blocks/index.html): cú pháp, newline cuối, incidental whitespace, escape và hướng dẫn bố cục.
- [Oracle — Text Blocks (Java 26)](https://docs.oracle.com/en/java/javase/26/language/text-blocks.html): tài liệu ngôn ngữ cập nhật về text blocks.
- [Java Language Specification — Text Blocks, `3.10.6](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.6): quy tắc cú pháp và giá trị text block.

**Ghi nhớ:** text block giúp giảm `\n`, `\"` và `+` khi biểu diễn chuỗi nhiều dòng, nhưng **vẫn là `String` với quy tắc indentation, xuống dòng và escape cụ thể**. Khi refactor, giữ đúng giá trị và tiếp tục bảo đảm an toàn cho dữ liệu động.
