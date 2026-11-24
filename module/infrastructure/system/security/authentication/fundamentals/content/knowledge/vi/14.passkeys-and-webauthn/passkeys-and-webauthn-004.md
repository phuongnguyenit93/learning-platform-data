# Public key credential

## 1. Public key credential là gì?

**Public key credential (credential khóa công khai)** là credential dựa trên mật mã bất đối xứng. Credential gắn một danh tính hoặc tài khoản với một cặp khóa: **khóa riêng (private key)** được giữ bởi chủ thể hoặc authenticator, còn **khóa công khai (public key)** được bên xác minh lưu để kiểm tra bằng chứng được tạo bằng khóa riêng.

Trong đăng nhập bằng passkey/WebAuthn, trình duyệt và authenticator dùng credential khóa công khai để chứng minh quyền kiểm soát khóa riêng đã đăng ký với một relying party (RP). Khi đăng ký, authenticator tạo credential và RP nhận credential ID cùng public key. Khi xác thực, RP phát challenge mới; authenticator ký dữ liệu xác thực bằng private key; RP kiểm tra chữ ký bằng public key đã lưu.

Điểm quan trọng: **private key không được gửi đến RP trong luồng WebAuthn thông thường**. RP không cần biết hoặc lưu bí mật có thể dùng để giả chữ ký của authenticator. Nếu cơ sở dữ liệu chỉ chứa public key bị lộ, attacker không thể từ public key tính ngược private key trong điều kiện thuật toán và độ dài khóa được chọn an toàn.

| Thành phần | Vai trò |
| --- | --- |
| **Private key** | Tạo chữ ký hoặc bằng chứng mật mã; cần được bảo vệ trong authenticator/secure storage. |
| **Public key** | Xác minh chữ ký; có thể lưu phía RP. |
| **Credential ID** | Định danh credential để RP tìm đúng public key và metadata. |
| **Authenticator** | Tạo, lưu và sử dụng private key theo chính sách của thiết bị. |
| **Relying party (RP)** | Đăng ký credential, phát challenge và xác minh response. |
| **User/account binding** | Liên kết credential với đúng tài khoản và tenant. |

Public key credential không đồng nghĩa với một chứng chỉ số X.509. WebAuthn thường đăng ký public key trực tiếp cho một RP bằng credential ID và metadata. Trong PKI truyền thống, public key có thể nằm trong certificate được CA ký và xác nhận các thuộc tính danh tính theo chính sách cấp chứng chỉ. Hai mô hình cùng dùng mật mã khóa công khai nhưng có cách xác lập danh tính, phân phối khóa và quản lý tin cậy khác nhau.

Trong module `SECURITY_AUTHENTICATION_FUNDAMENTALS`, public key credential là nền tảng mật mã của passkey: nó giúp xác thực chống phishing khi RP kiểm tra đúng challenge, origin và RP ID; đồng thời vẫn cần quản lý enrollment, session, authorization và recovery.

## 2. Mô hình khóa công khai và chữ ký số

Mật mã bất đối xứng sử dụng một cặp khóa có quan hệ toán học. Bên giữ private key tạo chữ ký trên dữ liệu; bên có public key kiểm tra chữ ký. Với chữ ký số đúng chuẩn:

- Chỉ chủ thể có khả năng sử dụng private key tương ứng mới có thể tạo chữ ký hợp lệ, trong giả định khóa chưa bị lộ và thuật toán an toàn.
- Bất kỳ bên nào có public key phù hợp đều có thể kiểm tra chữ ký.
- Chữ ký ràng buộc với nội dung được ký; thay đổi dữ liệu sẽ làm kiểm tra thất bại.
- Chữ ký **không mã hóa dữ liệu**. Nội dung được ký có thể vẫn công khai.

