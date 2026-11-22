# Batch fetching, @BatchSize và cấu hình đặc thù Hibernate

## 1. Mục tiêu

Batch fetching là cơ chế của Hibernate giúp giảm số câu SELECT khi ứng dụng truy cập nhiều association đang được tải lazy. Thay vì phát sinh một SELECT riêng cho từng Entity proxy hoặc từng collection, Hibernate gom nhiều mục chưa được khởi tạo vào một nhóm và tải chúng trong cùng một truy vấn, thường với điều kiện `IN`.

Bài học tập trung vào:
- Vì sao lazy loading có thể tạo vấn đề N+1.
- Batch fetching hoạt động với Entity proxy và collection như thế nào.
- Dùng `@BatchSize` ở cấp Entity và trên thuộc tính collection.
- Cấu hình mặc định toàn cục bằng `hibernate.default_batch_fetch_size` trong Spring Boot.
- Phân biệt batch fetching khi đọc với JDBC batching khi ghi.
- Chọn giữa batch fetching, `JOIN FETCH`, `@EntityGraph` và các chiến lược tải khác.
- Đo số câu SQL và kiểm thử hành vi batch fetching.

Sau bài học, bạn có thể giữ association ở chế độ lazy, giảm số lần round-trip tới database trong các use case phù hợp và chọn kích thước batch dựa trên số liệu thực tế.

## 2. Vấn đề N+1 khi dùng lazy loading

Giả sử có 20 đơn hàng, mỗi đơn liên kết với một khách hàng. Entity `PurchaseOrder` dùng `@ManyToOne(fetch = LAZY)` để không tải Customer ngay khi truy vấn đơn hàng.

Nếu ứng dụng làm như sau:

```java
List<PurchaseOrder> orders = orderRepository.findAll();

for (PurchaseOrder order : orders) {
    System.out.println(order.getCustomer().getName());
}
```

Truy vấn ban đầu lấy danh sách đơn hàng. Khi gọi `getCustomer().getName()`, Hibernate cần khởi tạo proxy Customer. Nếu mỗi Customer được tải bằng một SELECT riêng, tổng số câu lệnh có thể là:

```text
1 SELECT lấy 20 đơn hàng
+ 20 SELECT lấy 20 khách hàng
= 21 SELECT
```

Đây là vấn đề N+1: một truy vấn lấy tập dữ liệu gốc, sau đó phát sinh thêm N truy vấn cho dữ liệu liên quan. Lazy loading giúp tránh tải dữ liệu không cần thiết, nhưng truy cập từng association trong vòng lặp có thể tạo nhiều truy vấn.

Batch fetching giảm số truy vấn bổ sung bằng cách tải nhiều proxy cùng lúc. Với batch size 16 và 20 Customer khác nhau, ví dụ trên thường cần:

```text
1 SELECT lấy đơn hàng
+ 1 SELECT lấy tối đa 16 khách hàng
+ 1 SELECT lấy 4 khách hàng còn lại
= 3 SELECT
```

Đây là số truy vấn minh họa khi các proxy cùng loại đang chờ trong một persistence context, không có cache làm thay đổi kết quả và mỗi đơn tham chiếu một Customer khác nhau. Số thực tế phụ thuộc vào dữ liệu, thứ tự truy cập, cache và cấu hình.

## 3. Batch fetching hoạt động như thế nào?

Hibernate duy trì persistence context trong một Session/transaction. Khi Entity hoặc collection được tải lazy, Hibernate có thể ghi nhận các proxy hoặc collection wrapper chưa được khởi tạo.

Khi ứng dụng truy cập một proxy/collection, Hibernate chọn một nhóm các đối tượng cùng loại đang chờ và tải chúng trong một SELECT. Ví dụ với Entity Customer:

```sql
select c.id, c.name
from customers c
where c.id in (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
```

Với collection `Customer.orders`, Hibernate có thể tải các collection của nhiều Customer bằng một truy vấn:

```sql
select o.customer_id, o.id, o.order_number
from purchase_orders o
where o.customer_id in (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
```

Batch size là số Entity proxy hoặc collection tối đa Hibernate cố gắng tải trong một SELECT. Nếu có 20 mục cần tải và batch size là 16, thường sẽ có một batch 16 và một batch 4.

