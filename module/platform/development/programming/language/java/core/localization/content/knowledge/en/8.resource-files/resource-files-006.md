# Chọn Reader với charset tường minh khi cần kiểm soát mã hóa tệp tài nguyên

Trong Java, tệp `.properties` thường chứa các nhãn giao diện, thông điệp lỗi và văn bản bản địa hóa. Khi tệp có chữ tiếng Việt hoặc ký tự ngoài ASCII, một câu hỏi quan trọng xuất hiện: **dãy byte trong tệp được giải mã theo charset nào trước khi Java đọc cặp `key=value`?**

Nếu ứng dụng cần kiểm soát chắc chắn cách giải mã tệp tài nguyên, hãy tạo `Reader` với charset được chỉ định và truyền vào `PropertyResourceBundle(Reader)`. Cách này đặc biệt hữu ích khi tích hợp các bộ tài nguyên có mã hóa được xác định từ trước, xử lý tệp cũ không dùng UTF-8, hoặc muốn báo lỗi rõ ràng khi dữ liệu vi phạm encoding được cam kết.

Bài tập trung vào **lựa chọn Reader có charset tường minh** và hệ quả của nó trong quá trình tải tệp tài nguyên. Chúng ta cũng phân biệt với hành vi mặc định của `PropertyResourceBundle(InputStream)` trên Java 17, để tránh áp dụng nhầm các quy tắc của API khác.

## 1. Tách ba bước: byte → ký tự → tài nguyên

Đường đi của một tệp tài nguyên là:

~~~text
Tệp .properties trên đĩa hoặc trong classpath
             |
             | InputStream: dãy byte
             v
  Reader dùng charset đã chọn
             |
             | Các ký tự Unicode trong Java
             v
  Bộ phân tích cú pháp .properties
             |
             | key=value, comment, escape
             v
       PropertyResourceBundle
             |
             v
    bundle.getString("title")
~~~

`Reader` chịu trách nhiệm chuyển **byte thành ký tự**. Sau đó, `PropertyResourceBundle` xử lý **cú pháp tệp properties**, gồm dấu phân cách `=` hoặc `:`, khoảng trắng, comment, ký tự escape và các chuỗi `\uXXXX` theo cú pháp properties.

Hai bước này độc lập:

- Một tệp UTF-8 chứa `title=Chào Việt Nam` cần giải mã byte theo UTF-8 trước.
- Một tệp ASCII chứa `title=Ch\u00E0o` có thể được giải mã mà không cần byte UTF-8 cho chữ `à`; parser properties mới chuyển escape Unicode thành ký tự.
- Chọn đúng charset **không sửa** tệp có cú pháp properties sai; parser vẫn có thể ném lỗi do Unicode escape hỏng.
- Chọn đúng charset **không tự chọn locale**. `Locale` là cơ chế lựa chọn bộ tài nguyên, còn `Charset` là cơ chế giải mã byte.

Ví dụ chuỗi `"Đăng nhập"` sau khi đọc đúng UTF-8 sẽ là một `String` Java bình thường. Khi gọi `getString`, charset ban đầu không còn là tham số của thao tác lấy khóa.

## 2. Vì sao nên chỉ định charset tường minh?

Giả sử có tệp:

~~~properties
title=Chào Việt Nam
button.login=Đăng nhập
notice=Đặt lịch thành công
~~~

Nếu tệp được lưu bằng UTF-8 nhưng đọc bằng ISO-8859-1, những byte của ký tự có dấu có thể bị diễn giải thành nhiều ký tự khác, tạo hiện tượng **mojibake**. Một ví dụ điển hình là chuỗi `"Café"` trở thành dạng hỏng như `"CafÃ©"` khi byte UTF-8 bị giải mã theo Latin-1.

Đổi `Locale.forLanguageTag("vi-VN")` hoặc đổi font không thể sửa vấn đề này. Lỗi đã xảy ra tại **ranh giới byte → ký tự**.

