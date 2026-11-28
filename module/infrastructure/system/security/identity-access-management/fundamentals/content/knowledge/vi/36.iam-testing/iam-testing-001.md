# Authentication test — Kiểm thử xác thực

## 1. Kiểm thử xác thực cần chứng minh điều gì?

**Authentication test** kiểm tra hệ thống có nhận biết đúng chủ thể từ bằng chứng xác thực hợp lệ và từ chối việc thiết lập danh tính khi bằng chứng không đáp ứng yêu cầu hay không. Chủ thể có thể là người dùng, quản trị viên, ứng dụng hoặc workload.

Một form đăng nhập chuyển sang trang chủ chưa đủ để kết luận xác thực đúng. Kiểm thử còn cần biết tài khoản nào đã được thiết lập, những yếu tố xác thực nào đã hoàn thành, phiên hoặc token nào được tạo và các đường truy cập trực tiếp có được bảo vệ hay không.

Ví dụ, ứng dụng yêu cầu mật khẩu và OTP. Sau khi nhập đúng mật khẩu, người dùng được chuyển tới màn hình OTP. Nếu API đã xem phiên trung gian là phiên đăng nhập đầy đủ, người dùng có thể truy cập dữ liệu dù chưa hoàn thành bước thứ hai. Ca “nhập đúng mật khẩu và OTP thì đăng nhập thành công” sẽ không tự phát hiện lỗi này.

Mục tiêu của bộ kiểm thử là xác minh các điều kiện chấp nhận và từ chối theo contract xác thực đã công bố, tại cả luồng bình thường, luồng lỗi và các điểm chuyển trạng thái quan trọng.

## 2. Phân biệt xác thực với phân quyền và quản lý phiên

| Phạm vi | Câu hỏi chính | Ví dụ kiểm thử |
|---|---|---|
| Xác thực | Hệ thống có đủ bằng chứng để nhận biết chủ thể này không? | Mật khẩu sai không tạo phiên đăng nhập đầy đủ |
| Phân quyền | Chủ thể đã được nhận biết có được thực hiện hành động này không? | Người dùng hợp lệ không được đọc hóa đơn của tenant khác |
| Quản lý phiên | Trạng thái xác thực được duy trì và kết thúc thế nào? | Session ID cũ được xử lý đúng sau đăng nhập hoặc đăng xuất |
| Vòng đời danh tính | Trạng thái tài khoản và credential thay đổi thế nào? | Tài khoản bị disable không được thiết lập đăng nhập mới |

Các phạm vi giao nhau nhưng không thay thế cho nhau. Đăng nhập đúng tài khoản không chứng minh mọi API phân quyền đúng. Ngược lại, một API trả lỗi truy cập cũng chưa chứng minh nó đã xác thực credential đúng; có thể request bị chặn ở một bước không liên quan.

Khi lập kế hoạch, cần ghi rõ thành phần đang kiểm tra. Kiểm thử dịch vụ mật khẩu khác với kiểm thử client OIDC nhận kết quả từ IdP, hoặc resource server xác minh access token. Một bộ test của ứng dụng không tự chứng minh toàn bộ cơ chế xác thực bên trong nhà cung cấp danh tính hoạt động đúng.

## 3. Xác định contract và trạng thái trước khi viết ca kiểm thử

### 3.1. Những thông tin cần chốt

Contract xác thực nên làm rõ phương thức được hỗ trợ, nhóm tài khoản áp dụng, trạng thái tài khoản được phép đăng nhập, yêu cầu MFA hoặc xác thực tăng cường và loại credential được chấp nhận tại từng endpoint.

Với token hoặc assertion, cần biết issuer, audience, loại token, nguồn khóa, thuật toán được phép và chính sách thời gian. Với phiên, cần biết trạng thái nào là chưa xác thực, đang thực hiện challenge và đã xác thực đầy đủ theo yêu cầu của ứng dụng.

Các ngưỡng retry, throttling, lockout và thời gian cho phép sai lệch đồng hồ phải lấy từ cấu hình hoặc yêu cầu thực tế. Không tự chọn một con số phổ biến rồi coi mọi hệ thống dùng con số khác là lỗi.

