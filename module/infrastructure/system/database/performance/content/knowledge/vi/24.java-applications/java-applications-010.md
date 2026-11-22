# Ranh giới giao dịch Spring và tác động của gọi dịch vụ ngoài trong giao dịch

Trong ứng dụng Java dùng Spring, một phương thức có thể được đánh dấu **@Transactional** để nhiều thao tác cơ sở dữ liệu cùng tham gia một transaction. Vấn đề xuất hiện khi phương thức đó đồng thời gọi HTTP, RPC, gửi thông điệp hoặc chờ một dịch vụ bên ngoài. Thời gian chờ mạng có thể kéo dài transaction, giữ connection và lock lâu hơn, làm tăng thời gian chiếm connection pool, tạo lock wait và khiến throughput database giảm.

Đối với tối ưu hiệu năng cơ sở dữ liệu, ranh giới transaction cần bao quanh đúng phần công việc cần tính nguyên tử. Transaction quá rộng khiến tài nguyên database bị giữ trong lúc ứng dụng thực hiện công việc không thuộc database. Transaction quá hẹp lại có thể làm mất tính nhất quán nếu một nghiệp vụ gồm nhiều thay đổi cần commit cùng nhau. Vì vậy, cần hiểu Spring mở và kết thúc transaction như thế nào, biết chính xác khi nào connection và lock được giữ, rồi chọn cách phối hợp với dịch vụ ngoài phù hợp như gọi trước/sau transaction, transactional outbox hoặc Saga.

Bài học này trình bày cơ chế proxy và propagation của Spring, tác động của remote call trong transaction, timeout và rollback, các mẫu thiết kế thay thế, ví dụ Java/Spring và quy trình đo kiểm bằng connection pool metrics, database waits và latency.

## 1. Transaction trong Spring bắt đầu và kết thúc ở đâu?

@Transactional khai báo ngữ nghĩa transaction cho một phương thức hoặc lớp. Trong cấu hình Spring transaction thông thường, Spring dùng PlatformTransactionManager (hoặc một implementation tương ứng như JpaTransactionManager, DataSourceTransactionManager) để bắt đầu, tham gia, commit hoặc rollback transaction.

Ví dụ:

~~~java
@Service
public class OrderService {
    private final OrderRepository orderRepository;

    public OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public Order createOrder(CreateOrderCommand command) {
        Order order = Order.from(command);
        return orderRepository.save(order);
    }
}
~~~

Khi một lời gọi đi qua Spring transaction proxy, interceptor sẽ:

1. Kiểm tra metadata @Transactional.
2. Tìm transaction hiện có hoặc tạo transaction mới theo propagation.
3. Liên kết tài nguyên transaction với execution context phù hợp.
4. Gọi phương thức đích.
5. Commit nếu phương thức kết thúc bình thường.
6. Rollback nếu có exception thỏa quy tắc rollback.

Với ứng dụng imperative dùng JDBC/JPA, tài nguyên thường được gắn với thread hiện tại trong suốt transaction. Connection có thể được lấy ngay khi transaction bắt đầu hoặc được lấy trễ ở lần truy cập dữ liệu đầu tiên, tùy transaction manager, persistence provider và cấu hình. Khi connection đã được lấy và gắn với transaction, nó thường được giữ đến khi transaction hoàn tất.

Điểm quan trọng: @Transactional không tự biến mọi thao tác bên trong phương thức thành một transaction phân tán. Một lời gọi HTTP đến dịch vụ khác không tự động tham gia transaction JDBC của ứng dụng.

## 2. Proxy và ranh giới thực thi của @Transactional

Trong chế độ proxy phổ biến, Spring áp dụng transaction advice khi lời gọi đi qua proxy của bean. Điều này có một số hệ quả:

- Lời gọi từ bean khác đến phương thức được proxy có thể kích hoạt transaction.
- Lời gọi nội bộ từ một phương thức sang phương thức khác trong cùng instance (self-invocation) thường không đi qua proxy, nên annotation ở phương thức được gọi có thể không được áp dụng như kỳ vọng.
- Lời gọi trực tiếp bằng new thay vì lấy bean từ Spring container không có proxy transaction.
- Giới hạn đối với private, final hoặc phương thức không thể được proxy phụ thuộc loại proxy và cách cấu hình; không nên giả định annotation ở mọi vị trí đều được intercept.

Ví dụ dễ gây hiểu nhầm:

~~~java
@Service
public class PaymentService {
    public void process() {
        savePayment(); // self-invocation
    }

    @Transactional
    public void savePayment() {
        // ghi dữ liệu
    }
}
~~~

Nếu process() được gọi qua proxy, lời gọi savePayment() bên trong cùng object vẫn là lời gọi trực tiếp trên this; transaction advice của proxy thường không được chạy lần nữa. Hãy đặt ranh giới transaction ở phương thức được gọi từ bean khác, tách thao tác transaction sang bean riêng hoặc dùng cách cấu hình phù hợp với kiến trúc.

Một cách tách trách nhiệm:

~~~java
@Service
public class PaymentWriter {
    private final PaymentRepository repository;

    public PaymentWriter(PaymentRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void save(Payment payment) {
        repository.save(payment);
    }
}

@Service
public class PaymentFacade {
    private final PaymentWriter writer;

    public PaymentFacade(PaymentWriter writer) {
        this.writer = writer;
    }

