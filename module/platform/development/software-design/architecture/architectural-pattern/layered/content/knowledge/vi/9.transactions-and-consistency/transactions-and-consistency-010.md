# Phối hợp quy trình nhiều bước hoặc nhiều kho dữ liệu khi không có một giao dịch chung

Bài học này thuộc module **SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED** — **Học tổ chức phần mềm theo kiến trúc phân tầng**, trong chương **Giao dịch và tính nhất quán**. Một use case có thể phải phối hợp nhiều bước ghi dữ liệu, nhiều dịch vụ hoặc nhiều cơ sở dữ liệu độc lập. Khi không có một transaction chung bao trùm tất cả thành phần, hệ thống cần một cách tổ chức để tiến trình có thể tiếp tục, thử lại, bù trừ hoặc được xử lý thủ công khi một bước thất bại.

Vấn đề này thường xuất hiện trong quy trình đặt hàng: giữ hàng trong kho, xác nhận thanh toán, tạo yêu cầu giao hàng và xác nhận đơn. Mỗi dịch vụ có thể sở hữu database riêng và transaction riêng. Không thể giả định một lệnh rollback ở dịch vụ đặt hàng sẽ tự hoàn tác khoản thanh toán hoặc lượng hàng đã được giữ ở hệ thống khác.

## 1. Giới hạn của một transaction cục bộ

Transaction cơ sở dữ liệu cục bộ thường bảo đảm các thao tác trong cùng một ranh giới được commit hoặc rollback như một đơn vị. Với Spring, một phương thức có **@Transactional** có thể gom nhiều thao tác trên cùng transaction manager và resource được cấu hình tham gia transaction đó.

Ví dụ, lưu đơn hàng và các dòng hàng trong cùng một database có thể nằm trong một transaction:

~~~java
@Transactional
public OrderId createOrder(CreateOrderCommand command) {
    Order order = Order.place(command.customerId(), command.lines());
    orderRepository.save(order);
    orderLineRepository.saveAll(order.lines());
    return order.id();
}
~~~

Nếu một thao tác ghi thất bại và exception làm transaction rollback theo cấu hình, các thay đổi trong transaction đó được hoàn tác cùng nhau. Tuy nhiên, transaction này không tự bao gồm:

- Một request HTTP đến dịch vụ thanh toán.
- Một lệnh giữ hàng được gửi đến dịch vụ kho.
- Một message đã được broker chuyển cho consumer.
- Một bản ghi được ghi vào database độc lập do một service khác quản lý.

Mỗi hệ thống có thể commit công việc của nó trước khi hệ thống gọi nhận được phản hồi. Nếu gọi dịch vụ thanh toán thành công rồi lưu đơn hàng thất bại, rollback database của đơn hàng không thể tự xóa khoản tiền đã được thanh toán. Tương tự, một message đã được gửi không tự biến mất khi transaction cục bộ của producer rollback sau đó.

Một số nền tảng hỗ trợ distributed transaction hoặc two-phase commit (2PC), nhưng chúng đòi hỏi resource manager và participant hỗ trợ giao thức, làm tăng coupling và chi phí vận hành. Chúng cũng có thể giữ tài nguyên trong thời gian chờ coordinator. Với nhiều HTTP service, message broker hoặc database không cùng hỗ trợ XA, một transaction toàn cục thường không khả thi. Thiết kế cần giả định mỗi participant tự commit transaction cục bộ và phối hợp kết quả qua giao thức ứng dụng.

## 2. Mô hình hóa quy trình như một chuỗi bước có trạng thái

Thay vì xem toàn bộ quy trình là một transaction kéo dài, hãy mô hình hóa nó thành các bước nghiệp vụ có ranh giới rõ:

1. Tạo đơn ở trạng thái chờ xử lý.
2. Yêu cầu kho giữ số lượng sản phẩm cần thiết.
3. Yêu cầu cổng thanh toán xác nhận hoặc thu tiền.
4. Tạo yêu cầu giao hàng.
5. Chuyển đơn sang trạng thái đã xác nhận.

Mỗi participant thực hiện thay đổi dữ liệu của chính nó trong một transaction cục bộ. Một thành phần điều phối hoặc các event liên kết các bước. Quy trình có trạng thái để hệ thống biết bước nào đã hoàn thành, bước nào đang chờ và bước nào cần thử lại hoặc bù trừ.

