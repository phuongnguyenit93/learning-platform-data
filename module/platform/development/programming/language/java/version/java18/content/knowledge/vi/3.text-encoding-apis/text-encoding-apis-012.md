# Properties.load(InputStream) và store(OutputStream): hợp đồng ISO-8859-1 vẫn cần được hiểu đúng

## 1. Vì sao Java Properties vẫn có quy tắc mã hóa riêng?

`java.util.Properties` là API lưu các cặp khóa–giá trị dạng chuỗi, thường dùng cho cấu hình ứng dụng. Hai phương thức `load(InputStream)` và `store(OutputStream, String)` làm việc trực tiếp với luồng byte, nhưng **hợp đồng của chúng quy định ISO-8859-1 (Latin-1)**.

Điều này vẫn đúng trên Java 18 và các JDK hiện đại. JEP 400 đưa UTF-8 thành default charset thông thường cho nhiều API Java từ Java 18, nhưng không thay đổi hợp đồng riêng của `Properties.load(InputStream)` hoặc `Properties.store(OutputStream, ...)`.

```text
Tệp .properties theo hợp đồng byte truyền thống
        |
        | byte được diễn giải theo ISO-8859-1
        v
Properties.load(InputStream)
        |
        | xử lý cú pháp, escape và Unicode escape
        v
Properties (String key -> String value)

Properties
        |
        | escape ký tự theo định dạng .properties
        v
Properties.store(OutputStream, comments)
        |
        | byte theo ISO-8859-1
        v
Tệp .properties
```

Điểm quan trọng là phân biệt **charset của luồng byte** với **cú pháp của định dạng properties**. ISO-8859-1 xác định cách ánh xạ byte thành ký tự ở hai API này; cú pháp `\uXXXX`, dấu phân cách, comment và nối dòng xác định cách diễn giải các ký tự sau đó.

Sau bài này, bạn có thể đọc/ghi đúng file properties theo hợp đồng ISO-8859-1, chọn cặp `InputStream` hoặc `Reader` theo encoding thực tế, xử lý Unicode escape, quản lý vòng đời stream và tránh nhầm lẫn do UTF-8 mặc định từ Java 18.

## 2. Hợp đồng chính xác của hai phương thức

| Phương thức | Đầu vào/đầu ra | Charset hoặc cách xử lý |
| --- | --- | --- |
| `Properties.load(InputStream)` | Luồng byte | Giả định ISO-8859-1; mỗi byte tương ứng một ký tự Latin-1 |
| `Properties.store(OutputStream, String)` | Luồng byte | Ghi theo ISO-8859-1; các ký tự cần thiết được biểu diễn bằng Unicode escape |
| `Properties.load(Reader)` | Luồng ký tự | Không tự chọn charset; Reader đã quyết định cách decode |
| `Properties.store(Writer, String)` | Luồng ký tự | Không tự chọn charset; Writer đã quyết định cách encode |

Hai phương thức `InputStream`/`OutputStream` tạo thành một cặp phù hợp để đọc và ghi định dạng properties truyền thống:

```java
Properties properties = new Properties();

try (InputStream input = Files.newInputStream(path)) {
    properties.load(input);
}

try (OutputStream output = Files.newOutputStream(path)) {
    properties.store(output, "Application settings");
}
```

`load(InputStream)` và `store(OutputStream, ...)` không hỏi `Charset.defaultCharset()`. Không cần thêm `InputStreamReader` hoặc `OutputStreamWriter` để ép UTF-8 vào cặp API này; việc đó sẽ thay đổi tầng chuyển mã và có thể làm lệch hợp đồng byte.

## 3. Java 18 và JEP 400 không thay đổi ISO-8859-1 của Properties

JEP 400 — UTF-8 by Default — quy định UTF-8 là default charset thông thường của Java SE từ Java 18. Thay đổi này áp dụng cho những API có hợp đồng sử dụng default charset.

