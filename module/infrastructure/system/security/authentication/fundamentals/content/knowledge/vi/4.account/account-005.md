# Chu kỳ tài khoản

> **Chương:** Account  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS  
> **Phạm vi:** Quản lý tài khoản trong hệ thống xác thực, từ tạo lập danh tính và gắn phương thức xác thực đến sử dụng, thay đổi, khôi phục, đình chỉ và kết thúc tài khoản.

## 1. Tài khoản có một chu kỳ sống, không chỉ một màn hình đăng nhập

**Tài khoản (account)** là bản ghi mà hệ thống dùng để đại diện cho một chủ thể, liên kết các định danh, phương thức xác thực, trạng thái và quyền liên quan. Chủ thể có thể là một người dùng, một dịch vụ hoặc một thiết bị. **Chu kỳ tài khoản** là tập hợp các trạng thái và chuyển đổi mà bản ghi đó trải qua từ lúc được tạo đến lúc ngừng sử dụng.

Một tài khoản đã đăng nhập an toàn hôm nay vẫn có thể bị chiếm quyền ngày mai qua việc thay email, thêm phương thức xác thực mới hoặc lợi dụng quy trình khôi phục. Một nhân viên nghỉ việc có thể không đăng nhập nữa, nhưng phiên hoặc token cũ vẫn tiếp tục truy cập dữ liệu nếu hệ thống chưa xử lý việc thu hồi. Vì vậy, bảo vệ tài khoản đòi hỏi kiểm soát **toàn bộ vòng đời**.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt tài khoản, danh tính, tên đăng nhập, credential, phương thức xác thực, phiên và quyền truy cập.
2. Mô tả các giai đoạn tạo, xác minh, kích hoạt, sử dụng, bảo trì, khôi phục, vô hiệu hóa và xóa tài khoản.
3. Thiết kế các điều kiện chuyển trạng thái và ranh giới tin cậy nhằm ngăn chiếm tài khoản.
4. Áp dụng các nguyên tắc phòng chống phishing, replay, lạm dụng đăng nhập và lợi dụng luồng khôi phục.
5. Nhận diện hệ quả đối với phiên, token, quyền và dữ liệu khi trạng thái tài khoản thay đổi.

## 2. Những khái niệm không được đánh đồng

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| **Tài khoản** | Bản ghi chủ thể và trạng thái quản lý | Tài khoản nhân viên với ID nội bộ 824 |
| **Danh tính (identity)** | Tập thuộc tính giúp nhận diện chủ thể trong một ngữ cảnh | Nhân viên của tổ chức X; khách hàng số 824 |
| **Định danh (identifier)** | Giá trị dùng để tham chiếu hoặc tìm tài khoản | ID nội bộ, username, địa chỉ email |
| **Credential / authenticator** | Bí mật hoặc phương tiện dùng chứng minh quyền kiểm soát danh tính | Mật khẩu, passkey, ứng dụng TOTP, khóa riêng chứng chỉ |
| **Xác thực (authentication)** | Kiểm tra bằng chứng của chủ thể đang yêu cầu | Xác minh passkey hoặc mật khẩu và MFA |
| **Phiên / token** | Cơ chế duy trì hoặc chuyển tiếp ngữ cảnh đã xác thực | Cookie phiên, access token, refresh token |
| **Phân quyền (authorization)** | Quyết định chủ thể được làm gì trên tài nguyên nào | Quyền xem hóa đơn của chính mình |

**ID tài khoản nội bộ** nên ổn định, không phụ thuộc vào email hoặc username có thể thay đổi. Một email có thể đổi chủ, được tái cấp hoặc gắn với nhiều quan hệ đăng nhập; vì vậy không nên mặc nhiên coi nó là khóa định danh bất biến xuyên suốt chu kỳ tài khoản.

Ba vòng đời có liên quan nhưng khác nhau:

- **Vòng đời tài khoản:** tạo, kích hoạt, hoạt động, bị đình chỉ, khôi phục, vô hiệu hóa, xóa.
- **Vòng đời credential:** đăng ký, sử dụng, thay thế, thu hồi phương thức xác thực.
- **Vòng đời phiên/token:** phát hành, làm mới, hết hạn, đăng xuất, thu hồi.

Khi tài khoản bị khóa hoặc vô hiệu hóa, việc chỉ đổi một cờ trong cơ sở dữ liệu thường **chưa đủ**: các phiên, token, quyền trong dịch vụ khác và phương thức khôi phục cũng cần được xem xét.

## 3. Bản đồ các giai đoạn

Một hệ thống có thể dùng nhiều trạng thái và tên gọi khác nhau. Sơ đồ sau là **mô hình tham khảo**, không phải tập trạng thái bắt buộc đối với mọi sản phẩm:

~~~mermaid
stateDiagram-v2
    [*] --> ChoKichHoat: Đăng ký hoặc cấp tài khoản
    ChoKichHoat --> HoatDong: Đạt điều kiện kích hoạt
    ChoKichHoat --> HetHieuLuc: Lời mời hết hạn / hủy đăng ký
    HoatDong --> HoatDong: Đổi thông tin / credential / quyền
    HoatDong --> TamKhoa: Phản ứng rủi ro hoặc khóa tạm thời
    TamKhoa --> HoatDong: Kiểm tra và mở khóa
    HoatDong --> DinhChi: Quyết định quản trị / sự cố
    TamKhoa --> DinhChi: Xác nhận sự cố
    DinhChi --> HoatDong: Khôi phục có thẩm quyền
    HoatDong --> VoHieuHoa: Nghỉ việc / đóng tài khoản
    DinhChi --> VoHieuHoa: Kết thúc quyền sử dụng
    VoHieuHoa --> XoaHoacLuuTru: Đủ điều kiện xử lý dữ liệu
    HetHieuLuc --> XoaHoacLuuTru
    XoaHoacLuuTru --> [*]
~~~

| Giai đoạn | Điều kiện hoặc mục tiêu | Kiểm soát đáng chú ý |
|---|---|---|
| **Tạo lập** | Xác định nguồn và phạm vi cấp tài khoản | Chống tạo hàng loạt, chống nhầm/chiếm định danh |
| **Xác minh và kích hoạt** | Chứng minh quyền kiểm soát kênh liên hệ hoặc danh tính ở mức yêu cầu | Mã xác minh một lần, thời hạn, ràng buộc ngữ cảnh |
| **Hoạt động** | Đăng nhập và dùng tài nguyên được cấp quyền | Xác thực phù hợp, phân quyền từng yêu cầu, bảo vệ phiên |
| **Bảo trì** | Đổi email, mật khẩu, passkey, MFA, thuộc tính và quyền | Xác thực lại, kiểm tra ý định, nhật ký và thông báo |
| **Khôi phục** | Lấy lại quyền truy cập khi mất credential | Bảo đảm tương xứng rủi ro, chống chiếm quyền |
| **Khóa/đình chỉ** | Ngăn tạm thời hoặc theo quyết định có thẩm quyền | Chặn truy cập, xử lý phiên/token, quy trình mở khóa |
| **Vô hiệu hóa** | Kết thúc khả năng sử dụng tài khoản | Thu hồi quyền, phiên, tích hợp và credential thích hợp |
| **Xóa/lưu trữ** | Xử lý dữ liệu theo nhu cầu và nghĩa vụ áp dụng | Giảm thiểu dữ liệu, kiểm soát lưu trữ và tái sử dụng ID |

**Khóa tạm thời**, **đình chỉ** và **vô hiệu hóa** nên có ý nghĩa riêng trong chính sách. Ví dụ, khóa sau nhiều lần nhập sai mật khẩu có thể được mở bằng cơ chế có kiểm soát; đình chỉ vì nghi bị chiếm quyền cần điều tra; vô hiệu hóa khi nhân viên nghỉ việc phải kết thúc quyền truy cập dài hạn. Cũng cần tránh biến cơ chế khóa tự động thành công cụ từ chối dịch vụ: kẻ tấn công không nên chỉ cần nhập sai nhiều lần là làm tê liệt hàng loạt tài khoản.

## 4. Bước tạo lập: ai có quyền sinh tài khoản?

Hai mô hình thường gặp:

**Tự đăng ký (self-registration):** người dùng cung cấp thông tin tối thiểu để tạo tài khoản. Cần giới hạn hành vi tự động, kiểm tra định dạng và trùng lặp định danh, đồng thời tránh thông báo làm lộ việc một email đã có tài khoản nếu điều đó tạo rủi ro. Hệ thống không nên cấp quyền nhạy cảm chỉ vì một địa chỉ email được nhập vào biểu mẫu.

**Cấp phát có quản trị (provisioning):** quản trị viên hoặc hệ thống nhân sự, quản lý danh tính cấp tài khoản theo sự kiện gia nhập tổ chức. Quyền cấp tài khoản phải có nguồn đáng tin cậy, phạm vi vai trò rõ ràng và cơ chế đối soát. Một bản ghi xuất hiện trong danh sách nhân sự chưa đồng nghĩa người sở hữu đã hoàn tất bước xác thực đầu tiên.

### Phân biệt xác minh kênh liên hệ với xác minh danh tính

Khi người dùng nhấp liên kết gửi đến email, hệ thống có cơ sở cho rằng họ **đang kiểm soát hộp thư nhận liên kết** tại thời điểm đó. Điều này **không tự chứng minh** họ là một người cụ thể ngoài đời, đang làm đúng vị trí công việc, hoặc có quyền đối với một tổ chức. Nếu cần mức bảo đảm danh tính cao hơn, phải có quy trình kiểm chứng danh tính phù hợp với rủi ro và bối cảnh.

