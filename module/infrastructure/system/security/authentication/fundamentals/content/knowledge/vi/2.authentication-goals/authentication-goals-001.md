# Xác nhận danh tính

> **Chương:** Mục tiêu xác thực  
> **Chủ đề:** Xác nhận danh tính  
> **Phạm vi:** Nguyên lý xác thực trong hệ thống phần mềm, từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản.

## 1. Xác nhận danh tính nhằm trả lời câu hỏi nào?

Trong một ứng dụng, người dùng có thể tuyên bố: “Tôi là chủ tài khoản an@example.com”. **Xác thực (authentication)** là quá trình hệ thống thu thập và kiểm tra bằng chứng để quyết định có nên tin tuyên bố đó ở mức phù hợp với rủi ro hay không. Đầu ra thường là một **chủ thể đã xác thực** (authenticated principal), ví dụ mã tài khoản nội bộ bất biến, cùng thời điểm, phương thức và mức độ tin cậy của lần xác thực.

Điều quan trọng: đăng nhập thành công **không tự động chứng minh danh tính pháp lý** của người dùng, cũng không đảm bảo người cầm thiết bị hiện tại là chính người đã tạo tài khoản. Thông thường hệ thống chỉ xác minh rằng bên đang tương tác **kiểm soát một hoặc nhiều credential** được liên kết với tài khoản. Muốn khẳng định một người ngoài đời là ai còn cần bước **kiểm chứng danh tính ban đầu** (identity proofing), ví dụ đối chiếu hồ sơ hợp lệ theo quy trình riêng.

Ba câu hỏi liên quan nhưng khác nhau:

| Câu hỏi | Hoạt động | Ví dụ |
| --- | --- | --- |
| “Người/tác nhân này tuyên bố mình là ai?” | **Nhận diện (identification)** | Nhập tên tài khoản, chọn tài khoản, hoặc nhà cung cấp danh tính trả về mã chủ thể. |
| “Bằng chứng có đủ để chấp nhận tuyên bố đó không?” | **Xác thực (authentication)** | Kiểm tra mật khẩu, chữ ký passkey, OTP hoặc chứng chỉ đã được ràng buộc với chủ thể. |
| “Chủ thể đã xác thực được làm gì?” | **Phân quyền (authorization)** | Tài khoản A được xem hóa đơn của A nhưng không được xem hóa đơn của B. |

**Ví dụ:** Một nhân viên đăng nhập thành công bằng passkey. Ứng dụng biết phiên này gắn với tài khoản nhân viên số 1742, nhưng vẫn phải kiểm tra quyền trước khi cho phép duyệt chi. Việc đổi vai trò hay truy cập dữ liệu nhạy cảm có thể cần **xác thực lại** ngay cả khi phiên trước đó chưa hết hạn.

### Kết quả học tập

Sau bài này, người học có thể:

1. Phân biệt danh tính được khai báo, bằng chứng xác thực, chủ thể đã xác thực và quyền truy cập.
2. Giải thích chính xác một loại credential chứng minh điều gì và **không** chứng minh điều gì.
3. Vẽ được ranh giới tin cậy trong luồng đăng nhập nội bộ hoặc qua nhà cung cấp danh tính.
4. Nhận ra rủi ro phishing, phát lại thông điệp (replay), chiếm phiên và lạm dụng đăng nhập.
5. Mô tả cách gắn kết quả xác thực với tài khoản, token, phiên và luồng khôi phục an toàn.

## 2. Những khái niệm cần tách bạch

