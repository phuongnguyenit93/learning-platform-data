# Risk-based assurance — Xác định mức bảo đảm dựa trên rủi ro

> **Chương:** Mức độ tin cậy  
> **Chủ đề:** Risk-based assurance  
> **Phạm vi:** Module SECURITY_AUTHENTICATION_FUNDAMENTALS tìm hiểu nguyên lý xác thực từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này tập trung vào cách lựa chọn và duy trì **mức bảo đảm xác thực phù hợp với rủi ro**, đồng thời bảo vệ ranh giới tin cậy và giảm phishing, replay, lạm dụng đăng nhập.

## 1. Risk-based assurance là gì?

**Risk-based assurance** là cách xác định **cần bằng chứng xác thực mạnh và mới đến mức nào** dựa trên tài sản cần bảo vệ, hậu quả nếu xác thực sai, đặc tính người dùng và thao tác, cùng các dấu hiệu rủi ro của phiên hiện tại. Hệ thống thiết lập yêu cầu bảo đảm tối thiểu cho từng loại truy cập, rồi có thể tăng yêu cầu hoặc hạn chế hành động khi ngữ cảnh trở nên nguy hiểm.

Ví dụ: đọc bài học công khai không cần đăng nhập; xem điểm số cá nhân cần phiên đã xác thực; đổi email khôi phục hoặc thêm passkey có thể cần xác thực lại bằng phương thức mạnh; phê duyệt thanh toán lớn có thể cần thêm xác nhận nội dung giao dịch. Các yêu cầu đó xuất phát từ **hậu quả của việc cấp quyền nhầm**, không chỉ từ vị trí địa lý hay điểm rủi ro tự động.

Điều cốt lõi là phân biệt hai khái niệm:

- **Rủi ro (risk):** khả năng và hậu quả của một sự cố, chẳng hạn kẻ tấn công chiếm phiên để sửa thông tin thanh toán.
- **Mức bảo đảm (assurance):** mức tin cậy hợp lý rằng quá trình kiểm chứng, xác thực và/hoặc liên kết danh tính đã được thực hiện đúng theo yêu cầu kỹ thuật và chính sách.

Một lần đăng nhập từ thiết bị quen thuộc có thể **trông ít rủi ro**, nhưng không vì thế mà một mật khẩu yếu trở thành passkey chống phishing. Ngược lại, IP mới chỉ là **tín hiệu rủi ro**, không phải bằng chứng người dùng đang tấn công.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **mức bảo đảm danh tính, mức bảo đảm xác thực và mức bảo đảm liên kết danh tính** với điểm rủi ro của yêu cầu.
2. Xác định yêu cầu tối thiểu theo loại người dùng, tài sản và hành động; tránh hạ thấp các yêu cầu bắt buộc chỉ vì điểm rủi ro thấp.
3. Mô hình hóa luồng kiểm tra rủi ro, xác minh credential, step-up, tạo phiên và phân quyền trên ranh giới tin cậy.
4. Đánh giá tác động của phishing, replay, credential stuffing, token bị đánh cắp, đăng nhập liên kết và khôi phục tài khoản.
5. Viết bảng quyết định, trạng thái phiên, tiêu chí kiểm thử và chỉ số giám sát cho cơ chế xác thực thích ứng.

## 2. Risk-based authentication và assurance liên quan nhưng không đồng nghĩa

**Risk-based authentication (RBA)** thường phân tích các tín hiệu từ ngữ cảnh đăng nhập như thiết bị, hành vi, lịch sử, IP hoặc dấu hiệu tự động hóa để điều chỉnh biện pháp: cho phép, yêu cầu bước xác thực bổ sung, giới hạn thao tác hoặc chặn. **Risk-based assurance** bao quát hơn: nó hỏi liệu bằng chứng xác thực và các kiểm soát xuyên suốt vòng đời tài khoản có **đạt mức cần thiết cho rủi ro của tác vụ** hay chưa.

Có thể hình dung một hàm quyết định khái niệm:

~~~text
Yêu cầu bảo đảm = policy(tài sản, tác vụ, vai trò, hậu quả, yêu cầu bắt buộc)

Rủi ro ngữ cảnh = evaluate(tín hiệu đáng tin, chất lượng tín hiệu, thời điểm)

Độ tin cậy hiện có = evidence(methods, credential, auth_time,
                            session, federation, recovery history)

Quyết định = enforce(yêu cầu bảo đảm, độ tin cậy hiện có,
                      rủi ro ngữ cảnh, quyền truy cập)
~~~

**Yêu cầu bảo đảm** là ngưỡng phải đạt; **độ tin cậy hiện có** là những gì đã được kiểm chứng; **rủi ro ngữ cảnh** có thể khiến chính sách yêu cầu biện pháp bổ sung. Ba thông số này không thể hoán đổi.

Ví dụ, tài khoản quản trị được quy định phải dùng phương thức chống phishing. Một IP quen thuộc không phải lý do để bỏ yêu cầu đó. Một phiên đã qua MFA vẫn có thể bị chặn nếu có bằng chứng phiên bị thu hồi hoặc nếu chủ thể không có quyền trên tài nguyên. Kết quả **xác thực** không thay thế kết quả **phân quyền**.

| Câu hỏi | Kết quả mong đợi | Thí dụ |
| --- | --- | --- |
| Tài sản và tác vụ nhạy cảm đến đâu? | Chính sách bảo đảm tối thiểu | Đổi người thụ hưởng yêu cầu xác thực lại mạnh hơn đọc hồ sơ. |
| Đã kiểm tra danh tính/bằng chứng gì? | Assurance thực sự đạt được | Phương thức, cách đăng ký credential, thời điểm xác thực gần nhất. |
| Yêu cầu hiện tại có dấu hiệu bất thường nào? | Đánh giá rủi ro ngữ cảnh | Nhiều lần thử thất bại, yêu cầu push liên tiếp, phiên vừa đổi thiết bị. |
| Chủ thể có quyền hành động không? | Quyết định phân quyền | Không cho tài khoản A sửa dữ liệu B dù A đã qua MFA. |
| Cần hành động gì tiếp theo? | Cho phép, step-up, trì hoãn, giới hạn, từ chối | Yêu cầu WebAuthn mới cho thao tác thêm authenticator. |

## 3. Hiểu đúng IAL, AAL và FAL

Một số khung hướng dẫn như bộ tài liệu **NIST SP 800-63** tách các chiều bảo đảm khác nhau. Đây là từ vựng hữu ích khi mô tả hệ thống, nhưng để tuyên bố phù hợp một mức cụ thể cần đối chiếu đầy đủ phiên bản tiêu chuẩn và tất cả yêu cầu liên quan.

