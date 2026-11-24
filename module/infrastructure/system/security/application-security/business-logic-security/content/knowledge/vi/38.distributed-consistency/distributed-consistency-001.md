# Cross service invariant

## 1. Bất biến liên dịch vụ là gì?

**Cross service invariant** là quy tắc nghiệp vụ phải luôn được giữ trong một phạm vi xác định, nhưng dữ liệu hoặc hành động liên quan nằm ở nhiều dịch vụ.

Ví dụ: hệ thống chỉ được cho phép giao một đơn khi có căn cứ thanh toán đúng nội dung được duyệt và có hàng đã được cấp chắc chắn cho đơn đó. Order Service, Payment Service và Inventory Service có thể mỗi nơi đều có transaction đúng, trong khi quy tắc chung vẫn bị phá vỡ.

Trong module bảo mật logic nghiệp vụ, mục tiêu không chỉ là đồng bộ các bảng cho giống nhau. Mục tiêu là ngăn người gọi khai thác khoảng trễ, retry, dữ liệu cũ hoặc đường gọi khác nhau để:

- Nhận hàng khi chưa đáp ứng điều kiện thanh toán.
- Giữ hoặc tiêu thụ cùng một đơn vị hàng cho nhiều đơn.
- Trả tiền theo phiên bản giá khác với phiên bản được duyệt.
- Kích hoạt giao hàng hoặc thu tiền nhiều lần.
- Dùng kết quả của tenant, đơn hàng hoặc lượt thực thi khác.
- Hủy, hoàn tiền hoặc giải phóng tài nguyên theo thứ tự không được phép.

Sau bài học, bạn có thể viết một bất biến liên dịch vụ có phạm vi rõ ràng, chỉ ra bên có thẩm quyền với từng dữ kiện, thiết kế giao thức giữ bất biến và kiểm thử các lịch lỗi quan trọng.

## 2. Ví dụ xuyên suốt: chỉ cho giao một đơn đủ điều kiện

### 2.1. Hợp đồng minh họa

Giả sử một đơn có một mặt hàng, một kiện giao và phải thu tiền trước khi cho phép giao:

| Dữ kiện | Giá trị minh họa |
|---|---|
| Tenant | T-1 |
| Đơn hàng | O-981 |
| Phiên bản nội dung được duyệt | 7 |
| Mặt hàng | SKU-9, số lượng 1 |
| Tổng tiền được duyệt | 500.000 VND |
| Workflow operation | WF-501 |
| Thế hệ thực thi hiện tại | 3 |
| Chính sách giao | Thu tiền thành công và có cấp hàng chắc chắn trước khi cấp phép giao |

Thế hệ thực thi, gọi là generation trong bài, phân biệt một lượt điều phối còn hiệu lực với các lượt cũ đã bị thay thế hoặc hủy. Nó không thay thế danh tính đơn hàng hay operation nghiệp vụ.

Đây là hợp đồng cụ thể của ví dụ. Hệ thống cho phép giao khi mới được ủy quyền thanh toán, giao COD hoặc chia nhiều kiện phải có bất biến tương ứng, không dùng nguyên quy tắc trên.

### 2.2. Dữ liệu có thẩm quyền nằm ở đâu?

| Dịch vụ | Quyết định hoặc dữ liệu có thẩm quyền | Không tự chứng minh được |
|---|---|---|
| Order Service | Snapshot được duyệt, trạng thái điều phối, quyết định hủy hoặc cho giao | Tiền đã được nhà cung cấp thu thành công |
| Inventory Service | Số lượng có thể cấp, reservation và allocation cho từng đơn | Đơn đã thanh toán đủ |
| Payment Service | Payment operation, số tiền, tiền tệ, kết quả thu tiền được xác nhận | Hàng vẫn được cấp cho đúng đơn |
| Fulfillment Service | Operation giao hàng và việc chống áp dụng trùng tại đầu ra | Một cờ paid do client gửi là đáng tin |

Nếu Order Service có cột payment_status, đó thường là bản sao về tiến độ thanh toán. Cần phân biệt bản sao với bằng chứng phát ra từ nguồn có thẩm quyền.

Nếu Payment Service nhận amount từ một request nội bộ, nó vẫn cần biết amount ấy gắn với phê duyệt nào. Việc request đến từ một service được xác thực không tự chứng minh mọi nội dung đều đúng nghiệp vụ.

### 2.3. Viết bất biến theo đúng thời điểm

Với thiết kế minh họa:

~~~text
Khi cấp phép giao lần đầu cho (tenant, order, generation):

1. Snapshot đơn hàng phải là snapshot được duyệt và còn được phép thực thi.
2. Có xác nhận thu tiền phù hợp với snapshot đó.
3. Có allocation hàng đã commit, không tự hết hạn trong lúc chờ giao.
4. Quyết định cho giao không được đồng thời thua một quyết định hủy đã có hiệu lực.
5. Chỉ tạo một operation giao logic cho đơn theo hợp đồng một kiện.
~~~

Có thể viết ngắn:

~~~text
GrantDispatch(order, generation)
  => MatchesApprovedSnapshot(paymentEvidence)
  AND MatchesApprovedSnapshot(inventoryCommitment)
  AND DispatchDecisionIsCurrent(order, generation)
~~~

Các bằng chứng phải khớp về tenant, đơn hàng, operation hoặc quan hệ operation được phép, phiên bản, loại hành động, lượng hàng, số tiền và tiền tệ.

Không chỉ kiểm tra ba giá trị boolean ở ba nơi rồi kết luận chúng thuộc cùng một ý định.

Quy tắc trên xét tại điểm cấp phép giao. Việc khách trả hàng hoặc phát sinh hoàn tiền sau giao là quy trình khác; không diễn giải rằng payment_status phải vĩnh viễn là CAPTURED sau mọi sự kiện tương lai.

## 3. Vì sao từng service đúng mà toàn hệ thống vẫn sai?

