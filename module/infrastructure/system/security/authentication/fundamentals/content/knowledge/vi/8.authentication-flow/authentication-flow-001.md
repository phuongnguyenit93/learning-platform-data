# Client và authenticator

> **Chương:** Authentication flow  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS  
> **Trọng tâm:** Vai trò của client, authenticator và server trong luồng xác thực; cách chứng minh quyền kiểm soát credential mà không đặt niềm tin sai chỗ; những giới hạn của mật khẩu, OTP, passkey và chứng chỉ.

## 1. Client và authenticator có phải cùng một thứ?

Trong một luồng đăng nhập, **client** là phần mềm thay mặt người dùng tương tác với dịch vụ, chẳng hạn trình duyệt, ứng dụng di động hoặc ứng dụng desktop. **Authenticator** là bí mật, thiết bị hoặc cơ chế mật mã mà người dùng kiểm soát và sử dụng để tạo **bằng chứng xác thực**. Hai thành phần có thể nằm trên cùng một thiết bị nhưng thực hiện những trách nhiệm khác nhau.

Ví dụ, khi người dùng truy cập trang đăng nhập bằng trình duyệt:

- Trình duyệt là **client**: hiển thị giao diện, tiếp nhận thao tác và trao đổi thông điệp với server.
- Một passkey lưu trong hệ điều hành hoặc khóa bảo mật USB là **authenticator**: giữ khóa riêng và thực hiện thao tác mật mã khi người dùng đồng ý.
- Dịch vụ xác thực là **verifier**: kiểm tra bằng chứng được gửi về, ràng buộc nó với tài khoản và đánh giá chính sách.
- Ứng dụng có tài nguyên cần truy cập là **relying party (RP)** trong nhiều mô hình xác thực; trong hệ thống có nhà cung cấp danh tính (IdP), RP có thể không trực tiếp kiểm tra mật khẩu hoặc passkey.

Với đăng nhập bằng mật khẩu, người dùng nhập một **memorized secret** qua client; bằng chứng được kiểm tra tại server bằng password verifier. Với passkey/WebAuthn, client chuyển lời thách thức đến authenticator để ký và gửi kết quả về server: **khóa riêng không cần rời authenticator**.

### Kết quả học tập

Sau bài này, người học có thể:

1. Phân biệt client, authenticator, credential, verifier, RP, IdP và phiên/token.
2. Vẽ luồng thông điệp xác thực và xác định ranh giới tin cậy giữa từng thành phần.
3. Giải thích cách mật khẩu, OTP, passkey và chứng chỉ tạo ra bằng chứng khác nhau.
4. Phân tích khả năng chống phishing, replay, đánh cắp credential và chiếm quyền phiên.
5. Thiết kế luồng đăng ký, xác thực, xác thực tăng cường và thu hồi authenticator an toàn.

## 2. Thuật ngữ và trách nhiệm

| Thành phần | Trách nhiệm | Điều không được suy diễn |
|---|---|---|
| **Người dùng / chủ thể (claimant)** | Yêu cầu xác thực với một danh tính | Nói “tôi là A” chưa chứng minh được là A |
| **Client** | Truyền yêu cầu, tương tác với người dùng, nhận và trình bằng chứng | Giao diện hiển thị thành công không có nghĩa server đã xác minh |
| **Authenticator** | Lưu hoặc sử dụng bí mật/khóa để tạo bằng chứng xác thực | Có thiết bị không tự bảo đảm chủ thiết bị là người được ủy quyền |
| **Credential** | Dữ liệu liên kết authenticator với tài khoản hoặc định danh | Credential còn hợp lệ không có nghĩa tài khoản được cấp mọi quyền |
| **Verifier** | Kiểm tra bằng chứng, trạng thái và quy tắc xác thực | Chỉ xác thực danh tính chưa đủ để phân quyền tài nguyên |
| **Relying party (RP)** | Dựa vào kết quả xác thực để phục vụ người dùng | Không được tin assertion hoặc token chưa xác minh |
| **Identity provider (IdP)** | Cung cấp dịch vụ danh tính/xác thực cho RP trong mô hình liên kết | RP vẫn phải kiểm tra issuer, audience, trạng thái và quyền |
| **Resource server / API** | Bảo vệ dữ liệu, chức năng được gọi | Không được tin vai trò hoặc account ID do client tự khai |

**Credential** và **authenticator** có liên hệ nhưng không luôn đồng nghĩa. Trong WebAuthn, credential thường gắn với một cặp khóa và một mã credential; authenticator có thể giữ hoặc quản lý khóa riêng, còn RP lưu khóa công khai và metadata cần thiết. Trong luồng mật khẩu, password credential là bí mật ghi nhớ của người dùng, còn server lưu **verifier** dưới dạng dẫn xuất từ mật khẩu. Với OTP, authenticator có thể là ứng dụng tạo mã từ bí mật chung và bộ đếm/thời gian.

### Cùng một thiết bị, hai vai trò

Điện thoại có thể đồng thời chạy ứng dụng ngân hàng (**client**) và lưu passkey trong trình quản lý credential của hệ điều hành (**authenticator**). Việc hai vai trò cùng nằm trên điện thoại **không làm mất** sự khác biệt về logic: client yêu cầu một thao tác; hệ điều hành/authenticator thực hiện xác minh người dùng theo chính sách rồi ký dữ liệu. Tuy nhiên, khi thiết bị hoặc hệ điều hành bị xâm nhập sâu, ranh giới giữa hai vai trò có thể yếu đi. Vì thế, lựa chọn thiết bị và mức bảo đảm phải phù hợp rủi ro.