Batch fetching không biến tất cả association thành một truy vấn duy nhất. Nó gom các lần tải lazy thành những nhóm nhỏ. Nó cũng chỉ có thể gom các proxy/collection phù hợp đang tồn tại trong cùng persistence context; nếu mỗi vòng lặp mở một transaction/session riêng hoặc clear persistence context liên tục, cơ hội batching sẽ giảm.

## 4. Dùng @BatchSize trên Entity

`@BatchSize` là annotation riêng của Hibernate, có package:

```java
import org.hibernate.annotations.BatchSize;
```

Đặt annotation ở cấp Entity để chỉ định số proxy của Entity đó có thể được tải cùng lúc:

```java
@Entity
@Table(name = "customers")
@BatchSize(size = 16)
public class Customer {
    // Entity fields
}
```

Khi nhiều association lazy trỏ tới Customer và các proxy Customer đang chờ trong Session, Hibernate có thể khởi tạo tối đa 16 proxy trong cùng một SELECT.

Ví dụ quan hệ:

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;
}
```

Annotation trên `Customer` áp dụng cho việc batch load các instance Customer. Nó hữu ích khi truy vấn nhiều PurchaseOrder rồi lần lượt đọc `order.getCustomer()`.

### 4.1. @BatchSize không đổi fetch type

`@BatchSize` không biến `LAZY` thành `EAGER`, cũng không bắt Hibernate tải Customer ngay khi truy vấn PurchaseOrder. Nó chỉ ảnh hưởng cách Hibernate thực hiện việc tải khi proxy lazy được khởi tạo.

Vì vậy, ứng dụng vẫn có thể giữ mapping:

```java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;
```

và để Hibernate gom các lần khởi tạo proxy khi cần.

## 5. Dùng @BatchSize trên collection

Batch fetching cũng áp dụng cho collection lazy. Đặt `@BatchSize` trực tiếp trên thuộc tính collection để giới hạn số collection cùng role được tải trong một SELECT.

```java
@Entity
@Table(name = "customers")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
    @BatchSize(size = 16)
    private List<PurchaseOrder> orders = new ArrayList<>();
}
```

Khi ứng dụng tải danh sách Customer rồi gọi `customer.getOrders()` cho nhiều khách hàng, Hibernate có thể tải collection orders của tối đa 16 Customer trong một truy vấn.

Khác biệt giữa hai vị trí annotation:

| Vị trí @BatchSize | Đối tượng được gom | Ví dụ use case |
| --- | --- | --- |
| Trên class Entity `Customer` | Các proxy/instance Customer chưa khởi tạo. | Nhiều PurchaseOrder tham chiếu tới các Customer khác nhau. |
| Trên thuộc tính `Customer.orders` | Các collection orders chưa khởi tạo của nhiều Customer. | Tải danh sách Customer rồi đọc orders của từng người. |

Batch size của collection là số collection owner được tải cùng lúc, không phải số phần tử PurchaseOrder tối đa trong một collection.

## 6. Cấu hình mặc định toàn cục trong Spring Boot

Nếu muốn áp dụng một batch size mặc định cho lazy association trên toàn ứng dụng, cấu hình thuộc tính Hibernate:

`src/main/resources/application.properties`:

```properties
spring.jpa.properties.hibernate.default_batch_fetch_size=16
```

Với YAML:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        default_batch_fetch_size: 16
```

Đây là cấu hình Hibernate, không phải thuộc tính chuẩn của JPA. Spring Boot chuyển các thuộc tính dưới `spring.jpa.properties.*` tới Hibernate.

`hibernate.default_batch_fetch_size` là giá trị mặc định toàn cục cho batch fetching. Có thể dùng `@BatchSize(size = n)` ở một Entity hoặc collection cụ thể khi muốn chọn kích thước riêng cho mapping đó. Hãy giữ cấu hình rõ ràng và kiểm tra hành vi trên phiên bản Hibernate mà ứng dụng đang dùng.

### 6.1. Chọn kích thước batch

Không có một con số đúng cho mọi ứng dụng. Các giá trị 16, 32 hoặc 64 thường được dùng làm điểm bắt đầu để đo, nhưng cần cân nhắc:

- Số lượng association thường được truy cập trong một use case.
- Giới hạn bind parameter và khả năng xử lý `IN` của database.
- Kích thước từng dòng và lượng dữ liệu trả về.
- Bộ nhớ ứng dụng, mạng và độ trễ giữa ứng dụng với database.
- Số lượng proxy/collection thực tế có trong một persistence context.

Batch size lớn có thể giảm số round-trip nhưng tạo truy vấn nhiều tham số và trả nhiều dữ liệu hơn trong một lần. Batch size nhỏ làm tăng số truy vấn bổ sung. Hãy đo trên workload gần thực tế thay vì chọn số lớn nhất.

## 7. Phân biệt batch fetching với JDBC batching

Hai tính năng cùng có chữ “batch” nhưng giải quyết hai vấn đề khác nhau:

| Cơ chế | Mục đích | Cấu hình/annotation | Hành động database |
| --- | --- | --- | --- |
| Batch fetching | Giảm SELECT khi tải lazy Entity/collection. | `@BatchSize`, `hibernate.default_batch_fetch_size`. | Một SELECT tải nhiều Entity hoặc collection owner, thường dùng `IN`. |
| JDBC batching | Giảm số lần gửi lệnh ghi INSERT/UPDATE/DELETE. | `hibernate.jdbc.batch_size` và các cấu hình DML liên quan. | Driver gửi nhiều lệnh ghi theo batch. |

Ví dụ cấu hình JDBC batching:

```properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
```

Thuộc tính trên không bật batch fetching. Nếu mục tiêu là giảm N+1 khi đọc lazy association, cần cấu hình `@BatchSize` hoặc `hibernate.default_batch_fetch_size`.

## 8. Mô hình ví dụ hoàn chỉnh

Ví dụ dùng Java 17+, Spring Boot 3.5.x, Spring Data JPA và Hibernate do Spring Boot quản lý phiên bản. Mô hình có Customer và PurchaseOrder với hai chiều quan hệ:

- Một Customer có nhiều PurchaseOrder.
- Mỗi PurchaseOrder thuộc một Customer.
- Cả hai phía đều tải lazy khi đọc association.

### 8.1. Entity Customer

`src/main/java/com/example/orders/Customer.java`:

```java
package com.example.orders;

import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import java.util.ArrayList;
import java.util.List;
import org.hibernate.annotations.BatchSize;

@Entity
@Table(name = "customers")
@BatchSize(size = 16)
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    @OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
    @BatchSize(size = 16)
    private List<PurchaseOrder> orders = new ArrayList<>();

    protected Customer() {
        // JPA cần constructor không tham số.
    }

    public Customer(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Customer name is required");
        }
        this.name = name.trim();
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public List<PurchaseOrder> getOrders() {
        return orders;
    }

    public void addOrder(PurchaseOrder order) {
        orders.add(order);
        order.setCustomer(this);
    }
}
```

`@BatchSize` ở class áp dụng cho proxy Customer; annotation trên `orders` áp dụng cho collection orders của nhiều Customer.

### 8.2. Entity PurchaseOrder

`src/main/java/com/example/orders/PurchaseOrder.java`:

```java
package com.example.orders;

import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String orderNumber;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    protected PurchaseOrder() {
        // JPA cần constructor không tham số.
    }

    public PurchaseOrder(String orderNumber, Customer customer) {
        if (orderNumber == null || orderNumber.isBlank()) {
            throw new IllegalArgumentException("Order number is required");
        }
        if (customer == null) {
            throw new IllegalArgumentException("Customer is required");
        }
        this.orderNumber = orderNumber.trim();
        this.customer = customer;
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public Customer getCustomer() {
        return customer;
    }

    void setCustomer(Customer customer) {
        this.customer = customer;
    }
}
```

Constructor gán phía owning side `PurchaseOrder.customer`. Phương thức `Customer.addOrder()` giữ hai phía trong bộ nhớ đồng bộ khi ứng dụng cần xây dựng quan hệ từ Customer.

### 8.3. Repository

`src/main/java/com/example/orders/CustomerRepository.java`:

```java
package com.example.orders;

import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository extends JpaRepository<Customer, Long> {
}
```

