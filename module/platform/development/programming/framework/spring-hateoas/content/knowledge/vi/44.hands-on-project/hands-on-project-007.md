# Thêm phân trang

## Mục tiêu dự án

Trong dự án này, bạn sẽ mở rộng REST API quản lý đơn hàng để trả về collection có phân trang bằng Spring HATEOAS. Client có thể đọc metadata của trang hiện tại, theo các link `first`, `prev`, `self`, `next` và `last` khi chúng khả dụng, đồng thời theo link `self` của từng order để xem tài nguyên riêng lẻ.

Kết quả cần đạt là endpoint `GET /orders` trả representation HAL có metadata phân trang và link điều hướng. Client không phải tự ghép URL trang kế tiếp từ số trang hoặc tự đoán cấu trúc route.

Dự án áp dụng các kiến thức cốt lõi của Spring HATEOAS: `RepresentationModel`, `RepresentationModelAssembler`, HAL, link relation, tích hợp Spring MVC và kiểm thử hợp đồng hypermedia.

## 1. Bài toán và hành vi mong muốn

Giả sử hệ thống có hàng nghìn đơn hàng. Nếu endpoint trả toàn bộ dữ liệu trong một response, payload sẽ tăng theo số bản ghi, tốn bộ nhớ và thời gian truyền, đồng thời client phải xử lý dữ liệu lớn dù chỉ cần một phần.

Ta cần hỗ trợ các tham số:

| Tham số | Ý nghĩa | Mặc định trong dự án |
|---|---|---|
| `page` | Chỉ số trang, bắt đầu từ 0 | `0` |
| `size` | Số phần tử tối đa trong một trang | `20` |
| `sort` | Thuộc tính và hướng sắp xếp | `createdAt,desc` |

Ví dụ:

```http
GET /orders?page=0&size=2&sort=createdAt,desc
Accept: application/hal+json
```

Server trả về trang đầu tiên gồm tối đa hai order. Nếu còn trang sau, response có link `next`. Khi client theo link đó, server cung cấp trang tiếp theo và link `prev` để quay lại.

Các nguyên tắc của dự án:

- Mỗi item là một representation có link `self`.
- Collection có metadata về trang và các link điều hướng.
- URL điều hướng được server tạo từ request hiện tại và `Pageable`.
- Client theo `href` trong response, không tự dựng URI.
- Kích thước trang và thuộc tính sắp xếp được kiểm soát.
- Các trang được sắp xếp ổn định để hạn chế bản ghi nhảy giữa các trang.

## 2. Chuẩn bị project

Dự án cần Spring Web, Spring Data JPA và Spring HATEOAS. Nếu dùng Spring Boot, để dependency management của Boot quản lý phiên bản tương thích.

Ví dụ các dependency Maven:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-hateoas</artifactId>
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
```

Nếu project đã có entity, repository và dependency tương ứng, hãy tái sử dụng chúng. Không tạo một mô hình Order thứ hai chỉ để làm bài thực hành.

Ví dụ cấu hình H2 cho môi trường local:

```properties
spring.datasource.url=jdbc:h2:mem:orders
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.h2.console.enabled=true

spring.data.web.pageable.default-page-size=20
spring.data.web.pageable.max-page-size=100
spring.data.web.pageable.one-indexed-parameters=false
```

Ba thuộc tính cuối đặt mặc định page size, giới hạn kích thước tối đa và giữ cách đánh số trang bắt đầu từ 0. Hãy điều chỉnh cấu hình theo phiên bản Spring Boot đang sử dụng. Với production, dùng migration quản lý schema thay vì `create-drop`.

## 3. Chuẩn bị dữ liệu và repository

Một order cần có ID, trạng thái, tổng tiền và thời điểm tạo. Ví dụ entity rút gọn:

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "orders")
public class Order {

    @Id
    private UUID id;

    @Column(nullable = false)
    private String status;

    @Column(nullable = false, precision = 15, scale = 2)
    private BigDecimal total;

    @Column(nullable = false)
    private Instant createdAt;

    protected Order() {
    }

    public Order(
            UUID id,
            String status,
            BigDecimal total,
            Instant createdAt) {
        this.id = id;
        this.status = status;
        this.total = total;
        this.createdAt = createdAt;
    }

    public UUID getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
```

