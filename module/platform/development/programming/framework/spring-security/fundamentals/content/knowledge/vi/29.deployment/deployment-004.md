# Cấu hình cookie theo tên miền, đường dẫn và chính sách trình duyệt

> **Phạm vi:** triển khai ứng dụng **Java 17+, Spring Boot 3.x, Spring Security 6.x, Servlet/Spring MVC** dùng phiên đăng nhập trong trình duyệt. Bài học giải thích cách trình duyệt nhận, lưu và gửi cookie theo `Domain`, `Path`, `Secure`, `HttpOnly`, `SameSite`, thời hạn và các chính sách third-party; sau đó cấu hình cookie phiên an toàn trong Spring Boot, kiểm thử bằng MockMvc và kiểm tra thực tế qua trình duyệt/HTTPS. **Cookie không phải cơ chế cấp quyền**: ngoài phạm vi cookie còn cần xác thực, phân quyền, CSRF, kiểm soát session và cấu hình proxy đúng.

## 1. Bắt đầu từ một tình huống triển khai

Giả sử công ty vận hành ba dịch vụ:

- `https://app.example.com`: giao diện web có đăng nhập người dùng.
- `https://api.example.com`: API phục vụ web.
- `https://admin.example.com`: giao diện quản trị cần bảo vệ chặt.

Ứng dụng Java tạo session sau khi user đăng nhập. Trình duyệt giữ một cookie chứa **mã phiên ngẫu nhiên** (session identifier), ví dụ tên `__Host-SESSION`. Vấn đề cần quyết định không chỉ là “đã có cookie chưa”, mà gồm:

1. Cookie có được gửi tới **chính host đã tạo** hay toàn bộ `*.example.com`?
2. Cookie có được gửi khi URL nằm ở `/app`, `/admin` hay `/api`?
3. Chỉ gửi qua HTTPS hay có thể bị gửi ở HTTP?
4. JavaScript có đọc được cookie không?
5. Khi người dùng đến từ website khác hoặc frontend gọi API khác origin, cookie có được đính kèm không?
6. Khi session hết hạn, logout, trình duyệt chặn third-party cookies hoặc reverse proxy đổi scheme, điều gì xảy ra?

Một cấu hình cookie thiếu chính xác có thể khiến người dùng liên tục bị chuyển về trang login, browser không gửi session, cookie bị mở rộng sang subdomain không đáng tin, hoặc request giả mạo được gửi kèm session trong những tình huống nguy hiểm.

**Mục tiêu:** biết đọc `Set-Cookie`, phân biệt host-only và domain cookie, chọn path/samesite đúng mục đích, cấu hình `server.servlet.session.cookie.*` của Spring Boot, dự đoán hành vi trình duyệt và xác minh bằng test thay vì chỉ nhìn trạng thái HTTP.

## 2. Cookie thực sự hoạt động như thế nào?

Ứng dụng trả một HTTP response có header:

```http
HTTP/1.1 200 OK
Set-Cookie: __Host-SESSION=opaque-random-id; Path=/; Secure; HttpOnly; SameSite=Lax
```

Trình duyệt quyết định **có chấp nhận** cookie này không, và nếu có thì lưu cùng các metadata phạm vi. Ở request tiếp theo phù hợp, trình duyệt gửi:

```http
GET /profile HTTP/1.1
Host: app.example.com
Cookie: __Host-SESSION=opaque-random-id
```

**Điểm khác biệt bắt buộc:** request `Cookie` chỉ mang **tên và giá trị**, không mang lại các thuộc tính `Secure`, `HttpOnly`, `SameSite`, `Path` hoặc `Domain`. Những thuộc tính được áp dụng bởi browser khi lưu và quyết định gửi cookie. Do đó, **server không thể dựa vào việc đọc một header `Cookie` để chứng minh browser đã nhận cookie qua HTTPS hoặc thuộc tính nào đã được dùng**; phải cấu hình response đúng và kiểm tra bằng browser/HTTPS.

Session ID trong cookie thường chỉ là một **mã tra cứu** tới session phía server hoặc hệ thống session store; nó không tự là toàn bộ profile/quyền. Khi server đã xóa/invalid session hoặc session hết hạn, trình duyệt có thể vẫn giữ một cookie nhưng mã ấy không còn xác thực được.

### Hai header hay bị nhầm

| Header | Hướng dữ liệu | Nội dung |
| --- | --- | --- |
| `Set-Cookie` | Server → browser | Tạo/cập nhật/hết hạn cookie; kèm `Domain`, `Path`, `Secure`, `SameSite`… |
| `Cookie` | Browser → server | Những cặp `name=value` thuộc phạm vi được browser gửi tới server |
| `Authorization` | Client → server | Credential như Bearer/Basic (không phải cookie session, dù có thể cùng tồn tại) |

Không đặt toàn bộ object người dùng hoặc password vào cookie session. Không log đầy đủ `Cookie`, `Set-Cookie` hoặc session ID; chúng có thể chứa giá trị có khả năng chiếm quyền phiên.

## 3. Domain: host-only khác cookie dùng chung subdomain

### 3.1. Không khai báo Domain → host-only (khuyến nghị mặc định)

Nếu response từ `https://app.example.com` tạo:

```http
Set-Cookie: SESSION=abc; Path=/; Secure; HttpOnly; SameSite=Lax
```

và **không có `Domain`**, đây là **host-only cookie**. Trình duyệt gửi lại cho `app.example.com` nhưng **không gửi** cho `api.example.com` hay `admin.example.com` chỉ vì các host cùng thuộc `example.com`.

Nếu nhu cầu chỉ là user đăng nhập tại một ứng dụng web, host-only thường giảm bề mặt rủi ro và tránh cookie vô tình được gửi tới subdomain khác. Trong Spring Boot, **không đặt** `server.servlet.session.cookie.domain` nếu muốn cookie chỉ thuộc host đang phục vụ response.

### 3.2. Có Domain=example.com → phạm vi có thể rộng sang subdomain

Nếu `app.example.com` tạo:

```http
Set-Cookie: SESSION=abc; Domain=example.com; Path=/; Secure; HttpOnly; SameSite=Lax
```

trình duyệt có thể gửi cookie tới `example.com` và những subdomain của nó, chẳng hạn `app.example.com`, `api.example.com` và `admin.example.com` khi các điều kiện khác cũng phù hợp.

Điều đó **không đồng nghĩa các ứng dụng tự chia sẻ đăng nhập**. API B phải có cách **hiểu cùng session ID và cùng session store/chính sách phiên** hoặc một cơ chế xác thực liên thông đã thiết kế. Chỉ làm cho cookie đi tới B không khiến B nhận biết user của A; ngược lại, nó làm tăng số dịch vụ nhận mã phiên nhạy cảm.

