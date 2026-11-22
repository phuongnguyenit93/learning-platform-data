# Tạm dừng workflow để chờ callback hoặc phê duyệt

Một workflow serverless có thể gồm nhiều bước chạy trong vài giây, vài giờ hoặc nhiều ngày. Có bước cần chờ hệ thống đối tác trả kết quả, chờ người quản lý phê duyệt, hoặc chờ một sự kiện bên ngoài trước khi tiếp tục. Nếu giữ Java function đang chạy và dùng sleep() để chờ, hệ thống sẽ tiêu thụ tài nguyên trong lúc không làm việc, dễ vượt timeout và không thể phục hồi tốt khi execution environment bị thu hồi.

Workflow orchestration giải quyết tình huống này bằng trạng thái chờ bền vững (durable wait state). Workflow lưu tiến trình, tạm dừng tại một bước và tiếp tục khi nhận callback, tín hiệu hoặc khi hết thời hạn chờ. Java function chỉ chạy trong những bước cần xử lý; thời gian chờ được quản lý bởi workflow engine và các dịch vụ lưu trạng thái.

Bài học này giải thích cách thiết kế callback và phê duyệt an toàn, cách liên kết phản hồi với đúng workflow đang chờ, và cách xử lý timeout, callback trùng hoặc callback đến muộn.

## 1. Tạm dừng workflow khác với giữ function đang chạy

Một workflow thường có các trạng thái như **RUNNING**, **WAITING**, **SUCCEEDED**, **FAILED** hoặc **CANCELLED**. Khi đến bước cần chờ, orchestration engine lưu trạng thái hiện tại cùng dữ liệu cần thiết để tiếp tục, rồi giải phóng worker đang thực thi.

Khi callback hợp lệ đến, engine chuyển workflow sang trạng thái có thể chạy tiếp và khởi chạy bước kế tiếp. Không cần giữ một thread Java, process hoặc function invocation sống trong suốt thời gian chờ.

~~~mermaid
flowchart TD
    A["Bắt đầu workflow"] --> B["Thực hiện bước chuẩn bị"]
    B --> C["Gửi yêu cầu / tạo approval"]
    C --> D["Lưu trạng thái WAITING"]
    D --> E{"Sự kiện tiếp tục"}
    E -->|Callback hợp lệ| F["Kiểm tra và ghi kết quả"]
    E -->|Hết hạn| G["Nhánh timeout"]
    E -->|Hủy| H["Nhánh cancellation"]
    F --> I["Chạy bước tiếp theo"]
    G --> J["Từ chối / retry / escalation"]
    H --> K["Kết thúc hoặc bù trừ"]
    I --> L["Hoàn tất workflow"]
~~~

Có thể hình dung trách nhiệm của từng thành phần như sau:

- **Workflow engine:** lưu trạng thái, quản lý wait state, timeout và thứ tự các bước.
- **Java function:** thực hiện tác vụ ngắn, gửi yêu cầu ra ngoài, xác thực callback và xử lý nghiệp vụ.
- **Callback endpoint:** nhận phản hồi từ đối tác hoặc giao diện phê duyệt.
- **Database hoặc kho trạng thái:** lưu approval, correlation ID, kết quả callback, audit và outbox khi cần.
- **Queue/event bus:** chuyển callback hoặc tác vụ tiếp theo một cách bền vững nếu kiến trúc dùng xử lý bất đồng bộ.

Một wait state không đồng nghĩa với việc function bị treo. Engine giữ tiến trình workflow; compute chỉ được cấp khi cần chạy bước tiếp theo. Tên gọi và cách tính phí của wait state khác nhau theo nhà cung cấp, vì vậy cần kiểm tra giới hạn thời gian chờ, số execution đang chờ và chi phí lưu trạng thái.

## 2. Những tình huống cần chờ callback

Các ví dụ phổ biến:

| Tình huống | Bên gửi callback | Kết quả workflow cần nhận |
|---|---|---|
| Phê duyệt đơn hàng | Người quản lý qua portal | APPROVED hoặc REJECTED |
| Đối tác xử lý thanh toán | Payment provider | Thành công, thất bại hoặc cần xác minh |
| Xử lý tài liệu bên ngoài | Dịch vụ OCR hoặc kiểm tra | Kết quả, điểm tin cậy hoặc lỗi |
| Giao hàng | Hệ thống logistics | Đã nhận, đang giao, đã giao hoặc ngoại lệ |
| Chờ người dùng bổ sung dữ liệu | Ứng dụng/web portal | Dữ liệu đã gửi hoặc hết hạn |
| Chờ kiểm tra thủ công | Nhân viên vận hành | Kết quả kiểm tra và lý do |

Callback là một thông điệp báo rằng một điều kiện đã xảy ra. Nó có thể đến từ webhook HTTP, message trong queue, API của nhân viên hoặc event từ một dịch vụ khác. Workflow cần biết callback thuộc bước nào, execution nào và có còn hợp lệ hay không.

Không nên để callback chỉ mang một trường như approved=true rồi tin ngay nội dung đó. Cần xác thực nguồn gửi, liên kết với yêu cầu ban đầu, kiểm tra quyền và kiểm tra trạng thái hiện tại của workflow.

## 3. Hai cách liên kết callback với workflow

### 3.1. Task token do workflow engine cấp

Một số orchestration engine cung cấp task token hoặc callback token khi workflow bước vào một task chờ callback. Worker nhận token rồi chuyển nó đến thành phần có trách nhiệm hoàn tất task. Khi callback hợp lệ, dịch vụ tích hợp dùng token để gửi kết quả thành công hoặc thất bại về engine.

Luồng khái quát:

~~~mermaid
sequenceDiagram
    participant W as Workflow Engine
    participant F as Java Function
    participant P as Đối tác / Approver
    participant C as Callback API
    W->>F: Khởi chạy bước chờ, cấp task token
    Note over W: Task được giữ ở trạng thái WAITING
    F->>P: Gửi yêu cầu và thông tin callback an toàn
    P->>C: Gửi kết quả kèm định danh callback
    C->>C: Xác thực nguồn và kiểm tra trạng thái
    C->>W: Gửi task success hoặc task failure
    W->>W: Tiếp tục workflow
~~~

Task token thường có quyền hoàn tất đúng task đang chờ. Ai nắm token có thể có khả năng tiếp tục workflow, vì vậy phải xem token như một bí mật dạng bearer:

- Không ghi token vào log, analytics hoặc thông báo lỗi.
- Không đặt token trực tiếp trong URL có thể xuất hiện trong browser history, proxy log hoặc referrer.
- Mã hóa khi lưu ở database; giới hạn quyền đọc.
- Chỉ chuyển token qua kênh đã xác thực và mã hóa.
- Gắn token với workflow, task, tenant và thời hạn tương ứng.
- Xóa hoặc vô hiệu hóa token sau khi task đã hoàn tất hoặc hết hạn.

Không phải engine nào cũng dùng cùng cơ chế token, API callback hoặc thời hạn. Có engine yêu cầu worker gửi token trong message; có engine cung cấp integration trực tiếp với queue hoặc API. Hãy theo đúng giao thức của nền tảng đang dùng.

### 3.2. Correlation ID do ứng dụng quản lý

Một cách khác là tạo một định danh callback ngẫu nhiên ở tầng ứng dụng, ví dụ approvalId hoặc correlationId. Workflow lưu ID này trong state; callback endpoint nhận ID và tra cứu bản ghi liên kết đến workflow execution cùng bước đang chờ.

Ví dụ:

~~~text
workflow_id: order-2026-00421
step_id: manager-approval
approval_id: apv_7f1d...
tenant_id: tenant-42
status: WAITING
expires_at: 2026-12-02T10:00:00Z
~~~

Correlation ID giúp tìm đúng tiến trình, nhưng bản thân nó không chứng minh người gửi có quyền phê duyệt. Nếu ID có thể được đoán hoặc lấy từ log, attacker có thể thử gửi callback vào workflow khác. Cần thêm xác thực người gọi, authorization trên tài nguyên và kiểm tra trạng thái.