- **Danh tính (identity):** tập thuộc tính và định danh dùng để biểu diễn một thực thể trong phạm vi hệ thống. Một người có thể có nhiều danh tính/tài khoản ở các tổ chức khác nhau.
- **Chủ thể (subject/principal):** thực thể mà hệ thống gán kết quả xác thực, thường định danh bằng ID ổn định. Chủ thể cũng có thể là dịch vụ, thiết bị hoặc workload, không chỉ là con người.
- **Credential:** bí mật hoặc vật liệu mật mã được đăng ký/liên kết với chủ thể, chẳng hạn bộ xác minh mật khẩu, khóa công khai của passkey, khóa bảo mật, hoặc chứng chỉ kèm quan hệ tin cậy. Credential và tên đăng nhập không phải một.
- **Authenticator:** phương tiện người dùng kiểm soát để tạo bằng chứng, như ứng dụng tạo mã OTP, khóa phần cứng hay passkey trên thiết bị.
- **Bằng chứng xác thực:** thông tin được kiểm tra trong **một lần** xác thực, chẳng hạn mật khẩu được nhập, chữ ký của thử thách ngẫu nhiên hoặc mã OTP còn hiệu lực. Không nên coi mã gửi lại nhiều lần là bằng chứng mới.
- **Bên xác minh (verifier):** thành phần có khả năng kiểm tra bằng chứng theo chính sách.
- **Bên sử dụng kết quả xác thực (relying party – RP):** ứng dụng dựa vào kết quả xác thực để tạo phiên hoặc cho phép tiếp tục một tác vụ.
- **Phiên (session):** trạng thái duy trì việc đã xác thực qua nhiều yêu cầu. Cookie phiên hay access token là phương tiện chuyển tải quyền truy cập theo các điều kiện riêng, không phải lúc nào cũng là bằng chứng người dùng vừa xác thực.

Một chuỗi hợp lệ là:

~~~text
Danh tính được khai báo
        |
        v
Credential đã đăng ký với chủ thể --(kiểm tra bằng chứng)--> Kết quả xác thực
                                                            |
                                                            v
                                                  Chủ thể / mức bảo đảm
                                                            |
                                                            v
                                                      Phiên đăng nhập
                                                            |
                                                            v
                                           Phân quyền cho từng thao tác
~~~

**Nguyên tắc thiết kế:** sử dụng ID tài khoản nội bộ ổn định làm khóa nghiệp vụ; dùng email/số điện thoại như thuộc tính có thể thay đổi. Đừng biến việc sở hữu email thành quyền tự động lấy một tài khoản vốn được tạo bằng phương thức khác.

## 3. Bằng chứng xác thực có giới hạn

Khi lựa chọn một phương thức, cần ghi rõ nó xác minh **quyền kiểm soát nào**, mối liên kết với tài khoản được tạo ở đâu và những rủi ro còn lại.

| Phương thức | Điều bên xác minh thực sự kiểm tra | Hạn chế đáng lưu ý |
| --- | --- | --- |
| Mật khẩu | Bên đăng nhập biết bí mật khớp với bộ xác minh đã lưu cho tài khoản. | Có thể bị lộ, đoán, tái sử dụng, bị lừa nhập trên trang giả. |
| Email đăng nhập một lần / liên kết xác nhận | Bên đăng nhập truy cập được thư hoặc liên kết còn hiệu lực trong hộp thư đã ràng buộc. | Hộp thư bị chiếm hoặc liên kết bị chuyển tiếp thì tài khoản có thể bị chiếm. |
| SMS OTP | Bên đăng nhập nhận được mã tại số điện thoại đã đăng ký. | Rủi ro SIM swap, chuyển hướng, lừa nhập mã và khả năng truy cập số không đồng nghĩa nhận diện cá nhân. |
| TOTP | Bên đăng nhập có bí mật chia sẻ để sinh mã theo thời gian. | Mã vẫn có thể bị phishing, phát lại trong thời gian còn hiệu lực nếu không kiểm soát sử dụng. |
| Push MFA | Bên đăng nhập chấp thuận một yêu cầu trên thiết bị đã đăng ký. | Có thể bị “MFA fatigue”, chấp thuận nhầm; cần hiển thị ngữ cảnh và ràng buộc giao dịch. |
| Passkey / WebAuthn | Authenticator kiểm soát khóa riêng và ký thử thách cho đúng RP ID/origin. | Phải xác minh challenge, origin, RP ID, chữ ký và cờ phù hợp; thiết bị/khôi phục tài khoản vẫn là rủi ro. |
| Chứng chỉ và mTLS | Bên kết nối kiểm soát khóa riêng tương ứng với chứng chỉ được hệ thống tin cậy. | Chỉ đáng tin khi xác minh chuỗi, mục đích, định danh phù hợp và chính sách thu hồi; không tự chứng minh người vận hành. |
| Nhà cung cấp danh tính (OIDC) | Ứng dụng kiểm tra thông điệp danh tính do nhà cung cấp được tin cậy phát hành cho đúng ứng dụng. | Phải xác minh chữ ký, nhà phát hành, đối tượng nhận, thời gian, nonce khi áp dụng và liên kết chủ thể đúng cách. |

