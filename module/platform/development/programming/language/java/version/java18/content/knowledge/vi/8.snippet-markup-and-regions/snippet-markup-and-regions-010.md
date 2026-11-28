# Dấu hai chấm ở cuối markup comment để áp dụng markup cho dòng tiếp theo

## Mục tiêu bài học

Trong `{@snippet}`, markup comment như `@highlight`, `@link` và `@replace` thường được đặt ở cuối dòng mã mà chúng điều khiển. Tuy nhiên, không phải lúc nào cũng có thể chèn comment ở cuối dòng. Một số định dạng chỉ cho phép comment ở đầu dòng; một số vị trí trong Java cũng không cho phép đặt end-of-line comment.

Javadoc cung cấp một cú pháp ngắn: **nếu markup comment kết thúc bằng dấu hai chấm (`:`), các markup tag trong comment được xem như nằm trên dòng ngay sau comment đó**. Quy tắc này vẫn được hỗ trợ trong JDK hiện đại.

Bài học thuộc chương **Markup và region** của module `JAVA_VERSION_JAVA18`. Module tập trung vào những thay đổi Java 18 vẫn hữu ích trên JDK hiện đại, trong đó có snippet trong tài liệu API và cách kiểm chứng đầu ra.

Sau bài học, bạn có thể:

- Phân biệt markup comment mặc định tác động lên dòng hiện tại với comment kết thúc bằng `:` tác động lên dòng kế tiếp.
- Viết đúng cú pháp `@highlight`, `@link` và `@replace` ở dạng comment đứng riêng.
- Dùng dấu hai chấm trong snippet có ngôn ngữ chỉ cho phép comment ở đầu dòng, chẳng hạn file `.properties`.
- Hiểu vì sao cú pháp này hữu ích khi comment dài hoặc không thể đặt comment cuối dòng.
- Phân biệt dấu hai chấm kết thúc markup comment với dấu hai chấm mở nội dung `{@snippet : ...}`.
- Biết khi nào cần dùng region thay cho cú pháp áp dụng lên một dòng kế tiếp.
- Kiểm tra nội dung thực tế bằng HTML do `javadoc` sinh ra.

## 1. Quy tắc mặc định: markup comment áp dụng lên dòng chứa comment

Markup comment là comment cuối dòng chứa một hoặc nhiều markup tag. Với cú pháp thông thường, các tag tác động lên **dòng mã có comment**.

Ví dụ:

~~~java
/**
 * Làm nổi bật tên method ngay trên dòng có lời gọi:
 * {@snippet :
 *     String normalized = input.strip(); // @highlight substring="strip"
 * }
 */
public class CurrentLineMarkupDoc {
}
~~~

Dòng mã được hiển thị trong Javadoc:

~~~java
String normalized = input.strip();
~~~

Phần `strip` được làm nổi bật. Comment `// @highlight ...` bị lược khỏi mã hiển thị.

Cấu trúc này dễ đọc vì chỉ dẫn nằm cạnh đúng dòng mà nó điều khiển. Nhưng có những tình huống không thể hoặc không nên viết comment ở cuối dòng mã.

## 2. Kết thúc markup comment bằng `:` để chuyển tác động sang dòng kế tiếp

Nếu markup comment kết thúc bằng dấu hai chấm, Javadoc xử lý các tag như thể chúng được đặt ở **ngay dòng tiếp theo**.

Cú pháp:

~~~java
// @highlight substring="strip" :
String normalized = input.strip();
~~~

Kết quả hiển thị vẫn là:

~~~java
String normalized = input.strip();
~~~

Ở ví dụ này:

- Dòng comment chứa `@highlight` và dấu `:`.
- Dòng kế tiếp chứa mã cần được làm nổi bật.
- `javadoc` xem markup tag như thể nó xuất hiện ở cuối dòng `String normalized = ...;`.
- Comment điều khiển và dấu hai chấm không xuất hiện trong snippet được sinh ra.

Nếu một markup comment chứa nhiều tag, dấu hai chấm chuyển **tất cả các tag trong comment đó** sang dòng kế tiếp; selector và target của từng tag vẫn được giữ nguyên.

