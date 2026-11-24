# Single-factor authentication — Xác thực một yếu tố

**Single-factor authentication (SFA)** là cơ chế xác thực trong đó hệ thống dựa vào **một loại yếu tố xác thực độc lập** để kiểm tra người đang yêu cầu truy cập có kiểm soát credential gắn với một tài khoản hay không. Ví dụ quen thuộc nhất là đăng nhập bằng mật khẩu: người dùng khai báo tài khoản và chứng minh điều mình **biết**. Một ví dụ khác là đăng nhập chỉ bằng một khóa mật mã trên thiết bị, khi máy chủ chỉ yêu cầu bằng chứng **sở hữu** khóa mà không yêu cầu xác minh người dùng trên thiết bị.

SFA là nền tảng cần nắm trước khi học MFA, passkey, token, phiên, đăng nhập liên kết và khôi phục tài khoản. Nó phù hợp với một số nhu cầu rủi ro thấp, nhưng có giới hạn rõ ràng: **khi yếu tố duy nhất bị lộ, bị chiếm quyền hoặc bị dùng thay chủ sở hữu, hệ thống không còn một yếu tố độc lập khác để kiểm tra**. Thiết kế an toàn vì vậy phải xem xét cả credential, giao dịch đăng nhập, phiên sau đăng nhập, các ranh giới tin cậy và đường khôi phục.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích thế nào là **một yếu tố xác thực** và vì sao một bước đăng nhập không đồng nghĩa với một yếu tố.
2. Phân loại các ví dụ: mật khẩu, mã một lần, liên kết email, khóa mã hóa, sinh trắc, passkey và mật khẩu kèm câu hỏi bí mật.
3. Vẽ luồng SFA với các thành phần **claimant**, **verifier**, **credential store** và **session manager**.
4. Mô tả các rủi ro của SFA: phishing, credential stuffing, brute force, replay, session hijacking, giả mạo kênh khôi phục và lạm dụng endpoint.
5. Thiết kế phòng vệ nhiều lớp khi buộc phải dùng SFA, đồng thời nhận ra khi nào cần nâng lên MFA hoặc phương thức chống phishing.
6. Viết tiêu chí kiểm thử cho đăng nhập, hết hạn, phát lại, khóa phiên và khôi phục tài khoản.

## 2. Hiểu đúng chữ “factor”

Một yếu tố xác thực là **một loại bằng chứng** được dùng để chứng minh quyền kiểm soát credential. Ba loại thường gặp:

| Nhóm yếu tố | Ý nghĩa | Ví dụ | Điểm yếu cần xem xét |
| --- | --- | --- | --- |
| **Knowledge** — điều người dùng biết | Chứng minh biết một bí mật | Mật khẩu, PIN được máy chủ kiểm tra | Có thể bị đoán, lộ, chia sẻ hoặc nhập vào trang giả. |
| **Possession** — điều người dùng có | Chứng minh kiểm soát thiết bị/khóa/kênh đã ghi danh | Khóa bảo mật mật mã; thiết bị giữ private key; một mã gửi tới kênh đã đăng ký trong ngữ cảnh phù hợp | Thiết bị, khóa hoặc kênh nhận mã có thể bị chiếm quyền; phải chống sao chép/phát lại. |
| **Inherence** — đặc điểm của người dùng | Sử dụng đặc điểm sinh trắc để xác minh | Vân tay, khuôn mặt | Chất lượng cảm biến, chống giả mạo, quyền riêng tư và nơi dữ liệu được xử lý rất quan trọng. |

Không phải mọi bằng chứng về thiết bị hoặc kênh liên lạc đều tự động đạt mức bảo đảm của một authenticator đã ghi danh. Chẳng hạn, **nhận được email** chứng minh quyền truy cập hộp thư tại thời điểm đó, không mặc nhiên chứng minh danh tính pháp lý hoặc quyền sở hữu tài khoản ở mức bảo đảm cao.

### 2.1. Đếm yếu tố theo loại bằng chứng, không theo màn hình

Các trường hợp sau dễ gây nhầm lẫn:

| Luồng | Phân tích |
| --- | --- |
| Tên đăng nhập + mật khẩu | **Một yếu tố knowledge**. Tên đăng nhập chỉ là định danh được khai báo. |
| Mật khẩu + câu hỏi bí mật | Vẫn chỉ dựa vào **knowledge**; hai bí mật không tạo thành MFA. |
| Nhập mật khẩu hai lần | Một yếu tố, hai lần kiểm tra cùng một bằng chứng. |
| Chỉ nhập TOTP sau khi chọn tài khoản | Có thể là **một cơ chế OTP dựa trên quyền kiểm soát secret/app**; một mã không đồng nghĩa với MFA nếu không có yếu tố độc lập khác. |
| Chỉ nhấn liên kết đăng nhập gửi qua email | Thường là xác thực dựa trên quyền kiểm soát **hộp thư/kênh nhận link**, có thể được thiết kế như một luồng một yếu tố; độ bảo đảm phụ thuộc vào bảo vệ hộp thư và liên kết. |
| Dùng WebAuthn chỉ yêu cầu xác minh **sự hiện diện** của thiết bị/khóa (UP), không xác minh người dùng (UV) | Có thể chỉ chứng minh quyền kiểm soát **một authenticator**; cần kiểm tra chính sách và cờ giao thức. |
| Passkey với xác minh người dùng tại thiết bị (PIN/sinh trắc) và bằng chứng khóa mật mã | **Có thể là authenticator đa yếu tố trong một thao tác**, tùy cách ghi danh, xác minh cờ UV và mức bảo đảm được yêu cầu. Không nên mặc định mọi passkey là SFA hoặc mặc định mọi passkey đều đáp ứng MFA. |
| Mật khẩu + CAPTCHA | Vẫn là một yếu tố xác thực; CAPTCHA nhằm hạn chế tự động hóa, không xác minh thêm một yếu tố danh tính. |
| Mật khẩu + kiểm tra IP/vị trí/rủi ro | Thường vẫn là SFA với **tín hiệu rủi ro bổ sung**. Tín hiệu môi trường không tự động trở thành yếu tố xác thực độc lập. |

**Passwordless** nói rằng người dùng không cần gõ mật khẩu; nó **không cho biết** đang dùng bao nhiêu yếu tố. Tương tự, trải nghiệm “một chạm” có thể có một hoặc nhiều yếu tố được chứng minh trong cùng một thao tác.

## 3. SFA kiểm tra điều gì và không kiểm tra điều gì?

Giả sử sinh viên An chọn tài khoản `an@example.edu` rồi nhập mật khẩu. Ứng dụng kiểm tra credential đã đăng ký cho tài khoản đó. Nếu kiểm tra thành công, ứng dụng có thể thiết lập một phiên cho An.

Điều hệ thống **có thể kết luận**: bên gửi yêu cầu đang cung cấp bằng chứng phù hợp với credential của tài khoản.

Điều hệ thống **không thể tự kết luận**: người đó chắc chắn là An ngoài đời thực, không bị lừa nhập mật khẩu vào website giả, chưa bị chiếm quyền thiết bị, hoặc được phép thực hiện mọi tác vụ trong ứng dụng. Những câu hỏi này lần lượt thuộc về **identity proofing**, chống gian lận và **authorization**.

### 3.1. Các thành phần và ranh giới tin cậy

~~~mermaid
flowchart LR
    C["Người dùng / thiết bị (claimant)"] -->|"Trình bày credential qua kênh bảo vệ"| V["Verifier / authentication service"]
    V -->|"Đọc verifier hoặc public key"| S[("Credential store")]
    V -->|"Kết quả xác thực"| M["Session manager"]
    M -->|"Cookie hoặc token phiên"| C
    C -->|"Request kèm phiên"| R["Ứng dụng / API"]
    R -->|"Xác thực phiên và phân quyền"| M
~~~

Sơ đồ này mô tả các chức năng logic; hệ thống thật có thể gộp hoặc tách chúng thành nhiều dịch vụ. Hãy chỉ ra ranh giới:

- **Thiết bị/trình duyệt → dịch vụ xác thực:** credential có thể bị lộ, thay thế, nhập vào origin giả hoặc gửi lặp lại.
- **Dịch vụ xác thực → kho credential:** dữ liệu lưu trữ và đường truy cập cần bảo vệ; không nên cho ứng dụng bất kỳ quyền đọc bí mật quá mức cần thiết.
- **Dịch vụ xác thực → quản lý phiên:** chỉ cấp phiên đã xác thực sau khi đủ điều kiện; không tin dữ liệu client tự khai về vai trò hay kết quả xác thực.
- **Phiên → tài nguyên:** mỗi request phải xác minh phiên/token và **kiểm tra phân quyền riêng**, không vì đã đăng nhập mà bỏ qua quyền trên từng tài nguyên.

