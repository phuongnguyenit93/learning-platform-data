# Chuyển dữ liệu nhiều dòng thành text block có kiểm thử

**Bài thực hành Java 15+**: chuyển những chuỗi chứa nhiều dòng đang viết bằng nối chuỗi và ký tự thoát (`\n`, `\"`, `\\`) sang **text block**, sau đó viết kiểm thử để chứng minh dữ liệu đầu ra vẫn đúng từng ký tự. Nội dung áp dụng trên các JDK hiện đại, đặc biệt Java 17+; text block trở thành tính năng ngôn ngữ chính thức từ **Java 15 (JEP 378)** và vẫn được hỗ trợ.

Mục tiêu không đơn thuần là làm mã gọn hơn. Một bản chuyển đổi đạt yêu cầu phải bảo toàn **cấu trúc dòng, dấu cách có ý nghĩa, dấu ngoặc kép, dấu gạch chéo ngược và dấu xuống dòng cuối cùng** theo hợp đồng của ứng dụng. Những sai khác nhỏ trong JSON, SQL, HTML, email hoặc dữ liệu kiểm thử có thể làm chương trình hoạt động khác trước.

## 1. Kết quả học tập và phạm vi

Sau bài thực hành, bạn có thể:

1. Nhận diện trường hợp có lợi khi đổi một chuỗi nhiều dòng cố định trong mã Java thành `""" ... """`.
2. Viết đúng cú pháp, hiểu quy tắc mở/đóng dấu phân cách ba dấu nháy kép.
3. Dự đoán chính xác chuỗi mà compiler tạo ra sau khi chuẩn hóa xuống dòng, loại thụt lề phụ và xử lý escape.
4. Chuyển SQL/JSON nhiều dòng từ phép nối chuỗi sang text block mà vẫn giữ dữ liệu.
5. Tạo **kiểm thử hồi quy** bằng so sánh `String.equals` và xác nhận riêng các trường hợp whitespace/escaping.
6. Phân biệt **literal nằm trong mã nguồn** với dữ liệu nhiều dòng được đọc **lúc chạy** từ file/API.
7. Nhận diện lúc cần `\s`, ký tự `\` nối dòng, `\\` và `.formatted(...)`, tránh đưa vào ứng dụng những thay đổi nội dung ngoài ý muốn.

**Đầu ra thực hành:** tệp Java độc lập `TextBlockMigrationDemo.java`, chạy được trên Java 17+, in trạng thái kiểm thử; thêm ví dụ `JUnit Jupiter` để tích hợp vào dự án có framework kiểm thử.

## 2. Text block là gì?

Text block là một cách viết **`String` literal** có thể trải trên nhiều dòng. Nó vẫn có kiểu `java.lang.String`, nên các phương thức như `equals`, `length`, `formatted`, `getBytes` hoạt động như với chuỗi thông thường.

Ví dụ viết chuỗi nhiều dòng trước và sau khi chuyển:

```java
// Viết bằng string literal và nối chuỗi:
String before = "Đơn hàng:\n"
              + "- Mã: 42\n"
              + "- Trạng thái: OK\n";

// Viết bằng text block:
String after = """
    Đơn hàng:
    - Mã: 42
    - Trạng thái: OK
    """;

