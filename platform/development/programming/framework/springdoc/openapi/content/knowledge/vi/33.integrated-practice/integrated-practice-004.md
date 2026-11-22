# Mô tả API phân trang, lọc và sắp xếp

Một API danh sách thường cần đáp ứng nhiều cách truy vấn cùng lúc: lấy từng trang dữ liệu, giới hạn số bản ghi, lọc theo nhiều điều kiện và sắp xếp theo một hoặc nhiều trường. Với Spring Boot, Spring Data Web cung cấp Pageable để nhận thông tin phân trang/sắp xếp từ query string; springdoc-openapi có thể chuyển Pageable thành các query parameter hiển thị trong OpenAPI và Swagger UI.

Bài thực hành xây dựng API tra cứu sách. Client có thể tìm theo từ khóa, danh mục, khoảng giá và tình trạng tồn kho; đồng thời chọn page, size và sort. Mục tiêu là giữ hợp đồng OpenAPI khớp với cách Spring MVC bind request, cách Spring Data tạo truy vấn và hình dạng JSON trả về.

## 1. Mục tiêu và hợp đồng cần đạt

Sau bài thực hành, bạn có thể:

- Thiết kế query parameter cho phân trang, lọc và sắp xếp.
- Dùng Pageable và @PageableDefault trong controller.
- Dùng @ParameterObject để Springdoc mô tả Pageable và filter object thành các query parameter riêng.
- Dùng Specification để ghép điều kiện lọc động.
- Giới hạn page size và danh sách trường được phép sort.
- Thiết kế response envelope ổn định thay vì để API phụ thuộc trực tiếp vào cấu trúc nội bộ của Spring Data.
- Kiểm tra OpenAPI JSON, Swagger UI và hành vi runtime bằng integration test.

Hợp đồng ví dụ:

| Nhóm | Parameter | Ý nghĩa | Mặc định |
| --- | --- | --- | --- |
| Lọc | keyword | Tìm trong tên sách hoặc tác giả | Không lọc |
| Lọc | category | Lọc theo danh mục chính xác | Không lọc |
| Lọc | minPrice | Giá thấp nhất, bao gồm biên | Không lọc |
| Lọc | maxPrice | Giá cao nhất, bao gồm biên | Không lọc |
| Lọc | inStock | Chỉ lấy sách còn hàng hoặc hết hàng | Không lọc |
| Phân trang | page | Chỉ số trang, bắt đầu từ 0 | 0 |
| Phân trang | size | Số bản ghi tối đa trong một trang | 20 |
| Sắp xếp | sort | Trường và chiều sắp xếp; có thể lặp parameter | createdAt desc, id desc |

Ví dụ request:

~~~http
GET /api/books?keyword=spring&category=backend&minPrice=100000&maxPrice=500000&inStock=true&page=0&size=20&sort=price,asc&sort=createdAt,desc
~~~

Request trên tìm sách có từ khóa spring, thuộc danh mục backend, giá từ 100.000 đến 500.000, còn hàng; kết quả được chia thành trang đầu tiên, tối đa 20 bản ghi và sắp xếp theo giá tăng dần rồi ngày tạo giảm dần.

## 2. Phân biệt phân trang, lọc và sắp xếp

Ba nhóm parameter có trách nhiệm riêng:

| Nhóm | Thực hiện ở đâu | Tác động |
| --- | --- | --- |
| Lọc | Specification, Criteria API hoặc query repository | Xác định bản ghi nào được chọn |
| Sắp xếp | Sort trong Pageable hoặc ORDER BY | Xác định thứ tự bản ghi |
| Phân trang | PageRequest/Pageable và repository | Chọn một đoạn của tập kết quả |

Thứ tự xử lý logic là lọc trước, sắp xếp sau đó mới phân trang. Nếu phân trang trước rồi mới lọc trong Java, kết quả có thể thiếu bản ghi phù hợp và metadata totalElements không còn chính xác.

Ví dụ, nếu có 1.000 sách nhưng chỉ 80 sách thuộc danh mục backend, API phải lọc 80 bản ghi trước rồi mới chia trang. Không lấy 20 bản ghi đầu tiên trong 1.000 sách rồi mới lọc chúng trong bộ nhớ.

## 3. Quy ước query parameter của Spring Data Pageable

Spring Data Web mặc định đọc các parameter:

| Parameter | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| page | Số trang, zero-based | page=0 |
| size | Số phần tử trong trang | size=20 |
| sort | Trường và chiều sort | sort=price,asc |

Trang đầu tiên là page=0. Trang thứ hai là page=1. Nếu size=20, trang 0 chứa vị trí 0–19, trang 1 chứa vị trí 20–39 trong tập kết quả đã lọc và sắp xếp.

Có thể gửi nhiều sort parameter để sắp xếp theo nhiều trường:

~~~text
?sort=price,asc&sort=createdAt,desc
~~~

