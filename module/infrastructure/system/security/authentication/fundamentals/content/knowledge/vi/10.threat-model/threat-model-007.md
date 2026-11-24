# Kịch bản chiếm tài khoản

> **Chương:** Threat model  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS — tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Người học biết mô hình hóa ranh giới tin cậy, phòng chống phishing, replay, lạm dụng đăng nhập và thiết kế luồng xác thực an toàn.
>
> **Mục tiêu của bài:** Mô hình hóa một kịch bản **chiếm tài khoản (Account Takeover — ATO)** từ góc nhìn phòng thủ: xác định tài sản, chủ thể, điểm vào, ranh giới tin cậy, chuỗi tấn công, biện pháp giảm thiểu, tín hiệu phát hiện và cách ứng phó.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích chiếm tài khoản là gì và phân biệt chiếm tài khoản với việc chỉ thử đăng nhập thất bại hoặc truy cập một tài nguyên trái phép.
2. Xác định tài sản cần bảo vệ, tác nhân, bề mặt tấn công và ranh giới tin cậy của một hệ thống xác thực.
3. Mô tả chuỗi tấn công điển hình từ lộ credential đến vượt qua hoặc lợi dụng MFA, chiếm phiên, duy trì truy cập và lạm dụng quyền.
4. Phân tích các con đường như credential stuffing, phishing, MFA fatigue, SIM swap, đánh cắp cookie/token, lạm dụng khôi phục và liên kết danh tính.
5. Chuyển kịch bản thành yêu cầu bảo mật có thể kiểm thử ở các giai đoạn đăng ký, đăng nhập, quản lý phiên, khôi phục và phân quyền.
6. Xây dựng tín hiệu phát hiện và quy trình ứng phó nhằm hạn chế thiệt hại mà vẫn giảm khóa nhầm người dùng hợp lệ.

## 1. Chiếm tài khoản là gì?

**Chiếm tài khoản (Account Takeover — ATO)** xảy ra khi một người hoặc hệ thống không được phép giành được khả năng sử dụng tài khoản của chủ thể hợp lệ, thường bằng cách lấy credential, vượt qua quy trình xác thực, chiếm phiên đã đăng nhập hoặc lợi dụng quy trình khôi phục/liên kết danh tính.

Khi chiếm được tài khoản, kẻ tấn công có thể:

- Đọc thông tin cá nhân, hồ sơ, lịch sử giao dịch hoặc dữ liệu riêng tư.
- Gửi tin nhắn, thay đổi thông tin hồ sơ, lừa người khác bằng danh tính của nạn nhân.
- Thay email/số điện thoại khôi phục, thêm authenticator mới hoặc đổi mật khẩu để khóa chủ tài khoản.
- Sử dụng quyền đã có để truy cập tài nguyên, thực hiện giao dịch hoặc tạo thêm tài khoản/credential.
- Dùng phiên bị chiếm làm điểm tựa để tấn công tài khoản khác hoặc hệ thống liên kết.

ATO là **kết quả về quyền kiểm soát tài khoản**, không phải tên của một kỹ thuật duy nhất. Có nhiều đường dẫn dẫn tới cùng kết quả: mật khẩu bị tái sử dụng, phishing, SIM swap, lạm dụng MFA, malware đánh cắp phiên, khôi phục yếu hoặc hỗ trợ khách hàng bị social engineering.

Cần phân biệt ba tình huống:

| Tình huống | Điều đã xảy ra | Đã phải ATO chưa? |
| --- | --- | --- |
| Bot thử nhiều mật khẩu nhưng tất cả đều bị từ chối | Có hành vi dò hoặc lạm dụng đăng nhập. | Chưa có bằng chứng tài khoản đã bị chiếm. |
| Kẻ tấn công xem được một tài nguyên do lỗi phân quyền nhưng không kiểm soát tài khoản | Có thể là truy cập trái phép/IDOR/BOLA. | Không nhất thiết là ATO; cần phân loại sự cố theo quyền thực tế bị chiếm. |
| Kẻ tấn công đăng nhập được bằng credential bị lộ, dùng phiên và thay phương thức khôi phục | Đã giành quyền sử dụng tài khoản. | Đây là ATO. |

Trong thực tế, một sự cố có thể vừa là ATO vừa bao gồm lộ dữ liệu hoặc gian lận. Mô hình đe dọa cần ghi rõ **tài khoản nào, quyền nào, dữ liệu nào và hậu quả nào** bị ảnh hưởng.

## 2. Xác định phạm vi và tài sản cần bảo vệ

Xét một nền tảng học tập có người học, giảng viên và quản trị viên. Người dùng đăng nhập bằng mật khẩu, TOTP hoặc passkey; một số trường dùng SSO; ứng dụng cấp cookie phiên và có chức năng khôi phục tài khoản.

### 2.1 Tài sản

| Tài sản | Giá trị đối với người dùng/hệ thống | Hậu quả nếu bị chiếm hoặc lộ |
| --- | --- | --- |
| **Danh tính và hồ sơ tài khoản** | Liên kết người dùng với hồ sơ và hoạt động. | Mạo danh, thay đổi thông tin, mất quyền kiểm soát. |
| **Mật khẩu và bí mật xác thực** | Chứng minh quyền sử dụng tài khoản. | Đăng nhập trái phép, credential stuffing, chiếm nhiều dịch vụ nếu tái sử dụng. |
| **Authenticator và khóa** | Tạo bằng chứng xác thực như TOTP/passkey/chứng chỉ. | Đăng nhập bền vững, vượt qua chính sách MFA hoặc giả mạo dịch vụ. |
| **Cookie phiên và token** | Duy trì quyền truy cập sau đăng nhập. | Kẻ giữ bearer token có thể sử dụng quyền trong phạm vi còn hiệu lực. |
| **Email/số điện thoại khôi phục** | Hỗ trợ đặt lại credential và nhận cảnh báo. | Đường vòng qua MFA, thay đổi credential hoặc chặn chủ tài khoản. |
| **Liên kết IdP/SSO** | Kết nối danh tính bên ngoài với tài khoản nội bộ. | Gộp sai tài khoản, đăng nhập nhầm chủ thể hoặc lạm dụng trust relationship. |
| **Dữ liệu và nghiệp vụ** | Hồ sơ, điểm số, thanh toán, thông tin riêng tư. | Lộ dữ liệu, gian lận, sửa/xóa dữ liệu hoặc gây gián đoạn. |
| **Vai trò và quyền đặc biệt** | Quyền giảng viên, quản trị viên, hỗ trợ khách hàng. | Leo thang đặc quyền và mở rộng phạm vi thiệt hại. |
| **Nhật ký và bằng chứng điều tra** | Phát hiện, phân loại và truy vết sự cố. | Không phát hiện được, mất khả năng xác định phạm vi hoặc đối soát. |

Không chỉ mật khẩu mới là tài sản nhạy cảm. **Session cookie, refresh token, mã khôi phục, khóa riêng và quyền thay authenticator** đều có thể trao quyền truy cập. Khi lập mô hình, cần tính cả những dữ liệu mà kẻ tấn công có thể sử dụng để duy trì quyền sau lần đăng nhập đầu tiên.

