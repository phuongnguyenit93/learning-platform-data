# Password reuse — Tái sử dụng mật khẩu và rủi ro chiếm tài khoản

## 1. Password reuse là gì?

**Password reuse** (tái sử dụng mật khẩu) là việc dùng cùng một mật khẩu cho nhiều tài khoản hoặc nhiều dịch vụ. Một biến thể thường gặp là người dùng thay đổi một vài ký tự theo mẫu dễ đoán, chẳng hạn dùng cùng một cụm gốc rồi thêm tên dịch vụ hoặc năm hiện tại. Dù chuỗi không hoàn toàn giống nhau, các biến thể có quy luật vẫn có thể bị suy đoán khi một mật khẩu khác đã lộ.

Ví dụ: một người dùng mật khẩu cho diễn đàn cá nhân, hộp thư và cổng nhân sự. Diễn đàn bị xâm nhập, danh sách email/mật khẩu bị rò rỉ. Kẻ tấn công thử chính cặp thông tin đó trên hộp thư và cổng nhân sự. Nếu người dùng tái sử dụng mật khẩu, một sự cố ở dịch vụ ít quan trọng có thể mở đường vào tài khoản có dữ liệu nhạy cảm.

Trong chương **Password authentication** của module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, password reuse là một rủi ro trọng yếu vì nó làm suy yếu ranh giới giữa các tài khoản. Người học cần hiểu cách credential bị lộ ở một nơi có thể bị dùng ở nơi khác, cách hệ thống phát hiện và ngăn credential stuffing, và cách kết hợp mật khẩu duy nhất, MFA, passkey, bảo vệ phiên và khôi phục tài khoản.

### Các dạng tái sử dụng thường gặp

| Dạng | Ví dụ khái niệm | Rủi ro |
| --- | --- | --- |
| **Tái sử dụng chính xác** | Cùng một mật khẩu cho email cá nhân và cổng công ty. | Một lần lộ mật khẩu có thể mở nhiều tài khoản. |
| **Biến thể theo mẫu** | Cùng một cụm gốc, thêm tên website hoặc số năm. | Kẻ tấn công có thể thử các biến thể có quy luật. |
| **Mật khẩu mặc định/chia sẻ** | Nhiều nhân viên dùng chung mật khẩu ban đầu của một thiết bị hoặc dịch vụ. | Không truy vết được cá nhân; một người rời nhóm vẫn có thể biết bí mật. |
| **Dùng lại giữa môi trường** | Cùng mật khẩu cho development, staging và production. | Môi trường bảo vệ yếu hơn có thể trở thành đường vào môi trường quan trọng. |
| **Dùng lại bí mật quản trị** | Cùng một mật khẩu cho nhiều tài khoản quản trị hoặc máy chủ. | Một máy bị xâm nhập có thể dẫn đến leo thang trên nhiều hệ thống. |

**Nguyên tắc:** mỗi tài khoản hoặc dịch vụ có phạm vi tin cậy riêng cần một credential riêng. Khi một nơi bị xâm phạm, bí mật ở nơi khác không nên tự động bị ảnh hưởng.

## 2. Vì sao tái sử dụng mật khẩu nguy hiểm?

Mật khẩu là yếu tố **điều người dùng biết**. Khi một dịch vụ bị lộ mật khẩu, kẻ tấn công có thể kiểm tra credential đó ở những dịch vụ khác mà không cần phá cơ chế hash của dịch vụ đích.

Một chuỗi tấn công điển hình:

~~~mermaid
flowchart TD
    A["Người dùng tái sử dụng mật khẩu"] --> B["Dịch vụ A bị xâm nhập"]
    B --> C["Email + mật khẩu bị lộ"]
    C --> D["Kẻ tấn công chuẩn hóa danh sách credential"]
    D --> E["Thử tự động trên dịch vụ B, C, D"]
    E --> F{"Có tài khoản dùng cùng mật khẩu?"}
    F -->|"Có"| G["Đăng nhập thành công"]
    F -->|"Không"| H["Thử biến thể / mục tiêu khác"]
    G --> I["Chiếm email, dữ liệu hoặc phiên"]
    I --> J["Đặt lại mật khẩu / mở rộng quyền"]
