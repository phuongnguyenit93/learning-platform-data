# Ánh xạ Page<Entity> sang Page<DTO> và hợp đồng phản hồi

Trong Spring Data JPA, repository thường trả về **Page<Entity>** khi một truy vấn cần phân trang. Nhưng entity là mô hình persistence: nó có thể chứa quan hệ LAZY, field nội bộ và chi tiết mapping database. API thường chỉ cần một phần dữ liệu và cần một cấu trúc JSON ổn định để client đọc thông tin trang.

Cách phổ biến là chuyển **Page<Entity>** thành **Page<DTO>** bằng phương thức **Page.map()**, sau đó chuyển kết quả thành một response contract do ứng dụng định nghĩa. Cách này giữ lại metadata phân trang trong khi chỉ công khai các field cần thiết.

Bài này trình bày cách viết DTO, map content mà không làm mất metadata, xử lý association LAZY, khi nào nên query DTO trực tiếp, cách thiết kế JSON response ổn định, kiểm soát sort/page size và kiểm thử hợp đồng API.

**Điều kiện của ví dụ:** các đoạn mã dùng Java 17 trở lên, Spring Boot 3.x, Spring Data JPA và Spring MVC. Ứng dụng cần **spring-boot-starter-data-jpa**, **spring-boot-starter-web**, JDBC driver, DataSource và schema phù hợp. Các đoạn mã là những phần của ứng dụng Spring Boot, không phải chương trình độc lập có thể chạy chỉ bằng **javac**.

## 1. Vì sao không nên trả Entity trực tiếp từ API?

Entity mô tả dữ liệu được persistence context quản lý. Ví dụ Book có thể chứa các field:

~~~java
@Entity
@Table(name = "books")
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String title;

    @Enumerated(EnumType.STRING)
    private BookStatus status;

    private Instant createdAt;

    @ManyToOne(fetch = FetchType.LAZY)
    private Author author;

    // constructor, getters và các mapping khác
}
~~~

Một endpoint danh sách có thể chỉ cần ID, tiêu đề, trạng thái và thời điểm tạo. Trả entity trực tiếp tạo ra một số vấn đề:

- API có thể vô tình công khai field nội bộ khi entity được bổ sung thuộc tính.
- Serializer có thể truy cập association LAZY và phát sinh SQL ngoài dự kiến.
- Quan hệ hai chiều có thể tạo vòng lặp serialization.
- Entity/proxy phụ thuộc persistence provider và không phải hợp đồng JSON phù hợp.
- Thay đổi mapping database có thể làm thay đổi response API ngoài ý muốn.

DTO (Data Transfer Object) định nghĩa chính xác dữ liệu được gửi ra ngoài. DTO tách hợp đồng API khỏi entity và cho phép thay đổi persistence model mà không buộc client thay đổi theo.

## 2. Tạo DTO cho từng phần tử

Với Java 17+, record là lựa chọn gọn cho DTO bất biến:

~~~java
package com.example.catalog.dto;

import com.example.catalog.domain.BookStatus;
import java.time.Instant;

public record BookSummary(
    Long id,
    String title,
    BookStatus status,
    Instant createdAt
) {
}
~~~

DTO chỉ chứa bốn field mà màn hình danh sách cần. Nó không có annotation JPA, không phải entity managed và không được lưu bằng repository.

Có thể đặt logic chuyển đổi trong một static factory:

~~~java
package com.example.catalog.dto;

import com.example.catalog.domain.Book;

public record BookSummary(
    Long id,
    String title,
    BookStatus status,
    Instant createdAt
) {
    public static BookSummary from(Book book) {
        return new BookSummary(
            book.getId(),
            book.getTitle(),
            book.getStatus(),
            book.getCreatedAt()
        );
    }
}
~~~

Ví dụ giả định Book có getter tương ứng và BookStatus là enum của domain. Nếu DTO cần định dạng đặc biệt, có thể dùng mapper riêng như MapStruct hoặc một class mapper; không nên nhồi quy tắc nghiệp vụ phức tạp vào DTO.

