# Fallback authentication — Thiết kế phương thức xác thực dự phòng an toàn
 
> **Chương:** Availability  
> **Chủ đề:** Fallback authentication

**Fallback authentication** là cơ chế cho phép người dùng hoặc workload tiếp tục xác thực khi phương thức chính, thiết bị, identity provider hoặc một thành phần phụ thuộc tạm thời không khả dụng. Ví dụ: người dùng mất security key chính nhưng còn key dự phòng; ứng dụng chuyển sang IdP dự phòng khi IdP chính gặp outage; hoặc nhân viên vận hành dùng quy trình break-glass đã được kiểm soát khi hệ thống xác thực thông thường ngừng hoạt động.

Fallback giúp tăng availability, nhưng cũng có thể tạo ra đường vòng yếu hơn phương thức chính. Nếu tài khoản quản trị dùng passkey chống phishing trong điều kiện bình thường nhưng khi gặp lỗi lại cho phép đăng nhập bằng email OTP hoặc câu hỏi bảo mật, attacker có thể chủ động gây gián đoạn để ép hệ thống hạ mức bảo đảm. Đây là **authentication downgrade**. Vì vậy, fallback phải được thiết kế như một phần của security policy và threat model, có mức bảo đảm tương đương hoặc được giới hạn theo rủi ro, thời gian, hành động và người phê duyệt.

Bài học thuộc module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, kết nối credential, password, MFA, passkey, certificate, token, session, SSO, account recovery, risk-based authentication và availability. Người học sẽ biết phân biệt fallback authenticator với account recovery, xây dựng thứ tự ưu tiên phương thức, xử lý outage của IdP và dịch vụ phụ thuộc, giữ ranh giới tin cậy và kiểm thử các tình huống failover mà không mở ra bypass xác thực.

## 1. Kết quả học tập

Sau bài học, người học có thể:

1. Giải thích fallback authentication và phân biệt nó với retry, failover, recovery và break-glass.
2. Xác định các thành phần có thể hỏng trong một authentication flow.
3. Thiết kế phương thức dự phòng có mức bảo đảm phù hợp với phương thức chính và loại tài khoản.
4. Nhận diện downgrade attack và các đường fallback yếu như SMS OTP, email OTP hoặc câu hỏi bảo mật.
5. Xây dựng policy lựa chọn authenticator theo assurance, risk, user population và action.
6. Thiết kế backup passkey/security key, MFA recovery và credential lifecycle an toàn.
7. Xử lý IdP failover, JWKS/introspection outage, certificate rotation và workload identity failure.
8. Định nghĩa fail-open, fail-closed và degraded mode theo tác động của hành động.
9. Bảo vệ session, token, tenant context và authorization khi chuyển sang phương thức dự phòng.
10. Xây dựng runbook, test plan và production checklist cho fallback authentication.

## 2. Fallback authentication là gì?

Fallback authentication là một phương án xác thực thay thế được kích hoạt khi phương thức hoặc thành phần xác thực thông thường không thể hoàn tất flow. Phương án thay thế có thể là một authenticator khác đã được đăng ký, một identity provider dự phòng, một quy trình xác minh có giám sát hoặc một chế độ truy cập giới hạn.

Ví dụ:

- Người dùng không có điện thoại đang dùng security key dự phòng;
- Laptop mất kết nối với platform authenticator nhưng người dùng có roaming security key;
- IdP chính gặp sự cố và tổ chức chuyển sang IdP dự phòng đã được cấu hình, có mapping danh tính và trust anchor rõ ràng;
- Nhân viên trực vận hành dùng tài khoản break-glass độc lập để khôi phục dịch vụ identity;
- Dịch vụ workload không lấy được credential ngắn hạn và chuyển sang quy trình cấp lại qua workload identity control plane.

Fallback phải được định nghĩa trước. Không nên để người dùng hoặc service tự chọn bất kỳ phương thức yếu hơn nào khi phương thức chính thất bại.

### 2.1. Fallback không phải retry

Retry là thử lại cùng một phương thức hoặc request sau lỗi tạm thời, ví dụ gửi lại challenge sau timeout. Fallback chuyển sang phương thức hoặc thành phần thay thế, ví dụ dùng security key thứ hai thay vì platform authenticator.

Retry không được tạo thêm challenge vô hạn, bỏ qua rate limit hoặc làm một transaction được thực thi nhiều lần.

### 2.2. Fallback không phải recovery

Recovery là quy trình khôi phục quyền kiểm soát tài khoản khi người dùng mất hoặc không còn sử dụng được credential đã đăng ký. Recovery có thể cần identity proofing, approval, thời gian chờ, thông báo và thu hồi credential cũ.

Fallback thường sử dụng một authenticator dự phòng đã đăng ký trước đó. Nếu người dùng không còn phương thức dự phòng, hệ thống chuyển sang recovery policy chứ không tự động coi email hoặc SMS là fallback tương đương.

### 2.3. Fallback không phải failover

Failover là chuyển một thành phần hạ tầng sang instance/region/provider khác để duy trì dịch vụ. Fallback authentication là lựa chọn phương thức hoặc trust path thay thế. Một hệ thống có thể failover IdP nhưng vẫn cần xác thực người dùng bằng cùng authenticator và policy.

### 2.4. Fallback không phải break-glass

Break-glass là quyền truy cập khẩn cấp có phạm vi hẹp, dành cho tình huống đặc biệt và có giám sát/approval. Nó không phải phương thức đăng nhập tiện lợi thường ngày. Break-glass cần credential độc lập, lưu trữ an toàn, thời hạn, audit và diễn tập.

## 3. Availability và security là hai mục tiêu phải cân bằng

Authentication là control bảo vệ dữ liệu và chức năng. Khi nó ngừng hoạt động, người dùng có thể không truy cập được dịch vụ. Nhưng cho phép mọi người đi qua một phương thức yếu hơn để khôi phục availability có thể gây account takeover.

