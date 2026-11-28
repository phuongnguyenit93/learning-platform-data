# Properties.load(Reader) và store(Writer): kiểm soát charset qua Reader và Writer

## 1. Đọc và ghi Properties qua luồng ký tự

`java.util.Properties` lưu các cặp khóa–giá trị dưới dạng `String`. Khi làm việc với file, ứng dụng cần chuyển đổi giữa byte trên đĩa và ký tự trong Java. Cặp API `load(Reader)` và `store(Writer, String)` cho phép kiểm soát bước chuyển đổi này thông qua `Reader` và `Writer` mà ứng dụng truyền vào.

- `Reader` đã giải mã byte thành ký tự theo charset được chọn khi tạo reader.
- `Properties.load(Reader)` phân tích các ký tự đó theo cú pháp file properties.
- `Properties.store(Writer, String)` ghi cú pháp properties ra luồng ký tự.
- `Writer` mã hóa ký tự thành byte theo charset được chọn khi tạo writer.

```text
Đọc file UTF-8
  File bytes
      |
      | Reader / UTF-8 decoder
      v
  Ký tự Unicode
      |
      | Properties.load(Reader)
      v
  Properties (String -> String)

Ghi file UTF-8
  Properties
      |
      | Properties.store(Writer, comments)
      v
  Ký tự properties
      |
      | Writer / UTF-8 encoder
      v
  File bytes UTF-8
```

Điểm quan trọng: `Properties` không tự phát hiện charset và cũng không gọi `Charset.defaultCharset()` khi nhận `Reader` hoặc `Writer`. Charset đã được quyết định ở tầng tạo Reader/Writer. Nhờ đó, ứng dụng có thể đọc và ghi file `.properties` bằng UTF-8 trực tiếp, kể cả khi cấu hình default charset của JVM khác.

## 2. Hai overload làm việc với ký tự

Các phương thức chính:

```java
void load(Reader reader) throws IOException
void store(Writer writer, String comments) throws IOException
```

| Phương thức | Đầu vào/đầu ra | Trách nhiệm charset |
| --- | --- | --- |
| `load(Reader)` | Ký tự từ `Reader` | Reader đã decode; Properties chỉ phân tích ký tự |
| `store(Writer, comments)` | Ký tự ghi vào `Writer` | Writer sẽ encode theo charset đã cấu hình |

Các overload Reader/Writer có từ Java 6 và vẫn là API hiện hành trên JDK hiện đại. Chúng phù hợp khi ứng dụng cần làm việc với file UTF-8 hoặc một charset khác theo hợp đồng riêng.

Không có tham số `Charset` trong hai phương thức này vì chúng nhận đối tượng ký tự. Nếu muốn chọn UTF-8, hãy chọn ở nơi tạo Reader/Writer:

```java
Reader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8);
Writer writer = Files.newBufferedWriter(path, StandardCharsets.UTF_8);
```

Hoặc với luồng byte bất kỳ:

```java
Reader reader = new InputStreamReader(input, StandardCharsets.UTF_8);
Writer writer = new OutputStreamWriter(output, StandardCharsets.UTF_8);
```

## 3. Phân biệt với load(InputStream) và store(OutputStream)

Cặp API byte vẫn được hỗ trợ, nhưng có hợp đồng encoding riêng: `load(InputStream)` và `store(OutputStream, String)` dùng ISO-8859-1. Cặp Reader/Writer thì làm việc trên ký tự và để Reader/Writer quyết định encoding.

| API | Đơn vị nhận/gửi | Encoding |
| --- | --- | --- |
| `load(InputStream)` | Byte | ISO-8859-1 theo hợp đồng API |
| `store(OutputStream, comments)` | Byte | ISO-8859-1; ký tự ngoài vùng quy định được ghi bằng Unicode escape |
| `load(Reader)` | Ký tự | Theo charset mà Reader đã dùng để decode |
| `store(Writer, comments)` | Ký tự | Theo charset mà Writer dùng để encode |

JEP 400 đặt UTF-8 làm default charset thông thường của Java SE từ Java 18. Thay đổi đó không làm `load(InputStream)` chuyển sang UTF-8, cũng không khiến `load(Reader)` tự chọn UTF-8. Với Reader/Writer, charset được quyết định ở tầng tạo đối tượng; với cặp InputStream/OutputStream của Properties, ISO-8859-1 vẫn là hợp đồng.