~~~mermaid
sequenceDiagram
    participant A as Authenticator
    participant R as Relying Party
    Note over A: Giữ private key
    Note over R: Lưu public key
    R->>A: Challenge + ngữ cảnh xác thực
    A->>A: Ký dữ liệu bằng private key
    A-->>R: Credential ID + assertion + signature
    R->>R: Xác minh chữ ký bằng public key
    R-->>A: Chấp nhận hoặc từ chối
~~~

Đây là sơ đồ khái niệm; WebAuthn định nghĩa chính xác dữ liệu và thứ tự xử lý. Không nên tự ký một chuỗi challenge tùy ý rồi coi đó là WebAuthn assertion.

### 2.1. Vì sao public key có thể lưu ở server?

Public key được thiết kế để chia sẻ. RP có thể lưu public key cùng credential ID, user ID, tenant, thuật toán, trạng thái và metadata. Nếu attacker chỉ đọc được bản ghi public key, họ có thể biết một số thông tin định danh/metadata nhưng không thể tạo chữ ký hợp lệ nếu không có private key.

Điều này giảm tác động của một số vụ lộ cơ sở dữ liệu so với mô hình lưu mật khẩu dạng có thể kiểm tra bằng cách thử đoán. Tuy vậy, database vẫn cần bảo vệ vì có thể chứa thông tin cá nhân, liên kết tài khoản, credential ID và trạng thái thu hồi. Kẻ tấn công có quyền sửa dữ liệu có thể thay public key hoặc ánh xạ credential sang tài khoản khác nếu ứng dụng không bảo vệ tính toàn vẹn và quyền ghi.

### 2.2. Chữ ký không chứng minh danh tính pháp lý

Một chữ ký đúng chứng minh rằng private key tương ứng đã được sử dụng để tạo chữ ký trên nội dung đó. Nó không tự chứng minh người cầm thiết bị là ai ngoài đời, private key được cấp cho đúng cá nhân hay tài khoản có quyền làm mọi thao tác.

Để gắn public key với một tài khoản, hệ thống cần quy trình **enrollment** đáng tin cậy. Nếu yêu cầu danh tính pháp lý hoặc tư cách nhân viên, còn cần identity proofing hoặc nguồn dữ liệu có thẩm quyền. Authentication bằng public key và identity proofing là hai việc riêng.

## 3. Public key credential trong WebAuthn

WebAuthn là API chuẩn của trình duyệt cho phép RP đăng ký và xác thực credential khóa công khai. Credential được tạo theo phạm vi RP ID; browser kiểm soát origin và authenticator giữ private key. FIDO2 thường được dùng để chỉ hệ sinh thái gồm WebAuthn và CTAP, trong đó CTAP hỗ trợ giao tiếp với authenticator bên ngoài.

Một public key credential WebAuthn thường có:

- **Credential ID:** byte string do authenticator tạo, được trả về khi đăng ký và dùng để chọn credential khi xác thực.
- **Credential public key:** public key ở định dạng COSE_Key, gồm thuật toán và các tham số khóa cần thiết.
- **Relying Party ID:** định danh phạm vi dịch vụ mà credential được tạo cho.
- **User handle:** định danh opaque do RP cung cấp để gắn credential với tài khoản, đặc biệt hữu ích cho discoverable credential.
- **Authenticator metadata:** ví dụ AAGUID, transports, sign counter, backup eligibility/state và các thông tin khác tùy response.

Credential ID không phải public key và không phải secret xác thực. Biết credential ID không cho phép ký bằng private key. Tuy nhiên, credential ID có thể làm lộ dấu hiệu về tài khoản hoặc thiết bị, vì vậy cần hạn chế đưa vào log và giao diện không cần thiết.

### 3.1. Discoverable và non-discoverable credential

WebAuthn có credential có thể được authenticator tìm theo RP mà không cần RP chỉ định trước credential ID, gọi là **discoverable credential** (trước đây thường gọi resident credential). Điều này hỗ trợ đăng nhập không cần nhập username: authenticator cung cấp credential phù hợp, RP dùng credential ID/user handle để xác định tài khoản.

