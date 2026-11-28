# Hybrid snippet: quy tắc đối chiếu nội dung inline với nội dung external sau xử lý markup

## Mục tiêu bài học

Từ Java 18, Javadoc hỗ trợ `{@snippet}` để trình bày ví dụ mã trong tài liệu API. Có ba cách dùng: **inline** (mã nằm trong documentation comment), **external** (mã lấy từ tệp riêng) và **hybrid** (kết hợp cả hai trong một tag).

Hybrid snippet phù hợp khi tác giả muốn người đọc thấy ví dụ ngay cạnh phần giải thích API, đồng thời duy trì một tệp Java riêng để biên dịch và kiểm thử. Standard Doclet giữ hai bản nhất quán bằng quy tắc: **kết quả xử lý hybrid như inline snippet phải khớp kết quả xử lý nó như external snippet**. Nếu không khớp, Javadoc báo lỗi.

Điều kiện được áp dụng cho **kết quả sau xử lý markup**, không đơn thuần là hai chuỗi source ban đầu. Ví dụ, external file có thể dùng literal số hợp lệ cùng `@replace`; inline body lại viết trực tiếp dấu ba chấm `...`. Sau xử lý, hai nguồn vẫn có thể tạo cùng kết quả hiển thị.

Bài này thuộc chương **Markup và region** của module `JAVA_VERSION_JAVA18`. Module khám phá các thay đổi Java 18 vẫn hữu ích trên JDK hiện đại, gồm UTF-8 mặc định, Simple Web Server và snippet trong Javadoc; bài này chỉ sử dụng cơ chế hybrid vẫn được hỗ trợ hiện nay, theo yêu cầu loại bỏ kiến thức lỗi thời hoặc legacy.

Sau bài học, bạn sẽ:

- Viết được `{@snippet file="..." region="..." : ...}` với cả inline body và tệp external.
- Phân biệt source ban đầu với nội dung sau xử lý markup.
- Giải thích được vì sao hai source khác nhau vẫn có thể khớp sau `@replace`.
- Nhận diện trường hợp mismatch do một dòng mã, region, markup hoặc khoảng trắng.
- Hiểu vai trò của `String.stripIndent` với inline body.
- Kết hợp `@highlight`, `@link` và `@replace` theo cách giữ hai nhánh nhất quán.
- Dùng `javac` và `javadoc` để kiểm tra hai mục tiêu riêng biệt.

## 1. Inline, external và hybrid

### 1.1. Inline snippet

Mã nằm ngay trong documentation comment:

~~~java
/**
 * Chuẩn hóa chuỗi:
 * {@snippet :
 *     String text = " Java ".strip();
 *     System.out.println(text);
 *     }
 */
public class InlineExample {
}
~~~

Dấu hai chấm sau `{@snippet` mở inline body. Javadoc đọc nội dung đến dấu ngoặc nhọn đóng tag, chuẩn hóa thụt lề và xử lý markup. Ví dụ dễ đọc tại chỗ, nhưng `javac` không biên dịch các dòng trong documentation comment như một chương trình độc lập.

### 1.2. External snippet

Javadoc trích từ file riêng:

~~~java
/**
 * Chuẩn hóa chuỗi:
 * {@snippet file="TextExample.java" region="usage"}
 */
public class ExternalExample {
}
~~~

Tệp `TextExample.java` có thể là một Java compilation unit hoàn chỉnh. Region `usage` được đánh dấu bằng `@start` và `@end`. Nếu tệp hợp lệ, tác giả có thể dùng compiler hoặc test runner để kiểm tra ví dụ.

### 1.3. Hybrid snippet

~~~java
/**
 * Chuẩn hóa chuỗi:
 * {@snippet file="TextExample.java" region="usage" :
 *     String text = " Java ".strip();
 *     System.out.println(text);
 *     }
 */
public class HybridExampleDoc {
}
~~~

Đây là **một** tag `{@snippet}` có cả `file` và body theo sau dấu hai chấm. Standard Doclet xử lý hai nhánh riêng, rồi so kết quả.