Repository kế thừa `JpaRepository`:

```java
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository extends JpaRepository<Order, UUID> {
}
```

`JpaRepository` đã cung cấp `findAll(Pageable pageable)`, trả về `Page<Order>`. Spring Data chuyển thông tin page và sort thành truy vấn tương ứng. Với JPA, việc lấy một `Page` thường cần thêm count query để tính tổng số phần tử và tổng số trang.

Nếu hệ thống chưa dùng JPA, có thể thay repository bằng một nguồn dữ liệu hỗ trợ `Pageable`. Phần hypermedia ở controller vẫn dùng cùng nguyên tắc.

## 4. Tạo representation cho từng order

Không trả entity trực tiếp nếu API cần một hợp đồng response độc lập với cấu trúc persistence. Tạo model riêng kế thừa `RepresentationModel`:

```java
import java.math.BigDecimal;
import java.util.UUID;

import org.springframework.hateoas.RepresentationModel;

public class OrderModel extends RepresentationModel<OrderModel> {

    private final UUID id;
    private final String status;
    private final BigDecimal total;

    public OrderModel(UUID id, String status, BigDecimal total) {
        this.id = id;
        this.status = status;
        this.total = total;
    }

    public UUID getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }

    public BigDecimal getTotal() {
        return total;
    }
}
```

Assembler chịu trách nhiệm chuyển entity thành representation và gắn link `self`:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
public class OrderModelAssembler
        implements RepresentationModelAssembler<Order, OrderModel> {

    @Override
    public OrderModel toModel(Order order) {
        OrderModel model = new OrderModel(
                order.getId(),
                order.getStatus(),
                order.getTotal()
        );

        model.add(linkTo(methodOn(OrderController.class)
                .getOrder(order.getId()))
                .withSelfRel());

        return model;
    }
}
```

`linkTo(methodOn(...))` tạo link dựa trên mapping của controller. Khi đường dẫn của endpoint chi tiết thay đổi, assembler tiếp tục dùng mapping mới sau khi ứng dụng được cập nhật. Client chỉ cần tìm relation `self` trong representation.

Assembler chỉ mô tả tài nguyên. Phân trang collection sẽ do `PagedResourcesAssembler` đảm nhiệm ở bước tiếp theo.

## 5. Dùng PagedResourcesAssembler để tạo PagedModel

Spring Data cung cấp `PagedResourcesAssembler<T>` để chuyển `Page<T>` thành `PagedModel<R>` của Spring HATEOAS.

Hai kiểu dữ liệu có vai trò khác nhau:

| Kiểu | Trách nhiệm |
|---|---|
| `Page<Order>` | Kết quả truy vấn, nội dung trang và thông tin tổng số phần tử |
| `PagedResourcesAssembler<Order>` | Chuyển trang dữ liệu thành hypermedia representation |
| `PagedModel<OrderModel>` | Response collection có embedded items, page metadata và navigation links |

`PagedResourcesAssembler` thuộc Spring Data Web, package `org.springframework.data.web`. `PagedModel` là kiểu model phân trang của Spring HATEOAS. Trong các phiên bản cũ, một số tài liệu có thể dùng tên `PagedResources`; code hiện đại nên dùng `PagedModel`.

Controller có thể viết như sau:

```java
import java.util.UUID;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.data.web.PageableDefault;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.PagedModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderRepository orderRepository;
    private final OrderModelAssembler orderModelAssembler;

    public OrderController(
            OrderRepository orderRepository,
            OrderModelAssembler orderModelAssembler) {
        this.orderRepository = orderRepository;
        this.orderModelAssembler = orderModelAssembler;
    }

    @GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
    public PagedModel<OrderModel> listOrders(
            @PageableDefault(
                    size = 20,
                    sort = "createdAt",
                    direction = Sort.Direction.DESC
            ) Pageable pageable,
            PagedResourcesAssembler<Order> pagedAssembler) {

        Page<Order> page = orderRepository.findAll(pageable);

        return pagedAssembler.toModel(page, orderModelAssembler);
    }

    @GetMapping(
            value = "/{id}",
            produces = MediaTypes.HAL_JSON_VALUE
    )
    public OrderModel getOrder(@PathVariable UUID id) {
        Order order = orderRepository.findById(id)
                .orElseThrow(() -> new OrderNotFoundException(id));

        return orderModelAssembler.toModel(order);
    }
}
```

`OrderNotFoundException` là exception nghiệp vụ giả định của ứng dụng. Phần xử lý 404 có thể dùng `@RestControllerAdvice` và Problem Details theo hợp đồng lỗi hiện có.

Điểm quan trọng trong method `listOrders`:

1. Spring MVC phân tích query parameters và tạo `Pageable`.
2. Repository truy vấn đúng trang và thứ tự sắp xếp.
3. `PagedResourcesAssembler` chuyển mỗi `Order` qua `OrderModelAssembler`.
4. Assembler phân trang bổ sung metadata và link điều hướng.
5. Controller trả `PagedModel<OrderModel>` dưới media type HAL JSON.

Trong Spring Boot, Spring Data Web thường tự đăng ký resolver cho `Pageable` và assembler. Nếu dùng cấu hình Spring MVC tùy biến hoặc không có auto-configuration, hãy xác nhận `SpringDataWebConfiguration` và các bean liên quan đã được đăng ký.

## 6. Hiểu response HAL có phân trang

Một response minh họa khi trang đầu có hai order và còn trang tiếp:

```http
HTTP/1.1 200 OK
Content-Type: application/hal+json

