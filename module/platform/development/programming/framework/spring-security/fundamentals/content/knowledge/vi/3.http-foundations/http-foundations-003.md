# Cookie, phiên làm việc và cách trình duyệt tự gửi dữ liệu

Khi đăng nhập vào một trang web, bạn thường chỉ nhập tài khoản và mật khẩu **một lần**. Sau đó, bạn mở trang hồ sơ, chuyển sang trang danh sách và gửi biểu mẫu mà không phải nhập lại mật khẩu ở mỗi request. Điều này dễ khiến người mới học nghĩ rằng HTTP “nhớ” người đang đăng nhập. Thực tế, **mỗi HTTP request độc lập về mặt giao thức**; ứng dụng phải có cơ chế để nhận ra mối liên hệ giữa các request.

Hai cơ chế cần hiểu đầu tiên là **cookie** và **phiên làm việc (session)**:

- **Cookie** là một mẩu dữ liệu được trình duyệt lưu theo quy tắc HTTP, thường được máy chủ gửi qua header `Set-Cookie`. Khi yêu cầu tiếp theo phù hợp phạm vi của cookie, trình duyệt có thể **tự đưa** nó vào header `Cookie`.
- **Session** là trạng thái ứng dụng gắn với một lần tương tác, thường được giữ ở phía máy chủ. Trong ứng dụng servlet, session có thể được nhận diện bằng một mã ngẫu nhiên lưu trong cookie, phổ biến là `JSESSIONID`.
- **Spring Security** có thể dùng session để lưu và khôi phục thông tin xác thực (`SecurityContext` chứa `Authentication`) trong các request sau. Nhưng có cookie hay có session **không mặc nhiên** chứng minh rằng người dùng đã xác thực hợp lệ.

Từ đây xuất hiện một hệ quả bảo mật: vì trình duyệt tự gửi cookie, một request mà người dùng không chủ ý cũng có thể mang cookie đăng nhập. Đây là nguyên nhân nền tảng để hiểu **CSRF (Cross-Site Request Forgery)** và các thuộc tính bảo vệ cookie.

## 1. Vì sao HTTP cần cơ chế duy trì ngữ cảnh?

Ví dụ, Mai đăng nhập rồi yêu cầu hai tài nguyên:

~~~http
POST /login HTTP/1.1
Host: learning.example
Content-Type: application/x-www-form-urlencoded

username=mai&password=********
~~~

~~~http
GET /account HTTP/1.1
Host: learning.example
~~~

Request `GET /account` tự thân không mang một trí nhớ rằng `POST /login` trước đó đã thành công. Máy chủ không nên yêu cầu gửi lại mật khẩu ở mọi request. Thay vào đó, cơ chế có trạng thái thường vận hành như sau:

1. Máy chủ xác thực thông tin đăng nhập.
2. Máy chủ tạo hoặc dùng một session thích hợp, gắn kết quả xác thực với session đó.
3. Máy chủ gửi cho trình duyệt một **mã nhận diện session** (session ID) bằng cookie.
4. Trình duyệt lưu cookie và tự đính kèm cookie vào những request sau phù hợp phạm vi.
5. Máy chủ đọc session ID, tìm session tương ứng và khôi phục thông tin cần thiết.
6. Khi truy cập tài nguyên, Spring Security tiếp tục áp dụng quy tắc phân quyền.

Sơ đồ minh họa phiên servlet dùng cookie:

~~~text
TRÌNH DUYỆT                                      MÁY CHỦ
    |                                                 |
    | POST /login (tài khoản, mật khẩu)                |
    |------------------------------------------------>|
    |                                    Xác thực thành công
    |                                    Tạo/đổi session ID
    |                                    Lưu SecurityContext
    |<------------------------------------------------|
    | HTTP 302 + Set-Cookie: JSESSIONID=<mã-ngẫu-nhiên>|
    |                                                 |
    | (cookie được lưu trong kho của trình duyệt)      |
    |                                                 |
    | GET /account                                     |
    | Cookie: JSESSIONID=<mã-ngẫu-nhiên>               |
    |------------------------------------------------>|
    |                                    Tìm session
    |                                    Khôi phục Authentication
    |                                    Kiểm tra phân quyền
    |<------------------------------------------------|
    | 200 OK hoặc phản hồi từ chối phù hợp             |
~~~

Đây là luồng điển hình, không phải tất cả triển khai đều bắt buộc dùng session. Một API xác thực bằng bearer token trong header `Authorization` có thể không dùng cookie để duy trì trạng thái. Phải quan sát đúng cơ chế mà ứng dụng chọn.

## 2. Cookie thực sự đi qua HTTP như thế nào?

