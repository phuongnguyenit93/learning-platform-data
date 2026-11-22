# Text block có cùng kiểu `String` với literal thông thường (Java 15+)

> **Mục tiêu:** hiểu rằng Java text block (`""" ... """`) và string literal (`"..."`) đều tạo ra giá trị thuộc `java.lang.String`, dùng chung API, quy tắc bình đẳng, cơ chế intern và nơi có thể sử dụng trong chương trình. Điểm khác biệt là **cú pháp viết nguồn** và **quy trình tạo chuỗi ký tự thực tế**, nhất là xuống dòng, thụt lề và escape. Text block đã trở thành tính năng **chính thức ở Java 15** (JEP 378), vẫn áp dụng trong Java hiện đại; ví dụ dùng JDK 17+ và không cần chế độ preview của Java 14.

## 1. Khái niệm: hai cách viết, cùng một kiểu dữ liệu

Trong Java, chuỗi thông thường dùng cặp dấu nháy kép `"..."`, còn **text block** dùng dấu phân cách ba nháy kép `"""` để đặt nội dung thường gồm nhiều dòng. Dù cách viết khác nhau, **giá trị thu được vẫn là một đối tượng `java.lang.String`**. Java không có một kiểu runtime riêng tên `TextBlock`.

```java
String ordinary = "Hello\nJava\n";
String block = """
        Hello
        Java
        """;

System.out.println(ordinary.equals(block)); // true
System.out.println(block.getClass() == String.class); // true
```

Đây là đoạn mã minh họa đặt trong một phương thức. Hai biến có cùng **chuỗi ký tự** `H e l l o LF J a v a LF` sau khi trình biên dịch xử lý text block, nên `equals()` trả `true`. Dấu xuống dòng nằm giữa các dòng là ký tự `\n` (LF). Một text block không phải `StringBuilder`, `char[]`, `List<String>`, template engine hay luồng dữ liệu đặc biệt.

**Hệ quả thực tế:** mọi nơi API yêu cầu `String` đều có thể nhận text block, chẳng hạn tham số phương thức, giá trị `return`, toán tử nối chuỗi `+`, khai báo hằng chuỗi, khóa `Map`, phần tử `Set`, nội dung JSON/XML/SQL hay văn bản nhiều dòng. Một phương thức nhận `String` **không biết** dữ liệu đến từ literal một dòng, text block hay kết quả tính toán ở runtime.

## 2. Cú pháp text block và dấu xuống dòng sau dấu mở

Phần mở text block gồm ba dấu `"""`, có thể có khoảng trắng, và **phải kết thúc bằng dấu xuống dòng**. Nội dung chỉ bắt đầu từ dòng tiếp theo. Phần đóng cũng là ba dấu `"""`, có thể đặt trên dòng riêng hoặc ngay cuối dòng nội dung.

```java
String greeting = """
        Hello, Mai!
        Welcome.
        """;
```

Đoạn này tương đương về nội dung với:

```java
String greeting = "Hello, Mai!\nWelcome.\n";
```

Dòng xuống sau dấu mở dùng để phân tách cú pháp **không tự trở thành một ký tự LF đầu chuỗi**. Trái lại, khi dấu đóng nằm **trên một dòng riêng**, LF ở cuối dòng nội dung cuối cùng thường được giữ lại. Khi dấu đóng ở **cùng dòng với ký tự cuối**, không có LF bổ sung sau ký tự đó.

```java
String withFinalLf = """
        red
        blue
        """;                 // "red\nblue\n"

String withoutFinalLf = """
        red
        blue""";            // "red\nblue"
```

**Hai lỗi cú pháp thường gặp:**

```java
// CỐ Ý SAI: không có xuống dòng ngay sau dấu mở.
String bad1 = """hello""";

// CỐ Ý SAI: nội dung bắt đầu ngay trên dòng mở.
String bad2 = """hello
    world
    """;
```

Muốn biểu diễn một dòng bằng text block, vẫn phải có xuống dòng sau dấu mở, chẳng hạn `String one = """` rồi `hello""";` trên dòng tiếp. Nhưng nếu chuỗi chỉ gồm một dòng ngắn, literal `"hello"` thông thường thường rõ ràng hơn.

## 3. Cùng API `String`, cùng toán tử và kiểu tham số

Không có bộ phương thức riêng cho text block. Giá trị của nó gọi được toàn bộ API công khai thích hợp của `String`: `length()`, `substring()`, `contains()`, `replace()`, `equals()`, `hashCode()`, `lines()`, `strip()`, `isBlank()`, `formatted()`, `getBytes(...)`, v.v.

