# Tác nhân khách hàng đã xác thực — Authenticated customer actor

## 1. Đã xác thực mới trả lời được một phần câu hỏi bảo mật

Trong chương **Actor Model** của học phần **Business Logic Security**, một **actor** là chủ thể thực hiện hoặc khởi phát hành động có ảnh hưởng đến nghiệp vụ. Actor có danh tính, quan hệ với đối tượng, phạm vi hoạt động và các điều kiện chi phối quyền của mình.

**Authenticated customer actor** là khách hàng mà hệ thống đã xác thực danh tính theo cơ chế được chấp nhận. Ví dụ, một phiên đăng nhập hợp lệ được ánh xạ tới tài khoản nội bộ và hồ sơ khách hàng đang hoạt động trong một tenant cụ thể.

Điều đó chưa chứng minh khách hàng được phép:

- Đọc hoặc thay đổi bất kỳ đơn hàng nào có ID hợp lệ.
- Chọn giá thanh toán, trạng thái đã trả tiền hoặc số tiền được hoàn.
- Chuyển đơn của mình sang trạng thái giao hàng tùy ý.
- Dùng quyền sở hữu để bỏ qua bước kiểm tra hoặc phê duyệt.
- Tạo lại cùng quyền lợi bằng nhiều request hoặc nhiều khóa khác nhau.

Mục tiêu của bài học là mô hình hóa khách hàng đã xác thực như một chủ thể có quyền **giới hạn theo đối tượng, hành động và ngữ cảnh**, đồng thời có thể cố ý lạm dụng các chức năng mình được sử dụng. Đây là nền tảng để áp dụng business invariant, state machine, transaction và idempotency đúng ranh giới.

Sau bài này, bạn cần có khả năng:

- Phân biệt danh tính đăng nhập, tài khoản, hồ sơ khách hàng và tenant.
- Xây dựng actor context từ nguồn đáng tin cậy thay vì tin trường do client khai.
- Kiểm tra quyền theo đối tượng cùng điều kiện nghiệp vụ của hành động.
- Nhận diện các tình huống chính khách hàng sở hữu hợp lệ vẫn có thể lạm dụng.
- Thiết kế và kiểm thử một thao tác tự phục vụ không cho phép mở rộng quyền ngoài ý định.

## 2. Phân biệt các định danh trong mô hình khách hàng

Một chuỗi `userId` thường bị dùng cho nhiều khái niệm khác nhau. Điều này dễ làm quyền bị suy diễn sai.

| Khái niệm | Ý nghĩa | Điều không được tự suy ra |
| --- | --- | --- |
| Danh tính đã xác thực | Chủ thể được cơ chế xác thực nhận diện | Mọi hồ sơ có cùng email đều thuộc chủ thể đó |
| Tài khoản nội bộ | Bản ghi tài khoản của ứng dụng | Tài khoản có quyền trên mọi tenant |
| Hồ sơ khách hàng | Đối tượng dùng để sở hữu đơn, giỏ hàng hoặc quan hệ kinh doanh | Bất kỳ ai biết mã khách hàng đều có quyền đại diện |
| Tenant | Ranh giới tổ chức hoặc phạm vi dữ liệu theo thiết kế | Client chọn tenant nào cũng được |
| Phiên hoặc credential | Phương tiện xác thực một lần gọi hoặc một phiên làm việc | Mọi quyền tại lúc cấp còn đúng vô thời hạn |
| Quan hệ đại diện | Quyền hành động thay chủ thể khác trong phạm vi cụ thể | Có quyền đại diện cho mọi hành động và mọi tài sản |

Nếu dùng nhà cung cấp danh tính bên ngoài, ánh xạ cần dựa trên định danh ổn định trong đúng phạm vi nhà cung cấp. Không tự liên kết hai tài khoản chỉ vì email giống nhau, nếu chưa có một quy trình liên kết đủ tin cậy.

Email và số điện thoại có thể thay đổi, được tái cấp hoặc tồn tại trong nhiều quan hệ. Chúng là dữ kiện liên hệ, không phải bằng chứng quyền sở hữu bất biến cho mọi giao dịch lịch sử.

### 2.1. Một người có thể có nhiều ngữ cảnh khách hàng

Ví dụ, chủ thể U1 có:

~~~text
Tài khoản nội bộ: A1
Tenant T1: khách hàng cá nhân C42
Tenant T2: người mua được ủy quyền cho khách hàng doanh nghiệp C88
~~~

U1 có thể được mua hàng cho C88 nhưng không được thay tài khoản nhận hoàn tiền hoặc quản lý người đại diện của doanh nghiệp. Việc chọn C88 làm ngữ cảnh không làm U1 trở thành chủ sở hữu toàn quyền.

Thiết kế cần xác định actor đang hành động với tư cách nào. Nếu API cho chọn tenant hoặc hồ sơ khách hàng, lựa chọn đó chỉ là đầu vào đề nghị; máy chủ phải kiểm tra quan hệ và phạm vi hành động trước khi tạo actor context có hiệu lực.

### 2.2. Tách người khởi phát và chủ thể được đại diện

Trong tác vụ thay mặt khách hàng, cần lưu được ít nhất:

- Ai là người thực sự khởi phát?
- Đang hành động cho hồ sơ khách hàng nào?
- Quyền đại diện đến từ đâu và bao phủ hành động nào?
- Dịch vụ nào thực thi phần việc phía sau?

Một service account xử lý message không được tự coi mình là khách hàng rồi kế thừa mọi quyền. Ngược lại, một khách hàng không được truyền `onBehalfOf` tùy ý để mượn quyền của người khác.

