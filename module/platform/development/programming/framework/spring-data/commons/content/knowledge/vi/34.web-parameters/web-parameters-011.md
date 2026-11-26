# Phân biệt web support với việc xuất repository thành REST API

Một ứng dụng có thể nhận `Pageable` trong controller, chuyển một ID trên URL thành domain object và tạo liên kết phân trang mà không tự xuất repository thành REST API. Các khả năng đó thuộc phần tích hợp web của Spring Data Commons. Việc tạo HTTP resource dựa trên repository là trách nhiệm của một mô-đun riêng: Spring Data REST.

Bài học thuộc chương **Tham số web** của module **SPRING_DATA_COMMONS**. Mục tiêu là xác định đúng ranh giới giữa abstraction dữ liệu, hạ tầng xử lý HTTP và hợp đồng API. Phân biệt này giúp sử dụng Repository, CRUD, derived query, phân trang, projection và metadata đúng khả năng của từng store, đồng thời chủ động lựa chọn những thao tác sẽ xuất hiện trên HTTP.

## 1. Ba lớp trách nhiệm cần tách biệt

Xét ba câu hỏi:

1. Làm thế nào Java gọi được thao tác lưu hoặc tìm dữ liệu?
2. Làm thế nào controller nhận được thông tin phân trang từ request?
3. Ai quyết định có endpoint nào, nhận HTTP method nào và trả resource ra sao?

Ba câu hỏi tương ứng với các trách nhiệm khác nhau:

| Thành phần | Trách nhiệm chính | Ví dụ |
| --- | --- | --- |
| Repository và store module | Cung cấp, thực thi hợp đồng truy cập dữ liệu | `findById`, `save`, truy vấn theo tên phương thức |
| Spring Data Web Support | Tích hợp kiểu dữ liệu của Spring Data vào tầng web | Chuyển query parameter thành `Pageable`, `Sort` |
| Tầng HTTP resource | Xác định đường dẫn, thao tác và biểu diễn API | Controller tự viết hoặc exporter của Spring Data REST |

`CrudRepository` định nghĩa thao tác dữ liệu trong Java. Hợp đồng của nó không tự khai báo một URL, một controller hay mã trạng thái HTTP; xem [CrudRepository API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/CrudRepository.html).

Ví dụ, repository có `deleteById` chưa đủ để suy ra ứng dụng đã có `DELETE /customers/{id}`. Phải có một cơ chế tầng web ánh xạ HTTP tới thao tác dữ liệu đó.

## 2. Spring Data Web Support hỗ trợ controller như thế nào?

### 2.1. Nhận Pageable và Sort từ request

Controller tự viết có thể khai báo:

```java
@GetMapping("/api/customers")
CustomerPage list(Pageable pageable) {
    return queries.findCustomers(pageable);
}
```

Ở đây, `CustomerPage` và `queries` là kiểu phản hồi và dịch vụ do ứng dụng định nghĩa. Khi hạ tầng web phù hợp đã được đăng ký, request như sau có thể được chuyển thành tham số Java:

```http
GET /api/customers?page=0&size=15&sort=name,asc
```

Web support giúp hiểu thông tin phân trang và sắp xếp. Đường dẫn `/api/customers` vẫn do `@GetMapping` tạo ra. Nếu xóa controller và không có cơ chế xuất resource nào khác, việc resolver vẫn tồn tại không giữ lại endpoint này.

Trong một ứng dụng Spring MVC đã có cấu hình MVC, có thể bật phần tích hợp bằng:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.web.config.EnableSpringDataWebSupport;

