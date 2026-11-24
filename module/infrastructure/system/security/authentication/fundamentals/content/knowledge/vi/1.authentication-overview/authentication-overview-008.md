# Lộ trình học authentication

Authentication (xác thực) là quá trình kiểm tra một chủ thể có kiểm soát được bằng chứng định danh mà họ tuyên bố sở hữu hay không. Trong hệ thống thực tế, đó không chỉ là màn hình đăng nhập: từ lúc tạo tài khoản, cấp và quản lý credential, yêu cầu thêm yếu tố xác thực, phát hành phiên hoặc token, liên kết với nhà cung cấp danh tính, đến khi người dùng mất thiết bị và cần khôi phục quyền truy cập, mỗi bước đều tạo ra một ranh giới tin cậy.

Bài học này đưa ra **lộ trình học authentication từ cơ bản đến thiết kế hệ thống**. Người học sẽ lần lượt nghiên cứu mật khẩu, MFA, passkey, chứng chỉ, phiên, token, liên kết danh tính và khôi phục tài khoản; đồng thời học cách chống phishing, replay, lạm dụng đăng nhập và kiểm chứng các luồng xác thực bằng mô hình đe dọa.

## 1. Đích đến của lộ trình

Sau khi hoàn thành, bạn có thể:

1. **Phân biệt danh tính, xác thực và phân quyền**; xác định ai đưa ra khẳng định danh tính, bên nào kiểm tra và bên nào ra quyết định truy cập.
2. **Chọn cơ chế xác thực phù hợp với rủi ro**: mật khẩu, OTP, ứng dụng xác thực, khóa bảo mật, passkey hoặc chứng chỉ.
3. **Thiết kế vòng đời của credential**: đăng ký, lưu trữ an toàn, sử dụng, thay đổi, thu hồi và khôi phục.
4. **Giải thích phiên và token**: cách phát hành, kiểm tra, làm mới, hết hạn, đăng xuất, chống đánh cắp và chống replay.
5. **Đọc và thiết kế một luồng liên kết danh tính** bằng OpenID Connect (OIDC), biết ranh giới giữa OAuth 2.0 và đăng nhập.
6. **Vẽ trust boundary và threat model** cho đăng nhập, MFA, đăng nhập liên kết và khôi phục tài khoản; đề xuất phép thử an ninh cụ thể.
7. **Đánh giá trải nghiệm sử dụng** mà không đánh đổi an toàn: xử lý lỗi có chừng mực, hỗ trợ phương thức dự phòng, khả năng tiếp cận và giám sát sự cố.

Đây là lộ trình theo **phụ thuộc kiến thức**, không phải danh sách các công nghệ để học thuộc. Một công nghệ chỉ trở nên có ý nghĩa khi bạn hiểu nó kiểm tra điều gì, tin tưởng thành phần nào và xử lý ra sao nếu thành phần đó bị chiếm quyền.

## 2. Bản đồ kiến thức: các khái niệm phải tách bạch

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Định danh (identification) | Chủ thể tuyên bố mình là ai? | Nhập tên tài khoản hoặc chọn tài khoản tổ chức. |
| Xác minh danh tính ban đầu (identity proofing) | Có căn cứ nào để gắn người/thực thể ngoài đời với danh tính số? | Quy trình đối chiếu giấy tờ khi mở tài khoản yêu cầu xác minh pháp lý. |
| Ghi danh credential (enrollment) | Bằng chứng xác thực được đăng ký cho tài khoản nào? | Gắn một passkey mới sau khi đã xác thực đủ mạnh. |
| Xác thực (authentication) | Chủ thể có chứng minh được quyền kiểm soát credential không? | Kiểm tra mật khẩu hoặc chữ ký WebAuthn. |
| Phân quyền (authorization) | Chủ thể đã xác thực được phép làm gì? | Chỉ quản trị viên được thay đổi chính sách. |
| Phiên (session) | Làm sao hệ thống duy trì ngữ cảnh sau khi xác thực? | Cookie phiên với thời hạn và khả năng thu hồi. |
| Liên kết danh tính (federation) | Ứng dụng tin vào lời xác nhận của hệ thống danh tính khác theo điều kiện nào? | Ứng dụng nhận ID token hợp lệ từ một OpenID Provider. |
| Khôi phục (recovery) | Làm sao lấy lại quyền truy cập khi mất credential? | Sử dụng mã dự phòng hoặc quy trình khôi phục đã xác minh. |

