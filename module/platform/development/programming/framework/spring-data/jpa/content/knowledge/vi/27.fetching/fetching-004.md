# @EntityGraph, @NamedEntityGraph và attributePaths

## Mục tiêu

Khi truy vấn một entity có nhiều quan hệ, việc truy cập association lazy trong vòng lặp có thể tạo ra N+1 query: một query lấy danh sách gốc rồi thêm một query cho mỗi association được truy cập. Spring Data JPA và Jakarta Persistence cung cấp EntityGraph để mô tả những thuộc tính cần được tải cho một use case cụ thể.

Có hai cách khai báo thường dùng:

- `@NamedEntityGraph` định nghĩa một fetch graph có tên ngay trên entity mapping. Repository có thể tham chiếu lại graph đó ở nhiều method.
- `@EntityGraph(attributePaths = ...)` của Spring Data JPA tạo graph động ngay tại repository method. Cách này phù hợp khi fetch plan chỉ dùng ở một truy vấn.

EntityGraph giúp điều khiển fetch plan của query mà không phải đổi fetch type mặc định của association trên entity. Entity được trả về vẫn là entity JPA và vẫn tham gia persistence context.

Sau bài này, bạn có thể:

- Hiểu EntityGraph giải quyết vấn đề tải association như thế nào.
- Khai báo named graph và nested subgraph.
- Dùng `@EntityGraph` với tên graph hoặc `attributePaths`.
- Phân biệt `FETCH` và `LOAD` graph semantics.
- Dùng EntityGraph với derived query, `@Query` và EntityManager.
- Nhận biết ảnh hưởng của collection, phân trang và provider.
- Chọn giữa EntityGraph, fetch join, batch fetching và DTO projection.
- Kiểm thử trạng thái loaded và số lượng SQL thực tế.

Ví dụ sử dụng Java 17+, Spring Boot 3.x, Jakarta Persistence và Spring Data JPA.

## 1. EntityGraph là gì?

EntityGraph là mô tả về thuộc tính nào của một entity cần được tải khi thực hiện một thao tác đọc. Graph có thể chứa:

- Thuộc tính cơ bản như tên, trạng thái hoặc giá trị.
- Association to-one như `@ManyToOne` và `@OneToOne`.
- Association to-many như `@OneToMany` và `@ManyToMany`.
- Embedded attribute và các thuộc tính lồng nhau thông qua subgraph.

Ví dụ, entity Customer có Department và collection Orders. Màn hình danh sách chỉ cần Customer và Department; màn hình chi tiết cần thêm Orders và OrderItems. Có thể dùng hai fetch graph khác nhau cho hai use case thay vì đổi mapping mặc định thành EAGER.

EntityGraph là một fetch plan theo truy vấn. Nó không thay đổi kết quả thành DTO, không thay điều kiện WHERE, không thêm sort và không giới hạn số hàng. Nó cho provider biết association nào cần được nạp cùng use case đó.

### 1.1. Vì sao cần fetch plan theo use case?

Giả sử service đọc danh sách 50 khách hàng rồi hiển thị tên phòng ban:

```java
List<Customer> customers = customerRepository.findByActiveTrue();

for (Customer customer : customers) {
    System.out.println(customer.getDepartment().getName());
}
```

Nếu Department là LAZY và chưa được tải, Hibernate có thể phát sinh một query bổ sung cho từng Customer. Tổng số query có thể là một query lấy Customer cộng thêm nhiều query lấy Department.

EntityGraph cho phép yêu cầu Department được tải trong cùng fetch plan:

```java
@EntityGraph(attributePaths = "department")
List<Customer> findByActiveTrue();
```

Provider có thể dùng JOIN hoặc một chiến lược tải khác. Mục tiêu là tránh việc service vô tình kích hoạt một query riêng cho từng association khi duyệt kết quả.

### 1.2. EntityGraph không phải DTO

Kết quả của repository vẫn là entity Customer. Entity có thể được quản lý trong persistence context, dirty checking và lifecycle vẫn hoạt động như bình thường.

Nếu màn hình chỉ cần vài cột và không cần domain behavior, DTO projection có thể phù hợp hơn. EntityGraph tập trung vào việc tải association của entity; projection tập trung vào hình dạng dữ liệu trả về.

## 2. Mô hình entity dùng trong ví dụ

