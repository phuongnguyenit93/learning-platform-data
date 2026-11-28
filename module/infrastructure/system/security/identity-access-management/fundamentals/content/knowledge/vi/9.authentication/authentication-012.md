# User enumeration defense: ngăn dò tìm tài khoản

## 1. Vì sao sự tồn tại của tài khoản cũng cần được bảo vệ?

User enumeration là việc suy ra một định danh có thuộc về tài khoản trong hệ thống hay không thông qua hành vi có thể quan sát. Định danh đó có thể là email, số điện thoại, username hoặc mã nhân viên. Người dò tìm chưa cần biết mật khẩu; chỉ cần phân biệt được hai nhóm “có tài khoản” và “không có tài khoản” là đã thu được thông tin.

Ví dụ, một cổng quản trị trả về hai thông báo:

- Nhập email chưa đăng ký: “Không tìm thấy người dùng”.
- Nhập email đã đăng ký nhưng sai mật khẩu: “Mật khẩu không đúng”.

Hai thông báo biến chức năng đăng nhập thành công cụ tra cứu danh sách người dùng. Danh sách này có thể hỗ trợ password spraying, credential stuffing, phishing nhắm mục tiêu hoặc làm lộ quan hệ giữa một người với dịch vụ nhạy cảm. Trong hệ thống nhiều tenant, sự khác biệt còn có thể tiết lộ người đó thuộc tổ chức nào.

Mục tiêu phòng vệ là hạn chế khả năng phân biệt các trạng thái tài khoản qua giao diện công khai, đồng thời vẫn giúp người dùng hợp lệ hoàn thành đăng nhập và khôi phục quyền truy cập. Đây là bảo vệ thông tin danh tính; nó bổ sung cho mật khẩu mạnh, MFA và kiểm soát truy cập.

Cần phân biệt ba câu hỏi:

| Câu hỏi | Ví dụ | Điều kiện để trả lời |
|---|---|---|
| Định danh có tồn tại không? | Email này đã đăng ký chưa? | Không mặc nhiên được công bố |
| Người yêu cầu đã xác thực chưa? | Người này có chứng minh được quyền dùng tài khoản không? | Kiểm tra bằng chứng xác thực |
| Người đã xác thực được làm gì? | Có được xem danh sách nhân viên không? | Kiểm tra quyền và phạm vi dữ liệu |

Ẩn sự tồn tại của tài khoản không thay thế authorization. Ngược lại, đăng nhập thành công cũng không tự động cho phép tra cứu mọi tài khoản khác.

## 2. Xác định ai đang quan sát và họ quan sát được gì

Trước khi chọn thông báo lỗi, hãy xác định ranh giới thông tin. Với một endpoint đăng nhập công khai, giả định người gọi có thể xem toàn bộ HTTP response, không chỉ phần chữ được hiển thị trên trình duyệt. Họ có thể đo thời gian phản hồi và lặp lại yêu cầu trong giới hạn hệ thống cho phép.

Những tín hiệu thường cần kiểm tra gồm:

| Bề mặt quan sát | Ví dụ làm lộ thông tin | Hướng xử lý |
|---|---|---|
| Thông báo và mã lỗi ứng dụng | `USER_NOT_FOUND` khác `BAD_PASSWORD` | Dùng cùng hợp đồng lỗi công khai |
| HTTP status | Email lạ trả 404, email có thật trả 401 | Nhất quán trong cùng nhóm kết quả |
| URL và redirect | Một nhánh về login, nhánh kia về trang account-disabled | Kiểm tra toàn bộ chuỗi chuyển hướng |
| Header, cookie và cấu trúc body | Chỉ tài khoản thật nhận cookie đánh dấu hoặc trường `userId` | Loại bỏ khác biệt phụ thuộc sự tồn tại |
| Thời gian | Không tìm thấy người dùng thì thoát ngay, có người dùng mới kiểm tra hash | Giảm khác biệt đường xử lý |
| Thử lại và giới hạn | Chỉ tài khoản thật bị giới hạn sau vài lần thử | Áp dụng chính sách cho cả định danh chưa tồn tại |
| Giao diện và kênh phụ | Chỉ email đã đăng ký mới thấy ảnh đại diện hoặc số điện thoại che một phần | Đặt thông tin sau ranh giới xác minh phù hợp |

Ví dụ, hai response đều hiển thị “Đăng nhập thất bại” nhưng body thực tế khác nhau:

```json
{"message":"Đăng nhập thất bại","reason":"NO_SUCH_USER"}
```

