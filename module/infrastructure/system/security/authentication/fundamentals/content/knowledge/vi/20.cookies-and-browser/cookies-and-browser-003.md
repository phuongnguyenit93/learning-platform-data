# HttpOnly flag — Bảo vệ cookie phiên khỏi JavaScript

**HttpOnly** là thuộc tính của HTTP cookie yêu cầu trình duyệt không cho các API JavaScript thông thường đọc giá trị cookie. Với cookie phiên đăng nhập, thuộc tính này làm giảm nguy cơ script độc hại lấy session ID qua document.cookie rồi gửi nó ra ngoài. Trình duyệt vẫn tự gửi cookie trong những request phù hợp với host, path, HTTPS và SameSite; vì thế HttpOnly bảo vệ tính bí mật của cookie trước JavaScript, nhưng không ngăn script chạy cùng origin thực hiện request dưới phiên của người dùng.

Trong hệ thống authentication, cookie thường mang một session identifier ngẫu nhiên để server tra cứu trạng thái phiên. Nếu JavaScript đọc được session ID, XSS có thể đánh cắp và replay phiên từ môi trường khác. HttpOnly chặn con đường đọc trực tiếp này. Tuy nhiên, nếu XSS đã chạy trên origin đáng tin cậy, script vẫn có thể gọi API, đọc phản hồi mà same-origin policy cho phép, thay đổi dữ liệu hoặc khởi tạo thao tác nhạy cảm. Do đó HttpOnly phải đi cùng kiểm soát XSS, CSRF, Secure, SameSite, quản lý phiên và authorization.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích HttpOnly là gì, được thiết lập ở đâu và browser áp dụng nó thế nào.
2. Phân biệt JavaScript đọc cookie với browser tự gửi cookie trong HTTP request.
3. Mô tả HttpOnly giúp giảm nguy cơ đánh cắp session qua XSS nhưng không chặn session riding.
4. Phân biệt vai trò của HttpOnly, Secure, SameSite, Domain, Path và cookie prefix.
5. Thiết kế cookie phiên an toàn cho ứng dụng web và Backend-for-Frontend (BFF).
6. Giải thích vì sao HttpOnly không thay thế CSRF token, kiểm tra Origin hoặc phòng chống XSS.
7. Kiểm tra cookie trong browser DevTools, request header và endpoint phía server.
8. Viết ca kiểm thử cho XSS, CSRF, session fixation, logout và cookie attributes.

## 2. Cookie hoạt động thế nào trong đăng nhập?

Một ứng dụng web thường tạo session ở server sau khi người dùng xác thực thành công. Server sinh session ID ngẫu nhiên, lưu trạng thái phiên trong session store và gửi ID cho browser bằng header Set-Cookie. Browser lưu cookie và tự đính kèm nó vào các request phù hợp. Server đọc header Cookie, tra session ID và quyết định request thuộc phiên nào.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant B as Browser
    participant A as Authentication service
    participant S as Session store
    U->>B: Đăng nhập thành công
    B->>A: POST /login
    A->>S: Tạo session ID ngẫu nhiên
    S-->>A: Session active
    A-->>B: Set-Cookie: __Host-session=...; HttpOnly; Secure
    B->>B: Lưu cookie theo thuộc tính
    B->>A: GET /account kèm Cookie
    A->>S: Tra cứu session
    S-->>A: Session hợp lệ
    A-->>B: Trả dữ liệu theo quyền
~~~

Ví dụ response:

~~~http
HTTP/1.1 200 OK
Set-Cookie: __Host-session=<opaque-random-session-id>; Path=/; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
Content-Type: application/json
~~~

Ở request sau, browser có thể gửi:

~~~http
GET /account HTTP/1.1
Host: app.studyhub.example
Cookie: __Host-session=<opaque-random-session-id>
~~~

Có một khác biệt quan trọng:

- Set-Cookie là response header do server gửi để hướng dẫn browser lưu cookie và thuộc tính của nó.
- Cookie là request header browser gửi lại với tên và giá trị cookie phù hợp. Các thuộc tính HttpOnly, Secure, SameSite, Path và Domain không được gửi lại như một phần của header Cookie.
- Server không thể suy ra cookie đã được bảo vệ bằng HttpOnly chỉ từ request header Cookie; thuộc tính này được browser thực thi tại client. Server cần phát hành cookie đúng cấu hình và kiểm thử hành vi browser.