Một policy tốt phân loại hành động theo tác động:

| Hành động | Mức kiểm soát fallback gợi ý |
| --- | --- |
| Xem nội dung công khai | Có thể cho phép chế độ không đăng nhập |
| Xem dữ liệu cá nhân thông thường | Cần xác thực hợp lệ; fallback phải giữ policy account |
| Xem/sửa dữ liệu nhạy cảm | Yêu cầu authenticator đủ assurance và session phù hợp |
| Thêm/gỡ authenticator | Reauthentication/step-up và notification |
| Thay recovery channel | Step-up, approval hoặc delay theo risk |
| Cấp quyền admin | Phương thức chống phishing, approval và audit |
| Xuất dữ liệu hàng loạt | Step-up gần thời điểm thao tác và policy riêng |
| Thay đổi khóa/signing key | Quy trình đặc quyền, dual control và kiểm tra ngoài băng |
| Break-glass vận hành | Chỉ tài khoản được chỉ định, scope hẹp, TTL và review sau sự kiện |

### 3.1. Availability không có nghĩa là luôn phải cho đăng nhập

Một số hành động có thể được trì hoãn khi không thể xác minh danh tính đủ mạnh. Ví dụ, nếu cả passkey và phương thức dự phòng của admin đều không dùng được, hệ thống có thể từ chối cấp quyền admin trong thời gian outage và yêu cầu quy trình break-glass có approval.

### 3.2. Đặt mục tiêu dịch vụ riêng

Định nghĩa SLO cho:
- Availability của login endpoint;
- Availability của IdP và MFA provider;
- Thời gian cấp lại authenticator;
- Thời gian xử lý recovery;
- Thời gian phát hiện fallback activation;
- Tỷ lệ login hoàn tất bằng phương thức dự phòng;
- Tỷ lệ fallback bị từ chối do policy hoặc risk.

Không chỉ đo tỷ lệ login thành công; cần đo cả mức bảo đảm và số lần fallback được dùng.

## 4. Threat model cho fallback

Fallback tạo thêm đường đi tới cùng tài khoản hoặc resource. Attacker có thể nhắm vào đường ít được bảo vệ nhất.

### 4.1. Các mục tiêu của attacker

- Chủ động làm gián đoạn phương thức chính để buộc người dùng dùng fallback;
- Tìm endpoint fallback yếu hơn và gọi trực tiếp;
- Lạm dụng email/SMS recovery để chiếm tài khoản;
- Social-engineer helpdesk để thêm authenticator;
- Dùng IdP dự phòng có mapping hoặc policy yếu;
- Replay challenge hoặc token từ một flow fallback;
- Khai thác cache/stale session khi chuyển provider;
- Lạm dụng break-glass credential hoặc quy trình emergency;
- Dùng outage để che giấu hoạt động compromise.

### 4.2. Các trust boundary

- Người dùng và thiết bị;
- Browser/app và authenticator;
- RP/application và IdP;
- Primary provider và backup provider;
- Gateway và backend;
- Control plane và workload;
- Helpdesk/operator và người yêu cầu recovery;
- Kênh notification độc lập;
- Session/token issuer và resource server.

Mỗi boundary cần bằng chứng xác thực, policy, audit và cơ chế thu hồi.

### 4.3. Downgrade attack

Downgrade xảy ra khi hệ thống chấp nhận phương thức hoặc policy có assurance thấp hơn do phương thức mạnh hơn thất bại, bị attacker làm gián đoạn hoặc bị cấu hình sai.

Ví dụ: passkey bị timeout, trang đăng nhập hiện nút “Dùng email để nhận mã” và cho phép mã đó cấp cùng quyền admin. Nếu email account bị chiếm, attacker có thể vượt qua phishing-resistant authentication bằng con đường yếu hơn.

## 5. Phân loại tình huống cần fallback

| Tình huống | Loại lỗi | Phương án phù hợp |
| --- | --- | --- |
| Security key chính bị mất | Mất authenticator | Dùng key dự phòng đã đăng ký; nếu không có thì recovery |
| Platform authenticator không khả dụng | Thiết bị/platform | Roaming security key hoặc authenticator khác đã đăng ký |
| Điện thoại hết pin | Thiết bị không sẵn sàng | Backup key hoặc recovery code theo policy |
| TOTP app không đồng bộ thời gian | Lỗi thiết bị/cấu hình | Đồng bộ thời gian, dùng authenticator dự phòng |
| SMS provider outage | Phụ thuộc viễn thông | Dùng phương thức độc lập đã đăng ký; không tự hạ sang email yếu |
| IdP chính outage | Provider availability | Failover IdP đã tin cậy hoặc chế độ giới hạn |
| JWKS endpoint outage | Key discovery | Dùng key đã cache còn trong policy; không tin key mới chưa xác minh |
| Introspection outage | Token state lookup | Cache có TTL được duyệt hoặc fail closed theo risk |
| Certificate hết hạn | Credential lifecycle | Rotation/cấp lại qua PKI; không bỏ qua certificate validation |
| Workload identity service outage | Machine identity | Cache credential ngắn hạn theo policy hoặc khôi phục control plane |
| Session store outage | Session availability | Failover store; không chấp nhận session không xác minh |
| MFA provider outage | Second-factor service | Authenticator độc lập đã đăng ký hoặc giới hạn action |
| Recovery channel mất | Account recovery | Identity proofing/helpdesk có kiểm soát |
| Admin emergency | Operational emergency | Break-glass riêng và review sau sự kiện |

## 6. Assurance và thứ tự ưu tiên phương thức

Không phải phương thức nào cũng có mức bảo đảm giống nhau. Policy cần phân loại theo khả năng chống phishing, khả năng ràng buộc với thiết bị/kênh, xác minh người dùng, khả năng chống replay, độ độc lập giữa các factor và cách credential được khôi phục.

