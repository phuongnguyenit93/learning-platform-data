# Khi nào dùng JdbcAggregateTemplate thay cho repository?

Trong **Spring Data Relational JDBC**, repository là cách truy cập aggregate quen thuộc: khai báo một interface theo kiểu aggregate root, kế thừa CrudRepository hoặc ListCrudRepository, rồi dùng các method như findById, save và deleteById. Tuy nhiên, Spring Data JDBC còn cung cấp **JdbcAggregateTemplate**, một API dạng template để thao tác trực tiếp với aggregate mà không cần đi qua một repository interface cụ thể.

Hai cách này dùng chung mô hình ánh xạ aggregate của Spring Data JDBC, nhưng phù hợp với những kiểu tổ chức code khác nhau. Repository phù hợp với phần lớn use case CRUD gắn với một loại aggregate và các truy vấn được diễn đạt qua method. JdbcAggregateTemplate hữu ích khi cần gọi thao tác aggregate theo cách lập trình, chọn kiểu aggregate tại runtime, hoặc yêu cầu tường minh insert hay update.

Điểm cần nhớ là JdbcAggregateTemplate vẫn làm việc ở **cấp aggregate**. Nó không phải JdbcTemplate để chạy SQL tùy ý, cũng không thay thế hành vi domain. Bài học này giải thích cách hoạt động, những trường hợp nên dùng, cách tích hợp vào service và các giới hạn cần cân nhắc.

## 1. Repository là lựa chọn mặc định cho CRUD theo aggregate

Giả sử ứng dụng quản lý đơn hàng. PurchaseOrder là aggregate root và các OrderLine thuộc về đơn hàng:

~~~text
PurchaseOrder (aggregate root)
├── id
├── orderNumber
├── status
└── lines
    ├── OrderLine
    └── OrderLine
~~~

Repository có thể khai báo:

~~~java
import java.util.List;
import java.util.Optional;
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    Optional<PurchaseOrder> findByOrderNumber(String orderNumber);

    List<PurchaseOrder> findByStatus(String status);
}
~~~

Service sử dụng repository:

~~~java
@Service
public class OrderService {

    private final PurchaseOrderRepository orders;

    public OrderService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    public PurchaseOrder getOrder(long id) {
        return orders.findById(id)
            .orElseThrow(() ->
                new NoSuchElementException("Không tìm thấy đơn hàng"));
    }
}
~~~

Repository mang lại một abstraction theo kiểu domain:

- Kiểu aggregate và kiểu ID được xác định ngay trong khai báo.
- Các method CRUD có sẵn, không phải tự viết phần truy cập cơ bản.
- Có thể thêm derived query như findByStatus.
- Repository là ranh giới rõ ràng giữa application service và persistence.
- Code gọi không phải truyền Class<PurchaseOrder> cho mỗi thao tác.

Với một ứng dụng có các aggregate rõ ràng và CRUD thông thường, repository thường là cách dễ đọc và dễ bảo trì nhất.

## 2. JdbcAggregateTemplate là gì?

JdbcAggregateTemplate là API dạng template của Spring Data JDBC để thực hiện các thao tác persistence trên aggregate. Class nằm trong package:

~~~java
org.springframework.data.jdbc.core.JdbcAggregateTemplate
~~~

Thay vì khai báo một repository interface riêng cho từng aggregate, code có thể gọi template và truyền object hoặc kiểu domain cần thao tác.

Các thao tác thường dùng gồm:

| Thao tác | Mục đích |
|---|---|
| insert(aggregate) | Chèn một aggregate mới |
| update(aggregate) | Cập nhật aggregate đã tồn tại |
| save(aggregate) | Chọn insert/update theo chiến lược nhận diện entity mới |
| findById(id, AggregateType.class) | Tìm aggregate theo ID và kiểu root |
| findAll(AggregateType.class) | Đọc các aggregate của kiểu chỉ định |
| existsById(id, AggregateType.class) | Kiểm tra ID có tồn tại |
| count(AggregateType.class) | Đếm aggregate |
| deleteById(id, AggregateType.class) | Xóa aggregate theo ID |
| delete(aggregate) | Xóa aggregate được truyền vào |

