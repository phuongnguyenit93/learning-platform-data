# Top, First, OrderBy và giới hạn số kết quả

## Mục tiêu

Spring Data JPA cho phép giới hạn số kết quả ngay trong tên query method bằng `Top` hoặc `First`, sắp xếp bằng `OrderBy`, hoặc truyền điều kiện sắp xếp và phân trang ở runtime qua `Sort` và `Pageable`.

- `Top` và `First` giới hạn số bản ghi được trả về.
- `OrderBy` khai báo thứ tự cố định trong tên phương thức.
- `Sort` cho phép caller chọn thứ tự khi gọi repository.
- `Pageable` chọn trang, kích thước trang và có thể kèm sort.

Giới hạn kết quả giúp giảm dữ liệu truyền về ứng dụng và số entity cần hydrate. Tuy nhiên, hiệu năng còn phụ thuộc điều kiện lọc, thứ tự, index và execution plan của database.

## 1. Top và First trong tên query method

`Top` và `First` là các từ khóa giới hạn kết quả trong phần subject của query method, đứng trước `By`.

```java
List<Article> findTop5ByCategory(String category);
List<Article> findFirst5ByCategory(String category);
Optional<Article> findFirstByCategory(String category);
```

`Top` và `First` có cùng ý nghĩa giới hạn số kết quả. Số lượng có thể đặt ngay sau từ khóa; nếu bỏ số, giới hạn mặc định là một kết quả.

| Method | Giới hạn |
| --- | ---: |
| `findTopByCategory(...)` | 1 |
| `findFirstByCategory(...)` | 1 |
| `findTop3ByCategory(...)` | 3 |
| `findFirst10ByCategory(...)` | 10 |

Giới hạn được áp dụng ở query database, nên provider có thể sinh `LIMIT`, `FETCH FIRST`, `TOP` hoặc cú pháp tương đương tùy dialect. Ứng dụng chỉ nhận số hàng tối đa được yêu cầu.

### Chọn kiểu trả về

- `List<Article>` hoặc collection: nhận tối đa N phần tử, có thể rỗng.
- `Optional<Article>`: phù hợp với `First` không có số hoặc giới hạn một; kết quả không có bản ghi là `Optional.empty()`.
- `Article`: có thể dùng khi API cho phép kết quả không tồn tại được biểu diễn bằng `null`, nhưng `Optional` thường thể hiện rõ hơn.

Ví dụ:

```java
Optional<Article> newest = repository
        .findFirstByCategoryOrderByPublishedAtDescIdDesc("BOOK");
```

Nếu method trả về một entity hoặc `Optional` mà không có giới hạn một, nhưng query thực tế trả nhiều hàng, Spring Data có thể ném `IncorrectResultSizeDataAccessException`. Dùng `First`/`Top` khi nghiệp vụ thực sự muốn chọn một kết quả theo thứ tự xác định.

## 2. OrderBy: sắp xếp cố định trong tên method

`OrderBy` cho phép khai báo thứ tự sắp xếp ngay trong tên phương thức. Sau `OrderBy` là property Java của entity và hướng `Asc` hoặc `Desc`.

```java
List<Article> findTop3ByCategoryOrderByPublishedAtDesc(String category);
```

Method trên tìm bài thuộc category, sắp xếp `publishedAt` giảm dần và chỉ trả tối đa ba bài.

### Sắp xếp theo nhiều thuộc tính

Khi hai bản ghi có cùng giá trị ở thuộc tính chính, thêm thuộc tính phụ để thứ tự ổn định:

```java
List<Article> findTop3ByCategoryOrderByViewsDescIdDesc(String category);
```

Thứ tự là `views DESC`, sau đó `id DESC`. Nếu chỉ sắp xếp theo `views`, hai bài có cùng lượt xem có thể đổi thứ tự giữa các lần chạy vì database không cam kết thứ tự của các hàng có giá trị sort bằng nhau.

