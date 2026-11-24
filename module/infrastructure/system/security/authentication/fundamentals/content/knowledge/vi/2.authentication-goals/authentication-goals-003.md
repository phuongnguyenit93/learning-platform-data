# Giảm truy cập trái phép

## 1. Vì sao đây là mục tiêu cốt lõi của xác thực?

**Truy cập trái phép** xảy ra khi một chủ thể sử dụng hệ thống, tài khoản hoặc tài nguyên mà không có quyền tương ứng. Trong thực tế, kẻ tấn công có thể biết mật khẩu bị lộ, giả mạo trang đăng nhập, chiếm phiên của người dùng, lợi dụng quy trình khôi phục tài khoản hoặc liên kết tài khoản ngoài ý muốn. Vì vậy, chỉ đặt một biểu mẫu đăng nhập trước ứng dụng không đủ để ngăn truy cập trái phép.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, chúng ta tìm hiểu cách dùng credential, mật khẩu, xác thực đa yếu tố (MFA), passkey, chứng chỉ, token và phiên để xác minh danh tính, đồng thời bảo vệ các luồng liên kết danh tính và khôi phục tài khoản. Với mục tiêu **giảm truy cập trái phép**, câu hỏi thiết kế quan trọng là:

> Bằng chứng nào đủ đáng tin để hệ thống tin rằng yêu cầu này thực sự đến từ chủ thể được khai báo, ở thời điểm và trong ngữ cảnh hiện tại?

Ba khái niệm thường đi cùng nhau nhưng giải quyết các việc khác nhau:

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Định danh (identification)** | Chủ thể tự nhận mình là ai? | Nhập tên đăng nhập alice@example.com. |
| **Xác thực (authentication)** | Có bằng chứng đủ tin cậy cho tuyên bố đó không? | Kiểm tra passkey hoặc mật khẩu kèm MFA. |
| **Phân quyền (authorization)** | Chủ thể đã xác thực được phép làm gì? | Alice chỉ được xem hóa đơn của chính mình. |

Một phiên được xác thực hợp lệ **không** tự động cho phép truy cập mọi dữ liệu. Ngược lại, kiểm tra quyền trên API cũng không cứu được hệ thống nếu kẻ tấn công đã chiếm đúng tài khoản có quyền. Hai lớp bảo vệ phải phối hợp.

Mục tiêu thực tế không phải tuyên bố loại bỏ tuyệt đối mọi tấn công. Mục tiêu là **làm giảm khả năng thành công, giới hạn thiệt hại khi một lớp thất bại, phát hiện hành vi bất thường và có cách thu hồi quyền truy cập**.

## 2. Xác định tài sản, đối thủ và ranh giới tin cậy

Trước khi chọn cơ chế đăng nhập, hãy xác định thứ cần bảo vệ:

- **Bằng chứng xác thực:** mật khẩu, khóa riêng của passkey hoặc chứng chỉ, mã OTP, mã khôi phục.
- **Thông tin duy trì đăng nhập:** session ID, access token, refresh token và cookie.
- **Thao tác nhạy cảm:** thêm thiết bị đăng nhập, đổi mật khẩu, thay phương thức MFA, liên kết nhà cung cấp danh tính, đổi email và khôi phục tài khoản.
- **Dữ liệu, chức năng đích:** hồ sơ cá nhân, giao dịch, dữ liệu doanh nghiệp và các API yêu cầu quyền.

Kẻ tấn công không nhất thiết phải phá mật mã. Họ thường chọn mắt xích dễ khai thác hơn: dùng danh sách mật khẩu lộ từ dịch vụ khác, lừa người dùng nhập OTP, đánh cắp cookie, gửi nhiều yêu cầu đoán mật khẩu hoặc lợi dụng quy trình hỗ trợ để giành lại tài khoản.

### Sơ đồ ranh giới tin cậy

~~~mermaid
flowchart LR
    U["Người dùng / trình duyệt<br/>(môi trường không tin cậy)"]
    E["Điểm vào ứng dụng<br/>TLS, chống lạm dụng"]
    A["Dịch vụ xác thực<br/>kiểm tra bằng chứng"]
    I[("Kho định danh<br/>và xác thực")]
    S[("Kho phiên / token<br/>và trạng thái thu hồi")]
    R["API tài nguyên<br/>kiểm tra quyền"]
    U -->|"Credential hoặc phản hồi thử thách"| E
    E --> A
    A <--> I
    A <--> S
    E -->|"Yêu cầu kèm phiên"| R
    R -->|"Xác minh phiên / quyền"| S
