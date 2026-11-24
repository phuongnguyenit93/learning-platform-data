# Strong authentication requirement — Xác định và đáp ứng yêu cầu xác thực mạnh

Một hệ thống ngân hàng cho phép người dùng xem số dư bằng password, nhưng yêu cầu xác thực bổ sung trước khi chuyển tiền tới người thụ hưởng mới. Một cổng quản trị yêu cầu passkey hoặc security key cho tài khoản đặc quyền, trong khi một ứng dụng nội bộ chỉ dùng password và mã SMS cho mọi thao tác. Cả ba hệ thống đều có đăng nhập, nhưng mức bảo đảm mà chúng cần đạt khác nhau. Nếu tổ chức chỉ viết yêu cầu chung chung như “phải có MFA” mà không xác định threat model, loại authenticator, phạm vi áp dụng, recovery và cách kiểm chứng, việc triển khai có thể vẫn yếu trước phishing, replay hoặc chiếm quyền phiên.

**Strong authentication requirement (yêu cầu xác thực mạnh)** là tập hợp yêu cầu kỹ thuật và vận hành xác định mức độ tin cậy cần có khi một người dùng hoặc workload chứng minh danh tính. Yêu cầu này phải nói rõ chủ thể nào cần xác thực, trước hành động nào, bằng những yếu tố hoặc authenticator nào, chống được kiểu tấn công nào, khi nào cần xác thực lại và bằng chứng nào chứng minh hệ thống đã đáp ứng. Xác thực mạnh không chỉ là tăng độ phức tạp của password hay bật một tùy chọn MFA; nó là quyết định bảo đảm dựa trên giá trị tài sản, tác động nếu bị chiếm quyền, ranh giới tin cậy và khả năng phục hồi.

Bài học thuộc chương **Compliance** của học phần **SECURITY_AUTHENTICATION_FUNDAMENTALS**. Nội dung kết nối yêu cầu xác thực mạnh với credential, password, MFA, passkey, certificate, token, session, identity federation và account recovery. Người học sẽ biết mô hình hóa ranh giới tin cậy, phòng chống phishing, replay và lạm dụng đăng nhập; đồng thời chuyển yêu cầu chính sách hoặc quy định thành kiến trúc, kiểm soát và bằng chứng kiểm toán có thể kiểm chứng.

## 1. Kết quả học tập

Sau bài này, người học có thể:

- Giải thích xác thực mạnh và phân biệt nó với password policy hoặc MFA checkbox.
- Chuyển yêu cầu pháp lý, tiêu chuẩn và chính sách nội bộ thành control có thể triển khai và kiểm thử.
- Xác định mức bảo đảm phù hợp theo loại tài khoản, tài sản, hành động và threat model.
- Phân biệt yếu tố xác thực, authenticator, credential và bằng chứng xác thực.
- Đánh giá khả năng chống phishing, replay, credential theft và MFA fatigue của từng phương thức.
- Chọn passkey, security key, certificate, TOTP hoặc phương thức dự phòng theo rủi ro.
- Thiết kế step-up authentication cho hành động nhạy cảm và phiên có độ tin cậy thay đổi.
- Bao phủ enrollment, replacement, recovery, revocation và lifecycle của authenticator.
- Xác định yêu cầu cho privileged account, workload identity và service-to-service authentication.
- Thiết kế audit evidence, monitoring và test case chứng minh tuân thủ.
- Nhận diện các ngoại lệ, fallback và giới hạn cần được phê duyệt, theo dõi và hết hạn.

## 2. Xác thực mạnh có nghĩa là gì?

Xác thực trả lời câu hỏi: “Chủ thể đang tương tác có chứng minh được quyền kiểm soát credential gắn với danh tính đó không?” Xác thực mạnh yêu cầu bằng chứng đủ đáng tin cho mức rủi ro của giao dịch. Một cơ chế mạnh cần xem xét:

- **Độ mạnh của authenticator:** credential khó đoán, khó sao chép hoặc khó giả mạo đến mức nào.
- **Số yếu tố và tính độc lập:** các yếu tố có thực sự khác nhau hay cùng phụ thuộc một thiết bị/bí mật.
- **Khả năng chống phishing:** attacker có thể chuyển tiếp challenge/response tới dịch vụ giả mạo hay không.
- **Chống replay:** proof đã dùng có thể bị phát lại không.
- **Binding:** credential có gắn với đúng origin, audience, transaction, device hoặc workload không.
- **Lifecycle:** enrollment, recovery, reset, rotation và revoke có giữ được mức bảo đảm không.
- **Session assurance:** sau login, session/token có giữ đúng mức tin cậy và giới hạn thời gian không.
- **Khả năng vận hành:** hệ thống có giám sát, xử lý ngoại lệ và kiểm chứng việc thực thi không.

Một password dài và duy nhất có thể giảm nguy cơ đoán hoặc credential stuffing, nhưng password nhập vào website giả mạo vẫn có thể bị lấy cắp. MFA dựa trên OTP có thể thêm yếu tố thứ hai nhưng mã OTP vẫn có thể bị phishing hoặc relay trong thời gian hiệu lực. Passkey/WebAuthn có origin binding và proof bằng khóa công khai, do đó chống phishing tốt hơn trong các flow được triển khai đúng.

