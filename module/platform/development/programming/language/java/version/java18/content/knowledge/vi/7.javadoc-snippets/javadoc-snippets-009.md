# Thuộc tính có hoặc không có dấu nháy và giới hạn escape trong giá trị thuộc tính

## 1. Mục tiêu và bối cảnh

JEP 413 bổ sung thẻ `{@snippet ...}` cho Javadoc từ **JDK 18**. Trên JDK hiện đại, snippet tiếp tục là cách chuẩn để trình bày ví dụ mã trong tài liệu API. Một thẻ snippet có thể chứa các thuộc tính như `lang`, `id`, `file`, `class` và `region`. Giá trị thuộc tính có thể viết không có dấu nháy hoặc đặt trong dấu nháy đơn/đôi tùy nội dung.

Bài học tập trung vào **cú pháp giá trị thuộc tính và giới hạn escape**. Sau khi học, bạn có thể:

- Phân biệt giá trị thuộc tính dạng token đơn giản với giá trị chuỗi có dấu nháy.
- Biết khi nào dấu nháy là cần thiết vì giá trị chứa khoảng trắng.
- Chọn dấu nháy đơn hoặc kép phù hợp.
- Tránh nhầm dấu nháy bao quanh giá trị thuộc tính với escape sequence trong string literal Java.
- Hiểu vì sao không thể dựa vào dấu gạch chéo ngược để escape dấu nháy trong giá trị thuộc tính.
- Viết đúng thuộc tính cho inline, external và hybrid snippet.

Cần nhớ: cú pháp thuộc tính thuộc về **Javadoc**, còn cú pháp chuỗi Java thuộc về **ngôn ngữ Java**. Hai bộ phân tích xử lý nội dung ở những giai đoạn và với quy tắc khác nhau.

## 2. Cấu trúc thuộc tính trong thẻ snippet

Một thuộc tính có dạng tổng quát:

~~~text
name=value
~~~

Tên thuộc tính và giá trị được phân cách bằng dấu bằng. Các thuộc tính trong cùng một thẻ được phân cách bằng khoảng trắng hoặc xuống dòng.

Ví dụ:

~~~java
/**
 * {@snippet lang=java id=basic :
 * System.out.println("Hello");
 * }
 */
~~~

Trong ví dụ này:

- `lang=java` nhận diện nội dung là mã Java.
- `id=basic` đặt định danh cho snippet.
- Dấu hai chấm `:` kết thúc phần thuộc tính và mở đầu phần thân inline.
- Các câu lệnh sau dấu hai chấm là nội dung mã.

Một thuộc tính có thể được đặt trên dòng riêng để dễ đọc:

~~~java
/**
 * {@snippet
 *     lang=java
 *     id="snippet-order-validation"
 *     :
 *     if (quantity <= 0) {
 *         throw new IllegalArgumentException("quantity must be positive");
 *     }
 * }
 */
~~~

Không cần viết tất cả thuộc tính trên cùng một dòng. Điều quan trọng là parser nhận diện được tên, dấu bằng, giá trị và ranh giới phần thân.

## 3. Giá trị không có dấu nháy

Với các giá trị đơn giản không chứa khoảng trắng, có thể bỏ dấu nháy:

~~~java
{@snippet lang=java id=basic :
    System.out.println("Hello");
}
~~~

Các giá trị như `java`, `properties` hoặc `basic` là những ví dụ phù hợp cho cách viết không có dấu nháy. Cách này ngắn gọn và dễ đọc.

Dạng không có dấu nháy phù hợp với giá trị là **định danh đơn giản hoặc số nguyên** theo ngữ pháp thuộc tính. Ví dụ `lang=java`, `region=basic` và `id=basic`. Một giá trị có dấu gạch nối, dấu chấm, dấu gạch chéo hoặc khoảng trắng không phải định danh đơn giản; hãy đặt nó trong dấu nháy. Không suy luận rằng cứ không có khoảng trắng là có thể bỏ dấu nháy.

Ví dụ external snippet với thuộc tính ngôn ngữ và vùng đơn giản:

~~~java
/**
 * {@snippet
 *     file="OrderExamples.java"
 *     lang=java
 *     region=basic
 * }
 */
~~~

`file` được đặt trong dấu nháy vì đây là đường dẫn/tên tệp. `lang` và `region` là các token đơn giản nên không cần dấu nháy.

### Không phải mọi giá trị đều là định danh Java