Một liên kết kích hoạt hoặc lời mời nên:

- Có giá trị ngẫu nhiên đủ khó đoán, chỉ dùng một lần, có thời hạn và gắn đúng mục đích/tài khoản.
- Được truyền qua kênh phù hợp; không xuất hiện trong log, công cụ phân tích hoặc URL chuyển hướng bên ngoài.
- Được xử lý ở phía server bằng kiểm tra trạng thái và tiêu thụ nguyên tử để chống dùng lại.
- Không tự động trao quyền cao nếu bước chứng minh danh tính hoặc phê duyệt chưa hoàn tất.

Ví dụ, một lời mời làm quản trị viên được gửi nhầm đến email ngoài tổ chức **không nên** ngay lập tức cho phép người nhận truy cập toàn bộ dữ liệu khi chỉ nhấp liên kết. Quy trình có thể đòi hỏi xác minh thêm qua hệ thống danh tính tổ chức và phê duyệt phù hợp.

## 5. Kích hoạt và gắn phương thức xác thực

**Kích hoạt tài khoản** là lúc hệ thống chấp nhận một tập điều kiện trước khi cho phép truy cập. Điều kiện có thể gồm xác minh email, chấp nhận lời mời, đăng ký phương thức xác thực và hoàn thành bước phê duyệt. Không nên dùng một boolean duy nhất để đại diện cho mọi điều kiện khi các điều kiện đó có mức bảo đảm khác nhau.

| Phương thức | Việc cần quản lý trong chu kỳ tài khoản | Rủi ro điển hình |
|---|---|---|
| Mật khẩu | Thiết lập, thay đổi, kiểm tra mật khẩu lộ, đặt lại khi mất | Tái sử dụng, đoán mật khẩu, phishing |
| TOTP/MFA | Đăng ký thiết bị, chứng minh hoạt động, thay thế/thu hồi, mã dự phòng | Lừa lấy OTP, mất thiết bị, reset MFA yếu |
| Passkey/WebAuthn | Đăng ký khóa công khai, ràng buộc đúng miền, quản lý thiết bị/credential | Thiết bị bị chiếm quyền, thêm khóa trái phép, phục hồi yếu |
| Chứng chỉ/mTLS | Cấp phát, bảo vệ khóa riêng, gia hạn và thu hồi chứng chỉ | Rò rỉ khóa, chứng chỉ hết hạn hoặc cấp sai chủ thể |
| Khóa API/bí mật dịch vụ | Cấp với phạm vi nhỏ, lưu bí mật, xoay vòng và thu hồi | Lộ qua mã nguồn, pipeline hoặc log |

Mật khẩu phải được lưu bằng **thuật toán băm mật khẩu chuyên dụng có salt**, chẳng hạn Argon2id theo cấu hình phù hợp, thay vì lưu rõ hoặc dùng hàm băm nhanh thông thường. Passkey/WebAuthn sử dụng cặp khóa và kiểm tra gắn với miền nên có khả năng chống phishing tốt hơn OTP có thể bị chuyển tiếp. Tuy vậy, việc **thêm passkey mới** phải được bảo vệ cẩn thận: nếu người lạ chiếm một phiên rồi đăng ký khóa của mình, họ có thể duy trì quyền truy cập lâu dài.

Với các phương thức dự phòng, mã khôi phục nên đủ ngẫu nhiên, chỉ dùng một lần và được lưu ở dạng giảm thiểu nguy cơ lộ. Hệ thống cũng phải có cách thu hồi phương thức xác thực cũ khi người dùng mất thiết bị hoặc khi phát hiện chiếm quyền.

## 6. Trạng thái hoạt động: đăng nhập chỉ là điểm bắt đầu

Ở trạng thái hoạt động, người dùng xác thực bằng credential đã đăng ký. Hệ thống cần đánh giá thêm trạng thái tài khoản, rủi ro của yêu cầu và điều kiện truy cập tài nguyên.

~~~mermaid
flowchart LR
    C["Client không tin cậy"] -->|"Credential / challenge response"| A["Dịch vụ xác thực"]
    A --> V{"Bằng chứng và trạng thái tài khoản hợp lệ?"}
    V -->|"Không"| D["Từ chối và ghi nhận sự kiện"]
    V -->|"Có"| S["Phát hành phiên/token có giới hạn"]
    S -->|"Yêu cầu tài nguyên"| P["API tin cậy"]
    P --> Q{"Phiên/token còn hợp lệ và có quyền?"}
    Q -->|"Không"| R["Từ chối"]
    Q -->|"Có"| T["Thực hiện hành động"]
~~~

Một số biện pháp cho giai đoạn hoạt động:

1. **Chống lạm dụng đăng nhập:** giới hạn tốc độ và số lần thử theo nhiều tín hiệu, phát hiện credential stuffing, kiểm tra bất thường và ngăn dò tài khoản. Dùng phản hồi lỗi phù hợp để hạn chế tiết lộ sự tồn tại của username/email.
2. **Chống phishing:** ưu tiên phương thức chống phishing cho tài nguyên có rủi ro cao; không xem mọi loại MFA có mức bảo vệ tương đương.
3. **Chống replay:** dùng TLS, challenge/nonce đúng giao thức, giới hạn thời hạn và cơ chế chống phát lại khi cần; không tái sử dụng liên kết hoặc mã một lần.
4. **Bảo vệ phiên:** cookie web nên có Secure, HttpOnly và SameSite phù hợp; chống session fixation, XSS và CSRF theo ngữ cảnh; bảo vệ token khỏi URL/log.
5. **Phân quyền liên tục:** mỗi yêu cầu API phải xác định chủ thể và kiểm tra quyền trên tài nguyên cụ thể; tài khoản hợp lệ không có nghĩa được truy cập mọi dữ liệu.
6. **Xác thực tăng cường (step-up):** yêu cầu bằng chứng mới hoặc mạnh hơn trước thao tác như thay email khôi phục, thêm phương thức xác thực hay chuyển tiền.

### Trạng thái tài khoản ảnh hưởng đến token như thế nào?

Giả sử người dùng có access token còn hạn 20 phút, nhưng tài khoản vừa bị đình chỉ. Nếu API chỉ kiểm tra chữ ký và hạn của JWT, token **có thể vẫn được chấp nhận** trong thời gian còn hiệu lực, tùy kiến trúc. Các hệ thống có yêu cầu thu hồi nhanh phải tính đến thời hạn token ngắn, kiểm tra trạng thái/phiên ở server, danh sách thu hồi hoặc cơ chế tương đương.

Đừng nhầm **ID token** trong OpenID Connect với **access token** dùng để gọi API. API phải kiểm tra loại token phù hợp, issuer, audience, thời hạn, phạm vi và quyền truy cập. Với phiên phía server, vô hiệu hóa trạng thái phiên có thể chặn yêu cầu kế tiếp nhanh hơn, nhưng cần bảo đảm các dịch vụ dùng chung trạng thái nhận được cập nhật.

## 7. Bảo trì tài khoản: thay đổi có thể nhạy cảm hơn đăng nhập

Khi tài khoản đang hoạt động, chủ thể có thể thay đổi mật khẩu, địa chỉ liên hệ, thiết bị tin cậy, passkey, yếu tố MFA, tên hiển thị hoặc quyền trong tổ chức. Không phải mọi thay đổi có mức rủi ro bằng nhau.

| Thay đổi | Điều kiện an toàn nên xem xét | Sau khi thay đổi |
|---|---|---|
| Đổi tên hiển thị | Phiên và quyền chỉnh sửa hợp lệ | Lưu lịch sử nếu nghiệp vụ cần |
| Đổi mật khẩu | Xác thực lại khi phù hợp; bảo vệ mật khẩu mới | Cân nhắc thu hồi phiên/refresh token cũ và thông báo |
| Thay email chính | Xác minh quyền kiểm soát email mới; step-up cho tác vụ nhạy cảm | Thông báo qua kênh cũ nếu phù hợp; rà soát cơ chế khôi phục |
| Thêm passkey hoặc thiết bị MFA | Chứng minh quyền kiểm soát tài khoản ở mức mạnh, xác nhận ý định | Ghi nhận credential và thông báo thay đổi |
| Xóa phương thức MFA cuối cùng | Không để quy trình hạ cấp vượt chính sách | Có phương án thay thế/khôi phục được kiểm soát |
| Cấp quyền quản trị | Phê duyệt có thẩm quyền và kiểm tra phạm vi | Cập nhật quyền và phiên/token đang tồn tại theo chính sách |
| Liên kết nhà cung cấp danh tính mới | Xác thực lại tài khoản đích và bằng chứng từ bên liên kết | Ghi nhận liên kết, cung cấp cách ngắt liên kết an toàn |

Đặc biệt, **địa chỉ email không phải bằng chứng bất biến của cùng một con người**. Một tổ chức có thể tái cấp email khi nhân viên nghỉ việc. Khi liên kết tài khoản với nhà cung cấp danh tính (IdP), nên dựa trên định danh ổn định trong phạm vi của nhà phát hành, ví dụ cặp **issuer + subject (iss, sub)** của OpenID Connect, sau khi xác minh token đúng cách. Tự động hợp nhất hai tài khoản chỉ vì email giống nhau có thể tạo lỗi chiếm quyền tài khoản (account takeover).

### Ranh giới khi liên kết tài khoản

Ví dụ: một người đang đăng nhập bằng mật khẩu muốn liên kết tài khoản Google hoặc IdP doanh nghiệp. Ứng dụng cần xác nhận **người đó đang kiểm soát tài khoản hiện tại** và **đang kiểm soát danh tính mới**, rồi ghi lại ý định liên kết. Một email trùng khớp do bên ngoài gửi về không phải là phép ủy quyền để ghép hai hồ sơ.