| Đặc điểm | Inline | External | Hybrid |
| --- | --- | --- | --- |
| Có mã trong comment | Có | Không cần | Có |
| Có tệp nguồn riêng | Không | Có | Có |
| Có thể biên dịch external source | Không có file | Có, nếu nguồn hợp lệ | Có, nếu nguồn hợp lệ |
| Đối chiếu hai nhánh | Không | Không | Có |
| Công bảo trì | Một bản | Một bản | Hai biểu diễn cần đồng bộ |
| Phù hợp | Ví dụ ngắn | Ví dụ dài hoặc cần kiểm thử | Ví dụ ổn định cần cả hai lợi ích |

Hybrid **không chạy mã ví dụ**. Standard Doclet kiểm tra hợp đồng trình bày; việc chạy, biên dịch và xác minh hành vi của chương trình vẫn cần công cụ phù hợp.

## 2. Quy trình xử lý hybrid

Cú pháp cơ bản:

~~~java
{@snippet file="Example.java" region="example" :
    // nội dung inline sau khi trình bày
    }
~~~

Với nguồn class Java, cũng có thể tham chiếu bằng thuộc tính `class` khi tên class được phân giải:

~~~java
{@snippet class=ExternalExamples region=join :
    // nội dung inline
    }
~~~

Quy trình khái niệm:

~~~mermaid
flowchart TD
    A["Hybrid snippet"] --> B["Đọc và xử lý inline body"]
    A --> C["Tìm external file hoặc class và chọn region"]
    B --> D["Chuẩn hóa lề, áp dụng markup"]
    C --> E["Áp dụng markup trên phần external đã chọn"]
    D --> F{"Hai kết quả khớp?"}
    E --> F
    F -->|Có| G["Sinh snippet trong HTML"]
    F -->|Không| H["Báo lỗi Javadoc"]
~~~

Standard Doclet có thể xử lý `@highlight`, `@link`, `@replace` và marker region ở mỗi nhánh. Markup comment hợp lệ không xuất hiện như văn bản code, nhưng có thể thay văn bản hoặc ảnh hưởng đến kiểu trình bày và liên kết.

**Không nhầm phép đối chiếu này với so sánh ý nghĩa Java.** Hai lời gọi `strip()` và `trim()` không phải cùng văn bản dù trên một số đầu vào cho kết quả giống nhau. Hai file biên dịch thành công cũng chưa bảo đảm hybrid được Javadoc chấp nhận.

## 3. Ví dụ đầy đủ: external hợp lệ, inline hiển thị dấu ba chấm

Tổ chức file:

~~~text
src/
└── demo/
    ├── HybridApiDoc.java
    └── snippet-files/
        └── HybridUsage.java
~~~

### 3.1. Tệp external `HybridUsage.java`

~~~java
package demo;

public final class HybridUsage {
    private HybridUsage() {
    }

    public static void main(String[] args) {
        // @start region="usage"
        String raw = "  Java  ";
        String text = raw.strip();
        int limit = 3; // @replace substring="3" replacement="..."
        System.out.println(text);
        // @end region="usage"
    }
}
~~~

Source là Java hợp lệ: `int limit = 3;` là khai báo biến với literal số nguyên. Compiler xem các marker và `@replace` là comment.

Khi Javadoc lấy region `usage`, nó loại marker và áp dụng replacement lên dòng khai báo. Dòng được hiển thị trở thành:

~~~java
int limit = ...;
~~~

### 3.2. Tệp `HybridApiDoc.java`

~~~java
package demo;

/**
 * Ví dụ chuẩn hóa chuỗi:
 *
 * {@snippet file="HybridUsage.java" region="usage" :
 *     String raw = "  Java  ";
 *     String text = raw.strip();
 *     int limit = ...;
 *     System.out.println(text);
 *     }
 */
public final class HybridApiDoc {
}
~~~