System.out.println(before.equals(after)); // true
```

Đây là **đoạn mã minh họa** đặt trong phương thức Java. Hai chuỗi đều bằng `"Đơn hàng:\n- Mã: 42\n- Trạng thái: OK\n"`. Dấu `"""` mở phải được theo sau bởi một **ký tự kết thúc dòng**, nên không thể viết nội dung ngay sau dấu mở trên cùng dòng.

Text block là literal được xử lý khi **biên dịch**, không tự đọc file hay biến đổi dữ liệu bất kỳ đang nhận từ mạng. Nếu dữ liệu thay đổi lúc chạy, hãy giữ cách đọc dữ liệu bằng `Files.readString`, reader hoặc API tương ứng và chỉ dùng text block cho những mẫu/fixture tĩnh trong mã nguồn.

### 2.1. Ba bước mà compiler thực hiện

Về ngữ nghĩa, Java xử lý nội dung của text block theo thứ tự:

1. **Chuẩn hóa line terminator** trong nguồn: CRLF (`\r\n`) và CR (`\r`) thành LF (`\n`).
2. **Loại incidental whitespace**: bỏ phần thụt lề chung được xem là phụ; bỏ khoảng trắng cuối dòng không được bảo vệ.
3. **Giải mã escape sequences** như `\n`, `\t`, `\s`, `\\`, `\"`, và `\` ngay trước dấu kết thúc dòng.

Thứ tự rất quan trọng. Chẳng hạn `\s` được chuyển thành dấu cách **sau** bước xử lý khoảng trắng cuối dòng nên có thể giữ một dấu cách ở cuối dòng.

Ví dụ:

```java
String message = """
    A
      B
    """;
```

Giá trị thực tế là `"A\n  B\n"`: `A` không có dấu cách đầu dòng, `B` có **hai** dấu cách đầu dòng, và chuỗi **kết thúc bằng `\n`**.

### 2.2. Dấu đóng quyết định việc có newline cuối hay không

Nếu ba dấu nháy đóng đứng **trên dòng riêng**, dòng nội dung cuối có ký tự LF:

```java
String withFinalLf = """
    alpha
    beta
    """;
// "alpha\nbeta\n"
```

Nếu dấu đóng nằm **ngay sau chữ cuối cùng**, chuỗi không có LF cuối:

```java
String withoutFinalLf = """
    alpha
    beta""";
// "alpha\nbeta"
```

Cũng có thể bỏ LF cuối bằng escape nối dòng, giữ dấu đóng trên dòng riêng:

```java
String withoutFinalLf = """
    alpha
    beta\
    """;
// "alpha\nbeta"
```

Ba ví dụ trên là **những khai báo thay thế nhau**; đặt chung vào một khối mã cần đổi tên biến để tránh khai báo trùng. Không giả định rằng `println` hoặc editor hiển thị sự khác biệt cuối chuỗi: phải kiểm tra `equals`, `endsWith("\n")`, `length()` hoặc byte output.

### 2.3. Khoảng trắng: giữ và bỏ có chủ đích

Ví dụ có độ thụt lề có ý nghĩa:

```java
String tree = """
    root
      child
    """;
// "root\n  child\n"
```

Khoảng trắng chung phía trước `root` và `child` do vị trí trong source file sẽ bị bỏ, nhưng hai dấu cách tương đối trước `child` được giữ.

Khoảng trắng cuối dòng nguồn mặc định bị loại. Nếu ứng dụng thực sự cần một dấu cách sau ký tự `X`, dùng `\s`:

```java
String content = """
    X\s
    """;
// "X \n"
```

Trong trường hợp dòng rất dài, dấu `\` ngay trước line terminator cho phép nối hai dòng nguồn thành **một dòng trong giá trị**:

```java
String joined = """
    alpha\
    beta
    """;
// "alphabeta\n"
```

Dấu `\s` và nối dòng là tính năng đang được hỗ trợ; dùng có chủ đích và có test. Không lạm dụng chúng chỉ để làm mã ngắn.

### 2.4. Text block không phải chuỗi raw

Text block giảm số dấu escape cần viết, nhưng **vẫn diễn giải escapes**. Dấu ngoặc kép JSON thông thường có thể viết trực tiếp; dấu backslash muốn xuất hiện trong dữ liệu cần được escape:

```java
String json = """
    {"message": "first\\nsecond"}
    """;
```

Giá trị chuỗi Java gồm các ký tự `{"message": "first\nsecond"}` theo **cách nhìn có backslash và chữ `n`**, chứ không phải xuống dòng thực bên trong giá trị JSON. Trong Java source text block, `\\n` tạo ra hai ký tự `\` và `n` trong JSON. Nếu viết `\n`, Java chuyển nó thành LF thực, có thể làm JSON không hợp lệ vì chứa line break không thoát trong string value.

Các chuỗi có nhiều dấu nháy kép liên tiếp, đặc biệt `"""` lồng bên trong, có thể cần escape một dấu nháy để không vô tình đóng text block. Không tự loại hết dấu `\` từ dữ liệu cũ khi chuyển đổi.

## 3. Quy trình chuyển đổi có kiểm thử

Giả sử bạn đang bảo trì một câu SQL hoặc fixture JSON nhiều dòng được khai báo bằng phép nối chuỗi. Quy trình thực hành nên làm như sau:

1. **Ghi nhận hợp đồng trước khi đổi:** dòng nào có dấu cách đầu/cuối; có dòng trống không; dùng LF hay CRLF; chuỗi có newline ở cuối không; các ký tự `\` và `"` có ý nghĩa gì.
2. **Giữ biến hoặc hàm khai báo cũ làm oracle trong bài test** và viết test xác nhận nội dung mong đợi bằng literal rõ ràng. Đừng coi một output sai có sẵn là “đúng” chỉ vì nó hiện tại giống mã cũ.
3. **Viết text block** có mở/đóng rõ ràng, căn lề nhất quán, giữ chính xác ký tự thuộc dữ liệu. Chọn dấu đóng trên dòng riêng hay cuối dòng theo hợp đồng newline.
4. **So sánh chuỗi thực tế** bằng `expected.equals(actual)` hoặc `assertEquals(expected, actual)`. Thêm assertion riêng cho số dòng, khoảng trắng, newline cuối và chuỗi escape.
5. **Chạy test tự động** trên đúng JDK và cùng encoding với dự án; chỉ loại bỏ oracle cũ khi đã giữ được fixture/assertion độc lập.
6. Khi dữ liệu là template hoặc SQL, xác nhận thêm hành vi ở **nơi tiêu thụ**: parser JSON có đọc được không, database driver có nhận câu SQL đúng không, renderer HTML có tạo output mong muốn không.

