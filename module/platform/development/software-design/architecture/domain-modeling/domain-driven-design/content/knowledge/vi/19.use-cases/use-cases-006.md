# Quản lý giao dịch ở lớp ứng dụng

Trong Domain-Driven Design (DDD), Application Layer điều phối các ca sử dụng: nhận ý định từ bên ngoài, nạp Aggregate cần thiết, gọi hành vi miền, lưu thay đổi và trả kết quả. Một trách nhiệm quan trọng của lớp này là xác định **ranh giới giao dịch (transaction boundary)** để những thay đổi cần nhất quán được commit hoặc rollback như một đơn vị.

Transaction không nên được mở tùy tiện quanh từng câu lệnh repository, cũng không nên kéo dài qua toàn bộ một quy trình nghiệp vụ nhiều phút hoặc nhiều hệ thống. Ranh giới phù hợp thường bắt đầu khi một use case cần đọc trạng thái có thẩm quyền và kết thúc khi các thay đổi trong một đơn vị nhất quán đã được lưu thành công.

Application Layer quyết định một use case cần phối hợp những thao tác nào và transaction bao quanh phần nào. Domain Model vẫn chịu trách nhiệm bảo vệ invariant; Repository và Unit of Work thực hiện persistence; Infrastructure cung cấp transaction manager cụ thể. Phân chia này giúp ứng dụng giữ được ý nghĩa nghiệp vụ mà không gắn domain vào database hay framework.

## 1. Transaction trong ứng dụng DDD là gì?

Transaction là một đơn vị công việc có quy tắc commit hoặc rollback. Với relational database, transaction thường dựa trên các thuộc tính ACID:

- **Atomicity:** các thay đổi trong transaction cùng thành công hoặc cùng bị hủy.
- **Consistency:** transaction đưa dữ liệu từ một trạng thái hợp lệ sang trạng thái hợp lệ theo các ràng buộc được bảo vệ.
- **Isolation:** các transaction đồng thời không nhìn thấy hoặc ghi đè dữ liệu theo cách vi phạm mức cô lập đã chọn.
- **Durability:** khi commit thành công, dữ liệu được lưu bền vững theo cam kết của hệ thống.

Trong DDD, cần xác định transaction phục vụ đơn vị nhất quán nào. Một transaction database thường được dùng để lưu thay đổi của một use case, đặc biệt khi use case thay đổi một Aggregate hoặc một số Aggregate trong cùng một consistency boundary đã được xác định.

Transaction không tự định nghĩa quy tắc nghiệp vụ. Nó chỉ cung cấp cơ chế kỹ thuật để các thay đổi được lưu nhất quán. Ví dụ, database transaction có thể bảo đảm cập nhật trạng thái đơn và các dòng hàng cùng commit, nhưng Aggregate vẫn phải kiểm tra đơn có được phép thay đổi hay không.

### Transaction không đồng nghĩa với toàn bộ business process

Một quy trình đặt hàng có thể gồm:

1. Nhận yêu cầu đặt hàng.
2. Kiểm tra và xác nhận đơn.
3. Thu tiền qua payment provider.
4. Yêu cầu kho giữ hàng.
5. Tạo shipment.
6. Gửi thông báo cho khách hàng.

Đây là một business process có thể kéo dài và đi qua nhiều hệ thống. Không nên giữ một database transaction mở từ bước 1 đến bước 6. Các bước ngoài database có độ trễ, có thể thất bại độc lập và không thể rollback bằng lệnh SQL thông thường.

Cần phân biệt:

| Khái niệm | Phạm vi | Ví dụ |
|---|---|---|
| Database transaction | Một đơn vị đọc/ghi trong một resource manager | Lưu Order và outbox record cùng commit |
| Application use case | Một hành động mà ứng dụng cung cấp | ConfirmOrder |
| Business process | Chuỗi hoạt động nghiệp vụ có thể kéo dài | Đặt hàng, thanh toán, thực hiện và giao hàng |
| Saga / Process Manager | Điều phối business process qua nhiều transaction | Thanh toán thành công rồi yêu cầu kho giữ hàng |

Một use case có thể chứa một transaction database ngắn. Một business process có thể chứa nhiều use case và nhiều transaction.

## 2. Vì sao Application Layer thường xác định transaction boundary?

Application Layer biết use case đang thực hiện và các bước cần phối hợp. Nó có thể xác định:

- Aggregate nào cần được nạp.
- Hành vi domain nào sẽ được gọi.
- Repository nào cần lưu thay đổi.
- Những thay đổi nào phải commit cùng nhau.
- Khi nào Unit of Work bắt đầu và kết thúc.
- Kết quả nào được trả về sau commit.
- Event nào cần được chuyển tiếp sau khi dữ liệu đã commit.

Domain Layer không nên tự mở transaction database hoặc phụ thuộc vào EntityManager, JDBC connection hay annotation của framework. Domain chỉ biểu diễn hành vi và invariant.

Infrastructure Layer triển khai transaction bằng công nghệ cụ thể. Application Layer dùng abstraction hoặc framework configuration để xác định ranh giới use case.

Một cách nhìn đơn giản:

    Interface / Adapter
          |
          v
    Application Use Case
       begin transaction
          |
          +--> load Aggregate
          |
          +--> invoke domain behavior
          |
          +--> save Aggregate
          |
          +--> commit
          |
          v
    Result to caller

Transaction boundary thường bao quanh toàn bộ phần xử lý cần nhất quán của use case, thay vì đặt riêng trên từng câu lệnh ghi.

## 3. Transaction boundary và Aggregate boundary

Aggregate là ranh giới nhất quán của mô hình miền. Aggregate Root bảo vệ invariant bên trong boundary đó. Đây là cơ sở quan trọng khi quyết định transaction.

Ví dụ, Aggregate Order chứa OrderLine. Khi thay đổi số lượng một dòng hàng, hệ thống có thể cần:

- Xác nhận Order còn ở trạng thái cho phép chỉnh sửa.
- Xác nhận OrderLine thuộc Order.
- Kiểm tra số lượng hợp lệ.
- Tính lại tổng tiền.
- Bảo đảm tổng tiền và các giới hạn của đơn vẫn hợp lệ.

Nếu các dữ liệu đó thuộc cùng Aggregate, một use case nên nạp Order, gọi hành vi của root và lưu Aggregate trong một transaction phù hợp.

    OrderRepository.findById(orderId)
        -> order.changeLineQuantity(lineId, quantity)
        -> OrderRepository.save(order)
        -> commit

Không nên mở transaction riêng cho OrderLine rồi transaction khác cho Order nếu các thay đổi phải nhất quán cùng nhau.

### Không phải lúc nào một transaction cũng chỉ có một Aggregate

DDD khuyến khích Aggregate nhỏ và giới hạn invariant cần nhất quán tức thời trong một Aggregate. Tuy vậy, một use case có thể cần cập nhật nhiều Aggregate trong cùng một database transaction nếu nghiệp vụ và kiến trúc yêu cầu tính nguyên tử đó.

Ví dụ, chuyển tiền giữa hai tài khoản trong cùng một bounded context có thể cần ghi giảm số dư tài khoản nguồn và ghi tăng số dư tài khoản đích trong một transaction để không có trạng thái chỉ trừ tiền mà chưa cộng tiền.

Tuy nhiên, việc thường xuyên cập nhật nhiều Aggregate trong cùng transaction có thể cho thấy:

- Invariant liên quan đang nằm ngoài Aggregate boundary.
- Các Aggregate có thể đang được phân chia chưa phù hợp.
- Use case thực sự cần một quy trình nhiều bước với eventual consistency.
- Transaction đang trở nên quá rộng và dễ xung đột.

Không nên dùng quy tắc "một transaction chỉ được ghi đúng một Aggregate" như luật tuyệt đối. Hãy xác định consistency requirement của nghiệp vụ và giữ transaction nhỏ nhất có thể mà vẫn bảo đảm yêu cầu đó.

## 4. Application Service điều phối transaction

Application Service hoặc command handler thường là điểm vào của một use case. Nó tải dữ liệu, gọi domain behavior, lưu thay đổi và trả kết quả.

Ví dụ:

    public final class ConfirmOrderHandler {
        private final OrderRepository orders;

        public ConfirmOrderHandler(OrderRepository orders) {
            this.orders = orders;
        }

        public ConfirmOrderResult handle(ConfirmOrderCommand command) {
            Order order = orders.findById(command.orderId())
                    .orElseThrow(OrderNotFoundException::new);

            order.confirm();

            orders.save(order);

            return ConfirmOrderResult.confirmed(order.id());
        }
    }

Ở ví dụ này, handler thể hiện trình tự nghiệp vụ ở mức ứng dụng. Transaction có thể được áp dụng bằng decorator, interceptor, transaction runner hoặc annotation trên application entry point tùy công nghệ.

Điểm quan trọng:

- Application Service không nên tự viết lại invariant của Order.
- Aggregate Root thực thi confirm() và từ chối chuyển trạng thái không hợp lệ.
- Repository chịu trách nhiệm lưu Aggregate.
- Transaction manager bảo đảm thay đổi được commit hoặc rollback.
- Kết quả thành công chỉ nên được công bố sau khi commit thành công.

### Không để Application Service trở thành nơi chứa toàn bộ domain logic

Một handler có quá nhiều điều kiện và thao tác trực tiếp field của entity thường là dấu hiệu domain model đang thiếu hành vi.

Ví dụ không tốt:

    if (order.status() == DRAFT && !order.lines().isEmpty()) {
        order.setStatus(CONFIRMED);
    }

Cách này lặp lại quy tắc ở application và có thể bị bỏ qua bởi một use case khác. Nên gọi:

    order.confirm();

Application Layer điều phối; Domain Layer quyết định hành vi đó có hợp lệ không.

## 5. Đặt transaction ở đâu trong code?

Có nhiều cách triển khai tùy framework và kiến trúc.

### Annotation trên use case

Với Spring, một application service có thể dùng @Transactional:

    @Service
    public class ConfirmOrderService {
        private final OrderRepository orders;

        public ConfirmOrderService(OrderRepository orders) {
            this.orders = orders;
        }

        @Transactional
        public ConfirmOrderResult handle(ConfirmOrderCommand command) {
            Order order = orders.findById(command.orderId())
                    .orElseThrow(OrderNotFoundException::new);

            order.confirm();
            orders.save(order);

            return ConfirmOrderResult.confirmed(order.id());
        }
    }

Annotation đặt ở use case cho thấy ranh giới transaction gắn với một hành động ứng dụng. Domain object không cần biết Spring.

Cần hiểu hành vi proxy của framework. Với cấu hình proxy mặc định của Spring, self-invocation trong cùng object có thể không đi qua proxy nên annotation trên method được gọi nội bộ có thể không kích hoạt transaction như mong đợi. Các trường hợp method visibility, proxy mode và transaction propagation cũng cần được hiểu theo cấu hình thực tế.

Không nên đặt @Transactional lên mọi method repository một cách máy móc. Nếu mỗi lệnh repository tự mở và commit một transaction độc lập, use case có thể mất tính nguyên tử giữa các thao tác.

### Transaction runner hoặc Unit of Work abstraction

Nếu muốn Application Layer ít phụ thuộc framework, có thể định nghĩa một abstraction:

    public interface TransactionRunner {
        <T> T execute(Supplier<T> work);
    }

Application handler dùng abstraction:

    public final class ConfirmOrderHandler {
        private final TransactionRunner transactions;
        private final OrderRepository orders;

        public ConfirmOrderHandler(
                TransactionRunner transactions,
                OrderRepository orders
        ) {
            this.transactions = transactions;
            this.orders = orders;
        }

        public ConfirmOrderResult handle(ConfirmOrderCommand command) {
            return transactions.execute(() -> {
                Order order = orders.findById(command.orderId())
                        .orElseThrow(OrderNotFoundException::new);

                order.confirm();
                orders.save(order);

                return ConfirmOrderResult.confirmed(order.id());
            });
        }
    }

Infrastructure có thể triển khai TransactionRunner bằng Spring transaction manager, JTA hoặc cơ chế phù hợp.

Đây là ví dụ khái niệm. Trong dự án thực tế, cần xác định rõ cách truyền exception, rollback rule, read-only transaction và transaction propagation. Không nên tạo abstraction nếu framework hiện tại đã cung cấp ranh giới đơn giản, dễ kiểm thử và không làm domain phụ thuộc vào nó.

## 6. Unit of Work và Repository phối hợp thế nào?

Unit of Work theo dõi các thay đổi trong một đơn vị công việc và phối hợp ghi chúng xuống persistence. Trong nhiều ORM, Unit of Work được framework thực hiện ngầm thông qua persistence context hoặc session.

Một luồng thường gặp:

1. Bắt đầu transaction và tạo persistence context.
2. Repository tải Aggregate.
3. Application gọi hành vi domain.
4. ORM theo dõi thay đổi hoặc repository đánh dấu Aggregate cần lưu.
5. Khi flush/commit, các thay đổi được ghi xuống database.
6. Nếu có lỗi, transaction rollback.

Có hai phong cách phổ biến:

- **Explicit save:** application gọi repository.save(aggregate) sau khi thay đổi.
- **Change tracking:** ORM theo dõi entity trong persistence context và tự flush khi commit.

Cả hai có thể phù hợp. Hãy chọn một quy ước rõ ràng và hiểu thời điểm dữ liệu thực sự được ghi.

