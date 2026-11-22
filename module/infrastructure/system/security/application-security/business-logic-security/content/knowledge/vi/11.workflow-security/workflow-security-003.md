# Workflow interruption: bảo vệ quy trình khi bị gián đoạn

## 1. Mục tiêu bài học

Trong chương **Workflow Security** của module **Bảo mật logic nghiệp vụ** (mã dịch vụ: SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY), **workflow interruption** là tình huống quy trình nhiều bước bị dừng hoặc mất liên lạc trước khi các bên cùng biết kết quả cuối cùng.

Gián đoạn có thể đến từ người dùng đóng trình duyệt, mất mạng, request timeout, tiến trình bị dừng, worker khởi động lại hoặc một dịch vụ phụ thuộc chưa phản hồi. Kẻ tấn công cũng có thể chủ động tạo ra những điều kiện này để giữ tài nguyên, gửi lại yêu cầu, thay dữ liệu giữa các bước hoặc lợi dụng trạng thái chưa hoàn tất.

Mục tiêu bảo mật là giữ các quy tắc nghiệp vụ đúng khi quy trình bị ngắt, đồng thời cung cấp đường tiếp tục, hủy và phục hồi có kiểm soát. Sau bài học, bạn có thể:

- Phân biệt “thao tác thất bại” với “chưa biết thao tác đã thành công hay chưa”.
- Xác định trạng thái, bằng chứng và định danh phải được lưu bền vững trước hiệu ứng bên ngoài.
- Thiết kế resume, retry, cancellation và compensation mà không bỏ qua quyền hay bước phê duyệt.
- Hạn chế lạm dụng các quy trình bị bỏ dở để chiếm giữ tài nguyên.
- Xây dựng các tình huống kiểm thử tại những điểm gián đoạn có rủi ro nghiệp vụ cao.

## 2. Gián đoạn trở thành lỗ hổng nghiệp vụ như thế nào?

Xét một checkout đơn giản:

~~~text
Chốt nội dung đơn
    → giữ hàng
    → yêu cầu thanh toán
    → xác nhận thanh toán
    → tạo yêu cầu giao hàng
~~~

Các bước không nhất thiết chạy trong cùng một transaction. Cơ sở dữ liệu nội bộ, cổng thanh toán và hệ thống giao hàng có thời điểm ghi nhận riêng.

Giả sử cổng thanh toán đã thu tiền nhưng response về ứng dụng bị mất:

~~~text
Ứng dụng                  Cổng thanh toán
    | --- charge -------------> |
    |                           | Ghi nhận thu tiền
    | <--- response bị mất ---- X
    |
    | Request timeout
~~~

Nếu ứng dụng coi timeout là “chưa thu tiền” và tạo giao dịch mới, khách hàng có thể bị thu hai lần. Nếu ứng dụng coi timeout là “đã thu tiền” và giao hàng, hệ thống có thể giao cho một khoản thanh toán chưa thành công.

Những kiểu lạm dụng thường gặp còn gồm:

| Tình huống bị khai thác | Hệ quả có thể xảy ra |
|---|---|
| Bỏ dở nhiều checkout sau bước giữ hàng | Hàng bị giữ quá lâu, người khác không mua được |
| Đóng trang rồi gọi thẳng endpoint hoàn tất | Bỏ qua bước xác nhận, thanh toán hoặc phê duyệt |
| Đổi giỏ hàng sau khi đã được xác nhận giá | Thanh toán theo giá cũ cho nội dung mới |
| Resume bằng workflowId của người khác | Tiếp tục hoặc đọc dữ liệu của đối tượng không thuộc quyền |
| Gửi lại command khi worker đang xử lý | Tạo thêm giao dịch, thêm reservation hoặc giao hàng trùng |
| Hủy ngay khi thanh toán đang hoàn tất | Vừa được giao hàng vừa được giải phóng tiền/hạn mức |
| Giữ một resume token quá lâu | Dùng lại ngữ cảnh quyền hoặc phê duyệt đã hết hiệu lực |

Không cần hệ thống có lỗi hạ tầng lớn mới xuất hiện rủi ro. Một lần timeout đúng thời điểm cũng đủ bộc lộ hợp đồng nghiệp vụ chưa rõ.

## 3. Phân biệt kết quả thất bại và kết quả chưa biết

Mỗi bước có hiệu ứng cần phân loại ít nhất các kết quả sau:

| Kết quả | Ý nghĩa | Cách xử lý điển hình |
|---|---|---|
| Chưa bắt đầu | Chưa có ý định thực thi được ghi bền vững | Có thể bắt đầu nếu tiền điều kiện còn đúng |
| Đã ghi ý định, chưa biết đã gửi chưa | Command và định danh đã được lưu; worker có thể đang chạy | Tiếp tục cùng operation, không tạo operation mới |
| Thành công được xác nhận | Có bằng chứng phù hợp từ nguồn có thẩm quyền | Ghi kết quả và mở bước kế tiếp |
| Thất bại dứt khoát | Có kết quả cuối cùng được xác thực cho operation đó | Áp dụng nhánh thất bại hoặc giải phóng theo hợp đồng |
| Chưa xác định | Có khả năng hiệu ứng đã xảy ra nhưng chưa đủ bằng chứng | Đối soát, retry an toàn theo hợp đồng hoặc chuyển xử lý thủ công |

**Timeout, mất kết nối và worker bị dừng không tự chứng minh giao dịch thất bại.** Ngược lại, log “đã gửi request” cũng không chứng minh hiệu ứng đã xảy ra.

