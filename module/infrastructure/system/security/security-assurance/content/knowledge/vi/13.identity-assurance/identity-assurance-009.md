# Identity recovery: Khôi phục danh tính mà không làm suy giảm assurance

## 1. Identity recovery là gì?

**Identity recovery** là tập hợp các quy trình và security controls giúp một chủ thể hợp pháp **khôi phục khả năng chứng minh và sử dụng danh tính số của mình** khi mất quyền truy cập, mất thiết bị hoặc authenticator, bị khóa tài khoản, bị nghi xâm phạm hay khi hệ thống xác thực gặp sự cố. Một luồng recovery đúng cần giúp **đúng chủ thể** quay lại sử dụng dịch vụ, đồng thời **không tạo ra đường truy cập yếu hơn** để kẻ tấn công chiếm đoạt tài khoản.

Ví dụ: người dùng đã đăng ký **passkey hoặc ứng dụng TOTP** nhưng bị mất điện thoại. Họ không thể dùng yếu tố xác thực cũ để đăng nhập hoặc đăng ký thiết bị mới. Dịch vụ phải quyết định **bằng chứng thay thế nào đủ để xác nhận quyền kiểm soát tài khoản**, ai có thể phê duyệt khôi phục, cách giới hạn phiên khôi phục và cần làm gì với các session/token đang tồn tại.

**Điểm cốt lõi:** khôi phục không chỉ là đổi một giá trị trong cơ sở dữ liệu. Nó có thể là **thay đổi danh tính xác thực được liên kết với tài khoản**, đặc biệt khi một thiết bị mới trở thành yếu tố được tin cậy để đăng nhập về sau.

Trong module **SECURITY_SECURITY_ASSURANCE**, Identity recovery cần được xem như một **chuỗi yêu cầu và kiểm chứng có bằng chứng**:

**Risk scenario → mục tiêu bảo mật → recovery policy → recovery controls → kiểm thử và giám sát → bằng chứng assurance → phát hiện → khắc phục và tái đánh giá.**

Một nút “Quên mật khẩu” hoạt động đúng theo giao diện **không đủ** để kết luận quy trình identity recovery an toàn. Phải kiểm chứng khả năng chống giả mạo, chống chiếm quyền, giới hạn scope, trạng thái sau recovery và chất lượng audit.

### 1.1. Mục tiêu bảo mật và mục tiêu sử dụng

Một luồng recovery phải cân bằng:

- **Khôi phục hợp pháp:** người có quyền thực sự có cách phục hồi khi mất thiết bị, mất authenticator hoặc không thể sử dụng một đường đăng nhập.
- **Ngăn account takeover (ATO):** bên thứ ba không thể dùng email/điện thoại bị chiếm, thông tin cá nhân dễ biết hoặc thao túng hỗ trợ để tiếp quản tài khoản.
- **Duy trì mức tin cậy:** bằng chứng recovery và cơ chế thêm authenticator mới tương xứng với rủi ro của tài khoản và hành động sau khôi phục.
- **Giảm thời gian phơi nhiễm:** challenge, token, approval và recovery session phải có thời hạn, phạm vi và khả năng thu hồi.
- **Truy vết và phản ứng:** có thể điều tra ai/đường nào đã yêu cầu, xử lý, phê duyệt, hoàn tất hoặc hủy recovery mà không làm lộ secret.
- **Khả dụng và công bằng:** không tạo cơ chế loại bỏ vĩnh viễn người dùng hợp lệ chỉ vì mất một thiết bị, nhưng cũng không buộc phải cấp quyền khi bằng chứng quá yếu.
- **Bảo vệ quyền riêng tư:** chỉ thu thập dữ liệu định danh cần thiết, hạn chế lưu giữ tài liệu nhạy cảm.

**Recovery thành công về mặt chức năng** khác **recovery đạt yêu cầu assurance**. Nếu ai biết ngày sinh và số điện thoại cũng có thể chiếm tài khoản, người dùng hợp lệ có thể dễ khôi phục nhưng hệ thống đang có lỗ hổng nghiêm trọng.

## 2. Phân biệt các tình huống thường bị gọi chung là recovery

| Tình huống | Điều người dùng bị mất hoặc gặp lỗi | Mục tiêu xử lý | Rủi ro đáng chú ý |
| --- | --- | --- | --- |
| **Password reset** | Quên mật khẩu, còn recovery channel phù hợp | Đặt credential mới | Email hoặc kênh reset bị chiếm |
| **Authenticator recovery** | Mất ứng dụng TOTP, khóa bảo mật hoặc passkey trên thiết bị | Thiết lập authenticator mới sau bằng chứng đủ mạnh | Bypass MFA hoặc hạ mức assurance |
| **Account recovery** | Không còn đường đăng nhập bình thường | Khôi phục quyền kiểm soát tài khoản hợp lệ | Account takeover qua luồng thay thế |
| **Identity re-proofing** | Không đủ căn cứ liên kết người yêu cầu với danh tính đã đăng ký | Xác minh lại danh tính theo mức rủi ro và quy định áp dụng | Giả mạo giấy tờ, dữ liệu không chính xác, lộ thông tin cá nhân |
| **Account unlock** | Tài khoản bị khóa do chính sách hoặc hành vi bất thường | Mở khóa khi điều kiện an toàn được đáp ứng | Mở khóa cho kẻ đang thử chiếm account |
| **Compromised-account recovery** | Có dấu hiệu tài khoản/credential/session bị xâm phạm | Cô lập quyền trái phép rồi tái lập quyền hợp lệ | Kẻ tấn công còn giữ session, OAuth grant hoặc yếu tố dự phòng |
| **Federated identity recovery** | Không thể đăng nhập qua IdP doanh nghiệp/SSO | Khôi phục tại cấp thích hợp và đồng bộ trạng thái | Ứng dụng tự mở đường đăng nhập yếu ngoài IdP |
| **Workload identity recovery** | Mất khóa/secret, certificate hết hạn, service principal bị compromise | Cấp lại danh tính máy và khôi phục dịch vụ | Cấp credential rộng, giữ credential bị lộ còn hiệu lực |

Không phải mọi trường hợp đều cần **identity proofing lại từ đầu**. Nếu user vẫn đăng nhập bằng một authenticator mạnh còn lại, việc thêm yếu tố mới có thể đi qua cơ chế **step-up authentication** được phê duyệt. Nếu mất tất cả yếu tố, cần quy trình chứng minh quyền kiểm soát hoặc xác minh lại phù hợp mức assurance.

### 2.1. Identity proofing khác authentication và recovery

- **Identity proofing:** quá trình thu thập và kiểm chứng bằng chứng để thiết lập hoặc xác nhận mối liên kết giữa một người và danh tính được khai báo. Không phải mọi ứng dụng đều yêu cầu danh tính pháp lý.
- **Authentication:** chứng minh người đang truy cập kiểm soát authenticator liên kết với tài khoản.
- **Authorization:** xác định những hành động người đó có quyền làm.
- **Recovery:** thiết lập lại một hoặc nhiều phương tiện/chứng cứ để chủ thể có thể quay lại thực hiện authentication hợp lệ.
- **Rebinding authenticator:** liên kết một authenticator mới với tài khoản; đây là thao tác nhạy cảm vì có thể tạo khả năng đăng nhập lâu dài.

**Thay số điện thoại, email khôi phục, mật khẩu hoặc authenticator không phải hành động bình thường** nếu nó làm thay đổi ai có thể kiểm soát tài khoản. Các thay đổi này phải chịu chính sách và audit thích hợp.

## 3. Các khái niệm về mức bảo đảm danh tính

Một tổ chức có thể phân loại mức tin cậy khác nhau theo rủi ro của ứng dụng, tài sản và phiên đăng nhập.

Trong hệ thống thuật ngữ của **NIST SP 800-63**, thường phân biệt:

| Khái niệm | Trọng tâm | Liên hệ với recovery |
| --- | --- | --- |
| **IAL – Identity Assurance Level** | Mức bảo đảm của hoạt động xác minh danh tính và gắn nó với chủ thể | Khi cần re-proofing, phải xác định loại bằng chứng và quy trình đủ cho mức mục tiêu |
| **AAL – Authentication Assurance Level** | Mức tin cậy rằng người đang đăng nhập kiểm soát authenticator của tài khoản | Không cho một kênh recovery yếu trở thành con đường vô điều kiện vượt qua yêu cầu xác thực mạnh |
| **FAL – Federation Assurance Level** | Mức bảo đảm của giao thức và bảo vệ thông tin xác thực trong liên kết giữa IdP và relying party | Khi IdP xử lý recovery, ứng dụng dựa vào IdP cần biết tín hiệu và phiên sau recovery có phù hợp rủi ro không |

