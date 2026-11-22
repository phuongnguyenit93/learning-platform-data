# Thứ tự học và mô hình nghiệp vụ xuyên suốt tài liệu

Spring Data JPA giúp ứng dụng Spring làm việc với dữ liệu quan hệ thông qua các repository. Để sử dụng đúng, cần hiểu ba lớp khái niệm: **JPA** định nghĩa cách ánh xạ và quản lý entity; **Hibernate** thường là nhà cung cấp JPA được Spring Boot cấu hình mặc định; **Spring Data JPA** bổ sung repository, cơ chế suy diễn truy vấn và tích hợp với hệ sinh thái Spring. Repository không thay thế SQL, thiết kế cơ sở dữ liệu hay ranh giới transaction.

Tài liệu sử dụng một mô hình nghiệp vụ đơn hàng xuyên suốt. Mỗi bài mới sẽ bổ sung một khả năng vào cùng mô hình đó, nhờ vậy người học thấy được một tính năng ảnh hưởng thế nào đến dữ liệu, quan hệ, truy vấn và nghiệp vụ thực tế.

## 1. Kết quả cần đạt

Sau khi học hết phần Spring Data JPA, người học cần có thể:

- Chuyển một mô hình dữ liệu quan hệ thành các entity có ánh xạ rõ ràng và đúng ràng buộc.
- Giải thích vòng đời entity, persistence context, dirty checking, flush và commit.
- Dùng repository để lưu, tìm, cập nhật và xóa dữ liệu; chọn đúng giữa derived query, JPQL, native SQL và truy vấn động.
- Ánh xạ quan hệ hai chiều mà không làm sai khóa ngoại, cascade hoặc trạng thái của đối tượng.
- Thiết kế transaction ở tầng nghiệp vụ, xử lý lỗi và hiểu tác động của propagation, isolation và read-only.
- Phát hiện N+1, tránh tải dữ liệu thừa, phân trang đúng và chọn projection phù hợp.
- Bảo vệ dữ liệu khi có nhiều giao dịch đồng thời bằng optimistic hoặc pessimistic locking.
- Viết kiểm thử persistence đủ gần với hệ quản trị cơ sở dữ liệu thực tế.

## 2. Kiến thức nền cần có

Trước khi đi sâu, nên nắm các nội dung sau:

- **Java:** class, object, constructor, access modifier, interface, generic, collection, exception, enum, **BigDecimal**, **LocalDate** và **Instant**.
- **Cơ sở dữ liệu quan hệ:** table, row, primary key, foreign key, unique constraint, **NOT NULL**, index, join, aggregate, transaction và isolation level.
- **SQL:** **SELECT**, **INSERT**, **UPDATE**, **DELETE**, **JOIN**, **GROUP BY**, **ORDER BY**, **LIMIT** hoặc cú pháp phân trang tương ứng của hệ quản trị.
- **Spring:** dependency injection, bean, configuration, service layer và cách Spring quản lý transaction.
- **Spring Boot:** cấu hình datasource, driver, migration schema và cấu hình môi trường.

Không cần học thuộc toàn bộ SQL hoặc JPA specification trước khi bắt đầu. Tuy nhiên, khi một truy vấn repository tạo ra SQL không như mong đợi, người học phải có khả năng đọc SQL và đối chiếu với mô hình bảng.

## 3. Thứ tự học đề xuất