Một kết quả “không tìm thấy” khi truy vấn nhà cung cấp có thể chưa dứt khoát nếu hệ thống ngoài có độ trễ hiển thị hoặc request trước vẫn đang xử lý. Chỉ coi đó là căn cứ cho một lần thực thi mới khi hợp đồng của nhà cung cấp cho phép kết luận như vậy.

Không gom mọi trường hợp vào một trạng thái FAILED rồi cho phép người dùng bấm “thử lại từ đầu”. Cách đó làm mất sự khác biệt quyết định giữa một thao tác chưa xảy ra và một thao tác có thể đã xảy ra.

## 4. Đặc tả một checkout có thể phục hồi

Ví dụ trong bài sử dụng các chính sách minh họa sau:

- Một checkout thuộc một tenant và một khách hàng xác định.
- Nội dung đơn, tổng tiền và loại tiền được chốt theo một revision trước khi thanh toán.
- Mỗi lần có thể tạo hiệu ứng thanh toán có một paymentOperationId được lưu trước khi gọi hệ thống ngoài.
- Chỉ tạo yêu cầu giao hàng khi có thanh toán đã xác nhận và tài nguyên thực hiện đơn còn hợp lệ.
- Nếu thanh toán thành công nhưng không thể thực hiện đơn, hệ thống đi vào quy trình giải quyết/hoàn tiền riêng.
- Resume không tự kéo dài thời hạn giữ hàng hoặc khôi phục một phê duyệt đã hết hiệu lực.

### 4.1. Những bất biến cần được bảo vệ

**Không giao hàng khi thiếu bằng chứng thanh toán.**

~~~text
canRequestFulfillment
    ⇒ paymentStatus = CONFIRMED
       ∧ paidAmount = orderSnapshot.total
       ∧ paidCurrency = orderSnapshot.currency
       ∧ payment.orderRevision = orderSnapshot.revision
       ∧ inventoryCommitment hợp lệ
~~~

**Một lần thử nghiệp vụ không tạo thêm hiệu ứng chỉ vì bị gửi lại.**

~~~text
cùng paymentOperationId
    ⇒ cùng danh tính thao tác tại nhà cung cấp
       và không có lần thu tiền độc lập mới do retry
~~~

Để đạt được điều này, phải có cơ chế idempotency hoặc bảo vệ tương đương ở ranh giới có hiệu ứng. Chỉ lưu UUID trong cơ sở dữ liệu của ứng dụng không đủ nếu nhà cung cấp vẫn thực thi mọi lần gọi như một giao dịch mới.

**Hàng không được tính là vừa sẵn bán vừa đang được cam kết cho cùng một đơn.**

Ví dụ với mô hình tồn kho đơn giản:

~~~text
available = sellable - activeReservations - allocated
available ≥ 0
~~~

Mọi thao tác giữ, hết hạn, gia hạn và chuyển giữ chỗ thành phân bổ phải bảo vệ cùng một mô hình tồn kho. Không kiểm tra theo một bộ đếm rồi cập nhật theo một khái niệm khác.

**Trạng thái cuối phải phản ánh đầy đủ nghĩa vụ còn tồn tại.**

Nếu đã yêu cầu hủy nhưng vẫn có một khoản thanh toán chưa rõ kết quả, hệ thống chưa thể công bố “đã hủy và đã giải quyết xong”. Có thể công bố “đã nhận yêu cầu hủy, đang đối soát”. Nếu phát hiện đã thu tiền, cần theo dõi nghĩa vụ hoàn tiền cho đến kết quả phù hợp.

### 4.2. Một sơ đồ luồng minh họa

~~~mermaid
stateDiagram-v2
    [*] --> OPEN
    OPEN --> RESERVED: Chốt đơn và giữ hàng
    RESERVED --> PAYMENT_PENDING: Ghi ý định thanh toán
    RESERVED --> CANCELLED: Hủy trước khi có thao tác thanh toán
    PAYMENT_PENDING --> PAYMENT_CONFIRMED: Xác nhận đã thu tiền
    PAYMENT_PENDING --> RECONCILING: Timeout hoặc chưa rõ kết quả
    PAYMENT_PENDING --> CANCEL_REQUESTED: Nhận yêu cầu hủy
    RECONCILING --> PAYMENT_CONFIRMED: Đối soát xác nhận thành công
    RECONCILING --> CANCELLED: Xác nhận thất bại cuối cùng và hủy
    RECONCILING --> CANCEL_REQUESTED: Nhận yêu cầu hủy
    CANCEL_REQUESTED --> CANCELLED: Không còn hiệu ứng thanh toán chưa giải quyết
    CANCEL_REQUESTED --> REFUND_PENDING: Xác nhận đã thu tiền
    REFUND_PENDING --> CANCELLED: Xác nhận đã xử lý xong nghĩa vụ hoàn
    PAYMENT_CONFIRMED --> FULFILLMENT_PENDING: Còn quyền thực hiện đơn và đủ tài nguyên
    PAYMENT_CONFIRMED --> REFUND_PENDING: Không thể thực hiện đơn
    FULFILLMENT_PENDING --> COMPLETED: Xác nhận hoàn tất
~~~

Sơ đồ chỉ thể hiện một số đường chính. Hệ thống thực tế còn cần nhánh thất bại hoàn tiền, lỗi giao hàng và xử lý thủ công. Nếu có các nhánh chạy song song, nên tách trạng thái payment, inventory, fulfillment và cancellation thay vì ép mọi tổ hợp vào một enum duy nhất.

Điểm quyết định là các điều kiện chuyển phải đọc **sự thật bền vững**. Client không được chọn bước tiếp theo bằng cách gửi step=PAYMENT_CONFIRMED.

