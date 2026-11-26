# Mã XSS ảnh hưởng thế nào đến giả thiết của cơ chế CSRF

## Mục tiêu học tập

Sau bài học trong chương **Cơ chế CSRF**, người học có thể:

- Mô tả **giả thiết tin cậy cốt lõi của CSRF token**: kẻ tấn công đứng ngoài origin ứng dụng có thể kích hoạt một số request nhưng thường **không đọc được token** hoặc nội dung response của ứng dụng đích.
- Giải thích vì sao **Cross-Site Scripting (XSS)** có thể phá vỡ giả thiết ấy khi mã không đáng tin cậy thực thi **trong origin của ứng dụng**, từ đó đọc token hoặc gửi request có token hợp lệ.
- Phân biệt XSS phản xạ (*reflected*), XSS lưu trữ (*stored*) và XSS phía DOM (*DOM-based*), và xác định đường đưa dữ liệu không tin cậy vào **nguồn chạy JavaScript/HTML**.
- Hiểu vì sao `HttpOnly`, `SameSite`, CSRF token ngẫu nhiên, token có ký HMAC, XOR masking và CORS **không tự ngăn** một script độc hại đã chạy cùng origin thực hiện thao tác được phép trong phiên hiện tại.
- Phân tích trường hợp **subdomain khác origin nhưng cùng site**: SameSite có thể không ngăn cookie, song Same-Origin Policy vẫn tạo ranh giới với token trong ứng dụng đích nếu chưa có XSS ở origin đó.
- Áp dụng các phòng vệ **output encoding theo ngữ cảnh, DOM API an toàn, HTML sanitization, CSP, Trusted Types, phân quyền và xác nhận lại thao tác nhạy cảm**, cùng CSRF token.
- Viết ví dụ và kiểm thử **Spring Security Servlet** lẫn **Reactive/WebFlux** để bảo đảm CSRF filter vẫn hoạt động và dữ liệu người dùng không bị render thành mã thực thi.
- Chẩn đoán các kết luận sai kiểu “CSRF token vẫn đúng nên XSS không quan trọng” hoặc “chỉ cần bật CSP/HttpOnly là đủ”.

## 1. Đặt vấn đề: CSRF token dựa vào ranh giới origin nào?

Một ứng dụng web dùng cookie xác thực có thể nhận request POST được trình duyệt tự gắn credential. Khi một website ngoài làm nạn nhân gửi form tới ứng dụng, server có thể thấy phiên đăng nhập hợp lệ dù request không được khởi tạo từ giao diện đáng tin cậy.

Ví dụ request tới ứng dụng:

~~~http
POST /profile/email HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=SESSION_A
Content-Type: application/x-www-form-urlencoded

email=attacker@example.test
~~~

Nếu `/profile/email` có thể thay đổi email tài khoản, request thiếu bước kiểm chứng bổ sung có nguy cơ bị **CSRF**.

Mẫu **synchronizer token** xử lý bằng cách phát một token gắn với phiên A, rồi yêu cầu client đưa nó vào hidden form field hoặc HTTP header:

~~~http
POST /profile/email HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=SESSION_A
Content-Type: application/x-www-form-urlencoded

email=alice@example.test&_csrf=TOKEN_CUA_PHIEN_A
~~~

Server so submitted token với expected token của phiên A trước khi cho phép xử lý.

**Vì sao việc này hữu ích?** Một trang tại `https://other.test` có thể khiến browser tạo form POST đến `https://app.example.com` trong một số ngữ cảnh. Nhưng trang đó **thường không được đọc HTML, DOM, cookie riêng origin hoặc response của `app.example.com`** do Same-Origin Policy và những chính sách trình duyệt liên quan. Do đó nó không biết token ngẫu nhiên đúng để đưa vào request.

**Nhưng nếu mã do attacker điều khiển đã thực thi ngay trong origin `https://app.example.com` thì sao?** Khi ấy giả thiết “attacker đứng ngoài origin, không đọc được token” không còn đúng. Đó là điểm giao nhau giữa **XSS** và **CSRF**.

> **Kết luận trung tâm:** CSRF token là cơ chế hữu ích chống yêu cầu giả mạo do nguồn ngoài origin kích hoạt; **XSS ở origin đích có thể làm suy yếu hoặc vượt qua cơ chế này** vì script độc hại thường có quyền truy cập tương đương JavaScript hợp lệ của ứng dụng.

Bài học thuộc module **SPRING_SECURITY_HTTP_PROTECTION**, tập trung phòng vệ HTTP/trình duyệt trong Spring Security qua CSRF, CORS, security headers, CSP, HSTS, HTTP firewall và bảo vệ session cho cả **Servlet** lẫn **Reactive**. Chống XSS và chống CSRF phải được xây dựng **đồng thời**, không dùng một cơ chế để thay thế cơ chế kia.

## 2. Giả thiết bảo mật của CSRF token

### 2.1. Mô hình attacker thông thường của CSRF

Trong một kịch bản CSRF cổ điển:

1. Người dùng đã đăng nhập `app.example.com` bằng cookie session hoặc một credential mà browser có thể tự đính kèm.
2. Attacker kiểm soát một trang ở origin khác, ví dụ `evil.other.test`.
3. Attacker có thể làm browser tạo một số request đến ứng dụng đích thông qua link, form, tài nguyên nhúng hoặc các cơ chế điều hướng được phép.
4. Attacker **không có khả năng đọc token CSRF** do ứng dụng đích phát hành qua HTML, DOM hay API được Same-Origin Policy bảo vệ.
5. Server chỉ chấp nhận request thay đổi trạng thái khi token được client chủ động gửi và đúng với ngữ cảnh request.

CSRF token không cần chứng minh rằng người dùng đã bấm chuột theo nghĩa tuyệt đối. Nó chứng minh request mang một giá trị mà attacker ở ngoài ranh giới tin cậy **thường không thể biết hoặc giả mạo**.

### 2.2. Điều gì bảo vệ token khỏi website bên ngoài?

Có nhiều lớp tham gia:

| Lớp | Khả năng có liên quan |
|---|---|
| **Same-Origin Policy (SOP)** | Ngăn script ở origin khác đọc trực tiếp DOM hoặc nội dung response riêng của ứng dụng đích trong nhiều trường hợp |
| **CORS** | Quy định khi nào script khác origin có thể đọc response/call API theo một số điều kiện; cấu hình sai có thể làm rò rỉ dữ liệu |
| **CSRF repository** | Phát/lưu/kiểm chứng expected token theo session hoặc cơ chế khác |
| **CSRF request handler** | Cung cấp token cho client hợp lệ và đọc submitted token từ form/header |
| **CSRF filter** | Từ chối request thuộc phạm vi kiểm tra khi thiếu/sai token |
| **Cookie SameSite** | Hạn chế một số request cross-site có thể tự gửi cookie |
| **CSP/chống XSS** | Hạn chế khả năng dữ liệu không tin cậy biến thành script chạy trong origin ứng dụng |

**Ranh giới cần giữ:** Attacker ở ngoài origin không thể chỉ việc yêu cầu browser “đọc token giúp tôi” nếu SOP/CORS và các lớp liên quan được triển khai đúng. Attacker có **XSS cùng origin** lại ở vị trí khác: mã chạy ngay trong môi trường mà trình duyệt coi là **script của ứng dụng**.

### 2.3. XSS làm thay đổi loại năng lực nào?

