# MFA re enrollment — Đăng ký lại phương tiện xác thực đa yếu tố

## 1. Mục tiêu và phạm vi

Trong chương **MFA Recovery** của module **SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY**, đăng ký lại MFA là quá trình thiết lập một authenticator hoặc binding thay thế sau khi người dùng đổi thiết bị, mất phương tiện xác thực hay xử lý một sự cố bảo mật.

Quá trình này cần giải quyết hai câu hỏi độc lập:

1. Người đang thao tác có quyền thay đổi phương tiện xác thực của tài khoản không?
2. Phương tiện mới đã được thiết lập đúng, dùng được và đáp ứng chính sách chưa?

Một mã TOTP mới đúng chỉ giúp chứng minh khả năng sử dụng secret mới. Nó không tự chứng minh người trình mã có quyền với tài khoản cũ. Nếu bỏ qua sự khác biệt này, đối tượng có mật khẩu hoặc session bị đánh cắp có thể đăng ký MFA của họ và khóa chủ tài khoản ra ngoài.

Bài học giúp người đọc:

- Phân biệt đăng ký lại, thêm dự phòng, vô hiệu hóa yếu tố và khôi phục tài khoản.
- Thiết kế quyền đăng ký lại có phạm vi, thời hạn và khả năng chống dùng lại.
- Quản lý candidate mới trước khi kích hoạt.
- Thay thế TOTP, WebAuthn hoặc binding thiết bị mà không mở đường bỏ qua MFA.
- Kiểm soát thu hồi yếu tố cũ, recovery code, session và thông báo.
- Xử lý thất bại, retry và nhiều yêu cầu cạnh tranh.

Các trạng thái, trường dữ liệu và endpoint trong bài là thiết kế minh họa. Thời hạn và tổ hợp bằng chứng phải được xác định theo sản phẩm. Bài học không tuyên bố một luồng đạt AAL cụ thể chỉ vì có MFA hoặc có passkey.

## 2. Những thao tác cần phân biệt

| Thao tác | Mục đích | Kết quả trực tiếp |
| --- | --- | --- |
| Thêm authenticator dự phòng | Có thêm một phương tiện đã được chấp nhận | Binding mới được thêm, binding cũ có thể vẫn hoạt động |
| Đăng ký lại hoặc thay thế | Chuyển sang secret, credential hoặc binding mới | Phương tiện thay thế được kích hoạt theo quyết định |
| Ngừng hoặc thu hồi authenticator | Chặn phương tiện không còn tin cậy | Phương tiện đó không còn được dùng để xác thực trong phạm vi tương ứng |
| Tắt yêu cầu MFA | Thay đổi chính sách đăng nhập | Có thể làm giảm yêu cầu bảo vệ tài khoản |
| Khôi phục tài khoản | Lấy lại quyền khi không còn xác thực được theo yêu cầu | Có quyền giới hạn để thiết lập lại phương tiện theo chính sách |

Ví dụ, chuyển ứng dụng TOTP sang điện thoại khác bằng cùng một seed vẫn giữ cùng bí mật xác thực. Thao tác này không loại bỏ nguy cơ người khác đang giữ bản seed cũ.

Nếu nghi seed đã lộ, đăng ký lại cần dùng seed mới và xử lý binding cũ. Việc chỉ đổi tên thiết bị trong giao diện không xoay vòng bí mật.

Tương tự, đặt lại mật khẩu không tự thu hồi TOTP, passkey, session hoặc recovery code. Mỗi loại có trạng thái và cơ chế vô hiệu hóa riêng.

Một thiết kế dễ sai là:

~~~text
Tắt MFA
Cho người dùng đăng nhập bằng mật khẩu
Nhắc người dùng bật lại MFA khi thuận tiện
~~~

Thiết kế đó tạo khoảng thời gian có thể dùng tài khoản bằng điều kiện yếu hơn. Luồng thay thế nên quản lý candidate và quyền recovery trực tiếp, thay vì biến việc tắt MFA thành bước trung gian.

## 3. Xác định quyền đăng ký lại trước khi tạo phương tiện mới

### 3.1. Người dùng còn authenticator đáp ứng yêu cầu

Đây là nhánh thay đổi có xác thực lại:

1. Người dùng có session phù hợp để bắt đầu.
2. Server yêu cầu một sự kiện xác thực lại đáp ứng chính sách cho hành động thay MFA.
3. Kết quả được gắn với đúng tài khoản, mục đích và thời điểm.
4. Server cấp quyền giới hạn cho một thao tác đăng ký lại.

