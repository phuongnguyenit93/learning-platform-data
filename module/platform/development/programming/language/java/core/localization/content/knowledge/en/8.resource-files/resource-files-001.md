# Cú pháp .properties: khóa, giá trị, chú thích và dòng tiếp nối trong Java

## 1. Tệp .properties là gì?

Tệp `.properties` chứa các cặp **key–value** dạng văn bản. Trong Java, nó thường được dùng cho cấu hình ứng dụng (qua `java.util.Properties`) và bản địa hóa (qua `ResourceBundle` / `PropertyResourceBundle`). Ví dụ:

```properties
# Config
app.name=Learning Platform
timeout.seconds=30
welcome=Xin chào!
```

Dù `timeout.seconds` trông giống số, giá trị mà `Properties.getProperty("timeout.seconds")` trả về vẫn là chuỗi `"30"`. Tệp không tự có các kiểu dữ liệu JSON, không có object lồng nhau và không tự mở rộng placeholder. Dấu chấm trong `app.name` chỉ thuộc tên khóa. Một framework có thể hỗ trợ cú pháp riêng bên ngoài hợp đồng parser chuẩn của Java; bài này tập trung vào **cú pháp .properties chuẩn**.

Một key có thể xuất hiện trong tài nguyên `Messages_vi.properties` rồi được gọi bằng `bundle.getString("key")`. Cú pháp bên trong vẫn giống nhau; khác biệt quan trọng nằm ở **API đọc và cách giải mã encoding**, được làm rõ ở cuối bài.

## 2. Cách viết khóa–giá trị và dấu phân cách

Một cặp thuộc tính có một **logical line** với khóa và giá trị. Ba cách phân cách thường gặp đều hợp lệ:

```properties
app.name=Learning Platform
app.version:1.0
app.owner Development Team
app.mode = production
```

Dấu phân cách đầu tiên **không được escape** có thể là `=`, `:` hoặc whitespace. Parser bỏ qua whitespace đầu dòng, xác định khóa, sau đó bỏ qua whitespace và dấu phân cách không bắt buộc trước khi đọc value.

| Dòng trong file | Key thực tế | Value thực tế |
|---|---|---|
| `name=Lan` | `name` | `Lan` |
| `name:Lan` | `name` | `Lan` |
| `name Lan` | `name` | `Lan` |
| `name = Lan` | `name` | `Lan` |
| `empty=` | `empty` | Chuỗi rỗng `""` |
| `justKey` | `justKey` | Chuỗi rỗng `""` |
| `a=b=c` | `a` | `b=c` |
| `url=https://example.com?a=b` | `url` | `https://example.com?a=b` |

Dấu `=` hoặc `:` sau khi đã bắt đầu value chỉ là ký tự bình thường. Nên nhất quán dùng kiểu `key=value` để dễ đọc và giảm hiểu nhầm trong review.

### Khóa phân biệt chữ hoa chữ thường

`app.name` và `App.Name` là **hai khóa khác nhau**. Tên khóa như `button.save`, `menu.file`, `error.notFound` thường thuận tiện vì rõ nghĩa và không chứa whitespace. Không nên tự ý đổi chữ hoa/thường khi gọi `getProperty` hoặc `getString`.

### Escape trong key

Nếu key cần chứa khoảng trắng, `=` hoặc `:` thì thêm dấu gạch chéo ngược `\`:

```properties
first\ name=Lan
user\=id=42
server\:port=8080
\#headline=Introduction
\!notice=Attention
```

Các khóa tương ứng: `first name`, `user=id`, `server:port`, `#headline`, `!notice`. Dòng `first name=Lan` **không có escape** sẽ được hiểu là khóa `first` và giá trị `name=Lan` vì khoảng trắng đầu tiên đóng vai trò separator.

## 3. Chú thích: dòng bắt đầu bằng `#` hoặc `!`

Một **natural line** được bỏ qua dưới dạng comment nếu ký tự đầu tiên khác whitespace của nó là `#` hoặc `!`:

```properties
# Comment style one
! Comment style two

   # Indented comment
   ! Also valid
name=Lan
```

Dòng trống hoặc chỉ có whitespace cũng được bỏ qua. Comment **không** phải cặp key-value. Không dùng `//` hay `/* ... */` như comment Java; chúng không mang nghĩa comment trong cú pháp tệp `.properties`.

