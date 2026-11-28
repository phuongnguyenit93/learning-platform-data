# Kích hoạt @EnableNeo4jAuditing cho ứng dụng đồng bộ

Khi một ứng dụng lưu node bằng Spring Data Neo4j, thường cần biết bản ghi được tạo lúc nào, ai tạo, lần cập nhật gần nhất diễn ra khi nào và do ai thực hiện. Có thể tự gán các trường này trong từng service, nhưng cách đó dễ bị bỏ sót khi một entity được lưu từ nhiều luồng nghiệp vụ khác nhau.

Spring Data Neo4j tích hợp auditing của Spring Data để tự điền metadata trong quá trình lưu entity. Với ứng dụng đồng bộ, bật cơ chế này bằng `@EnableNeo4jAuditing` trên một lớp cấu hình Spring, sau đó khai báo các trường audit trong entity. Nếu chỉ theo dõi thời gian, không cần cung cấp auditor; nếu muốn lưu người tạo và người sửa, cần thêm bean `AuditorAware<T>` để trả về principal hiện tại.

## 1. Auditing ghi nhận điều gì?

Auditing theo dõi hai nhóm thông tin:

| Annotation | Ý nghĩa | Thời điểm được cập nhật |
|---|---|---|
| `@CreatedDate` | Thời điểm entity được tạo | Khi entity được nhận diện là mới |
| `@CreatedBy` | Người hoặc tài khoản tạo entity | Khi entity được nhận diện là mới |
| `@LastModifiedDate` | Thời điểm entity được sửa gần nhất | Khi tạo hoặc cập nhật, tùy `modifyOnCreate` |
| `@LastModifiedBy` | Người hoặc tài khoản sửa gần nhất | Khi tạo hoặc cập nhật, tùy `modifyOnCreate` |

Bạn có thể dùng từng annotation độc lập. Ví dụ, một dịch vụ chỉ cần `createdAt` và `updatedAt` thì chỉ khai báo hai trường ngày giờ. Không bắt buộc phải lưu tên người dùng.

Auditing là metadata do tầng mapping của Spring Data Neo4j quản lý. Khi entity được lưu qua repository hoặc `Neo4jTemplate`, auditing có thể điền các trường trước khi dữ liệu được bind và ghi vào Neo4j. Nó không tự động biến mọi câu Cypher thành thao tác audit.

## 2. Thêm @EnableNeo4jAuditing vào cấu hình

Annotation cần dùng là `org.springframework.data.neo4j.config.EnableNeo4jAuditing`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.config.EnableNeo4jAuditing;

@Configuration
@EnableNeo4jAuditing
public class Neo4jAuditingConfiguration {
}
```

Đặt lớp cấu hình trong package được Spring component scan. Khi ứng dụng khởi động, annotation đăng ký hạ tầng auditing dành cho entity Spring Data Neo4j.

Không nhầm annotation này với `@EnableJpaAuditing`. `@EnableJpaAuditing` dành cho Spring Data JPA; ứng dụng dùng Neo4j cần `@EnableNeo4jAuditing`.

Nếu ứng dụng Spring Boot đã tự cấu hình `Neo4jTemplate`, `Neo4jClient` và repository, thông thường chỉ cần bổ sung lớp cấu hình auditing. Không cần tự tạo auditing handler hoặc callback nếu không có yêu cầu đặc biệt.

## 3. Khai báo trường audit trong entity

Các annotation audit dùng chung của Spring Data nằm trong package `org.springframework.data.annotation`. Ví dụ entity bài viết:

```java
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.annotation.Version;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Article")
public class Article {

    @Id
    private String slug;

    @Version
    private Long version;

    private String title;

    @CreatedBy
    private String createdBy;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedBy
    private String lastModifiedBy;

    @LastModifiedDate
    private Instant lastModifiedAt;

    protected Article() {
    }

    public Article(String slug, String title) {
        this.slug = slug;
        this.title = title;
    }

    public void rename(String title) {
        this.title = title;
    }

    public String getSlug() {
        return slug;
    }

    public String getTitle() {
        return title;
    }

