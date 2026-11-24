# Kiểm thử flow thất bại

Một luồng xác thực chỉ an toàn khi hệ thống xử lý đúng cả lúc thành công lẫn lúc thất bại. Người dùng nhập sai mật khẩu, mã MFA hết hạn, passkey gửi assertion phát lại, nhà cung cấp danh tính bị timeout hoặc kho phiên không ghi được đều là những tình huống có thể xảy ra trong vận hành. Nếu chỉ kiểm thử đường đi thành công, nhóm phát triển có thể bỏ sót việc cấp token sau một lần xác thực lỗi, giữ challenge có thể dùng lại, tạo phiên dở dang hoặc tiết lộ tài khoản có tồn tại.

Bài học này hướng dẫn thiết kế và thực hiện kiểm thử end-to-end cho các flow thất bại trong hệ thống xác thực danh tính. Phạm vi bao gồm credential, mật khẩu, MFA, passkey, chứng chỉ, token, phiên, liên kết danh tính và khôi phục tài khoản. Trọng tâm là kiểm tra hành vi quan sát được qua ranh giới hệ thống, trạng thái sau lỗi và các bất biến bảo mật.

Sau bài học, người học có thể:

- Phân loại một lần thất bại thành từ chối xác thực dự kiến, từ chối theo chính sách hoặc lỗi vận hành.
- Mô tả các ranh giới tin cậy và trạng thái cần kiểm tra trong một flow xác thực.
- Viết kịch bản âm tính cho mật khẩu, MFA, passkey, chứng chỉ, token, session, liên kết danh tính và recovery.
- Kiểm tra rằng lỗi không tạo ra token, phiên hoặc quyền truy cập ngoài ý muốn.
- Kiểm thử timeout, retry, replay, race condition, giới hạn tốc độ và sự cố dependency một cách có thể lặp lại.
- Thu thập bằng chứng từ API, UI, cơ sở dữ liệu kiểm thử và audit event mà không làm lộ bí mật.

## 1. Flow thất bại là gì?

Flow thất bại là một đường đi hợp lệ trong mô hình xử lý, nơi một điều kiện không được đáp ứng hoặc một dependency không thể hoàn thành công việc. Kết quả đúng có thể là từ chối, yêu cầu thử lại, chuyển sang phương thức xác thực khác hoặc báo lỗi tạm thời. Vì vậy, không phải mọi phản hồi lỗi đều là bug. Bug xuất hiện khi hành vi thực tế vi phạm hợp đồng, làm sai trạng thái hoặc làm suy yếu ranh giới bảo mật.

Cần phân biệt ba nhóm:

| Nhóm | Ví dụ | Kết quả mong đợi |
|---|---|---|
| Từ chối xác thực | Mật khẩu sai, chữ ký passkey không hợp lệ, OTP sai | Không xác lập danh tính đã xác thực; không cấp quyền |
| Từ chối theo chính sách | Tài khoản bị khóa, thiết bị không đạt assurance, người dùng bị vô hiệu hóa | Áp dụng đúng chính sách; thông báo phù hợp; ghi nhận lý do nội bộ |
| Lỗi vận hành | Auth database timeout, dịch vụ MFA không phản hồi, kho session không ghi được | Fail closed ở ranh giới bảo mật; phản hồi có thể thử lại khi phù hợp; không tạo trạng thái nửa vời |

Một số tình huống có thể thuộc nhiều nhóm tùy hợp đồng. Ví dụ, mã OTP hết hạn là từ chối xác thực; dịch vụ gửi OTP không hoạt động là lỗi vận hành. Không nên dùng một nhãn chung “login failed” trong thiết kế kiểm thử rồi bỏ qua khác biệt về trạng thái và khả năng phục hồi.

Một kiểm thử thất bại tốt trả lời được bốn câu hỏi:

1. Điều kiện nào khiến flow thất bại?
2. Người dùng và client quan sát được điều gì?
3. Hệ thống đã thay đổi trạng thái nào, và trạng thái nào bắt buộc không được thay đổi?
4. Có bằng chứng nào cho thấy hệ thống từ chối đúng, không phát sinh side effect nguy hiểm và vẫn có thể phục hồi?

## 2. Mô hình hóa flow và ranh giới tin cậy

Một flow đăng nhập điển hình đi qua nhiều thành phần. Trình duyệt hoặc ứng dụng gửi yêu cầu; gateway kiểm tra request và giới hạn lưu lượng; authentication service chọn phương thức; verifier kiểm tra credential; MFA hoặc identity provider có thể được gọi; token issuer và session store tạo trạng thái đăng nhập; audit pipeline ghi lại kết quả.

~~~mermaid
flowchart LR
    U[Browser hoặc ứng dụng] --> G[Gateway và rate limiter]
    G --> A[Authentication service]
    A --> V[Credential verifier]
    A --> M[MFA hoặc Passkey service]
    A --> I[Identity Provider]
    V --> A
    M --> A
    I --> A
    A --> P[Policy và account state]
    P --> T[Token issuer]
    T --> S[Session store]
    A --> L[Audit và security events]
    T --> L
    S --> U
~~~

Mỗi mũi tên là một ranh giới cần xem xét. Request có thể bị sửa, gửi lại hoặc phát ra từ client không đáng tin cậy. Dependency có thể chậm, lỗi hoặc trả dữ liệu không đầy đủ. Dữ liệu đọc từ replica có thể cũ. Một tiến trình có thể dừng sau khi ghi một phần trạng thái. Kiểm thử end-to-end cần quan sát tác động của các ranh giới đó thay vì chỉ gọi một hàm kiểm tra mật khẩu.

Với mỗi flow, hãy xác định:

- **Actor:** người dùng, administrator, workload hoặc identity provider.
- **Subject:** tài khoản hay principal mà hệ thống đang xác thực.
- **Credential:** mật khẩu, OTP, passkey, certificate hoặc assertion liên kết.
- **Challenge:** nonce, state, transaction ID hoặc MFA challenge dùng để ràng buộc request.
- **Context:** origin, RP ID, audience, issuer, tenant, thiết bị, thời gian và mức assurance.
- **Decision:** accept, deny, step-up, retry hoặc temporary failure.
- **Artifacts:** token, cookie, session, recovery code, audit event và thông báo gửi ra ngoài.

Không được coi các giá trị do client gửi như user ID, tenant ID, role, email hoặc assurance level là sự thật đã được xác minh. Hệ thống phải tự ràng buộc chúng với credential, challenge và policy phía server.

## 3. Các bất biến bảo mật cần giữ khi thất bại

Trước khi viết test, hãy chuyển yêu cầu bảo mật thành các bất biến có thể kiểm tra. Một bất biến mô tả điều phải luôn đúng, kể cả khi một bước giữa flow bị lỗi.

### 3.1 Không xác thực thành công khi bằng chứng không hợp lệ

Nếu credential sai, hết hạn, bị thu hồi, không khớp challenge hoặc không thỏa policy thì principal không được chuyển sang trạng thái authenticated. Một thông báo lỗi trên UI không đủ chứng minh điều này; cần kiểm tra cả token, cookie, session và quyền truy cập vào endpoint được bảo vệ.

### 3.2 Không cấp quyền từ trạng thái dở dang

