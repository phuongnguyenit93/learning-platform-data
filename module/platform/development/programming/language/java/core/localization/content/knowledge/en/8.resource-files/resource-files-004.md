# java.util.PropertyResourceBundle.encoding và thời điểm có hiệu lực

## 1. Vấn đề cần hiểu

Trong Java, một bộ tài nguyên ngôn ngữ (*resource bundle*) thường được lưu dưới dạng tệp `.properties`. Nếu tệp chứa dấu tiếng Việt, tiếng Nhật, tiếng Đức hoặc các ký tự Unicode khác, chương trình phải **giải mã đúng các byte của tệp thành ký tự** trước khi dùng giá trị.

Từ Java 9, `java.util.PropertyResourceBundle` có cơ chế đọc tệp `.properties` theo **UTF-8 trước**, và trong chế độ mặc định sẽ thử lại bằng **ISO-8859-1** nếu phát hiện một số lỗi giải mã UTF-8. Java cho phép ép chế độ đọc bằng **system property**:

~~~text
java.util.PropertyResourceBundle.encoding
~~~

Tính chất đặc biệt cần nhớ là giá trị này được **đọc và đánh giá khi lớp `PropertyResourceBundle` khởi tạo lần đầu trong JVM**. Thay đổi nó về sau, kể cả xóa hoặc ghi lại bằng `System.setProperty(...)`, **không khiến chế độ giải mã của lớp tự cập nhật**.

Ví dụ khởi chạy:

~~~bash
java -Djava.util.PropertyResourceBundle.encoding=UTF-8 -cp . BundleEncodingDemo
~~~

Khi chạy câu lệnh này, `-D...` là cấu hình **JVM**, đặt trước tên lớp main. Nó không phải thuộc tính được khai báo trong `Messages.properties`, không phải `Locale` và cũng không phải giá trị được đọc lại mỗi lần gọi `ResourceBundle.getBundle(...)`.

**Mục tiêu bài học:** hiểu chính xác ba chế độ giải mã, thời điểm cấu hình có hiệu lực, phạm vi tác động và cách kiểm tra bằng ví dụ Java 17+; từ đó tránh lỗi ký tự bị biến dạng (*mojibake*) và các cấu hình không có tác dụng trong môi trường chạy thật.

## 2. Phân biệt byte, charset, Locale và ResourceBundle

Xét tài nguyên UTF-8 có nội dung:

~~~properties
welcome=Xin chào
~~~

Trước khi ứng dụng thấy chuỗi Java `"Xin chào"`, chuỗi byte UTF-8 của tệp phải được giải mã. Chữ `à` trong UTF-8 được biểu diễn bằng hai byte `C3 A0`. Nếu hai byte đó bị giải mã riêng rẽ theo ISO-8859-1, ứng dụng sẽ thấy ký tự sai dù tệp gốc vẫn đúng.

| Thành phần | Vai trò | Có tự chọn charset của `.properties` không? |
| --- | --- | --- |
| File `Messages_vi.properties` | Chứa byte, khóa và giá trị của bản dịch | Tệp phải được lưu theo charset phù hợp |
| `Locale.forLanguageTag("vi-VN")` | Yêu cầu ngôn ngữ/vùng để chọn bundle | **Không** |
| `ResourceBundle.getBundle(...)` | Tìm và trả resource bundle theo các ứng viên locale | Tự dùng cơ chế tải tài nguyên tương ứng |
| `PropertyResourceBundle` | Đọc tài nguyên dạng key/value từ `.properties` | **Có**, khi tải qua `InputStream` theo quy tắc Java 9+ |
| `java.util.PropertyResourceBundle.encoding` | Chọn chế độ giải mã của `PropertyResourceBundle(InputStream)` | **Có**, nhưng được chốt lúc lớp khởi tạo |
| `Charset` của `Reader` | Quy định cách `Reader` biến byte thành ký tự | Dùng riêng khi tạo `Reader` |
| Charset của terminal/stdout | Quy định cách Java ghi ký tự ra màn hình | Không thay đổi cách đọc tài nguyên |

