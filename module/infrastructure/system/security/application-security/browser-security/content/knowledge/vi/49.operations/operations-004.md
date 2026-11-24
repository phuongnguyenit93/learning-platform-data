# Cookie policy review: rà soát và vận hành cookie an toàn

Cookie là một phần của ranh giới bảo mật giữa browser và ứng dụng web. Server dùng cookie để duy trì session, ghi nhớ lựa chọn, cá nhân hóa trải nghiệm hoặc hỗ trợ phân tích. Một cookie cấu hình sai có thể mở rộng phạm vi một subdomain được phép nhận session, khiến credential bị gửi qua HTTP, làm JavaScript đọc được session, hoặc cho phép request cross-site thực hiện hành động ngoài ý muốn.

Cookie policy review là hoạt động kiểm kê và đánh giá toàn bộ cookie do ứng dụng, subdomain, CDN, identity provider và dịch vụ tích hợp đặt ra. Việc review phải trả lời được cookie nào cần tồn tại, ai đặt, browser gửi nó trong ngữ cảnh nào, dữ liệu/quyền mà nó đại diện, thời hạn bao lâu, và cách thu hồi khi logout hoặc xảy ra sự cố.

Bài học này hướng dẫn quy trình vận hành để lập inventory, chọn Domain/Path và các thuộc tính Secure, HttpOnly, SameSite, dùng cookie prefixes, quản lý expiry và session rotation, kiểm soát CSRF, third-party/partitioned cookies, privacy/consent, triển khai thay đổi an toàn và kiểm thử trên browser thực tế.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Lập inventory cookie theo domain, path, purpose, owner và lifetime.
- Phân biệt host-only cookie với Domain cookie và hiểu tác động của subdomain.
- Chọn Secure, HttpOnly, SameSite và cookie prefix theo threat model.
- Hiểu giới hạn của Path, SameSite và HttpOnly.
- Đánh giá Max-Age, Expires, session renewal, logout và session rotation.
- Phát hiện cookie trùng tên, cookie tossing và cấu hình Domain quá rộng.
- Kết hợp cookie policy với CSRF token, Origin validation và Fetch Metadata.
- Đánh giá third-party cookie, CHIPS/Partitioned cookie và tác động của browser privacy controls.
- Rà soát cookie consent, data minimization và retention.
- Lập kế hoạch rollout, monitoring, rollback và kiểm thử regression.

## 1. Cookie policy review là gì?

Cookie policy là tập hợp quy tắc quy định cookie nào được phép sử dụng, cho mục đích gì và với thuộc tính bảo mật nào. Review không chỉ là kiểm tra một header `Set-Cookie` trên một response. Một ứng dụng có thể nhận cookie từ nhiều thành phần:

- Web application và API backend.
- Identity provider hoặc hệ thống SSO.
- Reverse proxy, load balancer và gateway.
- Subdomain phục vụ tài liệu, media hoặc static assets.
- Payment, analytics, experimentation hoặc customer support integration.
- Service Worker hoặc frontend script kích hoạt endpoint đặt cookie.

Mỗi thành phần có thể phát hành cookie với Domain, Path, expiry và flags khác nhau. Nếu không có inventory, nhóm vận hành khó biết cookie nào là session quan trọng, cookie nào đã lỗi thời và cookie nào thuộc bên thứ ba.

### 1.1 Mục tiêu của một lần review

Một lần review tốt phải xác định:

1. Cookie có mục đích nghiệp vụ rõ ràng và owner chịu trách nhiệm.
2. Cookie được giới hạn ở host/domain và path nhỏ nhất có thể.
3. Cookie nhạy cảm dùng Secure, HttpOnly và SameSite phù hợp.
4. Lifetime và rotation phù hợp với mức độ rủi ro.
5. Các luồng thay đổi trạng thái có CSRF protection.
6. Cookie bên thứ ba và cookie analytics tuân thủ privacy policy.
7. Cookie cũ được loại bỏ và session có thể bị thu hồi.
8. Browser thực tế gửi cookie đúng theo thiết kế.
9. Thay đổi policy có kế hoạch rollout, quan sát và rollback.
10. Có bằng chứng kiểm thử và người phê duyệt.

### 1.2 Cookie không phải chỉ là dữ liệu lưu trữ

Cookie thường được browser tự động đính kèm vào request phù hợp với domain, path, secure context và SameSite rules. Đây là điểm khác biệt quan trọng với một giá trị mà frontend tự thêm vào header.

Nếu cookie đại diện cho session, browser có thể gửi nó khi user truy cập một trang khác tạo request tới ứng dụng. Vì thế cookie authentication tạo ra rủi ro CSRF và cần thiết kế cùng request validation, không chỉ chọn một flag.

### 1.3 Phạm vi review

Review cần bao gồm:

- Cookie do first-party host đặt.
- Cookie chia sẻ giữa các subdomain.
- Cookie session và refresh/session continuation.
- Cookie phục vụ CSRF hoặc security state.
- Cookie preference, consent và localization.
- Cookie analytics, advertising và experimentation.
- Cookie từ identity provider, payment hoặc support widget.
- Cookie trong production, staging và local development.

Không suy luận cookie từ tên gọi. Xác minh bằng response headers, browser storage và luồng request thực tế.

## 2. Lập cookie inventory

Inventory là nguồn sự thật để review, phê duyệt và theo dõi thay đổi. Mỗi cookie cần có owner và mục đích. Cookie không xác định được owner hoặc không còn được sử dụng là ứng viên cần điều tra và loại bỏ.

### 2.1 Trường thông tin nên ghi nhận

| Trường | Nội dung cần ghi |
|---|---|
| Cookie name | Tên chính xác, phân biệt hoa thường |
| Issuing component | Ứng dụng, gateway, IdP hoặc vendor |
| Owner | Team/service chịu trách nhiệm |
| Purpose | Session, CSRF, preference, analytics... |
| Data class | Credential, pseudonymous ID, preference, PII... |
| Host/Domain | Host-only hay Domain attribute |
| Path | Phạm vi request path |
| Secure | Có yêu cầu HTTPS không |
| HttpOnly | JavaScript có thể đọc không |
| SameSite | Strict, Lax, None hoặc behavior mặc định |
| Partitioned | Có dùng partitioned storage không |
| Lifetime | Session, Max-Age hoặc Expires |
| Rotation/revocation | Cách thay và thu hồi |
| Consent/legal basis | Cơ sở xử lý theo privacy policy |
| Dependencies | Luồng nào cần cookie |
| Evidence | Response/header/browser test xác nhận |

### 2.2 Ví dụ inventory

| Cookie | Purpose | Domain scope | Flags | Lifetime | Owner |
|---|---|---|---|---|---|
| __Host-session | Session đăng nhập | Host-only | Secure, HttpOnly, SameSite=Lax, Path=/ | Server session: 30 phút idle, 8 giờ absolute (ví dụ policy) | Identity/API |
| csrf_token | CSRF defense | Host-only | Secure, SameSite=Strict hoặc Lax theo flow, không HttpOnly nếu double-submit cần JS đọc | Theo session | Web platform |
| locale | Ngôn ngữ giao diện | Host-only | Secure, SameSite=Lax | 180 ngày | Frontend |
| consent_state | Lựa chọn privacy | Host-only | Secure, SameSite=Lax | Theo retention policy | Privacy |
| analytics_id | Phân tích sử dụng | Theo vendor contract | Tùy mục đích và consent | Theo privacy policy | Analytics |