## 3. HttpOnly thực sự làm gì?

Khi một cookie có thuộc tính HttpOnly, browser không cho các API JavaScript thông thường truy cập giá trị cookie đó. Ví dụ, nếu session cookie có HttpOnly, lệnh:

Thuộc tính HttpOnly phải được server thiết lập trong response Set-Cookie. JavaScript có thể tạo hoặc thay đổi một số cookie bằng document.cookie, nhưng không thể thêm thuộc tính HttpOnly để biến cookie do script tạo thành cookie HttpOnly.

~~~javascript
console.log(document.cookie);
~~~

sẽ không hiển thị cookie phiên đó. Các cookie không có HttpOnly trên cùng origin vẫn có thể xuất hiện trong kết quả, tùy phạm vi và thuộc tính của từng cookie.

HttpOnly không làm cookie biến mất khỏi browser, không mã hóa cookie và không ngăn browser gửi cookie lên server. Browser vẫn tự đính kèm cookie trong request nếu cookie phù hợp với host/domain, path, secure transport và SameSite context. Đây là lý do ứng dụng có thể dùng HttpOnly session cookie mà frontend không cần đọc session ID.

### 3.1. Phạm vi bảo vệ

| Hành vi | HttpOnly có ngăn không? | Giải thích |
| --- | --- | --- |
| JavaScript đọc session cookie bằng document.cookie | Có | Browser không cung cấp cookie HttpOnly qua API JavaScript thông thường. |
| JavaScript ghi đè trực tiếp cookie HttpOnly cùng tên bằng document.cookie | Không thể thay đổi thuộc tính HttpOnly của cookie hiện hữu theo cách đó | Script có thể tạo cookie khác cùng tên với phạm vi khác trong một số trường hợp; server phải cấu hình scope chặt và xử lý cookie trùng tên cẩn thận. |
| Browser tự gửi cookie trong request phù hợp | Không | Đây là hành vi cần thiết để duy trì phiên. |
| XSS gọi fetch tới API cùng origin | Không | Browser có thể tự đính kèm cookie; script không cần đọc giá trị cookie. |
| XSS đọc phản hồi same-origin mà browser cho phép | Không | HttpOnly không phải cơ chế phân quyền nội dung response. |
| Attacker dùng session ID đã đánh cắp từ log/backup/máy bị nhiễm | Không | HttpOnly không thu hồi hoặc ràng buộc session đã bị lộ từ nguồn khác. |
| CSRF từ website khác | Không trực tiếp | Cần SameSite, CSRF token, kiểm tra Origin/Referer và thiết kế request phù hợp. |
| Malware, extension có quyền cao hoặc người có quyền truy cập profile/browser | Không bảo đảm | HttpOnly chủ yếu kiểm soát các API web script thông thường. |

**Cách hiểu đúng:** HttpOnly làm khó việc lấy cắp giá trị session cookie qua JavaScript; nó không làm cho một origin đã bị XSS trở nên vô hại.

## 4. HttpOnly và XSS: giảm đánh cắp token, không ngăn hành động

Cross-site scripting (XSS) xảy ra khi attacker khiến script không đáng tin chạy trong origin của ứng dụng. Nếu session cookie không có HttpOnly, script có thể đọc giá trị cookie và gửi ra ngoài. Attacker sau đó có thể replay session từ môi trường khác cho đến khi server thu hồi hoặc phiên hết hạn.

Khi cookie có HttpOnly, đường đọc trực tiếp đó bị chặn. Nhưng script vẫn đang chạy trong ngữ cảnh origin hợp lệ và có thể thực hiện hành động thay người dùng.

Ví dụ trong môi trường lab được kiểm soát, một script chạy cùng origin có thể gọi:

~~~javascript
fetch("/api/profile", {
  method: "GET",
  credentials: "same-origin"
}).then(response => response.json())
  .then(data => console.log(data));
~~~

Với request same-origin, browser thường gửi cookie phù hợp tự động. Script không cần biết session ID. Nếu endpoint cho phép thay đổi dữ liệu và không có CSRF/authorization/reauthentication phù hợp, script độc hại có thể thực hiện hành động dưới phiên người dùng. Nếu response cho phép same-origin JavaScript đọc, dữ liệu trả về cũng có thể bị lạm dụng.

### 4.1. Phòng vệ XSS vẫn cần thiết

