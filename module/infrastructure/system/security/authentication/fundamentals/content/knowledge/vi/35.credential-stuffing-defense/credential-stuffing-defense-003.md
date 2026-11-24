# Credential stuffing (Tấn công nhồi nhét thông tin đăng nhập)

> **Chương:** Chống đoán credential  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS — tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Người học biết mô hình hóa ranh giới tin cậy, phòng chống phishing, replay, lạm dụng đăng nhập và thiết kế luồng xác thực an toàn.
>
> **Trọng tâm:** Hiểu cách attacker tự động thử các cặp username/password bị lộ từ dịch vụ khác trên một hệ thống; thiết kế phòng thủ nhiều lớp để giảm khả năng chiếm tài khoản, phát hiện đăng nhập bất thường, bảo vệ recovery và xử lý sự cố mà không khóa nhầm người dùng hợp lệ.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích credential stuffing và phân biệt với brute force, password spraying, phishing và credential replay.
2. Mô tả vòng đời tấn công từ dữ liệu credential bị lộ, tự động hóa thử đăng nhập đến chiếm phiên và khai thác tài khoản.
3. Nhận diện các dấu hiệu ở cấp tài khoản, IP/ASN, thiết bị, endpoint, tenant và chuỗi sự kiện.
4. Thiết kế rate limit nhiều chiều, bot mitigation, challenge và phản hồi đăng nhập an toàn.
5. Đánh giá vai trò và giới hạn của MFA, passkey, password screening và risk-based authentication.
6. Bảo vệ password reset, account recovery, session, refresh token và các đường đăng nhập thay thế.
7. Xây dựng quy trình ứng phó khi phát hiện credential stuffing hoặc tài khoản có dấu hiệu bị chiếm.
8. Thiết kế kiểm thử hiệu quả, đo false positive/negative và bảo vệ dữ liệu telemetry.

## 1. Credential stuffing là gì?

**Credential stuffing (tấn công nhồi nhét thông tin đăng nhập)** là kiểu tấn công trong đó attacker sử dụng các cặp username/password đã bị lộ hoặc đánh cắp từ một dịch vụ để thử đăng nhập vào một dịch vụ khác.

Cuộc tấn công dựa trên thói quen tái sử dụng mật khẩu. Nếu một người dùng dùng cùng mật khẩu ở diễn đàn, cửa hàng trực tuyến và cổng học tập, việc lộ thông tin ở một nơi có thể giúp attacker truy cập các tài khoản còn lại.

Ví dụ:

1. Một dịch vụ bên ngoài bị rò rỉ dữ liệu tài khoản.
2. Attacker thu thập các cặp email/password từ dữ liệu đó.
3. Bot thử những cặp này trên trang đăng nhập của Learning Platform.
4. Một phần nhỏ credential vẫn còn đúng vì người dùng tái sử dụng mật khẩu.
5. Attacker đăng nhập thành công, lấy dữ liệu, thay đổi thông tin khôi phục hoặc tạo phiên duy trì truy cập.

Điểm nguy hiểm là nhiều lần thử có thể là **credential hợp lệ**. Vì vậy, chỉ kiểm tra mật khẩu có đúng hay không không đủ để nhận ra tài khoản đang bị truy cập bởi người khác.

### Tác động

- Chiếm tài khoản (account takeover).
- Truy cập dữ liệu cá nhân, hồ sơ học tập hoặc thông tin thanh toán.
- Thay đổi email/điện thoại khôi phục và khóa chủ tài khoản thật.
- Đăng ký authenticator hoặc passkey mới để duy trì quyền truy cập.
- Lạm dụng tài khoản để gửi spam, lừa đảo hoặc tấn công người khác.
- Dùng một tài khoản bị chiếm làm bàn đạp truy cập dịch vụ liên kết.

Credential stuffing có thể gây thiệt hại ngay cả khi mật khẩu của hệ thống mục tiêu được hash đúng cách. Hashing bảo vệ mật khẩu lưu trữ khi database bị lộ; nó không ngăn attacker thử một mật khẩu hợp lệ mà người dùng đã tái sử dụng.

## 2. Phân biệt các kiểu tấn công đoán và tái sử dụng credential

Các thuật ngữ có liên quan nhưng mô tả hành vi khác nhau:

| Kiểu tấn công | Cách thực hiện | Dấu hiệu thường gặp |
| --- | --- | --- |
| **Credential stuffing** | Thử nhiều cặp username/password đã có từ nguồn rò rỉ. | Nhiều tài khoản, nhiều cặp credential, automation và phân tán IP. |
| **Brute force** | Thử nhiều mật khẩu cho một tài khoản hoặc một nhóm nhỏ tài khoản. | Nhiều lần thử trên cùng username, có thể theo mẫu từ điển. |
| **Password spraying** | Thử một số ít mật khẩu phổ biến trên nhiều tài khoản. | Một mật khẩu hoặc nhóm mật khẩu được thử trên nhiều username. |
| **Phishing** | Lừa người dùng tự nhập credential hoặc phê duyệt đăng nhập. | Trang giả mạo, email/tin nhắn dụ bấm link, thông tin đăng nhập bị gửi cho attacker. |
| **Credential replay** | Phát lại credential, token hoặc bằng chứng đã thu thập được. | Dùng lại dữ liệu xác thực cũ; có thể cần nonce, timestamp hoặc proof-of-possession để ngăn. |