**Rủi ro:** một subdomain bị chiếm quyền hoặc chứa ứng dụng yếu có thể gây tấn công liên quan domain cookie, như cookie tossing/session fixation hoặc ghi đè cookie trong các điều kiện nhất định. Không mở rộng phạm vi cookie chỉ để “cho tiện”; với đăng nhập liên ứng dụng, cân nhắc OIDC/SSO và phiên riêng cho từng host.

### 3.3. Ràng buộc tên miền

- Server chỉ được đặt `Domain` phù hợp với host hiện tại hoặc miền cha được phép; `app.example.com` không thể tùy ý đặt cookie cho `other-company.test`.
- Không được dùng một public suffix như `com` làm cookie domain. Trình duyệt áp dụng Public Suffix List và chính sách cookie.
- Dấu chấm đầu trong `Domain=.example.com` theo xử lý hiện đại thường được bỏ qua; không làm tăng quyền so với `Domain=example.com`.
- **Cookie không bị phân tách theo port.** Ví dụ hai ứng dụng khác port trên **cùng host** có thể cùng nhận cookie nếu domain/path/scheme phù hợp, dù chúng là **hai origin khác nhau** theo chính sách CORS.
- Một tên cookie giống nhau có thể tồn tại ở nhiều phạm vi `Domain`/`Path`. Khi nhiều cookie cùng tên được gửi, thứ tự không phải cơ sở đáng tin để server chọn “đúng” cookie. Tránh trùng tên/phạm vi và thiết kế migration rõ ràng.

**Ghi nhớ:** phạm vi `Domain` là quyết định **cookie delivery**, không phải một rule authorization hoặc đảm bảo isolation hoàn toàn giữa các ứng dụng trên cùng site.

## 4. Path: hạn chế nơi cookie được gửi, không phải ranh giới bảo mật

Một cookie với `Path=/app` phù hợp với request path `/app`, `/app/` và `/app/profile` nhưng không phù hợp với `/admin` hay `/application` theo quy tắc path matching của browser.

| Cookie Path | Request URL path | Browser có thể gửi cookie? |
| --- | --- | --- |
| `/` | `/profile` | Có nếu domain, scheme và SameSite đều phù hợp |
| `/app` | `/app` | Có |
| `/app` | `/app/account` | Có |
| `/app` | `/application` | Không |
| `/app` | `/admin` | Không |
| `/admin` | `/app/profile` | Không |

Một ứng dụng Spring MVC triển khai tại `/portal` có thể cần session cookie `Path=/portal` để browser chỉ gửi trên các request trong context đó. Nhưng nếu SPA chạy tại `/` và backend session cần dùng ở `/api`, đặt `Path=/portal` sẽ khiến request API **không có session cookie**, dẫn đến 401/redirect không mong đợi.

**Quan trọng:** `Path` **không phải cơ chế bảo vệ bí mật giữa các ứng dụng chạy chung host**. JavaScript, URL forwarding, cấu trúc trang hay một ứng dụng có quyền trên host vẫn có nhiều đường tương tác; thuộc tính `Path` không thay thế phân quyền, origin isolation hay segmentation bằng host riêng.

### Path và logout phải khớp

Khi muốn xóa cookie, thường trả một `Set-Cookie` mới có **cùng tên, Domain và Path tương ứng** với cookie gốc và `Max-Age=0` (hoặc Expires trong quá khứ). Nếu cookie thật được đặt ở `Path=/portal` mà code xóa tại `Path=/`, browser có thể giữ cookie cũ. Tương tự, đổi cấu hình `Domain` có thể để lại cookie cùng tên ở phạm vi cũ.

Tuy nhiên **xóa cookie phía browser không thay thế invalidation session phía server**. Spring Security logout cần invalid session/clear security context theo cấu hình; các token dài hạn/refresh tokens có vòng đời riêng và có thể đòi revoke.

## 5. Secure, HttpOnly và tên cookie có tiền tố bảo vệ

### 5.1. Secure

`Secure` yêu cầu browser gửi cookie qua kênh bảo mật, thông thường **HTTPS**. Với cookie mang session ID, nên đặt `Secure` trong production cùng với TLS/HSTS được cấu hình đúng.

**Không hiểu sai:** `Secure` không mã hóa giá trị cookie trong application log, không bảo vệ XSS và không giúp một HTTP server tự trở thành HTTPS. Trên một số trình duyệt có ngoại lệ liên quan `localhost`, nhưng **không được dựa vào ngoại lệ ấy làm tiêu chuẩn triển khai production**.

Khi ứng dụng chạy sau reverse proxy xử lý TLS, kết nối từ proxy tới Java có thể là HTTP trong mạng nội bộ. Vẫn nên phát session cookie có `Secure` nếu URL người dùng thực sự là HTTPS. Đặt thuộc tính rõ ràng và kiểm tra redirect/forwarded headers trong deployment.

### 5.2. HttpOnly

`HttpOnly` ngăn script trên trang đọc cookie qua `document.cookie` hoặc các API đọc cookie tương ứng. Đây là một lớp giảm thiểu rủi ro bị đánh cắp session ID qua JavaScript.

Nhưng `HttpOnly` **không** ngăn browser tự đính kèm cookie trong request hợp lệ, gồm request do JavaScript `fetch()`/XHR khởi tạo khi chính sách browser cho phép. Vì vậy XSS vẫn có thể khiến hành động được thực hiện dưới phiên người dùng; cần output encoding, CSP, CSRF/authorization và các kiểm soát khác.

Đừng tắt `HttpOnly` cho **session cookie** chỉ vì frontend muốn biết username. Frontend nên gọi API `/api/me` để lấy những trường cần thiết. Nếu SPA dùng một **cookie CSRF riêng** mà JavaScript cần đọc, có thể có lý do đặt `HttpOnly=false` **cho cookie CSRF ấy**, không phải cho session cookie.

### 5.3. __Secure- và __Host-

Trình duyệt hiện đại hỗ trợ các **cookie name prefixes** mang thêm điều kiện:

| Tiền tố | Yêu cầu browser kiểm tra | Khi nên cân nhắc |
| --- | --- | --- |
| `__Secure-` | Cookie được đặt từ secure origin và có `Secure` | Cookie cần Secure nhưng có thể có Domain/Path tùy hợp đồng |
| `__Host-` | Secure origin, `Secure`, `Path=/`, **không có Domain** | Session cookie chỉ thuộc host hiện tại, host-wide |
| Không tiền tố | Không có kiểm tra prefix bổ sung | Môi trường local/test hoặc cookie không đủ điều kiện dùng prefix |