**Ba câu hỏi nền tảng** khi xem bất kỳ cơ chế nào:

- **Bằng chứng là gì?** Một bí mật được ghi nhớ, một thiết bị/khóa đang sở hữu, hay đặc tính sinh trắc được dùng để mở khóa một authenticator? Sinh trắc cục bộ không tự động đồng nghĩa với việc máy chủ nhận hoặc lưu dữ liệu sinh trắc.
- **Ai xác minh bằng chứng?** Máy chủ ứng dụng, dịch vụ danh tính chuyên trách, authenticator, CA hay một bên liên kết?
- **Điều gì còn đáng tin sau xác thực?** Máy chủ có thể cấp một session/token, nhưng bằng chứng đăng nhập thành công không làm cho mọi yêu cầu sau đó tự động an toàn hoặc được phép.

### 2.1. Nhìn hệ thống qua ranh giới tin cậy

~~~mermaid
flowchart LR
    U["Người dùng / thiết bị"] --> B["Trình duyệt hoặc ứng dụng"]
    B -->|Credential hoặc yêu cầu xác thực| AS["Authentication service"]
    AS -->|Kiểm tra / cập nhật| CS[("Credential store")]
    AS -->|Phiên hoặc token| B
    B -->|Cookie / access token| API["Resource server / API"]
    API -->|Kiểm tra phiên hoặc token| V["Verifier / session store"]
    AS <-->|Liên kết danh tính khi có| IDP["Identity provider bên ngoài"]
~~~

Sơ đồ trên là mô hình khái niệm, không ngụ ý mọi credential đều truyền qua ứng dụng: với WebAuthn, authenticator ký một challenge theo ràng buộc origin/RP ID; với đăng nhập liên kết, ứng dụng thực hiện chuyển hướng tới nhà cung cấp danh tính. Các đường nối là chỗ cần hỏi: **dữ liệu có thể bị sửa, sao chép, phát lại, đánh cắp hoặc được một bên khác giả mạo không?**

Khi phân tích một luồng, hãy đánh dấu ít nhất bốn biên: **thiết bị người dùng ↔ trình duyệt/ứng dụng**, **ứng dụng ↔ dịch vụ xác thực**, **dịch vụ xác thực ↔ kho credential/khóa**, **ứng dụng ↔ hệ thống danh tính bên ngoài**. Biên mạng, biên quy trình, biên miền (origin) và biên quyền quản trị có thể khác nhau; kết nối TLS chỉ bảo vệ một phần vấn đề.

## 3. Thứ tự học và sản phẩm đầu ra

| Chặng | Nội dung chính | Nên biết trước | Sản phẩm tự kiểm chứng |
| --- | --- | --- | --- |
| 0 | Ngôn ngữ nền tảng và mô hình đe dọa | HTTP, HTTPS, cookie cơ bản | Vẽ sơ đồ tác nhân, tài sản, trust boundary. |
| 1 | Vòng đời danh tính và credential | Chặng 0 | Mô tả đăng ký, cấp, thay, thu hồi credential. |
| 2 | Mật khẩu và bảo vệ endpoint đăng nhập | Chặng 1 | Phác thảo đăng nhập mật khẩu an toàn và các phép thử. |
| 3 | MFA, passkey, WebAuthn | Chặng 2 | So sánh khả năng chống phishing/replay của từng phương thức. |
| 4 | Chứng chỉ và xác thực giữa dịch vụ | Chặng 0–3 | Phân biệt TLS máy chủ, mTLS và xác thực người dùng. |
| 5 | Phiên, cookie, token và logout | Chặng 2–3 | Thiết kế vòng đời phiên, refresh và thu hồi. |
| 6 | OAuth 2.0, OIDC và liên kết danh tính | Chặng 5 | Vẽ luồng Authorization Code + PKCE và quy tắc kiểm tra token. |
| 7 | Khôi phục, liên kết tài khoản và thay đổi yếu tố | Chặng 1–6 | Mô hình hóa đường khôi phục có độ bảo đảm phù hợp. |
| 8 | Phòng vệ, giám sát và thiết kế tổng thể | Tất cả chặng trước | Hoàn thành threat model, bộ test và bản thiết kế mẫu. |

