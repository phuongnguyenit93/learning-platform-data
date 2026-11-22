# Chuyển từ JPA: thay đổi tư duy về aggregate và vòng đời đối tượng

Chuyển một ứng dụng từ **JPA/Hibernate** sang **Spring Data Relational JDBC** không chỉ là đổi repository interface hoặc thay annotation. Hai công nghệ có mô hình persistence khác nhau. JPA quản lý entity trong một persistence context, theo dõi thay đổi object và có thể tải quan hệ lười. Spring Data JDBC làm việc theo **aggregate boundary**: repository đọc và ghi aggregate như một đơn vị, object Java không được framework giữ trong một persistence context dài hạn.

Thay đổi quan trọng nhất là cách suy nghĩ về object:

- Với JPA, một entity có thể trở thành managed sau khi được EntityManager tải hoặc persist; thay đổi field có thể được dirty checking phát hiện và ghi xuống database khi flush.
- Với Spring Data JDBC, object là dữ liệu trong bộ nhớ. Khi muốn lưu thay đổi, ứng dụng gọi repository/template một cách tường minh. Không có dirty checking, lazy proxy hay identity map của persistence context.
- Với JPA, quan hệ object thường được mô hình hóa bằng association giữa entity. Với Spring Data JDBC, cần xác định aggregate root, entity được sở hữu và reference đến aggregate khác.
- Với JPA, cascade và orphanRemoval điều khiển vòng đời entity trong persistence context. Với Spring Data JDBC, ownership của aggregate quyết định phần dữ liệu được lưu/xóa cùng root.
- Với JPA, query có thể tải một phần graph qua fetch join/entity graph. Với Spring Data JDBC, query root và các collection được xử lý theo aggregate loading; query tùy biến thường trả DTO/read model.

Không nên dịch máy móc từng annotation JPA sang một annotation JDBC tương tự. Hãy xác định lại ranh giới aggregate và use case trước, sau đó thiết kế mapping, query, transaction và test theo mô hình mới.

## 1. Hai mô hình persistence khác nhau

### JPA: persistence context quản lý entity

JPA EntityManager duy trì một persistence context. Trong phạm vi context, entity có trạng thái lifecycle:

- **New/transient:** object chưa được persistence context quản lý.
- **Managed:** object được theo dõi; thay đổi persistent fields có thể được dirty checking ghi xuống database.
- **Detached:** object từng được quản lý nhưng hiện không còn gắn với persistence context.
- **Removed:** entity được đánh dấu xóa và sẽ bị xóa khi flush/commit.

Ví dụ:

~~~java
@Transactional
public void renameCustomer(Long id, String name) {
    Customer customer = entityManager.find(Customer.class, id);
    customer.setName(name);
    // Không cần gọi save().
    // Dirty checking sẽ phát hiện thay đổi khi flush/commit.
}
~~~

Nếu entity được tải trong cùng persistence context, EntityManager thường trả về cùng managed instance cho cùng entity identity. Đây là identity map. JPA cũng có thể dùng proxy để tải quan hệ lazy khi ứng dụng truy cập property.

### Spring Data JDBC: lưu aggregate tường minh

Spring Data JDBC không duy trì persistence context kiểu JPA. Khi repository đọc dữ liệu, framework tạo object graph cho aggregate và trả về cho ứng dụng. Object không trở thành managed entity.

Cùng use case phải gọi save:

~~~java
@Transactional
public void renameCustomer(Long id, String name) {
    Customer customer = customerRepository.findById(id)
            .orElseThrow();

    customer.rename(name);

    customerRepository.save(customer);
}
~~~

Nếu bỏ lời gọi save, thay đổi chỉ nằm trong object Java và không được ghi xuống database.

### So sánh vòng đời

| Khía cạnh | JPA/Hibernate | Spring Data JDBC |
|---|---|---|
| Persistence context | Có | Không |
| Managed entity | Có | Không có khái niệm tương đương |
| Dirty checking | Có | Không |
| Flush | Có; đồng bộ thay đổi persistence context với DB | Không có flush của persistence context; repository thực thi thao tác persistence khi được gọi |
| Lazy proxy | Có thể có | Không |
| Identity map | Có trong persistence context | Không |
| Detached entity | Có | Object chỉ là object; không có trạng thái managed/detached |
| Thay đổi object | Có thể tự được ghi khi flush | Phải gọi save/update tường minh |
| Aggregate boundary | Không được JPA áp đặt | Là trung tâm của persistence model |

**Hệ quả:** code dựa vào việc “tải entity, sửa field, rồi để transaction tự flush” phải được viết lại khi chuyển sang Spring Data JDBC.

## 2. Xác định aggregate boundary trước khi đổi mapping

Trong Spring Data JDBC, aggregate là một cụm object có một root quản lý vòng đời. Root là entry point để tải và lưu cụm dữ liệu đó.

Ví dụ:

~~~text
PurchaseOrder (aggregate root)
  id
  customer reference
  status
  shipping address (value object)
  lines
    ├── OrderLine
    └── OrderLine

Customer (aggregate root riêng)
  id
  name

Product (aggregate root riêng)
  id
  sku
~~~

