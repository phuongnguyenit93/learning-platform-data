# Token leak: phát hiện, cô lập và khôi phục sau khi token bị lộ

Token là thông tin xác thực hoặc bằng chứng cấp quyền mà ứng dụng dùng để nhận diện phiên, người dùng, client hoặc quyền truy cập. Trong ứng dụng web, token có thể xuất hiện trong cookie, bộ nhớ browser, header HTTP, URL callback, log, telemetry, source code, artifact build hoặc thông điệp giữa các cửa sổ. Khi token rơi vào tay người không được phép, họ có thể sử dụng token trong thời hạn và phạm vi quyền mà token cho phép.

Ứng phó token leak cần xử lý đồng thời hai mục tiêu: ngăn token tiếp tục được sử dụng và xác định phạm vi ảnh hưởng. Xóa chuỗi token khỏi nơi nhìn thấy không thu hồi quyền đã cấp. Đổi mật khẩu người dùng cũng không nhất thiết vô hiệu hóa access token, refresh token, session cookie hoặc API key đã phát hành. Cần xác định đúng loại credential, cơ chế xác thực và khả năng thu hồi ở phía server.

Bài học này xây dựng quy trình xử lý sự cố token leak trong hệ thống web: nhận diện dấu hiệu, phân loại token, bảo toàn bằng chứng, containment, revoke/rotate, điều tra hành vi sử dụng, khôi phục dịch vụ và ngăn tái diễn. Nội dung tập trung vào ranh giới trình duyệt, origin, cookie và ứng dụng web.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt session cookie, access token, refresh token, API key và authorization code.
- Nhận diện các vị trí token có thể bị lộ trong ứng dụng browser.
- Đánh giá mức độ nghiêm trọng theo quyền, phạm vi, thời hạn và bằng chứng sử dụng.
- Xác định thứ tự containment để ngăn token bị lạm dụng.
- Thu hồi session, refresh token, access token và API key theo cơ chế tương ứng.
- Xử lý JWT và token stateless khi không có cơ chế revoke trực tiếp.
- Điều tra access log, audit log, telemetry và dấu hiệu sử dụng bất thường.
- Bảo toàn bằng chứng mà không tiếp tục phát tán giá trị bí mật.
- Khắc phục nguồn rò rỉ trong frontend, backend, CI/CD, log và dịch vụ bên thứ ba.
- Kiểm tra cookie, storage, URL, Referrer Policy, CSP và postMessage.
- Xây dựng runbook, checklist và bài diễn tập ứng phó token leak.

## 1. Token leak là gì?

Token leak là tình huống một credential hoặc bearer token bị tiết lộ tới người, hệ thống hoặc thành phần không được phép truy cập. Người có token có thể sử dụng token như chủ thể đã được cấp quyền, tùy thuộc vào loại token, audience, scope, thời hạn, binding và các kiểm tra bổ sung.

Ví dụ:

- Access token bị ghi vào console hoặc log frontend.
- Refresh token nằm trong localStorage và bị lấy qua XSS.
- Session cookie bị gửi tới domain không mong muốn.
- API key được commit vào repository công khai.
- Token xuất hiện trong URL và bị lưu trong browser history, proxy log hoặc Referer.
- Authorization code bị lộ trong callback URL hoặc log.
- Token được truyền qua postMessage tới sai origin.
- File cấu hình hoặc source map chứa credential đã bundle vào tài nguyên public.
- Screenshot, ticket hoặc bản ghi hỗ trợ khách hàng chứa token chưa được redact.

### 1.1 Token leak khác với mật khẩu bị lộ

Mật khẩu thường là thông tin dùng để xác thực và cấp token mới. Token đang hoạt động có thể cho phép truy cập trực tiếp mà không cần biết mật khẩu.

Do đó:

- Đổi mật khẩu có thể không làm session hiện tại bị thu hồi.
- Thu hồi session cookie không nhất thiết thu hồi refresh token độc lập.
- Revoke access token không nhất thiết thu hồi API key.
- Xóa token khỏi repository không xóa bản sao trong fork, cache, log hoặc lịch sử Git.
- Token đã hết hạn vẫn có thể là bằng chứng quan trọng về cách rò rỉ.

Khi ứng phó, cần xác định credential thực tế bị lộ và các credential có thể được tạo ra hoặc truy cập thông qua nó.

### 1.2 Exposure, compromise và abuse

Phân biệt ba trạng thái:

- **Exposure:** token đã xuất hiện ở vị trí người không được phép có thể truy cập.
- **Compromise:** có bằng chứng hoặc cơ sở đáng tin cậy cho thấy người không được phép đã kiểm soát token.
- **Abuse:** token đã được dùng để truy cập hoặc thực hiện hành động trái phép.

Cả ba tình huống đều cần đánh giá. Không thấy request đáng ngờ cũng không chứng minh token chưa bị dùng; log có thể thiếu hoặc thời gian lưu không đủ.

## 2. Phân loại token trước khi xử lý

Không dùng một quy trình revoke chung cho mọi loại token. Xác định issuer, subject, audience, scope, thời hạn và cơ chế lưu trữ trước khi chọn hành động.

| Loại credential | Mục đích | Cơ chế thu hồi thường dùng |
|---|---|---|
| Session cookie | Đại diện phiên đăng nhập browser | Invalidate session ở server, rotate session ID |
| Access token | Truy cập API trong thời hạn và scope nhất định | Revocation, denylist, introspection hoặc chờ hết hạn nếu không có revoke |
| Refresh token | Xin access token mới | Revoke token hoặc toàn bộ token family/session |
| API key | Xác thực ứng dụng hoặc tích hợp | Disable key, tạo key mới, cập nhật consumer |
| OAuth authorization code | Đổi lấy token trong luồng OAuth | Thường dùng một lần, thời hạn ngắn; xử lý state và client |
| CSRF token | Chống request giả mạo trong một phiên hoặc luồng | Rotate session/token binding theo thiết kế |
| Password reset token | Cho phép đặt lại mật khẩu | Invalidate token, hoàn tất hoặc hủy luồng reset |
| Signed URL | Cấp quyền truy cập tài nguyên trong thời gian giới hạn | Revoke object/policy nếu hỗ trợ, đổi signing key hoặc chờ hết hạn |

### 2.1 Session cookie

Session cookie thường chứa session identifier. Server tra cứu identifier để xác định session và trạng thái đăng nhập.