## 8. Khôi phục: đường vòng phải được bảo vệ

Người dùng có thể quên mật khẩu, mất khóa bảo mật, đổi điện thoại hoặc không còn quyền truy cập email. **Khôi phục tài khoản** là quy trình cấp lại khả năng đăng nhập; vì vậy nó có thể tương đương với **cấp quyền kiểm soát tài khoản cho một chủ thể mới** nếu bị lạm dụng.

### Luồng đặt lại mật khẩu tham khảo

1. Người dùng yêu cầu khôi phục. Phản hồi tránh tiết lộ tài khoản có tồn tại hay không; giới hạn tần suất và giám sát lạm dụng.
2. Server phát sinh mã ngẫu nhiên đủ mạnh, gắn với đúng tài khoản và mục đích khôi phục, có thời hạn ngắn và chỉ được dùng một lần. Có thể lưu dạng băm để giảm tác hại khi kho lưu trữ rò rỉ.
3. Mã được gửi qua kênh mà chính sách cho phép. Hệ thống phải nhận thức rằng kiểm soát email không luôn bảo đảm danh tính ở mức cao.
4. Server kiểm tra mã, trạng thái tài khoản và rủi ro, sau đó cho phép thiết lập lại credential theo chính sách. Việc sử dụng mã phải được đánh dấu **nguyên tử** để hai yêu cầu đồng thời không dùng lại cùng một mã.
5. Sau khôi phục, hệ thống thông báo sự kiện qua kênh phù hợp, thu hồi hoặc rà soát phiên/refresh token cũ, và xem xét các phương thức xác thực đã thêm gần đây.

Với tài khoản rủi ro cao, **chỉ một đường dẫn qua email** có thể không đạt mức bảo vệ cần thiết. Có thể cần recovery code đã cấp trước, phương thức xác thực khác còn hoạt động, xác minh danh tính có kiểm soát hoặc quy trình hỗ trợ được giám sát. Không nên gửi mật khẩu mới qua email hoặc cho nhân viên hỗ trợ truy cập trực tiếp vào mật khẩu của người dùng.

### Các lỗ hổng khôi phục thường bị bỏ qua

- Hủy MFA chỉ dựa trên yêu cầu qua điện thoại hoặc thông tin cá nhân dễ biết.
- Cho phép thêm email khôi phục mà không cần xác thực lại.
- Token khôi phục sống quá lâu, dùng nhiều lần hoặc xuất hiện trong log.
- Reset mật khẩu nhưng vẫn giữ phiên kẻ tấn công hoặc credential mới cài.
- Dựa vào câu hỏi bảo mật có câu trả lời có thể tìm thấy trên mạng.
- Khôi phục tài khoản đã bị đình chỉ theo quy trình thông thường, vượt qua quyết định của quản trị viên.

**Nguyên tắc:** cơ chế khôi phục và hỗ trợ phải đạt mức bảo đảm phù hợp với tài nguyên mà tài khoản truy cập. MFA mạnh sẽ mất nhiều giá trị nếu có thể bỏ qua bằng một thủ tục phục hồi yếu.

## 9. Khóa, đình chỉ và phản ứng sự cố

Không nên gộp tất cả các trạng thái không hoạt động thành một thao tác. Hệ thống cần xác định:

| Tình huống | Trạng thái/phản ứng có thể phù hợp | Điểm cần xác minh |
|---|---|---|
| Nhiều lần nhập sai mật khẩu | Giới hạn yêu cầu, thách thức tăng cường hoặc khóa tạm thời tùy chính sách | Tránh để kẻ tấn công khóa tài khoản người khác hàng loạt |
| Phát hiện phiên từ nguồn bất thường | Yêu cầu xác thực lại hoặc tạm đình chỉ phiên | Thu hồi phiên đáng ngờ, bảo toàn nhật ký |
| Người dùng báo mất thiết bị MFA | Thu hồi credential bị mất; dùng luồng khôi phục an toàn | Không cho đăng ký thiết bị mới chỉ bằng lời khai |
| Có bằng chứng tài khoản bị chiếm quyền | Đình chỉ/giới hạn truy cập và điều tra | Rà soát phương thức đăng nhập, token, thay đổi quyền |
| Nhân viên nghỉ việc | Vô hiệu hóa theo quy trình nguồn nhân sự | Thu hồi quyền, phiên, tài khoản liên kết và API key |
| Tài khoản không dùng lâu ngày | Đánh giá rủi ro, thông báo, khóa hoặc xóa theo chính sách | Xem nghĩa vụ lưu giữ và nhu cầu khôi phục hợp lệ |