### Không có inline comment sau value

```properties
# Entire line is comment
message=Hello! # This is part of the value
\#key=value
```

Dòng `message` chứa nguyên chuỗi `Hello! # This is part of the value`. Dòng `\#key=value` tạo key bắt đầu bằng `#` vì dấu này đã được escape. Do đó, không viết `timeout=30 # seconds` rồi nghĩ parser sẽ loại `# seconds`; value thực sự chứa cả phần đó. Đặt ghi chú trên một dòng độc lập.

Comment line không được kéo dài bằng continuation theo cùng cơ chế value. Muốn bình luận nhiều dòng, bắt đầu mỗi dòng với dấu comment riêng.

## 4. Giá trị: khoảng trắng, dấu nháy và ký tự thường

Giá trị có thể chứa dấu `=`, `:`, `#`, `!` sau separator:

```properties
query=https://example.com/search?q=java#results
expression=a=b:c
notice=Save! # Not an inline comment
```

Sau khi xác định đầu value, các ký tự trên không còn làm dấu phân cách hay comment.

### Khoảng trắng đầu và cuối

Whitespace bình thường ngay sau separator bị bỏ qua. Nếu muốn giữ **một khoảng trắng ở đầu value**, hãy escape nó:

```properties
trimmed=    hello
leading=\ hello
```

Kết quả là `trimmed` → `"hello"` và `leading` → `" hello"`. Whitespace cuối logical line không tự bị trim; tránh trailing spaces vô tình vì khó phát hiện khi so sánh cấu hình.

### Dấu nháy không được tự bỏ

```properties
title="Hello"
```

Value ở đây **bao gồm hai dấu nháy kép**, tức `"Hello"` theo cách nhìn của người đọc, chứ không tự thành `Hello`. `.properties` không có cú pháp đặt chuỗi trong dấu nháy theo kiểu JSON. Tương tự, `roles=admin,user` là một chuỗi chứa dấu phẩy; muốn list phải tự định nghĩa cách tách và kiểm tra.

### Value rỗng và key trùng

`empty=` hoặc chỉ `empty` đều tạo value rỗng. Trong cùng một `Properties`, nếu file có hai dòng trùng key, value được đọc sau ghi đè value trước:

```properties
mode=development
mode=production
```

Sau `load`, `mode` có giá trị `production`. Tính năng này hữu ích khi hiểu parser nhưng **không nên cố ý dựa vào duplicate keys** trong một file sản xuất, vì dễ gây sai cấu hình. Không nên mong việc liệt kê các keys qua `Properties` giữ đúng thứ tự dòng trong file.

## 5. Dòng tiếp nối: nhiều natural lines thành một logical line

Khi một dòng kết thúc bằng **số lẻ dấu backslash liên tiếp**, dấu `\` cuối cùng escape line terminator và nối nội dung dòng kế tiếp. Dấu `\` dùng để nối và ký tự xuống dòng **không** được thêm vào value. Whitespace đầu dòng tiếp theo được bỏ qua.

```properties
long.message=Hello, \
    Java \
    developer!
```

Value sau khi parse là `Hello, Java developer!`. Các dấu cách trong kết quả đến từ dấu cách đã được viết **trước** dấu `\` sau `Hello,` và sau `Java`. Parser không tự chèn dấu cách khi nối.

So sánh:

```properties
a=Hello\
    Java
b=Hello \
    Java
```

- `a` → `HelloJava`.
- `b` → `Hello Java`.

### Số dấu `\` cuối dòng quyết định có nối hay không

| Cuối dòng | Diễn giải |
|---|---|
| Một dấu `\` | Dòng tiếp theo được nối |
| Hai dấu `\\` | Thành một backslash literal, **không nối** |
| Ba dấu `\\\` | Một backslash literal và một dấu nối |
| Bốn dấu `\\\\` | Hai backslashes literal, **không nối** |

Khi dòng được nối, ký tự `#` hoặc `!` ở đầu phần tiếp theo được coi như phần của logical line, không phải một comment độc lập. Để tránh nhầm, không đặt comment giữa những phần của một value đang tiếp nối.

### Phân biệt tiếp nối với escape newline