Nếu cookie bị lộ, cần invalidate session tương ứng ở server. Chỉ xóa cookie trên browser của người dùng không ngăn bản sao đã bị đánh cắp tiếp tục được gửi từ thiết bị khác.

Nếu hệ thống dùng session ticket tự chứa, cần hiểu cơ chế validation và expiry trước khi tuyên bố đã revoke.

### 2.2 Access token và refresh token

Access token thường có scope, audience và thời hạn. Bearer token có nghĩa là bên giữ token có thể sử dụng nó; không được giả định người gửi request chính là người dùng đã đăng nhập ban đầu.

Refresh token có thể cấp access token mới trong thời gian dài. Khi refresh token bị lộ, chỉ revoke access token hiện tại là chưa đủ nếu attacker vẫn có thể đổi refresh token lấy token mới.

Nếu dùng refresh token rotation:

- Revoke token bị lộ.
- Kiểm tra token family và session liên quan.
- Phát hiện reuse của refresh token cũ.
- Thu hồi family khi phát hiện reuse theo chính sách.
- Yêu cầu người dùng xác thực lại.
- Kiểm tra access token được phát hành từ refresh token đó.

### 2.3 API key và service credential

API key có thể đại diện cho service account hoặc tích hợp với quyền rộng. Cần xác định consumer nào đang sử dụng key, nơi lưu key và khả năng tạo key thay thế.

Với key đang phục vụ production, có thể cần quy trình chuyển đổi có kiểm soát: tạo key mới, cập nhật consumer, xác nhận hoạt động, rồi disable key cũ. Nếu key bị khai thác hoặc có quyền rất cao, ưu tiên disable ngay và chấp nhận gián đoạn theo mức độ sự cố.

### 2.4 JWT không tự cung cấp cơ chế revoke

JWT là định dạng token có thể được ký và xác minh offline. Claim `exp` chỉ cho biết thời điểm hết hạn; nó không tự cung cấp cơ chế thu hồi.

Cần kiểm tra:

- Issuer và audience.
- Thời hạn `exp` và thời điểm `iat`.
- Subject và scope/role.
- Signing key và `kid`.
- Cơ chế denylist hoặc token version.
- Verifier có kiểm tra trạng thái session hay chỉ kiểm tra chữ ký.

Không gửi JWT production tới website decoder công khai. JWT payload thường chỉ được Base64URL encode, không được mã hóa; nó có thể chứa thông tin nhạy cảm.

## 3. Những đường token có thể bị lộ trong browser

Ứng dụng web có nhiều điểm chuyển tiếp dữ liệu. Khi điều tra, cần dựng lại đường đi từ nơi token được tạo tới nơi nó được lưu, sử dụng, ghi log hoặc gửi đi.

### 3.1 URL, query string và fragment

Không đặt bearer token hoặc session identifier trong URL nếu có thể tránh.

URL có thể bị lưu ở:

- Browser history.
- Access log của web server, reverse proxy và CDN.
- Analytics và telemetry.
- Screenshot, clipboard hoặc ticket hỗ trợ.
- Referer gửi tới tài nguyên hoặc trang khác, tùy Referrer Policy và browser.
- Hệ thống quan sát lỗi và công cụ ghi lại session.

Ví dụ dạng rủi ro:

~~~text
https://app.example.test/callback?access_token=REDACTED
https://app.example.test/reset?token=REDACTED
~~~

Nếu phát hiện token trong URL, cần kiểm tra log và các hệ thống nhận URL. Xóa query khỏi thanh địa chỉ sau khi tải trang không xóa bản ghi đã được tạo trước đó.

OAuth authorization code có thể xuất hiện trong callback URL theo response mode được thiết kế. Code phải dùng một lần, có thời hạn ngắn, được ràng buộc với client và PKCE khi áp dụng; không được xử lý như access token dài hạn.

### 3.2 localStorage và sessionStorage

Web Storage có thể được đọc bởi JavaScript chạy cùng origin. Nếu có XSS, script độc hại có thể lấy token trong localStorage hoặc sessionStorage.

Không lưu refresh token hoặc credential dài hạn trong Web Storage nếu kiến trúc có lựa chọn an toàn hơn. Dữ liệu trong sessionStorage vẫn có thể bị JavaScript cùng origin đọc; tên "session" không phải một cơ chế bảo mật chống XSS.

### 3.3 Cookie

Cookie không có `HttpOnly` có thể bị JavaScript đọc qua `document.cookie`. Cookie có `HttpOnly` không thể được đọc bằng JavaScript thông thường, nhưng browser vẫn gửi cookie theo quy tắc cookie khi request phù hợp.

HttpOnly giảm khả năng trích xuất cookie qua XSS nhưng không ngăn XSS thực hiện hành động thay người dùng trong phiên đang hoạt động.

Cookie nhạy cảm cần xem xét:

- `Secure`: chỉ gửi qua HTTPS.
- `HttpOnly`: ngăn JavaScript đọc cookie.
- `SameSite`: kiểm soát một số ngữ cảnh gửi cookie cross-site.
- `Path` và `Domain`: giới hạn phạm vi gửi.
- Thời hạn và cơ chế rotation.
- Session invalidation ở server.

### 3.4 Authorization header và API client

Access token thường được gửi trong header:

~~~http
Authorization: Bearer REDACTED
~~~

Header có thể bị ghi vào debug log frontend/backend, reverse proxy, API gateway, APM trace, HTTP client interceptor, error report, HAR file hoặc network capture.

Mặc định phải redact Authorization header và các header chứa credential khỏi log, trace và artifact chia sẻ.

### 3.5 postMessage và iframe

Nếu host gửi token bằng `postMessage` với target origin wildcard, dữ liệu có thể tới document không còn là origin dự kiến sau khi cửa sổ điều hướng.

Khi truyền message:

- Dùng `targetOrigin` chính xác.
- Receiver xác minh `event.origin`.
- Receiver xác minh `event.source`.
- Chỉ gửi dữ liệu tối thiểu.
- Không gửi refresh token hoặc secret dài hạn cho widget nếu không cần.
- Validate message schema và trạng thái handshake.

Origin validation giúp bảo vệ kênh message nhưng không thay thế authorization phía server.

### 3.6 Source map và bundle frontend

Source map có thể làm lộ mã nguồn và các giá trị bị hardcode. Bundle cũng có thể chứa token hoặc API key nếu build pipeline đưa secret vào biến frontend.

Mọi giá trị được gửi xuống browser đều có thể được người dùng tải và phân tích. Không đặt secret server-side trong frontend, kể cả khi biến có tiền tố "private" hoặc chỉ được dùng trong một route ít hiển thị.