Bảng trên chỉ là fixture minh họa. Không sao chép nguyên lifetime/flags cho mọi ứng dụng. Session cookie và CSRF cookie cần được thiết kế theo kiến trúc authentication thực tế.

### 2.3 Phát hiện cookie không được quản lý

So sánh ba nguồn:

- Danh sách cookie trong response headers và browser storage.
- Danh sách cookie trong code/config và dependency inventory.
- Danh sách cookie đã được phê duyệt trong policy/privacy register.

Điều tra cookie chỉ xuất hiện ở production, cookie không có owner, cookie có tên thay đổi theo build, cookie từ vendor chưa được ghi nhận và cookie cũ vẫn tồn tại sau khi feature bị loại bỏ.

### 2.4 Cookie name collision

Hai component có thể đặt cookie cùng tên nhưng khác Domain hoặc Path. Browser có thể gửi nhiều cặp cùng tên trong một Cookie header; server framework có thể chọn hoặc parse chúng khác nhau.

Không giả định cookie name là duy nhất trên toàn browser. Inventory cần ghi cả scope, và backend nên tránh thiết kế phụ thuộc vào thứ tự cookie trùng tên. Đặt tên có namespace hoặc dùng host prefix cho session cookie quan trọng.

## 3. Domain, host-only và Path

Domain và Path quyết định request nào có thể mang cookie. Cấu hình phạm vi quá rộng có thể đưa credential đến subdomain không cần thiết.

### 3.1 Host-only cookie

Nếu Set-Cookie không có thuộc tính Domain, browser lưu cookie gắn với host đã phát hành nó. Ví dụ:

~~~http
Set-Cookie: session=opaque-value; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Nếu response đến từ `app.example.test`, cookie host-only này chỉ được gửi tới host đó, không tự động gửi tới `api.example.test` hoặc `www.example.test`.

Đây thường là lựa chọn tốt cho session: không chia sẻ credential với subdomain khác nếu không có nhu cầu rõ ràng.

### 3.2 Domain cookie

Ví dụ:

~~~http
Set-Cookie: session=opaque-value; Domain=example.test; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Cookie Domain cho phép host phù hợp trong domain tree nhận cookie, bao gồm các subdomain theo quy tắc cookie domain-match. Điều này có thể cần cho kiến trúc cũ, nhưng mở rộng phạm vi tin cậy.

Nếu một subdomain yếu, bị takeover hoặc có ứng dụng do team khác quản lý, Domain cookie rộng có thể làm tăng rủi ro lộ hoặc ghi đè cookie. Không đặt Domain ở parent domain chỉ vì muốn chia sẻ session giữa nhiều host; hãy đánh giá SSO hoặc flow token exchange riêng.

### 3.3 Dấu chấm đầu Domain không tạo khác biệt

Trong cookie hiện đại, dấu chấm đầu của Domain như `.example.test` không tạo thêm semantics so với `example.test`. Browser xử lý theo domain matching; không dùng dấu chấm như biện pháp bảo mật.

Public suffix như `com` hoặc suffix dùng chung không được phép làm cookie Domain thông thường cho mọi tenant. Browser từ chối một số Domain attribute tương ứng public suffix.

### 3.4 Path là bộ lọc gửi cookie, không phải security boundary

Ví dụ:

~~~http
Set-Cookie: admin_session=value; Path=/admin; Secure; HttpOnly; SameSite=Strict
~~~

Path giới hạn request path phù hợp được gửi kèm cookie. Nhưng Path không cô lập cookie như một sandbox bảo mật giữa các ứng dụng cùng host. Một ứng dụng khác trên cùng host có thể có khả năng tạo request phù hợp hoặc đọc cookie thông qua các cơ chế browser tùy trường hợp.

Không dựa vào Path để tách hai ứng dụng có mức tin cậy khác nhau. Dùng host/origin tách biệt và session riêng khi cần ranh giới bảo mật.

### 3.5 Cookie không được cô lập theo port

Cookie không có thuộc tính Port. Các ứng dụng chạy trên những port khác nhau của cùng hostname vẫn chia sẻ không gian cookie theo Domain/Path/Secure rules.

Nếu hai service cùng host nhưng khác port, không coi port là ranh giới bảo vệ session cookie. Dùng hostname riêng nếu cần cách ly cookie.

### 3.6 Review phạm vi domain

Với mỗi cookie nhạy cảm, hãy hỏi:

- Có thể bỏ Domain để dùng host-only không?
- Có cần Path khác `/` không, và lý do là gì?
- Có subdomain do vendor/team khác quản lý không?
- Có subdomain cũ, CNAME hoặc dịch vụ thử nghiệm chưa được quản trị không?
- Có cookie cùng tên ở nhiều Path/Domain gây ambiguity không?
- Cookie có bị gửi tới host nhận static asset hoặc upload không cần session không?

Ưu tiên scope hẹp và chỉ mở rộng khi có yêu cầu kiến trúc được ghi nhận.

## 4. Các thuộc tính bảo mật của cookie

Các flags xác định browser có gửi cookie qua kết nối nào, JavaScript có đọc được không và request cross-site nào được phép mang cookie.

### 4.1 Secure

Cookie có `Secure` chỉ được gửi qua secure channel, thông thường là HTTPS:

~~~http
Set-Cookie: session=opaque-value; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Cookie session và cookie chứa dữ liệu nhạy cảm phải dùng Secure trong production. Nếu TLS kết thúc tại reverse proxy, ứng dụng cần cấu hình trust proxy chính xác để framework nhận biết request gốc là HTTPS; không suy luận secure state từ header do client tùy ý gửi.

Secure không mã hóa giá trị cookie trong browser storage và không ngăn người có quyền điều khiển browser xem cookie. Nó bảo vệ việc truyền cookie qua HTTP không an toàn.

### 4.2 HttpOnly

`HttpOnly` ngăn JavaScript truy cập cookie qua API như `document.cookie`:

~~~http
Set-Cookie: session=opaque-value; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Dùng HttpOnly cho session identifier và credential không cần JavaScript đọc. Nếu frontend cần CSRF token hoặc preference, thiết kế một cookie/endpoint riêng với quyền và dữ liệu tối thiểu.

HttpOnly không che cookie khỏi người đang kiểm soát thiết bị và browser profile. Người dùng cục bộ vẫn có thể xem cookie trong công cụ quản lý storage của browser; mục tiêu của flag là chặn JavaScript chạy trong trang đọc giá trị qua cookie API.

HttpOnly giảm khả năng XSS lấy trực tiếp session cookie, nhưng XSS vẫn có thể thực hiện hành động bằng session của trang, đọc dữ liệu DOM/API được phép hoặc thay đổi nội dung. Nó không thay CSP, output encoding hoặc CSRF protection.

