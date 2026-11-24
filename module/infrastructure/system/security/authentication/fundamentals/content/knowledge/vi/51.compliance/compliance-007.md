# Privacy requirement

## 1. Privacy requirement là gì?

**Privacy requirement (yêu cầu quyền riêng tư)** là những điều kiện một hệ thống phải đáp ứng khi thu thập, sử dụng, lưu trữ, chia sẻ, bảo vệ và xóa dữ liệu liên quan đến con người. Trong authentication, dữ liệu không chỉ là username và password. Hệ thống còn xử lý email, số điện thoại, địa chỉ IP, thiết bị, vị trí gần đúng, lịch sử đăng nhập, MFA factor, passkey metadata, federation claims, session, recovery event và tín hiệu phát hiện gian lận.

Authentication cần biết đủ thông tin để xác minh principal và bảo vệ tài khoản, nhưng thu thập quá nhiều có thể tạo rủi ro riêng tư, tăng hậu quả khi database bị lộ và làm dữ liệu được sử dụng ngoài mục đích ban đầu. Vì vậy, privacy requirement phải được xem xét ngay từ thiết kế luồng xác thực, không đợi đến lúc hoàn thiện giao diện hoặc viết chính sách quyền riêng tư.

Ví dụ: một ứng dụng cần xác minh người dùng bằng passkey. Relying Party thường cần public key credential, credential ID, thông tin liên kết account và kết quả user verification. Ứng dụng không cần nhận hoặc lưu dấu vân tay/khuôn mặt đã dùng để mở khóa authenticator. Nếu ứng dụng còn thu thập vị trí chính xác, danh bạ và lịch sử duyệt web mà không có mục đích xác thực cụ thể, phạm vi dữ liệu đã vượt quá nhu cầu của luồng.

Trong module SECURITY_AUTHENTICATION_FUNDAMENTALS, Privacy requirement kết nối credential, password, MFA, passkey, certificate, federation, token, session và account recovery. Người thiết kế cần vừa bảo vệ bí mật xác thực vừa giới hạn dữ liệu cá nhân theo mục đích, phạm vi và thời gian cần thiết.

## 2. Privacy khác gì security?

Privacy và security liên quan chặt chẽ nhưng trả lời các câu hỏi khác nhau:

| Góc nhìn | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Security** | Dữ liệu và hệ thống có được bảo vệ khỏi truy cập, sửa đổi hoặc phá hoại trái phép không? | Password verifier được hash và chỉ service xác thực được đọc. |
| **Privacy** | Có nên thu thập dữ liệu này, dùng cho mục đích gì, chia sẻ với ai và giữ bao lâu? | Không lưu vị trí chính xác nếu chỉ cần quốc gia để phát hiện đăng nhập bất thường. |
| **Data governance** | Ai sở hữu dữ liệu, ai phê duyệt mục đích, retention và quyền truy cập? | Privacy owner phê duyệt schema telemetry và thời hạn lưu. |
| **Compliance** | Yêu cầu pháp lý, hợp đồng và chính sách nào áp dụng? | Đánh giá nghĩa vụ bảo vệ dữ liệu theo khu vực và loại dịch vụ. |

Một hệ thống có thể mã hóa dữ liệu rất tốt nhưng vẫn xâm phạm privacy nếu thu thập quá mức, giữ vô thời hạn hoặc dùng dữ liệu đăng nhập cho quảng cáo mà người dùng không được thông báo phù hợp. Ngược lại, xóa mọi log để giảm dữ liệu cũng có thể làm mất khả năng phát hiện account takeover và điều tra sự cố.

Thiết kế tốt cần cân bằng mục đích xác thực, an toàn, khả năng kiểm toán và quyền riêng tư; từng loại dữ liệu phải có lý do, owner, quyền truy cập và vòng đời rõ ràng.

## 3. Nguyên tắc privacy-by-design

Các nguyên tắc thường dùng khi thiết kế hệ thống authentication:

1. **Purpose limitation:** xác định mục đích cụ thể trước khi thu thập hoặc sử dụng dữ liệu.
2. **Data minimization:** chỉ thu thập trường dữ liệu cần thiết cho mục đích đã xác định.
3. **Transparency:** giải thích dễ hiểu dữ liệu nào được xử lý, vì sao và chia sẻ với ai.
4. **Accuracy:** dữ liệu account, contact và trạng thái factor phải có cách cập nhật, sửa lỗi.
5. **Storage limitation:** đặt thời hạn lưu và quy trình xóa hoặc ẩn danh khi hết mục đích.
6. **Integrity and confidentiality:** giới hạn truy cập, bảo vệ khi truyền và khi lưu.
7. **Accountability:** lưu bằng chứng về quyết định, quyền truy cập và việc thực hiện policy.
8. **Privacy by default:** mặc định thu thập ít, chia sẻ hẹp và không bật theo dõi không cần thiết.

