# Trạng thái chargeback (Chargeback state)

Trạng thái chargeback mô tả tiến trình xử lý một tranh chấp thanh toán và các quyết định liên quan. Nếu hệ thống tin trạng thái do client gửi, bỏ qua quyền theo đối tượng hoặc xử lý sai sự kiện đến muộn, một vụ việc có thể bị đóng sai, phản hồi không được gửi hoặc phát sinh hoàn tiền trùng với một khoản đang tranh chấp.

Trong chương **Chargeback Rules**, bài học này xem state machine là một cơ chế bảo vệ quy tắc nghiệp vụ. Trọng tâm là business invariants, phân quyền trên đúng giao dịch, transaction, idempotency và kiểm thử tình huống lạm dụng logic.

Các trạng thái dưới đây là **mô hình nội bộ minh họa**. Tên gọi, bước xử lý, thời hạn và tác động tiền phải được ánh xạ với hợp đồng của nguồn thanh toán đang tích hợp; không có một sơ đồ duy nhất áp dụng nguyên trạng cho mọi provider hoặc phương thức.

Sau bài học, bạn có thể:

- Phân biệt trạng thái vụ việc, hành động của merchant và các biến động tiền.
- Xác định nguồn bằng chứng được phép thay đổi trạng thái.
- Chặn chuyển trạng thái trái quyền, sai đối tượng hoặc dựa trên dữ liệu cũ.
- Xử lý sự kiện lặp, sai thứ tự, timeout và khả năng mở lại vụ việc.
- Thiết kế audit và kiểm thử cho các cuộc đua giữa chargeback, refund và fulfillment.

## 1. Xác định đúng đối tượng và nguồn sự thật

### 1.1. Khiếu nại nội bộ không tự trở thành chargeback

Một ticket hỗ trợ, yêu cầu refund, thông báo hỏi thêm thông tin và một vụ tranh chấp do nguồn thanh toán ghi nhận là các đối tượng khác nhau. Có thể liên kết chúng, nhưng không tự coi mọi khiếu nại là một khoản tiền đã bị ghi nợ.

Ví dụ:

| Đối tượng | Thông tin nó có thể cho biết | Điều không được tự suy ra |
| --- | --- | --- |
| Ticket hỗ trợ | Khách cho rằng chưa nhận hàng | Provider đã mở chargeback |
| Inquiry/yêu cầu thông tin theo tích hợp | Cần cung cấp hoặc xác minh dữ liệu | Merchant chắc chắn đã bị trừ tiền |
| Dispute case | Nguồn thanh toán đang xử lý một vụ tranh chấp | Đã có kết quả cuối hoặc đã có debit |
| Balance transaction | Một biến động tiền được nguồn ghi nhận | Toàn bộ vụ tranh chấp đã kết thúc |
| Refund operation | Merchant đang hoặc đã thực hiện hoàn | Chargeback chắc chắn đã bị hủy |

Mỗi dữ kiện phải giữ đúng ý nghĩa của nguồn đã cung cấp. Không tạo debit chỉ vì một case vừa được mở.

### 1.2. Case phải gắn với đúng phạm vi thanh toán

Một ánh xạ đáng tin cậy cần xét ít nhất:

```text
tenant_id
provider
environment
merchant_account
provider_dispute_id
source_payment_or_capture_reference
```

Server quản lý quan hệ giữa các tham chiếu này với đơn và khoản thu nội bộ. Không dùng riêng `metadata.orderId` từ payload để xác nhận vụ việc thuộc một đơn.

Không mặc định “mỗi order chỉ có một chargeback”. Một order có thể có nhiều khoản thu, các phạm vi tranh chấp khác nhau hoặc các chu kỳ xử lý được nguồn hỗ trợ. Ngược lại, một case không được tùy ý chuyển sang capture khác chỉ để làm số liệu khớp.

Nếu mô hình nguồn cần phân bổ một case vào nhiều phần tiền, phải lưu phân bổ rõ ràng và kiểm tra quan hệ. Không đoán theo số tiền gần giống hoặc theo email người mua.

### 1.3. Phân biệt quyền quản lý nội bộ và quyền quyết định bên ngoài

Nhân viên có thể phân công người xử lý, chuẩn bị bằng chứng hoặc đề nghị chấp nhận tranh chấp. Những hành động này không trao quyền tự tuyên bố provider đã xử thắng hay đã hoàn trả tiền.

Một API nội bộ như sau là nguy hiểm nếu cập nhật trực tiếp kết quả có thẩm quyền:

```http
PATCH /disputes/D-100
Content-Type: application/json

{ "status": "WON" }
```

Nên cung cấp các command có ý nghĩa nghiệp vụ: giao người xử lý, khóa snapshot bằng chứng, yêu cầu gửi phản hồi hoặc yêu cầu chấp nhận theo chính sách. Kết quả bên ngoài phải được cập nhật từ bằng chứng đã xác minh.

## 2. Tách các chiều trạng thái

### 2.1. Vòng đời case

Một state machine chuẩn hóa tối giản có thể gồm:

```text
OPEN -> ACTION_REQUIRED -> UNDER_REVIEW -> RESOLVED

Một số luồng có thể:
OPEN -> UNDER_REVIEW
OPEN / ACTION_REQUIRED -> RESOLVED
```

| Trạng thái nội bộ | Ý nghĩa minh họa |
| --- | --- |
| `OPEN` | Đã xác nhận có vụ việc, đang xác định hoặc theo dõi bước xử lý |
| `ACTION_REQUIRED` | Theo nguồn có thẩm quyền, merchant có hành động cần thực hiện |
| `UNDER_REVIEW` | Vụ việc đang được xem xét theo tiến trình của nguồn |
| `RESOLVED` | Đã có thông tin giải quyết thuộc chu kỳ đang theo dõi |

