# Viết snippet cho ví dụ API thành công và ngoại lệ rồi xác minh bằng biên dịch cùng kiểm thử

## 1. Mục tiêu thực hành

Tài liệu API thường đưa ra đoạn mã mẫu nhưng không phải đoạn nào cũng được biên dịch hoặc chạy. Khi tên phương thức, kiểu tham số, quyền truy cập hay loại ngoại lệ thay đổi, ví dụ trong Javadoc có thể lỗi thời mà nhóm phát triển không phát hiện.

**JEP 413 — Code Snippets in Java API Documentation**, có từ Java 18, đưa vào tag `{@snippet}`. Một snippet có thể nằm trong Javadoc comment hoặc được lấy từ **file source bên ngoài**. Cách thứ hai đặc biệt hữu ích: source ví dụ có thể được `javac` kiểm tra và JUnit thực thi, đồng thời Standard Doclet lấy chính code đó để hiển thị. Đây vẫn là cách làm được hỗ trợ trên các JDK hiện đại.

Bài tập xây dựng một API đọc lời chào từ file UTF-8 và tài liệu hóa ba hành vi:

1. **Success:** đọc một lời chào tiếng Việt có emoji và giữ nguyên newline.
2. **Lỗi nghiệp vụ:** từ chối file chỉ chứa whitespace bằng `IllegalArgumentException`.
3. **Lỗi encoding:** từ chối byte UTF-8 malformed bằng `IOException`.

Sau đó xác minh độc lập bằng **biên dịch**, **JUnit** và **Javadoc**. Chỉ xem HTML được render đẹp chưa đủ: Standard Doclet **không tự biên dịch hoặc chạy snippet**.

## 2. Một nguồn code, ba loại bằng chứng

```text
             src/main/java/Utf8Greeting.java
                         |
                   API được gọi
                         v
        src/test/java/Utf8GreetingExamplesTest.java
                         |
                +--------+---------+
                |                  |
          javac + JUnit      marker @start/@end
                |                  |
                v                  v
           Test report       javadoc --snippet-path
                                   |
                                   v
                             HTML API docs
```

| Loại kiểm chứng | Công cụ | Điều được bảo đảm |
| --- | --- | --- |
| Mã hợp lệ về cú pháp và kiểu | Compiler Java | Import, chữ ký hàm và cách gọi API đúng |
| Hành vi thành công và lỗi | JUnit 5 | Test chạy thật, assertion về kết quả/ngoại lệ đúng |
| Tham chiếu và trình bày | Javadoc Standard Doclet | Có file, đúng region và HTML chứa đoạn mã mong muốn |
| Review nội dung | Người review hoặc kiểm tra HTML có mục tiêu | Snippet đủ ngữ cảnh, không mô tả sai hợp đồng |

Test pass **không** chứng minh tag Javadoc đã chọn đúng region. Javadoc build pass **không** chứng minh exception trong snippet đã được ném. Pipeline phải có cả ba hoạt động.

## 3. Xác định hợp đồng API trước khi viết ví dụ

API giả định:

```java
public static String readGreeting(Path file) throws IOException
```

Hợp đồng:

- Đọc **toàn bộ nội dung file** dưới dạng UTF-8.
- Không đoán encoding từ tên file hay cách terminal hiển thị.
- Giữ nguyên Unicode và các line terminator, không tự `strip()` dữ liệu trả về.
- Nếu toàn bộ nội dung là whitespace, ném `IllegalArgumentException`.
- Nếu gặp byte malformed/unmappable hoặc lỗi file I/O, ném `IOException`.
- Nếu `file` là `null`, ném `NullPointerException`.
- Đọc toàn bộ thành `String` chỉ phù hợp khi kích thước file có thể chứa trong bộ nhớ.

| Đầu vào | Tình huống | Kết quả |
| --- | --- | --- |
| `"Xin chào 🌍\n"` được ghi theo UTF-8 | Hợp lệ | Trả lại chính xác chuỗi |
| `" \t\n"` theo UTF-8 | Dữ liệu nghiệp vụ không hợp lệ | `IllegalArgumentException` |
| Hai byte `C3 28` | UTF-8 malformed | `IOException` |

