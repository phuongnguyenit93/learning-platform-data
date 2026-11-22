# Thiết kế hợp đồng Repository theo nhu cầu miền

Một hệ thống bán hàng có bảng `orders`. Nếu chỉ nhìn lược đồ database, lập trình viên dễ tạo interface `OrderRepository` với hàng chục phương thức kiểu `findAll()`, `updateColumn()`, `deleteById()` và cho phép mọi tầng gọi tùy ý. Nhưng nghiệp vụ thực sự có thể yêu cầu: **chỉ đơn đang chờ xử lý mới được đổi địa chỉ**, **không ghi đè chỉnh sửa đồng thời** và **một đơn được xác nhận phải đi kèm các thay đổi nhất quán**. Một hợp đồng Repository chỉ phản chiếu bảng dữ liệu sẽ không nói rõ những yêu cầu đó.

**Repository** là một ranh giới truy cập dữ liệu mà ứng dụng nhìn thấy như một tập hợp các đối tượng hoặc aggregate của miền. Hợp đồng Repository (*repository contract*) nên mô tả **những khả năng nghiệp vụ cần từ persistence**, không ép mã miền phụ thuộc vào JDBC, JPA, tên bảng hay SQL cụ thể.

Bài này thuộc chương **Ranh giới ứng dụng** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Người học sẽ thiết kế interface Repository theo use case và bất biến miền, xác định trách nhiệm của application service và adapter, đặt transaction đúng ranh giới, truyền đạt lỗi và kiểm soát đồng thời, sau đó kiểm thử tính tương đương giữa hợp đồng và triển khai Java.

## 1. Hợp đồng Repository là gì?

Một Repository thường có hai phần:

1. **Hợp đồng**: tập phương thức và quy tắc quan sát được — nhận kiểu dữ liệu nào, trả kết quả gì, lỗi nào, bảo đảm đồng thời nào, có tham gia transaction không.
2. **Triển khai**: cách thực hiện hợp đồng bằng JDBC, JPA, jOOQ, SQL thuần hoặc một công nghệ lưu trữ phù hợp.

Trong kiến trúc Ports and Adapters (Hexagonal Architecture), hợp đồng Repository là **outbound port** mà lớp ứng dụng cần, còn lớp persistence cung cấp **adapter** triển khai port đó.

~~~mermaid
flowchart TD
    A[HTTP controller / Message consumer] --> B[Application service]
    B --> C[Domain model và quy tắc nghiệp vụ]
    B --> D[OrderRepository interface - Port]
    D -. được triển khai bởi .-> E[JDBC / JPA Adapter]
    E --> F[(Database)]
~~~

Mã use case phụ thuộc vào **interface**, không phụ thuộc trực tiếp một class `JdbcOrderRepository`. Điều này không tự làm mọi DB hoán đổi được — khác biệt transaction, isolation, truy vấn và kiểu dữ liệu vẫn phải được xử lý — nhưng nó giúp giữ hướng phụ thuộc đúng và kiểm thử dễ hơn.

**Cần phân biệt Repository với DAO:** DAO thường hướng tới thao tác dữ liệu/lược đồ (bảng, hàng, câu SQL). Repository thường hướng tới ngôn ngữ miền và vòng đời của entity/aggregate. Trong các dự án nhỏ hai cách đặt tên có thể chồng lấn; quan trọng là hợp đồng có bảo vệ được ranh giới kiến trúc và ý nghĩa use case hay không.

## 2. Bắt đầu từ nhu cầu miền, không phải CRUD của bảng

Xét use case **đổi địa chỉ giao hàng**:

> Khách hàng đã mở trang chi tiết đơn hàng. Khi gửi yêu cầu đổi địa chỉ, hệ thống chỉ chấp nhận nếu đơn vẫn ở trạng thái `PENDING` và chưa ai sửa đơn kể từ lúc khách hàng mở trang. Nếu đơn đã giao cho vận chuyển hoặc dữ liệu đã đổi, hệ thống phải từ chối rõ ràng.

Để thực hiện use case này, application service cần:

- Tìm **một đơn theo định danh miền**.
- Lấy trạng thái, địa chỉ và phiên bản dữ liệu của đơn.
- Yêu cầu domain model kiểm tra điều kiện đổi địa chỉ.
- Lưu thay đổi nhưng **chỉ nếu phiên bản cũ còn đúng**.
- Phân biệt không tìm thấy, không đủ quyền, vi phạm quy tắc nghiệp vụ, xung đột và lỗi hạ tầng.

Đó là nhu cầu có thể dùng để thiết kế Repository. Một interface chỉ có `updateShippingAddress(id, text)` không thể hiện việc kiểm tra phiên bản hay bảo đảm domain rule.

### Ma trận từ use case sang hợp đồng

| Câu hỏi của use case | Nhu cầu truy cập dữ liệu | Đặc điểm hợp đồng |
| --- | --- | --- |
| Đơn hàng có tồn tại không? | Tra cứu theo ID | `Optional<Order>` hoặc kết quả tương đương |
| Có được đổi địa chỉ không? | Đọc trạng thái liên quan | Trả object chứa trạng thái cần đánh giá |
| Dữ liệu có bị sửa từ lần đọc trước không? | Dùng revision/version | Lệnh ghi mang `expectedRevision` |
| Có cần lưu nhiều thay đổi cùng lúc không? | Các bước cùng một transaction | Transaction boundary thuộc use case |
| Khi DB lỗi, API trả gì? | Phân loại lỗi | Không biến SQL timeout thành “không tìm thấy” |

