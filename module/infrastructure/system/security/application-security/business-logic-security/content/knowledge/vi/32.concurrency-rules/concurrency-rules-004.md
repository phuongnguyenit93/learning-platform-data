# Pessimistic lock decision

## 1. Quyết định khóa phải bắt đầu từ bất biến

Hai request đều hợp lệ khi chạy riêng vẫn có thể tạo ra kết quả trái nghiệp vụ khi chạy đồng thời. Người dùng hoặc một chương trình tự động có thể khai thác khoảng thời gian giữa kiểm tra và ghi để vượt hạn mức, duyệt hai lần hoặc chuyển trạng thái không hợp lệ.

**Pessimistic lock decision** là quyết định có dùng khóa bi quan cho một thao tác hay không, và nếu dùng thì khóa tài nguyên nào, trong transaction nào, giữ bao lâu và xử lý tranh chấp ra sao. Mục tiêu là làm cho những thao tác cạnh tranh phải tuân theo một thứ tự đủ để giữ bất biến nghiệp vụ.

Khóa bi quan thường giành quyền truy cập có xung đột trước khi hoàn tất chuỗi đọc–kiểm tra–ghi. Khác với kiểm tra phiên bản để phát hiện xung đột khi cập nhật, nó có thể khiến thao tác khác phải chờ hoặc bị từ chối ngay khi lấy khóa. Cách này hữu ích khi cần quyết định trên trạng thái được bảo vệ, nhưng cũng tạo chi phí chờ, nguy cơ deadlock và điểm nghẽn có thể bị lạm dụng.

Không nên quyết định bằng câu “đây là chức năng quan trọng nên thêm lock”. Cần chỉ ra được:

- Bất biến nào sẽ sai nếu hai thao tác xen kẽ?
- Dữ liệu nào quyết định bất biến và những đường ghi nào có thể thay đổi nó?
- Có thể dùng ràng buộc database hoặc một lệnh cập nhật có điều kiện đơn giản hơn không?
- Nếu phải chờ khóa, hệ thống có thể đáp ứng thời gian phản hồi và giới hạn tài nguyên không?

Trong bài, ví dụ chính là phê duyệt phiếu chi trong ngân sách. Các tên bảng, lớp và trạng thái là mô hình minh họa cho bảo vệ logic nghiệp vụ; chúng không giả định một database hay framework duy nhất cho toàn ứng dụng.

## 2. Một race condition làm vượt ngân sách

Giả sử ngân sách còn 1.000 đơn vị tiền nhỏ nhất. Có hai phiếu đang chờ: A yêu cầu 700 và B yêu cầu 500. Mỗi phiếu chỉ được duyệt một lần; tổng số tiền đã duyệt không được vượt hạn mức. Người duyệt cũng phải có quyền với dự án và không được tự duyệt phiếu của mình.

Một implementation không đủ an toàn có thể làm:

```text
đọc ngân sách còn lại
đọc phiếu đang chờ
kiểm tra quyền, trạng thái và số tiền
nếu đủ điều kiện:
    duyệt phiếu
    ghi phần ngân sách đã sử dụng
```

Khi hai transaction chạy đồng thời:

| Thời điểm | Transaction T1: duyệt A | Transaction T2: duyệt B |
|---|---|---|
| 1 | Đọc còn 1.000 | |
| 2 | | Đọc còn 1.000 |
| 3 | Kết luận đủ cho 700 | |
| 4 | | Kết luận đủ cho 500 |
| 5 | Ghi A đã duyệt | |
| 6 | | Ghi B đã duyệt |
| 7 | Commit nếu không có kiểm soát bổ sung | Commit nếu không có kiểm soát bổ sung |

Tổng cam kết trở thành 1.200. Tùy cách cập nhật counter, hệ thống còn có thể bị mất cập nhật, khiến số dư nhìn vẫn không âm trong khi các phiếu đã duyệt vượt ngân sách. Một `CHECK (remaining_amount >= 0)` không tự kiểm tra tổng tác dụng nếu ứng dụng ghi đè số dư từ dữ liệu đã đọc cũ.

Khóa riêng từng phiếu chưa giải quyết được: A và B là hai dòng khác nhau nên cả hai vẫn có thể được khóa độc lập. Tài nguyên cạnh tranh ở đây là **ngân sách chung**, bên cạnh trạng thái của từng phiếu.

Nếu mọi thao tác làm thay đổi khả năng chi cùng phối hợp trên một dòng ngân sách, T2 phải đợi T1 giải quyết. Sau khi T1 commit, T2 đánh giá trên phần còn lại là 300 và từ chối B. Nếu T1 rollback, T2 có thể được đánh giá trên ngân sách chưa bị tiêu thụ.

Khóa không thay kiểm tra quyền: một người không có quyền duyệt phải bị từ chối dù họ lấy được khóa trước. Khóa cũng không hợp thức hóa số tiền do client sửa; số tiền dùng để xét ngân sách phải lấy từ phiên bản phiếu mà server kiểm soát.

## 3. So sánh các lựa chọn trước khi dùng khóa bi quan

### 3.1. Chọn theo hình dạng bất biến

| Nhu cầu | Lựa chọn cần xem xét | Điều vẫn phải bảo đảm |
|---|---|---|
| Không tạo hai bản ghi cho cùng khóa nghiệp vụ | Unique constraint | Khóa có đúng tenant và miền nghiệp vụ; xử lý xung đột an toàn |
| Một dòng không được có số lượng âm | Cập nhật có điều kiện và constraint phù hợp | Kiểm tra số dòng bị ảnh hưởng; toàn bộ tác dụng liên quan cùng transaction |
| Người sửa phải dựa trên đúng phiên bản đã xem | Optimistic locking hoặc compare-and-set | Mọi đường cập nhật có liên quan tham gia cơ chế phiên bản |
| Quyết định ngắn cần đọc nhiều thuộc tính ổn định của một aggregate | Khóa bi quan trên phạm vi phối hợp thích hợp | Khóa trước khi đọc dữ liệu quyết định, kiểm tra lại sau chờ |
| Bất biến theo tập dữ liệu thay đổi khó gom vào một điểm phối hợp | Thiết kế lại aggregate, ràng buộc chuyên biệt hoặc serializable | Phân tích toàn bộ transaction và retry khi bị hủy do xung đột |
| Quy trình kéo dài qua mạng, người dùng hoặc dịch vụ ngoài | Reservation, state machine và idempotency | Không giữ transaction database để chờ toàn bộ quy trình |