Máy chủ có thể trả một response như sau:

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain
Set-Cookie: DEMO_SESSION=opaque-random-id; Path=/; Secure; HttpOnly; SameSite=Lax

Login successful
~~~

Dòng `Set-Cookie` bảo trình duyệt lưu một cookie tên `DEMO_SESSION`, giá trị `opaque-random-id`, kèm các quy tắc phạm vi và an toàn. Giá trị này chỉ là minh họa; mã session thực tế phải khó đoán, được tạo bằng nguồn ngẫu nhiên bảo mật. **Máy chủ không nên gửi mật khẩu trong cookie.**

Ở request sau phù hợp, trình duyệt có thể tự gửi:

~~~http
GET /account HTTP/1.1
Host: learning.example
Cookie: DEMO_SESSION=opaque-random-id
~~~

Những điểm cần nhìn kỹ:

- **`Set-Cookie`** là header **response** do máy chủ gửi để thiết lập/cập nhật cookie.
- **`Cookie`** là header **request** mang các cặp `tên=giá trị` mà trình duyệt quyết định gửi.
- Header `Cookie` thông thường chỉ mang cặp tên/giá trị; những thuộc tính như `HttpOnly`, `Secure`, `SameSite` và `Path` được dùng để quyết định cách lưu/gửi cookie, **không được lặp lại** như thuộc tính trong request.
- Trình duyệt có thể giữ nhiều cookie và gửi các cặp tên/giá trị phù hợp trong cùng một header. Tên cookie không phải danh tính người dùng; giá trị của cookie cũng không mặc nhiên đã được xác thực.
- Khi trình duyệt nhận nhiều response `Set-Cookie`, việc lưu, cập nhật hoặc loại bỏ cookie phụ thuộc vào tên, phạm vi, thuộc tính và chính sách bảo mật của trình duyệt.

Đừng nhầm cookie với một trường trong JSON response hoặc `localStorage`: cookie có cơ chế HTTP riêng và có thể được trình duyệt tự gửi; dữ liệu trong `localStorage` không được gắn tự động vào mọi request.

### Cookie có được gửi đến mọi website không?

**Không.** Trình duyệt áp dụng quy tắc của từng cookie và ngữ cảnh request: host/domain, đường dẫn, giao thức HTTPS khi có `Secure`, `SameSite`, chính sách cookie của trình duyệt và chế độ yêu cầu có mang credentials hay không.

Ví dụ nếu cookie đặt tại `https://app.example.com` với `Path=/account` thì nó có thể đi theo request đến `/account` và `/account/settings`; nó không tự đi theo request đến `/public`. Tuy nhiên, `Path` **không tạo ranh giới bảo mật mạnh** giữa các phần của cùng một website: không dựa vào `Path` để cô lập bí mật khỏi mã độc hoặc người dùng có quyền trên cùng host.

## 3. Session và cookie là hai lớp khác nhau

Có thể hình dung cookie là **tấm vé chứa mã tra cứu**, còn session là **bản ghi trạng thái** mà máy chủ quản lý.

| Đặc điểm | Cookie | Session ở máy chủ |
| --- | --- | --- |
| Nơi lưu | Trong kho cookie của trình duyệt (có thể là bộ nhớ hoặc lưu bền) | Bộ nhớ máy chủ, kho session dùng chung, cơ sở dữ liệu hoặc nơi lưu do ứng dụng chọn |
| Dữ liệu thường có | ID ngẫu nhiên, tùy chọn giao diện, giá trị trạng thái nhỏ | Thông tin gắn với phiên đăng nhập hoặc dữ liệu ứng dụng |
| Cách gửi | Browser có thể tự thêm `Cookie` vào request | Không tự chuyển nguyên session sang browser; server tra cứu theo mã phù hợp |
| Vai trò đối với đăng nhập | Có thể chuyên chở mã định danh session | Có thể giữ `SecurityContext` và trạng thái đăng nhập |
| Cách hết hạn | Quy tắc cookie và chính sách browser | Timeout/invalidation do server quyết định, có thể độc lập với cookie |

Ví dụ dữ liệu server giữ:

~~~text
Session store (chỉ ở máy chủ):
  key:   <mã-ngẫu-nhiên-123>
  value: { userId: "mai", SecurityContext: ..., expiresAt: ... }

Browser cookie store:
  DEMO_SESSION=<mã-ngẫu-nhiên-123>
~~~

Browser **không cần giữ toàn bộ** đối tượng `Authentication` hay quyền truy cập ở cookie session. Máy chủ lấy session ID rồi tra dữ liệu và ra quyết định bảo mật. Cookie phiên thường chỉ mang mã nhận diện; nếu ai đó đánh cắp một session ID còn hiệu lực, họ có thể tìm cách sử dụng phiên đó. Vì vậy **session ID là bí mật cần bảo vệ**, dù bản thân nó không chứa mật khẩu.