Đối với khách hàng tự phục vụ trực tiếp, mô hình có thể đơn giản hơn. Khi bổ sung đại diện hoặc hỗ trợ khách hàng, phải mở rộng chính sách rõ ràng thay vì bỏ điều kiện sở hữu để luồng mới chạy được.

## 3. Xây dựng actor context từ ranh giới xác thực đáng tin cậy

Một actor context minh họa:

~~~text
ActorContext
  subjectId
  accountId
  activeTenantId
  effectiveCustomerId
  sessionReference
  authenticationContext
  relationshipReference
~~~

Không bắt buộc phải có đúng các trường này. Mục tiêu là phân biệt dữ kiện đã xác minh với dữ liệu yêu cầu.

### 3.1. Luồng xây dựng context

1. Xác thực phiên hoặc credential theo cơ chế của ứng dụng.
2. Xác định danh tính và tài khoản nội bộ được ánh xạ.
3. Kiểm tra trạng thái tài khoản theo chính sách của hành động.
4. Xác minh quyền truy cập tenant đang chọn.
5. Xác minh quan hệ với hồ sơ khách hàng hiệu lực.
6. Cung cấp context cho lớp nghiệp vụ qua một ranh giới được kiểm soát.

Client có thể gửi `orderId`, số lượng muốn mua hoặc lý do hủy. Client không được tự quyết định `authenticated=true`, `isOwner=true`, `role=MANAGER` hay hạn mức tiền của actor.

Một token có cấu trúc đọc được không đồng nghĩa đã được xác minh. Việc lấy một claim ra khỏi chuỗi rồi dùng nó làm danh tính phải nằm sau bước xác thực đầy đủ theo cơ chế được chấp nhận, không chỉ sau thao tác giải mã dữ liệu.

### 3.2. Context đáng tin cậy không đồng nghĩa mọi thuộc tính luôn mới

Quyền thành viên, trạng thái tài khoản hoặc quan hệ đại diện có thể thay đổi sau khi phiên được tạo. Thiết kế cần quy định điều kiện nào được chốt và điều kiện nào cần kiểm tra lại.

Ví dụ:

- Tài khoản bị hạn chế chi tiêu có thể vẫn được xem lịch sử hoặc gửi yêu cầu hỗ trợ.
- Quyền đại diện bị thu hồi không nên tiếp tục cho phép tạo lệnh mới chỉ vì token còn hạn.
- Hành động nhạy cảm có thể cần ngữ cảnh xác thực mới hơn hoặc xác nhận bổ sung theo chính sách.

Không dùng một nhánh “tài khoản đã đăng nhập thì cho phép tất cả” hoặc “bị hạn chế thì cấm mọi thao tác” thay cho chính sách hành động cụ thể.

Nếu cache quyền, phải biết thời gian dữ liệu có thể cũ và cơ chế vô hiệu hóa. Khi một điều kiện bắt buộc yêu cầu hiệu lực hiện tại, dữ liệu cũ không tự trở thành bằng chứng đủ chỉ vì nó nằm trong token hoặc cache nội bộ.

### 3.3. Không để cơ chế HTTP thay thế quyền nghiệp vụ

Một request có phiên hợp lệ vẫn có thể là request bị giả mạo hoặc được gửi từ một luồng không mong muốn. Cần cơ chế bảo vệ phù hợp với cách mang credential, chẳng hạn chống giả mạo yêu cầu đối với các thao tác dùng cookie phiên.

Tuy nhiên, kể cả request do chính khách hàng chủ động gửi, mọi quyền theo đối tượng và điều kiện nghiệp vụ vẫn phải được thực thi. Bảo vệ kênh gọi không thay thế việc kiểm tra khách hàng đang định làm gì.

## 4. Mô tả quyền bằng hành động và đối tượng

Một vai trò chung như `CUSTOMER` thường chỉ đủ để mở cổng vào nhóm chức năng. Nó không diễn tả hết quyền trong nghiệp vụ.

| Đối tượng | Hành động khách hàng có thể được phép | Điều kiện minh họa |
| --- | --- | --- |
| Giỏ hàng | Xem, thêm hoặc đổi số lượng | Đúng khách hàng, đúng tenant, sản phẩm còn được bán, giới hạn số lượng hợp lệ |
| Đơn hàng | Xem chi tiết | Có quan hệ được phép xem, lọc đúng dữ liệu cần hiển thị |
| Địa chỉ giao | Đề nghị thay đổi | Đúng đơn và chưa vượt mốc xử lý được phép; có thể phải tính lại điều kiện giao hàng |
| Thanh toán | Khởi tạo hoặc thử lại theo quy trình | Đúng đơn, giá do máy chủ chốt, trạng thái cho phép, không tạo tác động trùng |
| Hủy đơn | Gửi yêu cầu hủy | Đúng đối tượng, đúng trạng thái và điều kiện chính sách |
| Trả hàng | Gửi yêu cầu cho dòng hàng đủ điều kiện | Quan hệ dòng hàng đúng, số lượng còn quyền trả, trong điều kiện áp dụng |
| Hoàn tiền | Theo dõi hoặc yêu cầu theo luồng | Không tự quyết định số tiền hoặc tự thực hiện phê duyệt dành cho bên khác |

Cụm “của tôi” phải được chuyển thành một quan hệ dữ liệu cụ thể. Với mô hình sở hữu trực tiếp, có thể kiểm tra:

~~~text
order.tenantId == actor.activeTenantId
order.customerId == actor.effectiveCustomerId
~~~

Với khách hàng doanh nghiệp hoặc đại diện, quan hệ có thể phức tạp hơn: thành viên được phân công, quyền trên chi nhánh, giá trị giao dịch hoặc loại thao tác. Khi đó cần chính sách quan hệ tương ứng; không áp đặt một phép so ID đơn giản rồi mở rộng bằng ngoại lệ thiếu kiểm soát.

