# Nhận diện trạng thái tải và khởi tạo có chủ đích trong Hibernate

Khi Hibernate trả về một entity, không phải mọi association, collection hoặc thuộc tính lazy đều đã được tải từ database. Một object có thể đang **managed** trong persistence context nhưng vẫn chứa proxy chưa khởi tạo hoặc collection chưa được nạp. Vì vậy, khi cần biết dữ liệu nào đã sẵn sàng và khi nào nên tải phần còn thiếu, ứng dụng cần phân biệt ba trạng thái:

- **Managed:** entity thuộc persistence context và được Hibernate theo dõi.
- **Loaded/initialized:** entity, proxy, collection hoặc thuộc tính cụ thể đã có dữ liệu cần thiết trong bộ nhớ.
- **Detached:** object không còn được persistence context quản lý; những phần lazy chưa tải có thể không còn khả năng tải tiếp.

Bài này giải thích cách **nhận diện trạng thái tải** bằng JPA và Hibernate, cách **khởi tạo có chủ đích** bằng API phù hợp, và cách chọn fetch plan để dữ liệu được tải đúng nơi cần dùng. Nội dung áp dụng cho Hibernate ORM 6.x và Jakarta Persistence. Một số API kiểm tra trạng thái thuộc Hibernate-specific; nếu cần code portable giữa JPA providers, hãy ưu tiên API chuẩn.

## 1. Vì sao phải nhận diện trạng thái tải?

Giả sử một đơn hàng có khách hàng và nhiều dòng hàng:

~~~java
PurchaseOrder order =
        entityManager.find(PurchaseOrder.class, 42L);

Customer customer = order.getCustomer();
List<OrderItem> items = order.getItems();
~~~

Nếu các association được ánh xạ LAZY, khi find hoàn tất:

- `order` có thể là entity managed đã tải.
- `customer` có thể là proxy/reference chưa khởi tạo.
- `items` có thể là persistent collection wrapper chưa tải nội dung.
- Một số basic attributes cũng có thể chưa được tải nếu dùng lazy attribute loading với bytecode enhancement.

Việc có một Java reference không chứng minh dữ liệu đích đã được đọc từ DB. Nếu code gọi `customer.getName()` hoặc lặp qua `items`, Hibernate có thể phát SQL để khởi tạo phần tương ứng.

~~~mermaid
flowchart TD
    A["Entity được tải"] --> B["Entity managed"]
    B --> C["Association to-one"]
    B --> D["Collection"]
    B --> E["Basic lazy attribute"]
    C --> F["Proxy/reference có thể chưa initialized"]
    D --> G["PersistentCollection có thể chưa initialized"]
    E --> H["Field có thể chưa loaded"]
    F --> I["Kiểm tra trạng thái"]
    G --> I
    H --> I
    I --> J["Chọn fetch plan hoặc initialize"]
~~~

Nhận diện trạng thái hữu ích khi:

- Chuẩn bị serialize dữ liệu hoặc dựng DTO mà không muốn vô tình phát thêm SQL.
- Debug N+1 query và xác định association nào bị khởi tạo trong vòng lặp.
- Xử lý entity trước khi đóng transaction/session.
- Viết logging, audit hoặc mapper không được phép truy cập lazy state tùy tiện.
- Tối ưu một use case chỉ cần một phần object graph.

**Managed không đồng nghĩa loaded toàn bộ.** Một entity có thể managed trong khi các association lazy vẫn chưa khởi tạo.

## 2. Proxy, persistent collection và lazy attribute khác nhau thế nào?

### 2.1. Proxy cho association to-one

Với quan hệ `@ManyToOne(fetch = LAZY)` hoặc một số mapping `@OneToOne`, Hibernate có thể trả về một proxy đại diện cho entity đích. Proxy giữ định danh và có thể trì hoãn việc đọc các thuộc tính khác tới lúc cần.

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "customer_id")
private Customer customer;
~~~

Sau khi tải `PurchaseOrder`, `getCustomer()` có thể trả một reference mà chưa đọc hàng `customers` tương ứng. Truy cập ID thường không cần khởi tạo proxy vì ID đã biết từ khóa ngoại; truy cập `getName()` thường cần tải target.

