# Assembler trong Spring MVC với Spring HATEOAS

Trong ứng dụng Spring MVC, controller thường lấy dữ liệu từ service rồi trả về HTTP response. Khi response cần hypermedia, controller còn phải chuyển entity thành representation model, thêm self link và các liên kết nghiệp vụ. Nếu lặp phần chuyển đổi này trong nhiều endpoint, cấu trúc response dễ không đồng nhất.

**Assembler** giải quyết phần việc đó bằng cách tập trung chuyển domain object thành representation model. Spring HATEOAS cung cấp `RepresentationModelAssembler`, `RepresentationModelAssemblerSupport` và các assembler chuyên biệt cho collection hoặc page. Controller chỉ cần gọi assembler rồi trả model; Spring MVC và message converter sẽ tuần tự hóa model theo media type được thương lượng.

## 1. Assembler nằm ở đâu trong luồng Spring MVC?

Một luồng xử lý phổ biến:

~~~text
HTTP request
    |
    v
Spring MVC Controller
    |
    v
Application Service
    |
    v
Repository / Domain
    |
    v
Entity hoặc Page<Entity>
    |
    v
RepresentationModelAssembler
    |
    v
EntityModel / CollectionModel / PagedModel
    |
    v
Spring HATEOAS message converter
    |
    v
HTTP response (ví dụ application/hal+json)
~~~

Assembler nhận dữ liệu domain và tạo representation mà API công bố. Nó thường thực hiện các việc:

- Chọn những field được phép xuất hiện trong response.
- Chuyển entity thành DTO hoặc model riêng.
- Tạo link `self` cho tài nguyên.
- Thêm link tới tài nguyên liên quan hoặc hành động có thể thực hiện.
- Chuyển nhiều entity thành `CollectionModel`.
- Phối hợp với `PagedResourcesAssembler` khi kết quả là `Page`.

Assembler không nên truy vấn database hoặc quyết định quy tắc nghiệp vụ. Các thao tác đó thuộc service/repository. Tách rõ trách nhiệm giúp có thể dùng cùng một assembler từ nhiều controller hoặc nhiều endpoint mà không sao chép logic chuyển đổi.

## 2. Các kiểu representation model thường gặp

Spring HATEOAS cung cấp các kiểu model chính:

| Kiểu | Mục đích |
|---|---|
| `EntityModel<T>` | Bao một nội dung đơn và các link |
| `CollectionModel<T>` | Bao một collection các model và link cấp collection |
| `PagedModel<T>` | Bao collection có metadata phân trang và link điều hướng |
| `RepresentationModel<T>` | Lớp cơ sở cho model tùy chỉnh có links |

Ví dụ một đơn hàng có thể được biểu diễn bằng `EntityModel<OrderDto>`:

~~~json
{
  "id": 42,
  "status": "PAID",
  "total": 1250000,
  "_links": {
    "self": {
      "href": "/orders/42"
    },
    "customer": {
      "href": "/customers/7"
    }
  }
}
~~~

Nội dung và link cùng nằm trong một representation. Client có thể đọc trạng thái đơn hàng và khám phá link tới đơn hàng hoặc khách hàng mà không cần tự ghép URL.

## 3. RepresentationModelAssembler là gì?

`RepresentationModelAssembler<T, D>` là interface chuyển một đối tượng domain `T` thành một representation model `D`, trong đó `D` phải kế thừa `RepresentationModel<?>`.

Interface có hai phương thức quan trọng:

- `toModel(T entity)`: chuyển một entity thành một representation.
- `toCollectionModel(Iterable<? extends T> entities)`: phương thức mặc định chuyển collection entity thành `CollectionModel` chứa các representation.

Ví dụ kiểu tổng quát:

~~~text
D toModel(T entity)
CollectionModel<D> toCollectionModel(Iterable<? extends T> entities)
~~~

