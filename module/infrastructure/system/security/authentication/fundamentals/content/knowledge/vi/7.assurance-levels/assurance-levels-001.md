# Authentication assurance (Mức bảo đảm xác thực)

> **Chương:** Mức độ tin cậy  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS — tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey, chứng chỉ đến token, phiên, liên kết danh tính, khôi phục tài khoản; mô hình hóa ranh giới tin cậy và chống phishing, replay, lạm dụng đăng nhập.
>
> **Câu hỏi trọng tâm:** Sau khi một chủ thể đăng nhập thành công, hệ thống có **bao nhiêu cơ sở để tin rằng người đang truy cập thực sự kiểm soát các authenticator đã đăng ký**, và mức bảo đảm đó có đủ cho hành động sắp thực hiện không?

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích **authentication assurance** và **Authenticator Assurance Level (AAL)**, cũng như giới hạn của một kết quả xác thực thành công.
2. Phân biệt **AAL** với **Identity Assurance Level (IAL)**, **Federation Assurance Level (FAL)** và **phân quyền (authorization)**.
3. Nhận biết ý nghĩa thực tiễn của AAL1, AAL2, AAL3; giải thích vì sao không thể suy ra AAL chính thức chỉ từ tên phương thức hoặc số màn hình đăng nhập.
4. Phân tích tác động của phishing, replay, đánh cắp token/phiên, thiết bị bị chiếm và các luồng khôi phục yếu lên mức bảo đảm.
5. Thiết kế quyết định **step-up authentication** theo rủi ro, độ mới của lần xác thực và quyền trên tài nguyên.
6. Mô tả cách ứng dụng nhận, kiểm tra và sử dụng **ngữ cảnh xác thực** từ máy chủ hoặc Identity Provider mà không tin dữ liệu tự khai của client.

## 1. Vì sao cần đánh giá mức bảo đảm xác thực?

Giả sử một hệ thống cung cấp ba thao tác:

- Đọc thông báo công khai.
- Xem hồ sơ cá nhân và lịch sử thanh toán.
- Thay phương thức khôi phục, thêm khóa đăng nhập mới hoặc chuyển một khoản tiền lớn.

Việc dùng một câu trả lời duy nhất — **“đã đăng nhập”** — cho cả ba thao tác bỏ qua sự khác biệt về hậu quả nếu tài khoản bị mạo danh. Một phiên chỉ được lập bằng mật khẩu có thể thích hợp cho một số tác vụ nhưng không đáp ứng chính sách của thao tác nhạy cảm. Ngược lại, yêu cầu thêm thử thách nặng nề ở mọi thao tác làm tăng ma sát và có thể dẫn người dùng tới các thói quen kém an toàn.

**Authentication assurance (mức bảo đảm xác thực)** mô tả mức độ tin cậy đạt được từ **quá trình xác thực**, trong phạm vi các mối đe dọa và các yêu cầu bảo mật đã định. Nói cách khác, hệ thống xem xét liệu việc kiểm chứng authenticator có đủ mạnh để tin rằng chủ thể yêu cầu đang kiểm soát những authenticator đã liên kết với danh tính được khai báo hay không.

Mức bảo đảm không phải xác suất tuyệt đối kiểu **“chắc chắn 99,9% đây là Minh”**. Nó cũng không chứng minh:

- Chủ tài khoản chính là người có danh tính pháp lý ngoài đời nếu chưa qua quy trình kiểm chứng danh tính phù hợp.
- Người dùng có quyền đọc hoặc sửa mọi tài nguyên chỉ vì đăng nhập thành công.
- Thiết bị, trình duyệt, mạng và mọi phần mềm đều không bị tấn công.
- Người đang điều khiển phiên tại thời điểm hiện tại vẫn là người đã xác thực trước đó.
- Một token chưa hết hạn chắc chắn chưa bị đánh cắp.

Authentication assurance là **một thành phần trong quyết định tin cậy**, bên cạnh kiểm chứng danh tính, phân quyền, trạng thái tài khoản, tính toàn vẹn phiên và đánh giá rủi ro giao dịch.

## 2. Các khái niệm cần phân biệt

| Khái niệm | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **Identification (định danh)** | Chủ thể khai hoặc được tham chiếu là tài khoản nào? | Mã người dùng nội bộ, cặp issuer–subject. |
| **Identity proofing (kiểm chứng danh tính ban đầu)** | Cơ sở nào liên kết hồ sơ số với người/tổ chức ngoài đời? | Quy trình đối chiếu bằng chứng khi mở tài khoản chịu yêu cầu định danh. |
| **Authentication (xác thực)** | Chủ thể có trình được bằng chứng hợp lệ của credential đã đăng ký không? | Xác minh mật khẩu hoặc chữ ký WebAuthn trên thử thách mới. |
| **Authentication assurance / AAL** | Quá trình xác thực đạt mức bảo đảm nào theo tập yêu cầu cụ thể? | Luồng đạt chính sách tương ứng AAL2 sau khi đáp ứng toàn bộ điều kiện. |
| **Federation assurance / FAL** | Bằng chứng và kết quả xác thực được chuyển giữa IdP và ứng dụng tin cậy đến mức nào? | Cơ chế bảo vệ assertion/token trong liên kết danh tính. |
| **Authorization (phân quyền)** | Chủ thể đã được xác thực được làm gì với tài nguyên này? | Chỉ giảng viên của lớp mới được sửa điểm lớp đó. |
| **Session assurance (bảo đảm tiếp diễn của phiên)** | Có đủ căn cứ để tiếp tục tin và sử dụng phiên hiện tại không? | Kiểm tra thời hạn, tính toàn vẹn phiên, hoạt động bất thường và yêu cầu xác thực lại. |

Một người có thể xác thực bằng phương thức mạnh vào **một tài khoản bút danh** mà không hề cung cấp giấy tờ cá nhân. Khi đó authentication assurance có thể cao trong khi mức kiểm chứng danh tính ngoài đời vẫn thấp hoặc không áp dụng. Một nhân viên đã được kiểm chứng danh tính rất kỹ cũng có thể đăng nhập bằng mật khẩu bị lộ: kiểm chứng danh tính ban đầu không bù được một lần xác thực yếu.

**Nguyên tắc:** không dùng AAL thay cho IAL, không dùng MFA thay cho phân quyền và không dùng kết quả xác thực cũ như bằng chứng rằng mọi hành động về sau đều an toàn.