Privacy-by-design không có nghĩa là bỏ mọi dữ liệu phục vụ bảo mật. Nó yêu cầu chứng minh vì sao một trường cần thiết, chọn độ chính xác tối thiểu đáp ứng mục đích và đặt giới hạn sử dụng.

## 4. Lập inventory dữ liệu trong vòng đời authentication

Trước khi thiết kế schema hoặc tích hợp nhà cung cấp, hãy lập inventory dữ liệu:

| Nhóm dữ liệu | Ví dụ | Mức nhạy cảm và lưu ý |
| --- | --- | --- |
| Account identifiers | Username, email, phone, internal subject ID | Có thể nhận diện cá nhân; cần giới hạn hiển thị và tra cứu. |
| Credential secrets | Password, TOTP seed, recovery code, API secret | Bí mật xác thực; không log, không lưu plaintext. |
| Password verifier | Argon2id/bcrypt verifier và salt | Vẫn nhạy cảm vì có thể hỗ trợ offline guessing khi bị lộ. |
| Passkey/WebAuthn | Credential ID, public key, RP/account mapping, authenticator metadata | Không lưu biometric template; metadata vẫn có thể nhận diện thiết bị hoặc người dùng. |
| Certificate identity | Subject/SAN, serial, issuer, public key reference | Có thể liên kết cá nhân, thiết bị hoặc tổ chức. |
| MFA state | Factor type, enrollment time, last-used time, challenge status | Có thể tiết lộ thói quen và mức bảo vệ tài khoản. |
| Federation claims | Issuer, subject, email, name, groups, roles, tenant | Chỉ nhận claim cần thiết; tránh sao chép toàn bộ directory profile. |
| Token/session | Token reference, session ID, expiry, assurance, client | Có thể cho phép truy cập; phải bảo vệ như credential. |
| Security telemetry | IP, device signal, user agent, login time, risk result | Có thể tạo hồ sơ hành vi và vị trí. |
| Recovery data | Recovery email/phone, recovery code status, proofing evidence | Rất nhạy cảm; recovery có thể thay đổi quyền kiểm soát account. |
| Audit record | Actor, action, target, outcome, timestamp | Có thể chứa dữ liệu cá nhân và thông tin vận hành nhạy cảm. |

Inventory cần ghi nguồn thu thập, mục đích, hệ thống lưu trữ, bên nhận, quyền truy cập, retention, cơ chế xóa và owner. Một trường dữ liệu có thể xuất hiện ở nhiều hệ thống; cần theo dõi cả bản sao trong cache, queue, log, backup và data warehouse.

## 5. Xác định mục đích và căn cứ xử lý

Mỗi hoạt động xử lý dữ liệu cần gắn với mục đích cụ thể, ví dụ:

- Tạo và duy trì account.
- Xác minh credential khi đăng nhập.
- Gửi MFA challenge hoặc thông báo bảo mật.
- Ngăn brute force, credential stuffing và account takeover.
- Phát hành token hoặc duy trì session.
- Liên kết danh tính qua federation.
- Khôi phục account và xác minh thay đổi factor.
- Điều tra sự cố và đáp ứng yêu cầu kiểm toán.

Không dùng cụm từ chung chung như “cải thiện dịch vụ” để biện minh cho mọi loại telemetry. Nếu muốn dùng login history cho phân tích sản phẩm, quảng cáo hoặc profiling ngoài mục đích bảo mật, cần đánh giá riêng mục đích, căn cứ xử lý, thông báo và quyền lựa chọn phù hợp.

Consent không phải lúc nào cũng là căn cứ phù hợp cho xử lý dữ liệu authentication. Một số hoạt động có thể dựa trên hợp đồng, nghĩa vụ pháp lý hoặc lợi ích hợp pháp tùy bối cảnh và luật áp dụng. Không mặc định một checkbox đăng nhập có thể hợp thức hóa mọi hoạt động theo dõi.

