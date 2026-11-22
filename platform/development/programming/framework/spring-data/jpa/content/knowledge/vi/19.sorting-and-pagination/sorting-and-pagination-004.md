# Pageable, PageRequest và quy ước chỉ số trang bắt đầu từ 0

## 1. Mục tiêu

Spring Data dùng `Pageable` để mô tả yêu cầu phân trang: trang cần lấy, số phần tử mỗi trang và thứ tự sắp xếp. `PageRequest` là implementation phổ biến để tạo một yêu cầu phân trang cụ thể. Điểm quan trọng nhất khi dùng `PageRequest` là **chỉ số trang bắt đầu từ 0**.

Sau bài học, bạn có thể:
- Giải thích vai trò của `Pageable`, `PageRequest`, `Sort`, `Page` và `Slice`.
- Tạo yêu cầu phân trang bằng `PageRequest.of(page, size)`.
- Tính đúng offset và phân biệt trang đầu tiên với số thứ tự trang mà giao diện hiển thị.
- Kết hợp phân trang với sắp xếp tăng dần, giảm dần và nhiều tiêu chí.
- Đọc metadata của `Page` và chọn `Page` hay `Slice` theo nhu cầu.
- Kiểm tra page/size từ HTTP request để tránh giá trị không hợp lệ hoặc truy vấn quá lớn.
- Kiểm thử thứ tự, nội dung và metadata của các trang.

## 2. Pageable là gì?

`Pageable` là interface mô tả một yêu cầu phân trang. Nó không chứa dữ liệu Entity; nó mang thông tin để Repository biết cần lấy phần dữ liệu nào.

Các thông tin chính:

| Thông tin | Ý nghĩa |
| --- | --- |
| `getPageNumber()` | Chỉ số trang hiện tại, bắt đầu từ 0. |
| `getPageSize()` | Số phần tử tối đa được yêu cầu trong một trang. |
| `getOffset()` | Vị trí bắt đầu trong toàn bộ kết quả, tính từ 0. |
| `getSort()` | Quy tắc sắp xếp của kết quả. |
| `isPaged()` | Cho biết yêu cầu có phân trang hay không. |
| `next()` / `previousOrFirst()` | Tạo yêu cầu cho trang kế tiếp hoặc trang trước; không thay đổi instance hiện tại. |

`Pageable` là abstraction mà Repository nhận vào. Nhờ vậy, phương thức repository không phụ thuộc trực tiếp vào một implementation cụ thể.

## 3. PageRequest và chỉ số trang bắt đầu từ 0

`PageRequest` là implementation của `Pageable`, được tạo bằng các factory method tĩnh. Cách dùng phổ biến nhất:

```java
PageRequest firstPage = PageRequest.of(0, 10);
PageRequest secondPage = PageRequest.of(1, 10);
PageRequest thirdPage = PageRequest.of(2, 10);
```

Tham số thứ nhất là page index, bắt đầu từ 0. Tham số thứ hai là page size.

Với `size = 10`, các trang có vị trí như sau:

| Page index truyền vào | Tên gọi theo thứ tự người dùng | Offset | Các vị trí kết quả |
| ---: | ---: | ---: | --- |
| `0` | Trang thứ 1 | `0` | 0 đến 9 |
| `1` | Trang thứ 2 | `10` | 10 đến 19 |
| `2` | Trang thứ 3 | `20` | 20 đến 29 |

Công thức:

\[
\text{offset} = \text{page index} \times \text{page size}
\]

Ví dụ, `PageRequest.of(2, 10)` yêu cầu trang có index 2, tức trang thứ ba theo cách đếm của người dùng; offset là 20.

**Quy ước cần nhớ:** `PageRequest.of(1, 10)` là trang thứ hai, không phải trang đầu tiên. Trang đầu tiên luôn có index `0`.

### 3.1. Tại sao Spring Data dùng index từ 0?

Index 0 phù hợp với cách đánh chỉ số của nhiều cấu trúc dữ liệu và API trong Java. Offset cũng bắt đầu từ 0: phần tử đầu tiên nằm ở vị trí 0. Vì vậy, công thức `page * size` có thể tính trực tiếp offset.