`src/main/java/com/example/orders/PurchaseOrderRepository.java`:

```java
package com.example.orders;

import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository extends JpaRepository<PurchaseOrder, Long> {
}
```

## 9. Quan sát SQL khi batch fetching

Trong `application.properties`, có thể bật SQL log và Hibernate statistics ở môi trường phát triển hoặc kiểm thử:

```properties
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.format_sql=true
spring.jpa.properties.hibernate.generate_statistics=true
spring.jpa.properties.hibernate.default_batch_fetch_size=16
```

Hoặc dùng logging:

```properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Bind logging có thể in dữ liệu tham số nhạy cảm; chỉ bật ở môi trường phát triển/kiểm thử và kiểm soát log phù hợp.

Với 20 đơn hàng tham chiếu 20 khách hàng, SQL thường có dạng:

```sql
-- Query 1: lấy các đơn hàng
select o.id, o.order_number, o.customer_id
from purchase_orders o;

-- Query 2: khởi tạo một nhóm Customer proxy
select c.id, c.name
from customers c
where c.id in (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);

-- Query 3: tải các Customer còn lại
select c.id, c.name
from customers c
where c.id in (?, ?, ?, ?);
```

SQL thực tế do Hibernate và dialect tạo ra có thể khác về alias, cột, số placeholder và cách chia nhóm. Điều cần kiểm tra là số SELECT giảm theo nhóm batch và dữ liệu association vẫn đúng.

## 10. Kiểm thử số câu truy vấn bằng Hibernate Statistics

Test chức năng chỉ xác nhận dữ liệu đúng chưa đủ để chứng minh batch fetching hoạt động. Có thể dùng Hibernate `Statistics` để đo số prepared statement trong một đoạn thao tác.

Test dưới đây tạo 20 Customer, mỗi người có một PurchaseOrder. Sau khi flush và clear persistence context, test đo:

1. Một SELECT lấy toàn bộ PurchaseOrder.
2. Hai SELECT tải 20 Customer proxy theo batch size 16.

### 10.1. Cấu hình test

Ví dụ dùng H2 trong `src/test/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:batchdb;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.properties.hibernate.generate_statistics=true
spring.jpa.properties.hibernate.default_batch_fetch_size=16
```

### 10.2. Integration test

`src/test/java/com/example/orders/BatchFetchingTest.java`:

```java
package com.example.orders;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.ArrayList;
import java.util.List;
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.data.domain.Sort;
import jakarta.persistence.EntityManager;

@DataJpaTest
class BatchFetchingTest {
    @Autowired
    private EntityManager entityManager;

    @Autowired
    private CustomerRepository customerRepository;

    @Autowired
    private PurchaseOrderRepository orderRepository;

    private Statistics statistics() {
        SessionFactory sessionFactory = entityManager
                .getEntityManagerFactory()
                .unwrap(SessionFactory.class);
        return sessionFactory.getStatistics();
    }

    private void seedTwentyCustomersAndOrders() {
        for (int i = 1; i <= 20; i++) {
            Customer customer = new Customer("Customer " + i);
            entityManager.persist(customer);
            entityManager.persist(new PurchaseOrder("ORD-" + i, customer));
        }
        entityManager.flush();
        entityManager.clear();
    }

    @Test
    void batchesLazyCustomerProxies() {
        seedTwentyCustomersAndOrders();
        Statistics stats = statistics();
        stats.clear();

        List<PurchaseOrder> orders = orderRepository.findAll(Sort.by("id").ascending());
        List<String> customerNames = orders.stream()
                .map(order -> order.getCustomer().getName())
                .toList();

        assertThat(customerNames).hasSize(20);
        assertThat(stats.getPrepareStatementCount()).isEqualTo(3);
    }

