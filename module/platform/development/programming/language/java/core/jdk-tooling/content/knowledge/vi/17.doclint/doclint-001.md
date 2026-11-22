# Doclint là gì?

**Doclint** là bộ kiểm tra chất lượng comment Javadoc được tích hợp trong công cụ **javadoc** của JDK. Nó phân tích documentation comment trong mã nguồn Java để phát hiện các vấn đề như cú pháp tag sai, HTML không hợp lệ, liên kết tới kiểu hoặc member không tồn tại, nội dung HTML khó tiếp cận và tài liệu API bị thiếu.

Doclint giúp nhóm phát hiện lỗi trong tài liệu ngay khi build, thay vì đợi người đọc mở trang Javadoc đã phát hành mới nhận ra liên kết hỏng hoặc ví dụ mô tả sai cấu trúc. Có thể xem Doclint như một bước kiểm tra tĩnh dành riêng cho phần tài liệu của source code.

Lệnh kiểm tra rõ ràng các nhóm Doclint:

~~~bash
javadoc -Xdoclint:all -Werror \
    -d build/docs \
    src/com/example/api/Greeter.java
~~~

Trong đó:

- **javadoc** đọc source và tạo tài liệu HTML.
- **-Xdoclint:all** bật tất cả nhóm kiểm tra Doclint, bao gồm kiểm tra tài liệu còn thiếu.
- **-Werror** làm cho warning trở thành lỗi build.
- **-d build/docs** chỉ định thư mục chứa Javadoc được tạo.

Doclint không thay thế compiler, unit test hay review nội dung. Nó kiểm tra cấu trúc và tham chiếu của documentation comment; developer vẫn phải xác nhận phần mô tả có đúng với hành vi thật của API hay không.

## 1. Vì sao cần Doclint?

Javadoc là một phần của API công khai. Người dùng thư viện thường dựa vào tài liệu để biết method làm gì, tham số có ý nghĩa gì, kết quả ra sao và exception nào có thể xuất hiện.

Một comment có thể nhìn vẫn hợp lý nhưng chứa lỗi:

~~~java
/**
 * Returns the display name.
 * @param user the account to display
 * @return the display name
 * @throws IOException if the account is missing
 */
public String displayName(User user) {
    return user.name();
}
~~~

Nếu method không khai báo hoặc không thể ném IOException, tag @throws có thể là tham chiếu sai. Nếu comment chứa một liên kết tới kiểu không tồn tại, người đọc sẽ nhận được trang tài liệu có link hỏng. Nếu HTML mở một tag nhưng không đóng đúng cách, cấu trúc trang được tạo có thể sai.

Doclint hỗ trợ phát hiện các vấn đề thuộc những nhóm sau:

- **Syntax:** cú pháp documentation comment và inline/block tag.
- **HTML:** cấu trúc, tag và thuộc tính HTML trong comment.
- **Reference:** tham chiếu tới kiểu, package, field, constructor, method hoặc tài liệu liên quan.
- **Accessibility:** vấn đề tiếp cận trong HTML được tạo từ comment.
- **Missing:** comment hoặc thành phần tài liệu cần thiết chưa được cung cấp.

Những kiểm tra này hữu ích với thư viện, SDK, framework và bất kỳ dự án nào coi Javadoc là một phần của sản phẩm.

## 2. Doclint được chạy ở đâu?

Doclint được tích hợp vào **Javadoc tool**, không phải một lệnh độc lập mà developer thường gọi riêng.

Quy trình phổ biến:

1. Developer viết source và documentation comment.
2. Compiler kiểm tra source Java khi build ứng dụng.
3. Javadoc đọc source, phân tích declaration và comment.
4. Doclint kiểm tra các comment theo nhóm đã bật.
5. Standard doclet tạo trang HTML nếu quá trình xử lý thành công.
6. CI đánh giá exit code và warning theo cấu hình build.

Lệnh tạo tài liệu và kiểm tra cùng lúc:

~~~bash
javadoc -Xdoclint:all \
    -d build/docs \
    src/com/example/api/Greeter.java
~~~

Nếu chỉ muốn kiểm tra mà không giữ lại kết quả HTML, có thể ghi output vào thư mục build tạm và xóa thư mục đó trong bước clean của pipeline. Javadoc vẫn thực hiện quá trình xử lý tài liệu để tạo output.

Doclint không được gọi tự động bởi mọi lệnh javac. Chạy javac thành công không có nghĩa Javadoc comment đã hợp lệ. Muốn kiểm tra tài liệu, cần chạy javadoc hoặc một build task gọi công cụ này.

