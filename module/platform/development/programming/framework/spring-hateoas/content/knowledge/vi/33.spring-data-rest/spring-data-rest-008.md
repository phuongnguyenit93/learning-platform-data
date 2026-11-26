# Custom repository endpoint

Spring Data REST tự động xuất bản các repository thành REST resource: collection resource, item resource và các query method được công bố dưới `search`. Tuy nhiên, có những trường hợp endpoint cần kết hợp nhiều query, áp dụng quy tắc nghiệp vụ, hậu xử lý kết quả hoặc trả một representation riêng. Khi endpoint đó thuộc không gian URI của repository đã xuất bản, Spring Data REST cung cấp `@RepositoryRestController` để viết handler tùy chỉnh mà vẫn dùng được base path, message converter, exception handling và cấu hình CORS của Spring Data REST.

Một custom repository endpoint thường có ba phần: repository hoặc repository fragment thực hiện truy vấn, controller nhận HTTP request và điều phối, Spring HATEOAS model/assembler tạo representation cùng link. Controller trả `EntityModel`, `CollectionModel` hoặc `PagedModel` để client tiếp tục khám phá API qua hypermedia.

## Khi nào cần custom repository endpoint?

Không phải mọi query mới đều cần controller tùy chỉnh. Spring Data REST có thể tự xuất bản query method của repository dưới resource `search`. Ví dụ:

```java
@RepositoryRestResource(path = "orders")
public interface OrderRepository extends JpaRepository<Order, UUID> {

    Page<Order> findByStatus(OrderStatus status, Pageable pageable);
}
```

Query method có thể được xuất bản dưới `/orders/search/findByStatus`. Client có thể khám phá query resource thông qua link `search` của collection.

Custom controller phù hợp hơn khi cần một endpoint có hợp đồng HTTP riêng, chẳng hạn:

- Kết hợp nhiều điều kiện nghiệp vụ mà không muốn công bố cấu trúc query method nội bộ.
- Truy vấn dữ liệu rồi nhóm, tính toán hoặc hậu xử lý trước khi trả response.
- Trả một DTO tổng hợp từ nhiều aggregate hoặc repository.
- Tạo response riêng có pagination metadata, custom links hoặc affordance.
- Duy trì một URI tương thích trong khi implementation truy vấn thay đổi.

Ví dụ, hệ thống bán hàng cần endpoint `/orders/search/overdue` trả các đơn hàng quá hạn, chỉ gồm các trường mà màn hình vận hành cần, kèm link tới tài nguyên đơn hàng gốc. Đây là một custom search endpoint trong URI space của `OrderRepository`.

## Phân biệt query method, repository fragment và custom controller

Ba cơ chế thường được dùng cùng nhau nhưng giải quyết các lớp vấn đề khác nhau:

| Cơ chế | Trách nhiệm | Tạo HTTP endpoint? |
|---|---|---|
| Repository query method | Khai báo truy vấn theo quy ước tên hoặc `@Query` | Có thể được Spring Data REST tự xuất bản dưới `search` |
| Repository fragment | Đóng gói logic truy vấn hoặc thao tác dữ liệu tùy chỉnh | Không tự tạo endpoint HTTP |
| `@RepositoryRestController` | Định nghĩa handler HTTP nằm trong URI space của Spring Data REST | Có |
| `@BasePathAwareController` | Định nghĩa endpoint tùy chỉnh dưới base path nhưng không nhất thiết gắn với một repository resource | Có |

Nếu chỉ cần query đơn giản và response mặc định là đủ, query method thường ít code hơn. Nếu logic truy vấn phức tạp, repository fragment giúp giữ logic ở tầng persistence. Nếu cần một HTTP contract riêng, controller kết nối các thành phần đó và định nghĩa response.

## @RepositoryRestController là gì?

`@RepositoryRestController` đánh dấu một Spring MVC controller được xử lý bởi Spring Data REST. Controller này được phục vụ dưới base path được cấu hình trong `RepositoryRestConfiguration`, giống các endpoint repository khác. Ví dụ, nếu base path là `/api`, mapping `/orders/search/overdue` trở thành `/api/orders/search/overdue`.

Khác với `@RestController` thông thường, `@RepositoryRestController` đưa handler vào hạ tầng request mapping của Spring Data REST. Nhờ đó handler có thể dùng cấu hình message converter, exception handling và CORS tương ứng với repository. Nếu dùng `@Controller` hoặc `@RestController` thông thường, endpoint thuộc phạm vi Spring MVC chung của ứng dụng, nằm ngoài một số tích hợp đặc thù của Spring Data REST.

