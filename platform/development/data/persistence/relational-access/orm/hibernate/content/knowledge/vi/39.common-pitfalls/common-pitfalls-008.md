# Thay equals, hashCode hoặc thuộc tính khóa khi thực thể đang nằm trong tập hợp

## 1. Một lỗi khó hiểu: entity đã nằm trong Set nhưng contains() trả về false

Hãy xem một entity có ID được database sinh tự động:

```java
@Entity
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String orderNumber;

    public Long getId() {
        return id;
    }
}
```

Một đoạn code thêm entity mới vào HashSet:

```java
Set<PurchaseOrder> orders = new HashSet<>();

PurchaseOrder order = new PurchaseOrder();
orders.add(order);

entityManager.persist(order);
entityManager.flush();

boolean found = orders.contains(order);
```

Nếu entity định nghĩa hashCode() dựa trực tiếp vào ID, giá trị hash có thể thay đổi khi Hibernate/database cấp ID. Object vẫn nằm trong bucket cũ của HashSet, trong khi contains() tính hash mới và tìm ở bucket khác. Kết quả có thể là false dù chính object đó vẫn đang nằm trong Set.

Một tình huống khác là entity dùng orderNumber làm equals/hashCode. Khi entity đã nằm trong Set, code đổi orderNumber. Hash code thay đổi và Set không còn tìm thấy object theo cách thông thường.

Đây là lỗi liên quan đến **hợp đồng equals/hashCode của Java Collections** và vòng đời entity của Hibernate. Nó không đơn thuần là một lỗi SQL.

## 2. Hợp đồng equals() và hashCode() của Java

Java yêu cầu hai method này tuân theo các quy tắc:

### equals()

- Phản xạ: object phải bằng chính nó.
- Đối xứng: nếu A bằng B thì B phải bằng A.
- Bắc cầu: nếu A bằng B và B bằng C thì A bằng C.
- Nhất quán: kết quả không tự thay đổi khi thông tin dùng để so sánh không thay đổi.
- So sánh với null phải trả về false.

### hashCode()

- Nếu hai object bằng nhau theo equals(), hashCode của chúng phải bằng nhau.
- Hai object không bằng nhau có thể có cùng hash code.
- Hash code cần ổn định trong khoảng thời gian các thông tin dùng để tính hash không thay đổi.

Điểm đặc biệt quan trọng với entity: **một field được dùng trong equals/hashCode không nên thay đổi trong khi object đang là phần tử của hash-based collection**.

## 3. HashSet hoạt động như thế nào?

HashSet thường sử dụng hash code để xác định vùng/bucket chứa phần tử, rồi dùng equals() để tìm phần tử tương ứng trong vùng đó.

Mô hình đơn giản:

```text
orders.add(order)
      |
      v
hash = order.hashCode()
      |
      v
bucket = spread(hash) & tableMask
      |
      v
Lưu object vào bucket đó

orders.contains(order)
      |
      v
Tính hashCode() hiện tại
      |
      v
Tìm bucket tương ứng
      |
      v
So sánh equals()
```

Giả sử hash code thay đổi:

```text
Lúc add:
  id = null
  hashCode = 17
  object nằm ở bucket 17

Sau persist:
  id = 501
  hashCode = 501

Lúc contains:
  tìm bucket 501
  object vẫn ở bucket 17
  không tìm thấy
```

Các con số chỉ minh họa. HashSet không tự di chuyển phần tử khi một field của object thay đổi.

## 4. Vì sao entity Hibernate dễ gặp lỗi này?

Entity có vòng đời dài hơn một object DTO thông thường. Một entity có thể:

1. Được tạo mới ở trạng thái transient.
2. Được đưa vào một collection trong bộ nhớ.
3. Được persist và nhận generated identifier.
4. Trở thành managed.
5. Được detach khi Session/EntityManager đóng hoặc clear.
6. Được merge vào một Persistence Context khác.
7. Được tải lại thành instance Java khác nhưng đại diện cùng một database row.

Trong những giai đoạn này, các field có thể được gán hoặc thay đổi. Nếu equals/hashCode dựa trên field thay đổi theo lifecycle, Java collection có thể hoạt động sai.

Ngoài ra, Hibernate có thể dùng proxy và persistent collection để quản lý lazy loading, nên việc so sánh entity cần tính đến proxy class và trạng thái managed/detached.

## 5. Lỗi 1: hashCode dựa trên generated ID

Một cách cài đặt dễ gặp:

```java
@Override
public boolean equals(Object other) {
    if (this == other) {
        return true;
    }
    if (!(other instanceof PurchaseOrder that)) {
        return false;
    }
    return Objects.equals(id, that.id);
}

@Override
public int hashCode() {
    return Objects.hash(id);
}
```

Khi entity mới chưa được persist:

```text
id = null
hashCode = hash(null)
```

Sau khi Hibernate/database cấp ID:

```text
id = 501
hashCode = hash(501)
```

Nếu entity đã nằm trong HashSet trước thời điểm đó, hash code thay đổi và bucket cũ không còn khớp.

### Ví dụ tái hiện

```java
Set<PurchaseOrder> orders = new HashSet<>();

PurchaseOrder order = new PurchaseOrder();
orders.add(order);

int hashBefore = order.hashCode();

entityManager.persist(order);
entityManager.flush();

int hashAfter = order.hashCode();

System.out.println(hashBefore);
System.out.println(hashAfter);
System.out.println(orders.contains(order));
```

Nếu hashBefore khác hashAfter, kết quả contains() có thể false. Không phải mọi implementation hash-based collection đều biểu hiện giống hệt ở mọi kích thước/capacity, nhưng vi phạm hợp đồng ổn định hash khiến hành vi không còn đáng tin.

## 6. Lỗi 2: equals/hashCode dựa trên field nghiệp vụ có thể thay đổi

Ví dụ:

```java
@Override
public boolean equals(Object other) {
    if (this == other) {
        return true;
    }
    if (!(other instanceof Customer that)) {
        return false;
    }
    return Objects.equals(email, that.email);
}

@Override
public int hashCode() {
    return Objects.hash(email);
}
```

Email có thể thay đổi:

```java
Set<Customer> customers = new HashSet<>();

Customer customer = new Customer("old@example.test");
customers.add(customer);

customer.changeEmail("new@example.test");

boolean found = customers.contains(customer);
```

Nếu email là thành phần hash, object có thể vẫn nằm ở bucket cũ. Việc thay đổi email còn có thể làm thay đổi kết quả equals với những object khác.

