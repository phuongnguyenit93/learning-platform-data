# Giới hạn số kết quả bằng Top, First hoặc Limit theo phiên bản

## 1. Mục tiêu

Spring Data JPA cung cấp nhiều cách giới hạn số bản ghi trả về từ Repository. Hai từ khóa `Top` và `First` được đặt trong tên derived query; `Limit` là tham số đặc biệt cho phép truyền số lượng tối đa khi gọi phương thức. Cách chọn phụ thuộc vào phiên bản Spring Data và nhu cầu có cần sắp xếp, phân trang hay giới hạn động hay không.

Sau bài học, bạn có thể:
- Dùng `Top` và `First` để giới hạn kết quả ngay trong tên phương thức.
- Hiểu số lượng mặc định khi không ghi số sau `Top` hoặc `First`.
- Dùng `Sort` để chọn đúng K bản ghi mới nhất, lớn nhất hoặc ưu tiên nhất.
- Dùng `Limit.of(n)` và `Limit.unlimited()` khi phiên bản Spring Data hỗ trợ.
- Phân biệt giới hạn tổng số kết quả với phân trang có offset.
- Kết hợp `Top`/`First` với `Pageable`, đồng thời nhận biết các tham số không được kết hợp.
- Chọn kiểu trả về `List`, `Optional`, `Page` hoặc `Slice` phù hợp.
- Kiểm thử số lượng, thứ tự và các trường hợp không có kết quả.

## 2. Vì sao cần giới hạn kết quả?

Nhiều use case chỉ cần một số bản ghi đầu tiên:

- Lấy 5 bài viết mới nhất để hiển thị trên trang chủ.
- Tìm sản phẩm có giá thấp nhất hoặc cao nhất.
- Lấy đơn hàng gần nhất của một khách hàng.
- Tìm một bản ghi phù hợp đầu tiên theo thứ tự ưu tiên.
- Hiển thị tối đa 10 gợi ý tìm kiếm.

Giới hạn ở tầng Repository giúp database chỉ trả số dòng cần thiết. Tuy nhiên, giới hạn phải đi cùng thứ tự sắp xếp rõ ràng. Nếu không có `ORDER BY`, database không bảo đảm bản ghi nào sẽ được xem là đầu tiên.

## 3. Dùng Top và First trong tên derived query

`Top` và `First` là hai từ khóa tương đương để giới hạn số kết quả trong tên phương thức. Có thể thêm một số nguyên ngay sau từ khóa để chỉ số lượng tối đa.

```java
List<Article> findTop5ByStatus(ArticleStatus status);

List<Article> findFirst10ByStatus(ArticleStatus status);

Optional<Article> findFirstBySlug(String slug);
```

Ý nghĩa:

| Tên phương thức | Giới hạn |
| --- | ---: |
| `findTop5ByStatus(...)` | Tối đa 5 kết quả. |
| `findFirst10ByStatus(...)` | Tối đa 10 kết quả. |
| `findFirstBySlug(...)` | Mặc định tối đa 1 kết quả. |
| `findTopByStatus(...)` | Mặc định tối đa 1 kết quả. |

Nếu không ghi số sau `Top` hoặc `First`, giới hạn mặc định là 1. `Top` và `First` có thể dùng thay thế nhau; không cần đặt cả hai trong cùng một tên phương thức.

### 3.1. Vị trí của từ khóa

Từ khóa giới hạn nằm trong phần subject của method name, tức phần trước `By`:

```java
findTop5ByStatusAndCategory(ArticleStatus status, String category);
```

Phần `Top5` giới hạn tối đa 5 dòng; phần `StatusAndCategory` tạo điều kiện lọc. Có thể kết hợp với các predicate và keyword khác của derived query.

### 3.2. Trả về một kết quả

Khi giới hạn là một bản ghi, có thể trả về Entity hoặc `Optional<Entity>`. `Optional` giúp thể hiện rõ trường hợp không tìm thấy kết quả:

```java
Optional<Article> findFirstBySlug(String slug);
```

Nếu không có bài viết khớp slug, Repository trả `Optional.empty()`. Nếu có nhiều dòng khớp, phương thức vẫn chỉ trả tối đa một dòng.

Với giới hạn lớn hơn 1, dùng `List`, `Slice` hoặc `Page` tùy nhu cầu. Không khai báo một method có thể trả nhiều kết quả dưới dạng một Entity đơn nếu không có giới hạn một dòng.

