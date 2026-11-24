# XSS test: kiểm thử Cross-Site Scripting trong ứng dụng web

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt reflected XSS, stored XSS và DOM-based XSS.
2. Xác định nguồn dữ liệu (source), bước xử lý và điểm đưa dữ liệu vào trang (sink).
3. Thiết kế ca kiểm thử theo ngữ cảnh HTML, attribute, URL, JavaScript, CSS và DOM.
4. Dùng payload kiểm thử vô hại để xác nhận HTML injection và JavaScript execution.
5. Kiểm tra XSS trong form, URL, kết quả tìm kiếm, nội dung lưu trữ, iframe và message.
6. Sử dụng DevTools để theo dõi request, DOM mutation, call stack và lỗi CSP.
7. Phân biệt output encoding, sanitization, CSP và Trusted Types.
8. Đánh giá tác động của XSS tới cookie, Web Storage, session và hành động của người dùng.
9. Xây dựng regression test và báo cáo phát hiện có thể tái hiện.
10. Xác minh bản sửa bằng cách kiểm thử cả payload tấn công lẫn dữ liệu hợp lệ.

> **Bối cảnh:** Module Browser Security phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; đồng thời thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types và security headers. XSS xảy ra khi dữ liệu không tin cậy được đưa vào ngữ cảnh thực thi hoặc markup mà không được xử lý phù hợp. Kiểm thử cần theo dấu dữ liệu từ nguồn tới sink, xác nhận khả năng thực thi và đánh giá ranh giới origin/session.

## 1. XSS test là gì?

Cross-Site Scripting (XSS) là nhóm lỗi cho phép dữ liệu do attacker kiểm soát trở thành markup hoặc script được browser xử lý trong trang của ứng dụng. Khi XSS chạy trong origin của ứng dụng, mã có thể tương tác với DOM, đọc dữ liệu mà JavaScript được phép đọc và gửi request theo quyền hiện tại của browser.

XSS test là quá trình kiểm tra có kiểm soát để xác định:

- Dữ liệu không tin cậy có đi vào trang hay không.
- Ứng dụng có encode hoặc sanitize đúng ngữ cảnh không.
- Browser có tạo markup ngoài ý muốn không.
- Event handler hoặc JavaScript có thực thi không.
- CSP hoặc Trusted Types có phát hiện/chặn sink không an toàn không.
- Lỗi có thể tái hiện qua reload, tài khoản khác, tab khác hoặc luồng nghiệp vụ nào.

Không kết luận có XSS chỉ vì chuỗi script tag xuất hiện trong trang. Cần xác định browser đã parse nó thành markup, có thể thực thi script hoặc event handler hay chỉ hiển thị chuỗi như văn bản.

### HTML injection khác JavaScript execution

Nếu payload tạo được một phần tử HTML nhưng không chạy JavaScript, đó có thể là HTML injection. Đây vẫn là vấn đề cần đánh giá, nhưng mức độ và tác động khác với XSS có thực thi script.

Ngược lại, payload script tag có thể không chạy trong một số sink như innerHTML, trong khi event handler hoặc URL nguy hiểm lại có thể chạy. Vì vậy, test phải phù hợp với sink và execution context.

## 2. Phân loại XSS

### Reflected XSS

Dữ liệu từ request được phản chiếu vào response hiện tại mà không được encode đúng ngữ cảnh.

Ví dụ luồng:

    Browser request:
      GET /search?q=TEST_MARKER

    Server response:
      <p>Kết quả cho: TEST_MARKER</p>

Nếu ứng dụng đưa query vào HTML không an toàn, payload có thể được browser parse và thực thi khi nạn nhân mở URL.

Nguồn thường gặp:

- Query parameter.
- Path parameter.
- Form field.
- Header được ứng dụng phản chiếu.
- Error message hoặc trang debug.

### Stored XSS

Dữ liệu độc hại được lưu ở database, CMS, comment, profile, ticket hoặc hệ thống khác rồi hiển thị cho người dùng ở một request sau.

Ví dụ:

1. User A lưu nội dung trong comment.
2. Server lưu comment.
3. User B mở trang danh sách comment.
4. Nội dung được render không an toàn và có thể thực thi trong browser của User B.

Stored XSS có thể ảnh hưởng nhiều người dùng hoặc nhóm có quyền cao hơn người nhập dữ liệu.

### DOM-based XSS

DOM-based XSS xảy ra khi JavaScript phía client đọc dữ liệu không tin cậy rồi đưa vào sink nguy hiểm.

Source thường gặp:

- location.search, location.hash và location.href.
- document.referrer.
- window.name.
- postMessage event.data.
- localStorage, sessionStorage và IndexedDB.
- Dữ liệu từ API hoặc DOM do người dùng kiểm soát.

Sink thường gặp:

- innerHTML, outerHTML và insertAdjacentHTML.
- document.write().
- eval() hoặc new Function().
- setTimeout()/setInterval() với chuỗi mã.
- Thuộc tính event handler hoặc URL nguy hiểm.

DOM XSS có thể không cần server phản chiếu payload vào HTML. Kiểm tra response HTML đơn thuần có thể bỏ sót lỗi này.

### XSS phía server và phía client có thể cùng tồn tại

Một giá trị có thể được lưu ở server, trả về qua JSON rồi được frontend chèn vào DOM không an toàn. Khi phân loại phát hiện, ghi rõ cả nguồn dữ liệu và sink cuối cùng; không chỉ dựa vào nơi payload được nhập.

## 3. Source → transform → sink

Mô hình thực hành hữu ích:

    Untrusted source
          |
          v
      Transform
   (validate/encode/
    sanitize/parse)
          |
          v
       DOM sink
          |
          v
   Browser parsing
          |
          v
   Markup or script