Không dùng `String.trim()`, `strip()`, `replaceAll("\\s+", " ")` hay `lines().collect(joining(...))` như biện pháp “làm cho test qua”, vì những phép đó **thay đổi** nội dung. Nếu ứng dụng cho phép chuẩn hóa, cần ghi rõ quy tắc chuẩn hóa rồi kiểm thử kết quả đã chuẩn hóa.

## 4. Bài thực hành hoàn chỉnh: chuyển SQL, JSON và kiểm thử byte-đúng

Tạo tệp **`TextBlockMigrationDemo.java`** với nội dung sau. Mã chỉ dùng Java SE, không cần thư viện ngoài. Phương thức `same` ném `AssertionError` khi có sai khác; không phụ thuộc vào tùy chọn JVM `-ea`. Các `original...()` biểu diễn kiểu khai báo cũ để đối chiếu trong thực hành.

```java
public final class TextBlockMigrationDemo {

    private TextBlockMigrationDemo() {
        // Utility class: chỉ chứa ví dụ thực hành.
    }

    static String originalSql() {
        return "SELECT id, name\n"
             + "FROM customers\n"
             + "WHERE status = ?\n"
             + "ORDER BY id\n";
    }

    static String sqlTextBlock() {
        return """
            SELECT id, name
            FROM customers
            WHERE status = ?
            ORDER BY id
            """;
    }

    static String originalJson() {
        return "{\n"
             + "  \"message\": \"line1\\nline2\",\n"
             + "  \"enabled\": true\n"
             + "}\n";
    }

    static String jsonTextBlock() {
        return """
            {
              "message": "line1\\nline2",
              "enabled": true
            }
            """;
    }

    static String treeTextBlock() {
        return """
            root
              child
            """;
    }

    static String withoutFinalLf() {
        return """
            alpha
            beta""";
    }

    static String preserveTrailingSpace() {
        return """
            X\s
            """;
    }

    static String joinSourceLines() {
        return """
            alpha\
            beta
            """;
    }

    static String greetingTemplate() {
        return """
            Xin chào, %s!
            Số bản ghi: %d
            """.formatted("Lan", 3);
    }

    private static String visible(String text) {
        return text.replace("\\", "\\\\")
                   .replace("\r", "\\r")
                   .replace("\n", "\\n")
                   .replace(" ", "·");
    }

    private static void same(String name, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(name
                    + "\nExpected: [" + visible(expected) + "]"
                    + "\nActual:   [" + visible(actual) + "]");
        }
    }

    public static void main(String[] args) {
        String sqlExpected =
                "SELECT id, name\n"
              + "FROM customers\n"
              + "WHERE status = ?\n"
              + "ORDER BY id\n";

        same("SQL baseline", sqlExpected, originalSql());
        same("SQL migrated", sqlExpected, sqlTextBlock());
        same("SQL before/after", originalSql(), sqlTextBlock());
        System.out.println("PASS SQL migration");

        String jsonExpected =
                "{\n"
              + "  \"message\": \"line1\\nline2\",\n"
              + "  \"enabled\": true\n"
              + "}\n";

        same("JSON baseline", jsonExpected, originalJson());
        same("JSON migrated", jsonExpected, jsonTextBlock());
        same("JSON before/after", originalJson(), jsonTextBlock());
        System.out.println("PASS JSON migration");

        same("indentation", "root\n  child\n", treeTextBlock());
        same("without final LF", "alpha\nbeta", withoutFinalLf());
        same("trailing space", "X \n", preserveTrailingSpace());
        same("joined lines", "alphabeta\n", joinSourceLines());
        System.out.println("PASS whitespace and newlines");

        same("formatting", "Xin chào, Lan!\nSố bản ghi: 3\n",
             greetingTemplate());
        System.out.println("PASS formatted text block");

        System.out.println("ALL CHECKS PASSED");
    }
}
```