## 3. IAL, AAL và FAL: ba chiều khác nhau

Trong họ hướng dẫn danh tính số NIST SP 800-63, ba nhóm khái niệm thường được nhắc tới là:

- **IAL — Identity Assurance Level:** mức bảo đảm của **quá trình kiểm chứng danh tính** và việc liên kết chủ thể thực với hồ sơ danh tính. Đây là câu hỏi về *ai được đăng ký*.
- **AAL — Authentication Assurance Level:** mức bảo đảm của **quá trình chứng minh quyền kiểm soát authenticator** khi đăng nhập hoặc xác thực lại. Đây là câu hỏi về *ai đang sử dụng credential đã đăng ký*.
- **FAL — Federation Assurance Level:** mức bảo đảm trong **việc truyền và sử dụng khẳng định danh tính** giữa nhà cung cấp danh tính (IdP) và ứng dụng tiếp nhận (RP). Đây là câu hỏi về *kết quả xác thực được chuyển giao tin cậy thế nào*.

Có thể hình dung:

~~~mermaid
flowchart LR
    P["Người / chủ thể"] -->|"Đăng ký và kiểm chứng khi cần"| I["Hồ sơ danh tính"]
    I -->|"IAL: độ tin cậy của liên kết danh tính"| R["Tài khoản và authenticator"]
    P -->|"Trình bằng chứng đã đăng ký"| V["Bộ kiểm chứng xác thực"]
    R --> V
    V -->|"AAL: bảo đảm của lần xác thực"| D["IdP hoặc dịch vụ xác thực"]
    D -->|"FAL: chuyển giao khẳng định danh tính"| A["Ứng dụng tiếp nhận"]
    A -->|"Kiểm tra quyền truy cập"| T["Tài nguyên / thao tác"]
~~~

Đây là sơ đồ học thuật về **những câu hỏi bảo đảm riêng biệt**. Một ứng dụng có thể tự xác thực, không dùng liên kết danh tính, nên FAL không nhất thiết xuất hiện trong kiến trúc đó. Việc phân loại chính thức theo tiêu chuẩn phải xét đúng phiên bản, hồ sơ áp dụng và tất cả yêu cầu tương ứng; sơ đồ không tự cấp mức tuân thủ cho hệ thống.

### Ví dụ độc lập giữa ba chiều

Một công ty tạo tài khoản nhân viên sau khi kiểm tra hồ sơ nhân sự, rồi cho đăng nhập bằng mật khẩu đơn lẻ vào ứng dụng nội bộ. Thông tin nhân sự có thể được kiểm chứng tốt, nhưng **bảo đảm của lần đăng nhập** vẫn bị giới hạn bởi cách xác thực mật khẩu và các kiểm soát đi kèm.

Ngược lại, một diễn đàn cho phép dùng biệt danh và đăng nhập bằng passkey. Phương thức này có thể cung cấp bằng chứng xác thực mạnh, nhưng không chứng minh biệt danh đó tương ứng với một người có tên pháp lý nào.

Khi diễn đàn dùng IdP ngoài, ứng dụng còn phải kiểm chứng kết quả liên kết đúng nguồn và đối tượng nhận. **Mạnh ở IAL hoặc AAL không tự động bảo đảm mạnh ở FAL**.

## 4. Các mức AAL thường gặp

Trong cách gọi của NIST SP 800-63, AAL thường được chia thành **AAL1, AAL2 và AAL3**. Bảng sau nhằm xây dựng trực giác; **không thay thế yêu cầu chuẩn của phiên bản tiêu chuẩn áp dụng**.

| Mức | Ý nghĩa khái quát | Khác biệt cần hiểu | Ví dụ mang tính minh họa |
| --- | --- | --- | --- |
| **AAL1** | Cung cấp mức bảo đảm cơ bản về quyền kiểm soát authenticator. | Có thể dùng một yếu tố nếu đáp ứng các điều kiện của mức này. | Luồng đăng nhập bằng mật khẩu với kiểm chứng, quản lý và bảo vệ phù hợp. |
| **AAL2** | Mức bảo đảm cao hơn, cần xác thực đa yếu tố đáp ứng yêu cầu liên quan. | Hai yếu tố phải được thực thi đúng, cùng với các kiểm soát về authenticator, verifier, kết nối, vòng đời và phiên. | Mật khẩu + TOTP hoặc authenticator đa yếu tố đạt điều kiện tương ứng, sau khi xác minh toàn bộ yêu cầu. |
| **AAL3** | Mức bảo đảm cao với yêu cầu nghiêm ngặt hơn về authenticator, bằng chứng mật mã, chống mạo danh verifier và bảo vệ khóa. | Bao gồm bảo đảm đa yếu tố và cơ chế mật mã dựa trên phần cứng đáp ứng yêu cầu mức cao; chống phishing là trọng tâm. | Luồng dùng authenticator phần cứng thích hợp, đáp ứng đầy đủ yêu cầu của hồ sơ AAL3. |

**Cẩn trọng với kết luận theo tên sản phẩm:** “có passkey”, “có khóa bảo mật”, “có sinh trắc” hay “có hai lớp” **không đủ** để tuyên bố đạt AAL2/AAL3. Cần kiểm tra loại authenticator, khả năng xuất/đồng bộ khóa, cách xác minh người dùng, quy trình gắn và khôi phục, bảo vệ verifier, phiên và tất cả điều kiện của tiêu chuẩn/hồ sơ áp dụng.

Ví dụ, một passkey có thể dùng khóa công khai rất mạnh và chống phishing, nhưng việc khóa được đồng bộ giữa thiết bị, bảo vệ nền tảng và chính sách xác minh người dùng ảnh hưởng đến đánh giá mức bảo đảm. Không nên tự gán **“mọi passkey đều AAL3”**.

### 4.1 AAL là mức bảo đảm theo yêu cầu, không phải thang điểm tùy ý

Không nên biến AAL thành thang điểm tự phát, chẳng hạn “password = 20 điểm, OTP = 40 điểm, Face ID = 50 điểm, cộng được 90 nên AAL3”. Hai bằng chứng có thể phụ thuộc vào cùng thiết bị bị chiếm hoặc cùng kênh khôi phục yếu. Điểm số nội bộ phục vụ phân tích rủi ro **không tương đương** phân loại AAL chính thức.

