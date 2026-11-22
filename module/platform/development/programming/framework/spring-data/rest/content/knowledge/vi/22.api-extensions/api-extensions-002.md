# @RepositoryRestController và tích hợp với base path, converter, xử lý lỗi trong Spring Data REST

## Mục tiêu

Spring Data REST tự động xuất Spring Data repositories thành các REST resources. Tuy nhiên, có những trường hợp ứng dụng cần một endpoint tùy chỉnh để xử lý nghiệp vụ, tổng hợp dữ liệu, bổ sung bước kiểm tra hoặc thay đổi representation trước khi trả response.

Nếu endpoint cần hoạt động trong URI space của Spring Data REST và sử dụng hạ tầng của exporter, hãy cân nhắc `@RepositoryRestController`. Annotation này cho phép custom controller dùng chung các thiết lập quan trọng của Spring Data REST như:

- API base path được cấu hình trong `RepositoryRestConfiguration`.
- Message converters và content negotiation của exporter.
- Cơ chế exception handling của Spring Data REST.
- CORS policy của repository liên quan tới path.
- Với JPA, `OpenEntityManagerInViewInterceptor` được áp dụng cho handler phù hợp để hỗ trợ truy cập thuộc tính lazy trong request.

Bài này giải thích cách đặt route, tích hợp base path, dùng `DomainClassConverter` và `AggregateReference` để giải quyết domain object/URI reference, tạo HAL response bằng Spring HATEOAS, và xử lý lỗi theo HTTP contract.

## 1. Khi nào nên dùng @RepositoryRestController?

Dùng `@RepositoryRestController` khi custom handler gắn với một repository resource hoặc cần hòa vào URI space mà Spring Data REST quản lý.

Ví dụ, repository Order được export tại `/orders` và ứng dụng muốn bổ sung endpoint:

~~~text
GET /api/orders/42/summary
GET /api/orders/search/recent
POST /api/orders/42/recalculate
~~~

Các endpoint này thuộc vùng API của repository Order và cần dùng cấu hình exporter.

Một controller có thể được khai báo như sau:

~~~java
@RepositoryRestController
class OrderCustomController {

    private final OrderRepository repository;

    OrderCustomController(OrderRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/orders/{id}/summary")
    ResponseEntity<?> getSummary(@PathVariable Long id) {
        // Đọc dữ liệu, áp dụng nghiệp vụ và tạo representation.
        return ResponseEntity.ok().build();
    }
}
~~~

Import annotation:

~~~java
import org.springframework.data.rest.webmvc.RepositoryRestController;
~~~

Đây là Spring bean do annotation kết hợp `@Component` tạo ra. Controller vẫn dùng các annotation Spring MVC thông thường như `@GetMapping`, `@PostMapping`, `@PathVariable`, `@RequestParam` và `@RequestBody`.

Điều quan trọng là request mapping phải nằm trong URI space mà Spring Data REST quản lý. Handler mapping của exporter kiểm tra repository được export theo path segment tương ứng. Nếu path không thuộc vùng repository phù hợp, request có thể được chuyển cho các HandlerMapping khác hoặc không được xử lý bởi custom handler như mong đợi.

## 2. Tích hợp với API base path

Giả sử ứng dụng cấu hình:

~~~properties
spring.data.rest.base-path=/api
~~~

Hoặc cấu hình bằng Java:

~~~java
@Configuration
class RestConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {
        config.setBasePath("/api");
    }
}
~~~

Với controller:

~~~java
@RepositoryRestController
class OrderCustomController {

    @GetMapping("/orders/{id}/summary")
    ResponseEntity<?> getSummary(@PathVariable Long id) {
        // ...
        return ResponseEntity.ok().build();
    }
}
~~~

URL bên ngoài là:

~~~http
GET /api/orders/42/summary
~~~

Spring Data REST tự đặt controller dưới base path đã cấu hình. Vì vậy, mapping method chỉ khai báo phần path tương đối như `/orders/{id}/summary`; không lặp lại `/api` trong từng annotation.

Nếu vừa cấu hình base path `/api` vừa viết:

~~~java
@GetMapping("/api/orders/{id}/summary")
~~~

thì URL có thể trở thành path lặp `/api/api/orders/...` hoặc không khớp URI mong muốn, tùy cấu hình mapping. Hãy để base path do exporter quản lý.

