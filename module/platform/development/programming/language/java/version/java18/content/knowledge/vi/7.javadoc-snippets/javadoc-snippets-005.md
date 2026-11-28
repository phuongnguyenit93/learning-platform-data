# Giới hạn của chuỗi kết thúc comment và Unicode escape trong comment chứa snippet

## 1. Bối cảnh và mục tiêu

JEP 413 đưa thẻ `{@snippet ...}` vào Javadoc từ **JDK 18** để trình bày ví dụ mã trong tài liệu API. Tính năng này tiếp tục được hỗ trợ trên JDK hiện đại. Khi viết snippet trực tiếp trong chú thích tài liệu truyền thống `/** ... */`, phần thân chịu giới hạn từ cú pháp comment của Java và quy tắc dịch mã nguồn.

Bài học tập trung vào hai giới hạn:

- Chuỗi ký tự `*/` kết thúc chú thích truyền thống, kể cả khi nó xuất hiện trong string literal, biểu thức chính quy hoặc comment của mã ví dụ.
- Unicode escape như `\u002a` được dịch trong bước xử lý mã nguồn trước khi Java nhận diện comment. Vì vậy, một chuỗi escape có thể biến thành chính ký tự kết thúc comment trước khi Javadoc đọc nội dung.

Sau bài này, bạn có thể:

- Giải thích vì sao không thể đặt `*/` trực tiếp trong inline snippet của comment `/** ... */`.
- Nhận biết Unicode escape có thể tạo ra ký tự `*` và `/` như thế nào.
- Phân biệt Unicode escape với escape sequence của string literal.
- Chọn external snippet hoặc hình thức documentation comment phù hợp khi cần trình bày ký tự đặc biệt.
- Kiểm tra tài liệu bằng Javadoc và kiểm chứng riêng mã nguồn ví dụ.

Phạm vi chính là **traditional documentation comment**. Một số JDK hiện đại còn hỗ trợ escape sequence riêng trong phần văn bản tài liệu; chúng có phạm vi áp dụng cụ thể và không xóa bỏ giới hạn của nội dung literal trong inline snippet.

## 2. Vì sao `*/` kết thúc comment trước khi Javadoc xử lý snippet?

Chú thích tài liệu truyền thống bắt đầu bằng `/**` và kết thúc bằng `*/`. Đây là quy tắc cú pháp comment của Java. Javadoc chỉ có thể phân tích nội dung tài liệu sau khi mã nguồn đã được xử lý thành comment.

Ví dụ hợp lệ:

~~~java
/**
 * Tài liệu cho API.
 *
 * {@snippet :
 * String message = "ready";
 * System.out.println(message);
 * }
 */
public class StatusPrinter {
}
~~~

Nhưng nếu nội dung cần minh họa chính chuỗi kết thúc comment:

~~~java
/**
 * {@snippet :
 * String terminator = "*/";
 * }
 */
public class CommentExample {
}
~~~

thì chuỗi `*/` trong string literal vẫn kết thúc comment bên ngoài. Trình biên dịch Java và Javadoc không chờ đến khi phân tích cú pháp string literal mới quyết định comment kết thúc ở đâu. Kết quả là phần còn lại của ví dụ không còn thuộc chú thích tài liệu như dự định; source có thể phát sinh lỗi cú pháp.

**Quy tắc cần nhớ:** trong traditional documentation comment, không thể đưa cặp ký tự `*/` vào nội dung inline snippet. Điều này áp dụng cho mọi vị trí:

| Vị trí xuất hiện | Ví dụ ý định | Vì sao không hợp lệ trong inline comment |
| --- | --- | --- |
| String literal | `"*/"` | Cặp ký tự vẫn kết thúc comment. |
| Regex hoặc glob | `".*/reports"` | Chuỗi vẫn chứa cặp ký tự kết thúc comment. |
| Line comment trong snippet | `// mẫu */` | Line comment không ngăn comment bên ngoài kết thúc. |
| Block comment trong snippet | `/* ... */` | Dấu đóng block comment cũng đóng luôn comment tài liệu bao ngoài. |
| Nội dung được ghép | Ký tự `*` và `/` đứng liền nhau | Parser nhận ra cặp ký tự sau khi source được dịch. |

