# Phối hợp nhiều repository, commit, rollback và xử lý ghi cạnh tranh

Một ca sử dụng trong hệ thống đơn hàng thường phải cập nhật nhiều loại dữ liệu: tạo đơn hàng, giảm số lượng tồn kho, ghi nhận thanh toán hoặc lưu sự kiện để gửi sang hệ thống khác. Nếu mỗi repository tự commit riêng, một phần công việc có thể thành công trong khi phần còn lại thất bại. Ví dụ, tồn kho đã giảm nhưng đơn hàng không được tạo; hoặc đơn hàng đã lưu nhưng sự kiện xác nhận không được ghi.

Tầng Application là nơi điều phối các bước của ca sử dụng và xác định ranh giới giao dịch. Khi nhiều repository cùng tham gia một thao tác nghiệp vụ cần nguyên tử, chúng phải cùng tham gia một transaction phù hợp. Database chịu trách nhiệm thực thi commit hoặc rollback; các repository cung cấp thao tác đọc/ghi trong transaction đó. Ngoài ra, khi nhiều request cùng cập nhật một bản ghi, cần cơ chế bảo vệ khỏi lost update, ghi đè dữ liệu hoặc vi phạm bất biến.

Trong module **Học tổ chức phần mềm theo kiến trúc phân tầng**, bài học này tập trung vào cách phối hợp nhiều repository trong ứng dụng Java/Spring, hiểu chính xác thời điểm commit và rollback, và chọn chiến lược xử lý ghi cạnh tranh theo đặc tính của nghiệp vụ.

## 1. Vì sao một use case cần phối hợp nhiều repository?

Một repository thường đại diện cho khả năng lưu trữ của một aggregate hoặc một nhóm dữ liệu. Một use case có thể cần phối hợp nhiều repository vì một hành động nghiệp vụ ảnh hưởng đến nhiều phần dữ liệu.

Ví dụ, khi khách hàng đặt hàng:

1. Đọc thông tin sản phẩm và giá được phép bán.
2. Giữ chỗ hoặc trừ tồn kho.
3. Tạo đơn hàng và các dòng hàng.
4. Ghi một sự kiện OrderPlaced vào outbox để xử lý sau commit.

Các thao tác này có quan hệ nghiệp vụ. Nếu giữ chỗ tồn kho thất bại, không được tạo đơn hàng ở trạng thái đã xác nhận. Nếu lưu đơn hàng thất bại sau khi tồn kho đã giảm, phần giảm tồn kho phải được rollback nếu cả hai thao tác cùng nằm trong một transaction database.

~~~mermaid
sequenceDiagram
    participant C as OrderController
    participant A as PlaceOrderService
    participant P as ProductRepository
    participant I as InventoryRepository
    participant O as OrderRepository
    participant X as OutboxRepository
    participant DB as Database
    C->>A: place(command)
    A->>P: findProduct(productId)
    P-->>A: Product
    A->>I: reserve(productId, quantity)
    I->>DB: UPDATE inventory
    A->>O: save(order)
    O->>DB: INSERT order
    A->>X: append(OrderPlaced)
    X->>DB: INSERT outbox
    A-->>C: result (sau khi transaction commit)
~~~

Sơ đồ giả định các repository cùng ghi vào một database và tham gia cùng transaction manager. Nếu chúng dùng các database độc lập hoặc gọi dịch vụ từ xa, một transaction Spring thông thường không tự làm cho toàn bộ thao tác trở thành nguyên tử.

## 2. Đặt ranh giới transaction ở application service

Application service biết một ca sử dụng gồm những bước nào và điều kiện nào khiến toàn bộ thao tác được xem là thành công. Vì vậy, ranh giới transaction thường đặt ở phương thức use case, thay vì để từng repository tự commit.