Một session cũ không tự có quyền thay mọi yếu tố. OWASP xem thay phương tiện MFA là hành động rủi ro cao, khuyến nghị xác thực lại và không chỉ dựa vào session đang hoạt động. [OWASP, Changing MFA Factors](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#changing-mfa-factors)

Với hệ thống áp dụng NIST SP 800-63B-4, binding bổ sung có yêu cầu về mức xác thực và thông báo độc lập với giao dịch binding. Cần đối chiếu quy tắc cụ thể thay vì mặc định “biết mật khẩu là đủ”. [NIST SP 800-63B-4, Authenticator Binding](https://pages.nist.gov/800-63-4/sp800-63b/events/#bind)

### 3.2. Người dùng đã mất yếu tố bắt buộc

Không thể yêu cầu một yếu tố đã mất làm điều kiện duy nhất để bắt đầu recovery. Người dùng cần đi qua phương thức khôi phục được sản phẩm hỗ trợ, chẳng hạn một tổ hợp bằng chứng đã thiết lập từ trước hoặc quy trình xác minh có thẩm quyền.

Kết quả thành công của nhánh đó nên cấp quyền cho hành động cụ thể như:

~~~text
REENROLL_MFA
    account: A
    allowed_method: TOTP
    replace: factor F1
    recovery_case: R1
    expires_at: thời điểm do chính sách quyết định
~~~

Quyền này chưa phải session đầy đủ của ứng dụng. Nó không mặc nhiên cho phép đọc dữ liệu nhạy cảm, đổi email, thêm API key hoặc xóa mọi phương tiện khác.

Một lần nhận mã ở email mới tự khai chỉ chứng minh quyền tiếp cận email mới. Server vẫn cần bằng chứng được chính sách chấp nhận để thay binding của tài khoản cũ.

### 3.3. Quản trị viên hoặc hỗ trợ thực hiện thay

Quyền tác nghiệp cần xác định rõ:

- Ai được khởi tạo, ai được phê duyệt và ai được hoàn tất.
- Tài khoản, tenant và loại authenticator thuộc phạm vi nào.
- Bằng chứng nào cho phép hành động.
- Có cần phân tách nhiệm vụ đối với tài khoản đặc quyền hay không.
- Hành động nào cần được chủ tài khoản xác nhận qua một đường phù hợp.

Nhân viên hỗ trợ không cần xem seed TOTP hoặc thu PIN thiết bị để hoàn tất quy trình. Việc có quyền đọc ticket không tự tạo quyền thay MFA.

## 4. Các bất biến bảo mật cần giữ

1. **Quyền thay MFA phải được xác minh trước khi cấp khả năng thiết lập có tác động lên tài khoản.**
2. **Candidate chưa active chỉ được dùng trong endpoint phục vụ enrollment.**
3. **Xác minh phương tiện mới không thay thế xác minh quyền tài khoản.**
4. **Candidate, proof và quyết định hoàn tất phải thuộc cùng tài khoản, thao tác và phiên bản.**
5. **Yếu tố đã bị thu hồi không tự hoạt động lại khi enrollment mới thất bại.**
6. **Một quyền dùng một lần không tạo được nhiều thay đổi độc lập ngoài phạm vi đã cấp.**
7. **Thay đổi tập authenticator không tự nâng mức bảo đảm của session đang có.**
8. **Khi không còn phương tiện đáp ứng yêu cầu, đường đăng nhập không tự bỏ yêu cầu MFA.**

Ví dụ, tài khoản chỉ còn một factor bị ngừng do sự cố có thể chuyển sang trạng thái cần recovery. Đây là trạng thái không đáp ứng đăng nhập thông thường, không phải trạng thái cho phép đăng nhập chỉ bằng mật khẩu.

Không nên suy ra điều kiện đăng nhập từ một biểu thức như:

~~~text
nếu không tìm thấy factor ACTIVE:
    bỏ qua bước MFA
~~~

Yêu cầu bảo vệ tài khoản là chính sách riêng. Việc thiếu phương tiện để đáp ứng chính sách phải dẫn đến nhánh xử lý phù hợp.

## 5. Mô hình dữ liệu và vòng đời

### 5.1. Tách ba đối tượng

| Đối tượng | Dữ liệu minh họa | Vai trò |
| --- | --- | --- |
| Quyền đăng ký lại | account, purpose, scope, evidence ref, expiry, state | Cho phép một hành động được xác định |
| Thao tác enrollment | operation ID, target factor, snapshot version, policy version | Theo dõi tiến trình thay thế |
| Candidate factor | candidate ID, method, material ref, generation, state, proof ref | Đại diện phương tiện mới đang thiết lập |

`material ref` có thể trỏ đến seed được mã hóa hoặc bản ghi public key, tùy loại factor. Không dùng một trường secret chung rồi áp cùng cơ chế lưu cho mọi phương thức.

Một mô hình minh họa:

~~~text
ReEnrollmentOperation
    id
    account_id
    tenant_id
    authorization_id
    target_factor_id
    target_factor_version
    expected_factor_set_version
    policy_version
    candidate_id
    candidate_generation
    state
    expires_at

CandidateFactor
    id
    operation_id
    account_id
    method
    material_reference
    generation
    state
    proof_reference
    proof_expires_at
~~~

Server xác định `account_id` từ context đã được cấp quyền và binding đã lưu. Thay một giá trị trong request không được chuyển operation sang tài khoản khác.

### 5.2. Vòng đời của candidate

~~~mermaid
stateDiagram-v2
    [*] --> PENDING_UNVERIFIED
    PENDING_UNVERIFIED --> PENDING_VERIFIED: Xác minh phương tiện mới
    PENDING_VERIFIED --> ACTIVE: Commit thay thế hợp lệ
    PENDING_UNVERIFIED --> EXPIRED
    PENDING_VERIFIED --> EXPIRED
    PENDING_UNVERIFIED --> CANCELLED
    PENDING_VERIFIED --> CANCELLED
    ACTIVE --> REVOKED: Quyết định thu hồi
    EXPIRED --> [*]
    CANCELLED --> [*]
    REVOKED --> [*]
~~~

`PENDING_VERIFIED` nghĩa là đã có kết quả kiểm tra candidate, chưa có nghĩa nó được dùng để đăng nhập thông thường. Query phục vụ login phải kiểm tra trạng thái active và mọi điều kiện chính sách liên quan.

Nếu thay seed, public key hoặc thiết bị candidate, cần tăng generation hoặc tạo candidate mới. Proof của generation cũ không được chuyển sang generation mới.

### 5.3. Quyền đăng ký lại có thể được giữ cho một operation

Một thiết kế dùng vòng đời:

~~~text
ISSUED -> BOUND_TO_OPERATION -> CONSUMED
                         -> EXPIRED hoặc REVOKED
~~~

Khi quyền được gắn vào operation, nó không còn được dùng để mở một operation độc lập khác. Các request tiếp theo được kiểm tra theo đúng operation đã gắn.

Cách chia trạng thái này là lựa chọn thiết kế để hỗ trợ nhiều bước. Không yêu cầu client gửi lại cùng token như một “quyền mới” sau mỗi lần bấm tiếp tục.

## 6. Luồng đăng ký lại tổng quát

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant C as Client
    participant A as Dịch vụ cấp quyền
    participant E as Dịch vụ enrollment
    participant D as Kho trạng thái
    U->>C: Chọn thay phương tiện MFA
    C->>A: Xác thực lại hoặc hoàn tất recovery
    A->>D: Lưu quyền có phạm vi và thời hạn
    A-->>C: Context đăng ký lại giới hạn
    C->>E: Bắt đầu operation
    E->>D: Gắn quyền với operation và candidate
    E-->>C: Thông tin thiết lập theo phương thức
    U->>C: Thiết lập và trình bằng chứng từ phương tiện mới
    C->>E: Xác minh candidate
    E->>D: Lưu proof gắn với generation
    C->>E: Xác nhận hoàn tất
    E->>D: Kiểm tra lại và commit thay thế
    D-->>E: Kết quả đã lưu
    E-->>C: Trạng thái hoàn tất
    E->>D: Xử lý sự kiện qua outbox đã ghi cùng commit
~~~

Trong mô hình này, bằng chứng được kiểm tra trước và quyết định commit được kiểm tra lại ở thời điểm thay đổi có hiệu lực. Một kết quả approval cũ không đủ nếu account, candidate hoặc policy đã thay đổi ngoài phạm vi cho phép.

Nếu yếu tố cũ còn an toàn và đang được thay theo kế hoạch, có thể giữ nó đến khi candidate mới sẵn sàng. Nếu có căn cứ mất hoặc lộ, biện pháp ngừng yếu tố cũ cần được thực hiện theo quy trình sự cố, không chờ luồng trên hoàn tất.

NIST yêu cầu xử lý kịp thời authenticator đã bị compromise. Điều kiện xác minh báo mất và phạm vi tác động vẫn cần được kiểm soát. [NIST SP 800-63B-4, Loss, Theft, Damage, and Compromise](https://pages.nist.gov/800-63-4/sp800-63b/events/#lost)

## 7. Đăng ký lại TOTP

### 7.1. Cấp seed mới cho candidate

Với thay thế do nghi lộ hoặc mất kiểm soát seed, server tạo seed ngẫu nhiên mới. Candidate ban đầu ở trạng thái pending và có thời hạn thiết lập.

Luồng minh họa:

1. Xác minh quyền đăng ký lại.
2. Tạo operation và candidate.
3. Sinh seed mới bằng nguồn ngẫu nhiên mật mã.
4. Lưu seed được bảo vệ cùng cấu hình thuật toán.
5. Cung cấp dữ liệu thiết lập qua kênh được bảo vệ cho đúng context.
6. Người dùng thêm cấu hình vào ứng dụng authenticator.
7. Người dùng trình mã để server kiểm tra candidate.
8. Server chỉ kích hoạt sau quyết định commit.

TOTP dựa trên shared secret và bước thời gian. Hai phía phải thống nhất tham số; RFC 6238 cũng yêu cầu bảo vệ key và chống chấp nhận lại OTP đã được xác minh thành công. [RFC 6238, Algorithm Requirements và Security Considerations](https://www.rfc-editor.org/rfc/rfc6238.html)

Không lấy mã TOTP sáu chữ số làm seed. Mã hiển thị là đầu ra ngắn hạn, không phải bí mật gốc.

### 7.2. QR và dữ liệu thiết lập là dữ liệu nhạy cảm

QR thiết lập TOTP thường chứa đủ dữ liệu để một ứng dụng tạo mã. Người có bản sao seed có thể tiếp tục tạo mã ngay cả khi họ không cầm điện thoại ban đầu.

Vì vậy, thiết kế cần:

- Chỉ phục vụ dữ liệu thiết lập cho operation còn hiệu lực và đúng người có quyền.
- Tránh để seed xuất hiện trong URL công khai, access log, analytics hoặc nội dung ticket.
- Ngăn cache không phù hợp trên response chứa dữ liệu thiết lập.
- Giảm mã bên thứ ba trên trang có seed.
- Xử lý đóng, hết hạn và hủy operation để bí mật pending không tồn tại vô thời hạn.

Hiển thị tên thiết bị chỉ giúp người dùng nhận diện binding. Đổi tên hoặc scan lại QR cũ không làm seed cũ hết hiệu lực.

### 7.3. Lưu seed khác với lưu recovery code

Verifier TOTP cần dùng shared seed để tính giá trị mong đợi. Lưu duy nhất một hash một chiều của seed thường không đáp ứng công việc đó.

Seed cần được mã hóa hoặc quản lý trong cơ chế xác minh được bảo vệ, với quyền truy cập tối thiểu. OWASP phân biệt seed TOTP lâu dài với OTP ngắn hạn và khuyến nghị bảo vệ seed bằng mã hóa, chẳng hạn qua KMS hoặc HSM phù hợp. [OWASP, TOTP Seeds and Validation Window](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#totp-seeds-and-validation-window)

Một recovery code ngẫu nhiên có thể được xác minh bằng cách đối chiếu biểu diễn được bảo vệ của code. Hai loại bí mật này có vòng đời và nhu cầu sử dụng khác nhau.

### 7.4. Xác minh mã và ghi nhận việc đã dùng

Server kiểm tra mã theo seed, cấu hình và cửa sổ thời gian đã chọn cho candidate. Hạn mức thử cần tính theo operation, tài khoản và nguồn phù hợp; tạo lại candidate không được làm mất toàn bộ hạn mức trước đó.

Kết quả có thể ghi:

~~~text
candidate_id = C2
generation = 3
proof_purpose = VERIFY_NEW_TOTP_FOR_REENROLLMENT
accepted_time_step = S
verified_at = thời điểm kiểm tra
expires_at = thời điểm proof hết hiệu lực
~~~

Việc chấp nhận time step và lưu proof cần nhất quán để hai verifier không cùng chấp nhận một lần trình mã thành hai bằng chứng độc lập.

Khi candidate trở thành active, trạng thái chống replay phải được giữ. Mã đã dùng để xác minh enrollment không được tiếp tục dùng như một mã mới cho login trong cùng bước thời gian đã được tiêu thụ.

Retry của cùng request có thể trả proof đã lưu theo idempotency; đó là trả lại kết quả cũ, không phải chấp nhận OTP lần nữa.

Không tạo danh sách cấm vĩnh viễn cho mọi chuỗi sáu chữ số từng xuất hiện. Những chuỗi số có thể trùng trong tương lai; trạng thái chống replay cần gắn với factor, phiên bản secret và bước thời gian phù hợp.

### 7.5. Xử lý lệch giờ và scan nhầm

Một mã không đúng có thể đến từ scan nhầm tài khoản, cấu hình không khớp hoặc lệch giờ. Giao diện nên giúp kiểm tra những điều này mà không yêu cầu nhân viên xem seed.

Không mở rộng cửa sổ chấp nhận vô hạn để enrollment thành công. Nếu cần cơ chế điều chỉnh lệch giờ, phải có giới hạn và cách theo dõi riêng.

Tạo hai mã liên tiếp có thể là một lựa chọn kiểm tra của sản phẩm, nhưng không phải một yêu cầu chung cho mọi luồng TOTP. Quan trọng là kiểm tra đúng seed, cấu hình và trạng thái của candidate đã được cấp quyền.

## 8. Đăng ký lại WebAuthn, khóa bảo mật hoặc thiết bị push

### 8.1. WebAuthn dùng ceremony mới cho credential thay thế

Server phát challenge đăng ký và gắn context nghiệp vụ với đúng account, operation, candidate và thời hạn. Phản hồi phải được verifier WebAuthn kiểm tra theo quy trình đầy đủ.

Các kiểm tra giao thức bao gồm type ceremony, challenge, origin, RP ID và các yêu cầu về authenticator, thuật toán hoặc attestation tương ứng. Dữ liệu server tự lưu về quyền enrollment vẫn phải được kiểm tra riêng. [W3C WebAuthn, Registering a New Credential](https://www.w3.org/TR/webauthn-3/#sctn-registering-a-new-credential)

Không thay các giá trị chuẩn như `webauthn.create` bằng tên nghiệp vụ `REENROLL_MFA`. Tên nghiệp vụ là context được quản lý bên phía server.

Credential ID mới không được ghi đè binding của một tài khoản khác. Ràng buộc duy nhất trong phạm vi RP và kiểm tra quyền account phải được thực thi ở tầng dữ liệu thích hợp.

### 8.2. Kiểm tra khả năng sử dụng là bước có mục đích riêng

Một thiết kế có thể giữ credential ở pending sau registration, rồi yêu cầu assertion riêng từ credential đó trước khi kích hoạt.

Endpoint thử candidate cần:

- Chấp nhận đúng candidate được phép trong operation.
- Dùng challenge mới, có phạm vi và chống dùng lại.
- Kiểm tra các yêu cầu xác thực theo chính sách.
- Ghi proof gắn với đúng public key và generation.
- Không cấp session ứng dụng đầy đủ chỉ vì assertion thử đã thành công.

Đây là lựa chọn kiểm tra khả năng sử dụng. Nó không thay thế verifier đăng ký và không chứng minh lại quyền sở hữu tài khoản cũ.

Nếu chính sách yêu cầu user verification hoặc loại thiết bị nhất định, lỗi tương thích không phải lý do tự hạ điều kiện. Sản phẩm cần hướng người dùng đến phương tiện phù hợp hoặc một nhánh được hỗ trợ.

### 8.3. Thiết bị push cần binding mật mã phù hợp

Một push token giúp định tuyến thông báo đến ứng dụng; biết push token không tự chứng minh quyền đăng ký thiết bị cho tài khoản.

Luồng binding cần làm rõ thiết bị nào được gắn, người nào đang phê duyệt và bằng chứng nào xác nhận quyền kiểm soát khóa hoặc bí mật của thiết bị.

QR hoặc mã ghép nối cần gắn với operation cụ thể, có thời hạn và trạng thái dùng một lần. Phê duyệt trên màn hình phải chỉ rõ hành động thêm hoặc thay phương tiện MFA.

Không phát push liên tục cho thiết bị cũ để ép người dùng bấm chấp nhận. Nếu thiết bị cũ không còn dùng được, chuyển sang nhánh recovery có chính sách, thay vì coi không phản hồi là đồng ý.

## 9. Thay kênh nhận mã và đánh giá phương tiện mới

### 9.1. Xác nhận số mới và quyền đổi số là hai kiểm tra

Nếu sản phẩm hỗ trợ thay số điện thoại dùng cho xác thực, một mã gửi đến số mới chỉ kiểm tra khả năng tiếp cận số đó.

Một luồng phù hợp cần cả:

1. Bằng chứng cho phép thay binding của tài khoản.
2. Bằng chứng phương tiện mới hoạt động theo phương thức được hỗ trợ.

Số mới nên ở trạng thái pending trong quá trình kiểm tra. Không cập nhật nó thành địa chỉ recovery chính trước commit rồi gửi một token “xác minh quyền tài khoản” về chính số vừa được người yêu cầu khai.

Cách làm đó tự tạo bằng chứng vòng tròn: người ngoài cung cấp kênh của họ, xác nhận kênh của họ, rồi được hệ thống coi là chủ tài khoản.

### 9.2. Thay thế cần đáp ứng chính sách phương thức

Đăng ký thành công một phương tiện yếu hơn không tự cho phép thay một phương tiện mạnh hơn. Ví dụ, tài khoản đặc quyền có thể yêu cầu authenticator chống phishing; luồng recovery không được âm thầm đổi yêu cầu đó thành nhận SMS.

Cần đánh giá:

- Phương thức mới có được phép cho tài khoản và hành động không.
- Những đặc tính nào đã được xác minh, những đặc tính nào chỉ do client khai.
- Phương tiện mới có phụ thuộc vào thiết bị hoặc kho đang bị chiếm không.
- Nhánh recovery có cho phép thay đổi loại phương thức hay chỉ thay cùng loại.

Không suy ra mọi passkey đều có cùng mức bảo đảm hoặc mọi khóa rời đều có cùng khả năng user verification.

### 9.3. Chuẩn bị dự phòng cần xét phụ thuộc chung

TOTP mới, email recovery và mã dự phòng cùng nằm trên một điện thoại có thể cùng mất trong một sự cố. Một passkey mới được lưu vào kho đang bị chiếm cũng có thể tiếp tục nằm trong phạm vi kiểm soát của đối tượng tấn công.

Thiết kế cần xem xét tính độc lập của đường dự phòng và tình trạng môi trường đang nhận phương tiện mới. Số dòng tăng lên trong danh sách MFA không tự chứng minh tài khoản đã có dự phòng phù hợp.

## 10. Commit thay thế và thu hồi yếu tố cũ

### 10.1. Hai kế hoạch thay thế khác nhau

| Bối cảnh | Xử lý yếu tố cũ | Khi candidate mới thất bại |
| --- | --- | --- |
| Đổi thiết bị theo kế hoạch, yếu tố cũ còn an toàn | Có thể giữ đến thời điểm thay thế được chấp thuận | Giữ trạng thái cũ theo chính sách đã chọn |
| Mất, lộ hoặc có căn cứ không còn tin cậy | Ngừng hoặc thu hồi theo quyết định sự cố | Tiếp tục nhánh recovery; không tự bật lại yếu tố cũ |

Nếu cần một giai đoạn cùng hoạt động, đó phải là hành vi được quyết định rõ: thời hạn nào, phương tiện nào và ai có quyền kết thúc. Không để khoảng chồng lấn vô thời hạn chỉ vì việc dọn dẹp được giao cho một job chưa có bảo đảm.

Ngược lại, quyền tạo candidate không tự cho phép ngừng tất cả yếu tố đang hoạt động. Phạm vi target phải được kiểm tra riêng.

### 10.2. Transaction minh họa

Giả sử proof candidate đã được verifier kiểm tra và lưu an toàn. Bước commit cần kiểm tra lại trạng thái nghiệp vụ:

~~~text
BEGIN

Khóa account và các bản ghi liên quan theo thứ tự thống nhất
Đọc operation, authorization, target factor, candidate và proof

Kiểm tra:
    caller có context hợp lệ cho operation
    account, tenant, purpose và scope khớp nhau
    authorization đang gắn với chính operation này
    operation, authorization và proof chưa hết hiệu lực
    trạng thái hiện tại cho phép commit
    factor set version và target version đúng kỳ vọng
    candidate ID, generation và material reference chưa thay đổi
    proof thuộc đúng candidate và purpose
    phương thức mới đáp ứng chính sách áp dụng
    không có hold hoặc thay đổi bảo mật buộc đánh giá lại

Kích hoạt candidate
Thu hồi target thuộc phạm vi quyết định nếu chưa được xử lý
Tăng factor_set_version
Áp dụng quyết định session/recovery-code đã được cấp quyền
Tiêu thụ authorization và ghi kết quả operation
Đóng các challenge và context không còn cần thiết
Ghi audit và outbox

COMMIT
~~~

`factor_set_version` bảo vệ thay đổi tập authenticator. Nếu có cơ chế `security_epoch` để vô hiệu hóa session, việc tăng epoch cần theo quyết định session cụ thể, không mặc định đồng nhất hai khái niệm.

Nếu target đã bị ngừng do sự cố trước đó, operation cần làm việc với trạng thái và version đã được ghi nhận. Không yêu cầu target phải active để commit bằng cách phục hồi nó tạm thời.

Nếu version không còn khớp, trả kết quả cần tải lại hoặc đánh giá lại. Không tự bỏ kiểm tra chỉ để người dùng hoàn tất.

### 10.3. Không giữ transaction mở khi gọi dịch vụ ngoài

Việc gửi email, push hoặc gọi một nhà cung cấp chậm không nên kéo dài khóa dữ liệu trong transaction thay thế.

Audit và outbox có thể được ghi cùng thay đổi bảo mật. Consumer xử lý thông báo và đồng bộ sau commit, với retry có kiểm soát và khả năng chống xử lý lặp.

Nếu gửi thông báo lỗi sau khi commit thành công, không bật lại factor cũ để “rollback email”. Server cần giữ kết quả bảo mật đã commit, ghi nhận lỗi gửi và tiếp tục xử lý thông báo.

### 10.4. Hệ thống phân tán cần nhìn thấy trạng thái mới

Kích hoạt candidate hoặc thu hồi target ở một database chưa bảo đảm mọi verifier và cache lập tức thấy thay đổi.

Cơ chế triển khai cần bảo vệ:

- Đường login không dùng bản cache cũ để chấp nhận target đã bị thu hồi.
- Consumer không để sự kiện cũ ghi đè trạng thái mới hơn.
- Candidate chưa commit không xuất hiện như factor active.
- Verifier bắt buộc không khả dụng không dẫn đến bỏ qua MFA.

Nếu kiến trúc có độ trễ, phải xác định giới hạn và cách xử lý phù hợp với mức rủi ro. Giao diện chỉ nên báo tác động đã thực thi được.

## 11. Chống replay, cạnh tranh và retry

### 11.1. Các bí mật một lần có mục đích khác nhau

| Dữ liệu | Dùng để làm gì | Phạm vi chống dùng lại |
| --- | --- | --- |
| Recovery code | Cung cấp bằng chứng cho nhánh recovery | Code và lần sử dụng được ghi cho đúng hồ sơ |
| Quyền đăng ký lại | Cho phép thao tác thay thế | Authorization và operation đã gắn |
| Challenge WebAuthn | Gắn phản hồi vào một ceremony | Challenge, ceremony và context tương ứng |
| Mã TOTP | Chứng minh khả năng dùng shared seed | Factor, phiên bản seed và time step |
| Mã ghép nối thiết bị | Liên kết endpoint trong thao tác đã cấp quyền | Operation, mục đích và thời hạn |

Không tái sử dụng một token chung cho reset mật khẩu, đổi email và thay MFA chỉ vì các hành động cùng nằm trong một giao diện.

### 11.2. Recovery code đã dùng không cần trình lại để commit

Một code được chấp nhận để cấp quyền recovery cần được tiêu thụ và ghi nhận bằng thao tác nhất quán. Kết quả xác minh được gắn với hồ sơ và thời hạn.

Bước enrollment sau đó sử dụng kết quả được cấp quyền này. Nó không yêu cầu người dùng trình lại code đã bị đánh dấu dùng rồi.

Nếu hai request cùng trình một code, chỉ một kết quả cấp quyền được tạo theo chính sách. Không cho mỗi request lấy một quyền độc lập vì chúng cùng đọc trạng thái “chưa dùng” trước khi cập nhật.

### 11.3. Hai tab thay cùng một factor

Giả sử tab A và B đều bắt đầu với factor set version 10:

~~~text
Tab A:
    candidate CA
    expected version = 10

Tab B:
    candidate CB
    expected version = 10

Tab A commit:
    kích hoạt CA
    factor set version -> 11

Tab B commit:
    phát hiện version 11
    không dùng quyết định cũ để tiếp tục thay thế
~~~

Hệ thống có thể chỉ cho phép một operation đang hoạt động hoặc cho nhiều operation tồn tại nhưng phát hiện xung đột ở commit. Cả hai cách đều cần quy tắc rõ cho candidate và quyền còn lại.

Không để tab B thu hồi CA chỉ vì nó chọn thao tác “thay toàn bộ MFA” từ ảnh chụp trạng thái cũ.

### 11.4. Retry sau khi mất response

Nếu server đã commit mà client không nhận response, request lặp nên trả kết quả đã lưu của cùng operation.

Idempotency key cần gắn với account, operation, hành động và nội dung liên quan. Dùng lại cùng key với candidate khác phải bị phát hiện, không được trả thành công như thể đó là cùng yêu cầu.

Một endpoint đọc trạng thái có thể giúp client khôi phục giao diện sau lỗi mạng. Endpoint đó vẫn cần xác minh quyền; biết operation ID không tự cho phép đọc kết quả.

Không tạo seed mới, kích hoạt thêm factor hoặc gửi lại bí mật đã được đóng chỉ vì client bấm “thử lại”.

## 12. Quản lý bí mật, candidate bỏ dở và recovery code

### 12.1. Secret pending cũng cần được bảo vệ

Seed chưa active vẫn là bí mật. Nếu bị lộ rồi candidate được kích hoạt sau đó, đối tượng có thể có khả năng tạo mã.

Khi hủy hoặc hết hạn:

- Đánh dấu operation và candidate không còn dùng được.
- Vô hiệu hóa challenge và context tương ứng.
- Hủy proof không còn phù hợp.
- Xóa vật liệu bí mật pending theo cơ chế lưu trữ và retention đã chọn.
- Giữ metadata audit cần thiết mà không giữ seed hoặc token thô.

Một tiến trình dọn dẹp chạy chậm không được làm candidate hết hạn tiếp tục hợp lệ. Verifier phải kiểm tra thời hạn ở thời điểm sử dụng.

### 12.2. Tạo lại candidate phải vô hiệu hóa proof cũ

Nút “tạo QR mới” cần có hành vi rõ ràng. Nếu tạo seed mới, candidate generation thay đổi và mọi proof gắn với seed trước đó mất hiệu lực cho việc kích hoạt seed mới.

Không dùng hai cột độc lập:

~~~text
seed = seed mới nhất
verified = true từ lần xác minh seed cũ
~~~

Thay vào đó, proof cần gắn với đúng vật liệu và generation. Cùng một yêu cầu retry cũng không được âm thầm tạo generation mới.

### 12.3. Xoay vòng recovery code theo phạm vi sự cố

Sau đăng ký lại, sản phẩm có thể yêu cầu thiết lập lại đường recovery. Việc thay toàn bộ code cũ cần theo chính sách hoặc bằng chứng chúng có thể đã bị lộ.

Một cơ chế minh họa dùng `recovery_code_set_version`:

1. Chuẩn bị bộ mới bằng nguồn ngẫu nhiên phù hợp.
2. Lưu biểu diễn được bảo vệ để xác minh; không đưa code thô vào log.
3. Kích hoạt bộ mới và vô hiệu hóa bộ cũ bằng thay đổi nhất quán.
4. Hiển thị code mới trong context được cấp quyền.
5. Ghi nhận riêng trạng thái chuẩn bị đường recovery.

Nếu code cũ từng nằm trên điện thoại bị mất, phạm vi sự cố cần xét cả bộ code đó. Không giữ chúng chỉ vì TOTP đã được thay.

Nếu response hiển thị code mới bị mất, có thể cung cấp thao tác cấp bộ khác được xác thực và vô hiệu hóa bộ trước theo version. Không cần lưu plaintext vô thời hạn chỉ để hỗ trợ tải lại.

### 12.4. Tách hoàn tất factor và sẵn sàng recovery

Hai trạng thái có thể được theo dõi riêng:

~~~text
factor_replacement = COMPLETED
recovery_readiness = NEEDS_SETUP
~~~

Sản phẩm cần quyết định trạng thái thứ hai ảnh hưởng quyền nào, nếu có. Không dùng nó để mở login yếu hơn.

Việc người dùng bấm “đã lưu mã” chỉ ghi nhận một xác nhận trong giao diện. Nó không chứng minh họ đã cất mã độc lập hoặc sẽ tìm được mã khi mất thiết bị.

## 13. Session sau đăng ký lại

### 13.1. Tập factor và bằng chứng của session là hai loại dữ liệu

Một tài khoản có factor active không có nghĩa mọi session của tài khoản đều đã xác thực bằng factor đó.

Ví dụ:

~~~text
Session S1:
    được tạo từ trước sự cố
    chưa có xác thực bằng phương tiện mới

Account A:
    factor mới F2 đã active

Kết luận:
    không tự cập nhật S1 thành phiên đã xác thực MFA bằng F2
~~~

NIST quy định session không được coi ở AAL cao hơn sự kiện xác thực tạo ra nó. Vì vậy, thay một bản ghi cấu hình không thay được lịch sử và thuộc tính xác thực của session. [NIST SP 800-63B-4, Session Bindings](https://pages.nist.gov/800-63-4/sp800-63b/session/#session-bindings)

### 13.2. Recovery session cần kết thúc đúng phạm vi

Sau commit, context recovery và challenge không còn cần thiết phải bị đóng. Đường đơn giản về mặt phân quyền là yêu cầu đăng nhập lại qua luồng thông thường với phương tiện đã được kích hoạt.

Nếu sản phẩm cấp session mới ngay sau enrollment, cần chứng minh các điều kiện xác thực của session đó đã được đáp ứng. Registration proof hoặc mã xác minh candidate không tự thay thế mọi thành phần của một lượt login.

Session mới cần cơ chế chống fixation và có thuộc tính quyền, thời điểm xác thực, phương thức, thời hạn phù hợp. Không tái sử dụng một bearer token recovery như session ứng dụng đầy đủ.

### 13.3. Quyết định thu hồi session phụ thuộc sự cố

| Bối cảnh | Điều cần xem xét |
| --- | --- |
| Thay thiết bị theo kế hoạch, không có tín hiệu lộ | Session nào cần xác thực lại theo chính sách |
| Điện thoại bị mất đang giữ session | Session và refresh token trên thiết bị đó |
| Mật khẩu, email hoặc kho bí mật bị chiếm | Phạm vi session và quyền phát sinh rộng hơn |
| Session bị đánh cắp dùng để bắt đầu thay MFA | Vô hiệu hóa quyền và operation không hợp lệ, xử lý session bị ảnh hưởng |
| Không thể nhận diện chắc chắn thiết bị nào | Phạm vi thu hồi rộng hơn nếu quyết định rủi ro yêu cầu |

Quyền thay một factor không tự cho phép người ngoài gây đăng xuất toàn bộ tài khoản. Biện pháp tác động rộng cần có căn cứ và thẩm quyền.

Trong kiến trúc token tự chứa, đổi factor không tự làm mọi access token cũ hết hiệu lực ngay. Cần cơ chế revocation, kiểm tra version, introspection hoặc thời hạn phù hợp với kiến trúc.

Nếu có SSO, session tại nhà cung cấp danh tính và session tại từng ứng dụng cũng cần được xét riêng.

## 14. API, giao diện, thông báo và hỗ trợ

### 14.1. Endpoint minh họa

| Endpoint | Mục đích | Điều kiện chính |
| --- | --- | --- |
| `POST /mfa/re-enrollments` | Tạo operation | Quyền đúng scope, chưa gắn sang operation khác |
| `POST /mfa/re-enrollments/{id}/candidate` | Tạo hoặc đổi candidate theo chính sách | Đúng account, operation, generation và hạn mức |
| `POST /mfa/re-enrollments/{id}/verify` | Kiểm tra phương tiện mới | Verifier phù hợp và context còn hiệu lực |
| `POST /mfa/re-enrollments/{id}/commit` | Áp dụng thay thế | Proof, version, quyền và policy vẫn phù hợp |
| `GET /mfa/re-enrollments/{id}` | Đọc trạng thái đã được phép xem | Quyền đọc đúng operation |
| `POST /mfa/re-enrollments/{id}/cancel` | Hủy operation chưa hoàn tất | Thẩm quyền và trạng thái cho phép |

Đây là ví dụ phân chia trách nhiệm, không phải cấu trúc bắt buộc. Mọi endpoint thay đổi cần kiểm tra quyền phía server; giao diện ẩn nút không thay thế kiểm soát truy cập.

Với cookie session, cần chống CSRF phù hợp. GET đọc trạng thái không được có tác dụng kích hoạt hoặc thu hồi factor.

### 14.2. Thông tin cần cho người dùng

Trước khi xác nhận, giao diện nên nêu rõ:

- Phương tiện nào đang được thay và phương tiện nào tiếp tục hoạt động.
- Có cần xử lý session hoặc bộ recovery code không.
- Khi nào thay đổi có hiệu lực.
- Cần làm gì nếu thiết lập mới thất bại.
- Cách báo một thay đổi không do người dùng yêu cầu.

Sau khi hoàn tất, trạng thái cần phản ánh kết quả server đã commit. Không báo “MFA đã khôi phục” chỉ vì QR được hiển thị hoặc ứng dụng camera đã scan.

Thông báo thay đổi nên dùng kênh đã được tin cậy theo chính sách. Kênh mới đang pending không nên trở thành kênh duy nhất báo chính việc thay đổi nó.

Việc gửi thông báo thành công không chứng minh người hợp lệ đã đọc hoặc đồng ý. Nếu kênh cũng nằm trên thiết bị bị mất, cần xét giới hạn đó trong xử lý sự cố.

### 14.3. Nhật ký có ích mà không chứa bí mật

Các sự kiện minh họa:

~~~text
MFA_REENROLLMENT_AUTHORIZED
MFA_REENROLLMENT_STARTED
MFA_CANDIDATE_CREATED
MFA_CANDIDATE_VERIFIED
MFA_FACTOR_REPLACED
MFA_FACTOR_REVOKED
MFA_REENROLLMENT_EXPIRED
MFA_REENROLLMENT_CONFLICTED
RECOVERY_CODE_SET_ROTATED
RELATED_SESSIONS_REVOKED
~~~

Ghi operation ID, account ref, actor, authorization ref, policy version, candidate generation, version trước/sau và reason code theo quyền truy cập.

Không ghi seed, QR chứa seed, mã OTP thô, private key, session cookie hoặc token recovery. Dữ liệu lỗi từ thư viện cũng cần được lọc trước khi đưa vào log hay ticket.

Nhân viên hỗ trợ nên nhìn thấy bước nào còn thiếu và hành động nào được cấp quyền, thay vì một nút bỏ qua mọi điều kiện.

## 15. Ví dụ xuyên suốt

### 15.1. Đổi ứng dụng TOTP theo kế hoạch

Minh còn dùng được factor F1 và muốn đổi sang thiết bị khác:

1. Minh xác thực lại theo chính sách thay MFA.
2. Server cấp quyền thay F1 cho một operation.
3. Server tạo candidate F2 với seed mới.
4. Minh thiết lập và trình mã từ F2.
5. Server lưu proof gắn với đúng seed generation.
6. Minh xác nhận thay thế.
7. Server commit F2 active và F1 revoked theo quyết định.
8. Minh đăng nhập hoặc xác thực lại theo quy trình sau thay đổi.

F1 có thể tiếp tục dùng trong giai đoạn thiết lập nếu chính sách cho phép và chưa có sự cố. Nếu Minh hủy trước commit, F2 bị đóng, F1 giữ trạng thái hợp lệ vốn có.

Nếu mục tiêu chỉ là thêm dự phòng, phạm vi quyết định cần là thêm factor; không tự thu hồi F1 bằng luồng thay thế.

### 15.2. Mất điện thoại giữ TOTP và session

Lan mất điện thoại, không còn dùng được F1. Báo mất được xử lý qua nhánh có xác minh; F1 bị ngừng theo quyết định sự cố.

Lan dùng bằng chứng recovery được hỗ trợ để nhận quyền đăng ký F2. Quyền này chỉ phục vụ enrollment, chưa mở dữ liệu ứng dụng.

Lan scan QR nhưng chưa trình được mã đúng:

- F2 vẫn pending và chưa đăng nhập được.
- F1 không tự hoạt động lại.
- Login bằng mật khẩu đơn lẻ vẫn không đáp ứng chính sách MFA.
- Lan tiếp tục operation còn hiệu lực hoặc bắt đầu lại qua nhánh được phép khi nó hết hạn.

Khi F2 hoàn tất, hệ thống xử lý session trên điện thoại mất và các quyền liên quan theo phạm vi sự cố. Thay TOTP không tự giải quyết session đang nằm trên điện thoại.

### 15.3. Đối tượng có session muốn thêm MFA của họ

Đối tượng lấy được session S1 của Hà và mở trang thay authenticator. Server yêu cầu bằng chứng đủ điều kiện cho hành động thay MFA.

Đối tượng có thể cài ứng dụng TOTP trên máy của họ và tạo mã từ một seed mà họ biết. Khả năng đó chỉ chứng minh quyền giữ seed ấy.

Nếu chưa có quyền đăng ký lại cho tài khoản Hà, server không tạo binding có thể được kích hoạt. Các endpoint tạo candidate, verify và commit đều thực thi cùng ranh giới quyền, tránh việc đối tượng bỏ qua trang đầu và gọi API phía sau.

Một cờ frontend như `recoveryApproved=true` không thay đổi quyết định này.

## 16. Các tình huống cần kiểm chứng khi triển khai

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Chỉ có session cũ, thiếu điều kiện thay MFA | Không được tự đăng ký factor mới |
| Người dùng mất yếu tố bắt buộc | Có nhánh recovery được hỗ trợ; không yêu cầu yếu tố mất như đường duy nhất |
| Đổi account ID hoặc tenant ID trong request | Không chuyển operation sang tài khoản khác |
| Quyền được cấp cho TOTP nhưng yêu cầu phương thức khác | Kiểm tra lại scope và chính sách |
| Candidate chưa có proof | Không active, không tham gia login |
| Candidate đã verified nhưng chưa commit | Chỉ dùng được trong context enrollment được phép |
| Seed được đổi sau lần verify | Proof cũ không kích hoạt seed mới |
| Hai verifier nhận cùng mã TOTP trong cùng time step | Không tạo hai lần chấp nhận độc lập |
| Retry request verify đã thành công | Trả kết quả đã lưu nếu đúng idempotency |
| Mã dùng cho enrollment được trình lại để login | Trạng thái chống replay vẫn được thực thi |
| Challenge WebAuthn sai origin hoặc operation | Bị từ chối theo giao thức và context |
| Credential ID đã thuộc binding khác | Không ghi đè hoặc chuyển chủ binding |
| Chỉ xác nhận được số điện thoại mới | Chưa có quyền thay số của tài khoản cũ |
| Candidate không đáp ứng yêu cầu chống phishing | Không tự hạ chính sách để hoàn tất |
| Yếu tố cũ đã thu hồi, candidate mới thất bại | Yếu tố cũ không tự hoạt động lại |
| Không còn factor active nhưng tài khoản vẫn yêu cầu MFA | Không mở login chỉ bằng mật khẩu |
| Hai tab commit từ cùng factor set version | Phát hiện xung đột; không thay đổi theo ảnh chụp cũ |
| Commit thành công nhưng response bị mất | Retry trả kết quả cũ, không tạo thêm factor |
| Operation hết hạn nhưng job dọn dẹp chưa chạy | Verifier vẫn từ chối theo thời hạn |
| Thông báo bị lỗi sau commit | Giữ thay đổi bảo mật, retry thông báo có kiểm soát |
| Consumer nhận sự kiện thu hồi cũ sau sự kiện mới | Không ghi đè version mới bằng trạng thái cũ |
| Factor mới active, session cũ chưa reauthenticate | Không tự nâng thuộc tính xác thực của session |
| Access token cũ còn được xác minh ngoại tuyến | Áp dụng cơ chế thu hồi hoặc giới hạn thời hạn thực tế |
| Mất response chứa bộ recovery code mới | Cấp lại qua quyền hợp lệ, vô hiệu bộ trước theo version nếu cần |
| Kiểm tra log, cache, analytics và ticket | Không có seed, QR nhạy cảm hoặc token thô |
| Verifier hoặc kho khóa bắt buộc đang lỗi | Chờ hoặc xử lý lỗi; không bỏ MFA hay chấp nhận candidate mặc định |

## 17. Những điểm cần ghi nhớ

- Đăng ký lại MFA là một thay đổi quyền truy cập, cần được bảo vệ như hành động nhạy cảm.
- Quyền thay factor, việc thiết lập candidate và bằng chứng xác thực bằng candidate là các bước riêng.
- TOTP cần seed mới khi mục tiêu là loại bỏ bí mật cũ bị lộ; WebAuthn cần credential và ceremony được kiểm tra đúng giao thức.
- Candidate chỉ trở thành phương tiện đăng nhập sau commit hợp lệ; proof cũ không được dùng cho vật liệu mới.
- Yếu tố đã bị ngừng do sự cố không được phục hồi chỉ để làm luồng mới thuận tiện hơn.
- Recovery code, token một lần, challenge và mã TOTP cần trạng thái chống dùng lại phù hợp với vai trò của chúng.
- Thay factor không tự thu hồi session, không tự nâng mức bảo đảm của session và không tự khôi phục mọi ranh giới tin cậy.
- Kết quả hoàn tất phải phản ánh phương tiện mới đã active, phương tiện cũ được xử lý đúng phạm vi và các quyền phát sinh được kiểm soát.
