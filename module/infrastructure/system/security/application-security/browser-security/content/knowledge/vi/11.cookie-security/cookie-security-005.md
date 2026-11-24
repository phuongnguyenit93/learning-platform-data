# Cookie tossing: chèn cookie từ subdomain và làm sai lệch trạng thái ứng dụng

> **Chương:** Cookie security  
> **Học phần:** SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

Cookie thường được xem như trạng thái mà máy chủ gửi cho trình duyệt rồi trình duyệt tự đính kèm vào request phù hợp. Tuy nhiên, một website có nhiều subdomain có thể gặp tình huống **một subdomain không đáng tin đặt cookie có phạm vi rộng**, khiến trình duyệt gửi cookie đó đến subdomain ứng dụng. Nếu cookie được đặt trùng tên với cookie hợp lệ, server có thể nhận nhiều giá trị cùng tên nhưng không biết giá trị nào đến từ phạm vi nào.

Kỹ thuật này thường được gọi là **cookie tossing** hoặc cookie injection. Nó có thể dẫn đến session fixation, sai lệch CSRF token, ghi đè tùy chọn bảo mật hoặc lỗi phân quyền nếu ứng dụng xử lý cookie trùng tên không nhất quán.

Điểm quan trọng: header `Cookie` chỉ mang các cặp tên/giá trị. Nó không kèm Domain, Path, Expires hay thông tin cho biết cookie nào là host-only. Vì vậy **server không thể dựa vào header Cookie để phân biệt nguồn gốc của hai cookie cùng tên**. Phòng vệ tốt nhất bắt đầu từ việc giới hạn phạm vi cookie và dùng prefix phù hợp, sau đó từ chối dữ liệu cookie trùng tên ở server.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích cookie host-only khác cookie có thuộc tính `Domain` như thế nào.
2. Mô tả cách một subdomain có thể đặt cookie cho parent domain và ảnh hưởng tới request của sibling subdomain.
3. Phân biệt cookie tossing, cookie shadowing và session fixation.
4. Giải thích vì sao hai cookie cùng tên có thể cùng xuất hiện trong header `Cookie` và vì sao parser first/last tạo ra rủi ro.
5. Sử dụng prefix `__Host-` cho session cookie và hiểu điều kiện browser áp dụng prefix.
6. Thiết kế server parser từ chối cookie nhạy cảm bị lặp, thu hồi session và xoay session ID sau xác thực.
7. Hiểu vì sao SameSite, HttpOnly và CORS không tự giải quyết cookie tossing giữa các subdomain cùng site.
8. Kiểm chứng duplicate cookie parsing bằng Node.js và DevTools trong môi trường thử nghiệm.

## 1. Phạm vi cookie: host-only và Domain

### 1.1 Cookie host-only

Nếu server gửi `Set-Cookie` mà **không có thuộc tính Domain**, browser tạo cookie host-only. Cookie chỉ được gửi đến đúng host đã đặt nó, theo Path và các điều kiện khác.

Ví dụ response từ `https://app.example.com`:

~~~http
Set-Cookie: session=RANDOM_VALUE; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Cookie này là host-only cho `app.example.com`. Nó không tự động được gửi đến `api.example.com` hoặc `blog.example.com`.

Đây là lựa chọn tốt cho session cookie khi chỉ một host cần sử dụng phiên đăng nhập. **Không thêm Domain chỉ để “cho tiện”** nếu các subdomain không thực sự cần chia sẻ cookie.

### 1.2 Cookie có Domain

Nếu server gửi:

~~~http
Set-Cookie: shared_pref=dark; Domain=example.com; Path=/; Secure; SameSite=Lax
~~~

browser có thể gửi cookie đến `example.com` và các subdomain phù hợp như:

- `app.example.com`
- `api.example.com`
- `blog.example.com`
- `tenant.example.com`

Cookie có `Domain=example.com` thường được gọi là domain cookie. Dấu chấm đầu như `Domain=.example.com` không tạo ra một phạm vi đặc biệt trong browser hiện đại; leading dot bị bỏ qua.

Server không thể đặt cookie cho một domain không phải domain hiện tại hoặc parent domain hợp lệ của host hiện tại. Browser cũng từ chối Domain là public suffix, ví dụ `com`, theo cơ chế public suffix protection.

### 1.3 So sánh host-only và Domain cookie