### 4.3 SameSite

`SameSite` kiểm soát việc browser gửi cookie trong một số ngữ cảnh cross-site. Ba giá trị chính:

| Giá trị | Hành vi tổng quát | Trường hợp sử dụng |
|---|---|---|
| Strict | Chỉ gửi trong ngữ cảnh same-site | Cookie không cần mang theo khi user đi từ site ngoài |
| Lax | Cho phép same-site và một số top-level cross-site navigation an toàn | Mặc định thực dụng cho nhiều session web |
| None | Cho phép cookie trong cross-site context nếu browser policy cho phép | SSO/embed/third-party flow cần thiết |

Ví dụ:

~~~http
Set-Cookie: session=opaque-value; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Nếu dùng `SameSite=None`, browser hiện đại yêu cầu `Secure`. Cookie không có SameSite được xử lý theo default của browser, thường gần với Lax nhưng có thể có khác biệt triển khai. Policy nên đặt tường minh thay vì dựa vào default.

### 4.4 Site không giống origin

Origin gồm scheme, host và port. Site trong SameSite model dựa trên scheme và registrable domain theo public suffix rules. Vì thế hai subdomain khác nhau có thể là cross-origin nhưng vẫn same-site.

Ví dụ `https://app.example.test` và `https://uploads.example.test` là hai origin khác nhau nhưng có thể cùng site. SameSite không tự ngăn request từ một sibling subdomain bị xâm nhập. Vì vậy vẫn cần kiểm tra Origin, CSRF token, authorization và các biện pháp cô lập subdomain.

### 4.5 SameSite không thay thế CSRF protection

SameSite là lớp giảm thiểu quan trọng, nhưng không nên là lớp duy nhất:

- Có luồng nghiệp vụ cần top-level cross-site navigation hoặc SSO.
- Subdomain cùng site có thể không bị SameSite chặn.
- Browser, embedded webview và phiên bản cũ có thể có hành vi khác.
- Một số request điều hướng vẫn có thể mang cookie theo Lax.
- XSS cùng site có thể thực hiện request trong phiên đã xác thực.

Với request thay đổi trạng thái, dùng anti-CSRF token hoặc cơ chế tương đương, kiểm tra Origin/Referer khi phù hợp, và áp dụng Fetch Metadata như lớp bổ sung. Không dùng GET cho hành động thay đổi trạng thái.

### 4.6 Thuộc tính không được hỗ trợ hoặc không liên quan

Không tự tạo thuộc tính cookie tùy biến và giả định browser sẽ enforce. Browser bỏ qua thuộc tính không hiểu. Các thuộc tính như Domain, Path, Expires, Max-Age, Secure, HttpOnly, SameSite và Partitioned cần được dùng theo chuẩn và browser support thực tế.

Cookie không có thuộc tính CORS, CSP hoặc Port. Không dùng các tên này trong Set-Cookie để mong browser tạo ranh giới bảo mật.

## 5. Cookie prefixes: ràng buộc cấu hình ngay tại browser

Cookie prefixes là quy ước tên cho phép browser áp dụng thêm điều kiện khi chấp nhận cookie. Chúng giúp giảm một số cấu hình sai, đặc biệt cookie session.

### 5.1 __Secure-

Cookie có tên bắt đầu `__Secure-` phải được đặt từ secure origin và có thuộc tính Secure trong các browser hỗ trợ prefix:

~~~http
Set-Cookie: __Secure-session=opaque-value; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Prefix giúp browser từ chối một số nỗ lực đặt cookie cùng tên qua HTTP hoặc thiếu Secure. Nó không tự bắt buộc HttpOnly, SameSite hoặc Path.

### 5.2 __Host-

Prefix `__Host-` áp dụng ràng buộc chặt hơn:

- Phải được đặt từ secure origin.
- Phải có thuộc tính Secure.
- Phải có Path=/.
- Không được có thuộc tính Domain.

Ví dụ:

~~~http
Set-Cookie: __Host-session=opaque-value; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Do không có Domain, cookie được giới hạn ở host đã đặt nó. Đây thường là lựa chọn tốt cho session cookie nếu kiến trúc hỗ trợ HTTPS và Path=/.

### 5.3 Browser không hỗ trợ prefix

Prefix là lớp enforcement phía browser khi được hỗ trợ. Server vẫn phải phát đúng flags, kiểm tra request và bảo vệ session. Không coi prefix như validation phía server hoặc thay thế kiểm thử tương thích browser.

### 5.4 Review prefix và cookie cũ

Khi đổi tên session sang `__Host-session`:

1. Kiểm tra mọi host thực sự cần session.
2. Xác nhận ứng dụng dùng HTTPS và Path=/.
3. Xác định cookie cũ có Domain/Path nào.
4. Phát cookie mới và chuyển luồng xác thực.
5. Thu hồi hoặc xóa cookie cũ đúng scope.
6. Kiểm thử duplicate cookie và rollback.
7. Xóa code tương thích cũ sau thời gian migration.

Không chỉ phát cookie mới mà để cookie cũ còn hiệu lực lâu dài.

## 6. Expiry, lifetime và session lifecycle

Cookie lifetime là một phần của chính sách session. Cookie hết hạn ở browser không nhất thiết làm session phía server bị vô hiệu ngay; ngược lại, session phía server có thể bị thu hồi trong khi browser vẫn giữ cookie cũ.

### 6.1 Session cookie

Nếu không có Max-Age hoặc Expires, cookie là session cookie theo browser. Tuy nhiên, browser có thể khôi phục session sau khi đóng/mở lại, tùy cài đặt session restore. Không giả định session cookie luôn bị xóa khi cửa sổ đóng.

### 6.2 Max-Age và Expires

Ví dụ dùng Max-Age:

~~~http
Set-Cookie: preference=compact; Path=/; Max-Age=2592000; Secure; SameSite=Lax
~~~

Hoặc Expires:

~~~http
Set-Cookie: preference=compact; Path=/; Expires=Tue, 22 Dec 2026 09:00:00 GMT; Secure; SameSite=Lax
~~~

`Max-Age` tính thời gian tồn tại theo giây; `Expires` chỉ thời điểm hết hạn. Nếu cả hai cùng xuất hiện, Max-Age được ưu tiên theo cookie processing rules.

Không đặt lifetime dài cho session credential chỉ vì muốn tránh user đăng nhập lại. Xác định idle timeout, absolute timeout, reauthentication cho hành động nhạy cảm và yêu cầu thu hồi.

### 6.3 Idle timeout và absolute timeout

- Idle timeout: session hết hạn sau một khoảng không hoạt động.
- Absolute timeout: session hết hạn sau thời gian tối đa kể từ lúc tạo, kể cả có hoạt động.
- Reauthentication: yêu cầu xác thực lại trước thao tác rủi ro cao như đổi email, thay mật khẩu hoặc quản lý MFA.

Cookie Max-Age không tự thực thi idle timeout. Server phải theo dõi session activity và expiry; client cookie chỉ là phương tiện mang session identifier.

