# Phân biệt Properties.load(InputStream) với PropertyResourceBundle

## 1. Hai API cùng đọc .properties nhưng phục vụ hai mục đích

Giả sử ứng dụng lưu thông điệp trong tệp `messages_vi.properties`:

```properties
title=Tiếng Việt
button.save=Lưu
```

Có thể đọc tệp này bằng `java.util.Properties.load(InputStream)`, hoặc để hệ thống đa ngôn ngữ tìm tệp thông qua `ResourceBundle.getBundle(...)` và `PropertyResourceBundle`. Cả hai đều hiểu cú pháp key/value của định dạng `.properties`, nhưng **không phải cùng một cơ chế tải tài nguyên**.

Sự khác biệt dễ gây lỗi nhất với tiếng Việt: **`Properties.load(InputStream)` luôn giải mã byte theo ISO-8859-1**, còn **`PropertyResourceBundle(InputStream)` trên Java 9+ mặc định giải mã UTF-8, có khả năng đọc lại theo ISO-8859-1 nếu gặp chuỗi byte UTF-8 không hợp lệ**. Dù file nằm trên cùng classpath và mang đuôi `.properties`, dùng nhầm API sẽ khiến văn bản có dấu bị lỗi (mojibake).

Bài này giúp bạn phân biệt rõ mục đích, cách giải mã, cách chọn locale, fallback, vòng đời và những tình huống cần chọn `Reader` để xử lý dữ liệu ổn định trên Java 17+.

## 2. Nhìn nhanh: Properties và PropertyResourceBundle

| Tiêu chí | `Properties` với `load(InputStream)` | `PropertyResourceBundle` |
| --- | --- | --- |
| Lớp Java | `java.util.Properties` | `java.util.PropertyResourceBundle extends ResourceBundle` |
| Mục đích chính | Nạp tập cấu hình key/value từ stream | Biểu diễn một bộ tài nguyên bản địa hóa từ nội dung properties |
| API đọc | `getProperty(key)`, `getProperty(key, default)` | `getString(key)`, `getObject(key)`, các API `ResourceBundle` |
| Kiểu giá trị của file | Chuỗi `String` | Chuỗi `String`; không tự tạo `String[]` hay số |
| `InputStream` giải mã | **ISO-8859-1** theo hợp đồng API | **UTF-8 từ Java 9+**; mặc định fallback ISO-8859-1 nếu UTF-8 lỗi |
| `Reader` | `load(Reader)` dùng ký tự đã được Reader giải mã | Constructor `PropertyResourceBundle(Reader)` dùng ký tự Reader đưa vào |
| Locale | Không có cơ chế chọn theo locale tích hợp | Có thể dùng trong `ResourceBundle.getBundle(baseName, locale)` |
| Parent/fallback | Có thể khai báo `Properties defaults`, không tự tìm file theo locale | Hệ thống `ResourceBundle` có chuỗi candidate locale/parent khi dùng `getBundle` |
| Vòng đời | Đối tượng do code tạo và quản lý, `load` nạp thêm vào đối tượng hiện có | Bundle được tạo khi load, `ResourceBundle.getBundle` có cơ chế cache |
| Khi phù hợp | Cấu hình ứng dụng, properties chung, đọc tệp tùy ý | Thông điệp, nhãn và tài nguyên bản địa hóa theo ngôn ngữ/vùng |

**Phân biệt hai tầng:** `PropertyResourceBundle` là một *kiểu triển khai* của `ResourceBundle`. `ResourceBundle.getBundle(...)` là *cơ chế tìm và lựa chọn* bundle theo locale, có thể tạo `PropertyResourceBundle` từ `.properties` hoặc chọn bundle định nghĩa bằng lớp Java. Nếu bạn gọi trực tiếp `new PropertyResourceBundle(inputStream)`, Java **không tự suy ra locale và parent chỉ từ tên file**.

## 3. Cùng định dạng .properties nhưng cách giải mã khác nhau

### 3.1. Cách hoạt động của Properties.load(InputStream)

`InputStream` cung cấp **byte**. Phương thức `Properties.load(InputStream)` diễn giải mỗi byte theo mã hóa **ISO-8859-1 (Latin-1)**; nó không tự nhìn file và đoán UTF-8, và không thay đổi hành vi này trên Java 17/21 chỉ vì `Charset.defaultCharset()` của JVM là UTF-8.