    public void process(Payment payment) {
        writer.save(payment); // đi qua bean proxy
    }
}
~~~

Tách bean chỉ là một cách làm rõ ranh giới. Thiết kế cuối cùng vẫn cần bảo đảm transaction bao trọn đúng các thao tác dữ liệu cần nguyên tử.

## 3. @Transactional không bao trùm dịch vụ ngoài

Xét phương thức sau:

~~~java
@Service
public class OrderService {
    private final OrderRepository orderRepository;
    private final InventoryClient inventoryClient;

    @Transactional
    public void placeOrder(PlaceOrderCommand command) {
        Order order = orderRepository.save(Order.pending(command));
        inventoryClient.reserve(command.items());
        order.markConfirmed();
        orderRepository.save(order);
    }
}
~~~

Transaction database được mở khi lời gọi đi qua proxy. Khi inventoryClient.reserve() thực hiện HTTP/RPC, transaction database vẫn đang mở. Nếu dịch vụ kho mất 2 giây để phản hồi, transaction có thể giữ connection và các lock đã lấy trong khoảng thời gian đó.

Nếu dịch vụ ngoài timeout sau 10 giây, transaction có thể tồn tại gần 10 giây dù phần SQL chỉ cần vài mili giây. Trong thời gian này:

- Connection có thể bị giữ khỏi pool.
- Row lock hoặc key lock đã lấy có thể tiếp tục được giữ.
- Snapshot/MVCC transaction có thể tồn tại lâu hơn.
- Transaction log và trạng thái transaction chưa được giải phóng.
- Request khác có thể phải chờ lock hoặc connection.
- Khi lỗi xảy ra, rollback có thể phải đảo ngược nhiều thay đổi hơn.

Không phải mọi transaction đều lập tức lấy connection hoặc giữ lock ngay từ thời điểm interceptor bắt đầu. Nếu remote call diễn ra trước lần truy cập database đầu tiên và connection được lấy trễ, có thể chưa có connection/lock để giữ. Tuy nhiên, transaction boundary vẫn kéo dài; sau khi truy cập dữ liệu, các tài nguyên đã lấy sẽ bị giữ cho đến commit/rollback. Vì vậy, thứ tự thao tác và cơ chế lấy connection của stack cụ thể cần được kiểm tra.

## 4. Tác động đến connection pool

Pool có số connection hữu hạn. Mỗi transaction đang hoạt động thường chiếm một connection database trong thời gian cần thiết. Nếu transaction giữ connection lâu vì chờ dịch vụ ngoài, số connection sẵn sàng cho request khác giảm.

Ví dụ:

- Pool có tối đa 30 connection.
- 20 request đang ở trong transaction.
- Mỗi request đã cập nhật database rồi chờ dịch vụ thanh toán 1,5 giây.
- Chỉ còn tối đa 10 connection cho các request khác, dù database có thể xử lý SQL rất nhanh.

Theo Little's Law, số connection bị giữ trung bình có quan hệ với throughput và thời gian checkout:

\[
C_{avg}\approx \lambda\times T_{hold}
\]

Trong đó \(\lambda\) là số transaction mỗi giây và \(T_{hold}\) là thời gian connection được giữ. Nếu cùng throughput 100 transaction/s, thời gian giữ connection tăng từ 20 ms lên 1,5 s thì concurrency trung bình lý thuyết tăng từ 2 lên 150 connection. Khi pool chỉ có 30 connection, request sẽ xếp hàng hoặc timeout.

Đây là phép tính minh họa. Thực tế còn phụ thuộc transaction có lấy connection ở thời điểm nào, số connection mỗi request, concurrency, burst và thời gian phân phối. Nhưng nó cho thấy một remote call chậm bên trong transaction có thể làm pool cạn dù database không bận tương ứng.

### 4.1. Dấu hiệu pool bị chiếm bởi transaction dài

- Active/in-use connections gần max pool size.
- Pending/acquire queue và acquire wait tăng.
- Query execution time trên DB thấp nhưng checkout duration của ứng dụng cao.
- Nhiều session idle in transaction hoặc transaction age lớn.
- Một số request giữ connection lâu hơn thời gian SQL.
- CPU database có thể còn thấp trong khi ứng dụng báo pool timeout.

Để xác định nguyên nhân, cần ghép trace ứng dụng với session/transaction của database theo request hoặc correlation ID.

## 5. Tác động đến lock, MVCC và throughput

### 5.1. Lock được giữ đến khi transaction kết thúc

Với các thao tác UPDATE/DELETE và nhiều loại khóa khác, lock thường được giữ đến COMMIT hoặc ROLLBACK theo quy tắc của DBMS và isolation level. Nếu transaction gọi dịch vụ ngoài sau khi đã sửa dữ liệu, lock có thể bị giữ trong toàn bộ thời gian chờ mạng.

Ví dụ:

~~~sql
BEGIN;

UPDATE inventory
SET reserved_quantity = reserved_quantity + 1
WHERE product_id = 100;

-- Ứng dụng gọi dịch vụ vận chuyển trong lúc transaction vẫn mở

COMMIT;
~~~

Các transaction khác cần cập nhật cùng product_id có thể phải chờ. Một lời gọi HTTP chậm có thể biến một đoạn cập nhật ngắn thành lock duration dài.

### 5.2. MVCC và transaction/snapshot lâu

Trong hệ thống MVCC, transaction hoặc snapshot lâu có thể giữ lại phiên bản dữ liệu mà các truy vấn khác không còn cần. Điều này có thể làm chậm vacuum/purge hoặc thu hồi phiên bản cũ, tăng bloat/undo history và áp lực lưu trữ. Chi tiết phụ thuộc PostgreSQL, InnoDB, Oracle hoặc DBMS đang dùng.

Một session idle in transaction đặc biệt đáng chú ý: ứng dụng không chạy SQL nhưng transaction vẫn mở. Nó có thể giữ snapshot, lock hoặc connection và làm công việc dọn dẹp dữ liệu khó tiến triển.

### 5.3. Throughput giảm do hàng đợi

Khi transaction dài:

1. Connection bị chiếm lâu hơn.
2. Lock được giải phóng chậm hơn.
3. Request mới phải chờ connection hoặc lock.
4. Thời gian request tăng và số công việc đang tồn tại trong hệ thống tăng.
5. Retry hoặc timeout có thể làm tải tăng thêm.

Vì vậy, giảm thời gian giữ transaction thường cải thiện throughput và tail latency ngay cả khi tổng số câu SQL không đổi.

## 6. Phân biệt timeout của database và timeout của dịch vụ ngoài

Một transaction có thể liên quan nhiều loại timeout độc lập:

| Timeout | Phạm vi | Điều cần hiểu |
|---|---|---|
| Transaction timeout | Transaction manager/DBMS | Giới hạn thời gian transaction theo khả năng hỗ trợ của stack |
| Query/statement timeout | Câu SQL | Giới hạn thời gian thực thi statement |
| Lock wait timeout | Chờ lock | Giới hạn thời gian chờ khóa |
| HTTP connect timeout | Thiết lập kết nối tới dịch vụ | Giới hạn thời gian bắt tay/kết nối |
| HTTP read/response timeout | Chờ phản hồi | Giới hạn thời gian đợi dữ liệu trả về |
| Application request timeout | Toàn request | Giới hạn thời gian xử lý request ở tầng ứng dụng/gateway |
| Pool acquire timeout | Lấy connection | Giới hạn thời gian chờ pool cấp connection |

@Transactional(timeout = ...) không nên được hiểu là tự động đặt timeout cho mọi HTTP client. Transaction timeout có thể được transaction manager truyền tới JDBC statement hoặc được DBMS áp dụng theo cơ chế riêng; remote client cần connect/read/call timeout riêng.

Ví dụ:

~~~java
@Transactional(timeout = 3)
public void updateOrder() {
    // transaction timeout 3 giây theo khả năng transaction manager
    // không tự động đặt HTTP timeout 3 giây cho client bên ngoài
}
~~~

Đặt timeout cần có thứ bậc hợp lý. Timeout của dependency thường ngắn hơn deadline của request tổng thể để ứng dụng còn thời gian xử lý lỗi. Nếu HTTP timeout dài hơn transaction timeout, database transaction có thể rollback trong khi lời gọi ngoài vẫn tiếp tục hoặc đã hoàn tất. Nếu request timeout ở gateway nhưng server vẫn chạy, công việc có thể tiếp tục sau khi client đã bỏ cuộc.

## 7. Quy tắc rollback và lỗi từ dịch vụ ngoài

Theo mặc định của Spring declarative transaction, RuntimeException và Error thường kích hoạt rollback; checked exception không tự động rollback nếu không cấu hình thêm. Có thể dùng rollbackFor hoặc noRollbackFor để điều chỉnh.

Ví dụ:

~~~java
@Transactional(rollbackFor = PaymentDeclinedException.class)
public void confirmPayment() throws PaymentDeclinedException {
    // ghi dữ liệu và gọi logic thanh toán
}
~~~

Nếu HTTP client ném một runtime exception, transaction thường rollback khi exception thoát khỏi phương thức transaction. Nhưng nếu ứng dụng bắt exception rồi không ném lại, Spring có thể thấy phương thức kết thúc bình thường và commit, trừ khi transaction đã bị đánh dấu rollback-only.

Ví dụ dễ gây lỗi:

~~~java
@Transactional
public void placeOrder() {
    orderRepository.save(new Order());
    try {
        paymentClient.charge();
    } catch (PaymentException ex) {
        log.warn("Payment failed", ex);
        // Không rethrow, transaction có thể commit
    }
}
~~~

Nếu nghiệp vụ yêu cầu đơn hàng không được commit khi thanh toán thất bại, cách xử lý exception phải thể hiện rõ quyết định rollback. Nếu muốn lưu trạng thái PAYMENT_FAILED để xử lý tiếp, cần thiết kế trạng thái và transaction phù hợp thay vì nuốt exception một cách ngẫu nhiên.

Một điểm quan trọng khác: rollback database không thể hoàn tác một thao tác dịch vụ ngoài đã thành công. Nếu payment service đã thu tiền nhưng transaction local rollback, hai hệ thống không tự quay về cùng trạng thái. Đây là vấn đề nhất quán phân tán, không thể giải quyết chỉ bằng @Transactional.

## 8. Mẫu không nên dùng: gọi dịch vụ ngoài trong transaction dài

~~~java
@Transactional
public void checkout(CheckoutCommand command) {
    Order order = orderRepository.save(Order.pending(command));
    inventoryClient.reserve(command.items());   // mạng
    paymentClient.authorize(command.payment()); // mạng
    shippingClient.createShipment(order);       // mạng
    order.confirm();
}
~~~

Phương thức này gộp nhiều hệ thống vào một luồng đồng bộ và giữ transaction database xuyên suốt các lần gọi. Nếu mỗi dependency mất 500 ms, transaction có thể kéo dài hơn 1,5 giây cộng thời gian SQL và xử lý ứng dụng.

Các rủi ro:

- Tăng thời gian giữ connection và lock.
- Phụ thuộc vào độ trễ và availability của nhiều dịch vụ.
- Một dependency chậm làm transaction local kéo dài.
- Timeout không thể bảo đảm biết chính xác remote side đã thực hiện hay chưa.
- Rollback local không hoàn tác remote side.
- Retry toàn request có thể gửi lặp lệnh thanh toán hoặc giữ chỗ.

## 9. Mẫu 1: gọi dịch vụ ngoài trước transaction

Nếu thao tác ngoài không phụ thuộc vào dữ liệu vừa ghi trong transaction, có thể gọi nó trước, sau đó mở transaction ngắn để lưu kết quả:

~~~java
@Service
public class CheckoutService {
    private final PaymentClient paymentClient;
    private final OrderWriter orderWriter;