### 4.1. Kiểm tra quan hệ giữa các ID trong cùng yêu cầu

Sở hữu `orderId` không chứng minh mọi `lineItemId`, `paymentId`, `addressId` hoặc `returnCaseId` đi kèm đều thuộc đơn đó.

Cần kiểm tra đồng thời:

~~~text
đúng tenant
đúng khách hàng hoặc quan hệ được phép
đúng quan hệ cha - con
đúng hành động
đúng trạng thái
~~~

Một khách hàng có thể sở hữu cả hai đơn nhưng vẫn không được ghép khoản thanh toán của đơn thứ nhất với yêu cầu hoàn của đơn thứ hai. Quyền sở hữu từng đối tượng riêng lẻ chưa chứng minh tổ hợp đối tượng hợp lệ.

### 4.2. Không cho endpoint cập nhật chung mở rộng quyền

Một endpoint nhận nguyên entity để cập nhật có thể vô tình cho sửa:

- `customerId`, `tenantId` hoặc quan hệ sở hữu.
- Giá đã chốt, phần giảm giá hoặc số tiền được hoàn.
- `paid=true`, `approved=true` hoặc trạng thái vận chuyển.
- Người phê duyệt, hạn mức hoặc tham chiếu quyết định.

Nên dùng command hoặc DTO theo hành động, chỉ nhận trường khách hàng được đề nghị thay đổi. Việc có danh sách trường cho phép vẫn phải đi kèm kiểm tra giá trị, trạng thái và ảnh hưởng nghiệp vụ; không phải mọi giá trị của một trường được phép đều hợp lệ.

## 5. Khách hàng hợp lệ vẫn là một nguồn rủi ro logic

Khách hàng có thể thao tác qua giao diện, ứng dụng di động hoặc API tự động. Máy chủ không nên giả định trình tự màn hình là ràng buộc bảo mật.

Các hành vi cần được mô hình hóa gồm:

- Gọi chức năng chưa được hiển thị trong trạng thái hiện tại.
- Thay ID sang đối tượng khác, kể cả đối tượng cùng sở hữu.
- Gửi tổng tiền, giảm giá hoặc trạng thái đã sửa.
- Chia một thao tác lớn thành nhiều thao tác nhỏ để vượt hạn mức tổng.
- Gửi song song nhiều yêu cầu cùng tiêu thụ một quyền lợi.
- Dùng nhiều khóa idempotency cho cùng một ý định nghiệp vụ.
- Phối hợp mua, nhận ưu đãi, hủy và hoàn để nhận quyền lợi vượt chính sách.
- Gọi lại endpoint cũ hoặc đường xử lý khác có kiểm tra yếu hơn.

Đó có thể là lỗi vô ý do retry hoặc là hành vi có chủ đích. Các invariant quan trọng phải đúng trong cả hai trường hợp; không chỉ bật kiểm tra khi hệ thống đánh giá một người dùng có vẻ đáng ngờ.

### 5.1. Sở hữu hợp lệ không mở quyền quyết định giá hoặc lợi ích

Khách hàng được chọn sản phẩm và số lượng theo chính sách. Máy chủ quyết định giá được áp dụng, phần giảm giá, phí, thuế theo mô hình của sản phẩm và số tiền phải thanh toán.

Khách hàng được đề nghị trả hàng không đồng nghĩa được đặt số tiền hoàn. Quyền hoàn phải được tính từ giao dịch đã chốt, số lượng đủ điều kiện và các khoản đã hoàn hoặc đang giữ.

Khách hàng được dùng ưu đãi không đồng nghĩa được tự xác định mình là “khách mới” hoặc tự tăng hạn mức chiến dịch. Nếu chính sách dùng một khái niệm rộng hơn tài khoản, mô hình cần thể hiện điều đó; một tài khoản mới không tự chứng minh một chủ thể kinh doanh mới.

### 5.2. Tách lệnh đề nghị khỏi quyết định có thẩm quyền

Có thể phân biệt các hành động:

~~~text
REQUEST_CANCELLATION
APPROVE_CANCELLATION
EXECUTE_REFUND
CONFIRM_REFUND_RESULT
~~~

Một sản phẩm có thể tự động duyệt hủy khi đủ điều kiện, nhưng quyết định tự động vẫn phải do chính sách phía máy chủ đưa ra. Không cho khách hàng gọi một endpoint phê duyệt dành cho nhân viên chỉ vì đó là bước tiếp theo trong workflow.

Nếu quy trình yêu cầu người đề nghị không tự duyệt, actor khách hàng không được mượn vai trò khác hoặc truyền `approverId` để làm điều đó. Phân tách nhiệm vụ cần được kiểm tra theo danh tính và quan hệ mà chính sách quy định.

## 6. Tình huống xuyên suốt: khách hàng yêu cầu hủy đơn

Xét chính sách minh họa:

- Chủ thể U1 đang hành động trực tiếp cho khách hàng C42 trong tenant T1.
- Đơn O810 thuộc C42 và đang ở trạng thái `CONFIRMED`.
- Tổng thanh toán đã được máy chủ chốt là 800.000 VND.
- Khách được yêu cầu hủy khi đơn chưa chuyển sang `FULFILLMENT_STARTED`.
- Máy chủ đánh giá điều kiện và số tiền dự kiến xử lý theo chính sách.
- Chấp nhận yêu cầu hủy tạo trạng thái `CANCELLATION_PENDING`, không tự chứng minh đã hoàn tiền.
- Một quyết định hủy cụ thể không được tạo nhiều lệnh hoàn nghiệp vụ.

Yêu cầu có thể chỉ chứa:

~~~json
{
  "orderId": "O810",
  "expectedOrderRevision": 7,
  "reasonCode": "CUSTOMER_CHANGED_MIND",
  "idempotencyKey": "request-key-created-for-this-intent"
}
~~~

