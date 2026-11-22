# UTF-8 của PropertyResourceBundle và cơ chế đọc lại ISO-8859-1

Khi ứng dụng Java đọc tài nguyên bản địa hóa từ file `.properties`, việc **lưu file bằng mã hóa nào** quyết định liệu các chữ như `Tiếng Việt`, `café`, `日本語` có được hiển thị chính xác hay không. Từ **Java 9**, `java.util.PropertyResourceBundle` đổi cách đọc từ `InputStream`: **ưu tiên UTF-8** và, theo mặc định, **đọc lại bằng ISO-8859-1 nếu gặp lỗi giải mã UTF-8**. Đây là hành vi tương thích với những bundle cũ, không phải bộ phát hiện chính xác mọi mã hóa.

Bài này giải thích quy tắc, lúc nào fallback xảy ra, giới hạn của nó, cách kiểm soát bằng system property `java.util.PropertyResourceBundle.encoding`, sự khác biệt giữa `InputStream` và `Reader`, ví dụ Java 17+ chạy được, và cách tổ chức tài nguyên i18n để tránh chữ bị lỗi.

## 1. Vì sao file .properties có vấn đề về mã hóa?

File `.properties` được lưu thành **byte** trên đĩa; Java phải chuyển các byte ấy thành **ký tự Unicode**. Các bảng mã khác nhau có thể biểu diễn cùng ký tự bằng những dãy byte khác nhau:

| Ký tự | UTF-8 (hex) | ISO-8859-1 (hex) | Ý nghĩa |
| --- | --- | --- | --- |
| `A` | `41` | `41` | ASCII trùng nhau trong hai mã hóa |
| `é` (U+00E9) | `C3 A9` | `E9` | Một ký tự, hai cách mã hóa |
| `à` (U+00E0) | `C3 A0` | `E0` | Các dấu tiếng Việt cơ bản có thể khác cách biểu diễn |
| `ệ` (U+1EC7) | `E1 BB 87` | Không biểu diễn trực tiếp được | ISO-8859-1 không bao phủ toàn bộ tiếng Việt |
| `日` (U+65E5) | `E6 97 A5` | Không biểu diễn trực tiếp được | UTF-8 hỗ trợ mọi ký tự Unicode hợp lệ |

Nếu đọc **byte `E9`** bằng UTF-8, đây không phải một chuỗi UTF-8 hợp lệ đứng một mình; quá trình giải mã có thể phát sinh `MalformedInputException`. Nhưng byte `E9` lại là một ký tự hợp lệ trong ISO-8859-1: `é`.

Ngược lại, byte `C3 A9` là UTF-8 hợp lệ của `é`, đồng thời cũng là hai ký tự ISO-8859-1: `Ã©`. Vì vậy, **không phải lúc nào dữ liệu “đọc được” cũng là dữ liệu được đọc đúng mã hóa ban đầu**. Điểm này rất quan trọng khi đánh giá cơ chế fallback.

### Bối cảnh thay đổi giữa Java 8 và Java 9+

