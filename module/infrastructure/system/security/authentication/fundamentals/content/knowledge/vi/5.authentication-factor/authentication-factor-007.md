# Multi-factor authentication (MFA) — Xác thực đa yếu tố

> **Chương:** Authentication factor  
> **Chủ đề:** Multi-factor authentication  
> **Phạm vi:** Bài học thuộc module `SECURITY_AUTHENTICATION_FUNDAMENTALS`, tập trung vào nguyên lý xác thực danh tính và thiết kế luồng đăng nhập an toàn. MFA được xem trong quan hệ với credential, mật khẩu, passkey, chứng chỉ, token, phiên, liên kết danh tính, khôi phục tài khoản, ranh giới tin cậy, phishing, replay và lạm dụng đăng nhập.

## 1. MFA giải quyết vấn đề gì?

**Multi-factor authentication (MFA)** là cơ chế yêu cầu người dùng chứng minh quyền kiểm soát **ít nhất hai loại yếu tố xác thực khác nhau** trong cùng một quy trình xác thực, theo chính sách của hệ thống. Ý tưởng là nếu một yếu tố bị lộ hoặc bị chiếm, kẻ tấn công vẫn còn phải vượt qua yếu tố độc lập khác.

Ví dụ: một người nhập mật khẩu (thứ họ **biết**) và sử dụng khóa bảo mật có thao tác chạm hoặc xác minh bằng PIN trên thiết bị (thứ họ **có**, có thể kèm xác minh cục bộ). Nếu kẻ tấn công đoán được mật khẩu nhưng không kiểm soát authenticator đã đăng ký, hệ thống không nên cấp phiên đăng nhập.

MFA không phải lời bảo đảm tuyệt đối. Kẻ tấn công có thể lừa người dùng nhập OTP vào website giả, gửi liên tiếp các yêu cầu push để người dùng chấp nhận, chiếm phiên sau khi MFA hoàn tất hoặc lợi dụng một quy trình khôi phục yếu. Vì vậy **mục tiêu của MFA là tăng độ tin cậy của sự kiện xác thực trong một mô hình đe dọa cụ thể**, chứ không thay thế toàn bộ hệ thống kiểm soát truy cập.

**Phân biệt ba lớp:**

- **Identification:** tìm tài khoản đang được tuyên bố, ví dụ username `linh` hoặc account ID nội bộ.
- **Authentication:** xác minh bằng chứng từ một hay nhiều authenticator đã được ràng buộc với tài khoản đó, bao gồm yêu cầu MFA.
- **Authorization:** quyết định principal trong phiên đã xác thực có quyền đối với tài nguyên hoặc hành động cụ thể hay không.

Một tài khoản đã qua MFA vẫn không được tự ý xem dữ liệu của tài khoản khác.

### Kết quả học tập

Hoàn thành bài này, người học có thể:

1. Nhận diện đúng ba nhóm yếu tố, phân biệt nhiều bước với nhiều yếu tố và giải thích vì sao **tính độc lập** quan trọng.
2. Đánh giá mật khẩu, TOTP, SMS, push, passkey/WebAuthn, khóa bảo mật và chứng chỉ theo khả năng chống phishing, replay và chiếm quyền.
3. Thiết kế luồng MFA có kiểm tra phía server, giới hạn thử, quản lý phiên và hỗ trợ xác thực tăng cường (*step-up*).
4. Mô hình hóa vòng đời đăng ký, thay thế, thu hồi, khôi phục authenticator và ranh giới tin cậy với IdP.
5. Kiểm tra các trường hợp gây lạm dụng như MFA fatigue, chuyển tiếp OTP theo thời gian thực, SIM swap và bỏ qua bước MFA.

## 2. Factor, authenticator và credential không phải một khái niệm

**Yếu tố xác thực (factor)** là loại bằng chứng mà người dùng cần kiểm soát. Có ba nhóm phổ biến:

| Loại yếu tố | Câu hỏi kiểm tra | Ví dụ | Rủi ro đặc trưng |
| --- | --- | --- | --- |
| **Knowledge — Điều biết** | Người dùng biết bí mật nào? | Mật khẩu, PIN, passphrase | Phishing, rò rỉ, đoán, tái sử dụng, chia sẻ bí mật. |
| **Possession — Điều có** | Người dùng kiểm soát thiết bị/khóa nào? | Khóa FIDO2, ứng dụng TOTP trên thiết bị, smart card có khóa riêng | Mất thiết bị, sao chép bí mật, thiết bị bị chiếm hoặc đồng bộ không an toàn. |
| **Inherence — Đặc điểm vốn có** | Người dùng biểu hiện thuộc tính sinh trắc nào? | Vân tay, khuôn mặt, giọng nói trong hệ thống phù hợp | Giả mạo cảm biến, sai số, rủi ro riêng tư và khó thay đổi đặc điểm sau lộ dữ liệu. |

**Authenticator** là cơ chế/phương tiện được dùng để sinh hoặc trình bằng chứng: một ứng dụng tạo mã TOTP, khóa bảo mật, passkey, thẻ thông minh, hoặc cơ chế mật khẩu. **Credential** là dữ liệu đã đăng ký để verifier kiểm tra, ví dụ bộ xác minh mật khẩu, bí mật TOTP, khóa công khai của passkey hoặc chứng chỉ gắn với quan hệ tin cậy.

Ví dụ, điện thoại là **thiết bị**, ứng dụng TOTP là **authenticator**, khóa bí mật TOTP đã đăng ký là **credential**, mã 6 chữ số hiện tại là **bằng chứng**. Phân biệt các tầng này giúp thiết kế đăng ký và thu hồi chính xác.

**Sinh trắc không nên được hiểu là một mật khẩu để gửi lên server.** Với passkey, vân tay/khuôn mặt thường chỉ được xác minh cục bộ nhằm mở quyền dùng khóa riêng; ứng dụng từ xa nhận chữ ký mật mã cùng chỉ báo của authenticator. Server không nhất thiết nhìn thấy dữ liệu sinh trắc.

### Hai bước không tự động là hai yếu tố

- Mật khẩu rồi câu hỏi “tên thú cưng đầu tiên?” → **hai lần hỏi điều biết**, không phải hai loại yếu tố độc lập.
- Hai mật khẩu khác nhau → vẫn chỉ là knowledge.
- Mật khẩu và mã gửi đến email có thể giảm rủi ro trong một số tình huống, nhưng **không được mặc nhiên xem là MFA độc lập** nếu hộp thư có thể truy cập chỉ bằng cùng mật khẩu/phiên bị chiếm.
- Mật khẩu cộng TOTP từ ứng dụng đã đăng ký thường tạo hai loại yếu tố: knowledge + possession, mặc dù TOTP vẫn có thể bị chuyển tiếp khi phishing.
- Dùng khóa mật mã kết hợp kiểm tra PIN/sinh trắc cục bộ có thể đáp ứng một mô hình xác thực đa yếu tố trên cùng thiết bị nếu giải pháp thực sự bảo vệ khóa, buộc kích hoạt cục bộ và có mức bảo đảm phù hợp. **Không phải mọi cách mở khóa điện thoại đều tự động được tính là MFA của ứng dụng.**