Tên và quy tắc chi tiết tùy **phiên bản tài liệu NIST**, loại hệ thống và hồ sơ tuân thủ áp dụng. Không tự kết luận một workflow đáp ứng cấp IAL/AAL/FAL chỉ dựa trên việc dùng email, SMS hay MFA. Phải tra tiêu chí chính thức của phiên bản được tổ chức lựa chọn và đánh giá bằng chứng theo đúng phạm vi.

### 3.1. Recovery assurance là “điểm yếu nhất”?

Đường recovery có thể trở thành **đường tắt để chiếm tài khoản** nếu cho phép thay yếu tố xác thực mạnh bằng bằng chứng dễ giả mạo.

Ví dụ: tài khoản buộc dùng khóa bảo mật chống phishing, nhưng helpdesk cho reset toàn bộ yếu tố khi caller biết tên, ngày sinh và bốn chữ số cuối số điện thoại. Kẻ tấn công không cần vượt qua khóa bảo mật; họ có thể tấn công helpdesk.

Vì vậy cần đánh giá **mức độ tin cậy của từng bước recovery so với mức rủi ro được bảo vệ**, chứ không chỉ đánh giá con đường đăng nhập bình thường.

### 3.2. Step-up authentication

**Step-up** yêu cầu chứng cứ xác thực mạnh hoặc bổ sung trước khi thao tác nhạy cảm như:

- Thêm/xóa authenticator.
- Đổi email/điện thoại khôi phục.
- Cấp quyền quản trị hoặc mở quyền dữ liệu nhạy cảm.
- Đổi secret/certificate, thiết lập khóa đăng nhập mới.
- Tắt MFA hoặc chuyển từ phương thức mạnh sang phương thức yếu hơn.

Step-up phải được kiểm tra ở **server và phiên thực tế**; một nút UI hoặc thông báo “đã xác nhận” không đủ. Nếu người dùng đã mất tất cả authenticator, không thể chỉ yêu cầu lại **chính yếu tố đã mất**; phải có nhánh recovery thay thế với bằng chứng thích hợp và kiểm soát rủi ro cao hơn.

## 4. Threat modeling cho identity recovery

Những kịch bản sau minh họa vì sao recovery cần được thiết kế như **security boundary**.

| ID | Threat scenario | Hậu quả | Điều cần kiểm soát |
| --- | --- | --- | --- |
| **REC-01** | Kẻ tấn công đã chiếm email yêu cầu reset mật khẩu rồi gắn MFA mới | Chiếm quyền lâu dài | Không mặc định email là bằng chứng đủ cho mọi loại tài khoản; thông báo ngoài kênh, risk assessment |
| **REC-02** | SIM swap/chiếm số điện thoại làm lộ OTP SMS | Recovery trái phép | Cân nhắc giới hạn dùng SMS theo rủi ro, phát hiện tín hiệu bất thường |
| **REC-03** | Caller giả mạo người dùng qua helpdesk bằng dữ liệu cá nhân công khai | Nhân viên hỗ trợ cấp quyền cho sai người | Quy trình xác minh mạnh, người duyệt độc lập cho trường hợp rủi ro cao, audit |
| **REC-04** | Token reset dễ đoán, sống lâu, tái sử dụng hoặc bị lộ trong log/URL | Chiếm tài khoản | Token entropy cao, one-time, TTL, bảo vệ secret và log |
| **REC-05** | Hai request cùng dùng một recovery token trước khi bị đánh dấu consumed | Replay do race condition | Consume nguyên tử, transaction/CAS, kiểm thử cạnh tranh |
| **REC-06** | API trả “email không tồn tại” hoặc lộ metadata recovery | User enumeration, hỗ trợ phishing | Phản hồi không phân biệt, rate limit và log an toàn |
| **REC-07** | Đổi authenticator thành công nhưng session bị chiếm vẫn tồn tại | Attacker duy trì truy cập | Session/token revocation theo threat, review OAuth grants và thiết bị |
| **REC-08** | Kẻ tấn công gây nhiều request recovery để khóa người dùng hợp lệ | Denial of service, social engineering | Abuse protection, giới hạn phù hợp, chống lockout bị lạm dụng |
| **REC-09** | Customer support có quyền bypass mọi MFA không cần kiểm tra | Insider risk hoặc chiếm helpdesk | Least privilege, SoD, approval, PAM và hậu kiểm |
| **REC-10** | Tài khoản nhạy cảm được khôi phục qua đường yếu hơn chính sách | Downgrade assurance | Tier theo rủi ro, giới hạn hành động sau recovery và re-verification |
| **REC-11** | Chủ tài khoản bị chiếm rồi attacker thay email recovery để chặn khôi phục | Khó khôi phục, chiếm quyền dài hạn | Kiểm tra thay đổi recovery contact, thông báo kênh cũ, quy trình tranh chấp |
| **REC-12** | Liên kết tài khoản SSO với local account qua email trùng nhưng chưa được xác minh | Account linking takeover | Liên kết theo ID tin cậy, không dựa riêng vào email tự khai |

Các kịch bản chỉ là giả thuyết để thiết kế và kiểm thử. **Threat modeling không tự chứng minh đã có lỗi**; cần kiểm tra hệ thống thực và ghi rõ bằng chứng.

### 4.1. Rủi ro từ cùng một kênh kiểm soát

Nếu email là **cả phương tiện đăng nhập và phương tiện recovery**, việc chiếm email có thể đủ để vượt nhiều control. Tương tự, gửi OTP khôi phục tới số điện thoại vốn đang có dấu hiệu SIM swap có thể làm rủi ro tăng.

Nên xem:

- Kênh recovery có **độc lập** với yếu tố bị mất/compromise?
- Kẻ tấn công giả định có thể kiểm soát cùng lúc email, số điện thoại, thiết bị hoặc session?
- Có cần nhiều chứng cứ **không cùng một điểm thất bại** cho tài khoản rủi ro cao?
- Có cách phát hiện thay đổi recovery contact hoặc device binding bất thường?
- Chính sách nào áp dụng khi người dùng không còn bất kỳ kênh đủ tin cậy nào?

**Nhiều bước không đồng nghĩa nhiều bằng chứng độc lập**. Ví dụ gửi cả email và SMS đến cùng một điện thoại bị chiếm không bảo đảm độ mạnh tương đương hai kênh độc lập.

## 5. Các phương thức identity recovery phổ biến

### 5.1. Recovery code dự phòng

**Recovery codes** được cấp trước cho chủ tài khoản có thể cho phép khôi phục khi mất authenticator. Thiết kế an toàn thường cần:

- Code do bộ sinh số ngẫu nhiên mật mã tạo ra, không dễ đoán.
- Mỗi code **dùng một lần**, có phạm vi chức năng rõ.
- Lưu **bản dẫn xuất an toàn** thay vì plaintext; hạn chế xem/khôi phục code ở phía server.
- Hướng dẫn người dùng cất giữ an toàn, không gửi code vào chat hỗ trợ.
- Tạo lại hoặc vô hiệu code cũ theo quy trình khi nghi lộ.
- Giới hạn thử sai và chống enumeration/rate abuse.
- Sau dùng code cần quy trình **bind authenticator mới** và xem xét session hiện hành.

Nếu chỉ giữ code ở thiết bị đã bị mất, recovery trở nên vô dụng. Nếu hỗ trợ dễ dàng đọc lại mọi code từ hệ thống quản trị, code có thể trở thành điểm yếu.

### 5.2. Authenticator dự phòng và passkey

**Backup authenticator** có thể là khóa bảo mật thứ hai, passkey khác hoặc phương thức được phê duyệt. Người dùng có thể đăng ký từ trước nhiều authenticator để giảm nhu cầu dùng kênh recovery yếu.

Một số **passkey được đồng bộ** qua hệ sinh thái nhà cung cấp và có cơ chế khôi phục thiết bị riêng. Điều đó có thể giúp người dùng truy cập lại, nhưng **không tự chứng minh** mọi rủi ro recovery của tài khoản dịch vụ đã được xử lý: phải xem bảo vệ tài khoản đồng bộ, hành vi của authenticator và chính sách ứng dụng.

**Thêm authenticator mới** phải yêu cầu bằng chứng thích hợp, xác minh thiết bị/khóa mới bằng challenge tương ứng và lưu trạng thái audit.

### 5.3. Email recovery link hoặc OTP

Email có thể phù hợp với một số tài khoản có mức rủi ro thấp hoặc trong cơ chế recovery có điều kiện, nhưng phải đánh giá **độ tin cậy của mailbox** và hậu quả nếu tài khoản bị chiếm.

Một recovery link/token nên:

- Có **entropy cao** từ CSPRNG.
- Có **hạn ngắn** dựa trên mục tiêu và rủi ro.
- **Ràng buộc** với account, purpose và challenge.
- **Dùng một lần**; consume nguyên tử.
- Không xuất hiện trong analytics, access log, crash report, Referrer, telemetry hoặc third-party script.
- Không tự thay đổi tài khoản qua request GET do email scanner/link preview có thể truy cập link.
- Không tạo **phiên đăng nhập đầy đủ** ngay sau khi click link nếu còn bước xác minh và bind authenticator cần thiết.

Giao diện nên phân biệt **link được mở** với **chủ thể đã hoàn tất proof và binding**. Một GET có thể chỉ hiển thị giao diện xác nhận; thao tác nhạy cảm nên cần một request có kiểm soát, bảo vệ CSRF/session theo kiến trúc.

### 5.4. SMS/voice recovery

SMS và voice có thể bị tác động bởi **SIM swap, chuyển số, chiếm thiết bị, social engineering nhà mạng** và rủi ro khác. Tổ chức phải đánh giá chúng trong bối cảnh rủi ro và phiên bản tiêu chí bảo mật áp dụng, tránh mặc định OTP SMS tương đương authenticator chống phishing.

Nếu được phép sử dụng:

- Giới hạn mục đích và độ nhạy của tài khoản.
- Có TTL, số lần thử, rate limit và chống replay.
- Theo dõi thay đổi số điện thoại gần đây và những tín hiệu bất thường khi khả thi.
- Cân nhắc trì hoãn/kiểm tra bổ sung trước khi thay authenticator hoặc giải phóng quyền nhạy cảm.
- Không hiển thị toàn bộ số điện thoại và không đưa OTP vào log.

### 5.5. Helpdesk và assisted recovery

Khi người dùng mất mọi authenticator, có thể cần một **assisted recovery** qua bộ phận hỗ trợ được huấn luyện.

Luồng này có nguy cơ **social engineering** đặc biệt cao. Các nguyên tắc gồm:

1. Phân loại tài khoản và mức hậu quả nếu cấp sai người.
2. Xác minh theo quy trình được phê duyệt; không chỉ dùng tên, ngày sinh, địa chỉ hoặc câu hỏi bí mật dễ tìm.
3. Giảm tối đa việc nhân viên hỗ trợ trực tiếp nhìn thấy secret hoặc tự đặt authenticator thay người dùng.
4. Với tài khoản rủi ro cao, có thể yêu cầu **review độc lập/dual control** và bằng chứng bổ sung.
5. Ghi case ID, nhân viên hỗ trợ, approval, phương pháp, giới hạn, thời gian và quyết định.
6. Có khả năng tạm dừng/chuyển cấp khi có tín hiệu lừa đảo hoặc tranh chấp quyền sở hữu.
7. Chỉ cấp **recovery-limited capability**, không tự động trao toàn quyền quản trị.
8. Hậu kiểm và giám sát các yêu cầu bất thường của cùng nhân viên/cùng nhóm tài khoản.

Không nên xem ảnh giấy tờ tùy thân hoặc cuộc gọi video là **bằng chứng tuyệt đối**. Chất lượng tùy thuộc quy trình kiểm tra, tính xác thực, chống giả mạo và yêu cầu bảo vệ dữ liệu cá nhân.

### 5.6. Re-proofing khi không còn đường recovery đủ tin cậy

Nếu không còn authenticator hoặc kênh đã đăng ký đủ tin cậy, hệ thống có thể phải **xác minh lại danh tính** bằng nguồn chứng cứ khác. Quy trình này cần phù hợp với:

- Loại tài khoản: ẩn danh, tài khoản có danh tính đã xác minh, tài khoản nhân viên, tài khoản quản trị.
- Risk tier và các nghĩa vụ hiện hành.
- Bằng chứng/nguồn xác minh được cho phép; mức tin cậy cần đạt.
- Dữ liệu tối thiểu cần thu, cách bảo vệ, thời hạn lưu và quyền xóa.
- Khả năng kháng giả mạo, chống social engineering và cơ chế khiếu nại.
- Phân quyền phê duyệt và yêu cầu độc lập cho trường hợp đặc biệt.

Nếu không thể đạt mức tin cậy cần thiết, có thể phải **giữ tài khoản ở trạng thái hạn chế** và chuyển qua kênh hỗ trợ an toàn hơn. Không nên mặc định nới tiêu chuẩn chỉ để đảm bảo 100% yêu cầu recovery đều thành công.

## 6. Thiết kế một luồng recovery nhiều giai đoạn

Một thiết kế thực dụng thường tách **yêu cầu recovery**, **xác minh chứng cứ**, **cấp khả năng bind hạn chế**, **đăng ký authenticator mới** và **xác minh trạng thái hậu recovery**.

~~~mermaid
flowchart TD
    A["Người dùng yêu cầu recovery"] --> B["Phản hồi không tiết lộ tồn tại account"]
    B --> C["Kiểm tra chống abuse / rủi ro / trạng thái tài khoản"]
    C --> D["Chọn recovery path được policy cho phép"]
    D --> E["Thu và xác minh chứng cứ hoặc approval"]
    E --> F{"Chứng cứ đủ cho mức rủi ro?"}
    F -- "Không" --> X["Từ chối, giới hạn hoặc chuyển assisted review"]
    X --> Y["Audit và cơ chế hỗ trợ/khiếu nại"]
    F -- "Có" --> G["Consume proof một lần"]
    G --> H["Cấp recovery session chỉ có quyền bind"]
    H --> I["Xác minh authenticator mới qua challenge"]
    I --> J{"Binding thành công?"}
    J -- "Không" --> K["Hủy/hết hạn grant, theo dõi và thử lại theo policy"]
    J -- "Có" --> L["Hoàn tất thay đổi, kiểm tra session và factor cũ"]
    L --> M["Thông báo qua kênh phù hợp, audit và giám sát"]
    M --> N["Reassess risk và evidence"]
~~~

**Mọi bước quan trọng phải được kiểm tra tại server**. Trạng thái “đã xác minh” do client gửi lên không có giá trị nếu backend không lưu và kiểm tra bằng chứng.

### 6.1. Giai đoạn A – tiếp nhận yêu cầu

Đầu vào có thể là username, email hoặc mã định danh tài khoản. Không cho phản hồi khác biệt dễ nhận thấy giữa “có tài khoản” và “không tồn tại”.

Ví dụ phản hồi:

> “Nếu thông tin tương ứng với một tài khoản đủ điều kiện, chúng tôi sẽ gửi hướng dẫn khôi phục qua phương thức đã đăng ký.”

Cần lưu ý sự khác biệt **thời gian phản hồi, mã HTTP, nội dung email, kích thước response và ngưỡng giới hạn** có thể tạo enumeration gián tiếp. Không có giải pháp chỉ bằng một câu thông báo; phải kiểm tra cả hành vi kỹ thuật.

### 6.2. Giai đoạn B – risk assessment và chọn recovery path

Có thể dựa vào:

- Loại tài khoản và quyền hiện có.
- Authenticator vẫn còn tin cậy, nếu có.
- Dấu hiệu đăng nhập/đổi recovery contact bất thường.
- Đã có tranh chấp quyền sở hữu hoặc sự cố chưa được giải quyết không.
- Loại tài sản/nghiệp vụ được bảo vệ.
- Khả năng độc lập của kênh recovery.
- Điều kiện của nhà cung cấp danh tính hoặc doanh nghiệp.

Một tài khoản đọc nội dung ít nhạy cảm có thể dùng recovery path khác tài khoản quản trị cloud hoặc tài khoản có quyền thanh toán. **Risk-based branching phải được thiết kế, thử và giám sát**, không chỉ dựa vào cảm tính của helpdesk.

### 6.3. Giai đoạn C – xác minh proof và tạo capability có giới hạn

Khi proof hợp lệ, hệ thống có thể tạo một **recovery-limited session/capability** chỉ dùng để **hoàn tất đăng ký authenticator mới**. Nó không mặc định có quyền:

- Đọc dữ liệu khách hàng.
- Xuất dữ liệu hoặc thực hiện thanh toán.
- Tạo API token hay cấp role quản trị.
- Thay email/số điện thoại recovery không qua rule riêng.
- Xóa các dấu vết bảo mật.

Capability cần **TTL ngắn, scope hẹp, ràng buộc tài khoản, chống replay và chống lạm dụng**. Hãy kiểm tra quyền ở từng endpoint, không phụ thuộc vào việc người dùng chỉ nhìn thấy trang recovery.

### 6.4. Giai đoạn D – binding và xác minh authenticator mới

Thêm authenticator nên diễn ra qua cơ chế **challenge–response** của công nghệ tương ứng.

