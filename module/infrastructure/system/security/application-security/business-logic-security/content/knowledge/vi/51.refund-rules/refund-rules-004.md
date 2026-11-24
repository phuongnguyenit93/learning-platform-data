# Phê duyệt hoàn tiền (Refund approval)

Phê duyệt hoàn tiền là quyết định cho phép thực hiện một nghĩa vụ hoàn cụ thể, trong phạm vi và điều kiện đã xác định. Nó không phải một cờ `approved=true` do client gửi và cũng không chứng minh tiền đã được trả về cho khách.

Trong chương **Refund Rules**, chủ đề này bảo vệ điểm giao giữa quyền hạn con người và tác động tài chính của hệ thống. Một quy trình có thể kiểm tra đúng số tiền nhưng vẫn bị lạm dụng nếu người đề nghị tự duyệt, sửa người nhận sau khi duyệt hoặc dùng cùng approval cho nhiều lần hoàn. Bài học tập trung vào business invariants, state machine, quyền theo đối tượng, transaction, idempotency và kiểm thử các tình huống tấn công logic.

Sau bài học, bạn có thể:

- Phân biệt đủ điều kiện hoàn, được phê duyệt và đã thực hiện hoàn.
- Thiết kế phê duyệt gắn với một snapshot bất biến của nội dung nghiệp vụ.
- Áp dụng nguyên tắc tách người đề nghị và người duyệt, hạn mức và phạm vi quyền.
- Phân xử các yêu cầu đồng thời để không duyệt hoặc hoàn vượt ngân sách.
- Xử lý thay đổi nội dung, thu hồi, hết hạn và kết quả thanh toán chưa rõ mà vẫn giữ được audit.

## 1. Ba câu hỏi phải được trả lời riêng

| Câu hỏi | Loại quyết định | Ví dụ |
| --- | --- | --- |
| Khoản này có được hoàn không? | Eligibility | Hàng trả đã được tiếp nhận theo quy trình, capture có thật và còn phần được hoàn |
| Ai được cho phép hoàn khoản này? | Approval | Người duyệt đúng phạm vi, đủ hạn mức và không phải người đề nghị |
| Tiền đã được hoàn chưa? | Execution | Operation hoàn đã có kết quả thành công được xác nhận từ nguồn thanh toán |

Ba câu trả lời có thể khác nhau tại cùng thời điểm:

```text
eligibility = ELIGIBLE
approval = APPROVED
execution = PENDING
```

Trạng thái trên có nghĩa khoản hoàn đã được phép nhưng chưa có kết quả tiền cuối cùng. Giao diện không được hiển thị “đã hoàn tiền” chỉ vì quy trình phê duyệt xong.

Ngược lại, một giao dịch còn số dư có thể hoàn không đồng nghĩa mọi người dùng đều được quyết định hoàn số đó. Ngân sách tài chính là giới hạn cần thiết, không thay thế quyền hạn và căn cứ nghiệp vụ.

## 2. Xác định đối tượng cần phê duyệt

### 2.1. Request, snapshot, approval và operation

Một thiết kế có thể tách các đối tượng:

| Đối tượng | Vai trò |
| --- | --- |
| Refund case | Hồ sơ nghiệp vụ, như hủy hàng, trả hàng hoặc thu thừa |
| Refund request | Đề nghị hoàn một phạm vi cụ thể của hồ sơ |
| Request revision/snapshot | Phiên bản nội dung được người duyệt xem xét |
| Approval decision | Phiếu quyết định của một chủ thể trên đúng revision |
| Approval permit | Quyền thực thi được cấp sau khi đủ điều kiện phê duyệt |
| Refund obligation/operation | Nghĩa vụ và thao tác thực hiện khoản hoàn đã được phép |
| Execution attempt | Lần thử kỹ thuật gọi hệ thống thanh toán |

Một case có thể có nhiều request từng phần hợp lệ. Một request có thể có nhiều revision sau khi sửa nội dung. Nhiều lần thử mạng không được tạo nhiều nghĩa vụ hoàn cho cùng khoản đã duyệt.

### 2.2. Snapshot phải chứa những gì?

Nội dung trọng yếu nên bao gồm:

```text
tenant_id
refund_case_id
request_id + revision
order_id + order_line_allocations
source_capture_ids + source_amount_allocations
refund_amount + currency
refund_destination_policy + verified_destination_reference
reason_code
eligibility_evidence_references + relevant_versions
requester_business_identity
policy_version + required_approval_route
```

Các tham chiếu chứng từ phải gắn với phiên bản hoặc bằng chứng được bảo vệ phù hợp. Nếu một tài liệu sau khi duyệt vẫn có thể bị thay toàn bộ mà giữ cùng ID, snapshot chỉ lưu ID đó chưa đủ để biết người duyệt đã xem nội dung nào.

Không cần sao chép dữ liệu thanh toán nhạy cảm vào snapshot. Dùng tham chiếu đã xác minh và thông tin hiển thị được phép, nhưng phải đủ để phân biệt nguồn tiền, đích hoàn và phạm vi quyết định.

Server tạo snapshot chuẩn hóa và fingerprint. Người duyệt gửi request ID, revision và quyết định; server đối chiếu với bản đang có. Một hash do client tự tính không tự bảo đảm nội dung đã được duyệt là đúng.

### 2.3. Trường nào thay đổi thì phải duyệt lại?

Theo mô hình của bài học, các thay đổi trọng yếu tạo revision mới và làm các phiếu cũ không còn được tính cho revision mới, gồm:

- Số tiền, tiền tệ hoặc phân bổ vào capture nguồn.
- Đơn, dòng hàng, số lượng hoặc căn cứ được hoàn.
- Đích nhận tiền hay phương thức hoàn.
- Lý do có ảnh hưởng tới chính sách.
- Bằng chứng hoặc điều kiện eligibility liên quan đến quyết định.
- Nội dung làm thay đổi tuyến duyệt hoặc điều kiện kiểm soát.

Kể cả giảm số tiền cũng cần được xử lý theo quy tắc phiên bản đã công bố, không tự tái sử dụng phiếu trên một snapshot khác. Ghi chú bổ sung không ảnh hưởng quyết định có thể được lưu dạng append-only nếu chính sách cho phép.

Approval không phải một chữ ký cho “mọi nội dung tương lai” của request.

## 3. Các bất biến bảo mật nghiệp vụ

### 3.1. Phê duyệt chỉ có hiệu lực trên đúng nội dung

Một quyết định có thể được ràng buộc bởi:

```text
ApprovalBinding = (
    tenant_id,
    request_id,
    revision,
    snapshot_fingerprint,
    policy_version
)
```

Khi nội dung không còn khớp, approval không được dùng để tạo operation theo nội dung mới. Endpoint thực thi cũng không nhận một `amount` hoặc `destination` tùy ý rồi dựa vào một approval ID hợp lệ để bỏ qua đối chiếu.

### 3.2. Người đề nghị không tự tạo đủ điều kiện duyệt

Với quy tắc tách người đề nghị và người duyệt:

```text
requester_business_identity != counted_approver_business_identity
```

Nếu cần hai người duyệt, phải có hai danh tính nghiệp vụ khác nhau, đúng vai trò và phạm vi. Hai phiên đăng nhập hoặc hai tài khoản liên kết cùng một người không mặc nhiên là hai người độc lập.

Service account thực thi không được trở thành cách che người khởi tạo. Audit cần giữ cả người đề nghị ban đầu và service thực hiện thay. Việc service ID khác requester ID không có nghĩa đã thỏa điều kiện tách trách nhiệm.

Cơ chế này không tự ngăn được thông đồng giữa những người khác nhau. Nó tạo ràng buộc, bằng chứng và điểm kiểm soát để giảm nguy cơ một người tự quyết toàn bộ luồng.

### 3.3. Số đã hoàn và số đang giữ chỗ không vượt giới hạn

Với một capture, trong mô hình cơ bản chưa xét tranh chấp hoặc điều chỉnh đặc biệt:

```text
C = số tiền đã thu thành công
R = số tiền đã hoàn thành công
H = số tiền được giữ chỗ cho các nghĩa vụ hoàn chưa giải quyết

Khi cấp thêm quyền hoàn x:
    x > 0
    R + H + x <= C
```

Giới hạn hoàn theo case hoặc dòng hàng có thể nhỏ hơn phần tiền còn lại của capture. Ví dụ, mới chấp nhận trả một sản phẩm thì không được dùng số dư của cả đơn để hoàn thêm những sản phẩm khác.

Cần bảo vệ cả hai lớp:

```text
Tiền nguồn còn được phép hoàn
VÀ
Quyền hưởng hoàn còn lại của căn cứ nghiệp vụ
```

Nếu có tranh chấp, reversal, nhiều phương thức hoặc hạn chế theo nguồn tiền, mô hình phải bổ sung các điều kiện liên quan. Công thức cơ bản không thay thế chính sách của nghiệp vụ và tích hợp.

### 3.4. Một approval không tạo nhiều nghĩa vụ hoàn

Permit được cấp cho đúng một nghĩa vụ nghiệp vụ có nội dung đã duyệt. Retry kỹ thuật không tiêu thêm tiền và không sinh nghĩa vụ mới.

Có thể dùng các ràng buộc như:

```text
UNIQUE (tenant_id, request_id, revision, effective_approver_identity)
UNIQUE (tenant_id, approval_permit_id) trên nghĩa vụ hoàn được tạo
UNIQUE (tenant_id, refund_obligation_id, financial_effect_type)
```

Đây là ý tưởng ràng buộc, không phải DDL hoàn chỉnh. Nếu cho phép rút phiếu hoặc thay quyết định, cần lưu hành động kế tiếp có liên kết và xác định rõ phiếu nào còn hiệu lực, thay vì ghi đè lịch sử.

Không unique trên toàn order vì có thể cần hoàn nhiều lần từng phần. Tính duy nhất phải bám đúng request, căn cứ và hiệu ứng.

### 3.5. Không được hợp thức hóa một khoản hoàn sai bằng cách duyệt

Approval không làm một capture không tồn tại trở thành có thật, không biến authorization chưa thu thành số dư có thể hoàn và không cho phép vượt số tiền hoặc quyền theo đối tượng.

Các điều kiện nền tảng phải được kiểm tra ở server khi đề nghị, khi chốt phê duyệt và tại điểm thực thi phù hợp. Người duyệt có thẩm quyền vẫn phải làm việc trong các bất biến của hệ thống.

## 4. Thiết kế chính sách phê duyệt theo phạm vi

### 4.1. Vai trò chung chưa đủ

Quyền `refund:approve` nên được đánh giá cùng các thuộc tính:

```text
người duyệt
tenant / đơn vị kinh doanh / merchant account
đơn và capture nguồn
số tiền + tiền tệ
loại lý do và mức rủi ro
người đề nghị
đích hoàn
trạng thái hồ sơ và bằng chứng
```

Một nhân viên được duyệt cho đơn vị A không được duyệt đơn vị B chỉ vì đoán được request ID. Người có hạn mức cao ở một tiền tệ không mặc nhiên có cùng hạn mức số học ở mọi tiền tệ.

### 4.2. Một tuyến duyệt minh họa