Ví dụ, nếu file `.properties` chứa Unicode trực tiếp và được lưu bằng UTF-8, đọc bằng `load(InputStream)` sẽ diễn giải từng byte theo Latin-1 và có thể tạo mojibake. Hãy tạo Reader UTF-8 rồi gọi `load(Reader)`.

## 4. Đọc file UTF-8 bằng Files.newBufferedReader

Đây là cách thường dùng khi file có đường dẫn:

```java
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

Path configPath = Path.of("application.properties");
Properties properties = new Properties();

try (Reader reader =
        Files.newBufferedReader(configPath, StandardCharsets.UTF_8)) {
    properties.load(reader);
}

String greeting = properties.getProperty("greeting", "Hello");
System.out.println(greeting);
```

`Files.newBufferedReader(path, charset)` tạo Reader đã giải mã theo charset chỉ định. `Properties.load(reader)` nhận ký tự Unicode và phân tích nội dung properties. Ví dụ này không phụ thuộc default charset của JVM.

`Files.newBufferedReader(path)` không truyền charset cũng có hợp đồng UTF-8 riêng của Files API. Dù vậy, truyền `StandardCharsets.UTF_8` tường minh giúp người đọc code nhận ra định dạng file ngay tại nơi mở.

### 4.1. Đọc từ InputStream với InputStreamReader

Nếu nguồn không phải file, ví dụ dữ liệu nhận từ socket hoặc resource, có thể tạo Reader trực tiếp:

```java
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

Properties properties = new Properties();

try (InputStreamReader reader =
        new InputStreamReader(obtainInputStream(), StandardCharsets.UTF_8)) {
    properties.load(reader);
}
```

`InputStreamReader` chịu trách nhiệm decode byte UTF-8. `Properties` không biết nguồn ban đầu là file, socket hay resource; nó chỉ nhận ký tự từ Reader.

Nếu Reader đã được truyền từ tầng khác, không tạo thêm `InputStreamReader` bọc lại. Chọn một nơi chịu trách nhiệm decode và thống nhất ai sở hữu, ai đóng reader.

## 5. Ghi file UTF-8 bằng Files.newBufferedWriter

Để ghi Unicode trực tiếp vào file UTF-8, tạo Writer với charset tương ứng:

```java
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

Properties properties = new Properties();
properties.setProperty("language", "vi");
properties.setProperty("greeting", "Tiếng Việt 🌍");
properties.setProperty("currency", "€");

Path configPath = Path.of("application.properties");

try (Writer writer =
        Files.newBufferedWriter(configPath, StandardCharsets.UTF_8)) {
    properties.store(writer, "Application settings");
}
```

`Properties.store(Writer, comments)` ghi các ký tự properties ra Writer. Writer UTF-8 chuyển những ký tự đó thành byte UTF-8. Giá trị tiếng Việt và emoji có thể được ghi trực tiếp, không cần chuyển toàn bộ thành `\uXXXX`.

`Files.newBufferedWriter(path, charset)` khi không truyền `OpenOption` sẽ tạo file nếu chưa tồn tại và truncate file cũ trước khi ghi. Nếu cần giữ nội dung cũ hoặc append, phải chỉ định options phù hợp khi mở Writer.

### 5.1. Ghi qua OutputStreamWriter

Khi ứng dụng đã có `OutputStream`, có thể tạo Writer như sau:

```java
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

Properties properties = new Properties();
properties.setProperty("message", "Đã sẵn sàng");

try (OutputStreamWriter writer =
        new OutputStreamWriter(obtainOutputStream(), StandardCharsets.UTF_8)) {
    properties.store(writer, "UTF-8 properties");
}
```

Charset thuộc về `OutputStreamWriter`. `store(Writer, ...)` chỉ ghi ký tự và không tự thêm một lớp encoding khác.

## 6. Unicode trực tiếp và Unicode escape trong file properties

Định dạng properties hỗ trợ escape để biểu diễn các ký tự đặc biệt. Khi dùng Reader/Writer UTF-8, có thể lưu ký tự Unicode trực tiếp:

```properties
language=vi
greeting=Tiếng Việt
currency=€
planet=🌍
```

Sau khi đọc bằng Reader UTF-8 và gọi `load(Reader)`, các giá trị được khôi phục thành Unicode tương ứng.

Định dạng cũng hỗ trợ Unicode escape dạng `\uXXXX`:

```properties
language=vi
greeting=Ti\u1EBFng Vi\u1EC7t
currency=\u20AC
```

