# Kiểm tra snippet properties có thể được nạp bằng đúng API và charset được mô tả

## 1. Vì sao phải kiểm chứng cả API nạp và charset?

Một file `.properties` có thể hiển thị đúng trong tài liệu nhưng khi ứng dụng đọc lại lại cho ra chuỗi sai. Lỗi thường không nằm ở cú pháp `key=value`; nó nằm ở **sự không khớp giữa cách file được mã hóa và API dùng để giải mã**.

Java 18 có thay đổi quan trọng về mã hóa mặc định qua **JEP 400**: UTF-8 trở thành charset mặc định của Java trong các cấu hình JDK thông thường. Tuy nhiên, thay đổi này **không làm cho mọi API đọc byte tự động dùng UTF-8**. Cụ thể:

- `Properties.load(InputStream)` có hợp đồng riêng: đọc byte theo **ISO-8859-1**.
- `Properties.load(Reader)` nhận ký tự đã được giải mã; charset phụ thuộc vào `Reader` mà ứng dụng tạo.
- Muốn đọc file `.properties` UTF-8 một cách tường minh, có thể dùng `Files.newBufferedReader(path, StandardCharsets.UTF_8)` rồi gọi `Properties.load(reader)`.

Quy tắc của `load(InputStream)` vẫn được giữ trên JDK hiện đại. Phương thức này không bị deprecated; nó phù hợp với file tuân theo định dạng ISO-8859-1 hoặc dùng escape Unicode. Với file lưu trực tiếp các ký tự UTF-8, hãy chọn overload nhận `Reader` và chỉ rõ charset.

Bài này thuộc phần **Kiểm chứng tài liệu** của mô-đun **JAVA_VERSION_JAVA18**. Ta sẽ đặt một file `.properties` làm external snippet trong Javadoc, viết lớp Java nạp chính file đó, rồi chạy kiểm tra để xác nhận giá trị Unicode thực tế. Các API dùng trong bài đều còn được hỗ trợ trên JDK hiện đại.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt `Properties.load(InputStream)` với `Properties.load(Reader)`.
2. Giải thích vì sao JEP 400 không thay đổi quy tắc ISO-8859-1 của overload nhận `InputStream`.
3. Nạp file `.properties` UTF-8 bằng charset được chỉ định rõ ràng.
4. Viết kiểm tra tự động phát hiện chuỗi Unicode bị giải mã sai.
5. Đồng bộ charset giữa file snippet, chương trình ví dụ và bước tạo Javadoc.

## 2. Hợp đồng mã hóa của các API `Properties`

### 2.1. Hai overload `load` có hợp đồng khác nhau

| API | Dữ liệu đầu vào | Quy tắc giải mã |
| --- | --- | --- |
| `Properties.load(InputStream)` | Luồng byte | **ISO-8859-1**; các ký tự ngoài phạm vi có thể biểu diễn bằng escape `\uXXXX`. |
| `Properties.load(Reader)` | Luồng ký tự | `Reader` đã quyết định cách giải mã byte; `Properties` đọc ký tự từ đó. |

Ví dụ nếu file chứa trực tiếp:

```properties
app.name=Ví dụ Java 18
welcome=Chào bạn
```

và được lưu dưới dạng UTF-8, cách đọc phù hợp là:

```java
Properties properties = new Properties();
try (Reader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    properties.load(reader);
}
```

Ở đây, `Files.newBufferedReader` chuyển byte UTF-8 thành ký tự Unicode. `Properties.load(Reader)` phân tích các ký tự đó theo cú pháp file properties.

Ngược lại, nếu truyền trực tiếp `Files.newInputStream(path)` cho `load(InputStream)`, từng byte UTF-8 được diễn giải theo ISO-8859-1. Chuỗi `Chào bạn` có thể trở thành dạng ký tự lỗi như `ChÃ o báº¡n`; phương thức thường không ném lỗi chỉ vì nội dung tiếng Việt bị giải mã sai. Do đó, **phải kiểm tra giá trị**, không thể chỉ dựa vào việc API chạy mà không có exception.

### 2.2. JEP 400 thay đổi charset mặc định, không thay đổi hợp đồng của `Properties`

JEP 400 đặt UTF-8 làm charset mặc định từ JDK 18 trong những cấu hình thông thường. Điều đó có ích cho API phụ thuộc vào charset mặc định của môi trường. Nhưng `Properties.load(InputStream)` không hỏi charset mặc định: tài liệu API quy định trực tiếp ISO-8859-1.