API cụ thể và overload có thể thay đổi theo phiên bản Spring Data JDBC. Hãy dùng Javadoc của phiên bản được khai báo trong dự án khi cần xác nhận chữ ký chính xác.

Điểm khác biệt dễ thấy là các thao tác đọc/xóa theo ID nhận thêm kiểu aggregate, ví dụ:

~~~java
PurchaseOrder.class
~~~

Template cần kiểu này để biết metadata mapping nào cần dùng, vì bản thân ID như 1001L không cho biết nó thuộc bảng aggregate nào.

## 3. Template vẫn giữ mapping và semantics của aggregate

Tên “Template” có thể khiến người học nghĩ JdbcAggregateTemplate chỉ là một lớp tiện ích bao quanh câu SQL. Thực tế, đây là API persistence của Spring Data JDBC, làm việc với metadata aggregate và cơ chế mapping của framework.

Khi thao tác với PurchaseOrder, template sử dụng mapping đã khai báo cho root và các thành phần thuộc aggregate, ví dụ collection con qua @MappedCollection:

~~~java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("order_number")
    private String orderNumber;

    private String status;

    @MappedCollection(idColumn = "order_id")
    private Set<OrderLine> lines = new LinkedHashSet<>();

    // Constructor và hành vi domain.
}
~~~

Khi lưu aggregate root, framework biết cách ánh xạ các phần tử con theo cấu hình. Ứng dụng vẫn làm việc với một aggregate thay vì tự ghi từng bảng bằng các câu SQL rời rạc.

Điều đó có nghĩa:

- Template dùng metadata mapping, converter và cơ chế persistence của Spring Data JDBC.
- Các thành phần thuộc aggregate được xử lý theo mapping của root.
- Entity con không tự trở thành aggregate root chỉ vì có bảng hoặc thuộc tính @Id.
- Các aggregate khác được tham chiếu bằng ID vẫn có vòng đời riêng.
- Template không tự áp dụng quy tắc nghiệp vụ; domain method và application service vẫn chịu trách nhiệm đó.

## 4. Trường hợp nên dùng JdbcAggregateTemplate

### 4.1. Cần thao tác aggregate nhưng không muốn tạo repository riêng

Một thành phần hạ tầng có thể cần ghi một loại aggregate trong một luồng tổng quát, nhưng không cần các derived query hoặc repository API riêng.

Ví dụ, một service nhập dữ liệu đã chuẩn hóa thành PurchaseOrder:

~~~java
@Service
public class OrderImportService {

    private final JdbcAggregateTemplate aggregateTemplate;

    public OrderImportService(JdbcAggregateTemplate aggregateTemplate) {
        this.aggregateTemplate = aggregateTemplate;
    }

    @Transactional
    public PurchaseOrder importNewOrder(PurchaseOrder order) {
        return aggregateTemplate.insert(order);
    }
}
~~~

Ở đây use case biết chắc object là aggregate mới và muốn yêu cầu INSERT tường minh. Không cần tạo một repository chỉ để gọi đúng một thao tác insert.

Ví dụ trên giả định Spring Data JDBC đã được cấu hình và JdbcAggregateTemplate được đăng ký làm bean trong application context, như cấu hình thông thường của Spring Data JDBC/Spring Boot.

### 4.2. Muốn chọn insert hoặc update một cách tường minh

Đây là một lý do thực tế để chọn template. Repository CRUD thường đưa code gọi đến save(), còn template cung cấp các thao tác riêng:

~~~java
aggregateTemplate.insert(newOrder);
aggregateTemplate.update(existingOrder);
~~~

Khi luồng nghiệp vụ đã xác định chắc chắn trạng thái:

- Dùng insert khi biết aggregate chưa tồn tại và muốn tạo mới.
- Dùng update khi biết aggregate đã tồn tại và muốn cập nhật.

