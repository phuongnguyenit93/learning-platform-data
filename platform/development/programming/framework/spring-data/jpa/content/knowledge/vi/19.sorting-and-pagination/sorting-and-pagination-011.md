# Tích hợp Pageable, Sort với Spring MVC và quy tắc cấu hình

## 1. Vì sao cần tích hợp Pageable và Sort ở tầng Web?

Spring Data JPA cung cấp `Pageable` và `Sort` để mô tả cách lấy dữ liệu theo trang và thứ tự. Ở tầng repository, ứng dụng có thể truyền một `Pageable` vào method để database chỉ trả về phần dữ liệu cần thiết.

Trong ứng dụng Spring MVC, client thường gửi các tham số trên URL, ví dụ:

```http
GET /api/customers?page=0&size=20&sort=name,asc
```

Spring Data Web hỗ trợ chuyển các tham số HTTP thành object `Pageable` và `Sort`. Controller nhận object đã được phân tích, sau đó truyền xuống service/repository. Nhờ vậy, controller không cần tự đọc từng query parameter rồi tạo `PageRequest` bằng tay.

Luồng tổng quát:

1. Client gửi page, size và sort trên HTTP request.
2. Spring MVC gọi argument resolver của Spring Data Web.
3. Resolver tạo `Pageable` và `Sort` từ tham số request, áp dụng default và giới hạn cấu hình.
4. Controller nhận `Pageable` như một method argument.
5. Service truyền yêu cầu phân trang xuống repository.
6. Spring Data JPA/JPA provider chuyển yêu cầu thành truy vấn có giới hạn hàng và thứ tự phù hợp database.
7. Controller trả content và metadata phân trang cho client.

Cần tách rõ hai trách nhiệm:
- Spring Data Web phân tích request và tạo `Pageable`/`Sort`.
- Spring Data JPA dùng các object đó để truy vấn database.

## 2. Cách Spring MVC nhận Pageable

### 2.1. Khai báo Pageable trong controller

Ví dụ controller:

```java
@RestController
@RequestMapping("/api/customers")
public class CustomerController {

    private final CustomerRepository repository;

    public CustomerController(CustomerRepository repository) {
        this.repository = repository;
    }

    @GetMapping
    public Page<CustomerSummary> search(Pageable pageable) {
        return repository.findAllProjectedBy(pageable);
    }
}
```

Khi Spring Data Web được cấu hình, tham số `Pageable` được tự động resolve từ query parameters. Controller không cần khai báo `@RequestParam` riêng cho page, size hoặc sort.

Ví dụ request:

```http
GET /api/customers?page=1&size=10&sort=name,asc
```

Theo mặc định phổ biến của Spring Data Web:
- `page` là số trang, bắt đầu từ 0.
- `size` là số phần tử tối đa trong trang.
- `sort` mô tả trường và hướng sắp xếp.
- Có thể truyền nhiều tham số `sort` để tạo thứ tự nhiều cấp.

Cấu hình có thể thay đổi tên parameter, prefix, delimiter, default page size và cách đánh số trang. Vì vậy hãy kiểm tra cấu hình ứng dụng thay vì giả định mọi dự án đều dùng giá trị mặc định.

### 2.2. Repository nhận Pageable

