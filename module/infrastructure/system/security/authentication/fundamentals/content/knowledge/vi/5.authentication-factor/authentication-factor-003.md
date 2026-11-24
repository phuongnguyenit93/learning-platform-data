# Yếu tố là

> **Chương:** Authentication factor  
> **Ngữ cảnh học tập:** SECURITY_AUTHENTICATION_FUNDAMENTALS — nguyên lý xác thực danh tính bằng credential, mật khẩu, MFA, passkey, chứng chỉ; cách duy trì phiên/token, thiết lập ranh giới tin cậy và phòng chống phishing, replay, lạm dụng đăng nhập.  
> **Ý chính:** Trong xác thực, **yếu tố (authentication factor)** là **loại bằng chứng** mà một chủ thể sử dụng để chứng minh quyền kiểm soát danh tính đã đăng ký. Hiểu đúng yếu tố giúp thiết kế xác thực đa yếu tố (MFA) thực sự có ý nghĩa.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích yếu tố xác thực là gì và phân biệt **yếu tố**, **credential**, **authenticator**, **phương thức xác thực**, **định danh** và **phiên đăng nhập**.
2. Nhận biết ba nhóm yếu tố phổ biến: **điều biết** (knowledge), **thứ sở hữu** (possession) và **đặc điểm vốn có** (inherence).
3. Phân loại các ví dụ như mật khẩu, PIN, TOTP, SMS OTP, passkey, khóa bảo mật, sinh trắc học và chứng chỉ số theo đúng cơ chế chứng minh.
4. Giải thích vì sao hai bước đăng nhập chưa chắc là MFA và vì sao số lượng yếu tố không tự bảo đảm chống phishing hay chiếm phiên.
5. Mô tả chu trình đăng ký, kiểm chứng, thu hồi và khôi phục authenticator tại ranh giới tin cậy.
6. Lựa chọn phương thức phù hợp với rủi ro truy cập, đồng thời nhận diện các cuộc tấn công credential stuffing, MFA fatigue, replay và đánh cắp token.

## 1. Vì sao cần khái niệm “yếu tố”?

Một ứng dụng nhận được yêu cầu: “Tôi là chủ tài khoản của Minh”. Chỉ biết tên tài khoản chưa đủ để tin người gửi. Máy chủ cần kiểm tra một **bằng chứng có liên kết với tài khoản**: chẳng hạn mật khẩu đúng, phản hồi mật mã được tạo bằng khóa riêng đã đăng ký hoặc mã do một authenticator hợp lệ sinh ra.

Vấn đề là các bằng chứng có thể bị tấn công theo những cách khác nhau. Mật khẩu có thể bị đoán hoặc lộ qua phishing; điện thoại có thể bị mất hoặc bị chiếm quyền; vân tay có thể bị giả mạo nếu thiết bị kiểm tra thiếu bảo vệ. **Phân loại yếu tố** giúp người thiết kế hiểu bằng chứng dựa trên loại khả năng nào và liệu việc kết hợp hai bằng chứng có thực sự giảm phụ thuộc vào cùng một điểm yếu hay không.

**Định nghĩa thực hành:** yếu tố xác thực là một **loại thuộc tính hoặc khả năng của chủ thể** được dùng để kiểm chứng quyền sử dụng danh tính số, thường nằm trong một trong ba nhóm sau:

| Nhóm yếu tố | Câu hỏi mà hệ thống muốn kiểm tra | Ví dụ quen thuộc |
| --- | --- | --- |
| **Điều bạn biết (something you know)** | Bạn có biết một bí mật đã đăng ký không? | Mật khẩu, PIN bí mật. |
| **Thứ bạn có/sở hữu (something you have)** | Bạn có kiểm soát thiết bị, khóa hoặc authenticator đã đăng ký không? | Khóa bảo mật FIDO2, thiết bị giữ khóa riêng, ứng dụng tạo TOTP. |
| **Đặc điểm vốn có (something you are)** | Bạn có đặc điểm sinh trắc phù hợp với mẫu được đăng ký không? | Vân tay hoặc khuôn mặt được kiểm tra bằng cơ chế có bảo vệ. |

Ba nhóm này là **mô hình tư duy**, không phải cách đánh giá an toàn tuyệt đối. Ví dụ, thiết bị có thể giữ khóa mật mã mạnh nhưng bị chiếm; sinh trắc có thể thuận tiện nhưng không thể “đổi vân tay” như đổi mật khẩu; mã OTP là mật mã ngắn hạn nhưng vẫn có thể bị nhập vào trang giả.

## 2. Tách “yếu tố” khỏi các thuật ngữ liên quan