Inline body viết ngay `int limit = ...;`. Nó không cần lặp lại comment `@replace` từ external.

### 3.3. Đối chiếu sau markup

| Giai đoạn | Nhánh inline | Nhánh external |
| --- | --- | --- |
| Source ban đầu | `int limit = ...;` | `int limit = 3;` kèm `@replace` |
| Sau xử lý | `int limit = ...;` | `int limit = ...;` |
| Kết luận | Hai kết quả khớp | Hai kết quả khớp |

Snippet dự kiến:

~~~java
String raw = "  Java  ";
String text = raw.strip();
int limit = ...;
System.out.println(text);
~~~

Đây là trường hợp được Oracle minh họa: **external source có thể giữ code biên dịch được, còn inline source trực tiếp dùng dấu ba chấm dễ đọc hơn**.

## 4. Quy tắc đối chiếu: cùng kết quả, không cần cùng source

| Tình huống | Kỳ vọng | Lý do |
| --- | --- | --- |
| Hai nhánh cho cùng văn bản sau xử lý. | Hợp lệ | Kết quả khớp. |
| External dùng `@replace` biến `3` thành `...`, inline viết `...`. | Hợp lệ | Khác source nhưng cùng kết quả. |
| Inline có `strip()`, external có `trim()` mà không thay thế. | Mismatch | Hai chuỗi kết quả khác nhau. |
| Inline thiếu một dòng so với external region. | Mismatch | Nội dung được trích không đồng nhất. |
| External chứa marker `@start`/`@end` hợp lệ. | Marker không tạo thêm dòng hiển thị | Markup comment được xử lý khi trích vùng. |
| External có comment thường mà inline thiếu. | Có thể mismatch | Comment thường có thể được giữ trong kết quả. |
| Khác biệt khoảng trắng vẫn còn sau xử lý. | Có thể mismatch | Không có đảm bảo bỏ qua mọi whitespace. |
| External không tìm thấy file hoặc region. | Lỗi Javadoc | Không thể tạo kết quả external để đối chiếu. |

Một hybrid snippet có thể có các ký tự source khác nhau nhưng không được tự ý thay đổi phần hiển thị cuối cùng. Không nên suy đoán trình kiểm tra dùng AST Java hay tương đương ngữ nghĩa: đặc tả nêu việc đối chiếu **kết quả xử lý snippet**.

### 4.1. Kết quả phù hợp nhờ replacement

External:

~~~java
int retries = 3; // @replace substring="3" replacement="..."
~~~

Inline:

~~~java
int retries = ...;
~~~

Sau xử lý, cả hai cho `int retries = ...;`. Điều này được chấp nhận nếu phần còn lại của region cũng khớp.

### 4.2. Kết quả khác vì selector sai

External:

~~~java
int retries = 3; // @replace substring="30" replacement="..."
~~~

Inline:

~~~java
int retries = ...;
~~~

Selector `"30"` không tìm thấy `3`. Phần external giữ `int retries = 3;`; nhánh inline vẫn có `int retries = ...;`. Hai kết quả lệch. Cần sửa selector thành `"3"`, hoặc đổi inline theo kết quả thực tế muốn trình bày.

### 4.3. Kết quả khác vì code khác

External:

~~~java
String text = raw.strip();
~~~

Inline:

~~~java
String text = raw.trim();
~~~

Đây là mismatch, ngay cả nếu có đầu vào mà hai method tạo ra cùng chuỗi. Javadoc không kiểm tra hai cách viết có tương đương về hành vi hay không.

## 5. Region và markup comment quyết định nội dung external

Hybrid tag trong mục 3 chọn:

~~~java
{@snippet file="HybridUsage.java" region="usage" :
    // body inline tương ứng
    }
~~~

Trong file external, marker có tên:

~~~java
// @start region="usage"
String raw = "  Java  ";
String text = raw.strip();
int limit = 3; // @replace substring="3" replacement="..."
System.out.println(text);
// @end region="usage"
~~~

