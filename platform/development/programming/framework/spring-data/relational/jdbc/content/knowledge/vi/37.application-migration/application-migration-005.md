# Thay dirty checking, flush và entity manager bằng thao tác ghi tường minh

Khi chuyển một ứng dụng từ JPA/Hibernate sang **Spring Data Relational JDBC**, thay đổi quan trọng nhất nằm ở cách ứng dụng quản lý trạng thái entity. Với JPA, entity được nạp vào persistence context có thể trở thành managed entity. Hibernate theo dõi thay đổi của object, thực hiện dirty checking và đồng bộ các thay đổi đó xuống database khi flush. Với Spring Data JDBC, không có persistence context theo cách đó: entity là object Java thông thường, và thay đổi trong bộ nhớ chỉ được lưu khi ứng dụng gọi thao tác ghi một cách tường minh.

Vì vậy, code chuyển đổi cần thay các giả định sau:

- Thay dirty checking bằng lời gọi `repository.save(...)`, `JdbcAggregateTemplate.update(...)` hoặc câu lệnh update cụ thể.
- Thay `EntityManager.flush()` bằng thao tác ghi được thực thi ngay trong transaction; transaction vẫn chỉ commit khi hoàn tất.
- Thay `EntityManager` bằng repository, `JdbcAggregateTemplate`, `JdbcTemplate` hoặc `NamedParameterJdbcTemplate` tùy mục tiêu.
- Thay việc dựa vào managed entity và identity map bằng cách truyền rõ aggregate cần lưu và tải lại khi cần trạng thái mới.

Bài học giải thích sự khác biệt về lifecycle, cách chuyển từng thao tác JPA, cách tổ chức transaction và cập nhật một phần dữ liệu, cùng những điểm cần chú ý khi aggregate có child, generated ID hoặc optimistic locking.

## 1. Hai mô hình persistence khác nhau

### 1.1. JPA: persistence context theo dõi entity

Trong JPA, một `EntityManager` quản lý persistence context. Khi gọi `find`, entity được nạp vào context và thường trở thành managed entity. Nếu thay đổi thuộc tính của entity, Hibernate có thể phát hiện thay đổi mà không cần gọi `save`:

~~~java
@Transactional
public void renameCustomer(Long id, String newName) {
    Customer customer = entityManager.find(Customer.class, id);
    customer.setName(newName);
    // Hibernate phát hiện thay đổi khi flush.
}
~~~

Dirty checking so sánh trạng thái hiện tại với snapshot mà persistence provider quản lý. Khi flush, Hibernate phát sinh INSERT/UPDATE/DELETE cần thiết để đồng bộ persistence context với database.

### 1.2. Spring Data JDBC: thao tác ghi tường minh

Spring Data JDBC không duy trì persistence context chứa managed entities. Repository trả về object được materialize từ database. Thay đổi object đó không tự tạo câu SQL:

~~~java
@Transactional
public void renameCustomer(Long id, String newName) {
    Customer customer = customers.findById(id)
            .orElseThrow();

    customer.setName(newName);
    // Chưa có SQL UPDATE chỉ vì setter đã được gọi.

    customers.save(customer);
    // Thao tác ghi được thực hiện tường minh.
}
~~~

Đây là thay đổi về trách nhiệm: service hoặc application use case phải quyết định lúc nào ghi aggregate. Không thể chuyển nguyên code JPA có setter rồi trông chờ dirty checking tự lưu.

### 1.3. So sánh nhanh

| JPA/Hibernate | Spring Data JDBC |
| --- | --- |
| `EntityManager` quản lý persistence context | Repository/template thực hiện thao tác trực tiếp |
| Managed entity được theo dõi | Entity là object thông thường |
| Dirty checking phát hiện thay đổi | Gọi thao tác ghi tường minh |
| `flush()` đồng bộ persistence context | SQL được thực thi khi thao tác ghi chạy |
| `clear()` detach tất cả entity trong context | Không có persistence context để clear |
| `refresh()` nạp lại trạng thái managed entity | Query lại để lấy snapshot mới |
| `persist()`/`merge()` theo lifecycle JPA | `save()` hoặc `JdbcAggregateTemplate.insert/update` |
| Lazy loading/proxy theo mapping JPA | Aggregate được tải theo mô hình Spring Data JDBC, không dựa vào lazy proxy |
| Cascade theo JPA mapping | Persistence theo aggregate boundary và mapping Spring Data Relational |

Không nên xem `repository.save` như một bản đổi tên trực tiếp của `EntityManager.merge`. Hai mô hình có semantics khác nhau, đặc biệt với aggregate và collection child.

## 2. Thay dirty checking bằng save tường minh

Giả sử code JPA cũ:

~~~java
@Transactional
public void changeAddress(Long customerId, Address newAddress) {
    Customer customer = entityManager.find(Customer.class, customerId);
    customer.setAddress(newAddress);
    // Không gọi merge/save.
}
~~~