### 2.2 Chủ thể và vai trò

- **Chủ tài khoản:** người học, giảng viên hoặc quản trị viên hợp lệ.
- **Kẻ tấn công:** cá nhân hoặc nhóm muốn chiếm quyền sử dụng tài khoản.
- **Client:** trình duyệt/ứng dụng di động, có thể bị sửa, giả lập hoặc nhiễm mã độc.
- **Dịch vụ xác thực/IdP:** kiểm chứng credential và phát hành kết quả xác thực.
- **Ứng dụng/API:** sử dụng kết quả xác thực và thực thi phân quyền.
- **Bên thứ ba:** nhà cung cấp email, SMS, SSO, thiết bị hoặc dịch vụ hỗ trợ.
- **Nhân viên hỗ trợ/vận hành:** có thể giúp khôi phục tài khoản nhưng cũng là mục tiêu của social engineering.

### 2.3 Phạm vi và giả định

Mô hình cần ghi các giả định thay vì mặc định hệ thống luôn đúng. Ví dụ:

- TLS được cấu hình cho endpoint đăng nhập và API.
- Mật khẩu được lưu bằng thuật toán băm chuyên dụng, có salt.
- Credential được gắn với mã tài khoản nội bộ.
- TOTP/passkey chỉ được đăng ký sau một quy trình đủ tin cậy.
- API có kiểm tra quyền theo đối tượng.
- Nhật ký đăng nhập được lưu nhưng không chứa bí mật xác thực.
- Email/SMS và IdP là phụ thuộc bên ngoài với mức tin cậy, khả năng sẵn sàng và cơ chế thu hồi riêng.

Nếu một giả định không đúng, nó trở thành một điểm cần kiểm tra hoặc một rủi ro trong mô hình.

## 3. Bề mặt tấn công và ranh giới tin cậy

**Bề mặt tấn công** là tập hợp điểm mà dữ liệu, credential, yêu cầu hoặc quyền có thể đi vào hệ thống. Trong ATO, các điểm đáng chú ý gồm:

- Đăng ký tài khoản và xác minh email/số điện thoại.
- Đăng nhập mật khẩu, TOTP, passkey và SSO.
- API gửi lại mã, phê duyệt push, khóa/mở khóa tài khoản.
- Thêm/xóa authenticator, đổi mật khẩu và cập nhật thông tin liên hệ.
- Quên mật khẩu, khôi phục tài khoản và hỗ trợ thủ công.
- Cookie, access token, refresh token, redirect/callback và ứng dụng tích hợp.
- API quản lý hồ sơ, quyền, thanh toán hoặc dữ liệu nhạy cảm.
- Thiết bị đầu cuối, trình duyệt, extension, log, hệ thống phân tích và nhân viên hỗ trợ.

### 3.1 Sơ đồ luồng dữ liệu khái quát

~~~mermaid
flowchart LR
    U["Người dùng"] --> C["Browser / Mobile"]
    C -->|"Đăng nhập / thay đổi credential"| AUTH["Dịch vụ xác thực"]
    C -->|"Cookie / token"| APP["Ứng dụng và API"]
    AUTH <--> DB[("Tài khoản, credential,\ntrạng thái MFA")]
    AUTH <--> IDP["IdP / SSO"]
    AUTH <--> REC["Email / SMS / khôi phục"]
    APP <--> SESS[("Phiên, token,\nngữ cảnh xác thực")]
    APP <--> DATA[("Dữ liệu và nghiệp vụ")]
    SUP["Hỗ trợ khách hàng"] --> REC
    SUP --> AUTH
    LOG["Giám sát và audit"] <-- AUTH
    LOG <-- APP
~~~

Sơ đồ là mô hình khái niệm. Khi triển khai thực tế, cần vẽ rõ giao thức, hướng truyền, nơi lưu secret và thành phần nào được quyền thay đổi trạng thái tài khoản.

### 3.2 Ranh giới tin cậy

| Ranh giới | Dữ liệu đi qua | Câu hỏi cần đặt ra |
| --- | --- | --- |
| Thiết bị ↔ dịch vụ xác thực | Password, assertion, OTP, challenge | Client có thể bị phishing hoặc sửa không? Server xác minh nguồn và ngữ cảnh thế nào? |
| Dịch vụ xác thực ↔ kho credential | Bản băm, khóa công khai, bí mật TOTP, trạng thái | Secret được bảo vệ, phân quyền truy cập và xoay/thu hồi ra sao? |
| Ứng dụng ↔ IdP | Authorization code, ID token, assertion | Có kiểm tra issuer, audience, chữ ký, state, nonce, redirect URI và PKCE đúng luồng không? |
| Trình duyệt ↔ ứng dụng/API | Cookie, bearer token, request | Token có thể bị đánh cắp, phát lại hoặc dùng sai audience không? |
| Ứng dụng ↔ hệ thống khôi phục | Email, SMS, mã reset, yêu cầu hỗ trợ | Kênh khôi phục có yếu hơn luồng đăng nhập không? |
| Nhân viên hỗ trợ ↔ tài khoản | Thông tin nhận diện, yêu cầu mở khóa/thay đổi | Có quy trình xác minh, phân quyền, phê duyệt và audit không? |
| Ứng dụng ↔ tài nguyên | Subject, role, object ID, action | API có kiểm tra quyền trên tài nguyên cụ thể không? |

**Ranh giới tin cậy là nơi phải xác minh lại.** Không coi userId, role, trạng thái MFA hoặc tên dịch vụ do client gửi là sự thật. Không tin một token chỉ vì nó có cấu trúc JWT hoặc được nhận từ một URL có vẻ quen thuộc.

## 4. Tác nhân đe dọa và mục tiêu

Kẻ tấn công có thể có năng lực khác nhau; không phải mọi ATO đều bắt đầu bằng kỹ thuật tinh vi.

| Tác nhân | Năng lực thường gặp | Mục tiêu điển hình |
| --- | --- | --- |
| Bot tự động | Thử credential rò rỉ, dò mật khẩu, gửi nhiều request. | Chiếm số lượng lớn tài khoản có bảo vệ yếu. |
| Kẻ phishing | Dụ người dùng nhập mật khẩu/OTP hoặc phê duyệt yêu cầu. | Chiếm một số tài khoản có giá trị. |
| Kẻ đánh cắp phiên | Lấy cookie/token từ thiết bị, trình duyệt, log hoặc mã độc. | Dùng quyền của phiên đã xác thực mà không cần đăng nhập lại. |
| Kẻ social engineering | Mạo danh chủ tài khoản với nhân viên hỗ trợ hoặc nhà cung cấp. | Đổi email, reset mật khẩu hoặc gỡ MFA. |
| Nội gián/lạm dụng quyền | Có quyền hợp lệ nhưng sử dụng sai mục đích. | Truy cập hoặc thay đổi tài khoản ngoài phạm vi được phép. |
| Nhóm có nguồn lực cao | Kết hợp phishing, malware, khai thác thiết bị và tài khoản liên kết. | Duy trì quyền lâu dài hoặc mở rộng sang hệ thống khác. |