### Source

Source là dữ liệu có thể chịu ảnh hưởng của người dùng, website bên ngoài hoặc hệ thống khác:

- Search term.
- Comment/profile/message.
- Query hoặc fragment trong URL.
- API response.
- Nội dung từ CMS.
- postMessage từ iframe.
- Dữ liệu lưu trong browser storage.

### Transform

Transform là bước xử lý trước khi dữ liệu đi vào sink:

- Validate theo schema và giới hạn độ dài.
- Encode theo ngữ cảnh đầu ra.
- Sanitize HTML bằng thư viện phù hợp nếu sản phẩm cho phép rich text.
- Parse URL và allowlist scheme/host.
- Loại bỏ field hoặc cấu trúc không được phép.

Validate dữ liệu không thay thế output encoding. Một chuỗi hợp lệ về schema vẫn có thể chứa ký tự đặc biệt khi đưa vào HTML.

### Sink

Sink là API hoặc vị trí browser diễn giải dữ liệu thành markup, script, URL hoặc style. Một giá trị an toàn trong text node có thể không an toàn khi đặt trong attribute hoặc JavaScript string.

Khi audit code, tìm sink trước, sau đó truy ngược dữ liệu về source và xác định transform đã áp dụng.

## 4. Chuẩn bị môi trường kiểm thử an toàn

Chỉ kiểm thử ứng dụng, tài khoản, tenant và hệ thống mà bạn được phép đánh giá. Ưu tiên local hoặc staging với dữ liệu giả.

### Chuẩn bị

1. Chọn một ứng dụng test có thể tái tạo lỗi.
2. Tạo tài khoản kiểm thử với quyền thấp và tài khoản xem nội dung.
3. Dùng dữ liệu giả, không dùng cookie, token hoặc PII production.
4. Ghi lại browser/version, URL, build và thời điểm kiểm thử.
5. Mở DevTools trước khi thực hiện thao tác.
6. Xác định cách xóa dữ liệu test sau khi hoàn thành.

### Phạm vi cần thống nhất

- Endpoint và route được phép kiểm thử.
- Form hoặc trường dữ liệu được phép nhập payload.
- Có được tạo stored content hay không.
- Có được kiểm tra bằng tài khoản thứ hai hay không.
- Có giới hạn request rate hay không.
- Cách báo cáo ngay nếu phát hiện ảnh hưởng tới người dùng thật.

Không thử payload lấy cookie, token, chụp màn hình hoặc gửi dữ liệu ra domain ngoài. Bài lab chỉ cần marker cục bộ để xác nhận browser có thực thi code.

## 5. Payload vô hại để xác nhận kết quả

Payload phải được chọn theo context. Bắt đầu bằng marker văn bản, sau đó kiểm tra markup và cuối cùng mới xác nhận thực thi bằng một hành động cục bộ, không phá hoại.

### Marker văn bản

    XSS_TEST_2026_01

Marker giúp tìm dữ liệu trong response, DOM, Network và storage. Nó không tự chứng minh có XSS.

### Kiểm tra HTML injection

Trong staging:

    <b data-xss-test="1">XSS_MARKER</b>

Nếu trang hiển thị chữ đậm và Elements cho thấy một phần tử b được tạo, dữ liệu đã được parse thành HTML. Đây là bằng chứng HTML injection; cần kiểm tra thêm khả năng thực thi script để phân loại XSS.

### Kiểm tra event handler bằng marker cục bộ

Trong một trang lab do bạn kiểm soát, có thể dùng payload sau để thay đổi một thuộc tính DOM vô hại:

    <img src="/__xss_test_missing_image__"
         onerror="document.documentElement.dataset.xssTest='executed'">

Sau khi browser xử lý event, kiểm tra trong Console:

    document.documentElement.dataset.xssTest

Giá trị executed cho thấy handler đã chạy. Request ảnh thất bại chỉ nhằm kích hoạt error event trong môi trường lab; không dùng URL ảnh trỏ tới máy chủ bên ngoài.

Payload có thể bị CSP chặn do inline event handler. Khi đó, cần kiểm tra Console và CSP report để biết code bị chặn hay không được parse vào DOM. Không tắt CSP trên production để ép payload chạy.

### Vì sao không chỉ dùng script tag?

Ví dụ:

    <script>document.documentElement.dataset.xssTest='executed'</script>

Script được tạo qua innerHTML thường không thực thi theo cách nhiều người kỳ vọng. Nếu test chỉ dùng script tag và không thấy marker, chưa đủ kết luận sink an toàn. Chọn payload theo loại sink và hành vi parser.

### Kiểm tra attribute context

Nếu dữ liệu được chèn vào một attribute HTML, kiểm tra xem dấu nháy có thoát khỏi attribute hay không. Dùng marker vô hại và quan sát cấu trúc Elements; chỉ thực hiện event handler test trong trang lab được kiểm soát.

Không sao chép payload từ một context sang context khác mà không điều chỉnh. Payload phù hợp HTML text không nhất thiết phù hợp quoted attribute, URL hoặc JavaScript string.

## 6. Kiểm thử reflected XSS

### Bước 1 — Tìm điểm nhập dữ liệu

Kiểm tra:

- Search box.
- Filter và sort parameter.
- Error message.
- URL path/query.
- Form validation message.
- Trang hiển thị tên file hoặc tên người dùng.

Nhập marker văn bản và xác định giá trị xuất hiện ở đâu.

### Bước 2 — Theo dõi request

