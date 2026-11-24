# Credential guessing — Mô hình hóa và phòng chống đoán credential

> **Chương:** Threat model  
> **Chủ đề:** Credential guessing

**Credential guessing** là nhóm hành vi thử đoán hoặc thử lại thông tin xác thực để chiếm quyền truy cập vào một tài khoản, thiết bị, dịch vụ hoặc workload. Phổ biến nhất là đoán mật khẩu, nhưng cùng mô hình rủi ro còn áp dụng cho mã OTP, recovery code, mã PIN, token có entropy thấp và bí mật dùng chung của dịch vụ.

Không phải mọi lần đăng nhập thất bại đều là tấn công. Người dùng có thể gõ sai, quên mật khẩu hoặc dùng nhầm tài khoản. Threat model cần phân biệt lỗi sử dụng bình thường với hành vi có chủ đích, đánh giá được **tài sản nào bị đe dọa, điểm vào nào nhận credential, năng lực của kẻ tấn công, giới hạn của từng biện pháp phòng vệ và tác động tới người dùng hợp lệ**.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, người học cần hiểu credential từ mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này tập trung vào cách mô hình hóa và giảm rủi ro đoán credential trong toàn bộ vòng đời đăng nhập, bao gồm cả trường hợp kẻ tấn công có được bản sao kho verifier để thử đoán ngoại tuyến.

## 1. Kết quả học tập

Sau bài học, người học có thể:

1. Phân biệt **brute force, dictionary attack, password spraying, credential stuffing, targeted guessing** và đoán credential ngoại tuyến.
2. Xác định tài sản, chủ thể, entry point, trust boundary và tác động trong một threat model cho đăng nhập.
3. Phân tích vì sao rate limit chỉ ở một IP hoặc khóa tài khoản cứng có thể không đủ, thậm chí gây từ chối dịch vụ.
4. Thiết kế bảo vệ theo nhiều lớp: password verifier an toàn, giới hạn thử, phát hiện bất thường, MFA chống phishing, challenge có thời hạn và quy trình recovery đáng tin cậy.
5. Thiết lập logging/monitoring có ích mà không lưu mật khẩu, OTP, token hoặc dữ liệu bí mật nguyên dạng.
6. Xây dựng test case cho các tình huống đoán credential và đánh giá rủi ro còn lại sau khi áp dụng kiểm soát.

## 2. Credential guessing là gì?

Một hệ thống xác thực chấp nhận một bằng chứng khi verifier xác định bằng chứng đó phù hợp với credential đã đăng ký và đáp ứng chính sách. Kẻ tấn công cố tìm một giá trị được chấp nhận bằng cách thử nhiều khả năng, sử dụng dữ liệu đã lộ hoặc khai thác quy trình kiểm tra yếu.

### 2.1. Các kiểu tấn công thường gặp

| Kiểu | Cách thức khái quát | Dấu hiệu thường gặp |
| --- | --- | --- |
| **Brute force** | Thử nhiều tổ hợp có thể có của một bí mật | Nhiều lần thử trên một tài khoản hoặc một tập tài khoản |
| **Dictionary attack** | Thử các mật khẩu phổ biến, từ điển hoặc biến thể dễ đoán | Các giá trị phổ biến được thử lặp lại |
| **Password spraying** | Thử một hoặc vài mật khẩu phổ biến trên nhiều tài khoản | Một mật khẩu/nhóm nhỏ xuất hiện trên nhiều subject |
| **Credential stuffing** | Dùng cặp username/password đã bị lộ ở dịch vụ khác | Đăng nhập thất bại phân tán, đôi khi có thành công trên tài khoản tái sử dụng mật khẩu |
| **Targeted guessing** | Dựa trên thông tin công khai hoặc ngữ cảnh về một người/tổ chức để đoán | Thử tập trung vào tài khoản cụ thể, có thể theo tên, mùa, sự kiện hoặc quy tắc tổ chức |
| **Offline password cracking** | Có bản sao password hash và thử đoán trực tiếp trên bản sao | Không tạo request đăng nhập tới dịch vụ thật |
| **OTP/PIN guessing** | Thử không gian mã ngắn hoặc mã dự phòng | Nhiều lần thử trong một challenge hoặc trên nhiều challenge |
| **Recovery token guessing** | Thử đoán mã đặt lại hoặc mã khôi phục có entropy không đủ | Request dồn vào endpoint recovery/verification |

Các tên gọi mô tả **mô hình hành vi**, không phải lúc nào cũng loại trừ nhau. Ví dụ, kẻ tấn công có thể dùng password spraying để tìm một tài khoản, sau đó thử credential stuffing hoặc khai thác recovery.

### 2.2. Đoán online và offline khác nhau thế nào?

| Thuộc tính | Online guessing | Offline guessing |
| --- | --- | --- |
| Nơi thử | Endpoint đăng nhập/MFA/recovery của dịch vụ | Bản sao dữ liệu verifier đã lấy được |
| Phụ thuộc mạng dịch vụ | Có | Không cần gửi request tới dịch vụ |
| Rate limit phía server | Có thể làm chậm hoặc chặn | Không áp dụng cho việc thử trên bản sao |
| Điều kiện để xảy ra | Endpoint nhận thử credential có thể truy cập | Kẻ tấn công lấy được hash/verifier hoặc dữ liệu đủ để kiểm tra giả lập |
| Kiểm soát trọng tâm | Rate limit, phát hiện hành vi, MFA, challenge, bảo vệ endpoint | Password hashing chậm, salt, pepper, bảo vệ kho dữ liệu và backup |

Rate limit rất hữu ích cho online guessing, nhưng không cứu được một kho password hash yếu đã bị đánh cắp. Ngược lại, Argon2id làm tăng chi phí đoán offline nhưng không ngăn một bot thử mật khẩu trực tiếp qua login endpoint. Hai kịch bản phải được mô hình hóa riêng.