Có thể kiểm tra base path bằng cách gọi API root và theo các link HAL. Với custom route, nên công bố link từ representation liên quan nếu client cần khám phá endpoint thay vì tự ghép URL.

## 3. Phân biệt @RepositoryRestController, @BasePathAwareController và @RestController

Ba annotation phục vụ các phạm vi khác nhau:

| Annotation | Phạm vi phù hợp | Hạ tầng Spring Data REST |
| --- | --- | --- |
| `@RepositoryRestController` | Custom operation gắn với URI space của repository | Có: base path, message converters, exception handling và chức năng bổ sung của exporter |
| `@BasePathAwareController` | Custom operation nằm dưới base path nhưng không gắn với entity/repository cụ thể | Được đặt dưới base path; dùng khi xây dựng resource hoặc view riêng |
| `@RestController` | API Spring MVC thông thường, có namespace riêng | Không tự động dùng hạ tầng Spring Data REST |

Ví dụ dùng `@BasePathAwareController` cho endpoint chung:

~~~java
@BasePathAwareController
class ApiHealthController {

    @GetMapping("/health")
    ResponseEntity<Map<String, String>> health() {
        return ResponseEntity.ok(Map.of("status", "UP"));
    }
}
~~~

Với base path `/api`, endpoint nằm tại `/api/health`. Endpoint này thuộc namespace của Spring Data REST nhưng không phải thao tác trên một repository cụ thể.

Dùng `@RestController` nếu muốn route hoàn toàn thuộc Spring MVC, ví dụ `/internal-tools/**` hoặc một API version khác. Controller thông thường không tự động nhận cấu hình base path, message converters, exception handling hay CORS của Spring Data REST.

Tóm lại:

- Thao tác tùy chỉnh quanh repository resource: `@RepositoryRestController`.
- Tài nguyên chung dưới base path: `@BasePathAwareController`.
- API MVC độc lập: `@RestController`.

## 4. Tránh xung đột với route repository mặc định

Spring Data REST đã tạo các route cho collection, item, search và association. Custom handler không nên vô tình trùng mapping với endpoint mặc định.

Ví dụ repository Order có:

~~~java
@RepositoryRestResource(path = "orders")
interface OrderRepository extends JpaRepository<Order, Long> {
}
~~~

Exporter có thể sử dụng:

~~~text
GET    /api/orders
POST   /api/orders
GET    /api/orders/{id}
PUT    /api/orders/{id}
PATCH  /api/orders/{id}
DELETE /api/orders/{id}
~~~

Custom route nên có hậu tố hoặc namespace rõ ràng:

~~~java
@GetMapping("/orders/{id}/summary")
@GetMapping("/orders/search/recent")
@PostMapping("/orders/{id}/recalculate")
~~~

Tránh khai báo một custom `@GetMapping("/orders/{id}")` nếu mục đích là thay thế item resource mặc định. Khi thực sự muốn override response handler cho một resource cụ thể, cần hiểu thứ tự HandlerMapping và hành vi của exporter trên đúng phiên bản Spring Data REST.

Nếu custom operation không cần gắn với repository, chuyển nó sang `@BasePathAwareController` hoặc controller MVC riêng để tránh tranh chấp URI.

## 5. Tạo response có hypermedia bằng Spring HATEOAS

Custom handler có thể trả `ResponseEntity` để kiểm soát HTTP status và header. Nếu response thuộc API hypermedia, nên dùng model types của Spring HATEOAS thay vì trả một `List<T>` trần.

Ví dụ collection:

~~~java
@RepositoryRestController
class OrderCustomController {

    private final OrderRepository repository;