Điều đó có nghĩa:

- Các ký tự ASCII thông thường, ví dụ `id=123` hoặc `enabled=true`, đọc giống nhau trong UTF-8 và ISO-8859-1.
- Một ký tự ngoài ASCII được mã hóa UTF-8 có thể biến thành **nhiều ký tự Latin-1 sai** khi nạp bằng `load(InputStream)`.
- Ký tự không thể mã hóa trực tiếp trong ISO-8859-1 phải biểu diễn dưới dạng `\uXXXX` trong tệp muốn sử dụng với overload này.
- `Properties.load(InputStream)` **không hỗ trợ đối số charset**; muốn đọc byte UTF-8 trực tiếp, dùng `Properties.load(Reader)` với `InputStreamReader(..., StandardCharsets.UTF_8)`.

Ví dụ minh họa:

```java
Properties properties = new Properties();

try (InputStream input = Files.newInputStream(Path.of("config.properties"))) {
    properties.load(input); // Byte được hiểu là ISO-8859-1.
}
```

Đây là **snippet**, cần các import từ `java.io`, `java.nio.file`, `java.util`; tên file chỉ là ví dụ đường dẫn. Nếu `config.properties` được lưu UTF-8 có tiếng Việt trực tiếp, kết quả có thể sai.

### 3.2. Cách hoạt động của PropertyResourceBundle(InputStream)

Với **Java 9 trở lên**, constructor:

```java
new PropertyResourceBundle(inputStream);
```

thử giải mã byte theo **UTF-8**. Mặc định, nếu xảy ra `MalformedInputException` hoặc `UnmappableCharacterException` trong quá trình giải mã UTF-8, nó đọc lại dữ liệu theo **ISO-8859-1** để tương thích các resource file kiểu cũ. Đây là thay đổi liên quan JEP 226, không phải hành vi của `Properties.load(InputStream)`.

Khi tệp thực sự là UTF-8 hợp lệ, chữ tiếng Việt được giữ đúng. Nếu file hỏng hoặc có byte không hợp lệ, mặc định có thể phát sinh kết quả đọc theo Latin-1 thay vì báo lỗi như bạn mong đợi. Vì thế cần thống nhất mã hóa file trong pipeline build.

Có thể buộc `PropertyResourceBundle` chỉ sử dụng một mã hóa bằng **system property chính xác**:

```bash
java -Djava.util.PropertyResourceBundle.encoding=UTF-8 Main
```

Các giá trị được công nhận là `UTF-8` hoặc `ISO-8859-1`. Tùy chọn được đọc khi **khởi tạo lớp `PropertyResourceBundle`**, nên không nên mong việc thay đổi `System.setProperty(...)` giữa các request sẽ thay đổi cách giải mã. Khi đặt là `UTF-8`, byte không hợp lệ có thể gây ngoại lệ giải mã thay vì fallback; khi đặt là `ISO-8859-1`, file phải mã hóa phù hợp hoặc dùng `\uXXXX`.

**Không nhầm tên property:** là `java.util.PropertyResourceBundle.encoding`; không có tác dụng khi đưa cờ này cho `Properties.load(InputStream)`.

### 3.3. Hai phiên bản Reader: kiểm soát mã hóa tường minh

Cả hai API đều có đường đọc qua `Reader`:

```java
try (Reader reader = Files.newBufferedReader(
        Path.of("messages_vi.properties"), StandardCharsets.UTF_8)) {
    Properties props = new Properties();
    props.load(reader);
}
```

```java
try (Reader reader = Files.newBufferedReader(
        Path.of("messages_vi.properties"), StandardCharsets.UTF_8)) {
    ResourceBundle bundle = new PropertyResourceBundle(reader);
}
```

`Reader` cung cấp **ký tự đã giải mã** thay vì byte. Việc chọn UTF-8 diễn ra ở `Files.newBufferedReader(...)`; các API nạp properties không tự giải mã lần thứ hai. Đây là cách rõ ràng khi bạn kiểm soát file và muốn **quy định UTF-8 tại điểm đọc**.