## 3. Documentation comment nào được Doclint kiểm tra?

Java có nhiều loại comment:

~~~java
// Single-line comment

/* Ordinary block comment */

/**
 * Documentation comment.
 */
~~~

Documentation comment bắt đầu bằng /** và được đặt trước declaration mà nó mô tả. Javadoc tool đọc loại comment này để tạo tài liệu.

Ví dụ:

~~~java
/**
 * Converts a name to uppercase.
 *
 * @param name the input name
 * @return the uppercase name
 */
public String uppercase(String name) {
    return name.toUpperCase();
}
~~~

Comment bắt đầu bằng // hoặc /* thông thường không phải Javadoc comment và không được xuất thành tài liệu API.

Doclint tập trung vào documentation comment và các tham chiếu mà Javadoc phân tích từ comment. Nó không đánh giá đầy đủ logic trong thân method, hiệu năng, thread safety hoặc tính đúng đắn nghiệp vụ.

Một comment có thể qua Doclint nhưng vẫn mô tả sai hành vi. Ví dụ, comment nói method luôn trả về một giá trị khác null trong khi implementation có thể trả null. Đây là lỗi nội dung cần review hoặc test, không phải lỗi cú pháp mà Doclint chắc chắn phát hiện.

## 4. Năm nhóm kiểm tra của Doclint

Javadoc hỗ trợ năm nhóm chính. Có thể bật tất cả bằng -Xdoclint:all hoặc chọn từng nhóm.

| Nhóm | Nội dung kiểm tra | Ví dụ vấn đề |
|---|---|---|
| syntax | Cú pháp comment và tag | Inline tag không đóng, tag dùng sai vị trí |
| html | Tag, thuộc tính và cấu trúc HTML | Tag không hợp lệ, lồng tag sai |
| reference | Tham chiếu trong Javadoc | Link tới class hoặc method không tồn tại |
| accessibility | Khả năng tiếp cận nội dung HTML | Ảnh thiếu mô tả thay thế |
| missing | Tài liệu còn thiếu | API cần tài liệu nhưng không có comment hoặc tag cần thiết |

### Syntax

Nhóm syntax kiểm tra cấu trúc Javadoc comment, cách viết block tag và inline tag.

Ví dụ lỗi:

~~~java
/**
 * Returns the account name.
 * See {@link User
 */
public String name() {
    return "Ada";
}
~~~

Inline tag link chưa được đóng bằng dấu ngoặc nhọn. Cách sửa:

~~~java
/**
 * Returns the account name.
 * See {@link User} for account details.
 */
public String name() {
    return "Ada";
}
~~~

Một lỗi syntax khác là đặt block tag ở vị trí không phù hợp hoặc viết sai cấu trúc tham số của tag.

### HTML

Comment Javadoc có thể chứa HTML để định dạng nội dung. Nhóm html kiểm tra các vấn đề HTML mà Doclint nhận diện.

Ví dụ cấu trúc danh sách:

~~~java
/**
 * Supported formats:
 * <ul>
 *   <li>JSON</li>
 *   <li>XML</li>
 * </ul>
 */
public void export() {
}
~~~

Hãy dùng tag HTML hợp lệ, đóng tag cần đóng và lồng phần tử theo cấu trúc phù hợp. Với nội dung inline đơn giản, các tag Javadoc như {@code ...} thường dễ đọc và an toàn hơn HTML thủ công.

### Reference

Nhóm reference kiểm tra các liên kết và tham chiếu tới declaration trong source hoặc tài liệu mà Javadoc có thể phân giải.

Ví dụ:

~~~java
/**
 * Parses a value using {@link #parse(String)}.
 *
 * @see java.time.LocalDate
 */
public Result parseValue(String value) {
    return parse(value);
}
~~~

Nếu method parse không tồn tại hoặc signature được ghi sai, Doclint có thể báo tham chiếu không phân giải được.

### Accessibility

Nhóm accessibility kiểm tra một số vấn đề tiếp cận trong nội dung HTML của Javadoc.

Ví dụ ảnh cần có mô tả thay thế:

~~~html
<img src="diagram.png" alt="Diagram of the request flow">
~~~

Với bảng, tiêu đề và cấu trúc nội dung cần rõ ràng để công nghệ hỗ trợ có thể hiểu quan hệ giữa các phần. Không nên dùng HTML chỉ để điều chỉnh hình thức mà bỏ qua ngữ nghĩa.