- Encode output theo đúng ngữ cảnh HTML, attribute, URL và JavaScript.
- Ưu tiên API DOM an toàn; tránh đưa dữ liệu không tin cậy vào innerHTML hoặc cơ chế thực thi script.
- Dùng Content Security Policy (CSP) chặt, tránh unsafe-inline/unsafe-eval nếu không cần; dùng nonce/hash phù hợp.
- Cân nhắc Trusted Types để giảm sink DOM XSS ở browser hỗ trợ.
- Cập nhật framework, template engine và dependency; rà soát điểm render dữ liệu do người dùng kiểm soát.
- Bảo vệ các hành động nhạy cảm bằng authorization phía server và step-up/reauthentication theo rủi ro.
- Giới hạn quyền của session; không để một phiên thông thường có quyền quản trị không cần thiết.

HttpOnly là một lớp giảm thiểu hậu quả. Không được dùng nó làm lý do bỏ qua secure coding hoặc kiểm thử XSS.

## 5. HttpOnly và CSRF là hai vấn đề khác nhau

**Cross-site request forgery (CSRF)** lợi dụng việc browser tự gửi cookie tới website đích. Một trang khác có thể khiến browser tạo request tới ứng dụng đã đăng nhập của nạn nhân. Vì cookie tự động được đính kèm, server có thể nhận request mang session hợp lệ mà không biết người dùng có chủ ý hay không.

HttpOnly không chặn điều đó. Trình duyệt vẫn gửi cookie HttpOnly theo quy tắc cookie. Do đó cần nhiều lớp phòng vệ:

1. Đặt SameSite=Lax hoặc Strict phù hợp luồng sản phẩm; chỉ dùng SameSite=None khi cần cross-site cookie và luôn kết hợp Secure.
2. Dùng CSRF token cho request thay đổi trạng thái trong mô hình cookie-based session.
3. Kiểm tra Origin và/hoặc Referer theo policy cho các request nhạy cảm; không dựa duy nhất vào header do client có thể bỏ qua trong một số ngữ cảnh.
4. Không dùng GET để thay đổi trạng thái.
5. Với API nhạy cảm, kiểm tra quyền và điều kiện giao dịch tại server.
6. Thiết kế CORS chính xác; CORS không phải biện pháp CSRF tổng quát và không thay thế CSRF token.

~~~mermaid
flowchart TD
    A["Browser có session cookie"] --> B["Trang cùng origin gọi API"]
    A --> C["Trang cross-site gửi request"]
    B --> D["Cookie được gửi nếu phù hợp"]
    C --> D
    D --> E["Server kiểm tra session"]
    E --> F["Kiểm tra CSRF token / Origin / policy"]
    F --> G{"Request hợp lệ và được phép?"}
    G -->|Có| H["Thực thi action"]
    G -->|Không| I["Từ chối"]
~~~

SameSite có thể giảm nhiều tình huống CSRF, nhưng không nên xem là bảo vệ duy nhất. Hãy kiểm tra hành vi redirect, subdomain cùng site, phương thức request và các client cũ.

## 6. Phối hợp với các thuộc tính cookie khác

Cookie phiên an toàn thường dùng nhiều thuộc tính có trách nhiệm khác nhau:

| Thuộc tính | Tác dụng | Không giải quyết |
| --- | --- | --- |
| HttpOnly | Ngăn JavaScript thông thường đọc giá trị cookie | Không ngăn request tự gửi cookie, XSS session riding hoặc CSRF. |
| Secure | Chỉ gửi cookie qua kênh HTTPS an toàn theo quy tắc browser | Không chống XSS hoặc phishing ở origin hợp lệ. |
| SameSite | Kiểm soát việc gửi cookie trong ngữ cảnh same-site/cross-site | Không thay thế toàn bộ CSRF protection hoặc authorization. |
| Domain | Mở rộng phạm vi host có thể nhận cookie khi được đặt | Domain quá rộng làm tăng phạm vi subdomain có thể nhận cookie. |
| Path | Giới hạn path mà browser gửi cookie tới | Không phải ranh giới bảo mật mạnh giữa các ứng dụng cùng host. |
| Max-Age / Expires | Xác định thời gian browser giữ cookie | Không bảo đảm server-side session còn hợp lệ hoặc đã bị thu hồi. |
| Priority | Gợi ý ưu tiên khi browser cần loại bỏ cookie | Không phải thuộc tính xác thực hay bảo vệ secret. |

