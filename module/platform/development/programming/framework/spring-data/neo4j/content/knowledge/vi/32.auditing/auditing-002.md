# @CreatedDate, @LastModifiedDate, @CreatedBy và @LastModifiedBy

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích bốn annotation auditing của Spring Data và vai trò của từng trường.
- Bật auditing cho Spring Data Neo4j (SDN) bằng cấu hình imperative hoặc reactive.
- Khai báo metadata ngày tạo, ngày cập nhật, người tạo và người cập nhật trên node entity.
- Cung cấp người thao tác hiện tại bằng `AuditorAware<T>` hoặc `ReactiveAuditorAware<T>`.
- Tùy chỉnh nguồn thời gian bằng `DateTimeProvider`.
- Hiểu thời điểm SDN điền metadata và những trường hợp auditing không tự chạy.
- Kiểm tra auditing khi tạo mới, cập nhật và sử dụng business ID.

## 1. Auditing giải quyết vấn đề gì?

Trong một ứng dụng dùng Neo4j, node thường cần lưu lại thông tin về vòng đời dữ liệu. Ví dụ, một bài viết cần biết ai đã tạo, được tạo lúc nào, ai sửa lần gần nhất và lần sửa đó diễn ra khi nào.

Nếu mỗi service tự gán các trường này, logic dễ bị lặp và có thể không nhất quán. Một luồng ghi có thể quên cập nhật `updatedAt`, luồng khác có thể ghi đè `createdAt`, hoặc người thao tác bị lấy từ một nguồn khác nhau.

Spring Data cung cấp auditing để tự động điền metadata trong quá trình persist entity. Spring Data Neo4j tích hợp cơ chế này với mapping và entity callback của SDN. Các annotation dùng chung với những module Spring Data khác:

- `@CreatedDate`: thời điểm entity được tạo.
- `@LastModifiedDate`: thời điểm entity được sửa gần nhất.
- `@CreatedBy`: người hoặc principal tạo entity.
- `@LastModifiedBy`: người hoặc principal sửa entity gần nhất.

Auditing lưu metadata vào property của node thông qua mapping entity. Đây là dữ liệu nghiệp vụ được lưu cùng node, không phải nhật ký lịch sử đầy đủ của mọi lần thay đổi. Nếu cần biết tất cả phiên bản trước, nội dung cũ và ai thay đổi từng field, cần thiết kế audit log hoặc event history riêng.

## 2. Phân biệt bốn annotation

| Annotation | Giá trị được ghi | Khi nào được cập nhật |
| --- | --- | --- |
| `@CreatedDate` | Thời điểm tạo entity | Khi SDN nhận diện entity mới |
| `@LastModifiedDate` | Thời điểm sửa gần nhất | Khi entity được persist; mặc định cũng được ghi lúc tạo |
| `@CreatedBy` | Principal tạo entity | Khi SDN nhận diện entity mới |
| `@LastModifiedBy` | Principal sửa gần nhất | Khi entity được persist; mặc định cũng được ghi lúc tạo |

Có thể chỉ dùng một phần annotation. Ví dụ, hệ thống chỉ cần theo dõi thời gian thì khai báo hai trường ngày và không cần `AuditorAware`.

Các trường ngày hỗ trợ kiểu thời gian Java như `Instant`, `LocalDate`, `LocalDateTime`, các kiểu JDK date/time khác, `long`, `Long`, `java.util.Date` và `Calendar`. Trong ứng dụng mới, `Instant` thường là lựa chọn phù hợp để biểu diễn một thời điểm tuyệt đối theo UTC.

Các trường người thao tác có kiểu generic tương ứng với `AuditorAware<T>`. Ví dụ, nếu `@CreatedBy` và `@LastModifiedBy` dùng `String`, auditor provider phải trả về `String`. Nếu dùng một kiểu user domain khác, provider phải trả về đúng kiểu đó và kiểu này phải ánh xạ được theo mô hình SDN.

## 3. Khai báo metadata trên node entity

Ví dụ một node `Article` có đủ bốn trường auditing:

```java
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Article")
public class Article {

    @Id
    @GeneratedValue
    private Long id;

    private String title;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant updatedAt;

    @CreatedBy
    private String createdBy;

    @LastModifiedBy
    private String updatedBy;

    protected Article() {
    }

    public Article(String title) {
        this.title = title;
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

    public Instant getUpdatedAt() {
        return updatedAt;
    }

    public String getCreatedBy() {
        return createdBy;
    }

    public String getUpdatedBy() {
        return updatedBy;
    }

    public void setTitle(String title) {
        this.title = title;
    }
}
```