Các mức sau chỉ minh họa cách biểu diễn chính sách nội bộ:

| Trường hợp | Điều kiện phê duyệt minh họa |
| --- | --- |
| Hoàn thông thường, giá trị nhỏ | Một người duyệt độc lập đúng phạm vi |
| Giá trị vượt ngưỡng của nhóm | Cấp có hạn mức tương ứng hoặc thêm cấp duyệt |
| Đổi đích hoàn, lý do ngoại lệ | Tuyến kiểm soát riêng và bằng chứng bổ sung |
| Dấu hiệu chia nhỏ hoặc hồ sơ rủi ro | Đánh giá theo tổng phạm vi liên quan, có thể yêu cầu nhiều người |

Không lấy bảng minh họa làm quy tắc mặc định cho mọi doanh nghiệp. Chính sách thực tế phải chỉ rõ ngưỡng, cách tính, vai trò và thời điểm kiểm tra.

Nếu cần so ngưỡng giữa nhiều tiền tệ, phải có quy tắc quy đổi, nguồn tỷ giá và thời điểm cố định phù hợp cho quyết định. Không cộng trực tiếp các con số ở các tiền tệ khác nhau hoặc để client chọn tỷ giá nhằm đổi tuyến duyệt.

### 4.3. Ngăn chia nhỏ để né ngưỡng

Một ngưỡng chỉ áp dụng cho từng request có thể bị vượt qua bằng nhiều request nhỏ. Cần định nghĩa nhóm cộng dồn, chẳng hạn theo case, capture, order hoặc chủ thể và khoảng thời gian theo chính sách.

Nhóm phải tính đúng những khoản có liên quan, kể cả các khoản đang được duyệt hoặc đã giữ chỗ nếu chính sách yêu cầu. Không chỉ nhìn số đã hoàn cuối cùng trong khi các đề nghị khác đang chờ.

Việc kiểm tra tổng và chốt tuyến duyệt phải được phân xử khi nhiều request đồng thời. Nếu hai request cùng đọc một tổng cũ, cả hai có thể lọt vào tuyến thấp dù tổng sau đó vượt ngưỡng.

Dấu vết đề nghị bị rút hoặc từ chối vẫn có thể cần cho đánh giá lạm dụng. Không để thao tác rút request tự xóa lịch sử đã dùng để phát hiện chia nhỏ.

## 5. State machine của phê duyệt và quyền thực thi

### 5.1. Vòng đời request

Một mô hình minh họa:

```text
DRAFT -> SUBMITTED -> IN_REVIEW -> APPROVED
                         |
                         +-----> REJECTED
                         |
                         +-----> NEEDS_CHANGES -> revision mới

SUBMITTED / IN_REVIEW -> WITHDRAWN hoặc EXPIRED
```

Quy tắc chuyển trạng thái cần được kiểm tra ở server:

| Chuyển trạng thái | Điều kiện chính |
| --- | --- |
| `DRAFT -> SUBMITTED` | Nội dung đầy đủ, đối tượng đúng quyền, đủ điều kiện để đưa vào duyệt |
| `SUBMITTED -> IN_REVIEW` | Snapshot đã cố định và tuyến duyệt được xác định |
| `IN_REVIEW -> APPROVED` | Đủ phiếu hợp lệ, còn đủ ngân sách và đủ điều kiện cấp quyền thực thi |
| `IN_REVIEW -> NEEDS_CHANGES` | Có yêu cầu sửa; nội dung mới phải theo revision mới |
| `IN_REVIEW -> REJECTED` | Có quyết định từ chối đúng quyền và lý do |
| `WITHDRAWN / EXPIRED` | Đóng đề nghị theo chính sách; không xóa lịch sử |

Một phiếu duyệt đã được ghi không nhất thiết làm request thành approved ngay. Có thể còn thiếu cấp duyệt hoặc điều kiện cuối. Response nên phân biệt “đã ghi phiếu của bạn” với “đã hoàn tất phê duyệt”.

### 5.2. Permit có vòng đời riêng

Sau khi chốt approval, hệ thống có thể cấp permit:

```text
ACTIVE -> CONSUMED
   |
   +----> REVOKED
   |
   +----> EXPIRED
```

- `ACTIVE`: còn được sử dụng để tạo đúng nghĩa vụ hoàn đã duyệt.
- `CONSUMED`: đã gắn với nghĩa vụ/operation thực thi, không được tạo khoản khác.
- `REVOKED`: quyền chưa sử dụng đã bị thu hồi theo quyết định hợp lệ.
- `EXPIRED`: quyền chưa sử dụng đã hết thời hạn.

Trong mô hình của bài, `expires_at` là hạn để consume permit và tạo operation được cấp quyền. Nó không tự biến operation đã được tạo hoặc gửi ra ngoài thành thất bại.

Nếu chính sách cần một hạn gửi thực tế tới provider, phải mô hình hóa thêm deadline và cổng kiểm tra tương ứng. Không suy ra rằng một thời hạn tạo operation cũng tự bảo đảm thời điểm request mạng được gửi.

### 5.3. Trạng thái thực thi không được trộn với quyết định phê duyệt

Một operation có thể theo luồng:

```text
CREATED -> PROCESSING -> PENDING -> SUCCEEDED
                 |
                 +-> UNKNOWN -> PENDING / SUCCEEDED / FAILED_FINAL
```

Approval vẫn có thể được ghi nhận là đã được cấp, còn permit đã consumed và operation đang unknown. Đó là ba thông tin khác nhau.

Với mô hình bảo thủ, một operation thất bại cuối không tự làm permit đã consumed trở lại active. Nếu cần tái cấp hoặc đổi phương án thực thi, phải có quyết định được chính sách cho phép, kiểm tra lại ngân sách và chứng minh không còn hiệu ứng chưa rõ từ lần trước.

