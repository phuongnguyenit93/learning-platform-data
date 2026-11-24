# Assurance requirement

## 1. Assurance requirement là gì?

**Assurance requirement** là yêu cầu về mức độ tin cậy và bằng chứng cần có trước khi hệ thống chấp nhận một danh tính, một lần xác thực hoặc một assertion được chuyển giữa các hệ thống. Nó trả lời câu hỏi: hệ thống cần tin cậy đến mức nào rằng người đang yêu cầu truy cập đúng là principal đã đăng ký, đã kiểm soát authenticator hợp lệ và đang thực hiện hành động trong đúng ngữ cảnh?

Một ứng dụng không nên yêu cầu cùng một mức xác minh cho mọi hành động. Xem trang trợ giúp công khai có thể không cần đăng nhập. Xem hồ sơ cá nhân cần session hợp lệ. Đổi password, thêm passkey, thay email khôi phục, cấp quyền quản trị hoặc chuyển tiền cần bằng chứng mạnh hơn, mới hơn và gắn với đúng hành động.

Assurance không chỉ là đếm số yếu tố. Hai bước có thể cùng dựa trên một yếu tố, một thiết bị hoặc một phiên đã bị chiếm quyền. Một lần xác thực có thể dùng mật khẩu và OTP nhưng vẫn dễ bị phishing; một passkey có thể chống phishing tốt hơn nhưng session sau đó có thể tồn tại quá lâu. Assurance requirement phải mô tả thuộc tính cần có, cách kiểm chứng, thời hạn hiệu lực và hậu quả khi không đạt.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, assurance requirement kết nối credential, password, MFA, passkey, certificate, token, session, identity proofing, federation, step-up và account recovery. Người thiết kế cần chuyển mức rủi ro của hành động thành policy có thể thực thi và kiểm thử được.

Sau bài học, người học có thể:

- Phân biệt identity assurance, authentication assurance và federation assurance.
- Giải thích IAL, AAL và FAL trong các framework như NIST SP 800-63.
- Chuyển risk classification thành yêu cầu xác thực cụ thể.
- Đánh giá phishing resistance, replay resistance, user verification và authenticator binding.
- Xác định freshness, reauthentication và step-up requirements.
- Đánh giá passkey, password, OTP, certificate và workload credential theo threat model.
- Xây policy cho session, federation, recovery và sensitive transaction.
- Xử lý assurance downgrade, missing evidence và dependency outage.
- Ghi nhận authentication context mà không tin mù quáng vào claim do client tự khai.
- Thiết kế test matrix và bằng chứng kiểm toán cho từng assurance requirement.

## 2. Assurance không phải một điểm số chung

Từ assurance có thể được dùng rộng trong kiến trúc bảo mật, nhưng các framework định nghĩa những chiều khác nhau. Một hệ thống cần nói rõ đang yêu cầu bằng chứng về điều gì.

Ba chiều thường được nhắc trong NIST SP 800-63 series:

- **Identity Assurance Level (IAL):** mức độ tin cậy của quy trình chứng minh và xác minh danh tính khi thiết lập hoặc liên kết danh tính với một người thật.
- **Authentication Assurance Level (AAL):** mức độ tin cậy của quá trình xác thực tại một thời điểm, dựa trên authenticator, cách sử dụng và các kiểm soát liên quan.
- **Federation Assurance Level (FAL):** mức độ bảo vệ khi một Identity Provider chuyển assertion hoặc thông tin xác thực sang Relying Party qua federation.

Ba chiều này trả lời những câu hỏi khác nhau. Một người có thể đã được proofing danh tính ở mức cao nhưng hiện đang dùng một session yếu hoặc cũ. Một lần đăng nhập có thể dùng authenticator mạnh nhưng assertion federation được chuyển thiếu bảo vệ. Một passkey có thể chứng minh quyền kiểm soát credential nhưng không tự chứng minh dữ liệu định danh ban đầu đã được kiểm tra theo mức proofing nào.

| Chiều assurance | Câu hỏi | Ví dụ bằng chứng |
| --- | --- | --- |
| IAL | Danh tính đã được chứng minh đáng tin đến đâu? | Quy trình proofing, kiểm tra bằng chứng, liên kết với chủ thể |
| AAL | Lần xác thực này mạnh đến đâu? | Authenticator, yếu tố, user verification, chống phishing/replay |
| FAL | Assertion federation được bảo vệ đến đâu? | Chữ ký, audience, recipient, transaction binding, assertion protection |

Không cộng IAL + AAL + FAL thành một điểm số. Một yêu cầu có thể đặt ngưỡng riêng cho từng chiều hoặc không cần một chiều nào đó. Ví dụ, một API nội bộ xác thực workload có thể cần assurance của client key và workload identity nhưng không cần IAL của một cá nhân.

### 2.1. Assurance framework và phiên bản áp dụng

NIST SP 800-63 là một bộ hướng dẫn phổ biến về digital identity. Tổ chức cũng có thể phải tuân theo tiêu chuẩn ngành, quy định pháp lý, profile của hệ thống hoặc policy nội bộ. Cần ghi rõ phiên bản và profile được áp dụng vì định nghĩa, lựa chọn authenticator và yêu cầu triển khai có thể được cập nhật.

Không lấy tên AAL/IAL/FAL làm nhãn marketing rồi tự gán cho sản phẩm. Đối chiếu yêu cầu normative của phiên bản được tổ chức chấp nhận, loại credential, quy trình vận hành và bằng chứng thực tế. Một tuyên bố assurance cần có phạm vi, owner, evidence và ngày review.

## 3. Tách identity proofing khỏi authentication