`Properties.load(InputStream)` và `Properties.store(OutputStream, ...)` có quy tắc encoding được ghi riêng trong Javadoc: ISO-8859-1. Do đó:

- `load(InputStream)` vẫn đọc byte theo Latin-1 trên JDK 18+.
- `store(OutputStream, comments)` vẫn ghi luồng byte theo Latin-1 trên JDK 18+.
- `Charset.defaultCharset()` không quyết định encoding của hai phương thức này.
- Unicode nằm ngoài ASCII trong key/value được biểu diễn bằng `\uXXXX` khi `store(OutputStream, ...)` ghi ra.

Ví dụ kiểm tra default charset:

```java
import java.nio.charset.Charset;

System.out.println(Charset.defaultCharset());
```

Trong cấu hình thông thường của JDK 18+, kết quả thường là `UTF-8`. Nhưng điều đó không làm cho `Properties.load(InputStream)` tự chuyển sang UTF-8.

Đây là khác biệt quan trọng khi nâng cấp ứng dụng: một file `.properties` được đọc trước đây bằng `load(InputStream)` vẫn phải được đọc theo cùng hợp đồng. Nếu file thực sự được lưu dưới dạng UTF-8 với ký tự Unicode trực tiếp, hãy dùng `Reader` được tạo bằng UTF-8 và gọi `load(Reader)`.

## 4. Vì sao byte UTF-8 có thể thành ký tự sai khi gọi load(InputStream)?

Giả sử file UTF-8 chứa giá trị `café`. Trong UTF-8, chữ `é` được mã hóa thành hai byte `C3 A9`. Khi gọi `load(InputStream)`, mỗi byte được diễn giải như một ký tự ISO-8859-1:

| Byte | Ký tự Latin-1 tương ứng |
| --- | --- |
| `C3` | `Ã` |
| `A9` | `©` |

Kết quả có thể thành `cafÃ©`, dù byte ban đầu là UTF-8 hợp lệ. Đây là lỗi **đọc bằng sai hợp đồng charset**, không phải lỗi parser của `Properties`.

```java
// Không phù hợp nếu file được lưu bằng UTF-8 với Unicode trực tiếp.
Properties properties = new Properties();
try (InputStream input = Files.newInputStream(path)) {
    properties.load(input); // Luôn áp dụng ISO-8859-1 cho byte.
}
```

Nếu file là UTF-8, hãy decode ở tầng Reader:

```java
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

Properties properties = new Properties();

try (Reader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    properties.load(reader);
}
```

`load(Reader)` nhận ký tự đã được Reader giải mã. `Properties` tiếp tục phân tích cùng cú pháp dòng và Unicode escape, nhưng không tự áp thêm ISO-8859-1 lên ký tự đó.

## 5. Unicode escape trong định dạng properties

Định dạng properties có thể biểu diễn ký tự ngoài Latin-1 bằng Unicode escape dạng `\uXXXX`, trong đó `XXXX` là bốn chữ số thập lục phân biểu diễn một đơn vị mã UTF-16.

Ví dụ nội dung file:

```properties
language=vi
greeting=Ti\u1EBFng Vi\u1EC7t
currency=\u20AC
```

Sau khi gọi `load(InputStream)` hoặc `load(Reader)`, các giá trị tương ứng là:

- `language` → `vi`
- `greeting` → `Tiếng Việt`
- `currency` → `€`

`store(OutputStream, ...)` tự tạo Unicode escape cho ký tự ngoài vùng in ASCII trong key/value, nên ứng dụng không cần tự thay mọi ký tự tiếng Việt thành `\uXXXX`.

### 5.1. Unicode escape biểu diễn đơn vị mã UTF-16

Một Unicode escape `\uXXXX` chứa đúng bốn chữ số hex, biểu diễn một đơn vị mã UTF-16. Ký tự ngoài BMP như `🌍` được biểu diễn bằng cặp surrogate, vì vậy file properties có thể chứa hai Unicode escape liên tiếp thay vì một escape duy nhất.