Các đoạn trên là **snippet độc lập trong phương thức**, cần import `java.io.Reader`, `java.nio.charset.StandardCharsets`, `java.nio.file.Files`, `java.nio.file.Path`, `java.util.Properties` và `java.util.ResourceBundle` hoặc `java.util.PropertyResourceBundle`. Phần demo đầy đủ bên dưới sẽ cung cấp một chương trình biên dịch/chạy được.

## 4. Thử nghiệm Java 17+ tái hiện lỗi mã hóa không cần file bên ngoài

Dùng chuỗi có ký tự ngoài tập Latin-1 như `ế` và `ệ` để phân biệt rõ cách giải mã. Chuỗi `"Xin chào"` có ký tự tiếng Việt nhưng riêng `à` và `ò` đã nằm trong Latin-1; nếu viết một phép thử sai cách chỉ với những ký tự này, có thể không làm lộ lỗi như dự kiến khi mã hóa đầu vào bị biến đổi. Vì vậy, ví dụ sau kiểm tra **giá trị cuối cùng so với chuỗi gốc** thay vì in trực tiếp các ký tự lỗi.

Tạo tệp **`PropertyEncodingDemo.java`** bằng UTF-8:

```java
import java.io.ByteArrayInputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;
import java.util.PropertyResourceBundle;

public class PropertyEncodingDemo {
    public static void main(String[] args) throws Exception {
        String expected = "Tiếng Việt";
        byte[] utf8 = ("greeting=" + expected + "\ncount=3\n")
                .getBytes(StandardCharsets.UTF_8);

        Properties fromBytes = new Properties();
        fromBytes.load(new ByteArrayInputStream(utf8));

        Properties fromReader = new Properties();
        fromReader.load(new InputStreamReader(
                new ByteArrayInputStream(utf8), StandardCharsets.UTF_8));

        PropertyResourceBundle bundleFromBytes =
                new PropertyResourceBundle(new ByteArrayInputStream(utf8));

        PropertyResourceBundle bundleFromReader =
                new PropertyResourceBundle(new InputStreamReader(
                        new ByteArrayInputStream(utf8),
                        StandardCharsets.UTF_8));

        System.out.println("Properties/InputStream OK: "
                + expected.equals(fromBytes.getProperty("greeting")));
        System.out.println("Properties/Reader OK: "
                + expected.equals(fromReader.getProperty("greeting")));
        System.out.println("Bundle/InputStream OK: "
                + expected.equals(bundleFromBytes.getString("greeting")));
        System.out.println("Bundle/Reader OK: "
                + expected.equals(bundleFromReader.getString("greeting")));
        System.out.println("Bundle count type: "
                + bundleFromBytes.getObject("count")
                        .getClass().getSimpleName());
    }
}
```

Biên dịch và chạy với **JDK 17 hoặc 21**, và không truyền system property thay đổi encoding:

```bash
javac -encoding UTF-8 PropertyEncodingDemo.java
java PropertyEncodingDemo
```

**Stdout:**

```text
Properties/InputStream OK: false
Properties/Reader OK: true
Bundle/InputStream OK: true
Bundle/Reader OK: true
Bundle count type: String
```

Giải thích:

1. `utf8` được tạo từ văn bản `"Tiếng Việt"` theo UTF-8, chứa các byte đa byte.
2. `Properties.load(InputStream)` giải mã chúng như ISO-8859-1 nên chuỗi không còn bằng `expected`.
3. `Properties.load(Reader)` nhận ký tự đúng vì `InputStreamReader` chỉ rõ UTF-8.
4. `PropertyResourceBundle(InputStream)` trên Java 17+ nhận UTF-8 hợp lệ và trả nguyên văn.
5. `PropertyResourceBundle(Reader)` cũng đúng vì Reader đã sử dụng UTF-8.
6. Giá trị `count=3` được cả các kiểu bundle dựa trên `.properties` coi là **String**, không tự thành `Integer`.

Ví dụ dùng dữ liệu ở bộ nhớ để không phụ thuộc đường dẫn, encoding mặc định của hệ điều hành hay file được đóng gói trong classpath. `ByteArrayInputStream` không giữ tài nguyên hệ điều hành; với file thực tế, hãy dùng `try-with-resources` để đóng stream/reader.

