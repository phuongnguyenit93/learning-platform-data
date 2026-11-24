# Administrative approval — Phê duyệt thao tác quản trị

## 1. Vì sao thao tác quản trị cần được phê duyệt?

Administrative approval là cơ chế yêu cầu một thao tác quản trị nhạy cảm được xem xét và chấp thuận theo chính sách trước khi hệ thống cho phép thực thi. Nó thường áp dụng cho hoàn tiền thủ công, điều chỉnh số dư, tăng hạn mức, thay giá đặc biệt, cấp quyền cao hoặc bỏ một ràng buộc vận hành.

Tài khoản quản trị có nhiều khả năng gây tác động lớn hơn tài khoản thông thường. Nếu một người có thể tự tạo yêu cầu, tự phê duyệt, sửa nội dung sau khi duyệt rồi gọi lại lệnh nhiều lần, nhãn “cần phê duyệt” không bảo vệ được quy tắc nghiệp vụ.

Trong bảo mật logic nghiệp vụ, cơ chế này phải bảo đảm:

- Đúng người được đề nghị đúng hành động trên đúng đối tượng.
- Đúng người độc lập xem xét nội dung cần phê duyệt.
- Nội dung thực thi khớp nội dung đã được duyệt.
- Các điều kiện nghiệp vụ vẫn hợp lệ tại thời điểm thực hiện.
- Retry và cạnh tranh không tạo thêm tác động ngoài ý muốn.
- Có thể truy vết ai yêu cầu, ai quyết định và kết quả thực tế.

Phê duyệt là một lớp kiểm soát trong quy trình. Nó không thay thế kiểm tra quyền, validation, transaction hoặc idempotency.

## 2. Phân biệt phê duyệt với các cơ chế gần nhau

| Cơ chế | Câu hỏi được trả lời | Giới hạn cần hiểu |
| --- | --- | --- |
| Xác thực | Người đang thao tác là ai? | Danh tính hợp lệ chưa cho phép thao tác trên mọi đối tượng |
| Phân quyền | Người đó có được thực hiện hành động này trong ngữ cảnh này không? | Có quyền chưa có nghĩa một đề nghị cụ thể đã được duyệt |
| Phê duyệt | Đề nghị cụ thể này đã được người phù hợp chấp thuận chưa? | Phải ràng buộc với nội dung, phiên bản, thời hạn và chính sách |
| Xác thực tăng cường | Có thêm bằng chứng về người đang thao tác không? | Một người xác thực lại vẫn chỉ là một người |
| Idempotency | Gửi lại cùng ý định có tạo thêm tác động không? | Không ngăn mọi hành vi dùng ý định mới để lặp một lợi ích |
| Audit | Chuyện gì đã xảy ra và ai liên quan? | Ghi nhận không tự ngăn hành động sai |

Ví dụ: người vận hành có quyền đề nghị hoàn tiền nhưng không có quyền tự duyệt yêu cầu của mình. Người duyệt có quyền chấp thuận hoàn tiền trong một tenant, nhưng không được duyệt khoản tiền thuộc tenant khác. Worker thực thi được duyệt cũng phải kiểm tra giới hạn có thể hoàn của khoản thanh toán.

## 3. Mô hình vai trò và phân tách nhiệm vụ

Một quy trình thường có các vai trò sau:

| Vai trò | Trách nhiệm |
| --- | --- |
| Người yêu cầu, maker | Tạo đề nghị, cung cấp lý do và dữ liệu cần thiết |
| Người duyệt, checker | Xem nội dung, kiểm tra căn cứ và đưa ra quyết định |
| Bộ thực thi | Thực hiện đúng lệnh được phép sau khi đạt điều kiện |
| Người quản lý chính sách | Quản lý ngưỡng, nhóm duyệt và điều kiện phê duyệt |
| Người kiểm tra dấu vết | Đối chiếu quyết định với tác động thực tế |

Một người có thể giữ nhiều vai trò trong tổ chức, nhưng chính sách phải cấm các tổ hợp gây xung đột trên cùng yêu cầu. Ví dụ, người có cả quyền tạo và quyền duyệt vẫn không được tự duyệt đề nghị mình tạo nếu quy trình yêu cầu maker–checker.

### 3.1. Tính độc lập phải gắn với con người

So sánh hai tên đăng nhập chưa đủ khi cùng một người có nhiều tài khoản. Nếu sản phẩm yêu cầu hai người độc lập, cần mô hình danh tính tổ chức phù hợp để nhận biết hai tài khoản thuộc cùng một chủ thể.

Các vấn đề cần xét:

- Tài khoản dùng chung làm mất khả năng quy trách nhiệm.
- Tài khoản dịch vụ không tự động được tính như một người duyệt độc lập.
- Một người không được gửi nhiều phiếu bằng nhiều phiên đăng nhập.
- Hai người duyệt có thể phải thuộc hai nhóm khác nhau theo chính sách.
- Người quản lý chính sách không được tự hạ ngưỡng để hợp thức hóa đề nghị của mình.

Maker–checker giảm rủi ro từ sai sót hoặc lạm dụng của một người; nó không loại bỏ thông đồng hay việc nhiều tài khoản cùng bị chiếm quyền. Các giới hạn này cần được xử lý cùng kiểm soát quyền, cảnh báo và kiểm tra sau thực hiện.

### 3.2. Phê duyệt theo đối tượng và hành động

Quyền duyệt nên biểu diễn đầy đủ ngữ cảnh, chẳng hạn:

~~~text
canApprove(
    actor,
    action = REFUND,
    tenant = T-A,
    target = PAYMENT-42,
    amountMinor = 12000000,
    currency = VND,
    requestRevision = 3
)
~~~

