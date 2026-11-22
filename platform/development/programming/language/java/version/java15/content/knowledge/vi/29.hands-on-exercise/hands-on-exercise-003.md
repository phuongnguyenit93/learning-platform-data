# Xử lý văn bản ngoài bằng `stripIndent()` và `translateEscapes()` trong Java

Hai phương thức `String.stripIndent()` và `String.translateEscapes()` được bổ sung chính thức từ **Java 15** và vẫn có trong API `java.lang.String` của Java hiện đại. Chúng rất hữu ích khi đọc **văn bản ngoài chương trình** — chẳng hạn file UTF-8, một template hoặc nội dung cấu hình được định nghĩa theo quy ước Java-style escapes — rồi cần (1) bỏ phần thụt lề chung của nhiều dòng và (2) biến chuỗi ký tự như dấu gạch chéo ngược + `n` thành ký tự xuống dòng thật.

Đây là các phương thức trên **chuỗi đã nằm trong bộ nhớ**, không trực tiếp đọc file, không phải parser JSON/YAML/XML, cũng không phải công cụ làm sạch dữ liệu bảo mật. Chỉ áp dụng bước nào thực sự nằm trong hợp đồng của định dạng đầu vào. Bài dùng **Java 17+**, mặc dù hai API đã ổn định từ Java 15, nhằm thực hành trên JDK còn được sử dụng rộng rãi.

## 1. Vì sao văn bản ngoài cần xử lý khác string literal?

Giả sử file bên ngoài chứa những ký tự nhìn thấy được dưới đây (các dấu `\n`, `\t` trong nội dung là **hai ký tự**: `` và chữ theo sau):

~~~text
    name: Lan\nAn
      note: Tab\tOK
    end: done
~~~

Vì file được đọc từ đĩa, Java **không tự** chuyển `\n` thành newline hay `\t` thành tab. Khi gọi `Files.readString(path, UTF_8)`, ta nhận chuỗi giữ nguyên các ký tự ấy. Tùy định dạng mong muốn, có thể cần:

1. `stripIndent()` để loại bốn khoảng trắng chung ở đầu mỗi dòng và giữ lại hai khoảng trắng thụt lề tương đối của `note`.
2. `translateEscapes()` để đổi `\n` và `\t` được ghi dưới dạng ký tự trong file thành newline/tab thực tế.

Hai thao tác **khác nhiệm vụ**. `stripIndent` không diễn giải gạch chéo ngược; `translateEscapes` không tự tính phần indent chung. Khi kết hợp theo cách gần với cơ chế xử lý Java text blocks, thứ tự thường là **`stripIndent().translateEscapes()`**; cần kiểm tra xem điều này có phù hợp với định dạng file cụ thể hay không.

## 2. `stripIndent()` hoạt động như thế nào?

Chữ ký API:

~~~java
String result = input.stripIndent();
~~~

`stripIndent()` bỏ **incidental indentation** (thụt lề phụ để trình bày), dựa trên những quy tắc chính sau:

- Phân chia input thành các dòng theo `\n`, `\r` hoặc `\r\n`. Kết quả dùng **LF (`\n`)** làm ký tự phân cách, cho dù file gốc dùng CRLF của Windows.
- Đếm số ký tự whitespace đầu mỗi dòng **không trống** (`!line.isBlank()`). **Dòng cuối cũng tham gia tính độ thụt lề tối thiểu kể cả khi chỉ chứa whitespace hoặc rỗng.**
- Lấy độ thụt lề **nhỏ nhất** trong các dòng được xét, loại đúng số ký tự whitespace đó khỏi đầu mỗi dòng không trống.
- Bỏ whitespace **cuối mỗi dòng không trống**; các dòng chỉ có whitespace trở thành dòng rỗng, tức giữa hai newline không còn space/tab.
- Giữ tương quan thụt lề giữa các dòng: nếu một dòng thụt sâu hơn dòng ít thụt nhất hai ký tự, kết quả vẫn sâu hơn hai ký tự.
- Giữ **số lượng line terminator**, kể cả trường hợp input kết thúc bằng một line terminator.