Identity proofing và authentication thường xảy ra ở các thời điểm khác nhau.

**Identity proofing** thiết lập mối liên hệ giữa một người và một danh tính trong hệ thống. Tùy rủi ro, quy trình có thể kiểm tra giấy tờ, nguồn dữ liệu đáng tin, sự hiện diện của người đó hoặc xác minh qua tổ chức có thẩm quyền.

**Authentication** kiểm tra liệu requester hiện tại có kiểm soát authenticator đã liên kết với principal hay không. Nó có thể dùng password, passkey, certificate, security key hoặc phương thức khác theo policy.

Ví dụ:
1. Người dùng hoàn thành identity proofing khi mở tài khoản.
2. Hệ thống liên kết tài khoản với một hoặc nhiều authenticator.
3. Những lần đăng nhập tiếp theo xác minh authenticator.
4. Khi người dùng mất authenticator, recovery có thể cần proofing hoặc bằng chứng thay thế.
5. Khi người dùng thay đổi thông tin định danh, hệ thống có thể cần proofing bổ sung.

Một lần đăng nhập bằng passkey không tự làm tăng IAL. Một lần kiểm tra giấy tờ không tự làm cho session sau đó có AAL cao. Assurance requirement phải ghi rõ chiều nào đang được đáp ứng và evidence nào hỗ trợ kết luận.

## 4. Authentication assurance: điều gì làm một lần xác thực mạnh hơn?

AAL không đơn giản là số màn hình hoặc số prompt. Các thuộc tính cần xem xét gồm:

- Số và loại yếu tố được chứng minh.
- Sự độc lập giữa các yếu tố.
- Khả năng chống phishing và giả mạo verifier.
- Khả năng chống replay.
- Bằng chứng possession của authenticator.
- User verification hoặc user presence theo yêu cầu.
- Bảo vệ secret/private key.
- Ràng buộc authenticator với account và thiết bị.
- Cách quản lý enrollment, rotation, revoke và recovery.
- Freshness của lần xác thực và session.
- Bảo vệ kênh truyền và transaction context.

### 4.1. Factor count không đủ

Ba nhóm yếu tố truyền thống:
- Knowledge: thứ người dùng biết, như password hoặc PIN.
- Possession: thứ người dùng sở hữu/kiểm soát, như security key hoặc thiết bị giữ private key.
- Inherence: đặc điểm sinh học, như vân tay hoặc khuôn mặt.

Hai password khác nhau vẫn là cùng loại knowledge factor. Password và câu hỏi bảo mật cũng thường cùng phụ thuộc knowledge. Hai OTP gửi tới cùng một điện thoại có thể không tạo ra hai yếu tố độc lập. Một thiết bị bị chiếm quyền có thể làm suy yếu nhiều yếu tố cùng lúc.

Khi đánh giá MFA, hỏi từng yếu tố có độc lập về nguồn credential, thiết bị, kênh và threat không. Đếm số prompt không thay thế việc phân tích sự độc lập.

### 4.2. Possession và proof-of-possession

Một giá trị token được lưu trong file không tự chứng minh thiết bị đang kiểm soát private key. Proof-of-possession thường dùng chữ ký hoặc MAC trên challenge để chứng minh requester có quyền sử dụng key.

Server phải xác minh:
- Public key hoặc shared-key reference đã được đăng ký.
- Challenge do server sinh, còn hạn và chưa dùng.
- Chữ ký/MAC đúng thuật toán và key.
- Audience, issuer, client và transaction context đúng.
- Key chưa bị revoke.
- Request gắn với đúng principal và action.

### 4.3. User presence và user verification

User presence cho biết có thao tác hoặc sự hiện diện của người dùng theo cơ chế authenticator. User verification cho biết authenticator đã xác minh người dùng bằng phương thức được hỗ trợ, như biometric hoặc PIN.

Hai thuộc tính này không đồng nghĩa. Với WebAuthn, relying party có thể kiểm tra cờ User Present và User Verified trong authenticator data theo policy. Không suy luận rằng mọi assertion đều có biometric chỉ vì user verification thành công.

## 5. IAL: yêu cầu đối với việc chứng minh danh tính

IAL tập trung vào quy trình thiết lập danh tính, chất lượng bằng chứng và mức tin cậy của liên kết giữa người thật với account.

Các câu hỏi thiết kế:
- Hệ thống cần biết người này là ai hay chỉ cần một account pseudonymous?
- Danh tính có ảnh hưởng đến quyền, nghĩa vụ hoặc tài sản có giá trị không?
- Nguồn bằng chứng nào đáng tin và còn hiệu lực?
- Có cần xác minh giấy tờ, dữ liệu độc lập, địa chỉ hoặc tổ chức phát hành không?
- Có cần xác minh người trình diện là chủ thể của bằng chứng không?
- Quy trình có chống giả mạo, deepfake hoặc synthetic identity không?
- Dữ liệu proofing được lưu bao lâu và ai có thể xem?
- Có quy trình sửa lỗi, khiếu nại và re-proofing không?

### 5.1. Không thu thập proofing quá mức

Không phải dịch vụ nào cũng cần tên pháp lý, ngày sinh hoặc giấy tờ. Nếu sản phẩm chỉ cần một account để lưu tùy chọn không nhạy cảm, yêu cầu proofing mạnh có thể không tương xứng và tạo thêm dữ liệu nhạy cảm.

Ngược lại, dịch vụ tài chính, quyền lợi pháp lý hoặc thao tác có ràng buộc danh tính có thể cần proofing theo tiêu chuẩn áp dụng. Quyết định cần dựa trên impact, nghĩa vụ và threat model, không chỉ sự tiện lợi.