Nếu verifier thành công nhưng bước MFA thất bại, hệ thống không được phát access token có quyền tương đương đăng nhập hoàn tất. Nếu token đã được tạo trong một kiến trúc nhiều bước, token đó phải được giới hạn rõ ràng, chẳng hạn chỉ cho phép hoàn thành MFA, có audience và scope hẹp, thời hạn ngắn và không được chấp nhận ở API nghiệp vụ.

### 3.3 Challenge và mã dùng một lần chỉ được tiêu thụ đúng một lần

Challenge, OTP, recovery code và authorization code phải được ràng buộc với đúng giao dịch, đúng subject và thời hạn. Khi đã tiêu thụ thành công, lần dùng tiếp theo phải bị từ chối. Khi giao dịch thất bại, hành vi giữ, hủy hoặc cho phép thử lại challenge phải theo một quy tắc rõ ràng; không được vô tình biến một challenge cũ thành credential có thể phát lại.

### 3.4 Thay đổi trạng thái phải nguyên tử

Không để một lỗi giữa chừng tạo ra trạng thái mâu thuẫn, ví dụ:

- Challenge đã đánh dấu hoàn tất nhưng token chưa được phát hành và client không thể tiếp tục.
- Session được tạo nhưng response bị lỗi khiến client không nhận được cookie, trong khi session vẫn có quyền truy cập.
- Recovery token đã bị tiêu thụ nhưng mật khẩu chưa được đổi.
- Identity link đã được ghi nhưng kiểm tra quyền sở hữu tài khoản chưa hoàn tất.

Nếu không thể dùng một transaction cơ sở dữ liệu xuyên suốt, thiết kế cần có state machine, idempotency key, outbox hoặc cơ chế bù trừ và reconciliation phù hợp.

### 3.5 Fail closed ở ranh giới cấp quyền

Khi không xác minh được chữ ký, trạng thái thu hồi, policy hoặc session, hệ thống phải từ chối quyền truy cập. Không được diễn giải “không kiểm tra được” thành “hợp lệ”. Tuy nhiên, lỗi dependency cũng không nên bị biến thành một thông báo sai rằng người dùng nhập sai mật khẩu; cần giữ phân loại nội bộ để vận hành xử lý.

### 3.6 Không tiết lộ bí mật hoặc sự tồn tại của tài khoản

Response công khai không nên phân biệt quá chi tiết giữa “email không tồn tại”, “mật khẩu sai” và “tài khoản bị khóa” nếu điều đó cho phép dò tài khoản. Audit event nội bộ vẫn cần reason code đủ chi tiết để điều tra. Không ghi mật khẩu, OTP, access token, refresh token, cookie, recovery URL, private key hoặc assertion đầy đủ vào log.

### 3.7 Retry không được tạo thêm quyền hoặc side effect

Một request được gửi lại do timeout không được tạo nhiều session, gửi nhiều recovery email ngoài ý muốn, tiêu thụ nhiều lần cùng một challenge hoặc thực hiện hai lần thao tác đổi credential. Kết quả retry phải dựa trên idempotency và trạng thái giao dịch, không dựa vào giả định rằng client chỉ gửi một lần.

## 4. Phân loại lỗi để tạo ma trận kiểm thử

Bảng sau là điểm khởi đầu. Khi triển khai thực tế, bổ sung mã lỗi, trạng thái HTTP, UI copy và chính sách retry theo hợp đồng của sản phẩm.

| Điểm lỗi | Kích hoạt trong test | Kỳ vọng bảo mật chính |
|---|---|---|
| Credential không đúng | Mật khẩu hoặc OTP sai | Không authenticated, không token/session |
| Credential hết hạn | OTP, challenge hoặc recovery token quá TTL | Từ chối; không gia hạn ngầm |
| Credential bị thu hồi | Passkey, certificate hoặc refresh token đã revoke | Từ chối kể cả khi chữ ký/định dạng còn hợp lệ |
| Context không khớp | Sai origin, RP ID, issuer, audience, tenant hoặc nonce | Từ chối; không dùng context do client tự khai làm căn cứ |
| Replay | Gửi lại challenge, assertion, code hoặc recovery token | Chỉ một giao dịch được chấp nhận |
| Account policy | Disabled, locked, suspended hoặc cần step-up | Áp dụng đúng policy; không rò trạng thái nhạy cảm |
| Rate limit | Gửi nhiều lần sai hoặc resend liên tục | Chặn theo policy, không tạo đường vòng qua nhiều endpoint |
| Dependency timeout | MFA, IdP, database hoặc session store chậm | Không cấp quyền khi chưa có bằng chứng cần thiết |
| Dependency lỗi | HTTP 5xx, TLS lỗi, dữ liệu sai định dạng | Fail closed; có telemetry và đường phục hồi |
| Ghi trạng thái lỗi | Commit thất bại hoặc kết quả commit không rõ | Không để session/credential ở trạng thái mâu thuẫn |
| Race condition | Hai request đồng thời dùng cùng mã | Chỉ một lần tiêu thụ thành công |
| Key rotation | Key ID cũ không còn hợp lệ hoặc cache stale | Chỉ chấp nhận key nằm trong trust policy |

Không phải mọi lỗi đều phải trả cùng một HTTP status. Ví dụ, 401 thường phù hợp cho xác thực không thành công, 429 cho giới hạn lưu lượng và 5xx cho sự cố dependency. Nhưng một số API cố ý chuẩn hóa response để chống enumeration. Hãy kiểm tra đúng hợp đồng API hiện hành, không áp đặt mã trạng thái từ một ví dụ chung.

## 5. Thiết kế kiểm thử end-to-end

### 5.1 Kiểm thử ở đúng ranh giới

Một bài test end-to-end nên đi qua những thành phần mà người dùng thực sự phụ thuộc vào: UI hoặc API public, gateway, authentication service, verifier, policy và nơi lưu session/token. Có thể thay một dependency bên ngoài bằng test double nếu mục tiêu là cô lập lỗi; nhưng cần ít nhất một nhóm kiểm thử tích hợp với cấu hình gần production để xác nhận hợp đồng thật.

Phân biệt ba mức:

- **Unit test:** xác minh logic nhỏ như kiểm tra expiry hoặc ánh xạ reason code. Nhanh và dễ bao phủ nhiều nhánh.
- **Integration test:** xác minh hợp đồng giữa auth service với database, verifier, MFA adapter, token issuer hoặc session store.
- **End-to-end test:** xác minh toàn bộ hành vi nhìn từ client qua các ranh giới được chọn, bao gồm trạng thái cuối và side effect.

Không cần biến mọi tổ hợp dữ liệu thành E2E. Hãy dùng unit và integration test để bao phủ chi tiết, sau đó chọn các đường đi đại diện có rủi ro cao cho E2E.

### 5.2 Viết test theo Given / When / Then

Mỗi test nên chỉ rõ:

- **Given:** tài khoản, credential, policy, clock, dependency và trạng thái ban đầu.
- **When:** request cụ thể hoặc lỗi được tiêm vào.
- **Then:** response công khai, trạng thái xác thực, token/session, challenge, side effect và audit event.

Ví dụ:

- Given: tài khoản đang hoạt động, mật khẩu đúng, MFA TOTP đã bật và challenge còn hạn.
- When: người dùng nhập một OTP sai.
- Then: bước MFA bị từ chối; không có session hoàn tất; challenge được xử lý theo policy; lần thử được ghi nhận; UI hiển thị lỗi an toàn; request tiếp theo tuân theo giới hạn thử lại.