Nên dùng ID đủ ngẫu nhiên để tránh đoán, không nhúng thông tin nhạy cảm vào ID và không coi ID là credential. Nếu muốn dùng một callback secret làm bearer token, cần quản lý nó như task token: entropy cao, lưu trữ bảo vệ, thời hạn rõ ràng và chỉ dùng một lần.

### 3.3. Chọn cách nào?

| Tiêu chí | Task token | Correlation ID |
|---|---|---|
| Liên kết với workflow | Engine quản lý trực tiếp | Ứng dụng tra cứu mapping |
| Tích hợp | Phụ thuộc API của workflow engine | Có thể dùng nhiều engine hoặc callback service |
| Bảo mật | Token thường có quyền hoàn tất task | ID chỉ định vị; cần xác thực và authorization riêng |
| Trạng thái callback | Engine thường quản lý kết quả task | Ứng dụng cần lưu trạng thái và deduplicate |
| Tùy biến nghiệp vụ | Theo giao thức engine | Linh hoạt hơn cho approval, audit và nhiều kênh callback |

Có thể kết hợp cả hai: dùng approval ID cho giao diện và audit, còn task token được giữ an toàn trong backend. Người duyệt chỉ nhìn thấy approval ID; callback service tìm token đã mã hóa và gửi kết quả đến workflow engine.

## 4. Thiết kế quy trình phê duyệt của con người

Một quy trình approval thường có các bước:

1. Workflow tạo yêu cầu phê duyệt và lưu nội dung cần duyệt.
2. Hệ thống gửi thông báo đến người có thẩm quyền.
3. Workflow chuyển sang WAITING_APPROVAL.
4. Người duyệt đăng nhập vào portal, xem đầy đủ dữ liệu và chọn approve hoặc reject.
5. Backend xác minh quyền, ghi quyết định và audit.
6. Callback service đánh thức workflow bằng kết quả.
7. Workflow tiếp tục nhánh tương ứng.

~~~mermaid
sequenceDiagram
    participant O as Order Workflow
    participant D as Approval DB
    participant N as Notification Service
    participant U as Approver Portal
    participant C as Callback Service
    O->>D: Tạo approval WAITING
    O->>N: Gửi thông báo approvalId
    Note over O: Workflow tạm dừng
    U->>D: Tải nội dung yêu cầu
    U->>C: Gửi quyết định approve/reject
    C->>D: Kiểm tra quyền và ghi quyết định
    C->>C: Tạo outbox callback
    C->>O: Resume workflow
    O->>O: Chạy nhánh được chọn
~~~

Thông báo email hoặc chat chỉ nên chứa liên kết đến portal và một mã tham chiếu an toàn. Không nên cho phép người dùng phê duyệt chỉ bằng cách mở một URL công khai chứa task token. Người duyệt cần đăng nhập; backend xác định danh tính từ session hoặc token đã xác minh rồi kiểm tra họ có quyền phê duyệt yêu cầu đó không.

Thứ tự đăng ký và gửi thông báo rất quan trọng. Hãy tạo approval record, liên kết correlation ID/task token và đưa thông báo vào outbox trước khi gửi yêu cầu cho đối tác hoặc người duyệt. Với task token, task chờ của engine phải được khởi tạo trước khi token được phát ra ngoài. Với correlation ID do ứng dụng quản lý, nếu callback có thể đến trước khi workflow hoàn tất việc vào wait state, hãy lưu callback vào inbox ở trạng thái chờ ghép nối rồi chỉ resume sau khi xác nhận workflow đang chờ đúng bước. Cách này tránh mất callback đến sớm.

Cần lưu tối thiểu:

- Approval ID và workflow execution ID.
- Tenant, loại tài nguyên và ID tài nguyên.
- Người được giao duyệt hoặc nhóm có quyền.
- Người thực tế đưa ra quyết định.
- Quyết định, lý do và thời điểm.
- Trạng thái hiện tại, thời hạn và version.
- Audit về việc tạo, xem, chuyển giao, duyệt, từ chối và hết hạn.

Không cho client tự gửi approverId rồi tin đó là người đã duyệt. Backend phải lấy danh tính từ thông tin xác thực đã kiểm tra. Nếu một nhóm người có thể duyệt, cần định nghĩa rõ ai được quyền, có cần một hay nhiều người duyệt, và hai người có thể đưa ra quyết định đồng thời hay không.

