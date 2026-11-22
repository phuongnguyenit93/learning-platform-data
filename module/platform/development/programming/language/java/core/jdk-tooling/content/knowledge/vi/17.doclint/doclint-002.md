# Lỗi HTML trong Javadoc

Javadoc tạo tài liệu HTML từ documentation comment trong mã nguồn Java. Các comment này có thể chứa mô tả văn bản, HTML, inline tags và block tags. Nếu HTML viết sai cấu trúc, trang tài liệu được tạo có thể hiển thị khác dự kiến, làm hỏng bố cục, ảnh hưởng khả năng truy cập hoặc không vượt qua bước kiểm định HTML.

**DocLint** là công cụ tích hợp trong javadoc và javac để phát hiện những vấn đề phổ biến trong documentation comment. Nhóm kiểm tra HTML có thể nhận diện một số lỗi cấu trúc như phần tử block nằm bên trong phần tử inline hoặc thiếu thẻ đóng bắt buộc. Nhóm syntax phát hiện lỗi cú pháp như dấu ngoặc nhọn HTML chưa escape. Nhóm accessibility phát hiện một số vấn đề như ảnh thiếu alt hoặc bảng thiếu thông tin mô tả.

Cần hiểu đúng giới hạn: DocLint không phải bộ kiểm định HTML5 đầy đủ, không sửa nội dung sai và không bảo đảm mọi trang HTML được tạo ra đều hợp lệ. Vì vậy, quy trình tốt cần kiểm tra cả documentation comment, kết quả javadoc và HTML cuối cùng mà người đọc sẽ mở.

## 1. HTML trong documentation comment

Javadoc hỗ trợ hai kiểu documentation comment phổ biến:

- **Traditional comment** bắt đầu bằng /** và kết thúc bằng */. Phần mô tả có thể chứa HTML, inline tags và block tags.
- **Markdown documentation comment** dùng các dòng bắt đầu bằng ///. Markdown, HTML và các Javadoc tags có thể cùng xuất hiện.

Ví dụ traditional comment:

~~~java
/**
 * Returns a normalized name.
 * <p>
 * Leading and trailing whitespace is removed.
 * </p>
 *
 * @param name input name
 * @return normalized name
 */
public String normalize(String name) {
    return name == null ? "" : name.trim();
}
~~~

Ví dụ Markdown documentation comment trên JDK hỗ trợ line doc comments:

~~~java
/// Returns a normalized name.
///
/// Leading and trailing whitespace is removed.
///
/// @param name input name
/// @return normalized name
public String normalize(String name) {
    return name == null ? "" : name.trim();
}
~~~

Dù dùng kiểu comment nào, HTML được chèn vào vẫn phải có cấu trúc phù hợp. Javadoc không tự biến một chuỗi HTML sai thành markup đúng.

HTML trong comment cần tuân theo HTML5. Với tài liệu tạo bởi standard doclet, cần chú ý thêm cấu trúc heading của trang Javadoc: comment cho module, package và type thường bắt đầu heading ở cấp 2; comment cho constructor, method, field và member khác thường bắt đầu heading ở cấp 4. Các trang HTML độc lập trong doc-files có thể bắt đầu ở heading cấp 1.

## 2. DocLint kiểm tra những nhóm lỗi nào?

DocLint chia các kiểm tra thành năm nhóm:

| Nhóm | Nội dung kiểm tra | Ví dụ |
|---|---|---|
| html | Các vấn đề cấu trúc HTML phổ biến | Phần tử block nằm trong inline element, thiếu thẻ đóng bắt buộc |
| syntax | Cú pháp documentation comment và Javadoc tags | Dấu < hoặc & chưa escape, tag Javadoc không hợp lệ |
| accessibility | Vấn đề hỗ trợ người dùng và công cụ trợ năng | img thiếu alt, table thiếu caption hoặc summary phù hợp |
| reference | Tham chiếu tới Java API elements | {@link} hoặc @see trỏ tới class/member không tồn tại |
| missing | Thiếu comment hoặc tag tài liệu | Thiếu @param, @return hoặc documentation comment |