Không tự tạo mọi cạnh chuyển trạng thái trong sơ đồ. Chỉ bật những chuyển phù hợp với các sự kiện và hành động thực tế của tích hợp.

Một case resolved cần lưu kết quả riêng, chẳng hạn `FAVORABLE`, `UNFAVORABLE` hoặc `CLOSED_OTHER`, cùng mã kết quả nguồn. Không suy rằng mọi trạng thái “closed” đều có cùng ý nghĩa.

### 2.2. Hành động phản hồi của merchant

Chuẩn bị hoặc gửi bằng chứng nên có trạng thái riêng:

```text
NOT_STARTED
PREPARING
SUBMISSION_PENDING
SUBMISSION_UNKNOWN
SUBMITTED_CONFIRMED
SUBMISSION_FAILED_FINAL
```

Các trạng thái này không đồng nghĩa với kết quả case:

- `PREPARING` không chứng minh provider đã nhận gì.
- `SUBMISSION_PENDING` có thể chỉ cho biết đã có tác vụ bền vững đang chờ gửi.
- `SUBMISSION_UNKNOWN` nghĩa là chưa biết lần gửi đã được áp dụng hay chưa.
- `SUBMITTED_CONFIRMED` chỉ được ghi theo bằng chứng tiếp nhận đáp ứng hợp đồng tích hợp.
- Đã gửi phản hồi không đồng nghĩa merchant được xử có lợi.

Nếu có hành động chấp nhận tranh chấp, cũng cần một operation với quyền, trạng thái và kết quả riêng. Bấm “chấp nhận” không tự chứng minh việc đó đã được nguồn áp dụng.

### 2.3. Biến động tiền là dữ kiện riêng

Một case có thể liên quan tới các dòng tiền khác nhau, ví dụ:

```text
DISPUTE_PRINCIPAL_DEBIT
DISPUTE_PRINCIPAL_CREDIT
DISPUTE_FEE_DEBIT
DISPUTE_FEE_CREDIT
```

Đây là các loại minh họa để phân biệt tiền gốc và phí khi nguồn cung cấp. Không giả định case nào cũng có đủ các loại này hoặc xảy ra theo cùng thứ tự.

Nên lưu từng hiệu ứng có định danh nguồn và liên kết tới case. Một cột `fundsStatus` duy nhất khó biểu diễn được việc đã có debit tiền gốc, đã có credit tiền gốc nhưng phí vẫn chưa được điều chỉnh.

Kết quả có lợi không tự tạo credit nếu chưa có bằng chứng của biến động đó. Ngược lại, một biến động tiền có thể đến sau thông báo kết quả case và vẫn cần được ghi nhận.

### 2.4. Trạng thái order và fulfillment không bị thay thế

Chargeback không chứng minh hàng đã được trả lại, đơn bị hủy hoặc kho đã thu hồi kiện. Một kết quả bất lợi cũng không tự cho phép tạo khoản thu mới từ khách.

Các bước như dừng giao, thu hồi hàng, refund hoặc xử lý công nợ phải đi qua quy tắc riêng và có căn cứ liên quan. Không dùng một phép gán trạng thái chargeback để thực hiện ngầm tất cả tác động đó.

## 3. Đặc tả chuyển trạng thái và quyền thực hiện

### 3.1. Bảng quyết định minh họa

| Thay đổi | Nguồn có thể cho phép | Kiểm tra quan trọng |
| --- | --- | --- |
| Tạo case đã xác nhận | Event hoặc truy vấn nguồn thanh toán đã xác minh | Đúng merchant, môi trường và khoản thu |
| Chuyển sang cần hành động | Trạng thái nguồn đã ánh xạ rõ | Loại hành động, chu kỳ và thời hạn liên quan |
| Bắt đầu chuẩn bị bằng chứng | Người/service đúng quyền | Case còn cho phép thao tác, đúng phạm vi |
| Yêu cầu gửi phản hồi | Command nội bộ hợp lệ | Snapshot, quyền, điều kiện và idempotency |
| Xác nhận đã gửi | Biên nhận hoặc trạng thái nguồn có ý nghĩa tiếp nhận | Đúng operation, snapshot và kết quả |
| Cập nhật kết quả giải quyết | Bằng chứng từ nguồn có thẩm quyền | Đúng case, chu kỳ và phiên bản nếu có |
| Ghi debit/credit | Biến động tiền được xác minh | Định danh hiệu ứng, số tiền, tiền tệ và quan hệ |
| Mở lại vụ việc | Thông tin mở lại/chuyển chu kỳ hợp lệ từ nguồn | Không nhầm với event cũ đến muộn |
| Đóng công việc nội bộ | Người/service đúng quyền | Không thay kết quả bên ngoài hoặc xóa nghĩa vụ đang chờ |

Quyền `dispute:write` chung thường chưa đủ. Có thể cần tách `dispute:read`, `dispute:prepare`, `dispute:submit` và quyền chấp nhận hoặc thực hiện ngoại lệ theo chính sách.

Phạm vi phải xét tenant, merchant account, đơn vị xử lý và case. API đọc, export bằng chứng và replay kết quả cũng cần kiểm tra quyền.

### 3.2. Mở lại là một chuyển có điều kiện

Không thể luôn áp dụng quy tắc “resolved là cuối tuyệt đối”, vì mô hình nguồn có thể hỗ trợ mở lại hoặc chu kỳ tiếp theo. Nhưng cũng không được cho mọi event `OPEN` đến sau làm case sống lại.

Một thiết kế có thể lưu:

```text
case_id
cycle_id hoặc cycle_number khi mô hình có căn cứ
provider_revision nếu nguồn cung cấp
local_version
raw_status
normalized_status
outcome
```

