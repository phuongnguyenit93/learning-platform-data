# Thuộc tính `type` của `@highlight` và lựa chọn kiểu nhấn mạnh phù hợp

## Mục tiêu bài học

Java 18 đưa `{@snippet}` vào tài liệu API thông qua **JEP 413**. Tính năng này tiếp tục được hỗ trợ bởi công cụ `javadoc` trong các JDK hiện đại. Khi tài liệu có ví dụ mã, markup tag `@highlight` giúp người đọc chú ý đến phần quan trọng. Thuộc tính **`type`** quyết định *kiểu trình bày* của phần được chọn.

Bài học nằm trong chương **Markup và region** của module `JAVA_VERSION_JAVA18`. Trọng tâm là sử dụng những khả năng hiện còn áp dụng: phân biệt ba giá trị của `type`, chọn kiểu phù hợp với mục đích giải thích API, hiểu sự phụ thuộc vào stylesheet và kiểm chứng trên JDK đang dùng.

Sau bài học, bạn có thể:

- Viết đúng cú pháp `@highlight type=bold`, `@highlight type=italic` và `@highlight type=highlighted`.
- Giải thích vì sao `type` chỉ quyết định **hình thức nhấn mạnh**, trong khi `substring`, `regex` và `region` quyết định **phần nội dung được nhấn mạnh**.
- Đọc ví dụ có `type` bị lược bỏ và hiểu kiểu mặc định trong standard doclet.
- Chọn mức nhấn mạnh phù hợp khi diễn giải tên biến, phép gọi API, nhánh xử lý và dòng mã cần chú ý.
- Kiểm tra CSS class và khả năng đọc của đoạn mã trong Javadoc đã sinh, kể cả khi dự án dùng stylesheet tùy chỉnh.

> **Phạm vi:** Đây là cú pháp dành cho markup trong `{@snippet}` của Javadoc. Nó không phải một annotation, không phải từ khóa Java, cũng không phải lệnh thay đổi hành vi thực thi của chương trình.

## 1. Nhắc lại: `@highlight` gồm hai quyết định độc lập

Khi thêm một chỉ dẫn `@highlight`, người viết thực chất trả lời hai câu hỏi:

1. **Nhấn mạnh chữ nào?** Chọn dòng hiện tại, chuỗi con trong dòng bằng `substring`, phần khớp mẫu bằng `regex`, hoặc mở rộng trên nhiều dòng bằng `region`.
2. **Nhấn mạnh bằng cách nào?** Chọn `type=bold`, `type=italic` hay `type=highlighted`.

Cú pháp tổng quát:

~~~text
// @highlight [substring="văn bản" | regex="biểu thức"] [region="tên"] [type=bold|italic|highlighted]
~~~

Trong Java, markup nằm ở phần comment cuối dòng. Ví dụ:

~~~java
int attempts = 3; // @highlight substring="attempts" type=bold
~~~

Khi sinh tài liệu:

- Nội dung `int attempts = 3;` vẫn xuất hiện.
- Từ `attempts` được gắn kiểu nhấn mạnh `bold`.
- Phần `// @highlight ...` bị lược khỏi khối mã mà người đọc thấy.

Nếu không có `substring` hoặc `regex`, phần được nhấn sẽ là **cả dòng** theo phạm vi mặc định. Nếu có `region`, cùng quy tắc chọn chữ được áp dụng qua các dòng thuộc region đó. **`type` không thay đổi phạm vi chọn.**

Để tránh nhầm lẫn, có thể hình dung chuỗi xử lý như sau:

~~~text
Nội dung snippet
      |
      v
Xác định phạm vi: dòng / region
      |
      v
Xác định đoạn được chọn: toàn phạm vi / substring / regex
      |
      v
Áp dụng kiểu: bold / italic / highlighted
      |
      v
Khối mã trong HTML Javadoc
~~~

## 2. Ba giá trị hợp lệ của `type`

Theo **JavaDoc Documentation Comment Specification** của standard doclet, danh sách giá trị hợp lệ gồm **`bold`, `italic` và `highlighted`**. Tên kiểu được chuyển thành một **CSS class** trong HTML sinh ra; stylesheet của Javadoc hoặc stylesheet dự án quyết định cách hiển thị cuối cùng.