Một số hệ thống dùng cookie chứa dữ liệu đã ký/mã hóa thay vì tra trạng thái server; không phải cookie nào cũng là session ID. Cần phân biệt chính xác thiết kế của hệ thống đang xét.

### “Session cookie” và “server session” không đồng nghĩa

Cookie **không có `Max-Age`/`Expires`** thường được gọi là *session cookie* theo nghĩa vòng đời lưu trữ của trình duyệt. Trong khi đó, `HttpSession` là một đối tượng trạng thái phía máy chủ, có quy tắc hết hạn độc lập.

Hệ quả:

- Cookie vẫn có thể còn trong trình duyệt nhưng session phía máy chủ đã hết hạn: request có gửi mã cũ vẫn không còn phiên hợp lệ.
- Máy chủ có thể hủy session khi đăng xuất nhưng trình duyệt chưa xóa cookie cũ; mã cũ vẫn không được phép cấp quyền.
- Trình duyệt có thể xóa cookie nhưng server session chưa hết hạn: client không còn mã để tham chiếu đúng session đó.
- Một số trình duyệt có chức năng khôi phục phiên và có thể giữ lại session cookie qua lần đóng/mở. Đừng coi đóng tab/trình duyệt là cơ chế đăng xuất an toàn duy nhất.

## 4. Thuộc tính cookie quyết định phạm vi và mức bảo vệ

| Thuộc tính | Tác dụng chính | Lưu ý |
| --- | --- | --- |
| `Domain` | Xác định phạm vi host/domain được gửi cookie | Không có `Domain` thường là **host-only**: chỉ host đã thiết lập, không tự mở rộng sang subdomain |
| `Path` | Chỉ gửi khi đường dẫn request khớp phạm vi đã đặt | `Path=/` bao phủ toàn website; **không phải** cơ chế phân quyền |
| `Secure` | Giới hạn gửi cookie qua kết nối bảo mật, thông thường HTTPS | Cần dùng cho cookie session trong production HTTPS; không tự ngăn mọi truy cập nội bộ ứng dụng |
| `HttpOnly` | JavaScript qua `document.cookie` không đọc/ghi được cookie này | Browser **vẫn gửi cookie trong HTTP request**, kể cả request do script kích hoạt nếu các điều kiện gửi được đáp ứng |
| `SameSite=Strict` | Giới hạn cookie trong ngữ cảnh same-site | Có thể ảnh hưởng điều hướng đến website từ trang khác |
| `SameSite=Lax` | Hạn chế nhiều request cross-site, vẫn cho một số điều hướng cấp cao an toàn như GET | Không thay thế token CSRF và không phải ranh giới phân quyền |
| `SameSite=None` | Cho phép cookie ở ngữ cảnh cross-site theo chính sách browser | Cần `Secure`; trình duyệt/chính sách chặn third-party cookies vẫn có thể hạn chế |
| `Max-Age` | Thời gian sống của cookie tính bằng giây | `Max-Age=0` có thể dùng xóa cookie với phạm vi khớp |
| `Expires` | Thời điểm hết hạn tuyệt đối | Khi có cả hai, `Max-Age` thường được ưu tiên |
| Prefix `__Host-` | Yêu cầu `Secure`, `Path=/`, không có `Domain` trong trình duyệt hỗ trợ | Giúp hạn chế cookie bị thiết lập từ subdomain; chỉ dùng khi hợp lệ trên HTTPS |

**Host-only và Domain:** nếu `app.example.com` thiết lập cookie không có `Domain`, cookie thường chỉ gửi về `app.example.com`. Nếu server có quyền thiết lập `Domain=example.com`, cookie cũng có thể được gửi tới các subdomain phù hợp, làm tăng phạm vi tiếp xúc. Chỉ mở rộng domain khi thật sự cần.

**Secure không đồng nghĩa đã mã hóa giá trị cookie ở lúc lưu.** Nó chủ yếu hạn chế cookie được truyền trên HTTP không bảo mật. Đường truyền HTTPS và khả năng bảo vệ thiết bị/browser vẫn là những yếu tố riêng.

**HttpOnly không làm cookie “ngừng hoạt động”.** Nó hạn chế truy cập bằng API JavaScript như `document.cookie`; browser vẫn có thể tự gửi cookie trong request. HttpOnly giúp giảm nguy cơ đánh cắp cookie qua một số kiểu XSS, nhưng XSS vẫn có thể gửi request trong ngữ cảnh người dùng và thực hiện hành động nếu ứng dụng có lỗ hổng.