Tên vai trò “admin” hoặc “finance” không tự chứng minh mọi điều kiện trên. Kiểm tra ở máy chủ phải xét phạm vi tenant, loại hành động, đối tượng, hạn mức và các điều kiện độc lập tương ứng.

## 4. Xác định thao tác nào cần phê duyệt

Không phải mọi thao tác quản trị đều cần cùng một quy trình. Nhóm nghiệp vụ cần xác định chính sách dựa trên tác động, khả năng phục hồi và nguy cơ lạm dụng.

| Loại thao tác | Quy tắc có thể cần bảo vệ |
| --- | --- |
| Hoàn tiền thủ công | Tổng hoàn và giữ chỗ không vượt số tiền được phép |
| Điều chỉnh số dư | Có căn cứ; không ghi tiền tùy ý; sổ cái vẫn nhất quán |
| Sửa giá hoặc chiết khấu | Có quyền sửa; đáp ứng giới hạn; không dùng phê duyệt cho giá khác |
| Tăng hạn mức | Người duyệt đủ thẩm quyền; hiệu lực và phạm vi rõ ràng |
| Cấp quyền đặc biệt | Không tự cấp quyền; quyền có phạm vi và thời hạn phù hợp |
| Thay quy tắc phê duyệt | Không tạo đường bỏ qua chính cơ chế kiểm soát |
| Chạy lại tác vụ lỗi | Không tạo khoản thu, hoàn tiền hoặc quyền lợi trùng |

Chính sách nên xác định ít nhất:

1. Điều kiện kích hoạt phê duyệt.
2. Số người duyệt cần thiết và yêu cầu về nhóm hoặc vai trò.
3. Trường dữ liệu mà quyết định phê duyệt ràng buộc.
4. Thời hạn hiệu lực.
5. Khi nào phải duyệt lại hoặc vô hiệu phiếu cũ.
6. Điều kiện được thực thi và cách thu hồi trước thực thi.
7. Cách xử lý ngoại lệ và kết quả chưa xác định.

**Ví dụ chính sách minh họa:** mọi khoản hoàn thủ công cần một người khác duyệt; khoản vượt ngưỡng nội bộ cần hai người thuộc các nhóm được chỉ định. Ngưỡng và số người là quyết định của từng sản phẩm, không có giá trị mặc định áp dụng cho mọi hệ thống.

Nếu điều kiện phụ thuộc tổng giá trị trong ngày hoặc một nhóm giao dịch liên quan, phải tính ở mức tổng hợp. Chỉ xét từng request có thể cho phép chia nhỏ khoản tiền để né ngưỡng.

## 5. Thiết kế yêu cầu phê duyệt có nội dung bất biến

Người duyệt cần biết chính xác mình đang cho phép điều gì. Không nên chỉ lưu một cờ như `approved = true` trên đối tượng có thể bị sửa tùy ý.

Một yêu cầu có thể gồm:

~~~json
{
  "requestId": "AR-73002",
  "revision": 3,
  "tenantId": "T-A",
  "action": "REFUND",
  "targetType": "PAYMENT",
  "targetId": "PAYMENT-42",
  "targetVersion": 8,
  "payload": {
    "amountMinor": 12000000,
    "currency": "VND",
    "destinationReference": "ORIGINAL_PAYMENT"
  },
  "reason": "Hoàn phần dịch vụ chưa cung cấp",
  "evidenceReference": "CASE-204",
  "policyVersion": "refund-policy-7",
  "status": "PENDING",
  "expiresAt": "2030-01-10T10:00:00Z"
}
~~~

Đây là dữ liệu minh họa; hạn dùng và thời điểm không phải cấu hình được khuyến nghị. Danh tính người yêu cầu và các trường hệ thống phải lấy từ ngữ cảnh đáng tin cậy hoặc được máy chủ xác định.

### 5.1. Ràng buộc quyết định với đúng nội dung

Mỗi phiếu cần liên kết đến `requestId`, `revision` và nội dung có ý nghĩa nghiệp vụ. Các trường thường quan trọng gồm tenant, đối tượng, hành động, số tiền, tiền tệ, tài khoản nhận, thời hạn và điều kiện thực hiện.

Nếu một trường quan trọng thay đổi:

- Không được giữ phiếu cũ cho nội dung mới.
- Có thể tạo revision mới hoặc tạo yêu cầu mới theo thiết kế.
- Người duyệt phải xem và quyết định lại.
- Lịch sử phiên bản và quyết định cũ vẫn phải truy vết được.

Cách đơn giản là cho phép sửa khi còn nháp và khóa nội dung khi gửi duyệt. Mọi chỉnh sửa sau đó tạo một phiên bản mới cần duyệt lại.

### 5.2. Hash nội dung hỗ trợ kiểm tra, không tự tạo niềm tin

Có thể lưu digest của biểu diễn chuẩn hóa để phát hiện nội dung không còn khớp phiếu duyệt. Biểu diễn đó phải xác định rõ tên trường, kiểu dữ liệu, đơn vị tiền, thứ tự tập hợp và cách xử lý giá trị thiếu.

Máy chủ phải tự tính digest từ dữ liệu có thẩm quyền. Không tin `payloadHash` client gửi, và không coi việc có hash là thay thế cho kiểm soát ghi dữ liệu. Nếu một chủ thể có thể sửa cả payload lẫn digest hoặc phiếu duyệt, digest đó không tạo ra bảo đảm độc lập.

### 5.3. Phiên bản đối tượng đích

Phê duyệt có thể dựa trên trạng thái của một đơn, khoản thanh toán hoặc hạn mức tại một thời điểm. Nếu đối tượng đổi, cần xác định thay đổi nào làm quyết định mất hiệu lực.

