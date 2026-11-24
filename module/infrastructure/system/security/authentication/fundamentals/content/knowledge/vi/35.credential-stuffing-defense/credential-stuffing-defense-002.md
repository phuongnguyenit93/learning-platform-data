# Password spraying — Phát hiện và phòng chống tấn công rải mật khẩu

Một tổ chức có vài nghìn tài khoản nhân viên. Kẻ tấn công biết danh sách email công khai và thử cùng một mật khẩu phổ biến hoặc một biến thể theo mùa trên nhiều tài khoản. Thay vì thử hàng trăm mật khẩu trên một tài khoản, attacker chỉ thử một hoặc hai mật khẩu trên mỗi tài khoản rồi đổi IP, thiết bị hoặc khoảng thời gian. Cách làm này có thể tránh ngưỡng khóa account đơn giản, nhưng vẫn tạo ra mẫu thất bại bất thường khi nhìn trên toàn hệ thống.

**Password spraying** là kiểu tấn công đoán mật khẩu trong đó attacker thử một số lượng nhỏ mật khẩu trên nhiều tài khoản khác nhau. Mục tiêu là tìm một tài khoản có mật khẩu yếu hoặc mặc định trong khi giữ số lần thử trên từng tài khoản ở mức thấp. Đây là dạng password guessing có tính phân tán; nó khác brute force tập trung vào một account và khác credential stuffing sử dụng cặp username/password đã bị lộ từ dịch vụ khác.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, bài học này giúp người học hiểu hành vi password spraying, phân biệt nó với các kiểu tấn công credential khác, thiết kế telemetry và phát hiện đa chiều, giảm thiểu mà không gây khóa nhầm hàng loạt, và xử lý sự cố sau khi có dấu hiệu compromise. Trọng tâm là phối hợp password policy, rate limiting, MFA chống phishing, passkey, kiểm soát giao thức cũ, bảo vệ session và quy trình phản ứng.

## 1. Password spraying là gì?

Trong password spraying, attacker thường có danh sách account và một tập nhỏ mật khẩu phỏng đoán. Họ thử từng mật khẩu trên nhiều account trước khi chuyển sang mật khẩu tiếp theo. Ví dụ minh họa:

~~~text
Account A: password candidate 1 -> fail
Account B: password candidate 1 -> fail
Account C: password candidate 1 -> success
Account D: password candidate 1 -> fail
...
Sau một khoảng nghỉ:
Account A: password candidate 2 -> fail
Account B: password candidate 2 -> fail
...
~~~

Kẻ tấn công cố giữ số lần thử trên mỗi account thấp để tránh quy tắc như “khóa sau 5 lần sai”. Nhưng tổng số lần thất bại trên tenant, domain, ứng dụng hoặc hệ thống có thể rất lớn. Một vài account có thể bị đăng nhập thành công nếu người dùng chọn mật khẩu phổ biến, mật khẩu mặc định hoặc mật khẩu bị tái sử dụng.

### 1.1. Phân biệt các kiểu tấn công

| Kiểu tấn công | Dữ liệu attacker dùng | Mẫu hành vi điển hình | Kiểm soát trọng tâm |
| --- | --- | --- | --- |
| **Brute force** | Nhiều mật khẩu cho một account hoặc một tập nhỏ account | Nhiều lần thử liên tiếp vào cùng một định danh | Throttle theo account, delay, MFA, password verifier mạnh |
| **Password spraying** | Một vài mật khẩu trên nhiều account | Mỗi account ít lần sai, nhưng nhiều account cùng bị thử | Phát hiện theo tenant/global, phân tích candidate và nguồn phân tán |
| **Credential stuffing** | Cặp username/password đã bị lộ từ nơi khác | Nhiều cặp credential khác nhau được thử trên dịch vụ đích | MFA, phát hiện credential reuse, bot controls, risk-based authentication |
| **Password guessing** | Mật khẩu dự đoán từ thông tin người dùng hoặc quy tắc | Có thể nhắm một người hoặc nhiều người | Mật khẩu dài, blocklist, MFA, giảm thông tin công khai |
| **Default credential abuse** | Mật khẩu mặc định hoặc credential chưa đổi | Tập trung vào thiết bị, ứng dụng hoặc account mới cài | Buộc đổi mặc định, unique secret, inventory và hardening |

Các kỹ thuật có thể kết hợp. Một chiến dịch có thể bắt đầu bằng password spraying, sau đó dùng credential hợp lệ vừa tìm được để truy cập email, VPN hoặc cloud console. Vì thế, phát hiện một lần đăng nhập thành công sau chuỗi thất bại có thể quan trọng hơn việc chỉ đếm số lần sai.

### 1.2. Vì sao password spraying có hiệu quả?

- Nhiều người dùng chọn mật khẩu ngắn, dễ đoán hoặc biến thể theo mùa.
- Mật khẩu bị tái sử dụng giữa tài khoản cá nhân và tài khoản công việc.
- Account cũ hoặc account dịch vụ chưa được quản lý đúng.
- Một số giao thức cũ không hỗ trợ MFA hoặc không đi qua chính sách đăng nhập hiện đại.
- Quy tắc khóa account chỉ nhìn từng account, không nhìn toàn tenant.
- Attacker phân tán request qua nhiều IP, proxy, thiết bị hoặc khoảng thời gian.
- Tổ chức có nhiều ứng dụng và cổng đăng nhập với policy không đồng nhất.

Không nên giả định mọi chiến dịch đều dùng một mật khẩu duy nhất hoặc cùng một IP. Mẫu thực tế có thể chậm, phân tán và thay đổi để né detection.

## 2. Mô hình tấn công và bề mặt cần bảo vệ