Ví dụ dành cho **HTTPS production**:

```http
Set-Cookie: __Host-SESSION=opaque-id; Path=/; Secure; HttpOnly; SameSite=Lax
```

Nếu thêm `Domain=example.com` hoặc đổi `Path=/portal`, cookie mang tiền tố `__Host-` **không còn hợp lệ** theo quy tắc prefix và có thể bị browser từ chối. Tên prefix không tự thay thế các thuộc tính: ứng dụng vẫn cần phát đúng `Secure`, `Path` và bỏ `Domain`.

**Bài học thiết kế:** nếu bắt buộc dùng cookie chia sẻ subdomain hoặc giới hạn path, **không thể đồng thời dùng `__Host-`**. Cân nhắc tên khác như `__Secure-SESSION` kết hợp `Secure`, `HttpOnly`, phạm vi hạn chế nhất có thể, sau khi đánh giá rủi ro.

## 6. SameSite: chính sách gửi cookie theo "site", không phải theo origin

`SameSite` giảm việc cookie bị đính kèm trong một số request có nguồn từ website khác, đặc biệt liên quan CSRF. Với cách xác định **schemeful same-site** của trình duyệt hiện đại, site xét **scheme** (`https`/`http`) và miền có thể đăng ký (`registrable domain`); origin còn xét thêm host và port.

Ví dụ:

| Hai URL | Quan hệ site | Quan hệ origin |
| --- | --- | --- |
| `https://app.example.com` và `https://api.example.com` | Thường là **same-site** | **Cross-origin** vì host khác |
| `https://app.example.com` và `https://app.example.com:8443` | **Same-site** | **Cross-origin** vì port khác |
| `http://app.example.com` và `https://app.example.com` | **Cross-site** theo schemeful site | **Cross-origin** vì scheme khác |
| `https://app.example.com` và `https://other.example.net` | **Cross-site** | **Cross-origin** |

Đây là điểm cực kỳ dễ nhầm: frontend tại `app.example.com` gọi API tại `api.example.com` có thể là **cross-origin nhưng same-site**. `SameSite=Lax` chưa chắc là nguyên nhân cookie bị chặn; có thể cookie là **host-only** của app nên không thuộc api, frontend không bật `credentials: "include"`, CORS chưa đúng, hoặc browser từ chối cookie vì Secure/Domain/Path.

### 6.1. Các giá trị

| SameSite | Hành vi khái quát | Ứng dụng |
| --- | --- | --- |
| `Strict` | Cookie chỉ được gửi trong bối cảnh same-site; điều hướng từ site khác có thể không mang cookie | Trang cần hạn chế cross-site tối đa, nhưng có thể làm khó luồng chuyển từ email/link ngoài |
| `Lax` | Được gửi trong same-site; trong cross-site có thể gửi ở điều hướng top-level dùng safe method như GET | Phù hợp nhiều ứng dụng web có đăng nhập và điều hướng thông thường |
| `None` | Cho phép cookie được gửi trong cross-site context **nếu browser cho phép**; bắt buộc `Secure` | Một số iframe, identity/embedded integration, flow cross-site được thiết kế riêng |

Nếu không ghi `SameSite`, nhiều browser có chính sách mặc định gần với `Lax`, **nhưng không nên dựa vào cách mặc định của từng browser/phiên bản**; một số tình huống có khác biệt khi thuộc tính bị bỏ trống. Hãy đặt rõ `Strict`, `Lax` hoặc `None` theo flow.

**`SameSite=None; Secure` không bảo đảm cookie third-party hoạt động:** browser có thể chặn cookie của bên thứ ba, người dùng có thể tắt tracking, iframe chịu sandbox/storage access restrictions, hoặc có cơ chế phân vùng (CHIPS). Không được coi `None` là một “công tắc bypass” chính sách quyền riêng tư của trình duyệt.

### 6.2. SameSite không thay thế CSRF

Ngay cả với `SameSite=Strict/Lax`, vẫn cần xem:

- Cross-site top-level navigation với safe method ở `Lax`.
- Môi trường cùng site nhưng **khác origin/subdomain**: một subdomain bị chiếm quyền có thể gửi request same-site.
- Những browser cũ/đặc thù, cookie được gửi khi người dùng truy cập từ các flow cho phép.
- Những endpoints không dùng session cookie nhưng có credential khác (Bearer, HTTP Basic, mTLS) và các cơ chế request giả mạo tương ứng.

Với form login/session của Spring Security, **không tắt CSRF chỉ vì đặt SameSite=Lax**. `CsrfFilter` và CSRF token ở form/headers là một lớp riêng cho request thay đổi trạng thái, đồng thời cần xử lý XSS và kiểm soát quyền theo request/resource.

## 7. CORS, fetch credentials và chính sách browser

### 7.1. Same-site không đồng nghĩa same-origin

Frontend tại `https://app.example.com`:

```javascript
const response = await fetch("https://api.example.com/api/me", {
  method: "GET",
  credentials: "include"
});
```

`credentials: "include"` cho phép browser gửi/nhận credentials theo các quy tắc cookie. Nhưng để JavaScript **đọc response** từ API cross-origin có credentials, server phải cho phép một origin cụ thể và credentials:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
```

Với credentialed CORS request, server **không thể** dùng `Access-Control-Allow-Origin: *` rồi mong browser cho JavaScript đọc response. Preflight phải được xử lý khi request có điều kiện tạo preflight. Hãy cấu hình CORS tại server/gateway đáng tin và cho phép origin cụ thể, không phản chiếu bừa mọi `Origin`.

**Hai quyết định riêng:** (1) browser có gửi cookie theo Domain/Path/Secure/SameSite và `credentials` không? (2) JavaScript có được phép **đọc response** theo CORS không? Một API trả 200 trong network nhưng JS vẫn bị CORS block là hiện tượng khác với 401 vì browser không gửi session cookie.

CORS **không phải** cơ chế chống CSRF toàn diện. Form POST từ website khác có thể đi theo những luật CORS khác với `fetch` và có thể gây side effect nếu CSRF/authorization thiếu.

### 7.2. Third-party cookie và Partitioned

Với widget đặt trong iframe của một site khác, cookie `SameSite=None; Secure` vẫn có thể bị browser hạn chế. Công nghệ **CHIPS** sử dụng thuộc tính `Partitioned` để lưu cookie trong một phân vùng theo top-level site ở những browser hỗ trợ:

```http
Set-Cookie: __Host-EMBED=opaque; Path=/; Secure; HttpOnly; SameSite=None; Partitioned
```

Cookie partitioned **không phải session chung toàn Internet**, cũng không phải cách bỏ qua chính sách quyền riêng tư. Cần kiểm tra browser support và nhu cầu thực tế. Spring Boot 3.5 có cấu hình `server.servlet.session.cookie.partitioned` cho session cookie, nhưng hành vi cuối còn phụ thuộc servlet container/browser và phiên bản thực tế. Không bật tùy tiện cho mọi session: một user có thể có các phân vùng cookie khác nhau theo top-level site.

## 8. Cấu hình session cookie trong Spring Boot 3

### 8.1. Cấu hình khuyến nghị cho host riêng dưới HTTPS

Giả sử ứng dụng được công bố duy nhất ở `https://app.example.com`. Tạo file **`src/main/resources/application.properties`**:

```properties
spring.application.name=cookie-policy-demo

# Session cookie host-only, chi gui qua HTTPS.
server.servlet.session.cookie.name=__Host-SESSION
server.servlet.session.cookie.path=/
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax

# Khong dat server.servlet.session.cookie.domain:
#   de browser tu gioi han cookie trong host tra response.

# Thoi han inactivity cua HttpSession phia server.
server.servlet.session.timeout=20m

# Dung cookie de theo doi session, khong dung URL rewriting.
server.servlet.session.tracking-modes=cookie
```

**Giải thích từng property:**

| Property | Giá trị ví dụ | Ý nghĩa |
| --- | --- | --- |
| `server.servlet.session.cookie.name` | `__Host-SESSION` | Tên cookie chứa mã session; prefix yêu cầu Secure + Path=/ + không Domain |
| `...path` | `/` | Cookie được gửi cho mọi URL path ở host hiện tại; phù hợp prefix `__Host-` |
| `...secure` | `true` | Yêu cầu browser chỉ gửi qua kênh bảo mật |
| `...http-only` | `true` | Không cho JavaScript đọc session cookie qua `document.cookie` |
| `...same-site` | `lax` | Giảm việc gửi cookie trong nhiều request cross-site, vẫn hỗ trợ top-level link GET |
| `...domain` | **không khai báo** | Tạo cookie host-only, không mở rộng sang sibling subdomain |
| `server.servlet.session.timeout` | `20m` | Thời gian inactivity của **session phía server**, không phải tuổi thọ cookie trong browser |
| `...tracking-modes` | `cookie` | Tránh dùng session tracking qua URL khi cấu hình hỗ trợ |

**Chú ý về `max-age`:** `server.servlet.session.cookie.max-age` điều khiển vòng đời cookie phía browser (nếu cấu hình), **khác** `server.servlet.session.timeout`. Không cần đặt cookie session thành persistent chỉ để kéo dài đăng nhập. Một cookie vẫn còn không có nghĩa HttpSession còn hiệu lực; và “cookie phiên” không có `Max-Age` vẫn có thể được khôi phục bởi tính năng session restore của browser tùy chính sách.

**Không copy cấu hình này nguyên xi sang môi trường HTTP local:** browser sẽ không thể dùng session cookie `__Host-SESSION; Secure` trên một kết nối HTTP bình thường. Để kiểm thử browser thực, ưu tiên cấu hình HTTPS local hoặc dùng profile local **chỉ phục vụ phát triển** như dưới đây.

### 8.2. Profile localhost dành cho lab, không deploy

Tạo file **`src/main/resources/application-local.properties`**:

```properties
# CHI cho HTTP localhost/dev. KHONG deploy production.
server.servlet.session.cookie.name=DEMOSESSION_LOCAL
server.servlet.session.cookie.secure=false
server.servlet.session.cookie.path=/
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
```

Chạy với Gradle Wrapper:

```bash
./gradlew bootRun --args='--spring.profiles.active=local'
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=local"
```

Profile `local` thay tên cookie để **không dùng `__Host-` khi đã tắt Secure**. Chạy với HTTP `localhost:8080` có thể thử form login trong browser để hiểu session, nhưng không thể dùng kết quả HTTP làm bằng chứng cookie production đủ an toàn. Cookie ở HTTPS production cần được kiểm tra riêng với TLS, ingress và host thật.

### 8.3. Cấu hình chia sẻ cookie qua subdomain khi thực sự cần

Nếu có thiết kế **đã được phê duyệt** phải phát domain cookie:

```properties
# Chi minh hoa; KHONG ket hop voi ten __Host-SESSION.
server.servlet.session.cookie.name=__Secure-SESSION
server.servlet.session.cookie.domain=example.com
server.servlet.session.cookie.path=/
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
```

Phải dùng một tên không yêu cầu host-only như `__Secure-SESSION` thay vì `__Host-SESSION`. Cần đánh giá tất cả subdomain, session store, vấn đề cookie conflict, logout và migration. **Không phải cứ Domain=example.com thì mọi service đều được đăng nhập**. Chia sẻ session trên nhiều subdomain làm tăng phạm vi lộ session ID nếu có subdomain kém an toàn; OIDC/SSO với session riêng thường có kiến trúc rõ ràng hơn.

### 8.4. Cấu hình cross-site cho flow đặc biệt

Trong một flow thực sự cần cookie được gửi cross-site:

```properties
server.servlet.session.cookie.same-site=none
server.servlet.session.cookie.secure=true
```

`SameSite=None` bắt buộc đi với `Secure` trong browser hiện đại. Cần tiếp tục xác định chính sách third-party, iframe, CSRF, CORS, Storage Access API/CHIPS (nếu có), và thử bằng browser cụ thể. **Không nên chọn None chỉ vì frontend và backend nằm ở hai subdomain khác nhau**: hai host đó có thể cross-origin nhưng vẫn same-site.

## 9. Ví dụ Java 17+ có thể chạy: form login và cookie scope

### 9.1. Phụ thuộc

Tạo dự án Spring Boot 3.x, Java 17+ bằng Spring Initializr hoặc công cụ xây dựng phù hợp. Trong file `build.gradle` đã khai báo plugin Spring Boot và repositories, phần `dependencies`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Đây chỉ là **khối phụ thuộc**, không phải toàn bộ script Gradle. Ví dụ cần Spring MVC, Security, JUnit Jupiter và MockMvc; không cần database.

### 9.2. Mã ứng dụng đầy đủ

Tạo **`src/main/java/demo/DemoApplication.java`**:

```java
package demo;

import java.time.Duration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

@Configuration
class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("alice-pass"))
                        .roles("USER")
                        .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public", "/cookie-demo")
                                .permitAll()
                        .anyRequest().authenticated())
                .formLogin(form -> form
                        .defaultSuccessUrl("/profile", true)
                        .permitAll())
                .logout(logout -> logout
                        .logoutSuccessUrl("/public")
                        .permitAll())
                .build();
    }
}

@RestController
class DemoController {

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/profile")
    String profile(Authentication authentication) {
        return "hello " + authentication.getName();
    }

    @GetMapping("/cookie-demo")
    ResponseEntity<String> demoCookie() {
        // Cookie minh hoa, KHONG chua session ID/token/PII.
        ResponseCookie cookie =
                ResponseCookie.from("__Host-DEMO_PREF", "ok")
                        .path("/")
                        .secure(true)
                        .httpOnly(true)
                        .sameSite("Lax")
                        .maxAge(Duration.ofMinutes(10))
                        .build();

        return ResponseEntity.ok()
                .header(HttpHeaders.SET_COOKIE, cookie.toString())
                .body("cookie-preview");
    }
}
```

**Điểm phân tách phải hiểu đúng:**

- `@SpringBootApplication` tạo ứng dụng Servlet, scan `SecurityConfig` và `DemoController`.
- `formLogin(...)` và `UserDetailsService` tạo luồng đăng nhập thật: trang login mặc định, POST login xử lý username/password, authentication thành công lưu `SecurityContext` trong session theo cơ chế framework.
- `server.servlet.session.cookie.*` trong file properties điều khiển **cookie của Servlet HttpSession**, không phải một dòng code trong controller.
- `ResponseCookie` trong `demoCookie()` tạo **một cookie minh họa riêng** tên `__Host-DEMO_PREF`, giá trị `ok` không nhạy cảm, để kiểm tra `Set-Cookie` trực tiếp qua MockMvc. **Cookie này không đăng nhập người dùng, không liên quan session cookie `__Host-SESSION`**.
- `.logout(...)` cấu hình success URL; Spring Security xử lý logout, invalidation session và security context theo thiết lập chuẩn. Với CSRF được bật, logout cần POST có CSRF token; không tạo GET thay đổi trạng thái trong demo.
- `Secure=true` ở cookie demo nghĩa là trình duyệt cần bối cảnh bảo mật để chấp nhận/gửi theo chính sách; MockMvc chỉ thấy header từ server và **không mô phỏng cookie jar của browser**.
- Không có `csrf.disable()`. Một endpoint public theo `permitAll` vẫn cần xử lý CSRF thích hợp nếu có unsafe method, bởi `permitAll` không có nghĩa bỏ qua toàn bộ các filter.

**Đặc điểm runnable:** chỉ có lớp `public DemoApplication`, cùng tên file; `SecurityConfig` và `DemoController` là top-level package-private trong package `demo`. Các import và type sử dụng tương thích Java 17+/Spring Boot 3.x/Spring Security 6.x.

### 9.3. Kiểm thử bằng MockMvc

Tạo **`src/test/java/demo/CookiePolicyTest.java`**:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.hamcrest.Matchers.allOf;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CookiePolicyTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    Environment env;

    @Test
    void productionSessionCookiePolicyIsExplicit() {
        assertThat(env.getProperty(
                "server.servlet.session.cookie.name"))
                .isEqualTo("__Host-SESSION");
        assertThat(env.getProperty(
                "server.servlet.session.cookie.path"))
                .isEqualTo("/");
        assertThat(env.getProperty(
                "server.servlet.session.cookie.secure"))
                .isEqualTo("true");
        assertThat(env.getProperty(
                "server.servlet.session.cookie.http-only"))
                .isEqualTo("true");
        assertThat(env.getProperty(
                "server.servlet.session.cookie.same-site"))
                .isEqualToIgnoringCase("lax");
        assertThat(env.getProperty(
                "server.servlet.session.cookie.domain")).isNull();
    }

    @Test
    void explicitCookieResponseHasSecurityAttributes()
            throws Exception {
        mvc.perform(get("/cookie-demo"))
                .andExpect(status().isOk())
                .andExpect(content().string("cookie-preview"))
                .andExpect(header().string(
                        HttpHeaders.SET_COOKIE,
                        allOf(
                                containsString("__Host-DEMO_PREF=ok"),
                                containsString("Path=/"),
                                containsString("Secure"),
                                containsString("HttpOnly"),
                                containsString("SameSite=Lax"))));
    }

    @Test
    void anonymousUserIsSentToLoginPage() throws Exception {
        mvc.perform(get("/profile"))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().string(
                        "Location", containsString("/login")));
    }

    @Test
    void successfulLoginProducesReusableSessionInMockMvc()
            throws Exception {

        MvcResult login = mvc.perform(formLogin()
                        .user("alice")
                        .password("alice-pass"))
                .andExpect(status().isFound())
                .andExpect(redirectedUrl("/profile"))
                .andExpect(authenticated().withUsername("alice"))
                .andReturn();

        MockHttpSession session = (MockHttpSession)
                login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/profile").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("hello alice"));
    }

    @Test
    void wrongPasswordDoesNotCreateAuthenticatedLogin()
            throws Exception {
        mvc.perform(formLogin()
                        .user("alice")
                        .password("wrong-password"))
                .andExpect(status().isFound())
                .andExpect(redirectedUrl("/login?error"))
                .andExpect(unauthenticated());
    }

    @Test
    void postLogoutWithoutCsrfIsRejected()
            throws Exception {

        MvcResult login = mvc.perform(formLogin()
                        .user("alice")
                        .password("alice-pass"))
                .andReturn();

        MockHttpSession session = (MockHttpSession)
                login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(post("/logout").session(session))
                .andExpect(status().isForbidden());
    }
}
```

**Phân loại bằng chứng từ tests:**

- `productionSessionCookiePolicyIsExplicit` kiểm tra **file cấu hình đang được tải** ở profile mặc định, không chứng minh browser đã nhận cookie. Không chạy class này dưới profile `local` vì khi ấy giá trị cookie cố ý khác; viết class/profiles test riêng nếu ứng dụng có nhiều môi trường.
- `explicitCookieResponseHasSecurityAttributes` kiểm tra header `Set-Cookie` của **cookie demo được controller tạo bằng `ResponseCookie`**. Đây không phải kiểm tra Set-Cookie của session do Tomcat/Jetty/Undertow phát hành.
- `successfulLoginProducesReusableSessionInMockMvc` chứng minh session authentication tồn tại trong luồng test và được dùng ở request thứ hai; **MockMvc không mô phỏng đầy đủ cách browser lưu/từ chối session cookie theo Secure/Domain/Path/SameSite**.
- `postLogoutWithoutCsrfIsRejected` chứng minh request thay đổi trạng thái cần CSRF trong cấu hình này; nó không thể được sửa đúng bằng việc “tắt CSRF vì SameSite=Lax”.

Chạy các tests:

```bash
./gradlew test
./gradlew test --tests demo.CookiePolicyTest
```

Trên Windows:

```powershell
.\gradlew.bat test --tests demo.CookiePolicyTest
```

**Không khẳng định có chuỗi stdout cố định:** nếu test pass, Gradle/JUnit sẽ thông báo theo phiên bản/cấu hình. Khi áp dụng vào dự án thật, cần bổ sung test có embedded server hoặc browser automation để quan sát session `Set-Cookie` và browser policy, không chỉ unit/integration ở MockMvc.

## 10. Kiểm tra bằng DevTools và HTTPS thực tế

### Bước 1 — Xác định URL và lớp kết nối thực

Xác minh browser mở `https://app.example.com` hay `http://localhost:8080`; backend có đứng sau TLS-terminating proxy không? Nhớ rằng **cookie Secure xét URL/kết nối của browser**, còn ứng dụng có thể thấy HTTP giữa proxy và Java.