Với **non-discoverable credential**, RP thường cần xác định tài khoản trước và gửi danh sách credential ID được phép dùng trong request options.

| Loại | Luồng chọn credential | Điểm cần chú ý |
| --- | --- | --- |
| Discoverable | Authenticator tìm credential theo RP ID; người dùng có thể chọn tài khoản. | Cần xử lý user handle và chống lộ thông tin tài khoản. |
| Non-discoverable | RP xác định tài khoản rồi cung cấp credential ID phù hợp. | Cần tránh account enumeration ở bước nhập username. |

Discoverable không có nghĩa credential được công khai hoặc bất kỳ RP nào cũng có thể tìm thấy nó. RP ID và cơ chế của authenticator giới hạn phạm vi sử dụng.

## 4. Đăng ký public key credential

Đăng ký là bước tạo khóa và gắn public key với đúng tài khoản. Đây là điểm đặc biệt nhạy cảm: nếu attacker thêm public key của họ vào tài khoản nạn nhân, họ có thể đăng nhập hợp lệ về sau.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Browser
    participant A as Authenticator
    participant RP as Relying Party
    U->>B: Yêu cầu thêm passkey
    B->>RP: Bắt đầu đăng ký
    RP->>RP: Xác định account, tạo challenge và flow
    RP-->>B: Creation options + challenge
    B->>A: navigator.credentials.create()
    A->>A: Tạo cặp khóa, lưu private key
    A-->>B: Credential ID + public key + attestation data
    B->>RP: Registration response
    RP->>RP: Kiểm tra challenge, origin, RP ID và cấu trúc
    RP->>RP: Lưu public key và liên kết credential
    RP-->>U: Hoàn tất đăng ký
~~~

Quy trình khái quát:

1. Xác định tài khoản đích bằng một phiên đã xác thực hoặc quy trình onboarding/proofing đáng tin cậy.
2. Kiểm tra người dùng có quyền thêm authenticator hay không; với tài khoản nhạy cảm có thể yêu cầu step-up.
3. Tạo challenge ngẫu nhiên, gắn với account, flow và thời hạn; lưu trạng thái ở phía server.
4. Tạo options đăng ký, bao gồm RP ID, user ID không nhạy cảm, user name/display name, thuật toán chấp nhận, authenticator selection, chính sách user verification và các tùy chọn phù hợp.
5. Browser gọi WebAuthn API; authenticator tạo credential và lưu private key theo chính sách thiết bị.
6. RP xác minh response: loại client data, challenge, origin, RP ID hash, cấu trúc attested credential data, thuật toán và chính sách attestation nếu được yêu cầu.
7. RP lưu credential ID, public key, user handle và metadata tối thiểu, liên kết với đúng account/tenant; tiêu thụ challenge.

### 4.1. Attestation là gì?

**Attestation** có thể cung cấp bằng chứng về nguồn gốc hoặc loại authenticator và cách credential được tạo, tùy định dạng attestation và chính sách RP. Nó khác assertion dùng khi đăng nhập: attestation xuất hiện trong một số luồng đăng ký, còn assertion chứng minh khả năng sử dụng credential trong một lần xác thực.

Không phải dịch vụ nào cũng cần attestation. Yêu cầu attestation quá cụ thể có thể giảm khả năng tương thích, tạo dấu vân tay thiết bị và thu thập dữ liệu không cần thiết. RP chỉ nên yêu cầu hoặc xác minh attestation khi có yêu cầu bảo đảm rõ ràng, đồng thời tuân thủ chính sách quyền riêng tư.

### 4.2. Lưu trữ public key

Một bản ghi minh họa:

~~~json
{
  "credentialId": "base64url-credential-id",
  "userId": "user_123",
  "tenantId": "tenant_a",
  "publicKeyCose": "stored-cose-key",
  "signCount": 0,
  "backupEligible": true,
  "backupState": true,
  "createdAt": "2026-11-22T10:00:00Z",
  "revokedAt": null
}
~~~

