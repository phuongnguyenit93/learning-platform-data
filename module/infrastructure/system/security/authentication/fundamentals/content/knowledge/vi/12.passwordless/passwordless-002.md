# Authenticator-based login

## 1. Đăng nhập dựa trên authenticator là gì?

**Authenticator-based login** là cách xác thực trong đó một thành phần xác thực (*authenticator*) giữ hoặc sử dụng credential để chứng minh người dùng đang kiểm soát credential đã đăng ký với dịch vụ. Authenticator có thể là phần cứng bảo mật, thành phần bảo mật tích hợp trong điện thoại/máy tính, hoặc ứng dụng xác thực.

Trong bối cảnh **passwordless**, cách triển khai tiêu biểu là **passkey/FIDO2/WebAuthn**: khi đăng ký, thiết bị tạo một cặp khóa mật mã. Khóa riêng được giữ trong authenticator; dịch vụ (relying party, RP) lưu khóa công khai. Khi đăng nhập, RP gửi challenge mới và authenticator dùng khóa riêng tạo chữ ký. RP kiểm tra chữ ký bằng khóa công khai đã đăng ký.

Điểm khác biệt quan trọng là dịch vụ không cần nhận hoặc lưu mật khẩu dùng chung với người dùng. Với WebAuthn được triển khai đúng, credential còn được ràng buộc với RP ID và origin, giúp chống các trang phishing giả mạo tên miền.

Tuy nhiên, không phải mọi lần đăng nhập có ứng dụng authenticator đều là passwordless:

| Phương thức | Authenticator làm gì? | Có phải passwordless theo nghĩa passkey? |
| --- | --- | --- |
| **Passkey/WebAuthn** | Giữ khóa riêng và ký challenge của RP. | Có; có thể thay mật khẩu bằng xác thực khóa công khai. |
| **Security key FIDO2** | Thiết bị phần cứng giữ khóa riêng và thực hiện thao tác mật mã. | Có; người dùng có thể xác minh bằng chạm, PIN hoặc phương thức hỗ trợ. |
| **Ứng dụng TOTP** | Tạo mã dựa trên secret chia sẻ và thời gian. | Không tự động; thường là yếu tố bổ sung cho mật khẩu. |
| **Ứng dụng push approval** | Nhận yêu cầu và gửi quyết định chấp thuận. | Không nhất thiết; có thể là MFA hoặc step-up. |
| **Sinh trắc học trên thiết bị** | Mở khóa cục bộ để cho phép authenticator sử dụng credential. | Có thể là một phần của passkey; RP thường không nhận dữ liệu sinh trắc học. |

Trong module `SECURITY_AUTHENTICATION_FUNDAMENTALS`, cần nhìn authenticator như một mắt xích của toàn bộ vòng đời xác thực: đăng ký credential, xác minh đăng nhập, cấp phiên, quản lý thiết bị, thu hồi và khôi phục tài khoản.

## 2. Các thành phần và ranh giới tin cậy

Một luồng passkey điển hình có các thành phần:

- **Người dùng:** chọn tài khoản hoặc phương thức đăng nhập và thực hiện xác minh trên thiết bị.
- **Authenticator:** thành phần tạo và giữ credential; có thể là authenticator nền tảng (*platform authenticator*) hoặc thiết bị chuyển vùng (*roaming authenticator*).
- **Client:** trình duyệt hoặc ứng dụng gọi API WebAuthn và chuyển kết quả giữa authenticator với RP.
- **Relying party (RP):** website/dịch vụ đăng ký credential và xác minh response.
- **Credential store:** nơi RP lưu credential ID, public key, metadata và liên kết với tài khoản.
- **Session service:** cấp và quản lý phiên sau khi xác thực thành công.

~~~mermaid
flowchart LR
    U["Người dùng"] --> C["Browser / Client"]
    C --> A["Authenticator"]
    A -->|Private key: ký cục bộ| A
    C -->|Challenge / assertion| R["Relying Party"]
    R --> S["Credential store: public key"]
    R --> P["Authorization và session"]
    P --> X["API / tài nguyên"]
