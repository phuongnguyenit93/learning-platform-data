# Passkey là gì? — Xác thực bằng khóa công khai thay cho mật khẩu

> **Chương:** Passkey và WebAuthn  
> **Chủ đề:** Passkey là gì  
> **Phạm vi:** Bài học thuộc module SECURITY_AUTHENTICATION_FUNDAMENTALS, tìm hiểu xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này giới thiệu passkey, cơ chế khóa công khai của WebAuthn/FIDO2, khả năng chống phishing, ranh giới tin cậy và vòng đời credential.

## 1. Passkey là gì?

**Passkey** là một credential đăng nhập dựa trên mật mã khóa công khai. Thay vì gửi một mật khẩu dùng chung bí mật tới server, thiết bị hoặc authenticator của người dùng giữ **khóa riêng (private key)** và dùng nó để ký một thử thách do dịch vụ tạo ra. Dịch vụ chỉ lưu **khóa công khai (public key)** cùng thông tin credential cần thiết để xác minh chữ ký.

Khi đăng nhập, website tạo challenge mới. Authenticator dùng khóa riêng tương ứng để ký dữ liệu xác thực; server kiểm tra chữ ký bằng public key đã đăng ký, đồng thời kiểm tra challenge, website đang yêu cầu xác thực và các điều kiện giao thức. Khóa riêng không được gửi lên website trong quy trình WebAuthn thông thường.

Ví dụ, Mai đăng ký passkey cho `learn.example`. Khi quay lại website, Mai chọn tài khoản hoặc chọn passkey được đề xuất. Điện thoại/laptop/khóa bảo mật yêu cầu Mai mở khóa bằng sinh trắc học, PIN hoặc thao tác phù hợp, sau đó ký challenge. Server xác minh chữ ký và xác định account gắn với credential. Mai không phải nhập mật khẩu.

**Điểm cốt lõi:** passkey không phải một mật khẩu dài được lưu trong trình duyệt. Nó là credential mật mã dùng một cặp khóa, có thể được bảo vệ bởi thiết bị và/hoặc đồng bộ an toàn giữa các thiết bị tùy loại passkey.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích passkey là credential khóa công khai và phân biệt public key, private key, credential ID, account ID.
2. Mô tả hai nghi thức WebAuthn: đăng ký credential và xác thực credential.
3. Giải thích vì sao ràng buộc RP ID/origin giúp passkey chống phishing.
4. Phân biệt user presence (UP), user verification (UV), passkey đồng bộ và credential gắn thiết bị.
5. Hiểu giới hạn của passkey, vai trò của MFA, attestation, recovery và quản lý vòng đời.
6. Đánh giá cách tích hợp passkey với session, token, tenant, liên kết danh tính và chính sách xác thực.

## 2. Passkey dựa trên WebAuthn và FIDO2 như thế nào?

Passkey thường được triển khai bằng **Web Authentication API (WebAuthn)**, một tiêu chuẩn web của W3C, và hệ sinh thái FIDO. WebAuthn định nghĩa cách trình duyệt/ứng dụng giao tiếp với authenticator để tạo và sử dụng public-key credential. FIDO2 thường được nhắc đến như sự kết hợp giữa WebAuthn và giao thức CTAP dùng để giao tiếp với authenticator bên ngoài hoặc nền tảng.

Các thành phần chính:

| Thành phần | Vai trò |
| --- | --- |
| **Relying Party (RP)** | Website/dịch vụ muốn xác thực người dùng; có RP ID, ví dụ `learn.example`. |
| **Client** | Trình duyệt hoặc ứng dụng gọi WebAuthn API, cung cấp origin và chuyển dữ liệu giữa RP với authenticator. |
| **Authenticator** | Thiết bị hoặc phần mềm tạo/giữ credential và thực hiện thao tác xác thực. Có thể là platform authenticator hoặc roaming authenticator. |
| **Credential** | Cặp khóa và dữ liệu liên quan được tạo cho một RP; server lưu public key và credential metadata cần thiết. |
| **RP server** | Sinh challenge, lưu credential, kiểm tra response và tạo principal/session khi xác minh thành công. |
| **User agent / OS** | Điều phối lựa chọn passkey, xác minh người dùng cục bộ, quyền truy cập credential và đồng bộ nếu nền tảng hỗ trợ. |

Sơ đồ tổng quan:

~~~mermaid
flowchart LR
    U["Người dùng"] --> A["Authenticator / Passkey"]
    A <-->|"WebAuthn / CTAP"| C["Trình duyệt hoặc ứng dụng"]
    C <-->|"HTTPS + WebAuthn response"| R["RP server"]
    R <--> DB[("Credential store: public key, credential ID")]
    R --> S["Principal và session"]
~~~

**RP** là dịch vụ mà credential được tạo cho. **Authenticator** là bên giữ và sử dụng khóa riêng. **Client** vận chuyển dữ liệu và cung cấp thông tin về origin. **Server** chịu trách nhiệm xác minh toàn bộ response trước khi chấp nhận đăng nhập.