Giới hạn này xuất phát từ **comment bao ngoài**, không phải riêng bộ xử lý snippet. Đổi `{@snippet ...}` thành `{@code ...}` hay đặt cặp ký tự đó trong inline tag khác cũng không làm traditional comment có thể chứa `*/`.

## 3. Unicode escape được xử lý trước khi nhận diện comment

Unicode escape trong Java có dạng một dấu gạch chéo ngược, chữ `u` và bốn chữ số thập lục phân, ví dụ `\u002a`. Một escape biểu diễn một UTF-16 code unit. Trong quá trình dịch mã nguồn, Java nhận diện và chuyển Unicode escape **trước bước phân loại ký tự thành comment, literal và token**.

Đây là lý do một chuỗi nhìn như văn bản bình thường vẫn có thể tạo ra dấu kết thúc comment.

### 3.1. Từ escape đến dấu kết thúc comment

Hai giá trị Unicode quan trọng:

| Escape | Ký tự sau dịch | Ý nghĩa |
| --- | --- | --- |
| `\u002a` | `*` | Ký tự sao |
| `\u002f` | `/` | Ký tự gạch chéo xuôi |

Nếu source chứa hai escape liền nhau `\u002a\u002f`, sau bước dịch Unicode, cặp ký tự thu được là `*/`.

Ví dụ cố ý sai:

~~~java
/**
 * {@snippet :
 * String terminator = "\u002a\u002f";
 * }
 */
public class UnicodeCommentExample {
}
~~~

Dòng code có vẻ chỉ chứa các chữ số và ký tự `\u`. Nhưng Java dịch source trước khi nhận diện comment. Phần liên quan sau bước dịch tương đương:

~~~java
/**
 * {@snippet :
 * String terminator = "*/";
 * }
 */
~~~

Cặp ký tự mới được tạo ra kết thúc comment tài liệu. Vì thế, snippet bị cắt ngay tại vị trí đó.

### 3.2. Unicode escape không phải escape của string literal

Có hai cơ chế khác nhau:

| Cơ chế | Thời điểm xử lý | Ví dụ |
| --- | --- | --- |
| Unicode escape của Java source | Trước khi nhận diện token, comment và literal | `\u0041` được dịch thành ký tự `A`. |
| Escape sequence của string literal | Khi phân tích nội dung literal theo cú pháp Java | `\n` biểu diễn ký tự xuống dòng trong giá trị chuỗi. |

Vì Unicode escape được dịch trước, đặt `\u002a\u002f` bên trong dấu nháy kép không bảo vệ nó khỏi việc trở thành `*/`. Dấu nháy kép chỉ có ý nghĩa khi Java phân tích string literal, tức là ở giai đoạn sau.

Tương tự, không nên cho rằng dấu gạch chéo ngược thứ hai sẽ luôn vô hiệu hóa Unicode escape. JLS quy định **điều kiện một dấu gạch chéo ngược có đủ điều kiện mở đầu Unicode escape**, dựa trên các dấu gạch chéo ngược đứng liền trước và nguồn gốc ký tự. Quy tắc này tinh tế hơn cơ chế escape của string; thêm một dấu gạch chéo ngược một cách tùy tiện không phải giải pháp tổng quát.

### 3.3. Không thể yêu cầu inline snippet giữ nguyên cách viết `\uNNNN`

Giả sử mục tiêu của tài liệu là cho người học nhìn thấy chính xác chuỗi ký tự `\u0041`, thay vì ký tự `A`. Nếu viết trực tiếp trong source Java, Unicode escape có thể được dịch trước khi Javadoc lấy nội dung comment. Vì vậy, nội dung được xử lý có thể không còn giống chuỗi ký tự mà tác giả gõ.

Điều này không chỉ ảnh hưởng đến `\u002a\u002f`. Bất kỳ Unicode escape hợp lệ nào trong source comment cũng có thể được dịch thành ký tự tương ứng trước khi Javadoc đọc comment.

Khi mục tiêu là **trình bày nguyên văn cách viết Unicode escape**, hãy dùng tệp snippet bên ngoài chứa nội dung văn bản cần hiển thị và kiểm tra kết quả Javadoc. Nếu tệp đó đồng thời là mã Java được biên dịch, nó vẫn chịu quy tắc Unicode escape của JLS; không được nhầm việc tách tệp với việc vô hiệu hóa quy tắc dịch mã nguồn.

## 4. Phạm vi của escape sequence trong Javadoc hiện đại