**Nhiều yếu tố (MFA)** đòi hỏi bằng chứng thuộc các loại độc lập như **điều biết** (mật khẩu/PIN), **điều có** (authenticator/khóa), **đặc điểm sinh trắc** (vân tay/khuôn mặt). Hai mật khẩu hoặc mật khẩu cộng câu hỏi bí mật vẫn chỉ là cùng loại yếu tố. Sinh trắc trên thiết bị thường dùng để mở khóa authenticator; ứng dụng từ xa nhận bằng chứng mật mã, không nhất thiết nhận hay lưu dữ liệu sinh trắc. Mức bảo đảm phụ thuộc cách triển khai và đăng ký, không chỉ tên phương thức.

**Chống phishing:** OTP thông thường có thể bị trang giả thu thập và chuyển tiếp ngay lập tức; WebAuthn/passkey ràng buộc chữ ký với RP ID/origin nên cung cấp đặc tính chống phishing mạnh hơn khi triển khai đúng. Tuy vậy, nếu luồng khôi phục tài khoản quá yếu thì kẻ tấn công vẫn có thể vòng qua phương thức mạnh.

## 4. Ranh giới tin cậy: ai được tin điều gì?

Trình duyệt, ứng dụng di động, mạng và mọi trường do client gửi đều có thể bị giả mạo. Máy chủ chỉ chấp nhận danh tính sau khi kiểm tra bằng chứng hoặc xác minh một thông điệp được phát hành bởi **bên mà hệ thống đã thiết lập quan hệ tin cậy**. Không được xem một nhãn “đã đăng nhập” trong local storage, header tự gửi hoặc email từ request body là kết luận xác thực.

~~~mermaid
flowchart LR
    U["Người dùng / authenticator"] --> B["Trình duyệt hoặc ứng dụng"]
    B -- "Yêu cầu + bằng chứng" --> V["Bên xác minh tin cậy"]
    V -- "Kết quả đã kiểm tra" --> S["Dịch vụ tạo phiên"]
    S -- "Session ID / token" --> B
    B -- "Yêu cầu nghiệp vụ" --> A["API tài nguyên"]
    A -- "Kiểm tra phiên + quyền" --> D[("Dữ liệu")]
~~~

Trong mô hình này có ít nhất bốn ranh giới cần xác định:

1. **Từ người dùng/thiết bị sang client:** kẻ tấn công có thể sở hữu thiết bị, mở khóa authenticator hoặc đánh lừa người dùng. UI không phải nguồn xác thực đáng tin.
2. **Từ client qua mạng sang verifier:** yêu cầu cần TLS; phải kiểm tra dữ liệu đầu vào, hạn chế thử đăng nhập và chống dùng lại bằng chứng theo loại giao thức.
3. **Từ verifier sang ứng dụng:** chỉ kết quả đã ký/được bảo vệ bằng cơ chế tin cậy hoặc qua kênh nội bộ an toàn mới được chuyển thành principal. Cấm tin header “X-User-Id” do Internet gửi trực tiếp.
4. **Từ phiên sang từng API:** API phải xác thực cookie/token, kiểm tra hiệu lực và quyết định quyền theo tài nguyên, ngay cả khi gateway đã kiểm tra đăng nhập.

Khi dùng đăng nhập liên kết (federated login), nhà cung cấp danh tính (Identity Provider – IdP) xác thực người dùng và trả về thông điệp theo giao thức; ứng dụng RP vẫn chịu trách nhiệm **kiểm tra thông điệp, ánh xạ tài khoản và quản lý phiên của mình**.