Với phân trang, sort ổn định đặc biệt quan trọng. Nếu thứ tự không duy nhất, một bản ghi có thể xuất hiện ở trang khác nhau hoặc bị bỏ qua khi dữ liệu thay đổi giữa các lần lấy trang.

### Property trong OrderBy là tên Java

Spring Data phân tích property của entity, không lấy tên cột SQL. Nếu entity có `publishedAt` nhưng cột database là `published_at`, method vẫn viết `OrderByPublishedAtDesc`.

## 3. Sort: sắp xếp động lúc gọi

Nếu thứ tự phụ thuộc vào yêu cầu màn hình hoặc caller, khai báo tham số `Sort`:

```java
List<Article> findTop5ByCategory(String category, Sort sort);
```

Caller chọn thứ tự:

```java
Sort sort = Sort.by(
        Sort.Order.desc("publishedAt"),
        Sort.Order.desc("id")
);

List<Article> latest = repository.findTop5ByCategory("BOOK", sort);
```

`Sort.Order` dùng tên property của entity. Có thể dùng `Sort.unsorted()` khi không cần thứ tự động. Hãy giới hạn các lựa chọn sort được phép ở tầng API; không chuyển trực tiếp mọi chuỗi do client gửi thành property mà không kiểm tra.

`Sort` không giới hạn số kết quả. Nếu cần vừa sắp xếp vừa giới hạn, kết hợp `Sort` với `Top`/`First` như ví dụ trên.

### Static OrderBy và dynamic Sort

`OrderBy` phù hợp khi thứ tự là một phần cố định của nghiệp vụ, ví dụ luôn chọn bản ghi mới nhất. `Sort` phù hợp khi caller được phép chọn thứ tự. Dùng một nguồn sắp xếp rõ ràng giúp API dễ đọc và tránh bất ngờ khi nhiều quy tắc sort cùng được cấu hình.

## 4. Pageable: phân trang với kích thước linh hoạt

`Pageable` chứa số trang, kích thước trang và có thể chứa `Sort`. Repository có thể khai báo:

```java
Page<Article> findByCategory(String category, Pageable pageable);
```

Caller:

```java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Order.desc("publishedAt"), Sort.Order.desc("id"))
);

Page<Article> page = repository.findByCategory("BOOK", pageable);
```

`PageRequest.of(0, 20, ...)` lấy trang đầu tiên với tối đa 20 hàng. Số trang bắt đầu từ 0.

### Page và Slice

| Kiểu trả về | Thông tin | Chi phí thường gặp |
| --- | --- | --- |
| `Page<T>` | Nội dung trang, tổng số hàng và tổng số trang | Có thể chạy thêm count query để biết tổng chính xác |
| `Slice<T>` | Nội dung trang và `hasNext()` | Thường chỉ cần lấy thêm một hàng để biết còn dữ liệu hay không, không cần tổng count |
| `List<T>` với `Pageable` | Chỉ nội dung trang | Không trả tổng số; phù hợp khi caller chỉ cần một đoạn dữ liệu |

Ví dụ dùng Slice:

```java
Slice<Article> findByCategoryAndActiveTrue(String category, Pageable pageable);
```

Nếu giao diện không cần hiển thị tổng số trang, `Slice` có thể tránh count query tốn kém. `Page` phù hợp khi cần tổng số chính xác để hiển thị hoặc điều hướng.

### Kết hợp Top/First với Pageable

Spring Data hỗ trợ giới hạn kết quả và phân trang trong các query method phù hợp. Khi kết hợp, phân trang được áp dụng bên trong tập kết quả đã bị giới hạn. Điều này có thể hữu ích cho một cửa sổ kết quả có kích thước tối đa, nhưng cần kiểm tra rõ semantics tổng số trang/count query trên phiên bản Spring Data JPA đang dùng.