Đừng thêm `findAll()`, `deleteEverything()` hay truy vấn tùy ý chỉ vì framework tự sinh được; hãy xem chúng có phục vụ use case hợp lệ và có giới hạn an toàn không.

## 3. Ngôn ngữ miền thể hiện qua tên và kiểu

Tên phương thức và kiểu tham số là phần quan trọng của hợp đồng. So sánh:

~~~java
// Interface quá gần cấu trúc bảng, chưa rõ ý nghĩa nghiệp vụ.
interface GenericOrderDao {
    Map<String, Object> selectRow(String table, long id);
    void updateColumn(String table, long id, String field, Object value);
}
~~~

với:

~~~java
public interface OrderRepository {
    Optional<Order> findById(OrderId id);
    void add(Order newOrder);
    long save(Order changedOrder, long expectedRevision);
}
~~~

Interface thứ hai vẫn là một ví dụ tối giản, nhưng đã diễn đạt rõ: **đối tượng thuộc miền Order**, có vòng đời thêm/lưu và khi lưu có điều kiện theo revision. Use case hoặc domain model quyết định *có được đổi địa chỉ hay không*; Repository thực hiện việc lưu một cách an toàn.

Các kiểu giá trị miền giúp tránh nhầm lẫn:

~~~java
import java.util.Objects;
import java.util.UUID;

public record OrderId(UUID value) {
    public OrderId {
        Objects.requireNonNull(value, "Order ID");
    }
}

public record ShippingAddress(String street, String city) {
    public ShippingAddress {
        if (street == null || street.isBlank()
                || city == null || city.isBlank()) {
            throw new IllegalArgumentException("Địa chỉ không hợp lệ");
        }
    }
}
~~~

Một `OrderId` giúp phân biệt định danh đơn với `CustomerId` hoặc `ProductId`, dù dữ liệu vật lý có thể đều là UUID/BIGINT. Với module nhỏ có thể dùng kiểu nguyên thủy nếu chi phí thêm value object không đáng; nhưng các giới hạn nghiệp vụ quan trọng nên được biểu đạt rõ bằng tên và kiểu.

## 4. Repository thường thao tác trên aggregate, không phải từng bảng

Trong Domain-Driven Design, **aggregate** là nhóm đối tượng có ranh giới nhất quán, với một *aggregate root* làm điểm truy cập để bảo vệ các bất biến nội bộ. Repository thường được thiết kế cho aggregate root — không bắt buộc một Repository cho mỗi bảng.

Ví dụ:

~~~text
Order (aggregate root)
  ├── OrderLine
  ├── ShippingAddress
  └── OrderStatus

Các bảng vật lý có thể là:
  orders
  order_lines
  order_shipping_addresses
~~~

Một thao tác `order.changeShippingAddress(next)` phải giữ đúng ràng buộc của đơn; adapter có thể ghi nhiều bảng để lưu aggregate. Application service không cần biết từng bảng nào được cập nhật.

Ngược lại, không nên làm một aggregate khổng lồ chứa cả Order, Inventory, Payment và Shipment chỉ vì toàn bộ quy trình “đặt hàng” đi qua các thành phần đó. Mỗi nhóm có vòng đời, chủ sở hữu và yêu cầu đồng thời khác nhau. Nếu chia thành nhiều aggregate/dịch vụ, cần thiết kế **trạng thái trung gian, transaction, outbox hoặc điều phối nhiều bước** thay vì hứa một Repository đơn lẻ sẽ commit tất cả mọi thứ.

**Quy tắc định hướng:** chọn ranh giới aggregate theo **bất biến phải giữ đồng bộ và nhu cầu thay đổi cùng nhau**, rồi mới quyết định Repository và lược đồ bên dưới. Đây là quyết định thiết kế miền, không thể suy hoàn toàn từ số bảng.

## 5. Ví dụ domain model: đơn hàng tự bảo vệ quy tắc

Ví dụ đơn hàng có ba trạng thái: `PENDING` (chờ xử lý), `SHIPPED` (đã chuyển vận) và `CANCELLED` (đã hủy). Chỉ được đổi địa chỉ khi đơn vẫn `PENDING`.

~~~java
import java.util.Objects;

public enum OrderStatus {
    PENDING, SHIPPED, CANCELLED
}

public record Order(
        OrderId id,
        OrderStatus status,
        ShippingAddress shippingAddress,
        long revision) {

    public Order {
        Objects.requireNonNull(id);
        Objects.requireNonNull(status);
        Objects.requireNonNull(shippingAddress);
        if (revision < 0) {
            throw new IllegalArgumentException("Revision không hợp lệ");
        }
    }

    public Order changeShippingAddress(ShippingAddress next) {
        Objects.requireNonNull(next);
        if (status != OrderStatus.PENDING) {
            throw new IllegalStateException(
                    "Chỉ đơn đang chờ xử lý mới được đổi địa chỉ");
        }
        return new Order(id, status, next, revision);
    }
}
~~~

Đây là mô hình **immutable** minh họa bằng Java record. Phương thức `changeShippingAddress()` trả một Order mới nhưng **giữ nguyên revision đã đọc**; Repository dùng revision đó để thực hiện ghi có điều kiện, rồi trả revision mới sau khi cập nhật thành công. Ứng dụng có thể chọn entity mutable thay vì record; quan trọng là quy tắc không bị rải trong controller và câu SQL.

Tình huống hai tác vụ chạy đồng thời:

~~~text
T0: Order(id=O1, status=PENDING, revision=5)
T1: Khách hàng đọc revision=5 và chuẩn bị địa chỉ mới.
T2: Bộ phận vận chuyển chuyển trạng thái SHIPPED; revision tăng lên 6.
T3: Khách gửi yêu cầu đổi địa chỉ với expectedRevision=5.
T4: Lệnh ghi WHERE revision=5 không còn khớp -> xung đột.
~~~

Điều kiện “đang PENDING” do domain model kiểm tra tại bản đã đọc; **kiểm tra version lúc ghi** chặn việc trạng thái thay đổi sau bước đọc. Điều này yêu cầu **mọi đường ghi vào aggregate phải tăng revision**, bao gồm cả cập nhật trạng thái SHIPPED bằng batch/native SQL. Nếu có writer bỏ qua revision, hàng rào này mất hiệu lực.

## 6. Hợp đồng Repository phải nói rõ ngữ nghĩa thao tác

Một interface thực tế cần nhiều hơn chữ ký phương thức. Phải mô tả điều kiện đầu vào, hậu điều kiện và lỗi quan sát được.

~~~java
import java.util.Optional;

public interface OrderRepository {
    // Không tìm thấy -> Optional.empty().
    // Lỗi DB không được biến thành empty().
    Optional<Order> findById(OrderId id);

    // Tạo một order mới. Trùng ID -> lỗi rõ ràng.
    void add(Order newOrder);

    // Lưu aggregate khi DB vẫn ở expectedRevision.
    // Thành công -> trả revision mới.
    // 0 dòng -> OrderWriteConflictException hoặc lỗi tương đương.
    long save(Order changedOrder, long expectedRevision);
}
~~~

Trong bài, quy ước:

- `findById` trả `Optional.empty()` chỉ khi **không có** đơn theo ID trong phạm vi truy vấn. Không trả `null` và không nuốt `SQLException` thành empty.
- `add` từ chối ID đã tồn tại; lỗi unique constraint phải được chuyển thành lỗi có ý nghĩa. Nếu use case cần chống gửi trùng request, phải có thêm idempotency key/ràng buộc phù hợp.
- `save` **không phải upsert**: không tự tạo đơn nếu ID không tồn tại; luôn kiểm tra `expectedRevision`.
- `save` trả revision mới khi lệnh ghi thực sự cập nhật được bản ghi; kết quả này **chưa đồng nghĩa transaction bao ngoài đã commit**.
- Nếu ghi không khớp ID/revision, adapter ném `OrderWriteConflictException`; có thể phân biệt “đã bị xóa” và “đã thay đổi” bằng một truy vấn khác khi cần, nhưng kết quả quan sát thêm vẫn có thể thay đổi ngay sau đó.
- Tất cả lời gọi phải tham gia đúng **transaction context do application service quản lý** nếu use case yêu cầu nhiều thay đổi cùng thành công.

Trong Java, có thể định nghĩa ngoại lệ dùng chung giữa hợp đồng và adapter:

~~~java
public class OrderWriteConflictException extends RuntimeException {
    public OrderWriteConflictException(String message) {
        super(message);
    }
}

public class OrderAlreadyExistsException extends RuntimeException {
    public OrderAlreadyExistsException(String message) {
        super(message);
    }
}
~~~

Tên và kiểu lỗi cần ổn định cho người gọi. Không nên bắt mọi lỗi hạ tầng rồi ném `OrderWriteConflictException`: DB không kết nối được khác hoàn toàn việc một người khác đã sửa đơn.

## 7. Application service điều phối, domain quyết định, Repository lưu

Ví dụ một use case đổi địa chỉ trong Spring:

~~~java
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ChangeShippingAddressService {
    private final OrderRepository orders;

    public ChangeShippingAddressService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public long change(UUID rawOrderId, ShippingAddress next,
                       long expectedRevision) {
        OrderId id = new OrderId(rawOrderId);
        Order current = orders.findById(id)
                .orElseThrow(() -> new OrderNotFoundException(id));

        // Phát hiện form cũ từ trước khi request bắt đầu.
        if (current.revision() != expectedRevision) {
            throw new OrderWriteConflictException(
                    "Đơn đã thay đổi từ lúc khách hàng đọc");
        }

        // Quy tắc nghiệp vụ nằm trong domain model.
        Order changed = current.changeShippingAddress(next);

        // CAS tại database bắt race giữa SELECT và UPDATE.
        return orders.save(changed, current.revision());
    }
}

public class OrderNotFoundException extends RuntimeException {
    public OrderNotFoundException(OrderId id) {
        super("Không tìm thấy đơn: " + id.value());
    }
}
~~~

Ví dụ giả định một transaction manager đã được cấu hình, phương thức `change()` được gọi qua Spring proxy đúng cách, và adapter của `OrderRepository` tham gia transaction Spring đó. Giá trị trả về là **revision được cấp bởi câu ghi trong transaction**; khi Spring proxy trả thành công cho caller, transaction do proxy quản lý thông thường đã hoàn tất commit. Nếu commit thất bại, lời gọi có thể ném lỗi ở ranh giới transaction.

Phân chia trách nhiệm:

| Thành phần | Nhiệm vụ | Không nên làm |
| --- | --- | --- |
| **Controller/API** | Xác thực đầu vào, lấy principal, chuyển HTTP request sang use case, ánh xạ lỗi | Tự viết SQL hoặc quyết định tính hợp lệ bằng cách sửa thẳng cột |
| **Application service** | Điều phối use case, kiểm tra quyền nghiệp vụ, đặt ranh giới transaction, gọi repository và dịch vụ khác | Nhúng chi tiết `ResultSet` / `EntityManager` vào domain |
| **Domain model** | Giữ quy tắc, bất biến và trạng thái hợp lệ | Phụ thuộc database connection hoặc HTTP framework |
| **Repository port** | Tuyên bố khả năng lưu/tải dữ liệu và kết quả/lỗi | Lộ cấu trúc driver hoặc cung cấp CRUD tùy ý không kiểm soát |
| **Persistence adapter** | Ánh xạ dữ liệu, SQL/ORM, kiểm tra version, chuyển lỗi hạ tầng | Quyết định workflow nghiệp vụ hoặc tự gửi email trong transaction |

**Lưu ý về quyền:** việc user có quyền sửa đơn hay không còn cần được xác minh từ principal và dữ liệu sở hữu đơn; kiểm tra `revision` chỉ chống ghi đè, **không phải kiểm tra phân quyền**.

## 8. Triển khai JDBC adapter cho hợp đồng

Một adapter có thể triển khai `OrderRepository` bằng `JdbcTemplate`. Ví dụ dưới đây tập trung vào `findById` và `save`; phần `add` phải dùng SQL `INSERT`, ràng buộc khóa chính và ánh xạ lỗi trùng ID theo hợp đồng.

~~~java
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class JdbcOrderRepository implements OrderRepository {
    private final JdbcTemplate jdbc;

    public JdbcOrderRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public Optional<Order> findById(OrderId id) {
        String sql = "SELECT id, status, ship_street, ship_city, revision " +
                     "FROM customer_orders WHERE id = ?";
        List<Order> rows = jdbc.query(sql, (rs, rowNum) -> new Order(
                new OrderId(UUID.fromString(rs.getString("id"))),
                OrderStatus.valueOf(rs.getString("status")),
                new ShippingAddress(
                        rs.getString("ship_street"),
                        rs.getString("ship_city")),
                rs.getLong("revision")), id.value());
        return rows.stream().findFirst();
    }

    @Override
    public void add(Order newOrder) {
        jdbc.update(
                "INSERT INTO customer_orders " +
                "(id, status, ship_street, ship_city, revision) " +
                "VALUES (?, ?, ?, ?, ?)",
                newOrder.id().value(),
                newOrder.status().name(),
                newOrder.shippingAddress().street(),
                newOrder.shippingAddress().city(),
                newOrder.revision());
        // Bắt lỗi trùng khóa từ Spring DataAccessException và ánh xạ
        // thành OrderAlreadyExistsException theo chính sách adapter.
    }

    @Override
    public long save(Order changedOrder, long expectedRevision) {
        String sql = "UPDATE customer_orders " +
                "SET status = ?, ship_street = ?, ship_city = ?, " +
                "revision = revision + 1 " +
                "WHERE id = ? AND revision = ?";

        int rows = jdbc.update(sql,
                changedOrder.status().name(),
                changedOrder.shippingAddress().street(),
                changedOrder.shippingAddress().city(),
                changedOrder.id().value(),
                expectedRevision);

        if (rows != 1) {
            throw new OrderWriteConflictException(
                    "Đơn không tồn tại hoặc revision đã thay đổi");
        }
        return expectedRevision + 1;
    }
}
~~~

**Giả định:** bảng `customer_orders` có khóa chính `id` kiểu UUID tương ứng driver, cột `revision BIGINT NOT NULL` và các trường phù hợp; adapter này là minh họa, chưa phải mã hoàn chỉnh cho sản xuất. `add` ở đây cần bổ sung logic chuyển lỗi trùng khóa thực tế thay vì chỉ bình luận. Có thể biểu diễn mapping bằng converter riêng nếu tên trạng thái ở DB khác enum Java.

Điểm quan trọng của `save` là:

~~~sql
UPDATE customer_orders
SET ship_street = :street,
    ship_city = :city,
    revision = revision + 1
WHERE id = :id
  AND revision = :expectedRevision;
~~~

Kiểm tra version và cập nhật nằm **trong một câu SQL**. Trường hợp hai request cùng đã đọc `revision=5`, một lệnh cập nhật được phép thành công và nâng lên `6`; lệnh còn lại không được âm thầm ghi đè. Một số database/isolation có thể trả lỗi serialization thay vì trả số hàng `0` — adapter cần xử lý theo hợp đồng.

### Một điểm thiết kế quan trọng của ví dụ

Đoạn `save` cập nhật toàn bộ các trường thuộc phạm vi Order đã mô hình hóa. Nếu dự án có writer khác sửa thêm những trường thuộc cùng aggregate, chúng **phải** kiểm tra và tăng chung revision. Nếu chỉ cần cập nhật địa chỉ mà không muốn chạm các cột khác, adapter có thể có lệnh chuyên biệt hơn miễn vẫn giữ hợp đồng và bất biến. Đừng đưa toàn bộ câu SQL chuyên biệt trở lại controller chỉ để tối ưu một cột.

## 9. Repository và transaction boundary không phải một thứ

Một phương thức `save()` không nhất thiết là một **transaction nghiệp vụ hoàn chỉnh**. Use case xác nhận đơn có thể cần:

1. Cập nhật trạng thái đơn.
2. Ghi bản ghi lịch sử hoặc outbox.
3. Ghi giữ chỗ tồn kho trong cùng cơ sở dữ liệu, nếu quy tắc nghiệp vụ yêu cầu.
4. Chỉ trả thành công khi toàn bộ thao tác cần nguyên tử đã commit.