## 5. Một luồng xác thực danh tính hoàn chỉnh

Xét một dịch vụ quản lý hồ sơ có tài khoản nội bộ ID 1742. Chính sách cho phép đăng nhập bằng mật khẩu kèm yếu tố thứ hai hoặc bằng passkey đã đăng ký.

1. **Bắt đầu đúng tài khoản và đúng ngữ cảnh.** Người dùng nhập định danh hoặc chọn passkey. Server xử lý đầu vào như dữ liệu không tin cậy; nếu tài khoản không tồn tại, phản hồi không tiết lộ thông tin không cần thiết.
2. **Tạo thử thách hoặc yêu cầu bằng chứng.** Với passkey, server sinh challenge ngẫu nhiên, đủ mạnh và ngắn hạn, gắn với một phiên giao dịch; với mật khẩu, server tiếp nhận qua TLS và đối chiếu với bộ xác minh mật khẩu. Không lưu mật khẩu thuần hay đưa bí mật vào log.
3. **Kiểm tra bằng chứng trên phía tin cậy.** Với mật khẩu, dùng thuật toán băm mật khẩu có salt và chi phí thích hợp, ví dụ Argon2id, theo cấu hình hiện hành. Với WebAuthn, kiểm tra chữ ký, challenge, origin, RP ID, user presence và user verification theo chính sách; xác nhận credential ID thuộc đúng chủ thể.
4. **Áp dụng chính sách rủi ro.** Kiểm tra trạng thái tài khoản, chống thử sai hàng loạt, yêu cầu MFA hoặc xác thực bổ sung khi thao tác nhạy cảm, cân nhắc thiết bị/ngữ cảnh đăng nhập. Không dùng tín hiệu rủi ro yếu thay cho xác thực.
5. **Tạo principal rõ ràng.** Sau khi các kiểm tra cần thiết thành công, ghi nhận ID 1742, cách xác thực, thời gian và thông tin bảo đảm cần thiết; tránh suy principal trực tiếp từ trường email do client khai báo.
6. **Tạo phiên an toàn.** Sinh session ID khó đoán, làm mới ID khi chuyển từ trạng thái chưa xác thực sang đã xác thực để tránh session fixation; gắn phiên với chủ thể và quyền/chính sách phù hợp. Nếu dùng cookie, cấu hình Secure, HttpOnly và SameSite theo mô hình ứng dụng.
7. **Duy trì, giám sát và kết thúc.** Mỗi request cần được kiểm tra phiên và phân quyền. Có thời hạn hết hiệu lực, cơ chế thu hồi phù hợp, đăng xuất và phương thức hủy phiên sau sự kiện bất thường.

~~~text
POST /login
  identifier = "an@example.com"
  evidence   = <bằng chứng từ phương thức đã đăng ký>

Server:
  account = find_account_by_identifier(identifier)
  enforce_login_abuse_controls(account, request_context)
  result  = verify_registered_credential(account, evidence)
  if result is not acceptable:
      return generic_authentication_failure
  principal = { account_id: 1742, method: result.method, auth_time: now }
  session   = create_fresh_session(principal)
  return secure_session_cookie(session)

GET /records/982
  principal = require_valid_session(request)
  require_permission(principal, "read", record_982)
  return record_982
~~~

Đây là **giả mã minh họa trách nhiệm**; các lệnh kiểm tra credential và tạo session cần dùng thư viện/giao thức đã được kiểm chứng. Đặc biệt, không tự viết thuật toán mật mã chỉ từ ví dụ.

### Vì sao đăng nhập thành công chưa đủ?

Giả sử API nhận yêu cầu “GET /records/982” từ tài khoản 1742. API vẫn phải kiểm tra hồ sơ 982 có thuộc người đó hay người đó có quyền truy cập không. Nếu bỏ qua bước này thì hệ thống mắc lỗi kiểm soát truy cập, dù xác thực mật khẩu và MFA hoàn toàn đúng.

## 6. Token, phiên và xác nhận danh tính liên quan thế nào?