### 6.4 Session rotation

Rotate session identifier sau các sự kiện làm thay đổi mức tin cậy:

- Đăng nhập thành công.
- Nâng quyền hoặc chuyển vai trò.
- Hoàn thành MFA hoặc step-up authentication.
- Thay đổi mật khẩu hoặc khôi phục tài khoản.
- Chuyển từ anonymous session sang authenticated session.

Rotation giúp giảm session fixation và hạn chế tiếp tục dùng identifier được tạo trước khi xác thực. Thu hồi session cũ ở server và tránh chấp nhận song song quá lâu ngoài policy.

### 6.5 Logout và revoke

Logout cần vô hiệu hóa session ở server hoặc identity provider, sau đó yêu cầu browser xóa cookie đúng scope.

Ví dụ xóa cookie host-only:

~~~http
Set-Cookie: __Host-session=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax
~~~

Để xóa cookie đã đặt với Domain/Path cụ thể, response phải nhắm đúng tên và scope tương ứng. Cookie cùng tên ở Path hoặc Domain khác có thể vẫn còn.

Xóa cookie ở browser không thu hồi bản sao cookie đã bị đánh cắp. Server-side revocation là điều kiện quan trọng khi logout hoặc xử lý incident.

### 6.6 Đổi tên hoặc đổi scope cookie

Khi chuyển Domain cookie sang host-only hoặc thay Path, browser có thể giữ cả cookie cũ và mới. Kế hoạch migration phải xác định:

- Cookie cũ có được server chấp nhận không.
- Cách phát hành và xác minh cookie mới.
- Cách xóa cookie cũ theo từng Domain/Path.
- Thời gian chuyển tiếp.
- Cách phát hiện client còn dùng cookie cũ.
- Điều kiện kết thúc migration và rollback.

Không đổi scope mà quên xóa bản cũ; duplicate name có thể khiến server parse nhầm session.

## 7. Cookie tossing, duplicate names và session integrity

Cookie tossing là nhóm tình huống một host/subdomain có thể đặt cookie có tên trùng hoặc scope rộng, làm ứng dụng nhận nhiều cookie cùng tên hoặc nhận giá trị không mong đợi.

### 7.1 Cookie cùng tên ở nhiều scope

Browser có thể gửi:

~~~http
Cookie: session=host-value; session=domain-value
~~~

Cookie header không mang lại thông tin Domain/Path của từng cặp để server phân biệt một cách đáng tin cậy. Framework/parser có thể chọn first, last hoặc biểu diễn thành danh sách. Hành vi khác nhau giữa proxy, framework và ứng dụng có thể tạo ambiguity.

Không dùng tên cookie session chung chung nếu nhiều ứng dụng cùng domain. Dùng prefix phù hợp, host-only cookie và parser đã được xác định rõ.

### 7.2 Subdomain không tin cậy

Nếu ứng dụng cho phép user tạo subdomain, phục vụ nội dung không tin cậy hoặc có CNAME trỏ vendor, một subdomain bị chiếm có thể gây rủi ro cookie cho parent domain khi cookie được chia sẻ rộng.

Giảm thiểu:

- Dùng host-only cookie cho session.
- Tránh Domain attribute ở parent domain nếu không cần.
- Tách user-generated content sang registrable domain khác.
- Xóa DNS/CNAME không còn sở hữu.
- Giám sát subdomain takeover và cookie name collision.
- Dùng __Host- prefix cho session khi đáp ứng điều kiện.

### 7.3 Cookie parsing phải rõ ràng

Server nên:

- Xác định parser xử lý duplicate name thế nào.
- Từ chối request có duplicate session cookie nếu ambiguity ảnh hưởng xác thực.
- Không chọn session theo thứ tự tình cờ.
- Không log giá trị cookie khi báo duplicate.
- Kiểm thử qua cả CDN, reverse proxy và framework.
- Đảm bảo gateway không normalize hoặc reorder cookie theo cách làm đổi ý nghĩa.

### 7.4 Cookie không phải nơi lưu dữ liệu lớn

Cookie được gửi lặp lại trong request phù hợp, làm tăng băng thông và có thể vượt giới hạn header ở browser/proxy/server. Giữ cookie nhỏ, thường chỉ là opaque identifier hoặc preference ngắn. Không lưu profile, quyền chi tiết hoặc dữ liệu nghiệp vụ lớn trong cookie nếu không có lý do rõ ràng.

## 8. Cookie và CSRF protection

Cookie authentication khiến browser tự gửi credential theo cookie rules. Attacker có thể lợi dụng browser của nạn nhân gửi request tới ứng dụng đã đăng nhập nếu server không kiểm tra nguồn request và ý định của user.

### 8.1 Phân biệt request đọc dữ liệu và request thay đổi trạng thái

CSRF nguy hiểm nhất khi request tạo side effect:

- Thay đổi email, mật khẩu hoặc MFA.
- Tạo/chuyển tiền hoặc đặt hàng.
- Thay đổi quyền, địa chỉ hoặc thông tin thanh toán.
- Thực hiện thao tác quản trị.
- Tạo API key hoặc cấp quyền tích hợp.

Dùng method và endpoint đúng ngữ nghĩa. GET/HEAD không được thực hiện hành động thay đổi trạng thái. Nếu GET có side effect, browser navigation và prefetch có thể kích hoạt hành động ngoài dự kiến.

### 8.2 Anti-CSRF token

Với session cookie, server có thể dùng synchronizer token hoặc double-submit cookie pattern được thiết kế đúng. Token phải gắn với session/context, khó đoán, được xác minh server-side và không được coi là thay thế authentication.

Trong double-submit pattern, cần cân nhắc cookie scope, token binding và các tấn công cookie injection/tossing. Một cookie CSRF có thể không HttpOnly nếu frontend phải đọc để gửi header, nhưng session cookie vẫn nên HttpOnly. Không để CSRF token trở thành credential có quyền độc lập.

### 8.3 Kiểm tra Origin và Referer

Với state-changing request, server có thể kiểm tra Origin theo allowlist scheme/host/port phù hợp. Nếu Origin không có, policy có thể kiểm tra Referer theo threat model và môi trường.

- Parse URL bằng parser chuẩn, không dùng substring match.
- So sánh origin chính xác; không chấp nhận host có hậu tố giả.
- Xử lý null/missing Origin theo policy rõ ràng.
- Không tin header do proxy/client không đáng tin tự thêm.
- Giữ allowlist ngắn và được quản lý.

Origin validation bổ sung cho CSRF token; không dùng nó như authorization.

### 8.4 Fetch Metadata

Các header như `Sec-Fetch-Site`, `Sec-Fetch-Mode` và `Sec-Fetch-Dest` cho server thêm tín hiệu về ngữ cảnh request. Ví dụ, ứng dụng có thể từ chối một số state-changing request có `Sec-Fetch-Site: cross-site`.

Đây là lớp phòng vệ bổ sung. Cần có fallback cho browser không gửi Fetch Metadata và không chặn nhầm flow SSO/payment đã được phê duyệt.