## 3. Phạm vi threat model cho đăng nhập

Threat model bắt đầu bằng việc xác định **cái gì cần bảo vệ** và **đường nào có thể bị lạm dụng**. Không bắt đầu bằng việc chọn CAPTCHA hay khóa tài khoản rồi giả định rủi ro đã được giải quyết.

### 3.1. Tài sản cần bảo vệ

- **Tài khoản và danh tính:** internal user ID, liên kết IdP, tenant membership và trạng thái tài khoản.
- **Credential:** password verifier, TOTP secret, recovery code, passkey public key/credential metadata, khóa/chứng chỉ client, API secret.
- **Kênh khôi phục:** email, số điện thoại, recovery token, quy trình hỗ trợ và quyền của nhân viên hỗ trợ.
- **Phiên và token:** session cookie, refresh token, access token và trạng thái thu hồi.
- **Dữ liệu/nghiệp vụ:** hồ sơ cá nhân, kết quả học tập, thông tin thanh toán, quyền quản trị và dữ liệu tenant.
- **Khả năng cung cấp dịch vụ:** login, MFA, recovery và hệ thống quản lý credential phải tiếp tục phục vụ người dùng hợp lệ.

### 3.2. Chủ thể và năng lực đối kháng

Kẻ tấn công có thể là người ngoài, botnet, người dùng nội bộ lạm dụng quyền, hoặc người đã có một phần thông tin về nạn nhân. Khi xây dựng kịch bản, hãy nêu rõ năng lực giả định:

- Biết email/username công khai hoặc danh sách tài khoản bị lộ;
- Có mật khẩu từ một vụ rò rỉ khác và biết một số người dùng tái sử dụng mật khẩu;
- Có thể gửi nhiều request từ nhiều địa chỉ mạng/thiết bị;
- Có thể đọc thông tin công khai về người dùng/tổ chức;
- Có thể thử lại một số lần trên endpoint login, MFA hoặc recovery;
- Trong kịch bản nghiêm trọng hơn, đã lấy được bản sao password hash hoặc dữ liệu backup;
- Có thể tận dụng tài khoản hợp lệ, proxy, thiết bị bị chiếm hoặc kênh hỗ trợ yếu.

Không mặc định mọi kẻ tấn công đều có botnet, quyền truy cập cơ sở dữ liệu hay khả năng vượt qua MFA. Phải ghi giả định và mức tác động để kiểm soát được ưu tiên đầu tư.

### 3.3. Entry point và ranh giới tin cậy

Các điểm nhận credential thường không chỉ có một form login:

| Entry point | Bằng chứng/đầu vào | Rủi ro cần mô hình hóa |
| --- | --- | --- |
| Login web/mobile | Identifier + password, passkey assertion | Brute force, stuffing, phishing, enumeration |
| MFA verification | TOTP, SMS/email OTP, push response | Đoán mã, replay, push fatigue, nhầm transaction |
| Password reset | Recovery token hoặc bằng chứng kênh liên hệ | Đoán token, chiếm email/điện thoại, bypass MFA |
| Account recovery | Recovery code, quy trình hỗ trợ | Mã ngắn dễ đoán, social engineering, lạm dụng nhân viên |
| Enrollment credential | Password hiện tại, MFA, challenge đăng ký passkey | Kẻ tấn công thêm credential của họ vào tài khoản đã chiếm |
| SSO callback | State, authorization code, token/assertion | Login CSRF, code interception, nhầm issuer/audience |
| API/service authentication | API key, client secret, certificate proof, token | Secret yếu/tái sử dụng, token replay, credential dùng chung |

~~~mermaid
flowchart LR
    C["Browser / Mobile / Service"] -->|"Login / MFA / Recovery"| E["Gateway / Auth endpoints"]
    E --> A["Authentication service"]
    A --> V[("Credential verifier store")]
    A --> S[("Session / token state")]
    I["IdP / External identity"] -->|"OIDC / SAML result"| A
    R["Recovery channel / Support"] -->|"Reset / recovery proof"| A
    A --> P["Policy / Authorization"]
    P --> D["Protected APIs and data"]
    M["Monitoring / Security operations"] -.-> E
    M -.-> A
~~~

Mỗi đường vào cần được kiểm soát riêng. Nếu login web có rate limit nhưng password reset hoặc MFA verify không có giới hạn tương đương, kẻ tấn công có thể chuyển sang đường yếu hơn. Nếu IdP bên ngoài được tin cậy, phải hiểu chính sách thử sai và recovery của IdP vì nó có thể là một phần của ranh giới bảo mật.

## 4. Cách kẻ tấn công tìm được credential

### 4.1. Mật khẩu yếu và dễ đoán

Mật khẩu ngắn, phổ biến, dựa trên thông tin cá nhân hoặc quy luật tổ chức thường có ít khả năng hơn người dùng nghĩ. Ví dụ các mẫu như tên tổ chức cộng năm hiện tại, tên đội cộng dấu chấm than, hoặc một chuỗi phổ biến chỉ thay ký tự cuối có thể bị đoán dễ hơn một passphrase dài, độc lập.

Không nên đánh giá độ mạnh chỉ dựa vào một quy tắc hình thức như “có chữ hoa, chữ thường, số và ký tự đặc biệt”. Một mật khẩu theo mẫu dễ đoán vẫn có thể yếu dù thỏa nhiều loại ký tự. Khuyến khích mật khẩu dài, duy nhất cho từng dịch vụ và dùng password manager; chặn mật khẩu phổ biến/đã lộ khi đặt hoặc đổi mật khẩu.

### 4.2. Tái sử dụng credential