Các nhóm này có thể được bật/tắt riêng bằng tùy chọn -Xdoclint.

Một số khác biệt quan trọng:

- Lỗi HTML cấu trúc thường được báo là error nếu có thể khiến output thất bại khi được kiểm tra bởi công cụ downstream.
- Lỗi syntax như ký tự HTML chưa escape thường được báo là error.
- Lỗi reference thường được báo là error vì có thể tạo tài liệu sai hoặc không đúng đích.
- Thiếu documentation hoặc tag thường được báo là warning vì thường không làm HTML đầu ra sai cấu trúc.
- Accessibility có thể được báo là error khi công cụ kiểm định đầu ra dự kiến cũng xem đó là lỗi.

DocLint chỉ báo vấn đề. Nó không tự thêm thẻ đóng, sửa URL, bổ sung alt hoặc viết lại documentation comment.

## 3. Lỗi thiếu thẻ đóng

Một lỗi phổ biến là mở một phần tử cần thẻ đóng nhưng không đóng nó.

Ví dụ sai:

~~~java
/**
 * <p>Returns the account information.
 * <strong>The result may be cached.
 */
public String getAccountInfo() {
    return "account";
}
~~~

Trong ví dụ, thẻ p và strong chưa được đóng. Browser có thể tự điều chỉnh DOM khi hiển thị, nhưng kết quả sửa chữa tự động của browser không bảo đảm giống nhau giữa các cấu trúc và công cụ kiểm định.

Cách sửa:

~~~java
/**
 * <p>Returns the account information.</p>
 * <p><strong>The result may be cached.</strong></p>
 */
public String getAccountInfo() {
    return "account";
}
~~~

Với các phần tử như p, div, strong, em, a, ul, ol, li và table, hãy kiểm tra vị trí mở và đóng rõ ràng. Một số thẻ trong HTML5 có end tag tùy chọn, nhưng viết tường minh thường giúp comment dễ đọc và giảm nhầm lẫn.

Các phần tử void như img, br, hr và meta không có thẻ đóng riêng. Trong HTML5, viết img với các thuộc tính cần thiết thay vì cố tạo một cặp thẻ img mở/đóng.

## 4. Lỗi lồng phần tử sai cấu trúc

HTML có quy tắc về loại phần tử nào được phép nằm bên trong phần tử khác. Không phải cứ đóng đủ thẻ là cấu trúc đã hợp lệ.

### Đặt block element bên trong inline element

Ví dụ sai:

~~~html
<span>
    <div>Configuration details</div>
</span>
~~~

span là inline phrasing content; không nên chứa div là block flow content.

Sửa bằng cách dùng container phù hợp:

~~~html
<div>
    <p>Configuration details</p>
</div>
~~~

Hoặc nếu chỉ cần nhấn mạnh một cụm từ:

~~~html
<p>
    The configuration is <strong>required</strong>.
</p>
~~~

### Lồng p bên trong p

Ví dụ sai:

~~~html
<p>
    First paragraph.
    <p>Second paragraph.</p>
</p>
~~~

Một p không được chứa một p khác. Sửa thành hai đoạn độc lập:

~~~html
<p>First paragraph.</p>
<p>Second paragraph.</p>
~~~

### Đặt phần tử sai vị trí trong danh sách

Ví dụ không nên dùng:

~~~html
<ul>
    <p>Available options</p>
    <li>Fast mode</li>
    <li>Safe mode</li>
</ul>
~~~

Đặt phần giới thiệu trước danh sách:

~~~html
<p>Available options:</p>
<ul>
    <li>Fast mode</li>
    <li>Safe mode</li>
</ul>
~~~

Mỗi mục danh sách nên nằm trong li. Nếu một mục cần nhiều đoạn hoặc một danh sách con, đặt chúng bên trong li tương ứng.

## 5. Lỗi bảng HTML