**Nguyên tắc:** đếm **loại bằng chứng độc lập**, không đếm số màn hình, số thông báo hoặc số thao tác chạm.

## 3. Một sự kiện MFA cần chứng minh điều gì?

Một luồng MFA đạt mục tiêu khi verifier có thể trả lời rõ ràng:

1. **Chủ thể nào?** Bằng chứng gắn với cùng một account ID đáng tin cậy.
2. **Credential nào?** Từng authenticator đã được đăng ký với đúng tài khoản, chưa bị thu hồi và còn đủ điều kiện.
3. **Yếu tố nào?** Những bước đã thực hiện thực sự thuộc loại yếu tố cần thiết theo chính sách.
4. **Giao dịch nào?** Challenge, OTP hoặc yêu cầu push đúng luồng đang chờ, đúng người dùng, đúng hành động, còn hiệu lực.
5. **Khi nào?** Bằng chứng và kết quả xác thực còn đủ mới cho lần đăng nhập hoặc thao tác nhạy cảm.
6. **Ai xác minh?** Kết luận được đưa ra bởi server/verifier đáng tin, không phải cờ `mfaCompleted=true` do client tự gửi.
7. **Duy trì bao lâu?** Session/token nhận được sau MFA có hạn dùng, phạm vi, cơ chế thu hồi và ràng buộc với principal phù hợp.

Mô hình luồng:

~~~mermaid
flowchart TD
    A["Client yêu cầu đăng nhập"] --> B["Server tìm tài khoản theo chính sách"]
    B --> C["Xác minh yếu tố thứ nhất"]
    C --> D{"Kết quả hợp lệ?"}
    D -- "Không" --> F["Từ chối và ghi nhận chống lạm dụng"]
    D -- "Có" --> E["Server tạo giao dịch MFA có thời hạn"]
    E --> G["Authenticator đã đăng ký tạo bằng chứng"]
    G --> H["Verifier kiểm tra yếu tố bổ sung"]
    H --> I{"Đúng chủ thể, chính sách, giao dịch?"}
    I -- "Không" --> F
    I -- "Có" --> J["Server tạo principal + trạng thái bảo đảm"]
    J --> K["Tạo session/token hợp lệ"]
    K --> L["Mỗi API tiếp tục kiểm tra phiên và quyền"]
~~~

Cần phân biệt **hoàn thành yếu tố thứ nhất** với **đã đăng nhập**. Không cấp phiên có toàn bộ quyền trước khi MFA bắt buộc thành công; nếu cần phiên tạm để thực hiện bước thứ hai, phiên đó phải bị giới hạn chức năng rõ ràng.

## 4. Khả năng bảo vệ của các phương thức MFA

Không có một nhãn “MFA bật” nào đủ để kết luận về sức mạnh của hệ thống. Các phương thức có mức chống phishing và replay rất khác nhau.

| Phương thức | Cơ chế chứng minh | Chống phishing theo nguồn gốc ứng dụng? | Các giới hạn cần giải quyết |
| --- | --- | --- | --- |
| **TOTP app** | Mã ngắn sinh từ bí mật chia sẻ và thời gian | **Không**: có thể bị trang giả chuyển tiếp trong thời gian hiệu lực | Phải giới hạn thử, kiểm soát lệch giờ và phát lại; bảo vệ bí mật khi đăng ký, sao lưu. |
| **HOTP** | Mã ngắn từ bí mật chia sẻ và bộ đếm | **Không** | Cần đồng bộ bộ đếm, giới hạn thử, xử lý mã đã sử dụng. |
| **SMS OTP** | Chứng minh truy cập kênh nhận SMS tại thời điểm đó | **Không** | SIM swap, chuyển hướng, phishing, đổi chủ số, sóng/yếu tố chi phí. |
| **Email OTP/link** | Chứng minh truy cập một hộp thư/đường dẫn | **Không** theo mặc định | Có thể phụ thuộc tài khoản email bị chiếm; mức độc lập yếu nếu dùng cùng bí mật/phiên. |
| **Push approve/deny** | Người dùng phê duyệt yêu cầu từ ứng dụng đã đăng ký | **Không nhất thiết** | MFA fatigue, prompt bombing, chấp thuận nhầm; cải thiện bằng number matching và ngữ cảnh. |
| **Push có xác nhận chi tiết giao dịch** | Người dùng kiểm tra và chấp thuận giao dịch cụ thể | Phụ thuộc **cách ràng buộc giao dịch** | Nếu chỉ hiển thị văn bản do client cung cấp, vẫn có thể bị đánh lừa. |
| **FIDO2/WebAuthn / passkey** | Khóa riêng ký challenge cho RP ID/origin hợp lệ | **Có**, nếu xác minh đúng RP ID/origin và giao thức | Phải quản lý user verification, đăng ký, thiết bị, đồng bộ, thu hồi và khôi phục. |
| **Smart card / client certificate** | Chứng minh kiểm soát khóa riêng kèm quan hệ tin cậy | Phụ thuộc giao thức và cách ràng buộc với server | Xác minh chứng chỉ, định danh, mục đích, thu hồi, bảo vệ khóa và PIN. |

**Phishing-resistant authentication** là thuộc tính kỹ thuật đặc biệt: bằng chứng không thể dễ dàng chuyển từ tên miền giả sang tên miền thật như một mã OTP. MFA có TOTP thường mạnh hơn chỉ có mật khẩu trước rò rỉ mật khẩu, nhưng **không tương đương** MFA chống phishing.

**Khả năng chống replay** cũng riêng biệt: một giá trị TOTP vẫn có thể bị gửi lại trong khoảng thời gian hợp lệ nếu server không ngăn tái sử dụng; với WebAuthn, verifier sinh challenge ngẫu nhiên cho phiên giao dịch và xác minh chữ ký với khóa đã đăng ký. Không nên đánh đồng “có thời gian hết hạn” với “không thể phát lại”.

### 4.1. Mật khẩu kết hợp OTP

Đây là cấu hình phổ biến do dễ triển khai. Sau khi kiểm tra bộ xác minh mật khẩu bằng thuật toán băm có salt và chi phí phù hợp (ví dụ Argon2id), hệ thống đòi hỏi OTP từ authenticator đã đăng ký.

Đối với **TOTP**, server và authenticator chia sẻ bí mật; thuật toán chuẩn tạo mã từ thời gian. Cần đặt thời hạn bước thời gian, cửa sổ chấp nhận lệch đồng hồ hợp lý, giới hạn số lần thử và chống chấp nhận lại mã đã dùng trong thời gian còn hiệu lực. Hạn chế cửa sổ quá rộng vì làm tăng số mã có thể chấp nhận. Lưu bí mật TOTP an toàn ở server: không nhầm với mật khẩu vốn cần lưu dạng bộ xác minh một chiều.

