# Cross-browser test

**Cross-browser test** là hoạt động xác minh một ứng dụng web hoạt động đúng và giữ nguyên các kiểm soát bảo mật trên nhiều trình duyệt, engine, phiên bản và cấu hình người dùng. Với authentication, khác biệt giữa browser có thể làm thay đổi cách cookie được gửi, cách redirect được xử lý, cách lưu session, cách WebAuthn/passkey tương tác với authenticator, cách third-party storage bị giới hạn và cách người dùng hoàn tất MFA hoặc recovery.

Một luồng đăng nhập chạy tốt trên một browser không chứng minh nó an toàn trên các browser khác. Ví dụ, cookie SameSite có thể ảnh hưởng callback cross-site; browser privacy controls có thể chặn cookie bên thứ ba; WebAuthn yêu cầu origin và RP ID khớp; popup/redirect có thể bị chặn nếu không bắt đầu từ thao tác người dùng; autofill và password manager có thể thay đổi hành vi form. Cross-browser testing cần xác minh cả **tính tương thích** và **tính nhất quán của ranh giới bảo mật**.

Bài học thuộc module **SECURITY_AUTHENTICATION_FUNDAMENTALS**. Module giúp người học hiểu xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản; đồng thời mô hình hóa ranh giới tin cậy, phòng chống phishing, replay, lạm dụng đăng nhập và thiết kế luồng xác thực an toàn. Trong chương **Testing**, bài này tập trung vào kiểm thử chéo trình duyệt cho authentication flow.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Xây dựng browser support matrix theo engine, phiên bản, hệ điều hành và loại thiết bị.
2. Phân biệt cross-browser functional test, compatibility test, security regression test và visual test.
3. Kiểm thử cookie attributes, SameSite, storage, session lifecycle và CSRF trên nhiều browser.
4. Kiểm thử OAuth/OIDC redirect, Authorization Code + PKCE, popup và callback.
5. Kiểm thử WebAuthn/passkey, authenticator platform/cross-platform và điều kiện origin/RP ID.
6. Kiểm thử password manager, autofill, MFA và account recovery mà không làm yếu policy.
7. Phát hiện khác biệt do browser privacy controls, third-party cookie blocking, tracking protection và private browsing.
8. Thiết kế test data, browser profile và môi trường cô lập để tránh rò credential thật.
9. Tự động hóa bằng WebDriver/Playwright hoặc công cụ tương đương, đồng thời bổ sung kiểm thử thiết bị thật.
10. Xây dựng tiêu chí pass/fail, báo cáo coverage và quy trình xử lý browser regression.

## 2. Vì sao authentication cần cross-browser testing?

Browser là một phần của ranh giới tin cậy. Nó quyết định khi nào gửi cookie, cách xử lý redirect, quyền truy cập storage, hành vi popup, tích hợp authenticator và cách hiển thị giao diện đăng nhập. Các browser có thể dùng engine khác nhau, nhưng ngay cả hai browser dùng cùng engine cũng có thể khác phiên bản, policy, extension, privacy settings hoặc tích hợp hệ điều hành.

Các nhóm khác biệt thường gặp:

- **Cookie:** SameSite, Secure, HttpOnly, Domain, Path, expiry, cookie prefix và giới hạn cookie.
- **Navigation:** top-level redirect, popup, iframe, back/forward cache, redirect URI và custom scheme.
- **Storage:** cookie jar, local/session storage, IndexedDB, partitioning và private browsing.
- **Privacy:** third-party cookie restrictions, tracking prevention, anti-fingerprinting và storage eviction.
- **WebAuthn:** platform authenticator, roaming security key, passkey provider, user verification và conditional UI.
- **Form behavior:** password manager, autofill, input type, validation, virtual keyboard và focus.
- **Network/security:** TLS behavior, certificate validation, CORS, CSP, mixed content và service worker.
- **Accessibility:** screen reader, keyboard navigation, zoom, focus order và error announcement.

Không nên giả định mọi khác biệt đều là bug của ứng dụng. Một số là browser security control có chủ đích. Mục tiêu kiểm thử là xác minh ứng dụng vẫn an toàn và có fallback được thiết kế khi browser không hỗ trợ một capability.

### 2.1. Cross-browser test khác cross-device test

Cross-browser test tập trung vào browser/engine/version và cách browser xử lý web platform. Cross-device test tập trung thêm vào kích thước màn hình, input method, OS integration, hardware authenticator, network transition và lifecycle ứng dụng.

Ví dụ:
- Chrome desktop và Edge desktop có thể chia sẻ engine nhưng khác policy/extension.
- Safari trên macOS và Safari trên iOS có cùng thương hiệu nhưng khác môi trường hệ điều hành và lifecycle.
- Chrome Android có thể tích hợp passkey với credential provider của Android.
- Browser trên iOS có thể chịu ràng buộc từ WebKit và cơ chế hệ điều hành.

Vì vậy, ma trận nên ghi cả browser, engine, version, OS và device class, không chỉ tên browser.

## 3. Xây dựng browser support matrix

Không thể kiểm thử mọi tổ hợp browser/version/device. Hãy chọn ma trận theo người dùng mục tiêu, rủi ro authentication, telemetry và chính sách hỗ trợ.

### 3.1. Các chiều của ma trận

| Chiều | Giá trị cần ghi | Lý do |
| --- | --- | --- |
| Browser | Chrome, Edge, Firefox, Safari và browser được sản phẩm hỗ trợ | Khác biệt về behavior và release cadence. |
| Engine | Chromium/Blink, Gecko, WebKit | Nền tảng thực thi web API và cookie/storage behavior. |
| Version | Stable hiện tại và các phiên bản còn trong support policy | Bắt lỗi regression sau update. |
| OS | Windows, macOS, Linux, iOS, Android | Tích hợp authenticator, key store, browser policy. |
| Device class | Desktop, laptop, tablet, phone | Input, popup, camera, biometric và responsive behavior. |
| Profile | Standard, private/incognito, managed profile | Storage lifetime và enterprise policy. |
| Privacy mode | Default, strict tracking protection, third-party cookies blocked | Tác động SSO và cross-site flow. |
| Authenticator | Platform passkey, roaming key, password manager, TOTP app | Khả năng và luồng xác thực khác nhau. |
| Network | Normal, high latency, offline/online transition | Redirect, timeout và recovery. |
| Locale/accessibility | Locale chính, keyboard, screen reader, zoom | Đảm bảo login dùng được và không gây lỗi bảo mật. |