### 2.1. So sánh hai cách viết

| Cách viết | Dòng được áp dụng markup |
| --- | --- |
| `String value = input.strip(); // @highlight substring="strip"` | Dòng `String value = ...;` có comment. |
| `// @highlight substring="strip" :` rồi đến dòng mã | Dòng mã ngay sau comment. |

Hai cách có thể tạo cùng kết quả trình bày. Khác biệt nằm ở vị trí đặt markup comment trong source.

### 2.2. Dấu hai chấm phải kết thúc markup comment

Dấu `:` là ký hiệu cú pháp khi nó đứng ở cuối markup comment, sau các tag và thuộc tính. Ví dụ:

~~~java
// @highlight substring="strip" :
String value = input.strip();
~~~

Không nhầm với dấu hai chấm nằm **bên trong giá trị thuộc tính**:

~~~java
String endpoint = "http://example.test"; // @replace substring="http:" replacement="https:"
~~~

Hai dấu hai chấm trong `http:` và `https:` là dữ liệu của thuộc tính, không phải ký hiệu chuyển dòng. Ở ví dụ đầu, comment nằm cuối dòng nên markup mặc định tác động lên chính dòng khai báo. Khi cần chuyển sang dòng kế tiếp, đặt comment riêng và thêm dấu `:` sau toàn bộ thuộc tính:

~~~java
// @replace substring="http:" replacement="https:" :
String endpoint = "http://example.test";
~~~

Quy tắc dễ nhớ: **dấu hai chấm chuyển dòng phải nằm ngoài các giá trị được đặt trong dấu nháy và là ký tự kết thúc markup comment**.

## 3. Dùng với `@highlight`

`@highlight` dùng để làm nổi bật toàn bộ dòng hoặc phần văn bản được chọn bằng `substring`/`regex`. Khi comment đứng riêng, dấu hai chấm khiến chỉ dẫn tác động lên dòng kế tiếp.

### 3.1. Làm nổi bật một chuỗi con

~~~java
/**
 * Nhấn mạnh method dùng để loại bỏ khoảng trắng ở hai đầu:
 * {@snippet :
 *     // @highlight substring="strip" type=bold :
 *     String normalized = input.strip();
 * }
 */
public class HighlightNextLineDoc {
}
~~~

Trong HTML, dòng `String normalized = input.strip();` vẫn hiển thị và phần `strip` được nhấn đậm. Dòng comment điều khiển không được đưa vào khối mã.

### 3.2. Làm nổi bật cả dòng

Nếu không có `substring` hoặc `regex`, toàn bộ dòng kế tiếp được chọn:

~~~java
/**
 * Đây là bước kiểm tra dữ liệu đầu vào:
 * {@snippet :
 *     // @highlight type=highlighted :
 *     if (input == null) {
 *         throw new IllegalArgumentException("input");
 *     }
 * }
 */
public class HighlightWholeNextLineDoc {
}
~~~

Chỉ dòng `if (input == null) {` được làm nổi bật. Các dòng `throw` và dấu đóng khối không tự động nhận cùng kiểu vì markup không khai báo region.

### 3.3. Dùng regex cho dòng kế tiếp

~~~java
/**
 * Làm nổi bật phần literal trong câu lệnh:
 * {@snippet :
 *     // @highlight regex='".*"' type=italic :
 *     System.out.println("ready");
 * }
 */
public class HighlightRegexNextLineDoc {
}
~~~

Regex được áp dụng lên dòng `System.out.println("ready");` ngay sau comment. Phần chuỗi literal `"ready"` được làm nổi bật kiểu nghiêng.

## 4. Dùng với `@link`

`@link` gắn hyperlink lên một đoạn văn bản của snippet. Dấu hai chấm hữu ích khi muốn đặt target dài trên một dòng riêng, tránh làm dòng mã ví dụ quá rộng.

~~~java
/**
 * Phương thức strip loại bỏ khoảng trắng ở hai đầu chuỗi:
 * {@snippet :
 *     // @link substring="strip()" target="java.lang.String#strip()" :
 *     String normalized = input.strip();
 * }
 */