**SameSite là quan hệ giữa các “site”, không hệt với origin.** Origin xét bộ ba **scheme + host + port**, còn same-site dựa trên scheme và domain đăng ký (registrable domain) tương ứng. Hai subdomain có thể khác origin nhưng vẫn cùng site. Vì vậy chỉ dùng `SameSite` không đủ để chống mọi tình huống từ subdomain không đáng tin.

Ví dụ cookie session cho website HTTPS:

~~~http
Set-Cookie: __Host-SESSION=some-unpredictable-id; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Giá trị session thật phải khó đoán, được bảo vệ và luân chuyển/hủy đúng lúc. Tên prefix `__Host-` là tùy chọn nâng cao; hệ thống servlet mặc định có thể dùng tên `JSESSIONID`, không cần ép thay tên nếu chưa thiết kế tương ứng.

## 5. “Trình duyệt tự gửi” nghĩa là gì trong các cách tạo request?

Một lập trình viên không phải viết lệnh thủ công “thêm cookie session” cho từng link cùng website. Khi người dùng nhấp link, tải trang, gửi form hoặc một đoạn script gọi API, **trình duyệt quyết định cookie nào được đính kèm** dựa trên phạm vi và ngữ cảnh.

| Cách tạo request | Hành vi thường gặp |
| --- | --- |
| Nhấn liên kết `<a>` đến cùng site | Browser điều hướng và đính kèm cookie phù hợp |
| Gửi HTML form | Browser tự gửi cookie phù hợp; đây là điểm liên quan trực tiếp đến CSRF |
| Tải ảnh, stylesheet hoặc script | Có thể gửi cookie đến đích nếu quy tắc cookie và bảo vệ third-party cho phép |
| JavaScript `fetch("/api/account")` cùng origin | Mặc định `credentials: "same-origin"`; cookie phù hợp thường được gửi |
| JavaScript fetch tới **khác origin** | Cần xét `credentials: "include"`, CORS của server và quy tắc `SameSite`/third-party cookies; `include` không thể vượt mọi chính sách cookie |
| API client không phải browser, chẳng hạn curl | Không tự có kho cookie trình duyệt; phải quản lý cookie jar/header theo cách client hỗ trợ |

Phân biệt **same-site** và **same-origin** rất quan trọng khi một frontend đặt ở `https://app.example.com` gọi API `https://api.example.com`: hai host khác origin dù có thể cùng site; `fetch` mặc định không gửi credentials cross-origin. Nếu cần cookie, frontend phải cấu hình đúng `credentials`; API phải trả CORS phù hợp (không dùng `Access-Control-Allow-Origin: *` cùng credentials), và cookie vẫn phải phù hợp `Domain`, `Path`, `Secure`, `SameSite`.

CORS chủ yếu quyết định việc JavaScript từ origin khác được **đọc** response và loại request nào được phép đi tiếp qua cơ chế preflight; **CORS không phải cơ chế thay thế bảo vệ CSRF**. Trình duyệt vẫn có thể gửi form hoặc điều hướng mà mã JavaScript ở trang khác không cần đọc response.

### Cookie và Authorization header là hai cách mang thông tin khác nhau

- Với ứng dụng dùng **session cookie**, trình duyệt thường tự gắn cookie vào request phù hợp.
- Với API nhận **bearer token trong `Authorization: Bearer ...`**, ứng dụng client thường phải chủ động gắn header hoặc dùng công cụ HTTP client có cơ chế hỗ trợ. Token lưu trong memory hoặc `localStorage` không tự biến thành `Cookie`.
- Có thể có hệ thống dùng bearer token **đặt trong cookie**; khi đó browser lại tự gửi theo luật cookie và cần đánh giá CSRF tương ứng. Đừng suy ra toàn bộ rủi ro chỉ từ tên “JWT” hoặc “stateless”.

## 6. Cookie được gửi tự động dẫn tới rủi ro CSRF ra sao?

Giả sử một người đang đăng nhập trang ngân hàng. Website độc hại có thể khiến browser của người đó tạo request đến ngân hàng, ví dụ bằng form. Nếu cookie phiên được đính kèm và ngân hàng chỉ kiểm tra “đã đăng nhập”, thao tác thay đổi dữ liệu có thể bị thực hiện ngoài ý muốn.

Sơ đồ đe dọa:

~~~text
[1] Người dùng đăng nhập ngân hàng
    Browser lưu cookie phiên hợp lệ
                  |
[2] Người dùng mở website không đáng tin
    Website đó kích hoạt request đến ngân hàng
                  |
[3] Browser có thể tự gửi cookie ngân hàng
    (tùy SameSite, ngữ cảnh, chính sách browser)
                  |
[4] Nếu server chỉ nhìn cookie đăng nhập
    và không có biện pháp chống CSRF phù hợp
                  |
              RỦI RO CSRF