Actor và tenant có hiệu lực được xác định qua ngữ cảnh đã xác minh. API không cần tin một `customerId` hoặc `refundAmount` do client gửi.

### 6.1. Ba yêu cầu khác nhau đều có thể trông hợp lệ

| Yêu cầu | Vì sao chưa được chấp nhận ngay? |
| --- | --- |
| U1 yêu cầu hủy O999 của khách hàng khác | Đã xác thực nhưng không có quyền trên đối tượng |
| U1 yêu cầu hủy O810 sau khi bắt đầu xử lý giao | Có quyền trên đơn nhưng trạng thái không còn cho phép |
| U1 gửi lại yêu cầu hủy O810 nhiều lần | Ý định có thể hợp lệ nhưng không được nhân số quyết định hoặc tác động |

Một phép kiểm tra vai trò `CUSTOMER` không giải quyết được ba trường hợp này. Một phép kiểm tra sở hữu cũng chưa giải quyết được hai trường hợp sau.

### 6.2. Invariant cho luồng hủy

~~~text
Actor phải có quyền yêu cầu hủy đúng đơn trong đúng tenant.
Lý do hủy phải thuộc tập và điều kiện được chính sách chấp nhận.
Nội dung đã chốt của đơn không do request hủy tự thay đổi.
Hủy và bắt đầu xử lý giao không được cùng thắng từ một trạng thái xung đột.
Một quyết định hủy chỉ tạo số tác động tài chính được phép.
Tổng hoàn thành công và đang giữ không vượt quyền hoàn liên quan.
Kết quả trả về phải phản ánh đúng bước đã hoàn tất.
~~~

Nếu chính sách cho hủy một phần hoặc chỉ cho hủy một số dòng hàng, cần invariant theo dòng hàng và số lượng. Bài này dùng hủy toàn đơn để làm rõ ranh giới actor.

### 6.3. State machine cần được mọi actor tuân thủ

~~~mermaid
stateDiagram-v2
    [*] --> CONFIRMED
    CONFIRMED --> CANCELLATION_PENDING: Khách yêu cầu và chính sách cho phép
    CONFIRMED --> FULFILLMENT_STARTED: Luồng xử lý giao giành quyền thực hiện
    CANCELLATION_PENDING --> CANCELLED: Quy trình hủy hoàn tất
    FULFILLMENT_STARTED --> FULFILLED: Hoàn tất xử lý giao
~~~

Trong chính sách minh họa, không có chuyển trực tiếp từ `FULFILLMENT_STARTED` sang `CANCELLED` bằng lệnh tự phục vụ này. Nếu sản phẩm có quy trình can thiệp riêng, cần thiết kế hành động, thẩm quyền và điều kiện riêng.

Luồng giao hàng phải cùng kiểm tra trạng thái và cơ chế tranh chấp với luồng hủy. Chỉ khóa ở phía khách hàng trong khi worker giao hàng bỏ qua khóa vẫn có thể làm cả hai cùng tạo tác động.

Trạng thái hủy đơn và trạng thái hoàn tiền có thể được quản lý riêng. Nếu hoàn tiền đang chờ, không trả `REFUNDED` chỉ vì đã tiếp nhận hủy.

## 7. Minh họa Java tại ranh giới nghiệp vụ

Đoạn mã sau là **mã khung kiến trúc**, chưa phải ứng dụng chạy độc lập. Ví dụ chỉ áp dụng cho khách hàng sở hữu trực tiếp; quyền đại diện doanh nghiệp cần chính sách quan hệ mở rộng.

~~~java
record CancelOrderCommand(
        String orderId,
        long expectedOrderRevision,
        String reasonCode,
        String idempotencyKey) {}

record CancellationReceipt(
        String cancellationId,
        String status) {}

public CancellationReceipt requestCancellation(
        CustomerActor actor,
        CancelOrderCommand command) {

    validateCommand(command);

    return transactions.required(() -> {
        var order = orders.lockByTenantAndCustomer(
                actor.tenantId(),
                actor.customerId(),
                command.orderId());

        permissions.requireCurrentCancellationCapability(actor, order);

        var scope = new IdempotencyScope(
                actor.tenantId(),
                actor.subjectId(),
                actor.customerId(),
                "REQUEST_CANCELLATION");

        var fingerprint = fingerprints.forCancellation(command);
        var replay = idempotency.claimOrReplay(
                scope, command.idempotencyKey(), fingerprint);

        if (replay.isPresent()) {
            return replay.get();
        }

        order.requireRevision(command.expectedOrderRevision());

        var assessment = cancellationPolicy.assessCustomerRequest(
                actor,
                order,
                command.reasonCode(),
                serverClock.instant());

        assessment.requireAllowed();

        var cancellation = cancellations.createUniqueForDecision(
                order.id(),
                assessment.decisionSnapshot(),
                command.reasonCode());

        order.markCancellationPending(cancellation.id());
        orders.save(order);
        outbox.appendCancellationRequested(cancellation.id());

        var result = new CancellationReceipt(
                cancellation.id(), "CANCELLATION_PENDING");

        idempotency.complete(scope, command.idempotencyKey(), result);
        return result;
    });
}
~~~

Các hợp đồng bắt buộc:

1. `CustomerActor` được tạo từ ngữ cảnh xác thực và quan hệ khách hàng đã kiểm chứng. Không deserialize trực tiếp kiểu này từ request rồi coi là đáng tin cậy.
2. `lockByTenantAndCustomer` chỉ tải đơn phù hợp với tenant và khách hàng của mô hình sở hữu trực tiếp, đồng thời khóa hoặc bảo vệ phiên bản theo transaction. Nếu không tìm được, lớp API trả lỗi theo quy ước không tiết lộ dữ liệu trái quyền.
3. `requireCurrentCancellationCapability` kiểm tra những điều kiện quyền hiện hành mà chính sách yêu cầu. Một vai trò chụp từ phiên cũ không tự đáp ứng mọi điều kiện.
4. `claimOrReplay` có ràng buộc duy nhất, so khớp fingerprint và xử lý request đang cạnh tranh. Fingerprint bao phủ nội dung nghiệp vụ liên quan, không bao gồm chính idempotency key.
5. Việc đọc lại kết quả diễn ra sau kiểm tra quyền. Khóa request không trở thành một bí mật giúp người khác đọc kết quả ngoài phạm vi.
6. `requireRevision` ngăn người gọi tác động lên phiên bản đã thay đổi theo hợp đồng API. Replay của cùng request thành công được xử lý trước kiểm tra này để không thất bại chỉ vì lần xử lý đầu đã tăng phiên bản.
7. `assessCustomerRequest` kiểm tra trạng thái, lý do và chính sách; mọi giá trị tiền trong quyết định lấy từ dữ liệu đáng tin cậy. Client không tự đặt số tiền.
8. Tạo quyết định, chuyển trạng thái, lưu kết quả và ghi outbox cùng commit hoặc rollback.
9. `createUniqueForDecision` cùng các ràng buộc trạng thái và cơ sở dữ liệu ngăn nhân bản ý định hủy. Quyết định nghiệp vụ không được tạo lại tùy ý chỉ vì có khóa request mới.

Mã khung chưa hiện thực việc hoàn tiền. Worker phía sau phải kiểm tra quyết định hủy, quyền hoàn, ngân sách và tính duy nhất trước khi tạo tác động tài chính.

Một phương thức Java gắn transaction cũng chỉ bảo vệ được những thay đổi thật sự tham gia transaction đó. Nếu repository dùng kết nối độc lập hoặc một lời gọi mạng tạo tác động bên ngoài, cần cơ chế riêng; không giả định toàn bộ phương thức đã nguyên tử.

## 8. Đồng thời và idempotency bảo vệ actor hợp lệ như thế nào?

### 8.1. Kiểm tra quyền không ngăn được tranh chấp

Hai request từ cùng khách hàng có thể đều đúng quyền và đều đọc thấy trạng thái cũ. Ví dụ, một yêu cầu hủy cạnh tranh với bước bắt đầu giao, hoặc hai yêu cầu trả hàng cùng sử dụng số lượng còn được trả.

Đó là lý do cần kiểm tra trạng thái và giành quyền thay đổi trong cùng cơ chế nhất quán: khóa hàng, cập nhật có điều kiện hoặc optimistic locking phù hợp. Chỉ gọi `canCancel()` trước rồi ghi trạng thái sau không bảo đảm điều kiện vẫn đúng.

Nếu dùng một JVM lock nhưng hệ thống có nhiều instance, hai request vẫn có thể chạy ở hai nơi khác nhau. Bảo vệ phải nằm ở ranh giới dữ liệu dùng chung hoặc cơ chế phối hợp có thẩm quyền.

### 8.2. Idempotency giải quyết gửi lại cùng ý định

Đối với cùng khóa, phạm vi và nội dung, máy chủ trả cùng kết quả đã ghi nhận hoặc trạng thái đang xử lý theo hợp đồng. Cùng khóa nhưng khác đơn hoặc lý do có ý nghĩa nghiệp vụ phải được xử lý như xung đột.

Nếu tranh chấp unique key làm transaction bị hủy, cần kết thúc transaction đó rồi mới đọc lại hoặc retry theo cơ chế của ứng dụng. Không tiếp tục thao tác trong transaction đã thất bại.

### 8.3. Khóa mới không mở rộng quyền lợi

Khách có thể gửi hai khóa khác nhau cho cùng đơn. Cần kiểm tra state machine, quyết định đang hoạt động và ràng buộc nghiệp vụ để không tạo hai luồng hủy hoặc hai lệnh hoàn.

Tương tự, hai yêu cầu trả hàng khác khóa phải cùng trừ vào số lượng được trả và ngân sách hoàn của giao dịch. Idempotency không thay thế invariant tổng.

Nếu quyết định đã mất hiệu lực, hết hạn hoặc nội dung thay đổi, một khóa mới cũng không làm nó hợp lệ trở lại. Phải đi qua quy trình tạo hoặc phê duyệt quyết định mới khi chính sách yêu cầu.

### 8.4. Tác vụ bất đồng bộ giữ nguồn gốc, không mang quyền vô hạn

Message nên tham chiếu `cancellationId`, `orderId`, tenant và dữ kiện nguồn gốc cần thiết. Worker tải quyết định có thẩm quyền thay vì tin mọi trường tiền hoặc quyền trong payload.

Không đưa credential của khách hàng vào queue như một cách giữ quyền dài hạn. Cần phân biệt người khởi phát với service actor thực thi, và xác định quyết định nào vẫn có hiệu lực sau khi phiên khách hàng hết hạn.

Tùy chính sách, một yêu cầu đã được chấp nhận hợp lệ có thể tiếp tục hoàn tất sau khi khách đăng xuất. Một yêu cầu chưa được chấp nhận không tự trở nên có quyền chỉ vì có message. Hệ thống phải có ranh giới quyết định rõ, không kiểm tra tùy tiện theo việc token còn hạn lúc worker chạy.

## 9. Cùng chính sách phải được áp dụng trên mọi đường truy cập

Một chức năng chi tiết được kiểm tra đúng vẫn có thể bị vượt qua qua endpoint danh sách, xuất file hoặc cập nhật hàng loạt.