public class LinkNextLineDoc {
}
~~~

Khi tạo Javadoc:

- Dòng mã được hiển thị bình thường.
- Chỉ chữ `strip()` trở thành liên kết.
- Target trỏ đến `String.strip()` trong tài liệu Java SE.
- Comment điều khiển bị lược khỏi khối mã.

Nếu bỏ `substring` và `regex`, toàn bộ dòng kế tiếp sẽ là phần được liên kết. Vì vậy, hãy chỉ rõ selector khi chỉ muốn liên kết tên API thay vì cả câu lệnh.

Dấu hai chấm không thay đổi target, selector hay kiểu liên kết. Nó chỉ thay đổi **dòng mà markup tag áp dụng**.

## 5. Dùng với `@replace`

`@replace` thay văn bản trong snippet hiển thị. Cú pháp dấu hai chấm cho phép đặt chỉ dẫn ở dòng riêng rồi thay nội dung ở dòng tiếp theo.

### 5.1. Thay một literal ở dòng sau

~~~java
/**
 * Giá trị thực tế được lược bỏ trong tài liệu:
 * {@snippet :
 *     // @replace substring='"placeholder"' replacement="..." :
 *     String token = "placeholder";
 * }
 */
public class ReplaceNextLineDoc {
}
~~~

Source chứa literal `"placeholder"` hợp lệ. Javadoc thay literal đó bằng `...` trong HTML:

~~~java
String token = ...;
~~~

Comment điều khiển nằm trên dòng riêng, nhưng nhờ dấu hai chấm, selector vẫn được áp dụng cho dòng khai báo bên dưới.

### 5.2. Thay toàn bộ dòng kế tiếp

Nếu không có selector `substring` hoặc `regex`, toàn bộ dòng ngay sau comment được thay bằng replacement:

~~~java
/**
 * Lược bỏ phần cài đặt chi tiết:
 * {@snippet :
 *     // @replace replacement="..." :
 *     return calculateDetailedResult(input);
 * }
 */
public class ReplaceWholeNextLineDoc {
}
~~~

Kết quả hiển thị:

~~~java
...
~~~

Dấu hai chấm ở cuối comment không tạo một region nhiều dòng. Nó chỉ chuyển markup tag sang **một dòng kế tiếp**. Muốn thay nhiều dòng, dùng `region` và marker `@end`.

## 6. Vì sao cú pháp này hữu ích?

Có ba tình huống chính mà dấu hai chấm giúp viết markup rõ ràng hơn.

### 6.1. Markup comment dài

Một `@link` có thể chứa target dài; `@replace` có thể có cả regex và replacement. Đặt comment ở dòng riêng giúp mã ví dụ không bị kéo dài:

~~~java
/**
 * {@snippet :
 *     // @link substring="of" target="java.util.Optional#of(java.lang.Object)" :
 *     Optional<String> value = Optional.of("ready");
 * }
 */
public class LongMarkupCommentDoc {
}
~~~

Người đọc source dễ thấy chỉ dẫn và dòng mã là hai phần riêng. Javadoc vẫn áp dụng link lên đúng dòng kế tiếp.

### 6.2. Định dạng chỉ cho comment ở đầu dòng

File `.properties` dùng ký tự `#` để bắt đầu comment. Comment này phải xuất hiện ở đầu dòng (sau khoảng trắng), không thể nối vào cuối một dòng thuộc tính như Java `//`.

Vì vậy, hãy dùng dấu hai chấm:

~~~java
/**
 * {@snippet lang="properties" :
 *     # @highlight substring="Main St." :
 *     house.street=Main St.
 *     house.town=AnyTown, USA
 * }
 */
public class PropertiesNextLineDoc {
}
~~~

Kết quả hiển thị:

~~~properties
house.street=Main St.
house.town=AnyTown, USA
~~~

Phần `Main St.` trên dòng đầu được làm nổi bật. Dòng `# @highlight ... :` không xuất hiện trong đầu ra. Cách này dùng đúng cú pháp comment của file properties và áp dụng markup cho dòng tiếp theo.

