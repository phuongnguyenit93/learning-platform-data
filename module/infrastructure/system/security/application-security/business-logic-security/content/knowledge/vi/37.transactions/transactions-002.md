# Thực thi quy tắc nghiệp vụ một cách nguyên tử

## 1. Atomic rule enforcement là gì?

Một quy tắc nghiệp vụ chỉ có giá trị bảo vệ khi không thể bị phá vỡ bởi lỗi giữa chừng, request đồng thời hoặc đường cập nhật khác. Việc viết một câu `if` đúng chưa đủ nếu dữ liệu có thể thay đổi giữa lúc kiểm tra và lúc tạo tác động.

**Atomic rule enforcement là thiết kế để việc kiểm tra điều kiện và những thay đổi thực thi quy tắc tạo thành một bước chuyển hợp lệ, không để giao dịch khác chen vào làm quyết định trở nên sai.** Nếu không thể thực hiện trọn vẹn bước chuyển, các thay đổi chưa commit liên quan phải bị hủy.

Trong Business Logic Security, các quy tắc cần bảo vệ có thể là:

- Không hoàn quá số tiền đã thu.
- Một yêu cầu đã phê duyệt chỉ được thực hiện một lần.
- Chỉ chủ thể có quyền trên đúng đối tượng mới được thay đổi nó.
- Không thanh toán đơn chưa được phê duyệt hoặc tự sửa số tiền đã chốt.
- Số dư, sổ cái và trạng thái nghiệp vụ phải phản ánh cùng một tác động.

Chủ đề Transactions giúp người học xác định ranh giới ghi nhận các thay đổi đó. Tuy nhiên, transaction không tự suy ra quy tắc nghiệp vụ và cũng không mặc nhiên ngăn mọi cuộc đua đồng thời. Cần kết hợp điều kiện cập nhật, khóa hoặc kiểm soát phiên bản, mức cô lập phù hợp và ràng buộc dữ liệu.

## 2. Kịch bản: hai yêu cầu hợp lệ riêng lẻ làm hoàn tiền quá mức

Một payment đã thu 1.000.000 đồng và đã hoàn 700.000 đồng. Hạn mức còn được hoàn là 300.000 đồng.

Hai yêu cầu hoàn tiền khác nhau, mỗi yêu cầu 250.000 đồng, được gửi gần như đồng thời. Kẻ tấn công có thể chủ động tạo lịch gửi này; hệ thống cũng có thể gặp nó do hai nhân viên hoặc hai worker cùng làm việc.

| Thời điểm | Request A | Request B |
|---|---|---|
| T1 | Đọc đã hoàn 700.000 đồng | |
| T2 | | Đọc đã hoàn 700.000 đồng |
| T3 | Kiểm tra 700.000 + 250.000 không vượt 1.000.000: đạt | |
| T4 | | Kiểm tra tương tự: đạt |
| T5 | Tạo khoản hoàn và cộng ví 250.000 đồng | |
| T6 | | Tạo khoản hoàn và cộng ví 250.000 đồng |

Tổng tiền thực sự đã hoàn thành 1.200.000 đồng. Từng request có thể vượt qua kiểm tra đăng nhập, dữ liệu đầu vào và cả kiểm tra hạn mức trước đó, nhưng kết quả chung vẫn sai.

Nếu hai request cùng tăng bộ đếm bằng phép cộng, bộ đếm có thể lên 1.200.000 đồng. Nếu mỗi request ghi đè giá trị đã tính sẵn là 950.000 đồng, bộ đếm có thể chỉ còn 950.000 đồng trong khi sổ cái và số dư đã ghi nhận hai khoản hoàn. Trường hợp sau còn che giấu sai lệch thay vì loại bỏ nó.

Đưa từng request vào một transaction không tự sửa lịch thực thi này. Cần bảo vệ chính điều kiện “còn đủ hạn mức” khi cập nhật dữ liệu có cạnh tranh.

## 3. Viết invariant trước khi chọn cơ chế

Giả sử ví khách hàng, payment, yêu cầu hoàn tiền, khoản hoàn và sổ cái cùng nằm trong một cơ sở dữ liệu. Ví dụ này thực hiện hoàn tiền nội bộ đồng bộ; chưa có lời gọi cổng thanh toán bên ngoài.