### Missing

Nhóm missing giúp phát hiện tài liệu chưa được viết cho API hoặc thiếu thành phần tài liệu cần thiết theo phạm vi kiểm tra.

Ví dụ:

~~~java
public class AccountService {
    public Account find(String id) {
        return null;
    }
}
~~~

Khi bật kiểm tra missing, Javadoc có thể cảnh báo declaration công khai chưa có comment. Với method, cần viết tài liệu phù hợp và các tag như @param, @return hoặc @throws khi chúng có ý nghĩa.

Phạm vi kiểm tra missing có liên quan tới mức truy cập và các phần tử mà Javadoc được yêu cầu tạo tài liệu. Tùy chọn -public, -protected, -package và -private ảnh hưởng tập declaration được đưa vào tài liệu.

## 5. Bật và tắt Doclint

Các tùy chọn Doclint là tùy chọn mở rộng của Javadoc tool. Chúng có tiền tố -X và tài liệu JDK cảnh báo rằng tùy chọn dạng này có thể thay đổi giữa các phiên bản.

### Bật các kiểm tra khuyến nghị

~~~bash
javadoc -Xdoclint -d build/docs src/com/example/api/Greeter.java
~~~

-Xdoclint bật tập kiểm tra được Javadoc khuyến nghị. Nếu cần build nhất quán giữa các máy và muốn kiểm tra rõ cả nhóm missing, hãy chỉ định -Xdoclint:all.

### Bật toàn bộ nhóm

~~~bash
javadoc -Xdoclint:all -d build/docs src/com/example/api/Greeter.java
~~~

Cấu hình này bật syntax, html, reference, accessibility và missing.

### Tắt toàn bộ nhóm

~~~bash
javadoc -Xdoclint:none -d build/docs src/com/example/api/Greeter.java
~~~

Tắt Doclint có thể hữu ích khi xử lý một codebase cũ đang có nhiều comment chưa đạt chuẩn, nhưng không nên dùng như cách sửa lỗi lâu dài. Việc tắt kiểm tra không làm comment trở nên đúng.

### Bật một số nhóm

~~~bash
javadoc -Xdoclint:syntax,html,reference \
    -d build/docs \
    src/com/example/api/Greeter.java
~~~

Ví dụ trên chỉ bật ba nhóm syntax, html và reference.

### Bật tất cả trừ một nhóm

~~~bash
javadoc -Xdoclint:all,-missing \
    -d build/docs \
    src/com/example/api/Greeter.java
~~~

Dạng này hữu ích khi dự án muốn kiểm tra cấu trúc, HTML, link và accessibility nhưng chưa muốn yêu cầu toàn bộ API cũ phải có comment.

### Tắt một nhóm cụ thể

~~~bash
javadoc -Xdoclint:all,-html \
    -d build/docs \
    src/com/example/api/Greeter.java
~~~

Chỉ tắt html trong khi giữ các nhóm khác. Nên ghi lý do cho ngoại lệ và có kế hoạch khắc phục nếu HTML lỗi ảnh hưởng người đọc.

### Kiểm tra package cụ thể

Javadoc còn hỗ trợ phạm vi package:

~~~bash
javadoc -Xdoclint:all \
    -Xdoclint/package:com.example.api.* \
    -d build/docs \
    src/com/example/api/Greeter.java
~~~

Package specifier có thể là tên package đầy đủ hoặc prefix kết thúc bằng .* để bao gồm các subpackage. Có thể đặt dấu trừ trước package specifier để loại package đó khỏi kiểm tra theo phạm vi này.

Dùng package filter khi dự án đang migration từng phần. Cần đọc trợ giúp của JDK đang dùng để xác nhận cú pháp và cách kết hợp filter với các nhóm kiểm tra.

## 6. Phân biệt -Xdoclint và -Werror

Hai tùy chọn này làm hai việc khác nhau:

- **-Xdoclint:** quyết định loại vấn đề trong Javadoc comment nào được kiểm tra.
- **-Werror:** quyết định warning có làm build thất bại hay không.

Ví dụ:

~~~bash
javadoc -Xdoclint:all -Werror \
    -d build/docs \
    src/com/example/api/Greeter.java
~~~

Nếu Doclint phát hiện warning, -Werror khiến Javadoc kết thúc với trạng thái lỗi thay vì chỉ in cảnh báo và tiếp tục như một build chấp nhận warning.