Không nên dùng `customer == null` để kết luận proxy đã được khởi tạo. Một proxy chưa khởi tạo vẫn là một object khác null. Nếu FK là null thì association có thể thực sự null; đó là trạng thái khác.

### 2.2. Persistent collection cho to-many

Với `@OneToMany` hoặc `@ManyToMany`, Hibernate thường dùng một collection wrapper như `PersistentBag`, `PersistentSet` hoặc implementation tương ứng. Wrapper có thể tồn tại trong Java trước khi các phần tử được tải.

~~~java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderItem> items = new ArrayList<>();
~~~

`order.getItems()` có thể trả wrapper chưa khởi tạo. Các thao tác như `size()`, `iterator()`, `contains()` hoặc truy cập phần tử có thể kích hoạt tải collection, tùy operation, extra-lazy behavior và mapping. Đừng giả định mọi method trên collection đều có cùng chi phí SQL.

### 2.3. Lazy basic attribute với bytecode enhancement

Một thuộc tính scalar cũng có thể được tải trễ khi mapping và enhancement hỗ trợ:

~~~java
@Basic(fetch = FetchType.LAZY)
@Lob
private String longDescription;
~~~

Đối với basic attributes, Hibernate thường cần bytecode enhancement để intercept việc truy cập field và tải lazy group tương ứng. Cơ chế này khác proxy entity và khác persistent collection. Vì vậy, kiểm tra một entity proxy đã initialized không đủ để kết luận mọi basic lazy attributes đã loaded.

## 3. Kiểm tra trạng thái bằng JPA portable API

Nếu muốn code ít phụ thuộc Hibernate, dùng `PersistenceUnitUtil` từ `EntityManagerFactory`.

~~~java
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.PersistenceUnitUtil;

public class LoadStateInspector {
    private final PersistenceUnitUtil persistenceUtil;

    public LoadStateInspector(EntityManagerFactory emf) {
        this.persistenceUtil = emf.getPersistenceUnitUtil();
    }

    public boolean isCustomerLoaded(PurchaseOrder order) {
        return persistenceUtil.isLoaded(order, "customer");
    }

    public boolean isOrderLoaded(PurchaseOrder order) {
        return persistenceUtil.isLoaded(order);
    }
}
~~~

Hoặc lấy tiện ích trực tiếp:

~~~java
PersistenceUnitUtil util =
        entityManagerFactory.getPersistenceUnitUtil();

boolean entityLoaded = util.isLoaded(order);
boolean customerLoaded = util.isLoaded(order, "customer");
boolean itemsLoaded = util.isLoaded(order, "items");
~~~

### 3.1. `isLoaded(entity)`

`isLoaded(entity)` kiểm tra trạng thái loaded của entity theo hợp đồng JPA. Cách diễn giải phải gắn với các thuộc tính bắt buộc eager theo mapping và fetch plan. Nó không phải lệnh “đảm bảo tất cả association trong toàn bộ object graph đã được tải”.

Một entity có thể được xem là loaded trong khi association LAZY chưa được khởi tạo. Do đó, nếu mục tiêu là kiểm tra `customer` hoặc `items`, dùng overload theo tên thuộc tính.

### 3.2. `isLoaded(entity, attributeName)`

Overload theo thuộc tính cho biết trạng thái loaded của attribute cụ thể theo semantics của JPA:

~~~java
if (util.isLoaded(order, "customer")) {
    // Attribute customer đã được load theo trạng thái JPA.
} else {
    // Chưa được load; không truy cập getter chỉ để kiểm tra.
}
~~~

Tên thuộc tính là **tên field/property Java trong mapping**, không phải tên cột SQL. Ví dụ dùng `"customer"` thay vì `"customer_id"`.

Kiểm tra trạng thái không nên làm phát sinh việc khởi tạo association chỉ để xem nó đã khởi tạo hay chưa. Đây là lý do nên dùng API kiểm tra thay vì gọi getter rồi suy luận từ object trả về.

### 3.3. `PersistenceUtil`

Jakarta Persistence cũng có `Persistence.getPersistenceUtil()` để lấy tiện ích kiểm tra load state dùng chung:

~~~java
import jakarta.persistence.Persistence;
import jakarta.persistence.PersistenceUtil;