### 2.1. Xác thực mạnh không đồng nghĩa với xác thực nhiều lần

Yêu cầu người dùng nhập password ở mọi trang không tự động tăng bảo đảm. Nó có thể tạo trải nghiệm kém, làm người dùng chọn password yếu hoặc dễ bị phishing hơn. Cần xác định thời điểm xác thực, freshness của authentication, hành động yêu cầu step-up và cách bảo vệ session sau đó.

### 2.2. Authentication khác authorization

Một người dùng có thể được xác thực mạnh nhưng vẫn không có quyền xem dữ liệu của tenant khác hoặc thực hiện thao tác quản trị. Authentication xác minh principal; authorization quyết định principal được làm gì trên resource nào. Compliance phải kiểm tra cả hai khi quy định yêu cầu kiểm soát truy cập.

### 2.3. Strong authentication là thuộc tính của cả flow

Một passkey mạnh không cứu được hệ thống nếu attacker có thể gọi recovery bằng email yếu, thêm authenticator mới qua session cũ, hoặc đổi số điện thoại mà không step-up. Hãy đánh giá từ lúc enrollment đến khi credential bị thu hồi, không chỉ kiểm tra màn hình login.

## 3. Từ yêu cầu tuân thủ tới control có thể kiểm chứng

Tổ chức thường nhận yêu cầu từ nhiều nguồn:

- Luật, quy định ngành hoặc nghĩa vụ hợp đồng.
- Tiêu chuẩn và framework bảo mật.
- Chính sách IAM, access control và privileged access nội bộ.
- Yêu cầu của khách hàng, đối tác hoặc nhà cung cấp.
- Threat model, risk assessment và kết quả kiểm toán.

Không nên chuyển nguyên văn một câu trong chính sách thành checkbox cấu hình. Hãy phân rã yêu cầu thành các câu hỏi có thể trả lời:

1. Chủ thể nào nằm trong phạm vi: người dùng cuối, nhân viên, quản trị viên, đối tác hay workload?
2. Hành động nào cần mức xác thực này: đăng nhập, truy cập dữ liệu, thanh toán, đổi credential hay quản trị?
3. Mức bảo đảm cần đạt là gì và dựa trên rủi ro nào?
4. Phương thức nào được phép, phương thức nào bị cấm hoặc chỉ dùng dự phòng?
5. Có yêu cầu chống phishing, chống replay, xác minh thiết bị hoặc transaction binding không?
6. Khi nào cần re-authentication hoặc step-up?
7. Recovery, support override và ngoại lệ có đáp ứng cùng mức bảo đảm không?
8. Bằng chứng nào chứng minh control được bật, hoạt động và được giám sát?

### 3.1. Traceability matrix

Một traceability matrix liên kết nguồn yêu cầu với thiết kế, triển khai và bằng chứng:

| Nguồn yêu cầu | Yêu cầu diễn giải | Control triển khai | Bằng chứng kiểm chứng |
| --- | --- | --- | --- |
| Chính sách nội bộ | Admin phải dùng xác thực chống phishing | Passkey hoặc security key bắt buộc cho admin | Policy export, enrollment inventory, login event, negative test |
| Quy định giao dịch | Giao dịch rủi ro cao cần xác thực phù hợp | Step-up và transaction confirmation | Flow specification, transaction log, test evidence |
| Tiêu chuẩn assurance | Credential và session phải đạt mức assurance xác định | Authenticator policy, session lifetime, recovery control | Assessment, configuration, test report |
| Hợp đồng đối tác | Service-to-service phải xác thực hai chiều | mTLS và workload identity | Certificate inventory, trust policy, connection test |
| Audit finding | Revoke phải lan tới mọi resource server trong SLA | Revocation event, cache invalidation, validator check | Propagation metrics, revoke test, audit record |

Mỗi yêu cầu cần có owner, phạm vi, ngày hiệu lực, cách đo và quy trình xử lý exception. Nếu một yêu cầu chưa có test hoặc evidence, không nên đánh dấu hoàn thành chỉ vì cấu hình đã được tạo.

### 3.2. Không tự suy diễn nghĩa vụ pháp lý

Một tiêu chuẩn kỹ thuật không tự động áp dụng cho mọi tổ chức hoặc mọi giao dịch. Cần xác định jurisdiction, loại dịch vụ, vai trò tổ chức, phạm vi dữ liệu, hợp đồng và phiên bản tiêu chuẩn. Đội pháp chế/compliance xác nhận nghĩa vụ; đội bảo mật và kỹ thuật chuyển nghĩa vụ thành control. Bài học này cung cấp phương pháp thiết kế, không thay thế đánh giá pháp lý cho một ngành hoặc thị trường cụ thể.

## 4. Mức bảo đảm xác thực và cách chọn

Mức bảo đảm nên tăng theo tác động nếu credential bị chiếm:

| Mức sử dụng | Ví dụ | Hướng kiểm soát thường phù hợp |
| --- | --- | --- |
| Rủi ro thấp | Nội dung công khai, preference không nhạy cảm | Session có giới hạn, password/passkey theo chính sách nền |
| Rủi ro trung bình | Dữ liệu cá nhân, lịch sử đơn hàng | MFA phù hợp, session timeout, device/risk signal |
| Rủi ro cao | Đổi email/phone, thêm authenticator, thanh toán | Phishing-resistant MFA hoặc step-up mạnh, transaction binding, notification |
| Rủi ro rất cao | Quản trị hệ thống, thay đổi trust root, ký giao dịch quan trọng | Hardware-backed authenticator, privileged access control, dual control khi cần, audit chặt |

Đây là mô hình phân loại minh họa. Tổ chức phải định nghĩa mức assurance cụ thể, không gán nhãn “high” mà thiếu tiêu chí đo.

### 4.1. Tham chiếu mô hình assurance

NIST Digital Identity Guidelines dùng các khái niệm Authentication Assurance Level (AAL) để mô tả mức bảo đảm của quá trình xác thực. Khi áp dụng, cần chọn đúng phiên bản hướng dẫn và profile phù hợp với hệ thống:

- AAL 1 biểu diễn mức bảo đảm cơ bản; một yếu tố có thể phù hợp tùy yêu cầu.
- AAL 2 yêu cầu xác thực đa yếu tố theo các điều kiện của tiêu chuẩn và có yêu cầu về lựa chọn phương thức chống phishing.
- AAL 3 hướng tới mức bảo đảm cao hơn, với authenticator mật mã chống phishing và các ràng buộc về khóa/thiết bị nghiêm ngặt hơn.

Không coi AAL là nhãn marketing cho một phương thức. Phải đối chiếu phiên bản NIST đang áp dụng, authenticator type, verifier requirements, lifecycle, recovery và session controls. Các ngành hoặc chương trình tuân thủ khác có thể dùng mô hình assurance riêng.

### 4.2. Assurance của identity proofing khác authentication

Identity proofing xác minh một người là ai khi tạo hoặc khôi phục danh tính. Authentication xác minh người đang truy cập có kiểm soát authenticator đã liên kết với danh tính. Một tài khoản được proofing kỹ vẫn có thể bị chiếm nếu authenticator yếu; ngược lại, passkey mạnh không chứng minh dữ liệu danh tính ban đầu đã được proofing đúng.

## 5. Yếu tố xác thực và authenticator

Ba nhóm yếu tố phổ biến:

- **Knowledge:** điều người dùng biết, như password hoặc PIN.
- **Possession:** thứ người dùng có, như security key, thiết bị chứa private key hoặc authenticator app.
- **Inherence:** đặc điểm sinh trắc học, như vân tay hoặc khuôn mặt.

Một yếu tố sinh trắc học thường mở khóa private key cục bộ trong authenticator; server không nên nhận raw biometric template. Sinh trắc học có thể tăng tiện lợi và bảo vệ thao tác cục bộ, nhưng không phải bí mật có thể đổi như password.

### 5.1. MFA cần hai yếu tố độc lập

Hai bước không nhất thiết là hai yếu tố. Password và câu hỏi bảo mật đều thuộc knowledge. Password và OTP app có thể là hai yếu tố nếu OTP được tạo trên authenticator possession độc lập theo mô hình phù hợp. Password và PIN mở khóa cùng một thiết bị không tự động tạo hai yếu tố độc lập.

Đánh giá independence phải xem nơi lưu, kênh truyền, khả năng attacker chiếm cả hai và cách verifier kiểm tra. Nếu cùng một malware có thể lấy password và điều khiển authenticator, mức độc lập thực tế có thể thấp hơn thiết kế trên giấy.

### 5.2. Authenticator và credential

Authenticator là thiết bị/phần mềm thực hiện thao tác xác thực; credential là dữ liệu hoặc khóa được liên kết với account. Ví dụ:

| Authenticator | Credential/proof | Rủi ro cần xem xét |
| --- | --- | --- |
| Password manager/browser | Password | Phishing, reuse, malware, autofill origin |
| TOTP app | Shared secret và mã theo thời gian | Phishing/relay, seed backup, clock skew |
| Push app | Device registration và approval proof | MFA fatigue, push interception, device compromise |
| FIDO2 security key | Private key và signed challenge | Mất thiết bị, enrollment/recovery, key protection |
| Synced passkey | Private key được đồng bộ theo hệ sinh thái | Account cloud/device recovery và sync security |
| Client certificate | Private key và certificate chain | Key export, CA compromise, revocation |
| Workload identity agent | SVID/token/certificate ngắn hạn | Runtime compromise, attestation trust, token theft |

## 6. So sánh phương thức theo khả năng chống tấn công