Có thể dùng **8 tuần, khoảng 4–6 giờ/tuần** làm nhịp tham khảo: tuần 1 học chặng 0–1, tuần 2 học chặng 2, tuần 3 học chặng 3, tuần 4 học chặng 4–5, tuần 5 học chặng 6, tuần 6 học chặng 7, tuần 7–8 làm chặng 8 và dự án tổng hợp. Nếu thời gian ít, giữ nguyên thứ tự phụ thuộc và kéo dài nhịp học; không cần học mọi chuẩn cùng độ sâu ngay từ đầu.

## 4. Chặng 0 — Đọc đúng bài toán trước khi chọn công nghệ

**Học gì:** HTTP request/response, HTTPS/TLS, origin và cookie; client/server; xác thực so với phân quyền; đối thủ có thể kiểm soát thiết bị, mạng, website giả, credential rò rỉ hay máy chủ phụ thuộc ở mức nào. Học thuật ngữ **threat actor**, **asset**, **attack surface**, **trust boundary**, **security control** và **residual risk**.

**Thực hành:** Lấy ứng dụng giả định **StudyHub** có học viên, giảng viên và quản trị viên. Vẽ quá trình học viên đăng nhập và xem hồ sơ. Ghi tài sản cần bảo vệ: danh tính người dùng, credential, session cookie, token, thông tin hồ sơ và quyền quản trị. Đánh dấu chỗ trình duyệt gửi dữ liệu, máy chủ kiểm tra và hệ thống quyết định phân quyền.

**Qua chặng khi:** Bạn chỉ ra được rằng “biết email” không phải bằng chứng xác thực; “đã đăng nhập” không mặc nhiên có quyền quản trị; một request có cookie hợp lệ vẫn cần kiểm tra quyền trên tài nguyên.

## 5. Chặng 1 — Danh tính và vòng đời credential

**Học gì:** Đăng ký tài khoản, xác thực quyền kiểm soát địa chỉ email/điện thoại nếu cần, liên kết account ID nội bộ với identifier bên ngoài, ghi danh và xóa credential, thay đổi thông tin liên lạc, khóa tài khoản, rút quyền, xóa dữ liệu theo yêu cầu sản phẩm. Phân biệt **account identifier ổn định** với thuộc tính có thể đổi như email hoặc tên hiển thị.

**Nguyên tắc thiết kế:** Email đã được xác nhận có thể là kênh liên lạc/khôi phục, nhưng không nên là khóa chính bất biến để liên kết tài khoản. Thêm một credential mới, đổi số điện thoại hoặc đổi phương thức MFA là thao tác nhạy cảm: yêu cầu một mức xác thực gần đây phù hợp với rủi ro, thông báo thay đổi và có cơ chế xử lý khi thao tác không do chủ tài khoản thực hiện.

**Thực hành:** Vẽ state machine: **tài khoản tạo mới → có credential → đang hoạt động → cần xác minh lại → bị khóa/thu hồi → đóng**. Với mỗi chuyển trạng thái, ghi người thực hiện, bằng chứng cần có và nhật ký cần giữ.

**Qua chặng khi:** Bạn mô tả được cách ngăn người khác chiếm tài khoản bằng cách tự ý thêm credential hay đổi địa chỉ khôi phục.

## 6. Chặng 2 — Mật khẩu: từ lưu trữ đến đăng nhập

**Học gì:** Mật khẩu là yếu tố thuộc loại *điều người dùng biết*. Trên máy chủ, lưu **password verifier** dưới dạng hàm dẫn xuất mật khẩu có salt ngẫu nhiên riêng cho từng mật khẩu và tham số chi phí thích hợp (ưu tiên Argon2id khi nền tảng hỗ trợ; scrypt/bcrypt khi có lý do tương thích). Không lưu mật khẩu dạng rõ hoặc chỉ băm nhanh bằng SHA-256. Kênh truyền cần TLS; không ghi mật khẩu vào log, analytics hay URL.

Luồng cơ bản:

1. Nhận định danh và mật khẩu qua kênh HTTPS; kiểm tra đầu vào và áp dụng giới hạn yêu cầu có tính đến tài khoản, IP/nguồn, thiết bị và nguy cơ khóa nhầm.
2. Tra cứu tài khoản và kiểm tra verifier bằng hàm chuyên dụng, tránh tiết lộ sự tồn tại của tài khoản qua nội dung lỗi hoặc chênh lệch xử lý quá dễ nhận thấy.
3. Nếu tài khoản yêu cầu MFA, tạo **giao dịch đăng nhập chờ hoàn tất**, có thời hạn và ràng buộc với lần đăng nhập này. Chưa phát hành phiên đã xác thực đầy đủ.
4. Sau khi đủ bằng chứng, tạo phiên mới và ghi sự kiện an ninh; không cho client tự chọn session ID hay quyền.