Với liên kết email hoặc WebAuthn, luồng trên sẽ có bước trung gian khác: hệ thống email hoặc authenticator thực hiện một phần chứng minh. Cần mô hình hóa thêm ranh giới tin cậy đó khi thiết kế.

## 4. Các biến thể SFA phổ biến

### 4.1. Mật khẩu đơn lẻ

**Cách vận hành:** người dùng khai báo tài khoản, gửi mật khẩu qua HTTPS; máy chủ so khớp với **password verifier** được lưu và quyết định cấp phiên.

**Ưu điểm:** phổ biến, dễ tích hợp, không buộc người dùng sở hữu thiết bị xác thực chuyên biệt. **Giới hạn:** người dùng có thể dùng lại mật khẩu, chọn bí mật yếu hoặc bị phishing; kẻ tấn công có thể thử danh sách credential rò rỉ trên nhiều dịch vụ.

Phòng vệ tối thiểu cần học:

1. Bảo vệ kênh với HTTPS/TLS và tránh chuyển mật khẩu qua URL, log, analytics hay thông báo lỗi.
2. Lưu password verifier bằng thuật toán dẫn xuất mật khẩu có chi phí như **Argon2id**, với **salt ngẫu nhiên riêng** cho từng mật khẩu; dùng scrypt/bcrypt khi có ràng buộc tương thích thích hợp. Tránh lưu plaintext, mã hóa có thể giải mã khi không cần, hoặc dùng duy nhất hàm băm nhanh như SHA-256.
3. Hỗ trợ mật khẩu đủ dài và password manager; đối chiếu mật khẩu yếu/đã rò rỉ theo chính sách; tránh ép thay đổi định kỳ nếu không có căn cứ bị xâm phạm.
4. Giới hạn và giám sát thử đăng nhập theo nhiều tín hiệu (tài khoản, IP, hành vi, thời điểm) để chống brute force và credential stuffing; không để đối thủ dễ dàng khóa vĩnh viễn tài khoản hợp lệ.
5. Dùng thông báo lỗi chung cho đăng nhập sai; tránh rò rỉ sự tồn tại tài khoản qua thông báo hoặc chênh lệch phản hồi dễ khai thác.
6. Khi xác thực thành công, tạo **phiên mới ngẫu nhiên**; tách riêng quản lý phiên, phân quyền và theo dõi các đăng nhập bất thường.

Hệ thống cần xử lý khả năng nâng cấp tham số băm mật khẩu về sau, thay đổi mật khẩu có xác minh thích hợp và thu hồi phiên khi có dấu hiệu bị chiếm quyền.

### 4.2. Đăng nhập bằng magic link gửi qua email

Ứng dụng tạo một **token ngẫu nhiên, khó đoán**, gửi URL đăng nhập tới địa chỉ email đã đăng ký. Người dùng mở liên kết; máy chủ xác minh token, thời hạn, trạng thái sử dụng và tài khoản liên quan, sau đó mới quyết định cấp phiên.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant A as Ứng dụng
    participant E as Hộp thư đã đăng ký
    U->>A: Yêu cầu link đăng nhập
    A->>A: Tạo token ngắn hạn, lưu bản kiểm tra an toàn
    A->>E: Gửi email chứa link
    E-->>U: Người dùng mở link
    U->>A: Trình link/token
    A->>A: Kiểm tra tài khoản, TTL, trạng thái một lần
    A-->>U: Tạo phiên nếu hợp lệ
~~~

Đây là một dạng **passwordless** nhưng không tự động là MFA: nếu hộp thư bị chiếm quyền hoặc liên kết bị rò rỉ, đối thủ có thể vượt qua bước xác thực. Các kiểm soát cần xem xét gồm: token có entropy cao, thời hạn ngắn, chỉ sử dụng một lần, giới hạn gửi email, không để token xuất hiện trong log hoặc dữ liệu phân tích, và chính sách `Referrer-Policy` phù hợp để tránh rò rỉ qua referrer.

**Lưu ý trải nghiệm thực tế:** ứng dụng email, công cụ chống phishing hoặc bộ quét đường link có thể tự mở URL. Tránh để một lượt quét đơn thuần có thể **tiêu thụ và hoàn tất đăng nhập**; có thể yêu cầu thao tác xác nhận chủ động sau khi người dùng mở link, kết hợp ràng buộc giao dịch với phiên khởi tạo khi phù hợp. Hãy xác định rõ trường hợp người dùng bắt đầu trên máy A nhưng mở email ở máy B.

