# Device binding — Liên kết thiết bị với tài khoản và phiên xác thực

## 1. Device binding là gì?

**Device binding** (liên kết thiết bị) là quá trình gắn một thiết bị hoặc một khóa mật mã được tạo trên thiết bị với một tài khoản, ứng dụng hoặc phiên xác thực. Sau khi liên kết, server có thể yêu cầu thiết bị chứng minh quyền kiểm soát khóa riêng tương ứng trước khi cho phép một số thao tác. Mục tiêu là nhận biết một thiết bị đã được đăng ký và giảm nguy cơ kẻ khác chỉ sao chép mật khẩu hoặc token rồi sử dụng từ một thiết bị khác.

Ví dụ: người dùng đăng nhập ứng dụng ngân hàng bằng passkey. Ứng dụng tạo một cặp khóa riêng/public key trong vùng lưu trữ an toàn của hệ điều hành. Server lưu public key cùng tài khoản và định danh binding. Ở những lần truy cập sau, server gửi challenge; ứng dụng yêu cầu thiết bị ký challenge bằng private key. Server xác minh chữ ký và trạng thái binding trước khi tiếp tục.

Trong chương **Authentication trong mobile** của module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, device binding kết nối credential, mật khẩu, MFA, passkey, chứng chỉ, token, session, liên kết danh tính và khôi phục tài khoản. Người học cần hiểu ranh giới tin cậy giữa app, hệ điều hành, phần cứng bảo vệ khóa, server và người dùng; phòng chống phishing, replay, giả mạo thiết bị và lạm dụng đăng nhập.

**Device binding không tự chứng minh người đang cầm thiết bị là chủ tài khoản.** Nó chứng minh một bên đang kiểm soát khóa hoặc authenticator đã liên kết, trong phạm vi mà hệ thống có thể tin cậy. Người dùng vẫn cần authentication phù hợp; ứng dụng vẫn cần authorization cho từng hành động.

## 2. Device binding khác device fingerprinting như thế nào?

Hai khái niệm thường bị nhầm:

| Khái niệm | Cách hoạt động | Giá trị bảo mật và giới hạn |
| --- | --- | --- |
| **Device binding** | Liên kết tài khoản với credential/khóa mật mã trên thiết bị; thiết bị chứng minh quyền kiểm soát private key. | Có bằng chứng mật mã có thể xác minh; phụ thuộc bảo vệ khóa, enrollment và trạng thái thu hồi. |
| **Device fingerprinting** | Kết hợp tín hiệu như model, OS, browser, IP, font hoặc thuộc tính môi trường để tạo dấu hiệu nhận diện. | Chỉ là tín hiệu xác suất; có thể thay đổi, giả mạo, trùng lặp và gây rủi ro quyền riêng tư. |
| **Device attestation** | Nền tảng cung cấp bằng chứng về app/device/key theo một cơ chế attestation. | Có thể tăng độ tin cậy về môi trường hoặc nguồn gốc khóa; không chứng minh tuyệt đối người dùng hay thiết bị không bị xâm nhập. |
| **Device posture** | Đánh giá trạng thái quản lý và bảo vệ thiết bị, ví dụ OS version hoặc chính sách MDM. | Hữu ích cho risk policy nếu nguồn posture được xác minh; không thay thế user authentication. |

Không dùng fingerprint làm khóa định danh bảo mật duy nhất. IP, user agent, model, kích thước màn hình hoặc advertising ID có thể thay đổi và không chứng minh quyền kiểm soát một bí mật. Device binding dựa trên khóa mật mã mạnh hơn, nhưng vẫn cần kiểm tra credential status, account status và policy.

## 3. Device binding giải quyết vấn đề nào?

Một binding được thiết kế đúng có thể hỗ trợ:

- Chứng minh một request đến từ bên giữ private key đã đăng ký.
- Giảm nguy cơ token bearer bị sao chép rồi dùng trên thiết bị khác, nếu token hoặc request được ràng buộc với khóa.
- Nhận biết thiết bị đã đăng ký để áp dụng policy hoặc giảm ma sát đăng nhập.
- Hỗ trợ xác minh lại trước hành động nhạy cảm.
- Quản lý danh sách thiết bị và thu hồi khóa khi mất thiết bị.
- Phân biệt thiết bị cá nhân, thiết bị doanh nghiệp và workload theo policy.

Device binding không tự giải quyết:

- Mật khẩu bị phishing trước khi thiết bị được liên kết.
- Malware điều khiển app hoặc thiết bị hợp lệ để ký request thay attacker.
- Người dùng bị lừa phê duyệt thao tác trên thiết bị đã đăng ký.
- Recovery yếu cho phép attacker liên kết thiết bị của họ.
- Session/token cũ vẫn còn hiệu lực sau khi binding bị thu hồi.
- Lạm dụng quyền trong ứng dụng sau khi xác thực thành công.