`toCollectionModel` là default method trong interface; đoạn trên chỉ tóm tắt chữ ký để làm rõ hai thao tác assembler cung cấp.

Trong ứng dụng thực tế, không cần tự định nghĩa lại interface. Hãy triển khai nó cho domain type và representation mà API muốn trả về.

## 4. Tạo DTO dành cho response

Không nên mặc định serialize trực tiếp JPA entity thành response. Entity có thể chứa quan hệ lazy, field nội bộ, thông tin nhạy cảm hoặc cấu trúc persistence không nên trở thành contract HTTP.

Tạo DTO riêng:

~~~java
import java.math.BigDecimal;
import java.time.Instant;

public record OrderDto(
    Long id,
    String status,
    BigDecimal total,
    Instant createdAt
) {}
~~~

DTO chỉ chứa dữ liệu mà client cần. Khi domain entity thay đổi vì lý do persistence hoặc nghiệp vụ, API representation có thể giữ nguyên nếu DTO không cần đổi.

Assembler chịu trách nhiệm tạo DTO từ entity và thêm các link phù hợp.

## 5. Tự triển khai RepresentationModelAssembler

Ví dụ assembler cho đơn hàng:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
public class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderDto>> {

    @Override
    public EntityModel<OrderDto> toModel(Order order) {
        OrderDto dto = new OrderDto(
            order.getId(),
            order.getStatus().name(),
            order.getTotal(),
            order.getCreatedAt()
        );

        return EntityModel.of(
            dto,
            linkTo(methodOn(OrderController.class)
                .one(order.getId())).withSelfRel(),
            linkTo(methodOn(CustomerController.class)
                .one(order.getCustomer().getId())).withRel("customer")
        );
    }
}
~~~

Các thành phần quan trọng:

- `Order` là domain type đầu vào.
- `EntityModel<OrderDto>` là kiểu representation đầu ra.
- `toModel` thực hiện ánh xạ dữ liệu và thêm link.
- `methodOn` mô tả lời gọi controller để Spring HATEOAS suy ra URI theo mapping.
- `withSelfRel()` gắn relation chuẩn `self`.
- `withRel("customer")` gắn relation mô tả liên kết tới khách hàng.

Nếu quan hệ customer có thể null, assembler cần kiểm tra trước khi tạo link. Không tạo link dẫn tới một tài nguyên không tồn tại.

Ví dụ:

~~~java
EntityModel<OrderDto> model = EntityModel.of(
    dto,
    linkTo(methodOn(OrderController.class)
        .one(order.getId())).withSelfRel()
);

if (order.getCustomer() != null) {
    model.add(
        linkTo(methodOn(CustomerController.class)
            .one(order.getCustomer().getId())).withRel("customer")
    );
}

return model;
~~~

Assembler là nơi thích hợp để thể hiện liên kết phụ thuộc vào dữ liệu entity. Tuy nhiên, link chỉ nên được thêm khi quan hệ hoặc hành động thực sự khả dụng với representation đó.

## 6. Bổ sung link cấp collection

Phương thức mặc định `toCollectionModel` chuyển từng entity thành model và đóng gói chúng. Nếu collection cần có link riêng như `self` hoặc `search`, có thể override phương thức này.

~~~java
@Override
public CollectionModel<EntityModel<OrderDto>> toCollectionModel(
        Iterable<? extends Order> orders) {

    CollectionModel<EntityModel<OrderDto>> collection =
        RepresentationModelAssembler.super.toCollectionModel(orders);

    collection.add(
        linkTo(methodOn(OrderController.class).all()).withSelfRel()
    );

    return collection;
}
~~~

Ở đây:

- Mỗi phần tử vẫn được chuyển qua `toModel`.
- `CollectionModel` chứa các `EntityModel<OrderDto>`.
- Link `self` được thêm vào cấp collection, không phải từng đơn hàng.

Nếu API công bố link tìm kiếm, có thể thêm relation `search` cùng URI template vào collection model. Không nên thêm cùng một link collection vào mọi entity nếu link đó thuộc về collection.