Ví dụ trạng thái đơn hàng có thể gồm:

| Trạng thái | Ý nghĩa |
|---|---|
| PENDING | Đã nhận yêu cầu, đang phối hợp các bước |
| INVENTORY_RESERVED | Kho đã giữ hàng |
| PAYMENT_AUTHORIZED | Thanh toán đã được xác nhận hoặc ủy quyền |
| CONFIRMED | Các bước bắt buộc đã hoàn tất, đơn được xác nhận |
| COMPENSATING | Đang thực hiện các hành động bù trừ |
| CANCELLED | Quy trình kết thúc bằng hủy đơn |
| REQUIRES_ATTENTION | Không thể tự phục hồi; cần xử lý thủ công |

Không phải hệ thống nào cũng cần tất cả trạng thái trên. Chọn trạng thái đủ để biểu diễn các quyết định và hành động phục hồi thực tế. Tránh chỉ dùng một cờ boolean vì nó không cho biết quy trình đang dừng ở bước nào.

## 3. Saga: phối hợp các transaction cục bộ

**Saga** là một chuỗi các transaction cục bộ, mỗi transaction cập nhật dữ liệu do một participant sở hữu và có thể kích hoạt bước tiếp theo. Nếu một bước không thể hoàn tất, quy trình có thể thực hiện các hành động bù trừ (compensating actions) cho những bước trước đó, hoặc tiếp tục theo một hướng phục hồi đã định.

Ví dụ đặt hàng:

| Bước | Transaction cục bộ | Hành động bù trừ có thể có |
|---|---|---|
| 1. Tạo đơn chờ | Lưu đơn PENDING | Hủy hoặc đánh dấu đơn thất bại |
| 2. Giữ hàng | Ghi reservation ở kho | Giải phóng reservation |
| 3. Thanh toán | Tạo authorization hoặc charge | Void authorization hoặc hoàn tiền |
| 4. Tạo giao hàng | Tạo shipment request | Hủy yêu cầu giao nếu hãng vận chuyển còn cho phép |
| 5. Xác nhận đơn | Chuyển đơn sang CONFIRMED | Nếu không thể xác nhận, bắt đầu quy trình bù trừ |

Một luồng thành công có thể được biểu diễn:

~~~mermaid
sequenceDiagram
    participant O as Order Service
    participant I as Inventory Service
    participant P as Payment Service
    participant S as Shipping Service

    O->>O: Lưu đơn PENDING
    O->>I: Reserve inventory
    I-->>O: Reservation confirmed
    O->>P: Authorize payment
    P-->>O: Payment authorized
    O->>S: Create shipment
    S-->>O: Shipment created
    O->>O: Chuyển đơn sang CONFIRMED
~~~

Nếu thanh toán bị từ chối sau khi kho đã giữ hàng, quy trình có thể giải phóng reservation và chuyển đơn sang CANCELLED. Nếu bước tạo giao hàng thất bại sau khi đã thu tiền, cần hủy authorization hoặc hoàn tiền tùy trạng thái thanh toán thực tế.

### Bù trừ không phải rollback

Rollback của database đưa các thay đổi trong transaction chưa commit về trạng thái trước transaction. Compensation là một hành động nghiệp vụ mới, được thực hiện trong một transaction khác sau khi bước trước đã commit. Vì thế, compensation không bảo đảm khôi phục chính xác mọi thứ như chưa từng xảy ra.

Ví dụ:

- Nếu chỉ mới authorize thẻ, có thể void authorization.
- Nếu đã capture/charge tiền, cần refund; tiền hoàn có thể mất thời gian mới xuất hiện.
- Nếu kho đã xuất hàng, không thể đơn giản xóa reservation; cần quy trình trả hàng hoặc xử lý giao nhận.
- Nếu hãng vận chuyển đã nhận kiện hàng, hủy shipment có thể cần yêu cầu riêng và có thể bị từ chối.

Mỗi hành động bù trừ phải phản ánh khả năng thực tế của nghiệp vụ. Có bước không thể bù trừ hoàn toàn; khi đó hệ thống cần forward recovery, quy trình xử lý ngoại lệ hoặc nhân viên can thiệp. Không nên thiết kế compensation chỉ bằng cách gọi lại phương thức với dữ liệu cũ mà không xác định trạng thái hiện tại của participant.

