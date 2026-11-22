# Mã hóa đầu ra và phòng chống XSS trong View

Trong module **MODEL_VIEW_CONTROLLER**, View nhận dữ liệu từ Controller hoặc view model rồi tạo HTML, JSON hay nội dung giao diện khác cho người dùng. Dữ liệu này có thể đến từ biểu mẫu, cơ sở dữ liệu, tệp tải lên hoặc dịch vụ bên ngoài. Ngay cả khi dữ liệu đã được lưu trong hệ thống, nó vẫn có thể không đáng tin cậy. Nếu View đưa dữ liệu đó vào trang mà không xử lý đúng ngữ cảnh, trình duyệt có thể diễn giải nó thành mã JavaScript và thực thi thay vì hiển thị như văn bản.

Lỗ hổng này thường được gọi là **Cross-Site Scripting (XSS)**. Cách phòng vệ quan trọng là mã hóa đầu ra theo đúng ngữ cảnh nơi dữ liệu được chèn vào, sử dụng cơ chế tự escape của template engine và tránh các API tạo HTML thô. Controller và Model vẫn cần xác thực dữ liệu, nhưng kiểm tra đầu vào không thay thế cho việc mã hóa đầu ra tại nơi dữ liệu được hiển thị.

## 1. XSS là gì?

XSS xảy ra khi ứng dụng đưa dữ liệu không đáng tin cậy vào nội dung mà trình duyệt diễn giải như mã có thể thực thi. Kẻ tấn công có thể khiến trình duyệt của người dùng chạy script trong ngữ cảnh website hợp lệ. Khi đó, script có thể thực hiện hành động dưới quyền phiên của người dùng, đọc dữ liệu mà JavaScript được phép truy cập hoặc thay đổi nội dung trang.

Ví dụ, một ứng dụng hiển thị tên người dùng bằng cách nối trực tiếp chuỗi vào HTML:

~~~java
String html = "<p>Xin chào " + userInput + "</p>";
~~~

Nếu người dùng nhập nội dung chứa thẻ HTML và script, trình duyệt có thể phân tích nội dung đó như markup thay vì văn bản. Một payload minh họa thường gặp là:

~~~html
<img src=x onerror=alert(1)>
~~~

Khi chuỗi trên được chèn vào HTML mà không escape, trình duyệt có thể tạo phần tử ảnh và chạy event handler khi tải ảnh thất bại. Trong ứng dụng thật, kẻ tấn công có thể thay đoạn thử nghiệm này bằng script thực hiện hành vi có hại.

XSS là vấn đề ở ranh giới giữa dữ liệu và mã. Dữ liệu có thể hoàn toàn hợp lệ theo cú pháp của ứng dụng nhưng vẫn nguy hiểm nếu được đặt sai ngữ cảnh trong HTML hoặc JavaScript.

## 2. Các dạng XSS thường gặp

| Dạng | Cách xảy ra | Ví dụ |
| --- | --- | --- |
| **Stored XSS** | Dữ liệu độc hại được lưu lại rồi hiển thị cho người khác | Bình luận hoặc tên hiển thị được lưu trong database và render không escape |
| **Reflected XSS** | Dữ liệu trong request được phản chiếu ngay vào response | Từ khóa tìm kiếm trong query string được đưa thẳng vào trang kết quả |
| **DOM-based XSS** | JavaScript phía trình duyệt lấy dữ liệu không tin cậy và đưa vào DOM qua một sink nguy hiểm | Script đọc location.hash rồi gán vào innerHTML |

### Stored XSS

Một người dùng gửi bình luận. Server lưu bình luận vào database. Khi người khác mở trang, template đưa nội dung vào HTML không escape. Vì dữ liệu được lưu lâu dài, nhiều người có thể bị ảnh hưởng mỗi khi xem trang đó.

### Reflected XSS

