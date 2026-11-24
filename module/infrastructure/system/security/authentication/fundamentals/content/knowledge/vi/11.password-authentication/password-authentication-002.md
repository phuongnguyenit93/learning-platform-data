# Password policy — Xây dựng chính sách mật khẩu an toàn và dễ sử dụng

**Password policy** là tập hợp quy tắc và kiểm soát xác định cách người dùng tạo, chọn, lưu trữ, sử dụng, thay đổi và khôi phục mật khẩu. Một chính sách tốt cần giảm khả năng đoán, tái sử dụng và đánh cắp mật khẩu, đồng thời hỗ trợ người dùng sử dụng mật khẩu dài, độc nhất và password manager. Chỉ yêu cầu thêm chữ hoa, chữ số và ký tự đặc biệt không đủ để bảo vệ tài khoản.

Trong hệ thống authentication, mật khẩu là credential thuộc nhóm **điều người dùng biết (knowledge)**. Máy chủ kiểm tra mật khẩu để xác thực tài khoản, sau đó tạo phiên hoặc token theo chính sách. Mật khẩu không tự chứng minh danh tính pháp lý, không quyết định quyền truy cập và không chống phishing. Chính sách phải kết hợp kiểm soát ở thời điểm tạo mật khẩu, lưu trữ verifier, đăng nhập, thay đổi, phát hiện lạm dụng, MFA và recovery.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Thiết kế quy tắc độ dài, danh sách mật khẩu bị cấm, kiểm tra mật khẩu đã lộ và hỗ trợ password manager.
2. Giải thích vì sao độ dài và tính độc nhất quan trọng hơn quy tắc thành phần cứng nhắc.
3. Chọn cách lưu password verifier bằng thuật toán dẫn xuất mật khẩu có salt và chi phí phù hợp.
4. Thiết kế luồng đăng ký, đăng nhập, đổi mật khẩu, reset mật khẩu và thu hồi phiên.
5. Phòng chống brute force, password spraying, credential stuffing, phishing và rò rỉ thông tin tài khoản.
6. Phân biệt chính sách mật khẩu cho SFA với mật khẩu là một phần của MFA.
7. Viết tiêu chí kiểm thử và vận hành chính sách mật khẩu mà không làm người dùng hợp lệ bị khóa ngoài.

## 2. Password policy giải quyết vấn đề gì?

Mật khẩu được dùng rộng rãi vì dễ triển khai và không đòi hỏi thiết bị chuyên biệt. Nhưng người dùng thường phải ghi nhớ quá nhiều mật khẩu, dẫn tới những hành vi có thể dự đoán:

- Dùng một mật khẩu cho nhiều dịch vụ.
- Chọn chuỗi ngắn, phổ biến, tên riêng hoặc mẫu bàn phím.
- Thêm một ký tự hoặc thay số theo mùa khi hệ thống bắt đổi định kỳ.
- Ghi mật khẩu vào nơi không an toàn hoặc chia sẻ qua tin nhắn.
- Dễ bị lừa nhập mật khẩu vào website giả mạo.
- Dùng mật khẩu đã lộ trong một vụ vi phạm ở dịch vụ khác.

Kẻ tấn công cũng có nhiều cách thử: đoán trực tuyến, dùng danh sách mật khẩu rò rỉ, thử một mật khẩu phổ biến trên nhiều tài khoản, hoặc lấy password verifier từ database để đoán ngoại tuyến. Chính sách cần xác định **mối đe dọa nào được xử lý ở từng lớp**.

| Mối đe dọa | Mục tiêu của chính sách |
| --- | --- |
| Mật khẩu yếu/dễ đoán | Khuyến khích mật khẩu dài, chặn mật khẩu phổ biến và dễ dự đoán. |
| Tái sử dụng mật khẩu | Hỗ trợ password manager và kiểm tra mật khẩu đã bị lộ. |
| Brute force/password spraying | Giới hạn tốc độ, phát hiện hành vi và bảo vệ endpoint đăng nhập. |
| Credential stuffing | Phát hiện credential đã lộ, giảm khả năng dùng lại và áp dụng MFA. |
| Database bị đánh cắp | Lưu verifier bằng KDF phù hợp, salt riêng và tham số chi phí cao. |
| Phishing | Khuyến khích passkey/phương thức chống phishing; mật khẩu đơn lẻ không thể tự chống phishing. |
| Recovery bị lạm dụng | Bảo vệ reset token, xác minh yêu cầu và thu hồi phiên thích hợp. |

## 3. Nguyên tắc cốt lõi: dài, độc nhất và dễ dùng

### 3.1. Ưu tiên độ dài

Mật khẩu dài làm tăng không gian tìm kiếm nếu được chọn đủ ngẫu nhiên. Một chuỗi ngắn nhưng có nhiều loại ký tự vẫn có thể dễ đoán nếu theo mẫu phổ biến, ví dụ một từ điển cộng với năm sinh và dấu chấm than.