PersistenceUtil util = Persistence.getPersistenceUtil();
boolean loaded = util.isLoaded(order, "items");
~~~

`PersistenceUnitUtil` lấy từ factory cụ thể; `PersistenceUtil` là tiện ích chuẩn chung. Khi ứng dụng có nhiều persistence unit hoặc provider, cần dùng đúng factory/persistence unit để tránh kiểm tra nhầm context.

### 3.4. Portable API không cung cấp mọi chi tiết nội bộ

JPA tập trung vào việc attribute/entity đã loaded theo contract. Nó không cung cấp toàn bộ thông tin về proxy implementation, collection wrapper, dirty tracker hoặc lazy group nội bộ. Nếu cần những thông tin đó để debug Hibernate, có thể dùng Hibernate API.

## 4. Kiểm tra trạng thái bằng Hibernate API

Hibernate cung cấp class tiện ích `org.hibernate.Hibernate`. Các phương thức thường dùng trong Hibernate 6.x gồm `isInitialized`, `initialize`, `isPropertyInitialized` và `unproxy`.

~~~java
import org.hibernate.Hibernate;
~~~

### 4.1. `Hibernate.isInitialized(Object)`

Phương thức này kiểm tra proxy hoặc persistent collection đã được khởi tạo chưa:

~~~java
boolean customerInitialized =
        Hibernate.isInitialized(order.getCustomer());

boolean itemsInitialized =
        Hibernate.isInitialized(order.getItems());
~~~

Cách đọc kết quả:

- `false`: proxy/collection vẫn chưa initialized.
- `true`: proxy/collection đã initialized hoặc object không cần khởi tạo theo cơ chế đó.

Đây là Hibernate-specific API, hữu ích khi code biết chắc đang chạy với Hibernate. Với association to-one, truyền proxy/reference; với to-many, truyền persistent collection wrapper.

Không nên gọi `Hibernate.initialize()` rồi mới `isInitialized()` nếu mục đích chỉ là kiểm tra. `initialize()` có thể phát SQL và thay đổi trạng thái tải.

### 4.2. `Hibernate.isPropertyInitialized(entity, propertyName)`

Với enhanced lazy attributes, cần kiểm tra thuộc tính cụ thể:

~~~java
boolean descriptionLoaded =
        Hibernate.isPropertyInitialized(product, "longDescription");
~~~

Phương thức này kiểm tra property đã được khởi tạo hay chưa theo cơ chế Hibernate. Nó đặc biệt hữu ích khi dùng bytecode-enhanced lazy attribute loading, nơi entity object có thể đã loaded nhưng một basic field vẫn chưa được tải.

Tên property là tên thuộc tính entity. Đây là API Hibernate-specific; nếu code cần chạy trên provider khác, ưu tiên `PersistenceUnitUtil.isLoaded(entity, attributeName)` và xác nhận provider hỗ trợ mapping tương ứng.

### 4.3. Kiểm tra managed state khác loaded state

Hibernate/JPA cũng có API kiểm tra entity có thuộc persistence context hay không:

~~~java
boolean managed = entityManager.contains(order);
~~~

`contains()` trả lời entity có managed trong EntityManager hiện tại không, không trả lời association đã loaded hay chưa.

| Câu hỏi | API phù hợp |
| --- | --- |
| Entity có managed trong EntityManager này không? | `EntityManager.contains(entity)` |
| Entity/attribute đã loaded theo JPA chưa? | `PersistenceUnitUtil.isLoaded(...)` |
| Proxy/collection Hibernate đã initialized chưa? | `Hibernate.isInitialized(...)` |
| Property lazy cụ thể đã initialized chưa? | `Hibernate.isPropertyInitialized(...)` |

Một entity detached có thể vẫn là object Java với mọi field đã tải; `contains()` trả false nhưng dữ liệu vẫn có sẵn. Ngược lại, entity managed có thể có proxy/collection chưa initialized.

## 5. Khởi tạo có chủ đích bằng `Hibernate.initialize()`

Nếu code thực sự cần một proxy hoặc collection trước khi Session đóng, Hibernate cung cấp:

~~~java
Hibernate.initialize(order.getCustomer());
Hibernate.initialize(order.getItems());
~~~