Với **SMS**, mã phải gắn với tài khoản, mục đích và yêu cầu đang chờ, có thời hạn ngắn, giới hạn số lần thử và không chấp nhận lại sau khi dùng. SMS không tự chứng minh danh tính pháp lý của chủ tài khoản và không bảo vệ trước SIM swap; các môi trường có rủi ro cao cần cân nhắc phương thức mạnh hơn.

**Cẩn thận về điện thoại cùng thiết bị:** nếu mật khẩu được lưu tự động và mã SMS cũng đến trên chính thiết bị đang bị chiếm, mức độc lập thực tế giảm. Không nhất thiết phải dùng hai thiết bị vật lý, nhưng cần phân tích điểm lỗi chung của các yếu tố.

### 4.2. Push MFA

Một ứng dụng trên thiết bị gửi thông báo “Có yêu cầu đăng nhập, chấp thuận hay từ chối?”. Đây là trải nghiệm thuận tiện, nhưng có thể bị **push bombing**: kẻ tấn công biết mật khẩu liên tục phát sinh yêu cầu, hy vọng người dùng bấm nhầm.

Các kiểm soát hữu ích gồm: number matching khi liên kết challenge với màn hình đăng nhập, hiển thị tên ứng dụng và ngữ cảnh đăng nhập, giới hạn tần suất, đưa ra nút từ chối rõ ràng, chặn thử lại bất thường, ghi log và cảnh báo. Number matching giúp giảm chấp thuận vô ý, nhưng **không đảm bảo chống phishing nếu trang giả dụ người dùng nhập số khớp**.

Với giao dịch nhạy cảm, yêu cầu xác nhận nội dung cụ thể (ví dụ người nhận, số tiền) và ràng buộc mật mã vào giao dịch có thể phù hợp hơn thao tác “Approve” chung.

### 4.3. Passkey, WebAuthn và khóa bảo mật

Passkey dựa trên mật mã khóa công khai. Trong quá trình đăng ký, authenticator tạo cặp khóa; server lưu **khóa công khai và credential ID**, còn khóa riêng được authenticator giữ và quản lý theo đặc tính sản phẩm. Khi xác thực, server sinh challenge mới, authenticator ký dữ liệu gắn với **RP ID**, còn client mang theo thông tin về **origin**. Server kiểm tra challenge, chữ ký, RP ID, origin, loại thao tác, thông tin user presence (**UP**) và user verification (**UV**) theo chính sách.

- **UP (user presence)** chỉ thể hiện có hành động hiện diện như chạm thiết bị; nó không đồng nghĩa đã xác minh người dùng bằng PIN hoặc sinh trắc.
- **UV (user verification)** thể hiện authenticator đã thực hiện kiểm tra người dùng cục bộ theo cơ chế của nó. Đây là tín hiệu quan trọng khi dùng passkey cho đăng nhập yêu cầu xác minh người dùng.
- Một passkey **đồng bộ (synced)** có thể sẵn trên nhiều thiết bị qua hệ sinh thái quản lý khóa; tính chống phishing theo RP ID vẫn được thiết kế giữ lại, nhưng đánh giá mức bảo đảm và quy trình khôi phục khác với khóa riêng bị giới hạn trên phần cứng.
- **Device-bound credential** với bảo vệ khóa phần cứng có thể phù hợp chính sách cao hơn trong một số môi trường, tùy cơ chế chứng thực và quản lý thiết bị.

Một lần đăng nhập bằng passkey với UV có thể cung cấp trải nghiệm **không mật khẩu** và thực hiện xác thực đa yếu tố trong cùng authenticator, tùy thuộc đặc tính, cấu hình và yêu cầu mức bảo đảm. Không cần buộc người dùng nhập mật khẩu lại chỉ để có hai màn hình nếu authenticator đã đáp ứng đầy đủ mục tiêu xác thực.

### 4.4. Chứng chỉ, smart card và môi trường tổ chức

Trong một số hệ thống doanh nghiệp, smart card hoặc thiết bị chứa khóa riêng được dùng cùng PIN. Một giao thức như mTLS có thể chứng minh bên kết nối kiểm soát khóa riêng tương ứng với chứng chỉ, nhưng **chứng chỉ hợp lệ không tự chứng minh người vận hành hiện tại chính là người đã được cấp tài khoản**. Cần chính sách phát hành, ràng buộc chủ thể, bảo vệ khóa, kiểm tra chain, mục đích sử dụng, thời hạn và thu hồi. Nếu muốn tính là MFA, phải đánh giá cả cơ chế kích hoạt bằng PIN hoặc yếu tố khác.

## 5. Khả năng chống phishing, replay và chiếm phiên

MFA cần được xem trong mô hình đe dọa của toàn bộ phiên đăng nhập.

~~~mermaid
flowchart LR
    A["Kẻ tấn công"] --> B["Đánh cắp mật khẩu"]
    B --> C["Phishing proxy chuyển tiếp OTP"]
    C --> D["Verifier chấp nhận đăng nhập"]
    D --> E["Phát hành cookie / token"]
    E --> F["Kẻ tấn công sử dụng phiên"]
    G["Passkey/WebAuthn ràng buộc RP ID"] -. "Cản chuyển tiếp chữ ký qua domain giả" .-> C
    H["Bảo vệ session, XSS/CSRF, thu hồi, step-up"] -. "Giảm lạm dụng sau đăng nhập" .-> F
~~~

Một cuộc tấn công **adversary-in-the-middle (AiTM)** có thể dựng trang giả và chuyển tiếp mật khẩu lẫn OTP tới trang thật gần như ngay lập tức. Người dùng trải qua đủ hai bước, nhưng kẻ tấn công vẫn có thể chiếm cookie phiên. Vì vậy:

- **TOTP/SMS/push thông thường** có giá trị ngăn sử dụng một mình mật khẩu bị lộ, nhưng vẫn có lỗ hổng trước phishing thời gian thực.
- **WebAuthn/passkey** dùng challenge và ràng buộc theo RP ID/origin để ngăn việc tạo bằng chứng có thể dùng cho RP thật từ origin giả, với điều kiện triển khai đúng.
- **Cookie/token sau MFA** vẫn là tài sản nhạy cảm. Nếu thiết bị bị nhiễm mã độc, có XSS hoặc máy chủ bị xâm nhập, kẻ tấn công có thể sử dụng phiên mà không cần nhập lại yếu tố.
- **Step-up** hạn chế rủi ro khi kẻ tấn công có phiên cũ muốn thực hiện hành động nhạy cảm, nhưng không thay thế kiểm soát token và phân quyền.

MFA không ngăn các lỗi như **IDOR/BOLA**, nơi API cho phép tài khoản A truy cập tài nguyên của B dù A đã đăng nhập hợp lệ. Mỗi yêu cầu vẫn phải kiểm tra quyền theo principal và đối tượng.

## 6. Kiến trúc luồng MFA với ranh giới tin cậy

Ví dụ ứng dụng quản trị có mật khẩu và TOTP. Các thành phần gồm trình duyệt (không tin cậy), authentication service, kho dữ liệu credential, session service và API nghiệp vụ.