### 6.1. Ví dụ phân nhóm

| Nhóm | Ví dụ | Ghi chú |
| --- | --- | --- |
| Phishing-resistant public-key | Passkey/WebAuthn, FIDO2 security key | Ràng buộc RP/origin khi triển khai đúng |
| Certificate/channel-bound | mTLS client certificate, smart card | Cần PKI, hostname và key validation đúng |
| OTP-based | TOTP, SMS OTP, email OTP | Có thể bị phishing/relay; không mặc định chống phishing |
| Knowledge-based | Password, PIN từ xa, câu hỏi bảo mật | Có rủi ro phishing, reuse hoặc đoán |
| Recovery artifact | Recovery code, recovery key | Dùng một lần/giới hạn; bảo vệ như credential nhạy cảm |
| Human-assisted recovery | Helpdesk/identity proofing | Cần proofing, approval, audit và chống social engineering |

Không suy ra một mức AAL hoặc assurance chính thức chỉ từ tên phương thức. Mức bảo đảm phụ thuộc toàn bộ quy trình enrollment, authenticator, verifier, session, recovery và policy. Nếu tổ chức sử dụng tiêu chuẩn assurance cụ thể, phải ánh xạ theo đúng yêu cầu tiêu chuẩn và triển khai thực tế.

### 6.2. Không tự động hạ assurance

Nếu action yêu cầu phishing-resistant authentication, fallback cũng phải đáp ứng policy tương ứng hoặc action phải bị hạn chế. Không cho password/TOTP/email OTP thay thế passkey chỉ vì người dùng bấm “không dùng được passkey”.

### 6.3. Độc lập giữa các phương thức

Hai phương thức dự phòng không nên cùng phụ thuộc vào một điểm hỏng duy nhất. Ví dụ, passkey trên điện thoại và TOTP trên cùng điện thoại có thể cùng mất khi thiết bị bị mất. Một security key được cất tách biệt có thể giảm phụ thuộc chung.

## 7. Thiết kế fallback cho passkey và security key

Passkey/WebAuthn có khả năng chống phishing nhờ RP ID/origin binding. Fallback cần giữ đặc tính này nếu policy yêu cầu.

### 7.1. Nhiều passkey đã đăng ký

Người dùng có thể đăng ký:
- Passkey trên thiết bị cá nhân;
- Passkey trên thiết bị thứ hai;
- Security key vật lý dự phòng;
- Passkey đồng bộ qua hệ sinh thái được tổ chức chấp nhận.

Mỗi credential cần credential ID, public key, trạng thái, thời điểm tạo, last-used metadata phù hợp và nhãn thiết bị do người dùng nhận biết. Không lưu private key của passkey tại RP.

### 7.2. Key dự phòng

Với account đặc quyền, khuyến nghị có key dự phòng được lưu tách biệt. Key dự phòng cần:
- Đăng ký trước khi xảy ra sự cố;
- Được kiểm tra định kỳ;
- Có inventory/owner;
- Không dùng chung giữa nhiều người;
- Có quy trình thu hồi khi mất;
- Có notification khi được sử dụng lần đầu sau thời gian dài.

### 7.3. Synced passkey

Synced passkey có thể giúp người dùng tiếp tục đăng nhập trên thiết bị khác, nhưng mức bảo đảm phụ thuộc tài khoản đồng bộ, cơ chế bảo vệ khóa và recovery của nền tảng. Nếu tài khoản nền tảng bị chiếm, attacker có thể có đường tới passkey đã đồng bộ. Cần đưa account sync provider vào threat model.

### 7.4. Không fallback sang OTP mà không xét policy

Nếu security policy yêu cầu phishing resistance, TOTP hoặc SMS không phải fallback tương đương. Có thể dùng recovery có kiểm soát để cấp lại passkey sau identity proofing, nhưng không nên cấp cùng quyền ngay chỉ bằng OTP yếu.

## 8. Thiết kế fallback cho MFA

MFA thường có nhiều factor nhưng khả năng độc lập và chống phishing khác nhau.

### 8.1. Backup factor đã đăng ký

Ví dụ:
- Security key thứ hai;
- Passkey khác;
- TOTP authenticator dự phòng;
- Recovery code;
- Hardware token theo policy.

Chọn factor dự phòng theo risk của account. Với admin, không nên coi email hoặc SMS là phương án mặc định chỉ vì thuận tiện.

### 8.2. Recovery code

Recovery code nên:
- Có entropy đủ cao;
- Chỉ hiển thị một lần khi tạo;
- Lưu dưới dạng verifier/hash phía server;
- Có thể dùng một lần;
- Có trạng thái consumed/revoked;
- Được thay mới khi nghi lộ;
- Không gửi trong email hoặc log;
- Được người dùng cất an toàn ngoài thiết bị chính.

Nếu hệ thống tạo nhiều code, mỗi code phải có trạng thái tiêu thụ riêng. Không chấp nhận reuse và không để response tiết lộ số code còn lại trước khi xác minh phù hợp.

### 8.3. TOTP fallback

TOTP có thể hữu ích khi platform authenticator không sẵn sàng, nhưng mã có thể bị phishing/relay theo thời gian thực. Nếu được phép, chỉ dùng cho action có risk phù hợp; yêu cầu step-up hoặc giới hạn session khi policy cần. Không quảng bá TOTP là phishing-resistant.

### 8.4. SMS/email OTP

SMS và email phụ thuộc vào SIM, mailbox, carrier, forwarding và khả năng bị social engineering. Chỉ dùng khi threat model chấp nhận, có rate limit và kiểm soát recovery. Với admin hoặc dữ liệu nhạy cảm, nên có phương án mạnh hơn.

## 9. Fallback cho password và credential knowledge-based