    public String getCreatedBy() {
        return createdBy;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public String getLastModifiedBy() {
        return lastModifiedBy;
    }

    public Instant getLastModifiedAt() {
        return lastModifiedAt;
    }
}
```

Trong ví dụ, `slug` là ID do ứng dụng cấp. Field `@Version` kiểu `Long` cho phép SDN nhận diện entity mới khi version còn `null`, đồng thời hỗ trợ optimistic locking khi cập nhật. Không tự gán version; để Spring Data Neo4j quản lý field này.

Các trường audit không cần setter công khai nếu Spring Data có thể ghi giá trị qua cơ chế property access đang được entity sử dụng. Với immutable entity hoặc constructor mapping tùy chỉnh, cần bảo đảm auditing metadata có thể được gán theo mô hình mapping đã chọn.

## 4. Kiểu dữ liệu được hỗ trợ

Các trường ngày giờ có thể dùng kiểu thời gian Java hiện đại, ví dụ `Instant`, `LocalDate`, `LocalDateTime`, `OffsetDateTime` hoặc `ZonedDateTime` nếu kiểu đó được SDN hỗ trợ. Auditing của Spring Data cũng hỗ trợ `long`, `Long` và các kiểu ngày giờ Java cũ như `Date` và `Calendar`.

Với ứng dụng mới, `Instant` thường là lựa chọn phù hợp cho thời điểm audit vì biểu diễn một mốc thời gian tuyệt đối. Nếu nghiệp vụ cần ngày theo lịch địa phương thay vì thời điểm tuyệt đối, hãy chọn kiểu ngày giờ phản ánh đúng ý nghĩa dữ liệu.

Kiểu của `@CreatedBy` và `@LastModifiedBy` phải tương thích với kiểu mà `AuditorAware<T>` trả về. Ví dụ, nếu entity dùng `String createdBy`, auditor provider nên là `AuditorAware<String>`.

## 5. Chỉ theo dõi ngày giờ: không cần AuditorAware

Đây là biến thể tối giản của lớp cấu hình ở phần 2. Trong ứng dụng, chỉ khai báo một lớp cấu hình auditing phù hợp với nhu cầu; không tạo nhiều lớp cùng tên từ các ví dụ.

Nếu chỉ muốn tự động ghi thời điểm tạo và cập nhật, cấu hình tối thiểu là:

```java
@Configuration
@EnableNeo4jAuditing
public class Neo4jAuditingConfiguration {
}
```

Entity chỉ cần hai trường:

```java
@CreatedDate
private Instant createdAt;

@LastModifiedDate
private Instant lastModifiedAt;
```

Spring Data dùng `CurrentDateTimeProvider` mặc định để lấy thời gian hiện tại. Không cần khai báo `AuditorAware` nếu entity không có `@CreatedBy` hoặc `@LastModifiedBy`.

## 6. Cung cấp người thực hiện bằng AuditorAware

Ví dụ này thay thế cấu hình tối giản ở phần 2 hoặc phần 5 khi entity có các trường `@CreatedBy`/`@LastModifiedBy`.

Khi dùng `@CreatedBy` hoặc `@LastModifiedBy`, auditing cần biết ai đang thực hiện thao tác. Spring Data cung cấp interface đồng bộ `AuditorAware<T>` trong package `org.springframework.data.domain`.

Nếu ứng dụng dùng Spring Security, có thể lấy username từ `SecurityContextHolder`:

```java
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.data.neo4j.config.EnableNeo4jAuditing;

@Configuration
@EnableNeo4jAuditing(auditorAwareRef = "auditorProvider")
public class Neo4jAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorProvider() {
        return () -> Optional.ofNullable(
                SecurityContextHolder.getContext().getAuthentication()
            )
            .filter(Authentication::isAuthenticated)
            .filter(authentication -> !(authentication instanceof AnonymousAuthenticationToken))
            .map(Authentication::getName)
            .or(() -> Optional.of("system"));
    }
}
```

`auditorAwareRef` trỏ đến tên bean `auditorProvider`. Khi có người dùng đã xác thực, provider trả username. Với request không có principal hoặc tác vụ chạy nền, ví dụ dùng giá trị `system` làm actor thay thế. Nếu hệ thống không dùng Spring Security, hãy triển khai `AuditorAware` dựa trên ngữ cảnh người dùng hoặc tài khoản dịch vụ mà ứng dụng đang sử dụng.

Không nên trả một username cố định cho mọi request thực tế nếu ứng dụng cần truy vết từng người dùng. Giá trị fallback như `system` chỉ phù hợp cho tác vụ hệ thống, job nền hoặc trường hợp không có người dùng tương tác.

## 7. Cấu hình đầy đủ cho auditor và thời gian

Đây là biến thể đầy đủ thay cho các lớp cấu hình ở phần 2, 5 hoặc 6 nếu ứng dụng cần tùy chỉnh cả actor và thời gian.

`@EnableNeo4jAuditing` cho phép chỉ định bean lấy actor và bean lấy thời gian. Ví dụ sau dùng `Clock` để có thể thay thế thời gian trong integration test:

```java
import java.time.Clock;
import java.time.Instant;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.neo4j.config.EnableNeo4jAuditing;