| Thuật ngữ | Nó trả lời câu hỏi nào? | Ví dụ |
| --- | --- | --- |
| **Danh tính/định danh (identity/identifier)** | Chủ thể đang khai mình là ai? | Một mã tài khoản nội bộ hoặc cặp issuer–subject của IdP. |
| **Yếu tố xác thực (factor)** | Bằng chứng dựa trên loại khả năng nào? | Biết bí mật, sở hữu thiết bị, có đặc điểm sinh trắc. |
| **Credential** | Thông tin hoặc khóa đã gắn với danh tính để hỗ trợ xác thực là gì? | Bí mật mật khẩu, khóa công khai đăng ký với passkey, chứng chỉ cùng khóa liên quan. |
| **Authenticator** | Cơ chế/phương tiện nào tạo hoặc giữ bằng chứng? | Khóa bảo mật, ứng dụng TOTP, thiết bị giữ passkey. |
| **Phương thức/giao thức xác thực** | Bằng chứng được trình và kiểm chứng bằng quy trình nào? | Password verification, TOTP, WebAuthn, cơ chế thử thách–phản hồi dựa trên khóa. |
| **Kết quả xác thực và phiên/token** | Hệ thống ghi nhận một lần xác thực và cho phép các yêu cầu sau như thế nào? | Cookie phiên hoặc token hợp lệ trong phạm vi cho phép. |
| **Phân quyền** | Chủ thể đã được xác thực được phép thực hiện hành động nào? | Người dùng chỉ xem đơn hàng của mình. |

Ví dụ: **passkey** sử dụng credential khóa công khai/khóa riêng và cơ chế WebAuthn; khóa riêng được giữ bởi authenticator. Tùy thiết kế, thiết bị có thể yêu cầu **xác minh người dùng cục bộ (user verification)** bằng PIN hoặc sinh trắc học. Máy chủ nhận và kiểm chứng phản hồi mật mã; máy chủ không cần nhận ảnh vân tay.

Trong khi đó, một **access token** được cấp sau đăng nhập thường là **bằng chứng mang quyền truy cập cho các request tiếp theo**, không phải một yếu tố độc lập thứ hai chỉ vì client có thể gửi nó. Khi token bị lộ, kẻ giữ token có thể khai thác phiên trong phạm vi và thời gian còn hiệu lực.

**Ghi nhớ:** việc hỏi tên người dùng, CAPTCHA, kiểm tra IP hoặc gửi thông báo đăng nhập **không tự động tạo một yếu tố xác thực mới**.

## 3. Yếu tố “điều bạn biết”: mật khẩu và PIN

Một yếu tố thuộc nhóm **knowledge** dựa vào việc người dùng biết một bí mật mà bên không có quyền khó đoán được.

**Ví dụ:**

- Mật khẩu tài khoản.
- PIN bí mật dùng theo thiết kế có kiểm soát thử sai.
- Mật khẩu dùng để mở khóa một vật chứa credential, nếu nó được dùng như thành phần xác minh phù hợp.

### Giá trị và giới hạn

Mật khẩu dễ triển khai và không đòi hỏi một thiết bị chuyên biệt. Tuy nhiên, bí mật có thể bị:

- Tái sử dụng giữa nhiều dịch vụ; một vụ rò rỉ làm tăng nguy cơ **credential stuffing** ở dịch vụ khác.
- Đoán bằng danh sách mật khẩu phổ biến hoặc các biến thể thông tin cá nhân.
- Lấy qua trang giả, phần mềm độc hại, keylogger hoặc hỗ trợ kỹ thuật giả.
- Rò rỉ qua log, hệ thống lưu trữ hoặc truyền thông không được bảo vệ.

Hệ thống dùng mật khẩu cần truyền qua kênh bảo mật, lưu dưới dạng **băm mật khẩu chuyên dụng với salt** bằng thuật toán phù hợp như Argon2id, kiểm soát thử sai và theo dõi đăng nhập bất thường. Không lưu mật khẩu rõ; không dùng SHA-256 đơn lẻ như giải pháp thay thế hoàn chỉnh cho thuật toán băm mật khẩu.

### Khi nào không phải hai yếu tố?

Nếu hệ thống hỏi:

1. Mật khẩu của tài khoản.
2. Một PIN khác do người dùng ghi nhớ.

Thì có **hai bí mật** nhưng cả hai vẫn thuộc nhóm **điều biết**. Đây có thể là hai bước kiểm tra, song **không tự động là MFA**. Tương tự, câu hỏi như “Tên thú cưng đầu tiên?” không tạo thêm nhóm yếu tố; câu trả lời có thể dễ đoán hoặc được tìm thấy công khai.

**Chú ý về PIN:** PIN mở khóa khóa riêng trong thiết bị có thể là bước **xác minh người dùng cục bộ**, khác về kiến trúc so với gửi thêm một PIN lên máy chủ sau mật khẩu. Không nên kết luận loại yếu tố chỉ từ việc giao diện hiển thị chữ “PIN”; phải xem ai kiểm chứng PIN và nó bảo vệ cái gì.

## 4. Yếu tố “thứ bạn có”: thiết bị, khóa và mã OTP

**Possession** dựa vào quyền kiểm soát một vật hoặc authenticator đã đăng ký, chẳng hạn thiết bị giữ khóa bí mật. Đây không chỉ là việc người dùng **khai rằng** họ có điện thoại, mà là việc hệ thống kiểm tra một bằng chứng mà thiết bị/credential đó có thể tạo hoặc nhận.

### 4.1 Khóa bảo mật và khóa mật mã

Khóa bảo mật FIDO2 có thể bảo vệ khóa riêng và ký một thử thách mới. Máy chủ kiểm chứng chữ ký bằng khóa công khai đã gắn với tài khoản. Khóa riêng không được gửi lên máy chủ trong luồng thông thường.