Khi một dịch vụ khác bị rò rỉ, cặp username/password có thể được thử trên hệ thống của bạn. Đây là lý do mật khẩu duy nhất cho từng dịch vụ quan trọng hơn việc ép người dùng thay một ký tự theo chu kỳ. Một hệ thống không thể giả định rằng password đúng ở lần đăng nhập là password chưa từng lộ ở nơi khác.

### 4.3. Thông tin công khai và nhắm mục tiêu

Tên, ngày sinh, đơn vị, tên khóa học, chức vụ, địa chỉ email và lịch sự kiện có thể giúp kẻ tấn công tạo các phỏng đoán có chủ đích. Những thông tin này không nhất thiết phải bí mật, nhưng không nên dùng chúng làm câu hỏi bảo mật hoặc thành phần dễ đoán của mật khẩu mặc định.

### 4.4. Lộ kho verifier

Nếu kẻ tấn công đọc được password hash, họ có thể thử đoán ngoại tuyến mà không bị rate limit của endpoint. Tốc độ thử phụ thuộc thuật toán, tham số chi phí và năng lực phần cứng. Hash nhanh và không có salt riêng khiến việc thử nhiều tài khoản hiệu quả hơn.

**Salt** ngẫu nhiên, riêng cho từng mật khẩu làm mất lợi thế của bảng tra cứu dùng chung và khiến cùng một password không nhất thiết tạo cùng hash. **Password hashing function chậm** làm tăng chi phí mỗi lần thử. **Pepper** được giữ riêng có thể bổ sung một lớp bảo vệ nếu kho hash bị lấy, nhưng không thay thế salt, thuật toán phù hợp hay bảo vệ database.

## 5. Threat scenarios: mô tả chuỗi tấn công và tác động

Threat model hữu ích cần diễn đạt một chuỗi nguyên nhân – kết quả thay vì chỉ liệt kê tên tấn công.

| Kịch bản | Chuỗi sự kiện | Tác động có thể có |
| --- | --- | --- |
| **Password spraying** | Kẻ tấn công thử một số mật khẩu phổ biến trên nhiều tài khoản; hệ thống chỉ giới hạn theo từng account | Một số tài khoản có thể bị chiếm mà từng account chưa chạm ngưỡng khóa |
| **Credential stuffing** | Cặp credential từ nơi khác được thử; hệ thống không phát hiện thiết bị/hành vi bất thường | Chiếm tài khoản có mật khẩu tái sử dụng |
| **Enumeration trước guessing** | Endpoint phản hồi khác nhau cho account tồn tại và không tồn tại | Thu thập danh sách subject để nhắm mục tiêu |
| **OTP guessing** | Mã ngắn được thử nhiều lần; challenge có thể tạo lại không giới hạn | Vượt MFA hoặc làm cạn tài nguyên xác minh |
| **Recovery guessing** | Mã reset có entropy thấp hoặc không hết hạn/không dùng một lần | Đổi credential và tiếp quản tài khoản |
| **Lockout DoS** | Chính sách khóa cứng sau ít lần sai; kẻ tấn công cố ý gây thất bại | Người dùng hợp lệ không đăng nhập được |
| **Offline cracking** | Backup chứa hash bị lộ; thuật toán hash quá nhanh | Khôi phục password có thể dùng lại ở nhiều dịch vụ |
| **MFA enrollment takeover** | Phiên yếu bị chiếm; attacker thêm authenticator của họ | Duy trì quyền kiểm soát kể cả khi nạn nhân đổi password |

### 5.1. Ví dụ: rate limit chỉ theo IP

Giả sử hệ thống cho phép một địa chỉ IP thử tối đa một số lần trong một khoảng thời gian. Điều này có thể giảm một nguồn gửi request quá nhanh, nhưng vẫn có lỗ hổng nếu:

- Một tài khoản bị thử từ nhiều nguồn;
- Nhiều tài khoản bị thử từ cùng một mạng hoặc các mạng khác nhau;
- Proxy/gateway không xác định đúng IP gốc và ứng dụng tin header do client tự đặt;
- Một nguồn dùng chung NAT của trường hoặc doanh nghiệp, làm người dùng hợp lệ bị giới hạn cùng nhau;
- Kẻ tấn công phân tán request để mỗi địa chỉ trông như lưu lượng bình thường.

Vì vậy, rate limit phải kết hợp nhiều chiều và có đánh giá tác động tới người dùng hợp lệ. Không có một ngưỡng duy nhất phù hợp cho mọi tenant, phương thức và mức rủi ro.

### 5.2. Ví dụ: khóa cứng tài khoản

Khóa tài khoản sau một số lần thất bại có thể ngăn đoán liên tục, nhưng kẻ tấn công cũng có thể cố tình làm tài khoản của nạn nhân bị khóa. Với tài khoản quan trọng, việc mở khóa qua helpdesk có thể trở thành một đường tấn công khác.

Có thể dùng trì hoãn tăng dần, giới hạn theo account và nguồn, step-up, cảnh báo và quy trình hỗ trợ đã xác minh. Nếu dùng lockout, cần quy định thời gian, cách mở khóa, quyền của nhân viên hỗ trợ và cách tránh để kẻ tấn công gây DoS lặp lại.

## 6. Phòng vệ online guessing theo nhiều lớp

Không một biện pháp đơn lẻ nào giải quyết được mọi loại guessing. Phòng vệ hiệu quả kết hợp **ngăn thử quá mức, làm giảm giá trị của credential bị đoán, phát hiện hành vi, bảo vệ recovery và phản ứng khi có dấu hiệu xâm nhập**.

### 6.1. Rate limiting đa chiều

Áp dụng giới hạn ở nhiều khóa đo lường:

- **Account/subject:** số lần thất bại trên internal subject ID; xử lý identifier chưa tồn tại bằng bucket phù hợp để không lộ account.
- **IP và network:** giới hạn theo địa chỉ, subnet hoặc nhóm nguồn khi có căn cứ; xác định IP từ proxy tin cậy, không tin header tùy ý.
- **Device/session:** tín hiệu thiết bị, cookie ẩn danh hoặc dấu hiệu tự động hóa có thể hỗ trợ nhưng không nên là định danh duy nhất.
- **Tenant/application:** ngăn một tenant hoặc client chiếm toàn bộ năng lực xác thực.
- **Global/service:** bảo vệ CPU, database, SMS/email provider và hệ thống MFA khỏi bão request.
- **Challenge/method:** OTP, recovery code và WebAuthn challenge cần giới hạn theo giao dịch/phương thức.

Rate limit nên áp dụng ở gateway và lớp ứng dụng phù hợp. Gateway giúp chặn sớm; authentication service có hiểu biết về subject, challenge và trạng thái credential để đưa ra quyết định chính xác hơn.

### 6.2. Delay và challenge theo rủi ro

Một số lựa chọn:

- Tăng dần thời gian chờ sau chuỗi thất bại;
- Yêu cầu step-up hoặc challenge bổ sung khi có dấu hiệu tự động hóa;
- Dùng CAPTCHA như một tín hiệu/biện pháp phụ trợ, không làm lớp bảo vệ duy nhất;
- Giới hạn thử OTP và số lần phát hành challenge;
- Từ chối hoặc yêu cầu xác minh lại khi có rủi ro cao, đồng thời cung cấp đường hỗ trợ cho người dùng hợp lệ.

Challenge phải được thiết kế sao cho người dùng có thể hoàn thành bằng phương thức trợ năng và thiết bị được hỗ trợ. Một biện pháp chống bot không được làm lộ danh tính tài khoản hoặc biến login thành một dịch vụ dễ bị từ chối.

### 6.3. Phản hồi thống nhất và chống enumeration

Nếu endpoint trả “không có tài khoản” khác “mật khẩu sai”, kẻ tấn công có thể lập danh sách tài khoản. Phản hồi công khai nên chung chung cho các trường hợp không xác thực được. Bên trong, hệ thống vẫn có thể ghi reason code đã lọc bí mật để hỗ trợ giám sát.

Đánh giá cả **mã HTTP, response body, độ dài response, thời gian phản hồi, luồng redirect và việc gửi thông báo**. Ví dụ, chỉ trả cùng câu chữ nhưng tài khoản không tồn tại mất 5 ms còn tài khoản có tồn tại mất 300 ms vẫn có thể tạo kênh enumeration. Cần kiểm soát timing ở mức phù hợp, không hứa hẹn triệt tiêu hoàn toàn mọi side channel.

## 7. Phòng vệ password và kho verifier

### 7.1. Lưu password đúng cách

- Dùng password hashing function chuyên dụng, ưu tiên **Argon2id** khi nền tảng hỗ trợ; lựa chọn tham số chi phí phù hợp với năng lực server và tải thực tế.
- Sinh **salt ngẫu nhiên, riêng cho từng password** và lưu cùng hash theo định dạng chuẩn của thư viện.
- Có thể dùng **pepper** được giữ ngoài database, trong secret manager/HSM; lập kế hoạch rotation và phục hồi khi pepper bị lộ hoặc không còn khả dụng.
- Không lưu plaintext, mã hóa đảo ngược hoặc hash nhanh thuần túy làm password verifier.
- Giới hạn quyền đọc kho verifier; mã hóa backup, bảo vệ môi trường vận hành và giám sát truy cập bất thường.
- Nâng tham số hash theo lộ trình; có thể rehash khi người dùng đăng nhập thành công bằng password hợp lệ, hoặc yêu cầu reset theo mức rủi ro nếu cần.

**Salt không làm mật khẩu yếu thành mạnh**. Nó làm cho việc dùng bảng hash tính sẵn và việc chia sẻ kết quả giữa các tài khoản khó hơn. Thuật toán chậm làm tăng chi phí từng phỏng đoán, còn độ dài và tính khó đoán của password quyết định xác suất phỏng đoán đúng.

### 7.2. Chính sách mật khẩu hướng tới người dùng

Khuyến khích passphrase dài, duy nhất; hỗ trợ password manager, copy/paste và autofill; chặn password phổ biến hoặc đã biết bị lộ khi tạo/đổi; không bắt người dùng đổi theo chu kỳ cứng nếu không có dấu hiệu xâm nhập hoặc yêu cầu chính sách phù hợp. Không áp dụng quy tắc thành phần quá máy móc khiến người dùng chọn mật khẩu theo mẫu dễ đoán.

Khi mật khẩu đã bị lộ, yêu cầu thay đổi và xem xét thu hồi phiên/refresh token theo rủi ro. Chỉ đổi password có thể chưa đủ nếu kẻ tấn công đã thêm passkey, thay recovery channel hoặc chiếm phiên đang hoạt động.

### 7.3. Nếu password hash bị đánh cắp

Kế hoạch phản ứng nên bao gồm:

1. Xác định kho dữ liệu, backup, thời điểm và phạm vi subject bị ảnh hưởng.
2. Ngăn truy cập tiếp, bảo vệ log/bằng chứng điều tra và đánh giá khả năng lộ pepper hoặc secret liên quan.
3. Đánh giá thuật toán, tham số hash, salt và nguy cơ đoán offline; ưu tiên tài khoản đặc quyền và mật khẩu có dấu hiệu tái sử dụng.
4. Yêu cầu reset hoặc nâng cấp credential theo mức rủi ro; cân nhắc buộc xác thực lại và thu hồi phiên.
5. Kiểm tra hoạt động đăng nhập bất thường ở các dịch vụ khác nếu cùng credential có thể được dùng lại.
6. Khắc phục quyền truy cập, backup, quy trình vận hành và kiểm thử để tránh tái diễn.