Khóa theo toàn bộ `targetVersion` có thể đơn giản nhưng dễ vô hiệu phê duyệt vì thay đổi không liên quan. Một thiết kế khác theo dõi phiên bản của tập dữ liệu quan trọng. Dù chọn cách nào, quy tắc phải rõ và được kiểm tra khi thực thi.

## 6. State machine cho quy trình phê duyệt

Một mô hình rút gọn:

~~~text
DRAFT → PENDING → APPROVED → EXECUTING → APPLIED
           │          │           │
           ├→ REJECTED│           ├→ FAILED
           ├→ CANCELLED           └→ EXECUTION_UNKNOWN
           └→ EXPIRED │
                      ├→ CANCELLED
                      └→ EXPIRED
~~~

Sơ đồ chỉ minh họa các nhánh chính. `EXECUTION_UNKNOWN` cần được đối soát để xác định tác động đã xảy ra hay chưa; không tự chuyển sang `FAILED` chỉ vì hết thời gian chờ.

| Chuyển trạng thái | Điều kiện chính |
| --- | --- |
| DRAFT → PENDING | Người gửi có quyền; nội dung hợp lệ; máy chủ chọn chính sách |
| PENDING → APPROVED | Đủ phiếu hợp lệ, đủ độc lập, đúng revision và chưa hết hạn |
| PENDING → REJECTED | Người có thẩm quyền từ chối theo chính sách |
| PENDING/APPROVED → CANCELLED | Chưa qua ranh giới không thể hủy; người hủy có quyền |
| PENDING/APPROVED → EXPIRED | Không còn trong thời gian hiệu lực |
| APPROVED → EXECUTING | Lệnh được giành quyền thực hiện và tái kiểm tra điều kiện cần thiết |
| EXECUTING → APPLIED | Đã xác nhận tác động nghiệp vụ thành công |
| EXECUTING → FAILED | Đã biết chắc thất bại theo hợp đồng xử lý |
| EXECUTING → EXECUTION_UNKNOWN | Chưa xác định được tác động do mất phản hồi hoặc lỗi liên lạc |

Không để endpoint cập nhật chung sửa trực tiếp `status`, `approvedBy`, `requiredApprovals` hoặc `policyVersion`. Máy chủ thực hiện từng lệnh hợp lệ qua state machine.

Với hết hạn, không cần chờ một cron đổi trạng thái mới từ chối. Điều kiện thời gian phải được kiểm tra ngay tại ranh giới chấp nhận quyết định hoặc giành quyền thực thi, dùng nguồn thời gian nhất quán theo thiết kế.

## 7. Luồng xử lý từ đề nghị đến thực hiện

### Bước 1 — Tạo và gửi yêu cầu

Máy chủ xác thực người gửi, kiểm tra quyền trên đối tượng, chuẩn hóa payload, chọn chính sách và lưu nội dung cần duyệt. Những trường như số phiếu cần thiết hoặc người tạo không được lấy tùy ý từ body.

Tạo đề nghị cũng có thể là thao tác cần idempotency. Nếu client mất phản hồi rồi gửi lại, không nên tạo nhiều đề nghị giống nhau khiến nhiều người duyệt độc lập và cuối cùng thực hiện nhiều lần.

### Bước 2 — Trình bày nội dung để quyết định

Giao diện hiển thị giá trị trước và sau, phạm vi tenant, số tiền, tiền tệ, người nhận, lý do, bằng chứng và cảnh báo liên quan. Với batch, người duyệt phải biết tập đối tượng cụ thể và tổng tác động.

Chỉ hiện nhãn “hoàn tiền cho khách hàng” trong khi ẩn số tiền hoặc đích nhận làm quyết định không đủ căn cứ. Nếu tập đối tượng được chọn bằng truy vấn động, cần đóng băng tập được duyệt hoặc định nghĩa rõ giới hạn của truy vấn và kiểm tra lại khi thực hiện.

### Bước 3 — Ghi phiếu duyệt hoặc từ chối

Máy chủ kiểm tra actor hiện tại, quyền theo đối tượng, tính độc lập, revision, thời hạn và chính sách. Phiếu được lưu với danh tính lấy từ phiên xác thực, thời điểm và căn cứ cần thiết.

Thao tác duyệt lặp lại từ cùng một người không được tăng số phiếu. Khi cần nhiều người duyệt, quorum là số phiếu đáp ứng điều kiện, không chỉ là số hàng trong bảng.

### Bước 4 — Giành quyền thực thi

Sau khi đạt quorum, hệ thống giành quyền xử lý đúng phiên bản yêu cầu bằng cơ chế nguyên tử. Tại đây cần kiểm tra lại các điều kiện có thể đổi: hiệu lực phê duyệt, điều kiện đối tượng, hạn mức và chính sách quyền áp dụng.

Một response “đã duyệt” không phải giấy phép cho client tự gửi payload khác tới endpoint thực thi.

### Bước 5 — Thực hiện và xác nhận kết quả

Bộ thực thi dùng payload đã khóa. Thay đổi nội bộ phải giữ invariant trong transaction phù hợp. Tác động ngoài hệ thống cần mã tham chiếu ổn định, xử lý trùng và luồng đối soát.

Chỉ đánh dấu `APPLIED` khi có bằng chứng thành công theo hợp đồng nghiệp vụ. Nếu kết quả chưa rõ, giữ trạng thái chưa xác định và tiếp tục đối soát.

## 8. Quyền, chính sách và thời điểm có hiệu lực

Cần đặc tả điều gì xảy ra nếu quyền hoặc chính sách đổi trong khi yêu cầu đang chờ. Chỉ kiểm tra quyền lúc mở trang duyệt tạo ra khoảng trống: người dùng có thể mở trang, bị thu hồi quyền rồi vẫn gửi quyết định.

### 8.1. Kiểm tra tại thời điểm ra quyết định