Biên dịch với UTF-8 và bật cảnh báo liên quan đến text block:

```bash
javac -encoding UTF-8 -Xlint:text-blocks TextBlockMigrationDemo.java
java TextBlockMigrationDemo
```

**Stdout chính xác khi các test đều thành công:**

```text
PASS SQL migration
PASS JSON migration
PASS whitespace and newlines
PASS formatted text block
ALL CHECKS PASSED
```

Nếu bất kỳ phép so sánh nào thất bại, chương trình ném `AssertionError` kèm biểu diễn dễ đọc: LF thành `\n`, CR thành `\r`, dấu cách thành `·` và backslash thành `\\`. Nhờ vậy bạn nhìn thấy sai lệch cuối dòng hoặc dấu cách mà console thường che mất. `-Xlint:text-blocks` giúp phát hiện một số kiểu thụt lề không nhất quán hoặc whitespace cuối dòng có nguy cơ bị bỏ; cách công cụ hiện cảnh báo có thể khác giữa các JDK.

### 4.1. Giải thích các kiểm thử trong ví dụ

**SQL:** Bản nối chuỗi và bản text block đều chứa dấu `?` giữ chỗ tham số. Kiểm thử so sánh từng ký tự gồm `\n`, không chỉ tìm từ khóa `SELECT`. Trong ứng dụng thực, giá trị cho `?` được bind qua `PreparedStatement`, **không** ghép dữ liệu người dùng bằng `.formatted()` vào SQL để tránh injection.

**JSON:** Bản cũ có literal Java `"\\n"` khi biểu diễn trong source; nó tạo ra `\n` theo nghĩa **hai ký tự backslash và `n`** trong dữ liệu JSON. Text block cũng phải viết `\\n` để giữ cùng nội dung. Dấu nháy kép bao quanh tên thuộc tính và chuỗi JSON không cần `\"` vì chúng không đóng text block.

**Indentation:** Trong `treeTextBlock`, hai dấu cách tương đối trước `child` là dữ liệu thật và phải tồn tại. Chỉ nhìn mã nguồn mà không kiểm thử rất dễ nhầm chúng với phần thụt lề phụ.

**Final newline:** `withoutFinalLf` đặt dấu đóng ngay sau `beta`; test đòi chuỗi kết thúc bằng ký tự `a`, không có `\n` cuối. Ngược lại, các text block đóng trên dòng riêng trong bài có newline cuối.

**Trailing space:** `preserveTrailingSpace` có `\s` trước LF; `same("trailing space", "X \n", ...)` sẽ phát hiện nếu ai đó xóa escape này.

**Line continuation:** Dấu `\` ở cuối dòng sau `alpha` nối chữ `alpha` và `beta` thành `alphabeta`, đồng thời dòng cuối vẫn kết thúc bằng LF vì dấu đóng trên dòng riêng.

**Formatting:** `.formatted("Lan", 3)` thay `%s` và `%d`, trả về một `String` bình thường. Nó dùng định dạng `java.util.Formatter`, **không phải** nội suy biến tự động; dấu `%` thật trong template có thể cần viết `%%`.

### 4.2. Kiểm chứng dữ liệu ở mức byte khi có yêu cầu

Nếu hợp đồng tệp đòi UTF-8 và LF, ngoài so sánh chuỗi có thể dùng:

```java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