### 4.3. Dữ liệu tối thiểu để tiếp tục an toàn

| Dữ liệu | Mục đích |
|---|---|
| workflowId, tenantId, ownerId | Định danh và giới hạn quyền theo đối tượng |
| orderRevision, snapshotHash hoặc snapshot bất biến | Ràng buộc thanh toán với đúng nội dung đã chốt |
| amount, currency | Đối chiếu số tiền thực tế và ngăn sửa giá |
| phase và trạng thái từng tài nguyên | Biết nghĩa vụ nào đã được tạo, nghĩa vụ nào chưa xong |
| paymentOperationId, providerReference | Đối soát đúng thao tác, tránh tạo lại khi chưa rõ kết quả |
| reservationId, reservationExpiresAt | Theo dõi tài nguyên được giữ và thời hạn hiệu lực |
| commandId hoặc idempotency key, fingerprint, receipt | Nhận diện request lặp và phát hiện cùng khóa nhưng khác nội dung |
| version | Chặn các command dựa trên ảnh chụp cũ |
| cancelRequestedAt, nextCheckAt, deadline | Điều phối hủy, đối soát và giới hạn thời gian chờ |
| audit và outbox | Lưu dấu quyết định và ý định thực hiện bước tiếp theo |

Không nhất thiết mọi trường nằm trong cùng một bảng. Chúng phải có quan hệ rõ ràng và được cập nhật theo những transaction bảo vệ các bất biến liên quan.

Session trong trình duyệt hoặc một biến trong worker không phải nguồn sự thật đủ bền vững cho những dữ liệu này.

## 5. Thiết kế theo các điểm có thể bị ngắt

Hãy đặt câu hỏi tại mỗi ranh giới ghi dữ liệu hoặc gọi hệ thống ngoài: nếu tiến trình dừng ngay tại đây, tiến trình mới sẽ biết điều gì và được phép làm gì?

| Điểm gián đoạn | Sự thật có thể tin cậy | Hành động phục hồi |
|---|---|---|
| Trước commit transaction tạo ý định | Chưa có ý định bền vững của lần thử đó | Gửi lại cùng command; kiểm tra tiền điều kiện |
| Sau commit, trước khi gửi ra ngoài | Đã có operation và outbox | Worker đọc lại ý định, tiếp tục đúng operation |
| Sau khi gửi, trước khi nhận response | Hiệu ứng có thể đã xảy ra | Đối soát hoặc retry cùng định danh theo hợp đồng nhà cung cấp |
| Sau thành công bên ngoài, trước khi ghi kết quả nội bộ | Nội bộ còn pending nhưng thế giới ngoài đã thay đổi | Khôi phục từ operationId/providerReference và bằng chứng được xác minh |
| Sau commit kết quả, trước khi trả response/ack | Kết quả nội bộ đã bền vững | Replay kết quả, không thực hiện thêm hiệu ứng |
| Sau khi reservation hết hạn, payment còn chưa rõ | Hàng có thể không còn được giữ; nghĩa vụ tài chính vẫn chưa rõ | Ngăn giao hàng theo reservation cũ, tiếp tục đối soát thanh toán |

Transaction nội bộ giúp phần dữ liệu cùng kho lưu trữ commit hoặc rollback cùng nhau. Nó không hoàn tác được hiệu ứng đã commit tại nhà cung cấp.

Một handler trong finally hoặc shutdown hook có thể hỗ trợ dọn dẹp, nhưng không thể là cơ chế duy nhất bảo vệ nghiệp vụ: mất điện, dừng cưỡng bức và mất liên lạc có thể khiến đoạn mã đó không chạy hoặc chạy không xong.

## 6. Ghi ý định trước, thực hiện hiệu ứng sau

### 6.1. Một transaction để chấp nhận command

Trước khi bắt đầu thanh toán, nên có transaction ghi đồng thời:

1. Workflow chuyển sang trạng thái đang chờ xử lý thanh toán.
2. Payment operation chứa số tiền, currency, revision và định danh cố định.
3. Outbox yêu cầu thực hiện operation đó.
4. Receipt của command được chấp nhận và audit tương ứng.

Nếu transaction rollback, không có worker hợp lệ nào được tạo hiệu ứng từ một ý định chưa commit. Nếu commit thành công rồi ứng dụng dừng, outbox vẫn cho phép tiếp tục.

Đây là lý do không nên gọi cổng thanh toán trước rồi mới tạo paymentOperationId trong cơ sở dữ liệu.

### 6.2. Java minh họa bước chấp nhận thanh toán

Mã dưới đây sử dụng các interface giả định để mô tả hợp đồng. Nó không phải một ứng dụng độc lập; các repository phải tham gia cùng transaction và khóa phải có hiệu lực đến hết transaction.

~~~java
PaymentAccepted requestPayment(Actor actor, PayCommand cmd) {
    return transactions.required(() -> {
        var workflow = workflows.lockForUpdate(
                actor.tenantId(), cmd.workflowId());
        access.requireCanOperate(actor, workflow);

        var scope = new CommandScope(
                actor.tenantId(), actor.id(), "REQUEST_PAYMENT");
        var fingerprint = fingerprints.of(
                cmd.workflowId(), cmd.expectedVersion(),
                cmd.orderRevision());

        var receipt = receipts.find(scope, cmd.idempotencyKey());
        if (receipt.isPresent()) {
            requireSameFingerprint(receipt.get(), fingerprint);
            return receipt.get().acceptedResult();
        }

        requireVersion(workflow, cmd.expectedVersion());
        requirePhase(workflow, RESERVED);
        requireRevision(workflow, cmd.orderRevision());
        requireSnapshotStillAuthorized(workflow, actor);
        requireReservationValid(workflow, clock.instant());
        requireNoUnresolvedPaymentOperation(workflow);

        var operationId = operationIds.next();
        var operation = PaymentOperation.requested(
                operationId,
                workflow.id(),
                workflow.orderSnapshot()); // Số tiền do server chốt.

        paymentOperations.insert(operation);
        workflow.markPaymentPending(operationId);
        workflows.save(workflow);
        outbox.insertPaymentRequested(operationId, workflow.id());

        var result = new PaymentAccepted(workflow.id(), operationId);
        receipts.insert(scope, cmd.idempotencyKey(), fingerprint, result);
        audit.insertPaymentRequested(actor, workflow, operationId);
        return result;
    });
}
~~~