Mỗi lệnh duyệt phải kiểm tra quyền hiện hành theo tenant, hành động và đối tượng. Không lấy quyền từ dữ liệu giao diện cũ hoặc trường `approverRole` trong request.

Nếu phiên xác thực còn sống nhưng quyền duyệt đã bị thu hồi, hành động phải theo chính sách thu hồi thực tế của hệ thống. Cần xác định cơ chế vô hiệu cache hoặc phiên bản quyền để tránh tiếp tục tin quyền cũ quá thời gian cho phép.

### 8.2. Phiếu cũ có tiếp tục hợp lệ sau thu hồi quyền không?

Có hai chính sách thường gặp:

| Chính sách | Ý nghĩa |
| --- | --- |
| Công nhận quyết định tại thời điểm ký duyệt | Phiếu hợp lệ khi được tạo có thể tiếp tục có giá trị sau khi người duyệt đổi vai trò |
| Yêu cầu người duyệt còn đủ điều kiện tại lúc thực thi | Phiếu có thể mất hiệu lực khi quyền hoặc tư cách của người duyệt thay đổi |

Không có một lựa chọn đúng cho mọi nghiệp vụ. Hệ thống phải chọn rõ, ghi nhận căn cứ và xử lý việc thu hồi khẩn cấp. Với chính sách thứ hai, không được dùng một bộ đếm quorum cũ mà không xét điều kiện hiện tại.

Nếu chính sách đổi, cần quy định yêu cầu cũ tiếp tục theo phiên bản đã chốt, được chuyển sang chính sách mới hay phải duyệt lại. Ghim phiên bản chính sách giúp giải thích quyết định, nhưng không có nghĩa mọi phê duyệt cũ đều được phép bỏ qua lệnh thu hồi bắt buộc.

### 8.3. Quyền của người thực thi

Một worker có thể thực hiện bằng quyền dịch vụ thay vì quyền của người tạo. Khi đó, hệ thống phải kiểm tra một ủy quyền có phạm vi đã được phê duyệt: hành động gì, trên đối tượng nào, với payload nào, đến khi nào.

Không biến tài khoản dịch vụ thành đường vòng cho một người không còn được phép tạo hoặc thúc đẩy hành động. Ngược lại, không tùy tiện coi việc người tạo đăng xuất là lý do hủy một tác vụ đã được ủy quyền hợp lệ.

### 8.4. Ranh giới thu hồi và thực thi

Phải xác định điểm mà yêu cầu được chấp nhận để thực thi. Ví dụ, một transaction chuyển `APPROVED` sang `EXECUTING` và giữ chỗ hạn mức có thể là ranh giới đó.

Nếu chính sách yêu cầu “thu hồi trước ranh giới này luôn ngăn thực hiện”, cơ chế kiểm soát quyền/chính sách và transaction phải phối hợp để bảo đảm thứ tự đó. Chỉ đọc quyền từ dịch vụ khác rồi cập nhật sau không tự tạo bảo đảm nguyên tử giữa hai hệ thống.

Sau khi lệnh đã được gửi đến hệ thống ngoài, hủy có thể chỉ là yêu cầu cố gắng dừng. Không báo hủy thành công chắc chắn khi tác động có thể đã xảy ra; cần đối soát hoặc hành động bù trừ riêng.

## 9. Transaction và cạnh tranh khi phê duyệt

### 9.1. Hai người cùng gửi phiếu cuối

Giả sử yêu cầu cần hai người duyệt và đã có một phiếu. Hai người còn lại cùng đọc trạng thái `PENDING`, cùng ghi phiếu rồi cùng kích hoạt thực thi.

Quy trình cần bảo đảm:

- Một người chỉ có một quyết định đang có hiệu lực cho cùng revision theo chính sách.
- Việc ghi phiếu, tính quorum và chuyển trạng thái được kiểm soát trong transaction.
- Chỉ một bên chuyển thành công từ `PENDING` sang `APPROVED`.
- Nếu tạo lệnh hoặc outbox event, việc tạo đó đi cùng chuyển trạng thái theo ranh giới nguyên tử đã chọn.
- Bên bị xung đột đọc lại trạng thái hoặc trả kết quả phù hợp, không tiếp tục tạo tác động lần nữa.

Có thể dùng khóa hàng, kiểm soát phiên bản hoặc cơ chế tương đương. Constraint duy nhất trên `(request_id, revision, approver_subject_id)` hỗ trợ chống phiếu trùng; nó không tự bảo đảm quorum đúng nhóm hoặc hai tài khoản không thuộc cùng người.

### 9.2. Minh họa xử lý một phiếu

Đoạn sau là giả mã, không phải mã hoàn chỉnh của một framework:

~~~text
transaction:
    request = loadApprovalRequestForUpdate(requestId)

    require request.status == PENDING
    require request.revision == submittedRevision
    require trustedNow() < request.expiresAt

    actor = authenticatedActor()
    require canApproveNow(actor, request)
    require satisfiesIndependence(actor, request)

    insertDecisionOnce(
        request.id,
        request.revision,
        actor.subjectId,
        decision = APPROVE
    )

    votes = loadEligibleDecisions(request)
    if policyQuorumSatisfied(request.policyVersion, votes):
        changeStatus(request, PENDING, APPROVED)
        appendAuditEvent(APPROVAL_GRANTED, request, actor)
        insertOutboxOnce(APPROVAL_READY, request.id, request.revision)
~~~

Quy tắc về từ chối, rút phiếu hoặc đổi quyết định phải được xác định riêng. Nếu tổ chức cho phép rút phiếu, việc rút cần kiểm tra trạng thái và cập nhật tính hợp lệ của phê duyệt bằng cùng cơ chế kiểm soát cạnh tranh. Không sửa mất lịch sử quyết định.

