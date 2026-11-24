# Tín hiệu trong risk-based auth

> **Chương:** Risk-based authentication  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS — tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Người học biết mô hình hóa ranh giới tin cậy, phòng chống phishing, replay, lạm dụng đăng nhập và thiết kế luồng xác thực an toàn.
>
> **Trọng tâm:** Nhận diện, đánh giá và kết hợp các tín hiệu rủi ro trong một lần đăng nhập hoặc thao tác nhạy cảm; hiểu nguồn gốc, độ tin cậy, độ mới và giới hạn của từng tín hiệu để chọn hành động phù hợp như cho phép, giám sát, giới hạn, step-up hoặc từ chối.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích tín hiệu rủi ro là gì và phân biệt tín hiệu với bằng chứng xác thực hoặc quyết định authorization.
2. Phân loại tín hiệu theo nhóm thiết bị, mạng, vị trí, hành vi, tốc độ, lịch sử tài khoản, threat intelligence và authentication context.
3. Đánh giá nguồn gốc, độ tin cậy, độ mới, tính toàn vẹn và khả năng bị giả mạo của một tín hiệu.
4. Kết hợp nhiều tín hiệu để ước lượng rủi ro mà không coi một tín hiệu đơn lẻ là kết luận chắc chắn.
5. Phân biệt risk score với assurance level và hiểu vì sao risk score không mặc nhiên là xác suất.
6. Thiết kế chính sách adaptive authentication theo hành động và hậu quả, bao gồm allow, monitor, rate limit, step-up và deny.
7. Giảm false positive, tránh thiên lệch và bảo vệ quyền riêng tư khi thu thập dữ liệu thiết bị, vị trí và hành vi.
8. Xây dựng kiểm thử cho tín hiệu thiếu, cũ, mâu thuẫn, giả mạo, bị replay hoặc không khả dụng.

## 1. Tín hiệu rủi ro trong risk-based authentication là gì?

**Risk-based authentication (RBA)** là cách điều chỉnh mức kiểm tra xác thực dựa trên bối cảnh và rủi ro của một request. Hệ thống xem xét các tín hiệu liên quan tới tài khoản, thiết bị, mạng, vị trí, hành vi và lần xác thực hiện tại để quyết định có cần kiểm tra bổ sung hay không.

**Tín hiệu rủi ro (risk signal)** là một dữ liệu hoặc sự kiện có thể làm thay đổi đánh giá về khả năng một request là hợp lệ, bất thường hoặc đang bị lạm dụng.

Ví dụ:

- Người dùng đăng nhập từ thiết bị đã sử dụng thường xuyên, mạng quen thuộc và hoàn tất passkey đúng cách.
- Một tài khoản vừa thất bại đăng nhập nhiều lần, sau đó xuất hiện request từ một ASN có lịch sử phát tán credential stuffing.
- Một phiên đang hoạt động đột ngột yêu cầu thay email khôi phục từ thiết bị mới và mạng có dấu hiệu proxy ẩn danh.
- Một workload gọi API với tốc độ gấp nhiều lần baseline và từ một vị trí mạng chưa từng thấy.

Các tín hiệu có thể làm tăng hoặc giảm mức nghi ngờ, nhưng **không tự chứng minh danh tính**. IP quen thuộc không chứng minh người dùng là chủ tài khoản; thiết bị mới không chứng minh attacker; vị trí bất thường không tự động chứng minh gian lận.

### RBA trả lời câu hỏi gì?

- Request hiện tại có khác đáng kể so với hành vi hợp lệ đã biết không?
- Có dấu hiệu credential stuffing, account takeover, automation hoặc replay không?
- Bằng chứng xác thực hiện tại có đủ cho hành động này không?
- Có nên yêu cầu thêm một yếu tố hoặc xác thực chống phishing?
- Có cần giới hạn tốc độ, tạm giữ hành động hoặc chuyển sang review không?

RBA bổ sung ngữ cảnh cho quyết định xác thực. Nó không thay thế xác minh credential, kiểm tra token, session validation hay authorization trên tài nguyên.

## 2. Phân biệt tín hiệu, bằng chứng và quyết định

Một hệ thống an toàn cần tách ba lớp:

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Signal** | Hệ thống quan sát được điều gì? | IP thuộc ASN mới; thiết bị chưa thấy; 8 lần thất bại trong 2 phút. |
| **Evidence / verified context** | Bằng chứng xác thực nào đã được kiểm chứng? | Chữ ký passkey hợp lệ, issuer đúng, nonce đúng, MFA đạt policy. |
| **Decision** | Request được xử lý thế nào? | Cho phép, yêu cầu step-up, rate limit, tạm giữ hoặc từ chối. |

Một signal có thể chưa được xác minh hoặc có độ tin cậy thấp. Ví dụ, header User-Agent là do client gửi và có thể dễ dàng thay đổi. Một verified context cần đến từ nguồn đáng tin cậy, chẳng hạn ID token đã xác minh hoặc authentication event do server ghi nhận.

Quyết định cuối cùng phải xét cả tín hiệu lẫn policy. Một request có risk score thấp vẫn cần bị từ chối nếu chữ ký token sai hoặc tài khoản đã bị khóa. Ngược lại, một request có tín hiệu lạ không nhất thiết bị từ chối nếu người dùng hoàn tất step-up đúng cách và policy cho phép.

## 3. Phân loại tín hiệu rủi ro

