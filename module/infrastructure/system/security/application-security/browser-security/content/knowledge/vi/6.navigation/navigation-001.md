# Top-level navigation: điều hướng trang cấp cao nhất và ranh giới bảo mật trình duyệt

> **Chương:** Navigation  
> **Học phần:** SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY — tìm hiểu ranh giới giữa trình duyệt, origin, cookie và ứng dụng web; thực hành phân biệt Same-Origin Policy (SOP), CORS, cách ly tài liệu và các biện pháp phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types và security headers.

Khi người dùng nhấp vào liên kết để mở trang thanh toán, nhập URL vào thanh địa chỉ, đăng nhập thông qua nhà cung cấp định danh hoặc gửi một biểu mẫu làm chuyển cả tab sang trang kết quả, trình duyệt thực hiện **top-level navigation** (điều hướng cấp cao nhất). Hoạt động này có thể chuyển tài liệu đang hiển thị sang một origin hoàn toàn khác.

Đối với bảo mật web, điều quan trọng là hiểu: **việc trình duyệt cho phép điều hướng tới một trang khác không đồng nghĩa với việc script của trang cũ được đọc nội dung trang mới**. Các quy tắc về quyền truy cập DOM, cookie, CSRF, CORS, iframe sandbox, popup và cách ly cửa sổ được áp dụng ở những bước khác nhau.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt top-level navigation với điều hướng iframe, request `fetch`/XHR và thay đổi URL trong SPA.
2. Mô tả vòng đời của một navigation request, bao gồm redirect, lựa chọn cookie, các header ngữ cảnh và tạo/khôi phục tài liệu đích.
3. Giải thích vì sao điều hướng cross-origin thường thực hiện được dù không có CORS, nhưng script ở origin cũ vẫn chịu SOP.
4. Dự đoán sự khác nhau của cookie `SameSite=Lax` và `SameSite=Strict` với điều hướng GET, gửi form POST, iframe và `fetch`.
5. Thiết kế luồng điều hướng an toàn trước CSRF, open redirect, reverse tabnabbing, clickjacking và điều hướng ngoài ý muốn từ iframe.
6. Dùng DevTools và một bài thực hành hai site trên localhost để kiểm chứng những hành vi này.

## 1. Top-level navigation là gì?

### 1.1 Top-level và nested navigable

Một **top-level navigable** là vùng điều hướng cấp cao nhất của một tab hoặc cửa sổ; bên trong nó có thể chứa nhiều **nested navigable** như iframe. Thuật ngữ *top-level browsing context* vẫn thường gặp trong tài liệu cũ.

~~~text
Tab trình duyệt (top-level navigable)
└── Document: https://app.example.com
    ├── iframe A: https://pay.example.net
    └── iframe B: https://help.example.com
~~~

**Top-level navigation** thay đổi tài liệu ở cấp tab/cửa sổ, chẳng hạn khi tab chuyển từ `https://app.example.com` sang `https://pay.example.net`. **Iframe navigation** chỉ đổi tài liệu trong iframe, không nhất thiết thay đổi tài liệu của tab.

Điều hướng là khái niệm về **tài liệu và lịch sử phiên (session history)**; không phải mọi thay đổi URL đều tạo network request mới. Trình duyệt có thể phục hồi trang từ **back/forward cache (bfcache)**, dùng HTTP cache, service worker, hoặc thực hiện *same-document navigation*.

### 1.2 Những cách thường khởi tạo top-level navigation

| Tác nhân | Ví dụ | Kết quả thường gặp |
|---|---|---|
| Người dùng | Nhập URL vào thanh địa chỉ | Tab đi tới tài liệu tại URL đích |
| Liên kết HTML | `<a href="https://example.net">` | Điều hướng tab hiện tại nếu không chọn target khác |
| JavaScript của top-level document | `location.assign(url)` | Thực hiện điều hướng tới tài liệu/địa chỉ mới |
| JavaScript | `location.replace(url)` | Điều hướng và thay entry lịch sử hiện tại, có một số ngoại lệ theo thuật toán navigation |
| Biểu mẫu HTML | `<form action="/checkout" method="POST">` | Gửi form; response có thể trở thành tài liệu mới |
| Máy chủ | HTTP `302`, `303`, `307` hoặc `308` | Trình duyệt đi tiếp theo `Location` nếu hợp lệ |
| Mở cửa sổ | `window.open(url)` hoặc link `target="_blank"` | Tạo một top-level navigable mới, tùy chính sách popup/noopener |
| Lịch sử trình duyệt | Back, Forward, Reload | Đi tới entry lịch sử; có thể không có network request mới |

Ví dụ điều hướng bằng liên kết:

~~~html
<a href="https://accounts.example.net/login">
  Đăng nhập qua nhà cung cấp khác
</a>
~~~

Việc liên kết cross-origin được phép hoạt động **không yêu cầu** máy chủ đích trả header CORS cho trang nguồn. Một số giới hạn khác vẫn có thể áp dụng, chẳng hạn sandbox của iframe, chính sách popup, scheme bị cấm, cơ chế duyệt hoặc chặn trang nguy hiểm.

### 1.3 Phân biệt với `fetch`, iframe và SPA

~~~mermaid
flowchart TD
    A["Trang tại app.example.com"] --> B{"Thao tác nào?"}
    B --> C["Nhấp link / location.assign"]
    B --> D["fetch / XHR"]
    B --> E["iframe.src = URL"]
    B --> F["history.pushState"]
    C --> G["Có thể thay tài liệu top-level"]
    D --> H["Dữ liệu trả về cho JavaScript<br/>không thay trang tự động"]
    E --> I["Chỉ điều hướng iframe"]
    F --> J["Thay URL / history trong<br/>tài liệu hiện tại; không tự fetch"]
~~~

- **Top-level navigation:** trình duyệt điều hướng vùng cấp cao nhất. Khi navigation tạo tài liệu mới, tài liệu đó nhận môi trường thực thi của nó và origin tương ứng.
- **Fetch/XHR:** trang hiện tại lấy tài nguyên bằng JavaScript; response cross-origin thường phải qua CORS mới được JavaScript đọc.
- **Iframe navigation:** tải/đổi tài liệu trong frame; SOP và sandbox quyết định quyền tương tác với parent.
- **SPA client-side routing:** `history.pushState`, `replaceState` hoặc đổi hash có thể thay URL/history mà không tạo tài liệu mới. `pushState` chỉ được dùng URL cùng origin và không tự tải tài nguyên.