Nếu mỗi Repository tự mở/commit một transaction độc lập, có thể xảy ra tình huống đơn đã xác nhận nhưng audit/outbox chưa tồn tại. Với Spring, ranh giới `@Transactional` thường đặt ở **application service**, còn các repository adapter tham gia cùng transaction manager.

~~~mermaid
sequenceDiagram
    participant API as Controller
    participant S as Application Service
    participant R as OrderRepository
    participant O as OutboxRepository
    participant DB as Database
    API->>S: confirmOrder(orderId)
    Note over S,DB: Một transaction do application service quản lý
    S->>R: findById(orderId)
    R->>DB: SELECT order
    DB-->>R: Order hiện tại
    S->>S: Order.confirm() theo quy tắc miền
    S->>R: save(changed, expectedRevision)
    R->>DB: UPDATE ... WHERE revision = ?
    S->>O: add(OrderConfirmed event)
    O->>DB: INSERT outbox_event
    S->>DB: COMMIT theo transaction manager
    DB-->>S: Thành công
    S-->>API: Kết quả
~~~

Không cần đưa phương thức `beginTransaction()`, `commit()` hoặc `rollback()` vào mọi Repository interface nếu transaction được quản lý bởi tầng ứng dụng/framework. Nhưng **hợp đồng phải nêu rõ kỳ vọng tham gia transaction** để triển khai không vô tình dùng connection khác hoặc auto-commit ngoài ý muốn.

Với JDBC thuần, có thể dùng một abstraction `UnitOfWork` hoặc truyền transaction-scoped connection qua adapter một cách có kiểm soát. Không nên để application service phụ thuộc thẳng vào `java.sql.Connection` chỉ vì muốn ghép hai thao tác trong một transaction nếu mục tiêu là giữ lõi ứng dụng độc lập hạ tầng.

### Không chạy I/O ngoài DB lâu trong transaction

Gửi email hoặc gọi cổng thanh toán giữa `BEGIN` và `COMMIT` làm transaction lâu và không có khả năng rollback tác dụng bên ngoài. Nếu cần phát sự kiện sau commit, có thể ghi **transactional outbox** trong cùng transaction DB rồi để worker phát riêng; receiver vẫn cần idempotency để xử lý phát lặp.

## 10. Khi nào cần phương thức theo hành vi chuyên biệt?

Hai kiểu hợp đồng đều có chỗ dùng:

**Kiểu tập hợp aggregate:**

~~~java
Optional<Order> findById(OrderId id);
long save(Order changed, long expectedRevision);
~~~

Phù hợp khi ứng dụng cần tải aggregate, áp quy tắc miền và lưu lại như một đơn vị.

**Kiểu thao tác domain-specific có điều kiện:**

~~~java
ReservationOutcome reserveIfAvailable(
        ProductId productId, int quantity, RequestId requestId);
~~~

Phù hợp khi bất biến có thể được diễn đạt hiệu quả trong SQL, chẳng hạn giảm kho nguyên tử với điều kiện `available >= quantity`. Application service vẫn định nghĩa hành vi nghiệp vụ, còn adapter thực hiện thao tác nguyên tử trong DB.

Không nên cố ép một phép giảm kho đơn giản thành:

~~~java
int count = stockRepository.findAvailable(productId);
stockRepository.setAvailable(productId, count - quantity);
~~~

Cách đọc–tính–ghi này có thể gây **lost update** khi nhiều request cạnh tranh. Repository contract phù hợp hơn có thể là `tryReserve(productId, quantity)`, với ngữ nghĩa rõ ràng về số lượng, lỗi và tác động.

Tuy vậy, đừng biến Repository thành lớp chứa toàn bộ workflow, gửi email, điều phối thanh toán và kiểm tra quyền HTTP. Phương thức chuyên biệt chỉ nên thể hiện **một khả năng persistence cần thiết để bảo vệ bất biến**, không trở thành “application service thứ hai”.

## 11. Thiết kế truy vấn đọc theo mục đích sử dụng

Không phải mọi màn hình cần tải nguyên aggregate. Trang danh sách đơn hàng có thể chỉ cần ID, ngày tạo, trạng thái và tổng tiền. Nếu `findAll()` tải toàn bộ Order cùng các dòng hàng, địa chỉ và lịch sử, hệ thống có thể tốn nhiều I/O và bộ nhớ.

Có thể thiết kế **read port** riêng:

~~~java
public record OrderSummary(
        OrderId id,
        OrderStatus status,
        java.math.BigDecimal total) {}

public interface OrderQuery {
    Page<OrderSummary> findSummaries(
            CustomerId customerId, OrderFilter filter, PageRequest page);
}
~~~

Trong ví dụ, `Page`, `OrderFilter` và `PageRequest` là các kiểu hợp đồng do ứng dụng định nghĩa, không nhất thiết là `org.springframework.data.domain.Page`. Tham số cần mô tả sort được phép, kích thước trang tối đa và ý nghĩa các bộ lọc.

Lựa chọn mô hình:

| Nhu cầu | Cách trả dữ liệu hợp lý |
| --- | --- |
| Sửa một đơn và áp quy tắc miền | Tải Order aggregate với revision |
| Hiển thị danh sách nhiều đơn | DTO/projection `OrderSummary` |
| Báo cáo tổng hợp | Read model hoặc query service chuyên biệt |
| Duyệt dữ liệu khổng lồ | Phân trang keyset/cursor với hợp đồng về thứ tự và vòng đời tài nguyên |