Tín hiệu thường được nhóm theo nguồn và ý nghĩa. Một tín hiệu có thể thuộc nhiều nhóm; điều quan trọng là xác định nó được thu thập ở đâu và có thể bị attacker tác động như thế nào.

| Nhóm | Ví dụ | Câu hỏi đánh giá |
| --- | --- | --- |
| **Thiết bị** | Device registration, cookie thiết bị, platform, browser, attestation. | Thiết bị đã được liên kết với tài khoản chưa? Bằng chứng có xác thực được không? |
| **Mạng** | IP, ASN, proxy/VPN/Tor, reputation, TLS/client certificate. | Request đến từ mạng nào? Dữ liệu mạng có đáng tin và đủ mới không? |
| **Vị trí** | Quốc gia, vùng, thay đổi vị trí, impossible travel. | Vị trí có khả thi về thời gian và chất lượng nguồn không? |
| **Hành vi** | Nhịp gõ, cách điều hướng, mẫu sử dụng, hành động thường gặp. | Hành vi khác baseline đến mức nào? Có nguy cơ xâm phạm quyền riêng tư không? |
| **Tốc độ / tần suất** | Login attempts, OTP requests, password reset, API calls. | Có automation, brute force, enumeration hoặc abuse không? |
| **Lịch sử tài khoản** | Login thành công/thất bại, recovery, đổi credential, cảnh báo trước. | Tài khoản có sự kiện bảo mật gần đây không? |
| **Authentication context** | Phương thức, MFA, auth_time, assurance, recovery used. | Bằng chứng hiện tại có đủ mạnh và đủ mới không? |
| **Threat intelligence** | IP/domain/device indicators, leaked credential signals. | Indicator có nguồn, độ mới và độ chính xác ra sao? |
| **Ứng dụng / transaction** | Loại hành động, giá trị giao dịch, resource, tenant. | Hậu quả nếu request trái phép là bao nhiêu? |

Không nên thu thập mọi tín hiệu chỉ vì có thể thu thập. Chỉ dùng dữ liệu có mục đích rõ, có thể giải thích trong policy và có cơ sở pháp lý/quyền riêng tư phù hợp.

## 4. Tín hiệu thiết bị (device signals)

Thiết bị có thể giúp hệ thống nhận biết một môi trường đã từng được sử dụng với tài khoản. Nhưng cần phân biệt **device identifier**, **device fingerprint**, **device registration** và **device attestation**.

### 4.1 Device identifier và cookie thiết bị

Một ứng dụng có thể cấp một identifier ngẫu nhiên cho browser sau khi đăng nhập thành công và lưu trong cookie có bảo vệ. Khi request sau gửi identifier đó, hệ thống biết browser này đã từng được ghi nhận.

Giới hạn:

- Cookie có thể bị xóa, sao chép hoặc đánh cắp.
- Người dùng có thể đổi browser profile hoặc cài lại ứng dụng.
- Một thiết bị dùng chung có thể phục vụ nhiều người.
- Identifier chỉ là tín hiệu liên tục, không phải bằng chứng người dùng đang cầm thiết bị.

Không dùng device cookie như yếu tố xác thực độc lập nếu chưa có cơ chế chứng minh quyền sở hữu khóa.

### 4.2 Device fingerprint

Fingerprint có thể kết hợp các thuộc tính như browser version, hệ điều hành, màn hình, locale, timezone hoặc đặc điểm runtime. Những thuộc tính này có thể thay đổi, trùng giữa nhiều người và bị giả mạo.

Rủi ro:

- Dùng fingerprint để theo dõi người dùng ngoài mục đích đã thông báo.
- Nhận diện nhầm thiết bị sau khi cập nhật browser hoặc hệ điều hành.
- Tạo dấu vết ổn định có thể liên kết hoạt động qua nhiều dịch vụ.
- Attacker có thể mô phỏng hoặc sửa các thuộc tính client.

Vì vậy fingerprint nên được dùng như tín hiệu xác suất, có thời hạn và giới hạn mục đích; không dùng làm định danh tuyệt đối.

### 4.3 Device registration và attestation

Một thiết bị có thể đăng ký public key hoặc chứng chỉ với tài khoản. Request sau đó chứng minh quyền kiểm soát private key tương ứng. Đây là bằng chứng mạnh hơn một fingerprint thuần túy, nhưng vẫn cần kiểm tra:

- Khóa có gắn đúng tài khoản và thiết bị không?
- Khóa còn active, chưa bị thu hồi và đúng mục đích không?
- Attestation có được xác minh theo chain, policy và metadata phù hợp không?
- Thiết bị có thực hiện user verification nếu policy yêu cầu không?
- Quy trình mất thiết bị và recovery có an toàn không?

Attestation có thể cung cấp tín hiệu về nguồn gốc hoặc trạng thái thiết bị, nhưng không phải lời đảm bảo rằng thiết bị hiện tại không bị malware hoặc người dùng hợp pháp đang điều khiển.

## 5. Tín hiệu mạng (network signals)

Tín hiệu mạng thường dễ thu thập và hữu ích cho phát hiện bất thường, nhưng không nên dùng một mình để quyết định danh tính.

### 5.1 IP address và ASN

IP có thể cho biết request đến từ một địa chỉ hoặc mạng cụ thể. ASN giúp nhóm IP theo nhà mạng, cloud provider hoặc tổ chức sở hữu mạng.

Có thể phát hiện:

- Một tài khoản thường truy cập từ mạng gia đình nhưng nay xuất hiện từ cloud hosting.
- Nhiều tài khoản thử đăng nhập từ cùng một dải IP.
- Một địa chỉ IP có lịch sử credential stuffing hoặc bot traffic.
- Một workload gọi API từ mạng ngoài vùng triển khai dự kiến.

Giới hạn:

- NAT khiến nhiều người chia sẻ cùng IP.
- Mạng di động và ISP thay IP thường xuyên.
- VPN doanh nghiệp có thể đưa người dùng qua một điểm tập trung.
- Cloud egress có thể hợp lệ với workload.
- Proxy và reverse proxy làm IP quan sát được khác IP thiết bị.
- IP reputation có thể cũ hoặc phân loại sai.

Nếu ứng dụng đứng sau proxy, chỉ tin forwarded IP header từ proxy đã được cấu hình tin cậy. Không tin **X-Forwarded-For** do client gửi trực tiếp.

### 5.2 VPN, proxy và Tor

VPN hoặc proxy có thể là tín hiệu bất thường trong một số bối cảnh, nhưng không mặc nhiên là hành vi xấu. Nhân viên làm việc từ xa, người dùng bảo vệ quyền riêng tư hoặc mạng doanh nghiệp có thể dùng VPN hợp lệ.

Policy nên xem xét loại hành động, lịch sử tài khoản, assurance và tín hiệu khác. Tránh chặn toàn bộ người dùng chỉ vì IP thuộc VPN/Tor nếu chưa có đánh giá tác động và yêu cầu rõ.

### 5.3 TLS và client certificate

Một số workload dùng mTLS để chứng minh client có private key tương ứng với chứng chỉ. Điều này có thể là bằng chứng ràng buộc request với workload identity. Tuy nhiên, chứng chỉ hết hạn, bị thu hồi, dùng sai audience hoặc private key bị lộ đều làm thay đổi đánh giá.

Đối với browser user, TLS session hoặc IP không thay thế authentication. TLS bảo vệ kênh và xác thực server; mTLS client certificate chỉ có ý nghĩa theo cách ứng dụng đăng ký, xác minh và gắn certificate với chủ thể.

## 6. Tín hiệu vị trí và impossible travel

Vị trí có thể được suy ra từ IP geolocation, GPS hoặc dữ liệu thiết bị được cấp quyền. Các nguồn này có độ chính xác và quyền riêng tư khác nhau.

### 6.1 IP geolocation

IP geolocation thường chỉ cho biết vùng ước lượng, không phải vị trí chính xác. Cơ sở dữ liệu có thể chậm cập nhật, đặc biệt với mạng di động, VPN, proxy và cloud.

Không nên hiển thị hoặc ghi nhận vị trí IP như thể đó là địa chỉ thực của người dùng.

### 6.2 GPS hoặc vị trí thiết bị

GPS có thể chính xác hơn trong điều kiện phù hợp, nhưng:

- Chỉ có khi ứng dụng được cấp quyền.
- Có thể bị giả lập trên thiết bị đã bị kiểm soát.
- Không nên thu thập liên tục nếu chỉ cần đánh giá đăng nhập.
- Có thể tiết lộ dữ liệu nhạy cảm về sinh hoạt và nơi ở.

Nếu không cần tọa độ chính xác, hãy giảm độ phân giải thành vùng hoặc nhóm địa lý.

### 6.3 Impossible travel

Impossible travel là tín hiệu khi hai sự kiện của cùng tài khoản xuất hiện ở các vùng cách xa nhau trong khoảng thời gian không đủ để di chuyển hợp lý.

Ví dụ:

- 09:00, IP được suy ra ở Hà Nội.
- 09:12, request khác được suy ra ở một quốc gia cách xa hàng nghìn kilomet.

Đây có thể là dấu hiệu session/token bị chia sẻ hoặc chiếm đoạt, nhưng cũng có thể do VPN, proxy, mạng di động, định tuyến hoặc dữ liệu geolocation sai.

Cách xử lý tốt:

1. Xác định chất lượng và nguồn của hai vị trí.
2. Tính đến thời gian, khoảng cách và sai số.
3. Kiểm tra session/device continuity, phương thức xác thực và hoạt động khác.
4. Dùng như một tín hiệu tăng rủi ro, không phải kết luận gian lận.
5. Với hành động nhạy cảm, yêu cầu step-up hoặc xác minh bổ sung.

## 7. Tín hiệu hành vi (behavioral signals)

Tín hiệu hành vi mô tả cách tài khoản hoặc người dùng tương tác với ứng dụng theo thời gian.

Ví dụ:

- Nhịp và khoảng dừng khi nhập thông tin.
- Tốc độ chuyển trang hoặc gọi endpoint.
- Chuỗi thao tác thường gặp.
- Thời điểm hoạt động theo lịch sử.
- Cách sử dụng chức năng hoặc thứ tự hành động.
- Mẫu tương tác của workload hoặc automation.

### Giới hạn và rủi ro

Hành vi thay đổi tự nhiên khi người dùng:

- Dùng thiết bị mới hoặc công nghệ hỗ trợ.
- Bị thương, mệt mỏi hoặc thay đổi môi trường làm việc.
- Học một quy trình mới.
- Dùng mạng chậm hoặc browser khác.
- Được hỗ trợ bởi người khác theo cách hợp lệ.