Một lần xác thực không thể yêu cầu nhập lại credential cho mọi lần bấm chuột. Hệ thống vì vậy cấp **phiên** hoặc token có điều kiện sử dụng. Đây là bước **duy trì kết quả xác thực**, có rủi ro riêng vì kẻ trộm token/cookie có thể mạo danh phiên mà không cần biết mật khẩu.

| Vật mang | Mục đích chính | Cần kiểm tra và bảo vệ |
| --- | --- | --- |
| Cookie session chứa ID ngẫu nhiên | Tra cứu phiên đã xác thực ở server. | Secure, HttpOnly, SameSite phù hợp, chống CSRF khi cần, thời hạn, thu hồi, đổi ID sau đăng nhập. |
| Access token | Cho API biết bên gọi được phép làm gì trong phạm vi và thời gian xác định. | Chữ ký hoặc introspection, issuer, audience, expiry, scope/quyền và ràng buộc với loại token; bảo vệ khi truyền/lưu. |
| ID token trong OpenID Connect | Truyền thông tin sự kiện xác thực/chủ thể từ IdP cho ứng dụng khách. | Xác minh issuer, audience, chữ ký, thời gian, nonce theo luồng; **không dùng ID token thay access token để gọi API**. |
| Refresh token | Xin access token mới mà không bắt người dùng đăng nhập lại ngay. | Lưu an toàn, xoay vòng hoặc sender-constrain theo thiết kế, phát hiện tái sử dụng và có khả năng thu hồi. |

**Quy tắc:** token có chữ ký hợp lệ vẫn có thể **không dùng được ở đây** nếu sai audience, sai issuer, hết hạn, bị thu hồi hoặc thiếu quyền. Trường “sub” trong token có ý nghĩa trong phạm vi nhà phát hành; không được mặc nhiên coi hai giá trị sub giống nhau từ hai IdP là cùng một người.

Ví dụ đối với tài khoản liên kết OIDC, có thể lưu khóa ánh xạ như:

~~~text
External identity key = (issuer = "https://id.example.org", subject = "00u7...")
Internal account ID   = 1742
~~~

Không dùng duy nhất email để liên kết tự động giữa hai nhà cung cấp. Email có thể thay đổi, được tái cấp, chưa được xác minh hoặc được xác minh theo chính sách khác nhau. Liên kết thêm danh tính vào tài khoản hiện tại nên yêu cầu người dùng **xác thực cả tài khoản hiện tại và danh tính mới** bằng quy trình có kiểm soát, và thông báo về thay đổi bảo mật.

### Phiên có thể bị chiếm dù phương thức đăng nhập mạnh

Người dùng đăng nhập bằng passkey nhưng thiết bị sau đó nhiễm mã độc đánh cắp cookie phiên. Kẻ tấn công có thể dùng cookie như một bearer credential trong giới hạn phiên. Biện pháp gồm bảo vệ cookie, giảm bề mặt XSS, kiểm soát CSRF, giới hạn thời gian phiên, thu hồi phiên và yêu cầu xác thực lại cho hành động có rủi ro cao. **SameSite không thay thế mọi biện pháp chống CSRF**, còn HttpOnly không tự ngăn được mọi hành vi lạm dụng từ mã độc chạy trong trang.

## 7. Các tấn công làm sai lệch kết luận “đúng người”