### 3.2. Phân nhóm ưu tiên

Một ma trận thực tế có thể chia thành:
- **Tier 1:** browser/version chiếm phần lớn người dùng và browser được hỗ trợ chính thức; chạy full critical authentication suite.
- **Tier 2:** browser/OS quan trọng nhưng tỷ trọng thấp hơn; chạy smoke suite và các security regression có liên quan.
- **Tier 3:** browser cũ hoặc môi trường đặc thù còn trong support policy; kiểm thử capability/fallback và luồng tối thiểu.
- **Unsupported:** hiển thị thông báo tương thích và đường dẫn cập nhật phù hợp; không âm thầm hạ security control để cố chạy.

Không lấy market share làm tiêu chí duy nhất. Một browser ít người dùng nhưng được sử dụng bởi nhóm quản trị hoặc môi trường enterprise có thể cần ưu tiên cao do mức độ rủi ro.

### 3.3. Ví dụ ma trận dự án

| Browser / môi trường | OS / thiết bị | Tier | Kiểm thử trọng tâm |
| --- | --- | --- | --- |
| Chrome Stable | Windows/macOS desktop | 1 | Password, MFA, OAuth redirect, cookie, passkey, logout. |
| Edge Stable | Windows managed desktop | 1 hoặc 2 theo telemetry | SSO enterprise, conditional access, cookie và password manager. |
| Firefox Stable | Windows/macOS/Linux | 1 hoặc 2 theo user base | Cookie, storage, redirect, WebAuthn và privacy controls. |
| Safari Stable | macOS desktop | 1 | ITP/privacy, passkey, popup/redirect, cookie. |
| Safari trên iOS | iPhone/iPad | 1 | Universal link, passkey provider, biometric handoff, app/browser transition. |
| Chrome trên Android | Android phone/tablet | 1 | Passkey, autofill, secure context, app links và lifecycle. |
| Browser private mode | Desktop/mobile | 2 | Storage lifetime, cookie restrictions và clean logout. |
| Browser có tracking protection strict | Browser/OS hỗ trợ | 2 | SSO cross-site, third-party storage và fallback. |

Đây là ma trận minh họa. Team cần thay tier bằng telemetry thực tế, support policy, release channel và yêu cầu hợp đồng.

## 4. Xác định phạm vi và test oracle

Trước khi chạy test, xác định điều gì chứng minh một luồng thành công và điều gì là lỗi bảo mật.

### 4.1. Test oracle

Với authentication, oracle không chỉ là “trang dashboard xuất hiện”. Cần xác minh:
- Principal đúng được gắn vào session.
- Authentication method và assurance level đúng với policy.
- Session/token được tạo đúng một lần theo semantics.
- Cookie flags và scope chính xác.
- Token không xuất hiện ở URL, console, log hoặc browser storage ngoài thiết kế.
- Redirect chỉ tới URI đã đăng ký.
- CSRF protection vẫn hoạt động.
- Logout/revoke làm credential cũ bị từ chối.
- Browser không hỗ trợ capability thì flow dừng an toàn hoặc dùng fallback đã được phê duyệt.
- Không có account enumeration qua nội dung hoặc timing dễ phân biệt ngoài policy.

### 4.2. Phân biệt functional và security regression

| Loại test | Ví dụ | Kết quả cần kiểm tra |
| --- | --- | --- |
| Functional | Đăng nhập password thành công | User vào đúng account. |
| Compatibility | Cookie được lưu và gửi đúng trong Safari | Session hoạt động theo policy. |
| Security regression | Cookie thiếu HttpOnly | Test phải thất bại. |
| Protocol | OAuth callback có state và PKCE hợp lệ | Code được đổi đúng transaction. |
| Negative | Redirect URI không đăng ký | Request bị từ chối. |
| Recovery | Third-party cookie bị chặn | Recovery/login vẫn theo flow an toàn đã thiết kế. |
| Accessibility | MFA dialog dùng được bằng keyboard/screen reader | Focus, label và error announcement đúng. |

Một functional test pass không thể thay thế security regression test. Ví dụ login thành công dù cookie bị đặt SameSite=None không cần thiết vẫn là một regression cần phát hiện.

## 5. Kiểm thử cookie và session trên nhiều browser

Cookie là một trong các nguồn khác biệt quan trọng nhất với web authentication.

### 5.1. Xác minh Set-Cookie

Với mỗi browser Tier 1, kiểm tra response login và các endpoint refresh/session:
- Cookie xác thực có Secure.
- Cookie nhạy cảm có HttpOnly.
- SameSite đúng theo flow và không được nới lỏng ngoài yêu cầu.
- Domain bị bỏ nếu cần host-only cookie.
- Path đúng scope, nhưng không được coi là biện pháp authorization.
- Max-Age/Expires khớp policy; server-side expiry vẫn được enforce.
- Prefix __Host- hoặc __Secure- được dùng đúng điều kiện.
- Không có cookie trùng tên khác scope gây parser ambiguity.
- Không có session identifier trong URL hoặc fragment.

Không chỉ đọc header bằng test HTTP client. Cần xác minh browser thực sự lưu cookie và gửi nó trong request tiếp theo theo behavior của browser.

### 5.2. SameSite và cross-site navigation