| Thứ tự | Nội dung | Vì sao học ở bước này | Kết quả cần tự làm được |
|---|---|---|---|
| 1 | Kiến trúc JPA, Hibernate và Spring Data JPA | Phân biệt hợp đồng JPA, provider và repository abstraction trước khi dùng API | Giải thích đường đi từ service đến repository, persistence context và database |
| 2 | Entity, primary key và vòng đời entity | Mọi thao tác persistence đều dựa trên entity và trạng thái của entity | Phân biệt transient, managed, detached và removed; hiểu persist, merge, remove, flush |
| 3 | Ánh xạ cột và kiểu dữ liệu | Bắt đầu bằng dữ liệu đơn giản trước khi tạo quan hệ | Ánh xạ ID, chuỗi, số tiền, thời gian, enum, nullability và unique constraint |
| 4 | Repository và CRUD | Khi entity đã rõ, repository trở thành điểm truy cập dữ liệu dễ hiểu | Dùng JpaRepository, save, findById, findAll, delete và xử lý Optional |
| 5 | Quan hệ entity và tính nhất quán hai phía | Quan hệ cần hiểu khóa ngoại và owning side trước khi viết truy vấn phức tạp | Ánh xạ ManyToOne, OneToMany, cập nhật hai phía, cascade và orphan removal |
| 6 | Derived query và quy tắc đặt tên method | Tận dụng truy vấn đơn giản trước khi viết JPQL | Tạo truy vấn lọc theo thuộc tính, quan hệ, khoảng giá trị, trạng thái và thứ tự |
| 7 | JPQL, @Query và native query | Chọn ngôn ngữ truy vấn theo nhu cầu thay vì mặc định viết SQL | Phân biệt JPQL dùng entity/property với native SQL dùng table/column |
| 8 | Sorting, pagination và projection | Truy vấn danh sách cần giới hạn dữ liệu và chỉ lấy trường cần thiết | Dùng Sort, Pageable, Page, Slice, interface projection và DTO projection |
| 9 | Transaction và service nghiệp vụ | Các thao tác đơn lẻ đã rõ; giờ ghép chúng thành một nghiệp vụ nguyên tử | Đặt @Transactional đúng ranh giới và hiểu rollback, flush, commit |
| 10 | Fetching, lazy loading và hiệu năng | Quan hệ đã có; cần học cách tải dữ liệu để tránh N+1 và tải thừa | Dùng fetch join, @EntityGraph, projection và batch fetching có chủ đích |
| 11 | Truy vấn động với Specification/Criteria | Sau truy vấn cố định, học cách kết hợp bộ lọc tùy chọn | Xây dựng bộ lọc tìm kiếm có thể ghép điều kiện mà không tạo nhiều method gần giống nhau |
| 12 | Auditing, locking và cập nhật đồng thời | Khi ứng dụng có nhiều người dùng, dữ liệu cần dấu vết và cơ chế bảo vệ | Dùng auditing, @Version, @Lock và xử lý xung đột |
| 13 | Bulk operation, batching và persistence context | Tối ưu sau khi đã hiểu hành vi thông thường | Biết bulk update khác dirty checking thế nào và khi nào phải clear/refresh |
| 14 | Kiểm thử repository và vận hành | Kết thúc bằng kiểm chứng hành vi trên môi trường gần thực tế | Viết kiểm thử slice/integration, kiểm tra SQL, index và migration |

Có thể quay lại một bước khi bài thực hành phát hiện lỗ hổng kiến thức. Tuy nhiên, không nên học locking hoặc tối ưu batch trước khi hiểu entity state, transaction và quan hệ. Các chủ đề nâng cao chỉ có ý nghĩa khi đã biết hành vi mặc định mà chúng thay đổi.

## 4. Mô hình nghiệp vụ dùng xuyên suốt

### 4.1. Bối cảnh

Ví dụ là một cửa hàng trực tuyến đơn giản. Khách hàng đặt đơn; mỗi đơn có nhiều dòng hàng; mỗi dòng tham chiếu một sản phẩm và lưu giá tại thời điểm đặt. Đơn hàng có trạng thái và thời điểm tạo. Mô hình đủ nhỏ để theo dõi bằng mắt nhưng đủ quan hệ để minh họa hầu hết tính năng Spring Data JPA.