### Mục tiêu của kẻ tấn công

Một mục tiêu tổng quát có thể biểu diễn:

~~~text
Chiếm tài khoản =
    đạt quyền sử dụng danh tính nạn nhân
    AND có thể thực hiện ít nhất một hành động trái phép
    OR duy trì khả năng truy cập sau khi chủ tài khoản lấy lại quyền
~~~

Các mục tiêu con có thể là lấy dữ liệu, thay đổi credential, chiếm kênh khôi phục, tạo authenticator mới, sử dụng quyền đặc biệt hoặc đánh cắp token để duy trì truy cập. Khi mô hình hóa, hãy ưu tiên **quyền và tác động** thay vì chỉ liệt kê công cụ tấn công.

## 5. Kịch bản ATO tổng quát: từ credential bị lộ đến tài khoản bị kiểm soát

Xét tình huống giả định: một học viên dùng cùng mật khẩu trên nhiều dịch vụ. Một dịch vụ khác bị rò rỉ dữ liệu credential. Nền tảng học tập có đăng nhập mật khẩu và TOTP, nhưng quy trình khôi phục email yếu và API quản lý thiết bị chưa yêu cầu xác thực lại đủ mạnh.

### 5.1 Chuỗi sự kiện

1. **Lộ credential ở nơi khác:** mật khẩu của học viên xuất hiện trong dữ liệu bị lộ từ một dịch vụ không liên quan.
2. **Thử đăng nhập tự động:** kẻ tấn công dùng thông tin bị lộ để thử truy cập nền tảng học tập. Một số tài khoản có thể bị thử với tốc độ thấp để tránh giới hạn yếu.
3. **Gặp MFA:** nếu TOTP được cấu hình đúng và kẻ tấn công chỉ có mật khẩu, đăng nhập bị chặn ở bước MFA.
4. **Tìm đường khác:** kẻ tấn công có thể nhắm vào người dùng qua phishing, tìm cách chiếm email khôi phục hoặc lạm dụng hỗ trợ khách hàng.
5. **Khôi phục yếu bị lợi dụng:** kẻ tấn công chiếm kênh email hoặc thuyết phục hỗ trợ thay email/đặt lại mật khẩu mà không có bằng chứng đủ mạnh.
6. **Thay authenticator:** sau khi vào được tài khoản, kẻ tấn công thêm authenticator do mình kiểm soát hoặc gỡ yếu tố cũ.
7. **Duy trì phiên:** kẻ tấn công giữ session/token, kể cả khi chủ tài khoản đổi mật khẩu nếu hệ thống không thu hồi phiên cũ.
8. **Lạm dụng tài khoản:** đọc dữ liệu, gửi tin nhắn, thay đổi hồ sơ hoặc thực hiện thao tác có quyền.
9. **Phát hiện muộn:** nếu hệ thống không thông báo thay đổi credential hoặc giám sát đăng nhập bất thường, chủ tài khoản có thể không biết đã bị chiếm.

### 5.2 Sơ đồ chuỗi tấn công

~~~mermaid
flowchart TD
    A["Credential bị lộ ở dịch vụ khác"] --> B["Thử đăng nhập tự động"]
    B --> C{"Mật khẩu được chấp nhận?"}
    C -->|"Không"| X["Từ chối và giám sát"]
    C -->|"Có"| D{"MFA hoàn tất?"}
    D -->|"Không"| E["Tìm đường phishing / khôi phục / hỗ trợ"]
    E --> F{"Chiếm được kênh hoặc quy trình reset?"}
    F -->|"Không"| Y["Chưa chiếm được tài khoản"]
    F -->|"Có"| G["Đặt lại hoặc thay credential"]
    D -->|"Có / MFA bị vượt qua"| H["Thiết lập phiên"]
    G --> H
    H --> I["Duy trì truy cập / thêm authenticator"]
    I --> J["Đọc dữ liệu hoặc lạm dụng quyền"]
    J --> K["Phát hiện, thu hồi và ứng phó"]
~~~

Đây là kịch bản phòng thủ, không phải hướng dẫn thực hiện tấn công. Các bước cho thấy vì sao MFA tại màn hình đăng nhập có thể không đủ nếu **khôi phục, thay authenticator và thu hồi phiên** yếu hơn.

### 5.3 Tác động

- **Bảo mật (confidentiality):** lộ hồ sơ, điểm số, thông tin liên hệ, lịch sử giao dịch.
- **Toàn vẹn (integrity):** sửa dữ liệu, thay thông tin khôi phục, gửi nội dung giả mạo.
- **Sẵn sàng (availability):** đổi mật khẩu/credential khiến chủ tài khoản không đăng nhập được.
- **Tin cậy và uy tín:** người dùng bị mạo danh, thông tin giả được gửi tới người khác.
- **Tài chính/nghiệp vụ:** gian lận thanh toán, chiếm ưu đãi, sử dụng dịch vụ trái phép hoặc chi phí hỗ trợ khôi phục.

## 6. Những đường dẫn phổ biến dẫn tới ATO

### 6.1 Credential stuffing và password spraying

**Credential stuffing** dùng cặp tên tài khoản/mật khẩu đã lộ ở dịch vụ khác để thử đăng nhập. **Password spraying** thử một số mật khẩu phổ biến trên nhiều tài khoản thay vì thử thật nhiều mật khẩu cho một tài khoản.

Rủi ro tăng khi người dùng tái sử dụng mật khẩu, endpoint đăng nhập không giới hạn thử và hệ thống không nhận diện được hành vi phân tán.

**Phòng thủ:**

- Khuyến khích mật khẩu duy nhất và hỗ trợ password manager.
- Kiểm tra mật khẩu mới có nằm trong danh sách mật khẩu phổ biến/bị lộ khi phù hợp, không tiết lộ chi tiết kiểm tra.
- Giới hạn thử theo nhiều chiều: tài khoản, nguồn, thiết bị, thời gian và hành vi; tránh chỉ khóa cứng theo IP.
- Dùng MFA, ưu tiên phương thức chống phishing theo mức rủi ro.
- Giảm khả năng dò tài khoản qua khác biệt thông báo, thời gian hoặc response.
- Giám sát tỷ lệ thất bại và mẫu đăng nhập bất thường, không lưu password trong log.

### 6.2 Phishing mật khẩu và OTP

Kẻ gian giả mạo trang đăng nhập, email hoặc nhân viên hỗ trợ để người dùng cung cấp bí mật. Mã TOTP/SMS có thể bị chuyển tiếp trong thời gian còn hiệu lực.

**Phòng thủ:**

- Ưu tiên passkey/WebAuthn cho tài khoản và thao tác có rủi ro cao; ràng buộc origin/RP ID giúp chống website giả.
- Dùng domain và luồng đăng nhập rõ ràng; tránh redirect không được kiểm soát.
- Thông báo cho người dùng khi credential, email khôi phục hoặc authenticator thay đổi.
- Đào tạo người dùng không phê duyệt đăng nhập mà họ không khởi tạo; quy trình hỗ trợ không yêu cầu đọc OTP hoặc mật khẩu.
- Theo dõi thay đổi bất thường ngay sau đăng nhập và yêu cầu step-up khi cần.