Vì vậy, binding là một thành phần của authentication architecture, không phải một cơ chế thay thế MFA, authorization, session management hoặc incident response.

## 4. Mô hình ranh giới tin cậy

Một luồng device binding thường gồm người dùng, mobile app, hệ điều hành, phần cứng bảo vệ khóa và server:

~~~mermaid
flowchart LR
    U["Người dùng"]
    APP["Mobile app"]
    OS["OS keystore<br/>Keychain / Keystore"]
    HW["Secure hardware<br/>nếu có"]
    API["Binding API / Identity server"]
    DB[("Credential registry<br/>public key + status")]
    RP["Resource server"]
    U <--> APP
    APP <--> OS
    OS <--> HW
    APP <--> API
    API <--> DB
    APP -->|"Proof-of-possession request"| RP
    RP <--> DB
~~~

Mobile app điều phối thao tác nhưng không nên đọc hoặc xuất private key. Hệ điều hành cung cấp API quản lý khóa; phần cứng bảo mật có thể thực hiện ký bên trong vùng bảo vệ. Server tạo challenge, xác minh proof và lưu trạng thái binding.

Các ranh giới cần xem xét:

- **App process:** có thể bị instrument, debug, hook hoặc điều khiển trên thiết bị đã compromise.
- **OS keystore:** bảo vệ key theo khả năng nền tảng và cấu hình; không phải mọi key đều hardware-backed.
- **Secure hardware:** giảm khả năng trích xuất key, nhưng không ngăn malware yêu cầu ký khi thiết bị đang hoạt động.
- **Network:** request và response phải được bảo vệ bằng TLS; proof cần ràng buộc đúng request.
- **Server registry:** là nguồn authoritative cho public key, trạng thái, owner và policy.
- **User interaction:** người dùng cần hiểu lúc nào đang đăng ký thiết bị hoặc phê duyệt thao tác nhạy cảm.

Không tin trạng thái binding do app tự khai như trusted_device=true. Server phải tự xác minh proof và tra trạng thái credential.

## 5. Các thành phần của một device binding

Một bản ghi binding có thể chứa:

| Trường | Mục đích |
| --- | --- |
| Binding ID | Định danh bản ghi liên kết duy nhất ở server. |
| Principal/subject | Tài khoản hoặc danh tính sở hữu binding. |
| Tenant | Phạm vi tổ chức nếu hệ thống multi-tenant. |
| Credential/key ID | Chọn public key hoặc credential đã đăng ký. |
| Public key | Xác minh chữ ký proof-of-possession. |
| Key algorithm/parameters | Xác định thuật toán và loại khóa được phép. |
| Platform/app metadata | OS, app version, app identifier ở mức cần thiết. |
| Attestation reference | Kết quả hoặc metadata attestation nếu policy sử dụng. |
| Created/last-used time | Hỗ trợ quản lý vòng đời và điều tra. |
| Status/version | Pending, active, suspended, revoked hoặc replaced. |
| Risk/policy labels | Phân loại theo policy, không phải khẳng định tuyệt đối về thiết bị. |

Không lưu private key ở server. Không lưu dữ liệu sinh trắc học thô. Metadata thiết bị cần được giảm thiểu để tránh tạo kho theo dõi người dùng quá mức.

## 6. Tạo khóa trên thiết bị mobile

Ứng dụng nên tạo key pair bằng API mật mã và kho khóa của nền tảng, thay vì tự sinh private key rồi lưu vào file, preferences hoặc database ứng dụng.

### Android

Android Keystore cho phép ứng dụng tạo và sử dụng khóa mà private key có thể không xuất được khỏi môi trường quản lý khóa. Tùy thiết bị và cấu hình, khóa có thể được bảo vệ bằng software-backed keystore, Trusted Execution Environment (TEE) hoặc StrongBox. Ứng dụng cần kiểm tra security level thực tế và không giả định mọi thiết bị đều có phần cứng bảo mật.

Các điểm cần xem xét:

- Chọn thuật toán/key size được nền tảng và server hỗ trợ.
- Đặt key purpose, digest và padding allowlist rõ ràng.
- Cấu hình yêu cầu user authentication nếu policy cần người dùng mở khóa thao tác ký.
- Xử lý key invalidation khi thay đổi sinh trắc/PIN theo chính sách của key.
- Nếu cần attestation, kiểm tra chain và security properties ở server theo policy.
- Không xuất private key hoặc đưa key material vào log/crash report.

### iOS

Ứng dụng có thể dùng Keychain và Secure Enclave cho các loại khóa được nền tảng hỗ trợ. Secure Enclave có thể tạo và sử dụng private key mà ứng dụng không đọc được trực tiếp. Keychain access control có thể yêu cầu passcode hoặc user presence/biometric theo policy.

Các điểm cần xem xét:

- Chọn key type và access control phù hợp.
- Cân nhắc ThisDeviceOnly khi credential không nên di chuyển qua backup/restore.
- Xử lý trường hợp key không còn khả dụng sau khi đổi passcode, sinh trắc hoặc thay đổi thiết bị.
- Phân biệt key dùng cho device binding với passkey/WebAuthn do hệ sinh thái quản lý.
- Không coi Face ID/Touch ID là dữ liệu được gửi tới server; xác minh sinh trắc diễn ra cục bộ và chỉ kết quả mở khóa thao tác được thể hiện qua hành vi của authenticator.

### Không phải mọi khóa đều hardware-backed

Thiết bị cũ, emulator, cấu hình OS hoặc API khác nhau có thể cung cấp mức bảo vệ khác nhau. Server cần nhận và đánh giá attestation/security level nếu policy yêu cầu; nếu không có bằng chứng, áp dụng mức assurance thấp hơn hoặc từ chối các hành động cần thiết bị bảo vệ phần cứng.

Không tự suy luận hardware-backed chỉ từ model thiết bị, OS version hoặc một cờ do app gửi.

## 7. Quy trình đăng ký device binding

Một luồng enrollment tham khảo:

1. Người dùng đăng nhập bằng phương thức hiện có và hoàn tất step-up nếu policy yêu cầu.
2. App yêu cầu server tạo enrollment transaction gắn với principal, tenant, session, purpose và expiry.
3. Server trả challenge ngẫu nhiên cùng thông tin transaction.
4. App yêu cầu OS keystore tạo key pair; private key được giữ trong vùng lưu trữ phù hợp.
5. App gửi public key, key metadata và attestation nếu policy yêu cầu.
6. Server kiểm tra transaction, challenge, app/platform evidence và quyền đăng ký.
7. Server lưu public key ở trạng thái pending.
8. App ký challenge hoặc một nonce xác nhận possession bằng private key.
9. Server xác minh proof, consume challenge và kích hoạt binding nguyên tử.
10. Server thông báo thiết bị mới đã được liên kết.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant A as Mobile app
    participant K as OS keystore
    participant S as Binding server
    U->>A: Chọn liên kết thiết bị
    A->>S: Bắt đầu enrollment sau step-up
    S-->>A: Transaction ID + challenge
    A->>K: Tạo key pair
    K-->>A: Public key + key reference
    A->>S: Public key + metadata/attestation
    S->>S: Kiểm tra transaction và policy
    S-->>A: Challenge xác nhận possession
    A->>K: Ký challenge
    K-->>A: Signature
    A->>S: Proof-of-possession
    S->>S: Verify và consume challenge
    S->>S: Activate binding
    S-->>A: Binding active
~~~

Không kích hoạt chỉ vì app đã gửi public key. Server phải xác minh người gửi có quyền kiểm soát private key tương ứng và transaction vẫn hợp lệ.

## 8. Challenge và proof-of-possession

Challenge phải được tạo bằng CSPRNG, khó đoán, có thời hạn ngắn và dùng một lần. Nó cần được ràng buộc với:

- Binding enrollment hoặc request cụ thể.
- Principal và tenant.
- Session đã xác minh.
- Purpose: enroll, authenticate, approve action hoặc recover.
- Audience/server dự kiến.
- Thời hạn và transaction state.

Proof nên bao phủ challenge cùng ngữ cảnh quan trọng. Ví dụ:

~~~text
proof_payload =
    protocol_version
    || challenge
    || transaction_id
    || principal_reference
    || tenant_reference
    || audience
    || purpose
    || timestamp

signature = Sign(device_private_key, proof_payload)
~~~

Server kiểm tra chữ ký bằng public key đã đăng ký hoặc public key đang chờ enrollment, sau đó consume challenge nguyên tử. Không chấp nhận cùng một challenge lần thứ hai. Không cho client đổi purpose hoặc audience sau khi server đã tạo transaction.

Trong request thực tế, cần canonicalization rõ ràng và tránh đưa dữ liệu cá nhân không cần thiết vào payload ký. Challenge không cần bí mật sau khi phát hành; giá trị của nó nằm ở tính không đoán được, one-time use và ràng buộc giao dịch.

## 9. Xác thực request bằng khóa đã liên kết

Sau enrollment, server có thể yêu cầu app ký request hoặc challenge mới để chứng minh possession. Proof-of-possession có thể bao phủ:

- Key ID và binding ID.
- Session hoặc token reference.
- HTTP method và canonical path.
- Body hash.
- Audience/resource.
- Sequence number hoặc nonce.
- Timestamp.
- Purpose/action.

~~~text
canonical_request =
    key_id
    || binding_id
    || session_id
    || sequence_number
    || timestamp
    || method
    || canonical_path
    || audience
    || SHA256(body)

proof = Sign(device_private_key, canonical_request)
~~~