~~~

Sơ đồ là mô hình khái niệm, không quy định bắt buộc phải triển khai thành các dịch vụ tách biệt. Ranh giới quan trọng nằm giữa **dữ liệu do client cung cấp** và **quyết định do server kiểm chứng**:

1. Client có thể gửi tên tài khoản, credential, token hoặc cờ giao diện, nhưng không được tự quyết định “đã đăng nhập” hay “là quản trị viên”.
2. Server phải kiểm tra bằng chứng xác thực bằng cơ chế phù hợp; mọi thao tác nhạy cảm dựa trên kết quả đã kiểm chứng.
3. Mỗi yêu cầu tới tài nguyên được bảo vệ phải có cơ chế xác thực phiên/token hợp lệ và kiểm tra quyền tương ứng.
4. Dữ liệu từ nhà cung cấp danh tính bên ngoài (IdP) cần được kiểm tra chữ ký, issuer, audience, thời hạn và liên kết danh tính đúng cách, thay vì tin mọi thông tin hiển thị trong trình duyệt.

**Điểm suy luận:** nếu mật khẩu được bảo vệ rất tốt nhưng đường dẫn “quên mật khẩu” cho phép chiếm tài khoản chỉ nhờ một thông tin công khai, ranh giới tin cậy vẫn bị phá vỡ.

## 3. Những con đường dẫn tới truy cập trái phép

| Kiểu tấn công | Cách kẻ tấn công tiến hành | Rủi ro chính | Lớp giảm thiểu tiêu biểu |
| --- | --- | --- | --- |
| **Credential stuffing** | Dùng các cặp tài khoản/mật khẩu đã lộ ở nơi khác để thử hàng loạt. | Đăng nhập thành công do người dùng tái sử dụng mật khẩu. | Passkey, MFA, phát hiện đăng nhập bất thường, giới hạn tốc độ nhiều chiều. |
| **Password spraying / brute force** | Thử một vài mật khẩu phổ biến trên nhiều tài khoản, hoặc đoán liên tục một tài khoản. | Khai thác mật khẩu yếu và năng lực thử nhiều lần. | Chặn mật khẩu yếu/lộ, kiểm soát tốc độ theo tài khoản và nguồn, cảnh báo. |
| **Phishing và chuyển tiếp OTP** | Dẫn người dùng tới trang giả, thu thập mật khẩu và mã OTP gần như ngay lập tức. | Kẻ tấn công hoàn thành một lần đăng nhập hợp lệ. | Passkey/WebAuthn gắn với origin, giáo dục nhận biết, kiểm soát thiết bị và phiên. |
| **Replay** | Phát lại một bằng chứng hoặc thông điệp xác thực đã ghi được. | Hệ thống chấp nhận bằng chứng cũ. | Thử thách có nonce, thời hạn ngắn, kiểm tra một lần và ràng buộc ngữ cảnh. |
| **Chiếm phiên / token** | Lấy cookie hoặc token từ thiết bị, ứng dụng hay log bị lộ. | Vượt qua bước đăng nhập và đôi khi cả MFA. | Bảo vệ cookie/token, TTL phù hợp, phát hiện và thu hồi phiên, xác thực lại thao tác nhạy cảm. |
| **Lạm dụng khôi phục tài khoản** | Chiếm email, số điện thoại, mã khôi phục hoặc thao túng hỗ trợ. | Đổi credential rồi khóa chủ tài khoản ra ngoài. | Luồng khôi phục chống lạm dụng, cảnh báo thay đổi, xác minh đủ mạnh và thu hồi phiên cũ. |
| **Liên kết danh tính sai** | Gắn một danh tính đăng nhập bên ngoài vào tài khoản nội bộ không thuộc sở hữu của mình. | Chiếm tài khoản qua SSO/social login. | Kiểm tra issuer và subject ổn định, yêu cầu chứng minh quyền sở hữu và xác thực lại khi liên kết. |

Các cơ chế trên không thay thế lẫn nhau. **MFA** giúp khi mật khẩu đã lộ nhưng không tự ngăn một phiên đã bị đánh cắp; **rate limit** giảm thử mật khẩu hàng loạt nhưng không xử lý người dùng nhập mật khẩu và OTP vào trang giả; **token ngắn hạn** giới hạn thời gian lạm dụng nhưng không đảm bảo việc cấp token ban đầu là an toàn.

## 4. Thiết kế phòng vệ theo vòng đời danh tính