Bảng trong Javadoc thường dùng để trình bày tham số, trạng thái hoặc các lựa chọn. Những lỗi thường gặp gồm:

- Thiếu cấu trúc tr hoặc đặt td/th ngoài hàng.
- Lồng bảng hoặc phần tử block sai vị trí.
- Thiếu tiêu đề cột.
- Không có caption hoặc mô tả phù hợp.
- Sử dụng bảng chỉ để căn chỉnh bố cục thay vì biểu diễn dữ liệu dạng bảng.

Ví dụ sai:

~~~html
<table>
    <tr>
        <td>Mode</td>
        <td>Description
    </tr>
</table>
~~~

Ô thứ hai chưa đóng và bảng không có thông tin tiêu đề rõ ràng.

Ví dụ sửa:

~~~html
<table>
    <caption>Available execution modes</caption>
    <thead>
        <tr>
            <th scope="col">Mode</th>
            <th scope="col">Description</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td>Fast</td>
            <td>Optimized execution.</td>
        </tr>
        <tr>
            <td>Safe</td>
            <td>Additional validation.</td>
        </tr>
    </tbody>
</table>
~~~

Giải thích:

- caption mô tả nội dung bảng.
- thead nhóm hàng tiêu đề.
- tbody nhóm các hàng dữ liệu.
- th đánh dấu ô tiêu đề.
- scope="col" cho biết tiêu đề áp dụng cho cột.
- Mỗi tr chứa các ô td hoặc th tương ứng.

Không phải mọi bảng đều bắt buộc có cùng cấu trúc phức tạp, nhưng caption và header rõ ràng giúp người dùng trình đọc màn hình hiểu dữ liệu tốt hơn.

## 6. Lỗi ảnh thiếu alt và accessibility

Ảnh trong Javadoc cần có văn bản thay thế phù hợp. Nếu ảnh truyền tải thông tin nhưng thiếu alt, người dùng không nhìn thấy ảnh có thể mất nội dung quan trọng.

Ví dụ sai:

~~~html
<img src="images/module-graph.png">
~~~

Ví dụ sửa:

~~~html
<img src="images/module-graph.png"
     alt="Module app depends on library and model">
~~~

Nếu ảnh chỉ mang tính trang trí và không cung cấp thông tin, dùng alt rỗng:

~~~html
<img src="images/decorative-divider.png" alt="">
~~~

Một số nguyên tắc:

- Mô tả nội dung hoặc chức năng của ảnh, không chỉ ghi "image" hoặc "picture".
- Không lặp lại nguyên văn caption nếu điều đó không giúp người đọc.
- Không dùng tên file làm alt nếu tên file không mô tả ảnh.
- Với sơ đồ phức tạp, cung cấp thêm phần giải thích bằng văn bản gần ảnh.
- Kiểm tra đường dẫn ảnh để bảo đảm resource thực sự được copy vào tài liệu.

Với bảng, hãy thêm caption hoặc tiêu đề phù hợp và đánh dấu hàng/cột tiêu đề bằng th. Nhóm accessibility của DocLint phát hiện một số vấn đề thường gặp như ảnh thiếu alt hoặc bảng thiếu thông tin mô tả.

## 7. Lỗi link và thuộc tính HTML

Link trong documentation comment thường dùng thẻ a. Các lỗi thường gặp:

- Thiếu href hoặc giá trị href sai.
- Thiếu dấu nháy bao quanh giá trị thuộc tính.
- URL có ký tự & chưa escape.
- Lồng một thẻ a bên trong một thẻ a khác.
- Link không có nhãn có ý nghĩa.
- Dùng đường dẫn tương đối nhưng không tồn tại trong output.

Ví dụ sai:

~~~html
<a href=https://example.com/search?a=1&b=2>Search</a>
~~~

Sửa:

~~~html
<a href="https://example.com/search?a=1&amp;b=2">Search documentation</a>
~~~

Khi trỏ tới Java API, nên ưu tiên Javadoc reference tags:

~~~java
/**
 * Uses {@link java.util.List} to store results.
 * See {@link java.lang.String#trim()} for whitespace handling.
 */
~~~

Cách này giúp Javadoc phân giải class và member theo Java API, đồng thời tạo link đúng trang trong bộ tài liệu.

Ví dụ link lồng nhau sai:

~~~html
<a href="https://example.com">
    Documentation <a href="https://example.com/api">More</a>
</a>
~~~

Sửa bằng cách tách thành hai link:

~~~html
<a href="https://example.com">Documentation</a>
<a href="https://example.com/api">API reference</a>
~~~

DocLint reference kiểm tra tham chiếu Java trong Javadoc tags; nó không bảo đảm mọi URL web trong href đều tồn tại hoặc phản hồi thành công. Dùng link checker riêng để kiểm tra URL bên ngoài và đường dẫn resource trong output.

## 8. Lỗi ký tự đặc biệt chưa escape

Trong documentation comment, các ký tự <, > và & có ý nghĩa trong HTML. Khi muốn hiển thị chúng như văn bản, cần escape đúng cách.

| Ký tự muốn hiển thị | Cách viết |
|---|---|
| < | &lt; |
| > | &gt; |
| & | &amp; |

Ví dụ sai:

~~~java
/**
 * Accepts a List<String> as input.
 * The condition is a < b && b > 0.
 */
~~~

Javadoc có thể diễn giải <String> như một HTML tag và các dấu <, >, & như markup hoặc ký tự cú pháp.

Cách sửa khi mô tả code:

~~~java
/**
 * Accepts a {@code List<String>} as input.
 * The condition is {@code a < b && b > 0}.
 */
~~~

Hoặc dùng HTML entities:

~~~java
/**
 * Accepts a List&lt;String&gt; as input.
 * The condition is a &lt; b &amp;&amp; b &gt; 0.
 */
~~~

{@code} phù hợp khi hiển thị identifier, biểu thức hoặc đoạn code ngắn. {@literal} phù hợp khi cần hiển thị nội dung literal mà không diễn giải như HTML hoặc nested Javadoc tag.

Không nên dùng HTML entity cho toàn bộ code một cách máy móc. Hãy chọn {@code}, {@literal} hoặc entity theo mục đích hiển thị.

## 9. Lỗi tag Javadoc bị nhầm với HTML

Một documentation comment có hai nhóm cú pháp cần phân biệt:

- HTML tags như p, div, a, table và img.
- Javadoc tags như @param, @return, @throws, {@link} và {@code}.

Ví dụ:

~~~java
/**
 * Returns the account identifier.
 *
 * @param accountId account identifier
 * @return formatted identifier
 */
~~~

Các block tags bắt đầu ở đầu dòng, sau khoảng trắng và dấu * mở đầu comment. Nếu một dòng văn bản bắt đầu bằng @ nhưng không phải Javadoc tag, Javadoc có thể hiểu nhầm nó là block tag.

Ví dụ muốn hiển thị một email hoặc ký hiệu @ ở đầu dòng:

~~~java
/**
 * Contact: &#064;support.example.com
 */
~~~

Dùng entity để hiển thị dấu @ ở đầu dòng mà không tạo block tag.

Nếu viết sai tên tag hoặc sai vị trí tag, DocLint có thể báo lỗi nhóm syntax. Nếu tag hợp lệ nhưng tham chiếu tới method, field hoặc tham số không tồn tại, đó thường là lỗi nhóm reference.

## 10. Heading và id trong trang Javadoc

Trang Javadoc được standard doclet tạo đã có cấu trúc heading riêng. Nếu documentation comment tự thêm heading không đúng cấp, cấu trúc tài liệu có thể khó điều hướng bằng bàn phím hoặc trình đọc màn hình.

Theo quy tắc HTML trong Javadoc JDK 26:

| Vị trí comment | Cấp heading nên bắt đầu |
|---|---|
| Module declaration | h2 |
| Package declaration | h2 |
| Class/interface/type | h2 |
| Constructor và member | h4 |
| HTML độc lập trong doc-files | h1 |

Ví dụ trong method comment, không nên tự mở h1:

~~~java
/**
 * <h1>Configuration</h1>
 * Explains the configuration options.
 */
public void configure() {
}
~~~

Nên dùng heading phù hợp với vị trí member:

~~~java
/**
 * <h4>Configuration</h4>
 * Explains the configuration options.
 */
public void configure() {
}
~~~

Với đoạn nội dung ngắn, dùng p hoặc strong có thể phù hợp hơn là tạo heading mới.

### Thuộc tính id

Standard doclet dùng các identifier để tạo anchor cho class và member. Nếu tự đặt id trùng với identifier Java, có thể xảy ra xung đột.

Ví dụ không nên dùng:

~~~html
<div id="normalize">Normalization rules</div>
~~~

Nếu class có method tên normalize, id này có thể xung đột với anchor do Javadoc tạo.

Sửa bằng id có ký tự không hợp lệ trong Java identifier, chẳng hạn dấu gạch nối:

~~~html
<div id="normalization-rules">Normalization rules</div>
~~~

Mỗi id vẫn phải duy nhất trong trang HTML được tạo.

## 11. Dùng pre, code và snippet đúng cách

Code sample thường là nơi phát sinh lỗi HTML vì dấu ngoặc nhọn và ký tự đặc biệt của Java dễ bị hiểu nhầm thành markup.

Ví dụ dùng {@code} cho biểu thức ngắn:

~~~java
/**
 * Returns a {@code List<String>} containing the results.
 */
~~~

Với code block:

~~~java
/**
 * Example:
 * <pre>{@code
 * List<String> names = List.of("Ada", "Grace");
 * System.out.println(names);
 * }</pre>
 */
~~~

Javadoc xử lý nội dung {@code} như literal code và hiển thị trong kiểu chữ monospace. pre giữ khoảng trắng và xuống dòng của đoạn code.

Với JDK hiện đại, có thể dùng {@snippet} để trình bày code sample có syntax highlighting và khả năng tham chiếu snippet bên ngoài:

~~~java
/**
 * Example:
 * {@snippet :
 * List<String> names = List.of("Ada", "Grace");
 * System.out.println(names);
 * }
 */
~~~

Khi dùng HTML pre/code trực tiếp, cấu trúc nên là:

~~~html
<pre><code class="language-java">
System.out.println("Hello");
</code></pre>
~~~

Không đặt p, div hoặc một block element khác vào giữa pre/code theo cách làm sai cấu trúc. Không chèn code Java thô có ký tự < và & vào HTML mà không dùng {@code}, {@snippet}, {@literal} hoặc escape entity phù hợp.

## 12. Chạy DocLint để tìm lỗi HTML

JDK 26 hỗ trợ các tùy chọn:

| Tùy chọn | Công dụng |
|---|---|
| -Xdoclint | Bật các kiểm tra được khuyến nghị cho documentation comment |
| -Xdoclint:html | Chỉ kiểm tra nhóm HTML |
| -Xdoclint:syntax | Kiểm tra cú pháp comment, ký tự escape và tag |
| -Xdoclint:accessibility | Kiểm tra các vấn đề accessibility |
| -Xdoclint:reference | Kiểm tra reference tới Java API elements |
| -Xdoclint:missing | Kiểm tra comment và tag bị thiếu |
| -Xdoclint:all | Bật tất cả các nhóm kiểm tra |
| -Xdoclint:none | Tắt tất cả DocLint checks |
| -Werror | Chuyển warning thành lỗi build |

Trong javadoc của JDK 26, DocLint được bật mặc định. Có thể chỉ định rõ nhóm muốn kiểm tra để lệnh build dễ đọc và nhất quán.

Kiểm tra HTML, syntax và accessibility:

~~~bash
javadoc -Xdoclint:html,syntax,accessibility -d docs -sourcepath src -subpackages com.example.api
~~~