| Thực thể | Ý nghĩa nghiệp vụ | Dữ liệu chính |
|---|---|---|
| Customer | Người mua hàng | id, name, email |
| Product | Sản phẩm có thể được đặt mua | id, sku, name, currentPrice, active |
| PurchaseOrder | Đơn hàng của một khách hàng | id, orderNumber, customer, status, createdAt, items, totalAmount |
| OrderItem | Một dòng sản phẩm trong đơn | id, order, product, quantity, unitPrice |

Quan hệ giữa các bảng:

- Một **Customer** có thể có nhiều **PurchaseOrder**; mỗi đơn thuộc về đúng một khách hàng.
- Một **PurchaseOrder** có nhiều **OrderItem**; mỗi dòng hàng thuộc về đúng một đơn.
- Một **Product** có thể xuất hiện trong nhiều **OrderItem**; mỗi dòng hàng tham chiếu đúng một sản phẩm.
- Khóa ngoại **customer_id** nằm ở bảng đơn hàng; **order_id** và **product_id** nằm ở bảng dòng hàng.

Có thể hình dung sơ đồ quan hệ như sau:

```text
Customer (1) -------- (N) PurchaseOrder
                              |
                              | (1)
                              |
                              | (N)
                          OrderItem (N) -------- (1) Product
```

### 4.2. Quy tắc nghiệp vụ phải giữ nhất quán

1. Một đơn hàng thuộc về một khách hàng. Không tạo đơn nếu không xác định được khách hàng hợp lệ.
2. Một dòng hàng phải tham chiếu sản phẩm hợp lệ và có **quantity > 0**.
3. **unitPrice** của **OrderItem** là giá chụp tại thời điểm đặt hàng. Không lấy lại **Product.currentPrice** để tính lịch sử đơn hàng, vì giá sản phẩm có thể thay đổi sau đó.
4. Thành tiền dòng hàng bằng **unitPrice × quantity**; tổng đơn bằng tổng thành tiền các dòng.
5. Đơn hàng chỉ chuyển sang trạng thái xác nhận khi đã có ít nhất một dòng hàng và các điều kiện nghiệp vụ cần thiết được đáp ứng.
6. Trạng thái đơn hàng phải được chuyển qua các bước hợp lệ, ví dụ **DRAFT → CONFIRMED → PAID → SHIPPED**; việc hủy phải tuân theo quy tắc riêng. Không cho phép mọi trạng thái chuyển tự do sang mọi trạng thái.
7. Các thay đổi tạo đơn và thêm dòng hàng phải nằm trong cùng một transaction để không lưu được đơn dở dang.

Đây là quy tắc của ví dụ học tập. Trong hệ thống thực tế, cần bổ sung quy tắc tồn kho, thuế, vận chuyển, thanh toán, hoàn tiền và chính sách hủy theo yêu cầu sản phẩm. Không tự đưa các quy tắc đó vào entity nếu chưa có yêu cầu nghiệp vụ.

### 4.3. Vì sao lưu giá tại dòng hàng?

Giả sử hôm nay sản phẩm có giá 100.000 đồng và khách mua hai sản phẩm. Đơn ghi nhận **unitPrice = 100.000**, thành tiền là 200.000 đồng. Ngày mai giá niêm yết tăng lên 120.000 đồng. Lịch sử đơn cũ vẫn phải thể hiện 200.000 đồng; vì vậy **OrderItem** lưu giá đã chốt, còn **Product.currentPrice** chỉ phản ánh giá hiện tại.

Quy tắc này giúp phân biệt dữ liệu danh mục hiện tại với dữ liệu giao dịch lịch sử. Đây là ví dụ quan trọng để hiểu vì sao không phải mọi thuộc tính đều nên được suy ra bằng cách join sang bảng khác.

## 5. Ánh xạ entity: bắt đầu từ khóa ngoại

Các đoạn dưới đây là **minh họa mapping**, không phải một chương trình Java độc lập; imports, getters, setters và constructor phụ trợ được lược bỏ. Chúng thể hiện các quyết định cần giữ nhất quán trong các bài tiếp theo.