Một trang tìm kiếm lấy từ khóa từ query parameter rồi chèn vào tiêu đề hoặc thông báo. Nếu ứng dụng phản chiếu chuỗi đó thành HTML thô, một liên kết được tạo có chủ đích có thể khiến trình duyệt thực thi nội dung ngoài ý muốn.

### DOM-based XSS

Trong dạng này, lỗi có thể nằm hoàn toàn ở JavaScript phía client. Ví dụ:

~~~javascript
const message = new URLSearchParams(location.search).get("message");
document.querySelector("#message").innerHTML = message;
~~~

innerHTML yêu cầu trình duyệt phân tích chuỗi thành HTML. Nếu message do người dùng kiểm soát, nội dung có thể trở thành markup hoặc script nguy hiểm. Nếu chỉ cần hiển thị văn bản, hãy dùng textContent:

~~~javascript
const message = new URLSearchParams(location.search).get("message");
document.querySelector("#message").textContent = message ?? "";
~~~

## 3. Vì sao View phải mã hóa đầu ra?

View là nơi dữ liệu được chuyển thành nội dung mà trình duyệt diễn giải. Cùng một chuỗi có thể an toàn trong một ngữ cảnh nhưng nguy hiểm ở ngữ cảnh khác.

Ví dụ chuỗi A&B:

- Trong nội dung văn bản HTML, dấu & cần được biểu diễn phù hợp để không bị hiểu là bắt đầu một character reference.
- Trong thuộc tính HTML, dấu nháy có thể kết thúc giá trị thuộc tính nếu không được mã hóa đúng.
- Trong JavaScript, dấu nháy hoặc ký tự xuống dòng có thể làm thay đổi cấu trúc chuỗi hoặc câu lệnh.
- Trong URL, dữ liệu cần được mã hóa theo thành phần URL và URL vẫn phải được kiểm tra scheme/đích đến.

Vì vậy, không có một hàm escape duy nhất phù hợp cho mọi vị trí. Mã hóa phải dựa trên **ngữ cảnh đầu ra**:

| Ngữ cảnh | Cách xử lý |
| --- | --- |
| Nội dung văn bản HTML | HTML entity encoding |
| Giá trị thuộc tính HTML | Attribute encoding và luôn đặt giá trị trong dấu nháy |
| Thành phần URL | URL component encoding, đồng thời kiểm tra scheme và đích đến |
| Chuỗi trong JavaScript | Tránh nội suy trực tiếp; nếu bắt buộc, dùng serializer/encoder đúng ngữ cảnh |
| CSS | Tránh đưa dữ liệu không tin cậy vào CSS; nếu thật sự cần, dùng quy tắc encoding chuyên biệt |
| HTML giàu định dạng do người dùng tạo | Dùng sanitizer HTML theo allowlist trước khi render |

## 4. Mã hóa nội dung văn bản HTML

Khi cần hiển thị dữ liệu như tên, bình luận hoặc thông báo, hãy để template engine escape nội dung thành văn bản. Các ký tự có ý nghĩa đặc biệt trong HTML như &lt;, &gt;, &amp; và dấu nháy cần được mã hóa để trình duyệt không diễn giải chúng thành cấu trúc HTML.

Với Thymeleaf, dùng th:text để hiển thị văn bản:

~~~html
<p th:text="${comment.content}">Nội dung bình luận</p>
~~~

Thymeleaf escape nội dung của th:text theo chế độ HTML mặc định. Nếu comment.content chứa chuỗi &lt;img src=x onerror=alert(1)&gt;, người dùng sẽ thấy chuỗi đó như văn bản thay vì trình duyệt tạo phần tử ảnh.

Trong JSP, có thể dùng JSTL c:out với escapeXml="true":

~~~jsp
<c:out value="${comment.content}" escapeXml="true" />
~~~

Không nên tự nối chuỗi HTML trong Controller hoặc service để hiển thị dữ liệu. Hãy truyền dữ liệu trong model/view model và để View chịu trách nhiệm render bằng cơ chế escape phù hợp.