Cơ chế này có thể chống phishing tốt vì phản hồi WebAuthn gắn với **Relying Party ID/origin** hợp lệ và thử thách. Trang giả ở một origin khác không thể tùy tiện thu được một assertion hợp lệ cho dịch vụ thật.

**Lưu ý:** một khóa bảo mật không yêu cầu PIN hoặc sinh trắc trong một luồng cụ thể có thể chỉ chứng minh **sở hữu khóa**. Khi có thêm xác minh người dùng cục bộ được authenticator thực thi và ứng dụng kiểm tra kết quả đúng cách, cấu hình có thể đạt xác thực bằng nhiều yếu tố. Phải xem **cách triển khai và chính sách xác minh**, không suy ra chỉ từ tên sản phẩm.

### 4.2 TOTP và mã OTP

Ứng dụng tạo TOTP thường giữ một bí mật đã đăng ký và sinh mã theo thời gian. Máy chủ kiểm tra mã và chính sách thời gian/thử sai; quyền truy cập authenticator được dùng như bằng chứng sở hữu trong mô hình thông thường.

Ưu điểm là dễ triển khai với nhiều tài khoản. Hạn chế quan trọng:

- **Mã có thể bị phishing theo thời gian thực**: trang giả chuyển mã vừa nhập tới dịch vụ thật.
- Nếu ứng dụng hoặc bí mật TOTP bị sao chép hoặc lộ, yếu tố sở hữu có thể mất tính độc lập.
- Máy chủ cần giới hạn số lần thử, chấp nhận cửa sổ thời gian hợp lý và tránh cho phép **sử dụng lặp lại** mã đã được chấp nhận trong cùng chu kỳ theo cơ chế của mình.
- Mã hết hạn nhanh giúp giảm rủi ro phát lại ngoài thời gian hợp lệ nhưng **không chặn** kẻ tấn công dùng ngay mã trong khoảng thời gian còn hiệu lực.

**SMS OTP** phụ thuộc vào quyền kiểm soát số điện thoại/kênh nhận mã, dễ chịu tác động của SIM swap, tái cấp số, chuyển tiếp tin và phishing. Nó có thể hỗ trợ một số luồng có rủi ro thấp hơn nhưng không nên được coi là phương thức chống phishing mạnh.

**Email OTP hoặc magic link** cần được đánh giá riêng: quyền kiểm soát hộp thư có thể phụ thuộc cùng mật khẩu hoặc phiên đã dùng; email có thể bị chiếm và không luôn tạo yếu tố sở hữu độc lập phù hợp cho MFA. Không mặc nhiên tính một email gửi mã là “yếu tố thứ hai an toàn” cho mọi mức rủi ro.

### 4.3 Push approval và thiết bị đã đăng ký

Một ứng dụng gửi thông báo yêu cầu phê duyệt đăng nhập có thể chứng minh quyền kiểm soát thiết bị. Nhưng nếu chỉ có nút **Approve** mà không hiển thị ngữ cảnh rõ ràng, kẻ tấn công có thể gửi yêu cầu liên tiếp gây **MFA fatigue/push bombing** để người dùng bấm đồng ý.

Cải thiện bằng đối chiếu số (number matching), hiển thị rõ thiết bị/vị trí/ngữ cảnh, hạn chế yêu cầu dồn dập và từ chối khi người dùng không chủ động đăng nhập. Những tín hiệu như vị trí gần đúng hỗ trợ quyết định nhưng không nên coi là chứng cứ duy nhất.

## 5. Yếu tố “đặc điểm vốn có”: sinh trắc học

**Inherence** dựa vào một đặc điểm gắn với cơ thể hoặc hành vi của chủ thể, như vân tay, khuôn mặt hoặc một dạng sinh trắc hành vi được kiểm chứng trong thiết kế phù hợp.

Sinh trắc có ích vì người dùng không phải nhớ thêm bí mật. Nhưng cần hiểu giới hạn:

- **Tính duy nhất không tuyệt đối:** phép đối sánh sinh trắc thường có xác suất sai, với nguy cơ chấp nhận sai hoặc từ chối nhầm.
- **Khó thu hồi:** khi mẫu sinh trắc bị lộ hoặc bị sao chép, người dùng không thể dễ dàng “đổi ngón tay”.
- **Có thể bị giả mạo:** yêu cầu chống giả mạo/phát hiện sự hiện diện sống (presentation attack detection) phù hợp với cảm biến và rủi ro.
- **Riêng tư:** xử lý và lưu dữ liệu sinh trắc nhạy cảm cần giới hạn rõ ràng, ưu tiên kiểm tra cục bộ, hạn chế truyền mẫu thô.
- **Khả năng tiếp cận:** cần cơ chế thay thế an toàn cho người không thể sử dụng sinh trắc theo thiết kế.

### Nhận diện bằng khuôn mặt và đăng nhập bằng khuôn mặt có giống nhau?

Không nhất thiết.

- Nếu một ứng dụng gửi ảnh khuôn mặt lên server rồi so khớp với ảnh hồ sơ, đó là một **kiến trúc xử lý sinh trắc** có rủi ro bảo mật và riêng tư riêng.
- Nếu người dùng mở khóa **authenticator có passkey** bằng khuôn mặt, bước kiểm tra thường diễn ra **cục bộ trên thiết bị**; máy chủ kiểm tra **chữ ký mật mã và các cờ/điều kiện WebAuthn**.