Không nên nhầm RP ID với hostname do client tự gửi. RP ID được xác định theo origin và quy tắc WebAuthn; server phải cấu hình rõ RP ID hợp lệ cho từng môi trường. Một credential được tạo cho RP này không được phép sử dụng tùy tiện cho RP khác.

## 3. Mật mã khóa công khai: vì sao server không cần biết private key?

Khi đăng ký passkey, authenticator tạo cặp khóa:

- **Private key:** được giữ trong authenticator hoặc hệ thống quản lý passkey của người dùng; dùng để ký challenge. Server không cần nhận private key.
- **Public key:** được gửi về RP trong kết quả đăng ký; server lưu để xác minh chữ ký ở các lần đăng nhập.
- **Credential ID:** định danh credential mà authenticator trả về để RP tra cứu đúng bản ghi public key.
- **User handle:** định danh opaque do RP quản lý, gắn credential với account; không nên coi nó là email hoặc dữ liệu cá nhân cần công khai.

Một sơ đồ đơn giản:

~~~text
Đăng ký:
  Authenticator tạo:
    private key  -> giữ ở phía authenticator
    public key   -> gửi RP server
  RP lưu:
    credential ID + public key + account/user handle + metadata

Đăng nhập:
  RP gửi challenge ngẫu nhiên
  Authenticator ký dữ liệu chứa challenge và ngữ cảnh RP
  RP xác minh chữ ký bằng public key đã lưu
~~~

Với mật khẩu truyền thống, server cần lưu password verifier (hash có salt và chi phí phù hợp) để kiểm tra bí mật người dùng nhập. Với passkey, server không lưu một bí mật chung có thể dùng để giả chữ ký; nó lưu public key. Nếu database public key bị đọc, kẻ tấn công vẫn không thể tạo chữ ký hợp lệ nếu không có private key tương ứng, dù server vẫn phải bảo vệ dữ liệu, metadata và các luồng thay credential.

Không nên tự xây thuật toán chữ ký hoặc protocol xác thực. WebAuthn response chứa nhiều trường và cần xác minh theo chuẩn bằng thư viện phía server đã được kiểm chứng.

## 4. Đăng ký passkey (registration ceremony)

Đăng ký là bước gắn một public-key credential với account. Nếu luồng này yếu, kẻ tấn công có thể thêm passkey của mình vào tài khoản nạn nhân rồi đăng nhập về sau. Vì vậy, trước khi cho phép đăng ký, RP phải xác thực account hiện tại và áp dụng chính sách quản lý credential.

### Các bước cơ bản

1. Người dùng đã có account và đang ở một phiên đủ tin cậy; thao tác thêm passkey có thể yêu cầu xác thực lại.
2. RP server tạo challenge ngẫu nhiên, ngắn hạn, gắn với account, session và mục đích đăng ký.
3. Server gửi public-key creation options cho client: challenge, RP, user handle, thuật toán được chấp nhận, authenticator selection và các điều kiện khác.
4. Client gọi `navigator.credentials.create()`; authenticator tạo credential cho RP và yêu cầu user presence/user verification theo lựa chọn.
5. Client gửi attestation object, client data và credential ID về server.
6. Server xác minh challenge, origin, RP ID hash, kiểu ceremony, trạng thái user presence/verification, dữ liệu public key và các điều kiện policy.
7. Server lưu credential ID, public key, user handle, thông tin authenticator cần thiết và trạng thái; ghi audit.
8. Server thông báo đã thêm passkey qua kênh phù hợp và cho phép người dùng quản lý/thu hồi credential.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant C as Browser / Client
    participant R as RP Server
    participant A as Authenticator
    U->>C: Chọn "Thêm passkey"
    C->>R: POST /webauthn/register/options
    R-->>C: challenge + creation options
    C->>A: navigator.credentials.create()
    A-->>C: credential + attestation response
    C->>R: POST /webauthn/register/complete
    R->>R: Verify challenge, origin, RP ID, flags, key
    R->>R: Lưu credential gắn với account
    R-->>U: Xác nhận đăng ký thành công
~~~

### Challenge phải gắn với đúng giao dịch

Challenge cần đủ ngẫu nhiên, có thời hạn, chỉ dùng một lần và lưu ở server hoặc được bảo vệ theo cơ chế tin cậy. Server phải kiểm tra challenge trả về khớp với challenge của phiên đăng ký hiện tại. Không nhận account ID tùy ý từ client để gắn public key; account được xác định từ phiên đã xác thực.

Nếu có hai request đăng ký song song hoặc một challenge cũ được gửi lại, server cần từ chối challenge đã hết hạn/đã dùng. Không lưu credential nếu bất kỳ kiểm tra quan trọng nào thất bại.

### Attestation có phải lúc nào cũng cần?