## 8. MFA, passkey và giới hạn của từng yếu tố

MFA làm giảm khả năng một password bị đoán đơn lẻ dẫn tới chiếm tài khoản, nhưng không phải mọi yếu tố thứ hai đều có khả năng chống phishing hoặc guessing như nhau.

| Phương thức | Tác dụng đối với guessing | Giới hạn/rủi ro |
| --- | --- | --- |
| **SMS OTP** | Bổ sung yếu tố ngoài password | SIM swap, phishing, số tái cấp và mã ngắn |
| **Email OTP** | Thêm bước kiểm soát hộp thư | Phụ thuộc bảo mật email; có thể cùng kênh recovery |
| **TOTP** | Bí mật thứ hai và mã đổi theo thời gian | Có thể bị đoán trong cửa sổ nếu giới hạn yếu; phishing thời gian thực |
| **Push approval** | Cần chấp thuận từ thiết bị đã đăng ký | Push fatigue, chấp thuận nhầm |
| **Passkey/WebAuthn** | Challenge có chữ ký gắn với RP ID/origin; chống phishing credential | Recovery/enrollment và bảo mật thiết bị vẫn quan trọng |
| **Client certificate/mTLS** | Proof of possession khóa riêng, phù hợp service/device | Bảo vệ khóa, CA, SAN và quyền cấp chứng chỉ |

### 8.1. MFA phải được gắn với đúng giao dịch

Server phải biết account nào đã qua yếu tố đầu, yếu tố tiếp theo được yêu cầu là gì, transaction còn hạn không và kết quả đã dùng chưa. Không nhận một trường boolean từ client như **mfa_passed** để bỏ qua verifier.

Mỗi OTP cần giới hạn số lần thử theo account/challenge và thời gian. Recovery code nên có entropy cao, chỉ sử dụng một lần, lưu verifier an toàn và được tiêu thụ nguyên tử. Không dùng cùng một mã hoặc kết quả xác thực cho nhiều mục đích.

### 8.2. Passkey không loại bỏ toàn bộ threat model

Passkey giúp chống phishing và giảm đoán password, nhưng attacker vẫn có thể:

- Lạm dụng luồng **thêm passkey** nếu một phiên yếu đã bị chiếm;
- Đánh cắp session cookie sau khi đăng nhập;
- Tấn công tài khoản email hoặc recovery channel;
- Lợi dụng quy trình hỗ trợ để thay credential;
- Gây từ chối dịch vụ bằng cách spam challenge hoặc khóa tài khoản.

Do đó, passkey phải đi cùng quản lý credential, thông báo khi thêm/xóa, xác thực lại phù hợp, recovery và session management.

## 9. Credential guessing ở MFA và recovery

Không nên chỉ tập trung login password. Những mã ngắn hoặc đường khôi phục có thể trở thành điểm yếu hơn.

### 9.1. TOTP và OTP

Mã OTP thường có không gian nhỏ hơn password dài. Giới hạn thử phải áp dụng theo challenge và account, có thời hạn, tránh cho phép tạo vô hạn challenge song song. Hệ thống nên kiểm soát việc chấp nhận lại một mã trong cùng cửa sổ theo chính sách, và tránh tiết lộ tài khoản tồn tại qua phản hồi.

Nếu endpoint xác minh TOTP cho phép nhiều request đồng thời, hai request có thể cùng kiểm tra trước khi trạng thái tiêu thụ được cập nhật. Dùng cập nhật nguyên tử hoặc cơ chế khóa phù hợp để không có hai kết quả thành công ngoài ý muốn.

### 9.2. Recovery token và reset link

Recovery token nên:

- Được tạo bằng bộ sinh số ngẫu nhiên mật mã với entropy đủ lớn;
- Gắn với một subject, mục đích cụ thể và thời hạn;
- Chỉ sử dụng một lần, có trạng thái tiêu thụ và hủy;
- Lưu verifier/hash token thay vì token thô nếu thiết kế cho phép;
- Không xuất hiện trong log, analytics, referrer hoặc trang bên thứ ba;
- Có rate limit và phản hồi chống enumeration.

Reset link không nên cho phép đổi mật khẩu chỉ vì một request GET được mở bởi email scanner hoặc preview bot. Có thể dùng bước xác nhận rõ ràng và giao dịch server-side để tránh token bị tiêu thụ ngoài ý muốn. Khi reset thành công, đánh giá thu hồi phiên, refresh token và credential nghi ngờ.

### 9.3. Helpdesk và quy trình recovery thủ công

Nhân viên hỗ trợ là một phần của trust boundary. Không yêu cầu khách hàng đọc password/OTP cho nhân viên. Quy trình xác minh cần tiêu chí rõ, ghi audit, phân quyền và kiểm soát hành động rủi ro cao. Tránh dựa trên thông tin dễ đoán hoặc dữ liệu công khai như ngày sinh, tên trường, email công ty.

Đối với tài khoản đặc quyền, có thể cần phê duyệt hai người, kênh xác minh độc lập hoặc thời gian chờ có thông báo. Mục tiêu là bảo đảm kẻ tấn công không thể biến recovery thành con đường vượt MFA.

## 10. Phát hiện hành vi đoán credential

Monitoring nên kết hợp dữ liệu theo account, nguồn, phương thức, challenge, tenant và kết quả. Không một tín hiệu đơn lẻ đủ để kết luận chắc chắn có tấn công.

### 10.1. Tín hiệu đáng chú ý