Các điểm cần giữ đúng khi triển khai:

- Truy vấn workflow phải giới hạn tenant và đối tượng; biết workflowId không cấp quyền.
- Snapshot chứa dữ liệu nghiệp vụ đã chốt; không nhận tổng tiền thay thế từ client.
- Kiểm tra reservation phải được phối hợp với luồng hết hạn hoặc chuyển giữ chỗ, bằng khóa/version/cập nhật có điều kiện phù hợp. Chỉ so thời gian trên một bản ghi đã đọc cũ là chưa đủ.
- Phải có ràng buộc ngăn hai payment operation chưa được giải quyết cùng đại diện cho một ý định thanh toán, kể cả khi có request cạnh tranh.
- Receipt có unique constraint trên scope và key. Lỗi trùng phải làm rollback transaction thua; đọc lại receipt trong transaction mới để so nội dung.
- Transaction wrapper chỉ trả thành công ra ngoài sau khi commit. Accepted nghĩa là đã ghi nhận công việc, chưa có nghĩa là đã thanh toán.

Trong ví dụ, receipt được xử lý trước kiểm tra version và phase để một retry hợp lệ nhận lại kết quả đã lưu dù workflow đã đi xa hơn. Quyền truy cập hiện tại vẫn phải được kiểm tra trước khi trả receipt.

### 6.3. Worker phải tiếp tục đúng operation

Worker lấy thông tin từ operation đã lưu, không dựng lại amount từ giỏ hàng hiện tại và không tạo khóa thanh toán mới cho mỗi lần retry.

Một chu trình xử lý có thể gồm:

~~~text
Đọc operation đã commit
    → nhận quyền xử lý bằng cập nhật có điều kiện
    → ghi nhận bắt đầu dispatch
    → gọi nhà cung cấp với định danh ổn định
    → xác minh kết quả
    → commit kết quả nội bộ và ý định bước tiếp theo
~~~

Lời gọi mạng thường nằm ngoài transaction giữ khóa cơ sở dữ liệu lâu. Vì vậy cần chủ động xử lý khoảng trống giữa “đã ghi nhận bắt đầu dispatch” và “đã biết kết quả”.

Nếu worker timeout:

~~~text
operationId giữ nguyên
provider idempotency key giữ nguyên
amount, currency, orderRevision giữ nguyên
kết quả chuyển sang cần đối soát nếu còn chưa xác định
~~~

Không đổi định danh chỉ để thoát một lỗi timeout. Thời hạn lưu khóa idempotency của nhà cung cấp cũng là một phần của hợp đồng. Khi quá thời hạn đó, không được mặc định gửi lại khóa cũ vẫn có tác dụng chống trùng.

### 6.4. Ghi kết quả phải chống trùng và chống lùi trạng thái

Callback và worker đối soát có thể cùng nhận biết một kết quả. Handler ghi kết quả cần:

1. Xác minh nguồn và ràng buộc kết quả với đúng provider account, operation, số tiền, currency và đối tượng.
2. Khóa hoặc cập nhật có điều kiện trên payment operation/workflow liên quan.
3. Nếu kết quả đã được áp dụng, trả kết quả tương ứng mà không tạo thêm hiệu ứng.
4. Không để timeout hoặc phản hồi cũ ghi đè một kết quả thành công đã được xác nhận.
5. Ghi kết quả, audit, dấu đã xử lý và outbox cho bước tiếp theo trong cùng transaction.
6. Xét lại cancelRequested và tình trạng tài nguyên trước khi cho phép giao hàng.

Một phản hồi “pending” đến muộn không được đưa operation từ CONFIRMED quay lại PENDING. Một callback thành công đúng thao tác cũng không được bị bỏ qua chỉ vì người dùng đã đăng xuất: đó là sự thật tài chính phải được ghi nhận, rồi mới quyết định giao hàng hay hoàn tiền.

Worker sử dụng danh tính dịch vụ và quyền thực thi được giới hạn theo thiết kế. Nó không dựa vào việc phiên đăng nhập của người khởi tạo còn sống để quyết định có ghi nhận khoản tiền đã xảy ra hay không.

## 7. Resume, retry và cancellation là ba hành vi khác nhau

| Hành vi | Mục đích | Điều không được suy diễn |
|---|---|---|
| Resume | Tiếp tục từ trạng thái bền vững và bước hiện được phép | Không tự chứng minh các quyền hoặc phê duyệt cũ vẫn còn hiệu lực |
| Retry | Gửi lại cùng ý định sau lỗi tạm thời hoặc mất response | Không mặc định được tạo một operation bên ngoài mới |
| Cancel | Yêu cầu dừng phần chưa xảy ra và giải quyết nghĩa vụ đã phát sinh | Không có nghĩa mọi hiệu ứng trước đó đã được hoàn tác |

### 7.1. Resume phải được quyết định ở server