Trong API thông thường, hãy chọn `Top`/`First` khi cần một số lượng tối đa cố định và chọn `Pageable` khi caller cần duyệt tập kết quả theo trang. Nếu cần cả hai, viết integration test xác nhận trang, tổng số và SQL được sinh.

## 5. SQL và chi phí thực thi

Ví dụ query:

```java
List<Article> findTop3ByCategoryOrderByViewsDescIdDesc(String category);
```

SQL khái niệm có thể tương tự:

```sql
select a.id, a.title, a.category, a.views
from articles a
where a.category = ?
order by a.views desc, a.id desc
fetch first 3 rows only;
```

Cú pháp giới hạn phụ thuộc database. SQL Server có thể dùng `TOP`, PostgreSQL/MySQL thường dùng `LIMIT`, trong khi một số database dùng `FETCH FIRST` hoặc cú pháp khác. Hibernate chọn cú pháp dựa trên dialect.

### Giới hạn kết quả không tự làm query rẻ

Top 3 chỉ yêu cầu trả tối đa ba hàng. Database vẫn phải tìm các hàng thỏa điều kiện và xác định ba hàng đứng đầu theo sort. Nếu không có index phù hợp, database có thể phải quét nhiều hàng rồi sort trước khi trả ba hàng.

Với filter `category` và sort `views DESC, id DESC`, index ghép theo các cột này có thể hữu ích:

```sql
create index ix_articles_category_views_id
    on articles(category, views desc, id desc);
```

Cú pháp index và khả năng tận dụng thứ tự DESC phụ thuộc hệ quản trị database. Hãy dùng `EXPLAIN` hoặc execution plan để xác nhận. Index giúp đọc nhưng làm tăng dung lượng và chi phí INSERT/UPDATE/DELETE.

### Offset pagination có thể đắt

Với trang sâu, database có thể phải bỏ qua nhiều hàng trước khi trả trang cần lấy. Ví dụ trang 500 với page size 20 có thể cần xử lý một lượng lớn hàng đứng trước tùy execution plan.

Khi cần duyệt tập dữ liệu lớn theo thứ tự ổn định, xem xét keyset pagination hoặc scrolling API được Spring Data hỗ trợ trong phiên bản phù hợp. Keyset dùng giá trị của bản ghi cuối trang trước làm điểm bắt đầu trang kế tiếp, thay vì bỏ qua một offset lớn.

## 6. Chọn method theo yêu cầu

| Nhu cầu | Method phù hợp |
| --- | --- |
| Lấy một bài mới nhất | `findFirstBy...OrderByPublishedAtDescIdDesc` |
| Lấy tối đa 5 bài phổ biến | `findTop5By...OrderByViewsDescIdDesc` |
| Caller tự chọn thứ tự, giới hạn 5 | `findTop5ByCategory(category, sort)` |
| Lấy trang bất kỳ và cần tổng số | `findByCategory(category, pageable)` trả `Page` |
| Lấy trang và chỉ cần biết còn trang sau | Query trả `Slice` |
| Lấy danh sách nhỏ không phân trang | `List` với `Top`/`First` |

## 7. Lưu ý về tính đúng đắn

1. **Luôn sắp xếp khi chọn top hoặc first có ý nghĩa nghiệp vụ.** Nếu không có `OrderBy` hoặc `Sort`, database không bảo đảm bản ghi nào được chọn trước.
2. **Thêm tie-breaker duy nhất.** Ví dụ sort theo `publishedAt DESC, id DESC` để có thứ tự ổn định khi timestamp trùng.
3. **Chú ý null trong thuộc tính sort.** Thứ tự null có thể khác giữa database; nếu cần kết quả nhất quán, định nghĩa quy tắc null rõ ràng hoặc chuẩn hóa dữ liệu.
4. **Không dùng Top để thay thế filter.** Giới hạn số hàng trả về không bảo đảm điều kiện lọc hiệu quả; cần index phù hợp.
5. **Không tải toàn bộ rồi subList ở Java.** Đưa limit vào repository để database giới hạn kết quả.
6. **Chọn Page khi cần total.** Count query có thể tốn chi phí đáng kể trên bảng lớn.
7. **Không giả định sort theo tên cột SQL.** Method derivation và Sort dùng property Java của entity.
8. **Xem xét dữ liệu thay đổi giữa các trang.** Offset pagination có thể bỏ sót hoặc lặp hàng nếu bản ghi được thêm/xóa trong khi người dùng duyệt; sort ổn định và snapshot/transaction phù hợp giúp giảm rủi ro.

