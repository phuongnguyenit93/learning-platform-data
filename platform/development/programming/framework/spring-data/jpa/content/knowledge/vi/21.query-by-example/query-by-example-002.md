# Cấu hình thuộc tính được xét hoặc bỏ qua

## Mục tiêu

Khi cuộn dữ liệu lớn bằng Spring Data JPA, đặc biệt với **keyset scrolling**, kiểu kết quả (projection) phải cung cấp đủ các thuộc tính để framework xác định vị trí tiếp theo. Bạn vẫn có thể chỉ lấy những trường cần cho màn hình hoặc xử lý, nhưng không được bỏ các thuộc tính tham gia sắp xếp và tạo cursor.

Quy tắc thực hành:

- **Bao gồm** tất cả thuộc tính dùng trong `Sort` hoặc `OrderBy` trong projection trả về.
- **Bao gồm khóa chính** (hoặc các phần còn lại của khóa chính ghép), vì keyset cần thứ tự duy nhất và Spring Data bổ sung khóa chính vào thứ tự khi cần.
- **Có thể bỏ qua** các thuộc tính chỉ dùng để lọc, cùng những trường lớn hoặc không cần cho tác vụ, nếu caller không cần đọc chúng.
- Giữ các keyset property không null và chọn index phù hợp với điều kiện lọc cùng thứ tự sắp xếp.

Ví dụ: query lọc theo `status`, sắp xếp theo `createdAt DESC, id DESC`, và chỉ hiển thị `title`. Projection phù hợp cần có `title`, `createdAt` và `id`. `status` chỉ dùng lọc nên có thể không xuất hiện trong projection; `body` là nội dung dài nên cũng có thể bỏ qua.

## 1. Vì sao keyset scrolling cần các thuộc tính sắp xếp?

Scroll API chia kết quả lớn thành các `Window<T>`. Mỗi window chứa một nhóm kết quả và có thể cung cấp `ScrollPosition` để lấy nhóm kế tiếp.

Với keyset scrolling, vị trí tiếp theo được xác định từ các giá trị sắp xếp của hàng cuối window hiện tại. Spring Data dùng những giá trị đó để xây dựng điều kiện tiếp tục trong truy vấn sau.

Giả sử thứ tự là:

```sql
order by created_at desc, id desc
```

Để tiếp tục sau hàng cuối có `created_at = :lastCreatedAt` và `id = :lastId`, truy vấn cần so sánh các giá trị này với các hàng tiếp theo. Vì thế, kết quả phải cung cấp được `createdAt` và `id` để framework trích xuất cursor.

Nếu projection chỉ trả `title`, framework không có đủ dữ liệu để tạo keyset position. Việc cuộn có thể thất bại khi trích xuất keyset, dù database vẫn có thể sắp xếp theo các cột đó.

## 2. Thuộc tính nào phải được bao gồm?

Với keyset-based `Window<T>`, hãy rà soát các nhóm sau:

| Loại thuộc tính | Có cần trong projection? | Lý do |
| --- | --- | --- |
| Thuộc tính dùng trong `OrderBy` hoặc `Sort` | **Có** | Giá trị được dùng để tạo vị trí tiếp tục. |
| Primary key | **Có** | Spring Data thêm khóa chính hoặc phần còn lại của khóa ghép để bảo đảm thứ tự duy nhất; cursor cần đọc được giá trị này. |
| Thuộc tính chỉ dùng trong `WHERE`/predicate | Không bắt buộc | Database dùng nó để lọc; projection chỉ cần đưa vào nếu code phía gọi cần đọc. |
| Thuộc tính hiển thị hoặc xử lý | Có nếu caller cần | Chọn các trường cần cho công việc sau khi lấy window. |
| Trường lớn không dùng, ví dụ `body`, `blob` hoặc mô tả dài | Có thể bỏ qua | Tránh tải dữ liệu không cần thiết. |

Ví dụ entity:

```java
@Entity
public class Article {
    @Id
    private Long id;

    private String status;
    private Instant createdAt;
    private String title;
    private String body;
}
```

Query lọc `status`, sắp xếp `createdAt DESC, id DESC`, và hiển thị `title`. Projection nên khai báo:

```java
public interface ArticleScrollRow {
    Long getId();
    Instant getCreatedAt();
    String getTitle();
}
```

`getId()` và `getCreatedAt()` là các trường cursor. `getTitle()` là trường nghiệp vụ cần hiển thị. `status` và `body` được bỏ khỏi projection vì chỉ dùng lọc hoặc không cần đọc.

## 3. Cấu hình thuộc tính được bao gồm bằng projection