### 6.3 MFA fatigue và push bombing

Kẻ tấn công gửi nhiều yêu cầu push để người dùng mệt mỏi rồi vô tình bấm chấp nhận.

**Phòng thủ:**

- Number matching hoặc hiển thị rõ ngữ cảnh, thiết bị và thời điểm.
- Giới hạn số push, có thời gian chờ và từ chối yêu cầu dồn dập.
- Cảnh báo khi có phê duyệt không do người dùng khởi tạo.
- Ưu tiên phương thức chống phishing cho tài khoản quan trọng.
- Ghi nhận việc người dùng từ chối nhiều yêu cầu liên tiếp như một tín hiệu cần đánh giá.

### 6.4 SIM swap và chiếm kênh SMS

Kẻ gian chiếm quyền số điện thoại hoặc lợi dụng quy trình cấp lại SIM/chuyển số để nhận OTP hoặc liên kết khôi phục.

**Phòng thủ:**

- Không dựa duy nhất vào SMS cho tài khoản rủi ro cao.
- Cung cấp passkey, khóa bảo mật hoặc phương thức thay thế phù hợp.
- Coi thay số điện thoại là thao tác nhạy cảm: xác thực lại, thông báo qua kênh cũ khi có thể và kiểm soát thời gian chờ theo rủi ro.
- Phát hiện việc đổi số rồi đăng nhập/giao dịch nhạy cảm ngay sau đó.

### 6.5 Đánh cắp cookie, access token hoặc refresh token

Kẻ tấn công có thể lấy phiên từ malware, XSS, extension độc hại, log, kho lưu trữ không an toàn hoặc thiết bị dùng chung. Nếu token là bearer token còn hiệu lực, người nắm giữ có thể sử dụng quyền trong phạm vi được cấp.

**Phòng thủ:**

- Cookie phiên web dùng Secure, HttpOnly, SameSite và phạm vi phù hợp; kết hợp biện pháp chống CSRF và XSS.
- Tránh lưu token dài hạn ở vùng JavaScript có thể đọc nếu kiến trúc có lựa chọn an toàn hơn, chẳng hạn BFF.
- Giới hạn TTL, audience và scope; refresh token cần được bảo vệ, xoay vòng hoặc ràng buộc và thu hồi theo thiết kế.
- Có cơ chế thu hồi phiên sau sự kiện rủi ro, đổi mật khẩu, thay authenticator hoặc khóa tài khoản.
- Không đưa cookie/token nguyên vẹn vào log, analytics, URL hoặc thông báo lỗi.

### 6.6 Lạm dụng khôi phục tài khoản

Nếu quy trình quên mật khẩu dễ hơn đăng nhập, nó trở thành đường vòng qua MFA. Kẻ tấn công có thể lợi dụng email bị chiếm, thông tin cá nhân công khai hoặc social engineering nhân viên hỗ trợ.

**Phòng thủ:**

- Token reset ngẫu nhiên, dùng một lần, thời hạn ngắn và ràng buộc đúng tài khoản/transaction.
- Không tiết lộ tài khoản có tồn tại qua response khác biệt rõ ràng.
- Thêm kiểm tra phù hợp khi thay email, số điện thoại hoặc authenticator.
- Thông báo thay đổi qua kênh liên hệ đã đăng ký trước, nếu còn đáng tin.
- Thu hồi hoặc đánh giá lại phiên/refresh token cũ sau reset theo chính sách.
- Hỗ trợ thủ công cần quy trình xác minh, phân quyền, phê duyệt và audit; không dùng câu hỏi dễ tìm thấy trên mạng làm bằng chứng mạnh.

### 6.7 Liên kết danh tính và SSO bị lạm dụng

Tự động gộp tài khoản chỉ vì hai hệ thống trả về cùng email có thể gắn nhầm danh tính. Nếu IdP bị cấu hình sai hoặc ứng dụng không kiểm tra issuer/audience/nonce/state, attacker có thể lợi dụng kết quả xác thực sai ngữ cảnh.

**Phòng thủ:**

- Ánh xạ danh tính liên kết bằng cặp **issuer + subject** theo cấu hình tin cậy.
- Kiểm chứng chữ ký, issuer, audience, thời hạn, nonce/state và redirect URI theo giao thức.
- Không dùng email làm khóa định danh duy nhất giữa các IdP.
- Liên kết tài khoản cần chứng minh quyền kiểm soát cả tài khoản hiện tại và danh tính ngoài được thêm.
- Có khả năng hủy liên kết, audit và xử lý xung đột rõ ràng.

### 6.8 Lạm dụng hỗ trợ khách hàng và nội bộ

Kẻ tấn công có thể giả danh người dùng để yêu cầu reset, đổi email hoặc gỡ MFA. Nhân viên có quyền hỗ trợ quá rộng cũng có thể bị lạm dụng hoặc thao tác nhầm.

**Phòng thủ:**

- Quy trình xác minh danh tính của người yêu cầu có nhiều căn cứ độc lập, không yêu cầu họ đọc mật khẩu/OTP.
- Tách vai trò hỗ trợ, phê duyệt và thực hiện thay đổi đặc biệt.
- Ghi audit ai yêu cầu, ai phê duyệt, ai thực hiện, thay đổi gì và lúc nào.
- Thông báo cho chủ tài khoản và có cơ chế đảo ngược/khóa khẩn cấp phù hợp.
- Hạn chế quyền hỗ trợ theo nguyên tắc tối thiểu; truy cập dữ liệu hỗ trợ phải có lý do và thời hạn.

## 7. Attack tree: những con đường để chiếm tài khoản

Một **attack tree** bắt đầu từ mục tiêu cuối cùng rồi phân rã thành các điều kiện hoặc nhánh cần đạt. Nó giúp nhóm phát triển nhìn thấy rằng chỉ vá màn hình đăng nhập có thể bỏ sót đường khôi phục hoặc chiếm phiên.

~~~mermaid
flowchart TD
    G["Mục tiêu: Chiếm quyền sử dụng tài khoản"]
    G --> O1["Lấy hoặc vượt credential"]
    G --> O2["Chiếm phiên/token"]
    G --> O3["Lạm dụng khôi phục / hỗ trợ"]
    G --> O4["Lạm dụng liên kết danh tính"]
    O1 --> A1["Credential stuffing / spraying"]
    O1 --> A2["Phishing / malware"]
    O1 --> A3["MFA fatigue / SIM swap"]
    O2 --> B1["Cookie/token bị lộ"]
    O2 --> B2["Thiết bị hoặc trình duyệt bị kiểm soát"]
    O3 --> C1["Email/số khôi phục bị chiếm"]
    O3 --> C2["Social engineering hỗ trợ"]
    O4 --> D1["Gộp tài khoản sai"]
    O4 --> D2["Kiểm chứng assertion/token sai"]
~~~