// Đoạn mã nằm bên trong phương thức kiểm thử:
byte[] before = originalSql().getBytes(StandardCharsets.UTF_8);
byte[] after = sqlTextBlock().getBytes(StandardCharsets.UTF_8);
if (!Arrays.equals(before, after)) {
    throw new AssertionError("UTF-8 bytes changed");
}
```

**Đây là đoạn mã minh họa, không phải một tệp Java độc lập.** Hai `import` cần đặt đầu tệp; hai phương thức trong ví dụ thuộc `TextBlockMigrationDemo`, nên trong lớp khác phải gọi qua tên lớp hoặc truy cập theo cách phù hợp. Nếu hai `String` bằng nhau thì mã hóa bằng cùng UTF-8 tất nhiên tạo cùng bytes; phép so byte hữu ích để làm rõ yêu cầu tích hợp với file, HTTP hoặc hệ thống ngoài.

Dữ liệu đọc từ file nguồn theo CRLF (`\r\n`) **không tự động tương đương** với text block dùng LF. Nếu hợp đồng chấp nhận chuẩn hóa, viết rõ bước đổi CRLF/CR sang LF rồi kiểm thử. Nếu bắt buộc giữ byte CRLF, cần tạo đúng chuỗi có `\r\n` hoặc dùng resource fixture giữ nguyên nội dung.

## 5. Viết bài test JUnit Jupiter

Mã `main` tiện để học và chạy nhanh. Trong dự án có JUnit Jupiter, hãy tạo **`TextBlockMigrationDemoTest.java`** ở test source set cùng package với lớp ví dụ. Các test dưới đây gọi các phương thức `static` package-private trong bài thực hành.

```java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class TextBlockMigrationDemoTest {

    @Test
    void sqlTextBlockMatchesExactBaseline() {
        String expected =
                "SELECT id, name\n"
              + "FROM customers\n"
              + "WHERE status = ?\n"
              + "ORDER BY id\n";

        assertEquals(expected, TextBlockMigrationDemo.originalSql());
        assertEquals(expected, TextBlockMigrationDemo.sqlTextBlock());
        assertTrue(TextBlockMigrationDemo.sqlTextBlock().endsWith("\n"));
    }

    @Test
    void jsonPreservesBackslashAndQuotes() {
        String expected = """
            {
              "message": "line1\\nline2",
              "enabled": true
            }
            """;

        assertEquals(expected, TextBlockMigrationDemo.jsonTextBlock());
        assertTrue(expected.contains("line1\\nline2"));
        assertFalse(expected.contains("line1\nline2"));
    }

    @Test
    void indentationAndFinalLineAreStable() {
        assertEquals("root\n  child\n",
                     TextBlockMigrationDemo.treeTextBlock());
        assertEquals("alpha\nbeta",
                     TextBlockMigrationDemo.withoutFinalLf());
        assertFalse(TextBlockMigrationDemo.withoutFinalLf()
                                       .endsWith("\n"));
    }

    @Test
    void escapeProcessingIsIntentional() {
        assertEquals("X \n",
                     TextBlockMigrationDemo.preserveTrailingSpace());
        assertEquals("alphabeta\n",
                     TextBlockMigrationDemo.joinSourceLines());
        assertEquals("Xin chào, Lan!\nSố bản ghi: 3\n",
                     TextBlockMigrationDemo.greetingTemplate());
    }
}
```

Các assertion chứng minh cả **giá trị tổng thể** lẫn **điểm dễ sai**. Riêng test JSON cần lưu ý `expected` cũng là text block nên chưa phải oracle độc lập hoàn toàn; trong dự án nghiêm ngặt, thêm fixture dạng literal `String` tường minh, file mẫu có hash đã duyệt, hoặc parser JSON để xác minh cú pháp và dữ liệu sau parse.

Để chạy JUnit, dự án cần khai báo dependency và bộ chạy tương ứng. Ví dụ cấu hình **Gradle Groovy DSL**:

```groovy
dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.13.4'
}

test {
    useJUnitPlatform()
}
```

Đây là **ví dụ cú pháp**, không buộc dự án phải dùng đúng version trên. Hãy lấy phiên bản JUnit thích hợp từ BOM/version catalog của dự án đang dùng. Trong Maven, cấu hình dependency và Surefire/JUnit Platform tương ứng. Không thể biên dịch tệp JUnit độc lập bằng `javac` thuần khi thiếu thư viện trên classpath.

## 6. Trường hợp chuyển đổi cần đặc biệt cẩn thận

### 6.1. Dữ liệu có dòng trống

Một dòng trống giữa hai dòng nội dung vẫn có ý nghĩa:

```java
String note = """
    Đoạn một.

    Đoạn hai.
    """;