- Tỷ lệ thất bại tăng bất thường so với baseline của dịch vụ/tenant;
- Nhiều subject khác nhau bị thử trong khoảng thời gian ngắn;
- Một account nhận thất bại từ nhiều mạng hoặc thiết bị không quen thuộc;
- Nhiều account bị thử với cùng pattern hoặc một tập nhỏ giá trị phổ biến;
- Tăng số lượng challenge MFA/recovery được phát nhưng không hoàn tất;
- Đăng nhập thành công sau một chuỗi thất bại bất thường;
- Thêm passkey, thay recovery channel hoặc đổi password ngay sau đăng nhập rủi ro;
- Tài khoản có quyền cao bị thử liên tục hoặc đăng nhập từ bối cảnh lạ;
- Lỗi xác minh tập trung ở một issuer, một ứng dụng hoặc một tenant.

### 10.2. Event schema an toàn

Một event có thể ghi:

~~~json
{
  "event_type": "authentication_failed",
  "timestamp": "2026-11-22T03:00:00Z",
  "subject_ref": "internal-pseudonymous-reference",
  "tenant_ref": "tenant-a",
  "method": "password",
  "result": "failure",
  "reason_group": "invalid_credential",
  "source_context": "redacted-network-and-device-signals",
  "correlation_id": "opaque-event-id"
}
~~~

Đây là schema minh họa. Không ghi password, password hash, OTP, recovery code, session ID, access/refresh token hoặc secret nguyên dạng. Dữ liệu IP/thiết bị có thể là dữ liệu cá nhân; cần kiểm soát quyền đọc, thời gian lưu và mục đích sử dụng.

### 10.3. Phân biệt tín hiệu tấn công với người dùng hợp lệ

Một lớp học có thể dùng chung NAT; một doanh nghiệp có thể có proxy; người dùng đi du lịch hoặc đổi thiết bị. Nếu chỉ thấy nhiều account cùng IP, không nên tự động kết luận tất cả là tấn công. Kết hợp nhiều tín hiệu, đánh giá rủi ro và theo dõi false positive. Người dùng hợp lệ cần có đường khôi phục đăng nhập không yêu cầu họ cung cấp bí mật cho bộ phận hỗ trợ.

## 11. Phản ứng khi phát hiện credential guessing

Phản ứng nên theo mức độ và bằng chứng:

1. **Xác nhận phạm vi:** loại endpoint, tenant, account, phương thức và thời gian; xác định có đăng nhập thành công hay chỉ có thất bại.
2. **Giảm lưu lượng gây hại:** điều chỉnh rate limit, challenge hoặc block có mục tiêu; tránh khóa hàng loạt account khiến tấn công biến thành DoS.
3. **Bảo vệ tài khoản bị ảnh hưởng:** step-up, buộc reset khi có bằng chứng credential lộ, thu hồi phiên/token và kiểm tra authenticator mới được thêm.
4. **Bảo toàn chứng cứ:** lưu sự kiện đã redaction, correlation ID và thông tin cần thiết cho điều tra; không sao chép secret vào ticket.
5. **Thông báo và hỗ trợ:** cảnh báo người dùng khi có đăng nhập/đổi credential đáng ngờ, hướng dẫn kiểm tra phiên và recovery an toàn.
6. **Khắc phục nguyên nhân:** sửa rate limit, verifier, recovery, enumeration, cấu hình proxy hoặc quy trình hỗ trợ.
7. **Đánh giá sau sự cố:** xác định kiểm soát nào thất bại, false positive/false negative, cập nhật threat model và test regression.

Nếu có bằng chứng kho verifier bị lấy, coi đó là sự cố **offline guessing** riêng: rate limit ở login endpoint không xử lý được nguy cơ này.

## 12. Ví dụ xuyên suốt: nền tảng học tập đa tenant

Một nền tảng phục vụ nhiều trường có học viên, giảng viên và quản trị viên. Hệ thống hỗ trợ password + TOTP, passkey và SSO của trường. Các tenant dùng chung một cụm authentication service nhưng có dữ liệu và chính sách riêng.

### 12.1. Tài sản, ranh giới và rủi ro

| Thành phần | Tài sản/điểm tin cậy | Rủi ro chính |
| --- | --- | --- |
| Login endpoint | Nhận password hoặc bắt đầu WebAuthn/SSO | Brute force, stuffing, enumeration |
| MFA endpoint | TOTP challenge và trạng thái giao dịch | Đoán OTP, replay, cross-account binding |
| Recovery service | Email, recovery token và hỗ trợ | Chiếm kênh khôi phục, reset token guessing |
| Credential store | Password verifier, TOTP secret, passkey metadata | Offline cracking, rò rỉ secret |
| Session/token service | Phiên và refresh token | Chiếm phiên sau khi guessing thành công |
| Tenant policy | Membership và role | Nhầm tenant, quyền vượt phạm vi |
| Monitoring | Event xác thực và tín hiệu thiết bị | Bỏ sót tấn công phân tán hoặc thu thập quá nhiều dữ liệu |

### 12.2. Một kịch bản password spraying

Hệ thống phát hiện nhiều tài khoản trong tenant trường A có một lần đăng nhập thất bại trong thời gian ngắn, từ nhiều nguồn khác nhau. Từng account chưa chạm ngưỡng giới hạn riêng nên rate limit theo account đơn lẻ không kích hoạt.

Phản ứng có thể:

- Tính tỷ lệ thất bại theo tenant và nhóm nguồn, đồng thời so sánh baseline;
- Tăng challenge hoặc delay theo rủi ro cho luồng password;
- Thông báo đội vận hành nếu pattern lan rộng, bảo vệ account đặc quyền;
- Không tự động khóa toàn bộ học viên của trường;
- Theo dõi đăng nhập thành công sau chuỗi thất bại và yêu cầu step-up khi phù hợp.

### 12.3. Một kịch bản credential stuffing

Một số học viên dùng lại password ở nhiều dịch vụ. Sau một vụ lộ dữ liệu bên ngoài, nền tảng thấy một nhóm login thành công từ thiết bị lạ dù trước đó có nhiều thất bại.

