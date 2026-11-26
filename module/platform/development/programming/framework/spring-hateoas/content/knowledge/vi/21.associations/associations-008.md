# Lazy association link

Trong một REST API, tài nguyên thường có quan hệ với tài nguyên khác. Ví dụ, một đơn hàng (`Order`) thuộc về một khách hàng (`Customer`). Representation của đơn hàng có thể công bố link relation `customer` trỏ tới tài nguyên khách hàng mà không cần nhúng toàn bộ dữ liệu khách hàng vào response.

Khi domain model dùng JPA/Hibernate với association `LAZY`, cần chú ý cách lấy định danh của tài nguyên liên quan để tạo link. Nếu đọc các thuộc tính của đối tượng liên quan, ORM có thể khởi tạo proxy và phát sinh truy vấn bổ sung. Một **lazy association link** là link được tạo từ thông tin định danh của quan hệ trong khi nội dung entity đích vẫn chưa được tải.

Spring HATEOAS cung cấp các kiểu `Link`, `EntityLinks`, `WebMvcLinkBuilder` và representation model để công bố quan hệ này. HATEOAS không tự biến mọi association JPA thành link trong controller viết thủ công; assembler hoặc processor cần chủ động tạo link theo hợp đồng API.

## Association, lazy loading và association link

Ba khái niệm liên quan nhưng có vai trò khác nhau:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| JPA association | Quan hệ giữa các entity trong mô hình persistence | `Order.customer` được ánh xạ bằng `@ManyToOne` |
| Lazy loading | Trì hoãn tải trạng thái entity liên quan cho tới khi cần truy cập | `Customer` được giữ dưới dạng proxy chưa khởi tạo |
| Hypermedia association link | Link trong representation cho client điều hướng tới tài nguyên liên quan | `_links.customer.href` trỏ tới `/customers/{id}` |

Lazy loading là chiến lược truy xuất dữ liệu ở server. Association link là một phần của hợp đồng HTTP. Link chỉ cần URI đích và relation; nó không yêu cầu server tải mọi trường của entity đích.

Ví dụ, response đơn hàng có thể chứa:

```json
{
  "id": "a7c1f4d2-55a1-4e51-93a2-88a12d1e1001",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "https://api.example.com/orders/a7c1f4d2-55a1-4e51-93a2-88a12d1e1001"
    },
    "customer": {
      "href": "https://api.example.com/customers/6d2b8e4a-2a10-4d10-a5d3-9b9f5e3a2002"
    }
  }
}
```

Client có thể theo link `customer` khi cần thông tin khách hàng. Response đơn hàng không cần nhúng tên, địa chỉ hoặc các dữ liệu khác của khách hàng nếu use case hiện tại không cần chúng.

## Association lazy trong JPA

Một entity đơn hàng có thể ánh xạ quan hệ nhiều đơn hàng tới một khách hàng:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import java.util.UUID;

@Entity
@Table(name = "orders")
public class Order {

    @Id
    private UUID id;

    private String status;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    private Customer customer;

    protected Order() {}

    public UUID getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }

    public Customer getCustomer() {
        return customer;
    }
}
```

Với `FetchType.LAZY`, persistence provider có thể trả về một proxy đại diện cho `Customer`. Khi truy cập thuộc tính cần trạng thái thực của khách hàng, Hibernate có thể phát truy vấn để khởi tạo proxy. Vì vậy, đoạn code sau có thể làm phát sinh truy vấn bổ sung:

```java
String customerName = order.getCustomer().getName();
```

Nếu assembler chỉ cần URI của khách hàng, tải tên khách hàng là không cần thiết. Cần lấy ID của association và dùng ID đó tạo link.

## Tạo link từ ID bằng EntityLinks

`EntityLinks` cho phép tạo link tới collection hoặc item resource dựa trên domain type. Controller expose resource nên khai báo `@ExposesResourceFor` để implementation dựa trên controller mapping biết loại tài nguyên mà controller quản lý:

```java
import org.springframework.hateoas.server.ExposesResourceFor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import java.util.UUID;

@RestController
@ExposesResourceFor(Customer.class)
@RequestMapping("/customers")
class CustomerController {

    @GetMapping("/{id}")
    CustomerRepresentation one(@PathVariable UUID id) {
        return customerQueryService.findRepresentation(id);
    }
}
```

Controller đơn hàng cũng cần expose đúng domain type để `EntityLinks` tạo self link:

```java
@RestController
@ExposesResourceFor(Order.class)
@RequestMapping("/orders")
class OrderController {
    // Các endpoint collection và item của Order.
}
```

Khi đã có `customerId`, assembler có thể tạo link mà không cần tải `Customer`:

```java
import java.util.UUID;