Các invariant chính:

```text
0 <= payment.refunded_minor <= payment.captured_minor

payment.refunded_minor
    = tổng các khoản hoàn thành công thuộc payment

Mỗi approved_refund_request chỉ có tối đa một lần thực thi thành công.

Mỗi khoản hoàn thành công có đúng tác động sổ cái tương ứng.

Biến động ví phải khớp những bút toán đã được ghi nhận.
```

Ngoài invariant dữ liệu còn có điều kiện chuyển trạng thái:

```text
APPROVED -> EXECUTED

Chỉ được chuyển khi:
  - actor có quyền trên đúng tenant, payment và yêu cầu hoàn tiền;
  - yêu cầu thuộc đúng payment;
  - số tiền và tiền tệ khớp quyết định phê duyệt;
  - còn đủ hạn mức hoàn tiền;
  - ví thụ hưởng được lấy từ liên kết nghiệp vụ tin cậy.
```

Số tiền dùng kiểu biểu diễn chính xác, chẳng hạn đơn vị nhỏ nhất của tiền tệ với giới hạn rõ ràng. Không dùng số thực có sai số để bảo vệ hạn mức tiền. Các giá trị định danh và số tiền quan trọng cần quy tắc không rỗng; không để `NULL` khiến điều kiện được hiểu khác dự kiến.

Việc liệt kê invariant giúp phân biệt ba bài toán: dữ liệu nào phải luôn đúng, ai được phép tạo thay đổi và những thay đổi nào phải commit cùng nhau.

## 4. Atomicity và isolation có vai trò khác nhau

| Cơ chế hoặc tính chất | Điều được bảo vệ | Điều chưa tự được bảo vệ |
|---|---|---|
| Atomicity của transaction | Các thay đổi trong cùng transaction cùng commit hoặc cùng rollback | Điều kiện đã đọc có còn đúng khi transaction khác cập nhật hay không |
| Isolation | Kiểm soát ảnh hưởng và tương tác giữa các transaction đồng thời | Quy tắc nghiệp vụ nếu ứng dụng không biểu diễn nó đúng |
| Unique constraint | Không tồn tại hai bản ghi trùng định danh được ràng buộc | Hạn mức tổng hoặc quyền trên đối tượng |
| Check constraint | Điều kiện dữ liệu mà cơ sở dữ liệu có thể kiểm tra trực tiếp | Mọi quy tắc tổng hợp xuyên bảng hoặc tác động bên ngoài |
| Cập nhật có điều kiện | Gắn điều kiện với chính lần cập nhật có cạnh tranh | Những thay đổi khác nếu chúng không cùng transaction |
| Khóa hoặc version check | Phối hợp truy cập và phát hiện quyết định dựa trên dữ liệu cũ | Các writer không tuân thủ giao thức bảo vệ |
| Idempotency | Liên kết retry với cùng một ý định | Các yêu cầu khác nhau cạnh tranh cùng hạn mức |

Atomicity xử lý lỗi nửa chừng. Isolation và giao thức truy cập xử lý việc xen kẽ. Muốn thực thi quy tắc nguyên tử cần hiểu cả hai.

Mức cô lập thấp hơn serializable vẫn có thể hỗ trợ thiết kế đúng nếu ứng dụng dùng cập nhật có điều kiện, khóa và ràng buộc phù hợp. Ngược lại, chọn một mức cô lập cao không sửa được việc thiếu kiểm tra quyền hoặc gọi một hệ thống ngoài nằm ngoài transaction.

## 5. Cách thứ nhất: gắn điều kiện với câu lệnh cập nhật

Thay vì đọc hạn mức rồi ghi một giá trị đã tính ở ứng dụng, có thể yêu cầu cơ sở dữ liệu cập nhật chỉ khi điều kiện vẫn đúng tại điểm cập nhật.

SQL minh họa sau dùng tham số bind. Cú pháp cụ thể và hành vi xung đột phải được hiện thực theo cơ sở dữ liệu đang sử dụng:

```sql
UPDATE payment
SET refunded_minor = refunded_minor + :amount_minor,
    version = version + 1
WHERE id = :payment_id
  AND tenant_id = :tenant_id
  AND state = 'CAPTURED'
  AND currency = :currency
  AND :amount_minor > 0
  AND :amount_minor <= captured_minor - refunded_minor;
```