Attestation có thể cung cấp thông tin về loại authenticator hoặc nguồn gốc của credential, nhưng không phải mọi dịch vụ đều cần thu thập hoặc kiểm tra attestation. Attestation có hệ quả về quyền riêng tư, tương thích và vận hành; policy cần xác định có yêu cầu hay không và tin loại attestation nào. Không mặc định attestation chứng minh danh tính người dùng ngoài đời.

## 5. Đăng nhập bằng passkey (authentication ceremony)

Khi người dùng đăng nhập, server tạo challenge mới và yêu cầu authenticator chứng minh quyền kiểm soát private key.

1. Client bắt đầu đăng nhập; có thể người dùng nhập username trước hoặc dùng passkey discoverable để chọn tài khoản mà không cần nhập tên.
2. RP server tạo challenge mới, lưu trạng thái giao dịch và trả về request options.
3. Client gọi `navigator.credentials.get()`; trình duyệt/authenticator tìm credential phù hợp với RP ID.
4. Authenticator yêu cầu thao tác hiện diện hoặc xác minh người dùng tùy policy, rồi ký dữ liệu xác thực.
5. Client gửi assertion response về server.
6. Server tìm credential bằng credential ID hoặc user handle, xác minh chữ ký bằng public key đã lưu.
7. Server kiểm tra challenge, origin, RP ID hash, cờ UP/UV, trạng thái account/credential và các quy tắc bổ sung.
8. Nếu tất cả điều kiện đạt, server tạo principal từ account ID nội bộ và cấp session mới.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant C as Browser
    participant R as RP Server
    participant A as Authenticator
    U->>C: Chọn đăng nhập bằng passkey
    C->>R: POST /webauthn/auth/options
    R-->>C: challenge + request options
    C->>A: navigator.credentials.get()
    A-->>C: assertion (credential ID, authenticator data, signature)
    C->>R: POST /webauthn/auth/complete
    R->>R: Find credential + verify signature
    R->>R: Verify challenge, origin, RP ID, UP/UV, policy
    R-->>C: Session cookie / result
~~~

### Challenge không được dùng lại

Mỗi lần xác thực cần challenge mới, không đoán được, có thời hạn và gắn với giao dịch hiện tại. Server từ chối response nếu challenge sai, hết hạn hoặc đã được sử dụng. Điều này ngăn response cũ được phát lại như một lần đăng nhập mới.

Không chỉ kiểm tra chữ ký. Một response có chữ ký hợp lệ nhưng origin không được phép, RP ID hash không đúng hoặc challenge không thuộc giao dịch hiện tại vẫn phải bị từ chối.

## 6. RP ID và origin: cơ chế nền tảng chống phishing

Một trong những lợi ích lớn của WebAuthn là bằng chứng xác thực được ràng buộc với **relying party**. Trang giả mạo ở `learn-example.attacker.test` không thể đơn giản yêu cầu authenticator ký một bằng chứng có thể sử dụng như đăng nhập cho `learn.example`.

Cần phân biệt:

- **Origin:** gồm scheme, host và port theo mô hình web; ví dụ `https://learn.example`.
- **RP ID:** định danh relying party được dùng trong WebAuthn; thường là domain hiện tại hoặc domain cha được phép theo quy tắc trình duyệt.
- **RP ID hash:** giá trị hash của RP ID được authenticator ghi trong authenticator data; server kiểm tra đúng giá trị mong đợi.
- **Challenge:** dữ liệu mới do RP tạo, gắn với lần đăng ký hoặc đăng nhập.
- **Client data:** chứa loại thao tác, challenge và origin; server phải parse và xác minh đúng.

Ví dụ:

~~~text
Website thật:
  Origin = https://learn.example
  RP ID  = learn.example

Website giả:
  Origin = https://learn-example.attacker.test

Passkey được tạo cho learn.example:
  authenticator không tạo assertion hợp lệ cho RP ID của website giả.
~~~

Ràng buộc này tạo **phishing resistance** ở tầng giao thức. Người dùng không cần tự phân biệt mọi ký tự trong URL để private key không bị dùng cho một RP khác. Tuy vậy, server phải kiểm tra origin/RP ID đúng; cấu hình RP ID quá rộng hoặc tin origin tùy ý có thể phá hỏng ranh giới bảo vệ.

### Domain và môi trường triển khai

- Dùng HTTPS cho website production (localhost có ngoại lệ phát triển theo quy tắc WebAuthn).
- Cấu hình danh sách origin chính xác, tránh wildcard quá rộng.
- Nếu có nhiều subdomain, quyết định rõ RP ID chung hay riêng và hiểu credential có thể dùng trên phạm vi nào.
- Custom domain phải được xác minh quyền kiểm soát và quản lý vòng đời; không tự thêm domain từ Host header.
- Môi trường staging/dev nên có RP ID tách biệt để tránh nhầm credential với production.

## 7. User Presence (UP) và User Verification (UV)

Hai cờ trong authenticator data thường bị hiểu nhầm:

| Cờ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **UP — User Presence** | Authenticator xác nhận có thao tác hiện diện của người dùng, ví dụ chạm khóa bảo mật. | Người dùng chạm security key để tiếp tục. |
| **UV — User Verification** | Authenticator đã thực hiện xác minh người dùng cục bộ theo cơ chế của nó. | Mở khóa passkey bằng PIN hoặc sinh trắc học. |

UP không đồng nghĩa người dùng đã được xác minh bằng sinh trắc/PIN. UV cũng không phải bằng chứng server đã nhận được dữ liệu sinh trắc. Authenticator thường chỉ trả tín hiệu rằng user verification đã hoàn tất.

Nếu policy yêu cầu UV, server phải kiểm tra cờ UV trong authenticator data đã được xác minh chữ ký và từ chối nếu thiếu. Không tin một boolean `userVerified=true` do client gửi ngoài dữ liệu WebAuthn được kiểm tra.

### Passkey có phải MFA không?

Passkey có thể hỗ trợ **xác thực đa yếu tố trong một thao tác** khi authenticator yêu cầu user verification bằng yếu tố cục bộ phù hợp (ví dụ PIN hoặc sinh trắc) kết hợp với việc kiểm soát credential/thiết bị. Nhưng không nên khẳng định mọi lần dùng passkey đều tự động đạt cùng một mức MFA:

- Nếu policy chỉ yêu cầu user presence, chạm khóa không nhất thiết là một yếu tố knowledge/inherence độc lập.
- Nếu authenticator yêu cầu UV bằng PIN hoặc sinh trắc, server có thể dựa vào cờ UV đã xác minh theo policy.
- Cách bảo vệ khóa, loại authenticator, đồng bộ và quy trình recovery cũng ảnh hưởng mức bảo đảm.
- Một passkey có thể cung cấp đăng nhập không mật khẩu và chống phishing mà không cần ép người dùng nhập thêm mật khẩu chỉ để tạo hai màn hình.

**Phân biệt chống phishing với MFA:** WebAuthn có thể chống phishing nhờ ràng buộc RP ID/origin. Đây là thuộc tính khác với việc một lần xác thực có bao nhiêu yếu tố.

## 8. Discoverable credential và đăng nhập không cần username

WebAuthn hỗ trợ credential có thể được authenticator khám phá (discoverable credential), trước đây thường gọi là resident credential. Khi đăng nhập, người dùng có thể chọn passkey từ trình duyệt hoặc hệ điều hành mà không phải nhập username trước.

Trong luồng này:

- Server có thể gửi request options không chỉ định một danh sách credential ID cụ thể.
- Authenticator hiển thị các passkey phù hợp với RP ID và người dùng chọn một credential.
- Assertion trả về credential ID và có thể có user handle.
- Server dùng credential ID để tìm bản ghi public key và account đã đăng ký.
- Sau khi xác minh chữ ký và challenge, server tạo principal từ account ID nội bộ.

Credential ID không phải account ID, email hoặc bằng chứng tự thân. Server chỉ tin nó như một chỉ mục tra cứu sau khi kiểm tra assertion. Nếu hai account có cùng email, passkey vẫn phải ánh xạ tới đúng account đã đăng ký.

### Username-first và usernameless

| Kiểu đăng nhập | Cách hoạt động | Trường hợp phù hợp |
| --- | --- | --- |
| **Username-first** | Người dùng nhập username/email; server chỉ định credential phù hợp rồi xác minh | Hệ thống cần chọn tenant hoặc account trước, hoặc có UX hiện hữu. |
| **Usernameless/discoverable** | Authenticator liệt kê passkey cho RP; server xác định account từ credential response | Trải nghiệm nhanh, không phải nhớ username. |

Nếu ứng dụng multi-tenant, cần xác định tenant context trước hoặc trong quá trình xác thực theo policy. Không dùng email hoặc tên miền do client tự gửi để tự động chọn tenant và cấp quyền.

## 9. Synced passkey và device-bound credential

Passkey có thể được cung cấp theo nhiều mô hình lưu giữ khóa.

### Synced passkey

Passkey đồng bộ có thể được cung cấp trên nhiều thiết bị thông qua hệ sinh thái quản lý credential của nền tảng hoặc nhà cung cấp. Người dùng có thể đăng nhập trên điện thoại, laptop hoặc thiết bị mới sau khi xác minh tài khoản đồng bộ theo cơ chế của nhà cung cấp.

Ưu điểm:

- Giảm nguy cơ mất toàn bộ khả năng đăng nhập khi mất một thiết bị.
- Trải nghiệm đa thiết bị thuận tiện.
- Có thể khôi phục passkey qua tài khoản đồng bộ của nền tảng.

Điều cần đánh giá:

- Tài khoản đồng bộ trở thành một phần quan trọng của ranh giới tin cậy.
- Mức bảo vệ khóa, backup và recovery phụ thuộc hệ sinh thái và cấu hình.
- Tổ chức có thể cần chính sách thiết bị được quản lý hoặc credential không đồng bộ cho tài khoản đặc quyền.
- Không nên suy ra mọi synced passkey có mức bảo đảm giống nhau.