Các nhánh có thể độc lập hoặc kết hợp. Ví dụ attacker có thể lấy password bằng credential stuffing nhưng không vượt được MFA; sau đó chuyển sang lạm dụng email khôi phục. Mô hình tốt cần xem **AND/OR** giữa các điều kiện, năng lực cần có, chi phí và điểm phát hiện.

### Ưu tiên theo đường dẫn rủi ro

Một cách sắp xếp thực dụng:

1. Đường nào dễ thực hiện và có thể mở rộng tự động?
2. Đường nào không cần vượt qua MFA?
3. Đường nào giúp duy trì quyền sau khi người dùng đổi mật khẩu?
4. Đường nào có thể chiếm tài khoản đặc quyền hoặc tài khoản có dữ liệu nhạy cảm?
5. Đường nào khó phát hiện vì log thiếu hoặc phụ thuộc bên ngoài?

Ưu tiên sửa các đường có **xác suất khai thác và tác động cao**, đặc biệt các đường vòng qua khôi phục, thay authenticator và phiên.

## 8. Phân tích STRIDE cho kịch bản ATO

STRIDE là một cách phân loại mối đe dọa theo sáu nhóm. Dùng nó để kiểm tra hệ thống có bỏ sót loại rủi ro nào không; không cần ép mọi vấn đề vào một nhóm duy nhất.

| Nhóm | Câu hỏi trong ATO | Ví dụ | Biện pháp tiêu biểu |
| --- | --- | --- | --- |
| **Spoofing — Giả mạo** | Có thể giả danh chủ tài khoản hoặc dịch vụ không? | Dùng password bị lộ, giả callback/IdP, mạo danh hỗ trợ. | MFA phù hợp, passkey, xác minh issuer/subject, quy trình hỗ trợ an toàn. |
| **Tampering — Sửa đổi** | Có thể thay credential, email, role, session hoặc dữ liệu không? | Thay email khôi phục, thêm passkey của attacker, sửa request. | Xác thực lại, kiểm soát quyền, kiểm tra toàn vẹn và audit. |
| **Repudiation — Chối bỏ** | Có thể phủ nhận hành động do thiếu bằng chứng không? | Không biết ai gỡ MFA hoặc đổi email. | Nhật ký chống sửa đổi, liên kết actor/transaction, thời gian và phê duyệt. |
| **Information Disclosure — Lộ thông tin** | Có thể lấy dữ liệu cá nhân hoặc bí mật xác thực không? | Cookie/token trong log, hồ sơ học viên bị truy cập. | Giảm dữ liệu, mã hóa/bảo vệ secret, phân quyền và kiểm soát log. |
| **Denial of Service — Từ chối dịch vụ** | Có thể khóa người dùng hoặc làm hệ thống không sẵn sàng không? | Lạm dụng lockout, push bombing, gửi reset liên tục. | Rate limit, kiểm soát khóa tài khoản, bảo vệ queue và phục hồi. |
| **Elevation of Privilege — Leo thang quyền** | Có thể biến tài khoản thường thành đặc quyền không? | Lợi dụng API role, tài khoản hỗ trợ hoặc liên kết IdP sai. | Authorization server-side, tách vai trò, least privilege, phê duyệt. |

STRIDE giúp phân loại; để ưu tiên, hãy bổ sung **tài sản, tác động, khả năng khai thác, phạm vi người dùng, khả năng phát hiện và chi phí khắc phục**.

## 9. Biện pháp phòng thủ theo vòng đời tài khoản

ATO cần được phòng thủ xuyên suốt, không chỉ ở endpoint đăng nhập.

### 9.1 Đăng ký và gắn authenticator

- Xác định tài khoản được tạo cho chủ thể nào và mức kiểm chứng ban đầu phù hợp.
- Xác minh kênh liên hệ với ngữ nghĩa rõ ràng: email verified chỉ chứng minh quyền truy cập kênh theo quy trình đó, không tự chứng minh danh tính pháp lý.
- Khi thêm passkey/TOTP/khóa bảo mật, yêu cầu phiên đủ tin cậy hoặc quy trình enrollment riêng.
- Gắn credential với mã tài khoản nội bộ và trạng thái; không để client tự gắn credential vào subject tùy ý.
- Thông báo khi có authenticator mới, thay đổi kênh khôi phục hoặc thay đổi bảo mật quan trọng.

### 9.2 Đăng nhập

- Mật khẩu được băm bằng thuật toán chuyên dụng như Argon2id với salt riêng; không lưu plaintext hoặc log.
- Giới hạn thử sai theo nhiều chiều, phát hiện credential stuffing và password spraying.
- Ưu tiên passkey/WebAuthn chống phishing khi phù hợp; TOTP/SMS có giới hạn cần được hiểu rõ.
- Chỉ cấp full session sau khi tất cả yếu tố bắt buộc đã đạt; pending MFA chỉ có quyền tối thiểu.
- Tránh thông báo lỗi làm lộ tài khoản tồn tại, credential đúng một phần hoặc chi tiết nội bộ.

### 9.3 Phiên và token

- Xoay session ID sau đăng nhập và các mốc nhạy cảm để giảm session fixation.
- Cookie web dùng Secure, HttpOnly, SameSite và phạm vi phù hợp; xử lý CSRF/XSS.
- Giới hạn TTL, scope và audience; refresh token được bảo vệ và quản lý vòng đời.
- Có khả năng thu hồi phiên sau reset, thay authenticator, cảnh báo chiếm tài khoản hoặc yêu cầu của người dùng.
- Cân nhắc xác thực lại khi thay email, thay MFA, thay thông tin thanh toán hoặc thực hiện giao dịch rủi ro cao.

### 9.4 Khôi phục và hỗ trợ

- Khôi phục không được yếu hơn đáng kể so với đăng nhập và enrollment.
- Mã reset dùng một lần, thời hạn ngắn, ràng buộc đúng tài khoản và transaction.
- Cảnh báo thay đổi qua kênh đã đăng ký trước nếu còn đáng tin cậy.
- Tách vai trò nhân viên hỗ trợ; ghi nhận và phê duyệt các thao tác đặc quyền.
- Có quy trình khẩn cấp để khóa phiên, thu hồi credential và khôi phục quyền kiểm soát.

### 9.5 Phân quyền và dữ liệu

- API lấy subject từ phiên/token đã kiểm chứng, không tin ID hoặc role do client gửi.
- Kiểm tra quyền theo **subject + resource + action + context**.
- Áp least privilege cho người dùng, dịch vụ, nhân viên hỗ trợ và tài khoản quản trị.
- Hạn chế truy cập dữ liệu nhạy cảm; kiểm tra export, download và hành động hàng loạt.
- Tách quyền đọc, sửa, phê duyệt và quản trị; yêu cầu phê duyệt độc lập cho thao tác có tác động lớn.

## 10. Phát hiện ATO: cần quan sát những tín hiệu nào?

Không có một tín hiệu đơn lẻ đủ để kết luận ATO. Đăng nhập từ IP mới có thể là người dùng đi du lịch; thất bại liên tiếp có thể là gõ nhầm; một thay đổi email có thể là hợp lệ. Cần **kết hợp tín hiệu, bối cảnh, mức rủi ro và hành vi tiếp theo**.

