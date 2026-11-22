# Phân biệt các ví dụ cũ dùng Resource, PagedResources với API RepresentationModel

## Mục tiêu

Các ví dụ Spring Data REST và Spring HATEOAS cũ thường dùng những kiểu như `Resource`, `Resources`, `PagedResources` và `ResourceSupport`. Từ Spring HATEOAS 1.0, API được thiết kế lại với nhóm kiểu `RepresentationModel`, `EntityModel`, `CollectionModel` và `PagedModel`.

Khi đọc hoặc nâng cấp code cũ, cần phân biệt ba việc:

- **Đổi tên API Java:** thay wrapper, assembler và link builder cũ bằng API mới.
- **Giữ semantics của representation:** item, collection và page vẫn có thể được biểu diễn bằng HAL với `_links`, `_embedded` và metadata phân trang.
- **Giữ contract HTTP:** media type, relation name, URI và status code phải tiếp tục phù hợp với client.

Đổi kiểu Java không có nghĩa phải thay đổi toàn bộ JSON contract. Tuy vậy, cần kiểm thử response thực tế sau khi nâng cấp vì cấu hình serializer, projection, assembler và phiên bản thư viện có thể ảnh hưởng representation.

## 1. Vì sao Spring HATEOAS đổi API?

Các kiểu cũ dùng tên `Resource` và `Resources` để mô tả một resource hoặc một collection resource. Chúng thường được dùng cùng `ResourceSupport`, `ResourceAssembler` và `ControllerLinkBuilder`.

API mới dùng một hệ thống tên rõ hơn:

- `RepresentationModel`: lớp cơ sở cho representation có hypermedia links.
- `EntityModel<T>`: representation của một đối tượng.
- `CollectionModel<T>`: representation của một collection.
- `PagedModel<T>`: representation của collection có metadata phân trang.

Nhóm tên mới giúp phân biệt representation đơn, collection và page ngay trong chữ ký Java, đồng thời dùng chung abstraction `RepresentationModel` cho link và processor.

## 2. Bảng ánh xạ API cũ sang API mới

| API cũ | API mới | Ý nghĩa |
|---|---|---|
| `Resource<T>` | `EntityModel<T>` | Một entity cùng hypermedia links |
| `Resources<T>` | `CollectionModel<T>` | Một collection representation |
| `PagedResources<T>` | `PagedModel<T>` | Collection có metadata phân trang |
| `ResourceSupport` | `RepresentationModel<T>` | Lớp cơ sở cho representation có links |
| `ResourceAssembler<T, D>` | `RepresentationModelAssembler<T, D>` | Chuyển domain object thành representation |
| `ResourceAssemblerSupport<T, D>` | `RepresentationModelAssemblerSupport<T, D>` | Base class hỗ trợ viết assembler |
| `ResourceProcessor<T>` | `RepresentationModelProcessor<T>` | Chỉnh sửa representation sau khi được tạo |
| `ControllerLinkBuilder` | `WebMvcLinkBuilder` | Tạo link từ Spring MVC controller method |
| `Resource.getContent()` | `EntityModel.getContent()` | Lấy entity được bọc trong model |
| `ResourceAssembler.toResource(...)` | `RepresentationModelAssembler.toModel(...)` | Tạo representation của một entity |
| `PagedResources.PageMetadata` | `PagedModel.PageMetadata` | Metadata trang |

Tên package cũng thay đổi ở một số API. Khi sửa import, cần dùng package của phiên bản Spring HATEOAS đang được Spring Boot quản lý, không chỉ thay tên class theo bảng.

## 3. Resource<T> chuyển thành EntityModel<T>

Code cũ thường tạo một resource wrapper:

    Resource<Order> resource =
        new Resource<>(order);

    resource.add(linkTo(
        methodOn(OrderController.class).getOrder(order.getId())
    ).withSelfRel());