Ví dụ:

~~~js
// Điều hướng toàn trang: tài liệu hiện tại có thể bị thay.
window.location.assign('https://accounts.example.net/login');

// Request dữ liệu: không tự thay tài liệu đang hiển thị.
const response = await fetch('https://api.example.net/profile');

// Đổi URL trong SPA (chỉ URL cùng origin).
history.pushState({ screen: 'orders' }, '', '/orders');
~~~

## 2. Vòng đời của một top-level navigation

Giả sử người dùng ở `https://shop.example.com/cart` nhấn nút thanh toán và điều hướng tới `https://checkout.example.net/start`.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant O as Tài liệu nguồn
    participant B as Trình duyệt
    participant S as Máy chủ đích
    U->>O: Nhấp liên kết thanh toán
    O->>B: Yêu cầu điều hướng URL
    Note over B: Kiểm tra target, sandbox, CSP liên quan<br/>và ngữ cảnh kích hoạt của người dùng
    Note over B: Chọn credentials/cookie, referrer<br/>và Fetch Metadata
    B->>S: Navigation request GET /start
    alt Máy chủ redirect
        S-->>B: 302/303/307/308 + Location
        B->>S: Request theo URL/method sau redirect
    end
    S-->>B: HTML + response headers
    Note over B: Áp dụng kiểm tra navigation<br/>và chính sách tài liệu đích
    B-->>U: Hiển thị tài liệu đích trong tab
~~~

### Bước 1: Xác định đích điều hướng và quyền khởi tạo

Trình duyệt xác định URL, loại điều hướng, target (`_self`, `_top`, `_blank`...), ngữ cảnh tài liệu khởi tạo, quyền popup, sandbox và mức độ **user activation**.

- Một trang top-level thông thường có thể điều hướng chính nó sang URL khác.
- Một iframe khác origin không mặc nhiên được phép buộc tab cha điều hướng trong mọi trường hợp. Trình duyệt áp dụng hạn chế điều hướng cấp cao nhất và, nếu iframe có sandbox, các cờ quyền tương ứng.
- `target="_blank"` hoặc `window.open` có thể bị giới hạn khi không có hành động người dùng; popup cũng có thể bị trình duyệt chặn.
- Navigation do script khởi tạo và navigation do nhấp chuột có thể có dấu hiệu user activation khác nhau trong request.

### Bước 2: Chuẩn bị navigation request

Với điều hướng tài liệu cấp cao nhất, request thường có:

~~~http
GET /start HTTP/1.1
Host: checkout.example.net
Accept: text/html,...
Sec-Fetch-Mode: navigate
Sec-Fetch-Dest: document
Sec-Fetch-Site: cross-site
Sec-Fetch-User: ?1
Referer: https://shop.example.com/
~~~

Đây là **ví dụ minh họa**, không phải bộ header bắt buộc. Trình duyệt, cấu hình quyền riêng tư, loại điều hướng và redirect quyết định header thực tế. `Sec-Fetch-User: ?1` thường xuất hiện khi điều hướng có user activation và có thể vắng mặt khi không có. `Sec-Fetch-Site` có thể là `same-origin`, `same-site`, `cross-site` hoặc `none` tùy ngữ cảnh.

**Fetch Metadata** giúp máy chủ hiểu request xuất phát từ đâu và nhằm mục đích gì, nhưng không phải chứng cứ về danh tính người dùng: HTTP client ngoài trình duyệt có thể tự tạo header. Server vẫn cần xác thực và phân quyền thực sự.

**Origin** header có thể xuất hiện ở form POST và một số kiểu navigation; **không giả định mọi GET navigation đều gửi `Origin`**. Giá trị header `Referer` phụ thuộc `Referrer-Policy` và có thể vắng mặt hoặc bị rút gọn.

### Bước 3: Trình duyệt quyết định cookie được gửi

Trình duyệt đánh giá cookie phù hợp với host/domain, path, `Secure`, `SameSite`, thời hạn, chính sách chặn cookie và ngữ cảnh request. **Top-level navigation** đặc biệt quan trọng đối với một số ngoại lệ SameSite của cookie, sẽ phân tích kỹ ở phần 4.

### Bước 4: Xử lý HTTP redirect

Máy chủ có thể phản hồi:

~~~http
HTTP/1.1 303 See Other
Location: /checkout/result
Cache-Control: no-store
~~~

Trình duyệt thường tiếp tục điều hướng tới đích mới. Mỗi bước redirect có thể đổi host, scheme hoặc method và khiến cookie/phạm vi bảo mật phải được xem xét lại; đừng suy đoán request cuối luôn cùng origin với request đầu.

| Status | Điểm cần nhớ khi redirect |
|---|---|
| `301 Moved Permanently`, `302 Found` | Với một số luồng POST, user agent có thể chuyển request tiếp theo sang GET; không dựa vào mã này để bảo toàn method |
| `303 See Other` | Phổ biến sau POST: điều hướng theo `Location` bằng GET (trừ một số ngữ nghĩa như HEAD) |
| `307 Temporary Redirect` | Giữ nguyên phương thức và body khi redirect theo quy tắc HTTP |
| `308 Permanent Redirect` | Giữ nguyên phương thức và body khi redirect theo quy tắc HTTP |

**Post/Redirect/Get (PRG)** dùng POST để xử lý thay đổi và redirect 303 sang trang GET hiển thị kết quả. PRG cải thiện trải nghiệm khi tải lại trang và làm rõ semantics, nhưng **không thay thế CSRF token**.

### Bước 5: Tài liệu đích được tải, tạo hoặc khôi phục

Khi nhận response cho điều hướng tới tài liệu mới, trình duyệt xác định môi trường tài liệu đích, áp dụng response headers và xác định origin theo URL/ngữ cảnh/chính sách sandbox. DOM của tài liệu đích không tự trở thành dữ liệu mà trang nguồn được phép đọc.