    public CheckoutService(
            PaymentClient paymentClient,
            OrderWriter orderWriter) {
        this.paymentClient = paymentClient;
        this.orderWriter = orderWriter;
    }

    public OrderResult checkout(CheckoutCommand command) {
        PaymentAuthorization authorization =
                paymentClient.authorize(command.payment());

        return orderWriter.saveAuthorizedOrder(command, authorization);
    }
}

@Service
public class OrderWriter {
    private final OrderRepository orderRepository;

    public OrderWriter(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public OrderResult saveAuthorizedOrder(
            CheckoutCommand command,
            PaymentAuthorization authorization) {
        Order order = Order.authorized(command, authorization.reference());
        orderRepository.save(order);
        return OrderResult.from(order);
    }
}
~~~

Transaction database chỉ bao quanh việc lưu đơn hàng. Tuy nhiên, payment authorization có thể thành công rồi thao tác lưu local thất bại. Cần có idempotency key, cơ chế void/reversal hoặc quy trình đối soát để xử lý tình huống đó. Cách gọi trước transaction chỉ phù hợp khi nghiệp vụ chấp nhận được khoảng thời gian giữa hai hệ thống và có cách bù trừ.

## 10. Mẫu 2: commit dữ liệu trước, gọi dịch vụ sau

Nếu dịch vụ ngoài cần thông tin đã được lưu, có thể ghi dữ liệu local trong transaction ngắn, commit, rồi gọi dependency ở bước sau:

~~~java
public OrderId createOrder(PlaceOrderCommand command) {
    return orderWriter.createPendingOrder(command);
}

@Service
public class OrderWriter {
    private final OrderRepository repository;