### 5.2. Proofing lifecycle

IAL không nhất thiết bất biến suốt vòng đời account. Cần xác định khi nào:
- Bằng chứng hết hạn hoặc bị thu hồi.
- Dữ liệu định danh thay đổi.
- Có dấu hiệu identity fraud.
- Account được chuyển giao hoặc hợp nhất.
- Recovery cần xác minh lại.
- Người dùng yêu cầu sửa thông tin.

Không coi một bản scan đã lưu nhiều năm là bằng chứng vĩnh viễn nếu nguồn có thể bị thu hồi hoặc danh tính đã thay đổi.

## 6. FAL: yêu cầu đối với federation

Federation cho phép một Identity Provider (IdP) xác thực principal và chuyển assertion tới Relying Party (RP). RP cần tin cậy issuer và kiểm tra assertion đúng ngữ cảnh.

FAL tập trung vào cách assertion được tạo, gửi, ràng buộc và bảo vệ. Các câu hỏi gồm:
- RP có xác minh chữ ký và issuer không?
- Audience/recipient có đúng RP không?
- Assertion có thời hạn ngắn và transaction binding không?
- Có chống replay và substitution không?
- Có bảo vệ assertion khỏi lộ hoặc bị sửa trên đường truyền không?
- RP có xác minh state/nonce/correlation với request ban đầu không?
- Attribute được phát hành có tối thiểu không?
- Logout, account disable và revocation được truyền như thế nào?

### 6.1. OIDC và SAML

Trong OpenID Connect, RP kiểm tra ID Token theo protocol: chữ ký, issuer, audience, expiry, nonce nếu được gửi, và các claim liên quan. OAuth access token dùng truy cập resource server; không nhầm access token với ID Token.

Trong SAML, service provider kiểm tra signature, issuer, audience restriction, recipient, destination, time conditions, subject confirmation và request correlation theo profile. Không chỉ parse XML rồi tin nội dung.

Cả hai protocol đều cần cấu hình chính xác và thư viện được duy trì. Không tự viết parser hoặc bỏ kiểm tra để xử lý lỗi tương thích.

### 6.2. Federation assurance không thay AAL

RP có thể nhận assertion nói rằng user đã được xác thực ở mức hoặc context nhất định. RP chỉ nên tin claim đó khi:
- IdP nằm trong trust configuration.
- Assertion được xác minh đúng protocol.
- Authentication context được ánh xạ theo agreement.
- Thời điểm xác thực đủ mới.
- Issuer thực sự bảo đảm thuộc tính được tuyên bố.
- RP policy chấp nhận mức assurance đó.

Một chuỗi ký hợp lệ chỉ chứng minh assertion đến từ issuer tương ứng và không bị sửa; nó không tự chứng minh issuer đã dùng phương thức mạnh nào nếu context claim không đáng tin hoặc mapping không rõ.

## 7. Chuyển risk thành assurance requirement

Bắt đầu từ hành động và tác động khi bị lạm dụng. Không bắt đầu bằng danh sách công nghệ rồi cố tìm nơi sử dụng.

Các yếu tố risk:
- Giá trị tài sản hoặc dữ liệu.
- Mức độ nhạy cảm và khả năng gây hại.
- Khả năng đảo ngược hành động.
- Tác động tới người khác hoặc tenant khác.
- Khả năng attacker có credential bị đánh cắp.
- Phishing, malware, device theft và insider threat.
- Thời gian phát hiện và khả năng phục hồi.
- Nghĩa vụ pháp lý hoặc hợp đồng.
- Mức chấp nhận gián đoạn dịch vụ.

### 7.1. Ma trận ví dụ

| Hành động | Impact nếu bị chiếm quyền | Assurance requirement minh họa |
| --- | --- | --- |
| Đọc nội dung public | Thấp | Không cần identity; rate limit theo abuse policy |
| Xem dữ liệu cá nhân | Trung bình/cao tùy dữ liệu | Session hợp lệ, audience/scope đúng, freshness phù hợp |
| Cập nhật profile thông thường | Trung bình | Authentication hiện hành và CSRF protection nếu cookie |
| Đổi password | Cao | Reauthentication hoặc step-up, session/credential lifecycle xử lý sau đổi |
| Thêm/xóa MFA hoặc passkey | Cao | Strong recent authentication, proof-of-possession hoặc factor hiện có, notification |
| Đổi recovery email/phone | Cao | Step-up, xác minh kênh mới, cảnh báo kênh cũ và delay theo risk |
| Cấp quyền admin | Rất cao | Phishing-resistant authentication, recent verification, approval và audit |
| Chuyển tiền giá trị lớn | Rất cao | Strong user verification, transaction binding và authorization độc lập |
| Service-to-service write | Cao | Workload identity, key protection, audience/scope hẹp và rotation |
| Thay đổi trust configuration | Rất cao | Privileged step-up, dual control và audit bền vững |

Đây là ví dụ định hướng, không phải mức assurance chuẩn áp dụng cho mọi tổ chức. Tổ chức phải phân loại dữ liệu/action và map sang framework, policy và nghĩa vụ cụ thể.

### 7.2. Assurance matrix phải có ngoại lệ được kiểm soát

Một policy có thể cho phép nhiều authenticator khác nhau nếu chúng đáp ứng cùng thuộc tính cần thiết. Ví dụ, passkey với user verification hoặc hardware security key có thể là các lựa chọn khác nhau cho một action phishing-resistant. SMS OTP có thể được chấp nhận ở một flow rủi ro thấp hơn nhưng không được âm thầm dùng thay phương thức bắt buộc chống phishing.