Với API mới:

    EntityModel<Order> model =
        EntityModel.of(order);

    model.add(linkTo(
        methodOn(OrderController.class).getOrder(order.getId())
    ).withSelfRel());

Các import chính:

    import org.springframework.hateoas.EntityModel;
    import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
    import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

`EntityModel.of(order)` tạo representation wrapper cho một entity. Có thể thêm một hoặc nhiều link:

    model.add(
        linkTo(methodOn(OrderController.class)
            .getOrder(order.getId()))
            .withSelfRel()
    );

    model.add(
        linkTo(methodOn(OrderController.class)
            .getCustomer(order.getId()))
            .withRel("customer")
    );

Link relation `self` thường xác định URI của chính resource. Relation `customer` là một relation do API định nghĩa và phải nhất quán với hypermedia contract của client.

Không cần tạo `EntityModel` nếu controller chỉ trả DTO không dùng hypermedia. Chọn representation theo contract mà endpoint cần cung cấp.

## 4. Resources<T> chuyển thành CollectionModel<T>

Code cũ có thể bọc một danh sách:

    Resources<Order> resources =
        new Resources<>(orders);

    resources.add(
        linkTo(methodOn(OrderController.class).getOrders())
            .withSelfRel()
    );

Code mới:

    CollectionModel<Order> model =
        CollectionModel.of(orders);

    model.add(
        linkTo(methodOn(OrderController.class).getOrders())
            .withSelfRel()
    );

Nếu mỗi item cũng cần links, dùng collection của `EntityModel<Order>`:

    List<EntityModel<Order>> items = orders.stream()
        .map(order -> EntityModel.of(order))
        .toList();

    CollectionModel<EntityModel<Order>> model =
        CollectionModel.of(items);

Có thể thêm link cho collection:

    model.add(
        linkTo(methodOn(OrderController.class).getOrders())
            .withSelfRel()
    );

`CollectionModel<T>` biểu diễn collection và links cấp collection. Mỗi `EntityModel<T>` bên trong có thể có links riêng. Không nhầm collection link với item self link.

## 5. PagedResources<T> chuyển thành PagedModel<T>

Với dữ liệu phân trang, API mới dùng `PagedModel<T>`. Kiểu này mang cả content, links điều hướng và metadata của page.

Ví dụ tạo thủ công:

    PagedModel.PageMetadata metadata =
        new PagedModel.PageMetadata(
            page.getSize(),
            page.getNumber(),
            page.getTotalElements(),
            page.getTotalPages()
        );

    PagedModel<EntityModel<Order>> model =
        PagedModel.of(orderModels, metadata);

Thứ tự tham số của `PageMetadata` là size, number, totalElements và totalPages. Dùng metadata từ đối tượng `Page` để tránh tự tính sai số trang.

Trong ứng dụng Spring MVC/Spring Data, thường nên dùng `PagedResourcesAssembler` để chuyển `Page<T>` thành `PagedModel` và tạo các link phân trang:

    @RestController
    @RequestMapping("/orders")
    class OrderController {

        private final OrderRepository orders;
        private final OrderModelAssembler assembler;

        OrderController(
                OrderRepository orders,
                OrderModelAssembler assembler) {
            this.orders = orders;
            this.assembler = assembler;
        }

        @GetMapping
        PagedModel<EntityModel<Order>> getOrders(
                Pageable pageable,
                PagedResourcesAssembler<Order> pagedAssembler) {

            Page<Order> page = orders.findAll(pageable);

            return pagedAssembler.toModel(page, assembler);
        }
    }

`PagedResourcesAssembler` vẫn có tên chứa từ Resources trong một số phiên bản Spring Data. Đây là tên helper/adapter; kiểu representation mà nó tạo theo API mới là `PagedModel`.

Không thay tên helper này một cách máy móc nếu phiên bản Spring Data hiện tại vẫn cung cấp nó. Hãy xem chữ ký API của dependency thực tế.