Các field thường không phù hợp làm equality key nếu có thể thay đổi:

- Tên hiển thị.
- Email có thể sửa.
- Trạng thái đơn hàng.
- Địa chỉ.
- Số điện thoại.
- Mô tả.
- Giá trị tổng tiền.
- Timestamp cập nhật.

Một field chỉ nên làm natural key khi domain bảo đảm tính duy nhất và bất biến theo thời gian sống của entity.

## 7. Vì sao lỗi có thể ảnh hưởng quan hệ @OneToMany Set?

Một mapping phổ biến:

```java
@Entity
public class PurchaseOrder {

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private Set<OrderLine> lines = new HashSet<>();

    public void addLine(OrderLine line) {
        lines.add(line);
        line.setOrder(this);
    }

    public void removeLine(OrderLine line) {
        lines.remove(line);
        line.setOrder(null);
    }
}
```

Nếu OrderLine.hashCode() dựa vào generated ID, một line có thể được thêm vào Set khi ID còn null, rồi nhận ID khi persist. Sau đó:

```java
order.removeLine(line);
```

có thể không loại được phần tử khỏi HashSet vì hash code đã thay đổi.

Hệ quả:

- remove() trả về false dù phần tử nhìn thấy khi duyệt Set.
- contains() trả về false.
- Collection có thể vẫn giữ phần tử không mong muốn.
- Code domain nghĩ rằng đã xóa child nhưng collection chưa thay đổi.
- Với orphanRemoval, Hibernate có thể không nhận được thay đổi collection như mong đợi.
- Việc đồng bộ owning side/inverse side có thể trở nên không nhất quán.

Không kết luận rằng mọi lỗi hash đều chắc chắn sinh SQL sai theo cùng một cách; kết quả persistence phụ thuộc collection snapshot, mapping và chuỗi thao tác. Điều chắc chắn là collection semantics trong Java đã bị vi phạm, nên không thể tin cậy kết quả add/remove/contains.

## 8. PersistentSet của Hibernate không sửa được hashCode sai

Khi một association được map thành Set, Hibernate có thể bọc collection bằng implementation như PersistentSet để hỗ trợ lazy loading, dirty checking và snapshot.

Persistent collection vẫn phải tuân theo semantics của Set/Java object equality. Nó không thể tự đoán rằng entity đã đổi business key hay generated ID và tự di chuyển mọi object đến bucket mới một cách an toàn.

Vì vậy:

- Đừng kỳ vọng Hibernate tự sửa hash code sau persist.
- Đừng coi PersistentSet là một collection có thể bỏ qua hợp đồng equals/hashCode.
- Đừng dùng mutable fields làm equality key chỉ vì collection được Hibernate quản lý.
- Hãy giữ equality key ổn định trong suốt thời gian entity tham gia Set.

## 9. Chiến lược 1: dùng natural key bất biến

Nếu domain có một khóa nghiệp vụ:

- Duy nhất trong phạm vi domain hoặc tenant.
- Được gán ngay khi tạo entity.
- Không thay đổi sau khi tạo.
- Có semantics rõ ràng trong domain.

thì có thể dùng key đó cho equals/hashCode.

Ví dụ một mã external reference bất biến trong phạm vi tenant:

```java
@Entity
public class ExternalOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @Column(name = "tenant_id", nullable = false, updatable = false)
    private String tenantId;

    @Column(name = "external_reference",
            nullable = false, updatable = false)
    private String externalReference;

    protected ExternalOrder() {}

    public ExternalOrder(String tenantId, String externalReference) {
        this.tenantId = tenantId;
        this.externalReference = externalReference;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof ExternalOrder that)) {
            return false;
        }
        return Objects.equals(tenantId, that.tenantId)
            && Objects.equals(externalReference, that.externalReference);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenantId, externalReference);
    }
}
```

Trong ví dụ này, key được gán trước khi entity được thêm vào Set và không thay đổi khi ID database được cấp.

### Cần unique constraint ở database

```java
@Table(
    uniqueConstraints = @UniqueConstraint(
        name = "uk_external_order_tenant_reference",
        columnNames = {"tenant_id", "external_reference"}
    )
)
```

Equality trong Java không thay thế unique constraint. Hai transactions đồng thời vẫn có thể tạo cùng key; database constraint mới là lớp bảo vệ cuối cùng.

### Khi nào natural key không phù hợp?

Nếu key có thể sửa, có thể null khi tạo, chỉ duy nhất sau một workflow dài, hoặc chỉ duy nhất trong một phạm vi chưa có trong equality, không nên dùng nó một cách máy móc.

Ví dụ email không phải natural key tốt nếu người dùng có thể đổi email.

## 10. Chiến lược 2: dùng generated ID nhưng giữ hashCode ổn định

Trong nhiều domain, database-generated surrogate ID là khóa định danh tự nhiên của entity, nhưng nó chỉ xuất hiện sau khi persist.

Một chiến lược phổ biến:

- Hai references giống hệt nhau thì bằng nhau.
- Hai entity khác instance chỉ bằng nhau khi cùng persistent entity type và cùng ID không null.
- Entity mới với ID null chỉ bằng chính nó.
- hashCode không phụ thuộc ID có thể thay đổi; nó ổn định theo entity type.

Mẫu minh họa Hibernate-specific có xử lý proxy:

```java
import org.hibernate.proxy.HibernateProxy;

private static Class<?> persistentClass(Object object) {
    if (object instanceof HibernateProxy proxy) {
        return proxy.getHibernateLazyInitializer().getPersistentClass();
    }
    return object.getClass();
}

@Override
public boolean equals(Object other) {
    if (this == other) {
        return true;
    }
    if (other == null || persistentClass(this) != persistentClass(other)) {
        return false;
    }

    PurchaseOrder that = (PurchaseOrder) other;
    return getId() != null && getId().equals(that.getId());
}

@Override
public int hashCode() {
    return persistentClass(this).hashCode();
}
```

Đây là một mẫu tham khảo cho entity đơn giản không có equality polymorphism qua nhiều subclass. Cần kiểm tra inheritance strategy, proxy behavior và accessors của model thực tế trước khi dùng nguyên mẫu.

### Vì sao hashCode không phụ thuộc ID?

Với entity mới:

```text
id = null
hashCode = hash(entity type)
```

Sau persist:

```text
id = 501
hashCode = hash(entity type)
```

