# Transition postconditions: điều kiện phải đúng sau chuyển trạng thái

## 1. Mục tiêu bài học

Trong chương **State Transitions** của module **Bảo mật logic nghiệp vụ** (mã dịch vụ: SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY), việc giới hạn các cạnh hợp lệ của state machine mới giải quyết một phần bài toán. Sau khi một chuyển trạng thái hoàn tất, dữ liệu, quyền sử dụng và nghĩa vụ phát sinh cũng phải nhất quán với trạng thái mới.

Bài học này tập trung vào **transition postconditions** — các điều kiện phải đúng sau khi chuyển trạng thái thành công. Chúng giúp bảo vệ quy tắc nghiệp vụ trước các cách lạm dụng như bỏ qua phê duyệt, thay số tiền đã duyệt, sử dụng quyền của đối tượng khác, gửi lặp yêu cầu hoặc khai thác xử lý đồng thời.

Sau bài học, bạn có thể:

- Phân biệt tiền điều kiện, bất biến và hậu điều kiện của một chuyển trạng thái.
- Viết hậu điều kiện kiểm tra được, bao gồm dữ liệu bắt buộc thay đổi và dữ liệu phải giữ nguyên.
- Xác định điều gì phải đúng ngay khi commit và điều gì được hoàn tất bất đồng bộ.
- Thiết kế transaction, kiểm soát phiên bản và idempotency để bảo vệ hậu điều kiện.
- Xây dựng các tình huống kiểm thử có khả năng phát hiện tấn công logic.

## 2. Vì sao đổi đúng trạng thái vẫn có thể sai nghiệp vụ?

Xét quy trình hoàn tiền:

~~~text
REQUESTED ──approve──> APPROVED ──schedule──> PAYOUT_PENDING
    │                                         │
    └──reject──> REJECTED                      └──confirm──> PAID
~~~

Hệ thống có thể chỉ cho phép cạnh REQUESTED → APPROVED nhưng vẫn gặp các lỗi sau:

- Đã ghi APPROVED nhưng không lưu ai duyệt hoặc số tiền nào được duyệt.
- Người duyệt thay số tiền trong cùng request, khiến chứng cứ phê duyệt không còn gắn với đề nghị ban đầu.
- Hai yêu cầu cùng được duyệt dựa trên một số dư hoàn tiền còn lại.
- Có bản ghi APPROVED nhưng hạn mức chưa được giữ chỗ do một lệnh cập nhật thất bại.
- Có bản ghi PAID chỉ vì đã đưa thông điệp vào hàng đợi, dù chưa nhận kết quả chi trả.
- Request trả lỗi sau khi commit; client gửi lại và tạo thêm một lần giữ chỗ.

Câu hỏi cần trả lời không dừng ở “có được đi từ A sang B không?”, mà phải bao gồm:

> Khi hệ thống công bố chuyển trạng thái đã thành công, những sự thật nào phải cùng tồn tại và điều gì tuyệt đối không được phát sinh?

## 3. Mô hình tư duy: tiền điều kiện, bất biến, hậu điều kiện

Có thể mô tả một command theo dạng hợp đồng:

~~~text
{ I(S) ∧ Pre(S, actor, command) }
              execute(command)
{ I(S') ∧ Post(S, command, S', effects) }
~~~

Trong đó:

- S là ảnh chụp trạng thái nghiệp vụ trước chuyển đổi.
- S' là trạng thái đã được commit sau chuyển đổi.
- I là tập bất biến phải đúng trong mọi trạng thái nghiệp vụ được công bố là hợp lệ.
- Pre là các điều kiện phải đúng để thực hiện command tại thời điểm quyết định và ghi dữ liệu.
- Post mô tả quan hệ giữa trước và sau, kèm các hiệu ứng bắt buộc hoặc bị cấm.

Đây là hợp đồng cho nhánh **thực hiện thành công**. Hợp đồng đầy đủ còn phải nói rõ lỗi nghiệp vụ, xung đột, retry và trường hợp client không biết transaction đã commit hay chưa.

| Loại điều kiện | Câu hỏi | Ví dụ khi duyệt hoàn tiền |
|---|---|---|
| Tiền điều kiện | Có được phép thực hiện lúc này không? | Yêu cầu đang REQUESTED; actor có quyền với đúng tenant và đối tượng; actor khác người tạo |
| Bất biến | Điều gì phải luôn đúng ở trạng thái đã commit? | Tổng tiền đã trả và đang giữ chỗ không vượt tổng tiền đã thu |
| Hậu điều kiện | Sau thành công phải có những gì, và đã thay đổi ra sao? | Trạng thái APPROVED; lưu người duyệt; tăng tiền giữ chỗ đúng số đã duyệt |
| Điều kiện giữ nguyên | Những gì command không được sửa? | Không thay paymentId, tenantId, người tạo và số tiền đề nghị |

Một quy tắc có thể xuất hiện ở nhiều vai trò. “Số tiền phải dương” có thể là tiền điều kiện để duyệt và cũng là bất biến của yêu cầu hoàn tiền. Điểm khác biệt nằm ở thời điểm kiểm tra và phạm vi bảo đảm.

