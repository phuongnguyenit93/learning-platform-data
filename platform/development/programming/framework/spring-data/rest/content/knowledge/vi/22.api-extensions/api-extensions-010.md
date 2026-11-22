# Giải quyết xung đột mapping và thay thế bộ xử lý mặc định có chủ đích

## Mục tiêu

Spring Data REST tự động tạo HTTP endpoint từ các repository được export. Khi ứng dụng cần xử lý một route đặc biệt, thêm logic nghiệp vụ hoặc thay thế response mặc định, controller tự viết có thể trùng URI với collection, item hoặc search resource do Spring Data REST quản lý.

Muốn xử lý đúng, cần hiểu controller nào sở hữu URL, mapping nào được áp dụng trước và annotation nào đưa custom controller vào đúng phạm vi của Spring Data REST.

Các nguyên tắc chính:

- Dùng `@RepositoryRestController` khi custom handler thuộc URI space của một repository đã export và cần dùng message converter, exception handling, CORS cùng các tích hợp của Spring Data REST.
- Dùng `@BasePathAwareController` cho endpoint tùy chỉnh nằm dưới API base path nhưng không gắn với một repository resource cụ thể.
- Dùng `@Controller` hoặc `@RestController` thông thường cho endpoint Spring MVC độc lập, có prefix riêng và không cạnh tranh với URI của repository.
- Nếu chủ đích thay thế một search endpoint được sinh tự động, hãy quản lý trạng thái export của finder để chỉ còn một handler sở hữu route.
- Không thay đổi thứ tự hoặc implementation nội bộ của HandlerMapping chỉ để ép một route chạy theo ý muốn.

## 1. Spring Data REST tạo route từ repository như thế nào?

Ví dụ repository:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {

    List<Person> findByLastName(String lastName);
}
~~~

Với base path mặc định, Spring Data REST tạo các resource chính:

| Resource | URI ví dụ | Mục đích |
|---|---|---|
| Collection | `/people` | Liệt kê và tạo Person |
| Item | `/people/42` | Đọc, cập nhật hoặc xóa một Person |
| Search collection | `/people/search` | Khám phá finder được export |
| Search method | `/people/search/findByLastName?lastName=Nguyen` | Chạy derived query |

Nếu cấu hình base path là `/api`, các URI tương ứng có thêm prefix:

~~~java
@Configuration
public class RestConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {
        config.setBasePath("/api");
    }
}
~~~

Khi đó collection là `/api/people`, item là `/api/people/42`, và search resource là `/api/people/search`.

Vì các route được sinh từ repository, một controller MVC tự viết có mapping như `/people/{id}` có thể đụng vào chính URI mà Spring Data REST quản lý. Trước khi thêm controller, hãy xác định chính xác collection path, item path, search path và base path của API.

## 2. RepositoryRestHandlerMapping và quyền sở hữu URL

Spring Data REST đăng ký một `RepositoryRestHandlerMapping` riêng. Mapping này tìm handler thuộc Spring Data REST và chỉ nhận request khi path tương ứng với một repository đã được export.

Điều này có hai hệ quả:

1. URI nằm trong namespace của repository có thể được xử lý bởi Spring Data REST, kể cả khi ứng dụng có các controller MVC khác.
2. URI không tương ứng với repository đã export có thể được chuyển tiếp cho các `HandlerMapping` khác để Spring MVC xử lý.

Ví dụ, khi repository được export dưới path `people`, các request bắt đầu bằng `/people` thuộc URI space của repository. Nếu ứng dụng có một controller thông thường cũng khai báo `/people/{id}`, không nên giả định controller đó sẽ nhận request.

Một custom controller muốn tham gia URI space này cần dùng annotation của Spring Data REST. Việc khai báo cùng một path trong một `@RestController` không tự động thay thế handler mặc định của repository.