## 4. Hai cách điều phối saga

### Orchestration: có bộ điều phối trung tâm

Trong orchestration, một saga orchestrator hoặc process manager lưu trạng thái quy trình, quyết định bước tiếp theo và gửi command đến participant. Participant thực hiện công việc cục bộ rồi trả kết quả hoặc phát event. Orchestrator cập nhật trạng thái và quyết định tiếp tục, retry hay bù trừ.

~~~mermaid
flowchart TD
    U[Place order request] --> O[Saga orchestrator]
    O -->|Reserve command| I[Inventory service]
    I -->|Reserved / Rejected| O
    O -->|Authorize command| P[Payment service]
    P -->|Authorized / Declined| O
    O -->|Create shipment| S[Shipping service]
    S -->|Created / Failed| O
    O -->|Complete or compensate| R[Update order state]
~~~

Ưu điểm là luồng quy trình tập trung, dễ xem trạng thái và hiểu bước kế tiếp. Đổi lại, orchestrator có thể trở thành thành phần phức tạp nếu chứa quá nhiều logic của các domain khác. Nó nên điều phối tiến trình, còn participant vẫn sở hữu quy tắc và dữ liệu của chính mình.

Orchestrator có thể là một application service chạy trong một tiến trình, một workflow engine hoặc một process manager lưu trạng thái bền vững. Với quy trình kéo dài qua nhiều phút hoặc nhiều ngày, trạng thái phải được lưu để worker có thể tiếp tục sau khi ứng dụng khởi động lại.

### Choreography: các participant phản ứng với event

Trong choreography, không có một coordinator trung tâm ra lệnh cho mọi bước. Participant phát event khi hoàn thành công việc; participant khác đăng ký nhận event và tự quyết định hành động tiếp theo.

~~~mermaid
flowchart LR
    O[Order service] -->|OrderPlaced| B[(Message broker)]
    B --> I[Inventory service]
    I -->|InventoryReserved| B
    B --> P[Payment service]
    P -->|PaymentAuthorized| B
    B --> S[Shipping service]
    S -->|ShipmentCreated| B
    B --> O
~~~

Choreography giảm sự phụ thuộc vào một coordinator và có thể phù hợp khi các phản ứng giữa service đơn giản, event là hợp đồng tự nhiên giữa các bounded context. Nhưng khi nhiều nhánh điều kiện, timeout và compensation xuất hiện, luồng tổng thể có thể khó theo dõi vì logic được phân tán trong nhiều consumer. Khi đó, process manager hoặc orchestration thường giúp biểu diễn trạng thái rõ hơn.

| Tiêu chí | Orchestration | Choreography |
|---|---|---|
| Ai quyết định bước tiếp theo? | Orchestrator | Participant nhận event |
| Trạng thái quy trình | Thường tập trung ở process manager | Phân tán qua trạng thái của participant và event |
| Theo dõi luồng | Dễ quan sát thứ tự tại một nơi | Cần lần theo event giữa các consumer |
| Coupling | Participant biết command/contract của coordinator | Participant biết event contract mà nó đăng ký |
| Phù hợp khi | Nhiều bước, nhánh, timeout và compensation | Phản ứng đơn giản, độc lập và hướng event |

Không có cách nào luôn tốt hơn. Chọn theo độ phức tạp workflow, nhu cầu quan sát, mức độc lập của service và năng lực vận hành của nhóm.

## 5. Đảm bảo ghi dữ liệu và gửi message không bị lệch nhau

Một lỗi thường gặp là cập nhật database rồi gửi message trong hai thao tác riêng:

~~~java
@Transactional
public void place(Order order) {
    orderRepository.save(order);
    messageBroker.publish(new OrderPlaced(order.id()));
}
~~~

Transaction annotation chỉ quản lý resource tham gia transaction được cấu hình. Nếu database commit thành công nhưng publish message thất bại, hệ thống có đơn hàng mà không có event. Nếu message được publish nhưng database rollback, consumer có thể xử lý một đơn hàng chưa tồn tại.

### Transactional outbox

**Outbox pattern** giải quyết khoảng hở này bằng cách ghi trạng thái nghiệp vụ và bản ghi message vào cùng một database transaction. Một relay riêng đọc outbox và gửi message đến broker sau khi transaction commit.