Việc chọn tường minh giúp code thể hiện ý định rõ hơn, đặc biệt trong import, migration dữ liệu hoặc adapter tích hợp. Database vẫn phải thực thi primary key và unique constraint; insert không làm mất khả năng xảy ra duplicate key.

Không dùng insert chỉ vì object có ID khác null. Một ID có thể được ứng dụng cấp trước khi hàng tồn tại. Trạng thái persistence phải được xác định từ use case, không chỉ nhìn giá trị ID.

### 4.3. Chọn kiểu aggregate tại runtime

Các method của template nhận kiểu domain như PurchaseOrder.class. Vì vậy, trong một thành phần generic, kiểu aggregate có thể được truyền vào từ cấu hình hoặc từ một luồng xử lý đã được kiểm soát.

Ví dụ một helper đọc aggregate:

~~~java
public class AggregateReader {

    private final JdbcAggregateTemplate template;

    public AggregateReader(JdbcAggregateTemplate template) {
        this.template = template;
    }

    public <T> Optional<T> findById(Object id, Class<T> aggregateType) {
        return template.findById(id, aggregateType);
    }
}
~~~

Code gọi có thể chọn kiểu một cách tường minh:

~~~java
Optional<PurchaseOrder> order =
    aggregateReader.findById(1001L, PurchaseOrder.class);
~~~

Đây là cách dùng hữu ích khi xây dựng adapter hoặc thành phần persistence dùng chung. Tuy nhiên, không nên biến mọi application service thành generic chỉ để tránh khai báo repository. Kiểu aggregate cụ thể thường giúp code nghiệp vụ an toàn và dễ đọc hơn.

Nếu kiểu aggregate đến từ input bên ngoài, không truyền trực tiếp tên class tùy ý để tải dữ liệu. Hãy ánh xạ một loại nghiệp vụ đã được whitelist sang class được phép.

### 4.4. Tích hợp vào custom repository fragment

Một repository có thể cần một số method đặc biệt ngoài CRUD và derived query. Có thể tạo repository fragment, rồi dùng JdbcAggregateTemplate bên trong implementation:

~~~java
public interface PurchaseOrderOperations {
    PurchaseOrder insertImported(PurchaseOrder order);
}
~~~

~~~java
public class PurchaseOrderOperationsImpl
        implements PurchaseOrderOperations {

    private final JdbcAggregateTemplate template;

    public PurchaseOrderOperationsImpl(JdbcAggregateTemplate template) {
        this.template = template;
    }

    @Override
    public PurchaseOrder insertImported(PurchaseOrder order) {
        return template.insert(order);
    }
}
~~~

Repository kết hợp fragment:

~~~java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long>,
                PurchaseOrderOperations {
}
~~~

Đây là một cách giữ API nghiệp vụ ở repository trong khi implementation dùng template cho thao tác persistence đặc biệt. Quy ước đặt tên fragment implementation và cách composition cần theo phiên bản Spring Data đang dùng.

### 4.5. Cần một API aggregate trong adapter hạ tầng

Một adapter có thể nhận một aggregate đã được tạo bởi domain/application layer rồi lưu nó mà không cần phụ thuộc vào interface repository cụ thể. Template cung cấp các thao tác aggregate ở dạng API trực tiếp.

Tuy nhiên, cần cân nhắc dependency direction: domain thuần không nên phụ thuộc Spring Data JDBC. Thông thường template được inject vào adapter hoặc infrastructure service, còn application service gọi qua một port nếu kiến trúc dự án sử dụng ports-and-adapters.

## 5. Ví dụ CRUD với JdbcAggregateTemplate

Ví dụ dưới đây dùng PurchaseOrder làm aggregate root, có ID kiểu Long.

### 5.1. Inject template

~~~java
import org.springframework.data.jdbc.core.JdbcAggregateTemplate;
import org.springframework.stereotype.Service;

@Service
public class PurchaseOrderPersistenceService {

    private final JdbcAggregateTemplate template;