### 9.1. Đọc cũng cần kiểm tra đối tượng và phạm vi dữ liệu

Các đường thường bị bỏ sót:

- Tìm kiếm hoặc phân trang đơn hàng.
- API lấy trạng thái thanh toán hoặc lịch sử hoàn.
- Tải hóa đơn, chứng từ hoặc file đính kèm.
- Đăng ký nhận thông báo qua kênh thời gian thực.
- Endpoint cũ, phiên bản di động hoặc API dành cho tích hợp.
- Bộ nhớ đệm dùng chung giữa khách hàng hoặc tenant.

Lọc danh sách phải dựa trên tenant và quan hệ khách hàng đã xác minh. Không chỉ bảo vệ endpoint xem từng đơn rồi để endpoint tìm kiếm trả về mọi đơn.

Một URL tải file khó đoán không tự chứng minh người tải có quyền. Nếu thiết kế dùng link mang quyền truy cập, cần phạm vi, thời hạn và cách phát link phù hợp. Không cấp link dựa trên `invoiceId` tùy ý mà chưa xác minh quan hệ.

Thông báo lỗi và phản hồi không nên làm lộ dữ liệu của đối tượng ngoài quyền. Có thể áp dụng một quy ước phản hồi nhất quán cho đối tượng không tồn tại hoặc không được truy cập, đồng thời giữ lý do chi tiết trong dấu vết nội bộ. Không nên hứa rằng chỉ đổi mã lỗi đã loại bỏ mọi kênh suy đoán; điều cốt lõi vẫn là không trả dữ liệu hoặc tạo tác động trái quyền.

### 9.2. Batch không được nhân rộng một lần kiểm tra

Với yêu cầu hủy nhiều đơn, quyền trên đơn đầu tiên không bao phủ các đơn còn lại. Mỗi đối tượng phải được kiểm tra, cùng với giới hạn tổng nếu có.

Hợp đồng API cần nói rõ:

- Toàn bộ batch phải thành công cùng nhau hay cho kết quả từng phần?
- Nếu có đơn khác tenant hoặc ngoài quyền, xử lý thế nào mà không lộ dữ liệu?
- Retry batch có nhận diện được từng ý định con không?
- Hạn mức tính theo từng đơn, cả batch hay trong một khoảng thời gian?

Một câu lệnh cập nhật theo danh sách ID thiếu điều kiện tenant hoặc chủ thể có thể làm vô hiệu hóa mọi kiểm tra trước đó.

### 9.3. Cache không được làm trộn actor context

Khóa cache cần phản ánh phạm vi dữ liệu và kết quả quyền mà nó phục vụ. Chỉ dùng `orderId` có thể không đủ nếu định danh không duy nhất toàn cục hoặc dữ liệu trả về phụ thuộc vai trò.

Không cache một phản hồi dành cho nhân viên rồi trả nguyên cho khách hàng. Không chuyển một context từ request trước sang request sau qua biến dùng chung hoặc trạng thái tiến trình.

Nếu cache kết quả kiểm tra quyền, cần cơ chế hết hạn hoặc vô hiệu hóa phù hợp với điều kiện hiện hành. Danh tính không đổi không chứng minh quan hệ và quyền không đổi.

### 9.4. Tách quyền xem replay khỏi điều kiện tạo tác động mới

Trong mã Java minh họa, kiểm tra quyền trước replay bảo đảm actor hiện tại có thể nhận kết quả. Nó không nên bị trộn với điều kiện “đơn còn ở trạng thái trước hủy”, vì lần xử lý đầu đã chuyển trạng thái hợp lệ.

Điều kiện tạo quyết định mới được đánh giá khi thật sự xử lý lần đầu. Điều kiện đọc lại kết quả được đánh giá mỗi lần trả dữ liệu. Nếu quyền truy cập bị thu hồi, hệ thống có thể từ chối trả kết quả theo chính sách, nhưng không vì vậy tạo lại hoặc đảo ngược tác động đã commit.

## 10. Hạn mức và các tín hiệu rủi ro không thay thế invariant

Một khách hàng có thể sở hữu hợp lệ hàng trăm giỏ hoặc đơn giữ chỗ. Mỗi request đều đúng quyền, nhưng tổng tài nguyên hoặc quyền lợi có thể vượt giới hạn sản phẩm.

| Tài sản hoặc quyền lợi | Phạm vi cần xem xét | Kiểm soát minh họa |
| --- | --- | --- |
| Tồn kho đang giữ | Khách hàng, sản phẩm và tổng thời gian giữ | Giới hạn số lượng đang giữ và cơ chế hết hạn nhất quán |
| Ngân sách ưu đãi | Chiến dịch và chủ thể đủ tư cách | Sổ cấp quyền lợi và ràng buộc sử dụng |
| Số lượng được trả | Dòng hàng và giao dịch gốc | Tổng đã trả, đang xử lý và yêu cầu mới không vượt quyền |
| Tiền được hoàn | Khoản thanh toán và phân bổ liên quan | Ngân sách đã hoàn và đang giữ được bảo vệ nguyên tử |
| Tác vụ xuất dữ liệu | Khách hàng hoặc tenant và tài nguyên dùng chung | Số tác vụ đồng thời, kích thước và thời gian xử lý |
| Luồng hỗ trợ hoặc yêu cầu điều chỉnh | Tài khoản, quan hệ và chính sách nghiệp vụ | Hạn mức phù hợp, phê duyệt khi cần, chống tạo trùng |

Rate limiting theo tài khoản hoặc IP có thể giảm tải và tăng chi phí lạm dụng, nhưng không chứng minh đúng giá, đúng quyền hoặc đúng tổng quyền lợi.