## 4. Luôn kết hợp giới hạn với thứ tự ổn định

`Top` hoặc `First` chỉ quy định số lượng tối đa. Chúng không tự xác định bản ghi nào đứng đầu. Hãy dùng `OrderBy` trong tên method hoặc truyền `Sort`.

### 4.1. Sắp xếp cố định bằng OrderBy

```java
List<Article> findTop5ByStatusOrderByPublishedAtDescIdDesc(ArticleStatus status);

Optional<Article> findFirstByStatusOrderByPublishedAtDescIdDesc(ArticleStatus status);
```

Truy vấn đầu lấy tối đa 5 bài theo trạng thái, sắp xếp thời điểm xuất bản mới nhất trước. `id` giảm dần là tiêu chí phụ để phân định khi hai bài có cùng `publishedAt`.

### 4.2. Sắp xếp động bằng Sort

Nếu nhiều màn hình cần các thứ tự khác nhau, nhận `Sort` làm tham số:

```java
List<Article> findTop5ByStatus(ArticleStatus status, Sort sort);
```

Cách gọi:

```java
Sort newestFirst = Sort.by(
        Sort.Order.desc("publishedAt"),
        Sort.Order.desc("id"));

List<Article> newest = repository.findTop5ByStatus(
        ArticleStatus.PUBLISHED, newestFirst);
```

Sort dùng tên thuộc tính Java của Entity, ví dụ `publishedAt`, không dùng tên cột database như `published_at`.

### 4.3. Vì sao cần tiêu chí phụ?

Giả sử 20 bài viết có cùng thời điểm xuất bản. Nếu chỉ sắp xếp `publishedAt DESC`, thứ tự giữa các bài cùng thời điểm không xác định. Khi lấy Top 5, database có thể chọn các dòng khác nhau giữa các lần thực thi.

Hãy thêm khóa duy nhất làm tiêu chí cuối, ví dụ `id DESC`. Điều này giúp kết quả ổn định hơn khi dữ liệu không đổi. Nếu dữ liệu vẫn đang được thêm hoặc sửa giữa các lần gọi, offset pagination vẫn có thể dịch chuyển; với luồng lớn và thay đổi liên tục, hãy cân nhắc cursor/keyset scrolling.

## 5. Limit: giới hạn động qua tham số

`org.springframework.data.domain.Limit` là kiểu tham số đặc biệt để truyền giới hạn lúc gọi Repository thay vì mã hóa con số vào tên phương thức.

`Limit` được giới thiệu trong **Spring Data Commons 3.2**. Vì vậy, chỉ dùng API này khi phiên bản Spring Data trong dependency thực tế hỗ trợ nó. Các dự án Spring Boot nên để Spring Boot BOM quản lý phiên bản Spring Data đồng bộ; nếu dự án dùng Spring Data cũ hơn 3.2, dùng `Top`/`First` hoặc nâng cấp dependency theo kế hoạch.

Import:

```java
import org.springframework.data.domain.Limit;
```

Tạo giới hạn:

```java
Limit five = Limit.of(5);
Limit unlimited = Limit.unlimited();
```

- `Limit.of(5)` yêu cầu tối đa 5 kết quả.
- `Limit.unlimited()` biểu thị không đặt giới hạn động.
- Không truyền `null` thay cho Limit không giới hạn; dùng `Limit.unlimited()`.

### 5.1. Repository dùng Limit

```java
List<Article> findByStatus(ArticleStatus status, Limit limit);

List<Article> findByStatus(ArticleStatus status, Sort sort, Limit limit);
```

Phương thức thứ hai cho phép chọn cả thứ tự và giới hạn ở thời điểm gọi:

```java
List<Article> recent = repository.findByStatus(
        ArticleStatus.PUBLISHED,
        Sort.by(
                Sort.Order.desc("publishedAt"),
                Sort.Order.desc("id")),
        Limit.of(5));
```

Cùng một method có thể được gọi với `Limit.of(3)`, `Limit.of(10)` hoặc `Limit.unlimited()` tùy use case. Đây là điểm khác biệt chính so với `Top5`, vốn cố định số 5 trong tên phương thức.

### 5.2. Giới hạn số lượng ở tầng Service

Không nên nhận một số lượng tùy ý từ client rồi truyền thẳng xuống database. Hãy kiểm tra giới hạn tối đa của API:

```java
package com.example.articles;

import java.util.List;
import org.springframework.data.domain.Limit;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class ArticleQueryService {
    private static final int MAX_RESULTS = 50;

    private final ArticleRepository repository;

    public ArticleQueryService(ArticleRepository repository) {
        this.repository = repository;
    }

    public List<Article> findRecent(ArticleStatus status, int requestedLimit) {
        if (requestedLimit < 1 || requestedLimit > MAX_RESULTS) {
            throw new IllegalArgumentException(
                    "Limit must be between 1 and " + MAX_RESULTS);
        }

        Sort sort = Sort.by(
                Sort.Order.desc("publishedAt"),
                Sort.Order.desc("id"));

        return repository.findByStatus(status, sort, Limit.of(requestedLimit));
    }
}
```

Service xác định rõ miền giá trị hợp lệ. Trong API thật, có thể chuyển `IllegalArgumentException` thành lỗi HTTP 400 qua exception handler. Mức tối đa 50 chỉ là chính sách minh họa; hãy chọn giới hạn phù hợp với workload và trải nghiệm sản phẩm.

## 6. Chọn Top/First hay Limit?

| Nhu cầu | Nên dùng | Lý do |
| --- | --- | --- |
| Luôn lấy đúng tối đa 5 bản ghi cho một use case cố định | `Top5` hoặc `First5` | Ý định hiển thị ngay trong tên method. |
| Luôn lấy một bản ghi đầu tiên theo thứ tự xác định | `First` hoặc `Top` không kèm số | Mặc định giới hạn là 1; có thể trả `Optional`. |
| Số lượng thay đổi theo request hoặc cấu hình | `Limit.of(n)` | Truyền số lượng động khi gọi method. |
| Cần cùng method nhưng nhiều kiểu sắp xếp | `Sort` kết hợp `Top` hoặc `Limit` | Tách thứ tự khỏi điều kiện lọc. |
| Cần lấy từng trang có offset | `Pageable` | Có page index, page size và Sort. |
| Chỉ cần biết còn dữ liệu tiếp theo | `Slice` với `Pageable` | Không cần tổng số phần tử như `Page`. |

`Top`/`First` phù hợp khi giới hạn là một phần cố định của use case. `Limit` phù hợp khi số lượng là tham số của use case.

## 7. Kết hợp Top/First với Pageable

`Top` hoặc `First` có thể kết hợp với `Pageable`. Khi đó:

- `Top`/`First` xác định tổng số kết quả tối đa của truy vấn.
- `Pageable` chọn một phần của tập kết quả đã bị giới hạn, đồng thời có thể cung cấp Sort.

Ví dụ Repository:

```java
Page<Article> findTop10ByStatus(ArticleStatus status, Pageable pageable);
```

Gọi trang đầu và trang kế tiếp:

```java
Sort sort = Sort.by(
        Sort.Order.desc("publishedAt"),
        Sort.Order.desc("id"));

Page<Article> firstPage = repository.findTop10ByStatus(
        ArticleStatus.PUBLISHED, PageRequest.of(0, 4, sort));

Page<Article> secondPage = repository.findTop10ByStatus(
        ArticleStatus.PUBLISHED, PageRequest.of(1, 4, sort));
```

Toàn bộ truy vấn bị giới hạn tối đa 10 bài. Với page size 4, trang đầu lấy tối đa 4 bài đầu trong nhóm 10, trang thứ hai lấy tối đa 4 bài tiếp theo. Trang thứ ba có thể lấy 2 bài cuối. Metadata của `Page` được tính trong phạm vi kết quả đã giới hạn.

Không nhầm cách này với `Limit`: `Pageable` đã mang thông tin giới hạn và offset. Vì vậy, `Pageable` và `Limit` không được khai báo cùng một method.

## 8. Các tổ hợp tham số hợp lệ và không hợp lệ

Spring Data nhận diện `Sort`, `Pageable` và `Limit` là special parameters. Một số tổ hợp không được phép vì chúng mô tả cùng một khía cạnh của truy vấn.

| Tổ hợp | Hợp lệ? | Giải thích |
| --- | --- | --- |
| `Top`/`First` + `Sort` | Có | Giới hạn cố định, thứ tự thay đổi lúc gọi. |
| `Top`/`First` + `Pageable` | Có | Top đặt trần tổng số kết quả; Pageable chọn trang trong trần đó. |
| `Sort` + `Limit` | Có | Chọn thứ tự và số dòng tối đa động. |
| `Pageable` + `Sort` | Không | `Pageable` đã chứa Sort. |
| `Pageable` + `Limit` | Không | `Pageable` đã chứa giới hạn số dòng và offset. |
| `Top`/`First` + `Limit` | Không | Hai cơ chế cùng giới hạn một truy vấn; chọn một. |