Để dùng nhãn AAL chuẩn, một tổ chức cần chọn **phiên bản tiêu chuẩn, phạm vi hệ thống, chính sách và hồ sơ triển khai** rồi đánh giá toàn bộ yêu cầu. Nếu chưa đánh giá, có thể mô tả **“mức bảo đảm do sản phẩm quy định”** như *cơ bản, tăng cường, đặc quyền* thay vì mượn nhãn chứng nhận.

### 4.2 AAL không phải đặc quyền

AAL3 không cấp quyền quản trị. Người dùng có thể xác thực ở mức rất cao nhưng vẫn chỉ có quyền đọc hồ sơ của mình. Ngược lại, tài khoản quản trị được phân quyền rộng mà đăng nhập yếu có thể trở thành điểm rủi ro lớn. Hệ thống cần kiểm tra **cả mức xác thực lẫn quyền cụ thể**.

## 5. Điều gì quyết định mức bảo đảm?

Một hệ thống không chỉ xét số lượng bước đăng nhập. Những thành phần có ảnh hưởng là:

1. **Loại và chất lượng authenticator:** mật khẩu, OTP, thiết bị mật mã, authenticator đa yếu tố, phần cứng giữ khóa.
2. **Độ độc lập của các yếu tố:** hai bí mật đều thuộc nhóm *điều biết* không tạo MFA đúng nghĩa; hai yếu tố phụ thuộc cùng bí mật phục hồi có thể cùng thất bại.
3. **Phương thức và ràng buộc mật mã:** thử thách mới, chữ ký/MAC đúng, liên kết origin/RP ID và ngữ cảnh nhận, kiểm chứng khóa và chống replay.
4. **Quy trình đăng ký/gắn kết:** ai được gắn credential với tài khoản, điều kiện thay đổi authenticator, ghi nhận và thông báo.
5. **Bảo vệ verifier:** mật khẩu được băm chuyên dụng và có salt, bí mật được bảo vệ, có giới hạn thử sai, kết nối bảo mật và kiểm tra bằng chứng ở máy chủ.
6. **Bảo đảm tiếp diễn của phiên:** token/cookie được bảo vệ, thời hạn phù hợp, cơ chế thu hồi, xác thực lại cho thao tác nhạy cảm.
7. **Khôi phục tài khoản:** quy trình thay credential không vô tình tạo đường vòng yếu hơn luồng đăng nhập.
8. **Ngữ cảnh rủi ro:** hành động cần bảo vệ, môi trường thiết bị, khả năng tấn công thực tế và tín hiệu bất thường.

Chẳng hạn, mật khẩu + TOTP thường tạo hai nhóm yếu tố, nhưng cả hai có thể bị trang phishing theo thời gian thực thu thập. Một authenticator WebAuthn chống phishing có thể giảm rủi ro đó, song không tự chặn việc token phiên bị đánh cắp hoặc phần mềm độc hại chiếm thiết bị.

### Phân biệt các cơ chế phòng vệ

| Thuộc tính bảo vệ | Nguy cơ được giảm | Điều **không** tự động được giải quyết |
| --- | --- | --- |
| **MFA** | Kẻ chỉ đánh cắp được một yếu tố khó đăng nhập hơn. | Phishing thời gian thực, lạm dụng khôi phục, chiếm phiên. |
| **Chống phishing** | Trang giả khó lấy bằng chứng dùng được cho dịch vụ thật. | XSS, thiết bị bị chiếm, lộ token sau đăng nhập. |
| **Chống replay** | Bằng chứng cũ khó được chấp nhận lần nữa. | Bằng chứng bị lấy và dùng ngay trong phiên hợp lệ nếu không có ràng buộc bổ sung. |
| **Bảo vệ phiên/token** | Giảm nguy cơ tái sử dụng trái phép quyền truy cập đã cấp. | Không thay thế xác thực ban đầu hoặc phân quyền. |
| **Step-up** | Tăng mức kiểm chứng ở thời điểm rủi ro cao. | Không sửa được lỗi cấp quyền hoặc liên kết tài khoản sai. |
| **Kiểm chứng danh tính** | Củng cố liên kết tài khoản với chủ thể đúng. | Không thay thế authenticator mạnh ở mỗi lần đăng nhập. |

## 6. MFA có phải luôn cho mức bảo đảm cao?

MFA đòi hỏi **ít nhất hai loại yếu tố xác thực độc lập theo thiết kế**, thường là:

- **Điều biết:** mật khẩu hoặc PIN bí mật.
- **Thứ sở hữu:** khóa bảo mật, thiết bị giữ credential, ứng dụng tạo mã một lần đã đăng ký.
- **Đặc điểm vốn có:** sinh trắc học được kiểm tra theo cơ chế phù hợp.

Ví dụ: mật khẩu + mã TOTP có thể là MFA; mật khẩu + một PIN khác gửi lên máy chủ vẫn thường là **hai bí mật cùng nhóm**. Một authenticator có thể cung cấp nhiều yếu tố trong một lần thao tác, ví dụ khóa riêng được bảo vệ bằng xác minh người dùng cục bộ; cần xem cách authenticator và verifier thực thi điều kiện cụ thể.

Bảng dưới đây nhấn mạnh mối quan hệ giữa phương thức và mức bảo đảm:

| Phương thức | Tính chất chính | Câu hỏi cần kiểm tra trước khi đánh giá |
| --- | --- | --- |
| Mật khẩu đơn lẻ | Dựa vào điều biết; dễ bị đoán, lộ và phishing. | Lưu trữ, kiểm soát thử sai, chính sách mật khẩu và bảo vệ kết nối ra sao? |
| Mật khẩu + SMS OTP | Hai nguồn bằng chứng thường được dùng cho MFA; rủi ro SIM swap, tái cấp số và phishing. | Có phù hợp mức rủi ro không, và kênh SMS được coi là đáng tin đến đâu? |
| Mật khẩu + TOTP | Thường là MFA; mã vẫn có thể bị chuyển tiếp khi phishing. | Bí mật TOTP, cửa sổ thời gian, thử sai và dùng lại mã được quản lý ra sao? |
| Push approval | Có thể chứng minh quyền sở hữu ứng dụng/thiết bị đăng ký. | Có chống MFA fatigue, đối chiếu số và hiển thị đúng ngữ cảnh không? |
| Passkey/WebAuthn | Mật mã khóa công khai, ràng buộc RP/origin; thường chống phishing tốt. | Loại authenticator, user verification, tính xuất được của khóa và quản lý vòng đời thế nào? |
| Khóa bảo mật phần cứng | Có thể bảo vệ khóa riêng tốt hơn ở một số kịch bản. | Có đáp ứng yêu cầu phần cứng, đa yếu tố và toàn bộ profile bảo đảm cần đạt không? |
| Chứng chỉ máy/mTLS | Có thể chứng minh dịch vụ hoặc thiết bị kiểm soát khóa riêng. | Danh tính được xác thực là **dịch vụ/thiết bị** hay **người dùng cuối**? |