Trong đó price là tiêu chí ưu tiên thứ nhất; createdAt được dùng khi hai bản ghi có cùng giá. Nếu không truyền sort, API dùng thứ tự mặc định được khai báo trong controller hoặc cấu hình ứng dụng.

## 4. Thêm dependency cần thiết

Ứng dụng Spring MVC dùng Spring Data JPA và Springdoc v2 có thể cần các starter sau:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-jpa</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>

<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>2.x-compatible-version</version>
</dependency>
~~~

Hãy thay placeholder version bằng phiên bản Springdoc 2.x tương thích với Spring Boot 3 của dự án. Nếu ứng dụng dùng WebFlux, chọn starter webflux tương ứng và cách triển khai repository/service phù hợp.

## 5. Cấu hình giới hạn phân trang

Có thể cấu hình tên parameter, kích thước mặc định và giới hạn tối đa trong application.yml:

~~~yaml
spring:
  data:
    web:
      pageable:
        page-parameter: page
        size-parameter: size
        default-page-size: 20
        max-page-size: 100
        one-indexed-parameters: false
~~~

Ý nghĩa:

- page-parameter và size-parameter giữ tên query parameter nhất quán với hợp đồng.
- default-page-size chọn số phần tử mặc định khi client không gửi size.
- max-page-size giới hạn số phần tử một request có thể yêu cầu.
- one-indexed-parameters=false giữ quy ước trang đầu tiên là 0.

Giới hạn page size quan trọng để tránh một client yêu cầu hàng trăm nghìn bản ghi trong một request. Cấu hình resolver là lớp bảo vệ đầu vào; service vẫn nên kiểm tra giới hạn nghiệp vụ nếu có đường gọi nội bộ hoặc resolver tùy chỉnh.

## 6. Tạo DTO bộ lọc

Không nên nhận toàn bộ entity làm query object. Hãy tạo DTO chỉ chứa những điều kiện mà API cho phép:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;

@Schema(description = "Các điều kiện lọc danh sách sách")
public class BookSearchCriteria {

    @Size(max = 100)
    @Schema(description = "Tìm trong tiêu đề hoặc tên tác giả", example = "spring")
    private String keyword;

    @Size(max = 50)
    @Schema(description = "Mã danh mục cần lọc", example = "backend")
    private String category;

    @DecimalMin("0.00")
    @Schema(description = "Giá thấp nhất, bao gồm giá trị biên", example = "100000")
    private BigDecimal minPrice;

    @DecimalMin("0.00")
    @Schema(description = "Giá cao nhất, bao gồm giá trị biên", example = "500000")
    private BigDecimal maxPrice;

    @Schema(description = "Chỉ lấy sách còn hàng khi true", example = "true")
    private Boolean inStock;

    public BookSearchCriteria() {}

    public String getKeyword() { return keyword; }
    public void setKeyword(String keyword) { this.keyword = keyword; }

    public String getCategory() { return category; }
    public void setCategory(String category) { this.category = category; }

    public BigDecimal getMinPrice() { return minPrice; }
    public void setMinPrice(BigDecimal minPrice) { this.minPrice = minPrice; }

    public BigDecimal getMaxPrice() { return maxPrice; }
    public void setMaxPrice(BigDecimal maxPrice) { this.maxPrice = maxPrice; }

    public Boolean getInStock() { return inStock; }
    public void setInStock(Boolean inStock) { this.inStock = inStock; }
}
~~~

Các field được phép null để biểu thị không áp dụng điều kiện lọc. Bean Validation kiểm tra độ dài từ khóa/danh mục và giá không âm. Điều kiện minPrice không được lớn hơn maxPrice sẽ được kiểm tra ở service hoặc bằng class-level validator riêng. DTO dùng getter theo quy ước getX() để Springdoc có thể trích từng field từ @ParameterObject; Java record chỉ có accessor theo tên component nên cần bổ sung getter bean-style nếu chọn dùng record cho mục đích này. Giữ query DTO ở dạng phẳng vì @ParameterObject không tự phân rã các parameter object lồng nhau.

Với query object, dùng @ModelAttribute để Spring MVC bind query parameter vào DTO. @ParameterObject bổ sung hướng dẫn cho Springdoc phân rã object thành các parameter riêng trong OpenAPI:

~~~java
@Valid
@ModelAttribute
@ParameterObject
BookSearchCriteria criteria
~~~

@ParameterObject là annotation phục vụ mô tả tài liệu. Nó không thay thế cơ chế binding của Spring MVC.

## 7. Mô tả Pageable bằng @ParameterObject

Springdoc hỗ trợ Pageable của Spring Data. Khi đặt @ParameterObject trên tham số Pageable, tài liệu sẽ mô tả các query parameter page, size và sort thay vì hiển thị một object Java khó hiểu.

Ví dụ:

~~~java
@ParameterObject
@PageableDefault(
    page = 0,
    size = 20,
    sort = {"createdAt", "id"},
    direction = Sort.Direction.DESC
)
Pageable pageable
~~~