Một chiến dịch có thể kết hợp nhiều kỹ thuật. Ví dụ, attacker dùng credential stuffing để tìm tài khoản có mật khẩu đúng, sau đó phishing hoặc MFA fatigue để vượt qua lớp xác thực bổ sung.

### Vì sao phân biệt quan trọng?

- Brute force thường cần giảm số lần đoán trên một tài khoản.
- Password spraying cần theo dõi số tài khoản khác nhau bị thử từ cùng nguồn.
- Credential stuffing cần phát hiện mẫu đăng nhập phân tán và tỷ lệ thành công bất thường.
- Phishing cần bảo vệ người dùng và ưu tiên phương thức chống phishing.
- Credential replay cần ràng buộc bằng chứng với request, phiên hoặc transaction.

Một bộ đếm thất bại duy nhất cho mỗi IP sẽ bỏ sót chiến dịch phân tán và có thể khóa nhầm người dùng hợp lệ dùng chung NAT.

## 3. Vòng đời của một cuộc credential stuffing

~~~mermaid
flowchart TD
    A["Credential bị lộ ở dịch vụ khác"] --> B["Thu thập và chuẩn hóa danh sách"]
    B --> C["Chia nhỏ username/password"]
    C --> D["Bot thử đăng nhập vào dịch vụ mục tiêu"]
    D --> E{"Kết quả đăng nhập"}
    E -->|"Sai"| F["Thử cặp tiếp theo hoặc đổi nguồn"]
    F --> D
    E -->|"Đúng"| G["Đánh dấu tài khoản có thể chiếm"]
    G --> H["Duy trì phiên và thăm dò tài khoản"]
    H --> I["Đổi recovery, đăng ký authenticator hoặc khai thác dữ liệu"]
    I --> J["Chiếm quyền lâu dài hoặc lạm dụng tài khoản"]
~~~

Các giai đoạn giúp xác định điểm can thiệp:

1. **Nguồn credential:** thông tin có thể đến từ breach dump, malware, phishing hoặc mua bán dữ liệu.
2. **Chuẩn bị:** attacker chuẩn hóa username, loại bản ghi trùng và thử nhiều định dạng.
3. **Tự động hóa:** bot gửi login request qua proxy, residential IP hoặc nhiều thiết bị.
4. **Xác thực:** hệ thống mục tiêu trả kết quả đúng/sai và có thể vô tình tiết lộ trạng thái tài khoản.
5. **Sau đăng nhập:** attacker kiểm tra dữ liệu, thay đổi profile, recovery channel hoặc authenticator.
6. **Duy trì và mở rộng:** tạo session/token, kết nối ứng dụng liên kết hoặc dùng tài khoản làm nguồn tấn công tiếp.

Phòng thủ cần bảo vệ cả trước và sau khi đăng nhập. Chỉ chặn request sai mật khẩu sẽ bỏ qua trường hợp attacker đã tìm được cặp credential đúng.

## 4. Vì sao một dịch vụ có thể bị tấn công dù không bị rò rỉ mật khẩu?

Credential stuffing thường khai thác việc người dùng tái sử dụng mật khẩu, chứ không nhất thiết khai thác lỗi lưu mật khẩu của dịch vụ mục tiêu.

Ví dụ:

- Người dùng đặt cùng mật khẩu cho email cá nhân và tài khoản học tập.
- Dịch vụ bên ngoài bị xâm nhập và lộ cặp email/password.
- Attacker thử cặp đó ở Learning Platform.
- Nếu mật khẩu vẫn được tái sử dụng, đăng nhập có thể thành công.

Ngay cả khi Learning Platform dùng Argon2id hoặc thuật toán password hashing mạnh, attacker vẫn có thể gửi password dạng rõ qua TLS đến login endpoint. Server cần so sánh với password hash và nếu trùng thì xác thực thành công. Thuật toán hash không thể biết mật khẩu đó đã bị lộ ở một dịch vụ khác.

### Hashing vẫn rất quan trọng

Mật khẩu cần được lưu bằng password hashing function chuyên dụng, có salt riêng và cost phù hợp, ví dụ Argon2id theo policy hiện hành. Không lưu plaintext hoặc mã hóa có thể giải ngược để dùng thay hash. Pepper có thể bổ sung lớp bảo vệ nếu được quản lý tách biệt.

Nhưng đây là biện pháp bảo vệ database khi bị lộ. Chống credential stuffing cần thêm kiểm soát tại login, MFA/passkey, screening mật khẩu bị lộ, telemetry và response.

## 5. Phòng thủ nhiều lớp

Không có một biện pháp duy nhất loại bỏ credential stuffing. Một thiết kế thực tế kết hợp:

| Lớp | Kiểm soát | Mục tiêu |
| --- | --- | --- |
| Credential | Mật khẩu riêng, password screening, hash mạnh. | Giảm khả năng credential tái sử dụng và bảo vệ dữ liệu lưu trữ. |
| Authentication | MFA, passkey/WebAuthn, step-up. | Ngăn một password đơn lẻ đủ để chiếm tài khoản. |
| Abuse prevention | Rate limit, bot detection, challenge. | Giảm tự động hóa và tốc độ thử credential. |
| Risk evaluation | Device/network/velocity/account signals. | Phát hiện mẫu bất thường và chọn hành động thích hợp. |
| Session/token | Session rotation, revoke, token lifecycle. | Hạn chế duy trì truy cập sau khi credential bị lạm dụng. |
| Recovery | Recovery proof, notification, cooling-off. | Ngăn attacker dùng recovery để giữ quyền kiểm soát. |
| Monitoring/response | Alert, investigation, incident playbook. | Phát hiện và xử lý tài khoản đã bị truy cập trái phép. |

Các lớp bổ trợ nhau. Ví dụ, MFA làm giảm khả năng đăng nhập bằng password bị lộ, nhưng nếu recovery yếu hoặc có đường đăng nhập legacy bỏ qua MFA thì attacker vẫn có thể vượt qua.

## 6. Rate limiting nhiều chiều

Rate limiting giới hạn tốc độ request để làm chậm automation và giảm số lần thử credential. Cần theo dõi nhiều chiều vì attacker có thể phân tán traffic.

### Các chiều cần theo dõi

| Chiều | Chỉ số ví dụ | Rủi ro cần phát hiện |
| --- | --- | --- |
| Tài khoản | Số lần thất bại theo subject/email trong cửa sổ thời gian. | Brute force, nhắm mục tiêu một tài khoản. |
| IP | Số lần login và số username khác nhau từ IP. | Bot tập trung, password spraying. |
| ASN/network | Số tài khoản và tỷ lệ thất bại theo ASN. | Traffic tập trung từ cloud hoặc mạng có reputation thấp. |
| Thiết bị | Số tài khoản được thử từ device/browser signal. | Automation hoặc device farm. |
| Endpoint | Login, password reset, OTP send, recovery request. | Abuse trên các luồng liên quan. |
| Tenant | Tỷ lệ thất bại và số subject bị nhắm tới. | Chiến dịch tập trung vào một tổ chức. |
| Toàn hệ thống | Tổng request, success ratio, concurrency. | Tấn công phân tán hoặc tăng đột biến diện rộng. |

### Kết hợp cửa sổ thời gian

- Fixed window dễ tổng hợp nhưng có thể tạo burst ở ranh giới hai cửa sổ.
- Sliding window phản ánh tần suất liên tục tốt hơn.
- Token bucket cho phép burst nhỏ trong giới hạn trung bình.
- Progressive delay tăng thời gian chờ khi hành vi đáng ngờ tiếp tục.
- Challenge có thể được yêu cầu khi tín hiệu vượt ngưỡng.

Ngưỡng phải được hiệu chỉnh theo lưu lượng thật, loại tài khoản và endpoint. Ngưỡng quá thấp có thể cản trở lớp học hoặc đợt onboarding có nhiều người đăng nhập cùng lúc.

### Tránh lockout denial of service

Nếu mỗi lần nhập sai đều khóa tài khoản trong thời gian dài, attacker có thể cố tình gửi sai password để khóa hàng nghìn người dùng. Nên kết hợp rate limit theo nguồn, progressive delay, challenge và kiểm soát theo tài khoản.

Có thể tạm hạn chế request đăng nhập mà không chuyển tài khoản sang trạng thái suspended dài hạn. Thông báo cần tránh tiết lộ quá nhiều về việc tài khoản có tồn tại hoặc đang bị nhắm tới.

## 7. Bot mitigation và challenge

Bot mitigation giúp phân biệt hành vi tự động với tương tác người dùng hợp lệ. Các tín hiệu có thể gồm tốc độ request, browser behavior, cookie continuity, TLS/network fingerprint và các challenge được hỗ trợ.

### Các biện pháp thường gặp

- WAF hoặc bot management ở edge.
- Rate limit và concurrency limit.
- Challenge tương tác hoặc proof theo policy.
- Phân tích request sequence và hành vi bất thường.
- Reputation của IP/ASN/device, có TTL và nguồn rõ ràng.
- Phát hiện automation qua mẫu traffic thay vì chỉ dựa vào User-Agent.

### Challenge không phải bằng chứng danh tính

CAPTCHA hoặc challenge thành công chỉ cho thấy request đã vượt qua một bài kiểm tra chống bot nhất định. Nó không chứng minh người gửi là chủ tài khoản và không thay thế password/MFA/passkey.

Challenge có thể gây khó khăn cho người dùng khuyết tật, người dùng công nghệ hỗ trợ hoặc mạng có chất lượng thấp. Cần có phương án thay thế tiếp cận được và theo dõi tỷ lệ challenge thất bại/abandon.

Không dùng một challenge duy nhất làm hàng rào bảo mật cuối cùng. Attacker có thể thuê người giải challenge hoặc dùng dịch vụ tự động hóa.

## 8. MFA và passkey giảm tác động của mật khẩu bị lộ

Credential stuffing thành công ở bước password không nhất thiết phải thành công ở bước xác thực tiếp theo.

