# Phishing response

## 1. Phishing response là gì?

**Phishing response (ứng phó phishing)** là quy trình phát hiện, đánh giá, khoanh vùng, loại bỏ và khôi phục sau khi người dùng hoặc tổ chức gặp một chiến dịch giả mạo nhằm đánh cắp credential, chiếm session, lừa chấp thuận MFA/OAuth hoặc cài mã độc. Mục tiêu là ngăn attacker tiếp tục sử dụng quyền đã lấy được, xác định phạm vi ảnh hưởng, khôi phục quyền kiểm soát tài khoản và giảm khả năng tái diễn.

Một sự kiện phishing không chỉ xảy ra khi người dùng nhập password vào trang giả. Attacker có thể đánh cắp session cookie, dụ người dùng chấp thuận push MFA, yêu cầu cấp OAuth consent cho một ứng dụng độc hại, lừa cài profile/certificate hoặc gửi tệp đính kèm có mã độc. Mỗi trường hợp cần cách xử lý khác nhau.

Ví dụ: một nhân viên nhận email giả mạo bộ phận IT và mở trang đăng nhập giống cổng công ty. Họ nhập password và mã TOTP. Đội ứng phó phải xem credential nào đã lộ, chặn các phiên và token có thể đã được cấp, kiểm tra factor hoặc OAuth grant mới, tìm email tương tự gửi cho đồng nghiệp và xác minh thiết bị có bị xâm nhập hay không.

Trong module SECURITY_AUTHENTICATION_FUNDAMENTALS, phishing response kết nối credential, MFA, passkey, federation, token, session và account recovery. Phản ứng hiệu quả phải xử lý toàn bộ đường truy cập bị ảnh hưởng thay vì chỉ đổi password rồi coi sự cố đã kết thúc.

## 2. Phân biệt các tình huống phishing

Trước khi chọn biện pháp containment, cần xác định người dùng đã làm gì và attacker có thể đã thu được gì:

| Tình huống | Tài sản có thể bị lộ | Hướng xử lý ban đầu |
| --- | --- | --- |
| Chỉ nhận hoặc mở email | Thông tin về mục tiêu; có thể có tracking pixel hoặc tải nội dung từ xa. | Báo cáo email, kiểm tra message và chiến dịch; không mặc định tài khoản đã bị chiếm. |
| Mở liên kết nhưng không nhập dữ liệu | Metadata trình duyệt, IP, fingerprint; có thể kích hoạt exploit nếu thiết bị chưa vá. | Ghi nhận URL/thời điểm, kiểm tra redirect và endpoint telemetry; đánh giá thiết bị. |
| Nhập username/password | Credential có thể bị attacker thu thập và thử ngay. | Đổi password từ thiết bị tin cậy, thu hồi session/token, kiểm tra đăng nhập và factor. |
| Nhập OTP hoặc chấp thuận push | Attacker có thể relay phiên đăng nhập theo thời gian thực. | Thu hồi phiên/token vừa tạo, xác minh factor, kiểm tra đăng nhập và yêu cầu step-up an toàn. |
| Nhập recovery code | Một hoặc nhiều bí mật dự phòng có thể đã bị lộ. | Tiêu thụ/thu hồi code còn lại, khôi phục factor và session theo policy. |
| Chấp thuận OAuth consent | Ứng dụng bên thứ ba có thể nhận quyền truy cập API/dữ liệu. | Thu hồi grant, refresh token và quyền ứng dụng; kiểm tra hoạt động API sau consent. |
| Tải hoặc chạy tệp | Thiết bị có thể bị nhiễm mã độc hoặc bị điều khiển. | Cô lập endpoint theo quy trình EDR, bảo toàn bằng chứng và điều tra persistence. |
| Cài certificate/profile hoặc cấu hình | Thiết bị có thể tin CA/proxy độc hại hoặc bị thay đổi cấu hình xác thực. | Gỡ cấu hình sau khi ghi nhận, đánh giá trust store, thiết bị và credential liên quan. |
| Session cookie/token bị đánh cắp | Attacker có thể truy cập mà không cần password. | Revoke session/token, kiểm tra thiết bị và nguồn đánh cắp; đổi password một mình không đủ. |

Không kết luận mức độ sự cố chỉ dựa trên câu trả lời “tôi chỉ bấm link”. Cần đối chiếu với email gateway, browser/EDR, IdP, proxy, DNS, OAuth audit và log ứng dụng trong khoảng thời gian liên quan.

