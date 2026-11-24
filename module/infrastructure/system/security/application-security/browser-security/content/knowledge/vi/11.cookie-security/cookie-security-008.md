# Cookie audit: kiểm kê, đánh giá và gia cố cookie bảo mật

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Lập danh mục cookie của ứng dụng và phân loại cookie session, chức năng, phân tích và bên thứ ba.
2. Đọc và đánh giá các thuộc tính Domain, Path, Secure, HttpOnly, SameSite, Expires, Max-Age và Partitioned.
3. Phát hiện rủi ro do cookie scope quá rộng, cookie trùng tên, thiếu thuộc tính, session fixation và cấu hình third-party cookie.
4. Chọn prefix __Host- hoặc __Secure- phù hợp và giải thích điều kiện browser kiểm tra.
5. Kiểm tra vòng đời session: tạo, đăng nhập, nâng quyền, logout, hết hạn và thu hồi ở server.
6. Thực hiện cookie audit bằng Chrome DevTools, phân loại phát hiện và đề xuất biện pháp sửa.

> **Bối cảnh:** Module Browser Security phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web. Cookie là cơ chế lưu và gửi trạng thái theo quy tắc của browser; cookie session thường mang credential nên cần được kiểm tra cùng SOP, CSRF, XSS, HTTPS và security headers. Cookie audit đánh giá cả cấu hình ở browser lẫn cách backend phát hành, xác thực và thu hồi session.

## 1. Cookie audit là gì?

**Cookie audit** là quá trình kiểm kê các cookie mà ứng dụng tạo hoặc sử dụng, xác định mục đích và phạm vi gửi của từng cookie, kiểm tra thuộc tính bảo mật, sau đó đánh giá vòng đời và cách backend xử lý giá trị cookie.

Không nên chỉ nhìn xem cookie có HttpOnly hay không rồi kết luận an toàn. Một cookie session có thể có đủ thuộc tính nhưng vẫn nguy hiểm nếu:

- Giá trị session không được xoay sau đăng nhập hoặc nâng quyền.
- Session cũ không bị thu hồi khi logout.
- Cookie có Domain quá rộng, cho phép nhiều subdomain cùng nhận.
- Backend tin cookie mà không kiểm tra session và quyền trên từng request.
- Ứng dụng không có phòng vệ CSRF phù hợp.
- Ứng dụng có XSS cho phép kẻ tấn công thực hiện hành động dưới phiên của nạn nhân dù không đọc được cookie.

Một cuộc audit tốt trả lời bốn câu hỏi:

1. **Cookie nào tồn tại?** Ai tạo, ở response nào, dùng cho chức năng nào?
2. **Browser gửi cookie ở đâu?** Host/domain, path, HTTPS hay HTTP, same-site hay cross-site?
3. **JavaScript có thể đọc cookie không?** Cookie có HttpOnly, và dữ liệu nào đang bị lộ cho script?
4. **Server bảo vệ session thế nào?** Token có đủ ngẫu nhiên, được xoay và thu hồi đúng lúc, được xác thực/phân quyền và chống CSRF không?

## 2. Kiểm kê cookie trước khi đánh giá

### Phân loại theo mục đích

| Nhóm | Ví dụ tên | Mục đích | Rủi ro cần xem |
| --- | --- | --- | --- |
| Session/authentication | __Host-session, SESSION, sid | Nhận diện phiên đăng nhập | Chiếm phiên, session fixation, cookie scope, thiếu HttpOnly/Secure |
| CSRF | XSRF-TOKEN, csrf | Hỗ trợ xác minh request | Cách token được kiểm tra, có bị lộ qua XSS hoặc log không |
| Preference | theme, language | Lưu lựa chọn giao diện | Dữ liệu không tin cậy, scope, thời hạn |
| Analytics/marketing | Cookie của công cụ đo lường/quảng cáo | Đo lường hoặc cá nhân hóa | Consent, third-party cookie, tracking và chia sẻ dữ liệu |
| Load balancing/affinity | route, LB_STICKY | Giữ request vào cùng backend | Cookie có chứa bí mật hoặc định danh nội bộ không |
| Security/anti-abuse | Cookie chống bot, risk signal | Hỗ trợ phát hiện lạm dụng | Nguồn phát hành, thời hạn và nguy cơ bị giả mạo |