~~~text
Browser                           Authentication service               Credential store
   |                                      |                                  |
   |-- username + password -------------->|                                  |
   |                                      |-- tìm account theo policy ------>|
   |                                      |<-- password verifier -----------|
   |                                      |-- kiểm tra password             |
   |<-- MFA transaction (giới hạn) -------|                                  |
   |                                      |                                  |
   |-- TOTP + MFA transaction ----------->|                                  |
   |                                      |-- tìm TOTP secret / trạng thái ->|
   |                                      |<-- credential metadata ---------|
   |                                      |-- kiểm tra OTP + chống replay   |
   |<-- new session cookie ---------------|                                  |
   |                                      |                                  |
   |-- request + cookie ----------------------------------------------------> API
   |                                                      API kiểm tra session
   |                                                      + quyền tài nguyên
~~~

Các bất biến kiến trúc:

1. **Trạng thái MFA đang chờ** chỉ chứa account, yếu tố thứ nhất đã kiểm tra, phương thức tiếp theo cho phép, challenge/giao dịch, hạn dùng và bộ đếm thử; không mang toàn quyền đăng nhập.
2. **MFA transaction** được tạo bởi server, có mã định danh khó đoán và gắn với đúng account, phương thức, ngữ cảnh đăng nhập; không chấp nhận chuỗi `accountId` hay `mfaPassed` do client khai báo.
3. **Từng authenticator** thuộc đúng account và trạng thái đăng ký còn hiệu lực. Người dùng không thể dùng TOTP của tài khoản A để hoàn tất yêu cầu của tài khoản B.
4. **Kết quả chỉ được nâng quyền** sau khi verifier kiểm tra đủ điều kiện và ghi nhận giao dịch đã sử dụng; thao tác hoàn tất phải nhất quán khi hai request đến đồng thời.
5. **Session ID được tạo hoặc làm mới** sau khi hoàn tất xác thực để chống session fixation; phiên có chính sách hết hạn, thu hồi và cơ chế bảo vệ cookie/token.
6. **Quyền tài nguyên** vẫn được kiểm tra trong từng API; hoàn tất MFA không có nghĩa được cấp mọi quyền.

Nếu dùng cookie phiên trên trình duyệt, áp dụng `Secure`, `HttpOnly`, `SameSite` theo kiến trúc, bảo vệ CSRF khi cần và giảm XSS. Đối với access token, kiểm tra chữ ký/introspection, issuer, audience, thời gian, phạm vi và quyền; một token còn hạn vẫn có thể thiếu mức xác thực phù hợp với hành động nhạy cảm.

### Ví dụ giả mã server xác nhận yếu tố bổ sung

~~~java
MfaResult completeMfa(String pendingTransactionId, String submittedOtp) {
    PendingAuth tx = pendingStore.requireActive(pendingTransactionId);

    // Giới hạn lần thử trước khi kiểm tra, bao gồm account, IP,
    // thiết bị và giao dịch theo chính sách chống lạm dụng.
    abuseGuard.checkAllowed(tx.accountId(), tx.id(), requestContext);

    Account account = accountStore.requireActive(tx.accountId());
    TotpAuthenticator totp =
        authenticatorStore.requireEnabledTotp(account.id(), tx.factorId());

    // Thư viện kiểm tra TOTP chuẩn; verifier còn phải chống dùng lại
    // cùng bước thời gian và xử lý đồng thời bằng cơ chế atomic.
    VerificationResult result =
        totpVerifier.verifyOnce(totp, submittedOtp, clock.now());

    if (!result.accepted()) {
        abuseGuard.recordFailure(tx.id(), account.id());
        throw genericAuthenticationFailure();
    }

    // Hoàn tất một lần. Giao dịch đã dùng/đã hết hạn không thể dùng lại.
    pendingStore.completeAtomically(tx.id());

    Principal principal = new Principal(
        account.id(), tx.tenantId(), tx.primaryMethod(),
        "TOTP", clock.now());

    return sessionService.createFreshAuthenticatedSession(principal);
}
~~~

Đây là **giả mã giải thích trách nhiệm**, không phải triển khai đầy đủ: để an toàn trước race condition, trạng thái *OTP đã sử dụng* và *giao dịch MFA hoàn tất* phải được kiểm soát nhất quán trong kho dữ liệu. Một triển khai thực nên dùng thư viện TOTP/WebAuthn/IdP đáng tin cậy, không tự viết thuật toán mật mã từ ví dụ.

Nếu verifier kiểm tra TOTP thành công nhưng ghi trạng thái dùng một lần thất bại, hoặc đánh dấu giao dịch hoàn tất trước khi kiểm tra trạng thái tài khoản, hệ thống có thể tạo điều kiện replay hoặc cấp phiên sai. Cần xử lý rollback, idempotency và tính nguyên tử phù hợp với kho dữ liệu.

## 7. Đăng ký authenticator: mắt xích quyết định độ mạnh MFA

MFA mạnh đến đâu cũng có thể bị bỏ qua nếu kẻ tấn công được phép **đăng ký yếu tố mới** cho tài khoản nạn nhân. Phải coi thêm, thay, xóa authenticator là thao tác nhạy cảm.

### 7.1. Quy trình thêm TOTP

1. Người dùng có phiên đã xác thực với mức tin cậy phù hợp và, khi cần, **xác thực lại** trước khi thay đổi bảo mật.
2. Server tạo một **TOTP secret mới** và giao dịch đăng ký ngắn hạn gắn với account và session. Bí mật chỉ hiển thị qua kênh được bảo vệ; không đưa vào analytics hoặc log.
3. Ứng dụng authenticator của người dùng quét mã QR có secret; server yêu cầu người dùng nhập một mã đúng để chứng minh đã cấu hình thành công.
4. Chỉ sau khi mã được xác minh và kiểm tra xung đột, server mới kích hoạt authenticator cho account.
5. Hệ thống ghi audit, thông báo thêm yếu tố mới qua kênh phù hợp và cung cấp phương án dự phòng an toàn.
6. Nếu hủy/timeout đăng ký, xóa hoặc vô hiệu hóa secret đang chờ; tránh giữ credential “nửa đăng ký” có thể được dùng để hoàn tất đăng nhập.

**Cẩn thận:** kẻ tấn công có thể chèn QR giả vào giao diện hoặc đánh cắp secret trong quá trình thiết lập. Cần ràng buộc thao tác với đúng account và phiên, chống CSRF, bảo vệ giao diện và không chấp nhận callback tự khai là “đã quét”.

### 7.2. Đăng ký passkey và khóa phần cứng

RP sinh challenge đăng ký, trình duyệt gọi WebAuthn, server xác minh challenge, origin, RP ID, các thông tin credential và chính sách authenticator trước khi lưu **credential ID, public key, metadata cần thiết** với account. Khóa riêng không được gửi cho server. Chính sách có thể yêu cầu UV, đặc tính authenticator phù hợp hoặc attestation trong môi trường quản lý thiết bị; không nên tin client chỉ khai `uv=true` mà bỏ qua việc kiểm tra dữ liệu đã được xác thực bằng giao thức.