Không phải mọi lỗi đều là warning. Một số vấn đề cú pháp hoặc tham chiếu có thể được Javadoc báo trực tiếp là error. -Werror đặc biệt hữu ích để biến warning còn lại thành điều kiện chặn CI.

Có thể dùng -Xmaxwarns và -Xmaxerrs để giới hạn số lượng warning/error được in:

~~~bash
javadoc -Xdoclint:all -Xmaxwarns 100 -Xmaxerrs 100 \
    -d build/docs \
    src/com/example/api/Greeter.java
~~~

Giới hạn số dòng hiển thị không có nghĩa các lỗi còn lại đã được sửa. Khi xử lý một codebase lớn, hãy sửa theo nhóm và chạy lại để xác nhận.

## 7. Viết Javadoc để tránh lỗi Doclint

Một documentation comment tốt cần giải thích hợp đồng của declaration, không chỉ lặp lại tên method.

Ví dụ:

~~~java
/**
 * Creates a greeting for the supplied name.
 *
 * <p>The method trims leading and trailing whitespace before
 * constructing the greeting.
 *
 * @param name the name to include; must not be null or blank
 * @return a greeting that starts with {@code Hello,}
 * @throws IllegalArgumentException if name is null or blank
 * @since 1.0
 */
public static String greet(String name) {
    if (name == null || name.isBlank()) {
        throw new IllegalArgumentException("name must not be blank");
    }
    return "Hello, " + name.trim() + "!";
}
~~~

Những điểm cần chú ý:

- Mỗi tag có cú pháp đúng.
- @param dùng đúng tên tham số.
- @return mô tả giá trị trả về của method không void.
- @throws tham chiếu tới exception hợp lệ và mô tả điều kiện ném.
- {@code ...} đánh dấu đoạn code inline.
- HTML paragraph được sử dụng có cấu trúc.
- Mô tả không khẳng định hành vi khác với implementation.

### @param cho generic type

Với generic declaration, tài liệu tham số kiểu dùng cú pháp có dấu ngoặc nhọn:

~~~java
/**
 * Stores a value of the requested type.
 *
 * @param <T> the type of value stored
 */
public final class Box<T> {
}
~~~

Nếu bỏ dấu ngoặc nhọn hoặc viết sai tên type parameter, Javadoc có thể báo lỗi tag hoặc missing documentation.

### @return và @throws

Method trả về giá trị nên có @return mô tả ý nghĩa giá trị đó:

~~~java
/**
 * Returns the number of active users.
 *
 * @return the number of active users; never negative
 */
public int activeCount() {
    return 0;
}
~~~

Method có thể ném exception nên mô tả điều kiện:

~~~java
/**
 * Loads an account.
 *
 * @param id account identifier
 * @return the matching account
 * @throws IllegalArgumentException if id is null or blank
 * @throws AccountNotFoundException if no account matches id
 */
public Account load(String id) {
    // implementation
}
~~~

Doclint có thể kiểm tra tham chiếu type và tag; nó không chứng minh điều kiện ném exception có đúng trong mọi đường chạy. Điều đó vẫn cần review và test.

### @deprecated

Khi API không còn nên được sử dụng, ghi rõ thay thế:

~~~java
/**
 * Returns the old account label.
 *
 * @deprecated Use {@link #displayName()} instead.
 */
@Deprecated
public String oldLabel() {
    return displayName();
}
~~~

Annotation @Deprecated ảnh hưởng compiler và tooling. Tag @deprecated cung cấp lời giải thích cho người đọc Javadoc. Hai thành phần bổ trợ nhau.

## 8. Kiểm tra HTML trong Javadoc

HTML trong documentation comment giúp tạo đoạn văn, danh sách, bảng và hình minh họa. Tuy nhiên, comment không phải trang HTML tùy ý: Javadoc xử lý nội dung theo quy tắc và phiên bản HTML mà standard doclet hỗ trợ.

Ví dụ danh sách:

~~~java
/**
 * Supported transports:
 * <ul>
 *   <li>HTTP</li>
 *   <li>HTTPS</li>
 * </ul>
 */
public void connect() {
}
~~~

Ví dụ bảng:

~~~java
/**
 * <table>
 *   <caption>Retry policy</caption>
 *   <tr>
 *     <th scope="col">Attempt</th>
 *     <th scope="col">Delay</th>
 *   </tr>
 *   <tr>
 *     <td>1</td>
 *     <td>100 ms</td>
 *   </tr>
 * </table>
 */