### 6.3. Vị trí không thể chèn end-of-line comment

Không phải ngôn ngữ hoặc định dạng nào cũng cho phép comment cuối dòng. Ngay cả Java cũng có vị trí mà comment kiểu `//` không thể đặt bên trong nội dung, ví dụ các dòng của text block.

Tài liệu Oracle khuyến nghị dùng region để áp dụng markup cho nội dung trong text block, kể cả khi region chỉ chứa một dòng. Dấu hai chấm là cú pháp bổ sung để xem markup comment như comment cuối dòng của dòng ngay sau nó trong các tình huống phù hợp.

Ví dụ dưới đây đặt markup comment bên ngoài text block, mở region ở dòng khai báo kế tiếp rồi làm nổi bật chữ nằm trong nội dung text block:

~~~java
/**
 * {@snippet :
 *     // @highlight region="textBlock" substring="selected" type=bold :
 *     String message = """
 *         first line
 *         selected value
 *         last line
 *         """;
 *     // @end region="textBlock"
 * }
 */
public class TextBlockMarkupDoc {
}
~~~

Region bắt đầu ở dòng `String message = """` và kết thúc tại marker `@end`. Markup không cần đặt comment vào bên trong các dòng văn bản của text block.

Điểm cần nhớ là dấu hai chấm **không biến một comment thành comment nằm bên trong text block**. Nó chỉ chuyển vị trí logic của markup sang dòng kế tiếp. Khi cấu trúc source không cho phép đặt comment, hãy kiểm tra xem có thể dùng region hay không và xác minh đầu ra trên JDK đang dùng.

## 7. Dấu hai chấm không thay thế region

Dấu hai chấm chỉ chuyển markup tag sang **dòng kế tiếp ngay lập tức**. Nó không tự kéo dài tác động đến những dòng tiếp theo.

Ví dụ:

~~~java
/**
 * Chỉ dòng khai báo được làm nổi bật:
 * {@snippet :
 *     // @highlight substring="value" :
 *     String value = input.strip();
 *     System.out.println(value);
 * }
 */
public class OneNextLineOnlyDoc {
}
~~~

Chỉ dòng `String value = ...;` được xử lý. Dòng `System.out.println(value);` nằm sau dòng mục tiêu nên không thuộc phạm vi của markup này.

Nếu muốn áp dụng một hành động trên nhiều dòng, dùng region:

~~~java
/**
 * Nhấn mọi lần xuất hiện của value trong vùng:
 * {@snippet :
 *     // @highlight region="valueUsage" substring="value" type=bold :
 *     String value = input.strip();
 *     System.out.println(value);
 *     // @end region="valueUsage"
 * }
 */
public class RegionInsteadOfColonDoc {
}
~~~

Ở đây:

- Dấu hai chấm chuyển điểm bắt đầu của markup sang dòng `String value = ...;`.
- Thuộc tính `region="valueUsage"` mở phạm vi nhiều dòng.
- `@end region="valueUsage"` kết thúc vùng.
- Tất cả lần xuất hiện của `value` trong vùng được làm nổi bật.

Như vậy, dấu hai chấm và region có thể **kết hợp**: dấu hai chấm quyết định dòng bắt đầu; region quyết định phạm vi kéo dài đến đâu.

## 8. Phân biệt ba loại dấu hai chấm dễ nhầm

Trong Javadoc snippet, có thể gặp dấu hai chấm ở nhiều vị trí với ý nghĩa khác nhau.

| Cách viết | Ý nghĩa |
| --- | --- |
| `{@snippet : ... }` | Dấu hai chấm mở phần nội dung inline của snippet. |
| `// @highlight substring="x" :` | Dấu hai chấm cuối markup comment chuyển tác động sang dòng kế tiếp. |
| `replacement="http:"` hoặc `target="module/package.Class#method()"` | Dấu hai chấm nằm bên trong giá trị thuộc tính là dữ liệu, không phải ký hiệu chuyển dòng. |

Ví dụ:

~~~java
/**
 * {@snippet :
 *     // @highlight substring="strip" :
 *     String value = input.strip();
 * }
 */