Với interface projection, các getter xác định những thuộc tính cần đọc:

```java
public interface ArticleScrollRow {
    Long getId();
    Instant getCreatedAt();
    String getTitle();
}
```

Spring Data tạo projection cho kết quả repository. Với closed interface projection, framework biết các property được khai báo và có thể tối ưu phần dữ liệu truy xuất.

Điểm cần nhớ là projection phải bao gồm cả hai nhóm:

1. Thuộc tính ứng dụng cần để hiển thị hoặc xử lý, như `title`.
2. Thuộc tính kỹ thuật cần để tiếp tục keyset scroll, như `createdAt` và `id`.

Bạn có thể giữ projection này ở tầng repository/service, sau đó chuyển sang DTO công khai chỉ chứa trường hiển thị:

```java
public record ArticleCard(String title) {
}

ArticleCard card = new ArticleCard(scrollRow.getTitle());
```

Như vậy API bên ngoài chỉ nhận `title`, trong khi projection nội bộ vẫn có các cursor key để cuộn đúng.

### DTO projection

DTO projection cũng dùng được nếu constructor hoặc record component bao gồm mọi sort key cần thiết:

```java
public record ArticleScrollDto(
        Long id,
        Instant createdAt,
        String title
) {
}
```

Không tạo DTO keyset chỉ có `title` nếu query sắp xếp theo `createdAt` và `id`. DTO phải giữ đủ dữ liệu cho keyset extraction, kể cả khi các trường đó không được đưa ra response cuối.

### Projection lồng nhau và property path

Nếu sort theo thuộc tính của association, ví dụ `publisher.name`, projection cần cung cấp được property path đó theo mapping mà Spring Data có thể đọc. Projection lồng nhau có thể làm phát sinh join hoặc tải thêm dữ liệu. Với keyset scrolling, nên ưu tiên các sort key đơn giản, ổn định và dễ ánh xạ; kiểm thử SQL và cursor extraction khi dùng nested projection.

## 4. Thuộc tính nào có thể bỏ qua?

Không cần đưa mọi field của entity vào projection. Hãy phân biệt property dùng để lọc với property dùng để tạo cursor.

Ví dụ:

```java
Window<ArticleScrollRow> findFirst20ByStatusOrderByCreatedAtDescIdDesc(
        String status,
        KeysetScrollPosition position
);
```

- `status` được dùng làm điều kiện lọc nhưng không phải sort key, nên không cần getter trong `ArticleScrollRow` nếu caller không dùng nó.
- `body` không tham gia filter, sort hoặc hiển thị, nên có thể bỏ qua.
- `createdAt` và `id` không được bỏ vì chúng tạo thứ tự và cursor.
- `title` được giữ lại vì ứng dụng cần xử lý hoặc hiển thị tiêu đề.

Việc bỏ qua field trong projection không xóa field khỏi entity hoặc database. Nó chỉ giới hạn dữ liệu mà query result/projection cung cấp cho caller. Nếu dùng repository trả entity đầy đủ (`Window<Article>`), entity có thể mang theo nhiều thuộc tính hơn nhu cầu; projection phù hợp hơn khi muốn giới hạn dữ liệu đọc.

### Không có annotation exclude riêng cho keyset

Bạn thường cấu hình việc bao gồm/bỏ qua bằng hình dạng projection: khai báo getter hoặc DTO component cho trường cần dùng và bỏ các trường không cần. Không có cách an toàn để yêu cầu keyset bỏ qua một sort property mà vẫn mong framework tái tạo cursor từ property đó.

Nếu muốn loại một trường khỏi response công khai nhưng vẫn cần cho cursor, giữ trường đó trong projection nội bộ rồi map sang response DTO nhỏ hơn.

## 5. Khóa chính và thứ tự duy nhất

Keyset scrolling cần thứ tự ổn định để mỗi hàng có vị trí riêng. Nếu sort chỉ theo `createdAt`, nhiều hàng có thể có cùng timestamp. Spring Data bổ sung primary key (hoặc các phần còn lại của composite primary key) vào thứ tự để bảo đảm uniqueness.

Ví dụ sort:

```java
Sort sort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
);
```

Ở đây `id` được khai báo rõ làm tie-breaker. Dù framework có thể bổ sung khóa chính khi cần, khai báo rõ thứ tự giúp người đọc hiểu quy tắc sắp xếp và giúp projection dễ kiểm tra.

Với khóa chính ghép, mọi thành phần cần thiết của khóa chính phải được ánh xạ và có thể lấy ra để tạo cursor. Đừng chỉ đưa một phần của khóa ghép vào projection.

## 6. Keyset property cần không null