```properties
joined=Hello\
    World
two.lines=Hello\nWorld
```

`joined` → `HelloWorld`, **không có xuống dòng**. `two.lines` là một chuỗi có ký tự LF thật giữa `Hello` và `World`. Đây là hai mục đích khác nhau: viết source trên nhiều dòng cho dễ đọc, hoặc lưu newline bên trong chính value.

## 6. Các escape sequences quan trọng

| Chuỗi viết trong file | Ký tự được đọc | Công dụng |
|---|---|---|
| `\t` | Tab | Chèn tab trong value |
| `\n` | Newline LF | Chèn xuống dòng trong value |
| `\r` | Carriage return CR | Trường hợp đặc biệt |
| `\f` | Form feed | Hiếm dùng |
| `\\` | Một backslash `\` | Đường dẫn Windows, regex |
| `\ ` | Một space | Space trong key hoặc đầu value |
| `\=` | `=` | Dấu bằng trong key |
| `\:` | `:` | Dấu hai chấm trong key |
| `\#` và `\!` | `#` và `!` | Dấu đặc biệt trong key |
| `\u00E9` | `é` | Unicode escape 4 hex digits |

Trong file `.properties`, hai dấu `\\` đại diện cho một dấu `\` thực sự. Hãy phân biệt với Java source: Java string literal cũng có quy tắc escape của riêng nó.

### Backslash không hợp escape đặc biệt

Trong `Properties.load(...)`, nếu backslash đứng trước một ký tự không thuộc escape có ý nghĩa, backslash có thể **bị loại bỏ âm thầm**. Ví dụ `a\qz` được đọc thành `aqz`. Không dựa vào parser để cảnh báo mọi lỗi backslash.

Đường dẫn Windows rất dễ sai:

```properties
bad.path=C:\temp\new
good.path=C:\\temp\\new
```

`bad.path` chứa tab do `\t` và newline do `\n`, không phải đường dẫn như mong muốn. `good.path` đọc thành đường dẫn với các dấu backslash đơn. Khi thích hợp, có thể dùng dấu gạch chéo `/` để giảm lượng escape.

### Unicode escapes

`\uXXXX` cần **đúng bốn chữ số hex** biểu diễn một UTF-16 code unit. Ví dụ:

```properties
cafe=Caf\u00E9
hello=Xin ch\u00E0o
```

Lần lượt thành `Café` và `Xin chào`. Escape Unicode không hợp lệ như `\uZZZZ` có thể ném `IllegalArgumentException` khi nạp. Không dùng cú pháp `\u{1F600}` vì đó không phải Unicode escape của Java `Properties`; ký tự bổ sung ngoài BMP cần hai UTF-16 surrogate escapes nếu dùng cách biểu diễn này.

Với tệp UTF-8 được nạp qua một `Reader` UTF-8, bạn thường có thể ghi tiếng Việt trực tiếp thay vì escape từng ký tự.

## 7. Ví dụ Java 17+ hoàn chỉnh: tạo file, đọc và giải thích stdout

Đặt **hai tệp cùng thư mục** như sau.

### `app.properties`

```properties
# General configuration
! A second comment style

app.name = World Service
app\ title : Localization handbook
greeting: Hello!
long.message = Hello, \
    Java \
    developer!
path = C:\\data\\images
unicode = Caf\u00E9
inline = Value # still value
blank=
duplicate=first
duplicate=final
```

### `PropertiesSyntaxDemo.java`

```java
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

public class PropertiesSyntaxDemo {
    public static void main(String[] args) throws Exception {
        Properties properties = new Properties();

        try (Reader reader = Files.newBufferedReader(
                Path.of("app.properties"), StandardCharsets.UTF_8)) {
            properties.load(reader);
        }

        print(properties, "app.name");
        print(properties, "app title");
        print(properties, "greeting");
        print(properties, "long.message");
        print(properties, "path");
        print(properties, "unicode");
        print(properties, "inline");
        print(properties, "blank");
        print(properties, "duplicate");
    }