### 3.1. Hai kết quả đúng nhưng thuộc hai phiên bản

Lịch sau có thể xuất hiện:

~~~text
Order phiên bản 7: tổng tiền 500.000 VND.
Payment thu thành công theo phiên bản 7.
Order bị sửa thành phiên bản 8: thêm hàng, tổng tiền 800.000 VND.
Inventory cấp đủ hàng theo phiên bản 8.
Order chỉ kiểm tra "payment success" và "inventory success".
Fulfillment giao toàn bộ nội dung phiên bản 8.
~~~

Payment Service không thu sai command của nó. Inventory Service không cấp sai command của nó. Sai ở quan hệ giữa các command và nội dung đơn được phép giao.

Cần gắn dữ kiện với một snapshot nghiệp vụ xác định. Nếu thay đổi nội dung sau phê duyệt, phải có quy tắc duyệt lại hoặc một workflow điều chỉnh được phép.

### 3.2. “Có hàng” không phải một cam kết giữ hàng

Một câu GET trả available = 1 không giữ đơn vị hàng đó cho người gọi.

~~~text
Order A đọc available = 1.
Order B đọc available = 1.
Cả hai đều quyết định có thể giao.
~~~

Dịch vụ tồn kho phải tự phân xử việc cấp tài nguyên bằng một thao tác có thẩm quyền. Không để nhiều bên dùng cùng một giá trị đọc để độc lập tiêu thụ một tài nguyên.

### 3.3. Thành công cũ đến sau quyết định hủy

~~~text
Generation 2 đang chờ thanh toán.
Workflow bị hủy hoặc thay thế bằng generation 3.
Event PaymentCaptured của generation 2 đến trễ.
Handler chỉ nhìn tên event và đổi đơn hiện tại sang "ready".
~~~

Event có thể là dữ kiện lịch sử thật nhưng không còn đủ quyền làm tiến triển workflow hiện tại.

Không xóa dữ kiện thu tiền thật chỉ vì event cũ. Cần lưu hoặc chuyển nó sang nhánh đối soát, đồng thời ngăn nó kích hoạt giao hàng sai generation.

### 3.4. Timeout bị hiểu thành thất bại chắc chắn

Payment Service đã thu tiền, nhưng Order Service không nhận được phản hồi. Nếu Order Service:

1. Coi timeout là chưa thu.
2. Tạo payment operation mới.
3. Giải phóng hàng cũ và cho khách thử lại.

thì có thể thu thêm lần nữa hoặc mất liên kết giữa tiền đã thu và tài nguyên của đơn.

Timeout chỉ mô tả việc chưa quan sát được kết quả. Phải có trạng thái chưa rõ và đường phục hồi bằng danh tính operation ổn định.

### 3.5. Transaction cục bộ không truyền qua HTTP

~~~java
// Cách hiểu sai: annotation không tự bao trùm hai database từ xa.
@Transactional
public void confirmOrder(Order order) {
    inventoryClient.allocate(order);
    paymentClient.capture(order);
    orderRepository.markReady(order.id());
}
~~~

Rollback database của Order Service không tự hủy allocation hoặc khoản thu đã commit ở dịch vụ khác. Không gọi đó là một giao dịch nguyên tử toàn hệ thống nếu không có giao thức và tài nguyên thực sự tham gia cơ chế như vậy.

## 4. Phân biệt bất biến an toàn với độ trễ đồng bộ

Có những khác biệt tạm thời chấp nhận được:

~~~text
Payment đã ghi CAPTURED.
Event chưa tới Order.
Order vẫn hiển thị PAYMENT_PENDING.
~~~

Nếu đơn chưa được phép giao, đây có thể là độ trễ của bản sao trạng thái, cần được theo dõi và xử lý để workflow tiến triển.

Có những khác biệt không thể chấp nhận:

~~~text
Fulfillment đã cho giao.
Chưa có căn cứ thu tiền theo hợp đồng.
Hoặc allocation dùng để cho giao đã hết hiệu lực.
~~~

Đồng bộ dữ liệu sau đó không thu hồi được một kiện hàng đã rời kho.

Phân biệt hai mục tiêu:

| Mục tiêu | Câu hỏi |
|---|---|
| Safety | Có bao giờ chấp nhận hành động bị cấm, như giao sai điều kiện hoặc thu trùng? |
| Liveness | Khi đủ điều kiện và hạ tầng phục hồi, workflow có tiến tới kết quả hoặc được đưa ra xử lý rõ ràng không? |

Eventual consistency không cho phép bỏ qua safety tại bước có tác dụng không thể đảo ngược dễ dàng. Nó cũng không tự bảo đảm mọi workflow sẽ hoàn tất trong một thời hạn cố định khi mạng hoặc participant lỗi kéo dài.

Khi thiếu căn cứ có thẩm quyền, hệ thống có thể giữ PENDING hoặc RECONCILIATION_REQUIRED thay vì suy đoán thành công. Đổi lại, phải có cách khôi phục tiến độ và xử lý tài nguyên đang giữ.

## 5. Đặt chủ sở hữu cho bất biến và thiết kế cam kết

### 5.1. Mỗi tài nguyên cần một bên phân xử rõ ràng

Inventory Service quyết định ai được cấp cùng một đơn vị hàng. Payment Service quyết định cách nhận diện và theo dõi một lần thu. Order Service sở hữu quyết định giữa hủy và cho giao của đơn trong ví dụ.

“Có một owner” không bắt buộc chỉ có một process. Owner có thể được triển khai bằng nhiều replica, nhưng các replica phải cùng tuân thủ một nguồn trạng thái và cơ chế phân xử đúng.

Nếu mọi service tự quyết định “đơn đủ điều kiện” từ cache riêng, không có một nơi đảm bảo hai quyết định mâu thuẫn bị loại trừ.

### 5.2. Reservation và commitment có hợp đồng khác nhau