~~~

Điểm mấu chốt: **server nhận cookie hợp lệ chưa chắc request do người dùng chủ ý tạo**. Máy chủ cần tách bạch xác thực với kiểm soát nguồn gốc/ý định của thao tác có tác dụng phụ.

Các lớp bảo vệ phù hợp gồm:

1. **CSRF token** ràng buộc với ngữ cảnh cần thiết và được server xác minh với request thay đổi trạng thái. Trang độc hại không nên có khả năng tự tạo token hợp lệ.
2. **`SameSite=Lax` hoặc `Strict`** cho cookie session khi phù hợp nghiệp vụ. Đây là hàng rào bổ sung, có giới hạn và khác nhau theo ngữ cảnh/browser.
3. **GET/HEAD/OPTIONS/TRACE phải được thiết kế là thao tác an toàn theo ngữ nghĩa HTTP**: không dùng GET để xóa/chuyển tiền; thiết kế endpoint thay đổi trạng thái bằng phương thức phù hợp.
4. **Kiểm tra Origin/Referer hoặc Fetch Metadata** ở những trường hợp phù hợp, như một phần của chiến lược phòng thủ nhiều lớp.
5. **Không bật CORS credentials rộng rãi** cho origin không tin cậy; CORS vẫn không thay thế CSRF token cho website dùng cookie để xác thực.

Spring Security cung cấp hỗ trợ CSRF cho ứng dụng servlet. Với ứng dụng web đăng nhập dựa trên phiên/cookie, **không nên vô hiệu hóa CSRF chỉ để form POST chạy qua**. Cần tìm cách đưa token hợp lệ vào form/header và cấu hình cơ chế phù hợp. Với API stateless sử dụng header `Authorization` do client chủ động gửi, đánh giá rủi ro có thể khác; nhưng nếu trình duyệt tự động đính kèm cookie thì rủi ro CSRF vẫn cần được xem xét.

### HttpOnly không thay cho CSRF token

Một cookie `HttpOnly` có thể bị chặn đọc từ JavaScript, nhưng trình duyệt vẫn có thể gắn cookie đó vào request. Vì vậy ngay cả khi script ở trang độc hại **không biết chuỗi session ID**, nó vẫn có thể tìm cách tạo request mà browser đính kèm cookie theo quy tắc.

Một số ứng dụng SPA sử dụng **cookie khác để truyền CSRF token** đến JavaScript. Cookie CSRF token và cookie session đăng nhập có vai trò khác nhau; không vì JavaScript cần đọc CSRF token mà biến cookie session nhạy cảm thành cookie JavaScript có thể đọc.

## 7. Session còn những rủi ro nào?

**Session hijacking (chiếm phiên):** ai đó lấy được mã session còn hợp lệ có thể giả mạo phiên của người dùng. Cần HTTPS, `Secure`, `HttpOnly`, phạm vi cookie hẹp, bảo vệ trước XSS, không ghi mã vào log, hủy phiên khi cần và giới hạn vòng đời.

**Session fixation (cố định phiên):** kẻ tấn công cố tạo/áp đặt một session ID trước khi nạn nhân đăng nhập, rồi chờ phiên đó được nâng quyền. Sau khi đăng nhập thành công, ứng dụng nên thay đổi session ID. Spring Security servlet có cơ chế bảo vệ session fixation khi dùng luồng xác thực phù hợp; với Servlet 3.1+ thường dùng `changeSessionId`. Không tự viết luồng đăng nhập rồi bỏ qua bước này.

**Session timeout:** session có thể hết hạn dù browser còn cookie. API cần xử lý request chưa còn Authentication hợp lệ như một yêu cầu cần xác thực lại, thay vì tự tin tưởng mã cookie cũ.

**Đăng xuất:** cần làm vô hiệu session hoặc xóa trạng thái xác thực theo cách cơ chế login đang dùng yêu cầu; có thể yêu cầu browser xóa cookie với đúng tên/phạm vi. Chỉ xóa giao diện đăng nhập hoặc một biến JavaScript không đủ để hủy session phía server.

**Đa thiết bị/đa tab:** nhiều tab cùng origin thường chia sẻ cookie jar; đăng nhập/đăng xuất ở một tab có thể làm ảnh hưởng request ở tab khác. Hai thiết bị thường có session riêng; chính sách có cho phép nhiều phiên đăng nhập đồng thời hay không là quyết định của ứng dụng.

**Đổi quyền trong lúc phiên còn sống:** một session cũ có thể giữ `Authentication`/authorities từ lúc đăng nhập. Nếu quyền bị thu hồi, hệ thống phải thiết kế cơ chế cập nhật quyền hoặc hủy/kiểm tra lại phiên khi cần. Cookie tự được gửi không bảo đảm quyền hiện tại còn đúng.