Một `Locale` đúng không sửa được tài nguyên đã đọc sai encoding. Tương tự, việc console không hiển thị được Unicode chưa chứng minh dữ liệu đã bị đọc sai; cần phân biệt lỗi **đọc tệp**, **biểu diễn trong Java** và **ghi ra console**.

## 3. Ba chế độ của `PropertyResourceBundle(InputStream)` trong Java 9+

Đối với trình tải tài nguyên chuẩn dựa trên `InputStream`:

| Cấu hình system property lúc lớp khởi tạo | Cách giải mã | Nếu gặp byte UTF-8 không hợp lệ |
| --- | --- | --- |
| **Không cấu hình**, hoặc giá trị không hợp lệ | Đọc bằng **UTF-8**, lỗi `MalformedInputException`/`UnmappableCharacterException` thì đọc lại từ đầu bằng **ISO-8859-1** | Thử lại ISO-8859-1 |
| `UTF-8` | Chỉ đọc bằng **UTF-8** | Phát sinh lỗi giải mã, **không fallback** sang ISO-8859-1 |
| `ISO-8859-1` | Chỉ đọc bằng **ISO-8859-1** | Không thử UTF-8; các byte được giải mã theo Latin-1 |

Chỉ có hai giá trị hợp lệ được tài liệu Java định nghĩa chính xác:

~~~text
UTF-8
ISO-8859-1
~~~

Các chuỗi như `utf8`, `UTF8`, `Latin1`, `windows-1258` hoặc `CP1252` không phải các giá trị được nhận cho system property này; **giá trị khác bị bỏ qua**, tức dùng quy tắc mặc định. Không dùng cách viết không chuẩn rồi tưởng đã ép chế độ đọc.

### 3.1. Mặc định: UTF-8, có fallback sang ISO-8859-1

Trong chế độ mặc định, Java cố giải mã theo UTF-8. Nếu một byte sequence không hợp lệ theo UTF-8 gây `MalformedInputException` hoặc `UnmappableCharacterException`, `PropertyResourceBundle` có thể đặt lại việc đọc và thử lại toàn bộ dữ liệu theo ISO-8859-1. Đây là một cơ chế tương thích với resource bundle cũ từ thời Java 8.

**Cần lưu ý:** fallback này dựa vào *lỗi giải mã*, không phải thuật toán xác định chính xác charset của file. Một file Latin-1 tình cờ có chuỗi byte hợp lệ theo UTF-8 có thể bị hiểu sai mà không kích hoạt fallback. Vì thế không nên dựa vào cơ chế tự đoán để quản lý tệp đa ngôn ngữ lâu dài; hãy chuẩn hóa tệp sang UTF-8.

### 3.2. Ép `UTF-8`

~~~bash
java -Djava.util.PropertyResourceBundle.encoding=UTF-8 -cp . BundleEncodingDemo
~~~

Chế độ này chỉ chấp nhận UTF-8. Khi gặp byte sequence không hợp lệ theo UTF-8, quá trình đọc sẽ báo lỗi thay vì âm thầm chuyển sang ISO-8859-1. Điều đó hữu ích khi muốn đảm bảo mọi file resource bundle trong sản phẩm thực sự được lưu bằng UTF-8.

Nếu gọi trực tiếp constructor `new PropertyResourceBundle(InputStream)`, lỗi có thể được nhận qua `IOException`/các ngoại lệ giải mã chuyên biệt. Khi tải qua `ResourceBundle.getBundle(...)`, lỗi có thể xuất hiện qua luồng exception của cơ chế tìm/tải bundle; không nên khẳng định mọi lời gọi đều phát sinh cùng một loại exception gốc, vì cơ chế chọn resource và xử lý lỗi cũng tham gia.

### 3.3. Ép `ISO-8859-1`

~~~bash
java -Djava.util.PropertyResourceBundle.encoding=ISO-8859-1 -cp . BundleEncodingDemo
~~~

Chế độ này dành cho môi trường cố ý duy trì tài nguyên byte Latin-1. Với file chứa ký tự nằm ngoài ISO-8859-1, sử dụng cú pháp Unicode escape như `\u1EA1` theo định dạng `.properties`, hoặc chuyển tài nguyên sang UTF-8 và chạy theo chính sách UTF-8.