### 4.3. Chỉ dùng OTP hoặc mã từ ứng dụng/thiết bị

OTP là mã có hiệu lực hạn chế; **TOTP** dựa trên thời gian, còn **HOTP** dựa trên bộ đếm. Nếu ứng dụng chỉ dùng một mã OTP để đăng nhập mà không có yếu tố độc lập khác, không nên gọi luồng đó là MFA.

Độ an toàn phụ thuộc cách ghi danh nguồn mã, bí mật được bảo vệ ở đâu, tính duy nhất của mã, giới hạn số lần thử, đồng bộ thời gian/bộ đếm và cơ chế ngăn **dùng lại một OTP đã được chấp nhận**. Với mã ngắn, máy chủ phải giới hạn thử vì không gian mã nhỏ. OTP có thể bị phishing thời gian thực; đặc tính “một lần” không tự động làm cho nó **phishing-resistant**.

Mã SMS và email có điểm yếu của kênh nhận; không nên mặc định các kênh này bảo đảm độc lập hoặc phù hợp cho tài khoản rủi ro cao. Xác định chính sách theo yêu cầu bảo đảm thực tế.

### 4.4. Chỉ dùng khóa/chứng chỉ thiết bị

Một thiết bị có thể chứng minh quyền sở hữu **private key** thông qua chữ ký đối với challenge. Máy chủ lưu public key để kiểm tra, không cần nhận private key. Một client có thể dùng **mTLS** để chứng minh đang kiểm soát private key ứng với chứng chỉ client đáng tin cậy; sau đó dịch vụ vẫn phải ánh xạ danh tính máy và kiểm tra quyền.

Nếu hệ thống chỉ kiểm tra quyền sở hữu khóa mà không yêu cầu một yếu tố độc lập khác, đây có thể là luồng SFA dựa trên possession. Mức bảo đảm còn tùy thiết bị có bảo vệ phần cứng không, khóa có thể xuất ra ngoài không, việc ghi danh có đáng tin cậy không và quy trình thu hồi/luân chuyển khóa có an toàn không.

Trong WebAuthn, cần phân biệt **user presence (UP)** với **user verification (UV)**. UP cho biết có tương tác với authenticator; UV thể hiện authenticator đã xác minh người dùng theo cơ chế của nó, chẳng hạn PIN hoặc sinh trắc. Máy chủ phải kiểm tra cờ phù hợp với chính sách. **Một passkey dùng UV có thể đáp ứng yêu cầu đa yếu tố bằng một authenticator**, vì vậy không thể kết luận “đăng nhập bằng một passkey” luôn là SFA.

### 4.5. Sinh trắc học đơn lẻ

Vân tay và khuôn mặt thường được dùng để **mở khóa authenticator tại thiết bị**, không có nghĩa là máy chủ nhận mẫu vân tay/khuôn mặt để kiểm tra trực tiếp. Nếu hệ thống tự xác minh sinh trắc như bằng chứng duy nhất, phải xem xét chống giả mạo trình diện (presentation attack), sai số nhận diện, xử lý dữ liệu nhạy cảm, khả năng thay thế credential và khả năng phục hồi khi xác minh thất bại.

Trong thiết kế hiện đại, nên phân tích **kiến trúc xác minh và bảo vệ khóa** thay vì dựa vào câu “có dùng vân tay nên an toàn”. Sinh trắc không phải bí mật có thể đổi tùy ý như mật khẩu khi dữ liệu bị lộ.

## 5. Phân tích vòng đời SFA qua ví dụ

Xét hệ thống giả định **CoursePortal** cho sinh viên truy cập tài liệu khóa học. Sinh viên đăng nhập bằng **mật khẩu duy nhất**. Tài khoản giảng viên có quyền quản lý điểm và thông tin nhạy cảm hơn, nên ứng dụng sẽ phải đánh giá yêu cầu nâng xác thực riêng.

### 5.1. Ghi danh credential

Ứng dụng tạo account ID ổn định, xác nhận các thông tin liên lạc cần thiết và đặt mật khẩu theo chính sách. Mật khẩu chỉ được xử lý trong kênh bảo vệ; server tạo verifier có salt và tham số chi phí phù hợp. Những hành động như **đổi mật khẩu, thêm passkey hoặc đổi email khôi phục** cần một mức xác thực gần đây tương xứng, không đơn thuần tin request đang có cookie.

### 5.2. Đăng nhập an toàn