`load(Reader)` vẫn xử lý Unicode escape sau khi Reader đã decode byte. Vì vậy, hai cách viết sau có thể tạo cùng một giá trị:

- Ký tự Unicode trực tiếp được Reader UTF-8 giải mã.
- Chuỗi escape `\uXXXX` được parser Properties diễn giải.

Không nhầm Unicode escape trong file properties với escape trong Java source. Cú pháp properties chỉ cho phép một chữ `u` và đúng bốn chữ số hex cho mỗi đơn vị mã.

### 6.1. Ký tự ngoài BMP

Ký tự như `🌍` có code point lớn hơn `U+FFFF`, được biểu diễn trong UTF-16 bằng cặp surrogate. Khi dùng UTF-8 Reader/Writer, ký tự có thể được truyền trực tiếp. Nếu biểu diễn bằng Unicode escape, cần hai escape tương ứng với hai đơn vị mã surrogate.

Không nên tự viết thuật toán escape theo từng `char` nếu không hiểu cặp surrogate. Để lưu Unicode trực tiếp, UTF-8 Reader/Writer thường là cách dễ đọc và ít lỗi hơn.

## 7. Reader/Writer không bỏ qua cú pháp của Properties

Việc chuyển sang Reader/Writer chỉ thay đổi tầng charset; cú pháp properties vẫn được áp dụng. Các quy tắc chính:

- Dòng trống bị bỏ qua.
- Dòng comment bắt đầu bằng `#` hoặc `!` ở ký tự không phải whitespace đầu tiên.
- Key kết thúc ở dấu `=`, `:`, hoặc whitespace chưa được escape đầu tiên.
- Sau key, whitespace được bỏ qua; dấu `=` hoặc `:` tiếp theo cũng được bỏ qua.
- Phần còn lại của dòng là value; nếu không còn nội dung, value là chuỗi rỗng.
- Một logical line có thể kéo dài qua nhiều natural line bằng dấu `\` ở cuối dòng với số lượng dấu gạch chéo liên tiếp lẻ.

Ví dụ, ba dòng sau cùng mô tả một cặp key/value:

```properties
Truth = Beauty
Truth:Beauty
Truth                    :Beauty
```

Kết quả là key `Truth`, value `Beauty`.

### 7.1. Nối dòng

```properties
message=Java Properties có thể \
        nối nội dung qua nhiều dòng \
        trong cùng một giá trị
```

Dấu `\` cuối dòng, line terminator và whitespace đầu dòng tiếp theo bị loại bỏ khi nối. Nếu cần một dấu cách trong giá trị, đặt dấu cách trước dấu `\`:

```properties
message=Java Properties có thể \
        nối nội dung
```

Giá trị sau khi load có một dấu cách giữa `thể` và `nối`.

### 7.2. Escape các ký tự đặc biệt

Các escape thường gặp:

| Escape | Giá trị sau khi load |
| --- | --- |
| `\t` | Tab |
| `\n` | Line feed |
| `\r` | Carriage return |
| `\f` | Form feed |
| `\\` | Dấu gạch chéo ngược |
| `\uXXXX` | Đơn vị mã UTF-16 |

Dấu `=`, `:`, `#`, `!` và khoảng trắng trong key/value có quy tắc riêng. `store(Writer, ...)` tự escape các ký tự cần thiết để dữ liệu có thể được đọc lại.

Lưu ý, cú pháp Properties không hoàn toàn giống Java string literal: `\b` không đại diện backspace; octal escape không được nhận diện; dấu gạch chéo ngược trước một escape không hợp lệ có thể bị bỏ đi thay vì gây lỗi.

## 8. Những gì store(Writer) ghi ra và cách nó escape

`store(Writer, comments)` ghi định dạng phù hợp để đọc lại bằng `load(Reader)`. Nó ghi một entry trên mỗi dòng, gồm key, dấu `=`, rồi value.

Một số quy tắc escape cần nhớ:

- Tất cả dấu cách trong key được ghi với dấu `\` đứng trước.
- Dấu cách ở đầu value được escape; dấu cách ở giữa hoặc cuối value không cần escape theo quy tắc này.
- Các ký tự `#`, `!`, `=`, `:` trong key/value được escape bằng `\`.
- Ký tự Unicode không bị ép thành `\uXXXX` chỉ vì nó nằm ngoài ASCII; Writer bên dưới nhận ký tự và quyết định cách mã hóa.
- Comment không phải entry; comment được ghi dưới dạng dòng bắt đầu bằng `#`.