Khi thêm passkey thứ hai, vẫn phải xác minh quyền kiểm soát **tài khoản hiện tại** và đăng ký credential mới đúng phiên giao dịch. Khuyến khích nhiều phương án truy cập hợp lệ để giảm khóa tài khoản, nhưng không mở một đường thêm thiết bị mới chỉ bằng email không đủ bảo đảm.

### 7.3. Thu hồi, đổi thiết bị và audit

Một authenticator có thể bị mất, thu hồi khi nhân viên nghỉ việc hoặc bị thay khi đổi máy. Server phải cập nhật trạng thái, ngừng chấp nhận credential đã bị thu hồi, cân nhắc thu hồi các phiên hiện hữu và ghi sự kiện thêm/xóa/thay thế. Đối với tài khoản quản trị, nên có chính sách yêu cầu phê duyệt hoặc xác thực mạnh hơn khi thay phương thức.

## 8. Recovery và fallback: đường vòng dễ làm MFA mất tác dụng

Người dùng có thể mất điện thoại, khóa bảo mật hoặc ứng dụng TOTP. Một hệ thống không có cách khôi phục sẽ gây khóa tài khoản; nhưng một cơ chế khôi phục quá dễ sẽ trở thành **đường tắt bỏ qua MFA**.

Các lựa chọn cần đánh giá cùng mức rủi ro:

| Cách phục hồi | Lợi ích | Rủi ro và kiểm soát |
| --- | --- | --- |
| **Authenticator dự phòng đã đăng ký** | Hạn chế phải dựa vào hỗ trợ thủ công | Phải được đăng ký khi tài khoản còn ở trạng thái tin cậy; hỗ trợ thu hồi khi mất. |
| **Recovery codes một lần** | Sử dụng được khi mất thiết bị, có thể offline | Mỗi mã mạnh, lưu băm/kiểm tra an toàn ở server khi phù hợp, một lần, giới hạn thử; hướng dẫn lưu ngoài thiết bị chính. |
| **Quy trình hỗ trợ quản trị** | Giải quyết trường hợp mất mọi thiết bị | Kiểm chứng nhiều tín hiệu phù hợp, tách nhiệm vụ/phê duyệt khi cần, chống social engineering, audit đầy đủ. |
| **Email/SMS reset** | Thuận tiện và dễ tiếp cận | Không tương đương authenticator chống phishing; cần đánh giá đổi chủ kênh, chiếm email/SIM, giới hạn tác vụ và bổ sung xác minh. |
| **Recovery bằng kênh tổ chức** | Tận dụng quy trình nội bộ | Chỉ mạnh bằng quy trình xác minh nhân viên, danh tính và quyền của người thực hiện. |

**Recovery code** là bí mật khẩn cấp dùng cho luồng phục hồi; đừng coi nó là bằng chứng đa yếu tố tương đương passkey trong mọi trường hợp. Chính sách cần phân biệt **đăng nhập thường**, **khôi phục quyền truy cập** và **gỡ/thay yêu cầu MFA**.

Quy trình khôi phục tốt nên:

- Xác định đúng account bằng định danh, nhưng **không** xem identifier là bằng chứng sở hữu.
- Dùng bằng chứng đủ tương xứng với hậu quả của việc cấp credential mới; áp dụng thời gian chờ, kênh thông báo hoặc kiểm tra thủ công cho trường hợp rủi ro cao.
- Không để nhân viên hỗ trợ tự ý tắt MFA chỉ sau khi biết tên, email, ngày sinh hoặc thông tin có thể tra cứu.
- Ghi audit về ai yêu cầu, bằng chứng/quyết định theo chính sách, khi nào, credential nào bị vô hiệu và phiên nào được thu hồi; không ghi token hoặc bí mật thuần.
- Thông báo thay đổi bảo mật qua kênh đã đăng ký nếu còn tin cậy, hỗ trợ người dùng phản hồi nếu thay đổi không do họ thực hiện.
- Có cách xử lý trường hợp tài khoản bị kẻ tấn công khóa trước khi người dùng hợp lệ kịp can thiệp.

**Nguyên tắc kiểm tra:** một MFA chống phishing mạnh sẽ không giúp nhiều nếu tính năng “Tôi mất thiết bị” cho phép thay MFA chỉ bằng một email vừa bị chiếm.

## 9. Step-up authentication cho hành động nhạy cảm

Không phải mọi yêu cầu cần xác thực lại. Một người vừa đăng nhập bằng MFA có thể xem nội dung thường, nhưng đổi mật khẩu, chuyển tiền, thêm thiết bị đăng nhập, gỡ MFA hoặc xuất dữ liệu hàng loạt có thể đòi hỏi **kết quả xác thực mới và mạnh hơn**.

Ví dụ:

~~~text
10:00 — Đăng nhập bằng password + TOTP: tạo session S1.
11:30 — Người dùng mở trang hồ sơ: session S1 đủ theo policy.
11:31 — Người dùng yêu cầu thêm passkey mới:
         Server thấy xác thực gần nhất đã quá ngưỡng cho tác vụ này.
         -> Bắt đầu step-up, ràng buộc với session S1 và tác vụ.
11:32 — Người dùng hoàn thành WebAuthn trên domain thật.
         Server kiểm tra challenge và độ mới, cập nhật thông tin
         assurance của session theo chính sách.
11:33 — Server cho phép thêm passkey sau khi kiểm tra quyền và
         trạng thái giao dịch còn hiệu lực.
~~~

Đối với những giao dịch có hậu quả lớn, có thể cần **transaction authorization**: yêu cầu xác nhận cụ thể giao dịch (ví dụ người nhận/số tiền) theo cơ chế không cho phép sửa nội dung sau xác nhận. Chỉ yêu cầu người dùng gõ một OTP mới rồi cho phép mọi giao dịch bất kỳ trong thời gian dài có thể không đủ.

**Không nhầm session age với authentication age.** Token được phát hành lại lúc 11:30 không có nghĩa người dùng vừa xác thực lại lúc đó. Cần duy trì `auth_time` hoặc metadata tương đương là thời điểm kiểm tra credential thật sự, đồng thời xác định phương thức và mức bảo đảm đã đạt.

Một ví dụ policy:

| Hành động | Ví dụ yêu cầu có thể đặt | Lý do |
| --- | --- | --- |
| Xem nội dung phổ thông | Phiên hợp lệ, không cần step-up | Giảm phiền toái, vẫn kiểm tra quyền. |
| Xem thông tin cá nhân nhạy cảm | Phiên có MFA phù hợp và không quá cũ | Giảm lạm dụng phiên bị đánh cắp. |
| Thay email khôi phục | Xác thực lại bằng authenticator đủ mạnh, thông báo thay đổi | Hạn chế chiếm quyền qua vòng đời account. |
| Thêm/xóa passkey hoặc MFA | Reauthentication, anti-CSRF, kiểm soát rủi ro và audit | Bảo vệ đường quản lý credential. |
| Phê duyệt tài chính/đặc quyền quản trị | Phương thức chống phishing, giao dịch được ràng buộc và chính sách riêng | Hậu quả của chiếm quyền lớn. |