Giá trị thuộc tính snippet không phải lúc nào cũng là tên biến hay tên kiểu Java. `lang` có thể là `properties`, `json` hoặc `text`; `file` là đường dẫn; `id` là định danh HTML; `region` là tên vùng. Vì vậy, không áp dụng máy móc quy tắc đặt tên biến Java cho tất cả giá trị thuộc tính.

## 4. Giá trị có dấu nháy đơn hoặc dấu nháy kép

Khi giá trị có khoảng trắng hoặc cần biểu diễn một chuỗi rõ ràng, đặt nó trong cặp dấu nháy đơn hoặc kép:

~~~java
/**
 * {@snippet
 *     file="examples/Order Examples.java"
 *     lang="java"
 *     id="snippet-order-create"
 * }
 */
~~~

Hai kiểu dấu nháy có vai trò tương đương để bao quanh giá trị chuỗi. Chọn kiểu nào cũng được, miễn là dấu mở và dấu đóng cùng loại.

Ví dụ dùng nháy đơn:

~~~java
{@snippet file='examples/Order Examples.java' lang='java' id='snippet-order-create'}
~~~

Ví dụ dùng nháy kép:

~~~java
{@snippet file="examples/Order Examples.java" lang="java" id="snippet-order-create"}
~~~

Dấu nháy bao quanh **không trở thành một phần của giá trị**. Với ví dụ trên, giá trị thuộc tính `file` là đường dẫn `examples/Order Examples.java`, không bao gồm dấu nháy.

### Khi nào cần đặt dấu nháy?

Giá trị chứa khoảng trắng phải được đặt trong dấu nháy để parser hiểu đó là một giá trị duy nhất.

~~~java
// Có dấu nháy: một giá trị file duy nhất.
{@snippet file="examples/Order Examples.java"}

/* Không có dấu nháy: đường dẫn bị tách ở khoảng trắng,
   không còn là một giá trị thuộc tính duy nhất. */
{@snippet file=examples/Order Examples.java}
~~~

Trong ví dụ sai, phần sau khoảng trắng có thể bị phân tích thành token/thuộc tính khác hoặc làm thẻ lỗi. Không dùng giá trị không nháy cho đường dẫn có khoảng trắng.

## 5. Chọn dấu nháy để giữ dấu nháy bên trong giá trị

Giá trị chuỗi có thể dùng một loại dấu nháy bên trong nếu dấu nháy bao ngoài là loại còn lại. Ví dụ tên tệp có dấu nháy đơn có thể bao bằng dấu nháy kép:

~~~java
{@snippet file="examples/Order's Examples.java"}
~~~

Ngược lại, nếu giá trị có dấu nháy kép, có thể bao bằng dấu nháy đơn:

~~~java
{@snippet file='examples/Order "Special" Examples.java'}
~~~

Đây là cách chọn delimiter, không phải escape. Dấu nháy bên trong thuộc giá trị; dấu nháy bao ngoài chỉ đánh dấu điểm bắt đầu và kết thúc chuỗi thuộc tính.

Nếu một giá trị cần chứa **cả dấu nháy đơn lẫn dấu nháy kép**, không có cơ chế backslash escape tổng quát để đưa một dấu nháy cùng loại vào trong chuỗi thuộc tính. Hãy đổi tên tài nguyên, thay đổi cách tổ chức ví dụ hoặc chuyển nội dung phức tạp vào tệp ngoài.

Ví dụ không nên dựa vào:

~~~java
{@snippet file="examples/Order \"Special\" Examples.java"}
~~~

Không coi `\"` là cách escape dấu nháy kép trong giá trị thuộc tính. Dấu gạch chéo ngược không hoạt động như escape sequence của Java string literal ở ngữ cảnh này.

## 6. Giới hạn escape trong giá trị thuộc tính

### 6.1. Backslash không phải ký tự escape tổng quát

Giá trị thuộc tính snippet không dùng cơ chế escape kiểu Java string. Viết `\"` không làm dấu nháy kép trở thành ký tự thông thường bên trong một giá trị được bao bởi nháy kép.

Ví dụ không nên dùng:

~~~java
{@snippet id="snippet-quote-\"order\"" :
    System.out.println("order");
}
~~~

Cách xử lý đúng là chọn delimiter khác nếu chỉ có một loại dấu nháy bên trong, hoặc đổi giá trị để không cần chứa dấu nháy. Nếu dấu nháy thuộc về **mã Java trong phần thân**, hãy viết nó theo cú pháp Java:

~~~java
/**
 * {@snippet :
 * String text = "He said \"ready\"";
 * System.out.println(text);
 * }
 */
~~~