Một **PurchaseOrder** tham chiếu khách hàng bằng **ManyToOne** và quản lý danh sách dòng hàng bằng **OneToMany**:

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_number", nullable = false, unique = true, length = 40)
    private String orderNumber;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private OrderStatus status;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderItem> items = new ArrayList<>();

    @Column(name = "total_amount", nullable = false, precision = 19, scale = 2)
    private BigDecimal totalAmount = BigDecimal.ZERO;

    protected PurchaseOrder() {
    }

    public void addItem(OrderItem item) {
        items.add(item);
        item.attachTo(this);
    }

    public void removeItem(OrderItem item) {
        if (items.remove(item)) {
            item.detachFromOrder();
        }
    }
}
```

**OrderItem** là phía chứa khóa ngoại **order_id**, nên đây là owning side của quan hệ với đơn hàng:

```java
@Entity
@Table(name = "order_items")
public class OrderItem {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "product_id", nullable = false)
    private Product product;

    @Column(nullable = false)
    private int quantity;

    @Column(name = "unit_price", nullable = false, precision = 19, scale = 2)
    private BigDecimal unitPrice;

    protected OrderItem() {
    }

    void attachTo(PurchaseOrder order) {
        this.order = order;
    }

    void detachFromOrder() {
        this.order = null;
    }

    public BigDecimal lineTotal() {
        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }
}
```

Trong code hoàn chỉnh, constructor của **OrderItem** phải kiểm tra sản phẩm, số lượng và giá; phương thức thêm/xóa dòng hàng phải duy trì cả hai phía quan hệ và cập nhật tổng đơn. Không cho phép controller tự gán **order**, **quantity**, **unitPrice** hoặc **totalAmount** tùy ý. Nên đặt thao tác thay đổi trạng thái và tính tổng trong hành vi của aggregate hoặc service nghiệp vụ phù hợp.

Một số lưu ý khi ánh xạ:

- Entity cần có **@Id** và constructor không tham số **public** hoặc **protected**. Tránh khai báo entity **final**; provider cần khả năng quản lý entity và proxy.
- Chọn một chiến lược truy cập nhất quán. Đặt annotation trên field như ví dụ thì JPA dùng field access.
- Dùng **@Enumerated(EnumType.STRING)** để lưu tên enum; **ORDINAL** lưu số thứ tự và có thể làm dữ liệu sai khi đổi thứ tự hằng enum.
- Dùng **BigDecimal** cho tiền; không dùng **float** hoặc **double** để tính tiền. Quy định precision/scale và cách làm tròn theo nghiệp vụ.
- Dùng **Instant** cho thời điểm tuyệt đối; thống nhất cách lưu và hiển thị múi giờ giữa ứng dụng và database.
- **GenerationType.IDENTITY** phù hợp với một số hệ quản trị nhưng có thể ảnh hưởng batching. Chọn ID strategy theo database và yêu cầu triển khai; không coi một strategy là tối ưu cho mọi hệ thống.
- Tránh dùng **@Data** hoặc tự sinh **toString**, **equals**, **hashCode** bao gồm mọi quan hệ. Việc duyệt collection hai chiều có thể gây đệ quy; truy cập quan hệ lazy có thể phát sinh SQL ngoài ý muốn. Equality của entity cần được thiết kế theo vòng đời và chiến lược ID cụ thể.

## 6. Owning side, cascade và vòng đời quan hệ

JPA lưu quan hệ dựa trên phía sở hữu. Với quan hệ đơn hàng - dòng hàng, cột **order_id** nằm trong bảng **order_items**, vì thế **OrderItem.order** là owning side. **mappedBy = "order"** trong **PurchaseOrder.items** trỏ đến tên thuộc tính Java ở entity con, không phải tên cột SQL.

Khi thêm một dòng hàng, chỉ thêm vào collection phía cha là chưa đủ. Phải gán luôn **item.order**. Ngược lại, khi xóa, cần loại dòng khỏi collection và đồng bộ phía con. Có thể đóng gói hai thao tác này trong phương thức của **PurchaseOrder** để caller không quên cập nhật một phía.

**cascade = CascadeType.ALL** ở quan hệ đơn hàng - dòng hàng có nghĩa thao tác persistence trên đơn có thể lan tới các dòng thuộc đơn. **orphanRemoval = true** có nghĩa một dòng bị loại khỏi quan hệ sẽ được xóa khi persistence context đồng bộ. Chỉ dùng chúng khi dòng hàng thực sự phụ thuộc vòng đời vào đơn hàng.

Không cascade thao tác xóa từ đơn hàng sang **Customer** hoặc **Product**: khách hàng và sản phẩm tồn tại độc lập, có thể được nhiều đơn tham chiếu. Xóa một đơn không được xóa khách hàng hay sản phẩm. Cascade không phải cách thay thế cho việc hiểu quyền sở hữu dữ liệu.

## 7. Repository và truy vấn trên mô hình chung

Repository khai báo kiểu entity và kiểu khóa chính:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    List<PurchaseOrder>
        findByCustomer_IdAndStatusOrderByCreatedAtDesc(
            Long customerId,
            OrderStatus status
        );

    Page<PurchaseOrder> findByStatus(
        OrderStatus status,
        Pageable pageable
    );

    Optional<PurchaseOrder> findOneByOrderNumber(String orderNumber);
}
```

