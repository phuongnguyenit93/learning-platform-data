# LazyInitializationException và truy cập ngoài PersistenceContext

## Mục tiêu

LazyInitializationException là lỗi thường gặp khi ứng dụng truy cập một thuộc tính lazy của entity sau khi Hibernate không còn Session/JPA PersistenceContext có thể dùng để tải dữ liệu đó. Lỗi thường xuất hiện khi service trả entity ra ngoài transaction, rồi controller, mapper, serializer hoặc một thread khác mới đọc association.

Cách xử lý đúng bắt đầu từ việc xác định dữ liệu use case cần và tải dữ liệu trong ranh giới persistence phù hợp. Những lựa chọn phổ biến gồm:

- Mở transaction ở service và chuyển entity thành DTO trước khi transaction kết thúc.
- Dùng JOIN FETCH hoặc @EntityGraph để định nghĩa fetch plan cho query.
- Dùng DTO/interface projection để chỉ lấy dữ liệu cần thiết.
- Khởi tạo tường minh một association bằng Hibernate.initialize() khi đang ở trong persistence context.
- Tắt Open Session in View (OSIV) nếu muốn phát hiện sớm truy cập database ngoài service.

Bài này giải thích vòng đời persistence context, lazy proxy và collection, các tình huống gây lỗi, cách phân biệt detached entity với entity đang managed, tác động của OSIV và ví dụ Java 17+ chạy được với Spring Boot 3.4.5, Spring Data JPA và H2.

## 1. PersistenceContext là gì?

JPA EntityManager quản lý một persistence context. Persistence context là vùng làm việc theo dõi các entity đang managed, trạng thái thay đổi của chúng và identity của entity trong một đơn vị làm việc.

Trong Hibernate, persistence context gắn với một Session. Khi entity được load trong persistence context, Hibernate có thể:

- Theo dõi thay đổi thuộc tính và tự flush khi transaction commit.
- Duy trì một instance cho cùng một entity identity trong context.
- Tải association lazy khi ứng dụng truy cập nếu Session còn mở.
- Dùng snapshot/version để thực hiện dirty checking và optimistic locking.

Entity có thể ở các trạng thái:

| Trạng thái | Ý nghĩa |
| --- | --- |
| Transient | Object Java mới, chưa được persistence context quản lý và thường chưa có hàng tương ứng trong database. |
| Managed/Persistent | Entity đang được một persistence context quản lý; thay đổi có thể được dirty checking ghi xuống database. |
| Detached | Entity từng được quản lý nhưng không còn thuộc persistence context hiện tại. |
| Removed | Entity đang được đánh dấu xóa trong persistence context; lệnh DELETE được đồng bộ khi flush/commit. |

Khi transaction kết thúc và persistence context tương ứng đóng hoặc entity bị detach, Hibernate không còn tự động truy vấn database để tải association lazy cho entity đó.

### Transaction và PersistenceContext có liên quan nhưng không hoàn toàn đồng nghĩa

Trong Spring, @Transactional thường tạo hoặc tham gia transaction và gắn EntityManager/persistence context vào luồng thực thi hiện tại. Khi method transactional kết thúc, transaction được commit/rollback và persistence context transaction-scoped thường được đóng hoặc giải phóng.

OSIV có thể giữ EntityManager mở trong suốt HTTP request dù transaction của service đã kết thúc. Vì vậy, “transaction đã kết thúc” và “EntityManager chắc chắn đã đóng” không luôn là cùng một thời điểm. Tuy nhiên, thiết kế service nên tự xác định dữ liệu cần đọc thay vì phụ thuộc vào request-scoped persistence context.

## 2. Lazy loading và proxy hoạt động thế nào?

Lazy loading trì hoãn việc lấy association cho đến khi ứng dụng thực sự truy cập nó. Hibernate thường dùng proxy cho quan hệ to-one và persistent collection cho quan hệ to-many.

Ví dụ:

~~~java
@Entity
public class PurchaseOrder {
    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderItem> items;
}
~~~