    @Transactional
    public OrderId createPendingOrder(PlaceOrderCommand command) {
        Order order = Order.pending(command);
        repository.save(order);
        return order.getId();
    }
}

public void continueCheckout(OrderId orderId) {
    OrderSnapshot snapshot = orderReader.load(orderId);
    inventoryClient.reserve(snapshot.items());
}
~~~

Sau commit, database không còn giữ transaction của bước tạo đơn trong lúc gọi inventory. Nhưng nếu process dừng sau commit và trước lời gọi ngoài, công việc tiếp theo có thể không bao giờ chạy. Nếu đây là nghiệp vụ quan trọng, cần lưu một công việc bền vững trong cùng transaction, thường bằng transactional outbox.

## 11. Mẫu 3: Transactional Outbox

Transactional outbox ghi thay đổi nghiệp vụ và một bản ghi sự kiện cần gửi trong cùng transaction local. Một relay riêng đọc outbox và gửi sự kiện tới broker hoặc dịch vụ ngoài sau khi transaction commit.

Ví dụ:

~~~java
@Service
public class OrderCommandService {
    private final OrderRepository orderRepository;
    private final OutboxRepository outboxRepository;

    public OrderCommandService(
            OrderRepository orderRepository,
            OutboxRepository outboxRepository) {
        this.orderRepository = orderRepository;
        this.outboxRepository = outboxRepository;
    }