Khi được lưu qua repository hoặc template, các giá trị auditing được SDN điền trước khi entity được bind thành dữ liệu Neo4j. Ở database, node `Article` sẽ có các property tương ứng với `createdAt`, `updatedAt`, `createdBy` và `updatedBy`.

Không nên tự gán các trường này trong constructor hoặc setter nghiệp vụ. Hãy để auditing infrastructure quản lý chúng, nhờ vậy mọi luồng ghi qua SDN dùng cùng một quy tắc.

## 4. Bật auditing cho imperative repository

Khai báo annotation `@CreatedDate` hoặc `@CreatedBy` trên entity chưa đủ. Ứng dụng cần bật auditing để Spring đăng ký infrastructure và callback tương ứng.

Với truy cập imperative, dùng `@EnableNeo4jAuditing` trong package `org.springframework.data.neo4j.config`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.config.EnableNeo4jAuditing;

@Configuration
@EnableNeo4jAuditing
public class Neo4jAuditingConfiguration {
}
```

Sau khi bật, SDN đăng ký auditing callback để xử lý metadata trước khi bind entity vào record Neo4j. Nếu entity chỉ có `@CreatedDate` và `@LastModifiedDate`, không cần cung cấp `AuditorAware`.

Nếu entity có `@CreatedBy` hoặc `@LastModifiedBy`, cần cung cấp bean `AuditorAware<T>` để xác định principal hiện tại.

## 5. Cung cấp người thao tác bằng AuditorAware

`AuditorAware<T>` là SPI của Spring Data. Phương thức `getCurrentAuditor()` trả về `Optional<T>`, cho phép auditing infrastructure lấy người dùng hoặc hệ thống đang thực hiện thao tác.

Ví dụ đơn giản dùng tài khoản hệ thống làm principal mặc định:

```java
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.neo4j.config.EnableNeo4jAuditing;

@Configuration
@EnableNeo4jAuditing(auditorAwareRef = "auditorAware")
public class Neo4jAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorAware() {
        return () -> Optional.of("system");
    }
}
```

Ví dụ này phù hợp để minh họa hoặc cho một tiến trình nền chỉ có một danh tính hệ thống. Trong ứng dụng nhiều người dùng, provider nên lấy principal từ security context hoặc cơ chế xác thực đã được xác minh.

Ví dụ với Spring Security imperative:

```java
import java.util.Optional;

import org.springframework.data.domain.AuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

public class SecurityAuditorAware implements AuditorAware<String> {

    @Override
    public Optional<String> getCurrentAuditor() {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return Optional.of("system");
        }

        return Optional.of(authentication.getName());
    }
}
```

Sau đó đăng ký implementation này thành bean và tham chiếu qua `auditorAwareRef`. Kiểu generic là `String`, vì entity đang khai báo các trường `createdBy` và `updatedBy` kiểu `String`.

Nếu `getCurrentAuditor()` trả `Optional.empty()`, auditing không có principal để điền vào các trường By trong lần ghi đó. Hãy quyết định rõ ứng dụng muốn bỏ trống hay dùng tài khoản hệ thống cho các luồng không có người dùng đăng nhập.

## 6. Tùy chỉnh thời gian bằng DateTimeProvider

Mặc định, auditing dùng `CurrentDateTimeProvider` để lấy thời điểm hiện tại. Nếu cần kiểm soát nguồn thời gian, có thể cung cấp bean `DateTimeProvider` và chỉ định tên bằng `dateTimeProviderRef`.

Ví dụ dùng `Clock` của Java:

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
    auditorAwareRef = "auditorAware",
    dateTimeProviderRef = "dateTimeProvider"
)
public class Neo4jAuditingConfiguration {

    @Bean
    Clock auditingClock() {
        return Clock.systemUTC();
    }

    @Bean
    AuditorAware<String> auditorAware() {
        return () -> Optional.of("system");
    }

    @Bean
    DateTimeProvider dateTimeProvider(Clock auditingClock) {
        return () -> Optional.of(Instant.now(auditingClock));
    }
}
```