### MFA

MFA yêu cầu nhiều yếu tố độc lập theo policy. Khi password bị lộ, attacker vẫn cần yếu tố bổ sung.

Tuy nhiên, mức bảo vệ khác nhau theo phương thức:

- TOTP có thể bị phishing hoặc relay theo thời gian thực.
- SMS OTP chịu rủi ro SIM swap, interception và phishing.
- Push approval có thể bị lạm dụng bằng MFA fatigue nếu người dùng liên tục bị thúc ép phê duyệt.
- Security key hoặc passkey theo WebAuthn có khả năng chống phishing nhờ ràng buộc với RP ID/origin khi triển khai đúng.

MFA cần được áp dụng cho mọi đường đăng nhập quan trọng, gồm web, mobile, API admin, legacy protocol và recovery. Một endpoint phụ bỏ qua MFA có thể trở thành đường vòng cho attacker.

### Passkey và WebAuthn

Passkey dựa trên cặp khóa public/private. Private key được bảo vệ bởi authenticator; server lưu public key và kiểm tra chữ ký challenge. WebAuthn gắn assertion với RP ID và origin, làm cho việc dùng credential trên trang phishing khác khó hơn nhiều so với password/OTP.

Để giảm credential stuffing:

- Ưu tiên passkey làm phương thức đăng nhập chính khi sản phẩm hỗ trợ.
- Yêu cầu user verification theo policy cho thao tác nhạy cảm.
- Bảo vệ đăng ký, thay thế và xóa passkey bằng step-up.
- Không để password fallback yếu hơn phá vỡ chính sách chống phishing.
- Có quy trình mất thiết bị và recovery an toàn.

Passkey không có nghĩa tài khoản không thể bị chiếm: attacker vẫn có thể lạm dụng recovery, thiết bị đã bị compromise, session cookie bị đánh cắp hoặc tài khoản hỗ trợ bị chiếm.

## 9. Kiểm tra mật khẩu đã bị lộ

Một biện pháp phòng ngừa là từ chối mật khẩu mới nếu nó xuất hiện trong danh sách mật khẩu phổ biến hoặc dữ liệu breach đã biết.

### Khi nào nên kiểm tra?

- Khi người dùng tạo tài khoản.
- Khi đặt hoặc đổi mật khẩu.
- Khi reset password sau sự cố.
- Trong chiến dịch rà soát credential theo policy, với quy trình bảo vệ quyền riêng tư.

### Cách triển khai

- Ưu tiên corpus nội bộ được quản lý hoặc dịch vụ kiểm tra có cơ chế bảo vệ dữ liệu.
- Có thể dùng giao thức k-anonymity: client gửi một phần prefix của hash tới dịch vụ, sau đó so sánh phần suffix ở phía client. Không gửi password nguyên văn cho bên thứ ba.
- Dùng TLS, giới hạn log và không lưu password hoặc hash đầy đủ trong telemetry.
- Đánh giá nguồn, thời điểm cập nhật và độ bao phủ của breach corpus.
- Nếu dịch vụ kiểm tra ngoài không khả dụng, áp dụng fallback đã định nghĩa; không âm thầm coi mọi password là an toàn.

### Không nên làm

- Gửi plaintext password tới analytics hoặc log.
- Gửi password nguyên vẹn tới một dịch vụ không được phê duyệt.
- Tự động ép người dùng đổi mật khẩu định kỳ vô lý mà không có bằng chứng hoặc yêu cầu policy.
- Từ chối password chỉ vì nó có trong danh sách phổ biến nhưng không giải thích cách tạo password mạnh hơn.
- Dùng breach corpus như bằng chứng rằng một tài khoản chắc chắn bị chiếm.

Password screening giúp giảm việc chọn mật khẩu đã biết là yếu hoặc bị lộ. Nó không thay thế MFA, rate limit và monitoring.

## 10. Bảo vệ login endpoint và phản hồi lỗi

Login endpoint là nơi attacker có thể thử hàng loạt cặp credential. Phản hồi cần hạn chế account enumeration và không tiết lộ thông tin nội bộ.

### Phản hồi nhất quán

Với thông tin đăng nhập không hợp lệ, tránh phân biệt rõ:

- Username không tồn tại.
- Username tồn tại nhưng password sai.
- Tài khoản bị khóa.
- Tài khoản bị suspend.
- Tài khoản chưa kích hoạt.

Thông báo có thể dùng câu chung như “Thông tin đăng nhập không hợp lệ hoặc tài khoản hiện không thể đăng nhập.” Tuy nhiên, người dùng hợp lệ cần có kênh hỗ trợ sau khi xác minh danh tính.

### Timing và side channel

- Tránh thời gian phản hồi khác biệt quá rõ giữa username tồn tại và không tồn tại.
- Không trả stack trace, SQL error hoặc chi tiết credential policy.
- Không đưa username/email nguyên vẹn vào log không được bảo vệ.
- Giới hạn response size và request concurrency.
- Dùng TLS và bảo vệ cookie/session.
- Chống CSRF theo kiến trúc ứng dụng.