Giả sử hệ thống có Customer, Department, PurchaseOrder và OrderItem. Các association mặc định để LAZY để ứng dụng chọn fetch plan theo use case.

Customer:

```java
package com.example.demo.customer;

import jakarta.persistence.*;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "customers")
@NamedEntityGraph(
    name = "Customer.detail",
    attributeNodes = {
        @NamedAttributeNode("department"),
        @NamedAttributeNode(value = "orders", subgraph = "ordersGraph")
    },
    subgraphs = {
        @NamedSubgraph(
            name = "ordersGraph",
            attributeNodes = {
                @NamedAttributeNode("items")
            }
        )
    }
)
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    @Column(nullable = false)
    private boolean active;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "department_id")
    private Department department;

    @OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
    private List<PurchaseOrder> orders = new ArrayList<>();

    protected Customer() {
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public boolean isActive() {
        return active;
    }

    public Department getDepartment() {
        return department;
    }

    public List<PurchaseOrder> getOrders() {
        return orders;
    }
}
```

Department:

```java
@Entity
@Table(name = "departments")
public class Department {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    protected Department() {
    }

    public String getName() {
        return name;
    }
}
```

PurchaseOrder:

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderItem> items = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public List<OrderItem> getItems() {
        return items;
    }
}
```

OrderItem:

```java
@Entity
@Table(name = "order_items")
public class OrderItem {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "order_id")
    private PurchaseOrder order;

    @Column(nullable = false)
    private String productName;

    protected OrderItem() {
    }

    public String getProductName() {
        return productName;
    }
}
```

Các entity trên là những đoạn minh họa mapping cần thiết cho graph. Trong dự án thật, bổ sung constructor, phương thức cập nhật quan hệ, equals/hashCode và validation theo quy ước domain; không thêm chúng vào graph chỉ để làm fetch plan.

## 3. Khai báo @NamedEntityGraph

`@NamedEntityGraph` là annotation của Jakarta Persistence, khai báo trên entity. Mỗi graph có một tên duy nhất trong persistence unit và danh sách attribute node cần tải.

Ví dụ trong Customer:

```java
@NamedEntityGraph(
    name = "Customer.detail",
    attributeNodes = {
        @NamedAttributeNode("department"),
        @NamedAttributeNode(value = "orders", subgraph = "ordersGraph")
    },
    subgraphs = {
        @NamedSubgraph(
            name = "ordersGraph",
            attributeNodes = @NamedAttributeNode("items")
        )
    }
)
@Entity
public class Customer {
    // ...
}
```

Giải thích:

- `name = "Customer.detail"`: tên graph được repository hoặc EntityManager tham chiếu.
- `@NamedAttributeNode("department")`: tải association department.
- `@NamedAttributeNode(value = "orders", subgraph = "ordersGraph")`: tải orders và áp dụng subgraph cho từng order.
- `@NamedSubgraph`: mô tả thuộc tính cần tải tiếp bên trong PurchaseOrder.
- `@NamedAttributeNode("items")`: tải collection items của mỗi order.

Tên trong attribute node là thuộc tính Java của entity, không phải tên bảng hoặc tên cột SQL. Ví dụ dùng `department`, không dùng tên cột `department_id`.

### 3.1. Nhiều named graph trên một entity

Một entity có thể khai báo nhiều graph. Dùng `@NamedEntityGraphs` để nhóm các khai báo:

```java
@NamedEntityGraphs({
    @NamedEntityGraph(
        name = "Customer.list",
        attributeNodes = {
            @NamedAttributeNode("department")
        }
    ),
    @NamedEntityGraph(
        name = "Customer.detail",
        attributeNodes = {
            @NamedAttributeNode("department"),
            @NamedAttributeNode(value = "orders", subgraph = "ordersGraph")
        },
        subgraphs = {
            @NamedSubgraph(
                name = "ordersGraph",
                attributeNodes = @NamedAttributeNode("items")
            )
        }
    )
})
@Entity
public class Customer {
    // ...
}
```

`Customer.list` dành cho danh sách chỉ cần Department; `Customer.detail` dành cho màn hình chi tiết cần thêm Orders và Items.

Tên graph nên thể hiện use case hoặc mức dữ liệu cần tải. Tránh đặt tên mơ hồ như `graph1` hoặc tạo một graph khổng lồ chứa mọi association.

## 4. Nested graph và subgraph

Graph có thể mô tả nhiều cấp quan hệ. Nếu chỉ khai báo:

```java
@NamedAttributeNode("orders")
```

provider được yêu cầu tải association orders. Các association bên trong PurchaseOrder vẫn theo fetch graph và mapping mặc định; không tự hiểu rằng items cũng phải được tải.

Để chỉ định cấp tiếp theo, dùng subgraph:

```java
@NamedEntityGraph(
    name = "Customer.ordersWithItems",
    attributeNodes = @NamedAttributeNode(
        value = "orders",
        subgraph = "orderItems"
    ),
    subgraphs = @NamedSubgraph(
        name = "orderItems",
        attributeNodes = @NamedAttributeNode("items")
    )
)
```

Nếu OrderItem có association Product và use case cần tên sản phẩm, có thể tiếp tục tạo subgraph cho items:

```java
@NamedEntityGraph(
    name = "Customer.ordersWithProduct",
    attributeNodes = @NamedAttributeNode(
        value = "orders",
        subgraph = "orderGraph"
    ),
    subgraphs = {
        @NamedSubgraph(
            name = "orderGraph",
            attributeNodes = @NamedAttributeNode(
                value = "items",
                subgraph = "itemGraph"
            )
        ),
        @NamedSubgraph(
            name = "itemGraph",
            attributeNodes = @NamedAttributeNode("product")
        )
    }
)
```

Tên subgraph được tham chiếu bởi attribute node tương ứng. Các node phải khớp với persistent attribute của type đang được mô tả ở cấp đó.

Subgraph giúp khai báo fetch plan sâu nhưng không nên mở rộng vô hạn. Mỗi association to-many có thể làm tăng số hàng trong kết quả SQL; nhiều collection cùng được tải có thể gây lượng dữ liệu rất lớn hoặc giới hạn riêng của provider.

## 5. Dùng named graph trong Spring Data JPA

Spring Data JPA cung cấp annotation `@EntityGraph` trong package `org.springframework.data.jpa.repository`. Có thể tham chiếu graph đã khai báo bằng thuộc tính `value`:

```java
package com.example.demo.customer;