Password spraying thường nhắm vào các endpoint nhận password hoặc giao thức có thể xác thực bằng password:

- Web login, mobile login và API authentication.
- VPN, remote access gateway và virtual desktop.
- Email, webmail, legacy mail protocols và collaboration tools.
- Identity provider, federation gateway và enterprise SSO.
- SSH, bastion, remote administration và các hệ thống quản trị.
- Ứng dụng nội bộ có local account hoặc password database riêng.
- Tài khoản dịch vụ, automation account và credential mặc định.

### 2.1. Chuỗi tác động

~~~mermaid
flowchart TD
    A[Thu thập danh sách account] --> B[Chọn một số password candidate]
    B --> C[Phân tán request qua account / nguồn / thời gian]
    C --> D{Có account xác thực thành công?}
    D -->|Không| E[Đổi candidate hoặc tiếp tục chiến dịch]
    E --> C
    D -->|Có| F[Chiếm phiên đăng nhập]
    F --> G[Thử truy cập email / VPN / ứng dụng khác]
    G --> H[Đánh cắp dữ liệu hoặc leo thang quyền]
    H --> I[Persistence / abuse / lateral movement]
~~~

Mỗi bước tạo ra cơ hội phát hiện:

1. Nhiều account bị thử trong cùng một khoảng thời gian.
2. Tỷ lệ thất bại tăng bất thường theo ứng dụng hoặc tenant.
3. Một số account nhận thất bại từ nhiều mạng hoặc thiết bị.
4. Một account thành công sau khi nhiều account khác thất bại từ cùng cụm tín hiệu.
5. Đăng nhập thành công từ nguồn mới, thiết bị lạ hoặc vị trí bất thường.
6. Sau đăng nhập, có hoạt động tạo forwarding rule, thêm MFA factor, truy cập dữ liệu hàng loạt hoặc tạo token.

### 2.2. Password spraying không chỉ là vấn đề của login form

Một hệ thống có thể có nhiều đường xác thực song song. Nếu web SSO yêu cầu MFA nhưng một giao thức cũ hoặc endpoint quản trị vẫn chấp nhận password đơn lẻ, attacker có thể chọn đường yếu nhất. Cần lập inventory các phương thức xác thực, account, tenant, ứng dụng và giao thức; mọi endpoint password phải được bao phủ bởi policy và telemetry.

## 3. Phát hiện: nhìn theo nhiều chiều

Một bộ đếm số lần sai trên từng account là không đủ. Password spraying được nhận diện tốt hơn khi tương quan sự kiện theo account, nguồn, tenant, ứng dụng, thời gian và kết quả.

### 3.1. Tín hiệu chính

| Tín hiệu | Vì sao hữu ích | Giới hạn cần nhớ |
| --- | --- | --- |
| Nhiều account khác nhau có login failure trong cửa sổ ngắn | Thể hiện hành vi thử rộng | Sự kiện nội bộ như đợt đổi mật khẩu cũng có thể tạo spike |
| Số lần thử trên mỗi account thấp nhưng tổng số account cao | Phù hợp mô hình spraying | Attacker có thể làm chậm hoặc chia chiến dịch |
| Một IP/ASN/device thử nhiều account | Có thể chỉ ra automation hoặc nguồn chung | NAT, proxy doanh nghiệp và carrier có thể dùng chung |
| Nhiều IP cùng thử các account trong một tenant | Gợi ý chiến dịch phân tán | Có thể là người dùng roaming hoặc hệ thống kiểm thử |
| Cùng một khoảng thời gian, nhiều account nhận cùng loại failure | Cho thấy candidate hoặc automation chung | Không nên suy ra mật khẩu được thử từ log nếu không có dữ liệu an toàn |
| Một account success sau chuỗi failure | Có thể là credential bị đoán trúng | Người dùng hợp lệ cũng có thể nhập sai rồi đăng nhập thành công |
| Login success từ device/ASN mới sau nhiều failure | Tăng độ nghi ngờ khi kết hợp tín hiệu | IP/device mới đơn lẻ không chứng minh compromise |
| Legacy authentication failure spike | Phát hiện đường password yếu hoặc không có MFA | Cần tách theo ứng dụng và giao thức |
| MFA push bất thường sau password success | Có thể là attacker đã biết password và đang thử MFA | Người dùng hợp lệ cũng có thể đăng nhập trên thiết bị mới |
| Nhiều account được thử theo danh sách có cấu trúc | Gợi ý account enumeration/spraying | Danh sách nhân viên hoặc batch job có thể tạo mẫu tương tự |

### 3.2. Cửa sổ thời gian và tổng hợp

Phân tích nhiều cửa sổ cùng lúc:

- Ngắn: vài phút để phát hiện burst.
- Trung bình: một đến vài giờ để phát hiện spraying có nhịp chậm.
- Dài: một ngày hoặc nhiều ngày để thấy low-and-slow campaign.

Không chỉ đếm số request. Nên theo dõi:

- Số account duy nhất bị thử.
- Số failure trên mỗi account.
- Số nguồn mạng, ASN, device hoặc client duy nhất.
- Tỷ lệ failure/success theo tenant và endpoint.
- Mức phân tán thời gian giữa các request.
- Tỷ lệ account mới hoặc account đặc quyền bị nhắm tới.
- Kết quả login success và hành động sau login.

Một heuristic minh họa có thể là: trong 10 phút, một tenant có nhiều account duy nhất nhận failure, phần lớn mỗi account chỉ có một hoặc hai lần thử, và các request đến từ một hoặc nhiều nguồn có đặc điểm tương tự. Đây là tín hiệu để điều tra hoặc áp dụng kiểm soát thích ứng, không phải ngưỡng chuẩn dùng cho mọi tổ chức.