Thông tin mở lại cần được xác minh theo nguồn và quy tắc ánh xạ. Nếu chỉ có event cũ nhưng đến trễ, trạng thái case không lùi.

`local_version` giúp phân xử cập nhật trong ứng dụng; nó không tự chứng minh event nào mới hơn ở provider. Không dùng số version nội bộ để thay thế một thứ tự nguồn chưa biết.

### 3.3. Deadline là điều kiện cần quản lý, không phải kết quả case

Lưu thời hạn từ nguồn phù hợp, dạng thời điểm có múi giờ rõ ràng và liên kết với hành động/chu kỳ liên quan. Nếu nguồn cập nhật deadline, phải xử lý theo phiên bản và căn cứ; không tin thời hạn client tự gửi.

Tiêu chí đáp ứng thời hạn phải được ánh xạ theo hợp đồng tích hợp. Việc bấm nút hoặc tạo job trước deadline không tự chứng minh phản hồi đã được tiếp nhận đúng yêu cầu.

Khi đồng hồ local qua deadline, có thể đánh dấu công việc nội bộ quá hạn và mở xử lý khẩn/đối soát. Không tự gán kết quả case bất lợi chỉ vì job chưa kịp chạy hoặc chưa nhận webhook.

## 4. Những bất biến phải giữ

### 4.1. Đúng case, đúng khoản thu, đúng ngữ cảnh

Mọi cập nhật có tác động phải liên kết với đối tượng đã ánh xạ trong cùng phạm vi. Một chữ ký event hợp lệ không sửa được việc chọn sai merchant, môi trường hoặc khoản thu.

Số tiền tranh chấp có thể chỉ là một phần của khoản thu. Không bắt buộc nó bằng toàn bộ capture để rồi loại bỏ case hợp lệ. Phí và biến động theo tiền tệ quyết toán cần được tách khỏi tiền gốc theo giao dịch; không cộng trực tiếp các số ở các tiền tệ khác nhau.

Thay đổi số tiền hoặc phạm vi case phải đến từ nguồn có thẩm quyền và được lưu vết. Không cho client sửa amount để vượt kiểm soát hoặc điều chỉnh số liệu theo mong muốn.

### 4.2. Không tạo sự thật tài chính từ nhãn trạng thái

Các suy luận sau phải bị chặn:

```text
OPEN      => chắc chắn đã debit
SUBMITTED => chắc chắn được xử có lợi
FAVORABLE => chắc chắn đã credit đủ cả phí
RESOLVED  => chắc chắn không còn công việc đối soát
```

Case state, response state và ledger state phải được cập nhật theo bằng chứng tương ứng.

### 4.3. Mỗi hiệu ứng chỉ áp dụng một lần

Event ID giúp chống xử lý lại cùng delivery, nhưng cùng một biến động tiền có thể được báo qua nhiều đường. Cần khóa theo định danh hiệu ứng nguồn, chẳng hạn:

```text
(provider, environment, merchant_account, source_balance_transaction_id)
```

Nếu một giao dịch nguồn có nhiều thành phần cần tách, khóa phải bao gồm thành phần hoặc phân bổ phù hợp.

Không unique chỉ theo `dispute_id` cho mọi dòng tiền: một case có thể có debit, credit và phí khác nhau. Ngược lại, đổi event ID không được làm cùng debit được ghi hai lần.

### 4.4. Event cũ không làm lùi case, nhưng có thể mang dữ kiện tiền chưa ghi

Một lỗi tinh vi là bỏ toàn bộ event vì case đã resolved. Event đến muộn có thể chứa một biến động tiền thật chưa được ghi nhận.

Bộ xử lý cần xét riêng:

```text
Có được thay đổi trạng thái case không?
Có hiệu ứng tiền mới, hợp lệ và chưa áp dụng không?
Có kết quả action cần hoàn tất không?
```

Không áp dụng trạng thái cũ không đồng nghĩa được bỏ mất mọi dữ kiện trong thông điệp. Mỗi chiều có quy tắc và khóa chống trùng riêng.

### 4.5. Không tạo đường hoàn tiền trùng trong lúc tranh chấp

Refund do merchant chủ động và chargeback là các luồng khác nhau nhưng cùng liên quan tới một khoản thu. Nếu từng luồng tự tính trên dữ liệu riêng, khách có thể nhận lợi ích trùng hoặc số liệu bị lệch.

Chính sách có thể chặn refund mới trên phần tiền đang tranh chấp cho tới khi xác định được cách xử lý, hoặc cho phép một quy trình phối hợp được kiểm soát. Nếu vẫn cho refund từng phần, phải định danh phần tiền, claim và điều kiện rõ ràng.

Không dùng một công thức chung “capture trừ mọi debit chargeback” để thay cho quan hệ thực tế: debit có thể tạm thời, có điều chỉnh, có phí và có giao thoa với refund trước đó. Cần phân biệt giới hạn nội bộ, biến động tiền và khả năng thao tác mà provider thực sự cho phép.

## 5. Mô hình dữ liệu phục vụ state machine

### 5.1. Case và trạng thái chuẩn hóa

| Nhóm | Trường gợi ý | Mục đích |
| --- | --- | --- |
| Phạm vi | Tenant, provider, environment, merchant account | Chặn nhầm nguồn và quyền |
| Ánh xạ | Provider dispute ID, payment/capture reference | Nối đúng giao dịch |
| Tiến trình | Raw status, normalized status, outcome | Giữ ý nghĩa nguồn và ý nghĩa nội bộ |
| Phiên bản | Provider revision nếu có, cycle reference, local version | Xử lý cạnh tranh và các chu kỳ |
| Phạm vi tiền | Disputed principal amount/currency, phân bổ liên quan | Không nhầm tiền gốc với phí |
| Hành động | Required action, deadline, response operation | Theo dõi công việc phải làm |
| Kiểm soát | Reconciliation flag, policy version, assigned team | Chặn tự động hóa khi chưa đủ thông tin |
| Thời điểm | Source occurred time, observed time, recorded time | Phân biệt lúc xảy ra và lúc hệ thống biết |