### Device-bound credential

Credential gắn với thiết bị có thể được bảo vệ bởi phần cứng và không đồng bộ sang thiết bị khác theo cách thông thường. Mô hình này có thể phù hợp khi tổ chức muốn kiểm soát thiết bị hoặc giảm khả năng sao chép credential, nhưng tăng rủi ro khóa tài khoản khi thiết bị hỏng/mất và đòi hỏi quy trình cấp phát/thu hồi.

| Tiêu chí | Synced passkey | Device-bound credential |
| --- | --- | --- |
| Dùng trên nhiều thiết bị | Có thể, qua cơ chế đồng bộ | Thường bị giới hạn vào thiết bị/authenticator |
| Recovery khi mất thiết bị | Có thể khôi phục qua hệ sinh thái đồng bộ | Cần credential dự phòng hoặc quy trình cấp lại |
| Quản trị tổ chức | Phụ thuộc nhà cung cấp và policy | Có thể gắn với quản lý thiết bị/phần cứng |
| Rủi ro chính | Tài khoản đồng bộ và chuỗi khôi phục | Mất thiết bị, provisioning và thu hồi |
| Phù hợp | Người dùng phổ thông, trải nghiệm đa thiết bị | Một số vai trò/thiết bị có yêu cầu kiểm soát cao |

Không phải tất cả passkey đồng bộ đều kém an toàn, và không phải mọi credential gắn thiết bị đều tự động đạt mức bảo đảm cao. Phải đánh giá cơ chế bảo vệ khóa, xác minh người dùng, attestation nếu cần, quản lý thiết bị và recovery.

## 10. Passkey so với mật khẩu, OTP và magic link

| Thuộc tính | Mật khẩu | TOTP/SMS OTP | Magic link | Passkey/WebAuthn |
| --- | --- | --- | --- | --- |
| Bí mật dùng chung lưu ở server | Password verifier | Bí mật TOTP hoặc thông tin gửi mã | Token ngẫu nhiên tạm thời | Không lưu private key; lưu public key |
| Chống phishing theo RP/origin | Không | Không | Không mặc định | Có khi triển khai đúng |
| Replay | Có thể nếu không có biện pháp bổ sung | Có thể trong cửa sổ hiệu lực nếu không chống dùng lại | Token một lần giảm replay sau consume | Challenge mới và chữ ký ràng buộc ngữ cảnh |
| UX | Phải nhớ/nhập | Nhập mã hoặc duyệt push | Mở email và nhấn link | Chọn passkey, xác minh cục bộ |
| Recovery | Reset mật khẩu | Cấp lại authenticator/số | Khôi phục hộp thư/link | Passkey dự phòng hoặc recovery của nền tảng/RP |
| Khả năng MFA | Một yếu tố knowledge | Có thể là yếu tố possession | Quyền truy cập email, không mặc định là MFA | Có thể đáp ứng nhiều yếu tố trong authenticator khi UV theo policy |

Passkey thường giảm rủi ro credential stuffing và phishing so với mật khẩu/OTP nhập tay. Tuy nhiên, nó không tự ngăn mọi chiếm phiên, lỗi phân quyền, chiếm tài khoản đồng bộ hoặc recovery takeover.

## 11. Quản lý vòng đời passkey

Một hệ thống không chỉ cần đăng nhập thành công; nó phải quản lý credential từ lúc thêm đến lúc thu hồi.

### Đăng ký và thêm passkey

- Chỉ account đã xác thực ở mức phù hợp mới được thêm credential.
- Thao tác thêm passkey có thể yêu cầu step-up hoặc reauthentication.
- Challenge đăng ký gắn account/session/purpose và hết hạn nhanh.
- Public key và credential ID được lưu đúng account, tenant context nếu cần.
- Ghi audit, thông báo và hiển thị danh sách thiết bị/passkey cho người dùng.

### Đổi tên và hiển thị thiết bị

Tên như “Laptop công việc” hoặc “Điện thoại cá nhân” giúp người dùng nhận biết credential. Tên này là metadata hiển thị, không phải bằng chứng xác thực. Không dùng user agent hoặc label do client gửi làm tiêu chí cấp quyền đặc biệt nếu chưa xác minh.

### Thu hồi passkey

Khi mất thiết bị hoặc phát hiện credential lạ:

1. Người dùng xác thực bằng một phương thức dự phòng đủ tin cậy hoặc recovery.
2. Server đánh dấu credential bị revoke/disabled.
3. Các lần đăng nhập sau bằng credential đó bị từ chối.
4. Cân nhắc thu hồi session/refresh token đã phát hành trong khoảng có rủi ro.
5. Ghi audit và gửi thông báo qua kênh liên hệ tin cậy.