## 5. Mã hóa thuộc tính HTML

Dữ liệu đặt trong thuộc tính HTML cũng phải được mã hóa theo ngữ cảnh thuộc tính. Luôn đặt giá trị thuộc tính trong dấu nháy và dùng template binding có escape:

~~~html
<input type="text" th:value="${profile.displayName}" />
<div th:attr="data-label=${profile.displayName}"></div>
~~~

Nếu tự ghép chuỗi thuộc tính, một giá trị chứa dấu nháy có thể đóng thuộc tính hiện tại và chèn thuộc tính mới. Vì vậy, không nên viết:

~~~java
String html = "<input value='" + userInput + "'>";
~~~

Đối với HTML thuần hoặc thư viện không tự escape, dùng encoder dành riêng cho thuộc tính HTML. Với OWASP Java Encoder, có thể dùng:

~~~java
import org.owasp.encoder.Encode;

String safeText = Encode.forHtmlContent(userInput);
String safeAttribute = Encode.forHtmlAttribute(userInput);
~~~

forHtmlContent dành cho nội dung HTML; forHtmlAttribute dành cho giá trị thuộc tính. Không dùng encoder JavaScript hoặc URL thay cho encoder HTML attribute.

## 6. Mã hóa URL và kiểm tra scheme

Một URL có thể chứa dữ liệu do người dùng cung cấp, ví dụ từ khóa tìm kiếm hoặc ID. Mã hóa thành phần URL giúp ký tự đặc biệt không làm thay đổi cấu trúc URL. Tuy nhiên, URL encoding không ngăn được mọi URL nguy hiểm.

Ví dụ, một liên kết có thể nhận giá trị từ người dùng:

~~~html
<a th:href="@{/search(q=${query})}">Xem kết quả</a>
~~~

Template engine hỗ trợ xây dựng URL và mã hóa tham số phù hợp. Nếu người dùng được phép cung cấp một URL đầy đủ, ứng dụng còn phải kiểm tra scheme và đích đến theo allowlist. Không chấp nhận URL có scheme thực thi như javascript: làm đích của liên kết hoặc thuộc tính tài nguyên.

Ví dụ Java kiểm tra URL chỉ cho phép HTTPS:

~~~java
URI uri = URI.create(candidateUrl);
if (!"https".equalsIgnoreCase(uri.getScheme())) {
    throw new IllegalArgumentException("URL scheme is not allowed");
}
~~~

Đoạn mã chỉ minh họa kiểm tra scheme cơ bản. Ứng dụng thực tế còn cần kiểm tra host, port, redirect, IDN và chính sách miền được phép nếu URL được dùng để điều hướng hoặc tải tài nguyên. Chỉ URL encoding là chưa đủ để xác nhận một URL an toàn.

## 7. Tránh đưa dữ liệu không tin cậy trực tiếp vào JavaScript

Một lỗi thường gặp là nhúng giá trị từ Model vào inline script bằng cách nối chuỗi:

~~~jsp
<script>
  const displayName = '${profile.displayName}';
</script>
~~~

Ví dụ này minh họa JSP EL được xuất trực tiếp vào chuỗi JavaScript mà không có JavaScript string encoding. Nếu dữ liệu chứa dấu nháy, dấu gạch chéo hoặc ký tự đặc biệt, nó có thể phá vỡ chuỗi JavaScript. Không dùng HTML escaping như thể nó là JavaScript string encoding; hai ngữ cảnh có quy tắc khác nhau.

Ưu tiên một trong các cách sau:

- Tránh inline script phụ thuộc dữ liệu động; đặt dữ liệu vào DOM bằng thuộc tính được template escape rồi đọc bằng API DOM.
- Gửi dữ liệu qua endpoint JSON có Content-Type: application/json và dùng JSON.parse/response.json() ở client.
- Nếu bắt buộc nhúng JSON vào trang, dùng thư viện serializer đáng tin cậy và cách đặt dữ liệu an toàn theo hướng dẫn của framework; không tự nối chuỗi JSON.