@PageableDefault xác định mặc định runtime cho request không truyền page/size/sort. Springdoc có thể dùng metadata này để mô tả default trong OpenAPI. FAQ chính thức của Springdoc xác nhận Pageable được hỗ trợ khi kết hợp với @ParameterObject và @PageableDefault.

Nếu parameter Pageable bị ẩn khỏi Swagger UI hoặc tài liệu chỉ hiện một object, hãy kiểm tra import đúng annotation org.springdoc.core.annotations.ParameterObject và dependency starter Springdoc. Không dùng annotation cùng tên từ thư viện khác.

## 8. Tạo repository hỗ trợ Specification và Pageable

Repository cần hỗ trợ cả truy vấn CRUD, Specification và Pageable:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

public interface BookRepository
        extends JpaRepository<Book, Long>,
                JpaSpecificationExecutor<Book> {
}
~~~

JpaSpecificationExecutor cho phép gọi findAll(specification, pageable). Spring Data JPA sẽ áp dụng điều kiện lọc, thứ tự sort và giới hạn trang ở database.

Nếu ứng dụng dùng query SQL tùy chỉnh, cần khai báo count query phù hợp khi trả Page<T>. Page cần tổng số bản ghi để tính totalElements và totalPages; query count có thể là phần chi phí đáng kể với điều kiện join phức tạp.

## 9. Xây dựng Specification từ filter

Specification giúp ghép các điều kiện tùy chọn mà không cần viết một method repository cho mọi tổ hợp filter:

~~~java
import jakarta.persistence.criteria.Predicate;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.util.StringUtils;

public final class BookSpecifications {

    private BookSpecifications() {}

    public static Specification<Book> from(BookSearchCriteria filter) {
        return (root, query, cb) -> {
            List<Predicate> predicates = new ArrayList<>();

            if (StringUtils.hasText(filter.getKeyword())) {
                String keyword = "%" + filter.getKeyword().trim().toLowerCase(Locale.ROOT) + "%";
                predicates.add(cb.or(
                    cb.like(cb.lower(root.<String>get("title")), keyword),
                    cb.like(cb.lower(root.<String>get("author")), keyword)
                ));
            }

            if (StringUtils.hasText(filter.getCategory())) {
                predicates.add(cb.equal(root.get("categoryCode"), filter.getCategory()));
            }

            if (filter.getMinPrice() != null) {
                predicates.add(
                    cb.greaterThanOrEqualTo(root.<BigDecimal>get("price"), filter.getMinPrice())
                );
            }

            if (filter.getMaxPrice() != null) {
                predicates.add(
                    cb.lessThanOrEqualTo(root.<BigDecimal>get("price"), filter.getMaxPrice())
                );
            }

            if (filter.getInStock() != null) {
                if (filter.getInStock()) {
                    predicates.add(cb.greaterThan(root.<Integer>get("stockQuantity"), 0));
                } else {
                    predicates.add(cb.equal(root.<Integer>get("stockQuantity"), 0));
                }
            }

            return cb.and(predicates.toArray(Predicate[]::new));
        };
    }
}
~~~

Mỗi điều kiện chỉ được thêm khi client gửi giá trị tương ứng. Khi không có filter, danh sách predicate rỗng và truy vấn trả về toàn bộ sách trong phạm vi truy cập của người dùng.

Trong ứng dụng thực tế, cần quyết định rõ category là mã hay tên hiển thị, tìm kiếm có phân biệt dấu/hoa thường hay không, và inStock=false có bao gồm sản phẩm ngừng kinh doanh hay chỉ sản phẩm có tồn kho bằng 0.

## 10. Kiểm tra khoảng giá và dữ liệu đầu vào

Nếu minPrice lớn hơn maxPrice, request không có ý nghĩa. Có thể kiểm tra trong service:

~~~java
private void validateFilter(BookSearchCriteria filter) {
    if (filter.getMinPrice() != null
            && filter.getMaxPrice() != null
            && filter.getMinPrice().compareTo(filter.getMaxPrice()) > 0) {
        throw new ResponseStatusException(
            HttpStatus.BAD_REQUEST,
            "minPrice must be less than or equal to maxPrice"
        );
    }
}
~~~

Thông báo lỗi công khai nên được chuẩn hóa và có thể bản địa hóa. Không trả stack trace, câu SQL hoặc chi tiết nội bộ của entity cho client.

## 11. Giới hạn các trường được phép sắp xếp

Không nên cho client sort tùy ý theo mọi thuộc tính entity. Một số property không có index, có quan hệ lồng nhau đắt đỏ hoặc không thuộc hợp đồng API. Hãy định nghĩa allowlist:

~~~java
private static final Set<String> ALLOWED_SORT_FIELDS = Set.of(
    "title",
    "price",
    "createdAt",
    "id"
);
~~~