### 3.2. Khi giao diện đánh số trang từ 1

Một số giao diện hiển thị Trang 1, Trang 2, Trang 3 cho người dùng. Nếu API của bạn cũng nhận số trang bắt đầu từ 1, cần chuyển đổi trước khi tạo `PageRequest`:

```java
int pageNumberFromUi = 1;
int pageIndex = pageNumberFromUi - 1;
Pageable pageable = PageRequest.of(pageIndex, 10);
```

Trong trường hợp này, UI gửi `1` để chỉ trang đầu tiên, còn Spring Data nhận `0`. Hãy xác định rõ hợp đồng của API: tham số `page` bắt đầu từ 0 hay 1. Không trừ 1 hai lần và cũng không chuyển đổi nếu client đã gửi zero-based index.

## 4. Tạo PageRequest

### 4.1. Chỉ định trang và kích thước

```java
Pageable pageable = PageRequest.of(0, 20);
```

Yêu cầu này lấy tối đa 20 phần tử đầu tiên. Mặc định không có thứ tự sắp xếp cụ thể (`Sort.unsorted()`). Nếu cần kết quả ổn định, nên chỉ định `Sort` rõ ràng.

### 4.2. Kèm Sort

```java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by("title").ascending());
```

Ví dụ sắp xếp theo tiêu đề giảm dần:

```java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by("title").descending());
```

### 4.3. Sắp xếp theo nhiều thuộc tính

```java
Sort sort = Sort.by(
        Sort.Order.asc("title"),
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("id"));

Pageable pageable = PageRequest.of(0, 20, sort);
```

Database sẽ sắp xếp theo `title` tăng dần trước. Nếu nhiều bản ghi cùng tiêu đề, `createdAt` giảm dần được dùng tiếp; nếu vẫn bằng nhau, `id` tăng dần phân định thứ tự.

**Nên thêm một tiêu chí duy nhất như `id` làm tiêu chí cuối** khi phân trang. Nếu chỉ sắp xếp theo một thuộc tính có nhiều giá trị trùng nhau, thứ tự giữa các bản ghi đồng hạng không được bảo đảm. Điều đó có thể khiến bản ghi xuất hiện lặp hoặc bị bỏ qua giữa các lần đọc trang, đặc biệt khi dữ liệu thay đổi.

### 4.4. Tạo Sort trước rồi truyền vào PageRequest

Bạn có thể tái sử dụng một `Sort`:

```java
Sort newestFirst = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id"));

Pageable firstPage = PageRequest.of(0, 25, newestFirst);
Pageable nextPage = PageRequest.of(1, 25, newestFirst);
```

`PageRequest` là immutable. Các thao tác như `next()`, `previousOrFirst()`, `first()` hoặc `withPage(...)` trả về một yêu cầu mới; chúng không sửa object hiện tại.

## 5. Quy tắc sắp xếp với Sort

`Sort` mô tả thứ tự theo thuộc tính của Entity, không theo tên cột vật lý trong database.

Giả sử Entity có:

```java
@Column(name = "created_at")
private Instant createdAt;
```

Thuộc tính cần dùng trong Sort là `createdAt`, dù tên cột database là `created_at`:

```java
Sort.by(Sort.Order.desc("createdAt"));
```

Các kiểu sắp xếp thường dùng:

```java
Sort ascending = Sort.by("title").ascending();
Sort descending = Sort.by("title").descending();

Sort combined = Sort.by("status").ascending()
        .and(Sort.by("createdAt").descending());
```

### 5.1. Kiểm soát thuộc tính sort từ request

Không đưa trực tiếp tên thuộc tính do client gửi vào `Sort` mà không kiểm tra. Hãy whitelist những trường API cho phép sắp xếp:

```java
private static final Set<String> ALLOWED_SORT_FIELDS = Set.of(
        "title", "createdAt", "id");

Sort toSort(String requestedField, boolean descending) {
    String field = ALLOWED_SORT_FIELDS.contains(requestedField)
            ? requestedField
            : "createdAt";

    Sort.Order order = descending
            ? Sort.Order.desc(field)
            : Sort.Order.asc(field);

    return Sort.by(order).and(Sort.by(Sort.Order.desc("id")));
}
```

Đây là ví dụ minh họa; trong ứng dụng thực tế, đặt helper ở một lớp phù hợp và xử lý tên field không hợp lệ theo hợp đồng API. Whitelist tránh lỗi do property không tồn tại và ngăn client yêu cầu sắp xếp theo các thuộc tính không được công bố.

`Sort.NullHandling` có thể mô tả mong muốn về vị trí giá trị null, nhưng đây là hint cho datastore/provider. Nếu vị trí null ảnh hưởng trực tiếp đến nghiệp vụ, cần xác nhận hành vi trên database đang dùng.

## 6. Page, Slice và List

Repository có thể trả về các kiểu kết quả khác nhau khi nhận `Pageable`.

| Kiểu trả về | Nội dung | Có tổng số phần tử/trang? |
| --- | --- | --- |
| `Page<T>` | Nội dung trang và metadata phân trang. | Có `getTotalElements()` và `getTotalPages()`. |
| `Slice<T>` | Nội dung trang và thông tin còn trang trước/sau. | Không có tổng số phần tử hoặc tổng số trang. |
| `List<T>` | Chỉ danh sách phần tử của trang được yêu cầu. | Không có metadata phân trang. |

### 6.1. Page<T>

`Page<T>` phù hợp khi giao diện cần hiển thị tổng số kết quả hoặc tổng số trang, ví dụ “1–20 trên 243 sản phẩm”.

Các phương thức hữu ích:

| Phương thức | Ý nghĩa |
| --- | --- |
| `getContent()` | Danh sách phần tử trong trang hiện tại. |
| `getNumber()` | Index trang hiện tại, bắt đầu từ 0. |
| `getSize()` | Kích thước trang được yêu cầu. |
| `getNumberOfElements()` | Số phần tử thực tế trong trang hiện tại. |
| `getTotalElements()` | Tổng số phần tử thỏa điều kiện. |
| `getTotalPages()` | Tổng số trang. |
| `hasNext()` | Có trang kế tiếp hay không. |
| `hasPrevious()` | Có trang trước hay không. |
| `isFirst()` / `isLast()` | Trang hiện tại có phải trang đầu/cuối hay không. |

Ví dụ, nếu có 43 kết quả và size là 20, tổng số trang là 3. Trang index 2 là trang cuối, chỉ có 3 phần tử.

### 6.2. Slice<T>

`Slice<T>` phù hợp khi giao diện chỉ cần nút “Tải thêm” hoặc “Trang tiếp theo” mà không cần biết tổng số kết quả.

```java
Slice<Article> findByPublishedTrue(Pageable pageable);
```

Provider thường lấy thêm một phần tử để xác định có trang tiếp theo hay không. `Slice` tránh nhu cầu tính tổng số dòng như `Page`, nên có thể tiết kiệm chi phí với bảng lớn hoặc điều kiện lọc phức tạp.

### 6.3. List<T> với Pageable

```java
List<Article> findByPublishedTrue(Pageable pageable);
```

Kết quả chỉ là danh sách của trang yêu cầu. Nếu Service cần số trang, tổng số kết quả hoặc cờ `hasNext`, hãy chọn `Page` hoặc `Slice`.

## 7. Repository dùng Pageable

Ví dụ dưới đây dùng Entity `Article` có tiêu đề, trạng thái xuất bản và thời điểm tạo.

`src/main/java/com/example/articles/Article.java`:

```java
package com.example.articles;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;

@Entity
@Table(name = "articles")
public class Article {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 160)
    private String title;

    @Column(nullable = false)
    private boolean published;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected Article() {
        // JPA cần constructor không tham số.
    }

    public Article(String title, boolean published, Instant createdAt) {
        if (title == null || title.isBlank() || title.length() > 160) {
            throw new IllegalArgumentException("Title is required");
        }
        if (createdAt == null) {
            throw new IllegalArgumentException("Created time is required");
        }
        this.title = title.trim();
        this.published = published;
        this.createdAt = createdAt;
    }

    public Long getId() { return id; }
    public String getTitle() { return title; }
    public boolean isPublished() { return published; }
    public Instant getCreatedAt() { return createdAt; }
}
```