Khi query PurchaseOrder, Hibernate có thể chỉ tải hàng trong bảng purchase_orders. customer được biểu diễn bằng proxy; items được biểu diễn bằng collection wrapper chưa khởi tạo.

Khi gọi:

~~~java
order.getCustomer().getName();
order.getItems().size();
~~~

Hibernate cần chạy thêm SQL để tải customer hoặc items. Nếu Session còn mở, truy vấn lazy có thể chạy. Nếu entity đã detached hoặc Session đã đóng, Hibernate không thể thực hiện truy vấn và có thể ném LazyInitializationException.

### Lazy không có nghĩa là không bao giờ tải

Lazy chỉ trì hoãn việc tải đến lúc cần. Nó không bảo đảm association sẽ không được tải. Việc đọc getter, lặp qua collection, gọi size(), contains() hoặc serialize object có thể kích hoạt truy vấn.

### Fetch type mặc định

Theo JPA, @ManyToOne và @OneToOne mặc định là EAGER, còn @OneToMany và @ManyToMany mặc định là LAZY. Nên khai báo rõ fetch = FetchType.LAZY cho quan hệ to-one nếu muốn tránh tải tự động ngoài nhu cầu; sau đó chọn fetch plan theo từng query/use case.

Không nên chuyển mọi quan hệ sang EAGER để tránh LazyInitializationException. EAGER có thể tải dữ liệu không cần, tạo join lớn hoặc phát sinh secondary select và N+1.

## 3. Khi nào LazyInitializationException xuất hiện?

Lỗi thường xảy ra khi một thuộc tính lazy chưa được khởi tạo và code truy cập nó sau khi persistence context không còn hoạt động.

Các tình huống điển hình:

1. **Service trả entity ra controller:** transaction của service kết thúc, controller đọc order.getCustomer().getName().
2. **JSON serialization:** controller trả entity; Jackson duyệt getter và chạm vào lazy association sau khi service đã kết thúc.
3. **Mapping DTO quá muộn:** service trả entity, mapper chạy ở tầng ngoài transaction và đọc collection lazy.
4. **Async hoặc executor:** entity được truyền sang thread khác; persistence context của thread gốc không được truyền theo.
5. **Message/event:** entity được giữ lại rồi truy cập association sau khi transaction xử lý message đã kết thúc.
6. **Entity đã detach:** code gọi entityManager.detach() hoặc clear(), sau đó đọc một association chưa load.
7. **Session đã đóng:** code giữ entity qua ranh giới request/job và dùng nó sau khi Session đóng.

Ví dụ lỗi:

~~~java
@Service
public class OrderService {
    @Transactional(readOnly = true)
    public PurchaseOrder findById(Long id) {
        return repository.findById(id).orElseThrow();
    }
}

// Controller gọi sau khi transaction của service kết thúc.
PurchaseOrder order = orderService.findById(id);
String customerName = order.getCustomer().getName();
~~~

Nếu customer chưa được khởi tạo, dòng cuối có thể ném LazyInitializationException.

Điểm cần xác định khi debug là association nào chưa load, entity đang ở trạng thái nào và persistence context đã kết thúc ở đâu. Stack trace thường chỉ ra getter/proxy/collection bị truy cập; SQL log và PersistenceUnitUtil.isLoaded() giúp xác nhận trạng thái.

## 4. Cách kiểm tra entity và association đã được load

JPA cung cấp PersistenceUnitUtil.isLoaded:

~~~java
PersistenceUnitUtil util = entityManagerFactory.getPersistenceUnitUtil();

boolean entityLoaded = util.isLoaded(order);
boolean customerLoaded = util.isLoaded(order, "customer");
boolean itemsLoaded = util.isLoaded(order, "items");
~~~

Trong Hibernate có thể kiểm tra trực tiếp:

~~~java
boolean initialized = Hibernate.isInitialized(order.getItems());
~~~

Đây là công cụ chẩn đoán hữu ích trong test hoặc debug. Không nên dùng những câu isLoaded để thay thế thiết kế fetch plan: nếu caller chắc chắn cần customer name và item count, query nên tải đúng dữ liệu đó.