Các ngưỡng thời gian và phương thức trong bảng là ví dụ thiết kế; tổ chức cần dựa trên mô hình rủi ro và yêu cầu tuân thủ thực tế.

## 10. Liên kết danh tính và MFA trong môi trường SSO/OIDC

Trong đăng nhập liên kết, **Identity Provider (IdP)** thực hiện xác thực, còn ứng dụng **Relying Party (RP)** nhận kết quả qua giao thức như OpenID Connect. Không được để client tự tuyên bố “đã qua MFA tại IdP”.

RP phải hoàn thành flow đúng giao thức, kiểm tra chữ ký token và các điều kiện thích hợp: issuer, audience, expiry, nonce, state/PKCE ở nơi áp dụng, rồi ánh xạ danh tính ngoài theo **(issuer, subject)** vào account nội bộ. Email trùng nhau không đủ để tự động liên kết tài khoản.

Một IdP có thể cung cấp:

- **`amr` (Authentication Methods References):** những phương thức xác thực đã sử dụng, nếu IdP phát hành claim và hai bên có quy ước hiểu giá trị.
- **`acr` (Authentication Context Class Reference):** ngữ cảnh/lớp bảo đảm xác thực theo một định nghĩa đã thỏa thuận.
- **`auth_time`:** thời điểm xác thực cuối cùng có ý nghĩa cho chính sách độ mới, nếu có và được xác minh trong thông điệp đáng tin cậy.

**Không được tự suy ra rằng bất kỳ chuỗi `amr: ["mfa"]` nào cũng đáp ứng toàn bộ chính sách của RP.** RP và IdP cần thỏa thuận rõ phương thức, cấp độ, hiệu lực, cách xử lý step-up và yêu cầu bảo mật. RP vẫn kiểm soát phiên ứng dụng và phân quyền dữ liệu của mình.

Khi cần xác thực tăng cường, RP có thể yêu cầu IdP tương ứng theo khả năng giao thức, sau đó **xác minh lại kết quả trả về** trước khi nâng assurance. Không nên tăng mức bảo đảm chỉ vì URL redirect đã trả về thành công.

Trường hợp người dùng đăng nhập qua nhiều IdP, một danh tính ở IdP A và một danh tính ở IdP B không tự nhiên là cùng người. Việc liên kết phải qua thao tác có kiểm soát với bằng chứng từ cả tài khoản nội bộ và danh tính mới.

## 11. Chống lạm dụng đăng nhập và bảo vệ quyền riêng tư

Yêu cầu MFA cũng là bề mặt tấn công: kẻ xấu có thể tiêu hao SMS, khóa tài khoản người dùng hợp lệ, gửi hàng nghìn yêu cầu push hoặc dò xem tài khoản nào đã bật MFA.

Biện pháp thường cần được phối hợp:

- **Rate limiting theo nhiều chiều:** account, identifier đã chuẩn hóa, IP, thiết bị, số điện thoại, giao dịch và nguồn mạng. Không chỉ chặn IP vì kẻ tấn công có thể phân tán IP.
- **Giới hạn số lần nhập OTP và gửi lại:** hết hạn challenge, tiêu hủy yêu cầu cũ theo chính sách, không cho dùng lại mã/giao dịch đã hoàn tất.
- **Phản hồi lỗi hợp lý:** tránh lộ tài khoản tồn tại, đã đăng ký yếu tố nào hoặc đang khóa ở bước nào cho người chưa xác thực. Vẫn cung cấp trải nghiệm hỗ trợ phù hợp cho người dùng hợp lệ.
- **Phát hiện bất thường:** nhiều lần sai mật khẩu, đổi thiết bị, chuyển SIM đáng nghi, thay đổi vùng địa lý quá nhanh, push liên tục, đăng ký thiết bị lạ, thử phục hồi dồn dập. Tín hiệu rủi ro không phải tự thân là bằng chứng danh tính.
- **Chính sách khóa và phục hồi thận trọng:** khóa cứng toàn bộ sau vài lần sai có thể tạo từ chối dịch vụ; dùng progressive throttling và phương án hỗ trợ phù hợp.
- **Bảo vệ kênh:** TLS, CSRF protection khi dùng cookie, CSP và phòng XSS, session cookie an toàn, tránh log mật khẩu, mã OTP, QR secret, reset link hoặc bearer token.
- **Thông báo bảo mật có ngữ cảnh:** cảnh báo thêm yếu tố, tắt MFA, reset bất thường, đăng nhập rủi ro cao; không tiết lộ dữ liệu cá nhân thừa.

**Khả năng sử dụng và tiếp cận là một phần bảo mật.** Yêu cầu điện thoại cho mọi người có thể loại trừ người không có thiết bị; ép người dùng chọn cách MFA không phù hợp dẫn đến chia sẻ authenticator hoặc phụ thuộc hỗ trợ. Nên có ít nhất một lựa chọn dự phòng đủ mạnh và phù hợp người dùng, không hạ toàn bộ hệ thống xuống phương thức yếu nhất.

## 12. Đánh giá mức bảo đảm thay vì chỉ bật/tắt MFA

Các tiêu chuẩn như **NIST SP 800-63B** đưa ra khái niệm mức bảo đảm xác thực (*Authentication Assurance Level*, AAL). Chỉ biết một luồng có “hai bước” không đủ để kết luận đáp ứng một AAL cụ thể. Cần xem xét **loại authenticator, khả năng chống replay/phishing, bảo vệ kênh, vòng đời đăng ký/thu hồi, chính sách phiên, khôi phục và các yêu cầu liên quan** của chuẩn áp dụng.

Có thể thiết lập một bảng yêu cầu nội bộ như sau:

| Nhóm sử dụng | Mô hình đe dọa chính | Hướng kiểm soát gợi ý |
| --- | --- | --- |
| Tài khoản người học | Mật khẩu bị lộ, chiếm email, mất thiết bị | Khuyến khích passkey; hỗ trợ MFA và recovery có kiểm soát. |
| Nhân viên truy cập dữ liệu nhạy cảm | Phishing quy mô lớn, chiếm phiên, lộ thông tin | Ưu tiên phương thức chống phishing, step-up, quản lý phiên và thiết bị theo rủi ro. |
| Quản trị viên hệ thống | Tấn công có mục tiêu, leo thang đặc quyền | Yêu cầu phương thức mật mã chống phishing, bảo vệ authenticator, tách đặc quyền và audit. |
| Tài khoản dịch vụ/workload | Rò rỉ API key, giả mạo máy gọi | Dùng xác thực máy bằng mTLS hoặc workload identity, khóa ngắn hạn/luân chuyển; không ép mô hình OTP dành cho con người. |