## 3. Nguyên tắc ứng phó

Một quy trình ứng phó tốt tuân theo các nguyên tắc:

1. **Hành động nhanh theo mức rủi ro:** chặn quyền đang bị lạm dụng trước khi hoàn tất điều tra dài.
2. **Không làm mất bằng chứng:** giữ email gốc, header, URL, timestamp, log IdP và endpoint telemetry theo quy trình.
3. **Dùng kênh liên lạc tin cậy:** xác minh người báo cáo qua directory hoặc số liên hệ đã biết, không dựa vào thông tin trong email đáng ngờ.
4. **Contain toàn bộ đường truy cập:** credential, session, refresh token, OAuth grant, authenticator và thiết bị có thể cùng bị ảnh hưởng.
5. **Giảm thiểu tác động phụ:** thu hồi đúng tài khoản, tenant, ứng dụng và thiết bị; ghi nhận ngoại lệ khi phải ngắt dịch vụ.
6. **Khôi phục từ môi trường tin cậy:** đổi credential trên thiết bị đã kiểm tra, với quy trình recovery có bảo đảm phù hợp.
7. **Kiểm tra persistence:** tìm factor mới, mailbox rule, OAuth app, forwarding, API key hoặc session lạ được attacker cài lại.
8. **Ghi nhận quyết định:** lưu ai đã làm gì, lúc nào, theo policy nào và kết quả ra sao.

Không yêu cầu người dùng gửi password, OTP, recovery code hoặc token cho đội hỗ trợ để “kiểm tra”. Nhân viên IT không cần biết các bí mật đó để xử lý sự cố.

## 4. Ai tham gia ứng phó?

Tổ chức cần biết ai có quyền ra quyết định và ai chịu trách nhiệm thực thi:

| Vai trò | Trách nhiệm |
| --- | --- |
| Người dùng/người báo cáo | Báo cáo qua kênh chính thức, cung cấp thời điểm và hành động đã thực hiện, không tiếp tục tương tác với trang giả. |
| Service desk | Tiếp nhận, xác minh người báo cáo, tạo incident và chuyển đúng đội; không tự bỏ qua quy trình identity proofing. |
| SOC/security operations | Phân tích tín hiệu, xác định phạm vi, điều phối containment và theo dõi hoạt động attacker. |
| IAM/identity team | Thu hồi session, token, grant, credential và xử lý account recovery. |
| Endpoint/IT operations | Kiểm tra hoặc cô lập thiết bị, xử lý mã độc và khôi phục cấu hình. |
| Email/collaboration admin | Tìm, quarantine hoặc xóa các bản sao phishing; kiểm tra mailbox rule và OAuth app. |
| Incident commander | Phân loại mức độ, phân công owner, quyết định escalation và cập nhật tình hình. |
| Legal/privacy/compliance | Đánh giá nghĩa vụ thông báo, dữ liệu cá nhân và yêu cầu lưu giữ bằng chứng khi phù hợp. |

Với tài khoản đặc quyền, tài khoản dịch vụ hoặc hệ thống quan trọng, cần escalation tới owner có thẩm quyền. Không để một nhân viên hỗ trợ tự quyết định xóa factor cuối cùng hoặc vô hiệu hóa tài khoản production mà không theo quy trình khẩn cấp đã được phê duyệt.

## 5. Tiếp nhận báo cáo và triage

Khi nhận được báo cáo phishing, hãy tạo incident record và thu thập thông tin tối thiểu:

- Người báo cáo, tài khoản, tenant và phương thức liên hệ đã xác minh.
- Thời điểm nhận email, mở liên kết, nhập credential, chấp thuận MFA hoặc chạy tệp.
- URL, domain, địa chỉ gửi, subject, message ID và email gốc nếu có.
- Loại thông tin đã nhập: password, OTP, recovery code, thông tin cá nhân hay không có gì.
- Có chấp thuận push, OAuth consent, cài extension/profile/certificate hoặc tải/chạy tệp không.
- Thiết bị, trình duyệt và mạng được sử dụng.
- Dấu hiệu bất thường sau đó như MFA prompt không mong muốn, email gửi đi lạ hoặc thông báo đăng nhập mới.

Nếu có thể, yêu cầu người dùng báo cáo email bằng chức năng Report Phishing hoặc chuyển email gốc dưới dạng attachment theo quy trình nội bộ. Tránh yêu cầu forward thông thường nếu việc đó làm mất header hoặc metadata cần thiết.