Không nên sửa thứ tự `HandlerMapping` hoặc thay bean nội bộ của Spring Data REST để giải quyết xung đột thông thường. Các extension point được hỗ trợ là `@RepositoryRestController`, `@BasePathAwareController`, cấu hình exposure và trạng thái export của repository/finder.

## 3. Chọn đúng annotation cho custom controller

Ba lựa chọn thường gặp có phạm vi khác nhau:

| Annotation | Khi nên dùng | Tích hợp với Spring Data REST |
|---|---|---|
| `@RepositoryRestController` | Handler gắn với URI space của repository | Có base path, repository CORS và JPA OpenEntityManagerInView; dùng cấu hình REST của framework |
| `@BasePathAwareController` | Endpoint tùy chỉnh dưới base path nhưng không phải thao tác entity cụ thể | Được gắn với API base path |
| `@Controller` / `@RestController` | Endpoint MVC độc lập, tách khỏi repository URI space | Dùng cơ chế Spring MVC thông thường, nằm ngoài xử lý REST exporter |

### 3.1. @RepositoryRestController

Dùng khi custom handler thay thế hoặc mở rộng hành vi của một resource mà Spring Data REST quản lý:

~~~java
@RepositoryRestController
public class PersonSearchController {

    private final PersonRepository repository;

    public PersonSearchController(PersonRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/people/search/recent")
    public ResponseEntity<?> findRecentPeople() {
        // Truy vấn repository và xây dựng representation tùy chỉnh.
        return ResponseEntity.ok(repository.findTop10ByOrderByCreatedAtDesc());
    }
}
~~~

Controller này nằm trong API base path của Spring Data REST. Nếu base path là `/api`, mapping trên được truy cập qua `/api/people/search/recent`.

Annotation này còn cho phép handler nhận các tích hợp theo repository path:

- CORS configuration được định nghĩa cho repository tương ứng.
- `OpenEntityManagerInViewInterceptor` khi dùng JPA, giúp truy cập các property cần lazy loading trong phạm vi request.
- Message converters và exception handling của Spring Data REST.

### 3.2. @BasePathAwareController

Dùng khi muốn có endpoint dưới base path nhưng không gắn với một repository cụ thể, ví dụ metadata hoặc thao tác tổng hợp:

~~~java
@BasePathAwareController
public class ApiMetadataController {

    @GetMapping("/metadata/status")
    @ResponseBody
    public Map<String, String> status() {
        return Map.of("status", "available");
    }
}
~~~

Nếu base path là `/api`, endpoint nằm ở `/api/metadata/status`. Đây là lựa chọn phù hợp khi API cần một route riêng bên cạnh các repository resource.

### 3.3. @RestController thông thường

Nếu endpoint không thuộc API base path hoặc không cần các tích hợp của Spring Data REST, dùng một controller MVC riêng với prefix rõ ràng:

~~~java
@RestController
@RequestMapping("/internal/reports")
public class InternalReportController {

    @GetMapping("/summary")
    public ReportSummary summary() {
        return new ReportSummary("ready");
    }
}
~~~

Không dùng controller MVC thông thường để cạnh tranh với các URI đã được Spring Data REST export. Controller thông thường nằm ngoài phạm vi message converter, exception handling và repository CORS configuration của Spring Data REST.

## 4. Thay thế một search handler mặc định có chủ đích

Một trường hợp rõ ràng là repository đã có finder nhưng response mặc định không đáp ứng nhu cầu. Ví dụ muốn giữ URL `/orders/search/by-status` nhưng xử lý thêm phân quyền, tổng hợp hoặc chuyển đổi kết quả.

Repository:

~~~java
@RepositoryRestResource(path = "orders")
public interface OrderRepository extends JpaRepository<Order, UUID> {

    @RestResource(
        path = "by-status",
        rel = "by-status",
        exported = false
    )
    List<Order> findByStatus(OrderStatus status);
}
~~~

`exported = false` ngăn finder này được công bố thành search resource mặc định. Method Java vẫn tồn tại và custom controller có thể gọi nó qua repository.

Custom handler:

~~~java
@RepositoryRestController
public class OrderSearchController {