- Với passkey/WebAuthn: xác minh challenge, origin, RP ID, public key credential, các thuộc tính xác thực và ràng buộc account theo yêu cầu.
- Với TOTP: kiểm tra mã sinh từ secret mới, chống replay theo thiết kế, lưu secret an toàn và hạn chế khả năng đọc.
- Với thiết bị/khóa bảo mật khác: xác nhận sự tham gia thực của authenticator mới trước khi đánh dấu active.

**Không chỉ lưu public key hoặc seed do client gửi rồi tuyên bố đăng ký đã được chứng minh**. Binding cần hoàn thành theo giao thức, ở server, và chống thao tác đăng ký thay người khác.

### 6.5. Giai đoạn E – kết thúc recovery và hậu xử lý

Sau khi hoàn tất:

1. Xác định các **authenticator cũ** phải giữ, thu hồi hoặc đánh dấu nghi compromise.
2. Xác định session/token/OAuth grant nào phải chấm dứt theo tình huống và chính sách; trong incident có thể cần thu hồi rộng.
3. Đánh giá việc quay lại mức quyền bình thường và yêu cầu **step-up** cho thao tác nhạy cảm.
4. Gửi thông báo **không chứa secret** qua kênh phù hợp, bao gồm kênh cũ khi có lý do và khả năng.
5. Cập nhật audit, rủi ro, device inventory và những flag đánh giá.
6. Cho người dùng kênh báo cáo “tôi không thực hiện recovery này”.
7. Đánh giá lại nếu có nhiều recovery liên tiếp hoặc dấu hiệu tấn công.

Thông báo không nên **là yếu tố duy nhất xác nhận recovery hợp lệ**; nó hỗ trợ phát hiện và phản ứng.

## 7. Quy tắc bảo mật cho recovery token, code và session

### 7.1. Token phải đủ khó đoán

Recovery secret phải được tạo bằng **CSPRNG** với entropy phù hợp. Không dùng:

- Mã tuần tự, timestamp, username hoặc email làm token.
- Random có thể dự đoán hoặc mã vài chữ số dùng không có rate limit.
- JWT lâu dài không có kiểm soát mục đích, revoke và replay phù hợp chỉ vì “dễ triển khai”.

Một ví dụ thiết kế dùng **32 byte ngẫu nhiên** (256 bit entropy nguồn) và mã hóa thành token cho người dùng. Token có **purpose, subject, challenge ID, TTL và trạng thái one-time** ở phía server.

### 7.2. Không lưu token dạng plaintext có thể lấy lại

Lưu **bản dẫn xuất có bảo vệ** để so khớp token:

- Với token ngẫu nhiên mạnh, có thể dùng digest được bảo vệ bằng **HMAC với secret phía server**; phải quản trị key và rotation.
- Nếu dùng mã ngắn/entropy thấp, chỉ băm nhanh là không đủ bảo vệ trước dò offline; cần rate limit, lưu trữ và phương pháp bảo vệ phù hợp.
- Không đưa token/code vào application log, analytics, tracing, exception, email template preview hoặc support ticket.

Chỉ băm token không giải quyết trường hợp mailbox bị chiếm. Cần xem **mô hình đe dọa của toàn bộ recovery channel**.

### 7.3. One-time consumption phải nguyên tử

Nếu hai request đồng thời gửi cùng token, chỉ **một request** được phép chuyển nó sang trạng thái consumed. Có thể dùng:

- Transaction với row lock.
- Atomic compare-and-set (CAS) trong database.
- Cập nhật có điều kiện theo trạng thái, expiry, purpose và digest; kiểm tra số bản ghi cập nhật.

Phải test **race condition**, không chỉ gửi từng request theo thứ tự. Trạng thái một lần dùng phải được quản lý phía server, không chỉ ở client.

### 7.4. Giới hạn thử sai và tránh denial of service

Các giới hạn cần phân biệt:

- Theo account hoặc recovery identifier.
- Theo IP/network/device và tín hiệu hành vi.
- Theo challenge và số lần nhập code.
- Theo số lần yêu cầu gửi lại link/code.
- Theo helpdesk case và nhân viên có quyền thực hiện.
- Theo thời gian cooldown và khả năng hỗ trợ người dùng thật.

Rate limit quá gắt có thể bị kẻ tấn công lợi dụng để **khóa người dùng liên tục**. Cần kết hợp phát hiện abuse, cách mở khóa an toàn và bảo vệ tính riêng tư.

### 7.5. Chống rò rỉ token qua URL và browser

Khi gửi magic link, phải xét:

- Log của reverse proxy/CDN và web server.
- Referrer tới tài nguyên bên thứ ba.
- Browser history, clipboard và screenshot.
- Email security scanner tự động mở link.
- Redirect và open redirect.
- Cache hoặc lưu trang recovery chứa secret.
- Analytics/telemetry chạy trên trang recovery.

Hạn chế đưa token vào URL khi có thiết kế phù hợp; nếu URL là cần thiết, dùng TTL ngắn, thực hiện đổi token sang phiên hạn chế một cách an toàn, dọn URL và tránh tải tài nguyên bên thứ ba trước khi secret được xử lý. **Mở link qua GET không nên tự động hoàn tất thay authenticator hoặc chuyển quyền**.

## 8. Ví dụ thực hành Java/Spring Boot: khôi phục MFA cho Orders API

### 8.1. Bối cảnh

Một nền tảng đặt hàng có ứng dụng web và **Orders API** viết bằng **Java/Spring Boot**. Người dùng đã đăng ký MFA, nhưng mất thiết bị chứa authenticator. Hệ thống hỗ trợ recovery code cấp trước để tạo **phiên chỉ được đăng ký authenticator mới**, không cấp ngay quyền đọc đơn hàng hay đổi địa chỉ giao hàng.

**Security claim REC-CLAIM-01:**

> “Một recovery code hợp lệ chỉ có thể được dùng một lần để tạo capability liên kết authenticator mới cho đúng tài khoản; người khác không thể tái sử dụng code, thay accountId hoặc truy cập chức năng nghiệp vụ bằng capability đó.”

**Security claim REC-CLAIM-02:**

> “Authenticator mới phải được kiểm chứng theo giao thức trước khi có hiệu lực; sau recovery phải có audit và xử lý session/authenticator cũ theo chính sách rủi ro.”

### 8.2. Mô hình ranh giới tin cậy

~~~mermaid
flowchart LR
    U["Người dùng / Trình duyệt"] -->|"Yêu cầu recovery"| API["Recovery API - Spring Boot"]
    API --> LIMIT["Abuse / Rate-limit control"]
    API --> DB[("Recovery Challenge Store")]
    API --> POLICY["Recovery Policy / Risk Engine"]
    API --> BIND["Authenticator Binding Service"]
    BIND --> AUTH[("Authenticator Registry")]
    API --> AUDIT[("Protected Audit Store")]
    BIND --> AUDIT
    API -->|"Thông báo không kèm secret"| NOTIFY["Notification Service"]
~~~

Trust boundaries gồm **client → backend**, **backend → recovery store**, **backend → authenticator registry**, **notification channel** và **identity/session service**. Email hoặc user-provided account ID không được tự coi là danh tính đã được xác minh.

### 8.3. State machine của recovery challenge

Một mô hình trạng thái nên tránh việc nhảy trực tiếp từ “nhận yêu cầu” sang “tài khoản hoàn tất recovery”.

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> PROOF_PENDING
    PROOF_PENDING --> PROOF_VERIFIED: Proof hợp lệ, consume một lần
    PROOF_PENDING --> EXPIRED: Quá hạn
    PROOF_PENDING --> REJECTED: Vượt số lần thử hoặc rủi ro
    PROOF_VERIFIED --> BIND_PENDING: Cấp capability giới hạn
    BIND_PENDING --> COMPLETED: Authenticator mới được xác minh
    BIND_PENDING --> EXPIRED: Capability hết hạn
    REQUESTED --> CANCELLED: Hủy hợp lệ
    PROOF_PENDING --> CANCELLED: Hủy hợp lệ
    COMPLETED --> [*]
    REJECTED --> [*]
    EXPIRED --> [*]
    CANCELLED --> [*]
~~~

**PROOF_VERIFIED** không tương đương **AUTHENTICATED_FOR_ALL_PURPOSES**. Capability trong **BIND_PENDING** chỉ được phép vào các endpoint phục vụ binding đã được bảo vệ.

### 8.4. Java code minh họa bảo toàn one-time proof

Giả sử recovery code được phát từ trước với entropy đủ cao và server lưu digest có bảo vệ. Phương thức sau chỉ thể hiện **invariant** của việc consume một lần.

~~~java
@Service
public class RecoveryProofService {
    private final RecoveryProofRepository repository;
    private final RecoverySecretVerifier verifier;
    private final RecoveryCapabilityIssuer capabilityIssuer;
    private final RecoveryAudit audit;