| Phương thức | MFA? | Chống phishing | Chống replay | Ghi chú |
| --- | --- | --- | --- | --- |
| Password | Không | Thấp | Thấp nếu password bị lộ | Cần KDF, blocklist, rate limit và chống reuse |
| SMS OTP | Có thể là yếu tố possession theo profile | Thấp | Mã có thời hạn nhưng có thể relay | SIM swap, SS7 và phishing |
| Email OTP | Phụ thuộc trust model | Thấp | Mã có thể replay trong hạn nếu không consume | Email account có thể là recovery single point |
| TOTP | Có thể là MFA | Thấp đến trung bình | One-time window và consume policy cần rõ | Có thể bị phishing/relay |
| Push approval | Có thể là MFA | Thấp đến trung bình tùy thiết kế | Challenge binding và number matching giúp giảm replay | MFA fatigue |
| FIDO2/passkey | Có thể đáp ứng MFA tùy authenticator/user verification | Cao khi origin binding đúng | Challenge-response, one-time challenge | Phụ thuộc RP ID, origin, user verification và lifecycle |
| Client certificate/mTLS | Xác thực mật mã của client/workload | Cao với private key và trust đúng | TLS handshake/protocol nonce chống replay theo thiết kế | Cần PKI, key protection và revocation |

Không có một bảng xếp hạng áp dụng cho mọi hệ thống. Mức bảo đảm phụ thuộc implementation, thiết bị, key storage, enrollment, recovery, session và threat model. Ví dụ, passkey được đăng ký qua recovery yếu có thể bị attacker thêm vào; certificate được phát từ CA bị compromise có thể không còn đáng tin.

## 7. Phishing-resistant authentication

Phishing-resistant authentication làm cho proof được ràng buộc với verifier/origin hoặc kênh xác thực dự kiến, khiến attacker khó chuyển tiếp proof từ trang giả mạo sang trang thật.

### 7.1. Passkey và WebAuthn

Trong WebAuthn:

1. Relying party tạo challenge ngẫu nhiên.
2. Browser gọi authenticator với RP ID/origin context.
3. Authenticator yêu cầu user presence/verification theo policy.
4. Authenticator ký dữ liệu chứa challenge và context bằng private key.
5. Server xác minh chữ ký, challenge, origin, RP ID hash, credential và user verification.

Origin binding khiến một trang phishing ở domain khác không thể đơn giản xin authenticator tạo assertion hợp lệ cho domain thật. Tuy nhiên, cần kiểm tra RP ID/origin chính xác, challenge freshness, credential binding và flow recovery.

### 7.2. Security key và synced passkey

Security key vật lý thường giữ private key trong thiết bị chuyên dụng; synced passkey có thể được đồng bộ qua hệ sinh thái thiết bị. Cả hai có thể cung cấp phishing resistance khi triển khai đúng, nhưng mô hình bảo vệ key, recovery và khả năng mất thiết bị khác nhau. Chính sách cho admin hoặc tài khoản có quyền cao có thể yêu cầu authenticator hardware-backed hoặc key không xuất được.

### 7.3. Không gọi OTP là phishing-resistant

OTP có thể ngăn một số dạng password-only compromise, nhưng attacker có thể dựng proxy trung gian để lấy password và mã OTP rồi chuyển tiếp ngay tới dịch vụ thật. Nếu yêu cầu tuân thủ đòi hỏi phishing resistance, cần chọn phương thức đáp ứng định nghĩa của profile/tiêu chuẩn áp dụng, không suy ra từ việc có hai yếu tố.

## 8. Định nghĩa yêu cầu theo loại tài khoản và hành động

Một policy tốt không chỉ nói “MFA required”. Nó cần nêu principal, action, authenticator, assurance, freshness, recovery và ngoại lệ.

### 8.1. Ma trận policy minh họa

| Chủ thể/hành động | Yêu cầu xác thực gợi ý | Kiểm soát bổ sung |
| --- | --- | --- |
| Người dùng đăng nhập thường | Password + MFA hoặc passkey theo risk tier | Rate limit, session lifetime, breached credential checks |
| Người dùng xem dữ liệu nhạy cảm | Authentication đủ freshness và factor theo policy | Authorization theo tenant/resource |
| Đổi email/phone recovery | Step-up bằng authenticator mạnh đã đăng ký | Notification tới kênh cũ và mới, hold nếu rủi ro |
| Thêm/xóa passkey hoặc MFA | Re-authentication đủ mạnh | Audit, confirmation và revoke session rủi ro |
| Thanh toán/người thụ hưởng mới | Step-up và xác nhận transaction | Binding số tiền/người nhận, risk checks |
| Nhân viên truy cập hệ thống nội bộ | MFA; phishing-resistant cho nhóm nhạy cảm | Device posture, conditional access |
| Privileged administrator | Phishing-resistant MFA, hardware-backed khi cần | PAM, just-in-time access, approval, session recording |
| Service-to-service | Workload identity và mTLS hoặc token federation | Audience/scope hẹp, credential ngắn hạn, rotation |
| CI/CD deploy production | Federated workload identity | Subject/branch/environment constraints, approval |