Không suy mục đích chỉ từ tên cookie. Hãy đối chiếu nơi phát hành, nơi sử dụng trong ứng dụng và cấu hình backend. Cookie do proxy/CDN tạo cũng cần có chủ sở hữu rõ ràng.

### Mẫu danh mục cookie

Ghi một dòng cho mỗi cookie và mỗi biến thể scope đáng kể:

| Trường cần ghi | Nội dung |
| --- | --- |
| Tên và giá trị mẫu đã che | Không lưu giá trị session thật; chỉ ghi tên hoặc dạng đã redacted |
| Host phát hành | Host gửi response Set-Cookie |
| Domain | Không có (host-only) hoặc domain được khai báo |
| Path | Phạm vi path mà browser áp dụng |
| Secure / HttpOnly | Có hoặc không |
| SameSite | Strict, Lax, None hoặc không khai báo |
| Expires / Max-Age | Hạn sử dụng hoặc session cookie |
| Partitioned / prefix | Có/không; tên có __Host- hoặc __Secure- không |
| Mục đích và chủ sở hữu | Session, preference, analytics...; đội chịu trách nhiệm |
| Nơi được gửi/đọc | Request nào gửi; script nào cần đọc nếu không HttpOnly |
| Kết luận | Pass, finding, mức độ, cách sửa và người phụ trách |

**Không đưa giá trị cookie thật vào báo cáo, ticket, ảnh chụp màn hình hoặc log.** Session cookie có thể tương đương một credential đang hoạt động. Dùng giá trị đã che như __Host-session=[REDACTED].

## 3. Phạm vi cookie: Domain, host, Path và port

### Host-only cookie và Domain cookie

Nếu Set-Cookie **không có thuộc tính Domain**, cookie là **host-only** và chỉ được gửi tới host đã phát hành cookie.

```http
# Host-only: chỉ host api.example.test nhận cookie này
Set-Cookie: session=abc; Path=/; Secure; HttpOnly; SameSite=Lax
```

Nếu khai báo Domain=example.test, cookie có thể được gửi tới domain đó và các subdomain phù hợp:

```http
# Phạm vi rộng hơn: có thể gửi tới app.example.test và admin.example.test
Set-Cookie: legacy-session=abc; Domain=example.test; Path=/; Secure; HttpOnly; SameSite=Lax
```

- Bỏ Domain thường là lựa chọn tốt cho cookie session: giảm số host có thể nhận credential.
- Domain=example.test mở rộng phạm vi đến subdomain phù hợp; hãy cân nhắc mọi subdomain, gồm host cũ, hệ thống thử nghiệm và subdomain do bên thứ ba quản lý.
- Dấu chấm đầu như .example.test không tạo khác biệt bảo mật hiện đại; browser xử lý theo quy tắc Domain chuẩn.
- Browser không chấp nhận cookie Domain đặt lên public suffix như com hoặc một public suffix không được phép.

**Rủi ro subdomain:** Nếu một subdomain bị chiếm quyền hoặc chạy ứng dụng kém tin cậy, cookie Domain rộng có thể bị gửi tới host đó. Subdomain không cần đọc cookie bằng JavaScript mới có thể nhận credential trong HTTP request.

### Path không phải ranh giới bảo mật

Path=/admin giới hạn những request path mà browser gửi cookie theo quy tắc path-match. Nhưng Path **không cô lập bảo mật giữa các ứng dụng cùng host**: nó không thay SOP, không phải cơ chế phân quyền, và script cùng origin có thể có khả năng truy cập cookie không HttpOnly theo quy tắc cookie.

Cookie cùng tên nhưng khác Path hoặc Domain có thể cùng tồn tại:

```http
Set-Cookie: session=one; Path=/; Secure; HttpOnly
Set-Cookie: session=two; Path=/admin; Secure; HttpOnly
```

Khi request khớp cả hai scope, header Cookie có thể chứa nhiều cặp cùng tên. Backend không nên dựa vào thứ tự để chọn session. Tránh phát hành trùng tên; khi đổi scope cần xóa cookie cũ bằng đúng tên, Domain và Path tương ứng.