Keyset filtering dùng các toán tử so sánh để tìm hàng sau cursor. Cách database xử lý `NULL` trong phép so sánh khác với giá trị thông thường; vì vậy Spring Data yêu cầu các property dùng làm keyset/sort phải không null. Keyset scrolling với sort property nullable có thể tạo kết quả không mong đợi.

Nên cấu hình schema và entity để các sort key không null:

```java
@Column(nullable = false, updatable = false)
private Instant createdAt;
```

Khóa chính vốn không null. Với trường nghiệp vụ có thể null, hãy cân nhắc:

- Dùng một sort key không null khác.
- Chuẩn hóa giá trị trước khi lưu, nếu quy tắc nghiệp vụ cho phép.
- Dùng offset scrolling nếu không thể đáp ứng ràng buộc keyset và dữ liệu nullable là cần thiết.

Không tự thay `NULL` bằng một giá trị giả trong cursor mà không bảo đảm query `ORDER BY` và predicate dùng cùng một quy tắc.

## 7. Offset scrolling khác keyset scrolling ở yêu cầu projection

Spring Data hỗ trợ offset-based và keyset-based scrolling, đều trả `Window<T>`:

| Đặc điểm | Offset scrolling | Keyset scrolling |
| --- | --- | --- |
| Vị trí tiếp tục | Số hàng đã bỏ qua | Giá trị sort key của hàng cuối |
| Cần projection expose sort key? | Không cần để trích xuất keyset | **Có**, phải expose mọi sort key và khóa chính cần cho cursor |
| Trang sâu | Có thể tốn chi phí do database phải bỏ qua nhiều hàng | Thường hiệu quả hơn khi có index phù hợp |
| Null trong sort key | Không có ràng buộc keyset tương tự | Sort/keyset property phải không null |
| Index | Hữu ích | Rất quan trọng để tận dụng keyset |

Offset scrolling vẫn nên có sort ổn định để thứ tự dễ dự đoán. Tuy nhiên, quy tắc projection phải giữ cursor fields là yêu cầu đặc thù của keyset scrolling.

### Bắt đầu và tiếp tục scroll

Với offset, có thể bắt đầu bằng `ScrollPosition.offset()`. Với keyset, bắt đầu bằng `ScrollPosition.keyset()`. Vị trí do `Window.positionAt(index)` trả về là vị trí của phần tử đó; truy vấn tiếp theo tiếp tục sau phần tử đã chọn.

Không nhầm `ScrollPosition.offset()` với `ScrollPosition.offset(0L)`: một giá trị biểu thị điểm bắt đầu trước phần tử đầu tiên, còn giá trị kia xác định phần tử tại offset 0. Vì scroll position có semantics exclusive, dùng sai vị trí ban đầu có thể bỏ qua phần tử đầu tiên.

## 8. Window và Stream dùng cho hai cách tiêu thụ dữ liệu

`Window<T>` phù hợp khi ứng dụng cần xử lý dữ liệu theo từng nhóm và tiếp tục bằng scroll position. Keyset projection cần chứa cursor key như các phần trước.

`Stream<T>` phù hợp khi muốn duyệt kết quả theo luồng. Stream không tự cung cấp keyset cursor để yêu cầu window kế tiếp. Nó có thể giữ JDBC resource hoặc cursor nên phải được đóng và tiêu thụ trong transaction phù hợp:

```java
@Transactional(readOnly = true)
public void processPublished(String status) {
    try (Stream<ArticleTitleView> stream = repository.streamByStatus(status)) {
        stream.forEach(this::process);
    }
}
```

Không trả một Stream đã mở ra khỏi transaction rồi mới xử lý ở caller. Với Stream, projection vẫn có thể chỉ khai báo những trường cần dùng; nhưng quy tắc bắt buộc phải expose sort keys để tạo keyset cursor áp dụng cho keyset `Window`, không phải cho mọi Stream.

Fetch size và khả năng đọc theo batch còn phụ thuộc JPA provider, JDBC driver và cấu hình database. Kiểu `Stream<T>` không tự bảo đảm mọi driver đều tải từng hàng một.

## 9. Index và chi phí truy vấn

Keyset filtering hoạt động tốt khi database có index phù hợp với điều kiện lọc và thứ tự sắp xếp. Với query lọc theo `status` và sort theo `created_at DESC, id DESC`, một index ghép có thể hữu ích:

```sql
create index ix_articles_status_created_id
    on articles(status, created_at desc, id desc);
```

Cú pháp index phụ thuộc database. Hãy dùng `EXPLAIN` hoặc execution plan để xác nhận database có tận dụng index cho predicate và sort hay không.