Không đoán rằng ứng dụng đang HTTPS chỉ vì load balancer có TLS; kiểm tra browser address bar, redirect, reverse proxy và response headers.

### Bước 2 — Xem response Set-Cookie

Trong DevTools → Network, chọn response đăng nhập hoặc response tạo session và xem `Set-Cookie`. Kiểm tra các thuộc tính:

```http
Set-Cookie: __Host-SESSION=<session-id>; Path=/; Secure; HttpOnly; SameSite=Lax
```

Dòng trên là **hình thức mong đợi**, không phải một giá trị session thật. Đừng copy nguyên session ID vào ticket, ảnh chụp, Slack, log hoặc bài báo lỗi. Trình duyệt có thể đánh dấu cookie bị chặn với lý do như sai Domain, thiếu Secure với SameSite=None, vi phạm prefix, third-party policy hoặc scheme.

### Bước 3 — Xem cookie jar và request Cookie

Trong DevTools → Application/Storage → Cookies, xem host, path, Secure, HttpOnly, SameSite, ngày hết hạn và partition key nếu có. Trên request kế tiếp `/profile`, xem browser **có gửi Cookie** hay không. Nếu Set-Cookie xuất hiện nhưng request kế tiếp không gửi cookie, vấn đề thường là phạm vi hoặc browser policy; nếu browser gửi cookie nhưng server vẫn redirect login, điều tra session store, invalidation, timeout và phân tích Spring Security.

### Bước 4 — So sánh trong cùng host và khác subdomain

Với host-only cookie do `app.example.com` phát, mở request tới `api.example.com` và xác nhận cookie của app **không được gửi**. Nếu hệ thống cố ý có domain cookie `example.com`, kiểm tra browser gửi cookie đến cả hai host khi SameSite/Secure/Path hợp lệ, nhưng vẫn phải xem hai backend **có nhận cùng session ID hay không**.

**Không sử dụng chung session secret chỉ để vượt CORS**. Nếu client cross-origin gọi API, kiểm tra từng điều kiện: scope cookie, `credentials:"include"`, response CORS hợp lệ và Spring Security authorization. Sự cố nào cũng phải có evidence từ Network và server logs đã redaction.

### Bước 5 — Xác minh hoạt động logout và rotation

Đăng nhập, ghi nhận cookie name/phạm vi **không ghi giá trị session ID**; logout bằng POST hợp lệ với CSRF rồi kiểm tra browser/session server. Thử quay lại endpoint private; nếu session invalid, cần xác thực lại. Session fixation protection/rotation của Spring Security khi login cũng cần test trong hệ thống thực nếu có session management tùy biến.

Nếu vừa thay Domain hoặc Path, có thể tồn tại cookie “di sản” trùng tên ở phạm vi cũ. Phải có kế hoạch xóa chúng chính xác theo name/domain/path và bảo đảm session store không còn chấp nhận session đã bị revoke.

### Bước 6 — Kiểm tra chính sách browser khác nhau

Thử Chrome/Edge/Firefox/Safari với chế độ private/strict privacy khi cần. Third-party cookies và iframe storage có khác biệt lớn. Một test trong server hoặc một browser không bảo đảm flow hoạt động trên mọi browser. Khi dùng iframe, có thể cần redesign auth flow thay vì cố nới SameSite vô hạn.

### Bước 7 — Công cụ CLI

Với HTTPS thật và endpoint sẵn sàng:

```bash
# Khong dung -k tren production; chi theo doi Set-Cookie.
curl -i https://app.example.com/login

# Chi mo ta cach luu cookie; file jar co the CHUA SECRET.
# Han che quyen doc file va xoa sau khi test.
curl -c cookie-jar.txt -b cookie-jar.txt \
  https://app.example.com/profile
```

`curl` giúp quan sát HTTP headers và lưu cookie jar cho thử nghiệm, **nhưng không mô phỏng chính sách browser `SameSite`/CORS/third-party** giống Chrome hay Safari. Không lưu cookie jar của phiên production vào thư mục share/git; với ứng dụng nhạy cảm, ưu tiên browser DevTools và test account riêng.

## 11. Khi đi qua reverse proxy, ingress và nhiều instance

### 11.1. TLS termination

Mô hình phổ biến:

```text
Browser --HTTPS--> Reverse Proxy / Load Balancer
                   |
                   +--HTTP (private network)--> Spring Boot
```

Ứng dụng phải phát cookie có `Secure` bởi browser sẽ gửi/nhận ở HTTPS. Trong cấu hình `application.properties` của bài, đặt `server.servlet.session.cookie.secure=true` để không vô tình phụ thuộc vào scheme mà Servlet request nhìn thấy.

Đồng thời cần xem redirect login, absolute URL, issuer/callback và cookie path. Nếu ứng dụng sinh `Location: http://...` sai khi browser đang HTTPS, proxy forward headers hoặc ứng dụng nhận diện scheme chưa đúng. Có thể cần `server.forward-headers-strategy=framework` hoặc `native` theo hạ tầng, **chỉ khi gateway tin cậy đã loại bỏ/thay thế các `Forwarded`/`X-Forwarded-*` do client bên ngoài tự khai**. Chấp nhận thẳng forwarded headers từ Internet có thể dẫn đến Host/scheme spoofing và redirect sai.

### 11.2. Nhiều instance và session store

Nếu app được scale ra nhiều Spring Boot instances, cookie sẽ đến đúng host nhưng một instance khác có thể **không biết session ID** nếu session state chỉ nằm ở bộ nhớ của instance cũ. Cần sticky sessions có cân nhắc hoặc một session store dùng chung (ví dụ Spring Session + Redis/JDBC tùy thiết kế), vòng đời và key rotation nhất quán.