### 3.1. Hậu điều kiện phải mô tả được sự thay đổi

Câu “số dư hợp lệ sau khi xử lý” quá mơ hồ. Hãy mô tả bằng quan hệ cụ thể:

~~~text
reservedAfter = reservedBefore + approvedAmount
paidAfter     = paidBefore
versionAfter  = versionBefore + 1
~~~

“Không vượt hạn mức” bảo vệ một biên; “tăng đúng số tiền” bảo vệ ý nghĩa của thao tác. Cần cả hai, vì tăng nhầm ít hơn vẫn có thể chưa vượt hạn mức nhưng đã làm sai nghĩa vụ nghiệp vụ.

### 3.2. Thành công, thất bại và kết quả chưa biết

Ba kết quả sau cần được phân biệt:

1. **Commit thành công:** toàn bộ hậu điều kiện cục bộ của transition phải đúng.
2. **Từ chối trước commit hoặc rollback:** không được để lại thay đổi nghiệp vụ một phần từ lần thực thi đó. Security log về lần thử có thể được ghi riêng.
3. **Không xác định từ phía client:** mất kết nối hoặc timeout không chứng minh transaction đã rollback. Client phải có cách tra cứu hoặc retry an toàn bằng cùng khóa idempotency.

Nếu chỉ nhìn HTTP 200 hoặc HTTP 500 để suy ra trạng thái cuối cùng, hệ thống dễ xử lý trùng khi mạng có sự cố.

## 4. Một hợp đồng cụ thể: duyệt yêu cầu hoàn tiền

Ví dụ dưới đây sử dụng một chính sách nghiệp vụ được chọn để minh họa:

- Một payment đã thu có thể có nhiều yêu cầu hoàn tiền.
- Mỗi yêu cầu được duyệt toàn bộ số tiền đã đề nghị; muốn đổi số tiền phải tạo quy trình sửa đổi riêng.
- Duyệt là giữ chỗ hạn mức. Nó chưa có nghĩa là tiền đã được chuyển về khách hàng.
- Tất cả số tiền trong ví dụ là số nguyên theo đơn vị nhỏ nhất của **cùng một loại tiền tệ**.
- Người tạo yêu cầu không được tự duyệt. Quyền duyệt còn phụ thuộc tenant, đối tượng và hạn mức của actor.

Gọi:

~~~text
C = capturedMinor          # Số tiền payment đã thu
P = paidRefundMinor        # Số tiền đã hoàn thành chi trả
R = reservedRefundMinor    # Số tiền đang giữ chỗ
A = requestedAmountMinor   # Số tiền của yêu cầu đang xét
~~~

Trong mô hình đơn giản này, bất biến về hạn mức là:

~~~text
C ≥ 0, P ≥ 0, R ≥ 0
P + R ≤ C
availableMinor = C - P - R
~~~

C được coi là cố định trong ví dụ. Nếu hệ thống còn có chargeback, điều chỉnh số tiền đã thu hoặc nhiều loại giữ chỗ khác, mô hình phải bổ sung các khoản đó và các transition liên quan.

### 4.1. Tiền điều kiện của approve

Tại thời điểm chấp nhận và ghi thay đổi:

- Yêu cầu tồn tại trong tenant mà actor đang thao tác.
- Trạng thái hiện tại là REQUESTED.
- Actor được phép duyệt chính yêu cầu này theo chính sách đang áp dụng.
- Actor không phải người tạo yêu cầu.
- A > 0 và A ≤ C - P - R.
- Loại tiền của yêu cầu trùng với payment.
- Phiên bản yêu cầu khớp phiên bản mà client đã xem, nếu API yêu cầu kiểm tra phiên bản.
- Khóa idempotency chưa được dùng cho một payload khác trong cùng phạm vi.

Đây là kiểm tra phía server. Việc giao diện ẩn nút duyệt hoặc JWT chứa một role phù hợp không đủ để xác nhận quyền đối với đối tượng cụ thể.

### 4.2. Hậu điều kiện của một lần approve mới

| Nhóm | Điều kiện sau commit |
|---|---|
| Trạng thái | refund.status = APPROVED |
| Dấu vết phê duyệt | approvedBy là actor đã được xác thực; approvedAt do server xác lập |
| Nội dung được duyệt | approvedAmountMinor = A tại thời điểm chuyển đổi; không lấy số tiền thay thế từ request approve |
| Hạn mức | reservedAfter = reservedBefore + A; paidAfter = paidBefore |
| Tính nhất quán | Hạn mức còn hợp lệ; mỗi yêu cầu APPROVED có phần giữ chỗ tương ứng |
| Chống thực thi lại | Một lần chuyển hợp lệ chỉ làm tăng reservation một lần |
| Audit nghiệp vụ | Có một bản ghi phê duyệt gắn refundId, actor, số tiền, phiên bản và transitionId |
| Khôi phục kết quả | Có receipt để cùng khóa idempotency và cùng nội dung có thể nhận lại kết quả |
| Phát sự kiện | Có ý định phát RefundApproved trong outbox cùng transaction, nếu thiết kế sử dụng sự kiện |
| Giữ nguyên | tenantId, paymentId, requestedBy, requestedAmountMinor và currency không đổi |
| Điều bị cấm | Không chi trả tiền và không ghi PAID chỉ vì thao tác duyệt đã thành công |