Nếu token bị bundle vào artifact public, cần xem token là đã lộ và revoke/rotate theo loại credential. Gỡ file map hoặc bundle khỏi CDN không thay thế việc thu hồi token.

### 3.7 Service worker, cache và offline storage

Service worker có thể intercept request và cache response. Cache API, IndexedDB hoặc cơ chế offline có thể lưu dữ liệu chứa token hoặc response nhạy cảm.

Điều tra:

- Service worker nào đang hoạt động.
- Cache nào chứa request/response nhạy cảm.
- IndexedDB và local database có giữ credential không.
- Có logic cache Authorization header hoặc URL chứa token không.
- Response có `Cache-Control` phù hợp không.
- Các thiết bị offline có thể giữ bản sao bao lâu.

Không xóa cache của người dùng rồi kết luận token đã revoke. Server vẫn phải vô hiệu hóa credential.

### 3.8 Third-party script và extension

Script bên thứ ba chạy trong document có thể truy cập nhiều dữ liệu mà trang cho phép. Extension có quyền phù hợp cũng có thể quan sát hoặc thay đổi nội dung trang.

Nếu token xuất hiện trong DOM, global variable hoặc Web Storage, hãy đánh giá tất cả script cùng origin và bên thứ ba được nhúng trong trang. Kiểm tra thay đổi dependency, tag manager và extension trong môi trường liên quan.

## 4. Phát hiện và xác nhận sự cố

Không cần chờ có bằng chứng sử dụng trái phép mới bắt đầu containment. Nhưng cần xác minh đủ để tránh revoke nhầm credential và gây gián đoạn diện rộng.

### 4.1 Nguồn phát hiện

Sự cố có thể được phát hiện qua:

- Secret scanning trong Git hoặc CI.
- Cảnh báo từ cloud provider hoặc API provider.
- Token xuất hiện trong log hoặc ticket.
- Người dùng báo đăng nhập lạ.
- Audit log cho thấy hành động ngoài dự kiến.
- Nhiều IP hoặc vị trí khác nhau dùng cùng session.
- Refresh token reuse.
- Request bất thường tới API nhạy cảm.
- Phản hồi từ bug bounty hoặc security researcher.
- Báo cáo rò rỉ từ dịch vụ bên thứ ba.

### 4.2 Xác minh token mà không phát tán token

Không copy token đầy đủ vào chat, issue, email, screenshot hoặc báo cáo. Khi cần đối chiếu:

- Giữ bản bằng chứng trong kho được kiểm soát quyền.
- Redact phần lớn giá trị.
- Dùng fingerprint phù hợp để liên kết sự kiện.
- Ghi token type, issuer, subject hoặc key identifier nếu có thể lấy an toàn.
- Ghi thời gian phát hiện và nơi xuất hiện.
- Hạn chế người có quyền truy cập raw evidence.

Với token có entropy cao, có thể dùng HMAC-SHA-256 với khóa nội bộ dành riêng cho điều tra để tạo fingerprint. Không dùng fingerprint làm credential và không ghi khóa HMAC vào log.

### 4.3 Xác định phạm vi

Cần trả lời:

- Token thuộc người dùng, service account hay ứng dụng nào?
- Token được issuer nào phát hành?
- Token có audience và scope gì?
- Token còn hiệu lực không?
- Token có thể tạo token khác không?
- Có bản sao ở những hệ thống nào?
- Ai có thể truy cập vị trí bị lộ?
- Có bằng chứng token đã được dùng không?
- Có credential liên quan nào cũng cần rotate không?

Nếu không xác định được loại token hoặc phạm vi, xử lý theo giả định thận trọng và escalate tới chủ sở hữu hệ thống xác thực.

## 5. Đánh giá mức độ nghiêm trọng

Severity phụ thuộc vào quyền token và mức độ tiếp xúc, không chỉ độ dài chuỗi hoặc nơi phát hiện.

| Mức độ | Ví dụ | Hướng phản ứng |
|---|---|---|
| Critical | Token quản trị hoặc signing key có quyền rộng bị công khai; có bằng chứng truy cập dữ liệu hoặc thay đổi hệ thống | Containment khẩn cấp, revoke/rotate ngay, điều tra diện rộng |
| High | Refresh token, session của tài khoản nhạy cảm hoặc API key production bị lộ ra ngoài phạm vi kiểm soát | Revoke/rotate nhanh, kiểm tra hành vi và credential liên quan |
| Medium | Access token giới hạn scope, thời hạn ngắn, vị trí lộ có quyền truy cập hạn chế | Đánh giá exposure, revoke nếu còn hiệu lực, theo dõi sử dụng |
| Low | Token thử nghiệm đã hết hạn, chỉ dùng trong lab và không có quyền với hệ thống thật | Xác nhận phạm vi, loại bỏ nguồn lộ và ghi nhận |

Không hạ mức độ chỉ vì token đã hết hạn nếu nó có thể cho biết signing secret, quy trình phát hành hoặc cấu trúc nội bộ. Cũng không nâng mức độ chỉ vì token có định dạng JWT; cần xem quyền và khả năng sử dụng thực tế.

### 5.1 Các yếu tố tăng mức độ

- Token còn hiệu lực và có thời hạn dài.
- Token có quyền admin, write, billing hoặc dữ liệu nhạy cảm.
- Token có thể tạo token khác.
- Token không có audience giới hạn.
- Token bị công khai trên internet hoặc repository public.
- Có bằng chứng sử dụng từ IP, thiết bị hoặc user-agent bất thường.
- Token dùng chung giữa nhiều service.
- Không có cơ chế revoke nhanh.
- Có nhiều bản sao trong log, cache hoặc artifact.

### 5.2 Các yếu tố giảm phạm vi ảnh hưởng

- Token đã hết hạn và verifier thực sự từ chối token hết hạn.
- Token chỉ dùng trong môi trường cô lập.
- Token có scope hẹp và audience giới hạn.
- Credential đã được revoke trước khi bị truy cập.
- Bằng chứng cho thấy vị trí lộ chỉ có quyền truy cập nội bộ giới hạn.

Các yếu tố này hỗ trợ đánh giá nhưng không thay thế xác minh.

## 6. Quy trình ứng phó sự cố

Quy trình nên có người chỉ huy sự cố, người phụ trách identity/token, chủ sở hữu ứng dụng, vận hành hạ tầng và người phụ trách truyền thông. Trong sự cố thật, dùng kênh liên lạc được phê duyệt; không gửi token qua kênh trao đổi.