Không xóa credential chỉ ở UI mà quên trạng thái phía server. API xác thực phải kiểm tra credential còn active trước khi cấp session.

### Credential rotation và counter

Một số authenticator có signature counter hoặc metadata khác có thể hỗ trợ phát hiện clone/credential bất thường. Counter không hoạt động giống nhau trên mọi authenticator, đặc biệt trong môi trường synced passkey; không nên coi counter đứng yên là bằng chứng chắc chắn credential bị clone. Dùng tín hiệu theo hướng dẫn chuẩn và chính sách tương thích, không từ chối nhầm mọi passkey đồng bộ.

## 12. Recovery: mất passkey thì làm gì?

Recovery là phần quan trọng của passwordless. Nếu người dùng mất tất cả thiết bị có passkey, họ cần cách khôi phục account; nếu quy trình recovery yếu, kẻ tấn công có thể bỏ qua passkey.

Các phương án:

- **Nhiều passkey đã đăng ký:** thiết bị hoặc authenticator dự phòng giúp giảm phụ thuộc một thiết bị.
- **Synced passkey:** có thể khôi phục qua tài khoản đồng bộ, tùy nhà cung cấp.
- **Recovery code:** mã khẩn cấp một lần, cần được tạo và lưu an toàn trước khi mất thiết bị.
- **Quy trình hỗ trợ:** kiểm chứng đủ mạnh, có audit, phê duyệt cho account nhạy cảm và chống social engineering.
- **Credential dự phòng khác:** có thể là security key hoặc phương thức được policy cho phép, nhưng không tự hạ yêu cầu chống phishing của vai trò đặc quyền.

Không cho phép reset toàn bộ passkey chỉ bằng email hoặc thông tin cá nhân dễ tra nếu account yêu cầu assurance cao. Khi recovery hoàn tất, có thể đánh dấu phiên vừa khôi phục, thu hồi credential cũ, thông báo độc lập và yêu cầu step-up trước khi thêm thiết bị hoặc thay đổi thông tin thanh toán.

**Recovery không nên yếu hơn mục tiêu bảo mật mà passkey đang bảo vệ.**

## 13. Passkey, MFA và risk-based assurance

Passkey có thể là phương thức xác thực mạnh, nhưng mức assurance thực tế phụ thuộc cách credential được tạo, authenticator, UV, mô hình đồng bộ, policy và recovery.

Ví dụ chính sách:

| Tác vụ | Yêu cầu có thể áp dụng |
| --- | --- |
| Đăng nhập người dùng phổ thông | Passkey hợp lệ theo RP ID/origin; UV theo policy. |
| Xem dữ liệu nhạy cảm | Phiên còn mới và đạt assurance tối thiểu. |
| Thêm/xóa passkey | Reauthentication bằng credential đang tin cậy, challenge riêng, audit. |
| Cấp quyền quản trị | Passkey chống phishing, UV bắt buộc và quy trình phê duyệt nếu cần. |
| Khôi phục account | Bằng chứng theo recovery policy, thu hồi credential cũ và giới hạn hành động sau recovery. |

Không dùng tín hiệu rủi ro như IP quen thuộc để bỏ qua kiểm tra chữ ký hoặc origin. Tín hiệu risk có thể yêu cầu step-up, trì hoãn hoặc từ chối; nó không thể biến một response sai thành response hợp lệ.

Một passkey đã xác minh chỉ chứng minh credential tương ứng được dùng trong ceremony. Server vẫn phải kiểm tra account active, tenant membership, session policy và quyền trên từng resource. **Passkey không phải authorization token.**

## 14. Những lỗi triển khai WebAuthn thường gặp

| Lỗi | Hậu quả | Kiểm soát |
| --- | --- | --- |
| Chỉ kiểm tra chữ ký, bỏ challenge | Response cũ có thể bị replay | Kiểm tra challenge khớp giao dịch, còn hạn và chưa dùng. |
| Không kiểm tra origin | Response từ origin không mong đợi có thể được chấp nhận | Allowlist origin chính xác và xác minh client data. |
| Không kiểm tra RP ID hash | Credential có thể bị dùng sai relying party | So sánh RP ID hash với RP ID đã cấu hình. |
| Tin cờ UP/UV do client gửi | Client giả trạng thái xác minh | Parse authenticator data và xác minh chữ ký; kiểm tra flag trong dữ liệu đó. |
| Đăng ký passkey khi chưa xác thực account | Kẻ tấn công thêm credential của mình | Step-up, ràng buộc registration challenge với account/session. |
| Gắn credential theo email từ request | Nhầm hoặc chiếm account | Dùng account ID nội bộ từ phiên đáng tin và user handle do RP quản lý. |
| Chấp nhận origin wildcard quá rộng | Mở rộng vùng tin cậy ngoài ý muốn | Cấu hình origin/RP ID cụ thể, review domain và staging. |
| Không kiểm tra credential revoked | Thiết bị đã mất vẫn đăng nhập được | Kiểm tra trạng thái server-side trước khi cấp session. |
| Tin signature counter như quy tắc tuyệt đối | Từ chối nhầm synced passkey hoặc bỏ qua tín hiệu clone | Diễn giải theo loại authenticator và hướng dẫn chuẩn. |
| Recovery bằng email yếu | Bỏ qua passkey qua đường vòng | Recovery assurance tương xứng, audit và step-up. |
| Không rotate session sau login | Session fixation | Tạo session ID mới sau xác thực. |