## 6. HAL JSON và contract HTTP

Các kiểu Java mới vẫn có thể được serialize thành HAL. Ví dụ một `EntityModel<Order>` có thể tạo response dạng:

    {
      "id": 501,
      "status": "PAID",
      "_links": {
        "self": {
          "href": "http://localhost:8080/orders/501"
        },
        "customer": {
          "href": "http://localhost:8080/orders/501/customer"
        }
      }
    }

Một `CollectionModel<EntityModel<Order>>` có thể tạo collection representation:

    {
      "_embedded": {
        "orders": [
          {
            "id": 501,
            "status": "PAID",
            "_links": {
              "self": {
                "href": "http://localhost:8080/orders/501"
              }
            }
          }
        ]
      },
      "_links": {
        "self": {
          "href": "http://localhost:8080/orders"
        }
      }
    }

Một `PagedModel` còn có metadata trang:

    {
      "_embedded": {
        "orders": [
          { "id": 501, "status": "PAID" }
        ]
      },
      "_links": {
        "self": { "href": "http://localhost:8080/orders?page=0&size=20" },
        "next": { "href": "http://localhost:8080/orders?page=1&size=20" }
      },
      "page": {
        "size": 20,
        "totalElements": 41,
        "totalPages": 3,
        "number": 0
      }
    }

Các response trên là ví dụ minh họa. Relation name trong `_embedded`, URI, số trang và link thực tế phụ thuộc cấu hình API và dữ liệu.

Khi nâng cấp, kiểm tra:

- `Content-Type` có tiếp tục là media type mà client mong đợi, ví dụ `application/hal+json`.
- Relation name trong `_embedded` có giữ nguyên.
- Link relation và href có giữ nguyên.
- Metadata `page` có đúng size, number, totalElements và totalPages.
- Custom serializer hoặc projection có làm thay đổi field trong body không.

Không coi việc compile thành công là bằng chứng contract JSON không đổi.

## 7. RepresentationModel là lớp cơ sở mới

Nếu class cũ kế thừa `ResourceSupport` để chứa links, chuyển sang `RepresentationModel`.

Code cũ:

    public class OrderModel extends ResourceSupport {
        private Long id;
        private String status;
    }

Code mới:

    public class OrderModel
            extends RepresentationModel<OrderModel> {

        private Long id;
        private String status;
    }

Có thể thêm links bằng `add(...)`:

    model.add(
        linkTo(methodOn(OrderController.class)
            .getOrder(model.getId()))
            .withSelfRel()
    );

`RepresentationModel` là base class dành cho representation có hypermedia links. Nếu chỉ cần một DTO thuần không có links, không bắt buộc phải kế thừa lớp này.

## 8. ResourceAssembler chuyển thành RepresentationModelAssembler

Assembler tách logic chuyển domain object thành representation khỏi controller.

Code cũ:

    public class OrderResourceAssembler
            implements ResourceAssembler<Order, Resource<Order>> {

        @Override
        public Resource<Order> toResource(Order order) {
            Resource<Order> resource =
                new Resource<>(order);

            resource.add(
                linkTo(methodOn(OrderController.class)
                    .getOrder(order.getId()))
                    .withSelfRel()
            );

            return resource;
        }
    }

Code mới:

    @Component
    public class OrderModelAssembler
            implements RepresentationModelAssembler<
                Order,
                EntityModel<Order>
            > {

        @Override
        public EntityModel<Order> toModel(Order order) {
            return EntityModel.of(
                order,
                linkTo(methodOn(OrderController.class)
                    .getOrder(order.getId()))
                    .withSelfRel()
            );
        }
    }

Các điểm thay đổi:

- Interface là `RepresentationModelAssembler`.
- Method là `toModel(...)`, thay cho `toResource(...)`.
- Kiểu output là `EntityModel<Order>`.
- Link được thêm vào representation mới.