## 3. Page.map(): chuyển Page<Entity> thành Page<DTO>

Spring Data cung cấp **Page.map(Function)** để chuyển từng phần tử của trang sang kiểu khác:

~~~java
Page<Book> entityPage = bookRepository.findByStatus(status, pageable);

Page<BookSummary> dtoPage =
    entityPage.map(BookSummary::from);
~~~

Kết quả là **Page<BookSummary>**. Phương thức map chỉ chuyển content và giữ metadata của trang gốc, bao gồm:

- Số trang hiện tại.
- Kích thước trang.
- Tổng số phần tử.
- Tổng số trang.
- Thông tin trang đầu/cuối và điều hướng.
- Thông tin sắp xếp.

Không cần tự tạo một Page mới chỉ để đổi kiểu phần tử. **Page.map()** giữ metadata chính xác từ Page ban đầu và không chạy lại truy vấn đếm.

Ví dụ service:

~~~java
package com.example.catalog.service;

import com.example.catalog.domain.Book;
import com.example.catalog.domain.BookStatus;
import com.example.catalog.dto.BookSummary;
import com.example.catalog.repository.BookRepository;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookService {

    private final BookRepository bookRepository;

    public BookService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    @Transactional(readOnly = true)
    public Page<BookSummary> findByStatus(
            BookStatus status,
            Pageable pageable) {

        Page<Book> books =
            bookRepository.findByStatus(status, pageable);

        return books.map(BookSummary::from);
    }
}
~~~

Mapping được thực hiện trên các entity đã có trong content của Page. Không có truy vấn mới chỉ vì gọi **map()**, miễn là mapper chỉ đọc các field đã có sẵn và không kích hoạt lazy association.

## 4. Repository trả về Page<Entity>

Repository có thể dùng derived query:

~~~java
package com.example.catalog.repository;

import com.example.catalog.domain.Book;
import com.example.catalog.domain.BookStatus;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface BookRepository extends JpaRepository<Book, Long> {

    Page<Book> findByStatus(
        BookStatus status,
        Pageable pageable
    );
}
~~~

Spring Data tạo truy vấn content có phân trang và thường tạo thêm count query để xác định tổng số phần tử. Với query đơn giản, framework thường suy ra count query.

Nếu query có join phức tạp, DISTINCT, GROUP BY hoặc điều kiện đặc biệt, cần kiểm tra count query. Có thể khai báo **countQuery** tường minh trên **@Query** để bảo đảm tổng số phần tử phản ánh đúng kết quả logic.

Ví dụ service nhận Page<Entity> rồi chuyển sang DTO giúp giữ repository tập trung vào persistence model. Đây là cách phù hợp khi mapping DTO đơn giản và số association cần truy cập đã được kiểm soát.

## 5. Viết response contract riêng cho API

Mặc dù service trả **Page<DTO>**, không nhất thiết phải serialize trực tiếp implementation Page của Spring Data. Cấu trúc JSON mặc định của Page có thể phụ thuộc phiên bản Spring Data và cách Jackson serialize. Nếu client dựa vào cấu trúc đó, nâng cấp framework có thể làm thay đổi response ngoài dự kiến.

Một response contract rõ ràng:

~~~java
package com.example.api.dto;

import java.util.List;
import org.springframework.data.domain.Page;

public record PageResponse<T>(
    List<T> content,
    int page,
    int size,
    int numberOfElements,
    long totalElements,
    int totalPages,
    boolean first,
    boolean last,
    boolean hasNext,
    boolean hasPrevious,
    List<SortField> sort
) {

    public static <T> PageResponse<T> from(Page<T> source) {
        List<SortField> sortFields = source.getSort()
            .stream()
            .map(order -> new SortField(
                order.getProperty(),
                order.getDirection().name()
            ))
            .toList();

        return new PageResponse<>(
            source.getContent(),
            source.getNumber(),
            source.getSize(),
            source.getNumberOfElements(),
            source.getTotalElements(),
            source.getTotalPages(),
            source.isFirst(),
            source.isLast(),
            source.hasNext(),
            source.hasPrevious(),
            sortFields
        );
    }

    public record SortField(
        String property,
        String direction
    ) {
    }
}
~~~

