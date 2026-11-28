# Contextual encoding — Mã hóa đầu ra theo đúng ngữ cảnh

## 1. Một giá trị không có một bản “an toàn cho mọi nơi”

Giả sử người dùng có tên hiển thị:

~~~text
Lan & Minh <Ops>
~~~

Đây có thể là dữ liệu hoàn toàn hợp lệ. Khi ứng dụng đưa tên vào nội dung HTML, ký tự `<` không được làm trình duyệt hiểu phần tiếp theo là một thẻ. Khi đưa tên vào một thuộc tính có dấu nháy, dấu nháy trong dữ liệu không được kết thúc thuộc tính. Nếu dùng tên làm giá trị tham số URL, dấu `&` không được tách thành tham số mới.

**Contextual encoding** là chọn cách biểu diễn dữ liệu phù hợp với **ngữ cảnh cú pháp thực sự nhận nó**, để dữ liệu tiếp tục được hiểu là giá trị thay vì thay đổi cấu trúc của tài liệu hoặc mã.

Cùng một tên hiển thị có thể đi tới nhiều nơi:

| Nơi sử dụng | Dữ liệu cần giữ vai trò gì? |
| --- | --- |
| Nội dung một `span` trong HTML | Text |
| Thuộc tính `title` của phần tử | Giá trị thuộc tính thông thường |
| Tham số `q` của liên kết tìm kiếm | Một giá trị tham số URL |
| Response JSON | Một JSON string |
| DOM được cập nhật sau khi tải trang | Text hoặc giá trị property |
| String trong mã JavaScript được nhúng vào HTML | Dữ liệu trong một string và trong tài liệu HTML bao ngoài |

Không nên tạo một biến `safeName` rồi dùng nó cho tất cả những nơi này. Tính phù hợp phụ thuộc nơi sử dụng, không chỉ phụ thuộc nguồn dữ liệu.

Trong thiết kế yêu cầu bảo mật, câu “encode toàn bộ output” cần được cụ thể hóa thành danh mục điểm xuất, ngữ cảnh, cơ chế thực thi và tiêu chí nghiệm thu. OWASP khuyến nghị chọn bảo vệ theo nơi dữ liệu được dùng: API xử lý text, output encoding đúng ngữ cảnh hoặc sanitization nếu sản phẩm thật sự nhận HTML. [OWASP XSS Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html).

Các trang, trường dữ liệu và mã yêu cầu trong bài là ví dụ thiết kế, không phải cấu hình bắt buộc của mọi framework.

## 2. Xác định ngữ cảnh từ điểm xuất, không từ tên trường

Muốn chọn encoder, trước hết cần biết thành phần nào sẽ diễn giải giá trị. Một trường tên là `description` vẫn có thể được đưa vào text HTML, một thuộc tính hoặc một đoạn mã JavaScript.

Có thể mô tả một điểm xuất bằng bốn thông tin:

~~~text
Nguồn giá trị:
    displayName từ hồ sơ người dùng.

Vị trí chèn:
    Nội dung của span có tên và cấu trúc cố định.

Thành phần diễn giải:
    HTML parser.

Cơ chế:
    Autoescape cho HTML text hoặc HTML-content encoder.
~~~

Đổi vị trí chèn sang `title="..."` làm hợp đồng thay đổi. Đổi sang `onclick="..."` lại đưa thêm ngữ cảnh mã JavaScript. Một encoder dành cho thuộc tính text thông thường không vì thế trở thành giải pháp cho event handler.

Bảng phân loại thực hành:

| Ngữ cảnh | Cách tiếp cận phù hợp | Điều không được suy ra |
| --- | --- | --- |
| Text giữa các thẻ HTML thông thường | Autoescape hoặc HTML text encoding | Không tự áp dụng cho script, style hoặc raw markup |
| Giá trị thuộc tính text có quote, tên cố định | Attribute encoding khi tạo HTML source | Không xác nhận URL hay an toàn của event handler |
| Một thành phần URL | URL builder hoặc component encoding | Không xác nhận toàn URL được phép truy cập |
| URL nằm trong HTML attribute | Xây URL đúng hợp đồng, rồi bảo vệ attribute bao ngoài | Không dùng một bước để thay cả hai ngữ cảnh |
| Dữ liệu trong JavaScript source | Tránh nhúng nếu có thể; nếu cần dùng cơ chế chuyên biệt đúng vị trí | Không chấp nhận mã, tên biến hoặc biểu thức tùy ý |
| Style động | Giá trị có kiểu/allowlist, tên property cố định | Không coi encoder là bộ kiểm tra toàn CSS |
| DOM text runtime | API tạo text/value phù hợp | Không cần pre-encode thành HTML entity |
| Nội dung HTML do người dùng soạn | Sanitizer theo chính sách và sink chuyên biệt | Không coi mọi string là HTML đáng tin |

