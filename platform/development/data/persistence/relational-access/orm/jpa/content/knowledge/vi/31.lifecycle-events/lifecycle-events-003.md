# Xử lý sự kiện sau khi entity được tải trong JPA

Trong Jakarta Persistence (JPA), một entity không chỉ trải qua các thao tác `persist()`, `merge()`, `remove()` và `flush()`. Khi JPA đưa dữ liệu của một entity vào **persistence context**, ứng dụng còn có thể được thông báo bằng **lifecycle callback**. Đối với thời điểm *sau khi entity được tải*, annotation quan trọng là **`@PostLoad`**.

Ví dụ một hệ thống quản lý sản phẩm lưu `firstName` và `lastName` của người phụ trách vào database, nhưng khi đưa entity vào bộ nhớ muốn tính trường chỉ dùng tại runtime `displayName`:

~~~java
@Transient
private String displayName;

@PostLoad
private void afterLoad() {
    displayName = firstName + " " + lastName;
}
~~~

Đây là một use case phù hợp vì callback chỉ tính một giá trị **trong bộ nhớ** từ các thuộc tính cơ bản đã tải, không phải chạy thêm SQL hay ghi dữ liệu ra hệ thống khác.

Tuy nhiên, cần hiểu một số giới hạn ngay từ đầu:

- `@PostLoad` **không đồng nghĩa “sau mỗi câu SELECT”** hoặc “sau mỗi lần gọi `find()`”.
- Một entity đã tồn tại trong **first-level cache** của cùng `EntityManager` thường được trả lại mà không tạo thêm instance và không có một lượt load mới.
- Entity có thể được load thông qua **second-level cache** mà không có SQL SELECT tương ứng; lifecycle event và SQL event là hai khái niệm khác nhau.
- Callback không phải nơi phù hợp để gọi repository, gửi HTTP, đọc LAZY association một cách tùy tiện hoặc phát business event.
- Giá trị `@Transient` tính tại `@PostLoad` **không tự cập nhật** mỗi khi một setter thay đổi trường nguồn sau đó.

Bài học này hướng dẫn **thời điểm JPA gọi `@PostLoad`**, khai báo callback bên trong entity và thông qua `@EntityListeners`, cách kết hợp với inheritance, fetch plan, transaction và cache, các use case nên/không nên dùng, cùng kỹ thuật kiểm thử trên persistence context thực.

## 1. Lifecycle callback là gì?

Lifecycle callback là một phương thức do JPA provider gọi tại các mốc được đặc tả trong vòng đời entity.

Một số annotation:

| Annotation | Mốc sự kiện theo ngữ nghĩa JPA |
| --- | --- |
| `@PrePersist` | Trước khi entity mới được persist |
| `@PostPersist` | Sau hoạt động persist/insert theo lifecycle semantics |
| `@PreUpdate` | Trước thao tác cập nhật persistent state |
| `@PostUpdate` | Sau thao tác cập nhật tương ứng |
| `@PreRemove` | Trước khi remove |
| `@PostRemove` | Sau thao tác remove tương ứng |
| **`@PostLoad`** | **Sau khi entity đã được tải vào persistence context hoặc được refresh** |

Nhóm annotation này thuộc `jakarta.persistence` trong Jakarta Persistence 3.x; dự án JPA/Java EE cũ có thể dùng namespace `javax.persistence`.

### Vì sao gọi là callback?

Ứng dụng khai báo phương thức:

~~~java
@PostLoad
void initializeRuntimeState() {
    // ...
}
~~~

Nhưng **không tự gọi phương thức đó** mỗi lần load. JPA provider điều phối việc gọi tại lifecycle event tương ứng. Vì thế callback phụ thuộc vào cách entity được đưa vào/refresh trong persistence context, không phụ thuộc trực tiếp vào số dòng code gọi `find()`.

## 2. PostLoad xảy ra ở thời điểm nào?

Sơ đồ đơn giản:

~~~text
EntityManager.find(Product.class, 10L)
                 |
                 v
     Đã có managed Product#10?
            /          \
          Có            Chưa
          |              |
          v              v
  Trả instance      Provider lấy state
  đang managed      từ DB hoặc shared cache
                         |
                         v
                 Gắn state cho entity
                 trong persistence context
                         |
                         v
                      @PostLoad
                         |
                         v
                  Trả managed entity
~~~

Đây là **sơ đồ tư duy**, không phải cam kết một thuật toán nội bộ duy nhất cho mọi provider.

Điểm chính:

1. `@PostLoad` liên quan **lifecycle của entity đang được tải/refresh**.
2. Nếu entity đã managed trong context, việc gọi lại `find()` thường chỉ lấy chính managed instance đó, **không phải một lần load mới**.
3. Callback được gọi khi provider thực hiện load entity trong phạm vi được đặc tả, có thể bao gồm việc load từ cache chia sẻ.
4. Một entity có thể được tải do **truy cập quan hệ**, query trả entities hoặc gọi `refresh()`; không nhất thiết chỉ do `find()` trực tiếp.

### Không hiểu PostLoad thành hook của SQL

Không nên viết:

~~~text
Một SELECT -> chính xác một @PostLoad.
Không có SELECT -> không có @PostLoad.
~~~

Số SQL, số row trả về, số managed entities và số callback invocations là những đại lượng khác nhau.

## 3. Một ví dụ tối thiểu có thể đọc được

Entity:

~~~java
package com.example.lifecycle;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PostLoad;
import jakarta.persistence.Transient;

@Entity
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String firstName;
    private String lastName;

    @Transient
    private String displayName;

    protected Customer() {
    }

    public Customer(String firstName, String lastName) {
        this.firstName = firstName;
        this.lastName = lastName;
        recomputeDisplayName();
    }

    @PostLoad
    private void afterLoad() {
        recomputeDisplayName();
    }

    private void recomputeDisplayName() {
        String first = firstName == null
            ? "" : firstName.trim();
        String last = lastName == null
            ? "" : lastName.trim();
        displayName = (first + " " + last).trim();
    }

    public Long getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

Ví dụ sử dụng:

~~~java
EntityManager em = emf.createEntityManager();
try {
    Customer customer =
        em.find(Customer.class, customerId);

    System.out.println(customer.getDisplayName());
} finally {
    em.close();
}
~~~

Khi một Customer được load vào context và callback chạy, `displayName` được tính từ hai cột persistent. Vì trường được đánh dấu `@Transient`, nó **không phải một cột được JPA quản lý trong mapping này**.

### Tại sao constructor cũng gọi recomputeDisplayName?

Một entity được tạo mới bằng:

~~~java
new Customer("An", "Nguyễn");
~~~

**chưa được load từ database**, nên `@PostLoad` chưa chạy. Việc gọi helper từ constructor bảo đảm derived field cũng có giá trị cho entity mới.

Không để use case phụ thuộc hoàn toàn vào callback mà bỏ quên các đường tạo entity khác.

## 4. Quy tắc về chữ ký phương thức @PostLoad trong entity

Callback khai báo **trực tiếp trong entity hoặc mapped superclass** thường có dạng:

~~~java
@PostLoad
private void onLoad() {
    // Không tham số, trả void.
}
~~~

Các yêu cầu quan trọng của callback method kiểu này:

- Có **return type là `void`**.
- **Không nhận tham số** đối với callback method khai báo trực tiếp trong entity.
- Không phải phương thức `static` hoặc `final` theo quy tắc portable lifecycle callback.
- Có thể dùng visibility được JPA cho phép, ví dụ `private`, `protected` hoặc package-level.
- Được provider gọi, không cần public API dành cho controller/service.

Ví dụ sai:

~~~java
@PostLoad
public String afterLoad() {
    return "Loaded"; // Sai chữ ký vì trả String.
}
~~~

Ví dụ sai:

~~~java
@PostLoad
public void afterLoad(EntityManager em) {
    // Sai chữ ký callback trong entity.
}
~~~

### Vì sao callback private có ích?

Callback là chi tiết vòng đời của entity, không phải public business operation. Để `private` ngăn code bên ngoài gọi nó tùy ý, đồng thời tách rõ chức năng khỏi service API.

## 5. Callback trong entity và EntityListener khác nhau thế nào?

Hai cách phổ biến:

**Cách A — Callback bên trong entity:**

~~~java
@Entity
public class Product {

    @PostLoad
    private void postLoad() {
        // Truy cập trực tiếp fields của Product.
    }
}
~~~

**Cách B — Listener class riêng:**

~~~java
@Entity
@EntityListeners(ProductLoadListener.class)
public class Product {
    // ...
}
~~~

~~~java
public class ProductLoadListener {

    @PostLoad
    public void onLoad(Product product) {
        // Callback nhận entity đang được load.
    }
}
~~~

Khác biệt về signature:

| Nơi khai báo | Dạng callback |
| --- | --- |
| Trong entity/mapped superclass | `void afterLoad()` |
| Trong entity listener class | `void afterLoad(Product product)` hoặc dạng tham số entity phù hợp |

Với listener, tham số thể hiện **entity nhận lifecycle event**, còn với method trong entity, `this` chính là entity đó.

### Chọn cách nào?

- Callback trong entity: logic rất gần domain state, ngắn, không cần tái dùng cho nhiều loại entity.
- Listener class: muốn tách trách nhiệm, dùng chung logic hoặc giữ entity bớt dày.

Không bắt buộc mọi dự án phải dùng listener class cho tất cả `@PostLoad`.

## 6. Ví dụ đầy đủ với @EntityListeners

Entity Product:

~~~java
package com.example.shop;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EntityListeners;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Transient;
import jakarta.persistence.Version;
import java.math.BigDecimal;

@Entity
@Table(name = "products")
@EntityListeners(ProductLoadListener.class)
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false, precision = 14, scale = 2)
    private BigDecimal price;

    @Column(nullable = false)
    private boolean active;

    @Version
    private Long version;

    @Transient
    private String runtimeSummary;

    protected Product() {
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public boolean isActive() {
        return active;
    }

    public Long getVersion() {
        return version;
    }

    public String getRuntimeSummary() {
        return runtimeSummary;
    }

    public void changePrice(BigDecimal nextPrice) {
        if (nextPrice == null || nextPrice.signum() < 0) {
            throw new IllegalArgumentException(
                "Giá không hợp lệ");
        }
        price = nextPrice;
        rebuildRuntimeSummary();
    }

    void rebuildRuntimeSummary() {
        runtimeSummary =
            name + " | " + price.toPlainString()
            + " | " + (active ? "ACTIVE" : "INACTIVE");
    }
}
~~~