**Cảnh báo:** nếu file thực tế là UTF-8 nhưng ép ISO-8859-1, các byte Unicode nhiều byte bị coi là nhiều ký tự Latin-1. Ứng dụng có thể hiển thị chuỗi sai mà không phát sinh lỗi. Đổi `Locale` hay xóa cache không khắc phục nguyên nhân chọn sai charset.

## 4. Thời điểm có hiệu lực: chốt khi lớp khởi tạo

Đây là trọng tâm của bài. Tài liệu `PropertyResourceBundle` quy định system property được **đọc và đánh giá khi khởi tạo lớp này**.

~~~text
Khởi động JVM
      |
      +-- Nhận -Djava.util.PropertyResourceBundle.encoding=...
      |
      v
PropertyResourceBundle được khởi tạo lần đầu
      |
      +-- Đọc/đánh giá system property một lần
      +-- Chốt chế độ giải mã
      |
      v
Tạo các PropertyResourceBundle sau đó
      |
      +-- Dùng chế độ đã được chốt
      |
      v
System.setProperty("java.util.PropertyResourceBundle.encoding", ...)
      |
      +-- KHÔNG cập nhật chế độ đã chốt
~~~

**Hệ quả thực tế:**

1. Đặt `-Djava.util.PropertyResourceBundle.encoding=...` **trước khi JVM chạy mã ứng dụng** là cách rõ ràng nhất để đảm bảo lớp đọc đúng cấu hình.
2. Lúc nào `PropertyResourceBundle` khởi tạo có thể do code của bạn hoặc thư viện/framework gọi trước. Không thể luôn dựa vào suy đoán rằng `main()` sẽ là nơi đầu tiên động tới nó.
3. `System.setProperty("java.util.PropertyResourceBundle.encoding", "UTF-8")` **chỉ có khả năng tác động nếu lớp chưa khởi tạo**. Vì thứ tự khởi tạo trong ứng dụng lớn khó kiểm soát, không nên dùng thay cho cấu hình khởi động JVM.
4. Khi lớp đã khởi tạo, **thay đổi hoặc xóa property không có tác dụng** với chế độ giải mã của lớp.
5. Việc gọi `ResourceBundle.clearCache()` có thể ảnh hưởng các bundle được cache, nhưng **không khởi tạo lại lớp `PropertyResourceBundle`**, nên không làm JVM đọc lại encoding property.
6. Mỗi tiến trình JVM mới có một lần khởi tạo lớp riêng. Muốn đổi chính sách một cách tin cậy, cấu hình khác lúc khởi động và chạy lại JVM.

### 4.1. Vì sao `System.setProperty(...)` trong request không phù hợp?

Ví dụ sai về mặt thiết kế:

~~~java
// Không làm việc này bên trong handler của một request.
System.setProperty(
        "java.util.PropertyResourceBundle.encoding",
        "UTF-8"
);
ResourceBundle bundle =
        ResourceBundle.getBundle("Messages", Locale.forLanguageTag("vi-VN"));
~~~

Đây là đoạn minh họa, yêu cầu import `java.util.ResourceBundle` và `java.util.Locale`. Lỗi không nằm ở cú pháp: system property là cấu hình **toàn cục**, còn `PropertyResourceBundle` đọc nó một lần khi khởi tạo. Nếu lớp đã dùng từ trước, lệnh `System.setProperty` không thể thay đổi chế độ; nếu chưa dùng, ứng dụng đang phụ thuộc vào thời điểm tải lớp khó kiểm soát.

Đặc biệt, không dùng cách đặt property khác nhau cho từng người dùng, từng ngôn ngữ hoặc từng request. **Charset của các tệp resource** là chính sách đóng gói/cấu hình tải tài nguyên, không phải lựa chọn địa phương hóa của người dùng.

### 4.2. Cách cấu hình khi triển khai

Đặt JVM option ngay tại lệnh chạy hoặc cấu hình JVM arguments trong công cụ khởi động:

~~~bash
java -Djava.util.PropertyResourceBundle.encoding=UTF-8 -jar app.jar
~~~