`initialize()` yêu cầu Hibernate khởi tạo proxy hoặc persistent collection nếu chúng chưa được khởi tạo. Nếu object đã initialized, thao tác thường không cần tải lại.

### 5.1. Khởi tạo trong transaction đang mở

~~~java
@Transactional(readOnly = true)
public OrderDetails loadDetails(long orderId) {
    PurchaseOrder order =
            entityManager.find(PurchaseOrder.class, orderId);

    if (order == null) {
        throw new OrderNotFoundException(orderId);
    }

    Hibernate.initialize(order.getCustomer());
    Hibernate.initialize(order.getItems());

    return OrderDetails.from(order);
}
~~~

`OrderDetails`, `OrderNotFoundException` và `from()` là thành phần domain/API minh họa. Các imports Spring/JPA/Hibernate cần được thêm theo ứng dụng.

Điểm quan trọng: **khởi tạo phải xảy ra khi persistence context còn hoạt động**. Nếu proxy chưa initialized và Session đã đóng, Hibernate không còn context/connection phù hợp để tải dữ liệu và có thể ném `LazyInitializationException`.

### 5.2. `initialize()` không tải đệ quy toàn bộ graph

Giả sử `order` có `items`, và mỗi item có `product` LAZY. Gọi:

~~~java
Hibernate.initialize(order.getItems());
~~~

chỉ đảm bảo collection `items` được khởi tạo. Nó **không cam kết** tất cả `item.getProduct()`, `product.getCategory()` hay các association lồng nhau đều được tải. Nếu code sau đó truy cập các quan hệ lồng nhau, chúng vẫn có thể phát SQL hoặc lỗi sau khi Session đóng.

Hãy kiểm tra từng attribute cần thiết và thiết kế fetch plan cho graph mong muốn. Không dùng một lệnh initialize như thể nó tải toàn bộ cây entity.

### 5.3. Collection có thể rất lớn

`Hibernate.initialize(order.getItems())` tải toàn bộ collection theo mapping. Nếu order có hàng trăm nghìn item, đây có thể là thao tác tốn memory/DB. Trước khi initialize, hãy hỏi:

- Use case có thực sự cần toàn bộ phần tử không?
- Có thể dùng query phân trang/projection thay vì collection không?
- Có thể lọc theo điều kiện ở DB không?
- Collection có được batch fetch hay cache phù hợp không?

Khởi tạo có chủ đích nghĩa là **chỉ tải dữ liệu mà caller thật sự cần**, không phải khởi tạo mọi thứ cho tiện.

## 6. Unproxy và truy cập lớp entity thực

Với proxy to-one, đôi khi code cần lấy entity đích thực thay vì proxy wrapper. Hibernate cung cấp:

~~~java
Customer customer =
        Hibernate.unproxy(order.getCustomer(), Customer.class);
~~~

`unproxy()` trả về object đã được unproxy; nếu proxy chưa initialized, thao tác có thể cần khởi tạo nó và phát SQL. Nếu target không tồn tại hoặc proxy không tương thích kiểu, có thể phát sinh exception.

Không nên gọi `unproxy()` chỉ để log class name hay so sánh object. Nếu chỉ cần kiểm tra đã initialized hay chưa, dùng `Hibernate.isInitialized()`. Nếu chỉ cần ID, đọc identifier qua mapping/proxy theo cách phù hợp mà không tải toàn bộ target.

### 6.1. Proxy class không nhất thiết bằng entity class

Với proxy subclass, `object.getClass()` có thể trả về class proxy thay vì class entity thực. Không nên dùng phép so sánh class trực tiếp như cách nhận diện loaded state. Nếu cần type thật, dùng API Hibernate phù hợp và hiểu rằng một số cách lấy class thực có thể initialize proxy.

### 6.2. `unproxy()` không thay thế fetch plan

Nếu một API cần customer name, tốt hơn là query DTO hoặc fetch join customer ngay từ đầu. Unproxy là thao tác xử lý object graph đã có, không phải chiến lược tổng quát để tối ưu số SQL.

## 7. Khởi tạo bằng fetch join hoặc EntityGraph

Nếu biết trước dữ liệu nào cần, hãy định nghĩa fetch plan tại query. Cách này thường rõ ràng hơn việc tải root rồi gọi nhiều `Hibernate.initialize()` rải rác.