## 5. Giải pháp ưu tiên: chuyển sang DTO bên trong transaction

Một cách thiết kế rõ ràng là service đọc entity, lấy tất cả dữ liệu cần dùng khi transaction còn mở, rồi trả DTO không chứa lazy proxy.

~~~java
public record OrderSummary(
        Long id,
        String status,
        String customerName,
        int itemCount
) {
}

@Transactional(readOnly = true)
public List<OrderSummary> findSummaries(String status) {
    return repository.findByStatus(status).stream()
            .map(order -> new OrderSummary(
                    order.getId(),
                    order.getStatus(),
                    order.getCustomer().getName(),
                    order.getItems().size()
            ))
            .toList();
}
~~~

Mapper chạy bên trong method transactional, nên Hibernate có thể tải association. Khi method trả về, caller chỉ giữ các giá trị Java đã được copy sang DTO.

Lợi ích:

- API không phụ thuộc vào entity graph và lazy proxy.
- Tránh Jackson vô tình truy cập database khi serialize.
- Kiểm soát rõ field nào được trả ra ngoài.
- Dễ kiểm thử, versioning response và phân quyền dữ liệu.
- Có thể giảm dữ liệu đọc bằng query projection phù hợp.

DTO phải chứa các giá trị cần dùng, không nên giữ nguyên entity hoặc collection Hibernate bên trong DTO.

## 6. Dùng @EntityGraph để khai báo fetch plan

@EntityGraph cho phép repository method chỉ định association cần tải cho một query cụ thể:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @EntityGraph(attributePaths = {"customer", "items"})
    List<PurchaseOrder> findByStatusOrderByIdAsc(String status);
}
~~~

Khi service gọi method này, Spring Data yêu cầu JPA provider tải customer và items theo entity graph. Service có thể map sang DTO ngay trong transaction.

EntityGraph hữu ích khi:

- Một use case cần thêm association nhưng các use case khác không cần.
- Muốn giữ repository method dễ đọc thay vì viết JPQL fetch join.
- Muốn định nghĩa fetch plan theo tên graph hoặc attributePaths.

EntityGraph không phải cam kết SQL phải luôn là một câu JOIN duy nhất. Provider có thể chọn cách tải phù hợp với mapping. Hãy kiểm tra SQL và số statement khi tối ưu hiệu năng.

## 7. Dùng JOIN FETCH

JPQL JOIN FETCH tải association trong cùng truy vấn:

~~~java
@Query("select distinct o from PurchaseOrder o "
     + "join fetch o.customer "
     + "left join fetch o.items "
     + "where o.status = :status")
List<PurchaseOrder> findWithDetails(@Param("status") String status);
~~~

- join fetch với customer yêu cầu có customer phù hợp.
- left join fetch với items vẫn giữ order không có item.
- distinct thể hiện ý định lấy mỗi root entity một lần; Hibernate 6 cũng loại trùng root entity trong kết quả fetch join.

Fetch join phù hợp khi use case luôn cần association đó. Không nên fetch mọi association trong mọi query.

### Fetch join collection và phân trang

Không nên kết hợp tùy tiện fetch join collection to-many với Pageable. Một order có nhiều item làm nhân bản hàng SQL; phân trang trên kết quả join có thể không tương ứng với số root entity. Hibernate có thể cảnh báo hoặc phải phân trang trong bộ nhớ tùy cấu hình/phiên bản.

Với danh sách có phân trang, các lựa chọn an toàn hơn gồm:

1. Query trang ID/root entity trước, với sort ổn định.
2. Query thứ hai tải graph cho các ID trong trang bằng IN (:ids).
3. Dùng DTO projection để lấy đúng cột cần hiển thị.
4. Dùng @EntityGraph cho quan hệ to-one và xử lý collection theo query riêng khi cần.

Fetch join nhiều collection cùng lúc cũng có thể tạo tích Descartes lớn hoặc gặp MultipleBagFetchException với một số kiểu mapping. Kiểm tra cardinality và SQL thay vì chỉ nhìn số dòng Java.

## 8. Dùng DTO/interface projection để tránh tải entity graph

