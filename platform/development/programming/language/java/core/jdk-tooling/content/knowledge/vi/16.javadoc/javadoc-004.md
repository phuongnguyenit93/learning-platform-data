# Các tag chuẩn trong Javadoc

Javadoc dùng các tag trong documentation comment để mô tả API Java và tạo tài liệu HTML có cấu trúc. Tag giúp người đọc hiểu ý nghĩa tham số, giá trị trả về, ngoại lệ, phiên bản API, quan hệ giữa các kiểu và ví dụ sử dụng. Công cụ Javadoc còn dùng tag để tạo liên kết đến lớp hoặc phương thức khác, đánh dấu API đã deprecated và trình bày nội dung đặc biệt như code snippet.

Bài viết dùng **standard doclet của JDK 24** làm mốc khi liệt kê tag chuẩn. Một số tag đã có từ các phiên bản Java đầu tiên; một số tag mới chỉ có trong JDK hiện đại. Khi dùng JDK cũ hơn, cần kiểm tra tag đó đã được hỗ trợ hay chưa.

## 1. Documentation comment và Javadoc tag

Documentation comment là comment đặc biệt gắn với một khai báo Java. Dạng truyền thống bắt đầu bằng /** và kết thúc bằng */:

~~~java
/**
 * Mô tả ngắn về lớp hoặc phương thức.
 *
 * Phần này có thể giải thích chi tiết hơn, gồm nhiều đoạn văn,
 * danh sách, liên kết và ví dụ.
 *
 * @since 1.0
 */
public class Example {
}
~~~

Javadoc nhận diện comment khi nó nằm ngay trước khai báo cần mô tả, không bị một khai báo hoặc comment khác chen giữa. Có thể dùng documentation comment cho module, package, class, interface, constructor, method, annotation element, enum member và field.

Comment thông thường bắt đầu bằng // hoặc /* không được xem là documentation comment. Vì vậy, nếu muốn tạo tài liệu API, hãy dùng đúng cú pháp /** ... */.

### Cấu trúc một documentation comment

Một comment thường có hai phần:

1. **Main description:** phần mô tả chính nằm trước tag dạng block đầu tiên.
2. **Block tags:** các tag bắt đầu bằng @ ở đầu dòng, cung cấp thông tin có cấu trúc như @param, @return hoặc @throws.

Ví dụ:

~~~java
/**
 * Chuyển chuỗi đầu vào thành dạng chuẩn hóa.
 *
 * Xóa khoảng trắng ở hai đầu và gộp các khoảng trắng liên tiếp
 * thành một dấu cách.
 *
 * @param input chuỗi cần chuẩn hóa
 * @return chuỗi sau khi chuẩn hóa
 * @throws IllegalArgumentException nếu input là null
 * @since 1.0
 */
public String normalize(String input) {
    // ...
}
~~~

Dòng đầu tiên nên là một câu tóm tắt ngắn, đầy đủ ý nghĩa và có thể đứng độc lập trong trang tổng hợp API. Các tag block phải bắt đầu ở đầu dòng, sau dấu * và khoảng trắng tùy ý. Nội dung của một tag kéo dài đến tag block tiếp theo hoặc hết comment.

Main description kết thúc tại block tag đầu tiên. Không viết phần mô tả chính tiếp tục sau @param hoặc @return.

### Block tag và inline tag

Javadoc có hai hình thức tag:

| Loại | Cú pháp | Vị trí thường dùng | Ví dụ |
|---|---|---|---|
| Block tag | @tag nội dung | Đầu một dòng trong documentation comment | @param input chuỗi đầu vào |
| Inline tag | {@tag nội dung} | Nằm trong câu hoặc đoạn mô tả | {@code String}, {@link String#strip()} |

Block tag tạo phần thông tin riêng trong tài liệu. Inline tag chèn nội dung, liên kết hoặc định dạng ngay tại vị trí xuất hiện.

## 2. Các block tag thông dụng

### @param — mô tả tham số

Dùng @param để mô tả từng tham số của method hoặc constructor. Tag phải dùng đúng tên tham số trong khai báo.

~~~java
/**
 * Tìm một mục theo mã.
 *
 * @param code mã cần tìm
 * @param ignoreCase true nếu không phân biệt chữ hoa và chữ thường
 * @return mục phù hợp, hoặc null nếu không tìm thấy
 */
public Item find(String code, boolean ignoreCase) {
    // ...
}
~~~

Với generic type parameter, đặt tên kiểu trong dấu ngoặc nhọn:

~~~java
/**
 * Chuyển đổi giá trị sang kiểu đích.
 *
 * @param <T> kiểu kết quả
 * @param value giá trị đầu vào
 * @param type lớp đại diện cho kiểu đích
 * @return giá trị sau khi chuyển đổi
 */
public <T> T convert(Object value, Class<T> type) {
    // ...
}
~~~

Lưu ý:

- Mỗi tham số nên có một @param tương ứng.
- Tên phải khớp với khai báo, bao gồm chữ hoa/chữ thường.
- Với type parameter, dùng dạng @param <T>.
- Mô tả điều kiện hợp lệ, giá trị đặc biệt và cách xử lý null khi có liên quan.

### @return — mô tả giá trị trả về

Dùng @return cho method có kiểu trả về khác void.

~~~java
/**
 * Tính tổng hai số nguyên.
 *
 * @param first số thứ nhất
 * @param second số thứ hai
 * @return tổng của hai số
 */
public int add(int first, int second) {
    return first + second;
}
~~~

Không dùng @return cho constructor hoặc method void. Mô tả cần nói rõ giá trị trả về có ý nghĩa gì, có thể null hay không, và có giá trị đặc biệt nào cần lưu ý.

### @throws — mô tả ngoại lệ

Dùng @throws để mô tả ngoại lệ mà method hoặc constructor có thể ném ra. Tên ngoại lệ phải tham chiếu đến kiểu ngoại lệ hợp lệ.

~~~java
/**
 * Chia hai số nguyên.
 *
 * @param dividend số bị chia
 * @param divisor số chia
 * @return thương nguyên
 * @throws ArithmeticException nếu divisor bằng 0
 */
public int divide(int dividend, int divisor) {
    return dividend / divisor;
}
~~~

Có thể khai báo nhiều @throws nếu method có nhiều điều kiện lỗi. Nên mô tả tình huống cụ thể khiến ngoại lệ xuất hiện, thay vì chỉ viết lại tên ngoại lệ.

**@exception** là tên tag cũ có ý nghĩa tương đương @throws. Nên dùng @throws trong tài liệu mới để thống nhất với cách gọi hiện hành.

### @see — tài liệu liên quan

@see thêm mục See Also ở phần cuối tài liệu của phần tử được mô tả. Tag hỗ trợ tham chiếu đến phần tử Java, URL hoặc một chuỗi văn bản.

~~~java
/**
 * Trả về tên đã chuẩn hóa.
 *
 * @see String#strip()
 * @see java.text.Normalizer
 * @see "Quy ước đặt tên trong dự án"
 */
public String normalizedName() {
    // ...
}
~~~

Các dạng thường dùng:

- @see ClassName: liên kết đến lớp.
- @see #methodName(Type): liên kết đến method trong cùng lớp.
- @see package.Class#field: liên kết đến field.
- @see "text": thêm văn bản tham khảo không tạo liên kết.
- @see <a href="URL">label</a>: tạo liên kết đến URL.

Nếu method bị overload, nên ghi danh sách kiểu tham số để Javadoc xác định đúng đích liên kết.

### @since — phiên bản bắt đầu có API

@since cho biết API hoặc tính năng xuất hiện từ phiên bản nào của sản phẩm.

~~~java
/**
 * Trả về mã định danh duy nhất.
 *
 * @return mã định danh
 * @since 2.1
 */
public String id() {
    // ...
}
~~~

Giá trị sau @since là văn bản tự do, nhưng nên dùng quy ước phiên bản nhất quán trong toàn dự án. Đừng nhầm @since với @version: @since nói API bắt đầu tồn tại từ bản nào, còn @version nói phiên bản hiện tại của thành phần hoặc phần mềm.

### @deprecated — đánh dấu API không còn được khuyến nghị

@deprecated giải thích vì sao API không nên tiếp tục được sử dụng và chỉ ra phương án thay thế.

Nên dùng cùng annotation @Deprecated:

~~~java
/**
 * Trả về tên theo quy tắc cũ.
 *
 * @deprecated Từ phiên bản 2.0, dùng {@link #normalizedName()}.
 */
@Deprecated(since = "2.0")
public String legacyName() {
    // ...
}
~~~

Nội dung @deprecated nên:

- Nêu phiên bản API bị deprecated.
- Nêu API thay thế cụ thể.
- Dùng {@link ...} để tạo liên kết đến phương án thay thế.
- Giải thích lý do hoặc thời điểm cần chuyển đổi nếu có.

Annotation @Deprecated hỗ trợ compiler và công cụ phát hiện việc sử dụng API cũ. Tag @deprecated cung cấp nội dung giải thích cho trang Javadoc. Hai thành phần có vai trò khác nhau và nên xuất hiện cùng nhau.

### @author và @version

@author ghi tác giả hoặc nhóm phát triển:

~~~java
/**
 * Bộ tiện ích xử lý văn bản.
 *
 * @author Java Platform Team
 */
public class TextTools {
}
~~~

@version ghi phiên bản hiện tại của lớp hoặc thành phần:

~~~java
/**
 * Bộ tiện ích xử lý văn bản.
 *
 * @version 1.4.0
 */
public class TextTools {
}
~~~

Hai tag này chỉ được đưa vào tài liệu HTML khi chạy Javadoc với tùy chọn tương ứng:

~~~bash
javadoc -author -version ...
~~~

Có thể dùng nhiều @author hoặc @version. Trong nhiều dự án hiện đại, thông tin tác giả và phiên bản được quản lý ở hệ thống khác; chỉ dùng hai tag khi chúng có giá trị thực tế với người đọc API.

## 3. Các block tag chuyên biệt

### @hidden — ẩn phần tử khỏi tài liệu API

@hidden yêu cầu standard doclet không đưa phần tử được đánh dấu vào tài liệu API được tạo.

~~~java
/**
 * Lớp hỗ trợ nội bộ cho quá trình khởi tạo.
 *
 * @hidden
 */
public class InternalBootstrap {
}
~~~

Tag này có từ JDK 9. Chỉ dùng khi cần giữ khai báo trong mã nguồn hoặc API nhị phân nhưng không muốn hiển thị nó trong tài liệu được tạo. Không dùng @hidden để thay thế thiết kế package/module hợp lý.

### @provides và @uses — mô tả service trong module

Hai tag này chỉ dùng trong documentation comment của module declaration.

- @provides service-type description mô tả module cung cấp implementation cho service.
- @uses service-type description mô tả module sử dụng service.

Ví dụ module-info.java:

~~~java
/**
 * Module cung cấp bộ chuyển đổi định dạng.
 *
 * @provides com.example.spi.Formatter
 *     Module cung cấp implementation JSON cho service Formatter.
 * @uses com.example.spi.Extension
 *     Module có thể sử dụng các extension được đăng ký trong runtime.
 */
module com.example.formatter {
    requires com.example.spi;
    provides com.example.spi.Formatter
        with com.example.formatter.JsonFormatter;
    uses com.example.spi.Extension;
}
~~~

Các tag này giúp người đọc hiểu vai trò service của module. Chúng bổ sung tài liệu cho directive provides và uses; chúng không thay thế các directive trong module-info.java.

### @spec — tham chiếu đặc tả bên ngoài

@spec liên kết một phần API với tài liệu đặc tả bên ngoài:

~~~java
/**
 * Mã hóa dữ liệu theo quy tắc được mô tả trong đặc tả.
 *
 * @spec https://www.rfc-editor.org/rfc/rfc8259 RFC 8259
 */
public String encode(Object value) {
    // ...
}
~~~

@spec được hỗ trợ từ JDK 20. URL và tiêu đề phải nhất quán nếu cùng một URL được tham chiếu ở nhiều nơi trong tài liệu.

### @serial — tài liệu hóa lớp và field Serializable

@serial phục vụ trang Serialized Form cho lớp triển khai Serializable. Có thể dùng tag này để mô tả field được serialize hoặc điều khiển việc đưa lớp vào trang serialized form.

Các dạng:

~~~java
@serial field-description
@serial include
@serial exclude
~~~

Ví dụ mô tả field:

~~~java
/**
 * Mã người dùng được lưu trong serialized form.
 *
 * @serial Mã định danh duy nhất của người dùng.
 */
private long userId;
~~~

Ở cấp class hoặc package, include/exclude có thể điều khiển việc phần tử được đưa vào trang serialized form theo quy tắc của standard doclet. Tag ở cấp class có thể ghi đè cấu hình ở cấp package.

### @serialField — mô tả serialPersistentFields

@serialField mô tả từng thành phần ObjectStreamField trong field serialPersistentFields của lớp Serializable.

Cú pháp:

~~~java
@serialField field-name field-type field-description
~~~

Ví dụ:

~~~java
/**
 * Các field được duy trì trong serialized form.
 *
 * @serialField userId long Mã định danh người dùng.
 * @serialField displayName String Tên hiển thị.
 */
private static final ObjectStreamField[] serialPersistentFields = {
    new ObjectStreamField("userId", long.class),
    new ObjectStreamField("displayName", String.class)
};
~~~

Chỉ dùng tag này khi lớp thực sự khai báo serialPersistentFields theo cơ chế Java Serialization.

### @serialData — mô tả dữ liệu được ghi/đọc khi serialize

@serialData mô tả kiểu và thứ tự dữ liệu được ghi bởi các phương thức serialization như writeObject hoặc writeExternal.

~~~java
/**
 * Ghi dữ liệu bổ sung vào stream.
 *
 * @serialData Ghi số phiên bản trước, sau đó ghi chuỗi tên người dùng.
 */
private void writeObject(java.io.ObjectOutputStream out)
        throws java.io.IOException {
    out.defaultWriteObject();
    out.writeInt(1);
    out.writeUTF(displayName);
}
~~~

Tag này chỉ phù hợp với các phương thức serialization được Javadoc quy định, như readObject, writeObject, readExternal, writeExternal, readResolve và writeReplace.

## 4. Các inline tag chuẩn

### {@code} — hiển thị văn bản dạng code

{@code ...} hiển thị nội dung bằng font monospace và không diễn giải nội dung bên trong như HTML hoặc Javadoc tag.

~~~java
/**
 * Trả về {@code true} nếu danh sách rỗng.
 */
public boolean isEmpty() {
    return size() == 0;
}
~~~

Dùng cho tên lớp, phương thức, biến, biểu thức, kiểu generic và lệnh. Có thể viết dấu < và > trực tiếp trong {@code ...} mà không cần chuyển thành HTML entity.

### {@literal} — hiển thị nguyên văn

{@literal ...} giữ nguyên cách hiển thị ký tự, không diễn giải HTML hoặc tag lồng bên trong, nhưng không dùng font code.

~~~java
/**
 * Điều kiện hợp lệ là {@literal value < limit}.
 */
public boolean isBelowLimit(int value, int limit) {
    return value < limit;
}
~~~

Phân biệt:

- {@code ...}: nguyên văn và font code.
- {@literal ...}: nguyên văn, font văn bản thông thường.

### {@link} — liên kết nội dòng

{@link reference label} tạo liên kết ngay trong câu đến class, package, field, constructor hoặc method.

~~~java
/**
 * Dùng {@link String#strip()} để loại bỏ khoảng trắng ở hai đầu.
 *
 * @return chuỗi đã xử lý
 */
public String clean(String value) {
    return value.strip();
}
~~~

Cú pháp tham chiếu thường gặp:

- {@link String}: liên kết đến lớp String.
- {@link #clean(String)}: liên kết đến method trong cùng lớp.
- {@link java.util.List#size()}: liên kết đến method của lớp khác.
- {@link #clean(String) clean}: dùng nhãn hiển thị riêng.

Nếu có nhãn, phần sau reference được dùng làm nội dung hiển thị.

### {@linkplain} — liên kết với nhãn văn bản thường

{@linkplain} hoạt động như {@link}, nhưng nhãn hiển thị bằng font văn bản thông thường thay vì font code.

~~~java
/**
 * Xem {@linkplain #clean(String) phương thức làm sạch chuỗi}
 * trước khi lưu dữ liệu.
 */
public void save(String value) {
    // ...
}
~~~

Dùng {@link} khi muốn tên API hiển thị như code; dùng {@linkplain} khi nhãn là một cụm từ tự nhiên trong câu.

### {@inheritDoc} — kế thừa tài liệu từ method được override

{@inheritDoc} chèn phần tài liệu tương ứng từ method trong superclass hoặc superinterface.

~~~java
interface Formatter {
    /**
     * Chuyển đổi giá trị sang chuỗi.
     *
     * @param value giá trị đầu vào
     * @return chuỗi đã chuyển đổi
     */
    String format(Object value);
}

final class JsonFormatter implements Formatter {
    /**
     * {@inheritDoc}
     */
    @Override
    public String format(Object value) {
        return String.valueOf(value);
    }
}
~~~

Tag này chỉ dùng trong documentation comment của method override, ở main description hoặc nội dung @param, @return, @throws. Nếu method cha không có phần tài liệu tương ứng, Javadoc không thể kế thừa phần đó.

Từ JDK 22, có thể chỉ rõ supertype làm nguồn kế thừa bằng dạng {@inheritDoc SuperType}. Dạng không có đối số để Javadoc tự tìm method phù hợp trong hệ thống kế thừa.

### {@docRoot} — đường dẫn đến gốc tài liệu

{@docRoot} được thay bằng đường dẫn tương đối từ trang hiện tại về thư mục gốc của tài liệu Javadoc được tạo.

~~~java
/**
 * Xem <a href="{@docRoot}/legal/license.html">điều khoản sử dụng</a>.
 */
public class LicenseInfo {
}
~~~

Tag hữu ích khi liên kết đến tài nguyên chung như license, hình ảnh hoặc trang hướng dẫn được đặt ở thư mục gốc output.

### {@index} — thêm từ khóa vào chỉ mục

{@index word description} tạo mục trong chỉ mục Javadoc. Có thể lập chỉ mục cho một từ hoặc cụm từ.

~~~java
/**
 * Phần này giải thích {@index "thread safety" tính an toàn khi truy cập đồng thời}
 * của đối tượng.
 */
public class ConcurrentCache {
}
~~~

Với cụm từ có nhiều từ, đặt cụm từ trong dấu ngoặc kép. Mô tả ngắn có thể giúp người đọc hiểu mục chỉ mục đang nói đến khái niệm nào.

### {@summary} — chỉ định câu tóm tắt

{@summary ...} xác định rõ phần nội dung dùng làm summary của API, thay cho việc để Javadoc tự lấy câu đầu tiên.

~~~java
/**
 * {@summary Bộ đệm lưu kết quả tính toán để tái sử dụng.}
 *
 * Bộ đệm hỗ trợ thời hạn hết hạn và giới hạn số phần tử.
 */
public class ResultCache {
}
~~~

Tag này có từ JDK 10 và chỉ có ý nghĩa khi xuất hiện ở đầu main description.

### {@systemProperty} — đánh dấu system property

{@systemProperty property.name} xác định tên một Java system property trong tài liệu.

~~~java
/**
 * Đọc cấu hình từ {@systemProperty app.region}.
 */
public String region() {
    return System.getProperty("app.region", "local");
}
~~~

Tên property nên là định danh dạng chấm, không có khoảng trắng. Tag này giúp tên system property được nhận diện và trình bày nhất quán trong tài liệu.

### {@value} — hiển thị giá trị hằng số

{@value} hiển thị giá trị của static field có giá trị hằng tại thời điểm biên dịch. Có thể chỉ rõ field bằng reference.

~~~java
/**
 * Số ký tự tối đa được chấp nhận.
 */
public static final int MAX_LENGTH = 120;

/**
 * Giới hạn hiện tại là {@value #MAX_LENGTH} ký tự.
 */
public void validate(String input) {
    // ...
}
~~~

Dùng {@value} không kèm reference trong comment của chính field để hiển thị giá trị field đó. Dùng {@value #CONSTANT} để tham chiếu hằng số khác. Từ JDK 20, tag hỗ trợ format string phù hợp với kiểu dữ liệu của hằng số.

### {@snippet} — chèn code example

{@snippet} đưa một đoạn code vào tài liệu được tạo. Tag được giới thiệu từ JDK 18, hỗ trợ nội dung viết trực tiếp trong comment hoặc lấy từ tệp ngoài.

Ví dụ inline:

~~~java
/**
 * Ví dụ sử dụng:
 *
 * {@snippet :
 *     List<String> names = List.of("An", "Binh");
 *     names.forEach(System.out::println);
 * }
 */
public void printNames() {
    // ...
}
~~~

Ví dụ lấy snippet từ tệp ngoài:

~~~java
/**
 * Ví dụ xử lý đầu vào:
 *
 * {@snippet file="Example.java" region="parse"}
 */
public void parse() {
    // ...
}
~~~

Tệp ngoài có thể đặt trong thư mục snippet-files theo cấu trúc package hoặc trên đường dẫn được cung cấp bằng tùy chọn --snippet-path. Có thể dùng markup như @start, @end, @highlight, @replace và @link trong comment dòng của đoạn code để chọn vùng hoặc điều chỉnh cách hiển thị.

Lưu ý khi dùng snippet inline trong traditional documentation comment:

- Không được chứa chuỗi ký tự */ vì nó sẽ kết thúc comment Java.
- Các dấu ngoặc nhọn phải cân bằng để Javadoc xác định được điểm kết thúc inline tag.
- Snippet là nội dung tài liệu; nếu cần bảo đảm ví dụ thực sự biên dịch, hãy kiểm tra bằng build/test riêng hoặc dùng snippet ngoài gắn với source được kiểm thử.

### {@return} — khai báo phần trả về ngay trong main description

Từ JDK 16, có thể dùng inline tag {@return ...} ở đầu main description của method. Javadoc dùng nội dung đó làm câu mở đầu và phần Returns.

~~~java
/**
 * {@return số lượng phần tử hiện có}
 */
public int size() {
    return 0;
}
~~~

Tag này chỉ dùng cho method. Nếu đã dùng {@return ...}, không cần thêm @return block tag cho cùng nội dung. Với method phức tạp, @return block tag truyền thống vẫn rõ ràng và dễ đọc.

## 5. Tag chuẩn theo ngữ cảnh khai báo

Không phải tag nào cũng dùng được ở mọi vị trí. Một số tag chỉ dành cho method, một số chỉ dành cho module hoặc serialization.

| Ngữ cảnh | Tag tiêu biểu |
|---|---|
| Module | @provides, @uses, @since, @spec, @see |
| Package | @author, @version, @since, @serial, @see |
| Class/interface/record | @param cho type parameter, @author, @version, @since, @deprecated, @hidden, @serial |
| Constructor | @param, @throws, @deprecated, @see, @since |
| Method | @param, @return, @throws, @inheritDoc, @deprecated, @since |
| Field | @value, @serial, @deprecated, @since |
| Method serialization đặc biệt | @serialData |
| Field serialPersistentFields | @serialField |

Các inline tag như {@code}, {@link}, {@linkplain}, {@literal}, {@summary}, {@snippet}, {@systemProperty}, {@value} và {@docRoot} được dùng trong nhiều loại documentation comment, tùy quy tắc riêng của từng tag.

Trước khi đặt một tag vào comment, hãy kiểm tra tag đó có hợp lệ với loại khai báo đang mô tả hay không. Ví dụ, @return không dành cho constructor; @uses và @provides chỉ dành cho module declaration.

## 6. Tag chuẩn và tag tùy chỉnh

Standard doclet của JDK 24 nhận diện một tập tag chuẩn được mô tả trong đặc tả Javadoc. Một số tag quen thuộc trong tài liệu JDK, chẳng hạn @apiNote, @implSpec và @implNote, thường được cấu hình như **custom tags** trong quy trình build tài liệu của JDK. Chúng không nằm trong danh sách tag chuẩn mặc định của đặc tả standard doclet JDK 24.

Có thể khai báo một custom block tag đơn giản bằng tùy chọn -tag:

~~~bash
javadoc -tag 'todo:a:To Do:' ...
~~~

Có thể viết Taglet khi cần định dạng hoặc xử lý phức tạp. Tùy chọn -taglet nạp implementation của Taglet; -tagletpath chỉ định nơi tìm class của Taglet.

Không nên tự dùng tag tùy chỉnh mà không cấu hình Javadoc. Nếu standard doclet không nhận diện tag, công cụ có thể báo unknown tag hoặc warning. Để tránh xung đột với tag chuẩn tương lai, nên đặt namespace riêng cho tag của dự án, ví dụ @com.example.todo.

## 7. Ví dụ hoàn chỉnh: viết và sinh tài liệu Javadoc

Tạo tệp src/com/example/TextTools.java:

~~~java
package com.example;

/**
 * Bộ tiện ích chuẩn hóa văn bản.
 *
 * Lớp này cung cấp các thao tác đơn giản để chuẩn hóa đầu vào
 * trước khi lưu hoặc so sánh.
 *
 * @author Example Team
 * @version 1.0
 * @since 17
 */
public final class TextTools {

    /**
     * Số ký tự tối đa của chuỗi sau khi chuẩn hóa.
     */
    public static final int MAX_LENGTH = 120;

    private TextTools() {
    }

    /**
     * Chuẩn hóa chuỗi và giới hạn độ dài kết quả.
     *
     * Xóa khoảng trắng ở hai đầu, gộp nhiều khoảng trắng liên tiếp
     * thành một dấu cách, sau đó cắt kết quả nếu vượt giới hạn
     * {@value #MAX_LENGTH}.
     *
     * @param input chuỗi đầu vào cần chuẩn hóa
     * @return chuỗi đã chuẩn hóa; kết quả không dài hơn
     *     {@value #MAX_LENGTH} ký tự
     * @throws IllegalArgumentException nếu input là null
     * @see String#strip()
     * @since 1.0
     */
    public static String normalize(String input) {
        if (input == null) {
            throw new IllegalArgumentException("input must not be null");
        }

        String result = input.strip().replaceAll("\\s+", " ");
        if (result.length() > MAX_LENGTH) {
            return result.substring(0, MAX_LENGTH);
        }
        return result;
    }

    /**
     * Trả về tên theo quy tắc tương thích cũ.
     *
     * @deprecated Từ phiên bản 2.0, dùng {@link #normalize(String)}.
     */
    @Deprecated(since = "2.0")
    public static String legacyNormalize(String input) {
        return normalize(input);
    }
}
~~~

Từ thư mục dự án, tạo HTML documentation bằng JDK 17 trở lên:

~~~bash
javadoc --release 17 -Xdoclint:all -encoding UTF-8 -author -version -d docs src/com/example/TextTools.java
~~~

Giải thích:

- --release 17 chọn mức tương thích nguồn và API Java 17.
- -Xdoclint:all bật các nhóm kiểm tra nội dung documentation.
- -encoding UTF-8 đọc source có tiếng Việt đúng mã hóa.
- -author và -version yêu cầu hiển thị hai tag tương ứng.
- -d docs chọn thư mục chứa HTML output.
- Tệp Java ở cuối lệnh là nguồn được dùng để tạo tài liệu.

Nếu muốn warning làm build thất bại, có thể thêm -Werror:

~~~bash
javadoc --release 17 -Xdoclint:all -Werror -encoding UTF-8 -author -version -d docs src/com/example/TextTools.java
~~~

Sau khi chạy, mở docs/index.html hoặc trang class tương ứng trong thư mục docs. Javadoc tạo các trang HTML cho class và member, kèm summary, phần Parameters, Returns, Throws, Since, See Also và thông tin deprecated theo các tag đã khai báo.

## 8. Doclint và lỗi thường gặp

Javadoc không chỉ chuyển comment thành HTML; nó còn phân tích reference, cú pháp tag và cấu trúc HTML. Tùy phiên bản, doclint có thể phát hiện nhiều lỗi trước khi tài liệu được phát hành.

### Thiếu @param

Method có tham số nhưng documentation không mô tả đầy đủ. Bổ sung @param cho từng tham số, kể cả type parameter nếu có.

### Thiếu @return

Method trả về giá trị nhưng comment không mô tả kết quả. Bổ sung @return hoặc dùng {@return ...} nếu phù hợp với phiên bản JDK.

### Thiếu @throws hoặc mô tả ngoại lệ

Method khai báo checked exception nhưng không có nội dung giải thích. Bổ sung @throws với điều kiện phát sinh và ý nghĩa ngoại lệ. Không ghi ngoại lệ không liên quan chỉ để làm đầy tài liệu.

### Reference không tồn tại

Ví dụ {@link #findById(String)} nhưng method thực tế có tên hoặc kiểu tham số khác. Kiểm tra tên lớp, package, overload và danh sách kiểu tham số. Với method overload, luôn ghi rõ signature khi cần.

### Đặt block tag sai vị trí

Block tag phải bắt đầu một dòng. Nếu viết @param giữa câu mô tả, Javadoc có thể hiểu sai hoặc không xử lý như dự kiến. Dùng inline tag khi cần chèn định dạng trong câu.

### Dùng tag ở sai loại khai báo

Ví dụ @return trong constructor hoặc @uses trong class comment. Kiểm tra bảng vị trí hợp lệ của tag trong đặc tả Javadoc.

### HTML không hợp lệ

Thẻ HTML thiếu thẻ đóng, lồng sai hoặc dùng thuộc tính không phù hợp có thể tạo trang lỗi hoặc warning. Ưu tiên HTML5 hợp lệ và dùng {@code}/{@literal} cho ký tự cần hiển thị nguyên văn.

### Tag tùy chỉnh chưa được đăng ký

Các tag như @todo hoặc @implSpec có thể báo unknown tag nếu chưa cấu hình -tag hoặc -taglet. Xác nhận tag là built-in hay custom trong toolchain của dự án.

### Dùng tag mới với JDK cũ

Ví dụ {@snippet} không có trên JDK 17 vì được giới thiệu trong JDK 18; @spec được giới thiệu trong JDK 20; dạng {@inheritDoc SuperType} cần JDK 22 trở lên. Kiểm tra phiên bản Javadoc đang chạy, không chỉ phiên bản Java mà ứng dụng target.

## 9. Quy tắc viết Javadoc dễ bảo trì

1. Viết câu đầu tiên ngắn, cụ thể và đủ nghĩa khi đứng độc lập.
2. Mô tả hành vi có thể quan sát được của API, gồm điều kiện đầu vào và kết quả.
3. Dùng @param cho mọi tham số và @return cho kết quả khác void.
4. Mô tả ngoại lệ bằng @throws và ghi điều kiện thực tế làm phát sinh lỗi.
5. Liên kết đến API liên quan bằng {@link} hoặc @see.
6. Ghi @since khi thêm API mới hoặc thay đổi phạm vi phiên bản hỗ trợ.
7. Dùng @Deprecated cùng @deprecated và chỉ rõ phương án thay thế.
8. Dùng {@code} cho tên kiểu, biến, method và đoạn code ngắn.
9. Dùng {@snippet} cho ví dụ dài khi toolchain hỗ trợ và có thể kiểm tra snippet.
10. Chỉ dùng tag serialization cho lớp thực sự triển khai Java Serialization.
11. Không để thông tin nội bộ hoặc TODO chưa hoàn thiện xuất hiện trong tài liệu API phát hành.
12. Chạy Javadoc trong CI với doclint để phát hiện lỗi tham chiếu và thiếu nội dung.

## 10. Bảng tra cứu nhanh các tag chuẩn JDK 24

| Tag | Loại | Mục đích |
|---|---|---|
| @author | Block | Ghi tác giả |
| @deprecated | Block | Giải thích API đã deprecated |
| @exception | Block | Bí danh cũ của @throws |
| @hidden | Block | Ẩn phần tử khỏi tài liệu được tạo |
| @param | Block | Mô tả tham số hoặc type parameter |
| @provides | Block | Mô tả service implementation của module |
| @return | Block | Mô tả giá trị trả về |
| @see | Block | Thêm tham chiếu liên quan |
| @serial | Block | Mô tả field hoặc phạm vi serialized form |
| @serialData | Block | Mô tả dữ liệu serialization |
| @serialField | Block | Mô tả field trong serialPersistentFields |
| @since | Block | Phiên bản API được giới thiệu |
| @spec | Block | Liên kết đến đặc tả bên ngoài |
| @throws | Block | Mô tả ngoại lệ |
| @uses | Block | Mô tả service module sử dụng |
| @version | Block | Ghi phiên bản thành phần |
| {@code} | Inline | Hiển thị code nguyên văn |
| {@docRoot} | Inline | Đường dẫn tương đối về gốc tài liệu |
| {@index} | Inline | Thêm mục vào chỉ mục |
| {@inheritDoc} | Inline | Kế thừa nội dung tài liệu của method |
| {@link} | Inline | Liên kết API với nhãn dạng code |
| {@linkplain} | Inline | Liên kết API với nhãn văn bản thường |
| {@literal} | Inline | Hiển thị nguyên văn không dùng font code |
| {@return} | Inline | Khai báo mô tả kết quả trả về ở đầu method |
| {@snippet} | Inline | Chèn code snippet |
| {@summary} | Inline | Chỉ định câu summary |
| {@systemProperty} | Inline | Đánh dấu tên system property |
| {@value} | Inline | Hiển thị giá trị hằng số |

@exception là dạng cũ; trong tài liệu mới nên dùng @throws. @return có cả dạng block và dạng inline {@return ...}. Tập tag và phiên bản giới thiệu từng tag cần được đối chiếu với JDK mục tiêu.

## 11. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Javadoc | Công cụ tạo tài liệu API từ documentation comment |
| Documentation comment | Comment bắt đầu bằng /** gắn với khai báo Java |
| Standard doclet | Doclet mặc định tạo tài liệu HTML |
| Block tag | Tag bắt đầu bằng @ ở đầu dòng |
| Inline tag | Tag có dạng {@...} nằm trong phần mô tả |
| Main description | Phần mô tả chính trước block tag đầu tiên |
| Summary sentence | Câu tóm tắt được dùng trong bảng tổng hợp API |
| Doclint | Nhóm kiểm tra cú pháp, reference, HTML và nội dung Javadoc |
| Taglet | Thành phần mở rộng để xử lý tag tùy chỉnh |
| Serialized form | Dạng dữ liệu và field được lưu khi serialize đối tượng |

Các tag Javadoc tạo ra hợp đồng tài liệu cho API. Hãy mô tả đúng tham số, kết quả và ngoại lệ; dùng liên kết để nối các phần API; ghi phiên bản và trạng thái deprecated rõ ràng; cuối cùng chạy doclint để kiểm tra tài liệu trước khi phát hành.

## Tài liệu tham khảo

- Oracle JDK 24 — [Documentation Comment Specification for the Standard Doclet](https://docs.oracle.com/en/java/javase/24/docs/specs/javadoc/doc-comment-spec.html)
- Oracle — [How to Write Doc Comments for the Javadoc Tool](https://www.oracle.com/java/technologies/javase/writing-doc-comments.html)
- Oracle JDK 24 — [The javadoc Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javadoc.html)
- OpenJDK — [JDK documentation build tag configuration](https://github.com/openjdk/jdk/blob/master/make/Docs.gmk)