Các lựa chọn có thể kết hợp. Khóa ngân sách không thay unique constraint của quyết định phê duyệt; một unique constraint cũng không tự giữ tổng ngân sách giữa các phiếu khác nhau.

### 3.2. Khi một cập nhật có điều kiện đã đủ

Nếu bất biến cốt lõi chỉ là trừ một số tiền dương khỏi số dư có sẵn, có thể dùng một lệnh như sau:

```sql
UPDATE budget
SET remaining_amount = remaining_amount - :amount
WHERE tenant_id = :tenant_id
  AND id = :budget_id
  AND remaining_amount >= :amount;
```

Đây là placeholder minh họa; implementation thực dùng prepared statement hoặc cơ chế bind tương ứng. `amount` phải dương, đúng đơn vị, trong giới hạn kiểu dữ liệu và được lấy từ ý định nghiệp vụ đã được server kiểm tra. Không nhận số âm để biến thao tác trừ thành cộng.

Ứng dụng phải kiểm tra số dòng cập nhật. Không cập nhật được không có nghĩa được tiếp tục duyệt phiếu. Ngược lại, cập nhật được một dòng cũng chưa cho phép commit nếu trạng thái phiếu hoặc quyền duyệt không hợp lệ; các thay đổi phải cùng transaction để có thể rollback.

Một lệnh `UPDATE` vẫn có thể lấy khóa và phải chờ ở database. Lựa chọn ở đây là có cần một bước đọc rồi khóa tường minh cho quyết định phức tạp hay không, không phải “có khóa” đối lập với “không có bất kỳ khóa nào”.

### 3.3. Khi optimistic locking phù hợp hơn

Nếu xung đột hiếm và người dùng đang chỉnh một đối tượng độc lập, kiểm tra `version` thường cho phép nhiều người đọc mà không chờ nhau. Khi version thay đổi, hệ thống trả xung đột để người dùng hoặc service đánh giá lại.

Tuy nhiên, đặt version riêng trên phiếu A và B không phát hiện việc cả hai cùng vượt ngân sách. Nếu dùng optimistic locking cho ví dụ này, cần có điểm kiểm tra phiên bản chung của ngân sách hoặc một cơ chế khác bảo vệ bất biến tổng hợp. Version phải gắn với dữ liệu quyết định, không chỉ có mặt ở một entity bất kỳ.

Không tự retry vô hạn một lệnh người dùng dựa trên dữ liệu cũ. Sau xung đột, ý định “duyệt đúng số tiền và phiên bản tôi đã xem” có thể không còn đúng; cần giữ điều kiện phiên bản hoặc yêu cầu đánh giá lại.

## 4. Khi nào khóa bi quan là lựa chọn có cơ sở?

Khóa bi quan đáng cân nhắc khi đồng thời có các điều kiện sau:

1. Có thể xác định một tập tài nguyên phối hợp nhỏ, chẳng hạn ngân sách theo dự án và kỳ.
2. Quyết định phụ thuộc vào trạng thái hiện hành mà nhiều thao tác có thể cùng thay đổi.
3. Thao tác trong vùng bảo vệ ngắn, không chờ người dùng hoặc dịch vụ ngoài có thời gian khó dự đoán.
4. Các đường ghi cạnh tranh có thể cùng tuân theo một giao thức khóa hoặc được chặn bằng cơ chế tương đương.
5. Hệ thống có giới hạn chờ, xử lý lỗi và khả năng quan sát tranh chấp.

Một mức xung đột cao không tự chứng minh cần thêm khóa. Nó có thể cho thấy thiết kế có một điểm nóng mà việc xếp hàng chỉ làm lộ giới hạn throughput. Đôi khi phải chia miền ngân sách, đặt trước hạn mức hoặc thay cách xử lý thay vì cho nhiều request đứng chờ trên cùng dòng.

Không nên giữ khóa trong lúc:

- Gọi cổng thanh toán hoặc gửi email.
- Tải tệp, quét virus hoặc tạo báo cáo lớn.
- Chờ người duyệt xác nhận trên giao diện.
- Chờ sleep/backoff cho một lần retry.
- Thực hiện phép tính tốn thời gian không cần dữ liệu đang được bảo vệ.

Nếu cần chống chi trùng trong một quy trình dài, có thể commit một reservation hoặc lệnh đã chốt rồi tiếp tục bằng state machine. Thời hạn reservation, việc giải phóng và idempotency ở tác dụng cuối là những quy tắc cần thiết kế riêng; giữ một database lock lâu không thay thế được chúng.

## 5. Xác định tài nguyên khóa và giao thức chung

### 5.1. Khóa theo miền cạnh tranh nhỏ nhất đủ giữ bất biến

Với ví dụ phê duyệt chi phí, khóa ngân sách theo `(tenant, project, period)` thường phù hợp hơn một khóa toàn hệ thống. Các dự án độc lập vẫn có thể xử lý song song, nhưng mọi phiếu cạnh tranh cùng hạn mức phải gặp cùng điểm phối hợp.

Dòng ngân sách đóng vai trò **guard row**: một tài nguyên tồn tại ổn định đại diện cho bất biến của một tập bản ghi. Khóa nó chỉ có tác dụng phối hợp nếu các thao tác khác cũng tuân theo giao thức. Dòng con có foreign key đến ngân sách không tự bảo đảm mọi insert hoặc thay đổi nghiệp vụ sẽ lấy đúng loại khóa cần thiết.

Các đường cần được rà vào cùng giao thức bao gồm duyệt phiếu, hủy quyết định duyệt, điều chỉnh hạn mức, chuyển ngân sách, import, worker và công cụ quản trị. Chỉ một endpoint dùng khóa trong khi một job nền cập nhật ledger trực tiếp vẫn có thể làm bất biến sai.

### 5.2. Đọc và kiểm tra trong đúng vùng được bảo vệ