Hai giao diện đều có thể hiện “Đăng nhập bằng khuôn mặt”, nhưng bằng chứng mà máy chủ nhận được và ranh giới tin cậy hoàn toàn khác nhau.

**Nguyên tắc:** sinh trắc thường nên tham gia một giải pháp có thêm bảo vệ thiết bị/khóa hoặc cơ chế tương đương; không giả định một ảnh khuôn mặt gửi qua HTTP đủ để xác thực mạnh.

## 6. MFA là gì và khi nào hai bước không thành MFA?

**Xác thực đa yếu tố (Multi-Factor Authentication, MFA)** yêu cầu bằng chứng từ **ít nhất hai nhóm yếu tố độc lập theo thiết kế**, để khi một nhóm bị lộ hoặc bị đánh bại, kẻ tấn công vẫn phải vượt qua kiểm tra còn lại.

Một luồng có hai màn hình chưa chắc là MFA. Một phương thức có thể đồng thời kết hợp nhiều yếu tố ngay trong **một thao tác**, ví dụ một passkey được bảo vệ bằng xác minh người dùng cục bộ trong authenticator đáp ứng chính sách.

### So sánh các tình huống

| Tình huống | Nhóm yếu tố liên quan | Có thể gọi MFA không? |
| --- | --- | --- |
| Mật khẩu + một PIN gửi lên server | Hai giá trị thuộc nhóm **điều biết** | **Không tự động**: hai bước nhưng cùng nhóm. |
| Mật khẩu + mã từ ứng dụng TOTP đã đăng ký | **Điều biết + sở hữu** | **Có thể**, khi hai thành phần được đăng ký/kiểm chứng an toàn và đủ độc lập. |
| Mật khẩu + SMS OTP | **Điều biết + sở hữu kênh nhận mã** trong các triển khai thông thường | **Có thể**, nhưng không chống phishing mạnh và chịu rủi ro đổi SIM/tái cấp số. |
| Mật khẩu + email có thể mở bằng cùng mật khẩu bị lộ | Có thể cùng phụ thuộc vào **một bí mật/phiên** | **Không nên mặc nhiên tính là MFA độc lập**. |
| Khóa bảo mật không yêu cầu xác minh người dùng | Bằng chứng sở hữu khóa | **Thường chỉ một yếu tố** ở luồng đó. |
| Passkey + xác minh người dùng cục bộ được thực thi và kiểm tra đúng chính sách | Sở hữu khóa + xác minh người dùng (PIN/sinh trắc) | **Có thể là MFA trong một authenticator**; cần kiểm tra cấu hình và cờ xác minh. |
| CAPTCHA + mật khẩu | CAPTCHA hỗ trợ chống bot, không phải bằng chứng danh tính riêng | **Không**. |
| Token phiên đã cấp + mật khẩu trong cùng ứng dụng | Token mang trạng thái phiên, chưa chắc đại diện authenticator độc lập | **Không kết luận MFA** chỉ từ hai giá trị gửi lên. |

**MFA không đồng nghĩa “yêu cầu OTP”, và không phải mọi OTP đều giống nhau.** Thiết kế cần xem từng yếu tố có đáng tin, độc lập, chống phishing và chống phát lại đến đâu.

### “Độc lập” nghĩa là gì?

Các yếu tố cần tránh cùng thất bại vì một điểm yếu dễ khai thác. Ví dụ, nếu mật khẩu tài khoản và toàn bộ mã khôi phục được gửi tới chính hộp thư có cùng mật khẩu đang bị đánh cắp, hai bước khó mang lại mức tách biệt kỳ vọng.

Ngay cả khi hai yếu tố khác nhóm, thiết bị bị malware kiểm soát hoặc một luồng phishing thời gian thực vẫn có thể lấy được cả mật khẩu và OTP. Vì vậy, mức bảo đảm cần đánh giá **chất lượng và ranh giới chứng minh**, không chỉ đếm yếu tố.

## 7. Yếu tố và phương thức chống phishing, replay

### 7.1 Phishing

Phishing lừa người dùng trình bằng chứng cho kẻ tấn công. Mật khẩu và OTP do người dùng nhập có thể bị chuyển tiếp ngay; một kẻ tấn công có thể mở một luồng đăng nhập thật ở phía sau và đánh cắp kết quả.

**Passkey/FIDO2/WebAuthn** có khả năng chống phishing mạnh nhờ khóa riêng không được gửi đi và phản hồi được ràng buộc với domain/RP ID hợp lệ, thử thách và ngữ cảnh giao thức. Điều này không có nghĩa passkey tự chặn XSS, thiết bị bị chiếm, lộ cookie phiên hay mọi lạm dụng luồng khôi phục.

### 7.2 Replay

**Replay** là việc ghi lại một bằng chứng hoặc thông điệp hợp lệ rồi phát lại để được chấp nhận lần nữa.