Tên method đầu tiên thể hiện đường dẫn thuộc tính **customer.id**; dấu gạch dưới giúp phân tách rõ quan hệ và thuộc tính. **JpaRepository** cung cấp CRUD, phân trang và sắp xếp cơ bản. Với truy vấn có điều kiện, Spring Data phân tích tên method để tạo query. Khi điều kiện quá phức tạp hoặc cần kiểm soát rõ câu truy vấn, dùng **@Query**.

Ví dụ JPQL tìm đơn và lấy luôn khách hàng:

```java
@Query("""
    select o
    from PurchaseOrder o
    join fetch o.customer
    where o.orderNumber = :orderNumber
    """)
Optional<PurchaseOrder> findWithCustomerByOrderNumber(
    @Param("orderNumber") String orderNumber
);
```

JPQL truy vấn entity và thuộc tính Java (**PurchaseOrder**, **customer**, **orderNumber**), không truy vấn tên table/column như SQL. Native query dùng cú pháp của database và hữu ích khi cần tính năng đặc thù hoặc câu SQL mà JPQL không biểu đạt phù hợp. Đổi lại, native query gắn chặt hơn với schema và hệ quản trị.

Phân trang một danh sách đơn đã xác nhận:

```java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(Sort.Direction.DESC, "createdAt")
);

Page<PurchaseOrder> page =
    repository.findByStatus(OrderStatus.CONFIRMED, pageable);
```

**Page** thường cần cả truy vấn dữ liệu và truy vấn đếm để tính tổng trang. **Slice** chỉ cho biết còn dữ liệu tiếp theo hay không, phù hợp khi không cần tổng số bản ghi. Luôn dùng thứ tự sắp xếp ổn định, đặc biệt khi phân trang trên dữ liệu thường xuyên thay đổi.

Không nên trả toàn bộ entity nếu màn hình chỉ cần mã đơn, tên khách hàng, thời điểm và tổng tiền. Projection hoặc DTO giúp truy vấn chỉ lấy các trường cần dùng, giảm tải dữ liệu và tránh vô tình kích hoạt lazy loading trong lúc serialize response.

## 8. Transaction: đặt ranh giới quanh nghiệp vụ

Một nghiệp vụ tạo đơn có thể gồm: kiểm tra khách hàng, tạo đơn nháp, thêm nhiều dòng hàng, tính tổng và lưu. Nếu một bước thất bại, không được để lại đơn chỉ có một phần dòng hàng. Vì vậy transaction nên bao quanh thao tác nghiệp vụ ở service:

```java
@Service
public class OrderService {

    private final PurchaseOrderRepository orderRepository;

    public OrderService(PurchaseOrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public Long saveOrder(PurchaseOrder order) {
        PurchaseOrder saved = orderRepository.save(order);
        return saved.getId();
    }

    @Transactional(readOnly = true)
    public Optional<PurchaseOrder> findOrder(Long id) {
        return orderRepository.findById(id);
    }
}
```

Đây là ví dụ rút gọn về ranh giới transaction; service thực tế cần nhận dữ liệu đầu vào phù hợp, kiểm tra quyền và quy tắc nghiệp vụ, nạp các entity liên quan, rồi gọi hành vi của aggregate. Không nên nhận nguyên entity do client gửi lên và lưu thẳng.

Trong transaction, entity được quản lý bởi persistence context. Khi thay đổi field của entity managed, dirty checking phát hiện thay đổi và provider phát SQL khi flush. **flush** đồng bộ thay đổi xuống database nhưng không đồng nghĩa commit. Commit kết thúc transaction; rollback hoàn tác các thay đổi thuộc transaction theo quy tắc của Spring và database. Cần hiểu quy tắc rollback mặc định và khai báo **rollbackFor** khi nghiệp vụ có checked exception cần rollback.

**readOnly = true** là tín hiệu tối ưu/hướng dẫn cho transaction manager và provider; không phải cơ chế bảo vệ tuyệt đối khiến mọi lệnh ghi chắc chắn bị chặn. Tránh mở transaction quá rộng hoặc gọi network chậm trong lúc đang giữ khóa database.

## 9. Fetching và hiệu năng

Quan hệ entity không đồng nghĩa dữ liệu liên quan luôn được tải cùng lúc. **LAZY** trì hoãn tải đến khi thuộc tính được truy cập; **EAGER** yêu cầu provider nạp sớm theo hợp đồng mapping, nhưng không bảo đảm chỉ có một câu SQL.

N+1 xảy ra khi ứng dụng tải N đơn hàng rồi truy cập khách hàng của từng đơn, làm phát sinh thêm nhiều query. Cách xử lý phải dựa trên use case:

- Dùng **join fetch** khi một truy vấn cụ thể cần dữ liệu quan hệ.
- Dùng **@EntityGraph** để khai báo thuộc tính cần nạp cho một repository method mà không đổi mapping mặc định toàn cục.
- Dùng DTO/interface projection khi chỉ cần một phần dữ liệu.
- Cân nhắc batch fetching khi phải nạp nhiều quan hệ lazy theo nhóm; đây có thể là tính năng cấu hình riêng của provider.
- Đo SQL và số query trong kiểm thử hoặc môi trường phát triển. Không suy đoán hiệu năng chỉ từ số lượng method Java.

Đặc biệt cẩn thận khi phân trang cùng fetch join collection **OneToMany**: join có thể nhân bản hàng cha và làm việc phân trang/count không còn đúng hoặc khiến provider phải xử lý trong bộ nhớ. Có thể phân trang ID đơn hàng trước rồi tải chi tiết bằng truy vấn thứ hai, hoặc dùng projection phù hợp. Không thêm fetch join cho mọi quan hệ chỉ để tránh lỗi lazy.

## 10. Truy vấn động, projection và các chủ đề nâng cao

Khi màn hình tìm kiếm đơn hàng có nhiều bộ lọc tùy chọn như khách hàng, trạng thái, khoảng ngày và khoảng tổng tiền, nhiều derived method sẽ nhanh chóng trở nên khó quản lý. **JpaSpecificationExecutor** và **Specification** cho phép ghép các predicate theo điều kiện có mặt. Mỗi predicate cần dùng đúng kiểu dữ liệu, xử lý null rõ ràng và có index hỗ trợ khi truy vấn trên bảng lớn.