| Chiều bảo đảm | Câu hỏi chính | Ví dụ phạm vi đánh giá |
| --- | --- | --- |
| **IAL — Identity Assurance Level** | Danh tính của người được đăng ký đã được kiểm chứng như thế nào? | Thu thập, xác minh và kiểm chứng thuộc tính/hồ sơ danh tính ngoài đời nếu nghiệp vụ cần. |
| **AAL — Authentication Assurance Level** | Sự kiện xác thực hiện tại dựa trên authenticator và giao thức mạnh đến mức nào? | Số/loại yếu tố, bảo vệ authenticator, phishing/replay resistance theo yêu cầu, bảo vệ phiên, vòng đời. |
| **FAL — Federation Assurance Level** | Thông tin định danh/xác thực được chuyển từ IdP sang RP với mức bảo vệ nào? | Cơ chế assertion, ràng buộc bên nhận, bảo vệ giao thức, yêu cầu xác minh và quản lý quan hệ tin cậy. |

**Ví dụ 1:** Người dùng tự tạo tài khoản qua email, sau đó đăng nhập bằng passkey. Họ có thể có **bằng chứng xác thực mật mã mạnh** nhưng dịch vụ vẫn **chưa kiểm chứng danh tính pháp lý** của họ. Không suy IAL cao từ AAL cao.

**Ví dụ 2:** IdP thực hiện MFA rồi RP nhận ID token đúng giao thức. RP vẫn cần đánh giá yêu cầu federation, kiểm tra issuer/audience/chữ ký và ánh xạ đúng subject. Không được coi “IdP có MFA” là bằng chứng rằng toàn bộ liên kết danh tính đã an toàn.

**Ví dụ 3:** Bộ quy tắc yêu cầu “quản trị viên phải đạt mức xác thực đủ mạnh để chống phishing”. Không được gán nhãn một phương thức là “AAL cao” chỉ vì UI có hai màn hình; cần kiểm tra chính xác authenticator, cách đăng ký/khôi phục, yêu cầu kỹ thuật và chính sách phiên.

Mức bảo đảm là **kết quả đánh giá trên toàn hệ thống**, không chỉ thuộc tính của một nút “MFA enabled”.

## 4. Xây mô hình rủi ro trước khi đặt chính sách

Muốn dùng bảo đảm theo rủi ro một cách nhất quán, trước hết phải xác định cái gì có thể bị xâm phạm và hậu quả.

### 4.1. Liệt kê tài sản và hành động

Ví dụ nền tảng học tập có thể phân loại:

- Nội dung khóa học công khai: tác động thấp nếu truy cập nhầm.
- Hồ sơ, bài nộp và thông tin liên lạc của người học: tác động đến riêng tư và tính toàn vẹn.
- Thay email khôi phục, đăng ký MFA, liên kết IdP: tác động đến **quyền kiểm soát tài khoản trong tương lai**.
- Duyệt hoàn tiền, thay tài khoản thanh toán, cấp vai trò quản trị: hậu quả tài chính và đặc quyền cao.
- Cấp token cho API hoặc thay khóa xác thực dịch vụ: có thể mở rộng tác động ra nhiều tài khoản.

Đánh giá cả **tính bảo mật (confidentiality)**, **toàn vẹn (integrity)**, **sẵn sàng (availability)** và hậu quả đối với người dùng/tổ chức. Hai thao tác đọc và ghi trên cùng một tài nguyên có thể có mức rủi ro khác nhau.

### 4.2. Xác định tác nhân và kịch bản tấn công

| Kịch bản | Điều kẻ tấn công có thể nắm | Hậu quả nếu chính sách sai |
| --- | --- | --- |
| Credential stuffing | Cặp username/mật khẩu bị rò | Truy cập hàng loạt tài khoản chỉ có mật khẩu. |
| Phishing theo thời gian thực | Mật khẩu và OTP vừa nhập trên trang giả | Vượt qua MFA dạng mã và lấy phiên. |
| Đánh cắp token/cookie | Phiên đã xác thực sẵn | Thực hiện thao tác dù không có authenticator. |
| Account recovery takeover | Quyền truy cập email hoặc kênh hỗ trợ yếu | Đổi credential và khóa chủ tài khoản thật. |
| Insider hoặc confused deputy | Tài khoản có một phần quyền | Vượt tenant, sửa dữ liệu hoặc cấp quyền sai. |
| Phát lại giao dịch | OTP, challenge response hoặc request bị thu thập | Hoàn thành lại bước xác thực/giao dịch nếu không ràng buộc. |
| Khóa người dùng hợp lệ | Có khả năng gửi vô số lần thử MFA | Gây từ chối dịch vụ và buộc người dùng chọn đường khôi phục yếu. |

**Mô hình đe dọa phải tính đến các đường ngoại lệ**, đặc biệt khi người dùng mất thiết bị, đổi số điện thoại, bị khóa hoặc cần hỗ trợ.

### 4.3. Xác lập yêu cầu nền và quyền miễn trừ

Chính sách có hai nhóm điều kiện:

1. **Bắt buộc**: loại authenticator tối thiểu, phishing resistance cho vai trò nhạy cảm, TLS, kiểm tra quyền, yêu cầu nghiệp vụ hoặc pháp lý. Không dùng điểm ngữ cảnh thấp để bỏ các điều kiện này.
2. **Thích ứng**: khi phát hiện bất thường, có thể yêu cầu xác thực lại, thêm bằng chứng, hạn chế hành động, xem xét thủ công hoặc chặn.

Để dễ kiểm toán, chính sách cần ghi rõ **ai phê duyệt, phạm vi áp dụng, phiên bản, ngày có hiệu lực**, cách xử lý ngoại lệ và lý do ra quyết định. Không nên để mỗi endpoint tự đặt một logic bảo đảm riêng không đồng nhất.

## 5. Tín hiệu rủi ro: hữu ích nhưng không phải bằng chứng danh tính

Cơ chế thích ứng có thể xét nhiều tín hiệu; mỗi tín hiệu đều có giới hạn và độ tin cậy nhất định.