- Với thử thách–phản hồi mật mã, máy chủ tạo **challenge/nonce mới, khó đoán** và kiểm tra phản hồi gắn với challenge cùng ngữ cảnh nhận phù hợp.
- Với OTP ngắn hạn, cần **hạn sử dụng, kiểm soát thử sai và từ chối tái sử dụng** trong phạm vi mà cơ chế yêu cầu. Thời hạn ngắn không đủ để ngăn replay ngay lập tức.
- Với token, phải kiểm tra **issuer, audience, thời hạn, chữ ký/mã xác thực** và các điều kiện ràng buộc khác; bearer token còn hiệu lực có thể tiếp tục được dùng nếu bị lấy cắp.

Có nhiều lớp chống replay khác nhau: bằng chứng đăng nhập, request nghiệp vụ, token truy cập và các giao dịch đặc biệt. Chống replay ở một lớp **không** làm các lớp khác tự động an toàn.

### 7.3 Lạm dụng đăng nhập

Khi một attacker biết tên tài khoản hoặc danh sách email, họ có thể thử mật khẩu, bắn hàng loạt yêu cầu OTP hoặc ép gửi push notification. Bảo vệ thực tế thường cần:

- Giới hạn tốc độ thử, cơ chế chậm dần/kiểm soát theo rủi ro, phát hiện hành vi bất thường và tránh tạo điều kiện dò tài khoản.
- Thông báo/ghi nhận sự kiện có ý nghĩa, nhưng tránh ghi log mật khẩu, OTP, secret và token rõ.
- Tùy tình huống, yêu cầu phương thức mạnh hơn hoặc xác thực tăng cường.
- Cơ chế báo cáo đăng nhập bất thường và thu hồi phiên khi nghi bị chiếm.

CAPTCHA và phát hiện bot có thể giúp chống lạm dụng, nhưng **không chứng minh chủ thể là ai** và không thay thế yếu tố xác thực.

## 8. Ranh giới tin cậy: máy chủ kiểm chứng cái gì?

Một đăng nhập đúng thiết kế không chỉ kiểm tra giao diện đã hiện “Thành công”. Những thành phần không đáng tin hoàn toàn, chẳng hạn trình duyệt hoặc ứng dụng di động, có thể bị sửa hoặc giả lập. Máy chủ xác thực cần tự kiểm chứng bằng chứng đã được chấp nhận theo chính sách.

~~~mermaid
flowchart TD
    U["Người dùng / thiết bị"] -->|"Trình bằng chứng"| B["Client: giao diện đăng nhập"]
    B -->|"Yêu cầu qua kênh bảo mật"| V["Dịch vụ xác thực"]
    V --> C{"Credential đã gắn đúng tài khoản,\n bằng chứng hợp lệ, chính sách đạt?"}
    C -->|"Không"| X["Từ chối / hạn chế thử / ghi sự kiện phù hợp"]
    C -->|"Có"| S["Tạo phiên hoặc token theo chính sách"]
    S --> R["Ứng dụng / API"]
    R --> P{"Phiên/token hợp lệ và\n quyền truy cập phù hợp?"}
    P -->|"Có"| O["Thực hiện thao tác"]
    P -->|"Không"| D["Từ chối"]
~~~

**Cần xác minh ít nhất ba mối liên hệ:**

1. **Bằng chứng ↔ credential:** chứng minh mật khẩu, mã, chữ ký hoặc phương thức khác hợp lệ theo cơ chế tương ứng.
2. **Credential ↔ danh tính:** credential đã được đăng ký và còn hiệu lực cho đúng chủ thể/tài khoản.
3. **Danh tính ↔ hành động:** sau khi xác thực, hệ thống vẫn phải kiểm tra **phân quyền** theo tài nguyên và ngữ cảnh.

Client gửi trường **authenticated=true**, **mfaPassed=true** hoặc **userId=42** không được xem là bằng chứng nếu máy chủ không kiểm chứng. Tương tự, chỉ ẩn nút trong giao diện không thay thế kiểm soát truy cập ở API.

### Ví dụ chuỗi kiểm tra một đăng nhập mật khẩu + TOTP

Đoạn sau là **giả mã** giải thích trình tự, không phải mã triển khai hoàn chỉnh:

~~~text
input: accountIdentifier, password, totpCode, requestContext

account = findAccountForLogin(accountIdentifier)

if shouldThrottle(requestContext, account):
    rejectSafely()

if !verifyPasswordAgainstStoredHash(account, password):
    recordFailedAttempt()
    rejectSafely()

authenticator = getActiveTotpAuthenticator(account)
if authenticator is absent:
    rejectSafely()

if !verifyTotpWithWindowAndReplayProtection(authenticator, totpCode):
    recordFailedAttempt()
    rejectSafely()

session = createSession(
    subjectId = account.internalId,
    authenticationContext = ["password", "totp"],
    issuedAt = currentTime,
    validityAndRotationPolicy = serverPolicy
)

returnProtectedSession(session)
~~~

Ví dụ cho thấy hệ thống phải xác minh **cả hai bằng chứng và liên kết của chúng với cùng tài khoản** trước khi cấp phiên. Một mã OTP đúng nhưng thuộc tài khoản khác không được chấp nhận. Sau đó, API vẫn cần kiểm tra phiên và quyền trên từng thao tác.

## 9. Một phương thức mạnh không thay thế bảo vệ phiên