Vì vậy, hai phát biểu sau không tương đương:

- “JDK 18 mặc định UTF-8.”
- “Mọi API đọc `InputStream` đều giải mã UTF-8.”

Phát biểu thứ hai là sai. Hợp đồng cụ thể của từng API vẫn có hiệu lực. Để mã dễ đọc và ổn định giữa máy phát triển, CI và môi trường triển khai, hãy truyền `StandardCharsets.UTF_8` khi file của bạn được quy định là UTF-8.

### 2.3. Khi nào dùng từng overload?

- Dùng **`load(Reader)`** khi định dạng file của ứng dụng được lưu bằng UTF-8 hoặc một charset cụ thể khác. Hãy tạo `Reader` bằng charset đã thống nhất.
- Dùng **`load(InputStream)`** khi file tuân theo quy tắc ISO-8859-1 của định dạng properties truyền thống, hoặc nội dung dùng escape Unicode ASCII như `\u00E0`.
- Với file XML properties, dùng API riêng **`loadFromXML(InputStream)`** và tuân thủ quy tắc encoding của XML. Không đưa tài liệu XML vào `load(Reader)` như thể đó là file `.properties` thông thường.

`load(InputStream)` không phải API lỗi thời; điều cần tránh là dùng nó cho một file UTF-8 mà không chuyển đổi byte sang ký tự theo UTF-8.

## 3. Tạo file `.properties` UTF-8 làm nguồn cho tài liệu

Sử dụng cấu trúc dự án sau, tính từ thư mục `demo/`:

```text
demo/
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── config/
                        ├── MessageCatalog.java
                        └── snippet-files/
                            ├── messages.properties
                            └── PropertiesExample.java
```

Thư mục `snippet-files` là nơi Standard Doclet tìm external snippet của package. Nó không phải thành phần của Java package; cả hai file `.java` khai báo `package com.example.config;`.

Tạo file **`src/main/java/com/example/config/snippet-files/messages.properties`** và lưu trực tiếp dưới dạng **UTF-8 không BOM**:

```properties
app.name=Ví dụ Java 18
welcome=Chào bạn
description=Đọc cấu hình bằng UTF-8
```

File có ký tự tiếng Việt thật, không chuyển chúng thành `\uXXXX`. Điều này giúp bài kiểm chứng đúng tình huống cần xử lý: byte UTF-8 phải được giải mã thành đúng ký tự trước khi `Properties` phân tích các cặp khóa và giá trị.

**Lưu ý về BOM:** `Files.newBufferedReader(..., UTF_8)` giải mã UTF-8 nhưng không tự loại bỏ ký tự BOM nếu file bắt đầu bằng BOM. BOM có thể trở thành một phần của khóa đầu tiên, khiến `getProperty("app.name")` không tìm thấy khóa mong muốn. Vì vậy, ví dụ quy ước file UTF-8 không BOM; nếu hệ thống đầu vào có thể tạo BOM, hãy xử lý nó như một yêu cầu riêng và kiểm thử rõ ràng.

## 4. Viết API nạp properties bằng UTF-8

Tạo **`src/main/java/com/example/config/MessageCatalog.java`**:

```java
package com.example.config;

import java.io.IOException;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Objects;
import java.util.Properties;

/**
 * Đọc cấu hình properties được lưu bằng UTF-8.
 */
public final class MessageCatalog {
    private MessageCatalog() {
    }

    /**
     * Nạp file properties UTF-8.
     *
     * <p>Nội dung mẫu của file:</p>
     * {@snippet file="messages.properties" lang="properties"}
     *
     * <p>Cách gọi và xác minh giá trị:</p>
     * {@snippet class=PropertiesExample region=loadUtf8}
     *
     * @param path đường dẫn file properties UTF-8
     * @return tập hợp khóa và giá trị đã nạp
     * @throws IOException nếu không thể đọc file
     * @throws NullPointerException nếu path là null
     */
    public static Properties loadUtf8(Path path) throws IOException {
        Objects.requireNonNull(path, "path");
        Properties properties = new Properties();
        try (Reader reader =
                     Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
            properties.load(reader);
        }
        return properties;
    }
}
```

Đoạn quan trọng là:

```java
try (Reader reader =
         Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    properties.load(reader);
}
```

