# Lập trình với giao diện JdbcAggregateOperations

Spring Data JDBC cung cấp giao diện `JdbcAggregateOperations` để thao tác trực tiếp với aggregate trong database. Thay vì gọi các phương thức repository đã định nghĩa sẵn, service hoặc custom repository fragment có thể dùng giao diện này để lưu, đọc, cập nhật, xóa và truy vấn aggregate theo kiểu miền nghiệp vụ.

`JdbcAggregateOperations` là abstraction cho các thao tác aggregate. Lớp triển khai phổ biến là `JdbcAggregateTemplate`, được Spring cấu hình và quản lý như một bean. Giao diện này làm việc ở cấp aggregate root: khi lưu hoặc đọc root, Spring Data JDBC xử lý cả các entity con thuộc aggregate theo mapping đã khai báo.

Bài học trình bày cách inject giao diện, cách chọn giữa `save`, `insert` và `update`, cách đọc/xóa aggregate, tạo truy vấn bằng `Query` và `Criteria`, cũng như cách phối hợp transaction và optimistic locking.

## 1. JdbcAggregateOperations nằm ở đâu?

Spring Data JDBC có nhiều lớp truy cập dữ liệu với mức trừu tượng khác nhau:

| Thành phần | Trách nhiệm |
| --- | --- |
| `CrudRepository` / repository chuyên biệt | API repository, derived query, query method và abstraction theo aggregate |
| `JdbcAggregateOperations` | Giao diện thao tác aggregate bằng code |
| `JdbcAggregateTemplate` | Lớp triển khai `JdbcAggregateOperations` |
| `JdbcTemplate` | API JDBC mức thấp để chạy SQL và làm việc với ResultSet |

Repository là lựa chọn tự nhiên khi ứng dụng cần một hợp đồng truy cập dữ liệu ổn định với các phương thức tìm kiếm được đặt tên. `JdbcAggregateOperations` hữu ích khi service hoặc custom repository cần gọi thao tác aggregate theo điều kiện lập trình động, hoặc cần một API template tổng quát mà không muốn tự viết SQL cho các thao tác CRUD.

Khác với `JdbcTemplate`, `JdbcAggregateOperations` hiểu metadata Spring Data JDBC: aggregate root, ID, embedded object, collection entity con, converter và version. Khi lưu `PurchaseOrder` có `OrderLine`, thao tác được thực hiện trên aggregate thay vì yêu cầu ứng dụng tự ghi từng bảng.

## 2. Inject giao diện qua Spring

Khi dự án đã cấu hình Spring Data JDBC và có DataSource/transaction infrastructure phù hợp, Spring tạo bean `JdbcAggregateTemplate`. Vì lớp này triển khai `JdbcAggregateOperations`, ứng dụng có thể inject giao diện bằng constructor:

~~~java
import org.springframework.data.jdbc.core.JdbcAggregateOperations;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final JdbcAggregateOperations aggregates;

    public OrderService(JdbcAggregateOperations aggregates) {
        this.aggregates = aggregates;
    }
}
~~~

Cách inject theo interface giúp service phụ thuộc vào hợp đồng thao tác aggregate. Không cần tự tạo `JdbcAggregateTemplate` bằng `new` hoặc tự khởi tạo converter, mapping context, dialect và data access strategy.

Nếu ứng dụng có cấu hình Spring Data JDBC tùy chỉnh, hãy kiểm tra bean template được đăng ký và có thể inject theo interface. Với cấu hình chuẩn, Spring quản lý các thành phần này.

### Package thường dùng

~~~java
import org.springframework.data.jdbc.core.JdbcAggregateOperations;
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;
import org.springframework.data.domain.Sort;
import org.springframework.transaction.annotation.Transactional;
~~~

`JdbcAggregateOperations` thuộc package `org.springframework.data.jdbc.core`. `Query` và `Criteria` thuộc package Spring Data Relational. Đừng nhầm chúng với các API query của Spring Data JPA.

## 3. Mô hình aggregate dùng trong ví dụ