Listener:

~~~java
package com.example.shop;

import jakarta.persistence.PostLoad;

public class ProductLoadListener {

    public ProductLoadListener() {
    }

    @PostLoad
    public void afterLoad(Product product) {
        product.rebuildRuntimeSummary();
    }
}
~~~

Khi Product được load, provider gọi listener để tính `runtimeSummary`. Phương thức helper nằm package-level để listener cùng package có thể gọi, nhưng vẫn không mở public setter cho client.

### Vì sao listener không gọi repository?

Mục đích listener ở ví dụ này chỉ là **khởi tạo derived transient state** từ dữ liệu của chính entity. Nó không cần EntityManager, JDBC hoặc HTTP. Điều này giúp callback dễ hiểu và không phụ thuộc transaction/service framework.

## 7. Listener có thể dùng cho nhiều entity không?

Có thể dùng một listener chung nếu các entities có một contract phù hợp.

Interface:

~~~java
package com.example.lifecycle;

public interface RuntimeStateInitializable {
    void rebuildRuntimeState();
}
~~~

Listener:

~~~java
package com.example.lifecycle;

import jakarta.persistence.PostLoad;

public class RuntimeStateListener {

    @PostLoad
    public void onLoad(Object entity) {
        if (entity instanceof RuntimeStateInitializable target) {
            target.rebuildRuntimeState();
        }
    }
}
~~~

Entity:

~~~java
@Entity
@EntityListeners(RuntimeStateListener.class)
public class Product
        implements RuntimeStateInitializable {

    @Override
    public void rebuildRuntimeState() {
        // Chỉ tính dữ liệu transient thuần túy.
    }
}
~~~

Với listener callback, JPA cho phép chữ ký nhận một entity instance thích hợp; ví dụ `Object` có thể được dùng để xây listener tổng quát khi cần, tùy rules của phiên bản API.

### Trade-off

Listener tổng quát giảm trùng lặp, nhưng việc kiểm tra `instanceof` cho hàng chục entity types dễ trở thành một “global hook” khó bảo trì. Nếu các entity có logic khác nhau, listener chuyên biệt hoặc callback trong entity thường rõ hơn.

## 8. @PostLoad được gọi khi find() load entity

Ví dụ:

~~~java
EntityManager em = emf.createEntityManager();

Product p = em.find(Product.class, 10L);
~~~

Nếu Product#10 chưa được quản lý trong `em`, provider phải tìm entity state theo mapping, trong database hoặc cơ chế shared cache phù hợp; khi load entity, `@PostLoad` được gọi theo lifecycle rules.

### Nhưng find() lần thứ hai thì sao?

~~~java
Product p1 = em.find(Product.class, 10L);
Product p2 = em.find(Product.class, 10L);

System.out.println(p1 == p2); // true
~~~

Khi Product vẫn managed, lần gọi thứ hai thường lấy cùng instance. **Đừng đếm hai lần PostLoad chỉ vì có hai dòng find**.

### Điều gì xảy ra sau clear()?

~~~java
em.clear();
Product p3 = em.find(Product.class, 10L);
~~~

`clear()` detach toàn bộ managed instances khỏi context. Lượt load tiếp theo có thể tạo/đưa một managed instance mới vào context, và lifecycle callback của lượt load được kích hoạt.

Tuy nhiên, `clear()` **không xóa shared L2 cache** và có thể làm mất pending changes chưa flush. Không dùng clear chỉ để “làm cho callback chạy lại” trong một transaction đang sửa dữ liệu.

## 9. @PostLoad và EntityManager.refresh()

JPA gọi `@PostLoad` cho entity được **refresh** theo lifecycle semantics.

Ví dụ:

~~~java
Product product = em.find(Product.class, 10L);

// Sau một sự kiện phù hợp, muốn load lại persistent state:
em.refresh(product);
~~~

Về ý nghĩa:

~~~text
Entity đang managed
      |
      v
EntityManager.refresh(entity)
      |
      v
Lấy lại persistent state theo DB/provider rules
      |
      v
@PostLoad
      |
      v
Derived transient state được tính lại
~~~

### Refresh có thể ghi đè thay đổi chưa flush

~~~java
product.changePrice(new BigDecimal("150000.00"));
em.refresh(product);
~~~

Nếu price trong DB vẫn là 100000, refresh có thể đưa price trở lại giá DB, làm mất thay đổi chưa được flush. `@PostLoad` chạy để phản ánh state vừa được refresh, **không phải để cứu pending changes**.

### Refresh không có nghĩa mọi transaction thấy commit mới nhất

Database isolation, transaction snapshot, shared cache hints, replication và provider configuration vẫn ảnh hưởng. Chỉ có callback chạy không chứng minh entity đang chứa “bản mới nhất toàn hệ thống”.

## 10. Query trả entity cũng có thể kích hoạt PostLoad

Ví dụ:

~~~java
List<Product> products = em.createQuery(
        "SELECT p FROM Product p " +
        "WHERE p.active = true " +
        "ORDER BY p.id",
        Product.class)
    .setMaxResults(100)
    .getResultList();
~~~

Các Product mới được load vào persistence context có thể nhận `@PostLoad`.

### Một query trả 100 rows có chắc 100 callbacks?

Không nên coi số row SQL bằng số callback:

- Một phần entities có thể **đã managed** trong context.
- Query có JOIN làm SQL lặp thông tin entity cùng identity.
- Cache/backend có thể ảnh hưởng cách state được lấy.
- Pagination/fetch graph làm số physical rows khác số distinct entities.

Điều nên kỳ vọng là callback gắn với **lifecycle load của mỗi entity**, không phải mỗi physical row trong ResultSet.

### Query trả DTO thì sao?

~~~java
List<ProductRow> rows = em.createQuery(
        "SELECT NEW com.example.shop.ProductRow(" +
        "p.id, p.name, p.price) " +
        "FROM Product p",
        ProductRow.class)
    .getResultList();
~~~

Nếu đây là constructor projection/scalar query không instantiate managed Product entity, không có lý do để đòi `Product.@PostLoad` chạy cho từng DTO. DTO không phải lifecycle-managed entity.

## 11. Association LAZY và thời điểm tải entity liên quan

Giả sử:

~~~java
@Entity
public class PurchaseOrder {
    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;
}
~~~

Khi tải PurchaseOrder:

~~~java
PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId);
~~~

Customer có thể chưa được khởi tạo. Khi code truy cập:

~~~java
order.getCustomer().getDisplayName();
~~~

provider có thể phải load Customer nếu nó chưa managed. Khi thực sự load Customer theo rules, `Customer.@PostLoad` có thể được gọi.

### Không kết luận load Order tự động gọi PostLoad của mọi quan hệ

`@PostLoad` của PurchaseOrder không có nghĩa toàn bộ `customer`, `items`, `shippingAddress` hoặc object graph đã được load đầy đủ.

### Proxy và lazy initialization

Nếu `getReference()` trả một proxy chưa initialized, việc có một Java reference **chưa đồng nghĩa state entity đã được load**. Callback thường gắn với lúc provider materialize/initialize state. Chi tiết về proxies/enhancement và thời điểm có SQL có thể khác nhau giữa providers.

Không dùng callback như một API để ép toàn bộ LAZY graph tải ngay.

## 12. Không đọc LAZY collection trong @PostLoad nếu không có yêu cầu rất rõ

Ví dụ:

~~~java
@Entity
public class PurchaseOrder {

    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines;

    @PostLoad
    private void afterLoad() {
        // Không nên làm kiểu này:
        int count = lines.size();
    }
}
~~~

Rủi ro:

- Callback có thể gây thêm SQL không mong muốn.
- Query danh sách Orders có thể biến thành **N+1 queries**.
- Provider có thể đang trong quá trình hydrate/fetch và callback truy cập graph chưa ở trạng thái người viết code giả định.
- Callback có thể bị kích hoạt trong use case chỉ muốn load Order header.
- Chi phí của một đoạn `lines.size()` trở nên khó nhìn thấy từ service.

### Hướng tốt hơn

Nếu cần count số dòng đơn hàng:

- Query DTO với `COUNT(line.id)`/`GROUP BY` phù hợp.
- Lưu một derived counter persistent được quản lý theo business transaction nếu thật sự cần.
- Tính khi caller yêu cầu và có fetch plan rõ.
- Dùng service/query riêng, không ép mọi PostLoad tạo thêm SQL.

**PostLoad nên ưu tiên xử lý local state đơn giản**, không âm thầm mở rộng truy vấn quan hệ.

## 13. N1 query do callback là một bẫy khó phát hiện

Giả sử admin page:

~~~java
List<Order> orders = orderRepository.findAll();
~~~

SQL kỳ vọng:

~~~text
1 SELECT orders
~~~

Nếu mỗi `Order.@PostLoad` đọc một LAZY Customer:

~~~java
@PostLoad
private void buildLabel() {
    label = customer.getName() + "-" + orderCode;
}
~~~

thì một số provider/fetch plans có thể phát:

~~~text
1 SELECT orders
N SELECT customers (hoặc các secondary SELECTs)
~~~

### Giải pháp

Nếu label cần `customer.name`:

~~~java
List<OrderLabel> results = em.createQuery(
        "SELECT NEW com.example.dto.OrderLabel(" +
        "o.id, o.orderCode, c.name) " +
        "FROM Order o JOIN o.customer c",
        OrderLabel.class)
    .getResultList();
~~~

Hoặc yêu cầu entity graph/fetch join phù hợp ở **đúng use case**, thay vì implicit fetch trong callback toàn cục.

### Kết luận nhỏ

Một callback chạy khi nhiều truy vấn khác nhau load entity. Thêm logic cần association vào đó có thể ảnh hưởng hiệu năng **mọi** truy vấn, kể cả những truy vấn chỉ đọc một entity field.

## 14. @PostLoad không phải @PostConstruct

`@PostConstruct` thường là lifecycle callback của CDI/Spring-managed bean, không phải entity-load callback chuẩn của JPA.

| Annotation | Thuộc cơ chế | Thời điểm |
| --- | --- | --- |
| `jakarta.persistence.PostLoad` | JPA | Khi entity được load/refresh theo contract |
| `jakarta.annotation.PostConstruct` | Jakarta dependency injection/lifecycle | Sau khi một managed component được dựng và dependencies được inject theo container |