### 3.3. Phân biệt tín hiệu theo account và theo nguồn

**Theo account:**

- Số lần password failure trong nhiều cửa sổ.
- Số IP/ASN/device khác nhau đã thử account.
- Login success sau failure.
- Account privilege, trạng thái, phương thức MFA và lịch sử thiết bị.
- Thay đổi mật khẩu, recovery hoặc MFA gần đây.

**Theo nguồn:**

- Số account duy nhất được thử.
- Tỷ lệ lỗi trên tổng request.
- Tần suất đổi account/identifier.
- User-agent/client fingerprint và dấu hiệu automation.
- ASN, hosting provider, proxy reputation và network range.
- Tính nhất quán giữa các request và nhiều tenant.

**Theo tenant/ứng dụng:**

- Tổng account duy nhất bị nhắm tới.
- Spike failure theo login endpoint hoặc protocol.
- Sự kiện legacy auth.
- Tỷ lệ MFA challenge và denial.
- Login success bất thường và các hành động sau login.

Không dùng một chiều duy nhất để ra quyết định. IP reputation xấu không đủ để khóa account; một account có nhiều lần sai cũng không đủ để kết luận spraying nếu không có bối cảnh.

## 4. Telemetry và dữ liệu đăng nhập

Detection chỉ đáng tin khi sự kiện được ghi nhất quán ở các điểm xác thực. Một event có thể chứa:

| Field | Ý nghĩa |
| --- | --- |
| `event_id` | ID duy nhất của sự kiện |
| `timestamp` | Thời điểm UTC phía server |
| `tenant_ref` | Tenant/realm ở dạng tham chiếu |
| `application_id` | Ứng dụng hoặc resource nhận xác thực |
| `auth_protocol` | Web, OAuth/OIDC, VPN, legacy protocol, SSH... |
| `method` | Password, passkey, MFA, certificate... |
| `account_ref` | Account reference đã pseudonymize |
| `source_ref` | Network/device reference theo policy |
| `outcome` | Success, failure, throttled, challenged |
| `reason_code` | Invalid credential, disabled, policy, timeout... |
| `risk_policy_version` | Phiên bản rule/model đã áp dụng |
| `correlation_id` | Liên kết request và session mà không lộ secret |

Không ghi password, password hash, OTP, recovery code, raw access token, session cookie hoặc toàn bộ Authorization header. Không lưu password candidate trong telemetry để cố chứng minh nhiều request đã thử cùng mật khẩu. Có thể dùng event metadata và mẫu hành vi để phát hiện mà không lưu bí mật.

### 4.1. Pseudonymization

Email và username là PII. Nếu cần tương quan account trong SIEM hoặc data lake, dùng định danh giả ổn định như HMAC của identifier đã chuẩn hóa với key do server quản lý. Không dùng hash thuần của email làm pseudonym nếu có thể dò ngược bằng dictionary.

Key pseudonymization cần được quản lý, giới hạn quyền truy cập và có kế hoạch rotation. Khi đổi key, detection pipeline cần biết cách liên kết dữ liệu theo phiên bản key mà không làm mất khả năng điều tra.

### 4.2. Tin cậy IP và forwarded headers

Nếu ứng dụng nằm sau reverse proxy/load balancer, không lấy X-Forwarded-For trực tiếp từ request internet làm IP thật. Chỉ tin forwarded headers từ proxy đã được cấu hình tin cậy; loại bỏ giá trị do client chèn và chuẩn hóa chain theo hạ tầng. Nếu không, attacker có thể giả IP để né rate limit hoặc làm sai detection.

### 4.3. Ví dụ truy vấn tổng hợp

SQL minh họa để tìm tenant có nhiều account duy nhất bị password failure trong một cửa sổ:

~~~sql
SELECT
    tenant_ref,
    application_id,
    COUNT(*) AS failure_count,
    COUNT(DISTINCT account_ref) AS distinct_accounts,
    COUNT(DISTINCT source_ref) AS distinct_sources
FROM authentication_event
WHERE timestamp >= CURRENT_TIMESTAMP - INTERVAL '10 minutes'
  AND method = 'password'
  AND outcome = 'failure'
GROUP BY tenant_ref, application_id
HAVING COUNT(DISTINCT account_ref) >= :minimum_accounts
   AND COUNT(*) >= :minimum_failures;
~~~

Truy vấn này chỉ là bước tổng hợp ban đầu. Một detection production cần baseline theo tenant, cửa sổ nhiều độ dài, loại trừ test account, xử lý duplicate/retry, phân tích success sau failure và đánh giá mức độ phân tán. Không áp dụng một minimum_accounts cố định cho tenant có quy mô rất khác nhau.

## 5. Xây dựng detection logic và alert

Detection tốt thường kết hợp rule xác định với baseline và phân tích hành vi. Có thể bắt đầu bằng các lớp:

1. **Burst rule:** nhiều account duy nhất có password failure trong thời gian ngắn.
2. **Low-per-account rule:** số lần sai mỗi account thấp nhưng số account bị thử cao.
3. **Distributed-source rule:** nhiều nguồn thử nhiều account trong cùng tenant hoặc cùng ứng dụng.
4. **Success-after-failure rule:** một account đăng nhập thành công sau chuỗi thất bại đáng ngờ.
5. **Privileged-target rule:** account quản trị, tài khoản dịch vụ hoặc account nhạy cảm bị thử.
6. **Legacy-protocol rule:** thất bại hoặc thành công bất thường qua giao thức không có MFA.
7. **Post-auth rule:** sau login success có thêm MFA factor, forwarding rule, token, consent hoặc truy cập dữ liệu bất thường.