Kiểm thử các tình huống:
1. Người dùng truy cập app trực tiếp.
2. Người dùng mở app từ một link trên site khác.
3. OIDC redirect từ RP sang OP và quay lại.
4. Callback qua top-level GET hoặc POST tùy response mode.
5. Login popup nếu sản phẩm hỗ trợ.
6. Flow embedded/iframe nếu có và được policy cho phép.
7. Third-party cookie bị chặn hoặc partitioned.
8. Người dùng bật strict tracking protection.

Không giả định SameSite=Lax sẽ hoạt động giống nhau cho mọi loại callback. Browser có thể xử lý top-level navigation, POST và iframe khác nhau. Test theo response mode thực tế và browser version được hỗ trợ. Nếu flow cần cookie cross-site, xác định chính xác cookie nào cần SameSite=None; Secure và tại sao.

### 5.3. Cookie expiry, restart và private browsing

Kiểm tra:
- Cookie session không có expiry phía client nhưng server-side idle/absolute timeout vẫn có hiệu lực.
- Persistent cookie hết hạn theo Max-Age/Expires.
- Browser restart hoặc session restore không làm session server-side hết hạn bị sống lại.
- Private/incognito mode không dùng chung cookie với normal profile.
- Khi đóng private window, browser có thể xóa storage; app không được dựa vào đó làm cơ chế revoke.
- Cookie bị xóa ở client nhưng bản sao cũ vẫn bị server từ chối sau logout.
- Cookie bị đổi domain/path không được dùng để vượt session boundary.

### 5.4. Session rotation và logout

Sau login, MFA step-up hoặc credential change, kiểm tra session ID được rotate theo policy. Sau logout:
- Response xóa cookie đúng name/path/domain scope.
- Server-side session bị revoke.
- Request phát lại cookie cũ bị từ chối.
- Back/forward navigation không hiển thị dữ liệu nhạy cảm đã cache.
- Logout một thiết bị không vô tình revoke thiết bị khác nếu policy hỗ trợ session riêng.
- Cache/service worker không phục vụ dữ liệu account sau logout.

## 6. Kiểm thử OAuth 2.0 và OpenID Connect

OAuth/OIDC thường có redirect qua nhiều origin và browser context, vì vậy cần test kỹ navigation, cookie, state, nonce và PKCE.

### 6.1. Authorization Code + PKCE

Kiểm thử:
- Authorization request chứa state, nonce nếu OIDC và PKCE challenge.
- PKCE method dùng S256 theo policy.
- Callback chỉ chấp nhận redirect URI đã đăng ký.
- State được liên kết với transaction browser và chỉ dùng một lần.
- Authorization code được đổi tại token endpoint đúng issuer.
- Code verifier không xuất hiện trong URL, log hoặc telemetry.
- Code bị replay hoặc state không khớp bị từ chối.
- Tab/popup đóng hoặc browser restart giữa flow không làm callback cũ được chấp nhận.
- Browser privacy setting không làm mất transaction cookie mà không có fallback an toàn.

### 6.2. Redirect, popup và opener

Popup có thể bị chặn nếu không được mở trực tiếp từ user gesture. Cross-origin opener policy hoặc browser privacy behavior có thể ảnh hưởng giao tiếp giữa cửa sổ. Hãy test:
- Popup được mở sau click/tap thực sự.
- Nếu popup bị chặn, UI đưa ra đường top-level redirect an toàn.
- window.opener không được tin cậy như một kênh xác thực nếu không kiểm tra origin/message.
- postMessage xác minh origin, message schema và transaction ID.
- Không dùng wildcard target origin cho dữ liệu nhạy cảm.
- Callback không gửi token qua URL hoặc postMessage tới origin không tin cậy.
- Người dùng mở nhiều tab không làm state của transaction này ghi đè transaction khác.

### 6.3. SSO và third-party cookie restrictions

Một số SSO integration cũ phụ thuộc cookie trong iframe hoặc third-party context. Browser có thể chặn third-party cookies hoặc giới hạn storage. Kiểm thử:
- Top-level redirect flow.
- Silent authentication/iframe nếu còn được hỗ trợ.
- Storage partitioning và third-party cookie blocking.
- Logout giữa RP/OP.
- Callback khi user có nhiều account tại IdP.
- Hành vi khi OP session còn nhưng RP session đã logout.

Nếu browser chặn third-party cookie, ứng dụng phải hiển thị bước đăng nhập/redirect rõ ràng hoặc dùng flow được hỗ trợ. Không yêu cầu người dùng tắt browser protection như giải pháp mặc định; không mở rộng cookie domain hoặc giảm CSRF protection chỉ để iframe tiếp tục hoạt động.

## 7. Kiểm thử WebAuthn và passkey

WebAuthn là phần cần test cả browser API và authenticator/platform integration.

### 7.1. Điều kiện cơ bản

- Trang chạy trong secure context (HTTPS; localhost có ngoại lệ phát triển theo browser).
- RP ID hợp lệ và thuộc phạm vi origin.
- Origin được server kiểm tra chính xác.
- Challenge ngẫu nhiên, gắn transaction và chỉ dùng một lần.
- Server xác minh clientDataJSON, challenge, origin, RP ID hash, signature và user verification theo policy.
- Credential ID và public key được lưu đúng account.
- Không log assertion chứa dữ liệu nhạy cảm hoặc credential response thô không cần thiết.

### 7.2. Các loại authenticator

| Authenticator | Kiểm thử |
| --- | --- |
| Platform authenticator | Passkey trên thiết bị, biometric/PIN, user verification, account selection. |
| Roaming security key | USB/NFC/Bluetooth nếu browser và OS hỗ trợ; PIN/touch. |
| Synced passkey | Credential provider, account sync và hành vi đổi thiết bị. |
| Cross-device authentication | QR/handoff và xác minh đúng relying party. |
| No authenticator available | Thông báo và fallback đã đăng ký, không tự bỏ xác thực mạnh. |