Bảng này là bản đồ lựa chọn, không phải một hàm `encode(value, contextName)` mà caller được tự gán context tùy ý. Nhóm cần kiểm soát vị trí sử dụng và cách truyền dữ liệu trong thiết kế.

## 3. Tách dữ liệu nghiệp vụ khỏi biểu diễn đầu ra

Một cách tổ chức rõ ràng là:

~~~mermaid
flowchart LR
    A[Dữ liệu nghiệp vụ đã kiểm tra] --> B[HTML renderer]
    A --> C[JSON serializer]
    A --> D[URL builder]
    B --> E[HTML text hoặc attribute đúng ngữ cảnh]
    C --> F[Response JSON]
    D --> G[URL theo hợp đồng]
    F --> H[Client nhận giá trị]
    H --> I[DOM text hoặc property phù hợp]
~~~

Dữ liệu nghiệp vụ không nên được lưu mặc định dưới dạng đã HTML-encode chỉ vì hôm nay nó được hiển thị trên web. Ngày mai cùng dữ liệu có thể được dùng trong JSON, email văn bản hoặc một ứng dụng khác.

Với tên `Lan & Minh <Ops>`, lưu ngay `Lan &amp; Minh &lt;Ops&gt;` làm các consumer không biết đó là tên nguyên bản hay một biểu diễn dành cho HTML. Consumer tiếp theo có thể encode lần nữa hoặc decode ngoài ý định.

Đặc tả nên phân biệt:

- Dữ liệu văn bản theo hợp đồng đầu vào.
- HTML source đã được tạo cho một vị trí xác định.
- URL hoặc thành phần URL.
- JSON document.
- HTML fragment đã được sanitizer xử lý theo chính sách riêng.

Không đặt nhãn “trusted” chỉ vì string đã đi qua một encoder. Ví dụ, một string phù hợp làm HTML text vẫn không được đưa vào `innerHTML` như một cách cấp quyền tạo markup tùy ý.

Charset cũng là một quyết định khác. UTF-8 quy định cách biểu diễn ký tự thành byte; HTML output encoding quy định cách các ký tự tham gia cú pháp HTML. Dùng UTF-8 không tự ngăn ký tự `<` trở thành phần mở đầu của markup.

Base64 hay URL encoding cũng không tạo ra một trạng thái “an toàn vĩnh viễn”. Sau khi decode, giá trị vẫn cần được dùng đúng ngữ cảnh ở điểm xuất cuối.

## 4. HTML text: giữ văn bản là văn bản

Giả sử trang hồ sơ chỉ muốn hiển thị tên trong một phần tử cố định:

~~~html
<p class="display-name">VỊ_TRÍ_DỮ_LIỆU</p>
~~~

Với dữ liệu `Lan & Minh <Ops>`, HTML source có thể có dạng:

~~~html
<p class="display-name">Lan &amp; Minh &lt;Ops&gt;</p>
~~~

Trình duyệt hiển thị tên với dấu `&` và dấu ngoặc góc như văn bản. Không có phần tử `Ops` được tạo từ tên.

Điểm cần nghiệm thu là **ngữ nghĩa sau parse**: text đúng và cấu trúc DOM không bị dữ liệu thay đổi. Không nhất thiết bắt buộc mọi encoder dùng cùng một cách viết entity nếu các cách đó tương đương trong ngữ cảnh đã chọn.