Các tình huống lỗi không phải cùng một nhóm: **validation nghiệp vụ** chạy sau decode thành công; **lỗi encoding** xuất hiện ngay trong quá trình chuyển byte thành ký tự.

## 4. Cấu trúc dự án

Bố cục minh họa theo quy ước Maven:

```text
utf8-snippet-lab/
├── pom.xml
├── src/
│   ├── main/
│   │   └── java/com/example/docs/
│   │       └── Utf8Greeting.java
│   └── test/
│       └── java/com/example/docs/
│           └── Utf8GreetingExamplesTest.java
└── target/
    ├── classes/
    ├── test-classes/
    ├── surefire-reports/
    └── site/apidocs/
```

`Utf8GreetingExamplesTest.java` là file có thể compile và chạy JUnit. Đồng thời, ba vùng mã trong file này sẽ được trích vào Javadoc. Không tạo một file snippet khác chỉ chứa bản sao của test: hai bản có thể bị lệch nhau khi sửa API.

JUnit 5 là dependency ngoài Java SE; Maven hoặc Gradle cần được cấu hình để compile test source và chạy JUnit Jupiter qua JUnit Platform. Tên lớp kết thúc bằng `Test` cũng phù hợp với quy tắc discovery thông thường của Maven Surefire.

## 5. Cài đặt API và tham chiếu ba snippet trong Javadoc

Tạo `src/main/java/com/example/docs/Utf8Greeting.java`:

```java
package com.example.docs;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Objects;

/**
 * Reads a nonblank greeting from a UTF-8 text file.
 *
 * <p>Line terminators are preserved; no charset guessing
 * or automatic BOM removal is performed.
 */
public final class Utf8Greeting {
    private Utf8Greeting() {
    }

    /**
     * Reads a greeting from a UTF-8 file.
     *
     * <p>Successful invocation:
     * {@snippet file="com/example/docs/Utf8GreetingExamplesTest.java"
     *           region="success"}
     *
     * <p>Blank content is rejected:
     * {@snippet file="com/example/docs/Utf8GreetingExamplesTest.java"
     *           region="blank-input"}
     *
     * <p>Malformed UTF-8 is reported as an I/O failure:
     * {@snippet file="com/example/docs/Utf8GreetingExamplesTest.java"
     *           region="malformed-utf8"}
     *
     * @param file the UTF-8 file to read
     * @return the exact decoded text, including line terminators
     * @throws IOException if the file cannot be read or contains
     *         malformed or unmappable byte sequences
     * @throws IllegalArgumentException if the content is blank
     * @throws NullPointerException if file is null
     */
    public static String readGreeting(Path file) throws IOException {
        Objects.requireNonNull(file, "file");

        String text = Files.readString(file, StandardCharsets.UTF_8);

        if (text.isBlank()) {
            throw new IllegalArgumentException(
                    "Greeting must contain non-whitespace text");
        }

        return text;
    }
}
```

Các quyết định có ý nghĩa:

- `Files.readString(file, StandardCharsets.UTF_8)` không dựa vào `Charset.defaultCharset()`.
- `Files.readString` có hợp đồng ném `IOException` khi gặp byte malformed/unmappable.
- `String.isBlank()` có từ Java 11, vẫn dùng trên JDK hiện đại.
- Không loại bỏ ký tự xuống dòng vì hợp đồng công bố giữ nguyên nội dung.
- Không bắt `IOException` để âm thầm thử charset khác.
- Ba `@throws` khớp ba nhóm lỗi khác nhau trong phần triển khai.
- Ba tag `{@snippet}` trỏ vào **cùng một file test nguồn**.

JEP 400 đã khiến UTF-8 thành default charset thông thường từ Java 18, nhưng mã vẫn chọn UTF-8 tường minh vì đó là định dạng của payload, không phải một sự tình cờ của môi trường chạy.

## 6. Viết external snippet trong source test thực sự chạy

Tạo `src/test/java/com/example/docs/Utf8GreetingExamplesTest.java`:

```java
package com.example.docs;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class Utf8GreetingExamplesTest {

    @Test
    void readsValidUtf8Greeting(@TempDir Path tempDir) throws IOException {
        // @start region=success
        Path file = tempDir.resolve("greeting.txt");
        String expected = "Xin chào 🌍\n";
        Files.writeString(file, expected, StandardCharsets.UTF_8);

        String actual = Utf8Greeting.readGreeting(file);
        assertEquals(expected, actual);
        // @end region=success
    }

    @Test
    void rejectsBlankGreeting(@TempDir Path tempDir) throws IOException {
        // @start region=blank-input
        Path file = tempDir.resolve("blank.txt");
        Files.writeString(file, " \t\n", StandardCharsets.UTF_8);

        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> Utf8Greeting.readGreeting(file));

        assertEquals(
                "Greeting must contain non-whitespace text",
                error.getMessage());
        // @end region=blank-input
    }

    @Test
    void rejectsMalformedUtf8(@TempDir Path tempDir) throws IOException {
        // @start region=malformed-utf8
        Path file = tempDir.resolve("malformed.txt");
        Files.write(file, new byte[] {(byte) 0xC3, 0x28});

        assertThrows(
                IOException.class,
                () -> Utf8Greeting.readGreeting(file));
        // @end region=malformed-utf8
    }
}
```

Điểm khác biệt so với một đoạn code chỉ để trình bày:

- Source có `package`, import, class và method đầy đủ, nên compiler có thể kiểm tra.
- `@Test` và `@TempDir` là API JUnit 5 thực; file được tạo ở vị trí test riêng, không phụ thuộc đường dẫn của máy cá nhân.
- `Files.writeString(... UTF_8)` tạo file hợp lệ với charset đã công bố.
- Byte `C3 28` là dữ liệu UTF-8 malformed đã biết trước, không phải chuỗi được “đoán” là sai từ cách hiển thị.
- `assertThrows` thực sự gọi API. Nếu API không ném loại lỗi mong đợi, test thất bại.

Dùng **chính class test làm external snippet source** tạo sự gắn kết giữa đoạn mã được nhìn thấy trong tài liệu và đoạn mã được thực thi.

## 7. Cách Javadoc tìm đúng named region

Trong `Utf8Greeting.java`:

```java
{@snippet file="com/example/docs/Utf8GreetingExamplesTest.java"
          region="success"}
```

Trong `Utf8GreetingExamplesTest.java`:

```java
// @start region=success
Path file = tempDir.resolve("greeting.txt");
String expected = "Xin chào 🌍\n";
Files.writeString(file, expected, StandardCharsets.UTF_8);

String actual = Utf8Greeting.readGreeting(file);
assertEquals(expected, actual);
// @end region=success
```

`@start` và `@end` ở đây nằm trong Java line comment, là **markup của snippet**, không phải annotation. Compiler bỏ qua các comment này, còn Standard Doclet dùng chúng để chọn vùng code.

| Region | Test method | Mục đích |
| --- | --- | --- |
| `success` | `readsValidUtf8Greeting` | Đường đi thành công |
| `blank-input` | `rejectsBlankGreeting` | Lỗi validation |
| `malformed-utf8` | `rejectsMalformedUtf8` | Lỗi decode/I/O |

Đặt tên region theo hành vi, không dựa vào số dòng. Nếu đổi tên region, phải cập nhật cả Javadoc tag và marker trong source test. Nếu chỉ đổi một bên, docs có thể báo lỗi không tìm thấy region.

Các vùng có thể được trích riêng từ một file. Đừng để một marker bị thiếu làm region kéo dài sang method khác hoặc chứa những dòng không được định giới rõ ràng.

## 8. Vì sao snippet cần có ngữ cảnh compile?

Vùng `success` dùng biến `tempDir` mà không khai báo bên trong region. Nó vẫn **biên dịch đúng trong file test** vì biến là tham số `@TempDir Path tempDir` của method bao quanh.

Khi hiển thị snippet trong tài liệu, nên chú thích rằng:

- `tempDir` là một `Path` do JUnit cung cấp.
- `assertEquals` và `assertThrows` thuộc JUnit 5.
- Ví dụ dành cho kiểm thử API, không phải đoạn code chạy độc lập ngoài test framework.