~~~

Khóa riêng không nên rời authenticator theo quy trình thông thường. RP chỉ cần public key và response đã ký để xác minh. Trình duyệt/client là một ranh giới quan trọng: nó phải thực thi quy tắc origin và chuyển tiếp dữ liệu đúng theo WebAuthn. Server vẫn phải kiểm tra đầy đủ response; không được tin rằng client đã kiểm tra mọi thứ.

**Sinh trắc học thường được xử lý cục bộ.** Khi thiết bị yêu cầu vân tay, khuôn mặt hoặc PIN, kết quả thường chỉ cho phép authenticator sử dụng khóa. RP nhận cờ xác minh người dùng và chữ ký, không nhận mẫu vân tay/khuôn mặt. Điều này giảm việc tập trung dữ liệu sinh trắc học ở server, nhưng không có nghĩa thiết bị không lưu hoặc xử lý dữ liệu sinh trắc học.

## 3. Các loại authenticator

### 3.1. Platform authenticator

Platform authenticator tích hợp trong thiết bị, hệ điều hành hoặc vùng bảo mật của thiết bị, ví dụ cơ chế xác thực sinh trắc học/PIN và kho khóa được hệ điều hành bảo vệ. Người dùng có thể đăng nhập trên chính điện thoại hoặc máy tính mà không cắm thiết bị riêng.

Ưu điểm:

- Trải nghiệm thuận tiện, có thể tận dụng màn hình khóa và xác minh cục bộ.
- Khóa riêng có thể được bảo vệ bởi phần cứng bảo mật hoặc vùng thực thi đáng tin cậy tùy thiết bị.
- Hỗ trợ luồng đăng nhập liền mạch và có thể đồng bộ passkey qua hệ sinh thái được người dùng chọn.

Giới hạn:

- Mức bảo vệ khóa phụ thuộc nền tảng, cấu hình và trạng thái thiết bị.
- Mất thiết bị, khôi phục tài khoản nền tảng hoặc malware chiếm phiên có thể ảnh hưởng đến khả năng truy cập.
- Không thể giả định mọi platform authenticator đều có cùng mức chống trích xuất khóa hoặc cùng chính sách xác minh người dùng.

### 3.2. Roaming authenticator và security key

Roaming authenticator là thiết bị xác thực bên ngoài có thể dùng với nhiều client, ví dụ security key kết nối USB, NFC hoặc Bluetooth. Khóa riêng được quản lý trên thiết bị; người dùng có thể cần chạm vào thiết bị, nhập PIN hoặc thực hiện thao tác xác minh.

Ưu điểm là có thể tách credential khỏi máy tính đang sử dụng và mang theo giữa các thiết bị. Đây là lựa chọn hữu ích cho tài khoản đặc quyền hoặc môi trường yêu cầu thiết bị xác thực riêng.

Giới hạn gồm mất thiết bị, hỏng phần cứng, nguy cơ bị đánh cắp, khả năng tương thích cổng/kết nối và nhu cầu đăng ký ít nhất một phương thức dự phòng. Một security key vẫn không sửa được lỗi authorization, session hijacking hoặc quy trình recovery yếu.

### 3.3. Synced passkey và device-bound credential

Passkey có thể được thiết kế theo hướng:

- **Device-bound:** credential gắn với một authenticator/thiết bị cụ thể, khóa riêng không được đồng bộ theo cơ chế passkey thông thường. Mất thiết bị có thể cần dùng credential dự phòng hoặc proofing lại.
- **Synced passkey:** credential có thể được đồng bộ giữa các thiết bị qua hệ sinh thái tài khoản của nhà cung cấp. Việc đồng bộ giúp phục hồi và sử dụng đa thiết bị dễ hơn, nhưng độ tin cậy còn phụ thuộc bảo mật tài khoản nền tảng, quy trình khôi phục và cách bảo vệ bản sao khóa.

