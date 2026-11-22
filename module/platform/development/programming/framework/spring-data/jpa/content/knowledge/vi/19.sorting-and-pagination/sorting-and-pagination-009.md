# Thứ tự ổn định, khóa phụ và thay đổi dữ liệu giữa các trang

## Mục tiêu

Khi phân trang dữ liệu bằng Spring Data JPA, mỗi trang là một truy vấn riêng. Nếu thứ tự sắp xếp không xác định duy nhất, hoặc dữ liệu thay đổi giữa hai lần gọi, người dùng có thể thấy bản ghi lặp lại, bị bỏ qua hoặc chuyển vị trí giữa các trang.

Có ba nguyên tắc cần kết hợp:

1. **Sắp xếp xác định:** dùng `ORDER BY` với đủ thuộc tính để xác định duy nhất thứ tự của từng hàng.
2. **Khóa phụ duy nhất (tie-breaker):** thêm khóa chính hoặc một thuộc tính duy nhất vào cuối thứ tự để phá hòa khi các giá trị sort chính bằng nhau.
3. **Chọn chiến lược phân trang theo mức thay đổi dữ liệu:** offset pagination dễ dùng nhưng nhạy với insert/delete trước offset; keyset pagination ổn định hơn khi tiếp tục từ vị trí cuối trang, nhưng không tự tạo snapshot bất biến của toàn bộ dữ liệu.

Bài này giải thích cách thiết kế thứ tự ổn định, hiện tượng page drift, cách viết cursor theo nhiều khóa sort, ảnh hưởng của transaction và ví dụ Java 17+ chạy được với Spring Boot và H2.

## 1. Vì sao ORDER BY cần xác định duy nhất thứ tự?

SQL không bảo đảm thứ tự hàng nếu query không có `ORDER BY`. Ngay cả khi có `ORDER BY`, các hàng có cùng giá trị ở tất cả thuộc tính sort vẫn có thể xuất hiện theo thứ tự bất kỳ.

Ví dụ:

```sql
select id, title, created_at
from articles
order by created_at desc;
```

Nếu nhiều bài viết có cùng `created_at`, database không có nghĩa vụ giữ một thứ tự cố định giữa các hàng đó. Một lần chạy có thể trả Article A trước Article B; lần khác có thể đảo lại do execution plan, index, vacuum, cập nhật dữ liệu hoặc thay đổi thống kê.

Khi phân trang, điều này nguy hiểm hơn truy vấn danh sách thông thường. Ranh giới giữa trang 1 và trang 2 có thể cắt qua nhóm hàng có cùng sort key. Nếu thứ tự trong nhóm thay đổi, một hàng có thể xuất hiện ở cả hai trang hoặc không xuất hiện ở trang nào trong quá trình duyệt.

## 2. Thêm khóa phụ duy nhất để phá hòa

Thêm một thuộc tính duy nhất vào cuối `ORDER BY`. Khóa chính là lựa chọn phổ biến:

```sql
select id, title, created_at
from articles
order by created_at desc, id desc;
```

Thứ tự có nghĩa là:

1. Bài mới hơn đứng trước theo `created_at DESC`.
2. Nếu hai bài có cùng thời điểm, bài có `id` lớn hơn đứng trước theo `id DESC`.

Vì `id` là khóa chính, tổ hợp `(created_at, id)` xác định duy nhất thứ tự của mỗi hàng.

Trong Spring Data JPA, derived query có thể viết:

```java
List<Article> findByPublishedTrueOrderByCreatedAtDescIdDesc();
```

Hoặc dùng `Sort`:

```java
Sort stableSort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
);

Pageable pageable = PageRequest.of(0, 20, stableSort);
Page<Article> page = repository.findByPublishedTrue(pageable);
```

`Sort` dùng tên property Java của entity, không dùng tên cột SQL. Nếu cột database là `created_at`, property Java vẫn có thể là `createdAt`.

### Khóa phụ nên có đặc điểm gì?