public record OrderRepresentation(UUID id, String status) {}
```

Assembler có thể nhận projection và tạo link như sau:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.EntityLinks;
import org.springframework.stereotype.Component;

@Component
class OrderModelAssembler {

    private final EntityLinks entityLinks;

    OrderModelAssembler(EntityLinks entityLinks) {
        this.entityLinks = entityLinks;
    }

    EntityModel<OrderRepresentation> toModel(OrderView order) {
        OrderRepresentation body = new OrderRepresentation(
            order.id(), order.status());

        Link self = entityLinks
            .linkForItemResource(Order.class, order.id())
            .withSelfRel();

        EntityModel<OrderRepresentation> model = EntityModel.of(body, self);

        if (order.customerId() != null) {
            Link customer = entityLinks
                .linkForItemResource(Customer.class, order.customerId())
                .withRel("customer");
            model.add(customer);
        }

        return model;
    }
}
```

`OrderView` là projection chứa `id`, `status` và `customerId`; `OrderRepresentation` là DTO công bố qua API. Cách làm này giữ assembler độc lập với proxy JPA: assembler chỉ nhận ID của tài nguyên liên quan và tạo link `customer`. Link `self` của đơn hàng và link `customer` đều được xây từ mapping resource đã khai báo.

## Cách lấy ID mà không tải entity liên quan

Có một số cách tiếp cận. Hãy ưu tiên cách phù hợp với query và persistence provider của ứng dụng.

### Cách 1: Dùng projection lấy foreign key

Đây thường là cách dễ dự đoán nhất khi API chỉ cần ID của tài nguyên liên quan. Truy vấn chỉ lấy các trường cần thiết và ID quan hệ:

```java
import java.util.UUID;

public record OrderView(
    UUID id,
    String status,
    UUID customerId
) {}
```

Ví dụ giả định `OrderView` nằm trong package `com.example.orders`, đúng với tên lớp đầy đủ trong biểu thức JPQL; hãy thay package theo dự án thực tế.

```java
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.Repository;
import org.springframework.data.repository.query.Param;

interface OrderReadRepository extends Repository<Order, UUID> {

    @Query("""
        select new com.example.orders.OrderView(
            o.id, o.status, customer.id)
        from Order o
        left join o.customer customer
        where o.id = :id
        """)
    Optional<OrderView> findViewById(@Param("id") UUID id);
}
```

Truy vấn có thể join bảng khách hàng để lấy khóa ngoại, nhưng không hydrate toàn bộ `Customer` entity. Assembler nhận `customerId` dạng scalar và tạo link. Cách này phù hợp cho collection lớn vì có thể lấy ID liên quan trong cùng một truy vấn projection thay vì kích hoạt một truy vấn cho từng association.

Với collection, hãy cân nhắc projection tương tự cho mọi phần tử. Như vậy, số truy vấn không tăng theo số đơn hàng chỉ để tạo link khách hàng.

### Cách 2: Lấy identifier từ proxy

Nếu service đã có `Order` entity và association được biểu diễn bằng proxy, có thể lấy ID qua `PersistenceUnitUtil`:

```java
import jakarta.persistence.PersistenceUnitUtil;
import jakarta.persistence.EntityManagerFactory;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.EntityLinks;
import org.springframework.stereotype.Component;

@Component
class OrderModelAssembler {

    private final EntityLinks entityLinks;
    private final PersistenceUnitUtil persistenceUnitUtil;

    OrderModelAssembler(EntityLinks entityLinks,
                        EntityManagerFactory entityManagerFactory) {
        this.entityLinks = entityLinks;
        this.persistenceUnitUtil = entityManagerFactory.getPersistenceUnitUtil();
    }

    EntityModel<OrderRepresentation> toModel(Order order) {
        EntityModel<OrderRepresentation> model = EntityModel.of(
            new OrderRepresentation(order.getId(), order.getStatus()),
            entityLinks.linkForItemResource(Order.class, order.getId())
                .withSelfRel());

        Customer customer = order.getCustomer();
        if (customer != null) {
            Object customerId = persistenceUnitUtil.getIdentifier(customer);
            if (customerId != null) {
                Link customerLink = entityLinks
                    .linkForItemResource(Customer.class, customerId)
                    .withRel("customer");
                model.add(customerLink);
            }
        }

        return model;
    }
}
```