**Thử nghiệm ngược:** nếu thay `java PropertyEncodingDemo` bằng chạy có cờ `-Djava.util.PropertyResourceBundle.encoding=ISO-8859-1`, kết quả `Bundle/InputStream OK` sẽ là `false` trong khi hai đường `Reader` vẫn đúng. Cờ này không thay đổi hành vi của `Properties.load`.

## 5. Properties: đọc tệp cấu hình, không tự chọn ngôn ngữ

`Properties` phù hợp với cấu hình key/value:

```properties
server.port=8080
feature.enabled=true
display.name=Demo
```

Ví dụ:

```java
Properties settings = new Properties();
try (Reader reader = Files.newBufferedReader(
        Path.of("app.properties"), StandardCharsets.UTF_8)) {
    settings.load(reader);
}

String port = settings.getProperty("server.port");
String fallback = settings.getProperty("unknown.key", "default");
boolean enabled = Boolean.parseBoolean(
        settings.getProperty("feature.enabled", "false"));
```

Các giá trị vẫn là `String`. Việc chuyển kiểu sang `int`, `boolean` hoặc loại khác là bước riêng; có thể xảy ra `NumberFormatException` khi parse số không hợp lệ.

**Điểm khác biệt về trạng thái:**

- `new Properties()` tạo bảng trống. Gọi `load(...)` **nạp/ghi đè các key được tìm thấy** vào bảng hiện có; nó **không tự xóa những key cũ không được liệt kê** trong dữ liệu mới.
- `setProperty(...)` và `getProperty(...)` cho phép cập nhật/đọc key bằng String. Không nên lạm dụng `put(...)` với value kiểu không phải String dù `Properties` kế thừa `Hashtable<Object,Object>`.
- `Properties` có thể dùng một đối tượng **defaults** qua constructor `Properties(defaults)`, nhưng đây là fallback do lập trình viên tự thiết lập, **không tự dò `messages_vi.properties` và `messages.properties`**.
- `load(InputStream)` và `load(Reader)` không tự đóng stream/reader được truyền vào; người gọi nên quản lý vòng đời bằng `try-with-resources`.

Các lựa chọn trong `Properties` phù hợp với cấu hình thông thường. Nếu cần các bản dịch phụ thuộc `Locale`, hãy cân nhắc `ResourceBundle` thay vì tự viết hàng loạt logic chọn file.

## 6. PropertyResourceBundle: một phần của cơ chế ResourceBundle

### 6.1. ResourceBundle.getBundle tìm file theo locale

Một ứng dụng có thể tổ chức:

```text
resources/
  messages.properties
  messages_vi.properties
  messages_en.properties
```

Nếu các file nằm trên **classpath root**, thì `ResourceBundle.getBundle("messages", Locale.forLanguageTag("vi-VN"))` có thể chọn `messages_vi.properties` khi `messages_vi_VN.properties` không tồn tại.

**Tệp `messages.properties`**:

```properties
title=Default title
footer=Powered by Java
```

**Tệp `messages_vi.properties`**:

```properties
title=Tiếng Việt
```

Tạo **`BundleLookupDemo.java`** trong cùng thư mục với hai file properties để có thể chạy classpath đơn giản:

```java
import java.util.Locale;
import java.util.ResourceBundle;

public class BundleLookupDemo {
    public static void main(String[] args) {
        ResourceBundle messages = ResourceBundle.getBundle(
                "messages", Locale.forLanguageTag("vi-VN"));

        System.out.println("Locale: "
                + messages.getLocale().toLanguageTag());
        System.out.println("Title: " + messages.getString("title"));
        System.out.println("Footer: " + messages.getString("footer"));
        System.out.println("Title type: "
                + messages.getObject("title").getClass().getSimpleName());
    }
}
```

Biên dịch/chạy bằng JDK 17+ trong thư mục chứa **cả ba file**:

```bash
javac -encoding UTF-8 BundleLookupDemo.java
java BundleLookupDemo
```

Stdout:

```text
Locale: vi
Title: Tiếng Việt
Footer: Powered by Java
Title type: String
```

Vì `messages_vi.properties` có key `title`, bundle lấy bản tiếng Việt; key `footer` không được khai báo ở bản tiếng Việt nên được tìm từ **parent** `messages.properties`. Bundle được chọn có `getLocale()` tương ứng `vi` (khác locale được yêu cầu `vi-VN`). File được lưu UTF-8, và trên Java 17+ đường tải mặc định của `PropertyResourceBundle` hiểu UTF-8.