`src/main/java/com/example/articles/ArticleRepository.java`:

```java
package com.example.articles;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ArticleRepository extends JpaRepository<Article, Long> {
    Page<Article> findByPublishedTrue(Pageable pageable);

    Slice<Article> findByTitleContainingIgnoreCase(String keyword, Pageable pageable);
}
```

Spring Data tạo implementation cho các phương thức này. `Pageable` mang page index, size và Sort; derived query `findByPublishedTrue` lọc những bài đã xuất bản.

## 8. Sử dụng PageRequest trong Service

Service có thể tạo `PageRequest`, gọi repository và trả lại Page:

```java
package com.example.articles;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class ArticleQueryService {
    private static final int MAX_PAGE_SIZE = 100;

    private final ArticleRepository repository;

    public ArticleQueryService(ArticleRepository repository) {
        this.repository = repository;
    }

    public Page<Article> findPublished(int page, int size) {
        if (page < 0) {
            throw new IllegalArgumentException("Page index must be zero or greater");
        }
        if (size < 1 || size > MAX_PAGE_SIZE) {
            throw new IllegalArgumentException("Page size must be between 1 and 100");
        }

        Sort sort = Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id"));
        Pageable pageable = PageRequest.of(page, size, sort);
        return repository.findByPublishedTrue(pageable);
    }
}
```

Service kiểm tra page index không âm và giới hạn size để tránh một request yêu cầu hàng trăm nghìn bản ghi. `PageRequest.of` cũng kiểm tra page index và size; việc kiểm tra ở Service giúp trả lỗi nghiệp vụ rõ ràng và áp dụng giới hạn API.

## 9. Ví dụ API: page zero-based và page one-based

### 9.1. API nhận page zero-based

Đây là cách truyền thẳng tham số API vào Spring Data:

```java
package com.example.articles;

import org.springframework.data.domain.Page;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/articles")
public class ArticleController {
    private final ArticleQueryService service;

    public ArticleController(ArticleQueryService service) {
        this.service = service;
    }

    @GetMapping
    public Page<Article> list(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        return service.findPublished(page, size);
    }
}
```

Request đầu tiên:

```http
GET /api/articles?page=0&size=20
```

Request trang thứ hai:

```http
GET /api/articles?page=1&size=20
```

### 9.2. API nhận page number bắt đầu từ 1

Nếu API công bố số trang theo cách đếm thông thường, có thể nhận `pageNumber` bắt đầu từ 1 và chuyển đổi:

```java
public Page<Article> findPublishedByPageNumber(int pageNumber, int size) {
    if (pageNumber < 1) {
        throw new IllegalArgumentException("Page number must be at least 1");
    }
    int pageIndex = pageNumber - 1;
    return findPublished(pageIndex, size);
}
```

Ví dụ `pageNumber = 1` được chuyển thành `pageIndex = 0`. Không dùng cách này nếu client đã gửi page index bắt đầu từ 0.

Trong API thực tế, hãy đặt tên tham số rõ ràng (`page` hoặc `pageNumber`) và ghi rõ quy ước trong OpenAPI/API documentation. Điều đó tránh hiểu nhầm giữa page index và số thứ tự trang hiển thị.

## 10. PageRequest và cách điều hướng trang

`PageRequest` cung cấp các thao tác tạo yêu cầu trang tiếp theo hoặc quay lại:

```java
PageRequest current = PageRequest.of(2, 20);

Pageable next = current.next();
Pageable previous = current.previousOrFirst();
Pageable first = current.first();
Pageable samePageWithNewSort = current.withSort(Sort.by("title").ascending());
```

Với `current` có page index 2:
- `next()` tạo page index 3.
- `previousOrFirst()` tạo page index 1.
- `first()` tạo page index 0.
- `withSort(...)` giữ page index và size, thay đổi quy tắc sort.