Không nhầm `\uXXXX` trong file properties với cách viết `\u{...}` của một số ngôn ngữ khác. Định dạng properties dùng đúng bốn chữ số hex và chỉ cho phép một chữ `u` trong escape.

### 5.2. Escape đặc biệt và dấu gạch chéo ngược

Các escape thường gặp:

| Escape | Ký tự sau khi load |
| --- | --- |
| `\t` | Tab |
| `\n` | Line feed |
| `\r` | Carriage return |
| `\f` | Form feed |
| `\\` | Dấu gạch chéo ngược `\` |
| `\uXXXX` | Đơn vị mã UTF-16 được chỉ định |

Dấu `#`, `!`, `=`, `:` và khoảng trắng ở một số vị trí có ý nghĩa cú pháp. Khi cần đưa chúng vào key/value như ký tự thông thường, phải escape theo quy tắc của định dạng. `store(...)` thực hiện việc escape cần thiết khi ghi.

Một khác biệt dễ nhầm: `\b` không có nghĩa là backspace trong định dạng properties; dấu gạch chéo ngược trước một ký tự escape không hợp lệ có thể bị bỏ qua thay vì báo lỗi. Vì vậy, không áp dụng máy móc toàn bộ quy tắc escape của Java string literal vào file properties.

## 6. Cú pháp dòng, comment và dấu phân cách

File properties là định dạng văn bản theo dòng. Các quy tắc quan trọng:

- Dòng trống bị bỏ qua.
- Dòng comment bắt đầu bằng `#` hoặc `!` ở ký tự không phải whitespace đầu tiên.
- Key bắt đầu từ ký tự không phải whitespace đầu tiên.
- Key kết thúc tại dấu `=`, dấu `:`, hoặc whitespace đầu tiên chưa được escape.
- Sau key, whitespace được bỏ qua; dấu `=` hoặc `:` tiếp theo cũng được bỏ qua.
- Phần còn lại của dòng là value; nếu không còn nội dung, value là chuỗi rỗng.

Các dòng sau đều tạo cùng cặp key/value:

```properties
Truth = Beauty
Truth:Beauty
Truth                    :Beauty
```

Kết quả:

```text
key   = Truth
value = Beauty
```

Dấu phân cách đầu tiên chưa escape quyết định ranh giới key/value. Nếu dấu `=`, `:` hoặc khoảng trắng cần nằm trong key, phải có dấu `\` đứng trước theo cú pháp properties.

### 6.1. Nối dòng bằng dấu gạch chéo ngược

Một logical line có thể trải qua nhiều natural line. Nếu một dòng kết thúc bằng số lẻ dấu gạch chéo ngược liên tiếp, dấu gạch chéo cuối cùng escape line terminator; dòng tiếp theo được nối vào. Whitespace đầu dòng tiếp theo bị bỏ qua.

```properties
message=Java Properties có thể \
        nối nội dung qua nhiều dòng \
        trong cùng một giá trị
```

Giá trị sau khi load là một chuỗi liên tục; dấu `\` dùng để nối dòng, line separator và whitespace đầu dòng tiếp theo không được giữ lại. Nếu có số chẵn dấu `\` liên tiếp trước line terminator, chúng được xử lý theo cặp và line terminator không được escape theo cách này.

Comment không được nối tiếp bằng cơ chế continuation; mỗi natural line comment phải có dấu `#` hoặc `!` riêng.

## 7. Đọc file properties theo định dạng ISO-8859-1

Khi file được tạo theo định dạng truyền thống của `Properties.store(OutputStream, ...)`, dùng `load(InputStream)`:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

Path configPath = Path.of("application.properties");
Properties properties = new Properties();

try (InputStream input = Files.newInputStream(configPath)) {
    properties.load(input);
}

String host = properties.getProperty("server.host", "localhost");
int port = Integer.parseInt(
        properties.getProperty("server.port", "8080"));