| Giá trị | Hiệu ứng điển hình với stylesheet chuẩn | Khi nào nên dùng | Điều cần lưu ý |
| --- | --- | --- | --- |
| `type=bold` | Chữ được chọn hiển thị **đậm**. | Tên API hoặc biểu thức trọng tâm cần người đọc nhận ra ngay. | Phần quá dài nếu đều in đậm sẽ khó phân cấp thị giác. |
| `type=italic` | Chữ được chọn hiển thị *nghiêng*. | Chú thích nhẹ cho một tên, tham số, hoặc từ đang giải thích trong dòng mã. | Chữ nghiêng trong font monospace có thể khó đọc ở cỡ nhỏ; nên dùng tiết chế. |
| `type=highlighted` | Phần được chọn có kiểu nổi bật rõ, thường dựa vào màu nền hoặc tương phản màu. | Một dòng quyết định, thao tác dễ bỏ sót, hoặc điểm khác biệt cần nhìn thấy khi quét nhanh. | Màu cụ thể phụ thuộc stylesheet và theme, nên cần kiểm tra độ tương phản. |

Bảng mô tả **cách dùng được khuyến nghị**, không phải quy tắc bắt buộc của ngôn ngữ. Javadoc không tự hiểu rằng `bold` nghĩa là “tên phương thức”, `italic` nghĩa là “tham số” hay `highlighted` nghĩa là “cảnh báo”. Ý nghĩa sư phạm đến từ lời giải thích đi kèm và cách bạn dùng thống nhất trong tài liệu.

### 2.1. `type=bold`: nhấn mạnh rõ nhưng gọn

Ví dụ, ta cần chỉ ra phương thức chuẩn hóa chuỗi trước khi kiểm tra dữ liệu:

~~~java
/**
 * Chuẩn hóa chuỗi trước khi kiểm tra:
 * {@snippet :
 *     String normalized = input.strip(); // @highlight substring="strip" type=bold
 *     boolean empty = normalized.isBlank();
 * }
 */
public class BoldSnippetDoc {
}
~~~

Nội dung chữ được hiển thị trong tài liệu:

~~~java
String normalized = input.strip();
boolean empty = normalized.isBlank();
~~~

Trên trang HTML, phần `strip` được nhấn đậm. Dòng còn lại giữ cách trình bày thông thường. `String.strip()` và `String.isBlank()` là các API ổn định từ Java 11, vẫn hữu ích trong các JDK hiện đại.

Kiểu `bold` phù hợp khi bạn muốn người đọc **nhận diện chính xác tên phương thức hoặc biến** mà không làm nổi cả dòng.

### 2.2. `type=italic`: nhấn nhẹ vào một thành phần

Giả sử tài liệu minh họa cách chuyển đổi tên đầu vào thành giá trị dùng để lưu trữ:

~~~java
/**
 * {@snippet :
 *     String input = "  Hello ";
 *     String normalized = input.strip(); // @highlight substring="normalized" type=italic
 *     System.out.println(normalized);
 * }
 */
public class ItalicSnippetDoc {
}
~~~

Ở dòng thứ hai, từ `normalized` được hiển thị theo kiểu *italic* của stylesheet. Dòng thứ ba không bị tác động vì chỉ dẫn không khai báo region.

`italic` có ích khi tác giả đang giới thiệu một biến trung gian. Tuy nhiên, nếu mục tiêu là làm bật một thao tác dễ gây lỗi hoặc một điểm cần nhìn thấy rất nhanh, `bold` hoặc `highlighted` thường dễ nhận ra hơn. Nên dùng `italic` sau khi kiểm tra xem font monospace của giao diện có phân biệt đủ rõ chữ nghiêng và chữ thường hay không.

### 2.3. `type=highlighted`: tạo điểm tập trung thị giác

~~~java
/**
 * {@snippet :
 *     String normalized = input.strip();
 *     if (normalized.isBlank()) { // @highlight type=highlighted
 *         throw new IllegalArgumentException("empty");
 *     }
 * }
 */