Đối với hệ thống xác thực **service-to-service**, “MFA cho người dùng” thường không phải mô hình phù hợp. Thay vào đó là danh tính workload, chứng chỉ hoặc token được cấp theo chính sách tin cậy; vẫn phải chống replay, bảo vệ khóa, ràng buộc audience và phân quyền API.

**Quyết định thiết kế nên bắt đầu từ rủi ro**, rồi lựa chọn phương thức và yêu cầu kỹ thuật có thể kiểm thử. “Có bật MFA” chỉ là một thông số, chưa phải kết luận an toàn.

## 13. Các lỗi thiết kế MFA phổ biến

| Lỗi | Vì sao nguy hiểm | Sửa như thế nào |
| --- | --- | --- |
| Kiểm tra chỉ ở giao diện: client gửi `mfaPassed=true` | Bỏ qua UI là vượt MFA | Server lưu/chứng thực giao dịch MFA và tạo principal sau xác minh. |
| Cấp session đầy đủ sau mật khẩu, chờ OTP sau | API có thể được gọi trước OTP | Chỉ dùng phiên tạm với quyền rất hạn chế; nâng quyền sau MFA. |
| Dùng OTP của tài khoản A cho giao dịch của B | Hoán đổi bằng chứng để chiếm account | Ràng buộc credential, account, mục đích, giao dịch tại server. |
| Chấp nhận lại TOTP trong cùng cửa sổ | Replay để hoàn tất nhiều lần | Ghi nhận bước thời gian đã dùng cho authenticator, xử lý atomic. |
| Không giới hạn thử mã 6 chữ số | Có thể đoán brute force | Giới hạn thử theo account/giao dịch và giảm tốc. |
| Push “approve” không ngữ cảnh | Fatigue, người dùng bấm nhầm | Number matching, ngữ cảnh, giới hạn prompt; ưu tiên chống phishing nếu rủi ro cao. |
| Đăng ký yếu tố mới chỉ cần mật khẩu đã lộ | Kẻ tấn công tự đặt MFA để giữ tài khoản | Reauthentication, kiểm tra rủi ro, thông báo và audit. |
| Tắt MFA qua kênh support yếu | Đường tắt vượt MFA | Recovery có mức bảo đảm tương xứng, phê duyệt, kiểm tra và audit. |
| Token vẫn mang assurance cao sau khi khôi phục yếu | Quá trình khôi phục làm sai ngữ cảnh xác thực | Xác định lại mức bảo đảm, thời điểm, phiên và quyền sau recovery. |
| Tin claim MFA từ IdP không được cấu hình/kiểm tra | Kẻ tấn công giả thông điệp hoặc IdP yếu | Kiểm tra giao thức, issuer, audience, token và thỏa thuận acr/amr. |
| Mặc định mật khẩu + SMS chống phishing | AiTM có thể chuyển tiếp mã | Ưu tiên WebAuthn/passkey cho tài khoản có rủi ro phishing. |
| Bỏ qua bảo vệ phiên và phân quyền sau MFA | Kẻ tấn công dùng session bị đánh cắp hoặc IDOR | Bảo vệ cookie/token, hạn phiên, step-up và kiểm tra quyền từng API. |

### Tình huống: OTP đúng nhưng vẫn không an toàn

Giả sử người dùng A nhận OTP để **đổi email**, còn người dùng B đang ở bước **đăng nhập**. Server chỉ lưu một bảng `otp -> valid`, không lưu mục đích hay account. Kẻ tấn công lấy được mã của A rồi gửi trong giao dịch B. Nếu server chỉ kiểm tra mã tồn tại và chưa hết hạn, hệ thống có thể cấp phiên cho B.

Cần thiết kế dữ liệu kiểu:

~~~text
challenge_id: ngẫu nhiên, không đoán được
account_id:  acc-A
purpose:     CHANGE_EMAIL
authenticator_id: authenticator đã đăng ký của A
expires_at:  ...
attempts:    ...
consumed_at: ...
~~~

Với mã **server-generated OTP**, việc ràng buộc có thể nằm ngay trong bản ghi challenge. Với **TOTP theo thời gian**, giá trị mã không tự mang challenge ID hoặc mục đích; server phải duy trì **giao dịch đăng nhập đang chờ** gắn với account/authenticator và không cho dùng lại bằng chứng đã chấp nhận theo chính sách. Hai loại mã không thể áp dụng nguyên xi cùng một mô hình lưu trữ.

## 14. Thiết kế một luồng MFA từ yêu cầu đến kiểm thử

Xét hệ thống quản lý tài khoản có ba nhóm: người học, nhân viên hỗ trợ và quản trị viên. Mục tiêu là ngăn chiếm quyền do mật khẩu lộ, chống phishing có mục tiêu với quản trị viên và cho phép khôi phục khi mất thiết bị.

### Bước 1: Xác định tài sản và ranh giới tin cậy

- Tài sản: dữ liệu người học, hồ sơ cá nhân, quyền hỗ trợ, khóa cấp phát token, các API quản trị.
- Vùng không tin cậy: trình duyệt, ứng dụng cài trên máy người dùng, các trường do client gửi và mạng có thể bị giám sát.
- Vùng tin cậy: verifier, kho credential được bảo vệ, session service, hệ thống phân quyền; khi có SSO phải chỉ rõ IdP tin cậy và giao thức.
- Hành động rủi ro cao: đổi credential, thêm IdP, gỡ MFA, cấp quyền quản trị, xuất dữ liệu diện rộng.

### Bước 2: Chọn phương thức theo nhóm

- **Người học:** cho phép passkey; hỗ trợ mật khẩu + TOTP hoặc phương thức khác theo mức rủi ro; cơ chế dự phòng an toàn, không khóa người dùng chỉ vì đổi điện thoại.
- **Nhân viên hỗ trợ:** ưu tiên phương thức chống phishing, yêu cầu MFA phù hợp trước khi truy cập dữ liệu nhạy cảm; audit hành động hỗ trợ.
- **Quản trị viên:** yêu cầu phương thức mật mã chống phishing, xác thực lại cho hành động đặc quyền và thu hồi nhanh khi mất thiết bị.

### Bước 3: Định nghĩa trạng thái xác thực

~~~text
ANONYMOUS
  |
  | verify primary authenticator
  v
PRIMARY_VERIFIED / PENDING_MFA
  |
  | verify registered additional authenticator
  v
AUTHENTICATED (principal, auth_time, methods/assurance)
  |
  | action requires fresher/stronger authentication
  v
STEP_UP_REQUIRED
  |
  | successful verifier-bound challenge
  v
AUTHENTICATED_WITH_STEP_UP
  |
  | logout / expiry / revocation
  v
ENDED
~~~

Không đặt `AUTHENTICATED` chỉ vì biết username hoặc vì màn hình MFA đã hiển thị. Trạng thái phải được kiểm tra trên server và tương ứng với quyền thực tế của phiên.

### Bước 4: Định nghĩa tiêu chí chấp nhận