### Cookie không được phân vùng theo port

Origin có port, còn cookie không dùng port làm thành phần scope. Ví dụ:

```text
https://app.example.test:443
https://app.example.test:8443
```

Hai URL khác origin, nhưng cookie phù hợp host/path có thể được gửi tới cả hai port. Vì vậy **không dùng port khác nhau để cách ly session hoặc bí mật**. Nếu cần ranh giới mạnh, dùng host riêng và cookie host-only, đồng thời áp dụng phân quyền backend.

## 4. Các thuộc tính bảo mật cần audit

### Secure

Cookie có Secure chỉ được gửi qua kênh an toàn (thông thường HTTPS). Cookie session/authentication trong môi trường production phải có Secure.

```http
Set-Cookie: __Host-session=abc; Path=/; Secure; HttpOnly; SameSite=Lax
```

Không coi việc site tự redirect HTTP sang HTTPS là thay thế cho Secure: request ban đầu hoặc cấu hình sai có thể xảy ra trước redirect. Dùng HTTPS toàn bộ và cân nhắc HSTS để giảm nguy cơ downgrade.

### HttpOnly

HttpOnly ngăn JavaScript truy cập cookie qua các API như document.cookie. Browser vẫn có thể tự gửi cookie trong request đủ điều kiện.

HttpOnly giảm khả năng đánh cắp trực tiếp giá trị session qua XSS, nhưng **không ngăn XSS thực hiện hành động bằng phiên hiện tại**. Script độc hại chạy trong origin của ứng dụng vẫn có thể gửi request mà browser tự đính kèm cookie.

Không gắn HttpOnly vào cookie CSRF double-submit nếu thiết kế frontend cần đọc token từ cookie để gửi trong request header. Trong trường hợp đó, token phải được thiết kế phù hợp, không phải session credential; server vẫn phải kiểm tra token và nguồn request.

### SameSite

SameSite kiểm soát việc cookie được gửi trong một số ngữ cảnh request **cross-site**:

| Giá trị | Hành vi khái quát | Dùng khi |
| --- | --- | --- |
| Strict | Không gửi trong phần lớn ngữ cảnh cross-site | Session nhạy cảm không cần luồng điều hướng từ website ngoài |
| Lax | Cho phép một số top-level cross-site navigation an toàn (thường là phương thức safe như GET), chặn nhiều subresource/form POST cross-site | Lựa chọn mặc định phù hợp cho nhiều cookie session |
| None | Cho phép cookie trong ngữ cảnh cross-site theo quy tắc SameSite | Chỉ khi thật sự cần tích hợp cross-site; phải đi kèm Secure |

Ví dụ:

```http
# Session chỉ cần same-site và các điều hướng Lax thông thường
Set-Cookie: __Host-session=abc; Path=/; Secure; HttpOnly; SameSite=Lax

# Chỉ khi cần cookie trong ngữ cảnh cross-site
Set-Cookie: embed-session=abc; Path=/; Secure; HttpOnly; SameSite=None
```

Nếu không khai báo SameSite, nhiều browser hiện đại áp dụng hành vi mặc định tương đương Lax; hành vi chi tiết có thể khác theo browser/chính sách tương thích. **Audit nên yêu cầu khai báo tường minh** để chủ đích rõ ràng.

SameSite dùng khái niệm **site**, không phải origin. Hai subdomain cùng scheme và registrable domain có thể same-site nhưng cross-origin. Vì vậy SameSite=Lax không thay thế kiểm tra origin/CSRF trong hệ thống có nhiều subdomain, đặc biệt khi có subdomain không đáng tin.

### Expires và Max-Age

- Không có cả hai thuộc tính: thường là **session cookie**; thời điểm kết thúc session do browser quyết định, và tính năng khôi phục session của browser có thể giữ lại dữ liệu lâu hơn kỳ vọng.
- Expires chỉ định ngày/giờ hết hạn theo HTTP-date.
- Max-Age chỉ định số giây còn hiệu lực; khi cả hai cùng xuất hiện, Max-Age có ưu tiên.
- Max-Age=0 hoặc giá trị âm dùng để yêu cầu xóa cookie.