Endpoint resume nên đọc trạng thái hiện tại, kiểm tra quyền theo đối tượng và xác định hành động hợp lệ. Client có thể gửi ý định tiếp tục, nhưng không được tự khai rằng các bước trước đã hoàn tất.

Nếu dùng resume token:

- Token phải gắn với workflow, mục đích và phạm vi sử dụng phù hợp.
- Server vẫn kiểm tra quyền đối với workflow; token thông thường không thay thế xác thực.
- Token có hạn dùng và phải có cách vô hiệu hóa khi ngữ cảnh thay đổi.
- Token không cho phép sửa amount, revision hoặc nhảy phase.
- Token không nên làm lộ bí mật qua URL, log hoặc các nơi không cần biết.

Nếu sản phẩm chủ ý cho phép một capability token thay thế một phần xác thực, phải đặc tả rõ quyền mà token cấp, ai có thể dùng và cách thu hồi. Không vô tình biến một mã tiếp tục quy trình thành quyền thanh toán hoặc phê duyệt.

### 7.2. Phân biệt chứng cứ cũ và quyền cho hành động mới

Khi resume, cần quyết định theo từng bước:

- Một xác nhận thanh toán đã xảy ra vẫn là sự thật cần lưu giữ.
- Một phê duyệt gắn với revision cũ không cho phép xử lý nội dung mới.
- Quyền thực hiện bước tiếp theo phải được kiểm tra theo chính sách hiện hành.
- Một xác thực tăng cường đã quá thời hạn có thể phải làm lại trước hành động nhạy cảm.
- Receipt của command cũ có thể được trả lại cho người hiện có quyền xem, nhưng không tạo quyền thực hiện command mới.

Không “reset” toàn bộ workflow chỉ vì quyền hiện tại đã thay đổi. Việc đó có thể làm mất liên kết với khoản thanh toán hoặc reservation đã tồn tại.

### 7.3. Hủy khi payment đang chưa rõ kết quả

Giả sử người dùng bấm hủy trong lúc worker có thể đã gửi yêu cầu thu tiền. Quy trình phù hợp là:

~~~text
Ghi cancelRequested
    → chặn việc mở thêm bước giao hàng chưa được cam kết
    → xác định kết quả payment operation hiện có
    → nếu chưa thu và có thể kết thúc an toàn: hoàn tất hủy
    → nếu đã thu: tạo nghĩa vụ hoàn tiền
    → nếu chưa rõ: tiếp tục đối soát, không tuyên bố đã giải quyết xong
~~~

Có thể hủy ngay một operation còn chờ gửi nếu việc hủy và việc nhận quyền dispatch tranh chấp qua cùng cập nhật có điều kiện: bên hủy thắng thì worker không được bắt đầu gửi; bên dispatch thắng thì phải coi hiệu ứng là có khả năng đã xảy ra.

Chỉ kiểm tra “chưa gửi” rồi cập nhật CANCELLED bằng một lệnh rời rạc tạo ra cuộc đua: worker có thể gửi ngay giữa hai bước đó.

Nếu đã có worker được phép bắt đầu dispatch, việc lease hết hạn không chứng minh worker cũ sẽ không gọi nhà cung cấp nữa. Một kết quả truy vấn chưa thấy giao dịch cũng không nhất thiết loại bỏ lần gửi đến muộn. Muốn công bố hủy dứt khoát cần căn cứ ở hợp đồng nhà cung cấp, chẳng hạn trạng thái kết thúc ngăn thực thi thêm hoặc cơ chế hết hạn được phía có hiệu ứng thực thi; nếu chưa có căn cứ, giữ nghĩa vụ đối soát.

## 8. Hết hạn tài nguyên và chống chiếm giữ do bỏ dở

### 8.1. Thời hạn giữ tài nguyên phải độc lập với sự có mặt của client

Đóng trình duyệt không bảo đảm server nhận được một thông báo đáng tin cậy. Không dùng sự kiện đóng trang làm cơ chế duy nhất giải phóng hàng, mã giảm giá hay quota.

Mỗi loại giữ chỗ cần có:

- Thời điểm bắt đầu và hạn dùng do server xác lập.
- Quy tắc gia hạn và giới hạn gia hạn.
- Tiến trình thu hồi có thể chạy lại an toàn.
- Ràng buộc tránh vừa hết hạn vừa chuyển thành phân bổ thành công.
- Giới hạn tài nguyên mà một chủ thể được giữ cùng lúc.

TTL trong bảng chỉ là dữ liệu. Phải có cơ chế thực thi hết hạn và các command tiêu thụ reservation phải kiểm tra tính hợp lệ tại thời điểm quyết định.

### 8.2. Không kéo dài thời hạn bằng thao tác đọc

Nếu mỗi lần polling hoặc resume lại đặt expiresAt = now + TTL, người dùng có thể giữ tài nguyên vô hạn chỉ bằng cách gửi request định kỳ.

Một chính sách minh họa có thể là giữ hàng trong một khoảng thời gian cố định, cho phép số lần gia hạn hạn chế nếu đáp ứng điều kiện nghiệp vụ. Các con số phải dựa trên sản phẩm và khả năng vận hành; không có một TTL đúng cho mọi hệ thống.

Biện pháp chống lạm dụng có thể gồm quota theo tài khoản/tenant, giới hạn số workflow đang giữ chỗ, kiểm tra theo đối tượng và giới hạn tần suất. Rate limit một endpoint không thay thế được invariant về tổng tài nguyên đang bị giữ.

### 8.3. Hết hạn hàng không xóa nghĩa vụ tài chính

