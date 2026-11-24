# State transition documentation — Tài liệu hóa chuyển trạng thái

Bài học thuộc chương **Documentation** của module bảo mật logic nghiệp vụ (`SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY`). Nội dung tập trung vào cách ghi lại vòng đời đối tượng và điều kiện chuyển trạng thái để bảo vệ quy tắc nghiệp vụ trước việc bỏ bước, sửa dữ liệu sau phê duyệt, thao tác sai quyền hoặc thực hiện trùng.

Một sơ đồ có các ô `DRAFT → APPROVED → COMPLETED` giúp nhìn tổng quan nhưng chưa trả lời được ai được duyệt, phiên bản nào đã được duyệt, lúc nào được hủy và retry có tạo thêm tác động không. Những phần chưa được mô tả thường trở thành giả định khác nhau giữa người viết API, worker, kiểm thử và vận hành.

**State transition documentation** cần mô tả hợp đồng của từng chuyển trạng thái: nguồn, đích, tác nhân, điều kiện, thay đổi dữ liệu, tác động, lỗi và bằng chứng. Tài liệu có giá trị khi đủ cụ thể để triển khai, kiểm thử và giải thích sự cố mà không phải tự đoán quy tắc còn thiếu.

Sau bài học, bạn cần có thể:

- Định nghĩa trạng thái theo sự thật nghiệp vụ và ranh giới đối tượng.
- Phân biệt command yêu cầu hành động với event ghi nhận việc đã xảy ra.
- Viết bảng chuyển trạng thái có quyền theo đối tượng, guard và bất biến.
- Ghi rõ transaction, điểm chấp nhận thực thi và tác động bên ngoài.
- Tài liệu hóa retry, idempotency, cạnh tranh, timeout và kết quả chưa rõ.
- Chuyển quy tắc thành các ca kiểm thử thành công, bị chặn và có lỗi.
- Duy trì liên kết giữa tài liệu, policy, code, migration và bằng chứng vận hành.

## 1. Tài liệu chuyển trạng thái là một hợp đồng bảo mật

Một đối tượng nghiệp vụ có thể đi qua nhiều bước, nhưng chỉ một phần các đường đi được cho phép. Kẻ lạm dụng có thể gọi API cuối trực tiếp, gửi trạng thái giả, dùng lại approval cũ hoặc chạy hai command cùng lúc.

Tài liệu phải giúp xác định điều kiện nào được cưỡng chế phía server, thay vì chỉ mô tả thứ tự thao tác trên giao diện.