1. Mở DevTools → Network.
2. Bật Preserve log nếu request điều hướng trang.
3. Thực hiện submit hoặc mở URL test.
4. Chọn request liên quan.
5. Kiểm tra Query String Parameters, Form Data hoặc Request Payload.
6. Kiểm tra response có phản chiếu marker không.

Không export HAR chứa cookie hoặc Authorization header nếu chưa redaction.

### Bước 3 — Kiểm tra response và DOM

So sánh:

- Response body trong Network.
- DOM sau khi JavaScript chạy trong Elements.
- Giá trị hiển thị trên giao diện.

Nếu response đã encode nhưng DOM sau đó tạo markup, có thể có một sink DOM-based ở bước client render.

### Bước 4 — Kiểm tra context

Xác định marker được đặt trong:

- HTML text node.
- Attribute có dấu nháy.
- Attribute URL.
- Inline script.
- CSS.
- Template hoặc JSON nhúng trong HTML.

Dùng payload tương ứng để kiểm tra parser boundary. Không chỉ nhìn chuỗi có xuất hiện hay không.

### Bước 5 — Xác nhận và ghi nhận

Ghi lại:

- URL/parameter đã kiểm thử, đã loại bỏ dữ liệu nhạy cảm.
- Request và response liên quan.
- DOM node hoặc sink.
- Có HTML injection không.
- Có JavaScript execution không.
- CSP có chặn không.
- Tài khoản và vai trò bị ảnh hưởng.

## 7. Kiểm thử stored XSS

Stored XSS cần kiểm tra cả nơi nhập, nơi lưu và mọi nơi hiển thị lại.

### Bước 1 — Chọn trường có lưu dữ liệu

Ví dụ:

- Comment.
- Profile display name.
- Ticket description.
- Product review.
- Nội dung CMS.
- Tên file hoặc metadata do người dùng đặt.

Chỉ dùng chức năng test đã được cho phép và nội dung marker vô hại.

### Bước 2 — Lưu marker

1. Đăng nhập bằng user test A.
2. Nhập marker văn bản hoặc HTML marker vào trường test.
3. Lưu nội dung.
4. Ghi nhận ID bản ghi và thời điểm.
5. Không dùng payload có khả năng gửi dữ liệu ra ngoài.

### Bước 3 — Mở lại bằng context khác

1. Mở trang danh sách bằng user test B nếu được phép.
2. Mở trang chi tiết, trang quản trị hoặc preview có hiển thị cùng dữ liệu.
3. Quan sát Elements và Console.
4. Xác định mỗi view có xử lý dữ liệu giống nhau hay không.

Một trường được encode ở trang chi tiết nhưng không encode ở trang quản trị vẫn có thể tạo stored XSS ở một context khác.

### Bước 4 — Kiểm tra vòng đời dữ liệu

- Reload trang.
- Mở tab mới.
- Đăng xuất rồi đăng nhập lại.
- Mở trang tìm kiếm hoặc danh sách có cùng record.
- Kiểm tra email notification hoặc export chỉ khi nằm trong phạm vi cho phép.

Không để payload test tồn tại lâu hơn cần thiết. Xóa record sau khi lưu bằng quy trình được phê duyệt và xác minh bản sao đã được cleanup.

### Đánh giá tác động

Stored XSS có thể ảnh hưởng người xem khác. Ghi rõ ai có thể xem record, vai trò nào bị ảnh hưởng và payload được render ở những route nào.

## 8. Kiểm thử DOM-based XSS

DOM XSS thường cần theo dõi JavaScript runtime thay vì chỉ xem HTML response.

### Bước 1 — Xác định source

Kiểm tra code và runtime với:

    location.search
    location.hash
    location.href
    document.referrer
    window.name
    event.data
    localStorage
    sessionStorage

Đây là các ví dụ source có thể không tin cậy. Việc đọc một source không tự tạo XSS; cần có đường dữ liệu tới sink nguy hiểm.

### Bước 2 — Tìm sink

Tìm trong source code:

    innerHTML
    outerHTML
    insertAdjacentHTML
    document.write
    eval
    new Function
    setTimeout(string)
    setInterval(string)

Đồng thời kiểm tra:

- setAttribute với tên attribute do dữ liệu điều khiển.
- href/src/action/formAction và URL scheme.
- Template engine hoặc framework escape mode.
- API tạo script/style/link element.

### Bước 3 — Theo dõi call stack

1. Mở Sources.
2. Dùng global search để tìm sink nghi vấn.
3. Đặt breakpoint trước sink hoặc DOM mutation breakpoint trên node liên quan.
4. Tái hiện thao tác nhập marker.
5. Quan sát call stack và giá trị trước khi ghi vào DOM.
6. Xác định transform có thực sự encode/sanitize đúng context không.

Không gửi toàn bộ object chứa token vào Console. Chỉ xem biến hoặc thuộc tính cần thiết.

### Bước 4 — Kiểm tra URL source

Thử marker trong query hoặc fragment của trang lab. Query được gửi tới server trong request; fragment thường không được gửi trong HTTP request thông thường nhưng JavaScript có thể đọc location.hash.

Nếu marker từ fragment đi tới innerHTML và tạo markup, đây là đường DOM injection cần đánh giá.

### Bước 5 — Kiểm tra postMessage

Nếu ứng dụng nhận message từ iframe hoặc cửa sổ khác:

- Kiểm tra event.origin.
- Kiểm tra event.source khi cần.
- Validate schema và kiểu dữ liệu.
- Không đưa event.data thẳng vào innerHTML.
- Chỉ chấp nhận message type được allowlist.

