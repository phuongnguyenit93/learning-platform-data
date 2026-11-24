# Authenticator assurance

## 1. Authenticator assurance là gì?

**Authenticator assurance** là mức độ tin cậy mà hệ thống có thể đặt vào **phương thức xác thực và bằng chứng do phương thức đó tạo ra** khi kết luận rằng chủ thể hiện tại đang kiểm soát authenticator đã gắn với một tài khoản. Đánh giá này liên quan tới cách thiết bị hoặc bí mật được cấp phát, bảo vệ, sử dụng, kiểm tra và thu hồi. Một mật khẩu, mã TOTP, passkey hoặc chứng chỉ có những đặc tính khác nhau trước phishing, replay, đánh cắp bí mật và giả mạo thiết bị.

Trong các tiêu chuẩn như **NIST SP 800-63B**, khái niệm liên quan trực tiếp là **Authentication Assurance Level (AAL)**: *mức đảm bảo của toàn bộ quá trình xác thực*. AAL không chỉ là nhãn gắn lên từng sản phẩm hoặc giao thức. Muốn đạt một AAL nhất định, hệ thống phải xem xét **tổ hợp authenticator, cách đăng ký và ràng buộc với tài khoản, giao thức xác minh, quản lý vòng đời, phiên và các yêu cầu vận hành** theo phiên bản tiêu chuẩn và chính sách áp dụng.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, chủ đề này nối credential, mật khẩu, MFA, passkey và chứng chỉ với token, phiên, liên kết danh tính và khôi phục tài khoản. Hiểu authenticator assurance giúp thiết kế luồng xác thực an toàn, mô hình hóa ranh giới tin cậy và phòng chống phishing, replay, lạm dụng đăng nhập.

Sau bài học, người học có thể:

- Phân biệt độ mạnh của **một authenticator** với AAL của **một sự kiện xác thực hoàn chỉnh**.
- Nhận biết ý nghĩa thực hành của AAL1, AAL2 và AAL3.
- Giải thích tại sao “hai bước” chưa chắc là MFA đủ mạnh, và tại sao không phải mọi passkey đều tương đương.
- Lập chính sách step-up, reauthentication, session và recovery dựa trên rủi ro và thuộc tính thực sự đã kiểm chứng.
- Đánh giá trust boundary giữa trình duyệt, authenticator, identity provider, ứng dụng và API.

> Nguyên tắc: **mức bảo đảm phải được suy ra từ quy trình đã xác minh**, không suy từ tên công nghệ, nhãn “MFA enabled” hoặc một claim do client tự khai.

## 2. Bốn câu hỏi trước khi gán mức tin cậy

Hãy xét một yêu cầu đăng nhập bất kỳ. Hệ thống cần trả lời được:

1. **Chủ thể kiểm soát cái gì?** Bí mật trong trí nhớ, thiết bị riêng, private key, authenticator đa yếu tố, hay chỉ một kênh như email?
2. **Điều đó đã được chứng minh bằng cách nào?** So khớp mật khẩu, mã dùng một lần, thử thách mật mã, chữ ký được kiểm chứng, hoặc assertion từ IdP?
3. **Kẻ tấn công có thể lấy hoặc chuyển tiếp bằng chứng không?** Bằng chứng có ràng buộc với origin, relying party, challenge, phiên, khóa và bên nhận hay không?
4. **Kết luận còn phù hợp ở thời điểm sử dụng không?** Authenticator có còn được gắn với đúng principal, session có còn hiệu lực, người dùng có vừa xác thực lại, đã có thay đổi hoặc sự kiện khôi phục nào không?

Ví dụ: hệ thống nhận đúng **mật khẩu + mã TOTP** và tạo phiên. Đây có thể là MFA hợp lệ theo chính sách, nhưng cả hai giá trị đều có thể bị lừa nhập vào trang phishing và chuyển tiếp gần như ngay lập tức. Nếu hệ thống nhận một **WebAuthn assertion** hợp lệ, việc kiểm tra chữ ký, challenge, origin và RP ID tạo ra những ràng buộc khác, giúp chống phishing và replay tốt hơn. Tuy nhiên, mức AAL chính xác vẫn phụ thuộc cấu hình authenticator và **toàn bộ flow**.

## 3. Đừng nhầm AAL với IAL, FAL hay quyền truy cập

Các chữ viết tắt gần nhau nhưng trả lời những câu hỏi khác nhau:

| Khái niệm | Câu hỏi trung tâm | Ví dụ về điều nó mô tả |
| --- | --- | --- |
| **IAL — Identity Assurance Level** | Có độ tin cậy nào về danh tính và thuộc tính thực của chủ thể? | Identity proofing, giấy tờ, xác minh thuộc tính |
| **AAL — Authentication Assurance Level** | Phiên xác thực vừa qua chứng minh việc kiểm soát authenticator đáng tin tới đâu? | Mật khẩu, MFA, WebAuthn, khóa phần cứng và giao thức liên quan |
| **FAL — Federation Assurance Level** | Assertion danh tính được truyền giữa IdP và relying party an toàn tới đâu? | Bảo đảm liên quan đến liên kết và truyền thông tin xác thực trong federation |
| **Authorization** | Chủ thể đã xác thực được phép thực hiện thao tác nào? | Được đọc hồ sơ của mình nhưng không được cấp quyền quản trị |

Một tài khoản có thể có hồ sơ danh tính được kiểm chứng kỹ nhưng chỉ dùng mật khẩu để đăng nhập. Ngược lại, tài khoản ẩn danh có thể dùng khóa phần cứng chống phishing rất tốt nhưng chưa từng cung cấp tên pháp lý. Hai trường hợp không mâu thuẫn: **IAL và AAL là hai chiều khác nhau**.

Một user đã xác thực ở mức mạnh cũng không mặc nhiên có quyền vào mọi API. Authorization vẫn phải kiểm tra principal, tài nguyên, hành động và chính sách tại resource server.

Trong liên kết danh tính (federation), bên sử dụng phải xác minh issuer, audience, chữ ký, thời hạn và các điều kiện của assertion/token; không được coi một ID token hợp lệ là bằng chứng rằng tất cả yêu cầu AAL hoặc IAL của ứng dụng đã được đáp ứng.