Tiền đề của ví dụ là `captured_minor` và `refunded_minor` không rỗng, không âm, đã có ràng buộc `refunded_minor <= captured_minor`, đồng thời nằm trong miền giá trị số được hỗ trợ. Số tiền được xác thực và lấy theo yêu cầu đã phê duyệt, không phải một giá trị tùy ý của client.

Ứng dụng phải kiểm tra số dòng cập nhật:

- Đúng một dòng: đã giành được hạn mức cho thao tác trong transaction hiện tại, còn phải hoàn thành các thay đổi liên quan.
- Không có dòng: không được coi thao tác thành công; có thể là thiếu quyền trong phạm vi truy vấn, sai trạng thái, không khớp tiền tệ hoặc không đủ hạn mức.
- Lỗi cạnh tranh hoặc transaction bị hủy: rollback và xử lý theo chính sách retry phù hợp.

Với hai request cùng tăng 250.000 đồng, không được để cả hai commit một trạng thái vượt hạn mức. Tùy cơ chế của cơ sở dữ liệu và mức cô lập, request sau sẽ đánh giá điều kiện trên dữ liệu đã được phối hợp cập nhật hoặc nhận lỗi xung đột cần retry. Ứng dụng phải xử lý các kết quả này, không giả định một phép đọc cũ còn hiệu lực.

Nếu sau khi cập nhật bộ đếm mà việc ghi refund hoặc cộng ví thất bại, toàn bộ transaction phải rollback. Một câu `UPDATE` nguyên tử chưa đủ nếu phần còn lại được commit riêng rẽ.

Không trả lỗi quá chi tiết cho người không có quyền để tránh làm lộ sự tồn tại hoặc trạng thái của payment. Có thể phân loại nguyên nhân sâu hơn bằng kiểm tra được phép và log nội bộ, nhưng không được thực thi lại tác động chỉ để tìm nguyên nhân.

## 6. Cách thứ hai: khóa bản ghi điều phối rồi kiểm tra

Khi quyết định phụ thuộc nhiều trường hoặc nhiều bảng, có thể khóa một bản ghi điều phối ổn định, chẳng hạn payment, rồi đọc và cập nhật trong cùng transaction:

```text
BEGIN TRANSACTION

payment = loadPaymentForUpdate(tenantId, paymentId)
refundRequest = loadRefundRequestForUpdate(tenantId, refundRequestId)

requireCurrentObjectPermission(actor, payment, refundRequest)
requireRequestBelongsToPayment(refundRequest, payment)
require(refundRequest.state == APPROVED)
require(refundRequest.amount <= payment.remainingRefundableAmount)

applyRefundAndAllRelatedChanges()

COMMIT
```

Đây là mã giả; `loadForUpdate` biểu thị cơ chế khóa tương ứng tại cơ sở dữ liệu, không phải một API chuẩn.

Điều kiện quan trọng là mọi writer tác động tới cùng hạn mức phải cùng tuân thủ giao thức điều phối. Nếu đường API khóa payment nhưng batch job khác ghi refund trực tiếp mà không khóa hoặc kiểm tra tương đương, invariant vẫn có thể bị phá.

Không đọc dữ liệu quyết định từ replica chậm rồi chỉ khóa khi ghi kết quả. Các giá trị liên quan phải được đọc lại trong ngữ cảnh transaction được bảo vệ và có tính nhất quán phù hợp.

### 6.1. Khóa một hàng không tự khóa mọi điều kiện

Nếu kiểm tra “chưa có refund nào” bằng một truy vấn trả về không có hàng, không được mặc định đã khóa được sự vắng mặt đó. Một transaction khác có thể insert sau bước kiểm tra, tùy mức cô lập và cơ chế khóa.

Các lựa chọn gồm ràng buộc duy nhất cho định danh nghiệp vụ, khóa một hàng cha luôn tồn tại, cơ chế khóa phạm vi phù hợp hoặc serializable với xử lý retry. Cần chọn theo quy tắc thực tế, không chỉ thêm khóa vào một truy vấn bất kỳ.

### 6.2. Thứ tự khóa và thời gian giữ khóa