- `StandardCharsets.UTF_8` xác định charset của file ngay tại điểm mở.
- `Properties.load(reader)` dùng overload nhận ký tự, không phải overload nhận byte.
- `try-with-resources` đóng `Reader` sau khi nạp thành công hoặc khi phát sinh lỗi.
- `Properties.load(Reader)` không tự đóng luồng do bên gọi mở; quyền sở hữu tài nguyên được thể hiện rõ trong khối `try`.

Đây là hợp đồng dễ đọc: phương thức nhận đường dẫn file UTF-8, tự mở và đóng reader, rồi trả về `Properties`. Người gọi không phải tự tạo `InputStream` hoặc đoán charset.

## 5. Viết lớp ví dụ để kiểm tra nội dung thật

Tạo **`src/main/java/com/example/config/snippet-files/PropertiesExample.java`**:

```java
package com.example.config;

import java.io.IOException;
import java.nio.file.Path;
import java.util.Properties;

/**
 * Ví dụ nạp và kiểm tra file properties UTF-8.
 */
public final class PropertiesExample {
    private PropertiesExample() {
    }

    public static void main(String[] args) throws IOException {
        // @start region=loadUtf8
        Path path = Path.of(
                "src/main/java/com/example/config/snippet-files/messages.properties");
        Properties properties = MessageCatalog.loadUtf8(path);

        String welcome = properties.getProperty("welcome");
        if (!"Chào bạn".equals(welcome)) {
            throw new AssertionError("Unexpected welcome value: " + welcome);
        }
        if (!"Ví dụ Java 18".equals(properties.getProperty("app.name"))) {
            throw new AssertionError("Property app.name was not decoded correctly");
        }
        System.out.println(welcome);
        // @end region=loadUtf8
    }
}
```

Lớp ví dụ đọc đúng file đã được tham chiếu trong Javadoc và so sánh với các chuỗi Unicode mong đợi. Nếu giải mã sai, khóa không tồn tại hoặc nội dung file bị thay đổi, chương trình ném `AssertionError` và kết thúc với mã thoát khác 0.

Hai đoạn snippet trong Javadoc có mục đích khác nhau:

| Thẻ | Nguồn được trích | Mục đích |
| --- | --- | --- |
| `{@snippet file="messages.properties" lang="properties"}` | File `.properties` UTF-8 | Cho người đọc thấy dữ liệu cấu hình thực tế. |
| `{@snippet class=PropertiesExample region=loadUtf8}` | Vùng mã Java | Cho người đọc thấy API và charset được dùng để nạp file. |

`lang="properties"` là thông tin ngôn ngữ để trình bày/highlight snippet. Nó **không chọn charset**, không thay thế `StandardCharsets.UTF_8` trong mã Java và cũng không tự chứng minh file đã được giải mã đúng.

## 6. Kiểm chứng sự khác nhau giữa `load(InputStream)` và `load(Reader)`

### 6.1. Tạo phép thử cho overload nhận byte

Với cùng file UTF-8 ở phần 3, có thể tái hiện cách giải mã sai:

```java
Properties decodedAsLatin1 = new Properties();
try (InputStream input = Files.newInputStream(path)) {
    decodedAsLatin1.load(input);
}

String actual = decodedAsLatin1.getProperty("welcome");
if (!"Chào bạn".equals(actual)) {
    throw new AssertionError("UTF-8 was decoded incorrectly: " + actual);
}
```

Đoạn này **vẫn biên dịch được**, nhưng phép kiểm tra sẽ thất bại khi chạy: `load(InputStream)` đọc byte theo ISO-8859-1 nên `actual` không bằng chuỗi tiếng Việt kỳ vọng. Lỗi là **sai hợp đồng mã hóa**, không phải lỗi cú pháp Java hay lỗi parser properties.

Đây là một trường hợp quan trọng của kiểm chứng tài liệu: chỉ nhìn thấy `Properties.load(...)` trong snippet không đủ. Phải đọc đúng kiểu đối số (`InputStream` hay `Reader`) và kiểm tra charset ở nơi tạo luồng.

### 6.2. Khi nào `load(InputStream)` vẫn là lựa chọn đúng?

Nếu file được quy định là ISO-8859-1, hoặc biểu diễn ký tự ngoài Latin-1 bằng Unicode escape, overload này vẫn phù hợp. Ví dụ file ASCII:

```properties
app.name=Java
welcome=Ch\u00E0o b\u1EA1n
```

Có thể nạp bằng:

```java
Properties properties = new Properties();
try (InputStream input = Files.newInputStream(path)) {
    properties.load(input);
}
```