{
  "_embedded": {
    "orders": [
      {
        "id": "order-42",
        "status": "PENDING",
        "total": 125000.00,
        "_links": {
          "self": {
            "href": "/orders/order-42"
          }
        }
      },
      {
        "id": "order-41",
        "status": "CONFIRMED",
        "total": 89000.00,
        "_links": {
          "self": {
            "href": "/orders/order-41"
          }
        }
      }
    ]
  },
  "_links": {
    "first": {
      "href": "/orders?page=0&size=2&sort=createdAt,desc"
    },
    "self": {
      "href": "/orders?page=0&size=2&sort=createdAt,desc"
    },
    "next": {
      "href": "/orders?page=1&size=2&sort=createdAt,desc"
    },
    "last": {
      "href": "/orders?page=4&size=2&sort=createdAt,desc"
    }
  },
  "page": {
    "size": 2,
    "totalElements": 10,
    "totalPages": 5,
    "number": 0
  }
}
```

Đây là response minh họa. Tên embedded relation `orders` phụ thuộc relation provider và kiểu representation được dùng trong ứng dụng. Hãy kiểm tra JSON runtime; nếu hợp đồng yêu cầu tên collection cụ thể, cấu hình relation provider hoặc cách biểu diễn collection tương ứng và kiểm thử tên đó.

Các trường `page` mô tả:

- `size`: số phần tử tối đa trong một trang.
- `totalElements`: tổng số phần tử phù hợp với truy vấn.
- `totalPages`: tổng số trang.
- `number`: chỉ số trang hiện tại, mặc định bắt đầu từ 0.

Các relation phân trang thường gặp:

| Relation | Vai trò |
|---|---|
| `first` | Đi đến trang đầu |
| `prev` | Đi đến trang trước nếu tồn tại |
| `self` | Trang hiện tại |
| `next` | Đi đến trang sau nếu tồn tại |
| `last` | Đi đến trang cuối |

Không phải link nào cũng xuất hiện ở mọi trang. Ví dụ trang đầu không có trang trước, trang cuối không có trang sau. Client phải kiểm tra sự hiện diện của relation thay vì giả định mọi response đều chứa đủ năm link.

## 7. Thử gọi endpoint và theo link

Khởi động ứng dụng rồi gửi request:

```bash
curl -i \
  -H "Accept: application/hal+json" \
  "http://localhost:8080/orders?page=0&size=2&sort=createdAt,desc"