Behavioral biometrics có thể là dữ liệu nhạy cảm. Không thu thập phím gõ, chuyển động chuột hoặc đặc điểm sinh học chi tiết nếu không có mục đích, thông báo, cơ sở xử lý và biện pháp bảo vệ phù hợp.

Tín hiệu hành vi nên được dùng để phát hiện thay đổi bất thường hoặc hỗ trợ step-up; không dùng để kết luận danh tính chắc chắn và không làm cơ chế duy nhất để từ chối truy cập.

## 8. Tín hiệu tốc độ và tần suất (velocity signals)

Velocity signal đo số lượng hoặc tốc độ sự kiện trong một cửa sổ thời gian.

Ví dụ:

- 20 lần đăng nhập thất bại cho một tài khoản trong 5 phút.
- Một IP thử 100 username khác nhau trong 1 phút.
- Một tài khoản yêu cầu 15 lần gửi OTP trong 3 phút.
- Một API key gọi endpoint export liên tục vượt baseline.
- Một thiết bị tạo nhiều phiên mới trong thời gian ngắn.

### Những chiều nên đo

| Chiều | Ví dụ | Phát hiện |
| --- | --- | --- |
| Theo tài khoản | Failed logins/user/minute | Brute force hoặc credential stuffing. |
| Theo IP/ASN | Distinct accounts/IP/window | Password spraying, bot traffic. |
| Theo thiết bị | Accounts/device/window | Device farm hoặc automation. |
| Theo endpoint | OTP/reset requests/window | Abuse chức năng recovery. |
| Theo tenant | Requests/tenant/window | Sự cố tích hợp hoặc tấn công diện rộng. |
| Theo credential | Failed token/API key validations | Credential guessing hoặc key misuse. |

### Chọn cửa sổ và ngưỡng

Cửa sổ quá ngắn có thể bỏ sót tấn công chậm; quá dài có thể làm tăng false positive khi người dùng hợp lệ có hoạt động dồn dập.

Có thể kết hợp:

- Fixed window để dễ tổng hợp.
- Sliding window để giảm hiệu ứng ranh giới cửa sổ.
- Token bucket/leaky bucket để rate limit.
- Count distinct subjects để phát hiện password spraying.
- Ngưỡng khác nhau theo tài khoản, IP, tenant và endpoint.

Không nên chỉ giới hạn theo IP vì attacker có thể phân tán qua nhiều địa chỉ, trong khi người dùng hợp lệ có thể chia sẻ NAT.

## 9. Lịch sử tài khoản và tín hiệu vòng đời credential

Lịch sử tài khoản có thể giúp phát hiện thay đổi rủi ro:

- Vừa đổi mật khẩu hoặc passkey.
- Vừa thêm hoặc xóa authenticator.
- Có recovery hoặc reset password gần đây.
- Có nhiều lần thất bại hoặc khóa tài khoản.
- Có phiên mới từ thiết bị chưa biết.
- Có thay đổi email/phone khôi phục.
- Có cảnh báo đăng nhập hoặc token compromise.
- Tài khoản vừa được mở khóa hoặc thay đổi trạng thái từ provisioning.

Các sự kiện này cần được lưu theo thời gian, nguồn và kết quả. Không chỉ ghi một cờ recently changed; policy cần biết thay đổi nào, do ai yêu cầu, bằng phương thức nào và có được xác thực lại không.

### Ví dụ

Một tài khoản vừa khôi phục bằng email hỗ trợ, sau đó trong vòng vài phút yêu cầu thêm passkey và đổi email khôi phục. Mỗi hành động có thể hợp lệ riêng lẻ, nhưng chuỗi sự kiện có thể tạo rủi ro account takeover. Hệ thống có thể áp cooling-off period, yêu cầu step-up mạnh hơn hoặc review trước khi cho phép thay đổi tiếp.

Không được dùng recovery event để kết luận tài khoản bị chiếm; đó là tín hiệu cần policy phù hợp và đường hỗ trợ cho người dùng hợp pháp.

## 10. Authentication context như một nhóm tín hiệu

Authentication context mô tả bằng chứng xác thực đã được xác minh, ví dụ:

- Issuer và subject.
- Thời điểm xác thực.
- Phương thức và yếu tố.
- ACR/AMR hoặc SAML AuthnContext theo mapping đã thống nhất.
- User verification, phishing resistance và transaction binding.
- Recovery/fallback có được sử dụng không.
- Session và credential reference.

Context thường có giá trị cao hơn một signal client tự khai, nhưng chỉ khi nguồn phát hành được tin cậy và validation thành công.

Ví dụ:

- Một passkey assertion hợp lệ với RP ID/origin đúng là bằng chứng khác với một cookie device fingerprint.
- Một ID token có auth_time cũ không chứng minh người dùng vừa xác thực lại, dù iat mới.
- Một kết quả MFA từ issuer chưa được onboard không nên tự động được ánh xạ thành assurance cao.
- Một phiên được khôi phục bằng quy trình hỗ trợ cần giữ rõ trạng thái recovery.

RBA nên sử dụng context để đánh giá **mức bằng chứng đã có**, đồng thời dùng các signal còn lại để đánh giá **mức rủi ro của request**.

## 11. Nguồn gốc, độ tin cậy và độ mới của tín hiệu

Không phải mọi signal đều có cùng chất lượng. Mỗi tín hiệu nên có metadata tối thiểu để policy engine hiểu nó đến từ đâu và còn đáng tin hay không.