Ghi rõ:
- Authenticator được phép.
- Authenticator bị cấm.
- Fallback.
- Bằng chứng thay thế.
- Điều kiện step-up.
- Người phê duyệt ngoại lệ.
- Thời hạn ngoại lệ và ngày review.

## 8. Đánh giá password, OTP, passkey và certificate

| Phương thức | Bằng chứng chính | Thuộc tính mạnh | Giới hạn cần đánh giá |
| --- | --- | --- | --- |
| Password | Knowledge secret được verifier kiểm tra | Dễ triển khai, phổ biến | Phishing, reuse, stuffing, offline guessing sau verifier leak |
| SMS OTP | Code gửi tới số điện thoại | Bổ sung possession theo kênh điện thoại trong một số threat model | SIM swap, SS7/interception, phishing, delivery dependency |
| TOTP | Code sinh từ shared secret và thời gian | Không phụ thuộc SMS delivery | Phishing real-time, seed theft, clock window và replay trong window nếu không kiểm soát |
| Push approval | User approve challenge trên thiết bị | UX tốt, có thể hiển thị context | MFA fatigue, prompt confusion, device compromise |
| FIDO/WebAuthn passkey | Public-key assertion gắn RP/origin | Phishing resistance, challenge-response, có thể có UV | Enrollment/recovery, synced vs device-bound, platform assurance |
| Hardware security key | Private key trên authenticator | Possession proof, phishing-resistant theo protocol/config | Mất thiết bị, enrollment và recovery |
| Client certificate | Private key chứng minh client identity | Mạnh cho machine/client authentication | Key protection, issuance, SAN mapping, revocation và lifecycle |
| HMAC API key | Shared secret ký request | Có thể bind method/path/body/time/nonce | Secret distribution, replay nếu thiếu nonce, rotation và attribution |

Không gán AAL chỉ từ tên phương thức. Assurance phụ thuộc cách triển khai, loại authenticator, enrollment, verifier, channel, user verification, phishing/replay resistance và framework được áp dụng.

### 8.1. Password + OTP có đủ không?

MFA có thể làm giảm nguy cơ khi một yếu tố bị lộ, nhưng không tự bảo đảm chống phishing. Attacker có thể dùng reverse proxy phishing để chuyển tiếp password và OTP trong thời gian thực. Nếu action yêu cầu phishing resistance, cần authenticator và flow có thuộc tính đó, chẳng hạn WebAuthn/FIDO đúng origin/RP ID theo policy.

### 8.2. Passkey có tự đạt mọi yêu cầu không?

Passkey có thể cung cấp phishing-resistant public-key authentication, nhưng cần kiểm tra:
- User verification có được yêu cầu và xác nhận không?
- Credential thuộc RP ID đúng không?
- Challenge có fresh và one-time không?
- Public key/credential có được liên kết đúng principal không?
- Credential là synced hay device-bound theo policy?
- Attestation có cần thiết không và được đánh giá thế nào?
- Recovery và account linking có làm yếu trust không?
- Session được cấp sau đó có expiry/revocation phù hợp không?

## 9. Phishing resistance và verifier binding

Một assurance requirement có thể yêu cầu authentication chống phishing. Đây là thuộc tính của giao thức và authenticator, không phải một checkbox UI.

Phishing-resistant authentication ràng buộc proof với verifier hoặc relying party hợp lệ, khiến credential khó dùng lại trên origin giả. WebAuthn/FIDO thực hiện ràng buộc qua RP ID/origin và chữ ký challenge theo protocol.

Kiểm thử:
- Credential không được chấp nhận ở origin giả.
- RP ID mismatch bị từ chối.
- Challenge gắn với đúng transaction và client.
- Assertion từ một RP không thể dùng cho RP khác.
- Redirect/callback không làm mất transaction correlation.
- Recovery không cho attacker đăng ký authenticator mới bằng một flow yếu.

Không tuyên bố password + OTP chống phishing chỉ vì có hai yếu tố. Không dùng UI domain warning như thay thế verifier binding.

## 10. Replay resistance và freshness

Replay resistance bảo đảm một proof cũ không thể được dùng lại để tạo authentication hoặc action mới. Freshness xác định bằng chứng có đủ mới so với policy không.

Các cơ chế:
- Server-generated nonce/challenge.
- One-time token và atomic consume.
- Timestamp với cửa sổ hợp lệ.
- Sequence number hoặc counter khi protocol hỗ trợ.
- Token expiry và audience binding.
- Request signature gắn method/path/body.
- Refresh token rotation và reuse detection.
- Transaction digest gắn nội dung hành động.

Một challenge hợp lệ về chữ ký vẫn có thể bị replay nếu server không lưu trạng thái đã dùng hoặc không kiểm tra expiry. Một token còn exp trong tương lai vẫn có thể không đạt freshness requirement cho hành động nhạy cảm nếu authentication time quá cũ.

### 10.1. Freshness không chỉ là token expiry

Phân biệt:
- Token validity: token có chữ ký/claims hợp lệ và chưa hết hạn không?
- Authentication freshness: user đã xác thực gần đây đến mức nào?
- Session freshness: session đã được tạo hoặc xác minh lại gần đây đến đâu?
- Transaction freshness: proof có được tạo cho đúng giao dịch hiện tại không?

Không suy ra auth_time mới từ token được refresh nếu refresh không thực hiện user authentication mới.

## 11. User verification, authenticator assurance và device binding

User verification xác nhận authenticator đã kiểm tra người dùng theo cơ chế của nó. Device binding liên kết credential hoặc key với thiết bị/client cụ thể. Hai thuộc tính này cần được policy phân biệt.