Projection giúp giới hạn trường đọc. Có thể dùng interface projection cho truy vấn theo tên thuộc tính hoặc DTO projection cho kết quả được định hình rõ. Với DTO constructor expression trong JPQL, constructor và kiểu dữ liệu phải khớp với kết quả select.

Khi nhiều giao dịch cùng sửa một đơn, **@Version** hỗ trợ optimistic locking: câu update kiểm tra version; nếu một giao dịch đã cập nhật trước, giao dịch còn lại nhận lỗi xung đột và cần xử lý/retry theo nghiệp vụ. Pessimistic locking (**@Lock** với **PESSIMISTIC_WRITE**) khóa bản ghi trong thời gian transaction; dùng khi cần tuần tự hóa thao tác và phải cân nhắc deadlock, thời gian giữ khóa cùng thứ tự truy cập.

Auditing có thể ghi **createdAt**, **createdBy**, **lastModifiedAt**, **lastModifiedBy** bằng Spring Data auditing (**@CreatedDate**, **@LastModifiedDate**, **@CreatedBy**, **@LastModifiedBy**) và cấu hình auditing phù hợp. Đây là dấu vết kỹ thuật về việc tạo/sửa bản ghi; không thay thế lịch sử nghiệp vụ như ai đã xác nhận, hủy hoặc hoàn tiền đơn hàng.

Bulk JPQL update/delete chạy trực tiếp trên database và không đi qua cơ chế dirty checking của từng entity. Persistence context hiện tại có thể giữ dữ liệu cũ; cần chủ động flush/clear hoặc refresh theo trường hợp. Lifecycle callback và entity đang managed không tự được cập nhật giống thao tác sửa từng entity. Batching giảm số lần round trip nhưng cần đo trên database thật và hiểu ảnh hưởng của chiến lược sinh ID.

## 11. Kiểm thử và xác minh

- Dùng **@DataJpaTest** để kiểm tra mapping, repository query và hành vi persistence trong một lát cắt ứng dụng.
- Dùng database cùng loại với môi trường chạy thật khi cần xác minh dialect, kiểu dữ liệu, khóa, index, transaction hoặc native SQL. H2 hữu ích cho kiểm thử nhanh nhưng không bảo đảm hành vi giống PostgreSQL, MySQL hay database khác.
- Dùng Testcontainers khi cần khởi tạo database thật có thể lặp lại trong integration test.
- Kiểm tra cả dữ liệu lưu và hành vi sau khi đọc lại; đừng chỉ xác nhận method trả về một object.
- Kiểm thử quy tắc nghiệp vụ: tổng đơn, giá chụp tại thời điểm mua, trạng thái hợp lệ, rollback khi thêm dòng hàng thất bại và xung đột khi cập nhật đồng thời.
- Quan sát SQL khi điều tra N+1, truy vấn thiếu index, phân trang sai hoặc tải quá nhiều cột.
- Dùng migration có phiên bản để thay đổi schema có kiểm soát; không phụ thuộc **ddl-auto=update** như chiến lược quản lý schema cho production.

## 12. Lộ trình thực hành với cùng một mô hình

Có thể dùng chuỗi bài tập sau để tự kiểm tra tiến độ:

1. Tạo **Customer** và **Product**, lưu rồi đọc lại bằng repository.
2. Tạo **PurchaseOrder** nháp cho một khách hàng; thêm hai **OrderItem** với số lượng và giá chụp khác nhau.
3. Tính tổng đơn từ các dòng hàng và kiểm tra kết quả bằng **BigDecimal**.
4. Tìm đơn theo khách hàng và trạng thái; sắp xếp đơn mới nhất trước.
5. Phân trang danh sách đơn; tạo DTO chỉ chứa mã đơn, tên khách, thời điểm và tổng tiền.
6. Dùng transaction để xác nhận đơn; thử làm một bước thất bại và xác nhận toàn bộ thay đổi được rollback.
7. Đọc danh sách đơn kèm khách hàng; quan sát SQL trước và sau khi dùng fetch join hoặc entity graph.
8. Thêm bộ lọc ngày/trạng thái/tổng tiền bằng Specification.
9. Thêm **@Version**, mô phỏng hai giao dịch cùng cập nhật một đơn và xử lý xung đột.
10. Viết integration test trên database tương thích với môi trường triển khai.