Ví dụ, dữ liệu có thể được đưa vào thuộc tính data-* bằng template engine:

~~~html
<div id="profile"
     th:attr="data-display-name=${profile.displayName}"></div>
~~~

JavaScript đọc giá trị như văn bản:

~~~javascript
const profileElement = document.querySelector("#profile");
const displayName = profileElement.dataset.displayName ?? "";
document.querySelector("#welcome").textContent = displayName;
~~~

Cách này tránh đưa chuỗi người dùng vào mã JavaScript. Tuy nhiên, vẫn cần bảo đảm template engine escape thuộc tính và dữ liệu được dùng đúng cách sau khi đọc.

## 8. Phân biệt escape với sanitize HTML

Escape và sanitize giải quyết hai nhu cầu khác nhau:

- **Escape/mã hóa đầu ra:** biến dữ liệu thành văn bản an toàn trong một ngữ cảnh cụ thể. Thẻ &lt;b&gt; sẽ được hiển thị như chuỗi ký tự, không trở thành thẻ định dạng.
- **Sanitize:** lọc một tập HTML không tin cậy để chỉ giữ lại những thẻ, thuộc tính và giao thức được cho phép. Ví dụ cho phép &lt;strong&gt; và &lt;em&gt; nhưng loại bỏ script, event handler và URL nguy hiểm.

Nếu sản phẩm chỉ cần bình luận dạng văn bản, hãy escape và hiển thị như văn bản. Không cần cho phép HTML. Nếu sản phẩm thực sự cần nội dung rich text, hãy dùng thư viện sanitizer đã được duy trì, cấu hình allowlist nhỏ và cập nhật thư viện thường xuyên.

Không dùng regex tự viết để loại bỏ &lt;script&gt; hoặc các chuỗi đáng ngờ. XSS có nhiều cách biểu diễn và ngữ cảnh; bộ lọc đơn giản thường bỏ sót biến thể hoặc phá nội dung hợp lệ.

Ví dụ với Thymeleaf:

~~~html
<!-- Hiển thị như văn bản, có escape -->
<div th:text="${article.body}"></div>

<!-- Chèn HTML thô; chỉ dùng khi nội dung đã được sanitizer đáng tin cậy xử lý -->
<div th:utext="${article.sanitizedHtml}"></div>
~~~

th:utext không escape nội dung. Không truyền dữ liệu người dùng trực tiếp vào th:utext. Nếu dùng rich text, tên thuộc tính sanitizedHtml nên thể hiện rõ dữ liệu đã qua sanitizer; ranh giới này cần được kiểm soát và kiểm thử.

## 9. Những API DOM cần thận trọng

XSS có thể xuất hiện sau khi trang đã tải nếu JavaScript đưa dữ liệu không tin cậy vào API có khả năng diễn giải mã.

| API hoặc thuộc tính | Rủi ro / cách dùng |
| --- | --- |
| innerHTML | Phân tích chuỗi thành HTML; tránh với dữ liệu không tin cậy |
| outerHTML | Thay thế phần tử bằng HTML; tránh đưa chuỗi không tin cậy vào |
| insertAdjacentHTML | Chèn chuỗi HTML; cần sanitizer nếu dữ liệu không tin cậy |
| document.write | Ghi HTML vào tài liệu; tránh dùng với dữ liệu động |
| eval, Function | Diễn giải chuỗi thành mã; không đưa dữ liệu người dùng vào |
| textContent | Đặt nội dung văn bản; phù hợp khi chỉ cần hiển thị text |
| createTextNode | Tạo node văn bản; phù hợp cho nội dung text |
| setAttribute | Phải xét loại thuộc tính; thuộc tính sự kiện hoặc URL vẫn có rủi ro |