Các field có ý nghĩa:

| Field | Ý nghĩa |
|---|---|
| **content** | Danh sách DTO trong trang hiện tại |
| **page** | Chỉ số trang, bắt đầu từ 0 |
| **size** | Kích thước trang được yêu cầu |
| **numberOfElements** | Số phần tử thực tế trong content |
| **totalElements** | Tổng số phần tử phù hợp với điều kiện truy vấn |
| **totalPages** | Tổng số trang |
| **first** / **last** | Trang hiện tại có phải trang đầu/cuối không |
| **hasNext** / **hasPrevious** | Có trang kế tiếp/trước đó không |
| **sort** | Các thuộc tính và hướng sắp xếp áp dụng |

**size** và **numberOfElements** khác nhau: size là giới hạn trang, còn numberOfElements là số phần tử thực tế được trả về. Trang cuối có thể có ít phần tử hơn size.

Với truy vấn không có kết quả, content rỗng, totalElements bằng 0 và totalPages bằng 0. Page index vẫn là giá trị yêu cầu, vì vậy client cần dựa vào metadata để xử lý trang ngoài phạm vi.

## 6. Chuyển Page<DTO> thành response ở controller

Controller có thể trả về response contract thay vì Page trực tiếp:

~~~java
package com.example.catalog.api;

import com.example.api.dto.PageResponse;
import com.example.catalog.domain.BookStatus;
import com.example.catalog.dto.BookSummary;
import com.example.catalog.service.BookService;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PageableDefault;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/books")
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @GetMapping
    public PageResponse<BookSummary> findBooks(
            @RequestParam BookStatus status,
            @PageableDefault(
                size = 20,
                sort = "createdAt",
                direction = Sort.Direction.DESC
            ) Pageable pageable) {

        return PageResponse.from(
            bookService.findByStatus(status, pageable)
        );
    }
}
~~~

Request ví dụ:

~~~http
GET /books?status=PUBLISHED&page=0&size=20&sort=createdAt,desc
~~~

Spring MVC có thể bind các tham số page, size và sort thành Pageable khi Spring Data web support được cấu hình. **@PageableDefault** đặt giá trị mặc định khi client không truyền các tham số này.

Controller chuyển Page sang PageResponse bằng factory method. Nhờ đó, cấu trúc JSON công khai được kiểm soát bởi ứng dụng và không phụ thuộc trực tiếp vào implementation Page.

## 7. Ví dụ JSON response

Một response có thể có dạng:

~~~json
{
  "content": [
    {
      "id": 101,
      "title": "Spring Data JPA",
      "status": "PUBLISHED",
      "createdAt": "2026-11-09T08:30:00Z"
    },
    {
      "id": 102,
      "title": "Hibernate Basics",
      "status": "PUBLISHED",
      "createdAt": "2026-11-08T10:15:00Z"
    }
  ],
  "page": 0,
  "size": 20,
  "numberOfElements": 2,
  "totalElements": 42,
  "totalPages": 3,
  "first": true,
  "last": false,
  "hasNext": true,
  "hasPrevious": false,
  "sort": [
    {
      "property": "createdAt",
      "direction": "DESC"
    }
  ]
}
~~~

Đây là JSON minh họa cho một trang có hai phần tử thực tế. Trong ví dụ này, size là 20 nhưng numberOfElements là 2; totalElements là 42 và totalPages là 3 chỉ khi page size và tổng số kết quả tương ứng với dữ liệu thực tế.