Retry kỹ thuật cho cùng tác vụ chưa biết kết quả dùng cùng định danh nghiệp vụ và cơ chế chống trùng phù hợp. Nó không phải một request hoàn mới được miễn duyệt.

## 6. Chốt phê duyệt trong transaction

### 6.1. Chọn thời điểm giữ ngân sách

Bài học chọn mô hình **giữ ngân sách khi phê duyệt cuối được chốt**, cùng lúc cấp permit active:

```text
Draft / đang xem xét:
    chưa chiếm ngân sách hoàn trong mô hình minh họa

Chốt phê duyệt:
    kiểm tra lại + claim tiền nguồn + claim quyền hưởng theo case
    + cấp permit + lưu audit trong cùng transaction
```

Cách này tránh để bản nháp tự giữ tiền vô thời hạn. Đổi lại, một request đã được người duyệt xem xét vẫn có thể không được chốt vì ngân sách đã thay đổi. Giao diện cần báo đúng lý do, không tự giảm số tiền để làm request vượt qua bước cuối.

Hệ thống có thể chọn giữ sớm hơn nếu nghiệp vụ cần, nhưng phải quy định thời hạn, giới hạn và cách giải phóng. Mọi ngân sách đang giữ đều phải xuất hiện trong kiểm tra cạnh tranh.

### 6.2. Luồng ghi phiếu và cấp permit

Đoạn dưới là **mã giả**, tập trung vào ranh giới quyết định:

```text
approveRefund(context, command, idempotencyKey):
    reviewer = authenticateAndResolveBusinessIdentity(context)
    authorizeReadAndReview(reviewer, command.requestId)
    fingerprint = approvalCommandFingerprint(command, reviewer)

    response = transaction:
        action = claimIdempotency(
            reviewer.scope,
            idempotencyKey,
            fingerprint
        )

        if action.alreadyExists:
            require action.fingerprint == fingerprint
            require reviewer may read action.result
            return action.savedResult

        lock relevant policy group, request, case budgets
             and capture budgets in a stable shared order

        request = loadCurrentRequest()
        require request.revision == command.expectedRevision
        require request.snapshotFingerprint == command.expectedFingerprint
        require request.state == IN_REVIEW

        require reviewer is authorized for this scope and amount
        require reviewer.businessIdentity != request.requesterBusinessIdentity
        require relevant evidence is still eligible
        require no incompatible final decision exists

        appendImmutableApprovalDecision(
            requestRevision = request.revision,
            reviewer = reviewer,
            decision = APPROVE
        )

        route = evaluateCurrentApprovalRoute(request, relatedRequests)
        votes = loadEffectiveDecisionsForThisRevision()

        if not route.isSatisfiedBy(votes):
            response = reviewStillPending(request, route)
        else:
            require current finalization conditions hold
            require enough refundable money on each source capture
            require enough unclaimed entitlement on the refund case

            claimSourceAndCaseBudgets(request.allocations)
            permit = createActivePermit(
                binding = request.snapshotBinding,
                amount = request.amount,
                allocations = request.allocations,
                expiresAt = policyDefinedDeadline
            )

            request.state = APPROVED
            appendFinalApprovalAudit(request, permit, votes, route)
            appendOutbox(REFUND_APPROVAL_READY, permit.id)
            response = approvalCompleted(request, permit)

        saveIdempotentResult(action, response)

    return response after successful commit
```

Các điều kiện và số liệu được dùng để chốt phải nằm trong cùng ranh giới cạnh tranh. Hai transaction cùng thấy “còn đủ tiền” trước khi khóa không được cùng claim vượt giới hạn.

Nếu request đã chốt, một action trùng phải replay hoặc trả trạng thái hiện tại phù hợp, không cấp permit lần nữa. Unique constraint hỗ trợ quyết định này nhưng không thay logic số lượng và quyền hạn.

### 6.3. Chốt tuyến duyệt tại trạng thái thật

Giả sử một request lúc nộp chỉ cần một người duyệt. Trước khi chốt, request khác cùng nhóm khiến tổng cộng dồn đi vào tuyến cần hai người.

Bước chốt phải đánh giá lại tuyến theo chính sách và tổng có thẩm quyền. Phiếu đã ghi có thể vẫn là một phiếu hợp lệ, nhưng chưa đủ để cấp permit. Không giữ kết luận “chỉ cần một người” từ màn hình cũ rồi bỏ qua tổng mới.

Với nhiều cấp, cần kiểm tra đúng vai trò của từng phiếu, không chỉ `count(approvals) >= 2`. Hai người cùng cấp thấp không thay thế một cấp có thẩm quyền cao nếu chính sách yêu cầu cấp đó.

### 6.4. Bằng chứng và quyền có thể đổi trong lúc chờ

Đánh giá quyền tại thời điểm ghi phiếu và tại các cổng mà chính sách quy định. Nếu chính sách yêu cầu quyền hoặc approval còn hiệu lực khi chốt, các phiếu đã bị thu hồi hoặc không còn đủ điều kiện không được tiếp tục tính.

Snapshot lưu policy version để giải thích quyết định, nhưng không nên trở thành cách vượt qua lệnh chặn hoặc thu hồi có hiệu lực ngay. Cần quy định rõ thay đổi nào làm request phải đánh giá lại, thay đổi nào chỉ áp dụng cho đề nghị mới.

Không mở rộng mặc nhiên một quyền đã hết hạn chỉ vì request từng được xem là hợp lệ.

## 7. Sử dụng permit và thực hiện hoàn tiền

