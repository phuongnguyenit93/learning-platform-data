# Viết endpoint nghiệp vụ qua service và bổ sung liên kết HAL

## Mục tiêu

Spring Data REST tự export các Spring Data repository thành REST resource. Tuy nhiên, một use case nghiệp vụ thường có nhiều bước hơn CRUD: kiểm tra trạng thái, áp dụng quy tắc miền, phối hợp nhiều repository hoặc gọi dịch vụ khác, rồi trả về kết quả có các liên kết để client tiếp tục thao tác.

Với loại use case này, hãy tạo một endpoint HTTP riêng gọi application service. Service chịu trách nhiệm thực hiện nghiệp vụ và transaction; controller chịu trách nhiệm chuyển HTTP request thành lời gọi service và định dạng response. Khi response cần hypermedia, dùng Spring HATEOAS để tạo HAL links bằng các API biết route của controller hoặc repository.

Ví dụ trong bài dùng thao tác xác nhận đơn hàng: `POST /orders/{id}/confirm`. Đây là ví dụ minh họa; thay domain, route, DTO và quy tắc nghiệp vụ bằng use case thực tế của ứng dụng.

## 1. Chia trách nhiệm giữa controller, service và repository

Một endpoint nghiệp vụ thường có ba lớp:

| Thành phần | Trách nhiệm |
|---|---|
| Controller / HTTP adapter | Khai báo route và HTTP method, parse/validate input, gọi service, chọn status/header và trả representation |
| Application service | Thực hiện use case, kiểm tra quyền/quy tắc nghiệp vụ, phối hợp repository và hệ thống khác, xác định transaction boundary |
| Repository | Đọc và ghi aggregate/domain data qua Spring Data |

Controller không nên tự chứa quy tắc như “đơn hàng chỉ được xác nhận khi đã thanh toán”, cũng không nên tự phối hợp nhiều repository. Đưa quy tắc đó vào domain/service để có thể gọi từ HTTP, job hoặc message handler mà vẫn giữ cùng hành vi.

Service nên trả về kết quả nghiệp vụ hoặc DTO phù hợp với use case. Controller chuyển kết quả đó thành HTTP representation. Với API công khai, DTO thường giúp kiểm soát field được phát hành và tránh vô tình serialize toàn bộ entity hoặc lazy association.

Ví dụ service:

~~~java
@Service
public class ConfirmOrderService {

    private final OrderRepository orders;

    public ConfirmOrderService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public OrderSummary confirm(Long orderId) {
        Order order = orders.findById(orderId)
            .orElseThrow(() -> new OrderNotFoundException(orderId));

        order.confirm(); // Domain kiểm tra trạng thái và quy tắc xác nhận.
        Order saved = orders.save(order);

        return OrderSummary.from(saved);
    }
}
~~~

Trong ví dụ, `Order.confirm()` chịu trách nhiệm bảo vệ invariant của domain. Service điều phối thao tác và đặt transaction boundary. Nếu use case cần ghi nhiều aggregate hoặc phát event, đặt toàn bộ chuỗi công việc cần tính nguyên tử trong cùng transaction phù hợp; xử lý tác vụ ngoài transaction bằng cơ chế nhất quán tương ứng.

Không để controller tự gọi `repository.save()` rồi tự kiểm tra trạng thái. Cách đó khiến logic nghiệp vụ bị gắn với HTTP và dễ bị bỏ qua khi use case được gọi từ nơi khác.

## 2. Chọn annotation controller phù hợp với Spring Data REST

Spring Data REST có hai annotation quan trọng cho custom controller:

- **`@RepositoryRestController`:** dùng khi custom handler thuộc URI space của repository được export, ví dụ bổ sung operation dưới `/orders/{id}` hoặc thay handler cho một resource/search cụ thể. Controller được phục vụ dưới base path của Spring Data REST và tham gia các tích hợp tương ứng như message converter, exception handling và CORS cấu hình cho repository.
- **`@BasePathAwareController`:** dùng cho operation tùy chỉnh nằm dưới base path nhưng không gắn với resource repository cụ thể, ví dụ một workflow nghiệp vụ tổng hợp hoặc endpoint điều phối.