    OrderCustomController(OrderRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/orders/search/recent")
    ResponseEntity<CollectionModel<EntityModel<Order>>> recent() {

        List<EntityModel<Order>> items = repository
                .findTop10ByOrderByCreatedAtDesc()
                .stream()
                .map(order -> EntityModel.of(
                        order,
                        linkTo(methodOn(OrderCustomController.class)
                                .getSummary(order.getId()))
                                .withRel("summary")))
                .toList();

        CollectionModel<EntityModel<Order>> model =
                CollectionModel.of(items);

        model.add(linkTo(methodOn(OrderCustomController.class)
                .recent()).withSelfRel());

        return ResponseEntity.ok(model);
    }

    @GetMapping("/orders/{id}/summary")
    ResponseEntity<EntityModel<Order>> getSummary(@PathVariable Long id) {
        Order order = repository.findById(id).orElseThrow();
        return ResponseEntity.ok(EntityModel.of(order));
    }
}
~~~

Các kiểu model thường dùng:

- `CollectionModel<T>`: representation cho collection.
- `EntityModel<T>`: representation cho một entity/resource.
- `RepresentationModel<T>`: abstraction tổng quát hơn cho resource có links.

Spring Data REST khuyến nghị bọc collection bằng `CollectionModel`; item đơn có thể dùng `EntityModel` hoặc `RepresentationModel`. Có thể tạo link bằng `linkTo(methodOn(...))` để tránh hardcode host, port hoặc base path.

Import thường dùng:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.http.ResponseEntity;
~~~

Khi trả `ResponseEntity`, Spring MVC/Spring Data REST chọn message converter tương ứng với `Accept` của request. Client có thể yêu cầu HAL bằng:

~~~http
Accept: application/hal+json
~~~

Không nên trả trực tiếp implementation nội bộ như `PageImpl` nếu cần contract JSON ổn định. Với page, hãy dùng Spring HATEOAS `PagedModel`/assembler hoặc DTO representation được thiết kế rõ ràng.

## 6. DomainClassConverter: chuyển path variable thành entity

Spring Data web support cung cấp `DomainClassConverter`. Converter này cho phép method parameter là domain type do repository quản lý, thay vì nhận ID rồi tự gọi repository.

Ví dụ:

~~~java
@RepositoryRestController
class PersonCustomController {