### 5.1. Phân loại mức độ

Một ma trận tham khảo:

| Mức | Dấu hiệu | Phản ứng |
| --- | --- | --- |
| **Informational** | Email đáng ngờ được báo cáo, chưa có tương tác. | Phân tích mẫu, tìm người nhận khác và quarantine chiến dịch. |
| **Suspected exposure** | Người dùng mở link hoặc nhập dữ liệu nhưng chưa thấy đăng nhập bất thường. | Triage nhanh, kiểm tra log, cân nhắc reset/revoke theo loại dữ liệu đã nhập. |
| **Confirmed account compromise** | Có đăng nhập lạ, session/token bất thường, push bị chấp thuận ngoài ý muốn hoặc factor bị thêm. | Containment ngay, revoke phiên/grant, bảo vệ account và điều tra persistence. |
| **Endpoint compromise** | Tệp chạy, exploit hoặc dấu hiệu malware/remote control. | Cô lập endpoint, incident response thiết bị và xoay credential từ thiết bị sạch. |
| **Widespread campaign** | Nhiều người nhận, nhiều tài khoản bị ảnh hưởng hoặc có quyền đặc quyền/dữ liệu nhạy cảm. | Incident commander điều phối, containment diện rộng có kiểm soát và đánh giá nghĩa vụ thông báo. |

Ma trận này giúp ưu tiên, không thay thế quy trình phân loại sự cố chính thức của tổ chức.

## 6. Quy trình ứng phó tổng thể

~~~mermaid
flowchart TD
    A["Nhận báo cáo hoặc cảnh báo phishing"] --> B["Triage: ai, khi nào, đã làm gì?"]
    B --> C["Bảo toàn email, URL, log và endpoint evidence"]
    C --> D{"Có credential/session/token hoặc thiết bị bị lộ?"}
    D -->|Không rõ / chỉ mở link| E["Điều tra telemetry và phạm vi chiến dịch"]
    D -->|Có khả năng| F["Contain: revoke session, token, grant, factor theo rủi ro"]
    E --> G["Tìm người nhận và tài khoản liên quan"]
    F --> G
    G --> H["Loại bỏ email, app, rule, malware hoặc persistence"]
    H --> I["Khôi phục từ thiết bị/kênh tin cậy"]
    I --> J["Giám sát tăng cường và xác nhận an toàn"]
    J --> K["Đóng incident, lưu evidence và bài học"]
~~~

Các giai đoạn có thể diễn ra song song. Nếu có bằng chứng attacker đang dùng tài khoản đặc quyền, containment không nên chờ hoàn tất phân tích toàn bộ email.

## 7. Containment khi password bị lộ

Nếu người dùng đã nhập password vào trang giả hoặc nghi password bị đánh cắp:

1. Xác minh người báo cáo qua kênh tin cậy.
2. Kiểm tra log IdP và ứng dụng để xác định lần đăng nhập, thiết bị, IP, session và hành động sau thời điểm lộ.
3. Đổi password từ thiết bị sạch và website chính thức; không dùng liên kết trong email đáng ngờ.
4. Thu hồi session đang hoạt động và refresh token theo policy. Nếu access token tự chứa không có cơ chế revoke tức thời, đánh giá TTL, denylist hoặc session version.
5. Kiểm tra MFA enrollment, recovery email/phone, passkey, security key và recovery code; thu hồi phương thức lạ.
6. Kiểm tra các lần đăng nhập thất bại/thành công trên các ứng dụng dùng cùng IdP.
7. Nếu password được tái sử dụng ở dịch vụ khác, hướng dẫn người dùng thay đổi tại các dịch vụ đó bằng kênh chính thức.
8. Theo dõi đăng nhập mới và cảnh báo sau khi khôi phục.

Đổi password mà không revoke session/token có thể để attacker tiếp tục dùng phiên đã tạo trước đó. Ngược lại, revoke session mà không đổi password bị lộ cho phép attacker đăng nhập lại.

Nếu thiết bị có thể bị malware điều khiển, không yêu cầu người dùng đổi password trên chính thiết bị đó trước khi kiểm tra. Credential mới có thể bị đánh cắp ngay lập tức.

## 8. Containment khi OTP hoặc push MFA bị lạm dụng