Khi xảy ra sự cố, một quy trình thông thường gồm: **ngăn truy cập tiếp diễn → xác minh quyền sở hữu → thu hồi bằng chứng bị lộ → sửa cấu hình và quyền → khôi phục có kiểm soát → theo dõi tái diễn**. Việc thay mật khẩu đơn lẻ có thể không đủ nếu kẻ tấn công đã thêm passkey, tạo refresh token hoặc liên kết một IdP mới.

Mở khóa phải có **điều kiện**: kết thúc thời hạn, xác thực lại, kiểm tra chống lạm dụng hoặc phê duyệt có thẩm quyền. Không nên cho phép mọi người dùng tự đưa trạng thái đình chỉ vì sự cố về hoạt động chỉ bằng đường “quên mật khẩu”.

## 10. Vô hiệu hóa, xóa và lưu trữ

### Vô hiệu hóa (deactivation)

Một tài khoản vô hiệu hóa thường không được tiếp tục xác thực hay sử dụng tài nguyên. Tùy kiến trúc, cần:

1. Chặn đăng nhập mới và các thao tác khôi phục không được phép.
2. Thu hồi phiên server, refresh token, khóa API và credential hoặc chứng chỉ liên quan khi cần.
3. Đánh giá access token chưa hết hạn, bộ nhớ đệm quyền, phiên SSO và các dịch vụ phụ thuộc.
4. Thu hồi vai trò, nhóm, ủy quyền và quyền truy cập dữ liệu.
5. Ghi lại ai/cơ chế nào thực hiện, căn cứ, thời điểm và kết quả; bảo vệ nhật ký.

**Đăng xuất ở một ứng dụng** chưa chắc đăng xuất khỏi nhà cung cấp danh tính hay các dịch vụ khác. Sự kiện vô hiệu hóa cần được truyền tới các hệ thống liên kết theo giao thức và chính sách phù hợp; phải chấp nhận và quản trị độ trễ đồng bộ nếu có.

### Xóa hoặc lưu trữ

Xóa tài khoản có thể bao gồm xóa dữ liệu nhận diện, mối liên kết, token còn lưu, bản ghi phụ thuộc và bí mật. Tuy nhiên, một số dữ liệu nghiệp vụ hoặc nhật ký có thể cần được giữ trong thời hạn cho phép hoặc bắt buộc theo chính sách/pháp luật áp dụng. Thiết kế cần tách **khả năng đăng nhập**, **dữ liệu cần giữ** và **dữ liệu được phép xóa**.

Không nên tái sử dụng ID tài khoản nội bộ đã xóa để đại diện cho người khác; các bảng nghiệp vụ, bản ghi kiểm toán và liên kết cũ có thể vô tình trỏ sang chủ thể mới. Cần quy định xử lý dữ liệu trong bản sao lưu, bộ nhớ đệm, hệ thống phân tích và nhà cung cấp bên ngoài.

**Tái kích hoạt** một tài khoản đã vô hiệu hóa là một hành động nhạy cảm. Người thực hiện phải có thẩm quyền, xác minh trạng thái nguồn, làm mới credential theo chính sách và đánh giá lại quyền thay vì tự động phục hồi mọi quyền cũ.

## 11. Ranh giới tin cậy và các bất biến cần giữ

Trong thiết kế, **bất biến (invariant)** là điều phải luôn đúng bất kể API nào hay luồng nào tạo ra thay đổi.

| Bất biến | Vì sao cần |
|---|---|
| Tài khoản không ở trạng thái cho phép thì không được cấp phiên mới | Tránh đăng nhập bằng credential cũ của tài khoản bị vô hiệu hóa |
| Credential phải gắn đúng tài khoản và có trạng thái hợp lệ | Tránh dùng nhầm credential đã thu hồi hoặc thuộc người khác |
| Thay đổi credential/định danh nhạy cảm phải có bằng chứng và ý định phù hợp | Ngăn chiếm quyền qua trang cài đặt hoặc CSRF |
| Token phục hồi, kích hoạt, lời mời chỉ dùng đúng mục đích và một lần | Chống replay và nhầm ngữ cảnh |
| Tài khoản hợp lệ vẫn cần kiểm tra quyền theo tài nguyên | Ngăn truy cập dữ liệu người khác |
| Vô hiệu hóa phải có tác động đến phiên/quyền theo yêu cầu hệ thống | Tránh trạng thái CSDL và khả năng truy cập thực tế mâu thuẫn |
| Chuyển trạng thái phải có dấu vết và chống ghi đè đồng thời | Giúp điều tra và hạn chế tranh chấp/race condition |

Một client có thể gửi yêu cầu “đặt trạng thái tài khoản = hoạt động”, nhưng server không được tin giá trị do client cung cấp. **Quyền chuyển trạng thái** phải được đánh giá từ danh tính, vai trò, nguồn sự kiện và trạng thái hiện tại; việc cập nhật phải thực hiện nguyên tử khi cần.

### Mã giả cho chuyển trạng thái