Các tín hiệu như tuổi tài khoản, tỷ lệ hủy hoặc nhiều tài khoản có liên hệ có thể hỗ trợ đánh giá rủi ro. Chúng không tự chứng minh một người đã gian lận. Nhiều người có thể dùng chung mạng, địa chỉ hoặc thiết bị theo ngữ cảnh hợp pháp.

Không dùng việc “đã xác thực mạnh” để bỏ invariant tài chính. Một khách hàng được xác thực tốt vẫn có thể chủ động gửi hai yêu cầu cạnh tranh hoặc khai thác quy tắc giảm giá bị thiết kế sai.

## 11. Kiểm thử mô hình khách hàng đã xác thực

Mỗi kiểm thử cần bắt đầu từ actor, quan hệ, đối tượng và hành động cụ thể. Chỉ kiểm thử một người dùng hợp lệ trên một đối tượng hợp lệ sẽ bỏ qua phần lớn rủi ro phân quyền và logic.

| Tình huống | Thao tác kiểm thử | Kết quả cần chứng minh |
| --- | --- | --- |
| Chưa xác thực | Gọi thao tác dành cho khách hàng với credential không có hoặc không hợp lệ | Không tạo tác động nghiệp vụ ngoài chính sách |
| Sai khách hàng | Actor C42 thao tác trên đơn C99 cùng tenant | Không đọc hoặc sửa trái quyền |
| Sai tenant | Cùng chủ thể nhưng chọn tenant không có quan hệ hợp lệ | Context không được mở rộng quyền |
| Giả context | Gửi `customerId`, vai trò hoặc cờ xác thực trong body | Giá trị không thay thế ngữ cảnh có thẩm quyền |
| Ghép sai đối tượng | Đơn của actor đi kèm payment hoặc dòng hàng không thuộc đơn | Bị chặn trước khi tạo tác động |
| Sửa trường máy chủ quản lý | Gửi giá, trạng thái đã trả tiền, người duyệt hoặc số tiền hoàn | Không thay đổi quyết định có thẩm quyền |
| Sở hữu nhưng sai trạng thái | Chủ đơn yêu cầu hủy sau mốc cấm của chính sách | Không tạo quyết định hủy tự phục vụ |
| Quan hệ bị thu hồi | Giữ phiên cũ sau khi mất quyền đại diện | Kết quả theo chính sách hiệu lực hiện hành |
| Cạnh tranh hủy và xử lý giao | Cho hai luồng cùng bắt đầu từ `CONFIRMED` | Không đồng thời chấp nhận hai chuyển trạng thái xung đột |
| Retry cùng ý định | Gửi cùng khóa và nội dung sau khi mất phản hồi | Cùng kết quả, không thêm quyết định hoặc lệnh tiền |
| Cùng khóa khác nội dung | Thay đơn hoặc nội dung liên quan trong cùng phạm vi khóa | Xử lý xung đột, không dùng nhầm kết quả |
| Đổi khóa cho cùng quyền lợi | Gửi nhiều khóa khi yêu cầu hủy đã được chấp nhận | Không nhân tác động nghiệp vụ |
| Chia nhỏ quyền trả hoặc hoàn | Gửi nhiều yêu cầu hợp lệ khi đứng riêng | Tổng không vượt số lượng hoặc ngân sách |
| Đường đọc phụ | Thử danh sách, file, thông báo và endpoint cũ | Áp dụng cùng phạm vi quyền phù hợp |
| Batch trộn đối tượng | Gửi lẫn đơn có quyền và không có quyền | Kết quả đúng hợp đồng, không thao tác ngoài quyền |
| Worker xử lý lại | Phát lại sự kiện hoặc chạy lại sau khi dừng | Không tạo thêm tác động tài chính |
| Bên ngoài timeout | Nhà cung cấp đã thực hiện nhưng phản hồi bị mất | Không tạo lệnh mới chỉ vì chưa biết kết quả |

Kiểm thử cạnh tranh cần đồng bộ các luồng tại điểm có thể tranh chấp. Gửi request tuần tự không kiểm chứng được race condition. Nên chạy với cơ sở dữ liệu có ngữ nghĩa transaction tương ứng; mock repository không chứng minh hành vi khóa hoặc ràng buộc duy nhất.

Sau mỗi kịch bản, kiểm tra nhiều hơn mã HTTP:

- Đối tượng có đổi trạng thái hoặc chủ sở hữu trái phép không?
- Có bao nhiêu quyết định, bản ghi outbox và lệnh tài chính?
- Các khoản giữ, số lượng tồn hoặc ngân sách hoàn có còn đúng không?
- Actor và khách hàng hiệu lực trong dấu vết có khớp không?
- Có trả file hoặc dữ liệu ngoài phạm vi qua đường phụ không?

Có thể bổ sung kiểm thử sinh chuỗi thao tác trên các đối tượng của nhiều khách hàng: tạo, xem, sửa, thanh toán, hủy, trả, retry và chuyển trạng thái. Sau mỗi commit, invariant về chủ thể, trạng thái và tổng quyền lợi vẫn phải được giữ.

## 12. Dấu vết kiểm toán cần thể hiện actor nào?

Một trường `userId` không đủ khi có nhiều vai trò và tác vụ bất đồng bộ. Dấu vết nên cho phép xác định:

~~~text
người khởi phát
tài khoản xác thực
tenant và khách hàng hiệu lực
quan hệ hoặc ủy quyền được sử dụng
hành động được yêu cầu
đối tượng và phiên bản
quyết định cùng phiên bản chính sách nếu cần
service actor thực thi
kết quả và tác động phía sau
~~~

Có thể nối chuỗi:

~~~text
requestId
  -> actor context reference
  -> orderId + orderRevision
  -> cancellationDecisionId
  -> executionId
  -> externalTransactionId
~~~