Hai kiểu có trade-off khác nhau. Device-bound có thể phù hợp yêu cầu kiểm soát thiết bị chặt hơn nhưng tăng rủi ro mất quyền truy cập khi thiết bị hỏng. Synced passkey cải thiện khả năng tiếp cận và khôi phục nhưng đưa thêm một ranh giới tin cậy vào hệ sinh thái đồng bộ. Không nên tuyên bố một kiểu luôn an toàn hơn trong mọi bối cảnh.

WebAuthn có các cờ backup eligibility và backup state để biểu thị một số đặc tính liên quan đến khả năng sao lưu/đồng bộ của credential. RP có thể lưu và dùng chúng theo chính sách, nhưng không nên suy diễn quá mức từ một cờ đơn lẻ hoặc coi nó là bằng chứng tuyệt đối về cách khóa được bảo vệ.

## 4. Đăng ký authenticator: tạo và gắn credential

Trước khi người dùng đăng nhập bằng passkey, RP cần **đăng ký credential** và gắn public key với đúng tài khoản. Việc này thường diễn ra sau khi người dùng đã xác thực bằng một phương thức hiện có, được mời đăng ký theo quy trình proofing, hoặc được cấp tài khoản bởi tổ chức.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Browser / Client
    participant A as Authenticator
    participant RP as Relying Party
    U->>B: Chọn đăng ký passkey cho tài khoản
    B->>RP: Yêu cầu options đăng ký
    RP->>RP: Tạo challenge và lưu flow/expiry
    RP-->>B: PublicKeyCredentialCreationOptions
    B->>A: navigator.credentials.create()
    A->>A: Tạo credential key pair và xác minh cục bộ
    A-->>B: Attestation / credential response
    B->>RP: Gửi response đăng ký
    RP->>RP: Kiểm tra challenge, origin, RP ID, dữ liệu và policy
    RP->>RP: Lưu credential ID + public key + metadata
    RP-->>U: Đăng ký thành công
~~~

Các bước chính:

1. Người dùng đã được xác định tài khoản cần đăng ký; RP kiểm tra họ có quyền thêm authenticator vào tài khoản đó không.
2. RP tạo challenge ngẫu nhiên, thời hạn và flow ID; lưu trạng thái ở phía server.
3. RP trả về các options như RP ID, user ID không nhạy cảm, user name/display name, thuật toán được chấp nhận, danh sách credential loại trừ nếu phù hợp, authenticator selection và chính sách user verification.
4. Client gọi WebAuthn API; authenticator tạo credential và trả về credential ID cùng public key trong cấu trúc response.
5. RP xác minh challenge, origin, RP ID hash, cấu trúc authenticator data, chữ ký/attestation theo chính sách và các thuộc tính bắt buộc.
6. RP lưu public key, credential ID, chủ tài khoản, thời điểm đăng ký và metadata cần thiết; không lưu private key.

**Attestation** có thể cung cấp thông tin về nguồn gốc hoặc loại authenticator, tùy định dạng và chính sách. Nhiều dịch vụ tiêu dùng không cần xác minh danh tính model thiết bị và có thể dùng chính sách attestation hạn chế để giảm thu thập dữ liệu thiết bị. Chỉ yêu cầu attestation cụ thể khi có nhu cầu bảo đảm rõ ràng; phải cân nhắc quyền riêng tư, tương thích và tác động đến người dùng.

Một RP không nên cho phép bất kỳ ai thêm passkey mới chỉ vì họ biết email hoặc username. Bước thêm credential có thể tạo quyền truy cập lâu dài, do đó phải được bảo vệ như một hành động bảo mật nhạy cảm.

## 5. Đăng nhập bằng authenticator