@Configuration
@EnableSpringDataWebSupport
class DataWebConfiguration {
}
```

Ứng dụng có thể đã được cấu hình tự động tương ứng; cần dùng một cơ chế cấu hình nhất quán. Đoạn mã trên không phải cấu hình hoàn chỉnh của toàn bộ ứng dụng, store và kết nối dữ liệu.

### 2.2. DomainClassConverter hỗ trợ tìm domain object

Khi đủ điều kiện, có thể dùng domain type trong chữ ký handler:

```java
@GetMapping("/api/customers/{id}/summary")
CustomerView summary(@PathVariable("id") Customer customer) {
    return new CustomerView(customer.getId(), customer.getName());
}
```

Ví dụ giả định `Customer` là domain đã được mapping, có getter tương ứng và có repository đủ điều kiện cho converter. Spring chuyển chuỗi ID sang kiểu ID của domain rồi tra cứu qua repository. Tài liệu Commons nêu repository phải triển khai `CrudRepository` để được phát hiện cho cơ chế chuyển đổi này. Các thành phần web support, bao gồm converter và resolver, được mô tả trong [Spring Data Commons Web Support](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions-web.html).

Converter không tạo mapping `/api/customers/{id}/summary`; annotation trên handler mới tạo mapping đó. Nó cũng không tự quyết định người gọi có quyền đọc khách hàng vừa tìm được hay không.

Chọn converter cần cân nhắc việc tra cứu đã diễn ra trong quá trình giải quyết tham số, trước phần thân handler. Nếu quy tắc truy cập yêu cầu tìm theo cả ID lẫn tenant hoặc người sở hữu, nhận ID rồi gọi một service truy vấn có phạm vi rõ ràng thường dễ thể hiện chính sách hơn.

### 2.3. Tạo biểu diễn và liên kết không đồng nghĩa xuất repository

Tích hợp web có thể hỗ trợ một số kiểu serialize và làm việc cùng Spring HATEOAS khi có dependency thích hợp. Controller cũng có thể tự trả DTO, mô hình phân trang hoặc mô hình có liên kết.

Một phản hồi có `_links` hoặc một kiểu tên `PagedModel` không chứng minh endpoint do Spring Data REST tạo ra. Các controller tự viết cũng có thể xây dựng biểu diễn đó.

## 3. Controller tự viết vẫn có thể dùng đầy đủ abstraction của Commons

Ví dụ dưới đây giả định Java 17 trở lên, Spring MVC và Spring Data Commons có [org.springframework.data.web.PagedModel](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/PagedModel.html) (từ 3.3 trở lên). Ứng dụng đã đăng ký web support và có implementation của `CustomerQueries`.

```java
import java.util.Optional;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedModel;
import org.springframework.data.web.PageableDefault;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/customers")
class CustomerController {

    private final CustomerQueries queries;

    CustomerController(CustomerQueries queries) {
        this.queries = queries;
    }

    @GetMapping
    PagedModel<CustomerView> list(
            @PageableDefault(size = 15, sort = "id")
            Pageable pageable) {

        return new PagedModel<>(queries.findVisible(pageable));
    }

    @GetMapping("/{id}")
    CustomerView detail(@PathVariable("id") Long id) {
        return queries.findVisibleById(id)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND,
                        "Customer not found"));
    }
}

interface CustomerQueries {
    Page<CustomerView> findVisible(Pageable pageable);

    Optional<CustomerView> findVisibleById(Long id);
}

record CustomerView(Long id, String name) {
}
```

`CustomerQueries` là cổng truy vấn của ứng dụng, không phải interface mà Spring tự động tạo implementation chỉ vì có hai phương thức trên. Implementation cần gọi repository hoặc cơ chế truy vấn phù hợp.

Tên `findVisible` thể hiện ý định rằng phạm vi dữ liệu phải được quyết định trong implementation. Ví dụ này không chứa implementation phân quyền, tenant hay kiểm tra sort; ứng dụng phải bổ sung các chính sách đó.

Trong luồng này:

```text
HTTP request
    -> CustomerController do ứng dụng viết
    -> CustomerQueries do ứng dụng cài đặt
    -> Repository/query của store
    -> Dữ liệu
```

Repository có thể dùng derived query, Query by Example hoặc projection nếu store hỗ trợ. Controller vẫn tự quyết định URL, DTO và lỗi HTTP.

Ngay cả khi repository nội bộ có `save` hoặc `deleteById`, controller trên chỉ khai báo hai handler đọc. Các thao tác ghi không tự có URL tương ứng nhờ việc bật web support.

## 4. Spring Data REST tạo một tầng HTTP resource từ repository

Spring Data REST là mô-đun riêng, có hạ tầng để xuất resource dựa trên repository đủ điều kiện. Trong ứng dụng Spring Boot, starter thường dùng cho mục đích này là:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-rest</artifactId>
</dependency>
```

Đây là đoạn dependency minh họa, giả định dự án đã có dependency management tương thích. Nó không thay cho dependency của store, driver hay cấu hình repository.

Với Spring Boot và các điều kiện cấu hình tự động phù hợp, thêm starter có thể kích hoạt Spring Data REST. Với MVC cấu hình thủ công, cần tích hợp cấu hình REST tương ứng. Cách khởi tạo được giải thích trong [Getting started của Spring Data REST](https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html).