## 8. Ví dụ Java 17+: kho cookie tự quyết định gửi cookie nào

Java có `java.net.CookieManager`, giúp mô phỏng một **kho cookie** của HTTP client. Ví dụ sau không tạo tài khoản, không lưu session thật, không mô phỏng mọi quy tắc trình duyệt hiện đại (đặc biệt là SameSite và chặn third-party cookies). Nó chỉ cho thấy một cookie được nhận từ `Set-Cookie` và có thể xuất hiện tự động trong header `Cookie` khi request đến URL phù hợp.

Tạo tệp `CookieJarDemo.java`:

~~~java
import java.io.IOException;
import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.URI;
import java.util.List;
import java.util.Map;

public class CookieJarDemo {

    private static boolean includesSession(
            CookieManager jar, URI target) throws IOException {
        Map<String, List<String>> headers = jar.get(target, Map.of());
        return headers.getOrDefault("Cookie", List.of())
                .stream()
                .anyMatch(value -> value.contains("DEMO_SESSION="));
    }

    public static void main(String[] args) throws IOException {
        CookieManager browserLikeJar = new CookieManager(
                null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);

        URI login = URI.create("https://app.example.test/login");
        URI account = URI.create("https://app.example.test/account");
        URI otherSite = URI.create("https://different.test/account");

        System.out.println("Before login: "
                + includesSession(browserLikeJar, account));

        browserLikeJar.put(login, Map.of(
                "Set-Cookie",
                List.of("DEMO_SESSION=opaque-demo-value; "
                        + "Path=/; Secure; HttpOnly; SameSite=Lax")));

        System.out.println("After login, same host: "
                + includesSession(browserLikeJar, account));
        System.out.println("Unrelated host: "
                + includesSession(browserLikeJar, otherSite));
        System.out.println("Cookie count: "
                + browserLikeJar.getCookieStore().getCookies().size());
    }
}
~~~

Chạy bằng JDK 17 trở lên, không cần thư viện ngoài hoặc kết nối Internet:

~~~bash
javac CookieJarDemo.java
java CookieJarDemo
~~~

Kết quả mong đợi:

~~~text
Before login: false
After login, same host: true
Unrelated host: false
Cookie count: 1
~~~

Giải thích theo từng dòng:

1. Ban đầu kho cookie trống nên request đến `/account` không có `DEMO_SESSION`.
2. `put` giả lập việc nhận response chứa `Set-Cookie`; sau đó kho cookie chọn cookie để gửi đến cùng host qua HTTPS.
3. Request đến host không liên quan không nhận cookie của `app.example.test`.
4. Bộ nhớ `CookieManager` có một cookie; ví dụ **không cần in giá trị bí mật**.

Đừng nhầm ví dụ này với cơ chế xác thực thật. Máy chủ production phải tạo ID bằng nguồn ngẫu nhiên bảo mật, tra cứu session hợp lệ và thực hiện kiểm tra phân quyền. `CookieManager` của JDK không phải trình duyệt: nó không dùng để kết luận chính xác về CORS, SameSite hoặc cơ chế hạn chế cookie bên thứ ba.

## 9. Cookie và session trong Spring Security servlet

Đối với ứng dụng Spring Boot servlet có form login/session, luồng khái niệm thường là:

~~~text
Browser
  -> Cookie: JSESSIONID=...
Servlet container
  -> tra cứu HttpSession theo mã hợp lệ
Spring Security
  -> SecurityContextRepository nạp SecurityContext khi cần
  -> Authentication được dùng để xử lý request hiện tại
  -> authorization quyết định cho/từ chối truy cập
~~~

Những lớp/hợp đồng thường gặp:

- **`HttpSession`**: khái niệm phiên phía servlet container; có thể lưu các thuộc tính qua nhiều request.
- **`SecurityContext`**: chứa `Authentication` đang được dùng để đưa ra quyết định bảo mật.
- **`SecurityContextHolder`**: truy cập ngữ cảnh bảo mật hiện tại trong luồng servlet thích hợp.
- **`SecurityContextRepository`**, ví dụ `HttpSessionSecurityContextRepository`: cơ chế lưu/đọc ngữ cảnh xác thực giữa các request.
- **`JSESSIONID`**: tên cookie phổ biến dùng để chuyên chở session ID; tên và cách tracking session có thể được cấu hình.

