# Phân biệt `PropertyResourceBundle` với `Properties.load` (Java 9+)

## 1. Hai API đọc cùng dạng tệp nhưng giải quyết hai nhu cầu khác nhau

Tệp `.properties` thường chứa các cặp `key=value`, ví dụ `welcome=Xin chào`. Tuy nhiên, việc cả hai API đều hiểu cú pháp này **không** có nghĩa chúng tự xử lý ngôn ngữ (`Locale`) giống nhau.

- `PropertyResourceBundle` là một triển khai của `ResourceBundle` dành cho dữ liệu đọc từ tệp properties. Khi được nạp thông qua `ResourceBundle.getBundle(baseName, locale)`, nó tham gia cơ chế tìm bản dịch theo `Locale`, nối với bundle cha để tìm khóa thiếu và sử dụng bộ nhớ đệm của `ResourceBundle`.
- `Properties` là cấu trúc ánh xạ thuộc tính có thể thay đổi. Các phương thức `load(InputStream)` và `load(Reader)` **chỉ đọc dữ liệu từ luồng được truyền vào** để thêm/cập nhật các khóa trong đối tượng; chúng không tự chọn tệp dựa trên `Locale`, không tự tìm `messages_vi.properties` và không tự liên kết bản dịch theo vùng/ngôn ngữ.

**Điểm mấu chốt:** Sự khác biệt về lựa chọn bản dịch và cơ chế dự phòng đến từ `ResourceBundle.getBundle` cùng chuỗi bundle cha. Tự tạo `new PropertyResourceBundle(stream)` chỉ đọc **một** tệp, không tự tìm tệp theo `Locale`.

## 2. Bảng so sánh thực tế

| Tiêu chí | `PropertyResourceBundle` / `ResourceBundle.getBundle` | `Properties.load` |
|---|---|---|
| Mục đích chính | Văn bản giao diện, thông báo và tài nguyên theo ngôn ngữ/vùng | Cấu hình hoặc các cặp khóa–giá trị do ứng dụng tự quản lý |
| Đối tượng dùng để đọc | `ResourceBundle` hoặc `PropertyResourceBundle` | `Properties` |
| Chọn tệp theo `Locale` | **Có**, khi dùng `ResourceBundle.getBundle` với base name và locale | **Không**; người gọi tự mở đường dẫn/luồng |
| Dự phòng khóa thiếu | Có thể tra bundle cha khi nạp bằng `getBundle` | Trả `null`/giá trị mặc định khi dùng `getProperty`; có thể tự tạo chuỗi `Properties` mặc định nhưng không gắn với locale |
| API lấy chuỗi | `getString("key")` | `getProperty("key")` |
| Khóa không tìm thấy | `getString` ném `MissingResourceException` nếu không có ở cả chuỗi bundle | `getProperty` trả `null` (hoặc tham số mặc định nếu cung cấp) |
| Thay đổi dữ liệu trong bộ nhớ | Không có API `setProperty` trên bundle được nạp | Có `setProperty`, `remove`, `clear`; `load` có thể ghi đè khóa đang tồn tại |
| Bộ nhớ đệm khi tra tài nguyên | `ResourceBundle.getBundle` có cơ chế cache | `Properties.load` không tự cache theo base name/locale |
| Nguồn dữ liệu | Tệp `.properties` đặt trong đường dẫn tài nguyên hoặc luồng/reader khi tạo trực tiếp | Bất kỳ luồng/reader do người gọi mở, miễn dữ liệu đúng cú pháp properties |

Hai loại đều sử dụng quy tắc cơ bản của tệp `.properties`: khóa/giá trị, dấu `=` hoặc `:`, dòng chú thích `#`/`!`, ký tự thoát như `\n` và `\uXXXX`. Khả năng hiểu cú pháp giống nhau **không quyết định** cách giải mã các byte.

## 3. Điểm khác biệt dễ gây lỗi nhất từ Java 9: encoding

Đối với một tệp **được lưu thật sự bằng UTF-8**, hành vi nạp khác nhau tùy overload:

| Cách đọc | Cách giải mã áp dụng hiện nay |
|---|---|
| `new PropertyResourceBundle(InputStream)` | Mặc định thử **UTF-8**; nếu gặp chuỗi byte UTF-8 không hợp lệ, thử đọc lại bằng **ISO-8859-1** |
| `ResourceBundle.getBundle(...)` tìm thấy tệp `.properties` | Thông thường sử dụng `PropertyResourceBundle` và cùng quy tắc UTF-8 mặc định của nó |
| `new PropertyResourceBundle(Reader)` | Dùng các ký tự đã được `Reader` giải mã; người gọi chọn charset cho reader |
| `properties.load(InputStream)` | **Luôn** diễn giải byte theo **ISO-8859-1**; không tự áp dụng UTF-8 chỉ vì chương trình chạy trên Java 9+ |
| `properties.load(Reader)` | Dùng các ký tự đã được `Reader` giải mã; người gọi có thể chọn UTF-8 |

Từ Java 9, tệp resource bundle dạng properties có thể ghi trực tiếp `message=Tiếng Việt` bằng UTF-8. Thay đổi này **không** làm `Properties.load(InputStream)` chuyển sang UTF-8. Nếu đưa byte UTF-8 cho overload `load(InputStream)`, các dấu tiếng Việt có thể biến thành văn bản sai mã hóa (*mojibake*).

Cách đọc cấu hình UTF-8 rõ ràng:

```java
Properties props = new Properties();
try (Reader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    props.load(reader);
}
```

Đoạn trên là **mảnh mã minh họa**; `path` là biến `Path` đã được tạo, các lớp `Files`, `Reader`, `StandardCharsets`, `Properties` cần import. Một chương trình hoàn chỉnh nằm ở mục 4.

### Khi nào cần ép encoding của bundle?

Có thể đặt thuộc tính JVM `java.util.PropertyResourceBundle.encoding` bằng chính xác `UTF-8` hoặc `ISO-8859-1`. Khi đó `PropertyResourceBundle(InputStream)` chỉ dùng encoding đã chọn, không thử mã hóa còn lại. Ví dụ, để phát hiện tệp resource không hợp lệ UTF-8 ngay khi nạp:

```bash
java -Djava.util.PropertyResourceBundle.encoding=UTF-8 -cp . BundleVsProperties
```

Thuộc tính này được đánh giá khi lớp `PropertyResourceBundle` được khởi tạo, nên hãy đặt **trước lúc JVM khởi chạy**, không chờ đến sau khi bundle đã được sử dụng. Nó không thay đổi hành vi của `Properties.load(InputStream)`. Nếu tự truyền `Reader`, charset đã được quyết định bởi reader và bạn không cần dựa vào thuộc tính trên.

**Lưu ý:** Cơ chế thử lại ISO-8859-1 chỉ xảy ra khi byte UTF-8 không hợp lệ. Nó không thể tự phát hiện mọi trường hợp tệp được lưu với encoding không mong muốn nhưng byte vẫn hợp lệ; vì vậy, dự án nên thống nhất lưu bản dịch bằng UTF-8 và kiểm tra chất lượng bản dịch.

## 4. Ví dụ chạy được: ba cách đọc cùng một bản dịch

Ví dụ này chạy trên **Java 9+** mà không cần thư viện bên ngoài. Đặt cả ba tệp vào **cùng một thư mục**, và chạy lệnh từ chính thư mục đó:

```text
demo/
├── BundleVsProperties.java
├── messages.properties
└── messages_vi.properties
```

**Tệp `messages.properties`** — giá trị gốc:

```properties
welcome=Hello
bye=Goodbye
```

**Tệp `messages_vi.properties`** — bản dịch tiếng Việt; cố ý thiếu `bye` để quan sát cơ chế dự phòng:

```properties
welcome=Xin chào
```

Lưu hai tệp bằng UTF-8. **Tệp `BundleVsProperties.java`**:

```java
import java.io.InputStream;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Locale;
import java.util.Properties;
import java.util.PropertyResourceBundle;
import java.util.ResourceBundle;

public class BundleVsProperties {
    public static void main(String[] args) throws Exception {
        Locale vietnamese = Locale.forLanguageTag("vi");

        // Cách 1: Tìm theo tên gốc + Locale và tra khóa trong bundle cha.
        ResourceBundle bundle =
                ResourceBundle.getBundle("messages", vietnamese);

        System.out.println("bundle.welcome=" + bundle.getString("welcome"));
        System.out.println("bundle.bye=" + bundle.getString("bye"));
        System.out.println("bundle.locale=" + bundle.getLocale().toLanguageTag());

        Path file = Paths.get("messages_vi.properties");

        // Cách 2: Tạo trực tiếp một bundle từ MỘT tệp.
        try (InputStream in = Files.newInputStream(file)) {
            PropertyResourceBundle direct = new PropertyResourceBundle(in);
            System.out.println("direct.welcome=" + direct.getString("welcome"));
            System.out.println("direct.hasBye=" + direct.containsKey("bye"));
        }

        // Cách 3: Properties.load với Reader UTF-8 rõ ràng.
        Properties props = new Properties();
        try (Reader reader = Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
            props.load(reader);
        }

        System.out.println("props.welcome=" + props.getProperty("welcome"));
        System.out.println("props.bye=" + props.getProperty("bye"));

        // So sánh overload InputStream: vẫn giải mã ISO-8859-1.
        Properties byteMode = new Properties();
        try (InputStream in = Files.newInputStream(file)) {
            byteMode.load(in);
        }
        System.out.println("props.byteModeUtf8Correct="
                + "Xin chào".equals(byteMode.getProperty("welcome")));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 BundleVsProperties.java
java -cp . BundleVsProperties
```

Kết quả chuẩn với ba tệp đúng như trên:

```text
bundle.welcome=Xin chào
bundle.bye=Goodbye
bundle.locale=vi
direct.welcome=Xin chào
direct.hasBye=false
props.welcome=Xin chào
props.bye=null
props.byteModeUtf8Correct=false
```

**Giải thích từng điểm:**

1. `ResourceBundle.getBundle("messages", vi)` tìm `messages_vi.properties` và ghép với `messages.properties` làm bundle cha. Khóa `welcome` được lấy từ bản tiếng Việt; khóa `bye` không có ở bản tiếng Việt nên được lấy từ bundle gốc.
2. `new PropertyResourceBundle(in)` chỉ biết nội dung của `messages_vi.properties`. Nó đọc UTF-8 đúng nhưng **không tự nối** với `messages.properties`; do đó `containsKey("bye")` là `false`.
3. `Properties.load(Reader)` đọc đúng dấu nhờ reader UTF-8, nhưng cũng chỉ thấy một tệp. `getProperty("bye")` trả `null`.
4. `Properties.load(InputStream)` nhận cùng byte UTF-8 nhưng diễn giải theo ISO-8859-1; giá trị có dấu không khớp với `"Xin chào"` nên phép so sánh trả `false`.

Vì `messages*.properties` nằm trên classpath của lệnh `java -cp .`, `ResourceBundle.getBundle` mới tìm thấy được chúng. Ở dự án Maven/Gradle, các tệp tương tự thường nằm trong `src/main/resources` và được hệ thống build đưa vào classpath khi chạy; `Properties.load` thì vẫn yêu cầu bạn tự cung cấp stream/reader.

## 5. Cơ chế chọn bundle và dự phòng: hiểu đúng giới hạn

Giả sử có `messages.properties`, `messages_vi.properties`, `messages_vi_VN.properties`. Khi tra cho `vi-VN`, `ResourceBundle.getBundle` ưu tiên biến thể cụ thể hơn rồi xem những ứng viên ít cụ thể hơn; khóa thiếu có thể lấy từ bundle cha tương ứng. Khi không tìm được bundle phù hợp, thuật toán mặc định còn có thể thử **locale mặc định của JVM**, sau đó bundle gốc. Không được mặc định rằng request `vi-VN` chắc chắn trả về dữ liệu tiếng Việt: hãy dùng `bundle.getLocale()` khi cần biết locale thực tế đã chọn.

Ngược lại, với `Properties`, người gọi phải tự quyết định tệp nào được đọc, thứ tự nạp và quy tắc dự phòng. Bạn có thể tạo `new Properties(defaults)` để cung cấp giá trị thuộc tính mặc định; đó là cơ chế **giá trị mặc định theo khóa**, không phải thuật toán tìm bản dịch theo `Locale`.

Hai tình huống thường bị nhầm:

- `new PropertyResourceBundle(reader)` **không** tìm thêm tệp `messages_vi_VN.properties` hay `messages.properties`. Để tận dụng lựa chọn locale tự động, dùng `ResourceBundle.getBundle`.
- `ResourceBundle.getBundle` có thể chọn một lớp `ResourceBundle` chuyên biệt thay vì tệp `.properties` nếu lớp phù hợp tồn tại. Do đó, không phải mọi `ResourceBundle` đều nhất thiết là `PropertyResourceBundle`, dù ví dụ hiện tại dùng tệp properties.