| Đặc điểm | Host-only | Có Domain |
|---|---|---|
| Cách tạo | Bỏ thuộc tính Domain | Gửi `Domain=example.com` |
| Host nhận cookie | Chỉ host đã đặt | Host đó và subdomain phù hợp |
| Chia sẻ giữa sibling subdomain | Không | Có |
| Rủi ro từ subdomain không đáng tin | Thấp hơn | Cao hơn vì subdomain có thể đặt cookie cho parent domain |
| Phù hợp với session riêng của ứng dụng | **Ưu tiên** | Chỉ khi kiến trúc thật sự cần chia sẻ |
| Header Cookie có chỉ ra loại này không? | Không | Không |

Cookie host-only không phải là một thuộc tính hiển thị trong request. Nó là trạng thái lưu trữ mà browser dùng để quyết định gửi cookie. Khi server nhận request, nó chỉ thấy tên và giá trị.

### 1.4 Domain cookie không bị giới hạn theo port

Cookie không được cô lập theo port giống origin. Hai ứng dụng chạy trên các port khác nhau của cùng hostname có thể chia sẻ cookie nếu Domain/Path và các điều kiện khác phù hợp.

Đây là khác biệt quan trọng giữa **origin** và **cookie scope**:

- Origin xét scheme, host và port.
- Cookie scope xét host/domain, path, Secure, SameSite và các chính sách khác.
- Cookie Domain không cho phép chia sẻ sang domain hoàn toàn khác, nhưng có thể mở rộng đến nhiều subdomain.
- Cookie Path là quy tắc gửi cookie, không phải ranh giới bảo mật đáng tin cậy giữa các ứng dụng.

## 2. Cookie tossing là gì?

### 2.1 Kịch bản sibling subdomain

Giả sử tổ chức có:

- `https://app.example.com`: ứng dụng chính, lưu session cookie tên `session`.
- `https://untrusted.example.com`: subdomain dành cho nội dung người dùng hoặc một ứng dụng ít tin cậy hơn.

Ứng dụng chính đặt cookie host-only:

~~~http
Set-Cookie: session=LEGIT_SESSION; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Nhưng subdomain không đáng tin có thể gửi response:

~~~http
Set-Cookie: session=ATTACKER_VALUE; Domain=example.com; Path=/; Secure; SameSite=Lax
~~~

Browser có thể lưu hai cookie cùng tên `session` ở các phạm vi khác nhau: một cookie host-only cho `app.example.com` và một domain cookie cho `example.com`.

Khi người dùng truy cập `app.example.com`, cả hai cookie có thể phù hợp với request và được gửi trong header:

~~~http
GET /account HTTP/1.1
Host: app.example.com
Cookie: session=ATTACKER_VALUE; session=LEGIT_SESSION
~~~

Thứ tự minh họa phụ thuộc thời điểm tạo và Path. Với các cookie cùng Path, quy tắc sắp xếp cookie của browser thường ưu tiên cookie được tạo sớm hơn; thứ tự thực tế phải kiểm chứng trên browser mục tiêu. Ứng dụng server không nên dựa vào thứ tự để xác định cookie nào đáng tin.

### 2.2 Vì sao server có thể chọn nhầm?

Header `Cookie` không mang theo thuộc tính `Domain` hay `Path`. Một middleware có thể lấy giá trị đầu tiên:

~~~js
const session = parseCookieHeader(req.headers.cookie).session;
~~~

Trong khi một thư viện khác lấy giá trị cuối cùng, hoặc trả về mảng. Nếu proxy, middleware xác thực và controller không thống nhất cách parse, cùng một request có thể được hiểu thành những session khác nhau.

Một số kết quả có thể xảy ra:

- Server chọn giá trị do attacker đặt thay vì session hợp lệ.
- Middleware kiểm tra một giá trị, controller sử dụng giá trị khác.
- Session lookup thất bại, người dùng bị logout hoặc ứng dụng rơi vào trạng thái không nhất quán.
- Nếu session ID do attacker kiểm soát được chấp nhận, ứng dụng có thể gặp **session fixation**.
- CSRF token trong cookie và token trong form/header có thể bị so sánh với giá trị khác nhau, gây lỗi xác thực hoặc làm yếu cơ chế bảo vệ nếu code xử lý duplicate không đúng.

Cookie tossing không tự động đồng nghĩa với chiếm quyền tài khoản. Tác động phụ thuộc cookie nào được ứng dụng sử dụng, server có chấp nhận giá trị do attacker chọn không và session lifecycle được thiết kế thế nào.

