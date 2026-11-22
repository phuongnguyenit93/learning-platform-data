# Dữ liệu kiểm thử dễ đọc bằng text block trong Java

## 1. Vì sao text block hữu ích cho dữ liệu kiểm thử?

Trong kiểm thử Java, dữ liệu đầu vào hoặc đầu ra kỳ vọng thường là một đoạn văn bản nhiều dòng: JSON, CSV, SQL, HTML, báo cáo, log, thông điệp lỗi hay payload gửi tới API. Trước đây, việc ghép nhiều literal ngắn bằng dấu `+` và escape `\n` dễ làm người đọc khó nhìn thấy cấu trúc thực của dữ liệu.

**Text block** là literal `String` nhiều dòng, mở và đóng bằng `"""`. Cú pháp đã chính thức có từ **Java 15** và vẫn được hỗ trợ trên Java 17+ và các phiên bản hiện đại. Nội dung kiểm thử có thể viết gần với văn bản mà ứng dụng thật sẽ nhận hoặc tạo:

```java
String csv = """
        id,name
        1,Lan
        2,Minh
        """;
```

Giá trị thực của `csv` là `"id,name\n1,Lan\n2,Minh\n"`. Text block giúp:

- Nhìn thấy cấu trúc dòng, các trường và thứ tự dữ liệu ngay trong mã kiểm thử.
- So sánh dễ dàng giữa **đầu vào** và **kết quả mong đợi** mà không phải ghép chuỗi dài.
- Tránh phần lớn escape cho dấu nháy kép trong JSON hoặc HTML.
- Đưa nội dung fixture sát đoạn `assertEquals`, nên người review thấy rõ yêu cầu của ca kiểm thử.
- Giảm sự phụ thuộc vào cách xuống dòng CRLF hay LF của file nguồn.

Text block chỉ tạo ra **chuỗi ký tự**: nó không tự phân tích JSON, không kiểm tra SQL hợp lệ và không tự biến một đoạn văn bản thành fixture đúng nghiệp vụ. Vẫn phải chọn dữ liệu đủ đại diện và viết assertion phù hợp.

## 2. Ba dạng fixture nên cân nhắc dùng text block

### 2.1. Payload JSON nhiều dòng

```java
String requestBody = """
        {
          "user": "Lan",
          "enabled": true,
          "roles": ["author", "reviewer"]
        }
        """;
```

Với JSON, dấu `"` trong nội dung thường không cần escape như literal chuỗi Java thông thường. Điều này làm fixture gần với payload gửi trong HTTP request hoặc đọc từ file.

Dù vậy, **văn bản trông giống JSON không bảo đảm JSON hợp lệ**. Nếu mục tiêu kiểm thử là nội dung JSON, nên dùng JSON parser/serializer hiện có trong dự án để kiểm tra cú pháp và cấu trúc. Nếu mục tiêu là xác nhận chính xác chuỗi JSON được xuất ra, so sánh toàn bộ `String` có thể phù hợp, kể cả whitespace và thứ tự trường khi hợp đồng yêu cầu.

### 2.2. CSV, log và kết quả xử lý văn bản

```java
String csv = """
        product,quantity
        pen,3
        book,5
        """;

String expectedReport = """
        total=8
        rows=2
        """;
```

Đây là cặp dữ liệu đầu vào và đầu ra dễ review. Mỗi hàng và dấu phân tách `,` đều có thể kiểm tra bằng mắt. Khi chạy test, vẫn cần kiểm tra output thực tế có đúng newline cuối, số dòng và khoảng trắng đã định nghĩa hay không.

### 2.3. Câu SQL, HTML, XML hoặc mẫu thông báo

```java
String sql = """
        SELECT id, title
        FROM articles
        WHERE status = ?
        ORDER BY id
        """;

String html = """
        <section class="result">
          <h2>Success</h2>
          <p>Saved</p>
        </section>
        """;
```