| Năng lực | Attacker chỉ có website ở origin khác | Script XSS đang chạy trong origin đích |
|---|---|---|
| Kích hoạt form POST đến app | Có thể, tùy ngữ cảnh browser | Có |
| Tự động gửi cookie phiên trong request đủ điều kiện | Browser quyết định theo cookie policy | Browser quyết định theo cookie policy; same-origin thường được phép |
| Đọc token trong hidden field/meta tag của app | Thường **không** | Thường **có** nếu DOM chứa token |
| Đọc cookie CSRF không có `HttpOnly` của app | Thường **không** | Thường **có** qua `document.cookie` |
| Đọc cookie session `HttpOnly` | Không | **Không** bằng JavaScript thông thường |
| Gửi POST cùng origin mang cookie `HttpOnly` | Không có script trong origin; chỉ một số request ngoài origin được phép | **Có thể**: browser tự gắn cookie cho request phù hợp |
| Đọc response cùng origin | Thường **không** | Thường **có** |
| Lấy token mới từ form/endpoint cùng origin | Thường **không** | **Có thể** nếu ứng dụng cung cấp kênh đọc phù hợp |

Bảng mô tả năng lực script thực thi **đúng origin ứng dụng và không bị sandbox/quyền hạn khác hạn chế**. Không phải mọi lỗi HTML injection hoặc mọi lỗi ở subdomain đều tương đương XSS cùng origin.

## 3. XSS là gì và nó xuất hiện từ đâu?

**Cross-Site Scripting (XSS)** xảy ra khi dữ liệu không đáng tin cậy được chèn vào trang/ứng dụng theo cách trình duyệt có thể **diễn giải thành mã thực thi hoặc thao tác DOM có quyền của origin đích**, thay vì hiển thị như dữ liệu thuần.

Một số dạng thường gặp:

| Dạng | Đường dữ liệu | Ví dụ nguồn lỗi |
|---|---|---|
| **Reflected XSS** | Input trong request được phản hồi ngay trong HTML không encode đúng | Tham số tìm kiếm được nội suy trực tiếp vào trang kết quả |
| **Stored XSS** | Input nguy hiểm được lưu rồi hiển thị cho người khác | Bình luận, mô tả tài liệu hoặc tên hiển thị được render như HTML tin cậy |
| **DOM-based XSS** | Mã JavaScript phía client tự đưa input không đáng tin cậy vào DOM sink nguy hiểm | `innerHTML` từ `location.search`, dữ liệu API hoặc message không tin cậy |

XSS không nhất thiết phải có một đường endpoint `/execute`. Nó có thể bắt đầu từ một trường văn bản thông thường, tham số URL, nội dung từ API, mô tả sản phẩm, comment hoặc dữ liệu từ hệ thống bên ngoài.

### 3.1. DOM sink nguy hiểm: `innerHTML`

Ví dụ frontend đọc thông điệp từ URL:

~~~javascript
const params = new URLSearchParams(window.location.search);
const message = params.get("message") ?? "";

// KHÔNG AN TOÀN với input không đáng tin cậy:
document.querySelector("#message").innerHTML = message;
~~~

`innerHTML` yêu cầu browser diễn giải input như markup. Dữ liệu không đáng tin cậy có thể chứa cấu trúc HTML có hành vi thực thi hoặc tác động DOM. Không phải mọi `<script>` chèn bằng `innerHTML` đều được thực thi; XSS có nhiều đường thực thi khác. Tránh kết luận “trình duyệt không chạy script tag trong innerHTML nên innerHTML là an toàn”.

Cách đơn giản để hiển thị **văn bản**:

~~~javascript
const params = new URLSearchParams(window.location.search);
const message = params.get("message") ?? "";

// Dữ liệu được coi là text, không diễn giải thành HTML:
document.querySelector("#message").textContent = message;
~~~

Ví dụ đầu tiên minh họa **sink không an toàn**, không phải đề nghị triển khai. Với input phức tạp, cần kiểm soát nguồn dữ liệu, kiểu đầu ra và các sink tương ứng.

### 3.2. Render dữ liệu ở Spring MVC/Thymeleaf

Controller có thể đưa input vào model:

~~~java
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@Controller
class PreviewPageController {

    @GetMapping("/notes/preview")
    String preview(@RequestParam(defaultValue = "") String message,
                   Model model) {
        model.addAttribute("message", message);
        return "notes/preview";
    }
}
~~~

Template hiển thị như text:

~~~html
<!-- templates/notes/preview.html -->
<p id="preview" th:text="${message}">Nội dung xem trước</p>
~~~

`th:text` escape nội dung theo ngữ cảnh text HTML. Ngược lại:

~~~html
<!-- Không dùng với dữ liệu chưa được kiểm soát/sanitize phù hợp. -->
<p th:utext="${message}">Nội dung chưa escape</p>
~~~

`th:utext` render nội dung không escape như HTML. Nó chỉ phù hợp khi nội dung thật sự cần HTML và đã được xử lý bằng **HTML sanitizer allowlist** đáng tin cậy, với chính sách rõ ràng. Không dùng `th:utext` chỉ để “giữ dấu ngoặc” hay “hiển thị chữ đẹp”.

### 3.3. Không phải XSS nào cũng cần đọc cookie

Một nhầm lẫn phổ biến là coi XSS chỉ nguy hiểm khi đọc được `JSESSIONID`. Thực tế:

- Cookie phiên `HttpOnly` giúp hạn chế **đọc chuỗi session ID qua JavaScript**.
- Nhưng mã chạy trong trang ứng dụng vẫn có thể tạo request cùng origin; browser có thể **tự gắn cookie `HttpOnly`**.
- Script cùng origin còn có thể đọc DOM, CSRF token được render, dữ liệu API và phản hồi được phép đọc.

Vì vậy **`HttpOnly` là biện pháp quan trọng để bảo vệ credential khỏi đọc trực tiếp**, nhưng không làm một script XSS mất khả năng tương tác với ứng dụng trong phiên hiện tại.

## 4. XSS phá vỡ giả thiết của CSRF token như thế nào?

### 4.1. Token nằm trong hidden field hoặc meta tag

Một trang form hợp lệ có thể chứa:

~~~html
<form method="post" action="/profile/email">
  <input type="email" name="email">
  <input type="hidden" name="_csrf" value="TOKEN_THUC_CUA_PHIEN">
  <button type="submit">Lưu</button>
</form>
~~~

Hoặc cung cấp token cho JavaScript:

~~~html
<meta name="_csrf" content="TOKEN_THUC_CUA_PHIEN">
<meta name="_csrf_header" content="X-CSRF-TOKEN">
~~~

Với script bên ngoài origin, hai giá trị này thường không được đọc trực tiếp. Nhưng nếu attacker **đưa được JavaScript vào chính origin ứng dụng**, mã đó có thể truy cập DOM tương tự code frontend hợp lệ.

Ví dụ mã JavaScript **hợp lệ của ứng dụng** dùng meta tag để gửi POST:

~~~javascript
const csrfToken = document.querySelector('meta[name="_csrf"]').content;
const csrfHeader = document.querySelector('meta[name="_csrf_header"]').content;

async function savePreference(theme) {
  return fetch("/api/preferences", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      [csrfHeader]: csrfToken
    },
    body: JSON.stringify({ theme })
  });
}
~~~

**Điểm an ninh:** Đây là chức năng bình thường của SPA. Nếu một script XSS chạy trong cùng origin và truy cập được những thành phần này, nó cũng có thể dùng các năng lực frontend tương tự để gửi request dưới phiên browser. **Có token đúng không chứng minh script gọi API là vô hại**.