### 7.1. Fetch join

~~~java
PurchaseOrder order = entityManager.createQuery(
        "select o from PurchaseOrder o " +
        "join fetch o.customer " +
        "left join fetch o.items " +
        "where o.id = :id",
        PurchaseOrder.class
    )
    .setParameter("id", orderId)
    .getSingleResult();
~~~

Một query có thể lấy customer và items cùng order. Tuy nhiên, fetch join collection làm result set có nhiều dòng lặp root; không kết hợp tùy tiện nhiều collection lớn hoặc pagination.

### 7.2. EntityGraph

~~~java
@Entity
@NamedEntityGraph(
    name = "PurchaseOrder.details",
    attributeNodes = {
        @NamedAttributeNode("customer"),
        @NamedAttributeNode("items")
    }
)
public class PurchaseOrder {
    // Các field và mapping còn lại.
}
~~~

Dùng graph:

~~~java
EntityGraph<?> graph =
        entityManager.getEntityGraph("PurchaseOrder.details");

PurchaseOrder order = entityManager.find(
        PurchaseOrder.class,
        orderId,
        Map.of("jakarta.persistence.fetchgraph", graph)
);
~~~

EntityGraph mô tả attribute cần được fetch theo use case. Provider có thể dùng JOIN hoặc SELECT; graph không bắt buộc một câu SQL duy nhất. Nếu graph có collection lớn, vẫn phải xem result set và query plan.

### 7.3. DTO projection

Nếu caller chỉ cần tên khách hàng và số dòng hàng, có thể query DTO:

~~~java
public record OrderSummary(
        Long orderId,
        String customerName,
        Long itemCount
) {}
~~~

~~~java
List<OrderSummary> summaries = entityManager.createQuery(
        "select new com.example.api.OrderSummary(" +
        "o.id, c.name, count(i)) " +
        "from PurchaseOrder o " +
        "join o.customer c " +
        "left join o.items i " +
        "group by o.id, c.name",
        OrderSummary.class
    )
    .getResultList();
~~~

`com.example.api.OrderSummary` là package minh họa. Projection tránh việc tạo managed entity graph lớn khi chỉ cần dữ liệu đọc. Nó cũng tránh phụ thuộc vào lazy initialization sau khi transaction kết thúc.

## 8. Nhận diện trạng thái trong mapper, serializer và logging

Một mapper có thể vô tình kích hoạt lazy loading:

~~~java
public OrderDto toDto(PurchaseOrder order) {
    return new OrderDto(
        order.getId(),
        order.getCustomer().getName(),
        order.getItems().size()
    );
}
~~~

Code này đọc customer name và items size. Nếu association chưa initialized, mapper có thể phát SQL. Nếu Session đã đóng, có thể lỗi. Nếu mapper chạy trong vòng lặp cho nhiều orders, có thể tạo N+1.

### 8.1. Kiểm tra trước khi truy cập

Với Hibernate:

~~~java
boolean customerLoaded =
        Hibernate.isInitialized(order.getCustomer());

boolean itemsLoaded =
        Hibernate.isInitialized(order.getItems());

if (!customerLoaded || !itemsLoaded) {
    throw new IllegalStateException(
        "Order graph was not fetched for this mapping"
    );
}
~~~

Đây là cách fail-fast trong mapper nếu hợp đồng yêu cầu graph phải được tải trước. Không nên tự động initialize trong mapper dùng chung, vì nó che giấu query phát sinh và khiến cùng một mapper có chi phí DB khó dự đoán.

Với JPA portable:

~~~java
PersistenceUnitUtil util =
        entityManagerFactory.getPersistenceUnitUtil();

if (!util.isLoaded(order, "customer")
        || !util.isLoaded(order, "items")) {
    throw new IllegalStateException("Required data is not loaded");
}
~~~

Kiểm tra chỉ phù hợp khi mapper có quyền truy cập utility và attribute name chính xác. Có thể thiết kế DTO query riêng để không cần kiểm tra runtime ở mọi call site.

### 8.2. Không gọi getter để “thử xem đã load chưa”

Đoạn sau có thể tự khởi tạo proxy:

~~~java
Object customer = order.getCustomer();
String name = order.getCustomer().getName();
~~~