Đây là cách áp dụng tinh thần **CQRS nhẹ**: tách API đọc tối ưu cho hiển thị khỏi API ghi bảo vệ bất biến, mà không nhất thiết cần hai database hoặc hệ thống sự kiện phức tạp.

### Hợp đồng phân trang phải rõ

Một Repository trả danh sách vô hạn mà không giới hạn page size có thể gây cạn bộ nhớ. Nếu dùng offset pagination, cần định nghĩa thứ tự ổn định và hiểu chi phí/khả năng bỏ sót hoặc trùng khi dữ liệu thay đổi. Nếu dùng keyset, cursor phải gắn với sort/filter và thời hạn hợp lệ; không được giả định một snapshot không đổi qua nhiều request nếu kiến trúc không bảo đảm.

## 12. Lỗi miền, lỗi đồng thời và lỗi hạ tầng

Hợp đồng Repository tốt giúp application service **ra quyết định đúng khi lỗi**, thay vì luôn bắt một `Exception` tổng quát rồi trả HTTP 500 hoặc retry mù.

| Tình huống | Cách biểu diễn ở hợp đồng | Ứng xử thường phù hợp |
| --- | --- | --- |
| Không tìm thấy đơn khi đọc | `Optional.empty()` | Use case trả lỗi không tìm thấy hoặc từ chối tiết lộ tùy quyền |
| Không đủ điều kiện đổi địa chỉ | Lỗi quy tắc miền từ `Order.changeShippingAddress()` | Thông báo trạng thái hiện tại không cho phép |
| Dữ liệu đã bị sửa | `OrderWriteConflictException` | Trả conflict, tải lại hoặc cho người dùng giải quyết |
| Tạo mới trùng ID | `OrderAlreadyExistsException` | Phân biệt request trùng và xung đột thực thể |
| Mất kết nối, SQL timeout, database quá tải | Lỗi hạ tầng / persistence failure | Quan sát, quyết định retry hữu hạn nếu an toàn |
| Commit bị ngắt mạng, kết quả chưa rõ | Trạng thái không xác định | Tra cứu/đối soát theo idempotency key |

Không nên biến mọi `DataAccessException` thành lỗi xung đột, vì mất kết nối không phải dấu hiệu người khác đã sửa dữ liệu.

**Cẩn trọng với retry:** nếu một transaction đã thất bại, thử lại cần một transaction mới với dữ liệu mới và kiểm tra lại bất biến. Không retry vô hạn hoặc chạy lại tác vụ bên ngoài như thanh toán mà không có idempotency. Khi commit thất bại do mất kết nối, không tự kết luận transaction đã rollback.

## 13. Tính nhất quán của cách đọc: current, snapshot hay replica?

Một phương thức có tên `findById` nhưng đọc từ replica chậm có thể trả bản cũ. Điều này ảnh hưởng trực tiếp use case:

- Màn hình chỉ hiển thị dữ liệu có thể chấp nhận **eventual consistency** nếu sản phẩm cho phép.
- Một lệnh cần kiểm tra và cập nhật bất biến không thể dựa vào bản đọc từ replica cũ rồi ghi thẳng vào primary mà thiếu cơ chế bảo vệ tại thời điểm ghi.
- Nếu yêu cầu “read your writes”, hợp đồng cần ghi rõ mức bảo đảm hoặc dùng nguồn đọc phù hợp.

Ví dụ có thể tách:

~~~java
public interface OrderRepository {
    Optional<Order> findById(OrderId id); // Nguồn authoritative cho command.
    long save(Order changed, long expectedRevision);
}

public interface OrderReadModel {
    Optional<OrderSummary> findSummary(OrderId id); // Có thể eventual.
}
~~~

Không nhất thiết phải đặt tên `findStronglyConsistent` ở mọi nơi; quan trọng là một yêu cầu **không thể thỏa** bằng bản sao chậm phải được nêu rõ. Nếu adapter thay đổi từ primary sang replica, đó có thể là **thay đổi hợp đồng về tính nhất quán**, không chỉ là tối ưu hạ tầng.

## 14. Kiểm thử hợp đồng Repository, không chỉ kiểm thử mock

Một fake/in-memory Repository rất hữu ích để kiểm thử luồng use case. Nhưng **mock không chứng minh** JDBC/JPA adapter thực sự tham gia transaction, phát hiện xung đột và ánh xạ dữ liệu đúng. Cần hai lớp kiểm thử bổ sung.

### 14.1. Unit test domain và application service

Các tình huống:

1. Order đang `PENDING` đổi địa chỉ hợp lệ.
2. Order `SHIPPED` hoặc `CANCELLED` từ chối đổi địa chỉ.
3. `expectedRevision` từ form khác revision hiện tại thì không gọi `save`.
4. Repository trả empty thì service báo không tìm thấy.
5. Repository báo conflict thì service không trả thành công.

Fake Repository dùng cho bài test cần mô phỏng đúng luật version, ví dụ:

~~~java
// Phác thảo phương thức save của một fake:
public long save(Order changed, long expectedRevision) {
    Order stored = byId.get(changed.id());
    if (stored == null || stored.revision() != expectedRevision) {
        throw new OrderWriteConflictException("Conflict");
    }
    long next = expectedRevision + 1;
    byId.put(changed.id(), new Order(
            changed.id(), changed.status(),
            changed.shippingAddress(), next));
    return next;
}
~~~

Fake nên mô phỏng quy tắc của hợp đồng thay vì trả một giá trị thành công cố định cho mọi lần gọi.