    @GetMapping("/people/{id}/card")
    ResponseEntity<PersonCard> getCard(
            @PathVariable("id") Person person) {

        return ResponseEntity.ok(
                new PersonCard(person.getId(), person.getDisplayName()));
    }
}
~~~

Khi Spring Data web support được bật và converter phù hợp được đăng ký, Spring MVC thực hiện các bước:

1. Đọc giá trị chuỗi từ path variable, ví dụ `42`.
2. Dùng `ConversionService` chuyển chuỗi sang kiểu ID của domain type, ví dụ `Long`.
3. Tìm repository `CrudRepository` quản lý domain type đó.
4. Gọi repository để lấy entity tương ứng.
5. Truyền entity vào tham số controller.

Spring Data web support có thể được bật bằng:

~~~java
@Configuration
@EnableSpringDataWebSupport
class SpringDataWebConfiguration {
}
~~~

Trong ứng dụng Spring Boot hoặc Spring Data REST đã tự cấu hình web support, hãy kiểm tra cấu hình hiện tại trước khi đăng ký thêm annotation này để tránh tạo cấu hình trùng lặp.

`DomainClassConverter` yêu cầu repository tương ứng triển khai `CrudRepository` để được phát hiện cho conversion. Nó đặc biệt hữu ích khi custom handler nhận ID resource thông thường.

### Khi nào nên nhận ID và tự tìm repository?

Không phải mọi trường hợp đều nên dùng domain parameter. Nếu muốn xử lý trường hợp không tồn tại rõ ràng, có thể nhận ID và gọi repository:

~~~java
@GetMapping("/people/{id}/card")
ResponseEntity<PersonCard> getCard(@PathVariable Long id) {

    Person person = repository.findById(id)
            .orElseThrow(() -> new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Không tìm thấy Person"));

    return ResponseEntity.ok(
            new PersonCard(person.getId(), person.getDisplayName()));
}
~~~

Cách này giúp controller chủ động định nghĩa response 404, kiểm tra quyền trên entity trước khi trả dữ liệu và dễ kiểm soát hơn khi cần nhiều bước nghiệp vụ.

Đừng giả định mọi converter đều chuyển một chuỗi thành entity theo cùng quy tắc. `DomainClassConverter` sử dụng kiểu ID của repository; nó không đơn thuần đọc JSON body và cũng không thay thế logic authorization.

## 7. AggregateReference: nhận URI tham chiếu theo Spring Data REST

Trong custom controller, request có thể chứa URI tới một aggregate khác. Từ Spring Data REST 4.1, có thể dùng `AggregateReference<T, ID>` làm tham số để nhận URI và giải quyết thành ID hoặc aggregate.

Ví dụ client gọi:

~~~http
GET /api/scanners?producer=http://localhost:8080/api/producers/15
Accept: application/hal+json
~~~

Controller:

~~~java
@RepositoryRestController
class ScannerController {

    @GetMapping("/scanners")
    ResponseEntity<?> getScanners(
            @RequestParam AggregateReference<Producer, Long> producer) {

        Long producerId = producer.resolveRequiredId();

        // Dùng producerId để truy vấn Scanner theo producer.
        return ResponseEntity.ok().build();
    }
}
~~~

Có thể yêu cầu aggregate đầy đủ:

~~~java
Producer producer = producerReference.resolveRequiredAggregate();
~~~

Các phương thức quan trọng:

- `getUri()`: lấy URI nguồn mà client gửi.
- `resolveId()`: giải quyết identifier, có thể trả null nếu không resolve được.
- `resolveRequiredId()`: yêu cầu phải resolve được ID.
- `resolveAggregate()`: giải quyết aggregate, có thể trả null.
- `resolveRequiredAggregate()`: yêu cầu phải tìm được aggregate.
- `withIdSource(...)`: tùy chỉnh cách trích identifier từ URI components.

Import:

~~~java
import org.springframework.data.rest.core.AggregateReference;
~~~

Khác với `DomainClassConverter`, `AggregateReference` làm việc với URI theo scheme mà Spring Data REST dùng để expose item resources. Nó phù hợp khi client truyền một resource URI thay vì chỉ gửi một giá trị ID đơn.

Nếu dùng custom identifier trong URI, ví dụ username hoặc slug, có thể cần tùy chỉnh cách trích identifier bằng `withIdSource`. Hãy kiểm tra mapping identifier và lookup của repository để bảo đảm URI reference được giải quyết nhất quán.

Không nên nhận URI từ client rồi tự tải bất kỳ URL tùy ý nào. AggregateReference giải quyết reference theo hạ tầng repository của Spring Data REST; vẫn phải kiểm tra domain type, sự tồn tại của aggregate và quyền truy cập.

## 8. Phân biệt DomainClassConverter và AggregateReference

| Tiêu chí | DomainClassConverter | AggregateReference |
| --- | --- | --- |
| Input thường gặp | Path variable hoặc request parameter chứa ID | URI của item resource |
| Kết quả | Domain object do repository quản lý | URI reference có thể resolve thành ID hoặc aggregate |
| Cơ chế | ConversionService + CrudRepository | Spring Data REST URI resolution |
| Dùng khi | Route có `/{id}` và handler cần entity trực tiếp | Request tham chiếu resource khác bằng URI |
| Kiểu repository | Cần CrudRepository được phát hiện | Dựa trên aggregate/repository mapping của Spring Data REST |
| Tùy chỉnh identifier | Theo chuyển đổi ID của repository | Có thể dùng `withIdSource` để trích ID từ URI |

Ví dụ ngắn:

~~~java
// ID trong path -> domain object
@GetMapping("/people/{id}/card")
PersonCard getCard(@PathVariable Person person) {
    return mapper.toCard(person);
}

// URI của resource khác -> aggregate identifier
@GetMapping("/scanners")
List<Scanner> byProducer(
        @RequestParam AggregateReference<Producer, Long> producer) {
    return repository.findByProducerId(producer.resolveRequiredId());
}
~~~

Hai cơ chế giải quyết hai kiểu input khác nhau. Không thay thế lẫn nhau một cách máy móc.

## 9. Message converters và content negotiation

Một lý do quan trọng để dùng `@RepositoryRestController` là custom handler được xử lý bởi hạ tầng Spring Data REST, bao gồm message converters và cấu hình content negotiation.

Ví dụ endpoint chỉ nhận JSON:

~~~java
@PostMapping(
    path = "/orders/{id}/commands/recalculate",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaTypes.HAL_JSON_VALUE
)
ResponseEntity<EntityModel<OrderSummary>> recalculate(
        @PathVariable Long id,
        @RequestBody RecalculateOrderRequest request) {
    // ...
}
~~~

- `consumes`: giới hạn Content-Type mà endpoint chấp nhận.
- `produces`: định dạng response mà endpoint tạo.
- `@RequestBody`: được đọc qua message converter phù hợp.
- `ResponseEntity`: kiểm soát status, headers và body.

Với request:

~~~http
POST /api/orders/42/commands/recalculate
Content-Type: application/json
Accept: application/hal+json
~~~

Spring chọn converter đọc JSON body và converter ghi response theo media type đã thương lượng.

Nếu client gửi Content-Type không được hỗ trợ, server có thể trả 415 Unsupported Media Type. Nếu Accept không thể được đáp ứng, server có thể trả 406 Not Acceptable.

Khi dùng `@RestController` thông thường, controller có thể sử dụng các converter Spring MVC được đăng ký cho MVC, nhưng không tự động nhận toàn bộ message converter và representation configuration riêng của Spring Data REST. Đây là một khác biệt thực tế khi endpoint trả HAL hoặc sử dụng custom media type của exporter.

## 10. Xử lý lỗi trong custom handler

Custom handler nên chuyển lỗi nghiệp vụ thành HTTP response rõ ràng. Ví dụ:

- Không tìm thấy resource: 404 Not Found.
- Người gọi không có quyền: 403 Forbidden.
- Request không hợp lệ: 400 Bad Request.
- Trạng thái nghiệp vụ không cho phép thao tác: 409 Conflict.
- Content-Type không hỗ trợ: 415 Unsupported Media Type.

Cách đơn giản cho một lỗi cụ thể:

~~~java
@GetMapping("/orders/{id}/summary")
ResponseEntity<OrderSummary> getSummary(@PathVariable Long id) {

    Order order = repository.findById(id)
            .orElseThrow(() -> new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Không tìm thấy đơn hàng"));

    return ResponseEntity.ok(mapper.toSummary(order));
}
~~~

Với lỗi tùy chỉnh, có thể đặt `@ExceptionHandler` ngay trong controller:

~~~java
@RepositoryRestController
class OrderCustomController {

    @GetMapping("/orders/{id}/summary")
    ResponseEntity<OrderSummary> getSummary(@PathVariable Long id) {
        // Có thể ném OrderNotAccessibleException.
        return ResponseEntity.ok().build();
    }

    @ExceptionHandler(OrderNotAccessibleException.class)
    ResponseEntity<ProblemDetail> handleNotAccessible(
            OrderNotAccessibleException exception) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.FORBIDDEN,
                "Bạn không có quyền truy cập đơn hàng này");

        problem.setTitle("Không được phép truy cập");

        return ResponseEntity.status(HttpStatus.FORBIDDEN)
                .body(problem);
    }
}
~~~

Spring Framework hỗ trợ `ProblemDetail` cho error response theo RFC 9457 trên các phiên bản tương ứng. Nếu dự án dùng phiên bản cũ hơn, có thể trả DTO lỗi riêng hoặc `ResponseEntity<ApiError>`.

### Dùng ControllerAdvice khi cần xử lý tập trung

Có thể dùng `@RestControllerAdvice` để xử lý exception từ nhiều custom controller:

~~~java
@RestControllerAdvice(assignableTypes = OrderCustomController.class)
class OrderControllerAdvice {