Người dùng đăng nhập bằng MFA rồi nhận được cookie phiên hoặc access token. Nếu token bị lấy cắp, kẻ giữ **bearer token** hợp lệ có thể sử dụng trong phạm vi token cho phép, kể cả khi họ không biết mật khẩu hay không có authenticator ban đầu.

Vì vậy, cần thiết kế:

- Cookie phiên web với cờ và phạm vi phù hợp như **Secure**, **HttpOnly**, **SameSite**, kết hợp bảo vệ CSRF và XSS.
- Thời hạn sử dụng phù hợp, kiểm soát thu hồi, đăng xuất và xoay/đổi session ID khi cần.
- Access token có **audience, issuer, phạm vi, thời hạn** và cơ chế kiểm chứng thích hợp. Không tin claim chưa được xác minh.
- Xác thực lại hoặc **step-up authentication** khi đổi mật khẩu, thêm thiết bị MFA, rút tiền, chuyển quyền hoặc thực hiện hành động rủi ro cao.
- Giám sát hành vi và phương án thu hồi phiên đã cấp khi tài khoản/credential bị nghi chiếm.

**Step-up** là yêu cầu tăng mức bảo đảm khi một thao tác đòi hỏi rủi ro cao hơn so với xác thực trước đó. Nó không nhất thiết phải là “thêm một OTP” nếu OTP có thể bị phishing; cần chọn bằng chứng phù hợp với mối đe dọa.

## 10. Đăng ký, thay đổi và khôi phục yếu tố xác thực

Một authenticator không tự nhiên trở thành yếu tố hợp lệ cho mọi tài khoản. Hệ thống cần quy trình **enrollment/binding** để đăng ký an toàn và quản lý vòng đời.

| Giai đoạn | Câu hỏi cần trả lời | Rủi ro nếu sai |
| --- | --- | --- |
| **Đăng ký lần đầu** | Tài khoản này được tạo cho ai? Ai được quyền đăng ký authenticator? | Gắn yếu tố của kẻ mạo danh từ đầu. |
| **Thêm authenticator** | Người đang thêm khóa/thiết bị có được kiểm tra đủ mạnh không? | Kẻ đã chiếm phiên thêm passkey riêng, duy trì truy cập lâu dài. |
| **Xác thực thường ngày** | Bằng chứng, nguồn gửi, thử thách, trạng thái và chính sách có hợp lệ không? | Chấp nhận OTP cũ, sai tài khoản hoặc bỏ qua MFA. |
| **Thu hồi/thay đổi** | Thiết bị mất, khóa lộ, nhân viên nghỉ việc thì vô hiệu hóa ra sao? | Credential cũ tiếp tục được chấp nhận. |
| **Khôi phục tài khoản** | Khi mất mọi yếu tố, làm sao khôi phục mà không hạ thấp mức bảo vệ? | “Quên mật khẩu” trở thành đường vòng qua MFA. |
| **Kiểm tra, thông báo, hỗ trợ** | Có phát hiện thay đổi nhạy cảm, lưu nhật ký tối thiểu và thông báo hợp lệ không? | Chiếm tài khoản âm thầm, không thể đối soát. |

Khôi phục cần được đánh giá như một **luồng xác thực nhạy cảm**. Liên kết đặt lại mật khẩu và mã khôi phục nên có thời hạn, giới hạn thử và phạm vi dùng phù hợp; quy trình khôi phục yếu hơn có thể vô hiệu hóa giá trị của MFA mạnh.

Để tránh khóa người dùng hợp lệ, có thể đăng ký nhiều authenticator độc lập hoặc cung cấp mã dự phòng theo chính sách. Mã dự phòng cần được sinh, cấp phát, lưu trữ và dùng một lần an toàn. Khi người dùng thay yếu tố, hệ thống cần xem xét thông báo và xử lý phiên/token cũ.

### Tình huống: mất điện thoại đang giữ passkey và TOTP

Một người bị mất điện thoại, trên đó có passkey và ứng dụng TOTP. Việc hiện hai ứng dụng không có nghĩa người dùng luôn có hai yếu tố dự phòng độc lập: nếu **cả hai cùng mất khi mất một thiết bị**, khả năng khôi phục sẽ bị ảnh hưởng.

Một thiết kế tốt cân nhắc từ trước: thiết bị dự phòng, phương án khôi phục được bảo vệ, chính sách thay credential, khóa phiên bị nghi lộ và hướng dẫn người dùng bảo vệ tài khoản sau khi mất thiết bị.

## 11. Chọn yếu tố theo chủ thể và mức rủi ro

Không có một tổ hợp phù hợp cho tất cả trường hợp. Mục tiêu là bảo vệ tài sản và hành động mà không tạo rào cản không cần thiết.