Ví dụ:
- Passkey có UV: authenticator đã thực hiện user verification theo protocol.
- Client certificate: chứng minh client giữ private key, nhưng không nhất thiết chứng minh có người đang thao tác.
- Workload identity: xác thực service/process, không phải human user.
- Biometric unlock cục bộ: mở khóa key trên thiết bị; server chỉ biết kết quả nếu flow tạo proof đáng tin.
- Device attestation: có thể cung cấp thông tin về thiết bị/key environment, nhưng cần trust model và privacy review.

Không dùng device fingerprint đơn thuần như proof-of-possession. Không coi thiết bị đã biết là bằng chứng account holder đang hiện diện.

## 12. Session assurance và authentication context

Sau login, session có thể tồn tại lâu hơn lần xác thực ban đầu. Assurance requirement cần quy định session kế thừa context nào và khi nào phải xác thực lại.

Thông tin context có thể gồm:
- Principal và issuer.
- Authentication method.
- Authenticator/factor category.
- Authentication time.
- User verification status.
- Phishing resistance property.
- Assurance profile/level.
- Client/device reference.
- Session creation time.
- Step-up time.
- Policy version.
- Federation issuer/context nếu có.

Không tin context do client tự gửi. Context phải được tạo bởi authentication service hoặc nhận từ issuer đã được tin cậy và được xác minh.

### 12.1. Idle và absolute timeout

Session nên có idle timeout và absolute lifetime theo risk. Một session hoạt động liên tục không nên tồn tại vô hạn nếu policy yêu cầu reauthentication sau một khoảng tối đa.

Với action nhạy cảm, yêu cầu recent authentication có thể ngắn hơn session lifetime. Session vẫn active nhưng không còn đủ freshness cho action đó.

### 12.2. Reauthentication

Reauthentication là xác minh lại user trước hoặc trong khi thực hiện action. Policy cần xác định:
- Khi nào yêu cầu.
- Authenticator nào được phép.
- Mức assurance tối thiểu.
- Freshness window.
- Có cần transaction binding không.
- Kết quả áp dụng cho một action hay nhiều action.
- Khi nào context hết hiệu lực.

Không coi việc người dùng mở khóa màn hình điện thoại là reauthentication từ xa nếu server không nhận được bằng chứng được policy chấp nhận.

## 13. Step-up authentication

Step-up nâng assurance trước một hành động có rủi ro cao hơn context hiện tại. Nó cần được kích hoạt bởi policy và ràng buộc với đúng principal/action.

Ví dụ:
1. Người dùng đăng nhập bằng password và TOTP để xem dữ liệu thông thường.
2. Người dùng yêu cầu thêm passkey hoặc thay recovery email.
3. Policy nhận thấy action yêu cầu phishing-resistant recent authentication.
4. Server tạo challenge gắn account, action và transaction.
5. User hoàn tất passkey hoặc authenticator được chấp nhận.
6. Server xác minh assertion và cập nhật context.
7. Action được authorize độc lập và audit.

~~~mermaid
sequenceDiagram
    participant U as User
    participant A as Application
    participant P as Policy Engine
    participant I as Authenticator
    U->>A: Request sensitive action
    A->>P: Evaluate current context and action
    P-->>A: Step-up required
    A->>I: Start fresh challenge
    I->>U: Verify user
    U->>I: Complete verification
    I-->>A: Signed assertion
    A->>P: Evaluate verified evidence
    P-->>A: Permit or deny
    A-->>U: Action result
~~~

### 13.1. Step-up không phải authorization

Xác thực mạnh hơn không tự cấp quyền. Sau step-up, server vẫn phải kiểm tra ownership, tenant, role, scope, transaction limits và business rule. Một admin vừa reauthenticate vẫn không được phép thay đổi tài nguyên ngoài phạm vi.

### 13.2. Chống step-up downgrade

Nếu policy yêu cầu passkey hoặc hardware key, không tự động chuyển sang SMS/email khi authenticator timeout. Fallback phải được định nghĩa trước, có assurance tương đương hoặc yêu cầu recovery/approval riêng.

## 14. Transaction binding cho hành động nhạy cảm

Với thanh toán, chuyển tiền, thay đổi payee, cấp quyền hoặc thay đổi recovery method, chỉ xác minh user gần đây có thể chưa đủ. Proof nên gắn với nội dung transaction.

Transaction binding có thể bao gồm:
- Transaction ID.
- Amount và currency.
- Recipient/destination.
- Resource và action.
- Policy version.
- Nonce/challenge.
- Expiry.
- Principal/client context.

Server tạo digest canonical của nội dung giao dịch, yêu cầu authenticator ký challenge hoặc transaction digest theo protocol được thiết kế. Khi nhận proof, server so sánh digest với transaction đang chờ và consume challenge atomically.

Không để client tự quyết định nội dung nào đã được ký. Không cho phép đổi amount hoặc destination sau khi user xác nhận mà không yêu cầu xác nhận mới.

## 15. Federation assurance và claim mapping

Khi nhận assertion từ IdP, RP cần ánh xạ authentication context sang policy nội bộ. Không phải claim string nào cũng tương đương cùng mức assurance.

Cần quản lý:
- Danh sách issuer tin cậy.
- Metadata và signing key rotation.
- Audience và recipient.
- Authentication context/class.
- Authentication time.
- MFA/UV claim semantics.
- LoA/AAL mapping theo agreement.
- Assertion expiry và replay state.
- User/subject identifier.
- Attribute release policy.
- Logout/revocation semantics.