Trong ví dụ này, `\"` là escape sequence của **Java string literal trong nội dung mã**. Nó không phải escape sequence cho thuộc tính Javadoc. Sự khác biệt nằm ở vị trí:

- Trước dấu hai chấm `:`: parser đang đọc tên và giá trị thuộc tính của Javadoc.
- Sau dấu hai chấm và dòng mới: nội dung snippet được lấy để hiển thị; các escape sequence Java xuất hiện như mã nguồn, nhưng Javadoc không biên dịch đoạn inline đó.

### 6.2. Không dùng escape sequence Java để sửa giá trị thuộc tính

Các dạng như `\n`, `\t` hoặc `\u0041` không phải cách chung để tạo newline, tab hay ký tự Unicode trong giá trị thuộc tính snippet.

- `\n` không biến giá trị thuộc tính thành một dòng mới.
- `\t` không phải cách tạo tab để tách thuộc tính.
- Unicode escape trong mã nguồn Java có quy tắc xử lý riêng và có thể được dịch **trước khi Javadoc phân tích comment**.

Nếu cần giá trị thuộc tính có khoảng trắng, dùng dấu nháy. Nếu cần trình bày dữ liệu phức tạp, đặt dữ liệu trong tệp external thay vì cố gắng nhồi escape sequence vào thuộc tính.

### 6.3. Unicode escape vẫn chịu quy tắc dịch source của Java

Thuộc tính snippet nằm trong comment của tệp Java. Vì vậy, quy tắc Unicode escape của Java source vẫn áp dụng trước khi Javadoc phân tích nội dung comment. Không thể dùng cách viết Unicode escape để bảo đảm một ký tự sẽ được giữ nguyên trong giá trị thuộc tính.

Nếu cần hiển thị nguyên văn chuỗi dạng `\uNNNN`, hãy đưa nội dung vào tệp văn bản external và kiểm tra HTML sinh ra. Nếu tệp đó đồng thời là mã Java được biên dịch, nó vẫn chịu quy tắc Unicode escape của JLS.

## 7. Thuộc tính nhiều dòng và dấu hai chấm

Các thuộc tính có thể được chia thành nhiều dòng. Điều này hữu ích khi một snippet có nhiều nguồn hoặc cần ghi rõ ID, region và ngôn ngữ:

~~~java
/**
 * {@snippet
 *     file="examples/Order Examples.java"
 *     lang="java"
 *     id="snippet-order-validation"
 *     region="validation"
 * }
 */
~~~

Với inline hoặc hybrid snippet, dấu hai chấm phân cách danh sách thuộc tính và phần thân:

~~~java
/**
 * {@snippet
 *     lang=java
 *     id="snippet-order-validation"
 *     :
 *     if (quantity <= 0) {
 *         throw new IllegalArgumentException("quantity must be positive");
 *     }
 * }
 */
~~~

Với external snippet thuần, phần thân không nằm trong thẻ nên không cần dấu hai chấm. Với hybrid snippet, có cả thuộc tính nguồn ngoài và phần thân inline sau dấu hai chấm:

~~~java
/**
 * {@snippet
 *     file="OrderExamples.java"
 *     region=validation
 *     id="snippet-order-validation"
 *     :
 *     if (quantity <= 0) {
 *         throw new IllegalArgumentException("quantity must be positive");
 *     }
 * }
 */
~~~

Không đặt dấu hai chấm trong danh sách thuộc tính như thể nó là dấu phân cách giữa hai thuộc tính. Khi dùng dạng inline, dấu hai chấm đánh dấu thời điểm kết thúc phần khai báo và bắt đầu phần thân. Nội dung phần thân bắt đầu từ dòng mới sau dấu hai chấm.

## 8. Phân biệt thuộc tính snippet với thuộc tính markup comment

Một nguồn nhầm lẫn thường gặp là thấy cùng tên thuộc tính ở cả thẻ snippet và markup comment.

~~~java
/**
 * {@snippet id="snippet-order-create" lang="java" :
 * // @highlight substring="create"
 * String code = OrderCode.create("order", 42);
 * System.out.println(code);
 * }
 */
~~~

Ở đây có hai lớp cú pháp:

| Vị trí | Thành phần | Vai trò |
| --- | --- | --- |
| Trước dấu `:` | `id="snippet-order-create"` | Thuộc tính của thẻ snippet, nhận diện khối trong HTML. |
| Trước dấu `:` | `lang="java"` | Thuộc tính của thẻ snippet, xác định ngôn ngữ. |
| Trong phần thân | `@highlight substring="create"` | Markup comment điều khiển cách hiển thị đoạn mã. |
| Trong phần thân | `substring="create"` | Giá trị của thuộc tính markup, không phải thuộc tính của thẻ snippet. |