Không phải mọi thuộc tính đều an toàn chỉ vì dùng setAttribute. Ví dụ, đặt một URL không tin cậy vào href vẫn cần kiểm tra scheme; đặt chuỗi vào onclick vẫn là đưa dữ liệu vào ngữ cảnh mã.

Với frontend framework, cơ chế render văn bản thường escape mặc định. Tuy nhiên, các API chèn HTML thô như dangerouslySetInnerHTML trong React hoặc directive tương đương ở framework khác cần được coi là ranh giới nhạy cảm và chỉ dùng với nội dung đã được xử lý an toàn.

## 10. Vì sao validation đầu vào không thay thế output encoding?

Validation đầu vào xác định dữ liệu có đáp ứng quy tắc nghiệp vụ hay không, ví dụ tên không rỗng hoặc độ dài không vượt giới hạn. Output encoding bảo đảm dữ liệu được diễn giải đúng khi đặt vào một ngữ cảnh đầu ra.

Một chuỗi tên như Alex &lt;Admin&gt; có thể hợp lệ theo nghiệp vụ nếu hệ thống cho phép ký tự &lt; và &gt;. Ứng dụng vẫn cần escape khi hiển thị trong HTML. Ngược lại, một chuỗi có thể được escape an toàn trong HTML nhưng không hợp lệ theo quy tắc nghiệp vụ.

Hãy áp dụng cả hai ở đúng nơi:

- **Validation:** tại biên nhận dữ liệu và trong use case/Model cho các quy tắc nghiệp vụ.
- **Authorization:** xác minh người dùng có quyền thực hiện hành động hoặc xem tài nguyên.
- **Output encoding:** ngay tại điểm dữ liệu được đưa vào HTML, thuộc tính, URL, JavaScript hoặc CSS.
- **Sanitization:** chỉ khi có yêu cầu cho phép một tập HTML do người dùng cung cấp.

Không nên encode dữ liệu quá sớm rồi lưu dạng đã escape vào database. Dữ liệu lưu trữ nên giữ ý nghĩa gốc theo hợp đồng nghiệp vụ; mã hóa được thực hiện khi render theo ngữ cảnh. Encode sớm có thể gây double encoding và khiến cùng dữ liệu khó dùng ở những ngữ cảnh khác.

## 11. Content Security Policy và các lớp phòng vệ bổ sung

**Content Security Policy (CSP)** là một lớp phòng vệ bổ sung do trình duyệt thực thi. CSP quy định nguồn script, style, ảnh và các tài nguyên khác được phép tải. Một chính sách chặt có thể giảm khả năng khai thác XSS nếu một lỗi mã hóa đầu ra vẫn còn.

Ví dụ chính sách minh họa:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-{random-per-response}'; object-src 'none'; base-uri 'self'; frame-ancestors 'self'
~~~

Giá trị nonce phải được tạo ngẫu nhiên cho từng response và gắn đúng vào các script được phép. Đây là ví dụ định hướng, không nên sao chép nguyên xi mà không kiểm kê tài nguyên của ứng dụng. Hãy bắt đầu bằng chế độ Content-Security-Policy-Report-Only để quan sát vi phạm, sau đó xây dựng và thực thi chính sách phù hợp. Tránh phụ thuộc vào unsafe-inline hoặc unsafe-eval nếu có thể.

CSP không thay thế output encoding hoặc sanitizer. Nó là lớp phòng vệ bổ sung; cấu hình sai có thể làm trang ngừng hoạt động, còn một số loại XSS vẫn có thể xảy ra trong phạm vi nguồn được cho phép.

Các biện pháp bổ sung khác:

- Cookie phiên nên có HttpOnly để JavaScript không đọc trực tiếp cookie, Secure để chỉ gửi qua HTTPS và SameSite phù hợp với luồng xác thực.
- Dùng HTTPS để bảo vệ dữ liệu khi truyền.
- Đặt X-Content-Type-Options: nosniff để giảm nguy cơ trình duyệt tự suy đoán kiểu nội dung.
- Trả đúng Content-Type, ví dụ application/json cho JSON và text/html cho HTML.
- Hạn chế quyền và thời hạn của phiên; có cơ chế thu hồi khi đăng xuất.

HttpOnly có thể hạn chế việc đánh cắp cookie qua JavaScript nhưng không ngăn script XSS thực hiện hành động trong trang dưới phiên người dùng đang mở. SameSite chủ yếu hỗ trợ giảm rủi ro CSRF; nó không phải biện pháp sửa XSS.

## 12. Xử lý dữ liệu rich text an toàn

Một số ứng dụng cần cho phép người dùng viết nội dung có định dạng như tiêu đề, liên kết, danh sách hoặc chữ đậm. Trong trường hợp này, chỉ escape toàn bộ nội dung sẽ làm mất định dạng; render HTML thô lại tạo rủi ro.

Một quy trình an toàn thường gồm:

1. Xác định rõ các thẻ được phép, chẳng hạn p, strong, em, ul, ol, li và a.
2. Chỉ cho phép thuộc tính cần thiết, chẳng hạn href trên liên kết.
3. Kiểm tra URL trong thuộc tính theo allowlist scheme; loại bỏ javascript: và giao thức không được phép.
4. Dùng thư viện sanitizer HTML chuyên dụng, được cập nhật và cấu hình allowlist.
5. Lưu hoặc sử dụng kết quả đã sanitize theo một quy trình rõ ràng; khi chính sách sanitizer thay đổi, cân nhắc xử lý lại nội dung cũ.
6. Render kết quả qua một điểm được kiểm soát, không cho phép mọi template gọi HTML thô tùy ý.

Sanitizer cần xử lý cấu trúc HTML theo parser, không phải tìm kiếm chuỗi đơn giản. Kiểm thử cả các trường hợp thuộc tính sự kiện, URL, SVG/MathML và cấu trúc lồng nhau nếu thư viện hoặc chính sách cho phép những loại nội dung đó.

## 13. Kiểm thử phòng chống XSS trong View

Kiểm thử nên xác nhận dữ liệu không tin cậy được hiển thị như dữ liệu và không trở thành phần tử hoặc mã thực thi.

Một số payload thử nghiệm vô hại:

~~~text
<script>alert(1)</script>
<img src=x onerror=alert(1)>
"'><svg onload=alert(1)>
javascript:alert(1)
~~~

Đưa các chuỗi này vào những nguồn dữ liệu khác nhau như tên, bình luận, từ khóa tìm kiếm, thông báo lỗi và nội dung rich text. Kiểm tra kết quả ở đúng ngữ cảnh:

- Văn bản xuất hiện như chuỗi đã escape, không tạo node HTML ngoài ý muốn.
- Giá trị thuộc tính không thể thoát khỏi dấu nháy để tạo thuộc tính mới.
- URL bị từ chối nếu scheme hoặc host không được phép.
- Dữ liệu không được thực thi khi đưa vào JavaScript hoặc DOM.
- HTML rich text chỉ chứa thẻ và thuộc tính nằm trong allowlist.
- CSP được gửi đúng và không có nguồn script ngoài dự kiến.

Ví dụ kiểm thử render template:

~~~java
@WebMvcTest(CommentController.class)
class CommentControllerTest {
    @Autowired
    MockMvc mvc;

    @MockBean
    CommentQuery commentQuery;

    @Test
    void commentIsRenderedAsText() throws Exception {
        given(commentQuery.getComment(1L))
                .willReturn(new CommentViewModel("<img src=x onerror=alert(1)>"));

        mvc.perform(get("/comments/1"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        org.hamcrest.Matchers.containsString(
                                "&lt;img src=x onerror=alert(1)&gt;"
                        )
                ));
    }
}
~~~