Hợp đồng nên được tài liệu hóa: tên field, kiểu dữ liệu, ý nghĩa page index, cách biểu diễn sort và hành vi khi không có dữ liệu. Khi cần đổi cấu trúc, có thể thêm field theo hướng tương thích hoặc tạo version API phù hợp.

## 8. Tránh N+1 khi mapper truy cập association LAZY

Mapper đơn giản như **BookSummary.from(book)** chỉ đọc field cơ bản. Nhưng nếu DTO cần tên tác giả:

~~~java
public record BookDetails(
    Long id,
    String title,
    String authorName
) {
    public static BookDetails from(Book book) {
        return new BookDetails(
            book.getId(),
            book.getTitle(),
            book.getAuthor().getName()
        );
    }
}
~~~

Nếu **Book.author** là LAZY, gọi **getAuthor().getName()** có thể kích hoạt truy vấn bổ sung cho từng Book. Với một trang gồm N sách, đây có thể trở thành N+1 query.

Có ba cách xử lý thường dùng:

1. Dùng **@EntityGraph** để tải association to-one cần thiết cùng truy vấn content.
2. Dùng JPQL DTO projection để database chỉ trả về các field DTO cần.
3. Dùng query/fetch plan phù hợp và đo SQL để xác nhận số truy vấn.

Ví dụ dùng EntityGraph cho association to-one:

~~~java
@EntityGraph(attributePaths = "author")
Page<Book> findByStatus(
    BookStatus status,
    Pageable pageable
);
~~~

Sau đó mapper có thể đọc tên tác giả mà không cần truy vấn riêng cho từng sách nếu provider thực hiện fetch plan như mong đợi. Kiểm tra SQL thực tế. Cẩn thận với fetch collection trong truy vấn phân trang vì join collection có thể nhân dòng và làm pagination khó dự đoán.

## 9. Khi nào nên query DTO trực tiếp?

Nếu use case chỉ đọc dữ liệu và DTO có cấu trúc rõ, có thể để repository trả thẳng **Page<DTO>** bằng JPQL constructor expression.

DTO:

~~~java
package com.example.catalog.dto;

import com.example.catalog.domain.BookStatus;
import java.time.Instant;

public record BookSummary(
    Long id,
    String title,
    BookStatus status,
    Instant createdAt
) {
}
~~~

Repository:

~~~java
@Query(
    value = """
        select new com.example.catalog.dto.BookSummary(
            b.id,
            b.title,
            b.status,
            b.createdAt
        )
        from Book b
        where b.status = :status
        """,
    countQuery = """
        select count(b)
        from Book b
        where b.status = :status
        """
)
Page<BookSummary> findSummariesByStatus(
    @Param("status") BookStatus status,
    Pageable pageable
);
~~~

Trong cách này, database trả trực tiếp các giá trị cần cho DTO. Không cần tải entity đầy đủ rồi map ở Java.

So sánh hai hướng:

| Tiêu chí | Page<Entity>.map(...) | Query trực tiếp Page<DTO> |
|---|---|---|
| Mapping | Thực hiện trong Java | Thực hiện trong truy vấn |
| Entity materialization | Có | Không cần entity đầy đủ |
| Tái sử dụng entity logic | Thuận tiện | Ít hơn |
| Chọn chính xác cột | Phụ thuộc projection/fetch plan | Rõ qua SELECT constructor |
| Association | Có thể phát sinh lazy query nếu mapper truy cập | Có thể join và chọn field cần |
| Count query | Query Page của entity | Cần count query tương ứng nếu framework không suy ra đúng |

Dùng **Page.map()** khi đã cần entity hoặc mapping đơn giản. Dùng DTO query trực tiếp khi cần tối ưu dữ liệu đọc, join nhiều bảng hoặc muốn tránh materialize entity.

## 10. Count query và metadata sau khi map

**Page.map()** không thay đổi tổng số phần tử. Nếu Page<Entity> có totalElements là 245, Page<DTO> sau map vẫn có totalElements là 245.