Một `@RestController` thông thường nằm ngoài phạm vi xử lý riêng của Spring Data REST. Nó vẫn có thể là API hợp lệ trong ứng dụng Spring MVC, nhưng không tự động nhận cùng request handling, message converter và exception handling của Spring Data REST. Hãy chọn rõ controller thuộc API nào để tránh hai cơ chế xử lý cạnh tranh cùng một route.

Với thao tác xác nhận một đơn hàng, route nằm ngay dưới collection resource `orders`, vì vậy ví dụ dùng `@RepositoryRestController`:

~~~java
@RepositoryRestController
public class OrderBusinessController {

    private final ConfirmOrderService confirmOrder;
    private final RepositoryEntityLinks repositoryLinks;

    public OrderBusinessController(
            ConfirmOrderService confirmOrder,
            RepositoryEntityLinks repositoryLinks) {
        this.confirmOrder = confirmOrder;
        this.repositoryLinks = repositoryLinks;
    }

    @PostMapping("/orders/{id}/confirm")
    public ResponseEntity<EntityModel<OrderSummary>> confirm(
            @PathVariable Long id) {

        OrderSummary summary = confirmOrder.confirm(id);

        EntityModel<OrderSummary> model = EntityModel.of(summary);
        model.add(repositoryLinks
            .linkToItemResource(Order.class, id)
            .withRel("order"));
        model.add(repositoryLinks
            .linkToCollectionResource(Order.class)
            .withRel("orders"));
        model.add(linkTo(methodOn(OrderBusinessController.class)
            .confirm(id))
            .withRel("confirm"));

        return ResponseEntity.ok(model);
    }
}
~~~

Đây là skeleton để minh họa cách ghép các thành phần; bổ sung import, validation, authorization và exception mapping theo phiên bản Spring Boot/Spring Data đang dùng. Ví dụ giả định collection relation mặc định là `orders`, repository export domain type `Order`, và ứng dụng có service/DTO tương ứng.

Nếu route không nằm trong URI space của repository, đổi sang `@BasePathAwareController`. Đừng gắn `@RepositoryRestController` chỉ vì muốn URL có cùng prefix; annotation này còn ảnh hưởng đến handler mapping và tích hợp của Spring Data REST.

## 3. Tạo HAL links bằng API thay vì ghép URL thủ công

HAL dùng `_links` để biểu diễn các quan hệ có thể điều hướng. Một response nghiệp vụ có thể trả DTO cùng các link liên quan:

~~~json
{
  "id": 42,
  "status": "CONFIRMED",
  "total": 125.50,
  "_links": {
    "order": {
      "href": "https://api.example.test/orders/42"
    },
    "orders": {
      "href": "https://api.example.test/orders"
    },
    "confirm": {
      "href": "https://api.example.test/orders/42/confirm"
    }
  }
}
~~~

Các URL trên chỉ là ví dụ để minh họa cấu trúc HAL. Trong code, hãy dùng API tạo link:

### Link đến repository resource: `RepositoryEntityLinks`

Spring Data REST cung cấp `RepositoryEntityLinks` để tạo link tới resource do repository export:

~~~java
repositoryLinks.linkToCollectionResource(Order.class);
repositoryLinks.linkToItemResource(Order.class, orderId);
repositoryLinks.linkToSearchResource(Order.class, "findByStatus");
repositoryLinks.linksToSearchResources(Order.class);
~~~

Các phương thức này phù hợp để tạo link tới collection, item và search resource của repository. Chúng biết cấu hình export của Spring Data REST và giảm nguy cơ link sai khi đổi base path, collection path hoặc search path.

### Link đến custom controller: `WebMvcLinkBuilder`

Khi link tới method của custom Spring MVC controller, dùng `linkTo(methodOn(...))`:

~~~java
Link confirmLink = linkTo(
    methodOn(OrderBusinessController.class).confirm(orderId)
).withRel("confirm");
~~~

Spring HATEOAS đọc mapping của controller/method để dựng URI. Nếu route thay đổi, link được sinh theo mapping mới thay vì một chuỗi URL bị lặp ở nhiều nơi.