Nếu reservation hết hạn khi payment còn UNKNOWN, hệ thống có thể phải trả hàng về pool để bảo vệ khả năng phục vụ, theo chính sách đã chọn. Nhưng cần đồng thời lưu rằng đơn hiện không còn quyền giao hàng theo reservation cũ.

Nếu sau đó phát hiện đã thu tiền, chỉ có thể:

- Giữ lại hàng bằng một thao tác mới hợp lệ, nếu chính sách cho phép và vẫn đáp ứng nội dung đã chốt; hoặc
- Chuyển sang giải quyết/hoàn tiền.

Không tự tái chiếm một sản phẩm đã được phân bổ cho đơn khác và không xóa payment operation để coi như chưa có gì xảy ra.

## 9. Phục hồi bền vững và bù trừ

### 9.1. Checkpoint phải đi cùng thay đổi nghiệp vụ

Trường lastCompletedStep chỉ hữu ích nếu việc cập nhật nó nhất quán với dữ liệu mà bước đó tạo ra.

Hai cách ghi sau đều nguy hiểm:

~~~text
Ghi checkpoint = RESERVED
    → tiến trình dừng
    → chưa có reservation thực tế
~~~

~~~text
Tạo reservation
    → tiến trình dừng
    → checkpoint vẫn là OPEN
    → resume tạo thêm reservation
~~~

Nếu cùng cơ sở dữ liệu, hãy commit reservation, trạng thái workflow, audit và ý định bước tiếp theo trong cùng transaction. Nếu ở hệ thống khác nhau, cần operation có định danh, xử lý trùng và đối soát; thêm một cột step không tạo ra tính nguyên tử xuyên hệ thống.

### 9.2. Outbox và hàng đợi không loại bỏ việc thực thi lặp

Worker có thể ghi kết quả xong rồi dừng trước khi ack message. Hàng đợi sẽ giao lại message; publisher cũng có thể phát lại outbox.

Vì vậy cần phân biệt:

- eventId: danh tính một thông điệp/sự kiện.
- operationId: danh tính một hiệu ứng nghiệp vụ.
- attempt: một lần cố gắng thực thi operation.
- workflowId: danh tính toàn bộ quy trình.

Một operation có thể có nhiều attempt nhưng vẫn chỉ được tạo một hiệu ứng tương ứng theo hợp đồng. Nếu một event mới vô tình tạo operation mới sau mỗi lần retry, việc deduplicate theo eventId có thể chưa đủ.

### 9.3. Lease và fencing bảo vệ những phạm vi khác nhau

Lease giúp phân chia công việc giữa các worker, nhưng worker có thể chạy chậm hoặc tiếp tục sau khi lease hết hạn.

Đối với ghi dữ liệu nội bộ, có thể dùng version hoặc fencing token tăng đơn điệu để từ chối cập nhật của worker đã mất quyền sở hữu. Việc kiểm tra phải diễn ra tại tài nguyên được bảo vệ.

Đối với lời gọi bên ngoài, một fencing token chỉ lưu trong bảng của ứng dụng không ngăn được nhà cung cấp thực thi request từ worker cũ. Cần cơ chế phía nhà cung cấp như idempotency, điều kiện thực thi hoặc giao thức hủy/hết hạn phù hợp.

Không sử dụng việc “đã có distributed lock” làm bằng chứng duy nhất rằng không thể có lời gọi thanh toán trùng hoặc đến muộn.

### 9.4. Compensation là một nghiệp vụ mới

Bù trừ không phải lúc nào cũng trả thế giới thực về trạng thái ban đầu:

| Hiệu ứng đã xảy ra | Hành động phục hồi có thể cần |
|---|---|
| Giữ hàng nội bộ | Giải phóng reservation một lần, nếu chưa chuyển thành phân bổ |
| Đã thu tiền | Tạo yêu cầu hoàn tiền và theo dõi kết quả |
| Đã tạo vận đơn | Yêu cầu hủy nếu đơn vị giao hàng còn cho phép |
| Đã gửi hàng | Quy trình chặn giao hoặc đổi trả theo chính sách |
| Đã tiêu thụ mã giảm giá | Hoàn lại lượt theo chính sách, có kiểm soát chống sử dụng lại sai |

Mỗi compensation cần có tiền điều kiện, trạng thái, định danh, idempotency và audit riêng. Một refundOperationId phải được phân biệt với paymentOperationId gốc và tham chiếu về khoản cần hoàn; không dùng lẫn khóa của hai loại hiệu ứng.

Nếu bù trừ thất bại, lưu nghĩa vụ chưa hoàn tất và lên lịch xử lý lại có giới hạn. Không đánh dấu toàn bộ workflow đã giải quyết chỉ vì đã phát yêu cầu bù trừ.

### 9.5. Đối soát là một phần của thiết kế

Một tiến trình đối soát có thể tìm các operation pending/unknown quá ngưỡng, kiểm tra kết quả bên ngoài và áp dụng transition hợp lệ. Nó cần:

- nextCheckAt, khoảng nghỉ tăng dần và độ ngẫu nhiên thích hợp để tránh nhiều worker đồng loạt gửi lại.
- Giới hạn số lần và thời gian tự động xử lý theo hợp đồng phụ thuộc.
- Cơ chế nhận quyền xử lý và chống áp dụng kết quả trùng.
- Đường chuyển sang xử lý thủ công khi không thể kết luận an toàn.
- Quy tắc lưu chứng cứ và định danh đủ lâu cho thời hạn truy vấn, gửi lại và callback.

Chuyển sang xử lý thủ công không được ngầm xóa nghĩa vụ tài chính hoặc cho phép tạo payment mới. Người vận hành cũng cần thao tác có kiểm tra quyền, version và audit; tránh một nút “reset về đầu” có thể gây thu tiền lại.

