# Recovery flow documentation — Tài liệu hóa luồng khôi phục tài khoản

## 1. Tài liệu cần làm rõ việc cấp lại quyền truy cập

Một sơ đồ “nhập email → nhận mã → đổi mật khẩu” mô tả được trải nghiệm quen thuộc, nhưng còn để ngỏ những quyết định quan trọng:

- Mã được gửi theo điều kiện nào và tới địa chỉ nào?
- Bằng chứng đó đủ cho đổi password hay cả thay MFA?
- Ai có quyền phê duyệt khi người dùng mất mọi thiết bị?
- Nếu token được dùng đồng thời, hệ thống xử lý ra sao?
- Sau khi thay credential, session cũ còn hoạt động không?
- Nhân viên hỗ trợ được làm gì khi provider xác minh bị lỗi?

Recovery flow documentation là tập mô tả có cấu trúc giúp các bên hiểu cách một yêu cầu khôi phục đi từ điểm vào, qua xác minh và cấp quyền giới hạn, tới thay đổi credential cùng các hậu điều kiện liên quan.

Trong module SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY, tài liệu phải bao quát đúng những đường sản phẩm hỗ trợ khi mất mật khẩu, MFA, passkey hoặc thiết bị xác thực. Mục tiêu là làm cho quyết định cấp lại quyền có thể được triển khai, kiểm tra và vận hành nhất quán.

Một tài liệu tốt không chỉ nói người dùng nhấn nút nào. Nó chỉ ra ai quyết định, quyết định dựa trên dữ kiện gì, quyền có giới hạn nào và nơi nào thực sự thực thi giới hạn đó.

Sau bài học, người học có thể:

- Chọn phạm vi và đối tượng đọc của bộ tài liệu.
- Phân biệt recovery, đăng nhập, thay factor và hỗ trợ thủ công.
- Biểu diễn actor, ranh giới tin cậy, trạng thái và chuyển trạng thái.
- Viết hợp đồng cho token, API, retry, hủy và tình huống thất bại.
- Mô tả session, thông báo và kết quả hoàn tất một cách chính xác.
- Nối yêu cầu, thiết kế, bằng chứng và phiên bản triển khai.
- Duy trì tài liệu khi luồng recovery thay đổi.

Những tên trạng thái, endpoint, control ID và biểu mẫu trong bài là ví dụ tự thiết kế. Chúng cần được điều chỉnh theo sản phẩm, không phải một giao thức recovery chuẩn dùng nguyên vẹn cho mọi hệ thống.

## 2. Xác định người đọc và nguồn thông tin có thẩm quyền

### 2.1. Một luồng, nhiều cách trình bày

| Người đọc | Cần biết | Cách trình bày phù hợp |
|---|---|---|
| Người sử dụng | Điều kiện bắt đầu, việc cần làm, đường hỗ trợ và thông báo | Hướng dẫn rõ, không chứa chi tiết nội bộ không cần thiết |
| Product và UX | Những nhánh, trạng thái người dùng có thể thấy, trường hợp mắc kẹt | Journey, nội dung thông báo và quyết định trải nghiệm |
| Kỹ sư triển khai | Preconditions, authorization, dữ liệu, API và bất biến | State model, sequence và hợp đồng |
| Nhóm kiểm thử | Kết quả mong đợi, điều kiện cạnh tranh và trường hợp bị từ chối | Bảng chuyển trạng thái và kịch bản |
| Support và vận hành | Quyền được phép, cách tra cứu, escalation và xử lý lỗi | Runbook có ranh giới hành động |
| Security và người đánh giá | Cơ sở policy, trust boundary, đường đi vòng và bằng chứng | Ma trận quyết định và traceability |

Không cần viết một bản sao policy đầy đủ cho mỗi nhóm. Nên có nguồn quy tắc được quản lý, rồi tạo những góc nhìn phù hợp với cùng quy tắc đó.

Ví dụ, tài liệu người dùng có thể nói “liên kết đã hết hạn, hãy bắt đầu lại”. Tài liệu kỹ thuật phải giải thích thời hạn tính từ đâu, hệ thống nào kiểm tra và bắt đầu lại ảnh hưởng gì tới các liên kết cũ.

### 2.2. Phân biệt chính sách, thiết kế, triển khai và runbook

Một bộ tài liệu thường chứa bốn lớp:

~~~text
Policy:
  Những điều kiện nào phải được đáp ứng để cho phép hành động?

Thiết kế:
  Hệ thống thực thi các điều kiện đó bằng cơ chế nào?

Triển khai:
  Phiên bản nào đang chạy, tại scope nào, với cấu hình nào?

Runbook:
  Người vận hành xử lý các tình huống cụ thể bằng quyền nào?
~~~

Nếu policy yêu cầu phê duyệt độc lập nhưng công cụ hiện tại chưa hỗ trợ, ghi đây là khoảng trống. Không mô tả sơ đồ mong muốn như thể tính năng đã có.

Một ghi chú trong runbook cũng không được tự tạo quyền bỏ qua policy. Nếu có ngoại lệ, cần nguồn quyết định, scope và cơ chế kiểm soát của ngoại lệ đó.

### 2.3. Dẫn nguồn nhưng không biến tham chiếu thành cam kết tuân thủ