Marker `@start` và `@end` xác định **phạm vi được trích**. Chúng không xuất hiện như câu lệnh trong HTML. Bốn dòng ở giữa là phần được đem xử lý và so sánh với inline body.

Nếu thay region của tag từ `usage` thành một tên không tồn tại, nhánh external không tạo được nội dung hợp lệ để so sánh. Nếu kéo điểm `@start` lên một dòng hoặc chuyển `@end` xuống dưới, region mới có thể trích thừa dòng và làm hybrid mismatch.

### 5.1. Region trích nội dung khác region của một action

| Cách viết | Tác dụng |
| --- | --- |
| `@start region="usage"` ... `@end region="usage"` | Đánh dấu đoạn trong external file để trích. |
| `@highlight region="focus"` ... `@end region="focus"` | Mở phạm vi nhiều dòng cho highlight. |
| `@replace region="detail"` ... `@end region="detail"` | Mở phạm vi nhiều dòng cho replacement. |
| `{@snippet file="Example.java" region="usage"}` | Chọn vùng `usage` để hiển thị. |

Một action region không tự động thay thế cho đoạn external được chỉ định bằng marker `@start`. Nếu cần cả hai cơ chế, nên dùng tên rõ ràng và marker kết thúc tương ứng.

### 5.2. Comment thông thường khác markup comment

External:

~~~java
// @start region="usage"
String text = raw.strip(); // chuẩn hóa chuỗi
// @end region="usage"
~~~

Inline:

~~~java
String text = raw.strip();
~~~

Phần `// chuẩn hóa chuỗi` không phải một markup tag được nhận diện; nó có thể được giữ trong mã trình bày. Khi đó hai nhánh có thể không khớp. Nếu chỉ muốn giải thích ý nghĩa dòng mã, đặt giải thích trong documentation comment ngoài snippet hoặc dùng markup comment được hỗ trợ đúng mục đích.

## 6. Thụt lề, dòng trống và `stripIndent`

Phần inline không được lấy nguyên lề tuyệt đối của source. Javadoc chuẩn hóa khoảng trắng thụt lề phụ bằng cách tương tự `String.stripIndent`. Vì thế, lề của phần mở/đóng snippet và các dòng body ảnh hưởng đến kết quả được so sánh.

Ví dụ:

~~~java
/**
 * {@snippet file="SimpleExample.java" region="one" :
 *     System.out.println("Hello");
 *     }
 */
public class IndentExample {
}
~~~

Dấu `}` đóng snippet được đặt cùng mức thụt lề với câu lệnh trong body sau khi loại phần tiền tố trang trí documentation comment. Đây là cách thường dùng để hạn chế lề dư.

Đừng suy rộng rằng Javadoc tự bỏ qua mọi khoảng trắng. Hai câu lệnh:

~~~java
System.out.println("Hello");
~~~

và:

~~~java
System.out.println( "Hello" );
~~~

có thể cùng hành vi nhưng **khác văn bản**. Sau khi xử lý, khoảng trắng còn lại có thể gây mismatch.

Khi đối chiếu không thành công, kiểm tra:

- Dòng trống ngay sau dấu hai chấm hoặc trước dấu `}` đóng tag.
- Dòng trống đầu/cuối vùng external.
- Mức thụt lề và vị trí dấu `}` đóng inline snippet.
- Khoảng trắng quanh toán tử, dấu ngoặc và dấu chấm phẩy.
- Tab, khoảng trắng cuối dòng và khoảng trắng được thêm bởi replacement.
- Những dòng ngoài region bị trích nhầm vì điểm bắt đầu/kết thúc chưa đúng.

Về nguyên tắc, hãy tin vào kết quả Javadoc trên JDK đang dùng. Không tự loại bớt ký tự mà đặc tả chưa hứa sẽ bỏ qua.

## 7. `@highlight` và `@link` trong hybrid snippet