### 4.1. Đăng ký và thiết lập credential

Ở thời điểm tạo tài khoản, hệ thống cần kiểm soát việc gắn danh tính với phương thức xác thực:

- Xác minh quyền kiểm soát địa chỉ email hoặc số điện thoại khi dùng chúng làm kênh liên hệ hay khôi phục. Việc nhận được email **chỉ chứng minh quyền kiểm soát hộp thư tại thời điểm đó**, không chứng minh danh tính pháp lý.
- Nếu dùng mật khẩu, khuyến khích mật khẩu dài, duy nhất và hỗ trợ trình quản lý mật khẩu. Phía server lưu **bản băm mật khẩu có salt**, với thuật toán chuyên dụng như Argon2id, scrypt hoặc bcrypt được cấu hình thích hợp; không lưu plaintext hoặc mã hóa có thể đảo ngược để dùng lại.
- Nếu dùng passkey theo FIDO2/WebAuthn, server lưu **khóa công khai** và thông tin credential; khóa riêng được bảo vệ trong authenticator hoặc cơ chế đồng bộ khóa của nền tảng. Khi đăng nhập, authenticator ký dữ liệu thử thách, và server kiểm tra chữ ký, challenge, origin, RP ID cùng các yêu cầu chính sách liên quan.
- Bảo vệ cả thao tác **đăng ký thêm credential**. Nếu ai đó có một phiên bị đánh cắp và được thêm passkey mới mà không cần xác thực lại, họ có thể duy trì quyền truy cập dài hạn.

### 4.2. Đăng nhập và xác minh nhiều yếu tố

Mật khẩu là yếu tố **điều người dùng biết**; thiết bị/khóa bảo mật là yếu tố **điều người dùng sở hữu**; sinh trắc học thường là cách mở khóa authenticator cục bộ, không nhất thiết là dữ liệu sinh trắc học được gửi tới server.

**MFA** kết hợp những loại yếu tố thích hợp để một mật khẩu bị lộ chưa đủ đăng nhập. Tuy nhiên, các phương thức MFA có khả năng chống phishing khác nhau:

| Cơ chế | Điểm mạnh | Giới hạn cần hiểu |
| --- | --- | --- |
| Mật khẩu đơn lẻ | Phổ biến, dễ tích hợp. | Có thể bị đoán, tái sử dụng hoặc phishing. |
| Mật khẩu + mã TOTP | Giảm hiệu quả của mật khẩu bị lộ đơn lẻ. | Mã có thể bị phishing và chuyển tiếp trong thời gian hiệu lực. |
| Mật khẩu + SMS OTP | Có thêm bước so với chỉ mật khẩu. | Phụ thuộc số điện thoại, có nguy cơ SIM swap và phishing. |
| Passkey / khóa bảo mật WebAuthn | Xác thực dựa trên khóa mật mã, gắn với website/app hợp lệ; chống phishing tốt. | Cần quản lý thiết bị, đồng bộ và quy trình phục hồi/đăng ký khóa an toàn. |
| Chứng chỉ máy khách trong mTLS | Hữu ích cho xác thực thiết bị hoặc hệ thống với hệ thống. | Cần quản lý vòng đời khóa, chứng chỉ, tin cậy CA và thu hồi; không tự chứng minh người vận hành hợp lệ. |

Passkey có xác minh người dùng (user verification) phù hợp có thể đáp ứng yêu cầu xác thực mạnh mà không cần thêm mật khẩu. Không nên mặc định bắt người dùng nhập một mã dễ phishing sau mỗi lần xác thực bằng passkey; hãy chọn mức bảo đảm theo yêu cầu hệ thống và rủi ro của thao tác.

Để giảm **đăng nhập tự động quy mô lớn**, triển khai lớp kiểm soát tổng hợp:

1. Giới hạn số lần thử theo **tài khoản, nguồn truy cập và tín hiệu thiết bị/ngữ cảnh**, kể cả khi hệ thống có nhiều máy chủ.
2. Có tăng thời gian chờ, thách thức bổ sung hoặc chặn có chọn lọc khi thấy dấu hiệu bất thường; tránh khóa tài khoản vô thời hạn chỉ vì một địa chỉ IP hoặc vài lần nhập sai, vì kẻ tấn công có thể lợi dụng để gây từ chối dịch vụ.
3. Giữ phản hồi lỗi đủ thống nhất để hạn chế **liệt kê tài khoản** qua nội dung, mã lỗi hoặc khác biệt thời gian dễ khai thác.
4. Không coi IP, vị trí hay fingerprint thiết bị là bằng chứng danh tính độc lập; đó chỉ là tín hiệu hỗ trợ đánh giá rủi ro.