### 4.1. Ví dụ repository được xuất thành resource

Ví dụ này là **phương án riêng** với cách dùng controller ở phần trước. Giả định domain `Customer` có các property `id`, `name`, đã được mapping cho store hỗ trợ các truy vấn được khai báo.

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.PagingAndSortingRepository;
import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;

@RepositoryRestResource(
        path = "customers",
        collectionResourceRel = "customers")
public interface CustomerRepository
        extends CrudRepository<Customer, Long>,
                PagingAndSortingRepository<Customer, Long> {

    @RestResource(path = "by-name", rel = "by-name")
    Page<Customer> findByName(
            @Param("name") String name,
            Pageable pageable);
}
```

Khai báo rõ cả CRUD lẫn phân trang để thể hiện hai năng lực được sử dụng. Không mặc định rằng mọi interface repository trong mọi thế hệ Spring Data đều có cùng cây kế thừa.

Khi Spring Data REST được bật, repository được chọn để export và không có chính sách exposure khác chặn thao tác, các đường dẫn có thể gồm:

```http
GET /data/customers
GET /data/customers/42
GET /data/customers/search/by-name?name=Lan&page=0&size=10
```

Tiền tố `/data` được cấu hình ở phần tiếp theo; nó không đến từ annotation `path = "customers"`.

### 4.2. HTTP method phụ thuộc thao tác repository và chính sách exposure

Với cấu hình phù hợp, tài nguyên collection có thể hỗ trợ đọc danh sách hoặc tạo mới; item resource có thể hỗ trợ đọc, cập nhật hoặc xóa. Spring Data REST chọn thao tác repository để thực hiện các HTTP operation.

Điều này không có nghĩa mỗi phương thức Java luôn trở thành một URL riêng. Các CRUD operation được ánh xạ theo quy tắc của exporter; query method có cơ chế search resource riêng. Tập resource, phương thức nền và biểu diễn HAL được mô tả trong [Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html).

Ví dụ, một repository chỉ có năng lực đọc không tự được cấp năng lực ghi. Ngược lại, thêm một phương thức nội bộ có thể ảnh hưởng bề mặt HTTP nếu quy tắc export cho phép. Do đó phải xem repository và chính sách export như những đầu vào cùng quyết định API.

## 5. Annotation của hai cơ chế không thay thế nhau

| Thành phần | Nằm ở đâu? | Ý nghĩa trong ngữ cảnh phù hợp |
| --- | --- | --- |
| `@EnableSpringDataWebSupport` | Cấu hình ứng dụng | Đăng ký tích hợp web của Commons |
| `@GetMapping`, `@PostMapping` | Handler trong controller | Khai báo mapping HTTP do ứng dụng viết |
| `@PageableDefault` | Tham số `Pageable` | Chọn mặc định khi giải quyết tham số |
| `@RepositoryRestResource` | Repository | Điều chỉnh metadata xuất resource của Spring Data REST |
| `@RestResource` | Repository/query method hoặc thành phần được hỗ trợ | Điều chỉnh metadata/exposure trong Spring Data REST |
| `@RestController` | Lớp controller | Xác định controller trả dữ liệu qua response body |

Các suy luận dễ sai:

- Có `@EnableSpringDataWebSupport` nên mọi repository sẽ có endpoint: annotation này không làm nhiệm vụ đó.
- Repository thiếu `@RepositoryRestResource` nên chắc chắn không được xuất: điều này phụ thuộc chiến lược phát hiện của Spring Data REST.
- Có `@RepositoryRestResource` nên chỉ cần Commons: annotation cần hạ tầng Spring Data REST đang hoạt động để tham gia export.
- Có `@RestController` thì repository tự được ánh xạ: controller vẫn cần các mapping và logic gọi dữ liệu của nó.

Spring Data REST sử dụng các abstraction của Spring Data và có thể dùng hạ tầng web liên quan. Quan hệ sử dụng chung đó không làm hai cơ chế trở thành một công tắc cấu hình duy nhất.

## 6. Chủ động chọn repository được export

### 6.1. Cấu hình export bằng annotation

Có thể giới hạn việc phát hiện repository theo chiến lược chỉ chọn những repository được đánh dấu phù hợp:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.core.mapping.RepositoryDetectionStrategy
        .RepositoryDetectionStrategies;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Configuration
class RepositoryApiConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.setBasePath("/data");
        config.setRepositoryDetectionStrategy(
                RepositoryDetectionStrategies.ANNOTATED);
    }
}
```