    public RecoveryProofService(
            RecoveryProofRepository repository,
            RecoverySecretVerifier verifier,
            RecoveryCapabilityIssuer capabilityIssuer,
            RecoveryAudit audit) {
        this.repository = repository;
        this.verifier = verifier;
        this.capabilityIssuer = capabilityIssuer;
        this.audit = audit;
    }

    @Transactional
    public RecoveryCapability verifyOneTimeProof(
            UUID challengeId, String submittedCode, Instant now) {

        RecoveryProof proof = repository.findByIdForUpdate(challengeId)
            .orElseThrow(RecoveryDeniedException::new);

        if (!proof.isPending()
                || !proof.expiresAt().isAfter(now)
                || !verifier.matches(submittedCode, proof.protectedDigest())) {
            throw new RecoveryDeniedException();
        }

        // Row lock + transaction: chi mot request consume thanh cong.
        proof.markConsumed(now);

        // Capability nay chi cho phep bat dau bind authenticator moi.
        // Khong phai access token cho Orders API hay tai khoan admin.
        RecoveryCapability capability =
            capabilityIssuer.issueBindingOnly(
                proof.subjectId(), now.plus(Duration.ofMinutes(10)));

        audit.recordProofAccepted(proof.subjectId(), challengeId, now);
        return capability;
    }
}
~~~

**Đây là mã định hướng thiết kế**, không phải module chạy độc lập. Cần triển khai RecoveryProofRepository, RecoverySecretVerifier, RecoveryCapabilityIssuer, RecoveryAudit, RecoveryDeniedException, transaction và persistence mapping; trường hợp lỗi/challenge invalid phải có **generic response, giới hạn thử sai và giám sát** ở tầng được bảo vệ.

Các điểm cần triển khai cẩn thận:

1. **findByIdForUpdate** phải thực sự có locking phù hợp database/transaction isolation. Cần test cạnh tranh với hai request, không suy tính atomic chỉ từ tên hàm.
2. **Verifier** phải bảo vệ secret; đối với code có entropy thấp cần cơ chế bổ sung, không chỉ digest đơn giản.
3. **Logging/Audit** phải bảo đảm không lưu submittedCode. Ghi audit theo transaction/outbox phù hợp để tránh sự kiện success không tương ứng commit hoặc mất audit.
4. Cần ngăn attacker chọn **subjectId** của người khác; subject phải lấy từ challenge đã phát hành và chứng minh đúng.
5. **RecoveryCapability** cần được ràng buộc server-side với scope, account, state, TTL, chống replay và endpoint cho phép. Việc issue không được mặc định tạo một user login session thông thường.
6. Phải xem tình huống **transaction rollback sau khi phát capability**, cache/token phát ngoài DB và lỗi của audit service. Thiết kế thật nên bảo đảm capability không sử dụng được trước khi trạng thái proof đã commit hợp lệ.
7. Logic quản lý **failed attempts** cần lưu bền vững theo cơ chế không bị rollback ngoài ý muốn; không chỉ tăng counter trong transaction rồi throw exception khiến mọi thay đổi bị hủy.
8. Sau này authenticator binding phải xác minh challenge riêng và ghi commit thành công ở registry; không tự active chỉ từ proof.

### 8.5. API và authorization của recovery-limited session

Thiết kế endpoint minh họa:

| Endpoint | Danh tính/quyền yêu cầu | Hành vi phải bảo vệ |
| --- | --- | --- |
| POST /recovery/requests | Không nhất thiết có login session | Generic response, rate limit, chống enumeration |
| POST /recovery/proofs/verify | Challenge + proof hợp lệ theo policy | Verify một lần, giới hạn thử và ghi audit |
| POST /recovery/authenticators/options | Recovery capability **BIND_ONLY** | Sinh binding challenge, ràng buộc account/session |
| POST /recovery/authenticators/complete | BIND_ONLY + binding proof hợp lệ | Đăng ký authenticator mới, consume capability |
| POST /recovery/cancel | Chính sách hủy phù hợp | Thu hồi/cancel challenge và audit |
| GET /api/orders | **Login session bình thường** và quyền dữ liệu | BIND_ONLY không được truy cập nghiệp vụ |
| POST /api/admin/roles | Admin quyền phù hợp, không chỉ BIND_ONLY | Không cấp đặc quyền qua recovery capability |

Đặc biệt, nếu hệ thống dùng JWT cho recovery capability, phải kiểm tra **audience, purpose/scope, issuer, expiry và trạng thái thu hồi** ở backend. Không được để cùng một authentication converter coi capability recovery là access token bình thường chỉ vì nó có claim “sub”.

### 8.6. Test cases cho Orders API

| Test case | Kết quả kỳ vọng | Điều chứng minh |
| --- | --- | --- |
| Recovery request cho email không tồn tại | Phản hồi công khai không tiết lộ tồn tại account | Chống enumeration ở response |
| Recovery request liên tiếp | Giới hạn theo policy, không làm lộ dữ liệu | Abuse control |
| Code sai hoặc hết hạn | Từ chối, không phát BIND_ONLY | Proof validation |
| Code đúng cho tài khoản A | Capability gắn A, không phải B | Account binding |
| Hai request dùng cùng code gần đồng thời | **Đúng một** request consume thành công | Replay/race protection |
| Code dùng lại sau thành công | Từ chối | One-time enforcement |
| BIND_ONLY gọi GET /api/orders | Từ chối truy cập nghiệp vụ | Least privilege của recovery session |
| BIND_ONLY gọi thao tác đổi role | Từ chối | Ngăn escalation |
| BIND_ONLY cố bind cho tài khoản B | Từ chối | Cross-account binding |
| Binding challenge bị giả mạo/replay | Từ chối | Authenticator binding integrity |
| Capability hết hạn trước binding | Từ chối, không active authenticator | TTL enforcement |
| Recovery hoàn tất thành công | Authenticator mới được verify; audit có sự kiện | Workflow integrity |
| Session/token cũ theo nhánh compromise | Bị thu hồi hoặc xử lý đúng policy | Post-recovery security |
| Notification thất bại | Không tạo trạng thái recovery không nhất quán; có retry/giám sát phù hợp | Failure handling |
| Helpdesk override trái quyền | Từ chối và audit | Governance/SoD |

Các ca cần chạy trên **phiên bản và cấu hình liên quan**, có test dương lẫn âm. Kết quả từ MockMvc chỉ đánh giá đường thử được cấu hình; không tự chứng minh hệ thống email, IdP, WebAuthn, cơ chế thu hồi token hay production hoàn toàn đúng.

## 9. Helpdesk recovery và quyền phê duyệt

Assisted recovery cần xem như một **privileged operation**, vì nhân viên hỗ trợ có thể gián tiếp đổi ai kiểm soát một tài khoản.

| Vai trò | Trách nhiệm | Giới hạn |
| --- | --- | --- |
| **Người dùng/chủ tài khoản** | Cung cấp chứng cứ theo kênh bảo mật, báo nghi chiếm quyền | Không chia sẻ password hoặc recovery secret cho nhân viên |
| **Support agent** | Tiếp nhận case, hướng dẫn quy trình, ghi trạng thái | Không tự vượt policy hoặc tự tạo authenticator thay người dùng |
| **Recovery approver** | Phê duyệt trường hợp có điều kiện hoặc rủi ro cao | Phải có thẩm quyền và độc lập khi SoD được yêu cầu |
| **Identity/IAM owner** | Thiết kế policy, identity proofing, binding, session và revoke | Không tự động có quyền chấp nhận residual risk của mọi hệ thống |
| **Application/control owner** | Bảo đảm ứng dụng không có đường recovery bypass | Không mặc định tin mọi claim từ client/helpdesk |
| **Risk owner** | Quyết định xử lý/chấp nhận rủi ro trong thẩm quyền | Không thay thế đánh giá kỹ thuật về tính xác thực của proof |
| **Security assurance/auditor** | Xem chất lượng bằng chứng và phát hiện trong scope | Giữ độc lập phù hợp với mức rủi ro |

### 9.1. Những control cần có cho helpdesk

- **Least privilege:** nhân viên không thể tự đổi mọi authenticator của mọi khách hàng không có case hợp lệ.
- **Step-up cho support:** yêu cầu xác thực mạnh và quyền tạm thời đối với thao tác nhạy cảm.
- **Separation of duties:** yêu cầu review chéo cho tài khoản đặc quyền hoặc trường hợp có dấu hiệu gian lận.
- **Case binding:** thao tác gắn với ticket, subject, scope, lý do và bằng chứng đã kiểm tra.
- **No secret exposure:** support không đọc recovery code hoặc token mà người dùng cần giữ kín.
- **Audit:** ghi actor, approver, action, subject, time, outcome và reason, tránh lưu giấy tờ/secret không cần thiết.
- **Exception governance:** không tự gọi bypass là “ngoại lệ thường xuyên”; phải có giới hạn và phê duyệt.
- **Monitoring:** phát hiện một support agent reset quá nhiều tài khoản, nhiều lần thất bại hoặc bất thường theo giờ/địa điểm.