**Độ dài không đồng nghĩa với độ khó đoán tuyệt đối.** Một câu dài trích từ lời bài hát hoặc thông tin công khai vẫn có thể xuất hiện trong danh sách từ điển. Cần kết hợp độ dài với danh sách chặn, kiểm tra mật khẩu bị lộ và hướng dẫn người dùng chọn mật khẩu độc nhất.

Theo **NIST SP 800-63B-4 (2025)**, khi hệ thống áp dụng bộ hướng dẫn này, verifier phải yêu cầu mật khẩu dài ít nhất **15 ký tự** nếu mật khẩu là yếu tố duy nhất; verifier **có thể** cho phép tối thiểu **8 ký tự** nếu mật khẩu chỉ được dùng như một phần của MFA. Verifier cũng phải hỗ trợ độ dài tối đa ít nhất **64 ký tự**. Mốc 8 ký tự là quyền cho phép trong ngữ cảnh MFA, không phải khuyến nghị hạ mọi mật khẩu xuống mức đó. Có thể đặt yêu cầu nghiêm hơn theo rủi ro và quy định áp dụng. **Luôn xác định đúng phiên bản và phạm vi tiêu chuẩn trước khi tuyên bố tuân thủ.**

### 3.2. Cho phép mật khẩu dài và passphrase

Cho phép người dùng tạo passphrase gồm nhiều từ, dấu cách và ký tự Unicode nếu nền tảng hỗ trợ an toàn. Hệ thống không nên từ chối một mật khẩu dài chỉ vì nó vượt giới hạn ngắn tùy tiện của giao diện.

Cần xác định rõ cách đo độ dài:

- Dùng cùng một quy tắc đo ở giao diện, API và verifier; tránh một thành phần đếm byte UTF-8 trong khi thành phần khác đếm code point.
- Không cắt cụt mật khẩu ở một độ dài cố định mà không thông báo; xác minh toàn bộ giá trị đã nhận.
- Giới hạn trên phải đủ lớn để ngăn request quá tải hoặc lạm dụng tài nguyên, nhưng không được biến thành giới hạn thấp làm giảm chất lượng mật khẩu.
- Nếu chuẩn hóa Unicode, phải áp dụng nhất quán trong đăng ký, xác minh, đổi và reset; không tự ý thay đổi mật khẩu cũ khi chưa có kế hoạch tương thích.
- Không trim hoặc đổi chữ hoa/chữ thường của mật khẩu trừ khi một quy tắc chuẩn hóa được công bố và áp dụng nhất quán. Mật khẩu thường phân biệt chữ hoa/chữ thường.

### 3.3. Tránh quy tắc thành phần cứng nhắc

Yêu cầu mọi mật khẩu phải có ít nhất một chữ hoa, một chữ thường, một số và một ký tự đặc biệt thường khiến người dùng chọn mẫu dễ đoán như Password1! hoặc thay ký tự theo quy luật. Các quy tắc này không đảm bảo entropy và có thể cản trở password manager tạo chuỗi ngẫu nhiên tốt.

Nên tập trung vào:

- Độ dài tối thiểu theo mức rủi ro và chuẩn áp dụng.
- Danh sách chặn mật khẩu phổ biến, dễ đoán hoặc đã bị lộ.
- Hỗ trợ passphrase, khoảng trắng và password manager.
- Kiểm tra mật khẩu mới có trùng mật khẩu hiện tại hoặc lịch sử theo chính sách.
- Kiểm soát đăng nhập và MFA phù hợp.

### 3.4. Không bắt đổi mật khẩu định kỳ nếu không có lý do

Ép đổi mật khẩu sau mỗi 30/60/90 ngày có thể khiến người dùng chỉ thay đổi rất nhỏ, ghi mật khẩu ra giấy hoặc lặp lại chu kỳ dễ đoán. Nên yêu cầu đổi khi có bằng chứng hoặc lý do hợp lý, chẳng hạn:

- Có dấu hiệu mật khẩu bị lộ hoặc được sử dụng trái phép.
- Mật khẩu xuất hiện trong danh sách credential đã bị xâm phạm.
- Người dùng chủ động đổi hoặc nghi ngờ tài khoản bị chiếm.
- Quản trị viên cần xử lý sự cố có căn cứ.
- Chính sách pháp lý/hợp đồng áp dụng yêu cầu cụ thể.

Nếu phải đổi do sự cố, cần hướng dẫn người dùng tạo mật khẩu mới độc nhất và cân nhắc thu hồi phiên/token hiện có. Đổi mật khẩu không tự động thu hồi mọi access token đã phát hành nếu kiến trúc không hỗ trợ điều đó.

## 4. Định nghĩa chính sách cụ thể

Một chính sách nên được ghi thành quy tắc có thể kiểm thử, thay vì câu chung chung như “mật khẩu phải mạnh”.