Xóa cookie phải dùng cùng tên và scope (Domain/Path) tương ứng:

```http
Set-Cookie: __Host-session=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax
```

Không đặt thời hạn quá dài cho session credential nếu không có nhu cầu và cơ chế thu hồi phù hợp. Hết hạn ở browser không thay cho việc server kiểm tra thời hạn session.

## 5. Cookie prefixes: __Host- và __Secure-

Browser hỗ trợ cookie prefixes có thể áp dụng các điều kiện bổ sung khi nhận Set-Cookie:

| Prefix | Điều kiện quan trọng | Lợi ích |
| --- | --- | --- |
| __Secure- | Cookie phải được đặt từ secure origin và có thuộc tính Secure | Giảm nguy cơ cookie cùng tên bị ghi đè từ ngữ cảnh không an toàn |
| __Host- | Secure origin, có Secure, Path=/ và **không có Domain** | Buộc cookie host-only, scope path gốc và ngăn subdomain đặt cookie Domain cùng prefix |

Cookie session phù hợp có thể là:

```http
Set-Cookie: __Host-session=opaque-random-id; Path=/; Secure; HttpOnly; SameSite=Lax
```

Không thêm Domain vào cookie __Host-; browser hỗ trợ prefix sẽ từ chối cookie nếu vi phạm điều kiện. Prefix là **lớp bảo vệ bổ sung**, không thay việc tạo session ID an toàn, rotate và thu hồi session ở server.

Tên prefix có phân biệt chữ hoa/thường theo chuỗi prefix chuẩn. Khi audit hệ thống cần hỗ trợ nhiều browser/engine, xác minh khả năng hỗ trợ của phiên bản mục tiêu và không dựa prefix làm lớp bảo vệ duy nhất.

## 6. Cookie bên thứ ba và Partitioned (CHIPS)

Cookie trong iframe hoặc request cross-site chịu chính sách third-party cookie của browser. SameSite=None; Secure là điều kiện cần cho cookie cross-site theo SameSite, nhưng **không bảo đảm cookie bên thứ ba luôn được browser cho phép**: browser có thể chặn, giới hạn, phân vùng hoặc yêu cầu quyền người dùng.

### Partitioned cookie

CHIPS (Cookies Having Independent Partitioned State) cho phép cookie được phân vùng theo **top-level site** trong browser hỗ trợ. Ví dụ:

```http
Set-Cookie: widget-state=abc; Path=/; Secure; HttpOnly; SameSite=None; Partitioned
```

Cookie Partitioned cần Secure. Nó được lưu trong một partition gắn với top-level site; cùng widget nhúng dưới hai top-level site khác nhau không mặc nhiên chia sẻ cùng trạng thái partitioned cookie.

| Tình huống | Cookie không partitioned | Cookie Partitioned |
| --- | --- | --- |
| Widget nhúng dưới shop.example.test | Có thể bị chính sách third-party cookie chặn/giới hạn | Có thể dùng partition riêng cho top-level site shop |
| Widget nhúng dưới news.other.test | Nếu được phép, có thể chia sẻ trạng thái cross-site theo scope | Có partition riêng cho top-level site news |
| Widget chạy top-level | Áp dụng scope và chính sách cookie thông thường | Cần xem ngữ cảnh và hành vi hỗ trợ của browser |

CHIPS hữu ích khi dịch vụ nhúng cần trạng thái độc lập theo từng website. Nó không phải cách vượt chính sách third-party cookie, không thay xác thực và không cho phép widget theo dõi một người dùng xuyên các top-level site bằng cùng partition.

## 7. Audit vòng đời session

Cookie chỉ là phương tiện browser mang một giá trị. **Session security chủ yếu được quyết định ở server**.

### Tạo và rotate session

Khi người dùng đăng nhập thành công, backend nên tạo hoặc rotate session ID mới thay vì tiếp tục dùng session ID do client chọn trước đăng nhập. Điều này giảm **session fixation**: kẻ tấn công không thể chuẩn bị một ID rồi chờ nạn nhân đăng nhập để dùng lại ID đó.