~~~mermaid
flowchart TD
    A["Phát hiện token có thể bị lộ"] --> B["Xác minh loại token và phạm vi"]
    B --> C["Bảo toàn bằng chứng đã redact"]
    C --> D["Đánh giá quyền và khả năng sử dụng"]
    D --> E["Containment: revoke hoặc disable"]
    E --> F["Rotate credential và sửa nguồn lộ"]
    F --> G["Điều tra log và hành vi sử dụng"]
    G --> H["Khôi phục và xác minh"]
    H --> I["Theo dõi sau sự cố"]
    I --> J["Post-incident review"]
~~~

### 6.1 Ghi nhận và mở incident

Ghi lại thời điểm phát hiện, người hoặc hệ thống báo cáo, vị trí token xuất hiện, token type dự kiến, ứng dụng, môi trường, owner, thời điểm phát hành và hết hạn nếu biết.

Dùng mã incident để liên kết ticket, log và bằng chứng. Không ghi token nguyên vẹn trong tiêu đề hoặc nội dung ticket.

### 6.2 Xác minh và bảo toàn bằng chứng

Trước khi xóa artifact hoặc rewrite history, lưu bằng chứng cần thiết vào kho có quyền truy cập hạn chế. Bằng chứng nên chứa nguồn, thời gian, commit/release, metadata và giá trị đã redact hoặc fingerprint.

Không trì hoãn revoke một token có quyền cao chỉ để thu thập đầy đủ bằng chứng. Thu thập metadata cần thiết nhanh chóng, rồi containment theo mức độ rủi ro.

### 6.3 Containment

Chọn hành động có thể chặn việc sử dụng token ngay:

- Disable API key hoặc credential bị lộ.
- Revoke session hoặc refresh token.
- Invalidate token family hoặc toàn bộ phiên liên quan.
- Thêm denylist cho token cụ thể nếu kiến trúc hỗ trợ.
- Tạm dừng integration bị xâm phạm.
- Chặn đường truy cập tới artifact public chứa secret.
- Giảm scope hoặc tạm vô hiệu hóa chức năng bị ảnh hưởng.
- Thu hồi quyền của service account nếu cần.

Containment phải tính đến tác động tới người dùng và service. Với token có quyền admin hoặc có bằng chứng bị khai thác, ưu tiên ngăn truy cập trái phép hơn duy trì tính liên tục của tích hợp.

### 6.4 Rotate credential

Sau khi revoke hoặc disable credential cũ:

- Tạo credential mới từ issuer hoặc secret manager.
- Cập nhật consumer và deployment.
- Xác minh consumer dùng credential mới.
- Disable credential cũ ở tất cả nơi phát hành.
- Kiểm tra không còn bản sao cũ được chấp nhận.
- Theo dõi lỗi xác thực và request thất bại.

Không đưa credential mới vào ticket, source code hoặc command history. Dùng secret manager hoặc cơ chế phân phối bí mật được phê duyệt.

### 6.5 Điều tra việc sử dụng

Tìm kiếm hoạt động từ thời điểm token có thể bị lộ đến lúc revoke có hiệu lực:

- Request thành công tới API nhạy cảm.
- Đăng nhập hoặc refresh bất thường.
- Thay đổi quyền, email, MFA hoặc thông tin tài khoản.
- Tạo API key hoặc service credential mới.
- Export hoặc đọc dữ liệu.
- Thay đổi cấu hình, webhook hoặc callback URL.
- Tải artifact, file hoặc dữ liệu ngoài dự kiến.
- Hành động phát sinh từ session hoặc token liên quan.

Dùng log từ issuer, API gateway, ứng dụng và hệ thống đích. Đồng bộ thời gian giữa các nguồn để dựng timeline.

### 6.6 Eradication và khắc phục nguồn lộ

Xác định nguyên nhân gốc và loại bỏ đường rò rỉ:

- Xóa secret khỏi frontend và build configuration.
- Sửa log redaction.
- Loại token khỏi URL hoặc telemetry.
- Cập nhật postMessage targetOrigin và validation.
- Chuyển credential sang secret manager.
- Sửa quyền repository và artifact storage.
- Loại script bên thứ ba không cần thiết.
- Sửa XSS hoặc lỗ hổng cho phép đọc token.
- Xóa cache và artifact public sau khi đã bảo toàn bằng chứng.
- Cập nhật quy tắc secret scanning.

Nếu token xuất hiện trong Git history, cần xử lý repository history và các bản fork/mirror theo quy trình. Rewrite history không thu hồi credential; revoke/rotate vẫn là bước bắt buộc.

### 6.7 Khôi phục và xác minh

Sau khi rotate:

- Kiểm tra login và refresh flow.
- Kiểm tra API client dùng credential mới.
- Kiểm tra token cũ bị từ chối.
- Kiểm tra session cũ không còn hoạt động.
- Kiểm tra service-to-service integration.
- Kiểm tra log không còn ghi secret.
- Kiểm tra CDN, cache, bucket và artifact public.
- Kiểm tra cảnh báo và dashboard sau deploy.

Không đóng incident chỉ vì token mới hoạt động. Cần chứng minh token cũ không còn được chấp nhận và nguồn lộ đã được xử lý.

## 7. Thu hồi theo từng loại token

### 7.1 Session cookie và session server-side

Với session store server-side, tìm session theo identifier đã được đối chiếu an toàn rồi đánh dấu revoked hoặc xóa session. Nếu không thể tìm theo token raw, dùng lookup/fingerprint được thiết kế từ trước.

Cân nhắc:

- Invalidate session bị lộ.
- Revoke tất cả session của tài khoản nếu không xác định được session cụ thể.
- Rotate session ID sau đăng nhập hoặc thay đổi quyền.
- Yêu cầu xác thực lại.
- Kiểm tra remember-me cookie và persistent login token.
- Revoke session trên thiết bị khác nếu chính sách yêu cầu.

Nếu dùng cookie chứa signed/encrypted ticket tự xác thực, cần xác định cách server kiểm tra ticket và khả năng thu hồi theo key, version hoặc session epoch.

### 7.2 Refresh token rotation

Một thiết kế rotation tốt phát hành refresh token mới mỗi lần sử dụng và đánh dấu token cũ đã dùng. Nếu token cũ được dùng lại, hệ thống có thể nhận diện dấu hiệu theft và revoke token family.