### 5.1. Alert nên có ngữ cảnh

Một alert hữu ích nên trả lời:

- Tenant và ứng dụng nào bị ảnh hưởng?
- Bao nhiêu account duy nhất đã bị thử?
- Bao nhiêu request, bao nhiêu nguồn và trong cửa sổ nào?
- Có account nào đăng nhập thành công không?
- Có account đặc quyền hoặc service account trong danh sách không?
- Phương thức xác thực và giao thức nào được dùng?
- Có MFA challenge, push denial hoặc thay đổi factor không?
- Hành động tự động nào đã áp dụng?
- Ai chịu trách nhiệm điều tra và thời hạn phản hồi?

Alert không nên chứa password, OTP, raw token hoặc danh sách email đầy đủ nếu không cần. Dùng account reference, mask và đường dẫn truy cập có kiểm soát cho analyst.

### 5.2. Severity

| Mức | Tình huống gợi ý | Phản ứng |
| --- | --- | --- |
| Informational | Một nguồn có vài failure, không có dấu hiệu lan rộng | Ghi nhận và theo dõi baseline |
| Low/Medium | Nhiều account bị thử nhưng chưa có success hoặc target nhạy cảm | Tăng telemetry, áp dụng throttle/risk challenge |
| High | Nhiều account bị thử, có success đáng ngờ hoặc nhắm account đặc quyền | Incident triage, bảo vệ account liên quan, kiểm tra session |
| Critical | Có compromise xác nhận, privilege account hoặc hành vi lateral movement | Kích hoạt incident response, containment và phối hợp SOC/IT/identity owner |

Severity phải dựa vào tác động và độ tin cậy của tín hiệu. Không biến mọi spike thành incident critical; alert fatigue khiến analyst bỏ qua chiến dịch thật.

## 6. Rate limiting: kiểm soát nhiều chiều

Rate limiting là một lớp quan trọng, nhưng chỉ rate limit theo IP hoặc khóa account sau vài lần sai đều có điểm yếu. Password spraying được thiết kế để né ngưỡng đơn giản.

| Chiều kiểm soát | Biện pháp | Rủi ro nếu dùng riêng |
| --- | --- | --- |
| Account | Progressive delay, temporary throttling, risk challenge | Attacker có thể cố ý khóa/chặn nạn nhân |
| Source IP/network | Token bucket, concurrency cap, reputation | NAT/VPN/proxy khiến nhiều người hợp lệ dùng chung |
| Device/browser session | Theo dõi tốc độ và tính nhất quán | Fingerprint có thể bị giả hoặc reset |
| Tenant/application | Ngưỡng theo quy mô và baseline | Một tenant không được làm nghẽn tenant khác |
| Global service | Bảo vệ CPU, database, password hash verifier và IdP dependency | Ngưỡng quá thấp gây DoS diện rộng |
| Account cluster | Phát hiện nhiều account bị cùng nguồn hoặc cụm nguồn thử | Cần dữ liệu tương quan và pseudonymization |

### 6.1. Progressive throttling

Thay vì khóa account vĩnh viễn sau một số lần sai:

- Tăng delay sau các lần thử thất bại liên tiếp.
- Giới hạn số request đồng thời cho cùng account.
- Áp dụng temporary throttle có TTL và tự phục hồi.
- Tăng yêu cầu xác thực bổ sung khi risk cao.
- Cho phép người dùng hợp lệ tiếp tục qua một kênh hỗ trợ an toàn.
- Giám sát để attacker không thể làm cạn tài nguyên bằng cách tạo hàng triệu throttle key.

Delay phải được áp dụng phía server và phân tán nhất quán. Không để một node có bộ đếm riêng trong memory trong khi attacker xoay request qua nhiều instance.

### 6.2. Không tạo account lockout DoS

Nếu mỗi lần password sai đều khóa account, attacker chỉ cần biết email nhân viên để làm gián đoạn công việc. Ưu tiên throttling tạm thời, step-up, thông báo an toàn và phát hiện chiến dịch. Với account có rủi ro cao, có thể dùng policy chặt hơn nhưng cần quy trình mở khóa/recovery không bị social engineering.

### 6.3. Rate limit theo tenant

Một tenant lớn và tenant nhỏ không nên dùng cùng một ngưỡng tuyệt đối. Baseline có thể dựa trên:

- Số account hoạt động.
- Tỷ lệ login bình thường theo giờ/ngày.
- Số ứng dụng và giao thức đang bật.
- Mùa cao điểm hoặc sự kiện đăng nhập hợp lệ.
- Tỷ lệ password failure lịch sử.

Ngưỡng cần có guardrail toàn cục để tenant bị cấu hình sai không làm ảnh hưởng hạ tầng chung.

## 7. Password policy và credential hygiene

Rate limit chỉ làm chậm việc thử mật khẩu. Password policy giảm xác suất một candidate phổ biến thành công.

- Yêu cầu mật khẩu đủ dài và cho phép passphrase; không ép quy tắc phức tạp khó nhớ khiến người dùng chọn biến thể dễ đoán.
- Chặn password phổ biến, password mặc định và password đã biết bị compromise bằng blocklist phù hợp.
- Không yêu cầu đổi password định kỳ vô điều kiện nếu không có dấu hiệu compromise hoặc chính sách cụ thể; thay đổi bắt buộc quá thường xuyên có thể tạo password pattern dễ đoán.
- Buộc đổi mật khẩu mặc định khi cấp account hoặc triển khai hệ thống.
- Không cho phép password trùng username, tên tổ chức hoặc các chuỗi mặc định dễ đoán.
- Dùng password hashing chuyên dụng như Argon2id, scrypt hoặc bcrypt với tham số được benchmark và cập nhật.
- Salt riêng cho từng password; bảo vệ pepper nếu sử dụng.
- Không lưu hoặc truyền password plaintext ngoài thời điểm cần xác minh qua kênh TLS.
- Hạn chế việc password công việc được tái sử dụng ở dịch vụ cá nhân bằng hướng dẫn, SSO và passkey.