| Tín hiệu | Có thể gợi ý điều gì? | Giới hạn và cách dùng thận trọng |
| --- | --- | --- |
| IP, ASN, mạng proxy, vị trí suy từ IP | Kết nối từ hạ tầng mới hoặc đã bị lạm dụng | VPN, NAT, mạng di động, geolocation sai; không dùng để nhận diện chính xác một người. |
| Thiết bị/trình duyệt đã biết | Mức độ quen thuộc của môi trường truy cập | Cookie có thể bị đánh cắp; fingerprint có thể thay đổi, bị giả mạo và ảnh hưởng quyền riêng tư. |
| Lịch sử đăng nhập và thay đổi phiên | Nhảy đột ngột giữa ngữ cảnh, nhiều phiên lạ | Lịch sử có thể thiếu; khi tài khoản vừa bị chiếm, “hành vi quen thuộc” cũng có thể bị học theo. |
| Số lần sai mật khẩu/OTP, tần suất push | Credential stuffing, brute force, MFA fatigue | Dễ bị lợi dụng để gây khóa dịch vụ; kết hợp giới hạn tốc độ và cơ chế phục hồi. |
| Trạng thái authenticator | Thiết bị mới đăng ký, credential vừa thu hồi, sự kiện recovery | Dữ liệu phải lấy từ hệ thống tin cậy, có audit; không tin cờ do client gửi. |
| Hành vi giao dịch | Giá trị lớn, người nhận mới, bất thường về tốc độ | Có thể là hành vi hợp lệ; cân nhắc xác nhận nội dung giao dịch. |
| Kết quả attestation / tín hiệu thiết bị quản lý | Mức đáp ứng chính sách phần cứng/thiết bị | Chỉ đáng tin khi nguồn và chữ ký được xác minh; không tương đương chứng minh danh tính người dùng. |
| Kết quả từ IdP | Phương thức, thời điểm và ngữ cảnh đã xác thực | Chỉ dùng sau khi xác minh assertion/token và thỏa thuận cách diễn giải. |

Một tín hiệu nên đi kèm **nguồn, thời điểm, độ tin cậy, hạn dùng và mục đích sử dụng**. Không coi một header như **X-Device-Trusted: true**, hay một thuộc tính JavaScript tự báo từ trình duyệt, là tín hiệu tin cậy khi chưa có cơ chế xác minh.

**Rủi ro chưa biết** khác với **rủi ro thấp**. Nếu hệ thống giám sát không hoạt động, thông tin thiết bị thiếu hoặc IdP không cung cấp thông tin đã thỏa thuận, chính sách cần chuyển sang trạng thái an toàn đã định sẵn. Với thao tác nhạy cảm, không nên tự động cho phép do điểm rủi ro bị thiếu.

### Giới hạn về quyền riêng tư và tính công bằng

Theo dõi liên tục có thể khiến sản phẩm thu thập quá nhiều dữ liệu về vị trí, thiết bị và hành vi. Chỉ thu thập tín hiệu thật sự phục vụ quyết định, giới hạn lưu giữ và quyền truy cập, thông báo minh bạch và tránh biến đặc điểm cá nhân được bảo vệ thành tiêu chí nghi ngờ.

Người dùng hay đi công tác, dùng VPN, sử dụng thiết bị hỗ trợ tiếp cận hoặc đổi mạng thường xuyên có thể bị gắn cờ nhiều hơn. Cần kiểm thử **false positive** và có lựa chọn xác thực bổ sung khả dụng, thay vì khóa vô thời hạn.

## 6. Từ tín hiệu đến quyết định: xây policy có thể giải thích

Một hệ thống thường chia đánh giá thành ba bước: **xác định yêu cầu tối thiểu**, **đánh giá rủi ro ngữ cảnh**, **thực thi kiểm soát**.

~~~mermaid
flowchart TD
    A["Yêu cầu đăng nhập hoặc thao tác"] --> B["Xác định account, tenant, tác vụ"]
    B --> C["Tải policy tối thiểu theo vai trò và tác vụ"]
    C --> D["Xác minh bằng chứng / trạng thái phiên hiện có"]
    D --> E["Thu thập tín hiệu rủi ro từ nguồn được tin cậy"]
    E --> F{"Đạt assurance tối thiểu?"}
    F -- "Không" --> G["Step-up / chặn / quy trình hỗ trợ"]
    F -- "Có" --> H{"Rủi ro hiện tại chấp nhận được?"}
    H -- "Không" --> I["Tăng kiểm tra, giới hạn hoặc từ chối"]
    H -- "Có" --> J["Kiểm tra quyền đối với tài nguyên"]
    J --> K{"Được phép?"}
    K -- "Không" --> L["Từ chối"]
    K -- "Có" --> M["Thực hiện và ghi audit phù hợp"]
~~~

Thứ tự có thể thay đổi giữa đăng nhập và thao tác nghiệp vụ, nhưng **mọi đường thành công** phải thỏa cả yêu cầu bảo đảm và quyền truy cập.

### 6.1. Bảng quyết định minh họa

Giả sử ứng dụng phân các tác vụ thành ba lớp nội bộ: **BASIC**, **SENSITIVE**, **PRIVILEGED**. Đây là tên do sản phẩm tự đặt, **không phải nhãn AAL chuẩn**.

| Tác vụ | Yêu cầu tối thiểu | Nếu tín hiệu bất thường | Khi không đủ bằng chứng |
| --- | --- | --- | --- |
| Xem bài học cá nhân | Phiên hợp lệ theo baseline của tài khoản | Có thể yêu cầu xác thực lại hoặc giới hạn thao tác | Chuyển đến đăng nhập. |
| Đổi tên hiển thị | Phiên hợp lệ và kiểm tra CSRF/quyền | Yêu cầu xác thực gần hơn nếu bị nghi chiếm phiên | Không ghi dữ liệu. |
| Đổi email khôi phục | Xác thực lại đủ mạnh, xác minh kênh mới | Trì hoãn/kiểm tra bổ sung, thông báo kênh cũ | Không kích hoạt email mới. |
| Thêm hoặc xóa passkey | Bằng chứng mới từ authenticator đủ mức yêu cầu | Tăng kiểm tra, ghi audit và thông báo | Giữ credential hiện tại, chuyển recovery có kiểm soát. |
| Cấp quyền quản trị | Phương thức chống phishing, quyền phê duyệt, chính sách tổ chức | Có thể chặn và yêu cầu quy trình xác minh độc lập | Không cấp quyền. |
| Đổi thông tin thanh toán | Xác thực mạnh đủ mới; có thể ràng buộc người nhận/số tiền | Step-up hoặc duyệt thủ công phù hợp rủi ro | Không thực hiện giao dịch. |

Các ngưỡng thời gian, giới hạn số lần thử và định nghĩa “rủi ro cao” phải được phê duyệt dựa trên tác động thực tế. Không sao chép giá trị ngưỡng từ một sản phẩm khác như thể đó là yêu cầu chuẩn.

### 6.2. Ví dụ chấm điểm minh họa

Một đội có thể dùng điểm **0–100** để phục vụ vận hành, nhưng đây **chỉ là mô hình ví dụ**, không phải xác suất kẻ tấn công hay con số do tiêu chuẩn quy định:

~~~text
Các dấu hiệu:
  +25  Nhiều lần sai credential trong một khoảng ngắn
  +20  Authenticator vừa được đăng ký qua luồng rủi ro
  +20  Thiết bị hoặc phiên mới không có lịch sử đáng tin
  +30  Có dấu hiệu phishing/replay đáng tin
  +15  Yêu cầu hành động tài chính bất thường

Điểm số dùng để tăng mức xem xét trong phạm vi policy.
Không trừ điểm để bỏ yêu cầu MFA/phishing resistance bắt buộc.
Không lấy điểm 0 làm bằng chứng tài khoản chắc chắn an toàn.
~~~

