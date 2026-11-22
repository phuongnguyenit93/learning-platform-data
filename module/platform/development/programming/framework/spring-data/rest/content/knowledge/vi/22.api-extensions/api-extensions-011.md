# Giữ nguyên phân trang, projection, header và bảo mật khi tự xử lý endpoint

## Mục tiêu

Khi cần thêm một endpoint tùy chỉnh vào ứng dụng Spring Data REST, ta có thể muốn truy vấn hoặc kết hợp dữ liệu theo cách mà repository resource mặc định không đáp ứng. Tuy nhiên, custom endpoint vẫn cần giữ các contract mà client đang dựa vào:

- **Phân trang:** nhận `page`, `size`, `sort` và trả metadata/link điều hướng nhất quán.
- **Projection:** chỉ trả representation phù hợp với use case, không vô tình lộ toàn bộ entity.
- **HTTP headers:** giữ content type, Location, ETag, Cache-Control và các header liên quan khi cần.
- **Bảo mật:** xác thực và phân quyền trên endpoint tùy chỉnh, kể cả quyền trên từng resource hoặc tenant.

Một endpoint tự viết không tự động kế thừa mọi hành vi của repository resource. Hãy chủ động thiết kế và kiểm tra từng phần của contract.

## 1. Chọn đúng loại controller

Spring Data REST cung cấp `@RepositoryRestController` cho controller tùy chỉnh hoạt động dưới base path của Spring Data REST.

Ví dụ nếu base path là `/api`, controller có thể cung cấp endpoint `/api/people/active`:

~~~java
@RepositoryRestController
public class PeopleCustomController {

    @GetMapping("/people/active")
    @ResponseBody
    public String activePeople() {
        return "custom response";
    }
}
~~~

`@RepositoryRestController` giúp controller tham gia cấu hình web và message converter của Spring Data REST. Method cần khai báo mapping rõ ràng; dùng `@ResponseBody` hoặc trả về `ResponseEntity` để xác định response body.

Một `@RestController` thông thường cũng có thể dùng cho API riêng. Khi chọn controller, hãy xác định endpoint có thuộc base path/representation conventions của Spring Data REST hay là một API độc lập. Tránh tạo hai endpoint trùng path hoặc vô tình bypass các quy tắc bảo mật đã cấu hình.

## 2. Giữ phân trang bằng Pageable và Page

Không nên tải toàn bộ dữ liệu rồi tự cắt danh sách bằng `subList`. Cách đó làm tăng bộ nhớ, bỏ qua khả năng phân trang của datastore và dễ tạo metadata sai.

Hãy nhận `Pageable` từ request và để repository thực hiện truy vấn theo trang:

~~~java
public interface PersonRepository extends JpaRepository<Person, Long> {

    Page<Person> findByActiveTrue(Pageable pageable);
}
~~~

Custom endpoint:

~~~java
@RepositoryRestController
public class PeopleCustomController {

    private final PersonRepository repository;

    public PeopleCustomController(PersonRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/people/active")
    @ResponseBody
    public Page<Person> activePeople(Pageable pageable) {
        return repository.findByActiveTrue(pageable);
    }
}
~~~

Spring Data web support ánh xạ query parameters vào Pageable:

~~~http
GET /api/people/active?page=0&size=20&sort=lastName,asc
~~~

- `page` bắt đầu từ 0.
- `size` là số phần tử tối đa trong trang.
- `sort` xác định thuộc tính và chiều sắp xếp.
- `Page<T>` giữ content, page number, page size, total elements và total pages.

Khi trả về API cho client, cần chọn representation phù hợp. Với API HAL, thường dùng Spring HATEOAS để tạo `PagedModel` và các link điều hướng.

## 3. Trả PagedModel và link điều hướng HAL

Spring HATEOAS cung cấp `PagedResourcesAssembler` để chuyển `Page<T>` thành `PagedModel` có metadata và navigation links.

Ví dụ minh họa:

~~~java
@RepositoryRestController
public class PeopleCustomController {

    private final PersonRepository repository;
    private final PagedResourcesAssembler<Person> pagedAssembler;

    public PeopleCustomController(
            PersonRepository repository,
            PagedResourcesAssembler<Person> pagedAssembler) {
        this.repository = repository;
        this.pagedAssembler = pagedAssembler;
    }