[NIST SP 800-63B-4, phần Authenticator Event Management](https://pages.nist.gov/800-63-4/sp800-63b/events/) phân biệt account recovery với việc gắn authenticator mới khi chủ thể vẫn xác thực được bằng phương tiện khác. Tài liệu này cũng đặt yêu cầu ghi nhận phân tích rủi ro đối với phương thức recovery thay thế trong phạm vi áp dụng của nó.

Điều đó gợi ý hai việc thực dụng: viết rõ loại hành động đang được mô tả và lưu cơ sở lựa chọn phương thức. Không gọi mọi thao tác thay password là cùng một mức recovery.

Khi sử dụng một tiêu chuẩn, ghi phiên bản, phần liên quan và phạm vi được tổ chức xác định là áp dụng. Một liên kết tới NIST hoặc OWASP không tự chứng minh thiết kế hay triển khai đã đáp ứng mọi yêu cầu.

## 3. Chốt phạm vi và từ vựng trước khi vẽ sơ đồ

### 3.1. Phạm vi cần có điểm bắt đầu và kết thúc

Một thẻ mô tả luồng có thể ghi:

~~~yaml
flowDocument:
  flowId: account-recovery-password-example
  revision: 3
  lifecycle: proposed
  audience:
    - engineering
    - security
    - support
  scope:
    entry: public-recovery-request
    credentialAction: replace-password
    accountClass: standard-user
    tenantBoundary: server-resolved-tenant
  startsWhen: request-is-admitted-and-recorded
  credentialMilestone: password-mutation-committed
  relatedEffects:
    - session-policy-actions
    - recovery-notification
  policyRef: recovery-policy-example-v7
  implementationRef: not-yet-linked
  ownerRole: recovery-platform
~~~

Đây là mẫu nội dung tài liệu, không phải cấu trúc metadata của module.

lifecycle proposed và implementationRef chưa liên kết giúp người đọc biết đây là thiết kế đề xuất. Khi đã triển khai, cần nguồn xác nhận phiên bản và scope tương ứng; không chỉ đổi một chữ trong tài liệu rồi coi như rollout hoàn tất.

### 3.2. Các thuật ngữ cần định nghĩa

| Thuật ngữ | Ý nghĩa cần thống nhất |
|---|---|
| Recovery request | Yêu cầu đầu vào; chưa chứng minh account tồn tại hay người gửi có quyền |
| Recovery transaction | Hồ sơ xử lý nghiệp vụ qua nhiều bước |
| Evidence | Dữ kiện dùng để đánh giá điều kiện xác minh |
| Verification result | Kết quả kiểm tra một bằng chứng trong một ngữ cảnh |
| Authorization decision | Quyết định cho phép một hành động và scope cụ thể |
| Recovery grant | Quyền giới hạn để thực hiện bước hoặc mutation được phép |
| Credential mutation | Thay đổi được authority credential commit |
| Recovery session | Ngữ cảnh giới hạn phục vụ luồng recovery |
| Application session | Quyền truy cập tài nguyên ứng dụng theo cơ chế đăng nhập |
| Notification | Thông báo về sự kiện, không mặc định là bằng chứng người nhận đã đọc |

Đặc biệt, recovery session không tự đồng nghĩa application session. Một quyền đủ để nhập password mới không mặc định đủ để đọc dữ liệu nghiệp vụ hay thêm một phương thức thanh toán.

Nếu hệ thống dùng một token cho nhiều vai trò, tài liệu phải nêu từng capability và cách hạn chế. Không để mọi thứ cùng được gọi là “token xác thực”.

### 3.3. Những gì nằm ngoài phạm vi cũng phải rõ

Ví dụ, tài liệu một nhánh password recovery có thể không mô tả đầy đủ quy trình khôi phục email tại nhà cung cấp email. Tuy vậy, nó cần chỉ ra việc mất quyền email ảnh hưởng thế nào tới điều kiện của nhánh này và người dùng chuyển tới đâu.

Tương tự, khôi phục quyền truy cập account bằng passkey mới khác với quá trình nhà cung cấp đồng bộ passkey phục hồi credential trên thiết bị. Nếu server không nắm private key, tài liệu không được hứa rằng support sẽ lấy lại private key đó.

## 4. Mô tả actor và ranh giới tin cậy

### 4.1. Vẽ nơi quyết định và nơi thực thi

~~~mermaid
flowchart LR
    U["Người yêu cầu / client"] --> R["Recovery service"]
    H["Nhân viên hỗ trợ"] --> C["Công cụ hỗ trợ"]
    C --> R
    R --> V["Dịch vụ kiểm tra bằng chứng"]
    R --> A["Credential authority"]
    A --> S["Session và resource"]
    R --> N["Dịch vụ thông báo"]
~~~

Sơ đồ chỉ là bản đồ thành phần. Mỗi mũi tên còn cần hợp đồng về xác thực caller, authorization, dữ liệu trao đổi, khả năng timeout và nguồn có thẩm quyền.

Ví dụ:

- Client cung cấp dữ liệu đầu vào, không tự quyết định account đã được xác minh.
- Công cụ support gửi yêu cầu dưới danh tính nhân viên có thể truy vết.
- Dịch vụ kiểm tra bằng chứng trả một kết quả gắn với ngữ cảnh, không mặc định cấp mọi quyền recovery.
- Credential authority là nơi biết mutation đã commit hay chưa.
- Session service và resource là nơi cần đối chiếu hiệu lực thu hồi theo kiến trúc.

Một database có trường status không tự trở thành authority cho mọi thành phần khác. Phải biết thành phần nào được phép thay trường đó và ai tin vào nó.

### 4.2. Ghi rõ ngữ cảnh nào có thể bị giả mạo

Với mỗi dữ liệu như tenant, accountRef, actorRef, evidenceRef hoặc action, nêu ai tạo, ai xác minh và dữ liệu có thể bị sửa ở đâu.

Tenant lấy từ body client không mặc định là tenant mà nhân viên hỗ trợ được phép thao tác. Actor ID client khai cũng không đủ để quy hành động cho một nhân viên.

Nếu dùng callback từ provider, cần tài liệu về xác thực nguồn, chống giao lại, ràng buộc transaction và cách xử lý kết quả đến muộn. Một response “verified” không có ngữ cảnh không đủ cho một quyết định nhạy cảm.

### 4.3. Danh mục đường ghi và quyền đặc biệt

Ngoài endpoint chính, cần ghi các đường có thể thay credential:

- Nhánh mobile hoặc API cũ.
- Công cụ quản trị tenant.
- Batch hoặc worker xử lý sau phê duyệt.
- Quyền break-glass nếu sản phẩm có.
- Các thao tác trực tiếp được cho phép trong vận hành.

Mục đích là biết bất biến được thực thi trên những đường nào. Không cần đưa thông tin truy cập nhạy cảm vào một tài liệu chia sẻ rộng; có thể dẫn tới inventory được phân quyền.

## 5. Lập ma trận các nhánh recovery

### 5.1. Đừng dùng một happy path cho mọi trường hợp mất quyền

| Tình huống | Điều phải phân biệt | Tài liệu cần chỉ rõ |
|---|---|---|
| Quên password nhưng còn authenticator hợp lệ | Thay credential sau xác thực có thể khác recovery khi mất mọi phương tiện | Yêu cầu xác thực lại và quyền được cấp |
| Mất MFA nhưng còn password | Password hiện có chưa tự đủ cho mọi thao tác thay factor | Phương thức thay thế và điều kiện đánh giá |
| Mất passkey trên một thiết bị | Có thể còn passkey khác hoặc đường xác thực khác | Nhánh dùng phương tiện còn lại và nhánh recovery thật sự |
| Mất mọi thiết bị xác thực | Không còn đường xác thực bình thường | Điều kiện bằng chứng, phương thức hỗ trợ và giới hạn |
| Có recovery code đã chuẩn bị | Mã mang quyền theo policy và vòng đời riêng | Scope, tiêu thụ một lần, thay bộ mã nếu áp dụng |
| Kênh recovery bị nghi chiếm | Chính kênh nhận mã có thể không đáng tin | Đường xác minh thay thế và trường hợp không thể tiếp tục |
| Có yêu cầu hỗ trợ thủ công | Nhân viên tác động vào quyết định mạnh | Quyền actor, phê duyệt, bằng chứng và audit |

Một sản phẩm không nhất thiết hỗ trợ mọi nhánh. Trạng thái “không có đủ bằng chứng để phục hồi” có thể là kết quả thực tế cần giải thích, thay vì hứa support luôn giải quyết được.

### 5.2. Ghi điều kiện chọn nhánh bằng dữ kiện cụ thể

Tránh câu “nếu rủi ro thấp thì gửi mã”. Cần làm rõ dữ liệu đầu vào nào được sử dụng, thành phần nào đánh giá, policy version nào áp dụng và kết quả nào cho phép chuyển bước.

Nếu ngưỡng hoặc mô hình không phù hợp để công bố rộng, tài liệu nội bộ vẫn phải có reference tới cấu hình được quản lý. Không dùng một nhãn mơ hồ để che việc chưa có quy tắc.

[OWASP Multifactor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#resetting-mfa) nhấn mạnh việc chọn phương thức reset MFA theo bối cảnh ứng dụng để tránh tạo đường vượt MFA. Phần thay factor cũng lưu ý rủi ro của việc chỉ tin một session đang hoạt động.

Vì vậy, tài liệu cần tách rõ “người dùng còn xác thực được và muốn đổi factor” với “người dùng không còn factor cần thiết”. Không áp dụng một bước reauthentication không thể thực hiện rồi để support tự nghĩ ra cách bỏ qua.

### 5.3. Mỗi nhánh phải có hậu điều kiện

Cho phép đặt password mới không tự có nghĩa MFA đã được thay. Đăng ký passkey mới không tự xóa mọi credential cũ. Xóa một factor cũng không tự thu hồi refresh token.

Ma trận nhánh cần nêu từng hành động được phép và những tài sản bị ảnh hưởng. Những điều kiện không áp dụng nên có lý do, tránh để một ô trống bị hiểu là đã được xử lý ở nơi khác.

## 6. Mô tả trạng thái theo ý nghĩa nghiệp vụ

### 6.1. Trạng thái cần có điều kiện, không chỉ tên

Ví dụ dưới đây dùng một transaction password recovery. Các tên là đề xuất minh họa:

| Trạng thái | Ý nghĩa | Điều chưa được suy ra |
|---|---|---|
| RECEIVED | Yêu cầu đã được ghi nhận | Account tồn tại hoặc người gửi là chủ account |
| VERIFYING | Hệ thống đang thu thập, kiểm tra điều kiện của nhánh | Đã đủ quyền thay credential |
| AUTHORIZED | Có quyết định cho phép hành động giới hạn còn được quản lý theo policy | Đã có application session đầy đủ |
| CREDENTIAL_UPDATED | Authority xác nhận password mutation đã commit | Mọi session cũ đã mất quyền hoặc thông báo đã được đọc |
| DENIED | Quyết định nội bộ không cho tiếp tục theo nhánh này | Có thể tiết lộ lý do chi tiết cho caller công khai |
| EXPIRED | Cơ hội tiếp tục transaction đã hết theo quy tắc | Mutation đã commit trước đó được đảo ngược |
| CANCELLED | Việc hủy đã có hiệu lực theo phạm vi được định nghĩa | Các tác động đã commit trước hủy tự bị hoàn tác |

Không dùng một trạng thái COMPLETED mà không định nghĩa hoàn tất việc gì. Trong ví dụ, CREDENTIAL_UPDATED chỉ là mốc credential; các hậu điều kiện được theo dõi riêng.

Nếu sản phẩm cần một trạng thái “phục hồi quyền kiểm soát đã hoàn tất”, phải định nghĩa thêm những gate cần có và nguồn xác nhận. Không đổi tên một commit password thành kết luận bảo mật rộng hơn.

### 6.2. Bảng chuyển trạng thái

| Từ | Hành động | Điều kiện cần kiểm tra | Sang |
|---|---|---|---|
| RECEIVED | Chọn nhánh xử lý | Admission, scope và policy của yêu cầu | VERIFYING hoặc kết quả kết thúc nội bộ phù hợp |
| VERIFYING | Đánh giá bằng chứng | Kết quả gắn đúng transaction, account, loại hành động và revision | AUTHORIZED nếu đủ điều kiện |
| VERIFYING | Từ chối | Điều kiện không đạt theo policy | DENIED |
| AUTHORIZED | Hoàn tất thay password | Grant hợp lệ tại điểm quyết định của authority và mutation được phép | CREDENTIAL_UPDATED |
| Trạng thái còn hoạt động | Hết thời gian | Quy tắc hết hạn tại nơi thực thi có hiệu lực | EXPIRED |
| Trạng thái còn hoạt động | Hủy có hiệu lực | Authority xác nhận chặn các quyền tiếp tục thuộc phạm vi hủy | CANCELLED |
| AUTHORIZED | Bằng chứng hoặc quyết định mất hiệu lực | Quy tắc invalidation được xác định | Đánh giá lại hoặc kết thúc theo policy |

“Trạng thái còn hoạt động” phải được liệt kê trong đặc tả thật; không dùng nó để vô tình cho phép hủy ngược mutation đã hoàn tất.

Bảng cũng cần chỉ rõ actor được gọi từng hành động. Có trạng thái phù hợp chưa đủ cho authorization: một nhân viên ngoài tenant vẫn không được hoàn tất transaction của tenant khác.

### 6.3. Vòng đời transaction khác vòng đời grant

Một transaction có thể chứa nhiều bước. Grant có scope và trạng thái riêng như available, consumed, revoked hoặc expired.

Tài liệu cần giải thích:

- Grant được cấp tại bước nào.
- Một grant cho phép một hành động hay một nhóm hành động nguyên tử nào.
- Dùng thành công làm thay đổi trạng thái gì.
- Retry cùng operation có trả lại kết quả cũ không.
- Hủy transaction có vô hiệu các grant nào.
- Bắt đầu transaction mới có ảnh hưởng transaction hoặc grant cũ không.

“One-time” phải gắn với đơn vị nghiệp vụ cụ thể. Một lần thay MFA có thể bao gồm nhiều cập nhật dữ liệu; điều cần giới hạn là hành động được phép, không phải chỉ số câu SQL.

### 6.4. Deadline phải có mốc bắt đầu và nơi kiểm tra

Tránh viết “token sống 10 phút” nếu chưa biết con số đó áp dụng cho loại token nào, được tính từ sự kiện nào và kiểm tra ở đâu.

Tài liệu thực tế nên nêu nguồn cấu hình, thời điểm phát hành, thời hạn tuyệt đối hoặc tương đối, nguồn thời gian và điểm quyết định authorization có hiệu lực.

Với request đến trước deadline nhưng chờ xử lý tới sau deadline, kết quả phụ thuộc quy tắc đã thiết kế. Phải ghi rõ, không để mỗi service tự chọn.

Không dùng thời gian trên UI làm authority. Đồng hồ đếm ngược giúp trải nghiệm nhưng server vẫn phải thực thi quy tắc được tài liệu hóa.

## 7. Viết một thẻ chuyển trạng thái có thể triển khai

### 7.1. Thẻ cho bước thay password

~~~yaml
transition:
  id: complete-password-recovery-example
  appliesTo: account-recovery-password-example
  fromState: AUTHORIZED
  targetMilestone: CREDENTIAL_UPDATED
  caller:
    capability: password-replacement-for-this-transaction
    applicationAccessGranted: false
  bindings:
    - tenant
    - account
    - transaction
    - credential-action
    - authorization-decision
    - evidence-revision
  preconditions:
    - grant-is-valid-under-the-current-enforcement-rule
    - decision-has-not-been-invalidated
    - requested-mutation-matches-grant-scope
  atomicBusinessEffect:
    - replace-password-credential
    - consume-the-one-action-grant
    - record-result-for-the-completion-operation
  followUp:
    - apply-session-policy
    - dispatch-recovery-notification
  retryRule: same-operation-does-not-create-another-mutation
  failureRule: preserve-a-queryable-authoritative-outcome
~~~

Thẻ này mô tả yêu cầu của bước. Nó chưa chứng minh một kiến trúc phân tán đã thực hiện nguyên tử được cả ba tác động.

Nếu authority quản lý grant và credential trong cùng database, tài liệu có thể chỉ rõ ranh giới transaction. Nếu chúng ở hai dịch vụ độc lập, phải mô tả giao thức phối hợp, trạng thái trung gian, reconciliation và những giới hạn thực tế.

### 7.2. Gắn quyết định với đúng bằng chứng

Một kết quả “verified” có thể trở nên không còn phù hợp nếu bằng chứng, account đích hoặc loại thao tác thay đổi trước lúc hoàn tất.

Thẻ chuyển trạng thái nên ghi cách ràng buộc revision và điều kiện invalidation. Ví dụ, thay địa chỉ recovery sau khi phê duyệt có làm mất hiệu lực quyết định không? Nếu có, cơ chế nào chặn completion cũ?

Không cho client chỉ gửi evidenceRef bất kỳ rồi authority tin rằng bằng chứng đã được chấp nhận. Reference cần được kiểm tra theo nguồn, transaction và policy.

### 7.3. Viết bất biến như điều kiện có thể kiểm tra

Các bất biến minh họa:

~~~text
INV-01:
  Một grant chỉ thực hiện mutation thuộc tenant, account và action đã cấp.

INV-02:
  Cùng quyền một lần không tạo thêm business mutation ngoài hợp đồng.

INV-03:
  Một quyết định đã bị vô hiệu không được dùng để hoàn tất bước mới.

INV-04:
  Reference dùng tra cứu không tự cấp quyền thay credential.

INV-05:
  Mốc credential đã đổi không được báo thành mốc mọi session đã bị chặn.
~~~

Mỗi bất biến cần chỉ ra nơi thực thi và đường gọi thuộc phạm vi. Việc viết INV-01 trong tài liệu không thay kiểm tra authorization tại server.

## 8. Dùng sequence diagram để chỉ rõ thời điểm có hiệu lực

### 8.1. Ví dụ nhánh hoàn tất password recovery

Trong sơ đồ này, credential authority được giả định sở hữu cả bản ghi completion grant và dữ liệu cần thay password trong cùng ranh giới transaction. Đây là giả định kiến trúc phải được xác nhận nếu áp dụng thực tế.

~~~mermaid
sequenceDiagram
    participant U as Người yêu cầu
    participant R as Recovery service
    participant V as Kiểm tra bằng chứng
    participant A as Credential authority
    participant S as Session service
    participant N as Dịch vụ thông báo

    U->>R: Gửi dữ liệu cho nhánh recovery
    R->>V: Kiểm tra bằng chứng trong ngữ cảnh
    V-->>R: Kết quả gắn transaction và revision
    R->>R: Quyết định theo policy
    R->>A: Đăng ký completion grant có scope
    A-->>R: Xác nhận quyền giới hạn đã sẵn sàng
    R-->>U: Cho tiếp tục bằng cơ chế giới hạn đã thiết kế
    U->>A: Yêu cầu thay password bằng quyền giới hạn
    A->>A: Kiểm tra grant, consume và commit mutation
    A-->>U: Kết quả credential đã thay
    A-->>S: Tác vụ thực thi session policy
    A-->>N: Tác vụ gửi thông báo recovery
    S-->>A: Kết quả xử lý theo khả năng quan sát
    N-->>A: Trạng thái gửi theo giao thức
~~~

Sơ đồ lược bỏ chi tiết đóng gói và vận chuyển quyền tới client. Tài liệu giao thức phải bổ sung cách tránh lộ token, xác thực caller và chống các thao tác ngoài scope.

Các mũi tên follow-up không có nghĩa “gửi event một lần là chắc chắn tới nơi”. Tài liệu cần nêu cơ chế giao, retry, khử trùng, lỗi và nơi biết tác vụ có hiệu lực.

### 8.2. Chú thích những ranh giới sơ đồ không thể tự diễn đạt

Phần chú thích nên trả lời:

- Quyết định còn hợp lệ bao lâu và bị hủy bởi những thay đổi nào?
- Authority kiểm tra lại điều kiện gì khi completion xảy ra?
- Nếu bước gửi grant bị timeout thì recovery service tra kết quả ở đâu?
- Nếu client không nhận response sau commit, retry thế nào?
- Session policy có hiệu lực đồng bộ hay bất đồng bộ?
- Người dùng được phép đăng nhập lại với điều kiện gì?
- Thành phần nào được phép tuyên bố từng mốc hoàn tất?

Một sơ đồ không có những câu trả lời này thường chỉ là đường đi thông điệp. Nó chưa phải hợp đồng đủ để xử lý sự cố.

## 9. Mô tả hợp đồng API và giao diện công khai

### 9.1. Bảng operation trước chi tiết payload

| Operation minh họa | Caller | Quyền cần có | Kết quả cần định nghĩa |
|---|---|---|---|
| Ghi nhận yêu cầu | Caller chưa xác thực | Admission và kiểm soát đầu vào | Yêu cầu đã được nhận; không chứng minh account tồn tại |
| Gửi bằng chứng | Caller trong ngữ cảnh recovery phù hợp | Quyền cho bước hiện tại | Chấp nhận xử lý hoặc kết quả công khai theo thiết kế |
| Hoàn tất credential action | Caller có completion capability | Đúng scope, trạng thái và điều kiện hiện tại | Mutation đã commit hoặc kết quả thất bại có nghĩa rõ |
| Hủy transaction | Chủ thể được phép theo giao thức | Quyền hủy trong scope | Yêu cầu hủy hay hủy đã có hiệu lực, phải phân biệt |
| Phê duyệt hỗ trợ | Nhân viên được xác thực | Role, tenant, loại thao tác và điều kiện phê duyệt | Quyết định có thể truy vết |
| Tra cứu vận hành | Actor nội bộ được cấp quyền | Quyền đọc theo scope | Dữ liệu được phân loại phù hợp |

Biết transaction ID không đồng nghĩa được gọi mọi operation. Tài liệu phải nêu rõ ID là định danh, capability hay kết hợp những thành phần nào.

### 9.2. Ví dụ response nhận yêu cầu

~~~http
POST /recovery/requests
Content-Type: application/json

{
  "identifier": "person@example.invalid",
  "requestedAction": "password-replace"
}
~~~

Một response minh họa cho yêu cầu được nhận:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "message": "Nếu yêu cầu đáp ứng điều kiện, hướng dẫn tiếp theo sẽ được gửi qua kênh phù hợp."
}
~~~

Địa chỉ trong ví dụ là dữ liệu giả. Endpoint và status code là thiết kế minh họa, không phải quy định bắt buộc cho mọi API.

Response 202 không nên được giải thích như “đã gửi email” nếu hệ thống mới chỉ nhận xử lý. Nó cũng không chứng minh rằng yêu cầu sẽ được phê duyệt.

[OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html) khuyến nghị tránh tiết lộ account qua phản hồi và thời gian xử lý; đồng thời nêu các đặc tính an toàn của token reset. Khi viết hợp đồng công khai, cần mô tả cả thông điệp và hành vi có thể quan sát, không chỉ chụp một màn hình.

### 9.3. Phân biệt lỗi công khai và lý do nội bộ

Một request không hợp lệ theo cú pháp có thể có response khác theo contract. Tuy nhiên, khác biệt dựa trên việc account có tồn tại hay không cần được xem xét trong mô hình chống dò account.

Bảng lỗi nên có hai cột riêng:

~~~text
Lý do nội bộ:
  Dùng cho vận hành và audit, có quyền truy cập theo scope.

Kết quả công khai:
  Dữ liệu caller được phép biết tại bước hiện tại.
~~~

Không sao chép nguyên mã lỗi nội bộ ra UI chỉ vì frontend cần debug. Cũng không gom mọi lỗi nội bộ thành “unknown” khiến không thể điều tra.

Nếu có API tra trạng thái, tài liệu phải chỉ ra cách authorization, giới hạn dữ liệu trả về và sự khác nhau giữa view công khai với state nội bộ. Một lookup bằng email không được trở thành công cụ xác nhận account.

### 9.4. Hợp đồng retry và idempotency

Tài liệu mỗi operation cần ghi:

- Đơn vị operation mà idempotency bảo vệ.
- Scope và thời gian giữ kết quả.
- Cách xử lý cùng key nhưng khác payload.
- Cách xử lý request cạnh tranh.
- Những response có thể retry và điều kiện retry.
- Cách lấy lại kết quả khi response bị mất.
- Giới hạn về lưu trữ hoặc phiên bản làm ảnh hưởng replay kết quả.

Idempotency không thay cho token một lần. Một key chỉ giúp nhận lại cùng operation; quyền thay credential vẫn phải có scope và vòng đời đúng.

Nếu key có thể do caller tự tạo, không đưa giá trị thô vào ví dụ log nhạy cảm một cách mặc định. Tài liệu cần nói dữ liệu nào được ghi và cách giảm lộ.

## 10. Viết rõ những đường thất bại và cạnh tranh

### 10.1. Ma trận những tình huống tối thiểu

| Tình huống | Điều tài liệu phải trả lời |
|---|---|
| Client timeout trước khi biết request đã được ghi chưa | Retry có tạo transaction mới không? |
| Provider không phản hồi | Pending, lỗi hay chuyển nhánh; ai được quyết định? |
| Callback provider đến sau khi transaction hết hạn | Kết quả bị bỏ qua hoặc xử lý theo quy tắc nào? |
| Bằng chứng thay đổi sau phê duyệt | Quyết định cũ còn hiệu lực không? |
| Hai completion cùng dùng grant | Hành động nào được commit, bên còn lại nhận kết quả gì? |
| Mutation commit nhưng response bị mất | Lấy kết quả cũ thế nào mà không đổi credential lần nữa? |
| Hủy và completion cạnh tranh | Điểm thứ tự có hiệu lực nằm ở đâu? |
| Resend mã | Mã cũ còn hợp lệ không, giới hạn gửi được tính thế nào? |
| Bắt đầu transaction mới | Transaction và grant cũ được giữ, thay thế hay vô hiệu? |
| Session service lỗi sau mutation | Trạng thái nào còn pending và ai xử lý? |
| Notification provider lỗi | Retry và escalation ra sao, người dùng được thông báo gì? |

Không nhất thiết mọi lỗi đều tạo một state mới. Nhưng mỗi lỗi phải có kết quả và trách nhiệm xử lý rõ.

### 10.2. Phân biệt thất bại đã xác nhận với kết quả chưa biết

Một timeout khi gọi authority có thể xảy ra sau commit. Không ghi “timeout = thay password thất bại” rồi cho phép retry như một mutation độc lập.

Tài liệu nên nêu operation reference, nguồn tra kết quả và chính sách reconciliation. Nếu hệ thống chưa biết kết quả, nói đúng là chưa biết và giới hạn hành động tiếp theo.

Điều này cũng cần xuất hiện trong UI và runbook. Thông báo “hãy thử lại” chỉ an toàn khi giao thức đã định nghĩa được thử lại tác động thế nào.

### 10.3. Hủy không tự đảo ngược tác động trước đó

Nếu completion đã commit trước điểm hủy có hiệu lực, hủy transaction không tự khôi phục password cũ.

Tài liệu cần chỉ ra hành động nào có thể bị chặn trước commit và hành động khắc phục nào cần quy trình khác sau commit. Nếu API chỉ mới nhận yêu cầu hủy, không báo CANCELLED như thể mọi authority đã thực thi xong.

Đối với grant được nhiều service kiểm tra, cần nêu cách vô hiệu được truyền và nơi xác nhận hiệu lực. Một cờ cancel ở recovery service chưa chắc chặn được một authority đang giữ dữ liệu cũ.

## 11. Định nghĩa kết quả hoàn tất và hậu điều kiện

### 11.1. Theo dõi riêng những mốc khác nhau

| Mốc | Nguồn xác nhận phù hợp | Giới hạn cần nêu |
|---|---|---|
| Bằng chứng đã được chấp nhận | Hệ thống đánh giá và decision record | Có thể chỉ đủ cho một action, có thời hạn hoặc revision |
| Credential đã thay | Credential authority | Không tự chứng minh quyền cũ ở mọi nơi đã mất hiệu lực |
| Grant đã tiêu thụ | Nơi thực thi vòng đời grant | Phải gắn với đúng mutation và quy tắc retry |
| Yêu cầu thu hồi session đã gửi | Nơi phát hành tác vụ | Chưa phải xác nhận resource đã từ chối |
| Session policy có hiệu lực | Điểm thực thi liên quan | Phạm vi client, resource và loại token phải rõ |
| Thông báo đã gửi | Kết quả trong pipeline/provider | Không tự chứng minh chủ account đã đọc |
| Chủ thể hợp lệ đăng nhập lại | Luồng xác thực và policy tương ứng | Không thay toàn bộ điều tra nếu có dấu hiệu compromise |

Tài liệu phải chỉ ra mốc nào được dùng để trả response cho bước credential và mốc nào được dùng để báo trạng thái phục hồi rộng hơn.

Nếu có công việc bất đồng bộ, người dùng và support cần biết hệ thống đang chờ gì. Không hứa “mọi thiết bị đã bị đăng xuất” khi kiến trúc chỉ mới ghi một tác vụ revoke.

### 11.2. Ma trận tài sản bị ảnh hưởng theo nhánh

Một phụ lục có thể bao gồm:

~~~text
Password:
  Thay credential nào, có giữ trạng thái password cũ hay không?

MFA:
  Factor nào bị loại, factor nào được thêm, có cần kiểm tra sử dụng mới?

Passkey:
  Credential mới được đăng ký theo quyền nào,
  credential cũ được giữ hay vô hiệu theo điều kiện nào?

Recovery code:
  Mã vừa dùng và bộ mã còn lại được xử lý thế nào?

Session và refresh:
  Nhóm nào cần thu hồi, nguồn nào biết hiệu lực, có giới hạn gì?

Recovery channel:
  Địa chỉ mới có được tin cậy ngay không,
  địa chỉ đang bị nghi chiếm được xử lý ra sao?
~~~

Không nhất thiết tự động xóa mọi tài sản sau mọi lần recovery. Tài liệu cần dẫn quy tắc áp dụng cho nhánh và rủi ro tương ứng.

Với passkey, phân biệt đăng ký credential mới với phục hồi credential qua hệ sinh thái đồng bộ. Không hướng dẫn người dùng gửi private key cho support.

### 11.3. Sau recovery có tự đăng nhập không?

Đây là một quyết định phải ghi rõ, không phải chi tiết UI có thể tự chọn.

Nếu sản phẩm yêu cầu quay lại đăng nhập bình thường, tài liệu phải nêu điều kiện và ảnh hưởng tới các context recovery còn lại. Nếu có cơ chế cấp session sau recovery, cần định nghĩa mức quyền, thời hạn, điều kiện nâng quyền và các hạn chế liên quan.

Không dùng một capability chỉ được thiết kế cho password replacement như bearer token truy cập application API.

## 12. Tài liệu người dùng và tài liệu support phải cùng một sự thật

### 12.1. Hướng dẫn người dùng theo bước có thể thực hiện

Một hướng dẫn tốt nên trả lời:

1. Người dùng đang gặp tình huống nào và nên chọn nhánh nào.
2. Họ cần chuẩn bị những phương tiện hoặc bằng chứng nào theo quy trình.
3. Dữ liệu phải nhập ở kênh chính thức nào.
4. Mỗi bước có thể chờ điều gì, và khi nào cần thực hiện hành động khác.
5. Cách nhận biết yêu cầu không do mình khởi tạo.
6. Cách báo lỗi hoặc đi tới hỗ trợ khi không còn phương tiện cần thiết.

Tránh viết “dùng phương thức khác” nếu sản phẩm không chỉ ra phương thức nào có thể dùng hoặc cách tìm nó.

Thời gian dự kiến nên dựa trên khả năng vận hành và điều kiện của nhánh. Không hứa một thời hạn cố định nếu quy trình có thể cần xác minh bổ sung mà chưa có cam kết tương ứng.

### 12.2. Ví dụ thông điệp đúng với mốc kỹ thuật

~~~text
Khi mới nhận yêu cầu:
  Nếu yêu cầu đáp ứng điều kiện, hướng dẫn tiếp theo sẽ được gửi
  qua kênh phù hợp.

Sau khi authority đã commit password:
  Mật khẩu đã được cập nhật. Hãy tiếp tục theo hướng dẫn đăng nhập.

Khi bước xác minh không còn hiệu lực:
  Bước này không còn dùng được. Hãy bắt đầu lại theo hướng dẫn.

Khi cần hỗ trợ:
  Liên hệ qua kênh hỗ trợ chính thức.
  Không gửi mật khẩu, mã khôi phục hoặc mã xác thực trong cuộc trò chuyện.
~~~

Đây là ví dụ lời văn. Sản phẩm cần điều chỉnh theo trạng thái thật và mức thông tin caller được phép biết.

Không bổ sung “tất cả phiên cũ đã bị hủy” vào thông điệp thứ hai nếu chưa có bằng chứng cho toàn phạm vi cần bảo vệ.

### 12.3. Runbook cho support ghi quyền và điều kiện dừng

Một thẻ runbook nên có:

| Thành phần | Nội dung cần ghi |
|---|---|
| Điều kiện bắt đầu | Nhánh nào, ai được tiếp nhận, dữ liệu tra cứu tối thiểu |
| Quyền đọc | Những hồ sơ nào được xem theo tenant và trách nhiệm |
| Quyền hành động | Được ghi nhận, yêu cầu thêm bằng chứng, phê duyệt hay hoàn tất? |
| Điều kiện xác minh | Reference tới policy và nguồn kiểm tra được phép |
| Điểm dừng | Chưa đủ bằng chứng, khác tenant, nghi compromise hoặc scope không rõ |
| Escalation | Vai trò chịu trách nhiệm và thông tin cần chuyển |
| Bằng chứng | Actor, transaction, quyết định và kết quả cần lưu |
| Ngoại lệ | Ai có quyền quyết định, thời hạn và cơ chế kiểm soát |

Một kịch bản support không nên viết “nếu khách hàng có vẻ đáng tin thì bỏ MFA”. Nó cần nêu quy trình thay thế có cơ sở, hoặc nói rõ hiện chưa đủ điều kiện để tiếp tục.

Support không cần xin token dùng một lần để “thử giúp” người dùng. Nếu cần kiểm tra trạng thái, dùng reference không mang quyền và công cụ có authorization.

### 12.4. Nội dung công khai và nội bộ có quyền truy cập riêng

Người dùng cần biết cách bảo vệ mình và hoàn tất bước hợp lệ. Nhân viên được phân quyền có thể cần lý do chi tiết hơn, nhưng vẫn không nhất thiết được thấy bí mật hoặc toàn bộ hồ sơ danh tính.

Không dựa vào việc giấu tên endpoint để bảo đảm an toàn. Kiểm soát phải được thực thi trong hệ thống. Phân quyền tài liệu nhằm bảo vệ dữ liệu và chi tiết vận hành không cần công bố, không thay cho cơ chế bảo mật.

## 13. Gắn tài liệu với yêu cầu, kiểm thử và vận hành

### 13.1. Ma trận traceability nhỏ nhưng có ích

| Yêu cầu minh họa | Phần tài liệu | Nơi thực thi cần chỉ rõ | Kịch bản kiểm tra cần có | Dữ kiện vận hành |
|---|---|---|---|---|
| Grant đúng scope | Thẻ completion | Credential authority | Dùng grant sai account hoặc tenant bị từ chối | Decision và mutation reference |
| Quyền một lần | Vòng đời grant, retry | Ranh giới commit | Hai completion cạnh tranh không tạo mutation ngoài hợp đồng | Consume và operation result |
| Quyết định đúng revision | Preconditions | Nơi đánh giá và authority | Thay bằng chứng sau phê duyệt | Evidence revision và invalidation |
| Hủy có nghĩa rõ | Ma trận race | Nơi ra thứ tự có hiệu lực | Hủy cạnh tranh completion | Requested/effective outcome |
| Không lộ account | Hợp đồng công khai | Endpoint và view trạng thái | So phản hồi giữa các trường hợp phù hợp | Telemetry nội bộ có phân quyền |
| Hoàn tất đúng phạm vi | Hậu điều kiện | Session/resource và messaging | Credential đã đổi nhưng follow-up còn pending | Milestone riêng biệt |

Bảng cho biết cần kiểm tra gì; nó không phải báo cáo rằng các test đã chạy hoặc đã đạt.

Mỗi reference thực tế phải trỏ tới tài liệu, implementation hoặc bằng chứng có thể tìm lại. Một ô ghi “có test” mà không biết test nào không hỗ trợ nhiều cho người duy trì.

### 13.2. Mô tả dữ liệu quan sát được, không sao chép bí mật

Nên ghi tên event, ý nghĩa, nguồn phát, những reference liên kết và quyền truy cập. Phân biệt event yêu cầu với event commit hoặc event hiệu lực.

Ví dụ:

~~~text
credential.change.committed:
  Nguồn: credential authority.
  Ý nghĩa: mutation được định danh đã commit.
  Liên kết: transactionRef, decisionRef, mutationRef.
  Không bao gồm: password mới, grant bearer value, token xác thực.

session.revocation.requested:
  Nguồn: nơi phát hành tác vụ.
  Ý nghĩa: yêu cầu thu hồi đã được ghi nhận để xử lý.
  Không tự chứng minh: mọi resource đã từ chối quyền cũ.
~~~

Tài liệu cũng cần nêu cách tra cứu khi event đến muộn hoặc không có dữ liệu. Thiếu event không tự chứng minh thao tác chưa xảy ra nếu pipeline có khoảng mù.

### 13.3. Liên kết tới runbook thay vì nhét mọi thao tác vào sơ đồ

Khi notification lỗi, sequence diagram có thể trỏ tới runbook xử lý gửi thất bại. Runbook cần thông tin về phạm vi retry, idempotency và escalation.

Không nên sao chép cùng một quy tắc retry vào nhiều tài liệu độc lập mà không có owner. Chúng dễ lệch nhau khi provider hoặc policy đổi.

## 14. Duy trì tài liệu theo vòng đời thay đổi

### 14.1. Một tài liệu cần trạng thái và owner

Các thuộc tính hữu ích:

- Chủ sở hữu nội dung và bên cần tham gia review.
- Revision, thời điểm thay đổi và lý do.
- Trạng thái như proposed, implemented hoặc deprecated.
- Policy version và implementation scope được mô tả.
- Những giả định, hạn chế và câu hỏi còn mở.
- Reference tới quyết định thiết kế khi có lựa chọn quan trọng.

Không cần ghi một “ngày review tiếp theo” nếu không có cơ chế chịu trách nhiệm thực hiện. Điều quan trọng là thay đổi của luồng kích hoạt việc cập nhật tài liệu phù hợp.

### 14.2. Những thay đổi phải xem lại tài liệu

| Thay đổi | Phần dễ bị lỗi thời |
|---|---|
| Thêm recovery channel | Chọn nhánh, bằng chứng, thông báo và dữ liệu nhạy cảm |
| Đổi provider xác minh | Trust boundary, callback và trường hợp lỗi |
| Thay scope hoặc vòng đời grant | Preconditions, replay, completion và hủy |
| Đổi session architecture | Hậu điều kiện và lời hứa đăng xuất |
| Thêm nhánh hỗ trợ | Quyền actor, phê duyệt và audit |
| Đổi cách đăng ký passkey | Quyền binding, xác minh và xử lý credential cũ |
| Thay API hoặc client cũ | Tương thích và những đường gọi còn tồn tại |
| Đổi policy giữa rollout | Phiên bản nào áp dụng cho transaction đang mở |

Một policy mới có thể không tự áp dụng giống nhau cho transaction đã tạo trước đó. Tài liệu cần nêu transaction pin phiên bản hay phải đánh giá lại, cùng điều kiện ngoại lệ nếu có.

### 14.3. Ghi quyết định kiến trúc và hệ quả

Một quyết định ngắn có thể gồm:

~~~text
Bối cảnh:
  Credential authority ở ngoài recovery service.

Lựa chọn:
  Authority kiểm tra completion grant và giữ operation result.

Lý do:
  Cần đặt giới hạn mutation tại nơi thực sự commit credential.

Hệ quả:
  Recovery service phải xử lý timeout bằng tra kết quả có thẩm quyền.
  Không thể suy thất bại chỉ từ lỗi mạng.
  Hợp đồng giữa hai bên cần quản lý phiên bản.
~~~

Đây là mẫu lý giải, không khẳng định kiến trúc nào đã được triển khai.

Ghi hệ quả giúp người sửa một bước hiểu vì sao các bước khác phụ thuộc. Chỉ lưu một sơ đồ mới sẽ làm mất lý do của những giới hạn quan trọng.

### 14.4. Giữ tài liệu lịch sử nhưng đánh dấu rõ

Bản cũ có thể cần cho điều tra, vận hành client còn hỗ trợ hoặc giải thích transaction trong quá khứ. Cần phân biệt lịch sử với hướng dẫn hiện hành.

Một đường link từ runbook phải tới đúng phiên bản phù hợp. Tránh để nhân viên tìm thấy tài liệu deprecated mà không có cảnh báo và áp dụng nó cho luồng hiện tại.

Những bản chụp màn hình, ví dụ payload và câu lệnh trong tài liệu cũng cần kiểm tra trước khi chia sẻ. Không để bí mật hoặc dữ liệu người dùng thật lọt vào lịch sử phiên bản của bộ tài liệu.

## 15. Từ một câu mơ hồ tới đặc tả có thể sử dụng

### 15.1. Câu mô tả ban đầu

~~~text
Sau khi xác minh email, hệ thống reset account và đăng xuất thiết bị cũ.
~~~

Câu này chưa cho biết “xác minh email” chứng minh điều gì, “reset account” gồm tài sản nào, hay “đăng xuất” có hiệu lực ở đâu.

### 15.2. Viết lại theo từng quyết định

~~~text
Phạm vi:
  Nhánh password replacement cho nhóm account được policy chỉ định.

Bằng chứng:
  Kết quả kiểm tra được chấp nhận cho đúng transaction và revision.
  Điều kiện đầy đủ tham chiếu tới policy version có hiệu lực.

Quyền cấp:
  Completion capability chỉ cho thay password của account và tenant đã ràng buộc.
  Không tự cấp quyền thay MFA hoặc truy cập application API.

Mutation:
  Credential authority kiểm tra capability và commit thay password.
  Consume grant cùng operation result theo cơ chế nhất quán đã mô tả.

Hậu điều kiện:
  Session actions thực hiện theo policy và được theo dõi riêng.
  Credential commit không được dùng làm bằng chứng mọi resource đã chặn quyền cũ.

Thông báo:
  Sự kiện recovery phát sinh tác vụ theo quy tắc địa chỉ và giao gửi đã thiết kế.

Lỗi:
  Timeout sau completion được tra lại bằng operation reference.
  Nếu session action chưa có hiệu lực, trạng thái còn lại phải hiển thị đúng.
~~~

Bản viết lại vẫn cần reference tới policy và implementation thật, nhưng đã làm rõ những chỗ phải quyết định. Người đọc có thể chỉ ra câu hỏi còn mở thay vì tự diễn giải “reset account”.

### 15.3. Cách tự đọc một tài liệu mới

Hãy chọn một giao dịch và lần theo:

1. Ai được yêu cầu và ai được quyết định?
2. Bằng chứng nào đủ cho hành động nào?
3. Quyền được ràng buộc ra sao và bị chặn ở đâu?
4. Mutation đã xảy ra được biết từ nguồn nào?
5. Nếu một bước timeout, retry hoặc bị hủy, kết quả nào còn có thể xảy ra?
6. Những gì đã hoàn tất và những gì còn chưa có hiệu lực?

Nếu không trả lời được, thêm thông tin tại đúng phần hợp đồng. Không chỉ thêm chữ “an toàn” hoặc “được xác minh” vào sơ đồ.

## 16. Bài tập vận dụng

### Bài tập 1: Một token cho nhiều việc

Tài liệu gọi tất cả reference, mã kiểm tra email và completion capability là “recovery token”.

Hãy đề xuất cách sửa.

Gợi ý: lập từ vựng theo vai trò; nêu giá trị nào chỉ để tra cứu, giá trị nào mang quyền, scope và nơi kiểm tra. Không để một identifier vô tình trở thành authorization.

### Bài tập 2: Hủy đã nhận nhưng chưa có hiệu lực

API trả “cancelled” ngay khi đưa tác vụ hủy vào queue, trong khi authority vẫn có thể nhận completion grant cũ.

Hãy chỉ ra phần tài liệu và hợp đồng cần làm rõ.

Gợi ý: phân biệt cancel requested với cancel effective; mô tả thứ tự cạnh tranh, nơi xác nhận vô hiệu và thông điệp công khai tương ứng. Nếu muốn hứa đã hủy, cần cơ chế thực thi đáp ứng lời hứa đó.

### Bài tập 3: Nhân viên phải tự nghĩ fallback

Nhánh mất mọi factor chỉ ghi “liên hệ support”. Runbook support không có điều kiện xác minh hay điểm dừng.

Hãy bổ sung những mục cần thiết.

Gợi ý: điều kiện tiếp nhận, quyền actor, nguồn policy, loại bằng chứng, cơ chế quyết định, escalation, audit và trường hợp chưa thể phục hồi. Không coi thao tác thủ công là một cách bỏ qua điều kiện chưa được thiết kế.

### Bài tập 4: Password đổi nhưng session còn hoạt động

UI báo mọi thiết bị đã đăng xuất ngay sau password commit. Một resource chưa thực thi revoke.

Hãy sửa mô tả kết quả.

Gợi ý: tách credential milestone, yêu cầu thu hồi và hiệu lực tại resource. Chỉ dùng thông điệp bao phủ toàn bộ thiết bị khi có cơ sở cho phạm vi đó; ghi việc pending và cơ chế xử lý.

### Bài tập 5: Tài liệu mới nhưng rollout cũ

Một bản tài liệu ghi grant phải kiểm tra evidence revision. Chỉ một phần instance đã triển khai kiểm tra này.

Hãy mô tả cách phản ánh trạng thái.

Gợi ý: ghi scope và phiên bản triển khai, phần còn thiếu cùng rủi ro hoặc biện pháp đang áp dụng. Không gọi trạng thái proposed hoặc rollout một phần là implemented trên toàn hệ thống.

### Bài tập 6: Mất passkey

Một hướng dẫn support hứa gửi lại private key cho người dùng mất thiết bị, dù hệ thống chỉ lưu public key.

Hãy viết lại phạm vi đúng.

Gợi ý: tài liệu cần mô tả đường xác minh cho phép đăng ký credential mới hoặc dùng phương tiện còn lại theo thiết kế. Phân biệt việc đó với phục hồi qua nhà cung cấp đồng bộ; không hứa dịch vụ lấy lại bí mật mà nó không nắm giữ.

## 17. Kết quả cần giữ lại

Một tài liệu recovery hữu ích cho phép người đọc lần theo điều kiện xác minh, quyết định cấp quyền, mutation và các hậu điều kiện mà không tự bổ sung những giả định quan trọng.

Tài liệu cũng phải thể hiện giới hạn: nhánh nào không hỗ trợ, kết quả nào chưa biết, phiên bản nào đang có hiệu lực và ai chịu trách nhiệm khi một bước không hoàn tất. Khi những điều đó rõ ràng, các nhóm có cơ sở chung để triển khai, kiểm tra và hỗ trợ người dùng lấy lại quyền truy cập.

## Tài liệu tham khảo

- [NIST SP 800-63B-4 — Authenticator Event Management](https://pages.nist.gov/800-63-4/sp800-63b/events/): phạm vi account recovery, binding và cơ sở ghi nhận phương thức thay thế.
- [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): hành vi công khai và các đặc tính an toàn của luồng reset password.
- [OWASP — Multifactor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html): các cân nhắc cho reset và thay MFA factor.