Text block hợp với các ví dụ này vì giữ nguyên bố cục dễ đọc của câu truy vấn và thẻ lồng nhau. Trong code truy cập cơ sở dữ liệu, vẫn cần **bind tham số** (ví dụ `PreparedStatement`) thay vì chèn trực tiếp đầu vào không tin cậy vào SQL. Text block không thay thế các quy tắc xử lý dữ liệu an toàn.

## 3. Hiểu đúng giá trị `String` trước khi viết assertion

Text block giúp mã nguồn dễ đọc, nhưng kết quả không nhất thiết giống toàn bộ khoảng trắng nhìn thấy trong file Java. Trình biên dịch xử lý nội dung theo các quy tắc ngôn ngữ:

1. Dấu kết thúc dòng CR, LF và CRLF trong **mã nguồn của text block** đều được chuẩn hóa thành LF (`\n`).
2. Phần thụt lề chung được coi là **incidental indentation** và loại bỏ.
3. Escape sequence như `\n`, `\r`, `\t`, `\s` được xử lý sau đó.

Ví dụ:

```java
String expected = """
        START
          ITEM
        END
        """;
```

Giá trị tương đương:

```java
String expected = "START\n  ITEM\nEND\n";
```

Khoảng thụt lề dùng để đặt text block vào trong class/phương thức không biến thành khoảng trắng đầu mọi dòng. Riêng dòng `ITEM` vẫn có **hai dấu cách có chủ ý** sau khi bỏ lề chung.

### 3.1. Newline cuối phụ thuộc vị trí dấu đóng

```java
String withFinalLf = """
        done
        """;
// Giá trị: "done\n"

String withoutFinalLf = """
        done""";
// Giá trị: "done"
```

Dấu `"""` đóng ở dòng mới giữ lại LF sau `done`. Nếu đặt ngay sau `done`, không có LF cuối. Đây là khác biệt quan trọng khi test file, giao thức truyền thông hoặc báo cáo theo byte.

### 3.2. Dòng nguồn CRLF không tạo CRLF trong text block

Dù file `.java` được lưu với CRLF (thường gặp trên Windows), newline thực trong text block vẫn được chuẩn hóa thành LF. Nếu hợp đồng đầu ra yêu cầu chính xác CRLF, hãy tạo giá trị đó có chủ ý:

```java
String expectedLf = """
        A
        B
        """;

String expectedCrlf = expectedLf.replace("\n", "\r\n");
```

Cách `replace` trên thích hợp vì `expectedLf` chỉ có LF. Với dữ liệu runtime có thể **đã chứa CRLF**, cần chuẩn hóa CRLF/CR về LF trước khi chuyển sang CRLF để tránh tạo `\r\r\n`.

### 3.3. Khi khoảng trắng cuối dòng là dữ liệu cần kiểm thử

Java thường loại bỏ khoảng trắng cuối dòng không chủ ý trong text block. Nếu test thực sự cần dấu cách cuối dòng, có thể viết escape `\s` (một dấu cách) để giữ nó:

```java
String padded = """
        name:\s\s
        """;
// Giá trị: "name:  \n" (hai dấu cách trước LF)
```

Tránh dựa vào việc nhấn nhiều dấu cách ở cuối dòng nguồn: editor có thể tự xóa chúng. Chỉ đưa những khoảng trắng này vào fixture khi hợp đồng đòi hỏi; nếu không, hãy giữ test đơn giản.

## 4. Ví dụ hoàn chỉnh chạy được trên Java 17+

Tạo file `ReadableFixtureDemo.java`. Ví dụ dùng text block cho dữ liệu CSV và output kỳ vọng của hàm tổng hợp số lượng.