Không biến raw status không nhận diện được thành một trạng thái thuận tiện như resolved. Nên giữ giá trị nguồn, đánh dấu cần ánh xạ/đối soát và giới hạn những tự động hóa phụ thuộc vào trạng thái chưa hiểu.

Lưu phiên bản bộ ánh xạ giúp giải thích vì sao cùng mã nguồn được diễn giải theo một quy tắc cụ thể. Việc thay bộ ánh xạ hoặc backfill không được tạo lại các hiệu ứng tiền đã tồn tại.

### 5.2. Operation phản hồi và snapshot bằng chứng

Một operation gửi phản hồi nên gắn với:

```text
operation_id
case_id + cycle_reference
action_type
case_version_at_request
evidence_snapshot_id + evidence_revision
evidence_fingerprint
initiated_by + executed_by
idempotency_key + request_fingerprint
provider_request_reference / receipt_reference nếu có
execution_state
```

Bằng chứng cần là nội dung thực tế có căn cứ. Lưu nguồn, người cung cấp và phiên bản phù hợp để biết hồ sơ nào đã được gửi; không sửa tài liệu sau khi gửi để tạo cảm giác hồ sơ trước đó có nội dung khác.

Nếu attachment có thể bị thay dưới cùng một đường dẫn, chỉ lưu path chưa đủ. Có thể dùng object bất biến, content hash và kiểm tra lại khi gửi theo kiến trúc lưu trữ.

Mỗi tài liệu phải được kiểm tra quyền và quan hệ với case. Một nhân viên được xử lý case A không mặc nhiên được đọc attachment của tenant B bằng cách đổi object ID.

### 5.3. Hiệu ứng tiền và số dư theo dõi

Mỗi biến động nên lưu định danh nguồn, case, loại thành phần, số tiền, tiền tệ và chiều tác động được quy ước rõ.

Nếu tiền gốc theo tiền tệ giao dịch nhưng phí hoặc quyết toán theo tiền tệ khác, lưu riêng từng đại lượng và căn cứ chuyển đổi nếu có. Không dùng tỷ giá client gửi để làm ledger nội bộ có vẻ cân bằng.

Sổ theo dõi case không tự chứng minh tiền đã về tài khoản ngân hàng hay đã sẵn sàng chi tiêu. Các kết luận đó cần dữ liệu và quy tắc quyết toán liên quan.

Các risk hold hoặc claim phục vụ chặn refund là đối tượng kiểm soát nội bộ. Không ghi chúng như một debit thật từ provider.

## 6. Command gửi phản hồi: lưu ý định trước, xác nhận sau

### 6.1. Luồng tiếp nhận minh họa

Đoạn dưới là **mã giả**, không phải API Java có thể chạy trực tiếp:

```text
requestEvidenceSubmission(context, command, idempotencyKey):
    actor = authenticate(context)
    case = resolveAndAuthorizeCase(actor, command.caseId)
    fingerprint = canonicalCommandFingerprint(
        case,
        command.cycle,
        command.evidenceSnapshot,
        command.action
    )

    response = transaction:
        request = claimIdempotency(
            actor.scope,
            idempotencyKey,
            fingerprint
        )

        if request.alreadyExists:
            require request.fingerprint == fingerprint
            require actor may read request.operation
            return request.savedResponse

        lockedCase = lockCase(case.id)
        snapshot = lockAndValidateEvidenceSnapshot(command.snapshotId)

        require lockedCase.localVersion == command.expectedCaseVersion
        require command.cycle matches current case cycle
        require actor may submit for this scope
        require current action is permitted by mapped state and policy
        require deadline gate is satisfied for this action
        require no incompatible unresolved action exists
        require snapshot belongs to this case and is complete
        require snapshot content is immutable for this submission

        operation = createSubmissionOperation(
            state = SUBMISSION_PENDING,
            case = lockedCase,
            snapshot = snapshot,
            actor = actor
        )

        appendAudit(SUBMISSION_REQUESTED, operation)
        appendOutbox(EXECUTE_DISPUTE_ACTION, operation.id)
        response = pendingSubmissionResponse(operation)
        saveIdempotentResponse(request, response)

    return response after successful commit
```

Tại thời điểm này, case chưa tự chuyển sang under review hay có kết quả có lợi. Hệ thống mới có một operation được ghi bền vững để thực thi.

Các kiểm tra dựa trên bản sao trạng thái cần xét độ mới theo thiết kế. Nếu cần lấy thông tin mới từ provider, thực hiện bước lấy bằng chứng thích hợp ngoài transaction dài, rồi kiểm tra version cục bộ trước khi áp dụng. Provider vẫn là nơi quyết định lệnh có được chấp nhận tại thời điểm thực thi hay không.

### 6.2. Không thay snapshot trong lúc operation đang chờ

Nếu người dùng sửa bằng chứng sau khi tạo operation, tạo revision mới và xử lý theo quy tắc của action. Operation cũ vẫn trỏ tới snapshot cũ, không tự đọc “bản mới nhất” khi worker chạy.

Gửi lại cùng key nhưng đổi snapshot hoặc case phải báo xung đột. Gửi lại cùng ý định sau mất response phải trả operation cũ.

Không đặt unique trên toàn case cho mọi action: nguồn có thể cho phép nhiều thao tác hợp lệ ở các bước hoặc chu kỳ khác nhau. Khóa phải gắn với ý định, loại action và phạm vi của nó.