“Hạn mức còn hợp lệ” và “reservation tăng đúng A” cần được thực thi ở cùng một ranh giới nhất quán. Không thể bảo đảm chúng bằng hai lệnh ghi độc lập có thể thành công riêng lẻ.

### 4.3. Hậu điều kiện của replay

Retry bằng **cùng khóa và cùng nội dung** là một nhánh hợp đồng riêng:

~~~text
responseReplay = storedReceipt
businessStateAfterReplay = businessStateBeforeReplay
newReservations = 0
newApprovalTransitions = 0
newApprovalOutboxRows = 0
~~~

Nếu trạng thái hiện tại đã tiến tới PAYOUT_PENDING, receipt vẫn có thể mô tả kết quả approve trước đây. API cần ghi rõ đây là kết quả của command đã thực thi; muốn biết trạng thái mới nhất thì truy vấn resource hiện tại.

Không nên đặt hậu điều kiện replay là “resource hiện vẫn ở APPROVED”, vì một transition hợp lệ khác có thể đã xảy ra sau lần duyệt đầu tiên.

## 5. Đặt hậu điều kiện vào đúng ranh giới transaction

Đối với ví dụ trên, một transaction cơ sở dữ liệu cần bao gồm:

~~~text
Khóa dữ liệu cần quyết định
    → xác thực quyền và kiểm tra receipt
    → kiểm tra trạng thái, phiên bản, số tiền
    → ghi reservation và trạng thái APPROVED
    → ghi audit, receipt và outbox
    → commit
    → trả kết quả thành công
~~~

Nếu một bước bắt buộc thất bại, toàn bộ thay đổi nghiệp vụ của lần approve đó phải rollback. Transaction wrapper chỉ được trả kết quả thành công ra ngoài sau khi commit thành công.

### 5.1. Đừng kiểm tra hậu điều kiện khi transaction đã kết thúc

Mẫu xử lý sau chỉ phát hiện lỗi sau khi dữ liệu sai đã trở nên quan sát được:

~~~java
refundRepository.markApproved(refundId); // Đã commit riêng.
paymentRepository.reserve(paymentId, amount); // Có thể thất bại.
checkReservation(refundId); // Quá muộn để rollback hai thao tác.
~~~

Nếu kiểm tra là một phần của hợp đồng, hãy kiểm tra trên dữ liệu đã được bảo vệ khỏi cập nhật cạnh tranh và để vi phạm làm hủy transaction. Các constraint của cơ sở dữ liệu phải là lớp bảo vệ bổ sung ở thời điểm ghi/commit.

Một kiểm tra trong bộ nhớ không thay thế được cơ chế kiểm soát concurrency. Hai transaction đều có thể kiểm tra thành công trên cùng dữ liệu cũ.

### 5.2. Phải bảo vệ tài nguyên dùng chung

Giả sử:

~~~text
captured = 100
paid = 0
reserved = 40
request A = 40
request B = 40
~~~

Cả A và B cùng đọc thấy available = 60. Nếu chỉ khóa từng dòng refund, hai transaction vẫn có thể cùng duyệt.

Có hai dạng hỏng khác nhau:

- Cập nhật kiểu đọc rồi gán có thể làm mất một lần tăng: reserved vẫn là 80, trong khi tổng reservation cần là 120.
- Cập nhật cộng dồn có thể đưa reserved lên 120, vượt captured = 100.

Cả hai đều vi phạm hậu điều kiện, theo hai cách khác nhau.

Một cách triển khai là khóa dòng payment dùng chung, sau đó khóa dòng refund. Tất cả transition tăng hoặc giảm phần tiền giữ chỗ, bao gồm approve, cancel và xử lý kết quả chi trả, phải tuân thủ cùng quy ước khóa. Với thao tác chạm nhiều payment, cần thêm thứ tự ổn định giữa các payment để giảm nguy cơ deadlock.

Chỉ dùng version trên từng refund không giải quyết được cạnh tranh giữa **hai refund khác nhau** cùng tiêu thụ một hạn mức.

### 5.3. Mã Java minh họa

Mã dưới đây là phác thảo tầng ứng dụng, sử dụng repository và transaction wrapper giả định. Nó mô tả thứ tự bảo vệ hợp đồng, không phải chương trình độc lập có thể chép vào chạy ngay.

Các giả định quan trọng:

- Route chỉ tra cứu quan hệ refund → payment trong đúng tenant; quan hệ này không thay đổi trong ví dụ.
- Các hàm lockForUpdate giữ khóa đến hết transaction; mọi luồng ghi liên quan tuân thủ cùng giao thức.
- Tất cả repository tham gia cùng một transaction và cùng cơ sở dữ liệu.
- Phương thức approveWithoutChangingRequest giữ nguyên dữ liệu đề nghị và tăng version một lần.
- require... ném exception nghiệp vụ làm rollback; không dùng Java assert cho kiểm soát bảo mật.