save() không nhất thiết có nghĩa dữ liệu đã commit. Một số ORM chỉ đồng bộ thay đổi vào transaction khi flush; commit có thể xảy ra sau đó. Vì vậy không được phát thông báo thành công ra bên ngoài chỉ vì phương thức save đã trả về.

### Repository không nên tự tạo transaction độc lập cho từng thao tác

Nếu findById() mở transaction riêng rồi đóng, save() lại mở transaction khác, use case có thể không còn một snapshot hoặc một đơn vị rollback thống nhất. Repository thường tham gia transaction do use case hoặc tầng điều phối xác định.

Có thể có repository method chạy độc lập cho một tác vụ đơn giản, nhưng đó phải là quyết định có chủ đích chứ không phải hệ quả ngẫu nhiên của từng method.

## 7. Read-only transaction cho use case truy vấn

Không phải use case nào cũng thay đổi state. Các use case đọc có thể được đánh dấu read-only để thể hiện ý định và giúp framework/database tối ưu phù hợp.

Ví dụ:

    @Transactional(readOnly = true)
    public OrderDetails getOrder(OrderId id) {
        return queries.findOrderDetails(id);
    }

Read-only transaction có thể hữu ích để:

- Giữ các lần đọc trong một transaction nhất quán.
- Hạn chế flush ngoài ý muốn trong một số framework.
- Làm rõ use case không có ý định ghi.
- Cho phép database hoặc ORM áp dụng tối ưu phù hợp.

Tuy nhiên, readOnly = true không phải lúc nào cũng là một cơ chế bảo mật ngăn tuyệt đối mọi thao tác ghi. Hành vi cụ thể phụ thuộc transaction manager, driver và database. Nếu cần bảo đảm không ghi, hãy dùng quyền database hoặc API chỉ đọc phù hợp.

Với CQRS, query handler có thể đọc projection/read model thay vì khôi phục Aggregate đầy đủ. Query transaction vẫn cần lựa chọn isolation phù hợp với yêu cầu nhất quán của màn hình hoặc báo cáo.

## 8. Transaction và Domain Event

Một hành vi domain có thể tạo Domain Event, ví dụ OrderConfirmed. Event biểu diễn điều đã xảy ra trong domain. Nhưng event không nên được publish ra broker trước khi transaction lưu Aggregate commit thành công.

Một lỗi thường gặp:

    order.confirm();
    eventBus.publish(new OrderConfirmed(order.id()));
    orderRepository.save(order);

Nếu save hoặc commit thất bại, hệ thống bên ngoài đã nhận event trong khi Order chưa được xác nhận bền vững.

Cách an toàn hơn là ghi nhận event trong cùng Unit of Work và chỉ dispatch sau commit. Tuy nhiên, callback sau commit đơn thuần vẫn có thể mất event nếu tiến trình dừng sau commit nhưng trước khi publish.

### Transactional Outbox

Transactional Outbox giải quyết khoảng trống giữa database commit và message publish:

1. Application gọi domain behavior.
2. Transaction ghi Aggregate thay đổi.
3. Cùng transaction ghi một outbox record chứa event.
4. Database commit cả hai.
5. Một publisher riêng đọc outbox và gửi message ra broker.
6. Publisher đánh dấu record đã gửi hoặc lưu trạng thái retry.

~~~mermaid
sequenceDiagram
    participant App as Application
    participant DB as Database
    participant Outbox as Outbox Publisher
    participant Broker as Message Broker

    App->>DB: Update Aggregate
    App->>DB: Insert Outbox Event
    DB-->>App: Commit
    Outbox->>DB: Read pending events
    DB-->>Outbox: Event records
    Outbox->>Broker: Publish event
    Broker-->>Outbox: Acknowledge
    Outbox->>DB: Mark event as published
~~~

Outbox record và Aggregate update cùng commit nên không xảy ra trường hợp database đã đổi nhưng event chưa được ghi nhận để gửi.

Publisher có thể gửi lặp nếu bị dừng sau khi broker nhận event nhưng trước khi đánh dấu đã gửi. Vì vậy consumer cần idempotency hoặc deduplication. Outbox giúp bảo đảm không mất ý định publish khi commit thành công; nó không tự bảo đảm message chỉ được gửi đúng một lần.

### Event nội bộ và integration event

Domain Event phục vụ mô hình miền và có thể mang kiểu dữ liệu nội bộ. Integration Event là hợp đồng trao đổi giữa bounded context hoặc hệ thống khác. Không nên mặc định publish nguyên domain object hoặc toàn bộ event nội bộ ra broker.