    @Test
    void batchesLazyCollectionsForMultipleCustomers() {
        seedTwentyCustomersAndOrders();
        Statistics stats = statistics();
        stats.clear();

        List<Customer> customers = customerRepository.findAll(Sort.by("id").ascending());
        List<Integer> orderCounts = customers.stream()
                .map(customer -> customer.getOrders().size())
                .toList();

        assertThat(orderCounts).hasSize(20);
        assertThat(orderCounts).containsOnly(1);
        assertThat(stats.getPrepareStatementCount()).isEqualTo(3);
    }
}
```

Test đầu kiểm tra batch Entity proxy Customer. Test thứ hai kiểm tra batch collection `Customer.orders`. Với 20 mục và batch size 16, mỗi test kỳ vọng một truy vấn gốc cộng hai truy vấn association, tức ba prepared statement.

Đếm statement chính xác có thể thay đổi nếu cấu hình, Hibernate version, cache, query setup hoặc cách seed dữ liệu thay đổi. Nếu test chạy trên project thực tế cho số khác, xem SQL log và statistics để xác định truy vấn nào được tính; không điều chỉnh assertion chỉ để ép test qua.

Chạy:

```bash
mvn test
```

Kết quả mong đợi là `BUILD SUCCESS` và hai test đều thành công với mapping/configuration như ví dụ. Đây là kết quả dự kiến, không phải log build đã chạy trong môi trường này.

## 11. Khi nào dùng BatchSize, JOIN FETCH hoặc EntityGraph?

Batch fetching không phải lựa chọn tốt nhất cho mọi truy vấn. Hãy chọn chiến lược theo số lượng association và hình dạng dữ liệu cần trả về.

| Chiến lược | Khi phù hợp | Điểm cần cân nhắc |
| --- | --- | --- |
| Batch fetching | Đọc nhiều Entity/collection lazy trong một persistence context, số association thực tế thay đổi theo dữ liệu. | Vẫn phát sinh các SELECT phụ theo từng batch. |
| `JOIN FETCH` | Một truy vấn cụ thể chắc chắn cần association và số dòng join được kiểm soát. | Join collection có thể nhân dòng, trùng root và gây khó cho pagination. |
| `@EntityGraph` | Muốn khai báo fetch plan theo Repository method hoặc use case. | Provider quyết định cách thực thi; cần xem SQL thực tế. |
| `@Fetch(FetchMode.SUBSELECT)` | Một truy vấn gốc tải nhiều owner và cần khởi tạo collection cùng role bằng một truy vấn phụ. | Là chiến lược riêng của Hibernate, có thể tải collection của cả nhóm owner trong truy vấn gốc. |
| DTO projection | Chỉ cần một số field và không cần Entity graph. | Cần thiết kế projection/query; thường tránh hydrate association không dùng. |

Ví dụ `JOIN FETCH`:

```java
@Query("""
       select o
       from PurchaseOrder o
       join fetch o.customer
       order by o.id
       """)