~~~

Kẻ tấn công thường không cần biết dịch vụ đích lưu mật khẩu bằng thuật toán gì. Họ chỉ gửi cặp username/password đã lộ tới endpoint đăng nhập của dịch vụ đích. Nếu cặp đó đúng, server đích tự xác minh và cấp phiên.

### Tác động lan truyền

- **Chiếm nhiều tài khoản:** một mật khẩu dùng ở nhiều dịch vụ làm tăng số mục tiêu bị ảnh hưởng.
- **Chiếm email trước:** hộp thư thường là kênh đặt lại mật khẩu cho dịch vụ khác. Khi email bị chiếm, kẻ tấn công có thể đặt lại nhiều tài khoản dù mật khẩu ban đầu của các dịch vụ đó khác nhau.
- **Vượt qua câu hỏi bảo mật hoặc khôi phục yếu:** thông tin cá nhân và các tài khoản liên quan có thể giúp kẻ tấn công hoàn tất quy trình phục hồi.
- **Duy trì truy cập:** sau khi đăng nhập, kẻ tấn công có thể tạo API key, thêm passkey, thay email khôi phục hoặc đánh cắp refresh token.
- **Ảnh hưởng tổ chức:** mật khẩu dùng lại giữa tài khoản nhân viên, VPN, máy chủ và môi trường thử nghiệm có thể làm sự cố nhỏ trở thành sự cố diện rộng.

Tái sử dụng mật khẩu **khuếch đại phạm vi ảnh hưởng**. Một dịch vụ bị xâm nhập không nhất thiết làm lộ tất cả tài khoản khác; rủi ro xuất hiện khi người dùng hoặc tổ chức dùng lại cùng bí mật hoặc biến thể có thể suy đoán.

## 3. Phân biệt credential stuffing, password spraying và brute force

Ba kiểu tấn công có thể xuất hiện cùng lúc nhưng khác nhau về dữ liệu đầu vào và cách thử:

| Kiểu tấn công | Cách thử | Mối liên hệ với password reuse |
| --- | --- | --- |
| **Credential stuffing** | Dùng danh sách username/password đã lộ để thử trên dịch vụ khác. | Khai thác trực tiếp việc dùng lại mật khẩu. |
| **Password spraying** | Thử một số ít mật khẩu phổ biến trên nhiều tài khoản. | Không nhất thiết cần mật khẩu lộ; nhắm vào mật khẩu yếu hoặc phổ biến. |
| **Brute force** | Thử nhiều ứng viên trên một tài khoản hoặc một tập tài khoản. | Có thể khai thác mật khẩu yếu; khác với việc tái sử dụng credential đã biết. |

Credential stuffing thường phân tán request qua nhiều IP, thiết bị hoặc thời điểm để tránh ngưỡng đơn giản. Password spraying giảm số lần thử trên từng tài khoản nhằm tránh khóa tài khoản. Vì vậy, chỉ giới hạn theo một địa chỉ IP hoặc một bộ đếm trên từng username có thể không đủ.

**Credential stuffing không phải là phá hash ngoại tuyến.** Kẻ tấn công lấy cặp thông tin đã lộ từ một nơi rồi thử đăng nhập trực tuyến ở nơi khác. Nếu database hash của dịch vụ A bị lộ, KDF chậm và salt riêng giúp làm khó việc đoán mật khẩu từ hash; nhưng chúng không ngăn một mật khẩu đã biết được thử trực tiếp vào dịch vụ B.

## 4. Hash mật khẩu tốt không giải quyết password reuse

Server cần lưu verifier mật khẩu an toàn: dùng thuật toán chuyên dụng như **Argon2id**, **scrypt**, **bcrypt** hoặc **PBKDF2** với tham số được cấu hình phù hợp và salt riêng cho mỗi tài khoản. Không lưu mật khẩu dạng plaintext, không dùng hash tổng quát nhanh như SHA-256 trực tiếp làm password hash.

Các biện pháp này bảo vệ trước một phần rủi ro khi **database verifier bị lộ**:

- Salt riêng làm cho cùng mật khẩu không tạo ra cùng verifier ở các tài khoản khác nhau.
- KDF chậm/tốn tài nguyên làm cho việc thử nhiều ứng viên ngoại tuyến tốn kém hơn.
- Pepper được quản lý riêng có thể bổ sung một lớp bảo vệ nếu kiến trúc phù hợp.

Tuy nhiên, nếu người dùng dùng cùng mật khẩu ở dịch vụ A và B, thì:

1. Kẻ tấn công biết mật khẩu plaintext từ A hoặc đã đoán được nó.
2. Kẻ tấn công gửi mật khẩu đó tới B.
3. Server B chạy KDF trên đầu vào và so sánh với verifier của chính B.
4. Nếu khớp, B chấp nhận đăng nhập.

KDF của B đang hoạt động đúng: nó xác minh đúng mật khẩu người dùng đã đặt. **Lỗi nằm ở việc bí mật đó được dùng ở nhiều nơi**, không phải ở việc thuật toán hash bị phá.

## 5. Quản lý mật khẩu duy nhất cho từng tài khoản

### 5.1. Password manager

Trình quản lý mật khẩu giúp tạo và lưu chuỗi ngẫu nhiên dài, duy nhất cho từng website. Người dùng chỉ cần bảo vệ một mật khẩu chính hoặc cơ chế mở khóa của vault, thay vì ghi nhớ hàng chục mật khẩu.

Lợi ích:

- Sinh mật khẩu ngẫu nhiên khác nhau cho từng dịch vụ.
- Giảm việc ghi mật khẩu ra giấy, file văn bản, email hoặc ghi chú không bảo vệ.
- Autofill theo tên miền giúp người dùng nhận biết trang đăng nhập giả hoặc tên miền gần giống.
- Hỗ trợ kiểm kê credential và phát hiện một số mật khẩu bị lặp hoặc đã lộ.

Điều cần bảo vệ:

- Mật khẩu chính, khóa khôi phục và thiết bị mở khóa vault.
- MFA của tài khoản password manager.
- Quy trình khôi phục vault và các thiết bị đã được tin cậy.
- Quyền chia sẻ mật khẩu trong nhóm; chỉ chia sẻ qua tính năng được quản lý và giới hạn người nhận.

Không nên dùng một mật khẩu chính dễ đoán hoặc tái sử dụng ở email. Nếu vault bị chiếm, nhiều credential riêng lẻ có thể cùng bị ảnh hưởng. Với tài khoản password manager, nên dùng mật khẩu chính mạnh, MFA chống phishing nếu có và kiểm soát thiết bị.

### 5.2. Không dùng biến thể dễ đoán

Đổi một ký tự, thêm tên dịch vụ, đổi năm hoặc thêm dấu chấm than ở cuối không tạo ra sự độc lập đáng tin cậy. Khi một mật khẩu gốc bị lộ, kẻ tấn công có thể thử các mẫu biến thể phổ biến.

Không nên hướng dẫn người dùng tạo quy tắc kiểu:

~~~text
<mật khẩu gốc> + tên website
<mật khẩu gốc> + năm hiện tại
<mật khẩu gốc> + ký tự đặc biệt
~~~

Thay vào đó, dùng password manager sinh chuỗi riêng hoặc passphrase dài được chọn ngẫu nhiên cho mỗi tài khoản. Nếu một dịch vụ giới hạn ký tự hoặc không hỗ trợ password manager, hãy chọn bí mật riêng đáp ứng chính sách dịch vụ và lưu trong vault.

### 5.3. Ưu tiên passkey khi phù hợp

**Passkey/WebAuthn** tạo credential mật mã gắn với RP ID/origin của dịch vụ. Người dùng không nhập một mật khẩu dùng chung trên nhiều website, nên credential stuffing dựa trên danh sách password bị lộ không áp dụng theo cùng cách.

Passkey giảm rủi ro phishing và tái sử dụng mật khẩu, nhưng vẫn cần:

- Quy trình đăng ký passkey chỉ cho chủ tài khoản hợp lệ.
- Bảo vệ thiết bị và tài khoản nền tảng đồng bộ passkey.
- Quản lý nhiều passkey, thiết bị dự phòng và thu hồi credential bị mất.
- Bảo vệ phiên/token sau khi passkey đã xác thực.
- Quy trình khôi phục tài khoản không yếu hơn đăng nhập chính.

Chuyển sang passkey không có nghĩa mọi mật khẩu cũ đã biến mất. Nếu tài khoản vẫn cho đăng nhập bằng mật khẩu yếu hoặc bị tái sử dụng, endpoint đó vẫn có thể bị credential stuffing. Cần xác định rõ khi nào có thể tắt mật khẩu và cách khôi phục tương ứng.

## 6. Phát hiện và ngăn credential stuffing

Một dịch vụ nên kết hợp nhiều lớp kiểm soát:

1. **Phát hiện mật khẩu phổ biến/đã lộ khi tạo hoặc đổi mật khẩu.** Từ chối mật khẩu xuất hiện trong danh sách bị lộ hoặc quá dễ đoán theo chính sách.
2. **Rate limit đa chiều.** Quan sát theo tài khoản, nguồn, mạng, thiết bị và mẫu chiến dịch; phối hợp giữa các server.
3. **Phân tích hành vi đăng nhập.** Tìm dấu hiệu thử nhiều tài khoản, nhiều mật khẩu từ một nguồn hoặc cùng credential pair trên nhiều tài khoản.
4. **MFA/passkey.** Yêu cầu yếu tố bổ sung theo chính sách; ưu tiên phương thức chống phishing cho tài khoản nhạy cảm.
5. **Phản hồi không tiết lộ tài khoản.** Hạn chế username enumeration qua thông báo, status code, thời gian phản hồi và luồng quên mật khẩu.
6. **Kiểm soát phiên sau đăng nhập.** Phát hiện phiên mới bất thường, thu hồi token, yêu cầu xác thực lại cho hành động nhạy cảm.

~~~mermaid
flowchart TD
    A["Nhận yêu cầu đăng nhập"] --> B["Thu thập tín hiệu an toàn<br/>tài khoản, nguồn, nhịp thử"]
    B --> C{"Có dấu hiệu stuffing<br/>hoặc vượt ngưỡng?"}
    C -->|"Có"| D["Giới hạn / thách thức bổ sung<br/>ghi nhận sự kiện"]
    C -->|"Không"| E["Kiểm tra password verifier"]
    E --> F{"Mật khẩu đúng?"}
    F -->|"Không"| G["Phản hồi chung<br/>cập nhật tín hiệu thất bại"]
    F -->|"Có"| H{"MFA / step-up<br/>được yêu cầu?"}
    H -->|"Có"| I["Xác minh yếu tố bổ sung"]
    H -->|"Không"| J["Tạo phiên mới"]
    I -->|"Đạt"| J
    I -->|"Không đạt"| G
    J --> K["Giám sát phiên và quyền API"]
~~~

### Rate limit cần tránh tạo khóa tài khoản thành công cho kẻ tấn công

Nếu cứ nhập sai năm lần là khóa tài khoản vô thời hạn, kẻ tấn công có thể cố tình làm mọi tài khoản bị khóa. Thay vào đó, cân nhắc:

- Tăng thời gian chờ có giới hạn.
- Giới hạn theo nhiều chiều thay vì chỉ theo username hoặc IP.
- Thách thức bổ sung khi rủi ro tăng.
- Cho phép người dùng hợp lệ tự phục hồi qua kênh đáng tin cậy.
- Theo dõi false positive và tác động tới người dùng cùng mạng.

CAPTCHA có thể làm tăng chi phí tự động hóa trong một số trường hợp, nhưng không thay thế MFA, phát hiện credential stuffing hoặc rate limit phía server. Không nên bắt mọi người dùng giải CAPTCHA liên tục nếu không có tín hiệu rủi ro.

## 7. Kiểm tra mật khẩu đã bị lộ khi đăng ký hoặc đổi