Khi người dùng nhập OTP vào trang giả hoặc chấp thuận push không do họ khởi tạo, attacker có thể đã hoàn tất một phiên đăng nhập thật thông qua relay.

Hành động:

- Xác định thời điểm và factor đã được sử dụng.
- Revoke session/token được tạo trong khoảng thời gian liên quan.
- Kiểm tra IdP authentication log, source/device, client và ứng dụng đích.
- Xem xét tạm ngưng factor hoặc yêu cầu đăng ký lại nếu secret/thiết bị có nguy cơ bị lộ.
- Kiểm tra push prompt bất thường, number matching, fatigue pattern và các lần chấp thuận liên tiếp.
- Xác minh không có factor mới được attacker đăng ký sau khi vào được tài khoản.
- Hướng dẫn người dùng từ chối prompt không do họ chủ động khởi tạo và báo cáo ngay.

Không phải mọi OTP đều cần rotate secret. Nếu người dùng chỉ nhập một mã TOTP trong một trang giả nhưng secret TOTP chưa bị lộ, secret có thể vẫn an toàn; tuy nhiên phiên relay cần được thu hồi và phải đánh giá xem attacker có truy cập được enrollment secret hay không. Nếu secret TOTP bị lộ, thu hồi factor và enroll secret mới.

## 9. Containment khi session cookie hoặc token bị đánh cắp

Session theft có thể xảy ra qua phishing proxy, malware, XSS, browser extension độc hại hoặc thiết bị bị xâm nhập. Attacker có thể dùng cookie/token mà không cần biết password.

Các bước:

1. Xác định session ID, token family, principal, client và resource server bị ảnh hưởng nếu log cho phép.
2. Revoke session phía server hoặc tăng session version để vô hiệu hóa phiên cũ.
3. Revoke refresh token family và authorization grant liên quan khi có nguy cơ.
4. Với access token opaque, gọi cơ chế revocation/introspection phù hợp.
5. Với JWT access token tự chứa, xác định giới hạn thu hồi thực tế: token có thể còn hiệu lực tới expiry nếu resource server chỉ xác minh chữ ký và claim. Dùng TTL ngắn, denylist, token version hoặc introspection khi kiến trúc hỗ trợ.
6. Kiểm tra request API bất thường, dữ liệu đã đọc/xuất, thay đổi profile, tạo credential và hành động quản trị.
7. Nếu nguồn là endpoint bị xâm nhập, cô lập thiết bị và xử lý nguyên nhân trước khi cấp session mới.

Không giả định nút “Log out” ở browser đã vô hiệu hóa cookie bị đánh cắp. Logout chỉ có tác dụng nếu server-side session hoặc token liên quan được revoke và resource server thực thi trạng thái đó.

## 10. Containment khi bị OAuth consent phishing

OAuth consent phishing lừa người dùng cấp quyền cho một ứng dụng bên thứ ba. Attacker có thể nhận access token hoặc refresh token theo grant được chấp thuận, truy cập email, file, profile hoặc API khác tùy scope.

Phản ứng:

1. Xác định application/client ID, publisher, redirect URI, user, tenant, thời điểm consent và các scope được cấp.
2. Kiểm tra consent grant và token activity trong audit của IdP/resource provider.
3. Thu hồi grant hoặc user consent; chặn ứng dụng theo policy nếu cần.
4. Thu hồi refresh token và các phiên/credential ứng dụng liên quan theo khả năng của nền tảng.
5. Đánh giá access token đã phát hành: token có thể còn hiệu lực tới expiry nếu resource server không hỗ trợ revoke/introspection.
6. Tìm hoạt động đọc, tải, gửi hoặc chia sẻ dữ liệu sau thời điểm consent.
7. Kiểm tra app registration, service principal, delegated permissions và quyền application-level do admin consent.
8. Tìm người dùng khác đã cấp cùng ứng dụng hoặc cùng publisher/client ID.
9. Thông báo owner dữ liệu và đánh giá nghĩa vụ xử lý dữ liệu nếu có truy cập trái phép.

Xóa ứng dụng khỏi danh sách giao diện người dùng chưa chắc đã thu hồi grant ở IdP. Cần xác nhận trạng thái consent/token ở hệ thống quản lý danh tính và resource service.

## 11. Containment khi tải hoặc chạy tệp độc hại