### 8.5 SameSite trong chiến lược CSRF

- Lax thường là baseline hợp lý cho session cookie của nhiều web app.
- Strict phù hợp khi không cần cookie trong cross-site navigation, nhưng có thể ảnh hưởng deep link/SSO.
- None chỉ dùng khi cần cross-site cookie và phải đi cùng Secure.
- Cookie không có SameSite phụ thuộc default browser; đặt explicit.

Test luồng đăng nhập, logout, redirect, payment callback và external link trước khi đổi Strict/Lax/None. SameSite không loại bỏ nhu cầu bảo vệ endpoint thay đổi trạng thái.

### 8.6 CORS không phải CSRF defense

CORS chủ yếu kiểm soát việc JavaScript cross-origin đọc response và điều kiện browser gửi một số request không đơn giản sau preflight. HTML form và các request đơn giản vẫn có thể gửi tới server.

Không dựa vào việc browser chặn đọc response để bảo vệ hành động có side effect. Server phải xác thực request và kiểm tra CSRF độc lập.

## 9. Third-party cookie và partitioned cookie

Cookie từ bên thứ ba có thể cần cho SSO, payment, embedded application hoặc widget. Browser privacy controls ngày càng hạn chế third-party cookie, nên flow dựa vào chúng cần được review cả về bảo mật và khả năng hoạt động.

### 9.1 First-party và third-party context

Một cookie thường được xem trong ngữ cảnh site đang truy cập và site của request/resource. Khi user mở trực tiếp vendor site, cookie của vendor có thể là first-party; khi vendor được nhúng trong iframe/script trên site khác, cookie đó có thể là third-party.

Browser có thể block, partition hoặc yêu cầu cơ chế truy cập đặc biệt tùy privacy settings, browser version và user choice. Không giả định third-party cookie luôn được gửi.

### 9.2 SameSite=None; Secure

Một cookie cần cross-site context thường phải khai báo:

~~~http
Set-Cookie: vendor_session=value; Path=/; SameSite=None; Secure; HttpOnly
~~~

Cấu hình này không đảm bảo browser cho phép cookie. Browser có thể block third-party cookies theo policy hoặc user setting. Kiểm thử trong browser mục tiêu và có phương án thay thế như top-level redirect, authorization code flow hoặc API backend.

### 9.3 Partitioned cookies và CHIPS

Partitioned cookie (CHIPS) cho phép cookie trong third-party context được phân vùng theo top-level site trong browser hỗ trợ. Ví dụ vendor widget trên hai website khác nhau có thể nhận các cookie partition riêng, thay vì chia sẻ một third-party cookie toàn cục.

Ví dụ:

~~~http
Set-Cookie: __Host-widget-session=value; Path=/; Secure; HttpOnly; SameSite=None; Partitioned
~~~

Browser hỗ trợ CHIPS áp dụng partition key theo top-level site. Cookie partitioned vẫn cần flags và scope hợp lệ; nó không phải cách vượt qua user privacy settings hoặc bảo đảm mọi browser hỗ trợ.

### 9.4 Storage Access API và các flow nhúng

Một số browser cung cấp Storage Access API để embedded content yêu cầu quyền truy cập storage không partitioned trong điều kiện nhất định. Flow có thể cần user gesture hoặc permission. Không thiết kế login/payment phụ thuộc vào quyền này mà không có fallback.

### 9.5 SSO và identity provider

Review cookie của IdP theo các bước redirect thực tế:

1. Người dùng bắt đầu đăng nhập từ first-party app.
2. Browser điều hướng tới IdP.
3. IdP thiết lập session cookie.
4. IdP redirect về callback với authorization response.
5. Backend đổi code lấy token qua back channel.
6. Ứng dụng thiết lập session cookie first-party.

Ưu tiên authorization code flow phù hợp, state/nonce/PKCE theo giao thức và session first-party của ứng dụng. Tránh phụ thuộc silent iframe login nếu browser privacy policy có thể block third-party cookie.

### 9.6 Cookie từ payment và embedded vendor

Không yêu cầu vendor cookie có Domain rộng tới parent domain của ứng dụng. Tách origin, chỉ nhúng script/iframe cần thiết, giới hạn permission và kiểm tra hợp đồng dữ liệu. Nếu vendor không còn được sử dụng, gỡ tích hợp và xác nhận cookie cũ không còn được phát hành.

## 10. Privacy, consent và data minimization

Cookie policy review phải xem cả security và privacy. Cookie có thể là định danh trực tiếp hoặc pseudonymous identifier, và có thể tạo hồ sơ hành vi khi kết hợp với dữ liệu khác.

### 10.1 Phân loại mục đích

Các nhóm thường gặp:

- Strictly necessary: session, load balancing hoặc security state cần để cung cấp chức năng người dùng yêu cầu.
- Preferences: ngôn ngữ, giao diện hoặc lựa chọn hiển thị.
- Analytics: đo lường sử dụng và chất lượng.
- Advertising/targeting: theo dõi hoặc cá nhân hóa quảng cáo.
- Third-party functionality: chat, video, payment hoặc social embed.

Phân loại phải dựa vào mục đích và luật áp dụng, không chỉ dựa vào tên cookie. Cookie analytics không tự động là necessary chỉ vì đội sản phẩm muốn có số liệu.

### 10.2 Consent trước khi đặt cookie không thiết yếu

Ở những khu vực pháp lý yêu cầu consent, cookie không thiết yếu và các công nghệ tương đương phải tuân theo quy trình consent phù hợp. Consent phải được ghi nhận, có thể thay đổi/rút lại và phản ánh tới các vendor tương ứng.

Yêu cầu pháp lý khác nhau theo quốc gia, loại dữ liệu và mục đích. Làm việc với privacy/legal owner để xác định cơ sở xử lý, banner, retention và cách chứng minh consent; bài học kỹ thuật này không thay thế tư vấn pháp lý.

### 10.3 Consent state cũng là dữ liệu cần bảo vệ

Cookie lưu lựa chọn consent nên:

- Chứa trạng thái tối thiểu, không lưu hồ sơ cá nhân không cần thiết.
- Có lifetime và version policy rõ ràng.
- Được cập nhật khi danh mục vendor/purpose thay đổi.
- Không bị script tùy tiện ghi đè để bật tracking.
- Được tôn trọng ở mọi subdomain/app liên quan theo thiết kế.
- Có cách xử lý khi người dùng rút consent.

Không dùng một cookie consent chung ở parent domain nếu nhiều subdomain có mục đích và owner khác nhau mà chưa đánh giá.

### 10.4 Data minimization và retention

Chỉ lưu identifier cần thiết. Đặt thời hạn dựa trên mục đích, không dùng expiry vô hạn. Khi mục đích kết thúc, ngừng phát hành và xóa cookie theo đúng scope. Với analytics, giảm độ chi tiết và thời gian lưu theo privacy policy.

### 10.5 Cookie banner không thay thế policy kỹ thuật