Đây là mẫu khởi đầu, không phải bảng nghĩa vụ pháp lý phổ quát. Tổ chức cần điều chỉnh theo risk assessment, loại dữ liệu, quy định và khả năng kỹ thuật.

### 8.2. Step-up authentication

Step-up yêu cầu bằng chứng mạnh hơn khi risk hoặc sensitivity tăng. Ví dụ:

- Login mới từ thiết bị chưa biết.
- Thay đổi email, phone, password hoặc authenticator.
- Tạo API key, certificate hoặc OAuth client.
- Export dữ liệu lớn.
- Chuyển tiền hoặc thêm người thụ hưởng.
- Thay đổi role, policy, signing key hoặc trust relationship.

Step-up cần gắn với action cụ thể và freshness window. Một MFA challenge vừa hoàn thành không nên tự động cấp quyền vô thời hạn cho mọi thao tác sau đó.

## 9. Authentication freshness và session assurance

Session sau login thường tồn tại lâu hơn proof ban đầu. Nếu một hành động nhạy cảm chỉ kiểm tra cookie session, hệ thống có thể dùng một authentication event đã quá cũ.

### Yêu cầu cần định nghĩa

- Thời điểm xác thực gần nhất.
- Authenticator/factor đã sử dụng.
- Có phishing-resistant proof hay không.
- User verification/step-up đã hoàn thành chưa.
- Session idle timeout và absolute lifetime.
- Có yêu cầu re-authentication sau đổi credential hoặc risk event không.
- Khi logout/revoke, token/session downstream bị vô hiệu hóa theo cách nào.

Trong OIDC, các claim như auth_time và acr có thể biểu diễn thời điểm/mức xác thực theo profile. Không tin acr chỉ vì token chứa chuỗi tùy ý; issuer và semantics phải được cấu hình. Resource server cần ánh xạ mức assurance sang policy nội bộ.

### 9.1. Session rotation và fixation

Sau login hoặc step-up, session identifier cần được rotate theo kiến trúc để tránh session fixation. Pre-auth session chỉ được phép hoàn tất authentication; không được truy cập resource cần full session. Cookie cần Secure, HttpOnly và SameSite phù hợp; CSRF protection vẫn cần thiết cho cookie-authenticated request.

### 9.2. Token lifetime và revocation

Access token ngắn hạn giảm cửa sổ lạm dụng nhưng không thay thế revocation. JWT tự xác minh có thể còn hiệu lực tới expiry nếu resource server không kiểm tra revoke state. Cần xác định introspection, denylist, session epoch hoặc TTL và ghi rõ SLA cho từng resource server.

## 10. Enrollment, replacement và recovery phải giữ cùng mức bảo đảm

Một hệ thống có thể yêu cầu passkey khi login nhưng cho phép thêm passkey mới chỉ bằng email link. Khi đó attacker chiếm email có thể thêm authenticator của họ và duy trì quyền truy cập. Enrollment và recovery là một phần của authentication assurance.

### 10.1. Enrollment

- Xác minh user hiện tại bằng mức phù hợp trước khi thêm authenticator.
- Gắn credential với đúng principal và origin/RP ID.
- Xác minh authenticator mới trước khi đánh dấu active.
- Thông báo qua contact đã xác minh khi credential được thêm.
- Audit actor, device/reference, thời gian và policy decision.
- Không hiển thị secret enrollment sau khi hoàn tất.

### 10.2. Replacement và mất thiết bị

- Thu thập bằng chứng độc lập phù hợp với giá trị tài khoản.
- Thu hồi authenticator/credential bị mất.
- Đánh giá session và token trên thiết bị bị mất.
- Cấp authenticator mới và kiểm tra proof-of-control.
- Gửi notification và áp dụng hold/step-up cho hành động rủi ro nếu cần.

### 10.3. Recovery

Recovery không nên yếu hơn mức bảo đảm mà nó khôi phục. Có thể dùng nhiều bằng chứng độc lập, identity proofing, recovery code đã cấp trước, support review hoặc delay có thông báo tùy risk. Không cho support agent bỏ qua policy mà không có dual control, approval và audit.

### 10.4. Fallback

Fallback như SMS, email OTP hoặc câu hỏi bảo mật có thể làm giảm mức bảo đảm tổng thể. Nếu phải duy trì vì accessibility hoặc compatibility:

- Nêu rõ nhóm người dùng và trường hợp được phép.
- Giới hạn hành động có thể thực hiện sau fallback.
- Thêm risk check và notification.
- Theo dõi tỷ lệ sử dụng và abuse.
- Có lộ trình loại bỏ nếu không còn phù hợp.
- Không quảng bá flow có fallback yếu như phishing-resistant end-to-end.

## 11. Privileged account và workload authentication

### 11.1. Privileged users

Tài khoản admin có blast radius lớn nên cần control riêng:

- Phishing-resistant MFA.
- Hardware-backed authenticator khi threat model yêu cầu.
- Tài khoản admin tách biệt khỏi tài khoản email/web thường.
- Just-in-time elevation và thời hạn quyền ngắn.
- Approval/dual control cho thay đổi trust root, signing key hoặc policy quan trọng.
- Re-authentication trước thao tác đặc quyền.
- Session monitoring, audit bất biến và emergency access được kiểm soát.