### Ví dụ response không hợp lệ

Một client gửi assertion có chữ ký đúng nhưng challenge không khớp với request hiện tại. Server vẫn phải từ chối. Chữ ký chứng minh một private key đã ký dữ liệu nào đó; nó không chứng minh dữ liệu đó thuộc giao dịch đăng nhập đang chờ.

Tương tự, nếu RP ID hash không đúng, server không được bỏ qua chỉ vì credential ID đã tồn tại trong database.

## 15. Ví dụ API và giả mã server

Một API có thể tách options và completion:

~~~http
POST /webauthn/register/options
Authorization: Bearer <authenticated-session>
~~~

Server trả challenge và creation options, không trả private key.

~~~http
POST /webauthn/register/complete
Content-Type: application/json

{
  "credential": "<public-key-credential-response>"
}
~~~

Đối với đăng nhập:

~~~http
POST /webauthn/auth/options
Content-Type: application/json

{}
~~~

Server tạo challenge mới và request options. Sau khi client hoàn tất WebAuthn:

~~~http
POST /webauthn/auth/complete
Content-Type: application/json

{
  "credential": "<assertion-response>"
}
~~~

Giả mã Java minh họa:

~~~java
LoginResult completeAssertion(AssertionResponse response) {
    PendingChallenge pending =
        challengeStore.requireActive(response.challengeTransactionId());

    VerifiedAssertion assertion =
        webAuthnVerifier.verify(
            response,
            pending.challenge(),
            configuredRpId(),
            allowedOrigins());

    CredentialRecord credential =
        credentialStore.requireActive(assertion.credentialId());

    if (!assertion.signatureValidFor(credential.publicKey())) {
        throw genericAuthenticationFailure();
    }
    if (!assertion.challengeMatches(pending.challenge())
            || !assertion.originAllowed()
            || !assertion.rpIdHashMatches()
            || !pending.consumeAtomically()) {
        throw genericAuthenticationFailure();
    }
    if (pending.requiresUserVerification() && !assertion.userVerified()) {
        throw genericAuthenticationFailure();
    }

    Account account = accountStore.requireActive(credential.accountId());
    Principal principal = Principal.authenticated(
        account.id(), assertion.authenticatedAt(), "WEBAUTHN");

    return sessionService.createFreshSession(principal);
}
~~~

Đây là giả mã để minh họa thứ tự trách nhiệm, không phải implementation hoàn chỉnh. Một thư viện WebAuthn server-side cần xác minh toàn bộ client data, authenticator data, signature, extension, credential status và các quy tắc giao thức. Không tự viết parser hoặc cryptography từ ví dụ.

Trong thực tế, response WebAuthn không có một trường transaction ID tùy ý mà server có thể tin; server cần lưu challenge theo session/correlation context hoặc giao dịch opaque được bảo vệ, rồi xác định đúng bản ghi pending ở phía server.

## 16. Kiểm thử bảo mật và vận hành

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Đăng ký passkey cho account đang xác thực hợp lệ | Lưu public key và credential ID gắn đúng account. |
| Đăng ký challenge hết hạn | Từ chối, không lưu credential. |
| Dùng challenge của account A để đăng ký cho B | Từ chối. |
| Đăng nhập với challenge mới và chữ ký hợp lệ | Xác minh và tạo session mới. |
| Assertion có challenge cũ | Từ chối. |
| Assertion từ origin giả | Từ chối. |
| RP ID hash sai | Từ chối. |
| Chữ ký sai hoặc credential ID không tồn tại | Từ chối. |
| Credential đã revoke | Từ chối. |
| Policy yêu cầu UV nhưng response không có UV | Từ chối. |
| UP có nhưng UV không có | Chỉ chấp nhận nếu policy không yêu cầu UV. |
| Hai request hoàn tất cùng challenge đồng thời | Chỉ một giao dịch được chấp nhận. |
| User chọn passkey discoverable | Server tìm đúng credential/account sau khi xác minh response. |
| Synced passkey có counter không tăng | Xử lý theo policy tương thích, không tự kết luận clone. |
| Thêm passkey sau khi session quá cũ | Yêu cầu reauthentication/step-up. |
| Người dùng báo mất thiết bị | Revoke credential và xử lý session/token theo policy. |
| Account bị khóa sau khi challenge phát hành | Không tạo session khi hoàn tất. |
| RP có nhiều tenant | Kiểm tra membership/tenant context riêng sau xác thực. |

### Vận hành