Không phải browser/OS nào cũng hỗ trợ cùng một loại authenticator hoặc conditional UI. Test capability detection và graceful fallback. Không dùng user-agent sniffing làm cơ chế bảo mật; feature detection và server-side verification mới quyết định.

### 7.3. Negative WebAuthn tests

- Origin sai.
- RP ID không khớp.
- Challenge hết hạn hoặc bị replay.
- Signature sai hoặc credential ID không tồn tại.
- User verification bắt buộc nhưng authenticator không đáp ứng.
- User cancel hoặc đóng browser prompt.
- Credential bị revoke/xóa trong lúc flow đang chạy.
- Callback tới nhầm tab hoặc transaction.
- Browser không hỗ trợ WebAuthn hoặc API bị policy disable.

Kết quả mong đợi là server từ chối assertion không hợp lệ, ghi event an toàn và không tạo session. UI có thể đề xuất phương thức đã đăng ký khác theo policy.

## 8. Kiểm thử password, autofill và MFA

### 8.1. Password form và password manager

Kiểm thử:
- autocomplete semantics đúng, ví dụ username/current-password/new-password.
- Input type và label không làm password manager nhầm trường.
- Paste password được hỗ trợ; không chặn paste tùy tiện.
- Autofill không ghi password vào hidden field hoặc field sai.
- Submit không gửi password qua query string.
- Password không xuất hiện trong console, analytics, DOM snapshot hoặc screenshot artifact.
- Error message không tiết lộ account tồn tại hay không ngoài policy.
- Keyboard/virtual keyboard không che nút submit hoặc MFA control.

Password manager behavior có thể khác giữa browser và extension. Không dựa vào extension bên ngoài để chứng minh bảo mật; test cả browser built-in password manager và form thủ công.

### 8.2. MFA

Với TOTP:
- Input một mã hợp lệ trong time window.
- Mã sai, hết hạn và mã đã dùng theo replay policy.
- Clock skew trong giới hạn được hỗ trợ.
- Resend/attempt rate limit.
- Không ghi OTP vào log hoặc browser telemetry.

Với push:
- Challenge pending, approve, deny, timeout và duplicate notification.
- Không chấp nhận approval từ transaction khác.
- UI thể hiện đúng số/challenge context nếu number matching được dùng.
- Browser refresh/back không tạo challenge mới vô hạn.

Với email/SMS:
- Không coi delivery thành công là authentication success.
- Link/code hết hạn và chỉ dùng một lần theo policy.
- Deep link/callback đúng origin và transaction.
- Không đưa secret vào referrer, analytics hoặc URL log.

### 8.3. Step-up authentication

Kiểm thử hành động nhạy cảm như đổi recovery email, thêm passkey, export dữ liệu hoặc thay role:
- Browser hiện tại có session hợp lệ nhưng auth_time cũ.
- Policy yêu cầu step-up.
- Step-up thành công nâng assurance và session/token context theo thiết kế.
- Step-up thất bại/hủy không thực hiện hành động.
- Tab khác không tự động được nâng quyền nếu không cùng transaction/session semantics.
- Browser back không replay hành động đã commit.

## 9. Storage, privacy controls và browser lifecycle

Browser privacy controls có thể thay đổi khả năng lưu state giữa các origin và phiên. Kiểm thử cần phản ánh cấu hình người dùng thực tế.

### 9.1. Storage API

Kiểm tra hành vi của:
- Cookies.
- sessionStorage.
- localStorage.
- IndexedDB.
- Cache Storage/service worker.
- BroadcastChannel hoặc storage event nếu dùng đồng bộ tab.
- Partitioned storage nếu flow có liên quan.

Không lưu long-lived bearer token vào web storage chỉ để tiện dùng. Nếu ứng dụng dùng BFF, browser nên giữ session cookie được bảo vệ và backend quản lý OAuth token. Dù vậy, XSS vẫn có thể gọi API cùng origin; cần CSP, output encoding, authorization và CSRF defense.

### 9.2. Private browsing và storage eviction

Kiểm thử:
- Storage bị xóa khi đóng private profile.
- IndexedDB/cookie bị giới hạn dung lượng hoặc eviction.
- Browser restart giữa enrollment hoặc recovery.
- App mở nhiều tab và storage event xảy ra.
- Storage write thất bại hoặc quota exceeded.
- User clear site data trong lúc đang đăng nhập.

Khi storage mất, app nên chuyển về trạng thái signed-out hoặc recovery an toàn; không dựng session giả từ dữ liệu UI cache.

### 9.3. Tracking protection và third-party cookie blocking

Test trong:
- Default privacy settings.
- Strict tracking prevention.
- Block third-party cookies.
- Browser có storage partitioning.
- Managed browser policy trong enterprise.

Ghi nhận capability và behavior, nhưng không thu thập fingerprint thiết bị quá mức. Không yêu cầu người dùng tắt privacy feature như điều kiện đăng nhập chung. Nếu flow SSO cần thay đổi, ưu tiên redirect top-level và transaction state an toàn.

## 10. CORS, CSP, TLS và browser security policy

Cross-browser testing cần kiểm tra cả các policy web platform:
- CORS cho đúng origin/method/header; credentialed request không dùng wildcard origin.
- CSP cho script, frame, form action, connect-src và trusted origins.
- frame-ancestors hoặc X-Frame-Options để ngăn clickjacking theo policy.
- HSTS và HTTPS; không có mixed content.
- Certificate chain hợp lệ, hostname đúng và expiry được kiểm tra.
- Referrer-Policy giảm nguy cơ lộ URL chứa thông tin nhạy cảm.
- Permissions-Policy giới hạn API không cần thiết.
- Cross-Origin-Opener-Policy/Cross-Origin-Embedder-Policy nếu app dùng; kiểm tra tác động popup/OIDC.
- Service worker scope và cache không làm lộ account data sau logout.