### 4.1. Phê duyệt, từ chối và yêu cầu bổ sung

Không nên mô hình hóa mọi kết quả nghiệp vụ thành exception. APPROVED, REJECTED và NEEDS_INFORMATION là các kết quả hợp lệ của quy trình. Workflow có thể rẽ nhánh theo kết quả:

~~~text
WAITING_APPROVAL
    |
    +-- APPROVED ----------> Tiếp tục xử lý đơn hàng
    |
    +-- REJECTED ----------> Ghi lý do và kết thúc
    |
    +-- NEEDS_INFORMATION -> Chờ dữ liệu bổ sung
    |
    +-- EXPIRED -----------> Nhắc lại / escalation / từ chối
~~~

Lỗi kỹ thuật như database không khả dụng hoặc callback service timeout cần retry theo policy kỹ thuật. Quyết định từ chối của người duyệt là kết quả nghiệp vụ, không nên tự động retry như một lỗi hạ tầng.

## 5. Callback endpoint cần xác thực và kiểm tra điều gì?

Một callback endpoint là bề mặt HTTP công khai hoặc được gọi bởi hệ thống ngoài. Trước khi tiếp tục workflow, endpoint cần kiểm tra:

1. **Nguồn gửi:** xác minh chữ ký webhook, OAuth client, mTLS hoặc cơ chế xác thực mà đối tác hỗ trợ.
2. **Tính toàn vẹn:** nếu dùng chữ ký, xác minh trên đúng raw body và đúng thuật toán của nhà cung cấp.
3. **Thời điểm:** kiểm tra timestamp, nonce hoặc cửa sổ chống replay khi giao thức hỗ trợ.
4. **Định danh:** xác định callback thuộc approval ID, task token hoặc correlation ID nào.
5. **Quyền:** kiểm tra caller được phép hoàn tất task hoặc người dùng có quyền duyệt tài nguyên.
6. **Trạng thái:** chỉ chấp nhận callback khi workflow/task đang chờ đúng kết quả.
7. **Thời hạn:** từ chối hoặc xử lý theo policy nếu callback đến sau khi hết hạn.
8. **Payload:** kiểm tra schema, kích thước, kiểu dữ liệu và các giá trị hợp lệ.

Nếu callback đến từ đối tác, dùng allowlist IP chỉ là một lớp bổ sung; IP không thay thế xác minh chữ ký hoặc danh tính. Nếu callback đến từ portal nội bộ, cần kiểm tra session, CSRF protection phù hợp với kiểu xác thực trình duyệt và authorization ở server.

Không cho payload callback chỉ định URL tùy ý để workflow gọi tiếp. Điều này có thể tạo SSRF hoặc biến workflow thành proxy gọi các địa chỉ nội bộ. URL đích phải đến từ cấu hình tin cậy và được kiểm tra theo allowlist.

## 6. Idempotency: xử lý callback trùng

Callback có thể được gửi lại khi bên gửi không nhận được phản hồi, callback service timeout hoặc queue giao lại message. Ví dụ, người duyệt bấm nút hai lần; đối tác gửi lại cùng webhook; hoặc callback service đã gửi tín hiệu đến workflow nhưng bị lỗi trước khi trả 2xx cho caller.

Hãy phân biệt:

- **Delivery ID:** định danh một lần gửi cụ thể của bên gửi.
- **Event ID:** định danh sự kiện từ nguồn, thường ổn định qua retry.
- **Correlation ID:** liên kết callback với workflow hoặc bước đang chờ.
- **Idempotency key:** định danh thao tác nghiệp vụ cần chỉ thực hiện một lần.

Không mặc định bốn ID này là một. Nhiều lần delivery có thể cùng event ID và cùng idempotency key. Một workflow có thể nhận nhiều event khác nhau trong cùng execution.

### 6.1. Trạng thái callback và cập nhật có điều kiện