Không ghép URL bằng `"/orders/" + id` hoặc hard-code host/port. Cách đó dễ sai khi có base path, servlet context path, reverse proxy hoặc cấu hình deployment khác nhau. Spring Data REST khuyến nghị dùng `RepositoryEntityLinks` cho resource do repository export; Spring HATEOAS `linkTo` phù hợp với endpoint MVC do ứng dụng tự viết.

### Chọn relation rõ nghĩa

Dùng relation ổn định, dễ hiểu với client:

- `self`: resource mà representation hiện tại mô tả.
- `order`: link đến resource đơn hàng.
- `orders`: link về collection.
- `confirm`: thao tác nghiệp vụ có thể thực hiện tiếp.
- `receipt`: link đến biên nhận nếu use case tạo ra biên nhận.

Không dùng tên class Java hoặc tên method nội bộ làm relation nếu chúng không có ý nghĩa với client. Nếu relation là một loại custom link được nhiều client dùng, cân nhắc công bố tài liệu/profile cho ý nghĩa của relation đó.

## 4. Dùng RepresentationModel cho response có hypermedia

Spring HATEOAS cung cấp các kiểu model chính:

| Kiểu | Dùng khi |
|---|---|
| `EntityModel<T>` | Một đối tượng/DTO kèm các link |
| `CollectionModel<T>` | Một collection kèm link cấp collection |
| `PagedModel<T>` | Collection có thông tin phân trang |
| `RepresentationModel<T>` | Kiểu cơ sở khi cần tự định nghĩa representation model |

Nếu có nhiều endpoint chuyển cùng loại entity sang cùng cấu trúc HAL, tách logic dựng representation vào `RepresentationModelAssembler` thay vì lặp link trong controller:

~~~java
@Component
public class OrderSummaryAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderSummary>> {

    private final RepositoryEntityLinks repositoryLinks;

    public OrderSummaryAssembler(RepositoryEntityLinks repositoryLinks) {
        this.repositoryLinks = repositoryLinks;
    }

    @Override
    public EntityModel<OrderSummary> toModel(Order order) {
        OrderSummary summary = OrderSummary.from(order);

        return EntityModel.of(summary,
            repositoryLinks
                .linkToItemResource(Order.class, order.getId())
                .withSelfRel(),
            repositoryLinks
                .linkToCollectionResource(Order.class)
                .withRel("orders"));
    }
}
~~~

Assembler nhận domain object và tạo representation có cấu trúc nhất quán. Với collection, có thể dùng `toCollectionModel(Iterable)` để chuyển danh sách thành `CollectionModel` chứa các model item.

Nếu endpoint trả về kết quả nghiệp vụ không phải entity, có thể tạo `EntityModel<YourDto>` trực tiếp hoặc xây assembler chuyên cho DTO. Không cần ép mọi response thành entity model nếu DTO phản ánh use case tốt hơn.

## 5. Bổ sung link vào representation mặc định của Spring Data REST

Nếu mục tiêu chỉ là thêm một link vào representation entity mà Spring Data REST đã export, không cần tạo endpoint CRUD mới. Dùng `RepresentationModelProcessor`:

~~~java
@Configuration
public class OrderRepresentationConfiguration {

    @Bean
    RepresentationModelProcessor<EntityModel<Order>> orderLinks(
            RepositoryEntityLinks repositoryLinks) {

        return model -> {
            model.getContent().ifPresent(order -> {
                model.add(repositoryLinks
                    .linkToCollectionResource(Order.class)
                    .withRel("orders"));
            });
            return model;
        };
    }
}
~~~

Ví dụ chỉ thêm link collection cho representation Order. Trong ứng dụng thực tế, thêm link tới workflow hoặc resource liên quan khi có đủ dữ liệu và điều kiện. Processor được Spring Data REST phát hiện và gọi khi exporter tạo representation tương ứng.

Dùng processor khi muốn enrich response mặc định cho nhiều request. Dùng custom controller khi cần một operation nghiệp vụ mới có request/response riêng. Tránh tạo một controller chỉ để lặp lại dữ liệu mà repository resource đã cung cấp.