Một số thao tác như chuyển hash trong cùng tài liệu, điều hướng lịch sử được phục hồi từ bfcache hoặc navigation được đáp ứng qua service worker có thể không tạo HTTP request mới. Khi điều tra, hãy nhìn cả **Network** và **Performance/Navigation Timing** trong DevTools thay vì mặc định mọi lần đổi URL đều gọi mạng.

## 3. Top-level navigation, SOP và CORS

### 3.1 Có thể điều hướng cross-origin mà không cần CORS

Giả sử trang ở `https://shop.example.com` chứa:

~~~html
<a href="https://reports.example.net/dashboard">
  Mở báo cáo
</a>
~~~

Người dùng nhấp link; trình duyệt thường có thể tải và hiển thị trang `reports.example.net`. Server đích **không cần** trả `Access-Control-Allow-Origin` để cho phép một navigation thông thường.

Ngược lại, đoạn code:

~~~js
const response = await fetch('https://reports.example.net/dashboard');
const html = await response.text();
~~~

là request do JavaScript muốn đọc response từ origin khác; CORS sẽ áp dụng theo cơ chế Fetch tương ứng. Nếu server không cho phép origin gọi, browser có thể đã gửi request nhưng từ chối cho script đọc response.

| Hoạt động | Có cần header CORS để dùng response? | Ai được đọc nội dung? |
|---|---|---|
| Nhấp link cross-origin mở trang trong tab | **Thông thường không** | Tài liệu đích được render và script của chính nó chạy theo policy của nó |
| Form cross-origin điều hướng tới response | **Thông thường không** | Trang đích trở thành tài liệu được hiển thị; SOP ngăn trang nguồn đọc tùy ý |
| `fetch` cross-origin ở mode `cors` | **Có**, để script đọc response | JavaScript tại origin gọi khi CORS hợp lệ |
| Iframe tải một HTML cross-origin | **Không dựa trên CORS thông thường** | Iframe hiển thị nhưng parent không được tùy ý đọc DOM do SOP |
| `fetch` cross-origin mode `no-cors` | Không mở quyền đọc JSON/HTML | Response thường là `opaque` đối với JavaScript |

**CORS bảo vệ quyền truy cập response từ script**, chứ không phải cơ chế cấm liên kết/điều hướng giữa mọi website. Đây cũng là lý do không dùng CORS làm biện pháp CSRF duy nhất.

### 3.2 SOP bảo vệ DOM khi tài liệu thay đổi origin

Nếu trang A mở trang B khác origin trong một cửa sổ:

~~~js
const popup = window.open('https://accounts.example.net/login', '_blank');
~~~

khi popup đã hiển thị tài liệu khác origin, script của A không được tùy ý đọc `popup.document.body`. Tùy chính sách mở cửa sổ, A có thể chỉ còn các quyền hạn chế như gửi message hoặc yêu cầu điều hướng; **COOP** có thể tách quan hệ opener mạnh hơn.

Nếu A tự điều hướng chính tab của nó sang B, script của tài liệu cũ không còn là script của tài liệu mới. Script của B được chạy với origin B và chỉ có quyền theo chính sách của B.

SOP không ngăn người dùng **nhìn thấy** trang B, cũng không cho A quyền đọc DOM B chỉ vì chính A khởi tạo navigation.

### 3.3 Same-origin, same-site và cross-site khác nhau

Từ `https://app.example.com`:

| Đích | So với URL nguồn | Ý nghĩa |
|---|---|---|
| `https://app.example.com/orders` | Same-origin và same-site | Không đổi bộ ba origin |
| `https://api.example.com` | Cross-origin, thường same-site | Khác subdomain; vẫn cùng scheme + registrable domain |
| `https://app.example.com:8443` | Cross-origin, same-site | Khác port; site thường bỏ qua port |
| `http://app.example.com` | Cross-origin và cross-site theo **schemeful same-site** | HTTPS và HTTP thuộc site khác nhau |
| `https://accounts.example.net` | Cross-origin, cross-site | Khác registrable domain |

**SOP/CORS xét origin**; **SameSite của cookie xét site** cùng các ngữ cảnh liên quan. Vì thế một navigation có thể khác origin nhưng vẫn same-site.

## 4. Cookie SameSite trong top-level navigation

### 4.1 Vì sao top-level navigation đặc biệt với `SameSite=Lax`?

Một session cookie ví dụ:

~~~http
Set-Cookie: __Host-session=RANDOM_SESSION; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

- `Secure` yêu cầu truyền cookie theo ngữ cảnh an toàn được hỗ trợ.
- `HttpOnly` ngăn JavaScript đọc cookie trực tiếp bằng `document.cookie`, nhưng không tự chặn việc browser gửi cookie hợp lệ.
- Prefix `__Host-` yêu cầu `Secure`, `Path=/` và không có `Domain`, giới hạn phạm vi cookie.
- `SameSite=Lax` vẫn cho phép gửi cookie trong nhiều trường hợp **top-level cross-site navigation dùng phương thức an toàn**, điển hình GET; khác với form POST cross-site.
- `SameSite=Strict` thường không gửi cookie trong cross-site navigation, kể cả GET.
- `SameSite=None; Secure` cho phép cookie trong nhiều ngữ cảnh cross-site khi chính sách browser/third-party cookie cho phép.

Top-level navigation có ngoại lệ Lax như trên; **iframe và fetch cross-site không tự được hưởng ngoại lệ chỉ vì chúng cũng có thể tạo GET request**.

### 4.2 Dự đoán cookie theo tình huống

Giả sử người dùng có cookie `session` dành cho `https://bank.example`, cookie đã được tạo trước đó và browser không có hạn chế bổ sung:

| Request đến bank.example | `SameSite=Strict` | `SameSite=Lax` | `SameSite=None; Secure` |
|---|---|---|---|
| Người dùng ở site khác nhấp link mở bank.example bằng top-level GET | Thường không gửi | **Thường gửi** | Có thể gửi |
| Trang khác gửi form POST top-level đến bank.example | Không gửi | **Không gửi** theo quy tắc Lax tường minh | Có thể gửi |
| Trang khác nhúng iframe GET từ bank.example | Không gửi | Không gửi | Có thể gửi, tùy chính sách cookie bên thứ ba |
| Script từ site khác `fetch` GET đến bank.example | Không gửi | Không gửi | Chỉ có thể gửi khi `credentials` và chính sách cookie cho phép |
| Một trang cùng site gửi request đến bank.example | Có thể gửi | Có thể gửi | Có thể gửi, nếu Domain/Path/Secure và các điều kiện khác phù hợp |