Nếu màn hình chỉ cần một số trường, projection có thể truy vấn trực tiếp dữ liệu cần dùng:

~~~java
public interface OrderListView {
    Long getId();
    String getStatus();
    String getCustomerName();
}
~~~

JPQL constructor projection:

~~~java
public record OrderListItem(Long id, String status, String customerName) {
}

@Query("select new com.example.orders.OrderListItem("
     + "o.id, o.status, c.name) "
     + "from PurchaseOrder o join o.customer c "
     + "where o.status = :status")
List<OrderListItem> findOrderItems(@Param("status") String status);
~~~

Projection không cần khởi tạo entity PurchaseOrder cùng toàn bộ association. Đây thường là lựa chọn hiệu quả cho read model, bảng danh sách và API tìm kiếm.

Với DTO projection, kiểm tra tên class đầy đủ, thứ tự constructor argument và kiểu dữ liệu trả về. Với interface projection, alias trong query phải khớp accessor.

## 9. Khởi tạo tường minh bằng Hibernate.initialize

Trong một số use case, có thể chủ động khởi tạo association khi Session còn mở:

~~~java
@Transactional(readOnly = true)
public PurchaseOrder loadWithItems(Long id) {
    PurchaseOrder order = repository.findById(id).orElseThrow();
    Hibernate.initialize(order.getItems());
    Hibernate.initialize(order.getCustomer());
    return order;
}
~~~

Hibernate.initialize() là API riêng của Hibernate, không phải JPA portable API. Nó hữu ích khi cần khởi tạo một association cụ thể trong một đoạn code hẹp.

Tuy nhiên, gọi Hibernate.initialize() trong vòng lặp trên hàng trăm entity có thể tạo N+1. Hãy ưu tiên EntityGraph, fetch join hoặc projection khi biết trước dữ liệu cần lấy.

Không thể gọi Hibernate.initialize() thành công cho proxy detached mà không có Session phù hợp. Phải thực hiện khi persistence context còn mở.

## 10. Open Session in View (OSIV)

OSIV là cơ chế giữ EntityManager/Session mở trong suốt vòng đời HTTP request. Trong Spring Boot ứng dụng web, OSIV có thể được bật mặc định tùy cấu hình; nên đặt rõ giá trị để hành vi không phụ thuộc môi trường:

~~~properties
spring.jpa.open-in-view=false
~~~

Khi OSIV bật, controller hoặc JSON serializer có thể truy cập lazy association sau khi service transaction kết thúc vì EntityManager vẫn mở theo request. Điều này có thể làm lỗi biến mất, nhưng cũng có rủi ro:

- SQL chạy ở tầng controller hoặc trong lúc serialize response.
- N+1 khó phát hiện vì query phát sinh ngoài service.
- Latency endpoint khó liên kết với repository method.
- Database access có thể xảy ra ở thời điểm bất ngờ.
- Tầng web vô tình phụ thuộc vào entity graph và persistence.

OSIV không có nghĩa một database transaction được giữ mở trong toàn bộ request. Nó chủ yếu giữ persistence context/EntityManager mở; transaction database thường chỉ tồn tại trong phạm vi transactional method. Dù vậy, lazy load ngoài service vẫn tạo SQL và cần connection.

Với API cần kiểm soát rõ truy cập dữ liệu, tắt OSIV và map DTO trong transaction là lựa chọn dễ dự đoán hơn. Nếu giữ OSIV, vẫn nên định nghĩa fetch plan rõ ràng và không dựa vào serializer để tải dữ liệu.

## 11. Detached entity, merge và clear

Khi persistence context kết thúc, entity đã load trở thành detached. Đọc field đã có sẵn trên object thường vẫn được; đọc association lazy chưa khởi tạo có thể ném LazyInitializationException.

### merge không phải cách tải lazy association

EntityManager.merge(detachedEntity) sao chép trạng thái detached sang một instance managed và trả về instance managed đó:

~~~java
PurchaseOrder managed = entityManager.merge(detached);
~~~

Đối tượng detached ban đầu vẫn là detached. Hãy dùng giá trị trả về từ merge() nếu thực sự cần merge.