### 6.3. Chấp nhận tranh chấp là quyền riêng

Một người được soạn hoặc gửi bằng chứng không mặc nhiên được chấp nhận tranh chấp hay từ bỏ phản hồi. Nếu chính sách yêu cầu phê duyệt độc lập, approval phải gắn với case, chu kỳ, phạm vi tiền và action cụ thể.

Không cho một flag như `forceClose=true` bỏ qua tuyến này. “Đóng task nội bộ” cũng phải khác “gửi quyết định chấp nhận tới provider”.

Hai action đối nghịch, như gửi phản hồi và chấp nhận cùng một case, cần được phân xử trong phạm vi mà chính sách và tích hợp yêu cầu. Nếu một action đã gửi và chưa biết kết quả, không tự mở một action trái ngược chỉ vì timeout.

### 6.4. Worker và kết quả chưa biết

Worker đọc operation bất biến, gửi đúng action và dùng cơ chế chống trùng phù hợp của provider.

Nếu tích hợp hỗ trợ idempotency, key phải ổn định cho cùng operation. Nếu không có bảo đảm chống trùng tương ứng, cần cách tra cứu biên nhận, trạng thái hoặc quy trình xử lý ngoại lệ; một lock local không làm request bên ngoài trở thành đúng một lần.

| Kết quả quan sát | Cách xử lý |
| --- | --- |
| Có xác nhận tiếp nhận đúng nghĩa | Ghi action confirmed theo bằng chứng và hợp đồng tích hợp |
| Chỉ có xác nhận đang xử lý | Giữ pending, tiếp tục theo dõi |
| Timeout hoặc response mất | Ghi unknown khi chưa có kết quả cuối; tìm lại cùng operation |
| Từ chối cuối đã xác minh | Ghi thất bại action, giữ nguyên sự thật của case và mở xử lý tiếp |
| Nội dung không khớp case/action | Giữ bằng chứng, chặn cập nhật sai và đối soát |

Không coi mọi HTTP `2xx` là đã gửi hồ sơ hợp lệ. Không coi mọi lỗi mạng là chưa gửi gì.

Khi gần deadline mà action unknown, cần tăng mức ưu tiên điều tra và xác minh theo quy trình. Không đánh dấu submitted giả để làm chỉ số công việc hết quá hạn.

## 7. Tiếp nhận event và cập nhật từng chiều

### 7.1. Xác minh trước khi tác động

Luồng kiểm tra nên gồm:

1. Xác minh nguồn theo hợp đồng tích hợp, trên dữ liệu nguyên gốc cần thiết.
2. Kiểm tra provider, môi trường và merchant account của endpoint/event.
3. Tra cứu ánh xạ case và khoản thu do server quản lý.
4. Kiểm tra loại sự kiện, chu kỳ, phiên bản nếu có và các trường liên quan.
5. Tách thông tin case, kết quả action và hiệu ứng tiền.
6. Áp dụng mỗi phần theo state machine và khóa chống trùng tương ứng.

Một event hợp lệ có thể chưa đủ thông tin cho mọi chiều. Ví dụ, thông báo mở case không nhất thiết chứa balance transaction. Có thể ghi case đã mở trong khi giữ phần tài chính ở trạng thái chưa có thông tin.

Ngược lại, event không khớp phạm vi không được dùng để đổi case hoặc ledger chỉ vì chữ ký kiểm tra thành công.

### 7.2. Inbox và transaction xử lý

Mã giả dưới đây minh họa trường hợp dữ liệu liên quan nằm trong cùng database:

```text
ingestVerifiedEvent(event):
    persist durable inbox with scoped event uniqueness
    acknowledge only after durable acceptance

processInboxEvent(inboxId):
    event = loadVerifiedInbox(inboxId)
    binding = resolveTrustedCaseAndPaymentBinding(event)

    transaction:
        case = lockCase(binding.caseId)
        require binding still matches expected source context

        caseUpdate = assessCaseTransition(case, event.caseFacts)
        actionUpdate = assessActionResult(case, event.actionFacts)
        moneyFacts = validateFinancialFacts(event.moneyFacts)

        if caseUpdate.isAuthoritativeAndAllowed:
            applyCaseTransition(caseUpdate)
        else if caseUpdate.needsReconciliation:
            flagCaseForReconciliation()

        applyActionResultIdempotently(actionUpdate)

        for fact in moneyFacts:
            recordSourceFinancialEffectIfAbsent(fact)

        appendAuditForAppliedDecisions()
        appendOutboxForFollowUpWork()
        markInboxProcessed()
```

Nếu case và ledger thuộc các dịch vụ khác nhau, mỗi dịch vụ cần transaction cục bộ, outbox/inbox và cơ chế đối soát phù hợp. Không giả định một transaction local có thể commit nguyên tử cả hai database.

Có thể ack việc tiếp nhận trước khi xử lý nghiệp vụ nếu inbox đã bền vững và có đường phục hồi. Không ack thành công rồi chỉ để event trong bộ nhớ.

### 7.3. Hai lớp chống trùng

Lớp delivery có thể dùng:

```text
UNIQUE (provider, environment, merchant_account, event_id)
```

Lớp tác động cần gắn với fact nguồn:

```text
UNIQUE (source_context, source_financial_effect_id, component_if_needed)
UNIQUE (internal_action_operation_id, confirmed_effect_type)
```

Cùng event bị gửi lại sẽ không chạy lại. Cùng hiệu ứng xuất hiện qua event khác hoặc API response vẫn không tạo tác động lần hai.

Nếu cùng định danh nguồn nhưng payload thay đổi mâu thuẫn, không tự cộng như một hiệu ứng mới. Cần phân biệt lỗi, bản sửa theo hợp đồng và một biến động điều chỉnh có định danh riêng.