Trong Spring Data JDBC, viết:

~~~java
@Transactional
public void changeAddress(Long customerId, Address newAddress) {
    Customer customer = customers.findById(customerId)
            .orElseThrow(() -> new CustomerNotFoundException(customerId));

    customer.setAddress(newAddress);
    customers.save(customer);
}
~~~

Lời gọi `save` là ranh giới rõ ràng nơi ứng dụng yêu cầu persistence layer lưu aggregate. Nếu entity bất biến, service tạo phiên bản mới:

~~~java
@Transactional
public void changeAddress(Long customerId, Address newAddress) {
    Customer current = customers.findById(customerId)
            .orElseThrow(() -> new CustomerNotFoundException(customerId));

    Customer changed = current.withAddress(newAddress);
    customers.save(changed);
}
~~~

Trong cả hai trường hợp, cần dùng object trả về từ `save` khi persistence có thể gán ID hoặc version mới. Với object bất biến, repository có thể trả về một instance chứa các giá trị được sinh hoặc cập nhật.

### 2.1. Không gọi save cho mọi setter

Spring Data JDBC không yêu cầu gọi `save` ngay sau từng setter. Hãy hoàn thành thay đổi của một use case rồi lưu aggregate một lần:

~~~java
@Transactional
public void confirmOrder(Long id) {
    PurchaseOrder order = orders.findById(id).orElseThrow();

    order.confirm();
    order.recordConfirmationTime(clock.instant());
    order.addDomainNote("Confirmed by customer");

    orders.save(order);
}
~~~

Các thay đổi trong bộ nhớ được gom thành trạng thái aggregate cuối cùng trước khi persistence operation chạy. Đây là cách tổ chức logic use case, không phải dirty checking.

### 2.2. Tránh quên save

Một lỗi chuyển đổi phổ biến là giữ nguyên code sửa entity nhưng bỏ mất thao tác ghi:

~~~java
@Transactional
public void deactivateCustomer(Long id) {
    Customer customer = customers.findById(id).orElseThrow();
    customer.deactivate();
    // Thiếu customers.save(customer).
}
~~~

Method vẫn chạy thành công nhưng database không đổi. Test cần đọc lại từ repository sau khi transaction kết thúc hoặc xác nhận câu SQL đã được thực thi để phát hiện lỗi này.

## 3. Thay persist và merge bằng repository.save

JPA phân biệt `persist` cho entity mới và `merge` cho trạng thái cần đồng bộ. Spring Data JDBC thường cung cấp một API `save` cho cả trường hợp mới và đã tồn tại:

~~~java
PurchaseOrder saved = orders.save(order);
~~~

Spring Data JDBC quyết định insert hay update theo cơ chế xác định entity mới (newness strategy). Cơ chế này có thể dựa trên ID, `@Version` hoặc `Persistable.isNew()` tùy entity và cấu hình.

### 3.1. Entity có ID do database sinh

Với ID tự sinh và chưa được gán, entity mới thường có ID null:

~~~java
PurchaseOrder order = new PurchaseOrder(
        null,
        "PO-1001",
        OrderStatus.NEW
);

PurchaseOrder saved = orders.save(order);
Long generatedId = saved.getId();
~~~

Không tiếp tục dùng `order.getId()` nếu object ban đầu bất biến hoặc repository trả về instance khác. Dùng `saved` làm trạng thái đã được lưu.

### 3.2. Entity có ID được ứng dụng gán

Nếu ID luôn được gán trước khi lưu, chiến lược mặc định dựa vào ID có thể không đủ để phân biệt entity mới với entity đã tồn tại. Có thể triển khai `Persistable<ID>` để cung cấp `isNew()`, hoặc dùng `@Version` theo mô hình phù hợp.

Ví dụ khung:

~~~java
@Table("external_customer")
public class ExternalCustomer implements Persistable<String> {

    @Id
    private String id;

    @Transient
    private boolean newEntity = true;

    @Override
    public String getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return newEntity;
    }

    public void markNotNew() {
        this.newEntity = false;
    }
}
~~~

Ví dụ cần hoàn thiện lifecycle của cờ `newEntity` theo cách entity được tạo và tải lại; không để một entity đã được lưu tiếp tục báo `isNew() == true`. Một cách thường dùng là callback sau khi load/insert hoặc factory riêng bảo đảm trạng thái đúng.

### 3.3. Khi muốn chỉ insert hoặc chỉ update

Nếu use case cần semantics cụ thể, `JdbcAggregateTemplate` có các thao tác tường minh:

~~~java
template.insert(newOrder);
template.update(existingOrder);
~~~

`insert` phù hợp với aggregate chắc chắn mới; `update` phù hợp với aggregate chắc chắn đã tồn tại. Dùng đúng thao tác giúp phát hiện trạng thái sai sớm hơn so với một `save` phải tự quyết định.