Các ô “có thể gửi” **không hứa chắc cookie sẽ đi**. Cần xét `Domain`/host-only, `Path`, trạng thái đăng nhập, chính sách tracking protection, cookie partitioning, HTTPS, quyền gửi credentials và các trường hợp đặc biệt.

**Lưu ý:** Một số trình duyệt từng có cơ chế tương thích cho cookie **không khai báo SameSite** trong khoảng thời gian ngắn sau khi tạo. Đừng phụ thuộc hành vi mặc định đó. Với phòng vệ CSRF, đặt `SameSite` **tường minh** và kiểm tra trên các browser mục tiêu.

### 4.3 Top-level GET là rủi ro nếu GET làm thay đổi trạng thái

Giả sử ứng dụng sử dụng GET để thực hiện hành động:

~~~http
GET /transfer?to=attacker&amount=1000 HTTP/1.1
Host: bank.example
Cookie: session=...
~~~

Nếu URL này được mở bằng top-level cross-site navigation, cookie `SameSite=Lax` có thể vẫn đi theo. Khi đó hành động có thể bị kích hoạt dù kẻ tấn công không đọc được response.

**Quy tắc thiết kế:** GET/HEAD và các phương thức an toàn phải không gây thay đổi trạng thái nghiệp vụ theo ý nghĩa ứng dụng. Dùng POST/PATCH/DELETE cho thao tác thay đổi dữ liệu, yêu cầu **CSRF token/biện pháp tương đương** khi xác thực dựa trên cookie, kiểm tra `Origin`/`Referer` có chính sách fallback phù hợp và xét `Sec-Fetch-Site` như lớp bổ trợ.

CORS không cứu được endpoint GET thay đổi trạng thái: browser có thể gửi navigation request mà không cần cấp quyền đọc cho JavaScript ở trang nguồn.

### 4.4 Phân biệt điều hướng và gửi dữ liệu qua form

~~~html
<!-- Người dùng điều hướng bằng GET -->
<a href="https://bank.example/account">Xem tài khoản</a>

<!-- Form POST có thể tạo cross-site navigation mà không cần CORS -->
<form method="POST" action="https://bank.example/transfer">
  <input name="amount" value="1000">
  <button>Gửi</button>
</form>
~~~

Việc form POST không được đính kèm một cookie Lax trong ngữ cảnh cross-site **không đủ để đảm bảo an toàn cho mọi ứng dụng**. Có thể tồn tại cookie khác `SameSite=None`, luồng same-site qua subdomain bị kiểm soát kém, endpoint không cần cookie, hoặc lỗi logic. Phòng vệ CSRF vẫn phải được thực hiện tại server theo mô hình xác thực thực tế.

## 5. Iframe có được điều hướng trang cấp cao nhất không?

### 5.1 `target="_top"` là yêu cầu, không phải quyền tự động

HTML có thể yêu cầu mở link hoặc form ở top-level:

~~~html
<a href="https://accounts.example.net/login" target="_top">
  Mở đăng nhập trên toàn tab
</a>
~~~

Từ iframe, kết quả còn phụ thuộc quyền điều hướng của browsing context, sandbox, các quy tắc liên quan user activation và browser. **Một iframe khác origin không được phép tùy tiện chiếm tab cha trong mọi ngữ cảnh**.

Iframe sandbox có các cờ liên quan:

| Sandbox flag | Khả năng liên quan đến top-level navigation |
|---|---|
| Không có `allow-top-navigation` và `allow-top-navigation-by-user-activation` | Mặc định bị sandbox hạn chế điều hướng top-level |
| `allow-top-navigation-by-user-activation` | Có thể cho phép điều hướng top-level khi có **transient user activation** phù hợp |
| `allow-top-navigation` | Bỏ hạn chế sandbox tương ứng ngay cả khi không có user activation; cần cân nhắc rủi ro |
| `allow-popups` | Cho phép mở popup theo các điều kiện khác; không đồng nghĩa được điều hướng top-level cha |
| `allow-popups-to-escape-sandbox` | Popup mới có thể không kế thừa sandbox; phải đánh giá riêng nếu dùng |
| `allow-same-origin` | Liên quan effective origin của iframe, **không phải cờ cho phép top navigation** |

Ví dụ một iframe nội dung đối tác có thể cần cho phép người dùng nhấp để đi đến luồng xác thực chính thức:

~~~html
<iframe
  title="Widget đối tác"
  src="https://partner.example.net/widget"
  sandbox="allow-scripts allow-forms allow-top-navigation-by-user-activation">
</iframe>
~~~

Cấu hình này chỉ là ví dụ về quyền tối thiểu theo nhu cầu; không mặc nhiên thêm `allow-top-navigation` hoặc `allow-same-origin` cho nội dung không đáng tin. Việc dùng iframe còn chịu CSP `frame-src` của trang cha và `frame-ancestors` của trang con.

### 5.2 Clickjacking và top-level navigation là hai hướng khác nhau

**Clickjacking** thường liên quan đến việc trang độc hại nhúng một trang thật trong iframe rồi lừa người dùng thao tác trên giao diện bị che phủ.

Để **chặn trang của mình bị nhúng**, máy chủ có thể trả:

~~~http
Content-Security-Policy: frame-ancestors 'none'
X-Frame-Options: DENY
~~~

Các header này **chặn việc bị nhúng** khi chính sách được thực thi; chúng **không nhằm chặn người dùng mở trang đó trực tiếp bằng top-level navigation**.

Phân biệt:

- `frame-ancestors`: ai được nhúng **trang hiện tại**.
- `frame-src`: **trang hiện tại** được tải iframe từ nguồn nào.
- Thuộc tính iframe `sandbox`: tài liệu **được nhúng** có quyền gì.
- `form-action` của CSP: giới hạn endpoint mà **trang hiện tại** được gửi form tới; có thể tác động tới navigation do form.
- CORS: quyền đọc response cross-origin qua API dành cho script; không phải chính sách nhúng hoặc điều hướng nói chung.

## 6. Popup, `window.opener`, reverse tabnabbing và COOP

### 6.1 Nguy cơ reverse tabnabbing

Một trang mở trang bên ngoài vào tab mới có thể tạo quan hệ **opener**. Dù SOP ngăn trang đích đọc DOM của opener khác origin, một số quyền tương tác bị giới hạn nhưng vẫn nguy hiểm có thể còn tồn tại, chẳng hạn thử chuyển địa chỉ trang đã mở.

Ví dụ link an toàn, rõ ý định:

~~~html
<a href="https://external.example.net"
   target="_blank"
   rel="noopener noreferrer">
  Xem tài liệu bên ngoài
</a>
~~~

- `noopener`: tránh cấp quan hệ `window.opener` cho tab mới trong bối cảnh hỗ trợ.
- `noreferrer`: không gửi thông tin referrer và thường cũng mang hiệu ứng noopener.
- Browser hiện đại thường ngầm áp dụng hành vi noopener cho nhiều link `target="_blank"`; khai báo rõ giúp biểu đạt chủ đích và tương thích.

Với JavaScript:

~~~js
window.open(
  'https://external.example.net',
  '_blank',
  'noopener,noreferrer'
);
~~~

Việc cửa sổ được mở hay bị chặn vẫn tùy user activation, popup policies và browser.

### 6.2 Cross-Origin-Opener-Policy (COOP)

**COOP** là response header giúp kiểm soát quan hệ giữa các top-level documents khi điều hướng hoặc mở cửa sổ, có thể tách browsing context group để giảm liên kết không mong muốn giữa các origin.

Ví dụ trang nhạy cảm có thể gửi:

~~~http
Cross-Origin-Opener-Policy: same-origin
~~~

Điều này có thể khiến các trang khác origin không duy trì quan hệ opener trực tiếp theo cách thông thường. Nó cũng có thể ảnh hưởng những luồng đăng nhập popup hoặc thanh toán bên thứ ba vốn cần trao đổi với cửa sổ mở chúng.

Các chính sách như `same-origin-allow-popups` cần được đánh giá theo nhu cầu ứng dụng và hành vi tích hợp thực tế; không nên nới chính sách tùy tiện. **COOP không thay thế SOP, CORS, xác thực hoặc CSRF**.

### 6.3 `postMessage` cho giao tiếp giữa các cửa sổ

Nếu ứng dụng thật sự cần gửi một thông điệp qua popup khác origin, dùng `postMessage` với origin đích được xác định:

~~~js
const popup = window.open('https://login.example.net', '_blank');

if (popup) {
  // Chỉ là ví dụ cách gửi thông điệp; thực tế nên đợi handshake phù hợp.
  popup.postMessage(
    { type: 'request-ready', version: 1 },
    'https://login.example.net'
  );
}
~~~

Ở phía nhận cần kiểm tra **`event.origin`, `event.source`, cấu trúc `event.data` và quyền nghiệp vụ**. Thực tế phải tính đến việc popup đã tải xong chưa, nó có điều hướng sang trang khác không, và COOP có làm mất quan hệ opener hay không. Không dùng `targetOrigin: "*"` cho bí mật; không thực thi trực tiếp HTML/mã từ message.

## 7. Redirect, OAuth và một số rủi ro điều hướng

### 7.1 Open redirect

Endpoint dạng sau đáng lo nếu nhận URL đích tùy ý:

~~~http
GET /redirect?next=https://attacker.example/phishing HTTP/1.1
Host: app.example.com
~~~

Nếu server phản hồi:

~~~http
HTTP/1.1 302 Found
Location: https://attacker.example/phishing
~~~

một liên kết bắt đầu bằng domain của ứng dụng có thể đưa người dùng sang trang lừa đảo. Open redirect còn có thể làm hỏng các giả định về redirect URI hoặc luồng đăng nhập nếu bị đưa vào vùng tin cậy.

Phòng vệ:

1. Với redirect **nội bộ**, ưu tiên ánh xạ mã đích hoặc đường dẫn nội bộ được kiểm soát.
2. Nếu cần redirect **ra ngoài**, xác thực URL bằng parser và allowlist chính xác cho scheme/host/origin; xử lý cả URL tương đối, dạng `//other.example`, userinfo, encoding và chuẩn hóa URL.
3. Không dùng phép so chuỗi `startsWith('https://trusted.example')`: các giá trị như `https://trusted.example.attacker.test` có thể vượt qua kiểm tra ngây thơ.
4. Với OAuth/OIDC, kiểm soát `redirect_uri` theo quy tắc provider, dùng `state` và các biện pháp như PKCE khi áp dụng; không xem việc bắt đầu tại domain tin cậy là bằng chứng redirect cuối cũng đáng tin.

### 7.2 Redirect từ HTTP sang HTTPS

Điều hướng ban đầu tới HTTP có thể để lộ request trên đường truyền trước khi nhận redirect HTTPS. **HSTS** giúp browser đã biết chính sách chuyển sang HTTPS trước khi gửi request HTTP tương ứng; preload list có thể hỗ trợ ngay từ lần đầu ở các browser có dữ liệu đó.

Ví dụ response HTTPS:

~~~http
Strict-Transport-Security: max-age=31536000; includeSubDomains
Referrer-Policy: strict-origin-when-cross-origin
X-Content-Type-Options: nosniff
~~~

`includeSubDomains` chỉ nên dùng khi toàn bộ subdomain trong phạm vi đều có thể phục vụ HTTPS phù hợp. HSTS không bảo vệ khi bản thân ứng dụng có XSS hoặc lỗi phân quyền.

### 7.3 Tham số nhạy cảm trong URL

Khi điều hướng, URL có thể xuất hiện trong history, logs, analytics và một số dạng referrer theo chính sách. **Không đặt session token, mật khẩu hay bí mật lâu dài trong query parameter**.