### 7.1. Credential reuse và breach screening

Credential stuffing dùng password đã lộ từ dịch vụ khác; password spraying thường đoán một số candidate phổ biến. Hai kiểu tấn công có thể giao nhau. Kiểm tra password mới với danh sách password đã bị compromise có thể giảm rủi ro, nhưng không gửi password người dùng tới dịch vụ bên ngoài theo cách không được bảo vệ. Chọn cơ chế có bảo vệ quyền riêng tư, ví dụ k-anonymity hoặc danh sách nội bộ được cập nhật, và đánh giá false positives.

Không ghi password để phân tích campaign. Nếu cần nghiên cứu credential abuse, dùng event outcome, account pseudonym, nguồn và thời gian; giữ bí mật password verifier.

## 8. MFA, passkey và giảm giá trị của password bị đoán

Nếu attacker đoán được password nhưng account có MFA được cấu hình đúng, password đơn lẻ thường chưa đủ để tạo session. Tuy nhiên, chất lượng MFA và recovery quyết định hiệu quả thực tế.

### 8.1. MFA theo mức chống phishing

| Phương thức | Tác dụng | Giới hạn |
| --- | --- | --- |
| SMS/voice OTP | Bổ sung yếu tố qua số điện thoại | SIM swap, interception, phishing và chuyển tiếp mã |
| TOTP app | Không phụ thuộc SMS; hữu ích với nhiều ứng dụng | Mã có thể bị phishing/replay trong thời gian hiệu lực |
| Push approval | Bổ sung xác nhận trên thiết bị | Push fatigue và người dùng bấm approve theo thói quen |
| Number matching / context-rich push | Giảm approve nhầm và push fatigue | Vẫn có thể bị lừa nếu người dùng không kiểm tra ngữ cảnh |
| Security key / passkey WebAuthn | Có khả năng chống phishing theo origin/RP binding | Cần enrollment, recovery và thiết bị phù hợp |
| Certificate-based authentication | Có thể ràng buộc danh tính với khóa và thiết bị/workload | Quản lý PKI, private key, revocation và enrollment phức tạp |

Ưu tiên MFA chống phishing như passkey/WebAuthn hoặc security key cho account đặc quyền và hệ thống có hậu quả cao. SMS hoặc TOTP vẫn có thể hữu ích như lớp bổ sung trong bối cảnh phù hợp, nhưng không nên gọi là phishing-resistant.

### 8.2. Passkey không làm password policy biến mất ngay lập tức

Nếu account vẫn có password fallback, attacker có thể tiếp tục spray vào endpoint password. Cần:

- Tắt password authentication khi không còn cần thiết và đã có recovery thay thế an toàn.
- Nếu giữ fallback, áp dụng rate limit, risk detection và MFA policy tương đương.
- Không cho phép password fallback yếu hơn ở API, VPN hoặc legacy endpoint.
- Thông báo khi có đăng ký passkey mới và yêu cầu reauthentication cho thao tác thêm/xóa credential.

### 8.3. MFA fatigue sau khi đoán được password

Attacker có thể thử password trên nhiều account; nếu một password thành công và kích hoạt push, họ có thể gửi nhiều yêu cầu phê duyệt. Hệ thống nên:

- Giới hạn số push trong một khoảng thời gian.
- Hiển thị context rõ: ứng dụng, vị trí tương đối, thiết bị và thời điểm.
- Dùng number matching hoặc challenge binding.
- Có nút report/deny suspicious request.
- Tự động tạm dừng push khi có spam và hướng người dùng sang kênh hỗ trợ.
- Ghi nhận push denied/reported như một tín hiệu detection.

Không gửi push vô hạn sau khi password đúng; điều đó biến MFA thành kênh DoS và social engineering.

## 9. Chặn đường xác thực yếu và legacy protocols

Một policy SSO mạnh không bảo vệ account nếu vẫn tồn tại endpoint khác chấp nhận password mà không có MFA hoặc không ghi log đầy đủ.

Thực hiện inventory và xử lý:

- Tắt legacy authentication không còn nhu cầu nghiệp vụ.
- Chặn basic authentication hoặc protocol không hỗ trợ MFA khi có thể.
- Buộc VPN/remote access đi qua identity provider và policy hiện đại.
- Dùng certificate hoặc workload identity cho service thay vì password tĩnh dùng chung.
- Xóa account mặc định, account không chủ sở hữu và account không dùng.
- Giới hạn quyền và network access của service account.
- Không cho phép endpoint nội bộ bỏ qua rate limit chỉ vì request đến từ mạng riêng.
- Kiểm tra mọi ứng dụng có local password store hoặc login riêng.

Nếu chưa thể tắt giao thức cũ, cô lập bằng network policy, allowlist nguồn, credential riêng, monitoring tăng cường và kế hoạch migration có deadline. “Mạng nội bộ” không phải ranh giới đủ để tin password request.

## 10. Conditional access và risk-based authentication

Risk-based authentication kết hợp nhiều tín hiệu để quyết định cho phép, throttle, step-up hoặc block. Một policy có thể xét:

- Account privilege và loại tài nguyên.
- Thiết bị đã quản lý, device posture và session integrity.
- Vị trí/ASN ở mức tín hiệu, không phải bằng chứng danh tính.
- Hành vi đăng nhập trong quá khứ.
- Password failure pattern theo account/tenant/source.
- MFA strength và authentication age.
- Legacy protocol hoặc client không tuân thủ.
- Hành động sau đăng nhập và rủi ro của transaction.