Nếu người dùng tải tệp nhưng chưa chạy, ghi nhận tên tệp, hash, nguồn tải và vị trí lưu; chuyển cho đội endpoint/security kiểm tra theo quy trình. Không mở tệp để “xem thử”.

Nếu tệp đã chạy hoặc có dấu hiệu thực thi:

- Cô lập thiết bị khỏi mạng theo công cụ EDR/incident procedure; tránh tự ý tắt nguồn nếu việc đó làm mất bằng chứng cần thiết.
- Ghi nhận hostname, user, thời điểm, process tree, file hash, network connection và alert liên quan.
- Bảo toàn disk/memory evidence theo hướng dẫn điều tra số.
- Xác định credential, cookie, token, SSH key, certificate hoặc secret có thể đã truy cập từ thiết bị.
- Thu hồi hoặc rotate bí mật có khả năng bị đọc, thực hiện từ một thiết bị sạch.
- Kiểm tra persistence như scheduled task, startup item, browser extension, remote access tool và cấu hình proxy.
- Reimage hoặc khôi phục thiết bị theo quy trình đã được phê duyệt; không chỉ xóa tệp được phát hiện.

Không tự ý xóa tệp, dọn browser profile hoặc chạy công cụ không được phê duyệt trước khi đội ứng phó thu thập bằng chứng.

## 12. Tìm và loại bỏ chiến dịch phishing

Containment một tài khoản là chưa đủ nếu email vẫn nằm trong hộp thư của nhiều người.

Đội email/security nên:

1. Dùng message ID, sender, subject, header, URL, attachment hash và đặc điểm nội dung để tìm bản sao.
2. Quarantine hoặc xóa message theo quy trình; tránh xóa nhầm thư hợp lệ do sender bị giả mạo.
3. Kiểm tra các alias, mailing list, shared mailbox và forwarding route.
4. Chặn domain/URL/hash ở email gateway, DNS, secure web gateway hoặc EDR phù hợp.
5. Kiểm tra domain tương tự, redirect chain và hạ tầng gửi liên quan.
6. Tìm người dùng đã click, nhập credential, consent hoặc chạy attachment.
7. Cảnh báo người dùng bằng kênh nội bộ đã xác minh, kèm dấu hiệu nhận biết và cách báo cáo.

Chặn một IP hoặc domain không nên được thực hiện mù quáng nếu đó là hạ tầng chia sẻ của nhà cung cấp hợp lệ. Dùng IOC có ngữ cảnh, thời hạn và quy trình rà soát false positive.

## 13. Kiểm tra persistence sau khi attacker truy cập

Sau khi chiếm được tài khoản, attacker thường cố giữ quyền ngay cả khi password đã đổi. Hãy kiểm tra:

- Passkey, security key, TOTP factor hoặc thiết bị mới được enrollment.
- Recovery email, số điện thoại và recovery code bị thay đổi.
- OAuth consent, enterprise application, service principal hoặc delegated permission lạ.
- Mailbox forwarding, inbox rule, delegate, shared mailbox permission và app password.
- API key, personal access token, certificate hoặc client secret mới.
- Session, refresh token và thiết bị tin cậy không nhận diện.
- Thay đổi role, group membership, conditional access hoặc security policy.
- Thay đổi thông tin liên hệ, phương thức thông báo và kênh recovery.
- Quy tắc tự động, scheduled task, browser extension hoặc remote access tool trên endpoint.

Kiểm tra theo phạm vi thời gian bắt đầu từ trước thời điểm click/credential exposure. Attacker có thể đã truy cập trước khi người dùng nhận ra email giả.

## 14. Khôi phục tài khoản an toàn

Chỉ khôi phục khi đã xử lý nguyên nhân và xác định được cách attacker có thể truy cập:

1. Xác minh người dùng qua kênh tin cậy; nếu họ mất toàn bộ factor, dùng account recovery/identity proofing đã được phê duyệt.
2. Dùng thiết bị sạch hoặc thiết bị đã được xác nhận an toàn.
3. Đổi password nếu bị lộ, yếu hoặc tái sử dụng; không tái dùng bí mật cũ.
4. Enroll lại passkey/security key/TOTP nếu factor hoặc thiết bị có nguy cơ bị lộ.
5. Cấp bộ recovery code mới và thu hồi bộ cũ nếu có khả năng đã bị truy cập.
6. Xóa factor, OAuth grant, session, API key và credential không nhận diện.
7. Khôi phục recovery email/phone và xác minh các thay đổi bằng kênh độc lập.
8. Áp dụng step-up hoặc thời gian chờ cho thay đổi nhạy cảm nếu policy yêu cầu.
9. Thông báo người dùng về những thay đổi đã thực hiện và cách báo cáo dấu hiệu tái diễn.
10. Bật giám sát tăng cường trong khoảng thời gian theo incident policy.