~~~java
ApprovalResult approve(Actor actor, ApproveCommand cmd) {
    return transactions.required(() -> {
        var route = refunds.findRoute(actor.tenantId(), cmd.refundId())
                .orElseThrow(NotFound::new);

        // Khóa tài nguyên chung trước, đối tượng chuyển trạng thái sau.
        var payment = payments.lockForUpdate(
                actor.tenantId(), route.paymentId());
        var refund = refunds.lockForUpdate(
                actor.tenantId(), cmd.refundId());

        requireSameParent(refund, payment);
        access.requireCanAccessApprovalResult(actor, refund);

        var scope = new ReceiptScope(
                actor.tenantId(), actor.id(), "APPROVE_REFUND");
        var fingerprint = fingerprints.of(
                scope, cmd.refundId(), cmd.expectedVersion());

        var oldReceipt = receipts.find(scope, cmd.idempotencyKey());
        if (oldReceipt.isPresent()) {
            requireSameFingerprint(oldReceipt.get(), fingerprint);
            return oldReceipt.get().result();
        }

        requireState(refund, REQUESTED);
        requireVersion(refund, cmd.expectedVersion());
        approvalPolicy.requireCanApprove(actor, refund, payment);

        long amount = refund.requestedAmountMinor(); // Dữ liệu server.
        requireSameCurrency(refund, payment);
        requireNonNegativePaymentAmounts(payment);
        long available = Math.subtractExact(
                Math.subtractExact(payment.capturedMinor(),
                                   payment.paidRefundMinor()),
                payment.reservedRefundMinor());
        requirePositiveAndWithin(amount, available);

        var before = ApprovalSnapshot.of(refund, payment);
        var transitionId = transitionIds.next();
        var approvedAt = clock.instant();

        payment.reserveExact(amount);
        refund.approveWithoutChangingRequest(
                actor.id(), approvedAt, amount, transitionId);

        var result = ApprovalResult.from(refund);
        payments.save(payment);
        refunds.save(refund);
        audit.insertApproval(before, refund, actor, transitionId);
        outbox.insertRefundApproved(transitionId, refund);
        receipts.insert(scope, cmd.idempotencyKey(), fingerprint, result);

        postconditions.requireApproval(before, refund, payment);
        return result;
    });
}
~~~

Trong ví dụ này, kiểm tra hậu điều kiện cuối cùng đối chiếu ảnh chụp trước với thực thể sau: số tiền giữ chỗ tăng đúng, số tiền đã trả giữ nguyên, chứng cứ phê duyệt đủ và các trường được bảo vệ không đổi. Việc insert audit, outbox và receipt phải báo lỗi nếu không thực hiện được; chúng không phải các thao tác “best effort”.

Math.subtractExact làm lỗi số học bị lộ ra thay vì âm thầm tràn số. Phương thức reserveExact cũng cần kiểm tra tràn khi cộng. Trường hợp dữ liệu đầu vào đã hỏng hoặc số học thất bại phải dẫn tới rollback, không được biến thành một kết quả thành công mặc định.

Nếu cùng một khóa idempotency bị sử dụng đồng thời trên **hai refund khác nhau**, khóa payment có thể không tuần tự hóa được cả hai transaction. Vì vậy receipt vẫn phải có unique constraint theo scope và khóa. Transaction thua cuộc phải rollback; sau đó handler ở ngoài transaction đọc lại receipt trong một transaction mới, so fingerprint và trả replay hoặc báo xung đột. Không bắt lỗi unique rồi tiếp tục dùng transaction đã lỗi.

### 5.4. Constraint và cập nhật có điều kiện

Tùy mô hình lưu trữ, các lớp bảo vệ có thể gồm:

| Cơ chế | Điều kiện được bảo vệ | Giới hạn |
|---|---|---|
| CHECK cho số tiền | Không âm; paid ≤ captured; reserved ≤ captured - paid | Không tự chứng minh tổng reservation của mọi refund khớp một bộ đếm |
| NOT NULL hoặc CHECK có điều kiện theo state | APPROVED phải có approvedBy, approvedAt, approvedAmount | Các trạng thái về sau cũng có thể cần giữ chứng cứ này |
| UNIQUE cho transitionId hoặc approval record | Không có hai bản ghi phê duyệt cho cùng một lần chuyển | Không tự bảo vệ hạn mức dùng chung |
| UNIQUE cho receipt scope và key | Không chấp nhận hai kết quả độc lập cho cùng khóa | Cần so fingerprint để phát hiện khóa bị dùng cho payload khác |
| Foreign key | Audit, reservation hoặc outbox tham chiếu đúng đối tượng theo thiết kế | Quyền nghiệp vụ vẫn phải được kiểm tra riêng |
| Cập nhật theo state và version | Một ảnh chụp cũ không thể ghi đè trạng thái mới | Cần cơ chế riêng cho bất biến xuyên đối tượng |

Một cách khác với khóa tường minh là cập nhật có điều kiện:

~~~sql
UPDATE payment
SET reserved_refund_minor = reserved_refund_minor + :amount,
    version = version + 1
WHERE tenant_id = :tenant_id
  AND id = :payment_id
  AND :amount > 0
  AND :amount <= captured_minor
                 - paid_refund_minor
                 - reserved_refund_minor;