Ví dụ xử lý text an toàn:

    window.addEventListener("message", (event) => {
      if (event.origin !== "https://widget.example.test") {
        return;
      }

      if (
        !event.data ||
        event.data.type !== "STATUS_TEXT" ||
        typeof event.data.text !== "string"
      ) {
        return;
      }

      statusElement.textContent = event.data.text;
    });

Allowlist origin phải khớp chính xác origin được tin cậy; không dùng kiểm tra chuỗi con như includes("example.test").

## 9. Kiểm thử theo output context

Encoding phải phù hợp vị trí dữ liệu được chèn. Không có một hàm escape duy nhất an toàn cho mọi context.

| Context | Cách xử lý ưu tiên | Điều cần kiểm tra |
| --- | --- | --- |
| HTML text | HTML entity encoding hoặc textContent | Ký tự markup hiển thị như text |
| Quoted HTML attribute | Attribute encoding và quote cố định | Dữ liệu không thoát khỏi attribute |
| URL attribute | Parse URL, allowlist scheme/host, encode component | Không chấp nhận javascript: hoặc scheme ngoài policy |
| JavaScript string | Tránh inline JS; nếu buộc phải dùng, dùng serializer/encoder đúng context | Dữ liệu không thoát khỏi string hoặc tạo statement |
| CSS value | Tránh đưa input vào CSS; dùng property và value allowlist | Không tạo rule hoặc URL ngoài ý muốn |
| Rich HTML | Sanitizer allowlist đã được kiểm thử | Loại script, event handler và cấu trúc không được phép |
| DOM node | textContent/createElement | Không parse input thành HTML |
| JSON response | JSON serializer và Content-Type phù hợp | Không nối JSON thủ công vào script HTML |

### HTML text

Không an toàn:

    output.innerHTML = userInput;

An toàn khi chỉ cần văn bản:

    output.textContent = userInput;

### Attribute

Ưu tiên tạo element và gán attribute cố định:

    const image = document.createElement("img");
    image.alt = userProvidedAlt;
    image.src = validatedImageUrl;

Không dùng dữ liệu người dùng để quyết định tên attribute, đặc biệt các attribute bắt đầu bằng on.

### URL

Parse và allowlist:

    function safeLink(value) {
      const url = new URL(value, location.origin);
      const allowedOrigins = new Set([
        location.origin,
        "https://docs.example.test"
      ]);

      if (!allowedOrigins.has(url.origin)) {
        throw new Error("URL scheme is not allowed");
      }

      return url.href;
    }

Ví dụ trên minh họa việc giới hạn scheme theo origin; ứng dụng thực tế nên định nghĩa allowlist scheme và host rõ ràng, không cho URL tùy ý điều hướng tới nơi không tin cậy.

### JavaScript context

Không nối dữ liệu người dùng vào inline script:

    const script = "const name = '" + userInput + "';";

Ưu tiên truyền dữ liệu bằng JSON response, data attribute đã được encode đúng cách hoặc property của object; tránh tạo source code từ chuỗi.

### CSS context

Không nối dữ liệu người dùng vào style text hoặc CSS rule. Dùng class allowlist hoặc gán property đã validate:

    element.style.color = allowedColors.has(color)
      ? color
      : "inherit";

## 10. Output encoding và sanitization

### Output encoding

Encoding chuyển ký tự đặc biệt thành dạng không được parser hiểu như cú pháp trong context mục tiêu.

Ví dụ HTML text:

    < becomes &lt;
    > becomes &gt;
    & becomes &amp;
    " becomes &quot;
    ' becomes &#x27;

Đây là ví dụ cho HTML context. Không dùng cùng encoder cho JavaScript, CSS hoặc URL context.

### Encode tại output

Dữ liệu nên được encode khi render vào context đích, thay vì encode một lần lúc nhập rồi tái sử dụng ở nhiều context khác nhau. Cùng một giá trị có thể được hiển thị trong text, attribute hoặc URL; mỗi nơi có quy tắc riêng.

### Sanitization cho rich text

Nếu sản phẩm cần cho phép HTML như bold, link hoặc list, dùng sanitizer được duy trì và cấu hình allowlist rõ:

- Element được phép.
- Attribute được phép.
- URL scheme được phép.
- Không cho event handler.
- Không cho script, object, embed hoặc cấu trúc không cần thiết.
- Kiểm tra SVG/MathML nếu sản phẩm không cần.

Sanitizer phải được cập nhật và cấu hình phù hợp. Không tự viết regex để xóa script tag rồi coi HTML đã sạch.

### Không sanitize hai lần tùy tiện

Sanitize/encode lặp lại có thể làm hỏng nội dung hoặc tạo hiểu lầm rằng dữ liệu đã an toàn trong mọi context. Lưu dữ liệu theo dạng phù hợp nghiệp vụ và xử lý tại output theo context.

## 11. Kiểm tra CSP trong XSS test

Content Security Policy là lớp phòng thủ bổ sung giúp hạn chế nguồn script và một số hành vi thực thi. CSP không thay output encoding hoặc sanitization.

### Kiểm tra response header

Trong Network, chọn document response và xem:

    Content-Security-Policy

Ví dụ policy có nonce:

    Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-RANDOM_PER_RESPONSE'; object-src 'none'; base-uri 'self'

Nonce phải được sinh ngẫu nhiên cho từng response và gắn nhất quán với script hợp lệ. Không tái sử dụng một nonce cố định.

### Report-Only

Trong giai đoạn quan sát:

    Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; object-src 'none'

Report-Only ghi nhận vi phạm theo cấu hình báo cáo mà không chặn nội dung. Dùng để phát hiện dependency trước khi enforce; không coi Report-Only là biện pháp ngăn XSS.

### Kiểm tra Console