```java
import java.util.List;

public class ReadableFixtureDemo {
    public static void main(String[] args) {
        String csv = """
                item,quantity
                apple,3
                banana,5
                """;

        String expected = """
                total=8
                rows=2
                """;

        String actual = summarize(csv);

        if (!expected.equals(actual)) {
            throw new AssertionError("Expected: " + visible(expected)
                    + ", actual: " + visible(actual));
        }

        System.out.println("PASS");
        System.out.println("inputLines=" + csv.lines().count());
        System.out.println("endsWithLF=" + expected.endsWith("\n"));
        System.out.println("exactLength=" + expected.length());
    }

    static String summarize(String csv) {
        List<String> lines = csv.lines().toList();
        int total = 0;

        for (String line : lines.subList(1, lines.size())) {
            String[] fields = line.split(",", -1);
            if (fields.length != 2) {
                throw new IllegalArgumentException("Invalid row: " + line);
            }
            total += Integer.parseInt(fields[1]);
        }

        return "total=" + total + "\nrows=" + (lines.size() - 1) + "\n";
    }

    static String visible(String text) {
        return text.replace("\r", "\\r")
                .replace("\n", "\\n")
                .replace("\t", "\\t");
    }
}
```

Chạy bằng JDK 17 hoặc mới hơn:

```bash
javac ReadableFixtureDemo.java
java ReadableFixtureDemo
```

Output chính xác:

```text
PASS
inputLines=3
endsWithLF=true
exactLength=15
```

**Giải thích chi tiết:**

- `csv` gồm 3 dòng có nội dung: header `item,quantity` và hai bản ghi.
- `csv.lines()` trả về các dòng **không gồm ký tự kết thúc dòng**, vì vậy `count()` là 3; newline cuối không làm tăng thành 4 dòng.
- `summarize(csv)` cộng `3 + 5 = 8`, đếm 2 bản ghi và trả về đúng `"total=8\nrows=2\n"`.
- `expected.equals(actual)` kiểm tra toàn bộ chuỗi, gồm chữ, dấu `=`, thứ tự dòng, dấu cách và LF cuối. Sai ở một ký tự cũng làm test thất bại.
- `expected.endsWith("\n")` là `true`; `expected.length()` bằng 15 đơn vị UTF-16 (`"total=8"` dài 7, LF 1, `"rows=2"` dài 6, LF 1).
- Hàm `visible` hỗ trợ chẩn đoán bằng cách thay CR/LF/tab thực thành chuỗi ký tự nhìn thấy `\\r`, `\\n`, `\\t`. Nó chỉ phục vụ hiển thị khi lỗi, **không thay đổi** dữ liệu gốc để so sánh.

Ví dụ là một chương trình Java độc lập, không cần thư viện kiểm thử ngoài JDK. Tại đây, `summarize` minh họa phần code cần kiểm thử; trong dự án thực tế, thay bằng hàm của hệ thống.

## 5. Đưa text block vào JUnit Jupiter

Nếu dự án đang sử dụng JUnit Jupiter, có thể dùng cùng mẫu text block với assertion chuẩn:

```java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class CsvReportTest {
    @Test
    void summarizesCsvIntoReadableReport() {
        String csv = """
                item,quantity
                apple,3
                banana,5
                """;

        String expected = """
                total=8
                rows=2
                """;

        String actual = ReadableFixtureDemo.summarize(csv);

        assertEquals(expected, actual);
    }
}
```

**Đoạn JUnit này cần dependency JUnit Jupiter và class `ReadableFixtureDemo` từ ví dụ trước**, đặt cùng package (hoặc chỉnh quyền truy cập và package phù hợp). Đây là ví dụ tích hợp vào test suite, không phải chương trình độc lập chạy bằng `java CsvReportTest`.

Ưu điểm của `assertEquals(expected, actual)` là các thư viện và IDE kiểm thử thường hiển thị sự khác biệt giữa expected/actual; text block làm phía expected dễ đọc ngay trong source. Khi kiểm thử API trả JSON và chỉ yêu cầu **tương đương cấu trúc**, việc parse JSON rồi so sánh cây dữ liệu có thể phù hợp hơn so sánh nguyên văn vì khoảng trắng/thứ tự trường có thể không phải một phần của hợp đồng.

## 6. Chọn cách kiểm thử dựa trên hợp đồng dữ liệu

