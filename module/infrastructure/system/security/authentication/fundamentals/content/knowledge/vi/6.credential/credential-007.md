# Credential binding — Gắn bằng chứng xác thực với danh tính

## 1. Credential binding giải quyết bài toán gì?

Trong xác thực, **credential** là dữ liệu hoặc cơ chế bằng chứng được dùng để chứng minh quyền xác thực một danh tính: mật khẩu, khóa riêng của passkey, bí mật TOTP, khóa đi kèm chứng chỉ, hay token trong một ngữ cảnh nhất định. **Credential binding** là quá trình **thiết lập và quản lý mối liên kết đáng tin cậy giữa credential hoặc authenticator và tài khoản/chủ thể được phép sử dụng nó**.

Ví dụ, một người dùng có tài khoản \`u-1024\` muốn đăng ký thêm passkey. Ứng dụng không thể chỉ nhận khóa công khai do trình duyệt gửi và ghi vào tài khoản đó. Trước tiên, hệ thống phải chắc rằng **đúng chủ tài khoản được phép yêu cầu thêm credential**, sau đó xác nhận credential mới được tạo và đáp ứng các kiểm tra cần thiết, cuối cùng lưu bản ghi liên kết một cách an toàn. Những lần đăng nhập sau dựa vào chính bản ghi liên kết đã được thiết lập.

Trong chương **Credential** của module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, chủ đề này kết nối các kiến thức về mật khẩu, MFA, passkey, chứng chỉ, token, phiên, liên kết danh tính và khôi phục tài khoản. Nó giúp mô hình hóa **ranh giới tin cậy**, phòng chống phishing, replay, lạm dụng luồng đăng ký credential và thiết kế xác thực an toàn trong toàn bộ vòng đời tài khoản.

Một hệ thống an toàn phải trả lời được bốn câu hỏi riêng:

1. **Danh tính đích:** credential mới sẽ được gắn với tài khoản nào, thuộc tổ chức/tenant nào?
2. **Quyền yêu cầu:** ai được phép thêm, thay hoặc xóa credential của tài khoản ấy?
3. **Bằng chứng sở hữu/quyền kiểm soát:** bên yêu cầu có chứng minh được quyền sử dụng credential mới theo cơ chế tương ứng không?
4. **Vòng đời:** credential sẽ được dùng cho loại đăng nhập nào, và có thể bị vô hiệu hóa, thay thế hoặc thu hồi bằng cách nào?

**Điểm cốt lõi:** biết một định danh (email, username, user ID) **không đủ** để tự gắn credential vào tài khoản mang định danh đó. Nếu cho phép làm vậy, người tấn công chỉ cần biết địa chỉ email là có thể đăng ký phương thức đăng nhập của chính họ cho tài khoản nạn nhân.

## 2. Phân biệt các kiểu “binding” dễ nhầm

Từ *binding* xuất hiện ở nhiều tầng bảo mật. Chúng có liên hệ nhưng không thay thế nhau:

| Khái niệm | Liên kết điều gì? | Mục đích | Ví dụ |
| --- | --- | --- | --- |
| **Credential/authenticator binding** | Credential hoặc authenticator với tài khoản. | Hệ thống biết bằng chứng nào được chấp nhận cho tài khoản nào. | Đăng ký khóa công khai WebAuthn cho \`userId=1024\`. |
| **Credential với website/RP** | Bí mật hoặc khóa mật mã với phạm vi sử dụng. | Ngăn dùng nhầm bằng chứng cho dịch vụ khác. | Passkey WebAuthn gắn với **RP ID** của website. |
| **Device binding** | Credential hoặc phiên với một thiết bị/khóa thiết bị cụ thể. | Giảm nguy cơ sao chép credential sang môi trường khác, khi kiến trúc hỗ trợ. | Khóa riêng không xuất được khỏi phần cứng chuyên dụng. |
| **Session/token binding** | Phiên hoặc token với một khóa chứng minh quyền kiểm soát hay ngữ cảnh giao thức. | Giảm giá trị của token nếu bị sao chép. | Sender-constrained token dùng mTLS hoặc DPoP theo thiết kế OAuth phù hợp. |
| **Account/identity linking** | Danh tính từ nhà cung cấp ngoài với tài khoản nội bộ. | Xác định đăng nhập federated thuộc người dùng nào. | Gắn cặp \`issuer + sub\` OIDC với tài khoản nội bộ. |

**Passkey có thể đồng bộ** giữa các thiết bị thông qua nhà cung cấp nền tảng. Vì vậy, việc credential WebAuthn được gắn đúng vào tài khoản và RP ID **không tự chứng minh nó chỉ tồn tại trên một thiết bị duy nhất**. Nếu yêu cầu ràng buộc với phần cứng cụ thể, chính sách phải chọn loại authenticator, cơ chế chứng minh và giới hạn tương ứng, chứ không suy ra từ tên “passkey”.

Tương tự, mật khẩu gắn với tài khoản không có nghĩa phiên đăng nhập được bảo vệ khỏi sao chép. Đó là hai lớp kiểm soát khác nhau.

## 3. Mô hình dữ liệu và ranh giới tin cậy

Một tài khoản có thể có **nhiều credential**: mật khẩu, hai khóa bảo mật, một passkey đồng bộ và một authenticator TOTP dự phòng. Mỗi credential cần có bản ghi quản lý riêng để hỗ trợ thu hồi từng chiếc mà không khóa toàn bộ tài khoản.

~~~mermaid
flowchart LR
    U["Người dùng / thiết bị<br/>không mặc định tin cậy"]
    B["Trình duyệt / ứng dụng"]
    V["Server xác thực<br/>kiểm tra yêu cầu và bằng chứng"]
    T[("Giao dịch binding đang chờ<br/>challenge, chủ tài khoản, hết hạn")]
    A[("Tài khoản nội bộ<br/>account ID, tenant ID")]
    C[("Sổ credential<br/>ID, loại, trạng thái, vật liệu xác minh")]
    S[("Phiên / token<br/>vòng đời riêng")]
    U -->|"Bằng chứng hoặc thao tác"| B
    B -->|"Yêu cầu bảo vệ qua TLS"| V
    V <--> T
    V <--> A
    V <--> C
    V -->|"Tạo phiên sau đăng nhập"| S
~~~

Đây là sơ đồ logic, không bắt buộc tách thành từng dịch vụ. **Server tin cậy** là nơi quyết định được thêm credential nào và xác thực chứng cứ ra sao. Trình duyệt chỉ chuyển yêu cầu và phản hồi; các giá trị như \`accountId\`, \`verified=true\` hoặc \`tenantId\` do client tự gửi không được dùng làm thẩm quyền.

### Ví dụ một bản ghi liên kết

~~~text
CredentialBinding
  account_id:        u-1024
  tenant_id:         org-27
  credential_id:     <ID duy nhất của credential>
  credential_type:   webauthn_public_key
  verification_data: <khóa công khai và thông tin cần kiểm tra>
  status:            active | revoked
  created_at:        <thời điểm đăng ký>
  last_used_at:      <thời điểm sử dụng gần nhất, nếu có>
  label:             "Khóa bảo mật của tôi"
~~~

Ví dụ chỉ mô tả **dữ liệu nghiệp vụ**. Không lưu khóa riêng của passkey ở server. Với mật khẩu, chỉ lưu **verifier dựa trên password hashing** (ví dụ Argon2id có salt và tham số phù hợp). Với TOTP, server cần bảo vệ bí mật dùng chung ở trạng thái lưu trữ theo chính sách khóa/mã hóa. Không đưa credential, mã phục hồi hay token thô vào log.

Một số ràng buộc dữ liệu thường cần:

- Credential ID/định danh ngoài có quy tắc **duy nhất theo phạm vi giao thức**, không thể âm thầm chuyển quyền sở hữu sang tài khoản khác.
- Mỗi bản ghi có chủ tài khoản và **tenant** rõ ràng; các truy vấn và cập nhật phải kiểm tra đồng thời hai phạm vi này.
- Trạng thái \`active\`, \`revoked\` và thông tin kiểm toán đủ để thu hồi, điều tra mà không tiết lộ bí mật.
- Thao tác ghi kết thúc binding phải có tính **nguyên tử** để hai phản hồi đồng thời không tạo hai liên kết trái chính sách.

## 4. Vòng đời credential binding

Credential binding không chỉ diễn ra lúc tạo tài khoản. Nó có vòng đời:

| Giai đoạn | Công việc bảo mật quan trọng |
| --- | --- |
| **Khởi tạo** (*bootstrap*) | Xác định chủ tài khoản hợp lệ khi chưa có credential nào hoặc khi tài khoản mới được cấp phát. |
| **Đăng ký** (*enrollment/binding*) | Xác minh quyền yêu cầu và bằng chứng kiểm soát credential mới; ghi liên kết. |
| **Sử dụng** (*authentication*) | Kiểm chứng bằng chứng cho đúng credential, tài khoản, ứng dụng và giao dịch. |
| **Bổ sung/thay thế** (*rotation/rebinding*) | Thêm credential mới, giữ khả năng truy cập hợp lệ và hạn chế nguy cơ người lạ chiếm tài khoản. |
| **Thu hồi** (*revocation*) | Vô hiệu hóa credential mất, lộ hoặc không còn được phép sử dụng. |
| **Khôi phục** (*recovery*) | Cho phép chủ tài khoản lấy lại quyền truy cập khi mất mọi phương thức thông thường, mà không mở cửa cho kẻ tấn công. |

Mỗi giai đoạn có thể đòi hỏi **mức bảo đảm khác nhau**. Ví dụ: một phiên đăng nhập cũ có thể đủ để xem hồ sơ, nhưng muốn thêm passkey mới hoặc đổi kênh khôi phục thì cần xác thực lại gần thời điểm thao tác, thông báo cho chủ tài khoản và áp dụng kiểm tra rủi ro.

### Ba xuất phát điểm phải xử lý khác nhau

**Tài khoản mới:** hệ thống chưa có credential để yêu cầu xác thực lại. Cần một **quy trình thiết lập tin cậy ban đầu** theo chính sách hệ thống: lời mời được bảo vệ, xác minh quyền kiểm soát kênh liên hệ, kiểm chứng danh tính có mức bảo đảm phù hợp hoặc quy trình cấp phát bởi quản trị viên. Xác minh email chỉ chứng minh quyền kiểm soát hộp thư tại thời điểm đó, không tự chứng minh danh tính ngoài đời.

**Tài khoản đang hoạt động:** đã có phương thức đăng nhập. Trước khi gắn credential mới, phải kiểm chứng phiên hiện có, yêu cầu **step-up/re-authentication** khi cần và ràng buộc yêu cầu thêm credential với đúng tài khoản của phiên đó.

**Tài khoản bị mất mọi credential:** đây là đường **khôi phục**, không thể áp dụng chính xác thủ tục re-auth như khi người dùng vẫn có credential. Phải dùng mã khôi phục đã chuẩn bị hoặc quy trình kiểm chứng thay thế, giới hạn số lần thử, ghi sự kiện và kiểm soát rủi ro; không tự động cấp credential mới chỉ dựa trên username hay câu hỏi bảo mật dễ đoán.

## 5. Năm điều kiện để binding đáng tin

Một quy trình binding có thể đánh giá qua năm điều kiện:

1. **Chủ thể được xác định đúng:** server lấy account ID từ phiên hoặc giao dịch bootstrap đã xác minh, không lấy theo tham số tùy ý do trình duyệt chọn.
2. **Người yêu cầu có thẩm quyền:** thao tác thêm credential yêu cầu mức xác thực đủ mạnh theo rủi ro, có kiểm tra CSRF hoặc ràng buộc giao dịch phù hợp.
3. **Credential mới được kiểm chứng:** tùy loại credential, phải chứng minh quyền kiểm soát bí mật, khóa riêng hoặc kênh tương ứng; chỉ nhận một chuỗi định danh là chưa đủ.
4. **Bằng chứng gắn với giao dịch mới:** challenge/mã xác minh có entropy phù hợp, thời hạn và quy tắc dùng một lần, được ràng buộc với account, loại thao tác và ngữ cảnh.
5. **Kết quả được lưu và phản hồi an toàn:** lưu nguyên tử, chặn liên kết trùng hoặc chiếm lại ID, ghi nhận và thông báo thay đổi quan trọng, hỗ trợ thu hồi.

Không phải giao thức nào cũng hiện thực năm điều kiện bằng cùng một loại challenge. **Mật khẩu** dựa trên bí mật đã thiết lập và chính sách tạo/đổi; **TOTP** cần xác nhận mã sinh từ secret mới; **WebAuthn** có ceremony đăng ký dùng challenge và kiểm tra origin/RP ID; **chứng chỉ** cần chứng minh quyền sở hữu khóa riêng và chuỗi tin cậy phù hợp.

## 6. Binding đối với từng loại credential

| Credential | Vật liệu liên kết với tài khoản | Cách xác minh lúc gắn | Rủi ro đặc biệt |
| --- | --- | --- | --- |
| **Mật khẩu/passphrase** | Password verifier (hash, salt, tham số KDF). | Chủ tài khoản được phép đặt/đổi mật khẩu qua luồng đã xác minh; áp dụng chính sách mật khẩu. | Mật khẩu yếu, tái sử dụng, đoán offline nếu lộ hash; đổi mật khẩu nhờ khôi phục yếu. |
| **Authenticator TOTP** | Bí mật dùng chung riêng cho thiết bị/đăng ký, metadata. | Tạo secret mới qua kênh bảo vệ; người dùng nhập mã TOTP đúng, còn hạn; chỉ kích hoạt sau xác minh. | Secret bị chụp QR/copy, OTP bị phishing, cùng secret dùng nhiều nơi, phát lại mã trong cửa sổ thời gian. |
| **Passkey/WebAuthn** | Credential ID, khóa công khai, RP ID và metadata cần thiết. | WebAuthn registration ceremony: challenge, origin, RP ID, yêu cầu về user presence/verification, dữ liệu attest theo chính sách. | Bỏ kiểm tra challenge/origin; kẻ tấn công thêm passkey qua phiên bị chiếm; hiểu nhầm passkey đồng bộ là khóa chỉ có trên một thiết bị. |
| **Khóa bảo mật phần cứng** | Khóa công khai/credential ID gắn với RP, thuộc tính hỗ trợ chính sách. | WebAuthn/FIDO2 hoặc giao thức chứng minh quyền kiểm soát khóa. | Mất thiết bị, cần chính sách thay thế và mã dự phòng; attestation có ý nghĩa tùy yêu cầu. |
| **Chứng chỉ khách / mTLS** | Chứng chỉ hoặc khóa công khai và ánh xạ danh tính đã được duyệt. | Kiểm tra chuỗi PKI, thời hạn/chính sách, và **proof of possession** của khóa riêng qua handshake/challenge. | Tin \`subject\`/CN như một username tuyệt đối; không kiểm tra thu hồi hoặc thay khóa; khóa riêng bị sao chép. |
| **Danh tính từ IdP** | Cặp định danh đã được giao thức xác minh, ví dụ \`issuer + sub\` với OIDC. | Hoàn tất OIDC/SAML, kiểm tra issuer, audience/recipient, chữ ký, ngữ cảnh rồi liên kết với tài khoản nội bộ theo chính sách. | Gộp tài khoản theo email; tin IdP sai; bỏ kiểm tra giao dịch hoặc nhầm tenant. |

### 6.1. Gắn mật khẩu và bảo vệ việc đổi mật khẩu

Server không cần và không nên giữ bản sao mật khẩu gốc để chứng minh binding. Khi người dùng tạo hoặc đổi mật khẩu, server **xác minh quyền thực hiện thao tác**, kiểm tra mật khẩu mới theo chính sách, rồi lưu verifier của mật khẩu ấy. Một bản ghi verifier thường chứa thuật toán, tham số, salt riêng và đầu ra hash; nó liên kết với đúng account ID.

Mật khẩu cũ bị lộ hoặc người dùng mất thiết bị không đồng nghĩa với quyền cấp mật khẩu mới. Nếu giao diện “đổi mật khẩu” chỉ kiểm tra cookie phiên cũ bị đánh cắp, kẻ tấn công có thể thiết lập bí mật của họ thành phương thức đăng nhập hợp lệ. Cần áp dụng xác thực lại và xử lý phiên đang tồn tại sau đổi mật khẩu theo chính sách.

### 6.2. Gắn TOTP đúng cách

Ví dụ người dùng bật TOTP khi đã đăng nhập:

1. Server kiểm tra quyền bật MFA của chủ tài khoản, có thể yêu cầu xác thực lại.
2. Server sinh **secret duy nhất, khó đoán**, tạo một bản ghi **pending**, rồi hiển thị QR hoặc chuỗi thiết lập qua kênh HTTPS đã bảo vệ.
3. Người dùng thêm secret vào ứng dụng authenticator và nhập mã TOTP đang có hiệu lực.
4. Server kiểm tra mã bằng secret **pending**, giới hạn số lần thử, cửa sổ thời gian chấp nhận và khả năng dùng lại mã theo chính sách.
5. Chỉ khi mã hợp lệ, server mới kích hoạt binding cho tài khoản đúng; xóa hoặc vô hiệu hóa bản ghi pending và thông báo thay đổi MFA.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant A as Ứng dụng
    participant S as Server
    U->>A: Yêu cầu thêm TOTP
    A->>S: Gửi yêu cầu trong phiên đã xác thực
    S->>S: Kiểm tra quyền và tạo secret pending
    S-->>A: Trả QR/secret qua kênh bảo vệ
    A-->>U: Hiển thị để quét
    U->>A: Nhập mã đang hiển thị trên authenticator
    A->>S: Xác minh mã theo giao dịch pending
    S->>S: Kiểm tra OTP, hạn, số lần thử, replay
    S-->>A: Nếu hợp lệ: kích hoạt binding và thông báo
~~~

Việc **hiển thị QR không chứng minh** người dùng đã cài đặt authenticator: phải xác minh một mã hợp lệ trước khi xem như gắn thành công. TOTP dùng secret chia sẻ nên không thể đảm bảo secret chỉ tồn tại ở một thiết bị; ai sao chép QR hoặc secret cũng có thể tạo mã. Mã TOTP có thể bị phishing/chuyển tiếp trong thời gian ngắn, nên không có tính chống phishing tương đương WebAuthn.

### 6.3. Gắn passkey với WebAuthn

Trong WebAuthn, ứng dụng (Relying Party — **RP**) yêu cầu trình duyệt tạo credential cho RP cụ thể. Authenticator tạo hoặc chọn vật liệu khóa; **RP lưu khóa công khai và credential ID**, còn khóa riêng được authenticator quản lý. Phần xác thực đăng nhập về sau là chữ ký đối với challenge mới, chứ không phải việc client tự khẳng định “tôi có passkey”.

Một quá trình đăng ký điển hình:

1. Server xác định account/tenant và kiểm tra người yêu cầu được **thêm passkey**; tạo challenge ngẫu nhiên, thời hạn ngắn, lưu giao dịch với account, phiên và chính sách RP.
2. Server gửi \`PublicKeyCredentialCreationOptions\` với challenge, **RP ID**, thông tin user handle và tùy chọn xác minh người dùng/phần cứng phù hợp.
3. Trình duyệt và authenticator thực hiện \`navigator.credentials.create(...)\`; trình duyệt gửi về dữ liệu đăng ký gồm client data và attestation object.
4. Server kiểm chứng loại ceremony (\`webauthn.create\`), challenge từ giao dịch đang chờ, **origin**, RP ID hash và các cờ bắt buộc như user presence/user verification. Nếu chính sách yêu cầu attestation để xác định thuộc tính authenticator, server phải xác minh attestation theo chuỗi tin cậy phù hợp.
5. Server lấy credential ID và khóa công khai từ dữ liệu **đã được xác minh**, kiểm tra credential ID chưa bị chiếm bởi bản ghi khác, tiêu thụ giao dịch dùng một lần rồi lưu binding với account/tenant.
6. Ghi nhận thay đổi credential, thông báo và cho phép đặt nhãn dễ hiểu; không xem nhãn người dùng nhập là dữ liệu xác thực.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant R as RP/server
    participant B as Trình duyệt
    participant K as Authenticator
    U->>R: Thêm passkey trong phiên đủ tin cậy
    R->>R: Tạo challenge và giao dịch ràng buộc account
    R-->>B: Registration options (challenge, RP ID, UV...)
    B->>K: webauthn.create với challenge
    K->>K: Tạo credential và xử lý xác minh người dùng
    K-->>B: Dữ liệu đăng ký, credential ID, khóa công khai
    B->>R: Gửi response
    R->>R: Verify challenge, origin, RP ID, cờ và attestation theo chính sách
    R->>R: Lưu credential ID và khóa công khai nguyên tử
    R-->>U: Xác nhận đã đăng ký passkey
~~~

**Hai khác biệt quan trọng:**

- **Proof of possession:** việc tạo credential và xác minh thông điệp WebAuthn cung cấp bằng chứng theo ceremony đăng ký. Trong **đăng nhập** (\`webauthn.get\`), RP còn kiểm tra chữ ký bằng khóa công khai đã lưu, challenge mới, origin, RP ID và các cờ liên quan. Hai ceremony có nhiệm vụ khác nhau.
- **Attestation khác user verification:** attestation, nếu được yêu cầu và kiểm chứng, nói về thuộc tính/nguồn gốc của authenticator theo trust policy; user verification (UV) cho biết authenticator đã kiểm tra người dùng theo cơ chế của nó. Một hệ thống có thể chấp nhận **attestation none** theo chính sách và vẫn xác minh đăng ký WebAuthn hợp lệ.

Không coi **signature counter** luôn tăng trên mọi passkey, đặc biệt với passkey đồng bộ; giá trị này có thể không hỗ trợ phát hiện bản sao khóa ở mọi trường hợp. Cần đọc và xử lý tín hiệu theo đặc tính authenticator, không khóa người dùng hợp lệ chỉ dựa trên giả định sai về counter.

### 6.4. Gắn chứng chỉ và danh tính liên kết

**Chứng chỉ X.509** thường cung cấp khóa công khai và thông tin do CA ký; bản thân tệp chứng chỉ có thể công khai. Server cần kiểm tra **chứng minh quyền kiểm soát khóa riêng** (ví dụ trong mTLS), chuỗi tin cậy, mục đích sử dụng, thời hạn và chính sách thu hồi phù hợp, rồi ánh xạ chứng chỉ/khóa đáng tin vào chủ thể hoặc thiết bị đã đăng ký. Không tự động cấp quyền cho người có cùng chuỗi tên \`CN\` hay email trong chứng chỉ.

Với **federated identity**, credential chính có thể ở IdP thay vì ứng dụng nội bộ. RP nhận thông điệp OIDC/SAML đã được xác minh, sau đó dùng định danh ổn định theo issuer để gắn danh tính ngoài với tài khoản. Đặc biệt, **email trùng không đủ để tự ghép tài khoản**: email có thể thay đổi, tái cấp phát hoặc được xác minh theo chính sách khác giữa các IdP. Quy trình linking phải chứng minh quyền kiểm soát tài khoản nội bộ và danh tính ngoài theo mức rủi ro.

## 7. Ràng buộc giao dịch để chống replay và nhầm tài khoản

Một hệ thống an toàn không chỉ kiểm chứng rằng **bằng chứng có thể đúng**, mà còn phải kiểm chứng **bằng chứng dành cho đúng yêu cầu hiện tại**.

Giả sử server chấp nhận cùng một mã xác minh nhiều lần, hoặc không gắn giao dịch thêm passkey với tài khoản đang đăng nhập. Kẻ tấn công có thể thử phát lại phản hồi cũ, thay ID trong yêu cầu, hoặc khiến nạn nhân vô tình đăng ký credential cho tài khoản do kẻ tấn công kiểm soát.

Một bản ghi giao dịch binding có thể mô tả như sau:

~~~text
PendingCredentialBinding
  transaction_id:   <ID khó đoán>
  account_id:       u-1024
  tenant_id:        org-27
  purpose:          add_webauthn_credential
  challenge:        <giá trị ngẫu nhiên mới>
  initiated_by:     <phiên/ngữ cảnh đủ tin cậy>
  created_at:       <thời điểm khởi tạo>
  expires_at:       <thời hạn>
  consumed:         false
~~~

Các kiểm tra phải được thực hiện **trên server**:

- Đối chiếu challenge/mã với **giao dịch đang chờ**, đúng mục đích, tài khoản và tenant; không cho client tự thay chủ tài khoản.
- Kiểm tra hạn và trạng thái đã tiêu thụ; phản hồi đã thành công không được thực hiện lại.
- Kiểm tra **origin/RP ID** với WebAuthn, hoặc issuer/audience/nonce/state với federation theo giao thức; không dùng các khái niệm này thay cho nhau.
- Ghi và chuyển trạng thái bằng thao tác nguyên tử để hai yêu cầu đồng thời không cùng được chấp nhận.
- Kết hợp CSRF protection, SameSite/Origin kiểm tra phù hợp khi endpoint dựa trên cookie phiên của trình duyệt.

**Challenge chống replay không thay thế xác minh quyền yêu cầu.** Một kẻ tấn công đang có phiên bị đánh cắp vẫn có thể khởi tạo challenge hoàn toàn mới. Vì vậy, thêm credential thường là thao tác nhạy cảm đòi hỏi xác thực lại, tín hiệu rủi ro, thông báo hoặc kiểm soát tăng cường.

## 8. Mã giả: thêm passkey vào tài khoản đang hoạt động

Ví dụ dưới đây mô tả một kiến trúc server quản lý binding bằng hai bước. Đây là **mã giả định hướng thiết kế**, không phải thư viện WebAuthn hoàn chỉnh. Trong triển khai thật, dùng thư viện WebAuthn được duy trì để xử lý CBOR, client data, attestation, cờ và kiểm tra giao thức.

~~~text
beginAddPasskey(authenticatedSession, requestContext):
    account = requireValidSession(authenticatedSession)
    require account.active
    require authorizedForCredentialChanges(account, authenticatedSession)
    require recentEnoughAuthenticationOrStepUp(account, requestContext)
    require abusePolicy.allows(account, requestContext)

    tx = createPendingTransaction(
        purpose = "add_passkey",
        accountId = account.id,
        tenantId = account.tenantId,
        sessionBinding = authenticatedSession.id,
        challenge = secureRandomChallenge(),
        expiresSoon = true
    )

    return generateWebAuthnRegistrationOptions(
        challenge = tx.challenge,
        rpId = configuredRpId(),
        userHandle = stableOpaqueUserHandle(account),
        userVerification = policy.requiredUserVerification()
    )

finishAddPasskey(authenticatedSession, transactionId, response):
    account = requireValidSession(authenticatedSession)
    tx = requireActivePendingTransaction(transactionId)
    require tx.accountId == account.id
    require tx.tenantId == account.tenantId
    require tx.sessionBinding == authenticatedSession.id
    require tx.purpose == "add_passkey"
    require tx.notExpired and not tx.consumed

    verified = webAuthnLibrary.verifyRegistrationResponse(
        response = response,
        expectedChallenge = tx.challenge,
        expectedOrigin = configuredAllowedOrigin(),
        expectedRpId = configuredRpId(),
        requireUserPresence = true,
        requireUserVerification = policy.requiredUserVerification(),
        attestationPolicy = configuredAttestationPolicy()
    )
    require verified.valid
    require not credentialIdAlreadyRegistered(verified.credentialId)

    atomicTransaction:
        consumePendingTransaction(tx)
        insertCredentialBinding(
            accountId = account.id,
            tenantId = account.tenantId,
            credentialId = verified.credentialId,
            publicKey = verified.publicKey,
            status = "active",
            metadata = verified.allowedMetadata
        )

    auditWithoutSecrets("credential_added", account.id)
    notifyAccountOwnerOfNewCredential(account.id)
    return success()
~~~

Các tính chất bắt buộc của ví dụ:

1. **Account ID lấy từ phiên đã xác minh** và giao dịch pending; client không được quyết định \`accountId\` ở bước hoàn tất.
2. **Chính sách step-up độc lập với verify registration.** Ngay cả một registration WebAuthn có challenge hợp lệ cũng không chứng minh người điều khiển phiên là chủ tài khoản được phép thêm phương thức đăng nhập.
3. **Giao dịch chỉ tiêu thụ một lần** và lưu credential bằng thao tác nguyên tử. Trong ứng dụng thực tế, kiểm tra credential trùng cần đặt cả ở **ràng buộc duy nhất của database**, không chỉ gọi \`credentialIdAlreadyRegistered\` trước khi ghi.
4. **Phản hồi trình duyệt là đầu vào chưa tin cậy.** Chỉ dữ liệu trả về từ thư viện đã kiểm chứng mới có thể dùng để lưu khóa công khai, credential ID và metadata.
5. **Không bắt buộc đưa khóa riêng lên server**. Trong WebAuthn, server giữ khóa công khai cho lần xác minh chữ ký đăng nhập sau này.

## 9. Các con đường tấn công vào credential binding

| Lỗ hổng | Kịch bản | Phòng vệ cốt lõi |
| --- | --- | --- |
| **Unauthorized enrollment** | Kẻ tấn công chiếm phiên và thêm passkey hoặc TOTP của họ vào tài khoản nạn nhân. | Xác thực lại theo rủi ro, kiểm tra quyền, thông báo thay đổi, thu hồi phiên khi có sự cố. |
| **IDOR / sai chủ tài khoản** | Endpoint nhận \`userId\` từ request, người dùng A gắn credential vào tài khoản B. | Account/tenant lấy từ ngữ cảnh server đã xác minh, ủy quyền trên mọi thao tác. |
| **Replay** | Gửi lại một phản hồi đăng ký hoặc mã OTP đã dùng. | Challenge ngắn hạn, trạng thái một lần, transaction binding, kiểm tra replay và giao dịch nguyên tử. |
| **Cross-origin / RP confusion** | Dùng bằng chứng WebAuthn cho nguồn gốc hoặc RP khác. | Kiểm tra origin và RP ID theo cấu hình tin cậy; không nhận URL tùy ý từ client. |
| **Credential reassignment** | Một credential ID đang thuộc tài khoản A bị đăng ký sang B. | Ràng buộc duy nhất, từ chối việc chiếm lại; xử lý di chuyển credential bằng quy trình đặc biệt được duyệt. |
| **TOTP setup leak** | Secret trong QR được chụp hoặc log, người lạ tạo được OTP. | Chỉ hiển thị qua kênh bảo vệ, không log, bảo vệ lưu trữ, xác nhận trước khi kích hoạt và có thể thu hồi. |
| **Federated account takeover** | IdP khác cung cấp email giống tài khoản đang tồn tại; ứng dụng tự ghép. | Liên kết theo định danh ổn định đã xác minh, xác minh sở hữu tài khoản nội bộ. |
| **Recovery bypass** | Người gọi hỗ trợ chỉ biết tên/email đã được cấp credential thay thế. | Quy trình khôi phục có bằng chứng độc lập, chống thao túng và audit. |
| **Delete-last-factor** | Người dùng hoặc kẻ tấn công xóa phương thức đăng nhập cuối cùng. | Cảnh báo, kiểm tra bước xác thực lại, yêu cầu đường khôi phục còn hiệu lực. |
| **Race condition** | Hai yêu cầu cùng hoàn tất giao dịch hoặc ghi liên kết trùng. | Transaction nguyên tử và unique constraint ở tầng lưu trữ. |
| **Tenant confusion** | Credential của tenant A được chấp nhận ở tenant B chỉ vì trùng username. | Lưu và kiểm tra định danh tenant cùng account/issuer/scope. |

Không nên dùng **device fingerprint, user agent, vị trí IP hoặc nhãn thiết bị** như bằng chứng duy nhất rằng người dùng kiểm soát authenticator. Các thông tin này có thể thay đổi, bị giả mạo hoặc được nhiều người dùng chia sẻ; chúng phù hợp hơn làm **tín hiệu rủi ro bổ trợ**.

## 10. Thu hồi, thay thế và khôi phục credential

### 10.1. Mất thiết bị hoặc nghi lộ credential

Ví dụ người dùng mất khóa bảo mật, nhưng vẫn còn một passkey khác:

1. Đăng nhập bằng credential còn hợp lệ, sau đó **xác thực lại** với mức bảo đảm thích hợp cho thao tác quản lý phương thức.
2. Liệt kê credential đang gắn với tài khoản dưới dạng tên dễ nhận biết, thời điểm tạo hoặc lần sử dụng; không lộ secret.
3. Chọn đúng credential mất và **thu hồi** bản ghi liên kết ở server.
4. Đăng ký credential mới qua một ceremony có kiểm chứng. Việc thay thế không cần làm cho credential bị mất sống lại.
5. Ghi audit, gửi thông báo, xem xét các phiên/token có thể đã được cấp bằng credential bị nghi xâm phạm và thu hồi khi chính sách yêu cầu.

Thu hồi liên kết ở server ngăn **những lần đăng nhập mới** dùng credential đó. Nếu một phiên hợp lệ đã được tạo trước khi thu hồi, phiên ấy có thể tiếp tục hoạt động; cần chính sách phiên riêng để xử lý. Với chứng chỉ, có thể cần thêm các biện pháp quản lý vòng đời PKI, danh sách thu hồi hoặc cơ chế kiểm tra trạng thái chứng chỉ tùy kiến trúc.

### 10.2. Mất toàn bộ phương thức đăng nhập

Trường hợp này không thể đơn giản yêu cầu “xác thực lại bằng credential hiện có”. Cần một **quy trình khôi phục đã thiết kế trước**: mã phục hồi một lần đủ mạnh, credential dự phòng, xác minh qua người/quy trình đáng tin cậy hoặc các phương thức phù hợp với mức bảo đảm của tài khoản.

Đối với tài khoản có quyền cao, thay đổi credential qua khôi phục có thể yêu cầu thêm kiểm soát như thời gian chờ, xác nhận ngoài băng, duyệt theo vai trò và thông báo rõ ràng. Tránh câu hỏi bảo mật dựa trên thông tin dễ tìm, mã cố định hoặc bỏ qua xác minh do người yêu cầu tự nhận là “đã mất điện thoại”.

### 10.3. Password reset và thay đổi email/IdP

**Đặt lại mật khẩu** thực chất là thay thế credential của tài khoản. Liên kết mới phải được thiết lập qua bằng chứng khôi phục đủ tin cậy, mã reset có thời hạn và chỉ dùng một lần; sau đó xử lý phiên cũ nếu cần.

**Thay đổi email hoặc IdP** có thể ảnh hưởng con đường truy cập và khôi phục. Đây là thao tác thay đổi thuộc tính liên hệ hoặc liên kết danh tính, không được tự gắn credential mới cho tài khoản cũ chỉ vì địa chỉ email vừa khớp. Nên xác minh quyền kiểm soát theo luồng rõ ràng và thông báo các thay đổi có nguy cơ cao.

## 11. Credential binding và bảo vệ token/phiên

Sau khi credential được xác minh trong lần đăng nhập, ứng dụng thường cấp một **session cookie** hoặc **access token**. Đây là đối tượng khác với credential đăng nhập gốc:

~~~text
Credential đã được gắn với tài khoản
             |
             v
Kiểm chứng credential ở lần đăng nhập hiện tại
             |
             v
Cấp session/token có phạm vi và thời hạn riêng
             |
             v
API kiểm tra phiên/token và quyền trên tài nguyên
~~~

**Bearer token** thường dùng được bởi bất cứ ai nắm giữ nó. Kẻ tấn công đánh cắp token có thể không cần biết mật khẩu hoặc có passkey. Các biện pháp như bảo vệ cookie (\`Secure\`, \`HttpOnly\`, \`SameSite\` phù hợp), TTL, xoay vòng refresh token, thu hồi phiên và xác thực lại cho thao tác quan trọng vẫn cần được thiết kế riêng.

Trong một số hệ thống OAuth, **sender-constrained access token** ràng buộc token với khóa của bên gửi, chẳng hạn qua **mTLS** hoặc **DPoP**, giúp giảm khả năng sử dụng token chỉ bằng cách sao chép chuỗi token. Với DPoP, phía tiếp nhận còn phải kiểm tra proof phù hợp với yêu cầu, khóa, thời gian, định danh proof dùng một lần và các trường ràng buộc liên quan theo đặc tả. Đây là **token binding** ở tầng sử dụng token; nó **không thay thế** việc gắn credential đăng nhập với tài khoản an toàn.

Phân biệt này đặc biệt quan trọng khi thiết kế SSO/federation: IdP xác thực danh tính và ứng dụng kiểm tra kết quả giao thức, nhưng ứng dụng vẫn phải quản lý credential/link, phiên của mình và quyền truy cập tài nguyên.

## 12. Tình huống thiết kế: cho phép nhân viên thêm passkey

Một cổng nội bộ đã sử dụng mật khẩu + TOTP. Nhóm phát triển muốn nhân viên thêm passkey để đăng nhập nhanh và giảm phishing. Đề xuất ban đầu:

> Người dùng mở mục Bảo mật, bấm “Thêm passkey”, server lưu khóa công khai từ phản hồi WebAuthn và hiển thị “Thành công”.

Đề xuất thiếu các kiểm tra quan trọng. Nếu cookie phiên bị lấy cắp, người lạ có thể thêm passkey của họ. Nếu callback không gắn với account/tenant và challenge, phản hồi có thể bị dùng sai giao dịch. Nếu dữ liệu bị ghi không nguyên tử, có thể tạo liên kết trùng.

### Thiết kế có thể triển khai theo lớp

| Bước | Kiểm soát | Lý do |
| --- | --- | --- |
| 1. Mở màn hình thêm passkey | Kiểm tra phiên và quyền quản lý credential của **chính** tài khoản. | Chặn IDOR và truy cập không được phép. |
| 2. Xác thực lại | Yêu cầu TOTP hoặc phương thức hiện có theo mức bảo đảm, xem xét tuổi phiên và tín hiệu rủi ro. | Một cookie cũ bị chiếm không đủ để thêm credential mới. |
| 3. Khởi tạo WebAuthn | Tạo challenge ngẫu nhiên, giao dịch pending, gắn account/tenant/phiên/RP ID, hạn ngắn. | Bằng chứng đúng cho một lần đăng ký cụ thể. |
| 4. Kiểm chứng phản hồi | Xác minh dữ liệu WebAuthn bằng thư viện tin cậy, origin, RP ID, challenge và chính sách UV/attestation. | Tránh chấp nhận phản hồi giả hoặc sai website. |
| 5. Lưu binding | Dùng unique constraint, transaction nguyên tử, trạng thái \`active\`. | Ngăn replay, ghi trùng, chuyển credential sang tài khoản khác. |
| 6. Kết thúc | Thông báo thêm credential, ghi audit và hiển thị cách thu hồi. | Hỗ trợ phát hiện thay đổi bất thường và phản ứng sự cố. |

### Hai phản ví dụ cần phân biệt

**Tình huống A:** Nhân viên dùng passkey đồng bộ trên điện thoại rồi đăng nhập được trên máy tính qua cơ chế hệ sinh thái hỗ trợ. Điều đó **không mặc nhiên là lỗi binding**: credential vẫn có thể hợp lệ cho đúng RP/tài khoản. Nếu chính sách bắt buộc khóa phần cứng không thể xuất, phải chọn và xác minh loại authenticator phù hợp.

**Tình huống B:** Nhân viên cho người khác mượn điện thoại đang mở khóa, và người đó dùng phiên đăng nhập sẵn để bấm “Thêm passkey”. Nếu ứng dụng không yêu cầu xác thực lại hoặc kiểm soát thao tác nhạy cảm, người kia có thể thêm credential riêng dù ceremony WebAuthn mới hoàn toàn hợp lệ. **Tính hợp lệ mật mã của credential mới không tự chứng minh thẩm quyền thêm credential vào tài khoản.**

## 13. Quan sát, vận hành và kiểm tra

Các sự kiện liên quan binding nên có khả năng truy vết:

- Yêu cầu bắt đầu và hoàn tất đăng ký credential; loại credential; kết quả, thời điểm, account/tenant và giao dịch tương quan.
- Số lần xác minh mã TOTP hoặc challenge sai, hết hạn, lặp lại; số lần vượt ngưỡng chống lạm dụng.
- Việc thêm, gỡ, đổi credential hoặc kênh khôi phục; thay đổi từ môi trường/thiết bị lạ.
- Các lần đăng nhập dùng credential vừa được thêm và sự kiện thu hồi sau khi phát hiện xâm phạm.

Log nên chứa **metadata tối thiểu cần thiết**, tránh ghi mật khẩu, seed TOTP, mã OTP, recovery code, token, session ID thô hoặc vật liệu khóa riêng. Khi cần điều tra, có thể dùng ID định danh nội bộ hoặc dấu vết có kiểm soát truy cập.

Nên thử nghiệm các trường hợp âm tính trước khi triển khai:

1. Người dùng A sửa \`accountId\` thành B trong request hoàn tất đăng ký: **phải bị từ chối**.
2. Phản hồi WebAuthn có challenge đúng nhưng origin/RP ID sai: **phải bị từ chối**.
3. Dùng lại phản hồi đã xử lý hoặc giao dịch hết hạn: **phải bị từ chối**.
4. Hai yêu cầu đồng thời đăng ký cùng credential ID ở hai tài khoản: **không được ghi hai liên kết hoạt động**.
5. Mã TOTP khởi tạo sai hoặc secret pending không được xác minh: **không kích hoạt MFA**.
6. Thu hồi một passkey: credential đó **không đăng nhập mới được**, nhưng các passkey hợp lệ khác của tài khoản vẫn có thể hoạt động.
7. Người dùng mất mọi credential: chỉ được đi qua **luồng khôi phục đã được phê duyệt**, không tự thêm passkey qua tên/email đơn thuần.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao server cần biết *ai được phép thêm passkey* trước khi kiểm tra response WebAuthn?

**Gợi ý:** Registration ceremony xác minh credential mới cho RP; nó không tự chứng minh phiên đang thao tác là phiên của chủ tài khoản hợp pháp.

**Câu 2.** Sau khi người dùng quét QR để bật TOTP, có nên đặt \`status=active\` ngay không?

**Gợi ý:** Chưa. Cần yêu cầu mã TOTP hợp lệ từ secret pending để xác nhận khả năng tạo mã, rồi mới kích hoạt.

**Câu 3.** Hai tài khoản có cùng email từ hai IdP khác nhau thì có thể tự động dùng chung credential không?

**Gợi ý:** Không. Cần kiểm chứng giao thức và liên kết định danh ngoài bằng khóa ổn định và quy trình xác nhận sở hữu tài khoản nội bộ.

**Câu 4.** Nếu xóa binding của passkey bị mất, mọi phiên được tạo trước đó có lập tức hết hiệu lực không?

**Gợi ý:** Không nhất thiết. Vòng đời credential và phiên khác nhau; cần cơ chế thu hồi hoặc thời hạn phiên phù hợp.

**Câu 5.** Vì sao passkey đồng bộ không đồng nghĩa với một credential gắn chặt vào một thiết bị vật lý?

**Gợi ý:** Nền tảng có thể đồng bộ vật liệu khóa và làm credential sử dụng được trên nhiều thiết bị. Yêu cầu khóa không thể xuất là một chính sách và khả năng xác minh riêng.

## 15. Ghi nhớ

**Credential binding là quyết định tin cậy về việc bằng chứng xác thực nào thuộc về tài khoản nào, ai được phép thiết lập liên kết đó và bằng chứng còn hợp lệ trong bao lâu.** Một binding an toàn đòi hỏi xác định đúng chủ tài khoản, kiểm tra thẩm quyền thêm/thay credential, chứng minh quyền kiểm soát bằng cơ chế thích hợp, ràng buộc bằng chứng với giao dịch để chống replay, lưu trạng thái nguyên tử và có quy trình thu hồi/khôi phục. Đây là nền tảng để mật khẩu, MFA, passkey, chứng chỉ và danh tính liên kết có thể được sử dụng trong một hệ thống xác thực an toàn.