### 15.1. Không tin claim không được bảo đảm

Nếu IdP gửi claim mfa=true, RP cần biết:
- MFA được định nghĩa như thế nào ở IdP?
- Factor có độc lập không?
- Có phishing resistance không?
- Có user verification không?
- Claim phản ánh lần auth hiện tại hay trạng thái account?
- Issuer có được đánh giá và hợp đồng hóa không?

Nếu không có mapping đáng tin, không nâng assurance chỉ từ tên claim.

### 15.2. Authentication time và max_age

OIDC có thể dùng auth_time và max_age để kiểm tra lần xác thực gần nhất. RP phải xác minh token và claim theo protocol. Token refresh không nhất thiết tạo một lần xác thực mới; không cập nhật auth_time giả tạo để vượt freshness requirement.

## 16. Workload và service-to-service assurance

Không phải mọi principal đều là con người. Workload identity cần assurance phù hợp với service-to-service threat model.

Yêu cầu có thể gồm:
- Private key hoặc workload credential được quản lý an toàn.
- Mutual TLS hoặc signed token theo profile.
- Issuer/audience hẹp.
- Short-lived credential.
- Rotation và revocation.
- Request binding hoặc proof-of-possession.
- Workload identity attestation nếu cần.
- Least privilege theo service/action.
- Audit và owner của workload.

Không yêu cầu MFA con người cho một service account theo nghĩa thông thường. Thay vào đó, kiểm tra nguồn gốc workload, key protection, runtime identity, issuance và quyền. Không dùng static API key dài hạn nếu có thể dùng short-lived workload credential.

## 17. Recovery và assurance continuity

Recovery có thể làm suy yếu assurance nếu attacker dùng kênh dễ chiếm quyền để thay authenticator. Quy trình cần duy trì mức tin cậy phù hợp sau khi user mất thiết bị hoặc factor.

Cần định nghĩa:
- Bằng chứng thay thế khi mất authenticator.
- Có cần identity proofing lại không.
- Recovery delay cho action rủi ro cao.
- Notification tới kênh đã xác minh.
- Revoke authenticator cũ và session liên quan.
- Step-up sau recovery.
- Thời gian hạn chế một số action sau khi recovery.
- Support-assisted recovery và dual control.
- Audit, dispute và rollback.

Không coi email reset link là tương đương passkey phishing-resistant. Không cho phép recovery channel yếu hơn âm thầm nâng lại quyền của authenticator mạnh.

### 17.1. Recovery event có thể làm giảm trust

Sau recovery, policy có thể:
- Thu hồi mọi session.
- Yêu cầu đăng nhập lại.
- Hạn chế thay đổi recovery/financial action trong một khoảng thời gian.
- Yêu cầu đăng ký authenticator mới.
- Gửi notification và mở dispute window.
- Yêu cầu step-up bổ sung.

Các biện pháp phải dựa trên risk và không tạo rào cản không cần thiết cho người dùng hợp lệ.

## 18. Assurance requirement dưới dạng policy

Yêu cầu nên được biểu diễn thành dữ liệu có thể đánh giá, không chỉ mô tả trong tài liệu.

Một policy minh họa:

~~~yaml
policy_id: sensitive-recovery-change
subject:
  type: human
action:
  name: change_recovery_contact
  resource: account.security_settings
minimum_assurance:
  authentication_profile: phishing_resistant
  user_verification: required
  max_authentication_age_seconds: 300
  replay_resistance: required
  transaction_binding: required
allowed_authenticators:
  - webauthn_passkey
  - hardware_security_key
federation:
  trusted_issuers:
    - approved-enterprise-idp
  minimum_context: approved_recent_authentication
session:
  must_be_active: true
  revoke_on_completion: according_to_policy
fallback:
  mode: recovery_workflow
  silent_downgrade: false
audit:
  required: true
  include_secret_material: false
~~~

Đây là ví dụ khái niệm, không phải schema tiêu chuẩn. Tên field, enum và cách biểu diễn phải phù hợp policy engine thực tế.

### 18.1. Policy evaluation input

PDP có thể nhận:
- Subject/principal và tenant.
- Action/resource.
- Current authentication context.
- Credential type và assurance attributes.
- Authentication time.
- Session status.
- Risk signals.
- Federation issuer/context.
- Device/workload posture.
- Policy version.

PDP cần trả outcome có lý do:
- Permit.
- Deny.
- Step-up required.
- Reauthentication required.
- Recovery required.
- Indeterminate/dependency unavailable.

Indeterminate không phải permit. Client không được tự gửi một assurance level rồi yêu cầu server tin giá trị đó.

### 18.2. Policy versioning

Khi assurance requirement thay đổi, cần version và migration plan. Session được tạo theo policy cũ có thể cần reauthentication hoặc được chấp nhận trong thời gian chuyển tiếp. Ghi lại policy version đã quyết định để điều tra.

## 19. Assurance failure và downgrade handling

Một request có thể không đạt requirement vì:
- Authenticator không được phép.
- User verification thiếu.
- Authentication quá cũ.
- Challenge hết hạn hoặc replay.
- Issuer không tin cậy.
- Federation context không đủ.
- Key bị revoke.
- Session đã hết hạn.
- Device/workload evidence stale.
- Policy engine không thể đưa ra quyết định.

Hệ thống phải phân biệt:
- **Deny:** bằng chứng đã được kiểm tra và không đạt.
- **Step-up:** có thể đáp ứng bằng authenticator mạnh hơn.
- **Reauthentication:** context cũ hoặc không đủ fresh.
- **Recovery:** authenticator không còn dùng được.
- **Indeterminate:** dependency hoặc evidence cần thiết không sẵn sàng.