    private final OrderRepository repository;

    public OrderSearchController(OrderRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/orders/search/by-status")
    public ResponseEntity<?> findByStatus(
            @RequestParam OrderStatus status) {

        List<Order> orders = repository.findByStatus(status);
        return ResponseEntity.ok(CollectionModel.of(
            orders.stream().map(EntityModel::of).toList()
        ));
    }
}
~~~

Khi đó:

- URL công khai vẫn là `/orders/search/by-status`.
- Finder tự động không còn được export.
- Custom controller chịu trách nhiệm xử lý request và tạo response.
- Repository method vẫn được dùng như một API truy vấn nội bộ của ứng dụng.

Nếu response là collection hypermedia, nên thêm self link và các link cần thiết. Ví dụ có thể dùng `linkTo(methodOn(...))` của Spring HATEOAS để tạo link thay vì tự ghép URL.

## 5. Thay thế response handler cho route hiện có

Khi cần thay thế handler của một URI đã tồn tại, thực hiện theo thứ tự:

1. Xác định đúng URI sau khi ghép API base path, repository path và suffix của resource.
2. Xác định HTTP method cần thay thế, ví dụ chỉ GET hoặc chỉ DELETE.
3. Tạo `@RepositoryRestController` vì route thuộc URI space của repository.
4. Khai báo mapping cụ thể cho đúng URI và method.
5. Nếu route đến từ một query method được export tự động, tắt export finder đó bằng `@RestResource(exported = false)`.
6. Nếu thay thế CRUD operation, cấu hình exposure của repository để method mặc định không còn được công bố theo chính sách mong muốn.
7. Kiểm thử route thực tế để xác nhận custom handler được gọi và các method khác vẫn có hành vi dự kiến.

Không nên tắt toàn bộ repository chỉ để thay một search method. `@RepositoryRestResource(exported = false)` ẩn cả repository resource; chỉ dùng khi chủ đích là ngừng export toàn bộ repository và ứng dụng tự chịu trách nhiệm cung cấp API thay thế.

Với CRUD operation, `RepositoryRestConfiguration.getExposureConfiguration()` cho phép cấu hình các HTTP method được export ở collection hoặc item exposure. Hãy giới hạn đúng domain type và đúng loại resource cần thay thế. Sau đó kiểm tra lại bằng HTTP request, vì việc disable một method mặc định và việc đăng ký custom handler là hai cấu hình riêng.

Không để một finder mặc định và một custom controller cùng tranh quyền sở hữu cùng một route nếu không có lý do rõ ràng. Nếu hai handler cùng được đăng ký trong một mapping context, ứng dụng có thể báo ambiguous mapping khi khởi động hoặc chọn handler khác dự định.

## 6. Phân biệt mở rộng endpoint và thay thế endpoint

Không phải mọi tùy chỉnh đều cần thay handler mặc định.

| Nhu cầu | Cơ chế phù hợp |
|---|---|
| Chuẩn hóa entity trước khi lưu | Repository event handler |
| Kiểm tra dữ liệu trước khi ghi | Validator hoặc event handler phù hợp |
| Thêm một search endpoint mới | Query method hoặc `@RepositoryRestController` với path riêng |
| Thay response của một search route | Ẩn finder mặc định rồi đăng ký custom handler cùng path |
| Thêm metadata hoặc endpoint tổng hợp dưới base path | `@BasePathAwareController` |
| Thay đổi exposure HTTP method | `RepositoryRestConfigurer` và exposure configuration |
| Thay đổi JSON representation | Projection, excerpt, Jackson customization |
| Thay đổi truy vấn hoặc hành vi repository dùng chung | Repository fragment hoặc custom repository implementation |
| Xây dựng API hoàn toàn độc lập | `@RestController` với URI prefix riêng |

Dùng event handler khi cần hook vào lifecycle nhưng vẫn muốn Spring Data REST giữ nguyên request mapping và response flow. Dùng custom controller khi cần kiểm soát request/response, status code, header hoặc cấu trúc representation.

## 7. Trả representation đúng kiểu hypermedia

Custom controller thuộc Spring Data REST thường nên trả `ResponseEntity` và các model Spring HATEOAS.

Ví dụ collection:

~~~java
@RepositoryRestController
public class ProductSummaryController {