Server xác minh signature, credential status, timestamp/nonce/sequence và authorization trước khi xử lý. Nếu dùng sequence number, replay state phải được lưu và cập nhật nguyên tử. Nếu dùng nonce, nonce phải được consume một lần. Không chỉ kiểm tra chữ ký rồi chấp nhận cùng một request vô hạn.

## 10. Device binding và token/session binding

Access token kiểu bearer có thể được sử dụng bởi bất kỳ bên nào nắm giữ token, nếu resource server chấp nhận nó. Device binding có thể bổ sung proof-of-possession để giảm rủi ro token bị sao chép đơn thuần.

Các cách triển khai có thể gồm:

- **DPoP:** client tạo proof JWT bằng private key cho request/token theo profile DPoP; server kiểm tra proof, method, URI, thời gian, jti và ràng buộc token.
- **mTLS-bound token:** token gắn với client certificate; phù hợp hơn với một số workload hoặc môi trường có TLS client certificate.
- **Application-specific request signing:** app ký request bằng key đã đăng ký, với protocol canonicalization và replay defense được thiết kế rõ.

Không tự gọi một token là device-bound chỉ vì app lưu token trong Keychain/Keystore. Token vẫn có thể là bearer token nếu resource server không yêu cầu proof tương ứng.

### Bảo vệ session

Ứng dụng có thể giữ refresh token trong kho an toàn của OS và yêu cầu proof bằng khóa thiết bị khi refresh hoặc gọi API. Server cần ràng buộc token family với binding/key ID và thu hồi khi thiết bị bị mất. Chỉ lưu token trong secure storage không ngăn malware điều khiển app hợp lệ sử dụng token.

## 11. Attestation: bằng chứng về app và thiết bị

Attestation là một dạng bằng chứng do nền tảng hoặc phần cứng tạo ra để giúp server đánh giá nguồn gốc khóa, app instance hoặc trạng thái môi trường. Attestation không đồng nghĩa với device binding và cũng không chứng minh tuyệt đối thiết bị không bị compromise.

### Android

Android Key Attestation có thể cung cấp chứng thư attestation mô tả thuộc tính của khóa và môi trường tạo khóa. Server cần xác minh certificate chain, challenge, application identity và security level theo hướng dẫn nền tảng, đồng thời xử lý root of trust, patch level và chính sách thiết bị.

Google Play Integrity có thể cung cấp verdict về app/device integrity theo điều kiện dịch vụ. Verdict cần được xác minh ở backend và diễn giải theo policy; không tin payload do client tự khai hoặc cache vô thời hạn.

### Apple

App Attest cho phép server xác minh một app instance thông qua key và attestation/assertion theo cơ chế của Apple. DeviceCheck cung cấp tín hiệu thiết bị theo một mục đích khác. Cần dùng đúng API, xác minh challenge và assertion ở server, quản lý counter/anti-replay theo đặc tả.

App Attest không phải một chứng chỉ phổ quát chứng minh mọi thuộc tính phần cứng của thiết bị. Nó hỗ trợ đánh giá app instance và tính toàn vẹn trong phạm vi dịch vụ cung cấp.

### Cách sử dụng an toàn

- Xác minh attestation ở backend, không chỉ ở client.
- Kiểm tra challenge freshness và chống replay.
- Pin trust roots/metadata theo hướng dẫn nền tảng và có quy trình rotation.
- Xử lý trường hợp không hỗ trợ attestation theo policy, không tự nâng assurance.
- Không thu thập metadata quá mức cần thiết.
- Có chiến lược cho emulator, thiết bị cũ, thiết bị doanh nghiệp và môi trường accessibility.
- Định kỳ cập nhật verifier khi nền tảng thay đổi chain, API hoặc semantics.

## 12. Device binding không thay thế user authentication

Thiết bị đã liên kết có thể được mượn, bị đánh cắp hoặc bị điều khiển từ xa. Việc app ký thành công chứng minh private key có thể được sử dụng, nhưng không nhất thiết chứng minh người dùng đang hiện diện hoặc có ý định thực hiện thao tác.

Có thể kết hợp:

- Local user verification bằng PIN/biometric để mở khóa thao tác ký.
- Passkey/WebAuthn với user verification theo policy.
- Reauthentication/step-up cho hành động nhạy cảm.
- Transaction confirmation hiển thị rõ dữ liệu người dùng sắp phê duyệt.
- Risk-based authentication và session freshness.

Sinh trắc học thường được xác minh cục bộ bởi OS/authenticator. Server không cần và không nên nhận ảnh vân tay hoặc dữ liệu khuôn mặt thô. Server nhận kết quả của giao thức xác thực hoặc proof được tạo sau khi thao tác cục bộ được cho phép.

Không coi một lần mở khóa điện thoại từ nhiều giờ trước là bằng chứng đủ cho mọi giao dịch. Policy có thể yêu cầu user verification mới hoặc xác thực lại.

## 13. Mobile OAuth/OIDC và device binding