### 14.2. Integration/contract test trên database thật

Một bộ test dùng cho mọi triển khai Repository cần xác minh ít nhất:

| Kịch bản | Kết quả cần kiểm tra |
| --- | --- |
| Add một Order hợp lệ | Đọc lại được dữ liệu tương đương |
| Add trùng ID | Không có hai bản ghi; lỗi theo hợp đồng |
| Find ID không tồn tại | Trả empty, không báo lỗi DB giả |
| Save với revision đúng | Cập nhật một bản ghi và tăng revision đúng quy tắc |
| Save với revision cũ | Bị từ chối, dữ liệu đã commit không bị ghi đè |
| Hai transaction cạnh tranh cùng Order | Chỉ một cập nhật dựa trên revision cũ được chấp nhận |
| Transaction chứa update rồi gặp lỗi | Rollback không để lại trạng thái nửa vời |
| Lỗi kết nối hoặc constraint | Chuyển lỗi/giải phóng connection đúng cách |
| Mapping enum, UUID, nullable/decimal | Không mất hoặc làm sai dữ liệu miền |

Đặc biệt, cần thử **hai connection/transaction độc lập** để tái hiện race. Không nên chỉ dùng H2 cho mọi kết luận về isolation nếu sản xuất dùng PostgreSQL hoặc MySQL, vì cơ chế khóa/snapshot khác nhau. Testcontainers hoặc môi trường tích hợp tương ứng giúp xác minh gần điều kiện thật hơn.

## 15. Khi dùng Spring Data JPA, đừng để framework quyết định toàn bộ hợp đồng

Spring Data JPA có `JpaRepository<T, ID>` với nhiều thao tác CRUD, phân trang và truy vấn tiện lợi. Dùng nó ở tầng persistence rất hiệu quả, nhưng **không bắt buộc** lớp ứng dụng phải phụ thuộc trực tiếp vào toàn bộ interface đó.

Một cách tổ chức:

~~~text
application/domain:
  OrderRepository                 <- port dùng trong use case

infrastructure/persistence:
  SpringDataOrderJpaRepository    <- extends JpaRepository<OrderEntity, UUID>
  JpaOrderRepositoryAdapter       <- implements OrderRepository
  OrderEntity + mapper
~~~

Ưu điểm là application service chỉ biết `findById`, `add`, `save` mà nó thực sự dùng, còn adapter tự quyết định ánh xạ entity, câu truy vấn và cách xử lý `@Version`.

Lưu ý riêng với JPA:

- `EntityManager` có **persistence context**, dirty checking và flush; `save()` ở một adapter không nhất thiết đã gửi SQL ngay, và lỗi optimistic lock có thể xuất hiện lúc flush/commit.
- Entity JPA có thể mang proxy/lazy association. Trả thẳng entity cho mọi tầng có thể làm rò rỉ lifecycle và phát sinh lỗi lazy loading sau transaction.
- Nếu interface ứng dụng hứa “lưu sẽ lập tức phát hiện conflict”, adapter phải dùng flush hoặc cách kiểm tra thích hợp; nhưng flush không phải commit.
- Khi dùng `@Version`, **mọi writer** (kể cả bulk update/native SQL) phải tuân theo chính sách kiểm tra/tăng version phù hợp.
- Giao dịch nhiều repository nên do transaction manager chung điều phối; tránh mỗi adapter tự tạo transaction độc lập.

Một adapter không nên nói dối về hậu điều kiện chỉ để giữ interface có vẻ giống triển khai JDBC. Nếu hai công nghệ có semantics khác nhau quan trọng với use case, hãy mô tả chính xác thời điểm lỗi có thể được quan sát.

## 16. Những dấu hiệu hợp đồng Repository thiết kế chưa tốt

| Dấu hiệu | Rủi ro | Hướng sửa |
| --- | --- | --- |
| Interface lộ `ResultSet`, `EntityManager`, `Session` hoặc SQL string tùy ý | Domain/application phụ thuộc hạ tầng, khó kiểm thử | Trả kiểu miền/DTO, đưa SQL sang adapter |
| Một Repository cho mỗi bảng bất kể aggregate | Quy tắc miền bị chia nhỏ, dễ commit dở dang | Tổ chức theo aggregate và use case |
| Chỉ có `save(Object)`, không nói về version | Ghi đè dữ liệu cũ hoặc upsert ngoài ý muốn | Định nghĩa CAS/expectedRevision hoặc chính sách đồng thời |
| Phương thức `findAll()` không giới hạn | Bộ nhớ và DB quá tải | Truy vấn có filter, phân trang và sort |
| Mọi lỗi được trả thành `Optional.empty()` | Che lỗi hạ tầng thành “không có dữ liệu” | Phân loại lỗi rõ ràng |
| Repository tự gửi email hoặc gọi payment provider | Gắn persistence với side effect, khó rollback | Điều phối tại application service; dùng outbox khi cần |
| Mỗi phương thức repository tự commit | Không thể ghép nhiều thao tác thành một use case nguyên tử | Transaction boundary ở service/unit of work |
| Tầng API cập nhật trực tiếp cột trạng thái | Bỏ qua domain invariant và chính sách đồng thời | Đi qua use case và domain operation |
| Phụ thuộc tên cột bảng trong API | Khó tiến hóa schema mà không sửa nghiệp vụ | Dùng kiểu miền và adapter mapping |
| Thêm hàng trăm phương thức `findBy...` ngẫu hứng | Port khó hiểu, không theo use case | Nhóm query theo mục đích, có read model khi phù hợp |
| Giả định dữ liệu luôn đọc từ primary | Chọn sai nguồn đọc khi chuyển sang replica | Mô tả yêu cầu consistency trong hợp đồng |