### 3.2. Kiểm tra chuyển trạng thái, không chỉ từng màn hình

Một mô hình đơn giản cho luồng có MFA:

```text
Chưa xác thực
    → bước xác thực đầu tiên đạt yêu cầu
    → đang chờ hoàn thành MFA
    → MFA đạt yêu cầu và challenge còn hợp lệ
    → phiên xác thực đầy đủ theo contract
    → phiên hết hạn hoặc bị kết thúc theo cơ chế của hệ thống
```

Tại trạng thái chờ MFA, hệ thống có thể tạo cookie hoặc session trung gian để quản lý challenge. Điều cần kiểm tra là trạng thái đó chưa được phép truy cập như phiên đã hoàn tất, không phải cấm tuyệt đối mọi session trước bước cuối.

Ca kiểm thử cần xem điều gì xảy ra khi bỏ qua bước, dùng lại challenge đã hoàn tất, chuyển challenge giữa hai tài khoản hoặc gọi trực tiếp endpoint được bảo vệ. Việc giao diện không hiển thị nút tiếp tục không chứng minh backend đã kiểm tra trạng thái.

## 4. Thiết kế dữ liệu và điều kiện kiểm thử

### 4.1. Tài khoản fixture có mục đích rõ ràng

Nên chuẩn bị các tài khoản thử nghiệm độc lập, chẳng hạn tài khoản hoạt động, tài khoản bị disable, tài khoản đang khóa, tài khoản có MFA và tài khoản chưa hoàn tất thiết lập theo chính sách. Mỗi ca cần biết trạng thái đầu vào và cách đưa dữ liệu về trạng thái đó.

Tránh để nhiều test cùng dùng một tài khoản rồi tác động lên bộ đếm thất bại, challenge hoặc phiên của nhau. Một ca lockout có thể làm ca đăng nhập hợp lệ thất bại không liên quan tới mục tiêu của nó. Cần tách fixture hoặc có cơ chế reset phù hợp trong môi trường kiểm thử.