### 9.2. Khi có tranh chấp quyền sở hữu tài khoản

Nếu hai bên đều nhận mình là chủ tài khoản, hoặc tồn tại dấu hiệu compromise, **không nên đơn giản phục hồi cho người liên hệ gần nhất**. Cần:

1. Hạn chế hành động nhạy cảm nếu phù hợp.
2. Bảo toàn audit và bằng chứng tranh chấp.
3. Kích hoạt quy trình xác minh/phê duyệt có kiểm soát.
4. Không tiết lộ dữ liệu tài khoản cho một bên khi chưa xác minh quyền.
5. Thông báo và xử lý theo quy định, đồng thời hỗ trợ khiếu nại.
6. Ghi quyết định, thẩm quyền, điều kiện và cách xem lại.

## 10. Recovery sau khi nghi ngờ tài khoản đã bị chiếm

**Compromised-account recovery** không giống “quên mật khẩu”. Nguy cơ chính là kẻ tấn công có thể **còn giữ các đường truy cập khác** dù người dùng đã đổi một authenticator.

Quy trình cần cân nhắc:

- **Cô lập truy cập đáng ngờ:** revoke session/token, khóa các token/credential bị nghi compromise, giới hạn thao tác theo policy.
- **Xem các yếu tố được đăng ký:** attacker đã thêm MFA, passkey, thiết bị tin cậy hay recovery contact mới?
- **Kiểm tra ủy quyền bên thứ ba:** OAuth consent/grant, app password, API keys, delegation và session khác.
- **Tái xác minh chủ tài khoản:** không dùng chính kênh/thiết bị bị nghi đã chiếm làm bằng chứng duy nhất.
- **Bind authenticator sạch:** xác minh authenticator mới và điều kiện quyền sử dụng.
- **Thu hồi thông tin/thiết bị đáng ngờ:** xác định phần nào phải xóa, block hoặc cảnh báo.
- **Xem dữ liệu bị ảnh hưởng:** kiểm tra hoạt động thay đổi email, thanh toán, role, export, nội dung và nhu cầu ứng cứu/tuân thủ.
- **Giám sát sau khôi phục:** phát hiện đăng nhập bất thường, lặp recovery hoặc tái chiếm.

Một trường hợp có thể cần **incident response** thay vì chỉ một ticket hỗ trợ. Khi có dấu hiệu dữ liệu nhạy cảm bị lộ, nhóm phải phối hợp các chủ thể có trách nhiệm và các nghĩa vụ thông báo thực sự áp dụng.

## 11. Tài khoản đặc quyền, doanh nghiệp và federated identity

### 11.1. Recovery tài khoản quản trị

Đối với tài khoản có thể sửa IAM, cloud, database, artifact hoặc thanh toán lớn, recovery cần bảo vệ trước:

- Social engineering helpdesk.
- Giả mạo người phê duyệt.
- Thêm authenticator rồi chiếm quyền ngay.
- Downgrade phương thức chống phishing.
- Grant đặc quyền tồn tại sau nghi compromise.
- Audit bị người khôi phục sửa/xóa.

Có thể đòi hỏi **proof mạnh hơn, người phê duyệt độc lập, recovery-limited state, thời gian chờ hoặc kiểm tra bổ sung** theo mức rủi ro. Không đưa một khoảng thời gian chờ tùy ý thành quy tắc toàn cầu; policy phải giải thích mục tiêu và trường hợp khẩn cấp.

### 11.2. Identity recovery ở doanh nghiệp và SSO

Khi ứng dụng dựa vào **Identity Provider (IdP)**:

- Recovery của **identity chính** nên được xử lý ở nơi có thẩm quyền quản lý danh tính.
- Relying application không nên tự mở một **đường password fallback** yếu chỉ dựa vào email.
- Ứng dụng cần kiểm tra claim, session và ngữ cảnh xác thực phù hợp với các hành động nhạy cảm.
- Recovery tại IdP có thể làm thay đổi authentication context; relying party cần biết **khi nào phải reauthenticate/step-up** theo khả năng giao thức và policy.
- Nên dùng định danh liên kết ổn định, không chỉ ghép tài khoản theo email trùng mà không xác minh.

**Thông báo IdP recovery thành công không tự chứng minh** mọi session ở ứng dụng đã được thu hồi. Phải xem kiến trúc token/session thực tế.

### 11.3. Break-glass khác account recovery

**Break-glass** là đường truy cập khẩn cấp để khôi phục khả năng quản trị khi cơ chế thông thường bị sự cố, có **kiểm soát, cảnh báo và hậu kiểm riêng**. **Account recovery** nhằm trả quyền kiểm soát tài khoản cho đúng chủ thể.

Không dùng break-glass thành phương thức mặc định để nhân viên lấy lại tài khoản. Ngược lại, không yêu cầu một quy trình recovery chậm xử lý thay cho phương án incident response đã phê duyệt khi hệ thống gặp sự cố nghiêm trọng.

### 11.4. Workload identity recovery

Khi service account hoặc machine credential bị mất/compromise:

1. Xác định hệ thống, chủ sở hữu, phạm vi permission và blast radius.
2. Tạo identity/credential mới qua cơ chế cấp phát tin cậy.
3. Cập nhật phụ thuộc một cách có kiểm soát và kiểm thử dịch vụ.
4. Thu hồi khóa/token/certificate cũ khi an toàn, phối hợp chuyển tiếp để tránh ngừng dịch vụ không cần thiết.
5. Kiểm tra IAM scope, deployment artifacts và giám sát hành vi.
6. Lưu bằng chứng rotation/revoke, không ghi secret nguyên bản trong ticket.
7. Khi nghi compromise, điều tra việc credential đã được dùng ở đâu và xử lý rủi ro còn lại.

Machine recovery không nên được thực hiện bằng cách gửi plaintext secret vào email hoặc chat nhóm.

## 12. Assurance: làm sao chứng minh recovery control hiệu quả?

### 12.1. Ba lớp đánh giá

| Lớp | Câu hỏi | Bằng chứng có thể sử dụng |
| --- | --- | --- |
| **Design effectiveness** | Recovery path có chống account takeover và đủ mạnh cho risk tier? | Threat model, recovery policy, proofing/risk design, state machine, failure-mode review |
| **Implementation effectiveness** | Token, session scope, retry, binding, approval và revoke được thực thi đúng? | Code/config review, integration tests, IAM settings, architecture evidence |
| **Operating effectiveness** | Quy trình thực tế có xác minh, thu hồi, audit và xử lý ngoại lệ đúng trong kỳ? | Helpdesk cases, access/change logs, rebind events, review kết quả, incident records |

Có recovery policy được ký **không chứng minh** hệ thống thực thi policy. Ngược lại, một integration test đạt trong môi trường thử nghiệm **không tự chứng minh** trạng thái production và những đường assisted recovery cũng đạt.

### 12.2. Security claims nên đo được

| Security claim | Control cần có | Bằng chứng tối thiểu |
| --- | --- | --- |
| Không thể đoán/đọc lại recovery secret từ dữ liệu lưu trữ | CSPRNG, protected digest, secret storage | Design review, kiểm tra triển khai và thử truy xuất DB |
| Code/token chỉ dùng một lần | Atomic consumption, state transition | Concurrency test và replay test |
| Challenge hết hạn đúng | TTL và server validation | Fake clock/time-bound test |
| Không dùng BIND_ONLY truy cập tài nguyên nghiệp vụ | Scope/audience checks | Negative authorization tests |
| Rebinding đúng chủ tài khoản | Subject binding, authenticator challenge | Cross-account test, WebAuthn/TOTP verification test |
| Không bypass chính sách qua helpdesk | SoD, approval và least privilege | Case sampling, audit và role tests |
| Recovery có thể được kiểm tra sau sự kiện | Protected audit trail và correlation | Log structure, integrity/access review |
| Compromise không duy trì access trái quyền | Revoke theo policy, rà session/factor/grant | Test hậu recovery, incident drill |
| Không enumeration tài khoản | Generic response, timing/abuse review | API behavior test, rate limit verification |
| Đảm bảo chủ thể hợp lệ có đường hỗ trợ phù hợp | Backup path/re-proofing được phê duyệt | UX/operational test, case process review |

### 12.3. Đánh giá bằng chứng và phạm vi

Bằng chứng phải:

- **Liên quan (relevant):** đúng security claim và threat.
- **Có nguồn gốc:** ai/công cụ nào tạo, thời điểm và cách kiểm tra.
- **Đúng phiên bản:** build, cấu hình, recovery policy và standard edition phù hợp.
- **Đúng môi trường:** staging không tự đại diện production.
- **Bao phủ hợp lý:** cả đường thành công, thất bại, replay, race, support override, session revoke và account compromise theo rủi ro.
- **Có thể tái kiểm chứng:** lưu test run, case reference, kết quả và phương pháp.
- **Được bảo vệ:** không lộ recovery token, PII, giấy tờ hoặc thông tin hỗ trợ dễ bị lạm dụng.
- **Có review độc lập khi cần:** nhất là tài khoản có đặc quyền lớn.

Nếu chỉ có test password reset qua email mà không kiểm tra helpdesk hay backup code, không được kết luận **toàn bộ Identity recovery hiệu quả**.

### 12.4. Trạng thái kết luận

- **Effective in assessed scope:** bằng chứng đủ cho các tiêu chí và đường recovery đã kiểm tra.
- **Partially effective:** một số luồng đạt, còn thiếu hoặc có sai lệch ở đường khác.
- **Ineffective:** có bằng chứng control không đạt claim quan trọng.
- **Insufficient evidence:** chưa đủ cơ sở kết luận.
- **Exception approved:** có quyết định ngoại lệ hợp lệ và residual risk; không tự biến thành “đạt”.
- **Not applicable:** có căn cứ được phê duyệt yêu cầu không áp dụng.

**Không có sự cố account takeover trong log không chứng minh recovery an toàn**, nhất là khi detection có thể chưa bao phủ toàn bộ hành vi.

## 13. Mẫu hồ sơ đánh giá recovery

Mẫu YAML sau là **dữ liệu minh họa**, chưa có kết quả kiểm thử thực:

~~~yaml
assessment_id: "IDENTITY-RECOVERY-DEMO-009"
service: "orders-api"
control_id: "CTRL-IDENTITY-RECOVERY-01"
policy_ref: "POL-IDENTITY-ASSURANCE"
standard_ref:
  id: "STD-ACCOUNT-RECOVERY"
  version: "demo-1.0"
risk_owner: "Orders Product Owner"
control_owner: "Identity Platform Owner"
scope:
  account_type: "customer"
  recovery_paths:
    - "preissued recovery code"
    - "assisted recovery"
  environments:
    - "integration"
  build: "demo-build-not-yet-verified"
security_claims:
  - id: "REC-01"
    requirement: "Recovery proof one-time and expires"
  - id: "REC-02"
    requirement: "Recovery capability limited to binding"
  - id: "REC-03"
    requirement: "Authenticator binding verifies challenge"
  - id: "REC-04"
    requirement: "Revocation and audit after recovery"
evidence_plan:
  - "Atomic replay/concurrency tests"
  - "Negative tests for cross-account capability"
  - "Binding challenge verification"
  - "Helpdesk approval and SoD review"
  - "Session and authenticator revocation checks"
evidence_refs: []
design_review: "PENDING"
implementation_review: "NOT_VERIFIED"
operating_review: "NOT_VERIFIED"
assurance_conclusion: "INSUFFICIENT_EVIDENCE"
confidence: "LOW"
findings: []
next_action: "Run recovery security tests and attach evidence"
exception:
  approved: false
  approver: null
~~~

Trong dự án thật, thêm **assessed_at, owner, reviewer, build ID, test run ID, môi trường, phạm vi dữ liệu, giới hạn, quyết định rủi ro, thời hạn và đường dẫn evidence được bảo vệ**. Không nên đưa recovery code hoặc giấy tờ người dùng thật vào hồ sơ kiểm toán thông thường.

## 14. Giám sát recovery bằng KPI/KRI

| Chỉ số | Tín hiệu quản trị | Hạn chế cần nhớ |
| --- | --- | --- |
| **Legitimate recovery completion** | Khả năng người dùng hợp lệ phục hồi qua những đường được phép | Tỷ lệ cao không tự chứng minh an toàn |
| **Time to recover by risk tier** | Độ trễ người dùng hợp lệ gặp phải | Giảm thời gian không được đánh đổi bằng bypass |
| **Suspicious recovery attempts** | Phát hiện yêu cầu bất thường, lặp lại, cross-account | Phụ thuộc chất lượng detection |
| **Token replay rejection** | Test/giám sát code đã dùng không được dùng lại | Production có thể có biến thể race cần đánh giá riêng |
| **Expired proof/capability rejection** | Độ hiệu quả kiểm soát TTL | Cần kiểm tra clock skew, cache và môi trường |
| **Recovery-limited scope enforcement** | Capability không truy cập chức năng khác | Đếm test có mẫu số đúng |
| **Factor rebind audit coverage** | Số lần rebind có audit event hợp lệ trên tổng số lần | Log đầy đủ chưa chứng minh đúng chủ thể |
| **Session/revocation verification** | Khả năng chấm dứt quyền đáng ngờ sau recovery | Cần phân loại nhánh quên yếu tố và compromise |
| **Helpdesk assisted recovery exceptions** | Khối lượng và tuổi ngoại lệ rủi ro cao | Phải đánh giá từng trường hợp, không chỉ số lượng |
| **False denial / support burden** | Người dùng hợp lệ bị từ chối không phù hợp | Cần cơ chế khiếu nại không gây lộ dữ liệu |
| **Repeated recovery and takeover signals** | Nguy cơ tái chiếm, recovery abuse | Phân biệt nhu cầu hợp lệ và tấn công |

Ví dụ giả định: 100 lần kiểm thử token recovery, có 98 lần PASS và 2 lần cho phép dùng lại token sau consume. Không nên kết luận “hiệu quả 98%” nếu **hai lỗi replay** có thể dẫn đến chiếm tài khoản; phải ghi finding nghiêm trọng theo ảnh hưởng và khắc phục.

Một con số khác: 30 kịch bản recovery cần kiểm tra, mới có bằng chứng hợp lệ cho 20. **Coverage 20/30 = 66,7%** chỉ mô tả độ bao phủ của kiểm chứng, **không có nghĩa hệ thống an toàn 66,7%**.

## 15. Phân công trách nhiệm và quyết định rủi ro

| Vai trò | Trách nhiệm | Điểm cần phân biệt |
| --- | --- | --- |
| **Identity policy owner** | Xác định recovery requirements, risk tier và đường được phép | Không tự tuyên bố hệ thống vận hành đạt |
| **Identity/IAM control owner** | Thiết kế và duy trì proof, grant, authenticator binding, revoke | Phải cung cấp bằng chứng về control thực tế |
| **Application owner** | Không cho recovery token bypass business authorization | Chịu trách nhiệm những integration paths của ứng dụng |
| **Support/helpdesk owner** | Đào tạo, quy trình assisted recovery, kiểm soát tác nhân hỗ trợ | Không được tùy ý bỏ qua proofing/approval |
| **Security analyst/incident response** | Phát hiện gian lận, xử lý compromise, bảo toàn bằng chứng | Phối hợp nhưng không thay quyền risk owner |
| **Risk owner** | Quyết định xử lý/chấp nhận residual risk trong thẩm quyền | Không thay thế kiểm chứng kỹ thuật |
| **Assurance reviewer/auditor** | Đánh giá mức đủ và độc lập của bằng chứng, kết luận phạm vi | Không tự động là người khắc phục control |
| **Privacy/compliance** | Rà soát dữ liệu định danh/giấy tờ, nghĩa vụ áp dụng | Không mặc định một giải pháp kỹ thuật là hợp lệ ở mọi phạm vi |

Một sơ đồ **RACI** minh họa:

| Hoạt động | Identity owner | App owner | Helpdesk | Risk owner | Assurance reviewer |
| --- | --- | --- | --- | --- | --- |
| Thiết kế recovery policy/control | **A/R** | C | C | C | C |
| Enforce BIND_ONLY trong ứng dụng | C | **A/R** | I | I | C |
| Assisted recovery theo workflow | C | I | **A/R** | C | C |
| Kiểm tra evidence và kết luận độc lập | C | C | C | I | **A/R** |
| Khắc phục gap identity platform | **A/R** | C | C | C | C |
| Quyết định residual risk thuộc quyền risk owner | C | C | C | **A/R** | I |

RACI cần điều chỉnh theo tổ chức; nếu cùng một người vừa phê duyệt assisted recovery vừa đánh giá chính mình, phải xem yêu cầu độc lập theo rủi ro.

## 16. Các sai lầm phổ biến

### 16.1. Biến recovery thành đường đăng nhập yếu hơn

**Sai:** tài khoản bắt buộc authenticator mạnh nhưng có thể thay MFA chỉ bằng thông tin cá nhân công khai.