Phép map không chạy count query lần nữa. Count query (nếu cần) đã được dùng khi Spring Data tạo Page<Entity> ban đầu.

Với DTO query trực tiếp, count query phải đếm đúng số kết quả logic. Nếu content query join collection làm một entity xuất hiện nhiều lần, count có thể cần **count(distinct b.id)**. Nếu query có GROUP BY, count query phải đếm số nhóm thay vì tổng số hàng nguồn.

Không nên tự tạo Page bằng constructor chỉ với content và page request nếu không có total chính xác. Cách đó có thể làm mất hoặc làm sai metadata mà client cần.

## 11. Sort ổn định và kiểm soát Pageable

Phân trang cần một thứ tự ổn định. Nếu chỉ sắp xếp theo createdAt mà nhiều bản ghi có cùng timestamp, database có thể trả các hàng đồng hạng theo thứ tự không xác định.

Thêm ID làm tie-breaker:

~~~java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(Sort.Direction.DESC, "createdAt")
        .and(Sort.by(Sort.Direction.DESC, "id"))
);
~~~

Tên sort thường là property của entity, ví dụ **createdAt**, không phải tên cột vật lý **created_at**.

API nên kiểm soát:

- Page index bắt đầu từ 0 hay 1.
- Kích thước trang tối đa.
- Danh sách property được phép sort.
- Hướng sort hợp lệ.
- Thứ tự mặc định và tie-breaker duy nhất.

Không chuyển chuỗi sort tùy ý của client thành SQL động. Với native query, khả năng áp dụng sort động phụ thuộc query và phiên bản Spring Data; khai báo ORDER BY rõ ràng nếu cần kiểm soát SQL.

## 12. Có thể dùng PagedModel thay cho response wrapper tự viết không?

Spring Data cung cấp **PagedModel** trong package **org.springframework.data.web** ở các phiên bản Spring Data tương ứng. Nó là wrapper để biểu diễn Page dưới dạng DTO web ổn định hơn.

Ví dụ ở phiên bản có API này:

~~~java
@GetMapping
public PagedModel<BookSummary> findBooks(Pageable pageable) {
    Page<BookSummary> page = bookService.findByStatus(
        BookStatus.PUBLISHED,
        pageable
    );

    return new PagedModel<>(page);
}
~~~

Một lựa chọn khác là cấu hình page serialization mode **VIA_DTO** bằng **@EnableSpringDataWebSupport** nếu phiên bản Spring Data hỗ trợ.

PagedModel thuận tiện khi muốn dùng cấu trúc chuẩn do Spring Data cung cấp. Response wrapper riêng phù hợp khi API cần field, tên metadata hoặc quy tắc tương thích riêng của hệ thống. Hãy kiểm tra phiên bản Spring Data được Spring Boot quản lý trước khi dùng API này; không nâng riêng dependency một cách tùy tiện.

## 13. Kiểm thử việc map và response contract

Có thể kiểm thử service để xác nhận nội dung và metadata được giữ lại:

~~~java
@DataJpaTest
class BookPageMappingTest {

    @Autowired
    private BookRepository bookRepository;

    @Test
    void mapsPageContentAndKeepsMetadata() {
        Pageable pageable = PageRequest.of(0, 2);

        Page<Book> entityPage =
            bookRepository.findByStatus(
                BookStatus.PUBLISHED,
                pageable
            );

        Page<BookSummary> dtoPage =
            entityPage.map(BookSummary::from);

        assertThat(dtoPage.getContent())
            .allSatisfy(item -> assertThat(item.id()).isNotNull());

        assertThat(dtoPage.getNumber())
            .isEqualTo(entityPage.getNumber());

        assertThat(dtoPage.getSize())
            .isEqualTo(entityPage.getSize());

        assertThat(dtoPage.getTotalElements())
            .isEqualTo(entityPage.getTotalElements());

        assertThat(dtoPage.getTotalPages())
            .isEqualTo(entityPage.getTotalPages());
    }
}
~~~