List<PurchaseOrder> findAllWithCustomer();
```

Ví dụ `@EntityGraph`:

```java
@EntityGraph(attributePaths = "customer")
List<PurchaseOrder> findByOrderNumberStartingWith(String prefix);
```

Với truy vấn trả Page và collection `@OneToMany`, tránh fetch join collection trực tiếp cùng pagination nếu chưa hiểu tác động nhân dòng và cách Hibernate xử lý. Batch fetching, DTO projection hoặc chiến lược hai bước thường dễ kiểm soát hơn.

## 12. Giới hạn và các yếu tố ảnh hưởng

Batch fetching có một số giới hạn cần hiểu:

- Batch size là mức tối đa, không phải cam kết mọi SELECT luôn có đúng số placeholder đó.
- Chỉ các proxy/collection thích hợp đang chờ trong cùng persistence context mới có thể được gom.
- Các association phải được truy cập khi Session còn mở; batch fetching không giải quyết `LazyInitializationException` sau khi persistence context đã đóng.
- Cache cấp hai có thể làm một số Entity không cần truy vấn database, khiến số SELECT thấp hơn dự kiến.
- Nếu các association có quá nhiều dữ liệu hoặc collection rất lớn, batch fetch có thể tạo result set lớn; cân nhắc phân trang child hoặc projection.
- Database có giới hạn bind parameter; batch size cần phù hợp với engine và kích thước query.
- Khi code mở transaction mới cho từng bản ghi hoặc clear Session trong vòng lặp, các proxy không còn cùng một batch queue.

Batch fetching giảm số round-trip, nhưng không tự động giảm tổng số byte dữ liệu cần tải. Hãy cân nhắc kích thước Entity, số association và nhu cầu thật của use case.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Vẫn có nhiều SELECT dù đã thêm `@BatchSize` | Association không phải lazy, proxy không cùng Session, hoặc annotation đặt sai Entity/collection role. | Kiểm tra fetch type, vị trí annotation, persistence context và SQL log. |
| `@BatchSize` không được nhận diện | Import nhầm package hoặc Hibernate dependency không tương thích. | Dùng `org.hibernate.annotations.BatchSize` và phiên bản Hibernate do Spring Boot quản lý. |
| Nhầm cấu hình JDBC batch với fetch batch | Dùng `hibernate.jdbc.batch_size` để kỳ vọng giảm SELECT lazy. | Dùng `hibernate.default_batch_fetch_size` hoặc `@BatchSize` cho đọc dữ liệu. |
| Batch query chứa quá nhiều bind parameter | Chọn batch size quá lớn với database hoặc query rộng. | Giảm batch size và đo lại trên engine mục tiêu. |
| Lazy loading lỗi sau khi rời transaction | Association được truy cập khi Session đã đóng. | Tải dữ liệu trong transaction, map sang DTO hoặc dùng fetch plan phù hợp. |
| Số truy vấn test không ổn định | Cache, dữ liệu seed, phiên bản Hibernate hoặc persistence context làm thay đổi batch queue. | Clear persistence context và statistics đúng thời điểm; kiểm tra SQL thay vì giả định. |
| Collection fetch làm dữ liệu nhân dòng | Dùng join fetch collection với nhiều phần tử. | Dùng batch fetching, DTO, EntityGraph phù hợp hoặc truy vấn hai bước. |
| Kỳ vọng một SELECT duy nhất | Nhầm batch fetching với JOIN FETCH. | Hiểu batch size là số tối đa mỗi nhóm; với nhiều nhóm vẫn có nhiều SELECT. |

## 14. Quy trình áp dụng và đo hiệu năng

1. Xác định use case đang phát sinh N+1 bằng SQL log, APM hoặc Hibernate statistics.
2. Kiểm tra association nào đang lazy và được truy cập trong vòng lặp.
3. Nếu cần giữ lazy loading, thử `@BatchSize` ở Entity proxy hoặc collection role tương ứng.
4. Nếu nhiều mapping cần một giá trị chung, cấu hình `hibernate.default_batch_fetch_size`.
5. Chạy lại đúng use case với lượng dữ liệu đại diện; so sánh số SELECT, số dòng và thời gian.
6. Thử batch size khác nhau, ví dụ 16, 32 và 64, theo giới hạn database và workload.
7. So sánh với JOIN FETCH, EntityGraph hoặc DTO projection nếu use case luôn cần cùng association.
8. Kiểm thử trường hợp association rỗng, nhiều owner, nhiều proxy trùng tham chiếu và trang dữ liệu lớn.
9. Giữ SQL log/bằng chứng đo trong môi trường phát triển hoặc kiểm thử; tránh bật bind parameter nhạy cảm ở production.

## 15. Checklist hoàn thành

- [ ] Giải thích được vấn đề N+1 khi truy cập lazy association.
- [ ] Mô tả được cách Hibernate gom Entity proxy vào một SELECT có `IN`.
- [ ] Dùng `@BatchSize` ở cấp Entity để batch fetch proxy.
- [ ] Dùng `@BatchSize` trên collection để batch fetch nhiều collection owner.
- [ ] Cấu hình `spring.jpa.properties.hibernate.default_batch_fetch_size`.
- [ ] Phân biệt fetch batch với `hibernate.jdbc.batch_size`.
- [ ] Biết batch fetching không thay đổi `LAZY` thành `EAGER`.
- [ ] Chọn được giữa batch fetching, JOIN FETCH, EntityGraph và DTO projection.
- [ ] Bật Hibernate statistics và quan sát số prepared statement.
- [ ] Viết được integration test cho batch Entity proxy và collection.
- [ ] Chọn batch size dựa trên dữ liệu đo và giới hạn database.

Khi hoàn thành, bạn có thể áp dụng batch fetching của Hibernate để giảm N+1 có kiểm soát, cấu hình batch size ở đúng phạm vi và xác nhận hiệu quả bằng SQL cùng Hibernate statistics.