Controller có thể dùng assembler:

    @GetMapping("/{id}")
    EntityModel<Order> getOrder(@PathVariable Long id) {
        Order order = orders.findById(id)
            .orElseThrow(OrderNotFoundException::new);

        return assembler.toModel(order);
    }

Cách này giúp controller tập trung lấy dữ liệu và điều phối, còn assembler chịu trách nhiệm tạo representation.

## 9. ResourceAssemblerSupport chuyển thành RepresentationModelAssemblerSupport

Nếu code cũ kế thừa `ResourceAssemblerSupport`, API mới có `RepresentationModelAssemblerSupport`.

Ví dụ:

    @Component
    public class OrderModelAssembler
            extends RepresentationModelAssemblerSupport<
                Order,
                EntityModel<Order>
            > {

        public OrderModelAssembler() {
            super(OrderController.class, EntityModel.class);
        }

        @Override
        public EntityModel<Order> toModel(Order order) {
            return EntityModel.of(
                order,
                linkTo(methodOn(OrderController.class)
                    .getOrder(order.getId()))
                    .withSelfRel()
            );
        }
    }

Base class này hỗ trợ tạo representation và liên kết với controller tương ứng. Cần điều chỉnh constructor, model type và các method override theo phiên bản Spring HATEOAS đang dùng.

Nếu assembler đơn giản, triển khai trực tiếp `RepresentationModelAssembler` thường dễ đọc hơn và ít phụ thuộc base class.

## 10. ResourceProcessor chuyển thành RepresentationModelProcessor

`ResourceProcessor` cũ dùng để bổ sung hoặc điều chỉnh links sau khi representation được tạo. API mới là `RepresentationModelProcessor`.

Ví dụ:

    @Component
    public class OrderModelProcessor
            implements RepresentationModelProcessor<
                EntityModel<Order>
            > {

        @Override
        public EntityModel<Order> process(
                EntityModel<Order> model) {

            model.add(
                Link.of("/help/orders")
                    .withRel("help")
            );

            return model;
        }
    }

Processor phù hợp với thay đổi representation mang tính dùng chung. Nếu link phụ thuộc dữ liệu cụ thể hoặc quyền của principal, cần kiểm tra context và tránh thêm link mà caller không được phép thực hiện.

Không dùng processor để thay thế authorization ở endpoint. Link ẩn khỏi representation không phải hàng rào bảo mật; server vẫn phải kiểm tra quyền khi request được gọi trực tiếp.

## 11. ControllerLinkBuilder chuyển thành WebMvcLinkBuilder

Code cũ thường import:

    import static org.springframework.hateoas.mvc.ControllerLinkBuilder.linkTo;
    import static org.springframework.hateoas.mvc.ControllerLinkBuilder.methodOn;

API mới dùng:

    import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
    import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

Ví dụ:

    Link self = linkTo(
        methodOn(OrderController.class).getOrder(501L)
    ).withSelfRel();

    Link collection = linkTo(
        methodOn(OrderController.class).getOrders(
            Pageable.unpaged()
        )
    ).withRel("orders");

Dùng `methodOn(...)` giúp link được tạo từ mapping của controller method, bao gồm path variable và request mapping metadata. Cần tránh tạo link bằng chuỗi URL thủ công nếu có thể dùng mapping của controller.

Với ứng dụng không dùng Spring MVC, có thể có link builder khác trong Spring HATEOAS server API. Chọn builder phù hợp web stack và module đang chạy.

## 12. Import và package sau khi nâng cấp

Một số package mới thường gặp:

    import org.springframework.hateoas.RepresentationModel;
    import org.springframework.hateoas.EntityModel;
    import org.springframework.hateoas.CollectionModel;
    import org.springframework.hateoas.PagedModel;
    import org.springframework.hateoas.Link;

    import org.springframework.hateoas.server.RepresentationModelAssembler;
    import org.springframework.hateoas.server.RepresentationModelProcessor;
    import org.springframework.hateoas.server.mvc.RepresentationModelAssemblerSupport;
    import org.springframework.hateoas.server.mvc.WebMvcLinkBuilder;