### 6.1. Cấu hình khuyến nghị cho session cookie

Một ví dụ thường phù hợp với ứng dụng web cùng origin:

~~~http
Set-Cookie: __Host-session=<random-opaque-id>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

- Secure: chỉ truyền qua HTTPS.
- HttpOnly: không cho JavaScript thông thường đọc.
- SameSite=Lax: giảm gửi cookie trong nhiều request cross-site; cần xác nhận có phù hợp luồng SSO/redirect của sản phẩm.
- Path=/: cookie áp dụng toàn host.
- Không có Domain: cookie là host-only.
- Prefix __Host-: browser hỗ trợ prefix yêu cầu cookie phải có Secure, Path=/ và không có Domain.

Prefix __Host- giúp tránh một số rủi ro ghi đè cookie từ subdomain và thu hẹp phạm vi host. Nếu ứng dụng cần cookie dùng chung nhiều subdomain, phải đánh giá rõ trade-off; không tùy tiện thêm Domain=.example.com cho session cookie nhạy cảm.

### 6.2. SameSite Strict, Lax và None

| Giá trị | Hành vi khái quát | Cân nhắc |
| --- | --- | --- |
| Strict | Hạn chế cookie trong các điều hướng/request cross-site | Bảo vệ mạnh hơn ở nhiều tình huống nhưng có thể làm trải nghiệm liên kết từ email/website ngoài bị gián đoạn. |
| Lax | Cho phép cookie trong một số điều hướng top-level an toàn, thường là GET; hạn chế nhiều request cross-site khác | Điểm cân bằng phổ biến cho session web; phải kiểm tra luồng callback. |
| None | Cho phép cookie trong ngữ cảnh cross-site | Cần Secure; chỉ bật khi thật sự cần, ví dụ một số luồng nhúng hoặc kiến trúc liên site. |

“Site” trong SameSite không hoàn toàn giống “origin”: scheme và registrable domain ảnh hưởng cách browser phân loại site. Hai subdomain có thể được xem là same-site nhưng vẫn là hai origin khác nhau. Điều này quan trọng khi có nhiều ứng dụng hoặc subdomain không cùng mức tin cậy.

## 7. Cookie trùng tên, Domain và Path

Browser có thể lưu nhiều cookie trùng tên với Domain/Path khác nhau. Server có thể nhận nhiều cặp cùng tên trong header Cookie; thứ tự không nên được dùng như một bảo đảm để chọn cookie an toàn. Ứng dụng cần tránh cấu hình cookie session trùng tên ở nhiều path/domain và parser phải xử lý trường hợp trùng tên theo cách rõ ràng.

Ví dụ rủi ro:
- app.example.com đặt session cookie host-only.
- Một subdomain không đáng tin có thể đặt cookie cùng tên với Domain rộng hơn nếu cấu hình cho phép.
- Browser gửi nhiều cookie cùng tên; framework/parser xử lý khác nhau có thể dẫn tới session confusion hoặc cookie tossing.

Biện pháp:
- Dùng prefix __Host- cho cookie phiên nếu phù hợp.
- Không đặt Domain nếu không cần chia sẻ subdomain.
- Dùng tên riêng cho cookie ở từng ứng dụng.
- Tránh coi Path là ranh giới bảo mật; các ứng dụng cùng host vẫn có thể có tương tác phức tạp.
- Kiểm tra hành vi parser/framework khi có cookie trùng tên; không tự chọn giá trị đầu/cuối mà không có policy.

## 8. Thiết kế session cookie trong authentication

HttpOnly phát huy tác dụng rõ nhất khi cookie chỉ chứa **opaque session ID** thay vì toàn bộ quyền hoặc dữ liệu nhạy cảm. Server giữ trạng thái phiên trong session store và có thể thu hồi khi cần.

### 8.1. Session ID cần đủ ngẫu nhiên

- Sinh bằng CSPRNG, có entropy cao và không suy ra từ user ID, timestamp hoặc dữ liệu tuần tự.
- Không chứa thông tin cá nhân hoặc role có thể bị client sửa.
- Không đặt session ID trong URL.
- Không tái sử dụng session ID trước đăng nhập sau khi xác thực thành công.
- Xoay session ID sau login, step-up, thay đổi quyền hoặc các sự kiện nhạy cảm theo policy.
- Lưu trạng thái active/revoked, subject, thời điểm tạo, idle/absolute expiry và metadata cần thiết phía server.