public void retry() {
}
~~~

Để giảm lỗi:

- Dùng tag HTML được hỗ trợ trong Javadoc.
- Đóng tag và lồng phần tử đúng cấu trúc.
- Dùng {@code ...} cho code inline.
- Dùng {@literal ...} khi muốn hiển thị ký tự có ý nghĩa HTML mà không diễn giải như markup.
- Tránh các tag HTML lỗi thời hoặc thuộc tính không hợp lệ.
- Dùng alt text cho hình.
- Dùng heading theo thứ tự hợp lý, không dùng heading chỉ để làm chữ to.
- Dùng caption và header cho bảng khi phù hợp.

Ví dụ {@literal}:

~~~java
/**
 * The expression {@literal <T>} represents a type parameter.
 */
public void describeType() {
}
~~~

Doclint kiểm tra cấu trúc mà nó nhận diện, nhưng không thể thay thế kiểm tra trực quan trang HTML trên trình duyệt hoặc kiểm tra accessibility đầy đủ bằng công cụ chuyên dụng.

## 9. Kiểm tra link và reference

Javadoc hỗ trợ liên kết tới declaration bằng inline tag:

~~~java
/**
 * Uses {@link java.time.LocalDate} to represent a calendar date.
 */
public void dateExample() {
}
~~~

Liên kết tới member trong cùng class:

~~~java
/**
 * Parses the supplied text. See {@link #parseStrict(String)}.
 */
public Result parse(String text) {
    return parseStrict(text);
}
~~~

Liên kết có nhãn hiển thị:

~~~java
/**
 * See {@link java.time.LocalDate LocalDate documentation}.
 */
public void dateExample() {
}
~~~

Một số tag liên quan:

- **{@link ...}:** tạo liên kết inline.
- **{@linkplain ...}:** tạo liên kết inline nhưng hiển thị văn bản thường.
- **{@see ...}:** tạo phần See Also.
- **@throws:** tham chiếu exception có thể được ném.
- **@param:** tham chiếu tham số hoặc type parameter.
- **@return:** mô tả giá trị trả về.

Nếu link trỏ tới overload, ghi signature đủ rõ để Javadoc phân giải:

~~~java
/**
 * Delegates to {@link #parse(String, boolean)}.
 */
public Result parse(String text) {
    return parse(text, false);
}
~~~

Nếu liên kết tới tài liệu bên ngoài, có thể cấu hình liên kết bằng -link hoặc -linkoffline. Những tùy chọn này điều khiển cách Javadoc tìm tài liệu tham chiếu; chúng không sửa link nội bộ bị sai.

Ví dụ:

~~~bash
javadoc -Xdoclint:all \
    -link https://docs.oracle.com/en/java/javase/17/docs/api/ \
    -d build/docs \
    src/com/example/api/Greeter.java
~~~

Khi build offline hoặc dùng tài liệu API đã tải về, dùng -linkoffline với URL tài liệu và vị trí package-list hoặc element-list phù hợp với bộ tài liệu được liên kết.

## 10. Phạm vi declaration được kiểm tra

Javadoc có các tùy chọn xác định mức truy cập của declaration được đưa vào tài liệu:

| Tùy chọn | Phạm vi tài liệu |
|---|---|
| -public | Chỉ public |
| -protected | Public và protected; đây là mức mặc định phổ biến |
| -package | Public, protected và package-private |
| -private | Tất cả, gồm private |

Ví dụ:

~~~bash
javadoc -private -Xdoclint:all \
    -d build/docs \
    src/com/example/api/Greeter.java
~~~

Khi mở rộng phạm vi sang private, Javadoc xử lý thêm nhiều declaration nội bộ. Điều này có thể làm phát sinh nhiều warning missing hơn nếu dự án không viết comment cho private members.

Phạm vi declaration và nhóm Doclint là hai trục cấu hình khác nhau:

- Nhóm Doclint quyết định loại vấn đề cần kiểm tra.
- Tùy chọn visibility quyết định declaration nào được đưa vào tài liệu.
- Package filter giới hạn package được kiểm tra.

Khi thiết lập CI, hãy ghi rõ cả ba để mọi developer có cùng kỳ vọng về kết quả.

## 11. Ví dụ thực hành hoàn chỉnh với Java 17+

Ví dụ này tạo một API nhỏ có Javadoc hợp lệ, sinh HTML và chạy chương trình kiểm tra hành vi. Cùng source được dùng cho javac và javadoc.