Hash code không đổi khi generated ID được cấp. Vì vậy object không bị mất bucket chỉ vì ID chuyển từ null sang giá trị mới.

### Đổi lại có nhiều hash collisions hơn

Các entity cùng persistent class có cùng hash code theo mẫu này. Với HashSet rất lớn, điều đó có thể làm lookup kém hiệu quả hơn so với hash phân tán.

Đây là trade-off: hash ổn định qua lifecycle quan trọng hơn phân bố hash hoàn hảo đối với các entity thường được dùng trong association sets có kích thước vừa phải. Nếu collection chứa hàng trăm nghìn entity, cần đo và xem lại mô hình dữ liệu/collection.

### Lưu ý về proxy

Hibernate lazy proxy có thể là subclass runtime của entity. So sánh getClass() trực tiếp có thể làm entity thật và proxy cùng row bị xem là khác class.

Mẫu trên dùng HibernateProxy metadata để lấy persistent class mà không dựa vào proxy subclass. Đây là Hibernate-specific và gắn với proxy implementation; nếu cần portable JPA, cân nhắc immutable natural key hoặc một strategy phù hợp với proxy/provider đang dùng.

Không gọi getter của field lazy bất kỳ trong equals/hashCode. Việc so sánh không nên vô tình tải toàn bộ association graph hoặc phát SQL không mong đợi.

## 11. Một biến thể đơn giản với instanceof: khi nào có thể dùng?

Với entity không có inheritance phức tạp, một số dự án dùng:

```java
@Override
public boolean equals(Object other) {
    if (this == other) {
        return true;
    }
    if (!(other instanceof PurchaseOrder that)) {
        return false;
    }
    return getId() != null && getId().equals(that.getId());
}

@Override
public int hashCode() {
    return PurchaseOrder.class.hashCode();
}
```

Ưu điểm:

- Proxy là subclass có thể thỏa instanceof.
- hashCode ổn định trước/sau khi ID được cấp.
- Không cần truy cập proxy runtime class.

Nhưng instanceof có thể làm equality giữa base class và subclass trở nên phức tạp. Nếu subclass bổ sung thuộc tính equality, tính đối xứng/bắc cầu có thể bị phá vỡ.

Chỉ dùng khi entity hierarchy có semantics rõ. Với inheritance, hãy quyết định entity type nào được phép so sánh bằng nhau và viết tests cho base/subclass/proxy.

## 12. Chiến lược 3: application-assigned UUID ổn định từ lúc tạo

Một lựa chọn khác là tạo UUID ngay khi khởi tạo entity, trước khi đưa vào Set:

```java
@Entity
public class Shipment {

    @Id
    private UUID id;

    protected Shipment() {}

    public Shipment() {
        this.id = UUID.randomUUID();
    }

    public UUID getId() {
        return id;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof Shipment that)) {
            return false;
        }
        return id.equals(that.id);
    }

    @Override
    public int hashCode() {
        return id.hashCode();
    }
}
```

Trong ví dụ, ID được tạo ở application constructor và không đổi trong lifecycle. Hash code ổn định khi thêm entity vào Set trước persist.

Đây là assigned identifier. Mapping, schema, constructor và ORM access strategy phải hỗ trợ cách tạo ID này.

### Không nhầm với UUID chỉ được cấp lúc persist

Nếu provider chỉ gán UUID khi persist, object vẫn có thể có ID null lúc được thêm vào Set. Khi đó vấn đề hash thay đổi vẫn tồn tại nếu hash dựa trên ID.

Điểm quyết định là **identifier phải có trước thời điểm entity tham gia hash collection** và không đổi sau đó.

## 13. Không dùng database ID như mutable business property

Primary key định danh row. Thay đổi primary key của một entity đã persistent thường là thao tác phức tạp và không nên dùng như một cách đổi danh tính.

Nếu business key thay đổi:

- Giữ surrogate primary key ổn định.
- Cập nhật business field như một thuộc tính riêng.
- Không dùng business field mutable trong equals/hashCode.
- Nếu cần danh tính mới theo domain, tạo entity mới hoặc thực hiện workflow chuyển đổi rõ ràng.

Không sửa ID để “làm Set nhận ra object khác”.

## 14. Composite key: equals/hashCode phải dựa trên toàn bộ key

Với composite primary key, key class phải triển khai equals/hashCode theo các thành phần khóa.

Ví dụ:

```java
@Embeddable
public class OrderLineId implements Serializable {

    private Long orderId;
    private Integer lineNumber;

    protected OrderLineId() {}

    public OrderLineId(Long orderId, Integer lineNumber) {
        this.orderId = orderId;
        this.lineNumber = lineNumber;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof OrderLineId that)) {
            return false;
        }
        return Objects.equals(orderId, that.orderId)
            && Objects.equals(lineNumber, that.lineNumber);
    }

    @Override
    public int hashCode() {
        return Objects.hash(orderId, lineNumber);
    }
}
```

Các thành phần composite key nên được thiết lập trước khi key được dùng trong Set/Map và không thay đổi sau khi entity persistent.

### Tránh association mutable trong primary key

Đừng đưa toàn bộ entity association hoặc một thuộc tính có thể đổi vào equals/hashCode của ID class. Composite key cần là value identity ổn định, phù hợp với database primary key semantics.

Với @IdClass, key class cũng phải có equals/hashCode nhất quán với các thành phần khóa của entity.

## 15. @NaturalId có giải quyết được equals/hashCode không?

Hibernate cung cấp @NaturalId để đánh dấu natural identifier của entity:

```java
@NaturalId
@Column(nullable = false, updatable = false, unique = true)
private String externalCode;
```

Annotation giúp Hibernate hiểu thuộc tính natural ID cho một số tính năng như natural-id loading/cache. Nhưng:

- @NaturalId không tự sinh equals/hashCode cho entity.
- Nó không tự bảo đảm business field thực sự bất biến ở mọi đường code.
- Unique constraint vẫn nên được bảo vệ ở database.
- Nếu natural ID có thể thay đổi, cần cấu hình/thiết kế mutable natural ID có chủ đích và hiểu cache behavior.

Đừng xem thêm @NaturalId là đủ để sửa lỗi HashSet. Equality contract vẫn do entity code quyết định.

## 16. Lombok @Data có thể tạo ra equals/hashCode nguy hiểm

Một entity:

```java
@Data
@Entity
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    private String email;

    @OneToMany(mappedBy = "customer")
    private Set<PurchaseOrder> orders = new HashSet<>();
}
```

