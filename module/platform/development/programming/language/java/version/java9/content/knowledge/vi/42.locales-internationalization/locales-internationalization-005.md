# Cơ chế quay về ISO-8859-1 và lựa chọn bảng mã tường minh trong ResourceBundle (Java 9+)

## 1. Vấn đề cần giải quyết

Khi ứng dụng Java lưu chuỗi đa ngôn ngữ trong các tệp `.properties`, dữ liệu trên đĩa là **byte**, còn chương trình cần **chuỗi Unicode**. Bảng mã (charset) quyết định cách biến byte thành ký tự. Chọn sai bảng mã có thể khiến `Xin chào` thành văn bản lỗi như `Xin chÃ o`.

Từ **Java 9**, theo JEP 226, `PropertyResourceBundle` đọc tệp properties từ `InputStream` theo hướng **ưu tiên UTF-8**, đồng thời duy trì một cơ chế tương thích: nếu byte không giải mã hợp lệ bằng UTF-8 thì tự **đọc lại dưới dạng ISO-8859-1**. Cơ chế này vẫn được mô tả trong tài liệu Java SE hiện hành.

Bài này tập trung vào ba câu hỏi thực tế:

1. Khi nào Java thực sự quay về ISO-8859-1?
2. Khi nào phải khóa bảng mã rõ ràng để tránh lỗi âm thầm?
3. Vì sao `ResourceBundle` và `Properties.load(InputStream)` có quy tắc khác nhau?

**Phạm vi:** việc giải mã byte của tài nguyên `.properties` dùng cho bản dịch và những API đọc properties liên quan. Đây là một vấn đề khác với cách Java tìm locale thích hợp, và cũng khác với bảng mã của tệp mã nguồn Java.

## 2. Các khái niệm phải phân biệt

- **UTF-8:** mã hóa Unicode có độ dài biến đổi; hỗ trợ tiếng Việt, tiếng Nhật, emoji và các ngôn ngữ khác. Đây là lựa chọn mặc định nên dùng cho tệp bản dịch mới.
- **ISO-8859-1 (Latin-1):** bảng mã một byte cho mỗi ký tự trong tập Latin-1. Nó không biểu diễn trực tiếp đầy đủ tiếng Việt. Trong tệp properties đọc theo Latin-1, ký tự ngoài bảng mã có thể được thể hiện qua escape `\uXXXX`.
- **`Locale`:** chỉ định ngôn ngữ/vùng, ví dụ `Locale.forLanguageTag("vi-VN")`. Locale giúp chọn `Messages_vi.properties`, **không quyết định bảng mã** của tệp.
- **`ResourceBundle`:** API tra cứu chuỗi theo khóa và locale. Khi tải tài nguyên dạng `.properties`, triển khai chuẩn dùng `PropertyResourceBundle`.
- **`PropertyResourceBundle`:** bộ đọc/giữ các cặp khóa-giá trị cho bản dịch; có constructor nhận `InputStream` và constructor nhận `Reader`.
- **`Properties`:** lớp cấu hình khóa-giá trị thông thường. Phương thức `load(InputStream)` có quy tắc mã hóa riêng, không mặc nhiên hưởng quy tắc UTF-8 của `PropertyResourceBundle`.

Ví dụ với ký tự `é`:

| Nội dung | Byte hex | Kết quả khi giải mã |
| --- | --- | --- |
| `é` mã hóa UTF-8 | `C3 A9` | UTF-8 → `é` |
| Chính hai byte `C3 A9` nhưng đọc bằng ISO-8859-1 | `C3 A9` | ISO-8859-1 → `Ã©` |
| `é` mã hóa ISO-8859-1 | `E9` | UTF-8 → byte không hợp lệ; ISO-8859-1 → `é` |

Vì thế, **giải mã thành công không đồng nghĩa bảng mã được đoán đúng**. Đây là lý do để lựa chọn UTF-8 một cách tường minh khi cần kiểm soát chất lượng bản dịch.

## 3. Cơ chế UTF-8 → ISO-8859-1 từ Java 9

Khi nạp một tệp `.properties` thông qua `PropertyResourceBundle(InputStream)` và **không cấu hình bảng mã bắt buộc**, quy trình có thể hiểu như sau:

```text
Byte của tệp .properties
    |
    v
Thử giải mã bằng UTF-8
    |
    +-- Hợp lệ --------------------> Phân tích các cặp key=value
    |
    +-- MalformedInputException
        hoặc UnmappableCharacterException
                |
                v
        Đọc lại bằng ISO-8859-1
                |
                v
        Phân tích các cặp key=value
```

Các điểm cần nắm:

1. **UTF-8 được thử trước.** Tệp UTF-8 hợp lệ được đọc trực tiếp; không cần chuyển chữ có dấu sang `\uXXXX`.
2. **Chỉ lỗi giải mã byte tương ứng** mới khiến bộ đọc quay về ISO-8859-1. Ví dụ, byte `E9` đứng riêng không phải một chuỗi UTF-8 hợp lệ.
3. **Toàn bộ tệp được đọc lại** bằng ISO-8859-1 khi nhánh tương thích được kích hoạt; đây không phải cách Java tự đổi bảng mã cho từng chữ.
4. Nếu byte Latin-1 tình cờ tạo thành một chuỗi UTF-8 hợp lệ, Java sẽ chấp nhận UTF-8 và **không** quay về Latin-1, dù nội dung đọc ra không đúng ý tác giả.
5. Nếu gặp lỗi khác như escape Unicode sai cú pháp `\u12G4`, hệ thống có thể báo lỗi phân tích properties; không được coi mọi lỗi đọc file là tín hiệu để đổi bảng mã.
6. Quy tắc này áp dụng cho **`PropertyResourceBundle` đọc byte**. Việc chuyển locale khi không tìm thấy `Messages_vi_VN.properties` là một cơ chế fallback **khác hoàn toàn**.

Cơ chế tương thích hữu ích khi một ứng dụng cần đọc các bản dịch vốn được lưu bằng Latin-1. Với tài nguyên đang được duy trì, nên chuẩn hóa tất cả tệp sang UTF-8 để loại bỏ sự mơ hồ.

## 4. Ví dụ hoàn chỉnh: bản dịch UTF-8 với ResourceBundle

Đặt ba tệp sau **cùng thư mục** và lưu hai tệp `.properties` bằng **UTF-8**.

**`Messages.properties`** – tài nguyên mặc định:

```properties
greeting=Hello
farewell=Goodbye
```

**`Messages_vi.properties`** – bản dịch tiếng Việt:

```properties
greeting=Xin chào
farewell=Tạm biệt
```

**`BundleDemo.java`**:

```java
import java.util.Locale;
import java.util.ResourceBundle;

public class BundleDemo {
    public static void main(String[] args) {
        Locale vietnamese = Locale.forLanguageTag("vi-VN");
        ResourceBundle messages =
                ResourceBundle.getBundle("Messages", vietnamese);

        System.out.println(messages.getString("greeting"));
        System.out.println(messages.getString("farewell"));
    }
}
```

Biên dịch và chạy trong thư mục chứa ba tệp bằng JDK 17+:

```bash
javac -encoding UTF-8 BundleDemo.java
java -cp . BundleDemo
```

Kết quả chuẩn (thiết bị đầu cuối cần hiển thị Unicode chính xác):

```text
Xin chào
Tạm biệt
```

Giải thích:

- Base name `Messages` tương ứng các tệp `Messages*.properties` trên classpath; **không** ghi phần mở rộng trong lời gọi `getBundle`.
- Locale `vi-VN` khiến bộ tìm kiếm xét tài nguyên tiếng Việt phù hợp. Trong ví dụ có `Messages_vi.properties`, nên hai khóa được đọc từ tệp này.
- Bảng mã UTF-8 được `PropertyResourceBundle` giải mã hợp lệ, vì vậy không xảy ra nhánh ISO-8859-1.
- Tham số `javac -encoding UTF-8` chỉ quy định **bảng mã tệp `BundleDemo.java`** khi biên dịch; nó không thiết lập bảng mã của `Messages_vi.properties` khi chương trình chạy.

Nếu mục đích là phát hiện ngay khi có tệp bản dịch không phải UTF-8, chạy cùng chương trình trong một JVM mới với thiết lập nghiêm ngặt:

```bash
java -Djava.util.PropertyResourceBundle.encoding=UTF-8 -cp . BundleDemo
```

Tài nguyên UTF-8 chuẩn vẫn in hai dòng như trên. Tệp có byte không hợp lệ theo UTF-8 sẽ làm quá trình nạp báo lỗi thay vì âm thầm đọc lại bằng ISO-8859-1.

## 5. Chọn bảng mã tường minh: hai cấp độ

### 5.1. Cấp JVM: thuộc tính của PropertyResourceBundle

Tên hệ thống chính xác là:

```text
java.util.PropertyResourceBundle.encoding
```

Các giá trị được công nhận:

| Thiết lập khi khởi động JVM | Hành vi đọc từ `InputStream` |
| --- | --- |
| Không đặt | Thử UTF-8; nếu lỗi giải mã phù hợp thì đọc lại bằng ISO-8859-1 |
| `-Djava.util.PropertyResourceBundle.encoding=UTF-8` | Chỉ giải mã UTF-8; byte UTF-8 sai gây lỗi, không fallback |
| `-Djava.util.PropertyResourceBundle.encoding=ISO-8859-1` | Chỉ giải mã ISO-8859-1; UTF-8 nhiều byte có thể trở thành ký tự sai |
| Giá trị không được hỗ trợ | Không có hiệu lực khóa bảng mã; không dùng để cấu hình tùy ý |

Ví dụ thực hành:

```bash
# Khuyến nghị khi toàn bộ resource bundle đã chuẩn UTF-8
java -Djava.util.PropertyResourceBundle.encoding=UTF-8 -cp . BundleDemo

# Chỉ dành cho nguồn dữ liệu thực sự được quản lý dưới ISO-8859-1
java -Djava.util.PropertyResourceBundle.encoding=ISO-8859-1 -cp . BundleDemo
```

**Lưu ý về phạm vi:** đây là thuộc tính hệ thống của JVM cho cách `PropertyResourceBundle` đọc `InputStream`; không phải tham số per-file, cũng không phải tùy chọn trực tiếp của `Locale`. Thuộc tính được đọc khi lớp `PropertyResourceBundle` khởi tạo lần đầu. Đổi bằng `System.setProperty(...)` sau khi lớp đã khởi tạo **không cập nhật hành vi**; nên chỉ định `-D` ngay lúc chạy ứng dụng. Khi kiểm thử hai cấu hình, chạy **hai tiến trình JVM khác nhau**.

Việc khóa `UTF-8` giúp lỗi byte lộ rõ sớm trong CI và môi trường triển khai. Khóa `ISO-8859-1` chỉ hợp lý khi đầu vào được định nghĩa rõ là Latin-1; một tệp UTF-8 tiếng Việt không thể được giải mã đúng theo lựa chọn này.

### 5.2. Cấp từng nguồn: truyền Reader mang charset rõ ràng

Khi tự mở file, dùng `Reader` giải mã bởi `StandardCharsets.UTF_8`. Cách này tường minh ngay tại chỗ đọc và không phụ thuộc vào thuộc tính JVM của constructor nhận `InputStream`.

Vẫn dùng tệp `Messages_vi.properties` ở mục 4; bổ sung tệp **`settings.properties`** lưu bằng UTF-8:

```properties
title=Cấu hình tiếng Việt
```

**`ExplicitEncodingDemo.java`** (chương trình độc lập chạy được):

```java
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;
import java.util.PropertyResourceBundle;

public class ExplicitEncodingDemo {
    public static void main(String[] args) throws Exception {
        Path translations = Path.of("Messages_vi.properties");

        try (Reader reader =
                     Files.newBufferedReader(translations, StandardCharsets.UTF_8)) {
            PropertyResourceBundle bundle = new PropertyResourceBundle(reader);
            System.out.println(bundle.getString("greeting"));
        }

        Properties settings = new Properties();
        try (Reader reader =
                     Files.newBufferedReader(Path.of("settings.properties"),
                                             StandardCharsets.UTF_8)) {
            settings.load(reader);
        }
        System.out.println(settings.getProperty("title"));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ExplicitEncodingDemo.java
java -cp . ExplicitEncodingDemo
```