## 7. Dùng assembler trong controller cho một tài nguyên

Assembler thường được đăng ký thành Spring bean bằng `@Component` và được inject qua constructor.

~~~java
@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler assembler;

    OrderController(
            OrderService orderService,
            OrderModelAssembler assembler) {
        this.orderService = orderService;
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    EntityModel<OrderDto> one(@PathVariable Long id) {
        Order order = orderService.getById(id);
        return assembler.toModel(order);
    }
}
~~~

Controller tập trung vào HTTP boundary:

1. Nhận path variable.
2. Gọi service lấy entity.
3. Gọi assembler tạo representation.
4. Trả representation cho Spring MVC.

Controller không cần biết cách map từng field hoặc cách tạo self link. Nếu API có nhiều endpoint cùng trả `OrderDto`, chúng có thể dùng chung `OrderModelAssembler`.

## 8. Dùng assembler cho collection endpoint

Với collection không phân trang, có thể gọi `toCollectionModel`:

~~~java
@GetMapping
CollectionModel<EntityModel<OrderDto>> all() {
    List<Order> orders = orderService.findAll();
    return assembler.toCollectionModel(orders);
}
~~~

Response HAL có thể có dạng:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": 42,
        "status": "PAID",
        "_links": {
          "self": {
            "href": "/orders/42"
          }
        }
      },
      {
        "id": 43,
        "status": "PENDING",
        "_links": {
          "self": {
            "href": "/orders/43"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "/orders"
    }
  }
}
~~~

Tên collection relation trong `_embedded` được quyết định bởi quy tắc relation của representation type, chẳng hạn cấu hình `@Relation` hoặc relation provider. Không nên mặc định mọi collection đều tự serialize với đúng tên mà client mong đợi; hãy kiểm thử payload thực tế.

## 9. Dùng PagedResourcesAssembler cho Page

`Page<T>` có metadata như số trang, kích thước, tổng phần tử và tổng số trang. `PagedResourcesAssembler` của Spring Data chuyển `Page<T>` thành `PagedModel` và tạo các link điều hướng.

Assembler cho từng entity vẫn được dùng để chuyển từng phần tử trong page.

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.PagedModel;

@GetMapping
PagedModel<EntityModel<OrderDto>> all(
        Pageable pageable,
        PagedResourcesAssembler<Order> pagedAssembler) {

    Page<Order> page = orderService.findAll(pageable);

    return pagedAssembler.toModel(page, assembler);
}
~~~

`PagedResourcesAssembler` là thành phần khác với `OrderModelAssembler`:

| Thành phần | Trách nhiệm |
|---|---|
| `OrderModelAssembler` | Chuyển một `Order` thành `EntityModel<OrderDto>` |
| `PagedResourcesAssembler<Order>` | Chuyển `Page<Order>` thành `PagedModel` và tạo page links |

Response có thể chứa `_embedded`, `_links` và `page` metadata:

~~~json
{
  "_embedded": {
    "orders": [
      {
        "id": 42,
        "status": "PAID",
        "_links": {
          "self": {
            "href": "/orders/42"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "/orders?page=0&size=20"
    },
    "next": {
      "href": "/orders?page=1&size=20"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 57,
    "totalPages": 3,
    "number": 0
  }
}
~~~

Khi dùng `PagedResourcesAssembler`, không tự tạo `next` bằng cách ghép chuỗi query. Hãy để assembler dựa trên `Pageable` và request hiện tại tạo link, nhờ đó page size, sort và các query parameter có thể được giữ lại.

## 10. RepresentationModelAssemblerSupport

Nếu API có model class riêng kế thừa `RepresentationModel`, `RepresentationModelAssemblerSupport` là lớp cơ sở giúp giảm boilerplate. Nó tự tạo model và thêm self link dựa trên controller class, resource type và identifier.

Ví dụ model tùy chỉnh:

~~~java
import org.springframework.hateoas.RepresentationModel;

public class OrderRepresentation extends
        RepresentationModel<OrderRepresentation> {

    private Long id;
    private String status;

    public OrderRepresentation(Long id, String status) {
        this.id = id;
        this.status = status;
    }

    public Long getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }
}
~~~

Assembler:

~~~java
import org.springframework.hateoas.server.mvc.RepresentationModelAssemblerSupport;

public class OrderRepresentationAssembler
        extends RepresentationModelAssemblerSupport<
            Order, OrderRepresentation> {

    public OrderRepresentationAssembler() {
        super(OrderController.class, OrderRepresentation.class);
    }

    @Override
    protected OrderRepresentation instantiateModel(Order order) {
        return new OrderRepresentation(
            order.getId(),
            order.getStatus().name()
        );
    }

    @Override
    public OrderRepresentation toModel(Order order) {
        return createModelWithId(order.getId(), order);
    }
}
~~~

`createModelWithId` tạo model và thêm link `self` theo mapping của controller đã truyền vào constructor. `instantiateModel` được override để khởi tạo model bằng constructor riêng, tránh yêu cầu lớp representation phải có no-argument constructor.

Lớp hỗ trợ này phù hợp khi cần model class riêng và muốn Spring HATEOAS hỗ trợ tạo self link. Với DTO đơn giản bọc bằng `EntityModel`, triển khai `RepresentationModelAssembler` trực tiếp thường dễ đọc hơn.

## 11. SimpleRepresentationModelAssembler

`SimpleRepresentationModelAssembler<T>` là lựa chọn gọn khi muốn dùng chính domain type `T` làm nội dung của `EntityModel<T>`, không cần tạo DTO riêng.

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.server.SimpleRepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class SimpleOrderAssembler
        implements SimpleRepresentationModelAssembler<Order> {

    @Override
    public void addLinks(EntityModel<Order> model) {
        Order order = model.getContent();

        model.add(
            linkTo(methodOn(OrderController.class)
                .one(order.getId())).withSelfRel()
        );
    }

    @Override
    public void addLinks(CollectionModel<EntityModel<Order>> collection) {
        collection.add(
            linkTo(methodOn(OrderController.class).all()).withSelfRel()
        );
    }
}
~~~

Interface cung cấp cách triển khai `toModel` và `toCollectionModel` mặc định, đồng thời yêu cầu định nghĩa link cho từng entity model và collection model.

Chỉ dùng cách này khi domain object thực sự phù hợp làm representation công khai. Nếu entity có field nội bộ, quan hệ persistence hoặc dữ liệu cần ẩn, hãy dùng `RepresentationModelAssembler<Order, EntityModel<OrderDto>>` để kiểm soát response.

## 12. Chọn loại assembler nào?

| Nhu cầu | Lựa chọn |
|---|---|
| Map entity sang DTO và thêm link tùy chỉnh | `RepresentationModelAssembler<T, EntityModel<Dto>>` |
| Dùng entity trực tiếp trong `EntityModel<T>` | `SimpleRepresentationModelAssembler<T>` |
| Dùng model class riêng và cần self link tự động | `RepresentationModelAssemblerSupport<T, D>` |
| Chuyển `Iterable<T>` thành collection representation | `toCollectionModel` |
| Chuyển `Page<T>` thành page representation | `PagedResourcesAssembler<T>` |

Đừng chọn lớp hỗ trợ phức tạp chỉ vì nó có nhiều method. Hãy chọn abstraction ít nhất đáp ứng được cấu trúc representation của API.

## 13. Assembler và RepresentationModelProcessor khác nhau

Assembler xây representation từ một domain object. `RepresentationModelProcessor` xử lý một representation model sau khi controller/assembler đã tạo ra nó.

Ví dụ một link chính sách có thể được thêm vào mọi `EntityModel<OrderDto>`:

~~~java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.RepresentationModelProcessor;
import org.springframework.stereotype.Component;

@Component
class OrderModelProcessor
        implements RepresentationModelProcessor<EntityModel<OrderDto>> {

    @Override
    public EntityModel<OrderDto> process(EntityModel<OrderDto> model) {
        model.add(
            Link.of("/policies/orders")
                .withRel("order-policy")
        );

        return model;
    }
}
~~~

Dùng processor khi link hoặc quy tắc bổ sung áp dụng chung cho một loại representation. Dùng assembler cho mapping entity-specific, self link và quan hệ phụ thuộc vào dữ liệu của entity.

Tránh đưa mọi logic link vào processor. Một processor quá rộng có thể làm response khó dự đoán vì link được thêm ở một nơi khác controller và assembler.

## 14. Cấu hình và tích hợp với Spring MVC

Trong ứng dụng Spring Boot dùng starter Spring HATEOAS phù hợp, auto-configuration đăng ký các thành phần cần thiết để serialize `EntityModel`, `CollectionModel` và `PagedModel` theo media type được hỗ trợ.

Thông thường chỉ cần:

- Đăng ký assembler là bean bằng `@Component` hoặc `@Bean`.
- Inject assembler vào controller qua constructor.
- Trả trực tiếp `RepresentationModel` hoặc `ResponseEntity` chứa model.
- Gửi request với `Accept: application/hal+json` khi muốn nhận HAL JSON.

Ví dụ:

~~~http
GET /orders/42 HTTP/1.1
Accept: application/hal+json
~~~

Nếu không dùng auto-configuration của Spring Boot, có thể bật hypermedia support bằng `@EnableHypermediaSupport`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.config.HypermediaType;

@Configuration
@EnableHypermediaSupport(type = HypermediaType.HAL)
class HypermediaConfiguration {
}
~~~

Không đăng ký lại cấu hình này một cách máy móc trong ứng dụng Spring Boot đã auto-configure hypermedia. Khi tự cấu hình, cần kiểm tra message converter và Jackson module để chắc chắn representation được serialize đúng media type.

## 15. Trả RepresentationModel bằng ResponseEntity

Controller có thể trả trực tiếp model hoặc bọc model trong `ResponseEntity` khi cần kiểm soát status/header.

Ví dụ tạo đơn hàng trả HTTP 201:

~~~java
import java.net.URI;

import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;

@PostMapping
ResponseEntity<EntityModel<OrderDto>> create(
        @RequestBody CreateOrderRequest request) {

    Order order = orderService.create(request);
    EntityModel<OrderDto> model = assembler.toModel(order);

    URI location = model
        .getRequiredLink(IanaLinkRelations.SELF)
        .toUri();

    return ResponseEntity.created(location).body(model);
}
~~~

Link `self` trong representation đồng thời được dùng làm `Location` header. Cách này giữ URI tài nguyên mới nhất quán giữa HTTP metadata và hypermedia body.

Nếu controller chỉ trả một representation với status mặc định 200, có thể trả trực tiếp `EntityModel` mà không cần tạo `ResponseEntity` dư thừa.

## 16. Kiểm thử assembler ở hai cấp

Có thể kiểm thử assembler trực tiếp để xác nhận mapping và link:

~~~java
import java.math.BigDecimal;

import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.MediaTypes;
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void mapsOrderAndAddsLinks() {
    Order order = new Order(
        42L,
        OrderStatus.PAID,
        new BigDecimal("1250000")
    );

    EntityModel<OrderDto> model = assembler.toModel(order);

    assertThat(model.getContent().id()).isEqualTo(42L);
    assertThat(model.getContent().status()).isEqualTo("PAID");
    assertThat(model.hasLink(IanaLinkRelations.SELF)).isTrue();
}
~~~

Kiểm thử tích hợp Spring MVC bằng MockMvc để xác nhận response thực tế có media type và cấu trúc hypermedia đúng:

~~~java
mockMvc.perform(
        get("/orders/42")
            .accept(MediaTypes.HAL_JSON)
    )
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$.id").value(42))
    .andExpect(jsonPath("$._links.self.href").exists());
~~~

Với collection hoặc page, kiểm tra thêm:

- Collection relation và số phần tử trong `_embedded`.
- Link cấp collection `self` hoặc `search`.
- Metadata `page.size`, `page.number`, `page.totalElements`.
- Link `next` và `prev` khi có trang tương ứng.
- Sort/filter hiện tại được giữ trong các page links.

Kiểm thử trực tiếp assembler giúp tìm lỗi mapping nhanh. MockMvc xác nhận cả quá trình controller, assembler, message converter và content negotiation.

## 17. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Mapping entity trực tiếp ở nhiều controller | Representation không nhất quán | Tập trung mapping trong assembler |
| Trả JPA entity mà không kiểm soát field | Lộ field nội bộ hoặc gặp lazy-loading | Dùng DTO và assembler |
| Assembler gọi repository | Trộn mapping với truy vấn | Lấy dữ liệu qua service trước khi assemble |
| Quên self link | Client không có link chuẩn tới tài nguyên hiện tại | Thêm link bằng `methodOn` hoặc `createModelWithId` |
| Thêm link collection vào từng item | Sai cấp quan hệ hypermedia | Thêm link vào `CollectionModel` |
| Dùng `PagedResourcesAssembler` như item assembler | Nhầm trách nhiệm chuyển page và chuyển entity | Dùng item assembler làm đối số cho page assembler |
| Dùng `SimpleRepresentationModelAssembler` với entity nhạy cảm | Có thể serialize field không mong muốn | Dùng DTO riêng |
| Dùng `RepresentationModelAssemblerSupport` cho mapping quá đơn giản | Tăng boilerplate | Triển khai interface trực tiếp |
| Không kiểm thử media type | Model có thể không serialize thành HAL như mong đợi | Kiểm thử `Accept` và `Content-Type` bằng MockMvc |
| Link được tạo từ route hard-code | Mapping controller đổi nhưng link không đổi | Dùng `WebMvcLinkBuilder` và `methodOn` |

## 18. Quy trình tích hợp assembler vào Spring MVC

Khi xây dựng endpoint có hypermedia, hãy thực hiện theo trình tự:

1. Xác định domain type và dữ liệu API được phép công bố.
2. Tạo DTO hoặc representation model phù hợp.
3. Tạo assembler triển khai `RepresentationModelAssembler`.
4. Ánh xạ dữ liệu trong `toModel` và tạo self/related links.
5. Override `toCollectionModel` nếu collection cần link cấp collection.
6. Đăng ký assembler thành Spring bean và inject vào controller.
7. Dùng `PagedResourcesAssembler` nếu service trả `Page`.
8. Trả `EntityModel`, `CollectionModel`, `PagedModel` hoặc `ResponseEntity` chứa model.
9. Kiểm thử assembler riêng và response HTTP bằng MockMvc.
10. Kiểm tra link, embedded relation, page metadata và media type.

Assembler giúp Spring MVC controller tập trung vào điều phối request trong khi Spring HATEOAS representation được tạo nhất quán. Khi mapping entity, DTO và link được gom vào một thành phần chuyên trách, API dễ kiểm thử, dễ tái sử dụng và có thể thay đổi cách biểu diễn mà không làm controller phình to.

## Tài liệu tham khảo

- [Spring HATEOAS Reference — Representation model assembler](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.mvc.representation-model-assembler)
- [RepresentationModelAssembler API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/RepresentationModelAssembler.html)
- [SimpleRepresentationModelAssembler API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/SimpleRepresentationModelAssembler.html)
- [RepresentationModelAssemblerSupport API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/mvc/RepresentationModelAssemblerSupport.html)
- [PagedResourcesAssembler API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/PagedResourcesAssembler.html)