Một bản ghi approval có thể dùng các trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| WAITING | Đang chờ quyết định |
| APPROVED | Đã được duyệt |
| REJECTED | Đã bị từ chối |
| EXPIRED | Đã quá hạn |
| CANCELLED | Yêu cầu bị hủy |
| CALLBACK_PENDING | Quyết định đã lưu, còn chờ gửi callback đến workflow |
| RESUMED | Workflow engine đã xác nhận nhận kết quả |

Chuyển trạng thái phải được thực hiện nguyên tử. Ví dụ, chỉ cho phép cập nhật từ WAITING sang APPROVED hoặc REJECTED. Hai callback đến đồng thời không được cùng thắng.

Một thao tác SQL khái niệm:

~~~sql
UPDATE approvals
SET status = 'APPROVED',
    decision_by = :actor_id,
    decision_at = :now,
    version = version + 1
WHERE approval_id = :approval_id
  AND status = 'WAITING'
  AND expires_at > :now;
~~~

Ứng dụng kiểm tra số dòng được cập nhật:

- Một dòng: quyết định đã được ghi nhận.
- Không dòng nào: approval không tồn tại, đã hết hạn hoặc đã có quyết định khác; đọc trạng thái hiện tại để phân loại.
- Nhiều hơn một dòng: vi phạm giả định khóa duy nhất và cần xử lý như lỗi dữ liệu.

Nếu cùng một callback được gửi lại với cùng event ID và cùng nội dung quyết định, có thể trả lại kết quả đã xử lý trước đó. Nếu callback thứ hai mang quyết định mâu thuẫn, ví dụ lần đầu APPROVED nhưng lần sau REJECTED, trả conflict hoặc ghi nhận sự kiện bị từ chối; không ghi đè quyết định đầu tiên.

### 6.2. Outbox để không mất tín hiệu resume

Có một khoảng lỗi nguy hiểm: database đã ghi APPROVED nhưng callback service chết trước khi gửi tín hiệu đến workflow engine. Người duyệt thấy đã hoàn tất, nhưng workflow vẫn nằm ở WAITING.

Transactional outbox giải quyết bằng cách ghi quyết định và bản ghi cần gửi callback trong cùng một transaction:

1. Cập nhật approval từ WAITING sang APPROVED.
2. Tạo outbox event chứa approval ID, workflow ID, task reference và kết quả.
3. Commit transaction.
4. Publisher đọc outbox và gửi callback đến workflow engine.
5. Khi engine xác nhận, đánh dấu outbox đã gửi và approval RESUMED.

Nếu publisher gửi callback thành công nhưng lỗi trước khi đánh dấu outbox, nó có thể gửi lại. Vì vậy, callback đến workflow engine cũng cần được bảo vệ bằng task token dùng một lần, idempotency key hoặc cách xử lý duplicate theo API của engine.

Không thể tạo exactly-once xuyên suốt database và workflow engine chỉ bằng một transaction cục bộ. Mục tiêu thực tế là giao ít nhất một lần, ghi trạng thái bền vững và làm cho việc xử lý lặp an toàn.

## 7. Timeout, heartbeat và escalation

Mỗi bước chờ cần có thời hạn. Nếu không, workflow có thể nằm ở WAITING vô thời hạn và chiếm quota execution hoặc làm phát sinh công việc không còn giá trị.

Một cấu hình chờ nên xác định:

- Thời điểm bắt đầu chờ.
- Thời điểm hết hạn tuyệt đối (expiresAt).
- Thời gian chờ tối đa theo policy.
- Có gửi nhắc lại hay không và sau bao lâu.
- Có chuyển cấp (escalation) sang người duyệt khác không.
- Kết quả khi hết hạn: tự từ chối, tự chấp thuận, hủy hoặc chờ xử lý thủ công.
- Ai có quyền gia hạn và giới hạn gia hạn.

Timeout của task, timeout của workflow và timeout của API callback là ba khái niệm khác nhau. Một workflow có thể tồn tại nhiều ngày, trong khi một task worker chỉ chạy vài giây. Callback endpoint cũng cần timeout ngắn để không giữ HTTP request trong lúc workflow engine hoặc database gặp sự cố.