`@replace` thay đổi văn bản hiển thị, nhưng `@highlight` và `@link` cũng là markup hỗ trợ cho cả inline và external snippets. Hai tag này làm thay đổi phần trình bày như kiểu nhấn mạnh hoặc liên kết API. Khi cần hiệu ứng tương đương trên hai nhánh, nên cấu hình markup nhất quán.

### 7.1. Highlight cùng đoạn ở hai nhánh

File external:

~~~java
// @start region="focus"
String normalized = raw.strip(); // @highlight substring="strip()" type=bold
// @end region="focus"
~~~

Inline trong hybrid tag:

~~~java
{@snippet file="HighlightExample.java" region="focus" :
    String normalized = raw.strip(); // @highlight substring="strip()" type=bold
    }
~~~

Cả hai nhánh yêu cầu nhấn đậm `strip()`. Markup comment không hiện trong khối code, nhưng kết quả trình bày có hiệu ứng highlight. Nếu một bên chọn `strip()` còn bên kia chọn `raw`, không nên giả định chúng vẫn có cùng kết quả.

### 7.2. Link cùng API ở hai nhánh

File external:

~~~java
// @start region="link"
String normalized = raw.strip(); // @link substring="strip()" target="java.lang.String#strip()"
// @end region="link"
~~~

Inline:

~~~java
{@snippet file="LinkExample.java" region="link" :
    String normalized = raw.strip(); // @link substring="strip()" target="java.lang.String#strip()"
    }
~~~

Hai nhánh dùng cùng selector và target. Đường dẫn target `java.lang.String#strip()` phải được Javadoc phân giải thành declaration API hợp lệ.

Đặc tả nói về sự khớp của **kết quả xử lý**, không đơn giản là chuỗi ký tự trước markup. Vì thế, khi dùng các action ảnh hưởng đến highlight hoặc hyperlink, nên đặt chúng giống nhau ở cả hai nhánh và xác minh đầu ra trên JDK đang sử dụng.

### 7.3. Cách dùng an toàn khi kết hợp nhiều markup

- Dùng `@replace` nếu muốn external source biên dịch được và inline chứa ký hiệu rút gọn.
- Với `@highlight` và `@link`, áp dụng cùng selector, target và phạm vi ở hai nhánh nếu cùng muốn hiệu ứng định dạng.
- Khi markup comment đứng riêng và kết thúc bằng dấu hai chấm `:`, tag áp dụng cho dòng **ngay sau comment**. Đảm bảo dòng mục tiêu tương ứng ở hai nhánh.
- Với action region nhiều dòng, kết thúc bằng đúng `@end region="name"` để tránh ảnh hưởng ngoài phạm vi.
- Kiểm tra kết quả Javadoc; đừng giả định source code biên dịch đúng đồng nghĩa với markup đúng.

## 8. Quy trình xây dựng hybrid snippet ít lỗi

Oracle khuyến nghị phát triển ví dụ dưới dạng inline **hoặc** external trước, rồi chuyển thành hybrid khi mã đã tương đối ổn định. Hybrid có hai biểu diễn cần bảo trì, nên đưa vào quá sớm thường gây thêm việc đồng bộ.

Quy trình thực tế:

1. **Viết external source hoàn chỉnh.** Tạo file Java với literal đúng kiểu, class và method hợp lệ.
2. **Đánh dấu đoạn cần hiển thị.** Đặt `@start region="usage"` và `@end region="usage"`.
3. **Biên dịch/kiểm thử nguồn.** Đảm bảo ví dụ hoạt động trên JDK hiện đang sử dụng.
4. **Thêm markup trình bày.** Dùng `@replace` cho placeholder; thêm `@highlight`, `@link` khi cần.
5. **Sinh tài liệu bằng external snippet trước.** Xem HTML để biết chính xác kết quả đã xử lý.
6. **Chép kết quả được trình bày vào inline body.** Giữ đầy đủ các dòng, chú ý lề và khoảng trắng.
7. **Thêm phần inline vào tag external.** Sử dụng dấu hai chấm sau các thuộc tính và body nội dung.
8. **Chạy Javadoc.** Đảm bảo hybrid không có lỗi mismatch.
9. **Duy trì hai bản đồng bộ.** Khi source hoặc markup đổi, cập nhật inline và sinh lại tài liệu.
10. **Đưa Javadoc vào CI khi phù hợp.** Điều này giúp phát hiện lỗi đồng bộ trong các lần sửa về sau.