Biện pháp:

1. Đánh giá tín hiệu rủi ro và yêu cầu step-up/phương thức mạnh hơn;
2. Kiểm tra mật khẩu đã lộ theo phương thức bảo vệ phù hợp khi đổi password;
3. Yêu cầu reset cho account có bằng chứng bị ảnh hưởng;
4. Thu hồi phiên và refresh token đáng ngờ;
5. Cảnh báo người dùng, khuyến khích password manager và mật khẩu duy nhất;
6. Rà soát các luồng recovery/enrollment để tránh attacker giữ quyền sau khi password đã đổi.

### 12.4. Chính sách khác nhau theo mức ảnh hưởng

| Nhóm | Kiểm soát đề xuất |
| --- | --- |
| Học viên | Rate limit, password dài/duy nhất, MFA/passkey khuyến khích hoặc theo rủi ro, recovery rõ ràng |
| Giảng viên | MFA mạnh hơn cho dữ liệu lớp học, step-up khi xuất dữ liệu hoặc thay đổi thông tin quan trọng |
| Quản trị viên | Phương thức chống phishing, recovery kiểm soát chặt, cảnh báo đăng nhập bất thường, quyền tối thiểu |
| Service/workload | Certificate hoặc workload identity, secret ngắn hạn/rotation, quyền API theo service và tenant |

Không nên coi mọi subject có cùng tác động. Tài khoản quản trị có quyền rộng nên cần mức bảo đảm và phản ứng phù hợp hơn, nhưng không được làm recovery trở thành điểm yếu nhất.

## 13. Xây dựng test plan cho credential guessing

Test phải dùng tài khoản và dữ liệu giả trong môi trường được phép. Mục tiêu là kiểm tra **hệ thống có chặn, phát hiện và phục hồi đúng** chứ không phải tối ưu hóa cách đoán mật khẩu.

| Nhóm | Kiểm thử | Kết quả mong đợi |
| --- | --- | --- |
| Rate limit account | Nhiều lần sai trên cùng subject | Delay/challenge/limit theo policy; không lộ trạng thái |
| Rate limit phân tán | Một nhóm nguồn thử cùng account | Kiểm soát kết hợp account và nguồn |
| Password spraying | Một pattern thất bại trên nhiều account | Phát hiện ở cấp tenant/global, không chỉ account |
| Credential stuffing | Credential giả định bị lộ dùng trong test | Tín hiệu bất thường và MFA/step-up theo policy |
| Enumeration | Account tồn tại và không tồn tại | Phản hồi công khai không tiết lộ dễ dàng |
| Offline storage | Kiểm tra cấu hình password verifier và backup | Salt riêng, KDF phù hợp, secret ngoài DB, quyền đọc chặt |
| TOTP guessing | Sai nhiều lần trong một challenge | Giới hạn thử; challenge hết hạn/khóa theo policy |
| TOTP replay | Dùng lại mã đã được chấp nhận trong cùng cửa sổ | Bị từ chối theo chính sách |
| Recovery token | Token hết hạn, sai account, sai purpose hoặc đã dùng | Không được reset password |
| Concurrent recovery | Hai request tiêu thụ cùng token | Chỉ một request thành công |
| MFA enrollment | Phiên chưa đủ assurance cố thêm authenticator | Yêu cầu xác thực lại hoặc từ chối |
| Session invalidation | Password reset sau khi có phiên đáng ngờ | Thu hồi phiên/token theo chính sách |
| Monitoring | Mô phỏng pattern thất bại tăng cao | Có event/alert đủ ngữ cảnh nhưng không chứa secret |
| False positive | Nhiều người hợp lệ chung NAT | Không khóa hàng loạt chỉ vì một tín hiệu |

### 13.1. Ma trận kết quả cần ghi

Với mỗi test, ghi:

- **Precondition:** trạng thái account, tenant, credential và phiên;
- **Input category:** password sai, OTP sai, challenge cũ, token hết hạn... Không ghi bí mật thật;
- **Expected decision:** accept, deny, delay, step-up hoặc require recovery;
- **Rate-limit state:** bucket nào tăng, thời điểm reset, phạm vi áp dụng;
- **Audit event:** có event đúng, đã redaction và correlation ID không;
- **User impact:** người hợp lệ có thể tiếp tục bằng đường an toàn nào;
- **Residual risk:** điều gì chưa được test hoặc phụ thuộc nhà cung cấp bên ngoài.

## 14. Ưu tiên xử lý rủi ro và residual risk

Khi có nhiều điểm yếu, ưu tiên theo **khả năng khai thác, tác động, số lượng tài khoản, mức quyền, mức phơi lộ và độ khó phát hiện/khôi phục**.

| Ưu tiên thường gặp | Vấn đề | Lý do |
| --- | --- | --- |
| Rất cao | Plaintext password hoặc hash yếu, kho verifier/backup truy cập rộng | Có thể tạo rủi ro offline trên diện rộng |
| Rất cao | Recovery cho phép đổi credential mà không có bằng chứng đủ mạnh | Có thể bỏ qua toàn bộ lớp login/MFA |
| Cao | Không rate limit OTP/recovery hoặc có thể dùng lại challenge | Không gian mã ngắn hoặc token một lần bị lạm dụng |
| Cao | Thiếu kiểm soát stuffing/spraying và không giám sát thành công bất thường | Nhiều account có thể bị chiếm mà không có một nguồn request nổi bật |
| Cao | Quản trị viên chỉ dùng password hoặc recovery yếu | Tác động lớn khi một account bị chiếm |
| Trung bình–cao | Enumeration qua phản hồi hoặc timing | Giúp lập danh sách mục tiêu và nhắm guessing |
| Trung bình | Chỉ dựa CAPTCHA hoặc khóa cứng theo account | Dễ bị né hoặc gây DoS cho người dùng hợp lệ |

