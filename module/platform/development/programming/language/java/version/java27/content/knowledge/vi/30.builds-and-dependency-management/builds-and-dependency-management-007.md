# Javadoc, doc comment Markdown và kiểm tra tài liệu API

Trong Java 27, **tài liệu API là một phần của hợp đồng phần mềm**. Người sử dụng một thư viện cần biết phương thức nhận tham số gì, trả về gì, có chấp nhận **null** không, khi nào ném ngoại lệ, có thực hiện I/O hay không và liệu kết quả có thể được chia sẻ giữa các thread.

Công cụ **javadoc** có trong JDK tạo tài liệu HTML từ mã nguồn Java và các **documentation comments**. Java hiện hành hỗ trợ cả comment truyền thống dạng **/** ... */** và **Markdown documentation comments** bằng các dòng **///** liên tiếp (được giới thiệu trong JDK 23 và vẫn áp dụng trong JDK 27). Công cụ còn có **DocLint** để phát hiện nhiều lỗi về tag, tham chiếu, cấu trúc HTML và nội dung tài liệu bị thiếu.

Bài thuộc chương **Build và quản lý phụ thuộc** của học phần **Java 27 và các kiến thức liên quan**. Trọng tâm là xây dựng tài liệu API có thể **sinh được, kiểm tra được và phát hành cùng phiên bản thư viện**, chỉ sử dụng những khả năng còn áp dụng hiện nay.

Mục tiêu học tập:

1. Viết đúng cú pháp Javadoc truyền thống và Markdown **///**.
2. Biết dùng mô tả, tag tham số, giá trị trả về, ngoại lệ và liên kết API.
3. Hiểu cách **{@snippet}**, **{@inheritDoc}**, package/module docs hoạt động.
4. Sinh tài liệu bằng javadoc CLI, Maven và Gradle.
5. Bật DocLint và chính sách warning-as-error trong CI.
6. Biết giới hạn của kiểm tra tự động: tài liệu build thành công chưa chắc đúng nghiệp vụ.

## 1. Tại sao Javadoc thuộc quy trình build?

Mã Java có thể biên dịch đúng nhưng vẫn tạo một API khó dùng:

~~~java
public int retry(int attempts) {
    return attempts;
}
~~~

Chữ ký trên chưa cho biết **attempts** là tổng số lần thử hay số lần thử lại, có chấp nhận số âm không, và return value biểu diễn điều gì.

Tài liệu tốt mô tả **hành vi quan sát được**, thay vì chỉ lặp lại tên method:

~~~java
/// Trả về số lần thử tối đa sau khi kiểm tra giới hạn.
///
/// Giá trị 0 có nghĩa không thực hiện thử lại.
///
/// @param attempts số lần thử lại được phép, từ 0 đến 10
/// @return số lần thử lại được chấp nhận
/// @throws IllegalArgumentException nếu attempts ngoài khoảng 0..10
public static int retryLimit(int attempts) {
    if (attempts < 0 || attempts > 10) {
        throw new IllegalArgumentException("Invalid retry count");
    }
    return attempts;
}
~~~

Tài liệu trên làm rõ các điều kiện mà caller có thể dựa vào. Nếu triển khai thay đổi hợp đồng, **Javadoc phải được cập nhật cùng mã**.

Một pipeline phát hành nên kiểm tra:

- Mã biên dịch với JDK/toolchain mục tiêu.
- Tài liệu HTML được tạo thành công.
- Các Javadoc tags và liên kết nội bộ hợp lệ.
- Không có warning mới theo chính sách.
- Ví dụ công khai khớp chữ ký API hiện tại.
- Artifact tài liệu được gắn với đúng phiên bản thư viện.

Javadoc không thay thế unit test, nhưng là một **quality gate** hữu ích trong build.

## 2. Phân biệt comment thông thường và documentation comment

Ba dạng comment có ý nghĩa khác nhau:

~~~java
// Ghi chú cho người đọc mã; không phải Javadoc.
public void refresh() {}

/* Block comment thông thường; cũng không phải Javadoc. */
public void rebuild() {}

/**
 * Documentation comment truyền thống.
 */
public void validate() {}

/// Documentation comment Markdown.
public void publish() {}
~~~

Documentation comment phải đặt **ngay trước phần khai báo**, trước annotation, modifier hoặc phần còn lại của khai báo.

~~~java
/// Biểu diễn đối tượng dưới dạng chuỗi.
@Override
public String toString() {
    return "Example";
}
~~~

Nếu một comment nằm sau khi khai báo đã bắt đầu, nó có thể bị bỏ qua. Nếu có nhiều documentation comments trước cùng một khai báo, công cụ dùng comment gần khai báo nhất theo quy tắc đặc tả, **không tự ghép các comment rời nhau**.

Trong cùng một source file có thể dùng cả dạng truyền thống lẫn Markdown, nhưng mỗi khai báo nên có **một comment rõ ràng**.

## 3. Comment truyền thống /** ... */

Dạng Javadoc lâu đời vẫn được hỗ trợ đầy đủ trong Java 27:

~~~java
/**
 * Chuẩn hóa tên người dùng.
 *
 * <p>Loại bỏ khoảng trắng hai đầu bằng String.strip().
 *
 * @param name tên đầu vào, không được null
 * @return tên sau khi chuẩn hóa
 * @throws NullPointerException nếu name là null
 * @throws IllegalArgumentException nếu tên sau chuẩn hóa rỗng
 */
public static String normalizeName(String name) {
    String result = java.util.Objects.requireNonNull(name).strip();
    if (result.isEmpty()) {
        throw new IllegalArgumentException("empty name");
    }
    return result;
}
~~~

Các thành phần:

- Mô tả chính ở đầu comment.
- Các đoạn giải thích bằng văn bản/HTML.
- **@param** cho tham số.
- **@return** cho giá trị trả về.
- **@throws** cho điều kiện lỗi có ý nghĩa với caller.

Trong traditional comment, HTML có thể được dùng cho paragraph, bảng và những thành phần cần thiết. Tuy nhiên, cú pháp HTML dài có thể làm code khó đọc, đặc biệt khi cần chèn đoạn mã nhiều dòng.

Một block comment **không thể chứa chuỗi kết thúc comment** ở phần nội dung mà không làm thay đổi cấu trúc comment. Dạng Markdown /// tránh giới hạn này và cho phép viết ví dụ trực tiếp hơn.