    private static void print(Properties properties, String key) {
        System.out.println(key + "=[" + properties.getProperty(key) + "]");
    }
}
```

Chạy:

```bash
javac PropertiesSyntaxDemo.java
java PropertiesSyntaxDemo
```

Output kiểm chứng bằng `Properties.load`:

```text
app.name=[World Service]
app title=[Localization handbook]
greeting=[Hello!]
long.message=[Hello, Java developer!]
path=[C:\data\images]
unicode=[Café]
inline=[Value # still value]
blank=[]
duplicate=[final]
```

Giải thích output:

1. `app\ title` tạo key có khoảng trắng là `app title`.
2. `long.message` nối ba dòng vật lý; giá trị còn khoảng trắng giữa các từ vì dấu cách được viết trước continuation.
3. `path`: hai dấu backslash trong file giải mã thành một trong chuỗi Java.
4. `unicode`: `\u00E9` thành `é`.
5. `inline` chứa nguyên dấu `#` ở giữa value.
6. `blank` là chuỗi rỗng, được in giữa cặp ngoặc vuông.
7. `duplicate` được nạp hai lần; lần sau ghi đè nên là `final`.

Chương trình đọc qua `Files.newBufferedReader` với charset UTF-8 tường minh và tự động đóng bằng `try-with-resources`. Nếu key không có, `properties.getProperty("missing")` trả `null` (trừ khi properties có defaults thích hợp); có thể dùng `getProperty("key", "fallback")` để chỉ định giá trị dự phòng.

## 8. Encoding: Properties và PropertyResourceBundle khác nhau

Đây là khác biệt API thiết yếu, đặc biệt với tiếng Việt.

| API đọc | Quy tắc encoding |
|---|---|
| `Properties.load(InputStream)` | **ISO-8859-1**, theo hợp đồng legacy của `Properties` |
| `Properties.load(Reader)` | Dùng **charset của Reader**; có thể chọn UTF-8 |
| `PropertyResourceBundle(InputStream)` trên JDK 9+ | Ưu tiên **UTF-8**; mặc định thử lại ISO-8859-1 nếu byte sequence không hợp lệ UTF-8 |

Vì thế, không nói đơn giản rằng “mọi file .properties trong Java 17 mặc định dùng UTF-8”. Việc Java 9 chuyển *property resource bundles* sang UTF-8 không làm thay đổi `Properties.load(InputStream)`, vốn vẫn đọc ISO-8859-1.

### Đọc file cấu hình UTF-8 với Properties

```java
try (Reader reader = Files.newBufferedReader(
        Path.of("app.properties"), StandardCharsets.UTF_8)) {
    Properties properties = new Properties();
    properties.load(reader);
}
```

Đây là đoạn code dùng bên trong một phương thức đã có các import liên quan, không phải chương trình độc lập. Nếu dùng `Properties.load(Files.newInputStream(...))` cho file UTF-8 chứa ký tự ngoài ASCII, có thể gặp mojibake vì diễn giải ISO-8859-1.

### Đọc file dịch qua ResourceBundle

`PropertyResourceBundle(InputStream)` trên JDK 17 mặc định ưu tiên UTF-8. Nếu phát hiện `MalformedInputException` hoặc `UnmappableCharacterException` khi giải mã, nó có thể đọc lại bằng ISO-8859-1. JVM property `java.util.PropertyResourceBundle.encoding` có thể buộc `UTF-8` hoặc `ISO-8859-1`, được đánh giá lúc class khởi tạo; thay đổi nó muộn hơn không nhất thiết có tác dụng. `PropertyResourceBundle(Reader)` vẫn phụ thuộc encoding của Reader.

Vì vậy hãy thống nhất quy ước encoding với bộ công cụ build, giữ tệp UTF-8 và kiểm thử bằng đúng JDK/API thực sự đang dùng. Nếu cần phát hiện lỗi encoding sớm, cấu hình strict UTF-8 một cách có chủ đích.

## 9. Tệp .properties dành cho localization với ResourceBundle

Giả sử classpath có hai tệp:

```text
Messages.properties
Messages_vi.properties
```

Nội dung `Messages.properties`:

```properties
welcome=Hello!
button.save=Save
```

Nội dung `Messages_vi.properties`:

```properties
welcome=Xin chào!
button.save=Lưu
```

Đặt các file này **ở gốc classpath** cùng `BundlePropertiesDemo.java` để chạy thủ công:

```java
import java.util.Locale;
import java.util.ResourceBundle;

public class BundlePropertiesDemo {
    public static void main(String[] args) {
        Locale locale = Locale.forLanguageTag("vi-VN");
        ResourceBundle bundle =
                ResourceBundle.getBundle("Messages", locale);

        System.out.println(bundle.getString("welcome"));
        System.out.println(bundle.getString("button.save"));
        System.out.println(bundle.getLocale().toLanguageTag());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 BundlePropertiesDemo.java
java -cp . BundlePropertiesDemo
```

Kết quả:

```text
Xin chào!
Lưu
vi
```

Java yêu cầu `vi-VN` nhưng tìm thấy `Messages_vi.properties`, nên bundle được chọn có locale `vi`. Nếu dự án dùng Maven/Gradle, resource thường nằm dưới `src/main/resources` và được copy vào output classpath khi build; bản thân đường dẫn source chưa đủ để file được runtime tìm thấy.

Cú pháp bên trong `Messages_vi.properties` vẫn là các cặp key/value với comment, escape và continuation như các mục trước. Khi một key không tồn tại trong bundle ngôn ngữ nhưng có ở bundle cha, `ResourceBundle.getString(...)` có thể lấy value ở cha; `bundle.getLocale()` vẫn thể hiện locale của **bundle được chọn**, không nhất thiết là nguồn của mọi key.

## 10. Lỗi thường gặp khi viết .properties

1. **Không escape space hoặc dấu separator trong key.** `first name=Lan` khác `first\ name=Lan`.
2. **Thêm comment cùng dòng key/value.** Phần sau `#` hay `!` trong value không tự bị bỏ.
3. **Dùng `//` làm comment.** Đây không phải comment marker chuẩn.
4. **Cho rằng dấu nháy bao value bị bỏ.** `title="Hello"` chứa cả dấu nháy.
5. **Nhầm continuation với `\n`.** Nối dòng không chèn newline; `\n` chèn LF thực vào value.
6. **Bỏ qua khoảng trắng trước dấu `\` cuối dòng.** Nó có thể quyết định value là `HelloWorld` hay `Hello World`.
7. **Dùng backslash đơn trong đường dẫn Windows.** `\t` và `\n` có ý nghĩa escape.
8. **Tin rằng escape lạ bị báo lỗi.** `\q` có thể thành `q`; phải kiểm tra giá trị thực.
9. **Cho rằng `Properties.load(InputStream)` mặc định UTF-8 từ Java 9.** Hợp đồng của nó vẫn là ISO-8859-1.
10. **Không phân biệt file cấu hình với file ResourceBundle.** Cùng cú pháp nhưng có quy tắc charset và fallback khác nhau theo API.
11. **Để duplicate key không chủ ý.** Value ở lần xuất hiện sau ghi đè trước.
12. **Đoán thứ tự key sau khi load.** `Properties` không bảo đảm liệt kê theo thứ tự dòng gốc.
13. **Cho rằng giá trị được parse thành số/boolean.** Hãy chuyển kiểu, validate và xử lý lỗi riêng.
14. **Dùng `store` để “định dạng lại mà giữ nguyên file”.** `Properties.store` có thể thêm timestamp/comment, viết lại escaping và thứ tự; không bảo tồn comment/layout gốc.
15. **Đặt tệp dịch sai classpath hoặc tên file.** `ResourceBundle.getBundle("Messages", ...)` cần tài nguyên tương ứng ở vị trí có thể tải.

## 11. Tự kiểm tra kiến thức

- `x=y=z` → key **`x`**, value **`y=z`**.
- `user\ name=Lan` → key **`user name`**, value **`Lan`**.
- `message=Hello #note` → value **`Hello #note`**.
- `a=Hello\` rồi nối dòng `World` → value **`HelloWorld`**.
- `a=Hello\nWorld` → value có ký tự newline giữa hai từ.
- `path=C:\\tools` → value có một dấu backslash trước `tools`.
- `name=first` và sau đó `name=second` → value **`second`**.
- `Properties.load(Reader UTF-8)` đọc ký tự Unicode UTF-8 theo Reader; `Properties.load(InputStream)` đọc **ISO-8859-1**.

**Tài liệu:** [Java SE 17 — Properties](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Properties.html) · [Java SE 17 — PropertyResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PropertyResourceBundle.html) · [Java SE 17 — ResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html).