Thứ tự cơ bản là:

```text
bắt đầu transaction
  lấy các khóa cần thiết theo thứ tự chung
  đọc hoặc làm mới trạng thái được bảo vệ
  kiểm tra tenant, quyền, phiên bản và state machine
  kiểm tra bất biến nghiệp vụ
  ghi thay đổi, kết quả chống trùng và outbox bắt buộc
commit
trả kết quả thành công
```

Đọc số dư ở ngoài transaction rồi chỉ lấy khóa ngay trước lệnh ghi không làm số dư đã đọc trở nên mới. Tương tự, một entity đã nằm trong cache của persistence context có thể cần được tải/làm mới theo hợp đồng của framework; không giả định thêm lock ở đâu đó sẽ thay mọi giá trị mà code đang giữ.

Ở mức triển khai PostgreSQL, row lock có thể chặn writer và các yêu cầu khóa xung đột, nhưng không ngăn mọi truy vấn đọc thông thường. Thời gian giữ khóa gắn với transaction, với các quy tắc riêng cho rollback tới savepoint. [PostgreSQL: Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html)

Do đó, `SELECT FOR UPDATE` chạy trong một transaction ngắn đã kết thúc trước khi service kiểm tra và ghi là chưa đủ. Dữ liệu quyết định và tác dụng cần nằm trong cùng ranh giới transaction có hiệu lực.

### 5.3. Một thứ tự khóa thống nhất

Nếu có nhiều ngân sách hoặc phiếu, cần một thứ tự khóa rõ ràng, chẳng hạn theo loại tài nguyên rồi khóa định danh chuẩn hóa. Các đường chuyển tiền/hạn mức phải dùng cùng thứ tự kể cả khi chiều chuyển ngược nhau.

Không dựa vào thứ tự phần tử client gửi trong `IN (...)` để kết luận database sẽ lấy khóa theo thứ tự đó. Với tập nhỏ đã biết, có thể khóa từng định danh đã sắp theo thứ tự quy định; với truy vấn tập hợp, cần hiểu execution plan và ngữ nghĩa khóa của database để giữ hợp đồng.

Thứ tự tường minh làm giảm vòng chờ nhưng không cho phép tuyên bố hết mọi deadlock: unique index, foreign key, trigger, flush của ORM và những cập nhật ngầm khác cũng có thể tham gia. Giao thức cần tính cả khóa tường minh lẫn tác dụng ngầm có liên quan.

## 6. Minh họa SQL: khóa rồi đánh giá trạng thái

Ví dụ sau dùng cú pháp PostgreSQL với placeholder để diễn giải. Nó giả định mỗi phiếu thuộc một ngân sách đã tồn tại, số tiền dùng số nguyên theo đơn vị tiền nhỏ nhất, và một phiếu chỉ có một quyết định duyệt cuối cùng trong vòng đời minh họa.

### 6.1. Khóa ngân sách trước, phiếu sau

Hai truy vấn nằm trong cùng transaction của service:

```sql
SELECT id, tenant_id, remaining_amount, state
FROM budget
WHERE tenant_id = :tenant_id
  AND id = :budget_id
FOR UPDATE;

SELECT id, tenant_id, budget_id, amount, state, version, requested_by
FROM expense_request
WHERE tenant_id = :tenant_id
  AND id = :request_id
FOR UPDATE;
```

`budget_id` phải được xác định từ quan hệ tin cậy của phiếu, không phải một ngân sách tùy ý do client gửi để đánh lạc hướng khóa. Nếu cần đọc trước để biết ngân sách nào phải khóa, dữ liệu đọc trước chỉ là gợi ý định tuyến; sau khi lấy khóa, phải xác nhận phiếu vẫn thuộc ngân sách đó và đúng phiên bản yêu cầu.

Nếu nghiệp vụ cho phép chuyển phiếu giữa các ngân sách, đường chuyển phải có cùng giao thức khóa. Khi quan hệ thay đổi so với gợi ý ban đầu, không tiếp tục dùng khóa sai ngân sách. Có thể rollback và thử lại có giới hạn bằng quan hệ mới, hoặc trả xung đột để caller đánh giá lại.

Sau khi có dữ liệu được bảo vệ, service kiểm tra tenant, quyền duyệt, tách người duyệt, trạng thái `PENDING`, phiên bản được kỳ vọng, số tiền dương, ngân sách còn hiệu lực và số dư đủ dùng. Những điều kiện này phải lấy từ dữ liệu đã xác nhận, không từ bản sao cũ của client.

### 6.2. Ghi thay đổi với kiểm tra phòng vệ

Ngay cả khi đã khóa, có thể giữ điều kiện trong lệnh ghi để làm rõ cam kết:

```sql
UPDATE budget
SET remaining_amount = remaining_amount - :approved_amount
WHERE tenant_id = :tenant_id
  AND id = :budget_id
  AND state = 'OPEN'
  AND remaining_amount >= :approved_amount;

UPDATE expense_request
SET state = 'APPROVED',
    approved_by = :approver_id,
    version = version + 1
WHERE tenant_id = :tenant_id
  AND id = :request_id
  AND budget_id = :budget_id
  AND state = 'PENDING'
  AND version = :expected_version;
```

Mỗi lệnh phải có đúng số dòng cập nhật mà hợp đồng yêu cầu. Nếu cập nhật ngân sách thành công nhưng cập nhật phiếu không đúng một dòng, phải rollback cả transaction; không giữ phần đã trừ rồi trả lỗi như thể chưa có tác dụng.

Ledger quyết định, kết quả idempotency và sự kiện outbox bắt buộc được ghi cùng transaction. Có thể thêm unique constraint theo `(tenant_id, request_id)` cho quyết định duyệt trong mô hình mỗi phiếu chỉ được duyệt một lần này. Nếu nghiệp vụ có nhiều vòng duyệt, khóa cần thêm vòng/phiên bản quyết định tương ứng, không dùng constraint sai miền.

Khóa bảo vệ trạng thái trong lúc đánh giá, còn predicate và constraint phòng vệ trước lỗi đường ghi hoặc sai giả định. Chúng bổ sung cho nhau nhưng không cho phép bỏ qua việc phân tích đường cạnh tranh.