Repository `save` vẫn là lựa chọn thông thường khi ứng dụng muốn Spring Data JDBC xác định insert/update theo newness strategy.

## 4. Thay EntityManager bằng repository và template

Không phải mọi thao tác JPA đều nên chuyển thành `repository.save`. Chọn abstraction theo mục tiêu.

| Thao tác JPA cũ | Spring Data JDBC tương ứng |
| --- | --- |
| `entityManager.find(Type.class, id)` | `repository.findById(id)` |
| `entityManager.persist(entity)` | `repository.save(entity)` hoặc `JdbcAggregateTemplate.insert(entity)` |
| `entityManager.merge(entity)` | `repository.save(entity)` hoặc `JdbcAggregateTemplate.update(entity)` khi chắc chắn entity đã tồn tại |
| `entityManager.remove(entity)` | `repository.delete(entity)` hoặc `deleteById(id)` |
| `entityManager.flush()` | Thực hiện thao tác ghi; transaction commit ở ranh giới transaction |
| `entityManager.clear()` | Không có thao tác tương đương cần thiết; không có persistence context |
| `entityManager.refresh(entity)` | Query lại entity/aggregate để lấy snapshot mới |
| JPQL bulk update | `@Modifying @Query`, `JdbcTemplate` hoặc `NamedParameterJdbcTemplate` |
| `EntityManager.createNativeQuery(...)` | Repository `@Query` hoặc JDBC template |

### 4.1. Repository cho thao tác aggregate

~~~java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

Service:

~~~java
@Service
public class PurchaseOrderService {

    private final PurchaseOrderRepository orders;

    public PurchaseOrderService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public PurchaseOrder addLine(Long orderId, OrderLine line) {
        PurchaseOrder order = orders.findById(orderId)
                .orElseThrow();

        order.addLine(line);
        return orders.save(order);
    }
}
~~~

### 4.2. JdbcAggregateTemplate cho persistence tường minh

`JdbcAggregateTemplate` là abstraction cấp aggregate của Spring Data JDBC. Có thể dùng khi cần thao tác insert/update/delete/find mà không muốn khai báo repository interface riêng:

~~~java
@Service
public class PurchaseOrderWriter {

    private final JdbcAggregateTemplate template;

    public PurchaseOrderWriter(JdbcAggregateTemplate template) {
        this.template = template;
    }

    @Transactional
    public PurchaseOrder create(PurchaseOrder order) {
        return template.insert(order);
    }

    @Transactional
    public PurchaseOrder revise(PurchaseOrder order) {
        return template.update(order);
    }
}
~~~

Chọn repository khi muốn API theo domain repository và query methods. Chọn template khi cần điều khiển trực tiếp thao tác aggregate trong một service hoặc custom persistence component.

### 4.3. JdbcTemplate cho thao tác SQL trực tiếp

Khi cần cập nhật một cột hoặc chạy bulk statement, `JdbcTemplate` hay `NamedParameterJdbcTemplate` thường phù hợp hơn việc tải và lưu toàn aggregate:

~~~java
int changed = jdbcTemplate.update(
        "UPDATE customer SET status = ? WHERE id = ?",
        "INACTIVE",
        customerId
);
~~~

Với named parameters:

~~~java
int changed = namedParameterJdbcTemplate.update(
        """
        UPDATE customer
        SET status = :status
        WHERE id = :id
        """,
        Map.of("status", "INACTIVE", "id", customerId)
);
~~~

Thao tác trực tiếp nên nằm trong persistence adapter hoặc repository fragment, để service vẫn gọi một API có ý nghĩa nghiệp vụ.

## 5. Thay flush bằng thao tác ghi và transaction

### 5.1. Flush trong JPA làm gì?

Trong JPA, `flush()` yêu cầu persistence provider đồng bộ thay đổi của persistence context xuống database. Nó không đồng nghĩa với commit. Transaction có thể tiếp tục chạy và sau đó rollback.

Ví dụ:

~~~java
entityManager.persist(order);
entityManager.flush(); // SQL được gửi tới database
// Transaction vẫn chưa nhất thiết commit.
~~~

### 5.2. Spring Data JDBC không có persistence context cần flush

Với Spring Data JDBC, lời gọi ghi như:

~~~java
orders.save(order);
~~~

thực thi các câu SQL tương ứng trong quá trình gọi persistence operation. Không cần một lệnh `flush()` riêng để yêu cầu đồng bộ dirty entities.

Tuy nhiên, nếu lời gọi nằm trong transaction đang mở, việc SQL đã thực thi không có nghĩa dữ liệu đã commit. Transaction manager vẫn quyết định commit hoặc rollback ở cuối transaction.

~~~text
BEGIN TRANSACTION
    |
    +-- repository.save(order)
    |       |
    |       +-- INSERT/UPDATE/DELETE được thực thi
    |
    +-- các thao tác JDBC khác
    |