| Tình huống | Cách mục tiêu xác thực bị phá vỡ | Biện pháp tiêu biểu |
| --- | --- | --- |
| Credential stuffing | Thử cặp tên đăng nhập/mật khẩu lộ từ hệ thống khác. | Mật khẩu không tái sử dụng, cảnh báo credential bị lộ, giới hạn tốc độ theo nhiều chiều, MFA phù hợp. |
| Phishing chuyển tiếp mã | Trang giả lấy mật khẩu và OTP rồi đăng nhập theo thời gian thực. | Passkey/WebAuthn chống phishing, kiểm soát origin, đào tạo nhận biết và giám sát bất thường. |
| Replay | Gửi lại OTP, challenge response hoặc token đã bị lộ trong khoảng còn hiệu lực. | Challenge ngẫu nhiên một lần, nonce, giới hạn thời gian, chống tái sử dụng OTP, ràng buộc token/bên gửi khi cần. |
| MFA fatigue | Gửi nhiều push đến khi người dùng bấm chấp thuận. | Giới hạn push, number matching/ngữ cảnh, xác thực chống phishing và cảnh báo. |
| Session fixation / hijacking | Ép nạn nhân dùng session ID đã biết hoặc chiếm cookie sau đăng nhập. | Đổi session ID sau xác thực, cookie an toàn, hạn phiên, thu hồi, ngăn XSS/CSRF. |
| Account enumeration | Dựa vào thông báo hoặc thời gian phản hồi để dò tài khoản tồn tại. | Phản hồi lỗi nhất quán, tránh lộ trạng thái tài khoản; giới hạn thử và giám sát. |
| Account recovery takeover | Kẻ tấn công dùng hỗ trợ/đổi email/reset yếu để thay credential mạnh. | Quy trình khôi phục có mức bảo đảm tương xứng, thông báo độc lập, trì hoãn/thẩm tra thao tác rủi ro. |

Một kiểm tra “mã đúng” chưa đủ để chống replay. Với giao thức thử thách, verifier phải liên kết phản hồi với **thử thách do chính mình vừa sinh ra**, đúng giao dịch, đúng chủ thể, còn hiệu lực và chưa được sử dụng. Với token bearer, không phải token nào cũng dùng một lần; thiết kế phải giảm hậu quả lộ token bằng thời hạn, phạm vi, lưu trữ an toàn và ràng buộc người gửi khi cần.

### Ví dụ lỗi phổ biến: tin email từ client

~~~text
Client gửi: { "email": "director@example.com", "otp": "583012" }
Server chỉ kiểm tra OTP hợp lệ cho một yêu cầu bất kỳ
Server tạo phiên của director@example.com
~~~

Nếu server không ràng buộc OTP với **đúng tài khoản, đúng mục đích và đúng giao dịch**, mã lấy từ tài khoản khác có thể bị dùng để mạo danh. Phiên bản an toàn cần lưu giao dịch xác minh ở server, gắn mã với chủ thể/mục đích, giới hạn số lần thử, thời gian, và đánh dấu đã sử dụng.

## 8. Xác thực liên kết, đăng ký credential và khôi phục tài khoản

Mọi phương thức xác thực chỉ đáng tin bằng quy trình **đăng ký, thay đổi và khôi phục** của nó. Nếu kẻ tấn công có thể tự thêm passkey vào tài khoản người khác qua email reset yếu, passkey mạnh không còn bảo vệ được toàn bộ vòng đời tài khoản.

**Đăng ký mới:** xác định cách tài khoản ban đầu được tạo, những thuộc tính đã xác minh (chẳng hạn quyền truy cập hộp thư) và mức độ kiểm chứng con người thật, nếu ứng dụng cần. Tránh dùng tên hiển thị làm khóa bảo mật.

**Thêm/xóa credential:** yêu cầu phiên hiện tại ở mức phù hợp, cân nhắc xác thực lại, áp dụng chống CSRF và thông báo độc lập khi thay đổi phương thức đăng nhập. Kiểm soát khả năng người dùng vô tình xóa hết mọi đường truy cập hợp lệ.

**Đăng nhập qua IdP:** ứng dụng phải tin IdP cụ thể theo cấu hình trước; kiểm tra toàn bộ kết quả giao thức, nhất là issuer, audience, chữ ký, thời gian và các giá trị chống giả mạo/cross-site như state, nonce, PKCE ở vị trí phù hợp của flow. Khi IdP trả về chủ thể, RP ánh xạ bằng cặp **(issuer, subject)** rồi mới thiết lập tài khoản nội bộ. Giao thức xác thực IdP không thay ứng dụng quyết định quyền.