### 4.2. Token chưa có trên trang hiện tại cũng không hẳn an toàn

Giả sử trang bị XSS không chứa hidden CSRF field. Không nên vội kết luận attacker không thể thao tác:

- Script cùng origin có thể truy cập một trang form khác của ứng dụng và **đọc response** nếu request/cơ chế bảo mật cho phép.
- Nó có thể gọi API cấp CSRF token mà frontend hợp lệ sử dụng.
- Nó có thể điều khiển một form hợp lệ có sẵn hoặc dùng mã ứng dụng đang quản lý token.
- Browser vẫn có thể tự gửi cookie phiên khi script gọi API cùng origin.

Các đường cụ thể phụ thuộc kiến trúc ứng dụng, chính sách CSP, session, token repository và kênh cấp token. XSS **không đảm bảo** mọi token đều lập tức đọc được trong mọi thiết kế, nhưng nó **phá ranh giới quan trọng** mà các mô hình chống CSRF thông thường dựa vào.

### 4.3. Khi cookie CSRF đọc được từ JavaScript

Nhiều SPA dùng `CookieCsrfTokenRepository.withHttpOnlyFalse()` (Servlet) hoặc repository cookie tương ứng ở Reactive. Cookie chuyên dùng cho CSRF có thể được client cùng origin đọc rồi đưa vào header `X-XSRF-TOKEN`.

Nếu xảy ra XSS cùng origin, script không đáng tin cậy cũng có thể:

- Đọc cookie CSRF không `HttpOnly` mà script của ứng dụng đọc được.
- Dùng token đó trong header đúng tên.
- Gửi request dựa trên cookie xác thực được browser tự đính kèm.

**Cookie xác thực vẫn nên `HttpOnly`**, ngay cả khi cookie CSRF cần được JavaScript đọc. Hai cookie không có cùng nhiệm vụ; không được dùng việc “CSRF cookie đọc được” làm lý do mở quyền đọc cho cookie session.

### 4.4. XSS không cần ăn cắp credential mới gây hại

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant B as Trình duyệt tại app.example.com
    participant S as Spring Security
    participant A as API nghiệp vụ

    U->>B: Mở trang chứa dữ liệu đã bị chèn mã XSS
    Note over B: Script không tin cậy chạy trong origin đích
    B->>B: Truy cập DOM hoặc kênh lấy CSRF token của app
    B->>S: Request cùng origin + cookie phiên tự gửi + token hợp lệ
    S->>S: CSRF check thấy token hợp lệ
    S->>A: Tiếp tục xác thực, phân quyền, xử lý
    A-->>B: Response
    Note over S,A: CSRF token không phân biệt script hợp lệ và XSS cùng origin
~~~

Sơ đồ nhằm **giải thích ranh giới tin cậy**; nó không mô tả bước khai thác một ứng dụng cụ thể.

### 4.5. CSRF token vẫn có giá trị dù ứng dụng có thể bị XSS

Không nên suy luận “có XSS là CSRF vô dụng nên tắt CSRF”.

- **Không có XSS cùng origin:** Token đúng vẫn chặn nhiều request từ site khác không thể biết token.
- **Có XSS ở một origin khác:** Kẻ tấn công chưa tự động vượt SOP để đọc token của ứng dụng đích.
- **XSS đã chạy đúng origin ứng dụng:** Cần xử lý XSS khẩn cấp; CSRF token không còn là ranh giới đáng tin cậy để phân biệt mã của attacker và mã của ứng dụng trong origin đó.
- **XSS được vá:** Giữ lớp CSRF token để bảo vệ trước những request giả mạo từ origin ngoài.

CSRF và XSS phải được quản lý như **hai lớp bảo mật độc lập, bổ sung cho nhau**, không phải hai công tắc có thể thay thế.

## 5. So sánh các phương án token khi đối mặt với XSS

| Phương án CSRF | Phòng vệ chính | Khi script XSS chạy trong origin đích |
|---|---|---|
| **Synchronizer token** lưu trong `HttpSession`/`WebSession` | Expected token gắn phiên, client gửi form/header | Script có thể đọc token được phát cho trang hoặc gọi luồng hợp lệ để lấy token khi quyền cho phép |
| **Double-submit cookie** thông thường | Cookie CSRF và header/form chứa cùng giá trị | Script đọc cookie CSRF không `HttpOnly` nếu frontend cần đọc, rồi tạo request hợp lệ |
| **Signed double-submit HMAC gắn phiên** | Ngăn token giả mạo/cookie injection và dùng token của phiên khác | Chữ ký vẫn hợp lệ cho token **được phát trong chính phiên nạn nhân**; XSS có thể dùng nó |
| **Token gốc được XOR/mask khi render** | Hạn chế các kênh rò rỉ liên quan nén phản hồi như BREACH | Nếu mã cùng origin có thể đọc biểu diễn token hợp lệ thì masking không tạo ranh giới mới |
| **Token phát lại mỗi request** | Giới hạn khả năng replay trong một số mô hình | Có thể gây khó cho tấn công replay ngoại tuyến, nhưng script XSS đang chạy có thể theo luồng cấp token hiện tại nếu quyền cho phép |
| **CSRF token trong header** | Trang ngoài không dễ đặt header có token đúng | Script cùng origin có thể đặt header tùy chỉnh như code frontend hợp lệ |

**Điểm mấu chốt:** **Không có thuật toán CSRF token thông thường nào được thiết kế để phân biệt hai đoạn JavaScript cùng chạy với quyền của một origin**. Token ngẫu nhiên dài, HMAC, masking và header tùy chỉnh vẫn quan trọng đối với các mối đe dọa riêng của chúng, nhưng không chữa được lỗi XSS.

### 5.1. XSS và signed double-submit

Một token có ký HMAC gắn phiên giúp server nhận biết token không phải do attacker tự bịa, không phải token lấy từ phiên khác. Nhưng nếu script độc hại đang chạy trong chính phiên browser hợp lệ và đọc được token đã phát, nó **không cần tự tạo chữ ký mới**. Nó chỉ dùng token hợp lệ theo chính sách.

Do đó không nên tuyên bố “đã ký CSRF token nên XSS không thể vượt qua bước CSRF”. Xác minh HMAC và chống XSS là hai công việc khác nhau.

### 5.2. XSS và XOR masking/BREACH

`XorCsrfTokenRequestAttributeHandler` ở Servlet có thể xuất ra các biểu diễn masked khác nhau của cùng raw token nhằm tránh lộ qua một số kênh nén. Đây **không** phải biện pháp chống script cùng origin đọc token trong DOM.

Ví dụ logic:

~~~text
Raw token trong repository: R

Render lần 1: masked(R, random_1) = M1
Render lần 2: masked(R, random_2) = M2

M1 và M2 có thể khác nhau.
Nếu XSS đọc được M1 từ form đang hoạt động,
handler hợp lệ vẫn có thể giải mã M1 rồi so với expected R.
~~~

Không tắt masking chỉ vì có XSS; masking có mục đích riêng. Nhưng cũng không kỳ vọng masking thay output encoding hoặc CSP.

## 6. Phân biệt same-origin XSS với một subdomain bị chiếm quyền

Một trường hợp dễ gây nhầm là attacker kiểm soát `https://blog.example.com`, còn ứng dụng ở `https://app.example.com`.

Hai origin này:

- Có thể **same-site** theo schemeful same-site vì cùng scheme và registrable domain.
- Vẫn **cross-origin** vì hostname khác nhau.
- Theo SOP, mã tại blog **không mặc nhiên được đọc** DOM/meta tag/response riêng origin của app.
- Cookie session của app có thể được browser gửi **đến app** trong một request same-site do blog kích hoạt nếu cookie policy cho phép.

Vì vậy:

| Tình huống | SameSite | SOP | Giá trị của CSRF token |
|---|---|---|---|
| Trang ngoài `evil.other.test` → app | Thường hạn chế cookie cross-site tùy chế độ | Ngăn đọc DOM/response riêng của app | Vẫn là phòng vệ quan trọng |
| Trang `blog.example.com` → app, không có XSS ở app | Cookie Strict/Lax vẫn có thể được gửi vì same-site | Blog vẫn khác origin, thường không đọc được token app | **Rất quan trọng** |
| Script XSS thực thi ngay tại `app.example.com` | Request script tạo thường same-origin | Script được trình duyệt coi là chạy trong origin app | Không đủ để phân biệt script độc hại và hợp lệ |
| Iframe có sandbox origin riêng | Tùy sandbox/cookie policy | Có thể có ranh giới origin khác | Phụ thuộc chính sách sandbox và thiết kế kênh token |

**Hệ quả thiết kế:** Không được kết luận một subdomain bị chiếm quyền tự động có khả năng đọc mọi CSRF token của subdomain khác. Nhưng cũng không được coi SameSite là lớp đủ mạnh chống request từ subdomain cùng site.

### 6.1. Chia sẻ cookie qua Domain quá rộng

Nếu ứng dụng dùng cookie `Domain=example.com`, phạm vi cookie có thể bao gồm nhiều subdomain. Điều đó tăng rủi ro trộn ranh giới tin cậy và một số đường **cookie injection**.

Với cookie phiên, nên cân nhắc host-only, `Secure`, `HttpOnly`, `SameSite` và tiền tố `__Host-` khi phù hợp. Với cookie CSRF, kiểm soát phạm vi, cookie trùng tên và khả năng attacker đặt giá trị là vấn đề bổ sung.

Những cấu hình cookie này giúp thu hẹp một số đường tấn công, **không biến XSS cùng origin thành mã vô hại**.

## 7. HttpOnly, SameSite, CORS, CSP: mỗi thứ ngăn điều gì?

### 7.1. Bảng phân tách trách nhiệm

| Lớp | Có thể giúp chống gì? | **Không** tự giải quyết gì? |
|---|---|---|
| **Cookie `HttpOnly`** | Ngăn JavaScript thông thường đọc trực tiếp cookie credential | Không ngăn browser gửi cookie cho request từ script cùng origin |
| **`Secure` / HTTPS / HSTS** | Giảm rủi ro cookie bị gửi qua kênh không an toàn hoặc truy cập HTTP bị hạ cấp trong phạm vi chính sách | Không ngăn script XSS đã chạy trong trang HTTPS |
| **`SameSite`** | Giới hạn nhiều request cross-site được gửi kèm cookie | Không chặn XSS same-origin; không phải ranh giới giữa subdomain cùng site |
| **CORS** | Kiểm soát quyền đọc response và một số request cross-origin trong browser | Không chặn mã cùng origin; không thay token CSRF |
| **CSRF token** | Chống nhiều yêu cầu giả mạo từ nguồn không biết token | Không tự nhận diện JavaScript độc hại đã chạy trong origin đích |
| **CSP** | Hạn chế nguồn/kiểu script được chạy, có thể giảm nguy cơ XSS | Không thay output encoding; CSP lỏng hoặc sai cấu hình có thể bị vượt |
| **Trusted Types** | Giảm DOM XSS ở các sink được browser hỗ trợ bằng cách ép dùng giá trị được tạo theo policy | Không thay sanitization/encoding, không phủ mọi browser hoặc mọi kiểu XSS |
| **Output encoding / sanitization** | Ngăn dữ liệu không tin cậy bị diễn giải thành mã/HTML nguy hiểm | Không thay CSRF, authentication, authorization |
| **Authorization/re-authentication** | Chặn thao tác khi quyền không đủ hoặc yêu cầu chứng minh bổ sung | Không chữa XSS; một số thao tác vẫn có thể được thực hiện bằng quyền của user hiện tại |

**Defense in depth** không phải cộng một loạt header để “đủ điểm”. Cần hiểu **ranh giới mà từng cơ chế bảo vệ** và kiểm thử các giả thiết của cơ chế đó.

### 7.2. HttpOnly không phải “khóa tương tác” với tài khoản

Xem cookie:

~~~http
Set-Cookie: JSESSIONID=opaque; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

`HttpOnly` rất quan trọng: script không thể dễ dàng lấy `JSESSIONID` qua `document.cookie`.

Nhưng trang web vẫn cần gọi API của chính mình. Do đó script cùng origin có thể dùng `fetch("/api/...", { credentials: "same-origin" })` và browser gửi cookie phù hợp. Với XSS, attacker có thể lợi dụng năng lực ứng dụng hợp lệ **mà không cần biết chuỗi session ID**.

### 7.3. SameSite không chống XSS trong chính site

`SameSite=Strict` hay `Lax` chủ yếu quyết định cookie có được gửi khi request cross-site hay không. Script XSS chạy tại `app.example.com` và gọi `/api/profile` là request cùng origin; vì thế SameSite **không tạo lớp cấm mới**.

SameSite vẫn nên được cấu hình theo chính sách cookie, nhưng không được dùng nó làm lý do bỏ kiểm soát output hoặc bỏ CSP.

### 7.4. CORS không thể chặn mã đã chạy trong origin được phép

Một API có thể chỉ cho phép JavaScript từ `https://app.example.com` đọc response. Nếu XSS xảy ra ngay trong origin này, script độc hại **đứng trong origin được phép**.

CORS không thể nhận biết “JavaScript của ứng dụng” và “JavaScript do input không tin cậy tạo ra” nếu cả hai cùng thực thi trong cùng origin. Nếu cần cô lập nội dung không tin cậy, hãy xem xét **sandbox có origin riêng**, domain riêng và cấu trúc trao đổi thông điệp an toàn, thay vì dựa vào CORS trong cùng origin.

## 8. Phòng vệ XSS: chặn dữ liệu không tin cậy trở thành script

### 8.1. Output encoding phải đúng ngữ cảnh

Không có một hàm “escape mọi thứ” dùng đúng cho tất cả vị trí. Dữ liệu không tin cậy có thể xuất hiện trong:

- HTML text;
- HTML attribute;
- JavaScript string/JSON được nhúng trong HTML;
- URL, URL attribute;
- CSS;
- DOM API/sink phía client.

**Tùy vị trí mà cần quy tắc encoding khác nhau.** Ví dụ HTML text nên dùng template engine escape theo text context như `th:text`. Dữ liệu đưa vào URL cần xây dựng/validate URL theo chính sách riêng; không thể lấy HTML entity encoding để giải quyết mọi trường hợp.

Tránh nối chuỗi HTML tự do:

~~~java
// Mẫu không phù hợp khi message là dữ liệu không tin cậy:
String html = "<div>" + message + "</div>";
~~~

Ưu tiên template engine có auto-escaping và dùng đúng cơ chế xuất dữ liệu.

### 8.2. DOM API: dùng textContent cho dữ liệu text

~~~javascript
const title = responseData.title; // Ví dụ dữ liệu từ API.
const target = document.querySelector("#title");

// Nên làm khi mục đích là hiển thị text:
target.textContent = title;