PurchaseOrder sở hữu OrderLine và ShippingAddress. Customer và Product là aggregate root riêng; PurchaseOrder chỉ tham chiếu chúng bằng ID.

Quy tắc thiết kế:

1. Một aggregate có một root được truy cập qua repository.
2. Entity được sở hữu có vòng đời phụ thuộc vào root.
3. Aggregate root khác được tham chiếu bằng identifier, không được coi như child object có cascade save/delete.
4. Transaction boundary thường bao trùm một use case có thể cập nhật một hoặc nhiều aggregate, nhưng mỗi aggregate vẫn có ranh giới ownership riêng.
5. Nếu một child cần được tải, cập nhật và xóa độc lập thường xuyên, hãy xem xét biến nó thành aggregate root riêng.

### Từ association graph sang aggregate model

Một mô hình JPA có thể có nhiều quan hệ hai chiều:

~~~java
@Entity
class PurchaseOrder {
    @OneToMany(mappedBy = "order",
               cascade = CascadeType.ALL,
               orphanRemoval = true)
    private List<OrderLine> lines;
}

@Entity
class OrderLine {
    @ManyToOne
    private PurchaseOrder order;

    @ManyToOne
    private Product product;
}
~~~

Khi chuyển sang Spring Data JDBC, không cần duy trì hai chiều object graph đó. Root giữ collection child; child không cần giữ back-reference đến root. Product được tham chiếu bằng ID hoặc AggregateReference.

~~~java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private Long customerId;

    private String status;

    @MappedCollection(idColumn = "order_id", keyColumn = "line_no")
    private List<OrderLine> lines = new ArrayList<>();
}

public class OrderLine {

    private Long productId;

    private int quantity;

    private BigDecimal unitPrice;
}
~~~

Đoạn code là ví dụ khái niệm; constructor, accessor, ID strategy và tên cột cần khớp schema của ứng dụng. Cột order_id trong bảng child là FK về root; productId là reference đến aggregate Product.

## 3. Thay đổi cách nghĩ về entity lifecycle

### JPA: thay đổi entity managed

Trong JPA, method service có thể tải entity, gọi setter/domain method và không cần repository.save nếu entity vẫn managed:

~~~java
@Transactional
public void changeOrderStatus(Long id, String status) {
    PurchaseOrder order = entityManager.find(PurchaseOrder.class, id);
    order.setStatus(status);
}
~~~

Khi transaction flush, Hibernate kiểm tra trạng thái entity và phát SQL cần thiết.

### Spring Data JDBC: load, thay đổi, save

Trong Spring Data JDBC, cùng flow phải ghi rõ:

~~~java
@Transactional
public void changeOrderStatus(Long id, String status) {
    PurchaseOrder order = orderRepository.findById(id)
            .orElseThrow(() -> new OrderNotFoundException(id));

    order.changeStatus(status);

    orderRepository.save(order);
}
~~~

Không có một background mechanism phát hiện thay đổi object. Nếu không gọi save, database không thay đổi.

### Không có merge semantics giống JPA

JPA EntityManager.merge nhận trạng thái từ một detached object và sao chép vào managed instance tương ứng. Giá trị trả về từ merge là managed instance; object truyền vào không nhất thiết trở thành managed.

Spring Data JDBC repository.save không phải bản sao của EntityManager.merge. Nó lưu aggregate theo mapping và newness detection của Spring Data. Không giả định save một object detached/stale sẽ hợp nhất từng field giống Hibernate.

Khi cần cập nhật một aggregate:

1. Tải aggregate hiện tại.
2. Áp dụng command/domain behavior lên object vừa tải.
3. Gọi save trong transaction.
4. Dùng object trả về từ save, đặc biệt khi dùng immutable entity, generated ID hoặc version.

~~~java
@Transactional
public PurchaseOrder updateOrder(Long id, UpdateOrderCommand command) {
    PurchaseOrder order = orderRepository.findById(id)
            .orElseThrow(() -> new OrderNotFoundException(id));

    order.changeShippingAddress(command.address());
    order.changeStatus(command.status());

    return orderRepository.save(order);
}
~~~

Nếu nhận một object từ client/API, đừng coi object đó là detached entity có thể merge. Hãy coi nó là command/DTO, tải aggregate hiện tại và áp dụng các thay đổi được phép.

## 4. save() không phải dirty checking

Spring Data JDBC sử dụng save để lưu aggregate. Framework xác định insert hay update dựa trên trạng thái mới/cũ của entity theo cơ chế newness detection, thường liên quan đến ID và version.

Ví dụ:

~~~java
PurchaseOrder newOrder = new PurchaseOrder(customerId, "DRAFT");
PurchaseOrder saved = repository.save(newOrder);
~~~

Nếu ID được database sinh, object trả về có ID được gán theo mapping.

Với aggregate đã tồn tại:

~~~java
PurchaseOrder existing = repository.findById(id).orElseThrow();
existing.changeStatus("PAID");
PurchaseOrder saved = repository.save(existing);
~~~