Không hạ assurance tự động để cải thiện conversion. Nếu có fallback, ghi rõ điều kiện, phạm vi action, người phê duyệt và thời hạn. Với action critical, có thể từ chối cho tới khi có bằng chứng mới.

## 20. Logging, audit và privacy của assurance

Audit cần chứng minh policy được thực thi mà không lưu secret.

Có thể ghi:
- Principal reference.
- Action/resource category.
- Authentication method category.
- Assurance profile/level được đánh giá.
- User verification/phishing resistance flags theo evidence tin cậy.
- Authentication time và freshness result.
- Issuer reference.
- Policy ID/version.
- Decision: permit/deny/step-up/indeterminate.
- Reason code.
- Correlation/transaction reference.
- Timestamp và actor.

Không ghi:
- Password, OTP, recovery code.
- Private key hoặc token thô.
- Biometric template/ảnh.
- Full WebAuthn assertion nếu không cần.
- Session cookie hoặc reset link.

Assurance claim có thể là dữ liệu nhạy cảm vì nó mô tả trạng thái bảo mật account. Giới hạn ai có thể xem, retention và khả năng liên kết. Không dùng metric label theo user hoặc session.

## 21. Kiểm thử assurance requirement

| Test case | Kết quả mong đợi |
| --- | --- |
| Public action không cần identity | Không bắt buộc login ngoài policy |
| Read personal data với session hợp lệ | Permit nếu audience, scope và authorization đúng |
| Session hết hạn | Reauthenticate |
| Authentication quá max age | Step-up/reauth theo action |
| Password-only cho action phishing-resistant | Deny hoặc yêu cầu authenticator phù hợp |
| Password + OTP bị phishing relay | Không tuyên bố đạt phishing-resistant requirement |
| Passkey với RP ID/origin sai | Từ chối assertion |
| Passkey thiếu UV khi policy yêu cầu | Từ chối |
| Challenge đã dùng | Từ chối replay |
| Challenge hết hạn | Từ chối |
| Transaction body thay đổi | Digest/binding mismatch |
| Credential đã revoke | Từ chối |
| Device key không đúng principal | Từ chối |
| Certificate hết hạn/revoked | Từ chối |
| Wrong issuer/audience | Từ chối |
| OIDC nonce/state mismatch | Từ chối callback |
| Federation context không được map | Không nâng assurance |
| Token refresh nhưng không có login mới | Không làm mới authentication time giả tạo |
| Recovery qua kênh yếu | Không âm thầm khôi phục assurance cao |
| Recovery hoàn tất | Revoke/limit session và notify theo policy |
| PDP indeterminate | Không permit mặc định |
| Risk signal missing | Không coi là low risk |
| Clock skew | Freshness/expiry xử lý theo tolerance đã định |
| Workload key rotation | Key cũ/new overlap theo policy |
| Policy version thay đổi | Session/context cũ được xử lý theo migration |
| Audit inspection | Có decision evidence, không có secret |
| Client tự khai AAL cao | Server bỏ qua claim không đáng tin |
| Step-up thành công | Context mới gắn đúng action và transaction |

### 21.1. Kiểm thử theo chiều assurance

Tách test:
- IAL: proofing source, evidence validation, identity binding, re-proofing và correction.
- AAL: authenticator, factor independence, user verification, phishing/replay resistance, freshness và lifecycle.
- FAL: issuer, signature, audience, recipient, assertion expiry, correlation và replay.

Không dùng một bài test login pass/fail để kết luận cả ba chiều đều đạt.

### 21.2. Kiểm thử negative và downgrade

Thử cố tình cung cấp evidence thiếu, cũ, sai issuer, sai audience, sai RP ID, token replay hoặc factor không được phép. Kiểm tra server trả đúng outcome và không có side effect. Test cả trường hợp dependency timeout để bảo đảm unknown không biến thành permit.

### 21.3. Kiểm thử UX và accessibility

Assurance policy phải có cách hoàn thành cho người dùng hợp lệ:
- Authenticator không khả dụng.
- Mất security key.
- Thiết bị mới.
- Người dùng cần công nghệ hỗ trợ.
- Network/provider outage.
- Account recovery.

Đo completion rate, false denial, recovery time và support burden. Accessibility không có nghĩa hạ yêu cầu bảo mật âm thầm; cần lựa chọn authenticator/fallback phù hợp và được review.

## 22. Ví dụ: yêu cầu assurance cho chuyển tiền

Một ứng dụng tài chính cho phép người dùng xem số dư sau khi đăng nhập. Chuyển tiền tới người nhận mới có impact cao hơn và cần assurance mới, chống phishing cùng transaction binding.

Flow:
1. User đăng nhập và nhận session với context được lưu phía server.
2. User tạo lệnh chuyển tiền.
3. Policy engine phân loại recipient mới và amount vượt ngưỡng.
4. Policy yêu cầu phishing-resistant authenticator, user verification và authentication freshness.
5. Server tạo challenge gắn principal, transaction ID, amount, currency và recipient.
6. User xác minh bằng passkey/security key được chấp nhận.
7. Server xác minh assertion, challenge, RP ID/origin, UV, credential status và transaction digest.
8. Authorization kiểm tra balance, ownership, limit, sanctions/fraud policy và quyền.
9. Transaction được commit idempotently.
10. Audit ghi assurance profile, policy version, decision và transaction reference.
11. Notification được gửi theo policy.