    @GetMapping("/people/active")
    @ResponseBody
    public PagedModel<EntityModel<Person>> activePeople(
            Pageable pageable) {

        Page<Person> page = repository.findByActiveTrue(pageable);
        return pagedAssembler.toModel(page);
    }
}
~~~

PagedModel có thể chứa:

- `_embedded`: các item trong trang hiện tại.
- `_links.self`: link tới trang hiện tại.
- `_links.first`, `prev`, `next`, `last`: link điều hướng nếu có.
- `page.size`, `page.totalElements`, `page.totalPages`, `page.number`: metadata trang.

Hình dạng chính xác của link phụ thuộc request hiện tại, cấu hình HATEOAS và assembler. Nếu cần item links hoặc representation tùy chỉnh, truyền một `RepresentationModelAssembler` phù hợp cho `toModel`.

Không tự tạo `totalPages` từ số item hiện có trong trang. Hãy dùng metadata do Page/repository trả về; nếu repository trả `Slice<T>` thì không có tổng số trang và tổng số phần tử như Page.

## 4. Giữ sort ổn định

Khi phân trang, các bản ghi cần có thứ tự xác định. Nếu sort key có thể trùng nhau, hãy thêm một thuộc tính duy nhất làm tiêu chí cuối.

Ví dụ:

~~~http
GET /api/people/active?page=0&size=20&sort=lastName,asc&sort=id,asc
~~~

Nếu chỉ sort theo `lastName`, nhiều Person cùng họ có thể đổi vị trí giữa các request. Thứ tự không ổn định có thể khiến client thấy item lặp hoặc bị bỏ qua khi duyệt trang, nhất là khi dữ liệu thay đổi.

Không cho phép client sort tùy ý trên mọi thuộc tính nội bộ. Hãy giới hạn sort properties theo API contract và domain model. Với truy vấn phức tạp, có thể xây dựng Sort allowlist hoặc map key public sang property được phép.

## 5. Projection không tự áp dụng cho custom endpoint

Spring Data REST hỗ trợ projection trên repository resources. Ví dụ client có thể yêu cầu:

~~~http
GET /api/people/42?projection=summary
~~~

Hoặc collection resource có thể dùng excerpt projection đã cấu hình. Nhưng custom controller không tự động áp dụng cùng cơ chế projection chỉ vì URL có query parameter `projection`.

Nếu custom endpoint trả entity trực tiếp, Jackson/HATEOAS có thể serialize các thuộc tính theo cấu hình hiện tại. Điều này có thể làm response khác contract của repository endpoint hoặc vô tình lộ field không nên công khai.

Có ba cách thường dùng:

1. Trả interface-based projection từ repository.
2. Map entity sang DTO/response model riêng.
3. Dùng `RepresentationModelAssembler` để tạo representation và link theo contract mong muốn.

Ví dụ interface projection:

~~~java
public interface PersonSummary {

    Long getId();

    String getFirstName();

    String getLastName();
}
~~~

Repository trả Page của projection:

~~~java
public interface PersonRepository extends JpaRepository<Person, Long> {