Để kiểm thử response contract, có thể dùng **@WebMvcTest** hoặc integration test với MockMvc và xác nhận JSON field:

- content là mảng DTO, không có field nội bộ của entity.
- page và size dùng đúng quy ước.
- totalElements và totalPages phản ánh kết quả.
- sort có property/direction dự kiến.
- trang rỗng có content rỗng và tổng số bằng 0.
- page vượt phạm vi trả content rỗng theo hợp đồng đã chọn.

Nếu mapper truy cập association, kiểm tra số SQL hoặc dùng Hibernate Statistics/datasource proxy để phát hiện N+1. Chỉ kiểm tra JSON đúng chưa đủ để kết luận truy vấn hiệu quả.

## 14. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Page<DTO> mất totalElements | Tự tạo Page mới không giữ total từ Page gốc | Dùng **Page.map()** |
| API lộ field entity | Trả entity trực tiếp | Dùng DTO với field được chọn rõ |
| JSON Page thay đổi sau nâng cấp | Serialize trực tiếp implementation Page | Dùng response DTO hoặc PagedModel phù hợp phiên bản |
| Mapping DTO tạo N+1 | Mapper truy cập association LAZY | EntityGraph, DTO query hoặc fetch plan rõ ràng |
| DTO có dữ liệu null | Getter/alias hoặc mapping không đúng | Kiểm tra entity field, constructor và query |
| totalElements sai | Count query đếm dòng join thay vì entity | Dùng count distinct hoặc countQuery đúng |
| Trang có bản ghi lặp/thiếu | Sort không ổn định | Thêm tie-breaker duy nhất như ID |
| Page size quá lớn | Không giới hạn tham số client | Đặt kích thước tối đa ở API |
| Sort lỗi khi chạy | Client gửi property không tồn tại hoặc không được phép | Dùng allowlist sort property |
| DTO query không khớp constructor | Sai thứ tự hoặc kiểu biểu thức SELECT | Đồng bộ constructor và kiểu JPQL |

## 15. Checklist triển khai

- [ ] Xác định field API thực sự cần và tạo DTO riêng.
- [ ] Dùng **Page.map()** để đổi Page<Entity> thành Page<DTO> khi mapping trong Java phù hợp.
- [ ] Không tự dựng Page mới nếu có thể giữ metadata bằng map().
- [ ] Đảm bảo mapper không truy cập association LAZY ngoài kế hoạch.
- [ ] Dùng EntityGraph hoặc DTO query trực tiếp nếu cần dữ liệu từ association.
- [ ] Kiểm tra count query và totalElements với join/grouping.
- [ ] Không serialize entity hoặc implementation Page trực tiếp như hợp đồng dài hạn.
- [ ] Định nghĩa response contract có page, size, content và metadata cần thiết.
- [ ] Ghi rõ page index zero-based và ý nghĩa từng field.
- [ ] Giới hạn page size và allowlist sort properties.
- [ ] Dùng thứ tự ổn định có tie-breaker.
- [ ] Kiểm thử JSON contract, trang rỗng, trang cuối và hiệu năng SQL.

## 16. Kết luận

**Page<Entity>.map()** là cách đơn giản để chuyển từng entity thành DTO mà vẫn giữ nguyên metadata phân trang. Mapper nên chỉ đọc dữ liệu cần thiết; nếu truy cập association LAZY, hãy chọn fetch plan phù hợp hoặc query DTO trực tiếp để tránh N+1.

Ở ranh giới API, hãy định nghĩa response contract rõ ràng thay vì phụ thuộc vào cách implementation Page được serialize. Một DTO cho content và một wrapper cho metadata giúp client có cấu trúc ổn định, dễ tài liệu hóa và dễ thay đổi khi entity hoặc framework được nâng cấp.