Nếu chỉ kiểm tra rằng response có chữ “Invalid code”, test chưa chứng minh được bất biến bảo mật.

### 5.3 Chốt hợp đồng của từng lớp quan sát

Với một failure flow, hãy kiểm tra tối thiểu các lớp sau:

| Lớp | Câu hỏi kiểm tra |
|---|---|
| UI/client | Người dùng thấy thông báo nào? Có lộ thông tin tài khoản hoặc chi tiết nội bộ không? Có nút retry/fallback đúng trạng thái không? |
| HTTP/API | Status, error code, schema, header và cache behavior có đúng hợp đồng không? |
| Authentication state | Principal có bị đánh dấu authenticated không? Assurance level có bị nâng sai không? |
| Token/session | Có access token, refresh token, cookie hoặc session mới nào được tạo không? Token cũ có bị thu hồi đúng lúc không? |
| Challenge/credential | Challenge còn hiệu lực hay đã bị tiêu thụ? Mã dùng một lần có bị dùng lại không? |
| Side effect | Có gửi email, SMS, push, webhook hoặc tạo identity link ngoài ý muốn không? |
| Audit/telemetry | Có event đúng reason code, correlation ID và timestamp không? Có bí mật trong log không? |

Không phải mọi test đều cần truy vấn trực tiếp database. Hãy ưu tiên API kiểm thử, test fixture hoặc audit interface được hỗ trợ. Khi cần đọc trạng thái nội bộ, chỉ dùng môi trường kiểm thử và quyền truy cập tối thiểu.

## 6. Chuẩn bị môi trường và dữ liệu kiểm thử

### 6.1 Dùng tài khoản và credential riêng cho test

Tạo fixture có định danh rõ ràng, chẳng hạn:

- Tài khoản đang hoạt động có mật khẩu hợp lệ.
- Tài khoản có TOTP và secret riêng cho test.
- Tài khoản có passkey test credential và RP ID/origin cố định.
- Tài khoản có certificate fixture với chain và thời hạn đã biết.
- Tài khoản có hai identity provider liên kết trong môi trường test.
- Tài khoản có refresh token, recovery code và session được tạo từ fixture.

Không dùng tài khoản thật, OTP thật, private key production, recovery link của người dùng hoặc dữ liệu cá nhân không cần thiết. Không gửi email/SMS thật từ test suite; dùng sandbox inbox, fake gateway hoặc provider test mode.

### 6.2 Kiểm soát thời gian

Expiry và not-before là nguồn gây flaky test nếu dựa vào thời gian thực. Dùng clock có thể điều khiển trong service hoặc test environment. Tạo challenge tại thời điểm T, sau đó dịch clock qua TTL để kiểm tra hết hạn. Không chèn sleep dài để chờ mã hết hạn.

Nếu nhiều service dùng clock khác nhau, kiểm tra skew có chủ đích. Một test nên xác định rõ tolerance được cấu hình, ví dụ thời gian cho phép lệch giữa issuer và verifier. Không nới tolerance chỉ để test qua.

### 6.3 Dùng dependency giả lập có hành vi xác định

Test double nên có thể trả về:

- Thành công hợp lệ.
- Từ chối nghiệp vụ.
- Timeout trước khi nhận request.
- Timeout sau khi đã xử lý request.
- HTTP 5xx.
- Response sai schema hoặc thiếu field.
- Chứng thư TLS không hợp lệ.
- Kết quả chậm hơn timeout.
- Kết quả cũ do replica hoặc cache.

Trường hợp “timeout sau khi dependency đã xử lý” đặc biệt quan trọng: caller không biết thao tác đã hoàn thành hay chưa. Retry phải không tạo side effect trùng lặp.

### 6.4 Cô lập và dọn dữ liệu

Mỗi test nên dùng account, challenge, session và correlation ID riêng. Dọn fixture sau test bằng API quản trị test hoặc transaction rollback khi phù hợp. Test song song không được dùng chung OTP hoặc recovery code. Nếu test thất bại giữa chừng, teardown vẫn phải thu hồi session và xóa dữ liệu tạm.

## 7. Các flow thất bại cần kiểm tra

### 7.1 Mật khẩu và credential cơ bản

Kiểm tra các trường hợp:

1. Username/email không tồn tại và password sai.
2. Password sai với account tồn tại.
3. Account bị disabled, suspended hoặc locked.
4. Password đã hết hạn theo policy.
5. Credential đã bị reset trong một phiên khác.
6. Password verifier hoặc credential store timeout.
7. Hash record sai định dạng hoặc thuật toán không còn được hỗ trợ.
8. Request thiếu field, field quá dài hoặc encoding bất thường.
9. Client gửi nhiều lần sai qua các endpoint hoặc địa chỉ IP khác nhau.
10. Một request thành công cạnh tranh với request sai làm thay đổi trạng thái lockout.

Kỳ vọng:

- Không tạo authenticated session hoặc token khi credential sai.
- Không trả thông tin đủ để phân biệt tài khoản tồn tại nếu policy chống enumeration yêu cầu response thống nhất.
- Rate limit được áp dụng theo nhiều chiều phù hợp, chẳng hạn account, IP, device hoặc risk signal; không dựa duy nhất vào một header do client tự khai.
- Account lockout không thể bị lợi dụng để khóa hàng loạt tài khoản người khác một cách dễ dàng; chính sách phải cân bằng chống brute force và denial of service.
- Lỗi verifier được ghi nhận như sự cố vận hành, không giả thành “mật khẩu sai” trong telemetry nội bộ.
- Password không xuất hiện trong URL, log, trace, exception hoặc test report.

Không nên chỉ kiểm tra số lần thử trên UI. Gửi request trực tiếp đến API để xác nhận rate limit và lockout được thực thi phía server. Kiểm tra cả đường đăng nhập thay thế để bảo đảm không thể bỏ qua giới hạn bằng cách đổi endpoint.

### 7.2 MFA và OTP

Các ca kiểm thử quan trọng:

| Trường hợp | Điều cần xác minh |
|---|---|
| OTP sai | Từ chối, tăng bộ đếm thử theo policy, không cấp session |
| OTP hết hạn | Từ chối dù mã có định dạng đúng |
| OTP đã dùng | Replay bị từ chối |
| OTP đúng nhưng thuộc account khác | Không xác thực nhầm subject |
| Challenge đã hết hạn | Không chấp nhận mã cho challenge cũ |
| Resend liên tục | Có rate limit; mã cũ được xử lý theo policy |
| MFA provider timeout | Không tự bỏ qua MFA |
| Push bị deny | Không hoàn tất đăng nhập |
| Push chưa phản hồi | Chờ hoặc timeout đúng state; không coi là approve |
| Recovery code đã dùng | Từ chối lần dùng tiếp theo |
| Hai request cùng dùng một OTP | Tối đa một request được tiêu thụ thành công |

Với TOTP, kiểm tra time step, cửa sổ clock skew và việc một mã đã được chấp nhận có thể bị dùng lại trong cùng time step hay không. Với SMS/email OTP, kiểm tra code gắn với purpose và transaction cụ thể. Một mã dùng cho đổi email không được dùng để đăng nhập hoặc đổi mật khẩu.