Trong luồng assertion/authentication, RP tạo challenge mới cho mỗi lần đăng nhập. Client gọi WebAuthn API để authenticator ký dữ liệu xác thực bằng private key tương ứng.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Browser
    participant A as Authenticator
    participant RP as Relying Party
    U->>B: Chọn đăng nhập bằng passkey
    B->>RP: Yêu cầu challenge
    RP->>RP: Sinh nonce, gắn flow và hạn dùng
    RP-->>B: PublicKeyCredentialRequestOptions
    B->>A: navigator.credentials.get()
    A->>A: Xác minh cục bộ và ký assertion
    A-->>B: Credential ID + authenticatorData + signature
    B->>RP: Gửi assertion
    RP->>RP: Kiểm tra challenge, origin, RP ID, chữ ký, UP/UV
    RP->>RP: Tiêu thụ challenge và kiểm tra trạng thái credential
    RP-->>B: Kết quả xác thực
    RP-->>U: Cấp session theo chính sách
~~~

RP phải kiểm tra response theo WebAuthn, bao gồm:

- `clientDataJSON.type` đúng loại assertion, thường là `webauthn.get`.
- Challenge đúng với giá trị vừa phát, gắn với flow hiện tại, chưa hết hạn và chưa được dùng.
- `origin` khớp allowlist origin của RP; không chấp nhận origin do client tự khai không được kiểm tra.
- RP ID hash trong authenticator data đúng RP ID dự kiến.
- Credential ID đã đăng ký, public key tương ứng tồn tại và thuộc đúng tài khoản/tenant.
- Chữ ký hợp lệ trên `authenticatorData || SHA-256(clientDataJSON)` bằng public key đã lưu.
- Cờ User Presence (UP) và User Verification (UV) đáp ứng chính sách của RP.
- Trạng thái credential/tài khoản và các chính sách rủi ro hiện hành cho phép đăng nhập.

WebAuthn nên được xử lý bằng thư viện server-side được duy trì và kiểm thử; không tự viết parser hoặc bỏ qua một trường xác minh để “đăng nhập cho chạy”.

## 6. User Presence và User Verification

Hai khái niệm này khác nhau:

| Cờ | Ý nghĩa khái quát | Điều không thể suy ra |
| --- | --- | --- |
| **User Presence (UP)** | Có bằng chứng người dùng hiện diện/tương tác với authenticator, chẳng hạn chạm security key. | Không nhất thiết đã xác minh người dùng cụ thể. |
| **User Verification (UV)** | Authenticator đã thực hiện phương thức xác minh người dùng cục bộ theo khả năng của nó, ví dụ PIN hoặc sinh trắc học. | Không chứng minh dữ liệu sinh trắc học được gửi cho RP, danh tính pháp lý hay ý định của người dùng đối với mọi giao dịch. |

RP có thể yêu cầu UV cho tài khoản có rủi ro cao hoặc thao tác nhạy cảm. Nếu chính sách yêu cầu UV mà response không có cờ UV phù hợp, server phải từ chối hoặc chuyển sang phương thức khác được chính sách cho phép.

Không nên hiểu UP là MFA, hoặc UV luôn là “sinh trắc học”. UV có thể là PIN thiết bị hoặc cơ chế cục bộ khác. Mức bảo vệ thực tế phụ thuộc authenticator và cách thiết bị triển khai.

## 7. Vì sao passkey có khả năng chống phishing?

Passkey/WebAuthn ràng buộc credential với **RP ID** và response với **origin** mà client sử dụng. Một website giả có origin khác không thể đơn giản yêu cầu authenticator ký credential của website thật như thể đang ở origin hợp lệ.

Ví dụ:

- Website thật dùng RP ID `example.com`.
- Attacker tạo trang `example-login.test` và chuyển tiếp yêu cầu đăng nhập.
- Trình duyệt/Authenticator nhận biết origin của trang giả khác với RP ID được credential đăng ký.
- Credential của `example.com` không được sử dụng để tạo assertion hợp lệ cho origin giả.