## 4. AAL1, AAL2 và AAL3: hiểu đúng phạm vi

NIST SP 800-63B sử dụng các mức **AAL1, AAL2, AAL3** để mô tả mức đảm bảo xác thực. Các chi tiết bắt buộc về loại authenticator, yếu tố, bảo vệ kênh, thời gian tái xác thực và quản lý vòng đời **phụ thuộc vào phiên bản tiêu chuẩn áp dụng**. Bảng sau cung cấp định hướng khái niệm để học, không thay thế bảng yêu cầu chính thức của phiên bản đang được tổ chức tuân thủ.

| Mức | Định hướng đảm bảo | Kiểu kiểm chứng phù hợp về nguyên tắc | Điều cần tránh hiểu nhầm |
| --- | --- | --- | --- |
| **AAL1** | Có cơ sở xác nhận chủ thể đang kiểm soát một authenticator đã được liên kết | Có thể sử dụng một yếu tố với các kiểm soát theo tiêu chuẩn, ví dụ mật khẩu được xử lý đúng | AAL1 không đồng nghĩa “bảo mật tuyệt đối” hoặc chống phishing |
| **AAL2** | Tăng độ chắc chắn bằng **nhiều yếu tố** theo quy tắc phù hợp; có các yêu cầu bảo vệ bổ sung | Hai yếu tố thuộc nhóm khác nhau hoặc authenticator đa yếu tố đáp ứng yêu cầu | Hai mã cùng gửi vào một hộp thư không tự động tạo MFA đúng nghĩa; AAL2 không bảo đảm mọi phương thức đều chống phishing |
| **AAL3** | Mức bảo đảm cao nhất trong mô hình AAL với yêu cầu mạnh về mật mã, chống phishing và khóa được bảo vệ bằng phần cứng, cùng các yêu cầu khác | Authenticator mật mã phần cứng đáp ứng tiêu chí, sử dụng nhiều yếu tố và ceremony phù hợp | Không phải mọi passkey, thiết bị có sinh trắc hoặc certificate đều tự động đạt AAL3 |

**Ở AAL2**, việc xác thực phải đáp ứng yêu cầu đa yếu tố phù hợp; các loại authenticator được cho phép và yêu cầu chống phishing phải được kiểm tra theo phiên bản chuẩn dùng thực tế. Các bản hướng dẫn hiện đại thúc đẩy khả năng dùng phương thức chống phishing vì mã OTP có thể bị chuyển tiếp bởi phishing proxy.

**Ở AAL3**, chỉ dùng “mật khẩu + OTP”, thêm bước xác nhận email, hoặc kết hợp hai cơ chế kém bảo vệ không đủ để suy ra mức cao nhất. Yêu cầu về authenticator mật mã bảo vệ khóa, tính chống phishing và nhiều yếu tố là trọng tâm; còn có các yêu cầu chi tiết về xác minh, thiết bị, thiết lập phiên và vòng đời.

### 4.1. Vì sao AAL không được suy chỉ từ tên phương thức?

Ví dụ, từ “passkey” chưa cho biết:

- Khóa có nằm trong phần cứng và có thể xuất/đồng bộ ra nơi khác hay không.
- Authenticator có được dùng với user verification phù hợp trong lần này hay không.
- Relying party đã xác minh đúng challenge, RP ID, origin và chữ ký hay chưa.
- Credential đã được đăng ký/gắn đúng tài khoản bằng một flow đáng tin chưa.
- Thiết bị, recovery và yếu tố bổ sung có đáp ứng chính sách của mức mục tiêu không.

**Passkey đồng bộ** (*syncable passkey*) và **passkey gắn thiết bị** (*device-bound passkey*) có đặc tính quản lý khóa khác nhau. Cả hai có thể hỗ trợ chống phishing qua WebAuthn nếu triển khai đúng; nhưng một thiết kế cần khóa riêng không thể xuất/đồng bộ và có bảo vệ phần cứng chặt chẽ phải kiểm tra yêu cầu đó cụ thể, thay vì mặc định mọi passkey đều phù hợp.

Tương tự, từ “chứng chỉ” không chỉ ra việc private key có được giữ trong phần cứng, chứng chỉ có đúng chủ thể/đúng phạm vi, hoặc người dùng có thực hiện thêm yếu tố nào không.

## 5. Các thuộc tính kỹ thuật tạo nên assurance

### 5.1. Loại yếu tố và tính độc lập

Ba nhóm yếu tố xác thực phổ biến:

- **Something you know** — điều người dùng biết, như mật khẩu/PIN.
- **Something you have** — điều người dùng kiểm soát hoặc sở hữu, như thiết bị giữ private key, token mật mã.
- **Something you are** — đặc điểm sinh trắc trong một quy trình xác minh phù hợp, như vân tay/khuôn mặt dùng để kích hoạt authenticator.

**Hai bước không nhất thiết là hai yếu tố.** Ví dụ nhập mật khẩu rồi trả lời một câu hỏi bí mật vẫn chủ yếu dựa vào thông tin người dùng biết; gửi hai OTP tới cùng một kênh không tạo tính độc lập như kỳ vọng. Một **authenticator đa yếu tố** có thể kết hợp yếu tố sở hữu thiết bị với user verification trên thiết bị và trả về bằng chứng mật mã cho relying party.

Sinh trắc có giới hạn về sai số, khả năng bị giả và khả năng thay thế sau khi lộ. Trong nhiều mô hình, sinh trắc chỉ nên được dùng như bước **kích hoạt authenticator được bảo vệ**, không coi một ảnh khuôn mặt tự gửi từ trình duyệt là chứng minh đủ để tạo phiên.

### 5.2. Khả năng bảo vệ bí mật hoặc khóa