### Thuộc tính nên quản lý

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Source | Nguồn phát hành hoặc thành phần thu thập. | Server authentication service, trusted proxy, device SDK. |
| ObservedAt | Thời điểm quan sát. | IP được ghi nhận tại thời điểm request. |
| ValidUntil / TTL | Thời gian tín hiệu còn hữu ích. | Reputation snapshot chỉ dùng trong một khoảng thời gian. |
| Integrity | Dữ liệu có được xác minh hoặc bảo vệ chống sửa không? | Signed attestation, validated token claim. |
| Confidence | Mức tin cậy hoặc chất lượng dữ liệu theo định nghĩa nội bộ. | High/medium/low với tiêu chí rõ. |
| Scope | Tín hiệu áp dụng cho tài khoản, thiết bị, phiên hay tenant nào. | Device signal gắn với một credential. |
| Version | Phiên bản nguồn hoặc thuật toán tạo signal. | GeoIP database version, model version. |
| Limitations | Giới hạn đã biết. | IP có thể là NAT/VPN; fingerprint có thể thay đổi. |

Confidence không nên là một con số tùy ý không có định nghĩa. Nếu sử dụng điểm tin cậy, cần biết nó được hiệu chuẩn như thế nào, đo lường bằng dữ liệu nào và có thể so sánh giữa nguồn nào.

### Signal stale hoặc missing

- Signal cũ cần giảm trọng số hoặc bỏ qua theo policy.
- Signal thiếu không đồng nghĩa rủi ro cao.
- Provider lỗi không được tự động biến thành safe.
- Provider lỗi cũng không nhất thiết phải khóa mọi người dùng; cần fallback theo mức nhạy cảm.
- Lưu rõ trạng thái unavailable, stale, invalid hoặc not-applicable.

Không thay giá trị không biết bằng giá trị mặc định trusted. Missing data cần có ngữ nghĩa riêng.

## 12. Kết hợp tín hiệu và risk scoring

Một risk engine có thể kết hợp nhiều tín hiệu thành một score hoặc phân loại như low, medium, high. Score chỉ là đầu vào cho policy.

### Ví dụ bảng đánh giá

| Tín hiệu | Hướng tác động ví dụ | Lưu ý |
| --- | --- | --- |
| Passkey assertion hợp lệ, user verification đạt | Giảm nghi ngờ về việc credential bị giả mạo. | Không loại bỏ malware hoặc account recovery abuse. |
| Thiết bị đã đăng ký, key proof hợp lệ | Có thể giảm rủi ro thiết bị lạ. | Cần kiểm tra khóa chưa bị thu hồi. |
| IP reputation xấu | Tăng nghi ngờ. | Reputation có thể false positive hoặc stale. |
| Nhiều lần login thất bại | Tăng nghi ngờ. | Có thể do người dùng quên mật khẩu. |
| Vị trí bất thường | Tăng nghi ngờ ở mức phù hợp. | VPN, roaming và GeoIP có thể sai. |
| Recovery vừa diễn ra | Tăng mức kiểm tra cho thay đổi nhạy cảm. | Người dùng hợp lệ vẫn cần đường tiếp cận. |
| Authentication context quá cũ | Không đủ freshness cho hành động nhạy cảm. | Có thể yêu cầu step-up. |
| Tín hiệu mạng không khả dụng | Không xác định. | Không tự gán low risk hoặc high risk. |

### Score không phải xác suất nếu chưa hiệu chuẩn

Một hệ thống có thể tính điểm 0–100, nhưng điểm 80 không có nghĩa xác suất gian lận là 80%. Nếu chưa được hiệu chuẩn trên dữ liệu phù hợp và đánh giá định kỳ, score chỉ là thang xếp hạng nội bộ.

Nếu dùng machine learning:

- Tập huấn luyện cần đại diện cho môi trường sử dụng thực tế.
- Tránh dùng nhãn sai hoặc nhãn phản ánh thiên lệch vận hành trước đây.
- Đánh giá precision, recall, false positive, false negative và calibration.
- Kiểm tra chất lượng theo nhóm người dùng/thiết bị/mạng có liên quan.
- Theo dõi model drift và thay đổi phân phối tín hiệu.
- Có giải thích đủ để đội vận hành hiểu vì sao request bị step-up hoặc chặn.
- Có quy trình rollback và human review cho trường hợp ảnh hưởng lớn.

Không để model tự động khóa tài khoản vĩnh viễn chỉ dựa trên một score không giải thích được.

## 13. Từ risk score đến hành động xác thực

Policy engine chuyển kết quả đánh giá thành hành động. Các mức hành động nên có ngữ nghĩa rõ và phù hợp với hậu quả của request.

| Hành động | Khi nào dùng | Ví dụ |
| --- | --- | --- |
| **Allow** | Tín hiệu và context đáp ứng policy; không có điều kiện chặn. | Đọc nội dung với session hợp lệ. |
| **Monitor** | Có bất thường nhẹ nhưng chưa đủ để cản trở. | Ghi audit tăng cường hoặc theo dõi request tiếp theo. |
| **Rate limit** | Có dấu hiệu automation hoặc thử credential quá nhanh. | Giới hạn OTP/reset/login attempts. |
| **Step-up** | Context chưa đủ mạnh/mới hoặc có tín hiệu rủi ro cần xác minh thêm. | Yêu cầu passkey hoặc MFA trước khi đổi email. |
| **Hold / Review** | Hành động có hậu quả cao và tín hiệu cần người hoặc quy trình bổ sung kiểm tra. | Tạm giữ thay đổi payout hoặc quyền quản trị. |
| **Deny** | Bằng chứng xác thực không hợp lệ hoặc policy cấm request. | Token sai chữ ký, tài khoản bị khóa, replay đã xác nhận. |