- **Duy nhất:** bảo đảm không còn hai hàng cùng toàn bộ sort key.
- **Không null:** khóa chính đáp ứng điều này.
- **Ổn định:** giá trị không nên thay đổi trong khi người dùng đang duyệt các trang.
- **Có thể so sánh nhất quán:** database phải có quy tắc so sánh xác định cho kiểu dữ liệu đó.

Không nhất thiết phải dùng `id DESC`; có thể dùng `id ASC`. Điều quan trọng là chọn một hướng cố định và dùng cùng hướng trong query, cursor và mọi trang.

## 3. Thứ tự nhiều thuộc tính và tie-breaker

Thứ tự có thể gồm nhiều trường nghiệp vụ trước khóa chính:

```sql
order by priority desc, created_at asc, id asc
```

Database so sánh theo thứ tự từ trái sang phải:

- Ưu tiên cao hơn đứng trước.
- Nếu cùng priority, bản ghi cũ hơn đứng trước.
- Nếu cả priority và created_at cùng giá trị, ID nhỏ hơn đứng trước.

Khóa chính ở cuối làm cho thứ tự trở thành duy nhất. Nếu chỉ dùng `priority DESC, created_at ASC`, các hàng cùng hai giá trị đó vẫn có thể đổi chỗ.

Với API cho phép sort động, hãy kiểm tra property sort theo whitelist và luôn nối thêm khóa duy nhất nếu caller chưa cung cấp:

```java
Sort requested = Sort.by(Sort.Order.desc("createdAt"));
Sort stable = requested.and(Sort.by(Sort.Order.desc("id")));
Pageable pageable = PageRequest.of(pageNumber, pageSize, stable);
```

Trong ứng dụng thật, nếu client có thể gửi sort theo `id`, hãy tránh nối thêm `id` lần thứ hai. Có thể kiểm tra `requested.getOrderFor("id")` trước khi thêm tie-breaker. Không cho phép client truyền tùy ý tên thuộc tính hoặc biểu thức SQL.

### Null và collation cũng ảnh hưởng thứ tự

Thuộc tính sort có thể null hoặc được so sánh theo collation không phân biệt hoa thường. Hai giá trị như `"alpha"` và `"ALPHA"` có thể được xem là bằng nhau theo collation. Vì vậy, khóa phụ duy nhất vẫn cần thiết.

Thứ tự NULL mặc định khác nhau giữa các database. Nếu nghiệp vụ yêu cầu null luôn ở cuối hoặc đầu, hãy định nghĩa rõ thứ tự bằng tính năng của database/dialect hoặc biểu thức `CASE` trong query. Khi dùng keyset pagination trên sort key nullable, cursor predicate phải mô phỏng chính xác cùng quy tắc null; cách đơn giản hơn là dùng các trường cursor không null hoặc tạo một sort key đã chuẩn hóa.

## 4. Offset pagination và hiện tượng page drift

`Pageable` thường triển khai offset pagination. Với page size bằng 3:

```java
PageRequest.of(0, 3); // hàng 0-2
PageRequest.of(1, 3); // hàng 3-5
PageRequest.of(2, 3); // hàng 6-8
```

Database thường dùng `OFFSET` và `LIMIT`, hoặc cú pháp tương đương theo dialect.

Giả sử thứ tự ban đầu là:

| Vị trí | Bản ghi |
| ---: | --- |
| 1 | Article-10 |
| 2 | Article-09 |
| 3 | Article-08 |
| 4 | Article-07 |
| 5 | Article-06 |
| 6 | Article-05 |

Trang đầu với page size 3 trả `Article-10`, `Article-09`, `Article-08`. Trước khi người dùng yêu cầu trang thứ hai, một bài mới hơn `Article-11` được thêm vào đầu danh sách:

| Vị trí mới | Bản ghi |
| ---: | --- |
| 1 | Article-11 |
| 2 | Article-10 |
| 3 | Article-09 |
| 4 | Article-08 |
| 5 | Article-07 |
| 6 | Article-06 |
| 7 | Article-05 |