~~~

Transaction phải kiểm tra **đúng một dòng** đã được cập nhật; không được tiếp tục ghi APPROVED khi số dòng là 0. Lệnh cập nhật refund theo state/version, audit, receipt và outbox vẫn phải nằm trong cùng transaction; lỗi ở bất kỳ bước bắt buộc nào phải rollback cả phần giữ chỗ.

Đây là phương án minh họa thay cho bước đọc rồi ghi không được bảo vệ. Cần xác nhận ngữ nghĩa cạnh tranh của hệ quản trị và isolation level đang sử dụng. Với bất biến phức tạp liên quan nhiều dòng, có thể cần khóa tập dữ liệu phù hợp hoặc mức cô lập mạnh hơn cùng cơ chế retry toàn bộ transaction.

Không nên suy luận rằng “đã mở transaction” đồng nghĩa mọi bất biến tự được bảo đảm.

## 6. Hậu điều kiện nào phải đúng ngay, điều nào có thể đến sau?

### 6.1. Phân tách trạng thái nội bộ và sự thật ở hệ thống ngoài

Sau approve, hệ thống có thể cam kết:

~~~text
APPROVED
+ hạn mức đã được giữ chỗ
+ ý định gửi sự kiện đã được ghi bền vững
~~~

Nó chưa thể cam kết:

~~~text
khách hàng đã nhận tiền
mọi consumer đã xử lý sự kiện
email thông báo đã được giao thành công
~~~

Cơ sở dữ liệu cục bộ không thể tự rollback một khoản chi trả đã xảy ra tại cổng thanh toán. Không đưa lời gọi cổng thanh toán vào transaction rồi mặc định hai hệ thống trở thành nguyên tử.

Để có trạng thái PAID, hợp đồng riêng phải yêu cầu bằng chứng hoàn tất chi trả được tin cậy: xác minh nguồn thông báo hoặc kết quả truy vấn, đối chiếu mã giao dịch, payment/refund, số tiền, currency và trạng thái nhà cung cấp. Thông báo trùng hoặc đến muộn không được làm tăng paidRefundMinor lần nữa.

Trong mô hình này, khi xác nhận chi trả A đã thành công:

~~~text
reservedAfter = reservedBefore - A
paidAfter     = paidBefore + A
refundAfter.status = PAID
~~~

Các thay đổi nội bộ đó phải được commit cùng nhau. Mô hình nhiều bước chi trả có thể cần thêm trạng thái và chứng từ; không suy diễn rằng một boolean success đủ cho mọi tích hợp.

### 6.2. Outbox bảo vệ ý định, không bảo đảm giao đúng một lần

Hậu điều kiện cục bộ phù hợp là “có một outbox row cho transitionId đã commit”. Nó không phải “broker đã nhận đúng một lần”.

Publisher có thể phát lại sau khi gửi thành công nhưng chưa kịp đánh dấu đã gửi. Vì vậy:

- Mỗi sự kiện có eventId ổn định, aggregateId và version/sequence phù hợp.
- Consumer có cơ chế nhận biết sự kiện đã xử lý.
- Hiệu ứng cục bộ và dấu đã xử lý của consumer cần được commit cùng transaction nếu cùng kho dữ liệu.
- Nếu consumer gọi hệ thống ngoài, tiếp tục cần idempotency và đối soát tại ranh giới đó.
- Consumer không suy ra thứ tự từ thời điểm nhận; sự kiện có thể bị trễ hoặc đảo thứ tự.

Nếu luồng bắt buộc có xử lý bất đồng bộ, đặc tả thêm thời hạn và hành động khi quá hạn, ví dụ: “outbox chưa được xử lý sau ngưỡng vận hành thì cảnh báo và retry”. Đây là yêu cầu về tiến triển, khác với điều kiện phải đúng ngay sau commit.

### 6.3. Bù trừ cũng là một transition cần hợp đồng

Nếu yêu cầu đã APPROVED nhưng chưa chi trả và nghiệp vụ cho phép hủy, cancellation có thể giải phóng reservation. Hợp đồng cần xác nhận chỉ giải phóng đúng một lần và không chạy đồng thời với bước khiến khoản chi trả trở nên không thể thu hồi.

Nếu nhà cung cấp đã chuyển tiền, việc đổi lại trạng thái thành REQUESTED và giảm paid không hoàn tác được thế giới thực. Cần một quy trình nghiệp vụ phục hồi riêng với chứng cứ và hậu điều kiện riêng.

## 7. Bảo vệ dữ liệu và quyền gắn với transition

### 7.1. Command chỉ nhận dữ liệu mà người gọi được phép quyết định

Với approve trong ví dụ, API có thể chỉ cần refundId, expectedVersion và idempotency key. Những giá trị sau do server xác định:

- actorId lấy từ danh tính đã xác thực.
- tenantId lấy từ ngữ cảnh được kiểm chứng và phải được ràng buộc vào truy vấn.
- approvedAmount lấy từ đề nghị đang được khóa.
- approvedAt lấy từ đồng hồ phía server.
- approvedBy, transitionId và các liên kết chứng từ được thiết lập bởi nghiệp vụ.