Ví dụ khai báo base path với Spring Boot:

```yaml
spring:
  data:
    rest:
      base-path: /api
```

Không thêm `/api` vào `@GetMapping` khi dùng `@RepositoryRestController`; base path được ghép tự động. Nếu lặp lại prefix, URI sẽ bị lồng sai, chẳng hạn `/api/api/orders/...`.

## Tạo query method cho custom endpoint

Giả sử `Order` có `dueDate`, `status` và `customerId`. Repository cần trả các đơn hàng có ngày đến hạn trước một mốc nhất định:

```java
import java.time.LocalDate;
import java.util.UUID;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;

@RepositoryRestResource(path = "orders")
public interface OrderRepository extends JpaRepository<Order, UUID> {

    @RestResource(exported = false)
    Page<Order> findByDueDateBeforeAndStatus(
            LocalDate dueDate,
            OrderStatus status,
            Pageable pageable
    );
}
```

`@RestResource(exported = false)` ngăn Spring Data REST xuất bản query method này như một search resource độc lập. Controller vẫn có thể gọi method đó qua bean `OrderRepository`. Cách này hữu ích khi muốn công bố một endpoint có tên và tham số ổn định hơn tên method truy vấn.

Nếu query method cần logic không thể biểu đạt gọn bằng query derivation, có thể chuyển phần truy vấn sang repository fragment:

```java
import java.time.LocalDate;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

public interface OrderSearchRepository {

    Page<Order> findOverdue(
            LocalDate dueDate,
            OrderStatus status,
            Pageable pageable
    );
}
```

Trong phương án fragment, repository chính được khai báo như dưới đây thay cho interface chỉ dùng derived query ở ví dụ trước:

```java
@RepositoryRestResource(path = "orders")
public interface OrderRepository extends
        JpaRepository<Order, UUID>, OrderSearchRepository {
}
```

Implementation fragment có thể dùng `EntityManager`, Criteria API hoặc các repository khác để thực hiện truy vấn. Tên implementation phải tuân theo quy ước repository fragment của phiên bản Spring Data đang sử dụng. Controller không cần biết chi tiết truy vấn; nó chỉ gọi phương thức nghiệp vụ được cung cấp bởi repository.

Khi dùng fragment, thay lời gọi `orders.findByDueDateBeforeAndStatus(...)` trong controller bằng `orders.findOverdue(...)`. Không cần giữ hai phương thức nếu chúng thực hiện cùng một truy vấn.

## Xây custom endpoint bằng @RepositoryRestController

Controller dưới đây xuất bản endpoint `/api/orders/search/overdue`. Nó nhận ngày đến hạn, trạng thái và `Pageable`, gọi repository rồi chuyển kết quả thành `PagedModel`:

```java
import java.time.LocalDate;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.PagedModel;
import org.springframework.data.rest.webmvc.RepositoryRestController;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@RepositoryRestController
public class OrderSearchController {

    private final OrderRepository orders;
    private final OrderModelAssembler orderAssembler;

    public OrderSearchController(
            OrderRepository orders,
            OrderModelAssembler orderAssembler
    ) {
        this.orders = orders;
        this.orderAssembler = orderAssembler;
    }

    @GetMapping(
            path = "/orders/search/overdue",
            produces = MediaTypes.HAL_JSON_VALUE
    )
    public ResponseEntity<PagedModel<EntityModel<OrderResponse>>> overdue(
            @RequestParam
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate before,
            @RequestParam OrderStatus status,
            Pageable pageable,
            PagedResourcesAssembler<Order> pagedAssembler
    ) {
        Page<Order> result = orders.findByDueDateBeforeAndStatus(
                before, status, pageable);

        PagedModel<EntityModel<OrderResponse>> model =
                pagedAssembler.toModel(result, orderAssembler);

        return ResponseEntity.ok(model);
    }
}
```

`@RepositoryRestController` đưa handler vào base path của Spring Data REST. `ResponseEntity` bảo đảm body được ghi qua cơ chế message conversion của Spring MVC. `PagedResourcesAssembler` chuyển `Page<Order>` thành `PagedModel` có metadata và pagination links; `OrderModelAssembler` chuyển từng `Order` thành `EntityModel<OrderResponse>`.

Ví dụ gọi endpoint:

```http
GET /api/orders/search/overdue?before=2026-11-01&status=OPEN&page=0&size=20 HTTP/1.1
Accept: application/hal+json
```

Response có thể chứa collection kết quả, metadata trang và link điều hướng:

```json
{
  "_embedded": {
    "orders": [
      {
        "id": "ORD-2048",
        "status": "OPEN",
        "_links": {
          "self": {
            "href": "/api/orders/ORD-2048"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "/api/orders/search/overdue?before=2026-11-01&status=OPEN&page=0&size=20"
    },
    "next": {
      "href": "/api/orders/search/overdue?before=2026-11-01&status=OPEN&page=1&size=20"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 21,
    "totalPages": 2,
    "number": 0
  }
}
```

Tên relation `orders` phụ thuộc `LinkRelationProvider` và kiểu representation được dùng. Nếu tên relation là một phần ổn định của hợp đồng, cấu hình rõ bằng `@Relation` trên DTO hoặc representation model.

## Dùng EntityModel và CollectionModel cho response tùy chỉnh

Không phải endpoint nào cũng cần phân trang. Nếu kết quả là một tài nguyên duy nhất, trả `EntityModel<T>` hoặc `RepresentationModel<T>` để gắn link. Nếu trả collection không phân trang, dùng `CollectionModel<T>`.

Ví dụ endpoint trả danh sách nhà cung cấp đã chuẩn hóa từ repository:

```java
import java.util.List;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.ResponseEntity;
import org.springframework.data.rest.webmvc.RepositoryRestController;
import org.springframework.web.bind.annotation.GetMapping;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RepositoryRestController
public class SupplierController {

    private final SupplierRepository repository;

    public SupplierController(SupplierRepository repository) {
        this.repository = repository;
    }

    @GetMapping(path = "/suppliers/search/active-names",
            produces = MediaTypes.HAL_JSON_VALUE)
    public ResponseEntity<CollectionModel<String>> activeNames() {
        List<String> names = repository.findActiveNames();

        CollectionModel<String> model = CollectionModel.of(names);
        model.add(linkTo(methodOn(SupplierController.class)
                .activeNames()).withSelfRel());

        return ResponseEntity.ok(model);
    }
}
```

`CollectionModel` cho biết body là collection hypermedia, còn link `self` cho client biết URI của search resource. Nếu từng phần tử cần link riêng, dùng `CollectionModel<EntityModel<T>>` và tạo item link qua assembler.

## Tạo link tới repository resource đã xuất bản

Khi custom endpoint cần link tới resource do Spring Data REST quản lý, nên dùng `RepositoryEntityLinks` thay vì nối chuỗi URL thủ công. Thành phần này biết repository mapping, base path và cấu hình URI của item resource.

```java
import org.springframework.data.rest.webmvc.support.RepositoryEntityLinks;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
public class OrderModelAssembler implements
        RepresentationModelAssembler<Order, EntityModel<OrderResponse>> {

    private final RepositoryEntityLinks entityLinks;

    public OrderModelAssembler(RepositoryEntityLinks entityLinks) {
        this.entityLinks = entityLinks;
    }

    @Override
    public EntityModel<OrderResponse> toModel(Order order) {
        OrderResponse content = new OrderResponse(
                order.getId(),
                order.getStatus().name()
        );

        return EntityModel.of(
                content,
                entityLinks.linkToItemResource(Order.class, order.getId())
                        .withSelfRel()
        );
    }
}
```

`RepositoryEntityLinks` cung cấp các phương thức thường dùng:

| Phương thức | Kết quả |
|---|---|
| `linkToCollectionResource(Order.class)` | Link tới collection resource của repository |
| `linkToItemResource(Order.class, id)` | Link tới một item resource |
| `linkToPagedResource(Order.class, pageable)` | Link tới collection có tham số phân trang |
| `linksToSearchResources(Order.class)` | Các link tới search resources đã xuất bản |
| `linkToSearchResource(Order.class, relation)` | Link tới một query resource theo relation |

Với link tới controller tự viết, `WebMvcLinkBuilder.linkTo(methodOn(...))` vẫn là lựa chọn phù hợp. Với link tới repository resource do Spring Data REST xuất bản, `RepositoryEntityLinks` giúp tránh phụ thuộc vào path và cách định danh item.

## @RepositoryRestController và @BasePathAwareController

Hai annotation này đều đặt controller dưới base path Spring Data REST, nhưng mục đích khác nhau:

| Annotation | Phạm vi phù hợp |
|---|---|
| `@RepositoryRestController` | Handler gắn với URI space của một repository đã xuất bản; có tích hợp CORS của repository và interceptor JPA Open EntityManager in View |
| `@BasePathAwareController` | Endpoint tùy chỉnh dưới base path nhưng không phải thao tác dành riêng cho resource repository, ví dụ view hoặc resource tổng quát |