Ví dụ với Writer UTF-8:

```java
Properties properties = new Properties();
properties.setProperty("tên hiển thị", "  Nguyễn An");
properties.setProperty("endpoint", "https://example.test/a=b");
properties.setProperty("greeting", "Xin chào");

try (Writer writer =
        Files.newBufferedWriter(Path.of("settings.properties"),
                StandardCharsets.UTF_8)) {
    properties.store(writer, "Cấu hình tiếng Việt");
}
```

File đầu ra là văn bản UTF-8. Dấu cách trong key, dấu cách đầu value và dấu `=` trong value được escape theo cú pháp properties; chữ tiếng Việt được ghi trực tiếp theo encoding của Writer.

`store(Writer, ...)` cũng ghi comment ngày giờ mặc định ở đầu file. Vì vậy, nội dung file được sinh ở hai thời điểm có thể khác nhau ở dòng comment dù các entry giống nhau. Khi kiểm thử, nên so sánh `Properties` sau khi load hoặc bỏ qua comment thay vì giả định toàn bộ file byte luôn giống nhau.

## 9. Vòng đời Reader và Writer

`Properties.load(Reader)` và `Properties.store(Writer, comments)` **không đóng** Reader/Writer được truyền vào.

- `load(Reader)` đọc dữ liệu nhưng để Reader mở.
- `store(Writer, comments)` flush Writer sau khi ghi xong nhưng để Writer mở.
- Caller chịu trách nhiệm đóng tài nguyên mà mình đã mở.

Mẫu thông thường:

```java
try (Reader reader =
        Files.newBufferedReader(inputPath, StandardCharsets.UTF_8)) {
    properties.load(reader);
}

try (Writer writer =
        Files.newBufferedWriter(outputPath, StandardCharsets.UTF_8)) {
    properties.store(writer, "Application settings");
}
```

Không cần gọi `reader.close()` hoặc `writer.close()` thêm lần nữa bên trong khối. Try-with-resources đảm bảo tài nguyên được đóng khi thoát khối, kể cả khi có ngoại lệ.

Nếu Reader/Writer được truyền vào từ một tầng khác, hãy thống nhất quyền sở hữu trước khi đóng. Đóng wrapper như `BufferedReader` hoặc `BufferedWriter` cũng đóng tài nguyên bên dưới.

### 9.1. Flush không thay thế close

`store(Writer, ...)` flush sau khi ghi các entry. Flush đẩy dữ liệu đang đệm xuống tầng Writer bên dưới, nhưng không giải phóng file handle và không bảo đảm dữ liệu đã được đồng bộ vật lý xuống thiết bị lưu trữ.

`close()` mới hoàn tất vòng đời Writer và giải phóng tài nguyên. Khi dùng try-with-resources, không cần gọi flush ngay trước close trong trường hợp thông thường.

## 10. Xử lý lỗi khi đọc

`load(Reader)` có thể ném:

| Ngoại lệ | Nguyên nhân |
| --- | --- |
| `IOException` | Reader gặp lỗi khi đọc dữ liệu |
| `IllegalArgumentException` | Có Unicode escape sai định dạng |
| `NullPointerException` | Reader được truyền vào là `null` |

Ví dụ escape sai:

```properties
greeting=Ti\u12G4ng
```

Chuỗi `\u` phải theo sau bởi đúng bốn chữ số hex. Nếu không, `load(Reader)` ném `IllegalArgumentException`.

Lỗi charset có thể xuất hiện trước khi parser Properties xử lý ký tự, ở tầng Reader. Ví dụ Reader UTF-8 với decoder nghiêm ngặt sẽ ném `MalformedInputException` khi gặp byte UTF-8 sai. Đây là lỗi giải mã byte, khác với `IllegalArgumentException` do Unicode escape trong nội dung properties.

### 10.1. Decode UTF-8 nghiêm ngặt

Nếu dữ liệu phải là UTF-8 hợp lệ, cấu hình `CharsetDecoder` để báo lỗi:

```java
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

var decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

Properties properties = new Properties();

try (Reader reader = new InputStreamReader(
        Files.newInputStream(Path.of("incoming.properties")), decoder)) {
    properties.load(reader);
}
```

Với cấu hình `REPORT`, byte malformed hoặc unmappable tạo ngoại lệ I/O khi Reader đọc đến vùng lỗi. Ứng dụng có thể từ chối file và báo lỗi cho nguồn tạo dữ liệu. Không đổi charset tùy tiện chỉ để làm cho nội dung đọc được.