    Page<PersonSummary> findByActiveTrue(Pageable pageable);
}
~~~

Custom endpoint dùng projection đó:

~~~java
@GetMapping("/people/active")
@ResponseBody
public Page<PersonSummary> activePeople(Pageable pageable) {
    return repository.findByActiveTrue(pageable);
}
~~~

Đây là ví dụ về kiểu dữ liệu trả về. Nếu cần HAL pagination links, kết hợp `Page<PersonSummary>` với `PagedResourcesAssembler<PersonSummary>` và assembler phù hợp.

### Nếu hỗ trợ tham số projection động

Nếu custom endpoint có query parameter `projection`, hãy tự định nghĩa contract:

- Chỉ chấp nhận tên projection nằm trong allowlist.
- Map mỗi tên sang DTO/projection cụ thể.
- Trả lỗi rõ ràng khi tên không hỗ trợ.
- Không nhận class name tùy ý từ client để reflection hoặc instantiate type.
- Bảo đảm mỗi projection không làm lộ field ngoài quyền đọc của principal.

Ví dụ:

~~~java
switch (projection) {
    case "summary" -> return summaryView(pageable);
    case "contact" -> return contactView(pageable);
    default -> throw new ResponseStatusException(
        HttpStatus.BAD_REQUEST,
        "Unsupported projection"
    );
}
~~~

Projection chỉ là hình dạng response. Nó không thay thế authorization hoặc write validation.

## 6. Dùng DTO khi custom endpoint có contract riêng

DTO phù hợp khi endpoint cần tổng hợp dữ liệu, đổi tên field hoặc chỉ công khai một tập field cụ thể.

Ví dụ:

~~~java
public record PersonSummaryResponse(
        Long id,
        String displayName,
        boolean active
) {
}
~~~

Service hoặc mapper chuyển domain object thành DTO:

~~~java
private PersonSummaryResponse toSummary(Person person) {
    return new PersonSummaryResponse(
        person.getId(),
        person.getFirstName() + " " + person.getLastName(),
        person.isActive()
    );
}
~~~

Đối với phân trang, giữ nguyên metadata Page khi map content:

~~~java
Page<PersonSummaryResponse> responsePage =
    personPage.map(this::toSummary);
~~~

`Page.map` giữ page information và biến đổi từng phần tử. Sau đó có thể dùng assembler phù hợp để tạo PagedModel. Tránh tự dựng một Page mới với total count giả định hoặc làm mất sort/page metadata.

DTO response cũng giúp tách API contract khỏi entity persistence. Nếu domain model thay đổi, custom endpoint có thể giữ response shape ổn định bằng cách chỉ sửa mapper.

## 7. Giữ HTTP status và headers

Khi custom controller trả response, dùng `ResponseEntity` để kiểm soát status, body và headers.

Ví dụ GET HAL response:

~~~java
@GetMapping("/people/active")
public ResponseEntity<PagedModel<EntityModel<PersonSummary>>> activePeople(
        Pageable pageable) {

    Page<PersonSummary> page = repository.findByActiveTrue(pageable);
    PagedModel<EntityModel<PersonSummary>> body =
        pagedAssembler.toModel(page);

    return ResponseEntity.ok()
        .contentType(MediaTypes.HAL_JSON)
        .body(body);
}
~~~

Một số header có ý nghĩa đặc biệt:

| Header | Vai trò | Khi cần giữ |
|---|---|---|
| `Content-Type` | Mô tả media type của response | HAL JSON, JSON hoặc media type khác |
| `Location` | URI của resource vừa tạo hoặc được chuyển hướng | POST tạo resource |
| `ETag` | Validator cho cache hoặc conditional request | Khi API hỗ trợ optimistic concurrency |
| `Last-Modified` | Thời điểm representation/resource thay đổi | Khi API hỗ trợ conditional GET |
| `Cache-Control` | Chính sách cache | Dữ liệu public, private hoặc nhạy cảm |
| `Vary` | Header request ảnh hưởng representation | Content negotiation hoặc response phụ thuộc header |
| `Link` | Quan hệ hypermedia bổ sung | Khi API dùng link header |

### POST cần Location

Khi custom endpoint tạo resource, response nên cung cấp URI resource bằng `Location`:

~~~java
URI location = linkTo(methodOn(PersonController.class)
        .getPerson(saved.getId()))
        .toUri();

return ResponseEntity.created(location)
        .body(response);
~~~

Ví dụ dùng Spring HATEOAS link builder; thay controller và method bằng route thực tế của ứng dụng. Không hard-code path nếu base path hoặc resource mapping có thể thay đổi.

### ETag và conditional request

Nếu endpoint hỗ trợ cập nhật có điều kiện, hãy trả ETag phù hợp và kiểm tra `If-Match` trước khi ghi. ETag phải gắn với đúng representation/version và được server tạo từ nguồn đáng tin cậy.

Không tự tạo ETag tùy tiện từ một field không phản ánh toàn bộ resource. Không bỏ qua `If-Match` chỉ vì custom endpoint đang dùng DTO. Nếu dùng `@Version` ở persistence layer, bảo đảm custom update path vẫn đi qua version check và xử lý optimistic locking.

### Cache-Control và dữ liệu nhạy cảm

Không copy chính sách cache từ endpoint public sang endpoint trả dữ liệu theo user. Với dữ liệu cá nhân hoặc nhạy cảm, xem xét `Cache-Control: no-store` hoặc chính sách private phù hợp.

Nếu response phụ thuộc vào `Accept`, `Accept-Language` hoặc header khác, cân nhắc `Vary` đúng cách. Tránh cache response theo một key không phân biệt principal khi nội dung khác nhau theo quyền.

## 8. Bảo mật custom endpoint

Custom endpoint vẫn nằm trong request pipeline của Spring Security nếu được triển khai trong cùng ứng dụng, nhưng các rule phải bao phủ đúng path và HTTP method.

Ví dụ URL-level security:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/people/active")
                .hasAuthority("people:read")
            .requestMatchers(HttpMethod.POST, "/api/people/import")
                .hasAuthority("people:import")
            .anyRequest().authenticated()
        )
        .build();
}
~~~