OWASP Transaction Authorization khuyến nghị kiểm soát các chuyển trạng thái được phép, giữ đúng thứ tự của luồng phê duyệt và có kiểm tra trước thực thi. Bài học dùng những mục tiêu đó để xây dựng hợp đồng chuyển trạng thái cụ thể. [OWASP: Transaction Authorization](https://cheatsheetseries.owasp.org/cheatsheets/Transaction_Authorization_Cheat_Sheet.html).

Ví dụ câu mô tả còn thiếu:

~~~text
Người dùng bấm Approve để đơn chuyển sang APPROVED.
~~~

Câu có thể kiểm thử rõ hơn:

~~~text
Checker có quyền trên đúng tenant và yêu cầu được phê duyệt
một request đang PENDING_APPROVAL ở workflowVersion đã đọc.
Checker phải độc lập với maker theo policy.
Approval gắn với contentVersion và dữ liệu trọng yếu đã xem xét.
Nếu cập nhật cạnh tranh làm version đổi, không commit approval cũ.
~~~

Điểm khác biệt nằm ở khả năng xác định quyết định đúng, các trường hợp phải chặn và tác động được phép xuất hiện.

## 2. Chốt ranh giới và từ vựng trước khi vẽ sơ đồ

### 2.1. Xác định đối tượng đang có vòng đời

Trong ví dụ xuyên suốt, đối tượng chính là **yêu cầu hoàn tiền**. Đơn hàng gốc, approval, lần gửi provider và ledger có quan hệ với nó nhưng không nhất thiết dùng chung một enum trạng thái.

Tài liệu cần ghi:

| Thuộc tính | Câu hỏi cần trả lời |
|---|---|
| Đối tượng | Trạng thái này thuộc request, payment hay execution attempt? |
| Scope | Định danh có duy nhất theo tenant hay toàn hệ thống? |
| Nguồn có thẩm quyền | Service và dữ liệu nào quyết định trạng thái nghiệp vụ? |
| Ranh giới nhất quán | Các bản ghi nào được thay đổi trong cùng transaction? |
| Nguồn bên ngoài | Provider xác nhận điều gì và hệ thống xác minh bằng cách nào? |
| Phiên bản | Version nội dung và version workflow có cùng nghĩa không? |

Tránh dùng `status` của provider trực tiếp làm trạng thái nội bộ khi hai bên có ngữ nghĩa khác nhau. Ví dụ provider báo “accepted” có thể mới là đã nhận xử lý, chưa chứng minh hoàn tiền thành công.

### 2.2. Phân biệt command, event và transition

~~~text
Command:
  ApproveRefund, RequestExecution, CancelRefund.
  Là yêu cầu; có thể bị từ chối.

Event:
  RefundApprovalCommitted, ProviderRefundConfirmed.
  Ghi nhận sự kiện theo bằng chứng đã xác minh.

Transition:
  Trạng thái nguồn + command/event + ngữ cảnh
  → quyết định + trạng thái đích + thay đổi/tác động được phép.
~~~

Một HTTP request được nhận không đồng nghĩa command đã được chấp nhận. Một event mang tên “confirmed” từ nguồn không xác thực cũng chưa được coi là sự thật nghiệp vụ.

### 2.3. Tách ba loại phiên bản

| Loại | Mục đích |
|---|---|
| `contentVersion` | Nhận diện nội dung trọng yếu như số tiền, loại tiền và người nhận đã được trình duyệt |
| `workflowVersion` | Phát hiện thay đổi cạnh tranh của aggregate và chuyển trạng thái |
| `policyVersion` | Giải thích bộ quy tắc dùng cho quyết định |

Một lần chuyển `APPROVED → QUEUED` có thể tăng workflowVersion nhưng giữ contentVersion. Không làm approval mất hiệu lực chỉ vì nhầm hai version này; cũng không dùng một version nội dung cũ để bỏ qua tranh chấp workflow.

## 3. Định nghĩa trạng thái bằng điều đã đúng

Ví dụ dưới đây là hợp đồng bài học, không phải workflow bắt buộc cho mọi hệ thống hoàn tiền.

| Trạng thái | Điều trạng thái khẳng định | Điều không được tự suy ra |
|---|---|---|
| `DRAFT` | Nội dung đang được soạn, chưa có approval dùng để thực thi | Maker đã có quyền thực thi |
| `PENDING_APPROVAL` | Một phiên bản nội dung đã được trình để checker xem xét | Đã có checker đồng ý |
| `APPROVED` | Có approval cho nội dung cụ thể theo policy | Approval còn hạn ở mọi thời điểm tương lai |
| `QUEUED` | Quyết định tiếp nhận thực thi đã commit và có ý định bền vững | Lệnh đã tới provider hoặc đã tạo tác động |
| `SUBMITTED` | Provider đã xác nhận tiếp nhận operation, chưa có kết quả cuối | Hoàn tiền đã thành công |
| `UNKNOWN` | Không đủ căn cứ kết luận kết quả của một lần thực thi có thể đã đi ra ngoài | Chắc chắn thất bại hoặc chắc chắn chưa gửi |
| `SUCCEEDED` | Có kết quả thành công đã được xác minh và ghi nhận | Có thể chạy lại cùng thao tác để “đồng bộ” |
| `FAILED` | Có kết quả cuối xác nhận không tạo tác động hoàn tiền cho operation này | Mọi HTTP lỗi đều đủ để gán trạng thái này |
| `REJECTED` | Checker đã từ chối yêu cầu theo workflow | Có thể bỏ bước duyệt bằng cách sửa status |
| `CANCELLED` | Yêu cầu được hủy hợp lệ trước ranh giới tiếp nhận thực thi | Một lệnh đã được provider nhận cũng đã bị hủy |

Trong hợp đồng này, `SUCCEEDED`, `FAILED`, `REJECTED`, `CANCELLED` là các trạng thái kết thúc. Một nghiệp vụ mới nếu được phép cần định danh và kiểm tra riêng; không tự mở lại đối tượng kết thúc bằng cập nhật status.

### 3.1. Đừng để một enum che mọi chiều trạng thái

Có thể cần quản lý riêng:

~~~text
businessState: vòng đời yêu cầu.
dispatchAttempt: đã claim, đang gửi, đã nhận phản hồi hay mất kết quả.
operationalHold: có đang bị tạm giữ vì sự cố hay không.
evidenceStatus: kết quả đã có đủ căn cứ hay còn thiếu đối soát.
~~~

Ví dụ một request vẫn `QUEUED` nhưng có operational hold đang bật. Hold không có nghĩa request bị hủy hay provider đã thất bại. Mỗi chiều cần ngữ nghĩa và guard riêng, tránh tạo một enum khổng lồ với mọi tổ hợp hoặc làm mất sự thật quan trọng.

## 4. Ghi bất biến xuyên suốt vòng đời

Trước khi liệt kê từng cạnh, viết các điều luôn phải được bảo vệ trong scope:

1. Actor chỉ được hành động trên đối tượng thuộc tenant và phạm vi được phép.
2. Checker độc lập với maker theo đơn vị danh tính mà policy yêu cầu.
3. Approval chỉ áp dụng cho đúng request, contentVersion và dữ liệu trọng yếu đã duyệt.
4. Tiền đã hoàn cộng phần giữ chỗ chưa tính vào tiền đã hoàn không vượt giá trị được phép hoàn của đơn gốc.
5. Một operation nghiệp vụ không tạo tác động trùng do retry hoặc message giao lại.
6. Kết quả chưa rõ không được tự đổi thành thất bại chỉ để gửi lại.
7. Trạng thái kết thúc không bị lùi vì event cũ hoặc callback trùng.
8. Chuyển trạng thái thành công, liên kết quyết định và ý định phát event cần nhất quán theo ranh giới đã thiết kế.

Nếu một cạnh hợp lệ làm vi phạm bất biến trên đối tượng liên quan, chỉ kiểm tra state của request là chưa đủ. Ví dụ hai refund request khác nhau cùng giữ chỗ trên một đơn cần kiểm soát cạnh tranh tại nguồn hạn mức chung.

Với mỗi bất biến, ghi nơi cưỡng chế: authorization service, aggregate, câu lệnh cập nhật, unique constraint, ledger hoặc provider adapter. Tài liệu không được ngụ ý một guard ở giao diện bảo vệ tất cả các đường thực thi.

## 5. Sơ đồ tổng quan và giới hạn của sơ đồ

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> DRAFT: edit
    DRAFT --> PENDING_APPROVAL: submit
    PENDING_APPROVAL --> APPROVED: approve
    PENDING_APPROVAL --> REJECTED: reject
    PENDING_APPROVAL --> DRAFT: amend
    APPROVED --> DRAFT: amend
    APPROVED --> PENDING_APPROVAL: resubmit
    DRAFT --> CANCELLED: cancel
    PENDING_APPROVAL --> CANCELLED: cancel
    APPROVED --> CANCELLED: cancel
    APPROVED --> QUEUED: request execution
    QUEUED --> SUBMITTED: provider accepted
    QUEUED --> UNKNOWN: result uncertain
    SUBMITTED --> UNKNOWN: result uncertain
    QUEUED --> SUCCEEDED: verified success
    SUBMITTED --> SUCCEEDED: verified success
    UNKNOWN --> SUCCEEDED: verified success
    QUEUED --> FAILED: verified final no effect
    SUBMITTED --> FAILED: verified final no effect
    UNKNOWN --> FAILED: verified final no effect
    SUCCEEDED --> [*]
    FAILED --> [*]
    REJECTED --> [*]
    CANCELLED --> [*]
~~~

Sơ đồ thể hiện các cạnh có thể được xem xét. Nó không trao quyền đi theo cạnh và không chứa đủ guard để triển khai.

Các cạnh trực tiếp `QUEUED → SUCCEEDED/FAILED` có chủ đích: một kết quả cuối có thể tới trước khi service kịp lưu acknowledgement trung gian. Hệ thống vẫn phải nối đúng operation, xác minh nguồn và xử lý cạnh tranh, thay vì chặn một kết quả thật chỉ vì thiếu trạng thái trung gian.

`UNKNOWN` chỉ áp dụng khi có căn cứ về một lần thực thi có thể đã phát sinh nhưng chưa rõ kết quả. Một job chưa từng được thử gửi, chỉ đang chờ queue, không tự trở thành UNKNOWN vì đã chờ lâu.

## 6. Bảng chuyển trạng thái là phần hợp đồng chi tiết

Mỗi dòng có một ID để nối với code, test và bằng chứng. Trong bảng, maker/checker là vai trò nghiệp vụ được giải quyết từ danh tính có thẩm quyền; tên vai trò không thay thế quyền theo đối tượng.

| ID | Nguồn → đích | Command/event | Actor và guard chính | Thay đổi/tác động được phép |
|---|---|---|---|---|
| T-01 | DRAFT → DRAFT | EditDraft | Maker có quyền, version khớp, dữ liệu hợp lệ | Tăng contentVersion và workflowVersion; chưa tạo ý định thực thi |
| T-02 | DRAFT → PENDING_APPROVAL | SubmitForReview | Maker có quyền; nội dung đầy đủ, version khớp | Ghi snapshot được trình duyệt |
| T-03 | PENDING_APPROVAL → APPROVED | ApproveRefund | Checker có quyền đúng đối tượng, độc lập maker, đúng snapshot/version | Ghi approval và căn cứ quyết định; chưa gửi provider |
| T-04 | PENDING_APPROVAL → REJECTED | RejectRefund | Checker có quyền và đáp ứng phân tách của workflow | Ghi từ chối; kết thúc yêu cầu |
| T-05 | PENDING_APPROVAL/APPROVED → DRAFT | AmendRefund | Maker có quyền, chưa tiếp nhận thực thi, version khớp | Thay nội dung, tăng contentVersion, vô hiệu liên kết approval đang dùng |
| T-06 | APPROVED → PENDING_APPROVAL | ResubmitForReview | Maker có quyền, chưa tiếp nhận thực thi | Trình lại cùng nội dung để duyệt mới; approval cũ không dùng cho lần trình này |
| T-07 | DRAFT/PENDING_APPROVAL/APPROVED → CANCELLED | CancelRefund | Actor có quyền hủy, version khớp, chưa qua ranh giới tiếp nhận thực thi | Kết thúc yêu cầu; không gửi lệnh mới |
| T-08 | APPROVED → QUEUED | RequestExecution | Actor có quyền thực thi; approval đúng nội dung và còn hiệu lực tại điểm quyết định; hạn mức đủ | Giữ chỗ, liên kết operation/idempotency, tiêu thụ quyền dùng approval và ghi outbox nhất quán |
| T-09 | QUEUED → SUBMITTED | ProviderAccepted | Handler tin cậy; acknowledgement thuộc đúng operation và chưa có kết quả cuối | Ghi tham chiếu provider; không tuyên bố thành công |
| T-10 | QUEUED/SUBMITTED → UNKNOWN | ExecutionResultUncertain | Có attempt tương ứng và thiếu căn cứ kết quả cuối | Giữ liên kết operation và giữ chỗ cần thiết; yêu cầu đối soát |
| T-11 | QUEUED/SUBMITTED/UNKNOWN → SUCCEEDED | VerifiedRefundSuccess | Kết quả được xác minh, đúng scope/operation/số tiền, chưa ghi tác động này | Ghi hoàn tất, chuyển phần giữ chỗ tương ứng thành đã hoàn; phát event nhất quán |
| T-12 | QUEUED/SUBMITTED/UNKNOWN → FAILED | VerifiedFinalNoEffect | Có kết quả cuối có thẩm quyền chứng minh không tạo tác động cho operation | Ghi thất bại cuối và giải phóng phần giữ chỗ theo policy |

Mọi cạnh không được mô tả là bị từ chối mặc định hoặc phải được làm rõ trước khi cho phép. Không tự suy rằng quyền admin có thể đặt bất kỳ trạng thái đích nào.

### 6.1. Self-transition và no-op khác nhau

T-01 giữ nguyên tên trạng thái nhưng thay đổi dữ liệu hợp lệ, có version và audit tương ứng. Một callback thành công trùng sau `SUCCEEDED` có thể chỉ trả kết quả đã lưu, không tạo transition nghiệp vụ mới và không tăng workflowVersion theo hợp đồng này.

Không dùng self-transition chung như `ANY → ANY` để cho mọi command đi qua. Mỗi trường hợp giữ nguyên trạng thái vẫn cần xác định có thay đổi dữ liệu hoặc tác động hay không.

### 6.2. Trạng thái nguồn không thay thế tất cả guard

T-08 chỉ được xem xét từ `APPROVED`, nhưng còn cần quyền trên đối tượng, approval đúng version, nguồn thời gian phù hợp, hạn mức và chống trùng. Một request có `APPROVED` vẫn có thể bị chặn vì approval hết hạn hoặc dữ liệu không khớp.

Tương tự, event từ provider chỉ được áp dụng sau xác thực nguồn, chống replay theo thiết kế và đối chiếu operation. Client gọi endpoint rồi gửi `state=SUCCEEDED` không tạo bằng chứng để đi theo T-11.

## 7. Viết một transition specification đầy đủ

T-08 là ranh giới quan trọng: hệ thống nhận trách nhiệm thực thi một yêu cầu đã duyệt. Một specification có thể dùng mẫu sau. Đây là ví dụ tài liệu, không phải cấu hình thực thi của framework cụ thể.

~~~yaml
transitionId: T-08
name: Accept refund execution
sourceState: APPROVED
targetState: QUEUED
trigger: RequestExecution
authority: refund-application-service
identityScope: authenticated tenant and authorized refund request
input:
  - requestId
  - approvalId
  - expectedWorkflowVersion
  - idempotencyKey
guards:
  - actor may execute this request in this tenant
  - stored state and workflow version match
  - approval binds the current reviewed content
  - approval is usable at the authoritative decision point
  - refundable balance can be reserved without violating the shared limit
  - a new operation is not created for an existing idempotent command
atomicChanges:
  - create the durable execution intent
  - bind and consume the approval for that intent
  - reserve the refundable amount
  - change request state and workflow version
  - store the idempotency result and outbox intent
externalEffects:
  - dispatched asynchronously using the committed operation identity
denialEffects:
  - no new execution intent or financial reservation
  - record the denied attempt according to the audit contract
recovery:
  - retry reads the existing operation for the same command
  - uncertain external outcomes are reconciled before any new send
~~~

Tài liệu production cần gắn tên field/câu lệnh/handler thực tế và các reason code theo hợp đồng của hệ thống. Phần `guards` không được biến thành nhãn chung mà không có nơi cưỡng chế.

### 7.1. Những field thường bị bỏ sót

| Nội dung | Câu hỏi specification cần trả lời |
|---|---|
| Dữ liệu trọng yếu | Số tiền, loại tiền và người nhận lấy từ đâu, có cho client sửa trong command không? |
| Điểm thời gian | Approval cần còn hạn lúc tiếp nhận hay tới lúc tạo tác động bên ngoài? |
| Tranh chấp | Nếu request hoặc hạn mức chung đổi giữa đọc và ghi thì ai thắng? |
| Cấu hình lỗi | Không xác minh được quyền, thời gian hoặc policy thì từ chối hay tạm giữ? |
| Idempotency | Cùng key/cùng payload, khác payload và key đang xử lý được phân biệt thế nào? |
| Bằng chứng | Event nào chỉ là attempt, event nào chứng minh quyết định đã commit? |
| Phục hồi | Ai đối soát UNKNOWN và căn cứ nào cho phép kết luận cuối? |

Trong ví dụ, command RequestExecution không cho phép đổi số tiền hoặc người nhận. Tài liệu API phải ghi cách xử lý field không được phép: từ chối theo schema hoặc chính sách được định nghĩa; không mass-assign payload vào aggregate.

### 7.2. Chốt thời điểm hiệu lực của approval

Hợp đồng bài học chọn kiểm tra approval tại **điểm quyết định tiếp nhận thực thi** ở T-08. Approval được gắn và tiêu thụ cho ý định bền vững; worker dùng ý định đó để thực hiện. Đây không phải cam kết rằng provider hoàn tất trước hạn approval.

Instant dùng cho guard được lấy từ nguồn có thẩm quyền theo thiết kế; nó không tự bằng thời điểm commit vật lý. Tài liệu phải ghi giới hạn này, nguồn thời gian và hành vi khi không đủ tin cậy.

Nếu nghiệp vụ thật yêu cầu quyền hoặc approval còn hiệu lực tại lần gửi ra ngoài, cần thêm guard tại ranh giới đó, cách xử lý khi hết hạn sau T-08 và tác động lên phần giữ chỗ. Không để API và worker âm thầm dùng hai hợp đồng thời gian khác nhau.

Một ý định đã được tiếp nhận hợp lệ không tự bị xóa chỉ vì giao message muộn. Những hạn chế mới như khóa khẩn cấp hoặc thu hồi trước thực thi phải có policy, điểm cưỡng chế và đường phục hồi riêng được mô tả.

## 8. Tài liệu hóa quyền theo đối tượng và guard

### 8.1. Ma trận quyền phải đi cùng scope

| Hành động | Actor điển hình | Điều kiện bổ sung |
|---|---|---|
| Soạn/chỉnh nội dung trước thực thi | Maker được cấp quyền | Đúng tenant, đúng đối tượng, trạng thái cho phép và version khớp |
| Phê duyệt/từ chối | Checker được cấp quyền | Phân tách với maker và đúng phạm vi tài nguyên |
| Tiếp nhận thực thi | Caller có quyền execute hoặc service được ủy quyền | Approval, hạn mức và operation hợp lệ |
| Ghi kết quả provider | Handler kỹ thuật được tin cậy | Xác thực bằng chứng và nối đúng operation |
| Đối soát | Service/nhân sự có quyền recovery | Không được tự biến thao tác đọc kết quả thành gửi lệnh mới |
| Sửa chữa dữ liệu đặc biệt | Quy trình quản trị đã xác định | Scope hẹp, bằng chứng và kiểm soát theo policy riêng |

Không ghi “admin được làm mọi thứ” thay cho một hợp đồng phục hồi. Đường quản trị có thể tạo tác động tương tự đường thường nên cũng cần bảo vệ bất biến và audit phù hợp.

### 8.2. Nguồn dữ liệu cho guard

~~~text
tenant/actor:
  từ ngữ cảnh xác thực và dữ liệu server có thẩm quyền.

state, workflowVersion, contentVersion:
  từ dữ liệu bền vững được đọc/ghi theo cơ chế tranh chấp đã chọn.

approval:
  từ bản ghi gắn với snapshot trọng yếu đã được review.

hạn mức:
  từ nguồn kiểm soát chung có cơ chế chống đặt giữ chỗ vượt mức.

provider outcome:
  từ callback/tra cứu được xác thực và đối chiếu nội dung.
~~~

Các trường `tenantId`, `role`, `approved`, `state` hoặc `now` do client gửi không tự là căn cứ tin cậy. API có thể nhận một định danh đối tượng nhưng vẫn phải giải quyết quyền trên đối tượng đó phía server.

### 8.3. Guard lỗi cũng là một nhánh cần viết

Phân biệt:

- Guard trả false: đủ căn cứ để từ chối điều kiện nghiệp vụ cụ thể.
- Nguồn guard không khả dụng hoặc không đáng tin: chưa đủ căn cứ quyết định.
- Lỗi kỹ thuật sau khi đã commit: có thể cần trả hoặc tra cứu operation đã tồn tại.

Không gom mọi exception thành `FAILED` của request. Một lỗi lấy policy trước T-08 có thể để request ở APPROVED với một lần thử bị hoãn; nó không chứng minh một execution đã thất bại ở provider.

## 9. Transaction và cạnh tranh phải được mô tả cụ thể

### 9.1. Tách kiểm tra thuần với quyết định có hiệu lực

~~~text
Đọc request đang APPROVED.
Kiểm tra approval còn dùng được.
Hai request đồng thời cùng thấy điều kiện đúng.
Cả hai tạo operation khác nhau nếu không có kiểm soát chung.
~~~

Một bảng transition đúng không ngăn race. Tài liệu cần chỉ rõ điểm quyết định được bảo vệ bởi version, lock, conditional update, unique constraint hoặc cơ chế tương ứng.

SQL sau chỉ minh họa việc ràng buộc state/version trên request. Named parameter phải được bind bởi lớp truy cập dữ liệu:

~~~sql
UPDATE refund_request
SET business_state = 'QUEUED',
    workflow_version = workflow_version + 1,
    execution_operation_id = :operationId
WHERE tenant_id = :tenantId
  AND request_id = :requestId
  AND business_state = 'APPROVED'
  AND workflow_version = :expectedWorkflowVersion;
~~~

Nếu số dòng cập nhật bằng 0, không được tiếp tục gửi provider như thể đã thắng. Service phải giải quyết xung đột, trạng thái hiện tại hoặc kết quả idempotency theo hợp đồng, sau khi kiểm tra quyền.

Câu lệnh trên chưa kiểm tra approval, hạn mức hoặc chống tạo operation trùng. Những điều kiện đó phải nằm trong ranh giới nhất quán phù hợp cùng việc tạo ý định, giữ chỗ và outbox. Không copy đoạn SQL rồi xem là đã bảo vệ toàn bộ T-08.

### 9.2. Mô tả xung đột giữa các command

| Cạnh tranh | Kết quả cần chốt |
|---|---|
| Approve và amend | Không tạo approval cho nội dung đã bị thay ngoài snapshot được duyệt |
| Cancel và request execution | Chỉ một quyết định hợp lệ thắng tại ranh giới chung; không vừa hủy thành công vừa tiếp nhận thực thi mới |
| Hai request execution khác key trên cùng request | Chỉ một operation được tiếp nhận theo hợp đồng một lần |
| Hai refund request khác nhau trên cùng đơn | Tổng giữ chỗ và đã hoàn không vượt hạn mức chung |
| Callback thành công và timeout handler | Kết quả cuối không bị lùi về UNKNOWN |
| Hai kết quả provider khác nhau | Không ghi đè tùy tiện; cần quy tắc xác minh và xử lý mâu thuẫn |

Tài liệu cần ghi cách xử lý version conflict: trả lỗi cho caller, retry có kiểm tra lại hay tra cứu kết quả đã tồn tại. Retry không được tự bỏ guard vừa thất bại.

### 9.3. Transaction nội bộ không bao phủ provider

Commit dữ liệu và outbox cùng transaction hỗ trợ giữ ý định nhất quán. Việc gửi lệnh ra ngoài vẫn có cửa sổ crash, timeout và giao lặp.

Không giữ transaction database mở trong thời gian chờ người duyệt hoặc chờ đối soát kéo dài. Không mô tả rollback nội bộ như cách thu hồi một tác động đã được provider chấp nhận. Nếu cần bù trừ, tài liệu phải định nghĩa một nghiệp vụ bù có định danh, quyền và bất biến riêng.

## 10. Luồng bất đồng bộ và trạng thái chưa rõ

### 10.1. Mỗi ranh giới cần có failure story

| Vị trí lỗi | Điều có thể đã xảy ra | Cách mô tả phục hồi |
|---|---|---|
| Trước commit T-08 | Chưa có ý định thực thi bền vững | Retry command theo idempotency; không đoán đã nhận |
| Commit xong nhưng HTTP response mất | Ý định đã tồn tại | Tra cứu theo operation/key; không tạo ý định mới |
| Outbox chưa được chuyển đi | Request đã QUEUED nhưng chưa được dispatcher nhận | Phát lại ý định đã commit, giữ cùng định danh |
| Worker chết trước lần gửi đã được xác định là chưa bắt đầu | Chưa tạo tác động ngoài theo bằng chứng hiện có | Nhận lại công việc theo cơ chế claim và chống trùng |
| Worker chết hoặc timeout sau điểm có thể đã gửi | Provider có thể đã làm nhưng chưa có kết quả | Giữ operation, chuyển UNKNOWN khi đủ căn cứ, đối soát trước lần gửi mới |
| Provider xác nhận tiếp nhận nhưng chưa có kết quả cuối | SUBMITTED vẫn đang chờ kết luận | Poll/callback theo hợp đồng; không coi pending là thất bại |
| Kết quả đã commit, consumer nhận event lại | Tác động đã ghi nhận | No-op theo event/operation identity; không ghi thêm tác động |

Cần biết “điểm có thể đã gửi” được nhận diện bằng attempt record, dispatcher protocol hoặc bằng chứng nào. Một trạng thái QUEUED đơn lẻ không đủ kết luận chưa có request nào ra ngoài nếu worker có thể crash trước khi lưu acknowledgement.

### 10.2. UNKNOWN là nghĩa vụ điều tra, không phải giấy phép retry mới

Tài liệu phục hồi cần nêu:

~~~text
Ai sở hữu operation chưa rõ?
Tra cứu provider bằng định danh nào?
Kết quả nào được coi là cuối và có thẩm quyền?
Không tìm thấy record ở một lần tra cứu có đủ kết luận chưa tạo tác động không?
Giữ chỗ/hạn mức được giữ hay giải phóng trong lúc chờ?
Khi provider không thể kết luận thì chuyển tới quy trình nào để xử lý tiếp?
~~~

Trong hợp đồng bài học, UNKNOWN giữ phần giữ chỗ cần thiết và không tự chuyển FAILED theo thời gian chờ. Muốn đi theo T-12 phải có bằng chứng cuối phù hợp, không chỉ “không thấy kết quả” ở một nguồn có thể chậm.

Nếu cần gửi lại cùng operation, phải mô tả rõ điều kiện an toàn và hợp đồng chống trùng phía provider. Không suy rằng một key nội bộ tự bảo vệ mọi tác động ngoài hoặc tồn tại vô hạn ở provider.

### 10.3. Kết quả đến muộn và mâu thuẫn

Sau SUCCEEDED, callback trùng cùng kết quả được nhận diện và không tạo transition mới. Callback cũ báo pending không được làm request quay về SUBMITTED.

Trong mô hình này, acknowledgement tiếp nhận đến muộn khi request đã UNKNOWN có thể bổ sung bằng chứng, nhưng chưa đủ để kết luận cuối hoặc tự mở một cạnh UNKNOWN → SUBMITTED. Cách lưu thông tin bổ sung đó cần được định nghĩa riêng với thay đổi businessState.

Nếu một kết quả mới mâu thuẫn trạng thái kết thúc đã lưu, cần cô lập, đối soát và áp quy trình sửa sai có kiểm soát. Không âm thầm bỏ qua bằng chứng mới đáng tin, cũng không cho callback tùy ý ghi đè terminal state.

## 11. Idempotency và ý nghĩa của việc lặp command

| Tình huống | Hợp đồng cần ghi |
|---|---|
| Cùng key, cùng nội dung, đã có kết quả | Trả/tra cứu kết quả phù hợp sau kiểm tra quyền; không tạo operation mới |
| Cùng key, nội dung khác | Báo xung đột; không sửa operation cũ thành ý định mới |
| Cùng key, đang xử lý | Trả trạng thái đang xử lý hoặc cách chờ/tra cứu có giới hạn |
| Key khác, cùng request đã được tiếp nhận | State/ràng buộc nghiệp vụ vẫn ngăn lần tiếp nhận thứ hai |
| Key đã hết retention | Không suy ra đối tượng được thực hiện lại; xét state và định danh nghiệp vụ bền vững |
| Message giao lại | Phân biệt attempt mới với operation nghiệp vụ đã tồn tại |

Fingerprint của command cần bao gồm dữ liệu có ý nghĩa theo scope: hành động, tenant, request, approval và nội dung liên quan. Không dùng một key toàn cục thiếu tenant hoặc không ràng buộc payload.

Tài liệu cũng cần phân biệt “nhận lại cùng kết quả” với “thực hiện lại kiểm tra hiện tại để tạo tác động mới”. Ví dụ retry T-08 sau khi approval đã hết hạn có thể trả operation đã được tiếp nhận hợp lệ trước đó; điều này không cấp quyền cho command mới dùng approval hết hạn.

Idempotency không thay authorization. Người biết operation ID hoặc key của người khác vẫn phải bị chặn truy cập và hành động ngoài quyền.

## 12. Ghi rõ các đường bị từ chối và hợp đồng API

Một tài liệu chỉ có các cạnh thành công sẽ để trống nhiều hành vi bảo mật. Cần liệt kê các yêu cầu không hợp lệ có chủ đích:

| Thao tác bị thử | Lý do phải chặn theo hợp đồng | Tác động không được xuất hiện |
|---|---|---|
| DRAFT → QUEUED bằng RequestExecution | Chưa được phê duyệt | Không tạo operation, giữ chỗ hoặc outbox thực thi |
| Đổi `state` trong payload thành APPROVED | Client không quyết định state nguồn có thẩm quyền | Không tự sinh approval |
| Approve trên snapshot cũ | Version/nội dung đã thay đổi | Không tạo approval cho dữ liệu chưa được checker xem xét |
| APPROVED → SUCCEEDED bằng API người dùng | Không có bằng chứng provider hợp lệ | Không ghi tác động thành công hoặc event hoàn tất giả |
| CANCELLED → QUEUED bằng retry key mới | Đối tượng đã kết thúc | Không tạo tác động mới |
| UNKNOWN → FAILED chỉ vì timeout | Chưa có kết quả cuối chứng minh không tạo tác động | Không giải phóng giữ chỗ rồi gửi lại tùy tiện |
| SUCCEEDED → SUBMITTED từ callback cũ | Event đến muộn không được lùi trạng thái kết thúc | Không mở lại operation |
| Hủy sau khi T-08 đã thắng | Đã qua ranh giới hủy trực tiếp của hợp đồng này | Không trả hủy thành công rồi để ý định cũ tiếp tục không được theo dõi |

API nên nhận command có ý nghĩa như ApproveRefund hoặc CancelRefund. Một endpoint chung `PATCH /refunds/{id}` cho phép đặt `businessState` cần được xem xét đặc biệt vì dễ biến state machine thành một tập giá trị client có thể chọn.

Nếu có công cụ sửa chữa đặc biệt, tài liệu phải chỉ rõ quyền, điều kiện, dữ liệu cần xác minh và audit; không dùng nó như nhánh mặc định cho một command thường bị chặn.

### 12.1. Reason code và phản hồi có giới hạn

Ví dụ nhóm reason có thể dùng trong hợp đồng:

~~~text
STATE_NOT_ALLOWED
WORKFLOW_VERSION_CONFLICT
APPROVAL_CONTENT_MISMATCH
APPROVAL_NOT_USABLE
OBJECT_ACCESS_DENIED
IDEMPOTENCY_PAYLOAD_CONFLICT
OUTCOME_REQUIRES_RECONCILIATION
~~~

Ánh xạ HTTP status và body phải được định nghĩa nhất quán cho ứng dụng. Chỉ cung cấp state, version hoặc chi tiết đối tượng sau khi xác minh caller có quyền biết chúng; thông báo lỗi không được trở thành cách dò request của tenant khác.

Một command bị chặn trước khi có thay đổi nghiệp vụ không tạo event thành công. Audit lần thử có thể được lưu theo hợp đồng riêng; không coi audit đó là một transition nghiệp vụ đã commit.

## 13. Bằng chứng của mỗi transition

Một transition được tài liệu hóa tốt phải có cách quan sát kết quả thực tế. Record minh họa cho T-08 đã commit:

~~~json
{
  "eventType": "REFUND_EXECUTION_ACCEPTED",
  "eventId": "event-example-81",
  "transitionId": "T-08",
  "decisionId": "decision-example-81",
  "tenantId": "tenant-T",
  "requestId": "refund-R",
  "fromState": "APPROVED",
  "toState": "QUEUED",
  "workflowVersionBefore": 12,
  "workflowVersionAfter": 13,
  "contentVersion": 3,
  "approvalId": "approval-A",
  "operationId": "operation-K",
  "actorRef": "actor-example-E",
  "authorizationRef": "authorization-example-81",
  "policyVersion": "policy-example-7",
  "commitOutcome": "COMMITTED"
}
~~~

Đây là fixture, cần bổ sung thời gian và metadata nguồn theo thiết kế thực tế. Event phải được gắn với dữ liệu đã commit bằng cơ chế phù hợp; một log được ghi trước commit không tự có giá trị như record trên.

Bằng chứng nên trả lời được:

- State/version nào được dùng làm precondition và state/version nào thực sự được lưu.
- Actor thực, scope quyền và căn cứ delegation nếu có.
- Approval, nội dung trọng yếu và policy dùng cho quyết định.
- Operation/idempotency và ý định outbox liên quan.
- Kết quả bên ngoài đến từ đâu, đã được xác minh như thế nào.
- Đường từ chối, conflict, rollback và phục hồi thuộc loại nào.

Không ghi token, OTP hoặc dữ liệu thanh toán đầy đủ vào audit chỉ để dễ debug. Dùng reference và quyền truy cập phù hợp cho snapshot nhạy cảm.

Nếu record từ chối được chèn trong transaction rồi bị rollback cùng transaction, bằng chứng có thể mất. Tài liệu cần nêu đường ghi denial phù hợp, cách cảnh báo khi audit lỗi và điều kiện nào buộc ngăn một transition thành công vì chưa lưu được bằng chứng cần thiết.

Thứ tự sự kiện cần dựa trên version/sequence, liên kết nhân quả và nguồn thời gian thích hợp. Không nối toàn bộ workflow chỉ bằng cách sắp timestamp từ các node rồi giả định đó là thứ tự chính xác.

## 14. Chuyển tài liệu thành ca kiểm thử

OWASP WSTG-BUSL-06 khuyến nghị xem tài liệu luồng để tìm cách bỏ bước hoặc thay đổi thứ tự và xây dựng misuse case tương ứng. Bảng transition là đầu vào hữu ích để tạo những ca thử đó. [OWASP WSTG: Testing for the Circumvention of Work Flows](https://wstg.owasp.org/stable/4-Web_Application_Security_Testing/10-Business_Logic_Testing/06-Testing_for_the_Circumvention_of_Work_Flows/).

### 14.1. Ma trận coverage theo transition

Với mỗi cạnh quan trọng, nên có:

| Nhóm ca | Điều cần kiểm tra |
|---|---|
| Đường hợp lệ | State đích, version, dữ liệu và tác động đúng |
| Sai state nguồn | Không đi tắt qua bước còn thiếu |
| Sai actor/scope | Role đúng tên nhưng sai đối tượng vẫn bị chặn |
| Guard false | Từng điều kiện quan trọng bị vi phạm thì không có tác động trái phép |
| Nguồn guard lỗi | Không tự coi thiếu dữ liệu là allow |
| Replay | Cùng command/event không tạo tác động mới |
| Cạnh tranh | Các command không thể cùng thắng ngoài hợp đồng |
| Crash/timeout | State bền vững và đường phục hồi đúng |
| Kết quả đến muộn | Terminal state và số tác động không bị thay đổi sai |
| Đường thay thế | Admin, batch, worker hoặc API cũ không bỏ guard |

Không chỉ đo số dòng của bảng đã có một test happy path. Cần biết test ở lớp nào: hàm policy thuần, repository thật, queue, adapter hoặc provider sandbox. Một mock không chứng minh điều kiện đồng thời trên database được cưỡng chế đúng.

### 14.2. Ví dụ: sửa dữ liệu sau duyệt

~~~gherkin
Scenario: Approval cũ không áp dụng sau khi maker sửa nội dung
  Given refund-R đang APPROVED
    And contentVersion là 3 và workflowVersion là 12
    And approval-A gắn với contentVersion 3
  When maker được phép sửa số tiền bằng AmendRefund với expectedWorkflowVersion 12
  Then request trở về DRAFT
    And contentVersion là 4 và workflowVersion là 13
    And approval-A không được dùng để thực thi nội dung mới
  When RequestExecution được gửi với approval-A cho request hiện tại
  Then command bị chặn
    And không có operation, giữ chỗ hoặc outbox thực thi mới
~~~

Reason cụ thể phụ thuộc thứ tự kiểm tra đã định nghĩa, ví dụ state không cho phép trước khi tới kiểm tra approval. Test cần giữ hợp đồng về tác động; không tự yêu cầu mọi hệ thống công khai tất cả lý do cùng lúc.

### 14.3. Ví dụ: cạnh tranh giữa hủy và tiếp nhận thực thi

~~~text
Fixture:
  R ở APPROVED, workflowVersion 12, approval và hạn mức hợp lệ.

Chạy đồng thời:
  CancelRefund(expectedVersion=12)
  RequestExecution(expectedVersion=12, key=K)

Expected:
  Chỉ một quyết định chuyển trạng thái thắng theo cơ chế đã chọn.

Nếu cancel thắng:
  R là CANCELLED, không có ý định/giữ chỗ thực thi mới.

Nếu execution thắng:
  R là QUEUED, có đúng một operation và phần giữ chỗ tương ứng;
  cancel không được trả thành công như thể đã hủy ý định đó.
~~~

Dùng barrier/latch hoặc cơ chế điều khiển phù hợp để tái hiện vị trí tranh chấp; không dựa vào sleep để đoán thứ tự. Đối soát cả dữ liệu request, hạn mức và outbox sau khi các transaction hoàn tất.

### 14.4. Ví dụ: timeout sau khi provider có thể đã xử lý

~~~text
Operation-K đã được tiếp nhận ở T-08.
Worker gửi lệnh, provider có thể đã tạo tác động nhưng phản hồi bị mất.
Hệ thống không có kết quả cuối đáng tin.

Expected:
  Giữ liên kết operation và phần giữ chỗ cần thiết.
  Ghi UNKNOWN khi điều kiện T-10 đúng.
  Retry không tạo operation mới hoặc dùng key mới để gửi lại tùy tiện.
  Khi kết quả thành công được xác minh, đi theo T-11 đúng một lần.
  Callback trùng không ghi thêm tác động.
~~~

Các mô hình state có thể hỗ trợ sinh chuỗi test như submit, amend, approve, execute và replay. Mô hình test vẫn cần được kiểm tra với policy nghiệp vụ; nếu copy nguyên lỗi từ code sang mô hình thì hai bên khớp nhau cũng chưa chứng minh quy tắc đúng.

## 15. Giữ tài liệu, code và policy nhất quán

### 15.1. Liên kết đủ để lần theo một quy tắc

Một bản tài liệu được quản lý có thể ghi:

~~~text
Workflow ID và phiên bản tài liệu.
Owner nghiệp vụ, owner kỹ thuật và người review bảo mật.
Phiên bản policy, thời điểm hiệu lực và quyết định thiết kế liên quan.
Transition ID → command/event handler → nơi cưỡng chế dữ liệu.
Transition ID → test case → bằng chứng quan sát.
Thay đổi tương thích, kế hoạch migration và đường phục hồi.
~~~

Trong ví dụ, T-08 có thể trỏ tới application service tiếp nhận thực thi, repository bảo vệ version/giữ chỗ và bộ test race. Không chỉ trỏ tới controller vì tác động có thể được kích hoạt từ worker hoặc batch.

### 15.2. Quy trình khi thay đổi workflow

1. Nêu rule hoặc bất biến cần thay đổi và lý do.
2. Cập nhật định nghĩa state, bảng transition và đặc tả guard/tác động.
3. Liệt kê dữ liệu hiện có và message đang chờ bị ảnh hưởng.
4. Điều chỉnh code, schema, policy và các đường thực thi tương ứng.
5. Bổ sung/đổi test cho hành vi mới, cạnh bị cấm và lỗi phục hồi.
6. Review ảnh hưởng tới authorization, idempotency và nguồn bằng chứng.
7. Ghi phiên bản hiệu lực, triển khai và cách phát hiện khác biệt sau deploy.

Không chấp nhận một cạnh mới chỉ xuất hiện trong code mà tài liệu vẫn ghi cấm. Cũng không đổi bảng thành “được phép” chỉ để hợp thức hóa một đường bypass chưa được đánh giá.

### 15.3. Phân biệt hợp đồng với chi tiết triển khai

Hợp đồng cần ổn định ở mức nghiệp vụ: ai được làm gì, điều kiện nào và tác động nào được phép. Tên class, queue hoặc bảng có thể đổi nhưng liên kết tới nơi cưỡng chế cần được cập nhật.

Nếu có nhiều bản sơ đồ và bảng, ghi bản nào là nguồn mô tả chuẩn và cách tạo/cập nhật các bản khác. Một sơ đồ sinh từ enum chỉ cho thấy danh sách state, chưa thể tự sinh đầy đủ guard về quyền và tiền.

## 16. Migration, phiên bản hỗn hợp và công cụ phục hồi

Thêm state mới có thể ảnh hưởng consumer cũ, mobile client, dashboard, script vận hành và dữ liệu đang xử lý. Tài liệu thay đổi phải xét cả lúc nhiều phiên bản ứng dụng cùng chạy.

| Tình huống | Điều cần tài liệu hóa |
|---|---|
| Consumer cũ gặp state mới | Giữ an toàn, bảo toàn dữ liệu, cảnh báo hoặc tạm giữ theo hợp đồng; không mặc định thành DRAFT |
| Đổi tên state | Cách tương thích serialization/storage và cách đọc lịch sử |
| Tách một state thành nhiều state | Căn cứ phân loại dữ liệu cũ, trường hợp chưa đủ bằng chứng |
| Thêm yêu cầu approval | Cách xử lý request/ý định đã tồn tại và policy hiệu lực |
| Message cũ tới sau deploy | Phiên bản schema, command/event semantics và cách ánh xạ |
| Script sửa chữa | Actor, phạm vi, precondition, transaction, audit và kiểm tra sau chạy |

Không ánh xạ mọi UNKNOWN cũ sang FAILED chỉ để migration có đủ giá trị enum mới. Việc thiếu bằng chứng về tác động vẫn là thiếu bằng chứng sau khi schema đổi.

Nếu dữ liệu trạng thái được lưu bằng mã hoặc enum, hợp đồng lưu trữ cần tránh cách diễn giải thay đổi khi thứ tự khai báo đổi. Mapping phải có ý nghĩa rõ và được quản lý cùng migration.

Một nghiệp vụ bù trừ sau SUCCEEDED không nên bị mô tả như “quay lại APPROVED”. Hãy định nghĩa đối tượng/operation bù, quyền thực hiện và liên kết tới tác động gốc. Việc giữ lịch sử giúp phân biệt sửa sai có chủ đích với việc thực hiện lại ngoài ý muốn.

## 17. Sai lầm thường gặp

| Sai lầm | Rủi ro | Cách cải thiện |
|---|---|---|
| Chỉ có sơ đồ happy path | Không biết cách xử lý đường cấm và lỗi | Bổ sung bảng, guard, denial và phục hồi |
| Định nghĩa state bằng tên màn hình | Backend và worker hiểu khác nhau | Định nghĩa theo sự thật nghiệp vụ |
| Cho client gửi state đích để cập nhật | Bỏ qua command và quy tắc nghiệp vụ | Nhận command, quyết định state phía server |
| Role đúng tên được coi là đủ quyền | Thao tác chéo tenant/đối tượng | Ghi scope và authorization theo tài nguyên |
| Approval là một boolean | Dùng lại phê duyệt cho giá/người nhận khác | Gắn snapshot, contentVersion và policy |
| Không tách version nội dung và workflow | Phê duyệt mất hiệu lực sai hoặc bỏ sót race | Định nghĩa từng loại version |
| Transaction được xem là chống mọi race | Vẫn tranh chấp trên state hoặc hạn mức chung | Nêu lock/CAS/ràng buộc và kiểm thử tương ứng |
| HTTP timeout được gán FAILED | Có thể gửi lại tác động đã xảy ra | Có UNKNOWN và đường đối soát |
| Callback cũ được phép ghi đè state | Lùi terminal state hoặc lặp tác động | Guard theo operation/version và tính đơn điệu theo hợp đồng |
| Retry key mới được coi là nghiệp vụ mới | Thực hiện lại cùng đối tượng | Giữ bất biến và định danh nghiệp vụ bền vững |
| Hủy nội bộ được coi là hủy provider | Báo thành công sai hoặc mất nghĩa vụ | Chốt ranh giới hủy, xác minh tác động và bù khi cần |
| Admin có nút đặt mọi status | Đường bypass không có hợp đồng | Quy trình sửa chữa riêng, scope hẹp và audit |
| Tài liệu đổi nhưng không xét dữ liệu/message cũ | Nhiều phiên bản diễn giải khác nhau | Lập kế hoạch tương thích và migration |

## 18. Bài tập thực hành

### Bài tập 1: Làm rõ trạng thái

Chọn một đối tượng như đơn hàng, yêu cầu hoàn tiền hoặc yêu cầu cấp quyền. Với mỗi state, viết điều nó khẳng định, điều chưa thể suy ra, nguồn có thẩm quyền và trạng thái kết thúc.

### Bài tập 2: Viết bảng transition

Liệt kê command/event, actor, quyền theo đối tượng, guard, tác động và reason khi từ chối. Đánh dấu những cạnh không được phép để tìm đường bỏ bước hoặc gọi API trực tiếp.

### Bài tập 3: Đặc tả ranh giới quan trọng

Chọn một cạnh tạo tác động nhạy cảm. Viết điểm quyết định, nguồn thời gian, approval/content binding, transaction, hạn mức và idempotency. Nêu bảo đảm nào chưa đạt được với provider bên ngoài.

### Bài tập 4: Race và event đến muộn

Dựng hai command xung đột và một callback đến sau timeout. Chốt expected về state, version, số operation, phần giữ chỗ và số tác động. Giải thích vì sao chỉ assert HTTP status là chưa đủ.

### Bài tập 5: Thay đổi workflow

Giả sử bổ sung một tầng duyệt trong khi hệ thống đang có request APPROVED, job QUEUED và operation UNKNOWN. Lập cách xử lý từng nhóm, phiên bản policy, consumer cũ và bằng chứng cần giữ; không tự gán tất cả về DRAFT.

## 19. Tự kiểm tra tài liệu

- Đối tượng, scope và nguồn trạng thái có thẩm quyền được xác định rõ.
- Mỗi state có ngữ nghĩa nghiệp vụ, không chỉ tên hiển thị.
- Command, event, attempt và transition được phân biệt.
- Bất biến về quyền, approval, tiền và chống trùng được ghi rõ.
- Có sơ đồ tổng quan cùng bảng cạnh, guard và tác động chi tiết.
- Các cạnh không được phép và cách phản hồi đã được mô tả.
- Version nội dung, workflow và policy có nghĩa riêng.
- Ranh giới transaction, tác động ngoài và điểm hủy được chốt.
- Race, retry, callback trùng, timeout và UNKNOWN có hợp đồng phục hồi.
- Tác động và bằng chứng được kiểm tra cùng nhau trong ca thử phù hợp.
- Liên kết tài liệu, nơi cưỡng chế, test và lịch sử thay đổi có thể lần theo.
- Migration và nhiều phiên bản cùng chạy không được bỏ qua.

Tài liệu chuyển trạng thái tốt giúp cả người xây dựng lẫn người vận hành biết một hành động có được phép hay không và vì sao. Khi các điều kiện, ranh giới tác động và đường phục hồi được ghi rõ, những giả định dễ bị khai thác trong workflow có thể trở thành quy tắc cụ thể để cưỡng chế và kiểm thử.