Lombok @Data thường sinh getter, setter, toString, equals và hashCode dựa trên fields theo cấu hình Lombok. Điều này có thể đưa vào equality:

- Generated ID thay đổi sau persist.
- Email có thể thay đổi.
- Collection association có thể thay đổi theo thời gian.
- Quan hệ hai chiều có thể gây recursion khi equals/toString.
- Lazy associations có thể bị truy cập ngoài ý muốn.

### Cách khai báo có chủ đích hơn

```java
@Getter
@Setter
@Entity
@EqualsAndHashCode(onlyExplicitlyIncluded = true)
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    @EqualsAndHashCode.Include
    @Column(nullable = false, updatable = false, unique = true)
    private String customerCode;

    @OneToMany(mappedBy = "customer")
    private Set<PurchaseOrder> orders = new HashSet<>();
}
```

Ví dụ chỉ phù hợp nếu customerCode thật sự immutable và unique. Nếu dùng generated ID, cần strategy hash ổn định và proxy-aware như phần trước; đừng chỉ thêm Include lên id rồi mặc định đã an toàn.

## 17. equals/hashCode không nên đi qua association

Một anti-pattern:

```java
@Override
public int hashCode() {
    return Objects.hash(id, customer, lines);
}
```

Association có thể:

- Lazy và chưa được load.
- Thay đổi sau khi entity được thêm vào Set.
- Có quan hệ hai chiều tạo vòng lặp.
- Tải thêm nhiều rows khi equals/hashCode chạy.
- Có hashCode riêng không ổn định.

Vì vậy entity equality thường nên dựa vào identifier hoặc natural key đơn giản, ổn định; tránh toàn bộ object graph.

## 18. Vì sao không nên dùng mọi field trong @EqualsAndHashCode?

Một DTO thường có thể so sánh theo toàn bộ field vì nó là snapshot value. Entity có identity và lifecycle khác:

| DTO/value object | Entity |
|---|---|
| Giá trị thường bất biến | State có thể thay đổi |
| Equality theo value là tự nhiên | Equality theo identity/domain key |
| Không có Persistence Context | Có managed/detached lifecycle |
| Không có proxy ORM | Có thể được đại diện bởi proxy |
| Không có cascade/association lifecycle | Có graph và relationship semantics |

Không áp dụng máy móc cách equals/hashCode của DTO cho entity.

## 19. Nếu cần đổi key khi entity đang nằm trong Set thì làm gì?

Phương án tốt nhất là thiết kế key bất biến để không phải đổi. Nếu một field thực sự là equality key và domain bắt buộc thay đổi, có thể cân nhắc:

1. Xác định chính xác Set nào đang chứa entity.
2. Remove entity khỏi mọi hash-based collections trước khi đổi key.
3. Thay đổi key trong transaction/domain operation.
4. Thêm entity lại sau khi key ổn định.
5. Đồng bộ owning side và inverse side.
6. Flush và kiểm tra kết quả persistence.

Ví dụ thuần Java:

```java
if (!customers.remove(customer)) {
    throw new IllegalStateException("Customer was not in the set");
}

customer.changeNaturalKey(newKey);
customers.add(customer);
```

Nhưng cách này chỉ an toàn nếu remove thành công trước mutation, mọi collection liên quan đều được xử lý và domain cho phép thay key. Nếu hash code đã thay đổi từ trước, remove() có thể thất bại; khi đó không thể trông chờ thao tác này tự khôi phục collection.

Với JPA association Set và orphanRemoval, remove rồi add có thể tạo collection changes mà Hibernate diễn giải theo lifecycle. Cần test mapping/SQL thực tế trước khi dùng như một giải pháp thường xuyên.

## 20. Khi nào dùng List thay cho Set?

Set thể hiện semantics phần tử không trùng theo equals/hashCode. Nếu domain không cần uniqueness theo equality:

```java
@OneToMany(mappedBy = "order")
private List<OrderLine> lines = new ArrayList<>();
```

List không dựa vào hash bucket để tìm phần tử. Thay đổi hashCode không làm phần tử “mất bucket”.

Tuy nhiên List vẫn có các vấn đề riêng:

- Có thể chứa duplicate.
- remove(Object) vẫn dùng equals().
- Thứ tự có thể trở thành semantics cần duy trì.
- Hibernate có thể cần @OrderColumn nếu vị trí phải lưu xuống DB.

Đổi Set sang List không phải cách chữa mọi lỗi equals/hashCode. Nó chỉ phù hợp nếu domain thực sự cho phép collection có thứ tự/duplicate semantics tương ứng.

## 21. Map key cũng chịu cùng rủi ro

Ví dụ:

```java
Map<PurchaseOrder, String> labels = new HashMap<>();
labels.put(order, "Priority");

entityManager.persist(order);
entityManager.flush();

String label = labels.get(order);
```

Nếu hashCode của Order thay đổi sau khi ID được cấp, Map có thể không tìm thấy entry.

Rủi ro tương tự xuất hiện khi:

- Entity làm key của HashMap.
- Entity làm phần tử HashSet.
- Entity nằm trong HashMap/HashSet lồng nhau.
- Entity nằm trong cache tự viết có key là object.

Ưu tiên dùng immutable scalar key (UUID, immutable business code) làm key của Map nếu phù hợp.

## 22. TreeSet không dùng hashCode nhưng vẫn có thể bị hỏng khi key thay đổi

TreeSet dùng comparator/natural ordering để đặt phần tử trong cây. Nếu comparator phụ thuộc một field mutable và field đó đổi sau khi add:

```java
Set<Customer> customers = new TreeSet<>(
    Comparator.comparing(Customer::getEmail)
);

customers.add(customer);
customer.changeEmail("new@example.test");
```

Cấu trúc cây vẫn phản ánh vị trí cũ. contains/remove có thể tìm theo đường đi không còn khớp.

Ngoài ra comparator có thể coi hai customers khác nhau là bằng nhau nếu cùng email; TreeSet khi đó chỉ giữ một phần tử theo comparator semantics, dù equals() nói chúng khác nhau.

Quy tắc tương tự: field dùng trong comparator/natural ordering không nên thay đổi khi object đang ở sorted collection.

## 23. Entity equality khi có Hibernate proxy

Hibernate có thể trả proxy cho association lazy hoặc getReference(). Proxy là một lớp runtime đại diện entity và có thể chưa tải state.

Ví dụ:

```java
PurchaseOrder reference =
    entityManager.getReference(PurchaseOrder.class, 100L);

PurchaseOrder loaded =
    entityManager.find(PurchaseOrder.class, 100L);
```

Hai biến có thể đại diện cùng database row nhưng runtime classes khác nhau:

```java
reference.getClass() != loaded.getClass()
```

Vì vậy implementation kiểu:

```java
if (getClass() != other.getClass()) {
    return false;
}
```

có thể làm proxy và entity thật không bằng nhau.

### Các hướng xử lý

- Dùng immutable natural key mà equality không cần truy cập lazy associations.
- Với Hibernate-specific equality, lấy persistent class từ proxy metadata.
- Với hierarchy đơn giản, cân nhắc instanceof và test rõ inheritance semantics.
- Tránh truy cập getters của lazy associations trong equals/hashCode.
- Test cả proxy-vs-proxy, proxy-vs-loaded entity và chiều ngược lại.

Không có một implementation equals/hashCode phù hợp mọi entity hierarchy. Phải xác định equality theo root entity type, subclass hay concrete persistent class.

## 24. Inheritance làm equality phức tạp hơn

Giả sử:

```java
@Entity
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class Payment {
    @Id
    private Long id;
}

@Entity
public class CardPayment extends Payment {
    private String lastFourDigits;
}

@Entity
public class BankTransfer extends Payment {
    private String bankReference;
}
```

Nếu equals dùng instanceof Payment và chỉ so ID, một CardPayment và BankTransfer khác loại nhưng cùng numeric ID có thể bị xem là bằng nhau. Nếu dùng getClass trực tiếp, proxy subclass lại có thể gây vấn đề.

Trước khi chọn strategy, xác định:

- Equality có được phép đi qua hierarchy không?
- ID có duy nhất trên toàn root hierarchy hay chỉ từng concrete table?
- Hai subclass khác nhau có thể cùng identifier value không?
- Proxy class được chuẩn hóa ra persistent class thế nào?

Với inheritance phức tạp, nên dùng một base-class equality strategy đã được test kỹ thay vì sao chép snippet từ entity không có inheritance.

## 25. Hai entity instance từ hai Session khác nhau có nên bằng nhau?

Ví dụ:

```java
PurchaseOrder first;
try (Session session = sessionFactory.openSession()) {
    first = session.find(PurchaseOrder.class, 100L);
}

PurchaseOrder second;
try (Session session = sessionFactory.openSession()) {
    second = session.find(PurchaseOrder.class, 100L);
}
```

Hai object khác reference nhưng đại diện cùng row.

Nếu entity equality dựa vào database identity, thường kỳ vọng:

```java
first != second
first.equals(second) == true
first.hashCode() == second.hashCode()
```

Đây là lý do identity-based equals/hashCode hữu ích khi entity đi qua nhiều Persistence Context, Set hoặc Map.

Nếu dùng Java object identity mặc định, hai instance khác nhau không bằng nhau dù cùng row. Điều đó có thể đúng với một số domain, nhưng cần chủ đích.

## 26. Generated ID strategy và thời điểm thêm vào collection

Nếu dùng generated ID làm equality key:

```java
Set<OrderLine> lines = new HashSet<>();
OrderLine line = new OrderLine();

lines.add(line);
entityManager.persist(line);
```

thời điểm ID được cấp phụ thuộc strategy:

- SEQUENCE có thể cấp identifier trước khi INSERT.
- IDENTITY thường cần INSERT để database cấp generated key.
- TABLE/custom generators có behavior riêng.

Nếu hashCode phụ thuộc ID, thời điểm hash đổi có thể khác nhau giữa environments hoặc database vendors.

Đừng viết test chỉ pass với H2 rồi cho rằng behavior ID timing giống production. Hãy dùng strategy và DB mục tiêu.

Giải pháp bền hơn là hash ổn định qua lifecycle hoặc immutable key có trước khi entity vào collection.

## 27. Collection snapshot và dirty checking

Hibernate quản lý collection state để phát hiện thay đổi khi flush. Với Set, equality/hash semantics góp phần vào việc xác định membership và so sánh snapshot.

Nếu entity đổi hash/equality key khi đã nằm trong collection:

- Java Set có thể không tìm được phần tử.
- remove/add có thể không biểu diễn thay đổi như dự định.
- Snapshot comparison có thể khó phản ánh thao tác domain.
- Cascade/orphan removal có thể nhận collection state khác kỳ vọng.

Khi debug, quan sát cả:

1. State của Java Set trước/sau thao tác.
2. Kết quả contains/remove.
3. Owning side và inverse side.
4. SQL INSERT/UPDATE/DELETE khi flush.
5. Rows thực tế sau reload.

Đừng chỉ xem log SQL mà bỏ qua collection trong memory, hoặc chỉ nhìn collection mà bỏ qua DB state.

## 28. Đồng bộ hai phía của quan hệ vẫn quan trọng

Với bidirectional association:

```java
public void addLine(OrderLine line) {
    lines.add(line);
    line.setOrder(this);
}

public void removeLine(OrderLine line) {
    lines.remove(line);
    line.setOrder(null);
}
```

Owning side thường là phía có foreign key (OrderLine.order trong ví dụ). Chỉ xóa khỏi inverse collection nhưng không cập nhật owning side có thể không tạo SQL như mong đợi.

Nếu remove() thất bại do hashCode đã đổi, cả hai phía có thể lệch:

- Collection parent vẫn chứa line.
- Child vẫn trỏ parent hoặc đã bị set null.
- Hibernate flush theo owning side/mapping có thể cho kết quả khác dự định.

Helper methods cần xử lý cả equality key stability và association synchronization.

## 29. Những điều không nên đưa vào equals/hashCode của entity

Thông thường nên tránh:

- Generated ID nếu hashCode sẽ đổi sau persist.
- Mutable business fields.
- Collections/associations.
- Lazy properties có thể kích hoạt SQL.
- Toàn bộ fields do Lombok @Data tự động chọn.
- Timestamp do database cập nhật.
- Status/amount thay đổi theo workflow.
- Field chỉ có giá trị sau callback/trigger.

Ưu tiên:

- Immutable natural key được domain bảo đảm.
- Assigned UUID tạo trước khi vào collection.
- Generated ID với hashCode ổn định và proxy-aware strategy phù hợp.

## 30. Test 1: hash code không đổi khi persist

Một regression test:

```java
@Test
void hashCodeRemainsStableWhenGeneratedIdIsAssigned() {
    PurchaseOrder order = new PurchaseOrder();
    Set<PurchaseOrder> orders = new HashSet<>();

    orders.add(order);
    int beforePersist = order.hashCode();

    entityManager.persist(order);
    entityManager.flush();

    int afterPersist = order.hashCode();

    assertThat(afterPersist).isEqualTo(beforePersist);
    assertThat(orders).contains(order);
    assertThat(orders.remove(order)).isTrue();
}
```

Test này chỉ phù hợp với strategy được thiết kế giữ hash ổn định qua ID assignment. Nó không yêu cầu mọi entity phải có cùng hash strategy; test phải phản ánh contract đã chọn.

## 31. Test 2: hai instance cùng database identity bằng nhau

```java
@Test
void sameDatabaseIdentityHasConsistentEquality() {
    PurchaseOrder created = new PurchaseOrder();
    entityManager.persist(created);
    entityManager.flush();
    Long id = created.getId();

    entityManager.clear();

    PurchaseOrder reloaded =
        entityManager.find(PurchaseOrder.class, id);

    assertThat(reloaded).isNotSameAs(created);
    assertThat(reloaded).isEqualTo(created);
    assertThat(reloaded.hashCode()).isEqualTo(created.hashCode());
}
```

Test này chứng minh detached/original và instance mới đại diện cùng row được so sánh nhất quán theo strategy.

## 32. Test 3: proxy và entity đã load

```java
@Test
void proxyAndLoadedEntityUseConsistentEquality() {
    PurchaseOrder order = new PurchaseOrder();
    entityManager.persist(order);
    entityManager.flush();
    Long id = order.getId();

    entityManager.clear();

    PurchaseOrder reference =
        entityManager.getReference(PurchaseOrder.class, id);

    entityManager.clear();

    PurchaseOrder loaded =
        entityManager.find(PurchaseOrder.class, id);

    assertThat(reference).isEqualTo(loaded);
    assertThat(loaded).isEqualTo(reference);
    assertThat(reference.hashCode()).isEqualTo(loaded.hashCode());
}
```

Đây là ví dụ ý tưởng. Cách giữ proxy reference qua clear và provider-specific initialization cần được kiểm tra theo Hibernate version; trong test thực tế, có thể tạo proxy và loaded object ở hai Persistence Context riêng để tránh assumptions về cùng context.

Điểm cần kiểm tra là tính đối xứng: proxy.equals(entity) và entity.equals(proxy).

## 33. Test 4: mutable display field không ảnh hưởng Set membership

```java
@Test
void changingNonKeyFieldDoesNotBreakSetMembership() {
    Customer customer = new Customer("C-100", "Old display name");
    Set<Customer> customers = new HashSet<>();

    customers.add(customer);
    int hashBefore = customer.hashCode();

    customer.rename("New display name");

    assertThat(customer.hashCode()).isEqualTo(hashBefore);
    assertThat(customers).contains(customer);
    assertThat(customers.remove(customer)).isTrue();
}
```

Test xác nhận field hiển thị không nằm trong equality/hash key.

## 34. Test 5: Set association và orphan removal

```java
@Test
void removingChildFromSetDeletesOrphan() {
    PurchaseOrder order = new PurchaseOrder();
    OrderLine line = new OrderLine("SKU-1");
    order.addLine(line);

    entityManager.persist(order);
    entityManager.flush();

    Long orderId = order.getId();
    Long lineId = line.getId();

    order.removeLine(line);
    assertThat(order.getLines()).doesNotContain(line);

    entityManager.flush();
    entityManager.clear();

    PurchaseOrder reloaded =
        entityManager.find(PurchaseOrder.class, orderId);

    assertThat(reloaded.getLines())
        .noneMatch(item -> item.getId().equals(lineId));
}
```

Test cần mapping cascade/orphanRemoval và helper methods đúng. Nó kiểm tra kết quả sau reload; nếu muốn chứng minh child row đã DELETE, có thể bổ sung JDBC count query.

## 35. Test 6: hai transient objects không bị coi là cùng entity

Nếu dùng generated ID strategy:

```java
@Test
void differentTransientEntitiesAreNotEqual() {
    PurchaseOrder first = new PurchaseOrder();
    PurchaseOrder second = new PurchaseOrder();

    assertThat(first).isNotEqualTo(second);
}
```

Nếu dùng natural key, test phải xác định behavior khi key chưa được gán hoặc bị trùng. Không cho phép hai transient entities với key null tự động bằng nhau chỉ vì Objects.equals(null, null) trả true.

## 36. Test 7: equality contract

Với ba instances đại diện cùng một row:

```java
assertThat(a).isEqualTo(a);
assertThat(a).isEqualTo(b);
assertThat(b).isEqualTo(a);
assertThat(b).isEqualTo(c);
assertThat(a).isEqualTo(c);

assertThat(a.hashCode()).isEqualTo(b.hashCode());
assertThat(b.hashCode()).isEqualTo(c.hashCode());
```

Kiểm tra thêm:

- So sánh với null.
- So sánh entity khác persistent type.
- So sánh subclass nếu có inheritance.
- Proxy và initialized entity.
- Transient entities có ID null.
- Detached instances từ Session khác.

Không chỉ test một chiều equals().

## 37. Checklist debug khi contains/remove thất bại

Khi Set không tìm được entity, kiểm tra theo thứ tự:

1. Ghi hashCode ngay sau add.
2. Ghi hashCode tại thời điểm contains/remove.
3. Xác định field nào thay đổi giữa hai thời điểm.
4. Xác định ID được cấp trước hay sau add.
5. Kiểm tra Lombok-generated equals/hashCode.
6. Kiểm tra association/collection có nằm trong equality không.
7. Kiểm tra proxy class và inheritance.
8. Kiểm tra entity có nằm trong nhiều Sets/Maps khác không.
9. Kiểm tra owning side và helper methods.
10. Flush, clear, reload rồi xác nhận DB state.

Không gọi clear() hoặc refresh() để chữa một HashSet bị hỏng. Hai API đó quản lý Persistence Context, không tái cấu trúc bucket của Java collection.

## 38. Migration từ equals/hashCode cũ

Một quy trình thay đổi an toàn:

### Bước 1: inventory

Tìm:

```bash
rg -n "equals\\(|hashCode\\(|@Data|@EqualsAndHashCode" src
rg -n "Set<|HashSet|Map<|HashMap|TreeSet" src
```

Xác định entity nào được dùng làm key/phần tử collection.