Dùng `Clock` có một số lợi ích:

- Có thể thống nhất nguồn thời gian UTC giữa các service.
- Có thể thay bằng clock cố định trong test để kết quả ổn định.
- Có thể kiểm thử logic tạo mới và cập nhật mà không phụ thuộc thời gian thực.

Không nên lưu thời gian local của máy chủ nếu hệ thống chạy trên nhiều node hoặc nhiều vùng địa lý. Dùng `Instant` và chuẩn hóa về UTC giúp so sánh, sắp xếp và đồng bộ dữ liệu dễ hơn.

## 7. Điều khiển hành vi lúc tạo mới

`@EnableNeo4jAuditing` có một số thuộc tính cấu hình quan trọng:

| Thuộc tính | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `auditorAwareRef` | Chuỗi rỗng | Tên bean cung cấp principal |
| `dateTimeProviderRef` | Chuỗi rỗng | Tên bean cung cấp thời gian |
| `modifyOnCreate` | `true` | Có điền metadata sửa đổi ngay lúc tạo entity hay không |
| `setDates` | `true` | Có điền các trường ngày hay không |

Với `modifyOnCreate = true`, khi tạo node mới, SDN cũng điền `@LastModifiedDate` và `@LastModifiedBy`. Điều này giúp một entity luôn có thông tin về lần persist gần nhất, kể cả khi nó vừa được tạo.

Nếu nghiệp vụ muốn các trường sửa đổi chỉ xuất hiện sau lần cập nhật đầu tiên, có thể đặt:

```java
@EnableNeo4jAuditing(
    auditorAwareRef = "auditorAware",
    modifyOnCreate = false
)
```

Khi đó, `@CreatedDate` và `@CreatedBy` vẫn ghi lúc tạo; các trường `@LastModifiedDate` và `@LastModifiedBy` được dành cho lần sửa sau đó.

Nếu `setDates = false`, auditing không điền các trường ngày. Không nên tắt thuộc tính này nếu entity đang phụ thuộc vào `@CreatedDate` hoặc `@LastModifiedDate`.

## 8. Luồng hoạt động khi tạo và cập nhật entity

Giả sử một service tạo bài viết rồi cập nhật tiêu đề:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ArticleService {

    private final ArticleRepository articleRepository;

    public ArticleService(ArticleRepository articleRepository) {
        this.articleRepository = articleRepository;
    }

    @Transactional
    public Article create(String title) {
        return articleRepository.save(new Article(title));
    }

    @Transactional
    public Article rename(Long id, String newTitle) {
        Article article = articleRepository.findById(id)
            .orElseThrow();

        article.setTitle(newTitle);

        return articleRepository.save(article);
    }
}
```

Repository:

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface ArticleRepository
        extends Neo4jRepository<Article, Long> {
}
```

Với cấu hình auditing mặc định và principal hiện tại là `alice`, luồng khái quát như sau:

| Thời điểm | `createdAt` | `updatedAt` | `createdBy` | `updatedBy` |
| --- | --- | --- | --- | --- |
| Tạo mới | Thời điểm tạo | Thời điểm tạo | alice | alice |
| Alice sửa bài | Giữ nguyên | Thời điểm sửa | Giữ nguyên | alice |
| Bob sửa bài | Giữ nguyên | Thời điểm sửa mới | Giữ nguyên | bob |

Các giá trị được tạo bởi auditing infrastructure khi SDN chuẩn bị persist entity. Việc gọi getter hoặc chỉ tải entity bằng `findById()` không làm thay đổi metadata.

## 9. Business ID và nhận diện entity mới

SDN cần biết entity đang được lưu là mới hay đã tồn tại để phân biệt trường `@Created*` và `@LastModified*`.

Nếu dùng ID do SDN sinh bằng `@GeneratedValue`, SDN có thể dùng trạng thái ID để xác định entity mới trong quy trình thông thường.

Nếu ứng dụng tự gán business ID, ví dụ `articleCode = "ART-2026-001"`, cần chú ý cơ chế nhận diện entity mới. Trong SDN hiện đại, `@Version` là bắt buộc khi dùng business ID để SDN xác định entity đã được persist hay chưa.

Ví dụ:

```java
import java.time.Instant;

import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.annotation.Version;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Article")
public class ArticleWithBusinessId {

    @Id
    private String articleCode;

    @Version
    private Long version;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant updatedAt;

    public ArticleWithBusinessId(String articleCode) {
        this.articleCode = articleCode;
    }
}
```