@Configuration
@EnableNeo4jAuditing(
    auditorAwareRef = "auditorProvider",
    dateTimeProviderRef = "auditingDateTimeProvider",
    modifyOnCreate = true,
    setDates = true
)
public class Neo4jAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorProvider() {
        return () -> Optional.of("system");
    }

    @Bean
    Clock auditingClock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider auditingDateTimeProvider(Clock auditingClock) {
        return () -> Optional.of(Instant.now(auditingClock));
    }
}
```

Trong ứng dụng thực tế, thay provider actor cố định bằng provider lấy principal hiện hành như phần trước. `DateTimeProvider` trả về `Optional<TemporalAccessor>`; `Instant` đáp ứng hợp đồng này và được chuyển sang kiểu property audit tương ứng.

Không nhất thiết phải tự cấu hình `DateTimeProvider` nếu chỉ cần thời gian hiện tại. Ví dụ này hữu ích khi muốn dùng một `Clock` thống nhất, kiểm thử thời gian xác định hoặc áp dụng chính sách thời gian riêng.

## 8. Ý nghĩa các thuộc tính của @EnableNeo4jAuditing

Annotation có các thuộc tính cấu hình chính:

| Thuộc tính | Mặc định | Ý nghĩa |
|---|---:|---|
| `auditorAwareRef` | `""` | Tên bean `AuditorAware` cung cấp actor hiện tại |
| `dateTimeProviderRef` | `""` | Tên bean `DateTimeProvider` cung cấp thời gian hiện tại |
| `modifyOnCreate` | `true` | Có điền trường `@LastModifiedBy` và `@LastModifiedDate` ngay khi tạo entity hay không |
| `setDates` | `true` | Có điền các trường ngày giờ audit hay không |

Nếu `modifyOnCreate = true`, entity mới thường có cả metadata tạo và metadata sửa với cùng actor/thời điểm ban đầu. Nếu đặt `false`, các trường modified chỉ được điền ở lần cập nhật sau.

`setDates = false` tắt việc tự điền các trường ngày giờ; nó không thay thế cấu hình auditor cho `@CreatedBy` và `@LastModifiedBy`. Hãy chọn giá trị theo chính sách audit của ứng dụng, không thay đổi các mặc định nếu chưa có yêu cầu nghiệp vụ cụ thể.

## 9. Auditing chạy ở thời điểm nào?

Auditing tích hợp với vòng đời mapping entity của Spring Data Neo4j. Khi một entity được lưu qua repository hoặc template, Spring Data xác định entity mới hay đã tồn tại, lấy thời gian và actor cần thiết, rồi điền các trường được đánh dấu trước khi bind dữ liệu để ghi.

Ví dụ repository:

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface ArticleRepository extends Neo4jRepository<Article, String> {
}
```