Yêu cầu cụ thể khác nhau theo quốc gia, loại dữ liệu, vai trò controller/processor và dịch vụ. Cần đưa privacy/legal owner vào review khi xác định căn cứ, thông báo, chuyển dữ liệu xuyên biên giới hoặc quyền của chủ thể dữ liệu.

## 6. Data minimization trong account và credential

Account schema nên lưu những trường cần cho định danh, xác thực, liên lạc và nghiệp vụ đã xác định. Không thu thập ngày sinh, địa chỉ nhà, giới tính hoặc giấy tờ định danh nếu luồng authentication không cần chúng.

Một số thực hành:

- Dùng internal subject ID ngẫu nhiên thay cho email làm khóa liên kết nội bộ lâu dài.
- Giữ email/phone ở vùng dữ liệu có kiểm soát và chỉ hiển thị một phần khi cần.
- Không dùng username/email làm secret; chúng thường có thể đoán hoặc công khai.
- Tách credential verifier khỏi profile và business data.
- Không sao chép toàn bộ thuộc tính từ IdP nếu chỉ cần subject và một vài claim.
- Không lưu password gốc; lưu verifier theo password hashing scheme phù hợp.
- Không lưu TOTP seed hoặc recovery code ở dạng plaintext.
- Xóa dữ liệu enrollment tạm sau khi hoàn tất hoặc hết hạn.

Data minimization cũng áp dụng cho request. Nếu API chỉ cần subject ID và assurance level, đừng gửi toàn bộ profile, group list và lịch sử đăng nhập.

## 7. Bảo vệ password và dữ liệu xác thực bí mật

Password là dữ liệu người dùng cung cấp và cần được xử lý như bí mật:

- Chỉ nhận qua kênh TLS được cấu hình đúng.
- Không ghi password vào log, trace, analytics, crash report hoặc support ticket.
- Không gửi password sang service không cần xác minh credential.
- Lưu password verifier bằng password hashing algorithm chuyên dụng với salt riêng và cost được benchmark.
- Giới hạn quyền đọc verifier và tách khỏi dữ liệu profile.
- Không trả verifier hoặc chi tiết kiểm tra password qua API.
- Xóa password khỏi memory/request context sớm nhất có thể theo khả năng runtime.

Password verifier không phải dữ liệu vô hại. Khi database bị lộ, attacker có thể thử password offline. Vì vậy cần kiểm soát quyền truy cập, mã hóa storage phù hợp, backup, export và quy trình ứng phó khi compromise.

Không dùng password làm định danh, analytics key hoặc dữ liệu để so khớp giữa dịch vụ. Không gửi password qua email hoặc thông báo.

## 8. Privacy trong MFA và recovery factor

MFA bổ sung dữ liệu về thiết bị, số điện thoại, authenticator và hành vi đăng nhập. Mỗi factor cần có mục đích và giới hạn:

| Factor | Dữ liệu có thể phát sinh | Yêu cầu privacy |
| --- | --- | --- |
| TOTP | Secret seed, enrollment time, last-used time | Không log seed/OTP; chỉ hiển thị seed trong enrollment có kiểm soát. |
| SMS OTP | Phone number, provider, delivery status | Chỉ lưu số cần thiết; giới hạn bên nhận và retention metadata. |
| Email OTP | Email, delivery status | Không dùng email xác thực cho marketing nếu chưa có mục đích/căn cứ riêng. |
| Push MFA | Device token, push status, approval/deny time | Không thu thập thêm danh bạ/vị trí nếu không cần; giải thích dữ liệu thiết bị. |
| Recovery code | Verifier, trạng thái used/revoked | Lưu verifier an toàn; không lưu mã hiển thị plaintext. |
| Security key | Credential ID, public key, authenticator metadata | Chỉ lưu metadata cần để xác minh và quản lý credential. |

Người dùng cần biết factor nào đang đăng ký và có cách xem, thay thế hoặc thu hồi factor theo quy trình xác minh an toàn. Thông báo bảo mật nên tránh tiết lộ dữ liệu quá mức trong subject/email preview hoặc trên thiết bị dùng chung.

## 9. Passkey, WebAuthn và biometric privacy

Với WebAuthn/passkey, relying party thường lưu credential ID, public key, user handle và metadata cần cho xác minh. Relying party không nhận private key của authenticator.

Khi authenticator dùng dấu vân tay hoặc khuôn mặt để mở khóa passkey, việc so khớp biometric thường diễn ra cục bộ trên authenticator/device. Relying party nhận assertion và cờ user presence/user verification theo protocol, không nhận ảnh khuôn mặt hay mẫu vân tay từ ceremony chuẩn.