Một banner đồng ý không làm cookie an toàn nếu cookie session thiếu Secure/HttpOnly hoặc analytics script gửi dữ liệu không được phép. Ngược lại, cookie flags đúng không tự chứng minh consent hợp lệ. Review hai lớp: browser enforcement và governance/privacy.


## 11. Quy trình vận hành cookie policy review

Review nên là quy trình lặp lại, có owner, bằng chứng và quyết định rõ ràng. Một lần quét thủ công trong DevTools không đủ để chứng minh mọi cookie đã được quản lý.

### 11.1 Khi nào cần review?

Thực hiện review:

- Trước khi phát hành authentication/session flow mới.
- Khi thêm subdomain, đổi domain, CDN hoặc reverse proxy.
- Khi tích hợp IdP, payment, analytics hoặc embedded vendor.
- Khi đổi SameSite, Domain, Path, Secure, HttpOnly hoặc lifetime.
- Khi nâng cấp browser support hoặc thay đổi frontend architecture.
- Khi có incident liên quan CSRF, session theft hoặc cookie leakage.
- Theo lịch định kỳ của security/privacy governance.
- Khi vendor thay đổi cookie, mục đích hoặc retention.

### 11.2 Các bước review

1. Xác định domain, subdomain, route và môi trường trong phạm vi.
2. Thu thập cookie từ response Set-Cookie và browser storage.
3. Đối chiếu source/config, vendor inventory và privacy register.
4. Xác định owner, purpose, data class và dependency cho từng cookie.
5. Đánh giá Domain, Path, Secure, HttpOnly, SameSite, prefix và Partitioned.
6. Đánh giá expiry, idle/absolute timeout, rotation và revocation.
7. Đánh giá CSRF, CORS, SSO, redirect và embedded flow.
8. Kiểm tra consent, data minimization và retention.
9. Tạo test matrix trên browser mục tiêu.
10. Ghi finding, severity, owner, due date và evidence.
11. Phê duyệt ngoại lệ có lý do, expiry và người chịu trách nhiệm.
12. Theo dõi remediation và kiểm tra lại sau rollout.

### 11.3 Mẫu quyết định cho từng cookie

| Câu hỏi review | Quyết định cần ghi |
|---|---|
| Cookie còn cần thiết? | Keep / Remove / Investigate |
| Có owner rõ? | Team và người chịu trách nhiệm |
| Purpose có được duyệt? | Necessary / Preference / Analytics / Other |
| Có chứa credential? | Yes/No và quyền được cấp |
| Scope tối thiểu? | Host-only/Domain, Path |
| Flags phù hợp? | Secure, HttpOnly, SameSite, Prefix, Partitioned |
| Lifetime hợp lý? | Session/Max-Age/Expires và server timeout |
| Có CSRF control? | Token/Origin/Fetch Metadata/other |
| Có consent/retention? | Policy reference và expiry |
| Có test evidence? | Browser/version, request, expected/actual |
| Finding và remediation? | Severity, owner, due date |

### 11.4 Phân loại finding

Có thể ưu tiên theo tác động:

- Critical/High: session cookie thiếu Secure trên production HTTP path; Domain rộng cho phép subdomain không tin cậy nhận session; session có thể bị fixation hoặc không revoke; cookie auth được gửi trong cross-site flow có side effect mà không có CSRF protection.
- Medium: SameSite không explicit; cookie không cần JavaScript nhưng thiếu HttpOnly; cookie lifetime dài hơn policy; duplicate cookie name gây parser ambiguity.
- Low/Informational: cookie preference không có owner rõ; cookie cũ không còn dùng nhưng không nhạy cảm; inventory thiếu evidence hoặc mô tả.

Severity cuối cùng cần xét exploitability, quyền session, exposure, browser behavior và compensating controls. Không áp dụng mức severity máy móc chỉ từ một flag.

## 12. Rollout thay đổi cookie policy

Thay đổi cookie flags có thể ảnh hưởng đăng nhập, SSO, payment callback, embedded content và API. Không triển khai trực tiếp trên toàn bộ người dùng nếu chưa hiểu luồng phụ thuộc.

### 12.1 Chuẩn bị trước thay đổi

- Lập danh sách cookie và consumer phụ thuộc.
- Ghi nhận behavior hiện tại bằng test account.
- Xác định browser/OS/webview support.
- Xác định tác động với redirect, iframe, subdomain và cross-site request.
- Chuẩn bị test case cho login/logout, MFA, refresh và recovery.
- Xác định metric theo dõi: login failure, session churn, CSRF rejection và callback error.
- Có cách rollback cấu hình và thu hồi cookie cũ.

### 12.2 Thay đổi theo từng bước

Ví dụ chuyển session cookie từ Domain cookie sang host-only và thêm prefix:

1. Xác nhận session chỉ cần trên một host.
2. Phát cookie mới theo policy host-only.
3. Cập nhật server đọc cookie mới và kiểm thử duplicate name.
4. Thu hồi session cũ hoặc cho migration có thời hạn rõ.
5. Xóa cookie cũ theo Domain/Path đã phát hành.
6. Theo dõi login, redirect, callback và session error.
7. Kết thúc compatibility window và bỏ code cũ.

Không giữ hai session cookie cùng tên ở nhiều scope nếu server parser không xử lý rõ.

### 12.3 Canary và rollback

Triển khai theo cohort hoặc staging/canary nếu kiến trúc hỗ trợ. Theo dõi:

- Tỷ lệ login success/failure.
- Session refresh/renewal failure.
- CSRF rejection theo route và browser.
- SSO callback và payment callback failure.
- Số lượng cookie mới/cũ xuất hiện.
- Error rate và support tickets.

Rollback cần khôi phục policy đã biết là hoạt động, đồng thời không vô tình mở lại cookie insecure hoặc Domain quá rộng. Nếu credential đã bị lộ, rollback flags không thay thế revoke/rotate.

### 12.4 Quan sát Set-Cookie tại edge

Cookie có thể bị thay đổi bởi application, gateway, proxy hoặc CDN. Kiểm tra header cuối cùng browser nhận được, không chỉ config ở source. Xác minh nhiều Set-Cookie header được giữ riêng; không gộp thành một header comma-separated vì Expires chứa dấu phẩy và cookie header có semantics riêng.

### 12.5 Quản lý ngoại lệ

Nếu một flow cần SameSite=None hoặc Domain cookie rộng, ghi lại:

- Business reason và flow cụ thể.
- Cookie name, owner và consumer.
- Rủi ro phát sinh và control bù.
- Browser/third-party dependency.
- Ngày review lại hoặc ngày hết hạn ngoại lệ.
- Người phê duyệt.

Ngoại lệ không có expiry hoặc owner thường trở thành cấu hình tồn tại mãi sau khi dependency đã biến mất.

## 13. Kiểm thử cookie policy trên browser

Kiểm thử cần xác minh cookie được đặt, lưu, gửi và xóa đúng trong các luồng thực tế. Header Set-Cookie đúng trên một response chưa chứng minh browser đã gửi cookie đúng ở request tiếp theo.

### 13.1 Kiểm tra Set-Cookie

Dùng môi trường test:

~~~http
HTTP/1.1 200 OK
Set-Cookie: __Host-session=test-session; Path=/; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
~~~

Xác nhận:

- Cookie được browser chấp nhận.
- Có Secure, HttpOnly và SameSite đúng policy.
- Không có Domain khi dùng __Host-.
- Path=/ khi dùng __Host-.
- Response qua HTTPS.
- Không có cookie trùng tên ở scope khác.

### 13.2 Kiểm tra request gửi cookie

Trong Network panel, kiểm tra request tới host/path phù hợp:

- HTTPS request có cookie theo policy.
- HTTP request không mang Secure cookie.
- Host khác không nhận host-only cookie.
- Path không phù hợp không mang cookie.
- Cross-site request có hành vi SameSite dự kiến.
- Credentialed fetch chỉ gửi cookie theo credentials mode và CORS policy.

Không copy giá trị cookie vào report. Ghi tên cookie, scope, flags và kết quả gửi/không gửi.

### 13.3 Kiểm tra CSRF

Tạo hai origin/site lab và thử:

1. Form cross-site gửi POST tới endpoint thay đổi trạng thái.
2. Fetch cross-origin với content type đơn giản.
3. Fetch với application/json gây preflight.
4. Request từ sibling subdomain cùng site.
5. Top-level navigation GET và POST.
6. Request không có CSRF token hoặc Origin không hợp lệ.

Xác nhận server từ chối request không hợp lệ và không có side effect. Đừng kết luận CORS đã chặn CSRF chỉ vì JavaScript không đọc được response.

### 13.4 Kiểm tra login và session lifecycle

- Đăng nhập tạo session identifier mới.
- Session cũ trước login không còn được chấp nhận nếu policy yêu cầu rotation.
- MFA/step-up thay đổi session state đúng.
- Idle timeout và absolute timeout được server enforce.
- Logout revoke server-side session.
- Cookie bị xóa đúng Domain/Path.
- Token/cookie cũ không thể tiếp tục truy cập sau revoke.
- Password reset hoặc account recovery vô hiệu hóa session theo policy.

### 13.5 Kiểm tra browser privacy và embedded flow

Thử trên browser/setting mục tiêu:

- Third-party cookies enabled và blocked.
- Private browsing/tracking protection.
- Embedded iframe.
- SSO redirect và callback.
- Payment hoặc identity provider.
- Partitioned cookie nếu dùng CHIPS.
- WebView/mobile browser nếu sản phẩm hỗ trợ.

Ghi browser/version, setting và expected/actual. Không giả định một browser profile đại diện cho mọi người dùng.

### 13.6 Kiểm tra cookie deletion và migration

Đặt cookie ở nhiều scope trong lab, sau đó gửi Set-Cookie expiry cho từng scope. Xác nhận cookie cũ biến mất và server không nhận duplicate session cookie. Test trường hợp browser còn cookie cũ từ phiên bản trước.

### 13.7 Test bằng curl

Có thể xem Set-Cookie bằng:

~~~bash
curl -i https://app.example.test/login
~~~

Curl không mô phỏng đầy đủ browser cookie jar, SameSite, third-party blocking, partitioning hoặc navigation context. Dùng browser automation/manual DevTools để xác nhận hành vi thực.

## 14. Lỗi vận hành thường gặp

### 14.1 Dùng Domain cookie cho mọi subdomain

Mở rộng session sang host không cần thiết. Ưu tiên host-only và SSO/token exchange khi cần chia sẻ danh tính.

### 14.2 Nghĩ Path tạo ranh giới bảo mật

Path chỉ điều khiển request matching. Tách ứng dụng khác trust level bằng hostname/origin riêng.

### 14.3 Thiếu Secure

Cookie có thể bị gửi qua HTTP nếu request phù hợp. Dùng HTTPS toàn bộ và Secure cho cookie nhạy cảm.

### 14.4 Thiếu HttpOnly cho session

JavaScript có thể đọc cookie session. Đặt HttpOnly khi frontend không cần đọc credential.

### 14.5 Dùng SameSite=None mà thiếu Secure

Browser hiện đại từ chối cấu hình này. Nếu thật sự cần cross-site cookie, dùng cả hai và test privacy controls.

### 14.6 Nghĩ SameSite thay thế CSRF token

SameSite có giới hạn, nhất là sibling subdomain và flow điều hướng. Bảo vệ state-changing request bằng CSRF control độc lập.

### 14.7 Dựa vào cookie mặc định của browser

Default có thể khác theo browser/version và có thể thay đổi. Đặt SameSite explicit và kiểm thử tương thích.

### 14.8 Không rotate session sau login

Session fixation có thể giữ identifier do attacker biết trước. Tạo session ID mới và revoke ID cũ sau xác thực/step-up.

### 14.9 Chỉ xóa cookie ở client khi logout

Cookie bị đánh cắp vẫn có thể dùng nếu server session còn hiệu lực. Revoke server-side session và xóa cookie đúng scope.

### 14.10 Xóa cookie sai Domain/Path

Cookie cũ vẫn tồn tại hoặc duplicate cookie gây lỗi. Ghi inventory scope và gửi expiry cho đúng name/domain/path.

### 14.11 Tin cookie parser xử lý duplicate giống nhau

Proxy và framework có thể chọn giá trị khác nhau. Xác định behavior, từ chối ambiguity với session và test end-to-end.

### 14.12 Không kiểm kê cookie bên thứ ba

Vendor thay đổi cookie hoặc mục đích mà policy không được cập nhật. Review định kỳ, gắn owner và loại bỏ tích hợp không còn cần.

### 14.13 Dùng third-party cookie làm dependency duy nhất

Browser có thể block hoặc partition. Thiết kế top-level redirect, back-channel exchange hoặc flow first-party có fallback.

### 14.14 Nghĩ consent banner đã giải quyết privacy

Consent UI không tự kiểm soát script và cookie. Phải enforce consent state ở tag manager, frontend, backend và vendor integration.

## 15. Checklist Cookie policy review

- [ ] Có inventory đầy đủ cookie từ app, gateway, IdP và vendor.
- [ ] Mỗi cookie có owner, purpose, data class và consumer.
- [ ] Cookie không còn mục đích đã được loại bỏ.
- [ ] Session cookie dùng Secure trong production HTTPS.
- [ ] Session cookie dùng HttpOnly nếu JavaScript không cần đọc.
- [ ] SameSite được đặt tường minh theo flow.
- [ ] SameSite=None đi cùng Secure và có fallback cho browser block third-party.
- [ ] Session cookie ưu tiên host-only; Domain chỉ dùng khi có lý do.
- [ ] Cookie session có thể dùng __Host- prefix khi đáp ứng điều kiện.
- [ ] Path không bị coi là security boundary.
- [ ] Không dựa vào port để cách ly cookie.
- [ ] Không có duplicate session cookie gây ambiguity.
- [ ] Cookie Domain không bao phủ subdomain không tin cậy.
- [ ] Cookie expiry phù hợp; server enforce idle/absolute timeout.
- [ ] Session ID rotate sau login và thay đổi privilege.
- [ ] Logout/revoke vô hiệu hóa session phía server.
- [ ] Cookie cũ được xóa đúng name, Domain và Path.
- [ ] State-changing request có CSRF protection.
- [ ] Origin/Referer và Fetch Metadata được đánh giá phù hợp.
- [ ] CORS không bị coi là CSRF defense.
- [ ] Third-party cookie và Partitioned/CHIPS flow đã được kiểm thử.
- [ ] Consent, purpose, retention và vendor sharing được phê duyệt.
- [ ] Set-Cookie headers được kiểm tra ở edge/browser cuối cùng.
- [ ] Rollout có canary, monitoring, rollback và owner.
- [ ] Có evidence browser test cho login, logout, SSO, CSRF và expiry.