Đừng dùng browser flag tắt same-origin policy, certificate validation hoặc web security để làm test pass. Test phải chạy gần với môi trường người dùng thật; nếu cần mock dependency, mock ở boundary được kiểm soát và vẫn giữ browser security model.

## 11. Accessibility và localization của authentication UI

Một flow xác thực không hoàn tất được vì keyboard/focus lỗi vẫn là lỗi chất lượng. Kiểm thử:
- Tất cả field, button, dialog và error có accessible name/role.
- Keyboard-only navigation theo thứ tự hợp lý.
- Focus được đưa tới dialog MFA/passkey và trả về đúng nơi sau khi đóng.
- Error được announce cho screen reader.
- Không chỉ dùng màu sắc để biểu diễn lỗi hoặc trạng thái.
- Zoom 200% và text scaling không che nút/OTP input.
- RTL, locale và định dạng số/thời gian không làm sai OTP/TOTP.
- Virtual keyboard mobile không che nội dung quan trọng.
- Timeout có thông báo và cách tiếp tục an toàn.
- Copy/paste recovery code có thể thực hiện, nhưng secret không được lưu clipboard lâu hơn cần thiết nếu sản phẩm có kiểm soát.

Accessibility test không nên bị coi là phần phụ tách khỏi security: người dùng không thể hoàn tất MFA có thể bị hướng sang recovery yếu hơn nếu UX không được thiết kế tốt.

## 12. Chiến lược automation và kiểm thử thủ công

Không có một công cụ đơn lẻ bao phủ mọi browser/authenticator. Kết hợp automation, browser matrix CI, thiết bị thật và kiểm thử exploratory.

### 12.1. Automation

Có thể dùng:
- Playwright cho browser automation và nhiều engine/browser project.
- WebDriver/Selenium cho browser/driver ecosystem phù hợp.
- BrowserStack/Sauce Labs hoặc device farm tương đương nếu cần thiết bị/browser cloud.
- Native test trên iOS/Android khi flow chuyển giữa app và browser hệ thống.
- Contract/API test cho issuer, token endpoint và session service.

Automation tốt cho regression lặp lại: cookie flags, redirect validation, CSRF, login/logout, form behavior và negative test. Một số capability như biometric prompt, roaming security key, synced passkey và enterprise browser policy có thể cần hardware/device thật hoặc môi trường quản lý chuyên biệt.

### 12.2. Cô lập browser profile

Mỗi test nên dùng browser context/profile riêng:
- Không dùng profile cá nhân có cookie hoặc password thật.
- Tạo test account và credential riêng cho môi trường.
- Xóa context sau test.
- Không chia sẻ storage state giữa test không cùng mục tiêu.
- Tắt extension không cần thiết trong baseline; chạy thêm test riêng với extension/managed policy nếu thuộc support scope.
- Giữ screenshot/video/trace đã redacted; không lưu password, OTP hoặc token trong artifact.
- Giới hạn quyền truy cập CI artifact.

### 12.3. Ví dụ Playwright project matrix

~~~typescript
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/auth",
  projects: [
    {
      name: "chromium-desktop",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "firefox-desktop",
      use: { ...devices["Desktop Firefox"] },
    },
    {
      name: "webkit-desktop",
      use: { ...devices["Desktop Safari"] },
    },
  ],
  use: {
    baseURL: process.env.AUTH_TEST_BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
~~~

Đây là ví dụ cấu hình khởi đầu. Cần dùng version Playwright và browser binary được pin trong CI. WebKit project không thay thế hoàn toàn Safari trên thiết bị Apple; test passkey/OS integration cần Safari/OS thật khi thuộc support scope. Artifact trace/screenshot có thể chứa dữ liệu nhạy cảm; dùng test credentials, redaction và access control.

### 12.4. Ví dụ kiểm tra cookie flags

~~~typescript
import { test, expect } from "@playwright/test";

test("session cookie has required security attributes", async ({ page, context }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(process.env.AUTH_TEST_USER!);
  await page.getByLabel("Password").fill(process.env.AUTH_TEST_PASSWORD!);
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page).toHaveURL(/dashboard/);

  const cookies = await context.cookies();
  const session = cookies.find((cookie) => cookie.name === "__Host-sid");

  expect(session).toBeTruthy();
  expect(session?.secure).toBe(true);
  expect(session?.httpOnly).toBe(true);
  expect(session?.sameSite).toBe("Lax");
  expect(session?.domain).not.toContain("example.test");
  expect(session?.path).toBe("/");
});
~~~

Test cần thay label, cookie name và expected SameSite theo ứng dụng. Với __Host-, browser phải áp dụng điều kiện prefix; ngoài API cookie, có thể kiểm tra response header để xác minh không có Domain. Không in cookie value vào test output. Dùng secret injection của CI, không commit credentials vào repository.

### 12.5. Ví dụ kiểm thử logout/replay

~~~typescript
test("revoked session cookie is rejected after logout", async ({ page, context, request }) => {
  await signInWithTestAccount(page);

  const cookies = await context.cookies();
  const session = cookies.find((cookie) => cookie.name === "__Host-sid");
  expect(session).toBeTruthy();

  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/login/);

  const response = await request.get("/api/account", {
    headers: {
      Cookie: "__Host-sid=" + session.value,
    },
  });

  expect([401, 403]).toContain(response.status());
});
~~~

Ví dụ này minh họa replay test trong môi trường test cô lập. Trong suite thật, cần tránh để token/cookie xuất hiện trong report hoặc trace. Request replay phải dùng cookie test và xác minh server-side session đã revoked; chỉ kiểm tra browser cookie biến mất là chưa đủ.

## 13. Quản lý test data và môi trường