    public PurchaseOrderPersistenceService(JdbcAggregateTemplate template) {
        this.template = template;
    }
}
~~~

Trong cấu hình Spring Data JDBC thông thường, template được cung cấp bởi infrastructure. Nếu ứng dụng tự cấu hình JDBC thủ công, cần bảo đảm mapping context, converter, dialect và data access strategy được cấu hình nhất quán.

### 5.2. Insert aggregate mới

~~~java
@Transactional
public PurchaseOrder create(PurchaseOrder draft) {
    return template.insert(draft);
}
~~~

insert biểu đạt rõ rằng use case muốn tạo hàng mới. Nếu database tự sinh ID, hãy dùng đối tượng được trả về để lấy định danh đã được framework điền vào. Với kiểu object bất biến, không giả định instance đầu vào được thay đổi tại chỗ.

Nếu ID đã được ứng dụng cấp, thao tác insert vẫn là insert. Primary key hoặc unique constraint trong database bảo vệ tính duy nhất.

### 5.3. Update aggregate đã tồn tại

~~~java
@Transactional
public PurchaseOrder update(PurchaseOrder changed) {
    return template.update(changed);
}
~~~

Chỉ gọi update khi use case biết aggregate đã tồn tại. Nếu không có hàng phù hợp, thao tác update không biến thành insert tự động. Khi aggregate dùng @Version, version vẫn tham gia cơ chế optimistic locking của Spring Data JDBC; cần truyền aggregate với version hợp lệ.

### 5.4. Dùng save khi trạng thái mới/cũ chưa được quyết định tường minh

~~~java
@Transactional
public PurchaseOrder save(PurchaseOrder order) {
    return template.save(order);
}
~~~

save sử dụng chiến lược nhận diện entity mới của Spring Data JDBC. Vì vậy, nó có semantics gần với thao tác save của repository: framework dựa vào metadata như @Id, @Version hoặc Persistable.isNew() để chọn insert/update.

Không hiểu save là câu lệnh SQL upsert nguyên tử. Nếu nhiều request cùng tạo một ID, hoặc dữ liệu thay đổi đồng thời, database constraint và optimistic locking vẫn cần được xử lý.

### 5.5. Tìm aggregate theo ID

~~~java
@Transactional(readOnly = true)
public PurchaseOrder get(long id) {
    return template.findById(id, PurchaseOrder.class)
        .orElseThrow(() ->
            new NoSuchElementException("Không tìm thấy đơn hàng"));
}
~~~

Kiểu PurchaseOrder.class cho template biết metadata aggregate cần dùng. Kết quả thường được biểu diễn bằng Optional<T> để code gọi xử lý trường hợp không tồn tại.

### 5.6. Kiểm tra tồn tại và đếm

~~~java
boolean exists = template.existsById(id, PurchaseOrder.class);

long count = template.count(PurchaseOrder.class);
~~~

Các thao tác này hữu ích cho kiểm tra kỹ thuật hoặc tác vụ quản trị. Nếu cần điều kiện phức tạp như đếm đơn theo trạng thái, theo tenant hoặc theo khoảng thời gian, hãy dùng repository query, @Query hoặc SQL đọc chuyên biệt.

### 5.7. Xóa aggregate

~~~java
@Transactional
public void delete(long id) {
    template.deleteById(id, PurchaseOrder.class);
}
~~~

Hoặc khi đã có aggregate:

~~~java
@Transactional
public void delete(PurchaseOrder order) {
    template.delete(order);
}
~~~

Thao tác vẫn áp dụng cho aggregate root. Nếu root sở hữu các entity con qua @MappedCollection, framework xử lý các thành phần thuộc aggregate theo mapping. Một aggregate khác chỉ có foreign key tham chiếu đến đơn hàng không mặc nhiên bị xóa cùng.

## 6. JdbcAggregateTemplate và repository khác nhau thế nào?

Hai API không phải hai cơ chế persistence độc lập. Cả hai đều thuộc Spring Data JDBC và dựa trên mapping aggregate. Khác biệt chính là mức abstraction và cách biểu đạt thao tác.