Trong các luồng xác thực, sử dụng cơ chế được tiêu chuẩn hóa, `state` chống ghép sai phiên/CSRF của authorization flow, PKCE khi phù hợp và chính sách referrer. Thực hiện đổi mã/tạo phiên ở thành phần đáng tin và tránh ghi log dữ liệu nhạy cảm.

## 8. Server đọc được gì từ navigation request?

### 8.1 Fetch Metadata

Một top-level navigation có thể có:

~~~http
GET /checkout HTTP/1.1
Host: shop.example.com
Sec-Fetch-Mode: navigate
Sec-Fetch-Dest: document
Sec-Fetch-Site: cross-site
Sec-Fetch-User: ?1
~~~

Máy chủ có thể dùng Fetch Metadata để hỗ trợ từ chối một số request bất thường, chẳng hạn endpoint chỉ dành cho API nội bộ lại nhận cross-site `no-cors` request. Tuy vậy:

- `navigate` không chứng minh request do người dùng thực sự muốn thực hiện thao tác nhạy cảm.
- `Sec-Fetch-User: ?1` biểu thị user activation trong ngữ cảnh hỗ trợ, **không phải xác thực hay token CSRF**.
- Các header này có thể vắng ở client cũ hoặc client không phải browser.
- Một số điều hướng cross-site là hợp lệ, ví dụ login callback, link tới trang công khai và luồng thanh toán.
- Quy tắc chặn phải xét endpoint, method, mục đích và các ngoại lệ hợp lệ, không nên từ chối toàn bộ navigation từ site khác.

### 8.2 Header `Origin` và `Referer`

Với request gây thay đổi trạng thái, có thể kiểm tra `Origin`, hoặc `Referer` khi cần, để bổ trợ CSRF. Một số request navigation GET không mang `Origin`. `Referer` có thể chỉ còn origin, bị ẩn hoặc thiếu hoàn toàn do chính sách riêng tư.

Thiết kế server nên xác định rõ:

- Endpoint nào chấp nhận request cross-site và vì sao.
- Cách xử lý header thiếu hoặc bị ghi `null`.
- Cách đối chiếu origin với allowlist chuẩn hóa và URL đích.
- Các biện pháp chống CSRF, xác thực, phân quyền không phụ thuộc duy nhất vào các header do client gửi.

## 9. Thực hành: navigation khác CORS và SameSite như thế nào?

Mục tiêu: quan sát **top-level GET**, **top-level POST** và **fetch cross-origin** trong DevTools; đồng thời so sánh cookie `SameSite=Lax`.

Thí nghiệm dùng **hai hostname khác nhau**, không chỉ hai cổng:

- Trang A: `http://localhost:3000`.
- Trang B: `http://127.0.0.1:4000`.

Hai địa chỉ này **cross-origin** (khác hostname và port) và được xem là **cross-site** trong cách xác định site thông thường. Hai cổng `localhost:3000` và `localhost:4000` sẽ chỉ khác origin, thường vẫn cùng site, nên không thích hợp để minh họa ngoại lệ cookie Lax cho cross-site top-level navigation.

### 9.1 Lưu `top-level-navigation-lab.mjs`

Chỉ cần Node.js, không cài package. Chạy trong môi trường thử nghiệm do bạn kiểm soát.

~~~js
import { createServer } from 'node:http';

const a = 'http://localhost:3000';
const b = 'http://127.0.0.1:4000';

const pageA = [
  '<!doctype html><html lang="vi"><meta charset="utf-8">',
  '<title>Navigation lab: trang A</title>',
  '<h1>Trang A: localhost:3000</h1>',
  '<p>Trước tiên ghé trang B /setup để tạo cookie.</p>',
  '<p><a href="' + b + '/setup">1. Thiết lập cookie ở B</a></p>',
  '<p><a href="' + b + '/echo">2. Top-level GET tới B</a></p>',
  '<form method="POST" action="' + b + '/echo">',
  '<button>3. Top-level POST tới B</button></form>',
  '<button id="fetch">4. fetch GET tới B</button>',
  '<pre id="output"></pre>',
  '<script>',
  'document.getElementById("fetch").onclick = async () => {',
  '  try {',
  '    const response = await fetch("' + b + '/echo",',
  '      { credentials: "omit" });',
  '    document.getElementById("output").textContent =',
  '      await response.text();',
  '  } catch (error) {',
  '    document.getElementById("output").textContent =',
  '      "Fetch bị chặn đọc response: " + error;',
  '  }',
  '};',
  '</script></html>'
].join('\n');

createServer((req, res) => {
  res.writeHead(200, {
    'Content-Type': 'text/html; charset=utf-8'
  });
  res.end(pageA);
}).listen(3000, () => {
  console.log('A: ' + a);
});

createServer((req, res) => {
  const path = new URL(req.url, b).pathname;

  if (path === '/setup') {
    res.writeHead(200, {
      'Content-Type': 'text/html; charset=utf-8',
      'Set-Cookie': 'demo_session=test; Path=/; HttpOnly; SameSite=Lax'
    });
    return res.end(
      '<meta charset="utf-8"><h1>Đã tạo SameSite=Lax cookie</h1>' +
      '<a href="' + a + '">Quay lại trang A</a>'
    );
  }

  if (path !== '/echo') {
    res.writeHead(404);
    return res.end('Not found');
  }

  const hasCookie = /(?:^|;\s*)demo_session=/.test(
    req.headers.cookie || ''
  );

  console.log({
    method: req.method,
    path,
    cookieReceived: hasCookie,
    origin: req.headers.origin || '(absent)',
    fetchSite: req.headers['sec-fetch-site'] || '(absent)',
    fetchMode: req.headers['sec-fetch-mode'] || '(absent)'
  });

  // Cố ý KHÔNG trả Access-Control-Allow-Origin để quan sát CORS.
  res.writeHead(200, {
    'Content-Type': 'text/html; charset=utf-8'
  });
  res.end(
    '<meta charset="utf-8"><h1>Trang B</h1>' +
    '<p>Method: ' + req.method + '</p>' +
    '<p>Cookie demo_session được gửi: ' + hasCookie + '</p>' +
    '<p><a href="' + a + '">Quay lại A</a></p>'
  );
}).listen(4000, '127.0.0.1', () => {
  console.log('B: ' + b);
});
~~~