Yêu cầu:

- Không yêu cầu hoặc thu thập biometric template nếu ứng dụng không có chức năng riêng cần xử lý dữ liệu đó.
- Không diễn giải cờ user verification thành danh tính sinh trắc học cụ thể; nó chỉ cho biết authenticator đã đáp ứng yêu cầu xác minh người dùng theo cơ chế của nó.
- Lưu credential metadata tối thiểu và giới hạn truy cập.
- Giải thích nếu hệ thống thu thập thông tin về loại authenticator, backup eligibility/state hoặc device model.
- Có quy trình xóa credential khi người dùng gỡ passkey hoặc account bị đóng.
- Không dùng attestation để fingerprint người dùng/thiết bị vượt quá mục đích đã thông báo.

Passkey đồng bộ giữa thiết bị có thể tạo metadata từ hệ sinh thái nhà cung cấp. Cần hiểu rõ bên nào quản lý đồng bộ, dữ liệu nào được chia sẻ và tổ chức có yêu cầu authenticator gắn thiết bị hay không.

## 10. Certificate và workload identity

Certificate có thể chứa tên cá nhân, email, tổ chức, hostname, URI hoặc thông tin thiết bị. Khi dùng certificate-based authentication:

- Chỉ đưa vào certificate các subject/SAN field cần cho xác minh.
- Tránh đặt thông tin cá nhân không cần thiết vào certificate công khai hoặc dễ truy vấn.
- Kiểm soát nơi lưu private key và ai có thể export.
- Đặt thời hạn, rotation, revocation và owner rõ ràng.
- Không log private key hoặc dữ liệu challenge bí mật.
- Với workload identity, ưu tiên định danh service/namespace/workload thay vì gắn dữ liệu cá nhân của operator vào certificate.

Certificate transparency, public CA log hoặc directory có thể làm một số metadata trở nên công khai. Cần đánh giá nội dung certificate trước khi phát hành.

## 11. Federation và claim minimization

Federation giúp một hệ thống dựa vào IdP khác để xác thực người dùng, nhưng có thể chuyển nhiều dữ liệu profile hơn mức cần thiết.

Ví dụ, một ứng dụng nội bộ chỉ cần biết người dùng là nhân viên đang hoạt động và thuộc tenant nào. Nó có thể không cần ngày sinh, số điện thoại cá nhân, địa chỉ, danh bạ hoặc toàn bộ group membership.

Thực hành:

- Chọn claim tối thiểu cho từng relying party.
- Dùng pairwise/pseudonymous subject khi phù hợp để hạn chế liên kết hoạt động giữa nhiều client.
- Không dùng email làm stable identifier nếu issuer cung cấp subject ổn định phù hợp.
- Kiểm tra purpose và quyền truy cập của từng client/recipient.
- Không phát hành group/role claim rộng nếu resource chỉ cần một scope cụ thể.
- Đặt thời hạn token phù hợp và tránh nhúng dữ liệu profile nhạy cảm vào JWT.
- Có quy trình account unlinking và xóa mapping khi quan hệ federation kết thúc.

Claim trong JWT thường có thể đọc được bởi người sở hữu token nếu token chỉ được ký mà không mã hóa. Không đưa password, số định danh nhạy cảm, dữ liệu sức khỏe hoặc thông tin riêng tư không cần thiết vào access token.

## 12. Token và session là dữ liệu nhạy cảm

Access token, refresh token, ID Token và session cookie có thể cho phép truy cập hoặc tiết lộ danh tính. Cần:

- Không đặt token trong URL hoặc query string.
- Không ghi token/cookie vào log, analytics, crash report hoặc ticket.
- Không gửi token tới bên nhận không cần thiết.
- Giới hạn audience, scope và thời hạn.
- Dùng secure storage phù hợp với client type.
- Xoay và thu hồi session/token theo account lifecycle.
- Tránh chứa claim cá nhân vượt quá mục đích resource.
- Kiểm soát quyền đọc token reference và session metadata.

Opaque token có thể giảm việc lộ claim trực tiếp cho client, nhưng authorization server/resource server vẫn xử lý dữ liệu liên kết ở backend. Tokenization không tự động làm dữ liệu trở nên vô danh.

## 13. IP, thiết bị, vị trí và behavioral telemetry

Security telemetry có thể giúp phát hiện credential stuffing, impossible travel hoặc thiết bị lạ. Tuy nhiên, IP, user agent, device fingerprint và vị trí gần đúng có thể là dữ liệu cá nhân hoặc tạo hồ sơ hành vi.