COMMIT hoặc ROLLBACK
~~~

Nếu không có transaction bên ngoài, repository operation có thể chạy trong transaction do repository quản lý và commit khi method kết thúc, tùy cấu hình transaction.

### 5.3. Thay đổi thứ tự khi code phụ thuộc vào flush

Một số code JPA gọi `flush()` giữa use case để buộc constraint được kiểm tra sớm hoặc để query sau đó nhìn thấy SQL đã đồng bộ.

Trong Spring Data JDBC:

- Gọi `save` tại vị trí cần SQL được thực thi.
- Nếu cần đọc dữ liệu vừa ghi trong cùng transaction, thực hiện query sau thao tác ghi; transaction đó nhìn thấy write của chính nó theo isolation/database semantics.
- Nếu cần kiểm tra constraint, để database thực thi thao tác ghi và xử lý exception phù hợp.
- Nếu constraint được trì hoãn đến commit bởi database, thao tác save chưa chắc phát hiện lỗi; commit vẫn có thể thất bại.

Không thêm `save` chỉ để mô phỏng `flush` nếu chưa có thay đổi aggregate cần lưu. Xác định chính xác lý do code cũ flush và thay bằng thao tác phù hợp.

### 5.4. Không có saveAndFlush

Spring Data JDBC không dùng mô hình `saveAndFlush` như một số Spring Data JPA repository. `save` đã thực hiện thao tác ghi. Ranh giới commit vẫn do transaction quyết định.

## 6. Thay clear và refresh

### 6.1. Không có persistence context để clear

JPA có `EntityManager.clear()` để detach mọi entity đang managed. Spring Data JDBC không theo dõi managed entities nên không có trạng thái tương ứng cần xóa.

Mỗi lần đọc repository là một thao tác đọc database và materialize object. Nếu cùng ID được đọc hai lần, không có bảo đảm hai lời gọi trả cùng một Java object reference.

### 6.2. Đọc lại khi cần trạng thái mới

Nếu cần trạng thái mới từ database:

~~~java
Customer reloaded = customers.findById(customerId)
        .orElseThrow();
~~~

Trong cùng transaction, query vẫn tuân theo isolation level của database. Đọc lại không bảo đảm thấy commit của transaction khác nếu isolation không cho phép.

### 6.3. Tránh giữ object cũ sau bulk update

Nếu dùng `@Modifying` hoặc `JdbcTemplate.update` để cập nhật trực tiếp, object đã được tải trước đó không tự thay đổi. Hãy bỏ qua snapshot cũ và query lại khi cần dữ liệu mới.

Đây là khác biệt quan trọng với JPA, nơi bulk JPQL update có thể khiến managed entities trong persistence context trở nên stale và cần clear/refresh. Trong Spring Data JDBC, không có identity map tự đồng bộ các object đã tải.

## 7. Ghi toàn aggregate hay cập nhật một phần?

Đây là quyết định thiết kế quan trọng khi chuyển từ JPA.

### 7.1. save lưu trạng thái aggregate

Spring Data JDBC làm việc theo aggregate boundary. Khi gọi `save` trên aggregate root, persistence xử lý root cùng các entity được root tham chiếu theo mapping. Với aggregate có collection child, quá trình lưu có thể bao gồm xóa các child row hiện tại và insert lại các child trong trạng thái mới, thay vì so sánh từng child để chỉ update phần thay đổi như dirty checking của ORM.

Chi tiết SQL phụ thuộc mapping, loại entity và phiên bản Spring Data Relational. Vì vậy, không nên giả định `save` chỉ phát một câu UPDATE cho root hoặc chỉ cập nhật child đã đổi. Hãy thiết kế aggregate hợp lý và quan sát SQL trong integration test khi hiệu năng quan trọng.

### 7.2. Khi nào lưu toàn aggregate là phù hợp?

`save` phù hợp khi:

- Use case thay đổi trạng thái của aggregate root.
- Aggregate nhỏ và được tải đầy đủ.
- Các child thuộc cùng consistency boundary.
- Toàn bộ aggregate là đơn vị thay đổi và lưu.

Ví dụ:

~~~java
@Transactional
public void changeOrderStatus(Long id, OrderStatus status) {
    PurchaseOrder order = orders.findById(id).orElseThrow();
    order.changeStatus(status);
    orders.save(order);
}
~~~

### 7.3. Khi nào cần partial update?

Nếu bảng có hàng triệu bản ghi hoặc use case chỉ cần tăng một bộ đếm, không nhất thiết tải cả aggregate rồi save. Dùng câu lệnh update cụ thể:

~~~java
public interface InventoryRepository
        extends CrudRepository<Inventory, Long> {

    @Modifying
    @Query("""
        UPDATE inventory
        SET reserved_quantity = reserved_quantity + :amount
        WHERE product_id = :productId
        """)
    int reserve(
            @Param("productId") Long productId,
            @Param("amount") int amount
    );
}
~~~