Giả mã giả định các điều kiện được đọc có mức nhất quán cần thiết. Khóa hàng yêu cầu không tự khóa mọi nguồn quyền, chính sách hoặc dữ liệu khác; triển khai phải xử lý những phụ thuộc đó theo bảo đảm đã đặc tả.

### 9.3. Hai bộ thực thi cùng nhận việc

Giành quyền xử lý có thể dùng cập nhật có điều kiện:

~~~sql
UPDATE administrative_requests
SET status = 'EXECUTING',
    execution_id = :execution_id,
    version = version + 1
WHERE id = :request_id
  AND tenant_id = :tenant_id
  AND revision = :approved_revision
  AND status = 'APPROVED'
  AND version = :expected_version
  AND expires_at > CURRENT_TIMESTAMP;
~~~

Phải kiểm tra số hàng cập nhật. Bằng 0 nghĩa là không giành được quyền bằng điều kiện này; không được cứ thế gọi cổng thanh toán.

Câu SQL chỉ minh họa chuyển trạng thái. Nó chưa kiểm tra đầy đủ quorum, quyền, chính sách, payload, phiên bản đối tượng hoặc hạn mức. Những điều kiện cần nguyên tử với việc giành quyền thực thi phải được bảo vệ cùng ranh giới phù hợp; thời gian cũng cần theo ngữ nghĩa của cơ sở dữ liệu được dùng.

Khóa trong bộ nhớ một instance không đủ khi hệ thống có nhiều instance. Việc worker bị chết sau khi giành việc cần cơ chế phục hồi; không tự trả yêu cầu về `APPROVED` rồi gọi lại hệ thống ngoài nếu chưa biết tác động lần trước.

## 10. Ví dụ hoàn tiền thủ công có phê duyệt

Một khoản thanh toán có số tiền còn được hoàn là 20.000.000 đồng. Nhân viên A đề nghị hoàn 12.000.000 đồng và nhân viên B duyệt.

Trước khi worker chạy, một luồng hoàn khác đã giữ chỗ 10.000.000 đồng. Dù đề nghị của A đã được duyệt, thực hiện thêm 12.000.000 đồng sẽ vượt hạn mức còn lại.

### 10.1. Invariant phải giữ

~~~text
refundedAmount + reservedRefundAmount <= refundableLimit
~~~

Các đại lượng phải cùng đơn vị tiền, tiền tệ và phạm vi khoản thanh toán. Quy tắc về phí, hoàn một phần hoặc điều chỉnh giới hạn phải do nghiệp vụ định nghĩa.

### 10.2. Ranh giới xử lý

Một cách tổ chức phù hợp có thể là:

1. Trong transaction nội bộ, kiểm tra yêu cầu đã được duyệt và còn hiệu lực.
2. Kiểm tra lại dữ liệu khoản thanh toán và điều kiện liên quan.
3. Giữ chỗ số tiền hoàn bằng cơ chế ngăn hai yêu cầu cùng sử dụng một hạn mức.
4. Tạo execution record và ý định gọi nhà cung cấp bằng mã tham chiếu ổn định.
5. Commit rồi chuyển tác vụ đến bộ thực thi.
6. Gọi nhà cung cấp với cơ chế chống lặp theo hợp đồng tích hợp.
7. Ghi kết quả; đối soát nếu mất phản hồi hoặc kết quả chưa rõ.

Giành quyền xử lý yêu cầu và giữ chỗ hạn mức cần một ranh giới nguyên tử hoặc cơ chế điều phối tương đương để không để lại trạng thái đã nhận việc nhưng không bảo vệ được hạn mức. Nếu thiết kế tách nhiều transaction, các trạng thái trung gian và cách phục hồi phải được mô tả rõ.

### 10.3. Khi điều kiện đã thay đổi

Có thể từ chối thực hiện, chuyển về trạng thái cần xem xét hoặc yêu cầu duyệt lại, tùy chính sách. Không tự giảm số tiền hoàn từ 12.000.000 xuống số còn lại rồi coi đó là đúng nội dung đã duyệt.

Nếu nghiệp vụ cho phép “hoàn tối đa đến một mức”, nội dung được duyệt phải thể hiện chính xác ý nghĩa đó, gồm giới hạn và cách xác định số thực tế. Không suy diễn quyền này từ một phê duyệt số tiền cố định.

## 11. Idempotency, phát lại và kết quả chưa xác định

Cần bảo vệ nhiều điểm có thể nhận yêu cầu trùng:

| Điểm vào | Rủi ro nếu xử lý lặp |
| --- | --- |
| Gửi đề nghị | Tạo nhiều yêu cầu cho cùng ý định |
| Gửi phiếu | Một người bị tính nhiều phiếu |
| Kích hoạt thực thi | Tạo nhiều execution cho cùng revision |
| Worker nhận message | Gọi tác động ngoài hệ thống nhiều lần |
| Webhook xác nhận | Cộng lại số tiền hoặc phát quyền lợi lần nữa |
| Công cụ chạy lại của quản trị | Bỏ qua trạng thái kết quả chưa biết và nhân đôi tác động |

Khóa idempotency cần có phạm vi tenant, hành động và chủ thể phù hợp. Cùng khóa nhưng khác nội dung phải được phát hiện theo hợp đồng API. Việc giành khóa phải nguyên tử và không phụ thuộc một instance.

Với tác động nghiệp vụ, thường cần thêm khóa duy nhất theo ý định hoặc nghĩa vụ được bảo vệ, chẳng hạn execution cho `(requestId, revision, action)`. Nếu mỗi retry tạo mã execution mới không liên kết với lần cũ, nhà cung cấp có thể hiểu đó là một lệnh mới.

### 11.1. Đổi khóa không được lặp lợi ích