Khi xử lý leak:

1. Xác định token family và subject liên quan.
2. Revoke refresh token bị lộ.
3. Revoke các token descendant nếu có.
4. Thu hồi access token liên quan nếu có cơ chế.
5. Kiểm tra sự kiện reuse và thời gian phát hành.
6. Yêu cầu xác thực lại.
7. Kiểm tra thiết bị và phiên liên quan.

Không chỉ xóa refresh token khỏi browser storage. Bản sao ở attacker vẫn có thể hoạt động nếu issuer chưa revoke.

### 7.3 Access token opaque

Nếu access token là opaque reference token, resource server có thể gọi introspection endpoint hoặc tra cứu trạng thái ở issuer.

Revoke token ở issuer và xác minh resource server thực sự kiểm tra trạng thái mới. Cache introspection có thể làm token vẫn được chấp nhận trong một khoảng thời gian; cần biết TTL và cơ chế invalidation.

### 7.4 JWT access token

JWT được xác minh offline thường khó thu hồi riêng lẻ. Các lựa chọn:

- Giảm thời hạn access token để giới hạn cửa sổ sử dụng.
- Dùng denylist theo `jti` hoặc fingerprint tới hết `exp`.
- Kiểm tra session/token version ở server.
- Dùng introspection thay vì chỉ xác minh chữ ký nếu yêu cầu revoke nhanh.
- Xoay signing key khi key ký bị lộ, đồng thời loại bỏ key cũ khỏi toàn bộ verifier.
- Revoke refresh token để ngăn cấp access token mới.

Xoay signing key có thể ảnh hưởng toàn bộ token được ký bằng key đó. Chỉ thực hiện sau khi xác định phạm vi, quy trình key rotation và thời gian chuyển verifier. Nếu verifier vẫn chấp nhận key cũ, rotation chưa có tác dụng thu hồi.

### 7.5 API key

Khi API key bị lộ:

1. Xác định owner, consumer và scope.
2. Kiểm tra log theo key identifier hoặc fingerprint.
3. Tạo key mới nếu cần duy trì dịch vụ.
4. Phân phối key mới qua secret manager.
5. Xác minh tất cả consumer đã chuyển.
6. Disable key cũ.
7. Xác minh request dùng key cũ bị từ chối.
8. Kiểm tra key có được dùng để tạo credential khác không.

Với key quản trị hoặc có bằng chứng khai thác, disable ngay có thể cần thiết dù làm gián đoạn service.

### 7.6 OAuth authorization code

Authorization code thường có thời hạn ngắn và dùng một lần. Nếu code bị lộ:

- Xác định client, redirect URI và transaction.
- Kiểm tra code đã được redeem chưa.
- Hủy transaction hoặc authorization grant nếu issuer hỗ trợ.
- Xác minh state và PKCE binding.
- Revoke token được phát hành từ code nếu cần.
- Kiểm tra callback URL và log đã lưu code.

Không xem code đã dùng một lần là vô hại nếu nó được redeem trước khi hết hạn.

### 7.7 CSRF và password reset token

CSRF token thường gắn với session hoặc request flow. Nếu token lộ, đánh giá liệu attacker có thể kết hợp nó với cookie/session hoặc nội dung trang để gửi request hay không. Xoay session hoặc CSRF token theo thiết kế.

Password reset token có thể cho phép chiếm tài khoản. Invalidate token bị lộ, kiểm tra token đã được dùng chưa và rà soát các thay đổi mật khẩu/MFA sau thời điểm lộ.

## 8. Điều tra log và dấu hiệu sử dụng trái phép

Điều tra phải tập trung vào hành vi và metadata, không thu thập thêm secret.

### 8.1 Timeline

Tạo timeline có các mốc:

- Token được phát hành.
- Token lần đầu xuất hiện ở nơi lộ.
- Vị trí lộ trở nên public hoặc có thể truy cập.
- Token được dùng lần đầu sau thời điểm lộ.
- Hành động nhạy cảm đầu tiên.
- Thời điểm phát hiện.
- Thời điểm revoke được yêu cầu.
- Thời điểm revoke có hiệu lực trên mọi verifier.
- Thời điểm rotate hoàn tất.
- Thời điểm nguồn lộ được khắc phục.

Phân biệt thời gian UTC và local timezone. Ghi rõ nguồn log và độ lệch đồng hồ nếu có.

### 8.2 Dấu hiệu bất thường

Tùy hệ thống, kiểm tra:

- IP hoặc ASN mới.
- User-Agent hoặc client fingerprint khác.
- Vị trí địa lý không phù hợp với hành vi bình thường.
- Nhiều thiết bị sử dụng cùng session.
- Request tăng đột biến.
- Truy cập endpoint chưa từng dùng.
- Thay đổi profile, MFA hoặc quyền.
- Refresh token reuse.
- API key được dùng từ môi trường không quen thuộc.
- Token được dùng sau khi người dùng đã logout.
- Request tiếp tục thành công sau thời điểm revoke dự kiến.

IP và User-Agent có thể thay đổi hợp lệ do VPN, NAT, mobile network hoặc browser update. Không kết luận compromise chỉ dựa vào một tín hiệu.

### 8.3 Log phải hỗ trợ điều tra nhưng không chứa token

Ghi các trường hữu ích:

- Credential identifier hoặc fingerprint đã bảo vệ.
- Issuer, subject, client và audience nếu phù hợp.
- Scope hoặc nhóm quyền.
- Thời điểm phát hành, hết hạn và revoke.
- Request ID, route, action và kết quả.
- IP/ASN hoặc browser family theo chính sách.
- Release, environment và service owner.

Redact:

- Authorization header.
- Cookie header.
- Refresh token.
- Password reset token.
- OAuth code.
- Secret trong query string.
- API key đầy đủ.
- Request/response body có credential.

Không ghi token raw để "dễ debug". Nếu cần đối chiếu, dùng identifier không bí mật hoặc fingerprint có khóa.

### 8.4 Xác định hành động sau khi token bị sử dụng

Nếu có request trái phép, cần xác định dữ liệu hoặc tài nguyên đã bị truy cập/thay đổi:

- Dữ liệu được đọc hoặc export.
- Tài khoản được sửa.
- Quyền được cấp thêm.
- Key hoặc token mới được tạo.
- Webhook hoặc callback bị thay đổi.
- Giao dịch hoặc thanh toán được tạo.
- File được tải lên hoặc tải xuống.
- Service khác bị truy cập từ credential bị lộ.