### 7.4. Sự kiện sai thứ tự và dữ kiện mâu thuẫn

Nếu nguồn cung cấp revision có ý nghĩa cho case, dùng nó theo phạm vi đúng. Một event revision cũ không được ghi đè lifecycle mới hơn.

Nếu không có thứ tự đủ tin cậy, không lấy thời điểm nhận hoặc timestamp bất kỳ làm quy tắc “mới nhất thắng”. Có thể cần tra cứu trạng thái hiện tại, giữ cờ chưa chắc chắn hoặc xử lý ngoại lệ.

Khi case đã resolved, một event open cũ có thể bị bỏ qua ở chiều lifecycle nhưng một credit mới đi kèm vẫn cần kiểm tra và ghi nếu hợp lệ, chưa tồn tại.

Một mở lại thật cần căn cứ của nguồn, được lưu như chuyển trạng thái/chu kỳ có kiểm soát. Không tự tái dùng snapshot hay operation của chu kỳ trước.

## 8. Phối hợp với refund và các nghiệp vụ khác

### 8.1. Chặn xung đột trên cùng phạm vi tiền

Giả sử refund đang được xem xét trong lúc chargeback vừa được ghi nhận. Một thiết kế kiểm soát có thể đặt hold trên phần capture liên quan và yêu cầu điều tra trước khi cho refund mới.

Đường refund và đường cập nhật hold cần dùng cơ chế cạnh tranh chung ở nơi quản lý quyền hoàn. Nếu mỗi dịch vụ tự kiểm tra một bản sao không nhất quán, cả hai vẫn có thể đi tiếp.

Hold không thu hồi được request refund mà provider đã nhận trước đó. Nếu refund đang pending/unknown, phải xác minh và phối hợp với case; không xóa nghĩa vụ đó rồi coi tiền chưa từng được hoàn.

### 8.2. Không tự động hoàn thêm vì case có kết quả bất lợi

Một kết quả bất lợi có thể liên quan đến việc xử lý tiền ở nguồn thanh toán. Tạo thêm refund toàn bộ chỉ dựa trên nhãn kết quả có thể làm khách nhận thêm ngoài phần đã được giải quyết.

Trước khi tạo action tiền mới, cần xác định khoản nào đã xảy ra, khoản nào đang chờ và điều gì còn được phép. Dữ liệu case, refund và balance transaction phải được đối chiếu chứ không thay thế lẫn nhau.

### 8.3. Lời báo của khách không phải kết quả cuối

Khách có thể nói đã rút khiếu nại hoặc đã giải quyết với bên khác. Đó là dữ kiện có thể lưu để xử lý, không phải bằng chứng đủ để gán case resolved favorable hay giải phóng mọi hold.

Cần chờ hoặc xác minh trạng thái có thẩm quyền theo quy trình. Nếu có thể tiếp tục xử lý bằng chứng trong khi chờ, công việc đó vẫn phải tuân theo deadline và quyền hiện tại.

### 8.4. Trạng thái case không tự thay đổi hàng vật lý

Nếu chính sách yêu cầu dừng giao khi phát sinh tranh chấp, tạo một lệnh dừng fulfillment có trạng thái riêng và kiểm tra quyền. Lệnh đó có thể đang chờ hoặc bị từ chối vì đã chốt xuất.

Không gán tồn kho tăng chỉ vì case bị đóng, và không đánh dấu hàng đã trả lại nếu chưa có căn cứ nhận hàng. Quy trình bảo vệ tiền và quy trình quản lý hàng phải liên kết nhưng giữ đúng sự thật của từng bên.

## 9. Ví dụ dòng thời gian: kết quả case và tiền không đi cùng nhịp

Giả sử khoản thu gốc là 1.000.000 đồng. Một case tranh chấp 400.000 đồng được nguồn xác nhận. Ví dụ này dùng cùng một tiền tệ và các con số minh họa, không quy định mức phí cho tích hợp thực tế.

Quy ước dấu trong bảng: số âm làm giảm số dư merchant được nguồn báo, số dương làm tăng. Các dòng tiền chỉ mô tả những hiệu ứng nguồn đã được xác minh và ghi nhận.

| Bước | Dữ kiện nhận được | Lifecycle / action | Hiệu ứng tiền mới |
| --- | --- | --- | --- |
| 1 | Case cần phản hồi | `ACTION_REQUIRED`, chưa gửi | Chưa có fact tiền trong dữ liệu đã nhận |
| 2 | Balance transaction T1 và F1 | Lifecycle không tự đổi | T1: debit tiền gốc -400.000; F1: debit phí -20.000 |
| 3 | Có xác nhận nhận hồ sơ và trạng thái xem xét tương ứng | Action confirmed, case `UNDER_REVIEW` theo nguồn | Không tự tạo tiền |
| 4 | Có kết quả có lợi | `RESOLVED`, outcome `FAVORABLE` | Chưa có fact credit mới |
| 5 | Balance transaction T2 | Giữ kết quả case | T2: credit tiền gốc +400.000 |
| 6 | Delivery cũ của T1 được gửi lại | Không làm lùi case | Không ghi debit lần hai |

Sau bước 4, hệ thống biết kết quả có lợi nhưng chưa có căn cứ để tự thêm credit vào sổ. Có thể còn công việc đối soát, tùy nguồn và chính sách.

Sau bước 5, tổng các hiệu ứng chargeback đã liệt kê là:

```text
-400.000 - 20.000 + 400.000 = -20.000
```

Điều đó không có nghĩa phí chắc chắn không bao giờ được điều chỉnh. Nó chỉ có nghĩa chưa có fact fee credit trong ví dụ. Nếu sau đó có một điều chỉnh phí hợp lệ, ghi một hiệu ứng riêng theo định danh nguồn.