Giả sử hệ thống quản lý đơn hàng. `PurchaseOrder` là aggregate root; danh sách `OrderLine` là các entity con thuộc vòng đời đơn hàng.

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Version
    private Long version;

    private String status;

    @MappedCollection(idColumn = "order_id", keyColumn = "line_no")
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String status, List<OrderLine> lines) {
        this.status = status;
        this.lines = new ArrayList<>(lines);
    }

    public void markPaid() {
        this.status = "PAID";
    }

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public String getStatus() {
        return status;
    }

    public List<OrderLine> getLines() {
        return List.copyOf(lines);
    }
}
~~~

Entity con:

~~~java
public record OrderLine(String sku, int quantity) {
}
~~~

Schema minh họa cho PostgreSQL:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    version BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL
);

CREATE TABLE order_lines (
    order_id BIGINT NOT NULL REFERENCES purchase_orders(id),
    line_no INTEGER NOT NULL,
    sku VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

`@MappedCollection` chỉ ra cột back reference `order_id` và cột key `line_no` trong bảng con. `@Version` bật optimistic locking cho root. Tên bảng và cột phải khớp mapping và migration của ứng dụng.

Khi thao tác qua `JdbcAggregateOperations`, truyền kiểu root `PurchaseOrder.class`. Không truyền `OrderLine.class` để yêu cầu template lưu riêng một child vốn thuộc aggregate này.

## 4. Lưu aggregate với save

`save` là lựa chọn tổng quát khi caller muốn lưu aggregate và để Spring Data JDBC quyết định thao tác insert hay update dựa trên trạng thái mới/cũ của entity.

~~~java
PurchaseOrder order = new PurchaseOrder(
    "NEW",
    List.of(
        new OrderLine("BOOK-01", 2),
        new OrderLine("PEN-02", 3)
    )
);

PurchaseOrder saved = aggregates.save(order);

Long orderId = saved.getId();
~~~

Với ID tự sinh, database tạo ID cho root và Spring Data JDBC đưa giá trị đó vào instance được trả về. Hãy sử dụng đối tượng trả về từ `save`, đặc biệt khi mô hình entity bất biến có thể cần tạo instance mới để chứa ID/version vừa sinh.

`save` lưu toàn bộ aggregate: root và các entity con được khai báo trong mapping. Nó không chỉ cập nhật một thuộc tính đơn lẻ.

### Spring Data xác định entity mới thế nào?

Mặc định, Spring Data kiểm tra property được đánh dấu `@Id`:

- ID là `null` thì entity thường được xem là mới.
- ID kiểu số nguyên thủy có giá trị mặc định `0` thì được xem là mới.
- ID có giá trị khác mặc định thì thường được xem là entity đã tồn tại.

Nếu có property `@Version`, Spring Data có thể dùng version để nhận diện trạng thái mới: version null hoặc 0 biểu thị entity mới. Nếu entity triển khai `Persistable`, việc xác định trạng thái mới được giao cho `isNew()`.

Điều này quan trọng khi ứng dụng tự cấp UUID hoặc ID trước khi insert. Một ID đã có giá trị không tự chứng minh hàng đó đã tồn tại trong database. Hãy chọn chiến lược newness phù hợp, chẳng hạn `@Version` hoặc `Persistable`, hoặc dùng thao tác insert tường minh khi đúng ý định.

## 5. Phân biệt save, insert và update

Ngoài `save`, template API có các thao tác chuyên biệt:

| Phương thức | Ý nghĩa | Khi dùng |
| --- | --- | --- |
| `save(instance)` | Tự chọn insert/update theo trạng thái entity | Thao tác lưu thông thường |
| `insert(instance)` | Luôn thực hiện luồng insert, bỏ qua kiểm tra newness | Caller biết aggregate là mới |
| `update(instance)` | Luôn thực hiện luồng update, bỏ qua kiểm tra newness | Caller biết aggregate đã tồn tại |
| `upsert(instance)` | Insert nếu chưa có ID tương ứng, nếu có thì update | Chỉ dùng khi version/dialect hỗ trợ |

Ví dụ insert rõ ý định:

~~~java
PurchaseOrder created = aggregates.insert(newOrder);
~~~

Ví dụ update rõ ý định:

~~~java
PurchaseOrder current =
    aggregates.findById(orderId, PurchaseOrder.class);

if (current == null) {
    throw new IllegalArgumentException("Order not found: " + orderId);
}

current.markPaid();
PurchaseOrder updated = aggregates.update(current);
~~~

`insert` và `update` không thay thế kiểm tra nghiệp vụ. Nếu caller gọi insert cho một aggregate đã tồn tại, database có thể từ chối do vi phạm khóa chính/unique. Nếu gọi update cho aggregate chưa tồn tại, nó không biến thao tác thành insert. Chọn phương thức theo trạng thái thực tế.

`save` giống `CrudRepository.save` về ý nghĩa. `insert` và `update` bỏ qua bước kiểm tra entity mới/cũ và thực hiện đúng loại thao tác được chỉ định.

### Lưu aggregate đã tồn tại có thể ghi lại các entity con

Spring Data JDBC không duy trì persistence context để theo dõi từng thay đổi nhỏ như một số ORM. Nó không biết trạng thái trước đó của aggregate trong database. Khi lưu một aggregate đã tồn tại, hành vi mặc định là xóa các entity được tham chiếu, cập nhật root rồi insert lại các entity con theo trạng thái hiện tại của object.

Điều đó có nghĩa `save` và `update` là thao tác ở cấp aggregate. Nếu chỉ đổi một thuộc tính của root nhưng aggregate có collection lớn, việc lưu vẫn có thể tạo nhiều câu SQL cho các hàng con. Hãy cân nhắc kích thước aggregate và thiết kế ranh giới aggregate hợp lý; đừng xem `JdbcAggregateOperations` như một API patch một cột.

### Upsert trong phiên bản hỗ trợ

Một số phiên bản Spring Data Relational mới có `upsert(instance)`. Trong Spring Data Relational 4.1, thao tác này yêu cầu ID đã được gán và dialect hỗ trợ native upsert, thường bằng `MERGE` hoặc `INSERT ... ON CONFLICT`.

~~~java
PurchaseOrder stored = aggregates.upsert(orderWithAssignedId);
~~~

`upsert` thực hiện insert nếu chưa có hàng root với ID đó, nếu đã có thì update. API này không hỗ trợ optimistic locking trong phiên bản 4.1 được tham chiếu. Chỉ dùng khi phiên bản dependency và database dialect của dự án hỗ trợ; với phiên bản cũ hơn, phương thức có thể chưa tồn tại.

## 6. Đọc aggregate

`findById` nhận hai thông tin: ID và class của aggregate root. Khác với `CrudRepository.findById`, phương thức template này trả về object hoặc `null` nếu không tìm thấy.

~~~java
PurchaseOrder order =
    aggregates.findById(orderId, PurchaseOrder.class);

if (order == null) {
    throw new IllegalArgumentException("Order not found: " + orderId);
}
~~~

Khi load root, Spring Data JDBC cũng đọc các thành phần thuộc aggregate theo mapping. Ứng dụng không cần tự query bảng `order_lines` chỉ để lắp danh sách dòng hàng vào đơn hàng.

### Tìm tất cả và tìm theo ID

~~~java
List<PurchaseOrder> all =
    aggregates.findAll(PurchaseOrder.class);

List<PurchaseOrder> selected =
    aggregates.findAllById(orderIds, PurchaseOrder.class);
~~~

Các phương thức này trả về collection các aggregate root. `findAll` không có giới hạn có thể đọc rất nhiều dữ liệu; tránh dùng nó cho bảng lớn nếu chỉ cần một phần kết quả.

### Sắp xếp kết quả

~~~java
List<PurchaseOrder> newestFirst = aggregates.findAll(
    PurchaseOrder.class,
    Sort.by(Sort.Direction.DESC, "id")
);
~~~

`Sort` mô tả thứ tự theo property được ánh xạ. Hãy xác nhận tên property và cột thực tế trong mapping của entity.

### Stream dữ liệu

Với API có hỗ trợ, `streamAll` trả về `Stream` để xử lý các aggregate tuần tự:

~~~java
try (Stream<PurchaseOrder> stream =
        aggregates.streamAll(PurchaseOrder.class)) {
    stream.forEach(this::processOrder);
}
~~~

Stream có thể giữ tài nguyên JDBC trong thời gian tiêu thụ. Đóng stream bằng try-with-resources và không giữ nó để dùng sau khi transaction/connection đã kết thúc. Stream không tự động biến một thao tác xử lý thành batch cập nhật; nếu cần ghi, hãy xác định ranh giới transaction và chiến lược batch rõ ràng.

## 7. Đếm và kiểm tra tồn tại

Khi chỉ cần số lượng, không nên load toàn bộ aggregate về Java:

~~~java
long totalOrders = aggregates.count(PurchaseOrder.class);

boolean exists =
    aggregates.existsById(orderId, PurchaseOrder.class);
~~~

Các thao tác này làm việc ở cấp aggregate root. Chúng phù hợp cho kiểm tra tồn tại hoặc số lượng tổng quát.

## 8. Xóa aggregate

Có thể xóa theo object root hoặc ID:

~~~java
PurchaseOrder order =
    aggregates.findById(orderId, PurchaseOrder.class);

if (order != null) {
    aggregates.delete(order);
}
~~~

Hoặc:

~~~java
aggregates.deleteById(orderId, PurchaseOrder.class);
~~~

Xóa theo ID sẽ xóa aggregate, bao gồm các entity con thuộc aggregate. Không cần gọi một lệnh delete riêng cho từng `OrderLine`.

Các thao tác xóa hàng loạt cũng có trong API:

~~~java
aggregates.deleteAllById(orderIds, PurchaseOrder.class);
~~~

`deleteAll(PurchaseOrder.class)` xóa tất cả aggregate thuộc kiểu đó. Đây là thao tác diện rộng, chỉ gọi khi nghiệp vụ thực sự yêu cầu xóa toàn bộ dữ liệu loại này.

Nếu root có `@Version`, xóa bằng object root có thể áp dụng kiểm tra version. `deleteById` không có version của object để so sánh, vì vậy không cung cấp cùng cơ chế optimistic locking như xóa bằng aggregate đã load.

## 9. Tạo truy vấn động với Query và Criteria

Điểm mạnh của template API là có thể tạo điều kiện tìm kiếm bằng code thay vì ghép tên method hoặc nối SQL. `Query` biểu diễn câu SELECT, còn `Criteria` xây dựng điều kiện WHERE.

Ví dụ tìm đơn hàng có trạng thái PAID:

~~~java
import static org.springframework.data.relational.core.query.Criteria.where;

import org.springframework.data.relational.core.query.Query;

Query query = Query.query(
    where("status").is("PAID")
);

List<PurchaseOrder> paidOrders =
    aggregates.findAll(query, PurchaseOrder.class);
~~~

`where("status")` chỉ tới property/cột được mapping; `is("PAID")` tạo điều kiện bằng. Tham số được xử lý thông qua cơ chế query của Spring Data, không cần nối giá trị vào chuỗi SQL.

### Kết hợp nhiều điều kiện

Ví dụ tìm đơn hàng có trạng thái PAID và ID lớn hơn một ngưỡng:

~~~java
Query query = Query.query(
    where("status").is("PAID")
        .and("id").greaterThan(1000L)
);

List<PurchaseOrder> result =
    aggregates.findAll(query, PurchaseOrder.class);
~~~

Có thể dùng các phép so sánh mà `Criteria` hỗ trợ, chẳng hạn `is`, `isNull`, `isNotNull`, `greaterThan`, `greaterThanOrEquals`, `lessThan`, `lessThanOrEquals`, `like`, `not` và `in`.

Ví dụ điều kiện LIKE:

~~~java
Query query = Query.query(
    where("status").like("P%")
);
~~~

`Criteria.like` dùng pattern như được truyền vào; nó không tự động biến pattern thành prefix/substring theo cách derived query `StartingWith` hoặc `Containing` làm. Nếu dùng wildcard, hãy chuẩn bị pattern đúng với ý định.

### Tìm một aggregate theo Query

~~~java
Optional<PurchaseOrder> result = aggregates.findOne(
    Query.query(where("status").is("PAID")),
    PurchaseOrder.class
);
~~~

`findOne` trả về `Optional`. Nó phù hợp khi truy vấn có tối đa một kết quả theo thiết kế. Nếu nhiều hàng thỏa điều kiện, API có thể ném `IncorrectResultSizeDataAccessException`; không dùng `findOne` cho điều kiện có thể khớp nhiều đơn hàng.

### Count và exists với Query

~~~java
long paidCount = aggregates.count(
    Query.query(where("status").is("PAID")),
    PurchaseOrder.class
);

boolean hasOpenOrders = aggregates.exists(
    Query.query(where("status").is("OPEN")),
    PurchaseOrder.class
);
~~~

Các thao tác này giúp kiểm tra tập dữ liệu theo điều kiện mà không cần load toàn bộ danh sách aggregate về ứng dụng.

## 10. Transaction khi gọi nhiều thao tác

Một use case có thể gồm nhiều thao tác aggregate hoặc thêm thao tác repository khác. Hãy đặt transaction ở service boundary bằng `@Transactional`.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final JdbcAggregateOperations aggregates;
    private final OrderAuditRepository audits;

    public OrderApplicationService(
            JdbcAggregateOperations aggregates,
            OrderAuditRepository audits) {
        this.aggregates = aggregates;
        this.audits = audits;
    }

    @Transactional
    public PurchaseOrder markPaid(Long id) {
        PurchaseOrder order =
            aggregates.findById(id, PurchaseOrder.class);

        if (order == null) {
            throw new IllegalArgumentException("Order not found: " + id);
        }

        order.markPaid();

        PurchaseOrder saved = aggregates.update(order);
        audits.save(OrderAudit.statusChanged(id, "PAID"));

        return saved;
    }
}
~~~