## 8. Ví dụ chạy được với Java 17+, Spring Boot và H2

Ví dụ lưu bài viết và lấy top 3 theo lượt xem, sau đó lấy trang đầu tiên. Dự án dùng Spring Boot 3.4.5, Java 17 và H2 in-memory database.

### Cấu trúc dự án

```text
top-first-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/topfirst/
        │   ├── TopFirstApplication.java
        │   ├── Article.java
        │   └── ArticleRepository.java
        └── resources/
            └── application.properties
```

### `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>top-first-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:h2:mem:topfirst;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
logging.level.org.hibernate.SQL=DEBUG
```

### `Article.java`

```java
package com.example.topfirst;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "articles")
public class Article {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 160)
    private String title;

    @Column(nullable = false, length = 40)
    private String category;

    @Column(nullable = false)
    private int views;

    protected Article() {
    }

    public Article(String title, String category, int views) {
        this.title = title;
        this.category = category;
        this.views = views;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public int getViews() {
        return views;
    }
}
```

### `ArticleRepository.java`

```java
package com.example.topfirst;

import java.util.List;
import java.util.Optional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ArticleRepository extends JpaRepository<Article, Long> {
    List<Article> findTop3ByCategoryOrderByViewsDescIdDesc(String category);

    Optional<Article> findFirstByCategoryOrderByViewsDescIdDesc(String category);

    List<Article> findTop3ByCategory(String category, Sort sort);

    Page<Article> findByCategory(String category, Pageable pageable);
}
```

### `TopFirstApplication.java`

```java
package com.example.topfirst;

import java.util.List;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