Không bind toàn bộ JSON của client vào entity rồi lưu lại. Nếu client gửi thêm approvedAmount, paymentId, approvedBy hoặc status, hợp đồng API cần từ chối trường không được phép hoặc có chính sách bỏ qua rõ ràng; các trường đó không được tác động tới hiệu ứng nghiệp vụ.

### 7.2. Hậu điều kiện có cả phần “không thay đổi”

Một danh sách các trường bắt buộc có giá trị vẫn chưa ngăn được việc thao tác sai đối tượng. Có thể viết rõ:

~~~text
refundAfter.id                   = refundBefore.id
refundAfter.tenantId             = refundBefore.tenantId
refundAfter.paymentId            = refundBefore.paymentId
refundAfter.requestedBy          = refundBefore.requestedBy
refundAfter.requestedAmountMinor = refundBefore.requestedAmountMinor
refundAfter.currency             = refundBefore.currency
~~~

Đối với dữ liệu bắt buộc bất biến sau phê duyệt, các transition về sau cũng phải bảo vệ nó. Nếu cho phép sửa số tiền sau APPROVED mà không vô hiệu hóa phê duyệt cũ và tính lại reservation, hậu điều kiện vừa được thiết lập sẽ mất ý nghĩa.

Một quy trình sửa đề nghị có thể tạo revision mới và đưa về bước chờ duyệt, nhưng phải có hợp đồng riêng về hủy phê duyệt cũ, giải phóng hạn mức và liên kết lịch sử.

### 7.3. Quyền phải gắn với đối tượng và thời điểm quyết định

Điều kiện “actor có role APPROVER” chưa thể hiện:

- Actor có được thao tác trong tenant này không?
- Actor có được duyệt payment/refund này không?
- Số tiền có vượt hạn mức phê duyệt của actor không?
- Actor có phải người tạo hoặc bên hưởng lợi bị chính sách phân tách nhiệm vụ hạn chế không?

Kiểm tra quyền phải dùng dữ liệu có thẩm quyền tại điểm quyết định, trong ranh giới nhất quán đã chọn. Nếu yêu cầu nghiệp vụ là thu hồi quyền có hiệu lực tức thời kể cả khi đang có transaction cạnh tranh, dữ liệu phân quyền cũng cần cơ chế phối hợp phù hợp, chẳng hạn khóa hoặc kiểm tra policy version. Khóa dòng refund tự nó không giải quyết được cuộc đua thay đổi quyền.

Với replay, cần kiểm tra người gọi hiện được xem kết quả tương ứng trước khi trả receipt. Biết một idempotency key không phải bằng chứng có quyền truy cập.

## 8. Kiểm thử hậu điều kiện bằng các tình huống lạm dụng

Các tình huống dưới đây là nội dung hướng dẫn xây dựng kiểm thử. Khi áp dụng vào hệ thống thực, hãy kiểm tra trạng thái đã commit bằng một lượt đọc mới sau command, thay vì chỉ nhìn đối tượng Java còn trong bộ nhớ.

### 8.1. Ma trận kiểm thử

| Tình huống | Kết quả cần kiểm chứng |
|---|---|
| Approve hợp lệ | APPROVED; đủ chứng cứ; reservation tăng đúng A; paid giữ nguyên; audit, receipt, outbox đúng hợp đồng |
| Người tạo tự duyệt | Từ chối; trạng thái và reservation giữ nguyên |
| Actor thuộc tenant khác biết refundId | Không truy cập được đối tượng; không phát sinh thay đổi nghiệp vụ |
| Client gửi thêm số tiền, người duyệt hoặc status | Không thể thay đổi giá trị do server quyết định; nếu từ chối request thì không có hiệu ứng nghiệp vụ |
| Phiên bản cũ | Từ chối hoặc trả xung đột theo API; không ghi đè dữ liệu mới |
| Cùng key, cùng payload, gọi lại sau commit | Trả receipt cũ cho người có quyền; không tăng reservation hoặc thêm approval event |
| Cùng key, khác refundId hoặc expectedVersion | Báo xung đột nội dung; không phát sinh thêm chuyển trạng thái |
| Hai key khác nhau cùng approve một refund | Tối đa một lần approve mới; lần còn lại nhận xung đột hoặc kết quả đã tồn tại theo hợp đồng |
| Hai refund tranh phần hạn mức chỉ đủ một yêu cầu | Tối đa một yêu cầu được giữ chỗ; tổng hạn mức vẫn hợp lệ |
| Lỗi khi ghi audit, receipt hoặc outbox bắt buộc | Rollback cả trạng thái refund lẫn reservation |
| Client timeout sau commit rồi retry | Nhận được kết quả đã lưu; không có hiệu ứng thêm |
| Sự kiện phát hai lần | Consumer không tạo hai lần cùng một hiệu ứng nghiệp vụ |
| Thông báo chi trả sai số tiền, currency hoặc liên kết | Không chuyển PAID; không cập nhật bộ đếm chi trả |
| Kết quả chi trả thành công được gửi lại | Không tăng paid hoặc giảm reserved lần thứ hai |
| Số tiền bằng 0, âm, vượt hạn mức hoặc gây tràn | Không chấp nhận; không có trạng thái đã commit bị hỏng |