```

`load(InputStream)` không đóng input stream. Ứng dụng sở hữu stream phải đóng nó, thường bằng try-with-resources như ví dụ trên.

Các lỗi có thể gặp:

- `IOException`: lỗi khi đọc nguồn.
- `IllegalArgumentException`: gặp Unicode escape sai định dạng, ví dụ thiếu chữ số hex sau `\u`.
- `NullPointerException`: truyền `null` làm input stream.

Vì ISO-8859-1 ánh xạ mọi giá trị byte từ `00` đến `FF` sang một ký tự Latin-1, byte bất kỳ không tạo ra lỗi malformed UTF-8 ở tầng charset. Lỗi có thể xuất hiện ở cú pháp Unicode escape hoặc ở thao tác I/O.

## 8. Ghi file bằng store(OutputStream, comments)

`store(OutputStream, comments)` ghi properties theo định dạng phù hợp để đọc lại bằng `load(InputStream)`. Luồng byte được mã hóa bằng ISO-8859-1.

Đối với key và value, các ký tự nhỏ hơn `U+0020` và lớn hơn `U+007E` được ghi dưới dạng Unicode escape `\uXXXX`. Như vậy, ký tự tiếng Việt và nhiều ký tự Unicode khác được biểu diễn bằng escape ASCII trong phần key/value.

```java
import java.io.IOException;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

Properties properties = new Properties();
properties.setProperty("language", "vi");
properties.setProperty("greeting", "Tiếng Việt");
properties.setProperty("currency", "€");

Path path = Path.of("application.properties");

try (OutputStream output = Files.newOutputStream(path)) {
    properties.store(output, "Application settings");
}
```

File được ghi theo định dạng ISO-8859-1. Giá trị `Tiếng Việt` được chuyển thành chuỗi Unicode escape; khi đọc lại bằng `load(InputStream)`, các escape được khôi phục thành Unicode ban đầu.

`store(OutputStream, ...)` flush output stream sau khi ghi xong nhưng **không đóng stream**. Try-with-resources ở ví dụ đóng tài nguyên do ứng dụng mở.

### 8.1. Comment cũng có quy tắc encoding

Nếu `comments` không phải `null`, nội dung comment được ghi ra đầu file. Ký tự trong comment không thuộc Latin-1 được biểu diễn bằng Unicode escape. Phần key/value có quy tắc riêng: ký tự nhỏ hơn `U+0020` hoặc lớn hơn `U+007E` được escape.

Do đó, không nên giả định file do `store(OutputStream, ...)` tạo ra là UTF-8 chỉ vì phần lớn key/value nhìn như ASCII. Hãy đọc lại bằng `load(InputStream)` để khớp hợp đồng.

### 8.2. Stream vẫn mở sau store

Sau khi `store(OutputStream, ...)` hoàn tất, stream đã được flush nhưng vẫn mở. Nếu cần tiếp tục ghi byte khác vào cùng stream, có thể làm như vậy theo thiết kế của ứng dụng; thông thường, hãy đóng stream ở nơi sở hữu nó.

Không gọi `store()` rồi giả định phương thức đã tự đóng file. Việc bỏ quên close có thể giữ file handle hoặc làm chậm giải phóng tài nguyên.

## 9. Cặp Reader/Writer cho file UTF-8 hiện đại

Nếu định dạng file của ứng dụng quy định UTF-8 với Unicode trực tiếp, hãy dùng `Reader` và `Writer` có charset tường minh:

```java
import java.io.Reader;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

Path path = Path.of("application-utf8.properties");

// Đọc: Files giải mã UTF-8, Properties xử lý ký tự đã decode.
Properties properties = new Properties();
try (Reader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    properties.load(reader);
}