// "Đoạn một.\n\nĐoạn hai.\n"
```

Test thích hợp là `assertEquals("Đoạn một.\n\nĐoạn hai.\n", note)`. Chỉ đếm số dòng bằng `String.lines()` không chứng minh đầy đủ có hay không LF cuối vì API này trả một stream các dòng mà không giữ delimiter.

### 6.2. Dữ liệu chứa khoảng trắng cố định

Một file giao thức hoặc fixture biểu diễn bảng theo độ rộng cố định có thể cần số cột, số dấu cách và LF chính xác. Không phụ thuộc vào khoảng trắng vô hình cuối dòng trong source code. Nếu cần một dấu cách cuối dòng dùng `\s`; nhiều dấu cách có thể dùng nhiều `\s`, escape bát phân `\040` hoặc các phương án có kiểm thử rõ ràng. Căn lề bằng Tab và space trộn nhau dễ tạo kết quả khó đoán vì compiler đếm ký tự whitespace theo quy tắc ngôn ngữ, không theo độ rộng hiển thị của editor.

Ví dụ giữ **hai** dấu cách sau `A`:

```java
String fixed = """
    A\s\s
    B
    """;
// "A  \nB\n"
```

Không dùng editor tự thêm/xóa trailing whitespace để tạo dữ liệu định dạng cố định mà không có assertion.

### 6.3. Chuỗi nguồn có CRLF

Java compiler chuẩn hóa line endings **của text block trong source** thành LF. Ví dụ hai bản Java source có dòng kết thúc CRLF hoặc LF vẫn tạo text block cùng cách xuống dòng logic. Nhưng nếu mã cũ tạo chuỗi `"\r\n"` một cách tường minh, chuyển sang text block với các dòng mới sẽ đổi thành `"\n"`:

```java
String oldProtocol = "A\r\nB\r\n";
String newProtocol = """
    A
    B
    """;

System.out.println(oldProtocol.equals(newProtocol)); // false
```

Muốn **bảo toàn CRLF** có thể tạo text block bằng LF rồi thay line endings sau đó (nếu yêu cầu rõ ràng):

```java
String protocolCrLf = """
    A
    B
    """.replace("\n", "\r\n");
```

Hai đoạn trên là các khai báo minh họa; đừng áp dụng đổi line ending mù quáng cho dữ liệu đã chứa CRLF hoặc dữ liệu binary. Khi làm với định dạng có tiêu chuẩn line endings riêng, test byte stream hoặc file fixture thật.

### 6.4. HTML, JSON và nội dung có nhiều dấu ngoặc kép

Text block thường làm template HTML/JSON dễ đọc hơn:

```java
String html = """
    <section>
      <p class="notice">Xin chào</p>
    </section>
    """;
```

Chỉ các dấu `"` riêng lẻ trong HTML không cần escape. Nếu nội dung thực sự chứa ba dấu nháy kép liền nhau, phải kiểm tra cách viết escape để parser Java không nhầm chúng thành dấu kết thúc text block. Với JSON, vẫn phải bảo vệ các escape thuộc JSON (`\\n`, `\\t`, `\\uXXXX` khi muốn lưu ký tự backslash thực) theo nhu cầu của dữ liệu.

Không đánh giá một text block là “JSON đúng” chỉ vì chương trình Java biên dịch: test `String` không thể thay thế test parse JSON, schema validation hoặc consumer integration.

### 6.5. Template động với `.formatted(...)`

Ví dụ:

```java
String report = """
    Người nhận: %s
    Số lượng: %d
    """.formatted("Lan", 4);
```

Kết quả là `"Người nhận: Lan\nSố lượng: 4\n"`. Nếu template có dấu phần trăm cần giữ nguyên, dùng `%%` theo quy tắc `Formatter`. Định dạng số, thời gian và locale có thể ảnh hưởng output; với dữ liệu cần tái hiện tuyệt đối, chỉ định locale/phương thức định dạng rõ và test chúng.