Nếu thao tác cập nhật đơn hàng hoặc ghi audit thất bại và exception làm transaction rollback, các thay đổi trong cùng transaction được rollback cùng nhau. Điều này giả định chúng dùng cùng transaction manager/DataSource và exception không bị nuốt theo cách khiến transaction vẫn commit.

`@Transactional` cần được gọi qua Spring proxy theo cơ chế quản lý transaction của ứng dụng. Trong cấu hình proxy-based thông thường, tự gọi method transactional bên trong cùng instance không đi qua proxy, nên không kích hoạt annotation như một lời gọi từ bean khác.

### Không tách child khỏi aggregate chỉ để gọi template

Nếu `OrderLine` thuộc vòng đời của `PurchaseOrder`, hãy thao tác qua root. Không cần tìm ID root rồi tự insert/update child bằng SQL riêng. Làm như vậy khiến service tự quản lý khóa ngoại và có thể phá vỡ ranh giới nhất quán của aggregate.

Nếu một đối tượng có vòng đời, danh tính và quy trình độc lập, hãy đánh giá nó như aggregate riêng; khi đó một thao tác template trên root riêng có thể hợp lý.

## 11. Optimistic locking với @Version

Nếu nhiều request có thể cập nhật cùng đơn hàng, `@Version` giúp phát hiện ghi đè thay đổi của request khác.