Phản hồi đồng nhất không có nghĩa mọi trường hợp phải có cùng HTTP status nếu điều đó phá vỡ giao thức; cần cân bằng an toàn, khả năng vận hành và trải nghiệm.

### Không khóa tài khoản chỉ dựa vào một nguồn

Kết hợp nhiều chiều và tránh khóa vĩnh viễn do failed attempts. Có thể tăng challenge hoặc tạm delay trước khi yêu cầu quy trình recovery.

## 11. Phát hiện credential stuffing qua telemetry

Một chiến dịch thường tạo ra mẫu ở cấp hệ thống, không chỉ ở một tài khoản.

### Các chỉ số quan trọng

| Chỉ số | Ý nghĩa | Tín hiệu bất thường |
| --- | --- | --- |
| Failed login rate | Tỷ lệ đăng nhập thất bại. | Tăng nhanh so với baseline. |
| Success-after-failure | Đăng nhập thành công sau nhiều lần thử. | Có thể là credential đúng được tìm thấy. |
| Distinct accounts per source | Số tài khoản khác nhau từ IP/ASN/device. | Một nguồn thử nhiều username. |
| Sources per account | Số IP/ASN/device thử cùng tài khoản. | Tấn công phân tán vào một subject. |
| Credential reuse signal | Cặp credential bị thử hoặc được phát hiện trong breach corpus. | Có thể liên quan tới dữ liệu lộ. |
| Post-login changes | Đổi recovery, thêm authenticator, tạo API key. | Hành vi sau login đáng ngờ. |
| Session anomalies | Nhiều session mới, vị trí/device thay đổi. | Có thể là account takeover hoặc token theft. |
| MFA challenge outcomes | Challenge được gửi, từ chối, timeout hoặc phê duyệt. | MFA fatigue hoặc lạm dụng fallback. |

### Correlate trước và sau login

Một tài khoản đăng nhập thành công sau nhiều lần thử từ nhiều nguồn có thể đáng chú ý hơn một login thành công bình thường. Sau login, hãy theo dõi các thay đổi nhạy cảm như email khôi phục, số điện thoại, passkey, MFA, API key, quyền và thiết bị tin cậy.

Không nên chỉ theo dõi thất bại. Credential stuffing tìm cách đạt thành công; sự kiện thành công bất thường là một phần quan trọng của phát hiện.

### Telemetry an toàn

- Dùng account identifier đã pseudonymize hoặc keyed hash cho phân tích.
- Không ghi password, OTP, recovery code, cookie hoặc token.
- Hạn chế truy cập IP/device signals và đặt retention phù hợp.
- Ghi policy/model version để giải thích quyết định.
- Bảo vệ audit khỏi sửa/xóa trái phép.
- Đồng bộ thời gian để tương quan sự kiện giữa dịch vụ.

## 12. Risk-based authentication và adaptive response

Risk-based authentication (RBA) kết hợp tín hiệu về thiết bị, mạng, vị trí, hành vi, velocity và authentication context để điều chỉnh mức kiểm tra.

Ví dụ:

- Login từ thiết bị đã đăng ký, passkey hợp lệ và không có tín hiệu abuse: có thể cho phép theo policy.
- Nhiều username được thử từ cùng nguồn, tốc độ cao: rate limit hoặc challenge.
- Một account có login thành công bất thường rồi yêu cầu đổi email khôi phục: step-up hoặc hold hành động.
- Session cũ dùng để thay đổi authenticator: yêu cầu xác thực mới, có thể bằng phương thức chống phishing.

### Không nhầm risk score với assurance

- **Risk score** đánh giá request có bất thường hoặc nguy cơ lạm dụng hay không.
- **Authentication assurance** mô tả mức bằng chứng xác thực đã đạt.
- **Authorization** quyết định subject được làm gì trên resource cụ thể.

Một risk score thấp không thể làm cho token sai chữ ký trở nên hợp lệ. Một passkey assertion mạnh cũng không tự cấp quyền quản trị. Policy cần kiểm tra từng lớp theo thứ tự.

### Hành động thích hợp

| Tình huống | Hành động có thể chọn |
| --- | --- |
| Một vài thất bại rải rác, không có tín hiệu khác | Monitor, không gây gián đoạn quá mức. |
| Tốc độ thử cao từ một nguồn | Rate limit hoặc challenge. |
| Nhiều tài khoản bị thử từ nhiều nguồn | Phân tích theo ASN/device/tenant, bot mitigation và adaptive challenge. |
| Password đúng nhưng device/context bất thường | Step-up chống phishing và theo dõi sau login. |
| Token/session không hợp lệ hoặc đã revoke | Deny. |
| Có dấu hiệu account takeover đủ mạnh | Revoke session/token, bảo vệ recovery và mở incident workflow. |

## 13. Bảo vệ password reset và account recovery

Sau khi password bị lộ, attacker có thể thử reset password hoặc chiếm kênh recovery. Một login endpoint mạnh nhưng recovery yếu vẫn dễ bị bypass.

### Các kiểm soát cần có