### Ví dụ policy

| Tình huống | Hành động phù hợp |
| --- | --- |
| Một account nhập sai một lần trên thiết bị quen thuộc | Cho retry có giới hạn |
| Nhiều account trong tenant bị thử từ một cụm nguồn | Throttle nguồn/campaign, cảnh báo SOC |
| Nhiều nguồn phân tán thử nhiều account | Áp dụng tenant/global detection và adaptive challenge |
| Account admin đăng nhập password từ thiết bị lạ sau campaign | Block hoặc yêu cầu phishing-resistant step-up và kiểm tra bổ sung |
| Account thành công sau nhiều failure, rồi tạo MFA factor mới | Coi là high risk, giữ quyền hạn chế và điều tra |
| Legacy protocol nhận burst failure | Chặn/disable theo policy và kiểm tra account đã bị thử |

Không để risk score tự động thay thế policy minh bạch. Ghi rõ feature, threshold, action, version và cách analyst override. Một người đi công tác hoặc dùng VPN không nên bị từ chối chỉ bởi một tín hiệu địa lý.

## 11. Xử lý khi phát hiện password spraying

Khi có alert, cần xác định đây là campaign thật hay sự kiện hợp lệ như batch migration, test nội bộ hoặc người dùng gặp lỗi. Nếu có dấu hiệu compromise, ưu tiên containment theo phạm vi.

### 11.1. Triage

1. Xác định tenant, ứng dụng, giao thức và thời gian bắt đầu.
2. Đếm account duy nhất bị thử và phân loại account thường, admin, service.
3. Xác định nguồn, ASN, device, client và mức phân tán.
4. Kiểm tra có login success trong hoặc sau campaign không.
5. Với success, kiểm tra MFA result, session issuance, device, token và hoạt động sau login.
6. Xác định password endpoint nào không có MFA/rate limit/telemetry.
7. So sánh với thay đổi vận hành, test hoặc đợt đăng nhập hợp lệ.

### 11.2. Containment

- Throttle hoặc block nguồn/cụm nguồn khi đủ bằng chứng; tránh block diện rộng gây ảnh hưởng người dùng hợp lệ.
- Tăng challenge hoặc yêu cầu MFA chống phishing cho account bị nhắm tới.
- Tạm hạn chế account có login success đáng ngờ, nhất là account đặc quyền.
- Revoke session và refresh token của account compromise.
- Reset password cho account đã xác nhận hoặc có bằng chứng compromise; không bắt buộc reset hàng loạt chỉ vì có failure.
- Kiểm tra và xóa MFA factor, app password, forwarding rule, OAuth grant hoặc recovery channel do attacker thêm.
- Tắt legacy protocol hoặc credential path bị khai thác nếu có thể.
- Bảo toàn audit, event và evidence phục vụ điều tra.

### 11.3. Eradication và recovery

- Xác định account nào bị lộ password và password có thể bị tái sử dụng ở dịch vụ khác không.
- Yêu cầu password mới không nằm trong blocklist/breach list theo policy.
- Đăng ký hoặc xác minh lại passkey/security key cho account có rủi ro cao.
- Thu hồi credential và session cũ; rotate secret service account nếu bị ảnh hưởng.
- Xem xét privilege, mailbox rule, delegated access, API token và persistence.
- Thông báo người dùng qua kênh đáng tin và hướng dẫn cách báo cáo.
- Theo dõi tái diễn trong nhiều cửa sổ thời gian sau containment.

### 11.4. Không phản ứng quá mức

Một đợt password failure không chứng minh mọi account đã bị compromise. Reset password hàng loạt không có căn cứ có thể tạo gián đoạn, làm tăng help desk load và đẩy người dùng sang hành vi kém an toàn. Hãy phân loại:

- Account chỉ bị thử nhưng chưa có success.
- Account có success đáng ngờ nhưng chưa xác nhận compromise.
- Account có dấu hiệu compromise được xác nhận.
- Account đặc quyền hoặc service account có rủi ro tác động lớn.

Áp dụng biện pháp theo mức độ và ghi lại lý do.

## 12. Java/Spring: phối hợp rate limit và campaign detection

Ví dụ dưới đây minh họa cấu trúc xử lý. Các service như DistributedRateLimiter, SprayDetector và RiskPolicy là abstraction; cần triển khai bằng kho trạng thái phân tán, đồng hồ nhất quán và telemetry đã pseudonymize.

~~~java
record LoginAttempt(
    String tenantId,
    String applicationId,
    String accountReference,
    String sourceReference,
    String deviceReference,
    Instant occurredAt
) {}