## 3. Mô hình tổng quát của luồng xác thực

~~~mermaid
flowchart LR
    U["Người dùng"] -->|"Thao tác"| C["Client: web / mobile / desktop"]
    C <-->|"Yêu cầu sử dụng credential"| A["Authenticator: bí mật / khóa / thiết bị"]
    C <-->|"Thông điệp xác thực qua TLS"| V["Verifier / dịch vụ xác thực"]
    V -->|"Đạt chính sách"| S["Phiên / token"]
    S -->|"Yêu cầu tài nguyên"| R["API / Resource server"]
    R --> P{"Phiên/token hợp lệ và có quyền?"}
    P -->|"Có"| OK["Cho phép thao tác"]
    P -->|"Không"| NO["Từ chối"]
~~~

Đây là sơ đồ khái niệm, **không phải mọi giao thức đều gửi bí mật qua cùng một đường**. Mật khẩu có thể được client gửi qua TLS để server kiểm tra; WebAuthn gửi kết quả ký thay vì khóa riêng; mTLS có thể cho client chứng minh quyền kiểm soát khóa riêng ngay ở tầng kết nối.

Một luồng an toàn thường trả lời được sáu câu hỏi:

1. **Ai là bên cần chứng minh?** Tài khoản hoặc định danh dịch vụ nào?
2. **Bằng chứng lấy từ đâu?** Mật khẩu, OTP, passkey, chứng chỉ hoặc yếu tố khác?
3. **Bằng chứng gắn với bối cảnh nào?** Origin, RP ID, phiên thách thức, thiết bị, mục đích hoặc thời hạn nào?
4. **Ai kiểm chứng?** Backend/IdP và thư viện xác thực nào có thẩm quyền?
5. **Khi nào phiên được cấp?** Sau những điều kiện bắt buộc nào, kể cả MFA và trạng thái tài khoản?
6. **Phiên cho phép điều gì?** API vẫn phải kiểm tra quyền trên tài nguyên và hành động cụ thể.

## 4. Client làm gì và có thể bị kiểm soát đến đâu?

### Vai trò hợp lệ của client

Client giúp người dùng thực hiện các bước xác thực:

- Hiển thị đúng dịch vụ và thao tác đang được xác thực.
- Thu thập định danh, mật khẩu hoặc yêu cầu sử dụng passkey qua API thích hợp.
- Nhận challenge hoặc yêu cầu MFA từ server và chuyển tới authenticator khi cần.
- Gửi kết quả đến verifier bằng kênh bảo vệ.
- Nhận trạng thái đăng nhập, quản lý phiên theo cơ chế được chọn và điều hướng giao diện.

Trình duyệt có thể cung cấp API như **Web Authentication (WebAuthn)** để trang web yêu cầu tạo hoặc sử dụng credential khóa công khai. Ứng dụng native có thể gọi API hệ điều hành tương ứng. Client thường **không trực tiếp đọc khóa riêng của passkey**; authenticator hoặc lớp quản lý credential thực hiện thao tác cần thiết.

### Ranh giới tin cậy của client

Người sử dụng có thể sửa JavaScript, can thiệp HTTP request, gọi API trực tiếp hoặc thay giá trị trong local storage. Kẻ tấn công có thể xây ứng dụng giả, website phishing hoặc khai thác XSS trong một trang có thật. Bởi vậy:

> **Client là nơi khởi tạo và trình bày tương tác; server là nơi ra quyết định xác thực và cấp quyền.**

Ví dụ client gửi:

~~~json
{
  "username": "employee-a",
  "password": "user supplied secret",
  "isAuthenticated": true,
  "role": "admin"
}
~~~