Không giả định save chỉ phát một UPDATE cho field vừa thay đổi như dirty checking. Spring Data JDBC lưu aggregate theo mapping của nó; việc lưu các entity được sở hữu có thể cần nhiều statement. Đặc biệt, khi update aggregate, dependent entities có thể được xóa và insert lại theo chiến lược persistence của framework. Điều này ảnh hưởng đến trigger, audit ở database, generated child IDs và FK. Hãy xem SQL thực tế và kiểm tra behavior trên phiên bản Spring Data Relational đang dùng.

### Assigned ID và xác định entity mới

Một migration hay gặp là JPA entity dùng ID do ứng dụng gán trước khi persist. Trong Spring Data JDBC, một ID không null thường làm entity được coi là đã tồn tại nếu không có thông tin newness khác. Nếu ID được gán trước cho aggregate mới, save có thể đi vào nhánh update.

Các lựa chọn:

- Dùng ID database-generated nếu phù hợp.
- Dùng @Version để Spring Data có thêm thông tin xác định newness theo quy tắc framework.
- Implement Persistable và isNew() khi cần kiểm soát rõ trạng thái mới.
- Viết test cho insert/update với assigned ID, không dựa vào giả định từ JPA.

Ví dụ interface:

~~~java
public class ExternalOrder implements Persistable<String> {

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

    public void markPersisted() {
        this.newEntity = false;
    }
}
~~~

Ví dụ này cần bổ sung cơ chế chuyển trạng thái sau khi insert và có thể dùng callback/withers phù hợp với kiểu entity. Với immutable model, thiết kế newness state khác đi. Không giữ cờ transient sai trạng thái vì nó có thể khiến save tiếp theo cố insert duplicate key.

## 5. JPA relationships chuyển thành ownership và references

### @OneToMany: thường là owned collection

JPA:

~~~java
@OneToMany(mappedBy = "order",
           cascade = CascadeType.ALL,
           orphanRemoval = true)
private List<OrderLine> lines;
~~~

Spring Data JDBC:

~~~java
@MappedCollection(idColumn = "order_id", keyColumn = "line_no")
private List<OrderLine> lines;
~~~

Collection child nằm trong bảng riêng với FK về root. Aggregate root quản lý vòng đời của child. Không cần back-reference object từ OrderLine về PurchaseOrder.

### @ManyToOne: reference bằng ID

JPA:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "customer_id")
private Customer customer;
~~~

Spring Data JDBC có thể lưu ID:

~~~java
@Column("customer_id")
private Long customerId;
~~~

Hoặc dùng AggregateReference:

~~~java
private AggregateReference<Customer, Long> customer;
~~~

Schema vẫn có cột customer_id và có thể có FK đến customer(id). Khi tải PurchaseOrder, Spring Data JDBC không tự tải Customer thành object graph qua lazy proxy. Nếu cần tên customer, thực hiện query riêng hoặc dùng projection JOIN.

### @ManyToMany: xem lại mô hình

JPA thường có thể dùng @ManyToMany để map join table. Khi chuyển sang Spring Data JDBC, hãy xem quan hệ đó có thực sự là many-to-many hay join table có dữ liệu/identity riêng.

Nếu association có thuộc tính như quantity, role, createdAt hoặc trạng thái, mô hình hóa association thành entity/aggregate phù hợp. Nếu chỉ cần tham chiếu đến nhiều aggregate khác, lưu ID trong một owned collection/reference structure theo mapping được hỗ trợ và xác định rõ ownership. Không tạo hai aggregate root cùng sở hữu một collection row.

### Bidirectional association không phải mục tiêu

JPA có thể duy trì cả hai chiều và yêu cầu helper method cập nhật owning side/inverse side. Spring Data JDBC thường dùng object graph một chiều từ aggregate root xuống child. Các quan hệ ngược chiều được giải quyết bằng query riêng khi cần.

Điều này giảm vòng tham chiếu và giúp aggregate boundary dễ nhìn hơn, nhưng yêu cầu ứng dụng viết query rõ ràng cho các hướng navigation khác.

## 6. CascadeType và orphanRemoval không được dịch máy móc

Trong JPA:

- CascadeType.PERSIST/REMOVE/MERGE/ALL lan truyền operation theo association.
- orphanRemoval xóa child khi child bị loại khỏi collection/association.

Trong Spring Data JDBC, không có cùng tập cascade annotations. Persistence của owned entities nằm trong aggregate root; save/delete root xử lý phần dữ liệu được sở hữu theo aggregate mapping. Reference đến aggregate khác không có nghĩa cascade.

| JPA mapping | Cách suy nghĩ khi chuyển sang JDBC |
|---|---|
| CascadeType.PERSIST trên owned child | Child thuộc aggregate; lưu thông qua root |
| CascadeType.MERGE | Tải root, áp dụng thay đổi rồi save; không có merge persistence-context semantics |
| CascadeType.REMOVE trên owned child | Xóa root/owned data theo aggregate lifecycle |
| CascadeType.REMOVE trên Customer/Product reference | Không cascade sang aggregate khác; xóa aggregate độc lập qua use case riêng |
| orphanRemoval=true | Việc bỏ child khỏi owned collection được xử lý theo aggregate persistence; kiểm thử SQL và FK |
| CascadeType.ALL trên graph lớn | Phân tích lại ownership; không chuyển nguyên xi |