import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @EntityGraph(value = "Customer.detail")
    Optional<Customer> findWithDetailById(Long id);

    @EntityGraph(value = "Customer.list")
    List<Customer> findByActiveTrue();
}
```

Spring Data áp dụng named graph vào query do repository method thực thi. Method name vẫn quyết định điều kiện truy vấn; EntityGraph chỉ bổ sung fetch plan.

Ví dụ gọi:

```java
Customer customer = repository.findWithDetailById(id)
        .orElseThrow();
```

Khi dùng graph `Customer.detail`, provider được yêu cầu tải department, orders và items theo graph đã khai báo. Cách SQL được tạo ra tùy provider.

### 5.1. Dùng với @Query

Có thể đặt `@EntityGraph` trên method khai báo JPQL:

```java
@EntityGraph(value = "Customer.detail")
@Query("""
       select c
       from Customer c
       where c.id = :id
       """)
Optional<Customer> loadDetail(@Param("id") Long id);
```

Query xác định Customer nào được chọn; named graph xác định association nào cần được tải cho kết quả entity.

Nếu query trả DTO/scalar thay vì entity, EntityGraph có thể không có tác dụng như với entity result. Hãy dùng projection cho dữ liệu phẳng và kiểm tra provider khi kết hợp graph với query result mapping đặc biệt.

## 6. Dùng attributePaths để tạo dynamic graph

Không phải fetch plan nào cũng cần khai báo tên graph trên entity. Spring Data JPA hỗ trợ tạo graph động ngay trên repository method bằng `attributePaths`:

```java
@EntityGraph(attributePaths = {"department"})
List<Customer> findByActiveTrue();
```

Ví dụ tải nhiều association:

```java
@EntityGraph(attributePaths = {
    "department",
    "orders",
    "orders.items"
})
Optional<Customer> findDetailedById(Long id);
```

`attributePaths` nhận các property path của entity. Có thể dùng đường dẫn lồng nhau như `orders.items`. Spring Data xây dựng dynamic EntityGraph từ các path này; không cần khai báo `@NamedEntityGraph` tương ứng trên entity.

### 6.1. Khi nào dùng attributePaths?

Dùng dynamic graph khi:

- Fetch plan chỉ phục vụ một hoặc vài repository method.
- Graph đơn giản và không cần tái sử dụng ở nhiều nơi.
- Muốn nhìn thấy ngay association được tải khi đọc method.
- Không muốn thêm metadata named graph vào entity chỉ cho một use case.

Ví dụ:

```java
Customer customer = repository.findByIdWithDepartment(id)
        .orElseThrow();