Dùng dữ liệu tổng hợp và credential thử nghiệm. Các ca làm tăng bộ đếm sai hoặc khóa tài khoản nên chạy trên tài khoản được dành cho mục đích đó, trong môi trường và phạm vi được phép. OWASP WSTG cũng lưu ý cần tài khoản có thể chấp nhận bị khóa khi đánh giá cơ chế lockout. [OWASP WSTG — Testing for Weak Lock Out Mechanism](https://owasp.github.io/www-project-web-security-testing-guide/stable/4-Web_Application_Security_Testing/04-Authentication_Testing/03-Testing_for_Weak_Lock_Out_Mechanism).

### 4.2. Kiểm soát thời gian và dependency

Các test liên quan token, OTP hoặc session nên có cách kiểm soát đồng hồ hoặc tạo dữ liệu với thời điểm rõ ràng. Không nên phụ thuộc vào việc chờ ngẫu nhiên cho token hết hạn hoặc chạy sát một biên thời gian khó tái lập.

Khi hệ thống cho phép clock skew, cần kiểm tra cả vùng được chấp nhận và vùng chắc chắn vượt mức cho phép. Một token chỉ quá `exp` một giây có thể chưa bị từ chối nếu validator được cấu hình một khoảng dung sai lớn hơn; test phải phản ánh đúng contract đó.

Với IdP hoặc nguồn khóa bên ngoài, có thể dùng stub trong một số tầng test để tạo lỗi và thời điểm một cách ổn định. Nhưng cần ghi rõ những gì stub thay thế; test chạy với IdP giả không chứng minh cấu hình của IdP thật đã đúng.

## 5. Ma trận ca kiểm thử nền tảng

| Nhóm | Điều kiện đưa vào | Kết quả cần kiểm tra |
|---|---|---|
| Thành công | Credential đúng, tài khoản hợp lệ và đủ các bước bắt buộc | Thiết lập đúng chủ thể và trạng thái xác thực theo contract |
| Credential sai | Username hợp lệ nhưng mật khẩu sai | Không tạo phiên xác thực đầy đủ hoặc credential thành công mới |
| Không có tài khoản | Định danh không tồn tại trong namespace đang kiểm tra | Bị từ chối; phản hồi ngoài không tiết lộ thông tin không cần thiết |
| Dữ liệu thiếu hoặc sai dạng | Thiếu trường bắt buộc, chuỗi rỗng hoặc credential không hợp lệ về định dạng | Từ chối có kiểm soát, không bỏ qua kiểm tra và không gây lỗi không được xử lý |
| Tài khoản không được phép | Tài khoản bị disable hoặc đang bị khóa theo chính sách | Không thiết lập đăng nhập mới bằng credential dù giá trị đó từng đúng |
| Chưa hoàn tất MFA | Bước đầu đúng nhưng chưa hoàn tất challenge bắt buộc | Trạng thái trung gian không được dùng như đăng nhập đầy đủ |
| Challenge không hợp lệ | OTP sai, challenge hết hạn hoặc bị dùng lại trái contract | Bị từ chối và không hoàn thành xác thực cho sai tài khoản hoặc sai phiên |
| Bằng chứng bị sửa | Token hoặc assertion thay đổi mà không có bảo vệ mật mã hợp lệ | Không tin claims từ bằng chứng đó |
| Sai phạm vi token | Token hợp lệ về một số mặt nhưng sai issuer, audience hoặc loại | Bị từ chối tại thành phần chỉ được chấp nhận loại bằng chứng tương ứng |
| Sai thời gian | Token hết hạn vượt dung sai, hoặc chưa tới thời điểm được phép dùng | Không được chấp nhận trước hoặc sau giới hạn theo contract |
| Đường truy cập khác | Gọi trực tiếp API hoặc endpoint sau proxy mà không có bằng chứng hợp lệ | Không đi tới hành động được bảo vệ chỉ nhờ bỏ qua giao diện |
| Dependency lỗi | IdP, dịch vụ xác minh hoặc nguồn khóa không đáp ứng khi cần để xác thực mới | Không tự thiết lập danh tính thành công thiếu bằng chứng; có hành vi lỗi đã định nghĩa |

Ma trận cần được điều chỉnh theo phương thức hệ thống thật sự hỗ trợ. Không áp ca kiểm tra mật khẩu cho một endpoint chỉ chấp nhận chứng thư, hoặc yêu cầu OTP cho mọi luồng khi chính sách không quy định như vậy.

## 6. Kiểm thử theo phương thức xác thực

### 6.1. Username và mật khẩu

Ngoài ca đúng và sai, cần kiểm tra namespace tài khoản, xử lý dữ liệu thiếu, trạng thái bị disable, throttling và lockout theo cấu hình. Không nên có đường thay thế cho phép bỏ kiểm tra mật khẩu khi dependency lỗi hoặc khi một trường request mang giá trị đặc biệt.

Phản hồi cho tài khoản không tồn tại và mật khẩu sai cần được đánh giá theo chính sách chống dò tìm tài khoản. Kiểm tra cả nội dung, status, redirect và hành vi quan sát được. Với thời gian phản hồi, cần phương pháp đo và số mẫu phù hợp; một lần đo nhanh hoặc chậm không đủ để kết luận về side channel.

Một lần thất bại có thể tạo audit event hoặc tăng bộ đếm chống lạm dụng. Vì thế, assertion đúng không phải “không có bất kỳ thay đổi nào”, mà là “không tạo ra trạng thái xác thực thành công hoặc tác dụng nghiệp vụ được bảo vệ ngoài dự kiến”.

### 6.2. MFA, passkey và challenge

Với MFA, cần kiểm tra challenge gắn đúng tài khoản, phiên và mục đích; yếu tố thứ hai không được hoàn tất cho một phiên khác chỉ vì mã còn đúng. Các trường hợp hết hạn, nhập sai và dùng lại cần phản ánh cơ chế đang triển khai.

Không được áp quy tắc chống replay một cách máy móc cho mọi loại artifact. OTP hoặc authorization code có ngữ nghĩa khác với access token thường được trình bày trong nhiều request khi còn hiệu lực. Test phải kiểm tra quy tắc dùng lại của đúng loại bằng chứng, không coi mọi lần dùng lại token đều là tấn công cần bị chặn.

Với WebAuthn hoặc passkey, bộ kiểm thử cần bao phủ challenge, origin, RP ID và các yêu cầu xác minh người dùng theo cấu hình. Chỉ mock một hàm trả về `true` chưa kiểm tra việc xác minh bằng chứng của authenticator. Nên sử dụng công cụ hoặc thư viện kiểm thử tương thích cơ chế đang dùng, không tự tạo một trình xác minh mật mã đơn giản để thay implementation thật.

### 6.3. Token, assertion và đăng nhập liên kết

Với JWT, cần tách các thuộc tính kiểm tra để biết ca test thật sự đánh giá điều gì. Một token có signature sai đồng thời có audience sai sẽ bị từ chối, nhưng kết quả đó chưa chứng minh validator có kiểm tra audience.

Nên tạo token fixture sao cho các điều kiện khác hợp lệ trong từng ca cần kiểm tra, rồi thay đúng điều kiện mục tiêu. Ví dụ, ca sai audience dùng token có bảo vệ mật mã hợp lệ trong môi trường test và chỉ dành cho một API khác. Ca payload bị sửa dùng dữ liệu đã thay đổi mà không có chữ ký mới hợp lệ.

RFC 8725 đề cập việc kiểm soát thuật toán, xác minh issuer và audience, cùng quy tắc tách biệt để tránh nhầm loại JWT. Những nguyên tắc này là cơ sở để xây các ca chấp nhận và từ chối riêng, thay vì chỉ kiểm tra token đọc được JSON. [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725.html).

Trong client OIDC, kiểm thử thêm việc liên kết kết quả với giao dịch đăng nhập đã bắt đầu. Kiểm tra `state` theo cơ chế bảo vệ giao dịch của ứng dụng, và kiểm tra `nonce` khi được dùng hoặc được luồng yêu cầu. Với Authorization Code Flow có PKCE, cần có ca code verifier không phù hợp và code bị dùng lại theo contract của authorization server.

Các ca ID token phải dựa vào yêu cầu của OIDC, không lấy nguyên quy tắc của một access token tùy ý để thay thế. Kiểm tra issuer, audience, thời hạn và các điều kiện áp dụng cho luồng cụ thể là một phần của quá trình xác minh kết quả xác thực. [OpenID Connect Core 1.0 — ID Token Validation](https://openid.net/specs/openid-connect-core-1_0.html#IDTokenValidation).

### 6.4. Danh tính workload

Với API nhận credential của ứng dụng hoặc chứng thư workload, cần có ca credential đúng cho đúng chủ thể, credential sai, hết hạn, không thuộc nguồn tin cậy hoặc không dành cho mục đích endpoint.

Nếu dùng mTLS, test phải đi qua thành phần thực sự xác minh chứng thư hoặc kiểm tra contract truyền ngữ cảnh từ thành phần đó. Gửi một header tự khai tên dịch vụ không tương đương với một kết nối đã được xác thực bằng chứng thư.

Xác thực workload thành công vẫn cần bộ kiểm thử phân quyền riêng. Một service principal hợp lệ không tự được thực hiện mọi thao tác nghiệp vụ.

## 7. Chọn tầng kiểm thử và hiểu giới hạn của mock

| Tầng | Phù hợp để kiểm tra | Điều chưa được chứng minh chỉ bằng tầng này |
|---|---|---|
| Unit | Logic chuyển trạng thái, lựa chọn policy, xử lý lỗi và biên thời gian của thành phần | Cấu hình filter, kết nối IdP hoặc kiểm tra mật mã của toàn ứng dụng |
| Integration | Validator thật, security middleware, nguồn khóa thử nghiệm, session store và audit sink | Cấu hình toàn bộ hệ thống triển khai hoặc hành vi của IdP sản xuất |
| End-to-end | Luồng client–IdP–ứng dụng, callback, cookie và truy cập tài nguyên qua điểm vào thật của môi trường test | Mọi biến thể policy và mọi tình huống lỗi nếu không có ca tương ứng |

Một test controller dùng principal giả có thể kiểm tra hành vi khi đã xác thực, nhưng không kiểm tra request đã đi qua xác thực thật hay chưa. Tương tự, gắn một user vào security context của test không chứng minh chữ ký token, issuer hoặc audience được xác minh.

Với integration test, có thể dùng key và issuer chuyên dụng cho môi trường thử nghiệm nhưng vẫn chạy validator và security chain thật. Các ca lỗi nên thay đổi fixture hoặc phản hồi dependency theo mục tiêu, không tắt toàn bộ kiểm tra bảo mật để làm request đi qua.

Với end-to-end test, cần kiểm tra cả đường gọi trực tiếp. OWASP WSTG chỉ ra rằng bảo vệ riêng trang login có thể bị vượt qua khi các trang hoặc dịch vụ phía sau không thực thi xác thực. [OWASP WSTG — Testing for Bypassing Authentication Schema](https://owasp.github.io/www-project-web-security-testing-guide/stable/4-Web_Application_Security_Testing/04-Authentication_Testing/04-Testing_for_Bypassing_Authentication_Schema).

## 8. Một ca kiểm thử đầy đủ cần quan sát kết quả nào?

### 8.1. Đặc tả ca chưa hoàn tất MFA

Ví dụ dưới đây là đặc tả minh họa nằm trong tài liệu, không phải schema của một công cụ kiểm thử cụ thể:

```yaml
testId: AUTH-MFA-PENDING-001
purpose: Không coi phiên chờ MFA là phiên xác thực đầy đủ
given:
  accountState: ACTIVE
  authenticationPolicy: PASSWORD_AND_OTP
  firstFactor: PASSED
  challengeState: PENDING
when:
  action: Gọi trực tiếp API yêu cầu hoàn tất xác thực
then:
  protectedActionExecuted: false
  fullAuthenticationEstablished: false
  authenticationState: PENDING_MFA
  response: Theo contract từ chối hoặc yêu cầu hoàn tất challenge
  audit:
    containsEnoughContext: true
    containsPasswordOrOtpOrRawToken: false
```

Ca này không chỉ kiểm tra một thông báo ở giao diện. Nó phải xác nhận hành động được bảo vệ chưa được thực hiện và session trung gian không bị nâng thành trạng thái đầy đủ ngoài dự kiến.

### 8.2. Assertion nên phản ánh contract

Với thành công, kiểm tra đúng chủ thể, đúng namespace hoặc tenant liên quan, mức hoàn tất xác thực, loại phiên hoặc credential được tạo và khả năng truy cập endpoint yêu cầu xác thực. Việc có cookie mới không đủ nếu cookie đó chỉ phục vụ giao dịch trung gian.

Với thất bại, kiểm tra không tạo danh tính thành công mới, không trả credential thành công và không thực hiện hành động được bảo vệ. Đồng thời kiểm tra audit, bộ đếm hoặc challenge được cập nhật đúng chính sách, không ghi bí mật vào bằng chứng kiểm thử.

HTTP status cần được diễn giải theo loại endpoint. Một API có thể dùng `401` cho trường hợp chưa xác thực, trong khi trang login có thể trả HTML với status `200` kèm lỗi hoặc dùng redirect. Không kết luận thành công chỉ vì nhận `2xx`, cũng không chốt test chỉ bằng một mã lỗi mà bỏ qua trạng thái phía máy chủ.

Lỗi thiếu quyền sau khi xác thực là một trường hợp khác. Khi debug, cần xác định request bị từ chối ở bước nào, tránh coi một kết quả `403` từ policy nghiệp vụ là bằng chứng cho việc validator đã kiểm tra một claim cụ thể.

## 9. Làm bộ kiểm thử có thể tái lập và hữu ích khi hồi quy

### 9.1. Mỗi ca có điều kiện đầu vào độc lập

Nên đặt lại hoặc tách session, challenge, bộ đếm và tài khoản theo từng test khi cần. Không dựa vào thứ tự chạy ngầm của một suite để giả định tài khoản đã được mở khóa hoặc OTP chưa bị sử dụng.

Các thao tác có thời gian hiệu lực cần đồng hồ và khoảng chấp nhận được kiểm soát. Nếu chạy song song, cần tránh dùng chung fixture gây tranh chấp. Với kiểm thử rate limiting, số request và khoảng thời gian phải gắn với policy thử nghiệm được chọn, không dùng một vòng lặp không giới hạn.

### 9.2. Biết đường kiểm tra nào thật sự đã được chạy

Một ca từ chối có thể pass vì lỗi format xảy ra trước bước cần kiểm tra. Do đó, phải thiết kế đầu vào để tới được bước mục tiêu hoặc có bằng chứng kỹ thuật phù hợp trong môi trường test. Không yêu cầu thông báo lỗi chi tiết ở giao diện công khai chỉ để làm test dễ viết; có thể dùng audit hoặc instrumentation nội bộ đã kiểm soát.

Khi đổi thư viện xác thực, cấu hình issuer, key rotation, chính sách MFA hoặc cách truyền ngữ cảnh qua gateway, cần chạy các ca liên quan. Một test “đăng nhập đúng vẫn được” không đủ để phát hiện việc cấu hình mới vô tình chấp nhận thêm issuer hoặc loại token ngoài dự kiến.

### 9.3. Báo cáo kết quả với phạm vi rõ ràng

Báo cáo nên có mã ca, yêu cầu được kiểm tra, tầng kiểm thử, phiên bản cấu hình, điều kiện đầu vào, kết quả mong đợi, quan sát thực tế và bằng chứng đã loại credential hoặc dữ liệu nhạy cảm.

Phân biệt `PASS`, `FAIL`, không áp dụng và chưa chạy. Một phương thức xác thực không tồn tại trong hệ thống không phải là test pass; một ca không chạy được vì dependency thiếu cũng không được tính là đã chứng minh yêu cầu.

Số lượng test hoặc tỷ lệ code coverage không tự thể hiện mức bao phủ rủi ro xác thực. Cần đối chiếu với ma trận phương thức, trạng thái, đường truy cập và các quy tắc từ chối quan trọng. Những phát hiện phải dẫn được về contract hoặc một hành vi bảo mật cụ thể.

## 10. Tự kiểm tra cách hiểu

**Đăng nhập bằng mật khẩu đúng thành công có đủ để xác nhận MFA không bị bỏ qua không?**

Không. Cần kiểm tra trạng thái trước khi hoàn tất MFA và gọi trực tiếp tài nguyên yêu cầu mức xác thực đầy đủ.

**Token sai chữ ký và sai audience bị từ chối có chứng minh audience được kiểm tra không?**

Chưa. Token có thể bị từ chối chỉ vì chữ ký. Muốn đánh giá audience, cần fixture thích hợp để các kiểm tra khác không che mất điều kiện mục tiêu.

**Test đặt sẵn principal trong security context có phải test xác thực token không?**

Không. Nó có thể hỗ trợ kiểm tra hành vi sau xác thực, nhưng thường bỏ qua việc xử lý credential và xác minh token thật.

**Mọi access token dùng lại trong request thứ hai đều phải bị chặn để chống replay không?**

Không. Phải dựa vào ngữ nghĩa của loại token và cơ chế đang dùng. Access token thường được dùng trong nhiều request khi còn hiệu lực; authorization code hoặc OTP có quy tắc khác.

**Một authentication test có giá trị cần cho thấy gì?**

Hệ thống thiết lập đúng danh tính khi đủ bằng chứng, giữ đúng các trạng thái trung gian và từ chối các đường vào không đáp ứng contract. Bằng chứng cần quan sát được ở cả response lẫn trạng thái và hành động phía máy chủ, với phạm vi kiểm thử được nêu rõ.
