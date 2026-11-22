# Tránh trùng đường dẫn giữa repository và Controller tự viết

## Mục tiêu

Khi Spring Data REST export một repository, nó tự tạo các endpoint cho collection, item, search và association. Nếu ứng dụng đồng thời khai báo Controller tự viết với cùng đường dẫn, request có thể được xử lý bởi handler mapping của Spring Data REST thay vì Controller mà lập trình viên dự định.

Để tránh lỗi định tuyến, cần xác định rõ vùng URI nào thuộc repository và vùng nào thuộc API tự viết. Khi thực sự muốn bổ sung hoặc thay thế một thao tác trong URI space của repository, hãy dùng đúng loại Controller của Spring Data REST.

## 1. Repository được export tạo ra vùng URI riêng

Ví dụ:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {

    List<Person> findByLastName(@Param("lastName") String lastName);
}
~~~

Với cấu hình mặc định, repository có thể cung cấp các endpoint dạng:

| URI | Ý nghĩa |
|---|---|
| `/people` | Collection resource |
| `/people/{id}` | Một item theo ID |
| `/people/search` | Điểm vào các query method được export |
| `/people/search/findByLastName?lastName=Nguyen` | Tìm kiếm theo họ |
| `/people/{id}/orders` | Association resource nếu domain model có quan hệ được export |

Nếu cấu hình `spring.data.rest.base-path=/api`, các URI trên được đặt dưới base path, ví dụ `/api/people` và `/api/people/42`.

Tên đường dẫn collection có thể được thay đổi bằng `@RepositoryRestResource(path = "...")`. Tên của search resource có thể được tùy chỉnh bằng `@RestResource(path = "...")` trên query method. Vì vậy, phải kiểm tra đường dẫn thực tế mà repository export trước khi đặt mapping cho Controller khác.

## 2. Vì sao hai Controller có thể tranh cùng một request?

Spring MVC sử dụng các `HandlerMapping` để tìm handler cho mỗi request. Spring Data REST đăng ký `RepositoryRestHandlerMapping` cho các Controller và endpoint thuộc phạm vi REST repository.

Handler mapping này kiểm tra URL path và tên repository đã export. Nếu path thuộc một repository được export, Spring Data REST nhận request. Nếu không có repository tương ứng, handler mapping trả về `null` để các `HandlerMapping` khác tiếp tục tìm handler.

Tài liệu tích hợp Spring Data REST vào ứng dụng Spring MVC mô tả `RepositoryRestHandlerMapping` được cấu hình với order `Ordered.LOWEST_PRECEDENCE - 100` và thường được xét trước mapping của ứng dụng. Ví dụ, khi repository được export dưới tên `person`, request bắt đầu bằng `/person` thuộc vùng Spring Data REST và Controller MVC thông thường của ứng dụng không nhận request đó.

Ví dụ dễ gây nhầm lẫn:

~~~java
@RestController
@RequestMapping("/people")
class PersonController {

    @GetMapping("/{id}")
    PersonView getPerson(@PathVariable Long id) {
        // custom response
    }
}
~~~

Nếu repository cũng export dưới đường dẫn `/people`, mapping `GET /people/{id}` của Controller này đụng vào URI space của repository. Không nên giả định Spring sẽ luôn chọn method trong Controller tự viết hoặc luôn báo lỗi ambiguous mapping ngay khi khởi động. Kết quả phụ thuộc loại Controller, các `HandlerMapping` đã đăng ký, thứ tự mapping và phiên bản/cấu hình ứng dụng.

Trong cùng một `HandlerMapping`, hai request mapping trùng hoàn toàn có thể gây lỗi ambiguous mapping khi đăng ký. Nhưng khi các handler nằm trong những `HandlerMapping` khác nhau, việc kiểm tra trùng lặp không nhất thiết diễn ra trong cùng một registry. Vì vậy, ứng dụng vẫn có thể khởi động nhưng request được chuyển đến handler khác với dự định.

## 3. Quy hoạch namespace trước khi viết Controller

Cách dễ quản lý nhất là dành các root path riêng cho từng nhóm API:

| Vùng URI | Chủ sở hữu | Ví dụ |
|---|---|---|
| `/api/people/**` | Repository `PersonRepository` | `GET /api/people/42` |
| `/api/orders/**` | Repository `OrderRepository` | `GET /api/orders/15` |
| `/api/reports/**` | Controller tự viết | `GET /api/reports/daily` |
| `/api/admin/**` | Controller tự viết | `POST /api/admin/reindex` |

Ví dụ, nếu `people` và `orders` là repository path, không nên đặt Controller MVC thông thường tại `/api/people/**` hoặc `/api/orders/**`. Hãy đặt các chức năng độc lập tại `/api/reports/**` hoặc một namespace riêng phù hợp với ứng dụng.

Một số nguyên tắc cụ thể:

- Dùng tên collection repository ổn định, rõ nghĩa và tránh trùng với root path của Controller.
- Dành các đường dẫn `/search/**` và các association path dưới repository cho những chức năng thuộc tài nguyên đó.
- Không tạo Controller tổng quát với `@RequestMapping("/api")` rồi khai báo lại những đường dẫn con đã thuộc repository.
- Nếu đổi `@RepositoryRestResource(path = "...")`, kiểm tra cả client, link HAL, tài liệu API và Controller hiện có.
- Không dựa vào việc hai path có tên khác nhau một chút. Hãy xác định rõ segment đầu tiên sau base path và các đường dẫn con đã export.

## 4. Chọn đúng annotation cho Controller tự viết

Spring Data REST cung cấp các annotation khác nhau tùy mục đích.

### 4.1. @RepositoryRestController: thao tác nằm trong URI space của repository

Dùng `@RepositoryRestController` khi muốn viết handler cho một tài nguyên cụ thể, dùng cấu hình REST của Spring Data REST và đặt mapping trong URI space mà repository quản lý.

Ví dụ thêm một search operation tùy chỉnh cho people:

~~~java
@RepositoryRestController
class PersonSearchController {

    private final PersonRepository repository;

    PersonSearchController(PersonRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/people/search/active")
    ResponseEntity<?> findActive() {
        var people = repository.findByActiveTrue();

        var result = people.stream()
            .map(EntityModel::of)
            .toList();

        return ResponseEntity.ok(CollectionModel.of(result));
    }
}
~~~

Đường dẫn thực tế là base path của Spring Data REST cộng với `/people/search/active`. Ví dụ base path là `/api` thì request là `GET /api/people/search/active`.

Đây là cách phù hợp khi endpoint thuộc về repository resource và cần dùng các cấu hình liên quan của Spring Data REST. Tài liệu Spring Data REST nêu rằng loại Controller này được xử lý bởi handler mapping đặc biệt, có thể áp dụng CORS của repository tương ứng và `OpenEntityManagerInViewInterceptor` khi dùng JPA.

Nếu mapping tùy chỉnh trùng với một search endpoint đã export, hãy coi đó là hành vi thay thế có chủ đích: ghi rõ hợp đồng endpoint, bảo đảm mapping được đăng ký như mong đợi và viết kiểm thử cho handler thực tế. Nếu chỉ muốn thêm chức năng, hãy chọn một path chưa được repository sử dụng.

### 4.2. @BasePathAwareController: Controller riêng dưới base path

Dùng `@BasePathAwareController` khi muốn xây dựng các thao tác tùy chỉnh dưới base path của Spring Data REST nhưng chúng không phải thao tác đặc thù của một repository, ví dụ báo cáo, tài nguyên tổng hợp hoặc endpoint điều phối.

~~~java
@BasePathAwareController
class ReportController {

    @ResponseBody
    @GetMapping("/reports/daily")
    DailyReport dailyReport() {
        return reportService.createDailyReport();
    }
}
~~~

Với base path `/api`, endpoint là `GET /api/reports/daily`. Namespace `reports` được dành riêng cho Controller nên không tranh với `/people` hoặc `/orders`.

### 4.3. @RestController: API Spring MVC độc lập

Dùng `@RestController` cho các endpoint thuộc API Spring MVC thông thường, nằm ngoài phạm vi xử lý của Spring Data REST.

~~~java
@RestController
@RequestMapping("/internal")
class InternalController {