### 11.2. Workload identity

Workload không có người nhập OTP mỗi lần. Xác thực mạnh giữa dịch vụ thường dựa trên:

- Workload identity được cấp từ authority tin cậy.
- Runtime attestation hoặc managed identity/federation.
- Certificate/mTLS hoặc token ngắn hạn có audience hẹp.
- Private key được bảo vệ và rotation tự động.
- Scope/role tối thiểu, tách theo service và environment.
- Revocation và kiểm tra credential cũ tại mọi validator.

Không dùng password nhân viên hoặc API key dùng chung làm danh tính dài hạn cho service. Một workload được xác thực mạnh vẫn cần authorization riêng cho từng resource/action.

## 12. Compliance mapping: từ yêu cầu tới bằng chứng

Compliance không chỉ cần control tồn tại; tổ chức cần chứng minh control được triển khai đúng, vận hành liên tục và xử lý ngoại lệ.

### 12.1. Bằng chứng thiết kế

- Risk assessment và threat model.
- Authentication policy theo principal/action.
- Danh sách authenticator được chấp nhận và bị cấm.
- Session, token, recovery và revocation requirements.
- Trust boundary và data flow.
- Mapping từ điều khoản tiêu chuẩn/chính sách tới control.

### 12.2. Bằng chứng triển khai

- Cấu hình IdP, MFA policy và conditional access.
- Passkey/security key enrollment coverage.
- Certificate inventory, issuer/CA trust và rotation config.
- Workload identity/federation trust policy.
- Session/token lifetime và revocation settings.
- API authorization policy và audience/scope mapping.

### 12.3. Bằng chứng vận hành

- Login/MFA/step-up audit events.
- Alert và incident records.
- Revoke propagation measurements.
- Access review và exception register.
- Test reports, CI release gates và regression evidence.
- Training/support procedure và recovery exercise.

### 12.4. Bằng chứng phải có provenance

Một screenshot cấu hình không chứng minh runtime thực sự từ chối credential yếu. Kết hợp cấu hình với test thực tế, audit event, sample verification và owner attestation. Evidence cần timestamp, environment, version, source, integrity và quyền truy cập phù hợp.

## 13. Quản lý exception và compensating control

Một số hệ thống cũ hoặc người dùng có nhu cầu accessibility không thể ngay lập tức dùng phương thức mạnh nhất. Exception cần được quản lý như một rủi ro có thời hạn:

- Lý do nghiệp vụ và phạm vi cụ thể.
- Principal, application, tenant và action được miễn.
- Risk assessment và approver có thẩm quyền.
- Thời hạn bắt đầu/kết thúc và ngày review.
- Compensating controls như giới hạn mạng, transaction cap, dual approval hoặc monitoring tăng cường.
- Owner chịu trách nhiệm và kế hoạch remediation.
- Bằng chứng sử dụng exception và sự kiện vi phạm policy.

Không tạo allowlist vĩnh viễn cho tài khoản đặc quyền chỉ vì một authenticator chưa tương thích. Không để fallback tự động áp dụng cho mọi user khi một provider gặp outage.

### 13.1. Break-glass account

Emergency account có thể cần để khôi phục hệ thống khi IdP hoặc MFA provider lỗi. Nó phải được giới hạn, credential bảo vệ độc lập, quyền sử dụng có kiểm soát, alert ngay khi được dùng, rotation sau mỗi lần sử dụng và kiểm tra định kỳ. Break-glass không phải đường đăng nhập thường ngày.

## 14. Threat model và lỗi triển khai thường gặp

| Lỗi/đe dọa | Vì sao làm yếu xác thực | Kiểm soát |
| --- | --- | --- |
| MFA checkbox nhưng factor yếu | Không đánh giá independence hoặc phishing resistance | Định nghĩa authenticator profile và threat model |
| SMS/email fallback không giới hạn | Attacker đi vòng phương thức mạnh | Giới hạn fallback, risk checks và action scope |
| Recovery yếu hơn login | Attacker reset hoặc thêm factor mới | Proofing, step-up, notification và delay |
| Session quá dài | Credential bị lộ có thời gian sử dụng lớn | Idle/absolute timeout, re-auth và revoke |
| Audience không kiểm tra | Token hợp lệ bị dùng ở resource sai | Audience validation tại từng API |
| Phishing OTP | Attacker relay code trong cửa sổ hợp lệ | Passkey/security key, origin binding |
| MFA fatigue | Người dùng bị thúc ép approve | Number matching, challenge limits, phishing-resistant MFA |
| Replay challenge | Proof cũ được dùng lại | Nonce, one-time consume và replay cache |
| Support override | Social engineering support để bypass factor | Dual control, verification và audit |
| Admin dùng tài khoản thường | Session/phishing thường ảnh hưởng quyền cao | Separate admin identity, PAM và step-up |
| Workload shared secret | Secret copy được giữa nhiều service | Workload identity, mTLS/federation, short-lived credential |
| Revocation không lan truyền | Credential cũ vẫn được chấp nhận | Validator inventory, SLA và verification test |
| Enrollment không xác minh | Attacker gắn authenticator của họ | Re-authentication và proof-of-control |
| Biometric bị coi là secret có thể đổi | Sinh trắc học không thể reset như password | Bảo vệ local template/key; có recovery credential an toàn |