| Điều cần xác minh | Cách phù hợp | Vì sao |
| --- | --- | --- |
| File CSV, báo cáo, template cần chính xác từng ký tự | So sánh `String` với text block bằng `assertEquals` | Bắt được LF, dấu cách và thứ tự dòng |
| JSON/XML mà hợp đồng chỉ yêu cầu cấu trúc | Dùng parser phù hợp rồi so sánh cấu trúc | Tránh lỗi giả vì format hoặc indentation |
| HTTP request body cần xác minh định dạng chính xác | Text block expected và so sánh nội dung thực | Dễ review payload và phát hiện ký tự thừa |
| Từng dòng log hoặc message | Text block expected, cân nhắc so sánh các dòng nếu **cố ý** bỏ qua line ending | Không gộp các trường hợp test khác nhau |
| Test chỉ yêu cầu chuỗi kết thúc bằng LF | `assertTrue(actual.endsWith("\n"))` cùng assertion nghiệp vụ | Nêu rõ điều kiện thay vì so sánh lan man |
| Fixture lớn, dùng chung nhiều test | File UTF-8 trong `src/test/resources` | Dễ quản lý tài nguyên riêng và tránh class test quá dài |

Điều quan trọng là **không normalize dữ liệu để test luôn PASS**. Chẳng hạn, dùng `expected.strip().equals(actual.strip())` có thể vô tình bỏ qua newline cuối hoặc khoảng trắng bị mất; nếu chúng là một phần của yêu cầu, so sánh đó sẽ che giấu lỗi.

Khi hợp đồng cho phép CRLF và LF tương đương, hãy chuẩn hóa **có chủ đích**, ví dụ:

```java
static String normalizeNewlines(String text) {
    return text.replace("\r\n", "\n")
               .replace("\r", "\n");
}
```

Sau đó so sánh kết quả chuẩn hóa và ghi rõ lý do trong tên hoặc mô tả test. Không sử dụng hàm này khi test đang kiểm tra chính xác loại line ending.

## 7. Template có chỗ thay thế dữ liệu: dùng đúng mục đích

Text block là `String`, nên vẫn có thể dùng `String.formatted(...)` (được thêm từ Java 15) hoặc `String.format(...)`:

```java
String template = """
        Hello, %s!
        You have %d new messages.
        """;

String expected = template.formatted("Lan", 2);
```

Giá trị `expected` là `"Hello, Lan!\nYou have 2 new messages.\n"`. Nếu bản thân nội dung tĩnh cần có dấu phần trăm khi được dùng làm format string, viết `%%`.

Tuy nhiên, **formatting không tự escape cho JSON, XML, SQL hay HTML**. Ví dụ tên người dùng chứa dấu nháy kép có thể phá vỡ cú pháp JSON nếu chỉ chèn bằng `%s`; giá trị không tin cậy có thể tạo lỗ hổng nếu ghép vào câu SQL. Khi cần tạo JSON có dữ liệu động, dùng serializer hiện có trong dự án; với SQL, dùng parameter binding.

Trong test, ưu tiên fixture với giá trị cố định nếu như thế đủ mô tả trường hợp; nếu cần nhiều trường hợp thay đổi giá trị, dùng parameterized tests hoặc factory/helper có tên rõ ràng, tránh tạo một mẫu format quá phức tạp.

## 8. Khi nào nên lưu fixture ra file?

Text block phù hợp khi dữ liệu **nhỏ hoặc vừa, thuộc một test cụ thể, cần nhìn trực tiếp cạnh assertion**. Chẳng hạn 5–30 dòng CSV/JSON ngắn thường đọc dễ hơn khi đặt trong code.

Ngược lại, cân nhắc file dưới `src/test/resources` nếu có một hoặc nhiều tình huống:

- JSON/HTML/XML dài hàng trăm dòng khiến logic test bị che khuất.
- Nhiều test dùng cùng nội dung và việc sao chép sẽ gây sai lệch.
- Cần kiểm thử **byte chính xác** như BOM, CRLF gốc hoặc encoding của file.
- Đầu vào là mẫu sản xuất dài hoặc binary không phù hợp đưa vào source.
- Fixture thay đổi độc lập với code hoặc cần mở bằng công cụ chuyên dụng.