| Tiêu chí | Repository | JdbcAggregateTemplate |
|---|---|---|
| Cách khai báo | Interface theo aggregate root | Inject template vào class |
| Kiểu aggregate | Được cố định trong generic repository | Truyền kiểu qua tham số Class<T> ở nhiều thao tác |
| CRUD thông thường | Rất thuận tiện | Có các thao tác aggregate tương ứng |
| Derived query | Có | Không cung cấp cơ chế khai báo method query theo tên |
| Custom operation | Repository method/fragment | Gọi trực tiếp từ service/adapter hoặc fragment |
| Insert/update tường minh | Thường dùng save từ CRUD repository | Có insert và update riêng |
| Tổ chức code | Hợp đồng persistence theo domain | API thao tác aggregate dạng lập trình |
| Phù hợp | Use case thông thường theo từng aggregate | Luồng generic, explicit persistence operation, infrastructure |

Chọn template không tự động làm thao tác nhanh hơn. Nó cũng không biến các thao tác aggregate thành bulk SQL. Lý do chọn nên là cách tổ chức API hoặc nhu cầu thao tác tường minh, không phải giả định về hiệu năng.

## 7. Phân biệt JdbcAggregateTemplate với JdbcTemplate

Tên hai class khá giống nhau nhưng mục đích khác nhau:

| | JdbcAggregateTemplate | JdbcTemplate |
|---|---|---|
| Abstraction | Aggregate của Spring Data JDBC | SQL/JDBC trực tiếp |
| Đầu vào | Aggregate object, ID và domain type | SQL, tham số và RowMapper |
| Mapping | Metadata aggregate và Spring Data converters | Ứng dụng chỉ định mapping hàng |
| Quan hệ con | Xử lý theo aggregate mapping | Ứng dụng tự viết SQL cho các bảng |
| JOIN và window function | Không phải mục tiêu chính | Phù hợp |
| DTO báo cáo | Không phải mục tiêu chính | Phù hợp |
| Thay đổi dữ liệu | Insert/update/delete aggregate | SQL tùy chỉnh, kể cả bulk statement |

Ví dụ JdbcTemplate:

~~~java
List<OrderSummary> summaries = jdbcTemplate.query(
    """
    SELECT
        o.id,
        o.order_number,
        COUNT(l.id) AS line_count
    FROM purchase_orders o
    LEFT JOIN order_lines l ON l.order_id = o.id
    GROUP BY o.id, o.order_number
    """,
    (rs, rowNum) -> new OrderSummary(
        rs.getLong("id"),
        rs.getString("order_number"),
        rs.getLong("line_count")
    )
);
~~~

Đây là truy vấn read model. JdbcTemplate thích hợp vì kết quả là DTO tổng hợp từ nhiều bảng, không phải một aggregate cần lưu qua mapping root.

Đừng chọn JdbcAggregateTemplate chỉ vì tên có chữ JDBC nếu mục tiêu thực sự là chạy JOIN, CTE, window function hoặc SQL bulk. Hãy chọn API theo loại kết quả và trách nhiệm cần thực hiện.

## 8. Template có thay thế domain behavior không?

Không. JdbcAggregateTemplate là API persistence. Nó không biết quy tắc như:

- Đơn đã gửi có được sửa dòng hàng không?
- Một đơn có thể được xác nhận khi chưa có dòng hàng không?
- Trạng thái nào cho phép hủy?
- Tổng tiền phải được tính hoặc kiểm tra theo quy tắc nào?

Những quy tắc này phải nằm trong aggregate hoặc domain/application service.

Ví dụ, không nên nhận một object tùy ý rồi gọi template.update(order) trước khi kiểm tra trạng thái. Hãy dùng domain method:

~~~java
@Transactional
public PurchaseOrder submit(long id) {
    PurchaseOrder order = template.findById(id, PurchaseOrder.class)
        .orElseThrow();

    order.submit(); // Domain kiểm tra invariant.

    return template.update(order);
}
~~~