Trong ví dụ, root có:

~~~java
@Version
private Long version;
~~~

Spring Data JDBC đưa version hiện tại vào điều kiện update. Nếu một request đã cập nhật hàng và tăng version, request khác dùng version cũ không thể cập nhật như thể dữ liệu vẫn chưa thay đổi; framework ném `OptimisticLockingFailureException`.

Ví dụ xử lý ở service:

~~~java
try {
    return aggregates.update(order);
} catch (OptimisticLockingFailureException ex) {
    throw new OrderConflictException(
        "Order was changed by another operation", ex
    );
}
~~~

Không nên tự tăng version trong Java rồi mong template tự hiểu. Hãy để cơ chế Spring Data quản lý version và dùng exception để xử lý xung đột theo nghiệp vụ.

Optimistic locking áp dụng ở aggregate root và giúp phát hiện cạnh tranh khi cập nhật/xóa có version. `upsert` trong Spring Data Relational 4.1 hiện không hỗ trợ optimistic locking, vì vậy đừng dùng upsert nếu use case phụ thuộc vào kiểm tra version.

## 12. Dùng JdbcAggregateOperations trong custom repository

Một custom repository fragment có thể dùng `JdbcAggregateOperations` để bổ sung thao tác mà repository interface không biểu đạt thuận tiện.