Với push MFA, kiểm tra push approval có ràng buộc với đúng phiên đăng nhập, thiết bị, giao dịch và thông tin hiển thị hay không. Một thông báo push cũ không được phê duyệt một challenge mới. Nếu ứng dụng hiển thị number matching hoặc transaction details, test cần xác minh dữ liệu đó được tạo từ server challenge và không bị client sửa.

### 7.3 Passkey và WebAuthn

Passkey/WebAuthn có nhiều điều kiện xác minh hơn một chữ ký số đơn giản. Hãy tạo test cho:

- Challenge không tồn tại, hết hạn hoặc đã tiêu thụ.
- Challenge được tạo cho một account hoặc ceremony khác.
- Client data có origin không nằm trong allowlist.
- RP ID hash không khớp RP ID dự kiến.
- Challenge trong clientDataJSON không khớp challenge server lưu.
- Assertion có chữ ký sai hoặc credential public key không khớp.
- Credential ID không được đăng ký hoặc đã bị thu hồi.
- User presence hoặc user verification flag không đáp ứng policy.
- Assertion được gửi lại lần thứ hai.
- Credential thuộc account khác hoặc tenant khác.
- Request có authenticator data sai định dạng.
- Đồng hồ, counter hoặc metadata authenticator thay đổi theo cách bất thường.

Các assertion được ký bằng private key của authenticator. Server cần xác minh chữ ký bằng public key đã đăng ký và kiểm tra origin, RP ID hash, challenge cùng các flag cần thiết. Không coi việc client báo “passkey verified” là bằng chứng.

Counter của authenticator không phải lúc nào cũng tăng theo cách đơn giản, đặc biệt với passkey đồng bộ giữa thiết bị. Test phải theo policy triển khai và đặc điểm authenticator; không viết một assertion chung rằng mọi counter không tăng đều chứng minh replay. Dù vậy, challenge phải được tiêu thụ một lần và replay của cùng assertion phải bị ngăn chặn.

Một test E2E hữu ích: đăng nhập bằng passkey hợp lệ, lưu lại request assertion ở test harness, hoàn tất đăng nhập, rồi phát lại cùng assertion với cùng challenge. Lần thứ hai phải bị từ chối và không tạo session mới. Dùng dữ liệu test, không thu thập assertion của người dùng thật.

### 7.4 Chứng chỉ và xác thực dựa trên khóa

Nếu hệ thống hỗ trợ client certificate hoặc workload certificate, kiểm tra:

- Certificate hết hạn hoặc chưa đến thời điểm có hiệu lực.
- Chain không nối tới trust anchor được cấu hình.
- Certificate bị revoke theo nguồn trạng thái thu hồi được hỗ trợ.
- SAN hoặc subject không ánh xạ tới principal được phép.
- EKU, key usage hoặc algorithm không đáp ứng policy.
- Certificate hợp lệ về chữ ký nhưng thuộc tenant hoặc workload khác.
- Certificate rotation xảy ra trong lúc cache hoặc connection pool còn giữ trạng thái cũ.
- Dịch vụ OCSP/CRL timeout hoặc không truy cập được.

Policy khi nguồn revocation không sẵn sàng phải được định nghĩa rõ theo loại credential và mức rủi ro. Test phải xác nhận hành vi fail closed hoặc chế độ degraded được phê duyệt; không mặc định “không tra cứu được nghĩa là chưa bị revoke”.

### 7.5 Token và federation

Đối với JWT hoặc token tương tự, kiểm tra các lỗi:

- Chữ ký không hợp lệ hoặc thuật toán không được phép.
- **kid** không tồn tại, key không tin cậy hoặc key đã bị thu hồi.
- **iss** không khớp issuer đã cấu hình.
- **aud** hoặc **azp** không đúng client/resource.
- **exp** đã qua, **nbf** nằm trong tương lai hoặc **iat** bất hợp lý theo policy.
- Nonce hoặc state không khớp giao dịch.
- Token bị gửi sang tenant khác.
- Token loại ID bị dùng như access token hoặc ngược lại.
- Claim role/scope do client tự sửa.
- Token từ issuer không nằm trong allowlist.

Không chỉ decode JWT để kiểm tra payload. Decode không xác minh chữ ký. Test phải gửi token tới resource server hoặc verifier thực tế và xác nhận quyền truy cập bị từ chối.

Với OIDC authorization code flow, kiểm tra state mismatch, nonce mismatch, code hết hạn, code đã dùng, redirect URI không khớp và PKCE verifier sai. Authorization code phải ràng buộc với đúng client, redirect URI và PKCE challenge. Không để callback lỗi vẫn tạo local session.

Với SAML hoặc federation tương tự, tùy giao thức triển khai, kiểm tra issuer, audience, recipient, destination, thời hạn, request correlation, signature và replay protection. Không chấp nhận assertion chỉ vì XML parse thành công. Kiểm tra cả canonicalization/signature validation theo thư viện được tin cậy; tránh tự viết parser hoặc verifier trong test fixture.

### 7.6 Session, cookie và refresh token

Sau một flow thất bại, kiểm tra không có session hoàn tất mới. Với flow đã có session trước đó, xác định rõ session cũ phải còn hiệu lực, bị thu hồi hay bị yêu cầu step-up. Không để một lần login lỗi làm mất session hợp lệ ngoài ý muốn nếu policy không yêu cầu.

Các tình huống cần test:

- Session ID cũ được giữ sau khi nâng quyền thay vì rotate.
- Cookie có thuộc tính **Secure**, **HttpOnly** và **SameSite** theo thiết kế.
- Cookie domain/path quá rộng hoặc sai tenant.
- Session đã hết hạn nhưng API vẫn chấp nhận.
- Session bị revoke nhưng cache vẫn cho phép truy cập.
- Session store timeout khi tạo hoặc thu hồi session.
- Refresh token hết hạn, bị revoke hoặc bị replay.
- Refresh token rotation phát hiện token cũ bị dùng lại.
- Logout không thu hồi session hoặc refresh token theo hợp đồng.
- CSRF token/state sai ở endpoint thay đổi trạng thái.
- Client gửi session ID do mình chọn trước khi đăng nhập (session fixation).

Refresh token rotation cần kiểm tra cả chuỗi token. Khi token cũ bị phát lại, hệ thống phải áp dụng chính sách phát hiện reuse, thường là thu hồi token family hoặc yêu cầu xác thực lại. Kiểm tra rằng response retry do timeout không tạo nhiều token family hợp lệ.

### 7.7 Liên kết danh tính và chuyển đổi tài khoản

Liên kết một identity provider với tài khoản hiện có là thao tác nhạy cảm vì có thể thay đổi cách truy cập tài khoản. Kiểm tra:

- Người dùng chưa xác thực đủ assurance nhưng yêu cầu link.
- State hoặc nonce của callback không khớp.
- Subject từ IdP đã được liên kết với account khác.
- Email trùng nhưng chưa được IdP xác minh.
- Tenant trong callback không khớp tenant của tài khoản đích.
- Callback được phát lại.
- Người dùng hủy consent hoặc IdP trả lỗi.
- Request link timeout sau khi IdP đã xử lý.
- Hai request đồng thời cố liên kết cùng một external subject.
- Unlink identity cuối cùng khiến tài khoản không còn phương thức đăng nhập hợp lệ.

Không tự động liên kết chỉ dựa trên email trùng, trừ khi có policy xác minh và kiểm soát rõ ràng. Test cần xác nhận external subject là khóa định danh theo issuer, không chỉ theo chuỗi email. Khi link thất bại, mapping không được ghi một phần và không được tạo session với danh tính khác.