Nếu tài liệu nhắm đến người dùng không sử dụng JUnit, hãy tạo một lớp `main` đầy đủ hoặc method ví dụ hoàn chỉnh và trích vùng tương ứng. Không tuyên bố một fragment thiếu context có thể copy-paste nguyên trạng vào mọi project.

Bài thực hành chọn JUnit fragment có chủ đích để đưa ra **bằng chứng test trực tiếp** cho cả success và exception.

## 9. Inline, external và hybrid snippet

Từ Java 18, Standard Doclet hỗ trợ các cách cung cấp nội dung:

| Cách | Ưu điểm | Cần chú ý |
| --- | --- | --- |
| Inline | Gọn, mã nằm ngay trong comment | Không tự compile/test, phải trích và tạo context |
| External | Có file source thật, dễ chạy compiler/JUnit | Cần đúng đường dẫn và named region |
| Hybrid | Có cả inline và external để đối chiếu | Hai phần sau xử lý phải khớp nhau |

Ví dụ inline ngắn:

```java
{@snippet lang="java" :
String text = "hello";
String upper = text.toUpperCase(java.util.Locale.ROOT);
}
```

Inline phù hợp khi code ngắn và rõ ngữ cảnh. Nhưng do nằm trong Javadoc comment, inline không thể chứa ký hiệu kết thúc Java comment, các dấu `{` và `}` phải cân bằng và Unicode escape trong source có thể được Java xử lý từ rất sớm.

Với bài này, ngoại lệ cần được tạo từ input thật và kiểm chứng bằng test runner nên **external snippet** thích hợp hơn.

## 10. Biên dịch code và xác minh source charset

Ví dụ trên dùng string literal tiếng Việt và emoji. Nên bảo đảm file source là UTF-8 và xác định encoding khi cần biên dịch tường minh:

```bash
javac --release 18 -encoding UTF-8 \
  -d target/classes \
  src/main/java/com/example/docs/Utf8Greeting.java
```

Trong đó:

- `--release 18` kiểm tra API và language level tương thích Java 18.
- `-encoding UTF-8` áp dụng cho **file source Java**, không phải file dữ liệu runtime.
- `-d` chỉ định thư mục chứa `.class` được tạo.

Lệnh này biên dịch **source chính**. Nó không đủ để xác nhận class test chứa snippet đã compile. Test source có JUnit dependency nên cần thêm classpath/test runner được cấu hình bởi build tool.

Với dự án Maven đã cấu hình JUnit Jupiter và Surefire:

```bash
mvn test
```

Với Gradle và `useJUnitPlatform()`:

```bash
./gradlew test --tests "com.example.docs.Utf8GreetingExamplesTest"
```

Hai lệnh là phương án tương ứng với build tool khác nhau; không chạy cả hai nếu project chỉ sử dụng một build tool.

## 11. Kiểm tra kết quả test thật, không chỉ BUILD SUCCESS

Kết quả mong đợi trong test report:

```text
Utf8GreetingExamplesTest
  readsValidUtf8Greeting        PASS
  rejectsBlankGreeting         PASS
  rejectsMalformedUtf8         PASS
```

Một build có thể xanh dù test bị skip hoặc runner không phát hiện được test. Vì vậy cần xác minh số lượng thực thi, không phải chỉ nhìn dòng cuối trong terminal.

Ba test chứng minh ba hợp đồng:

1. Thành công: chuỗi trả về bằng chuỗi mong đợi, gồm newline.
2. Dữ liệu trống: `isBlank()` dẫn tới `IllegalArgumentException`, message đúng.
3. Dữ liệu malformed: byte không hợp lệ làm `Files.readString(... UTF_8)` báo `IOException`.

Nếu test về exception chỉ có `try/catch` rồi bỏ qua, nó có thể pass ngay cả khi API không ném lỗi. Dùng `assertThrows` để test thất bại trong tình huống đó.

## 12. Sinh Javadoc với --snippet-path

Javadoc phải tìm được source test, dù trang tài liệu được sinh cho class trong `src/main/java`.

Ví dụ lệnh cho POSIX shell:

```bash
javadoc \
  -encoding UTF-8 \
  -docencoding UTF-8 \
  --snippet-path src/test/java \
  -sourcepath src/main/java \
  -d target/site/apidocs \
  com.example.docs
```