// Ghi: Properties ghi ký tự ra Writer, Writer mã hóa UTF-8.
try (Writer writer = Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
    properties.store(writer, "UTF-8 properties");
}
```

Trong cặp này:

- `Files.newBufferedReader(..., UTF_8)` chịu trách nhiệm decode byte UTF-8 thành ký tự.
- `Properties.load(Reader)` phân tích cú pháp properties từ ký tự.
- `Properties.store(Writer, ...)` ghi ký tự properties ra Writer.
- `Files.newBufferedWriter(..., UTF_8)` chịu trách nhiệm encode ký tự thành byte UTF-8.

`store(Writer, ...)` không tự ép Unicode thành `\uXXXX` chỉ vì ký tự nằm ngoài ASCII. Writer nhận ký tự và mã hóa theo charset của nó. Nếu Writer là UTF-8, các ký tự Unicode có thể được ghi trực tiếp bằng UTF-8.

Không dùng `load(InputStream)` cho file UTF-8 trực tiếp nếu muốn giữ đúng Unicode; hãy chọn `load(Reader)` cùng Reader đã decode UTF-8.

## 10. Chọn đúng API theo định dạng file

| Định dạng byte của file | Cách đọc | Cách ghi |
| --- | --- | --- |
| `.properties` truyền thống theo ISO-8859-1 và Unicode escape | `load(InputStream)` | `store(OutputStream, comments)` |
| `.properties` UTF-8 với Unicode trực tiếp | `load(Reader)` với Reader UTF-8 | `store(Writer, comments)` với Writer UTF-8 |
| XML Properties UTF-8 | `loadFromXML(InputStream)` | `storeToXML(OutputStream, comments)` |
| XML Properties cần charset cụ thể | `loadFromXML(InputStream)` theo encoding khai báo | `storeToXML(OutputStream, comments, charset)` |

Nếu một file đã tồn tại và được nhiều chương trình dùng, hãy tuân thủ encoding mà các bên đã thống nhất. Không thay cặp `InputStream`/`OutputStream` bằng `Reader`/`Writer` UTF-8 chỉ vì JDK mới mặc định UTF-8; việc đổi encoding có thể làm ứng dụng cũ đọc sai file.

## 11. XML Properties là định dạng khác, không phải cách đổi charset cho .properties

`Properties` cũng có `storeToXML` và `loadFromXML`. Đây là định dạng XML có cấu trúc riêng, không phải file `.properties` dạng dòng.

```java
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

Path xml = Path.of("settings.xml");
Properties properties = new Properties();
properties.setProperty("greeting", "Tiếng Việt 🌍");

// Ghi XML với UTF-8 rõ ràng.
try (OutputStream output = Files.newOutputStream(xml)) {
    properties.storeToXML(output, "Settings", StandardCharsets.UTF_8);
}