### 7.1. Consume đúng permit, không nhận nội dung tiền mới

Executor nên nhận permit ID hoặc nghĩa vụ đã được cấp quyền, rồi đọc nội dung bất biến từ server:

```text
consumeRefundPermit(permitId):
    transaction:
        lock permit, request and linked budget claims
        if permit already consumed:
            return existing refund obligation

        require permit.state == ACTIVE
        require now is before permit.expiresAt
        require permit binding matches approved request revision
        require required execution conditions still hold
        require no effective revocation blocks execution

        obligation = createImmutableRefundObligationFromPermit()
        transfer existing claims to this obligation without releasing them
        permit.state = CONSUMED

        appendAudit(PERMIT_CONSUMED, permit, obligation)
        appendOutbox(EXECUTE_REFUND, obligation.id)

    return obligation
```

Việc “transfer claim” là thay đổi chủ thể giữ chỗ trong cùng transaction, không phải giải phóng ngân sách rồi claim lại ở bước khác. Nếu có khoảng trống, một request khác có thể dùng mất phần tiền đã duyệt.

Operation phải dùng đúng capture, số tiền, tiền tệ và đích hoàn đã duyệt. Không nhận `refundAmount` hoặc `destination` mới từ message bên ngoài rồi coi permit là giấy phép chung.

### 7.2. Đích hoàn cần chính sách riêng

Thông thường, hệ thống nên áp dụng đích hoàn phù hợp với nguồn thanh toán và khả năng của phương thức. Không tự chuyển tiền sang một tài khoản bất kỳ vì người gọi gửi được số tài khoản.

Nếu nghiệp vụ hỗ trợ ngoại lệ, cần xác minh người nhận, căn cứ, phạm vi và tuyến duyệt riêng. Một approval cho hoàn về nguồn cũ không được dùng cho phương án chuyển sang ví hoặc tài khoản khác.

Tham chiếu đích cần đủ ổn định để không bị thay nội dung sau khi duyệt. Quyền sửa cấu hình người nhận và quyền duyệt ngoại lệ cũng cần được đánh giá trong mô hình tách trách nhiệm.

### 7.3. Gọi provider ngoài transaction database

Worker gửi đúng operation với provider idempotency key ổn định theo thiết kế tích hợp. Không giữ transaction khóa ngân sách trong lúc chờ mạng.

Các kết quả phải được phân loại:

| Kết quả | Tác động |
| --- | --- |
| Thành công có bằng chứng đúng operation | Chuyển tiền đang giữ chỗ thành số đã hoàn, đúng một lần |
| Đang xử lý | Giữ claim, tiếp tục theo dõi |
| Timeout hoặc chưa rõ | Giữ trạng thái chưa biết và claim; tra cứu/retry cùng định danh |
| Thất bại cuối được xác minh | Đóng operation theo chính sách, giải phóng claim phù hợp đúng một lần |
| Kết quả không khớp hoặc mâu thuẫn | Giữ bằng chứng và đối soát, không đoán kết quả |

API response và webhook có thể cùng báo thành công. Cần chống trùng theo hiệu ứng nghiệp vụ, không chỉ theo event ID của từng delivery.

Chữ ký webhook hợp lệ vẫn cần được đối chiếu với provider, merchant account, môi trường, capture nguồn, số tiền và tiền tệ. Approval không làm một webhook sai đối tượng trở thành hợp lệ.

### 7.4. Retry không được tái tạo nghĩa vụ

Nếu worker chết sau khi provider có thể đã nhận request, lần chạy tiếp theo phải tìm lại cùng operation. Không tạo một refund request mới, xin một approval mới rồi gửi thêm tiền khi lần cũ chưa rõ kết quả.

Một lần thử kỹ thuật mới vẫn chịu giới hạn của cùng nghĩa vụ. Nếu cần đổi provider hoặc phương án sau thất bại cuối, chính sách phải quy định cách bảo đảm không còn khả năng hoàn trùng, nội dung còn được phép và có cần duyệt lại hay không.

Không chuyển `UNKNOWN` thành thất bại chỉ để giải phóng ngân sách và mở đường cho một khoản khác.

## 8. Thu hồi, hết hạn và hủy yêu cầu

### 8.1. Thu hồi cạnh tranh với consume phải có một điểm phân xử

Cả hai thao tác cần khóa hoặc cập nhật có điều kiện trên cùng permit:

```text
Nếu thu hồi thắng:
    ACTIVE -> REVOKED
    không tạo operation mới
    giải phóng claim theo điều kiện an toàn

Nếu consume thắng:
    ACTIVE -> CONSUMED
    đã có nghĩa vụ thực thi
    thu hồi không được giả định rằng tiền chưa thể di chuyển
```

Khi operation đã được tạo, việc dừng cần theo state machine thực thi. Nếu request đã gửi ra ngoài hoặc kết quả chưa rõ, phải đối soát; không chỉ đổi permit thành revoked rồi giải phóng tiền.

Tương tự, một job hết hạn chỉ được giải phóng claim của permit chưa consumed khi đã phân xử nguyên tử với executor. Không chọn theo timestamp rồi cập nhật nhiều bảng rời rạc.

### 8.2. Hết hạn không xóa khoản hoàn đã xảy ra

Approval hết thời hạn không làm một refund thành công trở lại chưa hoàn. Nếu provider phản hồi muộn cho operation đã được cấp quyền đúng lúc, cần xử lý theo sự thật và điều kiện thực thi đã cam kết.

Sai sót phê duyệt hoặc kết quả ngoài dự kiến phải đi qua quy trình điều tra và sửa sai. Không sửa audit, đổi số tiền của operation cũ hoặc gán trạng thái khác để che việc tiền đã di chuyển.

