# Risk score — Xây dựng và sử dụng điểm rủi ro trong xác thực

Một người dùng đăng nhập bằng mật khẩu đúng nhưng từ thiết bị mới, qua mạng proxy lạ, ngay sau nhiều lần thử mật khẩu thất bại trên cùng tài khoản. Hệ thống có thể cho đăng nhập ngay, yêu cầu xác thực bổ sung hoặc tạm dừng thao tác nhạy cảm. Quyết định đó không nên dựa vào một tín hiệu đơn lẻ. **Risk score (điểm rủi ro)** là cách tổng hợp nhiều tín hiệu về lần truy cập, tài khoản, thiết bị, mạng và hành vi để hỗ trợ chọn biện pháp kiểm soát phù hợp.

Điểm rủi ro không phải điểm tin cậy danh tính, không phải mức bảo đảm xác thực và cũng không phải quyền truy cập. Nó là một đầu vào của policy engine để đánh giá khả năng hoặc mức độ nghiêm trọng của một sự kiện không mong muốn, chẳng hạn account takeover, credential stuffing, token theft hay lạm dụng phiên. Một điểm số cao không tự chứng minh người dùng là attacker; một điểm thấp không bảo đảm request an toàn.

Bài học thuộc chương **Risk-based authentication** của học phần **SECURITY_AUTHENTICATION_FUNDAMENTALS**. Nội dung liên hệ risk score với credential, mật khẩu, MFA, passkey, chứng chỉ, token, phiên, liên kết danh tính và khôi phục tài khoản. Người học sẽ biết phân loại tín hiệu, xây dựng quy tắc/mô hình, hiệu chỉnh ngưỡng, giải thích quyết định và phòng chống lạm dụng mà vẫn hạn chế false positive, thiên lệch và thu thập dữ liệu quá mức.

## 1. Kết quả học tập

Sau bài này, người học có thể:

- Giải thích risk score và phân biệt risk score, confidence score, identity assurance, authentication assurance và authorization.
- Phân loại tín hiệu theo credential, thiết bị, mạng/vị trí, hành vi, phiên/token và ngữ cảnh nghiệp vụ.
- Đánh giá chất lượng tín hiệu theo nguồn, độ mới, độ tin cậy, khả năng giả mạo và mức thiếu dữ liệu.
- Thiết kế rule-based scoring hoặc mô hình thống kê/học máy phù hợp với dữ liệu và rủi ro.
- Chọn ngưỡng theo chi phí của false accept, false reject, step-up và review.
- Thiết kế policy nhiều mức: allow, step-up, limit, hold/review và block/revoke.
- Hiểu calibration, drift, feedback loop, adversarial adaptation và giới hạn của mô hình.
- Giải thích quyết định cho người dùng/vận hành mà không tiết lộ quy tắc đủ để attacker né tránh.
- Bảo vệ quyền riêng tư, đánh giá fairness và có cơ chế appeal/alternative authentication.
- Viết tiêu chí kiểm thử cho scoring, dữ liệu thiếu, spoofing, replay, concurrency và phản ứng sau compromise.

## 2. Risk score là gì?

Risk score là giá trị do hệ thống tính từ các tín hiệu liên quan đến một sự kiện, ví dụ một lần đăng nhập, một lần refresh token, thay đổi thông tin recovery hoặc giao dịch có yêu cầu xác thực lại. Giá trị có thể là:

- **Ordinal score:** mức thấp/vừa/cao hoặc thang điểm nội bộ như 0–100.
- **Model score:** đầu ra của một mô hình phân loại/ranking, chưa chắc là xác suất.
- **Calibrated probability:** ước lượng xác suất của một outcome cụ thể trong một khoảng thời gian/ngữ cảnh đã định nghĩa.

Không gọi một số từ 0 đến 100 là “xác suất bị hack” nếu mô hình chưa được calibration và chưa xác định rõ outcome, population, time horizon. Điểm 80 có thể chỉ là mức rủi ro tương đối cao theo policy nội bộ; nó không có nghĩa 80% người dùng là attacker.

### 2.1. Xác định đúng outcome

Trước khi chấm điểm, cần xác định hệ thống đang dự đoán/đánh giá điều gì:

- Khả năng lần đăng nhập là credential stuffing.
- Khả năng phiên hiện tại đã bị chiếm.
- Nguy cơ token bị replay hoặc refresh token reuse.
- Rủi ro của một thao tác như đổi email, thêm passkey hoặc chuyển tiền.
- Mức cần step-up để bảo vệ một tài nguyên có giá trị cao.

Các outcome này không giống nhau. Một lần đăng nhập từ thiết bị mới có thể có rủi ro thấp với tài khoản đọc tin công khai nhưng rủi ro cao nếu nó có thể thêm credential quản trị hoặc thay đổi tài khoản thanh toán.

### 2.2. Đơn vị đánh giá

Risk score cần gắn với một đối tượng và thời điểm rõ:

| Đơn vị | Ví dụ | Điều cần xác định |
| --- | --- | --- |
| Login attempt | Một lần nhập password/passkey | Tín hiệu nào có trước và tại thời điểm xác thực? |
| Session | Phiên web đang hoạt động | Rủi ro có thay đổi theo thời gian/thiết bị không? |
| Token use | Request dùng access/refresh token | Audience, sender binding, replay và token age là gì? |
| Account change | Thêm passkey, đổi email, reset MFA | Mức rủi ro và hậu quả nếu attacker thực hiện thành công? |
| Transaction | Chuyển tiền, xuất dữ liệu, thay quyền | Tài nguyên và tác động cụ thể cần bảo vệ là gì? |

Không dùng một score cũ của lần đăng nhập để quyết định mọi hành động về sau. Risk context có thể thay đổi theo request, thiết bị, token, tài nguyên và thời điểm.

## 3. Phân biệt risk score với các khái niệm khác

| Khái niệm | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| Risk score | Sự kiện này có mức rủi ro nào theo threat model? | Login có thiết bị lạ và dấu hiệu token reuse |
| Confidence score | Hệ thống tin bao nhiêu vào một kết quả/tín hiệu? | IP geolocation có confidence thấp |
| Identity proofing assurance | Danh tính khai báo được chứng minh tới mức nào? | Bằng chứng giấy tờ/eID đã được kiểm tra |
| Authentication assurance | Phiên xác thực dùng phương thức nào và mức bảo đảm ra sao? | Passkey/WebAuthn, MFA, certificate |
| Authorization | Principal được phép làm gì trên tài nguyên nào? | User chỉ có quyền đọc workspace A |
| Fraud score | Khả năng hoặc mức độ gian lận theo một định nghĩa nghiệp vụ | Giao dịch có dấu hiệu mule/fraud |

Một thiết bị mới có thể làm risk score tăng nhưng không làm giảm tính hợp lệ của passkey. Ngược lại, một passkey hợp lệ không tự làm mọi giao dịch có rủi ro thấp. Hệ thống cần giữ riêng kết quả xác thực, mức assurance, risk context và quyết định authorization.

## 4. Các nhóm tín hiệu đầu vào

Risk engine có thể tổng hợp nhiều nhóm tín hiệu. Mỗi nhóm có giới hạn và mức tin cậy khác nhau.

### 4.1. Credential và authentication

- Số lần nhập sai mật khẩu, tốc độ thử và phân bố theo tài khoản/IP/device.
- Mật khẩu vừa được reset, credential bị báo lộ hoặc xuất hiện trong danh sách compromise theo nguồn đáng tin.
- MFA challenge thất bại, bị từ chối hoặc có dấu hiệu fatigue.
- Phương thức xác thực: password, OTP, passkey/WebAuthn, security key, certificate.
- Thời điểm và mức assurance của lần xác thực gần nhất.
- Passkey có user verification hay không, authenticator/device context và chính sách phishing resistance.
- Chứng chỉ hết hạn, bị revoke, chain không hợp lệ hoặc client identity thay đổi.

Không coi password đúng là đủ để bỏ qua mọi tín hiệu khác. Cũng không coi việc OTP được nhập đúng là bằng chứng chắc chắn không có phishing hoặc real-time relay.

### 4.2. Thiết bị và ứng dụng

- Thiết bị mới/quen thuộc, device binding hoặc trạng thái managed.
- OS/browser/app version, integrity signal và patch level nếu có căn cứ.
- Dấu hiệu emulator, automation, tampering hoặc malware theo khả năng quan sát.
- Thay đổi bất thường về cookie/session, browser profile hoặc device key.
- Thiết bị đã bị người dùng báo mất hoặc quản trị viên thu hồi.

Fingerprint thiết bị có thể sai lệch, bị giả mạo và gây tác động quyền riêng tư. Không coi một fingerprint ổn định là định danh phần cứng chắc chắn; cần dùng thiết bị được quản lý hoặc khóa mật mã khi yêu cầu bảo đảm cao.

### 4.3. Mạng và vị trí

- IP reputation, ASN/ISP, loại mạng và hosting provider.
- VPN, proxy, Tor, corporate egress và thay đổi điểm thoát.
- IP geolocation, quốc gia/khu vực ước lượng và impossible travel.
- Rate, số lượng tài khoản thử từ cùng nguồn và phân tán theo mạng.
- Mức tin cậy của forwarded headers và proxy chain.

IP/vị trí là tín hiệu có độ chính xác hữu hạn. VPN công ty, mạng di động, NAT và roaming có thể tạo thay đổi hợp lệ. Không dùng một quốc gia mới làm bằng chứng duy nhất để khóa tài khoản.

### 4.4. Hành vi và lịch sử

- Thời điểm truy cập, tần suất và nhịp thao tác so với baseline.
- Đường đi trong ứng dụng, thao tác nhạy cảm và hành vi tự động.
- Số lần thử đăng nhập, password reset, đổi email hoặc thêm authenticator.
- Hoạt động bất thường sau login, như tải dữ liệu lớn hoặc tạo nhiều token.
- Lịch sử khiếu nại, chargeback, fraud case hoặc incident đã xác nhận.