Cần nhớ `getBundle(...)` **không phải overload của `Properties.load(...)`**: nó có chiến lược chọn candidate locales, fallback và cache. Nếu trong classpath còn có lớp Java `messages_vi` tương ứng `ListResourceBundle`, chiến lược chọn định dạng bundle có thể ảnh hưởng kết quả; không đặt các resource trùng base name một cách tình cờ. Nếu chạy trong module được đóng gói bằng JPMS hoặc framework riêng, đường dẫn/khả năng cung cấp resource còn phụ thuộc cấu hình module/provider.

### 6.2. Constructor trực tiếp không tự tạo fallback

Mặt khác:

```java
try (InputStream in = Files.newInputStream(
        Path.of("messages_vi.properties"))) {
    PropertyResourceBundle direct = new PropertyResourceBundle(in);
    System.out.println(direct.getString("title"));
}
```

Đây là **snippet**. Nó nạp đúng file được truyền vào; không tự tìm `messages.properties` bên cạnh để làm cha. Khi gọi `direct.getString("footer")` mà file chỉ có `title`, sẽ phát sinh `MissingResourceException`. Ngược lại, phiên bản `getBundle("messages", vi-VN)` ở ví dụ trước có parent vì loader của `ResourceBundle` tạo chuỗi bundle tương ứng.

Đừng ghi `new PropertyResourceBundle(...)` rồi tin rằng tên file có hậu tố `_vi` sẽ tự kích hoạt cơ chế chọn bản dịch/parent. Muốn hành vi đó, dùng `ResourceBundle.getBundle`, hoặc cài đặt chính sách parent một cách có chủ đích trong cơ chế tài nguyên được hỗ trợ.

### 6.3. Kiểu trả về và lỗi truy cập

Với resource từ `.properties`:

```properties
retry.count=3
tags=red,green,blue
```

- `bundle.getString("retry.count")` trả `"3"`.
- `bundle.getObject("retry.count")` trả đối tượng `String`, không phải `Integer`.
- `bundle.getStringArray("tags")` ném `ClassCastException`, vì `"red,green,blue"` chỉ là một chuỗi, không phải `String[]`.
- `bundle.getString("not.existing")` ném `MissingResourceException` nếu key vắng mặt trong bundle và toàn bộ parent.

Nếu cần `String[]` hoặc giá trị object không phải String, hãy sử dụng nguồn bundle có hỗ trợ kiểu đó, chẳng hạn `ListResourceBundle`, hoặc tự phân tích định dạng dữ liệu đã được định nghĩa rõ. `Properties.load` cũng không tự biến `retry.count=3` thành số nguyên.

## 7. Cú pháp properties và Unicode escape

Hai API đều làm việc với cú pháp cơ bản của file properties:

```properties
# Comment
language=vi
message: Xin chào
continued=Phần thứ nhất \
  phần thứ hai
escaped=Line 1\nLine 2
unicode=\u1ebf
```

Các quy tắc cần hiểu:

1. `=` hoặc `:` có thể ngăn cách key/value; trong một số trường hợp khoảng trắng cũng là dấu phân cách. Dùng một kiểu nhất quán để dễ đọc.
2. Dòng bắt đầu bằng `#` hoặc `!` (sau khoảng trắng đầu dòng phù hợp) là comment.
3. Dấu backslash ở cuối dòng logic có thể nối dòng với dòng tiếp theo. Không nên dùng trực tiếp multiline messages phức tạp khi định dạng trình bày cần bảo toàn xuống dòng.
4. Escape `\n` trong giá trị là ký tự xuống dòng khi đọc; `\\` là backslash; một số ký tự đặc biệt ở key/value cần escape.
5. `\uXXXX` là Unicode escape gồm **chính xác bốn chữ số hex**, ví dụ `\u1ebf` biểu diễn chữ `ế`. Với ký tự ngoài BMP, cần cặp surrogate theo cú pháp escape tương ứng. Không viết escape sai dạng, vì parser có thể ném `IllegalArgumentException`.
6. File ISO-8859-1 chứa `unicode=\u1ebf` vẫn có thể được nạp đúng bằng `Properties.load(InputStream)`, vì chuỗi escape là các byte ASCII trước khi parser chuyển thành Unicode.