Không viết:

~~~java
@PostConstruct
void initializeEntityAfterDbLoad() {
    // Không phải cách chuẩn để nhận JPA load.
}
~~~

### Entity có phải Spring Bean không?

Một JPA entity thường được provider tạo/quản lý theo persistence lifecycle, không phải một singleton Spring service. Đừng kỳ vọng `@Autowired` hoặc `@PostConstruct` trên entity hoạt động giống Spring bean trong mọi môi trường.

## 15. @PostLoad không phải event khi dữ liệu bị cập nhật

Các sự kiện khác:

~~~text
@PrePersist -> @PostPersist
@PreUpdate  -> @PostUpdate
@PreRemove  -> @PostRemove
@PostLoad   -> sau load/refresh
~~~

Nếu service sửa Product:

~~~java
Product product = em.find(Product.class, id);
product.changePrice(newPrice);
em.flush();
~~~

`changePrice()` không có nghĩa JPA gọi lại `@PostLoad`. Provider có thể gọi `@PreUpdate`/`@PostUpdate` khi thực hiện cập nhật thuộc phạm vi tương ứng, nhưng đó là lifecycle phase khác.

### Vì sao cần quan tâm?

Nếu chỉ tính `runtimeSummary` trong `@PostLoad`:

~~~text
Load Product price=100 -> runtimeSummary = "...100"
changePrice(120)
runtimeSummary vẫn "...100" nếu setter không cập nhật.
~~~

Giải pháp: gọi helper tính lại trong domain method, hoặc thiết kế getter tính toán trực tiếp thay vì lưu state `@Transient` dễ bị stale.

## 16. Có nên tính derived field tại PostLoad hay trong getter?

Hai phương án:

**Phương án A — Cache giá trị transient khi load:**

~~~java
@Transient
private String displayName;

@PostLoad
void afterLoad() {
    displayName = makeDisplayName(firstName, lastName);
}

public String getDisplayName() {
    return displayName;
}
~~~

**Phương án B — Tính trực tiếp:**

~~~java
public String getDisplayName() {
    return makeDisplayName(firstName, lastName);
}
~~~

### Khi nào dùng B?

- Phép tính rất nhẹ.
- Fields nguồn có thể bị setter/domain methods thay đổi nhiều lần.
- Không muốn đồng bộ derived transient state với persistent fields.
- Getter không gây IO và tính toán không phụ thuộc giờ hệ thống ngẫu nhiên.

### Khi nào A có ích?

- Có bước xây dựng runtime state đáng kể nhưng vẫn thuần túy/deterministic.
- State cần chuẩn bị cho object mỗi lần được hydrate/refresh.
- Có kế hoạch rõ cho entity được tạo mới và cho mọi mutation sau load.

Không bắt buộc phải dùng `@PostLoad` cho một chuỗi nối tên đơn giản nếu computed getter rõ ràng hơn.

## 17. @Transient của JPA và Java transient

Trong entity:

~~~java
@jakarta.persistence.Transient
private String formattedPrice;
~~~

JPA `@Transient` báo rằng trường/property không được map thành persistent attribute.

Java cũng có keyword:

~~~java
private transient String formattedPrice;
~~~

Java `transient` chủ yếu liên quan Java object serialization và cũng được JPA xử lý theo quy tắc persistence mapping cho transient field khi field access thích hợp; tuy nhiên các hệ thống JSON serialization có quy tắc riêng.

### Cách làm dễ hiểu

Trong bài học về JPA lifecycle, dùng annotation `jakarta.persistence.Transient` để làm rõ ý đồ **không persist** giá trị computed.

### @Transient có tự ẩn khỏi JSON response không?

Không nên giả định. Một serializer như Jackson có cơ chế nhận diện annotation/JavaBean riêng. Nếu cần tránh expose một giá trị nội bộ, dùng DTO hoặc cấu hình serialization phù hợp thay vì tin `@Transient` là security annotation.

## 18. Không sửa persistent fields trong @PostLoad theo thói quen

Ví dụ gây rủi ro:

~~~java
@PostLoad
private void normalize() {
    name = name.trim();
}
~~~

Nếu `name` là persistent attribute, thao tác này có thể khiến entity thay đổi ngay khi load. Tùy provider/dirty checking, có thể:

- Phát UPDATE ngoài ý định.
- Tăng version và tạo optimistic conflicts không cần thiết.
- Kích hoạt validation/audit triggers.
- Làm dữ liệu trong database thay đổi khi một truy vấn “chỉ đọc” chạy.
- Gây behavior khác nhau theo read-only/flush mode.

### Hướng tốt hơn

Nếu dữ liệu legacy cần chuẩn hóa:

- Dùng data migration để sửa database.
- Chuẩn hóa tại thời điểm nhập dữ liệu bằng domain method/validation.
- Dùng `AttributeConverter` nếu đây là mapping conversion đúng nghĩa.
- Tạo một derived `@Transient` field nếu chỉ cần representation hiển thị.

**Tải entity không nên âm thầm trở thành nghiệp vụ ghi.**

## 19. @PostLoad và dirty checking

Dirty checking là cơ chế JPA provider phát hiện persistent attributes thay đổi trên managed entity để đưa UPDATE phù hợp lúc flush/commit.

Nếu callback chỉ sửa:

~~~java
@Transient
private boolean expiredForDisplay;
~~~

và không động tới persistent fields/associations, đó là loại thao tác ít rủi ro hơn:

~~~java
@PostLoad
void buildDerivedState() {
    expiredForDisplay =
        expiryDate != null
        && expiryDate.isBefore(fixedReferenceDate);
}
~~~

### Nhưng “expired” phụ thuộc thời gian thực

Nếu `fixedReferenceDate` thực chất là ngày hiện tại, giá trị tính khi load sẽ **dần cũ** khi thời gian trôi qua. Ví dụ entity được load trước nửa đêm và giữ trong long-lived context thì flag `expiredForDisplay` không tự đổi sau nửa đêm.

Trường hợp này nên cân nhắc:

~~~java
public boolean isExpired(Clock clock) {
    return expiryDate != null
        && expiryDate.isBefore(LocalDate.now(clock));
}
~~~

ở domain/service layer, hoặc tính trong DTO theo thời điểm của request.

### Tiêu chí chọn derived transient

Ưu tiên giá trị được tính **deterministically từ persistent scalar attributes** và không phụ thuộc thông tin thay đổi liên tục ngoài entity.

## 20. Tại sao không nên gọi EntityManager trong lifecycle callback?

Một ví dụ không nên dùng:

~~~java
@PostLoad
private void loadMore() {
    Category category = entityManager.find(
        Category.class, categoryId);
    // ...
}
~~~

Vấn đề:

- Entity không nên phụ thuộc trực tiếp vào EntityManager service.
- Trong portable lifecycle callbacks, JPA khuyến nghị **không gọi EntityManager/query operations, không truy cập tùy tiện các entity khác hoặc sửa relationships trong cùng persistence context**.
- Provider có thể đang thực hiện một load graph phức tạp; query re-entrant có thể gây hành vi khó đoán.
- Callback bị gọi ngầm ở nhiều entrypoints, làm database IO khó kiểm soát.
- Có thể tạo vòng lặp callback giữa hai entity.

### Hướng thay thế

Nếu cần dữ liệu từ repository:

1. Cho service thực hiện query tường minh.
2. Chọn fetch plan/DTO phù hợp.
3. Gọi một domain method thuần túy khi đã có đủ input.
4. Đảm bảo transaction boundary do service quản lý.

**Callback không phải một service layer ẩn.**

## 21. Không phát HTTP hoặc message trong @PostLoad

Ví dụ sai:

~~~java
@PostLoad
private void afterLoad() {
    httpClient.post("/audit", "Product loaded");
}
~~~

Một query hiển thị 5.000 Product có thể phát 5.000 HTTP calls chỉ vì entity được materialize.

Rủi ro:

- Hiệu năng/timeout.
- Side effect được thực hiện khi transaction có thể rollback.
- Callback có thể xảy ra từ query background, cache warm-up, serialization flow.
- Không có event ID/idempotency rõ.
- Một người xem lại trang nhiều lần có thể phát nhiều external events.

### Nếu cần audit lượt truy cập dữ liệu

Ghi nhận audit ở **API/service boundary** với user, request ID, mục đích xử lý và bảo mật phù hợp. Đó là sự kiện “ai yêu cầu dữ liệu”, không phải lifecycle load object.

### Nếu cần domain event

Phát event khi business operation có ý nghĩa hoàn tất, ví dụ OrderConfirmed, không phải khi `@PostLoad` được gọi. Dùng transactional outbox hoặc cơ chế after-commit/idempotent phù hợp nếu event phải đồng bộ với commit.

## 22. PostLoad không phải nơi xác thực quyền truy cập

Ví dụ không an toàn:

~~~java
@PostLoad
private void checkTenant() {
    if (!tenantId.equals(CurrentUser.tenantId())) {
        throw new SecurityException("Forbidden");
    }
}
~~~

Lý do:

- Callback có thể chạy trong background job không có HTTP user.
- Thread-local/current user context có thể không tồn tại hoặc không đáng tin.
- Query đã tải dữ liệu không được phép vào persistence context trước khi callback báo lỗi.
- Quan hệ/caches và code paths khác có thể đi vòng logic kiểm tra.
- Khi một entity đã managed, `find()` lại có thể không gọi PostLoad lần nữa; không phải mỗi lần truy cập đều được authorize.

### Cách đúng

- Bảo vệ dữ liệu tại query/service authorization boundary.
- Scope theo tenant/owner/ACL theo policy.
- Xem xét database Row Level Security khi phù hợp.
- Không coi PostLoad là một hệ thống kiểm soát truy cập.

## 23. Có thể kiểm tra invariant trong @PostLoad không?

Ví dụ:

~~~java
@PostLoad
private void checkInvariant() {
    if (price.signum() < 0) {
        throw new IllegalStateException(
            "Negative price in DB");
    }
}
~~~

Điều này có thể khiến một entity load thất bại nếu database đang chứa dữ liệu hỏng. Nhưng nếu app dùng callback để làm validation nghiệp vụ chính, các vấn đề xuất hiện:

- Mọi truy vấn đọc lỗi sẽ không lấy được entity, kể cả job đang cố sửa dữ liệu.
- Validation tại load không ngăn writer khác lưu giá trị không hợp lệ.
- Dữ liệu thiếu có thể do migration/schema inconsistency.
- Exception có thể ảnh hưởng transaction và làm cả query fail.