Đặc biệt, JPA cascade từ PurchaseOrder đến Customer có thể đang làm application xóa Customer cùng Order vì mapping cũ. Nếu Customer thực sự là aggregate root độc lập, hành vi đó thường vi phạm ranh giới aggregate. Chuyển sang JDBC là cơ hội xác định lại invariant và quy trình xóa.

### Database FK và cascade

Không đồng nhất framework cascade với ON DELETE CASCADE của database. Chúng là hai cơ chế khác nhau:

- JPA cascade là persistence provider điều phối operation qua entity graph.
- Spring Data JDBC aggregate persistence điều phối thao tác cho owned entities.
- FK ON DELETE CASCADE là database tự xóa row phụ thuộc khi row cha bị xóa.

Chọn database cascade có chủ đích, nhất là khi còn direct SQL, batch job hoặc ứng dụng khác ghi cùng schema. Kiểm tra thứ tự delete và constraint trên database thực tế.

## 7. Lazy loading thay bằng query/read model tường minh

JPA có thể khai báo:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;

@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderLine> lines;
~~~

Ứng dụng có thể truy cập order.getLines() trong khi persistence context còn mở; Hibernate có thể phát SQL bổ sung. Điều này tiện nhưng dễ tạo N+1 và lỗi LazyInitializationException khi truy cập sau khi session đóng.

Spring Data JDBC không có lazy proxy. Khi tải aggregate, framework tải các entity được sở hữu theo chiến lược aggregate loading. Reference đến aggregate khác không tự tải object liên quan.

Nếu cần dữ liệu liên quan cho màn hình:

- Dùng projection DTO với SQL JOIN.
- Dùng repository fragment/NamedParameterJdbcTemplate cho query chuyên biệt.
- Tải aggregate root riêng nếu use case cần domain behavior.
- Dùng Single Query Loading nếu aggregate và dialect đáp ứng giới hạn của tính năng.

Không thay lazy loading bằng việc gọi repository trong getter. Getter có side effect truy vấn sẽ che giấu query count và tạo coupling khó kiểm soát.

### N+1 vẫn có thể xuất hiện ở tầng service

Ví dụ:

~~~java
List<PurchaseOrder> orders = repository.findAll();

for (PurchaseOrder order : orders) {
    Customer customer = customerRepository.findById(order.getCustomerId())
            .orElseThrow();
    // ...
}
~~~

Không có lazy proxy nhưng code vẫn tạo N+1 bằng cách gọi repository trong vòng lặp. Nếu view cần customer name, viết một query JOIN/projection hoặc tải customers theo một batch ID.

## 8. Embedded value object và custom conversion

JPA có @Embeddable/@Embedded:

~~~java
@Embeddable
public class Address {
    private String street;
    private String city;
}

@Embedded
private Address shippingAddress;
~~~

Spring Data JDBC cũng có @Embedded để lưu field value object vào các cột của bảng owner:

~~~java
@Embedded(prefix = "shipping_")
private Address shippingAddress;
~~~

DDL có các cột shipping_street, shipping_city. Embedded object không phải aggregate root và không có bảng riêng.

Nếu value object được biểu diễn thành một store value đơn giản, có thể dùng custom converter domain type ↔ String/BigDecimal/UUID. Spring Data JDBC dùng JdbcCustomConversions; JPA AttributeConverter không tự được tái sử dụng như converter Spring Data.

Ví dụ:

~~~java
@WritingConverter
public class EmailAddressWritingConverter
        implements Converter<EmailAddress, String> {

    @Override
    public String convert(EmailAddress source) {
        return source.value();
    }
}

@ReadingConverter
public class EmailAddressReadingConverter
        implements Converter<String, EmailAddress> {

    @Override
    public EmailAddress convert(String source) {
        return new EmailAddress(source);
    }
}
~~~

Converter hai chiều cần được đăng ký trong JdbcCustomConversions/AbstractJdbcConfiguration hoặc cấu hình tương ứng của Spring Boot. Kiểm tra kiểu JDBC store thực tế và null behavior.

## 9. Transaction boundary vẫn quan trọng, nhưng không có flush context

Cả JPA và Spring Data JDBC đều có thể dùng @Transactional của Spring. Tuy nhiên, transaction không biến object Spring Data JDBC thành managed entity.

JPA có thể trì hoãn SQL đến flush/commit. Spring Data JDBC thực hiện các câu SQL khi repository/template được gọi, trong transaction hiện tại. Điều đó ảnh hưởng đến thời điểm constraint error xuất hiện và cách đọc SQL log.

Ví dụ service:

~~~java
@Transactional
public void placeOrder(PurchaseOrder order) {
    PurchaseOrder saved = orderRepository.save(order);
    inventoryRepository.reserve(order.getProductId(), order.getQuantity());

    if (saved.getId() == null) {
        throw new IllegalStateException("Missing generated ID");
    }
}
~~~

Các câu SQL đã chạy nhưng chưa commit cho đến khi transaction kết thúc. Nếu method ném runtime exception, transaction có thể rollback tất cả thay đổi. Không cần gọi EntityManager.flush vì Spring Data JDBC không dùng EntityManager.