### 8.3. Tránh giữ ngân sách vô thời hạn

Permit active nhưng không được thực thi có thể làm các khoản hoàn hợp lệ khác bị chặn. Cần thời hạn, giới hạn số permit đang mở, đối soát và người chịu trách nhiệm xử lý.

Giải phóng claim chỉ an toàn khi có bằng chứng chưa phát sinh tác động bên ngoài hoặc kết quả cuối xác nhận không có hoàn. Các nghĩa vụ đang pending/unknown không phải ngân sách rỗi.

## 9. Ví dụ số và các kết quả cần phân biệt

### 9.1. Chốt duyệt không được bỏ qua khoản đang chờ

Giả sử cùng một capture:

```text
Đã thu C = 1.000.000
Đã hoàn thành công R = 200.000
Đang giữ cho một nghĩa vụ khác H = 100.000

Ngân sách chưa claim = 1.000.000 - 200.000 - 100.000 = 700.000
```

Một request mới xin hoàn 500.000, có căn cứ đủ điều kiện và đủ phiếu đúng tuyến:

| Bước | R đã hoàn | H đang giữ | Ngân sách chưa claim |
| --- | ---: | ---: | ---: |
| Trước khi chốt request mới | 200.000 | 100.000 | 700.000 |
| Chốt duyệt và cấp permit 500.000 | 200.000 | 600.000 | 200.000 |
| Consume permit, chưa rõ kết quả provider | 200.000 | 600.000 | 200.000 |
| Hoàn 500.000 thành công | 700.000 | 100.000 | 200.000 |

Nếu một request khác xin 300.000 trong lúc permit 500.000 còn active hoặc operation còn unknown, không được chốt thêm 300.000 trên nguồn tiền này vì chỉ còn 200.000 chưa claim.

Nếu permit 500.000 hết hạn trước khi được consume và đã xác minh không có operation thực thi, việc giải phóng đưa `H` về 100.000. Nhưng nếu operation đang unknown, thời hạn permit không cho phép giải phóng 500.000.

Giả sử case đầu chỉ xác nhận quyền hưởng hoàn 500.000. Sau khi đã claim hoặc hoàn đủ phần đó, request khác cùng case không được dùng 200.000 còn lại của capture để hoàn thêm nếu chưa có căn cứ mới.

### 9.2. Sửa nội dung sau khi duyệt

Request R-10 revision 3 được duyệt hoàn 500.000 về đích đã xác minh. Người đề nghị sửa thành 600.000 hoặc đổi đích nhận rồi gọi executor với cùng permit.

Kết quả cần đạt:

- Revision mới không khớp binding của permit cũ.
- Executor không sử dụng nội dung mới để gửi tiền.
- Muốn thực hiện nội dung mới phải đi qua luồng revision và phê duyệt phù hợp.
- Claim cũ được xử lý theo trạng thái permit/operation, không cộng hoặc giải phóng tùy tiện.

Ngay cả khi capture còn đủ tiền, thiếu phê duyệt cho nội dung mới vẫn là lý do chặn. Ngân sách còn dư không sửa được lỗi quyền hạn.

### 9.3. Hai request nhỏ có thể thuộc một quyết định lớn

Giả sử chính sách nội bộ yêu cầu hai người duyệt khi tổng giá trị trong cùng nhóm đạt từ 500.000. Người đề nghị tách thành hai request 350.000 cùng case.

Nếu xét riêng từng request, cả hai có thể đi qua tuyến một người. Nếu đánh giá theo nhóm đúng chính sách, tổng liên quan là 700.000 và cần tuyến tương ứng.

Hai request chạy đồng thời vẫn phải bị phân xử trên nhóm cộng dồn. Không thể chỉ tính tổng ở giao diện hoặc một job sau khi tiền đã được gửi.

Các con số này minh họa một chính sách, không phải ngưỡng chung bắt buộc. Giá trị bảo vệ nằm ở việc chính sách được định nghĩa và thực thi nhất quán.

## 10. Các đường vòng cần được kiểm soát

### 10.1. Portal quản trị không phải ngoại lệ mặc định

Nếu API khách hàng kiểm tra đầy đủ nhưng portal hỗ trợ cho sửa `approved` hoặc gọi refund trực tiếp, đường quản trị trở thành nơi bỏ qua quy trình.

Mọi đường tạo hiệu ứng hoàn phải đi qua cổng cấp quyền phù hợp: API, batch, consumer, công cụ hỗ trợ và tích hợp nội bộ. Một script vận hành có credential mạnh cũng không nên âm thầm tạo khoản hoàn không gắn căn cứ và người chịu trách nhiệm.

Nếu có quy trình khẩn cấp, cần quyền riêng, phạm vi, hạn mức, lý do và audit theo chính sách. Nó không được tồn tại như một tham số do người đề nghị tự bật.

### 10.2. Không dùng tốc độ xử lý để bỏ tách trách nhiệm

Request chờ lâu không làm người đề nghị tự có quyền duyệt. Cơ chế chuyển người xử lý hoặc ủy quyền phải được cấp đúng phạm vi và thời hạn.

Nếu có ủy quyền, xác định danh tính nghiệp vụ nào được tính để bảo vệ tính độc lập. Không tính một người vừa dưới danh nghĩa cá nhân vừa dưới danh nghĩa ủy quyền thành hai người duyệt cho cùng quyết định.

Quyền thay tuyến duyệt, chỉnh hạn mức và sửa cấu hình cũng có thể ảnh hưởng trực tiếp đến khả năng hoàn tiền; các thay đổi đó cần được bảo vệ và truy nguyên phù hợp.

### 10.3. Nếu có phê duyệt tự động, phải mô hình hóa đúng