Password có thể là phương thức chính hoặc phương án khẩn cấp, nhưng password không tự tạo ra phishing resistance.

### 9.1. Password fallback

Nếu ứng dụng hỗ trợ password fallback cho tài khoản passkey:
- Phải có policy rõ ràng;
- Password cần hash bằng KDF phù hợp;
- Rate limit và breached-password controls;
- MFA/step-up theo risk;
- Không tiết lộ account state;
- Có audit khi password fallback được sử dụng;
- Không cho password fallback cấp action yêu cầu phishing-resistant authentication.

### 9.2. Không dùng câu hỏi bảo mật

Câu hỏi như tên thú cưng, trường học hoặc ngày sinh thường có thể đoán, tìm trên mạng hoặc thu thập qua social engineering. Không dùng chúng như fallback đủ mạnh để khôi phục account.

### 9.3. Không gửi password tạm qua email

Nếu cần đặt lại password, dùng recovery transaction một lần, TTL ngắn, purpose binding và thông báo qua kênh đã xác minh. Không gửi password tạm hoặc credential dùng chung.

## 10. Fallback khi Identity Provider gặp sự cố

IdP outage có thể khiến nhiều ứng dụng không xác thực được người dùng. Có thể dùng IdP dự phòng, nhưng failover identity không đơn giản là đổi URL.

### 10.1. Các yêu cầu trước khi failover

- Backup IdP đã được cấu hình và kiểm thử;
- Issuer và signing key được trust theo cấu hình riêng;
- Subject mapping ổn định, không chỉ dựa vào email;
- Audience/client registration phù hợp;
- Authentication context và MFA policy tương đương;
- Redirect URI, state, nonce và callback được bảo vệ;
- Logout, session revocation và account disable được đồng bộ;
- Tenant/organization mapping không bị thay đổi ngoài ý muốn;
- Audit cho biết IdP nào đã xác thực user.

### 10.2. Không tự động tin IdP bất kỳ

Không nhận token từ issuer mới chỉ vì IdP chính không phản hồi. Trust anchor phải được đăng ký trước, key phải được xác minh và mapping danh tính phải có chủ đích.

### 10.3. Subject mapping

Trong OIDC, subject thường chỉ duy nhất trong phạm vi issuer. Cặp issuer + subject là định danh quan trọng; không tự động liên kết hai account chỉ vì email giống nhau. Email có thể đổi, tái sử dụng hoặc chưa được xác minh.

### 10.4. Failover có thể làm mất session

Session do IdP chính tạo không tự động hợp lệ ở IdP dự phòng. Có thể cần đăng nhập lại. Không bỏ qua xác minh chỉ để giữ session liên tục. Nếu có federation/session bridging, phải có trust contract và kiểm thử riêng.

## 11. JWKS, introspection và token validation khi outage

### 11.1. JWKS cache

Resource server có thể cache public key đã lấy từ JWKS endpoint để xác minh JWT khi endpoint tạm thời không khả dụng. Chỉ dùng key đã được lấy từ issuer tin cậy và còn trong policy cache. Không tin một key mới chỉ vì JWT header chứa kid hoặc jku.

### 11.2. Key rotation

Khi issuer rotate signing key, verifier cần hỗ trợ overlap và refresh JWKS theo policy. Nếu endpoint outage xảy ra trong lúc key mới chưa được biết, token ký bằng key mới có thể không xác minh được. Không tắt signature validation để phục vụ availability.

### 11.3. Introspection outage

Với opaque token, introspection có thể là nguồn kiểm tra trạng thái active. Cache kết quả có TTL giới hạn. Khi outage:
- Action ít rủi ro có thể dùng kết quả cache còn hiệu lực nếu policy cho phép;
- Action nhạy cảm cần fail closed hoặc yêu cầu xác thực lại;
- Không coi mọi opaque token là active chỉ vì endpoint lỗi;
- Ghi rõ degraded mode và thời gian áp dụng.

### 11.4. Token expiry

Không kéo dài exp tùy tiện khi IdP outage. Nếu cần session continuity, thiết kế refresh token rotation, grace period và sender constraint trước; không chấp nhận token hết hạn chỉ vì không thể gọi issuer.

## 12. Fallback cho certificate và workload identity

Certificate-based authentication và workload identity cần cơ chế dự phòng để tránh gián đoạn service mà không bỏ qua xác minh peer.

### 12.1. Certificate rotation

Khi certificate sắp hết hạn:
- Cấp certificate mới trước khi certificate cũ hết hạn;
- Cho phép overlap ngắn có kiểm soát;
- Kiểm tra SAN/EKU/identity mapping;
- Xác minh chain và revocation;
- Gỡ certificate cũ sau khi rollout hoàn tất.

Nếu CA không khả dụng, không bỏ qua chain validation hoặc chấp nhận certificate self-signed không được trust. Dùng quy trình PKI dự phòng đã phê duyệt.

### 12.2. Workload identity

Workload có thể nhận credential ngắn hạn từ platform identity service. Khi control plane outage, có thể dùng credential đã cấp và còn hạn theo policy. Không lưu một shared static secret vô thời hạn làm fallback cho mọi workload.

### 12.3. Service-to-service fallback

Nếu service A không thể lấy token cho service B, không gửi user token có audience khác hoặc dùng admin service account chung. Chỉ sử dụng alternate credential có audience, scope, actor và expiry đúng với operation.

## 13. Fail-open, fail-closed và degraded mode

Ba chiến lược có trade-off khác nhau.

- **Fail-closed:** từ chối xác thực/operation khi không thể xác minh điều kiện cần thiết.
- **Fail-open:** cho phép tiếp tục dù một control không thể xác minh.
- **Degraded mode:** chỉ cho phép một tập chức năng hạn chế với điều kiện và thời hạn được định nghĩa.