Quy định một thứ tự thống nhất cho các luồng tương tác, ví dụ payment trước yêu cầu hoàn tiền, sau đó đến ví; nếu có nhiều ví thì khóa theo thứ tự định danh ổn định. Mọi đường ghi liên quan cần tuân thủ cùng thứ tự phù hợp.

Giữ transaction ngắn. Không chờ người dùng phê duyệt hoặc gọi mạng chậm trong lúc giữ khóa rồi cho rằng khóa sẽ giải quyết mọi vấn đề. Deadlock vẫn có thể xảy ra; ứng dụng cần rollback và retry có giới hạn thay vì bỏ qua lỗi.

## 7. Cách thứ ba: kiểm soát phiên bản lạc quan

Nếu đã đọc một đối tượng có `version = 12`, ứng dụng có thể yêu cầu cập nhật chỉ khi phiên bản vẫn là 12:

```sql
UPDATE payment
SET refunded_minor = :new_refunded_minor,
    version = version + 1
WHERE id = :payment_id
  AND tenant_id = :tenant_id
  AND version = :expected_version;
```

Ví dụ này chỉ minh họa điều kiện phiên bản. Trước đó vẫn phải kiểm tra invariant từ dữ liệu nhất quán; có thể bổ sung điều kiện dữ liệu hoặc ràng buộc cơ sở dữ liệu thích hợp. Không được suy ra rằng version match tự chứng minh số tiền được phép hoàn.

Nếu số dòng cập nhật bằng không, không được tiếp tục commit refund đã tạo dựa trên phiên bản cũ. Phải rollback toàn bộ thay đổi của lần thử và quyết định đọc lại, tính lại hoặc trả xung đột.

Cơ chế này chỉ bảo vệ những thay đổi thực sự được theo dõi bởi version. Nếu thay đổi quyết định phê duyệt hoặc hạn mức ở một bảng khác mà không tham gia giao thức phiên bản hoặc khóa, version của payment có thể không phát hiện dữ liệu liên quan đã đổi.

Không giải quyết xung đột bằng cách thay `expected_version` thành giá trị mới rồi ghi nguyên quyết định cũ. Một lần thử mới phải đánh giá lại điều kiện nghiệp vụ trên dữ liệu mới.

## 8. Ràng buộc dữ liệu là lớp bảo vệ cuối cùng

Những ràng buộc minh họa có thể gồm:

```sql
-- Các cột tiền liên quan còn cần NOT NULL và miền giá trị phù hợp.
CHECK (captured_minor >= 0)
CHECK (refunded_minor >= 0 AND refunded_minor <= captured_minor)

-- Chỉ một lần thực thi thành công cho một yêu cầu đã phê duyệt.
UNIQUE (tenant_id, refund_request_id)

-- Chỉ một bút toán cho cùng tác động hoàn tiền.
UNIQUE (refund_id, ledger_effect_type)
```

Các dòng trên là các ràng buộc trên những bảng tương ứng, không phải một đoạn DDL hoàn chỉnh đặt chung lên một bảng. Đơn vị uniqueness phải phản ánh đúng sản phẩm. Nếu có bản ghi lần thử thất bại, cần tách nó khỏi bản ghi thực thi thành công hoặc thiết kế uniqueness phù hợp với vòng đời đó.

`CHECK` trên payment có thể ngăn bộ đếm vượt tiền đã thu, nhưng không tự chứng minh bộ đếm bằng tổng refund ở bảng khác. Việc đồng bộ tổng, sổ cái và số dư vẫn cần transaction cùng giao thức ghi đúng.

Ràng buộc cũng không thay quyền theo đối tượng. Một khoản hoàn chỉ được thực hiện một lần vẫn có thể là khoản hoàn trái quyền nếu backend lấy `tenant_id`, ví thụ hưởng hoặc quyết định phê duyệt từ dữ liệu client mà không kiểm chứng.

Mỗi ràng buộc cần được đặt ở đúng nơi lưu dữ liệu có thẩm quyền. Một tập ID trong cache không tương đương với unique constraint bền vững cho tiền đã được ghi nhận.

## 9. Luồng hoàn tiền nguyên tử đầy đủ