| Thuộc tính | Quy tắc thiết kế gợi ý | Lý do |
| --- | --- | --- |
| Độ dài tối thiểu | Theo NIST SP 800-63B-4: 15 ký tự khi là yếu tố duy nhất; có thể là 8 khi chỉ là một phần của MFA; đánh giá thêm yêu cầu pháp lý và rủi ro. | Độ dài giúp tăng chi phí đoán. |
| Độ dài tối đa | Hỗ trợ độ dài tối đa ít nhất 64 ký tự theo NIST SP 800-63B-4, đồng thời đặt giới hạn request chống DoS hợp lý. | Không loại bỏ password manager và chuỗi ngẫu nhiên dài. |
| Bộ ký tự | Hỗ trợ Unicode và khoảng trắng nếu stack xử lý nhất quán. | Cho phép người dùng chọn passphrase tự nhiên. |
| Composition rules | Tránh bắt buộc mẫu chữ hoa/số/ký tự đặc biệt theo khuôn. | Tránh mẫu dễ đoán và trải nghiệm kém. |
| Blocklist | Chặn mật khẩu phổ biến, dễ đoán, mặc định của tổ chức và đã bị lộ. | Giảm mật khẩu yếu dù đủ độ dài. |
| Password reuse | Khuyến khích mật khẩu độc nhất; cân nhắc kiểm tra lịch sử theo yêu cầu tổ chức. | Giảm tác động credential stuffing. |
| Password manager | Cho phép paste, autofill và công cụ tạo mật khẩu. | Giúp người dùng tạo và quản lý bí mật độc nhất. |
| Thay đổi định kỳ | Không ép đổi theo lịch nếu không có căn cứ. | Tránh thay đổi hình thức và hành vi ghi chép không an toàn. |
| Reset | Token ngẫu nhiên, thời hạn ngắn, dùng một lần, giới hạn gửi/thử. | Tránh biến recovery thành lối tắt chiếm tài khoản. |
| Lưu trữ | KDF chuyên dụng, salt riêng, chi phí phù hợp và nâng cấp tham số. | Giảm tốc độ đoán ngoại tuyến khi database bị lộ. |
| Đăng nhập | Rate limit đa chiều, phát hiện lạm dụng, thông báo lỗi không tiết lộ tài khoản. | Giảm tấn công trực tuyến và enumeration. |

### 4.1. Blocklist mật khẩu

Blocklist nên bao gồm:

- Mật khẩu phổ biến, ví dụ các chuỗi mặc định thường gặp.
- Mật khẩu quá dễ đoán theo tên dịch vụ hoặc tên tổ chức.
- Mật khẩu chứa tên đăng nhập, tên miền, tên công ty hoặc thông tin công khai dễ liên hệ.
- Mật khẩu xuất hiện trong dữ liệu vi phạm đã biết, nếu có thể kiểm tra theo cách bảo vệ quyền riêng tư.
- Mẫu thay đổi nhỏ từ mật khẩu phổ biến, ví dụ thêm năm hiện tại hoặc một ký tự dấu câu.

Không cần tải toàn bộ danh sách mật khẩu bị lộ vào client. Có thể kiểm tra phía server hoặc dùng cơ chế truy vấn bảo vệ riêng tư, nhưng cần đánh giá rò rỉ qua API, log, cache và bên cung cấp. Không gửi mật khẩu rõ tới dịch vụ bên thứ ba tùy tiện.

### 4.2. Kiểm tra mật khẩu bị lộ

Khi người dùng chọn mật khẩu mới, hệ thống có thể kiểm tra xem mật khẩu có xuất hiện trong danh sách bị xâm phạm. Mục tiêu là ngăn bí mật đã phổ biến trong các vụ rò rỉ được dùng lại.

Nếu dùng dịch vụ tra cứu theo prefix/hash hoặc giải pháp tương tự, hãy hiểu rõ mô hình riêng tư: không truyền mật khẩu rõ; hạn chế thông tin có thể suy ra; không log dữ liệu tra cứu nhạy cảm; xử lý lỗi dịch vụ ngoài theo chính sách. Không nên từ chối mọi mật khẩu chỉ vì một dịch vụ tra cứu đang tạm thời không sẵn sàng, trừ khi policy rủi ro yêu cầu fail closed.

### 4.3. Mật khẩu độc nhất và password manager

Mỗi dịch vụ nên có mật khẩu riêng. Password manager giúp tạo chuỗi ngẫu nhiên, lưu trữ và điền tự động. Vì vậy ứng dụng cần:

- Cho phép paste vào trường mật khẩu.
- Không chặn autofill bằng thuộc tính hoặc JavaScript không cần thiết.
- Có nút hiển thị/ẩn mật khẩu khi người dùng cần kiểm tra nội dung.
- Dùng nhãn trường và autocomplete phù hợp như current-password, new-password.
- Không buộc người dùng nhập lại mật khẩu nhiều lần trong một quy trình không cần thiết.
- Không yêu cầu ghi nhớ hoặc trả lời câu hỏi bí mật như phương thức thay thế yếu.