Một chứng chỉ mTLS giữa hai dịch vụ không tự chứng minh con người thao tác ở đầu cuối đã đạt MFA. Hãy xác định **chủ thể** mà phép kiểm chứng hướng tới trước khi đánh giá mức bảo đảm.

## 7. Chống phishing và replay thay đổi mức tin cậy thế nào?

### 7.1 Phishing thời gian thực

Kẻ tấn công dựng trang đăng nhập giả, thu mật khẩu và OTP, rồi chuyển ngay tới dịch vụ thật. Dù người dùng đã thực hiện hai bước, attacker vẫn có thể chiếm một phiên hợp lệ. Đây là lý do MFA sử dụng OTP thường **không đồng nghĩa** với phương thức chống phishing.

Với WebAuthn/FIDO2, authenticator ký thử thách với ràng buộc tới **Relying Party ID** và ngữ cảnh origin theo giao thức. Website giả ở origin khác không thể tùy tiện thu được assertion dùng cho RP thật. Tuy vậy, rủi ro chiếm thiết bị, khai thác ứng dụng, chiếm phiên và khôi phục yếu vẫn tồn tại.

**Bài học:** chọn phương thức theo kẻ tấn công có khả năng làm gì, không chỉ theo số yếu tố.

### 7.2 Replay

**Replay** xảy ra khi một thông điệp hoặc bằng chứng hợp lệ bị ghi lại rồi phát lại ở thời điểm khác. Với thử thách–phản hồi, verifier phải phát **challenge ngẫu nhiên mới** và kiểm chứng chữ ký/phản hồi gắn với challenge đó, tài khoản, RP và các ràng buộc thích hợp.

Với TOTP, mã chỉ có hiệu lực trong một khoảng thời gian ngắn nhưng có thể bị dùng ngay. Verifier cần giới hạn thử sai và xử lý **không chấp nhận lại mã đã dùng thành công trong cửa sổ áp dụng**. Độ mới của một challenge không tự bảo vệ token tiếp theo nếu token bị lộ.

### 7.3 Tấn công dựa trên phiên

Sau khi đăng nhập, hệ thống thường cấp **cookie phiên hoặc token**. Một bearer token còn hiệu lực có thể trao quyền cho ai giữ nó, bất kể người đó có authenticator ban đầu hay không.

Cần xác minh chữ ký/MAC nếu áp dụng, issuer, audience, hạn dùng, trạng thái và điều kiện chấp nhận, đồng thời bảo vệ cookie web bằng các thuộc tính thích hợp như **Secure**, **HttpOnly**, **SameSite** cùng biện pháp chống CSRF/XSS. Cookie có HttpOnly không làm XSS vô hại; MFA cũng không cứu được một phiên bị kẻ khác lấy mất.

Vì vậy, bảo đảm xác thực phải gắn với **cách duy trì và chấm dứt phiên**, không dừng ở màn hình đăng nhập.

## 8. “Độ mới” của xác thực và step-up authentication

Mức bảo đảm của lần đăng nhập và **thời điểm đăng nhập** là hai khía cạnh khác nhau.

Giả sử người dùng xác thực bằng phương thức mạnh lúc 8 giờ sáng, để máy tính mở, đến 16 giờ ứng dụng nhận yêu cầu thay khóa khôi phục. Một lần xác thực đạt mức cao **không tự chứng minh** người đang điều khiển trình duyệt tám giờ sau là cùng người đã thực hiện nó.

**Step-up authentication** là yêu cầu chủ thể chứng minh lại hoặc bổ sung bằng chứng đáp ứng chính sách cao hơn trước một thao tác nhạy cảm. **Reauthentication** nhấn mạnh việc xác thực lại để tăng độ mới của bằng chứng; step-up có thể bao gồm xác thực lại bằng phương thức mạnh hơn.

Ví dụ:

| Thao tác | Chính sách minh họa của một sản phẩm | Lý do |
| --- | --- | --- |
| Xem trang thông tin công khai | Không cần phiên người dùng. | Không có tài sản cá nhân cần gắn với danh tính. |
| Xem thông tin cá nhân | Có phiên đã xác thực, đúng chủ thể và quyền. | Cần bảo vệ dữ liệu riêng tư. |
| Tải dữ liệu nhạy cảm | Yêu cầu ngữ cảnh xác thực phù hợp, phiên mới và đánh giá rủi ro nếu cần. | Rủi ro lộ dữ liệu lớn hơn. |
| Thay email khôi phục / thêm passkey | Xác thực lại đủ mạnh, kiểm tra quyền quản lý tài khoản và thông báo thay đổi. | Hành động có thể chuyển quyền kiểm soát tài khoản. |
| Duyệt thanh toán lớn | Phương thức chống phishing phù hợp, xác nhận thông tin giao dịch khi cần và phân quyền nghiệp vụ. | Giảm rủi ro chiếm tài khoản, lừa người dùng phê duyệt nhầm. |
| Cấp quyền quản trị hệ thống | Chính sách bảo đảm cao, phiên ngắn, kiểm tra vai trò và tín hiệu rủi ro. | Hậu quả lớn nếu đặc quyền bị lạm dụng. |

**Các chính sách trong bảng là ví dụ để học thiết kế, không phải quy tắc AAL bắt buộc cho mọi ngành.** Cách chọn ngưỡng thực tế cần dựa trên phân tích rủi ro, quy định và trải nghiệm người dùng của sản phẩm cụ thể.

### Không cho phép hạ mức bằng một đường vòng

Nếu ứng dụng yêu cầu passkey chống phishing cho việc đổi MFA nhưng cho phép một mã email đơn lẻ để **gỡ tất cả MFA**, kẻ tấn công sẽ chọn đường email. Cần xem xét:

- Cơ chế khôi phục bằng chứng nào, thời hạn bao lâu, giới hạn thử và thông báo ra sao?
- Ai được thêm, thay và xóa authenticator?
- Có thời gian chờ, kiểm tra bổ sung hoặc quy trình hỗ trợ được kiểm soát cho trường hợp rủi ro rất cao không?
- Khi credential bị thay, phiên và token cũ còn được chấp nhận không?

**Mức bảo đảm sử dụng được trong thực tế bị ảnh hưởng bởi đường truy cập và khôi phục yếu nhất mà kẻ tấn công có thể khai thác.**

## 9. Mô hình hóa chính sách xác thực ở ranh giới tin cậy

Một yêu cầu API đi qua các thành phần với mức tin cậy khác nhau:

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant C as Browser / Mobile client
    participant I as Bộ xác thực / IdP
    participant A as API / ứng dụng
    participant P as Chính sách và quyền
    U->>C: Yêu cầu hành động nhạy cảm
    C->>A: Gửi yêu cầu kèm phiên/token
    A->>A: Kiểm tra phiên/token và ánh xạ subject
    A->>P: Truy vấn quyền + mức bảo đảm + độ mới + rủi ro
    alt Đạt điều kiện
        P-->>A: Cho phép về mặt chính sách
        A->>A: Thực thi kiểm tra nghiệp vụ
        A-->>C: Kết quả
    else Cần xác thực tăng cường
        P-->>A: Yêu cầu step-up
        A-->>C: Chuyển tới luồng xác thực phù hợp
        C->>I: Thực hiện thử thách bằng authenticator
        I-->>C: Kết quả thông qua giao thức tin cậy
        C->>A: Gửi lại yêu cầu có ngữ cảnh mới
        A->>A: Kiểm chứng kết quả, mức bảo đảm và quyền
    else Không có quyền
        P-->>A: Từ chối
        A-->>C: Từ chối truy cập
    end
~~~

Sơ đồ lược giản; trong kiến trúc thực tế, token/authorization code và callback phải được xử lý theo giao thức phù hợp. Điều quan trọng là **API hoặc thành phần tin cậy**, chứ không phải giao diện, xác định:

- **Chủ thể đã được xác thực:** lấy từ phiên hoặc token đã xác minh, không tin userId client tự gửi.
- **Mức bảo đảm có căn cứ:** dựa trên kết quả thực thi ở bộ xác thực và chính sách được tin cậy, không dựa vào cờ client tự đặt là **mfaPassed=true**.
- **Độ mới:** thời điểm xác thực cuối đáp ứng yêu cầu; khác với thời điểm token mới được refresh hoặc request vừa tới.
- **Quyền truy cập:** vai trò và quyền trên hành động/tài nguyên cụ thể.
- **Ngữ cảnh rủi ro:** hành động, trạng thái tài khoản, cảnh báo về phiên và những tín hiệu được sử dụng phù hợp.

### Giả mã kiểm tra trước thao tác nhạy cảm

~~~text
function authorizeSensitiveAction(request, resource):
    principal = verifySessionOrTokenOnServer(request)
    if principal is absent:
        return DENY_UNAUTHENTICATED

    if not isAccountActive(principal.subjectId):
        return DENY

    if not hasPermission(principal.subjectId, resource, "modify"):
        return DENY_FORBIDDEN

    assurance = loadTrustedAuthenticationContext(principal.sessionId)

    if assurance is absent or not meetsRequiredAssurance(
            assurance, policyFor(resource, "modify")):
        return STEP_UP_REQUIRED

    if not isRecentEnough(
            assurance.lastQualifyingAuthenticationAt,
            policyFor(resource, "modify").maxAuthenticationAge):
        return REAUTHENTICATION_REQUIRED

    if indicatesHighRisk(request, principal, resource):
        return APPLY_ADDITIONAL_VERIFICATION_OR_DENY

    return ALLOW
~~~

Đây là **mã giả**, không phải API hoặc thư viện triển khai thực tế. Chính sách phải xác định rõ thế nào là **meetsRequiredAssurance**, thay vì cộng điểm các bước xác thực tùy ý. Kiểm tra quyền vẫn được thực hiện riêng. Sau khi step-up, máy chủ phải kiểm chứng ngữ cảnh mới và ràng buộc nó với chủ thể/phiên cùng hành động đang được bảo vệ.

## 10. Khi dùng SSO/OIDC, ứng dụng biết AAL bằng cách nào?

Một ứng dụng dựa vào Identity Provider (IdP) có thể nhận thông tin về lần xác thực thông qua khẳng định danh tính hoặc token theo giao thức liên kết.

Trong **OpenID Connect (OIDC)**, các claim thường gặp gồm:

| Claim/khái niệm | Ý nghĩa thường gặp | Điều ứng dụng phải lưu ý |
| --- | --- | --- |
| **iss** | Nhà phát hành. | Kiểm chứng đúng IdP đã cấu hình. |
| **sub** | Mã chủ thể trong phạm vi issuer. | Dùng cùng issuer để ánh xạ đúng tài khoản; email không phải khóa thay thế mặc định. |
| **aud** | Đối tượng nhận token. | Chỉ chấp nhận token dành cho ứng dụng/API tương ứng. |
| **exp**, **iat** | Thời hạn hết hiệu lực và thời điểm phát hành. | Token mới phát hành không có nghĩa người dùng vừa xác thực lại. |
| **auth_time** | Thời điểm người dùng được xác thực theo ngữ nghĩa giao thức. | Hữu ích để kiểm tra độ mới nếu được cung cấp và được tin cậy đúng cách. |
| **acr** | Tham chiếu lớp ngữ cảnh xác thực. | Cần có thỏa thuận rõ về giá trị và mức bảo đảm mà nó đại diện. |
| **amr** | Thông tin tham chiếu phương thức xác thực. | Không tự suy ra tuân thủ AAL chỉ từ tên phương thức hoặc số phần tử. |
| **nonce / state** | Thành phần bảo vệ ngữ cảnh phiên giao thức trong các luồng áp dụng. | Kiểm chứng và đối chiếu đúng luồng; không hoán đổi vai trò giữa các tham số. |

Ứng dụng cần xác minh chữ ký, thuật toán được chấp nhận, issuer, audience, thời hạn, nonce/state và những điều kiện khác tùy luồng OIDC. Đối với authorization code, phải sử dụng cơ chế bảo vệ callback, state và PKCE khi áp dụng. **OAuth 2.0 access token** dùng để cấp quyền truy cập tài nguyên; không mặc nhiên thay thế **OIDC ID token** làm bằng chứng đăng nhập.