Đây là khác biệt quan trọng so với OTP. OTP có thể bị nạn nhân nhập vào trang giả rồi chuyển tiếp tới dịch vụ thật trong thời gian mã còn hiệu lực. Passkey được thiết kế để ràng buộc bằng chứng vào origin/RP ID ở cấp giao thức.

Tuy vậy, chống phishing không đồng nghĩa miễn nhiễm mọi tấn công:

- XSS trên origin thật có thể thao tác trong phiên người dùng.
- Malware điều khiển thiết bị hoặc trình duyệt có thể lạm dụng quyền sau khi xác thực.
- Kẻ tấn công có thể chiếm phiên sau đăng nhập hoặc lừa người dùng phê duyệt hành động nghiệp vụ.
- Luồng khôi phục, thêm authenticator và liên kết tài khoản yếu có thể bị lợi dụng để thay đổi credential.
- Attacker có thể nhắm vào tài khoản nền tảng dùng để đồng bộ passkey hoặc thiết bị đã mở khóa.

Passkey giảm mạnh một lớp phishing credential; RP vẫn cần bảo vệ session, authorization, recovery và transaction confirmation.

## 8. Passkey discoverable và luồng chọn tài khoản

Credential WebAuthn có thể là discoverable credential (thường được gọi là resident credential trong thuật ngữ cũ), cho phép authenticator cung cấp danh sách credential phù hợp với RP mà không cần RP chỉ định trước credential ID.

Với discoverable credential, người dùng có thể nhập username-less: mở trang, chọn passkey/tài khoản từ giao diện hệ điều hành hoặc trình duyệt, rồi xác minh cục bộ. RP vẫn nhận credential ID và xác định tài khoản từ bản ghi đã đăng ký.

Với luồng non-discoverable, RP có thể yêu cầu người dùng nhập username trước để biết credential nào được phép dùng. Client nhận danh sách credential ID tương ứng và authenticator thực hiện xác thực.

| Luồng | Trải nghiệm | Điểm cần bảo vệ |
| --- | --- | --- |
| Discoverable / username-less | Người dùng chọn tài khoản trong bộ chọn passkey. | Tránh tiết lộ danh sách tài khoản; kiểm tra credential ID và ánh xạ đúng tenant. |
| Username-first | Người dùng nhập username/email rồi chọn passkey. | Phản hồi không làm lộ tài khoản; challenge vẫn mới và ràng buộc flow. |
| Conditional UI / autofill | Trình duyệt gợi ý passkey trong trường đăng nhập. | Phải dùng đúng API và cấu hình RP; không coi gợi ý từ client là kết quả xác thực. |

Discoverable không có nghĩa RP phải công khai mọi tài khoản hoặc credential. Server vẫn có thể dùng challenge và chính sách phản hồi thống nhất để giảm enumeration.

## 9. Quản lý nhiều authenticator và vòng đời credential

Người dùng có thể có nhiều passkey: một trên điện thoại, một trên laptop và một security key dự phòng. RP cần quản lý chúng như các credential độc lập gắn với cùng tài khoản.

Một bản ghi credential thường cần:

| Trường | Mục đích |
| --- | --- |
| `credentialId` | Nhận diện credential khi xác thực. |
| `publicKey` | Kiểm tra chữ ký assertion. |
| `userId` / `tenantId` | Ánh xạ credential tới đúng tài khoản và tổ chức. |
| `createdAt` / `lastUsedAt` | Hiển thị và quản lý vòng đời. |
| `transports` | Gợi ý cách client có thể liên lạc với authenticator. |
| `backupEligible` / `backupState` | Lưu trạng thái backup theo định nghĩa WebAuthn khi cần. |
| `signCount` | Theo dõi sign counter theo khả năng và chính sách authenticator. |
| `nickname` | Tên thân thiện do người dùng đặt, không phải bằng chứng tin cậy. |
| `revokedAt` | Ngừng chấp nhận credential đã bị thu hồi. |