Service xác minh từng Sort.Order:

~~~java
private Sort validateSort(Sort requested) {
    List<Sort.Order> orders = new ArrayList<>();

    requested.forEach(order -> {
        if (!ALLOWED_SORT_FIELDS.contains(order.getProperty())) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "Unsupported sort field: " + order.getProperty()
            );
        }
        orders.add(order);
    });

    if (orders.isEmpty()) {
        orders.add(Sort.Order.desc("createdAt"));
    }

    // Thêm tie-breaker để thứ tự ổn định giữa các trang.
    if (orders.stream().noneMatch(order -> order.getProperty().equals("id"))) {
        orders.add(Sort.Order.desc("id"));
    }

    return Sort.by(orders);
}
~~~

Sort allowlist phải dùng tên property mà Spring Data JPA hiểu, không nhất thiết là tên cột database. Nếu API dùng tên public khác tên entity, hãy ánh xạ từ tên public sang property được phép thay vì chuyển nguyên chuỗi client vào query.

Tie-breaker như id giúp thứ tự ổn định khi nhiều bản ghi có cùng price hoặc createdAt. Nếu không có tiêu chí cuối cùng duy nhất, một bản ghi có thể xuất hiện ở hai trang hoặc bị bỏ qua khi dữ liệu thay đổi giữa các request.

## 12. Tạo Pageable an toàn

Kết hợp sort đã xác minh với giới hạn page size:

~~~java
private Pageable normalizePageable(Pageable requested) {
    int page = Math.max(0, requested.getPageNumber());
    int size = Math.max(1, Math.min(requested.getPageSize(), 100));
    Sort sort = validateSort(requested.getSort());

    return PageRequest.of(page, size, sort);
}
~~~

Giới hạn trong service là lớp bảo vệ bổ sung bên cạnh spring.data.web.pageable.max-page-size. Với hệ thống cần từ chối size vượt mức thay vì âm thầm giới hạn, hãy dùng custom PageableHandlerMethodArgumentResolver hoặc kiểm tra input trước khi service chạy và trả lỗi 400 có thông báo rõ ràng.

Page number quá lớn có thể khiến database phải bỏ qua rất nhiều row khi dùng offset pagination. Giới hạn size không giải quyết hoàn toàn chi phí của page sâu; cần theo dõi truy vấn và cân nhắc keyset/cursor pagination khi dữ liệu tăng lớn.

## 13. Viết service ghép filter, sort và page

Service điều phối các bước theo đúng thứ tự:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;

@Service
public class BookSearchService {

    private final BookRepository repository;

    public BookSearchService(BookRepository repository) {
        this.repository = repository;
    }

    public Page<Book> search(BookSearchCriteria filter, Pageable requested) {
        validateFilter(filter);
        Pageable pageable = normalizePageable(requested);
        return repository.findAll(BookSpecifications.from(filter), pageable);
    }
}
~~~

Các method validateFilter, normalizePageable và validateSort là những method đã xây dựng ở các phần trước. Có thể đặt chúng trong class service hoặc tách thành validator/policy riêng nếu nhiều API dùng chung quy tắc.

Service không nên tự tải tất cả dữ liệu rồi lọc/sort bằng Java Stream. Hãy để database áp dụng WHERE, ORDER BY và LIMIT/OFFSET để chỉ trả về phần dữ liệu cần thiết.

## 14. Thiết kế response envelope ổn định

Spring Data Page<T> chứa content và metadata phân trang. Trả Page trực tiếp rất tiện, nhưng cấu trúc JSON của Page có thể phụ thuộc phiên bản Spring Data và cấu hình serialization. Nếu API là hợp đồng công khai, nên tạo response DTO của riêng ứng dụng:

~~~java
import java.util.List;
import org.springframework.data.domain.Page;

public record BookPageResponse(
    List<BookResponse> content,
    int page,
    int size,
    long totalElements,
    int totalPages,
    boolean first,
    boolean last,
    boolean hasNext,
    boolean hasPrevious
) {
    public static BookPageResponse from(Page<BookResponse> result) {
        return new BookPageResponse(
            result.getContent(),
            result.getNumber(),
            result.getSize(),
            result.getTotalElements(),
            result.getTotalPages(),
            result.isFirst(),
            result.isLast(),
            result.hasNext(),
            result.hasPrevious()
        );
    }
}
~~~

Ví dụ BookResponse:

~~~java
import java.math.BigDecimal;
import java.time.Instant;

public record BookResponse(
    Long id,
    String title,
    String author,
    String category,
    BigDecimal price,
    Instant createdAt,
    int stockQuantity
) {}
~~~

Controller chuyển Page<Book> thành Page<BookResponse> bằng mapper rồi tạo envelope. DTO response giúp API giữ cấu trúc ổn định ngay cả khi Spring Data bổ sung hoặc thay đổi metadata nội bộ.