### Ví dụ về claim và ý nghĩa giới hạn

Giả sử IdP phát hành ID token đã được ứng dụng kiểm chứng với các thông tin khái niệm:

~~~json
{
  "iss": "https://id.example.test",
  "sub": "opaque-user-42",
  "aud": "learning-app",
  "auth_time": 1700000000,
  "acr": "urn:example:auth:high",
  "amr": ["hwk", "pin"]
}
~~~

Đây là **dữ liệu minh họa**, không phải token ký hợp lệ, thời điểm hiện hành hay nhãn AAL chuẩn.

Ứng dụng chỉ được diễn giải **urn:example:auth:high** theo một **hợp đồng chính sách đã thống nhất với IdP**, sau khi token và ngữ cảnh giao thức được xác minh. Chuỗi có chữ “high” không tự chứng minh đạt AAL3. Danh sách **amr** chỉ gợi ý phương thức được dùng; muốn đánh giá AAL cần căn cứ vào yêu cầu của profile và việc thực thi thực tế.

**Bẫy độ mới:** IdP có thể phát một token mới từ phiên SSO cũ mà không yêu cầu người dùng xác thực lại. Lấy **iat** làm thời điểm đăng nhập mới có thể khiến ứng dụng bỏ qua yêu cầu xác thực lại. Nếu cần độ mới, cần cơ chế và claim có ngữ nghĩa xác thực được tin cậy (chẳng hạn auth_time) và chính sách yêu cầu xác thực lại theo giao thức.

## 11. Quản lý vòng đời authenticator quyết định mức bảo đảm thực tế

Mức bảo đảm tại thời điểm đăng nhập có thể bị làm suy yếu bởi cách tài khoản được đăng ký, thay credential và khôi phục:

| Giai đoạn | Điều cần kiểm soát | Hậu quả nếu sai |
| --- | --- | --- |
| **Enrollment ban đầu** | Đúng tài khoản, thủ tục gắn authenticator, chống tự cấp trái phép. | Kẻ tấn công đăng ký yếu tố cho tài khoản của nạn nhân. |
| **Xác thực thường ngày** | Kiểm tra bằng chứng, chống thử sai/phishing/replay, cập nhật trạng thái và ngữ cảnh. | Chấp nhận mật khẩu/OTP sai hoặc yếu tố chưa đăng ký. |
| **Thêm thiết bị hoặc passkey** | Yêu cầu quyền quản lý tài khoản và mức xác thực đủ mới, đủ mạnh. | Kẻ đang giữ phiên bị đánh cắp gắn thêm khóa để duy trì truy cập. |
| **Đổi mật khẩu / yếu tố** | Thực hiện xác thực lại và gửi thông báo thay đổi phù hợp. | Chuyển quyền kiểm soát tài khoản âm thầm. |
| **Mất authenticator** | Quy trình khôi phục có bằng chứng phù hợp và kiểm soát lạm dụng. | Bỏ qua yếu tố mạnh qua đường quên mật khẩu. |
| **Khóa hoặc đóng tài khoản** | Thu hồi credential, xử lý phiên/token và quyền theo chính sách. | Tài khoản không còn hợp lệ vẫn truy cập được. |
| **Đánh giá định kỳ** | Kiểm tra nhật ký, trạng thái thiết bị, phương thức cũ và nguyên nhân thất bại. | Duy trì đường truy cập lỗi thời không được phát hiện. |

### Tình huống khôi phục làm mất ý nghĩa MFA

Một quản trị viên có khóa bảo mật mạnh nhưng có thể thay toàn bộ credential qua email khôi phục không được bảo vệ thích hợp. Kẻ tấn công chiếm email, yêu cầu reset, đăng ký khóa riêng của mình rồi đăng nhập.

Mức mạnh của khóa ban đầu **không giải quyết được** điểm yếu ở quy trình **thay thế authenticator**. Để xây dựng bảo đảm xuyên suốt, phải xác định rõ ai được thay credential, căn cứ kiểm chứng, thông báo thay đổi, độ trễ hoặc kiểm tra bổ sung khi cần và chính sách vô hiệu hóa các phiên cũ.

## 12. Mức bảo đảm và chính sách dựa trên rủi ro

Không phải mọi ứng dụng đều cần một AAL cố định cho mọi hành động. Một hệ thống có thể xác định **mức tối thiểu** cho từng nhóm hành động và yêu cầu xác thực bổ sung khi tín hiệu rủi ro thay đổi.

Quy trình thiết kế thực hành:

1. **Xác định tài sản và hậu quả:** dữ liệu công khai, thông tin cá nhân, tiền, quyền quản trị, khóa dịch vụ.
2. **Liệt kê chủ thể:** người dùng, quản trị viên, đối tác, dịch vụ tự động, thiết bị.
3. **Phác họa mối đe dọa:** phishing, đoán mật khẩu, credential stuffing, chiếm phiên, replay, mạo danh IdP, chiếm đường khôi phục.
4. **Chọn mức bảo đảm và profile thích hợp:** nếu dùng AAL chính thức, chọn phiên bản tiêu chuẩn và đánh giá tất cả yêu cầu liên quan; nếu dùng mức nội bộ, định nghĩa điều kiện một cách kiểm chứng được.
5. **Thiết kế luồng đăng ký và khôi phục:** đường thay authenticator phải bảo vệ tương xứng.
6. **Quy định độ mới và phiên:** phiên tối đa bao lâu, khi nào cần reauthentication, xử lý token bị lộ hoặc tài khoản bị khóa.
7. **Đặt điểm thực thi ở server/IdP:** kiểm tra phiên, ngữ cảnh xác thực, quyền và rủi ro tại thành phần có thẩm quyền.
8. **Theo dõi hiệu quả:** đo tỷ lệ hoàn tất hợp lệ, lỗi xác thực, tín hiệu tấn công và trường hợp người dùng bị khóa nhầm; điều chỉnh chính sách dựa trên bằng chứng.

### Ma trận quyết định minh họa