~~~text
POST /login
  kiểm tra giới hạn yêu cầu
  tra cứu tài khoản và verifier
  nếu không hợp lệ -> trả lỗi đăng nhập chung
  nếu cần MFA -> tạo challenge ngắn hạn, chưa cấp session đầy đủ
  nếu hoàn thành xác thực -> tạo session mới trên máy chủ
~~~

**Thực hành:** Liệt kê phép thử cho sai mật khẩu, nhiều lần thất bại, tài khoản không tồn tại, mật khẩu bị rò rỉ, thay đổi mật khẩu, đăng nhập đồng thời và nâng cấp tham số hàm băm. Đánh giá vì sao khóa tài khoản vĩnh viễn sau vài lần sai có thể bị kẻ tấn công lợi dụng để gây từ chối dịch vụ.

**Qua chặng khi:** Bạn giải thích được khác biệt giữa hashing có chi phí và mã hóa có thể giải mã, đồng thời thiết kế được kiểm soát chống credential stuffing và password spraying mà không gây thiệt hại không cần thiết cho người dùng hợp lệ.

## 7. Chặng 3 — MFA và passkey: nâng độ bảo đảm xác thực

**Học gì:** MFA kết hợp các **loại yếu tố độc lập**: điều biết (mật khẩu/PIN), điều có (thiết bị, khóa bảo mật) và điều thuộc về người dùng (sinh trắc). Hai mật khẩu hoặc mật khẩu kèm câu hỏi bí mật không tự động thành hai yếu tố. Sinh trắc thường mở khóa một thiết bị xác thực và cần xem xét nơi đối chiếu diễn ra.

| Phương thức | Điều cần hiểu | Rủi ro/giới hạn điển hình |
| --- | --- | --- |
| OTP qua SMS | Mã có thời hạn được gửi qua số điện thoại | Chuyển SIM, đánh cắp mã, phishing; phụ thuộc nhà mạng. |
| TOTP bằng ứng dụng | Mã sinh từ bí mật chung và thời gian | Có thể bị nhập vào trang giả và sử dụng ngay; cần bảo vệ secret và chống dùng lại. |
| Push xác nhận | Thiết bị phê duyệt yêu cầu đăng nhập | Push bombing, xác nhận nhầm; nên hiển thị ngữ cảnh/ràng buộc giao dịch khi có thể. |
| Khóa bảo mật FIDO2 / passkey | Authenticator ký challenge bằng private key; máy chủ kiểm tra public key | Chống phishing tốt nhờ ràng buộc RP ID/origin; vẫn cần bảo vệ phiên, ghi danh và khôi phục. |

Với **WebAuthn**, máy chủ đăng ký public key của credential và phát một **challenge mới, khó đoán, chỉ dùng một lần hoặc có cơ chế ngăn phát lại** cho mỗi lần xác thực. Authenticator ký dữ liệu thử thách có ràng buộc với relying party; máy chủ kiểm tra challenge, origin, RP ID hash, chữ ký và các cờ cần thiết theo chính sách. **Private key không được gửi cho máy chủ**. Passkey có thể được đồng bộ giữa thiết bị qua hệ sinh thái cung cấp; mức bảo đảm của phương thức đồng bộ và khôi phục cần được xét riêng khi xác định chính sách.

**Thực hành:** Thiết kế hai đường cho StudyHub: **mật khẩu + TOTP** và **passkey**. Với mỗi đường, vẽ lúc đăng ký yếu tố, lúc sử dụng và lúc mất thiết bị. Thử giải thích vì sao một trang đăng nhập giả có thể lấy mã TOTP nhưng khó dùng chữ ký WebAuthn cho domain hợp lệ khi đang ở origin giả.

**Qua chặng khi:** Bạn phân biệt được MFA thông thường với phương thức **chống phishing**, và nhận ra MFA không khắc phục được session cookie đã bị đánh cắp hoặc luồng thêm yếu tố quá yếu.

## 8. Chặng 4 — Chứng chỉ và xác thực máy với máy