Nếu cần link chỉ xuất hiện khi đơn hàng đang ở trạng thái có thể xác nhận, kiểm tra điều kiện nghiệp vụ trước khi thêm link. Link là gợi ý điều hướng cho client; service vẫn phải kiểm tra lại trạng thái khi request thực sự được gửi vì trạng thái có thể thay đổi giữa lúc đọc và lúc thao tác.

## 6. Xử lý lỗi, validation và tính nhất quán

Một custom endpoint cần có contract lỗi rõ ràng:

- ID không tồn tại: trả lỗi not found phù hợp.
- Request body hoặc parameter sai: trả lỗi validation với field/constraint có thể hiểu được.
- Trạng thái miền không cho phép thao tác: trả conflict hoặc lỗi nghiệp vụ theo chính sách API.
- Người dùng không có quyền: trả unauthorized/forbidden theo cấu hình security.
- Lỗi hạ tầng: giữ nguyên ranh giới lỗi server, không để lộ stack trace hoặc chi tiết nội bộ.

Đặt validation input ở HTTP boundary bằng Bean Validation khi phù hợp, nhưng không dựa vào validation DTO để thay thế invariant trong domain. Service/domain phải bảo vệ quy tắc ngay cả khi được gọi từ một entry point khác.

Đặt transaction ở application service hoặc phương thức use case để ranh giới commit/rollback gắn với nghiệp vụ. Không giữ transaction mở trong lúc gọi HTTP service bên ngoài nếu có thể tránh; cân nhắc outbox/event hoặc cơ chế điều phối phù hợp khi use case cần phối hợp hệ thống khác.

Đối với thao tác như xác nhận, hủy hoặc thanh toán, xác định rõ tính lặp lại (idempotency), concurrency và retry. Nếu hai request cùng thao tác một đơn hàng, service phải xử lý trạng thái cạnh tranh bằng optimistic locking, khóa phù hợp hoặc quy tắc miền để không thực hiện chuyển trạng thái hai lần.

## 7. Kiểm thử endpoint và HAL links

Dùng `@SpringBootTest` cùng `@AutoConfigureMockMvc` để kiểm tra endpoint trong application context thực. MockMvc thực thi Spring MVC request handling mà không cần server thật.

Ví dụ kiểm tra response và link:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderBusinessControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void confirmReturnsOrderSummaryAndHalLinks() throws Exception {
        long orderId = 42L; // Fixture đã được tạo trong test database.

        mvc.perform(post("/api/orders/{id}/confirm", orderId)
                .accept("application/hal+json"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith("application/hal+json"))
            .andExpect(jsonPath("$.id").value(orderId))
            .andExpect(jsonPath("$.status").value("CONFIRMED"))
            .andExpect(jsonPath("$._links.order.href").exists())
            .andExpect(jsonPath("$._links.orders.href").exists())
            .andExpect(jsonPath("$._links.confirm.href").exists());
    }
}
~~~

Trong ví dụ, `/api` là base path giả định. Điều chỉnh URL theo `RepositoryRestConfiguration`/Spring Boot property của ứng dụng. Fixture phải được tạo trong test và trạng thái sau request phải được xác nhận qua repository hoặc endpoint đọc tương ứng.

Bổ sung các ca kiểm thử:

1. ID hợp lệ và trạng thái cho phép: service chạy, response chứa DTO và các link cần thiết.
2. ID không tồn tại: status not found, không ghi dữ liệu.
3. Trạng thái không hợp lệ: trả lỗi nghiệp vụ và không đổi trạng thái.
4. Không có quyền: request bị từ chối; không gọi use case nếu authorization được chặn ở HTTP boundary.
5. Hai request cạnh tranh: chỉ một chuyển trạng thái thành công hoặc kết quả theo chính sách idempotency.
6. Link có base path đúng và không chứa host/port hard-code.
7. Representation có media type HAL và relation đúng tên.

Có thể dùng Mockito để kiểm tra controller gọi service đúng tham số trong test hẹp; vẫn nên có integration test với service/repository thật để xác nhận transaction, serialization, security và link mapping hoạt động cùng nhau.

Nếu dùng live server hoặc test qua reverse proxy, thêm kiểm thử ở mức HTTP thật cho forwarded headers, HTTPS và base path. MockMvc không mô phỏng toàn bộ hành vi của servlet container/proxy.