Repository có thể khai báo:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Page<Customer> findByStatus(
        CustomerStatus status,
        Pageable pageable
    );
}
```

Service:

```java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Page<Customer> findActiveCustomers(Pageable pageable) {
        return repository.findByStatus(
            CustomerStatus.ACTIVE,
            pageable
        );
    }
}
```

Controller:

```java
@GetMapping("/active")
public Page<Customer> activeCustomers(Pageable pageable) {
    return customerService.findActiveCustomers(pageable);
}
```

`Pageable` được truyền xuyên qua các tầng. Không cần chuyển thành page number và size rồi tạo lại object ở mỗi tầng nếu không có yêu cầu nghiệp vụ.

Nếu API trả DTO, repository có thể dùng projection hoặc service map kết quả sang DTO. Tránh trả entity trực tiếp nếu việc serialize có thể kích hoạt lazy loading hoặc làm lộ field nội bộ.

## 3. Các query parameter mặc định

### 3.1. page và size

Ví dụ:

```http
GET /api/orders?page=0&size=25
```

Tương ứng với yêu cầu lấy trang đầu tiên, tối đa 25 phần tử.

```http
GET /api/orders?page=2&size=25
```

Yêu cầu lấy trang thứ ba theo cách hiển thị cho người dùng nếu UI đếm từ 1; trong Spring Data, page index vẫn là 2. Offset được tính từ page index nhân page size.

Không nên để client gửi size tùy ý mà không giới hạn. Một request có size quá lớn có thể làm tăng bộ nhớ, thời gian truy vấn và payload response. Hãy đặt default và max page size phù hợp.

### 3.2. sort

Cú pháp thường dùng:

```http
GET /api/customers?sort=name,asc
GET /api/customers?sort=createdAt,desc
```

Phần đầu là property cần sắp xếp; phần thứ hai là direction `asc` hoặc `desc`.

Tên property trong `Sort` thường là thuộc tính Java của entity, ví dụ `createdAt`, không nhất thiết là tên cột database `created_at`. Với native query hoặc projection phức tạp, khả năng sort còn phụ thuộc query và phiên bản Spring Data JPA.

### 3.3. Sắp xếp nhiều trường

Có thể lặp lại parameter `sort`:

```http
GET /api/customers?sort=lastName,asc&sort=firstName,asc&sort=id,asc
```

Thứ tự ưu tiên là:
1. lastName tăng dần.
2. Nếu trùng lastName, sắp theo firstName tăng dần.
3. Nếu vẫn trùng, sắp theo id tăng dần.

Một thứ tự có khóa duy nhất làm tie-breaker giúp kết quả giữa các trang ổn định hơn.

Không gộp nhiều trường vào một chuỗi tùy ý nếu resolver của ứng dụng đang mong đợi một parameter cho mỗi order. Cú pháp request nên được công bố rõ trong API documentation.

## 4. Dùng default với @PageableDefault

### 4.1. Đặt kích thước và sort mặc định cho endpoint

Nếu client không gửi page/size/sort, controller có thể khai báo default:

```java
@GetMapping
public Page<CustomerSummary> list(
    @PageableDefault(
        page = 0,
        size = 20,
        sort = "createdAt",
        direction = Sort.Direction.DESC
    )
    Pageable pageable
) {
    return customerService.findCustomers(pageable);
}
```

Annotation `@PageableDefault` giúp định nghĩa default gắn với endpoint:
- `page`: trang mặc định.
- `size`: kích thước trang mặc định.
- `sort`: một hoặc nhiều property mặc định.
- `direction`: hướng mặc định cho sort được khai báo trong annotation.

Nếu client gửi parameter tương ứng, request có thể ghi đè default theo quy tắc của resolver. Cần kiểm thử hành vi của phiên bản Spring Data đang dùng.

### 4.2. Default sort nhiều trường bằng @SortDefault

Khi cần nhiều sort order với direction riêng, dùng `@SortDefault`:

```java
@GetMapping
public Page<CustomerSummary> list(
    @PageableDefault(size = 20)
    @SortDefault.SortDefaults({
        @SortDefault(
            sort = "lastName",
            direction = Sort.Direction.ASC
        ),
        @SortDefault(
            sort = "firstName",
            direction = Sort.Direction.ASC
        ),
        @SortDefault(
            sort = "id",
            direction = Sort.Direction.ASC
        )
    })
    Pageable pageable
) {
    return customerService.findCustomers(pageable);
}
```

Cách này biểu đạt thứ tự mặc định nhiều cấp rõ ràng hơn việc cố gắng gộp nhiều property vào một giá trị annotation.

Nếu đã có Sort từ request, resolver áp dụng sort theo request; default sort đóng vai trò dự phòng khi request không cung cấp sort. Hãy kiểm tra trường hợp client chỉ gửi một sort order để xác nhận hành vi mong muốn và bảo đảm tie-breaker vẫn được giữ nếu ứng dụng yêu cầu.

## 5. Dùng Sort độc lập trong controller

Không phải endpoint nào cũng cần phân trang. Có thể nhận `Sort` trực tiếp:

```java
@GetMapping("/export")
public List<CustomerSummary> export(
    @SortDefault(
        sort = "createdAt",
        direction = Sort.Direction.DESC
    )
    Sort sort
) {
    return customerService.exportCustomers(sort);
}
```

Repository:

```java
List<Customer> findByStatus(
    CustomerStatus status,
    Sort sort
);
```

Sort độc lập phù hợp khi tập kết quả được giới hạn theo cách khác hoặc use case không dùng Page. Tuy nhiên, không nên trả danh sách không giới hạn chỉ vì bỏ Pageable; export lớn cần streaming, chunk hoặc quy trình export chuyên biệt.

## 6. Cấu hình Spring Data Web

### 6.1. Spring Boot auto-configuration

Trong ứng dụng Spring Boot có Spring Data Web trên classpath, Spring Boot thường tự cấu hình hỗ trợ argument resolver cho `Pageable` và `Sort`. Các thuộc tính thường được đặt dưới prefix `spring.data.web.pageable` và `spring.data.web.sort`.

Ví dụ cấu hình:

```yaml
spring:
  data:
    web:
      pageable:
        default-page-size: 20
        max-page-size: 100
        page-parameter: page
        size-parameter: size
        one-indexed-parameters: false
      sort:
        sort-parameter: sort