Ví dụ hợp đồng tùy chỉnh:

~~~java
public interface PurchaseOrderRepositoryCustom {
    PurchaseOrder markPaid(Long id);
}
~~~

Phần triển khai:

~~~java
import org.springframework.data.jdbc.core.JdbcAggregateOperations;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
public class PurchaseOrderRepositoryCustomImpl
        implements PurchaseOrderRepositoryCustom {

    private final JdbcAggregateOperations aggregates;

    public PurchaseOrderRepositoryCustomImpl(
            JdbcAggregateOperations aggregates) {
        this.aggregates = aggregates;
    }

    @Override
    @Transactional
    public PurchaseOrder markPaid(Long id) {
        PurchaseOrder order =
            aggregates.findById(id, PurchaseOrder.class);

        if (order == null) {
            throw new IllegalArgumentException("Order not found: " + id);
        }

        order.markPaid();
        return aggregates.update(order);
    }
}
~~~

Repository chính có thể kết hợp fragment:

~~~java
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long>,
                PurchaseOrderRepositoryCustom {
}
~~~

Tên class triển khai và cách Spring phát hiện fragment cần theo quy ước repository fragment của phiên bản Spring Data trong dự án. Ý tưởng quan trọng là custom implementation dùng cùng bean template mà Spring đã cấu hình, nhờ đó giữ nguyên mapping, converter và transaction infrastructure.