### 10.1 Nhóm tín hiệu

| Giai đoạn | Tín hiệu có thể quan sát | Ý nghĩa cần đánh giá |
| --- | --- | --- |
| Trước đăng nhập | Nhiều tài khoản được thử từ một nguồn hoặc nhiều nguồn; mẫu user-agent bất thường. | Credential stuffing, spraying hoặc bot. |
| Đăng nhập | Nhiều lần thất bại rồi một lần thành công bất thường; đăng nhập từ thiết bị/địa điểm mới. | Có thể là credential compromise; cần đối chiếu lịch sử và tín hiệu khác. |
| MFA | Push liên tiếp, nhiều OTP sai, phê duyệt sau chuỗi từ chối. | MFA fatigue hoặc thử chiếm yếu tố. |
| Sau đăng nhập | Tạo phiên mới từ môi trường khác; đổi mật khẩu/email/MFA ngay sau login. | Có thể là attacker đang củng cố quyền. |
| Duy trì phiên | Hai vị trí/thiết bị dùng cùng phiên bất thường; token dùng ngoài pattern. | Cookie/token bị chia sẻ hoặc đánh cắp. |
| Hành động | Tải dữ liệu hàng loạt, gửi tin nhắn hàng loạt, thay thông tin thanh toán. | Lạm dụng tài khoản sau khi chiếm. |
| Khôi phục | Nhiều yêu cầu reset, đổi kênh liên hệ rồi login mới. | Khai thác recovery hoặc social engineering. |
| Hỗ trợ | Nhiều yêu cầu gỡ MFA, thay email hoặc mở khóa từ một nhóm dấu hiệu giống nhau. | Lạm dụng quy trình hỗ trợ hoặc nội bộ. |

### 10.2 Kết hợp tín hiệu theo chuỗi

Ví dụ, tổ hợp sau đáng quan tâm hơn từng sự kiện riêng lẻ:

1. Đăng nhập từ thiết bị mới sau nhiều lần thử thất bại.
2. Hoàn tất MFA theo cách khác thường.
3. Ngay sau đó đổi email khôi phục.
4. Thêm authenticator mới.
5. Tải dữ liệu hoặc gửi thông điệp với tần suất cao.

Một chính sách rủi ro có thể yêu cầu step-up, tạm hoãn hành động nhạy cảm, thông báo người dùng hoặc chuyển sang quy trình xác minh. **Không nên khóa tài khoản tự động chỉ dựa trên một tín hiệu yếu**; cần cân nhắc false positive và tác động tới người dùng hợp lệ.

### 10.3 Dữ liệu log hữu ích và dữ liệu không được ghi

Nên ghi sự kiện có cấu trúc như:

- Mã tài khoản nội bộ hoặc định danh được bảo vệ.
- Mã transaction/session audit không thể dùng thay credential.
- Thời điểm, loại sự kiện, kết quả, phương thức và mã lý do.
- Tín hiệu thiết bị/mạng ở mức cần thiết, theo chính sách quyền riêng tư.
- Hành động nhạy cảm: thêm/xóa authenticator, reset, đổi email, thu hồi phiên, phê duyệt hỗ trợ.
- Actor thực hiện và người phê duyệt nếu có.

Không ghi mật khẩu, OTP, secret TOTP, khóa riêng, raw cookie/session ID, access/refresh token hoặc mã khôi phục có thể sử dụng. Nếu cần tương quan sự kiện, dùng ID audit hoặc giá trị dẫn xuất an toàn, không dùng bí mật đang trao quyền.

## 11. Ứng phó khi nghi ngờ tài khoản bị chiếm

Mục tiêu ứng phó là **ngăn truy cập trái phép, bảo toàn bằng chứng, khôi phục quyền kiểm soát và hạn chế tái diễn**. Cần quy định người có thẩm quyền, phạm vi hành động và cách liên hệ chủ tài khoản.

### 11.1 Quy trình tham khảo

1. **Tiếp nhận và phân loại:** xác định tài khoản, thời điểm, hành động bất thường, mức nhạy cảm và bằng chứng ban đầu.
2. **Hạn chế thiệt hại:** tùy mức tin cậy, tạm dừng thao tác rủi ro, khóa phiên hoặc chặn credential nghi bị lộ; tránh xóa log hay làm mất bằng chứng.
3. **Thu hồi đường truy cập:** vô hiệu hóa session/token/refresh token, credential hoặc authenticator bị nghi chiếm; kiểm tra liên kết IdP và kênh khôi phục.
4. **Xác minh chủ tài khoản:** dùng quy trình hỗ trợ an toàn, không yêu cầu người dùng cung cấp mật khẩu/OTP; không dựa vào thông tin công khai dễ đoán.
5. **Khôi phục:** đặt lại credential, đăng ký authenticator mới qua luồng đủ tin cậy, kiểm tra thông tin liên hệ và thiết bị.
6. **Kiểm tra hoạt động:** xem các thay đổi hồ sơ, dữ liệu đã đọc/xuất, giao dịch, tin nhắn và tài khoản liên quan.
7. **Thông báo phù hợp:** thông báo cho người bị ảnh hưởng và các bên liên quan theo quy trình tổ chức/quy định áp dụng.
8. **Đóng sự cố và cải thiện:** xác định đường tấn công ban đầu, điểm kiểm soát bị thiếu, phạm vi ảnh hưởng và hành động phòng ngừa.

### 11.2 Không chỉ đổi mật khẩu

Nếu attacker đã thêm passkey của mình hoặc giữ refresh token, **đổi mật khẩu có thể không đủ**. Quy trình containment cần xem:

- Các phiên đang hoạt động và token đã phát hành.
- Authenticator đã đăng ký, gồm passkey/TOTP/khóa bảo mật.
- Email/số điện thoại khôi phục và liên kết IdP.
- Ứng dụng OAuth đã được cấp quyền hoặc credential bên thứ ba.
- Quyền đặc biệt hoặc thay đổi vai trò.
- Thiết bị đầu cuối nếu có dấu hiệu malware/session theft.

Việc thu hồi phải hiểu giới hạn kiến trúc: JWT tự chứa có thể còn được chấp nhận đến khi hết hạn nếu resource server không có kiểm tra trạng thái/denylist hoặc cơ chế thu hồi tương ứng. Vì vậy cần thiết kế TTL, audience, introspection hoặc cơ chế kiểm tra trạng thái phù hợp với mức rủi ro.

### 11.3 Phục hồi và thông báo

Thông báo nên giúp chủ tài khoản biết sự kiện nào xảy ra, thời điểm và cách liên hệ qua kênh chính thức. Không đưa token reset hoặc dữ liệu nhạy cảm vào nội dung dễ bị chuyển tiếp. Cung cấp một đường báo cáo khẩn cấp và hướng dẫn bảo vệ tài khoản email/thiết bị nếu đó là điểm xâm nhập.

## 12. Chuyển threat model thành yêu cầu bảo mật

Mỗi rủi ro cần được chuyển thành **yêu cầu có thể kiểm chứng**, gắn với thành phần chịu trách nhiệm và bằng chứng kiểm thử.