## 15. Kiến trúc tham chiếu cho strong authentication

~~~mermaid
flowchart TD
    U[User or workload] --> P[Policy decision]
    P --> R[Risk and assurance requirement]
    R --> A[Approved authenticator]
    A --> V[Verifier / identity provider]
    V --> C[Credential and session issuance]
    C --> Z[Authorization policy]
    Z --> X[Protected resource]
    V --> L[(Audit and security events)]
    C --> L
    Z --> L
    L --> M[Monitoring and compliance evidence]
    P --> E[Enrollment / recovery policy]
    E --> A
    M --> Q[Review, incident and exception management]
~~~

### Các điểm quyết định

1. Policy xác định principal, action, risk tier và assurance requirement.
2. Risk engine có thể yêu cầu step-up hoặc từ chối theo context.
3. Authenticator chỉ được chọn từ danh sách được policy cho phép.
4. Verifier kiểm tra proof, origin, challenge, issuer, audience và lifecycle state.
5. Session/token được cấp với thời hạn và assurance context phù hợp.
6. Authorization kiểm tra action/resource/tenant độc lập với authentication.
7. Audit/monitoring ghi quyết định, phương thức và reference không chứa secret.
8. Enrollment/recovery phải tuân theo cùng trust model và có review/exception.

## 16. Pseudocode: đánh giá yêu cầu xác thực trước hành động

Ví dụ khái niệm cho policy evaluation. Đây không phải API tiêu chuẩn:

~~~ts
async function evaluateStrongAuthentication(context, action) {
  const requirement = policy.forAction({
    principalType: context.principalType,
    role: context.role,
    resource: action.resource,
    operation: action.name,
    tenant: context.tenant
  });

  if (!context.authenticated) {
    return { decision: "DENY", reason: "AUTHENTICATION_REQUIRED" };
  }

  if (!requirement.allowedAuthenticators.includes(context.authenticatorType)) {
    return { decision: "STEP_UP", reason: "AUTHENTICATOR_NOT_ALLOWED" };
  }

  if (context.authenticationAgeSeconds > requirement.maxAuthAgeSeconds) {
    return { decision: "STEP_UP", reason: "AUTHENTICATION_TOO_OLD" };
  }

  if (requirement.phishingResistant && !context.phishingResistant) {
    return { decision: "STEP_UP", reason: "PHISHING_RESISTANCE_REQUIRED" };
  }

  if (requirement.userVerification && !context.userVerified) {
    return { decision: "STEP_UP", reason: "USER_VERIFICATION_REQUIRED" };
  }

  if (context.credentialRevoked || context.sessionRevoked) {
    return { decision: "DENY", reason: "CREDENTIAL_REVOKED" };
  }

  return { decision: "ALLOW", assuranceProfile: requirement.profileId };
}
~~~

Trong triển khai thực tế:

- Context phải đến từ verifier/session store đáng tin, không lấy authenticator type hoặc assurance level do client tự khai.
- Policy phải được version hóa và áp dụng nhất quán tại resource server.
- Phải kiểm tra issuer/audience/signature/expiry và revocation trước khi tin claims.
- Authentication ALLOW không thay thế authorization cho resource/action.
- STEP_UP cần tạo challenge mới gắn với action/session và consume một lần.
- Audit ghi policy version, decision và reason category, không ghi credential secret.

## 17. Tiêu chí chấp nhận và kiểm thử

| Tình huống | Kết quả mong đợi |
| --- | --- |
| User thuộc nhóm bắt buộc MFA nhưng chỉ có password | Không cấp full session; yêu cầu enrollment/step-up theo policy |
| Admin dùng phương thức không phishing-resistant | Từ chối hoặc yêu cầu authenticator được phê duyệt |
| OTP bị phishing/relay trong threat model | Control được đánh giá là không đáp ứng phishing-resistant requirement |
| Passkey origin/RP ID sai | Assertion bị từ chối |
| Challenge đã dùng hoặc hết hạn | Từ chối replay/expired proof |
| Authenticator bị revoke | Không tạo session/token mới |
| Recovery qua kênh yếu | Không nâng lên full assurance ngoài policy |
| Thêm passkey không có re-authentication | Từ chối hoặc yêu cầu step-up |
| Step-up cũ quá freshness window | Yêu cầu xác thực lại |
| Token đúng chữ ký nhưng sai audience | Resource server từ chối |
| JWT đã revoke nhưng cache còn active | Propagation test phát hiện và đưa validator về trạng thái từ chối theo SLA |
| Admin thực hiện thay đổi trust root | Yêu cầu phishing-resistant authentication và approval theo policy |
| Workload gọi API nội bộ | Xác minh workload identity/mTLS và scope hẹp |
| Identity provider outage | Không fail-open; áp dụng fail-closed hoặc break-glass được kiểm soát |
| Break-glass account được dùng | Alert, audit, review và rotation sau sử dụng |
| Exception hết hạn | Policy tự ngừng miễn trừ hoặc yêu cầu gia hạn được phê duyệt |
| Credential mới được enroll | Có proof-of-control, audit và notification |
| Credential cũ bị revoke | Validator liên quan từ chối credential cũ theo SLA |
| Evidence export | Có policy version, timestamp, source, integrity và owner |
| Public error khi login sai | Không tiết lộ account existence hoặc authenticator inventory |