### Repository transaction và service transaction

Spring Data JDBC repository CRUD methods có transaction metadata mặc định. Tuy nhiên, khi use case gọi nhiều repository hoặc phối hợp repository với JdbcTemplate, đặt @Transactional ở service để tất cả thao tác nằm trong cùng transaction boundary.

Không dựa vào mỗi repository method để tạo atomicity cho toàn use case. Nếu mỗi method được gọi riêng và không có transaction bao ngoài, chúng có thể commit riêng.

### Không gọi database trong khi chờ network

Transaction dài có thể giữ connection và row lock. Sau khi chuyển từ JPA, cần rà soát service boundary để tránh mở transaction trước HTTP call hoặc chờ user input. Dùng outbox/saga nếu workflow phối hợp database với hệ thống ngoài.

## 10. Optimistic locking: @Version vẫn có nhưng semantics khác persistence context

Spring Data JDBC hỗ trợ optimistic locking qua @Version:

~~~java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    @Version
    private Long version;

    private String status;
}
~~~

Khi update, framework dùng version hiện tại trong điều kiện SQL và tăng version. Nếu row đã được transaction khác sửa, update không khớp version và Spring ném OptimisticLockingFailureException.

Khác biệt so với JPA:

- JPA thường phát hiện stale state khi flush managed entity.
- Spring Data JDBC phát hiện trong thao tác save/update tường minh.
- Không có persistence context để giữ managed snapshot.
- Object cũ trong bộ nhớ vẫn có thể stale; phải reload/retry theo nghiệp vụ.

Test concurrency nên dùng hai transaction/connection riêng:

1. Cả hai tải cùng root với version v.
2. Transaction A cập nhật và commit, version thành v+1.
3. Transaction B cố save object vẫn mang version v.
4. Transaction B phải nhận optimistic locking failure.

Không bắt exception rồi tiếp tục dùng object stale. Retry cần tải aggregate mới trong transaction mới và áp dụng lại command nếu business rule cho phép.

## 11. Entity callbacks và auditing

JPA có lifecycle annotations như @PrePersist, @PostLoad, @PreUpdate, @PreRemove. Spring Data JDBC có entity callbacks và lifecycle events riêng, ví dụ BeforeConvertCallback, BeforeSaveCallback, AfterSaveCallback, BeforeDeleteCallback và AfterDeleteCallback.

Không chuyển annotation JPA trực tiếp sang Spring Data JDBC; cần triển khai callback interface tương ứng hoặc chuyển logic nghiệp vụ về domain/service.

Ví dụ auditing:

~~~java
@Configuration
@EnableJdbcAuditing
public class JdbcAuditingConfiguration {
}
~~~

Entity có thể dùng @CreatedDate và @LastModifiedDate nếu auditing được cấu hình. Khi MyBatis/direct SQL cập nhật bảng, các callback/auditing Spring Data JDBC không tự chạy. Nếu nhiều đường ghi cùng tồn tại, cần quy ước cập nhật audit columns ở mọi đường.

Callback persistence không thay thế domain event hoặc after-commit event. Nếu gửi email/message chỉ sau khi commit, dùng transactional event listener AFTER_COMMIT hoặc transactional outbox.

## 12. Query language và repository API thay đổi

JPA có JPQL, Criteria API, EntityGraph và fetch join. Spring Data JDBC không cung cấp JPQL hoặc persistence context. Các cách query chính:

- Derived query cho property của aggregate root có thể lọc mà không cần JOIN.
- @Query để viết SQL tường minh.
- Repository fragment với JdbcTemplate/NamedParameterJdbcTemplate cho SQL động, JOIN, projection và query phức tạp.
- DTO projection/RowMapper cho read model.
- Aggregate loading cho command/domain use case.

Ví dụ derived query:

~~~java
List<PurchaseOrder> findByStatusAndCustomerId(
        String status,
        Long customerId
);
~~~

Tìm theo Customer name cần SQL JOIN vì Customer là aggregate khác:

~~~sql
SELECT po.id, po.customer_id, po.status, po.created_at
FROM purchase_order po
JOIN customer c ON c.id = po.customer_id
WHERE c.name = :customerName;
~~~

Nếu query trả DTO, dùng RowMapper. Nếu query trả aggregate root, cần tuân theo mapping/constructor requirements; collection có thể được tải bằng query riêng. Không giả định một JOIN trong @Query tự dựng đầy đủ object graph.

## 13. Tái thiết kế Many-to-Many và shared child

JPA cho phép @ManyToMany khi hai entity có association table. Nhưng nếu association có thuộc tính hoặc vòng đời riêng, mô hình join table thành entity rõ ràng.

Ví dụ User và Role:

~~~text
User (aggregate)
Role (aggregate)
UserRoleAssignment (association data)
  user_id
  role_id
  assigned_at
  assigned_by
~~~

Nếu assignment có nghiệp vụ riêng, không nên để cả User và Role cùng sở hữu nó. Chọn aggregate root chịu trách nhiệm tạo/xóa assignment, hoặc thiết kế assignment thành aggregate riêng có ID và reference đến User/Role.