Tên và import annotation phụ thuộc Spring Data JDBC version; trong repository query, `@Modifying` đánh dấu câu lệnh làm thay đổi dữ liệu. Kiểm tra số hàng bị ảnh hưởng để biết update có tìm thấy bản ghi hay không.

Đối với điều kiện phức tạp hoặc bulk update, dùng `NamedParameterJdbcTemplate` trong custom repository adapter.

### 7.4. Đừng trộn hai cách ghi thiếu kiểm soát

Nếu một use case vừa tải aggregate vừa dùng SQL trực tiếp để sửa cùng bảng, object trong bộ nhớ có thể không còn phản ánh trạng thái database. Hãy:

1. Xác định một nguồn dữ liệu có thẩm quyền cho use case.
2. Tránh save một aggregate stale sau khi đã chạy bulk update.
3. Query lại nếu cần đọc trạng thái đã thay đổi.
4. Dùng cùng transaction nếu các thao tác phải thành công/thất bại cùng nhau.

## 8. Thay đổi aggregate và child entities

Trong JPA, code có thể thay đổi một child managed và để dirty checking phát hiện. Trong Spring Data JDBC, child là một phần của aggregate được lưu qua root:

~~~java
@Transactional
public void changeLineQuantity(
        Long orderId,
        Long lineId,
        int quantity
) {
    PurchaseOrder order = orders.findById(orderId).orElseThrow();

    order.changeLineQuantity(lineId, quantity);
    orders.save(order);
}
~~~

Aggregate root kiểm soát invariant và thay đổi child. Repository lưu trạng thái aggregate theo mapping.

### 8.1. Không cập nhật child ngoài aggregate boundary tùy tiện

Nếu một bảng child được thay đổi độc lập bởi nhiều use case hoặc có lifecycle riêng, cần xem lại aggregate boundary. Spring Data JDBC giả định các entity được tham chiếu thuộc aggregate root và được persistence xử lý theo root.

Nếu cần cập nhật một child row riêng vì lý do hiệu năng, tạo một thao tác persistence tường minh có kiểm soát và xác định cách nó tương tác với invariant của root. Không để nhiều đường ghi cạnh tranh làm aggregate không còn nhất quán.

### 8.2. Collection thay đổi có thể tạo nhiều SQL

Thêm một phần tử vào collection không có nghĩa Spring Data JDBC chỉ INSERT một row nếu aggregate được save theo chiến lược thay thế collection. Đánh giá chi phí cho aggregate lớn:

- Số child rows phải xóa/insert.
- Foreign key và index.
- Trigger hoặc audit ở database.
- Lock và transaction duration.
- Số lượng SQL trong một lần save.

Nếu collection rất lớn hoặc có lifecycle độc lập, cân nhắc tách aggregate hoặc dùng repository/SQL riêng cho thao tác đó.

## 9. Transaction boundary thay cho EntityManager lifecycle

Transaction vẫn quan trọng trong Spring Data JDBC. Khác biệt là transaction bảo vệ các câu SQL thực thi, không bao quanh một persistence context chờ flush.

### 9.1. Đặt transaction ở application service

~~~java
@Service
public class OrderApplicationService {

    private final PurchaseOrderRepository orders;
    private final PaymentRepository payments;

    public OrderApplicationService(
            PurchaseOrderRepository orders,
            PaymentRepository payments
    ) {
        this.orders = orders;
        this.payments = payments;
    }

    @Transactional
    public void confirm(Long orderId) {
        PurchaseOrder order = orders.findById(orderId).orElseThrow();
        order.confirm();

        payments.recordConfirmation(orderId);
        orders.save(order);
    }
}
~~~

Nếu cả hai repository dùng cùng datasource và transaction manager, các thao tác database tham gia cùng transaction. Nếu một thao tác lỗi và exception làm transaction rollback, các thay đổi database trong transaction đó được rollback.

### 9.2. SQL chạy ngay nhưng commit vẫn ở cuối

Trong transaction, câu SQL được gửi tới database khi `save` được gọi. Những transaction khác thường chưa thấy thay đổi chưa commit; transaction hiện tại có thể đọc lại write của chính nó.

Không nhầm việc SQL đã chạy với dữ liệu đã bền vững. Commit mới là điểm transaction hoàn tất thành công.

### 9.3. Read-only transaction

Use case chỉ đọc có thể dùng:

~~~java
@Transactional(readOnly = true)
public PurchaseOrder getOrder(Long id) {
    return orders.findById(id).orElseThrow();
}
~~~

Không đặt thao tác ghi trong một transaction được đánh dấu read-only rồi kỳ vọng hành vi giống transaction ghi thông thường. Hãy dùng transaction phù hợp với công việc thực hiện.