Nếu dự án chủ động chấp nhận Page JSON của Spring Data, có thể trả Page<T> trực tiếp. Khi đó cần kiểm tra schema OpenAPI và JSON thực tế sau mỗi lần nâng Spring Data; không giả định cấu trúc serialization luôn bất biến.

## 15. Khai báo controller và metadata OpenAPI

Controller sử dụng @ParameterObject cho cả filter lẫn Pageable:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import jakarta.validation.Valid;
import org.springdoc.core.annotations.ParameterObject;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PageableDefault;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

// Các kiểu Book, BookResponse, BookPageResponse, BookMapper,
// BookSearchCriteria và BookSearchService thuộc package ứng dụng.

@RestController
@RequestMapping("/api/books")
public class BookController {

    private final BookSearchService service;
    private final BookMapper mapper;

    public BookController(BookSearchService service, BookMapper mapper) {
        this.service = service;
        this.mapper = mapper;
    }

    @GetMapping
    @Operation(
        summary = "Tìm kiếm sách",
        description = """
            Lọc danh sách sách theo từ khóa, danh mục, khoảng giá và tồn kho.

            Phân trang dùng page bắt đầu từ 0 và size tối đa 100.
            Có thể lặp sort để khai báo nhiều tiêu chí, ví dụ
            sort=price,asc&sort=createdAt,desc.
            """
    )
    @ApiResponses({
        @ApiResponse(
            responseCode = "200",
            description = "Danh sách sách cùng metadata phân trang",
            content = @Content(
                schema = @Schema(implementation = BookPageResponse.class)
            )
        ),
        @ApiResponse(
            responseCode = "400",
            description = "Filter, page, size hoặc sort không hợp lệ"
        )
    })
    public BookPageResponse search(
            @Valid
            @ModelAttribute
            @ParameterObject
            BookSearchCriteria filter,

            @ParameterObject
            @PageableDefault(
                page = 0,
                size = 20,
                sort = {"createdAt", "id"},
                direction = Sort.Direction.DESC
            )
            Pageable pageable) {

        Page<Book> books = service.search(filter, pageable);
        Page<BookResponse> responsePage = books.map(mapper::toResponse);
        return BookPageResponse.from(responsePage);
    }
}
~~~

Các import và class Book, BookMapper, BookSearchService, BookPageResponse cần nằm trong package của ứng dụng. Ví dụ tập trung vào phần hợp đồng; hãy điều chỉnh mapper và constructor theo cấu trúc dự án thực tế.

## 16. @ParameterObject làm gì trong tài liệu?

Nếu thiếu @ParameterObject, Springdoc có thể mô tả filter/Pageable không đúng như cách client gửi query string. Khi dùng annotation đúng:

- Các property của BookSearchCriteria trở thành query parameter riêng.
- Pageable được phân rã thành page, size và sort.
- @PageableDefault cung cấp default page, size và sort.
- @Schema trên property cung cấp description, example và ràng buộc schema.

Ví dụ document dự kiến có các parameter:

~~~yaml
paths:
  /api/books:
    get:
      parameters:
        - name: keyword
          in: query
          required: false
          schema:
            type: string
            maxLength: 100
        - name: category
          in: query
          required: false
          schema:
            type: string
            maxLength: 50
        - name: minPrice
          in: query
          schema:
            type: number
        - name: maxPrice
          in: query
          schema:
            type: number
        - name: inStock
          in: query
          schema:
            type: boolean
        - name: page
          in: query
          schema:
            type: integer
            default: 0
        - name: size
          in: query
          schema:
            type: integer
            default: 20
            maximum: 100
        - name: sort
          in: query
          description: Có thể lặp parameter để sắp xếp nhiều trường
          schema:
            type: array
            items:
              type: string
          style: form
          explode: true
~~~

Đây là hình dạng minh họa. OpenAPI document thực tế phụ thuộc Springdoc, Spring Data và cách cấu hình Pageable của ứng dụng. Hãy mở /v3/api-docs để kiểm tra tên, schema, default và style/explode mà phiên bản đang dùng thực sự sinh ra.

## 17. Mô tả sort allowlist cho client

OpenAPI có thể mô tả sort là chuỗi hoặc array các chuỗi. Nếu tự khai báo sort thủ công thay cho Pageable converter, có thể đặt mô tả trong Operation:

~~~java
@Operation(parameters = @Parameter(
    name = "sort",
    in = ParameterIn.QUERY,
    description = """
        Trường sắp xếp theo cú pháp property,direction.
        Có thể lặp parameter.
        Trường hỗ trợ: title, price, createdAt, id.
        Direction: asc hoặc desc.
        """
))
~~~

Ví dụ trên cần import Parameter và ParameterIn. Không khai báo thêm parameter sort tường minh nếu Pageable converter đã tạo parameter đó, vì có thể làm tài liệu xuất hiện hai parameter trùng tên. Với controller đang dùng Pageable converter, hãy ưu tiên description của Operation hoặc customizer phù hợp với phiên bản Springdoc mà không tạo parameter trùng.