### 4.3. Bảo vệ phiên và token sau khi đăng nhập

Đăng nhập thành công chỉ là **điểm bắt đầu** của một chuỗi yêu cầu. Nếu kẻ tấn công lấy được session ID hoặc bearer token, họ có thể truy cập mà không cần nhập lại credential.

Với **phiên dùng cookie** trên trình duyệt, một thiết kế điển hình cần:

- Phân phối qua HTTPS; gắn thuộc tính **Secure**, **HttpOnly** và **SameSite** phù hợp với luồng ứng dụng.
- Tạo session ID khó đoán bằng bộ sinh ngẫu nhiên mật mã; đổi session ID khi đăng nhập hoặc nâng quyền để giảm session fixation.
- Có thời hạn phiên, chính sách hết hạn khi không hoạt động nếu phù hợp, cùng khả năng đăng xuất và thu hồi phiên từ phía server.
- Bảo vệ yêu cầu thay đổi trạng thái trước **CSRF** khi dùng cookie tự động gửi, chẳng hạn bằng CSRF token và kiểm tra Origin/Referer phù hợp. SameSite hỗ trợ giảm rủi ro nhưng không nên là lớp kiểm soát duy nhất cho mọi tình huống.

Với **access token/refresh token**:

- Chỉ nhận token qua kênh bảo mật; không đưa token, mã xác thực, mật khẩu hoặc mã khôi phục vào URL, log hay công cụ phân tích.
- Nếu token là JWT, kiểm tra chữ ký bằng thuật toán/khóa được tin cậy, cùng **issuer**, **audience**, thời hạn và các claim bắt buộc; tuyệt đối không chỉ giải mã payload rồi tin nội dung.
- Thiết kế access token có thời gian sống phù hợp; bảo vệ refresh token chặt hơn, xoay vòng hoặc ràng buộc token khi kiến trúc cho phép và có cơ chế phát hiện/thu hồi khi bị lộ.
- Đối với cookie/session hoặc token, cần xác thực lại khi đổi credential, thêm authenticator, chuyển tiền, xuất dữ liệu nhạy cảm hoặc hành động có mức rủi ro cao.

**OAuth 2.0** chủ yếu là khung ủy quyền, trong khi **OpenID Connect (OIDC)** bổ sung lớp xác thực danh tính. Một access token dùng để gọi API không mặc nhiên là bằng chứng thích hợp để ứng dụng tự kết luận ai đang đăng nhập; việc nhận danh tính từ OIDC phải kiểm tra ID token và ngữ cảnh giao thức đúng cách.

### 4.4. Khôi phục và liên kết tài khoản

Khôi phục là một **con đường xác thực thay thế**. Do đó, không thể đặt mức kiểm tra thấp đến mức vô hiệu hóa MFA hoặc passkey của đăng nhập thông thường.

- Cấp mã/đường dẫn khôi phục có ngẫu nhiên đủ mạnh, thời hạn ngắn, dùng một lần và gắn với tài khoản/luồng cụ thể; lưu dấu xác minh ở dạng an toàn nếu cần đối soát.
- Không dùng câu hỏi bảo mật dựa trên dữ liệu dễ tra cứu (quê quán, tên người thân...) làm yếu tố duy nhất.
- Xử lý yêu cầu quên mật khẩu với phản hồi không tiết lộ tài khoản tồn tại hay không; giới hạn tần suất gửi để chống spam và dò tài khoản.
- Gửi thông báo khi thay đổi credential, địa chỉ khôi phục, MFA hoặc khi xuất hiện đăng nhập đáng ngờ; với tài khoản nhạy cảm, cân nhắc trì hoãn hay kiểm tra tăng cường cho thay đổi rủi ro cao.
- Sau khi xác nhận sự cố chiếm tài khoản hoặc hoàn tất khôi phục nhạy cảm, thu hồi phiên/token cũ khi phù hợp và cung cấp cách xem, đăng xuất các thiết bị.
- Khi liên kết đăng nhập Google, doanh nghiệp hoặc một IdP khác, liên kết theo cặp **issuer + subject ổn định** đã được xác minh. Không tự động hợp nhất chỉ vì email trong hai tài khoản trùng nhau; yêu cầu chứng minh quyền với cả tài khoản hiện tại và danh tính mới theo mức rủi ro.