~~~text
Client -> HTTPS POST /login { identifier, password }
Server:
  kiểm tra giới hạn yêu cầu và tín hiệu lạm dụng
  tra cứu account + password verifier
  kiểm tra bằng hàm password verification chuyên dụng
  nếu không hợp lệ:
      trả lỗi đăng nhập chung, ghi nhận sự kiện phù hợp
  nếu hợp lệ:
      quyết định có cần step-up vì mức nhạy cảm/rủi ro không
      nếu cần -> bắt đầu giao dịch xác thực bổ sung
      nếu đủ điều kiện -> tạo session ID mới, khó đoán, quản lý phía server
      trả cookie phiên được bảo vệ
Mỗi request:
  kiểm tra session và quyền trên tài nguyên được yêu cầu
~~~

Pseudocode minh họa **trình tự kiểm soát**, không phải mã production. Chính sách phát hiện lạm dụng không nên chỉ dựa vào một IP do nhiều người hợp lệ có thể dùng chung NAT; cũng không nên để thông báo khác biệt về “không tìm thấy tài khoản” và “sai mật khẩu” tiết lộ thông tin không cần thiết.

### 5.3. Duy trì và chấm dứt phiên

Đối với ứng dụng web dùng session cookie tham chiếu, một thiết lập minh họa là:

~~~http
Set-Cookie: __Host-session=<random-session-id>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