### Bước 2: xác định identity rule

Với từng entity:

- Natural key nào thực sự bất biến?
- ID được gán lúc nào?
- Có assigned ID hay generated ID?
- Có inheritance?
- Có Hibernate proxy?
- Entity có được dùng trong Set/Map association không?

### Bước 3: chọn một strategy

- Immutable natural key.
- Application-assigned immutable UUID.
- Generated ID với hashCode ổn định và equality proxy-aware.
- Java object identity nếu domain/test cho phép và không cần equality xuyên Persistence Context.

Không trộn nhiều strategy tùy hứng giữa các entity cùng hierarchy.

### Bước 4: kiểm tra associations

Review Set, Map, cascade, orphanRemoval, owning side và helper methods.

### Bước 5: test lifecycle

Test trước/sau persist, detach, merge, reload, proxy, key mutation và collection removal.

## 39. Có nên chỉ dùng object identity mặc định của Java?

Nếu không override equals/hashCode, Java dùng identity của object:

- Hai references cùng object thì bằng nhau.
- Hai instances khác nhau thì không bằng nhau, dù cùng database row.

Ưu điểm:

- Hash code không thay đổi do entity field.
- Không vô tình tải association trong equals/hashCode.
- Không phải quyết định proxy-aware database identity.

Nhược điểm:

- Hai Session tải cùng row sẽ cho hai objects không bằng nhau.
- Set/Map có thể chứa duplicate representations của cùng database entity.
- Detached và reloaded instances không có equality theo persistent identity.

Đây có thể là lựa chọn hợp lệ nếu collection chỉ chứa object instances trong một unit of work và không cần equality xuyên Session. Nhưng phải có chủ đích, không phải né vấn đề mà không hiểu semantics.

## 40. Một chiến lược theo từng trường hợp

| Tình huống | Hướng cân nhắc |
|---|---|
| Có natural key immutable, unique | Dùng natural key cho equals/hashCode |
| Generated ID, entity đi qua Set trước persist | Dùng hashCode ổn định qua lifecycle; equality theo ID khi ID non-null |
| UUID do application tạo trước khi add | Dùng UUID immutable làm identity |
| Assigned ID do business cung cấp | Đảm bảo key được gán trước và bất biến; kiểm soát uniqueness |
| Composite ID | equals/hashCode trên toàn bộ thành phần immutable |
| Entity inheritance/proxy | Strategy có persistent-class semantics và tests |
| Không cần uniqueness/equality theo identity | Cân nhắc List hoặc object identity |
| Sorted collection | Comparator dựa trên key ổn định |
| Entity làm Map key | Ưu tiên immutable scalar key nếu phù hợp |

Không có một snippet equals/hashCode duy nhất áp dụng an toàn cho mọi mapping. Hãy chọn theo identifier strategy, inheritance, proxy behavior và cách entity được dùng trong collection.

## 41. Những anti-pattern cần tránh

### Anti-pattern 1: hashCode thay đổi theo generated ID

```java
return Objects.hash(id);
```

Khi ID thay đổi sau add, bucket không còn khớp.

### Anti-pattern 2: dùng tất cả fields

```java
return Objects.hash(id, status, totalAmount, updatedAt, lines);
```

Field và association thay đổi làm equality/hash thay đổi, có thể tải lazy graph.

### Anti-pattern 3: Lombok @Data trên entity không kiểm soát

Generated equals/hashCode có thể bao gồm field mutable và association.

### Anti-pattern 4: so sánh getClass() trực tiếp mà không xét proxy

Proxy subclass và entity class có thể khác runtime class.

### Anti-pattern 5: equals dùng ID nhưng hashCode dùng business key

Vi phạm điều kiện hai object bằng nhau phải có cùng hash code.

### Anti-pattern 6: đổi primary key sau persist

Thay đổi persistent identity làm hỏng quan hệ và collection semantics.

### Anti-pattern 7: dùng email làm key dù email được phép đổi

Field không immutable không phù hợp làm equality key ổn định.

## 42. Bài thực hành 1: tái hiện lỗi generated ID

1. Tạo entity dùng IDENTITY.
2. Override equals/hashCode theo ID.
3. Add entity vào HashSet trước persist.
4. Ghi hashCode.
5. Persist/flush.
6. Ghi hashCode lần nữa.
7. Gọi contains/remove.
8. Giải thích bucket cũ không được di chuyển.

## 43. Bài thực hành 2: sửa bằng hashCode ổn định

1. Giữ equality theo persistent identity.
2. Đổi hashCode thành giá trị ổn định theo entity type.
3. Test trước/sau persist.
4. Test detached/reloaded instances cùng ID.
5. Test proxy equality hai chiều.
6. Test entity inheritance nếu có.

## 44. Bài thực hành 3: natural key bất biến

1. Chọn externalCode duy nhất trong tenant.
2. Gán code trong constructor/factory.
3. Không cung cấp setter thay đổi code.
4. Thêm unique constraint (tenant_id, external_code).
5. Implement equals/hashCode theo cả hai field.
6. Test Set membership sau khi generated ID được cấp.
7. Xác nhận cập nhật display name không đổi hash.

## 45. Bài thực hành 4: Hibernate proxy

1. Persist một entity.
2. Clear context.
3. Lấy reference bằng getReference().
4. Tải entity bằng find() ở context khác.
5. Kiểm tra equals theo cả hai chiều.
6. Kiểm tra hashCode bằng nhau.
7. Quan sát có lazy initialization/SQL phát ra không.
8. Lặp lại với subclass nếu entity có inheritance.

## 46. Bài thực hành 5: Set association và orphan removal

1. Tạo Order có Set<OrderLine>.
2. Add child trước persist.
3. Persist parent/child.
4. Flush.
5. Remove child bằng helper.
6. Kiểm tra remove trả true và Set không còn child.
7. Flush/clear/reload.
8. Xác minh child đã bị xóa theo orphanRemoval.

Thử lại với hashCode mutable để quan sát lỗi.

## 47. Bài thực hành 6: Lombok và equality

1. Tạo entity có @Data và collection association.
2. Quan sát generated equals/hashCode bằng delombok hoặc IDE.
3. Kiểm tra fields nào tham gia equality.
4. Thay bằng @Getter/@Setter và @EqualsAndHashCode có include rõ ràng.
5. Test không có recursion/lazy load ngoài ý muốn.

## 48. Câu hỏi tự kiểm tra