## 5. Ví dụ luồng đăng nhập có kiểm soát

Giả sử một dịch vụ quản lý hồ sơ cho phép đăng nhập bằng mật khẩu + TOTP hoặc passkey. Một người cố đăng nhập liên tiếp vào tài khoản nhân viên từ mạng lạ.

~~~mermaid
flowchart TD
    A["Nhận yêu cầu đăng nhập"] --> B{"Vượt giới hạn<br/>chống lạm dụng?"}
    B -->|Có| X["Trì hoãn / chặn tạm thời<br/>và ghi nhận tín hiệu"]
    B -->|Không| C["Kiểm tra credential<br/>trên server"]
    C -->|Sai| F["Trả lỗi chung<br/>và ghi nhận thất bại"]
    C -->|Đúng| D{"Chính sách yêu cầu<br/>xác minh bổ sung?"}
    D -->|Có| E{"Yếu tố / thử thách<br/>hợp lệ?"}
    E -->|Không| F
    E -->|Có| G["Tạo phiên mới<br/>với phạm vi hợp lệ"]
    D -->|Không| G
    G --> H["Trả cookie/token an toàn<br/>ghi sự kiện đăng nhập"]
    H --> I["Mỗi API tiếp tục kiểm tra<br/>phiên và quyền"]
~~~

Mã giả dưới đây minh họa **thứ tự quyết định**, không phải đoạn mã hoàn chỉnh để đưa vào môi trường production:

~~~text
login(request):
    signals = collectAbuseSignals(request)  // tài khoản, nguồn, nhịp thử, ngữ cảnh
    if abusePolicy.denies(signals):
        audit("login_restricted", sanitizedMetadata)
        return genericLoginFailureOrRetryLater()

    account = findAccountByIdentifier(request.identifier)
    credentialValid = verifyCredentialSafely(account, request.proof)
    // Khi tài khoản không tồn tại, vẫn dùng cách xử lý giúp hạn chế lộ thông tin.
    if not credentialValid:
        audit("login_failed", sanitizedMetadata)
        return genericLoginFailure()

    if policy.requiresAdditionalProof(account, signals, request.proof):
        if not verifyFreshAdditionalProof(account, request):
            audit("login_failed", sanitizedMetadata)
            return genericLoginFailure()

    session = createFreshSession(account.id, policy.allowedAssurance())
    audit("login_succeeded", sanitizedMetadata)
    return responseWithProtectedSession(session)
~~~

Trong triển khai thực tế, **verifyCredentialSafely** cho mật khẩu phải dùng thuật toán kiểm tra hash phù hợp, còn với passkey phải kiểm tra chữ ký và ngữ cảnh WebAuthn. Việc phân loại yếu tố và mức bảo đảm phải dựa trên bằng chứng thật sự được kiểm tra; không được tin giá trị như “mfa=true” do client gửi. Cần xử lý đồng thời, giới hạn số lần thử OTP và đảm bảo thử thách một lần/đã hết hạn không bị chấp nhận lại.

**Hai tình huống đối chiếu:**

- **Kẻ tấn công có mật khẩu từ vụ rò rỉ dữ liệu:** nếu tài khoản yêu cầu TOTP, họ chưa có đủ bằng chứng để hoàn thành đăng nhập. Passkey gắn origin còn giảm nguy cơ mật khẩu bị phishing ngay từ đầu. Nhưng các cơ chế này phải đi kèm phát hiện lạm dụng để tránh hàng nghìn lượt thử.
- **Kẻ tấn công có cookie phiên từ thiết bị nhiễm mã độc:** màn hình đăng nhập và MFA có thể không được kích hoạt. Bảo vệ token, khả năng thu hồi phiên và xác thực lại các thao tác nhạy cảm mới là các lớp kiểm soát trực tiếp ở tình huống này.

## 6. Đo lường hiệu quả mà không làm hỏng trải nghiệm

Tăng số lần hỏi mật khẩu hoặc OTP không đồng nghĩa với tăng an toàn. Một thiết kế tốt cân bằng **khả năng chống tấn công**, **khả năng sử dụng** và **khả năng khôi phục hợp lệ**.

Nên theo dõi các nhóm tín hiệu sau, với dữ liệu đã hạn chế hoặc ẩn danh theo chính sách riêng tư:

| Nhóm | Câu hỏi đo lường | Cách diễn giải |
| --- | --- | --- |
| Đăng nhập bất thường | Có bao nhiêu đợt thử tự động, password spraying hoặc credential stuffing được phát hiện? | Thể hiện áp lực tấn công và khả năng quan sát; con số tăng không tự chứng minh an toàn giảm. |
| Truy cập trái phép đã xác nhận | Có bao nhiêu sự cố chiếm tài khoản, phiên hoặc API được xác minh? | Đo kết quả thực, cần phân biệt với cảnh báo chưa xác thực. |
| Mức bảo vệ credential | Bao nhiêu tài khoản có MFA/passkey; phương thức nào chịu phishing tốt? | Đo độ phủ và chất lượng của phòng vệ, không chỉ đếm số yếu tố. |
| Hiệu quả phản ứng | Mất bao lâu từ khi phát hiện đến khi thu hồi phiên/credential bị lộ? | Đo khả năng giới hạn thiệt hại. |
| Tác động tới người hợp lệ | Tỷ lệ đăng nhập thành công, khóa nhầm, rớt ở bước MFA và hoàn thành khôi phục là bao nhiêu? | Phát hiện kiểm soát quá chặt gây cản trở hoặc tăng yêu cầu hỗ trợ. |

Log xác thực cần đủ để điều tra: thời điểm, loại sự kiện, nguồn/ngữ cảnh đã giảm thiểu dữ liệu nhạy cảm, kết quả và mã tương quan. **Không ghi mật khẩu, OTP, mã khôi phục, cookie hay token thô.** Hệ thống cảnh báo nên phân biệt nhiều lượt thất bại hợp lệ với chiến dịch tấn công; một địa chỉ IP chung của văn phòng có thể đại diện cho nhiều người dùng.

## 7. Tự kiểm tra thiết kế

Xét một ứng dụng nội bộ có các đặc điểm:

1. Nhân viên đăng nhập bằng mật khẩu và SMS OTP.
2. Mỗi lần đăng nhập thành công tạo cookie phiên tồn tại 30 ngày.
3. Trang đổi số điện thoại khôi phục chỉ yêu cầu phiên đang còn hiệu lực.
4. Nút “đăng xuất” xóa cookie trên trình duyệt nhưng server không vô hiệu hóa phiên.

Hãy xác định ít nhất ba con đường khiến kẻ tấn công có thể tiếp tục truy cập trái phép. Một hướng phân tích:

- **SIM swap hoặc phishing OTP:** mật khẩu + SMS chưa chống phishing tốt; cân nhắc passkey hoặc khóa bảo mật cho tài khoản cần mức bảo đảm cao.
- **Chiếm cookie:** phiên dài hạn bị lộ vẫn dùng được; cần cân nhắc thời hạn thích hợp, ràng buộc ngữ cảnh khi phù hợp, giám sát và thu hồi phía server.
- **Đổi kênh khôi phục:** một phiên bị chiếm có thể chuyển số khôi phục sang số của kẻ tấn công; thao tác này nên yêu cầu xác thực lại, thông báo và kiểm soát rủi ro.
- **Đăng xuất không thu hồi phiên:** bản sao cookie vẫn còn hiệu lực; server cần có trạng thái phiên hoặc cơ chế thu hồi phù hợp với kiến trúc token.

Khi rà soát một luồng khác, có thể dùng năm câu hỏi cố định:

1. **Ai đang khẳng định danh tính, bằng chứng lấy từ đâu, ai thực sự xác minh?**
2. **Bằng chứng có thể bị đoán, sao chép, phishing hoặc phát lại không?**
3. **Sau đăng nhập, phiên/token được bảo vệ, hết hạn và thu hồi như thế nào?**
4. **Nếu mất thiết bị hoặc credential, đường khôi phục có dễ bị lạm dụng hơn đường đăng nhập không?**
5. **Nếu một lớp bảo vệ thất bại, hệ thống phát hiện, giới hạn phạm vi và phản ứng ra sao?**

## 8. Ghi nhớ

Giảm truy cập trái phép là **mục tiêu xuyên suốt vòng đời xác thực**. Hệ thống cần kiểm tra đúng danh tính ở thời điểm đăng nhập, chống đoán và phishing, bảo vệ phiên/token trong mọi yêu cầu, giữ an toàn khi liên kết hoặc khôi phục tài khoản, rồi tiếp tục kiểm tra quyền ở tài nguyên đích. Không một yếu tố riêng lẻ nào đủ cho mọi tình huống; thiết kế an toàn đến từ việc xác định đúng ranh giới tin cậy và phối hợp các lớp kiểm soát tương ứng với mối đe dọa.