Behavioral signals có thể phản ánh thay đổi hợp lệ như người dùng đi công tác, đổi công việc hoặc dùng thiết bị trợ năng. Cần kiểm tra false positive và không suy diễn đặc điểm nhạy cảm của cá nhân từ hành vi.

### 4.5. Session và token

- Session age, idle time, absolute lifetime và trạng thái revoke.
- Token issuer, audience, scope, expiry, jti/reference và sender constraint.
- Refresh token rotation/reuse, token family và thiết bị/client.
- Session ID rotation, cookie anomalies và concurrent session behavior.
- Dấu hiệu access token bị sử dụng từ nhiều ngữ cảnh không phù hợp.

Một token có chữ ký hợp lệ vẫn có thể bị đánh cắp. Một phiên đã xác thực đúng lúc ban đầu có thể trở nên rủi ro khi thiết bị bị chiếm hoặc refresh token bị replay.

### 4.6. Ngữ cảnh tài nguyên và nghiệp vụ

- Giá trị/tính nhạy cảm của dữ liệu được yêu cầu.
- Tài khoản thường hay tài khoản đặc quyền.
- Hành động chỉ đọc hay thay đổi không thể đảo ngược.
- Tenant, vai trò, số tiền, người nhận và trạng thái giao dịch.
- Thời điểm, giới hạn, velocity và bất thường so với lịch sử của tài nguyên.

Risk score cần xét hậu quả nếu request sai. Cùng một login context có thể được chấp nhận để xem trang thông tin nhưng yêu cầu step-up trước khi đổi thông tin recovery hoặc chuyển tiền.

## 5. Chất lượng, nguồn và độ mới của tín hiệu

Không phải tín hiệu nào cũng đáng tin như nhau. Mỗi feature cần có metadata để tránh một giá trị sai hoặc cũ chi phối quyết định.

| Thuộc tính | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Source/provenance | Tín hiệu đến từ đâu? | IP socket, trusted proxy, authenticator, vendor |
| Freshness | Tín hiệu được quan sát khi nào? | GPS từ 30 phút trước không phải vị trí hiện tại |
| Confidence/quality | Nguồn có độ chính xác nào? | IP city estimate có sai số cao |
| Coverage | Tín hiệu có mặt ở mọi client không? | Mobile có device posture nhưng browser desktop không có |
| Spoofability | Attacker có thể sửa/giả dễ không? | Header do client tự gửi có thể giả mạo |
| Stability | Tín hiệu thay đổi hợp lệ thường xuyên không? | IP mạng di động thay đổi liên tục |
| Privacy impact | Việc thu thập có xâm phạm quyền riêng tư không? | GPS chính xác và hành vi chi tiết |

### Dữ liệu thiếu không đồng nghĩa rủi ro cao

Thiết bị không hỗ trợ một tín hiệu hoặc người dùng từ chối GPS không nên tự động bị gán điểm rủi ro cao. Hãy phân biệt:

- Signal absent: không có dữ liệu.
- Signal unknown: có dữ liệu nhưng không phân loại được.
- Signal invalid: dữ liệu sai định dạng hoặc không hợp lệ.
- Signal stale: dữ liệu quá cũ.
- Signal suspicious: có bằng chứng cụ thể về bất thường.

Mỗi trạng thái cần cách xử lý riêng. Ví dụ, thiếu GPS có thể không ảnh hưởng nếu hệ thống không cần GPS; một forwarded IP header không đến từ proxy tin cậy phải bị bỏ qua, không dùng làm nguồn xác định client IP.

## 6. Cách xây dựng risk score

Không có một công thức chung cho mọi sản phẩm. Bắt đầu bằng threat model và chính sách; chỉ chọn phương pháp đủ phức tạp cho dữ liệu, quy mô và yêu cầu giải thích.

### 6.1. Rule-based scoring

Rule-based scoring cộng/trừ điểm hoặc gán mức theo điều kiện rõ ràng. Nó dễ giải thích và phù hợp khi dữ liệu ít, threat model tương đối rõ hoặc cần kiểm soát thủ công.

Ví dụ minh họa:

| Tín hiệu | Điểm rủi ro minh họa |
| --- | ---: |
| Thiết bị chưa từng thấy | +15 |
| ASN hosting chưa biết | +10 |
| Nhiều lần đăng nhập thất bại gần đây | +20 |
| Refresh token reuse đã xác nhận | +50 hoặc rule block |
| Passkey/WebAuthn hợp lệ trên thiết bị đã đăng ký | Có thể giảm một phần risk theo policy |
| IP geolocation thiếu/độ tin cậy thấp | Không cộng điểm mặc định |

Các con số chỉ minh họa cách cộng điểm, không phải khuyến nghị production. Không nên cho phép một tín hiệu tốt xóa hoàn toàn một sự kiện compromise rõ ràng. Một số điều kiện nên là hard rule độc lập, chẳng hạn token đã revoke hoặc chữ ký không hợp lệ thì từ chối bất kể tổng điểm.