Application/Infrastructure có thể ánh xạ Domain Event sang integration event ổn định, có version và chỉ chứa dữ liệu cần thiết.

## 9. Không giữ database transaction mở khi gọi dịch vụ ngoài

Một use case có thể cần gọi payment provider, shipping API hoặc dịch vụ định danh. Những lời gọi này có độ trễ và có thể thất bại độc lập với database.

Ví dụ không nên làm:

    begin database transaction
    load Order
    order.confirm()
    call payment provider (several seconds)
    call shipping provider
    save Order
    commit

Nếu dịch vụ ngoài chậm, database connection và lock bị giữ lâu. Nếu payment thành công nhưng transaction database rollback, hệ thống ở trạng thái không nhất quán giữa hai resource.

Một hướng tiếp cận thường dùng:

1. Transaction ngắn ghi nhận ý định hoặc chuyển trạng thái sang PAYMENT_PENDING.
2. Commit và phát integration event/command qua outbox.
3. Worker gọi payment provider ngoài transaction database ban đầu.
4. Kết quả được nhận lại qua message hoặc callback.
5. Một use case mới mở transaction, nạp Aggregate và cập nhật trạng thái theo kết quả.

Mỗi bước có transaction riêng và có thể retry. Quy trình tổng thể cần mô hình hóa trạng thái trung gian và xử lý thất bại.

### Khi nào vẫn có thể gọi dịch vụ ngoài trong transaction?

Một số thao tác rất nhanh và có kiểm soát có thể được gọi trong transaction vì yêu cầu cụ thể. Nhưng cần đánh giá thời gian chờ, khả năng timeout, khả năng retry và tính nhất quán. Mặc định nên tránh giữ transaction database trong khi chờ mạng.

## 10. Quy trình nhiều bước: Saga và Process Manager

Khi một business process cần phối hợp nhiều bounded context hoặc nhiều resource manager, một database transaction duy nhất thường không thể bao trùm toàn bộ quy trình.

Saga chia quy trình thành các bước local transaction. Mỗi bước commit dữ liệu trong context của nó và có thể phát event để kích hoạt bước tiếp theo. Nếu bước sau thất bại, quy trình có thể chạy hành động bù trừ (compensation) theo nghiệp vụ.

Ví dụ đặt hàng:

    OrderPlaced
        |
        v
    ReserveInventory
        |
        +--> InventoryReserved
        |        |
        |        v
        |    RequestPayment
        |        |
        |        +--> PaymentAuthorized
        |        |        |
        |        |        v
        |        |    ConfirmOrder
        |        |
        |        +--> PaymentFailed
        |                 |
        |                 v
        |             ReleaseInventory
        |
        +--> InventoryUnavailable
                 |
                 v
             CancelOrder

Mỗi bước như reserve inventory, authorize payment hay confirm order là một use case có transaction local. Saga/Process Manager theo dõi tiến trình và quyết định bước tiếp theo.

Compensation không phải rollback database. Nếu đã thu tiền, compensation có thể là hoàn tiền; nếu đã giữ hàng, compensation có thể là giải phóng reservation. Những hành động này có ý nghĩa nghiệp vụ riêng và có thể thất bại hoặc cần retry.

Không phải quy trình nào cũng cần Saga framework. Một process manager đơn giản hoặc workflow orchestration có thể đủ. Hãy chọn theo độ phức tạp và yêu cầu vận hành.

## 11. Transaction isolation và concurrency

Isolation level ảnh hưởng đến cách các transaction đồng thời nhìn thấy và thay đổi dữ liệu. Các mức phổ biến gồm:

| Isolation level | Đặc điểm khái quát | Vấn đề cần lưu ý |
|---|---|---|
| Read Uncommitted | Có thể đọc dữ liệu chưa commit ở một số hệ quản trị | Dirty read |
| Read Committed | Chỉ đọc dữ liệu đã commit | Non-repeatable read vẫn có thể xảy ra |
| Repeatable Read | Giữ ổn định dữ liệu đã đọc theo định nghĩa của database | Phantom và hành vi cụ thể tùy hệ quản trị |
| Serializable | Cố gắng cho kết quả tương đương thực thi tuần tự | Có thể giảm throughput và tăng retry |

Tên isolation level không bảo đảm mọi database triển khai hoàn toàn giống nhau. Cần xem tài liệu của hệ quản trị đang dùng và kiểm thử với workload thực tế.