Đánh giá cả đường di chuyển ngang: token có thể truy cập service khác hoặc dùng để tạo credential mới.

## 9. Khắc phục nguồn rò rỉ trong ứng dụng web

### 9.1 Không lưu token dài hạn trong Web Storage

Nếu kiến trúc yêu cầu browser giữ session, cân nhắc cookie `HttpOnly`, `Secure` và `SameSite` phù hợp. Cookie tự động được gửi theo request nên cần CSRF protection đúng thiết kế.

Nếu dùng access token trong memory, vẫn phải đánh giá XSS và luồng refresh. Không có nơi lưu client-side nào loại bỏ hoàn toàn rủi ro XSS.

### 9.2 Cấu hình cookie an toàn

Ví dụ response:

~~~http
Set-Cookie: __Host-session=REDACTED; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Các thuộc tính cần hiểu:

- `Secure`: chỉ gửi qua HTTPS.
- `HttpOnly`: JavaScript không đọc được cookie.
- `SameSite=Lax`: hạn chế một số request cross-site nhưng không thay thế CSRF protection.
- Prefix `__Host-`: yêu cầu Secure, Path=/ và không có Domain attribute trong các browser hỗ trợ quy tắc này.

Chọn SameSite theo luồng ứng dụng. OAuth callback hoặc tích hợp cross-site có thể cần thiết kế riêng; không hạ thuộc tính cookie một cách tùy tiện để làm flow hoạt động.

### 9.3 Không đưa token vào URL

Dùng header Authorization hoặc cookie/session theo kiến trúc phù hợp. Với OAuth, dùng authorization code flow và PKCE khi áp dụng. Thiết lập Referrer Policy phù hợp để giảm khả năng URL chứa dữ liệu bị chuyển tiếp, nhưng không xem Referrer Policy là biện pháp thay thế việc loại token khỏi URL.

### 9.4 Redact log và telemetry

Cấu hình redaction ở nhiều tầng:

- Frontend logger.
- Backend logger.
- Reverse proxy.
- API gateway.
- APM và distributed tracing.
- Error monitoring.
- Analytics.
- CI/CD output.
- Support tooling.

Redaction cần áp dụng cả header, query parameter, cookie và body. Kiểm thử bằng fixture giả lập để xác nhận secret bị che trước khi dữ liệu rời process.

### 9.5 Sửa XSS và kiểm soát script

Nếu token bị lấy qua XSS:

- Xác định source và sink.
- Sửa output encoding hoặc DOM API.
- Loại bỏ innerHTML không cần thiết.
- Dùng sanitizer phù hợp khi phải render rich HTML.
- Triển khai CSP với nonce/hash và nguồn script chặt chẽ.
- Cân nhắc Trusted Types.
- Review third-party script và tag manager.
- Revoke token/session đã có thể bị đọc trong thời gian lỗ hổng tồn tại.

HttpOnly giảm khả năng đọc cookie bằng JavaScript nhưng XSS vẫn có thể gửi request thay người dùng. Vì vậy cần vừa sửa XSS vừa thu hồi credential có khả năng đã bị lạm dụng.

### 9.6 Kiểm soát postMessage

Nếu token bị lộ qua giao tiếp cửa sổ:

- Xác định message type nào mang token.
- Kiểm tra targetOrigin ở sender.
- Kiểm tra event.origin và event.source ở receiver.
- Không dùng wildcard cho secret.
- Giảm payload về dữ liệu tối thiểu.
- Validate schema và trạng thái handshake.
- Xem xét MessageChannel với capability giới hạn.
- Revoke token đã gửi nhầm.

Không giả định chỉ cần đổi origin allowlist là token đã gửi nhầm được thu hồi.

### 9.7 Kiểm soát source map và artifact

Kiểm tra bundle public, source map public, build artifact, release archive, static hosting, CDN, object storage, container image, package registry, backup và cache.

Loại bỏ credential khỏi source, build variables và artifact. Dùng secret manager cho secret server-side; frontend build chỉ nhận giá trị được phép công khai.

### 9.8 Cache và response nhạy cảm

Response chứa token hoặc dữ liệu xác thực cần policy cache phù hợp. Với response nhạy cảm, cân nhắc `Cache-Control: no-store` theo semantics của endpoint.

Kiểm tra browser cache, service worker, CDN và reverse proxy. no-store không xóa các bản sao đã được lưu trước khi header được áp dụng.

## 10. Kế hoạch rotate không gây gián đoạn ngoài ý muốn

Không phải mọi credential đều có thể đổi ngay mà không ảnh hưởng hệ thống. Cần phân biệt khi nào có thể dùng overlap và khi nào phải disable tức thì.

### 10.1 Rotation có overlap

Với service key hoặc signing key, có thể cần giai đoạn hai key cùng hợp lệ:

1. Tạo key mới.
2. Phân phối key mới tới consumer.
3. Xác nhận traffic dùng key mới.
4. Theo dõi lỗi và consumer chưa chuyển.
5. Disable key cũ.
6. Xác nhận key cũ bị từ chối.

Chỉ dùng overlap khi chưa có bằng chứng attacker đang khai thác và thời gian overlap được kiểm soát. Nếu credential có quyền cao đã bị công khai, overlap kéo dài tạo thêm thời gian cho attacker.

### 10.2 Rotation khẩn cấp

Khi có bằng chứng sử dụng trái phép hoặc token có quyền rất cao:

- Disable/revoke ngay.
- Chấp nhận gián đoạn cần thiết.
- Tạo credential mới sau khi xác định phạm vi.
- Phân phối qua kênh bí mật được phê duyệt.
- Khôi phục từng consumer và xác minh.
- Kiểm tra hành vi của credential cũ sau revoke.

Không giữ token cũ hoạt động chỉ vì một service chưa được cập nhật mà không có quyết định rủi ro rõ ràng.

### 10.3 Xác minh mọi verifier

Một hệ thống có thể có nhiều API gateway, region, cache hoặc resource server. Revoke ở issuer chưa chắc có hiệu lực tức thì ở mọi nơi.

Kiểm tra:

- Token introspection cache.
- JWT verifier và key cache.
- Session store replication.
- CDN hoặc gateway cache.
- Worker/background service.
- Mobile/backend consumer.
- Fail-open behavior khi issuer không truy cập được.

Ghi lại thời điểm revoke có hiệu lực thực tế, không chỉ thời điểm API revoke trả thành công.

## 11. Giao tiếp và quản lý incident