Special parameter cùng loại chỉ nên xuất hiện một lần trong method signature. API nhận `Sort`, `Pageable` hoặc `Limit` yêu cầu truyền object không null; dùng `Sort.unsorted()`, `Pageable.unpaged()` hoặc `Limit.unlimited()` khi muốn không áp dụng khía cạnh tương ứng.

## 9. Page, Slice, List và Optional khi giới hạn kết quả

Chọn kiểu trả về theo thông tin mà caller cần:

| Kiểu trả về | Khi phù hợp |
| --- | --- |
| `Optional<Article>` | Tối đa một kết quả và muốn biểu diễn trường hợp không tìm thấy. |
| `Article` | Tối đa một kết quả và ứng dụng có chính sách xử lý absence riêng; cần cẩn thận với null. |
| `List<Article>` | Cần một nhóm K kết quả, không cần metadata trang. |
| `Slice<Article>` | Cần biết còn phần dữ liệu tiếp theo trong một truy vấn phân trang. |
| `Page<Article>` | Cần tổng số phần tử và tổng số trang trong phạm vi truy vấn. |

Với `Page`, Spring Data có thể chạy count query để tính metadata. Nếu chỉ cần vài kết quả mới nhất, `List` thường đơn giản hơn và không cần count. Nếu cần duyệt một tập kết quả theo trang mà không cần tổng số, cân nhắc `Slice`.

Với `Top10` kết hợp `Pageable`, tổng số kết quả và tổng số trang được tính trong giới hạn 10, không phải toàn bộ bảng.

## 10. Ví dụ hoàn chỉnh với Article

Ví dụ dùng Java 17+, Spring Boot 3.5.x và Spring Data JPA 3.5.x. `Limit` có từ Spring Data Commons 3.2, nên phiên bản 3.5.x hỗ trợ API này.

### 10.1. Enum ArticleStatus

`src/main/java/com/example/articles/ArticleStatus.java`:

```java
package com.example.articles;

public enum ArticleStatus {
    DRAFT,
    PUBLISHED,
    ARCHIVED
}
```

### 10.2. Entity Article

`src/main/java/com/example/articles/Article.java`:

```java
package com.example.articles;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
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

    @Column(nullable = false, unique = true, length = 100)
    private String slug;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private ArticleStatus status;

    @Column(name = "published_at")
    private Instant publishedAt;

    protected Article() {
        // JPA cần constructor không tham số.
    }

    public Article(String title, String slug, ArticleStatus status, Instant publishedAt) {
        if (title == null || title.isBlank() || title.length() > 160) {
            throw new IllegalArgumentException("Title is required");
        }
        if (slug == null || slug.isBlank() || slug.length() > 100) {
            throw new IllegalArgumentException("Slug is required");
        }
        if (status == null) {
            throw new IllegalArgumentException("Status is required");
        }
        this.title = title.trim();
        this.slug = slug.trim();
        this.status = status;
        this.publishedAt = publishedAt;
    }

    public Long getId() { return id; }
    public String getTitle() { return title; }
    public String getSlug() { return slug; }
    public ArticleStatus getStatus() { return status; }
    public Instant getPublishedAt() { return publishedAt; }
}
```

### 10.3. ArticleRepository

`src/main/java/com/example/articles/ArticleRepository.java`:

```java
package com.example.articles;

import java.util.List;
import java.util.Optional;
import org.springframework.data.domain.Limit;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ArticleRepository extends JpaRepository<Article, Long> {
    List<Article> findTop5ByStatusOrderByPublishedAtDescIdDesc(ArticleStatus status);

    Optional<Article> findFirstBySlug(String slug);

    List<Article> findTop5ByStatus(ArticleStatus status, Sort sort);

    List<Article> findByStatus(ArticleStatus status, Sort sort, Limit limit);

    Page<Article> findTop10ByStatus(ArticleStatus status, Pageable pageable);
}
```

Phương thức đầu tiên giới hạn cố định 5 bài và sắp xếp tĩnh. Phương thức thứ hai trả về tối đa một bài theo slug. Phương thức thứ ba nhận Sort động nhưng vẫn giữ trần 5. Phương thức thứ tư nhận Limit động. Phương thức cuối kết hợp trần Top 10 với phân trang.