    private final ProductRepository repository;

    public ProductSummaryController(ProductRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/products/search/featured")
    public ResponseEntity<CollectionModel<EntityModel<Product>>> featured() {

        List<EntityModel<Product>> items = repository.findFeatured()
            .stream()
            .map(EntityModel::of)
            .toList();

        CollectionModel<EntityModel<Product>> model =
            CollectionModel.of(items);

        model.add(linkTo(methodOn(ProductSummaryController.class)
            .featured()).withSelfRel());

        return ResponseEntity.ok(model);
    }
}
~~~

Các kiểu model thường dùng:

- `EntityModel<T>`: một entity hoặc DTO cùng các link.
- `CollectionModel<T>`: một tập phần tử cùng các link ở cấp collection.
- `RepresentationModel<T>`: base abstraction cho representation có link.

Nếu trả DTO hoặc object trực tiếp từ controller được đánh dấu `@RepositoryRestController`, cần bảo đảm return value được ghi ra response. Có thể dùng `ResponseEntity` hoặc `@ResponseBody` cho method phù hợp; `@RepositoryRestController` không đồng nghĩa với `@RestController`.

Không nên trả entity thô cho mọi trường hợp nếu API cần kiểm soát field, link, projection hoặc tránh lazy-loading ngoài ý muốn. Hãy chọn representation theo hợp đồng API mà client cần.

## 8. Base path và đường dẫn mapping

Custom controller của Spring Data REST sử dụng API base path từ `RepositoryRestConfiguration.setBasePath(...)`. Path khai báo trên method được ghép với base path đó.

Ví dụ:

~~~java
config.setBasePath("/api");
~~~

~~~java
@RepositoryRestController
public class InventoryController {