    @Transactional
    public OrderId createOrder(CreateOrderCommand command) {
        Order order = Order.pending(command);
        orderRepository.save(order);

        OutboxEvent event = OutboxEvent.orderCreated(
                order.getId(),
                command.requestId());
        outboxRepository.save(event);

        return order.getId();
    }
}
~~~

Transaction commit đồng thời làm cho order và outbox event trở nên bền vững. Relay có thể chạy theo polling hoặc CDC để gửi sự kiện sau đó.

Luồng:

~~~text
Application
    |
    v
BEGIN local transaction
    |-- INSERT/UPDATE order
    |-- INSERT outbox event
    v
COMMIT
    |
    v
Outbox relay reads committed event
    |
    v
Message broker / remote service
    |
    v
Consumer handles event idempotently
~~~

Outbox tránh khoảng trống nguy hiểm giữa commit dữ liệu và ghi nhận ý định gửi sự kiện. Nếu process chết trước khi commit, cả order và outbox đều rollback. Nếu process chết sau commit, relay vẫn có thể tìm thấy event để gửi.

### 11.1. Outbox thường cung cấp at-least-once

Relay có thể gửi thành công nhưng chết trước khi đánh dấu event đã gửi. Khi khởi động lại, nó có thể gửi event lần nữa. Vì vậy, consumer cần idempotency:

- Mỗi event có ID duy nhất.
- Consumer lưu ID đã xử lý hoặc dùng business key duy nhất.
- Thao tác xử lý lặp phải không tạo hiệu ứng phụ trùng.
- Nếu gọi tiếp một dịch vụ khác, truyền idempotency key xuyên suốt.

Không giả định outbox tự cung cấp exactly-once end-to-end. Thông thường cần thiết kế at-least-once delivery kết hợp consumer idempotent.

### 11.2. Vận hành outbox

Theo dõi:

- Số event pending.
- Tuổi event cũ nhất chưa gửi.
- Tốc độ tạo và tốc độ gửi.
- Retry count và lỗi theo loại.
- Kích thước bảng outbox.
- Thời gian giữ event và chính sách archive/delete.
- Lock contention khi nhiều relay claim event.

Relay nên claim batch nhỏ, có lease/locking phù hợp và tránh giữ transaction database mở trong lúc gọi remote service. Một cách phổ biến là claim một nhóm event trong transaction ngắn, commit trạng thái claim, gửi bên ngoài, rồi cập nhật kết quả trong transaction khác. Cần xử lý crash và lease expiry để event không bị kẹt vĩnh viễn.

## 12. @TransactionalEventListener và giới hạn của callback sau commit

Spring hỗ trợ @TransactionalEventListener với các phase như BEFORE_COMMIT, AFTER_COMMIT, AFTER_ROLLBACK và AFTER_COMPLETION.

Ví dụ:

~~~java
@Component
public class OrderEventListener {
    private final NotificationClient notificationClient;