Không tự động mở khóa chỉ vì password mới đã được đặt. Account status, factor, session, grant và endpoint cần được xác minh độc lập.

## 15. Bảo toàn bằng chứng và điều tra

Evidence cần đủ để dựng lại timeline và xác định phạm vi:

| Nguồn | Bằng chứng cần giữ |
| --- | --- |
| Email gateway | Email gốc, full headers, message ID, sender, recipient, URL và attachment metadata. |
| Browser/proxy/DNS | URL, redirect chain, thời điểm truy cập, domain lookup và request metadata theo policy. |
| Identity provider | Login success/failure, MFA event, device, session, token issuance và factor enrollment. |
| OAuth platform | Consent grant, client ID, scopes, app publisher, token activity và admin consent. |
| Endpoint/EDR | Process tree, file hash, network connection, alert, device timeline và containment action. |
| Application/API | Request, resource access, data export, role change và hành động quản trị. |
| Incident system | Người xử lý, thời gian, quyết định, approval, action result và correlation ID. |

Giữ nguyên timestamp và timezone; ghi nguồn thu thập, người thu thập và cách bảo toàn. Hạn chế quyền truy cập evidence và tuân thủ retention/privacy policy. Không đưa password, OTP, recovery code, session cookie hoặc token plaintext vào incident ticket.

Không chỉ dựa vào screenshot của trang phishing. Email headers, DNS/proxy log và IdP event thường giúp xác định đường đi và thời điểm thực tế chính xác hơn.

## 16. Truyền thông với người dùng và tổ chức

Thông báo cần rõ ràng, không đổ lỗi cho người dùng:

- Nêu điều gì đã xảy ra ở mức đã xác minh.
- Nêu hành động người dùng cần thực hiện ngay và kênh hỗ trợ chính thức.
- Không yêu cầu gửi credential, OTP, recovery code hoặc token.
- Hướng dẫn từ chối MFA prompt không do họ khởi tạo.
- Cho biết cách báo cáo nếu phát hiện login, email gửi đi hoặc thay đổi tài khoản bất thường.
- Với chiến dịch diện rộng, cung cấp dấu hiệu nhận diện và phạm vi ảnh hưởng đã được xác minh.

Không gửi thông báo reset password hoặc recovery qua chính địa chỉ/URL đáng ngờ. Dùng portal nội bộ, số điện thoại hoặc kênh đã công bố từ trước.

## 17. Ví dụ: nhân viên nhập password và TOTP vào trang giả

Một nhân viên nhận email giả mạo thông báo hết hạn phiên. Họ mở liên kết, nhập password và mã TOTP. Vài phút sau, họ nhận được thông báo đăng nhập từ thiết bị lạ.

**Phản ứng:**

1. Service desk xác minh nhân viên qua directory và tạo incident.
2. SOC thu thập email gốc, URL, thời điểm nhập dữ liệu và thông báo đăng nhập.
3. IAM kiểm tra IdP log, xác định session được tạo từ nguồn lạ và revoke session/refresh token liên quan.
4. Nhân viên dùng thiết bị sạch truy cập portal chính thức, đổi password và xác minh factor.
5. Đội IAM kiểm tra enrollment mới, recovery contact và session khác; thu hồi mục không nhận diện.
6. SOC tìm các email có cùng message ID/URL, quarantine bản sao và xác định người nhận đã tương tác.
7. Đội email/security kiểm tra hoạt động mailbox và OAuth grant để phát hiện persistence.
8. Endpoint team kiểm tra browser/EDR nếu có dấu hiệu tải tệp hoặc extension.
9. Nhân viên đăng ký lại factor nếu secret hoặc thiết bị bị lộ, sau đó nhận recovery code mới.
10. Đội ứng phó theo dõi đăng nhập, token và hoạt động API; chỉ đóng incident khi containment và recovery được xác nhận.

**Điểm quan trọng:** TOTP có thể bị relay theo thời gian thực. Đổi password mà không revoke phiên do attacker tạo có thể để họ tiếp tục truy cập.