Spring Data REST chỉ chuyển request tới `@RepositoryRestController` khi mapping của controller nằm trong URI space được quản lý bởi repository. Nếu muốn tạo `/api/reports/monthly` độc lập với `/orders` hay `/customers`, `@BasePathAwareController` thường diễn đạt ý định rõ hơn.

Nếu dùng `@RestController` thông thường, endpoint vẫn có thể hoạt động như một Spring MVC endpoint, nhưng không tự động tham gia các tích hợp riêng của Spring Data REST. Chọn annotation theo phạm vi URI và hành vi cần kế thừa.

## Cấu hình CORS cho custom endpoint

Controller dùng `@RepositoryRestController` có thể kế thừa cấu hình CORS của repository tương ứng. Có thể dùng `@CrossOrigin` ở method nếu endpoint cần giới hạn riêng:

Đây là phần minh họa cấu hình annotation trên handler; phần thân truy vấn có thể dùng lại logic của `OrderSearchController` ở trên.

```java
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.data.domain.Pageable;
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.ResponseEntity;

@RepositoryRestController
public class OrderSearchController {

    @CrossOrigin(
            origins = "https://console.example.com",
            methods = RequestMethod.GET,
            maxAge = 3600
    )
    @GetMapping(path = "/orders/search/overdue",
            produces = MediaTypes.HAL_JSON_VALUE)
    public ResponseEntity<?> overdue(Pageable pageable) {
        // Truy vấn và tạo PagedModel như ví dụ OrderSearchController.
        PagedModel<?> model = createOverdueModel(pageable);
        return ResponseEntity.ok(model);
    }
}
```

Nếu cần cấu hình CORS toàn cục cho Spring Data REST, dùng `RepositoryRestConfigurer` và `configureRepositoryRestConfiguration(...)`. Cấu hình CORS MVC thông thường không tự động áp dụng cho các endpoint do Spring Data REST quản lý, vì chúng đi qua handler mapping riêng.

Không mở rộng `allowedOrigins` hoặc `allowedMethods` rộng hơn nhu cầu thực tế. Nếu bật credentials, origin không thể là wildcard `*`; hãy khai báo origin cụ thể và các header cần thiết.

## Xử lý lỗi và validation

Custom endpoint vẫn cần xác thực request giống controller thông thường. Với query parameter, dùng kiểu dữ liệu rõ ràng và annotation format để Spring chuyển đổi đầu vào:

```java
@GetMapping("/orders/search/overdue")
public ResponseEntity<?> overdue(
        @RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
        LocalDate before,
        @RequestParam OrderStatus status,
        Pageable pageable
) {
    // Kiểm tra quyền và truy vấn.
}
```

Nếu tham số không hợp lệ, Spring có thể trả lỗi `400 Bad Request` do không chuyển đổi được kiểu hoặc do validation. Với dữ liệu nghiệp vụ không hợp lệ, có thể ném exception domain và ánh xạ sang status phù hợp bằng `@ExceptionHandler` hoặc cơ chế exception handling của ứng dụng.

Đừng trả entity persistence trực tiếp nếu response cần giới hạn trường hoặc có link tùy chỉnh. Dùng DTO và assembler để kiểm soát dữ liệu công khai. Đồng thời kiểm tra authorization ở controller/service; việc endpoint nằm trong Spring Data REST không tự động bảo đảm mọi query method đều có cùng chính sách quyền như các CRUD handler.

## Kiểm thử custom repository endpoint