## 8. Quy trình triển khai một endpoint nghiệp vụ

1. Mô tả use case, actor, điều kiện trước/sau và các lỗi nghiệp vụ.
2. Xác định endpoint có nằm trong URI space của repository không để chọn `@RepositoryRestController` hay `@BasePathAwareController`.
3. Tạo DTO request/response và validation phù hợp; chỉ công bố field cần thiết.
4. Viết service thực hiện use case, áp dụng quy tắc miền và transaction.
5. Viết controller mỏng: nhận request, gọi service, tạo response và status/header.
6. Tạo link đến repository bằng `RepositoryEntityLinks`, link đến custom controller bằng `WebMvcLinkBuilder`.
7. Dùng `EntityModel`/`CollectionModel` hoặc assembler để biểu diễn HAL.
8. Viết test thành công, lỗi, security, concurrency và link mapping.
9. Kiểm tra API root/collection và response thực tế để bảo đảm endpoint/link có thể được client khám phá.

## 9. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Custom route không được gọi | Annotation/controller mapping không khớp URI space hoặc base path | Kiểm tra `@RepositoryRestController`/`@BasePathAwareController`, mapping và base path |
| Route chạy nhưng không dùng converter/exception handling mong muốn | Dùng `@RestController` nằm ngoài pipeline Spring Data REST | Dùng annotation phù hợp nếu route thuộc API base path |
| Link trả về sai host hoặc thiếu base path | Ghép URL thủ công hoặc thiếu forwarded header config | Dùng `RepositoryEntityLinks`/`WebMvcLinkBuilder`; kiểm tra proxy config |
| HAL response không có `_links` | Trả DTO/POJO thuần hoặc content negotiation không đúng | Trả `EntityModel`/`CollectionModel` và yêu cầu HAL media type |
| Collection có link nhưng từng item không có | Chỉ thêm link cấp collection | Dùng assembler tạo `EntityModel` cho từng item |
| Link xuất hiện dù thao tác không còn hợp lệ | Thêm link không xét trạng thái hoặc quyền | Tạo link có điều kiện; service vẫn kiểm tra lại khi thực thi |
| Controller chứa quá nhiều logic | Quy tắc miền và phối hợp repository nằm trong HTTP adapter | Chuyển use case sang application service/domain |
| Dữ liệu cập nhật một phần khi có lỗi | Transaction boundary đặt sai hoặc service gọi nhiều hệ thống ngoài transaction | Đặt transaction quanh phần ghi nguyên tử; thiết kế outbox/saga cho hệ thống ngoài |
| Test pass nhưng link production sai | MockMvc không mô phỏng proxy/ingress hoặc base path thực | Thêm live-server/ingress test và kiểm tra forwarded headers |

## Tài liệu chính thức

- [Spring Data REST — Overriding Response Handlers](https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr-response-handlers.html): `@RepositoryRestController`, `@BasePathAwareController`, response model và aggregate reference.
- [Spring Data REST — Integration](https://docs.spring.io/spring-data/rest/reference/integration.html): tạo link tới collection, item và search resource bằng `RepositoryEntityLinks`.
- [Spring Data REST — Customizing the JSON Output](https://docs.spring.io/spring-data/rest/reference/customizing/customizing-json-output.html): `RepresentationModelProcessor` và cách bổ sung link vào representation mặc định.
- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): resource model và hành vi HTTP của repository export.
- [Spring HATEOAS — EntityModel](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/EntityModel.html): model đơn chứa nội dung và links.
- [Spring HATEOAS — CollectionModel](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/CollectionModel.html): model cho collection.
- [Spring HATEOAS — RepresentationModelAssembler](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/RepresentationModelAssembler.html): chuyển domain object thành representation model.
- [Spring HATEOAS — WebMvcLinkBuilder](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/mvc/WebMvcLinkBuilder.html): dựng link tới Spring MVC controller method bằng `linkTo` và `methodOn`.
- [Spring Framework — MockMvc](https://docs.spring.io/spring/reference/testing/mockmvc.html): kiểm thử Spring MVC request/response mà không cần khởi động server thật.