Với request bị từ chối, “không có thay đổi nghiệp vụ” không có nghĩa là cấm ghi nhật ký an ninh về lần thử. Hãy tách audit của **phê duyệt thành công** khỏi log của một yêu cầu bị chặn.

### 8.2. Kiểm thử cạnh tranh phải tạo được sự chồng lấn

Gửi hai request nối tiếp không chứng minh được tính an toàn khi xử lý đồng thời. Một kiểm thử cạnh tranh có ý nghĩa nên:

1. Tạo payment có available = 60 và hai refund REQUESTED, mỗi yêu cầu 40.
2. Dùng hai transaction hoặc hai kết nối độc lập.
3. Điều phối để hai command thực sự cạnh tranh tại điểm giữ chỗ.
4. Chờ cả hai kết thúc, bao gồm nhánh retry nếu thiết kế có retry.
5. Đọc lại bằng transaction mới.
6. Kiểm tra chỉ có một yêu cầu được duyệt, reservation tăng đúng 40 và chứng từ chỉ xuất hiện cho lần thành công.

Không chỉ kiểm tra reserved ≤ captured. Trong một lỗi mất cập nhật, bộ đếm có thể vẫn dưới hạn mức trong khi hai refund đều APPROVED. Cần kiểm tra cả quan hệ giữa bộ đếm và các reservation được biểu diễn bởi trạng thái/chứng từ của từng refund.

### 8.3. Chèn lỗi vào các ranh giới bắt buộc

Ví dụ một integration test đặt lỗi có kiểm soát khi insert outbox:

~~~text
Trước:
  refund.status = REQUESTED
  payment.reserved = 20
  refund.amount = 30

Thực thi:
  cập nhật reservation
  cập nhật refund
  insert audit
  insert outbox → lỗi

Sau khi transaction kết thúc:
  refund.status = REQUESTED
  payment.reserved = 20
  không có approval audit mới
  không có approval receipt mới
  không có outbox row của lần thử
~~~

Kiểm thử này chứng minh điều có giá trị hơn việc chỉ mock repository rồi xác nhận save được gọi: các thao tác thật sự cùng rollback tại kho dữ liệu.

Một ca khác cần mô phỏng mất response **sau commit**. Kết quả mong đợi khi retry là replay, không phải rollback. Hai vị trí gây lỗi này có thể cùng hiện ra dưới dạng timeout với client nhưng đòi hỏi hành vi phục hồi khác nhau.

### 8.4. Kiểm thử theo chuỗi transition

Ngoài từng command riêng lẻ, có thể sinh các chuỗi như:

~~~text
request → approve → approve lại → schedule → confirm → confirm lại
request → reject → approve
request → approve → cancel → callback đến muộn
~~~

Sau mỗi bước được chấp nhận, kiểm tra bất biến toàn cục và hậu điều kiện của đúng transition đó. Sau bước bị từ chối, kiểm tra phần trạng thái nghiệp vụ phải được giữ nguyên.

Chuỗi có callback đến muộn đặc biệt cần quy tắc rõ ràng: hệ thống không được hủy một khoản đã thực sự chi trả chỉ bằng trạng thái nội bộ, cũng không được tin callback không khớp chứng từ của lần chi trả đang theo dõi.

## 9. Những lỗi thiết kế thường làm hậu điều kiện mất hiệu lực

| Cách làm | Vì sao có thể bị lạm dụng | Hướng sửa |
|---|---|---|
| Chỉ kiểm tra enum đích | Thiếu reservation, chứng cứ hoặc dữ liệu liên quan | Định nghĩa hợp đồng cho từng command |
| Kiểm tra trước transaction rồi ghi sau | Quyết định dựa trên trạng thái có thể đã thay đổi | Kiểm tra trong cơ chế khóa/version phù hợp |
| Chỉ khóa refund | Các refund khác vẫn tiêu thụ chung hạn mức | Bảo vệ tài nguyên chung hoặc cập nhật có điều kiện |
| Dùng assert cho quy tắc bảo mật | Assertion có thể không được bật khi chạy | Validation/exception bắt buộc và constraint |
| Tin các trường do client gửi | Cho phép thay số tiền, actor hoặc đối tượng | Command hẹp; server suy ra dữ liệu có thẩm quyền |
| Thấy APPROVED thì trả thành công cho mọi request | Che giấu payload khác hoặc replay sai phạm vi | Receipt có scope, fingerprint và kiểm tra quyền |
| Chỉ tạo eventId ngẫu nhiên mỗi lần retry | Mỗi lần gọi vẫn có thể thành một hiệu ứng mới | Gắn hiệu ứng với transition hợp lệ và idempotency bền vững |
| Kiểm tra số dòng update bằng 0 nhưng vẫn tiếp tục | Ghi APPROVED dù chưa giữ được tiền | Xung đột phải kết thúc hoặc rollback toàn bộ command |
| Commit rồi mới kiểm tra hậu điều kiện | Dữ liệu sai đã được công bố | Đặt ràng buộc trước hoặc tại commit |
| Gửi broker rồi coi như đã hoàn tiền | Đồng nhất “đã yêu cầu” với “đã hoàn tất” | Trạng thái trung gian và bằng chứng chi trả |
| Retry tự động sau mọi exception | Có thể lặp hiệu ứng đã xảy ra ngoài hệ thống | Phân loại lỗi, giới hạn retry và bảo vệ idempotency |