### 8.2. Ví dụ pseudocode cấp phiên

~~~text
onSuccessfulAuthentication(user):
    sessionId = secureRandomValue()
    sessionStore.create(
        id=sessionId,
        subject=user.id,
        createdAt=now,
        lastSeenAt=now,
        absoluteExpiresAt=policy.absoluteExpiry,
        status="active"
    )

    setCookie(
        name="__Host-session",
        value=sessionId,
        path="/",
        secure=true,
        httpOnly=true,
        sameSite="Lax"
    )
~~~

Đây là logic khái niệm. Trong thực tế, cookie cần được phát hành qua HTTP response đúng chuẩn; session store cần TTL và cơ chế thu hồi nhất quán. Không ghi sessionId vào log hoặc trace.

### 8.3. Logout và thu hồi

Logout cần vô hiệu session phía server, sau đó yêu cầu browser xóa cookie bằng Set-Cookie có cùng tên và phạm vi phù hợp, kèm Max-Age=0 hoặc thời điểm hết hạn trong quá khứ. Chỉ xóa cookie phía browser mà không thu hồi session phía server có thể để session ID bị đánh cắp tiếp tục hoạt động ở nơi khác.

Ví dụ response xóa cookie host-only:

~~~http
Set-Cookie: __Host-session=; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=0
~~~

Server vẫn phải đánh dấu session revoked hoặc xóa session record. Khi token/session có nhiều thiết bị, cần phân biệt logout thiết bị hiện tại với logout tất cả phiên.

## 9. HttpOnly trong SPA và Backend-for-Frontend

SPA thường cần gọi API sau khi người dùng đăng nhập. Có hai mô hình chính:

### 9.1. Browser giữ session cookie HttpOnly

Browser tự gửi cookie cho API cùng origin. JavaScript không đọc session ID; frontend chỉ nhận kết quả nghiệp vụ từ API. Cách này phù hợp khi backend quản lý session và cookie được cấu hình đúng.

Với fetch, request same-origin thường gửi credentials theo mặc định same-origin. Với request cross-origin, client thường cần cấu hình credentials: "include" và server phải có CORS credentials policy chính xác, origin cụ thể, cookie phù hợp SameSite và CSRF protection. Không dùng wildcard Access-Control-Allow-Origin: * cùng credentials.

### 9.2. Backend-for-Frontend (BFF)

BFF giữ access/refresh token ở server. Browser chỉ giữ cookie session HttpOnly tới BFF; BFF gọi API downstream bằng token phía server. Cách này giảm việc browser trực tiếp giữ bearer token dài hạn.

~~~mermaid
flowchart LR
    JS["SPA JavaScript"] -->|"Request + cookie session"| BFF["BFF backend"]
    BFF -->|"Session lookup"| S[("Session/token store")]
    BFF -->|"Access token server-side"| API["Resource API"]
    API --> DATA[("Dữ liệu")]
    BFF -->|"Response đã kiểm tra quyền"| JS
~~~

HttpOnly không tự tạo ra BFF. BFF cần bảo vệ session cookie, CSRF, authorization và token storage như mọi backend khác. Nếu XSS chạy trong SPA, script vẫn có thể gọi BFF dưới phiên người dùng và đọc response được phép. Vì vậy BFF giảm nguy cơ đánh cắp token trực tiếp nhưng không thay thế phòng chống XSS.

## 10. Các lỗi cấu hình thường gặp