### Dùng đúng lớp trách nhiệm

| Lớp | Cách bảo vệ |
| --- | --- |
| API/request | Input validation |
| Domain method | Business invariant khi thay đổi state |
| `@PrePersist`/`@PreUpdate` | Hook validation trước persistence operations nếu cần |
| Database | NOT NULL/CHECK/UNIQUE/FK constraints |
| `@PostLoad` | Khởi tạo derived state, quan sát cấu trúc đã tải một cách giới hạn |

Có thể dùng PostLoad cho **điều kiện phát hiện data corruption** trong một hệ thống được kiểm soát, nhưng phải chấp nhận tác động tới mọi đường đọc.

## 24. Exception trong @PostLoad có tác động gì?

Một callback:

~~~java
@PostLoad
private void afterLoad() {
    if (name == null) {
        throw new IllegalStateException(
            "Product name missing");
    }
}
~~~

Nếu exception không được xử lý, operation đang load entity có thể thất bại, và transaction có thể bị đánh dấu rollback-only tùy lifecycle/transaction contract. Đừng coi callback exception là một cảnh báo nhẹ không ảnh hưởng giao dịch.

### Không cố nuốt mọi lỗi

~~~java
@PostLoad
void afterLoad() {
    try {
        initializeSomething();
    } catch (Exception ignored) {
        // Entity ở trạng thái dở dang, nhưng query vẫn thành công.
    }
}
~~~

Một callback im lặng tạo state không nhất quán có thể gây lỗi ở tầng khác khó debug hơn.

### Hướng xử lý

- Viết callback nhỏ, thuần túy, ít khả năng ném lỗi.
- Kiểm tra null và dữ liệu legacy theo quy tắc rõ.
- Nếu lỗi nghiêm trọng, để service error handling/transaction boundary xử lý đúng.
- Không dùng callback làm điểm retries hoặc tự mở một transaction khác.

## 25. @PostLoad có chạy trong read-only transaction không?

Ví dụ Spring:

~~~java
@Transactional(readOnly = true)
public ProductView getProduct(long id) {
    Product p = em.find(Product.class, id);
    return ProductView.from(p);
}
~~~

Khi Product được load, `@PostLoad` vẫn là lifecycle event có liên quan. `readOnly=true` không phải một cơ chế tắt lifecycle callbacks.

### Hành vi mà readOnly không bảo đảm

Một read-only hint có thể tác động flush mode hoặc JDBC transaction read-only tùy Spring/provider, nhưng không thay đổi ý nghĩa cơ bản của `@PostLoad`.

### Vì sao callback nên thuần túy?

Vì entity có thể được load trong nghiệp vụ **chỉ đọc**. Nếu callback sửa persistent columns hoặc gọi service ghi, nó đi ngược ý định read-only và dễ có behavior provider-specific.

## 26. PostLoad và bộ nhớ đệm L1

Persistence context giữ entity identity:

~~~java
Product p1 = em.find(Product.class, 10L);
Product p2 = em.find(Product.class, 10L);
~~~

Với Product#10 managed trong cùng context:

~~~java
p1 == p2 // true
~~~

Do đó:

~~~text
find lần 1 -> entity được load -> PostLoad
find lần 2 -> entity đã managed -> không phải load mới
~~~

### Nếu persist entity mới?

~~~java
Product p = new Product(...);
em.persist(p);
~~~

Đây là lifecycle persist, không phải load. **Không kỳ vọng @PostLoad chạy cho một entity mới được persist** chỉ vì nó trở thành managed.

### Nếu merge?

`em.merge(detached)` có thể tạo hoặc dùng một managed instance và tải state trong quá trình merge khi cần; việc callback nào chạy phụ thuộc managed entity có thực sự được load hay không. Không dùng merge làm cách thủ công “kích hoạt PostLoad”.

## 27. PostLoad và shared cache L2

Nếu second-level entity cache được cấu hình, một Product có thể được tạo thành managed instance mới từ cached state.

~~~text
EntityManager A
    SELECT Product#10 từ DB
    Đưa state vào shared cache nếu được phép
    PostLoad cho managed Product A

EntityManager B mới
    L2 hit Product#10
    Tạo/nạp managed Product B từ state L2
    PostLoad cho managed Product B theo lifecycle load
~~~

### Không đánh đồng callback với SQL count

Một PostLoad được gọi không chứng minh có SQL SELECT; một câu SQL SELECT có thể trả dữ liệu phục vụ nhiều entities hoặc không tạo thêm managed instance nếu context đã chứa entity.

### Cache stale thì sao?

Nếu L2 chứa stale Product state do external writer không invalidates cache, callback sẽ tính derived transient state dựa trên **những field mà provider đang đưa vào entity**. Nó không tự kiểm tra database latest version.

Để bảo vệ tính mới phải dùng cache invalidation, transaction isolation, version/locking hoặc explicit refresh phù hợp. **PostLoad không phải validator về dữ liệu mới nhất toàn hệ thống.**

## 28. CacheRetrieveMode.BYPASS có làm callback luôn chạy?

Ví dụ:

~~~java
Product p1 = em.find(Product.class, id);

Product p2 = em.find(
    Product.class,
    id,
    Map.of(
        "jakarta.persistence.cache.retrieveMode",
        CacheRetrieveMode.BYPASS
    )
);
~~~

Mục đích `CacheRetrieveMode.BYPASS` là bỏ qua **shared entity cache** khi load phù hợp. Nó **không bỏ qua first-level identity map** nếu Product đã managed.

Do đó không thể dùng retrieve BYPASS để hứa `@PostLoad` chạy lại mỗi lần gọi `find()`.

### Nếu muốn callback chạy lại để tính derived field?

Đừng buộc JPA reload chỉ để tính một chuỗi/flag. Gọi helper domain hoặc computed getter thích hợp sẽ rẻ và rõ hơn.

Nếu thật sự cần DB refresh, dùng `em.refresh(entity)` với transaction/consistency semantics phù hợp; callback khi refresh phục vụ lifecycle state vừa được làm mới, không phải “máy chạy lại business function”.

## 29. @PostLoad trong mapped superclass

Khi nhiều entities cần một callback dùng chung, có thể đặt callback ở `@MappedSuperclass`.

~~~java
package com.example.lifecycle;

import jakarta.persistence.MappedSuperclass;
import jakarta.persistence.PostLoad;
import jakarta.persistence.Transient;

@MappedSuperclass
public abstract class VersionedDisplayBase {

    @Transient
    private String lifecycleFlag;

    @PostLoad
    protected void afterBaseLoad() {
        lifecycleFlag = "LOADED";
    }

    public String getLifecycleFlag() {
        return lifecycleFlag;
    }
}
~~~

Entity:

~~~java
@Entity
public class Product extends VersionedDisplayBase {
    // ...
}
~~~

### Được gọi trong inheritance như thế nào?

JPA có quy tắc thứ tự callback theo mapped superclasses/entity listeners/entity callback methods. Một callback ở superclass có thể tham gia vòng đời của subclass entity.

### Cần chú ý override

Nếu subclass override một phương thức callback có cùng chữ ký, phải hiểu quy tắc override/suppression của JPA và Java. Không tự nghĩ rằng luôn có hai lần gọi base + subclass cho cùng một chữ ký.

Một lựa chọn ít gây nhầm hơn là đặt các callback khác tên và kiểm tra lifecycle order với provider/test khi dựa vào thứ tự.

## 30. Thứ tự các entity listeners

Giả sử:

~~~java
@Entity
@EntityListeners({
    AuditInitListener.class,
    SearchTextListener.class
})
public class Product {

    @PostLoad
    private void afterOwnLoad() {
        // ...
    }
}
~~~

JPA có quy tắc gọi listener ở tầng superclass/default/entity-specific và entity callbacks. Trong một danh sách listeners khai báo trên cùng entity, **thứ tự khai báo là một phần của ordering semantics** theo đặc tả khi áp dụng.

### Nhưng không nên phụ thuộc thứ tự để “cứu” thiết kế yếu

Nếu `SearchTextListener` chỉ chạy đúng khi `AuditInitListener` vừa gán một transient field, hệ thống đã tạo **coupling ẩn giữa callbacks**.

Ưu tiên:

- Các callback độc lập.
- Hoặc một listener/helper duy nhất tính toàn bộ derived state liên quan.
- Hoặc service/domain method gọi các bước một cách tường minh nếu có dependency quan trọng.

### Default listeners

Persistence XML có thể cấu hình default entity listeners. Những listeners này có thể chạy cho nhiều entities. Một đoạn code load một Product có thể bị ảnh hưởng bởi listener **không thấy trực tiếp trong source Product**.

Khi debugging cần kiểm tra mapping XML và inheritance, không chỉ annotation trên entity.

## 31. @ExcludeSuperclassListeners và @ExcludeDefaultListeners

JPA có các annotation:

~~~java
@ExcludeSuperclassListeners
@ExcludeDefaultListeners
~~~

Mục đích là điều khiển việc áp dụng **listener callbacks** được kế thừa từ superclasses hoặc được định nghĩa là default listeners theo phạm vi của đặc tả.

Ví dụ minh họa:

~~~java
@Entity
@ExcludeDefaultListeners
@EntityListeners(ProductLoadListener.class)
public class Product {
    // ...
}
~~~

### Phân biệt “listener” với “callback method trong entity”

Không được hiểu việc loại bỏ default/superclass listeners là tự động xóa mọi callback method khai báo ở tất cả mapped superclasses. JPA phân biệt callback methods của entity hierarchy và listener classes trong ordering/exclusion rules.

### Khi nào cần?

Một entity có yêu cầu đặc biệt không phù hợp với default listener của persistence unit. Dùng exclusion annotation có chủ đích, ghi rõ lý do, và kiểm thử event invocation theo mapping thực tế.

Không dùng annotation exclusion như phương án đầu tiên cho một listener toàn cục được viết quá phức tạp; đôi khi cần thiết kế listener lại.

## 32. Attribute access và callback

JPA có hai cách truy cập persistent state:

- **Field access:** annotation mapping đặt trên fields.
- **Property access:** annotation mapping đặt trên getters.

### Field access

~~~java
@Id
private Long id;

@Column
private String name;
~~~

Callback:

~~~java
@PostLoad
private void afterLoad() {
    label = name == null ? "" : name.trim();
}
~~~