| Rủi ro thao tác | Ví dụ | Nguyên tắc đặt chính sách |
| --- | --- | --- |
| Thấp | Đọc tài liệu công khai | Có thể không cần đăng nhập. |
| Trung bình | Xem hồ sơ cá nhân | Cần phiên hợp lệ và phân quyền; chọn phương thức phù hợp dữ liệu. |
| Cao | Đổi email, thêm authenticator | Xác thực lại, bảo vệ luồng enrollment và thông báo. |
| Rất cao | Cấp đặc quyền, giao dịch tài chính quan trọng | Ưu tiên phương thức chống phishing, mức bảo đảm mạnh, độ mới và kiểm soát nghiệp vụ bổ sung. |

**Ma trận này là minh họa cho tư duy đánh giá rủi ro**, không chứng minh thao tác nào mặc nhiên cần một AAL được chuẩn hóa nhất định. Nhiều hệ thống có yêu cầu chuyên ngành hoặc pháp lý riêng.

### Mức bảo đảm và tín hiệu thích ứng

IP, vị trí, thiết bị, giờ truy cập, hành vi và tình trạng rủi ro có thể hỗ trợ quyết định xác thực thích ứng. Tuy nhiên:

- IP hoặc vị trí không tự chứng minh danh tính của một người.
- Máy quen không thay thế credential; máy lạ không mặc nhiên là kẻ tấn công.
- Một thuật toán phát hiện bất thường không được tạo đường bỏ qua kiểm tra bắt buộc.
- Cần xem xét sai số, quyền riêng tư, khả năng tiếp cận và khôi phục cho người dùng hợp lệ.

Hệ thống có thể dùng tín hiệu rủi ro để **tăng yêu cầu xác thực hoặc chặn thao tác**, nhưng phải phân biệt tín hiệu môi trường với **yếu tố xác thực được kiểm chứng**.

## 13. Ví dụ thiết kế: nền tảng học tập có giảng viên và quản trị viên

Giả sử một nền tảng học tập có người học, giảng viên và quản trị viên hệ thống. Một người dùng có thể đăng nhập bằng mật khẩu + TOTP, bằng passkey hoặc thông qua SSO của trường.

### 13.1 Chính sách minh họa theo thao tác

| Hành động | Kiểm tra quyền | Yêu cầu bảo đảm bổ sung |
| --- | --- | --- |
| Xem khóa học đã ghi danh | Tài khoản có quyền xem khóa học. | Phiên xác thực còn hợp lệ. |
| Giảng viên nhập điểm | Tài khoản là giảng viên của lớp tương ứng. | Xác thực đủ bảo đảm theo chính sách học vụ. |
| Sửa bảng điểm đã khóa | Có quyền đặc biệt và lý do thay đổi hợp lệ. | Xác thực lại đủ mới, theo dõi và phê duyệt nghiệp vụ khi cần. |
| Quản trị viên thêm tài khoản có quyền cao | Có quyền quản lý tài khoản. | Phương thức chống phishing và bước xác thực tăng cường theo chính sách. |
| Đổi passkey/thiết bị MFA | Có quyền trên chính tài khoản hoặc ủy quyền hỗ trợ đúng quy trình. | Xác thực lại và quy trình gắn credential được bảo vệ. |

Không có bước nào mặc nhiên cho phép **giảng viên lớp A** sửa điểm của **lớp B**, dù giảng viên đã dùng authenticator mạnh. Mức bảo đảm của đăng nhập và quyền trên đối tượng phải được kiểm tra riêng biệt.

### 13.2 Ranh giới tin cậy

Khi trình duyệt gửi yêu cầu **POST /grades/{gradeId}/approve**, máy chủ không được tin payload như:

~~~json
{
  "gradeId": "grade-100",
  "actingUserId": "principal-admin",
  "mfaPassed": true,
  "assurance": "AAL3"
}
~~~

Các trường này là **giá trị do client gửi, có thể bị giả mạo**. Máy chủ phải:

1. Kiểm chứng phiên hoặc token và ánh xạ subject đáng tin cậy.
2. Lấy ngữ cảnh xác thực từ bộ xác thực hoặc assertion IdP đã xác minh.
3. Kiểm tra độ mới và mức bảo đảm yêu cầu cho hành động.
4. Kiểm tra chủ thể có quyền phê duyệt **grade-100**, kể cả lớp/học phần liên quan.
5. Thực thi ràng buộc nghiệp vụ, chống request lặp nếu thao tác yêu cầu, ghi nhận sự kiện an toàn.
6. Khi không đạt mức bảo đảm, yêu cầu step-up qua luồng tin cậy và xác minh kết quả trước khi cho thực hiện.

### 13.3 Khi SSO không cung cấp thông tin mức bảo đảm

Nếu trường đại học chỉ cung cấp **subject** và email đã xác minh nhưng **không cung cấp hoặc không cam kết ngữ nghĩa ngữ cảnh xác thực**, ứng dụng không nên tự khẳng định người dùng đã đạt chính sách xác thực mạnh.

Các lựa chọn có thể là thỏa thuận/chỉnh cấu hình IdP để trả về ngữ cảnh tin cậy, thiết lập luồng step-up mà ứng dụng có khả năng kiểm chứng, hoặc hạn chế thao tác cho đến khi đủ bằng chứng. Đừng đánh đồng **“đăng nhập qua SSO”** với **“đã xác thực mức cao”**.

## 14. Những ngộ nhận phổ biến

**Ngộ nhận 1 — “Mật khẩu + OTP chắc chắn là AAL3.”**  
Không. Hai yếu tố không đồng nghĩa đáp ứng mọi yêu cầu AAL3; OTP vẫn có thể bị phishing và mức AAL chính thức phụ thuộc cả cơ chế, phần cứng và quy trình liên quan.

**Ngộ nhận 2 — “Passkey nào cũng đạt cùng một AAL.”**  
Không. Authenticator, bảo vệ khóa, khả năng đồng bộ/xuất khóa, user verification và các điều kiện của profile khác nhau.

**Ngộ nhận 3 — “AAL3 có nghĩa là danh tính pháp lý chắc chắn đúng.”**  
Không. AAL nói về xác thực; identity proofing và IAL nói về liên kết với danh tính ngoài đời.

**Ngộ nhận 4 — “Đã được IdP xác thực thì ứng dụng có thể tin mọi claim.”**  
Không. Ứng dụng phải kiểm chứng token/assertion đúng nguồn, đối tượng nhận, thời hạn, ngữ cảnh, cấu hình tin cậy và ánh xạ chủ thể.

**Ngộ nhận 5 — “Access token vừa phát hành nghĩa là vừa đăng nhập lại.”**  
Không. Một token mới có thể được cấp từ phiên SSO hoặc refresh token cũ; cần kiểm tra **thời điểm xác thực** theo cơ chế tin cậy.