Một reservation có lease có thể hết hạn. Nó phù hợp cho giữ hàng tạm thời, nhưng không thể dùng như một cam kết còn hiệu lực vô thời hạn.

Trong giao thức minh họa:

~~~text
RESERVED:
  Giữ hàng tạm thời, có chính sách hết hạn.

COMMITTED:
  Hàng đã được cấp chắc chắn cho snapshot và generation.
  Không tự hết hạn trong khi chờ quyết định giao.
  Chỉ giải phóng qua thao tác được phép bởi giao thức hủy.

RELEASED:
  Không còn được dùng làm căn cứ cho giao hàng.
~~~

Inventory phải tự kiểm tra transition RESERVED -> COMMITTED, bao gồm reservation còn hợp lệ và đủ số lượng. Không chỉ để Order đặt một cờ committed trên bản sao của nó.

Giữ commitment lâu tạo chi phí tài nguyên. Cần reconciliation và chính sách xử lý workflow mắc kẹt, thay vì âm thầm hết hạn nó trong khi một quyết định giao hợp lệ vẫn có thể được thực thi.

### 5.3. Bằng chứng phải còn dùng được tại điểm quyết định

Hai lần GET “thanh toán tốt” và “reservation còn hạn” không tạo một snapshot nguyên tử qua hai service. Trạng thái có thể đổi giữa lúc đọc và lúc dùng.

Để đưa ra quyết định an toàn, cần một trong những thiết kế phù hợp:

- Dùng các cam kết bền vững với quy tắc không bị thu hồi tùy ý.
- Đưa phần quyết định bắt buộc nguyên tử về cùng một authority hoặc transaction boundary.
- Dùng giao thức phối hợp có khả năng loại trừ các quyết định xung đột.
- Dùng distributed transaction khi mọi participant và tài nguyên thực sự hỗ trợ, với giới hạn vận hành được chấp nhận.

Không có một phép đọc thông thường nào tự biến dữ liệu có thể bị thu hồi thành cam kết không thể thay đổi.

## 6. Thiết kế một giao thức điều phối có thể kiểm tra

Thiết kế dưới đây dùng Order Service làm orchestrator. Đây là một giao thức minh họa cần được triển khai và kiểm thử ở từng participant, không phải bảo đảm có được chỉ bằng cách thêm một service điều phối.

### 6.1. Cố định snapshot trước khi tiêu thụ tài nguyên

Order lưu snapshot bất biến gồm:

~~~text
tenant
order
approved_snapshot_id
approved_version
các dòng hàng và số lượng
tổng tiền và tiền tệ
tham chiếu địa chỉ giao đã được cho phép
các điều kiện phê duyệt liên quan
~~~

Các command đến Inventory và Payment cùng gắn với snapshot này.

Nếu thay đổi một trường làm thay đổi ý nghĩa phê duyệt, cần tạo snapshot hoặc quy trình điều chỉnh mới. Không sửa âm thầm snapshot cũ rồi tiếp tục dùng bằng chứng của nó.

### 6.2. Mỗi participant xác nhận bằng transaction cục bộ

Inventory tiếp nhận yêu cầu giữ hàng bằng định danh nghiệp vụ ổn định, phân xử số lượng và lưu reservation.

Sau đó, Inventory chuyển reservation hợp lệ thành COMMITTED và phát bằng chứng allocation tương ứng. Chuyển trạng thái và lưu ý định phát event phải nằm trong cùng transaction cục bộ.

Trong luồng minh họa, sau khi có commitment hàng, orchestrator mới yêu cầu thu tiền. Lựa chọn này có thể giữ hàng lâu nếu thanh toán bị chậm; phần phục hồi phải xử lý rõ chi phí đó.

Payment thực hiện hoặc đối soát một payment operation ổn định. Nó chỉ phát sự kiện thu tiền thành công khi có căn cứ theo giao thức thanh toán, không khi mới gửi request đi.

Nếu Payment trả kết quả từ một read model chưa có thẩm quyền hoặc mới chỉ AUTHORIZED, đó chưa phải bằng chứng CAPTURED theo hợp đồng giao hàng của bài.

### 6.3. Lưu bằng chứng, không chỉ nhận callback rồi đổi cờ

Orchestrator xác minh nguồn phát và quan hệ của từng bằng chứng với workflow:

- Đúng tenant và đơn.
- Đúng snapshot được duyệt.
- Đúng payment operation hoặc inventory allocation dự kiến.
- Đúng generation đối với tiến trình điều phối hiện tại.
- Đúng số tiền, tiền tệ, dòng hàng và số lượng.
- Đúng loại kết quả và transition được phép.

Sau đó lưu dữ kiện và tiến độ bằng transaction của Order.

Chỉ khi đủ điều kiện mới chuyển sang READY_TO_DISPATCH.

### 6.4. Phân xử giữa hủy và cấp phép giao

Tại Order Service, hai quyết định phải loại trừ nhau:

~~~text
READY_TO_DISPATCH -> DISPATCH_COMMITTED

PREPARING hoặc READY_TO_DISPATCH -> CANCEL_COMMITTED
~~~

Chúng phải tranh chấp trên cùng một trạng thái có thẩm quyền bằng khóa, version hoặc conditional update thích hợp.

Ví dụ rút gọn cho nhánh giao:

~~~sql
UPDATE order_workflow
SET state = 'DISPATCH_COMMITTED',
    version = version + 1
WHERE tenant_id = :tenant_id
  AND order_id = :order_id
  AND generation = :generation
  AND version = :expected_version
  AND state = 'READY_TO_DISPATCH'
  AND approved_snapshot_id = :approved_snapshot_id
  AND payment_snapshot_id = approved_snapshot_id
  AND inventory_snapshot_id = approved_snapshot_id
  AND payment_evidence_id IS NOT NULL
  AND inventory_commitment_id IS NOT NULL;
~~~