- **Secure** yêu cầu cookie được gửi qua HTTPS; **HttpOnly** ngăn JavaScript thông thường đọc cookie; **SameSite** giúp giảm một số tình huống request liên site.
- Prefix **`__Host-`** yêu cầu **Secure**, **Path=/** và không có thuộc tính **Domain**, hạn chế phạm vi cookie.
- Vẫn phải phòng **CSRF** bằng biện pháp phù hợp (ví dụ CSRF token và/hoặc kiểm tra Origin); vẫn phải phòng **XSS**, vì script độc hại có thể thực hiện hành động trong phiên dù không đọc được HttpOnly cookie.
- Sau đăng nhập hoặc nâng đặc quyền, tạo/đổi session ID để phòng **session fixation**; quản lý idle timeout, absolute timeout, đăng xuất và thu hồi theo chính sách.
- Nếu dùng access token hoặc JWT, hãy kiểm tra chữ ký, issuer, audience, thời hạn và các claim bắt buộc ở bên nhận; không nhầm khả năng kiểm tra chữ ký với khả năng thu hồi ngay lập tức. Token bị đánh cắp vẫn có thể bị lạm dụng trong khoảng còn hiệu lực nếu không có ràng buộc bổ sung.

### 5.4. Khôi phục tài khoản

Khi sinh viên quên mật khẩu, hệ thống có thể gửi liên kết đặt lại qua kênh đã đăng ký. Nhưng nếu đường khôi phục quá yếu, kẻ tấn công có thể bỏ qua hoàn toàn màn hình đăng nhập. Token khôi phục cần khó đoán, ngắn hạn, dùng một lần, giới hạn gửi/thử; thao tác thay đổi credential nên được ghi log và thông báo cho chủ tài khoản. Cần xem xét phiên cũ có bị thu hồi sau khi đặt lại mật khẩu không.

Quan trọng hơn, nếu một hệ thống chuyển từ mật khẩu đơn lẻ sang MFA thì **đường khôi phục cũng phải nâng độ bảo đảm tương ứng**. Không thể tuyên bố đã bảo vệ tài khoản bằng MFA khi nhân viên hỗ trợ có thể tắt MFA chỉ dựa trên một thông tin công khai.

## 6. Mô hình đe dọa cho xác thực một yếu tố

| Đe dọa | Kẻ tấn công cần gì? | Tác động | Kiểm soát trọng tâm |
| --- | --- | --- | --- |
| **Phishing** | Dụ người dùng đưa bí mật/mã vào website giả | Đăng nhập trái phép nếu credential bị dùng kịp thời | Chuyển sang authenticator chống phishing khi cần; bảo vệ phiên, giám sát bất thường và giáo dục người dùng. |
| **Credential stuffing** | Danh sách email/mật khẩu đã rò rỉ | Chiếm nhiều tài khoản có dùng lại mật khẩu | Password manager, mật khẩu không tái sử dụng, kiểm tra mật khẩu rò rỉ, rate limiting và giám sát. |
| **Brute force / password spraying** | Khả năng gửi nhiều lần thử | Tìm mật khẩu yếu hoặc làm gián đoạn đăng nhập | Rate limiting nhiều chiều, kiểm soát có tính đến rủi ro, thông báo lỗi chung và phát hiện bất thường. |
| **Replay mã/đường link** | OTP hoặc token bị lấy trước đó | Dùng lại bằng chứng nếu verifier chấp nhận | Challenge/OTP dùng một lần hoặc chống replay, TTL ngắn, kiểm soát số lần thử, ràng buộc ngữ cảnh. |
| **Chiếm kênh email/SMS** | Kiểm soát hộp thư hoặc số điện thoại | Đăng nhập magic link, nhận OTP hoặc khôi phục trái phép | Chính sách kênh dự phòng, cảnh báo thay đổi, xác thực mạnh hơn cho thao tác nhạy cảm. |
| **Rò rỉ kho password verifier** | Truy cập trái phép database | Thử đoán mật khẩu ngoại tuyến | Argon2id/scrypt/bcrypt, salt riêng, quyền truy cập tối thiểu, theo dõi và ứng phó sự cố. |
| **Session hijacking** | Session ID hoặc access token còn hiệu lực | Bỏ qua lần xác thực ban đầu | Cookie an toàn, TLS, chống XSS, token TTL, phát hiện/thu hồi phiên, xác thực lại khi cần. |
| **Session fixation** | Khả năng khiến nạn nhân sử dụng session ID đã được đối thủ biết | Chiếm phiên sau khi nạn nhân đăng nhập | Tạo session ID mới sau xác thực và nâng quyền. |
| **Lạm dụng khôi phục** | Điểm yếu trong cấp lại credential | Chiếm tài khoản mà không cần credential cũ | Bằng chứng khôi phục phù hợp, token an toàn, giới hạn thử và cảnh báo. |

**Điểm cốt lõi:** các biện pháp bảo vệ lối vào (TLS, rate limit, CAPTCHA, giám sát) có ích nhưng không biến mật khẩu đơn lẻ thành MFA. Khi chính yếu tố duy nhất bị chiếm quyền, những biện pháp này chỉ có thể giảm khả năng hoặc thời gian lạm dụng, không tạo ra bằng chứng độc lập khác.

## 7. Khi nào SFA là đủ, và khi nào phải nâng cấp?

Quyết định cần dựa trên **rủi ro, tài sản được bảo vệ và yêu cầu tuân thủ áp dụng**, thay vì chỉ dựa trên sự tiện lợi của giao diện.

| Bối cảnh giả định | Hướng thiết kế |
| --- | --- |
| Xem nội dung công khai, không có tài khoản hoặc dữ liệu riêng tư | Có thể không cần xác thực. |
| Tài khoản dùng tính năng cá nhân hóa ít nhạy cảm | SFA có thể là điểm khởi đầu nếu kiểm soát abuse, session và recovery đầy đủ; vẫn đánh giá khả năng chuyển sang phương thức mạnh hơn. |
| Thay đổi email khôi phục, mật khẩu, phương thức thanh toán hoặc cấp credential mới | Xem xét **reauthentication/step-up** dựa trên rủi ro và mức nhạy cảm; chỉ có cookie hợp lệ thường không đủ. |
| Truy cập dữ liệu nhạy cảm, thao tác chuyển tiền, quản trị, hệ thống sản xuất | Ưu tiên MFA phù hợp, đặc biệt phương thức **chống phishing**, cùng kiểm soát phân quyền và giám sát. |
| API service-to-service | Xác thực workload bằng khóa/chứng chỉ/token có kiểm soát vòng đời và quyền riêng; đánh giá mức bảo đảm và mô hình tin cậy khác với người dùng cuối. |

### 7.1. Risk-based authentication có làm SFA thành MFA không?

Không nhất thiết. Hệ thống có thể dựa vào IP, thông tin thiết bị, vị trí, tốc độ truy cập và hành vi để **quyết định từ chối, tăng kiểm tra hoặc yêu cầu step-up**. Nếu chỉ dùng các tín hiệu đó để đánh giá rủi ro mà không kiểm tra một yếu tố độc lập, luồng vẫn dựa trên SFA.

Khi quyết định cần MFA, hệ thống phải thực sự kiểm tra thêm yếu tố thích hợp hoặc dùng authenticator được xác minh đáp ứng yêu cầu đa yếu tố; không được chỉ ghi “MFA passed” vì một bộ máy chấm điểm rủi ro trả kết quả tốt.

### 7.2. Chuyển từ SFA lên MFA

Một lộ trình triển khai thực tế:

1. **Hiểu và đo rủi ro hiện tại:** sự cố đăng nhập, dùng lại mật khẩu, khôi phục tài khoản, tài khoản quản trị và yêu cầu bảo vệ dữ liệu.
2. **Ưu tiên phương thức:** hỗ trợ passkey/WebAuthn chống phishing khi phù hợp; nếu dùng TOTP, hiểu giới hạn chống phishing của mã nhập tay.
3. **Ghi danh an toàn:** chỉ cho thêm/xóa yếu tố sau xác thực gần đây, kiểm tra thông báo thay đổi và bảo vệ credential dự phòng.
4. **Điều chỉnh phiên và step-up:** phân biệt phiên vừa đăng nhập, phiên đã xác thực tăng cường và thời gian xác thực gần nhất; kiểm tra tại server trước hành động nhạy cảm.
5. **Thiết kế đường mất thiết bị:** recovery phải tương xứng với chính sách tài khoản, có khả năng hỗ trợ người dùng và chống social engineering.
6. **Đo hiệu quả:** tỷ lệ hoàn tất đăng nhập, tỷ lệ recovery, khóa nhầm, cảnh báo bất thường và khả năng tiếp cận.

## 8. Thực hành: đánh giá ba thiết kế

### Trường hợp A — Website học từ vựng

Người dùng nhập email và mật khẩu để xem lịch sử học. Hệ thống có TLS, lưu verifier bằng Argon2id, giới hạn thử đăng nhập và cấp session cookie.

**Đánh giá:** Đây là **SFA dựa trên knowledge**. Kiểm soát kỹ thuật làm giảm rủi ro nhưng không chống được mọi phishing hoặc mật khẩu bị chiếm quyền. Hãy đề xuất cơ chế khôi phục và cách khuyến khích chuyển sang passkey mà không làm mất quyền truy cập tài khoản.

### Trường hợp B — Dashboard nội bộ

Nhân viên nhập mật khẩu, trả lời câu hỏi “Tên thú cưng đầu tiên?” và hoàn tất CAPTCHA. Người phát triển tuyên bố “ba bước nên là ba yếu tố”.

**Đánh giá:** Tuyên bố sai. Mật khẩu và câu hỏi bí mật đều là **knowledge**; CAPTCHA không phải yếu tố xác thực. Với dữ liệu nội bộ quan trọng, hãy thay bằng authenticator đa yếu tố thích hợp hoặc kết hợp các yếu tố độc lập theo mô hình đe dọa.

### Trường hợp C — Passkey trong ứng dụng quản trị

Ứng dụng dùng WebAuthn với challenge mới, kiểm tra chữ ký và RP ID/origin, yêu cầu **UV** và xác minh cờ UV đúng chính sách. Người dùng chỉ thực hiện một thao tác trên thiết bị.

**Đánh giá:** Số thao tác là một, nhưng **không thể kết luận chỉ một yếu tố**. Authenticator có khả năng chứng minh quyền kiểm soát khóa và xác minh người dùng cục bộ; tùy tiêu chuẩn bảo đảm và cách triển khai, đây có thể là **một authenticator đa yếu tố**. Vẫn phải bảo vệ enrollment, recovery, session và authorization.

## 9. Danh sách kiểm thử cho một luồng SFA

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Nhập đúng định danh nhưng sai mật khẩu | Không cấp session; thông báo lỗi không tiết lộ dữ liệu nhạy cảm. |
| Dùng định danh không tồn tại | Không rò rỉ thông tin hữu ích cho enumeration qua lỗi và thời gian xử lý quá khác biệt. |
| Thử nhiều mật khẩu liên tục hoặc từ nhiều nguồn | Hệ thống áp dụng kiểm soát lạm dụng và ghi sự kiện; không khóa nhầm hàng loạt người dùng hợp lệ. |
| Đăng nhập hợp lệ | Session ID mới được tạo; không tái dùng session ID chưa xác thực do client cung cấp. |
| Dùng lại magic link đã thành công hoặc hết hạn | Link bị từ chối; không tạo thêm phiên. |
| Mở magic link bằng bộ quét URL tự động | Việc quét đơn thuần không tự hoàn tất đăng nhập. |
| Dùng lại OTP đã được xác nhận | Mã bị từ chối theo chính sách ngăn replay. |
| Truy cập API bằng token hết hạn hoặc không đúng audience | API từ chối. |
| Dùng session học viên gọi API quản trị | API từ chối vì thiếu quyền dù đăng nhập hợp lệ. |
| Sau logout, dùng lại session đã bị thu hồi | Truy cập bị từ chối. |
| Nhập yêu cầu đổi mật khẩu/email khi phiên quá cũ | Hệ thống yêu cầu xác thực lại hoặc step-up theo mức rủi ro. |
| Đặt lại mật khẩu bằng token recovery đã sử dụng | Bị từ chối; sự kiện cần thiết được ghi nhận và thông báo. |

Những kiểm thử liên quan brute force, replay hoặc session hijacking chỉ nên thực hiện bằng **tài khoản và môi trường thử nghiệm được phép**, với giới hạn tải phù hợp.

## 10. Bài tập tổng hợp

**Yêu cầu:** Hãy thiết kế đăng nhập một yếu tố cho CoursePortal phiên bản đầu, sau đó viết kế hoạch nâng bảo vệ cho giảng viên.

Sản phẩm cần nộp:

1. Một **sequence diagram** từ bước nhập credential đến khi truy cập tài nguyên đầu tiên.
2. Bảng **credential lifecycle**: đăng ký, kiểm tra, thay đổi, thu hồi và khôi phục.
3. Bản đồ **trust boundary** và tối thiểu năm đe dọa có thể kiểm thử.
4. Quy tắc **session** gồm tạo mới, timeout, logout, bảo vệ cookie/token và phân quyền.
5. Bản quyết định **giữ SFA hay chuyển MFA** theo mức độ nhạy cảm của tài khoản, kèm đường recovery tương ứng.

Thử phản biện thiết kế bằng các câu hỏi: “Nếu mật khẩu của học viên bị lộ, những kiểm soát nào còn hiệu lực?”, “Nếu hộp thư bị chiếm quyền, có chiếm được tài khoản không?”, “Nếu một script độc hại chạy trong trình duyệt, HttpOnly có đủ không?”, “Nếu người dùng đăng nhập bằng passkey, máy chủ đã kiểm tra cờ UV chưa?”.

## 11. Câu hỏi tự kiểm tra

1. Tại sao username + password được tính là một yếu tố?
2. Khi nào magic link có thể là một luồng xác thực một yếu tố và rủi ro lớn nhất của nó là gì?
3. Vì sao mật khẩu + câu hỏi bí mật không phải MFA?
4. Khác nhau giữa **user presence** và **user verification** trong WebAuthn là gì?
5. Tại sao “passwordless” và “single-factor” không đồng nghĩa?
6. Những lớp phòng vệ nào cần có ngoài việc kiểm tra đúng mật khẩu?
7. Credential bị phishing và session bị đánh cắp khác nhau ở đường tấn công nào?
8. Tại sao recovery có thể làm vô hiệu ý nghĩa của một luồng đăng nhập mạnh?
9. Khi dùng SFA, hệ thống nên yêu cầu step-up trước các hành động nào?
10. Bạn sẽ chứng minh cơ chế ngăn replay hoạt động bằng những ca kiểm thử nào?

**Tự đối chiếu:** Một thiết kế đủ tốt phải giải thích được **bằng chứng nào được kiểm tra, ai kiểm tra, ranh giới nào được tin, điều gì xảy ra khi yếu tố duy nhất bị chiếm quyền, và phiên/khôi phục được bảo vệ thế nào**. Nếu không trả lời được một trong những câu này, việc chọn thư viện hay mẫu giao diện đăng nhập vẫn còn quá sớm.

### Tài liệu nên đọc tiếp

- **NIST SP 800-63** (bộ hướng dẫn về digital identity và authenticator assurance): để hiểu phân loại authenticator và yêu cầu bảo đảm.
- **OWASP Authentication Cheat Sheet, Password Storage Cheat Sheet, Session Management Cheat Sheet và Forgot Password Cheat Sheet**: để đối chiếu kiểm soát triển khai.
- **W3C Web Authentication (WebAuthn)** và **FIDO Alliance**: để hiểu rõ UP/UV, public-key credential, chống phishing và passkey.
- **OWASP ASVS**: để chuyển các yêu cầu thiết kế thành tiêu chí xác minh ứng dụng.

Khi triển khai sản phẩm thật, luôn kiểm tra phiên bản hiện hành của tiêu chuẩn, đặc tính thiết bị, mô hình đe dọa và yêu cầu tuân thủ của hệ thống.