Không nên biến mọi signal lạ thành deny. Step-up có thể giúp người dùng hợp pháp tiếp tục, trong khi rate limit và monitor phù hợp với abuse traffic. Tuy nhiên, nếu credential/token không hợp lệ hoặc account bị revoked, không được dùng step-up để bỏ qua lỗi xác minh nền tảng.

### Ví dụ policy theo rủi ro và hành động

~~~text
if credential_or_token_invalid:
    DENY

else if account_disabled_or_session_revoked:
    DENY

else if velocity_abuse_confirmed:
    RATE_LIMIT_OR_DENY

else if sensitive_action and context_not_fresh:
    STEP_UP

else if high_risk_signals and step_up_available:
    STEP_UP

else if medium_risk_signals:
    MONITOR

else:
    ALLOW
~~~

Đây là pseudocode khái niệm. Policy thật cần quy định thứ tự ưu tiên, ngoại lệ, giới hạn thử lại, xử lý provider unavailable và cách bảo vệ khỏi downgrade.

## 14. Kiến trúc thu thập và đánh giá tín hiệu

Một kiến trúc thường tách thu thập signal khỏi quyết định policy:

~~~mermaid
flowchart TD
    R["Login hoặc sensitive request"] --> C["Context collector"]
    C --> D["Device signals"]
    C --> N["Network signals"]
    C --> L["Location signals"]
    C --> B["Behavior / velocity"]
    C --> H["Account history"]
    C --> A["Verified authentication context"]
    D --> S["Signal normalization"]
    N --> S
    L --> S
    B --> S
    H --> S
    A --> S
    S --> Q["Quality, freshness, provenance"]
    Q --> E["Risk engine / policy evaluation"]
    E --> P{"Action"}
    P -->|"Allow"| AL["Continue authorization"]
    P -->|"Monitor"| M["Audit / observe"]
    P -->|"Rate limit"| RL["Throttle"]
    P -->|"Step-up"| U["Additional authentication"]
    P -->|"Hold / deny"| X["Review or reject"]
    U --> V["Verify new context"]
    V --> E
~~~

### Trình tự xử lý gợi ý

1. Xác minh credential/token/session cơ bản.
2. Xác định subject, tenant, action và resource.
3. Thu thập các signal có sẵn theo policy.
4. Chuẩn hóa format, source, timestamp và quality.
5. Bỏ qua hoặc giảm ảnh hưởng của signal stale/invalid/unavailable.
6. Tính risk classification/score.
7. Áp policy theo hậu quả và assurance cần thiết.
8. Nếu step-up, xác minh kết quả mới và đánh giá lại.
9. Thực thi authorization trên resource/action.
10. Ghi audit với lý do và signal reference đã tối thiểu hóa.

Risk engine không nên được quyền bỏ qua lỗi xác thực. Hệ thống cần fail closed đối với chữ ký/token sai, subject mismatch hoặc revoked credential; còn với signal phụ trợ không khả dụng thì fallback theo policy rủi ro.

## 15. Quyền riêng tư, công bằng và giải thích quyết định

Risk-based authentication có thể xử lý dữ liệu cá nhân và dữ liệu nhạy cảm. Một thiết kế tốt cần giới hạn thu thập và giảm tác động của quyết định sai.

### Nguyên tắc bảo vệ dữ liệu

- Xác định mục đích cho từng signal trước khi thu thập.
- Thu thập ít nhất mức dữ liệu cần thiết.
- Giới hạn thời gian lưu và quyền truy cập.
- Mã hóa dữ liệu nhạy cảm khi lưu/truyền.
- Không đưa raw IP, GPS, fingerprint chi tiết hoặc behavioral trace vào log công khai.
- Cung cấp thông tin phù hợp về việc xử lý dữ liệu và lựa chọn theo luật/chính sách.
- Có quy trình xóa, sửa hoặc giới hạn dữ liệu theo yêu cầu hợp lệ.
- Không tái sử dụng signal cho quảng cáo hoặc profiling ngoài mục đích đã công bố.

### False positive và công bằng

Một người đi công tác, dùng mạng di động, VPN, thiết bị hỗ trợ hoặc browser riêng tư có thể khác baseline. Nếu hệ thống liên tục chặn những trường hợp này, nó tạo ra bất tiện và có thể tác động không đồng đều tới nhóm người dùng.

Cần:

- Đo false positive theo từng loại signal và nhóm liên quan.
- Có phương án step-up dễ tiếp cận.
- Không phụ thuộc vào một tín hiệu dễ bất lợi cho người dùng có mạng/thiết bị khác thường.
- Cho phép support review khi cần, với quy trình bảo vệ tài khoản.
- Theo dõi tỷ lệ challenge, abandon, lockout và khiếu nại.
- Định kỳ kiểm tra model/policy drift.

### Giải thích đủ dùng

Khi yêu cầu step-up, có thể thông báo rằng hoạt động đăng nhập có một số điểm khác với thông thường và cần xác minh bổ sung. Không nhất thiết tiết lộ ngưỡng phát hiện, indicator nội bộ hoặc logic có thể giúp attacker né tránh.