Ví dụ không có newline cuối:

~~~java
String text = "    <root>  \r\n"
            + "      <item>42</item> \r\n"
            + "    </root>  ";

String result = text.stripIndent();

System.out.println(result.equals(
        "<root>\n  <item>42</item>\n</root>")); // true
~~~

Đây là đoạn mã đặt **bên trong một phương thức**. Các dấu cách dư ở cuối dòng bị xóa; `\r\n` đổi thành `\n`; phần thụt lề tương đối của `<item>` vẫn còn hai dấu cách.

### Bẫy thực tế: file có newline ở cuối có thể không bị kéo trái

Điều kiện về **dòng cuối** rất quan trọng. Xem hai chuỗi:

~~~java
String noFinalLf = "    A\n      B";
String withFinalLf = "    A\n      B\n";

System.out.println(
        noFinalLf.stripIndent().equals("A\n  B"));          // true
System.out.println(
        withFinalLf.stripIndent().equals("    A\n      B\n")); // true
~~~

Vì `withFinalLf` kết thúc bằng newline, dòng cuối theo thuật toán `stripIndent()` là một **dòng rỗng có độ thụt lề 0**. Giá trị `min` vì thế bằng 0, nên phần indent đầu các dòng có nội dung **không giảm**. Đây là hành vi theo đặc tả, không phải lỗi của API.

Nếu nguồn được tạo theo quy ước Java text block và cần bỏ indent, có thể dùng **dòng kết thúc có indent** khi kiểm soát được cách tạo đầu vào:

~~~java
String withIndentedLastLine = "    A\n      B\n    ";

System.out.println(
        withIndentedLastLine.stripIndent().equals("A\n  B\n")); // true
~~~

Tuy nhiên **không được tự ý xóa newline cuối của một file** chỉ để ép thuật toán rút indent nếu ứng dụng cần giữ byte/line structure nguyên bản. Hãy thiết kế quy ước đầu vào hoặc một thuật toán deindent riêng có kiểm thử, đặc biệt với dữ liệu CSV, chữ ký số, YAML, thơ, source code hoặc các định dạng mà khoảng trắng mang ý nghĩa.

### Tab và Unicode whitespace

`stripIndent` đếm **mỗi ký tự whitespace ở đầu dòng là một đơn vị**; tab `\t` cũng chỉ tính là một ký tự, **không được mở rộng thành bốn hay tám cột**. Khi nguồn trộn space và tab, mắt nhìn có thể thấy kết quả lệch dù thuật toán đúng. Khái niệm whitespace dựa trên `Character.isWhitespace`, không đồng nghĩa với mọi ký tự Unicode có bề ngoài giống dấu cách. Nếu phải giữ vị trí cột chính xác, hãy quy định kiểu indent nhất quán ngay từ nguồn.

So sánh nhanh:

| Phương thức | Phạm vi tác động | Dùng khi nào? |
| --- | --- | --- |
| `stripIndent()` (Java 15+) | Tự tính indent tối thiểu trên **nhiều dòng**, bỏ trailing whitespace từng dòng, chuẩn hóa newline | Muốn đưa một block nhiều dòng về lề trái nhưng giữ indent tương đối |
| `strip()` (Java 11+) | Bỏ whitespace ở **hai đầu toàn chuỗi** | Muốn bỏ khoảng trống bao ngoài; không chỉnh indent từng dòng |
| `trim()` | Bỏ các ký tự mã ≤ U+0020 ở hai đầu toàn chuỗi | Chỉ khi thật sự cần ngữ nghĩa cũ của `trim` |
| `indent(n)` (Java 12+) | Thêm `n` dấu cách hoặc bớt tối đa `-n` whitespace mỗi dòng; chuẩn hóa newline | Đã biết mức thay đổi indent cụ thể, không muốn tự dò min |