```

Method `findByIdWithDepartment` được khai báo ở Mục 12 với `@EntityGraph(attributePaths = {"department"})` và `@Query` lọc theo ID. Cách này làm rõ rằng use case đọc Customer theo ID cần Department.

### 6.2. Khi nào dùng named graph?

Named graph phù hợp khi:

- Nhiều repository method hoặc use case cần cùng fetch plan.
- Graph có nhiều cấp subgraph.
- Muốn tập trung metadata fetch plan cạnh entity mapping.
- Tên graph là một phần quy ước rõ ràng của domain.

Ví dụ nhiều method có thể dùng lại `Customer.detail` mà không phải lặp lại danh sách `attributePaths`.

### 6.3. attributePaths và value

Nếu khai báo `attributePaths`, Spring Data tạo dynamic graph từ các path đó; việc tra cứu named graph qua `value` không còn là cơ chế được dùng cho method đó. Vì vậy, nên chọn một cách khai báo rõ ràng cho từng method:

- Named graph: `@EntityGraph(value = "Customer.detail")`.
- Dynamic graph: `@EntityGraph(attributePaths = {"department", "orders"})`.

Không trộn hai kiểu với kỳ vọng Spring Data sẽ hợp nhất hai graph thành một.

## 7. FETCH và LOAD graph semantics

`@EntityGraph` của Spring Data có thuộc tính `type`, với hai lựa chọn:

- `EntityGraph.EntityGraphType.FETCH`
- `EntityGraph.EntityGraphType.LOAD`

Ví dụ:

```java
@EntityGraph(
    value = "Customer.detail",
    type = EntityGraph.EntityGraphType.FETCH
)
Optional<Customer> findWithFetchGraphById(Long id);
```

### 7.1. FETCH graph

Với fetch graph semantics:

- Thuộc tính có trong graph được xem như EAGER cho lần truy vấn này.
- Thuộc tính không có trong graph được xem như LAZY cho lần truy vấn này.
- Provider vẫn có thể tải thêm thuộc tính ngoài graph nếu cần theo đặc tả hoặc cách triển khai.

FETCH graph phù hợp khi muốn mô tả rõ những association cần thiết cho use case và giảm việc tải các association khác theo mapping mặc định.

### 7.2. LOAD graph

Với load graph semantics:

- Thuộc tính có trong graph được xem như EAGER cho lần truy vấn này.
- Thuộc tính không có trong graph giữ fetch behavior mặc định của mapping, tức EAGER vẫn EAGER và LAZY vẫn LAZY.

LOAD graph bổ sung những thuộc tính cần tải vào fetch plan hiện tại mà không yêu cầu các thuộc tính ngoài graph chuyển sang LAZY.

### 7.3. So sánh

| Nội dung | FETCH | LOAD |
|---|---|---|
| Thuộc tính trong graph | EAGER cho query | EAGER cho query |
| Thuộc tính ngoài graph | LAZY theo graph semantics | Theo mapping mặc định |
| Ý định | Xác định fetch plan cụ thể | Bổ sung vào fetch plan mặc định |
| Mặc định của Spring Data @EntityGraph | Có | Không |

JPA provider được phép tải thêm dữ liệu ngoài graph. Vì vậy, không nên coi FETCH graph là cam kết rằng SQL chỉ chứa đúng các cột/association được liệt kê. Hãy kiểm tra SQL và loaded state thực tế.

## 8. Dùng EntityGraph trực tiếp với EntityManager

Khi cần tạo fetch plan tại runtime, Jakarta Persistence cho phép tạo graph bằng EntityManager:

```java
EntityGraph<Customer> graph =
        entityManager.createEntityGraph(Customer.class);

graph.addAttributeNodes("department");

Subgraph<PurchaseOrder> ordersGraph =
        graph.addSubgraph("orders");

ordersGraph.addAttributeNodes("items");