Audit nội bộ nên ghi policy version, action, lý do ở mức phân loại, signal source/reference, thời điểm và kết quả step-up; không ghi bí mật xác thực hoặc dữ liệu thô không cần thiết.

## 16. Ví dụ thực tế: đăng nhập nền tảng học tập

Learning Platform muốn phát hiện account takeover mà vẫn cho phép học viên đăng nhập khi đi học ở nơi khác.

### Tình huống A: request quen thuộc

- Thiết bị có khóa đã đăng ký và proof hợp lệ.
- Passkey assertion hợp lệ, RP ID/origin đúng.
- Authentication context đáp ứng policy.
- Không có bất thường velocity.
- IP thuộc mạng di động có thể thay đổi nhưng không có indicator xấu.

Policy có thể cho phép sau khi kiểm tra trạng thái tài khoản và quyền.

### Tình huống B: thiết bị mới, mạng lạ

- Browser chưa có device registration.
- IP ở quốc gia khác với lịch sử gần đây.
- Không có bằng chứng credential bị lộ.
- Người dùng có thể hoàn tất passkey step-up.

Hệ thống có thể yêu cầu xác minh bổ sung, gửi thông báo bảo mật và ghi nhận thiết bị sau khi người dùng xác thực theo policy. Không nên tự động khóa chỉ vì quốc gia khác.

### Tình huống C: dấu hiệu credential stuffing

- Một IP/ASN thử nhiều username.
- Nhiều lần password failure trong thời gian ngắn.
- Có các request reset/OTP bất thường.
- Nhiều account có mẫu request giống nhau.

Policy có thể rate limit theo nhiều chiều, chặn automation đã xác nhận và yêu cầu step-up cho các request có nguy cơ. Cần tránh khóa hàng loạt tài khoản nạn nhân chỉ vì attacker thử mật khẩu của họ.

### Tình huống D: phiên cũ yêu cầu đổi email khôi phục

- Session còn active nhưng auth_time đã cũ.
- Request đến từ device chưa từng thấy.
- Tài khoản vừa recovery gần đây.
- Hành động ảnh hưởng kênh khôi phục.

Policy nên yêu cầu step-up chống phishing, ràng buộc xác nhận với transaction, áp cooling-off nếu cần và thông báo qua kênh cũ. Nếu context không đạt, từ chối thay đổi dù session cookie vẫn hợp lệ.

## 17. Kiểm thử tín hiệu và policy

| Kịch bản | Cách kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| Device identifier mới | Đăng nhập từ browser chưa được ghi nhận. | Signal mới được tạo; policy đánh giá theo context và action. |
| Device cookie bị sao chép | Dùng cookie từ thiết bị khác trong môi trường test. | Không coi cookie đơn lẻ là bằng chứng xác thực. |
| Fingerprint thay đổi sau update | Thay browser/OS version. | Không tự động kết luận account takeover. |
| IP qua trusted proxy | Gửi request qua proxy đã cấu hình. | Chỉ dùng forwarded address từ proxy tin cậy. |
| Client giả X-Forwarded-For | Gửi header giả từ Internet. | Header không được tin nếu request không đến từ trusted proxy. |
| VPN hợp lệ | Đăng nhập qua VPN doanh nghiệp. | Đánh giá kết hợp, không tự động deny chỉ vì VPN. |
| Impossible travel | Tạo hai event xa nhau trong thời gian ngắn. | Tăng risk signal; xác minh thêm nguồn và context. |
| GeoIP stale | Dùng dữ liệu vị trí cũ/không rõ. | Hạ confidence hoặc đánh dấu stale. |
| Velocity burst | Gửi nhiều login/OTP requests trong cửa sổ ngắn. | Rate limit/challenge theo dimension phù hợp. |
| Distributed credential stuffing | Phân tán request qua nhiều IP. | Theo dõi account/device/ASN/tenant, không chỉ IP. |
| Behavior drift hợp lệ | Người dùng đổi thiết bị hoặc công nghệ hỗ trợ. | Không khóa tự động; có fallback step-up. |
| Auth context stale | Session active nhưng auth_time quá cũ. | Step-up cho action yêu cầu freshness. |
| Signal provider unavailable | GeoIP/reputation API timeout. | Ghi unavailable; áp fallback policy rõ ràng. |
| Signal replay | Dùng lại device proof hoặc event cũ. | Kiểm tra nonce, timestamp, transaction và replay cache nếu protocol yêu cầu. |
| Contradictory signals | IP quen thuộc nhưng device/key proof không hợp lệ. | Lỗi bằng chứng xác thực vẫn bị từ chối; không lấy score thấp để bỏ qua. |
| Risk score thấp nhưng token sai chữ ký | Giả mạo token trong khi các signal khác quen thuộc. | Từ chối vì token invalid. |
| Risk score cao nhưng step-up đạt | Người dùng hợp pháp xác minh bằng phương thức được policy chấp nhận. | Đánh giá lại; chỉ cho phép nếu các điều kiện khác đạt. |
| Policy/model version thay đổi | Chạy cùng tập test với version mới. | So sánh false positive/negative và khả năng giải thích trước rollout. |

## 18. Checklist thiết kế risk signals