Một số hệ thống cho phép rule tự động duyệt các trường hợp đủ điều kiện. Đây phải là tuyến chính sách rõ ràng, với rule version, điều kiện, hạn mức và chủ thể hệ thống được ghi nhận.

Không tạo một phiếu giả mang danh người duyệt để làm đủ số lượng. Cũng không cho request tự chọn `approvalMode=AUTO` để tránh tuyến thủ công.

Những trường hợp bắt buộc có người duyệt độc lập theo chính sách không được thỏa bằng việc gọi service account khác tên. Cần phân biệt quyết định tự động được cho phép với việc giả lập tách trách nhiệm.

### 10.4. Giao diện duyệt phải thể hiện đúng quyết định

Người duyệt cần nhìn được số tiền, tiền tệ, nguồn thu, phần hàng/case, đích hoàn, lý do, bằng chứng và các khoản liên quan ảnh hưởng tới ngưỡng.

Nút duyệt phải gửi revision đang xem. Nếu request đã thay đổi, yêu cầu tải lại nội dung để quyết định trên bản mới, thay vì tự duyệt bản hiện tại với dữ liệu mà người duyệt chưa xem.

Ẩn nút chỉ hỗ trợ trải nghiệm. Các endpoint vẫn phải kiểm tra quyền, revision và điều kiện vì người gọi có thể gửi request ngoài giao diện.

## 11. Audit và đối soát phê duyệt

### 11.1. Chuỗi căn cứ cần nối được từ case đến khoản hoàn

Audit cần trả lời:

| Câu hỏi | Dữ liệu cần liên kết |
| --- | --- |
| Vì sao được hoàn? | Case, chứng từ, bằng chứng và phiên bản liên quan |
| Đã đề nghị nội dung gì? | Request, revision, snapshot và fingerprint |
| Ai đã quyết định? | Danh tính nghiệp vụ, vai trò/phạm vi, hình thức duyệt |
| Đủ tuyến theo quy tắc nào? | Policy version, tuyến, phiếu được tính và tổng liên quan tại quyết định |
| Được cấp quyền bao nhiêu? | Permit, phân bổ nguồn tiền, quyền hưởng và hạn dùng |
| Quyền đã được sử dụng chưa? | Consumption, obligation, operation và tác vụ thực thi |
| Tiền thực tế ra sao? | Provider reference, kết quả, thời điểm và hiệu ứng đã áp dụng |
| Có sửa, rút hoặc thu hồi không? | Hành động kế tiếp, người thao tác, lý do và liên kết quyết định trước |

Lưu cả người thao tác trực tiếp và người khởi tạo nghiệp vụ nếu service làm thay. Không thay requester bằng service ID rồi mất dấu chủ thể ban đầu.

Phiếu bị từ chối, lỗi quyền hoặc retry không phải phê duyệt thành công. Audit cần phân loại để không nhầm số lần gọi API với số quyết định có hiệu lực.

### 11.2. Bảo vệ lịch sử và dữ liệu nhạy cảm

Không cho tài khoản ứng dụng thông thường sửa/xóa quyết định đã ghi để che sai sót. Nếu rút phiếu, thay revision hoặc sửa sai, lưu hành động mới có quan hệ rõ với bản cũ.

Append-only ở ứng dụng vẫn cần quyền lưu trữ, backup và quy trình vận hành phù hợp; nó không tự bảo vệ trước mọi quyền quản trị hạ tầng. Mức bảo vệ phải phù hợp yêu cầu điều tra của hệ thống.

Không lưu bí mật, thông tin thanh toán nhạy cảm hoặc toàn bộ tài liệu cá nhân không cần thiết vào từng bản ghi. API audit, export và truy cập bằng chứng phải kiểm tra tenant và phạm vi quyền.

Reason code nên được chuẩn hóa, ghi chú có giới hạn và được hiển thị như dữ liệu. Không để nội dung ghi chú thay thế một căn cứ cần được xác minh.

### 11.3. Đối soát quyền đã cấp với tiền đã di chuyển

Các kiểm tra có giá trị gồm:

- Có permit active nhưng không còn đủ hoặc không còn đúng claim liên kết.
- Có operation refund nhưng không có permit/căn cứ phù hợp với tuyến chính sách.
- Một permit liên kết nhiều nghĩa vụ ngoài quy tắc cho phép.
- Snapshot của operation không khớp nội dung được duyệt.
- Request đã sửa nhưng phiếu của revision cũ vẫn đang được tính.
- Số đã hoàn hoặc đang giữ chỗ vượt capture nguồn hoặc quyền hưởng theo case.
- Permit revoked/expired nhưng executor vẫn tạo operation sau điểm chặn có hiệu lực.
- Operation đã thành công nhưng claim chưa được tiêu thụ, hoặc operation unknown mà claim đã bị giải phóng.
- Request chia nhỏ, đổi đích hoặc dùng quyền ngoại lệ với tần suất bất thường.

Đối soát phải xét cùng mốc và nguồn dữ liệu thích hợp. Một projection chậm có thể chưa phản ánh permit đã consumed; cần xác minh trước khi tự động giải phóng ngân sách.

Khi phát hiện sai lệch, giữ bằng chứng và chặn đúng phạm vi cần thiết. Không tự gán request thành approved hoặc operation thành failed để làm báo cáo khớp.

## 12. Kiểm thử các tình huống lạm dụng logic

Mỗi ca cần xác minh response, revision, phiếu có hiệu lực, permit, claim, operation, hiệu ứng tiền và audit sau xử lý.