- Response không tiết lộ email/username có tồn tại hay không.
- Recovery token ngẫu nhiên, đủ entropy, thời hạn ngắn và dùng một lần.
- Token được ràng buộc với đúng account và mục đích; không dùng chung cho login hoặc đổi email.
- Thay đổi recovery channel cần xác thực lại hoặc quy trình chứng minh quyền kiểm soát phù hợp.
- Thông báo qua kênh đã đăng ký trước khi thay đổi có hiệu lực nếu policy yêu cầu.
- Có rate limit riêng cho reset request, OTP send và verification attempts.
- Không cho recovery bypass suspension hoặc account hold đang hiệu lực.
- Sau recovery, thu hồi session/token cũ theo policy và đánh giá lại authenticator.

### Sau khi password bị xác định là compromised

Có thể yêu cầu người dùng đổi password, nhưng cần xác minh trước khi ép reset để tránh attacker dùng quy trình này khóa chủ tài khoản. Khi reset thành công:

1. Lưu sự kiện credential change.
2. Thu hồi hoặc rotate session/refresh token theo policy.
3. Kiểm tra authenticator và recovery channel vừa thay đổi.
4. Gửi thông báo bảo mật qua kênh đáng tin cậy.
5. Yêu cầu step-up trước thao tác nhạy cảm nếu có rủi ro còn lại.

Không gửi password mới qua email hoặc chat. Người dùng phải tự tạo secret mới qua kênh bảo mật.

## 14. Xử lý sau khi phát hiện đăng nhập có thể bị chiếm

Phát hiện một cặp credential bị sử dụng thành công cần một quy trình response rõ ràng.

### Quy trình ứng phó gợi ý

1. **Triage:** xác định account, tenant, thời gian, nguồn, endpoint và các sự kiện liên quan.
2. **Contain:** hạn chế hành động rủi ro, revoke session hoặc refresh token nghi ngờ và chặn automation theo nguồn phù hợp.
3. **Verify:** xác minh với chủ tài khoản qua kênh đã đăng ký trước, không dựa vào email/phone vừa bị thay.
4. **Recover:** yêu cầu đổi credential bị lộ, thu hồi authenticator không nhận diện và khôi phục recovery channel.
5. **Revoke:** kết thúc session, token và grant liên quan theo phạm vi sự cố.
6. **Review:** kiểm tra thay đổi dữ liệu, quyền, API key, passkey, thiết bị và hoạt động sau login.
7. **Notify:** thông báo rõ sự kiện, bước người dùng cần làm và kênh hỗ trợ.
8. **Learn:** cập nhật rule, threshold, breach screening và test cases dựa trên kết quả điều tra.

### Không phản ứng quá mức

Không nên tự động suspend hàng loạt mọi tài khoản có login thất bại. Credential stuffing có thể thử credential của nạn nhân mà không chứng minh tài khoản đã bị chiếm. Phân biệt:

- Account targeted: tài khoản nằm trong danh sách bị thử.
- Authentication failed: chưa có bằng chứng attacker đăng nhập thành công.
- Authentication succeeded under suspicious context: cần điều tra thêm.
- Confirmed takeover: có bằng chứng truy cập trái phép hoặc thay đổi do attacker thực hiện.

Mức response phải phù hợp bằng chứng và tác động.

## 15. Kiến trúc phòng thủ cho login service

~~~mermaid
flowchart TD
    R["Login request"] --> E["Edge / WAF / bot controls"]
    E --> L["Login service"]
    L --> V["Validate input and account policy"]
    V --> C["Credential verifier"]
    C --> S["Signal collector"]
    S --> D["Device / network / velocity / history"]
    S --> A["Authentication context"]
    D --> P["Risk and policy engine"]
    A --> P
    C --> P
    P --> Q{"Decision"}
    Q -->|"Deny"| X["Reject safely"]
    Q -->|"Rate limit / challenge"| H["Throttle or challenge"]
    Q -->|"Step-up"| U["MFA / passkey verification"]
    Q -->|"Allow"| T["Create rotated session"]
    U --> W["Verify new evidence"]
    W --> P
    T --> M["Session and token controls"]
    M --> O["Audit and monitoring"]
    H --> O
    X --> O
~~~

### Trình tự xử lý tham khảo

1. Edge kiểm tra TLS, request size, bot signals và giới hạn tổng thể.
2. Login service chuẩn hóa identifier và áp dụng rate limit nhiều chiều.
3. Credential verifier kiểm tra password hash hoặc phương thức đã đăng ký.
4. Hệ thống đánh giá account status, credential state và authentication context.
5. Risk engine kết hợp signal theo source/freshness/provenance.
6. Policy chọn allow, challenge, step-up, hold hoặc deny.
7. Nếu thành công, server xoay session ID và cấp session/token theo policy.
8. Ghi audit event đã loại bỏ secret và kích hoạt monitoring sau login.

Không để risk engine bỏ qua lỗi credential, chữ ký hoặc account status. Challenge cũng không thay thế bước xác minh credential.

## 16. Ví dụ thực tế: Learning Platform

Learning Platform phục vụ học viên, giảng viên và nhân viên hỗ trợ. Một dịch vụ thương mại điện tử bên ngoài bị lộ dữ liệu, trong đó có một số email được dùng tại nền tảng học tập.

### Đợt tấn công