Các class cũ có thể nằm trong package như `org.springframework.hateoas.mvc` hoặc `org.springframework.hateoas` tùy API. Khi nâng cấp, dùng IDE organize imports hoặc compiler để tìm chính xác import không còn tồn tại.

Không sửa hàng loạt tên import bằng text replacement nếu cùng một tên class xuất hiện trong package khác hoặc trong code ứng dụng tự định nghĩa.

## 13. Tích hợp với Spring Data REST

Spring Data REST tự tạo representation cho repository resources. Phần lớn ứng dụng không cần tự bọc từng entity trong `EntityModel` khi gọi repository exporter mặc định.

Các kiểu Spring HATEOAS mới thường xuất hiện khi:

- Viết custom controller hoặc custom repository handler.
- Dùng Spring HATEOAS assembler để tạo representation.
- Xây dựng custom endpoint trả collection hoặc page.
- Tùy chỉnh link và model processor.
- Kết hợp repository data với DTO hoặc view model.

Ví dụ custom controller dưới base path:

    @RepositoryRestController
    class OrderSearchController {

        private final OrderService orders;
        private final OrderModelAssembler assembler;

        @GetMapping("/orders/recent")
        ResponseEntity<CollectionModel<EntityModel<Order>>> recent() {
            List<EntityModel<Order>> models =
                orders.findRecent().stream()
                    .map(assembler::toModel)
                    .toList();

            CollectionModel<EntityModel<Order>> result =
                CollectionModel.of(models);

            result.add(
                linkTo(methodOn(OrderSearchController.class)
                    .recent())
                    .withSelfRel()
            );

            return ResponseEntity.ok(result);
        }
    }

Đây là ví dụ minh họa custom operation. Cần kiểm tra base path, controller annotation, repository mapping và message converter của ứng dụng. Không thêm wrapper thủ công vào endpoint exporter mặc định nếu framework đã tạo HAL representation phù hợp.

## 14. Nâng cấp theo từng bước

Khi chuyển một codebase cũ sang API mới:

1. Xác định Spring Boot, Spring Data và Spring HATEOAS version đang được dependency management chọn.
2. Tìm import và chữ ký dùng `Resource`, `Resources`, `PagedResources`, `ResourceSupport`.
3. Thay item wrapper bằng `EntityModel`.
4. Thay collection wrapper bằng `CollectionModel`.
5. Thay paged wrapper bằng `PagedModel`.
6. Thay base class bằng `RepresentationModel` nếu class thực sự cần chứa links.
7. Chuyển assembler sang `RepresentationModelAssembler` và đổi `toResource` thành `toModel`.
8. Chuyển processor sang `RepresentationModelProcessor`.
9. Chuyển controller link builder sang `WebMvcLinkBuilder` khi dùng Spring MVC.
10. Kiểm tra helper phân trang như `PagedResourcesAssembler` theo version; không tự đổi tên nếu thư viện vẫn cung cấp class đó.
11. Compile để phát hiện import và generic type còn sót.
12. Chạy integration test và so sánh HAL response, links, relation, page metadata và media type.

Không nâng riêng Spring HATEOAS lên một version bất kỳ nếu Spring Boot BOM đang quản lý compatibility. Dùng release train phù hợp với Spring Boot version của ứng dụng.

## 15. Kiểm thử sau migration

Nên kiểm tra cả kiểu Java và HTTP representation.

### 15.1. Unit test assembler

- `toModel(entity)` trả đúng content.
- Self link trỏ tới item URI đúng.
- Related link dùng relation name đúng.
- Link không xuất hiện nếu policy không cho caller thực hiện action đó.

### 15.2. Integration test controller