### 6.3. Sau khi chờ phải chấp nhận kết quả khác dự kiến

Ở PostgreSQL `READ COMMITTED`, thao tác khóa có thể đợi rồi trả về phiên bản đã được transaction trước cập nhật. Với các mức isolation khác, cùng một tình huống có thể dẫn tới lỗi cần retry. [PostgreSQL: Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html)

Service phải kiểm tra dữ liệu thực nhận được hoặc xử lý lỗi isolation; không tiếp tục với kết luận “còn đủ tiền” trước lúc chờ. Nếu phiếu đã được duyệt hoặc bị hủy trong thời gian chờ, kết quả phù hợp là replay có kiểm soát hoặc xung đột/trạng thái không hợp lệ, không phải duyệt thêm lần nữa.

## 7. Mã giả Java và lưu ý khi dùng ORM

### 7.1. Transaction phải bao trọn quyết định

Đoạn sau là mã giả Java để minh họa hợp đồng, không phải một service hoàn chỉnh. `tx.required` chỉ trả kết quả ra ngoài sau khi transaction commit thành công.

```java
public ApprovalReply approve(
        VerifiedContext context,
        ApproveCommand command) {

    ValidatedApproval input = commands.validate(command);
    RoutingHint hint = requests.findTrustedRoutingHint(
            context.tenantId(), input.requestId());

    return tx.required(() -> {
        Budget budget = budgets.lockInTenant(
                context.tenantId(), hint.budgetId());
        ExpenseRequest request = requests.lockInTenant(
                context.tenantId(), input.requestId());

        if (!request.belongsTo(budget)) {
            return ApprovalReply.routingConflict();
        }

        authorization.requireCanUseApprovalCommand(
                context, budget, request);

        IdempotencySlot slot = idempotency.reserveOrLock(
                context.tenantId(), context.subjectId(),
                "APPROVE_EXPENSE", input.idempotencyKey());
        String fingerprint = fingerprints.ofApprovalIntent(input);

        if (slot.hasResult()) {
            slot.requireSameFingerprint(fingerprint);
            return slot.authorizedResultFor(context);
        }

        ApprovalDecision decision = rules.evaluate(
                context, budget, request,
                input.expectedVersion(), clock.instant());

        if (!decision.allowed()) {
            ApprovalReply denied = ApprovalReply.denied(
                    decision.publicReason());
            slot.complete(fingerprint, denied);
            outbox.append(events.approvalDenied(
                    context, request, decision));
            return denied;
        }

        budget.reserveApprovedAmount(request.amount());
        request.approve(context.subjectId());
        approvals.insertConfirmedDecision(request, decision);

        ApprovalReply approved = ApprovalReply.approved(
                request.id(), request.version());
        slot.complete(fingerprint, approved);
        outbox.append(events.expenseApproved(context, request));

        return approved;
    });
}
```

Các hợp đồng quan trọng của ví dụ:

- Context chứa danh tính và tenant đã xác thực; request không được tự khai quyền hoặc approver có thẩm quyền.
- `lockInTenant` lấy khóa database thật trong transaction hiện tại và cung cấp trạng thái cần thiết đã được làm mới. Không triển khai nó bằng một truy vấn đọc không khóa.
- `RoutingHint` không thay kiểm tra quan hệ sau khóa. Không gọi một API trả chi tiết ngoài quyền chỉ để tìm ngân sách.
- Các đường phê duyệt, hủy và điều chỉnh ngân sách tuân cùng thứ tự: ngân sách, phiếu, rồi bản ghi idempotency trong mô hình này. Một thiết kế khác được phép nhưng phải nhất quán giữa các đường cạnh tranh.
- `rules.evaluate` kiểm tra số tiền, trạng thái, phiên bản, quyền theo đối tượng và điều kiện không tự duyệt. Điều kiện phân quyền có thể thay đổi cần cơ chế phối hợp riêng như phần sau trình bày.
- Bản ghi idempotency có unique constraint đúng phạm vi và xử lý được cạnh tranh khi chưa tồn tại. Fingerprint gồm hành động, request ID, expected version và các lựa chọn có ý nghĩa.
- Ví dụ lưu cả kết quả từ chối nghiệp vụ đã xác nhận. Retry cùng khóa trả lại quyết định đó; muốn tạo một ý định đánh giá mới sau khi sửa dữ liệu, caller phải dùng hợp đồng tạo lệnh mới, không sửa payload dưới khóa cũ.
- Các thay đổi entity, ledger, idempotency và outbox phải commit cùng tài nguyên transaction. Nếu commit lỗi, không được trả `approved` chỉ vì đối tượng kết quả đã được dựng trong bộ nhớ.

Một exception phân quyền làm rollback transaction không thể đồng thời được giả định là đã lưu audit deny trong chính transaction đó. Ví dụ giữ nhánh từ chối nghiệp vụ dưới dạng kết quả; các nhánh exception và lỗi trước vùng này cần cơ chế audit phù hợp riêng.

### 7.2. Dùng Jakarta Persistence không miễn kiểm tra SQL thực tế

Trong một transaction đang có hiệu lực, truy vấn khóa theo tenant có thể được biểu diễn như sau:

```java
Budget budget = entityManager.createQuery(
        "select b from Budget b " +
        "where b.tenantId = :tenantId and b.id = :id",
        Budget.class)
    .setParameter("tenantId", tenantId)
    .setParameter("id", budgetId)
    .setLockMode(LockModeType.PESSIMISTIC_WRITE)
    .getSingleResult();
```

Đây là phần repository minh họa, cần entity mapping và transaction phù hợp. Không suy rằng khóa entity ngân sách sẽ khóa mọi entity liên quan được ORM tải. Cần xác định các dòng phải bảo vệ và kiểm tra SQL cùng hành vi trên provider/database sử dụng.