~~~mermaid
flowchart TD
    A[User requests transfer] --> B[Classify action and risk]
    B --> C{Assurance already sufficient and fresh?}
    C -- No --> D[Require step-up]
    D --> E[Phishing-resistant authenticator + UV]
    E --> F[Verify challenge and transaction binding]
    C -- Yes --> G[Check current context]
    F --> H{Evidence valid?}
    G --> H
    H -- No --> X[Deny or recover]
    H -- Yes --> I[Authorization and business controls]
    I --> J{Permit?}
    J -- No --> X
    J -- Yes --> K[Commit transaction and audit]
~~~

Một passkey assertion hợp lệ không tự cho phép chuyển tiền. Nó chỉ cung cấp evidence authentication; authorization và business controls vẫn phải được thực thi.

## 23. Checklist review

| Câu hỏi | Dấu hiệu thiết kế tốt |
| --- | --- |
| Assurance dimension được xác định? | IAL, AAL, FAL tách riêng |
| Framework/version được nêu? | Có standard/profile và owner |
| Risk gắn với action? | Ma trận impact và yêu cầu cụ thể |
| Factor independence được đánh giá? | Không chỉ đếm prompt |
| Phishing resistance có kiểm tra? | Verifier/RP binding và authenticator phù hợp |
| Replay resistance có đủ? | Challenge one-time, expiry và atomic consume |
| User verification có phân biệt? | UV khác UP và biometric disclosure |
| Authenticator lifecycle được quản lý? | Enrollment, rotation, revoke và recovery |
| Session có freshness policy? | Idle/absolute timeout và max auth age |
| Step-up có action binding? | Context mới gắn principal/action/transaction |
| Federation issuer được tin cậy? | Signature, issuer, audience và context mapping |
| Recovery không downgrade? | Proofing, delay, notification và audit |
| Workload identity có profile riêng? | Key, issuer, audience, scope và rotation |
| Policy có outcome rõ? | Permit/deny/step-up/recovery/indeterminate |
| Unknown có thành permit? | Không |
| Audit có đủ evidence? | Policy version, method, result và reason |
| Privacy được bảo vệ? | Không log secret/biometric và retention rõ |
| Có negative tests? | Replay, stale, wrong issuer, wrong RP và revoked key |
| UX/accessibility được đo? | False denial, completion và recovery time |

### Tình huống tự kiểm tra

**Tình huống 1:** Người dùng đã proofing danh tính ở mức cao. Có thể coi mọi lần đăng nhập sau đó đều có authentication assurance cao không?

**Trả lời:** Không. IAL mô tả độ tin cậy của identity proofing; AAL mô tả lần authentication. Cần đánh giá authenticator và session hiện tại.

**Tình huống 2:** Login yêu cầu password và OTP. Có thể tự động tuyên bố phishing-resistant không?

**Trả lời:** Không. OTP có thể bị relay trong phishing real-time. Nếu action yêu cầu phishing resistance, cần authenticator/protocol có verifier binding phù hợp.

**Tình huống 3:** RP nhận ID Token có chữ ký hợp lệ và claim mfa=true. Đã đủ để chấp nhận assurance cao chưa?

**Trả lời:** Chưa. Cần tin cậy issuer, kiểm tra audience/expiry/nonce và hiểu semantics của claim MFA theo agreement. Chữ ký không tự xác minh cách IdP thực hiện MFA.

**Tình huống 4:** Access token được refresh thành công. Authentication time có được cập nhật thành thời điểm refresh không?

**Trả lời:** Không tự động. Refresh token exchange không nhất thiết là user authentication mới. Giữ auth_time theo lần xác thực thực sự.

**Tình huống 5:** Một passkey assertion hợp lệ được gửi cho giao dịch chuyển tiền. Có thể bỏ qua authorization không?

**Trả lời:** Không. Assertion chứng minh credential đã ký challenge theo protocol. Server vẫn kiểm tra quyền, ownership, balance, limits và transaction policy.

**Tình huống 6:** MFA provider timeout trong lúc step-up. Có thể fallback SMS dù policy yêu cầu phishing resistance không?

**Trả lời:** Không âm thầm. Chỉ dùng fallback được policy chấp nhận với thuộc tính tương đương; nếu không, từ chối tạm thời hoặc chạy recovery được kiểm soát.

**Tình huống 7:** Account recovery hoàn tất bằng email link. Assurance cao trước đó có tự động được giữ nguyên không?

**Trả lời:** Không. Recovery là một trust transition. Cần đánh giá proofing, revoke authenticator/session cũ và thiết lập lại assurance theo policy.

**Tình huống 8:** Một service account ký JWT bằng private key. Có cần gán AAL của con người cho workload không?

**Trả lời:** Không. Dùng workload identity assurance profile riêng, đánh giá key protection, issuer, audience, scope, rotation và runtime binding.

## 24. Ghi nhớ

**Assurance requirement chuyển mức rủi ro của một hành động thành yêu cầu bằng chứng xác thực có thể thực thi và kiểm thử.** Tách IAL cho identity proofing, AAL cho authentication và FAL cho federation. Không cộng các chiều thành điểm số, không suy ra assurance chỉ từ số factor, tên sản phẩm hoặc claim client tự khai.

Một policy cần chỉ rõ authenticator được phép, phishing/replay resistance, user verification, freshness, session lifetime, step-up, transaction binding, federation trust, recovery và hành vi khi evidence thiếu. Authentication mạnh không thay authorization; passkey hợp lệ không tự cho phép giao dịch. Ghi lại policy version và decision evidence mà không lưu secret. Kiểm thử cả positive, negative, downgrade, replay, outage, recovery và accessibility để bảo đảm mức assurance được duy trì trong toàn bộ vòng đời account.