Isolation level không thay thế domain invariant. Nếu Order không được phép xác nhận khi không có dòng hàng, Aggregate vẫn phải kiểm tra điều đó. Database constraint và transaction isolation bổ sung thêm lớp bảo vệ cho dữ liệu.

### Optimistic concurrency

Với optimistic locking, Aggregate hoặc persistence record có version. Khi lưu, repository chỉ cập nhật nếu version vẫn bằng expected version đã đọc.

    UPDATE orders
    SET status = ?, version = version + 1
    WHERE id = ?
      AND version = ?

Nếu không có dòng nào được cập nhật, có thể đã xảy ra concurrent modification. Application cần xử lý theo chính sách: nạp lại Aggregate, đánh giá lại command hoặc trả conflict để người dùng quyết định.

Không nên retry trên object cũ. Mỗi lần retry phải dùng state mới và đánh giá lại invariant.

### Pessimistic locking

Pessimistic locking khóa record hoặc tài nguyên trong transaction để ngăn thay đổi cạnh tranh. Nó có thể phù hợp khi xung đột cao và phạm vi khóa nhỏ, nhưng cần tránh giữ khóa lâu, khóa theo thứ tự không nhất quán hoặc tạo deadlock.

Không nên chọn isolation level cao nhất hoặc khóa mọi dữ liệu theo mặc định. Chọn cơ chế theo invariant và contention thực tế.

## 12. Retry và rollback

Khi một thao tác thất bại, cần phân biệt nguyên nhân:

- Domain rule bị vi phạm: không retry tự động chỉ vì lỗi.
- Optimistic concurrency conflict: có thể reload và re-evaluate.
- Deadlock: có thể retry toàn bộ transaction bằng transaction mới theo policy.
- Network timeout tới dịch vụ ngoài: cần retry riêng với idempotency.
- Database connection failure: tùy thời điểm lỗi, kết quả commit có thể không rõ; cần xử lý cẩn thận.
- Validation error: yêu cầu đầu vào cần được sửa, retry không giúp ích.

Transaction rollback chỉ hoàn tác các thay đổi thuộc transaction resource đó. Nó không thể tự thu hồi email đã gửi, payment đã được provider chấp nhận hoặc message đã publish.

Vì vậy, mọi retry phải xét đến side effect và idempotency. Không nên bọc toàn bộ business process trong một vòng retry chung.

### Rollback rule

Framework có thể phân biệt exception nào kích hoạt rollback. Ví dụ trong Spring, mặc định transaction rollback với unchecked exception và Error, còn checked exception có quy tắc khác trừ khi được cấu hình. Cần xác định rollback rule rõ cho exception nghiệp vụ và lỗi kỹ thuật; đừng giả định mọi exception đều tự động rollback theo cùng cách.

## 13. Idempotency trong use case có transaction

Client có thể gửi lại cùng request vì timeout hoặc người dùng bấm nút nhiều lần. Nếu use case tạo đơn, thu tiền hoặc giữ hàng, xử lý lặp có thể tạo side effect trùng.

Idempotency key giúp nhận diện cùng một ý định:

    command:
      idempotencyKey = "REQ-2026-001"
      customerId = C-42
      amount = 500000

Một cách triển khai thường gặp:

1. Nhận key và kiểm tra đã có kết quả được lưu chưa.
2. Nếu đã hoàn tất, trả lại kết quả trước đó.
3. Nếu chưa có, ghi nhận key trong transaction với unique constraint phù hợp.
4. Thực hiện thay đổi nghiệp vụ và lưu kết quả.
5. Commit.
6. Nếu request được gửi lại, đọc lại kết quả theo key.

Idempotency cần được thiết kế theo phạm vi và thời hạn nghiệp vụ. Không nên chỉ kiểm tra key trong bộ nhớ vì nhiều instance có thể nhận cùng request.

Với external provider, cần dùng idempotency key của provider nếu có, hoặc một cơ chế đối soát phù hợp. Database transaction nội bộ không bảo đảm provider chỉ xử lý một lần.

## 14. Transaction propagation và nested use case

Một use case có thể gọi service khác. Nếu cả hai đều khai báo transaction, framework phải quyết định cách transaction lồng nhau hoặc tham gia transaction hiện tại.

Các propagation mode thường gặp trong Spring:

- REQUIRED: tham gia transaction hiện tại hoặc tạo transaction mới nếu chưa có.
- REQUIRES_NEW: tạm treo transaction hiện tại và tạo transaction độc lập.
- MANDATORY: yêu cầu phải có transaction hiện tại.
- SUPPORTS: tham gia nếu có, nếu không thì chạy không transaction.
- NOT_SUPPORTED: tạm treo transaction hiện tại và chạy không transaction.
- NEVER: yêu cầu không có transaction hiện tại.