Nguyên tắc: một row được một aggregate sở hữu. Nhiều aggregate có thể tham chiếu cùng ID nhưng không cùng quản lý vòng đời row đó.

## 14. Schema và migration khi chuyển từ Hibernate

Nếu ứng dụng dùng Hibernate schema generation, không tiếp tục dựa vào ddl-auto để tự thay schema production khi chuyển sang JDBC.

Hãy quản lý DDL bằng Flyway/Liquibase:

- Giữ bảng/cột hiện có nếu schema đã ổn định.
- Đối chiếu tên bảng/cột với @Table/@Column và NamingStrategy.
- Bảo đảm FK phản ánh aggregate ownership/reference.
- Xác định child table FK và key column cho @MappedCollection.
- Thêm version column nếu dùng @Version.
- Chọn SQL type tương thích converter/JDBC driver.
- Tạo index theo query workload.
- Chạy migration trên database production-compatible trước khi deploy.

Không đổi schema và mapping trong một lần deploy nếu cần tương thích với phiên bản ứng dụng cũ đang chạy. Dùng expand → backfill → contract khi thay đổi phá vỡ tương thích.

### So sánh schema JPA và Spring Data JDBC

| JPA/Hibernate concept | Spring Data JDBC schema consideration |
|---|---|
| @Entity + @Table | Aggregate root/owned entity mapping và bảng tương ứng |
| @Id + @GeneratedValue | @Id với ID generation phù hợp dialect/schema |
| @JoinColumn | Cột FK, idColumn hoặc scalar/AggregateReference |
| @OrderColumn | keyColumn cho List/collection position |
| @Embedded | @Embedded prefix hoặc converter |
| @Version | Cột version tương ứng |
| @ManyToMany join table | Association entity/owned collection/reference theo ownership |
| orphanRemoval | Child thuộc aggregate; kiểm thử insert/delete/update collection |
| Hibernate DDL auto | Versioned migrations Flyway/Liquibase |

## 15. Chiến lược migration theo từng bước

Đừng chuyển toàn bộ entity và service trong một commit lớn. Một lộ trình ít rủi ro:

### Bước 1: Kiểm kê JPA behavior

Tìm các điểm phụ thuộc vào:

- EntityManager.find/persist/merge/remove.
- Dirty checking và flush.
- Lazy loading và proxy.
- CascadeType và orphanRemoval.
- Bidirectional relationship helper methods.
- JPQL/Criteria/fetch join/entity graph.
- Entity listeners, callbacks và auditing.
- @Version và locking.
- Hibernate-specific annotations, filters, custom types và schema generation.

Đặc biệt tìm các method không gọi repository.save nhưng vẫn sửa entity. Những method này phụ thuộc dirty checking và phải được sửa.

### Bước 2: Vẽ aggregate boundary

Với mỗi entity, xác định:

- Root nào quản lý lifecycle.
- Entity nào là owned child.
- Value object nào có thể embedded.
- Aggregate root nào chỉ được tham chiếu bằng ID.
- Quan hệ nào cần query JOIN thay vì object navigation.
- Child nào cần identity/lifecycle độc lập.

Không quyết định boundary chỉ từ annotation @OneToMany/@ManyToOne cũ. Dùng invariant và transaction consistency để xác định.

### Bước 3: Giữ schema ổn định và viết mapping

Tạo model Spring Data JDBC với @Table, @Id, @Column, @MappedCollection, @Embedded, AggregateReference và converter cần thiết. Đối chiếu DDL hiện tại; dùng explicit column names ở nơi cần ổn định.

### Bước 4: Viết repository và query read model

- Derived query cho root property.
- @Query cho SQL rõ ràng.
- Fragment/NamedParameterJdbcTemplate cho JOIN, CTE, dynamic filtering và projection.
- DTO cho read-only screen/report.
- Repository load aggregate cho command.

### Bước 5: Chuyển service từ dirty checking sang explicit save

Mẫu:

~~~text
JPA:
load managed entity
  → change fields
  → transaction flush

Spring Data JDBC:
load aggregate
  → execute domain method
  → repository.save(aggregate)
  → transaction commit
~~~

Kiểm tra immutable entity: dùng instance trả về từ save để nhận generated ID/version.

### Bước 6: Chuyển transaction và locking

Đặt @Transactional ở use case. Giữ cùng DataSource/transaction manager cho repository và JdbcTemplate. Chuyển optimistic locking sang @Version hoặc chiến lược conditional update/row lock phù hợp.

### Bước 7: Chuyển callbacks/auditing và side effects

Thay JPA entity listeners bằng Spring Data entity callbacks/lifecycle events khi phù hợp. Chuyển domain rule vào aggregate/service. Side effect sau commit dùng outbox hoặc transactional event listener.

### Bước 8: Chạy test theo database thật

Test insert/load/update/delete aggregate, collection, reference, converter, version, query, transaction rollback và concurrency. Dùng Testcontainers nếu production database có behavior đặc thù.

### Bước 9: Triển khai theo module/use case

Chọn một aggregate ít phụ thuộc làm pilot. Chuyển read path hoặc một bounded context trước, theo dõi SQL, latency, lock contention và pool. Chỉ mở rộng khi các test và behavior đã ổn định.