~~~java
@Service
public class PlaceOrderService {
    private final ProductRepository products;
    private final InventoryRepository inventory;
    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public PlaceOrderService(
            ProductRepository products,
            InventoryRepository inventory,
            OrderRepository orders,
            OutboxRepository outbox) {
        this.products = products;
        this.inventory = inventory;
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public PlaceOrderResult place(PlaceOrderCommand command) {
        Product product = products.findById(command.productId())
                .orElseThrow(ProductNotFoundException::new);

        boolean reserved = inventory.reserve(
                product.getId(),
                command.quantity()
        );

        if (!reserved) {
            throw new InsufficientStockException();
        }

        Order order = Order.place(
                command.customerId(),
                product.getId(),
                product.currentPrice(),
                command.quantity()
        );

        orders.save(order);
        outbox.append(new OrderPlacedEvent(order.getId()));

        return new PlaceOrderResult(order.getId());
    }
}
~~~

Ví dụ minh họa các repository cùng tham gia một transaction. Các kiểu Product, Order và repository cần được định nghĩa theo mô hình của ứng dụng. Quy tắc đặt hàng thuộc Domain; Application service chỉ điều phối việc tải dữ liệu, gọi hành vi nghiệp vụ và lưu kết quả.

Với transaction propagation mặc định là REQUIRED, các lời gọi repository có transaction riêng theo cấu hình của chúng thường tham gia transaction đang tồn tại nếu dùng cùng transaction manager. Nếu không có transaction bên ngoài, transaction được mở khi phương thức service đi qua Spring proxy.

Cần bảo đảm các repository thực sự dùng cùng transaction manager và cùng tài nguyên database nếu muốn commit/rollback nguyên tử. Chỉ gắn @Transactional lên service không thể gom nhiều database hoặc một HTTP service vào cùng local transaction.

## 3. Commit xảy ra khi nào?

Khi caller gọi một Spring bean qua proxy, transaction interceptor thực hiện các bước khái quát:

1. Bắt đầu transaction mới hoặc tham gia transaction hiện có theo propagation.
2. Gọi phương thức application service.
3. Nếu phương thức kết thúc bình thường, interceptor yêu cầu transaction commit nếu đây là ranh giới sở hữu transaction.
4. Nếu phương thức ném exception thuộc chính sách rollback, transaction được rollback.
5. Caller chỉ nhận kết quả sau khi proxy hoàn tất xử lý transaction.

~~~mermaid
sequenceDiagram
    participant Caller as Controller / Caller
    participant Proxy as Spring Transaction Proxy
    participant S as Application Service
    participant DB as Database
    Caller->>Proxy: place(command)
    Proxy->>DB: BEGIN
    Proxy->>S: invoke target method
    S->>DB: repository reads/writes
    S-->>Proxy: return result
    Proxy->>DB: COMMIT
    DB-->>Proxy: commit success
    Proxy-->>Caller: result
~~~

Điều này có một hệ quả quan trọng: phương thức service có thể đã chạy đến câu lệnh return nhưng commit vẫn có thể thất bại, ví dụ do constraint, deadlock hoặc lỗi kết nối ở thời điểm flush/commit. Caller bên ngoài proxy chỉ nhận kết quả thành công nếu quá trình commit hoàn tất.

Với JPA, save có thể chỉ cập nhật persistence context mà chưa gửi SQL ngay. SQL có thể được thực thi khi flush hoặc commit. Vì vậy, một lỗi constraint hoặc optimistic locking đôi khi chỉ xuất hiện ở cuối transaction. Gọi save thành công không đồng nghĩa dữ liệu đã commit.

Nếu service được gọi nội bộ bằng self-invocation, chẳng hạn một phương thức trong cùng object gọi phương thức khác có @Transactional, lời gọi đó thường không đi qua proxy ở chế độ proxy mặc định của Spring. Annotation có thể không được áp dụng như mong đợi. Hãy đặt ranh giới transaction trên phương thức được gọi qua bean proxy hoặc tổ chức lại service để tránh self-invocation.

## 4. Khi nào commit và rollback cùng nhiều repository?

Giả sử inventory.reserve đã cập nhật tồn kho, nhưng orders.save gặp lỗi. Nếu cả hai thao tác dùng cùng database transaction, lỗi làm transaction rollback thì thay đổi tồn kho cũng bị rollback.

| Tình huống | Kết quả mong đợi khi cùng transaction |
|---|---|
| Giữ chỗ tồn kho thành công, lưu đơn thành công, ghi outbox thành công | Commit tất cả |
| Không đủ tồn kho và use case ném lỗi | Không tạo đơn; không có thay đổi tồn kho |
| Tồn kho đã cập nhật nhưng lưu đơn thất bại | Rollback cả thay đổi tồn kho |
| Đơn đã lưu nhưng ghi outbox thất bại | Rollback cả đơn và các thay đổi cùng transaction |
| Commit thành công nhưng response bị mất | Dữ liệu vẫn đã commit; client cần retry an toàn hoặc truy vấn kết quả |

Rollback chỉ áp dụng cho những thay đổi thuộc transaction được quản lý. Nó không thể tự hoàn tác email đã gửi, HTTP request đã được đối tác xử lý hoặc message đã publish ra broker. Những tác động ngoài database cần cơ chế riêng như Transactional Outbox, idempotency hoặc hành động bù trừ.

## 5. Chính sách rollback của Spring

Theo mặc định, Spring đánh dấu rollback khi phương thức transactional ném RuntimeException hoặc Error. Checked exception thường không tự kích hoạt rollback theo mặc định.

~~~java
@Transactional
public void placeOrder() throws PricingException {
    // Nếu PricingException là checked exception,
    // mặc định transaction có thể không rollback.
}
~~~

Nếu một checked exception phải làm rollback, có thể khai báo rõ:

~~~java
@Transactional(rollbackFor = PricingException.class)
public void placeOrder() throws PricingException {
    // ...
}
~~~

Các lựa chọn khác gồm rollbackFor = Exception.class hoặc thiết kế exception ứng dụng phù hợp. Không nên chọn rollback mọi exception một cách máy móc nếu có trường hợp nghiệp vụ được xem là kết quả bình thường. Hãy định nghĩa chính sách theo hợp đồng use case.

Một số lỗi thường gặp:

- Bắt exception rồi chỉ ghi log và trả về bình thường: transaction có thể commit vì interceptor thấy phương thức kết thúc bình thường.
- Bắt exception rồi tiếp tục ghi dữ liệu khác: có thể để lại trạng thái không nhất quán.
- Ném checked exception nhưng mong Spring tự rollback: cần cấu hình rollbackFor nếu chính sách yêu cầu.
- Gọi setRollbackOnly khi cần hủy transaction nhưng sau đó trả kết quả thành công: caller có thể hiểu sai vì dữ liệu cuối cùng không được commit.

Nếu đã bắt lỗi nhưng quyết định transaction phải rollback, có thể ném lại exception hoặc đánh dấu rollback-only qua transaction API phù hợp. Thường cách rõ ràng nhất là để lỗi truyền tới ranh giới transaction và chuyển đổi thành response ở tầng ngoài.

## 6. Transaction propagation: REQUIRED, REQUIRES_NEW và NESTED

Propagation quyết định cách một phương thức transactional tham gia transaction hiện tại:

| Propagation | Hành vi chính | Khi cân nhắc |
|---|---|---|
| REQUIRED | Tham gia transaction hiện tại; nếu chưa có thì tạo mới | Mặc định và thường phù hợp cho các repository/use case cùng một nghiệp vụ |
| REQUIRES_NEW | Tạm treo transaction hiện tại và tạo transaction độc lập | Chỉ khi tác động cần commit độc lập có chủ đích |
| NESTED | Dùng nested transaction/savepoint nếu transaction manager hỗ trợ | Khi cần rollback một phần có kiểm soát trong cùng transaction vật lý |

Ví dụ, nếu inventory.reserve dùng REQUIRES_NEW, nó có thể commit giảm tồn kho trước khi transaction tạo đơn hoàn tất. Nếu orders.save sau đó thất bại, transaction ngoài rollback nhưng phần tồn kho đã commit vẫn còn. Điều đó phá vỡ yêu cầu “đặt hàng thất bại thì không giữ tồn kho” trừ khi nghiệp vụ có quy trình bù trừ riêng.

Vì vậy, không nên gắn REQUIRES_NEW lên mọi repository method. Hãy chọn propagation theo semantics nghiệp vụ. REQUIRED thường là lựa chọn đúng khi nhiều thao tác phải thành công hoặc thất bại cùng nhau.

NESTED phụ thuộc transaction manager và hỗ trợ savepoint; không phải mọi cấu hình JPA/database đều cung cấp hành vi nested như mong muốn. Cần xác minh với công nghệ đang dùng trước khi dựa vào nó.

## 7. Nhiều repository nhưng khác database hoặc hệ thống từ xa

Một transaction manager JDBC/JPA thông thường chỉ quản lý một phạm vi tài nguyên. Nếu Orders ghi vào database A, Billing gọi database B hoặc dịch vụ thanh toán từ xa, @Transactional ở Orders không tự rollback được thay đổi ở B.

Có ba trường hợp cần phân biệt:

- **Cùng database, cùng transaction manager:** có thể dùng local transaction để commit/rollback nguyên tử.
- **Nhiều datasource độc lập:** mỗi datasource có transaction riêng, trừ khi hệ thống dùng giải pháp transaction phân tán được cấu hình và hỗ trợ rõ ràng.
- **HTTP service hoặc broker:** không tham gia local database transaction; cần workflow, outbox/inbox, idempotency hoặc saga/compensation.

Ví dụ, sau khi lưu đơn hàng, không nên gọi trực tiếp cổng thanh toán rồi giả định database rollback sẽ hoàn tác việc thu tiền. Có thể lưu trạng thái PAYMENT_PENDING và outbox event trong transaction; worker gọi provider bằng idempotency key, sau đó cập nhật kết quả thanh toán trong transaction khác.

~~~mermaid
flowchart LR
    A[Place Order use case] --> T[(Order + Outbox commit)]
    T --> W[Outbox worker]
    W --> P[Payment provider]
    P --> R[Payment result]
    R --> U[Update order/payment state]
~~~

Đây là quy trình nhiều bước với trạng thái trung gian và eventual consistency. Nếu thanh toán thất bại, hệ thống cập nhật trạng thái hoặc chạy hành động bù trừ phù hợp. Không mô tả nó như một rollback ACID duy nhất xuyên qua database và provider.

## 8. Ghi cạnh tranh: lost update xảy ra như thế nào?

Giả sử tồn kho sản phẩm là 5. Hai khách hàng đồng thời đặt mỗi người 4 sản phẩm:

1. Request A đọc available = 5.
2. Request B cũng đọc available = 5.
3. A kiểm tra đủ hàng và tính số còn lại là 1.
4. B cũng kiểm tra đủ hàng và tính số còn lại là 1.
5. Cả hai ghi available = 1.

Kết quả cuối cùng là 1, dù tổng số lượng đã được đặt là 8. Hệ thống đã chấp nhận vượt tồn kho nhưng dữ liệu không thể hiện đúng lượng hàng đã bán. Đây là lost update/race condition do thao tác đọc rồi ghi không được bảo vệ.

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant B as Request B
    participant DB as Inventory DB
    A->>DB: Read available = 5
    B->>DB: Read available = 5
    A->>A: Check 5 >= 4
    B->>B: Check 5 >= 4
    A->>DB: Write available = 1
    B->>DB: Write available = 1
    Note over DB: Hai request được chấp nhận dù tổng lượng đặt là 8
~~~

Một transaction đơn thuần không luôn ngăn được lost update. Với isolation READ COMMITTED, hai transaction có thể đọc cùng một giá trị trước khi ghi. Cần chọn cơ chế concurrency control phù hợp với dữ liệu và nghiệp vụ.

## 9. Optimistic locking với @Version

Optimistic locking giả định xung đột không thường xuyên. Entity có một trường version; khi cập nhật, JPA kiểm tra version hiện tại có còn bằng version đã đọc không. Nếu một transaction khác đã cập nhật trước, transaction sau thất bại thay vì âm thầm ghi đè.

~~~java
@Entity
public class InventoryItem {
    @Id
    private UUID productId;