### 2.3 Sơ đồ luồng tấn công

~~~mermaid
sequenceDiagram
    participant V as Trình duyệt nạn nhân
    participant E as untrusted.example.com
    participant A as app.example.com
    V->>E: Truy cập subdomain ít tin cậy
    E-->>V: Set-Cookie: session=ATTACKER; Domain=example.com
    V->>A: Truy cập ứng dụng chính
    A-->>V: Set-Cookie: session=LEGIT; host-only
    V->>A: Request /account
    Note over V,A: Cookie header có thể chứa hai session cùng tên
    A->>A: Parser chọn first/last hoặc xử lý không nhất quán
    Note over A: Có thể dùng nhầm session nếu server không từ chối duplicate
~~~

## 3. Điều kiện và bề mặt tấn công

### 3.1 Khi nào cookie tossing có thể xảy ra?

Thông thường cần các điều kiện sau:

1. Ứng dụng có một cookie được gửi tới host mục tiêu.
2. Kẻ tấn công kiểm soát hoặc có thể phát response từ một sibling subdomain thuộc cùng parent domain.
3. Cookie của ứng dụng có tên và phạm vi cho phép cookie do attacker đặt cùng tên tồn tại đồng thời hoặc ảnh hưởng đến cookie hợp lệ.
4. Browser chấp nhận cookie do subdomain đặt và gửi nó tới host mục tiêu.
5. Server hoặc framework xử lý cookie trùng tên theo cách có thể bị lợi dụng.

Nguồn kiểm soát subdomain có thể đến từ:

- Subdomain cho phép người dùng tự host nội dung.
- Tenant subdomain có cấu hình tách biệt không đầy đủ.
- Dịch vụ cũ hoặc ứng dụng thử nghiệm còn DNS record.
- Dangling CNAME hoặc subdomain takeover.
- Ứng dụng bên thứ ba được đặt dưới subdomain của tổ chức.
- Một subdomain có XSS hoặc lỗi cho phép phản hồi HTTP tùy ý.

Không cần kiểm soát server chính để đặt domain cookie; chỉ cần khả năng trả response từ host con hợp lệ và browser chấp nhận thuộc tính Domain.

### 3.2 HTTPS và Secure không loại bỏ rủi ro sibling domain

Nếu attacker kiểm soát `https://untrusted.example.com`, họ có thể đặt cookie có `Secure` cho parent domain qua HTTPS. Vì vậy:

- `Secure` bảo vệ việc cookie chỉ được gửi qua kết nối an toàn; nó không giới hạn cookie vào một hostname cụ thể.
- `HttpOnly` ngăn JavaScript đọc cookie; nó không ngăn một server sibling gửi `Set-Cookie` cùng tên và Domain rộng.
- `SameSite=Lax` hoặc `Strict` không phải ranh giới bảo vệ giữa các sibling subdomain cùng site theo nghĩa schemeful same-site.
- HSTS giúp ép HTTPS cho domain trong phạm vi chính sách, nhưng không biến domain cookie thành host-only.
- CORS kiểm soát quyền đọc response của script; nó không ngăn browser lưu cookie từ response điều hướng hoặc request thông thường.

Do đó, phòng vệ cần bắt đầu từ **cookie scope** và **cách server xử lý duplicate**, không chỉ dựa vào các thuộc tính bảo mật khác.

### 3.3 Path không phải biện pháp cô lập

Một cookie có `Path=/admin` chỉ được gửi cho request có path phù hợp; điều đó không làm cookie trở nên an toàn trước script cùng host hoặc server sibling có quyền đặt cookie domain.

Không dùng Path như một ranh giới phân quyền giữa các ứng dụng cùng host. Nếu hai ứng dụng có mức tin cậy khác nhau, nên tách hostname/domain thay vì dựa vào Path.

## 4. Cookie tossing, shadowing và session fixation

Các thuật ngữ này liên quan nhưng không đồng nghĩa:

| Khái niệm | Ý nghĩa |
|---|---|
| **Cookie injection/tossing** | Kẻ tấn công làm browser lưu cookie mà họ kiểm soát, thường từ subdomain hoặc phạm vi Domain rộng |
| **Cookie shadowing** | Cookie do attacker đặt che khuất hoặc làm ứng dụng chọn nhầm cookie hợp lệ cùng tên, thường thông qua Domain/Path và thứ tự parse |
| **Cookie tossing qua Path** | Đặt cookie cùng tên ở Path khác để thay đổi thứ tự/giá trị gửi đến endpoint có path phù hợp |
| **Session fixation** | Attacker khiến nạn nhân sử dụng session ID mà attacker đã biết hoặc kiểm soát, rồi tận dụng việc nạn nhân xác thực trên session đó |
| **Session hijacking** | Attacker lấy được session ID/token của người dùng hợp lệ và sử dụng phiên đó |