| Lỗi | Hậu quả | Sửa thế nào |
| --- | --- | --- |
| Session cookie thiếu HttpOnly | Script có thể đọc giá trị qua API JavaScript | Thiết lập HttpOnly từ server và kiểm thử response. |
| Cookie thiếu Secure | Có nguy cơ bị gửi qua kết nối không an toàn trong cấu hình/đường dẫn không phù hợp | Bắt buộc HTTPS và Secure; triển khai HSTS phù hợp. |
| Dùng SameSite=None nhưng thiếu Secure | Browser hiện đại có thể từ chối cookie hoặc hành vi không như mong đợi | Chỉ dùng None khi cần và kèm Secure. |
| Cho mọi subdomain nhận session cookie | Subdomain yếu có thể làm tăng bề mặt nhận/ghi cookie | Ưu tiên host-only và __Host- nếu kiến trúc cho phép. |
| Coi HttpOnly là chống XSS hoàn chỉnh | Script vẫn gọi API và thực hiện hành động | Phòng XSS và giới hạn quyền/step-up ở server. |
| Coi HttpOnly là chống CSRF | Browser vẫn tự gửi cookie trong request phù hợp | SameSite, CSRF token, Origin/Referer và method design. |
| Chỉ xóa cookie khi logout | Session bị đánh cắp có thể còn hợp lệ ở thiết bị khác | Thu hồi session server-side và xóa cookie browser. |
| Session ID không xoay sau login | Session fixation có thể tồn tại | Tạo ID mới sau xác thực/nâng quyền. |
| Cookie có thời hạn dài nhưng session server không có idle timeout | Phiên bị bỏ quên vẫn có thể hoạt động | Thiết lập idle và absolute expiry phía server. |
| Cookie chứa quyền không kiểm tra server-side | Client/session claim có thể bị lạm dụng nếu thiết kế sai | Lưu session opaque, kiểm tra quyền server-side. |
| Dùng Domain/Path không nhất quán | Cookie trùng tên, scope không mong muốn | Chuẩn hóa tên và phạm vi; kiểm tra parser. |

## 11. Kiểm thử HttpOnly

Kiểm thử cần chứng minh cả hai mặt: script không đọc được cookie, nhưng browser vẫn gửi cookie để ứng dụng hoạt động. Không chỉ nhìn vào giao diện đăng nhập.

### 11.1. Kiểm tra response header

Sau đăng nhập thành công, kiểm tra Set-Cookie trong Network panel hoặc integration test. Cookie phiên cần có HttpOnly, Secure, SameSite và scope phù hợp. Không kiểm tra bằng cách tìm chữ HttpOnly trong request Cookie, vì browser không gửi thuộc tính đó về server.

### 11.2. Kiểm tra JavaScript access

Trong DevTools Console của origin ứng dụng:

~~~javascript
document.cookie
~~~

Session cookie có HttpOnly không được xuất hiện trong kết quả. Cookie không HttpOnly khác (nếu có) vẫn có thể xuất hiện. Kiểm tra bằng test browser tự động trên đúng domain/HTTPS và phiên bản browser mục tiêu.

### 11.3. Kiểm tra browser gửi cookie

Gọi endpoint same-origin yêu cầu đăng nhập. Trong Network panel, kiểm tra request có header Cookie tương ứng và server nhận diện đúng session. Nếu dùng fetch, nhớ kiểm tra credentials mode và domain/path/SameSite.

### 11.4. Kiểm tra giới hạn XSS

Trong môi trường test có quyền:
- Xác minh script không đọc được giá trị session cookie qua document.cookie.
- Xác minh script cùng origin vẫn có thể gọi endpoint thử nghiệm bằng cookie tự động đính kèm.
- Xác minh endpoint thay đổi trạng thái yêu cầu CSRF protection, authorization và step-up phù hợp.
- Xác minh CSP/encoding/Trusted Types và các kiểm soát XSS khác ngăn script không tin cậy được thực thi.

Mục đích là chứng minh HttpOnly giảm khả năng trích xuất session ID, đồng thời phát hiện nhầm tưởng rằng nó chặn mọi tác động của XSS.

### 11.5. Bộ ca kiểm thử chấp nhận

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Login response phát hành session cookie | Có HttpOnly, Secure, SameSite và scope theo policy. |
| document.cookie được đọc từ cùng origin | Không có giá trị session cookie HttpOnly. |
| Browser gọi API same-origin sau login | Cookie vẫn được gửi và server nhận đúng session. |
| Request HTTP không an toàn | Cookie Secure không được gửi qua kênh HTTP theo browser policy. |
| Cross-site request giả mạo | Bị hạn chế bởi SameSite/CSRF token/Origin policy; HttpOnly không được coi là lớp chặn duy nhất. |
| XSS script thử đọc cookie | Không đọc được session cookie HttpOnly. |
| XSS script gọi endpoint thử nghiệm cùng origin | Browser vẫn có thể gửi cookie; endpoint phải có kiểm soát action/CSRF/authorization. |
| Session cookie từ subdomain không được tin cậy | Không thể ghi đè cookie __Host- hợp lệ theo quy tắc prefix của browser hỗ trợ. |
| Session ID trước đăng nhập bị tái sử dụng | Kiểm thử thất bại; server phải xoay session ID. |
| Logout | Session bị thu hồi phía server và cookie được xóa đúng scope. |
| Session hết idle/absolute expiry | Server từ chối dù browser còn giữ cookie. |
| Cookie trùng tên với Domain/Path khác | Parser và policy không chọn nhầm session; cấu hình được phát hiện. |
| BFF gọi downstream API | Browser không nhận refresh token; BFF giữ token server-side và kiểm tra quyền. |
| CORS credentialed request | Chỉ origin được phép, credentials policy cụ thể và CSRF được kiểm tra. |