**Học gì:** Trong TLS thông thường, trình duyệt kiểm tra **chứng chỉ máy chủ** để xác thực máy chủ và thiết lập kết nối bảo mật; điều này **không tự xác thực người dùng cuối**. Với **mutual TLS (mTLS)**, phía client cũng trình bày chứng chỉ và chứng minh sở hữu private key, phù hợp một số mô hình máy với máy, thiết bị được quản lý hoặc hệ thống doanh nghiệp. Cần hiểu chuỗi chứng chỉ, trust store, tên miền/SAN, thời hạn, phát hành, luân chuyển khóa và thu hồi.

**Thực hành:** Vẽ một worker service gọi API nội bộ qua mTLS. Tách hai quyết định: **chứng chỉ client có được tin cậy không?** và **service identity đó được gọi endpoint nào?** Ghi cách phân phối và xoay vòng chứng chỉ trước khi hết hạn.

**Qua chặng khi:** Bạn không nhầm chứng chỉ website với đăng nhập tài khoản, và không xem “TLS đã bắt tay thành công” là bằng chứng đủ để cấp mọi quyền ứng dụng.

## 9. Chặng 5 — Phiên, cookie và token

Sau khi đã xác thực, ứng dụng cần duy trì trạng thái đăng nhập giữa các request. Hai mô hình thường gặp:

- **Session tham chiếu:** trình duyệt giữ một giá trị ngẫu nhiên khó đoán, máy chủ ánh xạ sang bản ghi phiên với danh tính, quyền/ngữ cảnh, thời hạn và trạng thái thu hồi.
- **Token có thể tự xác minh (ví dụ JWT đã ký):** resource server kiểm tra chữ ký và các claim bắt buộc như issuer, audience, expiration, not-before nếu có; quyền và chính sách thu hồi vẫn cần được thiết kế. Opaque token cũng phổ biến và có thể được kiểm tra qua hệ thống phát hành/introspection.

**Học gì:** Session fixation, đánh cắp cookie, CSRF, XSS, access token, refresh token, token replay, giới hạn thời gian, idle timeout và absolute timeout. Phân biệt **access token** dùng để gọi tài nguyên với **ID token** dùng để ứng dụng khách nhận thông tin về sự kiện xác thực từ OIDC; ID token không phải vé truy cập API tùy ý.

Ví dụ cookie phiên cho ứng dụng web sử dụng HTTPS:

~~~http
Set-Cookie: __Host-session=<opaque-random-value>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Đây là ví dụ định hướng, không phải cấu hình đủ cho mọi ứng dụng. Prefix **__Host-** yêu cầu cookie có **Secure**, **Path=/** và không có thuộc tính **Domain**. **HttpOnly** giảm khả năng JavaScript đọc cookie; **Secure** chỉ gửi qua HTTPS; **SameSite** giảm một số ngữ cảnh gửi cookie qua site khác nhưng không thay thế kiểm soát CSRF khi cần. Với request làm thay đổi trạng thái, dùng biện pháp CSRF phù hợp như CSRF token và/hoặc kiểm tra Origin, tùy kiến trúc. XSS có thể vẫn thực hiện hành động dưới phiên người dùng ngay cả khi không đọc được HttpOnly cookie.

**Thực hành:** Mô tả tạo phiên sau đăng nhập, **xoay session ID khi thay đổi mức đặc quyền hoặc hoàn tất xác thực**, logout, logout trên mọi thiết bị, xử lý phiên hết hạn và kiểm soát phiên khi đổi mật khẩu/credential. Nếu dùng refresh token, học refresh token rotation và cách nhận biết tái sử dụng; cân nhắc sender-constrained token như DPoP hoặc mTLS khi mô hình đe dọa cần.

**Qua chặng khi:** Bạn biết nơi kiểm tra token, tránh đưa access token vào URL, chọn nơi lưu token theo mô hình client và giải thích được vì sao logout của JWT tự chứa đòi hỏi chiến lược rõ ràng về thời hạn hoặc thu hồi.

## 10. Chặng 6 — Đăng nhập liên kết: OAuth 2.0 và OpenID Connect

**Học gì:** **OAuth 2.0** là khuôn khổ **ủy quyền** để một client nhận quyền truy cập giới hạn vào tài nguyên; **OpenID Connect (OIDC)** xây lớp **xác thực danh tính** trên OAuth 2.0. Vì vậy, “có access token” không đủ để tự suy ra user là ai và đã được xác thực thế nào. SAML là một hướng liên kết danh tính khác, thường gặp trong tích hợp doanh nghiệp; nên học khái niệm assertion, issuer, audience và trust configuration trước khi triển khai.

Với ứng dụng web hoặc mobile hiện đại, hãy hiểu **Authorization Code Flow + PKCE** trước. Cần biết vai trò user agent, client, authorization server/OpenID Provider và resource server; tham số **state** để ràng buộc phản hồi với yêu cầu, **nonce** trong ngữ cảnh OIDC để chống phát lại ID token, PKCE để ràng buộc authorization code với client đã khởi tạo, và quy tắc redirect URI chính xác.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant A as Ứng dụng StudyHub
    participant I as OpenID Provider
    U->>A: Chọn đăng nhập liên kết
    A->>I: Chuyển hướng kèm state, PKCE và tham số OIDC
    I->>U: Xác thực theo chính sách của IdP
    I-->>A: Trả authorization code và state
    A->>I: Đổi code bằng code_verifier tại token endpoint
    I-->>A: Trả token theo phạm vi và giao thức
    A->>A: Kiểm tra issuer, audience, chữ ký, thời hạn, nonce và ngữ cảnh
    A-->>U: Tạo phiên ứng dụng theo danh tính đã liên kết
~~~

Đây là luồng rút gọn. Trong triển khai, ứng dụng cần xác minh state trước khi sử dụng kết quả callback, bảo vệ client credential khi có, kiểm tra ID token theo quy tắc giao thức và chỉ liên kết bằng **issuer + subject** đáng tin cậy. Email hoặc tên hiển thị có thể thay đổi, trùng nhau, hoặc chưa được xác minh; **không tự ghép hai tài khoản chỉ vì email trùng**.

**Thực hành:** Vẽ màn hình “Đăng nhập với tổ chức” và callback; liệt kê điều gì xảy ra khi state sai, code bị dùng lại, redirect URI bất hợp lệ, issuer không mong đợi hoặc người dùng đăng nhập qua IdP khác với trước. Thêm quy trình yêu cầu xác thực lại khi liên kết thêm danh tính vào tài khoản hiện tại.

**Qua chặng khi:** Bạn giải thích được ứng dụng thực sự tin cậy nhà cung cấp nào, cách kiểm tra kết quả đăng nhập và nguy cơ account takeover khi liên kết tài khoản sai.

## 11. Chặng 7 — Khôi phục tài khoản và điểm yếu của đường dự phòng

**Học gì:** Mất mật khẩu, mất điện thoại, mất passkey, đổi máy, đổi email và mất quyền truy cập IdP tạo ra các ca khôi phục khác nhau. Một hệ thống có passkey chống phishing nhưng cho đặt lại toàn bộ credential chỉ bằng câu hỏi bí mật yếu sẽ có mức bảo vệ thực tế bị giới hạn bởi chính đường khôi phục đó.

Một quy trình khôi phục cần trả lời:

1. **Bằng chứng thay thế là gì?** Mã dự phòng dùng một lần, credential thứ hai đã đăng ký trước, quy trình xác minh hỗ trợ hoặc các biện pháp khác tương xứng với rủi ro tài khoản.
2. **Kênh nào đang được kiểm soát?** Email/SMS là kênh nhận liên lạc; khả năng nhận thông điệp không tự động đủ cho mọi tài khoản và mọi cấp độ truy cập.
3. **Token khôi phục có thuộc tính gì?** Khó đoán, thời hạn ngắn, một lần sử dụng, được lưu/kiểm tra an toàn, không xuất hiện trong log; giới hạn số lần thử và thông báo kết quả.
4. **Điều gì xảy ra sau khi khôi phục?** Cân nhắc thu hồi hoặc kiểm tra lại session, thông báo qua kênh đã đăng ký, yêu cầu đăng ký lại yếu tố cần thiết và trì hoãn thao tác nhạy cảm khi rủi ro cao.

**Thực hành:** Với tài khoản quản trị viên StudyHub, thiết kế hai trường hợp: còn một khóa bảo mật dự phòng và mất toàn bộ thiết bị. Vẽ quyết định của hệ thống, thời điểm đội hỗ trợ được can thiệp, chứng cứ cần lưu và cách chống kẻ tấn công lợi dụng bộ phận hỗ trợ để vượt MFA.

**Qua chặng khi:** Bạn có thể đánh giá toàn bộ vòng đời tài khoản qua **đường đăng nhập mạnh nhất lẫn đường khôi phục yếu nhất**, không chỉ qua màn hình login.

## 12. Chặng 8 — Gắn cơ chế với kiểu tấn công

| Tình huống | Ranh giới bị khai thác | Phòng vệ cần học và kiểm thử |
| --- | --- | --- |
| Phishing lấy mật khẩu/OTP | Người dùng → website giả | Phương thức chống phishing như WebAuthn; hướng dẫn người dùng; theo dõi đăng nhập bất thường. |
| Credential stuffing/password spraying | Endpoint đăng nhập → credential store | Mật khẩu không tái sử dụng, kiểm tra mật khẩu rò rỉ theo chính sách, rate limiting theo nhiều tín hiệu, phát hiện bất thường. |
| Replay OTP, challenge hoặc authorization code | Client → verifier/callback | Challenge ngắn hạn không tái sử dụng, ràng buộc giao dịch, PKCE/state/nonce theo ngữ cảnh và kiểm tra thời hạn. |
| Session hijacking/fixation | Trình duyệt → ứng dụng | HTTPS, cookie bảo vệ, tạo lại ID lúc đăng nhập/nâng quyền, chống XSS, quản lý timeout và thu hồi. |
| CSRF | Website khác → trình duyệt có cookie | SameSite phù hợp, CSRF token/kiểm tra Origin, không dùng GET cho hành động thay đổi trạng thái. |
| Token dùng sai nơi nhận | Client/API → resource server | Kiểm tra issuer, audience, chữ ký, thời hạn, scope/quyền và ràng buộc với client nếu có. |
| Đánh cắp tài khoản qua recovery | Người yêu cầu → quy trình khôi phục | Bằng chứng khôi phục tương xứng, cảnh báo, giới hạn thử, kiểm soát thao tác nhạy cảm. |
| Liên kết nhầm danh tính | Ứng dụng → IdP bên ngoài | Liên kết bằng subject + issuer, kiểm tra ID token, yêu cầu xác thực lại khi thay đổi liên kết. |

**Quan sát và vận hành:** Ghi sự kiện đăng nhập thành công/thất bại, thử thêm hoặc xóa credential, thay đổi MFA, khôi phục, cấp/thu hồi phiên và đăng nhập bất thường với dữ liệu tối thiểu cần thiết. Giới hạn quyền đọc log, tránh lưu secret/token/password, theo dõi tỷ lệ lỗi và cảnh báo có ngưỡng hợp lý. Hệ thống phát hiện cần xét cả **false positive**: việc bảo vệ không nên khiến hàng loạt người dùng hợp lệ bị khóa ngoài.

## 13. Dự án xuyên suốt: thiết kế authentication cho StudyHub

**Bối cảnh:** StudyHub có ba nhóm: học viên, giảng viên và quản trị viên; có web client, API và một tác vụ nền gọi dịch vụ nội bộ. Học viên có thể dùng passkey hoặc mật khẩu + MFA; giảng viên được phép liên kết với IdP của trường; quản trị viên phải xác thực lại trước hành động nhạy cảm. Đây là yêu cầu giả định để luyện thiết kế, không phải cấu hình mặc định cho mọi sản phẩm.

### 13.1. Hồ sơ thiết kế cần hoàn thành

1. **Mô hình danh tính:** account ID nội bộ bất biến; danh sách identifier, credential và liên kết IdP; quy tắc quyền của từng vai trò.
2. **Sơ đồ chuỗi:** đăng ký, login mật khẩu + MFA, login passkey, login OIDC, làm mới phiên, logout và recovery. Trên sơ đồ ghi rõ nguồn challenge, nơi xác minh, dữ liệu nào được tin cậy.
3. **Quy tắc phiên/token:** loại session phù hợp web/API, thời hạn, cách xoay và thu hồi, kiểm tra quyền mỗi request, chính sách xác thực lại.
4. **Threat model:** ít nhất một mối đe dọa tại mỗi trust boundary, tác động, kiểm soát và rủi ro còn lại.
5. **Bộ ca kiểm thử:** cả đường thành công, thất bại và hành vi tấn công giả lập an toàn trong môi trường thử nghiệm.

### 13.2. Ví dụ tiêu chí chấp nhận có thể kiểm thử

| Trường hợp kiểm thử | Kết quả mong đợi |
| --- | --- |
| Người lạ biết email nhưng sai mật khẩu nhiều lần | Không đăng nhập được; endpoint giới hạn lạm dụng mà không tiết lộ tài khoản. |
| Đúng mật khẩu nhưng MFA chưa hoàn tất | Không nhận session có toàn quyền; giao dịch chờ hết hạn hoặc bị hủy an toàn. |
| Gửi lại challenge WebAuthn cũ | Bị từ chối theo cơ chế chống replay của hệ thống. |
| Dùng token có audience khác API StudyHub | API từ chối. |
| Truy cập đường dẫn admin bằng phiên học viên | Bị từ chối bởi kiểm tra phân quyền phía máy chủ. |
| Đăng nhập xong rồi dùng lại session ID cũ chưa xác thực | Không thể nâng phiên cũ thành phiên đăng nhập mới. |
| Callback liên kết có state sai hoặc issuer lạ | Không hoàn tất đăng nhập hoặc liên kết tài khoản. |
| Sử dụng lại link khôi phục đã tiêu thụ | Link không còn hiệu lực. |
| Chủ tài khoản xóa credential cuối cùng | Hệ thống ngăn tự khóa tài khoản hoặc yêu cầu quy trình thay thế an toàn. |
| Tác vụ nền xuất trình chứng chỉ hợp lệ nhưng không có quyền phù hợp | API nội bộ từ chối hành động. |

### 13.3. Một vòng đánh giá thiết kế

Đọc lại từng sơ đồ theo vai kẻ tấn công: “Nếu có mật khẩu rò rỉ nhưng không có thiết bị thì sao?”, “Nếu có session cookie nhưng không có mật khẩu thì sao?”, “Nếu người dùng vào trang giả thì sao?”, “Nếu hệ thống IdP trả subject không đúng như dự kiến thì sao?”, “Nếu mất toàn bộ yếu tố khôi phục thì sao?”. Mỗi câu hỏi phải dẫn tới **một kết quả hệ thống kiểm chứng được**, thay vì lời hứa chung chung rằng “đã có bảo mật”.

## 14. Tự đánh giá và chọn hướng học tiếp

Tự kiểm tra bằng cách trả lời các câu sau mà không cần nhìn tài liệu:

1. Authentication, authorization và identity proofing khác nhau ở đâu?
2. Vì sao chỉ lưu SHA-256 của mật khẩu là chưa đủ?
3. Vì sao OTP có thể bị phishing trong khi WebAuthn có khả năng chống phishing?
4. Chứng chỉ TLS của server xác thực ai? Khi nào dùng mTLS?
5. Session cookie và access token có thể bị tấn công theo cách nào sau khi người dùng đã vượt MFA?
6. OAuth 2.0 và OIDC khác nhau ở mục tiêu gì? ID token phải được kiểm tra những gì?
7. Vì sao liên kết hai tài khoản theo email trùng có thể dẫn tới chiếm quyền?
8. Đường khôi phục yếu làm giảm độ an toàn của cơ chế đăng nhập mạnh ra sao?
9. Bạn sẽ kiểm thử phòng vệ trước replay, login abuse và session fixation thế nào?
10. Trong một thiết kế mới, bạn xác định trust boundary trước khi chọn thư viện hoặc giao thức bằng cách nào?

Nếu chưa trả lời được một câu, quay lại **chặng liên quan và cập nhật sơ đồ StudyHub**. Nếu trả lời được nhưng chưa chứng minh bằng ca kiểm thử, tiếp tục thực hành. **Hoàn thành lộ trình** nghĩa là bạn có thể giải thích lựa chọn, vẽ đúng luồng, chỉ ra các điểm tin cậy và chứng minh được hành vi bảo vệ của hệ thống.

Hướng đào sâu sau nền tảng: **WebAuthn/FIDO2 và vòng đời passkey; OAuth 2.0/OIDC security best practices; NIST SP 800-63 về bảo đảm danh tính và xác thực; OWASP Authentication, Session Management và Forgot Password Cheat Sheets**. Đọc phiên bản hiện hành của tài liệu chuẩn trước khi áp dụng vào sản phẩm cụ thể. Khi thiết kế thực tế, điều chỉnh theo loại tài khoản, mức nhạy cảm của hành động, nền tảng client và khả năng vận hành của đội ngũ.