## 13. So sánh repository, JdbcAggregateOperations và JdbcTemplate

| Nhu cầu | Nên cân nhắc |
| --- | --- |
| CRUD tiêu chuẩn và repository interface rõ ràng | `CrudRepository` / `ListCrudRepository` |
| Derived query theo tên phương thức | Repository |
| Query method có `@Query` | Repository |
| Thao tác aggregate bằng code trong service hoặc custom fragment | `JdbcAggregateOperations` |
| Tạo `Query`/`Criteria` động và chuyển kết quả thành aggregate | `JdbcAggregateOperations` |
| SQL tùy chỉnh ở mức thấp, join/projection riêng hoặc thao tác không theo aggregate mapping | `JdbcTemplate` / JDBC client |

`JdbcAggregateOperations` không phải bản thay thế cho mọi repository. Nếu một interface repository đã diễn đạt tốt use case, hãy tiếp tục dùng nó. Template API hữu ích khi logic cần xây dựng truy vấn động hoặc khi custom repository muốn tái sử dụng cơ chế persist/load aggregate.

`JdbcTemplate` cho phép điều khiển SQL trực tiếp hơn, nhưng caller phải tự quản lý câu SQL, bind parameter, row mapping và quan hệ bảng. Không dùng template aggregate cho câu SQL báo cáo phức tạp chỉ vì nó nằm trong Spring Data JDBC; hãy chọn API đúng với công việc.

## 14. Những giới hạn cần nhớ

- Template thao tác theo aggregate root và metadata mapping; không phải công cụ patch một cột tùy ý.
- `findById` trả về `null` nếu không tìm thấy, không phải `Optional`.
- `findAll` có thể tải toàn bộ aggregate; cân nhắc kích thước dữ liệu.
- `streamAll` cần được đóng và tiêu thụ trong thời gian tài nguyên JDBC còn hợp lệ.
- `findOne(Query, Class)` yêu cầu tối đa một kết quả; nhiều kết quả sẽ gây lỗi kích thước kết quả.
- Phân trang là nhu cầu thường phù hợp hơn với repository. Một số overload `findAll(..., Pageable)` trên template đã bị deprecated trong Spring Data Relational 4.0 và dự kiến bị loại bỏ.
- `upsert` chỉ có ở các phiên bản mới (từ 4.1), yêu cầu ID đã gán, dialect hỗ trợ và hiện không có optimistic locking.
- `save`/`update` ghi lại trạng thái aggregate; các entity con có thể bị xóa rồi insert lại, nên chi phí phụ thuộc kích thước aggregate.