// Không nên làm nếu title chưa tin cậy/sanitize:
// target.innerHTML = title;
~~~

Các sink như `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write` và những API thực thi chuỗi như `eval` hoặc `new Function` cần được kiểm soát nghiêm ngặt. Các thuộc tính URL nguy hiểm hay event handler nội tuyến cũng cần được kiểm tra theo ngữ cảnh.

### 8.3. Khi bắt buộc cho phép rich text

Ứng dụng có thể cần hiển thị nội dung HTML do người dùng viết (ví dụ mô tả có in đậm/in nghiêng). Khi ấy:

1. Xác định danh sách **thẻ và thuộc tính được phép**.
2. Dùng **HTML sanitizer allowlist được bảo trì** thay vì vài phép thay chuỗi/regex.
3. Kiểm soát protocol của URL, event handler và các cấu trúc có thể kích hoạt script.
4. Không đưa lại nội dung đã sanitize qua một thư viện khác khiến DOM bị biến đổi thành cấu trúc không an toàn.
5. Kiểm thử trên trình duyệt mục tiêu và kiểm tra cập nhật thư viện sanitizer.

Không dùng một regex đơn giản để “loại tất cả `<script>`” rồi coi input đã an toàn. XSS có nhiều ngữ cảnh thực thi không cần thẻ script trực tiếp.

### 8.4. Không phụ thuộc chỉ vào validation đầu vào

Validation giúp bảo đảm **dữ liệu phù hợp quy tắc nghiệp vụ**, ví dụ tên tài khoản không vượt độ dài, email có cấu trúc hợp lệ. Nhưng người dùng có thể có tên chứa dấu nháy hoặc dấu nhỏ hơn theo một số ngữ cảnh.

Output encoding theo ngữ cảnh mới ngăn trình duyệt diễn giải dữ liệu thành HTML/JavaScript nguy hiểm. **Validation và encoding phục vụ mục tiêu khác nhau**, nên có thể cần cả hai.

## 9. Content Security Policy và Trusted Types

### 9.1. CSP hỗ trợ hạn chế việc chạy mã không đáng tin cậy

**Content Security Policy (CSP)** là một response header giúp giới hạn script, style, resource, frame và các cơ chế khác mà trang được phép sử dụng. Với phòng vệ XSS, chính sách nghiêm ngặt có thể giảm khả năng thực thi mã được chèn.

Ví dụ **minh họa cấu trúc** một chính sách định hướng nonce:

~~~http
Content-Security-Policy: default-src 'self'; object-src 'none'; base-uri 'self'; script-src 'nonce-{FRESH_RANDOM_NONCE}'; frame-ancestors 'none'
~~~

`{FRESH_RANDOM_NONCE}` ở đây là **placeholder**, không phải giá trị cố định để chép vào production. Mỗi phản hồi cần nonce ngẫu nhiên đủ mạnh, được sinh ở server và gắn đúng cho script được phép chạy. Không dùng một nonce tĩnh hoặc tái sử dụng rộng rãi như một bí mật bất biến.

Những vấn đề cần chú ý:

- Không tùy tiện thêm `'unsafe-inline'` và `'unsafe-eval'` vì có thể làm yếu chính sách chống XSS.
- Chỉ cho phép nguồn script thực sự cần; một chính sách `script-src 'self'` rộng có thể không đủ nếu origin chứa script/file không tin cậy.
- `Content-Security-Policy-Report-Only` giúp quan sát vi phạm, **không chặn thực thi**.
- CSP không thay việc escape output, sanitization hoặc kiểm soát DOM sink. Nếu attacker đã chạy JavaScript được CSP cho phép, CSRF token vẫn không phân biệt được mã độc với mã tốt cùng origin.

Chính sách CSP phải tương thích cách frontend thực sự tải script, bundle, framework và nonce; không nên sao chép một dòng mẫu mà không kiểm thử chức năng.

### 9.2. Trusted Types giảm rủi ro DOM XSS trong browser hỗ trợ

`Trusted Types` là cơ chế browser hỗ trợ buộc một số DOM sink nhạy cảm nhận giá trị thuộc kiểu tin cậy được tạo theo policy, thay vì chuỗi tùy ý. Ví dụ cấu trúc CSP:

~~~http
Content-Security-Policy: require-trusted-types-for 'script'; trusted-types app-html-policy
~~~

Điều này có thể buộc code phải chuyển dữ liệu qua policy được kiểm soát trước khi chèn vào sink liên quan. **Chỉ khai báo policy không tự bảo đảm policy tạo HTML an toàn**; nội dung policy vẫn phải dùng sanitization đúng.

Hỗ trợ Trusted Types có thể khác theo browser/phiên bản, nên xem đây là lớp hỗ trợ thêm, không là căn cứ duy nhất để ngăn XSS. Nếu ứng dụng không dùng rich HTML, **`textContent` và rendering escape mặc định** thường đơn giản hơn nhiều.

### 9.3. CSP và CSRF token nên được kiểm thử riêng

CSP có thể ngăn một số đường XSS; CSRF filter có thể từ chối form POST giả mạo. Không chứng minh CSP tốt chỉ bằng test `csrf()`, và không chứng minh CSRF tốt chỉ bằng cách đặt CSP header.

Cần test **cả việc mã không tin cậy không được thực thi** lẫn việc **POST thiếu/sai token bị chặn**.

## 10. Ví dụ Servlet: giữ CSRF và render dữ liệu an toàn

### 10.1. SecurityFilterChain cho ứng dụng có phiên

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;