## 10. Kiểm thử bằng cách chủ động làm gián đoạn

Không chỉ kiểm tra đường chạy thành công. Hãy chọn các ranh giới mà một bên đã có thể commit nhưng bên khác chưa biết, rồi dừng hoặc gây lỗi có kiểm soát.

### 10.1. Ma trận tình huống

| Tình huống | Điều phải kiểm chứng |
|---|---|
| Đóng trình duyệt sau khi command đã commit | Công việc vẫn có thể được tìm thấy và phục hồi; không phụ thuộc session phía client |
| Tiến trình dừng trước commit tạo operation | Không có ý định/outbox nửa vời của lần thử và không phát sinh lời gọi ngoài từ dữ liệu chưa commit |
| Dừng sau commit outbox, trước dispatch | Worker mới tiếp tục đúng operation đã lưu |
| Nhà cung cấp thu tiền rồi làm mất response | Operation được đối soát hoặc retry cùng định danh; không tạo khoản thu độc lập |
| Ghi kết quả xong nhưng chưa ack queue | Message giao lại không tạo thêm fulfillment hoặc thay đổi bộ đếm lần nữa |
| Hai request resume cùng lúc | Chỉ các transition hợp lệ được chấp nhận; không nhân đôi reservation/operation |
| Resume từ tenant hoặc owner khác | Không đọc hoặc điều khiển được workflow |
| Sửa số tiền/revision trong request tiếp tục | Không thể dùng phê duyệt hay payment của snapshot cũ cho nội dung mới |
| Hủy tranh chấp với dispatch | Bên thắng được xác định bằng cơ chế nhất quán; nếu hiệu ứng có thể xảy ra thì chưa công bố hủy dứt khoát |
| Reservation hết hạn khi payment unknown | Không giao hàng theo reservation đã hết hạn; vẫn lưu nghĩa vụ đối soát |
| Callback thành công đến sau yêu cầu hủy | Ghi nhận sự thật thanh toán và mở nhánh giải quyết phù hợp; không tự giao hàng |
| Callback pending đến sau confirmed | Không làm lùi trạng thái hoặc tạo lại operation |
| Quyền thao tác bị thu hồi trong lúc gián đoạn | Chặn hành động mới theo chính sách; vẫn xử lý chứng cứ của hiệu ứng đã xảy ra |
| Polling/resume liên tục | Không tự gia hạn tài nguyên vô hạn |
| Dùng lại khóa cũ với payload khác | Báo xung đột, không thực hiện ý định mới |
| Worker cũ chạy tiếp sau khi mất lease | Không ghi đè trạng thái mới; hiệu ứng ngoài vẫn được bảo vệ ở ranh giới nhà cung cấp |
| Bù trừ thất bại hoặc message hoàn tiền bị giao lại | Nghĩa vụ còn được theo dõi; không hoàn tiền trùng |

### 10.2. Một kiểm thử có sức phân biệt lỗi

Dùng một cổng thanh toán giả lập có trạng thái độc lập với cơ sở dữ liệu ứng dụng:

~~~text
1. Tạo đơn revision 7, tổng tiền 500000 VND, giữ hàng hợp lệ.
2. Chấp nhận payment operation P và commit outbox.
3. Fake provider ghi nhận thành công cho P.
4. Ngắt response trước khi ứng dụng ghi nhận kết quả.
5. Khởi động worker khác và gửi lại command với cùng khóa.
6. Cho tiến trình đối soát truy vấn hoặc thực thi lại theo cùng định danh P.
7. Đọc trạng thái từ một transaction mới.
~~~

Kết quả cần quan sát:

- Nhà cung cấp chỉ có một hiệu ứng thu tiền tương ứng với P.
- Ứng dụng tham chiếu đúng P và revision 7.
- Số tiền/currency khớp snapshot.
- Không có payment operation mới chỉ vì timeout.
- Bước giao hàng chỉ được mở nếu tài nguyên và chính sách hiện tại cho phép.
- Audit phản ánh được lần gửi, sự gián đoạn và cách kết quả được phục hồi.

Chỉ mock hàm charge rồi cho lần gọi đầu ném exception không chứng minh được tình huống “đã thu tiền nhưng mất response”. Fake provider phải thực sự ghi hiệu ứng trước khi mô phỏng mất liên lạc.

### 10.3. Kiểm thử cạnh tranh phải điều phối đúng điểm

Đối với cuộc đua cancel/dispatch:

1. Chuẩn bị operation đã commit nhưng chưa được nhận xử lý.
2. Dùng hai transaction/kết nối độc lập cho cancel và claim dispatch.
3. Điều phối để cả hai cạnh tranh trên cùng trạng thái/version.
4. Chạy riêng cả trường hợp cancel thắng và dispatch thắng.
5. Kiểm tra trường hợp cancel thắng không có dispatch hợp lệ; trường hợp dispatch thắng đi qua nhánh chờ kết quả/đối soát khi cần.

Với worker đã bắt đầu gửi, kiểm tra thêm tình huống worker cũ bị treo rồi chạy tiếp. Không kết luận an toàn chỉ từ việc lease trong cơ sở dữ liệu đã được cấp cho worker mới.

### 10.4. Kiểm tra cả khả năng phục hồi và khả năng chống lạm dụng

Một workflow có thể không làm sai số tiền nhưng vẫn bị lạm dụng để làm cạn tài nguyên. Kiểm thử thêm:

- Tạo nhiều workflow bỏ dở có chạm quota giữ chỗ không?
- Có endpoint phụ nào gia hạn hoặc tạo thêm reservation ngoài quy tắc chung không?
- Một tài khoản có thể tái tạo workflow ngay khi hết hạn để giữ mãi cùng tài nguyên không?
- Quá nhiều operation unknown có làm nghẽn toàn bộ worker không?
- Đối soát có tiếp tục hoạt động sau khi ứng dụng khởi động lại hoặc triển khai phiên bản mới không?

Các tình huống này liên quan trực tiếp đến bảo vệ logic nghiệp vụ, vì tài nguyên bị giữ phải phục vụ đúng chủ thể, đúng thời hạn và đúng mục đích.

## 11. Quan sát để phát hiện workflow mắc kẹt

Theo dõi tối thiểu:

- Tuổi của workflow và operation trong các trạng thái pending/unknown.
- Số reservation đã quá hạn nhưng chưa được thu hồi hoặc xử lý.
- Số lần retry trên mỗi operation và số lần xung đột idempotency.
- Khoản thanh toán xác nhận thành công nhưng chưa có nhánh thực hiện đơn hoặc hoàn tiền.
- Compensation thất bại, callback trễ/trùng và kết quả bị từ chối vì không khớp dữ liệu.
- Số workflow bị bỏ dở và tổng tài nguyên đang giữ theo tài khoản/tenant.

Log và audit nên liên kết workflowId, operationId, eventId, attempt và version. Không ghi thông tin thanh toán nhạy cảm, thông tin xác thực hoặc toàn bộ resume token chỉ để thuận tiện truy vết.

Thông báo người dùng cần phản ánh đúng sự thật, ví dụ: “Yêu cầu đã được nhận, đang xác nhận thanh toán” hoặc “Đã nhận yêu cầu hủy, đang xác định nghĩa vụ hoàn tiền”. Một dòng “Thất bại, hãy thanh toán lại” là không phù hợp khi kết quả bên ngoài còn chưa xác định.

## 12. Các dấu hiệu cần xem lại trong thiết kế

| Dấu hiệu | Rủi ro |
|---|---|
| Chỉ lưu tiến độ trong session hoặc bộ nhớ worker | Không thể tiếp tục đáng tin cậy sau restart hoặc đổi phiên |
| Timeout luôn chuyển về bước đầu | Tạo lại hiệu ứng có thể đã xảy ra |
| Gọi nhà cung cấp trước khi lưu operation | Có hiệu ứng ngoài nhưng thiếu định danh bền vững để đối soát |
| Một khóa mới cho mỗi lần retry | Cơ chế chống trùng không còn nhận ra cùng ý định |
| Đổi workflow thành CANCELLED trước khi biết nghĩa vụ | Che giấu khoản thu hoặc khoản hoàn chưa giải quyết |
| Mọi lần resume đều gia hạn TTL | Tạo đường giữ tài nguyên vô hạn |
| Tin step/status từ client | Cho phép nhảy bước hoặc khôi phục ngữ cảnh đã hết hiệu lực |
| Mặc định lease ngăn mọi worker cũ | Bỏ sót hiệu ứng đến muộn tại hệ thống ngoài |
| Xóa workflow bỏ dở khi còn operation unknown | Mất dữ liệu đối soát và bằng chứng nghiệp vụ |
| “Reset thủ công” không có kiểm soát | Đường vận hành trở thành cách vượt state machine |

## 13. Bài tập tình huống

Một đơn đã giữ sản phẩm cuối cùng trong kho. Worker gửi payment operation P; cổng thanh toán thu tiền nhưng response bị mất. Người dùng bấm hủy, reservation hết hạn, rồi callback thành công đến.

Hãy xác định:

1. Sau timeout, trạng thái nào thể hiện đúng mức độ chắc chắn?
2. Khi nhận hủy, hệ thống phải lưu thêm ý định gì và ngăn bước nào?
3. Reservation hết hạn có cho phép xóa P hoặc coi thanh toán thất bại không?
4. Callback cần được đối chiếu với những dữ liệu nào?
5. Nếu sản phẩm đã được bán cho đơn khác, quy trình phải mở nghĩa vụ gì?
6. Khi callback được gửi lại, những hiệu ứng nào không được lặp?
7. Nếu yêu cầu hoàn tiền cũng timeout, cần giữ định danh và trạng thái nào?

Một lời giải phù hợp phải giữ P xuyên suốt, ghi nhận thanh toán đã xảy ra, không giao hàng dựa trên reservation cũ và tạo/theo dõi nghĩa vụ hoàn tiền nếu không thể thực hiện đơn. “Quay lại OPEN rồi thử lại” không bảo vệ được các sự thật đã phát sinh.

## 14. Khung rà soát một workflow có thể bị ngắt

Trước khi triển khai, hãy viết rõ cho từng bước:

~~~text
Bước và đối tượng:
Tiền điều kiện, quyền và revision:
Thay đổi nội bộ cần commit cùng nhau:
Hiệu ứng ngoài hệ thống:
Định danh ổn định của hiệu ứng:
Bằng chứng thành công hoặc thất bại dứt khoát:
Cách biểu diễn kết quả chưa xác định:
Hành vi khi retry/resume/cancel:
Tài nguyên đang giữ và thời hạn:
Quy tắc xử lý worker cũ và message trùng:
Bù trừ hoặc đối soát:
Ca kiểm thử gián đoạn:
~~~

Một quy trình chịu được gián đoạn phải có câu trả lời dựa trên dữ liệu đã lưu và hợp đồng thực thi. Việc client còn mở trang, worker còn sống hay request có nhận được response không phải bằng chứng đủ để quyết định rằng tiền, hàng hoặc quyền phê duyệt đang ở trạng thái nào.