    @ExceptionHandler(OrderNotAccessibleException.class)
    ResponseEntity<ApiError> handle(OrderNotAccessibleException exception) {
        return ResponseEntity.status(HttpStatus.FORBIDDEN)
                .body(new ApiError(
                        "ORDER_FORBIDDEN",
                        "Bạn không có quyền truy cập đơn hàng"));
    }
}
~~~

Nếu muốn advice áp dụng cho nhiều controller, có thể bỏ `assignableTypes` hoặc dùng `basePackages` phù hợp. Tuy nhiên, advice toàn cục có thể ảnh hưởng cả handler của Spring Data REST và các controller khác. Hãy giới hạn phạm vi khi cần giữ nguyên exception mapping mặc định của exporter.

Spring Data REST có exception handler riêng cho repository resources. `@RepositoryRestController` giúp custom controller dùng chung exception handling của exporter. Controller `@RestController` thông thường nằm ngoài phạm vi đó và dùng cơ chế exception resolver của Spring MVC.

Không bắt mọi exception rồi trả 200 hoặc 500 chung chung. Hãy ánh xạ exception theo ý nghĩa HTTP và không đưa stack trace, SQL, tên bảng hoặc dữ liệu nội bộ vào response production.

## 11. Tích hợp validation và request DTO

Custom endpoint thường thực hiện nghiệp vụ phức tạp hơn repository CRUD. Nên dùng DTO cho request thay vì bind trực tiếp toàn bộ entity:

~~~java
public record RecalculateOrderRequest(
        @NotBlank String reason,
        @Min(1) int priority
) {}
~~~

~~~java
@PostMapping(
    path = "/orders/{id}/commands/recalculate",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
ResponseEntity<OrderSummary> recalculate(
        @PathVariable Long id,
        @Valid @RequestBody RecalculateOrderRequest request) {

    OrderSummary summary = orderService.recalculate(id, request);

    return ResponseEntity.ok(summary);
}
~~~

DTO tạo allowlist field được phép gửi. Service chịu trách nhiệm xác thực nghiệp vụ, authorization và transaction. Không để client gửi toàn bộ entity graph hoặc các field nội bộ như owner, tenant, payment state hay audit metadata nếu họ không có quyền sửa.

Khi validation thất bại, Spring MVC có thể tạo exception tương ứng. Hãy kiểm thử error response để bảo đảm client nhận field error hữu ích nhưng không nhận dữ liệu nhạy cảm.

## 12. CORS, lazy loading và security

`@RepositoryRestController` được xử lý bởi HandlerMapping riêng của Spring Data REST nên có thêm một số tích hợp:

- CORS policy được định nghĩa cho repository tương ứng với base path segment trong mapping.
- Với JPA, `OpenEntityManagerInViewInterceptor` có thể được áp dụng để hỗ trợ truy cập thuộc tính lazy trong request.

Điều này không có nghĩa mọi custom route đều tự động an toàn:

- CORS chỉ điều khiển browser cross-origin access, không cấp quyền nghiệp vụ.
- Open EntityManager in View có thể giúp proxy lazy được truy cập trong request, nhưng không thay thế fetch plan hoặc DTO.
- Spring Security vẫn phải bảo vệ custom method và resource.
- Nếu custom controller truy cập repository trực tiếp, cần kiểm tra tenant/owner/role như mọi API khác.

Với controller độc lập `@RestController`, cần cấu hình CORS và transaction/fetch strategy theo hạ tầng MVC/service của ứng dụng.

## 13. Kiểm thử base path và custom route bằng MockMvc

Nên kiểm tra route sau khi áp dụng base path, không chỉ gọi mapping path tương đối.

Ví dụ cấu hình `spring.data.rest.base-path=/api`, test:

~~~java
@SpringBootTest(properties = "spring.data.rest.base-path=/api")
@AutoConfigureMockMvc
class OrderCustomControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void customRouteIsServedUnderRepositoryBasePath() throws Exception {
        mockMvc.perform(get("/api/orders/42/summary")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk());
    }
}
~~~

Kiểm thử DomainClassConverter:

~~~java
@Test
void resolvesRepositoryManagedDomainFromPathVariable() throws Exception {
    mockMvc.perform(get("/api/people/12/card")
            .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk());
}
~~~

Test này giả định web support và repository fixture đã được cấu hình, đồng thời Person có ID 12.

Kiểm thử lỗi 404:

~~~java
@Test
void returnsNotFoundForUnknownOrder() throws Exception {
    mockMvc.perform(get("/api/orders/999999/summary")
            .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isNotFound());
}
~~~

Kiểm thử lỗi validation:

~~~java
@Test
void rejectsInvalidCommandBody() throws Exception {
    mockMvc.perform(post("/api/orders/42/commands/recalculate")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "reason": "",
                  "priority": 0
                }
                """))
        .andExpect(status().isBadRequest());
}
~~~

Ngoài status code, nên xác nhận response body và Content-Type theo error contract đã chọn. Nếu route trả HAL, kiểm tra link self và các relation cần thiết. Nếu route trả DTO JSON, kiểm tra các field được allowlist.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Custom route thiếu `/api` | Controller không được xử lý như RepositoryRestController hoặc mapping thuộc MVC thông thường | Kiểm tra annotation và base path |
| URL thành `/api/api/...` | Lặp base path trong cả config và mapping | Chỉ khai báo phần route tương đối trong mapping |
| Handler không được gọi | Path không nằm trong URI space của repository exporter hoặc mapping xung đột | Kiểm tra repository path, mapping và HandlerMapping |
| `@RestController` không dùng message converter của exporter | Controller nằm ngoài phạm vi Spring Data REST | Dùng @RepositoryRestController nếu endpoint gắn với repository |
| Không resolve được `@PathVariable Person` | DomainClassConverter/web support chưa được đăng ký hoặc repository không phù hợp | Kiểm tra @EnableSpringDataWebSupport và CrudRepository |
| AggregateReference không resolve URI | URI không theo scheme item resource hoặc identifier extractor không đúng | Kiểm tra href và cấu hình withIdSource |
| Trả collection nhưng thiếu link | Handler trả List thuần thay vì HATEOAS model | Dùng CollectionModel/EntityModel và thêm link |
| Client nhận 406 | Accept không khớp produces/converter | Kiểm tra media type và response model |
| Client nhận 415 | Content-Type không được endpoint chấp nhận | Khai báo consumes phù hợp và gửi đúng Content-Type |
| Lỗi custom trả 500 | Exception chưa được ánh xạ | Dùng @ExceptionHandler, ControllerAdvice hoặc ResponseStatusException |
| Advice thay đổi lỗi của exporter | Advice toàn cục bắt exception quá rộng | Giới hạn advice theo controller/package và giữ exception mapping phù hợp |
| LazyInitializationException hoặc N+1 | Truy cập association ngoài fetch plan hoặc custom route không có persistence context phù hợp | Dùng service transaction, DTO, EntityGraph và kiểm tra query |
| CORS không theo policy repository | Controller không được xử lý bằng SDR HandlerMapping hoặc path không gắn repository | Kiểm tra annotation, path và RepositoryRestConfigurer |

## 15. Quy trình thiết kế custom endpoint

1. Xác định endpoint có thực sự gắn với repository resource hay chỉ cần nằm dưới base path.
2. Chọn `@RepositoryRestController`, `@BasePathAwareController` hoặc `@RestController` đúng phạm vi.
3. Cấu hình base path ở một nơi; mapping chỉ khai báo phần path tương đối.
4. Tránh xung đột với collection, item, search và association routes mặc định.
5. Chọn input type phù hợp: ID, DomainClassConverter, AggregateReference hoặc DTO.
6. Dùng Spring HATEOAS model nếu response cần hypermedia links.
7. Khai báo consumes/produces và trả ResponseEntity với status/header phù hợp.
8. Ánh xạ exception nghiệp vụ thành HTTP status và error body rõ ràng.
9. Bảo vệ endpoint bằng authorization và kiểm tra owner/tenant.
10. Kiểm thử URL thực tế sau base path, converter, content negotiation và error mapping.

## Tài liệu tham khảo

- [Spring Data REST — Overriding Spring Data REST Response Handlers](https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr-response-handlers.html): `@RepositoryRestController`, base path, message converters, exception handling, HATEOAS models, AggregateReference và khác biệt với `@BasePathAwareController`.
- [Spring Data REST API — RepositoryRestController](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/RepositoryRestController.html): annotation đánh dấu controller do Spring Data REST quản lý, CORS và OpenEntityManagerInView integration.
- [Spring Data REST — Getting Started](https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html): cấu hình base path bằng `spring.data.rest.base-path` hoặc `RepositoryRestConfiguration.setBasePath`.
- [Spring Data Commons — DomainClassConverter](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/repository/support/DomainClassConverter.html): chuyển input thành domain object thông qua ConversionService và CrudRepository.
- [Spring Data JPA — Web Support](https://docs.spring.io/spring-data/jpa/reference/repositories/core-extensions.html): `@EnableSpringDataWebSupport`, DomainClassConverter, Pageable/Sort argument resolvers và cách Spring MVC resolve domain object từ path variable.
- [Spring Data REST API — AggregateReference](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/AggregateReference.html): nhận URI reference, resolve ID/aggregate và tùy chỉnh identifier source.
- [Spring Framework — Exception Handling](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html): `@ExceptionHandler`, `@ControllerAdvice` và ResponseEntity.
- [Spring Framework — Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): ProblemDetail, ErrorResponse và ResponseEntityExceptionHandler theo RFC 9457.