Sự cố token leak thường ảnh hưởng nhiều nhóm. Thông tin cần được chia sẻ theo nguyên tắc tối thiểu cần biết.

### 11.1 Nội dung incident record

Một record nên có:

- Incident ID.
- Mức độ và trạng thái.
- Token type và owner.
- Hệ thống, môi trường và scope.
- Vị trí exposure.
- Thời điểm phát hiện và khoảng thời gian exposure.
- Bằng chứng đã redact.
- Hành động revoke/rotate và người thực hiện.
- Phạm vi hoạt động đáng ngờ.
- Nguồn lộ và biện pháp khắc phục.
- Trạng thái xác minh sau containment.
- Các quyết định rủi ro và lý do.

Không đưa token raw vào incident record. Dùng secret store hoặc evidence vault được kiểm soát nếu cần lưu bản gốc phục vụ điều tra.

### 11.2 Thông báo người dùng hoặc đối tác

Khi sự cố ảnh hưởng tài khoản hoặc dữ liệu khách hàng, phối hợp với bộ phận chịu trách nhiệm để xác định nội dung và thời điểm thông báo.

Thông tin nên nêu loại credential hoặc phiên bị ảnh hưởng ở mức phù hợp, hành động bảo vệ đã thực hiện, người dùng cần làm gì, cách nhận hỗ trợ qua kênh chính thức và những gì đã xác minh.

Không khẳng định không có truy cập trái phép khi log chưa đủ để kết luận. Không gửi token hoặc yêu cầu người dùng gửi token qua email/chat.

## 12. Kiểm thử và diễn tập Token leak

Thực hiện trong lab hoặc môi trường được phê duyệt. Dùng token giả lập, không dùng credential production.

### 12.1 Diễn tập token trong log

Tạo fixture có Authorization header giả. Chạy qua logger và APM test. Xác nhận output chỉ chứa giá trị đã redact, không có token nguyên vẹn.

### 12.2 Diễn tập token trong URL

Tạo callback lab với query parameter giả. Kiểm tra web server, reverse proxy, analytics và error monitoring. Xác nhận token không xuất hiện trong log hoặc Referer ngoài dự kiến.

### 12.3 Diễn tập token trong Web Storage

Đặt token giả vào localStorage. Mô phỏng script cùng origin đọc dữ liệu để chứng minh tác động của XSS. Sau đó thử kiến trúc thay thế và xác nhận token không nằm trong Web Storage. Không dùng payload trên ứng dụng production.

### 12.4 Diễn tập session revoke

Phát hành session test, sao chép cookie giả vào browser profile thứ hai trong lab, rồi revoke session ở server. Xác nhận cả hai profile đều không thể tiếp tục dùng session.

### 12.5 Diễn tập refresh token reuse

Dùng refresh token test, thực hiện rotation rồi thử lại token cũ. Xác nhận server phát hiện reuse và xử lý token family theo policy.

### 12.6 Diễn tập API key rotation

Tạo hai key test. Chuyển consumer sang key mới, disable key cũ và xác nhận request dùng key cũ bị từ chối trên mọi môi trường.

### 12.7 Diễn tập JWT revoke

Dùng JWT test có `jti` và `exp`. Thử denylist hoặc session version. Xác nhận verifier thực sự từ chối token trước khi hết hạn. Nếu xoay signing key, kiểm tra mọi verifier đã ngừng chấp nhận key cũ.

### 12.8 Diễn tập postMessage leak

Tạo host và iframe ở hai origin local. Cố ý gửi token giả bằng wildcard trong lab, điều hướng iframe và quan sát nguy cơ. Sau đó sửa targetOrigin, receiver validation và xác nhận token chỉ được gửi tới context dự kiến.

### 12.9 Diễn tập XSS containment

Dùng ứng dụng lab có XSS giả lập và token không có giá trị. Xác minh quy trình: phát hiện sink, revoke token, sửa code, deploy, kiểm tra lại và theo dõi. Không dùng token thật để chứng minh khả năng đánh cắp.

## 13. Checklist ứng phó Token leak

### Khi phát hiện

- [ ] Mở incident và ghi thời điểm phát hiện.
- [ ] Xác định token type, issuer, owner và môi trường.
- [ ] Xác định scope, audience, thời hạn và khả năng tạo credential khác.
- [ ] Ghi nhận vị trí exposure và ai có thể truy cập.
- [ ] Bảo toàn metadata/bằng chứng đã redact.
- [ ] Không đưa token raw vào ticket, chat, email hoặc log.
- [ ] Đánh giá mức độ theo quyền và khả năng sử dụng.

### Containment

- [ ] Revoke hoặc disable credential bị lộ.
- [ ] Revoke session/token family liên quan nếu cần.
- [ ] Ngăn refresh token cấp token mới.
- [ ] Disable API key hoặc service credential bị compromise.
- [ ] Kiểm tra cache và thời gian revoke có hiệu lực.
- [ ] Đánh giá credential liên quan và quyền có thể đã bị mở rộng.
- [ ] Theo dõi lỗi và tác động tới người dùng/service.

### Điều tra

- [ ] Dựng timeline từ phát hành tới revoke.
- [ ] Kiểm tra log issuer, gateway, application và resource server.
- [ ] Tìm request bất thường và hành động nhạy cảm.
- [ ] Kiểm tra thay đổi quyền, MFA, API key và webhook.
- [ ] Xác định dữ liệu đã được đọc, sửa hoặc export.
- [ ] Kiểm tra token có được dùng để tạo credential khác không.
- [ ] Ghi rõ giới hạn của log và khoảng thời gian không có dữ liệu.

### Khắc phục và khôi phục

- [ ] Rotate credential qua secret manager.
- [ ] Cập nhật consumer và xác minh credential mới.
- [ ] Xác nhận credential cũ bị từ chối trên mọi verifier.
- [ ] Sửa nguồn lộ trong frontend, backend, CI/CD hoặc third-party.
- [ ] Redact log, telemetry, trace và support tooling.
- [ ] Kiểm tra URL, storage, cookie, service worker và cache.
- [ ] Kiểm tra bundle, source map, artifact và repository.
- [ ] Kiểm tra XSS, postMessage và các điểm đưa token vào DOM.
- [ ] Xác minh luồng đăng nhập/refresh sau khôi phục.
- [ ] Theo dõi hoạt động bất thường sau incident.

### Sau sự cố