Không nên chọn propagation chỉ để làm lỗi biến mất. Ví dụ, dùng REQUIRES_NEW cho thao tác ghi một phần của cùng Aggregate có thể khiến thao tác đó commit ngay cả khi use case bên ngoài rollback. Điều này có thể phá vỡ tính nguyên tử mà nghiệp vụ cần.

Một use case gọi use case khác cần làm rõ:

- Có thực sự là một transaction chung không?
- Phần được gọi có thể commit độc lập không?
- Nếu phần ngoài rollback, kết quả phần trong có được phép tồn tại không?
- Có cần tách thành business process với event/saga không?

Đừng để propagation mode trở thành cách ngẫu nhiên quyết định consistency.

## 15. Transaction dài và dữ liệu người dùng chỉnh sửa

Một form có thể được mở trong vài phút. Người dùng tải Order, chỉnh sửa trên giao diện rồi bấm Save. Không nên giữ database transaction và lock trong suốt thời gian người dùng suy nghĩ.

Thay vào đó:

1. Khi mở form, đọc dữ liệu cùng version.
2. Người dùng chỉnh sửa ở client.
3. Khi submit, mở transaction mới.
4. Nạp hoặc cập nhật với expected version.
5. Nếu version đã thay đổi, trả conflict để ứng dụng hiển thị khác biệt hoặc yêu cầu người dùng quyết định.
6. Commit khi thay đổi hợp lệ.

Đây là optimistic concurrency ở ranh giới request. Transaction database chỉ tồn tại trong thời gian xử lý submit.

Không nên nhầm transaction database với conversation hoặc workflow dài của người dùng. Một business process dài cần trạng thái bền vững và cơ chế tiếp tục, không phải một transaction mở liên tục.

## 16. Quản lý transaction trong kiểm thử

Transaction có thể ảnh hưởng đến cách viết integration test.

### Unit test domain

Domain unit test thường không cần database transaction. Chúng kiểm tra:

- Hành vi Aggregate.
- Invariant.
- Chuyển trạng thái.
- Domain Event được tạo.
- Trường hợp domain từ chối hành động.

Nếu unit test domain cần khởi tạo Spring context hoặc database chỉ để kiểm tra một quy tắc, cần xem lại sự phụ thuộc của domain model.

### Application test

Application test có thể dùng fake repository và transaction runner giả để kiểm tra trình tự use case. Tuy nhiên, fake không chứng minh database rollback thực sự hoạt động.

### Repository/transaction integration test

Integration test nên kiểm tra:

- Nhiều thay đổi thuộc một use case cùng commit.
- Nếu một bước ghi thất bại, các thay đổi trước đó rollback.
- Outbox record và Aggregate update cùng transaction.
- Optimistic locking phát hiện version conflict.
- Transaction propagation đúng như cấu hình.
- Read-only behavior theo database/framework đang dùng.
- Retry mở transaction mới và nạp lại dữ liệu mới.

Ví dụ kịch bản:

| Kịch bản | Kết quả mong đợi |
|---|---|
| ConfirmOrder thành công | Order được lưu ở trạng thái CONFIRMED |
| Domain method từ chối | Không có thay đổi được commit |
| Lưu Aggregate thất bại | Transaction rollback |
| Outbox insert thất bại | Aggregate update cũng rollback |
| Hai request cùng ghi version cũ | Một request thành công, request còn lại nhận conflict |
| Request lặp cùng idempotency key | Không tạo nghiệp vụ trùng |
| Consumer xử lý event lặp | Không lặp side effect theo idempotency policy |

Test nên dùng database hoặc môi trường gần với production khi hành vi isolation, locking và constraint là trọng tâm. In-memory database có thể có semantics khác hệ quản trị production.

## 17. Những sai lầm thường gặp

### Mở transaction quá rộng

Giữ transaction trong lúc gọi HTTP, chờ người dùng hoặc xử lý nhiều bước kéo dài làm tăng thời gian giữ connection và lock.

### Mở transaction quá hẹp

Mỗi repository method tự commit khiến một use case có thể lưu một phần thay đổi rồi thất bại ở phần khác.

### Đưa transaction vào Domain Entity

Entity gọi transaction manager hoặc phụ thuộc ORM làm domain bị gắn với hạ tầng. Hãy để Application điều phối và Infrastructure triển khai.

### Để Application Service chứa invariant