Dòng đầu chỉ lấy reference; dòng sau có thể tải target. Nếu mục tiêu chỉ là quan sát, dùng API `isLoaded`/`isInitialized`, không gọi getter thuộc tính thực để kiểm tra.

### 8.3. JSON serialization có thể kích hoạt tải ngoài dự kiến

Nếu trả entity trực tiếp qua REST, serializer có thể gọi getter trên association và vô tình kích hoạt lazy loading. Hậu quả gồm N+1, vòng tham chiếu vô hạn, dữ liệu quá lớn hoặc `LazyInitializationException`.

Cách tốt hơn:

1. Xác định JSON contract bằng DTO.
2. Query/fetch dữ liệu DTO cần trong transaction.
3. Trả DTO sau khi transaction kết thúc.
4. Không để serializer tùy ý duyệt entity graph.

## 9. Trạng thái tải và vòng đời Session

### 9.1. Managed entity, detached entity và initialized proxy

| Tình trạng | `EntityManager.contains(entity)` | Association lazy có thể tải thêm? |
| --- | --- | --- |
| Managed, association chưa initialized | true | Có, khi context còn hoạt động |
| Managed, association initialized | true | Dữ liệu association đã có; association lồng nhau vẫn có thể lazy |
| Detached, association đã initialized | false | Dữ liệu đã tải vẫn có thể đọc từ object |
| Detached, association chưa initialized | false | Thường không thể tải; có thể ném `LazyInitializationException` |
| Entity mới/transient | false | Không có persistence context quản lý để tải association |

Một entity detached không tự trở thành managed khi gọi getter. Việc có thể đọc field đã tải không có nghĩa Hibernate vẫn theo dõi thay đổi.

### 9.2. Kiểm tra sau khi Session đóng

Có thể kiểm tra trạng thái bằng Hibernate API ngay cả khi Session đã đóng:

~~~java
boolean initialized =
        Hibernate.isInitialized(detachedOrder.getItems());
~~~

Nếu kết quả false, đừng gọi `Hibernate.initialize()` ở ngoài Session và mong nó tự mở kết nối. Hãy mở transaction/context mới, tải lại entity theo fetch plan hoặc lấy DTO mới.

### 9.3. Không giữ Session chỉ để tránh lỗi lazy

Open Session in View có thể giữ persistence context mở tới giai đoạn render response, nhưng nó cũng cho phép SQL phát sinh ngoài service transaction dự kiến và dễ tạo N+1. Không nên xem đây là giải pháp thay thế fetch plan. Định nghĩa dữ liệu cần trong transaction/use case thường dễ kiểm soát hơn.

## 10. Khởi tạo có chủ đích trong các tình huống cụ thể

### Tình huống A — Tạo DTO cần một to-one

Nếu chỉ cần tên khách hàng, dùng fetch join hoặc query DTO. `Hibernate.initialize(order.getCustomer())` có thể phù hợp trong service nhỏ khi entity đã tải và caller thực sự cần target, nhưng query plan thường rõ hơn.

### Tình huống B — Export cần toàn bộ collection

Nếu collection có kích thước vừa phải và nghiệp vụ thật sự cần toàn bộ, initialize trong transaction rồi map DTO. Nếu rất lớn, dùng query riêng có pagination/stream hoặc batch processing; không tải một collection khổng lồ chỉ để serialize.

### Tình huống C — Mapper dùng chung không được phát SQL

Kiểm tra `Hibernate.isInitialized()` hoặc JPA `isLoaded()` trước khi đọc association. Nếu graph không đủ, fail-fast hoặc gọi một query service có fetch plan rõ ràng. Đừng để mapper tự quyết định query.

### Tình huống D — Debug N+1

Log trạng thái trước và sau vòng lặp, kết hợp Hibernate SQL logging/statistics. Ví dụ:

~~~java
log.debug("items initialized before mapping: {}",
        Hibernate.isInitialized(order.getItems()));
~~~

Không log trực tiếp `order.getItems()` bằng `toString()` nếu implementation có thể duyệt collection và kích hoạt tải.

### Tình huống E — Entity detached từ cache/application layer

Không lưu entity proxy chưa initialized vào application cache rồi mong Session cũ tồn tại. Cache DTO hoặc immutable read model; nếu cần entity, tải lại bằng persistence context mới với fetch plan cụ thể.