Một cách phòng ngừa là kiểm tra mật khẩu mới với danh sách mật khẩu phổ biến, dễ đoán hoặc đã xuất hiện trong các vụ rò rỉ. Mục tiêu là **ngăn đặt một bí mật đã có nguy cơ cao**, không phải chứng minh mật khẩu chưa từng bị lộ ở mọi nơi.

Các yêu cầu thiết kế:

- Kiểm tra tại thời điểm đăng ký và đổi mật khẩu; cân nhắc kiểm tra lại theo chính sách khi có sự cố hoặc phát hiện credential bị lộ.
- Không gửi plaintext password tới dịch vụ tra cứu bên ngoài.
- Nếu dùng dịch vụ tra cứu theo k-prefix/hash range, thực hiện theo giao thức và tài liệu của nhà cung cấp, giảm tối đa dữ liệu tiết lộ và đánh giá rủi ro riêng tư.
- Dùng danh sách được cập nhật, kết hợp từ điển mật khẩu phổ biến và dữ liệu nội bộ đã được xử lý an toàn.
- Trả thông báo hướng dẫn chọn mật khẩu khác, không nói rõ mật khẩu nào có trong nguồn dữ liệu nhạy cảm.

Ví dụ logic:

~~~text
setNewPassword(account, candidate):
    require authorizedPasswordChange(account)
    require candidateMeetsLengthAndInputPolicy(candidate)

    if breachedPasswordCheck(candidate) == "known_compromised":
        return rejectWithGuidance()

    verifier = approvedPasswordKdf(candidate, uniqueSalt())
    storeVerifierAtomically(account.id, verifier)
    revokeOrReviewExistingSessionsAccordingToPolicy(account.id)
    notifyAccountOwner()
    return success()
~~~

Đây là mã giả. Hàm kiểm tra mật khẩu bị lộ phải được thiết kế để bảo vệ bí mật; không log ứng viên, hash đầy đủ hoặc request có chứa password. Việc đổi mật khẩu cần xác minh quyền thao tác, chống CSRF nếu dùng cookie và xử lý phiên/token hiện có theo chính sách.

## 8. MFA, passkey và giới hạn của từng lớp

| Biện pháp | Giảm rủi ro nào? | Không giải quyết được gì? |
| --- | --- | --- |
| **Mật khẩu duy nhất** | Một vụ lộ ở dịch vụ A không trực tiếp cung cấp mật khẩu cho B. | Phishing, malware, đoán mật khẩu yếu hoặc chiếm phiên. |
| **Password manager** | Tạo/lưu mật khẩu khác nhau; giảm tái sử dụng và lỗi nhập sai domain. | Vault hoặc thiết bị password manager bị chiếm. |
| **TOTP MFA** | Mật khẩu bị lộ đơn lẻ thường chưa đủ đăng nhập. | OTP có thể bị phishing/chuyển tiếp trong thời gian hiệu lực. |
| **Push MFA** | Bổ sung bước xác nhận sở hữu thiết bị. | MFA fatigue nếu không có xác nhận ý định và giới hạn request. |
| **Passkey/WebAuthn** | Giảm password reuse và phishing nhờ ràng buộc origin/RP ID. | Thiết bị/tài khoản nền tảng bị chiếm, phiên sau đăng nhập bị đánh cắp, recovery yếu. |
| **Giám sát phiên** | Phát hiện/thu hồi một số hoạt động bất thường sau đăng nhập. | Không thể bảo đảm phát hiện mọi phiên bị chiếm; cần kết hợp kiểm soát phòng ngừa. |

MFA phải dùng các nhóm yếu tố độc lập phù hợp. Hai mật khẩu hoặc mật khẩu cộng một biến thể của chính nó vẫn là **cùng yếu tố biết**. Passkey có user verification tại authenticator có thể đem lại xác thực mạnh; RP cần kiểm tra đúng WebAuthn response, challenge, origin, RP ID và chính sách UV.

Đừng coi MFA là lý do cho phép tái sử dụng mật khẩu. MFA là lớp bổ sung; mật khẩu duy nhất vẫn giúp giảm sự lan truyền khi một dịch vụ khác bị lộ và giảm khả năng kẻ tấn công có ngay credential đầu tiên.