Đây là biến thể assembler dùng proxy để minh họa `PersistenceUnitUtil`; nó là phương án thay thế cho assembler dùng `OrderView` ở phần projection phía trên. Trong ứng dụng, chỉ đăng ký một implementation cho cùng vai trò `OrderModelAssembler`.

`PersistenceUnitUtil.getIdentifier(...)` trả về ID của entity. Với Hibernate proxy, việc lấy identifier thường không cần khởi tạo toàn bộ target entity. Tuy nhiên, hợp đồng JPA mô tả kết quả ID chứ không cam kết mọi provider đều thực hiện thao tác này mà không phát SQL. Hãy kiểm tra hành vi với provider, kiểu truy cập ID và phiên bản ORM của dự án bằng integration test.

Đoạn code chỉ nên chạy khi entity/proxy thuộc persistence unit tương ứng. Nếu association không tồn tại, không tạo link. Nếu API cần hiển thị dữ liệu khách hàng thay vì chỉ liên kết, hãy tải dữ liệu đó một cách có chủ đích qua projection hoặc fetch plan phù hợp.

### Cách 3: Dùng ID scalar được truy vấn riêng

Một số mô hình domain lưu sẵn ID liên quan trong read model hoặc projection. Khi đó assembler có thể nhận `customerId` trực tiếp. Tránh ánh xạ cùng một cột foreign key thành hai thuộc tính ghi độc lập; nếu cần một thuộc tính ID chỉ đọc song song với association, phải cấu hình mapping nhất quán, ví dụ cột ID phụ có `insertable = false, updatable = false`, và kiểm tra việc đồng bộ sau khi thay đổi association.

## Phân biệt link tới entity và association resource

Một relation link có thể trỏ thẳng tới item resource của entity liên quan:

```text
rel="customer"  href="/customers/{customerId}"
```

Đây là cách thường dùng trong controller Spring HATEOAS tự xây dựng. Client theo link để lấy representation của khách hàng.

Spring Data REST có khái niệm **association resource** riêng. Khi repository export một association, nó có thể công bố sub-resource theo dạng `/orders/{id}/customer`; endpoint association cho phép đọc hoặc thay đổi quan hệ theo các HTTP method mà Spring Data REST hỗ trợ. Đây là hợp đồng của Spring Data REST và khác với việc controller HATEOAS thủ công tạo link trực tiếp tới `/customers/{customerId}`.

Vì vậy, hãy xác định đích link theo ý nghĩa API:

| Mục đích | URI đích minh họa | Client dùng để |
| --- | --- | --- |
| Truy cập entity khách hàng | `/customers/{customerId}` | Đọc representation khách hàng |
| Truy cập association resource | `/orders/{orderId}/customer` | Đọc hoặc thao tác quan hệ khách hàng của đơn hàng theo hợp đồng Spring Data REST |

Không nên đặt relation `customer` tới một URI chỉ trả dữ liệu khác với điều mà client mong đợi. Relation và đích link cần có ngữ nghĩa rõ ràng.

## Tránh N+1 khi tạo association link cho collection

Giả sử một endpoint trả về 100 đơn hàng. Nếu assembler truy cập `order.getCustomer().getName()` cho từng đơn, ORM có thể phát thêm truy vấn để tải từng khách hàng. Đây là dạng N+1: một truy vấn lấy đơn hàng và nhiều truy vấn bổ sung cho association.

Nếu chỉ cần link `customer`, hãy lấy ID liên quan trong projection và tạo link từ ID. Nếu cần thêm tên khách hàng vào representation, hãy chọn fetch plan có chủ đích:

- Projection chỉ lấy các trường cần thiết từ cả hai bảng.
- `JOIN FETCH` hoặc `EntityGraph` khi cần entity liên quan trong một use case cụ thể.
- Batch fetching khi cần tải một nhóm association và provider hỗ trợ cấu hình phù hợp.

Không đổi mọi association thành `EAGER` chỉ để tạo link. Eager loading toàn cục có thể tải dữ liệu thừa, tăng kích thước truy vấn và gây vấn đề khi nhiều quan hệ cùng được mở rộng.

## Transaction và thời điểm tạo representation

Nếu assembler truy cập proxy, việc đó cần persistence context còn hiệu lực. Sau khi entity detached hoặc persistence context đóng, truy cập trạng thái chưa tải có thể gây `LazyInitializationException` trong Hibernate. Đừng dựa vào Open Session in View để vô tình tải association trong lúc serialize response.

