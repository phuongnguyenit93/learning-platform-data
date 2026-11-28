# ResourceBundle và PropertyResourceBundle: đối chiếu quy tắc đọc tệp properties riêng của API

## 1. Hai lớp phối hợp để nạp tài nguyên theo Locale

`ResourceBundle` và `PropertyResourceBundle` thường được dùng cùng nhau khi ứng dụng cần hiển thị thông báo, nhãn giao diện hoặc nội dung theo ngôn ngữ và vùng địa lý.

- `ResourceBundle` là API tra cứu một họ tài nguyên theo `baseName` và `Locale`. Nó tìm bundle phù hợp, xây dựng chuỗi bundle cha, cung cấp API lấy giá trị theo key và cache kết quả.
- `PropertyResourceBundle` là một triển khai cụ thể của `ResourceBundle`. Nó đọc các cặp key/value từ nội dung theo cú pháp `.properties`.
- Khi tìm thấy tệp `.properties`, cơ chế nạp mặc định của `ResourceBundle` tạo `PropertyResourceBundle` từ luồng byte của resource.
- Quy tắc charset của `PropertyResourceBundle(InputStream)` là quy tắc riêng của API: UTF-8 trước, sau đó có thể fallback ISO-8859-1 nếu gặp byte UTF-8 malformed hoặc unmappable.

Điểm cần nhớ trong Java 18+ là hành vi UTF-8 của resource bundle properties đã có từ **Java 9** theo **JEP 226 — UTF-8 Properties Files**. Đây là thay đổi riêng của ResourceBundle/PropertyResourceBundle, không phải hệ quả của JEP 400 (UTF-8 by Default) trong Java 18.

```text
ResourceBundle.getBundle(baseName, locale)
             |
             | tìm tên bundle theo Locale
             v
      Messages_vi_VN
             |
             | ưu tiên class bundle, sau đó properties
             v
      Messages_vi_VN.properties
             |
             | new PropertyResourceBundle(InputStream)
             v
      UTF-8 decode
             |
             | nếu malformed/unmappable: thử ISO-8859-1
             v
      ResourceBundle (key -> value)
             |
             | key không có thì tìm bundle cha
             v
      Giá trị trả về cho ứng dụng
```

Bài này tập trung vào cách ResourceBundle tìm và ghép các bundle, quy tắc đọc byte của PropertyResourceBundle, sự khác nhau giữa `InputStream` và `Reader`, và cách chọn encoding phù hợp cho file `.properties` hiện nay.

## 2. Tổ chức một họ resource bundle

Một họ bundle có chung `baseName`, còn hậu tố thể hiện Locale. Ví dụ:

```text
src/main/resources/
└── com/
    └── example/
        └── i18n/
            ├── Messages.properties
            ├── Messages_vi.properties
            ├── Messages_vi_VN.properties
            ├── Messages_en.properties
            └── Messages_fr.properties
```

Tên bundle gốc là `com.example.i18n.Messages`.

| Tệp | Vai trò |
| --- | --- |
| `Messages.properties` | Bundle gốc, dùng khi không có bản địa hóa cụ thể phù hợp |
| `Messages_vi.properties` | Nội dung theo ngôn ngữ tiếng Việt |
| `Messages_vi_VN.properties` | Nội dung riêng cho tiếng Việt tại Việt Nam |
| `Messages_en.properties` | Nội dung tiếng Anh |
| `Messages_fr.properties` | Nội dung tiếng Pháp |

Ví dụ nội dung:

```properties
# Messages.properties
app.title=Application
button.save=Save
message.welcome=Welcome
```

```properties
# Messages_vi.properties
app.title=Ứng dụng
button.save=Lưu
message.welcome=Chào mừng
```

```properties
# Messages_vi_VN.properties
message.welcome=Chào mừng bạn đến với ứng dụng
```

Tên key phân biệt chữ hoa và chữ thường. Các file trong cùng họ nên dùng cùng key cho những nội dung tương đương; một locale có thể chỉ định nghĩa các key cần ghi đè, còn key thiếu sẽ được tra ở bundle cha.

## 3. Nạp bundle bằng ResourceBundle.getBundle

Ứng dụng thường không cần tự mở file `.properties`. Gọi `ResourceBundle.getBundle` để API tìm và nạp bundle:

```java
import java.util.Locale;
import java.util.ResourceBundle;

Locale locale = Locale.forLanguageTag("vi-VN");

ResourceBundle messages = ResourceBundle.getBundle(
        "com.example.i18n.Messages",
        locale);

String title = messages.getString("app.title");
String save = messages.getString("button.save");
String welcome = messages.getString("message.welcome");

System.out.println(title);
System.out.println(save);
System.out.println(welcome);
System.out.println(messages.getLocale());
```

`getBundle` trả về kiểu trừu tượng `ResourceBundle`, không yêu cầu ứng dụng biết bundle thực tế là `PropertyResourceBundle` hay một lớp resource bundle khác.

Nếu tìm thấy file `Messages_vi_VN.properties`, nó có thể được nạp thành `PropertyResourceBundle`. Nếu không có file locale đó, ResourceBundle tiếp tục tìm ứng viên ít cụ thể hơn theo quy tắc Locale.

Không truyền `Locale` khiến overload `getBundle(baseName)` sử dụng default Locale của JVM. Với kết quả cần ổn định giữa các máy, service hoặc bài kiểm thử, hãy truyền Locale tường minh.

## 4. Quy tắc tìm bundle theo Locale

Với yêu cầu `Locale.forLanguageTag("vi-VN")`, danh sách ứng viên thông thường là:

1. `Messages_vi_VN`
2. `Messages_vi`
3. `Messages` (root bundle)

ResourceBundle thử các ứng viên theo thứ tự. Với mỗi tên ứng viên, định dạng mặc định ưu tiên bundle dạng class (`java.class`) trước, rồi mới đến file properties (`java.properties`).

Ví dụ, nếu có `Messages_vi_VN.class` và `Messages_vi_VN.properties`, class bundle sẽ được chọn cho cùng tên ứng viên. Vì vậy, một class bundle có thể che khuất file properties cùng tên.

Nếu không tìm được bundle cho Locale được yêu cầu, cơ chế mặc định có thể thử lại bằng default Locale của JVM trước khi kết thúc ở bundle gốc. Điều này có nghĩa kết quả cuối cùng có thể phụ thuộc cấu hình Locale của tiến trình nếu ứng dụng không truyền Locale và không kiểm soát fallback.

### 4.1. Bundle cha và fallback cho từng key

Giả sử chỉ có:

```text
Messages.properties
Messages_vi.properties
```

Không có `Messages_vi_VN.properties`. Khi yêu cầu `vi-VN`, bundle `Messages_vi` có thể được chọn và bundle gốc trở thành parent.

Nếu `Messages_vi.properties` có `button.save` nhưng không có `app.title`, thao tác `getString("app.title")` tiếp tục tìm trong parent `Messages.properties`.

```java
ResourceBundle messages = ResourceBundle.getBundle(
        "com.example.i18n.Messages",
        Locale.forLanguageTag("vi-VN"));

String save = messages.getString("button.save"); // Có thể lấy từ Messages_vi
String title = messages.getString("app.title");  // Có thể lấy từ Messages.properties
```

Có hai tầng fallback cần phân biệt:

- **Fallback theo Locale:** chọn bundle ngôn ngữ/vùng phù hợp, ví dụ `vi_VN` rồi `vi` rồi root.
- **Fallback theo key:** khi key không có trong bundle đã chọn, ResourceBundle tìm key đó trong bundle cha.

`getLocale()` trả về Locale của bundle thực tế được chọn, giúp kiểm tra ứng dụng có nhận đúng bản địa hóa mong đợi hay đang dùng fallback.

### 4.2. MissingResourceException

Nếu không tìm được bundle phù hợp, `getBundle` ném `MissingResourceException`. Nếu bundle tồn tại nhưng key không có trong bundle đó hoặc chuỗi parent, `getString`/`getObject` cũng ném `MissingResourceException`.

```java
try {
    String text = messages.getString("message.not.defined");
} catch (java.util.MissingResourceException e) {
    // Key không tồn tại trong bundle và các bundle cha.
    System.err.println("Thiếu resource: " + e.getKey());
}
```

Không nên dùng exception như luồng điều khiển bình thường cho mọi key tùy chọn. Nếu key có thể vắng mặt theo thiết kế, kiểm tra `containsKey(key)` hoặc cung cấp giá trị mặc định ở tầng ứng dụng.