Trang thứ hai vẫn dùng `OFFSET 3 LIMIT 3`, nên trả `Article-08`, `Article-07`, `Article-06`. `Article-08` bị lặp lại vì nó đã nằm ở trang đầu trước khi dữ liệu thay đổi.

### Xóa trước offset cũng gây bỏ sót

Nếu một hàng đứng trước vị trí offset bị xóa sau khi trang đầu được đọc, các hàng phía sau dịch lên. Truy vấn trang hai vẫn bỏ qua cùng số hàng cũ, nên có thể bỏ qua một bản ghi mà người dùng chưa từng nhìn thấy.

### Cập nhật sort key có thể gây lặp hoặc mất hàng

Nếu một bản ghi được cập nhật `createdAt`, `priority` hoặc thuộc tính đang sort, nó có thể di chuyển từ phía sau cursor lên phía trước, hoặc ngược lại. Offset pagination và keyset pagination đều có thể bị ảnh hưởng bởi thay đổi vị trí này.

Do đó, `ORDER BY` xác định duy nhất là điều kiện cần để thứ tự mỗi truy vấn ổn định, nhưng **không bảo đảm các trang được lấy ở những thời điểm khác nhau nhìn thấy cùng một tập dữ liệu**.

## 5. Keyset pagination: tiếp tục từ khóa của hàng cuối

Keyset pagination (còn gọi là seek pagination) không bỏ qua N hàng bằng offset. Thay vào đó, query trang tiếp theo chỉ lấy các hàng đứng sau khóa sort của bản ghi cuối trang trước.

Với thứ tự:

```sql
order by created_at desc, id desc
```

Giả sử hàng cuối trang trước có `created_at = :lastCreatedAt` và `id = :lastId`. Những hàng tiếp theo phải có tuple sort nhỏ hơn cursor theo thứ tự giảm dần:

```sql
where created_at < :lastCreatedAt
   or (created_at = :lastCreatedAt and id < :lastId)
order by created_at desc, id desc
fetch first :pageSize rows only;
```

Đây là so sánh từ điển (lexicographic comparison): so sánh trường đầu tiên trước; chỉ khi bằng nhau mới so sánh trường tiếp theo.

### Ví dụ với nhiều sort key

Với thứ tự `priority DESC, created_at ASC, id ASC`, cursor tiếp theo phải thỏa một trong các trường hợp:

```sql
where priority < :lastPriority
   or (priority = :lastPriority and created_at > :lastCreatedAt)
   or (priority = :lastPriority
       and created_at = :lastCreatedAt
       and id > :lastId)
```

Mỗi nhánh tương ứng với việc trường đầu tiên khác nhau tại vị trí đó và nằm sau cursor theo hướng sort đã chọn. Với sort hỗn hợp ASC/DESC, dấu so sánh phải thay đổi tương ứng cho từng trường.

### Vì sao keyset ít bị ảnh hưởng bởi insert trước cursor?

Trong ví dụ `createdAt DESC, id DESC`, cursor ở `Article-08`. Nếu `Article-11` được thêm vào đầu danh sách, nó có khóa sort lớn hơn cursor nên không thỏa predicate `createdAt < lastCreatedAt`. Các bài `Article-07`, `Article-06`, `Article-05` vẫn nằm sau cursor và được trả về.

Keyset tránh việc các hàng mới trước cursor đẩy offset và làm lặp hàng đã đọc. Nó cũng không cần database đếm hoặc bỏ qua toàn bộ hàng của các trang trước.

## 6. Keyset không phải snapshot của dữ liệu

Keyset pagination giảm page drift do insert/delete trước vị trí đã đọc, nhưng không đóng băng dataset:

- **Insert sau cursor:** bản ghi mới có thể xuất hiện ở trang kế tiếp dù chưa tồn tại khi trang đầu được đọc.
- **Delete sau cursor:** bản ghi bị xóa sẽ không còn xuất hiện trong trang tiếp theo.
- **Update sort key:** bản ghi có thể di chuyển qua cursor, dẫn tới bị lặp hoặc bị bỏ qua.
- **Update thuộc tính không tham gia sort:** thứ tự không đổi, nhưng nội dung hiển thị có thể phản ánh phiên bản mới hơn so với trang trước.

Nếu cần duyệt chính xác một tập dữ liệu như tại một thời điểm, cần một cơ chế snapshot nhất quán, ví dụ transaction/snapshot isolation phù hợp trong một phiên xử lý ngắn, dữ liệu versioned hoặc truy vấn theo mốc snapshot được thiết kế rõ ràng. Giữ transaction database mở qua nhiều HTTP request thường không phải lựa chọn tốt vì giữ connection và snapshot quá lâu.

### Mốc thời gian as-of

Một cách đơn giản cho dữ liệu append-only là chốt một mốc `asOf` ở trang đầu:

```sql
where created_at <= :asOf
  and (
      created_at < :lastCreatedAt
      or (created_at = :lastCreatedAt and id < :lastId)
  )
order by created_at desc, id desc
```

Điều kiện `created_at <= :asOf` loại các bản ghi mới tạo sau thời điểm bắt đầu. Tuy nhiên, nó không ngăn một hàng cũ bị xóa hoặc cập nhật sort key; vì vậy đây chỉ là snapshot gần đúng cho workload append-only, không phải snapshot đầy đủ của database.

### Khi nào nên dùng immutable sort key?

Với feed hoặc danh sách cần duyệt ổn định, ưu tiên các trường được gán khi tạo và không thay đổi, ví dụ `createdAt` bất biến cùng khóa chính. Nếu sort theo `updatedAt`, trạng thái hoặc điểm có thể đổi liên tục, hãy chấp nhận semantics dữ liệu sống hoặc dùng snapshot/versioning khi yêu cầu nghiệp vụ cần.

## 7. Page, Slice và keyset

| Kiểu | Cách lấy dữ liệu | Metadata | Lưu ý |
| --- | --- | --- | --- |
| `Page<T>` | Thường offset pagination | Nội dung, tổng số hàng, tổng số trang | Có thể cần count query; các request trang riêng vẫn có thể thấy dữ liệu khác nhau. |
| `Slice<T>` | Thường offset pagination | Nội dung và `hasNext()` | Tránh tổng count nhưng vẫn có page drift do offset. |
| Keyset/cursor | Lọc theo giá trị của hàng cuối | Cursor tiếp theo | Tránh offset sâu và giảm dịch chuyển do insert trước cursor; cần sort key ổn định. |

`Slice` không tự động biến offset pagination thành keyset pagination. Nếu API cần cursor, hãy truyền các giá trị sort key của hàng cuối và dùng predicate keyset tương ứng.

Với Spring Data, có thể dùng `Pageable` cho offset pagination hoặc triển khai cursor query bằng JPQL/Criteria. Một số phiên bản Spring Data hỗ trợ scrolling/keyset API cho các kiểu query nhất định; kiểm tra tài liệu đúng phiên bản đang dùng và giới hạn của loại query trước khi chọn API.

## 8. Thiết kế cursor API

Cursor nên chứa toàn bộ giá trị sort cần thiết để tiếp tục sau hàng cuối, không chỉ chứa ID nếu thứ tự chính còn dựa trên trường khác.

Ví dụ payload logic:

```json
{
  "createdAt": "2025-01-08T00:00:00Z",
  "id": 3
}
```

API có thể mã hóa cursor thành token opaque để client không phải tự xây predicate. Nên:

- Gắn cursor với filter và sort đã dùng ở trang đầu; không cho client thay sort tùy ý giữa chừng.
- Kiểm tra và xác thực cursor đầu vào; không tin giá trị ID hoặc timestamp do client sửa.
- Bao gồm tất cả sort key và tie-breaker trong cursor.
- Bảo đảm timestamp dùng đúng độ chính xác đã lưu ở database; tránh tạo cursor từ giá trị đã bị làm tròn khác với giá trị so sánh.
- Chuẩn hóa timezone, thường dùng UTC/Instant.
- Có thể ký hoặc mã hóa token để chống chỉnh sửa nếu cursor chứa thông tin nhạy cảm hoặc ràng buộc truy vấn.

Không đưa dữ liệu nhạy cảm vào cursor dạng Base64 đơn thuần; Base64 chỉ là encoding, không phải mã hóa hay chữ ký.

## 9. Null, timestamp precision và sort key phức tạp

Keyset predicate phải dùng cùng quy tắc so sánh như `ORDER BY`:

- Nếu sort key nullable, cần biểu diễn null rank trong cursor và predicate, hoặc chuẩn hóa thành một giá trị không null.
- Nếu dùng collation không phân biệt hoa thường, phép so sánh trong cursor phải theo cùng collation.
- Nếu dùng biểu thức như `lower(title)`, cursor cần giữ giá trị biểu thức đã sắp xếp hoặc query phải tính lại cùng biểu thức.
- Nếu dùng timestamp, hãy dùng giá trị đọc từ database để tạo cursor. Database có thể lưu độ chính xác microsecond hoặc millisecond dù Java `Instant` có nanosecond.
- Nếu sort theo nhiều hướng khác nhau, xây predicate lexicographic với dấu `<` hoặc `>` đúng cho từng trường.

Ví dụ bài học này chọn `createdAt` và `id` đều không null, thứ tự giảm dần trên cả hai trường để predicate đơn giản và rõ ràng.

## 10. Index cho stable order và keyset

Với query lọc `published = true` và sắp xếp `created_at DESC, id DESC`, index ghép có thể hữu ích:

```sql
create index ix_articles_published_created_id
    on articles(published, created_at desc, id desc);
```

Index phù hợp có thể giúp database lọc theo published và đọc theo thứ tự cursor. Tuy nhiên, khả năng tận dụng index phụ thuộc database engine, phân bố dữ liệu, predicate và execution plan. Cú pháp DESC trong index cũng có thể khác theo dialect.

Dùng `EXPLAIN`/execution plan với dữ liệu đại diện để kiểm tra:

- Database có dùng index cho filter và order không?
- Có sort lớn trong bộ nhớ hoặc ghi temporary file không?
- Số hàng cần đọc để trả một trang là bao nhiêu?
- Query keyset có seek vào vùng index phù hợp không?

Index làm tăng dung lượng và chi phí ghi. Chỉ tạo index theo workload thực tế.

## 11. Ví dụ chạy được với Java 17+, Spring Boot và H2

Ví dụ tạo các bài viết có thứ tự thời gian, trong đó hai bài có cùng `createdAt`. Query sắp xếp `createdAt DESC, id DESC` nên ID lớn hơn đứng trước khi thời gian bằng nhau. Sau khi lấy trang đầu, chương trình chèn một bài mới ở đầu danh sách rồi so sánh trang hai dùng offset với trang tiếp theo dùng keyset.

### Cấu trúc dự án

```text
stable-pagination/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/pagination/
        │   ├── StablePaginationApplication.java
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
    <artifactId>stable-pagination</artifactId>
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
spring.datasource.url=jdbc:h2:mem:stablepagination;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
logging.level.org.hibernate.SQL=DEBUG
```

### `Article.java`

```java
package com.example.pagination;

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

    @Column(nullable = false, length = 120)
    private String title;

    @Column(nullable = false)
    private Instant createdAt;

    @Column(nullable = false)
    private boolean published;

    protected Article() {
    }

    public Article(String title, Instant createdAt, boolean published) {
        this.title = title;
        this.createdAt = createdAt;
        this.published = published;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
```

### `ArticleRepository.java`