- Bot gửi nhiều login request với email/password đã bị lộ.
- Traffic được phân tán qua nhiều IP.
- Một số request thất bại; một số cặp password vẫn đúng do tái sử dụng.
- Các tài khoản đăng nhập thành công bắt đầu truy cập hồ sơ, đổi recovery email và thêm thiết bị.

### Phòng thủ

1. Edge phát hiện velocity và số lượng account khác nhau theo IP/ASN/device.
2. Login service áp rate limit theo account và nhiều chiều khác.
3. Tài khoản có password đúng nhưng context bất thường phải step-up.
4. Passkey được ưu tiên cho các thao tác nhạy cảm; password fallback không được bỏ qua policy.
5. Hành động đổi recovery hoặc thêm authenticator yêu cầu xác thực mới và thông báo qua kênh cũ.
6. Monitoring phát hiện success-after-failure và thay đổi account sau login.
7. Security team revoke session/token của các tài khoản có bằng chứng bị chiếm, hỗ trợ reset credential và điều tra dữ liệu bị truy cập.

### Kết quả mong đợi

- Bot traffic bị làm chậm hoặc challenge.
- Password bị lộ không đủ để vượt qua xác thực mạnh.
- Recovery không trở thành đường bypass.
- Tài khoản bị chiếm được cô lập và khôi phục.
- Người dùng hợp lệ đổi mạng hoặc thiết bị không bị khóa tự động chỉ vì một signal lạ.

## 17. Kiểm thử credential stuffing defense

| Kịch bản | Cách kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| Một tài khoản bị thử nhiều password | Gửi nhiều lần thất bại trong cửa sổ ngắn. | Rate limit/progressive delay theo account; không lockout dài hạn dễ bị DoS. |
| Một IP thử nhiều tài khoản | Dùng nhiều username trong môi trường test. | Phát hiện distinct-account velocity và áp bot controls. |
| Distributed credential stuffing | Phân tán request qua nhiều IP/ASN. | Phát hiện qua account/device/tenant/global patterns, không chỉ IP. |
| Credential đúng từ thiết bị lạ | Dùng password hợp lệ nhưng device/context mới. | Step-up hoặc policy challenge trước khi cấp phiên. |
| MFA không hoàn tất | Password đúng nhưng OTP/passkey challenge thất bại. | Không tạo authenticated session. |
| Passkey assertion sai origin | Dùng assertion không khớp RP ID/origin. | Từ chối. |
| Legacy login bypass | Thử giao thức/endpoint phụ không áp MFA. | Mọi đường truy cập được bảo vệ cùng policy hoặc bị tắt. |
| Breached password khi đăng ký | Chọn password có trong corpus kiểm tra. | Từ chối hoặc yêu cầu chọn secret khác theo policy. |
| Breach-check provider unavailable | Làm provider timeout trong test. | Fallback được định nghĩa; không log hoặc gửi plaintext password. |
| Account enumeration | So sánh phản hồi username không tồn tại và password sai. | Không tiết lộ trạng thái tài khoản qua response/timing rõ ràng. |
| Reset enumeration | Thử reset cho email có và không có. | Phản hồi bên ngoài nhất quán. |
| Recovery token replay | Dùng token reset đã sử dụng. | Từ chối lần dùng lại. |
| Recovery bypass suspension | Thử recovery khi account bị suspended. | Không vượt qua trạng thái suspension. |
| MFA fatigue | Gửi nhiều push request. | Có rate limit, context và thông báo; không coi approve liên tục là mặc nhiên an toàn. |
| Success-after-failure | Tạo chuỗi thất bại rồi đăng nhập thành công bất thường. | Sinh signal và kiểm tra hành vi sau login. |
| Post-login account change | Thử đổi email, thêm passkey hoặc tạo API key ngay sau login rủi ro. | Step-up, hold hoặc review theo policy. |
| Session fixation | Giữ session ID trước login. | Session ID được xoay sau xác thực thành công. |
| Token/session revocation | Revoke session/token sau khi xác nhận takeover. | Request tiếp theo bị từ chối trong SLA. |
| Trusted proxy headers | Gửi X-Forwarded-For giả từ client. | Chỉ tin header từ proxy đã cấu hình. |
| Shared NAT | Nhiều người dùng hợp lệ cùng IP. | Không khóa hàng loạt; policy kết hợp nhiều chiều. |
| Monitoring privacy | Kiểm tra log và telemetry. | Không lưu password, OTP, cookie, token hoặc recovery secret. |

## 18. Checklist triển khai