Đây là thứ tự gợi ý, không thay cho đánh giá cụ thể. Một ứng dụng nội bộ ít tài khoản nhưng có quyền truy cập dữ liệu cực kỳ nhạy cảm có thể cần ưu tiên khác một dịch vụ công khai có hàng triệu người dùng.

Residual risk thường còn ở credential bị tái sử dụng, tài khoản email bị chiếm, thiết bị người dùng nhiễm mã độc, IdP ngoài bị tấn công và quy trình hỗ trợ con người. Ghi rõ phần nào hệ thống tự kiểm soát, phần nào phụ thuộc đối tác hoặc người dùng.

## 15. Checklist threat modeling

Trước khi đưa login/recovery vào production, hãy kiểm tra:

1. **Tài sản:** đã liệt kê account, credential, verifier, recovery, session/token và dữ liệu sau đăng nhập chưa?
2. **Đối thủ:** đã nêu rõ năng lực online, offline, phân tán, thông tin công khai và nội bộ chưa?
3. **Entry point:** login, MFA, recovery, reset, enrollment, SSO và API/service auth đều được xét chưa?
4. **Online/offline:** rate limit và password KDF có được thiết kế riêng theo đúng mối đe dọa không?
5. **Rate limit:** có chiều account, IP/network, tenant, global và challenge; proxy có xác định nguồn tin cậy không?
6. **Enumeration:** body, status, timing, redirect và thông báo có làm lộ tài khoản không?
7. **Verifier:** password hash chậm, salt riêng, pepper tách biệt khi dùng, backup và quyền đọc có an toàn không?
8. **MFA:** OTP có TTL, attempt limit, transaction binding và chống replay; passkey có verify challenge/origin/RP ID không?
9. **Recovery:** token ngẫu nhiên, một lần, đúng purpose/subject, có hạn và không tạo đường vòng MFA không?
10. **Session:** khi reset password hoặc nghi ngờ chiếm account, phiên/token được xử lý thế nào?
11. **Monitoring:** phát hiện spraying/stuffing, thành công sau thất bại, thay đổi credential và enrollment bất thường chưa?
12. **User impact:** biện pháp chống bot có gây khóa nhầm, DoS hoặc cản trở accessibility không?
13. **Incident response:** có quy trình bảo vệ account, thu hồi phiên, thông báo và điều tra không?
14. **Testing:** có test cả tấn công phân tán, cạnh tranh request, false positive và recovery không?

## 16. Bài tập tình huống

Một nền tảng học tập triển khai đăng nhập bằng email và password. Hệ thống có các đặc điểm:

- Rate limit chỉ theo IP, và proxy tin header X-Forwarded-For do client gửi;
- Khóa tài khoản sau ba lần đăng nhập sai;
- Thông báo riêng “email không tồn tại” và “sai mật khẩu”;
- Password verifier dùng SHA-256 không salt;
- TOTP có sáu chữ số nhưng endpoint cho thử không giới hạn;
- Người dùng có thể reset password bằng mã sáu chữ số gửi email, mã không hết hạn và không bị đánh dấu đã dùng;
- Đổi password không thu hồi phiên đang tồn tại.

**Yêu cầu:**

1. Xác định ít nhất **tám điểm yếu** và phân loại online guessing, offline guessing, enumeration, recovery hoặc DoS.
2. Vẽ trust boundary cho browser, proxy, authentication service, verifier store và recovery service.
3. Đề xuất kế hoạch sửa theo thứ tự ưu tiên; nêu vì sao một số thay đổi cần thực hiện trước.
4. Thiết kế lại rate limiting để giảm spraying/stuffing nhưng không khóa hàng loạt người dùng chung NAT.
5. Đề xuất password verifier, MFA và recovery token phù hợp.
6. Viết test case chứng minh reset token hết hạn/đã dùng bị từ chối, TOTP bị giới hạn và password reset xử lý phiên đúng policy.

**Gợi ý đối chiếu:** tin nguồn IP từ proxy được cấu hình; giới hạn đa chiều; phản hồi chống enumeration; dùng Argon2id với salt riêng; giới hạn OTP theo account/challenge; recovery token có entropy cao, purpose binding, TTL và một lần; reset password đánh giá thu hồi session/refresh token; giám sát thành công bất thường và tránh lockout DoS.

## 17. Ghi nhớ

- **Credential guessing có nhiều dạng:** brute force, dictionary, spraying, stuffing, targeted guessing và offline cracking. Không thể dùng một bộ đếm IP để chặn tất cả.
- **Online và offline là hai threat model khác nhau:** rate limit bảo vệ endpoint; password hashing chậm, salt và bảo vệ kho verifier giảm rủi ro khi dữ liệu bị lấy.
- **MFA làm giảm tác động của password bị đoán**, nhưng OTP/recovery vẫn cần giới hạn, thời hạn, ràng buộc giao dịch và chống replay; passkey có lợi thế chống phishing nhờ gắn với RP.
- **Khóa tài khoản cứng có thể trở thành DoS.** Cần cân bằng giữa giảm lạm dụng và khả năng truy cập của người dùng hợp lệ.
- **Recovery là một entry point xác thực**, phải được threat model như login và bảo vệ tương xứng.
- **Monitoring phải nhìn được pattern nhưng không thu bí mật.** Ghi sự kiện đã redaction, kiểm soát quyền truy cập và có quy trình phản ứng.

Một hệ thống chống credential guessing tốt không chỉ làm kẻ tấn công thử khó hơn. Nó còn hạn chế hậu quả khi password đã lộ, bảo vệ các đường MFA/recovery, phát hiện hành vi bất thường và giữ cho người dùng hợp lệ tiếp tục truy cập an toàn.