Các tham số:

| Tùy chọn | Ý nghĩa |
| --- | --- |
| `-encoding UTF-8` | Đọc source Java bằng UTF-8 |
| `-docencoding UTF-8` | Ghi HTML bằng UTF-8 |
| `--snippet-path src/test/java` | Thư mục gốc tìm file bên ngoài của snippet |
| `-sourcepath src/main/java` | Source tree chứa class cần sinh tài liệu |
| `-d target/site/apidocs` | Nơi nhận HTML |
| `com.example.docs` | Package cần tài liệu hóa |

Đường dẫn trong `file="com/example/docs/Utf8GreetingExamplesTest.java"` là đường dẫn **tương đối** so với root `src/test/java`.

Nếu sử dụng PowerShell, có thể truyền tất cả tham số trên một dòng, hoặc cấu hình qua task Javadoc của Maven/Gradle thay vì dùng cú pháp xuống dòng của POSIX shell.

### 12.1. Bật kiểm tra tài liệu mạnh hơn

```bash
javadoc -Werror -Xdoclint:all \
  -encoding UTF-8 \
  -docencoding UTF-8 \
  --snippet-path src/test/java \
  -sourcepath src/main/java \
  -d target/site/apidocs \
  com.example.docs
```

`-Werror` biến warning thành lỗi; `-Xdoclint:all` tăng phạm vi kiểm tra tài liệu. Chúng giúp phát hiện lỗi comment/tag/reference nhưng **vẫn không chạy JUnit**.

## 13. Xác minh HTML sau khi Javadoc build

Sau khi sinh, mở trang `Utf8Greeting` và kiểm tra:

- Có đủ ba snippet cho `success`, `blank-input`, `malformed-utf8`.
- Mã `Files.writeString(... UTF_8)` và `assertEquals` xuất hiện trong ví dụ success.
- `assertThrows(IllegalArgumentException.class, ...)` xuất hiện trong ví dụ blank.
- Byte fixture `C3 28` và `assertThrows(IOException.class, ...)` có trong ví dụ malformed.
- Markup `@start`/`@end` không bị hiển thị như code cần thực thi.
- Unicode tiếng Việt và emoji không bị mojibake.
- Không có lỗi đường dẫn file, sai tên region hoặc comment không hợp lệ.
- `@throws` trong Javadoc phản ánh các lỗi đúng như code.

Không nhất thiết so sánh toàn bộ HTML theo từng byte giữa các phiên bản JDK. Standard Doclet có thể thay đổi CSS hoặc cấu trúc markup mà nội dung snippet vẫn chính xác. Nếu viết kiểm tra HTML tự động, nên kiểm tra nội dung/region có ý nghĩa hơn là snapshot toàn bộ trang quá giòn.

## 14. Phân biệt lỗi nghiệp vụ và lỗi encoding

Cùng là một ví dụ lỗi nhưng cách chẩn đoán rất khác nhau:

```text
readGreeting(file)
       |
       v
Files.readString(file, UTF_8)
       |
       +-- Byte malformed --------> IOException
       |
       +-- Decode thành công
                 |
                 v
             text.isBlank()
                 |
          +------+------+
          |             |
         true          false
          |             |
          v             v
IllegalArgumentException   return text
```

`" \t\n"` là UTF-8 hợp lệ, nên dùng charset khác không giải quyết được quy tắc nghiệp vụ. Ngược lại, `C3 28` không hợp lệ theo UTF-8 nên không nên âm thầm thay byte lỗi hoặc thử Latin-1 để test tiếp tục xanh.

`assertThrows(IOException.class, ...)` chấp nhận subtype của `IOException`, đúng với cách khai báo hợp đồng của API Files. Chỉ dùng `assertThrowsExactly` khi thư viện thực sự cam kết một exception class chính xác.

## 15. Thêm fixture byte độc lập để kiểm tra encoding

Test success ở mục 6 là integration test: producer dùng `Files.writeString(... UTF_8)` và consumer dùng `readGreeting`. Nếu cần kiểm tra thêm chính xác biểu diễn byte, dùng fixture byte đã biết thay vì chỉ round-trip theo cùng charset.

Ví dụ cho `Café\n`:

```java
@Test
void readsKnownUtf8Bytes(@TempDir Path tempDir) throws IOException {
    Path file = tempDir.resolve("known-utf8.txt");
    byte[] fixture = {
            0x43, 0x61, 0x66, (byte) 0xC3, (byte) 0xA9, 0x0A
    };
    Files.write(file, fixture);

    assertEquals("Café\n", Utf8Greeting.readGreeting(file));
}
```

Đây là ví dụ mở rộng, cần được thêm vào **bên trong lớp test** với các import đã có ở mục 6 nếu muốn chạy thật. Mục tiêu là xác nhận đầu vào UTF-8 theo byte fixture độc lập.

Không dùng ảnh terminal làm bằng chứng cho encoding; so sánh byte hoặc chuỗi Unicode trong test.

## 16. Kiểm thử các trường hợp biên khác

Bên cạnh ba snippet được chọn cho tài liệu, test suite có thể chứa thêm:

```java
@Test
void rejectsNullPath() {
    assertThrows(
            NullPointerException.class,
            () -> Utf8Greeting.readGreeting(null));
}

@Test
void reportsMissingFile(@TempDir Path tempDir) {
    Path missing = tempDir.resolve("not-created.txt");

    assertThrows(
            IOException.class,
            () -> Utf8Greeting.readGreeting(missing));
}
```

`null` là lỗi tham số của caller; file không tồn tại là lỗi filesystem; byte malformed là lỗi decode; chuỗi blank là lỗi nghiệp vụ. Chúng không nên bị gom làm một lỗi chung nếu API cần giúp caller xử lý phù hợp.

Nếu người học thêm hai test này, phải đặt code vào class test với import JUnit tương ứng, không chỉ dán fragment tự do vào ngoài class.

## 17. Giữ sự trung thực của snippet khi dùng markup trình bày

JEP 413 còn có những markup như `@highlight`, `@replace`, `@link` để tăng khả năng đọc. Nhưng một code example được tô màu hoặc thay text trong HTML không nhất thiết giống hoàn toàn code chạy.

Các rủi ro:

- Đổi tên method chỉ ở đoạn render, không đổi nguồn test.
- Ẩn dòng setup quan trọng khiến exception xuất hiện không có nguyên nhân.
- Thay literal lỗi bằng literal khác không được test.
- Render ví dụ dùng biến hoặc type không có trong code thực tế.

Nếu một đoạn mã trình bày khác hành vi được kiểm thử, hãy tạo test cho chính đoạn mã đó. Không dùng presentation markup để che sự thiếu đồng bộ giữa API và docs.

## 18. Thiết kế pipeline CI đủ ba cổng

```text
CHECKOUT
   |
   v
COMPILE main + test
   |  fail -> stop
   v
RUN JUnit
   |  fail / 0 tests -> stop
   v
GENERATE Javadoc --snippet-path
   |  fail -> stop
   v
REVIEW HTML / publish docs artifact
```

Với Maven project có JUnit 5 được cấu hình:

```bash
mvn -q test

javadoc -Werror -Xdoclint:all \
  -encoding UTF-8 \
  -docencoding UTF-8 \
  --snippet-path src/test/java \
  -sourcepath src/main/java \
  -d target/site/apidocs \
  com.example.docs
```

Trong CI thực tế, có thể cấu hình Maven Javadoc Plugin hoặc Gradle Javadoc task để quản lý option. Quan trọng là thứ tự và **exit code** của các bước, không phải việc dùng công cụ cụ thể nào.

Hãy xác nhận có report ít nhất ba test success/error, Javadoc build không báo thiếu region và HTML chứa đúng ví dụ.

## 19. Khắc phục các lỗi dễ gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Javadoc pass, code trong snippet không compile | Doclet không biên dịch ví dụ | Compile test source riêng |
| Build success nhưng 0 tests | JUnit engine/test discovery cấu hình sai | Kiểm tra runner và tên lớp `*Test` |
| Javadoc không thấy file | Sai `--snippet-path` hoặc file path | Đối chiếu root và package |
| Region không tìm thấy | Tên region sai/thiếu `@start` | Kiểm tra marker và tag |
| Exception test pass khi API không ném lỗi | `try/catch` không có assertion | Dùng `assertThrows` |
| Test fail trên CI vì đường dẫn | Dùng đường dẫn cố định | Dùng `@TempDir` |
| Unicode trên terminal sai | Output charset/font không khớp | Assert Unicode/byte trong test |
| Javadoc hiển thị mã cũ | Dùng bản sao snippet hoặc build cache | Trích chính source test trong revision hiện tại |
| Test lỗi với subtype khác | Assert exception cụ thể hơn hợp đồng | Bám vào `IOException` nếu đó là hợp đồng |