### 6.2. Weighted score

Một mô hình đơn giản có thể dùng:

~~~text
raw_score = Σ(weight_i × normalized_feature_i)
~~~ 

Trong đó:

- Feature được chuẩn hóa theo định nghĩa rõ ràng.
- Weight phản ánh mức liên quan tới outcome, được hiệu chỉnh bằng dữ liệu/đánh giá.
- Không đưa trực tiếp dữ liệu thô nhạy cảm vào công thức nếu không cần.
- Các feature tương quan cao cần được xử lý để tránh đếm cùng một sự kiện nhiều lần.

Weighted score vẫn có thể bị sai nếu weight chỉ do trực giác đặt ra, dữ liệu thiên lệch hoặc feature bị attacker thao túng. Cần kiểm tra theo kịch bản và outcome thật.

### 6.3. Statistical/ML model

Mô hình thống kê hoặc machine learning có thể học mối quan hệ giữa feature và outcome từ dữ liệu lịch sử. Ví dụ logistic regression, tree-based model hoặc anomaly detection. Lựa chọn cần dựa trên:

- Có nhãn outcome đủ tin cậy và đại diện không?
- Dữ liệu có bao gồm cả trường hợp hợp lệ bị từ chối nhầm không?
- Mô hình có giải thích được và vận hành được không?
- Có thể giám sát drift, calibration, bias và adversarial manipulation không?
- Có quy trình versioning, rollback và kiểm tra trước khi triển khai không?

Không dùng mô hình phức tạp chỉ vì có thể. Rule-based policy có thể dễ kiểm soát hơn cho các điều kiện bắt buộc như token revoked, chữ ký sai hoặc tài khoản disabled.

### 6.4. Kết hợp hard rules và risk model

Một kiến trúc thường tách:

1. **Protocol/security validation:** kiểm tra chữ ký, issuer, audience, expiry, CSRF, PKCE, nonce, trạng thái token. Sai thì từ chối ngay.
2. **Hard policy:** tài khoản disabled, credential revoked, known compromise, giới hạn pháp lý hoặc quyền bị thu hồi.
3. **Risk scoring:** tổng hợp tín hiệu mềm để đánh giá mức bất thường.
4. **Decision policy:** chọn allow, step-up, hold/review hoặc block.

Risk score không được phép ghi đè lỗi xác minh mật mã hoặc khôi phục quyền đã bị thu hồi.

## 7. Chuẩn hóa và hiệu chỉnh điểm

### 7.1. Chuẩn hóa feature

Feature cần định nghĩa rõ:

- Giá trị hợp lệ, miền giá trị và cách xử lý ngoại lệ.
- Cửa sổ thời gian (ví dụ số lần thất bại trong 10 phút).
- Cách nhóm theo account, device, IP, ASN hoặc tenant.
- Cách xử lý bot traffic, NAT và nhiều người dùng chung mạng.
- Tín hiệu có phụ thuộc client type, country hoặc thiết bị không.

Không để cùng một feature mang ý nghĩa khác nhau giữa web và mobile mà không có metadata. Ví dụ “new device” cần có định nghĩa về device registration và thời gian lưu baseline.

### 7.2. Calibration

Nếu mô hình tuyên bố đầu ra là xác suất, cần kiểm tra calibration: trong nhóm dự đoán 10%, tỷ lệ outcome thực tế có gần 10% không trong population/time horizon đã định? Calibration có thể khác giữa nhóm người dùng, khu vực, loại client và thời điểm.

Nếu chỉ dùng ordinal score, hãy gọi đúng là score/risk band, không trình bày như xác suất. Có thể dùng historical validation, holdout set, reliability curve và phân tích theo cohort để kiểm tra độ ổn định.

### 7.3. Chọn ngưỡng theo chi phí

Ngưỡng không chỉ dựa vào accuracy tổng thể. Cần xét:

- False accept: attacker được phép tiếp tục.
- False reject: người dùng hợp lệ bị chặn.
- Step-up cost: thêm thao tác, mất thời gian hoặc cần thiết bị khác.
- Review cost: nhân lực và thời gian xử lý.
- Delay/hold cost: tác động tới nghiệp vụ.
- Missed detection: sự cố không bị phát hiện.

Tài khoản quản trị, giao dịch giá trị cao và thao tác thay đổi recovery có thể dùng ngưỡng khác với xem dữ liệu thông thường. Ngưỡng phải được đo bằng dữ liệu và đánh giá nghiệp vụ; không có con số phổ quát.

## 8. Từ risk score tới quyết định

Risk score chỉ có ích khi gắn với một policy rõ ràng. Một cách phân tầng minh họa:

| Risk band | Quyết định | Ví dụ kiểm soát |
| --- | --- | --- |
| Low | Allow | Tiếp tục phiên theo quyền hiện tại |
| Medium | Step-up | Yêu cầu passkey, security key hoặc MFA phù hợp |
| High | Limit / hold | Tạm dừng thao tác nhạy cảm, xác minh bổ sung hoặc human review |
| Critical/confirmed compromise | Block / revoke | Từ chối request, thu hồi phiên/token, khóa credential bị lộ và xử lý sự cố |

### 8.1. Step-up authentication

Step-up yêu cầu bằng chứng xác thực mạnh hơn hoặc mới hơn khi rủi ro tăng. Lựa chọn phương thức dựa trên:

- Mức bảo đảm cần cho hành động.
- Phương thức đã đăng ký và khả năng chống phishing.
- Nguy cơ kênh recovery/MFA bị chiếm cùng lúc.
- Thiết bị hiện tại có thể sử dụng authenticator không.
- Yêu cầu accessibility và phương thức thay thế.

Passkey/WebAuthn hoặc security key thường phù hợp khi cần chống phishing. OTP có thể hữu ích trong một số trường hợp nhưng có thể bị phishing/real-time relay; SMS có rủi ro SIM swap và phụ thuộc nhà mạng. Không step-up bằng đúng kênh đang bị nghi chiếm.

### 8.2. Hold và human review

Với rủi ro cao nhưng bằng chứng chưa đủ để block vĩnh viễn, có thể tạm dừng thao tác nhạy cảm và chuyển review. Review cần:

- Lý do và tín hiệu có thể giải thích.
- Người review có quyền phù hợp, có audit.
- Quy trình xử lý trong thời hạn xác định.
- Phương thức người dùng chứng minh quyền kiểm soát tài khoản.
- Cơ chế appeal và sửa sai khi hệ thống đánh giá nhầm.

### 8.3. Block và revoke

Chỉ dùng hard block khi có bằng chứng mạnh hoặc policy bắt buộc. Khi xác nhận compromise, chặn request hiện tại chưa đủ: cần thu hồi session, refresh token, token binding/credential bị lộ, kiểm tra thay đổi tài khoản và theo dõi tái đăng nhập.

## 9. Tác động của risk score tới session và token

Risk score có thể thay đổi trong vòng đời phiên:

- Khi login, score hỗ trợ quyết định có cho tạo session hay yêu cầu step-up.
- Khi session đang hoạt động, tín hiệu mới có thể làm tăng rủi ro và yêu cầu xác thực lại.
- Khi refresh token được sử dụng, phát hiện reuse hoặc client/device mismatch có thể kích hoạt revoke.
- Khi access token gọi API nhạy cảm, risk policy có thể yêu cầu step-up hoặc transaction confirmation.
- Khi logout, reset password hoặc account disable, trạng thái revoke phải có hiệu lực độc lập với risk score.

Không nhúng một risk score dài hạn vào JWT rồi xem nó là quyết định bất biến. Nếu score cần cập nhật, lưu trạng thái phía server hoặc dùng policy decision có version/time rõ. Resource server vẫn phải kiểm tra token và authorization.

### Continuous authentication

Continuous/risk-adaptive authentication đánh giá tín hiệu trong suốt phiên, thay vì chỉ lúc login. Nó có thể phát hiện session hijacking hoặc hành vi bất thường sau đăng nhập. Tuy nhiên, thu thập liên tục có thể ảnh hưởng quyền riêng tư, hiệu năng và trải nghiệm; chỉ theo dõi tín hiệu cần thiết, đặt retention và không yêu cầu GPS/behavioral biometrics liên tục nếu không có căn cứ.

## 10. Ranh giới tin cậy và kiến trúc risk engine

~~~mermaid
flowchart TD
    A[Login / API / sensitive action] --> B[Signal collectors]
    B --> C[Credential and auth signals]
    B --> D[Device, network and location signals]
    B --> E[Session, token and behavior signals]
    B --> F[Resource/business context]
    C --> G[Feature validation and freshness]
    D --> G
    E --> G
    F --> G
    G --> H[Risk scorer]
    H --> I[Policy decision engine]
    I --> J[Allow]
    I --> K[Step-up]
    I --> L[Hold / review]
    I --> M[Block / revoke / incident]
    I --> N[Audit and feedback]
~~~

### Các thành phần

- **Signal collectors:** thu thập dữ liệu từ authenticator, session store, gateway, device management và nguồn threat intelligence.
- **Feature validation:** xác minh nguồn, freshness, schema, confidence và xử lý dữ liệu thiếu.
- **Risk scorer:** tính score theo rules hoặc model đã version.
- **Policy engine:** áp dụng hard rules, ngưỡng theo hành động và yêu cầu compliance.
- **Enforcement points:** login service, token endpoint, API gateway, application backend và transaction service.
- **Audit/feedback:** ghi quyết định, reason code, model/policy version và kết quả sau đó.

### Trust boundaries