### 7.8 Khôi phục tài khoản

Recovery là một flow xác thực có mức rủi ro cao vì nó cho phép thay đổi credential hoặc khôi phục quyền truy cập khi phương thức cũ không còn dùng được.

Các ca cần kiểm tra:

- Email/phone không tồn tại; response không tiết lộ account existence.
- Recovery token sai, hết hạn, đã dùng hoặc không đúng purpose.
- Token được gửi tới account khác hoặc tenant khác.
- Token bị phát lại sau khi password đã đổi.
- Hai request đồng thời dùng cùng recovery token.
- Email/SMS provider lỗi trước hoặc sau khi chấp nhận gửi.
- Người dùng đổi password nhưng session cũ không được xử lý theo policy.
- Mất passkey và yêu cầu thêm passkey mới.
- Recovery code đã dùng hoặc bị revoke.
- Helpdesk-assisted recovery thiếu bằng chứng hoặc thiếu phê duyệt.
- Recovery hoàn tất nhưng audit event hoặc notification không được tạo.

Recovery token cần entropy đủ mạnh, thời hạn ngắn phù hợp, được lưu dưới dạng an toàn (ví dụ hash nếu thiết kế cho phép), ràng buộc với subject và purpose, và chỉ được tiêu thụ một lần. Không ghi token đầy đủ vào log hoặc analytics. Sau recovery, kiểm tra chính sách thu hồi session, refresh token và credential cũ; đồng thời xác nhận thông báo bảo mật được gửi đúng kênh.

## 8. Kiểm thử lỗi dependency và partial failure

Các lỗi dependency thường tạo ra bug khó thấy vì mỗi thành phần riêng lẻ có thể hoạt động đúng. Hãy kiểm tra những điểm mà kết quả của một thao tác có thể không rõ ràng.

### 8.1 Timeout ở từng thời điểm

Phân biệt:

1. **Timeout trước khi dependency nhận request:** thao tác chưa bắt đầu.
2. **Timeout trong khi dependency xử lý:** caller không biết kết quả.
3. **Timeout sau khi dependency đã commit:** thao tác có thể đã thành công dù caller nhận lỗi.
4. **Response đến muộn:** caller đã retry hoặc hủy giao dịch trước khi response cũ xuất hiện.

Ví dụ, dịch vụ MFA nhận yêu cầu gửi OTP, gửi thành công nhưng response bị timeout. Nếu client retry và hệ thống gửi thêm một mã, policy resend phải xác định mã nào còn hiệu lực và giới hạn side effect. Với session store, timeout sau commit có thể khiến server tạo session nhưng không trả cookie. Cần idempotency hoặc cơ chế tra cứu kết quả để không tạo nhiều session.

### 8.2 Database và tính nhất quán

Tiêm lỗi tại các điểm:

- Đọc account state thất bại.
- Ghi failed-attempt counter thất bại.
- Đánh dấu challenge consumed thất bại.
- Ghi session thành công nhưng ghi audit/outbox thất bại.
- Commit thành công nhưng kết nối bị ngắt trước khi client nhận xác nhận.
- Replica trả dữ liệu cũ sau khi credential bị revoke.

Test cần biết thao tác nào là nguồn sự thật và tính nhất quán được đảm bảo ở mức nào. Không dùng read replica eventual consistency để quyết định cấp quyền nếu nó có thể trả về credential hoặc session đã bị thu hồi. Với audit/outbox, định nghĩa rõ event nào bắt buộc phải tồn tại trước khi giao dịch được coi là hoàn tất và event nào có thể được chuyển tiếp bất đồng bộ.

### 8.3 Key service và cấu hình

Kiểm tra khi signing key service không truy cập được, key ID không có, key rotation đang diễn ra hoặc cache chứa key cũ. Không dùng fallback sang secret mặc định hoặc thuật toán yếu để “giữ dịch vụ chạy”. Verifier chỉ chấp nhận key nằm trong trust configuration.

Test cấu hình sai cũng quan trọng: origin allowlist thiếu, RP ID sai, issuer URL trỏ nhầm môi trường, redirect URI rộng quá mức hoặc audience bị dùng chung giữa service. Những lỗi này có thể khiến flow hợp lệ bị từ chối hoặc tạo trust boundary quá rộng.

### 8.4 Circuit breaker và phục hồi

Nếu dependency liên tục lỗi, circuit breaker có thể mở. Kiểm tra:

- Request mới nhận lỗi tạm thời đúng hợp đồng.
- Không có request nào được âm thầm chuyển sang bỏ qua bước xác thực.
- Sau khi dependency phục hồi, circuit breaker đóng theo policy.
- Request đang chờ không hoàn tất muộn và tạo session sau khi client đã hủy.
- Metrics phản ánh số lần timeout, open/half-open/closed và latency.

Không kiểm tra circuit breaker chỉ bằng cách chờ một khoảng thời gian cố định. Dùng clock hoặc cấu hình test có thể điều khiển để làm cho thời điểm chuyển state xác định.

## 9. Replay, retry và race condition

Một flow có thể an toàn khi chạy tuần tự nhưng thất bại khi hai request đến gần như đồng thời. Những tài nguyên cần kiểm tra atomic consume gồm OTP, challenge, recovery code, authorization code, refresh token và identity-link transaction.

Ví dụ hai request cùng gửi một recovery token:

~~~mermaid
sequenceDiagram
    participant C1 as Client A
    participant C2 as Client B
    participant S as Recovery service
    participant DB as State store
    C1->>S: Consume token X
    C2->>S: Consume token X
    S->>DB: Atomic consume X
    DB-->>S: Success for one request
    S->>DB: Consume X from second request
    DB-->>S: Already consumed
    S-->>C1: Recovery accepted
    S-->>C2: Rejected
~~~

Kết quả mong đợi là chỉ một request thắng. Nếu cả hai đều thành công, có thể có race condition trong thao tác đọc rồi ghi. Cần dùng conditional update, unique constraint, compare-and-swap hoặc cơ chế tương đương. Kiểm tra ở cấp API để xác nhận hệ thống thật bảo vệ thao tác, không chỉ mock trong unit test.

Một ma trận concurrency hữu ích:

| Tài nguyên | Thao tác cạnh tranh | Kết quả cần xác minh |
|---|---|---|
| OTP | Hai lần verify cùng lúc | Một lần consume thành công tối đa |
| WebAuthn challenge | Hai assertion cùng challenge | Một ceremony được chấp nhận |
| Recovery token | Hai lần đổi password | Một lần đổi thành công |
| Refresh token | Hai lần refresh token cũ | Phát hiện reuse theo policy |
| Identity link | Hai callback cùng external subject | Không tạo mapping trùng hoặc chiếm tài khoản |
| Session | Retry create sau timeout | Không tạo nhiều session không kiểm soát |

Retry phải phân biệt lỗi có thể thử lại và lỗi không thể thử lại. Credential sai không nên được tự động retry vô hạn. Timeout có thể retry nếu request idempotent và policy cho phép. Với thao tác một lần, cần lưu kết quả theo idempotency key hoặc transaction ID. Idempotency key phải được ràng buộc với principal, endpoint và payload thích hợp; không để một key của người dùng này trả lại kết quả giao dịch của người khác.