Trước khi thu thập, xác định:

- Tín hiệu nào thực sự cần cho risk decision?
- Có thể dùng quốc gia hoặc network category thay cho tọa độ chính xác không?
- Device identifier có ổn định lâu dài và có thể liên kết hoạt động qua dịch vụ không?
- Có thể dùng pseudonymous identifier hoặc rotating identifier không?
- Dữ liệu được dùng để bảo mật, analytics hay quảng cáo?
- Ai có quyền truy cập và thời gian lưu là bao lâu?
- Người dùng được thông báo thế nào và có quyền lựa chọn nào?

Không thu thập vị trí chính xác, danh bạ, sensor hoặc browsing history chỉ vì SDK hỗ trợ. Không dùng fingerprint như định danh chắc chắn; tín hiệu có thể sai, thay đổi hoặc bị giả mạo.

## 14. Privacy trong error message và account enumeration

Thông báo lỗi có thể tiết lộ account tồn tại, factor đã đăng ký, trạng thái khóa hoặc recovery channel. Cần:

- Dùng response chung ở nơi caller chưa được xác thực.
- Không tiết lộ email/phone đầy đủ; nếu cần hiển thị, mask phù hợp.
- Tránh response timing, status hoặc redirect tạo oracle cho account enumeration.
- Không hiển thị số recovery code còn lại hoặc chi tiết factor cho người chưa xác thực.
- Không đưa account identifier nhạy cảm vào URL.
- Ghi lý do chi tiết trong audit nội bộ với quyền truy cập hạn chế.

Generic message không thay thế kiểm soát timing, rate limit và abuse monitoring. Privacy review phải đánh giá toàn bộ observable response, không chỉ nội dung câu thông báo.

## 15. Logging, monitoring và audit với data minimization

Audit cần đủ để phát hiện và điều tra sự cố nhưng không được chứa bí mật xác thực:

| Có thể cần ghi | Không ghi |
| --- | --- |
| Event ID, timestamp, outcome, service và request reference | Password hoặc password plaintext |
| Pseudonymous principal/account reference | TOTP seed hoặc OTP |
| Authentication method và assurance result | Recovery code plaintext |
| Issuer, client, audience và token ID reference | Access/refresh token value |
| Session reference, create/revoke và expiry | Session cookie hoặc raw session secret |
| Device/risk category theo policy | Biometric template không cần thiết |
| Actor, action, target resource và approval reference | Private key, client secret hoặc API key |

Tránh ghi raw request body của login, recovery hoặc token endpoint. Redaction cần thực hiện trước khi dữ liệu đi vào log pipeline, vì nhiều collector và bản sao có thể giữ payload gốc.

Nếu cần tìm kiếm theo account, dùng pseudonymous identifier hoặc HMAC key được quản lý riêng. Không dùng hash không khóa của email/phone có entropy thấp nếu attacker có thể dictionary-attack để khôi phục định danh.

## 16. Retention và deletion

Mỗi loại dữ liệu cần thời hạn lưu phù hợp với mục đích:

- Login telemetry có thể chỉ cần giữ chi tiết trong thời gian ngắn, sau đó tổng hợp hoặc xóa.
- Audit đặc quyền có thể cần retention dài hơn theo nghĩa vụ kiểm toán hoặc điều tra.
- MFA challenge và OTP phải hết hạn nhanh; metadata không cần thiết cần được dọn.
- Recovery token/code phải bị vô hiệu hóa sau khi dùng hoặc hết hạn.
- Session và refresh token cần được thu hồi khi account đóng hoặc có sự kiện bảo mật phù hợp.
- Federation mapping cần được xóa hoặc unlink khi quan hệ kết thúc theo policy.
- Backup và archive cần có lịch hết hạn và quy trình xử lý deletion phù hợp.

Không đặt một retention period duy nhất cho mọi bảng chỉ vì tiện vận hành. Thời hạn phải có mục đích, owner, trigger bắt đầu tính và cách xử lý khi hết hạn.

Xóa account không nhất thiết có nghĩa xóa ngay mọi audit record hoặc dữ liệu phải giữ theo nghĩa vụ pháp lý. Cần phân biệt dữ liệu account hoạt động, dữ liệu backup, audit cần giữ và dữ liệu đã được ẩn danh; chỉ giữ phần có căn cứ và giới hạn quyền truy cập.