Đây là cấu trúc ứng dụng minh họa, không phải schema bắt buộc của WebAuthn. Dữ liệu thực tế cần lưu đúng kiểu binary/COSE, phiên bản schema và metadata theo thư viện. Public key không cần mã hóa để giữ bí mật, nhưng kho dữ liệu cần kiểm soát quyền ghi, backup, audit và tenant isolation. Không được cho phép người dùng sửa public key của credential đã đăng ký chỉ bằng một API profile thông thường.

## 5. Xác thực bằng public key credential

Khi đăng nhập, RP phát challenge mới và client yêu cầu authenticator dùng credential đã đăng ký tạo assertion. Authenticator không gửi private key; nó trả credential ID, authenticator data, client data và chữ ký.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Browser
    participant A as Authenticator
    participant RP as Relying Party
    U->>B: Chọn đăng nhập bằng passkey
    B->>RP: Yêu cầu authentication options
    RP->>RP: Tạo challenge mới và lưu flow
    RP-->>B: Request options
    B->>A: navigator.credentials.get()
    A->>A: Xác minh người dùng theo policy
    A->>A: Ký authenticator data và client data hash
    A-->>B: Assertion
    B->>RP: Credential ID + authenticatorData + clientDataJSON + signature
    RP->>RP: Tra public key và xác minh response
    RP->>RP: Kiểm tra trạng thái credential/account và consume challenge
    RP-->>B: Kết quả xác thực
    RP-->>U: Cấp session theo policy
~~~

RP phải kiểm tra đầy đủ, không chỉ kiểm tra chữ ký:

1. client data type đúng với thao tác, thường là loại assertion WebAuthn.
2. Challenge khớp giá trị RP đã phát, đúng flow, còn hạn và chưa được dùng.
3. Origin thuộc danh sách origin được RP cho phép; xử lý chính sách cross-origin/top-origin nếu có.
4. RP ID hash trong authenticator data đúng RP ID dự kiến.
5. Credential ID đã đăng ký, public key thuộc đúng tài khoản và tenant.
6. Chữ ký hợp lệ trên dữ liệu theo WebAuthn, thường là authenticatorData nối với SHA-256 của clientDataJSON, với thuật toán tương ứng public key/COSE.
7. Các cờ UP (User Presence) và UV (User Verification) đáp ứng chính sách.
8. Trạng thái tài khoản, credential, thời hạn và rủi ro hiện tại cho phép đăng nhập.

Thư viện WebAuthn server-side cần xử lý parsing, kiểm tra chữ ký và các quy tắc đặc tả. Không tự viết parser hoặc bỏ qua origin/challenge vì một test đơn giản đã thành công.

## 6. Các định dạng khóa và thuật toán

WebAuthn biểu diễn public key bằng **COSE_Key**, một cấu trúc được mã hóa theo CBOR, trong đó có thông tin về loại khóa, thuật toán và tham số. Các thuật toán thường gặp bao gồm:

| Nhóm | Ví dụ | Lưu ý |
| --- | --- | --- |
| Elliptic Curve | ES256 (ECDSA với P-256 và SHA-256) | Phải kiểm tra đúng curve và thuật toán được credential khai báo. |
| RSA | RS256 (RSASSA-PKCS1-v1_5 với SHA-256) | Cần độ dài khóa và chính sách phù hợp; không tự suy thuật toán từ định dạng byte. |
| Edwards curve | EdDSA, ví dụ Ed25519 trong môi trường hỗ trợ | Chỉ dùng khi client, authenticator và thư viện xác minh hỗ trợ theo đặc tả/chính sách. |

RP nên chỉ chấp nhận thuật toán đã được đánh giá và hỗ trợ bởi hệ sinh thái mục tiêu. Không cho client tự chọn một thuật toán yếu hoặc thay đổi thuật toán khi xác minh. Public key phải được parse từ định dạng chuẩn và kiểm tra tham số, không nhận một chuỗi key tùy ý.