## 10. Ví dụ thực hành: đăng nhập bằng mật khẩu rồi MFA thất bại

Giả sử một ứng dụng học tập đa tenant yêu cầu password và TOTP. Người dùng nhập đúng mật khẩu nhưng nhập sai OTP. Test cần chứng minh rằng password đúng mới chỉ hoàn thành bước đầu, chưa cấp quyền truy cập nội dung khóa học.

### 10.1 Điều kiện ban đầu

- Tài khoản test đang active và thuộc tenant **school-a**.
- Password fixture hợp lệ.
- TOTP được bật; secret chỉ tồn tại trong test vault.
- Clock test được cố định.
- Session store và audit sink là thành phần kiểm thử thật hoặc adapter có thể quan sát.
- Không có session đăng nhập trước đó cho browser context đang dùng.

### 10.2 Các bước và kỳ vọng

1. Mở trang đăng nhập và gửi username/password hợp lệ.
2. Xác nhận server tạo MFA challenge có TTL, subject và transaction ID đúng.
3. Xác nhận response chưa chứa access token có thể gọi API khóa học.
4. Gửi OTP sai.
5. Xác nhận API trả lỗi theo hợp đồng và UI thông báo có thể thử lại.
6. Gọi endpoint yêu cầu đăng nhập hoàn tất bằng cookie/token hiện có; request phải bị từ chối.
7. Kiểm tra không có session authenticated mới.
8. Kiểm tra challenge và failed-attempt counter đúng policy.
9. Kiểm tra audit event có reason code MFA failure và correlation ID.
10. Kiểm tra log/test report không chứa password, OTP hoặc secret.

### 10.3 Pseudocode phía browser

Đây là pseudocode minh họa theo phong cách Playwright. Tên selector, endpoint và schema phải được thay bằng hợp đồng thật của ứng dụng.

~~~typescript
test("khong cap session khi MFA that bai", async ({ page, request }) => {
  const account = await fixtures.activeTotpAccount("school-a");
  const browserContext = page.context();

  await page.goto("/login");
  await page.getByLabel("Email").fill(account.email);
  await page.getByLabel("Password").fill(account.password);
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByText("Enter your verification code")).toBeVisible();

  const challengeId = await fixtures.lastChallengeId(account.id);
  expect(challengeId).toBeTruthy();

  await page.getByLabel("Verification code").fill("000000");
  await page.getByRole("button", { name: "Verify" }).click();

  await expect(page.getByText("The code could not be verified")).toBeVisible();

  const protectedResponse = await request.get("/api/courses", {
    headers: await fixtures.currentBrowserAuthHeaders(browserContext)
  });
  expect([401, 403]).toContain(protectedResponse.status());

  const state = await fixtures.inspectAuthenticationState(account.id);
  expect(state.completedSessions).toHaveLength(0);
  expect(state.challenge(challengeId).failedAttempts).toBe(1);
});
~~~

Pseudocode trên giả định fixture có quyền quan sát state và response code thuộc một trong hai giá trị minh họa. Trong test thật, không nên đọc password từ log hoặc in credential khi assertion thất bại. Nếu app dùng cookie HttpOnly, browser request context phải chia sẻ cookie jar đúng cách; nếu không, hãy dùng browser page để gọi endpoint được bảo vệ hoặc helper đã được kiểm chứng.

### 10.4 Pseudocode kiểm tra atomic consume

Ví dụ sau minh họa ý tưởng kiểm tra hai request đồng thời dùng cùng một challenge. Nó không quy định API hay cách lưu dữ liệu cụ thể.

~~~java
@Test
void challengeChiDuocChapNhanMotLan() throws Exception {
    Challenge challenge = fixtures.validChallengeFor(account);

    CompletableFuture<AuthResult> first = async(
        () -> authService.verify(challenge.id(), validAssertion(challenge))
    );
    CompletableFuture<AuthResult> second = async(
        () -> authService.verify(challenge.id(), validAssertion(challenge))
    );

    List<AuthResult> results = List.of(first.get(), second.get());

    assertThat(results.stream().filter(AuthResult::accepted).count())
        .isEqualTo(1);
    assertThat(sessionRepository.countAuthenticatedFor(account.id()))
        .isEqualTo(1);
}
~~~

Test cần tạo đúng điều kiện đồng thời; chỉ gọi hai hàm tuần tự không chứng minh race safety. Có thể dùng barrier/latch trong test integration để hai request cùng tới điểm consume. Chỉ assert một kết quả accepted là chưa đủ nếu hệ thống có side effect trùng lặp; kiểm tra thêm session, token, challenge state và audit event.

## 11. Kiểm tra response, UI và trải nghiệm phục hồi

Thông báo lỗi nên giúp người dùng biết bước tiếp theo mà không tiết lộ dữ liệu nhạy cảm. Cần kiểm tra:

- Nội dung không tiết lộ email có tồn tại hay account đang bị khóa nếu policy yêu cầu chống enumeration.
- Người dùng biết khi nào có thể thử lại, khi nào cần dùng recovery hoặc liên hệ hỗ trợ.
- Nút retry không gửi lại request nhiều lần do double click.
- Loading state kết thúc khi timeout; không giữ màn hình chờ vô hạn.
- Khi MFA provider lỗi, UI không gợi ý rằng người dùng nhập sai mã.
- Fallback method chỉ xuất hiện nếu account và policy cho phép.
- Error page không hiển thị stack trace, SQL error, provider response hoặc token.
- Redirect sau đăng nhập không đưa người dùng tới URL ngoài allowlist.
- Khi session hết hạn, client xóa trạng thái local phù hợp và quay về flow an toàn.

Nếu response được chuẩn hóa để chống enumeration, test không nên yêu cầu các chuỗi lỗi khác nhau cho từng trường hợp. Có thể xác minh nội dung công khai giống nhau, còn reason code chi tiết được ghi ở audit nội bộ.

## 12. Audit, log và telemetry trong flow thất bại

Một hệ thống không thể vận hành an toàn nếu mọi lỗi chỉ hiện thành một dòng “login failed”. Cần có event đủ để phân tích nhưng không chứa bí mật.

Một event kiểm thử có thể có các thuộc tính:

~~~json
{
  "event": "authentication.denied",
  "subject_ref": "test-subject-42",
  "tenant_ref": "school-a",
  "method": "totp",
  "reason_code": "MFA_CODE_INVALID",
  "outcome": "denied",
  "correlation_id": "test-correlation-91",
  "occurred_at": "2030-04-05T10:15:30Z"
}
~~~

Đây là schema minh họa. Dùng pseudonymous reference hoặc ID test phù hợp với chính sách dữ liệu. Không ghi password, OTP, token, cookie, challenge secret, recovery URL hoặc toàn bộ assertion.

Kiểm thử audit nên xác minh:

- Có event cho các quyết định quan trọng như deny, lockout, revoke, recovery và identity link.
- Reason code nội bộ phân biệt được lỗi credential, policy và dependency.
- Correlation ID nối được các bước qua gateway, auth service và provider adapter.
- Timestamp có timezone và đủ chính xác để dựng lại thứ tự sự kiện.
- Không có duplicate event ngoài hợp đồng khi retry.
- Audit pipeline lỗi được xử lý theo policy; không âm thầm bỏ mất event bắt buộc.
- Log redaction áp dụng cả exception, request body, trace attribute và telemetry exporter.