Trong cấu hình IDE, build hoặc container, cần chắc rằng tham số này được truyền cho **JVM chạy ứng dụng**. Ví dụ: cấu hình thuộc tính trong file `application.properties` của Spring Boot **không tự động biến nó thành JVM system property trước lúc `PropertyResourceBundle` khởi tạo**. `-D` được đặt trước `-jar` hoặc tên main class. Khi chạy một ứng dụng đã có tiến trình JVM, thay cấu hình trên máy hoặc sửa source file mà không khởi động lại sẽ không làm chế độ giải mã đang chốt đổi theo.

## 5. Ví dụ chạy được: file UTF-8 và ba chế độ khởi động

Bài thực hành sau dùng Java 17+, chạy trên **classpath** trong một thư mục demo riêng. Tạo hai file:

~~~text
demo/
├── BundleEncodingDemo.java
└── Messages_vi.properties
~~~

Lưu file `Messages_vi.properties` bằng **UTF-8** (có thể chọn UTF-8 không BOM để nhất quán công cụ):

~~~properties
welcome=Xin chào Việt Nam
farewell=Tạm biệt
~~~

Tạo `BundleEncodingDemo.java`:

~~~java
import java.util.Locale;
import java.util.ResourceBundle;

public class BundleEncodingDemo {
    public static void main(String[] args) {
        Locale requested = Locale.forLanguageTag("vi-VN");
        ResourceBundle messages =
                ResourceBundle.getBundle("Messages", requested);

        System.out.println("Requested: " + requested.toLanguageTag());
        System.out.println("Resolved: " + messages.getLocale().toLanguageTag());
        System.out.println(messages.getString("welcome"));
        System.out.println(messages.getString("farewell"));
    }
}
~~~

Từ thư mục `demo`, biên dịch:

~~~bash
javac -encoding UTF-8 BundleEncodingDemo.java
~~~

### 5.1. Chạy chế độ mặc định

~~~bash
java -cp . BundleEncodingDemo
~~~

Với file được lưu UTF-8, kết quả:

~~~text
Requested: vi-VN
Resolved: vi
Xin chào Việt Nam
Tạm biệt
~~~

Giá trị `Resolved: vi` là do demo chỉ có bundle `Messages_vi.properties`, không có `Messages_vi_VN.properties`. Đây là **locale của bundle được chọn**, tách biệt với encoding dùng để đọc giá trị.

### 5.2. Ép UTF-8 lúc khởi động

~~~bash
java -Djava.util.PropertyResourceBundle.encoding=UTF-8 -cp . BundleEncodingDemo
~~~

Kết quả vẫn là:

~~~text
Requested: vi-VN
Resolved: vi
Xin chào Việt Nam
Tạm biệt
~~~

Ở đây file UTF-8 hợp lệ, nên chế độ mặc định và chế độ ép UTF-8 cùng đọc chính xác. Tuy nhiên ép UTF-8 tạo ra khác biệt quan trọng nếu một file trong hệ thống chứa **byte không hợp lệ**: ứng dụng báo lỗi giải mã thay vì dùng fallback Latin-1.

### 5.3. Ép ISO-8859-1 cho file UTF-8

~~~bash
java -Djava.util.PropertyResourceBundle.encoding=ISO-8859-1 -cp . BundleEncodingDemo
~~~

Hai dòng đầu vẫn mô tả locale như trước; phần tiếng Việt sau đó có thể biến thành ký tự sai (*mojibake*), vì các byte UTF-8 bị giải mã như Latin-1. **Không** lấy đầu ra sai đó làm chuẩn cố định: nhiều ký tự Unicode có thể trở thành ký tự điều khiển hoặc khoảng trắng đặc biệt, cách console hiển thị phụ thuộc môi trường.

Bài kiểm tra nên tập trung vào nguyên nhân và tính đúng của chuỗi trong Java thay vì chỉ quan sát ảnh chụp console. Có thể so sánh `messages.getString("welcome").equals("Xin chào Việt Nam")` để biết kết quả giải mã đúng hay sai, miễn source `.java` đã được biên dịch với UTF-8.