Các ký tự escape `\u00E0` và `\u1EA1` là văn bản ASCII trong file; parser properties chuyển chúng thành ký tự Unicode. Không cần giả định byte stream là UTF-8.

### 6.3. So sánh cách chọn API

| File thực tế | Cách đọc phù hợp | Ghi chú |
| --- | --- | --- |
| `.properties` chứa ký tự UTF-8 trực tiếp | `Files.newBufferedReader(path, UTF_8)` + `load(Reader)` | Lựa chọn của ví dụ chính. |
| `.properties` tuân theo ISO-8859-1 | `Files.newInputStream(path)` + `load(InputStream)` | Đúng hợp đồng byte stream của `Properties`. |
| `.properties` dùng escape `\uXXXX` trong dữ liệu ASCII | `load(InputStream)` hoặc `load(Reader)` với charset phù hợp | Escape được parser chuyển thành ký tự Unicode. |
| XML properties | `loadFromXML(InputStream)` | Là định dạng XML riêng, có quy tắc encoding XML. |

Không nên chọn overload dựa vào việc tên file có đuôi `.properties`; hãy chọn theo **encoding đã quy định cho nội dung file**.

## 7. Kiểm tra cả chiều ghi nếu ứng dụng cần round-trip

Nếu ứng dụng ghi lại file và yêu cầu file vẫn là UTF-8, hãy chọn overload `store(Writer, comments)` cùng một `Writer` được cấu hình UTF-8:

```java
Properties properties = new Properties();
properties.setProperty("welcome", "Chào bạn");

try (Writer writer =
         Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
    properties.store(writer, "UTF-8 properties");
}
```

`Properties.store(Writer, ...)` ghi ký tự ra writer; charset thực tế do writer quyết định. Ngược lại, `Properties.store(OutputStream, ...)` ghi byte theo ISO-8859-1; trong khóa và giá trị, các ký tự nhỏ hơn U+0020 hoặc lớn hơn U+007E được ghi bằng escape Unicode `\uXXXX`. Vì vậy overload này không tạo file UTF-8 chứa trực tiếp các ký tự Unicode. Hai overload ghi cũng cần được chọn theo định dạng file mà ứng dụng cam kết.

Để kiểm chứng round-trip, có thể:

1. Ghi một `Properties` chứa `welcome=Chào bạn` bằng `store(Writer)` với UTF-8.
2. Đóng writer, mở lại file bằng `Files.newBufferedReader(path, UTF_8)`.
3. Nạp bằng `load(Reader)` và xác nhận `getProperty("welcome")` đúng nguyên văn.
4. Đọc lại file ở mức byte nếu cần xác minh encoding đầu ra, thay vì chỉ dựa vào cách IDE hiển thị.

Đừng kết luận file là UTF-8 chỉ vì nội dung trên màn hình trông đúng: editor có thể tự đoán charset. Charset phải được xác định bởi hợp đồng ghi/đọc và phép kiểm chứng tương ứng.

## 8. Đồng bộ charset trong quy trình biên dịch và tạo Javadoc

Tại thư mục `demo/`, biên dịch cả API và lớp ví dụ:

```bash
mkdir -p build/classes

javac --release 18 -encoding UTF-8 -d build/classes \
  src/main/java/com/example/config/MessageCatalog.java \
  src/main/java/com/example/config/snippet-files/PropertiesExample.java
```

`-encoding UTF-8` ở đây điều khiển cách `javac` đọc **file nguồn Java**. Nó không thay thế `StandardCharsets.UTF_8` trong lời gọi `Files.newBufferedReader`, và không tự đổi encoding của file `.properties` khi chương trình chạy.

Chạy ví dụ từ thư mục gốc dự án:

```bash
java -cp build/classes com.example.config.PropertiesExample
```

Đầu ra mong đợi:

```text
Chào bạn
```

Tiếp theo tạo Javadoc:

```bash
javadoc -d build/docs \
  -encoding UTF-8 -docencoding UTF-8 \
  -Xdoclint:all -Werror \
  src/main/java/com/example/config/MessageCatalog.java
```

Khi các file nguồn và external snippet được lưu UTF-8, hãy cấu hình encoding đầu vào Javadoc tương ứng và kiểm tra HTML sinh ra. `-docencoding UTF-8` chỉ định encoding cho tài liệu HTML đầu ra. Thẻ `lang="properties"` giúp nhận diện ngôn ngữ snippet để trình bày; nó không thay thế cấu hình encoding của công cụ hoặc API runtime.

Mở `build/docs/com/example/config/MessageCatalog.html` và xác nhận:

- File `messages.properties` hiển thị đúng dấu tiếng Việt.
- Snippet Java thể hiện rõ `Files.newBufferedReader(..., StandardCharsets.UTF_8)`.
- Phần mô tả không khiến người đọc hiểu nhầm rằng `load(InputStream)` cũng tự đọc UTF-8.
- Giá trị kỳ vọng trong ví dụ khớp nội dung file cấu hình.

## 9. Những lỗi thường gặp khi kiểm chứng

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Giá trị tiếng Việt bị biến dạng nhưng không có exception | Dùng `load(InputStream)` với file UTF-8 trực tiếp. | Dùng `load(Reader)` với reader UTF-8. |
| `getProperty("app.name")` trả `null` dù nhìn thấy khóa trong editor | File có BOM đứng trước khóa đầu tiên, hoặc tên khóa/encoding không đúng. | Dùng UTF-8 không BOM hoặc xử lý BOM theo hợp đồng đầu vào; kiểm tra key thực tế. |
| Chương trình biên dịch nhưng kiểm tra chuỗi thất bại | Charset không đúng, file không đúng nội dung, hoặc key bị sai. | Assert giá trị Unicode chính xác và kiểm tra file nguồn. |
| Javadoc hiển thị file nhưng Java nạp file khác | Đường dẫn runtime và đường dẫn snippet không cùng một nguồn dữ liệu. | Dùng cùng file trong ví dụ, hoặc cấu hình resource path thống nhất. |
| IDE hiển thị đúng nhưng CI hiển thị sai | Charset đầu vào Javadoc hoặc cấu hình file khác nhau. | Lưu file UTF-8, cấu hình `-encoding UTF-8`, kiểm tra HTML trong CI. |
| Tưởng `javac -encoding UTF-8` làm file properties được đọc UTF-8 | Nhầm charset biên dịch mã nguồn với charset runtime. | Chỉ định charset ở `Files.newBufferedReader` khi mở file. |
| Dùng `store(OutputStream)` nhưng mong byte UTF-8 thô | Overload output stream dùng ISO-8859-1 và escape Unicode. | Dùng `store(Writer)` với writer UTF-8 nếu hợp đồng file là UTF-8. |

### Bài tự luyện

1. Đổi `MessageCatalog.loadUtf8` sang dùng `Files.newInputStream` và `properties.load(input)`. Biên dịch có thành công không? Điều kiện kiểm tra `welcome` có đạt không?
2. Lưu file bằng ISO-8859-1 và thay ký tự tiếng Việt bằng `\uXXXX`. Overload nào có thể nạp đúng nội dung?
3. Thêm BOM vào đầu file UTF-8. Quan sát việc tra khóa đầu tiên và giải thích nguyên nhân.
4. Đổi `javac -encoding UTF-8` thành cấu hình khác. Điều đó có thay đổi cách `Files.newBufferedReader(..., UTF_8)` giải mã file runtime không?
5. Viết kiểm tra round-trip với `store(Writer)` và `load(Reader)`. Điều kiện nào chứng minh nội dung được giữ nguyên?
6. Trong tài liệu API, giải thích rõ `lang="properties"` có tác dụng gì và không quyết định điều gì.

## 10. Tài liệu tham khảo chính thức

- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): thay đổi charset mặc định từ JDK 18 và phạm vi áp dụng.
- [Properties (JDK 25)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Properties.html): hợp đồng của `load(InputStream)`, `load(Reader)`, `store(OutputStream)` và `store(Writer)`.
- [Files (JDK 25)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html): `newBufferedReader` và `newBufferedWriter` với charset được chỉ định.
- [JEP 413 — Code Snippets in Java API Documentation](https://openjdk.org/jeps/413): external snippet trong tài liệu API từ Java 18.
- [Oracle Javadoc Guide — Snippets (JDK 25)](https://docs.oracle.com/en/java/javase/25/javadoc/snippets.html): cách tham chiếu file snippet và thuộc tính ngôn ngữ.

**Ghi nhớ:** Charset của file là một phần hợp đồng dữ liệu. Với `.properties` UTF-8, hãy mở file bằng `Reader` được cấu hình `StandardCharsets.UTF_8`, sau đó gọi `Properties.load(Reader)` và kiểm tra giá trị Unicode thật. JEP 400 không thay đổi quy tắc ISO-8859-1 của `Properties.load(InputStream)`; hãy thể hiện đúng API và charset ngay trong ví dụ Javadoc.