Ví dụ sau kết hợp điều phối bằng khóa payment, chuyển trạng thái có điều kiện, bảo vệ hạn mức, idempotency và ràng buộc dữ liệu. Đây là một thiết kế minh họa cho tác động nội bộ trong cùng cơ sở dữ liệu, không phải yêu cầu mọi hệ thống phải dùng tất cả cơ chế theo đúng cách này.

```text
actor = authenticate(request)
command = parseAndValidateSchema(request)
scope = trustedScope(actor, "refund.execute.v1")
digest = fingerprint(command)

result = inDatabaseTransaction:
    idem = reserveOrFindIdempotencyAtomically(scope, command.key, digest)

    if idem refers to a completed existing operation:
        requireSameIntent(idem, digest)
        requireCurrentPermissionToReceiveResult(actor, idem.target)
        return savedResult(idem)

    payment = loadPaymentForUpdate(trustedTenant(actor), command.paymentId)
    approval = loadRefundRequestForUpdate(trustedTenant(actor), command.refundRequestId)

    requireCurrentExecutionPermission(actor, payment, approval)
    require(approval.paymentId == payment.id)
    require(approval.currency == payment.currency)
    requireClientIntentMatchesApprovedRequest(command, approval)

    amount = approval.approvedAmountMinor
    walletId = trustedCustomerWalletFor(payment)

    changedRequest = markApprovedRequestExecutedConditionally(approval)
    requireExactlyOneRow(changedRequest)

    changedBudget = consumeRefundBudgetConditionally(payment, amount)
    requireExactlyOneRow(changedBudget)

    refund = insertSuccessfulRefundWithBusinessUniqueness(approval, payment, amount)
    ledger = insertRefundCreditLedger(refund, walletId, amount)
    requireExactlyOneWalletUpdatedAtomically(walletId, amount)

    appendBusinessAudit(actor, approval, refund, ledger)
    appendOutboxWithStableEventIdentity(refund)

    receipt = buildStableReceipt(refund)
    saveCompletedIdempotencyResult(idem, receipt)
    return receipt

# Chỉ trả thành công sau khi biết transaction đã commit.
return result
```

Nhánh idempotency đang xử lý hoặc chưa rõ kết quả, nếu mô hình có các trạng thái đó, phải được phân giải theo hợp đồng riêng; không được mặc định là quyền thực thi mới. Trong mô hình một transaction đồng bộ, bản ghi đăng ký và kết quả thường chỉ cùng xuất hiện bền vững sau commit.

Mọi hàm trong khối transaction phải thật sự dùng cùng phạm vi transaction như thiết kế. Việc ghi audit, sổ cái hoặc số dư qua connection độc lập tự commit có thể phá vỡ bảo đảm dù mã nguồn nằm trong cùng một khối hàm service.

Nếu `changedBudget` bằng không, thay đổi trạng thái yêu cầu ở bước trước cũng phải rollback. Nếu cộng ví thất bại, refund, sổ cái, hạn mức, audit nghiệp vụ và kết quả thành công chưa commit phải rollback cùng nhau. Không đánh dấu idempotency thành công để che một lỗi giữa chừng.

Đối với lỗi nghiệp vụ muốn lưu như một kết quả từ chối ổn định, cần thiết kế nhánh ghi riêng rõ ràng, không commit những cập nhật dở dang của nhánh thành công. Log vận hành cho một lần thử thất bại có thể có chính sách khác với audit của một khoản hoàn đã thực hiện.

## 10. Quyền và phê duyệt cũng có thể bị TOCTOU

TOCTOU là khoảng cách giữa thời điểm kiểm tra một điều kiện và thời điểm sử dụng kết quả kiểm tra đó. Nó không chỉ xảy ra với số dư.

Ví dụ:

1. Service đọc yêu cầu hoàn tiền đang ở trạng thái `APPROVED`.
2. Một người có quyền thu hồi phê duyệt.
3. Service vẫn dùng dữ liệu cũ để thực hiện hoàn tiền.

Nếu chính sách yêu cầu phê duyệt còn hiệu lực tại bước chuyển sang thực thi, đường thu hồi và đường thực thi phải phối hợp qua cùng khóa, version hoặc cập nhật có điều kiện. Khi hai transaction cạnh tranh, hệ thống phải có một thứ tự hợp lệ: hoặc thu hồi xảy ra trước và thực thi bị từ chối, hoặc thực thi đã được chốt trước và việc thu hồi phải xử lý theo trạng thái mới.