`@Version` còn cung cấp optimistic locking khi nhiều transaction cập nhật cùng entity. Không tự tăng hoặc gán giá trị version trong service; SDN quản lý trường này.

Nếu dùng business ID nhưng bỏ `@Version`, SDN không có đủ thông tin để phân biệt chắc chắn trạng thái mới và đã tồn tại. Khi đó, metadata creation có thể không được xử lý như mong đợi.

## 10. Auditing trong ứng dụng reactive

Với reactive repository, dùng annotation `@EnableReactiveNeo4jAuditing` thay cho annotation imperative. Annotation này thuộc package `org.springframework.data.neo4j.config`.

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.config.EnableReactiveNeo4jAuditing;

@Configuration
@EnableReactiveNeo4jAuditing(
    auditorAwareRef = "reactiveAuditorAware"
)
public class ReactiveNeo4jAuditingConfiguration {
}
```

Provider reactive cần implement `ReactiveAuditorAware<T>` và trả về `Mono<T>`. Ví dụ dùng reactive Spring Security:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.ReactiveAuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Mono;

@Configuration
public class ReactiveAuditorConfiguration {

    @Bean
    ReactiveAuditorAware<String> reactiveAuditorAware() {
        return () -> ReactiveSecurityContextHolder.getContext()
            .mapNotNull(SecurityContext::getAuthentication)
            .filter(authentication ->
                authentication.isAuthenticated()
                    && !(authentication instanceof AnonymousAuthenticationToken)
            )
            .map(Authentication::getName)
            .defaultIfEmpty("system");
    }
}
```

Reactive auditor lấy principal từ Reactor Security Context thay vì dựa vào `ThreadLocal`. Cách này phù hợp với Spring WebFlux và reactive pipeline vì thông tin xác thực được truyền theo context của subscription.

Không dùng `AuditorAware` imperative để thay thế `ReactiveAuditorAware` trong reactive infrastructure. Hai kiểu có hợp đồng trả về khác nhau: `Optional<T>` và `Mono<T>`.

## 11. Phạm vi hoạt động của auditing callback

SDN dùng `AuditingBeforeBindCallback` để điền các trường auditing trước khi entity được bind thành record lưu trong Neo4j. Callback này thuộc vòng đời mapping entity.

Điều đó có nghĩa auditing được áp dụng khi persist entity qua các abstraction như:

- `Neo4jRepository.save()`.
- `Neo4jTemplate.save()`.
- Các luồng persist entity tương ứng trong reactive repository hoặc `ReactiveNeo4jTemplate`.

Nếu ứng dụng thực thi Cypher trực tiếp bằng `Neo4jClient` hoặc Neo4j Java Driver, auditing entity callback không tự chạy. Ví dụ:

```java
neo4jClient.query("""
    MATCH (a:Article {articleCode: $articleCode})
    SET a.title = $title
    """)
    .bind(articleCode).to("articleCode")
    .bind(title).to("title")
    .run();
```

Truy vấn này thay đổi node trực tiếp. SDN không nhận một entity để đưa qua auditing callback, vì vậy các trường `updatedAt` và `updatedBy` không tự được cập nhật.

Nếu custom Cypher cần giữ metadata, hãy chủ động đưa giá trị thời gian và principal vào tham số hoặc xây dựng một callback/logic riêng phù hợp. Không nên giả định mọi thay đổi trong Neo4j đều được auditing của SDN quan sát.

## 12. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Có annotation nhưng trường auditing luôn null | Chưa bật auditing | Thêm `@EnableNeo4jAuditing` hoặc reactive variant |
| Dùng `@CreatedBy` nhưng không có principal | Chưa đăng ký `AuditorAware` hoặc provider trả empty | Cung cấp `AuditorAware<T>` |
| Kiểu auditor không khớp property | Generic type của provider khác kiểu trường | Đồng bộ kiểu dữ liệu |
| Dùng imperative auditor trong reactive app | Không lấy principal từ Reactor Context | Dùng `ReactiveAuditorAware<T>` |
| `LastModifiedDate` không có lúc tạo | Đã đặt `modifyOnCreate = false` | Kiểm tra lại cấu hình |
| Thời gian lệch giữa các máy | Dùng local clock hoặc timezone không thống nhất | Dùng `Instant` và UTC |
| `CreatedDate` không được điền với business ID | SDN không xác định được trạng thái mới/cũ | Khai báo `@Version` theo yêu cầu SDN |
| Custom Cypher không cập nhật metadata | Cypher trực tiếp bỏ qua entity callback | Bind và cập nhật audit fields rõ ràng |
| Service tự gán lại `createdAt` | Trộn trách nhiệm nghiệp vụ và auditing | Để callback quản lý các trường audit |
| Test thời gian không ổn định | Phụ thuộc đồng hồ thật | Cấu hình `DateTimeProvider` dùng Clock cố định |