| Cách lưu giữ/kiểm soát | Lợi ích có thể có | Rủi ro và điều cần xem |
| --- | --- | --- |
| Mật khẩu trong trí nhớ, hash phía server | Dễ triển khai rộng; có thể bảo vệ bằng kiểm tra mật khẩu tốt | Phishing, reuse, credential stuffing, offline cracking khi hash lộ |
| Seed TOTP trong authenticator | Có mã thay đổi theo thời gian | Seed có thể bị sao chép; OTP vẫn có thể bị chuyển tiếp |
| Khóa riêng bảo vệ bởi hệ điều hành hoặc kho khóa thiết bị | Hạn chế truy xuất khóa trong nhiều cấu hình | Phụ thuộc chính sách xuất khóa, sao lưu, bảo vệ thiết bị và môi trường |
| Khóa phần cứng với cơ chế không xuất private key | Giảm nguy cơ trích xuất bí mật; hỗ trợ proof of possession | Cần kiểm tra credential, attestation khi áp dụng, vòng đời và tình huống mất thiết bị |
| Khóa đồng bộ giữa các thiết bị | Cải thiện khả năng sử dụng và khôi phục | Mức bảo đảm phụ thuộc cơ chế bảo vệ tài khoản đồng bộ và yêu cầu tương ứng |

**Đã mã hóa khóa** không đồng nghĩa **khóa không thể xuất**. Muốn đánh giá assurance, cần biết khóa có thể bị sao chép/đồng bộ hay không, ai kiểm soát kênh đồng bộ, và phần cứng/ứng dụng bảo vệ thế nào.

### 5.3. Chống phishing (*phishing resistance*)

Một authenticator chống phishing phải có cơ chế khiến bằng chứng xác thực dành cho **bên nhận hợp lệ** khó có thể bị lấy và dùng ngay cho bên nhận giả mạo. WebAuthn/FIDO2 sử dụng khóa công khai gắn với relying party và quy trình kiểm tra **RP ID, origin, challenge, chữ ký**. Người dùng bị dẫn tới trang có origin khác không thể tạo một assertion hợp lệ cho RP ID của trang thật chỉ bằng cách gõ một mã.

Mã OTP qua SMS hoặc ứng dụng TOTP không có cùng ràng buộc origin; trang giả có thể lừa người dùng nhập mã và chuyển tiếp tới trang thật. Push approval thiếu ngữ cảnh cũng có thể bị lợi dụng qua **MFA fatigue**. Number matching và thông báo rõ hành động hỗ trợ giảm rủi ro phê duyệt nhầm nhưng không tự biến push/OTP thành cơ chế chống phishing tương đương WebAuthn.

### 5.4. Chống replay

**Replay resistance** là khả năng ngăn đối thủ dùng lại bằng chứng đã quan sát để xác thực lần khác. Các cơ chế có thể gồm:

- Challenge/nonce ngẫu nhiên, khó đoán, có hạn và gắn với giao dịch.
- Kiểm tra chữ ký trên dữ liệu chứa challenge hiện tại.
- Code/OTP được xử lý đúng cửa sổ thời gian và quy tắc chống sử dụng lại.
- Ràng buộc token/credential với client hoặc khóa sở hữu khi giao thức hỗ trợ.
- Giới hạn số lần thử, số lần gửi lại, phát hiện bất thường và thu hồi phiên.

**OTP thay đổi mỗi 30 giây không tự bảo đảm chống replay** nếu server chấp nhận cùng giá trị nhiều lần trong cửa sổ đó. Hệ thống phải áp dụng chính sách sử dụng một lần hoặc kiểm soát tương ứng. Challenge cũng phải được tiêu thụ/giới hạn theo giao thức chứ không chỉ được tạo một lần.

### 5.5. Xác minh đúng bên nhận và đúng giao thức

Một bằng chứng được kiểm tra đúng phải có ngữ cảnh: ai phát hành, cho relying party nào, dùng để làm gì và còn hợp lệ bao lâu. Với WebAuthn, kiểm tra chữ ký mà bỏ qua origin hoặc RP ID là thiếu ranh giới tin cậy. Với OIDC, decode được payload JWT không đồng nghĩa đã xác minh issuer, audience, signature, nonce và thời hạn theo flow.

Đầu ra cuối cùng phải là **kết quả xác thực có cơ sở**, không chỉ là một chuỗi dữ liệu có vẻ đúng định dạng.

## 6. Bảng so sánh các authenticator phổ biến

Bảng dưới đây phục vụ **so sánh thuộc tính kỹ thuật**, không phải bảng tự động gán AAL cho sản phẩm. AAL còn phụ thuộc tổ hợp phương thức, enrollment, cấu hình, policy và phiên bản tiêu chuẩn.

| Cơ chế | Bằng chứng bên xác minh nhận | Chống phishing theo cơ chế mặc định? | Rủi ro chính / điều kiện kiểm tra |
| --- | --- | --- | --- |
| **Mật khẩu** | Bí mật khớp với verifier | Không | Đoán/nhồi credential, phishing, reuse; cần hash mạnh, rate limit và kiểm tra mật khẩu yếu/lộ |
| **HOTP/TOTP** | Mã sinh từ shared secret và counter/thời gian | Không | Phishing proxy, lộ seed, relay và replay trong cửa sổ; chống brute force |
| **SMS/voice OTP** | Mã gửi qua kênh điện thoại | Không | SIM swap, chuyển số, SS7/đánh cắp kênh, relay; có thể bị hạn chế theo chuẩn/chính sách |
| **Push approval** | Phản hồi duyệt trên thiết bị đăng ký | Không mặc nhiên | MFA fatigue, duyệt nhầm, thiết bị bị chiếm; ngữ cảnh hành động và chống spam |
| **WebAuthn/passkey** | Chữ ký trên challenge và dữ liệu ràng buộc RP | Có, khi triển khai WebAuthn đúng | Phải xác minh origin, RP ID, challenge, UV/UP theo yêu cầu; tính exportable của khóa quyết định một số thuộc tính assurance |
| **Security key phần cứng** | Bằng chứng mật mã từ khóa thiết bị | Có nếu giao thức và cấu hình hỗ trợ ràng buộc RP | Kiểm tra key protection, attestation nếu yêu cầu, user verification, enrollment và recovery |
| **Chứng chỉ client / mTLS** | Proof of possession khóa riêng trong TLS, gắn với chứng chỉ | Có thể chống relay theo cơ chế được thiết kế đúng | PKI, chain, SAN/subject, revocation, EKU, khóa có xuất được không, user presence/factor |
| **Sinh trắc thiết bị** | Kết quả xác minh cục bộ dùng kích hoạt authenticator | Không khi đứng một mình | Cần chống giả mạo và ràng buộc với chứng cứ mật mã; ảnh/giọng gửi cho server không đồng nghĩa private key proof |