    private int available;

    @Version
    private long version;

    public void reserve(int quantity) {
        if (quantity <= 0 || available < quantity) {
            throw new InsufficientStockException();
        }
        available -= quantity;
    }
}
~~~

Khi hai transaction cùng đọc version 7, transaction đầu cập nhật thành công và version tăng lên 8. Transaction còn lại cố ghi với version 7 sẽ nhận optimistic locking conflict. Ứng dụng cần xử lý conflict bằng cách đọc lại và đánh giá nghiệp vụ lần nữa, hoặc trả lỗi để client thử lại.

Optimistic locking phù hợp khi xung đột hiếm, transaction ngắn và việc retry không quá tốn kém. Nó không tự động giải quyết mọi race condition giữa nhiều aggregate hoặc nhiều bảng; cần xác định dữ liệu nào phải được bảo vệ chung.

Với JPA, OptimisticLockException có thể phát sinh khi flush hoặc commit. Vì vậy, code bắt exception ngay quanh lệnh save có thể không bắt được nếu lỗi chỉ xuất hiện lúc transaction interceptor commit. Retry nên đặt ở bên ngoài ranh giới transaction để mỗi lần thử là một transaction mới.

## 10. Pessimistic locking khi cần khóa bản ghi

Pessimistic locking khóa bản ghi trong lúc transaction xử lý để transaction khác phải chờ hoặc thất bại theo timeout. Với Spring Data JPA, có thể dùng LockModeType.PESSIMISTIC_WRITE:

~~~java
public interface InventoryJpaRepository
        extends JpaRepository<InventoryItem, UUID> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
        select i from InventoryItem i
         where i.productId = :productId
        """)
    Optional<InventoryItem> findForUpdate(
            @Param("productId") UUID productId);
}
~~~

Application service tải bản ghi có khóa, kiểm tra số lượng và cập nhật trong transaction:

~~~java
@Transactional
public void reserve(UUID productId, int quantity) {
    InventoryItem item = inventory.findForUpdate(productId)
            .orElseThrow(ProductNotFoundException::new);

    item.reserve(quantity);
    inventory.save(item);
}
~~~

Transaction giữ khóa cho tới commit hoặc rollback. Request thứ hai phải chờ khóa được giải phóng, rồi mới đọc trạng thái mới nhất và kiểm tra số lượng còn lại.

Pessimistic locking có thể phù hợp khi xung đột thường xuyên và việc đọc rồi quyết định phải được tuần tự hóa. Đổi lại, nó làm tăng thời gian chờ, nguy cơ deadlock và áp lực connection. Cần transaction ngắn, timeout hợp lý và thứ tự lấy khóa nhất quán.

## 11. Cập nhật có điều kiện nguyên tử trong database

Với thao tác tồn kho, một câu UPDATE có điều kiện thường là cách gọn và mạnh:

~~~sql
UPDATE inventory
   SET available = available - :quantity
 WHERE product_id = :productId
   AND available >= :quantity;
~~~

Database thực hiện điều kiện và phép cập nhật như một thao tác nguyên tử đối với hàng được cập nhật. Application kiểm tra số hàng bị ảnh hưởng:

- 1 hàng: giữ chỗ thành công.
- 0 hàng: sản phẩm không tồn tại hoặc không đủ tồn kho; cần phân biệt bằng truy vấn bổ sung nếu hợp đồng cần thông báo riêng.

Interface repository có thể biểu đạt ý định:

~~~java
public interface InventoryRepository {
    boolean reserve(ProductId productId, int quantity);
}
~~~

Adapter trả true khi câu lệnh cập nhật đúng một hàng. Cách này tránh mẫu read-check-write tách rời. Tuy nhiên, cần kiểm tra quantity dương trước khi chạy SQL, bảo đảm số học không tràn và hiểu cách ORM đồng bộ persistence context nếu cùng entity đã được tải trước đó. Bulk update có thể bỏ qua trạng thái entity đang nằm trong persistence context; cần clear/refresh hoặc thiết kế luồng không giữ entity cũ.

Không phải mọi nghiệp vụ đều có thể giải quyết bằng một câu UPDATE có điều kiện. Khi quy tắc cần nhiều aggregate hoặc nhiều bảng, có thể kết hợp transaction, optimistic/pessimistic locking và constraint ở database.

## 12. Isolation level và các bất thường khi đọc/ghi

Isolation level quy định transaction nhìn thấy thay đổi của transaction khác ở mức nào. Tên và hành vi cụ thể có thể khác theo database:

| Mức isolation | Ý nghĩa khái quát | Lưu ý |
|---|---|---|
| READ UNCOMMITTED | Có thể đọc dữ liệu chưa commit | Một số database không hỗ trợ hoặc nâng lên mức khác |
| READ COMMITTED | Chỉ đọc dữ liệu đã commit | Có thể đọc cùng hàng hai lần và thấy giá trị khác nhau |
| REPEATABLE READ | Bảo đảm dữ liệu đã đọc không thay đổi theo semantics của database | Cách xử lý phantom và ghi cạnh tranh tùy hệ quản trị |
| SERIALIZABLE | Cố tạo kết quả tương đương thực hiện tuần tự | Có thể phát sinh serialization failure và cần retry |

Các bất thường thường được nhắc tới gồm dirty read, non-repeatable read, phantom read và lost update. Không nên giả định một isolation level có tên giống nhau sẽ có mọi chi tiết giống nhau trên PostgreSQL, MySQL hoặc SQL Server. Cần tham khảo semantics của database đang dùng và kiểm thử các tình huống cạnh tranh.

Nâng isolation lên SERIALIZABLE không phải giải pháp mặc định. Nó có thể giảm concurrency và làm tăng lỗi serialization cần retry. Hãy chọn mức thấp nhất vẫn bảo vệ được bất biến, kết hợp constraint, locking hoặc câu cập nhật nguyên tử khi thích hợp.

## 13. Deadlock và thứ tự truy cập tài nguyên

Deadlock có thể xảy ra khi hai transaction giữ khóa theo thứ tự khác nhau:

- Transaction A khóa hàng tồn kho sản phẩm X rồi chờ sản phẩm Y.
- Transaction B khóa sản phẩm Y rồi chờ sản phẩm X.
- Cả hai chờ nhau và database phải hủy một transaction để giải phóng hệ thống.

Để giảm nguy cơ:

- Truy cập nhiều bản ghi theo thứ tự ổn định, ví dụ sắp xếp theo productId.
- Giữ transaction ngắn và không gọi HTTP hoặc chờ người dùng trong lúc đang giữ khóa.
- Tạo index phù hợp để câu lệnh khóa ít quét và khóa ngoài ý muốn.
- Xử lý deadlock/lock timeout như lỗi có thể retry có giới hạn nếu use case an toàn.
- Theo dõi log deadlock của database và xác định câu query, thứ tự khóa thực tế.

Không nên bắt mọi lỗi database rồi retry vô hạn. Lỗi cú pháp, constraint nghiệp vụ hoặc dữ liệu không hợp lệ không tự biến mất sau retry. Chỉ retry các lỗi transient đã nhận diện, với số lần giới hạn, backoff và jitter phù hợp.

## 14. Retry toàn bộ transaction, không chỉ lặp lại một câu lệnh tùy tiện

Khi optimistic locking hoặc serialization failure xảy ra, transaction hiện tại thường đã thất bại hoặc bị đánh dấu rollback-only. Không nên bắt lỗi rồi tiếp tục dùng cùng persistence context và transaction để chạy lại một phần nghiệp vụ.

Cách an toàn hơn là đặt retry ở lớp bên ngoài bean transactional. Mỗi lần gọi vào transactional service tạo một transaction mới:

~~~java
@Service
public class PlaceOrderRetryFacade {
    private final PlaceOrderTransaction transaction;

    public PlaceOrderRetryFacade(PlaceOrderTransaction transaction) {
        this.transaction = transaction;
    }

    public PlaceOrderResult place(PlaceOrderCommand command) {
        int attempts = 0;

        while (true) {
            try {
                return transaction.execute(command);
            } catch (OptimisticLockingFailureException ex) {
                attempts++;
                if (attempts >= 3) {
                    throw ex;
                }
                // Có thể áp dụng backoff và jitter ở đây.
            }
        }
    }
}

@Service
public class PlaceOrderTransaction {
    @Transactional
    public PlaceOrderResult execute(PlaceOrderCommand command) {
        // Mỗi lần gọi qua Spring proxy có transaction riêng.
        // Đọc lại dữ liệu, kiểm tra lại quy tắc và thực hiện toàn bộ use case.
        return doPlaceOrder(command);
    }
}
~~~

Ví dụ chỉ minh họa ranh giới retry. Trong triển khai thực tế, cần nhận diện đúng exception transient của database/ORM, giới hạn tổng thời gian retry và không retry lỗi nghiệp vụ. Việc facade gọi một bean transactional khác giúp lời gọi đi qua proxy; nếu đặt cả hai phương thức trong cùng class rồi gọi nội bộ, transaction có thể không được tạo mới như mong muốn.

Retry chỉ an toàn khi use case không lặp side effect ngoài transaction. Nếu gọi cổng thanh toán hoặc gửi email trước khi transaction thất bại, lần retry có thể thực hiện side effect lần nữa. Dùng idempotency key ở provider, outbox hoặc saga/compensation tùy tình huống.

## 15. Những cấu hình và mẫu code dễ làm sai tính nguyên tử

| Mẫu triển khai | Rủi ro | Điều chỉnh |
|---|---|---|
| Mỗi repository tự dùng REQUIRES_NEW | Một repository commit dù use case ngoài rollback | Dùng REQUIRED khi cần cùng transaction |
| Bắt exception rồi trả success | Transaction có thể commit hoặc caller hiểu sai | Ném lại hoặc đánh dấu rollback-only và trả kết quả đúng |
| Gọi repository qua datasource khác nhưng chỉ có một @Transactional | Không có atomicity giữa hai database | Transaction manager riêng, distributed transaction có chủ đích hoặc saga |
| Gọi HTTP provider trong transaction dài | Giữ connection/lock khi chờ mạng; không rollback được provider | Outbox/workflow và idempotency |
| Đọc rồi ghi không khóa | Lost update | Version, lock hoặc conditional update |
| Retry trong cùng transaction đã lỗi | Transaction có thể đã rollback-only | Retry từ bên ngoài với transaction mới |
| Cho rằng save đồng nghĩa commit | Lỗi có thể xuất hiện khi flush/commit | Kiểm thử và xử lý lỗi tại ranh giới transaction |

Một lưu ý nữa: @Transactional thường hoạt động qua proxy trong Spring. Cần gọi phương thức transactional qua Spring-managed bean và hiểu propagation thực tế. Transaction imperative thông thường gắn với luồng thực thi hiện tại; chuyển công việc sang thread mới hoặc @Async không tự mang transaction sang thread đó.

## 16. Kiểm thử commit, rollback và ghi cạnh tranh

Unit test với mock có thể xác minh Application service gọi repository đúng, nhưng không chứng minh database rollback hoặc khóa hoạt động. Các đặc tính đó cần integration test với database tương thích, tốt nhất là cùng hệ quản trị như production khi hành vi phụ thuộc locking/isolation.

Các kịch bản nên kiểm tra:

- **Commit:** nhiều repository cùng cập nhật thành công và dữ liệu đều tồn tại sau khi transaction kết thúc.
- **Rollback giữa chừng:** repository đầu đã ghi, repository sau ném lỗi; sau rollback, không có thay đổi nào của transaction còn lại.
- **Constraint ở commit:** vi phạm unique/foreign key có thể xuất hiện khi flush hoặc commit; caller nhận lỗi thay vì response thành công.
- **Cạnh tranh:** hai transaction cùng giữ chỗ lượng tồn kho; tổng số lượng thành công không vượt lượng có sẵn.
- **Optimistic lock:** hai transaction cùng đọc version; một cập nhật thắng, cập nhật còn lại nhận conflict.
- **Deadlock/serialization retry:** lỗi transient được retry giới hạn trong transaction mới.
- **Outbox:** thay đổi nghiệp vụ và outbox record cùng commit hoặc cùng rollback.

Với Testcontainers, có thể khởi động PostgreSQL/MySQL kiểm thử, chạy hai request đồng thời bằng ExecutorService và đồng bộ thời điểm đọc bằng CountDownLatch. Sau khi các transaction hoàn tất, truy vấn lại database trong transaction mới để kiểm tra số lượng tồn kho và số đơn hàng thực tế. Không nên chỉ assert kết quả từ object trong bộ nhớ của test.

Nếu test method tự mang @Transactional và rollback khi kết thúc, nó có thể che khuất hành vi commit mà bài test cần xác minh. Hãy thiết kế test boundary rõ ràng: gọi service qua proxy, kết thúc transaction, rồi đọc lại dữ liệu bằng transaction mới.

## 17. Checklist thiết kế use case nhiều repository

Trước khi hoàn thành một thao tác nghiệp vụ cập nhật nhiều loại dữ liệu, hãy tự hỏi:

1. Những repository nào tham gia và chúng có dùng chung database/transaction manager không?
2. Ranh giới transaction đặt ở application service nào?
3. Các repository có tham gia REQUIRED hay có propagation độc lập ngoài ý muốn?
4. Trường hợp lỗi ở từng bước có rollback toàn bộ thay đổi cần thiết không?
5. Có side effect ngoài database nào không thể rollback bằng transaction này không?
6. Dữ liệu có thể bị hai request cập nhật đồng thời không?
7. Nên dùng optimistic version, pessimistic lock, unique constraint hay conditional update?
8. Thứ tự lấy khóa có nhất quán để giảm deadlock không?
9. Lỗi commit/flush có được xử lý tại ranh giới caller không?
10. Retry có giới hạn và mỗi lần thử dùng transaction mới không?
11. Có integration test cho commit, rollback và concurrency với database phù hợp không?

Phối hợp nhiều repository đúng cách đòi hỏi application service xác định ranh giới của một ca sử dụng, các repository tham gia đúng transaction và database bảo vệ những ghi cạnh tranh. Commit chỉ được xác nhận khi transaction hoàn tất; rollback chỉ hoàn tác tài nguyên thuộc transaction đó. Khi có nhiều request cùng ghi, hãy dùng constraint, optimistic/pessimistic locking hoặc cập nhật nguyên tử theo bất biến cần bảo vệ. Thiết kế rõ các ranh giới này giúp hệ thống đơn hàng tránh dữ liệu nửa vời, ghi đè sai và trạng thái khó đối soát.