Nên rotate session khi:

- Đăng nhập thành công.
- Nâng quyền hoặc chuyển sang vai trò nhạy cảm.
- Hoàn thành một bước xác minh quan trọng.
- Có sự kiện bảo mật khiến credential/session cũ cần bị vô hiệu hóa.

Session ID cần đủ ngẫu nhiên, khó đoán, không chứa thông tin cá nhân hoặc quyền có thể sửa ở client. Server lưu trạng thái/tra cứu session và xác minh trên mỗi request.

### Logout và thu hồi

Logout phải làm hai việc:

1. **Thu hồi session ở server** để ID cũ không còn xác thực được.
2. Gửi Set-Cookie xóa cookie tại browser với đúng tên, Path, Domain (nếu có) và các thuộc tính scope liên quan.

Chỉ xóa cookie ở browser mà không thu hồi session phía server có thể khiến bản sao cookie bị đánh cắp vẫn dùng được cho đến khi hết hạn.

### Idle timeout và absolute timeout

- **Idle timeout:** session hết hạn sau khoảng thời gian không có hoạt động phù hợp.
- **Absolute timeout:** session hết hạn sau tổng thời gian tối đa, dù người dùng vẫn hoạt động.
- **Server-side revocation:** cho phép vô hiệu hóa session do logout, thay đổi mật khẩu, phát hiện rủi ro hoặc quản trị viên thu hồi.

Không dựa duy nhất vào Expires/Max-Age để thực thi timeout; backend phải từ chối session đã hết hạn/thu hồi.

### Ví dụ phát hành cookie session

```http
HTTP/1.1 200 OK
Set-Cookie: __Host-session=opaque-random-id; Path=/; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
Content-Type: application/json

{"authenticated": true}
```

Giá trị opaque-random-id là minh họa, không phải session ID dùng thật. Trong ứng dụng thực, sinh ID bằng bộ sinh ngẫu nhiên mật mã của nền tảng và lưu session ở phía server.

## 8. Cookie và các cơ chế bảo vệ liên quan

### HttpOnly không chữa XSS

Nếu ứng dụng có XSS, script độc hại có thể thực hiện thao tác dưới origin nạn nhân. HttpOnly giúp ngăn đọc trực tiếp session cookie nhưng không chặn script gọi API hoặc đọc dữ liệu mà trang được quyền truy cập.

Phòng vệ XSS vẫn cần:

- Encode output đúng ngữ cảnh và tránh DOM injection sink nguy hiểm.
- CSP phù hợp, nonce/hash thay cho unsafe-inline khi có thể.
- Trusted Types tại các sink được hỗ trợ.
- Kiểm tra và sanitize HTML không tin cậy theo đúng use case.

### SameSite không thay thế CSRF token

Cookie SameSite=Lax hoặc Strict giảm một số request cross-site mang credential, nhưng ứng dụng vẫn nên có phòng vệ CSRF thích hợp cho endpoint thay đổi trạng thái:

- CSRF token được kiểm tra phía server.
- Xác minh Origin/Referer khi phù hợp.
- Dùng Fetch Metadata (Sec-Fetch-Site, Sec-Fetch-Mode, Sec-Fetch-Dest) để hỗ trợ lọc request.
- Không thực hiện thao tác thay đổi trạng thái qua GET.
- Kiểm tra quyền người dùng với từng tài nguyên/hành động.

### CORS không làm cookie an toàn hơn

CORS quyết định script cross-origin có thể đọc response hay không. Nó không quyết định toàn bộ quy tắc cookie và không thay xác thực/phân quyền. Với Fetch cross-origin cần credentials, frontend có thể dùng:

```js
fetch("https://api.example.test/profile", {
  credentials: "include"
});
```

Server cần ACAO origin cụ thể và Access-Control-Allow-Credentials: true; browser còn xét cookie attributes, SameSite và third-party cookie policy. JavaScript vẫn không thể đọc Set-Cookie qua response.headers.

## 9. Quy trình cookie audit bằng Chrome DevTools

Thực hiện trên ứng dụng và tài khoản thử nghiệm được phép. Không dùng session thật của người khác và không sao chép giá trị cookie ra báo cáo.