Ứng dụng mobile thường là **public client**: binary được cài trên thiết bị người dùng nên không thể giữ client secret tĩnh như confidential server. Với OAuth/OIDC:

- Dùng Authorization Code Flow với PKCE.
- Thực hiện đăng nhập qua external user-agent theo hướng dẫn cho native apps.
- Dùng redirect URI đã đăng ký và xác minh state/nonce.
- Không nhúng client secret vào app.
- Bảo vệ token trong OS secure storage và giảm thời gian lưu khi phù hợp.
- Dùng sender-constrained token hoặc request signing nếu server và SDK hỗ trợ.
- Ràng buộc binding với đúng issuer, client, audience và account.

Device binding không thay thế PKCE. PKCE bảo vệ authorization code trong luồng OAuth; device binding chứng minh quyền kiểm soát khóa đã đăng ký cho các request hoặc session cụ thể. Hai cơ chế giải quyết các rủi ro khác nhau.

Không đặt access token hoặc refresh token trong URL, clipboard, analytics hoặc log. Không dùng custom embedded webview để thu mật khẩu IdP. Nếu app dùng BFF hoặc backend trung gian, phải xác định rõ binding ở phía mobile, backend và resource server.

## 14. Device binding trong multi-device và multi-tenant

Một tài khoản có thể liên kết nhiều thiết bị. Mỗi thiết bị nên có binding/key riêng để có thể thu hồi độc lập:

| Thiết kế | Ưu điểm | Rủi ro/đánh đổi |
| --- | --- | --- |
| Một key cho mỗi thiết bị/app installation | Thu hồi và audit từng thiết bị. | Cần quản lý inventory và lifecycle. |
| Một key dùng chung trên nhiều thiết bị | Triển khai đơn giản hơn trong một số hệ thống. | Khó xác định thiết bị nào bị lộ; blast radius lớn. |
| Một binding cho mỗi tenant/client | Tách phạm vi tổ chức và ứng dụng. | Cần kiểm tra tenant membership và audience chặt chẽ. |

Không dùng chung key giữa người dùng, tenant hoặc môi trường production/staging. Key ID không phải bí mật, nhưng phải được ràng buộc với đúng owner và scope ở server.

### Device inventory

Giao diện quản lý thiết bị có thể hiển thị:

- Tên thiết bị do người dùng đặt.
- Nền tảng và phiên bản app ở mức cần thiết.
- Thời điểm liên kết và lần sử dụng gần nhất.
- Trạng thái active/suspended/revoked.
- Các session hoặc credential liên quan nếu policy cho phép.

Không hiển thị public key đầy đủ, attestation certificate chain hoặc metadata nhạy cảm cho người dùng phổ thông nếu không cần. Cho phép người dùng thu hồi thiết bị bị mất qua một phương thức xác minh độc lập.

## 15. Mất thiết bị, thay máy và reinstall

Device binding cần một lifecycle rõ:

### Mất thiết bị

1. Người dùng báo mất qua session hoặc recovery channel còn tin cậy.
2. Server xác minh yêu cầu và suspend/revoke binding cụ thể.
3. Invalidate cache hoặc phát sự kiện tới mọi verifier.
4. Đánh giá session, refresh token và access token được tạo từ binding.
5. Thông báo qua kênh đã xác minh trước đó.
6. Người dùng đăng ký thiết bị mới bằng recovery flow đủ assurance.

Nếu private key có khả năng bị lộ, revoke và tạo key mới. Không resume key cũ chỉ vì người dùng tìm lại điện thoại.

### Thay thiết bị

Thiết bị mới tạo key pair mới và thực hiện enrollment riêng. Không sao chép private key từ thiết bị cũ qua backup hoặc QR nếu kiến trúc không được thiết kế để di chuyển khóa. Sau khi thiết bị mới active, người dùng có thể thu hồi binding cũ.

### Reinstall ứng dụng

Sau khi gỡ và cài lại app, key có thể còn hoặc mất tùy nền tảng, loại storage và backup policy. App phải kiểm tra key reference còn dùng được; nếu không, bắt đầu re-enrollment. Không coi installation ID mới là bằng chứng cùng thiết bị.

### Backup và migration

Nếu key được backup hoặc đồng bộ, cần hiểu semantics và threat model của nền tảng. Với device-bound credential, cân nhắc loại trừ backup hoặc dùng key không di chuyển. Với passkey đồng bộ, đó là mô hình credential khác và cần policy phù hợp; không mô tả nó như một private key chỉ tồn tại trên một thiết bị.

## 16. Suspend, revoke và thay thế binding

Các trạng thái thường dùng:

| Trạng thái | Hành vi verifier |
| --- | --- |
| Pending | Chưa chấp nhận xác thực. |
| Active | Có thể chấp nhận proof nếu các kiểm tra khác đạt. |
| Suspended | Tạm từ chối proof; có thể resume sau review. |
| Revoked | Từ chối vĩnh viễn; cần enrollment mới. |
| Replaced | Binding cũ đã được thay thế; không tự active lại. |
| Expired | Không chấp nhận theo thời hạn hoặc policy. |