Tổng này cũng không phải toàn bộ số dư tài khoản merchant: nó chỉ cộng các dòng liên quan đã nêu, không bao gồm mọi khoản thu, payout hoặc điều chỉnh khác.

### Event open cũ đến sau kết quả

Nếu một event cũ báo `OPEN` đến sau bước 5, không gán case về open chỉ vì đó là delivery mới nhất.

Nếu event đến muộn mang thêm một hiệu ứng tiền chưa biết, xử lý phần tiền theo định danh và bằng chứng riêng. Không dùng quy tắc “case đã resolved nên bỏ toàn bộ event” để mất dữ liệu.

### Một mở lại thật xuất hiện

Nếu nguồn xác nhận mở lại hoặc chuyển sang chu kỳ mới theo mô hình của tích hợp, lưu căn cứ và cập nhật trạng thái có kiểm soát. Đánh giá lại công việc, deadline, hold và quyền liên quan.

Không tự gửi lại hồ sơ cũ hoặc tạo lại debit cũ. Một chu kỳ mới không làm các hiệu ứng đã ghi ở chu kỳ trước trở thành chưa từng xảy ra.

## 10. Audit và đối soát vận hành

### 10.1. Ghi quyết định cùng căn cứ

Audit của một thay đổi nên liên kết:

| Nhóm | Thông tin cần thiết |
| --- | --- |
| Đối tượng | Tenant, merchant, môi trường, case, payment/capture nguồn |
| Quyết định | Trạng thái trước/sau, outcome, cycle, local version |
| Nguồn | Event/query/command, source reference, revision nếu có |
| Chủ thể | Người khởi tạo, service thực thi, người phê duyệt nếu cần |
| Hành động | Operation, snapshot bằng chứng, biên nhận và kết quả |
| Tiền | Balance transaction, thành phần, số tiền, tiền tệ, chiều tác động |
| Nhân quả | Correlation ID, causation ID, outbox/inbox liên quan |
| Chính sách | Bộ ánh xạ và policy version được sử dụng |

Phải phân biệt yêu cầu gửi với kết quả gửi, thông tin khách cung cấp với dữ kiện nguồn và công việc nội bộ với trạng thái case bên ngoài.

Các thao tác bị từ chối hoặc command trùng có thể được lưu để điều tra nhưng không được tính như một chuyển trạng thái thành công.

### 10.2. Bảo vệ bằng chứng và phạm vi đọc

Lịch sử thay đổi và snapshot đã dùng cần được bảo vệ khỏi sửa/xóa tùy tiện qua các tài khoản ứng dụng. Sửa sai phải có hành động mới, lý do và quan hệ với bản cũ.

Quyền đọc evidence, download attachment và export cần theo tenant, case và phạm vi vai trò. Không để biết một object ID là đủ để lấy dữ liệu giao dịch của đơn vị khác.

Chỉ lưu thông tin cần thiết cho xử lý và giải trình. Không đưa token, bí mật ký event hay dữ liệu thanh toán nhạy cảm không cần thiết vào audit. Ghi chú và mô tả được xử lý như dữ liệu khi hiển thị, không trở thành nội dung có quyền thực thi.

### 10.3. Những kiểm tra nên có

- Case có raw status chưa ánh xạ nhưng đang kích hoạt tự động hóa phụ thuộc vào kết quả.
- Case cần hành động nhưng chưa có người hoặc tác vụ chịu trách nhiệm.
- Submission pending/unknown quá lâu hoặc gần deadline mà chưa có xác nhận phù hợp.
- Case đã resolved nhưng còn action hoặc hiệu ứng tiền chưa được đối soát; đây là công việc cần xử lý, không mặc nhiên là dữ liệu sai.
- Cùng source effect được ghi nhiều lần, hoặc cùng ID có payload mâu thuẫn.
- Case có biến động tiền nhưng chưa gắn đúng khoản thu hoặc ngược lại.
- Refund mới đi qua trong khi hold chính sách còn hiệu lực.
- Một outcome có lợi bị dùng để tự tạo credit hoặc mở giao hàng ngoài chính sách.
- Nội dung bằng chứng đã gửi không khớp snapshot operation.
- Tác vụ accept/submit hoặc thao tác hỗ trợ vượt phạm vi quyền.

Khi đối soát, chọn cùng phạm vi merchant, môi trường, tiền tệ và mốc dữ liệu. Replica hoặc báo cáo có thể chậm; cần xác minh trước khi tự sửa trạng thái nguồn chính.

Một phản hồi thiếu không chứng minh action chưa xảy ra. Một balance transaction chưa xuất hiện ở projection cũng không chứng minh tiền chưa di chuyển. Các kết luận phải dựa trên nguồn đủ tin cậy.

### 10.4. Xử lý lỗi không được che mất sự thật

Nếu ánh xạ sai, giữ mã nguồn và lịch sử quyết định, sửa quy tắc có kiểm soát rồi đối soát các case ảnh hưởng. Không ghi đè toàn bộ lịch sử để làm như hệ thống đã luôn hiểu đúng.

Nếu một công việc phản hồi bị bỏ lỡ, ghi nhận tình trạng thật và đi qua quy trình xử lý. Không gán submitted hoặc thay deadline cũ để làm báo cáo đẹp hơn.

Nếu tiền có tác động ngoài dự kiến, ghi đúng fact và mở xử lý nghiệp vụ. Không sửa outcome để ép case khớp với số dư đang có.

## 11. Kiểm thử tình huống lạm dụng logic

Mỗi ca cần kiểm tra lifecycle, outcome, action, ledger, hold, quyền và audit. Mã HTTP thành công không đủ để xác nhận mọi bất biến.