Không phải mọi phương thức chuyên biệt đều là “overengineering”. Một method `reserveIfAvailable` có thể là abstraction **đúng** khi nó thể hiện một bất biến và buộc database kiểm tra nguyên tử. Ngược lại, một generic Repository tưởng như tái sử dụng tốt nhưng không hỗ trợ use case an toàn có thể làm chi phí sửa lỗi cao hơn.

## 17. Bài tập thiết kế hợp đồng

Giả sử hệ thống có nghiệp vụ:

> Một khách hàng đặt giữ 3 vé cho sự kiện. Khi còn đủ vé, hệ thống phải trừ số vé còn lại và ghi yêu cầu giữ chỗ. Gửi lại cùng một request do timeout không được giữ vé hai lần. Một màn hình quản trị cần xem danh sách yêu cầu giữ chỗ theo trạng thái và thời gian.

Hãy trả lời:

1. Aggregate nào cần bảo vệ bất biến “số vé không âm”? Bạn có chọn một Repository cho mỗi bảng không?
2. Thiết kế interface cho thao tác **giữ vé nếu còn đủ**, sao cho hai request đồng thời không thể cùng vượt qua điều kiện khi chỉ đủ vé cho một request.
3. Nếu việc trừ vé và tạo reservation thuộc cùng database, transaction boundary nên đặt ở đâu?
4. Khi request bị gửi lại sau commit nhưng phản hồi thất lạc, có nên dựa vào `quantity` và `eventId` để chặn mọi yêu cầu giống nhau không?
5. Danh sách quản trị có cần tải aggregate đầy đủ hay có thể dùng DTO/read port?

Một phác thảo hợp đồng có thể là:

~~~java
public interface TicketInventoryRepository {
    // Thao tác nguyên tử trong DB; chỉ trừ nếu còn đủ.
    boolean tryReserve(EventId eventId, int quantity);
}

public interface ReservationRepository {
    void add(Reservation reservation);
    Optional<Reservation> findByRequestId(RequestId requestId);
}

public interface ReservationQuery {
    Page<ReservationSummary> search(
            ReservationFilter filter, PageRequest page);
}
~~~

Trong câu trả lời, cần chỉ rõ `EventId`, `RequestId`, `Reservation`, `Page`... là các kiểu miền/contract cần được định nghĩa. `tryReserve` có thể được hiện thực bằng SQL cập nhật có điều kiện:

~~~sql
UPDATE ticket_inventory
SET available = available - :quantity
WHERE event_id = :eventId
  AND available >= :quantity;
~~~

Chỉ tiếp tục khi cập nhật đúng một dòng. Nếu cần ghi reservation cùng việc trừ vé, dùng **cùng transaction** và rollback toàn bộ nếu ghi reservation thất bại. Để chống gửi trùng, dùng `RequestId`/idempotency key với unique constraint và lưu kết quả xử lý cùng transaction. Hai ý định mua vé khác nhau hoàn toàn có thể có cùng `eventId` và `quantity`, nên không deduplicate chỉ dựa vào payload.

Đây là **một hướng thiết kế**, không phải bắt buộc có ba Repository khác nhau. Nếu số vé là một phần của cùng aggregate và có ranh giới nhất quán thích hợp, có thể gộp các hành vi tương ứng. Hãy giải thích lựa chọn bằng bất biến, tần suất cập nhật, phạm vi transaction và nhu cầu đọc/ghi thực tế.

## 18. Checklist áp dụng khi viết Repository contract

Trước khi chốt một interface, kiểm tra:

1. **Use case:** những lời gọi nào thực sự cần thiết, tên phương thức có dùng ngôn ngữ miền không?
2. **Đơn vị nhất quán:** thao tác trên aggregate nào, bất biến nào phải được giữ?
3. **Kiểu dữ liệu:** có trả domain model/DTO phù hợp thay vì driver object hoặc entity persistence không?
4. **Ngữ nghĩa thiếu dữ liệu:** `Optional.empty()` khác lỗi kết nối hay conflict như thế nào?
5. **Kiểm soát đồng thời:** cần expected version, cập nhật nguyên tử, khóa hoặc isolation nào?
6. **Transaction:** ai mở/commit/rollback, những repository nào phải cùng tham gia?
7. **Lỗi và retry:** những lỗi nào retry được, khi nào commit outcome chưa rõ, có cần idempotency?
8. **Đọc dữ liệu:** consistency, sort, filter, page size và hiệu năng có được định nghĩa rõ?
9. **Bảo mật:** scope theo principal/tenant và quyền truy cập đặt ở đâu, làm sao tránh đọc chéo tenant?
10. **Tiến hóa:** thay schema hoặc adapter có buộc sửa application service không?
11. **Kiểm thử:** fake có tuân hợp đồng và integration tests có kiểm tra transaction/race trên DB thật không?

**Kết luận:** hợp đồng Repository tốt không phải interface có nhiều phương thức CRUD nhất, mà là ranh giới đủ rõ để application service và domain model thực hiện đúng nghiệp vụ dù persistence bên dưới thay đổi. Hãy bắt đầu từ bất biến miền, biểu đạt hành vi và lỗi có ý nghĩa, sau đó để adapter xử lý SQL/ORM, connection, transaction participation và các tối ưu vật lý một cách minh bạch.