Không ghi credential, token đầy đủ hoặc thông tin cá nhân không cần thiết vào log. Các tham chiếu cũng cần quyền truy cập phù hợp khi dùng để mở hồ sơ chi tiết.

Các tín hiệu đáng điều tra gồm nhiều lần thử đối tượng ngoài quyền, nhiều khóa cho cùng quyền lợi, hủy và trả theo chuỗi bất thường hoặc worker tạo tác động không có quyết định tương ứng. Đây là tín hiệu, không phải kết luận tự động về gian lận.

Log hỗ trợ phát hiện và giải thích. Nó không thay thế việc chặn thao tác trái quyền trước khi ghi dữ liệu hoặc tạo tác động.

## 13. Những cách triển khai dễ mở rộng quyền ngoài ý định

| Cách triển khai | Phần bị bỏ sót | Hướng hoàn thiện |
| --- | --- | --- |
| Chỉ kiểm tra vai trò `CUSTOMER` | Quan hệ với đối tượng và trạng thái | Kiểm tra theo hành động, đối tượng và ngữ cảnh |
| Tin `customerId` trong request | Người gọi có thể chọn chủ thể khác | Suy ra hoặc xác minh ngữ cảnh khách hàng tại máy chủ |
| ID khó đoán nên bỏ kiểm tra quyền | ID có thể lộ qua nhiều kênh | Coi ID là định danh, vẫn kiểm tra quan hệ |
| Chủ đơn được sửa mọi trường của đơn | Quyền sở hữu bị biến thành quyền giá và quy trình | Command theo hành động và trường được phép |
| Kiểm tra chỉ ở controller | Job, API khác hoặc đường ghi nội bộ có thể bỏ qua | Đặt invariant tại lớp nghiệp vụ và nơi ghi có thẩm quyền |
| Có transaction nhưng thiếu tranh chấp | Nhiều request cùng dùng một trạng thái hoặc ngân sách | Khóa, phiên bản hoặc cập nhật có điều kiện phù hợp |
| Có idempotency nên bỏ ràng buộc tổng | Khóa mới vẫn có thể dùng lại quyền lợi | Tính duy nhất và invariant theo nghiệp vụ |
| Worker tin payload do client tạo | Khách có thể gián tiếp điều khiển lệnh đặc quyền | Tải quyết định đáng tin cậy và kiểm tra binding |
| Nhân viên hỗ trợ dùng chung context khách | Mất nguồn gốc và phạm vi đại diện | Tách người khởi phát, chủ thể được đại diện và service actor |

## 14. Bài tập tự kiểm tra

### Bài 1: đăng nhập đúng nhưng chọn đơn của người khác

API kiểm tra token hợp lệ và vai trò `CUSTOMER`, sau đó gọi repository theo `orderId` trong URL. Không có điều kiện khách hàng hoặc kiểm tra quan hệ.

**Gợi ý trả lời:** API chỉ xác thực danh tính và quyền chức năng. Cần kiểm tra tenant cùng quan hệ được phép trên chính đơn đó. Không thể thay thế bằng việc giấu ID hoặc chỉ cho giao diện hiển thị đơn của người dùng.

### Bài 2: chủ đơn muốn đặt số tiền hoàn

Khách sở hữu đơn và gửi yêu cầu trả hàng với `refundAmount=800000`. Controller cho qua vì số tiền không âm và nhỏ hơn tổng giá trị đơn.

**Gợi ý trả lời:** số tiền đúng định dạng chưa phải quyền hoàn. Máy chủ cần tính theo dòng hàng, giảm giá đã phân bổ, số lượng còn được trả, phần đã hoàn và đang giữ. Khách được đề nghị hành động trong phạm vi, không tự xác định quyền lợi.

### Bài 3: hai khóa hủy khác nhau

Khách gửi hai yêu cầu hủy cùng đơn với hai idempotency key khác nhau. Cả hai đều được xử lý thành công ở tầng lưu khóa.

**Gợi ý trả lời:** lưu khóa chỉ chống gửi lại cùng khóa. Cần trạng thái và ràng buộc nghiệp vụ bảo đảm chỉ một ý định hủy có hiệu lực theo chính sách, đồng thời chỉ tạo số lệnh tài chính được phép. Nếu hai transaction cạnh tranh, cơ chế ở cơ sở dữ liệu phải giữ điều kiện đó.

### Bài 4: đăng xuất có làm dừng mọi job không?

Khách yêu cầu hủy hợp lệ, transaction tiếp nhận đã commit, sau đó đăng xuất trước khi worker xử lý.

**Gợi ý trả lời:** không suy ra kết quả chỉ từ trạng thái phiên lúc worker chạy. Cần quy định hiệu lực của quyết định đã được chấp nhận và điều kiện phải kiểm tra lại. Worker thực hiện với danh tính dịch vụ và nguồn gốc quyết định rõ ràng, không tái sử dụng credential của khách như quyền vô hạn.

## 15. Các điểm cần ghi nhớ

Khách hàng đã xác thực là một actor có danh tính đáng tin cậy trong phạm vi xác thực, nhưng quyền nghiệp vụ vẫn phụ thuộc quan hệ với đối tượng, tenant, hành động, trạng thái và các điều kiện hiện hành.

Quyền sở hữu không bao gồm quyền tự đặt giá, tự phê duyệt, bỏ qua bước hoặc sử dụng quyền lợi nhiều lần. Command có phạm vi rõ, kiểm tra quan hệ, state machine, transaction, kiểm soát cạnh tranh và idempotency cần phối hợp để giữ các invariant.

Câu hỏi cốt lõi là: **Actor này đang hành động với tư cách nào, trên đối tượng nào, được phép tạo tác động gì và cơ chế nào giữ giới hạn đó qua mọi request, retry và worker phía sau?**