Nhược điểm của mô hình cộng điểm là tín hiệu có thể **tương quan** (IP mới và vị trí mới cùng đến từ một nguyên nhân), bị kẻ tấn công thao túng và thay đổi theo thời gian. Hệ thống triển khai thật cần quản lý phiên bản, hiệu chỉnh trên dữ liệu phù hợp, kiểm tra độ chính xác và giám sát tác động. Dấu hiệu bị thu hồi phiên hoặc tài khoản bị khóa thường cần quy tắc **từ chối trực tiếp**, không được trung hòa bằng các điểm “tốt”.

## 7. Assurance đạt được phải dựa trên bằng chứng được xác minh

Sau khi verifier chấp nhận credential, hệ thống có thể tạo một **authentication context** gắn với principal và phiên:

~~~json
{
  "accountId": "acc-1742",
  "tenantId": "tenant-A",
  "authTime": "2026-11-22T04:00:00Z",
  "methods": ["password", "webauthn"],
  "phishingResistantVerified": true,
  "assurancePolicy": "privileged-v3",
  "sessionId": "<opaque-session-reference>"
}
~~~

Đây là **cấu trúc minh họa**, không phải format token chuẩn. Các trường chỉ được đưa vào ngữ cảnh tin cậy sau khi server **thực sự kiểm tra** bằng chứng theo giao thức. Không nhận các giá trị này từ body của client để tự nâng cấp assurance.

- **accountId/tenantId** xác định chủ thể và phạm vi nội bộ.
- **authTime** là thời điểm kiểm tra credential có ý nghĩa theo chính sách, không tự cập nhật chỉ vì làm mới access token.
- **methods** thể hiện các phương thức đã hoàn tất, nhưng việc diễn giải mức bảo đảm còn phụ thuộc chi tiết cấu hình và vòng đời.
- **phishingResistantVerified** chỉ được đặt khi verifier xác minh giao thức đủ điều kiện, chẳng hạn WebAuthn với challenge, origin và RP ID đúng.
- **assurancePolicy** hoặc phiên bản chính sách giúp giải thích vì sao quyết định được đưa ra; không mặc định có nghĩa tương đương AAL của tiêu chuẩn.
- **sessionId** phải được bảo vệ; không ghi token bearer thực vào log hoặc trả về ở cấu trúc dành cho bên không tin cậy.

**Mức bảo đảm không nên tăng chỉ từ một lần refresh token.** Một token mới có thể mang cùng kết quả xác thực cũ; việc xác thực lại cần một sự kiện verifier kiểm tra authenticator mới.

## 8. Step-up: tăng bằng chứng khi rủi ro hoặc hậu quả tăng

**Step-up authentication** là yêu cầu người dùng thực hiện một bước xác thực bổ sung hoặc xác thực lại bằng phương thức mạnh hơn, để đạt yêu cầu mới trước khi thực hiện hành động.

Ví dụ:

~~~text
09:00  Người dùng đăng nhập, server kiểm tra password + TOTP.
       Session S1 được tạo và gắn authTime=09:00.
10:15  Người dùng xem tiến độ khóa học: S1 còn phù hợp.
10:20  Người dùng muốn đổi email khôi phục:
       Policy yêu cầu xác thực lại gần đây, đủ mạnh.
       Server tạo giao dịch STEP_UP chỉ cho tác vụ CHANGE_RECOVERY_EMAIL.
10:21  Người dùng xác thực bằng passkey tại đúng RP ID/origin.
       Server kiểm tra challenge, chữ ký, UP/UV theo policy.
10:22  Server kiểm tra lại giao dịch, trạng thái account, quyền và email mới.
       Hoàn thành đổi email, ghi audit và gửi thông báo phù hợp.
~~~

Step-up tốt phải gắn với **đúng account, đúng session, đúng mục đích, đúng giao dịch và thời hạn**. Không chấp nhận một OTP/challenge của luồng đăng nhập A để vượt bước tăng cường trên tài khoản B. Với hành động nhạy cảm, có thể ràng buộc sự chấp thuận vào **nội dung giao dịch**: người nhận, số tiền, tài nguyên hoặc quyền được thay đổi.

### Step-up khác yêu cầu đăng nhập lại tùy tiện

Việc hiển thị thêm một hộp thoại mật khẩu không tự đảm bảo mạnh hơn, nhất là khi kẻ tấn công đã có mật khẩu hoặc có thể phishing lại. Cần xác định **yếu tố còn thiếu**, độ mạnh của phương thức mới và khả năng chống phishing.

Người dùng đã xác thực bằng passkey có UV đủ chính sách có thể không cần nhập thêm một mật khẩu chỉ để có “hai bước”. Ngược lại, khi hành động yêu cầu ràng buộc giao dịch chặt hơn, ngay cả phiên có MFA cũng có thể cần xác nhận mới.

### Trạng thái giao dịch

~~~text
AUTHENTICATED_BASELINE
        |
        | request high-impact action
        v
STEP_UP_REQUIRED
        |
        | server issues one-time challenge bound to account/session/action
        v
STEP_UP_PENDING
        |
        | verifier checks credential, expiry, binding, replay protection
        v
STEP_UP_VERIFIED
        |
        | server checks authorization and action data again
        v
ACTION_COMMITTED
~~~

Các trạng thái **EXPIRED**, **FAILED**, **CANCELLED** hoặc **REVOKED** phải không thể chuyển thẳng đến ACTION_COMMITTED. Giao dịch đã sử dụng không được hoàn tất lần hai; bảo vệ dữ liệu trạng thái bằng thao tác nguyên tử hoặc cơ chế tương đương khi có request đồng thời.

## 9. Ranh giới tin cậy trong hệ thống assurance thích ứng

Một kiến trúc có thể gồm: ứng dụng phía client, authentication service/verifier, risk engine, kho credential, session/token service, IdP liên kết và API tài nguyên.

~~~mermaid
flowchart LR
    U["Người dùng và authenticator"] --> C["Client không tin cậy"]
    C --> V["Verifier / Authentication service"]
    V <--> CR[("Credential store")]
    V --> R["Risk engine và policy"]
    R --> V
    V --> S["Session / token service"]
    S --> C
    C --> API["API tài nguyên"]
    API --> P["Authorization policy"]
    API --> D[("Dữ liệu")]
    IDP["IdP tin cậy theo cấu hình"] --> V
~~~

Cần trả lời ít nhất năm câu hỏi:

1. **Ai được cấp tín hiệu?** Tín hiệu từ client chỉ là dữ liệu đầu vào. Nếu dùng device attestation hoặc tín hiệu máy quản lý, phải xác minh nguồn, thời gian, chữ ký và mục đích.
2. **Ai được tính rủi ro?** Risk engine có thể tư vấn tăng yêu cầu; không thể tự tạo principal hoặc cấp quyền. Đầu ra risk engine cần chống giả mạo và chỉ có thời hạn hợp lý.
3. **Ai xác minh credential?** Verifier kiểm tra mật khẩu, TOTP, chữ ký passkey, chứng chỉ hoặc thông điệp IdP theo cơ chế được thiết lập tin cậy.
4. **Ai ghi kết quả assurance?** Phía server tạo phiên/token từ những kiểm tra đã thực hiện. Không cho client chỉnh sửa trường authTime, acr, mfaPassed hoặc userId để nâng quyền.
5. **Ai quyết định được dùng tài nguyên?** API kiểm tra phiên/token, bảo đảm yêu cầu, tenant và phân quyền tại thời điểm thực hiện; gateway xác thực trước đó không thay thế phân quyền theo tài nguyên.

Nếu mọi trạng thái assurance được lưu trong JWT, API phải kiểm tra chữ ký, issuer, audience, expiry, thuật toán được cho phép và các điều kiện liên quan. Nếu chính sách/tài khoản thay đổi trong khi token còn hạn, cần chiến lược **token ngắn hạn, introspection hoặc thu hồi** theo rủi ro. Một token có assurance claim hợp lệ vẫn không cấp quyền vượt quá chính sách hiện hành.

## 10. Phishing, replay và lạm dụng đăng nhập

Điểm rủi ro không sửa được nhược điểm mật mã của authenticator.

### 10.1. Phishing theo thời gian thực

Kẻ tấn công dựng trang giả, thu mật khẩu rồi yêu cầu người dùng nhập TOTP/SMS OTP. Mã được chuyển tiếp ngay đến trang thật; đôi khi kẻ tấn công còn lấy được cookie phiên. Risk engine có thể phát hiện bất thường, nhưng nếu tín hiệu không đủ, attacker vẫn vượt qua MFA dạng mã.

**Kiểm soát:** ưu tiên phương thức chống phishing như WebAuthn/passkey khi chính sách cần, kiểm tra đúng challenge, RP ID, origin, chữ ký và các cờ thích hợp. Với client certificate/smart card, phải đánh giá giao thức, ràng buộc máy chủ và bảo vệ khóa. **OTP không tự trở thành chống phishing chỉ vì có giới hạn thời gian.**

### 10.2. Replay và dùng sai ngữ cảnh

Một OTP hết hạn sẽ bị từ chối, nhưng mã **chưa hết hạn** cũng cần bị từ chối khi đã dùng, sai tài khoản hoặc sai mục đích. Verifier TOTP phải ngăn chấp nhận lại mã/bước thời gian đã dùng theo chính sách và xử lý yêu cầu đồng thời. WebAuthn cần challenge ngẫu nhiên, còn hiệu lực, gắn với đúng giao dịch và không được tái sử dụng.

Token bearer có thể được dùng nhiều lần cho các request hợp lệ; chống rủi ro của token bị lộ bằng bảo vệ lưu trữ, hạn dùng, scope/audience, thu hồi và sender-constrained token nếu phù hợp. **Không đồng nhất chống replay của challenge xác thực với cách vận hành của access token.**

### 10.3. Credential stuffing và MFA fatigue

Thử mật khẩu lộ hàng loạt có thể khiến risk engine tăng yêu cầu hoặc giới hạn tốc độ. Cần giới hạn theo nhiều chiều (account, IP, thiết bị, giao dịch), giám sát tỷ lệ thất bại và bảo vệ khỏi lockout lạm dụng. Với push MFA, hiển thị thông tin đăng nhập, number matching, giới hạn push và khả năng báo “không phải tôi” giúp giảm bấm duyệt vì mệt mỏi.

### 10.4. Chiếm phiên sau xác thực

Một phiên được tạo sau MFA mạnh vẫn có thể bị lộ qua XSS, mã độc trên thiết bị hoặc xử lý token sai. Cần cookie Secure/HttpOnly/SameSite phù hợp, bảo vệ CSRF khi cần, chống XSS, làm mới session ID sau đăng nhập, timeout, thu hồi và step-up cho tác vụ nhạy cảm. Assurance **không có nghĩa phiên bất khả xâm phạm**.

## 11. Federation: assurance của IdP không tự động trở thành assurance của RP

Trong OpenID Connect, ứng dụng **Relying Party (RP)** có thể dựa vào **Identity Provider (IdP)** để xác thực người dùng. Trước khi tin kết quả, RP phải kiểm tra đúng giao thức: issuer, audience, chữ ký, thời hạn, nonce khi áp dụng, state/PKCE ở luồng phù hợp và ánh xạ danh tính theo **issuer + subject** trong phạm vi cần thiết.

Một số claim có thể giúp đánh giá:

- **auth_time:** thời điểm xác thực; hữu ích để đánh giá độ mới khi được trả về theo giao thức và được xác minh.
- **amr:** các phương thức xác thực đã dùng, theo từ vựng mà IdP và RP đã thỏa thuận.
- **acr:** lớp/ngữ cảnh xác thực theo thỏa thuận giữa các bên.

**Không có quy tắc phổ quát rằng chuỗi amr chứa “mfa” thì RP đã đạt mọi yêu cầu.** RP phải biết IdP đã dùng phương thức gì, mức chống phishing ra sao, thời điểm gần nhất và cách khôi phục/đăng ký authenticator theo hợp đồng tin cậy.

Ví dụ: RP yêu cầu xác thực chống phishing để cấp đặc quyền quản trị. IdP chỉ báo đã dùng “password+SMS”, dù có hai yếu tố, thì **chưa chứng minh** thuộc tính chống phishing. RP phải yêu cầu bước xác thực phù hợp hoặc từ chối theo chính sách.

Khi gửi yêu cầu xác thực tăng cường sang IdP, không chỉ dựa vào việc redirect đã quay về: phải **kiểm tra response và thông tin assurance thực tế** trước khi cho phép hành động. Nếu IdP không cung cấp ngữ cảnh đã thỏa thuận, áp dụng hướng xử lý dự phòng được định nghĩa trước.

### Liên kết danh tính và rủi ro

Không tự gộp hai tài khoản chỉ vì email từ hai IdP giống nhau. Email có thể thay đổi hoặc được tái cấp; **sub** có nghĩa trong phạm vi **iss**. Liên kết credential mới hoặc IdP mới vào account hiện tại có thể cần step-up, bằng chứng từ cả account hiện tại và danh tính mới, kiểm tra xung đột, thông báo và audit. Nếu liên kết sai, mức bảo đảm đăng nhập cao cũng không cứu được dữ liệu thuộc tài khoản bị gộp nhầm.

## 12. Recovery: đường yếu nhất có thể quyết định rủi ro toàn tài khoản