**Phân biệt hai bước:** charset (UTF-8/Latin-1) giải mã **byte thành ký tự**; parser properties mới chuyển `\uXXXX`, `\n` và dấu phân cách thành cặp key/value. Unicode escape không có nghĩa `Properties.load(InputStream)` đã hỗ trợ giải mã UTF-8 trực tiếp.

Đối với nội dung chứa ký tự tiếng Việt thông thường, dùng UTF-8 cùng với `Properties.load(Reader)` hoặc `PropertyResourceBundle` trên Java 9+ sẽ dễ soạn và review hơn việc biến mọi chữ có dấu thành escape.

## 8. Tương thích phiên bản Java và tính nhất quán khi deploy

| Môi trường | `Properties.load(InputStream)` | `PropertyResourceBundle(InputStream)` |
| --- | --- | --- |
| Java 8 | ISO-8859-1 | ISO-8859-1 (đối với đường nạp InputStream thông thường) |
| Java 9+ | ISO-8859-1 | Mặc định UTF-8, nếu chuỗi UTF-8 lỗi thì thử lại ISO-8859-1 |
| Java 17/21 | ISO-8859-1 | Mặc định UTF-8 với cơ chế tương thích như trên |
| Java 17/21 với cờ `java.util.PropertyResourceBundle.encoding=ISO-8859-1` | Vẫn ISO-8859-1 | Chỉ dùng ISO-8859-1 |
| Java 17/21 với cờ `java.util.PropertyResourceBundle.encoding=UTF-8` | Vẫn ISO-8859-1 | Chỉ dùng UTF-8 |

**Vì sao fallback cần được quan tâm?** Một file ISO-8859-1 chứa ký tự non-ASCII có thể chứa byte không hợp lệ trong UTF-8 và kích hoạt chế độ đọc lại Latin-1. Tuy nhiên, một chuỗi byte thực chất theo Latin-1 **có thể ngẫu nhiên cũng hợp lệ UTF-8**, nên việc đọc tự động vẫn có thể cho ra kết quả sai mà không báo lỗi. Do đó, một dự án nên thống nhất và xác nhận encoding tại build/test thay vì dựa vào khả năng đoán.

Đừng nhầm cờ này với `-Dfile.encoding=UTF-8`. `Properties.load(InputStream)` có hợp đồng ISO-8859-1 cố định, và `PropertyResourceBundle` có chính sách riêng. Thay đổi encoding mặc định của máy không sửa được một parser được đặc tả mã hóa rõ ràng.

Đối với kho dự án còn hỗ trợ Java 8, phương án dùng `Reader` với UTF-8 có thể giúp kiểm soát việc đọc properties thủ công. Nếu lựa chọn tải `ResourceBundle.getBundle` mặc định trên Java 8, cần bảo đảm file và encoding theo quy tắc của JDK đó hoặc cấu hình cơ chế nạp phù hợp; không bê nguyên giả định UTF-8 từ Java 17 trở về Java 8.

## 9. Khi nào nên dùng API nào?

**Tình huống A — cấu hình runtime không phụ thuộc ngôn ngữ người dùng.**

Ví dụ `app.properties` chứa port, timeout, feature flag, endpoint. Nên dùng `Properties` (hoặc cơ chế cấu hình của framework), đọc theo charset của tệp bằng `Reader` khi bạn muốn UTF-8. Không cần tạo `ResourceBundle` chỉ để đọc `server.port`.

**Tình huống B — thông điệp giao diện có nhiều phiên bản theo ngôn ngữ.**

Ví dụ `messages.properties`, `messages_vi.properties`, `messages_en.properties`. Nên dùng `ResourceBundle.getBundle("messages", userLocale)`. Với các file .properties, bundle được sử dụng thường là `PropertyResourceBundle`; dự án có thể chuyển hướng provider tùy cấu hình. Cần kiểm tra key thiếu, locale không có bản dịch, fallback và ngữ pháp của từng thông điệp.

**Tình huống C — đọc một tệp properties cụ thể bằng đường dẫn và muốn API bundle.**