// Đọc lại XML Properties.
Properties loaded = new Properties();
try (InputStream input = Files.newInputStream(xml)) {
    loaded.loadFromXML(input);
}
```

Overload `storeToXML(OutputStream, String)` mặc định dùng UTF-8. Overload nhận `Charset` có từ Java 10 và cho phép chỉ rõ encoding. `loadFromXML(InputStream)` phải hỗ trợ UTF-8 và UTF-16 theo hợp đồng API.

Một khác biệt về vòng đời: `loadFromXML(InputStream)` **đóng** input stream sau khi đọc; `load(InputStream)` thì để stream mở. Hãy đọc Javadoc của đúng phương thức trước khi quyết định ai sở hữu tài nguyên.

## 12. Những lỗi thường gặp khi đọc và ghi Properties

### Lỗi 1: File UTF-8 nhưng dùng load(InputStream)

Kết quả tiếng Việt bị biến thành dạng `Tiáº¿ng Viá»‡t` hoặc tương tự. Nguyên nhân là byte UTF-8 được diễn giải thành ký tự Latin-1. Sửa bằng `Files.newBufferedReader(path, UTF_8)` rồi `load(Reader)` nếu định dạng file thực sự là UTF-8 trực tiếp.

### Lỗi 2: File ISO-8859-1 nhưng dùng Reader UTF-8

Đây là lỗi ngược lại. Nếu file được tạo bởi `store(OutputStream, ...)`, hãy dùng `load(InputStream)`. Dùng Reader UTF-8 có thể gây ký tự sai hoặc lỗi decode với byte không hợp lệ theo UTF-8, đặc biệt trong comment chứa ký tự Latin-1.

### Lỗi 3: Nghĩ store(OutputStream) ghi UTF-8 vì JDK 18+

Sai. `store(OutputStream, ...)` có hợp đồng ISO-8859-1. Muốn file properties UTF-8 trực tiếp, dùng `store(Writer, ...)` với Writer được cấu hình UTF-8.

### Lỗi 4: Tự escape Unicode trước khi gọi store

Nếu code tự đổi `Tiếng Việt` thành `Ti\u1EBFng Vi\u1EC7t`, sau đó `store(OutputStream, ...)` lại escape dấu gạch chéo ngược, file có thể lưu thành chuỗi chứa escape literal thay vì ký tự dự kiến. Hãy để `store` thực hiện escape theo hợp đồng của nó; chỉ tự escape khi định dạng hoặc yêu cầu nghiệp vụ đòi hỏi.

### Lỗi 5: Quên đóng stream

`load(InputStream)` và `store(OutputStream, ...)` không đóng stream. Dùng try-with-resources ở nơi mở stream. `store` có flush nhưng flush không thay thế close.

### Lỗi 6: Dùng put thay cho setProperty

`Properties` kế thừa `Hashtable<Object,Object>`, nên về mặt kế thừa có thể gọi `put`. Nhưng API khuyến nghị `setProperty(String, String)` để bảo đảm key/value là chuỗi. Nếu object chứa key hoặc value không phải `String`, `store` có thể ném `ClassCastException`.

## 13. Quản lý key/value, defaults và nội dung được ghi

`Properties` lưu cặp key/value dạng chuỗi. Dùng API phù hợp:

```java
Properties properties = new Properties();
properties.setProperty("server.host", "localhost");
properties.setProperty("server.port", "8080");

String host = properties.getProperty("server.host");
String port = properties.getProperty("server.port", "8080");
```

`getProperty(key, defaultValue)` trả giá trị mặc định nếu key không có trong properties hiện tại hoặc danh sách defaults.

Có thể tạo `Properties` với một bảng defaults:

```java
Properties defaults = new Properties();
defaults.setProperty("server.host", "localhost");
defaults.setProperty("server.port", "8080");

Properties application = new Properties(defaults);
application.setProperty("server.port", "9090");

String host = application.getProperty("server.host"); // localhost
String port = application.getProperty("server.port"); // 9090
```

`getProperty` tìm trong bảng hiện tại rồi lần lượt tìm defaults. Tuy nhiên, `store(OutputStream, ...)` và `store(Writer, ...)` chỉ ghi các entry trong bảng hiện tại; giá trị kế thừa từ defaults không được ghi ra file.

`stringPropertyNames()` trả về tập key có key/value là `String`, bao gồm cả key từ defaults nếu không bị ghi đè. Tập trả về không được backing trực tiếp bởi `Properties`.

## 14. save() đã deprecated: dùng store() để không nuốt lỗi I/O

Không dùng `Properties.save(OutputStream, String)` trong code mới. Phương thức này đã deprecated vì nó gọi `store(...)` nhưng **nuốt `IOException`** thay vì báo lỗi cho caller.

Dùng:

```java
try (OutputStream output = Files.newOutputStream(path)) {
    properties.store(output, "Application settings");
}
```

`store` khai báo `IOException`, giúp ứng dụng nhận biết khi không thể ghi file. Đây là khác biệt quan trọng khi lưu cấu hình quan trọng hoặc dữ liệu cần bảo toàn.

## 15. Kiểm thử round-trip và byte thực tế

Một kiểm thử hữu ích là ghi properties ra byte theo hợp đồng ISO-8859-1, sau đó đọc lại bằng `load(InputStream)` và so sánh giá trị:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

Properties original = new Properties();
original.setProperty("language", "vi");
original.setProperty("greeting", "Tiếng Việt 🌍");
original.setProperty("currency", "€");

ByteArrayOutputStream bytes = new ByteArrayOutputStream();
original.store(bytes, "Round-trip test");

// store(OutputStream) dùng ISO-8859-1; toString chỉ để quan sát byte.
String serialized = bytes.toString(StandardCharsets.ISO_8859_1);
System.out.println(serialized);

Properties restored = new Properties();
try (ByteArrayInputStream input =
        new ByteArrayInputStream(bytes.toByteArray())) {
    restored.load(input);
}

if (!original.equals(restored)) {
    throw new AssertionError("Properties round-trip failed");
}
```