Không thay `stripIndent` bằng `replace("    ", "")`: việc thay toàn bộ bốn dấu cách sẽ phá cả khoảng trắng **bên trong** một dòng, còn `stripIndent` chỉ tác động vào thụt lề đầu và whitespace cuối dòng.

## 3. `translateEscapes()` giải mã những chuỗi nào?

Chữ ký API:

~~~java
String decoded = input.translateEscapes();
~~~

Phương thức diễn giải **Java-style escape sequences** trong nội dung *đang có ở runtime*. Những nhóm được hỗ trợ gồm:

| Ký tự thô trong input | Kết quả của `translateEscapes()` |
| --- | --- |
| `\n` | LF, ký tự xuống dòng U+000A |
| `\r` | CR, ký tự U+000D |
| `\t` | Tab ngang U+0009 |
| `\b`, `\f` | Backspace U+0008, form feed U+000C |
| `\s` | Một dấu cách U+0020 |
| `\"`, `\'`, `\` | Dấu nháy kép, nháy đơn, một dấu `` |
| `\0` đến các dạng escape **bát phân** hợp lệ đến `\377` | Ký tự có giá trị tương ứng trong bảng mã |
| Một dấu `` theo ngay sau bởi **line terminator thực sự** | Nối tiếp dòng: bỏ dấu `` và line terminator đó |

Điểm rất dễ nhầm:

- `translateEscapes()` **không** hỗ trợ diễn giải escape Unicode kiểu Java source `\uXXXX`. Tại bước biên dịch **mã nguồn**, Java có cơ chế xử lý Unicode escapes riêng và sớm hơn; file văn bản ngoài **không** đi qua cơ chế ấy. Khi runtime gặp `\u0041` dưới dạng chuỗi escape, đây là escape không được hỗ trợ và có thể bị từ chối bằng `IllegalArgumentException`; **không** được dự đoán đầu ra là chữ `A`.
- `\x41` hoặc `\q` không phải Java-style escape hợp lệ với phương thức này; ký tự `` ở cuối không có ký tự theo sau cũng sai.
- Phương thức trả về chuỗi mới hoặc kết quả tương đương, **không sửa** String gốc (String là immutable).
- Đừng tự động giải mã dữ liệu hai lần. `translateEscapes` không phải một thao tác an toàn để áp dụng lặp lại: kết quả lượt đầu có thể còn chuỗi backslash mang nghĩa khác cho lượt tiếp theo.

Ví dụ (đặt trong `main`):

~~~java
String encoded = "line 1\\nline 2\\tOK\\s!";
String decoded = encoded.translateEscapes();

System.out.println(decoded.equals("line 1\nline 2\tOK !")); // true
System.out.println(decoded.lines().count());              // 2
~~~

Trong **mã Java**, `"\\n"` biểu diễn hai ký tự `` + `n` ở runtime, còn `"\n"` biểu diễn **một ký tự LF**. Trong file UTF-8 bên ngoài, không có bước Java compiler “tự mở escape” như trong source code: `Files.readString` trả về đúng dữ liệu được đọc.

### Escape bị lỗi phải được xử lý có chủ đích

~~~java
String bad = "\\" + "q";             // input chứa dấu \ rồi chữ q
String unicodeLike = "\\" + "u0041"; // input chứa \u0041
String trailingSlash = "abc" + "\\"; // input kết thúc bằng \

try {
    bad.translateEscapes();
    throw new AssertionError("Expected IllegalArgumentException");
} catch (IllegalArgumentException expected) {
    System.out.println("Invalid escape rejected");
}
~~~

Đây là **mã minh họa đặt trong phương thức**, không phải file chạy độc lập. Hai chuỗi `unicodeLike` và `trailingSlash` cũng không giải mã được bằng API này. Việc nối chuỗi trong code tránh nhầm **escape ở mã nguồn Java** với **escape trong dữ liệu runtime**. Trong ứng dụng thực, nên báo vị trí/dòng lỗi, không bắt `IllegalArgumentException` rồi âm thầm trả về chuỗi đã giải mã dở.

`translateEscapes` cũng không tự diễn giải quy tắc escape của JSON như `\/` và `\uXXXX`. Nếu file là JSON, dùng **JSON parser**; nếu là XML/HTML/YAML/CSV, dùng parser/reader tương ứng. Không dùng `translateEscapes` để thay thế validation hoặc escaping khi dữ liệu được đưa vào SQL, HTML, shell, template hay đường dẫn.

## 4. Thứ tự xử lý ảnh hưởng kết quả

Giả sử input từ file là:

~~~text
    item: one\nsecond
      status: yes
    done
~~~

Nếu gọi `stripIndent()` **trước**, tất cả các dòng vật lý ban đầu còn có ít nhất bốn dấu cách ở đầu, nên loại được indent chung. Sau đó `translateEscapes()` mới biến `\n` bên trong `one\nsecond` thành một dòng mới thực sự.

Nếu đảo ngược thành `translateEscapes().stripIndent()`, việc giải mã sẽ tạo thêm dòng `second` có **độ thụt lề 0** trước khi tính indent tối thiểu; do đó `stripIndent` có thể không loại bốn khoảng trắng ở các dòng cũ. Với những format yêu cầu dữ liệu được deindent rồi decode, thứ tự phù hợp là:

~~~java
String normalized = externalText.stripIndent();
String decoded = normalized.translateEscapes();
~~~

Đây cũng là hướng thứ tự xử lý **nội dung text block trong Java source**: chuẩn hóa line terminators, xử lý incidental indentation, rồi diễn giải escape. Lưu ý: text block được **compiler** xử lý sẵn; không cần mặc định gọi lại các phương thức trên chỉ vì biến String ban đầu được khai báo bằng `"""`.

Trên dữ liệu ngoài không hoàn toàn đáng tin, **bước giải mã có thể tạo thêm newline, tab, CR hay backspace**, làm thay đổi số dòng/định dạng downstream. Chỉ giải mã khi định dạng input đã quy định escape sequences; nếu đó là văn bản người dùng muốn giữ nguyên, chỉ đọc và xử lý phần indent cần thiết.

## 5. Chương trình đầy đủ: đọc file UTF-8 hoặc chạy dữ liệu mẫu

Tạo file **`ExternalTextDemo.java`** với nội dung dưới đây. Không cần Maven, Gradle hoặc thư viện ngoài; dùng JDK 17+ với `java.nio.file.Files`.

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ExternalTextDemo {
    public static void main(String[] args) throws IOException {
        if (args.length > 1) {
            throw new IllegalArgumentException(
                    "Usage: java ExternalTextDemo [path-to-utf8-file]");
        }

        // Không truyền argument: dùng dữ liệu mẫu mô phỏng văn bản bên ngoài.
        // \\n và \\t trong Java source tạo hai ký tự thô \ + n, \ + t.
        String raw = args.length == 1
                ? Files.readString(Path.of(args[0]), StandardCharsets.UTF_8)
                : "    name: Lan\\nAn  \r\n"
                + "      note: Tab\\tOK  \r\n"
                + "    end: done  ";

        String aligned = raw.stripIndent();
        String decoded;
        try {
            decoded = aligned.translateEscapes();
        } catch (IllegalArgumentException invalidEscape) {
            throw new IllegalArgumentException(
                    "Input contains an invalid Java-style escape", invalidEscape);
        }

        System.out.println("stripIndent=" + visible(aligned));
        System.out.println("translateEscapes=" + visible(decoded));

        if (args.length == 0) {
            String expected = "name: Lan\nAn\n  note: Tab\tOK\nend: done";
            System.out.println("decodedMatches=" + decoded.equals(expected));
            System.out.println("lastLineRule="
                    + "    A\n    B\n".stripIndent()
                        .equals("    A\n    B\n"));
        }
    }

    private static String visible(String text) {
        return text.replace("\n", "|").replace("\t", "<TAB>");
    }
}
~~~

Các lệnh chạy tại thư mục có file `ExternalTextDemo.java`:

~~~bash
javac --release 17 ExternalTextDemo.java
java ExternalTextDemo
~~~

Khi chạy **không truyền đường dẫn**, đầu ra chính xác là:

~~~text
stripIndent=name: Lan\nAn|  note: Tab\tOK|end: done
translateEscapes=name: Lan|An|  note: Tab<TAB>OK|end: done
decodedMatches=true
lastLineRule=true
~~~

Ý nghĩa:

- Đầu ra `stripIndent=...` vẫn có các ký tự `\n` và `\t` được ghi từ dữ liệu, vì lúc này chưa giải mã.
- Trong `translateEscapes=...`, `|` đại diện cho **LF thật** và `<TAB>` đại diện cho **tab thật**; hàm `visible` chỉ giúp nhìn thấy chúng trên một dòng console.
- Biểu thức `decodedMatches` so sánh chuỗi sau cả hai bước với giá trị mong đợi, trả về `true`.
- Biểu thức `lastLineRule` xác nhận quy tắc dòng cuối rỗng: input có newline cuối không nhất thiết bị loại phần indent chung.

Để dùng văn bản thực tế do người dùng/ứng dụng tạo, cung cấp đường dẫn đến một file UTF-8 có cấu trúc và escape theo đúng quy ước trên:

~~~bash
java ExternalTextDemo input.txt
~~~

Lần này chương trình lấy byte từ **file ngoài** bằng `Files.readString`, tự xử lý và chỉ in hai dòng trực quan. Kết quả phụ thuộc nội dung file; không có stdout cố định cho trường hợp này. Nếu file không tồn tại hoặc không đọc được, `IOException` sẽ được truyền ra. Nếu file chứa escape sai, `IllegalArgumentException` có nguyên nhân lồng bên trong; hệ thống thật nên đổi thành thông báo người dùng hiểu được, có thông tin dòng/cột nếu có parser riêng.

Trên Windows, các lệnh cũng chạy được trong PowerShell hoặc Command Prompt nếu `java` và `javac` thuộc JDK thích hợp có trong `PATH`. Lệnh `javac --release 17` yêu cầu compiler hỗ trợ release 17. Hãy kiểm tra `java --version` và `javac --version` để biết môi trường đang dùng.

## 6. Kiểm thử riêng từng hợp đồng, bao gồm phản ví dụ

Khi ứng dụng cần tự động kiểm thử, viết các test riêng cho việc bỏ indent và giải mã escape. Ví dụ sau là **một class JUnit Jupiter** tại `src/test/java/ExternalTextTest.java` trong dự án đã cấu hình JUnit; đây không phải file chạy độc lập bằng `java ExternalTextTest`.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class ExternalTextTest {
    @Test
    void stripsCommonIndentAndNormalizesCrlf() {
        String external = "    first  \r\n"
                        + "      second \r\n"
                        + "    third  ";
        assertEquals("first\n  second\nthird", external.stripIndent());
    }

    @Test
    void lastEmptyLineMayPreventOutdenting() {
        String external = "    A\n      B\n";
        assertEquals("    A\n      B\n", external.stripIndent());
    }

    @Test
    void decodesJavaStyleEscapesAtRuntime() {
        String external = "A\\nB\\tC\\sD";
        assertEquals("A\nB\tC D", external.translateEscapes());
    }

    @Test
    void rejectsUnsupportedEscapes() {
        assertThrows(IllegalArgumentException.class,
                () -> ("\\" + "q").translateEscapes());
        assertThrows(IllegalArgumentException.class,
                () -> ("\\" + "u0041").translateEscapes());
        assertThrows(IllegalArgumentException.class,
                () -> ("text" + "\\").translateEscapes());
    }

    @Test
    void orderingMatters() {
        String external = "    first\\nsecond\n    third";
        assertEquals("first\nsecond\nthird",
                external.stripIndent().translateEscapes());
        assertEquals("    first\nsecond\n    third",
                external.translateEscapes().stripIndent());
    }
}
~~~

Mỗi phép kiểm tra nhắm vào một hợp đồng có ý nghĩa: CRLF, khoảng trắng cuối dòng, dòng cuối rỗng, escape đúng, escape sai và thứ tự xử lý. Không nên chỉ assert “không ném exception” vì một pipeline có thể chạy thành công nhưng đã thay đổi lề hoặc line endings không như dự định.

Nếu bài kiểm thử dùng fixture **file thật**, tạo file UTF-8 bằng test temporary directory và kiểm tra đồng thời kết quả `Files.readString`; tránh phụ thuộc xuống dòng mặc định của máy chạy CI. Với Maven/Gradle, bảo đảm JDK thực thi test có cả hai API (`String.stripIndent` và `String.translateEscapes` xuất hiện từ Java 15).

## 7. Lỗi phổ biến và cách chẩn đoán

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `stripIndent()` không xóa bốn dấu cách chung | File kết thúc bằng newline, dòng cuối rỗng làm mức `min = 0` | Kiểm tra ký tự kết thúc; thiết kế lại định dạng/thuật toán bỏ indent phù hợp |
| Các dòng còn trông lệch sau khi strip | Trộn tab và space; tab tính một ký tự, không bằng số cột hiển thị | Chuẩn hóa quy ước indent tại nguồn |
| Không còn dấu cách cuối dòng | `stripIndent()` chủ động xóa trailing whitespace | Đừng dùng khi trailing whitespace có ý nghĩa nghiệp vụ |
| `\n` vẫn hiển thị thành gạch chéo + chữ n | Chỉ gọi `stripIndent` hoặc input không được giải mã | Chỉ gọi `translateEscapes` nếu format có Java-style escapes |
| Text sau giải mã bị chia dòng ngoài ý muốn | `translateEscapes()` chuyển `\n`, `\r` thành control characters | Xác nhận input contract và kiểm soát xử lý downstream |
| `IllegalArgumentException: Invalid escape...` | Có `\q`, `\uXXXX`, gạch chéo cuối, hoặc escape không hợp lệ | Sửa định dạng nguồn; không bỏ qua lỗi im lặng |
| Đã xử lý nhưng nội dung thay đổi khi chạy lại | Giải mã lặp hai lần có thể có kết quả khác lần đầu | Chỉ thực hiện tại một ranh giới parse xác định |
| Nội dung JSON không giải mã được | JSON hỗ trợ escape khác Java runtime API | Sử dụng JSON parser có kiểm tra schema |
| File đọc sai dấu tiếng Việt | Sai charset giữa file và reader, chẳng hạn dùng charset hệ thống ngầm định | Khai báo rõ `StandardCharsets.UTF_8` và xác minh encoding thực tế của file |
| Kết quả khác khi so sánh byte hoặc chữ ký | `stripIndent` chuẩn hóa CRLF/CR thành LF và xóa whitespace | Giữ dữ liệu nguyên gốc cho kiểm tra byte/chữ ký; chỉ transform trên bản sao phục vụ hiển thị |

Những giới hạn cần giữ trong môi trường sản xuất:

- **Quy ước dữ liệu trước, biến đổi sau.** `stripIndent` phù hợp với đoạn văn nhiều dòng được indent thống nhất; `translateEscapes` chỉ dùng khi phía phát dữ liệu cam kết cú pháp escape kiểu Java. Không tự suy đoán rằng mọi dấu `` là escape.
- **Không dùng làm sanitizer.** Chuyển `\n` thành newline không bảo vệ khỏi injection; ngược lại, nó có thể đưa control characters vào logs, HTML, CSV, terminal hoặc lệnh chạy. Luôn escape/encode đúng **ngữ cảnh đầu ra**.
- **Không giới hạn dữ liệu chỉ theo biểu thức String.** Đầu vào lớn có thể tốn bộ nhớ vì `Files.readString` đọc toàn bộ file và các phép biến đổi có thể cấp phát chuỗi mới. Với file lớn, dùng streaming/line reader và thuật toán riêng; việc tính indent tối thiểu cho toàn bộ file có thể cần hai lượt đọc hoặc vùng đệm.
- **Không bỏ qua phiên bản JDK mục tiêu.** Hai phương thức có `@since 15`; nếu chạy trên Java 11 hoặc 14, việc cố gọi sẽ không hợp lệ. Với môi trường mới, ưu tiên JDK LTS còn được hỗ trợ và chạy test trên runtime thực tế.
- **Giữ dữ liệu gốc khi cần điều tra.** Để phân tích lỗi, log một cách an toàn số dòng, charset, kiểu newline và loại lỗi; tránh in nguyên văn dữ liệu không tin cậy chứa bí mật hoặc control characters.

## 8. Checklist trước khi đưa vào pipeline

- [ ] File/nguồn bên ngoài có **charset xác định** (ví dụ UTF-8), đường dẫn và giới hạn dung lượng phù hợp.
- [ ] Biết chắc mục tiêu là bỏ thụt lề chung, không phải xóa mọi space/tab.
- [ ] Đã kiểm tra **dòng cuối có newline hay không**, các dòng trắng, các ký tự CRLF và việc trộn tab/space.
- [ ] Chỉ gọi `translateEscapes()` nếu dữ liệu thực sự dùng cú pháp escape kiểu Java và có quy tắc xử lý lỗi.
- [ ] Không nhầm escape Unicode của Java source với việc giải mã dữ liệu runtime; không dùng API này thay JSON parser.
- [ ] Chọn thứ tự biến đổi có test xác nhận, thông thường **`stripIndent()` rồi `translateEscapes()`** đối với format có indent của block và Java-style escapes.
- [ ] Có test cho cả input đúng lẫn input sai; assert **nội dung, whitespace và line endings**, không chỉ test việc chạy thành công.
- [ ] Chạy trên **JDK 15+** (và JDK được sản phẩm hỗ trợ hiện nay), xác nhận kết quả với file thực tế.
- [ ] Chỉ dùng văn bản đã transform ở những nơi phù hợp; xử lý escape/validation tại vị trí xuất dữ liệu nếu có ngữ cảnh bảo mật.

Điều cốt lõi: `stripIndent()` giải quyết **bố cục nhiều dòng**, còn `translateEscapes()` giải quyết **cú pháp escape của Java ở runtime**. Khi đọc văn bản ngoài, hai phương thức có thể phối hợp rất hiệu quả, nhưng newline cuối file, thứ tự xử lý và cú pháp escape cần được quy định và kiểm thử rõ ràng.

## Tài liệu chính thức

- [Java SE 25 – `String.stripIndent()` và `String.translateEscapes()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html#stripIndent())
- [Java SE 25 – `String.translateEscapes()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html#translateEscapes())
- [Oracle – Programmer's Guide to Text Blocks: thuật toán xử lý indent và escape](https://docs.oracle.com/en/java/javase/15/text-blocks/index.html)
- [Java SE 25 – `Files.readString(Path, Charset)`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html#readString(java.nio.file.Path,java.nio.charset.Charset))
- [Java SE 25 – `String.lines()`, `isBlank()`, `indent(int)`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html)
- [OpenJDK JEP 378 – Text Blocks (finalized Java 15)](https://openjdk.org/jeps/378)