Bạn cũng có thể dùng `withPage(0)` để tạo yêu cầu cho trang đầu. Các method này trả về object mới; cần giữ kết quả trả về nếu muốn dùng.

## 11. Offset pagination và giới hạn của nó

PageRequest thông thường dùng offset pagination. Với page index và size, database lấy dữ liệu bắt đầu từ offset tương ứng, thường thông qua `LIMIT` và `OFFSET` hoặc cú pháp tương đương của dialect.

Ví dụ `PageRequest.of(3, 25)` có offset 75. Khi page index tăng rất lớn, database có thể phải bỏ qua nhiều dòng trước khi trả về trang cần lấy. Vì vậy, offset pagination có thể chậm ở các trang sâu.

Các điểm cần lưu ý:
- Giữ page size có giới hạn.
- Luôn chỉ định thứ tự ổn định và thêm tiêu chí duy nhất.
- Với màn hình cần nhảy tới trang bất kỳ và tổng số trang, offset pagination thường phù hợp.
- Với luồng dữ liệu rất lớn chỉ cần tải tiếp, cân nhắc keyset/scrolling pagination hoặc cursor-based API.

Keyset pagination dùng giá trị của bản ghi cuối trang trước làm mốc cho trang tiếp theo, ví dụ `createdAt < lastCreatedAt` hoặc cặp `(createdAt, id)`. Cách này tránh offset lớn nhưng không hỗ trợ nhảy tùy ý tới trang số 500 dễ dàng. Cần chọn theo trải nghiệm API và thứ tự dữ liệu.

## 12. Page, metadata và chuyển đổi DTO

`Page<T>` có thể chuyển đổi nội dung sang kiểu DTO bằng `map()` mà vẫn giữ metadata phân trang:

```java
public record ArticleSummary(Long id, String title) {
    public static ArticleSummary from(Article article) {
        return new ArticleSummary(article.getId(), article.getTitle());
    }
}

Page<ArticleSummary> summaries = articleRepository
        .findByPublishedTrue(pageable)
        .map(ArticleSummary::from);
```

Điều này giúp API chỉ trả các field cần thiết mà vẫn giữ `getNumber()`, `getSize()`, `getTotalElements()` và `getTotalPages()`.

Không nên phụ thuộc vào toàn bộ cấu trúc JSON nội bộ của `PageImpl` làm hợp đồng API lâu dài. Nếu cần response ổn định, tạo DTO riêng:

```java
import java.util.List;

public record PageResponse<T>(
        List<T> content,
        int page,
        int size,
        long totalElements,
        int totalPages,
        boolean first,
        boolean last) {

    public static <T> PageResponse<T> from(Page<T> page) {
        return new PageResponse<>(
                page.getContent(),
                page.getNumber(),
                page.getSize(),
                page.getTotalElements(),
                page.getTotalPages(),
                page.isFirst(),
                page.isLast());
    }
}
```

## 13. Page và chi phí count query

Khi trả `Page<T>`, Spring Data cần tổng số kết quả để tính `getTotalElements()` và `getTotalPages()`. Với nhiều truy vấn, điều đó có thể yêu cầu một count query bổ sung. Framework có thể tối ưu và suy ra tổng trong một số trường hợp, nhưng không nên giả định mọi truy vấn Page chỉ chạy đúng một SQL statement.

Với bảng lớn, count query phức tạp hoặc join nhiều bảng có thể tốn kém. Khi giao diện chỉ cần biết còn dữ liệu tiếp theo, dùng `Slice<T>`:

```java
Slice<Article> findByPublishedTrue(Pageable pageable);
```

`Slice` không cung cấp tổng số kết quả. Provider thường đọc thêm một dòng ngoài page size để xác định `hasNext()`. Đây là lựa chọn phù hợp cho nút “Tải thêm” hoặc cuộn vô hạn.

## 14. Xử lý trang vượt quá dữ liệu

Giả sử có 23 bài viết và page size 10:

| Page index | Nội dung | `getNumberOfElements()` | `hasNext()` |
| ---: | --- | ---: | --- |
| 0 | Bài 1–10 | 10 | true |
| 1 | Bài 11–20 | 10 | true |
| 2 | Bài 21–23 | 3 | false |
| 3 | Không có bài nào | 0 | false |

Trang vượt quá dữ liệu thường trả về Page rỗng, không tự động quay về trang cuối. API có thể chọn trả trang rỗng, trả lỗi 404/400 hoặc điều chỉnh page về cuối; hãy xác định hành vi nhất quán trong hợp đồng API.

Không dùng `getSize()` để suy ra số phần tử thực tế trong trang cuối. Hãy dùng `getNumberOfElements()` hoặc `getContent().size()`.

## 15. Kiểm thử với H2

Ví dụ dùng Java 17+, Spring Boot 3.5.0, `spring-boot-starter-data-jpa`, H2 và `spring-boot-starter-test`.

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:pagingdb;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=true
```

`src/test/java/com/example/articles/ArticleRepositoryPagingTest.java`:

```java
package com.example.articles;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Sort;

@DataJpaTest
class ArticleRepositoryPagingTest {
    @Autowired
    private ArticleRepository repository;

    @Test
    void pageIndexStartsAtZeroAndReturnsCorrectMetadata() {
        repository.saveAll(List.of(
                new Article("Gamma", true, Instant.parse("2026-01-03T00:00:00Z")),
                new Article("Alpha", true, Instant.parse("2026-01-01T00:00:00Z")),
                new Article("Beta", true, Instant.parse("2026-01-02T00:00:00Z")),
                new Article("Hidden", false, Instant.parse("2026-01-04T00:00:00Z"))));
        repository.flush();

        Page<Article> first = repository.findByPublishedTrue(
                PageRequest.of(0, 2, Sort.by("title").ascending().and(Sort.by("id").ascending())));

        assertThat(first.getNumber()).isZero();
        assertThat(first.getSize()).isEqualTo(2);
        assertThat(first.getNumberOfElements()).isEqualTo(2);
        assertThat(first.getContent()).extracting(Article::getTitle)
                .containsExactly("Alpha", "Beta");
        assertThat(first.getTotalElements()).isEqualTo(3);
        assertThat(first.getTotalPages()).isEqualTo(2);
        assertThat(first.hasNext()).isTrue();

        Page<Article> second = repository.findByPublishedTrue(
                PageRequest.of(1, 2, Sort.by("title").ascending().and(Sort.by("id").ascending())));

        assertThat(second.getNumber()).isEqualTo(1);
        assertThat(second.getNumberOfElements()).isEqualTo(1);
        assertThat(second.getContent()).extracting(Article::getTitle)
                .containsExactly("Gamma");
        assertThat(second.isLast()).isTrue();
        assertThat(second.hasNext()).isFalse();
    }