Một số workflow engine có heartbeat cho task đang chờ callback hoặc task worker chạy dài. Heartbeat cho biết worker vẫn hoạt động và có thể kéo dài heartbeat timeout theo policy. Nó không thay thế wait state dài hạn và không có nghĩa cần chạy một function liên tục để chờ người duyệt. Cách tính heartbeat, task timeout và thời gian tối đa phụ thuộc engine.

Ví dụ policy:

~~~text
approval_timeout: 48 hours
reminder_after: 24 hours
escalate_after: 36 hours
on_expiry: REJECT
allow_extension: true
max_extension: 24 hours
~~~

Các giá trị trên chỉ minh họa. Thời hạn phải dựa trên SLA và quy định nghiệp vụ.

Khi timeout xảy ra, workflow cần đi vào một nhánh xác định: gửi nhắc, chuyển người duyệt, từ chối, hủy hoặc tạo tác vụ xử lý thủ công. Không để timeout chỉ biến thành một exception chung khiến workflow retry vô hạn.

## 8. Xử lý race giữa callback, timeout và cancellation

Callback có thể đến đúng lúc workflow hết hạn hoặc người dùng hủy yêu cầu. Nếu chỉ kiểm tra trạng thái rồi cập nhật ở hai thao tác riêng, callback và timeout có thể cùng đọc WAITING và cùng cố hoàn tất.

Cần dùng một chuyển trạng thái nguyên tử có điều kiện. Ví dụ, callback chỉ cập nhật khi trạng thái là WAITING và expires_at > now; timeout chỉ cập nhật khi trạng thái là WAITING và expires_at <= now. Database transaction hoặc conditional write sẽ quyết định một nhánh thắng.

~~~mermaid
stateDiagram-v2
    [*] --> WAITING
    WAITING --> APPROVED: Callback hợp lệ trước deadline
    WAITING --> REJECTED: Người duyệt từ chối
    WAITING --> EXPIRED: Deadline đến trước
    WAITING --> CANCELLED: Yêu cầu bị hủy
    APPROVED --> RESUMED: Workflow nhận callback
    REJECTED --> RESUMED: Workflow nhận callback
    EXPIRED --> RESUMED: Workflow xử lý timeout
    CANCELLED --> [*]
    RESUMED --> [*]
~~~

Nếu callback đến sau EXPIRED, ứng dụng phải có policy rõ ràng: từ chối callback, chuyển sang hàng chờ xử lý thủ công hoặc tạo một workflow mới. Không tự động đổi EXPIRED thành APPROVED chỉ vì callback đến muộn.

Nếu workflow đã bị hủy, callback không được khởi động lại nó trừ khi có một quy trình phục hồi được phê duyệt. Có thể ghi nhận callback muộn vào audit để điều tra. Nếu bên ngoài đã thực hiện side effect, có thể cần một hành động bù trừ.

## 9. Ví dụ Java: nhận quyết định phê duyệt

Ví dụ dưới đây thể hiện cấu trúc của một callback handler và dùng record cùng switch expression (Java 17 trở lên). Các repository và workflow port là adapter do ứng dụng triển khai. Thao tác recordDecisionAndOutbox phải cập nhật trạng thái approval và tạo outbox trong cùng transaction.

~~~java
public enum ApprovalDecision {
    APPROVED,
    REJECTED
}

public record ApprovalCommand(
        String approvalId,
        ApprovalDecision decision,
        String reason
) {}

public record ApprovalResult(
        String status,
        boolean accepted
) {}

public interface ApprovalRepository {
    Optional<Approval> find(String approvalId);
    DecisionResult recordDecisionAndOutbox(
            String approvalId,
            String actorId,
            ApprovalDecision decision,
            String reason
    );
}

public ApprovalResult decide(
        ApprovalCommand command,
        AuthenticatedPrincipal principal) {

    Approval approval = approvalRepository.find(command.approvalId())
            .orElseThrow(() -> new NotFoundException());

    authorization.requireCanApprove(principal, approval);

    DecisionResult result = approvalRepository.recordDecisionAndOutbox(
            approval.id(),
            principal.subject(),
            command.decision(),
            command.reason()
    );

    return switch (result) {
        case RECORDED -> new ApprovalResult("CALLBACK_PENDING", true);
        case SAME_DECISION_ALREADY_RECORDED ->
                new ApprovalResult("CALLBACK_PENDING", true);
        case CONFLICT -> new ApprovalResult("CONFLICT", false);
        case EXPIRED -> new ApprovalResult("EXPIRED", false);
    };
}
~~~