## 13. Quy trình triển khai auditing

Khi thêm auditing vào một entity, có thể làm theo trình tự:

1. Xác định metadata cần lưu: ngày tạo, ngày sửa, người tạo và/hoặc người sửa.
2. Chọn kiểu dữ liệu phù hợp; thường dùng `Instant` cho thời gian và `String` hoặc user ID cho principal.
3. Đặt annotation trên các field của entity.
4. Bật đúng auditing infrastructure: imperative hoặc reactive.
5. Nếu có các field By, đăng ký provider tương ứng.
6. Nếu cần kiểm soát thời gian, cung cấp `DateTimeProvider`.
7. Kiểm tra entity dùng generated ID hay business ID; nếu là business ID, khai báo `@Version`.
8. Lưu entity qua repository hoặc template và đọc lại để xác minh.
9. Kiểm tra cả lần tạo, lần cập nhật và các luồng ghi dùng custom Cypher.
10. Bảo đảm mọi luồng ghi tuân theo cùng chính sách metadata.

## 14. Câu hỏi tự kiểm tra

1. `@CreatedDate` khác `@LastModifiedDate` ở thời điểm cập nhật như thế nào?
2. Khi nào cần `AuditorAware<T>`?
3. Vì sao `@CreatedBy` và `@LastModifiedBy` cần cùng kiểu generic với provider?
4. Annotation nào bật auditing cho imperative SDN?
5. Annotation nào bật auditing cho reactive SDN?
6. `DateTimeProvider` có vai trò gì và provider mặc định lấy thời gian từ đâu?
7. `modifyOnCreate` ảnh hưởng đến các trường nào?
8. Vì sao `@Version` cần thiết khi entity dùng business ID?
9. Tại sao gọi `Neo4jClient` trực tiếp không kích hoạt auditing callback?
10. Khi ứng dụng không có người dùng đăng nhập, có thể biểu diễn principal hệ thống như thế nào?

## Tài liệu tham khảo

- [Spring Data Neo4j – Auditing](https://docs.spring.io/spring-data/neo4j/reference/auditing.html)
- [Spring Data Neo4j FAQ – Cấu hình auditing](https://docs.spring.io/spring-data/neo4j/reference/faq.html#how-do-i-audit-entities)
- [EnableNeo4jAuditing API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/config/EnableNeo4jAuditing.html)
- [EnableReactiveNeo4jAuditing API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/config/EnableReactiveNeo4jAuditing.html)
- [Spring Data Commons – Auditing](https://docs.spring.io/spring-data/commons/reference/auditing.html)
- [Spring Data Neo4j – Metadata-based Mapping và @Version](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/metadata-based-mapping.html)

## Kết luận

Bốn annotation `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy` và `@LastModifiedBy` giúp SDN tự điền thông tin tạo mới và cập nhật cho entity. Muốn sử dụng, ứng dụng phải bật auditing bằng `@EnableNeo4jAuditing` hoặc `@EnableReactiveNeo4jAuditing`. Các trường By cần provider lấy principal; các trường Date dùng `DateTimeProvider`, mặc định là thời gian hiện tại.

Auditing callback chạy trong vòng đời persist entity của SDN, vì vậy repository và template có thể tự động điền metadata. Custom Cypher qua `Neo4jClient` hoặc Driver không đi qua callback này và cần quản lý audit fields riêng. Khi dùng business ID, hãy khai báo `@Version` để SDN phân biệt entity mới với entity đã tồn tại. Thiết kế rõ nguồn principal, nguồn thời gian và phạm vi các luồng ghi sẽ giúp metadata audit nhất quán trong toàn bộ ứng dụng đồ thị.