1. Mở Console.
2. Tái hiện test case.
3. Tìm thông báo CSP violation.
4. Xác định directive bị vi phạm.
5. Phân biệt code bị CSP chặn với code không được browser parse.

Không thêm unsafe-inline hoặc unsafe-eval vào policy production chỉ để làm test payload chạy.

### CSP không sửa sink

Nếu dữ liệu đi vào innerHTML, ứng dụng vẫn có sink nguy hiểm ngay cả khi CSP hiện tại chặn một payload cụ thể. Một thay đổi policy hoặc browser context khác có thể làm hành vi khác đi. Sửa nguyên nhân ở source-to-sink path.

## 12. Trusted Types trong XSS test

Trusted Types giúp kiểm soát việc gán dữ liệu vào một số DOM injection sink. Browser có thể yêu cầu giá trị TrustedHTML, TrustedScript hoặc TrustedScriptURL thay cho string thông thường.

Header minh họa:

    Content-Security-Policy: require-trusted-types-for 'script'; trusted-types app-html

Khi enforcement được hỗ trợ và bật, gán string trực tiếp vào sink được bảo vệ có thể phát sinh TypeError nếu không có policy phù hợp.

### Kiểm tra enforcement

1. Xác nhận response có directive require-trusted-types-for 'script'.
2. Trong staging, chạy code test gán string vào sink được bảo vệ.
3. Quan sát Console và exception.
4. Xác nhận ứng dụng không còn phụ thuộc vào sink nhận string tùy ý.
5. Kiểm tra policy được tạo chỉ cho mục đích cụ thể.

### Trusted Types không tự sanitize

Policy có thể tạo TrustedHTML từ chuỗi không an toàn nếu code policy làm sai:

    const policy = trustedTypes.createPolicy("app-html", {
      createHTML(input) {
        return input;
      }
    });

Ví dụ này không an toàn vì chỉ đóng dấu trusted mà không làm sạch. Trong ứng dụng thực, policy phải gọi sanitizer đã được cấu hình và kiểm thử.

### Kiểm thử policy

- Policy có allowlist element/attribute không?
- URL scheme có được kiểm tra không?
- Có policy default quá rộng không?
- Có tạo TrustedScript/TrustedScriptURL không cần thiết không?
- Có chỗ bypass hoặc return input nguyên trạng không?
- Việc cập nhật sanitizer có regression test không?

## 13. Cookie, storage và tác động của XSS

XSS chạy trong origin có thể gây hậu quả khác nhau tùy dữ liệu được lưu và quyền browser.

### Cookie

- JavaScript không đọc được cookie HttpOnly qua document.cookie.
- Cookie không có HttpOnly có thể bị đọc bởi script cùng origin nếu scope phù hợp.
- HttpOnly không ngăn script thực hiện request same-origin với cookie tự động đính kèm.
- Secure bảo vệ việc gửi cookie qua kết nối không an toàn theo quy tắc cookie, không ngăn XSS.

### Web Storage và IndexedDB

Script cùng origin có thể đọc localStorage, sessionStorage và IndexedDB mà ứng dụng cho phép. Token hoặc PII lưu tại đây có thể bị lộ khi có XSS.

### Session và hành động thay người dùng

Ngay cả khi không lấy được session cookie, script XSS vẫn có thể:

- Đọc nội dung trang và dữ liệu API hiển thị.
- Gửi request cùng origin theo quyền session hiện tại.
- Thay đổi thông tin mà người dùng có quyền thay đổi.
- Hiển thị form giả hoặc thay đổi nội dung giao diện.
- Gửi dữ liệu mà script đọc được tới endpoint ngoài nếu CSP/network policy cho phép.

Vì vậy, đánh giá tác động không chỉ hỏi “có lấy được cookie không?”. Hãy kiểm tra dữ liệu và hành động mà script có thể truy cập trong phiên.

### Phân biệt XSS với CSRF

CSRF khiến browser gửi request không mong muốn bằng credential tự động gửi. XSS chạy script trong origin mục tiêu và thường có khả năng thực hiện hành động trực tiếp trong context đó. CSRF token không phải biện pháp sửa XSS; CSP/encoding cũng không thay thế CSRF defense.

## 14. Kiểm thử các bề mặt thường bị bỏ sót

Không chỉ test ô tìm kiếm. Hãy lập inventory các điểm nhận và hiển thị dữ liệu.

| Bề mặt | Source thường gặp | Nơi cần kiểm tra |
| --- | --- | --- |
| Search/filter | Query, form field | Kết quả, breadcrumb, title |
| Comment/review | Nội dung người dùng | List, detail, admin preview |
| Profile | Tên, bio, avatar URL | Header, tooltip, menu |
| File upload | Filename, metadata | File list, preview, error message |
| Import/export | CSV, JSON, document metadata | Preview, report, download page |
| Error page | Path, exception, parameter | Error message và stack trace |
| Markdown/rich text | Nội dung markup | Renderer, email preview, notification |
| postMessage | event.data | Message handler và DOM sink |
| Browser storage | localStorage/IndexedDB | Hydration và client-side rendering |
| API response | JSON từ backend/third-party | Template và DOM update |
| URL redirect | next/returnUrl | Link, location.assign và navigation |
| SVG/HTML preview | File không tin cậy | img, object, iframe, top-level navigation |

### Kiểm tra email và notification

Nếu ứng dụng render dữ liệu người dùng vào email HTML hoặc notification, đó là một output context khác. Kiểm thử cần xác định renderer và nơi nội dung được mở. Không giả định encode trong trang web tự động bảo vệ email template.

### Kiểm tra admin view

Admin panel thường xem dữ liệu do nhiều người dùng nhập. Stored XSS trong admin view có thể có tác động lớn. Đảm bảo cùng một dữ liệu được xử lý an toàn ở giao diện người dùng, dashboard, moderation queue và export preview.