Demo đặt `SameSite=Lax` **tường minh**, `HttpOnly` và không dùng `Secure` để phục vụ môi trường HTTP cục bộ. Đây chỉ là cookie thử nghiệm; **session cookie production phải dùng HTTPS và thuộc tính `Secure`**, cùng các phòng vệ phù hợp.

### 9.2 Chạy và quan sát

1. Trong thư mục chứa file, chạy `node top-level-navigation-lab.mjs`.
2. Mở `http://127.0.0.1:4000/setup`; trang B thiết lập cookie và có link quay về A.
3. Nhấp link quay về `http://localhost:3000`. Mở DevTools, chọn **Network**, bật **Preserve log**.
4. Nhấp **Top-level GET tới B**, quan sát request `/echo` cùng cookie; dùng link quay về A.
5. Nhấp **Top-level POST tới B**, quan sát request POST và cookie; dùng link quay về A.
6. Nhấn nút **fetch GET tới B**, quan sát Console, Network và thông báo CORS. Nếu có những request khác do browser tạo, lọc theo `/echo` và method.

**Kết quả dự kiến trong browser hỗ trợ các chính sách thông thường:**

| Hành động từ A | Request đến B | Cookie `demo_session` | Trang A có đọc response bằng JS? |
|---|---|---|---|
| Nhấp link top-level GET | GET `/echo`, mode navigation | Thường **có** do ngoại lệ Lax cho top-level cross-site GET | Không theo cách đọc DOM cross-origin; tab đã điều hướng sang B |
| Gửi form top-level POST | POST `/echo`, mode navigation | Thường **không** gửi cookie Lax | Không; browser hiển thị response như tài liệu của B |
| `fetch` GET với `credentials: "omit"` | GET `/echo`, mode `cors` | Không, vì đã chọn `omit` | **Không**; B không trả header cho CORS |

Tại terminal của Node.js, xem `origin`, `fetchSite`, `fetchMode` của từng request. Một GET navigation bình thường có thể **không có header Origin**; form POST thường có. Fetch cross-origin có thể đã đến server và được trả HTTP 200, nhưng script vẫn báo lỗi vì **không được đọc response theo CORS**.

Để giảm thay đổi hành vi do cache, có thể bật **Disable cache** trong DevTools khi thử nghiệm; một số khác biệt vẫn tùy phiên bản và chính sách riêng tư của browser.

### 9.3 Biến thể cần suy luận

- Đổi cookie thử nghiệm thành `SameSite=Strict`. Dự đoán cookie với top-level GET từ A sang B.
- Đổi hai địa chỉ thành `localhost:3000` và `localhost:4000`. Dự đoán vì sao cùng site ảnh hưởng kết quả SameSite, dù CORS vẫn thấy cross-origin do khác port.
- Nếu thêm header `Access-Control-Allow-Origin: http://localhost:3000` vào response của B, điều gì thay đổi với `fetch` khi `credentials: "omit"`? Việc đó có thay đổi điều hướng link/form không?
- Thử thêm vào trang A một form POST có field ẩn. Giải thích vì sao CORS không phải biện pháp chống CSRF cho form.
- Thử mở B trong tab mới với `target="_blank" rel="noopener"` và kiểm tra `window.opener` ở trang B.
- Khi thử header `Content-Security-Policy: frame-ancestors 'none'` trên B, top-level navigation trực tiếp có bị cấm không? Sau đó thử nhúng B trong iframe A để so sánh.

Thực hành chỉ sử dụng máy chủ và dữ liệu demo của mình; không thử thao tác thay đổi trạng thái trên hệ thống của người khác.

## 10. Chẩn đoán các tình huống thực tế

| Triệu chứng | Nên kiểm tra | Hướng giải quyết |
|---|---|---|
| Link cross-origin mở được nhưng `fetch` báo CORS | Loại thao tác, `Access-Control-Allow-Origin` và credentials mode | Cấu hình CORS đúng ở API nếu cần đọc response; giữ phân quyền ở server |
| Request top-level GET có cookie Lax nhưng POST không có | Site của trang nguồn/đích, `SameSite`, method, target navigation | Thiết kế authentication/CSRF phù hợp, không giả định hai request có cookie như nhau |
| Iframe không thể chuyển tab cha | `sandbox`, top navigation flags, user activation | Chỉ thêm `allow-top-navigation-by-user-activation` nếu nghiệp vụ cần |
| Trang tải trực tiếp được nhưng iframe bị chặn | `frame-ancestors`, `X-Frame-Options`, sandbox | Xác định chính sách nhúng phù hợp; không tắt phòng vệ clickjacking tùy tiện |
| Popup đăng nhập mở nhưng mất liên kết với opener | `noopener`, COOP, popup policy, cross-origin restrictions | Thiết kế callback/handshake đúng và kiểm thử luồng SSO |
| Redirect POST thành GET bất ngờ | Status `301/302/303/307/308` | Dùng mã redirect đúng ý nghĩa; cân nhắc PRG với 303 |
| Người dùng bị chuyển sang trang lạ qua URL thuộc domain mình | Open redirect, tham số `next`/`returnUrl` | Kiểm tra URL đích bằng parser và allowlist |
| Cookie không gửi sau cross-site navigation | SameSite, Secure, host/path, expiration, privacy settings | Đối chiếu từng điều kiện cookie; tránh tự động nới sang `SameSite=None` |
| Đổi URL mà Network không có document request | SPA routing, same-document navigation, cache, bfcache, service worker | Xác định dạng navigation và xem Performance/History |
| Endpoint nhạy cảm bị gọi qua link/form cross-site | GET có tác dụng phụ, thiếu CSRF token, header Origin/Fetch Metadata | Sửa ngữ nghĩa endpoint, xác minh CSRF và yêu cầu quyền server |

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Người dùng ở `https://news.example` nhấp liên kết đến `https://bank.example`. Bank không bật CORS. Browser có được hiển thị trang bank không?

**Đáp án:** Thường có. Top-level navigation không cần CORS để render trang. SOP vẫn ngăn script ở origin cũ đọc DOM bank theo cross-origin.