AuthenticationResult authenticatePassword(
        String tenantId,
        String applicationId,
        String identifier,
        char[] password,
        RequestContext context) {

    String accountRef = accountReferences.pseudonymize(
        tenantId, normalizeIdentifier(identifier)
    );
    String sourceRef = sourceReferences.fromTrustedProxyChain(context);
    String deviceRef = deviceReferences.fromValidatedSignals(context);

    LoginAttempt attempt = new LoginAttempt(
        tenantId, applicationId, accountRef, sourceRef,
        deviceRef, clock.instant()
    );

    // Áp dụng nhiều bucket; không chỉ dựa trên IP.
    rateLimiter.checkGlobal(applicationId);
    rateLimiter.checkTenant(tenantId, applicationId);
    rateLimiter.checkSource(sourceRef);
    rateLimiter.checkAccount(accountRef);

    Account account = accountLookup.find(tenantId, identifier);
    PasswordVerification result =
        passwordVerifier.verifyOrRunDummy(account, password);

    AuthenticationOutcome outcome =
        result.matches() && accountPolicy.canSignIn(account)
            ? AuthenticationOutcome.SUCCESS
            : AuthenticationOutcome.FAILURE;

    eventPublisher.publish(attempt, outcome);
    SpraySignal signal = sprayDetector.observe(attempt, outcome);

    if (signal.isCampaignLikely()) {
        riskResponse.applyCampaignControls(signal);
    }

    if (outcome == AuthenticationOutcome.FAILURE) {
        return AuthenticationResult.genericFailure();
    }

    RiskDecision decision = riskPolicy.evaluate(account, context, signal);
    if (decision.requiresPhishingResistantStepUp()) {
        return AuthenticationResult.stepUpRequired();
    }
    if (decision.blocksAuthentication()) {
        return AuthenticationResult.denied();
    }

    return sessionIssuer.issueFreshSession(account, decision.assurance());
}
~~~

Đây là pseudocode định hướng, cần chú ý:

- account pseudonym phải dùng HMAC/key quản lý an toàn; không dùng hash email thuần.
- Chỉ lấy IP từ proxy chain được cấu hình tin cậy.
- Account không tồn tại cần được xử lý để không làm lộ account enumeration qua response hoặc timing rõ rệt.
- Rate limiter cần atomic/distributed; không dùng bộ đếm local của một instance làm kiểm soát duy nhất.
- Không publish password, hash, OTP hoặc raw assertion vào event.
- Không để detection chạy đồng bộ làm login timeout; có thể dùng event pipeline nhưng cần synchronous guardrail cho throttle quan trọng.
- Khi campaign detection bất khả dụng, áp dụng fallback an toàn đã định nghĩa, không bỏ toàn bộ rate limit.
- Chỉ tạo session sau khi risk policy và MFA/step-up hoàn tất.

### 12.1. Ví dụ event aggregation pseudocode

~~~java
SpraySignal observe(LoginAttempt attempt, AuthenticationOutcome outcome) {
    WindowKey key = new WindowKey(
        attempt.tenantId(),
        attempt.applicationId(),
        clock.instant().truncatedTo(ChronoUnit.MINUTES)
    );

    counters.incrementFailuresIfNeeded(key, attempt, outcome);
    counters.addDistinctAccountIfNeeded(key, attempt, outcome);
    counters.addDistinctSourceIfNeeded(key, attempt, outcome);

    WindowStats stats = counters.readWindow(key);
    return baselineDetector.evaluate(
        stats,
        tenantBaseline.forTenant(attempt.tenantId()),
        detectionPolicy.currentVersion()
    );
}
~~~

Một triển khai thật cần xử lý cửa sổ trượt, duplicate event, event đến trễ, nhiều region, cardinality, retention và privacy. Không dùng identifier thô làm key có thể truy vấn công khai.

## 13. Những lỗi phòng thủ thường gặp

| Lỗi | Hậu quả | Cải thiện |
| --- | --- | --- |
| Chỉ khóa sau N lần sai trên một account | Password spraying giữ số lần mỗi account thấp | Phân tích account duy nhất theo tenant/global |
| Chỉ rate limit theo IP | Attacker phân tán qua proxy; NAT gây false positive | Kết hợp account, source, device, tenant và global |
| Khóa account vĩnh viễn tự động | Attacker có thể gây DoS cho người dùng | Progressive delay, temporary throttle và recovery |
| Chỉ giám sát web SSO | VPN, legacy hoặc app riêng vẫn nhận password | Inventory mọi authentication path |
| MFA chỉ là SMS/OTP nhưng được gọi phishing-resistant | Attacker vẫn có thể phishing mã | Phân loại đúng assurance; ưu tiên WebAuthn/security key |
| Push không có context/number matching | Push fatigue và approve nhầm | Number matching, rate limit và report control |
| Password policy chỉ ép ký tự phức tạp | Người dùng chọn pattern dễ đoán | Độ dài, blocklist, password manager và passkey |
| Alert chỉ đếm failure tổng | Không thấy số account duy nhất và low-per-account pattern | Tương quan theo account/source/tenant/time |
| Alert chỉ dựa vào IP reputation | Dễ block nhầm VPN/NAT hoặc bỏ sót distributed spray | Kết hợp nhiều tín hiệu và baseline |
| Tin X-Forwarded-For do client gửi | Attacker giả nguồn để né throttle | Chỉ tin proxy chain đã cấu hình |
| Reset password cho toàn tổ chức khi chỉ có failure | Gián đoạn và tăng help desk abuse | Phân loại failure, suspicious success và confirmed compromise |
| Không revoke session sau compromise | Attacker tiếp tục dùng phiên đã cấp | Revoke session/refresh token và kiểm tra persistence |
| Không kiểm tra hoạt động sau login success | Bỏ sót mailbox rule, MFA factor hoặc OAuth grant lạ | Post-auth monitoring và incident review |
| Service account dùng password chung | Một credential bị đoán ảnh hưởng nhiều hệ thống | Workload identity, certificate hoặc secret riêng |
| Ghi identifier/password vào log | Tạo thêm nguồn rò rỉ credential | Pseudonymization và redaction |