### Property access

~~~java
private Long id;

@Id
public Long getId() {
    return id;
}
~~~

Callback vẫn có thể là method không tham số:

~~~java
@PostLoad
private void afterLoad() {
    // Có thể dùng getter/fields của chính entity.
}
~~~

### Phân biệt mapping access với callback visibility

Việc JPA dùng field access hay property access **không làm @PostLoad trở thành getter/setter hook**. Callback là cơ chế lifecycle riêng.

### Tránh recursion

Nếu `getDisplayName()` có side effect cập nhật field mapping, và callback lại gọi getter đó, có thể tạo trạng thái khó dự đoán. Hãy để derived getter/helper thuần túy.

## 33. Dữ liệu đã được convert trước khi callback?

Một persistent attribute có thể sử dụng `@Convert`:

~~~java
@Convert(converter = MoneyAmountConverter.class)
private MoneyAmount amount;
~~~

Ý tưởng mapping:

~~~text
Database column
    -> JDBC
    -> AttributeConverter/provider hydration
    -> Persistent Java field được thiết lập
    -> @PostLoad có thể xử lý state đã map
~~~

Trong lifecycle load phù hợp, callback làm việc với **entity attributes dưới dạng Java đã được mapping**.

### Khi nào dùng converter thay vì PostLoad?

Nếu mục tiêu là chuyển một column string thành Java value object hoặc mã hóa/giải mã dữ liệu persistent, `AttributeConverter` thường đúng trách nhiệm hơn.

Nếu mục tiêu là tạo một **runtime summary** kết hợp nhiều mapped attributes, `@PostLoad` hoặc computed getter có thể phù hợp.

### Không duplicate logic

Đừng viết một converter và một PostLoad cùng sửa một persistent field theo hai cách khác nhau. Nó khiến dữ liệu thay đổi tùy load path và có thể tác động dirty checking.

## 34. Khi nào callback thực sự hữu ích?

Một số use case hợp lý:

**A. Khởi tạo derived transient flag từ scalar fields**

~~~java
@Transient
private boolean requiresManualReview;

@PostLoad
private void deriveFlag() {
    requiresManualReview =
        totalAmount != null
        && totalAmount.compareTo(reviewThreshold) > 0;
}
~~~

Nếu `reviewThreshold` là một field persistent hoặc hằng số domain ổn định và logic được recompute khi inputs thay đổi, đây là ví dụ dễ kiểm soát.

**B. Khôi phục cấu trúc runtime đơn giản không persist**

~~~java
@Transient
private Set<String> normalizedTags;

@PostLoad
private void initializeTags() {
    normalizedTags = new HashSet<>();
    for (String tag : simpleTagValues) {
        normalizedTags.add(tag.toLowerCase(Locale.ROOT));
    }
}
~~~

Ví dụ này chỉ phù hợp nếu `simpleTagValues` đã có sẵn và **không là một LAZY collection cần query thêm** tại callback.

**C. Xây local read-only index/lookup**

Một entity có vài scalar fields và cần một map transient nhỏ để xử lý tại runtime; callback có thể xây lại map sau hydration. Không nên dùng callback cho tập dữ liệu lớn hoặc query-driven index.

## 35. Khi nào không nên dùng @PostLoad?

Không dùng callback như nơi mặc định để:

- Gửi email/SMS/webhook.
- Tạo đơn hàng mới.
- Gọi payment gateway.
- Tự động UPDATE nhiều rows.
- Kiểm tra quyền user theo request context.
- Fetch toàn bộ LAZY relations.
- Chạy query tổng hợp N lần cho N entities.
- Tính toán nặng theo mạng hoặc một mô hình ML.
- Lấy cấu hình remote service.
- Gắn một EntityManager vào entity.
- Làm nóng toàn application cache không có giới hạn.
- Tự retry optimistic/pessimistic transaction failures.

### Vì sao?

PostLoad được gọi **ngầm** qua nhiều đường đọc và có thể xảy ra trong các transaction read-only hoặc background processing. Một side effect không kiểm soát tại đây dễ bị nhân số lần, sai transaction scope và làm khó việc phân tích hiệu năng.

**Dùng callback cho state initialization nhỏ; dùng service cho business workflow.**

## 36. Rủi ro khi sử dụng dependency injection trong listener

Ví dụ:

~~~java
public class ProductLoadListener {

    @Inject
    ProductRepository repository;

    @PostLoad
    public void afterLoad(Product product) {
        repository.findSomething(...);
    }
}
~~~

Có hai vấn đề:

1. **Injection/lifecycle của listener phụ thuộc môi trường và cách provider tích hợp CDI/Spring**. Không phải listener class do JPA trong Java SE đơn giản luôn là một Spring/CDI bean có dependencies được inject theo cách kỳ vọng.
2. **Repository call trong lifecycle callback không portable/dễ an toàn** và có thể dẫn tới re-entrant load/N+1 hoặc vòng lặp.

### Hướng khuyến nghị

Thiết kế listener stateless, với constructor đơn giản, không cần IO/service dependencies. Nếu cần một business service, hãy để application service gọi sau khi load với input rõ ràng.

Trong một ứng dụng Jakarta EE có CDI integration chính thức, listener injection có thể được hỗ trợ theo spec/environment. Nhưng **việc được phép inject không làm mọi database query trong callback trở thành lựa chọn kiến trúc tốt**.

## 37. Listener nên stateless và thread-safe

Một listener không nên giữ state thay đổi theo entity:

~~~java
public class BadListener {

    private Long lastLoadedId;

    @PostLoad
    public void afterLoad(Product p) {
        lastLoadedId = p.getId();
    }
}
~~~

Rủi ro:

- Listener instance lifecycle có thể được container/provider quản lý và chia sẻ/khởi tạo theo cách người viết không kiểm soát hoàn toàn.
- Nhiều transactions/requests có thể được thực thi song song.
- State của entity này có thể làm ảnh hưởng callback của entity khác.

### Mẫu tốt hơn

~~~java
public class ProductLoadListener {

    @PostLoad
    public void afterLoad(Product p) {
        p.rebuildRuntimeSummary();
    }
}
~~~

Không có mutable fields trong listener. Mọi state tính ra nằm trên entity tương ứng và được khai báo transient.

## 38. @PostLoad và inheritance: một ví dụ nhiều tầng

Giả sử:

~~~java
@MappedSuperclass
public abstract class NamedRecord {

    @Transient
    private String normalizedName;

    @PostLoad
    protected void initializeNormalizedName() {
        normalizedName = normalizeName();
    }

    protected abstract String normalizeName();
}
~~~

~~~java
@Entity
public class Supplier extends NamedRecord {

    private String companyName;

    @Override
    protected String normalizeName() {
        return companyName == null
            ? "" : companyName.trim();
    }
}
~~~

Khi Supplier được load, callback từ mapped superclass có thể tính normalizedName qua method được subclass implement.

### Rủi ro virtual dispatch

Callback của superclass gọi một overridable method của subclass. Nếu method truy cập quan hệ chưa initialized hoặc giả định fields khác đã sẵn sàng theo cách provider không bảo đảm, có thể gặp lỗi.

### Cách làm thận trọng

Giữ helper dựa trên scalar attributes đơn giản. Nếu logic giữa subclass khác biệt quá lớn, đặt callback tại subclass hoặc listener chuyên biệt thay vì một generic callback phức tạp ở superclass.

## 39. EntityGraph và PostLoad

JPA cho phép cấu hình fetch graph/load graph:

~~~java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);
graph.addAttributeNodes("customer");

Map<String, Object> hints =
    Map.of("jakarta.persistence.fetchgraph", graph);

PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId, hints);
~~~

Fetch graph có thể điều chỉnh những attributes cần tải. **PostLoad không phải nơi quyết định graph nào được fetch**.

### Hạn chế quan trọng

Ngay cả khi graph bao gồm một association, đừng viết callback phụ thuộc vào một trình tự chính xác “Customer luôn PostLoad hoàn tất trước Order PostLoad” nếu hợp đồng ứng dụng chưa được chứng minh theo JPA/provider/mapping.

Provider có thể có những điểm materialization/initialization nội bộ khác nhau. Nếu một tính toán cần cả Order và Customer, service nên query/fetch rõ và tính ở bước có input đã sẵn sàng.

### Không “chữa lazy load” bằng PostLoad

Nếu API trả `LazyInitializationException` sau khi đóng EntityManager, lỗi là fetch plan/transaction boundary, không phải “thiếu callback”. Cần DTO/EntityGraph/transactional service phù hợp.

## 40. EntityListener vs Spring @EventListener

Tên gọi dễ gây nhầm:

~~~java
@EntityListeners(ProductLoadListener.class)
~~~

và:

~~~java
@org.springframework.context.event.EventListener
public void handle(ProductLoadedEvent event) { ... }
~~~

là hai cơ chế hoàn toàn khác nhau.

### JPA EntityListener

- JPA provider gọi trong lifecycle entity theo mapping.
- Có thể được kích hoạt do load/refresh.
- Thường chạy trong call stack của persistence operation.
- Không mặc định là một domain event phát tới message bus.

### Spring @EventListener

- Spring application context gọi khi application publish một application event.
- Người phát sự kiện quyết định thời điểm và payload.
- Có thể dùng `@TransactionalEventListener` khi cần event handling theo transaction phase, với các giới hạn riêng.

**Không dùng @PostLoad để mô phỏng ứng dụng “phát event mỗi khi ai đó nhìn dữ liệu”** nếu use case thật cần theo dõi user request hoặc business event có identity/idempotency.

## 41. Một luồng API đầy đủ: load entity và trả DTO

DTO:

~~~java
package com.example.shop.api;

import java.math.BigDecimal;

public record ProductView(
    Long id,
    String name,
    BigDecimal price,
    String runtimeSummary,
    Long version
) {
}
~~~

Service:

~~~java
package com.example.shop;

import com.example.shop.api.ProductView;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductQueryService {

    @PersistenceContext
    private EntityManager em;

    @Transactional(readOnly = true)
    public ProductView findById(long productId) {
        Product p = em.find(
            Product.class, productId);

        if (p == null) {
            throw new IllegalArgumentException(
                "Product không tồn tại");
        }

        return new ProductView(
            p.getId(),
            p.getName(),
            p.getPrice(),
            p.getRuntimeSummary(),
            p.getVersion()
        );
    }
}
~~~