~~~

Dấu hai chấm đầu tiên sau `{@snippet` mở body snippet. Dấu hai chấm thứ hai ở cuối comment `@highlight` chuyển markup sang dòng `String value ...`.

Không được xóa nhầm dấu hai chấm mở snippet khi chỉnh markup comment. Hai dấu này thuộc hai cú pháp khác nhau.

## 9. Các lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Đặt markup ở dòng riêng nhưng không có dấu hai chấm. | Theo mặc định tag tác động lên dòng chứa comment. | Thêm `:` ở cuối markup comment. |
| Đặt dấu hai chấm bên trong giá trị thuộc tính. | Dấu hai chấm trong chuỗi là dữ liệu, không phải dấu kết thúc comment. | Đặt dấu `:` riêng ở cuối comment, ngoài dấu nháy. |
| Nghĩ dấu hai chấm kéo dài tác động qua nhiều dòng. | Nó chỉ chuyển tag sang dòng ngay sau comment. | Dùng `region` và `@end` nếu cần nhiều dòng. |
| Đặt comment kiểu Java `//` vào file properties. | File properties dùng `#` cho comment. | Dùng `# @highlight ... :` ở đầu dòng. |
| Dùng `@highlight` nhưng muốn tạo liên kết. | Mỗi markup tag có chức năng riêng. | Dùng `@link` với `target`. |
| Dùng `@replace` mà không có replacement. | Chỉ dẫn không mô tả văn bản thay thế. | Cung cấp `replacement="..."` hoặc chuỗi rỗng. |
| Cho rằng comment điều khiển xuất hiện trong HTML. | Markup comment hợp lệ bị lược khỏi khối mã hiển thị. | Kiểm tra nội dung snippet được sinh ra. |
| Cho rằng colon thay đổi selector hoặc target. | Colon chỉ thay đổi dòng áp dụng. | Giữ nguyên `substring`, `regex`, `target` và `replacement` theo mục tiêu. |
| Dùng end-of-line comment trong text block. | Comment không thể được đặt như vậy bên trong nội dung text block. | Dùng region hoặc cách tổ chức snippet phù hợp, rồi kiểm tra Javadoc. |

## 10. Quy trình kiểm chứng

Tạo một class đơn giản:

~~~java
/**
 * Ví dụ kiểm tra markup comment kết thúc bằng dấu hai chấm:
 *
 * {@snippet :
 *     // @highlight substring="strip" type=bold :
 *     String normalized = input.strip();
 *
 *     // @replace substring='"placeholder"' replacement="..." :
 *     String token = "placeholder";
 *
 *     // @link substring="isBlank()" target="java.lang.String#isBlank()" :
 *     boolean empty = normalized.isBlank();
 * }
 */
public class NextLineMarkupDoc {
}
~~~

Chạy trong thư mục chứa file:

~~~bash
javadoc -d docs NextLineMarkupDoc.java
~~~

Mở `docs/NextLineMarkupDoc.html` và kiểm tra:

1. `strip` trong dòng khai báo `normalized` được làm nổi bật.
2. Literal `"placeholder"` được thay bằng `...`.
3. `isBlank()` trở thành liên kết đến method tương ứng.
4. Các dòng markup comment và dấu hai chấm kết thúc comment không xuất hiện trong mã hiển thị.
5. Mỗi tag chỉ tác động lên dòng ngay sau nó, không tự áp dụng cho dòng kế tiếp nữa.

Để kiểm tra trường hợp file properties, dùng snippet có `lang="properties"` và comment `#` như ví dụ ở mục 6.2. Xác nhận dòng thuộc tính kế tiếp được làm nổi bật và marker không xuất hiện.

**Cần kiểm tra HTML thực tế** vì đây là cách xác nhận markup đã được gắn vào đúng dòng. Đừng chỉ nhìn source rồi suy luận rằng tag chắc chắn đã tác động đúng.

## 11. Bài tập tự đánh giá

### Bài 1 — Dòng nào được làm nổi bật?

~~~java
// @highlight type=highlighted :
if (input == null) {
    throw new IllegalArgumentException("input");
}
~~~