Tương tự, điều kiện sở hữu hoặc tenant cần được kiểm tra trong phạm vi dữ liệu được bảo vệ, có thể thông qua điều kiện trong câu lệnh ghi hoặc đọc lại đối tượng đã khóa. Chỉ kiểm tra quyền trên một DTO đọc từ lâu rồi ghi bằng `id` không có phạm vi tenant là không đủ.

Với quyền nằm trong hệ thống IAM bên ngoài, transaction cơ sở dữ liệu nội bộ không tự đồng bộ được mọi thay đổi quyền theo thời gian thực. Cần xác định chính sách rõ ràng: quyền được đánh giá tại thời điểm nào, phiên bản hoặc thời hạn quyết định quyền là gì và thao tác nhạy cảm cần cơ chế xác nhận nào. Không tuyên bố thu hồi có hiệu lực tức thì tại commit nếu hệ thống không có cơ chế phối hợp tương ứng.

Idempotency replay có quy tắc riêng: vẫn kiểm tra người gọi hiện tại có được nhận kết quả, nhưng không yêu cầu thao tác đã hoàn tất phải quay về trạng thái trước thực thi để được replay. Quyền truy cập kết quả và điều kiện thực thi mới là hai trách nhiệm cần phân biệt.

## 11. Quy tắc trên nhiều hàng và giới hạn của snapshot

Một số điều kiện không nằm trên một bản ghi. Ví dụ, chính sách yêu cầu có ít nhất hai phê duyệt hợp lệ từ hai người khác nhau và người yêu cầu không được tự tính là người phê duyệt.

Chạy `COUNT` trong transaction rồi thực thi không tự bảo vệ tập phê duyệt. Một transaction khác có thể thu hồi hoặc sửa các phê duyệt trong lúc quyết định đang được dùng, tùy mức cô lập và giao thức ghi.

Các cách thiết kế có thể gồm:

- Khóa một bản ghi yêu cầu làm điểm điều phối; mọi thêm, thu hồi và thực thi phê duyệt phải dùng cùng giao thức.
- Dùng phiên bản của tập quyết định và bảo đảm mọi thay đổi liên quan đều cập nhật phiên bản đó.
- Dùng mức cô lập serializable cùng việc retry toàn bộ transaction khi phát hiện xung đột.
- Ghi nhận một quyết định phê duyệt bất biến và thực thi theo đúng phiên bản đã chốt, nếu đó là chính sách nghiệp vụ được chọn.

Một snapshot nhất quán cho phép đọc một trạng thái nhất quán tại một thời điểm, nhưng không luôn ngăn các transaction đồng thời ghi những hàng khác nhau rồi làm sai invariant tổng hợp. Đây là lý do phải xem quy tắc trên toàn bộ tập dữ liệu liên quan, không chỉ nhìn transaction có đọc bẩn hay không.

Serializable giúp giao dịch đã commit có kết quả tương đương một thứ tự tuần tự trong phạm vi nó bảo vệ. Nó vẫn cần mã kiểm tra đúng invariant, đúng đối tượng và đúng ranh giới transaction; ứng dụng cũng phải xử lý các lần bị hủy do cạnh tranh.

## 12. Retry và kết quả commit chưa xác định

Một cơ chế bảo vệ đúng có thể từ chối hoặc hủy transaction trong lúc cạnh tranh. Đây là kết quả cần được xử lý, không phải lý do bỏ kiểm tra để request luôn thành công.

Khi retry do deadlock, serialization failure hoặc xung đột phiên bản:

1. Rollback lần thử thất bại theo cơ chế của cơ sở dữ liệu.
2. Bắt đầu một transaction mới, đọc lại dữ liệu và đánh giá lại toàn bộ điều kiện cần thiết.
3. Giữ nguyên định danh ý định nghiệp vụ hoặc idempotency key của thao tác đang phân giải.
4. Giới hạn số lần thử và có khoảng chờ phù hợp khi tranh chấp cao.
5. Không phát tác động ngoài transaction trong mỗi lần thử rồi hy vọng rollback sẽ thu hồi được.

Không chỉ retry câu lệnh cuối cùng nếu những quyết định trước đó dựa trên dữ liệu cũ. Không tạo idempotency key mới sau mỗi lỗi mạng, vì như vậy có thể biến một thao tác chưa rõ kết quả thành nhiều ý định độc lập.