## 16. Ví dụ chuyển một use case hoàn chỉnh

### Phiên bản JPA

~~~java
@Entity
class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    private String status;

    @OneToMany(mappedBy = "order",
               cascade = CascadeType.ALL,
               orphanRemoval = true)
    private List<OrderLine> lines = new ArrayList<>();

    public void addLine(OrderLine line) {
        lines.add(line);
        line.setOrder(this);
    }

    public void markPaid() {
        status = "PAID";
    }
}

@Service
class OrderService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void pay(Long id) {
        PurchaseOrder order =
                entityManager.find(PurchaseOrder.class, id);

        order.markPaid();

        // Không cần save; managed entity được dirty checking.
    }
}
~~~

### Phiên bản Spring Data JDBC

~~~java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    @Version
    private Long version;

    private String status;

    @MappedCollection(idColumn = "order_id", keyColumn = "line_no")
    private List<OrderLine> lines = new ArrayList<>();

    public void addLine(OrderLine line) {
        lines.add(line);
    }

    public void markPaid() {
        if (lines.isEmpty()) {
            throw new IllegalStateException(
                    "Cannot pay an order without lines"
            );
        }
        status = "PAID";
    }
}

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}

@Service
public class OrderService {

    private final PurchaseOrderRepository repository;

    public OrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public PurchaseOrder pay(Long id) {
        PurchaseOrder order = repository.findById(id)
                .orElseThrow(() -> new OrderNotFoundException(id));

        order.markPaid();

        return repository.save(order);
    }
}
~~~

Thay đổi không chỉ là gọi save. Mô hình mới:

- Không có back-reference từ OrderLine đến PurchaseOrder.
- OrderLine thuộc aggregate PurchaseOrder.
- Product/Customer nếu có là reference theo ID.
- Không có lazy loading.
- Không có dirty checking.
- Version được kiểm tra khi save.
- Transaction boundary vẫn bao trùm use case.

## 17. Kiểm thử regression khi chuyển từ JPA

Cần kiểm thử các behavior trước đây Hibernate âm thầm cung cấp:

| Behavior JPA cũ | Regression test cho Spring Data JDBC |
|---|---|
| Dirty checking | Thay đổi object nhưng không save phải không ghi DB; có save phải ghi DB |
| Cascade persist | Save root tạo owned rows đúng |
| orphanRemoval | Bỏ child khỏi collection và save root cho kết quả xóa đúng theo mapping |
| Lazy loading | Use case mới truy vấn rõ dữ liệu liên quan; không có query ngầm |
| Bidirectional association | Root/child mapping đúng và không cần back-reference |
| @Version | Hai transaction cập nhật đồng thời; transaction stale bị phát hiện |
| Entity callbacks | Callback JDBC chạy đúng persistence path |
| JPQL/fetch join | Query mới trả đúng DTO/root và không có N+1 |
| EntityManager.merge | Command tải aggregate hiện tại rồi save; stale object không được merge mù |
| Schema generation | Migration tạo schema tương thích production |

### Test chứng minh không có dirty checking

~~~java
@Test
void changingLoadedObjectWithoutSaveDoesNotPersist() {
    PurchaseOrder order = repository.findById(existingId).orElseThrow();
    order.changeStatus("PAID");

    PurchaseOrder reloaded = repository.findById(existingId).orElseThrow();

    assertThat(reloaded.getStatus()).isNotEqualTo("PAID");
}

@Test
void changingLoadedObjectAndSavingPersists() {
    PurchaseOrder order = repository.findById(existingId).orElseThrow();
    order.changeStatus("PAID");

    repository.save(order);

    PurchaseOrder reloaded = repository.findById(existingId).orElseThrow();

    assertThat(reloaded.getStatus()).isEqualTo("PAID");
}
~~~

Test đầu xác nhận object Java không được framework quản lý sau khi repository trả về. Test thứ hai xác nhận save là thao tác persistence tường minh.

### Test aggregate ownership

- Lưu root có hai child; kiểm tra FK child trỏ đúng root.
- Bỏ một child khỏi collection rồi save; xác nhận row tương ứng được xử lý đúng.
- Xóa root; xác nhận owned rows được xử lý và FK không vi phạm.
- Tham chiếu Customer/Product không tự cascade delete sang aggregate đó.
- Kiểm tra direct SQL và migration không tạo orphan rows.