## 17. Access control và separation of duties cho dữ liệu identity

Không phải mọi nhân viên vận hành đều cần đọc mọi trường trong identity store:

- Support có thể cần trạng thái account và factor type nhưng không cần đọc verifier hoặc seed.
- Security analyst có thể cần event và pseudonymous principal nhưng không cần profile đầy đủ.
- Identity operator có thể quản lý enrollment nhưng không được đọc password.
- Database administrator có quyền hạ tầng nhưng không nên có quyền ứng dụng mặc định để giải mã mọi secret.
- Privacy/legal owner cần báo cáo xử lý dữ liệu, không cần truy cập token/session đang hoạt động.

Áp dụng least privilege, role separation, approval cho truy cập khẩn cấp và audit truy cập dữ liệu. Truy cập production data để debug cần ticket, thời hạn, mục đích và cơ chế redaction.

## 18. Data sharing và third-party processor

Authentication có thể sử dụng IdP, SMS gateway, email provider, fraud/risk vendor, analytics SDK, customer support và cloud platform. Mỗi bên nhận dữ liệu là một trust boundary.

Review cần xác định:

- Dữ liệu nào được gửi cho nhà cung cấp và vì sao?
- Có thể gửi identifier giả danh hoặc dữ liệu tối thiểu hơn không?
- Nhà cung cấp có dùng dữ liệu cho mục đích riêng không?
- Dữ liệu được lưu ở đâu, retention bao lâu và có subprocessors nào?
- Có mã hóa, access control, incident notification và deletion mechanism không?
- Có thỏa thuận xử lý dữ liệu và cơ chế chuyển dữ liệu xuyên biên giới phù hợp không?
- Khi chấm dứt dịch vụ, dữ liệu và credential liên quan được xóa/thu hồi ra sao?

Không gửi password, OTP, refresh token hoặc session cookie cho analytics/fraud vendor. Nếu SMS/email provider cần destination để gửi mã, chỉ gửi thông tin cần thiết cho delivery và không đưa nội dung nhạy cảm vào log provider.

## 19. Privacy trong account linking và recovery

Account linking có thể liên kết nhiều identity provider hoặc login method với cùng một người. Nếu liên kết sai, dữ liệu của hai người có thể bị gộp hoặc attacker chiếm account.

Yêu cầu:

- Chỉ liên kết sau khi xác minh cả account hiện tại và identity mới theo assurance phù hợp.
- Không tự động link chỉ vì email giống nhau, trừ khi có quy tắc xác minh issuer/verified email rõ ràng và được phê duyệt.
- Thông báo khi thêm hoặc gỡ login method.
- Ghi audit actor, identity provider, subject mapping và thời điểm.
- Cho phép xem và gỡ liên kết theo quy trình an toàn.
- Xóa mapping khi mục đích liên kết kết thúc, trừ phần cần giữ có căn cứ.

Recovery có thể yêu cầu dữ liệu bổ sung như giấy tờ hoặc bằng chứng sở hữu kênh liên lạc. Chỉ thu thập khi phương pháp recovery yêu cầu, giới hạn người được xem, che/redact phần không cần thiết và xóa theo retention đã định.

Không yêu cầu người dùng gửi password, OTP hoặc recovery code cho nhân viên hỗ trợ. Support workflow cần hướng dẫn xác minh mà không làm lộ secret.

## 20. Quyền của chủ thể dữ liệu và transparency

Người dùng cần được thông báo phù hợp về:

- Loại dữ liệu account và authentication được thu thập.
- Mục đích xác thực, bảo mật, fraud prevention và audit.
- Bên nhận hoặc nhóm nhà cung cấp có thể xử lý dữ liệu.
- Thời hạn lưu hoặc tiêu chí xác định thời hạn.
- Cách xem, sửa, cập nhật, tải xuống hoặc yêu cầu xóa dữ liệu khi áp dụng.
- Cách quản lý passkey, MFA factor, recovery method và session.
- Kênh liên hệ về quyền riêng tư.

Quyền cụ thể và ngoại lệ phụ thuộc luật áp dụng. Hệ thống nên có quy trình nhận diện yêu cầu, xác minh người gửi, định tuyến tới owner và ghi nhận thời hạn xử lý. Không gửi dữ liệu account cho người yêu cầu chỉ dựa vào email chưa được xác minh.

Thông báo privacy cần dễ hiểu và gắn với thời điểm phù hợp. Không giấu mục đích xử lý quan trọng trong điều khoản dài hoặc dùng một consent chung cho nhiều mục đích không liên quan.