Ở các bản Java cũ, bundle dạng `.properties` theo `PropertyResourceBundle(InputStream)` truyền thống được đọc theo ISO-8859-1; ký tự vượt phạm vi bảng mã này phải viết bằng **Unicode escape** như `\u1EC7`. [JEP 226 — UTF-8 Property Resource Bundles](https://openjdk.org/jeps/226) đưa vào Java 9 cơ chế **UTF-8 trước, ISO-8859-1 dự phòng** cho đường đọc từ `InputStream`. Vì thế, với **Java 17+**, ta thường có thể viết trực tiếp tiếng Việt trong file `messages_vi.properties` đã được lưu bằng UTF-8.

Thay đổi này không có nghĩa là **tất cả API đọc properties** đều mặc định UTF-8. Cần phân biệt chính xác class và overload đang sử dụng.

## 2. Quy tắc của PropertyResourceBundle(InputStream)

Với mặc định Java 17+ và không ép mã hóa bằng system property, luồng xử lý có thể hình dung như sau:

```text
File bundle .properties (byte)
          |
          v
PropertyResourceBundle(InputStream)
          |
          v
Thử giải mã TOÀN BỘ stream bằng UTF-8
          |
          +-- Hợp lệ -------------> parse key=value bằng UTF-8
          |
          +-- MalformedInputException /
          |   UnmappableCharacterException
          v
Khôi phục trạng thái trước lần thử
          |
          v
Đọc lại TOÀN BỘ stream bằng ISO-8859-1
          |
          v
Parse key=value theo ký tự đã giải mã
```

Đây là hành vi **đọc lại stream**, không phải lấy riêng ký tự bị lỗi rồi chuyển một vài byte sang bảng mã khác. Khi UTF-8 thất bại, Java chuyển hướng **cả dữ liệu** về ISO-8859-1. Nếu một file lẫn đoạn UTF-8 với đoạn Latin-1 cũ, quá trình dự phòng có thể làm những đoạn UTF-8 vốn đúng trở thành chữ lỗi.

**Ba tình huống:**

1. File UTF-8 hợp lệ: đọc một lần bằng UTF-8; **không** thử ISO-8859-1.
2. File ISO-8859-1 có byte không hợp lệ theo UTF-8 (như `E9` lẻ): thử UTF-8 thất bại, đọc lại bằng ISO-8859-1.
3. File legacy có các byte *tình cờ tạo thành chuỗi UTF-8 hợp lệ*: không phát sinh lỗi UTF-8, nên **không fallback**; giá trị nhận được có thể khác nội dung tác giả định viết.

Đặc biệt, ISO-8859-1 giải mã được mọi giá trị byte từ `00` đến `FF`, nhưng dữ liệu giải mã thành ký tự không đồng nghĩa với nội dung hợp lệ về ngữ nghĩa hoặc đúng ngôn ngữ. Ngoài giải mã, parser `.properties` vẫn có các quy tắc key/value, escape và lỗi Unicode escape riêng; `IllegalArgumentException` do escape `\u` sai **không phải** điều kiện chuyển bảng mã.

## 3. Ví dụ Java 17+: kiểm chứng UTF-8 trước và fallback Latin-1

Ví dụ này tạo hai nội dung `word=café` **có cùng văn bản nhưng mã hóa byte khác nhau** ngay trong Java, không phụ thuộc editor tạo file nào. Một dữ liệu thứ ba minh họa sự mơ hồ khi byte ISO-8859-1 hợp lệ dưới UTF-8.

Tạo file **`PropertyEncodingDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.util.PropertyResourceBundle;

public class PropertyEncodingDemo {
    private static byte[] encode(String text, Charset charset) {
        return ("word=" + text + "\n").getBytes(charset);
    }

    private static void inspect(String label, byte[] bytes) {
        try (ByteArrayInputStream input =
                     new ByteArrayInputStream(bytes)) {
            PropertyResourceBundle bundle =
                    new PropertyResourceBundle(input);
            System.out.println(label + ": "
                    + bundle.getString("word"));
        } catch (IOException exception) {
            System.out.println(label + ": "
                    + exception.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        byte[] utf8 = encode(
                "café", StandardCharsets.UTF_8);
        byte[] latin1 = encode(
                "café", StandardCharsets.ISO_8859_1);
        byte[] ambiguous = encode(
                "cafÃ©", StandardCharsets.ISO_8859_1);

        inspect("UTF8", utf8);
        inspect("LATIN1", latin1);
        inspect("AMBIGUOUS", ambiguous);
    }
}
```

Biên dịch và chạy trên Java 17+:

```bash
javac -encoding UTF-8 PropertyEncodingDemo.java
java PropertyEncodingDemo
```

**Stdout ở chế độ mặc định** (không có `-Djava.util.PropertyResourceBundle.encoding`):

```text
UTF8: café
LATIN1: café
AMBIGUOUS: café
```

Giải thích cơ chế, thay vì chỉ nhìn vào chuỗi:

- `UTF8`: từ `"café"` tạo các byte `63 61 66 C3 A9`; UTF-8 hợp lệ nên giải mã thành `café`.
- `LATIN1`: từ cùng chữ đó tạo `63 61 66 E9`; byte `E9` lẻ không hợp lệ theo UTF-8, dẫn đến **đọc lại ISO-8859-1** và thu được `café`.
- `AMBIGUOUS`: tác giả cố tình mã hóa chuỗi `cafÃ©` dưới ISO-8859-1. Nó cũng tạo các byte `63 61 66 C3 A9`, hợp lệ theo UTF-8, vì vậy Java đọc thành `café`. Chuỗi gốc có ký tự khác nhưng **không có lỗi giải mã để kích hoạt fallback**.

Ví dụ thứ ba là bằng chứng vì sao không thể dùng cơ chế fallback này để xác nhận chắc chắn file “thuộc mã hóa nào”. **Nên chuẩn hóa tất cả bundle của dự án sang UTF-8**, không chủ đích trộn mã hóa cũ và mới.

> Đối với file dữ liệu thực, hãy kiểm tra byte nguồn; một giá trị hiển thị có vẻ hợp lý không chứng minh đúng charset. Một số chuỗi Latin-1 cũ hoàn toàn là ASCII thì cả hai cách đọc đều giống nhau, cũng không cho ta biết mã hóa ban đầu.

## 4. Ép một mã hóa bằng java.util.PropertyResourceBundle.encoding

Java hỗ trợ **system property** tên chính xác:

```text
java.util.PropertyResourceBundle.encoding
```

Nếu đặt giá trị bằng đúng `UTF-8` hoặc `ISO-8859-1`, `PropertyResourceBundle(InputStream)` **chỉ dùng bảng mã được chỉ định**. Chế độ thử UTF-8 rồi fallback sẽ **không chạy**.

Chạy lại chương trình ở mục 3 thành **các tiến trình JVM độc lập**:

```bash
java -Djava.util.PropertyResourceBundle.encoding=UTF-8 PropertyEncodingDemo
java -Djava.util.PropertyResourceBundle.encoding=ISO-8859-1 PropertyEncodingDemo
```

**Với `-D...=UTF-8`**, stdout:

```text
UTF8: café
LATIN1: MalformedInputException
AMBIGUOUS: café
```

Ở hàng `LATIN1`, byte `E9` sai UTF-8 nên ngoại lệ giải mã được báo lại, **không thử ISO-8859-1**. Đây là hành vi hữu ích khi muốn phát hiện file không hợp chuẩn UTF-8.

**Với `-D...=ISO-8859-1`**, stdout:

```text
UTF8: cafÃ©
LATIN1: café
AMBIGUOUS: cafÃ©
```

Byte `C3 A9` trong file UTF-8 bị diễn giải thành hai ký tự `Ã©`. Do ISO-8859-1 chấp nhận mọi byte, cách đọc này không tự báo lỗi khi gặp nội dung vốn là UTF-8.

| Cấu hình JVM khi khởi động | UTF-8 hợp lệ | Latin-1 chứa byte UTF-8 sai | Có chuyển bảng mã dự phòng? |
| --- | --- | --- | --- |
| Không đặt property | Đọc UTF-8 | Thử lại ISO-8859-1 | Có |
| `-Djava.util.PropertyResourceBundle.encoding=UTF-8` | Đọc UTF-8 | Báo lỗi giải mã | Không |
| `-Djava.util.PropertyResourceBundle.encoding=ISO-8859-1` | Có thể bị đọc thành chữ lỗi | Đọc bằng Latin-1 | Không |

Một số ràng buộc quan trọng:

- Java chỉ công nhận hai giá trị `UTF-8` và `ISO-8859-1` như trên cho system property này; giá trị khác **không chọn một bảng mã tùy ý**, mà bị bỏ qua theo đặc tả.
- Property được **đọc lúc khởi tạo class `PropertyResourceBundle`**. Đổi hoặc xóa property bằng `System.setProperty(...)` sau thời điểm đó **không làm thay đổi** cấu hình đã được chốt.
- Đặt `-D...` **trước tên class chính** trong dòng lệnh `java`. Mỗi lệnh ở trên phải khởi động một JVM mới, không chạy luân phiên bằng cách đổi property giữa chừng trong cùng chương trình.
- System property tác động trên toàn JVM đối với các luồng đọc bundle theo đường `InputStream` này. Không dùng nó làm lựa chọn encoding riêng cho từng người dùng.
- Khi chuyển một dự án sang UTF-8 chuẩn, có thể ép `UTF-8` trong CI hoặc khi chạy kiểm thử để phát hiện nguồn legacy sai mã hóa. Cần đánh giá dữ liệu hiện có và đường tải resources trước khi áp dụng vào sản phẩm đang phục vụ người dùng.

### Vì sao không dùng -Dfile.encoding để thay thế?

`file.encoding` thường liên quan charset mặc định của Java I/O và môi trường chạy. Nó **không phải** công tắc xác định quy tắc UTF-8/ISO-8859-1 của `PropertyResourceBundle(InputStream)`. Hãy dùng `java.util.PropertyResourceBundle.encoding` khi muốn điều khiển riêng cơ chế này. Trong code tự tạo `InputStreamReader`, truyền `StandardCharsets.UTF_8` rõ ràng thường tốt hơn phụ thuộc charset mặc định.

## 5. InputStream và Reader: cùng class, hai trách nhiệm khác nhau

`PropertyResourceBundle` có hai constructor quan trọng:

```java
PropertyResourceBundle(InputStream stream)
PropertyResourceBundle(Reader reader)
```

- **`InputStream`:** constructor nhận **byte**; `PropertyResourceBundle` chịu trách nhiệm giải mã theo UTF-8 trước / fallback ISO-8859-1 hoặc theo system property ép mã hóa.
- **`Reader`:** constructor nhận **ký tự đã giải mã**; việc chuyển byte sang ký tự thuộc trách nhiệm của **Reader do caller tạo**. Constructor này không tự thử lại ISO-8859-1.
- **Unicode escape** như `\u00E9` được parser properties xử lý theo cú pháp `.properties` sau khi đã có chuỗi ký tự. Vì escape chỉ gồm byte ASCII, nó có thể giữ tính tương thích giữa UTF-8 và ISO-8859-1 khi viết đúng.

Ví dụ Reader tường minh, file **`ReaderCharsetDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.PropertyResourceBundle;

public class ReaderCharsetDemo {
    public static void main(String[] args) throws Exception {
        byte[] latin1 = "word=café\n".getBytes(
                StandardCharsets.ISO_8859_1);

        try (InputStreamReader reader = new InputStreamReader(
                new ByteArrayInputStream(latin1),
                StandardCharsets.ISO_8859_1)) {
            PropertyResourceBundle bundle =
                    new PropertyResourceBundle(reader);
            System.out.println(bundle.getString("word"));
        }
    }
}
```

```bash
javac -encoding UTF-8 ReaderCharsetDemo.java
java ReaderCharsetDemo
```

Stdout:

```text
café
```

Ở đây kết quả đúng do **caller chọn ISO-8859-1 trong `InputStreamReader`**. Không có “fallback” nào xảy ra trong `PropertyResourceBundle(Reader)`. Nếu caller chọn sai charset, có thể thu được ký tự thay thế hoặc lỗi giải mã tùy cấu hình decoder của Reader; constructor không phát hiện “file này vốn là Latin-1” để cứu nội dung.

Đường Reader là lựa chọn phù hợp khi chương trình phải đọc một nguồn có bảng mã **đã biết trước** và cần kiểm soát khâu giải mã. Khi phát triển một hệ thống mới, ưu tiên nguồn được lưu thống nhất bằng UTF-8 thay vì đoán bảng mã bằng lỗi đọc.

## 6. Khác với java.util.Properties.load(InputStream)

Tên đuôi file `.properties` không đảm bảo mọi API Java diễn giải byte giống nhau:

| API | Đầu vào | Quy tắc giải mã |
| --- | --- | --- |
| `new PropertyResourceBundle(inputStream)` trong Java 17+ | Byte | UTF-8 trước; mặc định fallback ISO-8859-1 khi lỗi giải mã; có thể ép một charset bằng system property |
| `new PropertyResourceBundle(reader)` | Ký tự | Reader quyết định cách giải mã byte; không dùng cơ chế thử lại của InputStream |
| `new Properties().load(inputStream)` | Byte | Theo hợp đồng API `Properties.load(InputStream)`: ISO-8859-1, ký tự ngoài phạm vi dùng escape `\uXXXX` |
| `new Properties().load(reader)` | Ký tự | Reader quyết định cách giải mã; parser đọc cú pháp properties trên ký tự |

**Điểm cần ghi nhớ:** JEP 226 thay đổi cách đọc *property resource bundles*, không biến `Properties.load(InputStream)` thành API đọc UTF-8 mặc định. Nếu file UTF-8 chứa dấu tiếng Việt được tải bằng `Properties.load(InputStream)`, chữ có thể bị lỗi mà không có ngoại lệ.

Ví dụ dưới đây chạy độc lập để quan sát khác biệt. Lưu **`PropertiesVsBundleDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.util.Properties;
import java.util.PropertyResourceBundle;

public class PropertiesVsBundleDemo {
    public static void main(String[] args) throws Exception {
        byte[] utf8 = "word=café\n".getBytes(
                StandardCharsets.UTF_8);

        Properties properties = new Properties();
        properties.load(new ByteArrayInputStream(utf8));

        PropertyResourceBundle bundle =
                new PropertyResourceBundle(
                        new ByteArrayInputStream(utf8));

        System.out.println("Properties: "
                + properties.getProperty("word"));
        System.out.println("Bundle: " + bundle.getString("word"));
    }
}
```

```bash
javac -encoding UTF-8 PropertiesVsBundleDemo.java
java PropertiesVsBundleDemo
```

Stdout mặc định với Java 17+:

```text
Properties: cafÃ©
Bundle: café
```

Cả hai cùng nhận **một mảng byte**, nhưng hợp đồng giải mã khác nhau. Nếu muốn dùng `Properties` với UTF-8, hãy tạo `Reader` tường minh:

```java
// Đoạn code trong phương thức có biến byte[] utf8.
try (var reader = new java.io.InputStreamReader(
        new java.io.ByteArrayInputStream(utf8),
        java.nio.charset.StandardCharsets.UTF_8)) {
    java.util.Properties values = new java.util.Properties();
    values.load(reader);
    System.out.println(values.getProperty("word"));
}
```

Đoạn này in `café` khi `utf8` chứa nội dung của ví dụ, nhưng chỉ là **fragment đặt bên trong phương thức**, không phải một file Java độc lập.

## 7. Áp dụng với ResourceBundle.getBundle trên classpath

Trong ứng dụng thường gặp, bạn không trực tiếp `new PropertyResourceBundle(InputStream)`. Thay vào đó, `ResourceBundle.getBundle(...)` tìm tài nguyên `.properties` phù hợp trên classpath rồi tải thông qua cơ chế property bundle.

Ví dụ cấu trúc:

```text
i18n-demo/
├── BundleOnClasspathDemo.java
├── messages.properties
└── messages_vi.properties
```

File **`messages.properties`** (lưu UTF-8):

```properties
greeting=Hello
```

File **`messages_vi.properties`** (lưu UTF-8):

```properties
greeting=Chào bạn
```

File **`BundleOnClasspathDemo.java`**:

```java
import java.util.Locale;
import java.util.ResourceBundle;

public class BundleOnClasspathDemo {
    public static void main(String[] args) {
        Locale locale = Locale.forLanguageTag("vi-VN");
        ResourceBundle bundle = ResourceBundle.getBundle(
                "messages", locale,
                ResourceBundle.Control.getNoFallbackControl(
                        ResourceBundle.Control.FORMAT_PROPERTIES));
        System.out.println(bundle.getString("greeting"));
    }
}
```

Chạy **ngay trong thư mục có cả ba file**:

```bash
javac -encoding UTF-8 BundleOnClasspathDemo.java
java -cp . BundleOnClasspathDemo
```

Stdout với file đã lưu UTF-8 trên Java 17+:

```text
Chào bạn
```

`messages_vi.properties` được chọn cho `vi-VN` vì không cần file `messages_vi_VN.properties` mới sử dụng được bản tiếng Việt chung. `Control.FORMAT_PROPERTIES` chỉ chọn dạng file properties; `getNoFallbackControl` ngăn một lượt fallback sang **default locale của JVM** khi tìm bundle, nhưng vẫn cho phép chuỗi ứng viên/cha và bundle gốc bình thường.

**Cần phân biệt hai “fallback” hoàn toàn khác nhau:**

- **Fallback locale/bundle:** khi không có file cho `vi-VN`, Java xét `vi` rồi gốc tùy cách chọn bundle. Đây là logic **tìm tài nguyên**, không liên quan charset.
- **Fallback charset:** sau khi đã có một stream của file properties, `PropertyResourceBundle` có thể **đọc lại byte ISO-8859-1** nếu thử UTF-8 thất bại. Đây là logic **giải mã nội dung của một file**.

Không dùng lỗi chữ bị mã hóa sai làm tín hiệu để tự chuyển sang bundle gốc hoặc chọn một locale khác. Ngược lại, một bundle locale được chọn đúng vẫn có thể bị lỗi chữ nếu file đã lưu sai bảng mã.

### Lỗi có thể bị bao gói khi đọc qua getBundle

Với `new PropertyResourceBundle(InputStream)` trực tiếp, ngoại lệ giải mã bị ép UTF-8 có thể xuất hiện dưới dạng `MalformedInputException` hoặc `UnmappableCharacterException`. Khi thông qua `ResourceBundle.getBundle`, lỗi nạp resource có thể được phản ánh trong quá trình tìm bundle và nằm trong **cause** của ngoại lệ ở cấp cao hoặc bị ảnh hưởng bởi việc có ứng viên dự phòng. Vì thế, khi nghiên cứu lỗi encoding trong ứng dụng thực, cần kiểm tra **chuỗi cause**, file bundle được chọn, classpath và cấu hình cache; không khẳng định mọi lỗi charset ở `getBundle` đều ném trực tiếp một loại exception duy nhất.

## 8. Trường hợp thực tế: dữ liệu Latin-1 cũ chứa dấu và dữ liệu bị pha trộn

### File Latin-1 thực sự

Một bundle tiếng Pháp từ hệ thống cũ có thể chứa byte `E9` cho chữ `é`. Khi được đọc bằng default Java 17+, quá trình thử UTF-8 thất bại rồi fallback ISO-8859-1 có thể khiến nội dung **trông vẫn đúng**, dù file chưa được chuyển sang UTF-8. Đây là cơ chế hỗ trợ tương thích, không nên xem như bằng chứng toàn bộ kho file đã chuẩn hóa.

### Byte hợp lệ theo cả hai cách

Nếu legacy file chứa dãy `C3 A9` với ý nghĩa Latin-1 “`Ã©`”, Java sẽ thấy một UTF-8 hợp lệ biểu diễn “`é`” và **không fallback**. Ví dụ `AMBIGUOUS` ở trên minh họa hành vi này. Một số chuỗi khác có thể trở thành chữ vô nghĩa nhưng parser vẫn hoạt động bình thường.

### File có đoạn thuộc nhiều mã hóa

Giả sử phần đầu bundle là UTF-8, phần cuối được một công cụ cũ append byte Latin-1. Một byte sai UTF-8 ở cuối làm parser quay lại đọc **toàn bộ file** theo Latin-1. Kết quả: phần cũ Latin-1 có thể đúng, nhưng phần UTF-8 bị chuyển thành chữ lỗi. Để khắc phục, phải **chuyển đổi file nguồn thành một mã hóa duy nhất**, không chèn thêm quy tắc dự phòng theo key.

### Unicode escape

Một giá trị như:

```properties
greeting=caf\u00E9
```

chỉ chứa ký tự ASCII trong file, nên được giải mã giống nhau theo UTF-8 và ISO-8859-1 trước khi parser xử lý `\u00E9` thành `é`. Unicode escape hữu ích để giữ tương thích với công cụ cũ, nhưng không bắt buộc cho UTF-8 trong Java 17+. Nếu dùng escape cho ký tự ngoài BMP, cần biểu diễn đúng cặp UTF-16 surrogate escape theo quy tắc `\uXXXX`, không dùng mã code point tùy ý dài hơn bốn chữ số hex trong một escape.

## 9. Kiểm soát mã hóa và kiểm thử trong dự án

Một quy trình chắc chắn khi quản lý các bundle `messages*.properties`:

1. **Chọn UTF-8 làm chuẩn nguồn** cho toàn bộ file locale. Thiết lập editor và pipeline build tạo/sao chép resources dưới dạng byte không bị chuyển mã ngoài ý muốn.
2. **Kiểm tra byte/tính hợp lệ UTF-8** trong CI cho các file cần chuẩn hóa. Đừng suy ra encoding chỉ từ hậu tố file hoặc việc `getBundle` chạy không lỗi.
3. **Chạy một bộ test trong JVM riêng với `-Djava.util.PropertyResourceBundle.encoding=UTF-8`** để phát hiện bundle không hợp lệ theo UTF-8. Kết quả qua `ResourceBundle.getBundle` còn chịu ảnh hưởng fallback locale và cache, nên test cần tải trúng tài nguyên muốn kiểm tra.
4. **Kiểm tra giá trị Unicode cụ thể** như `Chào bạn`, `Đặng`, `café`, `日本語`. Đúng key chưa có nghĩa là đúng byte/đúng chữ.
5. **Kiểm tra cơ chế nguồn cũ**: xác định file nào là ISO-8859-1, chuyển byte sang UTF-8 bằng công cụ có charset tường minh, review diff ký tự và loại bỏ pha trộn trước khi áp dụng chế độ ép UTF-8.
6. **Dùng tiến trình mới khi đổi system property trong test**: thuộc tính được chốt lúc `PropertyResourceBundle` khởi tạo; không làm test A rồi B trong cùng JVM bằng `System.setProperty` và kỳ vọng constructor tự đổi chế độ.
7. **Kiểm thử classpath/packaging**: các file `.properties` phải nằm đúng đường dẫn resource, ví dụ gốc resources hoặc package tương ứng. Nếu file chưa được đóng gói vào JAR, lỗi là thiếu resource chứ không phải lỗi encoding.
8. **Kiểm tra môi trường đầu ra**: console không hỗ trợ Unicode có thể hiển thị sai dù chuỗi Java đã đúng. Tách lỗi **giải mã nội dung** khỏi lỗi **render** bằng cách so sánh chuỗi Unicode trong test.

### Test nhỏ có thể kiểm tra tự động

Với `PropertyEncodingDemo`:

| Chế độ | Điều cần xác minh |
| --- | --- |
| Default | Hai nguồn UTF-8 và Latin-1 có byte `E9` đơn đều cho `café` |
| Ép UTF-8 | Nguồn Latin-1 có byte `E9` bị từ chối bằng lỗi giải mã |
| Ép ISO-8859-1 | Nguồn UTF-8 `C3 A9` trở thành `Ã©` |
| Default với byte nhập nhằng | Một legacy file có byte hợp lệ theo UTF-8 **không kích hoạt fallback** |

Đây là kiểm thử trực tiếp constructor nhận `InputStream` nhằm cô lập hành vi encoding. Đối với kiểm thử `ResourceBundle.getBundle` ở cấp ứng dụng, ngoài encoding còn cần kiểm tra **locale được chọn**, bundle gốc/bundle cha, key kế thừa và caching.

## 10. Sai lầm phổ biến

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Cho rằng Java luôn đọc `.properties` bằng ISO-8859-1 | Không phù hợp với `PropertyResourceBundle(InputStream)` từ Java 9 | Biết rõ API, constructor, phiên bản Java |
| Cho rằng mọi file Latin-1 đều tự động được phát hiện | Một số chuỗi byte Latin-1 hợp lệ theo UTF-8 | Chuẩn hóa UTF-8 và kiểm tra byte |
| Cho rằng fallback chỉ sửa ký tự lỗi | Parser đọc lại **toàn bộ** stream bằng ISO-8859-1 | Không pha mã hóa trong một file |
| Dùng `-Dfile.encoding=UTF-8` để buộc `PropertyResourceBundle` từ chối Latin-1 | Không phải property chuyên dụng | Dùng `-Djava.util.PropertyResourceBundle.encoding=UTF-8` |
| Gọi `System.setProperty` sau khi đã dùng `PropertyResourceBundle` | Class đã chốt cấu hình encoding | Thiết lập khi khởi động JVM |
| Dùng `Properties.load(InputStream)` để đọc tiếng Việt UTF-8 trực tiếp | API này vẫn diễn giải ISO-8859-1 | Dùng `load(Reader)` với UTF-8 hoặc API bundle phù hợp |
| Tưởng `PropertyResourceBundle(Reader)` tự fallback | Charset là trách nhiệm của Reader | Tạo Reader với charset rõ ràng |
| Nhầm fallback bundle và fallback bảng mã | Chẩn đoán sai nguyên nhân nội dung lỗi | Phân tách lựa chọn locale với giải mã byte |
| Thấy `getString` có giá trị thì cho rằng chữ đúng | Giá trị có thể bị mojibake | Kiểm thử chuỗi Unicode, kiểm tra encoding |
| Test các chế độ `-D...` trên cùng JVM | Property chỉ được đánh giá lúc class initialization | Mỗi chế độ một JVM mới |
| Cho rằng Unicode escape là ký tự được lưu theo bảng mã riêng | Parser xử lý escape sau bước giải mã | Viết escape đúng cú pháp `\uXXXX` |
| Chỉ sửa console khi byte nguồn sai | Lỗi đầu vào và lỗi hiển thị là hai tầng khác nhau | Kiểm tra byte, chuỗi Java rồi đến terminal |

## 11. Câu hỏi thực hành

**Bài tập 1.** Tạo byte của `"greeting=café"` lần lượt với `StandardCharsets.UTF_8` và `ISO_8859_1`. Dùng `new PropertyResourceBundle(InputStream)` để đọc trên Java 17+. Giải thích vì sao mặc định cả hai đều hiển thị đúng và vì sao điều đó không đảm bảo charset được phát hiện chính xác.

**Bài tập 2.** Chạy `PropertyEncodingDemo` ở ba JVM độc lập: mặc định, ép `UTF-8`, ép `ISO-8859-1`. Ghi lại các dòng `UTF8`, `LATIN1`, `AMBIGUOUS`; giải thích các byte `E9` và `C3 A9`.

**Bài tập 3.** Dùng `Properties.load(InputStream)` đọc một mảng byte UTF-8 chứa `é` và so với `PropertyResourceBundle(InputStream)`. Thay `Properties.load(InputStream)` bằng `Properties.load(Reader)` với `UTF_8` rồi kiểm tra kết quả.

**Bài tập 4.** Tạo `messages.properties` và `messages_vi.properties` lưu UTF-8, rồi gọi `ResourceBundle.getBundle("messages", Locale.forLanguageTag("vi-VN"))`. Xác minh chữ tiếng Việt và phân tích riêng ba nguyên nhân nếu nó sai: file không đúng byte UTF-8, chọn nhầm bundle, hoặc môi trường console hiển thị không đúng.

**Đáp án nguyên tắc:** Mặc định Java 17+ thử UTF-8 trước, lỗi giải mã thì đọc lại Latin-1; ép `UTF-8` loại bỏ retry; `Properties.load(InputStream)` luôn theo Latin-1; `Reader` dùng charset do caller chọn. Khi lỗi, cần tìm đúng tầng đã tạo ra khác biệt.

## 12. Tài liệu chính thức

- [JEP 226 — UTF-8 Property Resource Bundles](https://openjdk.org/jeps/226): động lực tương thích và thay đổi mặc định từ Java 9.
- [JDK 21 — PropertyResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/PropertyResourceBundle.html): constructor nhận `InputStream`/`Reader`, quy tắc fallback và system property mã hóa.
- [JDK 21 — java.util.Properties](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Properties.html): `load(InputStream)` và `load(Reader)`.
- [JDK 21 — ResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ResourceBundle.html): cách tìm bundle từ classpath theo locale.

## 13. Ghi nhớ

**Với Java 17+, `PropertyResourceBundle(InputStream)` ưu tiên UTF-8; nếu gặp lỗi giải mã, nó đọc lại toàn bộ stream bằng ISO-8859-1.** Cơ chế này giúp tương thích file cũ nhưng không nhận diện chính xác mọi bảng mã, và không cứu được trường hợp byte sai mã hóa mà vẫn tạo UTF-8 hợp lệ. Có thể ép một charset bằng `-Djava.util.PropertyResourceBundle.encoding=UTF-8` hoặc `ISO-8859-1` **ngay khi khởi động JVM**, khi đó không fallback. `PropertyResourceBundle(Reader)` và `Properties.load(InputStream)` có quy tắc riêng, không tự kế thừa thay đổi này.

Trong dự án mới, hãy lưu bundle bằng **UTF-8 thống nhất**, kiểm tra byte và nội dung Unicode thật, cấu hình encoding rõ ràng ở CI khi cần, và phân biệt **fallback bảng mã** với **fallback tài nguyên theo locale**.