## 5. Phân biệt chính sách SFA và MFA

Mật khẩu có thể là **yếu tố duy nhất** trong SFA hoặc là một phần của MFA. Điều này ảnh hưởng cách đặt độ dài tối thiểu và mức bảo đảm cần đạt, nhưng **không làm cho mật khẩu tự trở nên chống phishing**.

| Kịch bản | Mật khẩu đóng vai trò | Hệ quả chính sách |
| --- | --- | --- |
| Đăng nhập chỉ bằng mật khẩu | Yếu tố knowledge duy nhất | Cần chính sách mật khẩu mạnh và kiểm soát endpoint chặt; cân nhắc nâng lên MFA. |
| Mật khẩu + TOTP | Một yếu tố trong MFA | Mật khẩu vẫn phải được bảo vệ; TOTP có thể bị phishing thời gian thực. |
| Mật khẩu + passkey/khóa bảo mật | Có thể là nhiều yếu tố hoặc một authenticator đa yếu tố tùy cách xác minh | Xác định rõ UV, chính sách authenticator và cách kiểm tra bằng chứng. |
| Passkey không cần mật khẩu | Passwordless | Không suy ra SFA/MFA từ việc không nhập mật khẩu; đánh giá authenticator thực tế. |
| Mật khẩu + CAPTCHA | Vẫn là một yếu tố | CAPTCHA giảm tự động hóa, không phải yếu tố danh tính độc lập. |

Đối với tài khoản quản trị hoặc dữ liệu nhạy cảm, mật khẩu đơn lẻ thường không đủ. Cân nhắc passkey/WebAuthn chống phishing hoặc phương thức MFA phù hợp. Việc thêm MFA không làm mất nhu cầu kiểm soát mật khẩu: mật khẩu vẫn có thể bị dùng để chiếm tài khoản, khởi tạo giao dịch hoặc lạm dụng recovery.

## 6. Lưu mật khẩu an toàn: chỉ lưu password verifier

Máy chủ cần kiểm tra mật khẩu mà không phải lưu bản rõ. Không mã hóa mật khẩu để có thể giải mã lại, và không chỉ dùng hàm băm nhanh thông thường.

### 6.1. Salt và password KDF

**Salt** là giá trị ngẫu nhiên riêng cho mỗi mật khẩu, được lưu cùng verifier. Salt khiến hai tài khoản dùng cùng mật khẩu vẫn có giá trị verifier khác nhau và làm giảm hiệu quả bảng tra cứu tiền tính toán.

Dùng **password-based key derivation function (password KDF)** có chi phí tính toán/bộ nhớ được điều chỉnh để làm chậm việc đoán mật khẩu ngoại tuyến. Lựa chọn phổ biến tùy nền tảng:

- **Argon2id:** lựa chọn mạnh cho nhiều hệ thống mới khi thư viện và môi trường hỗ trợ.
- **scrypt:** KDF có chi phí bộ nhớ, phù hợp khi được hỗ trợ và cấu hình đúng.
- **bcrypt:** còn gặp ở hệ thống hiện hữu; cần chọn cost phù hợp và lưu ý giới hạn độ dài đầu vào của triển khai.
- **PBKDF2:** có thể cần trong môi trường yêu cầu thuật toán được phê duyệt/FIPS; chọn PRF và số vòng lặp theo chuẩn hiện hành.

Không tự viết thuật toán mật mã. Dùng thư viện được duy trì và định dạng lưu trữ có phiên bản để biết thuật toán, salt và tham số.

### 6.2. Quy trình đăng ký và xác minh

~~~mermaid
flowchart TD
    A["Người dùng gửi mật khẩu mới qua HTTPS"] --> B["Kiểm tra policy và blocklist"]
    B --> C{"Đạt chính sách?"}
    C -->|Không| D["Trả hướng dẫn sửa mật khẩu"]
    C -->|Có| E["Tạo salt ngẫu nhiên riêng"]
    E --> F["Chạy password KDF với tham số cấu hình"]
    F --> G["Lưu verifier + salt + thuật toán + tham số"]
    G --> H["Không lưu mật khẩu rõ"]
~~~

Ví dụ cấu trúc khái niệm:

~~~text
account_id
password_verifier
kdf_algorithm
kdf_parameters
salt
created_at
updated_at
credential_version
~~~

Thực tế, nhiều thư viện lưu thuật toán, salt và tham số trong một chuỗi verifier đã chuẩn hóa. Điều quan trọng là dữ liệu đủ để xác minh và nâng cấp, không lưu mật khẩu rõ.

### 6.3. Pepper và bảo vệ database