Ở đây template thực hiện persistence, còn submit() quyết định thay đổi có hợp lệ hay không. Nếu ứng dụng cần phân biệt tạo mới và cập nhật, use case nên chọn insert/update có chủ đích.

## 9. Transaction và nhiều thao tác aggregate

Một use case có thể cần đọc aggregate, kiểm tra quy tắc, cập nhật aggregate khác hoặc ghi audit. Đặt ranh giới transaction ở application service khi các thao tác database cần thành công hoặc rollback cùng nhau:

~~~java
@Service
public class OrderWorkflowService {

    private final JdbcAggregateTemplate template;
    private final OrderAuditRepository audit;

    public OrderWorkflowService(
            JdbcAggregateTemplate template,
            OrderAuditRepository audit) {
        this.template = template;
        this.audit = audit;
    }

    @Transactional
    public PurchaseOrder confirm(long id) {
        PurchaseOrder order = template.findById(
            id, PurchaseOrder.class
        ).orElseThrow();

        order.confirm();
        PurchaseOrder saved = template.update(order);

        audit.save(OrderAudit.confirmed(saved.getId()));
        return saved;
    }
}
~~~

Ví dụ minh họa việc template và repository cùng tham gia một use case. Để cùng transaction, các thành phần phải dùng cùng transaction manager và cùng DataSource phù hợp. Không giả định hai database hoặc hai transaction manager khác nhau tự động commit/rollback cùng nhau.

Nếu thao tác có gọi dịch vụ ngoài, tránh giữ transaction database mở trong thời gian chờ network dài. Có thể cần outbox hoặc quy trình bất đồng bộ tùy yêu cầu nhất quán.

## 10. Những điều cần lưu ý khi chọn template

### 10.1. Đừng dùng template để né thiết kế repository

Nếu một aggregate có nhiều query nghiệp vụ như findByStatus, findByOrderNumber, findByCustomerId, repository interface giúp biểu đạt rõ hợp đồng đọc. Dùng template cho tất cả các thao tác rồi viết lại truy vấn thủ công sẽ làm mất lợi ích của repository abstraction.

### 10.2. Đừng thao tác trực tiếp entity con như aggregate độc lập

Nếu OrderLine thuộc PurchaseOrder, hãy tải và thay đổi nó qua root. JdbcAggregateTemplate không phải lý do để biến entity con thành một đơn vị persistence độc lập, bỏ qua ownership và invariant của aggregate.

### 10.3. Cẩn thận với insert, update và save

Ba method thể hiện ba ý định khác nhau:

- insert: chắc chắn đang tạo mới.
- update: chắc chắn đang cập nhật.
- save: để chiến lược nhận diện mới/cũ chọn nhánh.

Không chọn method dựa trên việc object có ID hay chưa một cách máy móc. ID do ứng dụng tự cấp có thể có giá trị trước lần insert đầu tiên. Nếu dùng save, hãy hiểu @Version hoặc Persistable.isNew() ảnh hưởng đến quyết định như thế nào.

### 10.4. Không mặc định template là bulk API

Gọi insert hoặc update cho từng aggregate vẫn là thao tác theo aggregate. Nếu cần nhập hàng trăm nghìn hàng với tốc độ cao, hãy đo chi phí, thiết kế batch và cân nhắc cơ chế bulk phù hợp. SQL bulk trực tiếp cần tự xử lý foreign key, mapping, audit và invariant mà repository/template thường giúp điều phối.

### 10.5. Kiểm tra API theo phiên bản

Chữ ký method, overload và cách cấu hình template có thể thay đổi theo phiên bản Spring Data JDBC. Hãy dùng dependency version của dự án để tra Javadoc và viết integration test với database mục tiêu. Không sao chép một ví dụ từ phiên bản khác mà chưa kiểm tra package, bean và kiểu trả về.

## 11. Bảng quyết định: nên dùng API nào?