Trong cùng transaction, tạo dispatch operation và outbox command gắn với quyết định này. Chỉ số dòng cập nhật bằng 1 mới cho phép nhánh đó tiếp tục.

Các cột bằng chứng trong câu SQL phải được ghi bởi handler đã xác minh dữ liệu có thẩm quyền. Một ID hoặc snapshot_id do client tự khai không tự trở thành bằng chứng vì xuất hiện trong WHERE.

Câu SQL cũng không tự làm cho commitment từ xa còn hiệu lực. Bảo đảm đó đến từ giao thức: allocation COMMITTED không tự hết hạn, và việc giải phóng phải đi qua nhánh hủy được phép.

Nếu CANCEL_COMMITTED thắng, không tạo permit giao. Nếu DISPATCH_COMMITTED thắng, nhánh hủy trước giao không được giải phóng hàng hoặc hoàn tiền như thể chưa có quyết định giao. Yêu cầu thay đổi sau mốc này phải theo một quy trình được thiết kế riêng.

### 6.5. Fulfillment chỉ nhận quyết định giao có thẩm quyền

Fulfillment không tự suy luận quyền giao từ một event thanh toán đơn lẻ. Nó nhận command giao gắn với dispatch operation đã được Order commit.

Tại Fulfillment:

1. Xác minh nguồn và phạm vi lệnh.
2. Kiểm tra tenant, order, snapshot và dispatch operation.
3. Nhận diện lệnh lặp.
4. Tạo một operation giao logic trong transaction cục bộ.
5. Lưu công việc cần gửi xuống hệ thống kho hoặc vận chuyển.

Với hợp đồng một kiện, ràng buộc chống tạo operation giao thứ hai phải bao phủ đơn hàng, không chỉ generation. Đổi generation không được làm một đơn đã giao trở thành đơn chưa giao.

Nếu hệ thống kho bên ngoài có thể nhận lệnh lặp, nó cũng cần hợp đồng idempotency hoặc cách đối soát theo định danh giao ổn định. Chỉ chống trùng trong database của Fulfillment chưa chứng minh rằng không thể gửi hai kiện ngoài thực tế.

### 6.6. Luồng thành công

~~~mermaid
sequenceDiagram
    participant O as Order
    participant I as Inventory
    participant P as Payment
    participant F as Fulfillment
    O->>I: Reserve và commit hàng cho snapshot 7
    I-->>O: InventoryCommitted với allocation ID
    O->>P: Capture theo snapshot 7, payment operation ổn định
    P-->>O: PaymentCaptured với số tiền và tiền tệ
    Note over O: Xác minh bằng chứng cùng workflow và snapshot
    O->>O: Phân xử hủy hoặc giao bằng transaction
    O->>O: Commit DISPATCH_COMMITTED và outbox
    O->>F: Dispatch command cho dispatch operation
    F->>F: Nhận lặp an toàn, tạo operation giao một lần
~~~

Các mũi tên là quan hệ nghiệp vụ; việc giao có thể qua broker và có thể lặp. Không giả định mỗi mũi tên là một lần truyền thành công duy nhất.

## 7. Outbox, inbox và idempotency bảo vệ từng ranh giới

### 7.1. Outbox giải quyết việc ghi dữ liệu rồi phát event

Mẫu outbox lưu thay đổi nghiệp vụ và ý định phát event trong cùng transaction của một service. Tài liệu [Transactional outbox của AWS](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html) mô tả vấn đề dual write và nhu cầu xử lý message trùng ở phía nhận.

Ví dụ tại Inventory:

~~~text
BEGIN
  Nhận diện command hoặc allocation intent đã có.
  Kiểm tra quyền và các điều kiện cấp hàng.
  Chuyển reservation hợp lệ sang COMMITTED.
  Lưu bằng chứng allocation gắn snapshot.
  Ghi outbox InventoryCommitted.
COMMIT
~~~

Nếu commit thành công rồi process chết trước khi publish, relay còn dữ liệu để gửi lại. Nếu transaction rollback, không được phát bằng chứng thành công tương ứng.

Outbox không tạo một transaction nguyên tử bao trùm Order, Payment và Inventory. Nó bảo vệ quan hệ giữa dữ liệu cục bộ với công việc phát thông điệp của service đó.

### 7.2. Inbox phối hợp việc nhận với áp dụng dữ kiện

Ở service nhận:

~~~text
Xác minh nguồn và kiểm tra cấu trúc message.

BEGIN
  Claim danh tính message bằng ràng buộc duy nhất.
  Nếu đã xử lý, trả kết quả hoặc kết thúc theo hợp đồng.

  Kiểm tra quan hệ với workflow và snapshot.
  Áp dụng transition hợp lệ hoặc lưu vào nhánh đối soát.
  Ghi các outbox command tiếp theo nếu cần.
  Hoàn thiện dấu đã xử lý.
COMMIT

ACK sau khi hoàn tất bước xử lý được phép.
~~~

Nếu chỉ ACK trước rồi mới ghi dữ liệu, có thể mất công việc. Nếu ghi dữ liệu rồi chết trước ACK, message có thể được giao lại; local transaction và ràng buộc chống trùng phải xử lý được trường hợp đó.

Message sai tenant, nguồn không hợp lệ hoặc payload mâu thuẫn không được ACK như thành công nghiệp vụ. Có thể cách ly hoặc từ chối theo chính sách xử lý message lỗi.

### 7.3. Chống trùng message chưa đủ cho chống trùng nghiệp vụ

Một command được gửi lại với event ID mới vẫn có thể cùng một ý định.

Cần phân biệt:

~~~text
Message identity:
  (source, event_id) trong phạm vi hệ thống đã quy định.

Business identity:
  tenant + order/intent + loại hành động hoặc operation ổn định.
~~~

Ví dụ hai message ID khác nhau cùng yêu cầu capture cho PAY-501 không được tạo hai payment operation độc lập.