Có thể dùng `new PropertyResourceBundle(Reader)` nếu bạn muốn `getString`/`keySet` của `ResourceBundle` và chủ động cung cấp nội dung. Nhưng không có khả năng chọn nhiều file theo locale chỉ vì tệp có hậu tố `_vi`.

**Tình huống D — dữ liệu nhiều kiểu và cấu trúc phức tạp.**

Cả file properties đọc theo các API trên đều lưu value như `String`. Cấu trúc phức tạp nên dùng schema rõ nghĩa, parser/validator phù hợp hoặc `ListResourceBundle` khi mục đích thật sự là tài nguyên kiểu object. Không lấy dấu phẩy trong chuỗi làm bằng chứng đó là `String[]`.

## 10. Lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `Properties.load(InputStream)` trả chữ Việt sai | File UTF-8 bị giải mã như ISO-8859-1 | Đổi sang `load(Reader)` và chỉ định UTF-8 |
| `PropertyResourceBundle` đọc file Latin-1 nhưng có ký tự sai | Byte tình cờ hợp lệ UTF-8, hoặc file trộn encoding | Chuẩn hóa toàn bộ file; cân nhắc cờ mã hóa cố định và kiểm thử |
| Chạy Java 8 ổn, lên Java 17 chữ thay đổi | Thay đổi mặc định của `PropertyResourceBundle` từ Java 9 | Kiểm tra encoding nguồn và đường nạp, không đổi bừa parser |
| `getString("unknown")` ném ngoại lệ | Key thiếu ở bundle và parent | Kiểm tra tên key, base name, parent/fallback |
| `getProperty("unknown")` trả `null` | Không có key trong `Properties`/defaults | Dùng overload default hoặc xử lý thiếu key |
| `getStringArray("menu")` với `menu=A,B` | File properties tạo `String`, không tạo mảng | Dùng key riêng hoặc parser có quy tắc rõ |
| `ResourceBundle.getBundle` tìm nhầm ngôn ngữ | Default locale/fallback hoặc cấu hình ứng viên chưa được hiểu | Truyền locale tường minh, kiểm tra `getLocale()` và catalog hỗ trợ |
| `new PropertyResourceBundle(file)` không fallback | Constructor trực tiếp không tạo chuỗi parent | Dùng `ResourceBundle.getBundle` khi cần chiến lược locale |
| Sau `Properties.load`, key cũ vẫn còn | `load` không xóa bảng trước khi thêm dữ liệu | Tạo đối tượng `Properties` mới nếu muốn thay toàn bộ |
| Đặt `-Dfile.encoding=UTF-8` nhưng lỗi không hết | Overload InputStream vẫn có encoding cố định | Chọn API/Reader tương ứng, không phụ thuộc default charset |
| `Integer.parseInt(getString(...))` lỗi | Value ở file là chuỗi không đúng dạng số | Xác thực và báo lỗi cấu hình, không coi bundle là bộ ép kiểu tự động |
| Unicode escape `\uXXXX` bị sai | Escape không đủ bốn hex hoặc nội dung được escape nhầm | Kiểm tra cú pháp và dùng UTF-8 rõ ràng |

### Lưu ý về tài nguyên, bảo mật và kiểm thử

- **Đóng stream/reader** do mình mở bằng `try-with-resources`. Không bỏ qua `IOException` khi đọc file; nếu file là bắt buộc, thông báo đường dẫn/nguồn và nguyên nhân.
- **Không ghi trực tiếp secret** vào resource dịch hoặc properties đóng gói trong ứng dụng public. Bản chất resource chứa các cặp key/value, không phải kho lưu bí mật.
- **Không gọi `Locale.setDefault(...)` cho mỗi request** để đổi ngôn ngữ: default locale là trạng thái JVM, có thể gây ảnh hưởng nhiều luồng. Truyền locale của người dùng cho `getBundle`.
- **Phân biệt mã hóa tệp với mã hóa console.** Nếu chuỗi trong Java đúng nhưng terminal in sai, kiểm tra encoding của console riêng. Thử so sánh `String.equals` hoặc code points để xác định lỗi từ lúc nạp hay lúc xuất.
- **Kiểm thử ở ít nhất hai môi trường** khi nâng JDK hoặc chuyển file legacy: một nội dung tiếng Việt có ký tự ngoài ASCII/Latin-1, một file có Unicode escape, key thiếu, bundle fallback, file trộn encoding và trường hợp dữ liệu không hợp lệ.
- **Kiểm thử caching** nếu có nhu cầu thay đổi bản dịch trong lúc ứng dụng đang chạy: `ResourceBundle.getBundle` có cache; thay file trên đĩa không đồng nghĩa mọi lần đọc sẽ tự dùng bản mới. Cần thiết kế chính sách reload riêng, thận trọng với phiên bản cũ đang được sử dụng.