## 21. Privacy impact assessment và threat modeling

Khi authentication xử lý dữ liệu nhạy cảm, quy mô lớn hoặc có profiling/biometric/identity proofing, cần đánh giá tác động privacy theo quy trình tổ chức và luật áp dụng. Tùy trường hợp, có thể cần DPIA hoặc review tương đương.

Các câu hỏi:

1. Dữ liệu nào có thể nhận diện trực tiếp hoặc gián tiếp một người?
2. Mục đích có cụ thể và cần thiết không?
3. Có trường nào có thể bỏ, giảm độ chính xác hoặc thay bằng reference không?
4. Dữ liệu có thể bị liên kết giữa nhiều dịch vụ/tenant không?
5. Ai có thể truy cập và việc truy cập được giám sát ra sao?
6. Hậu quả nếu dữ liệu bị lộ, sửa hoặc sử dụng sai mục đích là gì?
7. Có thể pseudonymize, encrypt, aggregate hoặc xử lý cục bộ không?
8. Retention, deletion và backup có thực hiện được không?
9. Nhà cung cấp/subprocessor và luồng xuyên biên giới đã được đánh giá chưa?
10. Người dùng có được thông báo và thực hiện quyền phù hợp không?

Privacy threat model nên xét cả attacker bên ngoài, insider, nhà cung cấp, log analyst, support operator và việc sử dụng dữ liệu ngoài mục đích.

## 22. Ví dụ: thiết kế privacy cho đăng nhập passkey

Một dịch vụ web muốn hỗ trợ passkey cho người dùng:

1. Khi đăng ký, server yêu cầu user đã xác minh account và tạo WebAuthn challenge ngẫu nhiên.
2. Browser/authenticator thực hiện ceremony; biometric nếu có được xử lý cục bộ bởi authenticator theo cơ chế của thiết bị.
3. Server xác minh challenge, origin, RP ID, ceremony type và attestation theo policy.
4. Server lưu credential ID, public key, user handle và metadata cần cho xác minh.
5. Server không nhận hoặc lưu private key, dấu vân tay hay ảnh khuôn mặt từ ceremony.
6. Khi đăng nhập, server tạo challenge mới, xác minh assertion và cập nhật metadata tối thiểu như thời điểm dùng gần nhất nếu có mục đích rõ.
7. Audit chỉ ghi principal reference, credential reference, outcome và timestamp; không ghi assertion secret hoặc raw payload không cần thiết.
8. Người dùng có thể xem, thêm hoặc gỡ passkey sau re-authentication; thao tác được audit.
9. Khi account đóng, credential mapping và metadata được xóa theo retention policy; audit cần giữ được xử lý theo quy định riêng.

**Dữ liệu được lưu:** credential ID, public key, account reference, trạng thái và metadata cần thiết.

**Dữ liệu không cần lưu:** private key của authenticator, biometric template và raw assertion sau khi xử lý nếu không có mục đích được phê duyệt.

## 23. Ví dụ schema inventory và retention

Một bảng inventory rút gọn:

| Data element | Purpose | Access | Retention trigger |
| --- | --- | --- | --- |
| Internal subject ID | Liên kết principal giữa dịch vụ | Identity service, API theo scope | Theo vòng đời account |
| Password verifier | Xác minh password | Authentication service hạn chế | Xóa/replace khi credential bị reset hoặc account đóng theo policy |
| Passkey public key | Xác minh assertion | WebAuthn verifier | Khi credential bị gỡ hoặc account đóng |
| MFA destination | Gửi challenge đã đăng ký | MFA service hạn chế | Khi factor bị thay hoặc account đóng |
| Login event reference | Phát hiện abuse và điều tra | Security operations theo role | Theo retention của telemetry |
| Session record | Duy trì phiên | Session service | Khi revoke hoặc hết hạn |
| Recovery proofing artifact | Xác minh yêu cầu recovery | Nhóm được phê duyệt | Sau thời hạn phục vụ recovery/audit |

Các thời hạn cụ thể cần được tổ chức xác định theo mục đích và nghĩa vụ áp dụng; bảng này không quy định một số ngày dùng chung cho mọi hệ thống.