```

Ý nghĩa:
- `default-page-size`: page size dùng khi request không chỉ định size và không có default cụ thể trên method.
- `max-page-size`: giới hạn kích thước tối đa resolver chấp nhận.
- `page-parameter`: tên query parameter cho số trang.
- `size-parameter`: tên query parameter cho page size.
- `one-indexed-parameters`: nếu bật, request page được hiểu theo cách đếm từ 1 ở tầng Web rồi chuyển về index nội bộ bắt đầu từ 0.
- `sort-parameter`: tên query parameter cho sort.

Tên property và khả năng cấu hình có thể thay đổi theo phiên bản Spring Boot. Hãy kiểm tra metadata/configuration reference của đúng phiên bản dự án. Nếu một property không được nhận diện, ứng dụng có thể khởi động mà không áp dụng giá trị bạn kỳ vọng.

### 6.2. Cấu hình Java bằng customizer

Khi cần tùy chỉnh resolver bằng Java, Spring Data Web cung cấp customizer interface. Ví dụ với Spring Data Commons:

```java
@Configuration
public class SpringDataWebConfiguration {

    @Bean
    PageableHandlerMethodArgumentResolverCustomizer pageableCustomizer() {
        return resolver -> {
            resolver.setMaxPageSize(100);
            resolver.setOneIndexedParameters(false);
        };
    }
}
```

Package của customizer trong các phiên bản Spring Data hiện hành là `org.springframework.data.web.config.PageableHandlerMethodArgumentResolverCustomizer`. Cần xác nhận import theo dependency thực tế.

Customizer hữu ích khi cần đặt giới hạn hoặc quy tắc không được biểu đạt qua application properties. Tránh vừa cấu hình cùng một giá trị trong YAML vừa ghi đè bằng customizer mà không có quy ước rõ ràng; điều đó khiến việc tìm nguồn cấu hình khó hơn.

### 6.3. @EnableSpringDataWebSupport trong ứng dụng không dùng Boot

Nếu ứng dụng Spring MVC không dùng Spring Boot auto-configuration, có thể đăng ký Spring Data Web support bằng:

```java
@Configuration
@EnableSpringDataWebSupport
public class WebConfiguration {
}
```

Annotation này đăng ký các thành phần hỗ trợ web của Spring Data, trong đó có resolver cho Pageable và Sort. Nếu ứng dụng đã được Boot auto-configure, không thêm cấu hình thủ công một cách máy móc; hãy tránh đăng ký resolver trùng lặp hoặc cấu hình mâu thuẫn.

## 7. Bảo vệ API khỏi page size quá lớn

### 7.1. Đặt giới hạn tối đa

Client có thể gửi:

```http
GET /api/customers?size=1000000
```

Nếu không giới hạn, request có thể yêu cầu quá nhiều dữ liệu, làm tăng:
- Số hàng database phải đọc và chuyển qua JDBC.
- Bộ nhớ heap dùng để tạo entity/DTO.
- Thời gian mapping và serialize.
- Kích thước response.
- Thời gian giữ connection và transaction.

Đặt `max-page-size` ở cấu hình web và chọn giá trị phù hợp với use case. Có thể đặt default page size thấp hơn max page size để API hoạt động hợp lý ngay cả khi client không truyền tham số.

### 7.2. Kiểm tra page và size

Resolver có thể chuẩn hóa hoặc giới hạn một số giá trị đầu vào tùy phiên bản. Tuy nhiên, API vẫn nên có hợp đồng rõ ràng cho page âm, size bằng 0, size âm hoặc giá trị vượt giới hạn.

Nếu cần trả lỗi validation thay vì tự clamp, có thể viết lớp adapter/validation riêng cho API. Đừng giả định mọi resolver đều phản hồi cùng một status code cho input sai.

### 7.3. Không để client điều khiển truy vấn không giới hạn

Ngay cả khi page size được giới hạn, client vẫn có thể yêu cầu page index rất lớn. Offset lớn có thể tốn kém. Với dataset lớn, cân nhắc keyset pagination hoặc endpoint cuộn dữ liệu thay vì cho phép offset vô hạn.

## 8. Sort từ request phải được kiểm soát

### 8.1. Chỉ cho phép các property đã công bố

Một request có thể chứa:

```http
GET /api/customers?sort=passwordHash,desc
```

Hoặc yêu cầu sort theo một association sâu không phù hợp. Sort không phải giá trị SQL parameter; Spring Data dùng property path để xây dựng order expression. Property không hợp lệ có thể gây lỗi query, và cho phép sort tùy ý có thể làm lộ cấu trúc domain hoặc tạo truy vấn nặng.

Nên định nghĩa allowlist cho từng endpoint, ví dụ:

```java
private static final Set<String> ALLOWED_SORTS = Set.of(
    "id",
    "name",
    "createdAt"
);
```

Sau đó kiểm tra sort nhận từ request trước khi chuyển xuống repository. Nếu không hợp lệ, trả lỗi 400 với thông báo dễ hiểu hoặc thay bằng sort mặc định theo hợp đồng API.

### 8.2. Map tên sort công khai sang property nội bộ

API có thể công bố `created` trong khi entity dùng `createdAt`. Hãy ánh xạ từ allowlist:

```java
private static final Map<String, String> SORT_FIELDS = Map.of(
    "name", "name",
    "created", "createdAt",
    "id", "id"
);
```

Service/controller adapter chỉ tạo `Sort.Order` từ giá trị đã được kiểm tra. Không nối trực tiếp raw query parameter vào chuỗi SQL hoặc JPQL.

Nếu query dùng native SQL, việc sort động có giới hạn phụ thuộc phiên bản Spring Data và query enhancer/parser. Với native query phức tạp, custom repository nên chọn column expression từ allowlist và ghép hướng sort đã validate; không cho phép client gửi tên cột SQL tùy ý.

### 8.3. Không phải property nào cũng sort được

Một số property:
- Là collection hoặc association có thể tạo join tốn kém.
- Không được chọn trong projection.
- Là computed/transient property không tồn tại trong query.
- Không tương thích với native SQL đang dùng.
- Có kiểu hoặc collation khiến thứ tự không phù hợp nghiệp vụ.

Chỉ công bố các trường sort có ý nghĩa và đã kiểm thử trên query thực tế.

## 9. Nhiều Pageable trong cùng controller

Một endpoint đôi khi cần hai danh sách độc lập, ví dụ trang khách hàng và trang đơn hàng:

```java
@GetMapping("/dashboard")
public DashboardResponse dashboard(
    @Qualifier("customers")
    Pageable customerPageable,
    @Qualifier("orders")
    Pageable orderPageable
) {
    Page<CustomerSummary> customers =
        customerService.findCustomers(customerPageable);

    Page<OrderSummary> orders =
        orderService.findOrders(orderPageable);

    return new DashboardResponse(customers, orders);
}
```

Dùng `@Qualifier` để phân biệt các tham số. Với delimiter mặc định là dấu gạch dưới, request có thể là:

```http
GET /api/dashboard?customers_page=0&customers_size=10&customers_sort=name,asc&orders_page=0&orders_size=5&orders_sort=createdAt,desc
```

Tên prefix và delimiter có thể được tùy chỉnh qua Spring Data Web configuration. Hãy ghi rõ quy ước trong API documentation; client cần biết tham số nào thuộc danh sách nào.

Nếu endpoint cần nhiều phân trang độc lập, cân nhắc tách thành nhiều endpoint khi response và tải dữ liệu quá lớn. Một request dashboard có thể kích hoạt nhiều query count và content cùng lúc.

## 10. Trả response phân trang cho client

### 10.1. Page object

Có thể trả trực tiếp Page từ controller:

```java
@GetMapping
public Page<CustomerSummary> list(Pageable pageable) {
    return customerService.findCustomers(pageable);
}
```

Spring sẽ serialize các thuộc tính Page theo cấu trúc phụ thuộc implementation. Tuy nhiên, không nên để client phụ thuộc trực tiếp vào mọi field nội bộ của Page implementation nếu API cần ổn định lâu dài.

### 10.2. Tạo response envelope riêng

Một response DTO giúp định nghĩa API contract:

```java
public record PageResponse<T>(
    List<T> content,
    int page,
    int size,
    long totalElements,
    int totalPages,
    boolean hasNext
) {
    public static <T> PageResponse<T> from(Page<T> source) {
        return new PageResponse<>(
            source.getContent(),
            source.getNumber(),
            source.getSize(),
            source.getTotalElements(),
            source.getTotalPages(),
            source.hasNext()
        );
    }
}
```

Controller:

```java
@GetMapping
public PageResponse<CustomerSummary> list(Pageable pageable) {
    Page<CustomerSummary> page =
        customerService.findCustomers(pageable);

    return PageResponse.from(page);
}
```

Response envelope tách API contract khỏi chi tiết serialize của Spring Data. Có thể bổ sung link next/previous hoặc sort hiện tại nếu client cần.

### 10.3. Phân biệt page index nội bộ và số trang hiển thị

Nếu resolver dùng `one-indexed-parameters=true`, request `page=1` có thể được chuyển thành page index nội bộ 0. Khi response trả `Page.getNumber()`, giá trị thường là index nội bộ bắt đầu từ 0.

Nếu API muốn trả số trang bắt đầu từ 1, cần chuyển đổi rõ trong response DTO. Không thay đổi ngầm giữa request và response vì client sẽ dễ gửi nhầm trang.

## 11. Sắp xếp ổn định và dữ liệu thay đổi

Phân trang dựa trên offset cần thứ tự xác định. Ví dụ:

```http
GET /api/orders?page=0&size=20&sort=createdAt,desc
```

Nếu nhiều order có cùng `createdAt`, database không bảo đảm thứ tự giữa các hàng có cùng giá trị. Khi chuyển trang, kết quả có thể bị lặp hoặc bỏ sót nếu thứ tự không ổn định hoặc dữ liệu thay đổi.

Nên thêm tie-breaker duy nhất:

```java
Sort sort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);
Pageable pageable = PageRequest.of(0, 20, sort);
```

Nếu dùng default sort, hãy đưa tie-breaker vào `@SortDefault` hoặc tạo sort mặc định trong resolver/service theo hợp đồng endpoint.

Với dữ liệu thay đổi liên tục, thứ tự ổn định vẫn không bảo đảm snapshot nhất quán qua nhiều HTTP request. Nếu use case cần duyệt toàn bộ dữ liệu không lặp, cân nhắc snapshot/version hoặc keyset pagination theo khóa sắp xếp.

## 12. Pageable với Page, Slice và List

Repository có thể trả về các kiểu khác nhau:

```java
Page<Customer> findByStatus(
    CustomerStatus status,
    Pageable pageable
);