Với Java 17, chọn `StandardCharsets.UTF_8` khi tệp được chuẩn hóa UTF-8. Chỉ dùng `StandardCharsets.ISO_8859_1`, `windows-1252` hoặc charset khác khi **đã biết** nguồn dữ liệu thực sự sử dụng cách mã hóa ấy. Không đoán charset từ quốc gia hoặc từ nội dung một vài chữ có dấu.

Ví dụ đọc tệp hiện có bằng charset UTF-8:

~~~java
Path path = Path.of("i18n", "messages_vi.properties");

try (Reader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    PropertyResourceBundle bundle =
            new PropertyResourceBundle(reader);
    System.out.println(bundle.getString("title"));
}
~~~

Đây là **đoạn mã minh họa** bên trong một phương thức có thể ném hoặc xử lý `IOException`; cần import `java.nio.file.Path`, `java.nio.file.Files`, `java.nio.charset.StandardCharsets`, `java.io.Reader`, `java.util.PropertyResourceBundle`. Đường dẫn tệp chỉ là ví dụ; ứng dụng phải dùng vị trí tài nguyên thực.

`Files.newBufferedReader(path, charset)` mở `Reader` theo charset đã chọn và đóng an toàn nhờ `try-with-resources`. Việc gọi `new PropertyResourceBundle(reader)` đọc dữ liệu khi xây dựng bundle; sau khi constructor hoàn thành, đối tượng bundle có thể được sử dụng sau khi `Reader` đóng.

## 3. So sánh chính xác các cách nạp trong Java 17

Không thể suy ra charset của mọi API có tên “properties” từ một quy tắc duy nhất.

| Cách đọc | Charset được quyết định thế nào? | Điều nên nhớ |
| --- | --- | --- |
| `new PropertyResourceBundle(reader)` | Dữ liệu ký tự đã được `Reader` giải mã | Chọn charset ngay khi tạo Reader |
| `new PropertyResourceBundle(inputStream)` | Java 17 ưu tiên UTF-8 và có cơ chế đọc lại bằng ISO-8859-1 khi byte UTF-8 không hợp lệ theo điều kiện API | Có thể chịu ảnh hưởng của system property riêng |
| `ResourceBundle.getBundle("messages", locale)` | Sử dụng cơ chế tải bundle thích hợp; với bundle `.properties` thông thường áp dụng quy tắc của `PropertyResourceBundle` | Đồng thời quản lý tìm bundle theo locale và chuỗi cha |
| `properties.load(inputStream)` với `java.util.Properties` | Đọc `.properties` theo ISO-8859-1 theo hợp đồng API | **Không giống** `PropertyResourceBundle(InputStream)` Java 17 |
| `properties.load(reader)` | Dùng ký tự Reader cung cấp | Charset được xác định khi tạo Reader |

### Hành vi mặc định của PropertyResourceBundle(InputStream)

Từ Java 9, `PropertyResourceBundle(InputStream)` mặc định đọc byte như UTF-8. Nếu gặp chuỗi byte không hợp lệ hoặc không ánh xạ được trong UTF-8, Java có thể **đọc lại bằng ISO-8859-1**, để duy trì tương thích với tệp tài nguyên cũ.

Trong Java 17, system property `java.util.PropertyResourceBundle.encoding` có thể đặt thành `UTF-8` hoặc `ISO-8859-1` để bắt buộc lựa chọn tương ứng cho đường đọc `InputStream`. Khi đặt `UTF-8`, dữ liệu UTF-8 không hợp lệ gây lỗi, không áp dụng fallback Latin-1. Property này được đọc khi lớp được khởi tạo; thay đổi khi ứng dụng đang chạy không phải một phương pháp đáng tin để đổi charset giữa các request.

**Quy tắc trên thuộc constructor nhận `InputStream`, không phải cách Java tự đổi charset của Reader.** Với `PropertyResourceBundle(Reader)`, Reader được tạo bằng charset nào thì byte được giải mã theo charset đó. System property kể trên không thay charset của một Reader đã được tạo.