Sign counter có thể giúp phát hiện một số trường hợp clone authenticator, nhưng nhiều passkey đồng bộ hoặc authenticator có thể không cung cấp counter tăng đơn điệu. RP không nên coi counter bằng 0 hoặc không tăng là bằng chứng chắc chắn credential bị sao chép; cần tuân thủ khuyến nghị của giao thức và đánh giá trong ngữ cảnh.

Các chức năng quản lý nên cho phép:

- Xem danh sách authenticator đã đăng ký với tên, thời điểm thêm và lần sử dụng gần nhất.
- Thêm credential mới sau khi xác thực lại hoặc step-up phù hợp.
- Đổi tên để người dùng dễ nhận biết, nhưng không dùng tên do người dùng nhập làm căn cứ quyền.
- Thu hồi credential bị mất, đánh cắp hoặc không còn thuộc quyền kiểm soát.
- Gửi thông báo khi thêm/xóa authenticator hoặc có thay đổi bảo mật quan trọng.
- Yêu cầu xác minh bổ sung khi thay đổi có nguy cơ chiếm tài khoản.

Không cho phép một phiên chỉ dựa trên bearer cookie bị đánh cắp tự ý thêm passkey mới rồi xóa hết credential cũ mà không có step-up hoặc kiểm soát rủi ro.

## 10. Session sau khi authenticator xác thực thành công

WebAuthn assertion là bằng chứng cho một lần xác thực; nó không phải session lâu dài. Sau khi RP xác minh thành công, ứng dụng thường tạo session cookie hoặc token riêng.

Các nguyên tắc quản lý phiên:

1. Sinh session ID mới sau đăng nhập để chống session fixation.
2. Cookie web thường cần `Secure`, `HttpOnly` và `SameSite` phù hợp; bổ sung CSRF protection cho thao tác thay đổi trạng thái khi cần.
3. Có thời hạn idle/absolute phù hợp mức rủi ro, cơ chế logout và thu hồi khi tài khoản bị khóa hoặc credential bị nghi lộ.
4. Không lưu access token hoặc session secret trong log, URL hay dữ liệu phân tích.
5. Kiểm tra authorization theo từng request và từng tài nguyên; passkey không tự cấp quyền nghiệp vụ.
6. Step-up lại với hành động nhạy cảm, đồng thời xác nhận đúng nội dung hành động nếu mục tiêu là bảo vệ ý định giao dịch.

Nếu access token là bearer token, nó vẫn có thể bị replay sau khi bị đánh cắp. Phương thức đăng nhập chống phishing không tự làm các phiên/token phía sau trở thành chống replay.

## 11. Recovery và backup authenticator

Khôi phục tài khoản là một phần của thiết kế passwordless. Người dùng có thể mất điện thoại, hỏng security key, mất quyền vào tài khoản đồng bộ hoặc không thể dùng sinh trắc học/PIN.

Một thiết kế recovery tốt cần nhiều phương án dự phòng được thiết lập **trước khi xảy ra sự cố**, chẳng hạn:

- Đăng ký ít nhất hai authenticator độc lập khi mức rủi ro yêu cầu.
- Dùng security key dự phòng được cất giữ an toàn.
- Synced passkey qua hệ sinh thái có quy trình khôi phục đáng tin cậy, sau khi đánh giá rủi ro tài khoản nền tảng.
- Recovery code ngẫu nhiên, lưu một lần và tiêu thụ nguyên tử, nếu dịch vụ chọn hỗ trợ.
- Quy trình proofing lại hoặc hỗ trợ có kiểm soát cho trường hợp mất toàn bộ credential.

Không nên khôi phục tài khoản chỉ bằng thông tin công khai như ngày sinh, tên người thân hoặc vài câu hỏi bảo mật dễ đoán. Đường recovery không được yếu hơn đáng kể so với đăng nhập chính, nếu không attacker sẽ nhắm vào recovery thay vì phá passkey.