## 6. Ví dụ byte Latin-1: chế độ mặc định fallback còn UTF-8 nghiêm ngặt thì lỗi

Ví dụ sau tạo trực tiếp các byte hợp lệ ISO-8859-1 nhưng **không** hợp lệ UTF-8, vì byte `E9` đứng một mình. Do đó không cần công cụ tạo file cũ.

Lưu `LegacyBytesDemo.java`:

~~~java
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.util.PropertyResourceBundle;

public class LegacyBytesDemo {
    public static void main(String[] args) throws Exception {
        // Một file .properties giả lập: text=<byte E9> + newline.
        // E9 là ký tự é trong ISO-8859-1, không hợp lệ khi đứng
        // một mình trong UTF-8.
        byte[] legacyLatin1 = {
                't', 'e', 'x', 't', '=', (byte) 0xE9, '\n'
        };

        try (InputStream input =
                     new ByteArrayInputStream(legacyLatin1)) {
            PropertyResourceBundle bundle =
                    new PropertyResourceBundle(input);
            System.out.println(
                    "Decoded correctly: "
                    + "é".equals(bundle.getString("text"))
            );
        }
    }
}
~~~

Chạy ba **tiến trình riêng**:

~~~bash
javac -encoding UTF-8 LegacyBytesDemo.java

java -cp . LegacyBytesDemo

java -Djava.util.PropertyResourceBundle.encoding=ISO-8859-1 -cp . LegacyBytesDemo

java -Djava.util.PropertyResourceBundle.encoding=UTF-8 -cp . LegacyBytesDemo
~~~

Diễn giải kết quả:

| Cách chạy | Kết quả dự kiến |
| --- | --- |
| Không đặt `-D` | `Decoded correctly: true`, vì thử UTF-8 thất bại rồi đọc lại ISO-8859-1 |
| Ép `ISO-8859-1` | `Decoded correctly: true` |
| Ép `UTF-8` | Phát sinh lỗi giải mã (ví dụ `MalformedInputException`), **không** in dòng thành công |

Điểm đáng chú ý là các lần chạy dùng **cùng một chương trình và cùng một mảng byte**, nhưng cấu hình JVM trước khi lớp được khởi tạo dẫn đến kết quả khác nhau. Đây là bằng chứng thực tế cho ý nghĩa của system property và chế độ fallback.

Không nên sửa system property nhiều lần trong một JVM và gọi lại constructor để “thử ba chế độ”: cách đó **không kiểm tra đúng** cơ chế đọc một lần. Dùng **ba tiến trình Java riêng** như lệnh trên.

## 7. `InputStream` khác `Reader`: phạm vi thật sự của system property

`PropertyResourceBundle` có hai constructor quan trọng:

~~~java
new PropertyResourceBundle(inputStream)
new PropertyResourceBundle(reader)
~~~

- Với `InputStream`, lớp phải giải mã byte, nên áp dụng chính sách UTF-8/ISO-8859-1 và system property đã nói.
- Với `Reader`, ký tự **đã được giải mã** bởi `Reader`. Constructor nhận `Reader` đọc các ký tự đó; system property `java.util.PropertyResourceBundle.encoding` **không điều khiển charset của Reader**.

### Ví dụ dùng Reader với charset tường minh

Lưu thành `ReaderEncodingDemo.java`:

~~~java
import java.io.ByteArrayInputStream;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.util.PropertyResourceBundle;