## 14. Ma trận kiểm thử password spraying defense

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Một IP thử một password trên nhiều account | Tenant-level detector nhận diện số account duy nhất |
| Nhiều IP thử cùng tenant theo nhịp chậm | Cửa sổ dài và correlation phát hiện campaign phân tán |
| Một account có nhiều password failure | Account throttle hoạt động nhưng không tạo permanent lockout mặc định |
| Nhiều account cùng IP công ty đăng nhập lỗi do thay đổi mật khẩu | Baseline/change window giảm false positive; có thể yêu cầu challenge phù hợp |
| Một account success sau nhiều failure đáng ngờ | Tạo high-risk signal và kiểm tra session/post-auth |
| Account admin bị spray | Áp dụng policy mạnh hơn, cảnh báo ưu tiên cao |
| Legacy protocol nhận burst failure | Alert và block/disable theo policy |
| Attacker giả X-Forwarded-For | Proxy trust config loại bỏ giá trị không đáng tin |
| Attacker phân tán qua nhiều ASN | Detection không phụ thuộc duy nhất vào IP |
| NAT khiến nhiều người dùng hợp lệ chung IP | Không khóa tất cả account chỉ dựa trên IP |
| Campaign detector timeout | Rate limit nền vẫn hoạt động; fallback được định nghĩa |
| Redis/rate-limit store mất kết nối | Áp dụng fallback bảo vệ service; không fail-open toàn bộ |
| Account không tồn tại bị thử | Response và timing không làm lộ account rõ rệt |
| Password đúng nhưng account cần MFA | Chưa tạo session trước step-up |
| MFA push spam sau password success | Giới hạn push, number matching và ghi nhận denial/report |
| Passkey được đăng ký nhưng password fallback còn bật | Password endpoint vẫn có throttle/detection tương đương |
| Service account bị thử password | Alert riêng; giới hạn nguồn và quyền; đánh giá chuyển sang workload identity |
| Credential compromise được xác nhận | Revoke session/token, xử lý factor và reset theo scope |
| User hợp lệ bị false positive | Có quy trình review/unblock an toàn, audit lý do |
| Log/event được kiểm tra | Không chứa password, OTP, raw token hoặc session cookie |

### Tình huống thực hành

Một tổ chức có 4.000 nhân viên. Trong 12 phút, 1.100 account có ít nhất một password failure; mỗi account chỉ có một hoặc hai lần sai. Request đến từ nhiều IP và một số ASN hosting. Sau đó ba account đăng nhập thành công từ thiết bị chưa từng thấy; một account có quyền quản trị đã nhận nhiều MFA push và người dùng bấm Deny.

Hệ thống hiện chỉ khóa account sau 10 lần sai và giới hạn 20 request mỗi IP trong 5 phút. Web SSO có MFA, nhưng một cổng VPN cũ vẫn cho phép password authentication.

**Yêu cầu:** đánh giá campaign và thiết kế phản ứng.

**Hướng phân tích:**

1. Mẫu nhiều account duy nhất, ít failure mỗi account trong cửa sổ ngắn phù hợp với password spraying; nhiều ASN/IP cho thấy khả năng phân tán.
2. Kiểm tra nguồn request, application/protocol và thời gian; xác minh forwarded headers chỉ đến từ proxy tin cậy.
3. Ưu tiên điều tra ba login success: device, session, MFA, token, mailbox rule, OAuth grant và hoạt động sau login.
4. Với account admin nhận MFA push bị deny, coi đây là tín hiệu high risk; liên hệ người dùng qua kênh đáng tin và bảo vệ account.
5. Throttle campaign theo tenant/account/source/global; không khóa đồng loạt 1.100 account chỉ dựa trên failure.
6. Cô lập hoặc tắt VPN legacy password path, chuyển sang IdP/MFA hoặc cơ chế mạnh hơn.
7. Revoke session/token và reset credential cho account đã xác nhận compromise; kiểm tra factor và recovery channel bị thêm trái phép.
8. Theo dõi chiến dịch sau containment, rà soát password policy, passkey adoption và alert baseline.

## 15. Câu hỏi tự kiểm tra

1. **Password spraying khác brute force thế nào?** Spraying thử ít mật khẩu trên nhiều account; brute force thường thử nhiều mật khẩu trên một account hoặc một tập nhỏ account.
2. **Password spraying khác credential stuffing thế nào?** Spraying dựa vào một số password candidate; stuffing dùng cặp username/password đã bị lộ từ dịch vụ khác.
3. **Vì sao khóa account sau N lần sai chưa đủ?** Attacker giữ số lần thử mỗi account thấp và phân tán qua nhiều account.
4. **Vì sao cần detection theo tenant/global?** Tổng thể chiến dịch có thể bất thường dù từng account hoặc từng IP chưa vượt ngưỡng.
5. **Vì sao chỉ rate limit theo IP gây vấn đề?** Attacker có thể phân tán nguồn; người dùng hợp lệ có thể dùng chung NAT/VPN.
6. **MFA nào có khả năng chống phishing tốt hơn?** Passkey/WebAuthn và security key khi được cấu hình đúng origin/RP; SMS/TOTP không có cùng bảo đảm.
7. **Sau một login success đáng ngờ cần kiểm tra gì?** Session/token, MFA factor, mailbox rules, OAuth grants, dữ liệu truy cập và hành vi persistence.
8. **Có nên reset password toàn tổ chức sau mọi spray alert không?** Không. Phân biệt account bị thử, success đáng ngờ và compromise đã xác nhận; phản ứng theo scope.

**Ghi nhớ:** Password spraying cố né bộ đếm từng account bằng cách thử ít mật khẩu trên nhiều người dùng. Hãy phát hiện bằng số account duy nhất, số nguồn, tenant, ứng dụng và cửa sổ thời gian; phối hợp rate limit đa chiều, password hygiene, MFA chống phishing, passkey và loại bỏ legacy authentication. Khi có login success đáng ngờ, điều tra session và hoạt động sau đăng nhập, thu hồi credential bị ảnh hưởng và phản ứng theo bằng chứng thay vì khóa hàng loạt.