**Pepper** là bí mật bổ sung dùng chung hoặc theo phạm vi, được lưu tách khỏi database (ví dụ secret manager/HSM). Pepper có thể tăng lớp bảo vệ khi database bị lộ, nhưng tạo thêm yêu cầu quản lý, rotation, backup và khôi phục. Nếu mất pepper, verifier có thể không xác minh được; nếu pepper bị lộ cùng database, lợi ích giảm đáng kể. Không coi pepper là thay thế salt hoặc KDF.

Cần hạn chế quyền đọc database, mã hóa ổ đĩa/backup, audit truy cập, bảo vệ môi trường chạy KDF và tránh ghi dữ liệu đầu vào vào log, crash dump hoặc telemetry.

### 6.4. Nâng cấp tham số theo thời gian

Phần cứng ngày càng nhanh; cost đã phù hợp hôm nay có thể yếu sau vài năm. Lưu thuật toán và tham số để có thể **rehash khi người dùng đăng nhập thành công**:

1. Xác minh mật khẩu với verifier hiện tại.
2. Kiểm tra verifier có dùng thuật toán/chi phí cũ không.
3. Nếu cần, tính verifier mới với salt mới và tham số mới.
4. Cập nhật nguyên tử, không làm mất khả năng đăng nhập nếu có lỗi giữa chừng.

Có thể chạy quy trình migration cho tài khoản ít hoạt động, nhưng không nên yêu cầu người dùng gửi lại mật khẩu rõ qua email hoặc hỗ trợ.

## 7. Luồng đăng ký, đăng nhập và đổi mật khẩu

### 7.1. Đăng ký

~~~text
POST /accounts
  validate identifier and account creation policy
  receive password only over HTTPS
  enforce length and maximum request size
  check blocklist and breached-password policy
  generate unique salt
  derive password verifier using configured KDF
  store verifier metadata
  create account in pending/active state per verification policy
  never log request body or password
~~~

Đăng ký cần xử lý trùng định danh, xác minh địa chỉ liên lạc nếu sản phẩm yêu cầu và chống bot. Không để việc xác minh email biến thành bằng chứng duy nhất cho tài khoản nhạy cảm nếu policy yêu cầu mức bảo đảm cao hơn.

### 7.2. Đăng nhập

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant C as Client
    participant A as Authentication service
    participant DB as Credential store
    participant S as Session manager
    U->>C: Nhập identifier và password
    C->>A: POST /login qua HTTPS
    A->>A: Rate limit và kiểm tra tín hiệu lạm dụng
    A->>DB: Tra cứu verifier theo account
    DB-->>A: Verifier + salt + KDF parameters
    A->>A: Verify bằng password KDF
    alt Sai hoặc tài khoản không đủ điều kiện
        A-->>C: Lỗi đăng nhập chung
    else Đúng mật khẩu
        A->>A: Kiểm tra yêu cầu MFA/step-up
        A->>S: Tạo session mới sau khi đủ điều kiện
        S-->>A: Session ID mới
        A-->>C: Cookie phiên được bảo vệ
    end
~~~

Các điểm bắt buộc:

- Dùng HTTPS/TLS; không nhận mật khẩu qua query string hoặc URL.
- Giới hạn request và bảo vệ KDF khỏi bị lạm dụng gây cạn CPU/bộ nhớ.
- Tránh thông báo khác nhau dễ bị lợi dụng để dò tài khoản tồn tại.
- Không phát hành session đầy đủ nếu MFA chưa hoàn tất.
- Xoay session ID sau đăng nhập hoặc thay đổi mức đặc quyền.
- Không lưu mật khẩu trong local storage, analytics, crash report hoặc log.
- Sau đăng nhập thành công, có thể nâng cấp password verifier theo chính sách.

### 7.3. Đổi mật khẩu khi người dùng còn truy cập

Luồng đổi mật khẩu cần yêu cầu xác thực lại phù hợp với rủi ro, đặc biệt khi phiên đã cũ hoặc thiết bị mới. Sau khi xác minh, kiểm tra policy cho mật khẩu mới, cập nhật verifier nguyên tử, thông báo cho chủ tài khoản và quyết định thu hồi phiên/token cũ.

Không nên chỉ dựa vào một request có cookie để cho đổi mật khẩu nếu thao tác có thể chiếm quyền lâu dài. Với tài khoản dùng MFA/passkey, yêu cầu xác thực lại bằng phương thức tương xứng; nhập lại chính mật khẩu hiện tại không giải quyết được tình huống mật khẩu đã bị phishing.

## 8. Phòng chống tấn công vào endpoint đăng nhập

### 8.1. Brute force

Kẻ tấn công thử nhiều mật khẩu cho một tài khoản. Rate limit theo tài khoản và nhiều tín hiệu, có delay tăng dần hoặc cơ chế challenge phù hợp. Khóa tài khoản cứng sau vài lần sai có thể bị lợi dụng để gây DoS cho nạn nhân; thiết kế cần cân bằng giữa giảm đoán và duy trì khả dụng.