### 9.4. Self-invocation và proxy

`@Transactional` của Spring thường được áp dụng qua proxy. Gọi một method transactional khác trên cùng instance (`this.someMethod()`) có thể không đi qua proxy, do đó transaction annotation ở method được gọi không được áp dụng như dự kiến.

Khi chuyển đổi service, giữ transaction boundary ở public application service method được gọi từ bên ngoài bean hoặc tách transaction collaborator thành bean riêng.

## 10. Optimistic locking thay cho kiểm soát trạng thái managed

Dirty checking không tự giải quyết xung đột ghi đồng thời. Spring Data JDBC hỗ trợ optimistic locking với `@Version`:

~~~java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    @Version
    private Long version;

    private OrderStatus status;
}
~~~

Khi lưu aggregate đã có version, Spring Data JDBC dùng version để phát hiện bản ghi đã bị thay đổi bởi transaction khác. Nếu version không còn khớp, thao tác có thể ném `OptimisticLockingFailureException`.

### 10.1. Xử lý conflict

~~~java
@Transactional
public void confirm(Long orderId) {
    PurchaseOrder order = orders.findById(orderId).orElseThrow();
    order.confirm();

    try {
        orders.save(order);
    } catch (OptimisticLockingFailureException ex) {
        throw new OrderWasModifiedConcurrentlyException(orderId, ex);
    }
}
~~~

Tùy nghiệp vụ, ứng dụng có thể trả conflict cho caller, tải lại aggregate và thử lại có giới hạn, hoặc yêu cầu người dùng giải quyết. Không tự động retry vô hạn vì thao tác có thể không còn hợp lệ trên trạng thái mới.

### 10.2. Partial update cần version predicate

Một câu `@Modifying` hoặc `JdbcTemplate.update` tự viết không tự động có cùng optimistic locking semantics với repository aggregate save. Nếu update trực tiếp trên bảng có version, hãy thêm điều kiện version và tăng version trong cùng câu SQL:

~~~sql
UPDATE purchase_order
SET status = :status,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion;
~~~

Nếu số hàng cập nhật bằng 0, bản ghi không tồn tại hoặc version đã thay đổi. Phân biệt hai trường hợp bằng query bổ sung nếu nghiệp vụ cần.

## 11. Auditing và entity callbacks

JPA ứng dụng có thể dựa vào lifecycle callbacks như `@PrePersist`, `@PreUpdate` hoặc listener để đặt audit fields. Khi chuyển sang Spring Data JDBC, cần chuyển logic sang cơ chế phù hợp của Spring Data Relational:

- Auditing annotations như `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy`, `@LastModifiedBy`.
- `AuditingEntityCallback` và auditing infrastructure.
- `BeforeConvertCallback`, `BeforeSaveCallback`, `AfterSaveCallback` hoặc callback phù hợp theo phiên bản.
- Logic nghiệp vụ được gọi tường minh trong application service/domain object.

Ví dụ entity:

~~~java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant updatedAt;
}
~~~

Auditing cần được bật và có `AuditorAware` nếu muốn ghi người thực hiện. Không giả định các annotation auditing hoạt động chỉ vì đã đặt lên field.

Các thao tác ghi trực tiếp qua `JdbcTemplate` không đi qua toàn bộ aggregate mapping/callback pipeline như repository save. Nếu partial SQL cần cập nhật audit fields, hãy đặt chúng trong SQL hoặc một persistence adapter có trách nhiệm rõ ràng.

## 12. Domain events và side effects

JPA code có thể dựa vào entity listener để phát event khi entity được persist/update. Khi chuyển sang Spring Data JDBC, hãy phân biệt:

- Logic nghiệp vụ của aggregate: gọi tường minh khi thực hiện hành động.
- Event của aggregate: lưu hoặc publish theo cơ chế Spring Data Relational phù hợp.
- Side effect sau commit: dùng transaction-bound event listener nếu cần chạy sau khi transaction thành công.

Ví dụ application service:

~~~java
@Transactional
public PurchaseOrder confirm(Long id) {
    PurchaseOrder order = orders.findById(id).orElseThrow();
    order.confirm();

    PurchaseOrder saved = orders.save(order);
    events.publishEvent(new OrderConfirmed(saved.getId()));
    return saved;
}
~~~

Nếu listener cần chạy sau commit, đăng ký bằng `@TransactionalEventListener(phase = AFTER_COMMIT)`. Nếu event không được phép mất khi process crash, lưu outbox row trong cùng transaction thay vì chỉ dựa vào callback trong bộ nhớ.

Không phát event hoặc gửi message trước commit nếu transaction rollback có thể làm event trở thành sai sự thật.

## 13. Những API JPA không có bản thay thế một-một

Một số API phản ánh persistence context và không có counterpart trực tiếp:

| JPA API/concept | Cách xử lý trong Spring Data JDBC |
| --- | --- |
| `EntityManager` | Inject repository, `JdbcAggregateTemplate` hoặc JDBC template |
| Managed entity | Không có; object được tải là snapshot |
| Dirty checking | Gọi save/update tường minh |
| `flush()` | SQL chạy trong thao tác ghi; commit do transaction quản lý |
| `clear()` | Không cần vì không có persistence context |
| `refresh()` | Query lại object |
| `detach()` | Không có trạng thái managed cần detach |
| `getReference()` | Query theo ID; không dựa vào lazy proxy |
| Lazy collection | Thiết kế aggregate và query riêng cho dữ liệu cần tải |
| JPQL bulk update | `@Modifying @Query` hoặc JDBC template |
| `merge()` graph | Lưu aggregate root theo mapping và semantics Spring Data JDBC |
| Cascade type | Aggregate boundary và quan hệ mapping Spring Data Relational |

Nếu một phần code phụ thuộc nặng vào `EntityManager` như một unit-of-work, đó là phần cần thiết kế lại thay vì thay từng method call bằng API có tên gần giống.

## 14. Ví dụ chuyển đổi use case hoàn chỉnh

### 14.1. Phiên bản JPA

~~~java
@Service
public class JpaOrderService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void addLine(Long orderId, OrderLine line) {
        PurchaseOrder order =
                entityManager.find(PurchaseOrder.class, orderId);

        order.addLine(line);

        entityManager.flush();
    }
}
~~~

Code dựa vào managed aggregate và flush để đồng bộ thay đổi.

### 14.2. Phiên bản Spring Data JDBC

~~~java
@Service
public class JdbcOrderService {

    private final PurchaseOrderRepository orders;

    public JdbcOrderService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public PurchaseOrder addLine(Long orderId, OrderLine line) {
        PurchaseOrder order = orders.findById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));

        order.addLine(line);

        return orders.save(order);
    }
}
~~~

Khác biệt:

1. Repository đọc aggregate.
2. Domain method thay đổi aggregate trong bộ nhớ.
3. `save` ghi aggregate một cách tường minh.
4. Transaction commit khi application service hoàn tất.

Không cần `flush` riêng. Nếu `save` thất bại, transaction có thể rollback và exception được truyền lên caller.

### 14.3. Partial update thay vì tải aggregate

Nếu use case chỉ cập nhật một trạng thái độc lập và không cần kiểm tra invariant của aggregate:

~~~java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    @Modifying
    @Query("""
        UPDATE customer
        SET status = :status
        WHERE id = :id
        """)
    int updateStatus(
            @Param("id") Long id,
            @Param("status") String status
    );
}
~~~

Service:

~~~java
@Transactional
public void setCustomerStatus(Long id, CustomerStatus status) {
    int changed = customers.updateStatus(id, status.name());

    if (changed == 0) {
        throw new CustomerNotFoundException(id);
    }
}
~~~

Đây là update một phần trực tiếp. Nó không tải aggregate, không chạy dirty checking và không tự áp dụng toàn bộ lifecycle của `save`. Nếu có version, auditing hoặc invariant cần duy trì, bổ sung chúng một cách tường minh.

## 15. Kiểm thử sau khi thay dirty checking và flush

Test cần chứng minh thay đổi chỉ được lưu khi có thao tác ghi, đồng thời kiểm tra transaction boundary.

### 15.1. Thay đổi trong bộ nhớ không tự lưu

1. Tạo entity và lưu.
2. Tải entity từ repository.
3. Thay đổi field nhưng không gọi save.
4. Kết thúc transaction.
5. Đọc lại bằng transaction mới.
6. Xác nhận database vẫn giữ giá trị cũ.

Test này làm rõ Spring Data JDBC không dirty-check entity.

### 15.2. Save ghi thay đổi

1. Tải aggregate.
2. Gọi domain method thay đổi.
3. Gọi repository save.
4. Đọc lại aggregate.
5. Xác nhận root và child state đúng.

### 15.3. SQL được thực thi trước commit

Trong một transaction:

1. Gọi save.
2. Query lại trong cùng transaction để xác nhận transaction thấy write của chính nó.
3. Rollback transaction.
4. Đọc từ transaction mới để xác nhận dữ liệu không được commit.

Điều này phân biệt thời điểm SQL thực thi với thời điểm transaction commit.

### 15.4. Kiểm thử optimistic locking

1. Đọc cùng aggregate ở hai transaction.
2. Transaction A cập nhật và commit.
3. Transaction B cố lưu snapshot cũ.
4. Xác nhận optimistic locking failure.

### 15.5. Kiểm thử partial update

Kiểm tra:

- Số hàng bị ảnh hưởng.
- Điều kiện WHERE không cập nhật nhầm nhiều hàng.
- Version được kiểm tra/tăng nếu có.
- Audit fields được cập nhật đúng.
- Object đã tải trước bulk update không được dùng như snapshot mới.