Kiểm tra tất cả nhóm và làm build thất bại khi có warning:

~~~bash
javadoc -Xdoclint:all -Werror -encoding UTF-8 -d docs -sourcepath src -subpackages com.example.api
~~~

Nếu chỉ muốn kiểm tra HTML:

~~~bash
javadoc -Xdoclint:html -d docs -sourcepath src -subpackages com.example.api
~~~

Để loại trừ một nhóm khỏi tất cả kiểm tra:

~~~bash
javadoc -Xdoclint:all,-missing -d docs -sourcepath src -subpackages com.example.api
~~~

Không nên tắt toàn bộ DocLint chỉ để làm build xanh. Nếu có warning hoặc error, hãy xác định nhóm, đọc vị trí được báo và sửa nguyên nhân trong comment.

## 13. Đọc và xử lý diagnostic

Khi phát hiện lỗi, javadoc thường in loại diagnostic, tên file, dòng và vị trí ký tự. Ví dụ minh họa:

~~~text
NameFormatter.java:12: error: element not closed: p
 * <p>Returns the normalized value.
   ^
1 error
~~~

Thông báo thực tế phụ thuộc JDK và loại markup. Khi xử lý:

1. Xác định file và dòng được báo.
2. Đọc toàn bộ documentation comment chứa dòng đó.
3. Xác định lỗi thuộc html, syntax, accessibility, reference hay missing.
4. Sửa HTML hoặc Javadoc tag tại nguồn.
5. Chạy lại cùng lệnh javadoc.
6. Kiểm tra output HTML để bảo đảm bố cục và nội dung đúng.

Một lỗi có thể gây nhiều diagnostic vì markup lồng nhau sai làm parser diễn giải phần tiếp theo theo cách không mong muốn. Hãy sửa lỗi cấu trúc đầu tiên rồi chạy lại trước khi xử lý các cảnh báo còn lại.

## 14. Ví dụ hoàn chỉnh: sửa HTML trong Javadoc

Tạo file NameFormatter.java:

~~~java
package com.example.api;

import java.util.List;

/**
 * Formats user-facing names.
 *
 * <p>This class normalizes whitespace before displaying names.</p>
 *
 * <h2>Examples</h2>
 * <ul>
 *     <li>Removes leading whitespace.</li>
 *     <li>Removes trailing whitespace.</li>
 * </ul>
 *
 * <p>For more details, see {@link java.util.List}.</p>
 */
public final class NameFormatter {

    private NameFormatter() {
    }

    /**
     * Normalizes a list of names.
     *
     * <p>Example input:</p>
     * <pre>{@code
     * List<String> names = List.of("Ada ", "Grace ");
     * }</pre>
     *
     * <table>
     *     <caption>Normalization behavior</caption>
     *     <thead>
     *         <tr>
     *             <th scope="col">Input</th>
     *             <th scope="col">Output</th>
     *         </tr>
     *     </thead>
     *     <tbody>
     *         <tr>
     *             <td>" Ada "</td>
     *             <td>"Ada"</td>
     *         </tr>
     *         <tr>
     *             <td>"Grace "</td>
     *             <td>"Grace"</td>
     *         </tr>
     *     </tbody>
     * </table>
     *
     * @param names names to normalize
     * @return normalized names
     */
    public static List<String> normalizeAll(List<String> names) {
        return names.stream()
                .map(String::trim)
                .toList();
    }
}
~~~

Lưu ý trong ví dụ:

- Các thẻ p được đóng đầy đủ.
- Heading của class bắt đầu ở h2.
- Bảng có caption, thead, tbody và scope cho tiêu đề cột.
- Đoạn code dùng pre và {@code} để escape dấu ngoặc nhọn.
- Reference tới List dùng Javadoc link tag.
- @param và @return mô tả đúng method.

Tạo Javadoc trên JDK 17 trở lên:

~~~bash
javadoc -Xdoclint:all -Werror -encoding UTF-8 -d docs -sourcepath src com.example.api
~~~

Nếu source nằm tại src/com/example/api/NameFormatter.java, lệnh trên tạo tài liệu trong thư mục docs.

Có thể mở trang:

~~~text
docs/com/example/api/NameFormatter.html
~~~

Để kiểm tra trang đã tạo, xem bảng, heading, code block và link Java SE API. Chương trình Java cũng có thể được biên dịch riêng:

~~~bash
javac --release 17 -d out src/com/example/api/NameFormatter.java
~~~

Lệnh biên dịch source không thay thế lệnh javadoc; hai công cụ kiểm tra những mục đích khác nhau.

## 15. Kiểm tra HTML sau khi Javadoc tạo xong

DocLint kiểm tra documentation comment tại source. Bộ kiểm định HTML downstream kiểm tra các trang HTML hoàn chỉnh sau khi standard doclet đã tạo chúng.

Kiểm tra output HTML giúp phát hiện những vấn đề mà DocLint không thể thấy, ví dụ:

- HTML được thêm bởi custom taglet.
- HTML trong các tùy chọn header, footer, title hoặc help file.
- Xung đột giữa nội dung comment và cấu trúc do standard doclet tạo.
- Link tới resource không tồn tại trong output.
- URL bên ngoài không còn truy cập được.
- Lỗi HTML chỉ xuất hiện khi các phần nội dung được ghép thành trang hoàn chỉnh.

Quy trình kiểm tra:

1. Tạo tài liệu bằng javadoc với DocLint.
2. Mở các trang HTML quan trọng bằng browser.
3. Dùng HTML conformance validator để kiểm tra cấu trúc trang hoàn chỉnh.
4. Dùng link checker để rà soát URL nội bộ và URL bên ngoài.
5. Kiểm tra accessibility với công cụ phù hợp.
6. Chạy lại build sau khi sửa comment hoặc cấu hình doclet.

Không nên chỉ dựa vào việc javadoc kết thúc với exit code 0. Một trang có thể được tạo thành công nhưng vẫn có lỗi HTML hoặc link không đúng.

## 16. Suppress DocLint khi thực sự cần thiết

Trong một số dự án legacy, có thể tồn tại documentation comment cũ mà chưa thể sửa ngay. Javadoc cho phép suppress một số nhóm DocLint bằng annotation:

~~~java
@SuppressWarnings("doclint:html")
public class LegacyFormatter {
}
~~~

Có thể suppress nhiều nhóm:

~~~java
@SuppressWarnings({"doclint:html", "doclint:accessibility"})
public class LegacyDocumentation {
}
~~~

Một số điểm cần cân nhắc:

- Suppress chỉ ẩn diagnostic; nó không sửa HTML.
- Annotation ở declaration có thể ảnh hưởng tới declaration đó và các declaration lồng bên trong theo quy tắc DocLint.
- Suppress ở class có thể che nhiều vấn đề trong các member của class.
- Không dùng suppress cho toàn package chỉ để tránh sửa markup sai.
- Ghi rõ lý do và kế hoạch loại bỏ suppression khi có thể.

Chỉ suppress lỗi đã được xem xét và chấp nhận có chủ đích. Với lỗi HTML có thể sửa trực tiếp, hãy sửa comment thay vì tắt kiểm tra.