Không nên dùng số lượng log line làm bằng chứng duy nhất. Một event có thể được ghi hai lần do retry hoặc chuyển tiếp; test phải hiểu semantics của event và idempotency key.

## 13. Ma trận kiểm thử gợi ý

Ma trận dưới đây có thể dùng làm backlog ban đầu. Chọn các ca phù hợp với phương thức xác thực được sản phẩm hỗ trợ.

| ID | Flow | Tình huống | Kết quả bắt buộc |
|---|---|---|---|
| F-01 | Password | Password sai | Không token/session |
| F-02 | Password | Account không tồn tại | Không enumeration theo policy |
| F-03 | Password | Account disabled | Từ chối theo policy |
| F-04 | Password | Verifier timeout | Fail closed, telemetry vận hành |
| F-05 | Password | Nhiều lần thử sai | Rate limit/lockout đúng policy |
| F-06 | MFA | OTP sai | Không hoàn tất authentication |
| F-07 | MFA | OTP hết hạn | Challenge hết hạn bị từ chối |
| F-08 | MFA | OTP replay | Không consume lần hai |
| F-09 | MFA | Provider timeout | Không bypass MFA |
| F-10 | MFA | Hai request cùng OTP | Tối đa một lần thành công |
| F-11 | Passkey | Sai origin hoặc RP ID | Assertion bị từ chối |
| F-12 | Passkey | Sai challenge | Assertion bị từ chối |
| F-13 | Passkey | Assertion replay | Không tạo session thứ hai |
| F-14 | Certificate | Certificate hết hạn | Từ chối |
| F-15 | Certificate | Revocation service lỗi | Theo policy fail closed/degraded |
| F-16 | Token | Sai issuer/audience | Resource server từ chối |
| F-17 | Token | Sai signature hoặc key | Không chấp nhận token |
| F-18 | OIDC | State/nonce/PKCE sai | Callback không tạo session |
| F-19 | Session | Session store timeout | Không cấp quyền từ trạng thái không rõ |
| F-20 | Refresh | Refresh token replay | Phát hiện reuse theo policy |
| F-21 | Identity link | External subject đã liên kết | Không chiếm hoặc ghi mapping trùng |
| F-22 | Identity link | Email trùng nhưng chưa verified | Không tự động link |
| F-23 | Recovery | Token hết hạn hoặc sai purpose | Không đổi credential |
| F-24 | Recovery | Hai request cùng token | Một lần consume tối đa |
| F-25 | Recovery | Gửi notification lỗi | Trạng thái và retry theo hợp đồng |
| F-26 | Dependency | Timeout sau commit | Retry không tạo side effect trùng |
| F-27 | Policy | Cần step-up | Không cho thao tác nhạy cảm đi tiếp |
| F-28 | Audit | Event sink lỗi | Xử lý theo mức đảm bảo audit |
| F-29 | Tenant | Credential thuộc tenant khác | Không truy cập chéo tenant |
| F-30 | Session | Logout rồi dùng lại cookie | Request bị từ chối |

Mỗi hàng nên được mở rộng thành test case có fixture, bước thực hiện, assertion, cleanup và liên kết tới yêu cầu bảo mật. Có thể gắn nhãn mức rủi ro để ưu tiên các ca có khả năng dẫn tới account takeover, cross-tenant access hoặc cấp token ngoài ý muốn.

## 14. Cách tiêm lỗi có kiểm soát

Fault injection chỉ có giá trị khi test biết lỗi được kích hoạt ở đâu và có thể tái hiện. Một số cách thường dùng:

- Test adapter cho MFA/IdP trả timeout hoặc response sai schema.
- Proxy trong môi trường test cắt kết nối ở một thời điểm xác định.
- Database test fixture làm transaction rollback hoặc gây lỗi constraint.
- Clock test dịch qua thời điểm hết hạn.
- Hook chỉ dành cho test làm chậm hoặc fail một bước trước/sau commit.
- Test key set chứa key thiếu, key cũ hoặc chữ ký không hợp lệ.
- Rate limiter với ngưỡng thấp trong profile test.
- Barrier/latch để đồng bộ request cạnh tranh.

Các hook fault injection phải bị giới hạn trong test profile, không thể kích hoạt từ request public và không được bật trong production. Test cần ghi lại cấu hình fault và correlation ID để người khác tái hiện.

Không nên dùng cách phá mạng hoặc kill process tùy tiện trên môi trường dùng chung. Cô lập dependency và phạm vi ảnh hưởng trước khi chạy test chaos. Một test nhỏ, có điều kiện lỗi xác định, thường cung cấp bằng chứng tốt hơn một lần làm hệ thống chập chờn không rõ nguyên nhân.

## 15. Đọc kết quả và tìm nguyên nhân

Khi test thất bại, điều tra theo thứ tự của flow:

1. **Request:** client gửi đúng method, payload, cookie, origin, state và correlation ID chưa?
2. **Gateway:** request có bị rate limit, rewrite header hoặc route sai không?
3. **Authentication service:** state machine đang ở bước nào? Quyết định là deny hay temporary failure?
4. **Verifier/provider:** kết quả trả về có đúng subject, challenge và transaction không?
5. **Policy:** account, tenant, assurance và risk context có được đọc từ nguồn tin cậy không?
6. **Token/session:** có artifact nào được tạo trước khi flow hoàn tất không?
7. **Persistence:** transaction có commit một phần hoặc kết quả commit không rõ không?
8. **Audit:** event có reason code và correlation ID đúng không?

Dùng trace và log đã redaction. Không yêu cầu người dùng gửi password, OTP, cookie, token hoặc recovery link để debug. Nếu cần payload, tạo payload tổng hợp từ fixture test và loại bỏ bí mật trước khi đính kèm.

Một test flaky thường xuất phát từ clock thật, dữ liệu dùng chung, request cạnh tranh không được đồng bộ, dependency sandbox không ổn định hoặc cleanup thiếu. Hãy làm cho thời gian, fixture và fault deterministic trước khi tăng retry cho test runner. Retry test runner nhiều lần có thể che một race condition thật.

## 16. Đưa flow thất bại vào CI/CD

Một pipeline thực tế có thể chia theo tốc độ và mức phụ thuộc:

- Mỗi commit: unit test cho policy, expiry, token validation và state transition.
- Pull request: integration test với database, session store và adapter giả lập.
- Build chính: E2E cho các flow thất bại có rủi ro cao như MFA deny, passkey replay, refresh reuse và recovery token consume.
- Theo lịch hoặc trước release lớn: kiểm thử concurrency, key rotation, dependency timeout và phục hồi.
- Sau triển khai theo canary: synthetic test bằng tài khoản riêng và credential test được quản lý.

Không chạy test tạo khóa account hoặc gửi notification thật trên production. Synthetic test production phải có account, tenant, endpoint và dữ liệu được phê duyệt riêng; cần cleanup và alert để không gây nhầm lẫn với hành vi người dùng.

Test report nên hiển thị ID test, flow, môi trường, correlation ID và reason code đã redaction. Không đưa secret vào artifact CI, screenshot, video, trace hoặc biến môi trường được in ra log. Quản lý test secret qua secret store và xoay vòng khi có nghi ngờ bị lộ.

## 17. Lỗi thiết kế kiểm thử thường gặp