Chữ ký ECDSA có thể có cách biểu diễn cụ thể theo giao thức/định dạng, và thư viện phải chuyển đổi đúng khi dùng thư viện mật mã nền tảng. Không tự xử lý chuỗi chữ ký bằng cách giả định mọi thuật toán đều có cùng format.

## 7. User Presence, User Verification và mức bảo đảm

Hai cờ thường gặp trong authenticator data:

| Cờ | Ý nghĩa | Giới hạn |
| --- | --- | --- |
| **UP** | Có bằng chứng user presence/tương tác với authenticator. | Không nhất thiết chứng minh người dùng cụ thể đã được xác minh. |
| **UV** | Authenticator thực hiện user verification cục bộ theo khả năng của nó, ví dụ PIN hoặc sinh trắc học. | Không chứng minh danh tính pháp lý, ý định cho mọi giao dịch hay dữ liệu sinh trắc học đã gửi cho RP. |

RP có thể yêu cầu UV cho tài khoản có rủi ro cao hoặc thao tác nhạy cảm. Nếu policy yêu cầu UV mà assertion không đáp ứng, RP cần từ chối hoặc dùng phương án thay thế đã được policy cho phép.

Không nên gọi một thao tác chạm security key là MFA nếu không có phân tích yếu tố. Một passkey với user verification cục bộ có thể đáp ứng yêu cầu xác thực mạnh theo chính sách, nhưng khái niệm MFA và mức bảo đảm còn phụ thuộc cách credential, thiết bị và quy trình được triển khai.

## 8. Phạm vi RP ID và chống phishing

Một lợi thế quan trọng của public key credential WebAuthn là credential được tạo cho **RP ID**, còn client data chứa **origin** của trang thực hiện thao tác. Browser và authenticator phối hợp ràng buộc credential vào phạm vi hợp lệ.

Ví dụ:

- Website thật có origin `https://login.example.com` và RP ID `example.com`.
- Attacker tạo trang `https://example-login.test` rồi yêu cầu người dùng đăng nhập.
- Origin của trang giả không nằm trong phạm vi origin hợp lệ của RP thật.
- Browser không cho dùng credential của `example.com` theo cách một trang giả có thể chuyển tiếp như OTP.

Điều này giúp chống phishing chuyển tiếp credential, nhưng không giải quyết:

- XSS hoặc malware thao tác trên origin thật.
- Session cookie/access token bị lấy sau khi đăng nhập.
- Kẻ tấn công chiếm tài khoản nền tảng dùng để đồng bộ passkey.
- Quy trình recovery hoặc thêm credential mới yếu.
- Người dùng bị lừa phê duyệt giao dịch không đúng ý định.

Origin và RP ID phải được cấu hình chính xác. RP ID không phải URL đầy đủ; origin bao gồm scheme, host và port theo quy tắc của trình duyệt. Không dùng wildcard hoặc danh sách origin quá rộng nếu không có nhu cầu được đánh giá.

## 9. Device-bound, synced passkey và backup flags

Public key credential có thể được quản lý theo nhiều mô hình:

- **Device-bound credential:** private key gắn với một authenticator cụ thể, thường không đồng bộ như passkey thông thường. Mất thiết bị có thể khiến credential không còn dùng được.
- **Synced passkey:** credential được đồng bộ qua hệ sinh thái của nhà cung cấp giữa các thiết bị. Người dùng có thể phục hồi trên thiết bị mới theo chính sách nền tảng.

WebAuthn định nghĩa các cờ liên quan backup eligibility (BE) và backup state (BS). RP có thể lưu các cờ này để hiểu một số đặc tính của credential. Tuy nhiên:

- BE cho biết credential đủ điều kiện backup theo định nghĩa giao thức, không phải bằng chứng độc lập rằng khóa đã được đồng bộ an toàn.
- BS phản ánh trạng thái backup được authenticator báo cáo tại thời điểm xác thực; không nên coi là một cam kết bất biến về mọi bản sao khóa.
- Việc đồng bộ làm thay đổi ranh giới tin cậy: bảo mật tài khoản nền tảng, thiết bị đã đăng nhập, cơ chế khôi phục và mã hóa đồng bộ đều có ý nghĩa.

Với tài khoản có yêu cầu thiết bị chuyên dụng hoặc kiểm soát vật lý, device-bound security key có thể phù hợp hơn. Với dịch vụ tiêu dùng cần khả năng tiếp cận và phục hồi, synced passkey có thể mang lại trải nghiệm tốt hơn. Lựa chọn cần dựa trên mô hình rủi ro và chính sách, không dựa vào nhãn marketing.

## 10. Sign counter và phát hiện credential bị sao chép

Authenticator data có thể chứa **sign counter**. Theo mô hình truyền thống, counter tăng qua mỗi lần sử dụng và RP so sánh với giá trị đã lưu để nhận biết dấu hiệu bất thường, chẳng hạn hai bản sao authenticator cùng tạo chữ ký từ một credential.

Tuy nhiên, không phải authenticator nào cũng cung cấp counter tăng đơn điệu. Một số passkey đồng bộ có thể trả về counter bằng 0 hoặc không đảm bảo quan hệ tăng như mô hình cũ. Vì vậy:

- RP nên lưu counter theo đặc tả và chính sách.
- Counter không tăng có thể là tín hiệu đánh giá rủi ro, không phải bằng chứng chắc chắn private key bị clone.
- Không từ chối tất cả passkey đồng bộ chỉ vì counter không tăng.
- Có thể kết hợp tín hiệu khác như credential backup state, hành vi đăng nhập, trạng thái thiết bị và step-up theo rủi ro.

## 11. Quản lý vòng đời public key credential

~~~mermaid
stateDiagram-v2
    [*] --> Created: Authenticator tạo key pair
    Created --> Registered: RP xác minh và lưu public key
    Registered --> Active: Credential sẵn sàng đăng nhập
    Active --> Used: Assertion được xác minh
    Used --> Active: Tiếp tục sử dụng
    Active --> Suspended: Nghi ngờ hoặc cần rà soát
    Suspended --> Active: Xác minh lại thành công
    Active --> Revoked: Người dùng/quản trị thu hồi
    Suspended --> Revoked: Xác nhận rủi ro
    Revoked --> [*]
~~~

RP nên hỗ trợ:

1. **Đăng ký:** tạo credential sau khi xác định đúng tài khoản và quyền enrollment.
2. **Liệt kê:** hiển thị các authenticator đang gắn với tài khoản, thời điểm tạo và lần dùng gần nhất.
3. **Đặt tên:** cho người dùng đặt nickname để nhận biết thiết bị; nickname không phải dữ liệu tin cậy.
4. **Xác thực:** kiểm tra assertion, trạng thái credential và policy hiện tại.
5. **Thu hồi:** ngừng chấp nhận credential khi mất thiết bị, nghi lộ hoặc người dùng xóa.
6. **Thay thế:** thêm credential mới sau khi xác minh lại phù hợp, rồi thu hồi credential cũ.
7. **Thông báo:** thông báo khi thêm/xóa credential và khi có thay đổi bảo mật quan trọng.

Thao tác thêm hoặc xóa public key có thể thay đổi quyền truy cập lâu dài. Không nên cho một session yếu tự thêm key do attacker kiểm soát rồi xóa hết key của chủ tài khoản. Hãy yêu cầu step-up, đánh giá rủi ro hoặc quy trình phê duyệt bổ sung.

## 12. Session và authorization sau public key authentication

Một assertion WebAuthn chứng minh credential đã được sử dụng trong một lần xác thực. Nó không phải session lâu dài. Sau khi xác minh thành công, RP thường tạo session ID mới hoặc cấp token theo chính sách.