## 15. Kiểm tra bằng Chrome DevTools

### Elements

- Tìm marker trong DOM.
- Kiểm tra node được tạo là text node hay element.
- Xem attribute thực tế sau browser parsing.
- Xác định dữ liệu có thoát khỏi attribute hoặc tạo node ngoài dự kiến không.

Elements hiển thị DOM sau khi parser và JavaScript xử lý; nó có thể khác response HTML ban đầu.

### Network

- Kiểm tra request chứa payload.
- Kiểm tra response có phản chiếu marker không.
- Xem redirect chain.
- Xem Content-Type và CSP header.
- Kiểm tra API response chứa dữ liệu sau đó được frontend render.

### Sources

- Global search các sink như innerHTML, document.write và eval.
- Đặt breakpoint tại vị trí gán DOM.
- Theo dõi call stack từ event handler tới sink.
- Kiểm tra source và transform.

### Console

- Xem exception và CSP violation.
- Kiểm tra marker cục bộ sau payload test.
- Không log token, cookie hoặc toàn bộ object session.
- Xóa snippet và dữ liệu test sau khi hoàn tất.

### Application

- Kiểm tra marker có bị lưu trong localStorage, sessionStorage hoặc IndexedDB không.
- Xóa record test sau khi kiểm tra stored XSS.
- Không dump dữ liệu production.

### Security panel và response headers

Đối chiếu CSP, HTTPS và các security header liên quan. Header hiện diện không tự chứng minh ứng dụng không có XSS; phải kiểm tra đường dữ liệu thực tế.

## 16. Kiểm thử tự động và regression test

Automated test hữu ích để đảm bảo dữ liệu không tin cậy luôn được render như text hoặc đi qua sanitizer đã xác định.

### Test HTML text rendering

Ví dụ pseudo-test:

    const input = "<b>XSS_TEST</b>";
    renderComment(input);

    expect(
      screen.getByText("<b>XSS_TEST</b>")
    ).toBeVisible();

    expect(
      container.querySelector("b")
    ).toBeNull();

Mục tiêu là xác nhận markup được hiển thị như text, không tạo element b.

### Test rich text sanitizer

Nếu sản phẩm cho phép rich text, test cả:

- Element hợp lệ được giữ.
- Element không cho phép bị loại.
- Event handler bị loại.
- URL scheme nguy hiểm bị loại.
- Attribute không được allowlist bị loại.
- Unicode và encoding edge cases được xử lý đúng.

### Browser integration test

Trong browser automation, có thể theo dõi marker cục bộ:

    await page.goto(testUrl);
    await page.locator("#search").fill(testMarker);
    await page.locator("#submit").click();

    const marker = await page.locator("html")
      .getAttribute("data-xss-test");

    expect(marker).toBeNull();

Đây là ví dụ khung kiểm tra. Test execution payload nên chạy trong origin lab riêng và xác nhận marker chỉ thay đổi trong trang test; không dùng payload exfiltration.

### Regression theo từng context

Một test cho HTML text không đủ bao phủ attribute, URL, JavaScript, CSS, SVG hoặc rich HTML. Mỗi context cần fixture và expected behavior riêng.

### Không chỉ dựa vào scanner

DAST scanner có thể bỏ sót DOM XSS cần tương tác phức tạp, authentication hoặc state đặc biệt. Scanner cũng có thể báo false positive khi chỉ phát hiện reflection mà không xác nhận execution. Kết hợp source review, manual browser test và automated regression.

## 17. False positive và false negative

### False positive thường gặp

- Payload xuất hiện trong response nhưng được encode thành text.
- Script tag nằm trong innerHTML nhưng browser không thực thi.
- CSP chặn event handler và scanner không phân biệt policy behavior.
- Payload chỉ tạo HTML injection nhưng báo cáo ghi là script execution.
- DOM hiển thị marker do framework render text node.

### False negative thường gặp

- Chỉ kiểm tra response HTML, bỏ qua DOM mutation.
- Chỉ thử script tag, bỏ qua event handler hoặc URL sink.
- Không đăng nhập nên không thấy stored content hoặc admin view.
- Không mở trang thứ hai để kích hoạt stored XSS.
- Chỉ test một browser hoặc một route.
- Payload bị encode ở một view nhưng một view khác không encode.
- CSP chặn payload hiện tại nhưng sink vẫn tồn tại và có thể bị khai thác qua context khác.

### Cách xác nhận

1. Tái hiện bằng marker duy nhất.
2. Xác định node/attribute được tạo.
3. Chứng minh execution bằng marker cục bộ khi phù hợp.
4. Ghi lại CSP hoặc browser policy ảnh hưởng.
5. Lặp lại trên build sạch.
6. Xác định vai trò và điều kiện cần.

## 18. Cách khắc phục theo nguyên nhân

| Nguyên nhân | Cách sửa ưu tiên |
| --- | --- |
| Dữ liệu đưa vào HTML text bằng innerHTML | Dùng textContent hoặc HTML encoding đúng context |
| Rich HTML không được kiểm soát | Sanitizer allowlist được duy trì |
| Dữ liệu thoát khỏi attribute | Quote cố định và attribute encoding |
| URL scheme không được kiểm tra | Parse URL và allowlist scheme/host |
| Nối dữ liệu vào inline JavaScript | Bỏ inline JS; truyền dữ liệu qua JSON/property |
| DOM sink nhận string tùy ý | Dùng safe DOM API và Trusted Types enforcement |
| Script inline không kiểm soát | CSP nonce/hash, giảm unsafe-inline |
| Third-party script không cần thiết | Loại bỏ hoặc giới hạn dependency và quyền |
| Stored content render khác nhau giữa views | Dùng renderer chung và regression test mọi view |
| postMessage không validate | Kiểm tra origin, source, schema và command allowlist |

