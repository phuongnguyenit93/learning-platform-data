# PropertyResourceBundle đọc dữ liệu UTF-8 (Java 9 trở lên)

## 1. Mục tiêu và ngữ cảnh

`PropertyResourceBundle` là lớp thuộc `java.util`, kế thừa `ResourceBundle`, dùng các tệp `.properties` để lưu chuỗi theo ngôn ngữ/vùng miền (`Locale`). Ứng dụng thường gọi `ResourceBundle.getBundle(baseName, locale)`; Java tìm tệp thích hợp và tự tạo `PropertyResourceBundle` khi nguồn là `.properties`. Mỗi khóa (`key`) ánh xạ tới một chuỗi (`value`); tên khóa phân biệt chữ hoa, chữ thường.

**Quy tắc đang áp dụng từ Java 9 đến các JDK hiện đại:** khi dữ liệu được đọc qua `PropertyResourceBundle(InputStream)`, Java ưu tiên giải mã **UTF-8**. Vì vậy có thể viết trực tiếp tiếng Việt và nhiều ngôn ngữ khác trong tệp `.properties` lưu bằng UTF-8, không cần chuyển từng ký tự có dấu thành Unicode escape. Đây là quy tắc riêng của *property resource bundle*, không phải quy tắc chung cho mọi API đọc `.properties`.

## 2. Cách đọc và cơ chế tương thích

| Đường đọc | Cách xử lý mã hóa hiện hành |
| --- | --- |
| `ResourceBundle.getBundle("messages", locale)` với tệp `messages*.properties` | Java tìm bundle theo locale; khi tải bundle từ tệp, dùng cơ chế `PropertyResourceBundle`, ưu tiên UTF-8. |
| `new PropertyResourceBundle(InputStream)` | Mặc định thử UTF-8. Nếu gặp chuỗi byte UTF-8 không hợp lệ, đọc lại bằng ISO-8859-1. |
| `new PropertyResourceBundle(Reader)` | Ký tự đã được `Reader` giải mã; cách chọn charset thuộc về nơi tạo `Reader`, không có bước tự thử lại như constructor nhận `InputStream`. |
| `new Properties().load(InputStream)` | **Vẫn** đọc theo ISO-8859-1; không được đồng nhất với `PropertyResourceBundle`. Muốn đọc UTF-8 bằng `Properties`, sử dụng `load(Reader)` với charset UTF-8. |

Trong chế độ mặc định của constructor nhận `InputStream`:

1. Byte của tệp được giải mã theo UTF-8.
2. Nếu bộ giải mã phát hiện `MalformedInputException` hoặc `UnmappableCharacterException`, Java quay lại và đọc bằng ISO-8859-1.
3. Nếu UTF-8 hợp lệ, Java **không** kiểm tra xem văn bản “trông có đúng ngôn ngữ” hay không; dữ liệu sai nhưng vẫn là UTF-8 hợp lệ có thể không được phát hiện.

Bước đọc lại bằng ISO-8859-1 hiện vẫn tồn tại để tương thích dữ liệu cũ; **đối với nội dung mới, hãy thống nhất UTF-8**. Việc tự đọc file bằng `Files.readString` hoặc `Properties.load(InputStream)` rồi tự dựng chuỗi là một đường xử lý khác, không tự động hưởng quy tắc này.

### Kiểm soát mã hóa khi khởi động JVM

Có thể đặt system property `java.util.PropertyResourceBundle.encoding` trước khi khởi tạo lớp:

```bash
java -Djava.util.PropertyResourceBundle.encoding=UTF-8 -cp . Main
```

- `UTF-8`: chỉ đọc theo UTF-8; byte không hợp lệ gây lỗi giải mã, không tự chuyển sang ISO-8859-1. Trong luồng tải bundle bằng `ResourceBundle.getBundle`, lỗi có thể được phản ánh qua ngoại lệ tải bundle và nguyên nhân đi kèm.
- `ISO-8859-1`: ép đọc theo mã hóa đó (chỉ nên dùng khi thực sự cần xử lý nguồn có mã hóa tương ứng).
- Giá trị khác hai tên trên bị bỏ qua. Property được đọc khi `PropertyResourceBundle` khởi tạo lần đầu, vì vậy đổi bằng `System.setProperty` sau khi lớp đã khởi tạo không có tác dụng.

**Thực hành được khuyến nghị:** lưu tài nguyên dưới UTF-8; nếu muốn phát hiện tệp sai mã hóa sớm, bật tùy chọn ép `UTF-8` ngay lúc chạy. Không cần dựa vào `-Dfile.encoding=UTF-8` để thay đổi cách `PropertyResourceBundle` giải mã tài nguyên.

## 3. Ví dụ chạy được trên Java 17+

Tạo bốn tệp trong **cùng một thư mục**, tất cả tệp văn bản được lưu UTF-8:

```text
demo/
├── Main.java
├── messages.properties
├── messages_vi.properties
└── messages_vi_VN.properties
```