```java
package com.example.pagination;

import java.time.Instant;
import java.util.List;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ArticleRepository extends JpaRepository<Article, Long> {
    @Query("select a from Article a "
         + "where a.published = true "
         + "order by a.createdAt desc, a.id desc")
    List<Article> findFirstPage(Pageable pageable);

    @Query("select a from Article a "
         + "where a.published = true "
         + "and (a.createdAt < :lastCreatedAt "
         + "or (a.createdAt = :lastCreatedAt and a.id < :lastId)) "
         + "order by a.createdAt desc, a.id desc")
    List<Article> findNextPage(
            @Param("lastCreatedAt") Instant lastCreatedAt,
            @Param("lastId") Long lastId,
            Pageable limit
    );
}
```

Query đầu dùng `Pageable` để áp dụng limit/offset cùng thứ tự cố định. Query thứ hai dùng cursor predicate và `PageRequest.of(0, pageSize)` để giới hạn số hàng mà không bỏ qua offset.

### `StablePaginationApplication.java`

```java
package com.example.pagination;

import java.time.Instant;
import java.util.List;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.data.domain.PageRequest;

@SpringBootApplication
public class StablePaginationApplication {
    public static void main(String[] args) {
        SpringApplication.run(StablePaginationApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(ArticleRepository repository) {
        return args -> {
            repository.saveAll(List.of(
                    new Article("Article-10-A", Instant.parse("2025-01-10T00:00:00Z"), true),
                    new Article("Article-10-B", Instant.parse("2025-01-10T00:00:00Z"), true),
                    new Article("Article-09", Instant.parse("2025-01-09T00:00:00Z"), true),
                    new Article("Article-08", Instant.parse("2025-01-08T00:00:00Z"), true),
                    new Article("Article-07", Instant.parse("2025-01-07T00:00:00Z"), true),
                    new Article("Article-06", Instant.parse("2025-01-06T00:00:00Z"), true),
                    new Article("Article-05", Instant.parse("2025-01-05T00:00:00Z"), true)
            ));
            repository.flush();

            int pageSize = 3;
            List<Article> firstPage = repository.findFirstPage(PageRequest.of(0, pageSize));
            System.out.println("First page: " + titles(firstPage));

            Article cursor = firstPage.get(firstPage.size() - 1);

            // A new row is inserted before the old page boundary.
            repository.save(new Article(
                    "Article-11", Instant.parse("2025-01-11T00:00:00Z"), true));
            repository.flush();

            List<Article> offsetPageTwo = repository.findFirstPage(
                    PageRequest.of(1, pageSize));
            System.out.println("Offset page 2 after insert: " + titles(offsetPageTwo));

            List<Article> keysetPageTwo = repository.findNextPage(
                    cursor.getCreatedAt(),
                    cursor.getId(),
                    PageRequest.of(0, pageSize)
            );
            System.out.println("Keyset page 2 after insert: " + titles(keysetPageTwo));
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

Stdout:

```text
First page: Article-10-B, Article-10-A, Article-09
Offset page 2 after insert: Article-09, Article-08, Article-07
Keyset page 2 after insert: Article-08, Article-07, Article-06
```

Hai bài có cùng `createdAt`; `id DESC` làm `Article-10-B` đứng trước `Article-10-A` vì được insert sau và có ID lớn hơn. Sau khi `Article-11` được thêm ở đầu danh sách, offset page 2 lặp `Article-09`, còn keyset tiếp tục sau cursor `Article-09` và trả `Article-08`, `Article-07`, `Article-06`.

Ví dụ minh họa insert trước cursor. Nếu một hàng sau cursor bị xóa hoặc sort key bị sửa, kết quả keyset vẫn có thể thay đổi; immutable sort key hoặc snapshot semantics cần thiết khi nghiệp vụ đòi hỏi một tập kết quả cố định.

## 12. Kiểm thử phân trang

Integration test nên xác minh cả thứ tự lẫn hành vi khi dữ liệu thay đổi:

- Tạo nhiều hàng có cùng giá trị sort chính và xác nhận khóa phụ quyết định thứ tự.
- Lấy trang đầu, chèn một hàng trước ranh giới, rồi so sánh offset page tiếp theo và keyset page tiếp theo.
- Xóa một hàng trước offset và xác nhận hiện tượng dịch chuyển.
- Cập nhật sort key của một hàng từ phía sau lên phía trước cursor để hiểu rủi ro lặp/bỏ sót.
- Kiểm tra cursor với giá trị biên trùng timestamp và ID.
- Kiểm tra null sort key, collation và timestamp precision nếu các trường đó tham gia thứ tự.
- Xác minh query có `ORDER BY` đầy đủ và execution plan tận dụng index mong muốn.

Không chỉ kiểm thử với dữ liệu mà mọi `createdAt` đều khác nhau; tie-breaker chỉ bộc lộ tác dụng khi có nhiều hàng cùng sort key chính.

## 13. Lỗi thường gặp

1. **Chỉ sort theo trường không duy nhất:** thêm khóa chính hoặc tie-breaker duy nhất ở cuối.
2. **Cho rằng ORDER BY cố định snapshot:** nó chỉ cố định thứ tự trong từng truy vấn; dữ liệu có thể thay đổi giữa các request.
3. **Dùng offset sâu trên bảng lớn:** database có thể phải bỏ qua nhiều hàng; cân nhắc keyset.
4. **Dùng Slice rồi nghĩ không còn page drift:** Slice thường vẫn dùng offset; nó chỉ tránh tổng count.
5. **Tạo cursor chỉ từ ID trong khi sort theo nhiều trường:** cursor phải chứa tất cả sort key theo đúng thứ tự.
6. **Viết sai dấu so sánh trong cursor predicate:** hướng `<`/`>` phải khớp ASC/DESC của từng trường.
7. **Sort key thay đổi trong khi duyệt:** hàng có thể vượt qua cursor. Ưu tiên sort key bất biến hoặc dùng snapshot.
8. **Không xác định null ordering:** kết quả và cursor predicate có thể khác giữa database.
9. **Làm tròn timestamp khi tạo cursor:** dùng giá trị đọc từ database với độ chính xác thực tế.
10. **Tin mốc asOf tạo snapshot hoàn chỉnh:** nó chỉ chặn insert sau mốc trong mô hình phù hợp; không ngăn delete hoặc update.
11. **Quên tie-breaker khi sort động:** nối khóa duy nhất sau khi whitelist sort của client.
12. **Không kiểm tra count query của Page:** tổng số có thể tốn kém và có thể được đọc ở snapshot khác với nội dung trang.

## 14. Nguyên tắc thực hành

- Mọi query phân trang phải có `ORDER BY` xác định duy nhất.
- Thêm khóa chính hoặc thuộc tính duy nhất làm tie-breaker cuối cùng.
- Giữ cùng thứ tự sort giữa query trang đầu, query tiếp theo và cursor.
- Dùng offset pagination khi dữ liệu vừa phải và page number là yêu cầu quan trọng.
- Dùng keyset pagination cho luồng duyệt tiếp theo trên tập dữ liệu lớn hoặc thường xuyên có insert trước vị trí đọc.
- Ưu tiên sort key không null và bất biến nếu cần hạn chế lặp/bỏ sót.
- Dùng snapshot/versioning khi cần nhìn cùng một tập dữ liệu qua nhiều trang.
- Tạo index theo filter và sort thực tế; xác nhận bằng execution plan.
- Kiểm thử với dữ liệu trùng sort key và thay đổi đồng thời.

Điểm cốt lõi: **Thứ tự ổn định cần một ORDER BY xác định duy nhất, thường bằng cách thêm khóa chính làm tie-breaker. Offset pagination có thể lặp hoặc bỏ sót hàng khi dữ liệu thay đổi trước offset; keyset tiếp tục từ khóa của hàng cuối và giảm hiện tượng dịch trang, nhưng muốn snapshot bất biến vẫn cần chiến lược nhất quán dữ liệu riêng.**