Transaction không thay thế Aggregate behavior. Một transaction hoàn toàn có thể commit một trạng thái nghiệp vụ sai nếu domain không bảo vệ invariant.

### Publish event trước commit

Consumer có thể xử lý một event cho thay đổi chưa bao giờ được lưu thành công. Dùng outbox hoặc cơ chế after-commit có bảo đảm phù hợp.

### Nghĩ rollback có thể hoàn tác mọi side effect

Database rollback không thu hồi payment, email hoặc message đã gửi. Những tác động đó cần compensation, idempotency hoặc workflow riêng.

### Dùng REQUIRES_NEW không có lý do

Transaction độc lập có thể commit một phần công việc dù use case ngoài thất bại. Hãy xác định rõ ý nghĩa nghiệp vụ trước khi dùng.

### Retry mọi exception

Business rejection, validation failure, optimistic conflict và network timeout có nguyên nhân khác nhau. Chúng cần policy riêng.

### Không xử lý kết quả commit không rõ ràng

Nếu kết nối bị ngắt đúng lúc commit, client có thể không biết transaction đã thành công hay chưa. Idempotency key và khả năng tra cứu kết quả giúp xử lý an toàn.

### Dùng transaction thay cho Saga

Một transaction database không thể giữ nguyên tử cho toàn bộ các dịch vụ độc lập. Quy trình phân tán cần local transaction, event và compensation.

## 18. Quy trình thiết kế transaction cho một use case

Có thể dùng các bước sau khi thiết kế một application use case:

1. **Mô tả ý định:** xác định command/query và kết quả nghiệp vụ cần đạt.
2. **Xác định Aggregate:** liệt kê root cần nạp và invariant phải bảo vệ.
3. **Xác định consistency requirement:** dữ liệu nào bắt buộc phải commit cùng nhau?
4. **Vẽ transaction boundary:** bắt đầu trước khi đọc state có thẩm quyền và kết thúc sau khi lưu các thay đổi cần nguyên tử.
5. **Đặt domain behavior:** gọi hành vi Aggregate thay vì sửa field trực tiếp.
6. **Xác định event:** event nào phát sinh từ thay đổi và cần lưu cùng transaction?
7. **Xử lý external interaction:** chuyển lời gọi mạng sang bước bất đồng bộ hoặc workflow phù hợp khi có thể.
8. **Chọn concurrency strategy:** optimistic/pessimistic locking, isolation level và retry policy theo contention.
9. **Xác định idempotency:** request lặp có thể tạo side effect trùng không?
10. **Kiểm thử commit/rollback:** xác minh transaction behavior với persistence thực tế.

## 19. Checklist transaction boundary

Trước khi hoàn thiện use case, hãy kiểm tra:

- Transaction boundary có gắn với use case rõ ràng không?
- Aggregate Root có tự bảo vệ invariant không?
- Các thay đổi cần nhất quán có nằm trong cùng transaction không?
- Transaction có được giữ ngắn và tránh chờ network không?
- Repository có tham gia transaction của use case thay vì tự commit từng phần không?
- Có hiểu rõ Unit of Work và thời điểm flush/commit không?
- Domain Event có được ghi cùng transaction hoặc dispatch sau commit an toàn không?
- Outbox có cần thiết để tránh mất integration event không?
- Consumer và side effect có idempotency không?
- Optimistic conflict, deadlock và timeout có policy retry riêng không?
- Transaction propagation có đúng ý nghĩa nghiệp vụ không?
- Business process nhiều bước có cần Saga/Process Manager không?
- Read-only use case có ranh giới phù hợp không?
- Integration test có xác minh rollback, locking và outbox không?

## 20. Kết luận

Application Layer quản lý transaction boundary vì nó hiểu use case cần phối hợp những hành động nào và những thay đổi nào phải được commit cùng nhau. Aggregate Root vẫn là nơi bảo vệ invariant; Repository và Unit of Work phối hợp persistence; Infrastructure cung cấp transaction manager và cơ chế lưu trữ.

Một transaction tốt đủ rộng để bảo đảm tính nhất quán cần thiết, nhưng đủ ngắn để không giữ tài nguyên trong lúc chờ hệ thống bên ngoài hoặc một business process dài. Khi quy trình đi qua nhiều bounded context, hãy dùng local transaction kết hợp event, outbox, idempotency và Saga/Process Manager thay vì cố kéo dài một transaction database.

Tách rõ use case, Aggregate boundary, transaction boundary và business process giúp ứng dụng xử lý thay đổi một cách đáng tin cậy, đồng thời giữ domain model độc lập với công nghệ lưu trữ và điều phối cụ thể.