Kết quả:

```text
Xin chào
Cấu hình tiếng Việt
```

Ở đây `Files.newBufferedReader(..., StandardCharsets.UTF_8)` tạo nguồn ký tự UTF-8 rõ ràng; `PropertyResourceBundle(Reader)` và `Properties.load(Reader)` đọc **ký tự đã được giải mã**. Nếu byte tệp không hợp lệ theo charset chỉ định, thao tác đọc Reader sẽ báo lỗi, không kích hoạt cơ chế quay về ISO-8859-1 của `PropertyResourceBundle(InputStream)`.

**Khi nào chọn cách nào?** Với ứng dụng chỉ cần `ResourceBundle.getBundle` để tra cứu bản dịch theo locale, đặt tài nguyên UTF-8 và (nếu muốn kiểm tra chặt) khóa UTF-8 ở JVM. Với các tệp cụ thể bạn tự mở, `Reader` có charset tường minh là cách rõ ràng, dễ kiểm tra và tái sử dụng.

## 6. Ví dụ kiểm chứng nhánh quay về ISO-8859-1

Không cần trình soạn thảo hỗ trợ Latin-1 để thử nghiệm: chương trình sau chủ động **tạo một tệp Latin-1 thật** bằng `StandardCharsets.ISO_8859_1` rồi nạp bằng `ResourceBundle`. Đặt `FallbackDemo.java` trong thư mục làm việc có quyền ghi; chạy JVM **không có** thuộc tính khóa encoding.

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import java.util.ResourceBundle;