Khi Product được load, listener xây runtime summary. Service chuyển managed entity thành DTO **trong transactional read boundary**, không trả entity graph thẳng ra HTTP serializer.

### Vì sao dùng DTO?

- Chỉ expose dữ liệu người dùng được phép xem.
- Tránh lazy loading khi JSON serializer chạy ngoài transaction.
- Có contract ổn định cho client.
- Tách logic persistence khỏi representation.

### Có thể bỏ PostLoad và tính DTO trực tiếp không?

Hoàn toàn có thể:

~~~java
return new ProductView(
    p.getId(), p.getName(), p.getPrice(),
    buildSummary(p), p.getVersion()
);
~~~

Nếu summary chỉ phục vụ một API, cách tính ở DTO/service thường dễ hiểu và có ít global side effects hơn callback chạy cho mọi Product load.

## 42. @PostLoad trong RESOURCE_LOCAL transaction

Ví dụ thuần JPA:

~~~java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Product product =
        em.find(Product.class, productId);

    // Nếu Product được load: @PostLoad đã có
    // cơ hội khởi tạo runtimeSummary.
    String summary = product.getRuntimeSummary();

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
~~~

### Callback có bắt buộc phải có transaction không?

Không nên gắn một quy tắc đơn giản “PostLoad chỉ chạy khi `tx.begin()` được gọi” cho mọi môi trường. Một số read operations có thể load entity trong context mà transaction không active theo rules JPA/provider. Nhưng nếu callback cần một transaction để query/write thì đó lại là dấu hiệu **thiết kế callback sai trách nhiệm**.

### Khi dùng JTA/Spring

Không gọi `em.getTransaction()` đối với JTA-managed hoặc Spring-managed transactional EntityManager. Transaction do container/manager sở hữu; callback vẫn được provider gọi trong lifecycle load.

## 43. Lỗi transaction và exception callback

Giả sử `@PostLoad` ném một unchecked exception. Controller có thể thấy lỗi ngay lúc `find()` hoặc lúc query materialization.

~~~text
Service @Transactional
    |
    +-- EntityManager.find()
             |
             +-- hydrate Product
             +-- invoke @PostLoad
                       |
                       +-- exception
    |
    +-- Transaction failure/rollback handling
~~~

### Có nên catch rồi tiếp tục cùng transaction?

Không mặc định. Exception từ lifecycle callback có thể khiến load operation thất bại và transaction bị đánh dấu rollback-only tùy contract. Với nghiệp vụ cần toàn vẹn, rollback và xử lý tại service/controller boundary thường an toàn hơn việc cố tiếp tục trên context chưa rõ trạng thái.

### Không làm logging “sửa” lỗi

Nếu callback có lỗi do data corruption, không nên catch-all rồi return DTO với state chưa khởi tạo mà không có contract. Chẩn đoán nguyên nhân và sửa dữ liệu/mapping/callback đúng nguồn.

## 44. Test callback thực sự chạy khi entity được load

Một unit test:

~~~java
Product product = new Product(...);
product.rebuildRuntimeSummary();
~~~

chỉ test helper; nó **không chứng minh JPA đã gọi `@PostLoad`**.

Integration test nên tạo fixture đã commit và dùng **EntityManager mới** để load.

Quy trình:

~~~text
Phase 1:
  EM_A mở transaction
  persist Product
  commit
  close EM_A

Phase 2:
  EM_B mới
  find Product#ID
  assert runtimeSummary được khởi tạo từ persistent state
  close EM_B
~~~

### Tại sao đóng EM_A?

Nếu Product vẫn managed trong EM_A sau `persist()`, gọi `find()` lại có thể chỉ trả managed instance và **không tạo lifecycle load**. Khi test PostLoad, phải buộc entity được hydrate vào một context mới.

## 45. Skeleton test với EntityManagerFactory

Pseudocode theo style JUnit:

~~~java
@Test
void postLoadInitializesRuntimeSummary() {

    Long productId = persistFixtureProduct(
        "Java Handbook",
        new BigDecimal("100000.00"));

    EntityManager em = emf.createEntityManager();
    try {
        Product loaded =
            em.find(Product.class, productId);

        assertNotNull(loaded);
        assertEquals(
            "Java Handbook | 100000.00 | ACTIVE",
            loaded.getRuntimeSummary());
    } finally {
        em.close();
    }
}
~~~

`persistFixtureProduct` là helper test tạo Product hợp lệ trong transaction riêng rồi commit, không phải API JPA built-in. Format kỳ vọng phải phù hợp `BigDecimal.toPlainString()` và dữ liệu fixture.

### Điều nên kiểm tra thêm

- Runtime summary có giá trị sau load từ context mới.
- Column database không chứa field transient.
- Một entity mới chưa load được khởi tạo đúng qua constructor/domain methods.
- Cập nhật price qua domain method không làm summary stale.

**Đây là kiểm thử behavior, không cần đếm số lần callback nếu use case không phụ thuộc count.**

## 46. Test PostLoad khi refresh

Fixture:

~~~text
Product#10:
  price = 100000
~~~

Luồng:

1. EM_A load Product#10, summary phản ánh giá 100000.
2. Một transaction **khác** cập nhật Product#10 thành 120000 rồi commit.
3. EM_A gọi `refresh(product)` với điều kiện database isolation/transaction cho phép quan sát update mới.
4. Kiểm tra price và summary của Product được cập nhật phù hợp.

### Ví dụ ý tưởng

~~~java
Product product =
    em.find(Product.class, productId);

// Một writer khác đã commit giá mới.
em.refresh(product);

assertEquals(
    new BigDecimal("120000.00"),
    product.getPrice());

assertTrue(
    product.getRuntimeSummary().contains("120000.00"));
~~~

### Thận trọng

- Nếu transaction đang giữ snapshot cũ, refresh có thể không thấy commit mới.
- Nếu shared cache/provider có cấu hình khác, test cần đặt fetch/cache hints thích hợp.
- Không nên sửa Product chưa flush trước refresh rồi mong giữ thay đổi.
- Không dùng cùng EntityManager cho writer bên ngoài và reader nếu cần kiểm tra concurrency thực.

## 47. Test L1: find() hai lần trong một context

Một bài test dùng identity:

~~~java
Product a = em.find(Product.class, productId);
Product b = em.find(Product.class, productId);

assertSame(a, b);
~~~

Mục tiêu là chứng minh **managed identity** được tái sử dụng.

### Có nên đếm callback đúng một lần?

Nếu cần quan sát behavior với provider hiện tại, có thể thêm test-only instrumentation để ghi nhận callback. Nhưng một test dựa trên counter global có thể nhiễu khi fixture setup, query phụ hoặc test chạy song song.

Điểm cần học là: **hai lời gọi find không đồng nghĩa hai load lifecycle events**.

### Dùng callback counter như thế nào?

Trong môi trường test cô lập có thể dùng listener ghi một event vào test recorder thread-confined. Tránh để static mutable counter trong entity production vì nó làm callback có side effects và khó kiểm thử song song.

## 48. Test entity listener riêng

Một entity sử dụng:

~~~java
@EntityListeners(ProductLoadListener.class)
public class Product {
    // ...
}
~~~

Integration test phải kiểm tra listener được provider nhận diện từ annotation/mapping và gọi khi một Product được load.

### Đừng chỉ gọi listener trực tiếp

~~~java
new ProductLoadListener().afterLoad(product);
~~~

chỉ xác nhận logic trong method, **không xác nhận mapping `@EntityListeners` đã hoạt động**.

### Test nên phân tách

- Unit test helper thuần túy (nhanh, không DB).
- Integration test PostLoad wiring (EntityManagerFactory thật).
- Integration test refresh/inheritance/cascade nếu business phụ thuộc behavior đó.

## 49. Test inheritance và callback order

Nếu entity có:

~~~java
@MappedSuperclass
abstract class BaseRecord {
    @PostLoad
    protected void baseLoad() { ... }
}
~~~

và:

~~~java
@Entity
@EntityListeners(MyListener.class)
class Product extends BaseRecord {
    @PostLoad
    private void productLoad() { ... }
}
~~~

hãy tạo Product từ DB rồi kiểm tra state của từng callback.

### Nếu business phụ thuộc thứ tự

Một test có thể ghi lại thứ tự gọi trong một recorder test-only, nhưng nên đánh giá xem thiết kế có thể được đơn giản hóa để không phụ thuộc vào những bước initialization rời rạc hay không.

### Default listeners/XML

Nếu persistence unit cấu hình default listeners qua XML, thêm integration test cho chúng và exclusion annotations tương ứng. Chỉ nhìn source Product không đủ thấy toàn bộ lifecycle pipeline.

## 50. Test không làm thêm SQL ngoài ý muốn

Một callback sạch chỉ tính derived scalar field thường **không cần SELECT bổ sung**.

Test đo:

~~~text
SELECT Product list (100 entities)
  -> Product @PostLoad chạy khi load
  -> Không phát thêm 100 SELECT Category/OrderLines
~~~

### Cách quan sát

- Bật SQL logging trong môi trường test.
- Dùng Hibernate Statistics nếu project dùng Hibernate.
- Đo query count trước/sau khi thêm callback.
- Thử query danh sách và query detail với các fetch plans khác nhau.

### Không chỉ đo happy path

Một callback có thể chạy tốt khi Product được find bằng PK nhưng gây N+1 khi dùng list query. Kiểm thử **access pattern đại diện**, không chỉ một entity.

## 51. Đồng bộ transient state khi entity bị thay đổi sau load

Đây là lỗi thiết kế phổ biến:

~~~java
@PostLoad
void afterLoad() {
    runtimeSummary = name + ":" + price;
}

void changePrice(BigDecimal newPrice) {
    price = newPrice;
}
~~~

Sau `changePrice()`, summary vẫn mang giá cũ.

### Cách A — Recompute trong mutation

~~~java
void changePrice(BigDecimal newPrice) {
    validatePrice(newPrice);
    price = newPrice;
    rebuildRuntimeSummary();
}
~~~

### Cách B — Computed getter

~~~java
public String getRuntimeSummary() {
    return name + ":" + price;
}
~~~

### Cách C — Derived value trong DTO

~~~java
ProductView view = new ProductView(
    product.getId(),
    product.getName(),
    product.getPrice(),
    buildSummary(product),
    product.getVersion()
);
~~~

Chọn theo số lượng use cases và chi phí phép tính. **@PostLoad không tự theo dõi và tính lại transient values khi fields bị dirty.**