## 5. PropertyResourceBundle là triển khai cho file properties

`PropertyResourceBundle` là lớp con cụ thể của `ResourceBundle`, đọc các cặp key/value theo cú pháp properties. Ứng dụng thông thường để `ResourceBundle.getBundle` tự nạp lớp này khi tìm thấy resource `.properties`.

Có thể tạo trực tiếp khi cần đọc một nguồn riêng:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.PropertyResourceBundle;
import java.util.ResourceBundle;

Path path = Path.of("Messages_vi.properties");

try (InputStream input = Files.newInputStream(path)) {
    ResourceBundle bundle = new PropertyResourceBundle(input);
    System.out.println(bundle.getString("message.welcome"));
}
```

Constructor nhận `InputStream` có hợp đồng encoding riêng. Trên JDK hiện đại, nó đọc UTF-8 trước; nếu decoder phát hiện byte malformed hoặc unmappable, mặc định nó đọc lại từ đầu bằng ISO-8859-1.

Khi dùng trực tiếp constructor, ứng dụng chịu trách nhiệm quản lý stream. Khi dùng `ResourceBundle.getBundle`, quá trình mở và nạp resource được API quản lý nội bộ.

## 6. UTF-8 Properties Files từ Java 9: JEP 226

Trước Java 9, property resource bundles được đọc theo ISO-8859-1 khi nạp từ luồng byte. Java 9 đưa **JEP 226 — UTF-8 Properties Files** vào nền tảng, giúp các file bản địa hóa lưu trực tiếp tiếng Việt và nhiều ngôn ngữ khác thuận tiện hơn.

Quy tắc hiện hành của `PropertyResourceBundle(InputStream)`:

1. Thử giải mã luồng byte bằng UTF-8.
2. Nếu UTF-8 đọc thành công, dùng kết quả UTF-8.
3. Nếu gặp `MalformedInputException` hoặc `UnmappableCharacterException`, mặc định quay về trạng thái đầu và đọc lại toàn bộ luồng bằng ISO-8859-1.
4. Nếu việc đọc lại hoặc phân tích cú pháp gặp lỗi khác, ngoại lệ tương ứng được báo ra.

| Nguồn byte | Kết quả mặc định |
| --- | --- |
| UTF-8 hợp lệ | Đọc bằng UTF-8 |
| Byte ISO-8859-1 chứa `E9` độc lập | UTF-8 lỗi, thử lại bằng ISO-8859-1 |
| ASCII thuần | UTF-8 hợp lệ; kết quả giống ISO-8859-1 cho vùng ASCII |
| Byte malformed theo UTF-8 nhưng hợp lệ dưới Latin-1 | Fallback có thể đọc được theo ISO-8859-1 |

Điều này giải thích vì sao phần lớn file properties ASCII cũ tiếp tục hoạt động, trong khi file ISO-8859-1 có byte ngoài ASCII thường được đọc lại theo Latin-1 nếu chuỗi byte đó không hợp lệ với UTF-8.

## 7. Fallback ISO-8859-1 không phải cơ chế tự nhận diện charset

Fallback chỉ xảy ra khi UTF-8 decoder phát hiện chuỗi byte malformed hoặc unmappable. Nó không xác định chắc chắn encoding thật của file.

Ví dụ, byte `E9` độc lập không hợp lệ trong UTF-8 nên có thể kích hoạt fallback. Nhưng chuỗi byte `C3 A9` là UTF-8 hợp lệ. Nếu file ISO-8859-1 có đúng hai byte đó, PropertyResourceBundle sẽ chấp nhận UTF-8 và tạo ký tự `é`, dù ý nghĩa Latin-1 ban đầu có thể là hai ký tự `Ã©`.

Nói cách khác, một file Latin-1 có thể vô tình là chuỗi byte UTF-8 hợp lệ. Khi đó không có lỗi malformed để kích hoạt fallback, và kết quả có thể khác ý định của người tạo file.

**Không dùng fallback như công cụ đoán encoding.** Với hệ thống đang kiểm soát được, chuẩn hóa file resource sang UTF-8 và xác nhận byte đầu ra. Với file cũ có encoding đã biết, khóa encoding tường minh hoặc dùng Reader phù hợp.

## 8. Điều khiển encoding qua system property

`PropertyResourceBundle` hỗ trợ system property:

```text
java.util.PropertyResourceBundle.encoding
```

Khi property này được đặt thành một trong hai giá trị được hỗ trợ, constructor `PropertyResourceBundle(InputStream)` chỉ sử dụng encoding đó và không fallback sang encoding còn lại.

| Giá trị property | Hành vi của constructor InputStream |
| --- | --- |
| Không đặt | Thử UTF-8; nếu malformed/unmappable thì đọc lại bằng ISO-8859-1 |
| `UTF-8` | Chỉ đọc UTF-8; byte không hợp lệ gây ngoại lệ |
| `ISO-8859-1` | Chỉ đọc ISO-8859-1; ký tự ngoài Latin-1 phải dùng Unicode escape |
| Giá trị khác | Bị bỏ qua; hành vi mặc định được sử dụng |

Ví dụ khóa UTF-8 ngay khi khởi động JVM:

```bash
java -Djava.util.PropertyResourceBundle.encoding=UTF-8 -cp app.jar com.example.Main
```

Khi khóa UTF-8, dữ liệu malformed sẽ được báo lỗi thay vì tự fallback. Đây là lựa chọn hữu ích nếu toàn bộ resource bundle trong tiến trình phải tuân thủ UTF-8.

### 8.1. Property chỉ được đọc khi lớp khởi tạo

Giá trị `java.util.PropertyResourceBundle.encoding` được đọc và đánh giá khi lớp `PropertyResourceBundle` được khởi tạo lần đầu. Thay đổi hoặc xóa property sau thời điểm đó không làm thay đổi hành vi của các lần tạo bundle tiếp theo trong cùng tiến trình.

Vì vậy, nếu cần đặt property, cấu hình bằng tham số `-D` trước khi ứng dụng bắt đầu. Không trông chờ `System.setProperty(...)` ngay trước một lần gọi `getBundle` sẽ thay đổi encoding nếu lớp đã được khởi tạo.

Property này là cấu hình toàn tiến trình cho constructor InputStream, không phải tham số chọn charset riêng cho từng file. Nếu mỗi file có encoding khác nhau, hãy tạo Reader với charset tương ứng rồi dùng constructor Reader.

## 9. Constructor Reader: charset do ứng dụng quyết định

`PropertyResourceBundle(Reader)` nhận ký tự đã được giải mã. Constructor này không giới hạn encoding của file nguồn vì Reader đã quyết định cách chuyển byte thành ký tự.

Ví dụ đọc file UTF-8 trực tiếp:

```java
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.PropertyResourceBundle;