Tệp `messages.properties` là bundle gốc:

```properties
greeting=Hello
title=Java lesson
thanks=Thank you
```

Tệp `messages_vi.properties` chứa phần dịch chung cho tiếng Việt:

```properties
greeting=Xin chào
thanks=Cảm ơn
```

Tệp `messages_vi_VN.properties` ghi đè phần riêng cho Việt Nam:

```properties
title=Học Java bằng tiếng Việt
```

Tệp `Main.java`:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import java.util.PropertyResourceBundle;
import java.util.ResourceBundle;

public class Main {
    public static void main(String[] args) throws Exception {
        Locale locale = Locale.forLanguageTag("vi-VN");
        ResourceBundle messages = ResourceBundle.getBundle("messages", locale);

        System.out.println(messages.getString("greeting"));
        System.out.println(messages.getString("title"));
        System.out.println(messages.getString("thanks"));
        System.out.println(messages.getLocale().toLanguageTag());

        try (InputStream input = Files.newInputStream(Path.of("messages_vi.properties"))) {
            PropertyResourceBundle direct = new PropertyResourceBundle(input);
            System.out.println("Trực tiếp: " + direct.getString("greeting"));
        }
    }
}
```

Trong thư mục `demo`, biên dịch và chạy:

```bash
javac -encoding UTF-8 Main.java
java -Djava.util.PropertyResourceBundle.encoding=UTF-8 -cp . Main
```

Kết quả khi terminal hiển thị Unicode đúng:

```text
Xin chào
Học Java bằng tiếng Việt
Cảm ơn
vi-VN
Trực tiếp: Xin chào
```

Giải thích:

- `getBundle("messages", vi-VN)` chọn `messages_vi_VN.properties`. Khóa `title` lấy từ tệp đó; khóa `greeting` và `thanks` không có trong bundle `vi_VN` nên tìm tiếp ở bundle cha `messages_vi.properties`.
- `messages.properties` cung cấp các khóa dự phòng của bundle gốc. Khi không có bản dịch ở các cấp phù hợp, `ResourceBundle` có cơ chế tìm bundle khác theo locale mặc định và bundle gốc; không nên giả định mọi yêu cầu không khớp đều trực tiếp rơi xuống tệp gốc.
- `messages.getLocale()` cho biết locale của **bundle được chọn** (ở đây `vi-VN`), không phải thông tin về encoding.
- `new PropertyResourceBundle(input)` trực tiếp đọc một tệp theo cơ chế UTF-8; constructor này **không tự xây chuỗi bundle cha** như `ResourceBundle.getBundle`.
- Tham số `-encoding UTF-8` của `javac` áp dụng cho **mã nguồn Java**; tham số `-Djava.util.PropertyResourceBundle.encoding=UTF-8` áp dụng cho cách đọc **property resource bundle**. Đây là hai mục đích khác nhau.

Với dự án Gradle/Maven thông thường, đặt các tệp `messages*.properties` dưới `src/main/resources/` để chúng được đóng gói vào classpath; `baseName` vẫn là `messages` khi tài nguyên nằm ở gốc resources. Nếu lưu dưới `src/main/resources/i18n/`, dùng `ResourceBundle.getBundle("i18n.messages", locale)`.

## 4. Khi nào cần Reader và khi nào dùng Properties?

Nếu nhận được tệp từ một nguồn ngoài và cần chỉ định chính xác charset tại điểm mở tệp, dùng constructor nhận `Reader`:

```java
// Đặt trong một phương thức có xử lý IOException hoặc khai báo throws.
try (var reader = Files.newBufferedReader(
        Path.of("messages_vi.properties"),
        java.nio.charset.StandardCharsets.UTF_8)) {
    PropertyResourceBundle bundle = new PropertyResourceBundle(reader);
    System.out.println(bundle.getString("greeting")); // Xin chào
}
```

`Files.newBufferedReader` mặc định cũng dùng UTF-8 trong các JDK hiện đại; truyền `StandardCharsets.UTF_8` ở đây để ý định mã hóa hiển nhiên. `Reader` đã chuyển byte thành ký tự trước khi `PropertyResourceBundle` phân tích cấu trúc `key=value`.

Nếu chỉ cần cấu hình dạng key/value, **không cần chọn theo locale**, `Properties` là API khác. Tránh giả định `Properties.load(InputStream)` đã chuyển sang UTF-8:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

Properties p = new Properties();
try (var reader = Files.newBufferedReader(
        Path.of("messages_vi.properties"), StandardCharsets.UTF_8)) {
    p.load(reader);
}
System.out.println(p.getProperty("greeting")); // Xin chào
```

Đoạn `Properties` trên là mã **minh họa dùng trong một phương thức**, không phải một tệp `.java` độc lập. Khi ứng dụng cần đa ngôn ngữ, chuỗi bundle cha và lựa chọn locale, ưu tiên `ResourceBundle`.