### Chỉ số vận hành và compliance

Theo dõi tỷ lệ principal đạt authenticator profile, tỷ lệ admin dùng phishing-resistant MFA, số fallback/exception còn hiệu lực, tỷ lệ step-up thành công/thất bại, recovery method changes, revoke propagation lag, credential inventory coverage, số test regression, số incident liên quan credential và tuổi của exception. Phân tách theo tenant, role và environment nhưng tránh đưa PII hoặc secret vào metric label.

## 18. Tình huống thực tế: nâng mức xác thực cho thao tác thanh toán

Một ứng dụng cho phép người dùng xem đơn hàng bằng session thông thường. Khi thêm người thụ hưởng hoặc chuyển tiền vượt hạn mức, tổ chức muốn yêu cầu xác thực mạnh hơn.

### Thiết kế

1. Xác định hành động rủi ro cao và principal thuộc phạm vi.
2. Chọn authenticator phishing-resistant phù hợp, ví dụ passkey/security key theo profile được chấp nhận.
3. Yêu cầu re-authentication gần thời điểm giao dịch và gắn proof với transaction context.
4. Hiển thị rõ người thụ hưởng, số tiền và thông tin cần xác nhận.
5. Resource server kiểm tra session freshness, assurance context, audience và authorization.
6. Nếu dùng delegated service, token downstream có scope hẹp và actor/subject rõ.
7. Ghi audit event về policy version, authenticator class, transaction reference và kết quả.
8. Nếu user mất authenticator, recovery phải có proofing tương xứng; không tự động hạ xuống email OTP không giới hạn.
9. Sau khi hoàn tất, session tiếp tục theo timeout/revocation policy.

### Kiểm thử

- Password-only session không thể thực hiện hành động rủi ro cao.
- OTP bị relay không được coi là phishing-resistant proof.
- Step-up challenge hết hạn hoặc replay bị từ chối.
- Transaction amount/beneficiary thay đổi sau khi ký/xác nhận phải yêu cầu proof mới.
- User không có quyền trên account/tenant vẫn bị authorization từ chối dù authentication mạnh.
- Recovery yếu không thể tự cấp lại quyền thanh toán đầy đủ.

## 19. Bài tập tự kiểm tra

Một tổ chức có web app cho khách hàng, portal nhân viên, console quản trị và nhiều service nội bộ. Hiện tại tất cả dùng password và SMS OTP. Tổ chức muốn đáp ứng yêu cầu xác thực mạnh cho giao dịch tài chính, dữ liệu cá nhân và thao tác quản trị.

Hãy:

1. Phân loại principal và hành động theo mức rủi ro.
2. Viết yêu cầu cụ thể cho login, step-up, session freshness, enrollment và recovery.
3. Chọn phương thức phù hợp cho khách hàng, nhân viên, admin và workload.
4. Giải thích vì sao SMS/TOTP không mặc nhiên đáp ứng phishing-resistant requirement.
5. Thiết kế policy cho thêm passkey, đổi recovery channel và giao dịch người thụ hưởng mới.
6. Định nghĩa control cho service-to-service và CI/CD workload.
7. Tạo traceability matrix từ policy tới cấu hình, test và audit evidence.
8. Thiết kế exception register và break-glass procedure.
9. Viết test case chứng minh credential yếu/fallback không thể vượt policy.

**Gợi ý đánh giá:** lời giải tốt phải xác định scope, assurance, authenticator profile, phishing/replay resistance, session/recovery lifecycle, authorization độc lập, exception có thời hạn và evidence có thể kiểm chứng. Không chỉ ghi “bật MFA” mà thiếu điều kiện chấp nhận và cách đo.

---

**Ghi nhớ:** strong authentication requirement phải mô tả rõ **ai**, **làm hành động nào**, **cần mức bảo đảm gì**, **dùng authenticator nào**, **chống threat nào**, **khi nào xác thực lại** và **bằng chứng nào chứng minh đã đáp ứng**. Đánh giá toàn bộ lifecycle từ enrollment tới recovery/revocation; ưu tiên phương thức chống phishing cho rủi ro cao; giữ authentication tách biệt với authorization; kiểm soát session, token và workload; quản lý fallback/exception có thời hạn. Một checkbox MFA hoặc cấu hình login đơn lẻ không chứng minh toàn bộ flow đáp ứng yêu cầu tuân thủ.