## 9. Trường hợp đặc biệt: SSO và mật khẩu dùng chung có chủ đích

**Single Sign-On (SSO)** có thể khiến người dùng chỉ cần xác thực một lần tại Identity Provider (IdP) rồi truy cập nhiều ứng dụng đã tin cậy IdP. Đây không phải là password reuse theo nghĩa dùng cùng mật khẩu ở nhiều website độc lập:

- Trong SSO, các ứng dụng dựa vào **bằng chứng federation** đã kiểm tra từ IdP; chúng không nhất thiết nhận hoặc lưu mật khẩu người dùng.
- Credential người dùng được quản lý tập trung tại IdP, với chính sách xác thực, MFA, khóa tài khoản và vòng đời danh tính thống nhất.
- SSO làm giảm số nơi người dùng phải nhập mật khẩu, nhưng tăng tầm quan trọng của IdP: nếu tài khoản IdP bị chiếm, nhiều ứng dụng có thể bị ảnh hưởng.

Vì vậy, IdP cần bảo vệ mạnh: passkey/MFA chống phishing khi phù hợp, bảo vệ phiên, quản trị khóa và thiết bị, quy trình khôi phục nghiêm ngặt, giám sát đăng nhập và khả năng thu hồi session ở các ứng dụng.

Một hệ thống cũng có thể dùng **service account** hoặc bí mật giữa các dịch vụ. Các bí mật này không phải mật khẩu người dùng, nhưng cũng cần tách biệt theo workload, môi trường và quyền tối thiểu. Không dùng cùng API key hoặc secret cho development, staging và production nếu có thể tránh; dùng secret manager, rotation và thu hồi.

## 10. Khi phát hiện mật khẩu đã bị tái sử dụng hoặc lộ

Phản ứng cần tập trung vào **phạm vi credential và phiên bị ảnh hưởng**, không chỉ yêu cầu người dùng đổi một mật khẩu:

1. Xác định tài khoản và dịch vụ có khả năng bị ảnh hưởng; tìm dấu hiệu đăng nhập thành công bất thường hoặc credential stuffing.
2. Buộc đổi mật khẩu ở dịch vụ bị ảnh hưởng nếu có căn cứ lộ hoặc dùng lại; mật khẩu mới phải duy nhất và không nằm trong danh sách đã lộ.
3. Nếu mật khẩu được dùng ở nhiều nơi, hướng dẫn người dùng thay ở **từng dịch vụ** bằng credential riêng. Một dịch vụ không thể thu hồi mật khẩu ở website khác.
4. Thu hồi session, refresh token, API key hoặc credential phụ đã bị lộ/được tạo trái phép theo phạm vi sự cố.
5. Kiểm tra thay đổi email khôi phục, passkey, MFA, thiết bị tin cậy và liên kết IdP.
6. Bật hoặc yêu cầu MFA/passkey theo chính sách; đặc biệt bảo vệ email và tài khoản quản trị.
7. Thông báo qua kênh đáng tin cậy, hướng dẫn người dùng tránh phishing giả mạo thông báo sự cố.
8. Theo dõi đăng nhập bất thường sau khi đổi mật khẩu; lưu log đủ điều tra nhưng không ghi mật khẩu/token thô.

**Không nên ép mọi người đổi mật khẩu định kỳ tùy tiện** chỉ vì password reuse là một rủi ro. Đổi mật khẩu có ích khi có bằng chứng bị lộ, mật khẩu yếu/phổ biến hoặc vi phạm chính sách. Thay đổi bắt buộc quá thường xuyên có thể khiến người dùng chọn các biến thể dễ đoán và tái sử dụng tiếp.

## 11. Ví dụ: một mật khẩu lộ dẫn đến chiếm email công ty

Một nhân viên dùng cùng mật khẩu ở diễn đàn bên ngoài và hộp thư công ty. Diễn đàn bị xâm nhập, credential bị rò rỉ. Kẻ tấn công thử cặp email/mật khẩu trên cổng email công ty. Hộp thư bị chiếm, sau đó kẻ tấn công dùng chức năng reset password của các ứng dụng khác.