Dấu nháy trong `substring="create"` là cú pháp của markup comment, được phân tích theo quy tắc markup. Không được nhầm nó với danh sách thuộc tính đứng trước dấu hai chấm.

Tương tự, `region` có thể xuất hiện trong thuộc tính snippet để chọn vùng external, hoặc trong markup comment `@start region=...` và `@end region=...` để đánh dấu vùng trong tệp nguồn. Ngữ cảnh quyết định ý nghĩa của nó.

## 9. Ví dụ thực tế: external snippet có đường dẫn chứa khoảng trắng

Giả sử thư viện có ví dụ được lưu trong tệp `Order Examples.java` dưới thư mục `snippet-files`. Trong Javadoc:

~~~java
/**
 * Ví dụ tạo mã đơn hàng:
 *
 * {@snippet
 *     file="Order Examples.java"
 *     lang=java
 *     id="snippet-order-create"
 *     region=basic
 * }
 */
public class OrderCode {
}
~~~

Trong tệp external `Order Examples.java`:

~~~java
package example;

public class OrderExamples {
    public static void main(String[] args) {
        // @start region=basic
        String code = OrderCode.create("order", 42);
        if (!"order:42".equals(code)) {
            throw new AssertionError(code);
        }
        // @end region=basic
    }
}
~~~

Giá trị `file` được đặt trong dấu nháy vì tên tệp có khoảng trắng. `lang=java` và `region=basic` là các giá trị ngắn, nên không cần dấu nháy. `id` được đặt trong dấu nháy để chứa tên ID có dấu gạch nối.

Ví dụ này minh họa việc chọn kiểu dấu nháy theo từng thuộc tính. Không cần tất cả thuộc tính cùng dùng một kiểu; mỗi giá trị có thể chọn dạng phù hợp miễn đúng cú pháp.

Nếu tên tệp không có khoảng trắng, vẫn có thể giữ dấu nháy để tăng tính nhất quán:

~~~java
{@snippet file="OrderExamples.java" lang="java" id="snippet-order-create" region=basic}
~~~

Đây là cách viết dễ đọc khi nhiều người cùng duy trì tài liệu.

## 10. Quy trình chọn và kiểm tra giá trị thuộc tính

Trước khi lưu một snippet, hãy kiểm tra theo thứ tự:

1. **Xác định thuộc tính cần dùng:** `lang`, `id`, `file`, `class` hoặc `region`.
2. **Xác định loại giá trị:** token ngắn hay chuỗi cần có dấu nháy.
3. **Kiểm tra khoảng trắng:** nếu giá trị có khoảng trắng, đặt trong dấu nháy đơn hoặc kép.
4. **Chọn delimiter:** dùng loại dấu nháy không xuất hiện trong giá trị nếu cần chứa một loại dấu nháy.
5. **Không dùng backslash escape:** đừng dùng `\"`, `\n` hoặc `\t` để điều khiển parser thuộc tính.
6. **Kiểm tra ranh giới:** dấu hai chấm kết thúc thuộc tính trong inline/hybrid snippet; phần thân bắt đầu ở dòng tiếp theo.
7. **Kiểm tra source sau Unicode translation:** nếu có chuỗi `\uNNNN` trong comment, nhớ rằng Java xử lý nó trước Javadoc.
8. **Sinh Javadoc:** xem cảnh báo/lỗi và xác nhận snippet được đọc đúng.
9. **Kiểm tra HTML:** xác nhận ID, đường dẫn và nội dung snippet hiển thị như dự định.

### Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Giá trị file bị tách thành nhiều token. | Giá trị chứa khoảng trắng nhưng không có dấu nháy. | Bao toàn bộ giá trị bằng dấu nháy đơn hoặc kép. |
| Parser kết thúc giá trị quá sớm. | Dùng dấu nháy bao ngoài giống dấu nháy xuất hiện bên trong. | Chọn loại dấu nháy còn lại làm delimiter. |
| `\"` không escape dấu nháy thuộc tính. | Giá trị thuộc tính không dùng escape sequence kiểu Java string. | Đổi delimiter hoặc cấu trúc lại giá trị. |
| Dùng `\n` để xuống dòng trong giá trị thuộc tính. | Backslash không biến thành escape newline trong ngữ cảnh này. | Chia thuộc tính thành các dòng hoặc dùng tệp external. |
| Thuộc tính bị đọc thành phần thân. | Đặt dấu `:` quá sớm hoặc sai vị trí. | Đặt toàn bộ thuộc tính trước dấu `:`. |
| Nhầm `substring` của markup với thuộc tính snippet. | Hai lớp cú pháp cùng có dạng name=value. | Xác định đang ở trước hay sau dấu `:`. |
| Unicode escape thay đổi nội dung comment. | Java dịch Unicode escape trước khi Javadoc đọc comment. | Dùng external text snippet nếu cần hiển thị nguyên văn. |