Text block vẫn có thể dùng cho các giá trị expected ngắn ngay cả khi input nằm trong file. Đặt tên rõ nghĩa như `inputCsv`, `expectedReport`, `expectedJson`; tránh các biến `a`, `b` hoặc `text1` khi người đọc cần phân biệt vai trò.

## 9. Những lỗi thường gặp với fixture text block

1. **Nhầm thụt lề của source với dữ liệu thật.** Java loại phần incidental indentation; muốn giữ số khoảng trắng chính xác, hãy kiểm tra `equals` và vị trí dấu đóng.
2. **Quên LF cuối.** Dấu đóng ở dòng riêng sau nội dung tạo LF cuối; dấu đóng ngay sau ký tự cuối thường không tạo LF cuối.
3. **Cho rằng source CRLF tạo String CRLF.** Trong text block, newline nguồn được chuẩn hóa thành LF; test giao thức CRLF cần ghi rõ CRLF mong đợi.
4. **Tự động `strip()` hai phía của assertion.** Việc bỏ whitespace có thể khiến test không phát hiện lỗi format mà người dùng thật thấy được.
5. **So sánh JSON nguyên văn dù chỉ quan tâm semantics.** Formatter, serializer và indentation có thể thay đổi mà dữ liệu JSON vẫn tương đương; khi đó nên parse và so sánh cấu trúc.
6. **Dùng `System.out.println(actual)` để kiểm tra có bao nhiêu newline.** `println` tự thêm newline; nên dùng `equals`, `endsWith`, `length` hoặc hàm `visible`.
7. **Chèn dữ liệu động không escape vào JSON/SQL.** Text block không thay thế serializer hay prepared statement.
8. **Lạm dụng fixture lớn trong test source.** Khi dữ liệu làm test khó đọc hơn, tách ra file resource có tên rõ ràng.

## 10. Checklist khi review test có text block

- Fixture đại diện cho tình huống thật và dữ liệu kỳ vọng có ý nghĩa?
- Text block có đúng dấu đóng, thụt lề, LF cuối và các khoảng trắng quan trọng?
- Assertion đang kiểm tra **chính xác văn bản** hay **tương đương cấu trúc** theo hợp đồng?
- Test có độc lập với locale, line ending của hệ điều hành và thứ tự không được bảo đảm?
- Nếu fixture có dữ liệu động, việc chèn giá trị có an toàn và hợp lệ với định dạng đích?
- Người mới đọc test có thể hiểu input và expected ngay mà không mở quá nhiều file?
- Output sai có tạo ra thông điệp kiểm thử hữu ích, dễ xác định phần khác biệt?

**Ghi nhớ:** Text block làm dữ liệu kiểm thử nhiều dòng gần với hình thức thật, giúp con người đọc và review dễ hơn. Sự chính xác vẫn đến từ hiểu quy tắc newline/indentation, từ phép so sánh phù hợp với hợp đồng và từ việc kiểm tra đúng hành vi của code dưới test.

## Tài liệu tham khảo hiện hành

- [Java Language Specification — Text Blocks, §3.10.6](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.6): quy định nội dung literal, incidental indentation, chuẩn hóa newline và escape.
- [Oracle Java — Programmer's Guide to Text Blocks](https://docs.oracle.com/en/java/javase/25/text-blocks/index.html): ví dụ cú pháp và các cách sử dụng text block.
- [Java String API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html): `lines()`, `formatted()`, `stripIndent()` và các thao tác chuỗi.
- [JUnit User Guide](https://docs.junit.org/current/user-guide/): cách tổ chức test và sử dụng assertion trong JUnit Jupiter.

Bài học sử dụng cú pháp chính thức, API đang được hỗ trợ trong Java hiện đại; các ví dụ chạy độc lập dùng Java 17+.