Projection giúp tránh đọc các field không cần, đặc biệt trường text/blob lớn. Tuy nhiên, projection không thay thế index và cũng không làm một keyset query hiệu quả nếu sort key không được index phù hợp.

## 10. Ví dụ chạy được với Java 17+, Spring Boot và H2

Ví dụ này tạo năm bài viết. Repository cuộn từng window hai bài bằng keyset, lọc theo `status`, sắp xếp theo `createdAt DESC, id DESC`. Projection chỉ trả `id`, `createdAt` và `title`; nó bỏ qua `status` và `body`.

### Cấu trúc dự án

```text
keyset-projection-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/keyset/
        │   ├── KeysetProjectionApplication.java
        │   ├── Article.java
        │   ├── ArticleScrollRow.java
        │   ├── ArticleRepository.java
        │   └── ArticleReader.java
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
    <artifactId>keyset-projection-demo</artifactId>
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
spring.datasource.url=jdbc:h2:mem:keysetprojection;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
logging.level.org.hibernate.SQL=DEBUG
```

### `Article.java`

```java
package com.example.keyset;

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

    @Column(nullable = false, length = 30)
    private String status;

    @Column(nullable = false, updatable = false)
    private Instant createdAt;

    @Column(nullable = false, length = 120)
    private String title;

    @Column(length = 4000)
    private String body;

    protected Article() {
    }

    public Article(String status, Instant createdAt, String title, String body) {
        this.status = status;
        this.createdAt = createdAt;
        this.title = title;
        this.body = body;
    }
}
```

### `ArticleScrollRow.java`

```java
package com.example.keyset;

import java.time.Instant;

public interface ArticleScrollRow {
    Long getId();

    Instant getCreatedAt();

    String getTitle();
}
```

`id` và `createdAt` là cursor fields. `title` là trường ứng dụng cần. Projection không khai báo `getStatus()` hoặc `getBody()`, nên caller không nhận các field đó.

### `ArticleRepository.java`

```java
package com.example.keyset;

import org.springframework.data.domain.KeysetScrollPosition;
import org.springframework.data.domain.Window;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ArticleRepository extends JpaRepository<Article, Long> {
    Window<ArticleScrollRow> findFirst2ByStatusOrderByCreatedAtDescIdDesc(
            String status,
            KeysetScrollPosition position
    );
}
```

Đây là derived query method. Scroll API của Spring Data JPA hiện chưa hỗ trợ scrolling cho string-based query methods; vì vậy ví dụ dùng query derivation thay vì `@Query`.

### `ArticleReader.java`

```java
package com.example.keyset;

import org.springframework.data.domain.KeysetScrollPosition;
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ArticleReader {
    private final ArticleRepository repository;

    public ArticleReader(ArticleRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public void printPublishedArticles() {
        KeysetScrollPosition position = ScrollPosition.keyset();

        while (true) {
            Window<ArticleScrollRow> window =
                    repository.findFirst2ByStatusOrderByCreatedAtDescIdDesc(
                            "PUBLISHED", position);

            for (ArticleScrollRow article : window) {
                System.out.println(article.getTitle()
                        + " | " + article.getCreatedAt()
                        + " | id=" + article.getId());
            }

            if (!window.hasNext()) {
                break;
            }

            position = (KeysetScrollPosition)
                    window.positionAt(window.size() - 1);
        }
    }
}
```

`positionAt(window.size() - 1)` lấy vị trí của phần tử cuối window. Truy vấn tiếp theo dùng vị trí đó theo semantics exclusive để lấy các hàng đứng sau. Vòng lặp chạy trong transaction đọc để persistence context và tài nguyên truy vấn được quản lý trong suốt quá trình xử lý.

### `KeysetProjectionApplication.java`

```java
package com.example.keyset;

import java.time.Instant;
import java.util.List;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class KeysetProjectionApplication {
    public static void main(String[] args) {
        SpringApplication.run(KeysetProjectionApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(ArticleRepository repository, ArticleReader reader) {
        return args -> {
            repository.saveAll(List.of(
                    new Article("PUBLISHED", Instant.parse("2025-01-10T00:00:00Z"),
                            "Article-10-A", "Long body A"),
                    new Article("PUBLISHED", Instant.parse("2025-01-10T00:00:00Z"),
                            "Article-10-B", "Long body B"),
                    new Article("PUBLISHED", Instant.parse("2025-01-09T00:00:00Z"),
                            "Article-09", "Long body C"),
                    new Article("PUBLISHED", Instant.parse("2025-01-08T00:00:00Z"),
                            "Article-08", "Long body D"),
                    new Article("DRAFT", Instant.parse("2025-01-11T00:00:00Z"),
                            "Draft-11", "Not included")
            ));
            repository.flush();

            reader.printPublishedArticles();
        };
    }
}
```