### 6.1. Mật khẩu + TOTP và passkey khác nhau ở đâu?

Giả sử website yêu cầu mật khẩu và TOTP. Kẻ tấn công kiểm soát trang giả có thể chuyển tiếp cả hai bí mật tới website thật trong thời gian ngắn. MFA vẫn làm tăng khó khăn cho đối thủ so với chỉ mật khẩu, nhưng **không loại bỏ phishing relay**.

Trong WebAuthn, authenticator tạo chữ ký cho challenge tương ứng relying party thực và origin được kiểm tra. Trang phishing ở origin khác không có khả năng làm cho assertion trở thành bằng chứng đúng cho relying party thật theo giao thức chuẩn, kể cả khi người dùng nhầm trang. Đây là lý do **phishing resistance** phải được xem như một thuộc tính kỹ thuật riêng bên cạnh “bao nhiêu yếu tố”.

### 6.2. Một passkey có thể là MFA không?

Có thể, tùy ceremony và yêu cầu. Khi thiết bị giữ private key (yếu tố sở hữu/kiểm soát) và yêu cầu **user verification** như PIN hoặc sinh trắc cục bộ, authenticator có thể đáp ứng mô hình nhiều yếu tố theo chính sách. Phía server phải kiểm tra các cờ và bảo đảm theo WebAuthn; không được suy từ việc trình duyệt hiển thị màn hình vân tay.

Nếu một phương thức chỉ kiểm tra **user presence** — có thao tác chạm/nhấn nhưng không xác minh người dùng cụ thể — thì chưa thể tự coi đó là cùng bằng chứng với **user verification**. Hai khái niệm này phục vụ mục đích khác nhau.

## 7. Từ credential enrollment đến authentication event

Một lần xác thực có assurance tốt chỉ khi credential được **gắn đúng chủ thể**. Nếu kẻ tấn công đăng ký khóa riêng của mình vào tài khoản nạn nhân qua đường recovery yếu, một chữ ký WebAuthn hợp lệ ở những lần sau vẫn có thể dẫn tới chiếm tài khoản.

~~~mermaid
flowchart TD
    A[Thiết lập identity/account] --> B[Enrollment: gắn authenticator với principal]
    B --> C[Kiểm soát bảo vệ và vòng đời credential]
    C --> D[Authentication ceremony]
    D --> E{Bằng chứng hợp lệ và gắn đúng bên nhận?}
    E -- Không --> R[Từ chối hoặc challenge lại]
    E -- Có --> F[Kiểm tra yếu tố, thuộc tính phương thức và chính sách]
    F --> G{Đủ assurance cho yêu cầu hiện tại?}
    G -- Chưa --> H[Step-up hoặc dùng phương thức mạnh hơn]
    H --> D
    G -- Đủ --> I[Tạo authentication context phía server]
    I --> J[Session hoặc assertion/token cho bên nhận hợp lệ]
    J --> K[Authorization cho từng thao tác]
~~~

### 7.1. Enrollment phải đáng tin

Khi đăng ký mật khẩu, khóa mới hoặc authenticator bổ sung, cần:

1. Xác định tài khoản/principal đích từ ngữ cảnh được xác thực và tin cậy.
2. Yêu cầu xác thực lại phù hợp trước thay đổi nhạy cảm.
3. Kiểm tra đúng giao thức đăng ký (ví dụ challenge, RP ID, origin, credential public key ở WebAuthn).
4. Ngăn thêm credential trái phép qua một phiên bị đánh cắp; cân nhắc thông báo kênh cũ và thời gian trì hoãn đối với thay đổi đặc biệt nguy hiểm.
5. Ghi audit sự kiện, hỗ trợ kiểm tra/thu hồi authenticator không còn thuộc quyền kiểm soát.

Một lỗ hổng trong bước enrollment có thể hạ assurance thực tế của cả hệ thống xuống dưới mức được quảng bá.

### 7.2. Recovery cũng nằm trong assurance

**Khôi phục tài khoản** là điểm tấn công thường gặp. Nếu một tài khoản yêu cầu thiết bị phần cứng nhưng có thể đặt lại mọi authenticator chỉ bằng một email yếu, đối thủ có thể bỏ qua cơ chế xác thực mạnh qua đường recovery.

Thiết kế cần:

- Phân loại cách khôi phục được cho phép theo mức rủi ro/tài khoản.
- Kiểm tra quyền kiểm soát kênh phục hồi và trạng thái phiên trước đó.
- Giới hạn thử, chống replay của recovery code/link và ngăn enumeration.
- Yêu cầu nhiều kiểm tra hoặc manual review khi rủi ro cao.
- Thông báo thay đổi, quản lý thời gian trì hoãn, thu hồi/luân chuyển token và session khi thích hợp.
- Xem xét lại mức bảo đảm của phiên **sau** khôi phục, không kế thừa AAL cao của một credential đã mất.

Đường phục hồi có thể là một quy trình bảo mật riêng. Không được mặc định “vừa vượt qua email reset” tương đương “vừa thực hiện xác thực phishing-resistant bằng phần cứng”.

## 8. Bảo đảm của phiên không tồn tại mãi mãi

Khi user vượt qua authenticator, server thường tạo **authentication context** và một cách duy trì phiên: cookie session hoặc assertion/token cho client. Các yêu cầu kế tiếp không lặp lại toàn bộ ceremony; chúng dựa trên trạng thái đã tạo, thời hạn và điều kiện tin cậy.

Một authentication context hữu ích có thể chứa:

| Thuộc tính | Ý nghĩa | Vì sao quan trọng |
| --- | --- | --- |
| Principal / subject | Tài khoản đã xác thực | Không dùng email hoặc tên hiển thị làm khóa bảo mật |
| Authentication time | Lần xác thực đáng tin diễn ra lúc nào | Hỗ trợ reauthentication theo tính mới (*freshness*) |
| Verified methods | Những phương thức **thật sự đã hoàn thành** | Không tin mảng phương thức do client tự gửi |
| Assurance context/profile | Chính sách đảm bảo nào thực sự được thỏa | Giúp policy engine quyết định cần step-up không |
| Phishing-resistant flag / property | Ceremony có đáp ứng yêu cầu chống phishing hay không | Cần bằng chứng giao thức và chính sách, không gắn tùy ý |
| Session ID / token lifetime | Phiên còn hiệu lực trong phạm vi nào | Hỗ trợ hết hạn, thu hồi, rotation |
| Issuer / audience khi federation | Bên nào xác nhận, bên nào được phép dùng | Ngăn tin nhầm token và nhầm tenant/issuer |

**Mức bảo đảm không phải một nhãn vĩnh viễn trên tài khoản.** Người dùng có thể có hai authenticator, một phiên đăng nhập bằng mật khẩu và một phiên bằng passkey. Hai phiên có ngữ cảnh xác thực khác nhau. Thao tác thay đổi dữ liệu nhạy cảm có thể yêu cầu lần xác thực đủ mạnh và đủ gần, cho dù phiên vẫn còn đăng nhập.

### 8.1. Reauthentication và step-up

- **Reauthentication:** yêu cầu người dùng xác thực lại khi thời gian hoặc rủi ro vượt ngưỡng cho phép.
- **Step-up:** yêu cầu cơ chế xác thực đáp ứng mức bảo đảm cao hơn trước thao tác cụ thể.
- **Session renewal/rotation:** thay mã phiên hoặc giới hạn lại thời hạn theo chính sách sau sự kiện quan trọng.
- **Session revocation:** thu hồi trạng thái đăng nhập khi phát hiện rủi ro, đổi credential, đăng xuất hoặc phục hồi tài khoản.

Nên chọn ngưỡng dựa trên phiên bản chuẩn và mức rủi ro hệ thống. Không nên viết một TTL “chuẩn” cố định áp dụng cho mọi AAL mà không xem yêu cầu cụ thể của chuẩn và sản phẩm.

Ví dụ ma trận yêu cầu minh họa:

| Hoạt động | Điều kiện xác thực có thể yêu cầu | Chính sách bổ sung |
| --- | --- | --- |
| Đọc tin tức công khai | Không cần xác thực | Rate limit nếu chống abuse |
| Xem hồ sơ cá nhân | Phiên hợp lệ theo mức cơ bản | Kiểm tra chủ thể, resource ownership |
| Đổi email khôi phục | Xác thực gần đây và phương thức đủ mạnh | Thông báo kênh cũ, chống takeover |
| Thêm passkey hoặc khóa phần cứng | Reauthentication thích hợp | Ghi audit, kiểm tra credential đăng ký |
| Chuyển tiền/đổi thông tin thanh toán | Step-up đủ mức theo chính sách nghiệp vụ | Xác minh ràng buộc giao dịch, hạn mức, kiểm tra gian lận |
| Truy cập hệ thống đặc quyền | Authenticator và phiên đáp ứng yêu cầu cao | Least privilege, giới hạn thời gian, giám sát |

Đây là **ví dụ chính sách**, không phải bảng quy định chung rằng hành động nào luôn bắt buộc AAL nhất định.

## 9. Trust boundary: ai được phép gán AAL?

Một lỗi thường gặp là để frontend quyết định rằng người dùng đã xác thực đủ mạnh. Trình duyệt có thể bị can thiệp, cookie có thể bị đánh cắp và các claim có thể bị giả nếu không xác minh.

~~~mermaid
flowchart LR
    A[Browser/Client] -->|Credential hoặc assertion| B[Auth Server / IdP]
    B -->|Kiểm chứng giao thức và policy| C[Trusted authentication context]
    C -->|Session hoặc token/ID assertion| D[Application / RP]
    D -->|Access token phù hợp| E[Resource Server / API]
    E --> F[Authorization quyết định theo tài nguyên]
~~~

Các ranh giới quan trọng:

1. **Client → Auth server:** server kiểm tra credential và trạng thái flow. Trường do client tự gửi như “MFA passed”, “AAL3”, “hardware key used” không phải bằng chứng.
2. **Authenticator → verifier:** verifier kiểm tra chữ ký/challenge hoặc mã theo giao thức; bảo vệ chống replay, phishing, rủi ro lạm dụng và ràng buộc authenticator với tài khoản.
3. **IdP → relying party:** OIDC/SAML assertion cần được xác minh theo issuer, audience, signature, expiry, nonce hoặc các ràng buộc tương đương tùy flow. RP phải tin **chính sách assurance của IdP**, không chỉ tin token được ký hợp lệ.
4. **Client → API:** API xác minh access token đúng đối tượng nhận, thời hạn, chữ ký/introspection và quyền. **ID token không phải access token cho API.**
5. **Session → thao tác:** server quyết định session còn hiệu lực và ngữ cảnh xác thực có đủ cho thao tác hiện tại không; không lấy trạng thái UI làm nguồn sự thật.

### 9.1. OIDC: amr, acr và auth_time

Các claim OIDC giúp diễn đạt một phần bối cảnh:

- **amr** (*Authentication Methods References*): cho biết phương thức được IdP báo đã dùng, theo tập giá trị và cách hiểu của IdP/giao thức.
- **acr** (*Authentication Context Class Reference*): tham chiếu tới một lớp/ngữ cảnh đảm bảo xác thực đã được IdP thực hiện.
- **auth_time**: thời điểm xác thực thực tế, hữu ích khi ứng dụng yêu cầu người dùng xác thực gần đây.
- **iss, sub, aud, exp, iat, nonce** (khi áp dụng): giúp xác minh bên phát hành, subject, đối tượng nhận, thời hạn và ràng buộc giao dịch.