- [ ] Đã xác định mục tiêu và hành động mà RBA bảo vệ.
- [ ] Mỗi signal có source, observed time, scope, freshness và giới hạn đã biết.
- [ ] Phân biệt signal do client khai với bằng chứng server-side đã xác minh.
- [ ] Device fingerprint không được coi là định danh hoặc yếu tố xác thực tuyệt đối.
- [ ] Device registration/attestation được xác minh theo policy và có revocation.
- [ ] Network signals xử lý đúng trusted proxy, NAT, VPN, mobile network và cloud egress.
- [ ] GeoIP/GPS có mức chính xác và giới hạn quyền riêng tư rõ.
- [ ] Impossible travel chỉ là tín hiệu, không phải kết luận tự động.
- [ ] Velocity đo theo account, IP, device, endpoint, tenant và credential khi phù hợp.
- [ ] Authentication context được kiểm tra issuer, subject, method, assurance và freshness.
- [ ] Risk score được phân biệt với assurance và không gọi là xác suất nếu chưa hiệu chuẩn.
- [ ] Có action policy allow, monitor, rate limit, step-up, hold và deny.
- [ ] Lỗi xác thực nền tảng không bị risk score thấp bỏ qua.
- [ ] Có fallback khi signal provider unavailable hoặc stale.
- [ ] Có đo false positive/negative, model drift và tác động theo nhóm người dùng.
- [ ] Có giới hạn dữ liệu, retention, access control và redaction.
- [ ] Có audit lý do quyết định mà không lưu raw secret hoặc dữ liệu thừa.
- [ ] Có quy trình review, rollback và hỗ trợ người dùng bị challenge nhầm.

## 19. Tự kiểm tra

**Câu 1.** Risk signal có chứng minh người gửi request là chủ tài khoản không?

**Đáp án:** Không. Signal chỉ cung cấp thông tin bối cảnh để đánh giá rủi ro. Danh tính cần được xác minh bằng credential hoặc bằng chứng được tin cậy.

**Câu 2.** Thiết bị mới có đồng nghĩa account takeover không?

**Đáp án:** Không. Người dùng có thể đổi điện thoại, cài lại browser hoặc sử dụng máy tính khác. Thiết bị mới là tín hiệu cần kết hợp với context và hành động.

**Câu 3.** Vì sao IP quen thuộc không đủ để cho phép đăng nhập?

**Đáp án:** Nhiều người có thể dùng chung NAT/VPN, IP có thể bị chia sẻ hoặc attacker có thể truy cập từ mạng quen thuộc. Vẫn phải xác minh credential và policy.

**Câu 4.** Impossible travel có thể tạo false positive vì lý do nào?

**Đáp án:** VPN, proxy, mạng di động, định tuyến và dữ liệu GeoIP sai có thể khiến vị trí quan sát không phản ánh vị trí thật.

**Câu 5.** Tại sao không nên tin X-Forwarded-For từ mọi request?

**Đáp án:** Client có thể tự đặt header. Chỉ tin forwarded IP do proxy đã được cấu hình tin cậy ghi hoặc chuẩn hóa.

**Câu 6.** Risk score 90 có nghĩa xác suất gian lận là 90% không?

**Đáp án:** Không, trừ khi score được hiệu chuẩn và có ý nghĩa xác suất được chứng minh. Thông thường nó chỉ là thang xếp hạng nội bộ.

**Câu 7.** Nếu GeoIP provider lỗi, hệ thống nên gán low risk hay high risk?

**Đáp án:** Không tự gán một trong hai. Ghi signal unavailable và áp fallback policy theo mức nhạy cảm, các signal còn lại và yêu cầu availability.

**Câu 8.** Vì sao auth_time quan trọng hơn token iat khi kiểm tra freshness?

**Đáp án:** iat là thời điểm token được phát hành; auth_time là thời điểm người dùng thực sự xác thực theo ngữ nghĩa của issuer. Token mới có thể được cấp bằng refresh mà không có xác thực mới.

**Câu 9.** Khi một signal lạ xuất hiện, hành động duy nhất có nên là deny không?

**Đáp án:** Không. Có thể monitor, rate limit, step-up hoặc hold tùy chất lượng signal, mức rủi ro, hậu quả và khả năng xác minh thêm. Token/credential không hợp lệ vẫn phải bị từ chối.

**Câu 10.** Vì sao cần đo false positive và tác động theo nhóm người dùng?

**Đáp án:** Một policy có thể ảnh hưởng không đồng đều tới người dùng có mạng, thiết bị hoặc cách tương tác khác nhau. Đo lường giúp phát hiện chặn nhầm, giảm bất công và cải thiện khả năng tiếp cận.

## Ghi nhớ

**Risk signal** là dữ liệu bối cảnh giúp hệ thống đánh giá request có bất thường hoặc nguy cơ lạm dụng hay không. Các nhóm phổ biến gồm thiết bị, mạng, vị trí, hành vi, velocity, lịch sử tài khoản, threat intelligence và authentication context. Mỗi signal cần có nguồn gốc, độ mới, phạm vi, chất lượng và giới hạn rõ ràng.

Không coi IP, fingerprint, vị trí hoặc hành vi là bằng chứng danh tính tuyệt đối. Kết hợp nhiều tín hiệu với context đã xác minh, đánh giá theo hành động và hậu quả, rồi chọn allow, monitor, rate limit, step-up, hold hoặc deny. Bảo vệ quyền riêng tư, đo false positive/negative, giải thích quyết định và có fallback khi dữ liệu thiếu hoặc provider lỗi. **RBA giúp điều chỉnh mức kiểm tra theo rủi ro; nó không được phép thay thế xác minh credential và authorization.**