Trong Java, OWASP Java Encoder cung cấp các API theo ngữ cảnh như `Encode.forHtmlContent` cho text HTML và `Encode.forHtmlAttribute` cho thuộc tính text có quote. Thư viện không thay thế việc xác định đúng ngữ cảnh hoặc chính sách dữ liệu. [OWASP Java Encoder](https://owasp.org/projects/java-encoder).

Nếu template engine đã autoescape đúng cho vị trí này, truyền dữ liệu nguyên bản cho nó. Không HTML-encode trước ở service rồi tiếp tục để template engine encode lần nữa.

Yêu cầu minh họa:

> Tên hiển thị phải được render như text trong phần tử cố định. Các ký tự có ý nghĩa cú pháp HTML không được tạo phần tử hoặc thuộc tính mới. Trình bày phải bảo toàn nội dung hợp lệ mà không encode hai lần.

Không dùng một danh sách từ khóa “đáng ngờ” để thay cơ chế này. Tên có dấu nháy, dấu `&` hoặc một đoạn văn bản giống thẻ vẫn có thể là dữ liệu hợp lệ.

## 5. Thuộc tính HTML: quote và loại thuộc tính đều quan trọng

Đối với thuộc tính thông thường:

~~~html
<input type="text" value="VỊ_TRÍ_DỮ_LIỆU">
~~~

Tên phần tử và tên thuộc tính do ứng dụng quyết định. Dữ liệu chỉ được đi vào giá trị đã được bao bởi dấu nháy và xử lý theo hợp đồng attribute.

Một đầu vào có dấu `"` không được kết thúc `value` và mở một thuộc tính khác. Việc bảo vệ cần áp dụng trước khi tạo HTML source, không đợi trình duyệt sửa tài liệu hỏng.

HTML có quy tắc cú pháp khác nhau cho giá trị thuộc tính được quote và không được quote. Do đó, thiết kế nên yêu cầu giá trị động luôn có quote thay vì dựa vào tập ký tự tình cờ của input. [WHATWG HTML — Attributes](https://html.spec.whatwg.org/multipage/syntax.html#attributes-2).

Tuy nhiên, không phải mọi attribute đều là text vô hại:

| Thuộc tính | Ngữ cảnh hoặc yêu cầu bổ sung |
| --- | --- |
| `title` | Text thông thường |
| `value` trên input text | Giá trị điều khiển theo hợp đồng của input |
| `href` | URL cần có chính sách scheme/destination thích hợp |
| `style` | Nội dung CSS, không chỉ một string HTML |
| `onclick` và các event handler | Mã JavaScript |
| `srcdoc` | Một tài liệu HTML khác |
| Tên thuộc tính do client chọn | Có thể thay đổi ý nghĩa của toàn phần tử |

Không nhận tên thuộc tính tùy ý từ request rồi cho rằng attribute encoder đã bảo vệ mọi hành vi. Một API như `setAttribute` với tên `title` cố định khác hẳn việc cho dữ liệu quyết định tên thuộc tính.

Ở phía client, gán giá trị runtime cho thuộc tính text thông thường không phải là tạo lại HTML source. Ví dụ:

~~~javascript
const input = document.querySelector("#display-name");
input.value = profile.displayName;
input.setAttribute("title", profile.displayName);
~~~

Với các phần tử đúng theo hợp đồng trang, API nhận giá trị trực tiếp. Không pre-encode `profile.displayName` thành entity HTML trước khi gán; làm như vậy có thể khiến người dùng nhìn thấy chính text `&amp;`.

## 6. URL: bảo vệ thành phần và kiểm tra ý nghĩa

Giả sử trang hồ sơ có liên kết tìm kiếm theo tên:

~~~text
/search?q=<giá trị tên>&page=1
~~~

Nếu nối trực tiếp tên `A&B` vào URL, dấu `&` có thể bị hiểu là ranh giới tham số thay vì một phần của `q`.

Quy trình cần tách rõ:

1. Đưa dữ liệu nguyên bản vào đúng thành phần URL.
2. Dùng builder hoặc encoder phù hợp cho thành phần đó.
3. Bảo đảm URL tổng thể tuân chính sách ứng dụng.
4. Nếu đưa URL vào HTML source, bảo vệ tiếp ngữ cảnh attribute bao ngoài.

Với một path tìm kiếm cố định của cùng ứng dụng, Java có thể xây giá trị query bằng `Encode.forUriComponent`. Không đưa toàn bộ URL vào component encoder vì như vậy các dấu phân cách có cấu trúc cũng bị coi là dữ liệu.

Khi client cung cấp **toàn URL**, cần kiểm tra scheme, destination và những thành phần ứng dụng quan tâm. HTML attribute encoding không biến một scheme bị cấm thành được phép. Parse thành công cũng chưa phải quyết định cho phép điều hướng.

Không đánh đồng `java.net.URLEncoder` với một encoder cho mọi vị trí URL. API này thực hiện `application/x-www-form-urlencoded` và biểu diễn dấu cách bằng `+`; phải dùng nó theo hợp đồng form/query tương ứng, không mặc định cho path hoặc toàn URL. [Java SE 21 — URLEncoder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLEncoder.html).

Ở phía trình duyệt, có thể dùng URL API với origin và path do ứng dụng quyết định:

~~~javascript
const link = document.querySelector("#search-name");
const url = new URL("/search", window.location.origin);
url.searchParams.set("q", profile.displayName);
url.searchParams.set("page", "1");

link.href = url.toString();
~~~

`searchParams.set` nhận giá trị tham số, không cần caller gọi `encodeURIComponent` trước. URLSearchParams có hợp đồng parse/serialize riêng trong URL Standard. [WHATWG URL — URLSearchParams](https://url.spec.whatwg.org/#interface-urlsearchparams).

Đoạn code trên gán URL qua DOM property, không chèn URL vào HTML source. Vì vậy, không thêm một bước HTML entity encoding trước `link.href`.

Yêu cầu URL của ví dụ chỉ cho liên kết tới đường tìm kiếm cố định. Nó không phải một validator tái sử dụng cho mọi redirect, tải file hoặc URL mà máy chủ sẽ truy cập.

## 7. Minh họa Java cho hai ngữ cảnh HTML và một URL lồng nhau

Đoạn code dưới đây minh họa renderer tạo HTML source trực tiếp. Template chứa tên thẻ, thuộc tính, path và các dấu phân cách cố định; dữ liệu chỉ đi vào những vị trí đã xác định.

~~~java
import java.util.Objects;

import org.owasp.encoder.Encode;

public final class ProfileHtmlRenderer {
    public static String render(String displayName) {
        Objects.requireNonNull(displayName, "displayName");

        String searchUrl =
                "/search?q="
                + Encode.forUriComponent(displayName)
                + "&page=1";

        return "<p class=\"display-name\">"
                + Encode.forHtmlContent(displayName)
                + "</p>"
                + "<input type=\"text\" value=\""
                + Encode.forHtmlAttribute(displayName)
                + "\">"
                + "<a href=\""
                + Encode.forHtmlAttribute(searchUrl)
                + "\">Tìm theo tên</a>";
    }
}
~~~

Ở đây có ba mục tiêu khác nhau:

- `displayName` trong `p` là HTML text.
- `displayName` trong `value` là giá trị attribute có quote.
- `displayName` trong `q` là URL component; URL đã ghép được xử lý tiếp cho HTML attribute.

Hướng dẫn sử dụng chính thức của Java Encoder có các API String/Writer và ví dụ xây URL component rồi bảo vệ attribute bên ngoài. Nó cũng lưu ý tránh double escaping khi framework đã thực hiện bước HTML tương ứng. [OWASP Java Encoder — Usage](https://github.com/OWASP/owasp-java-encoder/blob/main/docs/usage.md).

Renderer này trả một biểu diễn HTML cho vị trí đã chốt, không trả dữ liệu nghiệp vụ để đưa tiếp vào một template autoescape khác. Nếu kiến trúc dùng template engine, lựa chọn thông thường là để engine thực hiện HTML encoding ở điểm render, còn dữ liệu đầu vào vẫn có kiểu và nguồn rõ ràng.

Không lấy toàn bộ kết quả renderer rồi dùng nó để làm JavaScript string, CSS source hoặc một thuộc tính khác. Chuyển sang điểm xuất mới sẽ tạo một hợp đồng mới.

Đoạn code chỉ minh họa encoding. Việc kiểm tra quyền xem hồ sơ, giới hạn độ dài tên, HTTP headers và cách dữ liệu được lấy từ service thuộc các yêu cầu riêng.

## 8. JavaScript và JSON: đừng bỏ quên HTML bao ngoài

Một string được đưa vào mã JavaScript có những ký tự có ý nghĩa riêng như dấu quote và backslash. Nếu mã JavaScript ấy lại nằm trong `script` của tài liệu HTML, còn có HTML parser ở lớp ngoài.

Ví dụ cấu trúc:

~~~html
<script>
  const displayName = "VỊ_TRÍ_DỮ_LIỆU";
</script>
~~~

Một serializer hoặc encoder chỉ phù hợp với JavaScript resource độc lập chưa chắc bảo vệ đúng khi kết quả được nhúng vào HTML. Chuỗi đóng `script` là một ví dụ cần xét tại lớp HTML, dù trông như dữ liệu string đối với ngôn ngữ bên trong.

HTML Standard mô tả riêng các hạn chế của nội dung `script` và các chuỗi đặc biệt mà HTML parser xử lý. Do đó, không suy ra rằng bảo vệ quote JavaScript là đã bảo vệ toàn bộ cấu trúc tài liệu. [WHATWG HTML — Restrictions for contents of script elements](https://html.spec.whatwg.org/multipage/scripting.html#restrictions-for-contents-of-script-elements).

Một thiết kế dễ giữ ranh giới hơn là:

~~~text
HTML chứa cấu trúc trang và JavaScript cố định.
    → JavaScript lấy dữ liệu từ endpoint JSON.
    → JSON parser tạo các giá trị.
    → Giá trị được gán vào text/property phù hợp.
~~~

Ví dụ:

~~~javascript
async function loadProfile() {
    const response = await fetch("/api/profile", {
        headers: { Accept: "application/json" }
    });
    if (!response.ok) {
        throw new Error("PROFILE_UNAVAILABLE");
    }

    const profile = await response.json();
    if (typeof profile.displayName !== "string") {
        throw new Error("INVALID_PROFILE_RESPONSE");
    }

    document.querySelector("#profile-name").textContent =
            profile.displayName;
}
~~~

Endpoint phải serialize một JSON document theo hợp đồng và trả media type phù hợp. Không HTML-encode mọi string trong JSON chỉ vì client sau đó hiển thị nó trên web. Client vẫn phải chọn sink đúng khi sử dụng giá trị đã parse.

Nếu kiến trúc bắt buộc nhúng string vào inline script, dùng cơ chế được thư viện hoặc framework công bố cho **vị trí đó**, giữ code và dấu quote cố định. Không cho dữ liệu làm tên biến, biểu thức, một đoạn mã hoặc event handler.

Tương tự, một JSON document hợp lệ được đặt trong `script type="application/json"` vẫn chịu cách HTML parser xác định biên phần tử. Cần serializer hỗ trợ an toàn khi nhúng HTML hoặc một phương án truyền dữ liệu khác; `type="application/json"` không loại bỏ lớp HTML.

Tài liệu Java Encoder phân biệt JavaScript trong script block, event attribute, resource độc lập và JSON string, đồng thời nêu rõ giới hạn của mỗi hợp đồng. Không thay thế chúng bằng một hàm encode “JavaScript chung” do dự án tự đoán. [OWASP Java Encoder — Output contexts and boundaries](https://github.com/OWASP/owasp-java-encoder/blob/main/docs/contexts.md).

## 9. DOM runtime: tạo text khác với tạo HTML source

Khi JavaScript đã có một string runtime, có thể tránh HTML parser bằng cách gán vào text của phần tử thông thường:

~~~javascript
const label = document.querySelector("#profile-name");
label.textContent = profile.displayName;
~~~

DOM Standard quy định thao tác đặt text content cho Element theo việc tạo text node và thay nội dung con, không phải parse string như HTML source. [WHATWG DOM — textContent](https://dom.spec.whatwg.org/#dom-node-textcontent).

Điều này khác:

~~~javascript
label.innerHTML = profile.displayName;
~~~

Lệnh thứ hai yêu cầu trình duyệt diễn giải giá trị như HTML. Nếu mục tiêu chỉ là hiển thị tên, nó mở một ngữ cảnh không cần thiết.

Không gọi `textContent` là “HTML encoder”. API này đặt text trực tiếp; pre-encode rồi gán sẽ làm dữ liệu bị hiển thị khác ý định.

Phạm vi của khẳng định cũng quan trọng. `textContent` của một `span` chứa tên hiển thị khác với đặt text vào một phần tử `script` hoặc `style` có ý nghĩa thực thi riêng. Thiết kế cần cố định loại phần tử và mục đích sử dụng, không chỉ kiểm tra tên API.

Một giá trị đọc từ `textContent` rồi đưa sang `innerHTML` lại gặp một điểm xuất khác. Việc nó từng đi qua text node không cấp cho nó quyền làm HTML ở bước sau.

Yêu cầu minh họa:

> Các cập nhật hồ sơ phía client phải sử dụng text node hoặc property dữ liệu đã phê duyệt. Không dùng API parse HTML để hiển thị trường chỉ có ý nghĩa văn bản. Không decode entity rồi đưa lại vào sink HTML.

## 10. CSS, event handler và những vị trí nên tránh dữ liệu tự do

Contextual encoding không có nghĩa mọi vị trí đều nên nhận dữ liệu tùy ý nếu tìm được một encoder.

Với trạng thái hồ sơ, thay vì nhận CSS source do client gửi, có thể ánh xạ một tập trạng thái sang class cố định:

~~~javascript
const statusClasses = {
    ACTIVE: "status-active",
    PENDING: "status-pending",
    DISABLED: "status-disabled"
};

const statusClass = Object.hasOwn(statusClasses, profile.status)
        ? statusClasses[profile.status]
        : "status-unknown";

document.querySelector("#profile-status").className =
        "status " + statusClass;
~~~

Dữ liệu chọn một giá trị trong tập do ứng dụng quản lý; nó không quyết định selector, property name hoặc declaration CSS.

Nếu có giá trị style động, cần hợp đồng riêng cho từng property: ví dụ số nguyên trong một khoảng rồi ứng dụng tự thêm đơn vị đã chọn. Một encoder dành cho CSS string không phải validator cho độ rộng, toàn bộ `style` hoặc URL trong CSS.

Đối với hành vi click, giữ handler là code cố định:

~~~javascript
document.querySelector("#show-profile").addEventListener(
        "click",
        () => showProfile(profile.id)
);
~~~

Không tạo source event handler bằng cách nối dữ liệu vào `onclick`. Truyền giá trị vào một hàm đã viết sẵn giúp tách dữ liệu khỏi mã; hàm được gọi vẫn phải có hợp đồng và kiểm soát riêng.

Các vị trí khác cần hạn chế hoặc có xử lý chuyên biệt gồm tên thẻ, tên thuộc tính, comment HTML, tài liệu `srcdoc` và các đoạn code tùy ý. Không chấp nhận một yêu cầu “hỗ trợ encode mọi vị trí” mà chưa xác định parser và mục đích thực tế.

Đối với URL trong CSS, còn phải quyết định scheme và destination được phép. Đổi thành một API CSSOM không tự xác nhận URL đó phù hợp với chính sách sản phẩm.

## 11. Sanitization và encoding phục vụ hai mục tiêu khác nhau

Giả sử người dùng nhập:

~~~html
<strong>Thông báo</strong>
~~~

Nếu trường là **văn bản thuần**, encoding để hiển thị toàn bộ ký tự là phù hợp. Người xem có thể thấy chính nội dung giống một thẻ.

Nếu trường là **nội dung HTML được sản phẩm hỗ trợ**, mục tiêu có thể là cho phép chữ đậm nhưng loại bỏ cấu trúc hoặc khả năng không được chấp thuận. Khi đó cần sanitizer theo chính sách HTML, không chỉ output encoding.

Hai hợp đồng cần tách:

| Hợp đồng | Điều người dùng được cung cấp | Cách trình bày |
| --- | --- | --- |
| Plain text | String theo chính sách dữ liệu | Text, không tạo markup từ input |
| Rich text HTML | Một tập markup được sản phẩm cho phép | HTML đã qua sanitizer theo chính sách và sink chuyên biệt |

Không tắt autoescape cho một trường chỉ vì tên của nó là `descriptionHtml`. Cần có bằng chứng trường đã qua luồng xử lý phù hợp và không bị nối thêm nội dung chưa xử lý trước khi render.

Một HTML fragment đã qua sanitizer cũng không vì thế dùng được làm JavaScript string hoặc attribute tùy ý. Khi đổi ngữ cảnh, phải xét hợp đồng mới.

Đối với plain text, không dùng sanitizer để xóa dấu ngoặc góc rồi gọi đó là bảo toàn dữ liệu. Xóa markup và hiển thị markup như text là hai hành vi sản phẩm khác nhau.

Các bước kiểm tra quyền xem dữ liệu và kiểm soát nội dung nghiệp vụ vẫn độc lập. Encoding ngăn dữ liệu thay đổi cú pháp ở điểm xuất, không xác nhận người xem được phép nhận dữ liệu ấy.

## 12. Encode đúng điểm và tránh double encoding

Một giá trị thường đi qua service, mapper, cache, template và JavaScript. Nếu mỗi tầng đều “encode cho chắc”, kết quả có thể bị thay đổi nhiều lần:

~~~text
Giá trị nghiệp vụ:
    A & B

Một lần HTML encoding:
    A &amp; B

HTML encoding lần nữa:
    A &amp;amp; B
~~~

Trong ví dụ này, người dùng có thể nhìn thấy `A &amp; B` thay vì `A & B` sau khi HTML được parse.

Cũng cần phân biệt double encoding với việc bảo vệ **hai ngữ cảnh lồng nhau**:

~~~text
Sai:
    HTML encode → HTML encode lại cùng một vị trí.

Có chủ đích:
    Encode giá trị tham số URL
    → xây URL bằng dấu phân cách cố định
    → encode URL cho attribute HTML bao ngoài.
~~~

Thứ tự của trường hợp lồng nhau đi từ giá trị của ngôn ngữ bên trong tới biểu diễn của lớp bao ngoài. Không đảo thứ tự theo cảm tính.

Một global response filter thường không biết từng byte đang thuộc HTML text, JSON, URL hay JavaScript. Vì vậy, “encode toàn response tại một chỗ” có thể vừa bỏ sót context vừa phá dữ liệu.

Thiết kế nên đặt ownership rõ:

| Tầng | Trách nhiệm minh họa |
| --- | --- |
| Domain/service | Giá trị nghiệp vụ và quyền truy cập, không đánh dấu mọi string là HTML-safe |
| URL builder | Xây và kiểm tra URL theo chính sách |
| HTML template/renderer | Encoding tại các vị trí HTML được giao |
| JSON serializer | Tạo tài liệu JSON đúng hợp đồng |
| Client component | Chọn text/property/sink đúng với giá trị nhận được |
| Rich text renderer | Chỉ nhận artifact phù hợp từ sanitizer theo chính sách |

Nếu một framework cung cấp cơ chế “raw”, “safe HTML” hoặc bypass tương đương, mỗi chỗ sử dụng cần có lý do và nguồn dữ liệu rõ ràng. Không dùng chúng để sửa nhanh tình trạng double encoding mà chưa tìm được tầng đã encode sai.

## 13. Chuyển thiết kế thành yêu cầu bảo mật

Một bộ yêu cầu cho trang hồ sơ minh họa:

| ID | Yêu cầu | Rủi ro được xử lý | Bằng chứng nghiệm thu |
| --- | --- | --- | --- |
| CTX-001 | Mọi điểm xuất của trường người dùng có context được xác định | Dùng nhầm cơ chế | Mapping field → sink → parser → cơ chế |
| CTX-002 | Tên hiển thị trong HTML là text | Tạo markup từ dữ liệu | DOM text đúng, không thêm phần tử từ tên |
| CTX-003 | Attribute text có tên cố định và giá trị được quote/encode khi tạo HTML | Thoát giá trị attribute | Input có quote không tạo thuộc tính mới |
| CTX-004 | URL component được xây riêng khỏi cấu trúc URL | Tách tham số ngoài ý định | Query nhận đúng giá trị ban đầu, không thêm tham số |
| CTX-005 | URL tổng thể tuân chính sách điều hướng | Chấp nhận scheme/destination ngoài phạm vi | URL không được phép bị từ chối hoặc không render thành link |
| CTX-006 | Không nhúng text người dùng thành JavaScript code | Dữ liệu trở thành mã | Script/handler cố định, dữ liệu đi qua kênh dữ liệu |
| CTX-007 | JSON được serialize và truyền theo đúng hợp đồng | Dùng HTML encoding thay serialization | JSON parse được và bảo toàn giá trị |
| CTX-008 | Cập nhật DOM text không dùng HTML-parsing sink | DOM injection | Component dùng text/value đã phê duyệt |
| CTX-009 | CSS động theo tập giá trị hoặc kiểu cho phép | Thay đổi CSS ngoài ý định | Không nhận selector/declaration tùy ý |
| CTX-010 | Rich text có luồng sanitizer riêng | Cấp quyền HTML cho string thường | Plain text và artifact rich text không bị dùng lẫn |
| CTX-011 | Không double encode hoặc decode rồi đưa vào sink mới không bảo vệ | Sai hiển thị hoặc tái diễn giải | Ca ký tự đặc biệt bảo toàn qua các consumer |
| CTX-012 | Đổi sink hoặc template cần cập nhật hợp đồng encoding | Mất bảo vệ khi refactor | Mapping và ca hồi quy được cập nhật |

Trong mapping CTX-001, “nguồn là database” chưa đủ để đánh dấu dữ liệu an toàn. Cần xét ai có thể ghi và ngữ cảnh hiện tại sử dụng giá trị.

Không nghiệm thu chỉ bằng việc có thư viện encoder trong dependency. Cần chứng minh từng điểm xuất thật sự gọi cơ chế đúng hoặc được framework bảo vệ đúng cách.

Nếu cùng một trường xuất hiện trong trang HTML người dùng và trang quản trị, cả hai đều thuộc phạm vi. Stored content có thể gây tác động lớn hơn ở giao diện quyền cao nếu nơi đó dùng sink khác.

## 14. Tiêu chí nghiệm thu theo ngữ nghĩa sau parse

Bảng dưới đây mô tả các ca kiểm thử cần thiết cho ví dụ, không phải kết quả đã chạy:

| Ca | Dữ liệu hoặc điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| T01 | `Lan & Minh <Ops>` trong tên | Text hiển thị đúng; không tạo phần tử Ops |
| T02 | Tên có `"`, `'` và `&` | Không thoát attribute; giá trị DOM đúng |
| T03 | Chuỗi `<b id="encoding-canary">x</b>` ở trường plain text | Không tạo phần tử b từ dữ liệu |
| T04 | Input nguyên bản là text `&lt;b&gt;` | Hiển thị đúng các ký tự nguyên bản; không tự decode thành markup |
| T05 | Tên tiếng Việt và emoji hợp lệ | Không lỗi charset hoặc mất nội dung ngoài chính sách |
| T06 | Query chứa `A&B+C #x/?` | Server nhận một giá trị q đúng ý định; không thêm tham số từ dữ liệu |
| T07 | URL hoàn chỉnh có scheme ngoài chính sách | Không biến thành liên kết được cho phép chỉ vì đã encode |
| T08 | Giá trị title có quote và dấu lớn/nhỏ | Một attribute title cố định, không có attribute mới |
| T09 | Client gán tên qua textContent | Text đúng; không nhìn thấy entity do pre-encode thừa |
| T10 | JSON chứa quote, backslash và newline hợp lệ | Serializer/parser bảo toàn giá trị string |
| T11 | Dữ liệu có chuỗi giống đóng script trong kênh nhúng được hỗ trợ | Không kết thúc sai phần tử script hoặc đổi cấu trúc trang |
| T12 | Thay đổi client từ textContent sang innerHTML | Ca hồi quy phải phát hiện sai hợp đồng |
| T13 | Trạng thái style không thuộc tập cho phép | Dùng fallback đã chốt, không tạo CSS source từ input |
| T14 | Rich text hợp lệ theo chính sách | Định dạng được cho phép hiển thị đúng qua luồng sanitizer |
| T15 | Plain text đi qua service/cache/template | Không bị HTML-encode nhiều lần |
| T16 | Giá trị đã hiển thị được đọc rồi dùng ở vị trí khác | Điểm xuất mới vẫn áp dụng hợp đồng tương ứng |
| T17 | Cùng dữ liệu ở trang quản trị | Bảo vệ đúng sink của trang quản trị |
| T18 | Một cơ chế bypass autoescape xuất hiện khi refactor | Có đánh giá nguồn và bằng chứng cho mục đích sử dụng |

Các ca có markup có thể dùng phần tử canary vô hại để quan sát việc DOM bị thay đổi, không cần thực thi mã hoặc tác động lên tài khoản thật.

Với HTML text, nên kiểm tra text content và cấu trúc DOM. Với attribute, kiểm tra cả giá trị và danh sách attribute. Với URL, parse liên kết và kiểm tra tập tham số cùng giá trị sau giải mã. Những bằng chứng này mạnh hơn việc tìm một chuỗi entity trong response.

Không cố định test vào một dạng escape duy nhất nếu thư viện cho phép nhiều biểu diễn tương đương. Ngược lại, nếu sản phẩm phụ thuộc byte chính xác cho cache hoặc chữ ký, hợp đồng đó cần được quản lý riêng khi nâng thư viện.

CSP hoặc cơ chế giảm tác động khác có thể hỗ trợ phòng vệ, nhưng một ca chỉ “không thấy mã chạy vì bị policy chặn” chưa chứng minh encoding đã giữ nguyên cấu trúc. Cần quan sát ranh giới dữ liệu và parser.

## 15. Những phản mẫu làm mất ranh giới ngữ cảnh

**Một hàm escape duy nhất cho mọi đầu ra.** Tên hàm không cho biết nó bảo vệ HTML text, attribute, JavaScript hay URL.

**Encode ngay khi nhận input rồi lưu như dữ liệu chuẩn.** Các consumer mất thông tin về giá trị nguyên bản và mục đích biểu diễn.

**Cho rằng URL đã HTML-encode là URL được phép.** Cú pháp attribute và chính sách điều hướng là hai quyết định khác nhau.

**Dùng JSON serializer rồi chèn thẳng vào mọi script block.** JSON đúng không tự giải quyết lớp HTML bao ngoài.

**Pre-encode trước textContent.** API tạo text không cần dữ liệu ở dạng HTML source.

**Dùng attribute encoder cho event handler.** Giá trị có thêm ngữ cảnh JavaScript và hành vi thực thi.

**Dùng CSS string encoder cho cả declaration hoặc số đo tùy ý.** Ngữ cảnh nhỏ mà encoder hỗ trợ không đại diện toàn ngôn ngữ CSS.

**Tắt autoescape để sửa một lỗi hiển thị.** Có thể đang bỏ bảo vệ ở điểm xuất thay vì sửa tầng encode hai lần.

**Tin dữ liệu vì đã được một màn hình khác render an toàn.** Đổi vị trí sử dụng làm thay đổi hợp đồng.

**Decode ở client rồi đưa vào HTML sink.** Bước decode có thể làm dữ liệu gặp parser dưới một biểu diễn mới mà chưa được bảo vệ.

Contextual encoding bắt đầu từ câu hỏi: giá trị sắp được thành phần nào diễn giải, trong vị trí cú pháp nào? Yêu cầu bảo mật cần giữ câu trả lời đó cụ thể cho từng điểm xuất, đồng thời bảo toàn dữ liệu hợp lệ và tách encoding khỏi quyền truy cập, chính sách URL, sanitization và kiểm tra nghiệp vụ.