Ví dụ MockMvc:

    mockMvc.perform(get("/orders/501")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
            MediaTypes.HAL_JSON
        ))
        .andExpect(jsonPath("$._links.self.href").exists());

Với collection/page:

- Kiểm tra relation trong `_embedded`.
- Kiểm tra self, next và prev links.
- Kiểm tra `page.size`, `page.number`, `page.totalElements`, `page.totalPages`.
- Kiểm tra sort và pagination parameters được giữ trong links.

### 15.3. Contract test cho client

Nếu client đã phụ thuộc vào HAL response:

- So sánh relation name trước và sau migration.
- So sánh href và URI template.
- So sánh field JSON trong entity.
- So sánh media type.
- So sánh page metadata và link navigation.
- Kiểm tra projection/excerpt nếu endpoint dùng chúng.

Mục tiêu là bảo đảm migration Java không vô tình phá vỡ contract HTTP mà client đang sử dụng.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| `Resource` hoặc `Resources` không còn compile | Chuyển sang `EntityModel` hoặc `CollectionModel` |
| `PagedResources` không còn compile | Dùng `PagedModel` |
| `ResourceSupport` không còn compile | Dùng `RepresentationModel` |
| `toResource()` không còn trong assembler | Đổi sang `toModel()` |
| ControllerLinkBuilder import lỗi | Dùng `WebMvcLinkBuilder` trong Spring MVC |
| Generic type assembler không khớp | Cập nhật kiểu output thành EntityModel hoặc RepresentationModel tương ứng |
| Page mất next/prev link | Kiểm tra dùng đúng PagedResourcesAssembler/PagedModel và Pageable |
| `_embedded` relation đổi tên | Kiểm tra relation naming, collection model và HAL configuration |
| JSON body thay đổi sau nâng cấp | Kiểm tra serializer, wrapper type, projection và media type |
| Compile được nhưng client lỗi | Contract test chưa xác nhận links, media type hoặc page metadata |
| Version dependency xung đột | Spring HATEOAS được nâng độc lập với Spring Boot/Spring Data release train |
| Link URL sai | Kiểm tra controller mapping, base path, proxy và WebMvcLinkBuilder |

## 17. Checklist

1. Xác định version Spring Boot và Spring HATEOAS đang dùng.
2. Ánh xạ `Resource` sang `EntityModel`.
3. Ánh xạ `Resources` sang `CollectionModel`.
4. Ánh xạ `PagedResources` sang `PagedModel`.
5. Ánh xạ `ResourceSupport` sang `RepresentationModel`.
6. Chuyển assembler sang `RepresentationModelAssembler` và `toModel`.
7. Chuyển processor sang `RepresentationModelProcessor`.
8. Chuyển ControllerLinkBuilder sang WebMvcLinkBuilder trong Spring MVC.
9. Kiểm tra PagedResourcesAssembler theo dependency version; helper này có thể vẫn giữ tên cũ.
10. Cập nhật package import và generic type.
11. Compile và chạy test assembler/controller.
12. So sánh HAL links, relation, embedded content và page metadata.
13. Kiểm tra media type và client contract.
14. Dùng Spring Boot dependency management để giữ Spring Data/HATEOAS compatibility.
15. Chỉ thay đổi custom representation nơi ứng dụng thực sự tạo model; không bọc lại mặc định repository exporter một cách không cần thiết.

## Tài liệu tham khảo

- [Spring HATEOAS — Migration Guide](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring HATEOAS — Representation Models](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals)
- [Spring HATEOAS — Building Links](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.link-builder)
- [Spring HATEOAS — Representation Model Assemblers](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.assemblers)
- [Spring Data REST — Configuring the REST representation](https://docs.spring.io/spring-data/rest/reference/representations.html)
- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Boot — Spring HATEOAS support](https://docs.spring.io/spring-boot/reference/web/spring-hateoas.html)