## 20. Kiểm tra cuối trước khi merge

- [ ] API có hợp đồng thành công, validation error và I/O error rõ ràng.
- [ ] `StandardCharsets.UTF_8` được truyền tường minh.
- [ ] Source Java API có Javadoc và `@throws` phù hợp.
- [ ] Source test có import, class và các method `@Test` hoàn chỉnh.
- [ ] Các vùng `success`, `blank-input`, `malformed-utf8` nằm trong code chạy thật.
- [ ] Javadoc tag và marker `@start`/`@end` trùng khớp.
- [ ] Test success có assertion về nội dung Unicode và newline.
- [ ] Test validation dùng `assertThrows(IllegalArgumentException.class, ...)`.
- [ ] Test encoding dùng byte malformed và `assertThrows(IOException.class, ...)`.
- [ ] Test runner thực thi test, không báo 0 test.
- [ ] Main source và test source compile với JDK mục tiêu.
- [ ] Javadoc dùng JDK 18+ và `--snippet-path`.
- [ ] HTML đã được review về nội dung ba snippet.
- [ ] Không duy trì hai bản mã ví dụ độc lập.
- [ ] CI thất bại khi compile, JUnit hoặc Javadoc lỗi.

## 21. Những nhận định sai thường gặp

- **“`{@snippet}` tự biên dịch và chạy code.”** Sai. Standard Doclet hỗ trợ trình bày, không thực thi code.
- **“Javadoc build pass chứng minh exception path đúng.”** Sai. Cần test tạo input gây lỗi.
- **“Test pass bảo đảm HTML trích đúng.”** Sai. Javadoc vẫn có thể trỏ sai file/region.
- **“Một dòng throw trong ví dụ đã kiểm thử ngoại lệ của API.”** Sai. Ngoại lệ phải phát sinh từ API xử lý input.
- **“`assertThrows` chỉ chấp nhận đúng class, không nhận subtype.”** Sai. Nó chấp nhận subtype phù hợp.
- **“Blank content và malformed UTF-8 là cùng một lỗi.”** Sai. Một lỗi validation, một lỗi decode.
- **“Có @Test là chắc chắn runner chạy.”** Sai. Cần cấu hình JUnit Platform và kiểm tra report.
- **“Từ Java 18 có thể bỏ mọi tham số charset.”** Sai. Encoding của payload thuộc hợp đồng, không phải default JVM.
- **“Nếu ví dụ render đẹp thì có thể bỏ bước compile.”** Sai. Ví dụ có thể chứa import/signature không tồn tại.
- **“Inline snippet luôn tốt hơn external.”** Không đúng; external có lợi thế lớn khi cần test runtime.

## 22. Tài liệu tham khảo

- [JEP 413 — Code Snippets in Java API Documentation](https://openjdk.org/jeps/413): thẻ snippet được giới thiệu từ Java 18.
- [Programmer's Guide to Snippets — JDK 18](https://docs.oracle.com/en/java/javase/18/code-snippet/index.html): inline/external snippet, named region và cách kiểm thử bằng công cụ ngoài doclet.
- [Javadoc Documentation Comment Specification — JDK 18](https://docs.oracle.com/en/java/javase/18/docs/specs/javadoc/doc-comment-spec.html): cú pháp tag và markup.
- [Snippets — JDK 26](https://docs.oracle.com/en/java/javase/26/javadoc/snippets.html): hướng dẫn áp dụng trên JDK hiện đại.
- [Files — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html): `readString`, `writeString` và lỗi khi decode.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): `@Test`, `@TempDir`, `assertThrows` và chạy test.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): giải thích thay đổi default charset từ Java 18.