public class ReaderEncodingDemo {
    public static void main(String[] args) throws Exception {
        byte[] raw = "text=Tiếng Việt\n"
                .getBytes(StandardCharsets.UTF_8);

        try (Reader reader = new InputStreamReader(
                new ByteArrayInputStream(raw),
                StandardCharsets.UTF_8
        )) {
            PropertyResourceBundle bundle =
                    new PropertyResourceBundle(reader);
            System.out.println(bundle.getString("text"));
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ReaderEncodingDemo.java

java -cp . ReaderEncodingDemo

java -Djava.util.PropertyResourceBundle.encoding=ISO-8859-1 -cp . ReaderEncodingDemo
~~~

Cả hai lần đều in:

~~~text
Tiếng Việt
~~~

Nguyên nhân: `InputStreamReader(..., StandardCharsets.UTF_8)` đã quyết định charset trước khi `PropertyResourceBundle(Reader)` nhận dữ liệu. Lựa chọn này cho phép một loader **tự thiết kế** đọc tài nguyên theo charset cụ thể mà không dựa vào system property của `PropertyResourceBundle(InputStream)`. Nếu dự án tùy biến `ResourceBundle.Control.newBundle(...)` hoặc có cơ chế đọc file riêng, cần kiểm tra **đường tải thực tế**, không suy ra rằng system property tác động đến mọi thư viện đọc `.properties`.

### `java.util.Properties.load(InputStream)` là API khác

Một nhầm lẫn đặc biệt phổ biến:

~~~java
Properties properties = new Properties();
try (InputStream input = Files.newInputStream(path)) {
    properties.load(input);
}
~~~

Đây là **mảnh mã minh họa trong method**, cần import `java.util.Properties`, `java.io.InputStream`, `java.nio.file.Files` và `java.nio.file.Path` (biến `path` phải có sẵn).

`Properties.load(InputStream)` vẫn diễn giải bytes theo **ISO-8859-1**, và ký tự ngoài Latin-1 cần escape theo cú pháp `\uXXXX`. Nó **không** chuyển sang UTF-8 chỉ vì chạy Java 17 hay vì đã đặt `java.util.PropertyResourceBundle.encoding=UTF-8`.

Ngược lại, `Properties.load(Reader)` đọc các ký tự qua `Reader`, nên có thể dùng:

~~~java
try (Reader reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {
    properties.load(reader);
}
~~~

Đây cũng là mảnh mã minh họa trong method, cần import `java.io.Reader` và `java.nio.charset.StandardCharsets` bên cạnh các import `Properties`/`Files`/`Path` nói trên. Charset được chọn ở `newBufferedReader`.

**Ghi nhớ sự phân biệt:**

| API | Quy tắc giải mã |
| --- | --- |
| `PropertyResourceBundle(InputStream)`, Java 9+ | UTF-8 mặc định, có fallback ISO-8859-1; chịu system property khi lớp khởi tạo |
| `PropertyResourceBundle(Reader)` | Theo charset của `Reader` đã tạo |
| `Properties.load(InputStream)` | ISO-8859-1 theo hợp đồng API, độc lập với property trên |
| `Properties.load(Reader)` | Theo charset của `Reader` |
| `ResourceBundle.getBundle(...)` | Tùy cơ chế tải bundle thực tế; với tệp properties và loader chuẩn, liên quan đến `PropertyResourceBundle` |

Đừng nhầm quy tắc giải mã tài nguyên với các lựa chọn locale trong `ResourceBundle.getBundle(baseName, requestedLocale)`. Chọn locale quyết định **file nào** được tìm; charset quyết định **byte của file đó** được hiểu thành ký tự nào.

## 8. Khác biệt Java 8 và Java 9+

| Phiên bản/cơ chế | Đọc `PropertyResourceBundle` từ `InputStream` |
| --- | --- |
| Java 8, hành vi chuẩn | ISO-8859-1; ký tự ngoài Latin-1 thường phải dùng escape `\uXXXX` |
| Java 9 trở lên | UTF-8 mặc định, fallback ISO-8859-1 khi gặp lỗi giải mã |
| Java 9+ với `-D...encoding=UTF-8` | Chỉ dùng UTF-8 |
| Java 9+ với `-D...encoding=ISO-8859-1` | Chỉ dùng ISO-8859-1 |

Đây là thay đổi được giới thiệu qua **JEP 226 — UTF-8 Property Resource Bundles**. Với dự án còn phải chạy trên Java 8, kiểm tra build và tài nguyên thật: file UTF-8 thô có dấu tiếng Việt không thể được mặc định Java 8 `PropertyResourceBundle` đọc đúng như Java 17. Một lựa chọn tương thích là chuyển ký tự ngoài Latin-1 thành Unicode escape trong tài nguyên kế thừa; nếu chỉ hỗ trợ Java 17+, nên chuẩn hóa các bundle thành UTF-8.

Unicode escape có dạng như sau:

~~~properties
# \u00E9 biểu diễn chữ é
word=caf\u00E9
~~~

Chuỗi escape `\u00E9` chứa các ký tự ASCII trong tệp nên có thể đọc được dưới cả UTF-8 và ISO-8859-1. Đây là một phương án tương thích, không phải yêu cầu bắt buộc đối với mọi file `.properties` trên JDK mới.

## 9. Chẩn đoán lỗi sai ký tự trong thực tế

Khi bản dịch có dấu bị lỗi, xác minh theo trình tự có thể kiểm chứng:

1. **Byte gốc:** File trong repository và file được đóng gói vào JAR có thật sự là UTF-8 không? Build có bước *resource filtering*, copy, convert encoding hoặc đóng gói lại không?
2. **Đường tải:** Ứng dụng dùng `ResourceBundle.getBundle` với bundle `.properties` chuẩn, hay tự tạo `PropertyResourceBundle(Reader)`, `Properties.load` hoặc một thư viện i18n riêng?
3. **Cấu hình JVM:** In giá trị `System.getProperty("java.util.PropertyResourceBundle.encoding")` để biết JVM được cấu hình gì, nhưng **đừng suy ra** việc sửa giá trị này lúc chạy sẽ làm chế độ đang chốt thay đổi.
4. **Thời điểm khởi tạo:** Có framework hoặc thư viện nào dùng `PropertyResourceBundle` trước khi logic thiết lập property của ứng dụng chạy không? Nếu có, property đã được đánh giá rồi.
5. **Cache:** Resource bundle có thể được cache. Thay file hoặc gọi `ResourceBundle.clearCache()` có thể giúp thử lại nội dung, nhưng **không** ép class đọc lại system property.
6. **String trong Java:** So sánh giá trị đọc được với chuỗi mong đợi, hoặc kiểm tra Unicode code point. Nếu Java string đúng nhưng console hiển thị sai, điều tra charset/font/terminal riêng.
7. **Tương thích phiên bản:** Xác nhận JDK runtime thực tế. Không lấy quy tắc của Java 17 để dự đoán ứng dụng vẫn chạy Java 8.
8. **Khả năng UTF-8 hợp lệ nhưng sai nghĩa:** Không mặc định một file Latin-1 bị đọc sai sẽ luôn ném lỗi. Chế độ mặc định chỉ fallback khi xảy ra lỗi giải mã quy định.

### Phân biệt lỗi thường gặp

| Dấu hiệu | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| UTF-8 hợp lệ nhưng hiển thị sai khi ép ISO-8859-1 | Chọn sai charset | Bỏ ép Latin-1, chuẩn hóa file UTF-8, chạy lại JVM |
| Có lỗi giải mã khi ép UTF-8 | Resource chứa byte không hợp lệ UTF-8 | Chuyển file nguồn sang UTF-8 hoặc sửa byte; kiểm tra đóng gói |
| `System.setProperty` gọi rồi nhưng không tác động | `PropertyResourceBundle` đã khởi tạo | Đặt `-D` từ lúc start JVM, khởi động lại |
| `clearCache()` xong vẫn đọc theo charset cũ | Cache không chi phối giá trị static đã chốt | Sửa cấu hình khởi động và khởi động tiến trình mới |
| Dùng `Properties.load(InputStream)` vẫn đọc Latin-1 | Đây là hợp đồng của `Properties` | Dùng `Properties.load(Reader)` với charset rõ ràng |
| `Reader` luôn đọc UTF-8 dù JVM ép Latin-1 | Charset đã được Reader quyết định | Kiểm tra nơi tạo Reader và loại constructor |
| String Java đúng nhưng console hiển thị ô vuông/ký tự lạ | Font hoặc encoding đầu ra | Kiểm tra console, font và môi trường xuất kết quả |

## 10. Quy tắc thiết kế và kiểm thử

**Cấu hình ổn định:**

- Chọn một encoding thống nhất, thường là **UTF-8**, cho toàn bộ tệp tài nguyên của module.
- Nếu muốn phát hiện tệp sai charset ngay lúc tải, cân nhắc chạy Java 17+ với `-Djava.util.PropertyResourceBundle.encoding=UTF-8`.
- Truyền property ở startup JVM và kiểm tra tham số JVM thật của ứng dụng/container.
- Tránh thay `java.util.PropertyResourceBundle.encoding` bằng `System.setProperty` trong logic nghiệp vụ hoặc theo từng request.
- Không coi `ResourceBundle.clearCache` là cách làm mới cấu hình charset.
- Nếu có loader tùy biến hoặc `Reader`, ghi rõ charset tại nơi tạo Reader, kèm test trực tiếp.

**Bộ kiểm thử hữu ích:**

1. Có ít nhất một chuỗi tiếng Việt với dấu và một ký tự ngoài Latin-1 trong bundle UTF-8.
2. Test giá trị string sau `getString` bằng so sánh Unicode thực, không chỉ ảnh chụp console.
3. Khởi động **JVM riêng biệt** cho chế độ mặc định, UTF-8 nghiêm ngặt và ISO-8859-1 để kiểm chứng behavior.
4. Có một trường hợp byte Latin-1 không hợp lệ UTF-8 để xác nhận fallback mặc định và lỗi của chế độ UTF-8 nghiêm ngặt.
5. Kiểm tra file đã được build và đóng gói, không chỉ file trong source directory.
6. Khi hỗ trợ nhiều phiên bản Java, chạy integration test trên từng runtime mục tiêu.
7. Nếu dùng bộ nhớ đệm hoặc runtime reload resources, kiểm tra riêng quy tắc làm mới nội dung và quy tắc encoding startup.

## 11. Câu hỏi tự kiểm tra

1. Trong Java 17, `PropertyResourceBundle(InputStream)` sẽ làm gì nếu không có system property và tệp có byte không hợp lệ UTF-8? Điều gì thay đổi khi cấu hình `UTF-8`?
2. Vì sao đặt `System.setProperty("java.util.PropertyResourceBundle.encoding", "ISO-8859-1")` sau khi ứng dụng đã tải bundle không bảo đảm đổi cách đọc?
3. Nếu gọi `ResourceBundle.clearCache()` rồi tải lại file, giá trị encoding system property có được đọc lại từ đầu không? Vì sao?
4. Đặt `-Djava.util.PropertyResourceBundle.encoding=UTF-8` có làm `Properties.load(InputStream)` đọc UTF-8 không?
5. Tại sao `new PropertyResourceBundle(new InputStreamReader(stream, UTF_8))` không phụ thuộc encoding property giống constructor nhận `InputStream`?
6. Một file UTF-8 bị hiển thị sai khi ứng dụng ép `ISO-8859-1`. Hãy phân biệt lỗi giải mã byte của resource với lỗi console không hỗ trợ Unicode.
7. Nếu phải hỗ trợ cả Java 8 và Java 17, nên chọn cách lưu tệp `.properties` nào hoặc triển khai cơ chế đọc nào để tránh sai ký tự?

**Ghi nhớ:** Trong Java 9+, `PropertyResourceBundle(InputStream)` đọc **UTF-8 mặc định** và fallback sang **ISO-8859-1** khi phát hiện lỗi giải mã phù hợp. System property `java.util.PropertyResourceBundle.encoding` có thể ép chính xác `UTF-8` hoặc `ISO-8859-1`, nhưng **chỉ được đọc lúc lớp `PropertyResourceBundle` khởi tạo**. Muốn cấu hình đáng tin cậy, đặt `-D` khi khởi động JVM, quản lý tệp resource bằng UTF-8 và kiểm thử đúng đường tải tài nguyên.

### Tài liệu tham khảo

- [Java SE 17: PropertyResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PropertyResourceBundle.html) — encoding, hai constructor và thời điểm đọc system property.
- [Java SE 17: Properties](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Properties.html) — phân biệt `load(InputStream)` và `load(Reader)`.
- [OpenJDK JEP 226 — UTF-8 Property Resource Bundles](https://openjdk.org/jeps/226) — thay đổi từ Java 9 và mục tiêu tương thích.