Nếu mất kết nối khi commit, service có thể chưa biết transaction đã thành công hay chưa. Cần tra cứu bằng mã nghiệp vụ hoặc gửi lại cùng key để lấy kết quả. Không mặc định thất bại rồi cộng ví lại; cũng không mặc định thành công khi chưa có bằng chứng.

Idempotency ngăn cùng ý định bị lặp. Ràng buộc theo `refund_request_id` và hạn mức payment tiếp tục bảo vệ khi kẻ tấn công đổi key hoặc gửi nhiều yêu cầu khác nhau.

## 13. Transaction nội bộ không bao trùm hệ thống bên ngoài

Nếu hoàn tiền qua cổng thanh toán, việc gọi HTTP trong một khối transaction không làm cho nhà cung cấp tham gia rollback của cơ sở dữ liệu nội bộ.

Một lịch lỗi nguy hiểm:

1. Nhà cung cấp hoàn tiền thành công.
2. Service lỗi trước khi commit dữ liệu nội bộ.
3. Transaction rollback, nhưng khoản hoàn tiền bên ngoài vẫn tồn tại.
4. Retry gửi thêm một lệnh hoàn tiền mới.

Thiết kế thường cần tạo một thao tác và giữ hạn mức hoàn tiền trong transaction nội bộ, ghi công việc outbox cùng transaction, rồi worker thực hiện lời gọi ngoài với định danh ổn định. Những thao tác đang chờ phải chiếm phần hạn mức phù hợp để các yêu cầu khác không cùng tiêu lại phần đó.

Khi hoàn tất, trạng thái giữ hạn mức và trạng thái hoàn tiền được chuyển theo điều kiện đã thiết kế. Chỉ giải phóng giữ chỗ khi có bằng chứng phù hợp rằng tác động không xảy ra hoặc đã được xử lý bù; timeout không chứng minh thất bại.

Outbox giúp công việc được ghi cùng dữ liệu nội bộ, nhưng có thể được giao lại. Phía nhận cần idempotency hoặc cơ chế tương đương nếu được hỗ trợ; hệ thống cần tra cứu và đối soát khi kết quả chưa rõ. Hoàn tác nghiệp vụ là một thao tác mới có thể thất bại, không phải rollback vật lý của việc đã xảy ra bên ngoài.

Tương tự, gửi email ngay sau commit vẫn có khoảng lỗi giữa commit và gửi. Nếu việc gửi là một trách nhiệm phải phục hồi được, ghi công việc bền vững như outbox rồi xử lý tiếp, thay vì chỉ dựa vào một callback trong tiến trình.

## 14. Ma trận kiểm thử thực thi quy tắc nguyên tử

Kiểm thử nên quan sát trạng thái dữ liệu cuối cùng và các tác động, không chỉ kiểm tra response. Những lịch đồng thời và điểm dừng phải được chủ động tạo để nhìn thấy lỗi mà kiểm thử tuần tự thường bỏ sót.

| Tình huống | Kết quả cần khẳng định |
|---|---|
| Một yêu cầu hợp lệ, đủ hạn mức | Refund, sổ cái, ví, tổng hoàn và trạng thái yêu cầu cùng khớp |
| Hai yêu cầu 250.000 đồng cùng dùng hạn mức còn 300.000 đồng | Tối đa một yêu cầu được thực hiện; không hoàn quá tiền đã thu |
| Hai request thực hiện cùng yêu cầu phê duyệt bằng key khác nhau | Chỉ một lần thực thi thành công cho yêu cầu đó |
| Retry cùng key sau khi mất response thành công | Trả kết quả đã có, không thêm refund hoặc cộng ví |
| Sửa số tiền hoặc ví thụ hưởng trong request | Không vượt quyết định phê duyệt và liên kết phía server |
| Nhân viên tenant A gửi ID của tenant B | Không tác động dữ liệu của tenant B |
| Thu hồi phê duyệt cạnh tranh với thực thi | Có thứ tự hợp lệ theo chính sách; không thực thi dựa trên trạng thái đã bị vô hiệu trước bước chốt |
| Lỗi sau khi tăng tổng hoàn nhưng trước ghi sổ cái | Các thay đổi chưa commit rollback, không tiêu hạn mức dở dang |
| Lỗi sau ghi sổ cái nhưng trước cộng ví | Không commit một khoản hoàn thiếu tác động ví tương ứng |
| Cập nhật ví không khớp dòng nào | Không trả thành công; toàn bộ thao tác chưa commit bị hủy |
| Xung đột phiên bản | Không commit các thay đổi dựa trên quyết định cũ |
| Deadlock hoặc transaction bị hủy do cô lập | Retry đầy đủ có giới hạn, không lặp tác động |
| Mất kết nối lúc commit | Phân giải bằng cùng định danh, không đoán thất bại rồi thực thi mới |
| API và batch job cùng cập nhật payment | Cả hai tuân thủ cơ chế bảo vệ invariant |
| Hai transaction sửa các phê duyệt khác nhau | Quy tắc trên tập phê duyệt vẫn đúng khi thực thi |
| Worker ngoài hệ thống timeout sau khi bên nhận đã thực hiện | Không giải phóng hạn mức và phát lệnh mới tùy tiện |