Suspension có thể phù hợp khi người dùng vừa báo mất thiết bị và tổ chức cần xác minh thêm. Nếu private key bị compromise, revoke là lựa chọn phù hợp hơn. Resume cần bằng chứng và approval theo risk; không cho client tự bật lại trạng thái.

Khi binding bị thu hồi, cần xem xét:

- Challenge/authentication transaction đang chờ.
- Session và refresh token gắn với binding.
- Access token sender-constrained hoặc token family.
- API key/certificate hoặc credential được tạo từ thiết bị.
- Liên kết tài khoản/tenant được thiết lập trong cùng giai đoạn.

Thu hồi binding không tự động vô hiệu hóa mọi token bearer đã phát hành nếu resource server không kiểm tra trạng thái. Cần TTL, introspection, denylist hoặc security epoch phù hợp.

## 17. Tấn công nhắm vào device binding

| Rủi ro | Kịch bản | Biện pháp |
| --- | --- | --- |
| **Binding hijack** | Attacker dùng session yếu để đăng ký public key của họ vào tài khoản nạn nhân. | Step-up, transaction binding, notification và kiểm tra quyền. |
| **Private key extraction** | Malware/root exploit lấy key nếu key có thể xuất. | OS keystore, hardware-backed key khi cần và kiểm tra attestation. |
| **Authorized signing abuse** | Malware điều khiển app hợp lệ yêu cầu key ký request. | User verification, transaction confirmation, risk checks và giới hạn hành động. |
| **Proof replay** | Attacker phát lại chữ ký/challenge đã quan sát. | Challenge/nonce/sequence one-time, request binding và atomic consume. |
| **Device cloning** | Sao chép app data hoặc key material sang thiết bị khác. | Non-exportable key, attestation theo policy và key riêng mỗi installation. |
| **Root/jailbreak/instrumentation** | Runtime bị hook hoặc kiểm soát. | Integrity signals, risk policy, hạn chế hành động và step-up; không coi detector là tuyệt đối. |
| **Attestation replay** | Gửi lại attestation object cũ. | Challenge mới, xác minh backend và kiểm tra freshness/counter theo đặc tả. |
| **Token theft** | Bearer token bị trích xuất khỏi storage hoặc log. | Secure storage, redaction, sender-constrained token và revoke. |
| **SIM swap/recovery abuse** | Attacker chiếm kênh recovery để bind thiết bị mới. | Recovery assurance độc lập, cooldown và thông báo kênh cũ. |
| **Stale binding cache** | Node tiếp tục tin key đã revoke. | Status version, invalidation, TTL và propagation SLA. |
| **Device sharing** | Người khác dùng thiết bị đã bind và được mở khóa. | Local user verification, session policy và transaction confirmation. |
| **Privacy overcollection** | Thu thập fingerprint/attestation quá mức. | Data minimization, retention, purpose limitation và access control. |

Root/jailbreak detection chỉ là tín hiệu rủi ro. Nó có thể bị bypass và cũng có thể đánh dấu nhầm thiết bị hợp lệ. Không dựa duy nhất vào một cờ integrity do client gửi.

## 18. Mã giả: enrollment và xác minh proof

Mã giả sau minh họa thứ tự kiểm tra ở mức khái niệm, không thay thế API keystore, attestation hoặc thư viện chữ ký đã được kiểm thử:

~~~text
beginDeviceBinding(session):
    principal = requireActivePrincipal(session)
    require recentStepUpIfPolicyRequires(principal)

    tx = createOneTimeTransaction(
        principalId = principal.id,
        tenantId = principal.tenantId,
        sessionId = session.id,
        purpose = "device_binding_enroll",
        challenge = secureRandomChallenge(),
        expiresAt = shortExpiry()
    )
    return tx.publicOptions

completeDeviceBinding(txId, publicKey, keyMetadata, attestation, proof):
    tx = loadPendingTransaction(txId)
    require tx.status == "pending"
    require tx.notExpired
    require tx.sessionIsStillValid
    require tx.principalAndTenantStillMatch
    require publicKeyUsesAllowedAlgorithm(publicKey)
    require verifyAttestationIfRequired(attestation, tx.challenge)
    require verifyProofOfPossession(publicKey, tx.challenge, proof)

    atomically:
        consumeChallenge(tx)
        ensureKeyNotAlreadyBoundIllegitimately(publicKey)
        storeBinding(
            principal = tx.principalId,
            tenant = tx.tenantId,
            publicKey = publicKey,
            metadata = minimized(keyMetadata),
            status = "active"
        )
        markTransactionConsumed(tx)

    notifyAccountOwner("new device linked")
    return bindingCreated()