## 5. Quy tắc tệp .properties cần nhớ

- Dùng cú pháp `key=value` (hoặc dấu `:` làm dấu phân cách); dòng bắt đầu bằng `#` hoặc `!` là chú thích. Khóa phân biệt chữ hoa/chữ thường, nên `hello` và `Hello` là hai khóa khác nhau.
- Những escape như `\n`, `\t`, `\\` và `\u00E9` vẫn có ý nghĩa theo cú pháp Java properties; **UTF-8 không tắt cơ chế escape**. Một ký tự `\` trong đường dẫn Windows phải được escape phù hợp nếu muốn giữ nguyên.
- Tệp UTF-8 có thể chứa trực tiếp `Xin chào`, `Tiếng Việt`, `日本語`...; không cần chuyển chữ có dấu thành chuỗi `\u....` cho mục đích tương thích JDK hiện hành.
- Không trộn mã hóa giữa các tệp trong cùng một bundle. Thiết lập editor và pipeline build để lưu `.properties` bằng UTF-8, đồng thời bảo đảm tài nguyên xuất hiện đúng trên runtime classpath.
- `ResourceBundle` có cache. Khi đổi tệp bên ngoài trong lúc ứng dụng đang chạy, việc gọi lại `getBundle` có thể dùng bản đã cache; việc phát hành tài nguyên nên có chiến lược nạp lại rõ ràng, không kỳ vọng nó tự cập nhật ngay.

## 6. Lỗi phổ biến và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Tiếng Việt thành `Xin chÃ o` hoặc ký tự lạ | File không đúng UTF-8 hoặc đã bị giải mã sai ở một bước khác; fallback ISO-8859-1 có thể che lỗi byte | Kiểm tra encoding thực tế; lưu lại UTF-8; chạy với `-Djava.util.PropertyResourceBundle.encoding=UTF-8` để phát hiện byte sai chuẩn. |
| `MissingResourceException` khi lấy bundle | Sai `baseName`, tên file, thư mục trên classpath, hoặc không có bundle phù hợp | Kiểm tra `messages_vi_VN.properties` và vị trí resources; duy trì bundle gốc `messages.properties` khi thích hợp. |
| `MissingResourceException` khi lấy một key | Khóa sai tên hoặc không tồn tại ở bundle hiện tại và các bundle cha | Kiểm tra chuỗi khóa chính xác và bản dịch thiếu, có thể dùng `containsKey`. |
| Chỉnh file mà kết quả chưa đổi | `ResourceBundle` đang dùng cache hoặc resource đã đóng gói sẵn | Kiểm tra tài nguyên thực sự trên classpath; nếu cơ chế nạp lại là yêu cầu của ứng dụng, thiết kế làm mới cache một cách chủ động. |
| `Properties.load(InputStream)` cho kết quả khác `PropertyResourceBundle` | Hai API có quy tắc mã hóa khác nhau | Với `Properties`, dùng `load(Reader)` và charset UTF-8. |
| Chỉ nhìn lỗi tiếng Việt trên console | Terminal có thể hiển thị sai dù chuỗi Java đã được đọc đúng | Xác minh charset của terminal và so sánh nội dung chuỗi trong debugger/test trước khi sửa file. |

## 7. Tự kiểm tra kiến thức

1. Vì sao `PropertyResourceBundle(InputStream)` có thể đọc trực tiếp chữ “Cảm ơn” trong tệp UTF-8 trên Java 17+?
2. Nếu UTF-8 có byte không hợp lệ, behavior mặc định khác gì khi khởi động JVM bằng `-Djava.util.PropertyResourceBundle.encoding=UTF-8`?
3. `ResourceBundle.getBundle` khác `new PropertyResourceBundle(input)` ở điểm nào về chọn locale và bundle cha?
4. Vì sao không nên dùng `Properties.load(InputStream)` để kết luận mọi tệp `.properties` trong Java đều mặc định UTF-8?
5. Khi có `messages_vi_VN.properties` chỉ chứa `title`, vì sao vẫn lấy được `greeting` từ `messages_vi.properties`?

**Ghi nhớ:** từ Java 9 trở lên, `PropertyResourceBundle` ưu tiên UTF-8; dùng `ResourceBundle.getBundle` cho i18n theo locale, chọn UTF-8 thống nhất cho dữ liệu mới, và chỉ định encoding rõ ràng khi cần phát hiện lỗi. Quy tắc của `Properties.load(InputStream)` vẫn là ISO-8859-1.

## Tài liệu chính thức

- [JDK 21 — PropertyResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/PropertyResourceBundle.html): constructor `InputStream`/`Reader` và quy tắc mã hóa.
- [JDK 21 — ResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ResourceBundle.html): chọn locale, chuỗi bundle cha, cache và lỗi không tìm thấy tài nguyên.
- [JDK 21 — Properties](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Properties.html): khác biệt giữa `load(InputStream)` và `load(Reader)`.