Path path = Path.of("Messages_vi.properties");

try (Reader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    PropertyResourceBundle bundle = new PropertyResourceBundle(reader);
    System.out.println(bundle.getString("message.welcome"));
}
```

Nếu file nguồn là ISO-8859-1, truyền charset đó cho Reader:

```java
try (Reader reader = Files.newBufferedReader(
        path, StandardCharsets.ISO_8859_1)) {
    PropertyResourceBundle bundle = new PropertyResourceBundle(reader);
}
```

Với Reader constructor:

- Không có bước thử UTF-8 rồi fallback ISO-8859-1.
- Không có giới hạn ISO-8859-1 của constructor InputStream.
- Charset, chính sách malformed và nguồn dữ liệu thuộc về Reader.
- Unicode có thể được cung cấp trực tiếp từ Reader; không bắt buộc biểu diễn ký tự ngoài Latin-1 bằng `\uXXXX`.

### 9.1. Yêu cầu decode UTF-8 nghiêm ngặt

`Files.newBufferedReader(path, StandardCharsets.UTF_8)` sử dụng charset được chỉ định và báo lỗi I/O nếu gặp chuỗi byte malformed hoặc unmappable. Có thể dùng trực tiếp khi muốn từ chối file không phải UTF-8 hợp lệ:

```java
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.PropertyResourceBundle;

try (Reader reader = Files.newBufferedReader(
        Path.of("Messages_vi.properties"), StandardCharsets.UTF_8)) {
    PropertyResourceBundle bundle = new PropertyResourceBundle(reader);
}
```

Nếu cần kiểm soát rõ `CodingErrorAction`, tạo `CharsetDecoder` với `REPORT` rồi truyền vào `InputStreamReader`:

```java
import java.io.InputStreamReader;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.PropertyResourceBundle;

var decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try (var reader = new InputStreamReader(
        Files.newInputStream(Path.of("Messages_vi.properties")), decoder)) {
    PropertyResourceBundle bundle = new PropertyResourceBundle(reader);
}
```

Đây là cách kiểm soát theo từng nguồn. Nó không phụ thuộc vào `java.util.PropertyResourceBundle.encoding`.

## 10. So sánh với Properties.load(InputStream)

Không nên suy luận rằng mọi API đọc `.properties` có cùng charset. `Properties` và `PropertyResourceBundle` là hai API khác nhau, với hợp đồng byte khác nhau:

| API | Khi nhận InputStream | Khi nhận Reader |
| --- | --- | --- |
| `Properties.load(...)` | ISO-8859-1 theo hợp đồng API | Reader quyết định charset |
| `PropertyResourceBundle` | UTF-8 trước, fallback ISO-8859-1 khi malformed/unmappable (trừ khi bị khóa bằng system property) | Reader quyết định charset, không fallback |

Ví dụ, `Properties.load(InputStream)` vẫn dùng ISO-8859-1 trên Java 18+. `PropertyResourceBundle(InputStream)` lại có quy tắc UTF-8 từ Java 9. JEP 400 không thay đổi hai hợp đồng này.

Nếu một file được đọc bằng `Properties.load(InputStream)` và một ứng dụng khác dùng `ResourceBundle`, kết quả có thể khác nhau nếu file chứa byte ngoài ASCII. Hãy xác định API mà ứng dụng thực sự dùng trước khi chẩn đoán lỗi tiếng Việt.

## 11. Cú pháp properties vẫn được áp dụng sau khi decode

Charset chỉ quyết định byte thành ký tự. Sau bước đó, `PropertyResourceBundle` phân tích cú pháp properties:

- Dòng trống bị bỏ qua.
- Comment bắt đầu bằng `#` hoặc `!` ở ký tự không phải whitespace đầu tiên.
- Key và value được phân tách bởi `=`, `:` hoặc whitespace chưa escape.
- Dấu gạch chéo ngược dùng để escape ký tự đặc biệt và hỗ trợ nối dòng.
- Unicode escape `\uXXXX` được diễn giải thành đơn vị mã UTF-16.
- Key phân biệt chữ hoa/chữ thường.

Ví dụ:

```properties
# Resource bundle tiếng Việt
button.save=Lưu
message.welcome=Chào mừng
currency=\u20AC
```

Khi dùng UTF-8, các ký tự tiếng Việt có thể được ghi trực tiếp. Unicode escape vẫn hữu ích khi cần biểu diễn dữ liệu theo định dạng ASCII hoặc duy trì tương thích với file cũ.

Không nhầm escape của properties với escape của Java string literal. Quy tắc parser properties được áp dụng bởi `PropertyResourceBundle`, bất kể byte đầu vào được giải mã bằng UTF-8 hay ISO-8859-1.

## 12. ResourceBundle cache và cập nhật file resource

`ResourceBundle.getBundle` cache các bundle đã nạp. Vì vậy, sửa file `.properties` trong lúc ứng dụng đang chạy không bảo đảm lần gọi `getBundle` tiếp theo đọc lại file ngay.

Trong ứng dụng cần chủ động làm mới bundle, có thể xóa cache phù hợp:

```java
ResourceBundle.clearCache();
```

Hoặc với class loader cụ thể:

```java
ResourceBundle.clearCache(MyApplication.class.getClassLoader());
```

`clearCache` xóa các bundle được cache theo phạm vi tương ứng; nó không sửa file resource và cũng không tự tạo nội dung mới. Sau đó, lần gọi `getBundle` tiếp theo mới thực hiện lại quá trình tìm/nạp theo cơ chế cache và loader hiện hành.

Trong ứng dụng production, resource bundle thường được đóng gói cùng ứng dụng và không thay đổi tại runtime. Không dùng việc sửa file trên đĩa như cơ chế cấu hình nóng nếu chưa thiết kế rõ cache, class loader và chiến lược reload.

## 13. Resource bundle trong named modules