Cookie tossing có thể là bước hỗ trợ session fixation hoặc shadowing. Nhưng nếu server luôn tạo session ID mới sau đăng nhập, từ chối session ID không hợp lệ và từ chối duplicate cookie nhạy cảm, tác động sẽ giảm đáng kể.

## 5. Cookie prefix và cách thu hẹp phạm vi

### 5.1 Prefix `__Host-`

Với cookie nhạy cảm như session ID, browser hiện đại hỗ trợ prefix `__Host-`. Để cookie có prefix này được chấp nhận, cookie cần:

- Được đặt từ secure context/secure origin theo quy tắc browser.
- Có thuộc tính `Secure`.
- Có `Path=/`.
- **Không có thuộc tính Domain**.

Ví dụ:

~~~http
Set-Cookie: __Host-session=RANDOM_SESSION_ID; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Một sibling subdomain cố đặt:

~~~http
Set-Cookie: __Host-session=ATTACKER_VALUE; Domain=example.com; Path=/; Secure; SameSite=Lax
~~~

sẽ bị browser hỗ trợ prefix từ chối vì cookie `__Host-` không được có Domain. Nếu sibling bỏ Domain, cookie trở thành host-only cho chính sibling đó và không được gửi đến app host.

Đây là lớp phòng vệ rất hữu ích cho session cookie. Tuy nhiên, cần kiểm tra browser mục tiêu và không dựa vào prefix thay cho xác thực/authorization phía server.

### 5.2 Prefix `__Secure-` không tương đương __Host-

`__Secure-` yêu cầu cookie được đặt trong ngữ cảnh secure và có `Secure`, nhưng **không bắt buộc bỏ Domain** hoặc đặt Path=/.

Vì vậy:

~~~http
Set-Cookie: __Secure-session=VALUE; Domain=example.com; Path=/; Secure; HttpOnly
~~~

vẫn có thể là domain cookie trong browser hỗ trợ prefix. Nếu mục tiêu là chống sibling subdomain đặt cookie cùng tên cho parent domain, `__Secure-` không cung cấp ràng buộc host-only như `__Host-`.

### 5.3 Bảng so sánh prefix

| Prefix | Secure bắt buộc | Path=/ bắt buộc | Domain bị cấm | Ý nghĩa |
|---|---:|---:|---:|---|
| Không prefix | Không | Không | Không | Không có ràng buộc prefix |
| `__Secure-` | Có | Không | Không | Cookie phải được đặt từ secure context và có Secure |
| `__Host-` | Có | **Có** | **Có** | Buộc cookie host-only ở host đã đặt |

Prefix là một cơ chế bảo vệ ở browser. Server nên vẫn dùng tên cookie có ý nghĩa, validate session và từ chối duplicate cho các cookie nhạy cảm.

## 6. Phòng vệ ở phía server

### 6.1 Từ chối cookie nhạy cảm nếu xuất hiện nhiều lần

Vì server không biết cookie nào đến từ host-only hay Domain scope, một chính sách an toàn là **từ chối request nếu cookie nhạy cảm xuất hiện nhiều hơn một lần**.

Ví dụ parser đơn giản cho lab Node.js:

~~~js
function getUniqueCookie(rawHeader, expectedName) {
  const matches = [];

  for (const part of (rawHeader || '').split(';')) {
    const item = part.trim();
    const separator = item.indexOf('=');
    if (separator < 0) continue;

    const name = item.slice(0, separator).trim();
    const value = item.slice(separator + 1).trim();

    if (name === expectedName) {
      matches.push(value);
    }
  }

  if (matches.length !== 1) {
    throw new Error('Expected exactly one ' + expectedName + ' cookie');
  }

  return matches[0];
}
~~~

Đây là parser minh họa cho cookie value đơn giản. Production nên dùng thư viện cookie đã được kiểm tra và có chính sách duplicate rõ ràng; không tự decode cookie value theo nhiều lần hoặc tự diễn giải dấu phân cách không đúng grammar.

Sử dụng:

~~~js
try {
  const sessionId = getUniqueCookie(
    req.headers.cookie,
    '__Host-session'
  );
  const session = await sessionStore.findValid(sessionId);
  // Tiếp tục xác thực và phân quyền.
} catch (error) {
  res.writeHead(400, { 'Cache-Control': 'no-store' });
  res.end('Invalid cookie state');
}
~~~

Tùy ứng dụng, duplicate cookie nhạy cảm có thể được xử lý bằng 400, xóa phiên và yêu cầu đăng nhập lại, hoặc một quy trình khôi phục an toàn. **Không âm thầm chọn first/last** khi cookie có ý nghĩa xác thực.

### 6.2 Dùng một parser nhất quán trong toàn hệ thống

Đảm bảo reverse proxy, framework middleware, session library và controller không parse cùng header theo các quy tắc khác nhau.

- Không để middleware xác thực lấy giá trị đầu nhưng controller lấy giá trị cuối.
- Không parse cookie thủ công ở một tầng và dùng thư viện khác ở tầng tiếp theo.
- Từ chối duplicate của cookie xác thực, CSRF token hoặc cookie quyết định tenant/role.
- Không lấy quyền hoặc vai trò từ cookie tùy chọn do client kiểm soát mà không có xác thực/ủy quyền server.
- Log sự kiện duplicate ở mức an toàn, nhưng không ghi session ID/token đầy đủ vào log.

### 6.3 Xoay session ID sau đăng nhập và thay đổi quyền

Ngay cả khi attacker tìm cách đưa session ID do họ biết vào browser, ứng dụng nên tạo session ID mới sau khi người dùng đăng nhập hoặc nâng quyền:

1. Nhận session trước đăng nhập nếu có.
2. Xác thực thông tin người dùng.
3. Hủy hoặc vô hiệu hóa session ID cũ.
4. Sinh session ID ngẫu nhiên mới, khó đoán.
5. Gắn session mới với danh tính/quyền phía server.
6. Gửi lại cookie host-only có prefix `__Host-`.

Đây là phòng vệ quan trọng trước session fixation. Không chấp nhận một session ID do client tự chọn như một phiên đã xác thực.

### 6.4 Giới hạn Domain và tách miền cho nội dung không đáng tin

Nếu một phần hệ thống cho người dùng upload HTML, chạy JavaScript hoặc cấu hình tenant, không nên đặt nó dưới một subdomain có quyền đặt cookie cho parent domain của ứng dụng chính.

Ví dụ kiến trúc:

- Ứng dụng nhạy cảm: `app.example.com`.
- Nội dung người dùng: `usercontent.example.net` hoặc một domain tách biệt có kiểm soát.
- API xác thực/session: chỉ chấp nhận cookie host-only của host API/app được chỉ định.
- Không chia sẻ Domain cookie rộng giữa các vùng có mức độ tin cậy khác nhau.

Chỉ tạo subdomain riêng dưới cùng parent domain vẫn có thể là same-site và vẫn có thể đặt Domain cookie cho parent. Nếu cần ranh giới mạnh hơn, hãy dùng **registrable domain khác** và thiết kế CORS/cookie riêng.

### 6.5 Thu hồi cookie Domain cũ

Nếu hệ thống trước đây từng phát cookie rộng:

~~~http
Set-Cookie: session=old-value; Domain=example.com; Path=/; Max-Age=86400
~~~

Khi chuyển sang host-only hoặc `__Host-session`, hãy có kế hoạch loại bỏ cookie cũ:

~~~http
Set-Cookie: session=; Domain=example.com; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax
~~~

Nếu cookie cũ tồn tại ở nhiều Path hoặc Domain scope, cần gửi lệnh xóa tương ứng cho từng scope đã sử dụng. Không thể xóa một cookie ở mọi phạm vi chỉ bằng một header không khớp scope.

Trong thời gian chuyển đổi, server cần phát hiện duplicate, không chấp nhận giá trị không rõ nguồn và yêu cầu tạo session mới. Sau khi migration, bỏ hẳn tên cookie cũ nếu có thể.

## 7. SameSite, HttpOnly, Secure và CORS có giới hạn gì?