### Sửa tại sink và kiến trúc

Ưu tiên API tạo DOM an toàn. Nếu cần HTML, sanitize trước khi đưa vào sink. Không dựa vào blacklist vài chuỗi như script tag hoặc onerror; parser có nhiều cách biểu diễn markup và context khác nhau.

### CSP là defense in depth

Triển khai CSP phù hợp, ưu tiên nonce/hash và hạn chế nguồn script. Không coi CSP là lý do để giữ sink nguy hiểm.

### Trusted Types

Bật Trusted Types cho các sink được hỗ trợ và tạo policy nhỏ, có kiểm thử. Policy phải sanitize thật; không return input nguyên trạng.

## 19. Mẫu báo cáo XSS

Một báo cáo hữu ích cần đủ thông tin để developer tái hiện và sửa.

**Tiêu đề:** Stored XSS trong phần mô tả ticket

**Môi trường:** Staging, browser/version, build ID.

**Điều kiện:** User A có thể tạo ticket; User B có quyền xem ticket.

**Bước tái hiện:**

1. Đăng nhập User A.
2. Mở trang tạo ticket.
3. Nhập marker test đã thống nhất vào trường mô tả.
4. Lưu ticket.
5. Đăng nhập User B và mở ticket.
6. Quan sát DOM và marker execution trong trang lab.

**Kết quả thực tế:** Ghi rõ dữ liệu trở thành text, HTML injection hay JavaScript execution.

**Kết quả mong đợi:** Nội dung không tin cậy được hiển thị dưới dạng text hoặc đi qua sanitizer allowlist.

**Bằng chứng:**

- Request/response đã redaction.
- DOM node hoặc call stack liên quan.
- CSP violation nếu có.
- Ảnh chụp đã che PII và credential.

**Tác động:** Ghi nhóm người dùng, route và quyền có thể bị ảnh hưởng. Không phóng đại thành đánh cắp session nếu chưa chứng minh.

**Khuyến nghị:** Nêu sink và cách sửa cụ thể.

**Cleanup:** Xóa record/payload test và xác minh không còn trên các view liên quan.

## 20. Ma trận kiểm thử tổng hợp

| Nhóm | Ca kiểm thử | Kết quả mong đợi |
| --- | --- | --- |
| Reflected | Query marker hiển thị trong kết quả | Render text; không tạo markup ngoài ý muốn |
| Reflected | Payload trong error message | Không parse thành HTML/script |
| Stored | Comment hiển thị ở trang chi tiết | Encode/sanitize đúng context |
| Stored | Cùng comment hiển thị trong admin | Không có execution ở admin view |
| Stored | Reload và tab khác | Kết quả vẫn an toàn sau render lại |
| DOM | location.hash tới sink | Marker không tạo markup/script |
| DOM | postMessage từ origin không tin cậy | Message bị từ chối |
| DOM | localStorage tới innerHTML | Không có đường dữ liệu không an toàn |
| HTML text | Chuỗi có dấu ngoặc nhọn | Hiển thị như text |
| Attribute | Chuỗi chứa dấu nháy | Không thoát khỏi attribute |
| URL | javascript: hoặc scheme ngoài allowlist | Bị từ chối/loại bỏ |
| JavaScript | Input chứa quote và dấu phân cách | Không tạo source code mới |
| CSS | Input thành style value | Chỉ nhận value allowlist |
| Rich text | Element/attribute không cho phép | Sanitizer loại bỏ |
| CSP | Inline handler trong lab | Bị chặn khi policy không cho phép |
| CSP | Report-Only | Ghi nhận vi phạm nhưng không enforce |
| Trusted Types | String gán vào protected sink | Bị từ chối khi enforcement bật |
| Trusted Types | Policy sanitizer | Chỉ tạo TrustedHTML sau sanitization |
| Cookie | Session cookie HttpOnly | JS không đọc value; XSS vẫn có thể request trong phiên |
| Storage | Token trong localStorage | Được xem là có thể đọc nếu XSS chạy cùng origin |
| Regression | Dữ liệu hợp lệ và Unicode | Không hỏng chức năng và không tạo execution |
| Cleanup | Stored payload test | Được xóa khỏi record và view liên quan |

## 21. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ tìm chuỗi script tag | Bỏ sót event handler và DOM XSS | Test theo source, sink và context |
| Thấy marker trong response là kết luận XSS | False positive | Kiểm tra DOM parsing và execution |
| Script tag không chạy nên kết luận an toàn | Bỏ sót sink khác | Dùng payload phù hợp sink |
| Chỉ test một trang | Bỏ sót stored XSS ở admin/preview | Kiểm tra mọi view render dữ liệu |
| Dùng một encoder cho mọi context | Encode sai context | Contextual output encoding |
| Dùng regex xóa script | Bypass parser và cấu trúc khác | Sanitizer allowlist |
| Nghĩ CSP sửa được innerHTML | Sink nguy hiểm vẫn tồn tại | Sửa source-to-sink và dùng CSP bổ sung |
| Nghĩ Trusted Types tự sanitize | Policy có thể trả input nguyên trạng | Review policy và sanitizer |
| Nghĩ HttpOnly ngăn mọi tác động XSS | Script vẫn có thể gửi request trong phiên | Phòng XSS và giảm quyền/dữ liệu |
| Nghĩ CSRF token sửa XSS | Script trong origin có thể đọc/điều khiển luồng | Xử lý XSS riêng |
| Dump cookie/token để chứng minh tác động | Tạo thêm rò rỉ credential | Dùng marker và metadata đã redaction |
| Không xóa stored payload | Ảnh hưởng người dùng sau test | Cleanup và xác minh |
| Chỉ dựa vào DAST scanner | Bỏ sót state/DOM flow hoặc false positive | Kết hợp manual, code review và regression |
| Test trên production không kiểm soát | Ảnh hưởng dữ liệu/người dùng thật | Local/staging và phạm vi được phép |