TypedQuery<Customer> query = entityManager.createQuery(
        "select c from Customer c where c.id = :id",
        Customer.class
);

query.setParameter("id", id);
query.setHint("jakarta.persistence.fetchgraph", graph);

Customer customer = query.getSingleResult();
```

Các bước:

1. Tạo graph cho Customer.
2. Thêm association department.
3. Tạo subgraph cho orders.
4. Thêm items vào subgraph.
5. Đặt graph vào query bằng hint `jakarta.persistence.fetchgraph`.

Có thể lấy named graph đã khai báo:

```java
EntityGraph<?> graph =
        entityManager.getEntityGraph("Customer.detail");

query.setHint("jakarta.persistence.fetchgraph", graph);
```

Nếu cần LOAD semantics, dùng hint `jakarta.persistence.loadgraph`. Tên hint dùng namespace Jakarta trong Spring Boot 3.x. Ứng dụng Spring Boot 2.x cũ dùng `javax.persistence.fetchgraph` hoặc `javax.persistence.loadgraph` theo API tương ứng.

## 9. EntityGraph giúp xử lý N+1 như thế nào?

N+1 thường xảy ra khi query lấy N entity gốc rồi truy cập lazy association của từng entity:

```java
List<Customer> customers = repository.findByActiveTrue();

for (Customer customer : customers) {
    String departmentName = customer.getDepartment().getName();
    // ...
}
```

Nếu Department chưa được tải, provider có thể thực hiện thêm một SELECT cho mỗi Customer.

Thêm graph:

```java
@EntityGraph(attributePaths = "department")
List<Customer> findByActiveTrue();
```

Provider có thể tạo một query JOIN để lấy Customer và Department, hoặc dùng chiến lược tải khác. Số query thực tế cần được đo.

EntityGraph thường hữu ích với to-one association vì JOIN thường không làm nhân bản số hàng gốc quá nhiều. Với to-many, số hàng SQL có thể tăng nhanh do một Customer có nhiều Order và mỗi Order có nhiều Item.

### 9.1. Đừng dùng graph để tải mọi association

Một graph gồm nhiều collection có thể tạo Cartesian multiplication. Ví dụ một Customer có 10 Orders và 5 Addresses; nếu cả hai collection được JOIN cùng lúc, một Customer có thể tạo nhiều hàng kết hợp trong result set.

Hậu quả có thể gồm:

- Nhiều dữ liệu lặp trên đường truyền.
- Tăng bộ nhớ và chi phí hydrate entity.
- Query chậm dù số entity gốc không lớn.
- Provider gặp giới hạn khi fetch đồng thời nhiều bag collection.
- Phân trang trở nên khó dự đoán.

Chỉ tải association cần cho use case. Nếu cần xử lý collection lớn, cân nhắc batch fetching, query riêng, DTO projection hoặc chia thành nhiều bước.

## 10. EntityGraph và phân trang collection

Cần đặc biệt cẩn thận khi kết hợp graph tải collection với `Pageable`:

```java
Page<Customer> pageWithOrders =
        repository.findActiveWithOrders(pageable);
```

Method `findActiveWithOrders` được khai báo ở Mục 12 với `@EntityGraph(attributePaths = {"orders"})` và `@Query`; ví dụ này minh họa trường hợp phân trang tải collection cần thận trọng.

Nếu provider thực thi collection fetch bằng JOIN, giới hạn trang có thể áp dụng trên các hàng JOIN thay vì số Customer logic. Hibernate có thể phải phân trang trong bộ nhớ hoặc phát cảnh báo khi query fetch collection kết hợp firstResult/maxResults.

Không giả định EntityGraph tự bảo đảm pagination hiệu quả cho to-many association. Cần kiểm tra SQL, log và query plan trên provider thật.

Các lựa chọn an toàn hơn:

**Bước 1: phân trang ID hoặc entity gốc.**

```java
Page<Customer> page =
        repository.findByActiveTrue(pageable);
```

Repository phải khai báo method phân trang tương ứng; method này không gắn collection fetch graph:

```java
Page<Customer> findByActiveTrue(Pageable pageable);
```

**Bước 2: tải chi tiết theo danh sách ID với graph.**

```java
List<Long> ids = page.getContent().stream()
        .map(Customer::getId)
        .toList();