Jakarta Persistence cung cấp các chế độ khóa bi quan, nhưng timeout cấu hình qua `jakarta.persistence.lock.timeout` là hint, không phải một cam kết khả chuyển trên mọi provider và database. [Jakarta EE Tutorial: Locking](https://jakarta.ee/learn/jakartaee-tutorial/current/persist/persistence-locking/persistence-locking.html)

Một annotation hoặc phương thức tên `findForUpdate` không đủ chứng minh transaction thực sự bao trọn kiểm tra và ghi. Cần xác minh ranh giới service, connection, cách flush và vòng đời persistence context; đặc biệt tránh trả entity ra ngoài vùng khóa rồi mới ra quyết định.

## 8. Những bất biến không được bảo vệ chỉ bằng khóa dòng đã tìm thấy

### 8.1. Không có dòng không có nghĩa đã khóa được sự vắng mặt

Giả sử ứng dụng kiểm tra chưa có quyết định duyệt, rồi insert quyết định mới. Một truy vấn row lock không tìm được dòng không tự biến khóa nghiệp vụ chưa tồn tại thành một tài nguyên bị độc quyền. Với PostgreSQL, không thể dựa vào `SELECT ... FOR UPDATE` trả rỗng để ngăn transaction khác insert dòng phù hợp.

Nếu yêu cầu là không trùng quyết định, unique constraint đúng miền là lớp bảo vệ trực tiếp. Nếu cần phối hợp nhiều dữ kiện trước khi insert, có thể khóa một guard row đã tồn tại hoặc chọn cơ chế isolation/thiết kế khác phù hợp. Nếu guard row được tạo theo nhu cầu, việc khởi tạo nó cũng phải an toàn bằng ràng buộc và xử lý cạnh tranh.

### 8.2. Khóa từng dòng khác với khóa một điều kiện tổng hợp

Các bất biến như “nhóm luôn còn ít nhất một người có quyền duyệt” hoặc “không quá N reservation đang hoạt động” phụ thuộc vào cả tập dữ liệu. Hai transaction khóa hai dòng khác nhau có thể cùng thỏa kiểm tra trên snapshot của mình rồi làm sai bất biến sau khi commit.

Không giả định thêm `FOR UPDATE` vào một truy vấn `COUNT` hoặc `SUM` sẽ tạo một khóa đại diện cho điều kiện tổng. Cần xác định tài nguyên phối hợp thật, thiết kế lại counter/reservation hoặc dùng một mức isolation có cam kết phù hợp và xử lý lỗi của nó.

Một guard row chỉ là một giao thức ứng dụng. Writer không lấy guard vẫn có thể phá quy tắc nếu không có bảo vệ bổ sung ở database hoặc quyền ghi. Ngay cả khi đã khóa mọi dòng hiện có trong tập, cần phân tích insert mới, chuyển trạng thái và chuyển đối tượng vào/ra tập.

### 8.3. Snapshot ổn định không đồng nghĩa bất biến tự đúng

Đọc lặp lại cùng giá trị có thể giúp hiểu một snapshot, nhưng không tự làm mọi quyết định dựa trên nhiều dòng an toàn. Lựa chọn isolation và khóa phải được đánh giá cùng nhau; không dùng tên `REPEATABLE READ` làm bằng chứng rằng các transaction cạnh tranh đã được tuần tự hóa theo yêu cầu nghiệp vụ.

Nếu chọn `SERIALIZABLE`, phải hiểu phạm vi database bảo đảm, bảo đảm các transaction liên quan dùng giao thức phù hợp và sẵn sàng retry toàn transaction bị hủy. Điều đó vẫn không đưa một lời gọi thanh toán bên ngoài vào transaction, cũng không bỏ được kiểm tra quyền hoặc ý định phiên bản của người dùng.

## 9. Khóa, quyền, idempotency và tác dụng ngoài database

### 9.1. Giữ dữ liệu ổn định không có nghĩa giữ quyền ổn định

Khóa ngân sách không tự khóa bảng thành viên dự án, phiên bản chính sách hoặc dữ liệu của dịch vụ phân quyền bên ngoài. Người dùng có thể đủ quyền khi bắt đầu chờ nhưng bị thu hồi trước khi đến lượt thao tác.

Cần kiểm tra lại quyền tại điểm quyết định. Nếu chính sách yêu cầu thu hồi quyền phải được phối hợp chặt với commit, các thay đổi quyền cũng phải tham gia cơ chế thích hợp: guard cho phạm vi ủy quyền, version check có hiệu lực trong cùng giao thức hoặc một mandate nghiệp vụ rõ ràng. Chỉ gọi lại dịch vụ quyền một lần trước lệnh ghi không loại bỏ toàn bộ khoảng trống cạnh tranh với một lần thu hồi tiếp theo.

Trước khi lấy khóa đắt đỏ, nên kiểm tra xác thực, quyền chức năng và ngữ cảnh tenant để chặn yêu cầu rõ ràng không hợp lệ. Sau khi có dữ liệu được bảo vệ, vẫn kiểm tra quyền theo đối tượng và điều kiện hiện hành. Hai bước giúp giảm lạm dụng tài nguyên mà không dựa vào dữ liệu cũ làm quyết định cuối.

### 9.2. Khóa tuần tự hóa không tự chống tác dụng lặp

Nếu hai request giống nhau lần lượt lấy được khóa, cả hai vẫn có thể tạo tác dụng nếu state machine cho phép một hành động lặp và không có khóa nghiệp vụ chống trùng. Idempotency bảo vệ việc retry cùng ý định; khóa bảo vệ các thao tác cùng truy cập dữ liệu trong khoảng thời gian nhất định.

Với ví dụ, trạng thái `PENDING -> APPROVED`, unique decision và kết quả idempotency cùng ngăn duyệt lặp theo các miền khác nhau. Không gộp mọi request của một người thành một lệnh chỉ vì chúng dùng chung tenant hoặc ngân sách.

Replay không được bỏ qua quyền đọc kết quả hiện tại. Cùng idempotency key nhưng payload khác phải trả conflict, không áp dụng payload mới sau khi chờ khóa.

### 9.3. Không giữ database lock để chờ tác dụng từ xa

Sau khi duyệt, ứng dụng có thể ghi lệnh chi trả vào outbox trong cùng transaction rồi để worker thực hiện. Khi đó, “đã duyệt” và “đã chi trả” là hai trạng thái khác nhau. Không thông báo đã thanh toán chỉ vì ngân sách được giữ và event đã ghi.

Worker ở đích cần idempotency hoặc một giao thức chống chi trùng tương ứng. Nếu mất ACK sau commit hoặc sau lời gọi từ xa, phải đối soát bằng định danh gốc; timeout không chứng minh tác dụng chưa xảy ra.

`synchronized` hoặc một mutex trong JVM chỉ phối hợp những luồng cùng chia sẻ mutex đó. Nó không tự bảo vệ request chạy ở JVM khác, worker khác hay script quản trị. Khóa phân tán cũng cần phân tích lease, mất kết nối và fencing; chuyển sang một công cụ khóa khác không làm mất các câu hỏi về phạm vi bảo vệ.

## 10. Quyết định hành vi khi không lấy được khóa

### 10.1. Chờ, từ chối ngay và bỏ qua là ba hợp đồng khác nhau

| Lựa chọn | Ý nghĩa với caller | Trường hợp phù hợp và giới hạn |
|---|---|---|
| Chờ có giới hạn | Có thể đến lượt rồi được đánh giá trên trạng thái mới | Hành động tương tác ngắn, còn đủ ngân sách thời gian |
| Không chờ khóa dòng | Trả trạng thái bận/xung đột để caller xử lý | Khi phản hồi nhanh quan trọng hơn xếp hàng tại database |
| Bỏ qua dòng đang khóa | Chọn công việc khác có thể lấy được | Hàng đợi nhiều worker, nếu nghiệp vụ cho phép bỏ qua tạm thời |

Trong PostgreSQL, `NOWAIT` báo lỗi khi không thể lấy row lock ngay, còn `SKIP LOCKED` bỏ qua các dòng không lấy được khóa. Chúng không bảo đảm mọi loại khóa liên quan đều không phải chờ; `SKIP LOCKED` cũng không cung cấp một ảnh đầy đủ của tập dữ liệu. [PostgreSQL: SELECT locking clause](https://www.postgresql.org/docs/current/sql-select.html)

Vì vậy, không dùng `SKIP LOCKED` để kết luận “không còn phiếu cần duyệt”, “không có ngân sách” hoặc “người dùng không có quyền” khi dòng chỉ đang bận. Với một lệnh duyệt phiếu cụ thể, bỏ qua phiếu đó có thể làm sai ngữ nghĩa phản hồi. Với worker lấy một job bất kỳ, nó có thể phù hợp nếu có cơ chế quay lại xử lý phần bị bỏ qua và kiểm soát việc chờ quá lâu của một mục tiêu.

Nếu dùng chế độ chờ, cần phân biệt thời gian lấy connection, chờ khóa, chạy statement và tổng thời gian request. Cấu hình một lock timeout không tự giới hạn mọi công đoạn. Ngân sách retry cũng phải nằm trong tổng thời gian được phép, không phải mỗi lần thử lại có thêm một khoảng chờ không giới hạn.

### 10.2. Deadlock cần được dự kiến ngay từ thiết kế

Một vòng chờ đơn giản:

```text
T1 giữ khóa ngân sách X, chờ ngân sách Y.
T2 giữ khóa ngân sách Y, chờ ngân sách X.
```

Trong PostgreSQL, hệ thống phát hiện deadlock và hủy một transaction tham gia; ứng dụng không nên dựa vào việc transaction cụ thể nào sẽ bị chọn. [PostgreSQL: Deadlocks](https://www.postgresql.org/docs/current/explicit-locking.html#LOCKING-DEADLOCKS)

Ứng dụng cần chuyển lỗi thành kết quả an toàn hoặc retry có kiểm soát. Không coi deadlock là một từ chối nghiệp vụ như hết ngân sách. Cũng không ghi “đã duyệt” chỉ vì lệnh cập nhật từng chạy trước khi transaction bị hủy.

Thứ tự khóa nhất quán, chọn đúng mức khóa cần ngay từ đầu và thu ngắn vùng giữ khóa giúp giảm rủi ro. Một đường chỉ đọc rồi nâng khóa trong khi đường khác làm tương tự có thể tạo tranh chấp nâng cấp; cần xem các mode thực tế và SQL mà ORM phát sinh thay vì chỉ đếm số truy vấn.

### 10.3. Lỗi khóa không phải lúc nào cũng có cùng hậu quả transaction

Jakarta Persistence phân biệt `PessimisticLockException` cho trường hợp lỗi khóa dẫn đến rollback transaction với `LockTimeoutException` khi lỗi chỉ rollback statement. Mapping cụ thể còn phải được kiểm chứng trên provider/database và ranh giới transaction của ứng dụng. [Jakarta Persistence: EntityManager](https://jakarta.ee/specifications/platform/11/apidocs/jakarta/persistence/EntityManager.html)

Không catch mọi lỗi khóa rồi tiếp tục ghi như thể transaction luôn khỏe. Một transaction có thể đã bị đánh dấu rollback-only, hoặc framework có chính sách rollback bổ sung. Ngược lại, cũng không dựa vào tên “timeout” để khẳng định chưa có tác dụng ở một dịch vụ từ xa đã gọi trước đó.

Với một quyết định nghiệp vụ ngắn, chính sách dễ lý giải thường là kết thúc lần transaction gặp lỗi và, nếu lỗi được phân loại là có thể thử lại, bắt đầu một transaction mới cho toàn quyết định. Nếu muốn phục hồi ở mức statement/savepoint, cần một hợp đồng riêng đã được kiểm chứng; không áp dụng tùy tiện trong catch block.

### 10.4. Retry toàn quyết định, giữ nguyên ý định

Một vòng retry phù hợp cần:

1. Chỉ retry loại lỗi cạnh tranh/hạ tầng đã được phân loại, không retry tự động các lỗi thiếu quyền hoặc trạng thái không hợp lệ.
2. Kết thúc transaction trước, giải phóng tài nguyên rồi mới backoff; không sleep trong lúc đang giữ khóa.
3. Bắt đầu transaction mới, lấy lại khóa và đọc lại dữ liệu quyết định.
4. Giữ cùng idempotency key và các điều kiện của ý định gốc, bao gồm expected version khi đó là yêu cầu nghiệp vụ.
5. Giới hạn số lần, tổng thời gian và tốc độ retry; thêm jitter phù hợp để tránh nhiều request cùng dồn lại.

Nếu transaction trước chắc chắn rollback do deadlock, một lần thử mới có thể đánh giá lại. Nếu kết nối mất ở thời điểm commit và kết cục chưa rõ, phải đối soát kết quả theo định danh gốc bằng nguồn đọc phù hợp. Không đổi key chỉ để “thử lại cho sạch”.

Đọc kết quả từ một replica trễ có thể trả chưa thấy dù transaction đã commit ở nguồn chính. Khi chưa xác định được, hệ thống cần phản ánh đang xác minh hoặc dùng quy trình idempotent có bảo vệ tương ứng, thay vì kết luận thất bại rồi tạo thêm tác dụng.

## 11. Đánh giá chi phí chờ và khả năng bị lạm dụng

### 11.1. Một dòng nóng vẫn là điểm tuần tự hóa

Giả sử mỗi lần giữ khóa một ngân sách mất trung bình 20 ms. Chỉ xét vùng tuần tự này, trần lý tưởng xấp xỉ 50 lượt mỗi giây trên chính ngân sách đó, chưa tính overhead và biến động. Thêm nhiều instance API không làm hai transaction giữ khóa xung đột cùng lúc trên một dòng.

Ví dụ này là phép ước lượng để nhận diện điểm nghẽn, không phải dự báo benchmark. Cần đo thời gian giữ khóa, thời gian chờ và phân bố tải theo từng miền cạnh tranh. Một hệ thống có throughput tổng lớn vẫn có thể chậm nếu phần lớn request dồn vào một ngân sách.

Chọn guard theo tenant có thể đơn giản nhưng làm mọi dự án của tenant tranh nhau. Chọn theo từng phiếu lại có thể quá hẹp để giữ hạn mức chung. Phạm vi đúng xuất phát từ bất biến và cách phân bổ nguồn lực, không chỉ từ mục tiêu giảm số lock.

Nếu nghiệp vụ cho phép phân bổ ngân sách thành các phần độc lập, có thể tạo các miền cạnh tranh nhỏ hơn. Tuy nhiên, việc phân bổ và thu hồi giữa các phần cũng cần giữ tổng hạn mức; không chia counter tùy ý rồi hy vọng tổng không vượt.

### 11.2. Hàng chờ khóa là tài nguyên cần bảo vệ

Một người dùng có thể gửi nhiều yêu cầu tới cùng đối tượng để làm cạn connection hoặc kéo dài thời gian chờ của người khác. Việc họ có quyền gửi một lệnh không có nghĩa được sử dụng tài nguyên không giới hạn.

Các biện pháp cần gắn với thiết kế thực tế gồm giới hạn request đồng thời theo chủ thể/tenant, giới hạn kích thước batch, từ chối sớm yêu cầu không hợp lệ, áp dụng deadline và giới hạn retry. Không cho client chọn một “khóa toàn hệ thống” bằng một tham số tùy ý.

Giữ khóa trước khi thực hiện nhiều truy vấn không cần thiết làm tăng khả năng gây nghẽn. Có thể chuẩn hóa request, kiểm tra cấu trúc và tính toán thuần trước transaction; những điều phụ thuộc trạng thái thay đổi phải được kiểm tra lại trong vùng bảo vệ, không chuyển ra ngoài chỉ để làm số đo đẹp hơn.

### 11.3. Những chỉ số giúp đánh giá quyết định

| Chỉ số | Điều cần tìm hiểu |
|---|---|
| Thời gian chờ khóa và thời gian giữ khóa | Nghẽn do nhiều người chờ hay do một transaction giữ quá lâu |
| Tỷ lệ timeout, deadlock, retry hết ngân sách | Thiết kế tranh chấp có phù hợp hợp đồng phản hồi không |
| Số request đồng thời theo miền khóa | Có một đối tượng nóng hoặc một nguồn lạm dụng không |
| Tuổi transaction đang mở | Có đường gọi từ xa, chờ người dùng hoặc lỗi giải phóng tài nguyên không |
| Connection pool bị bận và hàng chờ ứng dụng | Chờ khóa có đang lan thành cạn tài nguyên toàn service không |
| Số quyết định và biến động ngân sách/ledger | Có dấu hiệu duyệt lặp, thiếu tác dụng hoặc sai bất biến không |

Log chẩn đoán nên có correlation ID, mã thao tác, tham chiếu miền khóa và kết quả phân loại. Không cần ghi toàn bộ SQL chứa literal nhạy cảm hoặc payload tài chính để đo thời gian chờ. Các định danh đối tượng có độ phân biệt cao cũng cần được cân nhắc trước khi dùng làm nhãn metric để tránh số lượng chuỗi nhãn tăng không kiểm soát.

## 12. Kiểm thử quyết định khóa bằng tình huống xen kẽ

Các tình huống dưới đây mô tả kiểm thử cần có khi triển khai; bài học này không giả định chúng đã được chạy.

### 12.1. Kịch bản hai phiếu cùng ngân sách

Thiết lập số dư 1.000, phiếu A là 700 và B là 500, cả hai chờ duyệt. Chạy hai transaction độc lập trên ít nhất hai connection.

Kỳ vọng sau khi cả hai đã được giải quyết:

- Chỉ một phiếu được duyệt, phiếu còn lại bị từ chối do số dư không đủ, nếu không có thay đổi ngân sách khác.
- Số dư cuối bằng 1.000 trừ tổng số tiền của phiếu đã duyệt.
- Mỗi quyết định commit có ledger và outbox tương ứng; không có kết quả thành công cho phần đã rollback.
- Không giả định A luôn thắng nếu không chủ động điều khiển thứ tự lấy khóa.

Muốn kiểm tra rõ hành vi chờ, cho T1 lấy khóa rồi tạm dừng bằng latch của test; khởi động T2 và quan sát nó đang chờ hoặc nhận lỗi theo chính sách; sau đó mới cho T1 tiếp tục. Không đặt barrier yêu cầu cả hai cùng vào một vùng mà khóa đang cố ngăn không cho chúng cùng vào, vì test sẽ tự tạo tình huống chờ vô ích.

### 12.2. Các tình huống bổ sung

| Tình huống | Cam kết cần xác nhận |
|---|---|
| Hai request duyệt cùng phiếu | Một quyết định logic, một lần giữ ngân sách; replay không trừ thêm |
| Duyệt cạnh tranh với hủy phiếu | Chỉ một thứ tự chuyển trạng thái hợp lệ; không chi trên phiếu đã hủy |
| Duyệt cạnh tranh với giảm hạn mức | Không cho hai thao tác cùng vượt bất biến tổng |
| Hai dự án độc lập | Không tranh nhau một guard quá rộng ngoài thiết kế |
| Quan hệ ngân sách thay đổi sau khi đọc routing hint | Không dùng khóa của ngân sách cũ để duyệt theo ngân sách mới |
| Row lock không tìm thấy bản ghi nghiệp vụ | Unique constraint hoặc guard vẫn ngăn insert trùng theo hợp đồng |
| Một writer import/worker không đi qua API | Vẫn phải tham gia giao thức hoặc bị ràng buộc chặn |
| Lấy khóa xong rồi thiếu quyền | Không có tác dụng nghiệp vụ; phản hồi và audit không lộ đối tượng ngoài quyền |
| Quyền bị thu hồi trong lúc chờ | Quyết định tuân thủ điểm có hiệu lực và cơ chế phối hợp đã công bố |
| Cùng key với payload khác | Trả conflict, không biến thành một ý định mới |
| Timeout hoặc deadlock ở database | Không trả thành công giả, không tiếp tục trên transaction đã hỏng |
| Retry sau lỗi cạnh tranh | Transaction mới đọc lại dữ liệu nhưng giữ điều kiện ý định và chống trùng |
| Mất ACK sau commit | Đối soát theo key gốc, không duyệt hoặc chi lần nữa |
| Outbox bắt buộc ghi thất bại | Phiếu, ngân sách và kết quả idempotency rollback cùng nhau |
| `SKIP LOCKED` không trả về phiếu đang bận | Không diễn giải là không tồn tại, hết việc hoặc thiếu quyền |
| Client gửi nhiều lệnh vào một ngân sách | Deadline và giới hạn tài nguyên có hiệu lực, không retry vô hạn |

Không dùng `Thread.sleep` ngẫu nhiên làm bằng chứng duy nhất rằng race đã được tái hiện. Nên điều khiển các điểm xen kẽ có chủ đích, có timeout cho test và bảo đảm rollback/đóng connection khi test thất bại.

Kiểm thử khóa cần đúng database, isolation và ORM/driver liên quan. Một database in-memory với ngữ nghĩa khóa khác, một mock repository hoặc toàn bộ test chỉ dùng một connection không xác nhận được giao thức trong môi trường thật.

Sau khi chạy, kiểm tra bất biến trên dữ liệu đã commit, không chỉ đếm HTTP thành công. Nếu dùng test nhiều lần hoặc tải ngẫu nhiên để tăng khả năng phát hiện lỗi, chúng bổ sung cho kịch bản điều khiển được chứ không thay cho việc lý giải tài nguyên nào đang bảo vệ bất biến.

## 13. Ghi lại quyết định để người khác có thể kiểm chứng

Một bản ghi quyết định cho ví dụ có thể trình bày như sau:

| Nội dung | Quyết định minh họa |
|---|---|
| Bất biến | Tổng cam kết duyệt không vượt ngân sách; một phiếu chỉ được duyệt một lần trong vòng đời này |
| Miền cạnh tranh | Ngân sách của một tenant, dự án và kỳ |
| Cách bảo vệ | Khóa dòng ngân sách rồi dòng phiếu trong transaction ngắn, kết hợp predicate và constraint |
| Các đường phải phối hợp | Duyệt, hủy quyết định, thay hạn mức, chuyển ngân sách, import và công cụ quản trị |
| Quyền | Kiểm tra tenant, đối tượng, trạng thái, phiên bản và không tự duyệt; phối hợp thay đổi quyền theo hợp đồng riêng |
| Chống trùng | Request idempotency có fingerprint cùng unique ledger theo miền quyết định |
| Tác dụng từ xa | Outbox sau quyết định đã commit; worker và đích có kiểm soát lặp tương ứng |
| Chờ và lỗi | Chờ có giới hạn theo ngân sách thời gian; phân loại timeout/deadlock; retry hữu hạn trong transaction mới |
| Giới hạn | Một ngân sách nóng vẫn tuần tự hóa; khóa không bảo vệ storage hoặc dịch vụ khác ngoài giao thức |
| Bằng chứng | Kiểm thử xen kẽ, kiểm tra dữ liệu commit và số đo chờ/giữ khóa trên hạ tầng triển khai |

Trước khi chốt lựa chọn, cần trả lời được:

1. Có thể thay chuỗi đọc–kiểm tra–ghi bằng ràng buộc hoặc một cập nhật có điều kiện đủ rõ không?
2. Tài nguyên khóa đã bao phủ bất biến chung hay mới chỉ khóa đối tượng của từng request?
3. Mọi writer cạnh tranh có tuân theo cùng giao thức, kể cả worker và đường quản trị không?
4. Dữ liệu quyết định có được đọc/làm mới sau khi lấy khóa, trong cùng transaction với tác dụng không?
5. Phạm vi khóa có bảo vệ cả dữ liệu chưa tồn tại hoặc thay đổi của tập nếu bất biến cần điều đó không?
6. Thứ tự khóa, thời hạn chờ, xử lý lỗi và retry có cụ thể và kiểm chứng được không?
7. Quyền, idempotency và tác dụng bên ngoài đã có cơ chế riêng đúng phạm vi chưa?
8. Điểm nóng có được đo và có hướng xử lý khi mức tải vượt khả năng phục vụ không?

Khóa bi quan là lựa chọn có cơ sở khi nó tạo được một vùng quyết định ngắn, có phạm vi đúng và được mọi thao tác cạnh tranh tôn trọng. Giá trị bảo mật nằm ở việc giữ bất biến trước những lịch thực thi bất lợi, không nằm ở việc code có thêm một annotation hoặc một câu `FOR UPDATE`.