Spring Security 6 có quy tắc **lưu SecurityContext rõ ràng** khi mã tùy biến tự xác thực, chẳng hạn trong một custom filter/controller. Nếu bạn tự tạo kết quả xác thực và chỉ đặt vào `SecurityContextHolder`, không mặc nhiên bảo đảm nó tồn tại ở request sau; cần lưu qua `SecurityContextRepository` đúng cách. Với các cơ chế login Spring Security tích hợp, framework xử lý quá trình xác thực và lưu ngữ cảnh theo cơ chế đã được cấu hình.

Một cấu hình `SecurityFilterChain` servlet tối giản có thể như sau (đây là ví dụ ứng dụng Spring Security, không phải chương trình Java độc lập):

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class WebSecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        // Không disable CSRF cho ứng dụng form login dùng session.
        return http.build();
    }
}
~~~

Đoạn này minh họa ranh giới: mọi URL ngoài `/public/**` đều yêu cầu xác thực, việc duy trì kết quả xác thực giữa request phụ thuộc cơ chế login/session được cấu hình, và CSRF vẫn được Spring Security bật theo mặc định. Để chạy một ứng dụng thật, còn cần dependency Spring Security, cấu hình user hoặc provider, cấu trúc Spring Boot và xử lý endpoint phù hợp.

Trong Spring Boot servlet, ví dụ cấu hình **cookie session trong môi trường HTTPS production** (không áp dụng nguyên xi lên local HTTP nếu `Secure=true` làm browser không gửi cookie) là:

~~~properties
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=lax
server.servlet.session.timeout=30m
~~~

Các thuộc tính cookie do servlet container/Spring Boot cấu hình; Spring Security không trực tiếp đặt mọi thuộc tính trên header session cookie. Khi triển khai sau reverse proxy hoặc TLS termination, cần cấu hình proxy/forwarded headers đáng tin cậy để ứng dụng nhận biết môi trường HTTPS phù hợp.

**`SessionCreationPolicy.STATELESS`** có thể được cấu hình cho luồng xác thực không lưu SecurityContext trong session. Nhưng nó không tự tắt mọi cookie hoặc cấm mọi thành phần ứng dụng tạo `HttpSession`; luôn kiểm tra cơ chế xác thực, CSRF và behavior của các bộ lọc/thư viện khác. Đừng nhầm `stateless` với “trình duyệt không thể gửi cookie”.

## 10. Một chuỗi request để tự phân tích

Giả sử website dùng `HttpSession` và cookie `JSESSIONID`:

| Thời điểm | Browser làm gì? | Server cần làm gì? |
| --- | --- | --- |
| Trước đăng nhập | Không có cookie session hợp lệ | Chưa có Authentication phù hợp thì yêu cầu xác thực |
| Sau đăng nhập | Nhận `Set-Cookie` và lưu mã session | Tạo/luân chuyển session ID và lưu trạng thái xác thực hợp lệ |
| Mở trang mới cùng website | Tự gửi cookie nếu URL và ngữ cảnh phù hợp | Tìm session, đọc SecurityContext và kiểm tra quyền |
| Session hết hạn | Có thể vẫn gửi cookie cũ | Không coi mã hết hạn là phiên hợp lệ |
| Đăng xuất | Có thể được yêu cầu xóa cookie | Vô hiệu session/xóa ngữ cảnh theo cơ chế login |
| Mở liên kết từ website khác | Có thể gửi hoặc không gửi cookie tùy SameSite | Không dùng riêng sự có mặt của cookie để xác nhận ý định thực hiện thay đổi |
| Gọi API sang origin khác | `fetch` cần xét credentials, CORS và chính sách cookie | Chỉ trả response có credentials cho origin được phép và vẫn thực thi xác thực, phân quyền, CSRF phù hợp |

Phép thử tư duy: người dùng đăng nhập thành công, browser gửi `JSESSIONID` ở request sau, nhưng session server đã bị xóa. **Cookie vẫn có thể xuất hiện trong request, nhưng server không tìm được session xác thực hợp lệ**, nên không thể coi người dùng còn đăng nhập. Ngược lại, server có session hợp lệ nhưng browser không gửi đúng cookie thì không thể tự suy ra phiên nào thuộc request đó.

## 11. Sai lầm phổ biến và cách tránh