**Không cần chuyển đổi mọi comment cũ sang ///** nếu tài liệu truyền thống đã rõ ràng và hoạt động tốt.

## 4. Markdown documentation comments bằng ///

Từ **JDK 23**, standard doclet hỗ trợ chuỗi dòng liên tiếp bắt đầu bằng ba dấu gạch chéo:

~~~java
/// Chuẩn hóa tên người dùng.
///
/// Loại bỏ khoảng trắng hai đầu bằng [String#strip()].
///
/// @param name tên không được null
/// @return tên đã chuẩn hóa
/// @throws NullPointerException nếu name là null
/// @throws IllegalArgumentException nếu kết quả rỗng
public static String normalizeName(String name) {
    String result = java.util.Objects.requireNonNull(name).strip();
    if (result.isEmpty()) {
        throw new IllegalArgumentException("empty name");
    }
    return result;
}
~~~

Dạng này là **Java documentation comment có nội dung Markdown**, không phải một file Markdown bên ngoài. Standard doclet xử lý các dòng ///, phần Markdown và các tag JavaDoc để sinh HTML.

### Dòng trống phải bắt đầu bằng ///

Đúng:

~~~java
/// Câu tóm tắt.
///
/// Một đoạn giải thích thứ hai.
public void run() {}
~~~

Sai nếu mong gộp thành một comment:

~~~java
/// Đoạn thứ nhất bị tách rời.

/// Chỉ đoạn thứ hai nằm trong comment gần khai báo nhất.
public void run() {}
~~~

Dòng trống hoàn toàn không có **///** sẽ tách chuỗi documentation comments. Phần trước có thể trở thành **dangling doc comment** và không được gắn với khai báo.

**Quy tắc:** mọi dòng của một Markdown documentation comment, kể cả dòng trống để phân đoạn, đều có tiền tố **///**.

### Không dùng // khi muốn viết Javadoc

Một ghi chú dạng **//** vẫn là comment Java thông thường. Chỉ ba dấu gạch chéo được nhận dạng theo cú pháp Markdown documentation comment ở đây.

## 5. Những phần Markdown có thể dùng

Standard doclet của Java 27 hỗ trợ **CommonMark**, các mở rộng dành cho JavaDoc và **bảng pipe đơn giản theo GFM**.

Ví dụ:

~~~java
/// Định dạng một chuỗi để hiển thị.
///
/// **Quy tắc:**
///
/// - Kết quả không bao giờ là `null`.
/// - Loại bỏ khoảng trắng hai đầu.
/// - Không thay đổi chữ hoa/chữ thường.
///
/// | Input | Output |
/// | --- | --- |
/// | `" A "` | `"A"` |
/// | `"B"` | `"B"` |
///
/// @param value chuỗi không được null
/// @return chuỗi đã chuẩn hóa
public static String format(String value) {
    return java.util.Objects.requireNonNull(value).strip();
}
~~~

Có thể dùng:

- Các đoạn văn, chữ đậm, chữ nghiêng.
- Danh sách có thứ tự hoặc không thứ tự.
- Inline code và fenced code blocks.
- Headings và liên kết.
- Bảng pipe đơn giản.
- JavaDoc inline/block tags.

**Không mặc định mọi tính năng Markdown của một dịch vụ website đều xuất hiện y hệt trong Javadoc.** Hãy xem HTML cuối cùng, đặc biệt với bảng, đoạn mã và liên kết phức tạp.

## 6. Summary: câu đầu ngắn gọn, chính xác

Câu tóm tắt đầu được dùng trong danh sách class/method và nhiều vị trí điều hướng của tài liệu.

Ví dụ chưa tốt:

~~~java
/// Đây là method xử lý dữ liệu.
public String convert(String input) {
    return input;
}
~~~

Tốt hơn:

~~~java
/// Chuẩn hóa mã định danh thành chuỗi không chứa khoảng trắng đầu và cuối.
///
/// Không thay đổi chữ hoa/chữ thường của các ký tự còn lại.
///
/// @param input mã đầu vào không được null
/// @return mã định danh sau chuẩn hóa
public String convert(String input) {
    return java.util.Objects.requireNonNull(input).strip();
}
~~~

Với comment Markdown, summary còn chịu ảnh hưởng bởi ranh giới block Markdown đầu tiên. Không đặt heading hoặc danh sách trước khi có mô tả ngắn nếu điều đó khiến summary khó hiểu.

JavaDoc còn có inline tag **{@summary ...}**:

~~~java
/// {@summary Tạo một cấu hình bất biến với các giá trị mặc định hợp lệ.}
///
/// Không mở kết nối mạng ở bước tạo.
public Config createConfig() {
    return new Config();
}
~~~

Ví dụ giả định kiểu **Config** tồn tại. Tag summary chỉ tác động tới tài liệu, không thay đổi hành vi của method.

## 7. Các block tag quan trọng

**Block tag** bắt đầu bằng ký hiệu **@** ở đầu một dòng nội dung comment, sau khi đã bỏ tiền tố comment/whitespace.

| Tag | Mục đích |
|---|---|
| **@param name** | Mô tả tham số method, constructor hoặc record component |
| **@param <T>** | Mô tả tham số kiểu generic |
| **@return** | Mô tả giá trị trả về |
| **@throws ExceptionType** | Giải thích điều kiện ném ngoại lệ |
| **@exception ExceptionType** | Bí danh của @throws vẫn được hỗ trợ |
| **@since** | Phiên bản API mà phần tử được giới thiệu |
| **@see** | Liên kết tài liệu/phần tử liên quan |
| **@deprecated** | Giải thích API đã deprecated và cách thay thế |
| **@apiNote** | Lưu ý hướng đến người sử dụng API |
| **@implSpec** | Đặc tả dành cho implementation |
| **@implNote** | Ghi chú về cách triển khai |

Ví dụ:

~~~java
/// Tìm đơn hàng theo mã mà không thay đổi trạng thái.
///
/// @param id mã đơn hàng không được rỗng
/// @return Optional chứa đơn hàng nếu có, ngược lại là Optional rỗng
/// @throws IllegalArgumentException nếu id rỗng
/// @since 2.0
/// @see java.util.Optional
public java.util.Optional<Order> findOrder(String id) {
    return java.util.Optional.empty();
}
~~~

Kiểu **Order** được giả định tồn tại; đoạn code minh họa cách mô tả API.