public class FallbackDemo {
    public static void main(String[] args) throws Exception {
        String source = "greeting=Café\n";
        Files.write(Path.of("LatinMessages_fr.properties"),
                    source.getBytes(StandardCharsets.ISO_8859_1));

        ResourceBundle bundle =
                ResourceBundle.getBundle("LatinMessages", Locale.FRENCH);
        System.out.println(bundle.getString("greeting"));
    }
}
```

```bash
javac -encoding UTF-8 FallbackDemo.java
java -cp . FallbackDemo
```

Kết quả:

```text
Café
```

Lý do: ký tự `é` trong tệp được tạo ra là byte `E9`. Đây không phải byte độc lập hợp lệ trong UTF-8, nên nhánh tương thích chuyển sang ISO-8859-1 để đọc và khôi phục đúng `é`. Nếu chạy một tiến trình mới với `-Djava.util.PropertyResourceBundle.encoding=UTF-8`, tệp Latin-1 này **không được đọc lại** bằng Latin-1, và thao tác nạp bundle sẽ thất bại do đầu vào UTF-8 không hợp lệ. Không nên ràng buộc bài kiểm thử vào tên lớp ngoại lệ ở tầng `ResourceBundle.getBundle`, vì API tra cứu bundle có thể bọc nguyên nhân trong ngoại lệ tìm tài nguyên.

**Điểm giới hạn đáng nhớ:** thử nghiệm `E9` cho thấy khi nào fallback xảy ra, không chứng minh Java có thể đoán bảng mã Latin-1 nói chung. Ví dụ hai byte `C3 A9` cũng hợp lệ theo UTF-8 nên sẽ không kích hoạt fallback, dù người tạo tệp thật sự định dùng hai ký tự Latin-1 `Ã©`.

## 7. Phân biệt các API đọc `.properties` còn được sử dụng hiện nay

| API / cách gọi | Cách hiểu byte hoặc ký tự | Có tự thử UTF-8 rồi Latin-1? |
| --- | --- | --- |
| `ResourceBundle.getBundle(...)` với bundle `.properties` chuẩn | Thường tạo `PropertyResourceBundle` từ tài nguyên theo locale | **Có**, khi không khóa encoding và đường nạp dùng `InputStream` |
| `new PropertyResourceBundle(InputStream)` | UTF-8 trước, ISO-8859-1 khi gặp lỗi giải mã; chịu ảnh hưởng system property | **Có**, theo điều kiện |
| `new PropertyResourceBundle(Reader)` | Dùng ký tự do `Reader` cung cấp | **Không**, charset do người tạo Reader quyết định |
| `Properties.load(InputStream)` | **ISO-8859-1** theo hợp đồng API, kể cả trên JDK mới | **Không** |
| `Properties.load(Reader)` | Dùng ký tự do `Reader` cung cấp | **Không** |
| `Files.newBufferedReader(path, UTF_8)` | Giải mã UTF-8 một cách tường minh | **Không** |

Hãy đặc biệt lưu ý đoạn sau:

```java
Properties p = new Properties();
try (var in = Files.newInputStream(Path.of("settings.properties"))) {
    p.load(in); // API này vẫn hiểu byte theo ISO-8859-1.
}
```

Đoạn minh họa trên dùng `Properties.load(InputStream)`, **không phải** cách nạp `PropertyResourceBundle`. Nếu `settings.properties` chứa tiếng Việt mã hóa UTF-8, dữ liệu có thể bị lỗi chữ dù chương trình dùng Java 9, 17, 21 hoặc mới hơn. Để đọc UTF-8 đúng, dùng `Properties.load(Reader)` như chương trình hoàn chỉnh ở mục 5.2.

Tương tự, `Properties.store(OutputStream, ...)` vẫn ghi theo biểu diễn ISO-8859-1/Unicode escape của API. Khi cần trao đổi tệp UTF-8 mà vẫn dùng `Properties`, sử dụng cặp `store(Writer, ...)` và `load(Reader)` với charset được chỉ định rõ.

**JDK 18+ dùng UTF-8 làm default charset theo JEP 400** không làm thay đổi hợp đồng nói trên của `Properties.load(InputStream)`, và không biến `java.util.PropertyResourceBundle.encoding` thành alias cho `file.encoding`. Vì vậy, đừng dựa vào default charset của hệ điều hành hoặc cờ biên dịch mã nguồn để sửa lỗi đọc tệp bản dịch.

## 8. Chẩn đoán khi bản dịch hiển thị sai

Thực hiện theo thứ tự sau để tránh sửa nhầm nguyên nhân:

1. **Xác định API thật sự đọc tệp:** `ResourceBundle/PropertyResourceBundle` hay `Properties.load(InputStream)`? Hai đường có quy tắc khác nhau.
2. **Xác định mã hóa byte của file trên đĩa:** lưu tệp bản dịch dưới UTF-8 một cách nhất quán trong editor, công cụ build và pipeline xuất bản. Không chỉ dựa vào phần mở rộng `.properties`.
3. **Kiểm tra đường tìm tài nguyên:** base name, tên `Messages_vi.properties`, classpath và locale. Không tìm thấy bundle/khóa là vấn đề tra cứu, không phải chứng cứ lỗi charset.
4. **Phân loại triệu chứng:** ngoại lệ dữ liệu UTF-8 không hợp lệ (có thể có fallback) khác với chuỗi đọc thành công nhưng sai nghĩa hoặc ký tự (mojibake, không có fallback).
5. **Khóa UTF-8 ở một JVM sạch** để thử tệp bundle do `ResourceBundle` nạp: `-Djava.util.PropertyResourceBundle.encoding=UTF-8`. Nếu lỗi giải mã hiện rõ, sửa hoặc chuyển mã tệp ở nguồn.
6. **Kiểm tra phần hiển thị:** terminal hoặc lớp giao diện có thể dùng cấu hình font/encoding riêng. Nếu nội dung Java String đúng mà in ra sai, lỗi có thể nằm ở đầu ra; đừng chuyển mã lại toàn bộ tài nguyên.
7. **Nhớ cache của ResourceBundle:** `getBundle` có thể tái sử dụng bản đã nạp. Khi muốn thử tệp vừa chỉnh, chạy JVM mới (hoặc quản lý cache phù hợp); việc `ResourceBundle.clearCache()` không thay đổi thuộc tính encoding đã được lớp `PropertyResourceBundle` ghi nhận khi khởi tạo.

Các lỗi phổ biến cần tránh:

- Nghĩ rằng **mọi** tệp `.properties` đều mặc định UTF-8 từ Java 9.
- Nhầm **fallback của bảng mã** với **fallback locale**.
- Coi chữ không đúng nội dung sau giải mã thành công là ngoại lệ có thể khiến hệ thống thử bảng mã khác.
- Dùng `-Dfile.encoding=UTF-8`, `javac -encoding UTF-8` hoặc thay `Locale` rồi kỳ vọng chúng sửa mọi cách nạp properties.
- Thiết lập `System.setProperty("java.util.PropertyResourceBundle.encoding", "UTF-8")` sau khi đã dùng `PropertyResourceBundle` và cho rằng lần nạp kế tiếp sẽ đổi quy tắc.
- Dùng cờ khóa ISO-8859-1 cho tệp dịch UTF-8 có dấu; ký tự nhiều byte sẽ bị đọc sai.
- Dùng `Reader` không chỉ rõ charset khi cần đầu ra nhất quán giữa môi trường.
- Đưa ký tự Unicode ngoài Latin-1 vào luồng được quy định ISO-8859-1 mà không dùng escape hợp lệ.

## 9. Cách làm phù hợp cho dự án đang được duy trì

**Với tài nguyên dịch mới:** đặt mọi `Messages*.properties` ở UTF-8; giữ nguyên chữ có dấu để người dịch dễ đọc, dùng `ResourceBundle.getBundle` để chọn locale và cân nhắc khóa `java.util.PropertyResourceBundle.encoding=UTF-8` ngay khi khởi động nhằm phát hiện file sai mã hóa. Với tệp dịch được cung cấp bởi công cụ bên ngoài, kiểm tra encoding trong CI thay vì trông đợi fallback tự khắc phục.

**Với tệp Latin-1 đã tồn tại và vẫn phải sử dụng:** xác nhận encoding thực tế trước, chuyển mã có kiểm tra nếu có thể; trong thời gian dữ liệu còn Latin-1, cơ chế fallback mặc định có thể giữ tương thích. Nếu có hợp đồng đầu vào Latin-1 bắt buộc, khóa chính xác `ISO-8859-1` cho đường `PropertyResourceBundle(InputStream)` hoặc dùng `Reader` với `StandardCharsets.ISO_8859_1` khi tự quản lý nguồn. Không trộn các định dạng trong cùng một bộ bản dịch.

**Với cấu hình qua `Properties`:** nếu cần Unicode/UTF-8, luôn ghép `load(Reader)` và `store(Writer, ...)` với `StandardCharsets.UTF_8`. Xem các overload nhận `InputStream`/`OutputStream` là giao diện có hợp đồng Latin-1 riêng.

### Tự kiểm tra kiến thức

1. File `Messages_vi.properties` có byte UTF-8 hợp lệ cho `á`. Có quay về ISO-8859-1 không? **Không**, vì UTF-8 được giải mã thành công.
2. File chứa byte `E9` độc lập, đọc bằng `PropertyResourceBundle(InputStream)` mặc định. Có thể xảy ra gì? **UTF-8 không hợp lệ, nên thử lại ISO-8859-1**.
3. Cùng file ở câu 2 nhưng chạy `-Djava.util.PropertyResourceBundle.encoding=UTF-8`? **Báo lỗi đọc UTF-8**, không có nhánh Latin-1.
4. Dùng `Properties.load(Files.newInputStream(path))` với file UTF-8 tiếng Việt, JDK hiện đại có tự thử UTF-8 không? **Không**; API này hiểu `InputStream` theo ISO-8859-1.
5. Muốn một file riêng được đọc bắt buộc bằng UTF-8 mà không cấu hình toàn JVM? **Tạo Reader với `StandardCharsets.UTF_8`**, rồi truyền vào `PropertyResourceBundle(Reader)` hoặc `Properties.load(Reader)`.

## Tài liệu chính thức để đối chiếu

- OpenJDK JEP 226 – UTF-8 Property Files: https://openjdk.org/jeps/226
- Oracle Java SE 26 – `PropertyResourceBundle`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/PropertyResourceBundle.html
- Oracle Java SE 26 – `ResourceBundle`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ResourceBundle.html
- Oracle Java SE 26 – `Properties`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Properties.html
- OpenJDK JEP 400 – UTF-8 by Default (để phân biệt default charset của JDK): https://openjdk.org/jeps/400