Cấu trúc:

~~~text
doclint-demo/
└── src/
    └── com/
        └── example/
            └── doclint/
                ├── Greeter.java
                └── Main.java
~~~

### Greeter.java

~~~java
package com.example.doclint;

/**
 * Creates simple greeting messages.
 *
 * <p>This class is a small example of an API with complete
 * documentation comments.
 *
 * @since 1.0
 */
public final class Greeter {

    private Greeter() {
    }

    /**
     * Creates a greeting for the supplied name.
     *
     * <p>Leading and trailing whitespace are removed before
     * the greeting is returned.
     *
     * @param name the name to include; must not be null or blank
     * @return a greeting that starts with {@code Hello,}
     * @throws IllegalArgumentException if name is null or blank
     * @see String#trim()
     * @since 1.0
     */
    public static String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return "Hello, " + name.trim() + "!";
    }
}
~~~

### Main.java

~~~java
package com.example.doclint;

/**
 * Runs the greeting example.
 */
public final class Main {

    private Main() {
    }

    /**
     * Prints a greeting for the first command-line argument.
     *
     * @param args command-line arguments; the first item is a name
     */
    public static void main(String[] args) {
        String name = args.length == 0 ? "Java" : args[0];
        System.out.println(Greeter.greet(name));
    }
}
~~~

### Biên dịch source

Từ thư mục gốc doclint-demo:

~~~bash
mkdir -p build/classes
javac --release 17 -d build/classes \
    src/com/example/doclint/Greeter.java \
    src/com/example/doclint/Main.java
~~~

### Chạy chương trình

~~~bash
java -cp build/classes com.example.doclint.Main Java
~~~

Output chính xác:

~~~text
Hello, Java!
~~~

### Chạy Javadoc với toàn bộ Doclint

~~~bash
javadoc --release 17 \
    -Xdoclint:all \
    -Werror \
    -d build/docs \
    src/com/example/doclint/Greeter.java \
    src/com/example/doclint/Main.java
~~~

Nếu comment hợp lệ và không có warning khác, lệnh kết thúc thành công và tạo tài liệu trong build/docs.

Một số file đầu ra:

~~~text
build/docs/
├── index.html
├── allclasses-index.html
├── allpackages-index.html
└── com/
    └── example/
        └── doclint/
            ├── Greeter.html
            ├── Main.html
            └── package-summary.html
~~~

Tập file chính xác có thể thay đổi theo phiên bản JDK và tùy chọn Javadoc. Mở Greeter.html để kiểm tra nội dung, link và định dạng thực tế.

## 12. Ví dụ comment lỗi và cách sửa

### Link tới declaration không tồn tại

Comment lỗi:

~~~java
/**
 * Uses {@link #formatName(String)}.
 */
public String displayName(String name) {
    return name.trim();
}
~~~

Nếu không có method formatName(String), nhóm reference có thể báo link không phân giải được.

Sửa bằng cách trỏ tới method thực tế:

~~~java
/**
 * Uses {@link #displayName(String)}.
 */
public String displayName(String name) {
    return name.trim();
}
~~~

Hoặc mô tả hành vi mà không tạo link nếu không cần liên kết.

### Sai tên tham số

Comment lỗi:

~~~java
/**
 * Returns the greeting.
 *
 * @param username the name
 */
public String greet(String name) {
    return "Hello, " + name;
}
~~~

Tên trong @param phải khớp tham số thật. Sửa:

~~~java
/**
 * Returns the greeting.
 *
 * @param name the name
 * @return the greeting
 */
public String greet(String name) {
    return "Hello, " + name;
}
~~~

### Thiếu return documentation

Nếu bật nhóm missing, public method trả về giá trị nhưng không mô tả kết quả có thể bị cảnh báo. Bổ sung @return với ý nghĩa cụ thể, không chỉ ghi "the result".

### HTML thiếu thông tin tiếp cận

Comment có hình:

~~~java
/**
 * <img src="architecture.png">
 */
public void start() {
}
~~~

Nên bổ sung alt text:

~~~java
/**
 * <img src="architecture.png" alt="Application component architecture">
 */
public void start() {
}
~~~

Alt text cần mô tả mục đích hoặc thông tin của hình trong ngữ cảnh. Nếu hình chỉ trang trí, cách xử lý phù hợp có thể khác tùy nội dung và yêu cầu accessibility.

### HTML lồng sai

Comment lỗi:

~~~java
/**
 * <ul>
 *   <p>Supported modes</p>
 *   <li>Fast</li>
 * </ul>
 */
public void modes() {
}
~~~

Một danh sách nên chứa các list item. Sửa:

~~~java
/**
 * Supported modes:
 * <ul>
 *   <li>Fast</li>
 *   <li>Safe</li>
 * </ul>
 */
public void modes() {
}
~~~

Thông báo cụ thể có thể khác giữa JDK, nhưng nguyên tắc là dùng cấu trúc HTML hợp lệ và có ngữ nghĩa.

## 13. Tích hợp Doclint vào build và CI

Doclint nên chạy như một bước riêng trong pipeline tạo tài liệu. Ví dụ:

~~~text
Checkout source
      |
      v
Compile Java source
      |
      v
Run unit tests
      |
      v
Run Javadoc + Doclint
      |
      v
Publish documentation artifact
~~~

Nếu Javadoc thất bại, pipeline nên dừng trước khi publish tài liệu.

### Maven

Maven Javadoc Plugin có thể cấu hình Doclint qua cấu hình plugin. Ví dụ cấu hình ở mức ý tưởng:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-javadoc-plugin</artifactId>
    <version>3.11.2</version>
    <configuration>
        <doclint>all</doclint>
        <failOnWarnings>true</failOnWarnings>
    </configuration>
</plugin>
~~~

Tên parameter và cách ánh xạ option có thể phụ thuộc phiên bản plugin. Kiểm tra tài liệu Maven Javadoc Plugin đang dùng và chạy goal javadoc để xác nhận option thực sự được truyền tới Javadoc tool.

Có thể chạy:

~~~bash
mvn javadoc:javadoc
~~~

Nếu dự án tạo Javadoc cho nhiều module hoặc nhiều execution, cấu hình plugin cần được đặt ở đúng execution và profile.

### Gradle

Với Gradle Java plugin, task Javadoc có thể nhận option từ StandardJavadocDocletOptions:

~~~groovy
tasks.withType(Javadoc).configureEach {
    options.addBooleanOption("Xdoclint:all", true)
    options.addBooleanOption("Werror", true)
}
~~~

Cú pháp option phụ thuộc Gradle version và cách StandardJavadocDocletOptions biểu diễn option. Kiểm tra task output hoặc chạy Javadoc trực tiếp để chắc chắn JDK nhận được đúng option.

Một cấu hình khác là truyền option qua options.addStringOption khi plugin cần một giá trị. Không cấu hình đồng thời nhiều dạng option gây ra tham số trùng lặp.

### CI

Trong CI, nên:

- Dùng JDK version được dự án hỗ trợ.
- Chạy Javadoc với nhóm kiểm tra rõ ràng.
- Bật -Werror khi nhóm đã sẵn sàng xử lý warning.
- Giữ log warning/error để developer biết file và dòng nguồn.
- Chạy cùng cấu hình trên máy developer và CI.
- Lưu tài liệu đã tạo làm artifact nếu cần review.
- Không tắt toàn bộ Doclint chỉ để làm pipeline xanh.

Với codebase cũ, có thể bật syntax/html/reference trước, xử lý dần missing và accessibility, sau đó nâng lên all. Ghi lại ngoại lệ và thời điểm loại bỏ chúng.

## 14. Chẩn đoán lỗi Doclint

### Javadoc kết thúc với lỗi nhưng javac thành công

Đây là tình huống bình thường: compiler kiểm tra Java source, còn Javadoc/Doclint kiểm tra documentation comment và các tham chiếu của nó. Chạy Javadoc riêng để xem lỗi.

### Không biết warning thuộc nhóm nào

Đọc phần thông báo và vị trí file/dòng. Thử chạy từng nhóm riêng:

~~~bash
javadoc -Xdoclint:syntax -d build/docs src/com/example/api/Greeter.java
javadoc -Xdoclint:html -d build/docs src/com/example/api/Greeter.java
javadoc -Xdoclint:reference -d build/docs src/com/example/api/Greeter.java
javadoc -Xdoclint:accessibility -d build/docs src/com/example/api/Greeter.java
javadoc -Xdoclint:missing -d build/docs src/com/example/api/Greeter.java
~~~

Cách này giúp thu hẹp loại lỗi. Khi sửa xong, chạy lại toàn bộ nhóm.

### Quá nhiều cảnh báo missing trong codebase cũ

Có thể kiểm tra các nhóm còn lại trước:

~~~bash
javadoc -Xdoclint:all,-missing \
    -d build/docs \
    src/com/example/api/Greeter.java
~~~

Sau đó lập kế hoạch bổ sung comment cho API và bật missing trong CI. Không nên để ngoại lệ tồn tại vô thời hạn.

### Link tới JDK API không được phân giải

Kiểm tra reference có đúng package, class và member không. Nếu tài liệu ngoài được tạo riêng, cấu hình -link hoặc -linkoffline tới bộ tài liệu đúng phiên bản. Không sửa một link sai bằng cách tắt toàn bộ reference checking.

### Javadoc không tìm thấy kiểu trong dependency

Đặt dependency vào classpath hoặc module path phù hợp. Ví dụ:

~~~bash
javadoc --class-path "lib/api.jar" \
    -Xdoclint:all \
    -d build/docs \
    src/com/example/api/Greeter.java
~~~

Với modular source, dùng --module-path và các tùy chọn module tương ứng. Doclint không tải dependency về thay cho build tool.

### Output warning thay đổi giữa các JDK

Các nhóm Doclint là tùy chọn mở rộng và có thể thay đổi. Kiểm tra trợ giúp của JDK hiện tại:

~~~bash
javadoc -X
javadoc --help
~~~

Đưa phiên bản JDK vào build metadata để có thể giải thích khác biệt giữa môi trường developer và CI.

## 15. Giới hạn của Doclint

Doclint rất hữu ích nhưng không phải bộ đánh giá toàn diện cho tài liệu.

Nó không bảo đảm:

- Mô tả trong comment đúng với hành vi thực tế.
- Ví dụ code trong comment chắc chắn compile hoặc chạy đúng.
- Hướng dẫn sử dụng đầy đủ cho mọi tình huống.
- Nội dung có văn phong rõ ràng hoặc phù hợp người đọc.
- Link tới website bên ngoài luôn hoạt động.
- Trang Javadoc hiển thị đẹp trên mọi trình duyệt.
- Toàn bộ yêu cầu accessibility của website đã được đáp ứng.
- API có thiết kế tốt hoặc backward compatible.

Vì vậy, nên kết hợp:

1. Doclint để phát hiện lỗi cấu trúc.
2. Compiler và test để xác nhận hành vi.
3. Review nội dung để xác nhận tính chính xác và dễ hiểu.
4. Kiểm tra HTML được tạo để xem link, bảng, hình và bố cục.
5. Công cụ accessibility chuyên dụng khi tài liệu là giao diện quan trọng cho người dùng.

Doclint là một lớp bảo vệ tự động, không thay thế trách nhiệm viết tài liệu có ích.

## 16. Quy trình viết và kiểm tra Javadoc hiệu quả

1. Viết documentation comment ngay cạnh public API.
2. Dùng câu đầu tiên mô tả mục đích declaration.
3. Mô tả tham số, kết quả và exception theo hợp đồng thật.
4. Dùng @param, @return, @throws, @since và @deprecated đúng ngữ cảnh.
5. Dùng {@code} cho identifier hoặc đoạn code ngắn.
6. Dùng {@link} khi liên kết thực sự giúp người đọc.
7. Dùng HTML có cấu trúc và chú ý accessibility.
8. Chạy javadoc -Xdoclint:all trong quá trình phát triển.
9. Sửa warning và error tại source thay vì tắt nhóm kiểm tra.
10. Dùng -Werror trong CI khi warning đã được kiểm soát.
11. Review trang HTML được tạo và kiểm tra link.
12. Ghi rõ JDK version cùng cấu hình Doclint của dự án.

Doclint giúp giữ Javadoc nhất quán với source và phát hiện lỗi trước khi tài liệu được phát hành. Khi hiểu năm nhóm kiểm tra, biết bật/tắt đúng phạm vi và tích hợp Javadoc vào CI, nhóm có thể duy trì tài liệu API đáng tin cậy qua nhiều lần thay đổi code.

## Tài liệu tham khảo

- [The javadoc Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javadoc.html)
- [Javadoc Tool User's Guide — Doclint](https://docs.oracle.com/en/java/javase/24/docs/specs/javadoc/doc-comment-spec.html)
- [Javadoc Tool User's Guide](https://docs.oracle.com/en/java/javase/24/javadoc/)
- [Maven Javadoc Plugin](https://maven.apache.org/plugins/maven-javadoc-plugin/)
- [Gradle Javadoc task](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.javadoc.Javadoc.html)