Một byte stream có thể chỉ chứa các byte tạo thành UTF-8 hợp lệ nhưng vốn được một nguồn ghi với mã hóa khác. Khi ấy, cơ chế tự động không thể suy luận chắc chắn encoding gốc. Nếu hợp đồng dữ liệu đòi một charset cụ thể, chọn Reader tường minh vẫn cho kết quả dễ dự đoán hơn.

### Đừng nhầm với java.util.Properties

Trên Java 17, `Properties.load(InputStream)` vẫn diễn giải mỗi byte như một ký tự ISO-8859-1 và hỗ trợ Unicode escape trong cú pháp properties. Muốn dùng UTF-8 với `Properties`, truyền `Reader` UTF-8 vào `Properties.load(Reader)`.

Việc cả `Properties` và `PropertyResourceBundle` đọc được định dạng `.properties` không có nghĩa chúng có cùng chính sách charset khi nhận `InputStream`.

## 4. Tạo Reader từ InputStream hoặc Path

### Cách A: tệp có đường dẫn trên hệ thống

Khi làm việc với một tệp nằm trên ổ đĩa và có `Path`, dùng:

~~~java
try (Reader reader = Files.newBufferedReader(
        Path.of("config", "labels.properties"),
        StandardCharsets.UTF_8)) {
    PropertyResourceBundle labels =
            new PropertyResourceBundle(reader);
    String title = labels.getString("title");
}
~~~

Mẫu này phù hợp với trình nhập bản dịch từ thư mục, lệnh kiểm tra tài nguyên hoặc tệp cấu hình ngoài classpath. `Files.newBufferedReader` trả về BufferedReader; không cần bọc thêm một BufferedReader chỉ vì constructor nhận kiểu `Reader`.

### Cách B: tài nguyên bên trong classpath

Nếu tệp được đóng gói trong JAR hoặc đặt dưới `src/main/resources`, `Path.of("...")` có thể không trỏ đúng vị trí runtime. Dùng `ClassLoader.getResourceAsStream` để lấy byte:

~~~java
ClassLoader loader = Thread.currentThread().getContextClassLoader();
if (loader == null) {
    loader = MyApplication.class.getClassLoader();
}

try (InputStream input =
        loader.getResourceAsStream("i18n/messages_vi.properties")) {
    if (input == null) {
        throw new FileNotFoundException("Missing resource");
    }
    try (Reader reader =
            new InputStreamReader(input, StandardCharsets.UTF_8)) {
        PropertyResourceBundle bundle =
                new PropertyResourceBundle(reader);
        System.out.println(bundle.getString("title"));
    }
}
~~~

Đây là **đoạn minh họa trong một lớp tên `MyApplication`** đã khai báo và có các import `java.io.*`, `java.nio.charset.StandardCharsets`, `java.util.PropertyResourceBundle`. Hãy thay đường dẫn resource và cách chọn class loader theo kiến trúc ứng dụng; `getResourceAsStream` có thể trả `null` khi không tìm được tệp. Với JPMS named modules, cần tuân theo quy tắc đóng gói/mở tài nguyên của module.

Phương thức `getResourceAsStream` không bảo đảm tài nguyên có charset nào; nó chỉ cung cấp byte. Chính `new InputStreamReader(input, StandardCharsets.UTF_8)` mới thể hiện quyết định giải mã.

### Cách C: bộ tài nguyên Latin-1 cũ

Nếu biết chắc tệp `labels_legacy.properties` được tạo dưới ISO-8859-1, dùng:

~~~java
try (Reader reader = Files.newBufferedReader(
        Path.of("legacy", "labels_legacy.properties"),
        StandardCharsets.ISO_8859_1)) {
    PropertyResourceBundle legacy =
            new PropertyResourceBundle(reader);
}
~~~

**Không dùng cách này cho tệp UTF-8 hiện đại** vì sẽ làm hỏng nhiều ký tự Unicode. ISO-8859-1 cũng không biểu diễn trực tiếp nhiều chữ cái tiếng Việt; tệp cũ có thể chứa dạng `\uXXXX` mà parser properties sẽ giải mã sau khi Reader xử lý byte.

## 5. Ví dụ Java 17+ độc lập: ba cách giải mã và dữ liệu lỗi