Authentication test cần credential giả lập nhưng có cấu trúc giống production:
- Test account riêng theo role, tenant và assurance level.
- Password ngẫu nhiên, không dùng lại password cá nhân.
- Passkey/test authenticator được provision trong môi trường test phù hợp.
- MFA test provider có sandbox hoặc test-only seed được bảo vệ.
- OAuth/OIDC issuer sandbox với redirect URI riêng.
- Token TTL ngắn, revoke/reset sau test.
- Test data được dọn bằng API quản trị có audit.
- Không dùng production account/token trong browser automation.
- Không ghi credential vào test fixture, snapshot, console hoặc CI artifact.

Tách environment theo trust boundary. Không cho browser test từ pull request không tin cậy truy cập secret production. Không mở endpoint test bypass authentication trên production. Nếu cần mock MFA hoặc IdP, chỉ bật trong test environment được cô lập và xác minh không thể kích hoạt từ production configuration.

### 13.1. Deterministic test và clock

Một số test phụ thuộc thời gian:
- Access token expiry.
- TOTP time window.
- Session idle/absolute timeout.
- Recovery link expiry.
- WebAuthn challenge timeout.

Dùng controllable clock ở service/test harness khi có thể; không sửa đồng hồ hệ điều hành của shared CI runner. Với TOTP, dùng test seed và clock fixture trong sandbox. Với browser cookie expiry, kiểm tra server-side expiry riêng vì browser clock và cookie engine có thể khác.

### 13.2. Network condition

Mô phỏng:
- Latency cao.
- Request timeout.
- Connection reset.
- Offline rồi online.
- Redirect response chậm.
- Token endpoint 429/5xx.
- MFA provider delayed response.
- Browser tab đóng giữa callback.
- Duplicate callback hoặc callback đến sai thứ tự.

Đảm bảo test phân biệt response đã commit ở server với response bị mất trên mạng. Với refresh token rotation, timeout không có nghĩa request chưa được xử lý; không tự động retry token cũ trong test để mong đợi success.

## 14. Bộ test matrix cho authentication

Bảng dưới đây là baseline để team chọn theo risk và support scope.

| Nhóm | Test case | Expected result |
| --- | --- | --- |
| Login | Password hợp lệ | Login đúng account, session mới được tạo. |
| Login | Password sai | Generic failure, không lộ account existence. |
| Login | Account disabled | Từ chối theo policy, không tạo session. |
| Cookie | Secure thiếu | Security regression fail. |
| Cookie | HttpOnly thiếu | Security regression fail với session cookie. |
| Cookie | SameSite sai theo flow | Test compatibility/security fail. |
| Cookie | Domain rộng không cần thiết | Test scope fail. |
| Session | Session ID không rotate sau login | Security regression fail. |
| Session | Cookie cũ replay sau logout | Server từ chối. |
| Session | Idle/absolute expiry | Server từ chối dù browser vẫn gửi cookie. |
| CSRF | POST thiếu token | Từ chối. |
| CSRF | Cross-site form submit | Không thực hiện thay đổi trạng thái trái phép. |
| OAuth | State mismatch | Callback bị từ chối. |
| OAuth | PKCE verifier sai | Code exchange thất bại. |
| OAuth | Redirect URI không đăng ký | Authorization server từ chối. |
| OAuth | Popup bị chặn | Có fallback top-level redirect an toàn. |
| OAuth | Nhiều tab login | Transaction không ghi đè hoặc trộn state. |
| OIDC | Issuer/nonce mismatch | ID token/callback bị từ chối. |
| SSO | Third-party cookie blocked | Flow dùng fallback được hỗ trợ hoặc thông báo rõ; không bypass. |
| Passkey | Origin/RP ID sai | Assertion bị từ chối. |
| Passkey | Challenge replay | Assertion bị từ chối. |
| Passkey | User verification bắt buộc nhưng không đạt | Không tạo session. |
| Passkey | Không có authenticator | Fallback đã enroll hoặc dừng an toàn. |
| MFA | OTP sai/hết hạn/replay | Không hoàn tất MFA. |
| MFA | Push deny/timeout | Không coi là success. |
| MFA | Challenge spam | Rate limit/cooldown và alert theo policy. |
| Recovery | Link hết hạn hoặc đã dùng | Từ chối. |
| Recovery | Browser private mode mất state | Recovery yêu cầu transaction mới an toàn. |
| Storage | localStorage/IndexedDB bị xóa | App chuyển trạng thái an toàn; không tạo session giả. |
| Privacy | Strict tracking protection | Không mở rộng quyền cookie ngoài thiết kế. |
| Browser lifecycle | Back/forward sau logout | Không lộ dữ liệu account đã cache. |
| Accessibility | Keyboard/screen reader MFA | Có thể hoàn tất và hiểu lỗi. |
| Network | Token endpoint timeout | Không retry refresh cũ trái semantics. |
| Security headers | CSP/CORS/HSTS sai | Regression test phát hiện. |
| Logging | Token/password trong console/trace | Test fail; artifact phải được redacted. |

## 15. Đánh giá kết quả và xử lý regression

Một test report cần ghi:
- Test ID, requirement và risk liên quan.
- Browser name, engine, version, OS, device class.
- Profile/privacy setting và authenticator type.
- App build, environment, issuer và policy version.
- Kết quả, timestamp, duration và failure category.
- Screenshot/trace đã redacted khi cần.
- Severity, reproduction steps và owner.

Phân loại lỗi:
- **Functional regression:** người dùng không thể hoàn tất flow hợp lệ.
- **Security regression:** browser-specific behavior làm yếu hoặc bỏ qua kiểm soát.
- **Compatibility issue:** capability không được hỗ trợ nhưng fallback chưa đúng.
- **Environment/test issue:** provider sandbox, test data hoặc CI browser binary lỗi.
- **Intermittent/flaky:** timing, race hoặc network; cần tìm nguyên nhân, không chỉ retry test đến khi xanh.

Security regression có thể nghiêm trọng dù chỉ xảy ra trên một browser. Ví dụ, cookie bị gửi cross-site ngoài dự kiến hoặc callback state không được kiểm tra là lỗi bảo mật, không phải cosmetic issue.