| Tình huống | Kết quả cần đạt |
| --- | --- |
| Client gửi `status=WON` hoặc `outcome=FAVORABLE` | Không tự cập nhật kết quả có thẩm quyền |
| Nhân viên đổi case ID sang tenant/merchant khác | Bị chặn ở command, API đọc và export |
| Event đúng chữ ký nhưng sai môi trường hoặc merchant | Không tác động lên case thật ngoài phạm vi |
| Metadata trỏ sang order khác nhưng payment reference không khớp | Không ánh xạ theo metadata tùy tiện |
| Tranh chấp chỉ một phần capture | Được mô hình hóa đúng phạm vi, không bắt bằng toàn khoản thu |
| Raw status chưa nhận diện | Giữ giá trị nguồn và cờ cần xử lý; không mặc định resolved |
| Cùng event được gửi nhiều lần | Không lặp chuyển trạng thái hoặc hiệu ứng |
| Cùng debit xuất hiện ở event khác ID | Chỉ một fact tiền theo định danh nguồn |
| Cùng source effect ID nhưng nội dung mâu thuẫn | Không cộng như hiệu ứng mới; đưa vào đối soát |
| Event open cũ đến sau resolved | Không làm lùi case nếu không có căn cứ mở lại |
| Event lifecycle cũ chứa fact tiền mới hợp lệ | Không áp lifecycle cũ, vẫn ghi fact tiền chưa có |
| Có kết quả thuận lợi nhưng chưa có credit | Không tự ghi credit hoặc hoàn phí |
| Mở lại thật theo nguồn | Cập nhật đúng chu kỳ, không tái áp dụng các debit/credit cũ |
| Gửi bằng chứng timeout rồi retry | Tìm lại cùng operation; không tự xác nhận submitted |
| Sửa attachment/snapshot sau khi tạo operation | Operation không âm thầm gửi nội dung mới |
| Lấy attachment của tenant khác đưa vào hồ sơ | Bị chặn quyền và quan hệ đối tượng |
| Submit và accept chạy đồng thời | Phân xử theo state machine và các action chưa giải quyết |
| Deadline local đã qua nhưng chưa có kết quả case | Đánh dấu công việc phù hợp, không tự kết luận thua |
| Refund đang unknown khi chargeback mở | Không xóa claim refund hoặc tạo khoản thay thế thiếu căn cứ |
| Khách báo đã rút tranh chấp | Không tự đóng case hoặc giải phóng mọi hold |
| Kết quả bất lợi đến | Không tự tạo refund thêm hoặc lệnh thu mới |
| Consumer chết sau commit trước ack | Delivery lại không áp dụng lần hai |
| Lỗi ghi outbox khi tạo operation | Rollback các thay đổi cục bộ liên quan |
| Phí khác tiền tệ với principal | Không cộng số thô hoặc giả chuyển đổi tiền tệ |
| Đóng task nội bộ rồi có event tiền đến | Event hợp lệ vẫn được tiếp nhận và đối soát |

Các ca cạnh tranh cần điều phối tác vụ tới cùng điểm kiểm tra và cập nhật. Chạy tuần tự không chứng minh được việc chống race.

Cũng cần kiểm tra đường hợp lệ: tranh chấp từng phần, phản hồi có xác nhận, event tiền đến sau kết quả và mở lại được nguồn hỗ trợ. Một state machine cứng quá mức có thể chặn những chuyển hợp lệ, trong khi một enum quá lỏng lại cho phép bỏ qua điều kiện.

## 12. Bài tập áp dụng

### Bài tập 1: Case đã resolved có được bỏ event cũ không?

Case D-1 đã `RESOLVED` với outcome `FAVORABLE`. Sổ hiện có debit tiền gốc 300.000 và debit phí 10.000, chưa có credit. Một event đến muộn chứa raw lifecycle cũ nhưng đồng thời mang balance transaction credit tiền gốc 300.000 chưa từng ghi.

Hãy xác định cách xử lý từng chiều.

**Gợi ý giải:** Không đưa case về lifecycle cũ nếu đó không phải mở lại hợp lệ. Kiểm tra credit theo nguồn, phạm vi, số tiền, tiền tệ và định danh hiệu ứng; nếu hợp lệ và chưa có thì ghi đúng một lần. Tổng các fact trong bài tập sau đó là `-300.000 - 10.000 + 300.000 = -10.000`. Không tự tạo thêm credit phí khi chưa có bằng chứng.

### Bài tập 2: Timeout trước deadline nói lên điều gì?

Một operation gửi bằng chứng được tạo trước deadline. Worker gọi provider rồi timeout. Nhân viên thấy task còn pending nên đổi trực tiếp case thành under review và action thành submitted để đóng công việc.

Hãy chỉ ra điều sai và đề xuất cách phục hồi.

**Gợi ý giải:** Thời điểm tạo job và timeout không chứng minh provider đã nhận hồ sơ theo yêu cầu. Action cần thể hiện unknown khi chưa có kết quả cuối, được tra cứu hoặc retry theo cùng định danh và cơ chế của tích hợp. Lifecycle chỉ đổi khi có căn cứ tương ứng. Cần theo dõi deadline, ưu tiên đối soát và lưu bằng chứng thực tế; không sửa trạng thái để che khoảng chưa biết.

Trạng thái chargeback đáng tin cậy khi mỗi chuyển có nguồn, quyền và điều kiện rõ ràng, còn tác động tiền được giữ riêng theo từng fact đã xác minh. Những phần đang chờ, mâu thuẫn hoặc chưa hiểu phải tiếp tục xuất hiện trong quy trình xử lý thay vì bị ép vào một trạng thái cuối cho thuận tiện.