    @Test
    void sliceExposesWhetherAnotherPageExists() {
        repository.saveAll(List.of(
                new Article("Alpha", true, Instant.parse("2026-01-01T00:00:00Z")),
                new Article("Beta", true, Instant.parse("2026-01-02T00:00:00Z")),
                new Article("Gamma", true, Instant.parse("2026-01-03T00:00:00Z"))));
        repository.flush();

        Slice<Article> slice = repository.findByTitleContainingIgnoreCase(
                "a", PageRequest.of(0, 2, Sort.by("title").ascending()));

        assertThat(slice.getContent()).hasSize(2);
        assertThat(slice.hasNext()).isTrue();
    }
}
```

Chạy kiểm thử từ thư mục chứa `pom.xml`:

```bash
mvn test
```

Kết quả mong đợi là Maven kết thúc với `BUILD SUCCESS`. Test đầu xác nhận index 0 là trang đầu tiên, index 1 là trang thứ hai, Sort được áp dụng và metadata tổng số được tính đúng. Test thứ hai kiểm tra `Slice.hasNext()`. Đây là kết quả kỳ vọng của ví dụ; chưa có log build thực tế.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Trang đầu bị bỏ qua | Gửi `page=1` trực tiếp vào `PageRequest.of` trong khi client đánh số từ 1. | Chuyển `pageNumber - 1` đúng một lần hoặc thống nhất API zero-based. |
| `PageRequest` ném `IllegalArgumentException` | Page index âm hoặc page size không dương. | Validate đầu vào trước khi tạo request. |
| Trang có kết quả lặp hoặc thiếu giữa các lần đọc | Sort không ổn định hoặc dữ liệu thay đổi khi đang phân trang. | Thêm tiêu chí duy nhất như `id`; cân nhắc snapshot/cursor cho dữ liệu biến động. |
| Thứ tự sắp xếp không đúng | Dùng tên cột database thay cho tên thuộc tính Entity. | Dùng property Java như `createdAt`, không dùng `created_at`. |
| API trả quá nhiều dữ liệu | Client có thể yêu cầu page size rất lớn. | Đặt giới hạn tối đa ở Controller/Service. |
| `Page` chậm hơn dự kiến | Count query có thể tốn kém. | Dùng `Slice` nếu không cần tổng số; tối ưu query/count query. |
| Trang cuối có ít phần tử hơn page size | Tổng số kết quả không chia hết cho page size. | Dùng `getNumberOfElements()` để đọc số phần tử thực tế. |
| Trang vượt quá dữ liệu trả rỗng | Page index lớn hơn trang cuối. | Xác định rõ API trả rỗng, báo lỗi hay điều chỉnh về trang cuối. |
| Sort field gây lỗi | Client gửi property không tồn tại hoặc không được phép. | Whitelist sort field và cung cấp default sort. |

## 17. Nguyên tắc sử dụng trong dự án

1. Nhớ `PageRequest.of(page, size)` dùng page index zero-based; index `0` là trang đầu.
2. Ghi rõ quy ước page bắt đầu từ 0 hay 1 trong hợp đồng API và chỉ chuyển đổi một lần.
3. Kiểm tra page không âm và size trong giới hạn hợp lý trước khi tạo PageRequest.
4. Luôn đặt sort ổn định; thêm ID làm tiêu chí phụ khi các thuộc tính chính có thể trùng.
5. Dùng tên thuộc tính Java của Entity khi tạo `Sort`, không dùng tên cột vật lý.
6. Dùng `Page` khi cần tổng số kết quả; dùng `Slice` khi chỉ cần biết có dữ liệu tiếp theo; dùng `List` khi không cần metadata.
7. Không dựa vào `getSize()` để xác định số phần tử thực tế của trang cuối.
8. Cân nhắc keyset/cursor pagination khi offset lớn hoặc dữ liệu thay đổi liên tục.
9. Không công bố trực tiếp cấu trúc nội bộ của `PageImpl` như một API contract lâu dài; dùng response DTO nếu cần định dạng ổn định.
10. Kiểm thử cả trang đầu, trang kế tiếp, trang cuối, trang rỗng, Sort và metadata.

## 18. Checklist hoàn thành

- [ ] Giải thích được `Pageable` và `PageRequest`.
- [ ] Tạo được `PageRequest.of(0, size)` cho trang đầu tiên.
- [ ] Tính được offset bằng `page index * page size`.
- [ ] Chuyển đổi đúng giữa page number bắt đầu từ 1 và page index bắt đầu từ 0.
- [ ] Kết hợp được `PageRequest` với `Sort` một hoặc nhiều thuộc tính.
- [ ] Hiểu vì sao cần tiêu chí sắp xếp phụ duy nhất.
- [ ] Đọc được metadata của `Page` và `Slice`.
- [ ] Chọn đúng `Page`, `Slice` hoặc `List` theo nhu cầu.
- [ ] Giới hạn page size và whitelist sort field từ API.
- [ ] Chạy được integration test cho nội dung trang, thứ tự và metadata.

Khi hoàn thành, bạn có thể xây dựng API phân trang Spring Data JPA đúng zero-based index, sắp xếp ổn định và trả metadata phù hợp với trải nghiệm người dùng.