```java
String message = """
        Hello
        Java
        """;

int numberOfChars = message.length();     // 11: 5 + LF + 4 + LF.
long lineCount = message.lines().count(); // 2.
String upper = message.toUpperCase(java.util.Locale.ROOT);
String firstLine = message.lines().findFirst().orElse(""); // "Hello".
```

Khác với `String.split("\n")`, `String.lines()` hiểu các dạng kết thúc dòng theo hợp đồng API và là cách trực quan để xử lý văn bản từng dòng. Cả literal và text block đều có thể gọi API này. `String.length()` đo **đơn vị UTF-16**, không nhất thiết là số ký tự người dùng nhìn thấy nếu chứa ký tự Unicode ngoài BMP; quy tắc ấy áp dụng như nhau cho hai cách tạo chuỗi.

**Truyền tham số / trả về:**

```java
static String firstLine(String text) {
    return text.lines().findFirst().orElse("");
}

// Gọi trong một phương thức:
String head = firstLine("""
        red
        blue
        """); // "red".
```

Phương thức `firstLine(String text)` nhận `String`, không cần một overload dành riêng cho text block. Khả năng dùng text block cũng không phụ thuộc việc đối số được tạo ở compile time hay runtime.

**Nối chuỗi:** `"prefix:" + block` và `block + "suffix"` đều hợp lệ. Kiểu biểu thức vẫn là `String`; dấu cộng có cùng ngữ nghĩa nối ký tự như với literal. Vì vậy text block có thể được kết hợp với các literal thông thường và các biến chuỗi.

## 4. `equals()`, `hashCode()` và việc sử dụng làm khóa

Hai `String` bằng nhau theo `equals()` khi có **cùng dãy ký tự**, không phụ thuộc cách biểu diễn tại mã nguồn. Do đó text block và literal chuẩn có thể thay nhau trong `HashMap<String,V>` hoặc `HashSet<String>` khi giá trị chuỗi đã tạo ra chính xác như nhau.

```java
String a = "red\nblue\n";
String b = """
        red
        blue
        """;

System.out.println(a.equals(b));                   // true
System.out.println(a.hashCode() == b.hashCode()); // true
System.out.println(java.util.Map.of(b, 7).get(a)); // 7
```

`hashCode()` là hàm băm của giá trị `String` theo hợp đồng API `String`, **không có** hàm băm khác dành riêng cho text block. Nếu `equals()` trả `true` thì hash phải bằng nhau. Ngược lại, hai hash bằng nhau không chứng minh chuỗi bằng nhau vì có thể va chạm hash. Đừng dùng `hashCode()` làm ID hoặc checksum bảo mật.

**Bẫy:** một text block trông giống literal nhưng có thêm `\n`, dấu cách, tab hoặc khác ký tự Unicode thì **không bằng nhau**. Ví dụ `"red\nblue"` khác `"red\nblue\n"`. Khi tra cứu thất bại, hãy kiểm tra ký tự thực tế (`length`, `endsWith("\n")`, mã code point hoặc hiển thị ký tự xuống dòng), không suy luận từ cách editor căn dòng.

## 5. Hai loại literal được intern nhưng `==` vẫn không phải cách so sánh chuỗi

Theo Java Language Specification, giá trị của **string literal** và **text block** được intern vào string pool. Khi hai literal thuộc hai cách viết biểu diễn **đúng cùng giá trị**, tham chiếu chúng được chuẩn hóa về cùng instance:

```java
String ordinary = "red\nblue\n";
String block = """
        red
        blue
        """;

System.out.println(ordinary == block);      // true với hai literal cùng giá trị.
System.out.println(ordinary.equals(block)); // true.
```

`==` ở ví dụ này trả `true` vì hai biểu thức đều là literal được intern — **không phải vì `String` dùng `==` để so sánh nội dung**. Với chuỗi được tạo hoặc sửa ở runtime, tham chiếu có thể khác dù ký tự giống nhau:

```java
String runtime = new String("red\nblue\n");
System.out.println(runtime.equals(block)); // true.
System.out.println(runtime == block);      // false: đối tượng runtime khác.
```

**Quy tắc thực hành:** so sánh nội dung bằng `equals()` (hoặc `Objects.equals()` khi có thể `null`). Không xây dựng kiểm tra nghiệp vụ dựa trên `==` vì dữ liệu không phải lúc nào cũng đến trực tiếp từ literal; `intern()` không phải giải pháp mặc định cho việc so sánh chuỗi.

## 6. Quy trình xử lý text block quyết định giá trị `String` thực tế

Text block không phải khối ký tự “raw”. Trình biên dịch xử lý nó theo thứ tự:

1. **Chuẩn hóa kết thúc dòng** trong text block thành LF (`\n`): CRLF và CR trong mã nguồn được chuẩn hóa.
2. **Loại khoảng trắng thụt lề phụ (incidental whitespace)** dựa trên lề chung của các dòng và vị trí dấu đóng, tương đương về kết quả với quá trình `String.stripIndent()` được JLS mô tả.
3. **Diễn giải escape sequences** sau cùng, tương đương giai đoạn xử lý `String.translateEscapes()` được JLS quy định.

Đây là quy tắc tạo ký tự của `String`, không làm thay đổi kiểu dữ liệu. Kết quả đã tạo có thể truyền sang bất kỳ API `String` nào như thông thường.

### 6.1. Thụt lề được loại bỏ khi là incidental

```java
String json = """
        {
          "name": "Mai",
          "active": true
        }
        """;
```

Với dấu đóng ở cùng lề cơ sở của nội dung, Java bỏ phần thụt lề do căn chỉnh mã nguồn, nhưng giữ mức lùi tương đối hai dấu cách của những dòng bên trong object. Dấu cách có ý nghĩa nghiệp vụ nằm sâu hơn lề cơ sở vẫn được giữ.

Đặt dấu `"""` đóng ở vị trí khác có thể thay đổi **phần thụt lề** được loại và dẫn đến một chuỗi khác. Khi dữ liệu có yêu cầu chính xác từng ký tự (snapshot, chữ ký số, JSON chuẩn hóa, request body), hãy kiểm tra chuỗi sau biên dịch thay vì chỉ nhìn hình thức trong editor.

### 6.2. Xuống dòng cuối và line continuation

```java
String a = """
        A
        B
        """;       // "A\nB\n"

String b = """
        A
        B""";      // "A\nB"

String joined = """
        A\
        B
        """;       // "AB\n": backslash ngay trước xuống dòng nối hai dòng.
```

Dấu gạch chéo ngược `\` **ngay trước kết thúc dòng** là *line continuation*; nó loại bỏ xuống dòng đó khi diễn giải escape. Đây không phải thao tác nối hai đối tượng `String`: toàn bộ text block vẫn biểu diễn một giá trị `String` duy nhất.

### 6.3. Escape vẫn được hỗ trợ; text block không tự nội suy biến

Cả literal và text block hỗ trợ những escape thông dụng như `\n`, `\t`, `\r`, `\"`, `\\`, `\s` (space), cũng như line continuation trong text block. Dấu nháy kép đơn lẻ bên trong text block thường **không cần** viết thành `\"`, nhưng một dãy `"""` có thể kết thúc text block nên phải được escape thích hợp khi cần chứa ba dấu nháy liền nhau.

```java
String withTrailingSpace = """
        A\s
        """; // "A \n": \s tạo dấu cách ở cuối dòng sau khi loại thụt lề.

String plainQuotes = """
        {"name":"Mai"}
        """;
```

Những cách viết ``\s` hoặc dùng escape khác hữu ích vì trình biên dịch thường loại khoảng trắng cuối dòng của text block khi xử lý thụt lề. `\s` được diễn giải **sau** bước đó nên giữ được dấu cách mong muốn. Muốn đưa chính ký tự `\` vào chuỗi, vẫn phải escape như với literal thông thường.

**Text block không tự thay thế `${name}`, `{name}` hoặc `%s` bằng giá trị biến.** Muốn điền dữ liệu, dùng API `String.formatted(...)`, `String.format(...)` hoặc công cụ chuyên dụng tùy ngữ cảnh. Ví dụ:

```java
String template = """
        Hello, %s!
        Role: %s
        """;
String message = template.formatted("Mai", "admin");
// message là String chứa "Hello, Mai!\nRole: admin\n".
```

`String.formatted(...)` có từ Java 15, dùng quy tắc định dạng của `Formatter`, **không** phải interpolation ngôn ngữ bên trong text block. Khi xây dựng SQL, đừng nối trực tiếp dữ liệu không tin cậy vào text block hay `.formatted` để thay cho parameter binding: phải dùng `PreparedStatement` với tham số ràng buộc. Với HTML/JSON, hãy dùng serializer/encoder đúng ngữ cảnh nếu có dữ liệu đầu vào.

## 7. Chương trình Java 17+ đầy đủ: hai cách viết `String` hoạt động giống nhau

Tạo tệp **`TextBlockStringDemo.java`** dưới đây. Chương trình kiểm tra kiểu, bình đẳng, hash, interning của literal, API `String`, newline, line continuation, định dạng và khóa `Map`.

```java
public class TextBlockStringDemo {
    static String firstLine(String text) {
        return text.lines().findFirst().orElse("");
    }