    @GetMapping("/health")
    HealthStatus health() {
        return new HealthStatus("UP");
    }
}
~~~

Controller này dùng mapping của Spring MVC. Nó không tự động nhận base path của Spring Data REST và không tự động dùng message converter, exception handling hay cấu hình CORS của Spring Data REST. Nếu muốn nó nằm dưới cùng base path, cần cấu hình prefix của ứng dụng một cách nhất quán hoặc cân nhắc `@BasePathAwareController`.

Không dùng `@RestController` thông thường với mục đích ghi đè một endpoint repository rồi kỳ vọng nó được Spring Data REST nhận diện. Nếu muốn xử lý trong URI space của repository, hãy dùng `@RepositoryRestController`.

## 5. Ví dụ thiết kế trước và sau

Giả sử repository export:

~~~java
@RepositoryRestResource(path = "products")
public interface ProductRepository extends JpaRepository<Product, Long> {
}
~~~

Các endpoint repository đã chiếm vùng `/products`:

- `GET /api/products`
- `POST /api/products`
- `GET /api/products/10`
- `PUT /api/products/10`
- `PATCH /api/products/10`
- `DELETE /api/products/10`
- Các search và association path được export.

Thiết kế dễ gây xung đột:

~~~java
@RestController
@RequestMapping("/api/products")
class ProductController {

    @GetMapping("/{id}")
    ProductDetails details(@PathVariable Long id) {
        // custom details
    }

    @PostMapping
    ProductView create(@RequestBody ProductInput input) {
        // custom create flow
    }
}
~~~

Hai mapping `GET /api/products/{id}` và `POST /api/products` trùng với chức năng repository. Client có thể gọi nhầm handler hoặc nhận response khác với định dạng HAL dự kiến.

Thiết kế tách namespace:

~~~java
@RestController
@RequestMapping("/api/product-operations")
class ProductOperationsController {

    @GetMapping("/{id}/summary")
    ProductSummary summary(@PathVariable Long id) {
        // custom summary
    }

    @PostMapping("/{id}/recalculate")
    RecalculationResult recalculate(@PathVariable Long id) {
        // custom operation
    }
}
~~~

Các thao tác đặc thù nằm ở `/api/product-operations/**`; repository vẫn quản lý `/api/products/**`. Nếu muốn các thao tác này nằm dưới base path do Spring Data REST quản lý, có thể dùng `@BasePathAwareController` với `/product-operations/**` thay cho hard-code `/api`.

## 6. Khi cần tùy chỉnh chính endpoint repository

Có những trường hợp nghiệp vụ yêu cầu giữ nguyên URI của repository nhưng xử lý khác endpoint mặc định. Ví dụ, một query method chỉ trả dữ liệu đã qua lọc bổ sung, hoặc response cần được tổng hợp từ nhiều repository.

Khi đó:

1. Xác định chính xác URI và HTTP method đang được repository export.
2. Tạo `@RepositoryRestController` và mapping nằm trong cùng URI space.
3. Tránh đăng ký một `@RestController` thông thường trên cùng path với mong đợi nó ghi đè handler của Spring Data REST.
4. Trả representation phù hợp với API. Với Spring HATEOAS, dùng `EntityModel` cho một tài nguyên và `CollectionModel` cho collection khi phù hợp.
5. Viết kiểm thử để xác nhận request thực sự đi vào custom handler và response không làm hỏng hợp đồng HAL mà client đang sử dụng.

Nếu mục tiêu chỉ là đổi tên hoặc ẩn một endpoint repository, hãy cân nhắc cấu hình export của repository hoặc query method trước khi tạo Controller mới. Việc tạo thêm handler cho một URI đã có thể làm tăng độ phức tạp định tuyến.

## 7. Cách kiểm tra đường dẫn có bị trùng

### 7.1. Kiểm tra danh sách mapping thực tế

Khi ứng dụng bật Spring Boot Actuator và expose endpoint mappings, có thể kiểm tra:

~~~http
GET /actuator/mappings
~~~

Tìm các path liên quan đến repository và Controller tự viết. Endpoint này có thể hiển thị handler method cùng mapping đã đăng ký. Chỉ expose Actuator mapping cho môi trường và người dùng phù hợp vì thông tin này tiết lộ cấu trúc nội bộ của ứng dụng.

Có thể bật log chi tiết cho quá trình đăng ký mapping và chọn handler trong môi trường phát triển:

~~~properties
logging.level.org.springframework.web.servlet.handler=DEBUG
logging.level.org.springframework.data.rest.webmvc=DEBUG
~~~

Tên logger và lượng log cụ thể có thể thay đổi theo phiên bản Spring Framework/Spring Data REST.

### 7.2. Kiểm thử bằng MockMvc

Đừng chỉ kiểm tra rằng ứng dụng khởi động thành công. Hãy gửi request đến các URI quan trọng và xác nhận handler, status cùng response:

~~~java
@WebMvcTest
class RepositoryRouteTests {