List<Customer> details = repository.findWithOrdersByIdIn(ids);
```

Sau đó ánh xạ kết quả về thứ tự ID trong Page ban đầu, vì điều kiện IN không bảo đảm giữ thứ tự của danh sách đầu vào.

Một lựa chọn khác là DTO projection chỉ lấy các trường cần cho trang, hoặc tải collection theo batch khi thực sự cần truy cập chúng.

Nếu dùng Hibernate, có thể bật cấu hình kiểm tra nghiêm ngặt `hibernate.query.fail_on_pagination_over_collection_fetch=true` trong môi trường phát triển/test để phát hiện query phân trang collection fetch thay vì để ứng dụng âm thầm xử lý trong bộ nhớ. Cấu hình và tên property cần đối chiếu với Hibernate version đang dùng.

## 11. EntityGraph, fetch join và các chiến lược khác

Các kỹ thuật tải dữ liệu có mục đích khác nhau:

| Kỹ thuật | Mô tả | Khi phù hợp |
|---|---|---|
| EntityGraph | Fetch plan theo query, khai báo named hoặc dynamic | Nhiều use case cần các graph khác nhau |
| JOIN FETCH | Viết rõ association cần fetch trong JPQL | Query cụ thể cần kiểm soát JOIN |
| LAZY | Tải association khi truy cập | Mặc định hợp lý cho nhiều association |
| EAGER | Mapping yêu cầu association được tải sớm | Chỉ dùng khi đó là nhu cầu thực sự ổn định của domain |
| Batch fetching | Tải nhiều association lazy theo nhóm | Cần tránh N+1 mà không JOIN mọi collection |
| DTO projection | Chỉ chọn các trường/giá trị cần trả về | Read model, danh sách, báo cáo, API |

Ví dụ fetch join:

```java
@Query("""
       select c
       from Customer c
       left join fetch c.department
       where c.active = true
       """)
List<Customer> findActiveWithDepartment();
```

EntityGraph:

```java
@EntityGraph(attributePaths = "department")
List<Customer> findByActiveTrue();
```

Hai cách có thể đạt mục tiêu tải Department, nhưng EntityGraph tách fetch plan khỏi JPQL và dễ thay đổi theo method. Fetch join thể hiện trực tiếp JOIN trong query và hữu ích khi cần điều khiển query cụ thể.

Không có cách nào luôn tốt hơn. Với graph đơn giản và có thể tái sử dụng, EntityGraph thường dễ quản lý. Với query cần nhiều biểu thức, JOIN, DISTINCT hoặc logic SQL cụ thể, JPQL/custom repository có thể rõ ràng hơn.

## 12. Kiểm thử EntityGraph

Test nên xác nhận association được tải theo graph và không dựa vào persistence context còn giữ entity từ bước setup.

Ví dụ repository:

```java
import java.util.Collection;
import java.util.List;
import java.util.Optional;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @EntityGraph(value = "Customer.detail")
    Optional<Customer> findWithDetailById(Long id);

    @EntityGraph(attributePaths = {"department"})
    List<Customer> findByActiveTrue();

    // Used by Section 10: paginate Customer roots without fetching collections.
    Page<Customer> findByActiveTrue(Pageable pageable);

    // Collection-fetch pagination example discussed in Section 10.
    @EntityGraph(attributePaths = {"orders"})
    @Query("select c from Customer c where c.active = true")
    Page<Customer> findActiveWithOrders(Pageable pageable);

    @EntityGraph(attributePaths = {"orders"})
    @Query("select distinct c from Customer c where c.id in :ids")
    List<Customer> findWithOrdersByIdIn(@Param("ids") Collection<Long> ids);

    @EntityGraph(attributePaths = "department")
    @Query("select c from Customer c where c.id = :id")
    Optional<Customer> findByIdWithDepartment(@Param("id") Long id);
}
```

Test với `@DataJpaTest`:

```java
@DataJpaTest
class CustomerEntityGraphTest {

    @Autowired
    private CustomerRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    @Autowired
    private EntityManagerFactory entityManagerFactory;