Slice<Customer> findSliceByStatus(
    CustomerStatus status,
    Pageable pageable
);

List<Customer> findTop100ByStatusOrderByCreatedAtDesc(
    CustomerStatus status,
    Pageable pageable
);
```

Ý nghĩa:
- `Page<T>` cung cấp tổng số phần tử và số trang; thường cần count query.
- `Slice<T>` chỉ cần biết có phần tử tiếp theo hay không; có thể tránh count query.
- `List<T>` kết hợp Pageable có thể giới hạn content nhưng không cung cấp metadata tổng như Page.

Tên derived method và kiểu trả về cần khớp khả năng hỗ trợ của Spring Data JPA phiên bản dự án. Không dùng Page khi giao diện không cần tổng số trang, vì count query có thể tốn kém.

## 13. Kiểm thử tích hợp Pageable và Sort

### 13.1. Kiểm thử repository

Repository test xác nhận database thực sự áp dụng page và sort:

```java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void appliesPageAndSort() {
        repository.saveAll(List.of(
            new Customer("Minh"),
            new Customer("An"),
            new Customer("Binh")
        ));

        Pageable pageable = PageRequest.of(
            0,
            2,
            Sort.by("name").ascending()
        );

        Page<Customer> page =
            repository.findAll(pageable);

        assertThat(page.getContent())
            .extracting(Customer::getName)
            .containsExactly("An", "Binh");

        assertThat(page.getTotalElements()).isEqualTo(3);
        assertThat(page.hasNext()).isTrue();
    }
}
```

Ví dụ giả định constructor và mapping của Customer phù hợp. Trong test thật, nếu repository có dữ liệu fixture khác, hãy dọn dữ liệu hoặc lọc theo trạng thái/tenant riêng để kết quả không phụ thuộc test khác.

### 13.2. Kiểm thử MVC argument resolver

Dùng `@WebMvcTest` hoặc `MockMvc` để gửi request có page, size và sort, rồi xác nhận controller nhận đúng Pageable hoặc repository được gọi với tham số tương ứng.

Các trường hợp nên kiểm tra:

- Không gửi parameter: nhận default page/size/sort.
- Gửi page và size hợp lệ.
- Gửi nhiều sort order.
- Gửi direction ASC và DESC.
- Gửi size vượt max.
- Gửi page âm, size 0 hoặc size âm.
- Gửi property sort không nằm trong allowlist.
- Dùng one-indexed request nếu cấu hình bật.
- Dùng nhiều Pageable có qualifier.
- Kiểm tra tên parameter/prefix/delimiter tùy chỉnh.

### 13.3. Kiểm thử trên đúng phiên bản

Spring Data Web resolver và Spring Boot configuration properties có thể khác giữa các phiên bản. Test tích hợp trên dependency thực tế giúp xác nhận:
- Property YAML được bind đúng.
- Resolver được đăng ký đúng một lần.
- Default annotation hoạt động như mong đợi.
- Sort request được parse đúng.
- Max page size được áp dụng.
- Response metadata nhất quán với request convention.

Không chỉ test service bằng cách tạo PageRequest trực tiếp; điều đó không kiểm tra phần Spring MVC parse HTTP request.

## 14. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Controller không nhận Pageable | Spring Data Web support chưa được cấu hình hoặc dependency thiếu | Kiểm tra Boot auto-configuration hoặc @EnableSpringDataWebSupport |
| Client gửi page=1 nhưng nhận trang thứ hai | Resolver đang dùng zero-based mặc định | Thống nhất quy ước hoặc bật one-indexed parameters |
| Request size quá lớn | Chưa đặt max page size | Cấu hình max-page-size và giới hạn ở API |
| Sort báo property không tồn tại | Dùng tên cột SQL thay vì property Java hoặc property sai | Dùng property path hợp lệ và kiểm thử |
| Native query không nhận sort như mong đợi | Giới hạn query parser/dialect/version | Dùng ORDER BY cố định hoặc custom repository với allowlist |
| Trang có bản ghi lặp/bỏ sót | Sort không ổn định hoặc dữ liệu thay đổi | Thêm tie-breaker duy nhất; cân nhắc keyset/snapshot |
| Nhiều query count không cần thiết | Dùng Page dù UI chỉ cần next/previous | Dùng Slice nếu phù hợp |
| Default sort bị mất | Request sort ghi đè default theo quy tắc resolver | Kiểm thử trường hợp request có/không có sort |
| Hai Pageable đọc cùng parameter | Thiếu @Qualifier hoặc prefix không đúng | Đặt qualifier và dùng đúng delimiter |
| Endpoint trả payload quá lớn | Không giới hạn page size hoặc trả entity nhiều quan hệ | Giới hạn page, dùng DTO projection và fetch plan phù hợp |

## 15. Checklist thiết kế API phân trang

- [ ] Endpoint khai báo `Pageable` hoặc `Sort` đúng nhu cầu.
- [ ] Client biết page index bắt đầu từ 0 hay 1.
- [ ] Default page size và max page size đã được cấu hình.
- [ ] Tên parameter `page`, `size`, `sort` được công bố.
- [ ] Default sort có tie-breaker duy nhất khi cần.
- [ ] Sort field được kiểm tra qua allowlist.
- [ ] Không nối raw sort parameter vào SQL/JPQL.
- [ ] Query native có chiến lược sort được kiểm thử riêng.
- [ ] Chọn Page, Slice hay List theo nhu cầu metadata.
- [ ] Nhiều Pageable được phân biệt bằng qualifier/prefix.
- [ ] Response metadata dùng quy ước page nhất quán.
- [ ] Đã kiểm thử MVC resolver và repository trên dependency thực tế.
- [ ] Đã cân nhắc offset lớn, keyset và dữ liệu thay đổi liên tục.

## 16. Kết luận

Spring Data Web tích hợp `Pageable` và `Sort` với Spring MVC bằng argument resolver. Client gửi page, size và sort; controller nhận object đã được phân tích rồi truyền xuống service/repository. `@PageableDefault` và `@SortDefault` định nghĩa mặc định theo endpoint, trong khi Spring Boot properties hoặc resolver customizer kiểm soát quy tắc toàn ứng dụng.

API cần giới hạn page size, thống nhất cách đánh số trang, công bố tên sort và chỉ cho phép các property đã được kiểm tra. Sort ổn định nên có tie-breaker duy nhất; với dataset lớn hoặc thay đổi liên tục, cân nhắc keyset pagination. Chọn Page khi cần tổng số, Slice khi chỉ cần biết còn dữ liệu và kiểm thử cả MVC argument resolver lẫn repository để bảo đảm cấu hình hoạt động đúng trên phiên bản thực tế.