**Khôi phục:** đặt câu hỏi “bằng chứng nào đủ để cho phép thay thế credential cũ?”. Liên kết đặt lại mật khẩu cần token mạnh, ngắn hạn, dùng một lần, gắn đúng tài khoản và tác vụ. Reset phải giới hạn lạm dụng, không tiết lộ tài khoản tồn tại và cân nhắc thu hồi phiên/credential cũ. Với tài khoản quan trọng, thêm xác nhận qua kênh tin cậy, thời gian chờ hoặc quy trình hỗ trợ có kiểm tra; không dựa vào câu hỏi bảo mật dễ đoán.

**Thay đổi thông tin liên lạc:** email/số điện thoại mới cần được xác minh trước khi dùng cho khôi phục; các thay đổi nhạy cảm nên tạo sự kiện audit và thông báo đến kênh cũ nếu còn tin cậy. Không để thay đổi thông tin liên lạc tự động chứng minh quyền sở hữu danh tính bên thứ ba.

## 9. Thiết kế theo mức bảo đảm và rủi ro

Không có phương thức nào phù hợp mọi tác vụ. Đăng nhập để xem nội dung ít nhạy cảm và phê duyệt thay đổi tài khoản ngân hàng có hậu quả khác nhau; hệ thống cần **mức bảo đảm xác thực tương xứng**. Có thể tham khảo khung AAL của NIST để trao đổi về độ mạnh, nhưng không tự gán AAL chỉ bằng tên “MFA”, “passkey” hoặc “OTP” khi chưa kiểm tra đầy đủ yêu cầu chuẩn.

Khi đặt chính sách, ghi rõ:

- **Tài sản và hậu quả:** tài khoản khách hàng, quyền quản trị, dữ liệu cá nhân, giao dịch chuyển tiền.
- **Đối tượng và bối cảnh:** người dùng phổ thông, quản trị viên, dịch vụ với dịch vụ; thiết bị và môi trường không tin cậy.
- **Bằng chứng và kênh:** credential nào đã đăng ký, chống phishing/replay đến đâu, có yêu cầu MFA hoặc xác thực lại không.
- **Tuổi của kết quả xác thực:** một phiên được tạo hôm qua có đủ cho đổi mật khẩu hôm nay không? Có cần xem thời điểm xác thực gần nhất?
- **Vòng đời ngoại lệ:** mất thiết bị, reset mật khẩu, đổi IdP, thêm tài khoản liên kết, hỗ trợ khách hàng và thu hồi.

Tín hiệu bất thường như vị trí, IP mới, thiết bị chưa từng thấy có thể kích hoạt kiểm soát rủi ro hoặc step-up authentication; chúng **không phải bằng chứng độc lập đủ để kết luận danh tính**. Các tín hiệu này có thể sai và cần chính sách giảm tác động lên người dùng hợp lệ.

## 10. Tình huống thực hành: một người, hai danh tính ngoài hệ thống

Một học viên đã có tài khoản nội bộ 1742 đăng nhập bằng mật khẩu. Sau đó học viên muốn dùng tài khoản công ty từ IdP A và tài khoản cá nhân từ IdP B để vào cùng dữ liệu.

**Thiết kế dễ mắc lỗi:** lấy email do hai IdP trả về, thấy giống nhau thì gộp tài khoản ngay. Đây là phép suy luận nguy hiểm vì email có thể chưa được xác minh, đổi chủ, hoặc không biểu diễn cùng một chủ thể theo quy trình của hai IdP.

**Thiết kế có kiểm soát:**

1. Học viên xác thực vào **tài khoản nội bộ 1742** và thực hiện xác thực lại nếu chính sách yêu cầu.
2. Học viên chủ động bắt đầu thao tác “liên kết tài khoản IdP A”.
3. RP hoàn thành luồng OIDC đúng giao thức, kiểm tra token và ánh xạ danh tính ngoài bằng **issuer + subject**.
4. RP kiểm tra danh tính ngoài chưa được liên kết trái phép với tài khoản khác; yêu cầu xác nhận phù hợp khi có xung đột.
5. RP lưu liên kết ngoài → ID 1742, ghi audit và gửi thông báo bảo mật. Khi đăng nhập lần sau qua IdP A, ánh xạ lại bằng cặp đã lưu thay vì chỉ dùng email.
6. Nếu IdP A ngừng hoạt động hoặc học viên mất quyền truy cập, quy trình khôi phục vẫn xác nhận quyền kiểm soát tài khoản 1742 ở mức tương xứng.