**Không dùng text block + `.formatted(userInput)` làm cơ chế escaping an toàn cho SQL, HTML hoặc JSON**. `formatted` chỉ chèn chữ theo format, không tự bind SQL parameters, không mã hóa JSON và không escape HTML. Với SQL dùng bind parameters, với JSON dùng serializer, với HTML dùng escape theo ngữ cảnh.

### 6.6. Đọc dữ liệu nhiều dòng lúc chạy

Nếu yêu cầu ban đầu là “đọc nội dung nhiều dòng từ file” rồi đưa nó vào xử lý, text block không thay thế thao tác đọc:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

// Bên trong phương thức có throws IOException hoặc xử lý ngoại lệ:
String data = Files.readString(Path.of("input.txt"),
                               StandardCharsets.UTF_8);
```

Đây là **đoạn mã phụ thuộc vào file và xử lý ngoại lệ**, không phải chương trình độc lập. Nó đọc đúng dữ liệu runtime; dữ liệu thay đổi khi file đổi. Ngược lại, text block được lưu trong source và được đóng gói cùng chương trình. Có thể dùng text block làm dữ liệu *expected* cho test với input file, nhưng nên lưu fixture bên ngoài nếu nó lớn hoặc cần sửa độc lập.

### 6.7. Text block trong test snapshot/golden file

Với những output như SQL, email hoặc báo cáo, bạn có thể viết giá trị kỳ vọng bằng text block để dễ review. Tuy vậy, nếu cả **implementation** và **expected** được sửa cùng lúc, test có thể tiếp tục PASS dù yêu cầu nghiệp vụ đã thay đổi sai. Cách tốt hơn:

- Phê duyệt fixture/golden output độc lập khi nội dung quan trọng.
- So sánh thông tin có ý nghĩa với parser/schema khi phù hợp, bên cạnh kiểm tra byte/chuỗi.
- Chỉ chủ động chuẩn hóa nội dung khi hợp đồng cho phép; ghi quy tắc chuẩn hóa vào test.
- Review diff hiển thị dấu cách và line endings khi có đổi template.

## 7. Bộ test tối thiểu trước khi xóa cách viết chuỗi cũ

| Ca kiểm thử | Đầu vào/giá trị chuyển đổi | Assertion cần có |
| --- | --- | --- |
| Nhiều dòng cơ bản | Hai hoặc nhiều dòng text | `equals` với chuỗi gốc đã chốt |
| Dấu ngoặc kép | HTML/JSON có `"..."` | Giữ nguyên mọi `"` |
| Backslash literal | JSON chứa `\\n` dưới dạng mã nguồn Java | Giá trị JSON giữ **backslash + n** |
| Thụt lề tương đối | `root`, `  child` | Hai dấu cách trước `child` vẫn có |
| Dòng trống | Dòng giữa hai đoạn | Hai ký tự LF liên tiếp |
| LF cuối | Dấu đóng ở dòng riêng | `endsWith("\n") == true` khi hợp đồng yêu cầu |
| Không LF cuối | Dấu đóng sát chữ cuối hoặc nối dòng | `endsWith("\n") == false` |
| Trailing space có chủ đích | `X\s` | `"X \n"` |
| Nối hai dòng nguồn | `alpha\` và `beta` | `"alphabeta\n"` |
| CRLF đầu vào cũ | `"\r\n"` | Test rõ có bảo toàn CRLF hoặc chuẩn hóa hợp lệ |
| Kết quả định dạng | `%s`, `%d`, `%%` | Ký tự, newline và giá trị thế đúng |
| Parser/consumer | SQL, JSON, HTML, template | Tác vụ tiếp theo hiểu đúng nội dung |

Mức độ kiểm thử nên theo tác động nghiệp vụ. Chuỗi làm tài liệu hiển thị thông thường có thể chỉ cần so sánh nội dung; dữ liệu ký, giao thức, export chuẩn hoặc golden file phải kiểm tra encoding/line endings ở mức byte nếu hợp đồng đòi hỏi.

## 8. Lỗi thường gặp và cách sửa

1. **Đặt nội dung ngay sau `"""` mở.** Text block phải có line terminator sau dấu mở; nếu chỉ có một dòng, string literal thông thường có thể đơn giản hơn.
2. **Quên newline cuối.** Đóng `"""` ở dòng riêng làm có LF sau dòng dữ liệu cuối. Kiểm tra `endsWith("\n")`.
3. **Thụt lề sai do đặt dấu đóng không tương ứng.** Compiler loại incidental indentation dựa vào cấu trúc block; dùng cùng cách thụt lề và test nội dung thực.
4. **Cố giữ dấu cách cuối dòng bằng gõ khoảng trắng ở editor.** Compiler bỏ trailing whitespace mặc định; dùng escape có kiểm thử khi dấu cách thật sự cần thiết.
5. **Quên escape backslash trong JSON hoặc regex.** Text block không phải raw literal; `\\` vẫn là cách biểu diễn một dấu backslash trong giá trị.
6. **Vô tình chuyển CRLF thành LF trong giao thức.** Source text block chuẩn hóa LF; phải kiểm thử khi chuyển từ chuỗi cũ có `\r\n`.
7. **Dùng `==` để so sánh nội dung.** `==` so sánh tham chiếu; dùng `String.equals`, `assertEquals` hoặc so bytes.
8. **Kiểm thử chỉ `contains` một đoạn nhỏ.** Test có thể bỏ qua dòng trống, thụt lề hoặc ký tự cuối; cần ít nhất một assertion toàn bộ chuỗi.
9. **Chuyển luôn dữ liệu runtime sang hard-coded text block.** Khi dữ liệu đến từ file/API/database, cần giữ luồng lấy dữ liệu lúc chạy.
10. **Lạm dụng `stripIndent()` hoặc `.trim()` trong assertion.** Những phương thức này sửa dữ liệu; kiểm thử phải thể hiện chính sách normalization, không che mất lỗi.
11. **Tin rằng text block tự chống SQL injection/HTML injection.** Nó chỉ là cú pháp chuỗi; an toàn đầu ra phụ thuộc API binding/escaping của consumer.
12. **Dùng hướng dẫn cũ về preview flags.** Text block đã là tính năng chuẩn từ Java 15, trên Java 17+ không cần `--enable-preview` để biên dịch bài này.

## 9. Checklist hoàn thành thực hành

- [ ] Đã ghi rõ expected content, bao gồm dòng rỗng, dấu cách và LF cuối.
- [ ] Text block mở/đóng hợp lệ; code được lưu ở file có encoding UTF-8.
- [ ] Chuyển đổi SQL/JSON giữ nguyên dữ liệu và các escape cần thiết.
- [ ] Có test phát hiện được sai lệch `\n`, `\r\n`, backslash và trailing spaces.
- [ ] Có test thụt lề tương đối và một trường hợp không có LF cuối.
- [ ] Test không dùng `trim` hoặc chuẩn hóa sai mục đích để bỏ qua khác biệt.
- [ ] Đã chạy lệnh `javac`/`java` với JDK 17+ và biết output thành công.
- [ ] Nếu dùng JUnit, test task đã bật JUnit Platform và dependency phù hợp.
- [ ] Đã kiểm tra parser hoặc API tiêu thụ dữ liệu nếu có yêu cầu tích hợp.
- [ ] Sau chuyển đổi, mã gốc dư thừa được bỏ khỏi ứng dụng; các fixture/assertion làm chuẩn vẫn được lưu trong test.

## 10. Tài liệu chính thức để đối chiếu

- [OpenJDK JEP 378 — Text Blocks (chính thức từ Java 15)](https://openjdk.org/jeps/378).
- [Oracle Java SE 25 — Text Blocks: cú pháp, incidental whitespace, escape, line ending](https://docs.oracle.com/en/java/javase/25/language/text-blocks.html).
- [Oracle — Programmer's Guide to Text Blocks: thực hành và lưu ý định dạng](https://docs.oracle.com/en/java/javase/25/text-blocks/index.html).
- [Java Language Specification 25, mục Text Block literals](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.6).
- [Java SE 25 API: `String` (`formatted`, `stripIndent`, `translateEscapes`)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html).

**Điều quan trọng nhất khi hoàn thành bài:** text block làm dữ liệu nhiều dòng trong Java dễ đọc hơn, nhưng việc chuyển đổi chỉ an toàn khi **nội dung thực tế được kiểm thử**. Hãy coi newline, whitespace, dấu ngoặc kép và backslash là dữ liệu cần bảo toàn, rồi xác minh bằng các assertion chạy được.