| Ngữ cảnh | Cách tiếp cận thường phù hợp | Điều cần kiểm tra |
| --- | --- | --- |
| **Xem nội dung công khai** | Có thể không yêu cầu xác thực người dùng. | Vẫn kiểm soát lạm dụng API/tài nguyên khi cần. |
| **Tài khoản cá nhân thông thường** | Passkey hoặc mật khẩu được bảo vệ tốt kèm MFA phù hợp. | Bảo vệ đăng nhập, phiên, thử sai và khôi phục. |
| **Truy cập dữ liệu nhạy cảm/đặc quyền** | Ưu tiên xác thực chống phishing, quản trị thiết bị/credential và step-up theo rủi ro. | Không chỉ dựa vào TOTP/SMS nếu đối thủ có khả năng phishing. |
| **Đổi yếu tố đăng nhập hoặc phương thức khôi phục** | Xác thực lại đủ mạnh, xác minh quyền kiểm soát, thông báo thay đổi. | Không để phiên bị chiếm âm thầm thêm authenticator. |
| **API dịch vụ với dịch vụ** | Credential máy/dịch vụ như mTLS hoặc cơ chế token được cấp phù hợp. | Xác thực danh tính dịch vụ, quản lý khóa, phạm vi quyền; không nhầm với MFA của con người. |
| **Thiết bị chia sẻ hoặc môi trường dễ mất thiết bị** | Chọn authenticator có khả năng bảo vệ, thay/thu hồi và khôi phục thực tế. | Điểm thất bại chung giữa các yếu tố, rò rỉ trên máy dùng chung. |

**Chứng chỉ số và mTLS** thường hữu ích để xác thực thiết bị/dịch vụ dựa trên quyền sở hữu khóa riêng. Nhưng việc một máy chủ có chứng chỉ hợp lệ **không chứng minh** nhân viên đang thao tác trên máy chủ đã được xác thực bằng hai yếu tố. Phải phân biệt chủ thể là **người**, **thiết bị** hay **dịch vụ**.

**Danh tính liên kết/SSO** cũng không phải yếu tố thứ tư: SSO là kiến trúc chuyển giao kết quả xác thực giữa IdP và ứng dụng. Ứng dụng phải kiểm chứng kết quả từ đúng IdP, đối tượng nhận, thời hạn và ngữ cảnh; các yếu tố cụ thể được thực hiện ở IdP theo chính sách và được biểu diễn bằng ngữ cảnh xác thực đáng tin cậy khi cần.

## 12. Một tình huống thiết kế xuyên suốt

Xét một hệ thống quản lý tài khoản có thao tác xem hồ sơ, thay phương thức xác thực và chuyển tiền.

**Bước 1 — Đăng ký tài khoản.** Hệ thống tạo mã chủ thể nội bộ và đăng ký passkey hoặc mật khẩu/OTP theo chính sách. Việc xác minh email không tự chứng minh danh tính pháp lý; nếu nghiệp vụ cần, quy trình kiểm chứng danh tính phải tách riêng.

**Bước 2 — Đăng nhập.** Người dùng hoàn tất thử thách với authenticator đã gắn đúng tài khoản. Nếu dùng password + TOTP, máy chủ kiểm tra cả hai, ngăn brute force và dùng lại mã. Nếu dùng passkey, máy chủ kiểm chứng challenge, RP ID/origin và chính sách user verification tương ứng.

**Bước 3 — Thiết lập phiên.** Máy chủ cấp cookie phiên/token với thời hạn và phạm vi phù hợp. Client không tự quyết định rằng mình đã đạt MFA; kết quả đến từ bộ phận xác thực đáng tin cậy.

**Bước 4 — Xem hồ sơ.** API kiểm tra phiên/token và quyền trên hồ sơ yêu cầu. Đăng nhập thành công không cấp quyền xem hồ sơ mọi người.

**Bước 5 — Chuyển tiền.** Hệ thống đánh giá rủi ro và có thể yêu cầu step-up hoặc xác nhận giao dịch phù hợp. Một OTP không ràng buộc với chi tiết giao dịch có thể bị kẻ gian lợi dụng trong luồng phishing thời gian thực; với nghiệp vụ cần bảo đảm cao, xem xét cơ chế ràng buộc chứng thực với thao tác cụ thể.

**Bước 6 — Mất authenticator.** Hệ thống thực hiện khôi phục với bằng chứng tương xứng, thông báo, thu hồi credential không còn tin cậy và xử lý phiên theo chính sách. Kẻ chỉ chiếm email khôi phục không nên mặc nhiên thay được mọi yếu tố cho tài khoản đặc quyền.

Điểm quan trọng là **tính liên tục của sự tin cậy**: từ đăng ký bằng chứng, kiểm chứng yếu tố, cấp phiên, sử dụng API, tới thu hồi và khôi phục.

## 13. Những ngộ nhận cần tránh

**Ngộ nhận 1: “Có hai ô nhập là MFA.”**  
Không đúng. Hai ô mật khẩu và PIN vẫn có thể cùng một nhóm yếu tố.

**Ngộ nhận 2: “OTP luôn chống phishing.”**  
Không đúng. TOTP, SMS OTP và nhiều loại OTP có thể bị lấy rồi sử dụng theo thời gian thực. Cần chọn phương thức chống phishing khi rủi ro yêu cầu.

**Ngộ nhận 3: “Passkey chỉ dùng sinh trắc.”**  
Không đúng. Passkey dựa trên mật mã khóa công khai. Authenticator có thể được mở bằng PIN, sinh trắc hoặc cơ chế thích hợp; máy chủ kiểm chứng assertion theo chính sách.

**Ngộ nhận 4: “Sinh trắc là mật khẩu không thể đánh cắp.”**  
Không đúng. Sinh trắc có sai số, nguy cơ giả mạo và hậu quả riêng tư nếu dữ liệu bị lộ; cần kiểm tra trên thành phần tin cậy với bảo vệ phù hợp.