authorizeBoundRequest(request):
    binding = loadBinding(request.keyId)
    require binding.status == "active"
    require binding.principal == request.session.principal
    require binding.tenant == request.session.tenant
    require request.audience == configuredResource
    require verifyRequestProof(binding.publicKey, canonicalRequest(request))
    require atomicallyConsumeNonceOrSequence(binding, request)
    require currentAuthorizationAllows(binding.principal, request.action)
    return executeWithIdempotencyPolicy(request)
~~~

Trong triển khai thật:

- Không gửi private key tới server hoặc lưu trong app preferences.
- Challenge và proof phải gắn đúng transaction, principal, tenant, purpose và audience.
- Attestation được xác minh ở backend theo trust configuration; không tin verdict do client tự khai.
- State transition và challenge consumption phải nguyên tử.
- Kiểm tra trạng thái binding gần thời điểm tạo session/token hoặc commit hành động.
- Nếu key không còn hợp lệ sau reinstall/OS update, yêu cầu re-enrollment theo recovery policy.

## 19. Tình huống thực tế: liên kết thiết bị mới sau khi mất điện thoại

Một người dùng có ứng dụng mobile đã liên kết với điện thoại cũ. Điện thoại bị thất lạc khi đi công tác. Người dùng có passkey dự phòng trên khóa bảo mật vật lý và muốn liên kết điện thoại mới.

### Đánh giá

| Thành phần | Trạng thái | Quyết định |
| --- | --- | --- |
| Điện thoại cũ | Đã báo mất | Suspend binding và đánh giá compromise. |
| Private key cũ | Không còn kiểm soát vật lý | Revoke nếu có khả năng bị lộ; không resume tùy tiện. |
| Passkey dự phòng | Active | Dùng để xác minh recovery và đăng nhập. |
| Session cũ | Có thể còn active | Kiểm tra và thu hồi theo binding/session policy. |
| Refresh token | Lưu trên điện thoại cũ | Thu hồi token family nếu nghi bị chiếm. |
| Điện thoại mới | Chưa đăng ký | Tạo key pair mới và enrollment riêng. |

### Luồng xử lý

1. Người dùng đăng nhập bằng passkey dự phòng và hoàn tất step-up.
2. Server tạo enrollment transaction mới, ràng buộc với principal, tenant và session.
3. App trên điện thoại mới tạo key pair trong OS keystore.
4. Server xác minh challenge, proof-of-possession và attestation nếu policy yêu cầu.
5. Binding mới được lưu active sau khi consume challenge nguyên tử.
6. Binding cũ được revoke; cache và verifier nhận trạng thái mới.
7. Session/refresh token liên quan được thu hồi theo incident policy.
8. Người dùng nhận thông báo qua kênh đã xác minh trước đó.

Nếu người dùng không còn passkey dự phòng, phải sử dụng account recovery có assurance phù hợp. Không cho phép chỉ cài app mới rồi tự bind bằng email hoặc SMS yếu.

## 20. Kiểm thử device binding

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Enrollment có session/step-up hợp lệ | Có thể tạo transaction pending. |
| Challenge hết hạn hoặc đã dùng | Từ chối proof. |
| Public key gửi lên nhưng không có proof-of-possession | Không activate binding. |
| Signature sai hoặc payload bị sửa | Từ chối. |
| Proof thuộc principal/tenant khác | Từ chối do transaction binding không khớp. |
| Attestation sai challenge hoặc chain không tin cậy | Từ chối hoặc áp dụng mức assurance thấp theo policy. |
| Client gửi cờ trusted=true | Bỏ qua; chỉ dùng trạng thái server đã xác minh. |
| Binding suspended/revoked | Từ chối proof dù chữ ký đúng. |
| Hai request cùng consume challenge | Chỉ một request thành công. |
| Request proof bị replay | Từ chối qua nonce/sequence state. |
| Device key không hardware-backed | Áp dụng policy đã định; không tự gán mức bảo đảm cao. |
| App reinstall làm mất key | Yêu cầu re-enrollment; không tự tạo binding mới bằng installation ID. |
| Device backup/migration | Xử lý theo semantics key portability; không giả định private key luôn device-bound. |
| Root/jailbreak signal | Risk policy đánh giá; không dựa vào một cờ đơn lẻ. |
| Binding bị revoke nhưng cache còn active | Invalidation/version/TTL giới hạn khoảng chấp nhận stale. |
| Token bearer bị lấy từ storage | Revoke/rotation hoặc sender-constrained policy giảm khả năng sử dụng lại. |
| User biometric thay đổi | Xử lý key invalidation theo access-control policy; yêu cầu recovery/re-enrollment nếu cần. |
| Notification service lỗi | Ghi nhận và retry; không làm binding chuyển trạng thái sai. |

### Kiểm thử vận hành và quyền riêng tư