| Tình huống | Hướng xử lý thường phù hợp |
| --- | --- |
| Không xác minh được password hoặc passkey | Fail closed |
| IdP outage, nội dung công khai | Có thể tiếp tục không cần auth |
| IdP outage, đọc dữ liệu nhạy cảm | Fail closed hoặc dùng trust path dự phòng đã kiểm thử |
| JWKS outage với key đã cache hợp lệ | Có thể xác minh theo cache policy |
| Introspection outage cho action đặc quyền | Fail closed |
| MFA provider outage | Dùng authenticator độc lập đã đăng ký hoặc giới hạn action |
| Certificate validation lỗi | Fail closed |
| Risk engine outage | Policy dự phòng được phê duyệt; action rủi ro cao fail closed |
| Audit pipeline outage | Có thể tạm ngừng action đặc quyền nếu không bảo đảm audit |
| Session store outage | Failover store; không bỏ qua session validation |

### 13.1. Phân loại theo action

Không nên áp dụng một fail mode cho toàn bộ ứng dụng. Xem xét:
- Độ nhạy cảm dữ liệu;
- Mức quyền của principal;
- Khả năng đảo ngược action;
- Phạm vi tác động;
- Mức assurance đã có;
- Khả năng audit;
- Thời gian outage;
- Sự tồn tại của alternate trust path.

### 13.2. Degraded mode có giới hạn

Một degraded mode cần định nghĩa:
- Nhóm user được phép;
- Endpoint/resource được phép;
- Hành động bị cấm;
- Assurance tối thiểu;
- Thời gian tối đa;
- Owner và approver;
- Monitoring riêng;
- Điều kiện tự tắt và rollback.

Không để degraded mode trở thành cấu hình vĩnh viễn.

## 14. Session và token trong fallback flow

Chuyển phương thức xác thực không được làm mất ràng buộc giữa principal, session, assurance và action.

### 14.1. Authentication context

Session nên giữ thông tin cần thiết như:
- Principal/subject;
- Issuer và authentication method;
- Authentication time;
- Assurance/context theo policy;
- Tenant context đã xác minh;
- Session version;
- Fallback indicator;
- Risk decision và expiry.

Không đưa secret hoặc raw authenticator response vào session metadata.

### 14.2. Session assurance không tự tăng

Nếu người dùng đăng nhập bằng phương thức fallback có assurance thấp hơn, session không được mang nhãn assurance cao của phương thức chính. Action cần assurance cao phải yêu cầu step-up bằng phương thức phù hợp.

### 14.3. Session rotation

Khi chuyển từ recovery/fallback sang session mới:
- Rotate session identifier;
- Thu hồi hoặc đánh dấu session cũ theo policy;
- Kiểm tra token family;
- Giữ actor và audit context;
- Xác minh tenant membership và authorization hiện tại.

### 14.4. Token audience và issuer

Token từ IdP dự phòng cần issuer/audience được backend tin cậy theo cấu hình. Không bỏ qua issuer validation hoặc chấp nhận token từ hai issuer chỉ bằng một danh sách rộng không có mapping subject rõ ràng.

## 15. Tenant context và multi-tenant fallback

Trong SaaS, một người dùng có thể thuộc nhiều tenant. Fallback không được tự chọn tenant khác hoặc khôi phục quyền membership đã bị thu hồi.

### 15.1. Kiểm tra lại membership

Khi fallback login thành công:
- Resolve tenant từ nguồn được tin cậy;
- Kiểm tra tenant active;
- Kiểm tra membership hiện tại;
- Kiểm tra role/action/resource;
- Không tin tenant claim cũ chỉ vì token đã ký;
- Áp dụng authorization version/freshness policy.

### 15.2. Tenant switching

Khi user đổi tenant trong degraded mode, cần kiểm tra membership cho tenant mới và đảm bảo session/context không bị lẫn giữa các tab hoặc request song song.

### 15.3. Support access

Support không được dùng fallback để bỏ qua tenant isolation. Quyền hỗ trợ phải có case, purpose, approval, tenant scope, TTL và audit.

## 16. Account recovery và fallback

Khi không còn authenticator hợp lệ, người dùng cần recovery. Đây là điểm có nguy cơ bị social engineering cao.

### 16.1. Recovery assurance

Recovery có thể bao gồm:
- Backup authenticator đã đăng ký;
- Recovery code;
- Identity proofing theo mức rủi ro;
- Helpdesk với dual control;
- Cooldown hoặc delayed activation;
- Notification tới kênh đã xác minh;
- Revoke credential và session bị mất.

Recovery method phải được đánh giá theo mức assurance thực tế. Không dùng một kênh email yếu để khôi phục quyền admin nếu login policy yêu cầu phishing-resistant authenticator.

### 16.2. Không xác minh chỉ bằng thông tin công khai

Tên, ngày sinh, chức danh, số điện thoại hoặc thông tin có trên mạng không đủ để chứng minh quyền kiểm soát account. Helpdesk cần quy trình xác minh độc lập và chống social engineering.

### 16.3. Recovery hold và notification

Với thay đổi rủi ro cao, có thể áp dụng thời gian chờ trước khi credential mới được dùng cho action nhạy cảm. Gửi thông báo tới kênh đã xác minh và cung cấp đường báo cáo nếu người dùng không khởi tạo yêu cầu.

### 16.4. Sau recovery

- Thu hồi credential đã mất hoặc nghi compromise;
- Thu hồi session/token cũ theo policy;
- Đăng ký authenticator mới;
- Kiểm tra email/phone/IdP linking;
- Kiểm tra role và membership;
- Theo dõi hành vi bất thường;
- Ghi audit đầy đủ.

## 17. Break-glass authentication

Break-glass là đường truy cập khẩn cấp khi hệ thống identity bình thường không thể vận hành. Nó có blast radius lớn và phải được quản lý như một control đặc biệt.

### 17.1. Nguyên tắc