~~~typescript
// Mã giả minh họa chính sách, không phải triển khai production.
async function activateAccount(actor, accountId, proof) {
  return transaction(async (tx) => {
    const account = await tx.getAccountForUpdate(accountId);
    if (!account || account.status !== "PENDING") {
      return { ok: false, reason: "invalid_transition" };
    }

    const verified = await tx.consumeActivationProof({
      accountId,
      proof,
      purpose: "ACTIVATE",
    });
    if (!verified) return { ok: false, reason: "invalid_proof" };

    if (!(await mayActivate(actor, account, verified))) {
      return { ok: false, reason: "not_authorized" };
    }

    await tx.setAccountStatus(accountId, "ACTIVE");
    await tx.appendAuditEvent({
      action: "ACCOUNT_ACTIVATED",
      accountId,
      actorId: actor?.id ?? "self-service",
    });
    return { ok: true };
  });
}
~~~

Ví dụ dùng giao dịch để tránh kích hoạt hai lần và kiểm tra rõ trạng thái nguồn, bằng chứng, quyền và nhật ký. Trong triển khai thực tế, cần tính đến khả năng lỗi, tính lặp an toàn (idempotency), khóa đồng thời và việc gửi thông báo sau khi giao dịch đã được xác nhận. Không nên chép nguyên mã giả này làm cơ chế xác thực hoàn chỉnh.

### Dữ liệu tối thiểu phục vụ kiểm soát

Một mô hình dữ liệu thường tách các đối tượng sau:

~~~text
Account
  id                  // ID nội bộ bất biến
  status              // PENDING, ACTIVE, SUSPENDED, DISABLED...
  createdAt, updatedAt, disabledAt

AccountIdentifier
  accountId, type, value, verifiedAt

Authenticator
  id, accountId, type, state, enrolledAt, revokedAt

Session / RefreshTokenRecord
  id, accountId, createdAt, expiresAt, revokedAt

AccountLifecycleEvent
  accountId, actorId, action, reason, occurredAt
~~~

Đây là sơ đồ khái niệm; trường thực tế phụ thuộc công nghệ. Không lưu mật khẩu hay token bí mật ở dạng rõ trong các bản ghi ví dụ; giới hạn thông tin nhạy cảm trong sự kiện kiểm toán. Dịch vụ dùng access token tự chứa có thể cần thêm phiên bản trạng thái, introspection hoặc cơ chế thu hồi phù hợp.

## 12. Trường hợp đặc biệt: tài khoản dịch vụ và đăng nhập liên kết

### Tài khoản dịch vụ

Tài khoản dịch vụ không có con người nhập mật khẩu mỗi ngày nhưng vẫn có chu kỳ tài khoản: được cấp bởi chủ sở hữu có thẩm quyền, nhận định danh máy/chứng chỉ hoặc khóa, được giới hạn quyền, xoay vòng bí mật và bị thu hồi khi ứng dụng ngừng hoạt động. Nên ưu tiên cơ chế danh tính công việc tạm thời có quản lý khi nền tảng hỗ trợ để giảm bí mật tồn tại lâu.

Không dùng chung một tài khoản quản trị cho nhiều dịch vụ nếu có thể tránh: khó truy vết, thu hồi từng hệ thống và áp dụng quyền tối thiểu. Khi người vận hành nghỉ việc, kiểm tra những bí mật, tài khoản và tích hợp họ từng sở hữu hoặc có quyền quản lý.

### Đăng nhập liên kết (federation/SSO)

Trong SSO, ứng dụng phụ thuộc một nhà cung cấp danh tính để xác thực nhưng vẫn chịu trách nhiệm với **tài khoản cục bộ, ánh xạ danh tính và phân quyền tài nguyên**. Cần quản lý các sự kiện như người dùng được thêm vào nhóm, chuyển bộ phận, đổi email, bị vô hiệu hóa ở IdP hoặc bị thu hồi quyền tại ứng dụng.

Không mặc nhiên coi logout khỏi ứng dụng là đã thu hồi mọi phiên IdP. Cũng không được tự động ghép hai tài khoản từ hai tổ chức chỉ vì chung tên hiển thị hoặc email chưa được xác minh.

## 13. Tình huống thực hành: nhân viên chuyển bộ phận rồi nghỉ việc

**Bối cảnh:** Một công ty có cổng nội bộ. Nhân viên Lan được cấp tài khoản khi gia nhập, đăng nhập bằng SSO và passkey. Lan chuyển từ bộ phận kinh doanh sang tài chính, sau đó nghỉ việc.