## 17. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân có thể | Cách khắc phục |
|---|---|---|
| element not closed | Thiếu thẻ đóng bắt buộc | Bổ sung thẻ đóng đúng vị trí |
| block element inside inline element | Lồng div, p hoặc ul trong span/a sai cách | Dùng container block phù hợp và không lồng sai loại |
| invalid HTML nesting | Lồng p, a, list hoặc table không đúng cấu trúc | Kiểm tra quy tắc nội dung của HTML5 |
| unescaped angle bracket | Viết List<String> hoặc a < b trực tiếp | Dùng {@code}, {@literal} hoặc &lt;/&gt; |
| unescaped ampersand | URL hoặc văn bản có ký tự & thô | Dùng &amp; trong HTML attribute/text |
| invalid documentation tag | Gõ sai tên tag hoặc đặt block tag sai vị trí | Kiểm tra Javadoc tag và vị trí đầu dòng |
| missing alt attribute | Ảnh thiếu văn bản thay thế | Bổ sung alt mô tả hoặc alt rỗng cho ảnh trang trí |
| table accessibility warning | Bảng thiếu caption hoặc tiêu đề rõ ràng | Bổ sung caption, th và scope |
| heading level không phù hợp | Dùng h1 trong method comment hoặc nhảy cấp heading | Chọn heading theo loại declaration |
| link Java không tìm thấy | Sai class/member hoặc signature | Kiểm tra reference và kiểu tham số |
| trang vẫn lỗi sau khi DocLint PASS | DocLint không phải HTML validator đầy đủ | Kiểm tra HTML output bằng validator riêng |
| HTML bị hỏng sau khi dùng taglet | Taglet sinh markup sai | Kiểm tra output taglet và validate trang cuối |

## 18. Checklist trước khi phát hành Javadoc

- [ ] Documentation comment dùng HTML5 hợp lệ.
- [ ] Các phần tử cần end tag được đóng đúng vị trí.
- [ ] Không lồng block và inline elements sai cấu trúc.
- [ ] Danh sách dùng li bên trong ul hoặc ol.
- [ ] Bảng có cấu trúc hàng/cột rõ ràng và caption phù hợp.
- [ ] Ảnh có alt phù hợp.
- [ ] Link có href hợp lệ và nhãn dễ hiểu.
- [ ] Không có anchor lồng nhau.
- [ ] Dấu <, > và & trong code/văn bản đã được escape.
- [ ] Heading tuân theo cấp phù hợp với module, package, type hoặc member.
- [ ] ID tùy chỉnh không xung đột với anchor của Java elements và là duy nhất.
- [ ] Javadoc chạy với -Xdoclint:all.
- [ ] CI cân nhắc -Werror để ngăn warning mới.
- [ ] HTML output được mở và kiểm tra trực quan.
- [ ] HTML validator và link checker được chạy cho tài liệu quan trọng.
- [ ] Các suppression có lý do rõ ràng và được rà soát định kỳ.

## 19. Ghi nhớ

- Lỗi HTML trong Javadoc có thể làm hỏng bố cục, khả năng truy cập hoặc tính hợp lệ của HTML output.
- DocLint có năm nhóm: html, syntax, accessibility, reference và missing.
- Nhóm html phát hiện lỗi cấu trúc phổ biến như block element nằm trong inline element hoặc thiếu thẻ đóng bắt buộc.
- Nhóm syntax phát hiện ký tự HTML chưa escape và Javadoc tag sai cú pháp.
- Nhóm accessibility kiểm tra các vấn đề như ảnh thiếu alt và bảng thiếu mô tả phù hợp.
- Dùng {@code} hoặc {@literal} để hiển thị code và ký tự đặc biệt an toàn.
- Viết heading đúng cấp theo vị trí declaration trong trang Javadoc.
- Javadoc không tự sửa HTML sai; DocLint cũng không phải trình kiểm định HTML5 đầy đủ.
- Kết hợp -Xdoclint:all, -Werror, HTML validator, link checker và kiểm tra trực quan.
- Chỉ suppress DocLint khi có lý do cụ thể; suppression không thay thế việc sửa markup.

## Tài liệu tham khảo chính thức

- [JavaDoc Documentation Comment Specification — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/javadoc/doc-comment-spec.html)
- [The javadoc Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javadoc.html)
- [JavaDoc Guide — JDK 26](https://docs.oracle.com/en/java/javase/26/javadoc/index.html)
- [HTML Living Standard](https://html.spec.whatwg.org/)
- [Web Content Accessibility Guidelines (WCAG)](https://www.w3.org/WAI/standards-guidelines/wcag/)