**Ngộ nhận 6 — “MFA mạnh là đủ, không cần xem cookie phiên.”**  
Không. Bearer token bị đánh cắp có thể bị sử dụng mà không cần trình lại authenticator.

**Ngộ nhận 7 — “Step-up chỉ là hỏi thêm mã OTP.”**  
Không. Step-up phải đáp ứng mức bảo đảm và rủi ro yêu cầu. Một OTP dễ bị phishing có thể không phù hợp trong kịch bản chống phishing.

**Ngộ nhận 8 — “Lưu cờ mfaPassed ở localStorage là đủ.”**  
Không. Client có thể sửa giá trị; bằng chứng về ngữ cảnh xác thực phải đến từ server hoặc IdP đã được tin cậy và được kiểm chứng.

**Ngộ nhận 9 — “Một phiên đạt mức cao thì suốt ngày không phải kiểm tra lại.”**  
Không. Độ mới của lần xác thực, tuổi phiên, thay đổi credential và dấu hiệu rủi ro có thể yêu cầu xác thực lại hoặc thu hồi.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Một người đăng ký bằng biệt danh rồi dùng khóa bảo mật mạnh để đăng nhập. Có thể khẳng định danh tính pháp lý của họ đã được kiểm chứng không?

**Đáp án:** Không. Authentication assurance và identity proofing là hai phạm vi khác nhau. Authenticator mạnh không tự chứng minh tên thật của người sử dụng tài khoản.

**Câu 2.** Vì sao không thể suy ra AAL3 chỉ vì hệ thống có hai màn hình hỏi mật khẩu và OTP?

**Đáp án:** AAL3 có các yêu cầu mạnh hơn việc có hai bước; đánh giá phải xem authenticator, mật mã/phần cứng, chống phishing, verifier, vòng đời và các điều kiện đầy đủ của profile. OTP có thể bị phishing.

**Câu 3.** Một IdP trả về claim **amr = ["pwd", "otp"]**. Ứng dụng có thể tự coi đây là chứng nhận AAL2 không?

**Đáp án:** Không nên. Ứng dụng cần biết ngữ nghĩa claim theo thỏa thuận và cách IdP thực thi chính sách. Chỉ hai nhãn phương thức không chứng minh đáp ứng đầy đủ mọi điều kiện AAL2.

**Câu 4.** Tại sao **iat** của một ID token mới không đủ chứng minh người dùng vừa xác thực lại?

**Đáp án:** **iat** phản ánh thời điểm phát hành token. Token mới có thể được phát từ phiên SSO cũ; yêu cầu về độ mới cần dựa trên thời điểm xác thực đáng tin cậy, chẳng hạn **auth_time** theo ngữ cảnh giao thức phù hợp.

**Câu 5.** Sau khi người dùng đăng nhập bằng passkey, kẻ tấn công đánh cắp cookie phiên. Phương thức chống phishing của passkey có ngăn chắc việc dùng cookie không?

**Đáp án:** Không. Khả năng chống phishing bảo vệ luồng xác thực; cookie phiên là đối tượng có thể bị lợi dụng riêng. Cần bảo vệ và quản lý phiên, phát hiện lạm dụng, thu hồi và xác thực lại khi thích hợp.

**Câu 6.** Một quản trị viên đã dùng phương thức xác thực mạnh nhưng không có quyền sửa dữ liệu của phòng ban khác. API có nên cho phép thao tác chỉ vì mức bảo đảm cao?

**Đáp án:** Không. Authentication assurance và authorization là hai kiểm tra độc lập. API cần xác minh quyền trên tài nguyên cụ thể.

**Câu 7.** Để đổi một authenticator đã đăng ký, hệ thống cho phép liên kết reset qua email duy nhất. Rủi ro chính là gì?

**Đáp án:** Kẻ chiếm email có thể vượt qua luồng xác thực mạnh bằng đường khôi phục yếu, rồi gắn authenticator riêng. Quy trình reset và enrollment phải có bảo đảm tương xứng.

**Câu 8.** Vì sao cần xét lại mức bảo đảm khi thực hiện một hành động nhạy cảm dù phiên hiện tại còn hạn?

**Đáp án:** Vì thời gian đã trôi qua, quyền kiểm soát thiết bị hoặc phiên có thể đã thay đổi, còn hành động có hậu quả cao hơn. Hệ thống có thể cần độ mới, step-up, kiểm tra quyền và rủi ro giao dịch.

**Câu 9.** Hãy nêu sự khác nhau giữa tín hiệu “IP lạ” và một yếu tố xác thực.

**Đáp án:** IP lạ là tín hiệu ngữ cảnh có thể hỗ trợ đánh giá rủi ro; nó không phải bằng chứng đã đăng ký chứng minh quyền sử dụng danh tính như mật khẩu, khóa hoặc authenticator.

**Câu 10.** Nếu ứng dụng không nhận được ngữ cảnh xác thực tin cậy từ IdP, nên xử lý thao tác đặc quyền thế nào?

**Đáp án:** Không tự gán mức bảo đảm cao. Cần thiết lập cơ chế chia sẻ ngữ cảnh có kiểm chứng, thực hiện step-up đáng tin cậy hoặc từ chối/hạn chế thao tác cho đến khi đáp ứng chính sách.

## Ghi nhớ

**Authentication assurance** trả lời câu hỏi: **có bao nhiêu cơ sở để tin một lần xác thực đã chứng minh đúng quyền kiểm soát authenticator của danh tính được khai báo, theo một tập yêu cầu và mối đe dọa xác định?** AAL1, AAL2 và AAL3 là các mức thường dùng trong khung NIST; việc gán một mức chuẩn đòi hỏi đáp ứng **toàn bộ yêu cầu liên quan**, không chỉ thêm yếu tố hoặc chọn một tên công nghệ.

Trong thiết kế thực tế, hãy phân biệt **IAL – AAL – FAL – phân quyền**, ưu tiên phương thức chống phishing theo rủi ro, xem xét replay và chiếm phiên, kiểm soát gắn/thu hồi/khôi phục credential, xác minh kết quả từ IdP tại ranh giới tin cậy, và yêu cầu **xác thực lại hoặc step-up** khi độ mới hay mức bảo đảm của phiên không đủ cho hành động nhạy cảm.