## 52. Callback có phải luôn chạy sau mọi @PostUpdate?

Không. `@PostLoad` là **load/refresh** event, còn `@PostUpdate` là event liên quan update.

~~~text
find Product
  -> PostLoad
changePrice
flush/commit
  -> PreUpdate / PostUpdate theo lifecycle rules
Không có lý do tự động PostLoad lần nữa chỉ do update.
~~~

### Có nên thêm @PostUpdate để tính lại summary?

Nếu mục tiêu là cập nhật transient summary ngay khi domain method sửa price, `@PostUpdate` có thể **quá muộn** (chỉ chạy lúc flush/update) và còn phụ thuộc operation có thực sự tạo update không. Domain method hoặc computed getter là giải pháp rõ hơn.

### @PostLoad + @PostUpdate cùng một method?

JPA cho phép một method được gắn nhiều lifecycle annotations trong những trường hợp phù hợp với signature, nhưng cần kiểm chứng mapping/version và tránh thiết kế phụ thuộc vào callback invocation ở mọi setter. Mục tiêu bài học vẫn là **xử lý sau load**, không dời business logic sang mọi lifecycle phase.

## 53. Bulk JPQL và native SQL không kích hoạt PostLoad của entity chưa được load

Ví dụ:

~~~java
int count = em.createQuery(
        "UPDATE Product p " +
        "SET p.active = false " +
        "WHERE p.id = :id")
    .setParameter("id", productId)
    .executeUpdate();
~~~

Đây là bulk update; JPA không cần load Product entity vào persistence context rồi gọi `@PostLoad` cho từng affected row.

Tương tự:

~~~java
em.createNativeQuery(
    "UPDATE products SET active=false WHERE id=?")
  .setParameter(1, productId)
  .executeUpdate();
~~~

không đồng nghĩa JPA đã load Product#10.

### Hệ quả về state

Nếu một Product đang managed trước bulk UPDATE, nó có thể giữ state cũ và transient summary cũ sau bulk. Cần thiết kế `refresh()`, `clear()` hoặc context mới theo transaction semantics, không kỳ vọng bulk update tự gọi PostLoad để đồng bộ mọi entity.

## 54. JSON deserialization không kích hoạt @PostLoad

Controller nhận JSON:

~~~json
{
  "id": 10,
  "name": "New Product",
  "price": 120000
}
~~~

Nếu Jackson tạo một Java Product/DTO từ JSON, đó không phải lifecycle event JPA load.

### Vì sao quan trọng?

Nếu entity được khởi tạo từ HTTP request rồi `merge()` trực tiếp, các transient fields chỉ có trong @PostLoad có thể chưa được xây dựng. Quan trọng hơn, nhận entity trực tiếp từ client có thể làm lẫn authorization, version và field update semantics.

### Hướng tốt hơn

Nhận DTO request, validate, load entity managed qua JPA, áp domain method rõ. Đừng phụ thuộc vào callback để sửa state của một object được tạo từ JSON.

## 55. @PostLoad và serialization

Khi trả entity trực tiếp ra JSON:

~~~java
return productRepository.findById(id).orElseThrow();
~~~

serializer có thể truy cập getters, bao gồm getter của transient field và LAZY relationships, sau khi transaction đã đóng.

### PostLoad không giải quyết lazy serialization

Không có nghĩa callback đã tải toàn bộ graph. Jackson có thể vẫn gây `LazyInitializationException` hoặc phát thêm SQL nếu OSIV còn mở.

### Hướng tốt hơn

Trong service:

1. Query dữ liệu đúng use case.
2. Map sang DTO rõ fields.
3. Không expose associations hoặc internal transient state vô tình.
4. Kết thúc transaction trước khi trả HTTP response theo architecture phù hợp.

**Một entity callback không thay thế API response design.**

## 56. Performance: callback càng rộng càng cần nhỏ

Một callback chạy trên entity được load từ nhiều chỗ:

~~~text
Product detail page:      1 Product
Product list page:      100 Products
Nightly export:      50.000 Products
Data import compare: 200.000 Products
~~~

Nếu mỗi `@PostLoad` tốn 1 ms CPU không cần thiết:

~~~text
50.000 entities × 1 ms = 50 giây CPU cộng dồn
~~~

chưa tính network/SQL nếu callback thực hiện IO.

### Nguyên tắc tối ưu

- Không truy cập repository/remote services.
- Không tạo object graph khổng lồ.
- Không format theo locale/timezone của user nếu entity dùng chung nhiều contexts.
- Không chuyển đổi dữ liệu lớn khi chỉ một số use cases cần.
- Dùng DTO projection cho batch/reporting khi không cần entity lifecycle.
- Nếu derived value đơn giản, computed getter có thể là lựa chọn tốt.

Một callback nhỏ có thể ổn, nhưng callback được gọi **ngầm** có chi phí khó nhìn thấy hơn code service.

## 57. Thread-safety và EntityManager lifecycle

EntityManager thường **không thread-safe**. Một managed entity thuộc về persistence context đang xử lý; đừng dùng cùng EntityManager giữa các threads để mong callback chạy ổn định.

### Listener không nên lưu state mỗi request

Ví dụ anti-pattern:

~~~java
public class CounterListener {
    private int loadCount;

    @PostLoad
    void afterLoad(Object entity) {
        loadCount++;
    }
}
~~~

Biến `loadCount` không có contract rõ về concurrency/lifecycle; listener có thể được provider/container khởi tạo/chia sẻ theo cách khác mong đợi.

### Nếu cần metrics

Đo SQL/cache/entity load statistics qua instrumentation ở tầng provider/observability. Nếu bắt buộc custom load metrics, cân nhắc service boundary và test concurrency/privacy, không gắn counter mutable tùy ý vào listener production.

## 58. Troubleshooting: PostLoad không chạy

Một số nguyên nhân có thể:

| Triệu chứng | Nguyên nhân cần xem xét |
| --- | --- |
| `new Product()` không chạy callback | Constructor không phải JPA load |
| `persist(product)` không chạy PostLoad | Persist là lifecycle phase khác |
| `find()` lần hai không chạy thêm | Product đã managed trong L1 |
| Query DTO không gọi Product PostLoad | Không load managed Product |
| Entity listener không được gọi | `@EntityListeners` thiếu/sai class/mapping |
| Callback method có tham số trong entity | Sai signature |
| Listener method không nhận entity param đúng | Sai signature hoặc mapping |
| Callback static/final hoặc return type sai | Không portable/không hợp lệ |
| Default listener không chạy | Exclusion annotation hoặc XML mapping |
| Listener superclass không chạy | Inheritance/exclusion/override rules |
| Cache USE cho load mà không thấy SELECT | L2 hit, không chứng minh callback không chạy |
| `getReference()` không tạo SQL/callback ngay | Proxy chưa initialized |
| Bulk JPQL UPDATE không gọi callback | Không load per-row entity |
| Product detached từ JSON không có callback | Không phải JPA load |
| Refresh không phản ánh giá mới | Isolation/cache/DB routing hoặc pending state |
| Callback gọi LAZY collection rồi lỗi | Truy cập graph không phù hợp |
| Callback làm UPDATE ngoài ý định | Sửa persistent mapped attributes |
| Runtime summary sai sau setter | Derived transient không được recompute |
| Callback lỗi làm query fail | Exception propagation/transaction |

### Cách chẩn đoán theo thứ tự

1. Xác nhận instance được **JPA load vào persistence context** thực sự.
2. Xác nhận mapping `@PostLoad` hoặc `@EntityListeners` đúng class/method.
3. Kiểm tra first-level cache và việc entity đã managed chưa.
4. Kiểm tra entity có được tạo từ DTO/JSON/constructor thay vì load không.
5. Xem mapped superclass, default listeners và exclusions.
6. Dùng integration test với EntityManagerFactory thực.
7. Đo SQL/cache nếu behavior có vẻ liên quan hiệu năng.

## 59. Quy trình thiết kế một PostLoad callback

Trước khi thêm `@PostLoad`:

1. Xác định **giá trị runtime** muốn khởi tạo sau load.
2. Kiểm tra có thể dùng computed getter hay map DTO rõ ràng hơn không.
3. Chỉ dùng các mapped scalar attributes chắc chắn có sẵn theo contract.
4. Giữ callback **thuần túy, deterministic, nhanh và không IO**.
5. Đặt field derived là `@Transient` nếu không muốn persist.
6. Đảm bảo constructor tạo entity mới cũng khởi tạo đúng.
7. Đảm bảo mọi domain mutations có thể thay đổi inputs sẽ cập nhật derived state.
8. Không phụ thuộc HTTP user/session, external service hoặc repository.
9. Không dùng callback để authorize hoặc phát business event.
10. Nếu dùng listener, giữ listener stateless và signature đúng.
11. Nếu dùng inheritance, hiểu default/superclass listener ordering và exclusions.
12. Kiểm thử load trong EntityManager mới, refresh và list query có quan hệ LAZY.
13. Đo query count để phát hiện N+1/hidden work.
14. Ghi rõ behavior khi state được cache và khi entity đã managed.

### Sơ đồ quyết định

~~~text
Có dữ liệu cần tính sau khi entity được load?
                     |
                     v
Chỉ phục vụ một API/DTO?
        |                      |
       Có                    Không
        |                      |
        v                      v
 Tính trong DTO          Có cần lưu runtime state
 projection/service?     trong entity không?
                               |
                      +--------+--------+
                     Không              Có
                      |                  |
                      v                  v
                Computed getter   Giá trị chỉ dùng scalar fields
                                  và tính nhanh/thuần túy?
                                          |
                                +---------+---------+
                               Không               Có
                                |                  |
                                v                  v
                       Chuyển về service      @Transient field
                       /query rõ ràng          + @PostLoad
                                                 |
                                                 v
                                       Constructor + domain methods
                                       cũng phải giữ state nhất quán
~~~

## 60. Bài tập thực hành

### Bài 1 — Nhận diện lifecycle event

Khi JPA provider load một Product lần đầu vào persistence context, annotation nào được dùng để chạy xử lý ngay sau sự kiện đó?

**Gợi ý:** `@PostLoad`.

### Bài 2 — Chữ ký phương thức

Trong entity, phương thức sau đúng hay sai?

~~~java
@PostLoad
public Product afterLoad(EntityManager em) {
    return this;
}
~~~