### 15.1. Release gate

Một release có thể yêu cầu:
- Tất cả Tier 1 smoke và critical auth tests pass.
- Không có unresolved critical/high security regression.
- Cookie/header/redirect contract tests pass.
- Passkey/MFA tests pass trên môi trường hỗ trợ đã định.
- Logout/revocation tests pass.
- Browser version matrix được cập nhật.
- Flaky test có owner và không che giấu failure.
- Test artifact đã redacted.
- Unsupported browser behavior có thông báo và fallback được phê duyệt.

Không dùng tỷ lệ test pass tổng hợp để che một lỗi bảo mật nghiêm trọng. Một test CSRF fail trên Safari không thể được bù bằng hàng trăm visual test pass trên Chromium.

## 16. Bài thực hành: Cross-browser test cho StudyHub

**Bối cảnh:** StudyHub có web app và trang quản trị. Người dùng đăng nhập bằng password hoặc passkey; tài khoản giảng viên/quản trị yêu cầu MFA khi thực hiện hành động nhạy cảm. Web app dùng session cookie __Host-sid, OIDC SSO với một external IdP và Course API. Người dùng có thể đăng nhập trên Chrome, Edge, Firefox, Safari desktop và Safari/Chrome mobile. Một số browser bật strict tracking protection hoặc block third-party cookies.

### 16.1. Nhiệm vụ

Thiết kế một cross-browser test plan:
1. Xác định browser/engine/version/OS/device support matrix và Tier.
2. Chọn full suite, smoke suite và manual hardware tests.
3. Kiểm tra cookie flags, host-only scope, SameSite và server-side session expiry.
4. Kiểm thử OAuth/OIDC redirect, state, nonce, PKCE và nhiều tab.
5. Kiểm thử passkey trên platform authenticator, roaming key và browser không hỗ trợ.
6. Kiểm thử password manager/autofill, TOTP, push MFA và recovery.
7. Kiểm thử third-party cookie blocking, private browsing và storage partitioning.
8. Kiểm thử logout, cookie replay, back/forward cache và service worker.
9. Kiểm thử CORS, CSP, HSTS, popup và postMessage origin validation.
10. Kiểm thử accessibility và localization.
11. Định nghĩa test data, secret injection, redaction và artifact retention.
12. Đặt release gate và quy trình triage regression.

### 16.2. Bảng test run mẫu

| Browser | Version | OS/device | Privacy mode | Auth method | Result | Issue |
| --- | --- | --- | --- | --- | --- | --- |
| Chrome | Stable pinned | Windows desktop | Default | Password + TOTP | Pending | — |
| Firefox | Stable pinned | macOS desktop | Strict | OIDC + passkey | Pending | — |
| Safari | Stable pinned | macOS desktop | Default | Passkey | Pending | — |
| Safari | Current supported | iPhone | Default | Passkey + biometric | Pending | — |
| Chrome | Current supported | Android phone | Default | Password manager + TOTP | Pending | — |
| Edge | Managed stable | Windows desktop | Enterprise policy | SSO + MFA | Pending | — |

Bảng là mẫu ghi nhận; thay Pending bằng kết quả từ test run thật. Không đánh dấu pass dựa trên browser emulation nếu test yêu cầu OS authenticator hoặc privacy policy thật.

### 16.3. Bộ ca kiểm thử chấp nhận

1. Login password thành công trên mọi Tier 1 browser.
2. Password sai không tiết lộ account existence qua UI.
3. Cookie session có Secure, HttpOnly, SameSite và host-only scope đúng policy.
4. Cookie prefix __Host- bị browser từ chối nếu cấu hình vi phạm điều kiện.
5. Session ID được rotate sau login và step-up.
6. Session cookie cũ bị từ chối sau logout trên mọi browser.
7. SameSite callback hoạt động theo response mode OIDC được hỗ trợ.
8. Third-party cookie blocking không dẫn đến bypass state/nonce/PKCE.
9. State mismatch, nonce mismatch và PKCE mismatch đều bị từ chối.
10. Popup bị chặn có fallback top-level redirect an toàn.
11. WebAuthn origin/RP ID/challenge được xác minh server-side.
12. Browser không có authenticator không được tự động hạ assurance.
13. TOTP sai/hết hạn/replay không hoàn tất MFA.
14. Push MFA deny/timeout không được ghi nhận là success.
15. Password manager autofill đúng field và không làm lộ password.
16. Private browsing không dùng lại session của normal profile.
17. Browser storage bị clear không tạo lại session giả.
18. Back/forward cache không hiển thị dữ liệu nhạy cảm sau logout.
19. CSRF request cross-site bị từ chối.
20. CSP/CORS/HSTS và certificate validation đúng trên browser được hỗ trợ.
21. Keyboard/screen reader có thể hoàn tất login/MFA.
22. Network timeout giữa token refresh không gây replay refresh token cũ.
23. Screenshot/trace/console không chứa raw password, OTP, token hoặc cookie.
24. Browser version update không làm security regression âm thầm.

### 16.4. Câu hỏi tự đánh giá

1. Vì sao authentication cần cross-browser test thay vì chỉ test một browser?
2. Browser engine, browser version và OS/device khác nhau ở đâu?
3. Vì sao SameSite behavior cần kiểm thử theo loại callback?
4. Third-party cookie blocking có thể ảnh hưởng SSO thế nào?
5. WebAuthn phụ thuộc origin, RP ID và challenge ra sao?
6. Vì sao passkey cần test trên thiết bị thật?
7. Popup bị chặn cần fallback gì để giữ security?
8. Vì sao chỉ kiểm tra cookie biến mất ở browser chưa chứng minh logout an toàn?
9. Làm sao test refresh token timeout mà không vô tình replay token cũ?
10. Vì sao private browsing và normal profile cần browser context riêng?
11. Những dữ liệu nào không được xuất hiện trong screenshot, trace hoặc console?
12. Làm sao xác định Tier và release gate dựa trên risk?
13. Vì sao browser privacy protection không nên bị tắt để làm test pass?
14. Khi một browser không hỗ trợ capability, fallback nào được phép?