Test tích hợp cần xác nhận endpoint được đăng ký dưới base path, trả đúng media type và công bố các link cần thiết.

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderSearchControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void returnsPagedHalForOverdueOrders() throws Exception {
        mockMvc.perform(get("/api/orders/search/overdue")
                .param("before", "2026-11-01")
                .param("status", "OPEN")
                .param("page", "0")
                .param("size", "20")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$.page.size").value(20))
            .andExpect(jsonPath("$._embedded.orders").isArray());
    }
}
```

Test cần được điều chỉnh theo base path, relation collection và dữ liệu test của ứng dụng. Nếu endpoint dùng `@RepositoryRestController`, gọi URL có base path đã cấu hình, ví dụ `/api`. Nếu controller không được đăng ký đúng URI space, test sẽ phát hiện lỗi `404` hoặc handler khác xử lý request.

Các trường hợp nên có thêm:

- Tham số ngày sai định dạng trả `400 Bad Request`.
- Trạng thái không hợp lệ được xử lý theo hợp đồng lỗi đã chọn.
- Trang tiếp theo giữ nguyên filter và sort.
- Collection rỗng vẫn có `self` link và metadata pagination phù hợp.
- Người dùng không có quyền không thể truy vấn dữ liệu bị giới hạn.
- Link item trỏ tới URI repository resource hợp lệ.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng `@RestController` cho endpoint cần tích hợp Spring Data REST | Không dùng cùng handler mapping, message converter hoặc exception handling của Spring Data REST | Dùng `@RepositoryRestController` khi endpoint thuộc URI space repository |
| Lặp base path trong `@GetMapping` | URL bị thêm prefix hai lần | Chỉ khai báo path tương đối dưới base path |
| Dùng custom controller cho query đơn giản | Tăng code và trách nhiệm bảo trì | Cân nhắc query method tự xuất bản dưới `search` |
| Cho rằng repository fragment tự tạo HTTP endpoint | Client không tìm thấy URI | Kết hợp fragment với query method được export hoặc controller |
| Nối chuỗi URI item thủ công | Link hỏng khi đổi base path hoặc repository mapping | Dùng `RepositoryEntityLinks` |
| Trả entity trực tiếp | Lộ trường nội bộ hoặc phụ thuộc persistence model | Dùng DTO, `EntityModel` và assembler |
| Quên bọc collection bằng model HATEOAS | Response thiếu cấu trúc collection/link phù hợp | Dùng `CollectionModel` hoặc `PagedModel` |
| Trùng path với resource/search handler khác | Handler mapping mơ hồ hoặc endpoint bị chiếm | Kiểm tra URI space và chọn path riêng trong repository namespace |
| Cho rằng CORS MVC áp dụng tự động | Browser request bị chặn | Cấu hình CORS qua Spring Data REST khi endpoint thuộc SDR |
| Không kiểm tra quyền truy cập | Custom query có thể trả dữ liệu vượt quyền | Kiểm tra authorization tại service/controller và truy vấn |

## Quy trình triển khai

1. Xác định endpoint có thuộc URI space của một repository đã xuất bản hay không.
2. Nếu chỉ cần query đơn giản, cân nhắc query method và `@RestResource` trước.
3. Nếu cần HTTP contract tùy chỉnh, dùng `@RepositoryRestController`; nếu endpoint chỉ cần nằm dưới base path nhưng không gắn với repository, cân nhắc `@BasePathAwareController`.
4. Đặt mapping tương đối với base path và repository path, tránh lặp prefix.
5. Đưa logic truy vấn vào repository method hoặc repository fragment.
6. Dùng DTO/assembler để tạo `EntityModel`, `CollectionModel` hoặc `PagedModel`.
7. Dùng `RepositoryEntityLinks` cho link tới repository resource và `WebMvcLinkBuilder` cho controller tự viết.
8. Kiểm tra CORS, validation, authorization và exception mapping.
9. Viết MockMvc test cho base path, media type, link, pagination, lỗi đầu vào và quyền truy cập.

## Kết luận

Custom repository endpoint mở rộng Spring Data REST khi query method tự động không đủ để diễn đạt hợp đồng HTTP hoặc xử lý nghiệp vụ. `@RepositoryRestController` đưa handler vào URI space và hạ tầng của repository đã xuất bản; repository query method hoặc fragment thực hiện truy vấn; Spring HATEOAS assembler tạo representation cùng link. `RepositoryEntityLinks` giúp liên kết tới resource mà Spring Data REST xuất bản mà không hard-code URL. Khi chọn đúng loại controller, giữ base path nhất quán, kiểm soát dữ liệu trả về và kiểm thử endpoint qua MockMvc, custom endpoint có thể mở rộng API mà vẫn giữ trải nghiệm hypermedia đồng nhất.

## Tài liệu tham khảo

- [Spring Data REST – Overriding Response Handlers](https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr-response-handlers.html): `@RepositoryRestController`, base path, URI space và `@BasePathAwareController`.
- [Spring Data REST – Integration](https://docs.spring.io/spring-data/rest/reference/integration.html): sử dụng `RepositoryEntityLinks` để tạo link tới collection, item, page và search resource.
- [Spring Data REST – Configuring the REST URL Path](https://docs.spring.io/spring-data/rest/reference/customizing/configuring-the-rest-url-path.html): `@RepositoryRestResource`, `@RestResource` và query method exposure.
- [Spring Data REST – CORS Configuration](https://docs.spring.io/spring-data/rest/reference/customizing/configuring-cors.html): cấu hình CORS cho repository và custom REST controller.
- [RepositoryRestController API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/RepositoryRestController.html): annotation và các thuộc tính path/value.