    @GetMapping("/inventory/summary")
    public ResponseEntity<?> summary() {
        return ResponseEntity.ok(Map.of("count", 12));
    }
}
~~~

URL thực tế là `/api/inventory/summary`.

Đối với route nằm trong repository namespace, dùng path đầy đủ tương đối với base path, ví dụ `/orders/search/by-status`. Không tự thêm `/api` vào mapping method nếu base path đã được cấu hình là `/api`, vì có thể tạo URL lặp prefix.

Khi có nhiều base path hoặc servlet context path, phân biệt chúng:

- Servlet context path thuộc cấu hình triển khai ứng dụng.
- Spring Data REST base path thuộc API exporter.
- Repository path thuộc annotation hoặc resource mapping của repository.
- Method mapping thuộc custom controller.

Ghi rõ từng phần trong tài liệu API và kiểm tra URL cuối cùng bằng integration test.

## 9. CORS, lazy loading và bảo mật của custom handler

Một lợi ích của `@RepositoryRestController` là handler được tích hợp với một số cấu hình của repository:

- CORS được áp dụng theo repository tương ứng với path.
- JPA `OpenEntityManagerInViewInterceptor` hỗ trợ đọc các property lazy trong request.
- Message converter và exception handling của Spring Data REST được sử dụng.

Dù vậy, custom handler vẫn cần tuân thủ security policy của ứng dụng. Dùng Spring Security để xác thực và phân quyền; không coi việc một endpoint nằm trong repository namespace là đã được bảo vệ tự động.

Nếu handler gọi repository method có `@PreAuthorize`, method security tiếp tục được áp dụng qua repository proxy. Nếu handler trả dữ liệu tổng hợp, kiểm tra quyền trên từng tập dữ liệu và từng thao tác theo nghiệp vụ.

Với `@BasePathAwareController` hoặc controller MVC thông thường, kiểm tra riêng CORS, serialization, exception mapping và security vì các tích hợp dành cho repository-specific handler có thể không áp dụng theo cùng cách.

## 10. Phát hiện mapping conflict

Khi ứng dụng khởi động, Spring MVC đăng ký request mapping từ các controller. Nếu hai method trong cùng mapping context có điều kiện giống nhau đến mức không thể phân biệt, Spring có thể báo lỗi ambiguous mapping.

Các dấu hiệu cần chú ý:

- Log khởi động báo hai handler cùng map một path và HTTP method.
- Request trả về response từ controller mặc định thay vì custom controller.
- Custom route trả 404 vì controller không nằm trong mapping context phù hợp.
- GET hoạt động nhưng POST/PUT/DELETE bị handler khác nhận.
- API base path bị lặp hoặc thiếu.
- Một route chỉ hoạt động khi repository bị ẩn, nhưng mất tích hợp CORS hoặc message converter mong muốn.

Cách xử lý:

1. Đọc log mapping khi ứng dụng khởi động và xác định hai handler cụ thể.
2. So sánh path, HTTP method, request parameter condition, consumes và produces.
3. Xác định controller có đúng annotation cho URI space hay không.
4. Kiểm tra finder/repository có đang export route mặc định không.
5. Tắt export route mặc định khi custom handler thay thế đúng route đó.
6. Chạy lại integration test cho custom route và các route lân cận.

Không dùng thứ tự khai báo method trong source code để giải quyết conflict. Không chỉnh sửa internal HandlerMapping order như một cách chữa mặc định; điều đó làm route phụ thuộc vào chi tiết triển khai của framework.

## 11. Kiểm thử custom handler bằng MockMvc

Nên kiểm thử cả route được thay thế và các route repository còn lại.

Ví dụ:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderSearchControllerTests {

    @Autowired
    MockMvc mvc;

    @Test
    void customSearchHandlerReturnsCollection() throws Exception {
        mvc.perform(get("/orders/search/by-status")
                .param("status", "OPEN")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaTypes.HAL_JSON
            ));
    }