Trong **named module** (Java Platform Module System), cách đóng gói và khả năng truy cập resource cần tuân theo quy tắc module. Java cung cấp các overload `ResourceBundle.getBundle(..., Module)` và cơ chế provider khi cần; tránh áp dụng máy móc ví dụ classpath cho một module có đóng gói tài nguyên riêng. Các overload nhận `ResourceBundle.Control` không được hỗ trợ khi lời gọi xuất phát từ named module.

## 6. Chọn API nào trong mã nguồn?

**Chọn `ResourceBundle.getBundle(baseName, locale)`** khi văn bản cần thay đổi theo ngôn ngữ/vùng: giao diện người dùng, bản dịch thông báo, nhãn hoặc nội dung được địa phương hóa. Đặt tên tệp nhất quán (`messages.properties`, `messages_vi.properties`, ...), có bundle gốc đủ khóa cần thiết và giữ cùng một khóa giữa các ngôn ngữ.

**Chọn `Properties.load(Reader)`** khi dữ liệu là cấu hình thông thường: tên máy chủ, timeout, cờ tính năng, giá trị thiết lập. Bạn kiểm soát nguồn tệp, charset, cách xử lý lỗi và có thể thay đổi các khóa sau khi nạp. Với dữ liệu UTF-8, truyền `Reader` dùng `StandardCharsets.UTF_8` thay vì dùng trực tiếp overload `InputStream`.

**Chọn `new PropertyResourceBundle(InputStream/Reader)` trực tiếp** khi đã có một tệp properties cụ thể và muốn sử dụng giao diện đọc `ResourceBundle`, nhưng **không cần** cơ chế tự chọn locale/cha từ `getBundle`.

### Lỗi phổ biến cần tránh

1. **Nhầm Java 9 đã đổi `Properties.load(InputStream)` sang UTF-8.** Thực tế overload này vẫn diễn giải ISO-8859-1.
2. **Chỉ tạo `PropertyResourceBundle` rồi chờ tự fallback.** Tạo trực tiếp không tự xây chuỗi bundle cha; phải dùng `ResourceBundle.getBundle` để có cơ chế lựa chọn theo locale chuẩn.
3. **Cho rằng khóa thiếu luôn trả `null`.** `ResourceBundle.getString` ném `MissingResourceException` nếu không có khóa trong cả chuỗi; `Properties.getProperty` có thể trả `null`.
4. **Nhầm `ResourceBundle.getBundle` tìm theo thư mục làm việc.** Nó tìm resource qua cơ chế classpath/module; ví dụ chỉ dùng thư mục làm việc vì thư mục đó cũng là classpath khi chạy `-cp .`.
5. **Dùng tên khóa khác nhau giữa các bản dịch.** Cơ chế tìm bundle có thể chọn đúng ngôn ngữ nhưng vẫn không tìm được một khóa bị viết sai; hãy kiểm tra đầy đủ key khi thêm bản dịch.
6. **Sửa file bản dịch lúc chương trình đang chạy rồi mong thấy ngay.** `ResourceBundle.getBundle` có cache; quy trình phát hành nên đóng gói lại tài nguyên, hoặc quản lý việc làm mới cache một cách có chủ đích.

## 7. Tự kiểm tra kiến thức

- Một tệp `messages_vi.properties` lưu UTF-8 chứa `welcome=Xin chào`. Đọc bằng `Properties.load(new FileInputStream(...))` có đảm bảo đúng dấu không? **Không**: overload byte-stream dùng ISO-8859-1. Dùng reader UTF-8.
- Vì sao `ResourceBundle.getBundle("messages", vi)` đọc được `bye=Goodbye` dù bản tiếng Việt không có? **Vì** chuỗi bundle cha cho phép tìm khóa trong bundle gốc.
- Vì sao `new PropertyResourceBundle(stream)` không tìm được `bye` ở cùng ví dụ? **Vì** nó chỉ đọc tệp được truyền trực tiếp, không tự nối bundle cha.
- Nếu mục tiêu chỉ là nạp file cấu hình UTF-8 tự chọn đường dẫn, có cần `ResourceBundle` không? **Không**: `Properties.load(Reader)` là lựa chọn phù hợp.

## Tài liệu API

- [`PropertyResourceBundle` — Java SE API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/PropertyResourceBundle.html)
- [`Properties` — Java SE API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Properties.html)
- [`ResourceBundle` — Java SE API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/ResourceBundle.html)
- [JEP 226 — UTF-8 Property Resource Bundles](https://openjdk.org/jeps/226)