    @Test
    void namedGraphLoadsDepartmentOrdersAndItems() {
        Customer customer = createCustomerWithDepartmentOrderAndItem();
        entityManager.persist(customer);
        entityManager.flush();

        Long id = customer.getId();
        entityManager.clear();

        Customer loaded = repository.findWithDetailById(id)
                .orElseThrow();

        PersistenceUnitUtil util =
                entityManagerFactory.getPersistenceUnitUtil();

        assertThat(util.isLoaded(loaded, "department")).isTrue();
        assertThat(util.isLoaded(loaded, "orders")).isTrue();

        PurchaseOrder order = loaded.getOrders().get(0);
        assertThat(util.isLoaded(order, "items")).isTrue();
    }
}
```

`createCustomerWithDepartmentOrderAndItem()` ở đây là fixture helper cần triển khai theo constructor và cách quản lý quan hệ của domain thật. Test phải persist quan hệ hai chiều đúng cách, ví dụ đặt Customer vào PurchaseOrder và thêm PurchaseOrder vào collection Customer nếu mapping yêu cầu đồng bộ cả hai phía.

`flush()` ghi fixture xuống database; `clear()` xóa persistence context để query phải nạp lại dữ liệu. `PersistenceUnitUtil.isLoaded(entity, attributeName)` kiểm tra trạng thái loaded của thuộc tính mà không cần đọc giá trị association để kích hoạt lazy load.

### 12.1. Kiểm tra dynamic graph

Với method dùng attributePaths, có thể kiểm tra tương tự:

```java
@Test
void dynamicGraphLoadsDepartmentUsingDedicatedRepositoryMethod() {
    Customer customer = createCustomerWithDepartment();
    entityManager.persist(customer);
    entityManager.flush();

    Long id = customer.getId();
    entityManager.clear();

    // Uses the repository method annotated with @EntityGraph(attributePaths = "department").
    Customer loaded = repository.findByIdWithDepartment(id).orElseThrow();

    assertThat(
            entityManagerFactory.getPersistenceUnitUtil()
                    .isLoaded(loaded, "department")
    ).isTrue();
}
```

Nếu repository method có tên khác như `findByActiveTrue`, hãy gọi đúng method đã gắn dynamic graph trong test. Test cần bảo đảm fixture có association để kiểm tra.

### 12.2. Loaded state chưa chứng minh số lượng SQL

`isLoaded` xác nhận trạng thái association, nhưng không chứng minh query chỉ chạy một SQL. Provider có thể tải association bằng JOIN, SELECT bổ sung hoặc một chiến lược khác.

Để xác nhận N+1 đã được giải quyết, kết hợp:

- Hibernate SQL logging hoặc datasource query counter.
- Hibernate Statistics nếu đã bật.
- Dữ liệu test có nhiều entity gốc và association.
- So sánh số query trước/sau khi áp dụng graph.
- Integration test trên database/provider tương ứng môi trường triển khai.

Không viết assertion phụ thuộc toàn bộ chuỗi SQL nếu mục tiêu chỉ là kiểm tra semantics; SQL có thể thay đổi theo version/provider. Dành kiểm tra query count cho một test hiệu năng có kiểm soát.

## 13. Những giới hạn và lưu ý khi dùng EntityGraph

**Provider quyết định cách thực thi.** Graph mô tả fetch plan, không bắt buộc phải dùng một câu JOIN duy nhất. Hibernate, EclipseLink và version khác nhau có thể tạo SQL khác nhau.

**Provider có thể tải thêm thuộc tính.** Không xem graph là cam kết rằng mọi thuộc tính ngoài danh sách chắc chắn chưa được tải.

**Collection có thể nhân bản hàng.** JOIN nhiều collection làm result set lớn và có thể gặp giới hạn của provider.

**Pagination với collection cần thiết kế riêng.** Phân trang trên query fetch to-many có thể sai semantics hoặc bị thực hiện trong bộ nhớ.

**Graph không thay thế projection.** Nếu chỉ cần một vài field, DTO projection có thể nhẹ hơn việc hydrate entity graph.

**Graph không phải authorization.** Việc association được tải không có nghĩa caller được phép xem mọi dữ liệu trong association. Kiểm tra quyền ở service/query và giới hạn dữ liệu trả về.

**Không thay đổi mapping mặc định.** EntityGraph chỉ áp dụng cho query được gắn graph; các use case khác vẫn dùng fetch behavior theo mapping.

**Native query cần xác minh riêng.** Khả năng áp dụng EntityGraph cho native result phụ thuộc provider và cách result được map; không giả định hành vi giống JPQL entity query.

**Không để graph thành một danh sách tải tất cả.** Fetch plan quá rộng có thể gây chậm hơn N+1 ban đầu vì dữ liệu lặp và lượng association được hydrate quá lớn.

## 14. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Named graph không được tìm thấy | Sai graph name hoặc graph chưa khai báo trên entity | Đối chiếu name và mapping |
| Attribute node không hợp lệ | Dùng tên cột SQL thay cho property Java | Dùng persistent attribute name |
| Nested association vẫn lazy | Thiếu subgraph hoặc nested path | Khai báo subgraph/attributePaths ở cấp cần tải |
| Dynamic graph không có tác dụng | Đặt nhầm method hoặc query không trả entity phù hợp | Kiểm tra repository method và result type |
| Query vẫn có nhiều SELECT | Provider chọn chiến lược tải khác hoặc graph chưa bao phủ association cần dùng | Xem SQL và loaded state |
| SQL trả quá nhiều hàng | JOIN nhiều collection | Thu hẹp graph, batch fetch hoặc tách query |
| Page chậm hoặc cảnh báo in-memory pagination | Graph tải collection trong query phân trang | Phân trang ID trước rồi tải chi tiết theo batch |
| Nhiều association bị tải ngoài dự kiến | Dùng LOAD graph hoặc mapping EAGER | Hiểu FETCH/LOAD semantics và kiểm tra mapping |
| Test báo association đã loaded dù query không tải | Entity còn trong persistence context từ fixture | Flush rồi clear trước khi gọi repository |
| Test pass nhưng vẫn có N+1 | Chỉ kiểm tra kết quả/loaded state, không đo query count | Bật SQL logging hoặc query counter |
| Native query không áp dụng graph | Provider/result mapping không hỗ trợ như mong đợi | Kiểm thử riêng hoặc dùng custom mapping |

## 15. Checklist chọn và áp dụng EntityGraph

- [ ] Xác định association mà use case thực sự cần.
- [ ] Giữ LAZY làm lựa chọn mặc định hợp lý cho association, rồi chọn fetch plan theo query.
- [ ] Dùng named graph khi nhiều method cần chung fetch plan.
- [ ] Dùng attributePaths khi graph chỉ phục vụ một repository method.
- [ ] Dùng subgraph cho association lồng nhau.
- [ ] Dùng property Java, không dùng tên bảng/cột SQL.
- [ ] Chọn FETCH hay LOAD theo semantics mong muốn.
- [ ] Không mặc định provider sẽ tạo một JOIN duy nhất.
- [ ] Cẩn thận với nhiều collection và MultipleBagFetchException của Hibernate.
- [ ] Không phân trang trực tiếp một graph tải collection nếu chưa kiểm tra SQL.
- [ ] Dùng DTO projection khi chỉ cần một tập trường phẳng.
- [ ] Flush/clear trong test trước khi kiểm tra loaded state.
- [ ] Đo query count để xác nhận N+1 đã được giảm.
- [ ] Kiểm thử với đúng JPA provider và database triển khai.
- [ ] Giữ authorization độc lập với fetch plan.

## Kết luận

`@NamedEntityGraph` định nghĩa fetch plan có tên ngay trên entity; `@EntityGraph(value = ...)` cho phép repository tái sử dụng graph đó. Khi chỉ cần một fetch plan nhỏ cho một method, `@EntityGraph(attributePaths = ...)` tạo dynamic graph mà không cần khai báo metadata riêng.

FETCH graph coi thuộc tính được liệt kê là EAGER cho query và các thuộc tính ngoài graph là LAZY theo graph semantics; LOAD graph giữ fetch behavior mặc định cho thuộc tính ngoài graph. Provider vẫn có thể tải thêm dữ liệu và quyết định cách tạo SQL.

Hãy chọn association theo use case, dùng subgraph cho quan hệ lồng nhau và đo SQL thực tế. Đặc biệt cẩn thận khi graph tải collection kết hợp với Page: phân trang ID rồi tải chi tiết theo batch hoặc dùng DTO projection thường dễ kiểm soát hơn. Kiểm thử loaded state sau khi clear persistence context và đo số query sẽ giúp xác nhận EntityGraph thực sự giải quyết N+1 mà không tạo một fetch plan quá rộng.