## 16. Bài thực hành

Thực hiện trên domain lab do bạn kiểm soát với tài khoản và cookie giả. Không thử nghiệm trên session của người khác.

### Bài 1: Lập cookie inventory

Mở một ứng dụng lab, ghi tất cả cookie từ Application/Storage và Network Set-Cookie. Điền name, owner, purpose, Domain, Path, flags, lifetime và consumer. Đánh dấu cookie chưa rõ owner.

### Bài 2: Host-only và Domain

Tạo hai host lab thuộc cùng domain. Đặt một cookie không có Domain và một cookie Domain ở parent domain. Quan sát request nào mang từng cookie. Ghi lại rủi ro khi subdomain không cùng mức tin cậy.

### Bài 3: Secure, HttpOnly và SameSite

Tạo cookie test với các tổ hợp flags. Quan sát browser chấp nhận/từ chối và request gửi cookie trong HTTPS, HTTP, same-site, cross-site và iframe. Không dùng session thật.

### Bài 4: Cookie prefix

Thử phát __Host-session với Path=/, Secure và không có Domain. Sau đó cố đặt biến thể sai như có Domain hoặc thiếu Secure trong lab. Quan sát browser từ chối theo hỗ trợ prefix.

### Bài 5: Session lifecycle

Tạo login/logout test. Xác nhận session ID rotate sau login, idle/absolute timeout được server enforce và logout revoke session. Thử dùng lại cookie cũ để xác nhận bị từ chối.

### Bài 6: Duplicate cookie và cookie tossing

Trong lab, tạo cookie cùng tên ở Path hoặc Domain khác nhau. Quan sát Cookie header và parser phía server. Xác nhận session endpoint từ chối trường hợp ambiguous.

### Bài 7: CSRF và SameSite

Tạo site lab khác và sibling subdomain. Gửi form cross-site tới endpoint test có side effect giả lập. So sánh behavior Strict/Lax/None, sau đó bật CSRF token và Origin validation để xác nhận request trái phép bị chặn.

### Bài 8: Third-party và partitioned cookie

Nhúng widget lab trong hai top-level site. Kiểm tra behavior khi third-party cookie được cho phép, bị block và khi dùng Partitioned cookie trong browser hỗ trợ. Ghi fallback khi storage access không có.

### Bài 9: Consent và vendor inventory

Tạo analytics cookie giả. Xác nhận cookie/script không được kích hoạt trước consent khi policy yêu cầu; rút consent và kiểm tra tag/vendor dừng xử lý, cookie được xử lý theo policy.

### Bài 10: Rollout tabletop

Giả lập thay Domain cookie thành host-only. Viết kế hoạch canary, migration, xóa cookie cũ, metric theo dõi, rollback và điều kiện kết thúc compatibility window.

## 17. Câu hỏi tự kiểm tra

**1. Host-only cookie khác Domain cookie thế nào?**

Host-only cookie chỉ gửi tới host đã đặt nó. Domain cookie có thể được gửi tới host phù hợp trong domain tree và mở rộng phạm vi tin cậy.

**2. Path có phải security boundary không?**

Không. Path chỉ ảnh hưởng request matching và không cô lập các ứng dụng cùng host như một sandbox.

**3. Secure bảo vệ điều gì?**

Yêu cầu browser chỉ gửi cookie qua secure channel, thông thường là HTTPS. Nó không che cookie khỏi người điều khiển browser.

**4. HttpOnly có ngăn mọi tác động của XSS không?**

Không. Nó ngăn JavaScript trang đọc cookie trực tiếp, nhưng XSS vẫn có thể thao tác trong session và gọi API theo quyền của trang.

**5. SameSite=None cần điều kiện gì?**

Browser hiện đại yêu cầu Secure. Third-party cookie vẫn có thể bị block theo privacy policy hoặc user setting.

**6. __Host- prefix yêu cầu gì?**

Cookie phải được đặt từ secure origin, có Secure, Path=/ và không có Domain.

**7. Max-Age và Expires khác nhau thế nào?**

Max-Age là thời lượng tính bằng giây; Expires là thời điểm hết hạn. Khi cả hai cùng có, Max-Age được ưu tiên.

**8. Vì sao phải rotate session sau login?**

Để tránh tiếp tục dùng identifier được tạo trước xác thực và giảm session fixation.

**9. SameSite có thay thế CSRF token không?**

Không. SameSite là lớp giảm thiểu; endpoint thay đổi trạng thái vẫn cần CSRF controls theo threat model.

**10. Logout có chỉ cần xóa cookie phía browser không?**

Không. Phải revoke/invalidate session phía server và xóa cookie đúng Domain/Path.

**11. Cookie partitioned giải quyết vấn đề gì?**

Nó tách cookie third-party theo top-level site trong browser hỗ trợ, hạn chế chia sẻ cookie toàn cục giữa các website nhúng cùng vendor.

**12. Vì sao phải kiểm thử browser thay vì chỉ xem Set-Cookie?**

Vì browser privacy controls, SameSite context, redirect, iframe và cookie jar quyết định cookie có được chấp nhận/gửi hay không; curl không mô phỏng đầy đủ các quy tắc này.

## Ghi nhớ

Cookie policy review phải bắt đầu từ inventory và purpose, sau đó đánh giá scope, flags, lifetime, session lifecycle, CSRF, third-party behavior và privacy. Ưu tiên host-only session cookie với Secure, HttpOnly, SameSite phù hợp; dùng prefix khi đáp ứng điều kiện; rotate và revoke session ở server; kiểm thử browser thật trước rollout. Mọi ngoại lệ cần owner, lý do, control bù và thời điểm review lại.

## Tài liệu tham khảo

- [RFC 6265: HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265.html)
- [IETF draft 6265bis: Cookies: HTTP State Management Mechanism](https://datatracker.ietf.org/doc/draft-ietf-httpbis-rfc6265bis/)
- [MDN: HTTP cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Cookies)
- [MDN: Set-Cookie header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie)
- [MDN: SameSite cookies explained](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie#samesitesamesite-value)
- [Chrome: CHIPS (Cookies Having Independent Partitioned State)](https://developer.chrome.com/docs/privacy-sandbox/chips/)
- [OWASP: Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP: Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [OWASP Web Security Testing Guide](https://owasp.org/www-project-web-security-testing-guide/)