### 8.2. Password spraying

Kẻ tấn công thử một số mật khẩu phổ biến trên nhiều tài khoản để tránh ngưỡng giới hạn theo từng tài khoản. Cần theo dõi theo IP/ASN/thiết bị/tập tài khoản và tín hiệu hành vi, nhưng tránh phụ thuộc một IP duy nhất vì nhiều người dùng hợp lệ có thể chung NAT hoặc mạng doanh nghiệp.

### 8.3. Credential stuffing

Kẻ tấn công dùng cặp username/password bị lộ từ dịch vụ khác. Phòng vệ gồm mật khẩu độc nhất, kiểm tra mật khẩu đã lộ, MFA, phát hiện đăng nhập bất thường, rate limit và cảnh báo khi có dấu hiệu. CAPTCHA hoặc IP reputation có thể là tín hiệu phụ, không phải giải pháp cốt lõi.

### 8.4. Enumeration

Phản hồi “tài khoản không tồn tại” khác “mật khẩu sai” có thể giúp dò danh sách tài khoản. Dùng thông báo lỗi chung và kiểm soát chênh lệch thời gian xử lý có thể quan sát. Không cần cố làm mọi đường xử lý giống nhau tuyệt đối, nhưng không được tạo khác biệt rõ ràng có ích cho attacker.

### 8.5. KDF exhaustion / denial of service

Password KDF được thiết kế tốn tài nguyên. Attacker có thể gửi số lượng lớn request đăng nhập để ép server tiêu thụ CPU/RAM. Giới hạn request trước bước KDF, kiểm soát concurrency, đặt timeout, giám sát hàng đợi và kiểm thử tải. Không giảm cost KDF toàn hệ thống chỉ để xử lý spike mà không đánh giá rủi ro.

### 8.6. Credential stuffing và MFA fatigue

MFA giảm rủi ro khi mật khẩu bị lộ nhưng có thể bị tấn công qua OTP phishing, push fatigue hoặc recovery yếu. Dùng phương thức chống phishing cho tài khoản có rủi ro cao, giới hạn yêu cầu push, hiển thị ngữ cảnh đăng nhập và giám sát sự kiện. Không tự động coi một lần nhập OTP thành công là bằng chứng chống phishing.

## 9. Reset và recovery mật khẩu

Reset password là một luồng authentication nhạy cảm vì có thể thay thế credential hiện tại. Thiết kế yếu có thể vô hiệu mọi kiểm soát ở màn hình đăng nhập.

### 9.1. Token reset

Một token reset nên:

- Được sinh bằng bộ sinh số ngẫu nhiên mật mã, entropy cao.
- Gắn với đúng account và mục đích reset; không dùng chung với token phiên hoặc token xác minh email khác mục đích.
- Có thời hạn ngắn theo policy và chỉ dùng một lần.
- Lưu bản kiểm tra an toàn (ví dụ hash token) thay vì token rõ khi phù hợp.
- Bị vô hiệu khi đã sử dụng, hết hạn hoặc có yêu cầu reset mới theo chính sách.
- Không ghi token vào log, analytics hoặc referrer.
- Có giới hạn gửi và thử để ngăn spam, enumeration và brute force.

### 9.2. Quy trình reset

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant A as Ứng dụng
    participant E as Kênh liên lạc đã đăng ký
    participant DB as Credential store
    U->>A: Yêu cầu reset
    A->>A: Phản hồi chung, rate limit
    A->>E: Gửi token ngẫu nhiên có thời hạn
    E-->>U: Nhận link reset
    U->>A: Trình token và mật khẩu mới
    A->>A: Kiểm tra token, TTL, trạng thái một lần
    A->>A: Kiểm tra policy và blocklist
    A->>DB: Tạo verifier mới, cập nhật nguyên tử
    A->>A: Tiêu thụ token, xử lý phiên cũ, gửi thông báo
    A-->>U: Hoàn tất theo chính sách
~~~

Khi yêu cầu reset, phản hồi nên chung chung để không tiết lộ tài khoản có tồn tại hay không. Với email/SMS, việc nhận được thông điệp chứng minh quyền kiểm soát kênh tại thời điểm đó; nó không tự động đáp ứng mọi mức assurance. Tài khoản quản trị hoặc tài khoản nhạy cảm có thể cần recovery mạnh hơn.

### 9.3. Sau reset

Sau khi đổi mật khẩu qua recovery:

- Thông báo cho chủ tài khoản qua kênh đã đăng ký.
- Thu hồi hoặc yêu cầu đánh giá lại các phiên và refresh token hiện tại theo policy.
- Cân nhắc yêu cầu đăng nhập lại và xác thực MFA nếu cần.
- Ghi sự kiện an ninh nhưng không ghi token hoặc mật khẩu.
- Theo dõi thay đổi email, MFA, passkey hoặc quyền xảy ra ngay sau recovery.
- Không tự động liên kết tài khoản IdP mới chỉ vì email khớp.