## 24. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Thu thập quá nhiều profile field từ IdP | Tăng dữ liệu cá nhân và hậu quả khi breach. | Claim minimization theo từng relying party. |
| Lưu biometric template dù passkey không cần | Tạo kho dữ liệu cực nhạy cảm không cần thiết. | Xử lý biometric cục bộ trên authenticator khi protocol hỗ trợ. |
| Ghi password, OTP hoặc token vào log | Log pipeline trở thành nơi lộ credential. | Redaction trước ingestion và kiểm thử logging. |
| Dùng email làm primary key toàn hệ thống | Dễ liên kết hoạt động và khó xử lý thay đổi email. | Internal subject ID và mapping có kiểm soát. |
| Dùng IP/device fingerprint vô thời hạn | Tạo hồ sơ hành vi vượt mục đích. | Minimize, pseudonymize, giới hạn retention và access. |
| Dùng login history cho marketing mà không review | Mở rộng purpose ngoài thông báo ban đầu. | Đánh giá mục đích/căn cứ và thông báo riêng. |
| Giữ recovery evidence mãi mãi | Tăng rủi ro lộ giấy tờ và dữ liệu cá nhân. | Retention theo purpose, xóa/redact sau thời hạn. |
| Cho support đọc secret hoặc seed | Insider hoặc support tool có thể chiếm account. | Least privilege và chỉ hiển thị trạng thái cần thiết. |
| JWT chứa quá nhiều claim cá nhân | Người giữ token có thể đọc dữ liệu và token khó thu hồi. | Claim tối thiểu, audience hẹp và TTL phù hợp. |
| Xóa account nhưng giữ bản sao không kiểm soát | Dữ liệu còn trong cache, queue, backup hoặc warehouse. | Deletion workflow xuyên hệ thống và kiểm tra bản sao. |
| Chia sẻ dữ liệu MFA với vendor không cần thiết | Tăng bên nhận và rủi ro chuyển dữ liệu. | Data flow review và giới hạn payload. |
| Coi consent là căn cứ cho mọi xử lý | Căn cứ xử lý có thể không phù hợp hoặc không tự nguyện. | Privacy/legal review theo mục đích và luật áp dụng. |

## 25. Checklist privacy requirement cho authentication

Trước khi đưa một luồng authentication vào production, hãy kiểm tra:

1. Đã lập inventory dữ liệu từ registration tới recovery và deletion chưa?
2. Mỗi trường có mục đích, owner, nguồn, recipient và retention rõ ràng không?
3. Có thu thập ít nhất dữ liệu cần thiết cho authentication và risk decision không?
4. Internal subject ID có được tách khỏi email/phone và profile data không?
5. Password, verifier, TOTP seed, recovery code, token và session secret có được bảo vệ đúng mức không?
6. Passkey flow có tránh thu thập biometric template và private key không?
7. MFA, certificate và device metadata có giới hạn theo mục đích không?
8. Federation chỉ phát hành claim cần thiết cho từng client/resource không?
9. Token có tránh chứa PII không cần thiết và có audience/scope/TTL phù hợp không?
10. IP, location, fingerprint và behavioral telemetry có được đánh giá purpose, precision và retention không?
11. Error response, timing và recovery flow có tránh account/factor enumeration không?
12. Log/trace/analytics có redaction trước ingestion và không chứa credential không?
13. Access control, separation of duties và audit truy cập identity data đã rõ chưa?
14. Vendor/subprocessor, data sharing và transfer đã được đánh giá chưa?
15. Retention/deletion có bao gồm cache, queue, backup, export và warehouse không?
16. Account linking và recovery có xác minh đúng chủ thể và giới hạn evidence không?
17. Privacy notice và quy trình thực hiện quyền của người dùng có phù hợp không?
18. Có privacy impact assessment khi quy mô/loại dữ liệu/risk yêu cầu không?
19. Có quy trình xử lý breach và thông báo theo nghĩa vụ áp dụng không?
20. Có kiểm thử schema, log redaction, deletion, access control và claim minimization không?

**Kết luận:** Privacy requirement trong authentication bao phủ toàn bộ dữ liệu được tạo và sử dụng để xác minh, duy trì và khôi phục danh tính. Hãy xác định mục đích trước khi thu thập, giảm claim và telemetry, bảo vệ credential/token như bí mật, xử lý biometric cục bộ khi có thể, giới hạn quyền truy cập và đặt retention có thể thực thi xuyên hệ thống. Một thiết kế chỉ an toàn khi vừa ngăn truy cập trái phép vừa tránh thu thập, chia sẻ hoặc giữ dữ liệu cá nhân vượt nhu cầu xác thực và nghĩa vụ hợp lệ.