**Đúng:** đánh giá từng recovery path theo rủi ro, yêu cầu chứng cứ phù hợp, giới hạn quyền trước khi bind và giám sát thay đổi.

### 16.2. Coi email OTP là bằng chứng danh tính tuyệt đối

Mailbox có thể bị chiếm; email không tự chứng minh chủ tài khoản pháp lý hay quyền trên tenant. **Cần** đánh giá độ tin cậy và kênh độc lập theo rủi ro.

### 16.3. Cho helpdesk toàn quyền đổi authenticator

Dễ bị social engineering, insider abuse và thiếu trách nhiệm giải trình. **Cần** least privilege, case binding, SoD, approval và audit.

### 16.4. Gửi token mã hóa yếu hoặc không giới hạn thử sai

Dễ dò, replay và abuse. **Cần** entropy đủ, TTL, one-time, rate limiting, bảo vệ lưu trữ và thiết kế chống race.

### 16.5. Mở GET link là hoàn tất recovery

Link scanner hoặc browser preview có thể kích hoạt ngoài ý muốn. **Cần** tách hiển thị/xác minh và thao tác nhạy cảm; không dùng GET để bind authenticator.

### 16.6. Recovery capability được coi là access token thường

Một claim subject có thể làm hệ thống cấp full user permissions. **Cần** purpose/audience/scope riêng, kiểm tra server-side và negative authorization test.

### 16.7. Đổi mật khẩu xong nhưng bỏ lại phiên đã bị chiếm

Kẻ tấn công vẫn có session/OAuth grant hoặc authenticator mới tự đăng ký. **Cần** quy trình compromised-account recovery, review sessions/factors và revoke phù hợp.

### 16.8. Đọc hoặc lưu recovery code trong ticket/log

Tạo nguồn lộ secret khác. **Cần** che và bảo vệ token, tách audit metadata khỏi thông tin bí mật.

### 16.9. Chỉ kiểm thử đường thành công

Không đánh giá replay, race, wrong account, expired token, helpdesk override, denied flow, browser scanner hoặc revoke. **Cần** test ma trận theo threat.

### 16.10. Khóa mọi người dùng khi có request lạ

Kẻ tấn công có thể lặp request để gây DoS. **Cần** abuse protection có cân bằng usability và lộ trình hỗ trợ người dùng thật.

### 16.11. Thấy không có alert thì kết luận an toàn

Rule có thể chưa đủ hoặc thiếu log. **Cần** mô phỏng detection và kiểm tra event routing, phản ứng theo kịch bản.

### 16.12. Dùng kết quả cũ cho luồng mới

Sau khi thêm passkey, thay IdP, bổ sung support tool hoặc email provider, trust boundary thay đổi. **Cần** re-review design và retest đúng phiên bản.

## 17. Checklist thiết kế và đánh giá Identity recovery

- [ ] Xác định loại tài khoản và mức rủi ro, bao gồm customer, staff, admin và workload.
- [ ] Phân biệt rõ quên mật khẩu, mất authenticator, compromise và federated recovery.
- [ ] Có **recovery policy**, phạm vi, điều kiện, thẩm quyền và phiên bản.
- [ ] Mỗi recovery path có threat model và security claims có thể kiểm chứng.
- [ ] Không coi thông tin cá nhân công khai là yếu tố chứng minh quyền kiểm soát.
- [ ] Có backup authenticator/code hoặc đường thay thế phù hợp khi người dùng mất thiết bị.
- [ ] Token/code có entropy và cơ chế lưu trữ phù hợp, giới hạn thử sai, TTL và one-time.
- [ ] Việc consume recovery proof được kiểm chứng **nguyên tử**, chống replay và race.
- [ ] Recovery request không tạo account enumeration dễ khai thác.
- [ ] Client không thể tự chọn subject hoặc đánh dấu mình đã vượt qua proof.
- [ ] Có **recovery-limited capability** với account binding, purpose và scope hẹp.
- [ ] BIND_ONLY không gọi được API nghiệp vụ hoặc cấp quyền đặc biệt.
- [ ] Authenticator mới được xác minh qua giao thức/challenge trước khi active.
- [ ] Session, token, OAuth grant và authenticator cũ được xử lý theo loại recovery.
- [ ] Có thông báo phù hợp, cơ chế báo thay đổi trái phép và hậu kiểm.
- [ ] Helpdesk có least privilege, approval/SoD và case audit.
- [ ] Với trường hợp không đủ bằng chứng, có đường chuyển cấp/hỗ trợ, không tự fail-open.
- [ ] Các hệ thống SSO không có đường login fallback ngoài policy.
- [ ] Recovery account quản trị có bảo vệ tương xứng với blast radius.
- [ ] Evidence không chứa recovery secret hoặc giấy tờ/PII không cần thiết.
- [ ] Kiểm thử bao gồm replay, race, wrong account, TTL, CSRF/browser preview và failure modes.
- [ ] Kết luận assurance ghi phạm vi, environment, build, policy revision và giới hạn.
- [ ] Findings có owner, thời hạn, tiêu chí retest và residual risk decision theo quyền.
- [ ] Có trigger đánh giá lại khi thay authenticator, IdP, support workflow hoặc có incident.

Checklist là công cụ tổ chức công việc; bản thân việc đánh dấu đủ ô **không phải bằng chứng** rằng mọi đường recovery đang an toàn.

## 18. Câu hỏi tự kiểm tra

1. Identity recovery khác password reset và identity proofing ở đâu?
2. Vì sao recovery channel có thể là điểm yếu nhất của một cơ chế đăng nhập MFA mạnh?
3. Khi người dùng mất TOTP nhưng còn passkey đã đăng ký, có cần re-proofing bằng giấy tờ không? Cần dựa vào những điều kiện gì?
4. AAL, IAL và FAL mô tả những khía cạnh nào; recovery có liên quan như thế nào?
5. Vì sao nhiều bước qua cùng email/số điện thoại chưa chắc tạo ra bằng chứng độc lập?
6. Một recovery code đã dùng một lần còn dùng được khi hai request gửi đồng thời không? Cần cơ chế nào để bảo vệ?
7. Vì sao một recovery capability chỉ nên có quyền BIND_ONLY, không dùng để truy cập Orders API?
8. Khi bind passkey mới, phía server cần kiểm chứng những thành phần nào theo giao thức?
9. Nếu có dấu hiệu tài khoản bị chiếm, vì sao chỉ đổi mật khẩu có thể chưa đủ?
10. Tại sao helpdesk được xem là một đường privileged access?
11. Trả lời “tài khoản không tồn tại” ở endpoint recovery gây rủi ro gì? Ngoài body response còn kênh nào có thể làm lộ?
12. Việc gửi token trong URL có những nguy cơ từ email scanner, Referrer, history và logs nào?
13. Trong ví dụ Spring Boot, tại sao consume proof phải nguyên tử và việc phát capability phải tính tới transaction commit?
14. Nếu notification service lỗi trong lúc hoàn tất recovery, hệ thống cần bảo vệ những invariant nào?
15. Một kết quả integration test ở staging có đủ để tuyên bố production recovery đạt không?
16. Khi mất mọi authenticator và không còn phương thức đáng tin, tổ chức nên dựa vào điều gì để quyết định recovery?
17. Tài khoản admin, khách hàng thông thường và machine identity có nên dùng cùng workflow recovery không? Vì sao?
18. Hãy viết security claim và 3 negative tests cho trường hợp email recovery bị chiếm.
19. Vì sao ngoại lệ được phê duyệt không tự đồng nghĩa control recovery hiệu quả?
20. Những thay đổi nào cần kích hoạt đánh giá lại identity recovery ngoài lịch định kỳ?

## 19. Tổng kết

**Identity recovery** là quá trình **khôi phục quyền kiểm soát danh tính số cho đúng chủ thể mà không mở ra đường chiếm tài khoản yếu hơn**. Thiết kế tốt cần phân biệt các tình huống mất mật khẩu, mất authenticator, account compromise, doanh nghiệp SSO và workload; lựa chọn recovery proof tương xứng với rủi ro; giới hạn token, thời hạn, quyền và số lần sử dụng; xác minh authenticator mới trước khi kích hoạt; xử lý session và credential cũ; bảo vệ helpdesk, audit và kênh phản ứng. Trong **SECURITY_SECURITY_ASSURANCE**, giá trị của quy trình chỉ được khẳng định khi có **security claim, negative tests, evidence về thiết kế–triển khai–vận hành và retest sau phát hiện**, với kết luận nêu đúng phạm vi và residual risk. Khôi phục tốt không chỉ giúp người dùng quay lại đăng nhập, mà còn bảo vệ toàn bộ niềm tin đã xây dựng quanh danh tính và quyền truy cập của họ.