@Configuration
class ServletWebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/assets/**", "/login").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .csrf(csrf -> csrf
                .csrfTokenRepository(new HttpSessionCsrfTokenRepository()))
            .build();
    }
}
~~~

`HttpSessionCsrfTokenRepository` lưu expected token theo phiên; `CsrfFilter` kiểm tra submitted token ở các request cần bảo vệ. Việc này **không escape HTML của controller/template**: phải kiểm soát rendering riêng.

Không tắt CSRF chỉ vì cần xử lý XSS. Ngay cả sau khi đã xử lý input không tin cậy, một trang ngoài origin vẫn có thể thử gửi form giả mạo; token vẫn là một lớp phòng vệ hữu ích.

### 10.2. Một trang vừa render text vừa chứa CSRF token

~~~html
<!-- templates/notes/preview.html -->
<h1>Xem trước ghi chú</h1>

<!-- Dữ liệu từ user được hiển thị như text, không diễn giải HTML. -->
<p id="preview" th:text="${message}">Nội dung ghi chú</p>

<form method="post" action="/notes/save">
  <textarea name="body" required></textarea>

  <!-- Chỉ token thật do Spring Security phát hành. -->
  <input type="hidden"
         th:name="${_csrf.parameterName}"
         th:value="${_csrf.token}">
  <button type="submit">Lưu ghi chú</button>
</form>
~~~

Các ranh giới khác nhau:

- `message`: **dữ liệu không tin cậy**, phải render an toàn bằng `th:text`.
- `_csrf`: **giá trị chống giả mạo** do framework cung cấp cho client hợp lệ.
- `POST /notes/save`: **hành động ghi**, phải qua CSRF filter và authorization.
- Cookie phiên: credential xác thực nên có các thuộc tính bảo vệ phù hợp, ví dụ `HttpOnly`, `Secure`, `SameSite`.

Nếu thay `th:text` bằng `th:utext` trên input không tin cậy, việc vẫn có hidden CSRF token **không chữa được XSS**. Nếu cần dùng `th:action`, lưu ý tích hợp form có thể tự sinh CSRF field; kiểm tra HTML cuối cùng tránh trùng trường.

### 10.3. Cấu hình CSP trong Servlet

Spring Security có cơ chế thêm header CSP, nhưng **không tự sinh một nonce an toàn cho từng script trong template chỉ nhờ dòng cấu hình tĩnh**. Vì vậy một CSP dùng nonce phải có thành phần phối hợp giữa filter/rendering và script tags.

Một ví dụ **không dựa vào nonce** cho trang chỉ tải script đã được kiểm soát từ cùng origin là:

~~~java
http.headers(headers -> headers
    .contentSecurityPolicy(csp -> csp
        .policyDirectives(
            "default-src 'self'; " +
            "script-src 'self'; " +
            "object-src 'none'; " +
            "base-uri 'self'")));
~~~

Đoạn này minh họa API cấu hình header; `script-src 'self'` **không phải chính sách XSS mạnh nhất** trong mọi ứng dụng, nhất là nơi có thể tải script không đáng tin cậy từ cùng origin. Khi có thể triển khai, cần nghiên cứu một CSP chặt hơn dùng nonce/hash, kiểm soát nguồn script và các directive liên quan.

Spring Security không tự escape mọi kết quả HTML/API để chống XSS. Output encoding, DOM sink và sanitization vẫn là trách nhiệm của tầng ứng dụng.

## 11. Ví dụ Reactive/WebFlux: XSS vẫn là vấn đề của view và DOM

WebFlux sử dụng security web filter thay vì Servlet filter, nhưng mô hình tin cậy browser không thay đổi: **mã XSS ở origin đích có thể sử dụng quyền của origin đó**, kể cả khi API viết bằng Mono/Flux.

### 11.1. Bật CSRF theo WebSession

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.csrf.WebSessionServerCsrfTokenRepository;

@Configuration
@EnableWebFluxSecurity
class ReactiveWebSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/assets/**", "/login").permitAll()
                .anyExchange().authenticated())
            .formLogin(Customizer.withDefaults())
            .csrf(csrf -> csrf
                .csrfTokenRepository(new WebSessionServerCsrfTokenRepository()))
            .build();
    }
}
~~~

`CsrfWebFilter` bảo vệ unsafe requests theo cấu hình. `WebSessionServerCsrfTokenRepository` lưu expected token theo WebSession.

Nó **không tự ngăn một reactive view render dữ liệu sai ngữ cảnh**. Một đoạn JS phía client dùng `innerHTML` với dữ liệu từ endpoint Reactive vẫn có thể tạo DOM XSS.

### 11.2. Cung cấp token cho view khi cần

Trong một luồng WebFlux dùng Spring Security, CSRF token có thể được cung cấp qua exchange attribute dưới dạng `Mono<CsrfToken>`:

~~~java
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.reactive.result.view.Rendering;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Controller
class ReactiveNotePage {

    @GetMapping("/notes/preview")
    Mono<Rendering> preview(ServerWebExchange exchange) {
        Mono<CsrfToken> csrf =
                exchange.getAttribute(CsrfToken.class.getName());

        return csrf.map(token ->
            Rendering.view("notes/preview")
                .modelAttribute("_csrf", token)
                .modelAttribute("message", "Nội dung ví dụ")
                .build());
    }
}
~~~

Ví dụ giả định `CsrfWebFilter` đã đưa publisher token vào exchange; ứng dụng có view engine/handler phù hợp để render. Khi lấy message từ người dùng hoặc API, phải **escape output theo đúng ngữ cảnh** thay vì ghép HTML trực tiếp.

### 11.3. Một luồng Reactive không tự an toàn trước XSS

~~~java
// Không phải vấn đề của Mono/Flux nếu HTML rendering phía sau sai.
Mono<String> userInput = service.loadUntrustedNote();
~~~

Nếu frontend nhận note và gọi `target.innerHTML = note`, XSS có thể phát sinh. Nếu frontend dùng `target.textContent = note`, cùng dữ liệu được hiển thị như văn bản. Chọn WebFlux thay cho Servlet **không làm thay đổi Same-Origin Policy hoặc trách nhiệm bảo vệ DOM**.

## 12. Kiểm thử: hai chiều độc lập nhưng liên quan

**Bộ test cần có cả hai nhánh:**

1. **CSRF baseline:** Request ghi thiếu/sai token bị từ chối; request có token hợp lệ và quyền phù hợp được xử lý.
2. **XSS defense:** Dữ liệu không tin cậy không trở thành HTML/script thực thi; kiểm thử output encoding, DOM sink, CSP và các nơi render quan trọng.

Một bài test chỉ chứng minh `POST` thiếu token trả `403` không chứng minh ứng dụng chống XSS. Ngược lại, một bài test xác nhận input đã được escape không chứng minh POST bên ngoài origin có bị CSRF filter chặn hay không.

### 12.1. Ma trận tình huống

| Tình huống | Token CSRF | XSS/nguồn thực thi | Kỳ vọng |
|---|---|---|---|
| POST từ trang ngoài, không biết token | Thiếu/sai | Không có mã trong origin app | Bị CSRF filter từ chối nếu thuộc phạm vi bảo vệ |
| POST hợp lệ từ form ứng dụng | Đúng | Không có XSS | Có thể qua CSRF, vẫn cần authentication/authorization |
| Text người dùng chứa markup, render bằng `th:text` | Không liên quan | Không được biến thành code | Nội dung được escape và hiển thị như text |
| Text người dùng đưa vào `innerHTML` không kiểm soát | Không liên quan | Có nguy cơ DOM XSS | Test phải phát hiện sink không an toàn, sửa rendering |
| XSS đã chạy trong origin app | Có thể tiếp cận token hợp lệ | Có | CSRF token **không phải** ranh giới đáng tin cậy với script đó |
| Attacker chỉ chiếm một sibling subdomain | Không biết token app nếu SOP bảo vệ | Cross-origin | CSRF token của app vẫn có giá trị, dù SameSite có thể cho cookie |
| Cookie phiên đặt `HttpOnly` | Token CSRF riêng nếu cần | XSS cùng origin | Không đọc thẳng session ID; script vẫn có thể gửi request có cookie |
| CSP ở chế độ Report-Only | Như cấu hình CSRF | Đường XSS vẫn có thể chạy | Nhận báo cáo nhưng không tự chặn |
| Action có re-authentication | Có | XSS có thể tạo request | Bước xác minh bổ sung có thể giảm rủi ro, cần thiết kế chống lạm dụng riêng |

### 12.2. Servlet MockMvc: CSRF filter có hoạt động không?

Giả sử ứng dụng có endpoint `POST /notes/save` trả `204 No Content` khi lưu thành công và được bảo vệ bởi `SecurityFilterChain`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfServletDefenseTests {

    @Autowired MockMvc mvc;

    @Test
    void missingTokenIsRejected() throws Exception {
        mvc.perform(post("/notes/save")
                .with(user("alice"))
                .param("body", "Nội dung"))
            .andExpect(status().isForbidden());
    }

    @Test
    void invalidTokenIsRejected() throws Exception {
        mvc.perform(post("/notes/save")
                .with(user("alice"))
                .with(csrf().useInvalidToken())
                .param("body", "Nội dung"))
            .andExpect(status().isForbidden());
    }

    @Test
    void validTokenPassesCsrfLayer() throws Exception {
        mvc.perform(post("/notes/save")
                .with(user("alice"))
                .with(csrf())
                .param("body", "Nội dung"))
            .andExpect(status().isNoContent());
    }
}
~~~

`with(user("alice"))` là mock authentication; `with(csrf())` là helper test, không mô phỏng hoàn chỉnh browser đọc HTML và gửi token thật. Test cuối giả định endpoint trả `204` và user có quyền. Đây là **test của lớp CSRF**, không phải test XSS.

### 12.3. Servlet MockMvc: kiểm tra output encoding trong view

Nếu có `GET /notes/preview` dùng `th:text` như mục 3, test có thể truyền markup **vô hại** để kiểm tra output không bị render như một thẻ HTML thực:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class EscapingServletTests {

    @Autowired MockMvc mvc;

    @Test
    void untrustedMarkupIsRenderedAsText() throws Exception {
        mvc.perform(get("/notes/preview")
                .with(user("alice"))
                .param("message", "<em>test</em>"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                containsString("&lt;em&gt;test&lt;/em&gt;")));
    }
}
~~~

Ví dụ này giả định template Thymeleaf `th:text` trả HTML escape theo ký tự như assertion. Với một template/engine khác, điều quan trọng là **DOM thực không xuất hiện một phần tử `em` do input tạo ra**, không nhất thiết byte encoding phải giống hệt. Một browser-based DOM test nên bổ sung, nhất là cho DOM XSS sau khi JavaScript xử lý response.

### 12.4. Reactive WebTestClient: kiểm tra CSRF WebFilter

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class CsrfReactiveDefenseTests {

    @Autowired ApplicationContext context;

    private WebTestClient client() {
        return WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .build();
    }

    @Test
    void postWithoutTokenIsRejected() {
        client().mutateWith(mockUser("alice"))
            .post().uri("/notes/save")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void postWithTokenPassesCsrfLayer() {
        client().mutateWith(mockUser("alice"))
            .mutateWith(csrf())
            .post().uri("/notes/save")
            .exchange()
            .expectStatus().isNoContent();
    }
}
~~~

Test cuối giả định endpoint Reactive nhận request phù hợp và trả `204`. Để kiểm tra XSS với WebFlux, cần test response/view rendering bằng dữ liệu không tin cậy và, với DOM sink, dùng browser automation trong môi trường được phép. Bản thân WebTestClient không thực thi JavaScript trong trình duyệt.

### 12.5. Browser test an toàn cho XSS/CSRF

Một kế hoạch kiểm thử có thể thực hiện trên **môi trường thử nghiệm được cho phép**:

1. Mở trang có input được hiển thị lại; thử chuỗi markup **vô hại** như `<em>kiểm thử</em>` và xác minh DOM chỉ hiển thị text, không tạo phần tử HTML ngoài dự kiến.
2. Kiểm tra các chỗ nhận dữ liệu từ query string, fragment, `postMessage`, API, form và storage; tìm việc đưa input vào `innerHTML`/DOM sink.
3. Xác nhận trang gửi **CSP ở chế độ enforce** khi yêu cầu; `Report-Only` chỉ thu thập báo cáo.
4. Kiểm tra không có inline script/event handler ngoài chính sách cho phép và nonce/hash thực sự đúng vòng đời.
5. Kiểm tra `GET` chỉ đọc; CSRF filter vẫn từ chối `POST` thiếu/sai token.
6. Tạo hai phiên A/B để xác minh token theo phiên không được dùng chéo khi thiết kế yêu cầu ràng buộc.
7. Kiểm tra cookie session `HttpOnly`, `Secure`, `SameSite`; đừng nhầm việc JS không đọc được cookie với việc JS không gửi được request xác thực.
8. Rà soát các thao tác nhạy cảm như chuyển tiền/đổi MFA/xóa tài khoản có bước xác nhận lại thích hợp, hạn chế dữ liệu/quyền có thể dùng lại trong một phiên bị tấn công.

Không dùng trang thật hoặc dữ liệu người dùng để thử khai thác XSS; test injection và khả năng thực thi chỉ nên tiến hành trong phạm vi được phép với dữ liệu thử nghiệm.

## 13. Kiểm soát nghiệp vụ khi browser đã bị ảnh hưởng

Khi một script độc hại chạy cùng origin, server khó phân biệt nó với frontend hợp lệ chỉ dựa vào CSRF token. Các ràng buộc ở tầng nghiệp vụ vẫn có thể **giảm tác động**:

- **Authorization theo từng tài nguyên và thao tác:** Một user có CSRF token hợp lệ vẫn không được xem dữ liệu hoặc thực hiện thao tác ngoài quyền.
- **Re-authentication/step-up** cho thao tác rủi ro cao: có thể yêu cầu mật khẩu hiện tại, WebAuthn user verification hoặc cơ chế độc lập phù hợp. Một bước chỉ yêu cầu “gửi lại CSRF token” không phải step-up.
- **Giới hạn giao dịch và cảnh báo:** Theo dõi thay đổi bất thường, quản lý rủi ro, xác nhận out-of-band khi cần.
- **Audit và revocation:** Có khả năng phát hiện, chấm dứt phiên và điều tra sau sự cố.
- **Giảm quyền JavaScript:** Không lưu access/refresh token nhạy cảm tùy tiện trong DOM/storage có thể đọc bởi mọi script; cô lập thành phần bên thứ ba.
- **Phân tách origin** cho nội dung người dùng không tin cậy hoặc rich document khi kiến trúc cho phép, với sandbox và giao tiếp có kiểm tra origin.

Các lớp này có thể giảm tác động nhưng **không thay mục tiêu chính là không để XSS thực thi ngay từ đầu**.

## 14. Chẩn đoán và ứng phó khi phát hiện XSS làm suy yếu CSRF

### 14.1. Ma trận nhầm lẫn phổ biến

| Nhận định | Vì sao không đúng hoặc chưa đủ? |
|---|---|
| “CSRF token dài 256 bit nên XSS không thể vượt qua.” | XSS cùng origin có thể **dùng token được cấp hợp lệ**, không cần đoán token |
| “Đã đặt `HttpOnly` nên XSS không nguy hiểm.” | `HttpOnly` ngăn đọc cookie, không ngăn browser gửi cookie cho request từ script cùng origin |
| “`SameSite=Strict` sẽ chặn script XSS.” | Script cùng origin không bị SameSite xem như request cross-site |
| “CSRF token được ký HMAC nên attacker không thể thao tác.” | Nếu script dùng token có chữ ký hợp lệ của chính phiên đang mở, nó không cần giả mạo chữ ký |
| “Token masked khác nhau mỗi lần render nên XSS không đọc được.” | Masking không ngăn DOM script đọc biểu diễn hợp lệ đang có |
| “Đã cấu hình CORS chỉ cho origin của app nên an toàn.” | XSS ở origin app chính là mã chạy trong origin đã được cho phép |
| “CSP có mặt trong response là đủ.” | CSP có thể lỏng, ở Report-Only hoặc không ngăn được mọi sink/đường chạy |
| “Cứ tắt CSRF để đơn giản rồi sửa XSS.” | Hai rủi ro khác nhau; tắt CSRF tạo thêm bề mặt giả mạo request từ origin khác |
| “XSS chỉ có khi tag `<script>` được render.” | DOM/event handler/URL/HTML context cũng có thể tạo điều kiện thực thi mã |
| “WebFlux tự xử lý escaping vì dùng reactive.” | Ngữ nghĩa browser/DOM không phụ thuộc Servlet hay Reactive |
| “XSS ở blog cùng site đồng nghĩa đọc được form app.” | Nếu **khác origin**, SOP vẫn có thể chặn đọc; SameSite và SOP là hai cơ chế khác nhau |

### 14.2. Quy trình xử lý sự cố có căn cứ

Nếu tìm thấy XSS thực tế:

1. **Khoanh vùng đường vào và nơi thực thi:** Input nào bị render không an toàn? Reflected, stored hay DOM-based? Những URL/trang nào chịu ảnh hưởng?
2. **Chặn nguồn và sửa sink:** Dùng output encoding/sanitizer/DOM API an toàn; xử lý dữ liệu stored độc hại đã lưu nếu cần.
3. **Giảm phạm vi tác động:** Cân nhắc tạm thời hạn chế chức năng nhạy cảm, kích hoạt kiểm soát bổ sung hoặc cảnh báo phù hợp với mức độ sự cố.
4. **Rà soát session và token:** Xác định khả năng request trái phép đã được gửi, có credential/token bị rò rỉ không; cân nhắc vô hiệu hóa phiên, thu hồi credential và luân phiên khóa khi **có bằng chứng hoặc nguy cơ liên quan**.
5. **Kiểm tra log theo cách không lộ bí mật:** Tập trung vào thao tác bất thường, route, user, thời gian, origin và chính sách. Không log đầy đủ session ID, access token hay CSRF token.
6. **Thêm regression tests:** Test output encoding, DOM sinks, CSP, phân quyền và CSRF baseline.
7. **Rà soát nguồn chung:** Tìm mẫu render tương tự trên các trang khác, dependency hoặc component có cùng sai sót.
8. **Duy trì phòng vệ nhiều lớp:** Không gỡ CSRF, `HttpOnly`, `Secure`, SameSite hoặc CSP chỉ vì đã vá một vị trí XSS.

Không thể khẳng định “chỉ cần đổi CSRF token là xử lý xong XSS”. Nếu mã XSS vẫn chạy, nó có thể tiếp tục dùng các token hợp lệ mới được cấp. **Phải xử lý nguyên nhân thực thi mã không đáng tin cậy.**

## 15. Câu hỏi tự đánh giá

**Câu 1.** Vì sao hidden CSRF token chống được một form POST từ `evil.other.test` nhưng có thể không chống được script XSS chạy trong `app.example.com`?

**Đáp án:** Trang ngoài origin thường bị SOP/CORS hạn chế đọc token trong DOM/response của app. Script XSS chạy ngay tại origin app có thể đọc token được cấp cho trang hoặc dùng kênh token mà code hợp lệ sử dụng.

**Câu 2.** Cookie session được đặt `HttpOnly; Secure; SameSite=Strict`. Một XSS chạy trong trang ứng dụng có thể gọi API trong phiên đó không?

**Đáp án:** Có thể. `HttpOnly` ngăn script đọc cookie trực tiếp nhưng browser vẫn có thể tự gửi cookie với request cùng origin hợp lệ. SameSite Strict không ngăn request cùng site/origin. API vẫn cần phân quyền và các ràng buộc khác.

**Câu 3.** Ứng dụng dùng signed double-submit token gắn session. Script XSS có cần biết khóa HMAC để gửi request dùng token đúng của phiên hiện tại không?

**Đáp án:** Không nhất thiết. Nếu script đọc hoặc sử dụng được token hợp lệ đã phát trong chính phiên, nó không cần tự ký token mới. HMAC bảo vệ tính toàn vẹn và ràng buộc phiên, không phân biệt script XSS với script frontend hợp lệ cùng origin.

**Câu 4.** Subdomain `blog.example.com` bị chiếm quyền, còn `app.example.com` không bị XSS. Có thể coi CSRF token vô ích vì hai host cùng site không?

**Đáp án:** Không. Chúng vẫn là **hai origin khác nhau**; SOP thường chặn blog đọc token của app. SameSite có thể không chặn cookie trong một request same-site, nên token vẫn có vai trò quan trọng.

**Câu 5.** Tại sao dùng `textContent` thường an toàn hơn `innerHTML` khi chỉ muốn hiển thị ghi chú văn bản?

**Đáp án:** `textContent` coi giá trị là text; `innerHTML` yêu cầu browser phân tích và tạo markup, mở đường cho những cấu trúc không tin cậy có hành vi nguy hiểm. Nếu bắt buộc rich HTML, cần sanitizer allowlist và kiểm soát sink phù hợp.

**Câu 6.** Có thể dùng CSP để bỏ qua output encoding không?

**Đáp án:** Không. CSP là lớp hạn chế thực thi khi có lỗi; output encoding/sanitization đúng ngữ cảnh nhằm ngăn dữ liệu biến thành mã ngay từ đầu. CSP yếu, cấu hình sai hoặc mã đã được cho phép vẫn có thể gây tác động.

**Câu 7.** `MockMvc` test POST thiếu CSRF token trả `403`, POST có token trả `204`. Có đủ để kết luận không có XSS không?

**Đáp án:** Không. Đây là test của CSRF filter. Phải kiểm thử việc dữ liệu không tin cậy được render an toàn và browser không thực thi HTML/JavaScript ngoài ý muốn.

## Kết luận

**Giả thiết quan trọng của CSRF token** là attacker từ origin khác có thể tạo request nhưng **không thể biết hoặc đưa đúng token mà ứng dụng phát hành** trong ngữ cảnh tin cậy. **XSS thực thi trong origin ứng dụng** làm suy yếu giả thiết ấy: script không đáng tin cậy có thể đọc DOM/token hoặc dùng các API cùng origin của frontend, trong khi browser vẫn gửi cookie phiên `HttpOnly` theo quy tắc của nó.

Điều này **không làm CSRF token trở nên vô ích**. Token vẫn chặn nhiều yêu cầu giả mạo từ origin khác và là một lớp bảo vệ cần giữ. Nhưng nó không thể thay **output encoding, DOM API an toàn, HTML sanitization, CSP/Trusted Types, bảo vệ session và phân quyền**. Ngược lại, chống XSS tốt cũng không phải lý do bỏ CSRF trên những endpoint dùng credential tự gửi.

Với **Spring Security Servlet** (`CsrfFilter`, `HttpSessionCsrfTokenRepository`) và **Reactive/WebFlux** (`CsrfWebFilter`, `WebSessionServerCsrfTokenRepository`), cần kiểm thử **hai năng lực độc lập**: request ghi thiếu/sai CSRF token bị từ chối, và dữ liệu không tin cậy không được thực thi như mã trong origin. Chỉ khi cả hai cùng đúng, các lớp CORS, CSP, HSTS, HTTP firewall, cookie/session và CSRF mới hỗ trợ nhau đúng mục đích trong **SPRING_SECURITY_HTTP_PROTECTION**.

## Tài liệu tham khảo

- [OWASP — Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html): encoding theo ngữ cảnh, DOM API an toàn, CSP và những giới hạn.
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): synchronizer token, double-submit token và quan hệ với XSS.
- [MDN — Same-origin policy](https://developer.mozilla.org/en-US/docs/Web/Security/Same-origin_policy): ranh giới đọc/truy cập nội dung giữa các origin.
- [MDN — Content Security Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP): cấu hình CSP và những lớp giới hạn thực thi.
- [Spring Security — CSRF Protection (Servlet)](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): filter, repository, request handler, token masking và SPA.
- [Spring Security — CSRF Protection (WebFlux)](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): CSRF trong ứng dụng Reactive.