- Tài khoản riêng, không dùng tài khoản cá nhân thông thường;
- Chỉ định người được phép sử dụng;
- Credential độc lập với hệ thống đang gặp sự cố;
- Phương thức bảo vệ mạnh và cất giữ an toàn;
- Scope tối thiểu, thời hạn ngắn;
- Dual control/approval nếu phù hợp;
- Alert ngay khi sử dụng;
- Audit độc lập và review sau sự kiện;
- Diễn tập định kỳ.

### 17.2. Không dùng chung credential

Không chia sẻ một password admin qua chat hoặc tài liệu nội bộ. Credential break-glass cần được cấp cho người/thiết bị được xác định, kiểm soát checkout, rotation và attribution.

### 17.3. Quy trình sau khi dùng

Sau sự kiện:
1. Xác minh ai đã sử dụng và lý do;
2. Review mọi action và resource đã truy cập;
3. Thu hồi hoặc rotate credential;
4. Kết thúc session và token;
5. Khôi phục cấu hình authentication bình thường;
6. Kiểm tra thay đổi trái phép;
7. Ghi post-incident review và cải tiến runbook.

## 18. Policy matrix cho fallback

Một policy matrix giúp tránh quyết định tùy tiện trong lúc outage.

| Principal/action | Primary method | Fallback được phép | Không được phép |
| --- | --- | --- | --- |
| User thông thường, nội dung ít nhạy cảm | Passkey hoặc password + MFA theo policy | Authenticator thứ hai đã đăng ký | Bỏ qua mọi xác minh |
| User truy cập dữ liệu cá nhân | Passkey/MFA | Backup authenticator đạt policy | Email đơn lẻ nếu policy yêu cầu MFA |
| Admin portal | Phishing-resistant MFA | Security key dự phòng hoặc break-glass có approval | SMS/email OTP thay thế cùng quyền |
| Thêm/gỡ credential | Reauthentication + step-up | Backup phishing-resistant authenticator | Recovery factor mới tự xác minh chính nó |
| Workload service | Short-lived workload identity | Credential dự phòng đã cấp và còn hạn | Shared static admin secret |
| Certificate client | mTLS certificate | Certificate thứ hai từ PKI tin cậy | Bỏ qua chain/hostname validation |
| IdP outage | Primary federation | Backup IdP đã trust/mapping trước | Chấp nhận issuer tùy ý |
| Helpdesk recovery | Identity proofing + approval | Dual-control procedure | Thông tin cá nhân công khai đơn lẻ |
| Break-glass | Normal auth unavailable | Emergency credential được quản lý | Bypass không log hoặc không hết hạn |

Matrix là ví dụ. Tổ chức phải xác định policy theo threat model, dữ liệu, tiêu chuẩn assurance và khả năng vận hành.

## 19. Pseudocode lựa chọn fallback an toàn

~~~text
authenticate_with_fallback(request):
    principal = resolve_principal(request)
    require principal_is_eligible(principal)

    policy = load_authentication_policy(
        principal = principal,
        action = request.action,
        tenant = resolve_verified_tenant(request)
    )

    primary_result = try_primary_authenticator(request, policy)

    if primary_result.success:
        return create_session(
            principal = principal,
            assurance = primary_result.assurance,
            method = primary_result.method,
            fallback_used = false
        )

    if not primary_result.is_temporary_unavailability:
        return deny_with_generic_response()

    candidates = registered_fallback_authenticators(principal)

    for candidate in policy.allowed_fallbacks:
        if candidate not in candidates:
            continue
        if not candidate_meets_required_assurance(candidate, policy):
            continue
        if candidate_is_revoked_or_expired(candidate):
            continue

        result = verify_fallback(candidate, request)
        if result.success:
            recheck_account_membership_and_risk(principal, request)
            return create_session(
                principal = principal,
                assurance = result.assurance,
                method = result.method,
                fallback_used = true
            )

    return start_controlled_recovery_or_deny()
~~~

Pseudocode chỉ minh họa policy flow. Thực tế cần transaction binding, challenge freshness, replay protection, rate limit, atomic consumption, audit, race handling và kiểm tra assurance theo chuẩn của tổ chức. Không cho candidate do client tự khai quyết định policy.

## 20. Pseudocode IdP failover có kiểm soát

~~~text
authenticate_via_federation(request):
    primary = configured_primary_idp()
    result = call_idp(primary, request)

    if result.success:
        return validate_federated_result(
            result,
            expected_issuer = primary.issuer,
            expected_audience = configured_audience
        )

    if not outage_policy_allows_failover(result.error):
        return deny_or_degraded_mode()

    backup = configured_backup_idp()
    require backup.is_pre_registered
    require backup.issuer in trusted_issuer_allowlist

    backup_result = call_idp(backup, request)
    require backup_result.success

    claims = validate_federated_result(
        backup_result,
        expected_issuer = backup.issuer,
        expected_audience = configured_audience
    )

    principal = map_subject_by_issuer_and_subject(claims.issuer, claims.sub)
    require principal exists
    require principal_is_active(principal)
    require required_authentication_context(claims, policy)

    audit_idp_failover(
        principal = principal,
        primary_issuer = primary.issuer,
        backup_issuer = backup.issuer
    )

    return issue_limited_session_if_policy_allows(principal, claims)
~~~

Không tự động liên kết principal theo email giống nhau. Token phải được xác minh chữ ký, issuer, audience, thời hạn, nonce/state theo flow và authentication context. Backup IdP cần được kiểm thử trước khi outage xảy ra.

## 21. Ví dụ kiến trúc: dịch vụ học tập nhiều tenant

Một nền tảng học tập có portal cho học viên, giảng viên và quản trị viên. Passkey là phương thức ưu tiên; một số tài khoản có security key dự phòng. Identity provider chính dùng OIDC. Dịch vụ backend xác minh access token và tenant membership.