Server không được tin các trường \`isAuthenticated\` và \`role\` do client cung cấp. Server phải xác minh mật khẩu hoặc bằng chứng khác, truy vấn trạng thái tài khoản rồi xây dựng phiên/quyền từ nguồn đáng tin cậy. Ví dụ trên chỉ minh họa cấu trúc; **không ghi hoặc lưu mật khẩu thực trong log hay bộ dữ liệu thử nghiệm công khai**.

### Trình duyệt, native app và client tự động

| Loại client | Đặc điểm | Cần chú ý |
|---|---|---|
| **Trình duyệt web** | Quản lý origin, cookie, API WebAuthn | HTTPS, XSS, CSRF, chính sách cookie, script bên thứ ba |
| **Ứng dụng di động/native** | Gọi API của hệ điều hành và lưu token trong vùng bảo vệ phù hợp | Deep link/callback giả, lưu trữ token, thiết bị root/jailbreak |
| **Ứng dụng desktop** | Có quyền tương tác phần cứng hoặc keychain | Cập nhật phần mềm, thư viện bị thay thế, bảo vệ phiên |
| **CLI / dịch vụ tự động** | Không có người dùng tương tác ở mỗi lần chạy | Dùng danh tính dịch vụ, chứng chỉ hoặc token phạm vi hẹp thay vì mật khẩu cá nhân |

Mức độ bảo vệ của client ảnh hưởng khả năng bảo vệ kết quả xác thực. Một authenticator mạnh có thể chống lộ khóa riêng, nhưng **không tự ngăn** malware trong client đọc dữ liệu sau khi người dùng đã đăng nhập hoặc thực hiện giao dịch sai ý định.

## 5. Authenticator là gì và có những nhóm nào?

Authenticator là thứ người dùng **biết, có hoặc kiểm soát** để tạo bằng chứng xác thực. Một cơ chế có thể kết hợp nhiều yếu tố; điều quan trọng là bằng chứng có thể bị sao chép, chuyển tiếp hoặc sử dụng sai ngữ cảnh đến mức nào.

| Authenticator/phương thức | Bằng chứng được trình | Điểm mạnh | Rủi ro tiêu biểu |
|---|---|---|---|
| **Mật khẩu / passphrase** | Bí mật người dùng nhớ và nhập | Dễ phổ cập, không yêu cầu thiết bị riêng | Đoán được, dùng lại, phishing, malware |
| **Ứng dụng TOTP** | Mã dựa trên thời gian và bí mật đã chia sẻ | Thêm yếu tố sở hữu trong nhiều triển khai | Mã có thể bị phishing thời gian thực, sao chép secret |
| **OTP phần cứng** | Mã do thiết bị chuyên dụng tạo | Tách khỏi máy tính đăng nhập | Vẫn có thể bị người dùng nhập vào trang giả |
| **Push authenticator** | Phê duyệt challenge qua ứng dụng trên thiết bị | Thuận tiện, có thể hiển thị ngữ cảnh | Push fatigue, chấp thuận nhầm, yêu cầu giả |
| **Passkey/WebAuthn** | Chữ ký bằng khóa riêng gắn với RP | Chống phishing theo origin/RP ID, không gửi khóa riêng | Mất/chiếm thiết bị, đăng ký credential trái phép, phục hồi yếu |
| **Khóa bảo mật FIDO2** | Thao tác mật mã bằng phần cứng bên ngoài | Cô lập khóa, mức bảo đảm thiết bị theo loại khóa | Mất khóa, quy trình thay thế cần an toàn |
| **Chứng chỉ client/mTLS** | Chứng minh quyền kiểm soát khóa riêng ở tầng kết nối | Phù hợp định danh máy/dịch vụ và thiết bị quản lý | Quản lý cấp phát, hạn dùng, thu hồi và khóa riêng |

**Passkey** có thể là credential đồng bộ giữa thiết bị qua trình quản lý passkey hoặc credential gắn thiết bị, tùy nhà cung cấp và chính sách. **Khóa bảo mật** có thể giữ credential theo dạng không xuất được. Cả hai có thể dựa trên WebAuthn/FIDO, nhưng mức độ ràng buộc thiết bị và lựa chọn phục hồi khác nhau.

### User presence và user verification

Trong WebAuthn có hai khái niệm cần tách:

- **User presence (UP):** chứng tỏ có tương tác vật lý hoặc hành động thể hiện sự hiện diện, chẳng hạn chạm khóa bảo mật.
- **User verification (UV):** authenticator đã kiểm tra người dùng tại chỗ bằng PIN, sinh trắc học hoặc phương thức tương đương được hỗ trợ.

Một lần chạm khóa có thể chứng minh **UP** mà chưa chứng minh **UV**. RP phải quyết định chính sách cho phép trường hợp nào và **kiểm tra cờ UP/UV được trả về**; không được suy luận chỉ từ giao diện client hiển thị “đã xác minh”.

**Sinh trắc học trong passkey** thường được kiểm tra cục bộ để mở quyền dùng khóa riêng. RP nhận kết quả xác thực mật mã, chứ không cần nhận mẫu vân tay hoặc ảnh khuôn mặt của người dùng. Việc sinh trắc học có được sử dụng hay không tùy authenticator và chính sách UV.

## 6. Ba ví dụ luồng: mật khẩu, TOTP và passkey

### 6.1. Luồng mật khẩu

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant C as Client
    participant V as Verifier
    participant DB as Kho verifier
    U->>C: Nhập định danh và mật khẩu
    C->>V: POST /login qua HTTPS
    V->>DB: Lấy verifier và trạng thái tài khoản
    DB-->>V: Salt, KDF params, password hash
    V->>V: Kiểm tra mật khẩu, chính sách, giới hạn thử sai
    alt Đủ điều kiện
        V-->>C: Phiên hoặc bước MFA tiếp theo
    else Sai / không hợp lệ
        V-->>C: Lỗi chung, không tiết lộ bí mật
    end
~~~

Server phải lưu password verifier bằng hàm băm mật khẩu chuyên dụng như Argon2id với salt riêng và tham số phù hợp. TLS bảo vệ mật khẩu trên đường truyền đến server thật, nhưng **không chống được** website giả mạo được người dùng tự điền mật khẩu. Mật khẩu bị lấy cắp có thể được nhập lại; vì vậy cần chống credential stuffing, giới hạn thử sai và cân nhắc MFA hoặc passkey.

### 6.2. Luồng mật khẩu kết hợp TOTP

Giả sử người dùng đã vượt qua mật khẩu và hệ thống yêu cầu mã 6 chữ số từ ứng dụng authenticator.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant C as Client
    participant A as Ứng dụng TOTP
    participant V as Verifier
    C->>V: Gửi mật khẩu qua HTTPS
    V->>V: Xác minh mật khẩu, xác định yêu cầu MFA
    V-->>C: Yêu cầu MFA, challenge tạm thời
    U->>A: Mở ứng dụng mã xác thực
    A-->>U: Mã TOTP ngắn hạn
    U->>C: Nhập mã
    C->>V: Mã TOTP + ngữ cảnh challenge
    V->>V: Kiểm tra mã, thời gian, trạng thái và chống lặp
    V-->>C: Phiên hoàn chỉnh hoặc từ chối
~~~

Ứng dụng TOTP và verifier biết cùng một bí mật đã đăng ký và tính mã theo bước thời gian. Server thường cần chấp nhận một độ lệch đồng hồ có giới hạn, đồng thời hạn chế số lần thử và cách tái sử dụng mã trong ngữ cảnh phù hợp.

**Điểm yếu:** kẻ tấn công có thể dựng trang giả, lấy mật khẩu và mã TOTP người dùng vừa nhập rồi chuyển tiếp tới dịch vụ thật ngay lúc đó. Bổ sung OTP làm tăng chi phí tấn công nhưng không tự tạo ràng buộc với **origin** của trang.

Với push MFA, cần giảm nguy cơ người dùng vô tình bấm chấp thuận yêu cầu do kẻ tấn công tạo. Number matching và thông tin ngữ cảnh có thể giúp, nhưng **không biến mọi push MFA thành chống phishing**.

### 6.3. Luồng passkey/WebAuthn

WebAuthn dùng mô hình **challenge–response bằng khóa công khai**, có cơ chế gắn bằng chứng với nguồn gốc website và RP ID. RP lưu khóa công khai hoặc thông tin xác minh tương ứng; authenticator dùng khóa riêng để ký. Đây là luồng minh họa khi credential đã đăng ký:

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant C as Browser/WebAuthn client
    participant A as Authenticator/passkey
    participant V as Server/RP
    U->>C: Chọn đăng nhập bằng passkey
    C->>V: Xin yêu cầu xác thực
    V-->>C: Challenge ngẫu nhiên + RP ID + options
    C->>A: Yêu cầu xác thực theo origin/RP ID
    A->>U: Yêu cầu UP/UV theo chính sách
    U-->>A: Chạm/PIN/sinh trắc học cục bộ
    A-->>C: Authenticator data + chữ ký
    C->>V: Credential ID + authenticatorData + clientDataJSON + signature
    V->>V: Kiểm tra challenge, origin, RP ID hash, flags, khóa công khai, chữ ký
    V-->>C: Phiên nếu tài khoản/chính sách hợp lệ
~~~

Tại server, xác minh assertion **không chỉ** là thấy một chữ ký khớp. Theo luồng WebAuthn, cần kiểm tra ít nhất:

1. **Challenge:** được server tạo ngẫu nhiên, đủ khó đoán, gắn với yêu cầu hiện tại và không được sử dụng lại.
2. **Origin và loại thao tác:** \`clientDataJSON\` phải chứa đúng origin được phép, đúng challenge và đúng loại thao tác xác thực; xử lý ngữ cảnh cross-origin theo chính sách.
3. **RP ID:** hàm băm RP ID trong \`authenticatorData\` phải khớp RP ID mong đợi.
4. **Credential:** mã credential tương ứng với khóa công khai đã được đăng ký cho tài khoản/định danh hợp lệ.
5. **Chữ ký:** được xác minh trên dữ liệu được tiêu chuẩn xác định, sử dụng khóa công khai đã lưu và thư viện WebAuthn đáng tin cậy.
6. **Cờ UP/UV:** đạt mức user presence và user verification mà RP yêu cầu.
7. **Trạng thái tài khoản và credential:** chưa bị thu hồi, được phép sử dụng trong ngữ cảnh hiện tại; xử lý sign counter nếu authenticator hỗ trợ và chính sách yêu cầu.

**Sign counter** có thể cung cấp tín hiệu bất thường ở một số authenticator, nhưng không phải thiết bị nào cũng cung cấp bộ đếm đơn điệu hữu ích; không nên coi nó là cơ chế chống sao chép tuyệt đối. **Attestation** trong đăng ký có thể hỗ trợ chính sách về loại authenticator, nhưng cần cân nhắc khả năng hỗ trợ và quyền riêng tư, thay vì mặc định bắt buộc mọi người dùng phải gửi thông tin nhận diện thiết bị.

Browser kiểm soát ràng buộc origin/RP ID khi sử dụng API WebAuthn đúng cách. Vì vậy, trang phishing trên miền giả thường không thể lấy assertion hợp lệ cho RP ID của trang thật. Tuy nhiên, nếu ứng dụng bị XSS hoặc thiết bị bị chiếm quyền sau đăng nhập, kẻ tấn công vẫn có thể thao tác **trong phiên hợp lệ**. Authenticator chống phishing không thay thế kiểm soát giao dịch, bảo vệ client và phân quyền ở backend.

## 7. Authenticator và client tương tác qua giao thức nào?

Giao thức quy định **ai đặt câu hỏi, ai tạo bằng chứng và ai kiểm chứng**. Không nên xem mọi authenticator như một ô nhập mã giống nhau.

| Giao thức/cơ chế | Client làm gì? | Authenticator làm gì? | Verifier kiểm tra gì? |
|---|---|---|---|
| **Mật khẩu qua HTTPS** | Thu và gửi bí mật trong yêu cầu an toàn | Người dùng nhớ hoặc trình quản lý mật khẩu điền | Password hash/KDF, trạng thái và chính sách |
| **TOTP** | Thu mã, gắn với phiên MFA đang chờ | Tính mã từ bí mật và thời gian | Mã, cửa sổ thời gian, giới hạn thử và chống phát lại |
| **WebAuthn** | Gọi API WebAuthn, duy trì origin, chuyển yêu cầu/kết quả | Sử dụng khóa riêng, xử lý UP/UV, ký assertion | Challenge, origin/RP ID, chữ ký, flags, credential |
| **FIDO CTAP2** | Browser/OS giao tiếp với authenticator ngoài hoặc trong nền tảng | Thực thi thao tác authenticator theo chuẩn CTAP | RP vẫn xác minh WebAuthn response nhận được |
| **mTLS** | Thiết lập kết nối TLS có chứng chỉ client | Giữ và sử dụng khóa riêng phù hợp | Chuỗi tin cậy, chứng chỉ, danh tính và chính sách cấp quyền |
| **OIDC/SSO** | Chuyển hướng theo giao thức, nhận kết quả qua flow | Tại IdP có thể dùng mật khẩu, passkey, MFA | RP kiểm tra token/response từ IdP và ràng buộc phiên |

**CTAP2** là giao thức giữa client nền tảng (ví dụ browser/OS) và authenticator FIDO; **WebAuthn** là giao diện/giao thức ở phía ứng dụng web và RP. Một hệ thống dùng WebAuthn không có nghĩa backend tự nói chuyện trực tiếp với thiết bị USB.

Với chứng chỉ **mTLS**, bằng chứng được xác minh ở tầng TLS của kết nối. Nó thường hợp với dịch vụ hoặc thiết bị quản lý; việc kết nối có chứng chỉ hợp lệ **không tự thay** quyết định người dùng cuối nào được đọc tài nguyên nào.

## 8. Xác thực nhiều yếu tố và sự độc lập giữa các yếu tố

**MFA (multi-factor authentication)** yêu cầu bằng chứng từ các nhóm yếu tố khác nhau, thường gồm:

- **Điều biết:** mật khẩu, PIN ghi nhớ.
- **Điều sở hữu/kiểm soát:** khóa bảo mật, thiết bị hoặc bộ sinh OTP.
- **Đặc tính của người dùng:** sinh trắc học được cơ chế xác thực hỗ trợ.

Không phải mọi yêu cầu nhập hai giá trị đều là MFA. Hai mật khẩu khác nhau vẫn thuộc nhóm “điều biết”; mã gửi đến cùng hộp thư vừa dùng đặt lại mật khẩu có thể không tạo được độ độc lập mong muốn. Mức bảo đảm thực tế cũng phụ thuộc **quy trình đăng ký, thay thế và khôi phục yếu tố**.

### Passkey là một yếu tố hay nhiều yếu tố?

Passkey là credential khóa công khai. Khi authenticator yêu cầu **user verification** bằng PIN hoặc sinh trắc học cục bộ để cho phép dùng khóa riêng, cách triển khai có thể đáp ứng các yêu cầu xác thực đa yếu tố theo chính sách và chuẩn áp dụng. Tuy nhiên, RP cần kiểm tra đúng tín hiệu **UV** và mức bảo đảm cần thiết; **không suy luận** chỉ từ việc người dùng nói “đăng nhập bằng passkey” rằng mọi yêu cầu MFA đều được đáp ứng.

Mức bảo đảm cũng chịu ảnh hưởng bởi authenticator có đồng bộ khóa hay không, khả năng khôi phục, cách bảo vệ thiết bị và quản trị credential. Các lựa chọn này nên được ghi thành chính sách rõ ràng cho từng lớp tài nguyên.

### Xác thực tăng cường trước thao tác nhạy cảm

Giả sử người dùng đã đăng nhập để xem thông tin. Khi họ muốn đổi email khôi phục hoặc cấp vai trò quản trị, server có thể yêu cầu **step-up authentication**:

1. Xác định thao tác và mức rủi ro, không chỉ kiểm tra đã đăng nhập.
2. Tạo yêu cầu xác thực mới gắn với phiên/ngữ cảnh hiện tại.
3. Yêu cầu authenticator có mức bảo đảm cần thiết.
4. Xác minh kết quả tại backend và ghi nhận thời điểm/mức xác thực.
5. Kiểm tra quyền thực hiện hành động và, khi phù hợp, ràng buộc bằng chứng với **chi tiết giao dịch**.

Việc “vừa xác thực lại” không tự ngăn tráo thông tin giao dịch sau đó. Với hành động như chuyển tiền, hệ thống cần đảm bảo người dùng xác nhận đúng người nhận và số tiền theo cơ chế phù hợp.

## 9. Ranh giới tin cậy và các đường tấn công

| Đường tấn công | Điều gì bị lợi dụng? | Ảnh hưởng tới client/authenticator | Hướng bảo vệ |
|---|---|---|---|
| **Phishing** | Trang giả yêu cầu mật khẩu hoặc mã OTP | Client giả thu bí mật người dùng nhập | Dùng xác thực gắn origin như WebAuthn, kiểm tra miền, giảm đường dự phòng yếu |
| **Replay** | Dùng lại mã hoặc response đã chặn được | Bằng chứng không gắn challenge/phiên hoặc không tiêu thụ | Challenge ngẫu nhiên một lần, thời hạn ngắn, chống tái sử dụng |
| **Credential stuffing** | Mật khẩu tái sử dụng bị lộ từ nơi khác | Kẻ tấn công không cần chiếm authenticator gốc | Passkey/MFA, kiểm tra mật khẩu lộ, giới hạn thử, giám sát |
| **Push fatigue** | Liên tục gửi yêu cầu MFA để người dùng bấm đồng ý | Authenticator push nhận yêu cầu ngoài ý muốn | Hạn chế số push, ngữ cảnh rõ ràng, number matching hoặc đổi phương thức |
| **Đánh cắp phiên/token** | XSS, malware, log rò rỉ hoặc cookie yếu | Không cần xác thực lại nếu có phiên sử dụng được | HttpOnly/Secure/SameSite phù hợp, giảm XSS/CSRF, thời hạn, thu hồi |
| **XSS trong RP thật** | Mã độc chạy cùng origin tin cậy | Có thể gọi API trong phiên hoặc yêu cầu thao tác khi người dùng hiện diện | Chống XSS, CSP phù hợp, xác nhận giao dịch và phân quyền |
| **Đăng ký authenticator trái phép** | Phiên bị chiếm để thêm passkey/MFA mới | Kẻ gian gắn credential của mình vào tài khoản | Re-auth/step-up, thông báo thay đổi, giám sát và thu hồi |
| **Khôi phục tài khoản yếu** | Hỗ trợ viên hoặc đường reset thiếu kiểm tra | Vượt qua authenticator mạnh bằng kênh khác | Recovery có bảo đảm tương xứng, ghi log, kiểm tra trạng thái |
| **Lộ khóa riêng/chứng chỉ** | Khóa dịch vụ lưu sai chỗ hoặc bị sao chép | Kẻ tấn công trình bằng chứng như dịch vụ thật | KMS/HSM hoặc vùng khóa bảo vệ, vòng đời và thu hồi |

### Đừng nhầm xác thực thành phân quyền

Ví dụ, người dùng A xác thực WebAuthn thành công nhưng gọi:

~~~http
GET /api/invoices/other-user-invoice
Authorization: Bearer <access_token>
~~~

API phải kiểm tra token **đúng đối tượng nhận**, còn hiệu lực và có quyền đọc **hóa đơn cụ thể**. Một passkey hợp lệ không cho A quyền đọc hóa đơn của B. Tương tự, client không thể tự tuyên bố \`role=admin\` rồi được server chấp nhận.

### Đừng nhầm thiết bị tin cậy với giao dịch tin cậy

Người dùng có thể xác thực thành công trên điện thoại bị cài ứng dụng độc hại; ứng dụng đó có thể đổi địa chỉ nhận tiền sau khi người dùng xác thực. Bằng chứng cho danh tính và bằng chứng cho **ý định thực hiện một hành động cụ thể** là hai yêu cầu liên quan nhưng khác nhau.

## 10. Đăng ký, thay thế và thu hồi authenticator

Authenticator được dùng trong đăng nhập chỉ sau khi nó được **liên kết hợp lệ với tài khoản**. Giai đoạn đăng ký (enrollment) nhạy cảm tương đương việc cấp thêm một phương thức đăng nhập cho người dùng.

### Đăng ký ban đầu

Một quy trình tiêu biểu:

1. Xác minh tài khoản đang ở trạng thái cho phép đăng ký, người yêu cầu có quyền và đã đạt mức xác thực cần thiết.
2. Khởi tạo một yêu cầu đăng ký riêng, có nonce/challenge ngẫu nhiên và thời hạn.
3. Dùng cơ chế phù hợp: tạo bí mật TOTP và trao đổi qua kênh bảo vệ, hoặc yêu cầu authenticator tạo credential WebAuthn mới.
4. Server kiểm tra bằng chứng đăng ký, nguồn gốc, định danh và chính sách; **không chỉ lưu dữ liệu mà client tự gửi**.
5. Liên kết credential vào đúng tài khoản và ghi sự kiện audit; thông báo thay đổi qua kênh phù hợp.

Với WebAuthn, server thường lưu **credential ID và khóa công khai** kèm metadata phục vụ chính sách. Server không cần và không nên nhận khóa riêng. Với TOTP, server và ứng dụng authenticator cần chia sẻ bí mật, nên bí mật TOTP phải được lưu dưới cơ chế bảo vệ phù hợp và tránh hiển thị lại sau thiết lập.

### Đăng ký bổ sung hoặc thay thế

Khi thêm passkey hoặc thiết bị MFA mới, cần cân nhắc **xác thực lại ở mức đủ mạnh** và xác nhận ý định. Nếu không, một phiên web bị lấy cắp có thể trở thành quyền sở hữu tài khoản lâu dài thông qua việc kẻ tấn công gắn authenticator của họ.

Khi mất thiết bị:

- Thu hồi credential hoặc thiết bị cụ thể thay vì vô hiệu hóa bừa mọi phương thức còn hoạt động.
- Sử dụng quy trình khôi phục có mức bảo đảm phù hợp với quyền tài khoản.
- Rà soát phiên, token và các credential vừa đăng ký.
- Thông báo thay đổi và lưu dấu vết để chủ tài khoản có thể phát hiện bất thường.

Nếu chỉ còn một authenticator, thiết kế cần dự trù đường khôi phục ngay từ đầu. Nhưng **không được để đường khôi phục yếu biến một authenticator chống phishing thành hình thức bảo vệ mang tính biểu tượng**.

### Liên kết IdP và tài khoản

Khi client hỗ trợ “đăng nhập với nhà cung cấp danh tính”, nó có thể chuyển hướng đến IdP; authenticator (ví dụ passkey) được sử dụng **ở IdP**. Ứng dụng nhận kết quả liên kết theo giao thức như OIDC, kiểm tra issuer/audience, nonce/state và các điều kiện liên quan trước khi gắn với tài khoản cục bộ.

Không tự động ghép tài khoản chỉ vì hai bên trả về email giống nhau. Trong OIDC, cặp **issuer + subject (iss, sub)** là cơ sở định danh ổn định hơn trong phạm vi nhà phát hành, sau khi đã kiểm tra token đúng cách. Việc liên kết vẫn cần kiểm tra quyền kiểm soát của tài khoản đích và ý định người dùng.

## 11. Thiết kế server: kiểm chứng bằng chứng và cấp phiên

Hãy xem xét một API xử lý **WebAuthn assertion** đã được client gửi về. Mã giả sau nhấn mạnh các bước tin cậy; không thay thế thư viện WebAuthn chuẩn:

~~~typescript
async function finishPasskeyLogin(request) {
  // Challenge và phiên đăng nhập đang chờ do server tạo, có thời hạn.
  const pending = await loadPendingChallenge(request.challengeSessionId);
  if (!pending || pending.expired || pending.used) {
    return authenticationFailed();
  }

  // Tìm credential đã đăng ký bằng ID không tin cậy từ request;
  // chỉ sử dụng public key và chính sách lấy từ kho dữ liệu đáng tin cậy.
  const credential = await findRegisteredCredential(request.credentialId);
  if (!credential || credential.revoked) {
    return authenticationFailed();
  }

  const assertion = await trustedWebAuthnLibrary.verifyAuthentication({
    response: request.assertion,
    expectedChallenge: pending.challenge,
    expectedOrigin: "https://login.example.test",
    expectedRPID: "example.test",
    credentialPublicKey: credential.publicKey,
    requireUserVerification: true,
  });
  if (!assertion.verified) return authenticationFailed();

  // Việc tiêu thụ challenge phải chống đua tranh và chỉ dùng được một lần.
  const consumed = await consumeChallengeAtomically(pending.id);
  if (!consumed) return authenticationFailed();

  const account = await findAccount(credential.accountId);
  if (!account || account.status !== "ACTIVE") {
    return authenticationFailed();
  }

  // Còn phải áp dụng kiểm soát rủi ro, yêu cầu MFA/step-up bổ sung
  // nếu chính sách riêng của hệ thống đòi hỏi.
  return issueSession(account.id, { method: "webauthn", uv: true });
}
~~~

\`expectedOrigin\` và \`expectedRPID\` phải đến từ **cấu hình tin cậy**, không lấy nguyên giá trị client tự gửi. Server cần áp dụng kiểm soát trạng thái challenge và credential một cách nhất quán, kể cả khi có hai yêu cầu đến đồng thời. Trong sản phẩm thực tế, thư viện và API cung cấp nhiều tham số khác; hãy tuân thủ tài liệu và giao thức cụ thể, đồng thời lưu thông tin cần thiết để đánh giá tín hiệu clone/sign counter khi phù hợp.

**Lỗi phổ biến:** sau khi verifier đồng ý, client lưu \`isLoggedIn=true\` vào local storage và backend tin cờ này ở mỗi request. Backend phải dựa trên **phiên hoặc token có thể xác minh**, không dựa trên trạng thái giao diện.

### Phiên sau xác thực

Một phiên web có thể dùng cookie \`Secure\`, \`HttpOnly\`, \`SameSite\` phù hợp; cần cân nhắc session fixation, XSS, CSRF, thời hạn và đăng xuất. Với access token, dịch vụ phải xác minh issuer, audience, thời hạn và phạm vi áp dụng; khi trạng thái tài khoản thay đổi, cần chiến lược thu hồi/hết hạn thích hợp.

**WebAuthn bảo vệ lúc tạo bằng chứng xác thực**; nó không tự bảo vệ mọi token được phát hành sau đó. Nếu attacker lấy được bearer token còn hạn, họ có thể dùng token trong giới hạn mà hệ thống chấp nhận, ngay cả khi họ không có passkey.

## 12. Tình huống thực hành: đăng nhập cổng quản trị

**Bối cảnh:** Một doanh nghiệp có cổng quản trị tài khoản nhân sự. Quản trị viên dùng laptop có trình duyệt, điện thoại có TOTP và khóa bảo mật hỗ trợ passkey. Tài khoản có quyền tạo người dùng, chỉnh vai trò và xuất dữ liệu.

**Thiết kế yêu cầu:**

| Thao tác | Client | Authenticator | Server cần kiểm tra |
|---|---|---|---|
| Đăng nhập vào cổng | Trình duyệt tại miền chính thức | Passkey với UV phù hợp | Challenge, origin, RP ID, chữ ký, account status |
| Thêm authenticator mới | Trình duyệt trong phiên hiện tại | Authenticator hiện có để xác thực lại, sau đó authenticator mới | Quyền sở hữu tài khoản, ý định thêm, kết quả đăng ký mới |
| Xem danh sách nhân viên | Trình duyệt gọi API | Phiên/token từ đăng nhập trước | Tính hợp lệ phiên và quyền xem dữ liệu |
| Cấp quyền quản trị cho người khác | Client hiển thị người nhận và quyền dự định cấp | Step-up phù hợp và xác nhận ngữ cảnh | Quyền cấp vai trò, mức xác thực, chống thay đổi giao dịch |
| Mất khóa bảo mật | Client thực hiện quy trình khôi phục | Phương thức còn lại hoặc quy trình xác minh được kiểm soát | Mức bảo đảm phục hồi, thu hồi credential bị mất |

### Phân tích hai tấn công

**Tấn công A — Trang giả lấy mật khẩu và TOTP.** Kẻ tấn công gửi đường dẫn \`https://portal-login.example.invalid\` giống trang thật. Người dùng nhập mật khẩu và TOTP; kẻ tấn công có thể chuyển tiếp chúng trong thời gian còn hiệu lực. Nếu tài khoản sử dụng WebAuthn với ràng buộc origin/RP ID đúng cách cho đăng nhập, trang giả thường không thể lấy assertion hợp lệ cho miền thật. Tuy vậy, các đường đăng nhập hoặc khôi phục dự phòng yếu vẫn cần được kiểm soát.

**Tấn công B — Phiên đã đăng nhập bị chiếm.** Kẻ tấn công khai thác XSS trên cổng thật, gọi API tạo quản trị viên mới bằng phiên nạn nhân. WebAuthn trước đó vẫn có thể xác thực chính xác chủ tài khoản. Biện pháp bổ sung là chống XSS, phân quyền, step-up gần thao tác và xác nhận nội dung hành động có rủi ro cao.

**Kết luận của tình huống:** cần bảo vệ cả **bằng chứng lúc đăng nhập** và **cách ứng dụng sử dụng quyền sau đăng nhập**.

## 13. Checklist triển khai và kiểm thử

- [ ] Vẽ được chủ thể, client, authenticator, verifier, RP/IdP và API tài nguyên.
- [ ] Client chỉ trình yêu cầu; mọi quyết định xác thực và quyền nhạy cảm đều ở phía tin cậy.
- [ ] Không ghi mật khẩu, OTP, khóa riêng, challenge dùng để xác thực hoặc token bí mật vào log.
- [ ] Mật khẩu được truyền qua HTTPS và lưu bằng KDF có salt, có chống dò đoán và credential stuffing.
- [ ] TOTP/push có giới hạn thử, thời gian, tái sử dụng và chống lạm dụng phù hợp.
- [ ] WebAuthn xác minh challenge, origin, RP ID, credential, chữ ký, UP/UV và trạng thái tài khoản.
- [ ] Khóa riêng passkey không được gửi đến server; thông tin thiết bị/attestation tuân thủ chính sách riêng tư.
- [ ] Yêu cầu đăng ký và thu hồi authenticator phải có đủ bằng chứng và quyền.
- [ ] Khôi phục tài khoản không cho phép hạ cấp âm thầm cơ chế xác thực mạnh.
- [ ] MFA và step-up dựa trên rủi ro, phân biệt nhiều yếu tố với nhiều bước cùng một yếu tố.
- [ ] Token/phiên sau đăng nhập được bảo vệ, hết hạn và thu hồi theo thiết kế.
- [ ] API kiểm tra quyền trên tài nguyên cụ thể, không chỉ kiểm tra người dùng đã đăng nhập.
- [ ] Kiểm thử phishing, replay, challenge cũ, trạng thái tài khoản bị khóa và client tự sửa dữ liệu.
- [ ] Kiểm thử đăng ký thêm credential khi phiên bị chiếm, mất thiết bị và liên kết IdP sai.

### Tự kiểm tra

**Câu 1.** Trong WebAuthn, browser và authenticator làm công việc gì khác nhau?  
*Gợi ý:* Browser/client kết nối RP với API authenticator, gắn ngữ cảnh origin; authenticator sử dụng khóa riêng để tạo bằng chứng, server kiểm tra bằng khóa công khai và chính sách.

**Câu 2.** Vì sao nhập đúng OTP không bảo đảm chống phishing?  
*Gợi ý:* Mã OTP có thể được chuyển tiếp đến website thật trong thời gian còn hiệu lực; mã thường không ràng buộc mật mã với origin.

**Câu 3.** Một passkey đăng nhập thành công nhưng API trả dữ liệu của tài khoản khác. Sai ở đâu?  
*Gợi ý:* Phân quyền cấp đối tượng tại API; thành công trong xác thực không tự trao quyền đọc mọi tài nguyên.

**Câu 4.** Tại sao thao tác thêm passkey mới cần xác thực lại?  
*Gợi ý:* Một phiên bị đánh cắp có thể bị lợi dụng để gắn credential của kẻ tấn công vào tài khoản và duy trì quyền truy cập.

## Ghi nhớ

**Client** tạo trải nghiệm và vận chuyển thông điệp; **authenticator** sử dụng bí mật hoặc khóa để tạo bằng chứng; **verifier** quyết định bằng chứng đó có hợp lệ trong đúng bối cảnh hay không. Bảo vệ danh tính đòi hỏi ranh giới tin cậy rõ ràng giữa ba vai trò, từ credential và thiết bị đến challenge, token và phiên.

Mật khẩu và OTP có thể bị lộ hoặc chuyển tiếp; WebAuthn/passkey có cơ chế chống phishing nhờ ràng buộc origin/RP ID và chứng minh bằng khóa riêng, nhưng vẫn cần bảo vệ client, quản lý credential, khôi phục an toàn, kiểm soát phiên và phân quyền tài nguyên. Khi thiết kế một authentication flow, hãy luôn hỏi: **Ai tạo bằng chứng? Bằng chứng gắn với yêu cầu nào? Ai xác minh? Và sau khi xác minh, chủ thể thực sự được phép làm gì?**