## 10. Mật khẩu trong hệ thống nhiều dịch vụ

Trong kiến trúc nhiều service, cần xác định **thành phần nào thực sự nhận mật khẩu**. Thông thường chỉ authentication service xử lý mật khẩu và credential store; các resource service nhận session hoặc access token đã được phát hành theo cơ chế tin cậy.

Không truyền mật khẩu từ frontend tới nhiều API hoặc lưu lại ở service nghiệp vụ. Không dùng password của người dùng làm shared secret giữa các service. Với machine-to-machine, dùng credential/workload identity phù hợp như chứng chỉ, khóa hoặc token có vòng đời; quản lý secret riêng.

Nếu tích hợp IdP bên ngoài, RP không nhận mật khẩu của người dùng tại IdP. RP phải kiểm tra kết quả OIDC/SAML theo cấu hình, issuer, audience, chữ ký, thời hạn và mapping danh tính; không tạo một form giả để thu mật khẩu của nhà cung cấp khác.

## 11. Vận hành và giám sát chính sách

Một chính sách tốt cần có khả năng vận hành và thay đổi theo bằng chứng.

### 11.1. Chỉ số nên theo dõi

- Tỷ lệ đăng ký thất bại do mật khẩu không đạt policy.
- Tỷ lệ đăng nhập thất bại theo nhóm nguyên nhân và nguồn.
- Tín hiệu brute force, spraying và credential stuffing.
- Tỷ lệ reset, số lần gửi token và tỷ lệ token hết hạn/dùng lại.
- Tỷ lệ đăng nhập yêu cầu MFA/step-up và kết quả.
- Tỷ lệ người dùng bị khóa nhầm hoặc phải liên hệ hỗ trợ.
- Thời gian xác minh KDF, CPU/RAM và độ trễ endpoint đăng nhập.
- Số verifier được nâng cấp thuật toán/tham số.
- Sự kiện đổi mật khẩu, đổi kênh khôi phục và thu hồi phiên.

Không log mật khẩu, password verifier nếu không cần, token reset, OTP, session ID hoặc nội dung request nhạy cảm. Log nên có correlation ID, account ID nội bộ khi đã xác định, thời gian, loại sự kiện, kết quả và nguồn ở mức tối thiểu cần thiết; giới hạn quyền đọc và thời gian lưu.

### 11.2. Quản trị thay đổi policy

Khi đổi độ dài tối thiểu, blocklist hoặc KDF parameters:

1. Xác định tác động với tài khoản hiện có và client cũ.
2. Thử nghiệm trên nhóm nhỏ hoặc môi trường staging.
3. Theo dõi tỷ lệ từ chối và liên hệ hỗ trợ.
4. Có kế hoạch migration/re-hash cho verifier cũ.
5. Cập nhật tài liệu hướng dẫn và thông báo phù hợp.
6. Có phương án rollback cấu hình mà không hạ thấp kiểm soát một cách âm thầm.

Không thay đổi cách chuẩn hóa hoặc cắt cụt mật khẩu mà không đánh giá tương thích, vì có thể khiến người dùng không đăng nhập được với credential đã đăng ký.

## 12. Bài thực hành: thiết kế Password policy cho StudyHub

**Bối cảnh:** StudyHub có học viên, giảng viên và quản trị viên. Học viên dùng mật khẩu và có thể bật TOTP/passkey. Giảng viên truy cập dữ liệu điểm; quản trị viên quản lý quyền và cấu hình hệ thống. Dịch vụ authentication lưu password verifier; các API nghiệp vụ chỉ nhận session/token.

### 12.1. Hãy viết policy có thể kiểm thử

Điền các quyết định cụ thể cho hệ thống giả định:

| Câu hỏi | Quyết định cần ghi |
| --- | --- |
| Độ dài tối thiểu cho mật khẩu SFA? | Chọn số ký tự và giải thích căn cứ chuẩn/rủi ro. |
| Độ dài tối thiểu khi mật khẩu là một phần của MFA? | Xác định có khác SFA không và căn cứ nào cho phép. |
| Độ dài tối đa và Unicode? | Chọn giới hạn đủ lớn, quy tắc đếm và xử lý chuẩn hóa. |
| Blocklist gồm những gì? | Nguồn dữ liệu, cập nhật và cách bảo vệ riêng tư. |
| Có ép đổi định kỳ không? | Nêu trường hợp ngoại lệ có căn cứ. |
| KDF và tham số? | Chọn thuật toán, salt, cost, cách nâng cấp. |
| Rate limit? | Phân biệt giới hạn theo tài khoản, nguồn và toàn hệ thống. |
| Recovery? | Loại token, TTL, một lần, thông báo và thu hồi phiên. |
| Tài khoản quản trị? | Mức MFA/phương thức chống phishing và step-up. |