### 21.1. Người dùng thông thường

1. Người dùng thử passkey trên thiết bị chính.
2. Nếu authenticator không khả dụng do lỗi thiết bị, UI hiển thị security key hoặc passkey khác đã đăng ký.
3. Backend xác minh assertion cho đúng RP ID/origin và challenge.
4. Session ghi nhận method, auth_time và fallback_used.
5. Nếu không còn authenticator hợp lệ, bắt đầu recovery policy.

### 21.2. Giảng viên truy cập bảng điểm

Nếu IdP chính outage:
- Có thể failover tới IdP dự phòng đã được trust và mapping;
- Backend xác minh token từ issuer dự phòng;
- Membership và ownership của lớp vẫn được kiểm tra;
- Nếu không thể xác minh quyền hiện tại, từ chối sửa/xuất bảng điểm;
- Có thể cho phép xem tài liệu công khai hoặc nội dung không nhạy cảm.

### 21.3. Quản trị viên

Admin cần phishing-resistant authentication. Nếu passkey chính không hoạt động, dùng security key thứ hai. Nếu cả hai không sẵn sàng, break-glass cần approval và alert; email OTP không được tự động cấp quyền admin tương đương.

## 22. Kiểm thử fallback và failover

Kiểm thử trong staging với account, IdP, authenticator và provider sandbox. Không cố ý gây outage trên production hoặc thử bypass tài khoản thật.

| Nhóm | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| Primary success | Authenticator chính hoạt động | Đăng nhập theo policy bình thường |
| Backup authenticator | Key dự phòng đã đăng ký | Được chấp nhận nếu đạt assurance |
| Unknown fallback | Client gửi loại factor chưa đăng ký | Từ chối |
| Revoked backup | Backup credential đã revoke | Từ chối |
| Expired recovery code | Code đã hết hạn/đã dùng | Từ chối |
| Recovery code replay | Dùng code lần hai | Từ chối và ghi event |
| Passkey outage | Platform authenticator không khả dụng | Chỉ hiển thị fallback đã đăng ký |
| Downgrade | Admin passkey fail, thử SMS OTP | Từ chối nếu policy yêu cầu phishing resistance |
| TOTP relay risk | TOTP dùng trong flow yêu cầu chống phishing | Không coi là tương đương passkey |
| MFA provider outage | Provider timeout | Dùng factor độc lập đã đăng ký hoặc degraded policy |
| IdP primary outage | Primary không phản hồi | Failover chỉ tới backup issuer đã trust |
| Unknown issuer | Token từ issuer chưa đăng ký | Từ chối |
| Subject collision | Email giống nhau ở hai IdP | Không tự động liên kết account |
| Wrong audience | Token dự phòng dành cho resource khác | Từ chối |
| Invalid signature | Token không xác minh được | Từ chối |
| JWKS outage | Key đã cache còn hợp lệ | Chỉ xác minh bằng key đã trust theo cache policy |
| Unknown signing key | kid mới nhưng JWKS không lấy được | Từ chối; không tắt signature validation |
| Introspection outage | Action đặc quyền cần trạng thái active | Fail closed hoặc policy đã duyệt |
| Expired access token | IdP outage kéo dài | Không tự kéo dài exp |
| Certificate expiry | mTLS certificate hết hạn | Rotation/cấp lại; không bỏ qua validation |
| Workload outage | Credential ngắn hạn không cấp mới được | Dùng credential còn hạn theo policy hoặc dừng workload |
| Session store outage | Không đọc được session | Failover store; không chấp nhận session không xác minh |
| Tenant switching | Fallback session đổi tenant | Resolve lại membership và resource scope |
| Recovery | Không còn authenticator | Chuyển controlled recovery, không bypass |
| Break-glass | Emergency credential được dùng | Alert, audit, scope/TTL và post-use rotation |
| Notification | Fallback/recovery được kích hoạt | Thông báo qua kênh đã xác minh |
| Concurrent requests | Hai flow fallback cùng consume recovery code | Chỉ một transaction thành công |
| Rollback | Primary provider phục hồi | Trở về policy bình thường, đóng degraded mode |
| Audit | Fallback thành công/thất bại | Ghi method, reason, issuer, actor và policy version |
| Privacy | Alert/log được tạo | Không chứa password, OTP, token hoặc private key |

### 22.1. Bất biến bảo mật

- Fallback chỉ dùng authenticator đã đăng ký hoặc trust path đã phê duyệt;
- Assurance của session phản ánh phương thức thực tế đã sử dụng;
- Action yêu cầu phishing resistance không được hạ xuống OTP/password yếu;
- Fallback không bỏ qua account state, membership, tenant và resource authorization;
- Challenge/recovery artifact có purpose, TTL, replay protection và one-time consumption;
- IdP failover chỉ dùng issuer, key và subject mapping đã được cấu hình;
- Không chấp nhận token sai issuer/audience hoặc bỏ qua signature validation;
- Degraded mode có scope, owner, TTL, monitoring và rollback;
- Break-glass được audit và review sau khi sử dụng.