## 12. Bài thực hành: bảo vệ session cookie cho StudyHub

**Bối cảnh:** StudyHub là ứng dụng học tập có SPA ở app.studyhub.example, backend ở cùng origin qua reverse proxy và API quản lý hồ sơ/điểm. Sau đăng nhập, backend cấp session cookie. Một số API cho phép cập nhật email và sửa điểm.

### 12.1. Yêu cầu thiết kế

1. Chọn cookie name, Domain, Path, Secure, HttpOnly, SameSite, Max-Age và giải thích từng thuộc tính.
2. Xác định session ID là opaque hay self-contained; server lưu subject, trạng thái, idle/absolute expiry và quyền thế nào.
3. Vẽ luồng login, request API, logout và thu hồi phiên.
4. Phân tích một tình huống XSS: script không đọc cookie nhưng gọi API dưới phiên người dùng.
5. Phân tích một tình huống CSRF: website ngoài khiến browser gửi request thay đổi email.
6. Xây dựng biện pháp phòng vệ: HttpOnly, Secure, SameSite, CSRF token, Origin validation, CSP, output encoding và authorization.
7. Xác định hành động nào cần reauthentication/step-up, ví dụ đổi email khôi phục hoặc sửa điểm.
8. Viết test chứng minh session cookie không thể đọc bằng JavaScript nhưng vẫn được browser tự gửi trong request hợp lệ.

### 12.2. Câu hỏi tự đánh giá

1. HttpOnly được thiết lập bằng response header nào và vì sao JavaScript không thể bật nó cho cookie?
2. Vì sao browser vẫn gửi HttpOnly cookie trong request?
3. HttpOnly ngăn XSS đánh cắp session ID bằng cách nào?
4. Vì sao XSS vẫn có thể gọi API cùng origin dưới phiên người dùng?
5. HttpOnly và SameSite giải quyết những vấn đề khác nhau nào?
6. Vì sao cookie Secure vẫn cần HttpOnly?
7. __Host- yêu cầu những điều kiện gì và giúp thu hẹp ranh giới nào?
8. Vì sao không nên dùng Domain rộng cho session cookie nếu không cần chia sẻ subdomain?
9. Logout cần làm gì ở server ngoài việc xóa cookie?
10. BFF giảm rủi ro nào và không giải quyết được rủi ro nào?

**Tiêu chí hoàn thành:** Người học có thể giải thích chính xác browser bảo vệ và gửi cookie như thế nào, cấu hình cookie phiên theo đúng trust boundary, phân biệt XSS với CSRF, thiết kế logout/expiry và viết test chứng minh HttpOnly không bị hiểu nhầm thành biện pháp bảo vệ toàn diện.

## 13. Tài liệu nên đọc tiếp

- **RFC 6265bis / HTTP State Management Mechanism**: mô hình cookie, thuộc tính và hành vi browser; kiểm tra phiên bản hiện hành.
- **MDN — Set-Cookie và HttpOnly**: cách browser lưu và gửi cookie.
- **OWASP Session Management Cheat Sheet**: session ID, cookie attributes, rotation, timeout và logout.
- **OWASP Cross-Site Request Forgery Prevention Cheat Sheet**: SameSite, CSRF token và Origin checks.
- **OWASP Cross Site Scripting Prevention Cheat Sheet**: phòng XSS và giảm tác động script độc hại.
- **OWASP ASVS**: chuyển yêu cầu cookie/session thành tiêu chí xác minh.

Khi triển khai thật, hãy kiểm tra browser mục tiêu, domain/subdomain, HTTPS termination, reverse proxy, SSO redirect và mô hình SPA/BFF. **HttpOnly là một thuộc tính quan trọng để bảo vệ bí mật của session cookie khỏi JavaScript; phiên chỉ an toàn khi cookie, server-side session, XSS, CSRF, logout và authorization được thiết kế cùng nhau.**