Người có quyền có thể cố ý tạo hai đề nghị khác nhau, mỗi đề nghị đều được duyệt hợp lệ. Khóa idempotency theo từng request không đủ để ngăn hai đề nghị vượt tổng hạn mức hoặc cùng thực hiện một quyền lợi chỉ được cấp một lần.

Cần giữ invariant ở mức đối tượng nghiệp vụ và kiểm tra các đề nghị liên quan theo chính sách, gồm tổng giá trị, thời gian, đích nhận và nghĩa vụ đang được xử lý.

### 11.2. Timeout không xác định kết quả

Nếu cổng hoàn tiền đã nhận lệnh nhưng ứng dụng mất phản hồi:

- Lưu trạng thái kết quả chưa xác định.
- Giữ mã tham chiếu để truy vấn lại.
- Không giải phóng hạn mức chỉ vì client hoặc worker timeout.
- Không tạo lệnh mới với mã tham chiếu khác để “thử lại”.
- Đối soát theo hợp đồng nhà cung cấp rồi xác nhận thành công hoặc thất bại.
- Chỉ giải phóng giữ chỗ khi đã xác định an toàn.

Không thể dựa vào transaction cơ sở dữ liệu của ứng dụng để rollback một khoản hoàn đã thực hiện ở hệ thống khác. Outbox giúp lưu bền ý định gửi; relay vẫn có thể gửi lại nên bên nhận và bộ thực thi vẫn cần xử lý trùng.

## 12. Bảo vệ mọi đường quản trị

Một màn hình duyệt an toàn chưa đủ nếu còn API hoặc công cụ có thể ghi thẳng kết quả.

Các điểm vào cần đi qua quy tắc tương ứng:

- API quản trị, API nội bộ và endpoint phục vụ công cụ hỗ trợ.
- Import, batch và tác vụ định kỳ.
- Worker, webhook và lệnh chạy lại.
- Công cụ sửa dữ liệu, chức năng hỗ trợ khẩn cấp.
- Luồng thay policy, nhóm duyệt, hạn mức hoặc cấu hình.

Thiết kế nên đặt invariant và lệnh nghiệp vụ ở nơi các đường này cùng sử dụng hoặc được kiểm soát tương đương. Không dựa vào việc “chỉ nhân viên nội bộ biết endpoint”.

### 12.1. Không chấp nhận trường đặc quyền tùy ý

Request cập nhật thông thường không được gán tùy ý các trường như:

~~~json
{
  "approved": true,
  "approvedBy": "another-user",
  "requiredApprovals": 0,
  "status": "APPLIED",
  "skipApproval": true
}
~~~

Máy chủ xác định các trường trạng thái và quyết định bằng luồng nghiệp vụ. Nếu có tùy chọn quản trị làm thay đổi quy trình, bản thân tùy chọn đó phải có chính sách quyền và kiểm soát riêng; không dùng một cờ bí mật làm đường vượt.

### 12.2. Quyền trực tiếp vào cơ sở dữ liệu

Quyền ghi trực tiếp có thể vượt qua mọi kiểm tra ứng dụng. Cần giới hạn tài khoản vận hành, có quy trình thay đổi dữ liệu, khả năng truy vết và đối soát. Constraint ở cơ sở dữ liệu giúp giữ một số invariant, nhưng không biểu diễn đầy đủ mọi chính sách phê duyệt.

Thay đổi nhóm duyệt hoặc chính sách cũng là thao tác có thể nhạy cảm. Hệ thống phải ngăn vòng lặp “tự cấp quyền duyệt, duyệt yêu cầu, rồi xóa dấu vết quyền đã cấp” bằng kiểm soát thay đổi và audit phù hợp.

## 13. Ngoại lệ khẩn cấp và cơ chế break-glass

Một số hệ thống cần hành động khẩn cấp khi người duyệt hoặc dịch vụ phê duyệt không sẵn sàng. Ngoại lệ phải là một quy trình được đặc tả, không phải một nhánh “nếu lỗi thì cho qua”.

Cơ chế khẩn cấp có thể gồm:

- Danh sách rõ các hành động được phép trong chế độ khẩn cấp.
- Người đủ thẩm quyền kích hoạt và phương thức xác thực tương ứng.
- Phạm vi đối tượng, hạn mức và thời gian hiệu lực.
- Lý do bắt buộc và tham chiếu sự cố.
- Cảnh báo ngay đến người chịu trách nhiệm.
- Rà soát sau thực hiện và cách kết thúc quyền tạm thời.

Nếu không có ngoại lệ được định nghĩa, mất dịch vụ phê duyệt không được biến thành tự động chấp thuận thao tác nhạy cảm.

Break-glass có thể thay đổi yêu cầu phê duyệt theo chính sách, nhưng không được âm thầm vô hiệu mọi invariant. Ví dụ, ngoại lệ về người duyệt không mặc nhiên cho phép hoàn nhiều hơn số tiền đã thanh toán hoặc ghi sai tiền tệ.

Hậu kiểm cần phân biệt việc ghi nhận một quyết định khẩn cấp với phê duyệt trước thực hiện. Không sửa thời điểm hay lịch sử để làm một tác động đã xảy ra trông như đã được duyệt từ trước.

## 14. Audit và khả năng đối soát

Dấu vết cần nối được toàn bộ chuỗi:

~~~text
actor → request + revision → decision → execution → business outcome
~~~