    public static void main(String[] args) {
        String literal = "red\nblue\n";
        String block = """
                red
                blue
                """;

        String noFinalNewline = """
                red
                blue""";

        String joined = """
                A\
                B
                """;

        String preservedSpace = """
                A\s
                """;

        String template = """
                Hello, %s!
                Role: %s
                """;

        String json = """
                {"name":"Mai","roles":["editor"]}
                """;

        System.out.println("class=" + block.getClass().getSimpleName());
        System.out.println("equals=" + literal.equals(block));
        System.out.println("sameHash=" + (literal.hashCode() == block.hashCode()));
        System.out.println("literalInterned=" + (literal == block));
        System.out.println("length=" + block.length());
        System.out.println("lines=" + block.lines().count());
        System.out.println("first=" + firstLine(block));
        System.out.println("endsLF=" + block.endsWith("\n"));
        System.out.println("noFinalLF=" + noFinalNewline.equals("red\nblue"));
        System.out.println("joined=" + joined.strip());
        System.out.println("preservedSpace=" + preservedSpace.endsWith(" \n"));
        System.out.println("formatted=" +
            template.formatted("Mai", "admin").replace("\n", "|"));
        System.out.println("json=" + json.strip());
        System.out.println("mapKey=" + java.util.Map.of(block, 7).get(literal));
    }
}
```

Biên dịch và chạy bằng JDK 17+ (không cần `--enable-preview`):

```bash
javac -encoding UTF-8 TextBlockStringDemo.java
java TextBlockStringDemo
```

**Stdout chính xác:**

```text
class=String
equals=true
sameHash=true
literalInterned=true
length=9
lines=2
first=red
endsLF=true
noFinalLF=true
joined=AB
preservedSpace=true
formatted=Hello, Mai!|Role: admin|
json={"name":"Mai","roles":["editor"]}
mapKey=7
```

**Giải thích kết quả:** `block` và `literal` biểu diễn `"red\nblue\n"`, dài 9 đơn vị UTF-16, gồm 2 dòng văn bản. Hai literal được intern cùng giá trị nên `==` cũng đúng **trong riêng trường hợp này**, nhưng không nên dùng `==` để so sánh các chuỗi có thể được tạo động. Dấu đóng ngay sau `blue` loại LF cuối; `A\` nối dòng trước dòng `B`; `A\s` giữ dấu cách ngay trước LF; `formatted()` tạo một `String` mới có dữ liệu thay thế vào `%s`; `Map` tra ra `7` bằng giá trị của khóa.

## 8. Các tình huống dùng text block đúng cách

| Tình huống | Chọn dạng nào? | Lý do |
|---|---|---|
| Chuỗi một dòng ngắn như thông báo lỗi hoặc mã trạng thái | Literal `"..."` | Ít cú pháp, dễ nhìn |
| JSON/XML/HTML tĩnh nhiều dòng | Text block | Tránh nhiều chuỗi nối và escape dấu nháy kép |
| Câu SQL nhiều dòng **tĩnh** | Text block + `PreparedStatement` | Dễ trình bày câu truy vấn, dữ liệu đầu vào vẫn phải bind tham số |
| Đoạn văn nhiều dòng hoặc template định dạng | Text block + `formatted()`/công cụ chuyên dụng | Rõ cấu trúc, dữ liệu vẫn là `String` |
| Nội dung cần giữ đúng CRLF hay khoảng trắng cuối | Cân nhắc explicit escapes / kiểm thử ký tự | Text block chuẩn hóa line ending và loại incidental whitespace |
| Chuỗi nhận từ API/input người dùng | Các API tạo `String` thông thường | Text block chỉ là cú pháp ở mã nguồn, không thay thế xử lý input runtime |

Trong mọi trường hợp, chữ ký phương thức vẫn nhận `String` hoặc kiểu chung như `CharSequence` như bình thường. Chọn cách viết theo **khả năng đọc và bảo toàn nội dung**, không theo hiệu suất được giả định: không có bằng chứng ngôn ngữ bảo đảm text block luôn chạy nhanh hơn literal.

## 9. Những nhầm lẫn và lỗi phổ biến

### Nhầm 1: text block tạo ra một kiểu riêng

**Sai:** tạo overload `process(TextBlock value)` hoặc chờ một `TextBlock.class` tồn tại trong Java chuẩn. **Đúng:** dùng `process(String value)`; text block là một biểu thức kiểu `String`.

### Nhầm 2: hai chuỗi nhìn giống nhau thì `equals()` luôn bằng nhau

```java
String literal = "a\nb";
String block = """
        a
        b
        """;