public class HighlightedSnippetDoc {
}
~~~

Trong khối mã đã sinh, chỉ dòng `if (normalized.isBlank()) {` được áp dụng class `highlighted`. Hai dòng bên trong khối `if` không tự động nhận class chỉ vì chúng nằm trong cặp ngoặc nhọn.

`highlighted` phù hợp với câu lệnh điều kiện cần chú ý, bước có tác động quan trọng đến luồng xử lý hoặc chỗ khác nhau giữa hai cách sử dụng API. Hiệu ứng có thể sử dụng màu và không nên đoán màu cụ thể của trang từ tên `highlighted`.

## 3. Nếu không ghi `type` thì sao?

Với standard doclet, **kiểu tô nổi bật mặc định là `bold`**. Vì vậy hai chỉ dẫn sau nhằm tạo cùng kiểu nhấn mạnh cho từ `strip`:

~~~java
String value = input.strip(); // @highlight substring="strip"
~~~

~~~java
String value = input.strip(); // @highlight substring="strip" type=bold
~~~

Trong nhiều trường hợp, bỏ `type` giúp comment gọn hơn. Viết tường minh `type=bold` có thể hữu ích khi cùng một ví dụ hoặc nhóm tài liệu sử dụng cả `italic` và `highlighted`: người bảo trì dễ thấy chủ đích định dạng.

**Đừng đồng nhất kiểu mặc định với `highlighted`.** Ba tên kiểu đều là các lựa chọn hợp lệ, còn mặc định standard doclet dùng `bold`. Khi dự án tùy chỉnh CSS, hiệu ứng thực tế của `bold` vẫn có thể được định nghĩa lại.

Nếu tài liệu nội bộ dùng stylesheet riêng, cách đáng tin cậy nhất là sinh HTML với đúng cấu hình triển khai rồi xem trực tiếp.

## 4. Một ví dụ so sánh đủ ba kiểu

Tạo file `HighlightTypesDoc.java` với một Javadoc comment chứa cả ba kiểu:

~~~java
/**
 * Các vị trí trọng tâm khi kiểm tra dữ liệu người dùng:
 *
 * {@snippet :
 *     String normalized = raw.strip();                  // @highlight substring="strip" type=bold
 *     boolean missing = normalized.isBlank();           // @highlight substring="isBlank" type=italic
 *     if (missing) {                                    // @highlight type=highlighted
 *         throw new IllegalArgumentException("empty");
 *     }
 * }
 */
public class HighlightTypesDoc {
}
~~~

Đây là **một mảnh mã minh họa**, có biến `raw` được giả định đã khai báo ở ngữ cảnh bên ngoài; snippet không nhất thiết phải là chương trình Java có thể biên dịch độc lập.

Nội dung chữ mà Javadoc trình bày:

~~~java
String normalized = raw.strip();
boolean missing = normalized.isBlank();
if (missing) {
    throw new IllegalArgumentException("empty");
}
~~~

Ba tác động độc lập:

1. `strip` được nhấn **đậm** vì `substring="strip" type=bold`.
2. `isBlank` được nhấn *nghiêng* vì `substring="isBlank" type=italic`.
3. Toàn bộ dòng `if (missing) {` được áp dụng kiểu `highlighted` do không có `substring`/`regex`.

Các comment điều khiển không xuất hiện trong khối mã. Câu lệnh `throw` và dấu `}` ở hai dòng sau không bị tô theo kiểu `highlighted`, vì không có region kéo dài.

Điểm mạnh của ví dụ nằm ở **sự phân cấp**: tên phương thức chính nhận trọng tâm rõ, lời gọi hỗ trợ có mức nhấn nhẹ, còn câu lệnh quyết định nhánh được làm nổi ở cấp toàn dòng. Một tài liệu khác có thể ưu tiên cách trình bày khác; trước khi chọn, hãy xác định người đọc cần nhận ra điều gì.

## 5. `type` kết hợp với `substring`, `regex` và toàn dòng

`type` chỉ chọn **kiểu**; các thuộc tính còn lại quyết định **văn bản**:

| Ví dụ markup comment | Phần được chọn | Kiểu |
| --- | --- | --- |
| `// @highlight type=bold` | Toàn bộ dòng có comment. | `bold` |
| `// @highlight substring="strip" type=italic` | Mọi lần xuất hiện của chuỗi `strip` trên dòng. | `italic` |
| `// @highlight regex='get[A-Z][a-z]+' type=bold` | Các đoạn phù hợp mẫu regex trên dòng. | `bold` |
| `// @highlight substring="null" type=highlighted` | Mọi lần xuất hiện của chữ `null` trên dòng. | `highlighted` |
| `// @highlight substring="value"` | Mọi lần xuất hiện của `value` trên dòng. | Mặc định `bold` |

### 5.1. Với `substring`: không có hiểu biết về cú pháp Java

~~~java
String statusText = "status=" + status; // @highlight substring="status" type=italic
~~~

`substring="status"` khớp cả bên trong tên `statusText`, chuỗi `"status="` và tên biến `status`. Công cụ chọn **văn bản**, không kiểm tra loại token Java.

Nếu cần chọn đúng một tên theo quy tắc cụ thể, dùng regex để giới hạn kết quả, hoặc đơn giản điều chỉnh ví dụ sao cho phần cần nhấn có vị trí rõ ràng.

### 5.2. Với `regex`: chọn một mẫu rồi áp kiểu

~~~java
String id1 = "A", id2 = "B"; // @highlight regex='id[0-9]+' type=bold
~~~

Cả `id1` và `id2` được nhấn `bold`, vì cả hai cùng khớp mẫu. Lựa chọn `type` **không thay đổi biểu thức chính quy**. Nếu viết `type=italic`, cùng hai đoạn sẽ được nhấn nghiêng.

Với regex phức tạp, phải chú ý cú pháp `java.util.regex.Pattern` và cách đặt dấu nháy của thuộc tính markup. Luôn kiểm tra ví dụ cả ở trường hợp khớp và trường hợp không khớp.

### 5.3. Với cả dòng: giới hạn mạnh hơn cần thiết có thể gây nhiễu