1. **“HTTP có session sẵn vì browser nhớ người dùng.”** HTTP không tự nhớ các request; cookie/session là cơ chế bổ sung.
2. **“Cookie và session là một.”** Cookie lưu ở client; session phía server là trạng thái có thể được nhận diện bằng cookie.
3. **“`JSESSIONID` chứa toàn bộ tài khoản và quyền.”** Thường chỉ chứa ID dùng để tra phiên; trạng thái xác thực nằm trong ngữ cảnh phía server.
4. **“Có header `Cookie` nghĩa là đã login.”** Cookie có thể không hợp lệ, hết hạn, thuộc chức năng không liên quan hoặc không ánh xạ tới Authentication tin cậy.
5. **“`HttpOnly` sẽ làm browser không gửi cookie.”** Sai: nó hạn chế JavaScript đọc/ghi, còn browser vẫn tự gửi theo quy tắc.
6. **“`Secure` ngăn mọi tấn công cookie.”** Sai: còn cần HTTPS đúng cấu hình, giảm phạm vi, chống XSS, CSRF và bảo vệ session ID.
7. **“`SameSite=Lax` loại bỏ mọi CSRF.”** Sai: đây là một lớp phòng thủ; website vẫn cần chiến lược chống CSRF phù hợp.
8. **“CORS cho phép/không cho phép đăng nhập thay cho CSRF.”** Sai: CORS và CSRF xử lý các ranh giới khác nhau.
9. **“GET đổi dữ liệu là bình thường vì người dùng đã login.”** Không an toàn: điều hướng GET có thể được kích hoạt từ nguồn khác; thao tác an toàn không nên làm thay đổi trạng thái nghiệp vụ.
10. **“Dùng JWT thay session là hết CSRF.”** Không đúng nếu JWT vẫn nằm trong cookie tự được gửi; cần xét cơ chế chuyên chở và điều kiện request.
11. **“Đóng trình duyệt luôn hủy phiên trên server.”** Không chắc; vòng đời cookie và `HttpSession` là hai lớp riêng.
12. **“Chỉ cần xóa cookie ở client là đã vô hiệu session.”** Với session server, vẫn cần hủy phiên hoặc trạng thái xác thực phù hợp.

## 12. Câu hỏi tự kiểm tra

**1. Vì sao người dùng thường không cần gửi lại mật khẩu ở mỗi request sau khi đăng nhập?**  
Vì trình duyệt có thể gửi lại cookie chứa mã session và server dùng mã này để tra trạng thái xác thực đã lưu. Một request vẫn phải được xác minh theo cơ chế ứng dụng, không tự kế thừa trí nhớ từ HTTP.

**2. Ai thiết lập cookie, ai gửi cookie đi ở request sau?**  
Máy chủ thường thiết lập qua response header `Set-Cookie`. Trình duyệt lưu và tự lựa chọn cookie phù hợp để gửi trong request header `Cookie`.

**3. `HttpOnly` được bật. JavaScript không đọc được session ID. Tại sao vẫn cần chống CSRF?**  
Vì browser vẫn có thể tự gắn cookie vào request; việc request mang cookie chưa chứng minh người dùng chủ ý yêu cầu thay đổi trạng thái.

**4. Browser có cookie `JSESSIONID`, nhưng server báo chưa đăng nhập. Có nhất thiết là lỗi của cookie không?**  
Không. Session có thể đã hết hạn, bị vô hiệu, không tìm thấy trong kho session hoặc không còn Authentication hợp lệ.

**5. Frontend `app.example.com` gọi `api.example.com`. Tại sao cookie có thể không được gửi dù cả hai cùng một website theo cách hiểu thường ngày?**  
Vì hai địa chỉ khác origin; `fetch` mặc định chỉ gửi credentials cùng origin. Còn phải xét cấu hình credentials, CORS, domain/path, Secure, SameSite và chính sách browser.

**6. Một API dùng bearer token trong `Authorization` có nguy cơ CSRF giống ứng dụng dùng session cookie không?**  
Không thể kết luận chỉ từ chữ “bearer”. Nếu trình duyệt không tự gửi credential và client phải chủ động gắn header, nguy cơ CSRF có thể khác. Nếu token nằm trong cookie tự gửi, cần đánh giá CSRF như các cơ chế cookie khác.

**7. Một người đã đăng nhập có thể sửa mọi bản ghi chỉ vì cookie phiên hợp lệ không?**  
Không. Cookie/session giúp xác định ngữ cảnh xác thực; Spring Security và logic nghiệp vụ vẫn phải kiểm tra quyền thao tác trên chính dữ liệu được yêu cầu.

Khi gặp lỗi đăng nhập hoặc bảo mật request trong Spring Security, hãy kiểm tra theo chuỗi: **response có `Set-Cookie` không → browser có lưu cookie không → request tiếp theo có gửi `Cookie` phù hợp không → server có tìm lại session không → `SecurityContext` có Authentication hợp lệ không → authorization và CSRF có cho phép thao tác không**. Chia nhỏ các bước này giúp xác định đúng lỗi ở tầng HTTP, tầng phiên hay tầng bảo mật.

### Tài liệu tham khảo

- [MDN — Using HTTP cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies)
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie)
- [MDN — Secure cookie configuration](https://developer.mozilla.org/en-US/docs/Web/Security/Practical_implementation_guides/Cookies)
- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/reference/application-properties.html)