Cấu hình trên giả định Spring Data REST đã được khởi tạo và lớp cấu hình được phát hiện. `ANNOTATED` là chiến lược opt-in ở cấp repository. Nó không đồng nghĩa mọi phương thức của repository được chọn cũng phải có annotation opt-in riêng.

Chính sách mặc định của Spring Data REST có thể chọn public repository không có annotation export tường minh. Các chiến lược `DEFAULT`, `ANNOTATED` và những lựa chọn khác được mô tả trong [Customizing repository exposure](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html).

### 6.2. Không xuất một repository hoặc query method

Ví dụ đối với một repository nội bộ:

```java
@RepositoryRestResource(exported = false)
public interface InternalCustomerRepository
        extends CrudRepository<Customer, Long> {
}
```

Hoặc chỉ tắt export một query method:

```java
@RestResource(exported = false)
Page<Customer> findByName(
        @Param("name") String name,
        Pageable pageable);
```

Hiệu lực cần được xét cùng chiến lược phát hiện/exposure thực tế. Không chọn một chiến lược bỏ qua annotation rồi mặc định `exported = false` vẫn là hàng rào tuyệt đối.

Các annotation này điều khiển exporter của Spring Data REST. Chúng không cấm một service nội bộ gọi repository, cũng không xóa một controller do ứng dụng tự viết đang sử dụng cùng repository.

### 6.3. Opt-in repository khác opt-in phương thức

Nếu muốn tắt export mặc định ở cả cấp repository và phương thức, Spring Data REST cung cấp:

```java
config.disableDefaultExposure();
```

Khi dùng cách này, các repository và phương thức cần được đánh dấu phù hợp để tạo resource mong muốn. Chỉ gắn `@RepositoryRestResource` rồi chờ mọi CRUD method xuất hiện có thể không đáp ứng cấu hình này. Xem định nghĩa [disableDefaultExposure trong RepositoryRestConfiguration](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/core/config/RepositoryRestConfiguration.html).

Tắt riêng một phương thức `delete` cũng không nên được diễn giải thành đã xử lý mọi biến thể xóa hoặc mọi HTTP operation. Phải xét chữ ký CRUD, quy tắc lựa chọn phương thức và exposure của resource trong phiên bản sử dụng.

## 7. Export resource không thay cho thiết kế nghiệp vụ

### 7.1. Tầng service không tự trở thành đường đi bắt buộc

So sánh hai luồng:

```text
Controller tự viết:
HTTP -> Controller -> Application service -> Repository

Resource do Spring Data REST xuất:
HTTP -> Hạ tầng Spring Data REST -> Repository
```

Luồng thứ hai không tự chèn một service nghiệp vụ chỉ vì service đó cũng tồn tại trong application context.

Giả sử hủy đơn hàng phải kiểm tra trạng thái, hoàn tiền và ghi lịch sử. Một endpoint nghiệp vụ `POST /orders/{id}/cancel` có thể thể hiện use case này qua application service. Cho phép xóa một bản ghi đơn hàng qua CRUD không tự mang cùng ý nghĩa.

Spring Data REST có các điểm mở rộng và tích hợp, nhưng ứng dụng phải chủ động thiết kế chúng. Không suy ra một chuỗi nghiệp vụ nhiều bước từ tên một CRUD operation.

### 7.2. Exposure khác authorization

“Resource có tồn tại không?” và “Người gọi này được thực hiện thao tác không?” là hai câu hỏi khác nhau.

`exported = false` có thể loại một thao tác khỏi exporter theo chính sách phù hợp. Nó không phải hệ thống phân quyền theo người dùng. Ngược lại, một resource đã được export vẫn cần xác thực và kiểm soát quyền phù hợp với ứng dụng.