Khi code thay đổi liên tục, một external snippet có thể dễ bảo trì hơn. Hybrid phù hợp nhất với ví dụ đã ổn định và có lợi ích rõ ràng từ việc người đọc thấy mã ngay trong documentation comment.

## 9. Kiểm chứng bằng `javac` và `javadoc`

Dùng hai file của mục 3:

~~~text
src/
└── demo/
    ├── HybridApiDoc.java
    └── snippet-files/
        └── HybridUsage.java
~~~

### 9.1. Biên dịch external source

Từ thư mục gốc:

~~~bash
javac -d out src/demo/snippet-files/HybridUsage.java
~~~

Lệnh này kiểm tra Java compilation unit thật. Marker `@start`, `@end` và `@replace` là comment, nên không làm thay đổi cú pháp Java.

### 9.2. Sinh tài liệu và kiểm tra hybrid

~~~bash
javadoc -d docs -sourcepath src demo
~~~

Mở `docs/demo/HybridApiDoc.html` và xác nhận:

- Chỉ bốn dòng từ region `usage` được hiển thị.
- Dòng `int limit = ...;` xuất hiện như phiên bản rút gọn.
- Marker `@start`, `@end` và comment `@replace` không xuất hiện trong khối mã.
- Không có lỗi mismatch giữa inline body và external region trong kết quả chạy Javadoc.

Nếu tệp nằm ngoài `snippet-files`, khai báo thư mục tìm kiếm bằng `--snippet-path`:

~~~bash
javadoc -d docs -sourcepath src --snippet-path snippets demo
~~~

Thuộc tính `file` dùng đường dẫn tương đối theo các thư mục snippet được tìm kiếm.

### 9.3. Thử tình huống mismatch có chủ đích

Trong inline body của `HybridApiDoc.java`, chỉ thay:

~~~java
int limit = ...;
~~~

thành:

~~~java
int limit = 999;
~~~

Giữ nguyên external file. Nhánh external sau `@replace` vẫn cho `int limit = ...;`, còn nhánh inline cho `int limit = 999;`. Chạy lại `javadoc` sẽ tạo lỗi vì hai kết quả khác nhau.

Thông điệp lỗi và phần hiển thị dòng chênh lệch có thể thay đổi theo JDK. Hãy đọc chẩn đoán thực tế của công cụ, không phụ thuộc vào một chuỗi lỗi cố định. Sau thí nghiệm, trả inline về `int limit = ...;`.

### 9.4. Ba loại kiểm chứng khác nhau

| Công cụ | Mục đích |
| --- | --- |
| `javac` | Kiểm tra cú pháp và kiểu của external Java source. |
| Unit test hoặc chạy chương trình | Xác minh hành vi thực thi phù hợp yêu cầu. |
| `javadoc` | Kiểm tra hợp đồng hiển thị và sự khớp của hai nhánh hybrid. |

Standard Doclet **không biên dịch hoặc chạy snippet**. Hybrid chỉ giúp bắt lỗi hai bản tài liệu không nhất quán.

## 10. Giới hạn inline body vẫn áp dụng trong hybrid

Mặc dù hybrid có tệp ngoài, phần inline vẫn nằm trong Java documentation comment. Các giới hạn của inline snippet không biến mất:

| Giới hạn | Ảnh hưởng |
| --- | --- |
| Chuỗi `*/` | Không thể nhúng trực tiếp trong comment `/** ... */` vì nó kết thúc documentation comment. |
| Dấu ngoặc nhọn `{` và `}` | Cần cân bằng để Javadoc xác định dấu kết thúc `{@snippet}`. |
| Unicode escape | Java xử lý escape khi phân tích source; ký tự biểu diễn bằng escape không luôn phân biệt được với ký tự tương ứng. |
| `String.stripIndent` | Inline body được chuẩn hóa lề phụ; đối chiếu theo kết quả cuối. |
| Ví dụ dài và hay đổi | Phải sửa hai biểu diễn, dễ gây mismatch nếu thiếu đồng bộ. |

Khi ví dụ chứa cấu trúc khó nhúng an toàn trong documentation comment, chẳng hạn comment block phức tạp hoặc chuỗi có thể làm đóng comment, external snippet là lựa chọn hợp lý hơn. Đừng ép mọi ví dụ thành hybrid nếu không có nhu cầu đọc inline tại chỗ.

## 11. Các lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Hybrid mismatch dù source external biên dịch. | `javac` không kiểm tra nội dung inline. | Chạy `javadoc` và so kết quả hai nhánh. |
| External hiện `3` nhưng inline hiện `...`. | `@replace` thiếu hoặc selector sai. | Kiểm tra `substring`/`regex` và `replacement`. |
| Hybrid trích thừa dòng. | Marker region mở hoặc đóng sai vị trí. | So `@start`/`@end` với nội dung inline. |
| Javadoc không tìm thấy file hoặc region. | Sai `file`, `region` hoặc `--snippet-path`. | Kiểm tra tên, vị trí file và thư mục tìm kiếm. |
| Hai đoạn trông giống nhau nhưng mismatch. | Khác whitespace, dòng trống hoặc thụt lề. | Đọc chẩn đoán Javadoc; kiểm tra từng ký tự còn lại sau xử lý. |
| Một bên có comment thường, bên kia không. | Comment thường có thể xuất hiện trong kết quả. | Sửa source/inline cho nhất quán hoặc đưa giải thích ra ngoài snippet. |
| Chỉ một bên có highlight/link. | Kết quả trình bày có thể không nhất quán. | Cấu hình cùng selector, type và target ở hai nhánh. |
| Inline tag bị kết thúc sai. | Dấu ngoặc nhọn không cân bằng hoặc nội dung đóng comment. | Kiểm tra cú pháp và giới hạn của inline snippet. |
| `@replace` được dùng để che secret. | File external vẫn chứa secret gốc. | Không đặt dữ liệu nhạy cảm trong source mẫu. |
| Sau khi sửa source, HTML vẫn là bản cũ. | Chưa sinh lại tài liệu. | Chạy lại `javadoc` và kiểm tra file đầu ra mới. |

Nếu Javadoc báo lỗi do sự chênh lệch, hãy xác định trước **bản nào phản ánh ý định hiện tại**. Sửa external source nếu API đã đổi; sau đó cập nhật markup và inline body. Tránh sửa inline chỉ để ép hết lỗi khi ví dụ bên ngoài thực sự đã sai.

## 12. Bài tập tự đánh giá

### Bài 1 — So sánh sau xử lý

External:

~~~java
int retries = 3; // @replace substring="3" replacement="..."
~~~

Inline:

~~~java
int retries = ...;
~~~

Hai kết quả có thể khớp không?

**Đáp án:** Có. External thay literal `3` bằng `...`. Hai nhánh chỉ hợp lệ nếu toàn bộ các dòng khác trong region cũng khớp.

### Bài 2 — So sánh theo ý nghĩa Java?

External:

~~~java
String value = text.strip();
~~~

Inline:

~~~java
String value = text.trim();
~~~

Giả sử hai lệnh trả về cùng kết quả cho một đầu vào. Hybrid có chắc hợp lệ không?

**Đáp án:** Không. Javadoc đối chiếu kết quả snippet sau xử lý, không so tương đương hành vi runtime; hai dòng ở đây khác văn bản.

### Bài 3 — Sửa selector

External:

~~~java
int limit = 3; // @replace substring="30" replacement="..."
~~~

Inline:

~~~java
int limit = ...;
~~~