merge() không phải cách tổng quát để tải mọi association lazy và không bảo đảm graph được khởi tạo. Nếu cần dữ liệu, query lại bằng fetch plan phù hợp.

### clear và detach

entityManager.detach(entity) detach một entity cụ thể; entityManager.clear() detach tất cả entity trong persistence context. Sau đó association lazy chưa khởi tạo không thể tự tải qua context cũ.

Trước khi clear, cần flush các thay đổi muốn giữ lại. Nếu clear để tránh first-level cache làm sai phép đo hoặc để đồng bộ bulk DML, hãy hiểu rằng mọi entity đang managed sẽ mất trạng thái quản lý.

## 12. Async, thread và message boundary

Spring transaction và EntityManager thường gắn với thread hiện tại. Không truyền entity có lazy association sang @Async, executor, scheduler hoặc message consumer rồi kỳ vọng persistence context của thread gốc được chia sẻ.

Cách làm phù hợp:

- Truyền ID hoặc command DTO qua thread/message boundary.
- Trong thread xử lý, mở transaction mới và query lại dữ liệu cần dùng.
- Hoặc map thành DTO đầy đủ trước khi gửi sang thread khác.

Ví dụ:

~~~java
@Async
public CompletableFuture<Void> processOrder(Long orderId) {
    workerService.processInNewTransaction(orderId);
    return CompletableFuture.completedFuture(null);
}

@Transactional
public void processInNewTransaction(Long orderId) {
    PurchaseOrder order = repository.findWithDetails(orderId);
    // Work with loaded state inside this transaction.
}
~~~

Hai method nên ở các Spring bean riêng để lời gọi đi qua proxy. Không dựa vào self-invocation để kích hoạt @Async hoặc @Transactional.

## 13. Ví dụ chạy được với Java 17+, Spring Boot 3.4.5, Spring Data JPA và H2

Ví dụ tạo một order có customer và hai item. Service đầu tiên trả entity với association lazy chưa khởi tạo; truy cập sau khi transaction kết thúc sẽ ném LazyInitializationException. Service thứ hai dùng @EntityGraph và map DTO bên trong transaction, nên caller không cần persistence context.

### Cấu trúc dự án

~~~text
lazy-loading-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/lazyloading/
    │   │   ├── LazyLoadingApplication.java
    │   │   ├── Customer.java
    │   │   ├── PurchaseOrder.java
    │   │   ├── OrderItem.java
    │   │   ├── OrderSummary.java
    │   │   ├── CustomerRepository.java
    │   │   ├── PurchaseOrderRepository.java
    │   │   └── OrderService.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/lazyloading/OrderServiceIntegrationTest.java
~~~

### pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>lazy-loading-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### src/main/resources/application.properties

~~~properties
spring.datasource.url=jdbc:h2:mem:lazyloading;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=false
logging.level.org.hibernate.SQL=DEBUG
~~~

open-in-view=false giúp ví dụ thể hiện rõ ranh giới transaction của service. SQL logger được bật để quan sát query; có thể tắt sau khi học.

### Customer.java

~~~java
package com.example.lazyloading;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    protected Customer() {
    }

    public Customer(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

### PurchaseOrder.java

~~~java
package com.example.lazyloading;

import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 30)
    private String status;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @OneToMany(mappedBy = "order", cascade = CascadeType.ALL, orphanRemoval = true)
    private List<OrderItem> items = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String status, Customer customer) {
        this.status = status;
        this.customer = customer;
    }

    public void addItem(OrderItem item) {
        items.add(item);
        item.setOrder(this);
    }

    public Long getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }

    public Customer getCustomer() {
        return customer;
    }

    public List<OrderItem> getItems() {
        return items;
    }
}
~~~

### OrderItem.java

~~~java
package com.example.lazyloading;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "order_items")
public class OrderItem {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String productName;

    @Column(nullable = false)
    private int quantity;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    protected OrderItem() {
    }

    public OrderItem(String productName, int quantity) {
        this.productName = productName;
        this.quantity = quantity;
    }