Riêng UNIQUE(transitionId) chỉ chặn trùng **cùng giá trị ID**. Nếu mỗi lần thực thi sai lại sinh ID mới, constraint đó vẫn có thể cho qua. Tính “một phê duyệt cho một lần chuyển hợp lệ” cần được bảo vệ bằng state/version và khóa nghiệp vụ thích hợp, không dựa vào độ ngẫu nhiên của ID.

## 10. Áp dụng cùng cách nghĩ cho nghiệp vụ khác

| Transition | Hậu điều kiện đáng chú ý |
|---|---|
| Đơn hàng DRAFT → CONFIRMED | Chốt giá theo chính sách phía server; tổng tiền khớp dòng hàng; reservation tồn kho được ghi đúng |
| Chứng từ PENDING → APPROVED | Chứng cứ phê duyệt gắn đúng revision; giữ phân tách nhiệm vụ; không sửa nội dung đã duyệt |
| Mã giảm giá AVAILABLE → REDEEMED | Ghi người dùng và đơn hàng; hạn mức sử dụng giảm đúng một lần; retry không tiêu thụ thêm lượt |
| Tài khoản ACTIVE → SUSPENDED | Các đường thao tác thuộc phạm vi đình chỉ phải thực thi chính sách thu hồi quyền đã công bố |
| Lời mời PENDING → ACCEPTED | Tạo membership đúng tổ chức, đúng danh tính và quyền đã được phép; token không thể tạo thêm membership khi dùng lại |

Với tài khoản bị đình chỉ, nếu access token hoặc cache quyền còn hiệu lực, chỉ đổi một cột status có thể chưa đáp ứng hậu điều kiện mong muốn. Cần nêu rõ hiệu lực thu hồi quyền xảy ra ngay hay trong khoảng trễ được cho phép, và mọi đường thực thi phải phù hợp với cam kết đó.

## 11. Mẫu đặc tả một transition

Có thể dùng mẫu sau khi thiết kế hoặc review một command:

~~~text
Tên command:
Đối tượng, tenant và tài nguyên dùng chung:
Trạng thái nguồn → trạng thái đích:

Tiền điều kiện:
- Quyền theo đối tượng, phân tách nhiệm vụ, hạn mức
- Trạng thái, version, dữ liệu có thẩm quyền

Bất biến được bảo vệ:
- Phạm vi một đối tượng và xuyên đối tượng

Hậu điều kiện của lần thực thi mới:
- Trạng thái và dữ liệu bắt buộc thay đổi
- Dữ liệu bắt buộc giữ nguyên
- Chứng từ, audit, receipt, outbox
- Hiệu ứng bị cấm tại bước này

Hợp đồng replay:
- Scope và fingerprint
- Kết quả được lưu; kiểm tra quyền đọc lại
- Không phát sinh thêm hiệu ứng

Ranh giới nhất quán:
- Những gì cùng commit
- Khóa/version/conditional update/constraint
- Chính sách xung đột và retry

Hiệu ứng ngoài hệ thống:
- Bằng chứng thành công
- Idempotency, đối soát, trạng thái trung gian
- Hành động khi thất bại hoặc quá hạn

Kiểm thử:
- Thành công, quyền sai, dữ liệu bị sửa
- Gọi trùng, xử lý đồng thời, lỗi giữa chừng
- Đọc lại dữ liệu sau commit/rollback
~~~

## 12. Câu hỏi tự kiểm tra

1. Vì sao trạng thái APPROVED chưa đủ để kết luận quy trình phê duyệt hợp lệ?
2. Hai refund khác nhau có version độc lập. Vì sao optimistic locking trên từng refund vẫn có thể để vượt hạn mức chung?
3. Sau timeout, dựa vào bằng chứng nào để phân biệt retry một command cũ với yêu cầu mới?
4. Hậu điều kiện của replay khác gì với hậu điều kiện của lần approve đầu tiên?
5. Outbox đã commit chứng minh được điều gì, và chưa chứng minh được điều gì?
6. Ngoài trạng thái và số tiền, những trường nào trong nghiệp vụ của bạn phải được giữ nguyên sau khi duyệt?
7. Nếu một bước bắt buộc như ghi audit thất bại, dữ liệu nào phải được quan sát thấy sau rollback?
8. Một consumer nhận lại cùng thông báo chi trả phải bảo vệ cả bộ đếm tiền và chứng từ bằng cách nào?

Khi trả lời, hãy chỉ ra cụ thể **dữ liệu nào**, **thay đổi bao nhiêu**, **trong ranh giới nào** và **được kiểm chứng bằng cách nào**. Một hậu điều kiện hữu ích phải đủ rõ để người triển khai, người review và người kiểm thử cùng nhận ra trạng thái đúng sau mỗi chuyển đổi.