## 11. Tự kiểm tra kiến thức

**Câu 1.** File `messages_vi.properties` được lưu UTF-8, chứa `title=Tiếng Việt`. Vì sao `new Properties().load(InputStream)` có thể trả chữ sai trên Java 21?

**Đáp án:** Vì `Properties.load(InputStream)` diễn giải byte theo **ISO-8859-1**, kể cả trên Java 21. Dùng `Properties.load(Reader)` với `InputStreamReader`/`Files.newBufferedReader` chỉ định UTF-8.

**Câu 2.** Cùng file đó, `new PropertyResourceBundle(InputStream)` trên Java 17 mặc định đọc theo encoding nào?

**Đáp án:** Thử **UTF-8** trước. Nếu gặp lỗi giải mã cụ thể, mặc định có cơ chế đọc lại theo ISO-8859-1 để tương thích, trừ khi system property `java.util.PropertyResourceBundle.encoding` buộc một encoding được hỗ trợ.

**Câu 3.** Gọi `new PropertyResourceBundle(input)` với nội dung của `messages_vi.properties`, rồi đọc key chỉ có trong `messages.properties`. Nó có tự lấy từ file gốc không?

**Đáp án:** Không. Constructor trực tiếp không dò file cha bằng hậu tố tên. Chuỗi fallback theo locale được thiết lập thông qua cơ chế chọn bundle như `ResourceBundle.getBundle`.

**Câu 4.** Hai API có nạp `quantity=3` trực tiếp thành `int` hoặc `Integer` không?

**Đáp án:** Không. Value của file properties vẫn là `String`. Chuyển kiểu là bước khác của ứng dụng.

**Câu 5.** Thay `Properties.load(InputStream)` bằng `load(Reader)` nhưng Reader dùng charset mặc định không được kiểm soát có đảm bảo chữ đúng không?

**Đáp án:** Không. Reader phải giải mã đúng charset của file. Chỉ định rõ `StandardCharsets.UTF_8` (hoặc charset nguồn đã xác định) để kết quả ổn định.

**Câu 6.** Nếu file cấu hình chỉ có ASCII, tại sao hai phương thức thường cho kết quả giống nhau?

**Đáp án:** Byte ASCII thông thường có cùng giá trị ký tự trong UTF-8 và ISO-8859-1; sự khác biệt lộ rõ với dữ liệu Unicode ngoài ASCII.

## 12. Ghi nhớ và tài liệu chính thức

- **`Properties.load(InputStream)` = ISO-8859-1**, luôn theo hợp đồng Java. Muốn đọc file UTF-8 bằng `Properties`, dùng `load(Reader)` với charset tường minh.
- **`PropertyResourceBundle(InputStream)` trên Java 9+** mặc định giải mã UTF-8 rồi có thể fallback Latin-1. Có thể kiểm soát bằng `java.util.PropertyResourceBundle.encoding`.
- **`Reader` giải quyết bước giải mã byte**, trong khi parser properties giải thích key/value và escape; đừng nhầm hai tầng này.
- `Properties` phù hợp cấu hình và có thể nạp thêm vào bảng hiện có. `PropertyResourceBundle` phục vụ tài nguyên i18n, và `ResourceBundle.getBundle` mới điều phối việc chọn file theo locale/parent/caching.
- Dù dùng cách nào, giá trị trong file `.properties` vẫn là **chuỗi**, không tự biến thành số hoặc mảng.

Tài liệu tham khảo:

- [Java SE 21 — Properties](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Properties.html)
- [Java SE 21 — PropertyResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/PropertyResourceBundle.html)
- [Java SE 21 — ResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ResourceBundle.html)
- [JEP 226 — UTF-8 Property Resource Bundles](https://openjdk.org/jeps/226)