| Thời điểm | Chuyển đổi vòng đời | Hành động hệ thống cần xem xét |
|---|---|---|
| Ngày gia nhập | Cấp phát → chờ kích hoạt | Gắn đúng định danh nhân viên, xác minh lời mời, đăng ký passkey |
| Lần đăng nhập đầu | Chờ kích hoạt → hoạt động | Xác minh IdP/passkey và quyền đầu tiên đúng vai trò |
| Chuyển bộ phận | Hoạt động, thay đổi quyền | Gỡ quyền dữ liệu kinh doanh, cấp quyền tài chính khi được duyệt |
| Mất điện thoại | Thay credential/khôi phục | Xác minh lại chủ thể, thu hồi phương thức mất, cấp phương thức mới |
| Nghỉ việc | Hoạt động → vô hiệu hóa | Ngăn SSO vào ứng dụng, thu hồi phiên/token và quyền ở các hệ thống liên kết |
| Hết thời hạn lưu giữ | Vô hiệu hóa → xóa/lưu trữ | Xử lý dữ liệu, bản sao và nhật ký theo chính sách |

**Hai lỗi thiết kế cần phát hiện:**

1. Quyền kinh doanh được lưu cứng trong JWT còn hiệu lực sau khi Lan chuyển sang bộ phận tài chính. API không kiểm tra lại chính sách, nên Lan vẫn truy cập dữ liệu cũ. Cần có thời hạn token và phương án làm mới/thu hồi quyền phù hợp với yêu cầu thay đổi.
2. Sau khi tài khoản bị vô hiệu hóa, liên kết “quên mật khẩu” vẫn cho phép kích hoạt tài khoản và cấp phiên mới. Luồng khôi phục đang vượt qua chuyển trạng thái có thẩm quyền. Cần kiểm tra trạng thái tài khoản trước khi chấp nhận khôi phục.

### Bài tập ngắn

Hãy vẽ chuỗi trạng thái cho tài khoản khách hàng có mật khẩu + TOTP khi họ: (1) tạo tài khoản, (2) xác minh email, (3) mất điện thoại, (4) đặt lại mật khẩu và (5) yêu cầu đóng tài khoản. Ở mỗi bước, trả lời:

- Ai khởi tạo hành động, họ chứng minh quyền kiểm soát bằng gì?
- Server được phép chuyển từ trạng thái nào sang trạng thái nào?
- Có phải thu hồi phiên, token hoặc authenticator cũ không?
- Nếu nhận cùng yêu cầu hai lần hoặc nhận hai yêu cầu đồng thời, điều gì phải giữ nguyên?
- Sự kiện nào cần ghi log và người dùng cần nhận thông báo gì?

Không có một quy trình chung phù hợp mọi hệ thống; hãy giải thích lựa chọn dựa trên độ nhạy của tài khoản và các tài nguyên nó truy cập.

## 14. Checklist rà soát chu kỳ tài khoản

- [ ] Phân biệt rõ trạng thái tài khoản với trạng thái credential và phiên/token.
- [ ] ID nội bộ không phụ thuộc email hoặc username có thể tái cấp, đổi chủ.
- [ ] Tạo lập, kích hoạt và mời người dùng có điều kiện, thời hạn và hạn chế lạm dụng.
- [ ] Xác minh email được hiểu đúng là quyền kiểm soát kênh liên hệ, không mặc nhiên là danh tính ngoài đời.
- [ ] Đăng ký, thay thế, thu hồi mật khẩu/MFA/passkey/chứng chỉ có kiểm tra quyền và ý định.
- [ ] Đăng nhập chống phishing, replay, credential stuffing và dò tài khoản ở mức phù hợp.
- [ ] Mỗi yêu cầu tài nguyên kiểm tra cả trạng thái phiên/token lẫn phân quyền tại server.
- [ ] Đổi email, thêm authenticator, liên kết IdP và cấp quyền cao có xác thực lại/step-up thích hợp.
- [ ] Khôi phục không dùng đường yếu để vượt qua MFA hoặc trạng thái đình chỉ.
- [ ] Khóa và đình chỉ có quy trình mở khóa có thẩm quyền, tránh bị lạm dụng để gây từ chối dịch vụ.
- [ ] Vô hiệu hóa có kế hoạch thu hồi phiên, refresh token, API key, quyền và tích hợp liên quan.
- [ ] Xóa/lưu trữ dữ liệu, bản sao và nhật ký theo chính sách; không tái sử dụng ID cũ.
- [ ] Các chuyển trạng thái chống sử dụng mã một lần hai lần, ghi đè đồng thời và có audit.

## Ghi nhớ

Chu kỳ tài khoản nối liền **con người hoặc dịch vụ**, **bằng chứng xác thực**, **phiên/token**, **quyền truy cập** và **trạng thái quản trị**. Tại mọi chuyển đổi, hãy xác định: **ai yêu cầu**, **bằng chứng nào đủ mạnh**, **server cho phép chuyển trạng thái nào**, **quyền/phiên nào phải thay đổi** và **sự kiện nào cần được ghi nhận**.

Một tài khoản được bảo vệ tốt không chỉ đăng nhập an toàn. Nó còn phải được tạo đúng người, gắn đúng credential, duy trì quyền hợp lệ, khôi phục có kiểm soát và chấm dứt truy cập đúng lúc.