**Tiêu chí hoàn thành:** Người học có thể xây browser support matrix, kiểm thử authentication protocol và browser behavior trên các engine/OS được hỗ trợ, phát hiện security regression do cookie/redirect/storage/WebAuthn, quản lý test credential an toàn và đưa ra release decision dựa trên risk cùng bằng chứng.

## 17. Các lỗi thiết kế phổ biến

- **Chỉ test trên Chromium:** bỏ sót WebKit/Gecko và privacy behavior khác.
- **Chỉ ghi tên browser:** không pin version, OS và device nên không tái hiện được lỗi.
- **Dùng user-agent sniffing làm bảo mật:** dễ sai và không chứng minh capability.
- **Chỉ test happy path:** bỏ qua state mismatch, replay, timeout và browser privacy setting.
- **Nới SameSite hoặc Domain để SSO chạy:** có thể mở rộng cross-site/cross-subdomain exposure.
- **Tắt tracking protection:** che giấu vấn đề compatibility và làm test xa môi trường thật.
- **Dùng embedded WebView tùy tiện cho login:** có thể làm suy yếu trust boundary và SSO integration.
- **Chỉ kiểm tra UI sau login:** không kiểm tra cookie, token, principal và server-side session.
- **Giả lập passkey bằng mock ở mọi nơi:** không kiểm tra platform authenticator/OS integration.
- **Dùng profile cá nhân trong CI:** có thể lộ cookie/password và làm test flaky.
- **Ghi trace/screenshot chưa redacted:** biến artifact thành nơi lưu credential.
- **Retry flaky test vô hạn:** che giấu race hoặc regression thực.
- **Chỉ kiểm tra cookie bị xóa ở client:** không chứng minh server đã revoke session.
- **Bỏ qua back/forward cache/service worker:** dữ liệu account có thể còn hiển thị sau logout.
- **Không test keyboard/accessibility:** người dùng bị mắc kẹt và tìm đường fallback yếu hơn.
- **Gộp tất cả browser thành một pass rate:** che giấu lỗi bảo mật chỉ xảy ra trên một engine.
- **Không test browser update:** release mới có thể thay đổi cookie/privacy/WebAuthn behavior.
- **Không cô lập test account:** test song song có thể làm nhiễm session/token lẫn nhau.

## 18. Vận hành browser compatibility và cập nhật định kỳ

Browser release cadence nhanh; test matrix cần được cập nhật thường xuyên:
- Theo dõi release stable/beta của browser thuộc support policy.
- Pin binary trong CI để kết quả có thể tái lập.
- Chạy smoke suite trên browser mới trước khi mở rộng traffic.
- Chạy security regression khi browser thay đổi cookie, storage, WebAuthn hoặc privacy behavior.
- Có thiết bị thật cho passkey, biometric và app/browser handoff.
- Theo dõi telemetry lỗi theo browser/version nhưng giảm thiểu định danh người dùng.
- Đặt owner cho mỗi browser Tier và quy trình loại bỏ phiên bản hết hỗ trợ.
- Ghi rõ browser/OS không hỗ trợ và fallback được duyệt.
- Review extension/enterprise policy nếu nhóm người dùng quản lý thiết bị.
- Kiểm tra lại sau khi thay IdP, cookie policy, CSP, SDK hoặc auth library.

Không cần chạy full suite trên mọi commit nếu chi phí quá lớn. Có thể chạy fast smoke trên pull request, critical security suite theo lịch hoặc trước release, và full device matrix trên release candidate. Tuy nhiên, thay đổi auth/cookie/redirect/WebAuthn phải kích hoạt test phù hợp với phạm vi ảnh hưởng.

## 19. Tài liệu tham khảo và hướng đọc tiếp

- **MDN Web Docs — Browser compatibility data (BCD):** theo dõi hỗ trợ web API và behavior theo browser/version.
- **Playwright documentation:** browser projects, contexts, tracing và test isolation.
- **WebDriver specification:** chuẩn hóa browser automation.
- **Web Authentication: An API for accessing Public Key Credentials (WebAuthn):** origin, RP ID, challenge và authenticator behavior.
- **RFC 8252 — OAuth 2.0 for Native Apps:** external user-agent và native app redirect flow.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** bảo vệ OAuth flow và token.
- **OpenID Connect Core:** authorization response, state, nonce và token validation.
- **OWASP Web Security Testing Guide:** kiểm thử session, authentication, authorization và client-side behavior.
- **OWASP ASVS:** yêu cầu kiểm chứng authentication, session, CSRF và security configuration.
- **MDN — Cookies / SameSite:** cookie attributes và browser behavior.
- **Apple Platform Security / passkeys documentation:** passkey và authenticator integration trên Apple platform.
- **Android Credential Manager documentation:** passkey/password credential selection trên Android.

Khi triển khai, đối chiếu phiên bản browser và tài liệu hiện hành. Compatibility data là thông tin hỗ trợ lập kế hoạch, không thay thế kiểm thử trên browser/OS thật. Mọi thay đổi cookie, redirect, passkey hoặc privacy behavior cần được kiểm thử lại theo support matrix của sản phẩm.

**Kết luận:** Cross-browser test cho authentication phải chứng minh cùng một policy bảo mật được giữ vững trên browser, engine, version và thiết bị được hỗ trợ. Ma trận test cần bao phủ cookie/SameSite, OAuth/OIDC redirect, PKCE, WebAuthn/passkey, MFA, storage, privacy controls, logout, accessibility và network failure. Automation giúp phát hiện regression lặp lại; browser/OS thật xác minh các tích hợp authenticator và privacy. Release decision phải dựa trên bằng chứng theo từng browser và không được bỏ qua một security regression chỉ vì các browser khác đã pass.