| Tình huống | Kết quả cần đạt |
| --- | --- |
| Người đề nghị tự duyệt | Không được tính phiếu khi chính sách yêu cầu độc lập |
| Dùng hai tài khoản cùng danh tính nghiệp vụ để đủ hai người | Không tính thành hai chủ thể độc lập |
| Reviewer đúng vai trò nhưng sai tenant/đơn vị/hạn mức | Từ chối trên đúng đối tượng và phạm vi |
| Client gửi `approved=true` hoặc `force=true` | Không thay thế quyết định server và tuyến duyệt |
| Sửa số tiền, tiền tệ, nguồn hoặc đích sau khi duyệt | Binding không khớp; không dùng approval cũ cho nội dung mới |
| Reviewer bấm duyệt từ màn hình revision cũ | Conflict hoặc yêu cầu đọc lại; không tự duyệt bản chưa xem |
| Hai người cùng chốt phiếu cuối | Chỉ một permit và một bộ claim cuối được tạo |
| Cùng một reviewer gửi nhiều request đồng thời | Một phiếu hiệu lực theo quy tắc, không tăng giả quorum |
| Hai request cùng tranh ngân sách còn lại | Tổng claim không vượt nguồn tiền và quyền hưởng |
| Chia nhỏ request để né ngưỡng | Tuyến được tính theo nhóm và thời điểm chính sách quy định |
| Cùng key, cùng nội dung, retry sau mất response | Replay quyết định; không tạo thêm phiếu/permit/claim |
| Cùng key nhưng đổi request, revision hoặc quyết định | Xung đột nội dung, không áp dụng ý định mới |
| Consume cùng permit nhiều lần hoặc qua nhiều worker | Cùng nghĩa vụ, không tạo nhiều khoản hoàn |
| Thu hồi/hết hạn đồng thời với consume | Có một kết quả phân xử; không vừa giải phóng claim vừa cho thực thi |
| Operation unknown rồi job hết hạn chạy | Không giải phóng claim chỉ dựa vào deadline của permit |
| Reviewer bị thu hồi quyền trong lúc chờ | Áp dụng kiểm tra hiệu lực theo chính sách tại cổng liên quan |
| Lỗi ghi outbox khi chốt hoặc consume | Rollback các thay đổi cục bộ liên quan, không để trạng thái lệch |
| API response và webhook cùng báo refund thành công | Một hiệu ứng tiền, claim được tiêu thụ đúng một lần |
| Event đúng chữ ký nhưng sai merchant/capture/tiền tệ | Không áp dụng vào khoản hoàn đang xét; giữ bằng chứng để đối soát |
| Nhân viên hỗ trợ gọi đường hoàn trực tiếp không có căn cứ | Không bỏ qua cổng quyền và phê duyệt |
| Đổi sang đích nhận tiền khác qua message thực thi | Không chấp nhận nội dung ngoài snapshot được cấp quyền |

Các ca race cần điều phối để thao tác chạm cùng thời điểm kiểm tra và cập nhật; chạy tuần tự không chứng minh được tính an toàn đồng thời.

Kiểm tra cả đường hợp lệ: hai cấp duyệt đúng vai trò, nhiều request từng phần không trùng căn cứ, rút request trước thực thi, permit hết hạn chưa dùng và retry cùng operation. Cơ chế bảo vệ quá rộng không nên khóa mọi khoản hoàn khác của cùng order nếu chúng có căn cứ và ngân sách độc lập hợp lệ.

## 13. Bài tập áp dụng

### Bài tập 1: Phê duyệt cũ có đủ cho nội dung mới không?

Request R-1 revision 2 đề nghị hoàn 400.000 về nguồn thanh toán gốc và đã được duyệt. Sau đó một API hỗ trợ sửa thành 900.000, đổi đích nhận rồi gọi refund với cùng approval ID. Capture còn dư đủ 900.000.

Hãy chỉ ra những điều kiện phải chặn dù ngân sách còn đủ.

**Gợi ý giải:** Số tiền và đích không còn khớp snapshot được duyệt. Nội dung mới cần revision và tuyến duyệt phù hợp; quyền sửa của nhân viên cũng cần được kiểm tra riêng. Executor không được nhận nội dung mới cùng một approval ID rồi thực hiện. Ngân sách còn đủ chỉ thỏa một giới hạn tài chính, không tạo ra phê duyệt cho thay đổi.

### Bài tập 2: Đồng thời và ngân sách đang chờ

Một capture có `C = 900.000`, `R = 300.000` và `H = 200.000`. Hai request khác nhau, mỗi request xin hoàn 250.000 và đều có căn cứ hợp lệ, cùng đi tới bước chốt.

Hãy tính ngân sách chưa claim và kết quả phân xử.

**Gợi ý giải:** Ngân sách chưa claim là `900.000 - 300.000 - 200.000 = 400.000`. Nếu request thứ nhất claim 250.000, `H` tăng lên 450.000 và chỉ còn 150.000 chưa claim. Request thứ hai không được chốt nguyên vẹn 250.000. Không được bỏ qua 200.000 đang chờ hoặc tự giảm nội dung của request thứ hai mà vẫn dùng approval cho số tiền cũ.

Nếu nghĩa vụ thứ nhất đã được gửi nhưng unknown, hết thời hạn của permit không làm 250.000 đó trở lại ngân sách rỗi. Cần biết kết quả thực thi trước khi giải phóng theo quy trình.

Phê duyệt hoàn tiền có giá trị khi người duyệt biết chính xác mình đang cho phép điều gì, hệ thống giữ nguyên phạm vi quyết định đó và mọi hiệu ứng được gắn với căn cứ đã duyệt. Các thao tác sửa, retry, thu hồi và đối soát phải giữ được chuỗi ràng buộc ấy trong suốt vòng đời khoản hoàn.