### Bước 1 — Kiểm kê cookie đang lưu

1. Mở Chrome DevTools → **Application**.
2. Trong **Storage → Cookies**, chọn đúng origin/host.
3. Ghi tên cookie, Domain, Path, Expires/Max-Age, Size, HttpOnly, Secure, SameSite, Partition Key (nếu giao diện hiển thị).
4. Đối chiếu cookie với chức năng ứng dụng và response Set-Cookie đã phát hành.
5. Che hoặc không sao chép cột Value; session token là bí mật.

### Bước 2 — Xem nơi cookie được phát hành

1. Mở **Network**, bật Preserve log.
2. Thực hiện các luồng đăng nhập, đổi quyền, logout và tải API.
3. Chọn response liên quan → **Headers → Response Headers**.
4. Kiểm tra từng dòng Set-Cookie, nhất là các thuộc tính có mặt/thiếu và biến thể cùng tên.
5. Xem tab Cookies/blocked reasons của request/response nếu browser cung cấp để hiểu vì sao cookie bị chặn hoặc không được lưu.

Một response có thể phát hành nhiều cookie. Mỗi cookie nên có một Set-Cookie header riêng; không gộp các cookie thành một dòng phân cách bằng dấu phẩy vì thuộc tính Expires tự chứa dấu phẩy.

### Bước 3 — Kiểm tra cookie thực sự được gửi

1. Chọn request cần audit trong Network.
2. Mở **Request Headers** hoặc tab **Cookies**.
3. Kiểm tra cookie có được gửi đúng host/path và qua HTTPS hay không.
4. Đọc blocked reason nếu cookie không được gửi; đối chiếu SameSite, Secure, third-party policy và Partition Key.
5. So sánh request same-site, cross-site iframe và top-level navigation trên môi trường test.

### Bước 4 — Kiểm tra khả năng JavaScript đọc cookie

Trong Console của origin đang kiểm tra:

```js
document.cookie
```

Kết quả chỉ gồm cookie mà script được phép đọc; cookie HttpOnly không xuất hiện. **Không dùng việc cookie vắng mặt trong document.cookie để kết luận cookie không tồn tại**. Hãy so sánh với Application và response headers.

### Bước 5 — Kiểm tra vòng đời session

1. Ghi nhận cookie session đã che giá trị trước đăng nhập.
2. Đăng nhập và xác minh session ID được thay mới (so sánh fingerprint đã hash/che, không lưu token).
3. Thực hiện thao tác nâng quyền hoặc đổi mật khẩu theo kịch bản test; xác minh session cũ được rotate/thu hồi theo chính sách.
4. Logout; kiểm tra response xóa cookie đúng scope và backend từ chối session ID cũ.
5. Thử lại bằng bản sao cookie test cũ trong môi trường cô lập; xác minh không thể dùng lại sau khi server thu hồi.

## 10. Checklist phát hiện và khuyến nghị

| Kiểm tra | Kỳ vọng với cookie session nhạy cảm | Dấu hiệu cần điều tra |
| --- | --- | --- |
| HTTPS và Secure | Chỉ gửi qua HTTPS; cookie có Secure | Session cookie thiếu Secure hoặc được dùng trên HTTP |
| HttpOnly | Có nếu JavaScript không cần đọc session | Session credential xuất hiện trong document.cookie |
| SameSite | Khai báo rõ Lax/Strict; None chỉ khi cần cross-site và có Secure | Không khai báo, hoặc None không có Secure |
| Domain | Ưu tiên host-only, không có Domain | Domain rộng tới subdomain không cần thiết |
| Path | Thường / cho session toàn ứng dụng; không coi Path là ranh giới bảo mật | Nhiều cookie cùng tên khác path gây chọn session mơ hồ |
| Prefix | Ưu tiên __Host- cho session host-only trên HTTPS nếu phù hợp | Cookie session có thể bị subdomain đặt/ghi đè |
| Expiry | Thời hạn phù hợp; server có idle/absolute timeout | Session sống quá lâu hoặc chỉ dựa vào browser expiry |
| Session rotation | Đổi ID sau đăng nhập/nâng quyền | ID trước và sau login giữ nguyên |
| Logout | Thu hồi phía server và xóa đúng scope | Chỉ xóa cookie client, session cũ vẫn hoạt động |
| Third-party | Chỉ dùng khi có yêu cầu; xem partitioning và browser policy | Phụ thuộc cookie bên thứ ba không ổn định |
| Logging | Không log giá trị cookie/session | Cookie xuất hiện trong log, analytics hoặc ticket |
| Backend authz | Kiểm tra session và quyền mỗi request | Tin dữ liệu/role lấy từ cookie mà không xác minh |