`ByteArrayOutputStream.toString(ISO_8859_1)` ở đây chỉ giúp quan sát byte đã ghi dưới dạng Latin-1. Nó không thay đổi hợp đồng của `Properties`. Giá trị tiếng Việt và ký hiệu euro được lưu bằng Unicode escape, rồi được khôi phục khi `load(InputStream)` phân tích.

### Kiểm tra file UTF-8 trực tiếp

Nếu định dạng của ứng dụng là UTF-8 với Unicode trực tiếp, kiểm thử bằng cặp Reader/Writer:

```java
import java.io.Reader;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

Path file = Files.createTempFile("properties-utf8-", ".properties");

try {
    Properties original = new Properties();
    original.setProperty("greeting", "Tiếng Việt 🌍");

    try (Writer writer = Files.newBufferedWriter(file, StandardCharsets.UTF_8)) {
        original.store(writer, "UTF-8");
    }

    Properties restored = new Properties();
    try (Reader reader = Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
        restored.load(reader);
    }

    if (!"Tiếng Việt 🌍".equals(restored.getProperty("greeting"))) {
        throw new AssertionError("UTF-8 Reader/Writer round-trip failed");
    }
} finally {
    Files.deleteIfExists(file);
}
```

Hai bài kiểm thử xác nhận hai định dạng khác nhau. Không dùng lẫn hai cặp API trong cùng một file nếu chưa có kế hoạch chuyển đổi encoding.

## 16. Những nhận định dễ nhầm

- **“Java 18 đổi Properties sang UTF-8.”** Sai. `load(InputStream)` và `store(OutputStream, ...)` vẫn dùng ISO-8859-1 theo hợp đồng API.
- **“Không truyền charset thì Properties tự dùng Charset.defaultCharset().”** Sai. Hai overload byte này quy định ISO-8859-1.
- **“Muốn đọc file UTF-8 phải gọi load(InputStream).”** Sai. Dùng Reader đã decode UTF-8 rồi gọi `load(Reader)`.
- **“store(OutputStream) ghi Unicode trực tiếp dưới UTF-8.”** Sai. Nó ghi byte ISO-8859-1 và dùng Unicode escape cho ký tự cần escape trong key/value.
- **“store(OutputStream) tự đóng stream.”** Sai. Nó flush nhưng để stream mở.
- **“load(InputStream) tự đóng stream.”** Sai. Stream vẫn mở sau khi phương thức trả về.
- **“Mọi escape trong file properties giống Java string literal.”** Sai. Cú pháp có khác biệt, bao gồm `\b`, escape không hợp lệ và Unicode escape.
- **“store ghi cả các giá trị kế thừa từ defaults.”** Sai. Chỉ các entry trong bảng hiện tại được ghi.
- **“save() tương đương store() nhưng tên ngắn hơn.”** Sai. `save()` deprecated và nuốt lỗi `IOException`; dùng `store()`.

## 17. Tài liệu tham khảo chính thức

- [Properties — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Properties.html): hợp đồng `load(InputStream)`, `store(OutputStream)`, Reader/Writer, cú pháp properties, Unicode escape và vòng đời stream.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): default charset từ Java 18 và phạm vi tác động.
- [StandardCharsets — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/StandardCharsets.html): các charset chuẩn như UTF-8 và ISO-8859-1.
- [Files — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html): `newBufferedReader`, `newBufferedWriter` và lựa chọn charset rõ ràng.