System.out.println(literal.equals(block)); // false: block có LF cuối.
```

**Sửa:** đặt dấu `"""` đóng ngay sau `b` nếu không muốn LF cuối, hoặc viết literal với `\n` cuối. Đừng gọi `strip()`/`trim()` bừa bãi để che mất khác biệt nếu khoảng trắng là dữ liệu có ý nghĩa.

### Nhầm 3: viết nội dung ngay sau dấu mở

```java
String invalid = """one line"""; // LỖI cú pháp.
```

**Sửa:** phải xuống dòng sau dấu mở; dùng literal thông thường nếu chỉ có một dòng.

### Nhầm 4: text block giữ nguyên CRLF hoặc thụt lề như file nguồn

Trình biên dịch chuẩn hóa kết thúc dòng thành LF và loại incidental indentation; nếu chương trình cần byte-for-byte tương thích với giao thức khác, hãy dùng đúng escape, encoding và kiểm thử. `getBytes(StandardCharsets.UTF_8)` vẫn là lời gọi API của `String`; text block không tự tạo mảng byte.

### Nhầm 5: text block tự nội suy biến

```java
String name = "Mai";
String text = """
        Hello, ${name}
        """;
// text chứa đúng chữ ${name}, không tự chèn giá trị của biến name.
```

**Sửa:** sử dụng `%s` cùng `formatted(name)` hoặc một cơ chế template rõ ràng, kèm escaping/binding khi đưa dữ liệu vào SQL/HTML/JSON.

### Nhầm 6: `==` là cách kiểm tra String bằng nhau

`ordinary == block` có thể `true` khi cả hai đều là literal được intern, nhưng chuỗi tạo bằng `new String(...)`, API đọc file, `formatted(...)` hoặc thao tác biến đổi không nhất thiết có cùng tham chiếu. **Dùng `equals` cho bình đẳng nội dung.**

### Nhầm 7: nghĩ text block luôn phải chứa nhiều dòng

Cú pháp bắt buộc có xuống dòng ngay sau dấu mở nhưng chuỗi kết quả **có thể chỉ có một dòng hoặc rỗng** tùy vị trí dấu đóng. Vì vậy lựa chọn text block là vấn đề thuận tiện của mã nguồn, không phải điều kiện số dòng của giá trị `String`.

## 10. Checklist kiểm thử khi chuyển literal sang text block

1. Giá trị sau chuyển đổi có đúng là `String` và vẫn phù hợp với kiểu tham số của API đang gọi?
2. Có cần LF **ở cuối** chuỗi không? Dấu `"""` đóng đang ở dòng riêng hay cùng dòng nội dung cuối?
3. Có thay đổi số lượng khoảng trắng đầu/cuối dòng sau khi Java loại incidental whitespace?
4. Kết thúc dòng trong chuỗi có đúng là LF (`\n`), hay bài toán cần CRLF (`\r\n`) khác?
5. Nếu xuất hiện `\`, dấu nháy liên tiếp hoặc `%s`, đã xác định escape/format chính xác chưa?
6. Đã so sánh **giá trị** với literal cũ bằng `equals()` thay vì chỉ so bằng mắt hoặc `==`?
7. Nếu dữ liệu đi tới `HashMap`/`HashSet`, ký tự chuỗi có hoàn toàn khớp với khóa tham chiếu không?
8. Với dữ liệu động (SQL, HTML, JSON), đã dùng tham số ràng buộc/serializer/escaping phù hợp chưa?
9. Có test `length()`, `endsWith("\n")`, `lines()` và ký tự đặc biệt nếu kết quả cần chính xác từng ký tự?
10. Đã biên dịch với JDK 17+ hoặc mức Java chính thức phù hợp (Java 15+), không sử dụng preview flags cũ?

## Tài liệu tham khảo chính thức

- Java Language Specification (SE 25), §3.10.5 *String Literals* và §3.10.6 *Text Blocks* — text block luôn có kiểu `String`, xử lý LF/indent/escape, và interning: https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.6
- Oracle, *Programmer's Guide to Text Blocks* (hướng dẫn cú pháp và sử dụng, Java 15+): https://docs.oracle.com/en/java/javase/25/text-blocks/index.html
- Oracle, *Text Blocks* (Java SE 26): https://docs.oracle.com/en/java/javase/26/language/text-blocks.html
- OpenJDK, JEP 378 *Text Blocks* — tính năng hoàn thiện trong Java 15: https://openjdk.org/jeps/378
- Java SE 17 API, `String` (`equals`, `hashCode`, `lines`, `formatted`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html