**Gợi ý:** sai; entity callback cần `void`, không tham số, không dùng EM parameter.

### Bài 3 — Listener class

Với `@EntityListeners(ProductLoadListener.class)`, listener method thường nhận tham số gì?

**Gợi ý:** entity instance đang nhận event, ví dụ `void afterLoad(Product product)`.

### Bài 4 — Two finds

Gọi `em.find(Product.class, 10L)` hai lần trên cùng EntityManager. Có chắc PostLoad được gọi hai lần không?

**Gợi ý:** không; L1 identity map thường trả cùng managed entity.

### Bài 5 — Cache

Không có SQL SELECT khi gọi find nhưng có một managed Product mới. PostLoad có thể liên quan không?

**Gợi ý:** có; entity có thể được hydrate từ shared cache.

### Bài 6 — Refresh

`em.refresh(product)` có liên quan gì đến PostLoad?

**Gợi ý:** refresh là một lifecycle event sau đó PostLoad được gọi theo JPA semantics.

### Bài 7 — Pending changes

Sửa price trong entity nhưng chưa flush, rồi gọi refresh. Điều gì có thể xảy ra?

**Gợi ý:** refresh có thể ghi đè thay đổi chưa flush bằng DB state.

### Bài 8 — DTO projection

Một JPQL constructor projection chỉ trả `ProductDto`, có cần chạy Product.@PostLoad cho mỗi DTO không?

**Gợi ý:** không; không load managed Product tương ứng.

### Bài 9 — Constructor

Vì sao entity mới được `new` không thể phụ thuộc @PostLoad để xây displayName?

**Gợi ý:** chưa có JPA load event; constructor/domain method phải khởi tạo.

### Bài 10 — Derived state stale

PostLoad xây `summary = name + price`, sau đó setter đổi price. Summary có tự cập nhật không?

**Gợi ý:** không; recompute trong domain method hoặc computed getter.

### Bài 11 — Lazy association

Một PostLoad gọi `order.getLines().size()` cho 1.000 Orders. Rủi ro gì?

**Gợi ý:** N+1/hidden SQL và graph loading side effects.

### Bài 12 — Service call

Có nên inject repository rồi query Categories từ PostLoad của Product không?

**Gợi ý:** không phải thiết kế portable/đơn giản; chuyển query sang service/fetch plan.

### Bài 13 — Security

Có thể coi PostLoad kiểm tra `CurrentUser.tenantId()` là authorization đầy đủ không?

**Gợi ý:** không; không chạy trên mọi access và phụ thuộc request context.

### Bài 14 — External HTTP

Vì sao gửi webhook trong @PostLoad có thể tạo 1.000 requests ngoài ý muốn?

**Gợi ý:** callback được gọi khi nhiều entities được materialize từ một query.

### Bài 15 — Persistent field mutation

PostLoad gọi `name = name.trim()` trên persistent field có rủi ro gì?

**Gợi ý:** dirty checking/UPDATE/version tăng ngoài ý muốn.

### Bài 16 — Transient vs JSON

Một field có `@Transient` có chắc không xuất hiện trong JSON response không?

**Gợi ý:** không; JPA mapping và JSON serializer là cơ chế khác nhau.

### Bài 17 — Inheritance

Callback trong `@MappedSuperclass` có thể liên quan đến load event của entity subclass không?

**Gợi ý:** có; cần hiểu override và ordering rules.

### Bài 18 — Exclude annotations

`@ExcludeDefaultListeners` và `@ExcludeSuperclassListeners` dùng để điều khiển cái gì?

**Gợi ý:** default/superclass listener application theo lifecycle rules; không đơn giản xóa mọi callback method.

### Bài 19 — Read-only transaction

Entity được load trong `@Transactional(readOnly=true)`. Có chắc PostLoad bị tắt không?

**Gợi ý:** không; read-only không tự vô hiệu hóa lifecycle callback.

### Bài 20 — @PostConstruct

`@PostConstruct` của Spring/CDI bean có phải JPA entity load event không?

**Gợi ý:** không; dùng `jakarta.persistence.PostLoad` cho JPA entity lifecycle.

### Bài 21 — Bulk UPDATE

Một JPQL bulk UPDATE thay giá của 500 Product. Có bắt buộc gọi PostLoad cho 500 rows không?

**Gợi ý:** không; bulk update không load entity per row.

### Bài 22 — Mapped field conversion

Khi chỉ muốn chuyển column code thành value object tương ứng, nên cân nhắc `AttributeConverter` hay PostLoad?

**Gợi ý:** `AttributeConverter` đúng trách nhiệm mapping hơn.

### Bài 23 — Business event

Một đơn hàng được load bởi màn hình admin. Có nên từ PostLoad phát sự kiện `OrderConfirmed` không?

**Gợi ý:** không; load không phải hành động confirm.

### Bài 24 — Integration test

Vì sao cần đóng EntityManager sau persist fixture rồi mở context mới để test PostLoad?

**Gợi ý:** entity persist vẫn managed ở context cũ, find có thể trả ngay instance cũ.

### Bài 25 — L1 và L2

Gọi `CacheRetrieveMode.BYPASS` lần hai trong cùng EntityManager có chắc làm PostLoad chạy lại không?

**Gợi ý:** không; BYPASS chủ yếu áp dụng L2 chứ không bỏ L1.

### Bài 26 — Callback exception

Một callback ném unchecked exception khi load. Có thể chỉ log warning rồi mặc định transaction vẫn khỏe không?

**Gợi ý:** không; load có thể thất bại/transaction rollback-only, cần xử lý đúng boundary.

### Bài 27 — Performance

Một callback tốn 2 ms CPU và 50.000 entities được load trong export. Tổng chi phí callback là bao nhiêu?

**Gợi ý:** 100 giây CPU cộng dồn, chưa tính IO/overhead.

### Bài 28 — Test count

Tại sao chỉ assert callback counter từ một query duy nhất có thể gây sai nhận định?

**Gợi ý:** entities có thể đã managed, JOIN rows trùng, L2/cache/fixtures ảnh hưởng.

### Bài 29 — EntityGraph

`@PostLoad` có bảo đảm mọi LAZY association đã được load trước khi callback chạy không?

**Gợi ý:** không; dùng fetch plan/service logic khi cần graph.

### Bài 30 — Quyết định kiến trúc

Một Product cần hiển thị chuỗi `name + price` duy nhất ở một endpoint. Có nhất thiết phải dùng PostLoad không?

**Gợi ý:** không; computed getter hoặc DTO mapper có thể rõ ràng hơn.

## 61. Bảng ghi nhớ nhanh

| Câu hỏi | Quy tắc |
| --- | --- |
| Hook sau khi JPA tải entity là gì? | `@PostLoad` |
| Hook thuộc package nào? | `jakarta.persistence` (Jakarta Persistence 3.x) |
| Entity callback signature? | `void method()` |
| Listener callback signature? | `void method(EntityType entity)` |
| Được khai báo trong mapped superclass? | Có, theo lifecycle inheritance rules |
| Entity đã managed, find lại? | Thường không tạo load/callback mới |
| Load từ second-level cache? | Có thể có PostLoad dù không SQL SELECT |
| `EntityManager.refresh()`? | Load lại managed entity, PostLoad theo lifecycle rules |
| Callback chạy khi `new Entity()`? | Không |
| Callback chạy chỉ vì `persist()`? | Không, đó là phase khác |
| JPQL DTO projection? | Không mặc định load entity/không đòi PostLoad |
| `getReference()`? | Proxy reference chưa chắc đã load state |
| Có nên query trong callback? | Không cho portable, dễ N+1/re-entrant |
| Có nên sửa persistent fields? | Tránh để không dirty/update ngoài ý muốn |
| Derived state không persist? | `@Transient` |
| Derived state sau setter có tự mới? | Không; recompute hoặc computed getter |
| `@PostConstruct` có tương đương? | Không |
| `@EntityListeners` để làm gì? | Tách callback vào listener class |
| Listener nên lưu mutable state? | Không, nên stateless |
| Callback là authorization hook? | Không |
| Callback là business event? | Không |
| Callback gửi HTTP/email? | Không nên |
| Exception trong callback? | Có thể làm load/transaction thất bại |
| L1 clear có làm PostLoad có cơ hội chạy lại? | Có khi load lại, nhưng clear có tác động khác |
| L2 BYPASS có buộc reload managed entity? | Không |
| Test đúng? | Persist fixture, EntityManager mới, load thật |
| Performance? | Giữ callback nhỏ, không IO/lazy graph |

## Kết luận

**`@PostLoad` là callback chuẩn của JPA để xử lý sự kiện sau khi một entity được tải vào persistence context hoặc được refresh.** Callback có thể nằm trực tiếp trong entity/mapped superclass hoặc trong class được đăng ký qua `@EntityListeners`. Nó phù hợp nhất với việc **khởi tạo một lượng nhỏ trạng thái `@Transient`, thuần túy và có thể xác định từ các persistent attributes đã được nạp**.

Điều cần nhớ là **load lifecycle khác với gọi phương thức Java và khác với SQL SELECT**. Một `EntityManager` có first-level identity map; entity đã managed có thể được trả lại mà không tạo load mới. Provider cũng có thể phục vụ state từ shared cache; ngược lại, một query DTO hoặc bulk update không nhất thiết tạo managed entities. Khi `refresh()`, JPA có thể gọi PostLoad lại nhưng đồng thời thay đổi persistent state trong RAM theo database và transaction visibility.

Hãy **tránh biến PostLoad thành một service ẩn**: không query repository, không fetch LAZY graph tùy tiện, không gửi thông báo, không ủy quyền truy cập, không thay đổi persistent columns chỉ vì entity được đọc. Nếu derived state phải đổi cùng setter, hãy tính lại bằng domain method hoặc computed getter; nếu chỉ phục vụ API, DTO mapper thường rõ hơn. Cuối cùng, kiểm thử bằng **EntityManager thực, context mới và những fetch patterns đại diện** để xác nhận event wiring, behavior khi refresh và chi phí SQL.

Nguyên tắc thực hành là **dùng `@PostLoad` cho khởi tạo runtime state nhỏ và deterministic, dùng transaction/service cho nghiệp vụ, và dùng query/DTO/fetch plan cho nhu cầu dữ liệu cụ thể**. Ranh giới đó giúp lifecycle callback hữu ích mà không làm thay đổi ngầm tính nhất quán hoặc hiệu năng của lớp persistence.