```json
{"message":"Đăng nhập thất bại","reason":"PASSWORD_MISMATCH"}
```

Việc frontend bỏ qua `reason` không bảo vệ được dữ liệu. Người gọi API vẫn đọc được trường này.

OWASP khuyến nghị dùng phản hồi xác thực tổng quát và xem xét cả khác biệt về xử lý, HTTP status lẫn URL, vì thông báo giống nhau vẫn có thể để lộ trạng thái tài khoản. Xem [Authentication Cheat Sheet — Authentication Responses](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#authentication-responses).

## 3. Thiết kế hợp đồng phản hồi cho đăng nhập

Một hợp đồng minh họa cho các lần đăng nhập không thành công:

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json
Cache-Control: no-store

{
  "code": "AUTHENTICATION_FAILED",
  "message": "Không thể đăng nhập bằng thông tin đã cung cấp."
}
```

Trong thiết kế này, các trường hợp dưới đây đi về cùng hợp đồng công khai:

- Định danh không tồn tại.
- Định danh tồn tại nhưng mật khẩu không đúng.
- Tài khoản không được phép đăng nhập bằng phương thức này.
- Tài khoản bị vô hiệu hóa hoặc đang chịu hạn chế theo chính sách.

Đây là ví dụ cho endpoint đăng nhập của ứng dụng, không phải quy tắc bắt mọi giao thức hay mọi endpoint đều trả 401. Nếu dùng một giao thức xác thực tiêu chuẩn, cần tuân theo hợp đồng của giao thức và cơ chế xử lý lỗi của thư viện.

Cũng không cần gom lỗi cú pháp đầu vào với lỗi xác thực. JSON hỏng hoặc một trường bắt buộc bị thiếu có thể trả 400 nếu kết quả chỉ phụ thuộc cấu trúc yêu cầu, không phụ thuộc việc tài khoản có tồn tại hay không. Tương tự, lỗi hạ tầng phải được xử lý theo hợp đồng lỗi hệ thống; không biến lỗi database thành xác thực thành công.

Người dùng cần hướng dẫn đủ rõ để tự xử lý:

> Không thể đăng nhập bằng thông tin đã cung cấp. Hãy kiểm tra thông tin hoặc sử dụng chức năng khôi phục tài khoản.

Chức năng hỗ trợ phía sau phải có quy trình xác minh riêng. Nếu nhân viên hỗ trợ trả lời công khai “Email này có trong hệ thống” ngay khi được hỏi, ranh giới bảo vệ của API sẽ bị phá vỡ qua kênh hỗ trợ.

### 3.1. Không làm mất thông tin vận hành bên trong

Ứng dụng vẫn cần phân biệt nguyên nhân thật để điều tra và hỗ trợ người dùng. Điểm cần kiểm soát là ai được đọc dữ liệu đó.

```text
Phản hồi cho người gọi chưa xác thực:
    AUTHENTICATION_FAILED

Sự kiện nội bộ, chỉ người được cấp quyền mới truy cập:
    reason = UNKNOWN_IDENTIFIER
    hoặc PASSWORD_MISMATCH
    hoặc ACCOUNT_DISABLED
```

Không trả nguyên nhân nội bộ qua header debug, GraphQL extensions, nội dung lỗi của mobile API hoặc trang lỗi mặc định của framework. Mã theo dõi yêu cầu có thể được cung cấp nếu nó không mã hóa trạng thái tài khoản và không mở ra chức năng tra cứu sự kiện cho người chưa được phép.

### 3.2. Đặt bước MFA sau bằng chứng thích hợp

Nếu chỉ cần nhập email đã tồn tại là hệ thống hiển thị “Nhập mã MFA gửi đến số ...1234”, giao diện đã tiết lộ thông tin trước khi người gọi chứng minh được quyền dùng tài khoản.

Với đăng nhập bằng mật khẩu rồi MFA, chỉ chuyển sang bước MFA sau khi yếu tố đầu tiên đã được xác minh. Trạng thái trung gian chỉ cấp quyền thực hiện bước tiếp theo, có thời hạn ngắn và không được coi là phiên đăng nhập đầy đủ.

Điều này không có nghĩa mọi phương thức xác thực phải có cùng số màn hình. Passwordless, passkey và các luồng liên kết danh tính có ranh giới riêng. Cần xem ở thời điểm nào người gọi đã có bằng chứng phù hợp để nhận thêm thông tin, thay vì dùng sự tồn tại của email làm bằng chứng.

## 4. Giảm rò rỉ qua thời gian xử lý

Một triển khai dễ gây khác biệt:

```text
account = findAccount(identifier)

if account không tồn tại:
    return authenticationFailed()

if verifyPassword(password, account.hash) thất bại:
    return authenticationFailed()
```

Nhánh không tồn tại chỉ tra cứu database. Nhánh tồn tại thực hiện thêm hàm kiểm tra mật khẩu có chi phí tính toán đáng kể. Thông báo giống nhau nhưng thời gian có thể tạo ra tín hiệu thống kê.

### 4.1. Dùng kiểm tra hash giả khi không có credential phù hợp

Một cách thiết kế là chuẩn bị sẵn một password hash giả hợp lệ theo cấu hình xác minh đang dùng. Khi không có credential mật khẩu phù hợp, vẫn thực hiện một lần kiểm tra với hash giả.

```text
function login(request):
    input = validateBoundedInput(request)
    identifier = normalizeAccordingToIdentityPolicy(input.identifier)

    if admissionControlRejects(request, identifier):
        return publicRateLimitedResponse()

    account = repository.findByIdentifier(identifier)
    credential = passwordCredentialOf(account)

    selectedHash = credential tồn tại
        ? credential.hash
        : precomputedDummyHash

    passwordMatches = passwordVerifier.matches(input.password, selectedHash)

    canContinue =
        account tồn tại
        AND credential tồn tại
        AND passwordMatches
        AND account được phép dùng phương thức này

    if NOT canContinue:
        recordInternalFailureWithoutSecrets(account, identifier)
        return publicAuthenticationFailedResponse()

    return beginNextAuthenticationStep(account)
```

Đây là mã giả mô tả thứ tự xử lý, không phải một thư viện xác thực có thể sao chép vào production. Triển khai thật còn cần quản lý phiên, chống tấn công tự động, cập nhật credential và xử lý lỗi.

Những điều kiện quan trọng:

- Hash giả phải hợp lệ với bộ xác minh, được tạo trước và giữ trong bộ nhớ hoặc cấu hình phù hợp. Không tạo một hash mới cho từng yêu cầu.
- Hash giả không được gắn với tài khoản đăng nhập được. Kết quả kiểm tra hash giả không bao giờ là điều kiện đủ để cho phép truy cập.
- Không thay bộ xác minh mật khẩu bằng so sánh chuỗi tự viết.
- Cần xem xét cấu hình chi phí của hash thật và hash giả. Nếu hệ thống còn nhiều thế hệ hash, một hash giả duy nhất không thể làm mọi nhóm có thời gian giống nhau.
- Không bỏ qua admission control. Việc cố tình thực hiện phép kiểm tra tốn tài nguyên cho cả email lạ có thể khuếch đại từ chối dịch vụ nếu không giới hạn tải.

Điều kiện `account tồn tại` và `credential tồn tại` phải nằm trong quyết định cho phép tiếp tục. Đây là yêu cầu về tính đúng đắn, không chỉ về thời gian.

### 4.2. Không hứa hẹn “constant-time” cho toàn bộ HTTP request

Hàm so sánh an toàn và phản hồi web có thời gian giống nhau là hai phạm vi khác nhau. Một request còn chịu ảnh hưởng của truy vấn dữ liệu, cache, scheduler, kết nối mạng, log, hàng đợi và dịch vụ bên ngoài.

Mục tiêu thực tế là loại bỏ các khác biệt ổn định do trạng thái tài khoản và đo lại hiệu quả trong điều kiện đại diện. Không nên tuyên bố một endpoint hoàn toàn constant-time chỉ vì đã dùng hash giả.

Một số khác biệt thường bị bỏ sót:

- Chỉ tài khoản tồn tại mới truy vấn bảng nhóm hoặc quyền trước khi báo lỗi.
- Chỉ credential thật mới gọi hệ thống quản lý khóa hoặc pepper.
- Tài khoản SSO-only thoát ngay, còn tài khoản local chạy hàm kiểm tra mật khẩu.
- Nhánh tài khoản bị khóa gửi sự kiện đồng bộ đến dịch vụ bên ngoài.
- Cache lưu riêng kết quả “có tài khoản”, tạo hai quần thể thời gian.
- Chỉ một nhánh phải đợi ghi audit log xuống ổ đĩa.

Không cần thêm công việc nghiệp vụ giả cho mọi nhánh một cách máy móc. Hãy loại bỏ công việc không cần thiết khỏi đường phản hồi công khai, giữ kiểm soát bảo mật cần thiết và đo xem phần còn lại có tạo tín hiệu phân biệt hay không.

### 4.3. Vì sao chỉ thêm sleep hoặc jitter chưa đủ?

Một độ trễ ngẫu nhiên có thể làm kết quả nhiễu hơn, nhưng người quan sát có thể lặp lại phép đo. Nếu một nhóm luôn có thêm một công việc tốn thời gian, phân phối của hai nhóm vẫn có thể khác nhau.

Một độ trễ cố định còn có thể không bao phủ trường hợp tải cao và làm tăng số kết nối chờ. Với luồng bất đồng bộ, dùng chờ không đúng chỗ cũng có thể làm cạn worker hoặc thread pool.

Nếu sản phẩm cần một ngưỡng thời gian phản hồi, phải đánh giá nó cùng ngân sách tài nguyên và số request đồng thời. Độ trễ là một thành phần thiết kế có điều kiện; nó không sửa được hợp đồng lỗi khác nhau hay một nhánh thoát quá sớm.

## 5. Bảo vệ toàn bộ vòng đời tài khoản

Chỉ sửa trang đăng nhập là chưa đủ nếu chức năng đăng ký, gửi lại email hoặc khôi phục mật khẩu vẫn cho biết tài khoản tồn tại.

### 5.1. Quên mật khẩu

Một phản hồi công khai phù hợp:

> Nếu thông tin phù hợp với tài khoản đủ điều kiện, hướng dẫn khôi phục sẽ được gửi qua kênh đã đăng ký.

Phản hồi này có thể đi kèm 202 Accepted khi ứng dụng đã chấp nhận yêu cầu vào quy trình xử lý. Việc chấp nhận không khẳng định có tài khoản hoặc đã giao email thành công.

OWASP hướng dẫn giữ thông báo và thời gian phản hồi nhất quán cho yêu cầu khôi phục, áp dụng chống lạm dụng, đồng thời dùng token ngẫu nhiên, có hạn dùng và chỉ dùng một lần. Không khóa hoặc thay đổi tài khoản chỉ vì nhận được yêu cầu đặt lại mật khẩu. Xem [Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#forgot-password-request).

Một kiến trúc minh họa để tách việc gửi thư khỏi đường phản hồi:

```text
Yêu cầu công khai
    |
    v
Kiểm tra định dạng và giới hạn tải
    |
    v
Chấp nhận công việc khôi phục có kích thước giới hạn
    |
    +----> Phản hồi chung cho người gọi
    |
    v
Xử lý nền: tra cứu tài khoản và chính sách khôi phục
    |
    +----> Có tài khoản đủ điều kiện: tạo token và gửi đến kênh đã đăng ký
    |
    +----> Không có hoặc không đủ điều kiện: kết thúc công việc
```

Trong cách này, công việc nền nhận yêu cầu đã được kiểm soát cho cả hai nhóm. Nếu API chỉ enqueue khi email tồn tại, bản thân việc enqueue và lỗi của nó có thể lại tạo khác biệt.

Hàng đợi không tự giải quyết mọi vấn đề. Cần giới hạn dung lượng, thời gian lưu, quyền đọc dữ liệu và chi phí xử lý. Nếu hàng đợi không nhận được công việc, không khẳng định rằng công việc đã được chấp nhận. Hợp đồng lỗi hạ tầng cũng phải được xem xét để tránh phụ thuộc vào kết quả tra cứu tài khoản.

Ngoài ra:

- Gửi hướng dẫn đến địa chỉ đã đăng ký và đã được xác minh theo chính sách, không gửi đến một địa chỉ đích tùy ý do request cung cấp.
- Không trả đường dẫn reset, token hoặc thông tin định tuyến gửi thư về client công khai.
- Tránh trả `deliveryStatus` hay một endpoint polling cho biết “đã tìm thấy người nhận”.
- Giới hạn số email gửi đến cùng một người để tránh biến endpoint thành công cụ quấy rối.
- Dữ liệu nhạy cảm trong job nền cũng cần được bảo vệ và có thời hạn lưu phù hợp.

Thông điệp ngoài băng có thể cho chủ hộp thư biết về tài khoản của chính họ. Đây là sự tiết lộ có chủ đích tới người chứng minh được quyền kiểm soát kênh, không đồng nghĩa người gửi request công khai được quyền nhận thông tin đó.

### 5.2. Đăng ký

Một endpoint công khai trả “Email đã được sử dụng” có thể là nguồn enumeration dù login đã được bảo vệ.

Với sản phẩm coi việc tham gia dịch vụ là thông tin riêng tư, có thể dùng một luồng:

1. Nhận email và trả phản hồi chung.
2. Gửi hướng dẫn phù hợp đến hộp thư theo chính sách chống lạm dụng.
3. Xác minh quyền kiểm soát hộp thư.
4. Chỉ sau đó cho phép tiếp tục tạo mới hoặc hướng dẫn truy cập tài khoản hiện có.

Đây là lựa chọn thiết kế sản phẩm, không phải cách làm bắt buộc cho mọi website. Một diễn đàn có username và hồ sơ công khai có thể cho phép kiểm tra tên hiển thị đã dùng. Khi đó phải ghi nhận rằng tên công khai là dữ liệu được phép tra cứu, nhưng không suy ra email đăng nhập cũng được phép công bố.

Không biến chống enumeration thành lỗi chiếm đoạt tài khoản: nếu email đã thuộc một tài khoản, yêu cầu đăng ký mới không được ghi đè mật khẩu, gắn thêm phương thức đăng nhập hoặc liên kết danh tính với tài khoản đó.

### 5.3. Gửi lại email xác minh, magic link và OTP

Các endpoint này cần được đánh giá cùng nhau. Những phản hồi như “Người dùng này chưa đăng ký”, “Email đã xác minh” hoặc “Tài khoản không hỗ trợ OTP” có thể phân loại tài khoản cho người chưa xác thực.

Trước khi đã có bằng chứng thích hợp, dùng một phản hồi chung và hạn chế tiết lộ số điện thoại, địa chỉ email hoặc phương thức MFA đang gắn với tài khoản.

Với magic link hoặc OTP dùng để đăng nhập, việc gửi mã và việc xác minh mã là hai giai đoạn khác nhau. Chấp nhận yêu cầu gửi mã không tạo phiên đăng nhập. Chỉ sau khi mã hoặc liên kết hợp lệ được xác minh mới được chuyển sang trạng thái xác thực tương ứng.

### 5.4. Luồng SSO và tenant discovery

Màn hình nhập email rồi tự chọn Identity Provider có thể làm lộ việc một địa chỉ thuộc tenant nào hoặc đang có tài khoản local hay SSO. Cần phân biệt:

- Định tuyến dựa trên domain doanh nghiệp được công khai theo chính sách.
- Định tuyến dựa trên bản ghi thành viên cụ thể chưa được phép công bố.

Nếu phải hỗ trợ discovery công khai, hãy xác định chính xác thông tin nào được công bố và giới hạn phản hồi ở mức đó. Không kèm danh sách tenant, user ID nội bộ, vai trò hoặc trạng thái MFA chỉ để giúp frontend chọn màn hình.

Với tài khoản tham gia nhiều tổ chức, việc liệt kê tổ chức thường nên nằm sau bước xác minh thích hợp. Các quyết định này phải nhất quán với quy trình mời thành viên và quyền xem danh bạ của từng tenant.

## 6. Định danh nhất quán và chống lạm dụng

### 6.1. Chuẩn hóa theo chính sách định danh

Cùng một định danh có thể được biểu diễn nhiều cách. Nếu đăng nhập chuẩn hóa khác khôi phục mật khẩu hoặc rate limiter, hệ thống có thể xử lý một người thành nhiều khóa khác nhau.

Cần xác định quy tắc tại một nơi và dùng nhất quán cho:

- Đăng ký, đăng nhập và tra cứu credential.
- Khôi phục, gửi lại email xác minh và thay đổi định danh.
- Tính khóa giới hạn yêu cầu và ghi nhận sự kiện an ninh.

Không tự ý áp dụng mọi quy tắc vào mọi loại định danh. Ví dụ, không mặc định xóa dấu chấm, phần sau dấu cộng hoặc đổi toàn bộ email sang chữ thường nếu chính sách định danh chưa cho phép. Quy tắc riêng của một nhà cung cấp email không phải quy tắc chung cho tất cả địa chỉ.

Tương tự, nếu username phân biệt chữ hoa và chữ thường theo thiết kế, rate limiter phải xử lý phù hợp với quyết định đó. Chuẩn hóa sai có thể vừa làm vượt giới hạn, vừa gây nhập nhằng danh tính.

### 6.2. Giới hạn yêu cầu theo nhiều chiều

Một khóa chỉ theo IP có thể ảnh hưởng nhiều người sau cùng NAT và bỏ sót các nguồn phân tán. Một khóa chỉ theo tài khoản có thể khiến kẻ khác làm nghẽn riêng tài khoản của nạn nhân.

Thiết kế thường cần kết hợp các chiều: nguồn gửi, định danh được nhập, tenant, endpoint, rủi ro và tổng công suất của hệ thống. Mỗi chiều có mục đích riêng:

| Chiều giới hạn | Mục đích | Điểm cần cân nhắc |
|---|---|---|
| Nguồn gửi hoặc nhóm kết nối | Giảm lưu lượng từ một nguồn | NAT, proxy và nguồn phân tán |
| Định danh được nhập | Giảm số lần nhắm vào cùng một người | Tránh khóa cứng gây mất khả dụng |
| Tenant hoặc tổ chức | Bảo vệ ngân sách từng tổ chức | Không để tổ chức lớn bị nghẽn vô lý |
| Toàn dịch vụ | Giữ tài nguyên xác thực trong khả năng phục vụ | Cần ưu tiên và cơ chế suy giảm phù hợp |
| Kênh gửi email hoặc SMS | Hạn chế quấy rối và chi phí | Bộ đếm gửi thực tế nên tách khỏi phản hồi công khai |

Chính sách dựa trên định danh cần áp dụng được cả khi chưa tìm thấy user ID. Nếu chỉ tạo bộ đếm sau khi tra cứu ra tài khoản, trạng thái giới hạn có thể thành một phép thử tồn tại.

Có thể dùng một khóa nội bộ được dẫn xuất bằng HMAC từ tenant và định danh đã chuẩn hóa, với khóa bí mật được bảo vệ. Cách này giúp tránh để email thô xuất hiện trong tên khóa của kho rate limit. Tuy vậy, HMAC vẫn là dữ liệu có khả năng liên kết; không được mặc nhiên xem là dữ liệu ẩn danh hay đưa ra metric label không giới hạn.

Số lượng định danh chưa tồn tại do người gọi cung cấp có thể rất lớn. Kho bộ đếm cần thời hạn sống, giới hạn dung lượng và chiến lược quản lý tải. Không để chống enumeration tạo một nơi lưu dữ liệu vô hạn.

### 6.3. Thông báo giới hạn và khóa tài khoản

Nếu cùng lịch sử thử nhưng chỉ tài khoản thật trả `ACCOUNT_LOCKED`, thông báo khóa trở thành tín hiệu enumeration.

Phân biệt giới hạn nhận yêu cầu, trì hoãn phản hồi và trạng thái khóa tài khoản bên trong. Một response 429 công khai có thể hợp lệ nếu quyết định và hình thức phản hồi không phụ thuộc việc định danh có tồn tại trong điều kiện đang so sánh.

Tránh tự động khóa lâu dài chỉ vì có người lạ gửi nhiều request tới một email. Cần cân bằng chống dò mật khẩu với khả năng người dùng thật bị từ chối dịch vụ. Việc mở khóa và hỗ trợ tài khoản phải có bằng chứng xác minh tương ứng.

CAPTCHA hoặc thử thách chống bot có thể là một lớp giảm tự động hóa, nhưng chính điều kiện xuất hiện thử thách cũng cần được kiểm tra. Nếu CAPTCHA chỉ xuất hiện với tài khoản tồn tại, nó có thể tiết lộ trạng thái mà thông báo lỗi đã cố che giấu.

## 7. Log, metric và hỗ trợ người dùng

Dữ liệu vận hành nên giúp phân biệt lỗi hệ thống với hoạt động đáng ngờ, đồng thời hạn chế thông tin nhạy cảm.

Một sự kiện minh họa:

```json
{
  "event": "authentication_failure",
  "requestId": "example-request-id",
  "identifierKey": "opaque-internal-key",
  "internalReason": "PASSWORD_MISMATCH",
  "publicOutcome": "AUTHENTICATION_FAILED"
}
```

`identifierKey` chỉ là tên minh họa cho khóa nội bộ đã được bảo vệ. Nó không phải token đăng nhập và không nên xuất hiện trong response.

Không ghi mật khẩu, OTP, token reset, toàn bộ cookie phiên hoặc nội dung magic link vào log. Nếu cần lưu email để hỗ trợ nghiệp vụ, phải có mục đích, phân quyền, thời hạn lưu và cơ chế che dữ liệu phù hợp. Việc dùng một giá trị hash hay HMAC không tự động miễn các yêu cầu này.

Những dấu hiệu cần quan sát:

- Nhiều định danh khác nhau được thử từ cùng nguồn hoặc cùng nhóm hành vi.
- Nhiều yêu cầu khôi phục nhưng rất ít lần hoàn thành.
- Tăng đột biến ở tài khoản không tồn tại so với mức nền.
- Thay đổi phân phối độ trễ sau một bản triển khai.
- Lượng gửi email, SMS hoặc chi phí kiểm tra hash tiến gần công suất cho phép.

Không dùng email, số điện thoại hoặc khóa định danh có số lượng lớn làm nhãn metric. Dùng số liệu tổng hợp cho dashboard; khi cần điều tra chi tiết, truy cập sự kiện theo quyền đã cấp.

Quy trình hỗ trợ cũng cần phân tầng. Nhân viên có thể giải thích cách đăng nhập và khôi phục trước khi xác minh. Những thông tin như tài khoản có tồn tại, đang bị khóa vì lý do gì hoặc gắn với tổ chức nào chỉ được cung cấp theo chính sách tiết lộ và bằng chứng phù hợp.

## 8. Kiểm chứng bằng các tình huống đại diện

Việc kiểm chứng cần được thực hiện trên môi trường và tập tài khoản được cho phép. Dùng tài khoản kiểm thử do nhóm quản lý, định danh giả và giới hạn tải rõ ràng; không cần thử danh sách người dùng thật để đánh giá thiết kế.

### 8.1. Ma trận kiểm tra chức năng

| Trường hợp | Kết quả công khai cần xem xét | Hành vi nội bộ cần xác nhận |
|---|---|---|
| Email không tồn tại, đầu vào hợp lệ | Cùng hợp đồng đăng nhập thất bại | Không tạo phiên hoặc tài khoản |
| Tài khoản local, sai mật khẩu | Cùng hợp đồng đăng nhập thất bại | Xác minh credential đúng cách |
| Tài khoản bị vô hiệu hóa | Không công bố trạng thái qua lỗi công khai | Không cho phép đăng nhập |
| Tài khoản chỉ dùng SSO tại endpoint mật khẩu | Không lộ phân loại credential ngoài chính sách | Không tạo đường đăng nhập local |
| Tài khoản có MFA, sai mật khẩu | Không hiển thị thông tin MFA | Không tạo trạng thái hoàn thành MFA |
| Yêu cầu khôi phục tới email tồn tại và không tồn tại | Cùng hợp đồng chấp nhận phù hợp | Chỉ gửi tới kênh đủ điều kiện |
| Vượt giới hạn với cùng lịch sử yêu cầu | Kiểm tra thông báo, header và thử thách | Bộ đếm áp dụng cho cả định danh chưa tồn tại |
| Mật khẩu đúng và các yếu tố cần thiết đã hợp lệ | Chuyển trạng thái đúng thiết kế | Không làm hỏng đăng nhập hợp lệ |

Bài kiểm tra không nên yêu cầu đăng nhập thành công phải giống đăng nhập thất bại. Mục tiêu là người chưa đưa được bằng chứng hợp lệ không suy ra sự tồn tại từ các nhánh thất bại đang so sánh.

Kiểm tra cả API trực tiếp lẫn web và mobile. Không chỉ chụp màn hình: hãy xem status, body, header, cookie, redirect và các request phụ do frontend tạo ra.

### 8.2. Đánh giá thời gian

Một lần đo không đủ để kết luận. Lập hai hoặc nhiều nhóm kiểm thử có đầu vào tương đương: cùng độ dài hợp lý, cùng loại request, cùng trạng thái giới hạn và cùng môi trường.

Quy trình minh họa:

1. Dùng các tài khoản kiểm thử và định danh không tồn tại đã được xác định.
2. Làm nóng kết nối và hệ thống trong điều kiện có kiểm soát.
3. Xen kẽ thứ tự gửi giữa các nhóm để giảm ảnh hưởng theo thời gian.
4. Thu thập phân phối độ trễ, không chỉ lấy một giá trị trung bình.
5. Xem xét median, các phân vị và mức chồng lấp của các nhóm.
6. Đối chiếu trace nội bộ để tìm bước xử lý tạo khác biệt.
7. Đo lại sau khi sửa và dưới tải đại diện trong phạm vi được phép.

Các giá trị đo chỉ có ý nghĩa trong bối cảnh của môi trường. Không có một ngưỡng mili giây cố định bảo đảm an toàn cho mọi dịch vụ. Việc chưa phát hiện khác biệt trong một đợt đo cũng không chứng minh không còn mọi kênh rò rỉ.

Đồng thời kiểm tra chi phí của giải pháp: CPU hoặc bộ nhớ dùng cho password verification, thời gian chờ, dung lượng hàng đợi và tác động lên người dùng hợp lệ.

## 9. Tình huống áp dụng: cổng quản trị nội bộ

Một cổng quản trị cho phép đăng nhập bằng email và mật khẩu. Nhóm phát triển đã dùng thông báo “Không thể đăng nhập”, nhưng còn ba vấn đề:

- Email không tồn tại trả về trước khi kiểm tra hash.
- Endpoint quên mật khẩu trả `EMAIL_NOT_FOUND`.
- Chỉ tài khoản thật nhận CAPTCHA sau nhiều lần thử.

Đánh giá riêng màn hình login có thể bỏ sót hai vấn đề sau. Cách xử lý cần bám toàn bộ chuỗi:

1. Xác định rằng danh sách người có quyền vào cổng quản trị không được công bố.
2. Chuẩn hóa hợp đồng lỗi đăng nhập và bỏ nguyên nhân nội bộ khỏi response.
3. Thực hiện kiểm tra credential thật hoặc hash giả sau admission control.
4. Tách xử lý khôi phục ra nền với phản hồi chung và kiểm soát gửi thư.
5. Thiết kế điều kiện giới hạn, thử thách cho cả định danh chưa tồn tại.
6. Kiểm chứng bằng nhóm tài khoản do nhóm quản lý, gồm disabled và SSO-only.
7. Theo dõi hiệu năng và số lần người dùng thật bị ảnh hưởng sau triển khai.

Nếu chính sách cho phép công khai domain SSO của tổ chức, đội phát triển có thể giữ thông tin domain đó. Quyết định này không kéo theo quyền công bố từng thành viên hay vai trò quản trị của họ.

Kết quả cần đạt có hai mặt: các lần thất bại không để lộ thông tin vượt chính sách, còn người có bằng chứng hợp lệ vẫn đăng nhập hoặc khôi phục được theo quy trình.

## 10. Những lỗi thiết kế thường gặp

| Cách làm | Vì sao chưa đủ | Điều cần bổ sung |
|---|---|---|
| Chỉ đổi câu thông báo trên giao diện | API còn mã lỗi, header hoặc redirect khác | Kiểm tra toàn bộ hợp đồng HTTP |
| Chỉ dùng hash giả | Registration hoặc recovery vẫn công bố tài khoản | Đánh giá toàn bộ vòng đời |
| Chỉ thêm một khoảng chờ | Khác biệt đường xử lý vẫn còn và có thể gây nghẽn | Sửa nhánh xử lý, đo lại và giới hạn tải |
| Chỉ giới hạn theo IP | Khó phân biệt NAT với nguồn phân tán | Kết hợp nhiều chiều phù hợp |
| Khóa cứng tài khoản khi bị thử nhiều | Người lạ có thể làm gián đoạn tài khoản nạn nhân | Kiểm soát rủi ro và phục hồi khả dụng |
| Trả thông tin MFA ngay sau email | Chưa có bằng chứng quyền dùng tài khoản | Đặt thông tin sau bước xác minh phù hợp |
| Công bố nguyên nhân qua endpoint debug | Tạo lại kênh dò tìm bên cạnh endpoint chính | Phân quyền dữ liệu vận hành |
| Coi email hash là dữ liệu vô danh | Có thể bị liên kết hoặc dò theo tập ứng viên | Bảo vệ khóa, quyền truy cập và thời hạn lưu |

## 11. Câu hỏi tự kiểm tra

1. Vì sao hai thông báo giống nhau nhưng HTTP status khác nhau vẫn có thể để lộ sự tồn tại của tài khoản?
2. Hash giả giải quyết khác biệt nào trong luồng kiểm tra mật khẩu? Nó không bảo đảm được những điều gì?
3. Tại sao admission control phải được tính đến trước khi tăng chi phí kiểm tra cho định danh không tồn tại?
4. Một endpoint quên mật khẩu trả 202 nhưng chỉ enqueue khi tìm thấy user có thể còn kênh rò rỉ nào?
5. Vì sao bộ đếm chỉ theo user ID không đủ để kiểm soát các định danh chưa tồn tại?
6. Khi nào công khai việc username đã được sử dụng có thể là quyết định hợp lệ của sản phẩm?
7. Trong một ứng dụng nhiều tenant, cần phân biệt công bố domain SSO với công bố danh sách thành viên như thế nào?
8. Làm thế nào giữ đủ nguyên nhân nội bộ để hỗ trợ vận hành mà không trả chúng cho người chưa được phép?

Một thiết kế tốt xác định rõ thông tin danh tính được phép tiết lộ ở từng bước, giữ phản hồi công khai nhất quán trong ranh giới đó, hạn chế khả năng tự động hóa và kiểm chứng cả hành vi lẫn chi phí vận hành.