Allowlist trong service mới là nơi thực thi quy tắc. Description OpenAPI chỉ giúp client biết quy tắc; nó không tự ngăn server nhận một sort property không hợp lệ.

## 18. Ví dụ request và response

Request chỉ phân trang:

~~~http
GET /api/books?page=0&size=20
~~~

Request lọc và sort nhiều trường:

~~~http
GET /api/books?keyword=spring&category=backend&minPrice=100000&maxPrice=500000&inStock=true&page=0&size=20&sort=price,asc&sort=createdAt,desc
~~~

Response ví dụ:

~~~json
{
  "content": [
    {
      "id": 42,
      "title": "Spring Boot thực hành",
      "author": "Nguyen An",
      "category": "backend",
      "price": 250000,
      "createdAt": "2026-01-12T09:30:00Z",
      "stockQuantity": 12
    }
  ],
  "page": 0,
  "size": 20,
  "totalElements": 1,
  "totalPages": 1,
  "first": true,
  "last": true,
  "hasNext": false,
  "hasPrevious": false
}
~~~

Nếu không có bản ghi phù hợp, API vẫn trả HTTP 200 với content là mảng rỗng và metadata phản ánh kết quả rỗng. Danh sách rỗng không phải lỗi 404.

## 19. Cấu hình đổi tên query parameter

Spring Data cho phép đổi page/size parameter bằng cấu hình:

~~~yaml
spring:
  data:
    web:
      pageable:
        page-parameter: pageNumber
        size-parameter: pageSize
~~~

Khi đổi tên, URL trở thành:

~~~text
GET /api/books?pageNumber=0&pageSize=20
~~~

Springdoc phải đọc được cấu hình Spring Data tương ứng để document phản ánh đúng tên mới. Sau khi đổi property, kiểm tra OpenAPI JSON và thử request thật. Không chỉ sửa description của @Operation trong khi resolver runtime vẫn dùng tên cũ.

Nếu dùng nhiều Pageable trong cùng một endpoint, có thể dùng @Qualifier và qualifier delimiter để tách tên parameter, ví dụ orders_page/orders_size và reviews_page/reviews_size. Khi đó cần kiểm tra document được sinh ra để xác nhận tên prefix khớp resolver.

## 20. Một-based hay zero-based pagination

Spring Data mặc định dùng zero-based indexing: page=0 là trang đầu tiên. Có thể bật one-indexed-parameters để public API nhận page=1 là trang đầu tiên:

~~~yaml
spring:
  data:
    web:
      pageable:
        one-indexed-parameters: true
~~~

Chỉ bật khi hợp đồng API đã thống nhất rõ. Cần kiểm tra đồng thời:

- Swagger UI hiển thị default page là 1.
- Request page=1 trả về tập bản ghi đầu tiên.
- Response metadata page được định nghĩa là số trang public hay index nội bộ.
- Link next/previous nếu có dùng cùng quy ước.

Không tự trừ 1 ở controller nếu resolver đã thực hiện one-indexed conversion, vì sẽ làm lệch trang. Với API mới, zero-based thường dễ đồng bộ với PageRequest và tài liệu Spring Data.

## 21. Kiểm thử OpenAPI document

Tạo integration test tải /v3/api-docs và xác nhận các query parameter xuất hiện:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class BookOpenApiTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void documentsFilterAndPageableParameters() throws Exception {
        String json = mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();

        JsonNode spec = objectMapper.readTree(json);
        JsonNode parameters = spec.at("/paths/~1api~1books/get/parameters");

        Set<String> names = StreamSupport.stream(parameters.spliterator(), false)
            .map(parameter -> parameter.path("name").asText())
            .collect(Collectors.toSet());

        assertThat(names).contains(
            "keyword", "category", "minPrice", "maxPrice",
            "inStock", "page", "size", "sort"
        );
    }
}
~~~

Đoạn test cần các import cho JsonNode, ObjectMapper, StreamSupport, Collectors, Set, AssertJ và static MockMvcRequestBuilders.get. Nếu Spring Security bảo vệ docs, cung cấp user/authority thích hợp trong test.

Có thể mở rộng test để kiểm tra schema default:

~~~java
JsonNode pageParameter = StreamSupport.stream(parameters.spliterator(), false)
    .filter(parameter -> "page".equals(parameter.path("name").asText()))
    .findFirst()
    .orElseThrow();

assertThat(pageParameter.at("/schema/default").asInt()).isZero();
~~~

Vì hình dạng parameter do Springdoc tạo ra có thể thay đổi theo phiên bản, hãy kiểm tra đúng JSON Pointer trong document thực tế. Nếu parameter sort được biểu diễn thành string thay vì array, cập nhật assertion và description cho khớp.

## 22. Kiểm thử hành vi phân trang và lọc