- Không tin location/device metadata do client tự khai nếu chưa có cơ chế xác minh.
- Không tin forwarded IP header trừ khi request đến từ proxy tin cậy và chain được cấu hình.
- Không cho vendor/model trực tiếp tạo quyền; policy engine và backend có thẩm quyền cuối cùng.
- Không để client sửa score, risk band hoặc kết quả step-up.
- Không để lỗi risk service tự động biến thành allow cho tài nguyên nhạy cảm.
- Tách quyền truy cập dữ liệu sinh trắc, IP, hành vi và token khỏi nhóm không cần xem.

## 11. Giải thích quyết định và chống né tránh

Người dùng cần biết hành động tiếp theo, nhưng không nhất thiết phải thấy mọi chi tiết của mô hình. Nếu hiển thị chính xác quy tắc “chỉ chặn ASN X” hoặc “ngưỡng velocity Y”, attacker có thể điều chỉnh hành vi để né tránh.

### Reason codes

Có thể lưu reason code nội bộ như:

- NEW_DEVICE_CONTEXT
- CREDENTIAL_FAILURE_BURST
- UNUSUAL_NETWORK_CONTEXT
- TOKEN_REUSE_DETECTED
- SESSION_AGE_EXCEEDED
- HIGH_VALUE_ACTION_REQUIRES_STEP_UP

Reason code cần có định nghĩa ổn định, phiên bản và nguồn feature. Giao diện người dùng có thể hiển thị thông điệp an toàn như “Chúng tôi cần xác minh thêm trước khi tiếp tục” thay vì tiết lộ tín hiệu phát hiện chi tiết.

### Explainability cho vận hành

Nhân viên bảo mật cần biết:

- Score/risk band và outcome đang được đánh giá.
- Các feature chính đã tác động và độ mới của chúng.
- Model/policy version.
- Quyết định cuối cùng và rule override nào đã chạy.
- Hành động đã thực thi (step-up, hold, revoke).
- Kết quả sau đó để đánh giá false positive/false negative.

Không ghi token, mật khẩu, OTP, private key hoặc dữ liệu sinh trắc thô vào log. Dùng ID/reference và dữ liệu đã giảm định danh.

## 12. Fairness, privacy và quản trị mô hình

Risk scoring có thể tạo tác động không đồng đều nếu feature hoặc dữ liệu huấn luyện phản ánh chênh lệch giữa vùng địa lý, thiết bị, khả năng tiếp cận hoặc nhóm người dùng.

### 12.1. Fairness và false positive

- Đánh giá tỷ lệ false reject/step-up theo cohort phù hợp và được phép.
- Không dùng thuộc tính nhạy cảm hoặc proxy của thuộc tính nhạy cảm nếu không có cơ sở pháp lý/chính sách rõ.
- Kiểm tra người dùng ở vùng có geolocation kém, mạng chia sẻ hoặc thiết bị cũ.
- Cung cấp phương thức xác thực thay thế và appeal.
- Đánh giá liệu một tín hiệu có tạo vòng lặp bất lợi: bị chặn → phải dùng recovery yếu → tiếp tục bị chấm rủi ro cao.

Không chỉ tối ưu detection rate. Một mô hình chặn rất nhiều người dùng hợp lệ có thể gây hại lớn và khiến người dùng tìm cách né chính sách.

### 12.2. Data minimization

- Thu thập feature cần thiết cho outcome đã định nghĩa.
- Ưu tiên category/metadata giảm định danh thay cho tọa độ, nội dung hoặc dữ liệu thô.
- Không lưu lịch sử vị trí/hành vi vô thời hạn.
- Giới hạn truy cập, audit truy vấn và đặt retention theo mục đích.
- Tách dữ liệu vận hành, fraud investigation và analytics.
- Thông báo mục đích sử dụng theo pháp luật và chính sách áp dụng.

### 12.3. Model governance

Với mô hình thống kê/ML:

- Version dataset, feature definitions, model, threshold và policy.
- Kiểm tra bias, calibration, precision/recall và drift trước khi rollout.
- Dùng shadow mode hoặc canary để so sánh trước khi enforcement.
- Có rollback và fallback policy được phê duyệt.
- Giám sát thay đổi nguồn dữ liệu/vendor và feature distribution.
- Ghi nhận override/review để cải thiện nhưng không coi mọi quyết định của reviewer là ground truth.

## 13. Adversarial adaptation và feedback loop

Attacker có thể quan sát phản ứng của hệ thống, phân tán request hoặc thay đổi proxy/device để giảm score. Vì vậy:

- Không công bố toàn bộ trọng số, threshold và danh sách tín hiệu nhạy cảm.
- Kết hợp tín hiệu độc lập, không dựa vào một IP/device fingerprint.
- Rate limit theo nhiều chiều (account, device, IP/ASN, token, endpoint) và có giới hạn toàn cục.
- Phát hiện hành vi phân tán qua nhiều tài khoản và nhiều nguồn.
- Giữ hard rules cho sự kiện xác minh được như revoked credential, signature invalid hoặc token reuse đã xác nhận.
- Giám sát feature drift và dấu hiệu model evasion.
- Thử nghiệm adversarial trong môi trường kiểm soát; không thay đổi ngưỡng chỉ vì một đợt traffic bất thường chưa được xác minh.