```

Đọc response và tìm `_links.next.href`. Gửi request tiếp theo đến URI đó:

```bash
curl -i \
  -H "Accept: application/hal+json" \
  "http://localhost:8080/orders?page=1&size=2&sort=createdAt,desc"
```

Trong ứng dụng thực tế, client nên lấy nguyên URI từ `href` của link `next` và gửi request đến đó. URI trong ví dụ chỉ minh họa. Đừng ghép `page + 1` vào một URL được hard-code trong client.

Khi ở trang thứ hai, kiểm tra link `prev` và theo link đó để quay lại trang đầu. Sau đó theo `last` để kiểm tra trang cuối.

Có thể thử các trường hợp:

- Không truyền query parameter: server dùng page size mặc định.
- `size=1`: mỗi trang có tối đa một item.
- `page=2`: lấy trang có chỉ số 2.
- `sort=total,asc`: sắp xếp tổng tiền tăng dần nếu thuộc tính được cho phép.
- `page=999`: trang vượt quá dữ liệu; response vẫn cần metadata nhất quán và không có item.

## 8. Kiểm soát page size và sort

Không nên để client yêu cầu kích thước trang tùy ý. Page size quá lớn có thể gây truy vấn nặng, response lớn và tăng áp lực bộ nhớ.

Cấu hình giới hạn tối đa trong Spring Boot:

```properties
spring.data.web.pageable.default-page-size=20
spring.data.web.pageable.max-page-size=100
spring.data.web.pageable.one-indexed-parameters=false
```

Ngoài cấu hình resolver, service nên xác thực thuộc tính sort. Không nên cho client sắp xếp theo mọi field của entity, đặc biệt các field nội bộ hoặc quan hệ có thể tạo truy vấn đắt.

Ví dụ service kiểm soát sort và bổ sung khóa duy nhất làm tie-breaker:

```java
import java.util.Set;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;

@Service
public class OrderQueryService {

    private static final int MAX_PAGE_SIZE = 100;

    private static final Set<String> ALLOWED_SORTS = Set.of(
            "createdAt",
            "status",
            "total"
    );

    private final OrderRepository repository;

    public OrderQueryService(OrderRepository repository) {
        this.repository = repository;
    }

    public Page<Order> findOrders(Pageable requested) {
        requested.getSort().forEach(order -> {
            if (!ALLOWED_SORTS.contains(order.getProperty())) {
                throw new InvalidSortParameterException(
                        order.getProperty()
                );
            }
        });

        int safeSize = Math.min(
                requested.getPageSize(),
                MAX_PAGE_SIZE
        );

        Sort stableSort = requested.getSort()
                .and(Sort.by(Sort.Direction.ASC, "id"));

        Pageable safePageable = PageRequest.of(
                requested.getPageNumber(),
                safeSize,
                stableSort
        );

        return repository.findAll(safePageable);
    }
}
```

`InvalidSortParameterException` là exception tùy ứng dụng, cần ánh xạ thành lỗi 400 có error representation rõ ràng. Nếu resolver đã giới hạn page size, kiểm tra trong service vẫn là lớp bảo vệ bổ sung khi service được gọi từ nơi khác.

Khóa `id` được thêm vào sort để tạo thứ tự xác định khi nhiều order có cùng `createdAt` hoặc `total`. Nếu không có tie-breaker, hai request liên tiếp có thể nhận thứ tự không ổn định ở ranh giới trang.

Cập nhật controller để dùng service:

```java
private final OrderQueryService orderQueryService;

// Inject OrderQueryService trong constructor.

@GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
public PagedModel<OrderModel> listOrders(
        @PageableDefault(
                size = 20,
                sort = "createdAt",
                direction = Sort.Direction.DESC
        ) Pageable pageable,
        PagedResourcesAssembler<Order> pagedAssembler) {

    Page<Order> page = orderQueryService.findOrders(pageable);

    return pagedAssembler.toModel(page, orderModelAssembler);
}
```

Trong dự án lớn, có thể đặt quy tắc sort trong một lớp query riêng và trả lỗi validation thống nhất. Đừng âm thầm bỏ qua sort không hợp lệ nếu client cần biết request đã bị từ chối hoặc thay đổi.

## 9. Phân trang ổn định và giới hạn của offset pagination

`Pageable` thường dùng offset pagination: page 0 lấy một đoạn đầu, page 1 lấy đoạn tiếp theo. Cách này phù hợp cho collection có quy mô vừa và UI cần nhảy đến trang cụ thể.

Tuy nhiên, dữ liệu có thể thay đổi giữa hai request. Ví dụ client đọc trang 0, sau đó một order mới được thêm lên đầu danh sách trước khi client đọc trang 1. Với offset cố định, client có thể thấy bản ghi trùng hoặc bỏ sót một bản ghi.

Để giảm vấn đề:

- Dùng sort xác định và có khóa duy nhất làm tie-breaker.
- Chọn trường sort ổn định, hạn chế thay đổi liên tục.
- Giữ page size hợp lý.
- Với luồng dữ liệu lớn hoặc cập nhật liên tục, cân nhắc cursor/keyset pagination.

`Page<T>` thường cần count query để tính `totalElements` và `totalPages`. Nếu client chỉ cần biết còn dữ liệu tiếp theo hay không, `Slice<T>` có thể tiết kiệm count query. Tuy nhiên, `PagedResourcesAssembler` nhận `Page<T>`; dùng `Slice` cần cách xây collection model và navigation links phù hợp riêng.

Không chuyển sang cursor pagination chỉ bằng cách đổi tên query parameter. Cursor cần định nghĩa token, sort order, cách encode vị trí cuối cùng và semantics của các link tiếp theo.

## 10. Kiểm thử phân trang bằng MockMvc

Kiểm thử cần xác nhận media type, page metadata, embedded items và navigation links. Ví dụ integration test với H2:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderPaginationIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private OrderRepository orderRepository;

    @BeforeEach
    void setUp() {
        orderRepository.deleteAll();

        orderRepository.saveAll(java.util.List.of(
                new Order(
                        UUID.fromString("00000000-0000-0000-0000-000000000001"),
                        "PENDING",
                        new BigDecimal("125000.00"),
                        Instant.parse("2026-01-03T10:00:00Z")
                ),
                new Order(
                        UUID.fromString("00000000-0000-0000-0000-000000000002"),
                        "CONFIRMED",
                        new BigDecimal("89000.00"),
                        Instant.parse("2026-01-02T10:00:00Z")
                ),
                new Order(
                        UUID.fromString("00000000-0000-0000-0000-000000000003"),
                        "SHIPPED",
                        new BigDecimal("45000.00"),
                        Instant.parse("2026-01-01T10:00:00Z")
                )
        ));
    }

    @Test
    void returnsFirstPageWithNextLink() throws Exception {
        mockMvc.perform(get("/orders")
                        .param("page", "0")
                        .param("size", "2")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$.page.size").value(2))
                .andExpect(jsonPath("$.page.number").value(0))
                .andExpect(jsonPath("$.page.totalElements").value(3))
                .andExpect(jsonPath("$.page.totalPages").value(2))
                .andExpect(jsonPath("$._links.self.href").exists())
                .andExpect(jsonPath("$._links.first.href").exists())
                .andExpect(jsonPath("$._links.next.href").exists())
                .andExpect(jsonPath("$._links.last.href").exists())
                .andExpect(jsonPath("$._links.prev").doesNotExist())
                .andExpect(jsonPath("$._embedded").exists());
    }

    @Test
    void returnsLastPageWithPreviousLinkAndNoNextLink() throws Exception {
        mockMvc.perform(get("/orders")
                        .param("page", "1")
                        .param("size", "2")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.page.number").value(1))
                .andExpect(jsonPath("$.page.totalElements").value(3))
                .andExpect(jsonPath("$._links.prev.href").exists())
                .andExpect(jsonPath("$._links.next").doesNotExist());
    }
}
```