Một số phiên bản Standard Doclet hiện đại có escape sequence riêng để biểu diễn ký tự đặc biệt trong **phần văn bản thông thường** của traditional documentation comment. Ví dụ, đặc tả JDK 26 hỗ trợ `*@/` để biểu diễn dấu gạch chéo xuôi trong ngữ cảnh cần tránh kết thúc comment; cách viết `*@/` có thể được dùng để biểu diễn `*/` trong văn bản tài liệu.

Ví dụ phần văn bản:

~~~java
/**
 * Trong phần mô tả, chuỗi kết thúc comment được viết bằng dạng *@/.
 */
public class CommentTerminology {
}
~~~

Tuy nhiên, cần phân biệt hai ngữ cảnh:

- **Văn bản tài liệu thông thường:** escape sequence của Standard Doclet có thể được áp dụng theo quy tắc và phiên bản hỗ trợ.
- **Inline tag chứa literal text:** đặc tả hiện hành nêu rõ escape sequence của documentation comment không được dùng bên trong các inline tag như `code`, `literal` và `snippet`.

Do đó, `*@/` không phải cách thay thế để chèn `*/` vào phần thân `{@snippet ...}`. Cần kiểm tra đúng phiên bản JDK mục tiêu khi dùng escape sequence này; đừng giả định mọi JDK đều hỗ trợ giống nhau.

Ngoài ra, escape sequence của Javadoc và Unicode escape của Java source là **hai tầng xử lý khác nhau**. Escape của Javadoc không ngăn Unicode escape được dịch trước đó bởi Java.

## 5. External snippet giải quyết giới hạn của comment bao ngoài

Khi cần trình bày string literal, regex hoặc block comment có chứa `*/`, cách phù hợp là đưa mã ra một tệp riêng rồi tham chiếu bằng external snippet. Nội dung tệp ngoài không bị đặt bên trong comment `/** ... */` chứa thẻ.

Cấu trúc thư mục ví dụ:

~~~text
src/main/java/
└── example/
    ├── PatternExamples.java
    └── snippet-files/
        ├── PatternSnippet.java
        └── UnicodeEscapeText.txt
~~~

Tệp `src/main/java/example/snippet-files/PatternSnippet.java`:

~~~java
package example;

import java.util.regex.Pattern;

public final class PatternSnippet {
    private PatternSnippet() {
    }

    public static void main(String[] args) {
        // @start region=pattern
        /* Đây là block comment trong tệp Java riêng. */
        String regex = "a.*/reports";
        boolean matched = Pattern.compile(regex)
                .matcher("abc/reports")
                .matches();
        if (!matched) {
            throw new AssertionError(regex);
        }
        // @end region=pattern
    }
}
~~~

Tệp `src/main/java/example/snippet-files/UnicodeEscapeText.txt` chứa văn bản cần hiển thị nguyên văn:

~~~text
Unicode escape được viết trong tài liệu: \u002a\u002f
Ký tự tương ứng sau khi dịch là dấu sao theo sau bởi dấu gạch chéo xuôi.
~~~

Trong Javadoc của lớp `PatternExamples`, tham chiếu từng tệp:

~~~java
/**
 * Mẫu biểu thức chính quy có chuỗi kết thúc comment:
 *
 * {@snippet file="PatternSnippet.java" region=pattern}
 *
 * Cách viết Unicode escape ở dạng văn bản:
 *
 * {@snippet file="UnicodeEscapeText.txt"}
 */
public class PatternExamples {
}
~~~

Tệp Java bên ngoài cho phép ví dụ có block comment và chuỗi chứa `*/` vì nó không nằm trong comment bao ngoài. Tệp văn bản riêng thích hợp để trình bày nguyên văn chuỗi Unicode escape mà không biến nó thành mã Java cần biên dịch.

Các tệp external snippet có thể đặt trong thư mục `snippet-files` của package chứa thẻ, hoặc trong đường dẫn bổ sung cấu hình bằng tùy chọn `--snippet-path` của Javadoc. Một tệp có thể chứa nhiều vùng `@start region=...` và `@end region=...` để tái sử dụng ở nhiều vị trí.

**Lưu ý về kiểm thử:** Javadoc trích nội dung và dựng tài liệu; nó không tự xác nhận mã Java trong external snippet chạy đúng. Nếu tệp Java ngoài được dùng như ví dụ thực thi, hãy biên dịch và chạy nó riêng. Nếu tệp văn bản chỉ dùng để hiển thị, không cần đưa nó vào bước biên dịch Java.