**Phân biệt rõ:** thay `Domain=example.com` không giải quyết session store khác nhau; chia sẻ session store cũng không thay thế bảo mật đường truyền hoặc quyền truy cập từng ứng dụng.

### 11.3. Context path thay đổi

Khi chuyển từ `/` sang `/portal`, cookie Path có thể cần được điều chỉnh nếu muốn giới hạn gửi cookie; nhưng dùng `__Host-` buộc `Path=/`. Không cố đặt `__Host-SESSION` và `Path=/portal` cùng lúc. Nếu yêu cầu path hẹp quan trọng hơn prefix, dùng tên cookie hợp lệ khác và đánh giá rủi ro khi các app cùng host.

## 12. Chẩn đoán những lỗi cookie phổ biến

| Hiện tượng | Các nguyên nhân nên kiểm tra | Cách xác minh |
| --- | --- | --- |
| Đăng nhập xong lại bị đưa tới login | Cookie bị browser từ chối hoặc không gửi, session store mất, invalid session | Network response `Set-Cookie`, request `Cookie`, server session |
| Cookie bị từ chối ngay khi nhận | `SameSite=None` thiếu `Secure`; prefix `__Host-` sai; Domain không hợp lệ | DevTools Issues/Cookies rejection reason |
| HTTPS production nhưng cookie thiếu Secure | Cấu hình mặc định/proxy scheme sai | Xem Set-Cookie ở browser; đặt Secure rõ ràng |
| `/app` gửi cookie, `/api` không gửi | `Path=/app` giới hạn phạm vi | So sánh URL path và cookie Path |
| `app.example.com` có session nhưng `api.example.com` không thấy cookie | Host-only cookie; browser không gửi sang sibling subdomain | Xem Domain trong DevTools, request headers |
| API có cookie nhưng frontend báo lỗi CORS | ACAO không khớp, thiếu ACAC, fetch credentials chưa đúng | Network CORS headers + console, không quy lỗi cho SameSite |
| CORS hợp lệ nhưng API trả 401 | Cookie không được gửi, session đã hết hạn hoặc cookie thuộc host khác | Inspect Cookie request và server authentication |
| Widget iframe mất đăng nhập | Third-party cookie policy, SameSite/partition/storage restriction | Browser-specific DevTools, test iframe thực |
| Đổi Domain/Path rồi logout vẫn thấy đăng nhập | Cookie cũ khác scope chưa bị xóa, session chưa invalid | Kiểm tra trùng tên trong cookie jar, session store |
| Cookie với `__Host-` + `Domain=example.com` không được lưu | Prefix yêu cầu **không có Domain** | Bỏ Domain hoặc đổi loại cookie/prefix |
| Cookie được gửi cho nhiều port cùng host | Cookie không được cô lập theo port | So sánh origin và cookie scope; tách host nếu cần cách ly |
| Không thấy Set-Cookie trong `fetch().headers` | `Set-Cookie` là forbidden response-header name của Fetch | Kiểm tra DevTools Network, không cố đọc qua JavaScript |
| Test MockMvc pass nhưng browser vẫn lỗi | MockMvc không mô phỏng đầy đủ cookie jar/policy | Browser E2E hoặc embedded server + TLS |
| CSRF 403 khi POST dù session đang hợp lệ | Có cookie không đồng nghĩa có CSRF token đúng | Kiểm tra CSRF token flow, không tắt CSRF tùy tiện |
| Server 401 dù request gửi cookie | Session ID không hợp lệ/hết hạn hoặc security context không có | Tra session store, logout, cookie name, app profile |

Không log giá trị thực của session cookie để điều tra; ghi mã tương quan request, endpoint category, HTTP status và event code đã được phê duyệt là cách an toàn hơn.

## 13. Lỗi thiết kế cần tránh

1. **Đặt Domain=example.com cho mọi cookie mặc định.** Đây là mở rộng phạm vi không cần thiết; một subdomain yếu có thể làm tăng rủi ro chiếm quyền phiên. Ưu tiên host-only.
2. **Xem Path=/admin là hàng rào phân quyền.** Path chỉ ảnh hưởng browser gửi cookie; URL admin vẫn cần `hasRole` và kiểm tra server-side.
3. **Chọn SameSite=None chỉ vì API nằm ở subdomain khác.** Hai subdomain dùng HTTPS thường vẫn same-site; kiểm tra Domain, fetch credentials, CORS trước khi thay đổi.
4. **Dùng __Host-SESSION với Domain hoặc Path không hợp lệ.** Browser có thể reject; tuân thủ Secure + Path=/ + no Domain.
5. **Bỏ HttpOnly để SPA đọc session ID.** Tạo API profile/CSRF flow thích hợp; không phơi session cookie qua JS.
6. **Tắt CSRF vì đã bật SameSite=Lax.** Browser có nhiều flow cùng site/cross-site; SameSite là defense in depth, không thay thế CSRF token.
7. **Coi CORS là bảo vệ chống mọi cross-site request.** CORS chủ yếu điều khiển việc JavaScript được đọc response; những request khác vẫn có thể gây side effect nếu server không kiểm tra.
8. **Bật Secure=true trên HTTP dev nhưng vẫn dùng __Host- prefix rồi kết luận app hỏng.** Dùng HTTPS local hoặc tên cookie riêng với profile local, tuyệt đối không deploy cấu hình giảm bảo vệ.
9. **Tin tưởng mọi X-Forwarded-Proto/Host do client gửi.** Cần cấu hình trusted proxy và sanitization.
10. **Giữ cookie persistent nhưng không quản lý session timeout/revocation.** Tuổi cookie và tuổi server session là hai khái niệm khác nhau.
11. **Cố gắng chia sẻ đăng nhập qua Domain mà không có common session store/protocol.** Browser có thể gửi cookie nhưng server khác không hiểu session.
12. **Bỏ qua chiến lược xóa cookie cũ sau khi đổi Domain/Path/name.** Dễ xuất hiện duplicate cookies và session khó gỡ.
13. **Dùng một kiểm thử MockMvc cho mọi browser.** Cần kiểm tra HTTP response từ real container và cookie policy trên browser thực.
14. **Log Set-Cookie/Cookie nguyên văn.** Session ID là credential; token trong log hoặc ticket có thể bị chiếm dụng.
15. **Để endpoint GET thực hiện thay đổi trạng thái quan trọng.** Chính sách SameSite và CSRF có thể giả định safe methods; action phải dùng method và CSRF phù hợp.

## 14. Checklist triển khai cookie theo môi trường

### Bảng quyết định rút gọn