    @Autowired
    MockMvc mvc;

    @Test
    void repositoryCollectionUsesSpringDataRest() throws Exception {
        mvc.perform(get("/api/people"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaTypes.HAL_JSON));
    }

    @Test
    void customReportUsesItsOwnNamespace() throws Exception {
        mvc.perform(get("/api/reports/daily"))
            .andExpect(status().isOk());
    }

    @Test
    void customRepositoryOperationUsesExpectedHandler() throws Exception {
        mvc.perform(get("/api/people/search/active"))
            .andExpect(status().isOk());
    }
}
~~~

Đây là khung minh họa. Bổ sung mock repository/service, cấu hình Spring Data REST và assertion cho body/link theo ứng dụng thực tế. Nếu dùng `@WebMvcTest`, bảo đảm slice test import đúng cấu hình cần thiết; một integration test với `@SpringBootTest` và `@AutoConfigureMockMvc` có thể phù hợp hơn khi cần kiểm tra đầy đủ cả repository handler mapping lẫn MVC handler mapping.

Các điểm cần xác nhận:

- Collection và item URI của repository vẫn trả response dự kiến.
- Search endpoint mặc định vẫn hoạt động nếu không chủ ý thay thế.
- Custom endpoint đi vào đúng Controller.
- Request với HTTP method không được hỗ trợ trả status phù hợp.
- Base path được áp dụng đúng cho cả repository và Controller mang annotation tương ứng.
- Không có endpoint cũ hoặc endpoint khác vô tình chiếm cùng path.

## 8. Checklist trước khi thêm Controller

- Ghi lại base path của Spring Data REST, ví dụ `/api`.
- Ghi lại collection path thực tế của từng repository đã export.
- Liệt kê các item, search và association path quan trọng.
- Chọn namespace riêng cho Controller nghiệp vụ độc lập.
- Dùng `@RepositoryRestController` khi cần xử lý trong URI space của repository.
- Dùng `@BasePathAwareController` cho custom operation dưới base path nhưng không gắn với một repository cụ thể.
- Dùng `@RestController` cho API Spring MVC độc lập ngoài phạm vi repository.
- Kiểm tra mappings thực tế và chạy request test cho từng path có nguy cơ trùng.
- Khi thay đổi repository path, cập nhật client, tài liệu API và các link liên quan.

## Kết luận

Spring Data REST sở hữu URI space được tạo từ các repository export. Controller tự viết cần có namespace riêng nếu cung cấp chức năng độc lập. Khi cần custom handler bên trong URI space của repository, hãy dùng `@RepositoryRestController`; khi cần endpoint chung dưới base path, dùng `@BasePathAwareController`; còn `@RestController` thông thường dành cho mapping Spring MVC độc lập. Xác nhận route bằng mapping thực tế và MockMvc/integration test để bảo đảm mỗi request đến đúng handler.

## Tài liệu tham khảo

- Spring Data REST – Overriding Spring Data REST Response Handlers: https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr-response-handlers.html
- Spring Data REST – Adding Spring Data REST to an Existing Spring MVC Application: https://www.springframework.org/spring-data/rest/reference/customizing/adding-sdr-to-spring-mvc-app.html
- Spring Data REST – Getting Started and Changing the Base URI: https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html