Ví dụ minh họa **payload sau khi decode**, chưa phải token có chữ ký đã kiểm chứng:

~~~json
{
  "iss": "https://login.example.test",
  "sub": "user_7c14",
  "aud": "backoffice-client",
  "iat": 1795320000,
  "exp": 1795320300,
  "auth_time": 1795319900,
  "amr": ["hwk", "pin"],
  "acr": "urn:example:authn:strong-phishing-resistant",
  "nonce": "random-request-bound-value"
}
~~~

Giá trị **acr** trong ví dụ là tên lớp do hệ thống giả định, **không phải** nhãn AAL được chuẩn hóa toàn cầu. Một RP chỉ có thể diễn giải acr theo **hợp đồng đã thống nhất với IdP**. Việc amr chứa “hwk” hoặc “pin” không tự chứng minh AAL3; RP vẫn phải biết IdP bảo vệ khóa, kiểm chứng người dùng và quản lý phiên/recovery như thế nào.

Không được suy kết luận assurance từ việc **decode JSON** hoặc nhìn tên claim. Phải xác minh token và đúng issuer/khóa/thuật toán/audience, đồng thời ràng buộc với giao dịch và chính sách đã thỏa thuận.

## 10. Mô hình kỹ thuật: đưa assurance vào quyết định chính sách

Một cách làm có thể kiểm thử là tách **sự kiện đã xác minh** khỏi **chính sách yêu cầu cho hành động**. Kiểu dữ liệu TypeScript dưới đây chỉ là ví dụ tư duy thiết kế, không phải thư viện triển khai tiêu chuẩn:

~~~ts
type AssuranceProfileId = "baseline" | "mfa-approved" | "phishing-resistant";

type VerifiedAuthenticationContext = {
  principalId: string;
  sessionId: string;
  authenticatedAt: string;     // ISO 8601, server kiểm soát
  verifiedMethods: string[];   // Từ verifier/IdP đáng tin, không từ client
  assuranceProfile: AssuranceProfileId;
  phishingResistant: boolean;  // Kết quả policy engine kiểm chứng
  enrollmentPolicyVersion: string;
};

type ActionRequirement = {
  minProfile: AssuranceProfileId;
  requirePhishingResistance: boolean;
  maxAuthenticationAgeSeconds?: number;
};

type Decision =
  | { kind: "allow"; authorizationStillRequired: true }
  | { kind: "step_up"; reason: "assurance" | "freshness" | "phishing-resistance" }
  | { kind: "deny"; reason: "invalid-session" | "risk-policy" };
~~~

Các profile **baseline**, **mfa-approved** và **phishing-resistant** là tên nội bộ của ví dụ; không tự tương đương AAL1/AAL2/AAL3. Nếu cần tuyên bố tuân thủ AAL, tổ chức phải có **ma trận phương thức, chính sách, kiểm chứng và hồ sơ chứng minh** tương ứng phiên bản NIST áp dụng. Trong mã thật, tuyệt đối không so sánh thứ hạng assurance bằng cách sắp xếp chữ cái của chuỗi tên profile.

Pseudocode phía server:

~~~text
function decideSensitiveAction(request, actionPolicy):
    session = verifySessionCookieOrToken(request)
    if session.invalidOrRevoked:
        return DENY_INVALID_SESSION

    authContext = loadServerVerifiedAuthContext(session)
    if authContext.missing:
        return STEP_UP_ASSURANCE

    if not policyEngine.meetsRequiredProfile(authContext, actionPolicy):
        return STEP_UP_ASSURANCE

    if actionPolicy.requirePhishingResistance
       and not authContext.phishingResistant:
        return STEP_UP_PHISHING_RESISTANCE

    if not policyEngine.isAuthenticationFresh(authContext, actionPolicy):
        return STEP_UP_FRESHNESS

    if riskEngine.requiresAdditionalControls(request, session):
        return RESTRICT_OR_STEP_UP

    return authorizePrincipalForAction(authContext.principalId, request.resource)
~~~

**Không** để trình duyệt tự gán assuranceProfile; backend phải suy ra từ **ceremony đã xác minh** hoặc assertion từ IdP tin cậy. Khi step-up hoàn tất, cần cập nhật ngữ cảnh xác thực phía server và quản lý session rotation/phạm vi phiên theo chính sách.

### 10.1. Lưu ý bảo vệ token và session

Một access token là **vật mang quyền truy cập** tới API; việc nó là JWT đã ký không đảm bảo token chống phishing hay proof-of-possession. Với **bearer token**, ai sở hữu token có thể sử dụng token trong phạm vi và thời gian hợp lệ. Có thể giảm rủi ro bằng TTL ngắn, hạn chế scope/audience, bảo vệ lưu trữ, thu hồi và các cơ chế ràng buộc người giữ khóa như DPoP/mTLS khi thích hợp.

Cookie session nên có **Secure**, **HttpOnly** và **SameSite** phù hợp, kết hợp chống CSRF, XSS, session fixation và session hijacking; đổi mã phiên khi nâng mức xác thực nếu thiết kế yêu cầu. Assurance của sự kiện xác thực **không thay thế** kiểm soát quản lý phiên.

## 11. Ví dụ: thiết kế một flow với assurance theo thao tác

Giả sử ứng dụng quản lý tài khoản cho phép người dùng xem dữ liệu cơ bản nhưng yêu cầu xác thực mạnh khi thay đổi phương thức khôi phục.

**Luồng A — đăng nhập bằng mật khẩu:**

1. Người dùng nhập tên đăng nhập và mật khẩu.
2. Server kiểm tra bí mật đúng cách và đánh giá rate limiting/credential stuffing.
3. Ứng dụng chỉ cấp mức phù hợp cho những thao tác cho phép một yếu tố; không tự đánh dấu là “MFA completed”.
4. Khi người dùng muốn thay đổi email khôi phục, backend trả về yêu cầu step-up.
5. Người dùng thực hiện authenticator bổ sung được phê duyệt; server xác minh rồi mới xử lý yêu cầu.

**Luồng B — đăng nhập bằng passkey:**