## 11. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `contains(entity)` true nhưng getter association phát SQL | Managed không có nghĩa mọi association đã loaded | Dùng `isLoaded`/`isInitialized` và fetch plan |
| `getAssociation() != null` nhưng chưa có dữ liệu target | Proxy chưa initialized vẫn khác null | Dùng `Hibernate.isInitialized()` |
| `isLoaded(entity)` true nhưng collection vẫn lazy | Entity-level loaded không đồng nghĩa toàn graph loaded | Kiểm tra attribute cụ thể |
| `Hibernate.initialize()` sau khi Session đóng bị lỗi | Không còn persistence context để tải | Khởi tạo trong transaction hoặc reload |
| Initialize một collection làm memory tăng mạnh | Toàn bộ phần tử bị tải | Pagination/projection/query riêng |
| Initialize collection nhưng association lồng nhau vẫn lazy | `initialize()` không đệ quy toàn graph | Fetch graph cụ thể hoặc initialize thuộc tính cần |
| DTO mapper tạo N+1 | Getter trong mapper truy cập proxy từng entity | Fetch join, batch hoặc DTO query |
| JSON serialization gây LazyInitializationException | Serializer truy cập lazy state ngoài Session | Trả DTO |
| `getClass()` trả proxy class | Proxy subclass/bytecode enhancement | Dùng API Hibernate phù hợp nếu cần type thật |
| Basic lazy field đã loaded ngoài ý muốn | Enhancement/lazy group/fetch access | Kiểm tra enhancer và `isPropertyInitialized` |
| `unproxy()` phát SQL | Unproxy cần khởi tạo target | Dùng fetch plan nếu biết trước dữ liệu cần |

## 12. Đo lường việc tải có chủ đích

Khi điều tra fetch behavior, có thể bật SQL logging Hibernate 6 trong môi trường phát triển:

~~~properties
# Cấu hình logger qua Logback/Log4j/framework:
# org.hibernate.SQL = DEBUG
# org.hibernate.orm.jdbc.bind = TRACE
~~~

Logger `org.hibernate.SQL` hiển thị SQL; `org.hibernate.orm.jdbc.bind` có thể hiển thị bind parameters khi TRACE. Không bật bind trace rộng rãi trong production nếu dữ liệu có thông tin cá nhân hoặc bí mật.

Hibernate statistics cũng có thể hữu ích:

~~~properties
hibernate.generate_statistics=true
~~~

Theo dõi:

- Số entity fetch và collection fetch.
- Số query trên một use case.
- Cache hit/miss.
- Thời gian query và thời gian xử lý.
- Số dòng result set, kích thước collection.
- Trạng thái loaded trước/sau đoạn code cần điều tra.

Một query count thấp không luôn đồng nghĩa nhanh: JOIN lớn có thể trả nhiều dòng lặp. Ngược lại, một số SELECT nhỏ được batch có thể phù hợp hơn. Kết hợp log ORM với execution plan và monitoring DBMS.

## 13. Bảng chọn API phù hợp

| Mục tiêu | Lựa chọn |
| --- | --- |
| Code portable, kiểm tra attribute đã loaded | `PersistenceUnitUtil.isLoaded(entity, "attribute")` |
| Code portable, kiểm tra entity loaded | `PersistenceUnitUtil.isLoaded(entity)` |
| Kiểm tra entity managed trong context hiện tại | `EntityManager.contains(entity)` |
| Kiểm tra Hibernate proxy/collection initialized | `Hibernate.isInitialized(value)` |
| Kiểm tra lazy property với Hibernate enhancement | `Hibernate.isPropertyInitialized(entity, "property")` |
| Chủ động tải proxy/collection khi Session còn mở | `Hibernate.initialize(value)` |
| Lấy entity target thay proxy | `Hibernate.unproxy(value, EntityClass.class)` |
| Biết trước graph cần tải | Fetch join hoặc JPA EntityGraph |
| Chỉ cần một số field cho response | DTO projection |
| Nhiều proxy/collection lazy cần tải theo nhóm | Hibernate batch fetching |

## 14. Quy trình xử lý an toàn