Test runtime cần chứng minh server áp dụng đúng filter và Pageable. Ví dụ với service mock:

~~~java
@Test
void passesFilterAndPageableToService() throws Exception {
    mockMvc.perform(get("/api/books")
            .param("keyword", "spring")
            .param("category", "backend")
            .param("page", "1")
            .param("size", "10")
            .param("sort", "price,asc"))
        .andExpect(status().isOk());

    ArgumentCaptor<BookSearchCriteria> filterCaptor =
        ArgumentCaptor.forClass(BookSearchCriteria.class);
    ArgumentCaptor<Pageable> pageableCaptor =
        ArgumentCaptor.forClass(Pageable.class);

    verify(service).search(filterCaptor.capture(), pageableCaptor.capture());

    assertThat(filterCaptor.getValue().getKeyword()).isEqualTo("spring");
    assertThat(filterCaptor.getValue().getCategory()).isEqualTo("backend");
    assertThat(pageableCaptor.getValue().getPageNumber()).isEqualTo(1);
    assertThat(pageableCaptor.getValue().getPageSize()).isEqualTo(10);
    assertThat(pageableCaptor.getValue().getSort().getOrderFor("price").getDirection())
        .isEqualTo(Sort.Direction.ASC);
}
~~~

Test trên giả định controller dùng service mock và response của mock đã được cấu hình. Với integration test database thật, kiểm tra cả content, totalElements và sort order sau khi truy vấn.

## 23. Kiểm tra trường hợp biên

Một API danh sách cần test ít nhất các tình huống:

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Không truyền filter | Trả danh sách trong phạm vi truy cập |
| Không truyền page/size | Dùng page=0, size=20 |
| size vượt 100 | Bị giới hạn hoặc trả 400 theo policy đã công bố |
| page âm | Resolver chuẩn hóa hoặc trả 400 theo policy |
| sort field không hỗ trợ | Trả 400 |
| minPrice lớn hơn maxPrice | Trả 400 |
| Không có kết quả | 200 với content rỗng |
| Nhiều bản ghi cùng giá trị sort | Tie-breaker giữ thứ tự ổn định |
| Filter có ký tự đặc biệt | Binding và query parameter encoding được xử lý đúng |
| Dữ liệu thay đổi giữa hai lần tải trang | Client hiểu pagination offset có thể dịch chuyển |

Không nên để test chỉ xác nhận HTTP 200. Cần kiểm tra cả dữ liệu trả về, metadata trang và điều kiện sort/filter thực tế.

## 24. Page, Slice và cursor pagination

Page<T> chứa tổng số phần tử và tổng số trang. Để tính totalElements, Spring Data thường cần một count query bổ sung. Điều này hữu ích khi giao diện cần hiển thị tổng số trang, nhưng có thể tốn chi phí với truy vấn join hoặc filter phức tạp.

| Kiểu | Metadata | Phù hợp |
| --- | --- | --- |
| Page<T> | content, totalElements, totalPages, page number | UI cần tổng số kết quả và số trang |
| Slice<T> | content, hasNext, page/size | UI chỉ cần biết còn trang tiếp theo |
| Cursor/keyset | cursor/position tiếp tục, không phụ thuộc offset sâu | Dataset lớn, truy cập liên tục theo thứ tự ổn định |

Nếu API không cần tổng số kết quả, cân nhắc Slice để tránh count query. Nếu dữ liệu rất lớn và người dùng thường đi sâu nhiều trang, cân nhắc keyset/cursor pagination. Khi đó hợp đồng sẽ dùng cursor hoặc continuation token thay cho page number; cần mô tả schema và quy tắc cursor riêng trong OpenAPI.

Không gọi mọi cơ chế phân trang là Pageable. Pageable là mô hình page/size/sort dựa trên offset; cursor pagination có semantics khác và thường cần DTO request/response riêng.

## 25. Hiệu năng và index database

Filter và sort cần được thiết kế cùng index database:

- Tìm theo category và createdAt có thể cần composite index theo mẫu truy vấn thực tế.
- Lọc minPrice/maxPrice cần xem xét index price.
- Tìm kiếm contains với LIKE '%keyword%' thường khó tận dụng B-tree index; cân nhắc full-text search hoặc search engine khi dữ liệu lớn.
- Sort theo nhiều trường cần đánh giá thứ tự cột index.
- Page sâu với OFFSET lớn có thể chậm dù page size nhỏ.
- Page<T> có thể phát sinh count query; đo riêng thời gian truy vấn dữ liệu và truy vấn đếm.

Không tạo index theo mọi filter có thể có. Hãy dùng query log, execution plan và workload thực tế để xác định index phù hợp.

## 26. Bảo mật và tính đúng đắn của filter/sort

Một số nguyên tắc quan trọng:

1. Chỉ expose filter mà người dùng được phép sử dụng.
2. Luôn áp dụng tenant/user scope ở backend; không để client truyền tenantId tùy ý để đọc dữ liệu người khác.
3. Dùng Criteria API/Specification hoặc parameter binding, không nối chuỗi SQL từ query string.
4. Giới hạn page size và allowlist sort field.
5. Không cho phép sort/filter trên property nhạy cảm như passwordHash, internalCost hoặc dữ liệu phân quyền.
6. Giới hạn độ dài keyword và số lượng sort criteria.
7. Kiểm tra quyền truy cập trước khi tính totalElements để tránh rò rỉ số lượng dữ liệu ngoài phạm vi.

OpenAPI chỉ mô tả contract; authorization và validation phải được thực thi ở backend. Ẩn parameter trong Swagger UI không phải biện pháp bảo mật.

## 27. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Swagger UI hiện Pageable như object | Thiếu @ParameterObject hoặc sai import | Dùng org.springdoc.core.annotations.ParameterObject |
| Filter object không bind query string | Thiếu @ModelAttribute hoặc DTO không bind được | Dùng @ModelAttribute và constructor/setter phù hợp |
| Page/size không xuất hiện trong OpenAPI | Pageable bị ẩn hoặc Springdoc starter không phù hợp | Kiểm tra @ParameterObject và pageable converter |
| Default page/size trong docs sai | @PageableDefault hoặc Spring Data property không khớp | Kiểm tra runtime resolver và OpenAPI JSON |
| Sort không hoạt động | Cú pháp sort sai hoặc field không tồn tại | Dùng property hợp lệ, ví dụ sort=price,asc |
| Sort có thứ tự không ổn định | Không có tie-breaker duy nhất | Thêm id làm tiêu chí cuối |
| API trả thiếu kết quả sau khi lọc | Lọc trong Java sau khi phân trang | Đưa filter vào Specification/query database |
| totalElements không đúng | Count query không áp dụng cùng điều kiện lọc | Kiểm tra query count và Specification |
| Request size quá lớn | Chưa giới hạn max page size | Cấu hình max-page-size và kiểm tra service |
| Sort field gây lỗi runtime | Client gửi property không được hỗ trợ | Validate sort allowlist và trả 400 |
| Page response schema thay đổi khi nâng Boot | Trả trực tiếp Page<T> và serialization thay đổi | Dùng response DTO ổn định hoặc kiểm tra schema diff |
| Tìm kiếm chậm | LIKE contains, thiếu index hoặc join nặng | Xem execution plan và cân nhắc full-text search |

## 28. Checklist hoàn thành bài thực hành

- [ ] Query filter chỉ chứa field mà API cho phép.
- [ ] DTO filter có description, example và validation phù hợp.
- [ ] Controller dùng @ModelAttribute cho filter object.
- [ ] Controller dùng @ParameterObject cho filter và Pageable.
- [ ] @PageableDefault mô tả default page, size và sort.
- [ ] page bắt đầu từ 0 hoặc có quy ước one-based được công bố rõ.
- [ ] max-page-size được giới hạn ở cấu hình và/hoặc service.
- [ ] Sort field được kiểm tra bằng allowlist.
- [ ] Sort nhiều trường và tie-breaker có thứ tự xác định.
- [ ] Specification ghép filter trước khi repository phân trang.
- [ ] Response có content và metadata trang rõ ràng.
- [ ] OpenAPI JSON hiển thị keyword/category/minPrice/maxPrice/inStock/page/size/sort.
- [ ] Swagger UI cho phép nhập đúng query parameter và hiển thị default.
- [ ] Test kiểm tra OpenAPI document và request runtime.
- [ ] Test các trường hợp invalid filter, size quá lớn, sort không hỗ trợ và kết quả rỗng.
- [ ] Database index được đánh giá theo query thực tế.
- [ ] Tenant/user authorization luôn được áp dụng phía server.

Khi kết hợp Spring Data Pageable với @ParameterObject, Springdoc có thể mô tả page, size và sort thành query parameter để client dùng trực tiếp trong Swagger UI. Để API đáng tin cậy, hãy mô tả filter bằng DTO riêng, áp dụng Specification tại database, giới hạn sort/page size và trả response envelope ổn định. Cuối cùng, kiểm tra cả OpenAPI document lẫn request/response runtime để bảo đảm tài liệu và hành vi triển khai luôn thống nhất.

## Tài liệu tham khảo

- [Springdoc OpenAPI FAQ — Pageable và @ParameterObject](https://springdoc.org/faq.html)
- [Springdoc OpenAPI v2 FAQ](https://springdoc.org/v2/faq.html)
- [Spring Data Commons — PageableHandlerMethodArgumentResolver](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/PageableHandlerMethodArgumentResolver.html)
- [Spring Data Commons — Pageable resolver configuration](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/web/PageableHandlerMethodArgumentResolverSupport.html)
- [Spring Data JPA — Specifications](https://docs.spring.io/spring-data/jpa/reference/jpa/specifications.html)