### 12.2. Ca kiểm thử chấp nhận

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Mật khẩu ngắn hơn mức tối thiểu | Đăng ký/đổi mật khẩu bị từ chối với hướng dẫn rõ ràng. |
| Mật khẩu phổ biến hoặc có trong blocklist | Bị từ chối, không lưu verifier. |
| Mật khẩu dài hợp lệ có khoảng trắng/Unicode | Được xử lý nhất quán theo quy tắc đã công bố. |
| Mật khẩu vượt giới hạn request | Bị từ chối an toàn trước khi tiêu thụ quá nhiều tài nguyên. |
| Password manager paste/autofill | Hoạt động bình thường; không bị chặn vô lý. |
| Hai tài khoản dùng cùng mật khẩu | Salt riêng tạo verifier khác nhau. |
| Database verifier bị lộ trong môi trường thử | Không có mật khẩu rõ; tham số KDF và salt được lưu đúng. |
| Mật khẩu đúng nhưng tài khoản yêu cầu MFA | Chưa cấp session đầy đủ trước khi MFA hoàn tất. |
| Sai mật khẩu nhiều lần | Rate limit/giám sát kích hoạt; không làm lộ tài khoản tồn tại. |
| Password spraying trên nhiều account | Hệ thống phát hiện theo nhiều tín hiệu, không chỉ ngưỡng từng account. |
| Reset token hết hạn hoặc dùng lại | Bị từ chối; không thay đổi credential. |
| Reset token hợp lệ nhưng request thay account ID | Bị từ chối vì token gắn với đúng account. |
| Reset thành công | Verifier mới được lưu; phiên/token cũ được xử lý theo policy và có thông báo. |
| Người dùng đổi mật khẩu khi phiên cũ | Xác thực lại/step-up theo rủi ro; không chỉ tin cookie cũ. |
| KDF parameters đã lỗi thời | Verifier được nâng cấp theo quy trình sau lần xác thực thành công. |
| Log/analytics thu nhận request đăng nhập | Không chứa mật khẩu, token hoặc dữ liệu bí mật. |

### 12.3. Câu hỏi tự đánh giá

1. Vì sao độ dài thường có ích hơn việc bắt buộc mọi nhóm ký tự?
2. Khi nào nên yêu cầu người dùng đổi mật khẩu?
3. Salt và pepper khác nhau ở đâu? Vì sao không dùng một salt chung?
4. Vì sao SHA-256 đơn lẻ không phải password storage scheme phù hợp?
5. Argon2id, scrypt, bcrypt và PBKDF2 khác nhau ở những điểm nào cần cân nhắc?
6. Vì sao rate limit chỉ theo IP không đủ cho password spraying?
7. CAPTCHA có làm mật khẩu thành MFA không?
8. Tại sao reset password là một trust boundary và token phải dùng một lần?
9. Sau reset, cần xem xét phiên và refresh token như thế nào?
10. Nếu một ứng dụng hỗ trợ passkey, password policy còn cần thiết trong những đường nào?

**Tiêu chí hoàn thành:** Người học có thể viết policy có con số và quy tắc rõ ràng, giải thích căn cứ, vẽ được luồng credential lifecycle, xác định cách lưu verifier và chứng minh bằng test rằng mật khẩu yếu, replay, lạm dụng đăng nhập và recovery không an toàn bị xử lý đúng.

## 13. Tài liệu nên đọc tiếp

- **NIST SP 800-63B** (Digital Identity Guidelines — Authentication and Authenticator Management): yêu cầu hiện hành về mật khẩu, authenticator và mức bảo đảm; cần xác định đúng phiên bản và phạm vi.
- **OWASP Authentication Cheat Sheet**: thiết kế đăng nhập, lỗi, rate limiting và xác thực lại.
- **OWASP Password Storage Cheat Sheet**: lựa chọn KDF, salt, pepper và nâng cấp tham số.
- **OWASP Forgot Password Cheat Sheet**: token reset và quy trình recovery.
- **OWASP ASVS**: chuyển yêu cầu mật khẩu, session và authentication thành tiêu chí xác minh.
- **Tài liệu chính thức của Argon2, scrypt, bcrypt hoặc PBKDF2** và thư viện triển khai được duy trì: để cấu hình tham số đúng môi trường.

Khi áp dụng vào sản phẩm thật, hãy kiểm tra phiên bản tiêu chuẩn hiện hành, yêu cầu pháp lý/hợp đồng, năng lực nền tảng và dữ liệu tấn công thực tế. Chính sách phải được đánh giá định kỳ dựa trên sự cố, khả năng sử dụng và chất lượng kiểm soát ở toàn bộ vòng đời credential.