| ID | Yêu cầu bảo mật | Thành phần thực thi | Bằng chứng kiểm tra |
| --- | --- | --- | --- |
| TM-01 | Không tạo full session khi MFA bắt buộc chưa hoàn tất. | Dịch vụ xác thực | Test dừng sau yếu tố thứ nhất; API từ chối pending transaction. |
| TM-02 | Challenge phải mới, có thời hạn và chỉ dùng trong đúng transaction. | Verifier | Test challenge hết hạn, sai transaction và phát lại. |
| TM-03 | Thêm/xóa authenticator phải yêu cầu mức xác thực phù hợp. | Account security service | Test session cũ/đã hạ mức không thể thay MFA. |
| TM-04 | Reset credential không được tiết lộ tài khoản tồn tại và token reset phải dùng một lần. | Recovery service | Test response, hết hạn, tái sử dụng token và rate limit. |
| TM-05 | Đổi email/số khôi phục phải có thông báo và kiểm soát theo rủi ro. | Account service | Test đổi kênh, thông báo và thời gian chờ nếu có. |
| TM-06 | Session ID phải được xoay khi đăng nhập hoặc nâng trạng thái xác thực. | Session service | Test session fixation trước/sau login. |
| TM-07 | API không tin subject, role, mfaPassed do client tự gửi. | API/resource server | Test sửa payload/URL; quyền phải lấy từ nguồn server-side. |
| TM-08 | Token phải được kiểm tra đúng issuer, audience, thời hạn, chữ ký và scope. | API/gateway | Test token sai audience, issuer, chữ ký và hết hạn. |
| TM-09 | Có thể thu hồi hoặc hạn chế phiên khi tài khoản bị báo chiếm. | Session/token service | Test sự kiện incident làm phiên không còn được chấp nhận theo SLA. |
| TM-10 | Nhật ký không chứa credential/token bí mật nhưng đủ tương quan sự kiện. | Logging pipeline | Kiểm tra log sau login, reset, thay MFA và revoke. |
| TM-11 | Liên kết IdP phải dựa trên issuer+subject và quy trình chứng minh quyền kiểm soát. | Federation/account linking | Test email trùng nhưng subject/issuer khác không tự gộp. |
| TM-12 | Hỗ trợ khách hàng không thể tự ý bỏ MFA nếu thiếu phê duyệt và audit phù hợp. | Support tooling | Test phân quyền, approval và nhật ký người thực hiện. |

Yêu cầu tốt có thể được kiểm tra bằng test tự động, kiểm thử tích hợp, review cấu hình hoặc diễn tập vận hành. Tránh viết yêu cầu mơ hồ như “hệ thống phải rất an toàn”; hãy nêu **điều kiện, hành vi mong đợi và bằng chứng**.

## 13. Kịch bản kiểm thử và diễn tập

Bảng sau có thể dùng để lập kế hoạch kiểm thử phòng thủ. Các tình huống giả lập nên thực hiện trong môi trường được phép, với tài khoản và dữ liệu thử.

| Kịch bản | Hành vi thử nghiệm | Kết quả mong đợi |
| --- | --- | --- |
| Credential stuffing | Gửi chuỗi đăng nhập thất bại có kiểm soát trên tài khoản thử. | Giới hạn/đánh giá rủi ro, log sự kiện, không lộ tài khoản qua response. |
| Password đúng, MFA thiếu | Hoàn tất yếu tố thứ nhất nhưng dừng trước MFA. | Không có full session; endpoint dữ liệu riêng tư từ chối. |
| TOTP phát lại | Trình lại mã đã được chấp nhận trong cửa sổ áp dụng. | Server từ chối tái sử dụng theo chính sách và ghi nhận sự kiện. |
| WebAuthn sai origin/challenge | Dùng assertion không khớp giao dịch thử. | Verifier từ chối; không tạo session. |
| Push fatigue | Tạo nhiều yêu cầu push thử nghiệm trong giới hạn cho phép. | Có giới hạn, number matching/hiển thị ngữ cảnh và cảnh báo phù hợp. |
| Session fixation | Giữ ID trước login rồi thử dùng sau login. | ID phiên được xoay; ID cũ không trở thành phiên xác thực. |
| Token sai audience | Gửi token dành cho API khác. | Resource server từ chối. |
| Reset token tái sử dụng | Dùng lại token reset đã thành công. | Từ chối, không thay credential lần nữa. |
| Thêm authenticator bằng phiên cũ | Dùng phiên quá cũ hoặc không đủ assurance để thêm passkey. | Yêu cầu xác thực lại/step-up; không gắn credential. |
| Liên kết tài khoản sai | Hai IdP trả cùng email nhưng issuer/subject khác. | Không tự động gộp; cần quy trình liên kết được bảo vệ. |
| Thu hồi sau báo chiếm | Khóa tài khoản/thu hồi phiên theo quy trình. | Session/token/credential được xử lý theo chính sách; audit đầy đủ. |
| Role giả từ client | Sửa payload gửi role=admin hoặc userId khác. | API bỏ qua dữ liệu tự khai và kiểm tra quyền server-side. |

### Diễn tập tabletop

Một nhóm có thể diễn tập theo vai trò:

- **SOC/đội giám sát:** phát hiện chuỗi đăng nhập bất thường và thay đổi MFA.
- **Đội xác thực:** xác định session, credential, refresh token và IdP liên quan.
- **Hỗ trợ khách hàng:** xác minh người báo mất tài khoản qua quy trình an toàn.
- **Đội sản phẩm/API:** xác định dữ liệu và hành động mà tài khoản đã truy cập.
- **Quản lý sự cố:** quyết định khóa/thu hồi, thông báo và mở lại tài khoản.

Sau diễn tập, ghi lại thời gian phát hiện, thời gian containment, số tài khoản ảnh hưởng, dữ liệu có thể bị truy cập, điểm mù log và các thay đổi ưu tiên.

## 14. Cân bằng bảo mật, khả dụng và quyền riêng tư

Biện pháp chống ATO có thể gây tác động phụ nếu thiết kế không cẩn thận:

- **Khóa tài khoản quá sớm:** attacker có thể cố ý làm nạn nhân bị khóa bằng cách gửi nhiều lần đăng nhập sai. Dùng kiểm soát theo rủi ro và cơ chế khôi phục an toàn thay vì khóa cứng thiếu giới hạn.
- **Thu thập quá nhiều dữ liệu thiết bị/vị trí:** có thể tạo rủi ro quyền riêng tư và vẫn không chứng minh danh tính. Chỉ thu thập tín hiệu cần thiết, giới hạn thời gian lưu và quyền truy cập.
- **MFA gây ma sát:** người dùng có thể tìm cách né quy trình hoặc dùng phương thức yếu hơn. Hỗ trợ passkey và nhiều authenticator an toàn, có hướng dẫn khôi phục.
- **Thông báo quá nhiều:** cảnh báo liên tục khiến người dùng bỏ qua. Ưu tiên sự kiện nhạy cảm và cho phép người dùng hiểu hành động cần làm.
- **Chặn nhầm thiết bị hợp lệ:** người dùng đổi điện thoại, đi du lịch hoặc dùng mạng chia sẻ. Kết hợp tín hiệu thay vì coi IP/thiết bị là bằng chứng duy nhất.
- **Quy trình hỗ trợ quá quyền lực:** tiện cho khôi phục nhưng trở thành mục tiêu social engineering. Dùng least privilege, phê duyệt và audit.