Khi người dùng mất passkey hoặc thiết bị MFA, hệ thống cần quy trình khôi phục. Nhưng khôi phục là **một đường thay đổi quyền kiểm soát tài khoản**, không chỉ tác vụ chăm sóc khách hàng.

### 12.1. Mô hình hóa recovery như một sự kiện bảo mật

Một luồng có thể gồm:

1. Tìm account dựa trên identifier, tránh lộ quá nhiều thông tin về tài khoản tồn tại.
2. Thu thập bằng chứng khôi phục theo chính sách rủi ro, không coi việc biết email, tên hoặc ngày sinh là bằng chứng đủ.
3. Xác minh recovery code đã cấp trước, authenticator dự phòng, kênh liên hệ hoặc quy trình hỗ trợ có kiểm soát tùy mức tác động.
4. Giới hạn số lần thử, thời hạn, ngăn dùng lại mã, chống social engineering và ghi nhận bằng chứng/quyết định thích hợp.
5. Thu hồi hoặc vô hiệu hóa authenticator bị mất; cân nhắc thu hồi phiên/token cũ, thông báo thay đổi qua kênh còn tin cậy.
6. Cấp credential mới qua quy trình đăng ký chặt chẽ, yêu cầu kiểm tra bổ sung trước khi mở ngay các thao tác cực kỳ nhạy cảm nếu chính sách cần.

Một **recovery code** hoặc liên kết email có thể là đường hợp lệ để phục hồi truy cập trong hệ thống cụ thể, nhưng không tự làm cho phiên vừa khôi phục có cùng assurance với một phiên đã xác thực bằng phương thức chống phishing. Chính sách có thể đặt trạng thái **RECENTLY_RECOVERED**, hạn chế thêm credential, đổi thông tin thanh toán hoặc cấp quyền đặc biệt cho đến khi đáp ứng yêu cầu bổ sung.

### 12.2. Quy tắc không thể bị điểm rủi ro bỏ qua

Nếu một tài khoản quản trị bắt buộc phải dùng authenticator chống phishing, không thể kết luận “thiết bị quen thuộc nên tắt MFA cho lần này”. Nếu nhân viên hỗ trợ có quyền bỏ điều kiện, chính đường hỗ trợ trở thành mục tiêu tấn công. Ngoại lệ phải được kiểm soát, có thẩm quyền và audit, đồng thời vẫn đáp ứng mức bảo đảm do tổ chức quy định.

### 12.3. Hiệu ứng của thay đổi thông tin liên lạc

Email và số điện thoại có thể thay đổi chủ sở hữu. Trường **verified_at** chỉ nói rằng đã xác minh ở một thời điểm, không bảo đảm một người còn kiểm soát mãi. Việc thay email khôi phục nên yêu cầu kiểm tra phiên đủ mạnh, xác minh kênh mới và thông báo kênh cũ khi phù hợp. Không cho người mới nhận số điện thoại cũ tự động kế thừa toàn bộ lịch sử tài khoản chỉ vì nhận được SMS.

## 13. Thiết kế policy engine thực tế

Một policy engine có thể nhận **request context**, **principal/session**, **trạng thái account**, **tín hiệu rủi ro** và **yêu cầu bảo đảm của hành động**, rồi trả về một quyết định có lý do.

### 13.1. Hợp đồng đầu vào/đầu ra

~~~text
Input:
  actorAccountId, tenantId, action, targetResource
  authenticatedMethods, authTime, assuranceEvidence
  sessionStatus, credentialStatus, recoveryEvents
  verifiedRiskSignals, policyVersion

Output:
  decision: ALLOW | STEP_UP | DENY | REVIEW
  reasonCodes: [ ... ]
  requiredEvidence: [ ... ] (khi STEP_UP)
  stepUpTransaction: <server-generated reference> (nếu cần)
  policyVersion: ...
~~~

**ALLOW** chỉ áp dụng sau khi kiểm tra quyền. **STEP_UP** biểu thị chưa đủ bằng chứng nhưng có một phương thức hợp lệ để đạt yêu cầu. **DENY** cho trường hợp bị cấm, phiên bị thu hồi, tài khoản bị khóa hoặc vi phạm ràng buộc. **REVIEW** dành cho hành động đã quy định cần quy trình thủ công, không phải con đường tự động cấp quyền trong lúc chờ.

Tránh cho risk engine được phép trực tiếp ký token hoặc cấp vai trò. Vai trò của nó là **đưa tín hiệu/quyết định theo chính sách**; authentication service và authorization layer vẫn chịu trách nhiệm kiểm tra bằng chứng và quyền.

### 13.2. Giả mã kiểm tra một tác vụ nhạy cảm

~~~java
Decision authorizeSensitiveAction(Request request, Session session) {
    Principal actor = sessionVerifier.requireValidPrincipal(session);
    Account account = accountStore.requireActive(actor.accountId());
    Resource target = resourceStore.loadForTenant(
        actor.tenantId(), request.targetId());

    // Được phép làm việc trên tài nguyên này hay không?
    if (!authorizationService.canPerform(actor, request.action(), target)) {
        return Decision.deny("NOT_AUTHORIZED");
    }

    AssurancePolicy policy = policyStore.forAction(
        account.tenantId(), actor.roles(), request.action());

    RiskSignals signals = signalCollector.collectVerified(
        actor, session, request, target);

    if (session.isRevoked() || account.isLocked()) {
        return Decision.deny("REVOKED_OR_LOCKED");
    }

    if (!assuranceService.meetsRequiredEvidence(
            session.authContext(), policy.minimumEvidence())) {
        return Decision.stepUp(policy.requiredAuthenticator());
    }

    RiskDecision risk = riskEngine.evaluate(signals, policy);
    if (risk.mustDeny()) {
        return Decision.deny("RISK_POLICY_DENY");
    }
    if (risk.needsFreshAuthentication()
            || assuranceService.isTooOld(session.authContext(), policy)) {
        return Decision.stepUp(policy.requiredFreshEvidence());
    }

    return Decision.allow(policy.version());
}
~~~

Đây là **giả mã minh họa ranh giới trách nhiệm**, không phải thư viện có thể chạy ngay. Trong một hệ thống thật, phải xác minh quyền/trạng thái **lại tại điểm commit**, chống TOCTOU khi quyền hoặc dữ liệu giao dịch đổi giữa lúc step-up và thực thi, quản lý race condition và dùng các thành phần xác thực/giao thức đã kiểm chứng.

### 13.3. Tách quyết định khỏi điểm rủi ro

Không nên có một phép so sánh duy nhất kiểu “score < 50 thì đăng nhập, score ≥ 50 thì cấm”. Các ràng buộc mạnh được thực thi **trước hoặc độc lập với** điểm rủi ro:

- Phiên bị thu hồi hoặc chữ ký token không hợp lệ → **DENY**, không cần tính điểm.
- Người dùng không có quyền trên tài nguyên → **DENY**.
- Phương thức không đạt yêu cầu tối thiểu → **STEP_UP/DENY** theo policy.
- Tín hiệu nghi ngờ phiên bị chiếm → **STEP_UP/REVIEW/DENY** tùy mức tin cậy và hậu quả.
- Hoàn thành đầy đủ kiểm tra → **ALLOW** trong phạm vi hành động cụ thể.

Nếu mô hình chấm điểm bị lỗi, kết quả dự phòng phải được định nghĩa cho từng nhóm tác vụ. Không được **fail open** với hành động rủi ro cao chỉ vì risk engine không phản hồi.

## 14. Session, token và độ mới của xác thực

Sau đăng nhập, ứng dụng thường duy trì quyền sử dụng qua session cookie hoặc access token. Đánh giá risk-based assurance phải xét thêm **độ mới của lần xác thực** và khả năng phiên bị chiếm.

| Vật mang/trạng thái | Vai trò | Yêu cầu quan trọng |
| --- | --- | --- |
| Session ID trong cookie | Tham chiếu trạng thái phiên ở server | Ngẫu nhiên, khó đoán, Secure/HttpOnly/SameSite phù hợp, hạn dùng, thu hồi, làm mới ID sau đăng nhập. |
| Access token | Cấp phạm vi truy cập API trong thời gian nhất định | Kiểm tra issuer, audience, signature/introspection, expiry, scope/quyền và bảo vệ token. |
| Refresh token | Xin access token mới mà không bắt nhập credential ở mọi lần | Lưu an toàn, cơ chế xoay vòng hoặc ràng buộc người gửi phù hợp, phát hiện tái sử dụng, thu hồi. |
| Authentication context | Bằng chứng và thời điểm đã xác thực | Không cho client tự chỉnh; không tăng authTime chỉ do refresh token. |
| Step-up transaction | Ràng buộc một yêu cầu tăng bảo đảm với phiên/tác vụ | Challenge ngẫu nhiên, mục đích, thời hạn, ngăn replay, chỉ dùng một lần. |

Một session có thể hợp lệ để đọc tài liệu nhưng đã quá cũ cho phép đổi credential. Đây là khác biệt giữa **session còn hiệu lực** và **sự kiện xác thực đủ mới**. Với JWT, token cũ chứa assurance claim không tự động phản ánh thay đổi chính sách hay thu hồi credential; chọn thời hạn, phương thức kiểm tra trạng thái và bước xác thực lại phù hợp.

Khi đòi xác thực lại, UI phải trình bày rõ **người dùng chuẩn bị cho phép thao tác gì**, nhất là thay quyền hoặc giao dịch. Không kéo dài mọi quyền đặc biệt vĩnh viễn sau một lần step-up.

## 15. Vận hành, đo lường và kiểm thử chính sách

Risk-based assurance cần được đánh giá bằng khả năng **ngăn tấn công** lẫn trải nghiệm của người dùng hợp lệ.

### 15.1. Các chỉ số theo dõi

- Tỷ lệ đăng nhập thành công/thất bại theo phương thức và nhóm rủi ro, sau khi tách lưu lượng tự động hóa.
- Số lần step-up được yêu cầu, hoàn thành và hủy; tỷ lệ người dùng hợp lệ bị chặn nhầm (**false positive**).
- Sự kiện phát lại OTP/challenge, phishing được báo cáo, MFA fatigue, credential stuffing, phiên bị thu hồi.
- Số lần recovery, thay đổi authenticator, thời gian hoàn tất recovery, số lần bị nghi lạm dụng hỗ trợ.
- Tỷ lệ phương thức chống phishing được sử dụng cho nhóm tài khoản nhạy cảm.
- Độ trễ quyết định, tình trạng không nhận được tín hiệu, tác động của thay đổi model/policy theo phiên bản.
- Số sự cố truy cập sai quyền, bởi **MFA không thay thế authorization**.

Không lưu OTP, mã khôi phục, private key, session cookie hoặc bearer token trong log. Với thông tin hành vi và thiết bị, chỉ thu thập phần đủ để phát hiện rủi ro và kiểm tra hiệu quả, đồng thời có chính sách lưu giữ/xóa thích hợp.

### 15.2. Ma trận kiểm thử

| Ca thử | Kỳ vọng |
| --- | --- |
| IP mới nhưng passkey hợp lệ, tác vụ thông thường | Áp dụng risk policy; không mặc định quy kết tấn công chỉ từ IP. |
| Tác vụ quản trị từ IP quen nhưng chỉ có mật khẩu | Không vượt qua yêu cầu phương thức tối thiểu. |
| TOTP đã dùng được gửi lại trong cửa sổ thời gian | Bị từ chối theo chính sách chống replay. |
| Thay tài khoản giữa bước MFA/step-up | Giao dịch cũ không áp dụng cho account mới. |
| Token sai audience hoặc issuer | Bị từ chối trước khi tính assurance. |
| Client tự gửi "risk=low" hoặc "mfa=true" | Không có tác dụng nâng bảo đảm. |
| Phiên bị thu hồi nhưng token còn thời hạn | Không được dùng tại điểm kiểm tra có cơ chế thu hồi. |
| Refresh token được cấp lại | Không tự thay đổi authTime thành thời điểm hiện tại. |
| IdP trả amr không đủ cho yêu cầu chống phishing | Không nâng assurance; yêu cầu flow phù hợp. |
| Email vừa thay và chưa xác minh | Không dùng như kênh recovery đã tin cậy. |
| Tài khoản vừa khôi phục bằng kênh yếu muốn cấp quyền quản trị | Áp dụng policy hạn chế và xác thực lại mạnh. |
| Hai request dùng cùng step-up challenge | Tối đa một giao dịch được hoàn tất; kiểm tra tính nguyên tử. |
| Risk engine không phản hồi | Hệ thống thực thi chính sách dự phòng, không tự mở thao tác nhạy cảm. |
| Người dùng A đã xác thực mạnh gọi tài nguyên B | Bị từ chối nếu thiếu quyền tài nguyên hoặc tenant. |
| Thay số tiền sau khi xác nhận giao dịch | Từ chối hoặc yêu cầu phê duyệt lại theo dữ liệu mới. |

### 15.3. Đánh giá tác động khi đổi policy

Trước khi áp dụng quy tắc mới rộng rãi, có thể dùng **shadow evaluation** (tính quyết định thử mà chưa thực thi) trên dữ liệu đã được quản lý phù hợp để đo tỷ lệ bị chặn nhầm. Sau đó triển khai theo nhóm nhỏ, so sánh rủi ro và tác động, có khả năng rollback policy khi phát hiện sự cố. Không dùng rollout thử nghiệm để bỏ bảo vệ bắt buộc ở tài khoản nhạy cảm.