~~~java
@Transactional
public void place(Order order) {
    orderRepository.save(order);
    outboxRepository.append(
            OutboxMessage.of("OrderPlaced", order.id().value()));
}
~~~

Trong cùng transaction, cả order và outbox record cùng commit hoặc rollback. Relay có thể gửi message nhiều lần nếu nó gửi thành công nhưng chưa kịp đánh dấu bản ghi đã phát trước khi tiến trình dừng. Vì vậy, outbox thường bảo đảm khả năng phát ít nhất một lần (at-least-once), không tự bảo đảm exactly-once ở phía consumer.

Consumer cần xử lý message trùng một cách an toàn. Một cách là dùng **inbox** hoặc bảng lưu message ID đã xử lý, đồng thời ghi dấu và thay đổi dữ liệu nghiệp vụ trong cùng local transaction:

~~~java
@Transactional
public void on(OrderPlaced event) {
    if (inboxRepository.exists(event.messageId())) {
        return;
    }

    inventory.reserve(event.orderId(), event.lines());
    inboxRepository.markProcessed(event.messageId());
}
~~~

Ví dụ trên giả định **inventory.reserve** thay đổi dữ liệu trong cùng transaction mà inbox sử dụng. Nếu nó gọi một hệ thống từ xa, hai thao tác đó lại có ranh giới khác; cần dùng outbox/command hoặc một cơ chế idempotency ở phía hệ thống đích. Không nên đánh dấu message đã xử lý trước khi tác động nghiệp vụ được commit.

Outbox relay cần có cơ chế claim hoặc lease để nhiều worker không gửi cùng bản ghi đồng thời ngoài dự kiến, xử lý retry có giới hạn và theo dõi message bị kẹt. Dùng CDC (change data capture) hay polling là lựa chọn triển khai; điều cốt yếu là outbox record được ghi nguyên tử cùng dữ liệu nghiệp vụ.

## 6. Idempotency, retry và kết quả không xác định

Trong hệ thống phân tán, timeout không nhất thiết có nghĩa participant chưa làm gì. Ví dụ, Payment Service có thể đã thu tiền và commit, nhưng phản hồi bị mất trên đường truyền. Nếu caller coi timeout là thất bại chắc chắn rồi gửi lại một lệnh thu tiền mới, khách hàng có thể bị charge hai lần.

### Idempotency key

Một command có thể mang một khóa idempotency ổn định, ví dụ **paymentAttemptId** hoặc **reservationId**. Participant lưu khóa cùng kết quả. Khi nhận lại cùng yêu cầu, participant trả kết quả đã ghi nhận thay vì thực hiện tác động lần nữa.

~~~java
public PaymentResult authorize(
        PaymentAttemptId attemptId,
        OrderId orderId,
        Money amount) {
    return paymentAttemptRepository.findResult(attemptId)
            .orElseGet(() -> authorizeAndStore(attemptId, orderId, amount));
}
~~~

Đoạn mã chỉ minh họa ý tưởng; việc kiểm tra khóa, thực hiện tác động và lưu kết quả phải được đồng bộ hóa bằng transaction/unique constraint hoặc cơ chế tương đương để hai request đồng thời không cùng thực hiện charge. Với provider bên ngoài, cần truyền idempotency key đến provider nếu họ hỗ trợ và giữ khóa ổn định qua mọi lần retry.

### Retry có chính sách

Retry hữu ích với lỗi tạm thời như timeout, lỗi mạng hoặc HTTP 5xx. Nó không phù hợp với mọi lỗi:

- Lỗi validation hoặc dữ liệu nghiệp vụ không hợp lệ thường không tự hết khi retry.
- Từ chối thanh toán là kết quả nghiệp vụ, không phải lỗi kết nối.
- Timeout sau khi gửi lệnh có thể tạo kết quả không xác định; nên tra cứu theo idempotency key trước khi quyết định gửi lại.

Chính sách retry nên có số lần tối đa, khoảng chờ tăng dần (exponential backoff), jitter, timeout tổng thể và giới hạn tốc độ. Sau khi hết retry, quy trình phải chuyển sang trạng thái chờ, bù trừ hoặc cần can thiệp; không retry vô hạn.

### Phân biệt các kết quả