    public OrderEventListener(NotificationClient notificationClient) {
        this.notificationClient = notificationClient;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCreated(OrderCreatedEvent event) {
        notificationClient.notifyOrderCreated(event.orderId());
    }
}
~~~

Listener AFTER_COMMIT chỉ chạy khi transaction đã commit thành công, vì vậy lời gọi ngoài không còn kéo dài thời gian giữ lock của transaction trước theo cùng cách gọi trước commit. Tuy nhiên, đây vẫn là callback trong cùng tiến trình:

- Nếu process chết sau commit nhưng trước khi listener chạy, sự kiện trong bộ nhớ có thể mất.
- Nếu listener gọi dịch vụ chậm, request hoặc thread phát sự kiện có thể vẫn phải chờ tùy cách dispatch.
- Lỗi remote không thể rollback transaction đã commit.
- Nếu callback cần ghi dữ liệu database sau commit, cần chú ý tài nguyên transaction có thể vẫn được bind trong giai đoạn completion; dùng transaction mới phù hợp khi cần ghi thêm.

Vì vậy, @TransactionalEventListener(AFTER_COMMIT) hữu ích cho side effect best-effort hoặc tín hiệu nội bộ, nhưng không thay thế outbox khi cần bảo đảm công việc gửi ra ngoài không bị mất.

Có thể kết hợp AFTER_COMMIT để đánh thức outbox relay sớm, trong khi bản ghi outbox vẫn là nguồn công việc bền vững.

## 13. Khi nghiệp vụ trải qua nhiều dịch vụ: Saga và compensation

Nếu một quy trình cần cập nhật nhiều hệ thống độc lập, không thể dựa vào một transaction JDBC để rollback tất cả. Saga chia quy trình thành các bước local transaction; mỗi bước commit ở hệ thống của nó. Khi bước sau thất bại, hệ thống chạy hành động bù (compensation) để đưa nghiệp vụ về trạng thái hợp lệ.

Ví dụ đặt hàng:

1. Tạo order ở trạng thái PENDING.
2. Giữ hàng tại inventory.
3. Authorize payment.
4. Xác nhận order.
5. Nếu payment thất bại, yêu cầu inventory release reservation.
6. Nếu xác nhận cuối thất bại sau khi authorize, có thể void authorization theo quy tắc payment provider.

Mỗi bước cần:

- Transaction local ngắn.
- State machine hoặc trạng thái nghiệp vụ rõ.
- Command/event có ID để chống xử lý trùng.
- Timeout và retry có giới hạn.
- Compensation có thể chạy lại an toàn.
- Theo dõi quy trình đang ở bước nào và xử lý trạng thái không xác định.

Compensation không nhất thiết đảo ngược chính xác mọi hiệu ứng. Ví dụ, hoàn tiền không giống việc chưa từng thu tiền; thông báo đã gửi không thể thu hồi. Saga bảo đảm tiến trình nghiệp vụ có cách tiến tới trạng thái kết thúc hoặc cần can thiệp, chứ không tạo atomicity phân tán như một transaction đơn.

## 14. Propagation và việc mở thêm transaction

Spring hỗ trợ nhiều propagation behavior. Một số lựa chọn phổ biến:

| Propagation | Hành vi khái quát | Điểm cần chú ý |
|---|---|---|
| REQUIRED | Tham gia transaction hiện có hoặc tạo mới | Mặc định; lời gọi lồng nhau thường dùng chung transaction |
| REQUIRES_NEW | Tạm ngưng transaction hiện tại và tạo transaction mới | Có thể cần connection thứ hai trong khi transaction ngoài vẫn giữ tài nguyên |
| NESTED | Dùng nested transaction/savepoint nếu transaction manager hỗ trợ | Không phải transaction độc lập có thể commit bền vững riêng |
| SUPPORTS | Tham gia nếu có, nếu không thì chạy không transaction | Hành vi phụ thuộc transaction hiện có |
| NOT_SUPPORTED | Tạm ngưng transaction hiện tại và chạy không transaction | Transaction ngoài bị suspend, tài nguyên của nó có thể vẫn được giữ |
| MANDATORY | Yêu cầu phải có transaction hiện tại | Ném lỗi nếu không có |
| NEVER | Yêu cầu không có transaction | Ném lỗi nếu đang có transaction |

### 14.1. Không dùng REQUIRES_NEW như cách giải phóng connection

Ví dụ:

~~~java
@Transactional
public void process() {
    updateMainRecord();
    auditService.writeAudit(); // REQUIRES_NEW
}

@Transactional(propagation = Propagation.REQUIRES_NEW)
public void writeAudit() {
    auditRepository.save(...);
}
~~~

REQUIRES_NEW tạm ngưng transaction ngoài và mở transaction mới. Transaction ngoài có thể vẫn giữ connection đã lấy; transaction trong cần thêm connection. Nếu nhiều request cùng làm vậy và pool nhỏ, có thể cạn pool hoặc deadlock tài nguyên theo kiểu chờ connection.

REQUIRES_NEW phù hợp khi thao tác cần commit độc lập theo yêu cầu nghiệp vụ, ví dụ ghi audit phải tồn tại dù transaction chính rollback. Nó không phải thủ thuật để tách HTTP call hoặc giảm lock duration. Hãy kiểm tra connection pool capacity và số transaction lồng nhau.

### 14.2. NESTED không tương đương Saga

Nested transaction thường dựa trên savepoint trong cùng transaction vật lý. Rollback nested scope có thể quay về savepoint, nhưng commit nested scope không làm dữ liệu bền vững độc lập trước transaction ngoài. Nếu transaction ngoài rollback, phần nested đã commit vẫn rollback theo.

Không dùng NESTED để phối hợp dịch vụ ngoài hoặc thay thế distributed transaction.

## 15. Async và thread boundary

Trong mô hình imperative thông thường, Spring transaction context được gắn với thread hiện tại. Một tác vụ chạy qua @Async, executor hoặc thread mới không tự động tham gia transaction đang mở ở thread gọi.

Ví dụ:

~~~java
@Transactional
public void createOrder() {
    orderRepository.save(...);
    notificationService.sendAsync(...);
}
~~~

Nếu sendAsync chạy trên thread khác, nó không tự động chia sẻ JDBC transaction của thread hiện tại. Tác vụ async có thể bắt đầu trước khi transaction ngoài commit, hoặc thất bại sau khi transaction rollback. Nếu nó đọc dữ liệu mới ghi, có thể chưa nhìn thấy dữ liệu đó.

Các lựa chọn:

- Phát sự kiện sau commit bằng cơ chế phù hợp.
- Dùng outbox để bảo đảm sự kiện bền vững.
- Nếu tác vụ async cần transaction riêng, đặt @Transactional ở phương thức được gọi qua proxy trên worker thread.
- Không truyền connection hoặc EntityManager không thread-safe sang thread khác.

Với reactive transaction management, context thường được truyền qua Reactor Context thay vì ThreadLocal. Không áp dụng giả định thread-bound imperative cho reactive stack; hãy dùng API reactive và transaction manager tương ứng.

## 16. Giữ tính đúng đắn khi gọi dịch vụ ngoài

Tách remote call ra khỏi transaction không có nghĩa là có thể bỏ qua nhất quán. Cần xác định trạng thái trung gian và cách xử lý lỗi.

### 16.1. Idempotency key

Mỗi yêu cầu nghiệp vụ có một ID ổn định. Khi retry, gửi lại cùng ID để dịch vụ nhận biết đây là cùng một yêu cầu và không thực hiện hiệu ứng phụ lần thứ hai.

Ví dụ:

~~~http
POST /payments/authorize
Idempotency-Key: order-8450-authorize-v1
~~~

Khóa idempotency cần được lưu và xử lý nguyên tử ở phía dịch vụ nhận. Nếu chỉ gửi header mà server không lưu trạng thái, nó không bảo đảm chống trùng.

### 16.2. Timeout không xác định kết quả

Nếu client timeout, có thể:

- Request chưa đến server.
- Server đã nhận nhưng chưa xử lý.
- Server đã xử lý thành công nhưng phản hồi bị mất.
- Server đang xử lý và sẽ hoàn tất sau khi client bỏ chờ.

Không được mặc định timeout nghĩa là thao tác thất bại. Hãy dùng idempotency key, API tra cứu trạng thái hoặc reconciliation để xác định kết quả.

### 16.3. Retry có giới hạn và backoff

Retry ngay lập tức nhiều lần có thể làm dịch vụ đang lỗi quá tải hơn. Dùng exponential backoff, jitter, giới hạn số lần retry và deadline tổng. Phân biệt lỗi có thể retry như một số lỗi mạng tạm thời với lỗi nghiệp vụ không thể retry như thẻ bị từ chối.

### 16.4. Outbox/inbox

Outbox bảo đảm ý định gửi event được lưu cùng transaction local. Inbox hoặc bảng processed-message ở consumer giúp nhận diện event đã xử lý. Kết hợp hai cơ chế này giúp xây dựng xử lý at-least-once có tính idempotent.

## 17. Ví dụ hoàn chỉnh: đặt hàng bằng outbox

Một mô hình đơn giản:

~~~java
@Service
public class OrderApplicationService {
    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public OrderApplicationService(
            OrderRepository orders,
            OutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public UUID placeOrder(PlaceOrderCommand command) {
        Order order = Order.pending(
                command.customerId(),
                command.items(),
                command.requestId());
        orders.save(order);

        outbox.save(OutboxMessage.create(
                UUID.randomUUID(),
                "OrderPlaced",
                order.getId().toString(),
                command.requestId()));

        return order.getId();
    }
}
~~~

Relay:

~~~java
@Component
public class OutboxRelay {
    private final OutboxReader reader;
    private final InventoryClient inventoryClient;
    private final OutboxMarker marker;