| Cơ chế | Giúp gì? | Không giải quyết được gì trong cookie tossing |
|---|---|---|
| `Secure` | Cookie chỉ được gửi qua kết nối an toàn theo quy tắc browser | Subdomain attacker chạy HTTPS vẫn có thể đặt Domain cookie Secure |
| `HttpOnly` | Script không đọc trực tiếp cookie bằng document.cookie | Server sibling vẫn có thể gửi Set-Cookie; browser vẫn có thể gửi cookie |
| `SameSite=Lax/Strict` | Hạn chế một số request cookie cross-site | Sibling subdomain thường cùng site, nên không phải ranh giới chống cookie tossing |
| CORS | Kiểm soát script cross-origin đọc response | Không ngăn browser lưu Set-Cookie từ response phù hợp hoặc gửi cookie trong navigation |
| CSP | Hạn chế nguồn script/kết nối/nhúng theo chỉ thị | Không thu hẹp Domain cookie |
| HSTS | Ép HTTPS trong phạm vi policy đã biết | Không biến domain cookie thành host-only |
| `__Host-` | Cấm Domain, yêu cầu Secure và Path=/ | Không thay thế kiểm tra session và xử lý duplicate ở server |

### 7.1 Same-site không có nghĩa same-origin

`https://app.example.com` và `https://untrusted.example.com` là hai origin khác nhau nhưng thường cùng site theo schemeful same-site. Do đó, request từ sibling có thể được xem là same-site đối với cookie SameSite.

Đây là lý do không thể dùng SameSite như ranh giới cô lập giữa các subdomain. Nếu một subdomain không đáng tin có thể chạy nội dung chủ động, hãy tránh chia sẻ cookie parent-domain và cân nhắc tách registrable domain.

### 7.2 HttpOnly không ngăn cookie injection từ server khác

HttpOnly bảo vệ khả năng đọc cookie qua JavaScript trong document. Nó không nói rằng chỉ một host được quyền đặt cookie cùng tên. Server của sibling vẫn có thể gửi Set-Cookie với Domain phù hợp; browser sẽ tự quản lý và có thể gửi cookie đó đến host mục tiêu.

### 7.3 CORS không quyết định cookie scope

CORS không xác định cookie nào được lưu hay cookie nào phù hợp với host/path. Nó kiểm soát quyền đọc response của JavaScript trong một số cross-origin request.

Nếu một trang sibling điều hướng top-level đến endpoint, response Set-Cookie vẫn có thể được browser xử lý theo chính sách cookie và ngữ cảnh. Không coi CORS là lớp phòng vệ cookie tossing.

## 8. Thực hành: nhận diện duplicate Cookie header bằng Node.js

Bài lab dưới đây chỉ kiểm tra cách server nhận và phân tích header. Nó không tự khai thác website bên ngoài, không cần package và dùng dữ liệu giả.

### 8.1 Tạo file `cookie-tossing-lab.mjs`

~~~js
import { createServer } from 'node:http';

function findCookieValues(rawHeader, wantedName) {
  const values = [];

  for (const part of (rawHeader || '').split(';')) {
    const item = part.trim();
    const index = item.indexOf('=');
    if (index < 0) continue;

    const name = item.slice(0, index).trim();
    const value = item.slice(index + 1).trim();

    if (name === wantedName) values.push(value);
  }

  return values;
}

createServer((req, res) => {
  if (req.url === '/inspect') {
    const raw = req.headers.cookie || '';
    const values = findCookieValues(raw, 'session');

    const result = {
      rawCookieHeader: raw,
      duplicateCount: values.length,
      firstValue: values[0] ?? null,
      lastValue: values.at(-1) ?? null,
      safeDecision: values.length === 1
        ? 'Accept exactly one value'
        : 'Reject ambiguous cookie state'
    };

    res.writeHead(200, {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store'
    });
    return res.end(JSON.stringify(result, null, 2));
  }

  res.writeHead(200, {
    'Content-Type': 'text/html; charset=utf-8',
    'Cache-Control': 'no-store'
  });
  res.end(
    '<h1>Cookie tossing lab</h1>' +
    '<p>Gửi một request demo có cookie trùng tên.</p>' +
    '<pre>curl -H "Cookie: session=attacker; session=legit" ' +
    'http://localhost:3000/inspect</pre>'
  );
}).listen(3000, 'localhost', () => {
  console.log('Lab: http://localhost:3000');
});
~~~

### 8.2 Chạy lab

~~~bash
node cookie-tossing-lab.mjs
~~~

Trong terminal khác:

~~~bash
curl -H "Cookie: session=attacker; session=legit" http://localhost:3000/inspect
~~~

Kết quả JSON cho thấy server nhận hai giá trị cùng tên. Hàm minh họa báo trạng thái **Reject ambiguous cookie state** thay vì chọn first/last.