## 22. Câu hỏi củng cố

**Câu 1.** Reflected XSS khác stored XSS thế nào?

**Giải đáp:** Reflected XSS phản chiếu dữ liệu từ request vào response hiện tại; stored XSS lưu dữ liệu rồi render lại trong một request hoặc view sau.

**Câu 2.** DOM-based XSS cần những thành phần nào?

**Giải đáp:** Một source không tin cậy, đường xử lý và sink khiến dữ liệu được browser diễn giải thành markup hoặc code không an toàn.

**Câu 3.** HTML injection có luôn là JavaScript execution không?

**Giải đáp:** Không. Markup có thể được tạo mà không thực thi script. Cần xác nhận hành vi browser và context.

**Câu 4.** Vì sao không chỉ test bằng script tag?

**Giải đáp:** Một số sink không thực thi script tag được tạo động, trong khi event handler hoặc URL sink có thể vẫn nguy hiểm.

**Câu 5.** Khi nào dùng textContent?

**Giải đáp:** Khi dữ liệu chỉ cần hiển thị như văn bản. textContent tránh parse chuỗi thành HTML.

**Câu 6.** Sanitization khác output encoding thế nào?

**Giải đáp:** Encoding biến ký tự thành dạng an toàn cho một output context; sanitization lọc markup theo allowlist khi ứng dụng cần cho phép một tập HTML.

**Câu 7.** CSP có thay output encoding không?

**Giải đáp:** Không. CSP là defense in depth, không sửa source-to-sink hoặc làm dữ liệu trở nên an toàn.

**Câu 8.** Trusted Types có tự làm sạch chuỗi không?

**Giải đáp:** Không. Policy phải gọi sanitizer hoặc kiểm tra phù hợp; policy trả input nguyên trạng vẫn không an toàn.

**Câu 9.** HttpOnly có ngăn XSS thực hiện request thay người dùng không?

**Giải đáp:** Không. HttpOnly ngăn JavaScript đọc cookie value, nhưng browser vẫn có thể tự gửi cookie trong request cùng phiên.

**Câu 10.** Bằng chứng tối thiểu để báo cáo XSS là gì?

**Giải đáp:** Có thể tái hiện, xác định source/sink/context, chứng minh HTML hoặc script behavior, ghi điều kiện và cung cấp bằng chứng đã redaction.

## 23. Tổng kết

XSS test cần theo dõi dữ liệu từ source qua transform tới sink và đánh giá cách browser parse dữ liệu trong context thực tế. Phân biệt reflected, stored và DOM-based XSS giúp chọn đúng luồng kiểm thử. Marker xuất hiện trong response chưa đủ chứng minh XSS; cần xác định markup được tạo và JavaScript có thực thi hay không.

Thực hiện kiểm thử trên hệ thống được phép, ưu tiên staging và payload vô hại chỉ thay đổi marker cục bộ. Dùng DevTools Network, Elements, Sources, Console và Application để xác định request, DOM mutation, call stack và dữ liệu lưu. Kiểm tra nhiều view, vai trò người dùng, reload và luồng lưu trữ để không bỏ sót stored XSS.

Biện pháp khắc phục phải phù hợp context: textContent hoặc output encoding cho text, attribute/URL validation cho attribute và URL, sanitizer allowlist cho rich HTML, cùng CSP và Trusted Types làm lớp phòng thủ bổ sung. HttpOnly giảm khả năng đọc cookie nhưng không ngăn script XSS thực hiện request trong phiên. Mỗi phát hiện cần có bước tái hiện, tác động chính xác, bằng chứng đã redaction, khuyến nghị sửa và cleanup payload test.

## Tài liệu tham khảo

1. [OWASP — Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html): output encoding, sanitization và phòng XSS theo context.
2. [OWASP — DOM based XSS Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/DOM_based_XSS_Prevention_Cheat_Sheet.html): source, sink và DOM XSS.
3. [OWASP — Web Security Testing Guide: Testing for Reflected XSS](https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/11-Client-side_Testing/01-Testing_for_Reflected_Cross_Site_Scripting): quy trình kiểm thử reflected XSS.
4. [OWASP — Web Security Testing Guide: Testing for Stored XSS](https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/11-Client-side_Testing/02-Testing_for_Stored_Cross_Site_Scripting): quy trình kiểm thử stored XSS.
5. [OWASP — Web Security Testing Guide: Testing for DOM-based XSS](https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/11-Client-side_Testing/03-Testing_for_DOM-based_Cross_Site_Scripting): kiểm tra source và sink phía client.
6. [MDN — Cross-site scripting (XSS)](https://developer.mozilla.org/en-US/docs/Web/Security/Attacks/XSS): tổng quan XSS và cách phòng vệ.
7. [W3C — Content Security Policy Level 3](https://www.w3.org/TR/CSP3/): CSP directives, nonce, hash và enforcement.
8. [W3C — Trusted Types](https://www.w3.org/TR/trusted-types/): kiểm soát DOM injection sinks.
9. [Chrome Developers — Trusted Types](https://developer.chrome.com/docs/lighthouse/best-practices/trusted-types): triển khai và kiểm tra Trusted Types.