| Nhóm thông tin | Dữ liệu cần cân nhắc |
| --- | --- |
| Định danh | Request, revision, execution, tenant và đối tượng |
| Chủ thể | Người yêu cầu, từng người quyết định, actor thực thi hoặc tài khoản dịch vụ |
| Quyết định | Duyệt/từ chối/rút phiếu, thời điểm, lý do và phiên bản chính sách |
| Nội dung | Tham chiếu bản nội dung bất biến, các giá trị trước/sau phù hợp |
| Tác động | Mã giao dịch ngoài hệ thống, kết quả, thời điểm và trạng thái đối soát |
| Ngoại lệ | Thu hồi, hết hạn, sửa phiên bản, break-glass và người chấp thuận |
| Tương quan | Correlation ID để nối request, worker, callback và audit event |

Không cần ghi mọi payload nhạy cảm vào log. Nên lưu dữ liệu phù hợp tại nơi có kiểm soát truy cập rồi ghi tham chiếu, che thông tin nhạy cảm và có chính sách lưu giữ.

Audit phục vụ quyết định quan trọng phải có độ bền phù hợp. Nếu chỉ ghi một dòng log sau commit, tiến trình có thể chết giữa commit và log. Có thể ghi audit record trong cùng transaction với thay đổi nội bộ rồi chuyển sang nơi lưu tập trung. Mức bảo vệ chống sửa và cách phân quyền truy cập cần theo yêu cầu của hệ thống.

Một số tín hiệu nên theo dõi:

- Cùng một chủ thể cố tự duyệt nhiều lần.
- Nhiều đề nghị nhỏ có tổng giá trị gần hoặc vượt ngưỡng phê duyệt.
- Tăng truy cập ngoài tenant hoặc ngoài phạm vi được duyệt.
- Thay payload, revision hoặc chính sách ngay trước khi thực thi.
- Nhiều lần kích hoạt lại cùng yêu cầu.
- Execution chưa xác định tồn đọng quá thời gian đối soát.
- Kích hoạt break-glass hoặc thay nhóm duyệt bất thường.

Cảnh báo giúp phát hiện vấn đề và hỗ trợ điều tra; các điều kiện bắt buộc vẫn phải được thực thi trên đường xử lý trước khi tạo tác động.

## 15. Kiểm thử tình huống lạm dụng phê duyệt

Kiểm thử nên xuất phát từ invariant, không chỉ từ việc màn hình có nút “duyệt” hay không. Mỗi ca cần quan sát phản hồi, trạng thái yêu cầu, dữ liệu nghiệp vụ và tác động ngoài hệ thống.

| Tình huống | Thao tác thử | Kết quả mong đợi |
| --- | --- | --- |
| Tự duyệt | Người tạo gửi quyết định cho yêu cầu của mình | Bị từ chối khi chính sách yêu cầu độc lập |
| Hai tài khoản cùng người | Dùng tài khoản thứ hai để tạo phiếu độc lập | Không đáp ứng yêu cầu hai người nếu nhận diện cùng chủ thể |
| Đổi tenant | Sửa tenant hoặc ID đối tượng trong request duyệt | Không ra quyết định ngoài phạm vi |
| Giả người duyệt | Gửi `approvedBy` hoặc vai trò qua body | Danh tính và quyền được xác định từ nguồn đáng tin cậy |
| Sửa sau duyệt | Đổi tiền, đối tượng hoặc đích nhận | Không dùng phê duyệt cũ cho nội dung mới |
| Mở trang rồi mất quyền | Thu hồi quyền trước khi gửi phiếu | Quyết định theo quyền hiện hành và chính sách thu hồi |
| Hết hạn | Thực thi sau thời hạn dù cron chưa cập nhật trạng thái | Bị từ chối ở ranh giới kiểm tra hiệu lực |
| Đủ phiếu sai nhóm | Hai người cùng nhóm trong quy tắc yêu cầu hai nhóm | Không đạt quorum |
| Gửi phiếu trùng | Một người gửi lại nhiều lần, kể cả đồng thời | Không tăng thêm phiếu hợp lệ |
| Hai phiếu cuối cạnh tranh | Hai người cùng hoàn tất quorum | Một chuyển trạng thái và một ý định thực thi theo thiết kế |
| Hai worker nhận việc | Cùng kích hoạt một request/revision | Không tạo thêm tác động |
| Duyệt rồi hủy | Hủy cạnh tranh với giành quyền thực thi | Kết quả theo ranh giới đã đặc tả, không mâu thuẫn |
| Đổi chính sách | Thay yêu cầu số phiếu trong khi chờ | Xử lý theo phiên bản và quy tắc chuyển đổi rõ ràng |
| Giảm hạn mức còn lại | Một luồng khác giữ chỗ trước execution | Invariant tổng hợp vẫn được giữ |
| Chia nhỏ đề nghị | Nhiều yêu cầu dưới ngưỡng cho cùng mục tiêu | Áp dụng chính sách tổng hợp nếu nghiệp vụ yêu cầu |
| Lỗi dịch vụ chính sách | Timeout trong lúc kiểm tra | Không tự chấp thuận khi chưa xác định đủ điều kiện |
| Timeout nhà cung cấp | Mất phản hồi sau khi đã nhận lệnh | Trạng thái chưa xác định, đối soát, không tạo lệnh mới tùy ý |
| Callback lặp hoặc đến trễ | Phát lại sự kiện kết quả | Không cộng tiền hoặc áp dụng tác động lần hai |
| Gọi endpoint nội bộ | Bỏ toàn bộ bước gửi và duyệt | Không vượt kiểm soát nhờ đường gọi khác |
| Break-glass sai phạm vi | Dùng quyền khẩn cấp cho thao tác ngoài chính sách | Bị từ chối và có dấu vết phù hợp |

### 15.1. Chứng minh kiểm soát cạnh tranh

Để thử race condition, cần điều khiển các luồng cùng đến điểm kiểm tra hoặc cập nhật liên quan. Gửi hai request tuần tự nhanh không chứng minh chúng cạnh tranh thực sự.