## 11. Kiểm thử giới hạn và thứ tự với H2

Ví dụ dùng `spring-boot-starter-data-jpa`, H2 và `spring-boot-starter-test`. H2 có thể dùng để kiểm tra derived query cơ bản; nếu ứng dụng phụ thuộc cú pháp hoặc hành vi đặc thù database, hãy kiểm thử thêm trên engine production.

`src/test/java/com/example/articles/ArticleRepositoryLimitTest.java`:

```java
package com.example.articles;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.data.domain.Limit;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

@DataJpaTest
class ArticleRepositoryLimitTest {
    @Autowired
    private ArticleRepository repository;

    private void insertArticles() {
        repository.saveAll(List.of(
                new Article("Article 1", "article-1", ArticleStatus.PUBLISHED, Instant.parse("2026-01-01T00:00:00Z")),
                new Article("Article 2", "article-2", ArticleStatus.PUBLISHED, Instant.parse("2026-01-02T00:00:00Z")),
                new Article("Article 3", "article-3", ArticleStatus.PUBLISHED, Instant.parse("2026-01-03T00:00:00Z")),
                new Article("Article 4", "article-4", ArticleStatus.PUBLISHED, Instant.parse("2026-01-04T00:00:00Z")),
                new Article("Article 5", "article-5", ArticleStatus.PUBLISHED, Instant.parse("2026-01-05T00:00:00Z")),
                new Article("Article 6", "article-6", ArticleStatus.PUBLISHED, Instant.parse("2026-01-06T00:00:00Z")),
                new Article("Draft", "draft", ArticleStatus.DRAFT, null)));
        repository.flush();
    }

    private Sort newestFirst() {
        return Sort.by(
                Sort.Order.desc("publishedAt"),
                Sort.Order.desc("id"));
    }

    @Test
    void topKeywordReturnsOnlyFiveNewestRows() {
        insertArticles();

        List<Article> result = repository.findTop5ByStatusOrderByPublishedAtDescIdDesc(
                ArticleStatus.PUBLISHED);

        assertThat(result).hasSize(5);
        assertThat(result).extracting(Article::getTitle)
                .containsExactly("Article 6", "Article 5", "Article 4", "Article 3", "Article 2");
    }

    @Test
    void limitParameterAppliesDynamicMaximumAndSort() {
        insertArticles();

        List<Article> result = repository.findByStatus(
                ArticleStatus.PUBLISHED, newestFirst(), Limit.of(3));

        assertThat(result).hasSize(3);
        assertThat(result).extracting(Article::getTitle)
                .containsExactly("Article 6", "Article 5", "Article 4");
    }

    @Test
    void firstQueryReturnsOptionalEmptyWhenNoRowMatches() {
        insertArticles();

        Optional<Article> result = repository.findFirstBySlug("missing-slug");

        assertThat(result).isEmpty();
    }

    @Test
    void pageableSelectsAWindowInsideTheTopTenCap() {
        insertArticles();

        Page<Article> page = repository.findTop10ByStatus(
                ArticleStatus.PUBLISHED,
                PageRequest.of(1, 2, newestFirst()));

        assertThat(page.getTotalElements()).isEqualTo(6);
        assertThat(page.getTotalPages()).isEqualTo(3);
        assertThat(page.getNumber()).isEqualTo(1);
        assertThat(page.getContent()).extracting(Article::getTitle)
                .containsExactly("Article 4", "Article 3");
    }
}
```

Test đầu xác nhận `Top5` giới hạn và sắp xếp đúng. Test thứ hai xác nhận `Limit.of(3)` thay đổi số lượng tối đa tại thời điểm gọi. Test thứ ba xác nhận `First` trả `Optional.empty()` khi không có dòng phù hợp. Test cuối xác nhận `Pageable` chọn trang thứ hai trong tập kết quả bị giới hạn.

Chạy test từ thư mục chứa `pom.xml`:

```bash
mvn test
```