~~~java
if (input == null) { // @highlight type=highlighted
~~~

Không có `substring`/`regex` nên toàn bộ dòng `if (input == null) {` được làm nổi. Cách này thường phù hợp nếu mục đích giải thích là **điều kiện kiểm tra**, chứ không riêng từ `null`.

Nếu chỉ muốn người đọc chú ý tới việc kiểm tra giá trị `null`:

~~~java
if (input == null) { // @highlight substring="null" type=bold
~~~

Hai cách dùng khác nhau ở **phần được chọn** lẫn **kiểu**. Người viết nên chọn mức đủ để truyền đạt ý tưởng, không mặc định tô cả dòng cho mọi ví dụ.

## 6. Kết hợp `type` với phạm vi nhiều dòng

Khi muốn áp cùng một kiểu cho nhiều vị trí, dùng `region` để mở vùng và `@end` để kết thúc. Trong ví dụ sau, mỗi lần xuất hiện của từ `normalized` trong vùng được nhấn đậm:

~~~java
/**
 * {@snippet :
 *     // @highlight region="normalize" substring="normalized" type=bold :
 *     String normalized = input.strip();
 *     boolean blank = normalized.isBlank();
 *     System.out.println(normalized);
 *     // @end region="normalize"
 *     System.out.println("finished");
 * }
 */
public class HighlightRegionTypeDoc {
}
~~~

Văn bản hiển thị:

~~~java
String normalized = input.strip();
boolean blank = normalized.isBlank();
System.out.println(normalized);
System.out.println("finished");
~~~

Ba lần xuất hiện `normalized` ở ba dòng đầu được nhấn `bold`; dòng `"finished"` ở ngoài vùng không chịu ảnh hưởng của markup. Dòng comment `@highlight ... :` và `@end ...` bị loại khỏi mã hiển thị.

Hai chi tiết quan trọng:

- `region="normalize"` điều khiển **phạm vi** của `@highlight` cho đến marker `@end region="normalize"`.
- Dấu `:` cuối markup comment khiến vùng bắt đầu từ **dòng kế tiếp**. Nhờ đó comment điều khiển có thể đứng riêng, dễ đọc trong file nguồn.

Khi sử dụng region cho kiểu `highlighted` trên nhiều dòng, cân nhắc lượng nội dung được đánh dấu. Tô nổi quá nhiều dòng làm phần cần chú ý không còn nổi bật.

### Region chọn nội dung và region áp dụng kiểu

Một external snippet có thể dùng `{@snippet file="Example.java" region="example"}` để **chọn đoạn mã được đưa vào tài liệu**. Còn `@highlight region="focus" type=bold` dùng `region` để **mở rộng nơi áp dụng cách nhấn mạnh**.

Chúng giải quyết hai bài toán khác nhau. Thuộc tính `type` của `@highlight` không làm thay đổi đoạn mã mà thẻ `{@snippet}` chọn từ file bên ngoài.

## 7. Thực hành: quyết định kiểu nhấn mạnh theo mục đích truyền đạt

Không có một `type` đúng cho mọi ví dụ. Cách lựa chọn nên dựa trên **đối tượng mà người đọc cần nhìn thấy trước**:

| Mục đích của đoạn giải thích | Gợi ý chọn | Ví dụ nội dung |
| --- | --- | --- |
| Chỉ đúng một phương thức mới được giới thiệu | `type=bold` với `substring`. | Nhấn `strip` trong `input.strip()`. |
| Đề cập tên biến trung gian mà không muốn nó chiếm toàn bộ sự chú ý | `type=italic` với `substring`. | Nhấn `normalized` trong câu lệnh gán. |
| Chỉ ra nhánh xử lý quyết định hoặc một bước dễ bỏ sót | `type=highlighted`, thường đi với cả dòng. | Nhấn dòng `if (normalized.isBlank()) {`. |
| Đánh dấu cùng một tên xuất hiện nhiều lần trong một vùng | `type=bold` với `region` và `substring`. | Nhấn `normalized` xuyên suốt ba dòng. |
| Mẫu API lặp lại với các hậu tố khác nhau | `type=bold` hoặc `italic` với `regex`. | Nhấn `getName`, `getAge` nếu khớp mẫu có chủ đích. |
| Trang có nhiều ví dụ và nhiều mức độ quan trọng | Quy định một bộ quy tắc dùng chung, rồi áp dụng nhất quán. | Nhấn API bằng `bold`, bước trọng yếu bằng `highlighted`. |

Một quy trình lựa chọn đơn giản:

1. Viết câu giải thích trước đoạn mã: “Người đọc cần chú ý đến điều gì?”.
2. Chọn mức phạm vi hẹp nhất truyền đạt được ý: một chuỗi con, một dòng, hoặc region nhiều dòng.
3. Chọn `type` phù hợp với mức nhấn mong muốn và thống nhất với các ví dụ xung quanh.
4. Sinh Javadoc, xem kết quả và điều chỉnh nếu đoạn cần chú ý chưa đủ rõ.

Ví dụ, nếu mục tiêu là giải thích cách xử lý chuỗi rỗng, **`isBlank`** mới là trọng tâm:

~~~java
boolean empty = normalized.isBlank(); // @highlight substring="isBlank" type=bold
~~~

Nếu mục tiêu là nhắc người đọc thực hiện kiểm tra **trước khi tiếp tục xử lý**, nhấn toàn bộ dòng điều kiện có thể hợp lý hơn:

~~~java
if (normalized.isBlank()) { // @highlight type=highlighted
~~~

Cùng một API nhưng khác thông điệp sẽ dẫn tới lựa chọn `type` và phạm vi khác nhau.

## 8. Vì sao `type` gắn với CSS và ảnh hưởng của theme

Standard doclet chuyển mỗi giá trị `type` thành **tên CSS class** tương ứng. Đặc tả HTML đầu ra của Javadoc liệt kê các class `bold`, `italic`, `highlighted` dùng trong snippet.

Có thể hình dung ý tưởng hiển thị như sau:

~~~html
<pre class="snippet">
  <code>String value = input.<span class="bold">strip</span>();</code>
</pre>
~~~

Đoạn HTML trên **chỉ minh họa ý tưởng CSS class**, không phải cam kết về toàn bộ cấu trúc HTML chính xác do mọi phiên bản JDK tạo ra. Tên class và ý nghĩa kiểu theo đặc tả là phần ổn định cần biết; chi tiết phần tử bao quanh do standard doclet quyết định.

### 8.1. Có thể thay giao diện mà không đổi comment

Giả sử tài liệu sử dụng mặc định:

~~~java
String value = input.strip(); // @highlight substring="strip" type=highlighted
~~~

Dù cùng nội dung nguồn, `highlighted` có thể trông khác khi trang sử dụng stylesheet riêng, theme sáng/tối hoặc CSS của phiên bản JDK khác. Không nên mô tả kỹ thuật này thành “`type=highlighted` luôn tô nền vàng”, vì đặc tả không cam kết một màu cố định.

Nếu cần tùy chỉnh trên các JDK hiện đại, có thể thêm CSS mà không phải thay toàn bộ stylesheet của Javadoc. Ví dụ một file `snippet-emphasis.css` dành cho dự án:

~~~css
/* Chỉ là ví dụ tùy chỉnh màu nhấn; kiểm tra trên theme thực tế. */
.snippet .highlighted {
    background-color: #ffe9a6;
    color: #202020;
}
~~~

Sau khi đã có file CSS riêng, có thể chạy:

~~~bash
javadoc --add-stylesheet snippet-emphasis.css -d docs HighlightTypesDoc.java
~~~

`--add-stylesheet` thêm stylesheet bên cạnh stylesheet mặc định. Với tác vụ này, nó phù hợp hơn việc thay hẳn stylesheet chính bằng `--main-stylesheet`. Đây là cách kiểm soát ngoại hình khi thật sự cần giao diện nhất quán theo sản phẩm.

Không cần CSS riêng cho mọi bài: mặc định của Javadoc thường đã đủ cho phần lớn tài liệu API. Cần tùy chỉnh khi tổ chức có quy chuẩn màu sắc và đã kiểm thử khả năng đọc.

### 8.2. Lưu ý khả năng tiếp cận

Kiểu nhấn mạnh là **tín hiệu thị giác bổ trợ**, không nên là cách duy nhất để truyền đạt một yêu cầu quan trọng.

- Với `type=highlighted`, kiểm tra độ tương phản chữ/nền ở theme sáng và tối.
- Với `type=italic`, đọc thử trên font monospace và màn hình nhỏ để chắc chắn nét nghiêng dễ nhận ra.
- Với mọi `type`, viết lời giải thích cụ thể như “Dòng này kiểm tra dữ liệu đầu vào” thay vì “Xem dòng màu vàng”.
- Dùng ít kiểu nhấn mạnh trong cùng một khối mã để người đọc nhận biết được thứ tự ưu tiên.

Điều này cũng giúp tài liệu duy trì ý nghĩa khi stylesheet được thay đổi hoặc được xem trong môi trường có khả năng hiển thị khác nhau.

## 9. Kiểm chứng trên JDK đang sử dụng

Tạo file `HighlightTypesDoc.java` ở thư mục làm việc với ví dụ sau:

~~~java
/**
 * Minh họa các kiểu nhấn mạnh trong Javadoc snippet.
 *
 * {@snippet :
 *     String input = "  sample  ";
 *     String value = input.strip();         // @highlight substring="strip" type=bold
 *     boolean empty = value.isBlank();      // @highlight substring="isBlank" type=italic
 *     if (empty) {                          // @highlight type=highlighted
 *         throw new IllegalArgumentException("blank");
 *     }
 * }
 */
public class HighlightTypesDoc {
}
~~~

Chạy với JDK hiện tại có hỗ trợ `@snippet`:

~~~bash
javadoc -d docs HighlightTypesDoc.java
~~~

Mở trang `docs/HighlightTypesDoc.html` được tạo ra rồi kiểm tra:

1. Khối mã hiển thị nguyên các câu lệnh từ ví dụ; các comment `@highlight` không còn xuất hiện như comment trong mã.
2. `strip` được nhấn `bold`, `isBlank` được nhấn `italic`.
3. Dòng `if (empty) {` nhận kiểu `highlighted`; câu lệnh `throw` không tự được nhấn vì ở dòng khác.
4. So sánh giao diện khi dùng stylesheet mặc định với stylesheet tùy chỉnh nếu dự án đã có cấu hình riêng.
5. Khi xem HTML hoặc công cụ Inspect của trình duyệt, tìm class `bold`, `italic` và `highlighted` ở các phần mã tương ứng.

**Cần phân biệt hai phép kiểm:** `javac` biên dịch lớp Java; `javadoc` tạo và kiểm tra tài liệu API. Ví dụ `{@snippet}` được xử lý khi sinh tài liệu, nên chỉ chạy chương trình Java sẽ không cho biết kiểu nhấn mạnh có đúng hay không.

Nếu công cụ báo lỗi do tên `type`, cú pháp thuộc tính, regex hoặc region, hãy sửa markup rồi sinh lại trang. Khi chỉ dùng loại nhấn mạnh, không cần chạy thêm framework hoặc công cụ ngoài chuẩn JDK.

## 10. Các lỗi thường gặp

| Nhầm lẫn | Điều gì thực sự xảy ra | Cách xử lý |
| --- | --- | --- |
| Nghĩ `type=highlighted` là giá trị mặc định. | Kiểu mặc định của standard doclet là `bold`. | Ghi `type=highlighted` tường minh khi muốn kiểu này. |
| Dùng `type=underline`, `type=red` hoặc tên tự đặt. | Đây không thuộc ba giá trị `type` hợp lệ theo đặc tả. | Chỉ dùng `bold`, `italic`, `highlighted`; tùy chỉnh giao diện qua CSS nếu cần. |
| Dùng `type=bold` và mong chỉ tên biến được tô. | Khi không có `substring`/`regex`, cả phạm vi dòng/region được nhấn. | Thêm `substring` hoặc `regex` để giới hạn phần chữ. |
| Đặt comment `// @highlight type=italic` ở một dòng riêng, muốn nhấn dòng tiếp theo. | Mặc định chỉ dẫn áp dụng trên dòng chứa comment. | Đặt comment ở cuối dòng mục tiêu, hoặc thêm `:` ở cuối markup comment. |
| Dùng `region` nhưng không đóng `@end`. | Phạm vi đánh dấu không được kết thúc hợp lệ. | Thêm `@end` hoặc `@end region="..."` tương ứng. |
| Giả định `highlighted` luôn có một màu cụ thể. | Stylesheet quyết định màu thực tế. | Kiểm tra cả stylesheet mặc định và theme dự án. |
| Dùng `italic` cho cả đoạn mã dài. | Nhiều dòng nghiêng có thể giảm khả năng đọc. | Chỉ chọn đoạn ngắn hoặc ưu tiên `bold`/`highlighted` theo mục đích. |
| Xem `type` như chỉ dẫn semantic của Java. | `type` chỉ điều khiển hình thức trình bày trong Javadoc. | Kết hợp chú giải rõ nghĩa bên ngoài snippet. |
| Nghĩ đổi `type` sẽ sửa mã nguồn. | Chỉ HTML Javadoc thay đổi cách hiển thị; file Java vẫn nguyên. | Muốn đổi mã thực thi phải sửa mã nguồn và kiểm thử riêng. |

## 11. Bài tập tự đánh giá

### Bài 1 — Xác định giá trị `type`

Giả sử muốn nhấn **toàn bộ** dòng kiểm tra dưới đây bằng kiểu có nền nổi bật điển hình:

~~~java
if (input == null) {
~~~

**Gợi ý đáp án:** Viết ở cuối dòng `// @highlight type=highlighted`. Vì không có `substring`/`regex`, cả dòng được chọn. Màu chính xác do stylesheet điều khiển.

### Bài 2 — Sự khác nhau giữa các kiểu

Xét hai dòng:

~~~java
String normalized = input.strip(); // @highlight substring="strip" type=italic
boolean empty = normalized.isBlank(); // @highlight substring="isBlank" type=bold
~~~

**Đáp án:** Chỉ `strip` nhận class `italic` và chỉ `isBlank` nhận class `bold`. Đổi `type` chỉ thay đổi loại trình bày, không thay đổi các đoạn chữ mà `substring` đã chọn.

### Bài 3 — Khi bỏ qua `type`

~~~java
int attempts = 3; // @highlight substring="attempts"
~~~

**Đáp án:** `attempts` được nhấn theo kiểu mặc định của standard doclet, tức `bold`. Nó không được tự hiểu là `highlighted`.

### Bài 4 — Vùng nhiều dòng

~~~java
// @highlight region="validation" substring="valid" type=bold :
boolean valid = input != null;
if (valid) {
    System.out.println("valid");
}
// @end region="validation"
System.out.println("done");
~~~

**Đáp án:** Những đoạn chữ khớp `valid` trong region `validation` được làm nổi bằng `bold`: tên `valid` ở khai báo, tên `valid` ở điều kiện, và chữ `valid` trong string literal. Dòng cuối có `"done"` nằm ngoài region; marker điều khiển bị lược khỏi khối mã. `substring` nhận diện văn bản nên không phân biệt tên biến với string literal.

### Bài 5 — Chọn kiểu cho người đọc

Trong tài liệu hướng dẫn người dùng tránh truyền chuỗi rỗng vào API, hãy chọn một trong hai cách sau và giải thích vì sao:

~~~java
boolean invalid = input.isBlank(); // @highlight substring="isBlank" type=bold
~~~

~~~java
if (input.isBlank()) { // @highlight type=highlighted
~~~

**Đáp án tham khảo:** Cả hai đều hợp lý nhưng mang trọng tâm khác nhau. Khi đang giải thích **API nào cần gọi**, nên nhấn `isBlank`. Khi đang giải thích **bước kiểm tra phải có trước xử lý**, nhấn dòng `if` rõ hơn. Tiêu chí lựa chọn là ý định truyền đạt, không có một kiểu cố định cho mọi tình huống.

## Tổng kết

- `@highlight` hỗ trợ ba `type` hợp lệ: **`bold`, `italic`, `highlighted`**.
- `type` xác định **kiểu trình bày**, còn `substring`, `regex`, dòng hiện tại và `region` xác định **phần mã được chọn**.
- Khi bỏ `type`, standard doclet dùng **`bold`** làm mặc định.
- Mỗi tên `type` được thể hiện dưới dạng **CSS class**; ngoại hình thực tế phụ thuộc stylesheet Javadoc và cấu hình theme của dự án.
- Chọn kiểu theo mục tiêu học tập và kiểm tra bằng trang HTML do `javadoc` sinh ra. Đây là hành vi tài liệu còn áp dụng trên các JDK hiện đại.

## Nguồn tham khảo chính thức

1. [Oracle — JavaDoc Documentation Comment Specification, JDK 26, mục Highlighting](https://docs.oracle.com/en/java/javase/26/docs/specs/javadoc/doc-comment-spec.html#snippet): các giá trị `type` hợp lệ, cách chọn phạm vi và chuyển kiểu sang CSS class.
2. [Oracle — JavaDoc Output Generated by the Standard Doclet, JDK 25, mục Snippets](https://docs.oracle.com/en/java/javase/25/docs/specs/javadoc/std-doclet-output.html#snippets): CSS class `bold`, `italic`, `highlighted` trong HTML.
3. [Oracle — JavaDoc CSS Themes, JDK 25](https://docs.oracle.com/en/java/javase/25/javadoc/javadoc-css-themes.html): tùy chỉnh style bằng `--add-stylesheet` và theme.
4. [Oracle Java Magazine — Snippets add a lot of value to Java’s Javadoc facility](https://blogs.oracle.com/javamagazine/java-javadoc-snippet/): ví dụ thực tế và kiểu tô nổi bật mặc định `bold`.
5. [OpenJDK — JEP 413: Code Snippets in Java API Documentation](https://openjdk.org/jeps/413): nền tảng tính năng snippet trong Java 18.