Spring Data REST tích hợp với Spring Security, bao gồm kiểm soát ở phương thức khi được bật và cấu hình đúng; xem [Security của Spring Data REST](https://docs.spring.io/spring-data/rest/reference/security.html). Các đường gọi khác đến cùng dữ liệu cũng phải tuân thủ chính sách của chúng.

### 7.3. Projection, auditing và metadata vẫn có phạm vi riêng

Projection giúp chọn biểu diễn dữ liệu theo khả năng repository và cơ chế API hỗ trợ. Nó không mặc nhiên kiểm tra quyền đọc từng đối tượng hay giới hạn trường được phép ghi.

Auditing hỗ trợ quản lý metadata như người tạo hoặc thời điểm chỉnh sửa khi store và cấu hình đáp ứng yêu cầu. Bật web support hoặc export repository không tự hoàn tất cấu hình auditing.

Query by Example cũng không tự trở thành một API tìm kiếm mở cho mọi thuộc tính. Nếu muốn client gửi điều kiện lọc, cần có hợp đồng nhận đầu vào và cách chuyển đổi phù hợp; với endpoint tự viết, ứng dụng thực hiện việc đó qua controller/service. Với Spring Data REST, phải xem đúng cơ chế resource/query mà exporter hỗ trợ.

## 8. Cùng Pageable nhưng cấu hình HTTP có thể khác

Cả controller tự viết lẫn collection resource của Spring Data REST đều có thể làm việc với phân trang. Việc hai endpoint cùng nhận `page`, `size`, `sort` không chứng minh chúng dùng cùng một đường xử lý hay toàn bộ cấu hình giống nhau.

Ví dụ:

| Quyết định | Controller tự viết | Spring Data REST |
| --- | --- | --- |
| Đường dẫn gốc | `@RequestMapping` hoặc cấu hình MVC liên quan | Cấu hình base path và metadata resource |
| Mặc định tại handler | Có thể dùng `@PageableDefault` | Theo cấu hình/hạ tầng của exporter |
| Kiểu phản hồi | DTO hoặc mô hình do controller chọn | Biểu diễn resource theo cấu hình REST |
| Danh sách sort được phép | Ứng dụng kiểm tra trước khi gọi query | Cần chính sách tương ứng với resource và truy vấn |
| Phạm vi dữ liệu | Service/query do ứng dụng chọn | Repository, truy vấn và các cơ chế kiểm soát đã cấu hình |

Đừng thay cấu hình resolver cho controller rồi mặc định mọi endpoint REST đã nhận cùng chính sách. Ngược lại, đổi base path của Spring Data REST không tự đổi `@RequestMapping("/api/customers")` trong một controller thông thường.

## 9. Chọn cách phù hợp với hợp đồng API

Một controller tự viết thường thuận tiện khi URL, DTO, mã lỗi và thao tác cần bám sát use case: duyệt yêu cầu, hoàn tiền, tổng hợp báo cáo hoặc truy vấn qua nhiều nguồn dữ liệu. Web support giúp giảm phần chuyển đổi tham số mà vẫn để ứng dụng làm chủ hợp đồng.

Spring Data REST phù hợp khi chủ động chọn mô hình resource gắn với repository và muốn sử dụng hạ tầng export, liên kết, phân trang cùng các điểm tùy chỉnh của mô-đun. Lựa chọn này vẫn cần thiết kế phạm vi export và hành vi truy cập.

Hai cách có thể cùng tồn tại nếu có ranh giới rõ ràng. Chẳng hạn, `/data/customers` là vùng resource được export còn `/api/customer-onboarding` là use case riêng. Tránh để hai vùng trùng mapping hoặc cùng thay đổi dữ liệu theo những chính sách nghiệp vụ mâu thuẫn.

Một quyết định đúng cần dựa vào hợp đồng mong muốn và khả năng của store, không chỉ dựa vào việc đã có một interface repository.

## 10. Nhận diện bằng một thí nghiệm có kiểm soát

Có thể hình dung hai cấu hình độc lập:

| Tình huống | Điều được kỳ vọng |
| --- | --- |
| Có repository và web support, chưa có controller hay exporter | Các thành phần đó chưa tự tạo CRUD endpoint |
| Thêm controller với `@GetMapping` | Có mapping do controller khai báo |
| Controller nhận `Pageable` | Resolver có thể chuyển tham số khi cấu hình đúng |
| Thêm Spring Data REST và repository được chọn export | Xuất hiện resource theo quy tắc của exporter |
| Tắt export repository trong chính sách phù hợp | Resource tương ứng của exporter không còn được xuất |
| Vẫn giữ một controller riêng gọi repository đó | Mapping của controller phải được xem xét độc lập |

Khi quan sát ứng dụng thật, response 401, 403 hay 404 đơn lẻ chưa đủ xác định repository có được export hay không: bộ lọc bảo mật, base path và mapping khác có thể ảnh hưởng kết quả. Cần đối chiếu cấu hình export, handler đang xử lý request và phương thức repository được gọi.