1. **Xác định object/attribute cần dữ liệu.** Entity root, to-one, collection hay basic lazy property?
2. **Kiểm tra trạng thái đúng cấp.** Dùng JPA `isLoaded` cho portability, Hibernate `isInitialized`/`isPropertyInitialized` cho chi tiết provider.
3. **Không truy cập getter chỉ để kiểm tra.** Getter có thể khởi tạo proxy và phát SQL.
4. **Nếu biết trước nhu cầu, định nghĩa fetch plan ở query.** Fetch join, EntityGraph hoặc DTO projection.
5. **Nếu cần khởi tạo thủ công, thực hiện trong transaction/session đang hoạt động.** Dùng `Hibernate.initialize()` có chủ đích.
6. **Chỉ tải phần cần thiết.** Tránh initialize collection lớn hoặc toàn bộ graph.
7. **Map sang DTO trước khi đóng persistence context.** Đừng để serializer/mapper phát SQL bất ngờ.
8. **Nếu object đã detached và lazy state chưa tải, mở context mới và reload.** Không cố dùng Session cũ.
9. **Đo SQL và memory.** Kiểm tra N+1, row multiplication và query plan.
10. **Giữ fetch plan theo use case.** Không biến một nhu cầu của màn hình thành EAGER toàn cục.

## 15. Bài tập tự kiểm tra

1. Một entity `PurchaseOrder` managed có `customer` proxy chưa initialized. `EntityManager.contains(order)` trả lời câu hỏi nào? Có cho biết customer đã loaded không?
2. Vì sao `order.getCustomer() != null` không chứng minh hàng customer đã được tải?
3. Khi nào dùng `PersistenceUnitUtil.isLoaded(order, "customer")` thay cho `Hibernate.isInitialized(order.getCustomer())`?
4. `Hibernate.initialize(order.getItems())` có đảm bảo mọi `item.getProduct()` cũng initialized không?
5. Vì sao gọi `Hibernate.initialize()` sau khi Session đóng không thể tự tải proxy chưa initialized?
6. Một DTO mapper lặp qua 100 orders rồi gọi `getCustomer().getName()`. Có thể phát sinh vấn đề gì? Cách chọn fetch plan?
7. Khi cần kiểm tra lazy basic property `longDescription`, Hibernate API nào phù hợp?
8. Nếu chỉ cần customer name, vì sao DTO projection hoặc fetch join thường rõ ràng hơn gọi `unproxy()`?
9. `isLoaded(entity)` có nghĩa tất cả association trong toàn bộ graph đã tải không?
10. Vì sao không nên trả entity có proxy/collection lazy trực tiếp qua JSON serializer?

**Gợi ý:** (1) contains kiểm tra managed state, không kiểm tra loaded association; (2) proxy khác null dù chưa tải; (3) JPA portable API so với Hibernate-specific API; (4) không, initialize chỉ bảo đảm collection được tải; (5) không còn persistence context/Session; (6) N+1 hoặc lazy exception; (7) `Hibernate.isPropertyInitialized`; (8) fetch plan định nghĩa nhu cầu trước; (9) không; (10) serializer có thể vô tình kích hoạt SQL hoặc truy cập sau khi context đóng.

## 16. Tài liệu tham khảo

- [Hibernate ORM 6.6 User Guide – Fetching](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html#fetching): proxy, lazy fetching, batch fetching và các chiến lược tải.
- [Hibernate ORM 6.6 Javadocs – Hibernate](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/Hibernate.html): `isInitialized`, `initialize`, `isPropertyInitialized` và `unproxy`.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/): `PersistenceUnitUtil`, `PersistenceUtil`, load state và `EntityManager`.
- [Hibernate ORM Documentation](https://hibernate.org/orm/documentation/): chọn user guide/Javadocs theo đúng phiên bản runtime.

**Nguyên tắc cần nhớ:** managed state, loaded state và initialized state trả lời các câu hỏi khác nhau. Dùng JPA `isLoaded` khi cần tính portable; dùng Hibernate `isInitialized` hoặc `isPropertyInitialized` khi cần quan sát proxy, collection và lazy attribute cụ thể. Khi đã biết dữ liệu cần, ưu tiên fetch plan rõ ràng; chỉ gọi `Hibernate.initialize()` trong Session đang hoạt động và cho đúng phần dữ liệu cần dùng.