Chương trình sau chủ động tạo byte trong bộ nhớ để không phụ thuộc hệ điều hành, cấu hình console hay tệp bên ngoài. Nó chứng minh:

1. Chọn UTF-8 cho dữ liệu UTF-8 sẽ giữ nguyên chuỗi Unicode.
2. Cố đọc cùng byte UTF-8 theo ISO-8859-1 tạo chuỗi **khác**.
3. Chọn ISO-8859-1 cho dữ liệu Latin-1 cũ cho kết quả đúng.
4. Tạo `CharsetDecoder` với `CodingErrorAction.REPORT` giúp phát hiện byte UTF-8 không hợp lệ.

Tạo tệp **`ReaderCharsetDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.Charset;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.MalformedInputException;
import java.nio.charset.StandardCharsets;
import java.util.PropertyResourceBundle;
import java.util.TreeSet;

public class ReaderCharsetDemo {
    static PropertyResourceBundle load(
            byte[] bytes, Charset charset) throws IOException {
        try (Reader reader = new InputStreamReader(
                new ByteArrayInputStream(bytes), charset)) {
            return new PropertyResourceBundle(reader);
        }
    }

    static PropertyResourceBundle loadStrictUtf8(
            byte[] bytes) throws IOException {
        CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        try (Reader reader = new InputStreamReader(
                new ByteArrayInputStream(bytes), decoder)) {
            return new PropertyResourceBundle(reader);
        }
    }

    public static void main(String[] args) throws IOException {
        String vietnamese =
                "title=Chào Việt Nam\nbutton=Đăng nhập\n";
        byte[] utf8 = vietnamese.getBytes(StandardCharsets.UTF_8);

        PropertyResourceBundle correct =
                load(utf8, StandardCharsets.UTF_8);
        PropertyResourceBundle wrong =
                load(utf8, StandardCharsets.ISO_8859_1);

        System.out.println("UTF-8 title correct: "
                + correct.getString("title").equals("Chào Việt Nam"));
        System.out.println("Wrong charset differs: "
                + !wrong.getString("title").equals("Chào Việt Nam"));
        System.out.println("Keys: "
                + new TreeSet<>(correct.keySet()));

        String latin1 = "title=Café\n";
        PropertyResourceBundle legacy = load(
                latin1.getBytes(StandardCharsets.ISO_8859_1),
                StandardCharsets.ISO_8859_1);
        System.out.println("Latin-1 title correct: "
                + legacy.getString("title").equals("Café"));

        try {
            loadStrictUtf8(new byte[] {
                    't', 'i', 't', 'l', 'e', '=',
                    (byte) 0xC3, (byte) 0x28
            });
            System.out.println("Malformed UTF-8 rejected: false");
        } catch (MalformedInputException ex) {
            System.out.println("Malformed UTF-8 rejected: true");
        }
    }
}
~~~

Lệnh biên dịch/chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 ReaderCharsetDemo.java
java ReaderCharsetDemo
~~~

Stdout đã đối chiếu với chương trình tương đương ở Java:

~~~text
UTF-8 title correct: true
Wrong charset differs: true
Keys: [button, title]
Latin-1 title correct: true
Malformed UTF-8 rejected: true
~~~

**Giải thích đầu ra:**

- Chuỗi `"Chào Việt Nam"` được mã hóa UTF-8 rồi đưa qua `InputStreamReader(..., UTF_8)`; `PropertyResourceBundle(Reader)` đọc đúng giá trị. `equals` trả `true`.
- Cùng byte được giải mã theo ISO-8859-1 tạo chuỗi khác; `equals` với bản gốc là `false`, vì vậy dòng `Wrong charset differs` in `true`.
- `keySet()` trả tập khóa của bundle; `TreeSet` khiến thứ tự `button`, `title` có tính xác định.
- Tệp Latin-1 trong bộ nhớ chứa `Café` được mã hóa và giải mã bằng cùng charset nên giữ nguyên.
- Chuỗi byte `0xC3 0x28` không hợp lệ theo UTF-8. Decoder strict báo `MalformedInputException`, được chương trình bắt và in kết quả `true`.

Chương trình là tệp Java độc lập, không cần thư viện ngoài. Lệnh `-encoding UTF-8` chỉ định **mã hóa của chính file mã nguồn Java** cho trình biên dịch; nó không tự đặt charset cho `InputStreamReader`. Charset của resource vẫn là giá trị được truyền trong code.

## 6. Phân biệt chọn charset với chính sách xử lý byte hỏng

Hai câu hỏi liên quan nhưng khác nhau:

- **Đọc byte theo bộ mã nào?** Chọn `Charset` khi tạo Reader.
- **Khi byte không thể giải mã hợp lệ thì làm gì?** Chọn `CodingErrorAction` của `CharsetDecoder`.

Với constructor `new InputStreamReader(stream, charset)`, decoder mặc định có thể **thay thế** chuỗi byte lỗi bằng ký tự thay thế thay vì phát lỗi ngay. Đối với dữ liệu bản dịch cần kiểm định chặt, hành vi thay thế im lặng có thể khiến bản dịch hỏng lọt vào môi trường sản xuất.

Dùng `CharsetDecoder` chủ động để phát hiện lỗi:

~~~java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try (Reader reader = new InputStreamReader(stream, decoder)) {
    PropertyResourceBundle bundle =
            new PropertyResourceBundle(reader);
}
~~~

Đây là **đoạn mã minh họa** khi `stream` là `InputStream` đã mở; import `java.io.*`, `java.nio.charset.*`, `java.util.PropertyResourceBundle`. Với `REPORT`, những byte không hợp lệ có thể gây `MalformedInputException` hoặc `UnmappableCharacterException`, đều là nhánh cần xử lý theo hợp đồng dữ liệu.

Tuy nhiên, **decoder strict không xác nhận rằng bạn đã chọn đúng charset**. Một dãy byte có thể hợp lệ dưới nhiều charset nhưng mang ý nghĩa khác nhau; với ISO-8859-1, mọi byte đều biểu diễn được ký tự. Để phát hiện chọn sai encoding, phải có thông tin nguồn tin cậy (cấu hình, hợp đồng giao tiếp, metadata hoặc quy trình migrate), kết hợp kiểm thử chuỗi mong đợi.

`Reader` do `Files.newBufferedReader(path, charset)` tạo có cơ chế báo lỗi byte bất hợp lệ theo hợp đồng API; khi cần tùy biến chính xác `REPORT`/`REPLACE`/`IGNORE`, tạo `CharsetDecoder` riêng.

### Xử lý lỗi ở đúng tầng

| Lỗi | Nơi phát sinh | Cách hiểu |
| --- | --- | --- |
| `NoSuchFileException` | Mở tệp trên đĩa | Không tồn tại đường dẫn |
| `IOException` | I/O hoặc decoder báo lỗi | Tệp không đọc được / dữ liệu byte lỗi |
| `IllegalArgumentException` khi có Unicode escape hỏng | Parser `.properties` | Cú pháp tài nguyên không hợp lệ |
| `MissingResourceException` từ `getString` | Tra cứu khóa | Không có key ở bundle và chuỗi cha |
| `ClassCastException` từ `getString` | Tra cứu giá trị không phải `String` | Loại tài nguyên không khớp API |

Không gộp mọi exception thành “không có bản dịch”. Encoding sai, tệp thiếu, key không có và cú pháp hỏng đều có cách sửa khác nhau.

## 7. Reader và ResourceBundle.getBundle(): giới hạn quan trọng

Tạo trực tiếp:

~~~java
PropertyResourceBundle bundle =
        new PropertyResourceBundle(reader);
~~~

chỉ tạo **một bundle từ nguồn ký tự đã cung cấp**. Phép này **không tự chạy thuật toán chọn ứng viên theo Locale** như:

~~~java
ResourceBundle.getBundle("messages", Locale.forLanguageTag("vi-VN"));
~~~

Cụ thể, khi bạn tự mở `messages_vi_VN.properties` rồi gọi constructor nhận `Reader`, đối tượng đó không tự biết rằng còn có `messages_vi.properties` và `messages.properties` để truy cập khóa chưa định nghĩa. Không nên giả định mọi khóa vắng mặt sẽ tự fallback về bundle cha.

Nếu ứng dụng chỉ muốn đọc một tệp có charset đặc biệt, constructor nhận Reader là lựa chọn đơn giản. Nếu ứng dụng cần **tự động chọn locale, tổ chức chuỗi cha và cache**, hãy giữ cơ chế `getBundle` và thiết kế cách nạp charset phù hợp với cơ chế đó.

### Khi cần Reader riêng trong quy trình getBundle

Trong ứng dụng chạy trên **classpath/unnamed module**, có thể tùy biến `ResourceBundle.Control.newBundle` để lấy stream của từng bundle candidate, tạo `InputStreamReader(stream, chosenCharset)`, rồi xây `PropertyResourceBundle(reader)`. `getBundle` vẫn tổ chức chuỗi cha theo các candidate locales và chính sách Control.

Hình dung quy trình:

~~~text
ResourceBundle.getBundle(baseName, locale, control)
           |
           | lựa chọn candidate locale, tên tài nguyên
           v
control.newBundle(...):
           |
           | mở InputStream phù hợp candidate
           | tạo Reader với charset yêu cầu
           | new PropertyResourceBundle(reader)
           v
ResourceBundle quản lý chuỗi cha và cache theo Control
~~~

Đây là **mô tả cơ chế**, không phải đoạn Java độc lập. Khi thực hiện `Control.newBundle`, cần xử lý đúng `format`, `loader`, cờ `reload`, URL connection/caching và đóng stream; không dùng một bộ tài nguyên duy nhất cho mọi candidate rồi cho rằng fallback của `getBundle` vẫn đúng.

**Giới hạn module:** các overload `ResourceBundle.getBundle` nhận `ResourceBundle.Control` không được hỗ trợ trong ngữ cảnh named modules theo hợp đồng Java 17; có thể ném `UnsupportedOperationException`. Với JPMS named modules, cần xem xét cơ chế resource bundle provider/module thích hợp, không sao chép mẫu Control của classpath mà không kiểm tra.

### Có cần tùy biến Control chỉ để đọc UTF-8?

Với Java 17, `PropertyResourceBundle(InputStream)` thông thường **đã ưu tiên UTF-8**. Nếu tất cả tài nguyên được chuẩn hóa UTF-8, ứng dụng thường không cần một `Control` riêng chỉ để hỗ trợ chữ Unicode. Chỉ phát triển đường nạp Reader tùy chỉnh khi có yêu cầu cụ thể như charset khác, chính sách decoder, nguồn tài nguyên riêng, hoặc cần chống fallback encoding tự động.

Dù dùng cách nào, kiểm thử đường chạy thực tế của `getBundle` trên bản triển khai để chắc chắn tài nguyên tiếng Việt, lựa chọn locale, fallback khóa và resource caching đúng như mong muốn.

## 8. Ví dụ tệp properties thực tế và cách kiểm thử

Một dự án Gradle/Maven thường đặt tài nguyên trong `src/main/resources`:

~~~text
src/main/resources/
  i18n/
    messages.properties
    messages_vi.properties
    messages_vi_VN.properties
~~~

Ví dụ `i18n/messages_vi.properties` lưu bằng UTF-8:

~~~properties
title=Chào mừng
button.login=Đăng nhập
message=Bạn có {0} thông báo
~~~

Khi đọc riêng file từ classpath bằng Reader UTF-8, dùng:

~~~java
try (InputStream input = MyApplication.class.getClassLoader()
        .getResourceAsStream("i18n/messages_vi.properties")) {
    if (input == null) {
        throw new FileNotFoundException("Missing messages_vi.properties");
    }
    try (Reader reader =
            new InputStreamReader(input, StandardCharsets.UTF_8)) {
        PropertyResourceBundle bundle =
                new PropertyResourceBundle(reader);
        System.out.println(bundle.getString("title"));
    }
}
~~~

Đây là **đoạn mã minh họa** trong lớp `MyApplication` có import cần thiết, không phải chương trình độc lập. Với tệp đúng như trên, `getString("title")` trả `Chào mừng`. Mẫu chỉ đọc riêng `messages_vi.properties`, không tự kết nối `messages.properties` làm cha.

`{0}` trong `message` không được `PropertyResourceBundle` tự thay bằng dữ liệu đầu vào. Nếu cần định dạng tham số, kết hợp `MessageFormat` với `Locale` phù hợp; đó là bước khác với charset. Không dùng `String.format` để mong thay placeholder kiểu `{0}`.

### Checklist kiểm thử thực tế

- Kiểm tra byte tệp thật được lưu đúng encoding đã cam kết; bộ soạn thảo và công cụ build không tự đổi mã hóa.
- Có chuỗi tiếng Việt nhiều dấu, ví dụ `Đăng nhập`, `Tạm biệt`, `Ưu đãi`, để phát hiện decode sai.
- Kiểm tra round trip hoặc so sánh với **chuỗi Unicode mong đợi** sau `getString`, không chỉ nhìn bằng mắt.
- Kiểm tra lỗi khi tệp biến mất; với classpath, xử lý `getResourceAsStream == null`.
- Kiểm tra byte UTF-8 không hợp lệ và kỳ vọng trả lỗi hay thay thế được thiết kế.
- Kiểm tra cú pháp `.properties`, đặc biệt backslash, Unicode escape `\uXXXX`, dấu `=`, `:` và khoảng trắng.
- Nếu dùng `getBundle`, kiểm tra cả fallback locale, khóa kế thừa, tên `baseName`, đóng gói resource và cache.
- Với tài nguyên legacy, kiểm tra rõ charset và đường chuyển đổi về UTF-8, tránh tải cùng tệp bằng hai encoding tùy môi trường.

## 9. Lỗi phổ biến và cách tránh

| Lỗi | Hệ quả | Cách làm đúng |
| --- | --- | --- |
| Dùng `InputStreamReader(stream)` không truyền charset | Có thể phụ thuộc charset mặc định môi trường, nhất là trên Java 17 | Truyền `StandardCharsets.UTF_8` hoặc charset đã cam kết |
| Lấy `Locale` để đoán charset | Dữ liệu bị decode sai dù locale đúng | Charset độc lập với language/region |
| Cho rằng `Properties.load(InputStream)` và `PropertyResourceBundle(InputStream)` giống nhau | Nhầm chính sách ISO-8859-1 và UTF-8 | Đọc đúng hợp đồng từng API của Java 17 |
| Dùng ISO-8859-1 để đọc tệp UTF-8 | Chữ có dấu bị hỏng | Chuẩn hóa UTF-8 và truyền Reader tương ứng |
| Dựa vào fallback Latin-1 của constructor `InputStream` để phát hiện encoding đúng | Dữ liệu hợp lệ nhưng vẫn có thể bị hiểu sai | Dùng hợp đồng encoding rõ ràng, kiểm thử dữ liệu |
| Dùng `InputStreamReader(stream, UTF_8)` rồi nghĩ mọi byte lỗi đều được báo | Decoder có thể thay byte lỗi thành ký tự thay thế | Dùng `CharsetDecoder` với `REPORT` khi yêu cầu strict |
| Tự tạo `PropertyResourceBundle(reader)` và mong có parent từ các file locale khác | Không thấy khóa nằm ở bundle cha | Dùng cơ chế `getBundle` hoặc tự xây chuỗi cha có kiểm soát |
| Chỉ đọc resource trên disk bằng `Path` khi app đóng gói JAR | Không tìm được tệp | Dùng class loader/module resource API khi phù hợp |
| Không đóng `Reader` | Rò rỉ descriptor/stream | `try-with-resources` |
| Chỉnh `java.util.PropertyResourceBundle.encoding` giữa runtime | Không điều khiển được Reader và có thể không có tác dụng | Cấu hình từ đầu hoặc tạo Reader charset tường minh |
| Chỉ kiểm tra key có tồn tại mà bỏ qua nội dung | Mojibake vẫn được trả qua `getString` | Kiểm tra chuỗi Unicode đúng sau khi tải |

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Một file properties được lưu UTF-8 có giá trị `title=Đăng nhập`. Nên mở file bằng API nào nếu yêu cầu chắc chắn giải mã UTF-8?

**Đáp án:** Dùng `Files.newBufferedReader(path, StandardCharsets.UTF_8)` hoặc `new InputStreamReader(input, StandardCharsets.UTF_8)`, rồi truyền Reader vào `new PropertyResourceBundle(reader)`. Nếu cần phát hiện byte hỏng nghiêm ngặt, dùng Decoder có `CodingErrorAction.REPORT`.

**Câu 2.** Vì sao dùng `PropertyResourceBundle(InputStream)` trên Java 17 thường đọc được file UTF-8 mà không truyền charset, nhưng `Properties.load(InputStream)` lại có thể tạo lỗi chữ?

**Đáp án:** Hai API có hợp đồng encoding khác nhau. `PropertyResourceBundle(InputStream)` Java 17 ưu tiên UTF-8 với cơ chế tương thích ISO-8859-1; `Properties.load(InputStream)` dùng ISO-8859-1.

**Câu 3.** Tại sao đọc tệp bằng Reader UTF-8 rồi xây một `PropertyResourceBundle` trực tiếp không tự kế thừa thông điệp từ `messages.properties`?

**Đáp án:** Constructor nhận Reader chỉ nạp một bundle, không chạy thuật toán `ResourceBundle.getBundle` lựa chọn candidate locale và thiết lập chuỗi parent. Quy tắc charset và quy tắc bundle fallback là hai cơ chế độc lập.

**Câu 4.** CharsetReader có giúp `MessageFormat` tự thay `{0}` trong chuỗi không?

**Đáp án:** Không. Reader chỉ giải mã byte; `PropertyResourceBundle` đọc khóa/giá trị. Muốn thay tham số, dùng `MessageFormat` hoặc một bộ format thông điệp phù hợp.

**Câu 5.** Một file Latin-1 cũ cần giữ nguyên đến khi migrate. Có nên sửa `Locale.setDefault(Locale.US)` để đọc đúng không?

**Đáp án:** Không. `Locale.setDefault` không thay charset cho byte stream. Dùng Reader với `StandardCharsets.ISO_8859_1` theo hợp đồng file rồi kiểm thử, sau đó có thể chuyển đổi file sang UTF-8 theo kế hoạch.

## 11. Kết luận và tài liệu chính thức

Khi kiểm soát mã hóa tệp tài nguyên, cách ổn định là chọn **charset theo hợp đồng dữ liệu**, tạo `Reader` với charset đó, đọc `.properties` qua `PropertyResourceBundle(Reader)`, và xác minh kết quả Unicode. Với dữ liệu quan trọng, dùng decoder strict để không chấp nhận byte lỗi. Khi cần tự động lựa chọn locale và chuỗi tài nguyên cha, hãy kiểm tra riêng cơ chế `ResourceBundle.getBundle` và chỉ tùy biến đường nạp khi có lý do kỹ thuật cụ thể.

Tài liệu tham khảo:

- [PropertyResourceBundle — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PropertyResourceBundle.html): constructor `Reader` và `InputStream`, encoding và ngoại lệ.
- [InputStreamReader — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html): lựa chọn charset và decoder.
- [Files.newBufferedReader — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): đọc tệp với charset chỉ định.
- [Properties — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Properties.html): phân biệt `load(InputStream)` và `load(Reader)`.
- [ResourceBundle.Control — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.Control.html): tùy biến tải bundle và giới hạn trong named modules.

**Ghi nhớ:** `Reader + Charset` quyết định cách giải mã byte, `PropertyResourceBundle` quyết định cách phân tích các cặp khóa–giá trị, còn `ResourceBundle.getBundle` quyết định cách tìm bundle theo locale và chuỗi cha. Kiểm soát đúng từng lớp giúp bản dịch không bị hỏng và hành vi nhất quán giữa các môi trường Java.