@SpringBootApplication
public class TopFirstApplication {
    public static void main(String[] args) {
        SpringApplication.run(TopFirstApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(ArticleRepository repository) {
        return args -> {
            repository.saveAll(List.of(
                    new Article("Intro to JPA", "BOOK", 120),
                    new Article("Spring Data", "BOOK", 250),
                    new Article("Hibernate", "BOOK", 180),
                    new Article("JPA in Practice", "BOOK", 250),
                    new Article("Java basics", "TOOL", 90)
            ));
            repository.flush();

            List<Article> top = repository
                    .findTop3ByCategoryOrderByViewsDescIdDesc("BOOK");
            System.out.println("Top 3: " + titles(top));

            Article first = repository
                    .findFirstByCategoryOrderByViewsDescIdDesc("BOOK")
                    .orElseThrow();
            System.out.println("First: " + first.getTitle());

            Sort sort = Sort.by(
                    Sort.Order.desc("views"),
                    Sort.Order.desc("id")
            );
            System.out.println("Dynamic top 3: "
                    + titles(repository.findTop3ByCategory("BOOK", sort)));

            Page<Article> page = repository.findByCategory(
                    "BOOK",
                    PageRequest.of(0, 2, sort)
            );
            System.out.println("Page 0: " + titles(page.getContent()));
            System.out.println("Total BOOK: " + page.getTotalElements());
        };
    }

    private static String titles(List<Article> articles) {
        return articles.stream()
                .map(Article::getTitle)
                .reduce((left, right) -> left + ", " + right)
                .orElse("");
    }
}
```

### Chạy chương trình

```bash
mvn spring-boot:run
```

Phần output do ứng dụng in ra:

```text
Top 3: JPA in Practice, Spring Data, Hibernate
First: JPA in Practice
Dynamic top 3: JPA in Practice, Spring Data, Hibernate
Page 0: JPA in Practice, Spring Data
Total BOOK: 4
```

Hai bài có cùng `views = 250`; `id DESC` quyết định `JPA in Practice` đứng trước `Spring Data` vì bài đó được lưu sau và có ID lớn hơn. Kết quả cho thấy `Top3` giới hạn ba hàng, `First` chọn một hàng theo sort, `Sort` cung cấp thứ tự lúc gọi, còn `Page` trả nội dung trang và tổng số bản ghi.

SQL do Hibernate sinh có thể khác alias và cú pháp limit theo dialect. Với query Top 3, phần SQL cốt lõi gồm điều kiện `category = ?`, `ORDER BY views DESC, id DESC` và giới hạn ba hàng. Với Page, thường có query lấy trang và count query để tính tổng.

## 9. Kiểm tra và tối ưu trong dự án

1. Bật `logging.level.org.hibernate.SQL=DEBUG` ở môi trường phát triển để xem câu SQL được sinh.
2. Dùng dữ liệu gần quy mô thật và `EXPLAIN` để kiểm tra database có tận dụng index cho filter và order hay không.
3. Kiểm tra sort có tie-breaker duy nhất, nhất là khi phân trang.
4. So sánh `Page` và `Slice` nếu count query gây chậm.
5. Kiểm tra hành vi khi thuộc tính sort là null và khi dữ liệu được thêm/xóa trong lúc client duyệt trang.
6. Đo trên cùng database engine với production; kết quả từ H2 không đại diện chính xác cho PostgreSQL, MySQL, SQL Server hoặc Oracle.

## 10. Lỗi thường gặp

1. **Dùng `First` mà không sort:** kết quả đầu tiên không có ý nghĩa ổn định. Thêm `OrderBy` hoặc truyền `Sort`.
2. **Sort theo một field có thể trùng:** thêm khóa duy nhất như `id` làm tie-breaker.
3. **Viết tên cột SQL trong method:** dùng property Java, ví dụ `publishedAt` thay cho `published_at`.
4. **Giới hạn sau khi tải toàn bộ:** không lấy tất cả rồi cắt bằng `subList`; dùng `Top`/`First` hoặc `Pageable` để database giới hạn.
5. **Dùng Page dù không cần tổng số:** cân nhắc `Slice` để tránh count query.
6. **Cho rằng Top luôn nhanh:** thiếu index phù hợp vẫn có thể cần scan và sort nhiều hàng.
7. **Cho rằng Sort giới hạn kết quả:** Sort chỉ sắp xếp; cần Top/First hoặc Pageable để giới hạn.
8. **Bỏ qua dữ liệu thay đổi giữa các trang:** chọn sort ổn định và cân nhắc keyset pagination khi duyệt dữ liệu lớn.

## 11. Nguyên tắc thực hành

- Dùng `Top`/`First` cho giới hạn cố định và khai báo số lượng rõ ràng khi lớn hơn một.
- Dùng `OrderBy` khi thứ tự là quy tắc cố định của nghiệp vụ.
- Dùng `Sort` khi caller được chọn thứ tự, đồng thời whitelist property được phép sort.
- Dùng `Page` khi cần tổng số chính xác; dùng `Slice` khi chỉ cần biết có trang kế tiếp.
- Luôn thêm tie-breaker duy nhất cho top result và phân trang.
- Tạo index theo điều kiện lọc và thứ tự thực tế, rồi xác minh bằng execution plan.
- Kiểm thử SQL và semantics khi kết hợp limit với pagination.

Điểm cốt lõi: **Top/First giới hạn số hàng; OrderBy và Sort quyết định thứ tự; Pageable chia kết quả thành trang. Muốn kết quả ổn định và hiệu quả, hãy sắp xếp rõ ràng, thêm tie-breaker duy nhất và kiểm tra index cùng count query trên database thực tế.**