    public void publishBatch() {
        List<OutboxMessage> batch = reader.claimNextBatch(50);

        for (OutboxMessage message : batch) {
            try {
                inventoryClient.reserve(
                        message.aggregateId(),
                        message.messageId().toString());
                marker.markPublished(message.messageId());
            } catch (TransientRemoteException ex) {
                // Giữ trạng thái pending/retry theo policy
            }
        }
    }
}
~~~

Đây là cấu trúc minh họa, không phải triển khai đầy đủ. Trong production, cần thiết kế claim/lease an toàn khi nhiều relay chạy, tránh giữ transaction mở qua remote call, cập nhật trạng thái published trong transaction ngắn, có retry schedule, dead-letter hoặc trạng thái cần xử lý thủ công, và bảo đảm consumer idempotent.

Nếu relay đánh dấu message đã gửi trong cùng một transaction đang giữ lock trong suốt lời gọi HTTP, vấn đề transaction dài lại xuất hiện. Hãy claim batch bằng transaction ngắn, commit claim, gọi remote bên ngoài transaction, rồi mở transaction khác để ghi kết quả.

## 18. Đo tác động trước và sau khi tách transaction

Một thay đổi thiết kế chỉ có giá trị khi đo được tác động đến ứng dụng và database.

### 18.1. Metric ở ứng dụng

- Request latency p50/p95/p99.
- Thời gian checkout và check-in connection.
- Pool active, idle, pending và acquire wait.
- Transaction duration.
- HTTP/RPC latency, timeout và retry count.
- Thời gian xử lý trước/sau transaction.
- Số request bị từ chối hoặc timeout.

### 18.2. Metric ở database

- Active sessions và idle-in-transaction.
- Transaction age và số transaction lâu nhất.
- Lock wait, blocked sessions và deadlocks.
- CPU, I/O latency, logical/physical reads.
- Connection count và worker availability.
- WAL/redo/log generation, flush latency.
- MVCC cleanup/vacuum/purge pressure tùy DBMS.
- Replication lag nếu ghi được sao chép.

### 18.3. So sánh một kịch bản

Giả sử thao tác tạo đơn gồm:

- SQL ghi đơn: 8 ms.
- HTTP reserve inventory: 700 ms.
- SQL xác nhận trạng thái: 4 ms.

Nếu cả ba bước nằm trong một transaction, connection có thể bị giữ khoảng 712 ms hoặc lâu hơn tùy thời gian xử lý và connection acquisition. Nếu tách thành hai transaction ngắn và một bước remote ở giữa, connection có thể chỉ được giữ khoảng 8 ms và 4 ms, cộng overhead transaction. Tuy nhiên, trạng thái nghiệp vụ lúc đó cần mô hình PENDING/RESERVED/CONFIRMED và xử lý bù trừ.

Không chỉ đo thời gian response của endpoint. Hãy xem connection hold time và lock duration có giảm hay không, replica có theo kịp không, và số lỗi/trạng thái trung gian có được xử lý đúng không.

## 19. Kiểm thử ranh giới transaction

Các tình huống cần kiểm tra:

1. Remote service phản hồi nhanh và thành công.
2. Remote service trả lỗi nghiệp vụ.
3. Remote service timeout trước khi xử lý.
4. Remote service đã xử lý nhưng response bị mất.
5. Database commit thất bại sau khi remote đã thành công.
6. Process chết sau commit nhưng trước khi gửi event.
7. Relay gửi event thành công nhưng chết trước khi đánh dấu published.
8. Consumer nhận cùng event nhiều lần.
9. Hai request cùng cập nhật một aggregate.
10. Pool cạn khi nhiều transaction đồng thời gọi remote chậm.

Với mỗi trường hợp, xác định trạng thái database, trạng thái dịch vụ ngoài, cách retry, cách compensation và khả năng khôi phục. Kiểm tra cả correctness lẫn latency/connection usage.

## 20. Những sai lầm thường gặp

- **Gọi HTTP trong transaction sau khi đã UPDATE.** Lock và connection có thể bị giữ trong suốt thời gian chờ mạng.
- **Nghĩ @Transactional bao trùm dịch vụ ngoài.** Transaction manager local không tự rollback HTTP/RPC.
- **Cho rằng mọi phương thức có annotation đều được intercept.** Self-invocation hoặc gọi object ngoài Spring có thể bỏ qua proxy.
- **Bắt exception rồi tiếp tục commit ngoài ý muốn.** Cần quy tắc rollback và trạng thái nghiệp vụ rõ ràng.
- **Cho rằng timeout nghĩa là remote thất bại.** Kết quả có thể không xác định.
- **Dùng REQUIRES_NEW để giải phóng connection.** Transaction ngoài có thể vẫn giữ tài nguyên trong khi transaction mới cần connection khác.
- **Dùng AFTER_COMMIT như outbox.** Callback trong bộ nhớ có thể mất nếu process chết sau commit.
- **Gửi async trước khi commit rồi để worker đọc dữ liệu mới.** Worker có thể chạy trước khi dữ liệu trở nên visible.
- **Retry không có idempotency.** Có thể thu tiền, giữ hàng hoặc gửi thông báo nhiều lần.
- **Giữ transaction mở trong lúc xử lý file/API hoặc chờ người dùng.** Connection và snapshot bị giữ không cần thiết.
- **Tách transaction mà không mô hình hóa trạng thái trung gian.** Dữ liệu có thể xuất hiện từng phần mà ứng dụng không hiểu cách xử lý.

## 21. Quy trình thiết kế và tối ưu

1. **Vẽ luồng nghiệp vụ.** Liệt kê thao tác database, remote call, message publish và điểm cần nguyên tử.
2. **Đặt ranh giới local transaction.** Gom các thao tác database phải commit/rollback cùng nhau; không đưa chờ mạng vào nếu không cần.
3. **Xác minh Spring proxy.** Kiểm tra self-invocation, bean lifecycle, transaction manager và propagation thực tế.
4. **Đo thời gian giữ connection.** So sánh checkout duration với SQL execution time và remote latency.
5. **Đo lock/snapshot.** Kiểm tra lock wait, transaction age và idle-in-transaction.
6. **Chọn chiến lược phối hợp.** Gọi trước/sau transaction nếu nghiệp vụ cho phép; dùng outbox cho event bền vững; dùng Saga khi cần nhiều local transaction và compensation.
7. **Thiết kế idempotency.** Mỗi command/event có ID ổn định, retry an toàn và consumer chống trùng.
8. **Đặt timeout theo tầng.** Query, lock, transaction, HTTP connect/read, pool acquire và request deadline cần nhất quán.
9. **Kiểm thử lỗi phân tán.** Bao gồm timeout không xác định, process crash, duplicate delivery và rollback.
10. **Benchmark dưới tải.** So sánh throughput, p95/p99, pool wait, transaction duration, lock wait và replication lag.
11. **Theo dõi sau triển khai.** Cảnh báo transaction dài, pool pending, outbox backlog, retry storm và trạng thái Saga bị kẹt.

## 22. Checklist kiểm chứng production

- [ ] Transaction bao quanh đúng các thay đổi database cần tính nguyên tử.
- [ ] Remote call không nằm trong transaction dài nếu không có yêu cầu rõ ràng.
- [ ] Đã xác minh phương thức @Transactional thực sự đi qua proxy.
- [ ] Đã kiểm tra self-invocation, propagation và transaction manager.
- [ ] Đã phân biệt thời gian SQL với thời gian giữ connection.
- [ ] Đã đo lock duration, transaction age và idle-in-transaction.
- [ ] Đã đặt timeout riêng cho transaction, query, lock, HTTP và pool acquire.
- [ ] Đã xác định rollback behavior cho checked/unchecked exception.
- [ ] Không giả định rollback local hoàn tác remote side effect.
- [ ] Đã có idempotency key và quy tắc xử lý timeout không xác định.
- [ ] Nếu dùng outbox, event được ghi cùng transaction nghiệp vụ.
- [ ] Relay không giữ transaction/connection trong khi chờ remote service.
- [ ] Consumer có khả năng xử lý duplicate an toàn.
- [ ] Nếu dùng AFTER_COMMIT, đã đánh giá nguy cơ mất callback khi process crash.
- [ ] Nếu dùng Saga, có state machine, retry, compensation và giám sát tiến trình.
- [ ] Đã kiểm tra async/thread boundary và không chia sẻ connection không an toàn.
- [ ] Đã benchmark pool active/pending, p95/p99, DB waits và replication lag.

Ranh giới transaction Spring quyết định thời gian connection, lock và snapshot được giữ, nên cần bao quanh phần thay đổi database thật sự cần tính nguyên tử. Gọi dịch vụ ngoài trong transaction có thể biến vài mili giây SQL thành hàng trăm mili giây hoặc nhiều giây giữ tài nguyên. Tách remote call ra khỏi transaction giúp giảm áp lực database, nhưng đòi hỏi mô hình trạng thái, idempotency và compensation phù hợp. Với công việc cần gửi ra ngoài sau commit, transactional outbox cung cấp ý định gửi bền vững; Saga phù hợp khi quy trình trải qua nhiều local transaction. Hãy xác minh proxy/propagation của Spring và đo connection hold time, lock wait, pool queue cùng latency dưới tải thực tế trước khi kết luận thay đổi đã cải thiện hiệu năng.