**Đáp án:** Chỉ dòng `if (input == null) {` được làm nổi bật. Dấu hai chấm chuyển tag sang dòng ngay sau comment; nó không mở phạm vi cho các dòng còn lại.

### Bài 2 — Sửa markup comment

Đoạn sau không làm nổi bật dòng khai báo vì tag nằm riêng:

~~~java
// @highlight substring="strip"
String value = input.strip();
~~~

**Đáp án:** Thêm dấu hai chấm:

~~~java
// @highlight substring="strip" :
String value = input.strip();
~~~

### Bài 3 — Comment trong properties

Muốn làm nổi bật chữ `localhost` trong file properties:

~~~properties
service.host=localhost
~~~

**Đáp án:**

~~~properties
# @highlight substring="localhost" :
service.host=localhost
~~~

Dùng `#` làm ký tự comment và dấu hai chấm ở cuối để áp dụng markup cho dòng thuộc tính ngay sau.

### Bài 4 — Dấu hai chấm nào là dấu chuyển dòng?

~~~java
// @replace substring="http:" replacement="https:"
String endpoint = "http://example.test";
~~~

**Đáp án:** Dấu hai chấm trong `http:` và `https:` nằm trong giá trị thuộc tính, nên không chuyển markup sang dòng sau. Nếu muốn áp dụng lên dòng kế tiếp, viết:

~~~java
// @replace substring="http:" replacement="https:" :
String endpoint = "http://example.test";
~~~

### Bài 5 — Khi nào cần region?

Muốn làm nổi bật cùng một từ trên năm dòng liên tiếp. Chỉ thêm dấu hai chấm vào comment có đủ không?

**Đáp án:** Không. Dấu hai chấm chỉ chuyển markup sang dòng ngay sau. Dùng `region` và `@end` để áp dụng tag trên toàn bộ năm dòng.

## Tổng kết

- Markup comment mặc định tác động lên **dòng chứa comment**.
- Nếu comment kết thúc bằng dấu hai chấm `:`, các markup tag được xem như nằm trên **dòng ngay tiếp theo**.
- Cú pháp này hữu ích khi markup comment dài, khi định dạng chỉ cho comment ở đầu dòng như `.properties`, hoặc khi không thể đặt end-of-line comment ở vị trí cần xử lý.
- Có thể dùng với `@highlight`, `@link` và `@replace`; selector và target vẫn giữ nguyên ý nghĩa.
- Dấu hai chấm chuyển dòng không mở phạm vi nhiều dòng. Dùng `region` và `@end` khi cần áp dụng trên một đoạn.
- Phân biệt dấu hai chấm kết thúc markup comment với dấu hai chấm mở body `{@snippet : ...}` và dấu hai chấm nằm trong giá trị thuộc tính.
- Luôn sinh Javadoc và xem HTML để xác nhận tag đã áp dụng lên đúng dòng.

## Nguồn tham khảo chính thức

1. [Oracle — JavaDoc Guide: Snippets, JDK 26, mục Limitations of End-of-Line Comments](https://docs.oracle.com/en/java/javase/26/javadoc/snippets.html): quy tắc comment kết thúc bằng dấu hai chấm được xử lý như comment của dòng kế tiếp; ví dụ với file properties.
2. [Oracle — JavaDoc Documentation Comment Specification, JDK 24, mục Markup Tags](https://docs.oracle.com/en/java/javase/24/docs/specs/javadoc/doc-comment-spec.html): quy tắc mặc định của markup comment, cú pháp dấu hai chấm, vùng và cách áp dụng tag.
3. [Oracle — JavaDoc Guide, JDK 26, mục Regions](https://docs.oracle.com/en/java/javase/26/javadoc/javadoc-guide.pdf): cách dùng region khi cần tác động lên một dòng hoặc nhiều dòng, kể cả nội dung text block.
4. [OpenJDK — JEP 413: Code Snippets in Java API Documentation](https://openjdk.org/jeps/413): tính năng `{@snippet}` được đưa vào Java 18 và tiếp tục được hỗ trợ trong JDK hiện đại.