## 23. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Fallback yếu hơn nhưng giữ nguyên quyền | Authentication downgrade | Assurance-aware policy và giới hạn action |
| Hiển thị email OTP sau khi passkey lỗi | Attacker ép dùng đường yếu | Chỉ cho fallback đã đăng ký và đạt policy |
| Recovery bị coi là fallback thường ngày | Recovery trở thành bypass | Tách recovery, proofing và approval |
| IdP dự phòng chưa kiểm thử | Sai mapping hoặc token trust | Pre-register issuer, audience, keys và test |
| Liên kết account theo email | Account takeover/collision | Mapping theo issuer + subject và proofing |
| Chấp nhận token khi JWKS outage mà không verify | Forged token | Chỉ dùng key cache đã trust, fail closed nếu cần |
| Kéo dài token khi outage | Session tồn tại quá lâu | TTL, refresh policy và bounded degraded mode |
| Shared static secret cho workload | Blast radius và khó attribution | Workload identity và short-lived credential |
| Bỏ qua certificate validation | Workload impersonation | PKI validation và rotation |
| Không rotate session sau recovery | Session attacker vẫn sống | Revoke/rotate session và token family |
| Fallback không ghi audit | Không biết ai đã dùng đường khẩn cấp | Audit method, actor, reason và policy |
| Break-glass không hết hạn | Emergency account thành backdoor | TTL, checkout, rotation và review |
| Degraded mode không tự tắt | Hạ assurance kéo dài | Expiry, owner và rollback |
| Dùng IP làm identity | Nhận nhầm caller | Workload identity và mTLS |
| Không kiểm tra tenant sau failover | Cross-tenant access | Membership/resource check hiện tại |

## 24. Checklist production

1. **Inventory:** Đã liệt kê primary authenticator, backup authenticator, IdP và dependency?
2. **Policy:** Có quy định fallback theo principal, action, tenant và assurance?
3. **Registration:** Backup authenticator được đăng ký và xác minh trước khi sự cố?
4. **Independence:** Backup có tránh cùng một điểm hỏng với primary?
5. **Phishing resistance:** Action yêu cầu chống phishing có fallback tương đương?
6. **Recovery:** Recovery được tách khỏi fallback và có proofing/approval?
7. **Recovery artifact:** Code có entropy, hash, TTL, one-time use và rotation?
8. **IdP failover:** Issuer, keys, audience, subject mapping và auth context đã được kiểm thử?
9. **Token:** JWKS/introspection outage có cache policy và fail mode rõ?
10. **Certificate:** PKI rotation, trust anchor, expiry và revocation được bảo vệ?
11. **Workload:** Service identity không fallback sang shared secret rộng quyền?
12. **Session:** Fallback indicator, assurance, issuer, auth_time và session rotation được quản lý?
13. **Authorization:** Tenant membership, resource ownership và role được kiểm tra lại?
14. **Degraded mode:** Có scope, endpoint, TTL, owner, approval, monitoring và rollback?
15. **Break-glass:** Account riêng, credential độc lập, dual control, alert và post-use review?
16. **Abuse protection:** Rate limit, replay protection và chống recovery spam hoạt động?
17. **Privacy:** Notification/log không chứa token, OTP, recovery code hoặc secret?
18. **Observability:** Có metric cho fallback success/failure, downgrade attempt, provider outage và recovery?
19. **Testing:** Đã test primary failure, backup, unknown factor, replay, wrong issuer/audience và rollback?
20. **Governance:** Có owner, runbook, review date và diễn tập định kỳ?

## 25. Bài tập tình huống

Một tổ chức dùng passkey làm phương thức đăng nhập chính cho quản trị viên. Khi passkey không hoạt động, trang login tự động hiển thị lựa chọn nhận OTP qua email. Email của quản trị viên được bảo vệ bằng password và SMS. IdP chính có outage nhưng ứng dụng chấp nhận token từ một IdP thứ hai dựa trên email claim mà không có subject mapping. Backend giữ session cũ sau khi recovery hoàn tất. Nhân viên vận hành có một tài khoản break-glass dùng chung không có TTL.

**Yêu cầu:**

1. Xác định ít nhất **tám rủi ro** trong fallback, IdP failover, recovery và session lifecycle.
2. Thiết kế policy fallback riêng cho user thường, giảng viên và admin.
3. Xác định backup authenticator độc lập cho admin và cách enrollment trước sự cố.
4. Thiết kế IdP failover với issuer, audience, key và subject mapping rõ ràng.
5. Đề xuất recovery flow có proofing, approval, notification và revoke credential cũ.
6. Xác định session/token nào phải thu hồi sau recovery.
7. Thiết kế break-glass account có scope, owner, TTL, dual control và audit.
8. Viết test cho downgrade, unknown issuer, subject collision, recovery replay và degraded-mode expiry.

**Gợi ý đối chiếu:** Email OTP không tương đương passkey; account không được liên kết chỉ theo email; IdP dự phòng phải được trust trước; recovery phải re-establish assurance; session cũ cần xử lý; break-glass phải có owner, expiry, rotation và review.

## 26. Ghi nhớ

- **Fallback authentication** duy trì khả năng xác thực khi phương thức hoặc dependency chính không khả dụng, nhưng phải tuân thủ security policy.
- Fallback, retry, failover, recovery và break-glass là các khái niệm khác nhau.
- Phương thức dự phòng phải được đăng ký hoặc trust trước, có assurance phù hợp và được kiểm thử.
- Không hạ từ phishing-resistant authentication xuống SMS/email/TOTP yếu hơn cho action có cùng yêu cầu bảo đảm.
- IdP failover cần issuer, signing key, audience, subject mapping và authentication context được cấu hình trước.
- JWKS/introspection outage không phải lý do để bỏ qua signature, issuer, audience hoặc expiry validation.
- Session phải ghi nhận phương thức thực tế và không tự nâng assurance; recovery cần xử lý session/token cũ.
- Tenant membership, resource ownership và authorization phải được kiểm tra lại sau fallback.
- Degraded mode cần scope, TTL, owner, approval, monitoring và rollback.
- Break-glass là quy trình khẩn cấp riêng, có credential độc lập, audit, rotation và post-use review.

Fallback authentication an toàn khi **dịch vụ có thể tiếp tục trong giới hạn được xác định, nhưng mọi đường thay thế vẫn chứng minh đúng principal, giữ đúng assurance cho action và duy trì khả năng audit/thu hồi**. Nếu không thể xác minh đủ mức cần thiết, từ chối có kiểm soát là một quyết định availability có chủ đích để bảo vệ tài khoản và dữ liệu.