**Chỉ kiểm tra HTTP status.** Một response 401 không chứng minh không có session ngầm được tạo. Kiểm tra token, cookie, state và quyền truy cập tiếp theo.

**Chỉ kiểm tra thông báo UI.** UI có thể hiển thị lỗi trong khi API vẫn cấp quyền. Gọi endpoint được bảo vệ để xác nhận kết quả thực tế.

**Dùng mock cho mọi dependency.** Mock có thể xác nhận logic cục bộ nhưng không phát hiện cấu hình issuer, audience, TLS, cookie, callback hoặc contract sai. Giữ một nhóm integration/E2E với cấu hình gần thực tế.

**Dùng sleep để kiểm tra expiry.** Sleep kéo dài pipeline và tạo test flaky. Dùng clock có thể điều khiển.

**Không kiểm tra side effect.** Một login bị từ chối vẫn có thể tạo session, gửi push approve nhầm hoặc ghi identity link. Kiểm tra các artifact liên quan.

**Chạy concurrency test tuần tự.** Hai lời gọi nối tiếp không tạo race. Dùng barrier để điều khiển điểm tranh chấp.

**Bỏ qua lỗi sau commit.** Timeout không có nghĩa transaction chưa thành công. Test cả trường hợp dependency đã commit nhưng response bị mất.

**Assert mọi lỗi đều có cùng một response.** Chống enumeration có thể yêu cầu response công khai thống nhất, nhưng sự cố vận hành cần được phân loại nội bộ để có thể khắc phục.

**In toàn bộ request/response khi test fail.** Điều này có thể làm lộ credential và token vào CI. Redact trước khi ghi report.

**Không dọn dữ liệu.** Session, challenge và lockout còn sót lại làm ảnh hưởng test khác. Fixture cần teardown an toàn ngay cả khi assertion lỗi.

## 18. Checklist trước khi hoàn thành một test case

- [ ] Có điều kiện đầu vào và trạng thái ban đầu xác định.
- [ ] Đã xác định trust boundary và dependency liên quan.
- [ ] Lỗi được kích hoạt một cách deterministic.
- [ ] Response UI/API khớp hợp đồng.
- [ ] Principal không được xác thực hoặc nâng assurance ngoài ý muốn.
- [ ] Không có access token, refresh token, cookie hoặc session trái phép.
- [ ] Challenge, OTP, authorization code hoặc recovery token có trạng thái đúng.
- [ ] Không có side effect trùng lặp hoặc mapping danh tính sai.
- [ ] Retry và request đồng thời được kiểm tra khi có liên quan.
- [ ] Audit event có reason code và correlation ID phù hợp.
- [ ] Log, trace, screenshot và test report không chứa bí mật.
- [ ] Test có cleanup và chạy độc lập với fixture của test khác.
- [ ] Có ít nhất một assertion chứng minh endpoint được bảo vệ vẫn từ chối truy cập.

## 19. Bài tập áp dụng

### Bài tập A: OTP bị phát lại

Một người dùng gửi OTP hợp lệ. Server trả thành công nhưng response bị mất trên đường truyền. Client gửi lại cùng request. Hãy xác định:

1. Server cần nhận diện request retry bằng dữ liệu nào?
2. Nếu lần đầu đã tiêu thụ OTP thì lần hai nên trả kết quả nào?
3. Có được tạo hai session không?
4. Audit event được ghi một hay hai lần theo semantics của hệ thống?
5. Test cần tiêm timeout ở thời điểm nào để chứng minh hành vi?

Kết quả mong đợi của bài tập là một test có thể chạy lặp lại, xác nhận chỉ có một giao dịch xác thực và không tạo side effect trùng lặp.

### Bài tập B: IdP timeout sau khi callback

Identity provider đã xử lý authorization code nhưng callback của ứng dụng bị timeout trước khi lưu local session. Người dùng thử lại callback cũ.

Hãy mô tả cách test xác minh code không thể dùng lại, state/nonce được ràng buộc, local session không bị tạo hai lần và người dùng nhận được hướng phục hồi phù hợp. Phân biệt trường hợp IdP chưa xử lý code với trường hợp code đã được consume.

### Bài tập C: Recovery cạnh tranh

Hai tab trình duyệt cùng mở một recovery link và đồng thời gửi yêu cầu đổi password. Thiết kế test dùng barrier để hai request tranh chấp. Xác định trạng thái cuối của recovery token, password hash, session cũ và audit event. Nêu cách kiểm tra account không bị chuyển sang trạng thái nửa vời.

### Bài tập D: Dependency MFA ngừng hoạt động

MFA provider trả timeout. Product muốn cho người dùng tiếp tục bằng phương thức khác nếu account đã đăng ký passkey.

Thiết kế policy và test để chứng minh fallback chỉ hiện với account đủ điều kiện, passkey vẫn được xác minh đầy đủ, không có đường bỏ qua MFA cho account không có phương thức thay thế và audit ghi đúng phương thức cuối cùng.

## 20. Câu hỏi tự kiểm tra

1. Vì sao một test chỉ assert HTTP 401 chưa đủ để chứng minh login thất bại an toàn?
2. Phân biệt credential sai với verifier timeout. Hai trường hợp cần khác nhau ở telemetry nội bộ như thế nào?
3. Vì sao challenge phải ràng buộc với subject, transaction và thời hạn?
4. Làm thế nào để chứng minh OTP hoặc recovery token chỉ được consume một lần khi có hai request đồng thời?
5. Vì sao không được coi timeout là bằng chứng rằng dependency chưa thực hiện thao tác?
6. Trong WebAuthn, những giá trị nào cần được xác minh ngoài chữ ký assertion?
7. Vì sao decode JWT không tương đương xác minh JWT?
8. Khi refresh token cũ bị replay, những artifact nào cần kiểm tra?
9. Vì sao email trùng không phải lúc nào cũng đủ để tự động liên kết hai danh tính?
10. Những bí mật nào tuyệt đối không nên xuất hiện trong log và test report?
11. Khi audit sink không hoạt động, cần dựa vào yêu cầu nào để quyết định flow có được hoàn tất?
12. Làm thế nào để phân biệt một test flaky do clock với một lỗi race condition thực sự?

## 21. Tiêu chí hoàn thành

Một bộ kiểm thử flow thất bại có chất lượng cần chứng minh được ba lớp:

- **Đúng quyết định:** credential, challenge, context và policy không hợp lệ đều bị từ chối; lỗi dependency không biến thành chấp nhận.
- **Đúng trạng thái:** không có token, session, identity link hoặc recovery mutation trái phép; thao tác dùng một lần và retry có semantics rõ ràng.
- **Đủ bằng chứng:** UI/API, state, side effect và audit có thể đối chiếu bằng correlation ID; bí mật được bảo vệ trong toàn bộ test lifecycle.

Khi thêm một phương thức xác thực mới, hãy bổ sung cả flow thành công và các flow thất bại tương ứng: credential sai, hết hạn, revoke, replay, context mismatch, dependency failure, retry và recovery. Kiểm thử thất bại cần được duy trì cùng với code và policy vì thay đổi ở token issuer, session store, MFA provider hoặc account recovery đều có thể làm thay đổi hành vi của chúng.

Một test case được coi là hoàn tất khi người khác có thể đọc điều kiện đầu vào, chạy lại lỗi, quan sát trạng thái cuối và giải thích vì sao kết quả đó giữ được ranh giới tin cậy của hệ thống.