**Câu 2.** Một cookie session của bank có `SameSite=Lax`. Vì sao top-level GET từ site khác có thể gửi cookie nhưng cross-site form POST thường không?

**Đáp án:** Cookie Lax có ngoại lệ cho một số **top-level navigation dùng phương thức an toàn**, ví dụ GET. POST không thuộc nhóm phương thức an toàn và không được hưởng ngoại lệ Lax tường minh.

**Câu 3.** Có thể dùng CORS để ngăn hoàn toàn CSRF qua form HTML không?

**Đáp án:** Không. Form cross-origin vẫn có thể được trình duyệt gửi để điều hướng mà không cần quyền đọc response bằng JavaScript. Cần CSRF token/biện pháp tương đương, kiểm tra origin khi phù hợp, cookie SameSite và phân quyền ở server.

**Câu 4.** Trang có header `Content-Security-Policy: frame-ancestors 'none'`. Người dùng có thể mở URL trực tiếp trong tab không?

**Đáp án:** Thường có. `frame-ancestors` chặn ngữ cảnh nhúng, không phải một chính sách cấm top-level navigation trực tiếp.

**Câu 5.** Một iframe sandbox thiếu `allow-top-navigation` và `allow-top-navigation-by-user-activation` có thể chắc chắn đổi `window.top.location` không?

**Đáp án:** Không. Sandbox đặt giới hạn top-level navigation. Nếu luồng yêu cầu điều hướng bằng hành động người dùng, cân nhắc `allow-top-navigation-by-user-activation` cùng những điều kiện browser khác.

**Câu 6.** Sau POST, server muốn hiển thị trang kết quả bằng GET để tránh gửi lại biểu mẫu khi reload. Redirect nào phù hợp?

**Đáp án:** Mẫu Post/Redirect/Get thường dùng HTTP **303 See Other** để chuyển sang GET của trang kết quả. Vẫn phải bảo vệ POST trước CSRF và kiểm tra quyền.

**Câu 7.** Browser mở tab mới có quan hệ `window.opener` với trang ban đầu. Vì sao cần chú ý khi mở site ngoài?

**Đáp án:** Trang ngoài có thể giữ một số quyền tác động tới cửa sổ mở nó dù không đọc được DOM cross-origin. Dùng `noopener`/`noreferrer` phù hợp; COOP có thể bổ sung cách ly theo chính sách của từng trang.

**Câu 8.** Script gọi `history.pushState({}, '', '/orders')`. Có phải browser thực hiện top-level network request đến `/orders` không?

**Đáp án:** Không tự động. `pushState` thay URL và history trong tài liệu hiện tại theo các ràng buộc cùng origin; ứng dụng có thể chủ động dùng fetch để tải dữ liệu, nhưng đó là thao tác khác.

**Câu 9.** Header `Sec-Fetch-User: ?1` có thể thay thế xác thực và CSRF token không?

**Đáp án:** Không. Nó cung cấp tín hiệu user activation cho những navigation phù hợp, không chứng minh danh tính hay tính hợp lệ của thao tác. Phải kết hợp xác thực, phân quyền và phòng vệ CSRF tại server.

**Câu 10.** Trang A và API B ở hai cổng khác nhau trên cùng hostname HTTPS. Chúng có thể cross-origin nhưng same-site không?

**Đáp án:** Có. Port thuộc tuple origin nhưng thường không quyết định site; do đó CORS và SameSite có thể cho kết quả khác nhau.

## 12. Checklist thiết kế điều hướng an toàn

Trước khi triển khai navigation trong ứng dụng web, nên kiểm tra:

1. **Nguồn điều hướng và đích:** URL đích có do người dùng kiểm soát không? Có nguy cơ open redirect hoặc chuyển người dùng sang site lừa đảo không?
2. **Loại request:** Đây là link/form navigation, fetch/XHR, iframe hay SPA route? Kết quả CORS/SOP và việc thay tài liệu rất khác nhau.
3. **Cookie và phiên:** So sánh origin lẫn site; đánh giá method, SameSite, Secure, HttpOnly, third-party cookie và partitioning nếu liên quan.
4. **Thao tác thay đổi trạng thái:** Không làm bằng GET; kiểm tra CSRF, Origin/Referer khi phù hợp, Fetch Metadata, authentication và authorization.
5. **Iframe:** Hạn chế sandbox; chỉ cấp top navigation theo nhu cầu, dùng `frame-ancestors`/`X-Frame-Options` bảo vệ trang khỏi bị nhúng trái phép.
6. **Popup/opener:** Dùng `noopener` cho link ngoài; kiểm tra COOP và giao tiếp an toàn nếu cần mở cửa sổ đăng nhập.
7. **Redirect và dữ liệu nhạy cảm:** Kiểm tra `Location`, status, tham số URL, HSTS/HTTPS và Referrer-Policy.
8. **Thử nghiệm:** Dùng Network + Preserve log, Console và các trường Cookie/Headers/Initiator trong DevTools để biết request có được gửi, cookie nào đi kèm, response có được đọc và tài liệu nào cuối cùng được hiển thị.

**Ghi nhớ:** Top-level navigation là hoạt động thay tài liệu ở cấp tab/cửa sổ. Trình duyệt có thể điều hướng cross-origin mà không cần CORS, còn JavaScript vẫn chịu SOP khi muốn đọc dữ liệu giữa các origin. Để bảo vệ ứng dụng, cần nhìn riêng **quyền điều hướng**, **cookie/CSRF**, **quyền đọc response**, **quyền nhúng** và **quan hệ opener**.

## Tài liệu tham khảo

- [WHATWG HTML — Navigation](https://html.spec.whatwg.org/multipage/browsing-the-web.html)
- [MDN — Same-origin policy](https://developer.mozilla.org/en-US/docs/Web/Security/Same-origin_policy)
- [MDN — Set-Cookie: SameSite](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie)
- [MDN — Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)
- [MDN — iframe sandbox](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/iframe)
- [MDN — Cross-Origin-Opener-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cross-Origin-Opener-Policy)
- [MDN — Fetch Metadata request headers](https://developer.mozilla.org/en-US/docs/Glossary/Fetch_metadata_request_header)