## 11. Xử lý lỗi khi ghi

`store(Writer, comments)` có thể ném `IOException` nếu ghi ra Writer thất bại. Nó cũng có thể ném `ClassCastException` nếu đối tượng `Properties` chứa key hoặc value không phải `String`, và `NullPointerException` nếu Writer là `null`.

`Properties` kế thừa `Hashtable<Object,Object>`, vì vậy về mặt kế thừa vẫn có thể gọi `put(Object,Object)`. Tuy nhiên, nên dùng `setProperty(String, String)` để giữ đúng kiểu dữ liệu:

```java
Properties properties = new Properties();
properties.setProperty("server.port", "8080");
properties.setProperty("server.host", "localhost");
```

Tránh:

```java
properties.put("server.port", 8080);
```

Giá trị `Integer` không phải `String`; thao tác `store` có thể thất bại với `ClassCastException`.

### 11.1. Writer có thể không biểu diễn được ký tự

`Properties.store(Writer, ...)` không tự chọn charset. Nếu Writer bên dưới dùng charset giới hạn như US-ASCII, chính encoder của Writer quyết định cách xử lý ký tự không thể biểu diễn. Với Writer thông thường, encoder có thể thay thế ký tự theo chính sách mặc định; nếu cần từ chối mất dữ liệu, cấu hình `CharsetEncoder` với `CodingErrorAction.REPORT`.

```java
import java.io.OutputStreamWriter;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

var encoder = StandardCharsets.UTF_8.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try (var writer = new OutputStreamWriter(
        Files.newOutputStream(Path.of("strict.properties")), encoder)) {
    properties.store(writer, "Strict UTF-8");
}
```

UTF-8 có thể biểu diễn các ký tự Unicode hợp lệ, nhưng vẫn có thể cần chính sách `REPORT` nếu ứng dụng muốn phát hiện chuỗi UTF-16 đầu vào chứa surrogate không hợp lệ thay vì thay thế.

## 12. Defaults và những gì được lưu ra file

Một `Properties` có thể tham chiếu một bảng defaults:

```java
Properties defaults = new Properties();
defaults.setProperty("server.host", "localhost");
defaults.setProperty("server.port", "8080");

Properties application = new Properties(defaults);
application.setProperty("server.port", "9090");

String host = application.getProperty("server.host"); // localhost
String port = application.getProperty("server.port"); // 9090
```

`getProperty` tìm trong bảng hiện tại rồi tìm defaults nếu không có key. Nhưng `store(Writer, ...)` chỉ ghi các entry nằm trực tiếp trong bảng hiện tại; các giá trị kế thừa từ defaults không được ghi.

Nếu muốn tạo file cấu hình độc lập chứa cả giá trị mặc định, hãy hợp nhất các giá trị cần thiết vào đối tượng Properties sẽ lưu trước khi gọi `store`.

## 13. XML Properties là định dạng khác

Nếu hệ thống cần định dạng XML, `storeToXML` và `loadFromXML` là cặp API riêng. Chúng không dùng cú pháp dòng của `load(Reader)`/`store(Writer)`.

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

try (OutputStream output = Files.newOutputStream(xml)) {
    properties.storeToXML(output, "Settings", StandardCharsets.UTF_8);
}

Properties loaded = new Properties();
try (InputStream input = Files.newInputStream(xml)) {
    loaded.loadFromXML(input);
}
```

XML Properties là lựa chọn khi định dạng XML được yêu cầu bởi hệ thống tích hợp. Với file `.properties` dạng dòng, tiếp tục dùng cặp Reader/Writer nếu muốn tự kiểm soát charset văn bản.

## 14. Ví dụ hoàn chỉnh: ghi UTF-8 rồi đọc lại

Ví dụ sau tạo file tạm, lưu Unicode trực tiếp qua Writer UTF-8, đọc lại qua Reader UTF-8 và kiểm tra các giá trị:

```java
import java.io.Reader;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