Theo dõi số lượng passkey đã đăng ký, tỷ lệ thành công/thất bại, loại authenticator theo metadata được phép, lỗi origin/RP ID, challenge hết hạn, credential bị revoke, recovery và tỷ lệ người dùng không thể đăng nhập sau khi đổi thiết bị. Không ghi private key, token, raw challenge nhạy cảm hoặc dữ liệu sinh trắc. Metadata authenticator có thể ảnh hưởng quyền riêng tư; chỉ thu thập phần cần thiết cho policy và hỗ trợ.

## 17. Bài tập tình huống

Một nền tảng đào tạo có hai domain: `learn.example` và `admin.example`. Người học đăng nhập bằng passkey; quản trị viên cũng dùng passkey. Một nhóm triển khai muốn đặt RP ID là `example` để dùng chung passkey trên mọi subdomain. Một API chỉ kiểm tra chữ ký nhưng không kiểm tra origin. Khi người dùng mất điện thoại, support có thể gỡ mọi passkey chỉ bằng email.

**Yêu cầu phân tích:**

1. RP ID rộng ảnh hưởng phạm vi sử dụng credential như thế nào? Có nên dùng chung cho admin và learner không?
2. Vì sao bỏ kiểm tra origin là lỗi nghiêm trọng dù chữ ký hợp lệ?
3. Làm sao ràng buộc việc thêm passkey với account đang xác thực?
4. Recovery qua support cần kiểm soát gì để không phá mục tiêu chống phishing?
5. Làm sao phân biệt user presence và user verification?
6. Sau khi passkey thành công, API cần tiếp tục kiểm tra những gì?

**Hướng giải:** Chọn RP ID theo ranh giới tin cậy mong muốn; nếu admin và learner có policy khác nhau, cân nhắc RP ID/ứng dụng tách biệt hoặc kiểm soát origin rõ ràng. Server xác minh origin allowlist và RP ID hash cùng challenge/signature. Đăng ký yêu cầu phiên account hiện tại và step-up; recovery cần bằng chứng đủ mạnh, audit, thông báo và thu hồi credential cũ. UP chỉ biểu thị hiện diện, UV biểu thị xác minh cục bộ. Sau authentication, kiểm tra account, tenant membership, session và quyền tài nguyên.

## 18. Câu hỏi tự đánh giá

1. Passkey khác mật khẩu ở chỗ nào trong cách server lưu và kiểm tra credential?
2. Private key được giữ ở đâu và vì sao không gửi lên RP server?
3. RP ID và origin khác nhau như thế nào?
4. Vì sao passkey chống phishing tốt hơn TOTP nhập tay?
5. User presence khác user verification ở điểm nào?
6. Discoverable credential hỗ trợ usernameless login ra sao?
7. Synced passkey và device-bound credential có những trade-off gì?
8. Vì sao attestation không phải lúc nào cũng bắt buộc?
9. Vì sao thêm passkey phải yêu cầu account hiện tại đã xác thực?
10. Vì sao một assertion có chữ ký hợp lệ vẫn có thể bị từ chối?
11. Passkey có tự động đồng nghĩa MFA không?
12. Recovery yếu có thể làm mất lợi ích bảo mật của passkey như thế nào?

**Gợi ý đáp án:** (1) server lưu public key thay vì password verifier cho credential đó; (2) private key ở authenticator/credential provider; (3) origin là scheme-host-port của client, RP ID là relying-party identifier; (4) chữ ký gắn với RP ID/origin; (5) UP là hiện diện, UV là xác minh người dùng cục bộ; (6) authenticator trả credential phù hợp mà không cần username trước; (7) synced thuận tiện nhưng phụ thuộc hệ sinh thái đồng bộ, device-bound kiểm soát thiết bị nhưng recovery khó hơn; (8) attestation có tác động quyền riêng tư/tương thích và chỉ cần khi policy yêu cầu; (9) ngăn attacker thêm khóa của họ; (10) sai challenge, origin, RP ID, trạng thái credential hoặc policy; (11) tùy authenticator và UV/policy; (12) attacker có thể bỏ qua passkey qua reset yếu.

## 19. Ghi nhớ

**Passkey là credential khóa công khai được sử dụng qua WebAuthn, trong đó authenticator giữ private key và RP server lưu public key để xác minh chữ ký.** Challenge mới, kiểm tra origin/RP ID, UP/UV và trạng thái credential tạo nên luồng xác thực chống phishing mạnh khi triển khai đúng. Để duy trì mức bảo đảm, hệ thống còn phải quản lý đăng ký, đồng bộ, thu hồi, recovery, session, token, tenant và authorization.

Khi review một triển khai, hãy hỏi: **Credential được tạo cho RP ID nào? Server xác minh origin và challenge ra sao? Private key được bảo vệ thế nào? Policy có yêu cầu UV không? Credential được thêm và thu hồi bằng quy trình nào? Nếu người dùng mất mọi thiết bị, recovery có giữ được ranh giới tin cậy không?**