Khi thực hành, giữ nguyên tên entity, ý nghĩa thuộc tính và quy tắc giá chụp giữa các bài. Nếu một bài cần mở rộng mô hình, hãy nêu rõ thuộc tính/bảng mới và lý do nghiệp vụ; không âm thầm đổi ý nghĩa dữ liệu đã dùng ở bài trước.

## 13. Các lỗi cần nhận diện sớm

| Biểu hiện | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| LazyInitializationException | Truy cập quan hệ lazy sau khi persistence context đã đóng | Xác định transaction boundary; dùng DTO, fetch plan hoặc truy vấn phù hợp |
| Nhiều query cho một danh sách | N+1 khi truy cập quan hệ từng entity | Bật log SQL, đếm query, chọn entity graph/fetch join/projection |
| Thêm vào collection nhưng FK không đổi | Chỉ cập nhật inverse side, chưa gán owning side | Đồng bộ OrderItem.order và PurchaseOrder.items |
| Xóa đơn làm mất dữ liệu dùng chung | Cascade REMOVE đặt lên quan hệ không sở hữu vòng đời | Chỉ cascade tới entity con thực sự phụ thuộc |
| Enum đọc sai sau khi đổi thứ tự khai báo | Dùng ordinal | Lưu enum bằng STRING và quản lý thay đổi giá trị |
| Tổng tiền thay đổi khi giá sản phẩm đổi | Tính lại lịch sử bằng giá hiện tại | Lưu giá chụp ở OrderItem.unitPrice |
| Kết quả phân trang lặp hoặc thiếu | Join collection làm nhân bản hàng hoặc thứ tự không ổn định | Kiểm tra SQL/count và dùng chiến lược phân trang phù hợp |
| Dữ liệu entity trong bộ nhớ cũ sau bulk update | Bulk query bỏ qua trạng thái managed hiện tại | Flush/clear/refresh persistence context theo đúng luồng |
| Lỗi trùng dữ liệu hoặc mất cập nhật | Thiếu unique constraint, transaction hoặc locking | Xác định invariant và bảo vệ ở database cùng tầng nghiệp vụ |

## 14. Cách dùng mô hình trong các bài tiếp theo

Mỗi bài nên trả lời bốn câu hỏi trước khi đi vào API:

1. **Nghiệp vụ đang giải quyết là gì?** Ví dụ: tìm các đơn đã xác nhận của một khách hàng.
2. **Dữ liệu nào liên quan?** Ví dụ: PurchaseOrder, Customer, trạng thái và thời điểm tạo.
3. **Ràng buộc nào phải giữ?** Ví dụ: khách hàng phải tồn tại; thứ tự phân trang ổn định; giá lịch sử không đổi.
4. **Cần đọc/ghi bao nhiêu dữ liệu?** Ví dụ: danh sách chỉ cần DTO, màn hình chi tiết cần các dòng hàng và sản phẩm.

Sau đó mới chọn repository method, JPQL, projection, entity graph, transaction hoặc locking. Cách tiếp cận này giúp phân biệt yêu cầu nghiệp vụ với lựa chọn kỹ thuật, đồng thời khiến ví dụ giữa các bài có thể nối tiếp nhau.

**Nguyên tắc xuyên suốt:** entity phản ánh dữ liệu được quản lý bởi persistence context; repository biểu diễn thao tác truy cập dữ liệu; service điều phối transaction và nghiệp vụ; DTO định hình dữ liệu trao đổi qua biên ứng dụng. Giữ rõ các vai trò này sẽ giúp ứng dụng Spring Data JPA dễ kiểm thử, dễ tối ưu và ít phát sinh lỗi nhất quán dữ liệu.