Bài viết [Making retries safe with idempotent APIs của Amazon Builders’ Library](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/) giải thích vai trò của định danh yêu cầu do caller cung cấp, việc ràng buộc ý định và xử lý yêu cầu đến trễ. Khi áp dụng, mỗi API vẫn cần một scope và hợp đồng nội dung cụ thể.

Không đổi định danh payment operation cho mỗi lần retry. Cũng không tự coi một generation mới là quyền thu tiền thêm khi kết quả của generation cũ chưa rõ.

### 7.4. Broker không tự đảm bảo tác dụng bên ngoài xảy ra một lần

Tài liệu [Message Delivery Semantics của Apache Kafka](https://kafka.apache.org/44/design/design/#message-delivery-semantics) phân biệt phạm vi xử lý trong Kafka với việc ghi sang hệ thống đích khác, nơi cần sự phối hợp của đích.

Vì vậy, một tùy chọn “exactly once” của broker hoặc stream processor không tự bao trùm việc thu tiền, cập nhật một database độc lập hay gửi một kiện hàng.

Cần nêu rõ điểm nào có transaction, điểm nào có dedupe và điểm nào phải đối soát khi chưa rõ kết quả.

## 8. Event cũ, sai thứ tự và worker còn sống sau lease

### 8.1. Envelope phải chứa đủ quan hệ nghiệp vụ

Một event thanh toán minh họa:

~~~json
{
  "schemaVersion": 1,
  "eventId": "EVT-P-104",
  "source": "payment-service",
  "type": "PaymentCaptured",
  "tenantId": "T-1",
  "orderId": "O-981",
  "workflowId": "WF-501",
  "generation": 3,
  "approvedSnapshotId": "SNAP-O981-7",
  "paymentOperationId": "PAY-501",
  "aggregateVersion": 4,
  "amount": 500000,
  "currency": "VND"
}
~~~

Trường source trong JSON chỉ là dữ liệu. Tính xác thực của nguồn phải đến từ kênh, danh tính publisher, chữ ký hoặc cơ chế bảo vệ được triển khai.

Tương tự, một snapshot ID cần liên kết được với dữ liệu được duyệt có thẩm quyền; không chỉ là chuỗi trùng nhau giữa hai request do client kiểm soát.

### 8.2. Version không tự tạo thứ tự toàn hệ thống

aggregateVersion = 12 của Inventory không lớn hơn theo nghĩa nghiệp vụ so với aggregateVersion = 4 của Payment. Chúng thuộc hai đối tượng hoặc luồng khác nhau.

Nên theo dõi tiến độ từng nguồn và quan hệ phụ thuộc cần thiết. Không dùng timestamp lớn nhất hoặc một biến lastVersion chung cho mọi service để quyết định tất cả event mới hay cũ.

Nếu thấy khoảng trống version trong một luồng cần đủ dữ kiện, có thể phải đợi, backfill hoặc tra cứu nguồn có thẩm quyền. Không mặc định bỏ qua mọi event có số nhỏ hơn mà không xét loại dữ kiện.

### 8.3. Event cũ có thể không được tiến triển nhưng vẫn phải được đối soát

Một PaymentCaptured của generation đã hủy không được làm sống lại workflow hiện tại.

Nhưng khoản thu đó vẫn có thể thật. Handler phải bảo toàn bằng chứng và đưa vào quy trình đối soát hoặc hoàn tiền thích hợp, không đơn giản vứt bỏ toàn bộ event như thể tiền chưa từng được thu.

Tách hai quyết định:

~~~text
Có ghi nhận dữ kiện lịch sử này không?
Dữ kiện này có được phép làm tiến triển workflow hiện tại không?
~~~

Hai câu hỏi có thể có hai câu trả lời khác nhau.

### 8.4. Lease hết hạn không chứng minh worker cũ đã dừng

Một worker giữ lease rồi bị pause. Worker mới nhận quyền làm việc. Worker cũ tỉnh lại và tiếp tục ghi hoặc gửi lệnh cũ.

Fencing token có thể giúp bên quản lý tài nguyên từ chối quyền ghi lỗi thời. Phân tích gốc của Martin Kleppmann về [distributed locking và fencing](https://martin.kleppmann.com/2016/02/08/how-to-do-distributed-locking.html) nhấn mạnh rằng phía tài nguyên phải thực sự kiểm tra token.

Generation hoặc fencing token cần được authority kiểm tra nguyên tử với thao tác được bảo vệ. Chỉ thêm số generation vào log hoặc payload mà nơi nhận không kiểm tra thì không ngăn được gì.

Token lớn hơn cũng không thay thế quyền nghiệp vụ: worker có generation mới vẫn không được thu tiền sai snapshot hoặc giao một đơn đã hoàn tất trước đó.

## 9. Saga và bù trừ phải giữ đúng ý nghĩa nghiệp vụ

Saga điều phối các transaction cục bộ và các bước phục hồi tương ứng. Tài liệu [Saga orchestration của AWS](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/saga-orchestration.html) nêu các vấn đề về idempotency, dữ liệu cũ và việc saga không tự cung cấp isolation như một transaction đơn.

### 9.1. Không nhầm bù trừ với rollback toàn hệ thống

Nếu đã thu tiền rồi hoàn tiền, lịch sử là “đã thu và đã hoàn”, không phải “chưa từng thu”.

Nếu hàng đã rời kho, một lệnh release reservation không làm kiện hàng quay lại. Cần quy trình trả hàng hoặc xử lý hậu quả tương ứng.

Bù trừ là một thao tác nghiệp vụ có:

- Điều kiện được phép thực hiện.
- Danh tính ổn định và cơ chế chống thực hiện trùng.
- Trạng thái đang chờ, thành công, thất bại hoặc chưa rõ.
- Quan hệ với quyết định hủy có thẩm quyền.
- Cách retry, đối soát và can thiệp khi không thể tự hoàn tất.

Không coi việc đã gửi command Refund hoặc Release là bằng chứng bù trừ đã hoàn thành.

### 9.2. Tách quyết định hủy khỏi việc hoàn tất hủy

~~~text
CANCEL_COMMITTED:
  Đã chọn nhánh hủy; không được cấp phép giao theo workflow này.

COMPENSATING:
  Đang giải phóng tài nguyên hoặc xử lý tiền theo nhánh hủy.

CANCELLED:
  Các nghĩa vụ hủy theo hợp đồng đã được xác nhận hoàn tất.
~~~

Nếu một PaymentCaptured đến sau CANCEL_COMMITTED, không chuyển sang READY_TO_DISPATCH. Ghi nhận khoản thu và xử lý theo nhánh hoàn tiền/đối soát của quyết định hủy.

Nếu DISPATCH_COMMITTED đã thắng trước đó, không chạy nhánh hủy trước giao để tùy ý hoàn tiền và giải phóng hàng. Cần một quy trình sau quyết định giao với điều kiện riêng.

### 9.3. Phân loại lỗi theo bằng chứng thực tế

| Tình huống | Điều đã biết | Hành động an toàn theo giao thức minh họa |
|---|---|---|
| Reservation bị từ chối | Chưa có hàng được giữ theo yêu cầu đó | Không tiến tới bước giao; kết thúc hoặc điều chỉnh theo chính sách |
| Commit allocation thất bại chắc chắn | Không có commitment hàng hợp lệ | Không dùng reservation cũ làm bằng chứng cho giao |
| Capture timeout | Chưa rõ tiền đã thu hay chưa | Đối soát cùng payment operation; chưa cấp phép giao |
| Capture thất bại cuối cùng được xác nhận | Không đủ căn cứ thanh toán cho giao | Chọn nhánh hủy và giải phóng commitment theo giao thức |
| PaymentCaptured đến sau hủy | Có khoản thu cần xử lý nhưng workflow không còn được giao | Đối soát hoặc hoàn tiền, không làm sống lại workflow |
| Refund timeout | Chưa rõ nghĩa vụ hoàn tiền đã hoàn tất | Giữ trạng thái cần đối soát, không kết luận CANCELLED thiếu căn cứ |
| Relay hoặc consumer restart | Công việc có thể được giao lại | Dùng lại operation và ràng buộc chống áp dụng trùng |

Nếu chọn hủy trong lúc thanh toán chưa rõ, có thể thiết kế giải phóng hàng sau khi quyết định hủy đã chắc chắn loại trừ giao. Tuy nhiên, nghĩa vụ đối soát tiền vẫn còn; không được đóng workflow như thể chưa từng có khả năng thu tiền.

### 9.4. Giới hạn sự tích tụ tài nguyên đang giữ

Cam kết bền vững cần đi cùng quản lý tiến độ:

- Giới hạn số workflow và lượng tài nguyên đang giữ theo principal hoặc tenant.
- Theo dõi tuổi của các commitment chưa có kết quả.
- Có deadline nghiệp vụ và hành động hủy được điều phối đúng.
- Tách xử lý tự động khỏi trường hợp cần quyết định của người vận hành.
- Không cấp commitment vô hạn chỉ vì mỗi request riêng lẻ hợp lệ.

Nếu không, người gọi có thể tạo nhiều workflow hợp lệ nhưng bỏ dở để làm cạn hàng hoặc hạn mức, dù chưa từng nhận một kiện hàng trái phép.

## 10. Quyền theo đối tượng vẫn phải được thực thi qua các service

### 10.1. Xác thực service không thay thế kiểm tra command

Một service identity được xác thực cho biết ai đang gọi, nhưng chưa trả lời:

- Nó có được gửi loại command này không?
- Nó có được tác động tới tenant này không?
- Đơn hàng và payment operation có thực sự liên quan không?
- Số tiền, số lượng và snapshot có nằm trong phê duyệt không?
- Nó có được ra lệnh giao sau khi nhánh hủy đã thắng không?

Danh tính workload, quyền gọi API và quyền nghiệp vụ của một command cần được phối hợp.

### 10.2. Truyền ngữ cảnh được ủy quyền có phạm vi rõ ràng

Khi cần mang ngữ cảnh người dùng qua các bước, xác định rõ:

~~~text
Ai là chủ thể gốc?
Service nào đang hành động thay?
Được tác động tới tenant và đối tượng nào?
Được phép thực hiện hành động nào?
Bằng chứng phê duyệt nào cho phép hành động đó?
Ngữ cảnh được chấp nhận trong điều kiện hoặc thời hạn nào?
~~~

Không tin các header actor_id hoặc tenant_id do client tùy ý đặt. Không để một event chỉ có orderId đủ để một consumer truy cập mọi tenant.

Một event của nhà cung cấp thanh toán phải được gắn đúng tài khoản tích hợp, merchant hoặc phạm vi tương ứng trước khi ánh xạ vào đơn hàng nội bộ.

### 10.3. Mọi đường tạo tác dụng phải tuân thủ cùng bất biến

Người dùng có thể gọi API trực tiếp, retry từ mobile, kích hoạt webhook hoặc đi qua một công cụ vận hành.

Nếu đường giao hàng từ giao diện yêu cầu dispatch permit nhưng endpoint quản trị lại cho tạo shipment chỉ từ orderId, bất biến vẫn có đường bị bỏ qua.

Công cụ sửa lỗi, batch job và quy trình replay message phải sử dụng cùng các điều kiện nghiệp vụ hoặc một quy trình ngoại lệ được định nghĩa rõ. Không sửa trạng thái thành “thành công” chỉ để làm dashboard bớt báo lỗi.

## 11. Reconciliation là một phần của giao thức

### 11.1. Đối soát dựa trên danh tính ổn định

Một tác vụ đối soát có thể:

1. Tìm workflow ở trạng thái chưa có kết quả sau deadline.
2. Tra Payment bằng payment operation hoặc provider reference đã lưu.
3. Tra Inventory bằng allocation intent và commitment ID.
4. Đọc quyết định hủy/giao hiện tại từ Order.
5. Tiếp tục, bù trừ hoặc đưa ra xử lý theo state machine.
6. Lưu hành động phục hồi với idempotency và version phù hợp.

Không tạo một workflow mới chỉ vì bản ghi cũ trông như bị kẹt. Workflow cũ có thể đã tạo tác dụng mà bản sao trạng thái chưa biết.

### 11.2. Bất biến có thể được kiểm tra bằng dữ liệu đối soát

Ví dụ các truy vấn logic cần hỗ trợ:

~~~text
Dispatch operation nào thiếu căn cứ thu tiền đúng snapshot?

Đơn nào có nhiều operation giao logic trái hợp đồng một kiện?

Payment operation nào thành công nhưng chưa được gắn với workflow xử lý?

Allocation nào vẫn COMMITTED cho một nhánh hủy đã đủ điều kiện release?

Workflow nào đã CANCEL_COMMITTED nhưng chưa kết thúc nghĩa vụ hoàn tiền?

Event nào thuộc tenant, snapshot hoặc generation không khớp?
~~~

Tác vụ đối soát giúp phát hiện và phục hồi sai lệch. Nó không thay thế cơ chế chặn tại bước cấp phép giao, vì phát hiện sau đó có thể đã quá muộn để ngăn mất tài sản.

### 11.3. Theo dõi quan hệ nhân quả, không chỉ thời gian đồng hồ

Log và trace nên có tenant, order, snapshot, workflow, generation, operation, event ID, loại transition và căn cứ đã dùng.

Timestamp hữu ích để điều tra độ trễ, nhưng đồng hồ của các service có thể lệch. Muốn biết quyết định nào có hiệu lực trước, cần dựa vào version, transaction và quan hệ nhân quả của giao thức, không chỉ so sánh hai dòng log theo giây.

Các chỉ số hữu ích gồm:

- Tuổi lớn nhất và phân bố tuổi của workflow chưa rõ kết quả.
- Số commitment đang giữ mà chưa tiến triển.
- Số retry và event bị nhận diện là trùng.
- Số event cũ bị chặn tiến triển nhưng còn cần đối soát.
- Số lần xung đột giữa nhánh hủy và giao.
- Số bất thường khi đối chiếu payment, inventory và fulfillment.

## 12. Chọn mức phối hợp theo quy tắc cần bảo vệ

| Yêu cầu | Hướng thiết kế phù hợp để xem xét |
|---|---|
| Một tài nguyên khan hiếm không được cấp hai lần | Authority duy nhất về mặt logic, conditional update hoặc reservation tại nguồn |
| Quyết định cần dữ kiện ổn định từ nhiều nơi | Cam kết có hợp đồng rõ ràng và bước quyết định có thẩm quyền |
| Quy trình có trạng thái trung gian được chấp nhận | Workflow/saga bền vững, idempotency, bù trừ và đối soát |
| Nhiều thay đổi bắt buộc nguyên tử tức thời | Đưa về cùng boundary hoặc dùng giao thức transaction được các tài nguyên hỗ trợ |
| Màn hình cần cập nhật nhanh nhưng chấp nhận trễ | Read model bất đồng bộ, có cách biểu đạt trạng thái đang xử lý |
| Tác dụng bên ngoài không có API chống trùng | Cần khả năng tra cứu/đối soát và chính sách cho kết quả chưa rõ; giới hạn bảo đảm phải được nêu |

Một số nguồn dữ liệu và transaction manager có thể hỗ trợ distributed transaction. Chỉ chọn khi tất cả participant liên quan thực sự tham gia, và chấp nhận được cách hệ thống giữ tài nguyên hoặc xử lý lỗi. Một API thanh toán hay kho vận độc lập thường có hợp đồng riêng cần tích hợp.

Đừng chọn cách chia service rồi mới cố ép một bất biến tức thời vào những lần GET và PUT rời rạc. Phạm vi dữ liệu bắt buộc nhất quán là một căn cứ để quyết định ranh giới dịch vụ.

Khi thiếu liên lạc với authority, một bước nhạy cảm có thể phải trì hoãn hoặc từ chối tạm thời. Cho phép tiếp tục bằng cache cũ chỉ để luôn trả thành công có thể làm mất bảo đảm nghiệp vụ.

## 13. Chuyển bất biến thành kiểm thử liên dịch vụ

### 13.1. Kiểm tra tác dụng, không chỉ trạng thái cuối

Một đơn cuối cùng là CANCELLED không chứng minh rằng trước đó chưa từng được giao trái điều kiện.

Cần quan sát:

- Quyết định cấp phép giao và các bằng chứng nó tham chiếu.
- Operation thu tiền và kết quả đã được xác nhận.
- Lịch sử allocation, release và thay đổi generation.
- Operation giao logic và tác dụng ở hệ thống kho/nhà cung cấp.
- Các nghĩa vụ bù trừ chưa hoàn thành.

Một assertion minh họa:

~~~text
Với mọi dispatch permit được commit:
  payment evidence thuộc đúng tenant/order/snapshot.
  inventory commitment thuộc đúng tenant/order/snapshot.
  điều kiện của giao thức còn được bảo vệ tại điểm cấp permit.
  quyết định hủy có hiệu lực trước đó không bị vượt qua.

Với mọi operation giao:
  có dispatch decision hợp lệ.
  không có operation giao thứ hai cho cùng đơn theo hợp đồng một kiện.
~~~

Đối với giao hàng vật lý, cần quan sát cả bên thực hiện tác dụng. Một bảng shipment chỉ có một dòng chưa đủ nếu worker có thể tạo hai lần yêu cầu gửi hàng bên ngoài.

### 13.2. Ma trận lịch lỗi quan trọng

| Ca kiểm thử | Lịch cần tạo | Điều phải giữ |
|---|---|---|
| Hai đơn tranh hàng cuối | Cả hai cùng yêu cầu cấp một đơn vị | Inventory không cấp vượt tài nguyên |
| Thanh toán đúng snapshot cũ | Thu theo v7, sửa đơn sang v8 | Không giao v8 bằng bằng chứng thanh toán v7 |
| Reservation hết hạn | Đến bước commit sau khi lease không còn hiệu lực | Không phát commitment giả |
| Mất phản hồi capture | Thu thành công, ngắt trước phản hồi | Đối soát cùng payment operation, không thu thêm bằng ID mới |
| Event thanh toán đến trễ | Hủy đã thắng rồi mới nhận success cũ | Không cấp phép giao; khoản thu vẫn được xử lý |
| Hủy và giao đồng thời | Hai transition tranh cùng authority | Chỉ một quyết định thắng theo hợp đồng |
| Worker cũ tỉnh lại | Lease/generation bị thay thế rồi worker cũ ghi | Authority từ chối quyền ghi lỗi thời |
| Message được giao lại | Chết sau local commit nhưng trước ACK | Không áp dụng tác dụng lần hai |
| Hai event ID cho cùng ý định | Đóng gói lại command nhưng giữ operation | Chống trùng theo nghiệp vụ vẫn có hiệu lực |
| Giả tenant hoặc snapshot | Payload tham chiếu đối tượng khác phạm vi | Bị từ chối, không làm tiến triển workflow |
| Bù trừ thất bại | Refund hoặc release timeout | Không tuyên bố đã hủy hoàn tất thiếu căn cứ |
| Orchestrator restart | Đã gửi command nhưng chưa lưu phản hồi | Phục hồi từ trạng thái bền vững và định danh cũ |
| Kho nhận lặp | Giao lại dispatch command sau lỗi mạng | Không tạo thêm tác dụng giao theo hợp đồng của bên nhận |

### 13.3. Điều phối lịch thay vì chỉ tăng tải

Dùng điểm đồng bộ, fault injection và các mốc xử lý có thể quan sát để:

- Giữ một event rồi giao nó sau khi nhánh hủy commit.
- Dừng worker sau khi provider thực hiện nhưng trước khi ứng dụng lưu kết quả.
- Restart consumer sau khi local transaction commit nhưng trước ACK.
- Cho hai transition hủy/giao cùng tranh một version.
- Giao lại message với event ID cũ và với event ID mới nhưng cùng operation.

Mỗi test cần dữ liệu riêng, timeout có giới hạn và bằng chứng rằng lịch dự định đã thực sự xảy ra.

Khi xác minh kết quả cuối, chờ các công việc liên quan đạt mốc hoàn tất hoặc đối soát đã định nghĩa. Một khoảng sleep rồi “chưa thấy shipment thứ hai” không chứng minh tác dụng trùng sẽ không xuất hiện sau đó.

Ngoài các ca có lịch cụ thể, kiểm thử sinh chuỗi trạng thái có thể kết hợp retry, reorder, cancel và restart. Sau mỗi transition được commit, kiểm tra bất biến và lưu seed cùng lịch sự kiện để tái hiện.

## 14. Bài tập thực hành

### Bài tập 1: Viết bất biến không mơ hồ

Một hệ thống cấp quyền tải nội dung sau thanh toán. Payment và Entitlement là hai service riêng.

Hãy xác định:

- Thanh toán nào được xem là đủ điều kiện?
- Quyền tải gắn với tenant, người dùng và sản phẩm nào?
- Hoàn tiền tác động tới quyền đã cấp theo chính sách nào?
- Event thanh toán cũ có được cấp lại quyền đã bị thu hồi không?
- Authority nào phân xử các quyết định mâu thuẫn?

Tránh chỉ viết “payment và entitlement phải đồng bộ”.

### Bài tập 2: Tìm cửa sổ sai phiên bản

Order đọc payment success, sau đó nội dung đơn bị sửa, rồi Order đọc inventory success.

Thiết kế lại dữ liệu và giao thức để hai success không bị gộp nhầm. Nêu rõ snapshot nào bất biến và sự kiện nào buộc phải duyệt lại.

### Bài tập 3: Hủy trong lúc capture chưa rõ

Capture timeout nhưng có thể đã thu tiền. Người dùng bấm hủy.

Thiết kế các trạng thái, thời điểm cấm giao, cách giải phóng hàng và cách đối soát tiền. Chỉ ra điều kiện để cuối cùng được đánh dấu CANCELLED.

### Bài tập 4: Phát hiện giới hạn bảo đảm

Fulfillment có unique constraint theo order nhưng gọi một hệ thống kho không hỗ trợ idempotency và không tra cứu được kết quả.

Phân tích trường hợp kho đã nhận lệnh nhưng phản hồi bị mất. Nêu điều gì còn có thể bảo đảm và thông tin/giao thức nào cần bổ sung để ngăn gửi hai kiện khi retry.

## 15. Điểm cần nhớ

Bất biến liên dịch vụ là quan hệ giữa các hành động và dữ kiện có thẩm quyền, gắn với đúng tenant, đối tượng, snapshot và ý định nghiệp vụ.

Một thiết kế đáng tin cậy cần chỉ ra ai phân xử tài nguyên, cam kết nào còn hiệu lực, nơi nào quyết định giữa các nhánh xung đột và cách nhận diện cùng một operation qua retry. Outbox, inbox, saga, version và fencing hỗ trợ những phần khác nhau của giao thức; chúng không thay thế việc viết rõ bất biến.

Trong ví dụ đặt hàng, sự đồng thuận của các cờ success chưa đủ. Điều quyết định là có căn cứ phù hợp, có cam kết tài nguyên được bảo vệ và có một quyết định giao hợp lệ không thể bị vượt qua bởi hủy, event cũ hoặc đường gọi khác.