    void setOrder(PurchaseOrder order) {
        this.order = order;
    }
}
~~~

### OrderSummary.java

~~~java
package com.example.lazyloading;

public record OrderSummary(
        Long id,
        String status,
        String customerName,
        int itemCount
) {
}
~~~

### CustomerRepository.java

~~~java
package com.example.lazyloading;

import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository extends JpaRepository<Customer, Long> {
}
~~~

### PurchaseOrderRepository.java

~~~java
package com.example.lazyloading;

import java.util.List;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository extends JpaRepository<PurchaseOrder, Long> {
    @EntityGraph(attributePaths = {"customer", "items"})
    List<PurchaseOrder> findByStatusOrderByIdAsc(String status);
}
~~~

findById kế thừa từ JpaRepository không khai báo fetch graph, nên các association vẫn lazy theo mapping. findByStatusOrderByIdAsc yêu cầu tải customer và items cho use case tạo summary.

### OrderService.java

~~~java
package com.example.lazyloading;

import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final CustomerRepository customerRepository;
    private final PurchaseOrderRepository repository;

    public OrderService(
            CustomerRepository customerRepository,
            PurchaseOrderRepository repository) {
        this.customerRepository = customerRepository;
        this.repository = repository;
    }

    @Transactional
    public Long createDemoOrder() {
        Customer customer = customerRepository.saveAndFlush(new Customer("Acme"));

        PurchaseOrder order = new PurchaseOrder("NEW", customer);
        order.addItem(new OrderItem("Keyboard", 1));
        order.addItem(new OrderItem("Mouse", 2));

        return repository.saveAndFlush(order).getId();
    }

    @Transactional(readOnly = true)
    public PurchaseOrder loadWithoutFetching(Long id) {
        return repository.findById(id).orElseThrow();
    }

    @Transactional(readOnly = true)
    public List<OrderSummary> findSummaries(String status) {
        return repository.findByStatusOrderByIdAsc(status).stream()
                .map(order -> new OrderSummary(
                        order.getId(),
                        order.getStatus(),
                        order.getCustomer().getName(),
                        order.getItems().size()
                ))
                .toList();
    }
}
~~~

loadWithoutFetching trả entity ra sau khi transaction kết thúc; caller nhận entity detached với association chưa khởi tạo. findSummaries dùng EntityGraph và map sang DTO khi transaction còn mở.

### LazyLoadingApplication.java

~~~java
package com.example.lazyloading;