Đây chỉ là ví dụ matcher. Nếu dùng `@RepositoryRestController`, xác nhận path sau khi áp dụng Spring Data REST base path và thứ tự các SecurityFilterChain trong ứng dụng. Một matcher sai có thể khiến endpoint rơi vào rule tổng quát hoặc rule không mong muốn.

### Method security

Có thể đặt quyền ở service hoặc controller method:

~~~java
@EnableMethodSecurity
@Configuration
public class MethodSecurityConfiguration {
}
~~~

~~~java
@PreAuthorize("hasAuthority('people:read')")
public Page<PersonSummary> findActivePeople(Pageable pageable) {
    return repository.findByActiveTrue(pageable);
}
~~~

`@PreAuthorize` chỉ có hiệu lực khi method security được bật và method được gọi qua Spring proxy tương ứng. Không gọi self-invocation rồi giả định annotation chắc chắn được áp dụng.

### Kiểm tra quyền trên từng resource

Quyền truy cập có thể phụ thuộc owner, tenant hoặc trạng thái:

~~~java
@PreAuthorize("@personAccess.canRead(authentication, #personId)")
public PersonSummaryResponse getPerson(Long personId) {
    // Load and return authorized representation.
    return null;
}
~~~

Method security giúp kiểm tra policy theo resource. Cần triển khai bean `personAccess` với logic xác thực ownership/tenant thực tế. Không dựa vào việc ẩn link, projection hoặc nút giao diện để bảo vệ endpoint.

### Không để custom endpoint bypass policy

Nếu repository endpoint có security rule riêng, custom endpoint phải được bổ sung rule tương đương. Kiểm tra cả:

- GET collection và GET item.
- POST, PUT, PATCH và DELETE.
- Endpoint tìm kiếm/tổng hợp.
- Endpoint export/import.
- Các association hoặc action endpoint.
- Các request theo tenant hoặc owner.

Nếu custom endpoint gọi service dùng chung, đặt authorization và invariant quan trọng ở service/domain boundary để các entry point khác cũng được bảo vệ.

## 9. Giữ hypermedia links nhất quán

Spring Data REST khuyến khích client khám phá URI qua link thay vì tự ghép path. Custom endpoint nên trả link rõ ràng nếu client cần theo dõi resource hoặc chuyển tiếp tiếp theo.

Với PagedModel, link `self`, `next`, `prev` cần giữ đúng query parameters liên quan:

- Page hiện tại.
- Page size.
- Sort order.
- Filter hoặc search criteria.
- Các tham số khác ảnh hưởng tập kết quả.

Nếu client chuyển từ `page=0` sang `page=1`, filter `active=true` và sort phải được giữ nguyên. Nếu link chỉ mang page/size mà bỏ filter, trang tiếp theo có thể trả một tập dữ liệu khác.

Không hard-code base URL trong assembler nếu ứng dụng chạy sau reverse proxy hoặc có context path. Dùng link builder/HATEOAS infrastructure và kiểm tra forwarded headers theo cấu hình triển khai.

## 10. Content negotiation và response format

Custom endpoint cần xử lý `Accept` phù hợp với API contract:

~~~http
GET /api/people/active
Accept: application/hal+json
~~~

Nếu endpoint chỉ trả HAL JSON, đặt content type tương ứng. Nếu hỗ trợ nhiều media type, cấu hình converter và mapping rõ ràng. Tránh trả JSON thường từ endpoint mà client kỳ vọng HAL links hoặc PagedModel.

Request body cũng cần đúng `Content-Type`. Khi nhận DTO, validate body và trả lỗi theo cùng quy ước error response của API.

Không giả định một `@RepositoryRestController` tự động làm mọi response thành HAL. Kiểu trả về, annotations, message converters và cấu hình của Spring Data REST quyết định cách serialize.

## 11. Quy trình triển khai một custom endpoint

Khi thêm endpoint, thực hiện theo trình tự:

1. Xác định endpoint thuộc Spring Data REST base path hay API riêng.
2. Chọn `@RepositoryRestController` hoặc controller phù hợp.
3. Xác định response contract: entity, projection, DTO hay resource model.
4. Nhận `Pageable` và để repository thực hiện phân trang.
5. Giữ Page metadata; dùng PagedResourcesAssembler khi cần HAL navigation.
6. Chỉ công khai các field phù hợp; không dựa vào projection query parameter tự động.
7. Thiết lập status, Content-Type, Location, ETag và Cache-Control khi cần.
8. Thêm URL-level và method/resource-level authorization.
9. Giữ filter/sort/page parameters trong hypermedia links.
10. Viết integration tests cho paging, projection, headers và security.

## 12. Kiểm thử contract của custom endpoint

Nên kiểm tra từng khía cạnh độc lập:

- **Paging:** `page`, `size`, `sort` được bind đúng; totalElements/totalPages và links chính xác.
- **Stable ordering:** hai item có cùng sort key vẫn có thứ tự xác định nhờ tie-breaker.
- **Projection/DTO:** response chỉ chứa field được công bố; field nội bộ không xuất hiện.
- **Content negotiation:** HAL client nhận đúng media type và cấu trúc.
- **Headers:** POST có Location; ETag/Cache-Control/Vary có đúng contract.
- **Conditional write:** If-Match cũ bị từ chối nếu endpoint hỗ trợ optimistic concurrency.
- **Authorization:** user thiếu quyền bị từ chối khi gọi URL trực tiếp.
- **Resource policy:** user không thể truy cập item thuộc tenant/owner khác.
- **Error response:** validation và lỗi nghiệp vụ giữ status/representation nhất quán.

Dùng MockMvc hoặc WebTestClient tùy stack. Kiểm tra response HTTP thực tế thay vì chỉ unit test method controller.

## 13. Những lỗi thường gặp

- **Custom endpoint trả List rồi tự cắt trang.** Có thể gây tải dữ liệu lớn và mất metadata; dùng Pageable và Page.
- **Trả Page nhưng client cần HAL navigation.** Dùng PagedModel/PagedResourcesAssembler và kiểm tra links.
- **Có query parameter projection nên nghĩ projection tự chạy.** Custom controller cần tự chọn projection/DTO và mapping.
- **Serialize trực tiếp entity.** Có thể làm lộ field hoặc tạo response contract không ổn định; dùng projection/DTO khi cần.
- **Chỉ giữ body mà bỏ headers.** Có thể làm mất Location, ETag hoặc cache semantics.
- **ETag được tạo tùy tiện.** Validator phải phản ánh version/representation và conditional write phải được kiểm tra.
- **Ẩn link để bảo vệ endpoint.** Client có thể gọi URL trực tiếp; enforce bằng Spring Security.
- **Chỉ kiểm tra quyền theo path.** Quyền trên từng bản ghi/tenant cần policy riêng.
- **Phân trang thiếu sort ổn định.** Có thể gây item lặp hoặc mất khi duyệt các trang.
- **Link next làm mất filter.** Trang tiếp theo có thể truy vấn tập dữ liệu khác.
- **Giả định @RepositoryRestController tự tạo HAL cho mọi kiểu trả về.** Kiểm tra converter, annotations và media type thực tế.

## 14. Ghi nhớ

- Custom endpoint cần chủ động giữ các contract mà repository resource mặc định cung cấp.
- Dùng Pageable và Page để truy vấn theo trang; dùng PagedModel/assembler khi cần HAL navigation.
- Sort nên ổn định và chỉ cho phép property đã công bố.
- Projection/excerpt của repository không tự động áp dụng cho custom controller; dùng projection/DTO rõ ràng.
- Dùng ResponseEntity để kiểm soát status và headers như Content-Type, Location, ETag và Cache-Control.
- Conditional write phải kiểm tra If-Match và version ở server.
- Bảo mật custom endpoint bằng URL rules, method security và kiểm tra quyền trên resource khi cần.
- Hypermedia links phải giữ page, size, sort và filter.
- Kiểm thử paging, representation, headers và security bằng HTTP integration tests.

## Tài liệu tham khảo

- [Spring Data REST Reference — Customizing and extending](https://docs.spring.io/spring-data/rest/reference/customizing-and-extending.html)
- [Spring Data REST Reference — Events and repository resources](https://docs.spring.io/spring-data/rest/reference/)
- [Spring HATEOAS Reference — Pagination](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring Security Reference — Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/index.html)
- [Spring Framework Reference — ResponseEntity and MVC controllers](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller.html)