Kết quả: nhiều cách đăng nhập có thể cùng dẫn đến **một tài khoản nội bộ**, nhưng mỗi đường đăng nhập cần bằng chứng và quy tắc liên kết rõ ràng.

## 11. Checklist kiểm tra thiết kế

Dùng các câu hỏi sau khi review một luồng xác nhận danh tính:

- [ ] Ứng dụng có phân biệt **ai được khai báo**, **bằng chứng nào được kiểm tra**, **principal nào được tạo** và **quyền nào được cấp**?
- [ ] Credential đã được đăng ký với đúng chủ thể; các thay đổi và khôi phục có yêu cầu mức xác thực phù hợp?
- [ ] Verifier có xác minh challenge/OTP/token đúng chủ thể, giao dịch, nguồn tin cậy, thời gian và chống replay phù hợp?
- [ ] Luồng đăng nhập có bảo vệ trước phishing, credential stuffing, dò tài khoản và lạm dụng MFA theo mức rủi ro?
- [ ] Sau đăng nhập, phiên có ID mới, thuộc tính cookie/token phù hợp, hết hạn, thu hồi và log sự kiện bảo mật cần thiết?
- [ ] Mọi API có thực hiện kiểm tra quyền theo tài nguyên thay vì chỉ tin “đã đăng nhập”?
- [ ] Nếu dùng OIDC, hệ thống có kiểm tra thông điệp giao thức, ánh xạ bằng issuer + subject và kiểm soát liên kết tài khoản?
- [ ] Hệ thống có yêu cầu xác thực lại cho thao tác nhạy cảm và có quy trình xử lý khi mất authenticator?

### Câu hỏi tự đánh giá

1. Vì sao đăng nhập bằng mật khẩu thành công không chứng minh danh tính pháp lý ngoài đời?
2. Nếu một API đã xác minh JWT hợp lệ nhưng bỏ kiểm tra audience, rủi ro là gì?
3. Vì sao mã TOTP và passkey khác nhau về khả năng chống phishing?
4. Vì sao phải thay session ID sau đăng nhập?
5. Vì sao không được tự động gộp hai tài khoản OIDC chỉ dựa vào email giống nhau?
6. Trong luồng reset mật khẩu, bằng chứng nào cho phép thay credential cũ và vì sao quy trình này phải được bảo vệ tương xứng với đăng nhập?

**Gợi ý đáp án:** (1) mật khẩu chứng minh quyền biết bí mật đã ràng buộc, không phải hồ sơ pháp lý; (2) token có thể được phát hành cho ứng dụng khác; (3) TOTP có thể bị chuyển tiếp còn WebAuthn ràng buộc khóa với RP/origin; (4) chống session fixation; (5) email không phải khóa chủ thể ổn định, đáng tin xuyên IdP; (6) reset là đường cấp quyền kiểm soát tài khoản mới, nên token/quy trình phải giới hạn thời gian, mục đích, số lần sử dụng và lạm dụng.

## 12. Ghi nhớ

**Xác nhận danh tính là một kết luận có điều kiện dựa trên bằng chứng, ranh giới tin cậy và chính sách rủi ro.** Nó bắt đầu từ credential đã đăng ký với chủ thể, được kiểm tra qua một giao thức phù hợp, sau đó mới trở thành principal và phiên. Sự an toàn thực tế phụ thuộc vào toàn bộ vòng đời: đăng ký, đăng nhập, token/phiên, phân quyền, liên kết danh tính, xác thực lại và khôi phục. Khi thiết kế hoặc đánh giá, luôn hỏi: **“Chúng ta vừa chứng minh quyền kiểm soát điều gì, cho chủ thể nào, trong bao lâu, và ai có quyền tin kết luận đó?”**