## 11. Bài tập thực hành

### Bài tập 1: Chọn dạng có hoặc không có dấu nháy

Với mỗi giá trị, quyết định có cần dấu nháy không:

- `lang=java`
- `id=snippet-order-create`
- `file=Order Examples.java`
- `file="Order Examples.java"`
- `region=validation`

**Gợi ý đáp án:** `lang=java` và `region=validation` là các định danh đơn giản nên có thể không cần dấu nháy. `id=snippet-order-create` có dấu gạch nối nên phải viết dạng chuỗi có dấu nháy, ví dụ `id="snippet-order-create"`. Đường dẫn `file` phải được đặt trong dấu nháy; càng cần thiết khi giá trị chứa khoảng trắng. Dạng `file=Order Examples.java` là ví dụ sai.

### Bài tập 2: Sửa thuộc tính có dấu nháy bên trong

Cho ý định dùng tên tệp `examples/Order "Special".java`. Hãy chọn dấu nháy đơn làm delimiter để giữ dấu nháy kép bên trong. Giải thích vì sao dùng dấu nháy kép bao ngoài và thêm `\"` không phải cách escape đúng.

### Bài tập 3: Phân biệt hai lớp cú pháp

Với đoạn sau, hãy phân loại từng thuộc tính:

~~~java
/**
 * {@snippet id="snippet-quote-example" lang=java :
 * // @highlight substring="create"
 * String message = "He said \"ready\"";
 * System.out.println(message);
 * }
 */
~~~

Xác định `id` và `lang` thuộc phần mở thẻ; `substring` thuộc markup comment; `\"` trong string literal thuộc cú pháp Java. Giải thích vì sao cùng dấu nháy nhưng quy tắc xử lý khác nhau.

### Bài tập 4: Tạo external snippet

Tạo một tệp có tên `Order Examples.java` và tham chiếu bằng `file="Order Examples.java"`. Đặt thêm `lang=java`, `id="snippet-order-create"` và `region=basic`. Sinh Javadoc, kiểm tra snippet được trích đúng và ID xuất hiện trong HTML.

**Tự kiểm:** biết khi nào cần nháy; chọn đúng loại delimiter; không dùng backslash để escape giá trị thuộc tính; phân biệt thuộc tính snippet với markup comment; hiểu Unicode escape vẫn thuộc bước dịch source; đã sinh Javadoc để xác nhận.

## 12. Ghi nhớ

- **Giá trị đơn giản có thể không cần dấu nháy.** Ví dụ `lang=java` và `region=basic`.
- **Giá trị chứa khoảng trắng phải đặt trong dấu nháy.** Dùng nháy đơn hoặc kép tùy nội dung.
- **Dấu nháy bao quanh không thuộc giá trị.** Chọn delimiter khác nếu cần giữ một loại dấu nháy bên trong.
- **Không có backslash escape tổng quát cho giá trị thuộc tính snippet.** `\"` không tương đương escape sequence của Java string.
- **Java string escape chỉ có ý nghĩa trong phần mã Java.** Đừng nhầm cú pháp thuộc tính trước dấu hai chấm với nội dung snippet sau dấu hai chấm.
- **Unicode escape được dịch trước khi Javadoc phân tích comment.** Dùng external text khi cần giữ nguyên cách viết escape.

## Tài liệu chính thống

- [Oracle – JDK 26 Javadoc Snippets Guide, mục Attributes](https://docs.oracle.com/en/java/javase/26/javadoc/snippets.html).
- [Oracle – JDK 26 Documentation Comment Specification, cú pháp snippet và attribute values](https://docs.oracle.com/en/java/javase/26/docs/specs/javadoc/doc-comment-spec.html).
- [Oracle – Java Language Specification, JDK 26, mục 3.2–3.3 Lexical Translations và Unicode Escapes](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-3.html).
- [OpenJDK – JEP 413: Code Snippets in Java API Documentation](https://openjdk.org/jeps/413).