Các lớp bảo vệ tiếp theo:

- Cookie web cần cấu hình `Secure`, `HttpOnly`, `SameSite` phù hợp và bảo vệ CSRF cho thao tác thay đổi trạng thái.
- Session/token cần expiry, logout, thu hồi khi tài khoản bị khóa hoặc credential bị nghi lộ.
- API phải kiểm tra authorization trên từng hành động, tài nguyên và tenant.
- Hành động rủi ro cao có thể yêu cầu step-up hoặc xác nhận giao dịch gắn với nội dung thực tế.
- Token dạng bearer vẫn có thể bị replay nếu bị đánh cắp; passkey không tự bảo vệ phiên đã cấp.

Do đó, không được dùng việc “đã đăng nhập bằng passkey” làm điều kiện duy nhất để đọc mọi dữ liệu hoặc thực hiện mọi nghiệp vụ.

## 13. Recovery và liên kết danh tính

Người dùng có thể mất thiết bị, mất security key, không truy cập được tài khoản đồng bộ hoặc bị khóa khỏi mọi authenticator. Recovery phải duy trì mức tin cậy tương xứng với luồng đăng nhập:

- Khuyến khích đăng ký credential dự phòng khi phù hợp.
- Cung cấp recovery code ngẫu nhiên, chỉ dùng một lần, được lưu và tiêu thụ an toàn nếu dịch vụ hỗ trợ.
- Với tài khoản tổ chức, có thể dùng quy trình hỗ trợ/identity proofing và phê duyệt độc lập.
- Không dùng câu hỏi bảo mật dễ đoán hoặc thông tin công khai làm bằng chứng duy nhất.
- Sau recovery, đánh giá thu hồi session/token và credential cũ, thông báo thay đổi và ghi audit event.

Nếu passkey được đồng bộ qua một tài khoản nền tảng, hệ thống RP cần hiểu rằng khả năng khôi phục của tài khoản nền tảng là một phần của ranh giới tin cậy. Không nên tự động coi email trùng nhau là bằng chứng đủ để liên kết hai tài khoản; cần subject/issuer hoặc định danh nội bộ ổn định cùng quy trình liên kết được xác minh.

## 14. Public key credential so với password và certificate

| Tiêu chí | Mật khẩu | WebAuthn public key credential | Certificate-based credential |
| --- | --- | --- | --- |
| Bí mật phía client | Người dùng nhớ và nhập mật khẩu. | Authenticator giữ private key. | Client giữ private key tương ứng certificate. |
| Dữ liệu phía server | Password verifier dạng hash có salt. | Credential ID, public key và metadata. | Certificate/chain hoặc public key và trust metadata. |
| Bằng chứng khi xác thực | Knowledge secret qua giao thức đăng nhập. | Assertion/chữ ký trên challenge và context. | Chữ ký hoặc proof-of-possession theo giao thức, thường kết hợp TLS. |
| Chống phishing | Phụ thuộc domain awareness, MFA và giao thức. | Có ràng buộc origin/RP ID theo WebAuthn. | Phụ thuộc cách client chọn certificate, xác minh server và chính sách. |
| Quản lý tin cậy | Reset, hash, MFA, rate limit. | Enrollment, public key, credential lifecycle, RP scope. | CA, chain, expiry, revocation, key usage và identity mapping. |
| Khôi phục | Reset password và kênh phục hồi. | Thêm authenticator/recovery an toàn. | Cấp lại certificate và bảo vệ private key. |

WebAuthn không phải một PKI certificate truyền thống. RP thường tin public key vì nó đã được đăng ký trong một ceremony hợp lệ cho chính RP, không phải vì một CA công khai ký certificate của người dùng. Attestation có thể cung cấp thêm thông tin về authenticator nhưng không biến mọi WebAuthn credential thành chứng chỉ danh tính pháp lý.