public class PropertiesReaderWriterDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("properties-utf8-", ".properties");

        try {
            Properties original = new Properties();
            original.setProperty("language", "vi");
            original.setProperty("greeting", "Tiếng Việt 🌍");
            original.setProperty("currency", "€");
            original.setProperty("server.url", "https://example.test/a=b");

            // Writer quyết định byte đầu ra là UTF-8.
            try (Writer writer =
                    Files.newBufferedWriter(file, StandardCharsets.UTF_8)) {
                original.store(writer, "Cấu hình UTF-8");
            }

            // Reader giải mã byte UTF-8 thành ký tự.
            Properties restored = new Properties();
            try (Reader reader =
                    Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
                restored.load(reader);
            }

            if (!original.equals(restored)) {
                throw new AssertionError("Properties round-trip failed");
            }

            System.out.println(restored.getProperty("greeting"));
            System.out.println("Round-trip OK");
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Trong ví dụ này, `store(Writer, ...)` ghi Unicode qua Writer UTF-8; `load(Reader)` nhận ký tự đã decode. Dấu `=` trong value được escape để không bị hiểu nhầm là dấu phân cách key/value. Sau khi load, giá trị ban đầu được khôi phục.

## 15. Kiểm thử tách biệt charset và cú pháp

Để kiểm tra đúng lớp nguyên nhân, nên có các ca riêng:

| Ca kiểm thử | Điều cần xác nhận |
| --- | --- |
| UTF-8 có tiếng Việt và emoji | Reader decode đúng, Properties nhận đúng chuỗi |
| Unicode escape hợp lệ `\uXXXX` | Parser chuyển escape thành ký tự |
| Unicode escape thiếu hoặc sai hex | `IllegalArgumentException` |
| Byte UTF-8 malformed với decoder `REPORT` | Reader báo lỗi decode dưới dạng I/O |
| Writer UTF-8 | Byte đầu ra khớp UTF-8 |
| Writer charset giới hạn | Chính sách encoder với ký tự không biểu diễn được |
| Key/value chứa `=`, `:`, `#`, `!` | `store` escape để load lại đúng |
| Properties có defaults | `store` chỉ ghi entry hiện tại |
| Reader/Writer được truyền vào | API không đóng tài nguyên của caller |

Một bài test round-trip không đủ để chứng minh encoding byte nếu cả ghi và đọc đều dùng cùng một charset sai. Hãy kiểm tra byte đầu ra hoặc mở file bằng một Reader có charset độc lập đã được xác định theo hợp đồng.

## 16. Những nhận định dễ nhầm

- **“`Properties.load(Reader)` tự chọn UTF-8.”** Sai. Reader đã quyết định cách decode byte; `load(Reader)` chỉ nhận ký tự.
- **“JEP 400 làm thay đổi charset của mọi API Properties.”** Sai. JEP 400 thay default charset thông thường; Reader/Writer dùng charset đã cấu hình, còn cặp InputStream/OutputStream của Properties có hợp đồng ISO-8859-1 riêng.
- **“`store(Writer)` chuyển Unicode thành `\uXXXX` giống `store(OutputStream)`.”** Sai. Writer nhận ký tự; ký tự Unicode được chuyển qua Writer theo charset của Writer. Các ký tự cú pháp và khoảng trắng cần thiết vẫn được escape.
- **“Có thể truyền Charset trực tiếp vào `load(Reader)`.”** Sai. Chọn charset khi tạo Reader.
- **“`store(Writer)` đóng Writer sau khi ghi.”** Sai. Nó flush nhưng để Writer mở; caller chịu trách nhiệm close.
- **“`load(Reader)` đóng Reader khi đọc hết.”** Sai. Reader vẫn mở sau khi phương thức trả về.
- **“`store` ghi cả defaults.”** Sai. Chỉ entry trong bảng hiện tại được ghi.
- **“Mọi lỗi đọc đều là lỗi charset.”** Sai. Có thể là `IOException` từ nguồn, `IllegalArgumentException` do Unicode escape hoặc lỗi logic ở tầng ứng dụng.
- **“Dùng `put` thay `setProperty` không có khác biệt.”** Sai. `put` có thể đưa key/value không phải String vào bảng và làm `store` thất bại.

## 17. Tài liệu tham khảo chính thức

- [Properties — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Properties.html): hợp đồng `load(Reader)`, `store(Writer, String)`, cú pháp properties, escape, defaults và vòng đời Reader/Writer.
- [Reader — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/Reader.html): abstraction luồng ký tự.
- [Writer — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/Writer.html): abstraction ghi ký tự, flush và close.
- [InputStreamReader — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/InputStreamReader.html): chuyển byte thành ký tự bằng charset hoặc decoder.
- [OutputStreamWriter — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/OutputStreamWriter.html): chuyển ký tự thành byte bằng charset hoặc encoder.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): phạm vi thay đổi default charset từ Java 18.