DecisionResult, Approval, AuthenticatedPrincipal, repository và authorization service là kiểu minh họa cần được định nghĩa. Thao tác recordDecisionAndOutbox phải kiểm tra lại tenant, người được giao duyệt, version, trạng thái WAITING và thời hạn trong cùng transaction để tránh quyền hoặc trạng thái thay đổi giữa bước đọc và bước ghi. Ví dụ không gửi callback trực tiếp trong HTTP handler; publisher nền đọc outbox và tiếp tục workflow. Nhờ vậy, endpoint có thể trả response nhanh sau khi quyết định được lưu bền vững.

Với callback từ đối tác, handler cần xác minh chữ ký và event ID trước khi gọi logic tương tự. Với task token của workflow engine, backend tra cứu token liên kết với approval ID rồi gửi task success/failure theo API chính thức của engine. Không để trình duyệt của người duyệt trực tiếp nắm token.

## 10. Callback payload và version hóa hợp đồng

Callback payload nên nhỏ, rõ ràng và có version. Không gửi lại toàn bộ dữ liệu nghiệp vụ nếu workflow có thể đọc dữ liệu mới nhất từ kho chính. Một payload khái niệm:

~~~json
{
  "eventId": "evt-98a1",
  "eventType": "approval.decided",
  "schemaVersion": 1,
  "approvalId": "apv-7f1d",
  "workflowId": "order-2026-00421",
  "correlationId": "order-2026-00421:manager-approval",
  "decision": "APPROVED",
  "occurredAt": "2026-12-01T09:15:00Z"
}
~~~

Worker cần xác minh:

- schemaVersion được hỗ trợ.
- eventType đúng loại callback đang chờ.
- approvalId liên kết với workflow và tenant phù hợp.
- correlationId trỏ đến đúng bước chờ.
- eventId chưa được xử lý hoặc đã xử lý với cùng kết quả.
- occurredAt và thời hạn callback phù hợp policy.

Khi thay đổi schema, hỗ trợ version cũ trong khoảng chuyển tiếp hoặc có bước migrate rõ ràng. Không diễn giải trường thiếu theo một giá trị mặc định nguy hiểm, ví dụ coi thiếu decision là APPROVED.

## 11. Theo dõi workflow đang chờ và khả năng vận hành

Workflow chờ callback có thể tồn tại lâu hơn các bước compute. Cần dashboard và công cụ vận hành để tìm các tiến trình đang chờ, biết chúng chờ ai, chờ điều kiện gì và sẽ hết hạn khi nào.

Các metric hữu ích:

- Số workflow đang ở từng trạng thái wait.
- Tuổi của wait state và số workflow gần hết hạn.
- Thời gian từ lúc gửi yêu cầu đến callback.
- Tỷ lệ callback thành công, duplicate, sai chữ ký và đến muộn.
- Số approval chờ theo tenant, người duyệt và nhóm.
- Số lần reminder và escalation.
- Số outbox event chưa gửi hoặc gửi lỗi.
- Số callback không tìm thấy workflow/task tương ứng.
- Số workflow bị kẹt quá SLA.
- Tỷ lệ timeout, cancellation và xử lý thủ công.

Log cần có workflow ID, step ID, approval ID, correlation ID, event ID và kết quả xác minh. Không log task token, secret, bearer token hoặc thông tin nhạy cảm của hồ sơ. Dùng trace/correlation ID để nối log giữa function, callback service, database và workflow engine.

Cần có quy trình vận hành để xem chi tiết workflow, gửi lại callback đã lưu trong outbox, gia hạn approval nếu được phép hoặc kết thúc một workflow bị kẹt. Mọi thao tác thủ công phải được xác thực, phân quyền và ghi audit.

## 12. Kiểm thử callback và phê duyệt

Không chỉ kiểm thử đường đi thành công. Hãy kiểm tra:

1. Callback hợp lệ đến khi workflow đang chờ.
2. Callback đến trước khi wait state được đăng ký.
3. Callback trùng với cùng event ID và cùng kết quả.
4. Callback trùng nhưng mang quyết định khác.
5. Callback có chữ ký sai hoặc timestamp ngoài cửa sổ.
6. Người không có quyền cố phê duyệt.
7. Callback thuộc tenant hoặc workflow khác.
8. Callback đến sau khi approval hết hạn.
9. Callback đến đồng thời với timeout hoặc cancellation.
10. Database commit thành công nhưng callback publisher bị dừng.
11. Workflow engine nhận callback nhưng publisher lỗi trước khi đánh dấu outbox.
12. Người duyệt bấm hai lần hoặc hai người duyệt cùng lúc.
13. Workflow bị hủy trong khi callback đang được xử lý.
14. Payload callback có schema version không hỗ trợ.
15. Workflow chờ lâu hơn thời hạn dự kiến và cần reminder/escalation.

Dùng clock giả lập để kiểm thử timeout mà không phải chờ thật. Dùng test đồng thời để xác minh conditional update chỉ cho một quyết định thắng. Với integration test, kiểm tra callback token hết hạn, callback trùng và cách engine báo task đã hoàn tất.

## 13. Quy trình thiết kế một wait state an toàn

1. **Xác định điều kiện tiếp tục.** Workflow chờ callback từ đối tác, event từ queue hay quyết định của con người?
2. **Chọn cơ chế liên kết.** Dùng task token do engine cấp hoặc correlation ID do ứng dụng quản lý.
3. **Lưu trạng thái bền vững.** Ghi workflow ID, step ID, tenant, expiry, trạng thái và dữ liệu cần tiếp tục.
4. **Bảo vệ callback.** Xác thực nguồn, kiểm tra chữ ký/token, authorization và schema.
5. **Thiết kế idempotency.** Dùng event ID và conditional state transition để xử lý duplicate.
6. **Thiết kế timeout.** Chọn expiry, reminder, escalation và nhánh hết hạn.
7. **Giải quyết race.** Định nghĩa quy tắc thắng giữa callback, timeout và cancellation bằng cập nhật nguyên tử.
8. **Bảo đảm resume.** Dùng outbox hoặc cơ chế retry bền vững khi gửi tín hiệu đến workflow engine.
9. **Theo dõi vận hành.** Đo thời gian chờ, callback muộn, duplicate và workflow bị kẹt.
10. **Kiểm thử sự cố.** Mô phỏng callback lặp, callback sai, worker chết và workflow bị hủy.

Một wait state tốt có định danh rõ ràng, thời hạn, quyền truy cập, trạng thái có thể quan sát và cách tiếp tục sau lỗi. Callback chỉ là tín hiệu để workflow tiếp tục; quyết định cuối cùng vẫn phải được xác minh và ghi nhận trong hệ thống có thẩm quyền.

## 14. Câu hỏi tự kiểm tra

- Vì sao không nên dùng sleep() để chờ một callback trong Java function?
- Durable wait state giúp giải phóng compute và phục hồi workflow như thế nào?
- Task token khác correlation ID ở điểm nào?
- Vì sao task token cần được bảo vệ như một bí mật dạng bearer?
- Người duyệt cần được xác thực và phân quyền ở đâu?
- Làm thế nào để callback trùng không gửi cùng một quyết định hai lần?
- Transactional outbox giải quyết khoảng lỗi nào giữa database và workflow engine?
- Cần làm gì khi callback đến đồng thời với timeout hoặc cancellation?
- Vì sao không nên cho callback đến muộn tự động mở lại workflow đã hết hạn?
- Những metric nào giúp phát hiện workflow chờ quá lâu hoặc bị kẹt?

Tạm dừng workflow để chờ callback hoặc phê duyệt là một trạng thái nghiệp vụ có vòng đời riêng. Hãy lưu trạng thái chờ bền vững, xác thực mọi tín hiệu tiếp tục, xử lý duplicate bằng idempotency và quy định rõ timeout. Khi đó, workflow có thể chờ lâu mà không giữ function chạy liên tục, đồng thời vẫn phục hồi được khi callback đến trễ hoặc hệ thống gặp lỗi.