### Mẫu ghi nhận một finding

```text
Finding: Session cookie thiếu HttpOnly
Asset: https://app.example.test
Cookie: __Host-session=[REDACTED]
Evidence: Response Set-Cookie không có thuộc tính HttpOnly
Impact: Script cùng origin có thể đọc trực tiếp session cookie nếu có XSS
Severity: Đánh giá theo khả năng XSS, phạm vi session và tác động tài khoản
Recommendation: Thêm HttpOnly; đồng thời xử lý nguyên nhân XSS bằng CSP,
Trusted Types và output encoding phù hợp
Retest: Xác nhận cookie không xuất hiện trong document.cookie và session
vẫn hoạt động đúng qua request browser
```

Không gán mức độ nghiêm trọng chỉ từ một thuộc tính. Ví dụ cookie preference thiếu HttpOnly có thể là thiết kế bình thường nếu frontend cần đọc; cookie session thiếu HttpOnly thường có rủi ro cao hơn.

## 11. Ví dụ backend và lỗi thường gặp

### Node.js: phát hành và xóa session cookie

```js
// Sau khi xác thực thành công và tạo session ID mới ở server:
response.setHeader("Set-Cookie",
  "__Host-session=" + encodeURIComponent(sessionId) +
  "; Path=/; Secure; HttpOnly; SameSite=Lax"
);

// Khi logout: thu hồi sessionId trong session store trước,
// sau đó yêu cầu browser xóa cookie với đúng scope:
response.setHeader("Set-Cookie",
  "__Host-session=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax"
);
```

Đây là ví dụ minh họa header; ứng dụng thực nên dùng framework cookie API để tránh lỗi serialize, và lưu ý session ID phải được sinh bằng CSPRNG, lưu/kiểm tra server-side, rotate và revoke đúng lúc. Với __Host-, không thêm Domain.

### Nhiều Set-Cookie phải được gửi thành nhiều header

Trong Node.js:

```js
response.setHeader("Set-Cookie", [
  "__Host-session=opaque-id; Path=/; Secure; HttpOnly; SameSite=Lax",
  "theme=dark; Path=/; Secure; SameSite=Lax; Max-Age=2592000"
]);
```

Không nối các cookie bằng dấu phẩy thành một Set-Cookie duy nhất. Dấu phẩy xuất hiện trong định dạng ngày của Expires, nên việc gộp có thể làm parser hiểu sai.

### Lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Session cookie thiếu Secure | Có nguy cơ bị gửi qua kết nối không an toàn | HTTPS toàn bộ, thêm Secure và cân nhắc HSTS |
| Session cookie thiếu HttpOnly dù không cần JS | XSS có thể đọc trực tiếp credential | Thêm HttpOnly; vẫn xử lý XSS |
| Dùng SameSite=None nhưng thiếu Secure | Browser hiện đại từ chối hoặc không lưu cookie | Thêm Secure và chỉ dùng None khi thực sự cần |
| Domain cookie quá rộng | Nhiều subdomain nhận được session cookie | Bỏ Domain để dùng host-only; cân nhắc __Host- |
| Dùng Path để cách ly ứng dụng | Path không phải ranh giới bảo mật | Dùng host/origin riêng và authz server-side |
| Không rotate sau login | Session fixation | Tạo ID mới và vô hiệu hóa ID trước |
| Logout chỉ xóa cookie | Session bị đánh cắp vẫn còn hiệu lực ở server | Thu hồi server-side và xóa cookie đúng scope |
| Cho rằng HttpOnly ngăn XSS | XSS vẫn thực hiện request dưới phiên nạn nhân | CSP, Trusted Types, encoding và CSRF defense |
| Cho rằng SameSite thay CSRF token | Subdomain same-site hoặc luồng đặc biệt vẫn có rủi ro | Token, Origin/Fetch Metadata và kiểm tra quyền |
| Đọc cookie session qua document.cookie | Vi phạm mục tiêu bảo vệ credential | Không expose session cho JS; dùng API backend |
| Gộp nhiều Set-Cookie bằng dấu phẩy | Parser có thể hiểu sai thuộc tính Expires | Gửi nhiều Set-Cookie header riêng |