Một luồng rõ ràng hơn là thực hiện truy vấn và ánh xạ sang DTO/projection trong service có transaction đọc, rồi trả representation đã hoàn chỉnh với link. Khi assembler chỉ làm việc với DTO và ID, việc serialize không phụ thuộc vòng đời proxy hoặc persistence context.

## Kiểm thử association link có thực sự lazy

Test cần xác nhận cả hợp đồng HTTP và trạng thái tải association. Với JPA, `PersistenceUnitUtil.isLoaded(entity, "customer")` có thể kiểm tra association đã được nạp hay chưa:

```java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.PersistenceUnitUtil;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
class LazyCustomerLinkTests {

    @Autowired
    OrderRepository orderRepository;

    @Autowired
    EntityManagerFactory entityManagerFactory;

    @Autowired
    OrderModelAssembler assembler;

    @Test
    @Transactional
    void createsCustomerLinkWithoutLoadingCustomerState() {
        Order order = orderRepository.findById(EXISTING_ORDER_ID)
            .orElseThrow();
        PersistenceUnitUtil persistenceUnitUtil =
            entityManagerFactory.getPersistenceUnitUtil();

        assertThat(persistenceUnitUtil.isLoaded(order, "customer"))
            .isFalse();

        assembler.toModel(order);

        assertThat(persistenceUnitUtil.isLoaded(order, "customer"))
            .isFalse();
    }
}
```

`EXISTING_ORDER_ID` phải trỏ tới fixture có customer khác null và association được cấu hình lazy. Test dùng transaction để giữ persistence context trong lúc kiểm tra. Nếu assembler dùng projection thay vì entity proxy, hãy kiểm tra query projection chỉ đọc các cột cần thiết và không hydrate `Customer` entity.

`isLoaded` kiểm tra trạng thái tải của association; để xác nhận chính xác số câu SQL, có thể dùng Hibernate Statistics, datasource-proxy hoặc SQL statement inspector trong integration test. Ví dụ, đặt bộ đếm SQL trước và sau khi gọi assembler, rồi xác nhận không có truy vấn select bổ sung vào bảng `customers` chỉ để tạo link.

Kiểm thử response HAL để bảo vệ relation và `href`:

```java
import static org.hamcrest.Matchers.endsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/orders/{id}", EXISTING_ORDER_ID)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.customer.href")
        .value(endsWith("/customers/" + EXISTING_CUSTOMER_ID)));
```

Nếu association là optional và không có khách hàng, test nên xác nhận link `customer` không xuất hiện. Không tạo link với ID null hoặc chuỗi URL thiếu định danh.

## Những lỗi thường gặp

- **Truy cập thuộc tính không cần thiết:** gọi `getName()` hoặc serialize toàn bộ proxy chỉ để tạo link, khiến association được tải.
- **Dùng entity làm response trực tiếp:** Jackson có thể đi qua các getter association, kích hoạt lazy loading hoặc tạo vòng tham chiếu.
- **N+1 query:** mỗi phần tử trong collection phát sinh một truy vấn tải entity liên quan.
- **Tạo link từ ID không có:** association optional hoặc dữ liệu mới chưa có ID nhưng assembler vẫn tạo URI.
- **Nhầm entity link với association resource:** client theo link nhưng nhận loại tài nguyên hoặc hành vi khác hợp đồng mong muốn.
- **Phụ thuộc persistence context khi serialize:** proxy bị truy cập sau khi session đóng và phát sinh `LazyInitializationException`.
- **Bật EAGER toàn cục:** tải quá nhiều dữ liệu để giải quyết một nhu cầu link nhỏ.
- **Cho rằng link là phân quyền:** link chỉ mô tả đường điều hướng; endpoint đích vẫn phải xác thực và kiểm tra quyền.

Lazy association link cho phép representation công bố quan hệ giữa các tài nguyên mà không phải nhúng hoặc tải toàn bộ entity liên quan. Cách ổn định nhất là lấy foreign key bằng projection rồi dùng `EntityLinks` tạo URI; khi làm việc với proxy, lấy identifier cần được kiểm chứng với persistence provider. Kết hợp kiểm thử trạng thái loaded, số câu SQL và response HAL giúp giữ hợp đồng hypermedia rõ ràng mà vẫn kiểm soát được chi phí truy vấn.

## Tài liệu tham khảo

- [Jakarta Persistence – PersistenceUnitUtil](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/PersistenceUnitUtil.html)
- [Spring HATEOAS API – EntityLinks](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/EntityLinks.html)
- [Spring Data REST – Repository resources and association resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