| Tình huống | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| CRUD thông thường cho PurchaseOrder | PurchaseOrderRepository | Hợp đồng theo aggregate, CRUD sẵn có |
| Tìm đơn theo trạng thái hoặc mã | Repository derived query | Tên method diễn đạt điều kiện |
| Luồng import biết chắc aggregate mới | JdbcAggregateTemplate.insert | Ý định INSERT tường minh |
| Luồng cập nhật biết chắc aggregate đã tồn tại | JdbcAggregateTemplate.update hoặc repository save sau khi tải root | Chọn thao tác theo trạng thái đã biết |
| Thành phần generic cần domain type tại runtime | JdbcAggregateTemplate | Có thể truyền Class<T> |
| Repository có một thao tác đặc biệt cần template | Custom repository fragment | Giữ API repository, dùng template ở implementation |
| Báo cáo JOIN nhiều bảng | JdbcTemplate/NamedParameterJdbcTemplate | SQL và DTO tùy chỉnh |
| Projection theo một số property | Repository projection hoặc query chuyên biệt | Chỉ trả góc nhìn dữ liệu cần thiết |
| Bulk SQL theo điều kiện phức tạp | Spring JDBC hoặc SQL chuyên biệt | Cần kiểm soát câu SQL và batch |

## 12. Bài tập thực hành

### Bài 1 — Thực hiện CRUD bằng template

1. Tạo PurchaseOrder aggregate có @Id và collection OrderLine.
2. Inject JdbcAggregateTemplate.
3. Tạo đơn mới bằng insert.
4. Đọc lại bằng findById(id, PurchaseOrder.class).
5. Thay đổi trạng thái qua domain method và lưu bằng update.
6. Xóa aggregate bằng deleteById.

Quan sát dữ liệu ở cả bảng root và bảng con để hiểu template vẫn sử dụng aggregate mapping.

### Bài 2 — So sánh save với insert

1. Tạo aggregate có UUID hoặc ID được cấp trước.
2. Thử save với cấu hình nhận diện mới/cũ phù hợp.
3. Thử insert cho một aggregate mới.
4. Thử insert trùng ID và quan sát constraint.
5. Giải thích vì sao ID khác null không tự chứng minh hàng đã tồn tại.

### Bài 3 — Kết hợp repository và template

1. Dùng repository để tìm đơn theo orderNumber.
2. Dùng template để thực hiện một thao tác insert tường minh trong import service.
3. Đặt cả hai trong một application service.
4. Xác nhận chúng dùng cùng mapping và transaction manager.

### Bài 4 — Phân biệt ba API

Viết cùng một báo cáo danh sách đơn theo ba cách: repository trả aggregate, projection trả các property của root và JdbcTemplate JOIN bảng khách hàng. Ghi nhận dữ liệu trả về, số cột và mục đích của mỗi cách.

## 13. Kết luận

**Dùng repository cho phần lớn CRUD theo aggregate** vì nó cung cấp abstraction theo kiểu domain, CRUD sẵn có và derived query dễ đọc. **Dùng JdbcAggregateTemplate khi cần thao tác aggregate theo cách lập trình**, đặc biệt khi muốn gọi insert/update tường minh, làm việc với kiểu aggregate được truyền vào tại runtime hoặc tích hợp một thao tác persistence đặc biệt trong infrastructure/custom repository fragment.

JdbcAggregateTemplate vẫn tuân theo mô hình mapping aggregate của Spring Data JDBC. Nó không phải công cụ chạy SQL tùy ý, không tự thay thế quy tắc domain và không phải bulk API. Khi cần JOIN, tổng hợp hoặc DTO báo cáo, dùng JdbcTemplate/NamedParameterJdbcTemplate hoặc projection phù hợp.

Hãy chọn API theo ý định: repository cho hợp đồng CRUD theo aggregate, template cho thao tác aggregate tường minh và linh hoạt, SQL JDBC trực tiếp cho truy vấn hoặc cập nhật tùy chỉnh. Dù dùng cách nào, aggregate root vẫn là nơi bảo vệ invariant của domain.