### Feedback loop nguy hiểm

Nếu mô hình chỉ được huấn luyện trên các request đã được cho phép, nó thiếu dữ liệu về những request bị chặn và có thể củng cố thiên lệch hiện tại. Nếu mọi request bị chặn đều được gán nhãn attacker, mô hình học nhầm false positive thành gian lận. Cần outcome label độc lập như incident đã xác nhận, khiếu nại được giải quyết, điều tra và kết quả giao dịch; ghi nhận mức độ chắc chắn của label.

## 14. Tình huống thực tế: đăng nhập vào tài khoản quản trị

Một quản trị viên thường đăng nhập từ laptop công ty bằng passkey. Hôm nay một request dùng password đúng từ thiết bị mới, qua ASN hosting, sau đó thử tạo passkey mới và xuất dữ liệu khách hàng.

### Phân tích

1. Password đúng chỉ chứng minh thông tin đăng nhập phù hợp; không chứng minh người đang gửi là quản trị viên hợp lệ.
2. Thiết bị mới và ASN hosting là tín hiệu cần xem xét, nhưng mỗi tín hiệu riêng có thể có giải thích hợp lệ.
3. Hành động thêm passkey là thay đổi credential có tác động lâu dài; cần step-up mạnh và có thể yêu cầu xác nhận bằng authenticator hiện có.
4. Xuất dữ liệu khách hàng là hành động nhạy cảm; policy có thể yêu cầu xác thực lại, quyền riêng biệt và approval.
5. Nếu có credential stuffing burst, token reuse hoặc bằng chứng endpoint bị chiếm, chặn và thu hồi phiên/token liên quan.

### Quyết định phù hợp

- Không cho thêm passkey chỉ dựa trên password.
- Yêu cầu passkey/security key đã đăng ký hoặc quy trình recovery có bảo đảm phù hợp.
- Tạm dừng xuất dữ liệu tới khi xác minh hoàn tất.
- Ghi reason code và audit; thông báo người dùng qua kênh đã xác minh.
- Nếu compromise được xác nhận, revoke phiên/token, kiểm tra thay đổi credential và điều tra dữ liệu đã truy cập.

Điểm số hỗ trợ chọn hành động; quyền quản trị vẫn được kiểm tra ở authorization layer. Không vì risk score thấp mà bỏ qua yêu cầu phê duyệt cho export.

## 15. Pseudocode: risk scoring và policy decision

Đoạn mã sau minh họa cách tách kiểm tra bảo mật bắt buộc, risk scoring và quyết định policy. Điểm số/threshold không phải giá trị dùng trực tiếp cho production.

~~~ts
type RiskDecision =
  | { action: "ALLOW"; score: number; reasons: string[] }
  | { action: "STEP_UP"; score: number; method: string; reasons: string[] }
  | { action: "HOLD"; score: number; reasons: string[] }
  | { action: "BLOCK"; score: number; reasons: string[] };

async function evaluateAuthentication(event): Promise<RiskDecision> {
  // Protocol validation is mandatory and independent of risk score.
  const protocol = await validateCredentialAndProtocol(event);
  if (!protocol.valid) {
    return { action: "BLOCK", score: 100, reasons: ["INVALID_CREDENTIAL_OR_PROTOCOL"] };
  }

  const signals = await collectValidatedSignals(event);
  const features = normalizeFeatures(signals, {
    includeFreshness: true,
    preserveUnknown: true,
    discardUntrustedClientClaims: true
  });

  const modelResult = await riskModel.score(features);
  const policy = policyForAction(event.requestedAction);

  if (await hardCompromiseRuleMatches(event, signals)) {
    return { action: "BLOCK", score: modelResult.score, reasons: ["CONFIRMED_COMPROMISE"] };
  }
  if (modelResult.score >= policy.holdThreshold) {
    return { action: "HOLD", score: modelResult.score, reasons: modelResult.reasons };
  }
  if (modelResult.score >= policy.stepUpThreshold) {
    return {
      action: "STEP_UP",
      score: modelResult.score,
      method: policy.phishingResistantMethod,
      reasons: modelResult.reasons
    };
  }
  return { action: "ALLOW", score: modelResult.score, reasons: modelResult.reasons };
}
~~~

Đây là pseudocode, không phải API cụ thể. Trong hệ thống thực:

- Không để protocol validation thất bại nhưng risk model trả score thấp rồi cho phép.
- Hard rules phải được định nghĩa riêng và có thứ tự ưu tiên rõ.
- Policy threshold cần theo hành động/tài nguyên và được hiệu chỉnh bằng dữ liệu.
- Lưu model/policy version, feature provenance, timestamp và reason code.
- Không trả score nội bộ đầy đủ cho client nếu có thể giúp attacker né tránh.
- Xử lý lỗi risk service theo chính sách fail-safe; không mặc định allow cho hành động nhạy cảm.