### 8.3 So sánh parser first/last và parser từ chối duplicate

| Cookie header | Parser lấy first | Parser lấy last | Parser an toàn cho session |
|---|---|---|---|
| `session=legit` | `legit` | `legit` | Chấp nhận đúng một giá trị |
| `session=attacker; session=legit` | `attacker` | `legit` | Từ chối |
| `session=legit; session=attacker` | `legit` | `attacker` | Từ chối |
| Không có session | Không có | Không có | Yêu cầu xác thực/đăng nhập |

**Giới hạn của lab:** curl chủ động tạo header để minh họa parser ambiguity. Nó không chứng minh browser sẽ gửi thứ tự cookie cụ thể hoặc cookie store thực tế đã tạo được hai cookie cùng tên. Muốn kiểm tra hành vi browser, cần môi trường thử nghiệm có hai subdomain thuộc cùng một domain do mình kiểm soát, quan sát Application/Storage và Network, không dùng tài khoản thật.

### 8.4 Thí nghiệm browser tùy chọn với hai subdomain kiểm soát

Trong môi trường lab có DNS/hosts và HTTPS phù hợp, có thể triển khai hai host:

- `app.example.test`: đặt cookie host-only `session=legit`.
- `untrusted.example.test`: đặt cookie `session=attacker; Domain=example.test`.

Thứ tự thử:

1. Truy cập subdomain không đáng tin để tạo domain cookie trước.
2. Truy cập app để tạo host-only cookie cùng tên.
3. Mở DevTools → Application/Storage → Cookies, quan sát các bản ghi cùng tên nhưng domain/scope khác nhau.
4. Tải endpoint kiểm tra cookie ở app và xem raw request header trong Network.
5. Đổi tên cookie app thành `__Host-session`, đặt Secure và Path=/, bỏ Domain.
6. Thử lại từ sibling: browser hỗ trợ prefix phải từ chối domain cookie vi phạm quy tắc `__Host-`.

Thí nghiệm này cần host mapping và HTTPS local phù hợp. Không thay đổi DNS hoặc cookie của domain production.

## 9. Chẩn đoán và xử lý sự cố

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Server nhận hai cookie cùng tên | Host-only và Domain cookie cùng tồn tại; hoặc Path khác nhau | Từ chối duplicate cookie nhạy cảm; kiểm tra scope đã cấp |
| Middleware và controller thấy session khác nhau | Parser first/last hoặc thư viện khác nhau | Chuẩn hóa một parser và một chính sách duplicate |
| Logout nhưng cookie vẫn xuất hiện | Chỉ xóa một Domain/Path scope | Xóa đúng name, Domain và Path của từng cookie |
| Cookie session bị thay đổi sau khi ghé subdomain | Subdomain đặt Domain cookie cùng tên | Thu hồi session, chuyển sang `__Host-` và xử lý duplicate |
| Cookie `__Host-session` bị browser từ chối | Thiếu Secure, Path không phải /, hoặc có Domain | Tuân thủ đầy đủ yêu cầu prefix |
| Cookie không được gửi ở request dự kiến | Host/domain/path/Secure/SameSite/credentials không phù hợp | Kiểm tra request context và thuộc tính cookie |
| CORS được cấu hình nhưng duplicate cookie vẫn xuất hiện | CORS không kiểm soát cookie scope | Sửa cookie scope và server parser |
| SameSite=Lax không ngăn sibling domain | Hai subdomain cùng site | Không dùng SameSite như ranh giới giữa sibling |
| Server chấp nhận session do client chọn | Thiếu session rotation hoặc kiểm tra server | Tạo session mới sau login, revoke session cũ |

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Server đặt cookie cho `app.example.com` nhưng bỏ thuộc tính Domain. Cookie có được gửi tới `api.example.com` không?

**Đáp án:** Không theo phạm vi host-only. Cookie chỉ áp dụng cho host đã đặt nó, cùng các điều kiện Path/Secure/SameSite.

**Câu 2.** Subdomain `untrusted.example.com` có thể đặt cookie cho `app.example.com` bằng cách nào?

**Đáp án:** Nó có thể trả `Set-Cookie` với `Domain=example.com`, nếu domain hợp lệ và browser chấp nhận. Cookie đó có thể được gửi tới app host.

**Câu 3.** Vì sao server không thể biết một cookie trùng tên đến từ host-only hay Domain cookie chỉ bằng header Cookie?