## 18. Những lỗi thường gặp khi chuyển từ JPA

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Sửa field nhưng DB không đổi | Dựa vào dirty checking JPA | Gọi repository.save aggregate |
| Save detached object gây dữ liệu bất ngờ | Coi save như EntityManager.merge | Tải aggregate hiện tại và áp dụng command |
| Không truy cập được relation lazy | Spring Data JDBC không tạo lazy proxy | Query reference rõ ràng hoặc dùng DTO JOIN |
| Nhiều query trong vòng lặp | Tự tạo N+1 ở service | Batch query/projection/JOIN |
| Cascade xóa Customer ngoài ý muốn | Chuyển cascade JPA không xét ownership | Customer là aggregate riêng; xóa qua use case riêng |
| Child không được lưu | Collection không nằm trong aggregate mapping hoặc FK/key column sai | Kiểm tra @MappedCollection và DDL |
| Child bị ghi lại nhiều hơn dự kiến | Save xử lý aggregate như đơn vị, không dirty-check từng child như Hibernate | Đo SQL; đánh giá trigger/audit/generated ID |
| Assigned ID bị coi là entity cũ | Newness detection dựa vào ID/version | Dùng @Version/Persistable hoặc ID generation phù hợp |
| Query theo field của aggregate khác không hoạt động | Derived query JDBC không tự JOIN | Dùng @Query hoặc repository fragment |
| @Version không tăng khi MyBatis/direct SQL ghi | Đường ghi bỏ qua Spring Data JDBC lifecycle | Tự kiểm tra và tăng version |
| Callback JPA không chạy | JPA listener không còn trong runtime | Triển khai EntityCallback tương ứng |
| Schema tự tạo khác mapping | Dựa vào Hibernate DDL generation hoặc naming strategy khác | Quản lý migration và mapping tường minh |
| Test H2 pass, production fail | Dialect/driver/locking khác nhau | Testcontainers với database production |

## 19. Checklist quyết định trước khi chuyển một aggregate

1. **Ai sở hữu dữ liệu?** Xác định aggregate root và owned entities.
2. **Quan hệ nào chỉ là reference?** Lưu ID/AggregateReference, không cascade lifecycle qua aggregate khác.
3. **Code có dựa dirty checking không?** Tìm mọi mutation không gọi save.
4. **Có detached merge không?** Thay bằng load-current → apply-command → save.
5. **Có lazy loading không?** Thiết kế query/projection tường minh.
6. **Có cascade/orphanRemoval không?** Chuyển thành ownership rule và kiểm thử child lifecycle.
7. **Có @Version không?** Map cột version và test stale updates.
8. **Có entity listeners/auditing không?** Chuyển callback hoặc application logic.
9. **Có JPQL/fetch join không?** Viết SQL/query fragment/DTO phù hợp.
10. **Có schema generation không?** Chuyển sang versioned migration.
11. **Có assigned ID/custom type không?** Kiểm tra newness detection và converter.
12. **Có transaction dài hoặc network call không?** Rút gọn transaction và tách side effects.
13. **Có nhiều writer không?** Quy định write ownership, version và cache invalidation.
14. **Đã có regression test trên database thật chưa?** Kiểm tra aggregate, query, transaction, concurrency và schema.

### Bảng quyết định nhanh

| JPA habit | Thay đổi khi dùng Spring Data JDBC |
|---|---|
| Tải managed entity rồi sửa | Tải aggregate, thay đổi, gọi save |
| EntityManager.merge detached graph | Dùng command/DTO, tải aggregate hiện tại, áp dụng thay đổi |
| Lazy association | Query reference hoặc read model rõ ràng |
| Bidirectional entity graph | Object graph một chiều từ aggregate root |
| Cascade qua nhiều entity | Phân biệt owned child và aggregate reference |
| orphanRemoval | Child thuộc aggregate; test persistence khi bỏ child |
| JPQL/Criteria/fetch join | Derived query, @Query SQL, repository fragment |
| Dirty checking/flush | Explicit repository/template calls trong transaction |
| JPA @Version | Spring Data JDBC @Version và optimistic locking |
| @PreUpdate/@PostLoad | Spring Data EntityCallback/lifecycle event phù hợp |
| Hibernate DDL auto | Flyway/Liquibase migration |
| EntityManager first-level cache | Không có persistence context; quản lý read/cache riêng |

**Điểm cốt lõi:** khi chuyển từ JPA sang Spring Data JDBC, hãy chuyển từ tư duy managed entity và association graph sang tư duy aggregate root, ownership và persistence tường minh. Tải aggregate, áp dụng domain behavior, save rõ ràng; dùng ID để tham chiếu aggregate khác; thay lazy loading bằng query/read model; thay cascade bằng ownership rule; và kiểm thử lại transaction, version, callback, schema cùng mọi behavior trước đây Hibernate tự cung cấp.

## Tài liệu tham khảo chính thức

- [Spring Data Relational — Domain Driven Design and Relational Persistence](https://docs.spring.io/spring-data/relational/reference/jdbc/domain-driven-design.html): aggregate root, aggregate boundary và cách Spring Data JDBC lưu aggregate.
- [Spring Data Relational — Object Mapping Fundamentals](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): mapping entity, @MappedCollection, @Embedded, AggregateReference, ID và version.
- [Spring Data Relational — Persisting Entities](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html): insert/update aggregate, lifecycle và entity callbacks.
- [Spring Data Relational — Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html): derived query, @Query, custom SQL và projection mapping.
- [Spring Data Relational — Transactionality](https://docs.spring.io/spring-data/relational/reference/jdbc/transactions.html): transaction boundary ở repository và service layer.
- [Jakarta Persistence — Entity Lifecycle](https://jakarta.ee/specifications/persistence/): lifecycle states, persistence context, entity manager và dirty checking contract.
- [Hibernate ORM User Guide — Persistence Context](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html): managed/detached entity, dirty checking, cascading và lazy loading.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): @Transactional, proxy và rollback rules.