    @Test
    void repositoryCollectionStillWorks() throws Exception {
        mvc.perform(get("/orders")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk());
    }
}
~~~

Đây là khung kiểm thử; điều chỉnh media type theo representation thực tế của controller. Nếu controller trả JSON thuần thay vì HAL, kiểm tra `application/json` và cấu trúc DTO tương ứng.

Các trường hợp nên kiểm tra:

- Custom handler thực sự được gọi cho đúng URI và HTTP method.
- Finder mặc định đã bị ẩn nếu đang thay thế finder đó.
- Search link HAL phản ánh đúng trạng thái export.
- Collection và item resource không liên quan vẫn hoạt động.
- Base path được ghép đúng.
- Response có status, headers và content type đúng.
- CORS policy của repository được áp dụng nếu dùng `@RepositoryRestController`.
- Security vẫn chặn user không có quyền.
- Không có ambiguous mapping khi khởi động.

Có thể dùng một mock service hoặc spy để xác nhận custom handler đã gọi đúng logic. Tuy nhiên, integration test cần đi qua MockMvc và Spring MVC mapping thực tế để phát hiện xung đột route; chỉ gọi method Java trực tiếp không kiểm tra được mapping.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể gặp | Cách xử lý |
|---|---|---|
| Custom `@RestController` không nhận request dưới repository path | Spring Data REST sở hữu URI space của repository | Dùng `@RepositoryRestController` nếu cần tích hợp với repository |
| Custom controller không được chọn | Annotation hoặc mapping context không phù hợp | Kiểm tra `@RepositoryRestController`, base path và repository path |
| Ứng dụng báo ambiguous mapping | Default finder và custom handler cùng đăng ký một route | Ẩn finder mặc định bằng `@RestResource(exported = false)` khi thay thế |
| Custom endpoint thiếu prefix API | Nhầm base path với method mapping | Dùng path tương đối với base path, không lặp prefix |
| Response object không được serialize như mong muốn | Method thiếu response body semantics hoặc trả kiểu không phù hợp | Dùng `ResponseEntity` hoặc `@ResponseBody` |
| CORS khác với repository mặc định | Dùng controller nằm ngoài SDR handler mapping | Dùng `@RepositoryRestController` hoặc cấu hình CORS riêng |
| Lazy property lỗi sau khi trả response | Custom handler không nhận JPA OpenEntityManagerInView integration | Dùng repository-aware controller hoặc tải dữ liệu trong transaction rõ ràng |
| Tắt toàn bộ repository làm mất các CRUD route | Dùng `@RepositoryRestResource(exported = false)` quá rộng | Chỉ tắt finder/method cần thay hoặc thiết kế API thay thế đầy đủ |
| Custom GET hoạt động nhưng DELETE vẫn mặc định | Chỉ thay một HTTP method | Cấu hình riêng từng method/exposure cần thay |
| Test không phát hiện conflict | Chỉ gọi controller method trực tiếp | Dùng MockMvc để kiểm tra routing thực tế |

## 13. Checklist giải quyết mapping và thay handler

- Liệt kê collection, item, search URI và API base path đang được export.
- Xác định route và HTTP method cần mở rộng hoặc thay thế.
- Dùng `@RepositoryRestController` cho handler nằm trong repository URI space.
- Dùng `@BasePathAwareController` cho endpoint tùy chỉnh dưới base path nhưng không gắn với repository cụ thể.
- Dùng `@RestController` với prefix độc lập cho API MVC ngoài Spring Data REST.
- Nếu thay finder mặc định, đặt `@RestResource(exported = false)` trên finder đó.
- Nếu thay CRUD method, điều chỉnh exposure đúng resource và HTTP method.
- Không tắt cả repository khi chỉ cần thay một route.
- Dùng `ResponseEntity`, `EntityModel` và `CollectionModel` cho response phù hợp.
- Không tự thêm base path hai lần.
- Kiểm tra CORS, JPA lazy loading và Spring Security của custom handler.
- Đọc log mapping và chạy MockMvc test cho route mới cùng route lân cận.
- Không sửa thứ tự HandlerMapping nội bộ để xử lý conflict thông thường.

## Kết luận

Xung đột mapping trong Spring Data REST xuất hiện khi custom controller và endpoint được sinh từ repository cùng cạnh tranh một URI hoặc khi controller được đặt sai mapping context. `@RepositoryRestController` là lựa chọn cho handler nằm trong URI space của repository và cần các tích hợp REST exporter; `@BasePathAwareController` phù hợp với endpoint tùy chỉnh dưới base path nhưng không gắn với entity; controller MVC thông thường nên dùng prefix độc lập. Khi thay finder mặc định, ẩn finder bằng `@RestResource(exported = false)` rồi map custom handler vào route có chủ đích. Với CRUD, điều chỉnh exposure đúng method. Luôn kiểm tra base path, log mapping, response representation và các route còn lại bằng integration test.

## Tài liệu tham khảo

- Spring Data REST – Overriding Spring Data REST Response Handlers: https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr-response-handlers.html
- Spring Data REST – RepositoryRestController API: https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/webmvc/RepositoryRestController.html
- Spring Data REST – Adding Spring Data REST to an Existing Spring MVC Application and RepositoryRestHandlerMapping: https://docs.spring.io/spring-data/rest/reference/customizing/adding-sdr-to-spring-mvc-app.html
- Spring Data REST – Customizing Spring Data REST and supported HTTP methods: https://docs.spring.io/spring-data/rest/reference/customizing/customizing-sdr.html