### Chuỗi tác động

| Giai đoạn | Sự kiện | Kiểm soát cần có |
| --- | --- | --- |
| 1 | Diễn đàn bị lộ credential. | Người dùng dùng mật khẩu duy nhất; kiểm tra mật khẩu bị lộ khi đặt/đổi. |
| 2 | Credential stuffing vào email công ty. | MFA/passkey, phát hiện đăng nhập bất thường, rate limit đa chiều. |
| 3 | Hộp thư bị chiếm. | Bảo vệ email mạnh, cảnh báo đăng nhập, thu hồi session và kiểm soát thay đổi recovery. |
| 4 | Reset các tài khoản khác qua email. | Kiểm tra khôi phục, thông báo thay đổi, xác minh bổ sung cho tài khoản nhạy cảm. |
| 5 | Kẻ tấn công tạo passkey/token hoặc quy tắc chuyển tiếp email. | Cảnh báo thao tác nhạy cảm, kiểm kê credential, audit và thu hồi. |

### Câu hỏi thiết kế

**Nếu email đã bật TOTP, password reuse còn nguy hiểm không?** Có. Nó vẫn tạo ra lượng lớn lượt đăng nhập thất bại, có thể dẫn đến phishing hoặc MFA fatigue. Nếu kẻ tấn công lấy được OTP bằng phishing, hoặc chiếm kênh khôi phục, mật khẩu tái sử dụng làm bước đầu của chuỗi tấn công. MFA giảm rủi ro nhưng không biến password reuse thành an toàn.

**Nếu người dùng đổi mật khẩu email, các ứng dụng khác có tự an toàn không?** Không. Họ cần thay mật khẩu ở từng nơi đã dùng lại; đồng thời kiểm tra phiên, token và phương thức khôi phục đã bị kẻ tấn công thay đổi.

## 12. Mã giả: phát hiện dấu hiệu credential stuffing

Đoạn mã sau mô tả logic khái niệm, không phải hệ thống phát hiện production:

~~~text
handleLogin(identifier, password, requestContext):
    signals = collectSignals(
        account = normalizeIdentifier(identifier),
        source = requestContext.networkSignals,
        device = requestContext.deviceSignals,
        recentAttempts = sharedAttemptStore
    )

    if abusePolicy.requiresThrottle(signals):
        recordEvent("login_throttled", safeMetadata(signals))
        return genericRetryResponse()

    account = findAccount(identifier)
    verifier = account.exists ? account.passwordVerifier : dummyVerifier()
    passwordOk = verifyWithApprovedKdf(verifier, password)

    if not account.exists or not passwordOk:
        sharedAttemptStore.recordFailure(signals)
        recordEvent("login_failed", safeMetadata(signals))
        return genericAuthenticationFailure()

    if account.disabled:
        recordEvent("login_denied", safeMetadata(signals))
        return genericAuthenticationFailure()

    if policy.requiresMfaOrPasskey(account, signals):
        return beginAdditionalVerification(account, signals)

    session = createFreshProtectedSession(account.id)
    sharedAttemptStore.recordSuccess(signals)
    recordEvent("login_succeeded", safeMetadata(signals))
    return issueSession(session)
~~~

Các điểm cần chú ý:

- Bộ đếm/tín hiệu cần được phối hợp giữa nhiều instance; nếu mỗi server đếm độc lập, kẻ tấn công có thể phân tán request.
- \`dummyVerifier\` là một kỹ thuật giảm chênh lệch thời gian cho tài khoản không tồn tại; cần triển khai cùng KDF và chính sách tài nguyên hợp lý.
- Không ghi plaintext password hoặc gửi nó vào hệ thống phân tích.
- Không khóa vô thời hạn tài khoản chỉ vì một bộ đếm; chính sách phải cân bằng chống lạm dụng và khả năng truy cập của người dùng hợp lệ.
- Chỉ tạo phiên sau khi mọi bước xác thực bắt buộc đạt; MFA pending không được coi là đăng nhập hoàn chỉnh.

## 13. Danh sách kiểm tra cho tổ chức

- [ ] Mỗi tài khoản người dùng có mật khẩu riêng; không dùng chung bí mật giữa nhân viên, dịch vụ hoặc môi trường.
- [ ] Người dùng được hỗ trợ password manager, autofill và mật khẩu/passphrase dài.
- [ ] Không khuyến khích biến thể mật khẩu theo tên website, năm hoặc mẫu dễ đoán.
- [ ] Mật khẩu bị lộ/phổ biến được kiểm tra khi tạo và đổi theo cách bảo vệ dữ liệu.
- [ ] Server lưu password verifier bằng KDF chuyên dụng, salt riêng và tham số được đánh giá.
- [ ] Endpoint đăng nhập có rate limit đa chiều, phát hiện credential stuffing/password spraying và phản hồi chống liệt kê tài khoản.
- [ ] MFA/passkey được triển khai theo mức rủi ro; tài khoản quản trị và email được bảo vệ mạnh.
- [ ] SSO/IdP có chính sách xác thực, session, khôi phục và thu hồi đủ mạnh vì đây là điểm tập trung quyền truy cập.
- [ ] Session/refresh token được bảo vệ, xoay vòng, thu hồi và giám sát sau đăng nhập.
- [ ] Quy trình phản ứng khi mật khẩu lộ bao gồm đổi ở các dịch vụ tái sử dụng, thu hồi phiên/token và kiểm tra thay đổi tài khoản.
- [ ] Không ghi mật khẩu, OTP, reset token, cookie hoặc bearer token thô vào log.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao password reuse khiến một vụ rò rỉ ở dịch vụ ít quan trọng có thể dẫn đến chiếm email công ty?

**Câu 2.** Credential stuffing khác password spraying ở điểm nào?

**Câu 3.** Argon2id với salt riêng có ngăn kẻ tấn công thử một mật khẩu đã biết ở website khác không?

**Câu 4.** Tại sao thêm tên website vào cuối mật khẩu gốc không phải cách tốt để tránh tái sử dụng?

**Câu 5.** Password manager giảm password reuse nhưng tạo ra tài sản mới cần bảo vệ nào?

**Câu 6.** Vì sao SSO không đồng nghĩa với việc người dùng đang tái sử dụng cùng mật khẩu ở mọi ứng dụng?

### Gợi ý trả lời

1. Kẻ tấn công dùng cặp email/mật khẩu bị lộ để thử ở email công ty; nếu đúng, hộp thư có thể trở thành kênh reset cho nhiều tài khoản.
2. Credential stuffing dùng cặp thông tin đã lộ; password spraying thử một số mật khẩu phổ biến trên nhiều tài khoản.
3. Không. KDF giúp chống đoán ngoại tuyến từ verifier bị lộ; nếu kẻ tấn công đã biết mật khẩu, họ có thể gửi trực tiếp tới website khác.
4. Quy luật biến thể có thể suy đoán từ mật khẩu gốc; cần mật khẩu ngẫu nhiên và duy nhất cho mỗi dịch vụ.
5. Vault, mật khẩu chính/khóa mở khóa, thiết bị tin cậy và quy trình khôi phục password manager.
6. Trong SSO, ứng dụng dựa vào bằng chứng federation do IdP phát hành; chúng không nhất thiết nhận hoặc lưu mật khẩu người dùng.

## 15. Ghi nhớ

**Password reuse biến một credential bị lộ thành nguy cơ cho nhiều tài khoản.** Credential stuffing khai thác trực tiếp điểm yếu này; KDF tốt, salt riêng và TLS không thể ngăn một mật khẩu plaintext đã biết được thử ở dịch vụ khác. Cách giảm rủi ro bền vững là dùng mật khẩu ngẫu nhiên, duy nhất cho từng tài khoản qua password manager hoặc chuyển sang passkey khi phù hợp; kết hợp kiểm tra mật khẩu đã lộ, MFA chống phishing, rate limit đa chiều, bảo vệ phiên/token và quy trình khôi phục an toàn. Khi xảy ra sự cố, cần thay credential ở mọi nơi đã tái sử dụng và thu hồi các phiên/token có thể bị chiếm.