- [ ] Hoàn tất timeline và phạm vi ảnh hưởng.
- [ ] Ghi nguyên nhân gốc và yếu tố góp phần.
- [ ] Cập nhật secret scanning và log redaction.
- [ ] Bổ sung test revoke/rotate vào pipeline.
- [ ] Cập nhật runbook và owner.
- [ ] Xác định hành động khắc phục, người phụ trách và thời hạn.
- [ ] Chia sẻ bài học theo nguyên tắc tối thiểu cần biết.

## 14. Những sai lầm cần tránh

### 14.1 Chỉ xóa token khỏi nơi bị lộ

Xóa chuỗi khỏi Git, log hoặc trang web không vô hiệu hóa bản sao. Revoke/rotate phải được thực hiện ở issuer hoặc hệ thống kiểm tra token.

### 14.2 Chỉ đổi mật khẩu

Session cookie, refresh token và API key có thể tiếp tục hoạt động sau khi đổi mật khẩu. Cần kiểm tra chính sách revoke theo tài khoản và từng loại credential.

### 14.3 Chỉ revoke access token

Refresh token có thể cấp access token mới. Cần revoke token family hoặc session liên quan theo cơ chế issuer.

### 14.4 Cho rằng JWT hết hạn là đủ

Token có thể có thời hạn dài và verifier có thể không kiểm tra denylist. Cần xác định thời điểm hết hạn thực tế, khả năng revoke và quyền token.

### 14.5 Gửi token tới công cụ phân tích trực tuyến

Không đưa JWT, cookie hoặc API key production vào website decoder, paste service hoặc công cụ không được phê duyệt. Dữ liệu có thể bị lưu hoặc chia sẻ.

### 14.6 Ghi token vào incident ticket để dễ đối chiếu

Ticket thường có nhiều người truy cập và retention dài. Dùng fingerprint hoặc identifier không bí mật.

### 14.7 Xóa log trước khi điều tra

Log có thể là bằng chứng về thời điểm và hành động sử dụng token. Bảo toàn bản cần thiết có kiểm soát, sau đó xử lý dữ liệu nhạy cảm theo policy.

### 14.8 Rotate key nhưng vẫn chấp nhận key cũ

Nếu verifier còn trust key cũ hoặc cache chưa cập nhật, rotation chưa hoàn tất. Kiểm tra mọi region và consumer.

### 14.9 Dựa vào HttpOnly để kết luận XSS không thể lạm dụng session

HttpOnly ngăn JavaScript đọc cookie, nhưng XSS có thể gửi request từ browser đang có cookie. Vẫn cần sửa XSS và đánh giá hành động trái phép.

### 14.10 Dựa vào CORS để bảo vệ token

CORS không phải cơ chế revoke hoặc quản lý bí mật. Token đã lộ qua log, URL, bundle hoặc storage vẫn cần xử lý theo loại credential.

### 14.11 Không kiểm tra token liên quan

Một token bị lộ có thể tạo refresh token, API key hoặc session khác. Điều tra đường phát hành credential và thu hồi những credential phát sinh trái phép.

### 14.12 Kết thúc incident ngay khi login hoạt động

Login thành công không chứng minh token cũ bị revoke, log đã sạch hoặc attacker không còn quyền. Cần xác minh từng điều kiện khôi phục.

## 15. Câu hỏi tự kiểm tra

**1. Token leak là gì?**

Là việc credential hoặc bearer token bị tiết lộ tới người hoặc hệ thống không được phép, có thể cho phép sử dụng quyền được cấp cho token.

**2. Vì sao đổi mật khẩu không luôn xử lý được token leak?**

Session cookie, access token, refresh token và API key có thể có vòng đời và cơ chế revoke độc lập với mật khẩu.

**3. Vì sao refresh token leak thường nghiêm trọng?**

Refresh token có thể cấp access token mới, kéo dài khả năng truy cập sau khi access token hiện tại hết hạn.

**4. JWT có tự hỗ trợ revoke không?**

Không. JWT có thể được xác minh offline; cần denylist, token version, introspection hoặc biện pháp key rotation phù hợp nếu cần thu hồi trước `exp`.

**5. HttpOnly có ngăn mọi tác động của XSS không?**

Không. Nó ngăn JavaScript đọc cookie nhưng XSS vẫn có thể thực hiện request trong phiên browser đang hoạt động.

**6. Vì sao không nên đưa token vào URL?**

URL có thể bị lưu trong history, log, telemetry, Referer hoặc screenshot và được sao chép tới nhiều hệ thống.

**7. Vì sao xóa token khỏi Git không đủ?**

Các bản sao trong clone, fork, cache và log có thể còn tồn tại; token đã bị lộ phải được revoke hoặc rotate.

**8. Cần điều tra những gì sau khi revoke?**

Timeline, request sử dụng token, hành động nhạy cảm, thay đổi quyền, dữ liệu truy cập và credential khác có thể được tạo từ token đó.

**9. Vì sao cần xác minh mọi verifier sau rotation?**

Gateway, region, service và cache có thể tiếp tục chấp nhận credential cũ nếu trạng thái revoke hoặc key mới chưa được cập nhật.

**10. Khi nào có thể đóng incident?**

Khi credential cũ không còn được chấp nhận, nguồn lộ đã được xử lý, phạm vi ảnh hưởng đã được đánh giá, hệ thống được xác minh và các hành động theo dõi có owner rõ ràng.

## Ghi nhớ

Token leak là sự cố về quyền truy cập, không chỉ là sự cố lộ một chuỗi ký tự. Xác định loại token, issuer, scope, audience, thời hạn và khả năng tạo credential khác trước khi chọn cách xử lý. Ưu tiên containment bằng revoke hoặc disable ở phía xác thực; sau đó rotate credential, điều tra hành vi sử dụng và sửa nguồn rò rỉ. Đổi mật khẩu hoặc xóa token khỏi nơi nhìn thấy không tự thu hồi bản sao đang hoạt động. Trong ứng dụng browser, kiểm tra URL, cookie, Web Storage, log, postMessage, source map, service worker và XSS. Chỉ đóng incident khi token cũ đã bị từ chối trên mọi verifier liên quan và nguồn lộ đã được khắc phục.

## Tài liệu tham khảo

- [OWASP: Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [OWASP: Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP: JSON Web Token Cheat Sheet for Java](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html)
- [OWASP: OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html)
- [OWASP: Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html)
- [OWASP: Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [RFC 6750: OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7009: OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 9700: Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [MDN: Set-Cookie header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie)
- [MDN: Referrer-Policy header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referrer-Policy)