## 15. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Lưu private key ở server thay vì chỉ public key | Tăng tác động khi database bị xâm nhập. | Dùng mô hình WebAuthn; private key được authenticator giữ. |
| Chỉ kiểm tra chữ ký, bỏ qua challenge/origin/RP ID | Assertion hợp lệ bị dùng sai flow hoặc origin. | Xác minh đầy đủ theo đặc tả bằng thư viện server. |
| Cho client tự chỉ định user ID hoặc public key | Gắn nhầm credential sang tài khoản khác. | Lấy account từ session/policy tin cậy và kiểm soát enrollment. |
| Thêm passkey chỉ bằng session yếu | Attacker có thể đăng ký khóa của họ. | Step-up, risk check và thông báo thay đổi credential. |
| Coi credential ID là secret hoặc public key là credential ID | Thiết kế sai việc bảo vệ và ánh xạ. | Phân biệt định danh credential, public key và private key. |
| Tin mọi attestation hoặc yêu cầu attestation quá mức | Sai mô hình tin cậy hoặc giảm quyền riêng tư/tương thích. | Chọn chính sách attestation theo nhu cầu rõ ràng. |
| Coi UV là proofing danh tính | Suy diễn quá mức từ xác minh cục bộ. | Tách identity proofing, authentication và authorization. |
| Từ chối passkey vì sign counter không tăng | Từ chối nhầm authenticator đồng bộ hợp lệ. | Diễn giải counter theo đặc tính credential và chính sách. |
| Không thu hồi key bị mất | Credential cũ tiếp tục đăng nhập. | Credential registry, revoke và kiểm tra trạng thái trên mọi node. |
| Recovery yếu hơn enrollment | Attacker thay credential bằng đường khôi phục. | Recovery có proofing/step-up, phê duyệt và audit phù hợp. |
| Coi passkey bảo vệ cả session sau login | Session token bị đánh cắp vẫn có thể bị replay. | Quản lý session, token, XSS/CSRF và authorization độc lập. |

## 16. Checklist thiết kế public key credential

Trước khi triển khai, hãy trả lời:

1. Credential gắn với đúng account, tenant và RP ID như thế nào?
2. Private key được tạo và giữ ở đâu? Có bị xuất ra khỏi authenticator không?
3. Public key, credential ID và metadata được lưu với quyền đọc/ghi ra sao?
4. Registration challenge có mới, có expiry và được gắn với flow/account không?
5. Server xác minh đầy đủ challenge, origin, RP ID hash, credential ID, thuật toán, public key và attestation policy chưa?
6. Assertion có kiểm tra chữ ký trên đúng dữ liệu WebAuthn, UP/UV và trạng thái credential không?
7. Có xử lý discoverable credential, user handle và account enumeration an toàn không?
8. Device-bound và synced passkey có được đánh giá theo rủi ro, quyền riêng tư và recovery không?
9. Sign counter và backup flags được diễn giải đúng, tránh kết luận quá mức không?
10. Có cơ chế thêm, liệt kê, thu hồi, thay thế credential và thông báo thay đổi bảo mật không?
11. Session/token sau đăng nhập có expiry, revoke và chống lạm dụng phù hợp không?
12. API vẫn kiểm tra authorization theo tài nguyên/tenant và xác nhận giao dịch nhạy cảm không?
13. Recovery có đủ mạnh, có audit và không dựa vào thông tin dễ đoán không?

**Kết luận:** Public key credential gắn một tài khoản với public key đã đăng ký và cho phép authenticator chứng minh quyền sử dụng private key mà không phải gửi private key đến RP. Trong WebAuthn, challenge, origin và RP ID ràng buộc assertion với đúng lần xác thực và dịch vụ, tạo nền tảng cho passkey chống phishing. Để bảo vệ tài khoản hoàn chỉnh, hệ thống vẫn cần enrollment đáng tin, quản lý credential và thu hồi, session an toàn, authorization riêng và recovery đủ mạnh.