Ví dụ giả định entity `Order` có constructor như ở phần chuẩn bị dữ liệu, ứng dụng dùng H2 và mapping đã được đăng ký. Nếu dùng Spring Boot phiên bản khác, có thể cần điều chỉnh import test annotation theo cấu hình test của dự án.

Bổ sung các test quan trọng khác:

| Test | Điều cần xác nhận |
|---|---|
| Không truyền `page` và `size` | Dùng giá trị mặc định đã công bố |
| `size` vượt giới hạn | Bị giới hạn hoặc từ chối theo chính sách đã chọn |
| Sort hợp lệ | Kết quả có thứ tự đúng |
| Sort không hợp lệ | Trả lỗi 400 theo error contract |
| Trang giữa | Có cả `prev` và `next` khi dữ liệu cho phép |
| Trang cuối | Có `prev`, không có `next` |
| Trang rỗng | Metadata nhất quán, không có item |
| Accept không hỗ trợ | Trả 406 |
| HAL response | Có `Content-Type: application/hal+json` và links theo hợp đồng |

Nếu dùng `@WebMvcTest` thay cho `@SpringBootTest`, hãy mock repository/service và xác nhận test context vẫn có `PagedResourcesAssembler`. Integration test với cấu hình ứng dụng thật hữu ích để phát hiện lỗi converter hoặc Spring Data Web configuration.

## 11. Tiêu chí hoàn thành

Dự án được xem là hoàn thành khi các điều kiện sau đều đạt:

- `GET /orders` nhận `page`, `size` và `sort`.
- Endpoint trả `application/hal+json`.
- Mỗi order embedded có link `self`.
- Collection có page metadata: `size`, `totalElements`, `totalPages`, `number`.
- Link `first`, `prev`, `self`, `next`, `last` xuất hiện theo đúng điều kiện.
- Client có thể theo `href` của link `next` để lấy trang tiếp.
- Page size bị giới hạn.
- Sort property được allow-list và có tie-breaker ổn định.
- MockMvc integration tests xác nhận metadata, links và media type.
- OpenAPI hoặc tài liệu API mô tả query parameters và HAL response đúng với runtime.

## 12. Câu hỏi tự đánh giá

1. Vì sao không nên trả toàn bộ collection khi số lượng order lớn?
2. `Page<Order>` khác `PagedModel<OrderModel>` ở trách nhiệm nào?
3. `PagedResourcesAssembler` tự động hỗ trợ những phần nào của response?
4. Vì sao client nên theo link `next` thay vì tự tăng `page`?
5. Tại sao page cần sort có thứ tự xác định và tie-breaker duy nhất?
6. Khi nào `Slice` phù hợp hơn `Page`?
7. Vì sao phải giới hạn page size và allow-list sort properties?
8. `Vary: Accept` có vai trò gì nếu endpoint hỗ trợ nhiều representation?

## Kết luận

Bạn đã xây dựng collection endpoint có phân trang bằng Spring Data và Spring HATEOAS. `Pageable` nhận yêu cầu trang và sort từ client, repository trả `Page`, còn `PagedResourcesAssembler` chuyển dữ liệu thành `PagedModel` với page metadata và navigation links. Client có thể khám phá trang đầu, trang trước, trang hiện tại, trang sau và trang cuối bằng relation trong HAL. Khi giới hạn page size, kiểm soát sort, giữ thứ tự ổn định và kiểm thử bằng MockMvc, hợp đồng phân trang sẽ rõ ràng và an toàn hơn khi API phát triển.

## Tài liệu tham khảo

- [Spring HATEOAS Reference – Paging](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.paging)
- [Spring Data Commons Reference – Web support](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html#core.web)
- [Spring Data API – PagedResourcesAssembler](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/PagedResourcesAssembler.html)
- [Spring HATEOAS API – PagedModel](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/PagedModel.html)
- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288.html)