**Ngộ nhận 5: “Đăng nhập bằng MFA rồi thì token không đáng lo.”**  
Không đúng. Bearer token hoặc cookie phiên bị đánh cắp có thể bị sử dụng mà không cần trình lại các yếu tố ban đầu.

**Ngộ nhận 6: “MFA mạnh thì không cần bảo vệ reset password.”**  
Không đúng. Nếu luồng khôi phục yếu, kẻ tấn công có thể đi vòng qua MFA bằng cách thay credential hoặc authenticator.

**Ngộ nhận 7: “IP lạ là một yếu tố xác thực mới.”**  
Không đúng. IP, vị trí, thời gian đăng nhập hoặc dấu hiệu thiết bị có thể làm **tín hiệu rủi ro**, không tự trở thành bằng chứng danh tính đã đăng ký.

## 14. Tự kiểm tra

**Câu 1.** Mật khẩu và PIN bí mật gửi lên server là một hay hai nhóm yếu tố? Vì sao?

**Đáp án:** Cả hai thuộc nhóm **điều biết**. Có thể là hai bước nhưng không tự động đạt MFA vì không có bằng chứng độc lập thuộc nhóm khác.

**Câu 2.** Vì sao ứng dụng TOTP được coi là một phương thức dựa vào yếu tố sở hữu trong nhiều mô hình nhưng mã TOTP vẫn có thể bị phishing?

**Đáp án:** Mã được tạo từ bí mật trên authenticator đã đăng ký, biểu hiện quyền kiểm soát authenticator. Tuy nhiên mã ngắn hạn có thể bị người dùng nhập vào trang giả và bị chuyển ngay đến dịch vụ thật khi còn hiệu lực.

**Câu 3.** Điện thoại dùng Face ID để mở khóa passkey rồi xác thực qua WebAuthn. Máy chủ có cần nhận ảnh khuôn mặt không?

**Đáp án:** Thông thường không. Việc xác minh người dùng diễn ra cục bộ trong authenticator; máy chủ kiểm tra phản hồi mật mã, nguồn gọi và các điều kiện user verification theo chính sách.

**Câu 4.** Khi người dùng gửi access token còn hạn, API có nên coi đó là lần trình yếu tố MFA mới?

**Đáp án:** Không. Token thường mang kết quả xác thực đã xảy ra. API cần kiểm tra tính hợp lệ và quyền; hành động nhạy cảm có thể yêu cầu xác thực lại bằng phương thức đủ mạnh.

**Câu 5.** Một service gọi API bằng mTLS đã chứng minh điều gì? Điều đó có đồng nghĩa người dùng cuối đạt MFA không?

**Đáp án:** Nó có thể chứng minh danh tính dịch vụ/thiết bị sở hữu khóa riêng theo chuỗi tin cậy được chấp nhận. Nó không tự chứng minh danh tính hoặc MFA của con người đang sử dụng hệ thống.

**Câu 6.** Tại sao nên từ chối dùng lại cùng mã TOTP đã được chấp nhận trong cửa sổ hợp lệ?

**Đáp án:** Để giảm nguy cơ một mã bị nhìn thấy hoặc thu thập rồi phát lại trong thời gian còn hiệu lực; cần kết hợp kiểm soát thử sai và chính sách thời gian.

**Câu 7.** Kẻ tấn công có phiên đăng nhập hợp lệ và cố thêm khóa bảo mật của mình. Điểm kiểm soát nào cần đặt trước khi gắn credential mới?

**Đáp án:** Kiểm tra lại quyền kiểm soát tài khoản bằng mức xác thực phù hợp, quản lý trạng thái phiên, thông báo thay đổi và có khả năng vô hiệu hóa thiết bị/credential thêm trái phép.

**Câu 8.** Hệ thống yêu cầu cả mật khẩu và OTP qua email, nhưng hộp thư có thể mở bằng cùng mật khẩu bị lộ. Điểm yếu là gì?

**Đáp án:** Cơ chế có thể phụ thuộc vào cùng bí mật, làm suy yếu tính độc lập của bằng chứng; không nên mặc nhiên xem đây là MFA đủ mạnh. Cần thiết kế kênh, authenticator và quy trình khôi phục sao cho một sự cố đơn lẻ không dễ chiếm tất cả.

## Ghi nhớ

**Yếu tố xác thực** mô tả **loại bằng chứng** dùng để chứng minh quyền sử dụng danh tính: **điều biết, thứ sở hữu hoặc đặc điểm vốn có**. **MFA** có ý nghĩa khi các bằng chứng được kết hợp với mức độc lập và chất lượng phù hợp; **hai bước nhập liệu không mặc nhiên là hai yếu tố**.

Để xác thực an toàn, hệ thống phải gắn credential với đúng chủ thể, kiểm chứng bằng chứng và ngữ cảnh ở ranh giới tin cậy, ưu tiên phương thức chống phishing khi cần, chống replay, bảo vệ token/phiên, phân quyền từng hành động và giữ luồng thay đổi/khôi phục authenticator đủ mạnh. Số lượng yếu tố là điểm khởi đầu để thiết kế, còn mức an toàn thực tế phụ thuộc vào toàn bộ vòng đời xác thực.