## 16. Lỗi thường gặp khi chuyển đổi

| Lỗi | Vì sao xảy ra | Cách xử lý |
| --- | --- | --- |
| Đổi setter nhưng quên save | Không có dirty checking | Gọi save/update tường minh |
| Gọi save sau từng field | Nhầm save là flush | Gom thay đổi của use case rồi lưu aggregate |
| Giữ `EntityManager.flush()` | Không còn persistence context | Xóa flush và đặt save ở vị trí cần ghi |
| Nghĩ save đồng nghĩa commit | SQL chạy trong transaction chưa commit | Dùng transaction boundary đúng |
| Coi save giống merge | Semantics aggregate khác JPA | Kiểm tra newness và aggregate write behavior |
| Dùng object cũ sau save | Generated ID/version có thể nằm trong object trả về | Dùng instance trả về từ save |
| Giữ entity reference như managed object | Không có identity map | Truyền ID và query lại khi cần |
| Dùng lazy-loading giả định | Spring Data JDBC không dựa vào lazy proxy | Tải aggregate hoặc query dữ liệu riêng |
| Save aggregate lớn chỉ để đổi một field | Có thể ghi lại nhiều child rows | Dùng partial update nếu phù hợp invariant |
| Bulk update rồi save snapshot cũ | Save có thể ghi đè trạng thái vừa cập nhật | Query lại hoặc chọn một đường ghi |
| Custom update bỏ qua @Version | Không kiểm tra concurrent update | Thêm version predicate và tăng version |
| SQL trực tiếp bỏ qua auditing | Không chạy aggregate callback pipeline | Cập nhật audit fields rõ ràng |
| Không kiểm thử transaction | Nhầm SQL execution với commit | Test cả visibility và rollback |

## 17. Quy trình refactor từ JPA sang Spring Data JDBC

Khi chuyển một service:

1. **Tìm mọi điểm dùng EntityManager:** find, persist, merge, remove, flush, clear, refresh và native query.
2. **Phân loại thao tác:** aggregate CRUD, query đọc, partial update hay bulk operation.
3. **Xác định aggregate boundary:** object nào là root và child nào được lưu cùng root.
4. **Thay read API:** dùng repository hoặc query adapter.
5. **Thay write API:** dùng save, insert, update, delete hoặc câu SQL tường minh.
6. **Bổ sung lời gọi ghi:** tìm mọi domain mutation trước đây dựa vào dirty checking.
7. **Bỏ flush/clear/refresh:** thay bằng SQL execution và query lại khi cần.
8. **Xem xét transaction:** đặt @Transactional ở use case và kiểm tra datasource/transaction manager.
9. **Xử lý concurrency:** chuyển optimistic locking và partial update đúng cách.
10. **Chuyển lifecycle logic:** auditing, callbacks và domain events.
11. **Kiểm thử:** save/no-save, root/child, generated ID, rollback, version conflict và bulk update.
12. **Đo SQL thực tế:** kiểm tra số câu lệnh và chi phí lưu aggregate lớn.

## Ghi nhớ

Spring Data JDBC không có persistence context và dirty checking như JPA. Entity được tải là object thông thường; thay đổi trong bộ nhớ không tự lưu. Hãy gọi `repository.save`, `JdbcAggregateTemplate.insert/update` hoặc câu lệnh update cụ thể tại ranh giới use case. `save` lưu aggregate theo mapping, vì vậy không giả định nó chỉ cập nhật field đã thay đổi hoặc chỉ ghi một child row.

Không cần `EntityManager.flush()` vì SQL được thực thi trong thao tác ghi. Transaction vẫn quyết định commit hay rollback; SQL đã chạy chưa có nghĩa dữ liệu đã commit. `clear`, `detach` và `refresh` cũng không có counterpart trực tiếp: không có managed state để xóa, và khi cần snapshot mới thì query lại.

Dùng repository/template cho aggregate, dùng `@Modifying @Query` hoặc JDBC template cho partial/bulk update khi phù hợp. Với partial update, chủ động bảo vệ optimistic locking, auditing và invariant vì đường SQL trực tiếp không tự chạy toàn bộ aggregate save lifecycle. Đặt transaction ở application service, dùng object trả về từ save khi có generated ID/version và kiểm thử cả trường hợp quên save, rollback, child persistence và concurrent update.

## Tài liệu tham khảo

- [Spring Data Relational — JDBC](https://docs.spring.io/spring-data/relational/reference/jdbc.html)
- [Spring Data Relational — Persisting Entities](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html)
- [Spring Data Relational — JDBC Aggregate Template](https://docs.spring.io/spring-data/relational/reference/jdbc/aggregate-template.html)
- [Spring Data Relational — Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html)
- [Spring Data Relational — Mapping and Optimistic Locking](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html)