Kết quả mong đợi là `BUILD SUCCESS` và cả bốn test đều thành công. Đây là kết quả kỳ vọng của ví dụ, không phải log build thực tế.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Lấy sai bản ghi đầu tiên | Dùng `First`/`Top` mà không có Sort hoặc OrderBy. | Khai báo thứ tự rõ ràng và thêm ID làm tiêu chí phụ. |
| Không biên dịch được import `Limit` | Spring Data Commons cũ hơn 3.2 hoặc dependency bị override. | Kiểm tra dependency tree; dùng Top/First hoặc nâng Spring Data đồng bộ. |
| Method báo special parameter không hợp lệ | Kết hợp `Pageable` với `Limit`, `Pageable` với `Sort`, hoặc `Top`/`First` với `Limit`. | Chọn đúng một cơ chế giới hạn; Pageable đã có Sort và page size. |
| Kết quả vượt số lượng mong muốn | Nhầm `Pageable` với tổng giới hạn hoặc dùng một method không có Top/First/Limit. | Kiểm tra method signature và semantics của từng tham số. |
| `Optional` không phù hợp kiểu kết quả | Phương thức có thể trả nhiều hơn một kết quả. | Chỉ dùng Optional khi truy vấn được giới hạn tối đa một dòng. |
| API cho phép lấy quá nhiều dòng | Client điều khiển Limit hoặc page size không có giới hạn. | Validate số lượng và áp dụng mức tối đa ở Service/API. |
| Bản ghi trùng hoặc thiếu giữa các lần lấy | Sort không ổn định hoặc dữ liệu thay đổi giữa các lần gọi. | Thêm tiêu chí sort duy nhất; cân nhắc snapshot hoặc keyset scrolling. |
| `Limit` bị null | Caller không truyền special parameter hợp lệ. | Dùng `Limit.of(n)` hoặc `Limit.unlimited()`, không dùng null. |
| Dùng tên cột trong Sort gây lỗi | Sort phân giải theo thuộc tính Entity. | Dùng `publishedAt`, không dùng `published_at`. |

## 13. Nguyên tắc sử dụng

1. Dùng `Top` hoặc `First` khi giới hạn cố định là một phần rõ ràng của use case.
2. Dùng `Limit.of(n)` khi số lượng tối đa cần thay đổi theo request hoặc cấu hình và Spring Data Commons từ 3.2 trở lên.
3. Không dùng `Top`/`First` cùng `Limit`, hoặc `Pageable` cùng `Limit`.
4. Có thể kết hợp `Top`/`First` với `Pageable`; Top xác định trần tổng, Pageable chọn trang trong trần đó.
5. Luôn xác định thứ tự bằng `OrderBy` hoặc `Sort`; thêm ID làm tiêu chí cuối để phân định kết quả đồng hạng.
6. Dùng `Optional` cho truy vấn tối đa một kết quả, `List` cho nhóm kết quả, `Slice` khi cần biết còn trang tiếp theo và `Page` khi cần tổng số.
7. Kiểm tra giới hạn do client cung cấp và đặt mức tối đa hợp lý.
8. Dùng tên thuộc tính Java trong Sort, không dùng tên cột SQL.
9. Kiểm thử số lượng, thứ tự, trường hợp không có kết quả và tổ hợp Pageable/Top trên phiên bản Spring Data thực tế của dự án.

## 14. Checklist hoàn thành

- [ ] Viết được `findTop5By...` và `findFirstBy...`.
- [ ] Hiểu rằng không ghi số sau Top/First thì mặc định lấy tối đa một kết quả.
- [ ] Kết hợp Top/First với `OrderBy` và `Sort` để có thứ tự xác định.
- [ ] Biết `Limit` thuộc `org.springframework.data.domain` và có từ Spring Data Commons 3.2.
- [ ] Dùng được `Limit.of(n)` và `Limit.unlimited()`.
- [ ] Phân biệt giới hạn động `Limit` với page index/offset của `Pageable`.
- [ ] Nhận diện các tổ hợp tham số không hợp lệ.
- [ ] Kết hợp `Top` với `Pageable` khi cần phân trang trong một tập kết quả có trần.
- [ ] Chọn đúng `Optional`, `List`, `Slice` hoặc `Page`.
- [ ] Kiểm thử số lượng và thứ tự kết quả bằng `@DataJpaTest`.

## 15. Tài liệu tham khảo

- [Spring Data Commons — Defining Query Methods](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html)
- [Spring Data Commons 3.2 — Limit API](https://docs.spring.io/spring-data/commons/docs/3.2.3/api/org/springframework/data/domain/Limit.html)
- [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)

Khi hoàn thành, bạn có thể giới hạn số kết quả theo cách phù hợp với phiên bản Spring Data, tạo thứ tự ổn định và chọn giữa giới hạn cố định, giới hạn động hoặc phân trang theo nhu cầu của ứng dụng.