import java.util.List;
import org.hibernate.LazyInitializationException;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class LazyLoadingApplication {
    public static void main(String[] args) {
        SpringApplication.run(LazyLoadingApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(OrderService orderService) {
        return args -> {
            Long orderId = orderService.createDemoOrder();
            PurchaseOrder detached = orderService.loadWithoutFetching(orderId);

            try {
                detached.getCustomer().getName();
            } catch (LazyInitializationException expected) {
                System.out.println("Detached customer access: LazyInitializationException");
            }

            try {
                detached.getItems().size();
            } catch (LazyInitializationException expected) {
                System.out.println("Detached items access: LazyInitializationException");
            }

            List<OrderSummary> summaries = orderService.findSummaries("NEW");
            for (OrderSummary summary : summaries) {
                System.out.println("DTO: order=" + summary.id()
                        + ", status=" + summary.status()
                        + ", customer=" + summary.customerName()
                        + ", itemCount=" + summary.itemCount());
            }
        };
    }
}
~~~

### Chạy chương trình

~~~bash
mvn spring-boot:run
~~~

Stdout mong đợi trên database H2 mới:

~~~text
Detached customer access: LazyInitializationException
Detached items access: LazyInitializationException
DTO: order=1, status=NEW, customer=Acme, itemCount=2
~~~

ID đầu tiên được sinh là 1 trong database mới của ví dụ. Hai dòng đầu minh họa truy cập association chưa khởi tạo sau transaction. Dòng cuối cho thấy service tải graph cần thiết và trả DTO độc lập với persistence context.

## 14. Integration test cho lỗi và cách khắc phục

Test không nên tự mở transaction bao quanh toàn bộ method test nếu muốn chứng minh entity đã detached sau khi service trả về. @SpringBootTest mặc định không tự thêm transaction cho test method; giữ test không có @Transactional để quan sát ranh giới thực.

~~~java
package com.example.lazyloading;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import org.hibernate.LazyInitializationException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class OrderServiceIntegrationTest {
    @Autowired
    private CustomerRepository customerRepository;

    @Autowired
    private PurchaseOrderRepository orderRepository;

    @Autowired
    private OrderService orderService;

    private Long orderId;

    @BeforeEach
    void setUp() {
        orderRepository.deleteAll();
        customerRepository.deleteAll();

        Customer customer = customerRepository.saveAndFlush(new Customer("Test Customer"));
        PurchaseOrder order = new PurchaseOrder("NEW", customer);
        order.addItem(new OrderItem("Keyboard", 1));
        order.addItem(new OrderItem("Mouse", 2));
        orderId = orderRepository.saveAndFlush(order).getId();
    }

    @Test
    void lazyAssociationsCannotBeLoadedAfterServiceTransactionEnds() {
        PurchaseOrder detached = orderService.loadWithoutFetching(orderId);

        assertThatThrownBy(() -> detached.getCustomer().getName())
                .isInstanceOf(LazyInitializationException.class);
        assertThatThrownBy(() -> detached.getItems().size())
                .isInstanceOf(LazyInitializationException.class);
    }

    @Test
    void entityGraphAllowsDtoMappingInsideTransaction() {
        List<OrderSummary> summaries = orderService.findSummaries("NEW");

        assertThat(summaries).hasSize(1);
        assertThat(summaries.get(0).customerName()).isEqualTo("Test Customer");
        assertThat(summaries.get(0).itemCount()).isEqualTo(2);
    }
}
~~~

Chạy test:

~~~bash
mvn test
~~~

Test thứ nhất xác nhận cả to-one proxy và to-many collection đều chưa khởi tạo khi service trả entity. Test thứ hai xác nhận EntityGraph cho phép service map DTO trong transaction mà không cần truy cập lazy association ở caller.

## 15. Những cách xử lý nên tránh

### Bật EAGER cho mọi association

EAGER có thể làm query tải dữ liệu lớn hơn mức cần thiết và tạo secondary selects. Fetch plan nên được quyết định theo use case.

### Bật OSIV chỉ để che lỗi

OSIV có thể khiến lazy loading tiếp tục chạy ở controller/serializer, che giấu việc service trả entity chưa đủ dữ liệu. Nếu dùng OSIV, vẫn cần theo dõi SQL và tránh truy cập association tùy tiện.

### Bật hibernate.enable_lazy_load_no_trans

Đây là tùy chọn Hibernate cho phép cố tải lazy association ngoài transaction bằng cơ chế Session phụ trong một số trường hợp. Nó có thể tạo nhiều transaction/connection nhỏ, che giấu ranh giới persistence và dẫn đến N+1. Không nên dùng làm giải pháp mặc định cho thiết kế ứng dụng.

### Gọi merge() để “mở lại” entity

merge() không làm object detached ban đầu trở thành managed và không tự bảo đảm toàn bộ lazy graph đã load. Nếu cần dữ liệu, query lại với EntityGraph/fetch join hoặc projection.

### Trả entity trực tiếp cho JSON serializer

Serializer có thể gọi getter và kích hoạt lazy loading. Response API nên là DTO/projection với cấu trúc đã xác định.

### Khởi tạo mọi collection trong vòng lặp

Đọc từng collection lazy của hàng trăm entity có thể tạo N+1. Dùng fetch plan hoặc batch fetching phù hợp và đo số query.

## 16. Lỗi thường gặp và cách chẩn đoán

1. **Truy cập association sau khi service trả entity:** map DTO trong transaction hoặc tải association bằng EntityGraph/fetch join.
2. **Jackson làm phát sinh LazyInitializationException:** không serialize entity trực tiếp; trả DTO.
3. **Chỉ thêm @Transactional ở controller:** transaction quá rộng và không làm rõ ranh giới nghiệp vụ; đặt ở service use case.
4. **Gọi method transactional bằng self-invocation:** lời gọi không qua Spring proxy; tách method sang bean khác hoặc dùng transaction API phù hợp.
5. **Entity truyền sang async thread:** persistence context không thread-safe và không tự truyền; gửi ID/DTO rồi query lại trong transaction mới.
6. **Dùng merge() nhưng tiếp tục đọc object cũ:** dùng instance managed mà merge() trả về, hoặc query lại theo fetch plan.
7. **Fetch join collection cùng Pageable:** có thể nhân bản hàng và phân trang sai/đắt; phân trang ID trước rồi fetch graph.
8. **Đặt EAGER trên mọi quan hệ:** tải quá nhiều dữ liệu; chọn fetch plan theo query.
9. **Bật OSIV nhưng không kiểm tra SQL:** lazy query có thể phát sinh trong serialization và gây N+1.
10. **Dùng Hibernate.initialize() ngoài Session:** không thể khởi tạo proxy detached; gọi khi transaction còn mở.
11. **Clear persistence context khi còn thay đổi chưa flush:** thay đổi có thể không được đồng bộ; flush trước khi clear nếu cần giữ chúng.
12. **Nhầm field đã load với association đã load:** entity có thể đọc được scalar field nhưng vẫn có proxy/collection lazy chưa khởi tạo.

## 17. Checklist khi điều tra LazyInitializationException

- [ ] Xác định chính xác association hoặc collection gây lỗi từ stack trace.
- [ ] Kiểm tra entity có còn managed không và persistence context kết thúc ở đâu.
- [ ] Kiểm tra PersistenceUnitUtil.isLoaded(entity, "association") khi cần.
- [ ] Xác định caller có thực sự cần dữ liệu association đó không.
- [ ] Nếu cần, tải bằng @EntityGraph, JOIN FETCH, projection hoặc query riêng.
- [ ] Map sang DTO trong service transaction trước khi trả dữ liệu ra ngoài.
- [ ] Kiểm tra controller, serializer, mapper, async task và message consumer có truy cập entity sau transaction không.
- [ ] Đặt rõ spring.jpa.open-in-view và không dựa vào OSIV để che lỗi.
- [ ] Kiểm tra N+1 và số SQL statement sau khi thay fetch plan.
- [ ] Không bật EAGER toàn cục hoặc enable_lazy_load_no_trans chỉ để làm lỗi biến mất.
- [ ] Kiểm thử service với transaction thật và test method không tự mở transaction nếu cần xác minh detached behavior.

## 18. Nguyên tắc thực hành

- Hiểu persistence context là phạm vi quản lý entity và lazy loading.
- Xem LazyInitializationException như tín hiệu code đang đọc dữ liệu ngoài ranh giới persistence phù hợp.
- Đặt transaction ở service và hoàn thành việc đọc dữ liệu cần thiết trong transaction.
- Ưu tiên DTO/projection cho dữ liệu đi qua ranh giới API, async hoặc message.
- Dùng @EntityGraph hoặc JOIN FETCH để tải association theo use case.
- Dùng projection khi chỉ cần một số trường và không cần entity graph.
- Chỉ dùng Hibernate.initialize() cho association cụ thể khi Session còn mở; tránh lặp gây N+1.
- Tắt OSIV nếu muốn kiểm soát rõ truy cập database ở service; dù bật OSIV vẫn phải kiểm soát fetch plan.
- Không coi EAGER, merge hoặc lazy-load-no-trans là giải pháp tổng quát.
- Kiểm thử detached behavior, DTO mapping và số SQL statement.

Điểm cốt lõi: **LazyInitializationException xảy ra khi Hibernate cần tải một association lazy nhưng persistence context đã không còn khả dụng. Hãy xác định dữ liệu use case cần, tải nó trong transaction bằng EntityGraph/fetch join/projection, rồi trả DTO đã hoàn chỉnh. Điều đó giữ truy cập database trong ranh giới service và tránh phụ thuộc vào serializer hoặc OSIV.**