**Main description phải đi trước block tags.** Nội dung sau block tag thường được xem là phần của tag đó đến khi có tag tiếp theo hoặc hết comment, không tự quay lại thành phần mô tả chính.

## 8. Viết @param và @return có giá trị sử dụng

Comment kiểu **@param count số lượng** thường quá ngắn nếu caller cần biết hợp đồng:

~~~java
/// Thêm sản phẩm vào giỏ hàng.
///
/// Nếu sản phẩm đã có, số lượng mới được cộng vào số hiện tại.
///
/// @param product sản phẩm không được null
/// @param count số đơn vị thêm, phải lớn hơn 0
/// @throws NullPointerException nếu product là null
/// @throws IllegalArgumentException nếu count không dương
public void add(Product product, int count) {}
~~~

Ví dụ giả định class **Product** và implementation đầy đủ đã tồn tại. Trong thực tế, tài liệu phải phản ánh đúng những kiểm tra được thực hiện.

Một @param **timeoutMillis** cần ghi rõ đơn vị là mili giây và ý nghĩa của số 0 hoặc số âm nếu được phép.

**@return** nên mô tả:

- Có thể trả **null** hay không.
- Trả danh sách rỗng hay ném exception nếu không có dữ liệu.
- Giá trị có được sắp xếp không.
- Trả bản sao, view hay đối tượng dùng chung.
- Giá trị còn hợp lệ trong bao lâu.
- Kết quả có tính nguyên tử hay chỉ là ước lượng.

Ví dụ:

~~~java
/// Trả về một danh sách không cho phép chỉnh sửa qua API của nó.
///
/// @return danh sách không null, có thể rỗng
public java.util.List<String> names() {
    return java.util.List.of("Lan", "Minh");
}
~~~

## 9. @throws mô tả điều kiện lỗi, không chỉ liệt kê tên

Một API tốt phải giúp caller biết **khi nào cần xử lý lỗi**:

~~~java
/// Chia hai số nguyên theo phép chia nguyên.
///
/// @param numerator số bị chia
/// @param denominator số chia
/// @return thương theo quy tắc chia nguyên Java
/// @throws ArithmeticException nếu denominator bằng 0
public static int divide(int numerator, int denominator) {
    return numerator / denominator;
}
~~~

Có thể tài liệu hóa cả checked và unchecked exception khi chúng là một phần hợp đồng cần biết.

Đừng liệt kê mọi lỗi JVM có thể ném trong mọi hoàn cảnh. Ưu tiên những ngoại lệ có ý nghĩa với caller và những giới hạn đặc thù của API.

Khi implementation đổi từ trả giá trị fallback sang ném exception, comment **@throws** và **@return** phải thay đổi cùng method.

## 10. Generic API và record components

Đối với generic, dùng **@param <T>**:

~~~java
/// Trả về phần tử đầu nếu danh sách không rỗng.
///
/// @param <T> kiểu phần tử
/// @param values danh sách không được null và không chứa null
/// @return Optional chứa phần tử đầu hoặc Optional rỗng
/// @throws NullPointerException nếu values là null
public static <T> java.util.Optional<T> first(
        java.util.List<T> values) {

    java.util.Objects.requireNonNull(values);

    return values.isEmpty()
            ? java.util.Optional.empty()
            : java.util.Optional.of(values.get(0));
}
~~~

Lời hứa “không chứa null” là **tiền điều kiện của caller** trong ví dụ; nếu phần tử đầu là null, **Optional.of(...)** sẽ ném NullPointerException. Đừng đưa tiền điều kiện mà implementation không tuân theo hay caller không thể biết.

Với record, **@param** mô tả các component:

~~~java
import java.math.BigDecimal;

/// Đại diện cho một khoản tiền.
///
/// @param amount số tiền không được null
/// @param currency mã đơn vị tiền tệ không được rỗng
public record Money(BigDecimal amount, String currency) {}
~~~

**Documentation comment không tự thực thi các ràng buộc.** Nếu muốn record thực sự từ chối null hoặc currency rỗng, phải có validation trong constructor phù hợp.

## 11. Inline tags và liên kết đến API Java

**Inline tags** nằm trong phần mô tả:

| Tag | Vai trò |
|---|---|
| **{@link ...}** | Tạo liên kết đến class, method, field hoặc phần tử Java |
| **{@linkplain ...}** | Liên kết với nhãn văn bản thông thường |
| **{@code ...}** | Hiển thị code literal |
| **{@literal ...}** | Hiển thị nội dung literal |
| **{@value ...}** | Hiển thị compile-time constant phù hợp |
| **{@summary ...}** | Quy định summary rõ ràng |
| **{@inheritDoc}** | Kế thừa tài liệu từ supertype theo quy tắc JavaDoc |
| **{@snippet ...}** | Nhúng code sample theo cú pháp snippets |

Ví dụ truyền thống:

~~~java
/**
 * Chuẩn hóa chuỗi bằng {@link String#strip()}.
 *
 * Trả về {@code ""} nếu input chỉ có khoảng trắng.
 *
 * @param input chuỗi không được null
 * @return chuỗi đã chuẩn hóa
 */
public static String trimText(String input) {
    return input.strip();
}
~~~

Với Markdown, có thể dùng code span và liên kết dạng ngắn:

~~~java
/// Chuẩn hóa chuỗi bằng [String#strip()].
///
/// Trả về `""` nếu input chỉ có khoảng trắng.
///
/// @param input chuỗi không được null
/// @return chuỗi đã chuẩn hóa
public static String trimText(String input) {
    return input.strip();
}
~~~

Đừng dùng **{@value}** để mong Javadoc chạy một method và tính kết quả runtime. Tag này dành cho trường hợp hằng phù hợp được hỗ trợ.

## 12. Markdown reference links tới chương trình

Standard doclet JDK 27 hỗ trợ những liên kết Markdown tới phần tử Java, chẳng hạn:

~~~java
/// Xem [String], [String#strip()] và [java.util.Optional].
///
/// Có thể sử dụng [java.base/] để tham chiếu module Java cơ bản.
public void inspect() {}
~~~

Các ví dụ thường gặp:

- **[String]** — type.
- **[String#strip()]** — method.
- **[String#CASE_INSENSITIVE_ORDER]** — field.
- **[java.util]** — package.
- **[java.base/]** — module.

Dạng có nhãn rõ:

~~~java
/// Dùng [phương thức chuẩn hóa][String#strip()] cho chuỗi đầu vào.
public void normalize() {}
~~~

Nếu tên tham chiếu trông hợp lệ nhưng class/method không tồn tại, Javadoc có thể phát hiện lỗi **reference**. Hãy sửa link hoặc cấu hình dependency resolution thay vì bỏ hoàn toàn kiểm tra.

### Link ngoài

~~~java
/// Xem [JavaDoc Guide](https://docs.oracle.com/en/java/javase/27/javadoc/).
public void help() {}
~~~

Liên kết bên ngoài cần được đánh giá theo phiên bản dependency và bảo trì định kỳ. **DocLint không phải công cụ kiểm tra mọi URL còn truy cập được qua HTTP**.

## 13. @since và version API

**@since** thông thường nói về **phiên bản của thư viện/API**, không tự động là **27** chỉ vì ứng dụng dùng Java 27.

~~~java
/// Chuyển chuỗi thành dạng mã hóa URL.
///
/// @param value chuỗi không được null
/// @return chuỗi đã mã hóa
/// @since 1.4
/// @see java.net.URLEncoder
public String encode(String value) {
    return value;
}
~~~

Nếu method được giới thiệu ở bản 1.4 của chính thư viện, tài liệu nên ghi 1.4 theo chính sách versioning. JDK 27 là môi trường thực thi, không phải thời điểm mọi API của bạn được thêm.

Nếu người dùng vẫn sử dụng các phiên bản cũ của thư viện, cần giữ **API docs tương ứng phiên bản**, không chỉ một tài liệu “latest” luôn trỏ tới code mới.

## 14. Deprecated API cần cả annotation và mô tả thay thế

Ví dụ:

~~~java
/**
 * Tạo báo cáo theo định dạng cũ.
 *
 * @deprecated Dùng {@link #render(String)} thay thế.
 */
@Deprecated(since = "2.0", forRemoval = false)
public String createReport(String input) {
    return render(input);
}
~~~

Ví dụ giả định class có method **render(String)** phù hợp.

- **@Deprecated** là Java annotation để compiler và công cụ nhận diện.
- **@deprecated** là JavaDoc block tag giải thích lý do và hướng chuyển đổi.
- **forRemoval=true** báo chủ sở hữu dự định loại bỏ API, không có nghĩa API đã bị xóa.

Dù API deprecated, tài liệu vẫn có giá trị cho người dùng đang chuyển đổi. Không xóa toàn bộ hướng dẫn của API cũ trước khi có cơ chế migration phù hợp.

## 15. Kế thừa tài liệu bằng {@inheritDoc}

Một method overriding có thể sử dụng tài liệu từ interface hoặc superclass:

~~~java
interface Formatter {
    /// Định dạng văn bản thành chuỗi hiển thị.
    ///
    /// @param input chuỗi không được null
    /// @return chuỗi hiển thị
    String format(String input);
}

final class UpperFormatter implements Formatter {
    /// {@inheritDoc}
    @Override
    public String format(String input) {
        return input.toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

Lưu ý:

- **@Override** dành cho kiểm tra ghi đè của compiler.
- **{@inheritDoc}** yêu cầu Javadoc dùng phần tài liệu kế thừa theo quy tắc tìm kiếm phù hợp.
- Không lạm dụng inheritDoc khi implementation có điều kiện bổ sung quan trọng.
- Với nhiều interface, cách chọn nguồn tài liệu theo một thứ tự xác định, không đơn giản lấy comment bất kỳ.

Nếu một implementation có deadline, side effect hoặc chính sách thread riêng, hãy bổ sung thông tin đó vào tài liệu thay vì chỉ dùng inheritDoc.

## 16. @apiNote, @implSpec và @implNote

Ba block tag giúp tách góc nhìn:

| Tag | Người đọc chính | Ví dụ nội dung |
|---|---|---|
| **@apiNote** | Người gọi API | Điều kiện dùng, lưu ý vận hành |
| **@implSpec** | Người triển khai API | Yêu cầu implementation phải tuân thủ |
| **@implNote** | Người bảo trì implementation | Ghi chú lựa chọn kỹ thuật hiện tại |

Ví dụ:

~~~java
/// Xử lý yêu cầu đầu vào theo hợp đồng của dịch vụ.
///
/// @param request yêu cầu không được null
/// @return kết quả hợp lệ
/// @apiNote Có thể gọi phương thức này nhiều lần với cùng dữ liệu.
/// @implSpec Implementation phải trả một kết quả không được null.
/// @implNote Implementation mặc định có thể dùng bộ đệm trung gian.
public Result process(Request request) {
    return new Result();
}
~~~

Đoạn mã giả định kiểu **Result** và **Request** tồn tại. Phần mô tả chỉ minh họa cách tổ chức tags.

**Một yêu cầu bắt buộc cho mọi implementation không nên chỉ ghi trong @implNote.** Phân biệt hợp đồng với chi tiết triển khai.

## 17. Code blocks trong Markdown documentation comment

Fenced code block giúp ví dụ ngắn dễ đọc:

~~~java
/// Tạo lời chào cho tên đã cung cấp.
///
/// Ví dụ:
///
/// ~~~java
/// String message = Greeter.greet("Lan");
/// System.out.println(message);
/// ~~~
///
/// @param name tên không được null
/// @return lời chào
public static String greet(String name) {
    return "Xin chào, " + name;
}
~~~

Standard doclet sẽ hiển thị code trong HTML. Tuy nhiên, **một fenced code block không được javadoc tự biên dịch hoặc chạy**.

Nếu ví dụ trỏ tới method đã đổi tên, HTML vẫn có thể được tạo thành công. Với code sample quan trọng, nên có kiểm thử/biên dịch riêng trong dự án thực tế.

## 18. {@snippet} và ví dụ có cấu trúc

**{@snippet ...}** là inline tag được hỗ trợ trong Javadoc hiện hành để trình bày code sample.

~~~java
/// Trả về tên đã chuẩn hóa.
///
/// {@snippet :
///     String normalized = "  Lan  ".strip();
///     System.out.println(normalized);
/// }
///
/// @return chuỗi đã chuẩn hóa
public String normalizedName() {
    return "Lan";
}
~~~

Snippet còn hỗ trợ các khả năng như lựa chọn vùng code và định dạng hiển thị theo cú pháp của standard doclet.

**Javadoc không tự chạy snippet như unit test**. Một snippet hiển thị đúng không chứng minh nó biên dịch, có output đã ghi hoặc còn hợp lệ sau khi refactor.

Khi tài liệu chứa snippet quan trọng:

1. Dùng API public thực sự tồn tại.
2. Cập nhật cùng commit khi chữ ký thay đổi.
3. Cân nhắc source/example có thể được compile/test.
4. Không dùng token hoặc bí mật thật trong ví dụ.
5. Xem kết quả HTML sau khi sinh.

## 19. External snippet và doc-files

Với ví dụ dài, có thể tổ chức source dùng cho snippet ở file bên ngoài và tham chiếu bằng tag thích hợp:

~~~java
/// Cách dùng:
///
/// {@snippet file="GreeterExamples.java" region="basic"}
public final class Greeter {
    // Triển khai API.
}
~~~

Đây chỉ là cú pháp minh họa. Để hoạt động, source snippet phải tồn tại trong vị trí được javadoc hỗ trợ, region được đánh dấu theo cú pháp của snippet và đường dẫn nguồn được cấu hình phù hợp (ví dụ qua **--snippet-path** khi cần).

Với tài liệu dài ở mức package, standard doclet còn xử lý những file **.md** hoặc **.html** đặt trong thư mục **doc-files** theo quy tắc tương ứng:

~~~text
src/main/java/
  com/example/api/
    package-info.java
    Greeter.java
    doc-files/
      usage.md
      format.html
~~~

**Đây là cây thư mục minh họa**, không yêu cầu tạo thêm file trong nhiệm vụ viết bài Markdown này.

## 20. Tài liệu package bằng package-info.java

API không chỉ gồm từng method riêng lẻ. Người dùng cần hiểu mục đích chung của một package.

Ví dụ **src/main/java/com/example/api/package-info.java**:

~~~java
/// Cung cấp các thao tác định dạng chuỗi.
///
/// Package này chứa các phép xử lý không thực hiện I/O
/// và không chia sẻ trạng thái có thể thay đổi.
///
/// ## Bắt đầu
///
/// Xem [com.example.api.Greeter] để tạo lời chào.
///
/// @since 1.0
package com.example.api;
~~~

Một tài liệu package hữu ích nên nêu:

- Những bài toán package giải quyết.
- Các class/interface public nên bắt đầu từ đâu.
- Quy tắc chung về nullability và exception.
- Quyền sở hữu tài nguyên nếu package chứa API I/O.
- Những phụ thuộc hoặc yêu cầu cấu hình quan trọng.

**package-info.java** là cách hiện hành để ghi package documentation. Một dự án cũ có thể có **package.html**, nhưng không cần tạo package.html mới cho một project hiện đại.

## 21. Module docs và JPMS

Nếu dự án dùng Java Platform Module System, **module-info.java** có thể mang documentation comment:

~~~java
/// Cung cấp các API định dạng chuỗi cho ứng dụng Java.
///
/// Chỉ các package được export mới thuộc phạm vi
/// API module đã công khai.
///
/// @since 1.0
module com.example.library {
    exports com.example.api;
}
~~~

Khi tạo tài liệu:

- Mô tả ý nghĩa module và package công khai.
- Cấu hình module path/source path đúng.
- Không xuất nhầm package nội bộ chỉ để nó xuất hiện trong HTML.
- Không nhầm tùy chọn hiển thị Javadoc với quyền truy cập thực tế trong JVM.

**exports**, visibility của class và tùy chọn hiển thị tài liệu phục vụ những mục đích khác nhau. Việc ẩn một class khỏi tài liệu không tự biến class đó thành private.

## 22. Sinh HTML bằng công cụ javadoc

Ví dụ source nằm dưới **src/main/java** và package chính là **com.example.api**:

~~~text
javadoc -d build/apidocs -encoding UTF-8 -sourcepath src/main/java -subpackages com.example.api
~~~

Ý nghĩa:

| Tùy chọn | Tác dụng |
|---|---|
| **-d** | Chọn thư mục output HTML |
| **-encoding UTF-8** | Đọc mã nguồn chứa tiếng Việt theo UTF-8 |
| **-sourcepath** | Thư mục gốc chứa source cho các package |
| **-subpackages** | Xử lý package chỉ định và các subpackage |
| **--release 27** | Chọn mức Java platform/source phù hợp khi dùng Javadoc JDK 27 |
| **-public** | Chọn phạm vi chỉ public API |
| **-protected** | Phạm vi public và protected, thường là mặc định |
| **-package** | Bao gồm package-private |
| **-private** | Bao gồm cả thành viên private |
| **-link URL** | Kết nối tới tài liệu API bên ngoài |

Có thể chỉ định source file trực tiếp:

~~~text
javadoc -d build/apidocs -encoding UTF-8 src/main/java/com/example/api/Greeter.java
~~~

Khi source có dependencies, cần cấu hình **classpath** hoặc **module path** phù hợp. Một lệnh dựa trên classpath đơn giản không thay thế cấu hình của project modular.

### Kiểm tra JDK/toolchain

~~~text
javadoc --version
javac --version
java --version
~~~

Nếu source dùng **///**, Javadoc chạy trong CI phải là JDK có hỗ trợ Markdown documentation comments. Không để local dùng JDK 27 nhưng máy build dùng JDK quá cũ.

## 23. DocLint kiểm tra những gì?

**DocLint** là cơ chế phát hiện nhiều vấn đề cấu trúc và tham chiếu trong documentation comments.

| Nhóm | Ví dụ vấn đề |
|---|---|
| **missing** | Thiếu comment hoặc thiếu @param/@return cần thiết |
| **reference** | @link/@see không tìm thấy phần tử, tên tag sai |
| **syntax** | Cú pháp comment không hợp lệ |
| **html** | Một số lỗi về cấu trúc HTML |
| **accessibility** | Thiếu thông tin cần thiết cho khả năng truy cập, như alt text |

Bật mọi nhóm:

~~~text
javadoc -d build/apidocs -Xdoclint:all -sourcepath src/main/java -subpackages com.example.api
~~~

Các kiểm tra DocLint thường được bật theo mặc định trong standard doclet, nhưng **-Xdoclint:all** hữu ích khi cần chính sách CI rõ ràng.

### DocLint không kiểm tra mọi thứ

DocLint **không chứng minh**:

- Example code thực sự biên dịch hoặc chạy đúng.
- Chú thích về thread safety khớp implementation.
- Method luôn trả giá trị được tài liệu mô tả.
- Mọi URL ngoài vẫn còn hoạt động.
- Mọi HTML đều đạt đầy đủ chuẩn và an toàn.
- Người đọc hiểu đúng hợp đồng API.

Dùng DocLint cùng **code review, kiểm thử và kiểm tra artifact HTML**.

## 24. Dùng -Werror để chặn cảnh báo

Khi muốn coi warning Javadoc là lỗi build:

~~~text
javadoc -d build/apidocs -encoding UTF-8 -Xdoclint:all -Werror -sourcepath src/main/java -subpackages com.example.api
~~~

**-Werror** khiến công cụ báo lỗi nếu có warning. Điều này giúp CI không bỏ qua một warning mới về tag hoặc tài liệu public.

### Lộ trình cho dự án cũ

Nếu mã nguồn hiện có quá nhiều comment thiếu, có thể cải tiến theo từng bước:

1. Sửa lỗi tham chiếu và cú pháp nghiêm trọng.
2. Bổ sung tài liệu cho API public quan trọng.
3. Bổ sung @param, @return và @throws.
4. Bật đầy đủ DocLint và warning-as-error.
5. Giữ quality gate từ những lần thay đổi tiếp theo.

Có thể tạm thời dùng:

~~~text
javadoc -Xdoclint:all,-missing -d build/apidocs -sourcepath src/main/java -subpackages com.example.api
~~~

Tùy chọn này giảm kiểm tra nhóm **missing** trong giai đoạn chuyển đổi, không phải thiết kế khuyến nghị lâu dài cho dự án mới.

**Không dùng -Xdoclint:none như giải pháp mặc định** cho những lỗi do link sai hoặc thiếu hợp đồng. Hãy sửa nguyên nhân.

## 25. Kiểm tra dangling documentation comments khi biên dịch

Nếu comment /// bị tách khỏi khai báo, phần mô tả có thể bị bỏ rơi.

~~~java
/// Đoạn này không còn gắn liền với khai báo.

/// Đoạn gần khai báo hơn.
public void work() {}
~~~

Trong JDK 27, có thể dùng cảnh báo **javac -Xlint:dangling-doc-comments**:

~~~text
javac -Xlint:dangling-doc-comments src/main/java/com/example/api/Greeter.java
~~~

Kiểm tra này bổ sung cho Javadoc DocLint, giúp phát hiện những comment không được dùng như người viết mong đợi.

Không dùng **///** cho ghi chú nội bộ đơn giản trong thân method:

~~~java
// Giải thích một nhánh xử lý khó hiểu.
if (condition) {
    // ...
}
~~~

Chọn comment thông thường khi không muốn tạo API docs.

## 26. Tích hợp Javadoc trong Maven

**Maven Javadoc Plugin** hỗ trợ sinh và đóng gói tài liệu. Một project có thể chạy:

~~~text
mvn javadoc:javadoc
~~~

Ví dụ cấu hình trong **pom.xml**:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-javadoc-plugin</artifactId>
      <version>REPLACE_WITH_VERIFIED_PLUGIN_VERSION</version>
      <configuration>
        <encoding>UTF-8</encoding>
        <doclint>all</doclint>
        <failOnError>true</failOnError>
        <failOnWarnings>true</failOnWarnings>
      </configuration>
      <executions>
        <execution>
          <id>check-api-docs</id>
          <phase>verify</phase>
          <goals>
            <goal>javadoc</goal>
          </goals>
        </execution>
      </executions>
    </plugin>
  </plugins>
</build>
~~~

**REPLACE_WITH_VERIFIED_PLUGIN_VERSION là placeholder bắt buộc thay bằng phiên bản plugin đã được chọn và kiểm chứng**, không phải giá trị có thể chạy nguyên xi. Nên quản lý phiên bản plugin tường minh (hoặc qua pluginManagement của parent POM) để build dễ tái lập.

Các tùy chọn quan trọng:

- **doclint=all:** bật các nhóm kiểm tra.
- **failOnError=true:** lỗi Javadoc làm build thất bại.
- **failOnWarnings=true:** warning Javadoc làm build thất bại theo hỗ trợ của plugin.
- **verify:** phase ví dụ chạy kiểm tra tài liệu trước khi phát hành.

Với cấu hình lifecycle trên:

~~~text
mvn verify
~~~

Maven chạy goal đã cấu hình tại phase verify. Ngoài tài liệu HTML, goal thích hợp như **javadoc:jar** có thể tạo Javadoc artifact để phát hành cùng thư viện.

Khi phát hành source JAR và Javadoc JAR, nên gắn **cùng phiên bản** với binary artifact.

## 27. Tích hợp Javadoc trong Gradle

Với Gradle Java plugin, có task **javadoc**:

~~~text
./gradlew javadoc
~~~

Trên Windows:

~~~text
gradlew.bat javadoc
~~~

Ví dụ **build.gradle** dùng Groovy DSL:

~~~groovy
tasks.withType(Javadoc).configureEach {
    options.encoding = 'UTF-8'
    options.addBooleanOption('Xdoclint:all', true)
    options.addBooleanOption('Werror', true)
    failOnError = true
}
~~~

Ví dụ khai báo toolchain cho Java 27:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(27)
    }
}
~~~

Điều kiện: **phiên bản Gradle thực tế phải hỗ trợ JDK/toolchain được cấu hình** và máy build phải có JDK phù hợp hoặc cơ chế provision toolchain đúng.

Trong multi-project build, cần xác định module nào sinh Javadoc, những package nào được công khai, và task nào chạy trong CI. **Có task javadoc nhưng không chạy nó trước publish** thì chưa có quality gate thực sự.

## 28. Liên kết tới tài liệu dependency và JDK

Khi API public dùng các kiểu của dependency ngoài, người đọc có lợi từ liên kết tới tài liệu đúng phiên bản.

Ví dụ:

~~~text
javadoc -d build/apidocs -link https://docs.oracle.com/en/java/javase/27/docs/api/ -sourcepath src/main/java -subpackages com.example.api
~~~

**-link** yêu cầu công cụ liên kết tới tài liệu API bên ngoài phù hợp.

Lưu ý:

- Link tới phiên bản thư viện **tương thích với artifact hiện tại**.
- Cấu hình dependency classpath/module path để Javadoc phân giải được kiểu.
- Nếu CI offline, cần chính sách dùng tài liệu/link được cache hoặc cấu hình offline phù hợp.
- Có thể cần kiểm tra URL bên ngoài định kỳ vì DocLint không xác minh mọi đích HTTP.

Không trỏ API của dependency phiên bản 1.x tới tài liệu bản 3.x nếu hợp đồng đã thay đổi.

## 29. Document những ràng buộc khó thấy: null, side effect và lifecycle

Một API có thể rất ngắn nhưng đòi hỏi nhiều thông tin về cách sử dụng đúng.

### API bất đồng bộ

~~~java
/// Tải dữ liệu từ một dịch vụ ngoài.
///
/// Future có thể hoàn tất ngoại lệ nếu gặp lỗi mạng.
/// Hủy future trả về không nhất thiết dừng thao tác đang chạy.
///
/// @param id mã yêu cầu không được null
/// @return future không null chứa dữ liệu khi thành công
public java.util.concurrent.CompletableFuture<Data> fetch(String id) {
    return java.util.concurrent.CompletableFuture.failedFuture(
            new UnsupportedOperationException("illustration"));
}
~~~

Ví dụ giả định kiểu **Data** tồn tại và body là stub, chỉ dùng để minh họa cách ghi ràng buộc. Không dùng stub như implementation thực tế.

### API quản lý tài nguyên

~~~java
/// Mở reader mới cho một tệp.
///
/// Caller sở hữu reader và phải đóng sau khi sử dụng.
///
/// @param path đường dẫn không được null
/// @return reader đã mở
/// @throws java.io.IOException nếu không mở được tệp
public java.io.BufferedReader open(java.nio.file.Path path)
        throws java.io.IOException {
    return java.nio.file.Files.newBufferedReader(path);
}
~~~

Đối với API quản lý tài nguyên, nên nói rõ:

- Ai sở hữu và ai đóng.
- Có dùng được từ nhiều thread hay không.
- Timeout và cancellation hoạt động thế nào.
- Trả một view hay bản sao.
- Sau khi đóng, những đối tượng liên quan còn hợp lệ hay không.

Các thông tin đó thường có giá trị hơn mô tả cách triển khai nội bộ.

## 30. Ví dụ hoàn chỉnh: hai file nguồn Java 27

Cấu trúc dự án minh họa:

~~~text
sample/
  src/main/java/com/example/greeting/
    package-info.java
    Greeter.java
~~~

**Nội dung package-info.java:**

~~~java
/// API tạo và kiểm tra lời chào.
///
/// Package này cung cấp những thao tác thuần túy,
/// không giữ trạng thái dùng chung có thể thay đổi.
///
/// @since 1.0
package com.example.greeting;
~~~

**Nội dung Greeter.java:**

~~~java
package com.example.greeting;

import java.util.Objects;

/// Tạo lời chào tiếng Việt từ tên người dùng.
///
/// Các method của lớp không giữ trạng thái dùng chung.
///
/// Ví dụ:
///
/// {@snippet :
///     String greeting = Greeter.greet("Lan");
///     System.out.println(greeting);
/// }
///
/// @since 1.0
public final class Greeter {
    private Greeter() {
        // Utility class.
    }

    /// Trả về lời chào cho một tên không rỗng.
    ///
    /// Kết quả bắt đầu bằng `"Xin chào, "`.
    ///
    /// @param name tên không được null hoặc chỉ chứa khoảng trắng
    /// @return lời chào không null
    /// @throws NullPointerException nếu name là null
    /// @throws IllegalArgumentException nếu tên sau chuẩn hóa rỗng
    /// @since 1.0
    public static String greet(String name) {
        String normalized = Objects.requireNonNull(name).strip();

        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("name is empty");
        }

        return "Xin chào, " + normalized;
    }
}
~~~

Khi dùng API:

~~~java
System.out.println(
        com.example.greeting.Greeter.greet("  Lan  "));
// Xin chào, Lan
~~~

Từ thư mục **sample**, lệnh sinh tài liệu:

~~~text
javadoc -d build/apidocs -encoding UTF-8 -Xdoclint:all -Werror -sourcepath src/main/java -subpackages com.example.greeting
~~~

Nếu hoàn tất thành công, có thể mở **build/apidocs/index.html** và điều hướng đến package và lớp Greeter.

**Các file trong phần ví dụ chỉ được mô tả bên trong bài Markdown; không cần tạo các file Java này trong nhiệm vụ worker.**

Giải thích:

1. package-info.java mô tả toàn package.
2. Class Greeter có mô tả mục đích và snippet.
3. greet() mô tả input, return và hai ngoại lệ.
4. Implementation dùng **Objects.requireNonNull** và kiểm tra tên trống đúng hợp đồng.
5. Tài liệu không gắn nghĩa mới cho một method chỉ vì nó có snippet.
6. Lệnh Javadoc bật cả DocLint và warning-as-error.

## 31. Đặt kiểm tra tài liệu vào CI

Một pipeline tham khảo:

~~~text
Thay đổi public API
         |
         v
Compile + unit tests
         |
         v
Dangling-comment check
         |
         v
Javadoc + DocLint
         |
         v
Chặn warnings theo quality gate
         |
         v
Compile/test code samples quan trọng
         |
         v
Review HTML và hợp đồng API
         |
         v
Đóng gói và publish Javadoc cùng version
~~~

Một số quy tắc nên có trong pull request:

1. Khi đổi chữ ký, cập nhật @param và link tương ứng.
2. Khi thay lỗi/nullability, cập nhật @throws/@return.
3. Khi một API deprecated, có đường chuyển đổi.
4. Khi thay dependency version, kiểm tra liên kết ngoài.
5. Khi có warning DocLint mới, giải thích hoặc sửa trước khi merge.
6. Không chỉ lưu log build; cung cấp HTML artifact để người review có thể xem.
7. Những snippet quan trọng nên được thử compile/test ở nơi có khả năng tự động hóa.
8. Tài liệu HTML/JAR phải ghi nhận cùng version/release với code.

Không cần viết Javadoc quá dài cho mọi private method nhỏ. Ưu tiên **hợp đồng public/protected** và những chỗ có điều kiện sử dụng khó nhìn thấy.

## 32. Tài liệu HTML, security và artifact publication

Javadoc sinh HTML. Vì vậy ngoài việc tag đúng, cần có yêu cầu bảo mật và xuất bản:

- Không chèn token, mật khẩu, private key hoặc dữ liệu khách hàng thật vào ví dụ.
- Không đưa internal URL hay thông tin cấu hình nhạy cảm vào public API docs.
- Không chèn HTML/JavaScript không tin cậy vào tài liệu.
- Không mặc định DocLint là công cụ quét bảo mật HTML toàn diện.
- Kiểm tra đường dẫn output và phạm vi package/module được công bố.
- Quản lý version của Javadoc artifact để người dùng tra đúng API.
- Tôn trọng bản quyền đoạn mã, hình ảnh và tài liệu tham khảo.
- Có chính sách lưu phiên bản tài liệu cũ đang còn được sử dụng.

**@hidden** hoặc tùy chọn **-public** ảnh hưởng phạm vi tài liệu được sinh, **không biến một API public thành private hoặc thay đổi quyền truy cập trong JVM**.

## 33. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Comment không vào HTML | Dùng // thay /// hoặc đặt sai vị trí | Dùng đúng doc comment ngay trước khai báo |
| Chỉ có đoạn cuối Markdown | Dòng trống không có /// chia tách comment | Đặt /// trên cả dòng trống |
| @param sai tên | Signature đổi nhưng comment chưa đổi | Cập nhật cùng chữ ký |
| Generic thiếu @param <T> | Quên type parameter | Bổ sung mô tả type parameter |
| @return thiếu | Chưa mô tả contract trả về | Viết rõ giá trị, nullability, ownership |
| @link không phân giải | Sai tên hoặc thiếu dependency | Sửa reference và path |
| @since ghi JDK version | Nhầm với API version | Ghi version thư viện thực |
| Snippet hiển thị nhưng sai code | Javadoc không tự chạy snippet | Compile/test ví dụ |
| External snippet không tìm thấy | Sai đường dẫn/region | Kiểm tra snippet path và region |
| CI báo nhiều warning cũ | Bật nhóm missing trên dự án thiếu docs | Có lộ trình bổ sung baseline |
| Tắt -Xdoclint hoàn toàn | Che lỗi cấu trúc và link | Sửa lỗi gốc, giới hạn tạm thời nếu cần |
| Maven/Gradle dùng JDK sai | Toolchain khác local | Cố định và kiểm tra phiên bản |
| Class không xuất hiện | Nằm ngoài phạm vi package/module docs | Kiểm tra source path và access scope |
| Docs nói thread-safe nhưng code không an toàn | Mâu thuẫn hợp đồng/implementation | Review, test và sửa |
| Artifact sai version | Phát hành docs không cùng release | Gắn version rõ cho Javadoc JAR/website |
| Dùng @hidden để “bảo mật” | Không thay access control | Thiết kế visibility/exports thật |

## 34. Checklist trước khi phát hành API docs

- Tool **javadoc** đã dùng đúng JDK mục tiêu và hỗ trợ **///** chưa?
- Mỗi public API mới đã có summary ngắn và đúng chưa?
- Comment có nằm ngay trước khai báo và không bị tách bởi dòng trống thiếu /// không?
- Có đủ **@param**, **@param <T>**, **@return**, **@throws** quan trọng chưa?
- @return có nói rõ nullability, ordering, mutability và ownership không?
- Nếu method deprecated, đã dùng @Deprecated và mô tả @deprecated chưa?
- **@since** phản ánh version của API, không nhầm version JDK?
- Các JavaDoc links trỏ đúng thành phần và đúng dependency version?
- Mọi snippet quan trọng có source/kiểm thử phù hợp?
- package-info.java và module-info.java có giải thích phạm vi API không?
- Có mô tả thread safety, timeout, I/O, close, cancellation khi cần?
- Đã bật DocLint và kiểm tra warning-as-error thích hợp?
- Có kiểm tra dangling comments?
- Đã mở HTML để kiểm tra khả năng điều hướng và hiển thị?
- Có xác nhận không có thông tin nhạy cảm trong docs?
- Javadoc artifact có cùng version với thư viện phát hành?
- CI đã được cấu hình toolchain/plugin thống nhất và có thể tái lập?

## 35. Tài liệu tham khảo chính thức

Những nguồn hữu ích để đối chiếu cú pháp và công cụ trong Java 27:

- [JavaDoc Guide — Java SE 27](https://docs.oracle.com/en/java/javase/27/javadoc/): hướng dẫn tổng quan, Markdown comments và snippets.
- [The javadoc Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javadoc.html): các tùy chọn command line, DocLint và cách sinh HTML.
- [JavaDoc Documentation Comment Specification — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/javadoc/doc-comment-spec.html): cấu trúc comment, tags, references và kế thừa tài liệu.
- [JEP 467 — Markdown Documentation Comments](https://openjdk.org/jeps/467): chức năng /// được đưa vào từ JDK 23.
- [Apache Maven Javadoc Plugin](https://maven.apache.org/plugins/maven-javadoc-plugin/): tích hợp Maven và kiểm tra warnings.
- [Gradle Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html): Javadoc task, cấu hình build và toolchain.

Khi nâng JDK hoặc build plugin, hãy kiểm tra tài liệu đúng phiên bản mà pipeline hiện dùng, không sao chép ngẫu nhiên một hướng dẫn cho Java rất cũ.

## Kết luận

Trong Java 27, **Javadoc** giúp biến hợp đồng của public API thành tài liệu HTML có thể tìm kiếm, kiểm tra và phân phối. Cả **comment truyền thống /** ... */** và **Markdown comment ///** đều hợp lệ. Dạng Markdown làm việc viết danh sách, code sample, bảng và liên kết tới thành phần Java thuận tiện hơn.

Những tag như **@param**, **@return**, **@throws**, **@since**, **{@link}**, **{@inheritDoc}** và **{@snippet}** làm rõ ràng các thông tin caller cần biết. **DocLint** phát hiện nhiều lỗi thiếu tài liệu, sai tag và tham chiếu; **-Werror** hoặc chính sách Maven/Gradle tương đương có thể chặn cảnh báo mới trước phát hành.

Nhưng việc tạo Javadoc thành công **không chứng minh tài liệu đúng ngữ nghĩa hay ví dụ thực sự chạy được**. Một quy trình build và quản lý phụ thuộc trưởng thành cần kết hợp **documentation comments, kiểm tra tự động, code review, tests và artifact có version**, để người sử dụng tin cậy vào hợp đồng API được phát hành.