## 18. Các lỗi ứng phó thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ đổi password | Session/token đã cấp vẫn có thể hoạt động. | Revoke session/refresh token và kiểm tra access token theo kiến trúc. |
| Chỉ xóa email phishing khỏi inbox người báo cáo | Các bản sao khác vẫn còn và tiếp tục lừa người dùng. | Tìm theo IOC trên toàn tenant và quarantine chiến dịch. |
| Coi mọi lần click là đã chiếm tài khoản | Gây gián đoạn và giảm độ tin cậy của quy trình. | Phân loại theo hành động, evidence và risk. |
| Bỏ qua OAuth consent | App bên thứ ba vẫn có thể truy cập API/dữ liệu. | Revoke grant/token và kiểm tra app/service principal. |
| Không kiểm tra factor mới | Attacker giữ đường truy cập sau khi password đổi. | Rà soát enrollment, recovery method và authenticator. |
| Không kiểm tra mailbox rule/forwarding | Attacker tiếp tục đọc hoặc chuyển tiếp email. | Kiểm tra persistence và quyền mailbox. |
| Dùng thiết bị nghi nhiễm để đổi password | Credential mới có thể bị đánh cắp ngay. | Khôi phục từ thiết bị sạch đã xác minh. |
| Không bảo toàn email/log gốc | Mất khả năng dựng timeline và phạm vi. | Thu thập evidence theo quy trình trước khi dọn dẹp. |
| Gửi OTP/recovery code cho IT | Tạo thêm nơi lộ bí mật và mở đường social engineering. | Nhân viên không bao giờ cần biết secret người dùng. |
| Thu hồi diện rộng không đánh giá tác động | Có thể làm gián đoạn hệ thống và workload quan trọng. | Scope theo principal/resource, incident approval và kế hoạch khôi phục. |
| Đóng incident sau khi login lại được | Persistence hoặc dữ liệu đã bị truy cập chưa được điều tra. | Kiểm tra grant, session, factor, mailbox, endpoint và API activity. |
| Không theo dõi sau recovery | Attacker có thể đăng nhập lại hoặc tái enrollment. | Giám sát tăng cường và xác nhận trạng thái an toàn. |

## 19. Checklist phishing response

Khi xử lý một báo cáo phishing, hãy kiểm tra:

1. Đã xác minh người báo cáo qua kênh liên lạc tin cậy chưa?
2. Người dùng đã nhận email, mở link, nhập password/OTP/recovery code, chấp thuận push/OAuth hay chạy tệp?
3. Email gốc, header, URL, message ID, attachment metadata và timestamp đã được bảo toàn chưa?
4. Có đăng nhập lạ, session/token mới, MFA event hoặc factor enrollment không nhận diện không?
5. Session, refresh token, OAuth grant và credential bị ảnh hưởng đã được revoke theo policy chưa?
6. Access token tự chứa còn hiệu lực tới khi nào và resource server có hỗ trợ revoke/introspection không?
7. Recovery email/phone, recovery code, passkey, TOTP và security key có bị thay đổi không?
8. Có mailbox rule, forwarding, delegate, OAuth app, API key hoặc service principal lạ không?
9. Thiết bị có tải/chạy tệp, cài extension/profile/certificate hoặc có EDR alert không?
10. Có tìm và quarantine các bản sao phishing trên toàn tổ chức chưa?
11. Password/factor mới có được tạo từ thiết bị và kênh tin cậy không?
12. Có xác minh lại account status, session, grant và authorization sau recovery không?
13. Bằng chứng có được lưu với quyền truy cập, nguồn và retention phù hợp không?
14. Người dùng và owner hệ thống đã nhận thông báo qua kênh chính thức chưa?
15. Có giám sát tăng cường, người chịu trách nhiệm và tiêu chí đóng incident rõ ràng không?

**Kết luận:** Phishing response phải bắt đầu bằng việc xác định người dùng đã tương tác ở mức nào, sau đó khoanh vùng credential, session, token, OAuth grant, authenticator và thiết bị có thể bị ảnh hưởng. Đổi password chỉ là một phần của containment; cần revoke phiên/quyền đã cấp, tìm persistence, bảo toàn bằng chứng và khôi phục từ thiết bị tin cậy. Chỉ đóng incident khi đã kiểm tra phạm vi, xác nhận các đường truy cập bị lạm dụng đã được xử lý và có giám sát sau khôi phục.