| Kết quả | Ý nghĩa | Hành động tiếp theo |
|---|---|---|
| Thành công | Participant đã hoàn thành bước | Ghi nhận và tiếp tục |
| Từ chối nghiệp vụ | Participant hiểu yêu cầu nhưng không chấp nhận | Chuyển nhánh nghiệp vụ hoặc bù trừ |
| Lỗi tạm thời chắc chắn chưa commit | Có thể thử lại theo chính sách | Retry có giới hạn |
| Timeout / kết quả không xác định | Không biết participant đã commit hay chưa | Tra cứu trạng thái hoặc retry với cùng idempotency key |
| Lỗi không thể phục hồi tự động | Cần quyết định khác hoặc người vận hành | Chuyển trạng thái ngoại lệ |

## 7. Tính nhất quán cuối cùng và trải nghiệm người dùng

Khi các bước commit ở những thời điểm khác nhau, hệ thống thường chấp nhận **eventual consistency**: trong một khoảng thời gian, các service có thể quan sát trạng thái chưa đồng bộ; nếu thông điệp được xử lý thành công và không có lỗi kéo dài, trạng thái sẽ hội tụ về kết quả mong muốn.

Ví dụ, ngay sau khi người dùng đặt hàng, Order Service có thể trả trạng thái PENDING. Sau đó kho giữ hàng, thanh toán được xác nhận và shipment được tạo; đơn mới chuyển sang CONFIRMED. Người dùng cần được thông báo rõ rằng đơn đang xử lý, thay vì hiển thị như đã hoàn tất ngay khi chỉ mới tạo bản ghi.

Các màn hình đọc có thể lấy dữ liệu từ read model hoặc projection được cập nhật theo event. Vì projection có thể chậm hơn nguồn sự thật, API nên thể hiện trạng thái hoặc thời điểm cập nhật để client hiểu dữ liệu đang chờ đồng bộ. Với thao tác yêu cầu xác nhận ngay, hệ thống cần xác định chính xác bước nào bắt buộc hoàn tất trước khi trả thành công.

Không phải mọi nghiệp vụ đều chấp nhận eventual consistency. Ví dụ, số dư không được vượt hạn mức hoặc lượng tồn kho không được phân bổ quá mức có thể cần một kiểm soát nguyên tử ngay tại service sở hữu dữ liệu đó, chẳng hạn cập nhật có điều kiện, optimistic locking hoặc constraint database. Saga không thay thế invariant cục bộ của từng participant.

## 8. Phục hồi, bù trừ và vận hành workflow

Một workflow kéo dài cần lưu đủ thông tin để tiếp tục sau khi tiến trình hoặc máy chủ khởi động lại. Trạng thái saga thường cần:

- Saga ID và mã tương quan đến yêu cầu gốc.
- Trạng thái hiện tại và bước đã hoàn tất.
- ID của các command/message đã gửi và kết quả participant trả về.
- Idempotency key cho các tác động có thể lặp.
- Thời điểm bắt đầu, deadline, số lần retry và lịch sử lỗi.
- Thông tin cần thiết để chạy compensation hoặc forward recovery.

Không nên chỉ giữ trạng thái saga trong bộ nhớ của một instance. Nếu process restart, hệ thống phải khôi phục được công việc đang dở từ dữ liệu bền vững.

Khi một bước thất bại, hãy xác định chiến lược:

1. **Retry:** dùng khi lỗi có khả năng tạm thời và thao tác an toàn khi lặp.
2. **Forward recovery:** tiếp tục bằng một hành động thay thế hoặc yêu cầu mới để đạt mục tiêu.
3. **Compensation:** thực hiện hành động nghiệp vụ đối nghịch cho các bước đã commit.
4. **Manual intervention:** chuyển vào hàng đợi hoặc màn hình vận hành khi không thể quyết định tự động.

Các metric và log nên giúp trả lời: saga nào đang chờ lâu; participant nào lỗi nhiều; outbox message nào chưa phát; message nào bị retry liên tục; compensation nào thất bại; và quy trình nào cần người vận hành. Dùng correlation ID và saga ID xuyên qua log, trace và event để theo dõi một yêu cầu qua nhiều service. Không ghi dữ liệu nhạy cảm hoặc thông tin thanh toán đầy đủ vào log.

## 9. Kiểm thử quy trình nhiều bước