## 6. Khi nào dùng traditional comment, Markdown documentation comment và external snippet?

Trên JDK hiện đại, Standard Doclet hỗ trợ cả traditional documentation comment `/** ... */` và Markdown documentation comment dùng các dòng `///`. Hai hình thức có cách bao comment khác nhau.

| Nhu cầu | Lựa chọn phù hợp | Giới hạn cần nhớ |
| --- | --- | --- |
| Tài liệu API thông thường, ví dụ ngắn | Traditional comment và inline snippet | Không thể có `*/` trong nội dung comment; Unicode escape được dịch trước. |
| Ví dụ có block comment hoặc string chứa `*/` | External snippet | Mã được tách khỏi comment bao ngoài; vẫn kiểm tra riêng nếu biên dịch tệp Java. |
| Tài liệu viết bằng Markdown trong source | Markdown documentation comment `///` trên JDK hỗ trợ | Không có dấu đóng comment `*/`; Unicode escape của Java source vẫn được xử lý trước. |
| Hiển thị chính xác văn bản `\uNNNN` | External snippet từ tệp văn bản | Tránh để chuỗi cần hiển thị bị phân tích như Unicode escape của Java source. |

Markdown documentation comment dùng ký hiệu `///` ở đầu từng dòng, nên không dùng cặp `/** ... */` để bao nội dung. Đây là hình thức documentation comment hiện đại, hữu ích khi tài liệu cần có ví dụ chứa block comment hoặc chuỗi `*/`. Tuy nhiên, Unicode escape vẫn thuộc bước dịch source của Java; đổi sang `///` không biến chuỗi escape thành văn bản bất biến.

Ví dụ dạng Markdown documentation comment:

~~~java
/// Ví dụ về một chuỗi có dấu kết thúc comment:
///
///     String marker = "*/";
///
/// Tài liệu được viết bằng Markdown documentation comment.
public class MarkdownCommentExample {
}
~~~

Trong ví dụ này, `*/` xuất hiện trên dòng `///` nên không kết thúc một traditional block comment. Dạng Markdown documentation comment chỉ dùng được trên JDK hỗ trợ cú pháp này; nếu dự án cần tương thích JDK 18, hãy dùng external snippet cho ví dụ chứa ký tự đặc biệt.

## 7. Quy trình kiểm tra trước khi xuất bản

Khi một ví dụ có chuỗi đặc biệt hoặc Unicode escape, nên rà soát theo trình tự:

1. **Xác định kiểu documentation comment:** source đang dùng `/** ... */` hay `///`?
2. **Tìm cặp `*/` trong toàn bộ nội dung:** kiểm tra string literal, regex, line comment, block comment và dữ liệu mẫu; đừng chỉ tìm trong câu lệnh Java.
3. **Tìm Unicode escape:** rà soát các chuỗi dạng `\uNNNN` trong source comment, nhất là escape tạo ra `*`, `/` hoặc line terminator.
4. **Kiểm tra quy tắc eligible backslash của JLS:** không dùng mẹo nhân đôi dấu gạch chéo ngược khi chưa xác nhận kết quả sau bước dịch Unicode.
5. **Chuyển nội dung phù hợp sang external snippet:** dùng tệp Java riêng cho mã có thể chạy, tệp văn bản riêng cho chuỗi cần hiển thị nguyên văn.
6. **Sinh tài liệu:** chạy Javadoc với JDK mục tiêu để phát hiện comment bị kết thúc sớm, thẻ bị lỗi hoặc đường dẫn snippet sai.
7. **Kiểm thử hành vi:** biên dịch và chạy ví dụ Java hoặc đưa ví dụ vào unit test nếu kết quả có ý nghĩa đối với hợp đồng API.
8. **Xem HTML kết quả:** xác nhận chuỗi, dấu gạch chéo, ký tự Unicode và vùng snippet hiển thị đúng như mong đợi.

### Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Javadoc hoặc trình biên dịch báo lỗi ngay sau string literal. | Chuỗi chứa `*/` và đóng comment bao ngoài. | Chuyển ví dụ sang external snippet. |
| Dòng snippet bị cắt khi dùng `\u002a\u002f`. | Unicode escape đã được dịch thành `*/` trước khi nhận diện comment. | Dùng external text snippet để hiển thị nguyên văn escape. |
| Tăng số dấu gạch chéo ngược nhưng kết quả vẫn khác dự định. | Quy tắc eligible backslash của JLS phức tạp hơn escape của string. | Kiểm tra source sau dịch; không dựa vào phỏng đoán. |
| Dùng `*@/` trong snippet nhưng Javadoc không hiển thị như mong muốn. | Escape sequence của documentation comment không áp dụng trong inline tag chứa literal text. | Chỉ dùng escape đó trong văn bản comment được hỗ trợ; dùng external snippet cho mã. |
| External snippet hiển thị đúng nhưng chương trình không biên dịch. | Javadoc chỉ trích nội dung, không chạy ví dụ. | Biên dịch và chạy tệp Java riêng. |
| Đổi sang `///` nhưng chuỗi Unicode escape vẫn thay đổi. | Unicode escape được dịch trước khi Java phân loại comment. | Dùng tệp văn bản external nếu cần giữ nguyên cách viết. |

## 8. Bài tập thực hành

### Bài tập 1: Xác định comment kết thúc ở đâu

Cho đoạn mã:

~~~java
/**
 * {@snippet :
 * String glob = "reports/*.csv";
 * String regex = "a.*/b";
 * }
 */
public class PatternDoc {
}
~~~

Hãy xác định dòng nào chứa `*/` liên tiếp. Giải thích vì sao dấu nháy kép không bảo vệ cặp ký tự đó khỏi việc kết thúc comment. Viết lại bằng external snippet.

### Bài tập 2: Theo dõi Unicode translation

Cho source:

~~~java
/**
 * {@snippet :
 * String end = "\u002a\u002f";
 * }
 */
~~~

Hãy ghi kết quả sau bước dịch Unicode trước khi parser nhận diện comment. Giải thích vì sao Unicode escape không phải string escape và tại sao dấu nháy kép không giúp giữ comment mở.

### Bài tập 3: Chọn cách lưu ví dụ

Bạn cần tài liệu thể hiện cả ba nội dung:

- Một block comment Java `/* ... */`.
- Một regex có chứa `*/`.
- Dòng ký tự `\u002a\u002f` để giải thích Unicode escape.

Hãy quyết định nội dung nào đặt trong `PatternSnippet.java`, nội dung nào đặt trong `UnicodeEscapeText.txt` và viết các thẻ external snippet tham chiếu đến chúng. Sau đó tạo Javadoc, mở HTML và xác nhận cả ba nội dung xuất hiện đúng.

**Tự kiểm:** hiểu ranh giới của traditional comment; phân biệt Unicode translation với string escape; không dùng escape Javadoc bên trong snippet literal; biết khi nào cần external file; đã xem kết quả Javadoc và kiểm tra mã thực thi riêng.

## 9. Ghi nhớ

- **`*/` kết thúc traditional documentation comment**, dù xuất hiện trong string literal, regex hoặc comment bên trong snippet.
- **Unicode escape được dịch trước khi nhận diện comment.** `\u002a\u002f` có thể trở thành `*/` và đóng comment sớm.
- **Unicode escape và escape sequence của string là hai cơ chế khác nhau.** Quy tắc eligible backslash của JLS khiến việc nhân đôi dấu gạch chéo không phải mẹo thay thế tổng quát.
- **Escape sequence của Javadoc có phạm vi riêng.** `*@/` trong văn bản comment hiện đại không phải cách chèn `*/` vào nội dung literal của `{@snippet}`.
- **External snippet tách ví dụ khỏi comment bao ngoài.** Dùng tệp Java cho mã có thể chạy và tệp văn bản cho nội dung cần giữ nguyên cách viết; kiểm thử riêng theo mục đích.

## Tài liệu chính thống

- [OpenJDK – JEP 413: Code Snippets in Java API Documentation](https://openjdk.org/jeps/413).
- [Oracle – JDK 26 Snippets Guide](https://docs.oracle.com/en/java/javase/26/javadoc/snippets.html).
- [Oracle – JDK 26 Documentation Comment Specification, Inline Snippets và Escape Sequences](https://docs.oracle.com/en/java/javase/26/docs/specs/javadoc/doc-comment-spec.html).
- [Oracle – Java Language Specification, JDK 26, mục 3.2–3.3 Lexical Translations và Unicode Escapes](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-3.html).