1. Server tạo challenge ngẫu nhiên và duy trì trạng thái flow gắn với relying party.
2. Browser/authenticator thực hiện WebAuthn ceremony.
3. Server xác minh credential public key đã đăng ký, challenge, origin, RP ID, chữ ký, cờ UP/UV cần thiết và các tín hiệu khác theo chính sách.
4. Policy engine đánh giá đặc tính của authenticator, user verification và ràng buộc đã xác minh; không dựa đơn thuần vào chữ “passkey”.
5. Nếu phiên thỏa yêu cầu assurance và freshness của thao tác, backend tiếp tục kiểm tra **authorization**.

**Luồng C — recovery sau khi mất thiết bị:**

1. Người dùng chứng minh quyền kiểm soát các phương thức phục hồi được quy định.
2. Hệ thống đánh giá rủi ro, chống lạm dụng, yêu cầu thêm bằng chứng/review khi cần.
3. Credential mới được gắn với đúng principal qua flow an toàn; các credential hoặc session bị nghi bị xâm nhập được xử lý.
4. Phiên mới chỉ mang **mức bảo đảm thực tế** của lần xác thực và recovery vừa hoàn tất, không kế thừa vô điều kiện mức assurance trước đó.

| Tình huống | Kết luận chính xác | Phản ứng |
| --- | --- | --- |
| Mật khẩu đúng, thiếu MFA bắt buộc | Chưa đủ assurance cho đăng nhập mục tiêu | Challenge tiếp, không cấp phiên đầy đủ |
| OTP đúng nhưng bị phishing proxy chuyển tiếp | Có thể vượt một lớp MFA không chống phishing | Ưu tiên chuyển sang cơ chế chống phishing và đánh giá bất thường |
| WebAuthn assertion đúng nhưng không kiểm tra origin | Chưa đủ xác minh theo giao thức | Không tin sự kiện; sửa verifier |
| Passkey đồng bộ hoạt động đúng | Có bảo đảm WebAuthn theo cấu hình | Đánh giá chính sách khóa/UV/backup trước khi gán mức |
| Khóa phần cứng được xác minh nhưng session đã cũ | Assurance khi xác thực có thể mạnh, freshness không đủ | Reauthentication hoặc step-up |
| ID token hợp lệ nhưng RP không có hợp đồng về acr | Chưa đủ cơ sở suy ra AAL | Yêu cầu diễn giải đáng tin hoặc dùng flow riêng |
| Đăng nhập thành công nhưng thiếu quyền tài nguyên | Authenticated không đồng nghĩa authorized | Trả lỗi quyền hoặc xử lý theo API policy |

## 12. Threat model: những cách assurance bị nâng khống

| Kiểu lỗi/tấn công | Diễn biến | Kiểm soát phù hợp |
| --- | --- | --- |
| **Phishing và credential relay** | Kẻ xấu thu mật khẩu/OTP và chuyển tiếp phiên đăng nhập | Phương thức chống phishing như WebAuthn, ràng buộc origin/RP, phát hiện lạm dụng |
| **Replay** | Một OTP hoặc signed response bị gửi lại | Challenge duy nhất, thời hạn, one-time acceptance khi cần, signature verification |
| **MFA fatigue** | Liên tục gửi push để nạn nhân nhấn đồng ý | Giới hạn yêu cầu, number matching/ngữ cảnh, cảnh báo, khóa tạm và hỗ trợ người dùng |
| **Credential stuffing** | Tái sử dụng mật khẩu lộ từ nơi khác | Rate limiting đa tín hiệu, mật khẩu mạnh, phát hiện password breach, MFA phù hợp |
| **Enrollment takeover** | Đối thủ dùng session đánh cắp để thêm authenticator của mình | Reauthentication, step-up, thông báo và audit đăng ký credential |
| **Recovery bypass** | Reset yếu thay thế phương thức xác thực mạnh | Chính sách phục hồi tương xứng, chống enumeration và review trường hợp rủi ro |
| **Key extraction/copy** | Khóa riêng bị sao chép hoặc sync tới tài khoản bị chiếm | Bảo vệ phần cứng/không xuất khi yêu cầu; kiểm soát thiết bị và đồng bộ |
| **Session hijacking** | Cookie/access token bị lấy cắp sau xác thực mạnh | Secure session, TTL, rotation, revoke, risk-based reauthentication |
| **Token confusion** | API dùng ID token hoặc token sai audience | Xác minh issuer/audience/scope/type, từ chối token sai mục đích |
| **AAL claim spoofing** | Frontend gửi giá trị “aal=3”, RP tin amr/acr không kiểm tra | Chỉ dựa vào verifier hoặc IdP đáng tin; hợp đồng acr và evidence kiểm toán |
| **Downgrade/fallback** | Flow tự hạ xuống mật khẩu/email sau khi authenticator mạnh gặp lỗi | Policy fallback rõ ràng, hạn chế phạm vi/quyền, recovery tương xứng |

Các biện pháp về assurance cần kiểm thử ở **nhánh lỗi và đường dự phòng**, không chỉ ở flow đăng nhập thành công. Bảo mật thực tế thường bị quyết định bởi đường đi mà kẻ tấn công thấy dễ nhất.

## 13. Kiểm thử và bằng chứng vận hành

Đội phát triển nên kiểm tra **những gì verifier và policy engine thực sự thực thi** thay vì dựa vào cấu hình đã khai báo.

### 13.1. Những ca kiểm thử tối thiểu