Khi khôi phục thành công, cần xem xét:

1. Thu hồi session và token đáng ngờ.
2. Thu hồi authenticator bị mất hoặc không còn kiểm soát.
3. Thêm credential mới qua luồng enrollment an toàn.
4. Thông báo thay đổi qua kênh độc lập khi phù hợp.
5. Ghi nhận sự kiện và theo dõi đăng nhập bất thường.

## 12. Threat model và các lỗi triển khai

| Mối đe dọa/lỗi | Tác động | Kiểm soát |
| --- | --- | --- |
| Không kiểm tra challenge hoặc chấp nhận challenge cũ | Replay assertion. | Challenge ngẫu nhiên, gắn flow, expiry và tiêu thụ một lần nguyên tử. |
| Không kiểm tra origin/RP ID | Có thể chấp nhận response ngoài ngữ cảnh dự kiến. | Allowlist origin, RP ID hash và kiểm tra bằng thư viện chuẩn. |
| Tin dữ liệu do client tự gửi | Có thể giả principal, user verification hoặc trạng thái credential. | Server-side verification; lấy metadata từ credential store. |
| Thêm passkey chỉ bằng session yếu | Attacker chiếm phiên có thể cài credential của mình. | Step-up, kiểm tra rủi ro, thông báo và xác nhận thay đổi bảo mật. |
| Lưu private key ở server | Mở rộng tác động khi database bị lộ. | Passkey dùng public-key model; server chỉ lưu public key và metadata cần thiết. |
| Yêu cầu attestation quá mức | Giảm tương thích, thu thập thêm dữ liệu thiết bị. | Chỉ yêu cầu khi có mục tiêu bảo đảm cụ thể và chính sách quyền riêng tư rõ. |
| Coi UV là bằng chứng danh tính pháp lý | Suy diễn quá mức từ xác minh cục bộ. | Phân biệt credential control, local user verification và identity proofing. |
| Không có authenticator dự phòng | Người dùng bị khóa tài khoản khi mất thiết bị. | Nhiều credential, recovery an toàn và quy trình hỗ trợ. |
| Coi sign counter luôn tăng | Từ chối nhầm passkey đồng bộ hoặc authenticator hợp lệ. | Xử lý theo đặc tả và đặc tính authenticator. |
| Không quản lý session sau login | Session hijacking/replay dù đăng nhập bằng passkey mạnh. | Cookie/token an toàn, expiry, revoke, CSRF/XSS protection. |
| Dựa vào email trùng để nối tài khoản | Chiếm hoặc ghép nhầm tài khoản. | Ánh xạ bằng subject nội bộ ổn định và quy trình liên kết được xác minh. |

~~~mermaid
flowchart TD
    A["Credential được đăng ký"] --> B["Authenticator giữ private key"]
    B --> C["RP phát challenge mới"]
    C --> D["Authenticator ký theo RP/origin"]
    D --> E["RP xác minh response và trạng thái"]
    E --> F{"Hợp lệ và đúng policy?"}
    F -->|Không| G["Từ chối / ghi nhận rủi ro"]
    F -->|Có| H["Tạo session"]
    H --> I["Authorization theo từng request"]
    I --> J["Step-up / recovery khi cần"]
~~~

## 13. Ví dụ thiết kế: bật passkey cho tài khoản nhân viên

Một tổ chức muốn cho nhân viên đăng nhập vào cổng nội bộ bằng passkey. Tài khoản đã được tạo từ nguồn nhân sự và gắn với mã nhân viên.

**Enrollment:**