### Không dùng template để bỏ qua aggregate boundary

Nếu `Customer` là aggregate riêng và `PurchaseOrder` chỉ giữ ID khách hàng, lưu đơn hàng không có nghĩa template sẽ tự lưu Customer. Một thao tác trên root chỉ quản lý thành phần thuộc aggregate root đó. Hãy dùng service/application workflow để phối hợp nhiều aggregate và xác định transaction phù hợp.

## 15. Kiểm thử thao tác template

Có thể dùng integration test để xác nhận template lưu và khôi phục cả root lẫn child:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.jdbc.DataJdbcTest;
import org.springframework.data.jdbc.core.JdbcAggregateOperations;

@DataJdbcTest
class JdbcAggregateOperationsTest {

    @Autowired
    JdbcAggregateOperations aggregates;

    @Test
    void insertsAndLoadsWholeAggregate() {
        PurchaseOrder order = new PurchaseOrder(
            "NEW",
            List.of(
                new OrderLine("BOOK-01", 2),
                new OrderLine("PEN-02", 3)
            )
        );

        PurchaseOrder saved = aggregates.insert(order);

        assertThat(saved.getId()).isNotNull();

        PurchaseOrder loaded =
            aggregates.findById(saved.getId(), PurchaseOrder.class);

        assertThat(loaded).isNotNull();
        assertThat(loaded.getStatus()).isEqualTo("NEW");
        assertThat(loaded.getLines()).hasSize(2);
    }
}
~~~

Ví dụ giả định migration đã tạo bảng và cấu hình test có database phù hợp. Nếu dùng entity có version, có thể kiểm tra version thay đổi sau update và hai cập nhật cạnh tranh không thể cùng ghi thành công với cùng một version cũ.

Nên kiểm thử các trường hợp:

1. Insert aggregate mới và xác nhận ID được sinh.
2. Đọc aggregate và xác nhận entity con được khôi phục.
3. Update root và xác nhận thay đổi được lưu.
4. Delete root và xác nhận child thuộc aggregate được xóa.
5. Gọi findById với ID không tồn tại và xác nhận kết quả null.
6. Dùng Query/Criteria với điều kiện phù hợp và xác nhận tập kết quả.
7. Nếu dùng `@Version`, kiểm thử xung đột optimistic locking.

## 16. Lỗi thường gặp khi lập trình với template

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Không inject được JdbcAggregateOperations | Spring Data JDBC chưa cấu hình hoặc bean template bị thay đổi | Kiểm tra starter, DataSource và cấu hình JDBC |
| findById trả null | Không có root với ID đó | Xử lý trường hợp không tìm thấy trước khi update |
| save insert thay vì update | Entity bị nhận diện là mới | Kiểm tra ID, version hoặc Persistable.isNew |
| save update thay vì insert | ID đã có giá trị và entity bị nhận diện là tồn tại | Dùng insert khi biết chắc aggregate mới hoặc sửa chiến lược newness |
| update không tạo hàng mới | update luôn thực hiện update | Dùng insert hoặc save đúng trạng thái |
| Insert bị duplicate key | Aggregate đã tồn tại hoặc ID được cấp trùng | Kiểm tra ID và constraint |
| Child bị ghi lại khi update | Spring Data JDBC đồng bộ toàn bộ aggregate | Đánh giá kích thước aggregate và tần suất cập nhật |
| findOne báo nhiều kết quả | Điều kiện query không duy nhất | Dùng findAll hoặc bổ sung điều kiện duy nhất |
| Dữ liệu không được rollback cùng nhau | Các thao tác không dùng chung transaction/DataSource | Đặt transaction ở service và kiểm tra transaction manager |
| OptimisticLockingFailureException | Version đã thay đổi bởi transaction khác | Reload aggregate và xử lý xung đột nghiệp vụ |
| Query không sắp xếp như mong muốn | Sort dùng sai property hoặc không khai báo Sort | Chỉ định Sort và kiểm tra mapping |

## 17. Quy trình chọn thao tác