1. Vì sao HashSet cần hashCode ổn định khi object đang nằm trong Set?
2. Điều gì xảy ra nếu generated ID làm hashCode thay đổi sau add?
3. Vì sao contains() có thể false dù duyệt Set vẫn thấy object?
4. Vì sao mutable email không nên làm equality key nếu có thể sửa?
5. Java equals/hashCode contract yêu cầu điều gì?
6. Vì sao Hibernate entity có lifecycle khác DTO?
7. PersistentSet có tự sửa hashCode sai không?
8. Vì sao orphanRemoval có thể bị ảnh hưởng khi remove() thất bại?
9. Natural key cần những đặc điểm nào?
10. Unique constraint có thay thế equals/hashCode không?
11. Vì sao generated ID strategy không nên quyết định hash bucket?
12. Stable hash theo entity class có trade-off gì?
13. Vì sao hai transient entities có ID null không nên tự động bằng nhau?
14. Khi nào assigned UUID hữu ích?
15. Vì sao UUID phải được gán trước khi entity vào Set?
16. Vì sao composite ID cần equals/hashCode trên tất cả key fields?
17. Vì sao không nên đưa association vào equals/hashCode?
18. @NaturalId có tự implement equals/hashCode không?
19. Vì sao Lombok @Data nguy hiểm trên entity?
20. Vì sao getClass() trực tiếp có thể thất bại với proxy?
21. instanceof có rủi ro gì trong inheritance?
22. Hai entity instances từ hai Session cùng row có nên bằng nhau không?
23. TreeSet bị ảnh hưởng thế nào khi comparator key thay đổi?
24. Map key là entity có cùng rủi ro nào?
25. Vì sao clear() không chữa được HashSet bucket đã sai?
26. Khi nào List phù hợp hơn Set?
27. Vì sao phải cập nhật cả owning side và inverse side?
28. Cần test những trạng thái nào cho equals/hashCode entity?

**Gợi ý:** (1) bucket được xác định lúc add; (2) lookup sang bucket khác; (3) object còn ở bucket cũ; (4) hash/equality đổi; (5) reflexive, symmetric, transitive, consistent và equal objects cùng hash; (6) managed/detached/proxy; (7) không; (8) collection mutation không diễn ra như mong muốn; (9) unique, non-null, immutable; (10) không; (11) ID được cấp muộn; (12) collisions; (13) hai new objects khác identity; (14) identity có trước persistence; (15) tránh đổi hash sau add; (16) phản ánh DB key; (17) mutable/lazy/cyclic; (18) không; (19) bao gồm fields/associations mutable; (20) proxy subclass; (21) equality xuyên subclass có thể phá symmetry/transitivity; (22) tùy domain, thường có nếu dùng persistent identity; (23) vị trí cây không còn đúng; (24) mất bucket; (25) clear chỉ quản lý Persistence Context; (26) không cần uniqueness theo equality; (27) owning side điều khiển FK; (28) transient, managed, detached, proxy, cross-session và collection membership.

## 49. Nguyên tắc cần ghi nhớ

1. **Không thay đổi field dùng trong equals/hashCode khi entity đang nằm trong HashSet hoặc làm key của HashMap.**
2. **Generated ID thường được cấp sau khi entity được tạo.** Nếu hashCode dựa trực tiếp vào ID, hash có thể đổi sau persist và object bị mất khỏi bucket lookup.
3. **Field nghiệp vụ mutable như email, status, amount hoặc display name không phù hợp làm equality key ổn định.**
4. **Set association của Hibernate vẫn tuân theo Java Set semantics.** PersistentSet không thể sửa một equals/hashCode thiết kế sai.
5. **Natural key chỉ phù hợp khi duy nhất, có giá trị trước khi add và bất biến theo domain.**
6. **Với generated ID, cân nhắc hashCode ổn định qua lifecycle và equality theo ID khi ID đã có.** Test cả transient và persistent states.
7. **Application-assigned UUID có thể là identity ổn định** nếu được tạo trước khi entity vào collection và không bao giờ đổi.
8. **Composite key cần equals/hashCode trên toàn bộ thành phần key bất biến.**
9. **Không đưa collections, lazy associations hoặc mutable graph vào equals/hashCode.**
10. **Lombok @Data có thể tự đưa nhiều field không phù hợp vào equality.** Cấu hình include rõ ràng hoặc viết method có chủ đích.
11. **Hibernate proxy có thể khác runtime class với entity thật.** Equality cần xử lý proxy và inheritance theo strategy cụ thể.
12. **TreeSet cũng bị lỗi khi comparator key mutable.** Map/Set đều cần key ổn định.
13. **Khi remove child khỏi Set association, kiểm tra equality, hash và cả owning side.** Orphan removal chỉ hoạt động theo collection/mapping changes được Hibernate nhận diện.
14. **Không dùng clear()/refresh() để sửa collection bucket bị hỏng.** Đó là vấn đề của Java collection và equality contract.
15. **Viết tests cho lifecycle transitions, proxy, cross-Session identity và Set membership** để ngăn lỗi quay lại.

Entity có thể đổi trạng thái từ transient sang managed, detached rồi được tải lại trong Session khác. Nếu equals/hashCode dựa vào một field thay đổi trong các bước đó, Set và Map không thể bảo đảm lookup như mong đợi. Hãy chọn một identity key ổn định theo domain hoặc giữ hash code ổn định xuyên lifecycle, đồng thời kiểm tra proxy, inheritance và association semantics. Khi key cần thay đổi, thiết kế lại equality hoặc thao tác collection có chủ đích; đừng để một setter thông thường âm thầm làm hỏng cấu trúc collection.

### Tài liệu tham khảo chính thức

- [Java SE API — Object.equals() and hashCode()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Object.html)
- [Java SE API — HashSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HashSet.html)
- [Java SE API — HashMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HashMap.html)
- [Hibernate ORM User Guide — Entity equality and identity](https://docs.hibernate.org/orm/current/userguide/html_single/)
- [Hibernate ORM Javadocs — HibernateProxy](https://docs.hibernate.org/orm/current/javadocs/org/hibernate/proxy/HibernateProxy.html)
- [Hibernate ORM Javadocs — NaturalId](https://docs.hibernate.org/orm/current/javadocs/org/hibernate/annotations/NaturalId.html)
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/)
- [Project Lombok — EqualsAndHashCode](https://projectlombok.org/features/EqualsAndHashCode)
- [Project Lombok — Data](https://projectlombok.org/features/Data)