Service tạo mới và cập nhật entity:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ArticleService {

    private final ArticleRepository repository;

    public ArticleService(ArticleRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Article create(String slug, String title) {
        return repository.save(new Article(slug, title));
    }

    @Transactional
    public Article rename(String slug, String title) {
        Article article = repository.findById(slug)
            .orElseThrow(() -> new IllegalArgumentException("Không tìm thấy bài viết"));

        article.rename(title);
        return repository.save(article);
    }
}
```

Khi `create` lưu entity mới, SDN điền `createdAt`, `createdBy` và các trường modified theo cấu hình. Khi `rename` lưu entity đã tồn tại, `createdAt` và `createdBy` giữ nguyên; `lastModifiedAt` và `lastModifiedBy` được cập nhật.

Auditing không thay thế transaction. `@Transactional` xác định ranh giới commit/rollback của nghiệp vụ; auditing chỉ bổ sung metadata vào entity trong quá trình mapping.

## 10. Auditing với Neo4jTemplate

`Neo4jTemplate` cũng dùng mapping infrastructure của Spring Data Neo4j. Vì vậy, khi lưu entity bằng `template.save(entity)`, các trường auditing có thể được điền như khi lưu qua repository.

```java
import org.springframework.data.neo4j.core.Neo4jTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ArticleTemplateService {

    private final Neo4jTemplate template;

    public ArticleTemplateService(Neo4jTemplate template) {
        this.template = template;
    }

    @Transactional
    public Article save(Article article) {
        return template.save(article);
    }
}
```

Điểm quan trọng là thao tác phải đi qua cơ chế lưu entity được Spring Data Neo4j quản lý. Một câu Cypher ghi trực tiếp qua `Neo4jClient` hoặc Neo4j Java Driver không tự chạy auditing callback của entity. Nếu ứng dụng cần audit cho các lệnh ghi trực tiếp, phải truyền actor/thời gian và cập nhật các property audit trong chính câu lệnh hoặc chuyển thao tác sang đường lưu entity phù hợp.

## 11. Entity dùng ID tự gán và nhận diện entity mới

Auditing cần biết một entity là mới hay đã được lưu để quyết định khi nào điền `@CreatedBy` và `@CreatedDate`. Nếu ID được gán thủ công ngay khi tạo object, SDN không thể chỉ dựa vào ID để phân biệt hai trạng thái đó.

Với entity dùng assigned ID, khai báo field `@Version` kiểu `Long` là cách thông dụng để Spring Data Neo4j nhận diện entity mới khi version còn `null`. SDN sẽ quản lý version khi lưu; không tự gán giá trị version trong service.

Nếu dùng generated ID, SDN có thể nhận diện entity mới qua ID chưa được cấp. Dù chọn chiến lược ID nào, hãy kiểm thử lần lưu đầu để xác nhận các trường `@Created*` được điền và lần cập nhật sau không ghi đè metadata tạo.

## 12. Auditing và custom Cypher

Auditing được kích hoạt khi Spring Data Neo4j xử lý entity qua mapping lifecycle. Các thao tác raw Cypher không tạo entity để mapping nên không tự gọi auditing handler.

Ví dụ một lệnh ghi trực tiếp:

```java
neo4jClient.query("""
    MATCH (a:Article {slug: $slug})
    SET a.title = $title
    """)
    .bind(slug).to("slug")
    .bind(title).to("title")
    .run();
```

Lệnh trên chỉ thay đổi `title`. Nó không tự cập nhật `lastModifiedAt` hoặc `lastModifiedBy`. Nếu cần audit cho đường ghi này, có thể thêm các tham số audit một cách tường minh:

```cypher
MATCH (a:Article {slug: $slug})
SET a.title = $title,
    a.lastModifiedAt = $modifiedAt,
    a.lastModifiedBy = $modifiedBy
```

Hãy bảo đảm actor và thời gian được lấy từ cùng chính sách của ứng dụng. Tránh để một số luồng ghi cập nhật audit tự động còn các luồng khác âm thầm bỏ qua metadata.

## 13. Kiểm thử auditing trong ứng dụng đồng bộ

Integration test nên xác nhận cả lúc tạo và lúc cập nhật. Có thể dùng `AuditorAware` và `DateTimeProvider` cố định để kết quả kiểm thử không phụ thuộc người dùng hoặc đồng hồ hệ thống.

Các trường hợp cần kiểm tra:

1. Khi lưu entity mới, `createdAt` và `createdBy` được điền.
2. Với `modifyOnCreate = true`, các trường `lastModifiedAt` và `lastModifiedBy` cũng được điền khi tạo.
3. Khi cập nhật entity, các trường `created*` giữ nguyên.
4. Các trường `lastModified*` thay đổi theo actor và thời gian của lần cập nhật.
5. Với `modifyOnCreate = false`, các trường modified chưa được điền khi tạo và được điền ở lần cập nhật đầu tiên.
6. Với `setDates = false`, các trường date không được tự động cập nhật.
7. Khi chỉ có trường ngày giờ, ứng dụng vẫn hoạt động mà không cần `AuditorAware`.
8. Với entity dùng assigned ID, xác nhận SDN nhận diện đúng trạng thái mới qua version field.
9. Một lệnh Cypher ghi trực tiếp không tự điền audit metadata, trừ khi câu lệnh tự cập nhật các property đó.

Đọc lại entity bằng repository hoặc template sau khi lưu để xác nhận metadata thực sự nằm trong database, thay vì chỉ kiểm tra object trước khi ghi.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Các trường audit vẫn null | Chưa bật `@EnableNeo4jAuditing` hoặc lớp cấu hình không được scan | Đặt annotation trên `@Configuration` trong package được scan. |
| `@CreatedBy` và `@LastModifiedBy` không được điền | Chưa khai báo `AuditorAware` hoặc `auditorAwareRef` sai tên bean | Tạo bean đúng kiểu và tham chiếu đúng tên. |
| Giá trị actor sai kiểu | Generic `AuditorAware<T>` không khớp kiểu field audit | Dùng cùng kiểu, ví dụ `AuditorAware<String>` với field `String`. |
| `@CreatedDate` không được điền với assigned ID | SDN không nhận diện entity là mới | Dùng `@Version Long` cho entity assigned ID và kiểm tra version ban đầu là null. |
| `createdAt` bị thay đổi khi cập nhật | Nhầm `@CreatedDate` với `@LastModifiedDate` hoặc tự gán field trong service | Để auditing quản lý trường tạo và không ghi đè thủ công. |
| `lastModifiedAt` không được điền lúc tạo | Đã cấu hình `modifyOnCreate = false` | Bật lại nếu muốn modified metadata có giá trị từ lần tạo đầu. |
| Custom Cypher không cập nhật audit | Raw Cypher bỏ qua entity mapping lifecycle | Bind actor/time và cập nhật property trong Cypher hoặc lưu qua SDN entity API. |
| Thời gian kiểm thử thay đổi theo máy | Dùng clock hệ thống trực tiếp | Cung cấp `DateTimeProvider` dựa trên `Clock` có thể thay thế. |

## 15. Quy trình kích hoạt auditing

1. Xác định cần theo dõi thời gian, actor hay cả hai.
2. Thêm `@EnableNeo4jAuditing` vào lớp `@Configuration` được Spring scan.
3. Đánh dấu entity bằng `@CreatedDate`, `@LastModifiedDate` và các annotation actor khi cần.
4. Nếu dùng `@CreatedBy` hoặc `@LastModifiedBy`, tạo `AuditorAware<T>` và cấu hình `auditorAwareRef`.
5. Nếu cần nguồn thời gian riêng, tạo `DateTimeProvider` và cấu hình `dateTimeProviderRef`.
6. Chọn `modifyOnCreate` và `setDates` theo chính sách metadata của ứng dụng.
7. Kiểm tra cách SDN nhận diện entity mới, đặc biệt khi ID được gán thủ công.
8. Lưu entity qua repository hoặc `Neo4jTemplate` để auditing lifecycle được thực thi.
9. Rà soát các đường ghi raw Cypher và bổ sung audit metadata tường minh nếu cần.
10. Viết integration test cho create, update, actor, timestamp và cấu hình tùy chỉnh.

## 16. Ghi nhớ

Để bật auditing cho ứng dụng đồng bộ Spring Data Neo4j, thêm `@EnableNeo4jAuditing` vào một lớp cấu hình Spring. Dùng `@CreatedDate` và `@LastModifiedDate` để theo dõi thời gian; dùng `@CreatedBy` và `@LastModifiedBy` để theo dõi actor. Chỉ khi có trường actor mới cần `AuditorAware<T>`. Có thể tùy chỉnh nguồn thời gian bằng `DateTimeProvider`.

Mặc định, `modifyOnCreate` và `setDates` đều là `true`. Entity được lưu qua repository hoặc `Neo4jTemplate` sẽ đi qua auditing mapping lifecycle; raw Cypher không tự kích hoạt cơ chế này. Hãy bảo đảm SDN nhận diện đúng entity mới, chọn actor phù hợp cho request và job nền, đồng thời kiểm thử riêng hành vi lúc tạo và cập nhật để metadata audit phản ánh chính xác lịch sử thay đổi.

## Tài liệu tham khảo

- [Spring Data Neo4j – Auditing](https://docs.spring.io/spring-data/neo4j/reference/auditing.html)
- [Spring Data Neo4j – EnableNeo4jAuditing API](https://docs.spring.io/spring-data/data-graph/docs/8.0.6/api/org/springframework/data/neo4j/config/EnableNeo4jAuditing.html)
- [Spring Data Commons – Auditing](https://docs.spring.io/spring-data/commons/reference/auditing.html)