Trên JDK hiện đại, resource bundle có thể nằm trong named module. Khi đó, quy tắc đóng gói resource và quyền truy cập của module cần được tính đến.

- Bundle nằm trong cùng module có thể được nạp bằng các overload `ResourceBundle.getBundle` phù hợp với caller module.
- Resource bundle trong named module có thể bị encapsulate; resource package cần được mở phù hợp để cơ chế tra cứu truy cập được.
- `ResourceBundle.Control` không được hỗ trợ khi gọi các overload `getBundle` có tham số Control từ named module; lời gọi đó ném `UnsupportedOperationException`.
- Nếu cần cung cấp bundle theo định dạng tùy chỉnh trong kiến trúc module, dùng cơ chế `ResourceBundleProvider` thay cho việc phụ thuộc `ResourceBundle.Control`.

Với ứng dụng classpath/unnamed module, các overload dùng `ClassLoader` và `ResourceBundle.Control` vẫn có thể được dùng theo hợp đồng của chúng. Không đưa ví dụ custom Control vào code chạy trong named module mà không kiểm tra giới hạn này.

## 14. Ví dụ hoàn chỉnh: nạp bundle tiếng Việt theo Locale

Giả sử resource nằm trong:

```text
src/main/resources/com/example/i18n/
    Messages.properties
    Messages_vi.properties
    Messages_vi_VN.properties
```

Code:

```java
import java.util.Locale;
import java.util.ResourceBundle;

public class MessageDemo {
    public static void main(String[] args) {
        Locale locale = Locale.forLanguageTag("vi-VN");

        ResourceBundle messages = ResourceBundle.getBundle(
                "com.example.i18n.Messages", locale);

        System.out.println("Bundle locale: " + messages.getLocale());
        System.out.println(messages.getString("app.title"));
        System.out.println(messages.getString("button.save"));
        System.out.println(messages.getString("message.welcome"));
    }
}
```

Nếu các file `.properties` được lưu bằng UTF-8, cơ chế mặc định trên JDK 18+ đọc chúng bằng UTF-8 theo quy tắc của PropertyResourceBundle. Nếu `Messages_vi_VN.properties` thiếu một key, giá trị có thể được lấy từ `Messages_vi.properties` hoặc bundle gốc.

Nếu chỉ có bundle gốc, `getBundle` có thể trả về bundle đó sau quá trình tìm kiếm và fallback. Hãy kiểm tra `messages.getLocale()` khi cần xác nhận chính xác bản dịch đã được chọn.

## 15. Ví dụ kiểm chứng InputStream fallback và Reader encoding

Có thể tạo bundle trực tiếp từ byte trong bộ nhớ để kiểm chứng hành vi constructor. Ví dụ sau dùng byte Latin-1 có `E9`, một byte không hợp lệ khi đứng riêng trong UTF-8:

```java
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.util.PropertyResourceBundle;

byte[] latin1 = {
        'g', 'r', 'e', 'e', 't', 'i', 'n', 'g', '=',
        'c', 'a', 'f', (byte) 0xE9
};

try (var input = new ByteArrayInputStream(latin1)) {
    PropertyResourceBundle bundle = new PropertyResourceBundle(input);
    System.out.println(bundle.getString("greeting")); // café
}
```

Với mặc định (không khóa `java.util.PropertyResourceBundle.encoding` thành `UTF-8` hoặc `ISO-8859-1`), UTF-8 decoder phát hiện byte `E9` malformed và PropertyResourceBundle đọc lại bằng ISO-8859-1. Ví dụ này chỉ minh họa fallback theo hợp đồng; với resource mới, nên lưu file UTF-8 thay vì dựa vào fallback.

Cùng dữ liệu nhưng nếu truyền Reader UTF-8, Reader sẽ quyết định decode và có thể báo lỗi malformed:

```java
import java.io.ByteArrayInputStream;
import java.io.InputStreamReader;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.PropertyResourceBundle;

var decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try (var reader = new InputStreamReader(
        new ByteArrayInputStream(latin1), decoder)) {
    PropertyResourceBundle bundle = new PropertyResourceBundle(reader);
}
```

Ở ví dụ thứ hai không có fallback ISO-8859-1 vì `PropertyResourceBundle(Reader)` không quyết định charset và không thử encoding khác. Lỗi decode đến từ Reader đã cấu hình `REPORT`.