Đánh giá theo thời gian vì kẻ tấn công học cách né tín hiệu, còn thiết bị/ngữ cảnh người dùng thay đổi. Lưu dấu vết **policy version, reason code, kết quả** để điều tra quyết định nhưng phải tránh ghi dữ liệu bí mật.

## 16. Bài tập tình huống: hệ thống trả học phí và quản trị đào tạo

Một nền tảng có ba vai trò: **học viên**, **kế toán** và **quản trị viên**.

- Học viên xem lịch học bằng phiên đăng nhập thông thường.
- Kế toán thay tài khoản ngân hàng nhận hoàn học phí.
- Quản trị viên thêm phương thức SSO mới cho toàn bộ tổ chức.

Hệ thống nhận các tình huống:

1. Học viên đăng nhập bằng mật khẩu + TOTP từ mạng di động mới, không có dấu hiệu bất thường khác.
2. Kế toán đã qua TOTP sáng nay, lúc chiều đổi tài khoản thụ hưởng từ một trình duyệt chưa từng thấy.
3. Quản trị viên dùng passkey đã đăng ký để đăng nhập, nhưng account vừa trải qua recovery thủ công.
4. Một IdP mới gửi ID token có email trùng tài khoản quản trị, kèm claim "mfa" nhưng chưa có thỏa thuận về mức bảo đảm.

**Câu hỏi thiết kế:**

- Hành động nào cần baseline, hành động nào cần xác thực lại hoặc xác nhận giao dịch?
- Những yếu tố nào là ràng buộc bắt buộc không được bỏ dù điểm rủi ro thấp?
- Với trường hợp kế toán, tín hiệu thiết bị mới nên tăng kiểm tra ra sao để vẫn cho người hợp lệ tiếp tục?
- Điều gì ngăn tài khoản vừa khôi phục lập tức cấp quyền mới?
- Vì sao không thể dùng email trùng và claim "mfa" chưa xác minh để liên kết IdP mới?
- Nếu phiên của kế toán đã bị đánh cắp sau MFA, những cơ chế nào còn giảm hậu quả?

### Hướng phân tích

**Trường hợp 1:** mạng mới là tín hiệu có độ tin cậy hạn chế; nếu baseline đã đáp ứng, có thể cho học viên tiếp tục theo policy và giám sát. Không tự động suy ra nguy cơ cao chỉ vì IP khác.

**Trường hợp 2:** thay người thụ hưởng là hành động có hậu quả tài chính, nên yêu cầu xác thực đủ mới và mạnh theo baseline của giao dịch, có thể yêu cầu xác nhận gắn với **người nhận/số tiền**. Thiết bị mới tăng rủi ro; server có thể step-up và gửi thông báo độc lập, đồng thời xác minh lại toàn bộ dữ liệu ở thời điểm commit.

**Trường hợp 3:** recovery vừa xảy ra có thể thay đổi bằng chứng về quyền kiểm soát tài khoản. Chính sách có thể tạm hạn chế tác vụ quản trị, yêu cầu authenticator đủ mạnh được xác minh theo quy trình đáng tin và kiểm tra/đồng phê duyệt cần thiết.

**Trường hợp 4:** RP phải xác minh ID token và quan hệ IdP, xử lý issuer + subject theo policy, yêu cầu liên kết danh tính có kiểm soát; email và claim "mfa" không đủ để tự xác định account hoặc mức assurance.

**Phòng thủ chung:** chính sách theo tác vụ; bảo vệ phiên và token; step-up có giao dịch ngắn hạn, chống replay; authorization từng tài nguyên; recovery bảo đảm tương xứng; audit đủ để giải thích quyết định.

## 17. Câu hỏi tự đánh giá

1. Vì sao “rủi ro ngữ cảnh thấp” không chứng minh rằng credential yếu đã trở thành credential mạnh?
2. IAL, AAL và FAL tập trung vào ba khía cạnh nào của bảo đảm danh tính?
3. Vì sao phải phân biệt **required assurance** với **achieved assurance**?
4. Một token mới phát hành sau refresh có đồng nghĩa người dùng vừa xác thực lại không?
5. Tại sao OTP còn hạn vẫn có thể bị từ chối khi dùng trong step-up?
6. WebAuthn chống phishing nhờ những kiểm tra giao thức quan trọng nào?
7. Tại sao việc gỡ passkey qua tổng đài hỗ trợ có thể làm mất ý nghĩa của yêu cầu chống phishing?
8. Khi IdP trả về "mfa" trong amr, RP cần biết gì trước khi chấp nhận cho thao tác nhạy cảm?
9. Tại sao risk engine không nên tự ký token hoặc gán quyền truy cập?
10. Nếu người dùng có assurance mạnh nhưng không có quyền sửa tài khoản khác, API phải làm gì?
11. Tại sao cần thử trường hợp hai request đồng thời hoàn tất cùng một challenge?
12. Cần đo chỉ số gì để chính sách giảm tấn công mà không gây khóa nhầm hàng loạt?

**Gợi ý đáp án:** (1) IP/thiết bị quen không thay đổi loại và đặc tính bằng chứng; (2) identity proofing, authentication, federation; (3) phải so yêu cầu với những gì verifier đã kiểm tra; (4) không, authTime phải phản ánh sự kiện xác thực thật; (5) sai account/mục đích, đã dùng hoặc challenge hết hạn; (6) challenge, chữ ký, RP ID/origin và cờ UP/UV theo policy; (7) recovery yếu là đường thay credential mạnh; (8) nghĩa được thỏa thuận, độ mới, phương thức và bằng chứng IdP; (9) tách tín hiệu rủi ro khỏi xác minh principal và phân quyền; (10) từ chối; (11) để phát hiện replay/race condition; (12) tỷ lệ chặn nhầm, step-up, sự cố và kết quả thực tế theo phân nhóm.

## 18. Ghi nhớ

**Risk-based assurance là thiết kế và thực thi mức bảo đảm phù hợp với hậu quả của hành động, dựa trên bằng chứng xác thực thật sự và rủi ro ngữ cảnh đáng tin cậy.** Đánh giá rủi ro giúp lựa chọn biện pháp bổ sung, nhưng không biến một tín hiệu hành vi thành credential và không cho phép hạ thấp yêu cầu bắt buộc. Một thiết kế hoàn chỉnh phải bao phủ đăng ký authenticator, phishing/replay resistance, IdP, phiên/token, step-up, phân quyền, khôi phục, giám sát và trải nghiệm của người dùng hợp lệ.

Khi review một quyết định, hãy hỏi: **Tài sản nào đang bị đe dọa? Yêu cầu bảo đảm tối thiểu là gì? Verifier thực sự đã chứng minh được điều gì, ở thời điểm nào? Tín hiệu nào có thể bị giả mạo? Nếu credential hoặc phiên bị chiếm thì còn lớp bảo vệ nào? Ai chịu trách nhiệm cho phép hành động cuối cùng?**
