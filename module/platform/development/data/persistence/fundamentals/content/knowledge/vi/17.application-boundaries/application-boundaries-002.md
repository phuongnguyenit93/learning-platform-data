# Vai trò của DAO, Repository và lớp truy cập dữ liệu

Một ứng dụng Java cần lưu đơn hàng, truy vấn sản phẩm, cập nhật trạng thái thanh toán và đọc dữ liệu báo cáo. Nếu mọi service đều tự viết SQL, quản lý connection và diễn giải các cột trong database, mã nguồn sẽ nhanh chóng phụ thuộc vào cấu trúc lưu trữ: đổi schema kéo theo sửa nhiều nơi, khó kiểm thử nghiệp vụ, khó kiểm soát giao dịch và dễ phát sinh lỗi khi nhiều thao tác cùng chạy.

**DAO, Repository và lớp truy cập dữ liệu** giúp thiết kế ranh giới rõ ràng giữa nghiệp vụ và persistence. Tuy nhiên ba thuật ngữ này không hoàn toàn đồng nghĩa, và đặt tên lớp là Repository không tự làm mã nguồn tách khỏi database.

Bài thuộc chương **Ranh giới ứng dụng** trong module **DATA_PERSISTENCE_FUNDAMENTALS**. Người học sẽ kết nối các kiến thức về mô hình dữ liệu, SQL, chỉ mục, giao dịch, cô lập, quản lý kết nối, lỗi và tối ưu hiệu năng với cách tổ chức mã Java trong một hệ thống có thể bảo trì.

> **Thông điệp chính:** tầng ứng dụng quyết định *cần hoàn thành nghiệp vụ gì*; domain quyết định *quy tắc nghiệp vụ nào phải đúng*; tầng truy cập dữ liệu quyết định *đọc và ghi vào hệ thống lưu trữ bằng cách nào*. Repository hay DAO là công cụ để biểu diễn ranh giới này, không phải một bảo đảm tự động.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Phân biệt **DAO (Data Access Object)**, **Repository** và **data access layer/persistence adapter** theo trách nhiệm và mức trừu tượng.
- Đặt interface truy cập dữ liệu ở vị trí hợp lý so với domain, application service và hạ tầng database.
- Thiết kế method theo ý nghĩa nghiệp vụ hoặc nhu cầu truy vấn, tránh đưa JDBC/JPA và cấu trúc bảng vào domain một cách không cần thiết.
- Dùng JDBC/JdbcTemplate, Spring Data JPA hoặc ORM như những lựa chọn triển khai, không xem chúng là định nghĩa của domain.
- Xác định tầng sở hữu transaction, connection, ánh xạ dữ liệu và phân loại lỗi.
- Bảo vệ invariant và khả năng xử lý đồng thời bằng constraint, cập nhật nguyên tử, optimistic locking hoặc isolation phù hợp.
- Tổ chức luồng đọc, ghi và truy vấn báo cáo mà không tạo một repository quá lớn.
- Kiểm thử riêng logic nghiệp vụ và hành vi persistence thật bằng database phù hợp.
- Nhận diện các anti-pattern như generic repository quá trừu tượng, query leak, N+1, Open Session in View và service chỉ đóng vai trò chuyển tiếp.

## 2. Bức tranh tổng thể về ranh giới ứng dụng

Xét ứng dụng đặt hàng có các phần:

- **HTTP controller:** nhận request, xác thực dữ liệu đầu vào và chuyển sang use case.
- **Application service:** điều phối luồng đặt hàng, xác định transaction boundary và kết quả trả về.
- **Domain model:** mô tả Order, trạng thái hợp lệ và quy tắc chuyển trạng thái.
- **Repository port:** cung cấp thao tác cần thiết để lưu/lấy các đối tượng hoặc trạng thái phục vụ nghiệp vụ.
- **Persistence adapter / DAO:** ánh xạ thao tác đó thành SQL/JPA, quản lý tương tác với DB.
- **Database:** cưỡng chế khóa chính, khóa ngoại, UNIQUE, CHECK, transaction và các đảm bảo lưu trữ.

~~~mermaid
flowchart TD
    H["HTTP Controller"] --> A["Application Service / Use Case"]
    A --> D["Domain Model + Invariants"]
    A --> P["OrderRepository interface (port)"]
    P -. "được triển khai bởi" .-> J["JdbcOrderRepository / JpaOrderRepository"]
    J --> Q["SQL / JPA / DAO / Row Mapper"]
    Q --> DB[("Relational Database")]
    A --> O["Outbox / other ports khi cần"]
~~~

Mũi tên nét đứt thể hiện quan hệ triển khai interface; không có nghĩa ở thời điểm chạy service sẽ bỏ qua adapter. Một ứng dụng nhỏ có thể không cần đầy đủ tất cả các lớp này. Mục đích của sơ đồ là phân biệt **trách nhiệm và chiều phụ thuộc**, chứ không phải bắt buộc tạo một lớp Java cho mỗi hình chữ nhật.

### 2.1. Phân biệt ba câu hỏi

| Câu hỏi | Thành phần thường trả lời | Ví dụ |
|---|---|---|
| “Cho phép hủy đơn lúc này không?” | Domain hoặc application policy | Chỉ đơn PENDING mới được hủy |
| “Cần lưu những thay đổi nào cùng transaction?” | Application service/transaction boundary | Đổi trạng thái đơn và ghi outbox event |
| “Thực thi UPDATE và ánh xạ cột thế nào?” | Persistence adapter/DAO | SQL có WHERE tenant_id, id và version |

Nếu method xử lý nghiệp vụ trực tiếp cài DataSource, PreparedStatement, biết tên bảng và tự đóng connection, ranh giới đang bị trộn lẫn. Nếu DAO quyết định khi nào hoàn tiền, gửi email hay chọn chính sách hủy đơn, DAO cũng đang gánh trách nhiệm ngoài persistence.

## 3. DAO là gì?

**DAO (Data Access Object)** là đối tượng đóng gói cách ứng dụng tiếp cận một nguồn dữ liệu cụ thể. DAO thường gần với thao tác truy vấn, câu SQL, bảng, view hoặc kết quả truy vấn.

Ví dụ những trách nhiệm phù hợp:

- Đọc hàng order theo tenant_id và id.
- INSERT hoặc UPDATE record bằng prepared statement.
- Ánh xạ ResultSet/JPA projection thành một kiểu dữ liệu được định nghĩa.
- Thi hành phân trang, sắp xếp, batch DML và trả số hàng bị tác động.
- Chuyển lỗi hạ tầng thành nhóm lỗi để tầng gọi có thể xử lý theo hợp đồng.
- Không tự quyết định điều kiện nghiệp vụ phức tạp ngoài hợp đồng truy cập dữ liệu.

Một DAO thường trả về các kiểu như OrderRow, InvoiceProjection, PageResult hoặc DTO báo cáo. Nó có thể dùng JDBC, JPA, jOOQ, mapper framework hay một REST storage API tùy hệ thống.

### 3.1. Ví dụ DAO dùng JDBC

Giả sử bảng orders lưu id UUID, tenant_id, status, total_amount và version:

~~~sql
CREATE TABLE orders (
    id uuid PRIMARY KEY,
    tenant_id bigint NOT NULL,
    status text NOT NULL
       CHECK (status IN ('PENDING', 'CONFIRMED', 'CANCELLED')),
    total_amount numeric(18, 2) NOT NULL CHECK (total_amount >= 0),
    version bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_orders_tenant_created
    ON orders (tenant_id, created_at DESC, id DESC);
~~~

Một DAO sử dụng JdbcTemplate có thể đơn giản như sau:

~~~java
public record OrderRow(
        UUID id,
        long tenantId,
        String status,
        BigDecimal totalAmount,
        long version
) {}

@Repository
public class JdbcOrderDao {
    private final JdbcTemplate jdbc;

    public JdbcOrderDao(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Optional<OrderRow> findById(long tenantId, UUID id) {
        List<OrderRow> rows = jdbc.query(
            """
            SELECT id, tenant_id, status, total_amount, version
            FROM orders
            WHERE tenant_id = ? AND id = ?
            """,
            (rs, rowNum) -> new OrderRow(
                rs.getObject("id", UUID.class),
                rs.getLong("tenant_id"),
                rs.getString("status"),
                rs.getBigDecimal("total_amount"),
                rs.getLong("version")
            ),
            tenantId, id
        );

        return rows.stream().findFirst();
    }

    public int changeStatus(
            long tenantId, UUID id, String expectedStatus,
            String newStatus, long expectedVersion) {
        return jdbc.update(
            """
            UPDATE orders
            SET status = ?, version = version + 1
            WHERE tenant_id = ?
              AND id = ?
              AND status = ?
              AND version = ?
            """,
            newStatus, tenantId, id, expectedStatus, expectedVersion
        );
    }
}
~~~

DAO biết SQL và tên cột; application service không cần biết chúng. Method changeStatus trả số hàng cập nhật để caller phát hiện không tìm thấy bản ghi hoặc không còn đúng status/version. Việc phân biệt các nguyên nhân có thể cần đọc lại hoặc một error contract rõ ràng.

**Lưu ý:** annotation @Repository của Spring đánh dấu stereotype và có thể tham gia cơ chế dịch ngoại lệ. Nó **không** tự biến mọi class được đánh dấu thành Repository theo định nghĩa DDD, cũng không tự tạo transaction quanh toàn bộ use case.

### 3.2. DAO theo bảng hay theo nhiệm vụ?

Không bắt buộc một DAO tương ứng chính xác một bảng. Một OrderReadDao có thể JOIN orders, order_items và customers để trả OrderDetailsProjection; một PaymentLedgerDao có thể ghi các bảng ledger liên quan trong cùng transaction. Cần cân bằng giữa khả năng tái sử dụng và ranh giới nghiệp vụ.

Các tên DAO quá tổng quát như DatabaseDao hoặc CommonSqlHelper thường che khuất hợp đồng. Ngược lại, tạo hàng trăm DAO chỉ làm một method gọi lại JdbcTemplate mà không bổ sung ý nghĩa cũng làm kiến trúc cồng kềnh.

## 4. Repository là gì?

Trong thiết kế domain-oriented, **Repository** biểu diễn tập hợp các đối tượng nghiệp vụ, thường là **aggregate root**, như thể chúng là một bộ sưu tập có thể tìm, thêm và lưu; phía dùng không phải quan tâm đối tượng đang ở bảng nào hay được ánh xạ bằng SQL/JPA.

Một interface có thể mô tả:

~~~java
public interface OrderRepository {
    Optional<Order> findById(TenantId tenantId, OrderId orderId);

    void save(Order order);
}
~~~

Ở đây Order là đối tượng domain, không phải ResultSet hoặc một bảng. Repository giúp ứng dụng giữ tập trung vào Order và invariant của nó. Cách triển khai có thể cần đọc nhiều bảng orders/order_items, ghi cả audit/outbox theo thiết kế, hoặc dùng một mapping ORM; interface không cần biết chi tiết.

Tuy nhiên **Repository không phải phép màu loại bỏ mọi phụ thuộc vào lưu trữ**. Nếu persistence adapter không thể thực thi một contract một cách hiệu quả hoặc nguyên tử, thiết kế interface phải được xem lại.

### 4.1. Repository theo aggregate, không nhất thiết theo từng bảng

Một Order aggregate có thể gồm:

~~~text
Order
 ├── orderId, tenantId, status, version
 ├── OrderLine #1
 ├── OrderLine #2
 └── Quy tắc: không xác nhận khi chưa có hàng
~~~

Repository của Order có thể lưu Order và các dòng hàng trong một local transaction, dù dữ liệu nằm ở hai bảng. Không nhất thiết tạo một OrderLineRepository để application service cập nhật trực tiếp từng dòng nếu điều đó cho phép phá invariant do Order quản lý.

Trong DDD, aggregate là **ranh giới consistency**: những invariant thuộc aggregate phải được bảo vệ trong giao dịch và cơ chế đồng thời phù hợp. Không nên gộp mọi đối tượng có liên hệ thành một aggregate khổng lồ; như vậy mọi thao tác đơn giản sẽ phải tải hoặc khóa quá nhiều dữ liệu.

### 4.2. Một interface repository có thể hướng nghiệp vụ

~~~java
public interface OrderRepository {
    Optional<Order> findById(TenantId tenantId, OrderId id);

    boolean confirmPending(
        TenantId tenantId,
        OrderId id,
        long expectedVersion
    );
}
~~~

Với use case chỉ cần chuyển PENDING thành CONFIRMED theo version, một method update có điều kiện có thể tốt hơn tải toàn bộ aggregate, thay đổi entity rồi lưu lại. Việc sử dụng tên Repository ở đây vẫn hợp lý nếu interface biểu diễn thao tác trên đối tượng nghiệp vụ và bảo vệ đúng ranh giới.

Điều kiện quan trọng là không chuyển domain policy thành SQL rải rác không kiểm soát. Nếu confirmPending đòi nhiều invariant, phải bảo đảm adapter hoặc application service kiểm tra chúng trong cùng transaction và theo cơ chế cô lập phù hợp.

## 5. DAO, Repository và data access layer khác nhau thế nào?

| Khía cạnh | DAO | Repository | Lớp truy cập dữ liệu / persistence adapter |
|---|---|---|---|
| Mức trừu tượng điển hình | Gần câu truy vấn, record, kết quả SQL | Gần entity/aggregate và ngôn ngữ domain | Toàn bộ thành phần triển khai kết nối đến storage |
| Interface thường phục vụ ai? | Service truy vấn hoặc lớp repository | Application/domain use case | Interface/port và các nhu cầu hạ tầng |
| Phụ thuộc SQL/JDBC? | Thường có ở implementation | Không nên ở domain-facing interface | Implementation có thể có |
| Kết quả trả về | Row, DTO, projection, số hàng | Domain object, aggregate hoặc trạng thái nghiệp vụ | Tùy loại adapter |
| Mapping dữ liệu | Row-to-object, DTO | Storage representation ↔ domain | Mapping, conversion, cache, driver |
| Kiểm soát transaction | Thường tham gia transaction do bên ngoài mở | Hợp đồng phải phù hợp ranh giới nhất quán | Tích hợp transaction manager/pool |
| Ví dụ | JdbcOrderDao | OrderRepository | JdbcOrderRepository, JpaOrderRepository |

Không có một quy tắc phổ quát “DAO luôn dùng JDBC, Repository luôn dùng JPA”. Trong thực tế, Spring Data đặt tên các interface như JpaRepository và cung cấp CRUD/query methods. Đó là **API persistence**; muốn đạt sự tách biệt của domain repository, có thể bọc nó sau một port độc lập với Spring Data.

**Cách đọc tên lớp:** xem input/output, phụ thuộc và nơi đặt logic, không quyết định chỉ dựa trên hậu tố Dao/Repository.

## 6. Dependency inversion: interface thuộc phía dùng, adapter thuộc phía hạ tầng

Một cách tổ chức đơn giản:

~~~text
application/
  PlaceOrderService.java
  CancelOrderService.java

domain/
  Order.java
  OrderId.java
  OrderRepository.java

infrastructure/
  persistence/
    JdbcOrderRepository.java
    JdbcOrderDao.java
    OrderRowMapper.java

api/
  OrderController.java
~~~

Đây là ví dụ cấu trúc gợi ý, không phải yêu cầu tuyệt đối về package. Khi domain chịu trách nhiệm định nghĩa abstraction, **domain không import org.springframework.jdbc.*, java.sql.* hoặc JPA repository chỉ để tồn tại**.

~~~mermaid
flowchart LR
    A["Application service"] --> P["OrderRepository (domain port)"]
    I["JDBC/JPA adapter"] -->|implements| P
    I --> B[("Database")]
~~~

Mã hạ tầng phụ thuộc vào contract phía domain. Ở runtime dependency injection nối OrderRepository với implementation được cấu hình. Như vậy không phải domain gọi hạ tầng bằng cách import một class cụ thể.

### 6.1. Một domain model nhỏ

~~~java
public record TenantId(long value) {
    public TenantId {
        if (value <= 0) throw new IllegalArgumentException("Invalid tenant");
    }
}

public record OrderId(UUID value) {
    public OrderId {
        Objects.requireNonNull(value);
    }
}

public enum OrderStatus {
    PENDING, CONFIRMED, CANCELLED
}

public final class Order {
    private final TenantId tenantId;
    private final OrderId id;
    private OrderStatus status;
    private long version;

    public Order(TenantId tenantId, OrderId id,
                 OrderStatus status, long version) {
        this.tenantId = Objects.requireNonNull(tenantId);
        this.id = Objects.requireNonNull(id);
        this.status = Objects.requireNonNull(status);
        this.version = version;
    }

    public void confirm() {
        if (status != OrderStatus.PENDING) {
            throw new IllegalStateException("Only PENDING can be confirmed");
        }
        status = OrderStatus.CONFIRMED;
    }

    public TenantId tenantId() { return tenantId; }
    public OrderId id() { return id; }
    public OrderStatus status() { return status; }
    public long version() { return version; }
}
~~~

Order.confirm() chứa điều kiện chuyển trạng thái. Nó không xây SQL, không biết bảng orders và không đóng connection. Mẫu này giúp kiểm thử điều kiện nghiệp vụ bằng một unit test nhanh.

### 6.2. Port cho trường hợp cập nhật có điều kiện

~~~java
public interface OrderRepository {
    Optional<Order> findById(TenantId tenantId, OrderId id);

    boolean updateStatusIfVersionMatches(
        TenantId tenantId,
        OrderId id,
        OrderStatus expectedStatus,
        OrderStatus newStatus,
        long expectedVersion
    );
}
~~~

Interface có thể được đặt ở domain hoặc application tùy trường phái và chủ sở hữu use case. Quan trọng là **phía cần chức năng định nghĩa contract**, không buộc nó phụ thuộc vào chi tiết truy vấn cụ thể.

Ở trường hợp này, interface đã phơi ra version để người gọi xử lý cập nhật cạnh tranh. Điều đó chấp nhận được nếu version là khái niệm concurrency trong hợp đồng ứng dụng; nếu không, có thể định nghĩa một method nghiệp vụ như confirmPending và để adapter chịu trách nhiệm chiến lược concurrency cùng việc báo xung đột.

## 7. Adapter: nối domain port với JDBC DAO

Một adapter có thể kết hợp DAO gần SQL với conversion từ OrderRow sang Order:

~~~java
@Repository
public class JdbcOrderRepository implements OrderRepository {
    private final JdbcOrderDao dao;

    public JdbcOrderRepository(JdbcOrderDao dao) {
        this.dao = dao;
    }

    @Override
    public Optional<Order> findById(TenantId tenant, OrderId id) {
        return dao.findById(tenant.value(), id.value())
            .map(row -> new Order(
                new TenantId(row.tenantId()),
                new OrderId(row.id()),
                OrderStatus.valueOf(row.status()),
                row.version()
            ));
    }

    @Override
    public boolean updateStatusIfVersionMatches(
            TenantId tenant,
            OrderId id,
            OrderStatus expectedStatus,
            OrderStatus newStatus,
            long expectedVersion) {
        return dao.changeStatus(
            tenant.value(),
            id.value(),
            expectedStatus.name(),
            newStatus.name(),
            expectedVersion
        ) == 1;
    }
}
~~~

Trong ví dụ này:

- OrderRepository là hợp đồng phục vụ nghiệp vụ.
- JdbcOrderRepository là adapter chuyển kiểu domain sang kiểu phù hợp storage.
- JdbcOrderDao thực thi SQL, quản lý mapping row và tham gia transaction.
- JdbcTemplate dùng connection do Spring transaction manager quản lý khi cấu hình đúng.

**Không nhất thiết phải có đủ hai lớp JdbcOrderRepository và JdbcOrderDao** nếu cả hai chỉ làm công việc thừa. Ở hệ thống nhỏ, một JdbcOrderRepository có thể vừa implement port vừa trực tiếp dùng JdbcTemplate. Tách DAO khi nó gom những truy vấn phức tạp, dùng lại cho read projections hoặc giúp giảm phụ thuộc giữa mapping và domain.

### 7.1. Không trả đối tượng hạ tầng qua domain port

Tránh interface kiểu:

~~~java
// Không phù hợp làm domain-facing repository contract.
ResultSet findOrderResultSet(UUID orderId);
EntityManager getEntityManager();
Connection borrowConnectionForBusinessLogic();
JpaSpecificationExecutor<OrderJpaEntity> getQueryExecutor();
~~~

Nó khiến application service phải quản lý tài nguyên JDBC, biết JPA entity hoặc tự ghép truy vấn hạ tầng. Điều này làm ranh giới mờ đi và tăng khả năng rò connection hoặc truy vấn ngoài transaction.

Với nhu cầu truy vấn động thực sự, có thể dùng **query object/criteria của chính ứng dụng** có các trường được cho phép, không phơi một DSL quá cụ thể của persistence vào domain nếu không cần.

## 8. Transaction boundary: nên đặt ở đâu?

Một application service thường biết **những thao tác nào phải commit nguyên tử**. Vì thế ranh giới transaction thường nằm ở use case, không nằm trong từng DAO nhỏ.

Ví dụ hủy đơn cần đổi status và ghi outbox event:

~~~java
@Service
public class CancelOrderService {
    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public CancelOrderService(OrderRepository orders,
                              OutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public void cancel(TenantId tenant, OrderId id) {
        Order order = orders.findById(tenant, id)
            .orElseThrow(() -> new NoSuchElementException("Order not found"));

        if (order.status() != OrderStatus.PENDING) {
            throw new IllegalStateException("Only PENDING orders can be cancelled");
        }

        boolean changed = orders.updateStatusIfVersionMatches(
            tenant, id, OrderStatus.PENDING,
            OrderStatus.CANCELLED, order.version()
        );
        if (!changed) {
            throw new ConcurrentModificationException(
                "Order changed; reload before cancelling"
            );
        }

        outbox.appendOrderCancelled(tenant, id);
    }
}
~~~

Giả định hai repository dùng cùng DataSource và transaction manager, method được gọi qua Spring transactional proxy, và outbox được ghi vào **cùng database transaction**. Khi UPDATE thất bại, exception trước outbox khiến transaction rollback; khi ghi outbox thất bại, cập nhật order cũng rollback. Nếu publish message trực tiếp qua HTTP/broker trong method, transaction DB **không tự bảo vệ** việc gửi ấy.

### 8.1. Vì sao không để mỗi DAO tự mở/commit transaction?

Nếu OrderDao.cancel() commit một lần còn OutboxDao.append() commit độc lập, crash giữa hai lời gọi có thể để đơn đã hủy nhưng không có event cần phát. Các thao tác vốn phải nguyên tử đã bị tách thành hai transaction.

DAO nên tham gia **transaction hiện tại** của use case; nơi sở hữu use case chịu trách nhiệm quyết định commit/rollback. Có ngoại lệ: tác vụ dữ liệu độc lập chỉ cần một câu SQL có thể tự đủ transaction autocommit, hoặc một adapter có transaction boundary riêng được định nghĩa rõ. Quan trọng là lựa chọn có chủ đích.

### 8.2. Cùng tên @Transactional không tự phối hợp mọi tài nguyên

- Spring @Transactional chỉ có hiệu lực theo transaction manager và propagation thực tế.
- Hai DataSource độc lập không tự có một transaction toàn cục.
- Method con tham gia transaction đã tồn tại thường không tự commit khi return.
- Lời gọi nội bộ qua this.method() trong cùng bean có thể không đi qua proxy.
- JDBC Connection mượn raw không qua cơ chế transaction-aware có thể chạy ngoài transaction do Spring quản lý.
- Một HTTP API, message broker hoặc email không tự rollback theo database. Dùng outbox/Saga/idempotency khi workflow vượt ranh giới tài nguyên.

Những ranh giới này ảnh hưởng trực tiếp tính đúng đắn nghiệp vụ và cách xử lý lỗi, chứ không chỉ tổ chức package.

## 9. Spring Data JPA Repository và domain repository

Spring Data JPA cung cấp các interface như JpaRepository<T, ID> để thực hiện CRUD và tạo query theo convention. Đây là công cụ persistence hữu ích, nhưng **repository của framework** không nhất thiết là **repository port của domain**.

Ví dụ lớp ánh xạ:

~~~java
@Entity
@Table(name = "orders")
public class OrderJpaEntity {
    @Id
    private UUID id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    @Version
    private Long version;

    // Constructor và getters/setters phù hợp với JPA.
}

public interface SpringOrderJpaRepository
        extends JpaRepository<OrderJpaEntity, UUID> {
    Optional<OrderJpaEntity> findByIdAndTenantId(UUID id, Long tenantId);
}
~~~

Trong ví dụ này, SpringOrderJpaRepository là một **persistence repository** thuộc framework. Nếu application service gọi thẳng nó, service có thể phụ thuộc vào JPA entity, persistence context, lazy loading và ORM semantics. Khi domain cần độc lập hơn, dùng adapter:

~~~java
@Repository
public class JpaOrderRepositoryAdapter implements OrderRepository {
    private final SpringOrderJpaRepository jpa;

    public JpaOrderRepositoryAdapter(SpringOrderJpaRepository jpa) {
        this.jpa = jpa;
    }

    @Override
    public Optional<Order> findById(TenantId tenantId, OrderId id) {
        return jpa.findByIdAndTenantId(id.value(), tenantId.value())
            .map(entity -> new Order(
                tenantId,
                id,
                entity.getStatus(),
                entity.getVersion()
            ));
    }

    // Implement các method khác theo contract của OrderRepository.
}
~~~

Ví dụ chỉ minh họa điểm nối port/adapter. Trong dự án thật cần khai báo đầy đủ mapping và implementation cập nhật, nhất là việc xử lý version conflict và transaction.

### 9.1. Có bắt buộc tách JPA entity và domain object?

Không. Với CRUD đơn giản, dùng JPA entity làm model ứng dụng có thể hợp lý hơn việc viết hai loại class chỉ để copy từng field. Khi domain có quy tắc phức tạp, nhiều value object, hoặc schema legacy không đồng nhất với khái niệm nghiệp vụ, tách domain khỏi JPA có thể giảm phụ thuộc framework và giúp kiểm thử.

Hãy cân nhắc chi phí mapping và độ phức tạp. **Mục tiêu là ranh giới đủ rõ**, không phải có càng nhiều abstraction càng tốt.

### 9.2. Lazy loading và vòng đời EntityManager

Một quan hệ JPA lazy có thể truy vấn DB khi getter được gọi. Nếu controller trả entity và JSON serializer truy cập getter sau khi transaction/persistence context đã đóng, có thể phát sinh lazy initialization error. Nếu giữ session mở qua giai đoạn render HTTP, kết nối hoặc truy vấn có thể bị kéo dài ngoài phạm vi use case.

Phương án thường tốt hơn:

- Application/query adapter đọc đúng dữ liệu cần thiết trong scope hợp lệ.
- Trả DTO/projection độc lập với session của ORM.
- Sử dụng join fetch, entity graph hoặc batch fetching theo trường hợp để tránh N+1.
- Không cấu hình tất cả quan hệ thành EAGER như một cách chữa lỗi chung.
- Không trả entity hai chiều thẳng ra JSON khi chưa xét lặp tham chiếu và lộ dữ liệu nhạy cảm.

## 10. Tách mô hình truy vấn đọc khỏi mô hình ghi

Một màn hình quản trị cần danh sách đơn hàng cùng tên khách hàng, số tiền và thời điểm tạo. Trong khi đó use case xác nhận đơn chỉ cần một thao tác cập nhật có điều kiện trên một order.

Nếu OrderRepository luôn tải toàn bộ aggregate chỉ để vẽ danh sách, hệ thống có thể tăng lượng SQL và bộ nhớ không cần thiết. Có thể tách contract:

~~~java
public interface OrderRepository {
    Optional<Order> findById(TenantId tenant, OrderId id);

    boolean updateStatusIfVersionMatches(
        TenantId tenant, OrderId id,
        OrderStatus expected, OrderStatus next,
        long version
    );
}

public interface OrderQueryService {
    List<OrderListItem> listRecentOrders(TenantId tenant, int limit);
}

public record OrderListItem(
    UUID id,
    String customerName,
    OrderStatus status,
    BigDecimal totalAmount,
    Instant createdAt
) {}
~~~

OrderQueryService có thể dùng JOIN và read projection tối ưu cho màn hình mà không cần dựng full aggregate. **Đây chỉ là tách luồng đọc/ghi trong code**, chưa phải yêu cầu triển khai CQRS lớn, hai database hoặc event sourcing.

Một DAO truy vấn có thể triển khai:

~~~java
public List<OrderListItem> listRecentOrders(long tenantId, int limit) {
    int safeLimit = Math.min(Math.max(limit, 1), 100);

    return jdbc.query(
        """
        SELECT o.id, c.display_name, o.status,
               o.total_amount, o.created_at
        FROM orders o
        JOIN customers c
          ON c.id = o.customer_id
         AND c.tenant_id = o.tenant_id
        WHERE o.tenant_id = ?
        ORDER BY o.created_at DESC, o.id DESC
        LIMIT ?
        """,
        (rs, index) -> new OrderListItem(
            rs.getObject("id", UUID.class),
            rs.getString("display_name"),
            OrderStatus.valueOf(rs.getString("status")),
            rs.getBigDecimal("total_amount"),
            rs.getTimestamp("created_at").toInstant()
        ),
        tenantId, safeLimit
    );
}
~~~

Ví dụ query giả định schema bổ sung bảng customers và khóa orders.customer_id; không phải tất cả các cột này đều xuất hiện trong DDL tối giản ở phần đầu. Trong triển khai thực tế cần căn chỉnh schema và ràng buộc tenant.

### 10.1. Phân trang và khối lượng dữ liệu

- Page có COUNT phù hợp khi giao diện cần số trang, nhưng COUNT trên tập lớn có thể tốn kém.
- Slice hoặc trang giới hạn số hàng có thể tránh COUNT khi chỉ cần biết còn dữ liệu hay không.
- Keyset pagination phù hợp với tập lớn và thứ tự ổn định, chẳng hạn created_at cộng id.
- Streaming/cursor có thể giảm bộ nhớ nhưng giữ connection và transaction lâu nếu người gọi xử lý chậm.

**Không trả raw ResultSet hoặc lazy Stream qua interface rồi mặc định controller sẽ tiêu thụ an toàn**. Nếu cần export hàng triệu record, cân nhắc job theo batch hoặc callback thực hiện trong một scope quản lý rõ ràng.

## 11. Một contract truy cập dữ liệu tốt

### 11.1. Phương thức nói rõ mục đích

Những method sau làm người dùng phải biết chi tiết SQL hoặc trạng thái kỹ thuật:

~~~java
Object execute(String sql, Object[] args);
Map<String, Object> getData(int type, String where);
Connection borrowConnection();
~~~

Một contract rõ hơn:

~~~java
Optional<Order> findById(TenantId tenant, OrderId id);
boolean confirmPending(TenantId tenant, OrderId id, long expectedVersion);
List<OrderListItem> listRecentOrders(TenantId tenant, int limit);
~~~

Input/output biểu đạt đúng vấn đề, có tenant scope, giới hạn truy vấn và phản ánh khả năng tranh chấp.

### 11.2. Kết quả không tìm thấy và lỗi ghi

| Trường hợp | Hợp đồng gợi ý | Cần cẩn thận |
|---|---|---|
| Không có một order | Optional.empty() | Đừng lạm dụng null |
| Danh sách không có dữ liệu | Danh sách rỗng | Không tự coi là lỗi |
| UPDATE có điều kiện trả 0 hàng | false hoặc conflict result | Có thể không tồn tại, status sai hoặc version cũ |
| UNIQUE conflict | Lỗi xung đột có ý nghĩa | Không retry bừa toàn bộ nghiệp vụ |
| Lỗi mạng lúc commit | Unknown outcome | Không khẳng định transaction rollback |
| DB tạm hết connection | Hạ tầng tạm thời không sẵn sàng | Retry có budget và backoff |

Không phải mọi SQLException đều nên được dịch thành IllegalArgumentException: như vậy mất thông tin quan trọng để phân biệt lỗi nghiệp vụ, lỗi tạm thời và kết quả commit chưa rõ.

### 11.3. Hợp đồng cần nêu rõ consistency

Nếu read adapter lấy dữ liệu từ read replica bất đồng bộ, method findLatestBalance không thể hứa đọc mọi commit mới nhất trên primary. Hãy ghi rõ consistency cần thiết cho từng use case. Các quyết định quan trọng như kiểm tra số dư và xác nhận trả tiền có thể cần đọc nguồn authoritative hoặc dùng thao tác nguyên tử trực tiếp.

## 12. Bảo mật ở ranh giới persistence

Trừ khi được bảo vệ phù hợp, các phương thức truy cập dữ liệu có thể vô tình làm lộ record giữa tenant hoặc đưa input người dùng vào SQL.

### 12.1. Parameterized query

Không làm:

~~~java
// Nguy hiểm: nối input chưa kiểm soát vào cú pháp SQL.
String sql = "SELECT * FROM orders WHERE customer_email = '"
           + emailFromRequest + "'";
~~~

Dùng PreparedStatement/JdbcTemplate:

~~~java
jdbc.query(
    """
    SELECT id, status
    FROM orders
    WHERE tenant_id = ? AND customer_email = ?
    """,
    rowMapper,
    tenantId, customerEmail
);
~~~

Tham số phân biệt dữ liệu với cú pháp truy vấn. Tuy nhiên danh sách tên cột, tên bảng hoặc hướng ORDER BY không thể bind như giá trị bình thường; nếu cần sắp xếp động, hãy dùng **whitelist** các trường được phép, không ghép biểu thức tùy ý từ người dùng.

### 12.2. Tenant scope và kiểm tra quyền

Một method truy vấn theo id mà bỏ tenant_id có thể trả dữ liệu của tenant khác nếu người gọi đoán được UUID:

~~~sql
UPDATE orders
SET status = 'CANCELLED'
WHERE tenant_id = :tenantId
  AND id = :orderId
  AND status = 'PENDING';
~~~

TenantId phải đến từ ngữ cảnh xác thực đáng tin cậy, không chỉ trường JSON do khách hàng tự khai. Khi thích hợp, cân nhắc row-level security ở database và kiểm thử với nhiều tenant. DAO chịu trách nhiệm đưa phạm vi truy cập vào câu truy vấn; application/domain xác định **ai được phép làm nghiệp vụ gì**.

### 12.3. Tối thiểu hóa dữ liệu và log

Đừng SELECT toàn bộ thông tin thanh toán, địa chỉ, token hoặc dữ liệu riêng tư nếu màn hình chỉ cần id và trạng thái. Không log raw entity, connection string chứa mật khẩu hoặc các câu SQL in-line có tham số nhạy cảm một cách vô thức.

## 13. Đồng thời và invariant ở ranh giới ghi

Một Repository.save() không tự ngăn lost update hay write skew. Khi có nhiều request đồng thời, phải bảo vệ bằng constraint, câu SQL nguyên tử, version, khóa hoặc isolation phù hợp.

### 13.1. Optimistic locking

~~~sql
UPDATE orders
SET status = :newStatus,
    version = version + 1
WHERE tenant_id = :tenantId
  AND id = :orderId
  AND status = :expectedStatus
  AND version = :expectedVersion;
~~~

Khi ảnh hưởng 0 hàng, application service phải từ chối hoặc đọc lại. Không phát OrderCancelled nếu DB không cập nhật gì. Với JPA @Version, ORM có thể thực hiện check phiên bản khi cập nhật entity qua cơ chế tương ứng; các câu bulk SQL bỏ qua version sẽ phá bảo vệ nếu không xử lý riêng.

### 13.2. Một hàng: SQL nguyên tử

~~~sql
UPDATE inventory
SET available = available - :quantity
WHERE sku = :sku AND available >= :quantity;
~~~

Repository.reserveStock có thể dùng update count để trả kết quả. Cách đọc available rồi tự tính trong Java và ghi giá trị cố định dễ mất cập nhật khi hai request cùng chạy.

### 13.3. Nhiều hàng: isolation và khóa nhất quán

Với luật “mỗi ca phải còn ít nhất một bác sĩ trực”, hai transaction có thể cùng đếm 2 và cho hai bác sĩ khác nhau nghỉ, gây **write skew** ở PostgreSQL REPEATABLE READ. Các cách bảo vệ có thể gồm:

- Constraint biểu diễn được bất biến, nếu có.
- Một guard row theo shift mà mọi writer đều khóa trước khi đếm và cập nhật.
- SERIALIZABLE kết hợp retry **toàn bộ transaction** nếu nhận serialization failure.

Repository và application service phải thống nhất ranh giới, không để một worker nền bỏ qua cơ chế.

### 13.4. Transaction ngắn và thứ tự khóa

Khi một use case cập nhật nhiều hàng, giữ thứ tự thao tác nhất quán giúp giảm nguy cơ deadlock. Không giữ transaction mở trong lúc chờ HTTP, email hoặc upload. Một use case quá dài dù ít SQL vẫn có thể làm đầy connection pool vì giữ kết nối và snapshot/lock quá lâu.

## 14. Lỗi truy cập dữ liệu và chính sách retry

Tầng persistence là nơi tiếp xúc trực tiếp với SQLSTATE, lỗi kết nối, khóa, timeout và constraint. Nhưng nơi quyết định **có retry cả use case hay không** thường là application boundary, bởi chỉ tầng này biết thao tác có tạo side effect nào ngoài database hay không.

### 14.1. Phân loại lỗi có ý nghĩa

| Nhóm lỗi | Ví dụ | Chính sách thường phù hợp |
|---|---|---|
| Dữ liệu không hợp lệ | NOT NULL, CHECK, format | Không retry; kiểm tra request/schema |
| Xung đột định danh | UNIQUE constraint | Xử lý duplicate/idempotency hoặc trả conflict |
| Không tìm thấy record | UPDATE 0 hàng | Theo contract nghiệp vụ, không tự coi là sự cố hạ tầng |
| Optimistic conflict | expectedVersion cũ | Đọc lại và quyết định hoặc trả 409 |
| Serialization failure | PostgreSQL 40001 | Retry toàn transaction nếu workload và nghiệp vụ cho phép |
| Deadlock | PostgreSQL 40P01 | Retry toàn transaction có giới hạn khi an toàn |
| Pool hết connection | Hết thời gian chờ getConnection | Điều tra pool, giới hạn tải và retry có backoff |
| Lỗi mạng ở COMMIT | Mất ACK dù DB có thể đã commit | Kết quả chưa rõ; dùng idempotency và xác minh trạng thái |
| Lỗi cấu hình/quyền | Credentials, access denied | Cần sửa nguyên nhân; không retry liên tục |

**Timeout không chứng minh thao tác ghi chưa xảy ra.** Một client có thể mất phản hồi sau khi database đã commit. Nếu code tự bắt mọi lỗi rồi tạo orderId mới để retry, một yêu cầu có thể tạo hai đơn.

### 14.2. Đặt idempotency ở ranh giới phù hợp

Ví dụ endpoint tạo đơn nhận requestKey ổn định:

~~~sql
CREATE TABLE order_requests (
    tenant_id bigint NOT NULL,
    request_key uuid NOT NULL,
    request_hash text NOT NULL,
    order_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, request_key),
    UNIQUE (tenant_id, order_id)
);
~~~

Trong cùng transaction, application service yêu cầu repository:

1. Thử ghi requestKey (và dấu vết payload) được bảo vệ bằng UNIQUE.
2. Nếu key đã tồn tại, kiểm tra payload khớp và trả lại orderId cũ.
3. Nếu key mới, tạo order và ghi các record liên quan.
4. COMMIT một lần cho key và order.
5. Nếu ACK commit mất, request mới vẫn dùng **cùng key**, cho phép đọc lại hoặc replay an toàn theo contract.

Không lưu key chỉ trong RAM nếu nhiều instance/restart có thể xảy ra. Không xóa key trước khi hết cửa sổ retry thực tế. Nếu API còn gọi cổng thanh toán bên ngoài, cần idempotency tương ứng ở cổng thanh toán; transaction DB không bao phủ nó.

### 14.3. Retry phải bao quanh đúng transaction

Nếu @Transactional đặt ở method inner được gọi qua proxy, lớp retry bên ngoài phải tạo **transaction mới cho mỗi attempt**. Việc retry riêng câu UPDATE sau khi transaction bị serialization failure là sai vì dữ liệu đọc trước đó có thể đã lỗi thời.

Đừng nhét chính sách retry phân tán vào DAO với mục tiêu “mọi SELECT/UPDATE tự chạy lại vài lần”: điều này che khuất việc những SQL thuộc **một transaction lớn hơn** và có thể tạo side effect ngoài DB.

## 15. Thiết kế API của repository không đồng nghĩa tối ưu SQL

Một interface đẹp vẫn có thể được triển khai bằng câu SQL chậm. Việc tách ranh giới làm cho nơi tối ưu truy vấn rõ ràng hơn, chứ không làm các vấn đề hiệu năng tự biến mất.

### 15.1. Nhận diện N+1

Một query lấy 100 đơn, sau đó code vòng lặp gọi repository.findItems(orderId) cho từng đơn tạo thêm 100 query. Tổng cộng 101 truy vấn dù màn hình chỉ cần một trang danh sách.

Các lựa chọn:

- Tạo read projection JOIN với các trường cần thiết.
- Dùng batch fetch hoặc truy vấn theo tập order IDs, sau đó map về nhóm.
- Dùng fetch plan JPA phù hợp; tránh JOIN FETCH nhiều collection gây bùng nổ số hàng.
- Đo số query thật bằng log/metrics ở môi trường test.

### 15.2. Index phải gắn với predicate thực tế

Nếu truy vấn chính là:

~~~sql
SELECT id, status, total_amount
FROM orders
WHERE tenant_id = :tenantId
ORDER BY created_at DESC, id DESC
LIMIT :pageSize;
~~~

Một index bắt đầu bằng tenant_id rồi các cột sắp xếp có thể hỗ trợ truy cập hiệu quả hơn việc quét toàn bộ bảng, tùy dữ liệu và planner. Hãy kiểm chứng bằng EXPLAIN (ANALYZE, BUFFERS) trên dữ liệu đại diện và xét chi phí cập nhật index; đừng thêm index cho mọi cột chỉ vì repository có method tìm kiếm.

### 15.3. Batch và giới hạn truy vấn

- Batch insert/update giúp giảm round-trip nhưng cần kiểm soát transaction size và xử lý lỗi từng lô.
- Projection chỉ tải cột cần dùng, giảm network và object mapping.
- LIMIT và keyset pagination tránh đưa hàng triệu dòng tới JVM.
- Timeout truy vấn và connection acquisition timeout là hai loại khác nhau.
- Chỉ cache khi có chính sách invalidation, TTL và consistency phù hợp; cache không tự tạo ranh giới giao dịch chung với DB.

### 15.4. Ngăn abstraction che đi truy vấn khó

GenericRepository<T> với phương thức findAll(Specification<T>) không phải lúc nào là contract tốt cho use case. Nó có thể khiến tầng trên tạo query tùy ý, khó kiểm soát tenant scoping, N+1 và mục tiêu hiệu năng. Với truy vấn phức tạp, một interface hẹp, có tên rõ ràng như findOrdersReadyForSettlement() thường dễ kiểm thử và tối ưu hơn.

## 16. Kiểm thử theo ranh giới trách nhiệm

### 16.1. Unit test domain không cần database

~~~java
@Test
void cannotConfirmCancelledOrder() {
    Order order = new Order(
        new TenantId(10),
        new OrderId(UUID.randomUUID()),
        OrderStatus.CANCELLED,
        3
    );

    assertThrows(IllegalStateException.class, order::confirm);
}
~~~

Test này chứng minh quy tắc trạng thái của Order, không chứng minh SQL mapping hay transaction. Nó nhanh, đơn giản và không cần test container.

### 16.2. Unit test application service với fake repository

~~~java
public final class InMemoryOrderRepository implements OrderRepository {
    private final Map<UUID, Order> data = new HashMap<>();

    @Override
    public Optional<Order> findById(TenantId tenant, OrderId id) {
        return Optional.ofNullable(data.get(id.value()))
            .filter(order -> order.tenantId().equals(tenant));
    }

    @Override
    public boolean updateStatusIfVersionMatches(
            TenantId tenant, OrderId id,
            OrderStatus expected, OrderStatus next, long version) {
        Order existing = data.get(id.value());

        if (existing == null
                || !existing.tenantId().equals(tenant)
                || existing.status() != expected
                || existing.version() != version) {
            return false;
        }
        data.put(id.value(), new Order(tenant, id, next, version + 1));
        return true;
    }

    public void put(Order order) {
        data.put(order.id().value(), order);
    }
}
~~~

Fake repository giúp kiểm tra application service quyết định đúng khi order không tồn tại hoặc version mismatch, nhưng nó **không thay thế integration test**: HashMap không có isolation, row locks, SQL constraints, JDBC connection hoặc hành vi PostgreSQL.

Có thể dùng mock để xác nhận ứng dụng gọi appendOutbox sau khi cập nhật thành công, nhưng test tương tác không chứng minh hai thao tác thực sự commit nguyên tử khi triển khai thật.

### 16.3. Integration test persistence adapter với database thật

Kiểm thử dùng database gần với production và migration thật, có thể thông qua Testcontainers hoặc hạ tầng staging chuyên dụng:

- INSERT và SELECT trả đúng mapping kiểu UUID, DECIMAL, timestamp và enum.
- Query bắt buộc có tenant_id, không đọc chéo tenant.
- UNIQUE/CHECK/FK được DB cưỡng chế.
- Hai request cùng expectedVersion không cùng ghi đè thành công.
- Method use case ghi order và outbox cùng transaction; nếu append outbox lỗi thì order rollback.
- Transaction dùng nhiều repository có cùng DataSource/transaction manager.
- Lazy relation và mapping proxy hoạt động trong scope đúng.
- Query danh sách có giới hạn số hàng, không gây N+1 bất ngờ.
- Khi SQL ném exception, connection/statement được hoàn trả, không giữ transaction treo.

Không dùng H2 như bằng chứng duy nhất cho concurrency và SQL đặc thù PostgreSQL. Hai database có thể khác nhau về isolation, locking, SQLSTATE và cú pháp.

### 16.4. Kiểm thử concurrency có điều phối

Thử hai connection riêng, dùng barrier để hai transaction cùng đọc phiên bản cũ rồi mới cập nhật. Assert sau commit rằng invariant và version đúng. Test này có thể phát hiện lost update/write skew mà unit test đơn luồng không thấy.

Khi mô phỏng lỗi COMMIT mất phản hồi, xác minh requestKey vẫn ngăn tạo tác động thứ hai. Đừng chỉ assert “có exception”; hãy assert trạng thái database sau khi hệ thống khôi phục.

## 17. Anti-pattern thường gặp

| Anti-pattern | Vì sao có vấn đề | Hướng thay thế |
|---|---|---|
| Controller trực tiếp tạo JDBC Connection | HTTP dính vào SQL/resource lifecycle | Controller gọi application service |
| Service nhận Connection rồi trả ResultSet cho UI | Rò tài nguyên và persistence details | Mapping trong adapter, trả DTO/domain |
| Một GenericDao chứa mọi SQL của hệ thống | Coupling cao, ownership mơ hồ | DAO/repository theo tính năng hoặc aggregate |
| Repository quyết định gửi email/thu tiền | Trộn I/O ngoài DB với persistence và transaction | Application orchestration + port/outbox |
| Domain entity biết JdbcTemplate hoặc EntityManager | Khó test và bị khóa vào framework | Domain model + adapter |
| Mỗi DAO tự commit riêng khi use case có nhiều thao tác | Mất atomicity | Transaction boundary ở use case |
| @Transactional áp mọi method kể cả render và gọi HTTP | Giữ connection/lock lâu | Transaction ngắn quanh DB operation |
| Return JPA entity trực tiếp ra controller | Lazy loading, N+1, rò dữ liệu | Query projection/DTO |
| SELECT rồi INSERT để chống trùng | Hai request có thể cùng thấy rỗng | UNIQUE và xử lý xung đột |
| Bắt mọi SQLException rồi retry với ID mới | Có thể tạo hai thao tác khi mất ACK | Idempotency + phân loại lỗi |
| Chỉ mock DAO, không kiểm thử SQL | Lỗi mapping/constraint/transaction lọt qua | Integration test DB thật |
| Tạo nhiều lớp pass-through chỉ để đúng mô hình | Tăng chi phí mà không thêm trách nhiệm | Giữ abstraction khi nó giải quyết vấn đề cụ thể |

**Một kiến trúc vừa đủ** thường có ít điểm nối nhưng mỗi điểm nối rõ ràng: application service, repository interface khi cần, adapter truy cập DB, domain invariant và tập integration test. Các lớp còn lại xuất hiện khi có yêu cầu thực tế.

## 18. Tình huống thiết kế: hủy đơn có lưu lịch sử

Yêu cầu: người dùng hủy một đơn PENDING; hệ thống cần ghi trạng thái CANCELLED, thêm audit và phát sự kiện cho dịch vụ kho. Không được phát sự kiện nếu transaction DB rollback.

Một cách chia trách nhiệm:

| Thành phần | Nhiệm vụ |
|---|---|
| Controller | Xác thực request, lấy tenant/actor từ security context, chuyển command |
| CancelOrderService | Kiểm tra quyền, đặt transaction boundary, điều phối cập nhật order và outbox |
| Order/domain policy | Quy tắc trạng thái có thể hủy |
| OrderRepository | Đọc order, cập nhật có điều kiện và version |
| AuditDao | Ghi record kiểm toán trong cùng transaction |
| OutboxRepository | Ghi intent phát OrderCancelled trong cùng DB |
| Outbox dispatcher | Sau commit, gửi event qua broker với retry và event ID ổn định |
| Consumer kho | Xử lý idempotent, không lặp lại release reservation |

~~~mermaid
sequenceDiagram
    participant C as Controller
    participant A as CancelOrderService
    participant R as OrderRepository
    participant U as AuditDao
    participant O as OutboxRepository
    participant DB as Database
    C->>A: cancel(tenant, orderId)
    Note over A,DB: BEGIN một local transaction
    A->>R: findById(...)
    R->>DB: SELECT
    DB-->>R: Order PENDING, version=4
    A->>R: updateStatusIfVersionMatches(..., 4)
    R->>DB: UPDATE ... version=4
    A->>U: appendAudit(...)
    U->>DB: INSERT audit
    A->>O: appendOrderCancelled(...)
    O->>DB: INSERT outbox
    Note over A,DB: COMMIT hoặc ROLLBACK cả ba thay đổi
    A-->>C: Kết quả commit theo transaction manager
~~~

Dispatcher chạy **sau đó**, không nằm trong DB transaction nói trên. Khi broker ACK mất, dispatcher có thể gửi lại event; consumer phải chịu được thông điệp trùng. Như vậy các ranh giới dữ liệu, nghiệp vụ và tài nguyên bên ngoài được mô tả rõ, không hứa nguyên tử trên hai hệ thống khác nhau.

### 18.1. Cách đánh giá thiết kế

Hãy tự hỏi:

1. Nếu UPDATE order không có hàng nào bị ảnh hưởng, AuditDao/OutboxRepository có được gọi không?
2. Nếu INSERT audit lỗi, trạng thái order có rollback không?
3. Nếu DB commit thành công nhưng HTTP response bị mất, retry cùng requestKey có tạo audit/event lần hai không?
4. Nếu dispatcher chết ngay sau broker ACK, event trùng có gây release tồn kho hai lần không?
5. Nếu khách hàng thuộc tenant khác đoán được orderId, DAO có vô tình trả dữ liệu không?
6. Nếu khóa order bị tranh chấp, method repository có báo conflict và cho tầng ứng dụng xử lý đúng không?

Câu trả lời phải dựa trên SQL, transaction manager và test thật, không chỉ dựa trên tên class.

## 19. Bài tập tự kiểm tra

### Bài A — Đặt ranh giới sai

Một Controller mở transaction, gọi một Repository.saveOrder(), gửi HTTP API thanh toán, ghi AuditDao, rồi render PDF trong cùng transaction.

**Hỏi:** Vấn đề nằm ở đâu? Nên chia lại trách nhiệm thế nào?

**Gợi ý:** Controller đang gánh orchestration và giữ DB transaction qua mạng/render. Đặt use case ở application service; giữ transaction ngắn cho dữ liệu cần nguyên tử; xử lý thanh toán qua port và state machine/idempotency phù hợp.

### Bài B — DAO hay Repository?

Một interface có phương thức findInvoiceRowsByDateRange trả List<InvoiceReportRow> được dùng cho dashboard. Một interface khác có findById(OrderId) và save(Order aggregate).

**Hỏi:** Tên gọi nào diễn tả vai trò tốt hơn?

**Gợi ý:** Interface đầu thiên về query DAO/read model; interface sau là domain-facing repository. Tên thật có thể khác, nhưng input/output và ownership mới quyết định mức trừu tượng.

### Bài C — N+1

API liệt kê 100 order và gọi getCustomer() cho từng order, tạo tổng cộng 101 câu SQL.

**Hỏi:** Nên thay đổi controller, domain hay adapter?

**Gợi ý:** Thiết kế read projection/query adapter lấy dữ liệu cần hiển thị bằng truy vấn hoặc batch phù hợp; không ép UI duyệt lazy JPA entity ngoài transaction.

### Bài D — Hai use case cùng cập nhật version

Hai request đọc Order version=4. Cả hai muốn đổi status. Một request commit trước.

**Hỏi:** Làm sao ngăn request sau ghi đè mù quáng?

**Gợi ý:** UPDATE có điều kiện version=4, tăng version khi thành công; request thứ hai thấy 0 hàng và báo conflict/đọc lại. Đối với JPA, cân nhắc @Version và kiểm tra đường ghi bulk.

### Bài E — DAO đóng Connection được truyền vào

Application service mở transaction và truyền Connection cho hai DAO. DAO đầu gọi connection.close() sau INSERT.

**Hỏi:** Tại sao không nên đóng?

**Gợi ý:** DAO đầu không sở hữu Connection; transaction coordinator sở hữu nó. DAO chỉ đóng PreparedStatement/ResultSet do mình tạo. Close quá sớm có thể phá transaction nhiều bước.

### Bài F — Giao dịch cross-service

Một OrderRepository thay đổi DB rồi gọi emailClient.send() bên trong method save().

**Hỏi:** Nếu email gửi xong nhưng DB rollback, có rollback email không?

**Gợi ý:** Không. Persistence repository không nên che một side effect không thể hoàn tác như thể nó thuộc ACID transaction. Dùng application orchestration/outbox và thiết kế idempotency nếu email bắt buộc phải gửi.

### Bài G — Unit test có đủ không?

Team tạo FakeOrderRepository trên HashMap, tất cả test use case đều pass nhưng production vẫn có lỗi unique và deadlock.

**Hỏi:** Thiếu tầng kiểm thử nào?

**Gợi ý:** Integration test adapter với DB thực, migration và các lịch concurrent transaction. Fake repository không tái hiện SQL constraint, MVCC, lock hay transaction manager.

## 20. Checklist triển khai ranh giới dữ liệu

- [ ] Đã phân biệt domain policy, application orchestration và thao tác lưu trữ.
- [ ] DAO hoặc adapter có hợp đồng rõ, không phơi Connection/ResultSet cho controller.
- [ ] Repository domain-oriented diễn đạt nhu cầu của use case hoặc aggregate.
- [ ] Chỉ tách interface/adapter bổ sung khi sự tách biệt tạo lợi ích thực tế.
- [ ] Hợp đồng method thể hiện tenant, ownership, điều kiện trạng thái và version khi cần.
- [ ] SQL dùng parameter binding, giới hạn tập dữ liệu và không trả dữ liệu nhạy cảm thừa.
- [ ] Transaction được đặt quanh toàn bộ thay đổi DB cần nguyên tử, trên cùng transaction manager.
- [ ] Repository không âm thầm tạo transaction riêng khiến use case mất atomicity.
- [ ] Bảo vệ UNIQUE/CHECK/FK và invariant dưới truy cập đồng thời.
- [ ] Có chính sách rõ cho conflict, not found, retryable error và ambiguous commit.
- [ ] Các tác động ngoài DB được điều phối qua port/outbox/idempotency thích hợp.
- [ ] Read projection tránh tải aggregate quá lớn, lazy loading và N+1.
- [ ] Có giới hạn kết quả, pagination và index được kiểm chứng bằng execution plan.
- [ ] Tài nguyên JDBC, persistence context và connection có vòng đời rõ ràng.
- [ ] Domain tests, application tests và database integration tests bổ sung cho nhau.
- [ ] Có metrics SQL, connection pool, lock wait, retry và request latency trong production.

**Ghi nhớ:** DAO, Repository và lớp truy cập dữ liệu không phải ba tên thay thế hoàn toàn cho nhau. DAO thường gần truy vấn và record; Repository có thể biểu diễn một tập aggregate/domain object; persistence adapter là mã hiện thực kết nối đến database hoặc nguồn lưu trữ. Ranh giới tốt đặt **quy tắc ở domain, điều phối và transaction ở application service, SQL/mapping ở adapter**, đồng thời vẫn nhìn thẳng vào constraint, concurrency, lỗi kết nối và hiệu năng của DB thật.