- [ ] Đã phân biệt credential stuffing với brute force, password spraying, phishing và replay.
- [ ] Mật khẩu được lưu bằng password hashing function chuyên dụng, salt riêng và cost phù hợp.
- [ ] Có password screening khi tạo/đổi password với quy trình bảo vệ dữ liệu.
- [ ] Không gửi plaintext password hoặc secret tới log/analytics.
- [ ] Rate limit theo account, IP, ASN, device, endpoint, tenant và toàn hệ thống khi phù hợp.
- [ ] Có progressive delay/challenge và chống lockout denial of service.
- [ ] Bot mitigation không được coi là bằng chứng danh tính.
- [ ] MFA được áp dụng cho mọi đường đăng nhập quan trọng.
- [ ] Ưu tiên passkey/WebAuthn và bảo vệ password fallback.
- [ ] Có kiểm soát cho legacy protocol, mobile/API và service account.
- [ ] Login/reset/recovery response hạn chế account enumeration.
- [ ] Recovery token có entropy, expiry, one-time use và đúng mục đích.
- [ ] Thay đổi recovery/authenticator cần xác thực và notification phù hợp.
- [ ] Session ID được xoay; session/refresh token có cơ chế revoke.
- [ ] Telemetry theo dõi failed attempts, success-after-failure và post-login changes.
- [ ] Risk score được phân biệt với authentication assurance và authorization.
- [ ] Có incident playbook để triage, contain, verify, recover, revoke và notify.
- [ ] Có đo false positive/negative, challenge rate và tác động tới người dùng.
- [ ] Log, retention và access control bảo vệ privacy.
- [ ] Có test distributed traffic, shared NAT, recovery, legacy bypass và token revocation.

## 19. Tự kiểm tra

**Câu 1.** Credential stuffing khác brute force ở điểm nào?

**Đáp án:** Credential stuffing dùng các cặp username/password đã bị lộ từ nơi khác; brute force thử nhiều mật khẩu để tìm mật khẩu đúng. Credential stuffing thường có tỷ lệ request hợp lệ thấp nhưng một phần có thể đăng nhập thành công.

**Câu 2.** Vì sao password hashing mạnh không ngăn credential stuffing?

**Đáp án:** Attacker gửi password bị lộ tới login endpoint. Server hash và so sánh như với một đăng nhập bình thường; password đúng vẫn được chấp nhận nếu không có kiểm soát bổ sung.

**Câu 3.** Chỉ rate limit theo IP có đủ không?

**Đáp án:** Không. Attacker có thể phân tán IP, còn người dùng hợp lệ có thể chia sẻ NAT. Cần kết hợp account, IP/ASN, device, endpoint, tenant và toàn hệ thống.

**Câu 4.** Vì sao lockout dài hạn sau vài lần nhập sai có thể nguy hiểm?

**Đáp án:** Attacker có thể cố tình nhập sai để khóa tài khoản nạn nhân, tạo denial of service. Nên kết hợp rate limit, delay, challenge và recovery có kiểm soát.

**Câu 5.** CAPTCHA có chứng minh người gửi request là chủ tài khoản không?

**Đáp án:** Không. Challenge chỉ giúp đánh giá hoặc làm chậm automation; vẫn cần xác minh credential và authentication context.

**Câu 6.** MFA có loại bỏ hoàn toàn credential stuffing không?

**Đáp án:** Không. MFA giảm khả năng password bị lộ đủ để đăng nhập, nhưng phishing, MFA fatigue, recovery yếu, legacy endpoint và session theft vẫn có thể bị khai thác.

**Câu 7.** Vì sao passkey có lợi thế trước phishing?

**Đáp án:** WebAuthn ràng buộc assertion với RP ID/origin và private key được authenticator bảo vệ. Trang giả mạo khác origin khó yêu cầu chữ ký có thể dùng tại RP thật.

**Câu 8.** Password screening nên gửi password nguyên văn tới dịch vụ bên ngoài không?

**Đáp án:** Không. Dùng corpus nội bộ hoặc cơ chế privacy-preserving như k-anonymity, và không ghi password/hash đầy đủ vào telemetry.

**Câu 9.** Một login thành công sau nhiều lần thất bại có nên tự động chứng minh account takeover không?

**Đáp án:** Không. Đây là tín hiệu cần điều tra kết hợp device, network, authentication context và hành vi sau login. Không nên tự động khóa tài khoản chỉ dựa vào một mẫu.

**Câu 10.** Sau khi xác nhận account takeover, chỉ yêu cầu đổi password đã đủ chưa?

**Đáp án:** Chưa. Cần revoke session/token liên quan, kiểm tra và thu hồi authenticator/recovery channel bị thay đổi, xem xét hoạt động sau login, thông báo người dùng và tạo phiên mới sau recovery.

## Ghi nhớ

**Credential stuffing** khai thác việc tái sử dụng username/password bị lộ từ một dịch vụ khác. Password hashing bảo vệ dữ liệu lưu trữ nhưng không ngăn attacker thử một cặp credential hợp lệ tại login endpoint. Phòng thủ cần kết hợp rate limit nhiều chiều, bot mitigation, password screening, MFA/passkey, risk-based authentication, bảo vệ recovery và monitoring cả trước lẫn sau login.

Không khóa tài khoản dài hạn chỉ dựa trên số lần thất bại, không coi CAPTCHA/IP/device fingerprint là bằng chứng danh tính và không để recovery hoặc legacy endpoint bỏ qua MFA. Khi có dấu hiệu takeover, hãy xác minh, revoke session/token, xử lý credential và authenticator, bảo vệ kênh recovery, điều tra thay đổi sau login và thông báo qua kênh tin cậy. **Mục tiêu là làm cho credential bị lộ không đủ để chiếm tài khoản, đồng thời giữ đường đăng nhập và khôi phục an toàn cho người dùng hợp lệ.**