## 16. Tiêu chí chấp nhận và kiểm thử

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Credential hợp lệ, thiết bị quen thuộc, không có tín hiệu bất thường | Cho phép theo authorization và policy hiện hành |
| Password đúng nhưng có credential stuffing burst và device mới | Risk tăng; step-up/hold theo policy, không tự cấp quyền |
| Token đã revoke hoặc chữ ký không hợp lệ | Từ chối bất kể risk score |
| Refresh token reuse được xác nhận | Thu hồi token family/session liên quan và kích hoạt response |
| IP geolocation thiếu hoặc confidence thấp | Không tự cộng risk cao chỉ vì thiếu dữ liệu |
| Người dùng qua VPN doanh nghiệp | Đánh giá network context theo nguồn; tránh false positive chỉ từ IP |
| GPS/device location bị spoof | Không dùng làm bằng chứng duy nhất; kiểm tra provenance và tín hiệu khác |
| Passkey hợp lệ nhưng hành động là thêm authenticator mới | Áp dụng policy step-up/confirmation theo mức nhạy cảm |
| Risk score thấp nhưng user không có quyền trên resource | Authorization từ chối |
| Risk score cao nhưng không có bằng chứng compromise rõ | Step-up/hold/review phù hợp; có đường appeal |
| Risk service timeout | Áp dụng fallback được phê duyệt; hành động nhạy cảm không tự động allow |
| Feature cũ hoặc từ nguồn không tin cậy | Đánh dấu stale/invalid và xử lý theo policy |
| Model version thay đổi | Canary/shadow và kiểm tra metric trước enforcement toàn bộ |
| Tỷ lệ false reject tăng ở một cohort | Cảnh báo, điều tra bias/quality và có biện pháp giảm tác động |
| Model output thay đổi đột ngột | Drift alert, rollback hoặc chuyển sang policy fallback |
| Attacker phân tán request qua nhiều IP | Rate limit/aggregation nhiều chiều; không phụ thuộc một IP |
| Logout/credential revoke sau confirmed compromise | Phiên/token/credential bị thu hồi theo SLA và audit được ghi |

### Chỉ số vận hành

Theo dõi:

- Precision, recall và false positive/false negative theo outcome đã định nghĩa.
- Tỷ lệ allow, step-up, hold, block và completion của step-up.
- Tỷ lệ khiếu nại/appeal và kết quả review.
- Calibration và drift theo thời gian/cohort.
- Độ trễ risk engine, tỷ lệ feature missing/stale và lỗi vendor.
- Số sự cố được phát hiện, thời gian từ detection tới revoke và thiệt hại còn lại.
- Tỷ lệ quyết định bị override và nguyên nhân.

Không dùng accuracy tổng thể làm chỉ số duy nhất, đặc biệt khi outcome gian lận hiếm. Cần xem precision/recall, cost matrix và tác động người dùng.

## 17. Bài tập tự kiểm tra

Một nền tảng doanh nghiệp có web app, mobile app và API. Tài khoản nhân viên dùng passkey; tài khoản quản trị có quyền xuất dữ liệu và thêm authenticator. Risk engine hiện dùng IP quốc gia, thiết bị mới, số lần password thất bại và thời gian đăng nhập.

Hãy:

1. Xác định outcome mà risk score cần dự đoán cho login và cho thao tác thêm authenticator.
2. Bổ sung feature về session/token, credential, device posture và tài nguyên; giải thích nguồn và giới hạn từng feature.
3. Phân biệt signal absent, unknown, stale và suspicious; đề xuất cách xử lý.
4. Thiết kế rule-based score ban đầu và nêu hard rules không được score override.
5. Xác định các risk band và hành động allow/step-up/hold/block cho từng loại hành động.
6. Giải thích cách hiệu chỉnh threshold và đánh giá false accept/false reject.
7. Mô tả cách kiểm tra fairness, privacy, drift và adversarial adaptation.
8. Viết test case cho token revoke, VPN, spoofed location, refresh reuse, risk service outage và false positive.

**Gợi ý đánh giá:** lời giải tốt phải định nghĩa outcome, đơn vị đánh giá và chất lượng feature; tách xác thực khỏi risk scoring và authorization; chọn threshold theo tác động; có step-up/review/appeal; và nêu rõ cách giám sát mô hình sau triển khai.

---

**Ghi nhớ:** risk score tổng hợp tín hiệu để ước lượng mức rủi ro của một lần đăng nhập, phiên, token hoặc hành động. Hãy định nghĩa outcome rõ, đánh giá nguồn và độ mới của feature, kết hợp hard rules với scoring, hiệu chỉnh ngưỡng theo chi phí sai lầm và chuyển score thành policy có thể audit. **Điểm thấp không thay thế xác minh credential hay authorization; điểm cao không tự chứng minh người dùng là attacker.** Bảo vệ quyền riêng tư, theo dõi drift/fairness và cung cấp step-up/review/appeal để hệ thống vừa an toàn vừa công bằng.