**Đáp án:** Selector `"30"` không khớp `3`. Sửa thành `substring="3"`, rồi chạy Javadoc để xác nhận.

### Bài 4 — Đúng region nào?

File external có hai vùng `setup` và `run`. Tag hybrid:

~~~java
{@snippet file="Examples.java" region="run" :
    // nội dung inline tương ứng với run
    }
~~~

Javadoc cần so inline với cả file hay chỉ vùng `run`?

**Đáp án:** Với kết quả sau xử lý của vùng `run`. Inline phải có đúng toàn bộ nội dung mà vùng đó tạo ra, không chỉ một dòng bất kỳ trong file.

### Bài 5 — Compiler và Javadoc

Tệp external biên dịch thành công, nhưng hybrid báo mismatch. Hai kết quả có mâu thuẫn không?

**Đáp án:** Không. Compiler kiểm tra source Java; Javadoc kiểm tra sự khớp giữa hai nguồn trình bày.

### Bài 6 — Thụt lề

Inline và external có cùng câu lệnh nhưng khác khoảng trắng giữa các token sau xử lý. Có thể khẳng định Standard Doclet chấp nhận không?

**Đáp án:** Không. `stripIndent` chỉ chuẩn hóa lề phụ của inline body. Javadoc không cam kết bỏ qua toàn bộ khoảng trắng bên trong code.

### Bài 7 — Thời điểm áp dụng hybrid

Một ví dụ Java dài đang thay đổi liên tục. Nên chuyển ngay sang hybrid hay ổn định external source trước?

**Đáp án:** Nên phát triển và kiểm thử external trước; khi mã ổn định và có nhu cầu xem inline, chuyển sang hybrid rồi dùng Javadoc kiểm tra đồng bộ.

## Tổng kết

- Hybrid snippet chứa cả **inline body** và **tham chiếu external** trong cùng tag `{@snippet}`.
- Standard Doclet đối chiếu **kết quả sau xử lý snippet và markup**; không khớp là lỗi.
- Hai source ban đầu có thể khác nhau: external `@replace` biến literal Java hợp lệ thành dấu `...` để khớp phần inline.
- `@start`/`@end` xác định region external được trích; marker hợp lệ không hiển thị như mã nguồn.
- `@highlight` và `@link` ảnh hưởng cách trình bày; cần giữ hai nhánh nhất quán và kiểm tra bằng Javadoc.
- Lưu ý `stripIndent`, dòng trống, khoảng trắng, comment thường, selector và tên region.
- `javac` kiểm tra source Java; bộ test kiểm tra hành vi; `javadoc` kiểm tra hợp đồng tài liệu hybrid.
- Hybrid phù hợp với ví dụ đã tương đối ổn định để tránh chi phí duy trì hai bản tăng cao.

## Nguồn tham khảo chính thức

1. [Oracle — JavaDoc Guide: Snippets, JDK 26, mục Hybrid Snippets](https://docs.oracle.com/en/java/javase/26/javadoc/snippets.html): hướng dẫn đối chiếu hai nhánh sau markup, ví dụ dùng `@replace` và khuyến nghị chuyển sang hybrid khi code ổn định.
2. [Oracle — JavaDoc Documentation Comment Specification, JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/javadoc/doc-comment-spec.html): cú pháp inline, external, hybrid, marker region và quy tắc mismatch.
3. [Oracle — JavaDoc Guide: Testing Snippets, JDK 26](https://docs.oracle.com/en/java/javase/26/javadoc/snippets.html): Standard Doclet không biên dịch hoặc kiểm thử snippet, và cách dùng công cụ khác để kiểm tra.
4. [Oracle — String.stripIndent(), Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html#stripIndent()): quy tắc loại bỏ lề phụ trong văn bản.
5. [OpenJDK — JEP 413: Code Snippets in Java API Documentation](https://openjdk.org/jeps/413): cơ sở tính năng snippet từ Java 18 và khả năng tiếp tục dùng trên JDK hiện đại.