| Ý định | API gợi ý |
| --- | --- |
| Lưu aggregate mới/cũ mà không tự chọn nhánh | `save(instance)` |
| Chắc chắn aggregate mới | `insert(instance)` |
| Chắc chắn aggregate đã tồn tại | `update(instance)` |
| Insert hoặc update bằng native upsert | `upsert(instance)` nếu phiên bản/dialect hỗ trợ |
| Đọc một root theo ID | `findById(id, Root.class)` |
| Đọc nhiều root theo điều kiện động | `findAll(query, Root.class)` |
| Đếm kết quả theo điều kiện | `count(query, Root.class)` |
| Kiểm tra có kết quả | `exists(query, Root.class)` |
| Xóa root và thành phần aggregate | `delete(root)` hoặc `deleteById(id, Root.class)` |

Trước khi chọn API, hãy xác định trạng thái mới/cũ của aggregate, ID được sinh hay cấp trước, có dùng optimistic locking không, query có thể trả về bao nhiêu hàng và thao tác có cần nằm cùng transaction với nghiệp vụ khác không.

## 18. Bài tập tự thực hành

### Bài 1 — Inject interface

Tạo một service nhận `JdbcAggregateOperations` qua constructor. Giải thích vì sao service có thể nhận interface trong khi bean thực tế là `JdbcAggregateTemplate`.

### Bài 2 — Save và newness

Tạo một aggregate có ID tự sinh. Gọi `save` trước và sau khi aggregate đã tồn tại. Quan sát ID và SQL. Thử một entity có ID cấp trước để tìm hiểu vai trò của `@Version` hoặc `Persistable`.

### Bài 3 — Insert và update

Gọi `insert` cho aggregate mới, sau đó gọi `update` để đổi trạng thái. Thử gọi nhầm `insert` lần thứ hai và ghi lại lỗi database. Thử `update` với một ID không tồn tại và quan sát hành vi.

### Bài 4 — Query và Criteria

Tạo Query tìm đơn hàng theo status, kết hợp thêm điều kiện ID. Dùng `findAll`, `findOne`, `count` và `exists` để so sánh kiểu kết quả.

### Bài 5 — Transaction

Trong một method `@Transactional`, cập nhật đơn hàng rồi ghi audit. Tạo lỗi ở bước audit và xác nhận cả hai thay đổi được rollback khi dùng chung transaction manager.

### Bài 6 — Optimistic locking

Tạo hai instance của cùng một aggregate ở hai transaction. Cập nhật instance thứ nhất, sau đó thử cập nhật instance thứ hai với version cũ. Xác nhận xung đột và thiết kế cách thông báo cho caller.

### Bài 7 — Custom repository fragment

Tạo custom repository fragment có phương thức nghiệp vụ `markPaid`. Dùng `JdbcAggregateOperations` để load và update root trong cùng transaction.

## 19. Tài liệu tham khảo chính thức

- [Spring Data Relational — Persisting Entities](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html): cách template lưu aggregate, xác định entity mới, query động và optimistic locking.
- [Spring Data Relational — JdbcAggregateOperations API](https://docs.spring.io/spring-data/jdbc/docs/current/api/org/springframework/data/jdbc/core/JdbcAggregateOperations.html): danh sách phương thức và kiểu trả về của giao diện.
- [Spring Data Relational — JdbcAggregateTemplate API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/JdbcAggregateTemplate.html): lớp triển khai template.
- [Spring Data Relational — Query API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/query/Query.html): cấu trúc query được tạo bằng code.
- [Spring Data Relational — Criteria API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/query/Criteria.html): các toán tử điều kiện cho WHERE clause.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): cách dùng `@Transactional` để xác định transaction boundary.

`JdbcAggregateOperations` cung cấp API trực tiếp để làm việc với aggregate theo mapping của Spring Data JDBC. Hãy inject bean qua constructor, chọn `save`, `insert` hoặc `update` theo trạng thái entity, dùng Query/Criteria cho điều kiện động và đặt transaction ở ranh giới nghiệp vụ khi cần phối hợp nhiều thao tác. Nhớ rằng template lưu aggregate như một đơn vị; các entity con và version được xử lý theo mapping, nên cách thiết kế aggregate quyết định cả tính nhất quán lẫn chi phí ghi dữ liệu.