**Đáp án:** Header Cookie chỉ chứa cặp name/value; Domain, Path và metadata lưu trữ không được gửi trong request header.

**Câu 4.** Cookie `__Secure-session` có ngăn sibling subdomain đặt cookie Domain cùng tên không?

**Đáp án:** Không. `__Secure-` yêu cầu Secure nhưng vẫn có thể dùng Domain. `__Host-` mới cấm Domain và yêu cầu Path=/ cùng Secure.

**Câu 5.** Hai subdomain HTTPS khác origin nhưng cùng site. SameSite=Lax có ngăn cookie được gửi giữa chúng không?

**Đáp án:** Không thể coi SameSite là ranh giới ngăn sibling. SameSite xét site, không xét origin; hai subdomain cùng site thường vẫn là same-site.

**Câu 6.** HttpOnly có ngăn cookie tossing không?

**Đáp án:** Không. HttpOnly ngăn JavaScript đọc cookie, không ngăn server sibling gửi Set-Cookie với Domain phù hợp.

**Câu 7.** Middleware lấy cookie đầu tiên, controller lấy cookie cuối cùng. Rủi ro gì?

**Đáp án:** Các tầng có thể xác thực một session nhưng sử dụng session khác, dẫn tới lỗi logic hoặc bypass nếu cookie quyết định quyền. Nên từ chối duplicate cookie nhạy cảm.

**Câu 8.** Cookie session hợp lệ vẫn tồn tại nhưng session ID bị attacker biết. Chỉ đặt Max-Age ngắn có đủ không?

**Đáp án:** Không. Cần session rotation, revoke phía server, xác thực/ủy quyền và bảo vệ cookie scope; lifetime ngắn chỉ giảm một phần cửa sổ rủi ro.

**Câu 9.** CORS có ngăn sibling subdomain đặt cookie Domain parent không?

**Đáp án:** Không. CORS điều khiển quyền đọc response của script; cookie scope và xử lý Set-Cookie là cơ chế riêng.

**Câu 10.** Server nên làm gì khi nhận hai giá trị `__Host-session` trong cùng request?

**Đáp án:** Từ chối trạng thái cookie nhập nhằng, không chọn first/last. Ghi log sự kiện an toàn và yêu cầu phiên mới nếu cần.

## 11. Checklist phòng vệ cookie tossing

Trước khi triển khai hoặc rà soát cookie, hãy kiểm tra:

1. **Host-only mặc định:** bỏ Domain nếu cookie chỉ phục vụ một host.
2. **Session prefix:** dùng `__Host-` cho session cookie khi browser mục tiêu hỗ trợ.
3. **Thuộc tính bắt buộc:** Secure, HttpOnly, Path=/ và không Domain cho `__Host-`.
4. **Không tin sibling subdomain:** kiểm soát tenant hosting, upload, CNAME, subdomain takeover và ứng dụng bên thứ ba.
5. **Duplicate handling:** từ chối cookie nhạy cảm xuất hiện nhiều lần; không âm thầm chọn first/last.
6. **Parser nhất quán:** proxy, middleware, framework và controller phải dùng cùng một cách hiểu cookie.
7. **Session lifecycle:** xoay session ID sau login/nâng quyền, thu hồi khi logout và kiểm tra timeout phía server.
8. **Migration:** xóa Domain cookie cũ theo đúng Path/Domain và không tiếp tục chấp nhận tên cookie cũ.
9. **SameSite đúng vai trò:** dùng để giảm CSRF cross-site; không coi nó là ranh giới giữa sibling subdomain.
10. **Giám sát:** log duplicate cookie và nguồn request ở mức không lộ token; theo dõi subdomain không còn được quản lý.

**Ghi nhớ:** Cookie tossing lợi dụng việc browser có thể gửi nhiều cookie cùng tên từ các phạm vi khác nhau, trong khi server chỉ nhận name/value và parser có thể chọn nhầm. Hãy **giới hạn Domain, dùng `__Host-` cho session, từ chối duplicate cookie nhạy cảm và quản lý session ở server**.

## Tài liệu tham khảo

- [RFC 6265 — HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265)
- [RFC 6265bis — Cookies: HTTP State Management Mechanism](https://datatracker.ietf.org/doc/draft-ietf-httpbis-rfc6265bis/)
- [MDN — Set-Cookie header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie)
- [MDN — Cookie prefixes](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies#cookie_prefixes)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP — Session Fixation](https://owasp.org/www-community/attacks/Session_fixation)