| Ca thử | Hành vi mong đợi |
| --- | --- |
| Đúng mật khẩu, sai OTP | Không cấp phiên đầy đủ; ghi nhận và giới hạn thử. |
| Đúng OTP nhưng sai account hoặc authenticator | Từ chối; không nâng quyền. |
| OTP đúng nhưng challenge đã hết hạn | Từ chối. |
| Gửi lại cùng OTP/challenge đã dùng | Từ chối theo cơ chế một lần của giao thức. |
| Hai yêu cầu song song hoàn tất cùng giao dịch | Chỉ một yêu cầu được chấp nhận; kết quả nhất quán. |
| Client tự gửi `mfaPassed=true` | Không có tác dụng. |
| Đổi tài khoản giữa bước mật khẩu và bước MFA | Không được dùng transaction cũ cho tài khoản mới. |
| Phiên tạm trước MFA gọi API dữ liệu | Bị từ chối. |
| Passkey từ origin không được phép | WebAuthn verification từ chối. |
| Passkey ký challenge đã sử dụng hoặc sai RP ID | Từ chối. |
| Push liên tục do kẻ tấn công phát sinh | Rate limit và cơ chế giảm MFA fatigue hoạt động. |
| Quản trị viên đã xác thực từ quá lâu cố thêm passkey | Yêu cầu step-up mới. |
| IdP không đáp ứng `acr` theo hợp đồng | RP không coi chính sách MFA là đã thỏa mãn. |
| Mất authenticator và kích hoạt recovery | Cần bằng chứng/phê duyệt theo policy; có audit và thu hồi cần thiết. |
| Tài khoản A đã qua MFA nhưng yêu cầu tài nguyên B không có quyền | API từ chối vì thiếu quyền. |
| Session token bị thu hồi | Không được dùng dù MFA trước đó thành công. |

### Bước 5: Theo dõi vận hành

Có thể theo dõi tỷ lệ hoàn tất MFA theo phương thức, số lần thử sai, push bị từ chối, thất bại do đồng hồ TOTP lệch, số lần recovery, khóa tài khoản, thời gian đến khi thu hồi authenticator mất và sự kiện thêm yếu tố bất thường. Khi phân tích cần tách vấn đề **phishing/lạm dụng** khỏi vấn đề **UX/khả năng tiếp cận**. Log có thể lưu account ID nội bộ hoặc mã sự kiện phù hợp; tuyệt đối không lưu OTP hay secret để tiện debug.

## 15. Bài tập tình huống và câu hỏi tự đánh giá

### Tình huống: tài khoản kế toán bị đánh cắp mật khẩu

Lan là kế toán của một doanh nghiệp. Hệ thống dùng mật khẩu + SMS OTP. Kẻ tấn công dựng website giả có giao diện giống hệ thống, thu mật khẩu của Lan và yêu cầu Lan điền OTP. OTP được chuyển tiếp ngay sang website thật, kẻ tấn công lấy cookie phiên rồi mở chức năng đổi tài khoản nhận tiền.

**Các câu hỏi cần giải quyết:**

1. Vì sao hệ thống vẫn bị xâm nhập dù đã yêu cầu hai yếu tố?
2. Phương thức nào có thể cải thiện khả năng chống phishing và vì sao?
3. Nếu kẻ tấn công đã đánh cắp cookie phiên, những biện pháp nào còn giúp giảm rủi ro?
4. Trước khi đổi tài khoản nhận tiền, hệ thống nên yêu cầu gì ngoài việc kiểm tra “đã đăng nhập”?
5. Nếu Lan mất thiết bị xác thực, quy trình recovery cần tránh những đường vòng nào?

**Phân tích:** Phishing proxy đã chuyển tiếp mật khẩu và SMS OTP theo thời gian thực, nên **MFA kiểu mã nhập không bảo đảm chống phishing**. Dùng passkey/WebAuthn đúng RP ID/origin giúp chặn việc sử dụng bằng chứng từ domain giả; tuy nhiên vẫn cần ngăn chiếm phiên bằng kiểm soát session, chống XSS, phát hiện bất thường và thu hồi. Với đổi người nhận tiền, yêu cầu quyền phù hợp, xác thực lại bằng phương thức mạnh và, nếu chính sách cần, xác nhận được ràng buộc với nội dung giao dịch. Recovery không được chỉ dựa vào thông tin cá nhân dễ tra hoặc email đã bị chiếm.

### Câu hỏi kiểm tra kiến thức

1. Vì sao mật khẩu + câu hỏi bí mật không nhất thiết là MFA?
2. Sự khác nhau giữa yếu tố xác thực, authenticator và credential là gì?
3. TOTP có chống phishing tốt như WebAuthn không? Giải thích bằng ví dụ.
4. Tại sao một mã OTP chưa hết hạn vẫn có thể phải bị từ chối?
5. Number matching giải quyết rủi ro nào và không giải quyết được rủi ro nào?
6. Phân biệt user presence (UP) và user verification (UV) trong WebAuthn.
7. Vì sao bật MFA mạnh nhưng reset tài khoản bằng hỗ trợ yếu vẫn nguy hiểm?
8. `auth_time` khác thời điểm cấp mới access token thế nào?
9. Vì sao RP cần xác minh `acr`/`amr` theo chính sách IdP thay vì tin mọi chuỗi `mfa`?
10. Vì sao một tài khoản đã qua MFA vẫn có thể gặp lỗ hổng IDOR?

**Gợi ý đáp án:** (1) đều là knowledge; (2) factor là loại bằng chứng, authenticator là phương tiện, credential là dữ liệu đăng ký để kiểm tra; (3) TOTP có thể bị chuyển tiếp, WebAuthn ràng buộc RP ID/origin; (4) đã dùng, sai account, sai giao dịch/mục đích hoặc nằm ngoài chính sách; (5) giảm duyệt push nhầm nhưng không chống được mọi phishing; (6) UP cho biết có thao tác hiện diện, UV là kiểm tra người dùng cục bộ; (7) kẻ tấn công thay credential qua đường phục hồi; (8) refresh token không tự chứng minh xác thực mới; (9) claim chỉ có nghĩa theo hợp đồng tin cậy và giao thức; (10) MFA xác thực principal, còn từng quyền tài nguyên phải được kiểm tra riêng.

## 16. Ghi nhớ

**MFA thực chất là việc kết hợp các loại bằng chứng xác thực phù hợp và độc lập, được kiểm tra trong đúng ngữ cảnh, cho đúng tài khoản, theo chính sách rủi ro.** Chọn phương thức cần phân biệt MFA thông thường và MFA chống phishing; thiết kế phải bao phủ ranh giới client–verifier, đăng ký authenticator, chống replay, phiên/token, SSO, xác thực tăng cường và khôi phục. Khi kiểm tra một luồng, hãy luôn hỏi:

> **Hai yếu tố được xác minh là gì? Bên nào tin kết quả đó? Bằng chứng có bị chuyển tiếp hoặc phát lại được không? Phiên được bảo vệ ra sao, và có đường đăng ký/khôi phục nào cho phép kẻ tấn công bỏ qua bảo vệ này không?**