Kiểm thử không chỉ tập trung vào đường thành công. Cần kiểm tra các điểm đứt giữa những lần commit:

1. Giữ hàng thành công, thanh toán bị từ chối: reservation được giải phóng và đơn được hủy.
2. Thanh toán thành công nhưng phản hồi timeout: retry với cùng idempotency key không thu tiền lần hai.
3. Tạo shipment thất bại sau khi thanh toán: quy trình thực hiện void/refund phù hợp với trạng thái thanh toán.
4. Consumer nhận cùng event nhiều lần: tác động nghiệp vụ chỉ được áp dụng một lần theo khóa idempotency.
5. Relay gửi message rồi dừng trước khi đánh dấu outbox: message có thể được gửi lại nhưng consumer xử lý an toàn.
6. Compensation thất bại: saga chuyển sang trạng thái cần can thiệp và giữ đủ dữ liệu để vận hành xử lý.
7. Worker khởi động lại giữa quy trình: trạng thái đã lưu cho phép tiếp tục đúng bước.

Nên kết hợp:

- Unit test cho state machine hoặc logic điều phối.
- Integration test cho transaction cục bộ, outbox/inbox và unique constraint.
- Contract test cho command/event giữa các participant.
- End-to-end test cho một số luồng quan trọng.
- Fault injection hoặc mô phỏng timeout, duplicate, message trễ và lỗi broker để kiểm tra khả năng phục hồi.

Mock một participant có thể kiểm tra quyết định của orchestrator, nhưng không chứng minh broker, database và adapter hoạt động đúng khi có lỗi thực tế.

## 10. Khi nào nên chọn cơ chế nào?

| Tình huống | Cơ chế nên cân nhắc |
|---|---|
| Nhiều thay đổi trong cùng một database và transaction manager | Transaction cục bộ |
| Ghi dữ liệu và phát event phải cùng nhất quán | Transactional outbox |
| Consumer có thể nhận message lặp | Idempotent handler và inbox/deduplication |
| Nhiều service thực hiện quy trình có thứ tự và có nhánh | Saga orchestration |
| Các service phản ứng độc lập với event đơn giản | Choreography |
| Một bước đã commit cần được đảo bằng nghiệp vụ | Compensation |
| Timeout khiến không rõ participant đã commit chưa | Tra cứu trạng thái và idempotency key |
| Quy trình không thể tự phục hồi | Hàng đợi ngoại lệ và manual intervention |

Đừng áp dụng saga chỉ vì một use case có nhiều phương thức hoặc nhiều bảng. Nếu tất cả thay đổi thuộc cùng một database và cùng transaction, transaction cục bộ thường đơn giản và đáng tin cậy hơn. Saga hữu ích khi quy trình thực sự vượt qua các ranh giới transaction độc lập.

## 11. Checklist thiết kế

Trước khi triển khai workflow nhiều bước, hãy trả lời:

- Những dữ liệu nào do service hoặc database nào sở hữu?
- Mỗi bước có transaction cục bộ và trạng thái kết quả rõ ràng chưa?
- Bước nào có thể thất bại sau khi bước trước đã commit?
- Khi thất bại, nên retry, forward recovery, compensation hay yêu cầu người xử lý?
- Compensation có khả thi về nghiệp vụ và có thể thất bại không?
- Message có thể bị gửi lặp hoặc đến sai thứ tự không; participant xử lý thế nào?
- Command có idempotency key ổn định và trạng thái có thể tra cứu không?
- Ghi database và publish message có được nối bằng outbox không?
- Workflow có lưu trạng thái bền vững, deadline và lịch sử để phục hồi không?
- Người dùng và hệ thống downstream có nhìn thấy trạng thái đang chờ một cách chính xác không?

Khi không có một transaction chung, tính nhất quán được xây dựng từ các transaction cục bộ, trạng thái quy trình, hợp đồng message, idempotency và hành động phục hồi. Saga cung cấp cách phối hợp các bước; outbox/inbox giúp xử lý khoảng hở giữa database và message broker; retry và compensation xử lý lỗi theo ngữ nghĩa nghiệp vụ. Thiết kế tốt khi hệ thống có thể giải thích nó đang ở bước nào, điều gì đã commit, việc gì sẽ được thử lại hoặc bù trừ, và khi nào cần con người can thiệp.