Ví dụ minh họa cho template HTML có escape nội dung. Chi tiết chuỗi output có thể khác theo template engine và cấu hình; kiểm thử cần khớp với cách render thực tế. Ngoài kiểm tra chuỗi HTML, kiểm thử trình duyệt hoặc DOM có thể xác nhận payload không tạo phần tử ảnh hay event handler.

## 14. Những lỗi triển khai thường gặp

| Lỗi | Vì sao nguy hiểm | Cách xử lý |
| --- | --- | --- |
| Dùng th:utext với nội dung người dùng | Chèn HTML thô vào trang | Dùng th:text, hoặc sanitizer trước khi render rich text |
| Nối chuỗi để tạo HTML | Không kiểm soát được ngữ cảnh và dấu nháy | Dùng template engine và binding có escape |
| Dùng một hàm escape cho mọi vị trí | Encoding không phù hợp với context | Chọn encoder cho HTML, attribute, URL, JS hoặc CSS |
| Đưa query parameter vào innerHTML | Trình duyệt phân tích dữ liệu thành HTML | Dùng textContent hoặc DOM API an toàn |
| Đưa dữ liệu vào inline script | Có thể phá cấu trúc JavaScript | Tránh nội suy; dùng JSON serialization hoặc DOM data |
| Chỉ validation đầu vào | Dữ liệu hợp lệ vẫn có thể nguy hiểm trong HTML | Encode tại điểm render |
| Chỉ dựa vào CSP | Chính sách có thể chưa bao phủ mọi đường khai thác | Kết hợp encoding, sanitizer và CSP |
| Encode trước khi lưu database | Dễ double encoding và phụ thuộc ngữ cảnh | Lưu dữ liệu gốc, encode khi xuất |

## 15. Quy trình xây dựng View an toàn

Khi tạo hoặc sửa một màn hình MVC, hãy đi theo trình tự:

1. Liệt kê các nguồn dữ liệu được đưa vào View: form, database, query parameter, dịch vụ ngoài và dữ liệu do client gửi.
2. Xác định chính xác vị trí sử dụng của từng giá trị: text node, attribute, URL, JavaScript, CSS hay HTML rich text.
3. Ưu tiên binding và template engine có auto-escaping; xác minh chế độ và cú pháp đang dùng.
4. Tránh HTML thô, inline script và DOM sink có khả năng diễn giải chuỗi không tin cậy.
5. Nếu cần rich text, dùng sanitizer theo allowlist và kiểm soát điểm render.
6. Kiểm tra URL, scheme và đích đến khi dữ liệu được dùng làm liên kết hoặc tài nguyên.
7. Bổ sung CSP và các header/cookie bảo mật như lớp phòng vệ bổ sung.
8. Kiểm thử payload ở từng context và kiểm tra cả response HTML lẫn DOM sau khi render.
9. Rà soát template mới khi thêm trường hoặc thay đổi cách hiển thị dữ liệu.

Trong MVC, Controller nên cung cấp dữ liệu qua view model; View dùng binding an toàn để trình bày. Model không cần lưu dữ liệu đã HTML-encode, vì cùng một giá trị có thể được sử dụng trong HTML, JSON hoặc một ngữ cảnh khác với quy tắc mã hóa riêng.

## Kết luận

XSS xuất hiện khi dữ liệu không đáng tin cậy bị trình duyệt diễn giải thành mã. View cần mã hóa đầu ra theo đúng ngữ cảnh, ưu tiên cơ chế auto-escaping của template engine, tránh chèn HTML/JavaScript thô và chỉ cho phép rich text sau khi sanitizer xử lý theo allowlist. Validation, authorization, CSP, cookie an toàn và kiểm thử payload bổ sung cho nhau. Khi dữ liệu được xử lý đúng tại điểm render, ứng dụng MVC giảm nguy cơ script ngoài ý muốn chạy trong trình duyệt người dùng.