| Kiến trúc | Scope gợi ý | SameSite gợi ý | Điều kiện bắt buộc |
| --- | --- | --- | --- |
| Web một host qua HTTPS | Không Domain, Path phù hợp (ưu tiên `/` nếu dùng `__Host-`) | `Lax` hoặc `Strict` theo UX | `Secure`, `HttpOnly`, CSRF, session expiry |
| Frontend và API ở hai subdomain cùng site | Ưu tiên session riêng và auth flow rõ; nếu cần Domain cookie phải review | Thường không cần `None` chỉ vì khác subdomain | CORS/credentials nếu cross-origin, data authorization, HTTPS |
| Iframe/third-party integration | Phạm vi tối thiểu có đánh giá riêng | Có thể cần `None; Secure` hoặc thiết kế lại login | Chính sách third-party, browser support, CSRF, tracing |
| Shared domain session | Domain được cho phép và hẹp nhất | Theo flow | Trust subdomains, shared session store, logout/migration |
| Localhost HTTP lab | Tên cookie dev không dùng tiền tố Secure/Host nếu Secure=false | `Lax` | Không deploy profile local |
| Reverse proxy TLS termination | Cookie browser thấy qua HTTPS, Secure=true | Theo web flow | Trusted proxy, sửa redirect và scope đúng |

### Checklist cuối cùng

1. Xác định **đúng host, scheme, port, context path** mà browser nhìn thấy.
2. Chọn host-only theo mặc định; chỉ đặt `Domain` khi thật sự cần chia sẻ tới subdomain và đã đánh giá rủi ro.
3. Chọn `Path` theo URL thực của ứng dụng; hiểu Path không phải security boundary.
4. Session cookie trong production có `Secure` + `HttpOnly`, thời hạn và session timeout hợp lý.
5. Chọn `SameSite` rõ ràng theo flow; `None` phải có `Secure` và vẫn chịu third-party blocking.
6. Nếu dùng `__Host-`, kiểm tra **no Domain, Path=/, Secure và HTTPS**.
7. Không đặt tên cookie trùng tùy tiện giữa nhiều app/host/path; có kế hoạch migration.
8. CSRF, XSS, authorization, session fixation và logout vẫn được bảo vệ độc lập.
9. Với cross-origin fetch, kiểm tra `credentials` và CORS response cho origin cụ thể.
10. Với proxy, kiểm tra forwarded headers chỉ từ trusted network, redirect URL và Secure.
11. Kiểm tra real `Set-Cookie`/`Cookie` trong Network và DevTools Application Storage mà không lộ session ID.
12. Kiểm thử hoạt động login/logout/timeout/rotation trên browser thực và khi scale nhiều instance.
13. Lưu ý khác biệt browser, iframe, CHIPS/partitioned, third-party policies theo use case.
14. Không log credentials; có event code và correlation ID cho hỗ trợ.

## 15. Câu hỏi tự luyện

1. `app.example.com` không đặt Domain, vậy `api.example.com` có nhận cookie ấy chỉ vì chung `example.com` không?
2. Nếu thêm `Domain=example.com`, hai backend có tự hiểu chung `HttpSession` không? Còn thiếu điều kiện kiến trúc nào?
3. Cookie `Path=/app` có được gửi tới `/application` không? Có nên dựa vào Path để bảo vệ `/admin` không?
4. `Secure` và `HttpOnly` giải quyết hai rủi ro khác nhau như thế nào? Hai thuộc tính này có loại bỏ XSS/CSRF không?
5. Vì sao `SameSite=Lax` không đồng nghĩa chỉ cho phép same-origin? `app.example.com` và `api.example.com` có quan hệ origin/site thế nào?
6. Cookie `SameSite=None` thiếu `Secure` thường sẽ ra sao trong browser hiện đại? Sau khi thêm Secure, third-party iframe có chắc hoạt động không?
7. Trong ứng dụng HTTPS production, tại sao cấu hình `__Host-SESSION; Path=/; Secure` phải **bỏ Domain**?
8. Nếu frontend cross-origin dùng `fetch` mà quên `credentials: "include"`, vấn đề có thể biểu hiện thế nào dù SameSite đúng?
9. Nếu server trả `Access-Control-Allow-Origin: *` cùng `Access-Control-Allow-Credentials: true`, browser có cho JavaScript đọc response credentialed không?
10. Vì sao lỗi CSRF 403 sau login không nên được sửa bằng `csrf.disable()` chỉ vì cookie có `SameSite=Lax`?
11. Tại sao test MockMvc không tự chứng minh cookie `Secure` được browser lưu và gửi đúng?
12. Nếu đổi `Path=/portal` thành `Path=/`, cookie cũ sẽ tự biến mất không? Cần làm gì với cookie cũ và server session?
13. Vì sao `server.servlet.session.timeout=20m` không đồng nghĩa `Max-Age=1200`?
14. Với HTTPS ở load balancer và HTTP tới Spring Boot, vì sao vẫn cần phát `Secure` và làm sạch forwarded headers?
15. Nếu user đăng nhập ở instance A rồi request chuyển sang instance B mà mất login, lỗi có nhất thiết do SameSite không?
16. Nếu muốn chia sẻ đăng nhập qua nhiều ứng dụng nhưng không muốn mở rộng Domain cookie, còn mô hình nào phù hợp hơn?

**Gợi ý:** (1) không, host-only; (2) cần auth/session store chung hoặc protocol SSO; (3) không, Path không phải authorization; (4) HTTPS delivery vs JS read; (5) site xét scheme/registrable domain, origin xét host/port; (6) None cần Secure nhưng browser vẫn có chính sách riêng; (7) điều kiện __Host-; (8) browser có thể không gửi credentials; (9) không; (10) SameSite chỉ defense in depth; (11) MockMvc thiếu browser cookie policy; (12) xóa đúng name/domain/path và invalidate session; (13) timeout server khác tuổi cookie; (14) browser dùng HTTPS và proxy headers cần trust; (15) cần xem session store/sticky session; (16) OIDC/SSO với session riêng.

## Nguồn tham khảo

- [Spring Boot 3.5 — Common Application Properties: server.servlet.session.cookie.*](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html)
- [Spring Boot 3.5 — Servlet Web Applications, SameSite Cookies](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html)
- [MDN — Set-Cookie: Domain, Path, Secure, HttpOnly, SameSite, prefixes](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie)
- [MDN — Using HTTP cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies)
- [MDN — Secure cookie configuration](https://developer.mozilla.org/en-US/docs/Web/Security/Practical_implementation_guides/Cookies)
- [MDN — Partitioned Cookies / CHIPS](https://developer.mozilla.org/en-US/docs/Web/Privacy/Guides/Third-party_cookies/Partitioned_cookies)
- [Spring Security 6.5 — CSRF Protection](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security 6.5 — MockMvc Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html)