- Đo thời gian propagation từ revoke tới mọi verifier.
- Kiểm tra attestation chain/key rotation và thay đổi API nền tảng.
- Kiểm tra khóa không xuất hiện trong backup/log/crash report ngoài policy.
- Kiểm tra thiết bị cũ, emulator, thiết bị accessibility và thiết bị doanh nghiệp.
- Đánh giá tỷ lệ false positive của root/jailbreak và integrity signals.
- Giới hạn metadata thiết bị, retention và quyền truy cập inventory.
- Kiểm tra người dùng có thể xem và thu hồi binding của thiết bị đã mất.

## 21. Checklist thiết kế device binding

- [ ] Phân biệt device binding, fingerprinting, attestation và device posture.
- [ ] Xác định threat model và hành động cần proof-of-possession.
- [ ] Tạo key pair trên thiết bị bằng OS keystore/Keychain phù hợp.
- [ ] Không xuất private key hoặc lưu key trong preferences/file thông thường.
- [ ] Đánh giá hardware-backed security theo bằng chứng thực tế, không suy đoán từ model.
- [ ] Enrollment cần session/step-up và transaction gắn principal, tenant, purpose, challenge, expiry.
- [ ] Xác minh proof-of-possession trước khi activate binding.
- [ ] Attestation được xác minh ở backend và có policy cho thiết bị không hỗ trợ.
- [ ] Proof bao phủ audience, purpose, session và request context cần thiết.
- [ ] Chống replay bằng nonce/sequence và atomic state update.
- [ ] Tách binding/key theo thiết bị, tenant, client và môi trường.
- [ ] Không coi device binding là user authentication hoặc authorization.
- [ ] Nếu ràng buộc token, resource server phải thực sự yêu cầu sender proof.
- [ ] Quản lý mất máy, reinstall, migration, backup, suspend, revoke và replacement.
- [ ] Thu hồi session/token liên quan theo policy khi binding bị compromise.
- [ ] Có cache invalidation, status version và propagation SLA.
- [ ] Giảm thiểu metadata và bảo vệ quyền riêng tư thiết bị.
- [ ] Kiểm thử root/jailbreak, key invalidation, replay, race, stale cache và recovery.

## 22. Câu hỏi tự kiểm tra

**Câu 1.** Device binding khác device fingerprinting như thế nào?

**Gợi ý:** Binding dùng khóa mật mã và proof-of-possession; fingerprinting dùng tín hiệu xác suất có thể thay đổi hoặc giả mạo.

**Câu 2.** Vì sao device binding không tự chứng minh người đang cầm điện thoại là chủ tài khoản?

**Gợi ý:** Thiết bị có thể bị mượn, mất hoặc điều khiển bởi malware; cần user authentication/verification và authorization riêng.

**Câu 3.** Vì sao server phải xác minh proof-of-possession sau khi nhận public key?

**Gợi ý:** Public key có thể được gửi bởi bất kỳ ai. Proof chứng minh bên đăng ký đang kiểm soát private key tương ứng.

**Câu 4.** Hardware-backed key có ngăn malware yêu cầu ký request không?

**Gợi ý:** Không tuyệt đối. Private key khó trích xuất hơn, nhưng malware có thể điều khiển app hợp lệ yêu cầu thiết bị ký khi key được phép sử dụng.

**Câu 5.** Attestation có chứng minh thiết bị hoàn toàn an toàn không?

**Gợi ý:** Không. Attestation cung cấp bằng chứng trong phạm vi nền tảng; server cần kiểm tra freshness, trust chain và policy, đồng thời đánh giá rủi ro còn lại.

**Câu 6.** Thu hồi device binding có tự động vô hiệu hóa bearer token đã phát hành không?

**Gợi ý:** Không. Cần token/session revocation policy hoặc sender-constrained validation ở resource server.

**Câu 7.** Vì sao app reinstall không nên tự động được coi là cùng một thiết bị?

**Gợi ý:** Key có thể bị xóa hoặc thay đổi; installation ID không phải bằng chứng mật mã. Cần kiểm tra key còn dùng được hoặc re-enrollment.

## 23. Ghi nhớ

**Device binding liên kết tài khoản hoặc phiên với một khóa mật mã được quản lý trên thiết bị để server có thể yêu cầu proof-of-possession.** Thiết kế an toàn cần tạo khóa trong OS keystore/Keychain phù hợp, giữ private key ngoài tầm đọc của app, xác minh challenge và proof ở server, gắn binding với đúng principal/tenant/session và chống replay bằng nonce/sequence state nguyên tử. Attestation có thể bổ sung bằng chứng về app hoặc môi trường nhưng không chứng minh tuyệt đối thiết bị an toàn hay người dùng đang hiện diện. Device binding không thay thế user authentication, authorization hoặc PKCE; hệ thống còn phải quản lý mất máy, reinstall, migration, suspend/revoke, session/token và quyền riêng tư trong toàn bộ vòng đời.