1. **Sai challenge:** một response WebAuthn được tạo cho challenge khác hoặc đã hết hạn phải bị từ chối.
2. **Sai RP/origin:** assertion có origin không hợp lệ không được chấp nhận dù chữ ký có vẻ đúng.
3. **Thiếu user verification:** nếu chính sách yêu cầu UV, response không có bằng chứng UV phù hợp phải bị từ chối hoặc yêu cầu thử lại.
4. **OTP bị dùng lại:** một OTP đã chấp nhận không được dùng lặp sai quy tắc giao thức.
5. **Thử nhiều lần:** brute force mật khẩu, OTP và recovery phải gặp giới hạn và giám sát phù hợp.
6. **Token sai audience:** API không được chấp nhận token cấp cho client/resource khác.
7. **Session hết freshness:** yêu cầu thay email khi xác thực quá cũ phải dẫn tới reauthentication.
8. **Enrollment từ session cũ/bị lấy cắp:** việc thêm authenticator phải tuân thủ yêu cầu step-up.
9. **Recovery không đủ bằng chứng:** không được mặc nhiên cấp lại mức assurance cao đã mất.
10. **Client giả claim AAL cao:** mọi giá trị do client tự gán phải bị bỏ qua khi policy engine tính mức.
11. **Xâm nhập IdP hoặc đổi issuer:** relying party phải từ chối assertion không đúng issuer/khóa hoặc không theo cấu hình tin cậy.
12. **Sự kiện logout/revoke:** session/token bị thu hồi phải không còn được chấp nhận theo cơ chế và thời điểm thu hồi đã thiết kế.

### 13.2. Logging và audit phù hợp

Nên lưu sự kiện có cấu trúc như: principal nội bộ, phương thức đã kiểm chứng, kết quả/nhánh flow, thời điểm, assurance profile, phiên bản policy, correlation ID, yêu cầu step-up, thay đổi credential và thông báo rủi ro. Không đưa vào log mật khẩu, OTP, private key, raw token, recovery code hoặc bản ghi sinh trắc không cần thiết.

Các số liệu vận hành cần quan sát: tỷ lệ MFA/step-up thành công, số lần fallback/recovery, tỷ lệ khóa nhầm, phishing/credential stuffing, tỷ lệ authenticator chống phishing, thời gian xử lý hỗ trợ, và các trường hợp session không được thu hồi đúng.

## 14. Checklist review authenticator assurance

| Câu hỏi review | Tiêu chí thiết kế đáng tin |
| --- | --- |
| Đang cần mức assurance cho thao tác nào? | Có chính sách theo tài nguyên, rủi ro và yêu cầu nghiệp vụ |
| Mục tiêu AAL dựa trên tiêu chuẩn nào? | Chỉ rõ tên và phiên bản chuẩn, yêu cầu chi tiết và phương pháp đánh giá |
| Authenticator tạo bằng chứng gì? | Giao thức chứng minh quyền kiểm soát bí mật/khóa phù hợp |
| Đã có nhiều yếu tố đúng nghĩa chưa? | Kiểm chứng đúng nhóm yếu tố, không đếm số màn hình/OTP |
| Có chống phishing và replay không? | Origin/RP/challenge và tính mới được kiểm tra nơi có thẩm quyền |
| Khóa có xuất/đồng bộ được không? | Có tài liệu về bảo vệ khóa và cấu hình phù hợp mức cần đạt |
| User presence khác user verification? | Verifier kiểm tra cờ/bằng chứng theo policy, không đoán từ UI |
| Enrollment có thể bị chiếm qua session cũ? | Có step-up và kiểm soát gắn authenticator mới |
| Recovery có hạ assurance không? | Mức sau recovery được đánh giá lại; có kiểm soát phù hợp |
| Nhãn amr/acr do ai phát hành? | IdP/verifier đáng tin, assertion được xác minh và diễn giải theo hợp đồng |
| Session có giữ assurance quá lâu? | Có freshness, TTL, rotation, revoke và step-up |
| API có kiểm tra đúng token? | Xác minh issuer, audience, expiry, signature và authorization |
| Fallback khi authenticator lỗi ra sao? | Có đường thay thế an toàn, có thể tiếp cận và không tự động nâng mức |
| Có bằng chứng kiểm thử và audit? | Test các nhánh phishing/replay/recovery và số liệu vận hành |

### Câu hỏi tự kiểm tra

**1. Người dùng nhập đúng mật khẩu và TOTP. Có thể kết luận đây là phương thức chống phishing không?** Không. Hai yếu tố có thể đáp ứng yêu cầu MFA trong cấu hình phù hợp, nhưng mã TOTP vẫn có thể bị trang giả chuyển tiếp.

**2. Website xác minh chữ ký WebAuthn đúng nhưng không kiểm tra RP ID và origin. Có nên đánh dấu phiên là phishing-resistant?** Không. Ràng buộc relying party là phần thiết yếu của assurance mà giao thức cung cấp.

**3. Một passkey lưu trong đồng bộ đám mây và một security key phần cứng không thể xuất khóa có thể tự nhận cùng AAL3 không?** Không. Cần đánh giá khả năng bảo vệ khóa, user verification, enrollment và yêu cầu chuẩn áp dụng; không gán AAL chỉ từ tên công nghệ.

**4. Người dùng vừa có phiên mạnh nhưng đã đổi credential qua recovery rủi ro cao. Có nên giữ nguyên assurance cũ?** Không mặc nhiên. Recovery và binding có thể làm thay đổi trạng thái tin cậy, cần đánh giá lại phiên và quy tắc thu hồi.

**5. API nhận được access token hợp lệ. Nó có được phép bỏ qua authorization không?** Không. Authentication/assurance và authorization là những quyết định khác nhau.

## 15. Ghi nhớ

**Authenticator assurance** mô tả độ tin cậy của phương thức và bằng chứng xác thực; **AAL** mô tả mức đảm bảo của **toàn bộ lần xác thực** theo một bộ yêu cầu đã định nghĩa. AAL1, AAL2 và AAL3 tăng yêu cầu bảo đảm theo những cơ chế và điều kiện xác minh khác nhau, nhưng mức cụ thể không được suy ra chỉ từ việc có mật khẩu, MFA, passkey hay chứng chỉ.

Muốn thiết kế flow có mức tin cậy phù hợp, hãy xác minh **đúng chủ thể, đúng authenticator, đúng relying party, đúng challenge, đúng yêu cầu yếu tố, đúng thời điểm và đúng vòng đời credential**. Sau đó bảo vệ session/token, kiểm tra quyền tại API, yêu cầu step-up khi cần và giữ đường recovery/fallback tương xứng. Khả năng chống phishing, replay và chiếm phiên phải được thực thi bằng giao thức và chính sách có thể kiểm thử, không chỉ bằng nhãn assurance.