1. Nhân viên đăng nhập bằng phương thức hiện có hoặc được cấp onboarding session có giới hạn.
2. RP kiểm tra tài khoản còn hoạt động, đúng tenant và người dùng có quyền đăng ký authenticator.
3. RP tạo WebAuthn registration challenge, gắn với session, user ID và thời hạn.
4. Nhân viên tạo passkey trên laptop; authenticator xác minh cục bộ theo chính sách.
5. RP xác minh response, lưu credential ID/public key và metadata, rồi thông báo thiết bị mới.
6. Với vai trò đặc quyền, tổ chức có thể yêu cầu thêm security key dự phòng hoặc kiểm soát thiết bị theo chính sách.

**Login:**

1. RP tạo authentication challenge mới.
2. Nhân viên chọn passkey trong trình duyệt hoặc hệ điều hành.
3. Authenticator xác minh người dùng cục bộ và ký assertion.
4. RP kiểm tra challenge, origin, RP ID, chữ ký, UP/UV, trạng thái credential và tài khoản.
5. RP cấp session mới; API tiếp tục kiểm tra vai trò và quyền của nhân viên theo từng thao tác.

**Khi mất laptop:**

- Nhân viên dùng authenticator dự phòng hoặc quy trình recovery được tổ chức phê duyệt.
- Bộ phận quản trị thu hồi credential của laptop mất, đánh giá phiên còn hiệu lực và thông báo sự kiện.
- Nhân viên đăng ký passkey mới qua luồng enrollment có xác minh.

Trong ví dụ này, passkey xác thực quyền kiểm soát credential gắn với tài khoản nhân viên. Nguồn nhân sự xác lập quan hệ nhân viên; authorization quyết định quyền truy cập ứng dụng. Ba trách nhiệm đó không được gộp làm một.

## 14. Checklist triển khai authenticator-based login

Trước khi đưa passwordless login vào production, hãy kiểm tra:

1. **Authenticator:** hỗ trợ platform, roaming hay synced passkey? Mức bảo vệ khóa và trải nghiệm dự phòng được hiểu rõ chưa?
2. **Enrollment:** ai được thêm credential, làm thế nào để gắn credential với đúng tài khoản, có step-up và thông báo thay đổi không?
3. **Challenge:** có ngẫu nhiên, mới, gắn đúng flow và được tiêu thụ một lần không?
4. **WebAuthn verification:** server có kiểm tra challenge, origin, RP ID hash, credential ID, chữ ký, UP/UV và trạng thái theo thư viện chuẩn không?
5. **Privacy:** có thật sự cần attestation không? Dữ liệu thiết bị và metadata được thu thập ở mức tối thiểu chưa?
6. **Account selection:** discoverable credential và username-first có xử lý enumeration, tenant và ánh xạ tài khoản an toàn không?
7. **Credential lifecycle:** có xem, thêm, đổi tên, thu hồi, phát hiện credential mất và quản lý nhiều authenticator không?
8. **Session:** session ID có được tạo mới, cookie/token có bảo vệ, expiry và revoke rõ ràng không?
9. **Authorization:** API có kiểm tra quyền theo tài nguyên và tenant sau xác thực không?
10. **Recovery:** người dùng mất mọi thiết bị sẽ làm gì? Recovery có được bảo vệ tương xứng với login không?
11. **Accessibility:** người dùng không có thiết bị tương thích hoặc không thể dùng sinh trắc học có phương án thay thế an toàn không?
12. **Monitoring:** có log sự kiện enrollment/login/revoke không chứa bí mật, phát hiện bất thường và quy trình ứng phó sự cố không?

**Kết luận:** Authenticator-based login cho phép người dùng chứng minh quyền kiểm soát credential bằng một thành phần xác thực, và passkey/WebAuthn là cách triển khai passwordless tiêu biểu dựa trên khóa công khai. Khả năng chống phishing đến từ việc ràng buộc credential với RP ID/origin và kiểm tra response đúng chuẩn. Một hệ thống hoàn chỉnh còn phải bảo vệ enrollment, nhiều authenticator, session, authorization và recovery; nếu một trong các đường này yếu, tài khoản vẫn có thể bị chiếm dù bước đăng nhập chính rất mạnh.