Một chính sách tốt bảo vệ chủ tài khoản nhưng cũng cho phép người hợp lệ lấy lại quyền kiểm soát. **Khôi phục an toàn là một phần của thiết kế xác thực**, không phải chức năng phụ thêm sau khi đăng nhập đã xong.

## 15. Checklist lập threat model cho ATO

Khi bắt đầu một sản phẩm hoặc review một luồng hiện có, có thể dùng checklist sau:

- [ ] Đã xác định tài khoản, dữ liệu, credential, phiên/token và quyền đặc biệt cần bảo vệ.
- [ ] Đã liệt kê chủ thể, attacker, phụ thuộc bên ngoài và giả định của hệ thống.
- [ ] Đã vẽ luồng dữ liệu từ đăng ký, đăng nhập, MFA, phiên, API tới khôi phục.
- [ ] Đã đánh dấu ranh giới tin cậy và nơi kiểm chứng bằng chứng.
- [ ] Đã xét credential stuffing, phishing, MFA fatigue, SIM swap, session theft, recovery abuse và federation/linking abuse.
- [ ] Đã kiểm tra việc thêm/xóa authenticator và thay kênh khôi phục.
- [ ] Đã kiểm tra full session chỉ được cấp sau khi đủ chính sách.
- [ ] Đã xác minh API không tin userId/role/cờ MFA do client tự gửi.
- [ ] Đã có TTL, scope, audience và cách thu hồi phiên/token.
- [ ] Đã xác định tín hiệu phát hiện, log an toàn và người chịu trách nhiệm ứng phó.
- [ ] Đã chuyển rủi ro thành yêu cầu và test có kết quả mong đợi.
- [ ] Đã xem xét false positive, khả năng tiếp cận và quyền riêng tư.

## 16. Tự kiểm tra

**Câu 1.** Một hệ thống có 10.000 lần đăng nhập thất bại nhưng không có lần nào thành công. Có thể kết luận đã xảy ra ATO không?

**Đáp án:** Chưa. Đây là dấu hiệu dò hoặc lạm dụng đăng nhập; ATO cần bằng chứng rằng kẻ tấn công đã giành được quyền sử dụng tài khoản hoặc phiên. Vẫn cần điều tra và giảm thiểu.

**Câu 2.** Vì sao bật TOTP nhưng giữ quy trình reset mật khẩu qua email yếu vẫn có rủi ro ATO?

**Đáp án:** Attacker có thể bỏ qua luồng đăng nhập bằng cách chiếm email hoặc lạm dụng quy trình reset, thay credential hoặc MFA. Khôi phục phải có mức bảo vệ tương xứng.

**Câu 3.** Người dùng đã đăng nhập bằng passkey. Tại sao cần tiếp tục bảo vệ cookie phiên?

**Đáp án:** Passkey bảo vệ bằng chứng đăng nhập, còn cookie phiên duy trì quyền truy cập sau đó. Nếu cookie bị đánh cắp, kẻ giữ nó có thể sử dụng phiên mà không cần trình passkey lại.

**Câu 4.** Hai tài khoản ở hai IdP có cùng email. Có thể tự động liên kết không?

**Đáp án:** Không. Cần xác minh issuer và subject, kiểm chứng quyền kiểm soát các tài khoản và xử lý xung đột qua quy trình liên kết an toàn.

**Câu 5.** Một client gửi userId của quản trị viên và mfaPassed=true. API nên xử lý thế nào?

**Đáp án:** Không tin hai trường tự khai. API xác minh session/token ở server, lấy subject và ngữ cảnh xác thực đáng tin cậy, rồi kiểm tra quyền trên hành động/tài nguyên.

**Câu 6.** Vì sao thay mật khẩu chưa chắc đã chấm dứt ATO?

**Đáp án:** Attacker có thể giữ cookie, refresh token, passkey đã thêm, ứng dụng OAuth được cấp quyền hoặc kênh khôi phục. Ứng phó phải rà soát và thu hồi tất cả đường truy cập liên quan.

**Câu 7.** IP mới có đủ để khóa tài khoản ngay không?

**Đáp án:** Không. IP là tín hiệu rủi ro, có thể thay đổi hoặc dùng chung. Nên kết hợp với hành vi, trạng thái thiết bị, thay đổi credential và thao tác tiếp theo; tránh khóa nhầm.

**Câu 8.** Trong attack tree, tại sao phải xét cả khôi phục và phiên sau khi đã có MFA?

**Đáp án:** Vì attacker có thể đi đường vòng qua recovery hoặc đánh cắp session/token. MFA ở lần đăng nhập không bảo vệ tự động các con đường này.

**Câu 9.** Một giảng viên bị chiếm tài khoản và attacker tải danh sách học viên. Ba nhóm tác động CIA nào có thể bị ảnh hưởng?

**Đáp án:** Confidentiality bị ảnh hưởng do lộ dữ liệu; integrity có thể bị ảnh hưởng nếu dữ liệu bị sửa; availability có thể bị ảnh hưởng nếu attacker đổi credential hoặc khóa chủ tài khoản.

**Câu 10.** Một yêu cầu bảo mật tốt để giảm ATO qua thêm passkey trái phép cần mô tả gì?

**Đáp án:** Nêu rõ điều kiện xác thực lại/step-up trước khi thêm, credential được gắn với subject nào, kiểm tra trạng thái và transaction, thông báo/audit thay đổi, cùng test chứng minh phiên cũ hoặc phiên chưa đủ bảo đảm không thể tự thêm authenticator.

## Ghi nhớ

**Kịch bản chiếm tài khoản không chỉ là kẻ tấn công biết mật khẩu.** ATO có thể bắt đầu từ credential stuffing, phishing, MFA fatigue, SIM swap, malware đánh cắp phiên, khôi phục yếu, hỗ trợ bị social engineering hoặc liên kết danh tính sai. Sau khi có quyền, attacker có thể thêm authenticator, giữ token, thay kênh khôi phục và lạm dụng quyền của tài khoản.

Threat model tốt xác định **tài sản, chủ thể, bề mặt tấn công, ranh giới tin cậy, chuỗi tấn công và hậu quả**; sau đó chuyển từng rủi ro thành kiểm soát và test có thể kiểm chứng. Phòng thủ cần bao phủ toàn vòng đời: enrollment, xác thực, MFA chống phishing, phiên/token, khôi phục, liên kết danh tính, phân quyền, giám sát và ứng phó. Mục tiêu cuối cùng là phát hiện và chặn việc chuyển từ một dấu hiệu bất thường thành **quyền kiểm soát tài khoản trái phép**, đồng thời giúp chủ tài khoản hợp lệ khôi phục an toàn.