Với ví dụ hạn mức, cần đối chiếu ít nhất ba nguồn: tổng refund thành công, tổng bút toán hoàn tiền và biến động ví. Đồng thời kiểm tra bộ đếm trên payment bằng đúng tổng theo mô hình dữ liệu. Một bộ đếm không vượt trần chưa đủ chứng minh không có khoản cộng ví dư ở nơi khác.

Đây là các tình huống để thiết kế kiểm thử nghiệp vụ. Việc triển khai kiểm thử phải dùng những cơ chế transaction và cạnh tranh thật sự tương ứng với hệ thống cần bảo vệ.

## 15. Dấu hiệu thiết kế cần xem lại

Các dấu hiệu dễ dẫn đến lỗ hổng gồm đọc điều kiện ở đầu request rồi ghi không có điều kiện; chỉ khóa trong một instance; bỏ qua số dòng bị cập nhật; tiếp tục sau lỗi ràng buộc; hoặc kiểm tra quyền trên dữ liệu đọc từ trước transaction.

Một dấu hiệu khác là coi transaction chỉ như nơi chứa các câu lệnh ghi mà không liệt kê writer cạnh tranh. API, webhook, worker, batch, công cụ vận hành và luồng sửa dữ liệu đều có thể tác động cùng invariant. Đường ghi ít gặp vẫn có thể là đường bỏ qua phê duyệt, sửa giá hoặc tiêu hạn mức hai lần.

Khi xem một thao tác nhạy cảm, hãy xác định điểm quyết định được bảo vệ, những dữ liệu tạo nên điều kiện, các thay đổi phải commit cùng nhau và cách những writer khác bị buộc tuân thủ. Nếu chưa xác định được các điểm này, một khai báo transaction trong mã nguồn chưa đủ chứng minh quy tắc được thực thi nguyên tử.

## 16. Câu hỏi tự kiểm tra

1. Vì sao mỗi request đều có transaction nhưng tổng tiền hoàn vẫn có thể vượt số tiền đã thu?
2. Cập nhật có điều kiện bảo vệ điều gì mà kiểm tra `if` trước đó không bảo vệ được?
3. Vì sao số dòng cập nhật bằng không phải ngăn nhánh thành công tiếp tục commit?
4. Một check constraint trên payment có chứng minh số dư và sổ cái khớp nhau không?
5. Khi một tập phê duyệt thay đổi, version của đối tượng nào thực sự bảo vệ quyết định thực thi?
6. Vì sao timeout khi commit hoặc gọi cổng thanh toán không chứng minh tác động chưa xảy ra?
7. Nếu một batch job bỏ qua giao thức khóa của API, invariant còn được bảo vệ bằng gì?

Một thao tác nghiệp vụ an toàn cần giữ cùng lúc ba cam kết: chỉ người được phép mới tạo được thay đổi, điều kiện vẫn đúng tại bước chuyển được bảo vệ và mọi dữ liệu phản ánh tác động được chốt nhất quán. Transaction là nền tảng để thực hiện các cam kết đó khi ranh giới dữ liệu, cạnh tranh và cơ chế phục hồi đã được thiết kế rõ ràng.