### Chạy chương trình

```bash
mvn spring-boot:run
```

Stdout:

```text
Article-10-B | 2025-01-10T00:00:00Z | id=2
Article-10-A | 2025-01-10T00:00:00Z | id=1
Article-09 | 2025-01-09T00:00:00Z | id=3
Article-08 | 2025-01-08T00:00:00Z | id=4
```

Thứ tự trong output dùng `createdAt DESC, id DESC`. Hai bài có cùng timestamp được phân biệt bằng ID. Bản ghi `Draft-11` không xuất hiện vì bị lọc theo `status`; projection không cần trả `status`. `body` cũng không được trả về vì caller không khai báo getter cho trường đó.

## 11. Lỗi thường gặp

1. **Projection chỉ có field hiển thị:** nếu thiếu sort key, keyset extraction có thể thất bại. Thêm mọi sort property và khóa chính vào projection.
2. **Bỏ `id` vì framework tự thêm tie-breaker:** framework có thể thêm primary key vào thứ tự; projection vẫn cần expose giá trị cần cho cursor.
3. **Đưa filter-only field vào projection một cách máy móc:** field chỉ dùng trong predicate có thể bỏ nếu caller không cần đọc.
4. **Dùng sort key nullable:** keyset comparison có thể bỏ sót hoặc trả kết quả bất ngờ. Dùng sort key không null.
5. **Sort key thay đổi trong khi scroll:** một hàng có thể di chuyển qua cursor. Ưu tiên sort key ổn định, bất biến.
6. **Projection bỏ trường cần cho nghiệp vụ:** field bị bỏ không thể truy cập từ projection. Giữ lại các field hiển thị hoặc xử lý cần thiết.
7. **Nhầm offset scroll với keyset scroll:** offset dùng số hàng đã bỏ qua; keyset dùng giá trị sort key và cần expose chúng.
8. **Dùng `@Query` string-based cho Scroll API:** scrolling với string-based query methods chưa được Spring Data JPA hỗ trợ; dùng derived query, Query by Example, Querydsl hoặc custom repository phù hợp.
9. **Dùng Stream mà không đóng:** stream có thể giữ cursor/connection. Dùng try-with-resources và transaction.
10. **Chọn quá nhiều field:** projection không cần toàn bộ entity; bỏ trường lớn không dùng để giảm dữ liệu đọc.
11. **Quên index theo filter và sort:** keyset cần index phù hợp để đạt hiệu năng tốt.
12. **Tách projection nội bộ và DTO công khai không rõ ràng:** giữ cursor key trong projection nội bộ, sau đó map sang response chỉ có trường được phép hiển thị.

## 12. Checklist khi thiết kế projection cho keyset scroll

- [ ] Xác định chính xác các property trong `OrderBy` hoặc `Sort`.
- [ ] Đưa tất cả sort property vào projection.
- [ ] Đưa primary key hoặc toàn bộ phần còn lại của composite key vào projection.
- [ ] Kiểm tra sort key không null trong schema và dữ liệu.
- [ ] Chỉ giữ các field hiển thị/xử lý cần thiết; bỏ filter-only hoặc payload lớn nếu không cần đọc.
- [ ] Dùng sort ổn định và không thay đổi trong quá trình cuộn nếu có thể.
- [ ] Tạo index theo filter và thứ tự, rồi kiểm tra execution plan.
- [ ] Kiểm thử nhiều window, trường hợp sort key trùng và cursor ở cuối dữ liệu.
- [ ] Map projection nội bộ sang DTO công khai nếu không muốn lộ cursor fields.
- [ ] Đóng Stream và giữ việc tiêu thụ stream trong transaction.

## 13. Tài liệu tham khảo

- Spring Data JPA Reference — JPA Query Methods, phần Scrolling Large Query Results: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html
- Spring Data Commons Reference — Scrolling: https://docs.spring.io/spring-data/commons/reference/repositories/scrolling.html
- Spring Data Commons API — `Window` và `ScrollPosition`: https://docs.spring.io/spring-data/commons/docs/3.4.x/api/

Điểm cốt lõi: **Projection cho keyset scrolling phải giữ mọi sort key và khóa chính cần cho cursor, dù caller không hiển thị chúng. Các field chỉ dùng để lọc hoặc payload lớn có thể bỏ nếu không cần đọc. Hãy giữ cursor fields trong projection nội bộ, map sang DTO nhỏ hơn khi trả ra ngoài, và bảo đảm sort key không null cùng index phù hợp.**