Với hoàn tiền, cần xác nhận tổng `refundedAmount + reservedRefundAmount` sau khi các luồng kết thúc. Với duyệt nhiều người, kiểm tra số phiếu hợp lệ, số lần chuyển trạng thái, execution record và tác động thực tế.

### 15.2. Thử lỗi tại các ranh giới

Các điểm lỗi hữu ích gồm:

1. Sau khi lưu phiếu nhưng trước khi transaction commit.
2. Sau khi commit trạng thái được duyệt nhưng trước khi phát message.
3. Sau khi worker giành việc nhưng trước khi gọi nhà cung cấp.
4. Sau khi nhà cung cấp tạo tác động nhưng trước khi lưu kết quả.
5. Sau khi lưu kết quả nhưng trước khi xác nhận xử lý message.

Hành vi phục hồi phải đúng với từng ranh giới. Ví dụ, việc phát lại message sau bước 5 có thể đọc kết quả đã lưu; lỗi ở bước 4 cần đối soát chứ không thể suy ra thất bại.

Các ca trong mục này là hướng dẫn xây dựng kiểm thử cho hệ thống. Một báo cáo chỉ kiểm tra mã HTTP chưa đủ chứng minh quy trình phê duyệt giữ được quy tắc nghiệp vụ.

## 16. Những thiết kế dễ tạo cảm giác an toàn giả

| Thiết kế có vấn đề | Vì sao có thể bị lạm dụng | Hướng xử lý |
| --- | --- | --- |
| Chỉ ẩn nút duyệt | Có thể gọi API trực tiếp | Kiểm tra actor, quyền và state machine phía máy chủ |
| Một cờ `approved` trên bản ghi mutable | Có thể sửa nội dung sau khi duyệt | Nội dung bất biến, revision và phiếu gắn đúng phiên bản |
| Tin quyền từ giao diện | Quyền hoặc đối tượng có thể đã thay đổi | Kiểm tra khi nhận lệnh và ở ranh giới thực thi cần thiết |
| Đếm số hàng phiếu duyệt | Phiếu trùng, sai nhóm hoặc mất hiệu lực vẫn có thể bị tính | Tính quorum theo chính sách trên các phiếu hợp lệ |
| Chỉ kiểm tra `requesterId != approverId` | Hai tài khoản có thể thuộc một người | Mô hình chủ thể và tính độc lập phù hợp yêu cầu |
| Worker có quyền cao nên bỏ validation | Tác vụ cũ hoặc dữ liệu giả có thể được thực hiện | Kiểm tra ủy quyền cụ thể và invariant của đối tượng |
| Bấm duyệt là thực thi ngay nhiều lần | Retry hoặc race nhân đôi tác động | Giành quyền nguyên tử và idempotency theo ý định nghiệp vụ |
| Lưu khóa chống trùng sau khi gọi xong | Hai luồng cùng tạo tác động trước khi thấy khóa | Giành quyền bền vững trước và xử lý trạng thái trung gian |
| Timeout thì giải phóng giữ chỗ | Tác động có thể đã xảy ra ngoài hệ thống | Kết quả chưa xác định và đối soát trước khi giải phóng |
| Mất dịch vụ phê duyệt thì cho qua | Lỗi phụ thuộc tạo đường vượt chính sách | Dừng hành động hoặc dùng ngoại lệ được đặc tả |
| Một người tự sửa policy rồi tự duyệt | Cơ chế kiểm soát tự bị vô hiệu | Kiểm soát độc lập việc thay policy và quyền |
| Chỉ ghi log sau thực hiện | Có thể thiếu dấu vết nếu tiến trình chết | Ghi audit bền vững theo ranh giới cần bảo đảm |

## 17. Checklist thiết kế quy trình phê duyệt quản trị

- [ ] Đã liệt kê các thao tác nhạy cảm và invariant cần giữ.
- [ ] Chính sách chọn theo dữ liệu có thẩm quyền, có phiên bản và phạm vi.
- [ ] Quyền tạo, duyệt, thực thi, hủy và thay policy được phân định.
- [ ] Độc lập giữa người yêu cầu và người duyệt được kiểm tra đúng mô hình chủ thể.
- [ ] Nội dung người duyệt nhìn thấy khớp nội dung được khóa để thực thi.
- [ ] Phiếu gắn với revision, đối tượng, tenant, hành động và dữ liệu quan trọng.
- [ ] Chỉnh sửa sau gửi duyệt làm mất hiệu lực quyết định theo quy tắc rõ ràng.
- [ ] State machine ngăn nhảy bước và sửa trực tiếp trạng thái đặc quyền.
- [ ] Hiệu lực thời gian, thay đổi quyền và thu hồi có ranh giới xác định.
- [ ] Quorum và giành quyền thực thi được bảo vệ trước cạnh tranh.
- [ ] Invariant tổng hợp được kiểm tra lại ở thời điểm cần thiết.
- [ ] Retry, message trùng và callback trễ không tạo tác động thêm.
- [ ] Timeout ngoài hệ thống có trạng thái chưa xác định và cách đối soát.
- [ ] Các đường quản trị khác chịu kiểm soát tương đương.
- [ ] Ngoại lệ khẩn cấp có phạm vi, thời hạn, audit và người chịu trách nhiệm.
- [ ] Audit nối được yêu cầu, quyết định, execution và kết quả nghiệp vụ.
- [ ] Kiểm thử bao gồm sai quyền, sửa nội dung, race condition và lỗi giữa chừng.

Phê duyệt quản trị bảo vệ nghiệp vụ khi quyết định của con người được chuyển thành một ủy quyền cụ thể mà máy chủ thực thi đúng phạm vi. Mỗi bước từ đề nghị đến tác động cuối phải giữ được mối liên hệ giữa người có thẩm quyền, nội dung đã duyệt và các điều kiện còn hợp lệ.