## 16. Checklist khi rà soát lỗi ResourceBundle

1. Xác nhận tên `baseName`, vị trí resource và tên file theo Locale.
2. Kiểm tra có class bundle cùng tên đang che khuất file `.properties` không.
3. Xác định file `.properties` thực tế là UTF-8 hay ISO-8859-1; đừng đoán từ nội dung hiển thị.
4. Xác định ứng dụng dùng `ResourceBundle.getBundle`, `PropertyResourceBundle(InputStream)`, `PropertyResourceBundle(Reader)` hay `Properties.load`.
5. Nếu dùng InputStream constructor, hiểu UTF-8-first và fallback ISO-8859-1.
6. Nếu cần khóa encoding toàn tiến trình, cấu hình `java.util.PropertyResourceBundle.encoding` trước khi lớp được khởi tạo.
7. Nếu cần encoding riêng theo từng file, tạo Reader với charset đã biết rồi gọi constructor Reader.
8. Kiểm tra Locale thực tế bằng `getLocale()` và xác nhận key có thể đến từ bundle cha.
9. Kiểm tra cache nếu resource được thay đổi trong môi trường phát triển hoặc hệ thống có reload.
10. Với named modules, kiểm tra encapsulation và dùng `ResourceBundleProvider` khi cần provider tùy chỉnh.

## 17. Những nhận định dễ nhầm

- **“Java 18 mới khiến ResourceBundle properties dùng UTF-8.”** Sai. UTF-8 cho `PropertyResourceBundle(InputStream)` được đưa vào từ Java 9 theo JEP 226.
- **“ResourceBundle properties dùng cùng encoding với Properties.load(InputStream).”** Sai. `PropertyResourceBundle(InputStream)` UTF-8 trước và có fallback ISO-8859-1; `Properties.load(InputStream)` dùng ISO-8859-1 theo hợp đồng.
- **“Fallback ISO-8859-1 là tự nhận diện encoding.”** Sai. Fallback chỉ xảy ra khi UTF-8 malformed/unmappable; chuỗi byte Latin-1 tình cờ hợp lệ UTF-8 vẫn được đọc bằng UTF-8.
- **“Đặt system property encoding sau khi ứng dụng chạy sẽ đổi cách đọc.”** Sai. Property được đọc lúc `PropertyResourceBundle` khởi tạo.
- **“Constructor Reader cũng tự fallback giống InputStream.”** Sai. Reader đã quyết định charset; không có fallback trong constructor này.
- **“ResourceBundle.getBundle luôn trả đúng file locale yêu cầu.”** Không bảo đảm. Nó có thể chọn locale ít cụ thể hơn hoặc fallback theo default Locale và bundle gốc.
- **“Thiếu key trong file locale là MissingResourceException ngay.”** Không nhất thiết. ResourceBundle tìm key trong parent bundle trước.
- **“Sửa file properties thì getBundle lập tức đọc lại.”** Sai. Bundle được cache; cần chiến lược cache/reload phù hợp.
- **“Có thể dùng ResourceBundle.Control trong mọi ứng dụng module.”** Sai. Các overload nhận Control không được hỗ trợ trong named modules; dùng ResourceBundleProvider cho cơ chế provider.

## 18. Tài liệu tham khảo chính thức

- [PropertyResourceBundle — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/PropertyResourceBundle.html): constructor InputStream/Reader, UTF-8-first, fallback ISO-8859-1 và system property encoding.
- [ResourceBundle — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ResourceBundle.html): `getBundle`, candidate Locale, parent chain, fallback và cache.
- [ResourceBundle.Control — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ResourceBundle.Control.html): thứ tự format, candidate locale, giới hạn trong named modules và `ResourceBundleProvider`.
- [JEP 226 — UTF-8 Properties Files](https://openjdk.org/jeps/226): thay đổi encoding cho property resource bundles từ Java 9.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): phạm vi thay đổi default charset từ Java 18; phân biệt với hợp đồng riêng của ResourceBundle.
- [Internationalization Enhancements in JDK 9 — UTF-8 Properties Files](https://docs.oracle.com/javase/9/intl/internationalization-enhancements-jdk-9.htm): mô tả tương thích và fallback cho file properties bản địa hóa.