## 12. Câu hỏi củng cố

**Câu 1.** Cookie session không có Domain có phạm vi thế nào?

**Giải đáp:** Nó là host-only cookie, chỉ được gửi tới host đã phát hành cookie theo các điều kiện Path/Secure khác. Subdomain không tự nhận cookie này.

**Câu 2.** Hai ứng dụng cùng host nhưng khác port có thể nhận cùng cookie không?

**Giải đáp:** Có thể. Cookie không được phân vùng theo port như origin. Không dùng port để cách ly session.

**Câu 3.** HttpOnly có ngăn XSS thực hiện hành động chuyển tiền không?

**Giải đáp:** Không. HttpOnly ngăn script đọc trực tiếp cookie, nhưng browser vẫn có thể gửi cookie trong request do script khởi tạo. Cần phòng XSS, CSRF và xác minh giao dịch phía server.

**Câu 4.** Vì sao cookie SameSite=None cần Secure?

**Giải đáp:** Quy tắc cookie hiện đại yêu cầu None đi cùng Secure để cookie có thể được gửi trong ngữ cảnh cross-site qua kết nối an toàn; browser còn có thể áp dụng chính sách third-party cookie riêng.

**Câu 5.** __Host-session có thể khai báo Domain=example.test không?

**Giải đáp:** Không. Prefix __Host- yêu cầu Secure, Path=/ và không có Domain; browser hỗ trợ prefix sẽ từ chối cookie vi phạm.

**Câu 6.** Xóa cookie ở browser đã đủ để logout chưa?

**Giải đáp:** Chưa. Backend phải thu hồi session ở server, sau đó gửi cookie hết hạn với cùng tên và scope.

## 13. Tổng kết

Cookie audit bắt đầu bằng **kiểm kê và xác định mục đích**, tiếp tục với scope (Domain, host-only, Path, port), thuộc tính (Secure, HttpOnly, SameSite, expiry, prefixes, Partitioned) và kết thúc ở **vòng đời session phía server**. Với session credential, cấu hình thường phù hợp là cookie host-only, Secure, HttpOnly, SameSite=Lax hoặc Strict theo luồng ứng dụng, và prefix __Host- nếu đáp ứng điều kiện.

Không một thuộc tính cookie nào thay thế xác thực, phân quyền, chống CSRF hoặc phòng XSS. Dùng DevTools để quan sát cookie được lưu và gửi, nhưng luôn kiểm tra backend có rotate/revoke session và từ chối request trái quyền. Khi báo cáo audit, che mọi giá trị cookie thật và mô tả finding bằng bằng chứng có thể tái kiểm tra.

## Tài liệu tham khảo

1. [RFC 6265bis — Cookies: HTTP State Management Mechanism](https://datatracker.ietf.org/doc/draft-ietf-httpbis-rfc6265bis/): quy tắc cookie, scope và thuộc tính.
2. [MDN — HTTP cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies): tạo, gửi, scope và bảo vệ cookie.
3. [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): Domain, Path, Secure, HttpOnly, SameSite, prefixes và Partitioned.
4. [MDN — Document.cookie](https://developer.mozilla.org/en-US/docs/Web/API/Document/cookie): giới hạn truy cập cookie từ JavaScript.
5. [Chrome for Developers — CHIPS](https://developer.chrome.com/docs/privacy-sandbox/chips/): cookie được phân vùng theo top-level site.
6. [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session ID, rotation, timeout và logout.
7. [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): SameSite, CSRF token và kiểm tra request.
