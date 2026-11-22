# Bật kiểm toán với `@EnableElasticsearchAuditing`

Spring Data Elasticsearch hỗ trợ auditing để tự động ghi nhận ai tạo document, ai sửa gần nhất, thời điểm tạo và thời điểm cập nhật. Khi bật `@EnableElasticsearchAuditing`, Spring đăng ký hạ tầng auditing cho các entity được lưu qua Spring Data. Các annotation `@CreatedBy`, `@CreatedDate`, `@LastModifiedBy` và `@LastModifiedDate` đánh dấu những thuộc tính cần được điền trong vòng đời lưu entity.

Auditing giúp ứng dụng có metadata nguồn gốc và thời gian nhất quán mà không phải tự gán bốn thuộc tính này ở mọi service. Để ghi nhận người thao tác, ứng dụng cung cấp bean `AuditorAware<T>`. Để kiểm soát thời gian, có thể cung cấp `DateTimeProvider`, thường kết hợp với `Clock` để kiểm thử dễ dàng.

Auditing là metadata nghiệp vụ được lưu trong `_source`. Nó giúp trả lời “ai tạo?”, “ai sửa gần nhất?” và “khi nào?”, nhưng không tự tạo lịch sử đầy đủ của mọi lần thay đổi. Nếu cần audit trail bất biến, cần thiết kế thêm event log hoặc hệ thống lưu lịch sử chuyên biệt.

## 1. Auditing giải quyết vấn đề gì?

Một entity thường cần lưu thông tin quản trị bên cạnh dữ liệu nghiệp vụ:

- Người tạo bản ghi.
- Thời điểm tạo.
- Người cập nhật gần nhất.
- Thời điểm cập nhật gần nhất.

Nếu mỗi service tự gán các field này, code dễ bị lặp và không nhất quán. Một luồng quên gán `lastModifiedDate`, một luồng dùng timezone khác hoặc một batch job không ghi nhận actor đều làm dữ liệu auditing thiếu tin cậy.

Spring Data auditing đưa việc điền metadata vào vòng đời persist entity. Khi entity được lưu qua repository hoặc `ElasticsearchOperations`, auditing infrastructure có thể cập nhật các thuộc tính được đánh dấu trước khi entity được chuyển thành document để ghi vào Elasticsearch.

### Ví dụ kết quả mong muốn

Một document sau lần tạo đầu tiên:

```json
{
  "id": "p-100",
  "name": "Wireless Mouse",
  "createdBy": "alice",
  "createdDate": "2026-11-13T09:00:00Z",
  "lastModifiedBy": "alice",
  "lastModifiedDate": "2026-11-13T09:00:00Z"
}
```

Sau khi người dùng `bob` sửa tên sản phẩm:

```json
{
  "id": "p-100",
  "name": "Wireless Mouse Pro",
  "createdBy": "alice",
  "createdDate": "2026-11-13T09:00:00Z",
  "lastModifiedBy": "bob",
  "lastModifiedDate": "2026-11-13T10:30:00Z"
}
```

`createdBy` và `createdDate` phản ánh lần tạo đầu tiên; `lastModifiedBy` và `lastModifiedDate` phản ánh lần ghi sửa gần nhất.

## 2. Bốn annotation auditing

Các annotation auditing phổ biến thuộc package `org.springframework.data.annotation`:

| Annotation | Ý nghĩa | Khi được gán |
|---|---|---|
| `@CreatedBy` | Actor tạo entity | Khi tạo mới |
| `@CreatedDate` | Thời điểm tạo entity | Khi tạo mới |
| `@LastModifiedBy` | Actor sửa gần nhất | Khi tạo hoặc cập nhật theo cấu hình |
| `@LastModifiedDate` | Thời điểm sửa gần nhất | Khi tạo hoặc cập nhật theo cấu hình |

Ví dụ entity:

```java
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    private String name;

    @CreatedBy
    @Field(type = FieldType.Keyword)
    private String createdBy;

    @CreatedDate
    @Field(type = FieldType.Date)
    private Instant createdDate;

    @LastModifiedBy
    @Field(type = FieldType.Keyword)
    private String lastModifiedBy;

    @LastModifiedDate
    @Field(type = FieldType.Date)
    private Instant lastModifiedDate;

    // Constructors, getters and setters
}
```

`@CreatedBy` và `@LastModifiedBy` thường dùng kiểu phù hợp với kiểu trả về của `AuditorAware<T>`. Ví dụ `AuditorAware<String>` đi cùng các thuộc tính `String`. Các thuộc tính ngày giờ nên dùng kiểu temporal được Spring Data hỗ trợ; `Instant` là lựa chọn thuận tiện khi muốn lưu thời điểm UTC.

Các annotation auditing không tự biến field thành Elasticsearch mapping đặc biệt. Chúng điều khiển việc gán giá trị ở tầng Spring Data. Mapping field vẫn cần phù hợp với cách ứng dụng muốn truy vấn hoặc hiển thị metadata.

## 3. Bật auditing bằng `@EnableElasticsearchAuditing`

Đặt annotation trên một class cấu hình Spring được component scan:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.config.EnableElasticsearchAuditing;

@Configuration
@EnableElasticsearchAuditing
public class ElasticsearchAuditingConfiguration {
}
```

Annotation này đăng ký hạ tầng auditing của Spring Data Elasticsearch, bao gồm callback cần thiết để áp dụng auditing metadata trong vòng đời entity.

Nếu entity chỉ dùng `@CreatedDate` và `@LastModifiedDate`, Spring có thể cung cấp thời điểm hiện tại thông qua date-time provider mặc định. Nếu muốn ghi `@CreatedBy` hoặc `@LastModifiedBy`, ứng dụng cần cung cấp `AuditorAware` để xác định actor hiện tại.

### Vị trí đặt cấu hình

Class cấu hình phải được Spring Boot/Spring application phát hiện. Ví dụ, nếu class main nằm trong package `com.example`, cấu hình có thể nằm trong package con để được component scan tự động:

```text
com.example
  Application.java
  config
    ElasticsearchAuditingConfiguration.java
  product
    ProductDocument.java
```

Nếu cấu hình nằm ngoài vùng component scan, annotation sẽ không được áp dụng dù file compile thành công.

## 4. `AuditorAware<T>` là gì?

`AuditorAware<T>` là abstraction của Spring Data để trả về actor hiện tại. Nó thuộc package `org.springframework.data.domain` và có phương thức `getCurrentAuditor()` trả về `Optional<T>`.

Ví dụ đơn giản dùng actor cố định cho một ứng dụng thử nghiệm:

```java
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;

@Configuration
public class ElasticsearchAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorProvider() {
        return () -> Optional.of("system");
    }
}
```

Bean này giúp minh họa cơ chế nhưng không phù hợp cho hệ thống nhiều người dùng vì mọi document đều được ghi nhận là `system`. Trong ứng dụng thực tế, actor nên được lấy từ ngữ cảnh xác thực hoặc được truyền qua một execution context có kiểm soát.

### Liên kết bean bằng `auditorAwareRef`

Nếu chỉ có một bean `AuditorAware`, Spring có thể tìm bean phù hợp theo cơ chế cấu hình. Khi có nhiều auditor provider, nên chỉ định tên bean rõ ràng:

```java
@Configuration
@EnableElasticsearchAuditing(auditorAwareRef = "auditorProvider")
public class ElasticsearchAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorProvider() {
        return () -> Optional.of("system");
    }
}
```

`auditorAwareRef` là tên bean, không phải tên class hoặc tên field entity. Kiểu generic của provider phải tương thích với các thuộc tính `@CreatedBy` và `@LastModifiedBy`.

## 5. Lấy actor từ Spring Security

Trong ứng dụng dùng Spring Security, actor thường là username hoặc subject của `Authentication` hiện tại.

```java
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

@Configuration
public class ElasticsearchAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorProvider() {
        return () -> {
            Authentication authentication = SecurityContextHolder.getContext()
                .getAuthentication();

            if (authentication == null
                    || !authentication.isAuthenticated()
                    || authentication instanceof AnonymousAuthenticationToken) {
                return Optional.empty();
            }

            return Optional.of(authentication.getName());
        };
    }
}
```

Khi không có người dùng đã xác thực, provider trả `Optional.empty()`. Khi đó auditing không có actor để gán. Nếu ứng dụng cần ghi nhận tác vụ nền, có thể dùng actor hệ thống thông qua một execution context riêng thay vì giả định mọi request đều có `Authentication`.

### Vì sao cần loại `AnonymousAuthenticationToken`?

Trong một số cấu hình Spring Security, request chưa đăng nhập vẫn có một authentication object đại diện cho anonymous user. Chỉ kiểm tra `authentication != null` và `isAuthenticated()` có thể khiến actor anonymous bị ghi như một người dùng thực. Kiểm tra kiểu token hoặc một quy tắc actor rõ ràng giúp tránh điều này.

### Không nên lưu toàn bộ Authentication

Auditing thường chỉ cần một định danh ổn định như username, user ID hoặc service principal. Không lưu object `Authentication`, credentials, access token hoặc toàn bộ claims vào field auditing.

## 6. Xử lý tác vụ nền và actor hệ thống

Một scheduler, message consumer hoặc batch worker có thể chạy ngoài HTTP request. Trong trường hợp đó, `SecurityContextHolder` có thể không chứa actor người dùng.

Có thể định nghĩa actor hệ thống rõ ràng ở tầng ứng dụng. Một cách là dùng context riêng cho tác vụ nền:

```java
public final class AuditActorContext {

    private static final ThreadLocal<String> CURRENT = new ThreadLocal<>();

    private AuditActorContext() {
    }

    public static void set(String actor) {
        CURRENT.set(actor);
    }

    public static Optional<String> get() {
        return Optional.ofNullable(CURRENT.get());
    }

    public static void clear() {
        CURRENT.remove();
    }
}
```

`AuditorAware` có thể đọc context này hoặc kết hợp với SecurityContext theo quy tắc ưu tiên của ứng dụng. Khi dùng ThreadLocal, luôn xóa trong `finally` để tránh actor của tác vụ trước rò sang tác vụ sau trên thread pool:

```java
try {
    AuditActorContext.set("nightly-cleanup");
    cleanupService.run();
} finally {
    AuditActorContext.clear();
}
```

Với `@Async`, executor hoặc message listener, không giả định security context tự truyền qua thread. Nếu cần giữ danh tính người khởi tạo, hãy truyền actor tường minh trong message/job metadata hoặc cấu hình cơ chế context propagation phù hợp.

## 7. Dùng `DateTimeProvider` để kiểm soát thời gian

Mặc định auditing sử dụng thời điểm hiện tại. Nếu muốn kiểm soát nguồn thời gian, có thể đăng ký `DateTimeProvider` và chỉ định bằng `dateTimeProviderRef`.

Ví dụ dùng `Clock`:

```java
import java.time.Clock;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;

@Configuration
public class TimeConfiguration {

    @Bean
    Clock auditClock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider auditDateTimeProvider(Clock auditClock) {
        return () -> Optional.of(auditClock.instant());
    }
}
```

Kết hợp với auditing configuration:

```java
@Configuration
@EnableElasticsearchAuditing(
    auditorAwareRef = "auditorProvider",
    dateTimeProviderRef = "auditDateTimeProvider"
)
public class ElasticsearchAuditingConfiguration {
    // AuditorAware bean
}
```

`DateTimeProvider` trả `Optional<TemporalAccessor>`. `Instant` là kiểu temporal phù hợp và biểu diễn một thời điểm tuyệt đối. Khi cần múi giờ hiển thị, ứng dụng có thể chuyển đổi ở tầng API/UI thay vì lưu giờ địa phương không kèm timezone.

### Vì sao nên dùng `Clock`?

- Production có thể dùng `Clock.systemUTC()`.
- Unit/integration test có thể dùng `Clock.fixed(...)`.
- Service không phải gọi trực tiếp `Instant.now()` ở nhiều nơi.
- Dễ kiểm tra giá trị `createdDate` và `lastModifiedDate` một cách xác định.

## 8. Cấu hình đầy đủ cho auditing

Ví dụ cấu hình kết hợp actor provider và date-time provider:

```java
import java.time.Clock;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.elasticsearch.config.EnableElasticsearchAuditing;

@Configuration
@EnableElasticsearchAuditing(
    auditorAwareRef = "auditorProvider",
    dateTimeProviderRef = "auditDateTimeProvider"
)
public class ElasticsearchAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorProvider() {
        return () -> Optional.of("system");
    }

    @Bean
    Clock auditClock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider auditDateTimeProvider(Clock auditClock) {
        return () -> Optional.of(auditClock.instant());
    }
}
```

Trong ứng dụng thực tế, thay actor cố định bằng provider lấy người dùng hiện tại hoặc service principal. Tách bean cấu hình thời gian và actor nếu muốn kiểm thử hoặc thay thế độc lập.

## 9. `modifyOnCreate` và `setDates`

`@EnableElasticsearchAuditing` cung cấp các tùy chọn điều khiển hành vi auditing ở các phiên bản Spring Data hỗ trợ:

- `setDates`: bật/tắt việc gán các thuộc tính ngày tạo và ngày sửa.
- `modifyOnCreate`: quyết định có gán metadata sửa đổi (`@LastModifiedBy`, `@LastModifiedDate`) ngay ở lần tạo mới hay không.

Mặc định, auditing thường gán date fields và `modifyOnCreate` là `true`, nên `lastModifiedDate` có thể bằng `createdDate` ở lần tạo đầu tiên.

Ví dụ không gán metadata sửa đổi khi tạo mới:

```java
@Configuration
@EnableElasticsearchAuditing(
    auditorAwareRef = "auditorProvider",
    modifyOnCreate = false
)
public class ElasticsearchAuditingConfiguration {
}
```

Khi đó, `@CreatedBy`/`@CreatedDate` vẫn phản ánh lần tạo; các trường `@LastModified...` chỉ được gán khi entity được sửa theo semantics của auditing.

Nếu đặt `setDates = false`, date auditing bị tắt. Không nên dùng tùy chọn này nếu entity phụ thuộc vào `@CreatedDate` hoặc `@LastModifiedDate`.

Tên và phạm vi thuộc tính của annotation có thể khác giữa các thế hệ Spring Data; kiểm tra Javadoc đúng version đang dùng trước khi dựa vào tùy chọn cấu hình.

## 10. Vòng đời callback khi lưu entity

Auditing không chạy như một câu lệnh riêng mà được áp dụng trong vòng đời entity của Spring Data. Với các thao tác lưu qua repository hoặc `ElasticsearchOperations`, Spring Data có thể gọi entity callback trước khi chuyển entity thành dữ liệu ghi.

```text
Controller / Service
        |
        v
Repository.save(entity)
hoặc ElasticsearchOperations.save(entity)
        |
        v
Auditing callback
        |
        +--> Đọc AuditorAware
        +--> Đọc DateTimeProvider
        +--> Gán @CreatedBy / @CreatedDate khi tạo
        +--> Gán @LastModifiedBy / @LastModifiedDate theo cấu hình
        |
        v
Entity conversion / mapping
        |
        v
Index API của Elasticsearch
        |
        v
Các field auditing được lưu trong _source
```

Auditing callback phụ thuộc vào đường ghi đi qua Spring Data mapping/callback infrastructure. Nếu ứng dụng gọi Elasticsearch Java API Client trực tiếp hoặc gửi raw REST request, Spring Data không tự chạy callback cho request đó.

### Callback không phải database trigger

Auditing được thực hiện ở tầng ứng dụng Spring Data. Một tiến trình khác ghi trực tiếp vào Elasticsearch sẽ không tự động nhận các giá trị auditing này. Nếu nhiều hệ thống cùng ghi một index, cần thống nhất quy tắc ghi metadata giữa các writer.

## 11. `save()` và `saveAll()`

Ví dụ dùng repository:

```java
ProductDocument product = new ProductDocument();
product.setId("p-100");
product.setName("Wireless Mouse");

productRepository.save(product);
```

Khi auditing được bật và callback được áp dụng, các field `createdBy`, `createdDate`, `lastModifiedBy`, `lastModifiedDate` được điền theo cấu hình trước khi document được lưu.

Lưu nhiều entity:

```java
productRepository.saveAll(products);
```

Hãy xác nhận đường triển khai `saveAll` của version Spring Data đang dùng có đi qua entity callbacks. Các API bulk cấp thấp nhận `IndexQuery`/raw request không nhất thiết có cùng hành vi với việc lưu từng entity. Nếu metadata auditing là bắt buộc, hãy kiểm tra rõ đường ghi được chọn và có thể gán metadata tường minh trước khi tạo bulk actions.

## 12. Partial update và các API bỏ qua entity callback

Một điểm quan trọng: không phải mọi thao tác cập nhật đều chạy qua entity auditing callback.

Ví dụ Update API chỉ gửi một phần document:

```java
Document partial = Document.create();
partial.put("name", "Wireless Mouse Pro");

UpdateQuery update = UpdateQuery.builder("p-100")
    .withDocument(partial)
    .build();

operations.update(update, IndexCoordinates.of("products"));
```

Đường cập nhật này làm việc với partial document, không nhất thiết nạp entity đầy đủ và chạy callback auditing như `save(entity)`. Vì vậy, không giả định `lastModifiedDate` và `lastModifiedBy` tự được cập nhật trong mọi partial update, update-by-query, scripted update hoặc bulk action.

Nếu cần auditing cho partial update:

- Gán `lastModifiedBy` và `lastModifiedDate` tường minh vào partial document.
- Hoặc đọc entity, sửa thuộc tính rồi lưu lại qua đường Spring Data có callback, nếu chi phí và concurrency phù hợp.
- Hoặc đóng gói cập nhật vào một service chung để mọi đường ghi đều áp dụng quy tắc auditing.

Ví dụ:

```java
Document partial = Document.create();
partial.put("name", "Wireless Mouse Pro");
partial.put("lastModifiedBy", currentActor);
partial.put("lastModifiedDate", clock.instant());
```

Đảm bảo tên field và kiểu dữ liệu tương thích với mapping. Không dùng cả callback tự động và gán thủ công một cách không nhất quán, vì giá trị có thể bị ghi đè hoặc lệch nhau.

## 13. Auditing và `@Version` là hai việc khác nhau

Auditing trả lời ai và khi nào; optimistic locking kiểm soát cập nhật đồng thời.

| Cơ chế | Mục tiêu | Ví dụ |
|---|---|---|
| `@CreatedBy` | Ai tạo document | `alice` |
| `@CreatedDate` | Khi nào tạo | `2026-11-13T09:00:00Z` |
| `@LastModifiedBy` | Ai sửa gần nhất | `bob` |
| `@LastModifiedDate` | Khi nào sửa gần nhất | `2026-11-13T10:30:00Z` |
| `@Version` | Kiểm soát version khi cập nhật | Version 7 → 8 |
| `_seq_no` + `_primary_term` | Kiểm soát thao tác dựa trên trạng thái đã đọc | Conditional update token |

Một entity có thể dùng cả auditing và optimistic concurrency. Việc bật `@EnableElasticsearchAuditing` không tự bật `@Version`, không tự thêm `if_seq_no`/`if_primary_term` và không giải quyết lost update.

## 14. Mapping field auditing trong Elasticsearch

Các field auditing thường được lưu trong `_source` như field bình thường. Chọn kiểu mapping dựa trên cách sử dụng:

| Field | Mapping thường phù hợp | Mục đích |
|---|---|---|
| `createdBy` | `keyword` | Lọc hoặc nhóm theo actor tạo |
| `lastModifiedBy` | `keyword` | Lọc theo actor sửa gần nhất |
| `createdDate` | `date` | Lọc theo thời gian tạo, sort và range query |
| `lastModifiedDate` | `date` | Lọc theo lần sửa gần nhất |

Ví dụ mapping:

```json
{
  "properties": {
    "createdBy": { "type": "keyword" },
    "createdDate": { "type": "date" },
    "lastModifiedBy": { "type": "keyword" },
    "lastModifiedDate": { "type": "date" }
  }
}
```

Nếu dùng tên field khác trong Java và Elasticsearch, khai báo mapping name rõ ràng bằng `@Field(name = "...")` theo quy ước của entity.

### Lưu thời gian UTC

`Instant` biểu diễn một thời điểm UTC. Khi serialize, giá trị thường có dạng ISO-8601 với `Z`. Nếu giao diện cần giờ địa phương, chuyển đổi ở tầng trình bày. Tránh lưu `LocalDateTime` nếu hệ thống cần xác định chính xác một thời điểm toàn cầu mà không có timezone đi kèm.

## 15. Truy vấn metadata auditing

Vì auditing fields là dữ liệu trong `_source` và có mapping tương ứng, có thể dùng Query DSL thông thường.

Tìm document do một actor tạo:

```http
POST /products/_search
Content-Type: application/json

{
  "query": {
    "term": {
      "createdBy": "alice"
    }
  }
}
```

Tìm document được sửa trong một khoảng thời gian:

```json
{
  "query": {
    "range": {
      "lastModifiedDate": {
        "gte": "2026-11-01T00:00:00Z",
        "lt": "2026-12-01T00:00:00Z"
      }
    }
  }
}
```

Sort theo thời gian sửa mới nhất:

```json
{
  "sort": [
    {
      "lastModifiedDate": {
        "order": "desc"
      }
    }
  ]
}
```

Nếu cần audit report lớn, có thể kết hợp aggregation hoặc export theo batch. Hãy nhớ rằng `lastModifiedBy` chỉ là actor gần nhất, không phải danh sách tất cả actor từng sửa.

## 16. Kiểm thử auditing với actor xác định

Unit/integration test nên kiểm soát cả actor và thời gian để assertion ổn định.

Ví dụ dùng `Clock.fixed`:

```java
Clock fixedClock = Clock.fixed(
    Instant.parse("2026-11-13T09:00:00Z"),
    ZoneOffset.UTC
);
```

Trong test configuration, cung cấp `AuditorAware` trả về actor cố định và `DateTimeProvider` dùng fixed clock. Sau khi lưu entity qua repository hoặc `ElasticsearchOperations`, kiểm tra:

```java
assertThat(saved.getCreatedBy()).isEqualTo("test-user");
assertThat(saved.getLastModifiedBy()).isEqualTo("test-user");
assertThat(saved.getCreatedDate()).isEqualTo(fixedInstant);
assertThat(saved.getLastModifiedDate()).isEqualTo(fixedInstant);
```

Khi kiểm tra dữ liệu qua `_search`, cần bảo đảm refresh đã diễn ra. Có thể dùng refresh policy phù hợp trong test hoặc gọi `IndexOperations.refresh()` sau khi nạp fixture. Không dùng `Thread.sleep()` cố định để chờ refresh.

### Kiểm thử lần cập nhật

Một test có thể:

1. Lưu entity lần đầu với actor `alice` và thời điểm T1.
2. Đọc lại entity.
3. Đổi actor sang `bob` và clock sang T2.
4. Lưu entity lần hai qua đường có callback.
5. Xác nhận `createdBy`/`createdDate` giữ giá trị T1, còn `lastModifiedBy`/`lastModifiedDate` là `bob`/T2.

Nếu test partial update, hãy kiểm tra riêng liệu đường API đó có chạy callback hay không; nếu không, xác nhận service đã gán metadata sửa đổi tường minh.

## 17. Kiểm thử `AuditorAware` với Spring Security

Với ứng dụng bảo mật, kiểm thử các tình huống:

- Authentication hợp lệ trả đúng actor.
- Không có authentication trả `Optional.empty()` hoặc actor hệ thống theo chính sách.
- Anonymous authentication không bị ghi như user đã đăng nhập.
- Tác vụ nền có actor hệ thống rõ ràng.
- Context được xóa sau khi xử lý trong thread pool.
- Tên actor hoặc user ID không chứa credentials/token.

Nếu dùng `@WithMockUser` trong Spring Security Test, xác nhận auditor provider đọc đúng principal/name mà test cấu hình. Nếu ứng dụng dùng custom principal, ánh xạ sang định danh actor ổn định thay vì phụ thuộc vào `toString()` của principal.

## 18. Những giới hạn của auditing

Auditing rất hữu ích cho metadata vận hành nhưng không phải một hệ thống audit trail đầy đủ.

### Chỉ lưu trạng thái gần nhất

`@LastModifiedBy` và `@LastModifiedDate` chỉ lưu actor và thời điểm của lần sửa gần nhất. Khi document được cập nhật lần nữa, giá trị cũ bị thay thế.

Nếu cần biết mọi lần thay đổi, cần lưu event/audit record riêng, ví dụ:

```json
{
  "entityId": "p-100",
  "action": "PRICE_CHANGED",
  "actor": "alice",
  "occurredAt": "2026-11-13T09:30:00Z",
  "before": { "price": 100 },
  "after": { "price": 120 }
}
```

### Không tự bao phủ mọi writer

Một writer dùng raw REST, Elasticsearch Java API Client trực tiếp, ingest pipeline hoặc một ứng dụng khác không chạy Spring Data callback. Các writer này có thể không điền auditing fields.

### Không bảo đảm tính bất biến

Các field auditing nằm trong document có thể bị cập nhật bởi quyền ghi phù hợp. Chúng không phải bằng chứng mật mã hoặc log chống sửa đổi.

### Không tự xác thực actor

`AuditorAware` chỉ trả giá trị do ứng dụng cung cấp. Nếu provider lấy actor sai hoặc context bị rò giữa request, auditing sẽ ghi sai actor. Cần kiểm thử và bảo vệ context propagation.

## 19. Thiết kế audit trail khi cần lịch sử đầy đủ

Nếu nghiệp vụ yêu cầu truy vết đầy đủ, có thể kết hợp metadata auditing trong entity với một index event append-only:

```text
Lệnh nghiệp vụ
      |
      v
Kiểm tra quyền và trạng thái
      |
      +----> Cập nhật document hiện tại
      |
      +----> Ghi audit event riêng
                    |
                    v
             entityId / actor
             action / timestamp
             before / after hoặc diff
```

Audit event nên có ID riêng, thời gian, actor, action, entity ID và dữ liệu thay đổi cần thiết. Nếu hai thao tác ghi cần nhất quán, cân nhắc transactional outbox hoặc cơ chế đảm bảo phát event phù hợp với kiến trúc; không giả định hai request Elasticsearch độc lập tạo thành transaction nguyên tử.

Index audit cần quyền ghi hạn chế, chính sách retention, backup và kiểm soát xóa. Nếu yêu cầu tuân thủ nghiêm ngặt, cần đánh giá thêm storage bất biến hoặc hệ thống audit chuyên dụng.

## 20. Auditing trong bulk ingestion

Khi nạp dữ liệu hàng loạt, actor có thể là người khởi tạo import hoặc service account thực hiện import. Nên phân biệt hai khái niệm nếu nghiệp vụ cần:

- `createdBy`: actor được xem là người tạo bản ghi theo quy tắc nghiệp vụ.
- `lastModifiedBy`: actor/service thực hiện lần ghi hiện tại.

Ví dụ import do `migration-service` thực hiện theo yêu cầu của `admin-42`. Ứng dụng cần quyết định auditing ghi actor nào. Có thể lưu thêm `requestedBy` hoặc `importJobId` như field nghiệp vụ riêng nếu cần giữ cả người yêu cầu và service thực thi.

Với bulk API cấp thấp, hãy tạo metadata auditing trước khi dựng `IndexQuery`/bulk action hoặc dùng đường ghi đã được xác nhận chạy callback. Không mặc định raw bulk request tự gọi `AuditorAware`.

## 21. Lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `@CreatedDate` luôn null | Chưa bật auditing, config không được scan hoặc callback không chạy | Kiểm tra `@EnableElasticsearchAuditing` và đường persist |
| `@CreatedBy` null | Không có `AuditorAware` hoặc provider trả empty | Đăng ký bean và kiểm tra SecurityContext |
| Actor luôn là `system` | Provider trả actor cố định | Lấy actor theo request/job context |
| `lastModifiedDate` không đổi | Partial update hoặc raw client bypass callback | Gán tường minh hoặc lưu qua entity callback path |
| `createdDate` bị thay đổi khi update | Logic ứng dụng ghi đè field hoặc callback/mapping không đúng | Không tự gán lại created metadata; kiểm tra callback và update path |
| Date lệch múi giờ | Dùng local time không có timezone hoặc serialize không thống nhất | Dùng `Instant`/UTC và chuẩn hóa ở tầng hiển thị |
| Không tìm thấy ngay sau save | Chưa refresh | Dùng `WAIT_UNTIL` hoặc refresh index khi cần |
| Actor sai trong async worker | Security context không được truyền hoặc ThreadLocal không được clear | Truyền actor rõ ràng và quản lý context lifecycle |
| Bulk document thiếu audit fields | Bulk API cấp thấp không chạy entity callback | Gán metadata trước khi tạo bulk action |

## 22. Quy trình bật auditing trong ứng dụng

Một trình tự triển khai rõ ràng:

1. Xác định actor cần ghi là username, user ID hay service principal.
2. Thêm bốn field auditing vào entity với kiểu dữ liệu phù hợp.
3. Chọn mapping `keyword` cho actor và `date` cho timestamp nếu cần query/sort.
4. Tạo class cấu hình có `@EnableElasticsearchAuditing`.
5. Đăng ký `AuditorAware<T>` nếu cần `@CreatedBy`/`@LastModifiedBy`.
6. Chỉ định `auditorAwareRef` nếu có nhiều provider hoặc muốn cấu hình tường minh.
7. Cấu hình `DateTimeProvider`/`Clock` nếu cần kiểm soát thời gian.
8. Xác nhận cấu hình nằm trong component scan.
9. Kiểm tra repository/`ElasticsearchOperations` save path có chạy callback.
10. Xem xét riêng partial update, update-by-query, raw client và bulk action.
11. Kiểm thử actor, timestamp, lần tạo, lần sửa và context nền.
12. Xác định có cần audit event bất biến ngoài bốn field metadata hay không.

## 23. Ví dụ hoàn chỉnh: entity, configuration và service

Entity:

```java
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "articles")
public class ArticleDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String title;

    @CreatedBy
    @Field(type = FieldType.Keyword)
    private String createdBy;

    @CreatedDate
    @Field(type = FieldType.Date)
    private Instant createdDate;

    @LastModifiedBy
    @Field(type = FieldType.Keyword)
    private String lastModifiedBy;

    @LastModifiedDate
    @Field(type = FieldType.Date)
    private Instant lastModifiedDate;

    // Constructors, getters and setters
}
```

Configuration:

```java
import java.time.Clock;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.elasticsearch.config.EnableElasticsearchAuditing;

@Configuration
@EnableElasticsearchAuditing(
    auditorAwareRef = "auditorProvider",
    dateTimeProviderRef = "auditDateTimeProvider"
)
public class ElasticsearchAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorProvider() {
        return () -> Optional.of("article-service");
    }

    @Bean
    Clock auditClock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider auditDateTimeProvider(Clock auditClock) {
        return () -> Optional.of(auditClock.instant());
    }
}
```

Service:

```java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;
import org.springframework.stereotype.Service;

@Service
public class ArticleService {

    private final ArticleRepository repository;

    public ArticleService(ArticleRepository repository) {
        this.repository = repository;
    }

    public ArticleDocument create(ArticleDocument article) {
        return repository.save(article);
    }

    public ArticleDocument updateTitle(String id, String title) {
        ArticleDocument article = repository.findById(id)
            .orElseThrow(() -> new IllegalArgumentException("Article not found: " + id));

        article.setTitle(title);
        return repository.save(article);
    }
}

interface ArticleRepository
        extends ElasticsearchRepository<ArticleDocument, String> {
}
```

Ví dụ dùng actor service cố định để dễ đọc. Trong hệ thống có người dùng, thay `AuditorAware` bằng provider lấy actor từ security context hoặc execution context đã được quản lý. Với `updateTitle`, entity được đọc, sửa rồi lưu qua repository nên auditing callback có thể cập nhật metadata sửa đổi.

## 24. Kết luận

`@EnableElasticsearchAuditing` bật hạ tầng auditing của Spring Data Elasticsearch. Entity dùng `@CreatedBy`, `@CreatedDate`, `@LastModifiedBy` và `@LastModifiedDate` để đánh dấu metadata cần ghi. `AuditorAware<T>` cung cấp actor hiện tại; `DateTimeProvider` có thể kiểm soát nguồn thời gian. Có thể cấu hình provider bằng `auditorAwareRef` và `dateTimeProviderRef`, đồng thời điều chỉnh hành vi ngày sửa khi tạo bằng `modifyOnCreate` trong các phiên bản hỗ trợ.

Auditing được áp dụng qua entity callback khi dữ liệu đi qua đường persist của Spring Data. Partial update, update-by-query, raw REST/Java client và bulk action cấp thấp có thể không chạy callback, vì vậy cần kiểm tra đường ghi và gán metadata tường minh khi cần. Dùng `Instant`/UTC, quản lý actor cho tác vụ nền, kiểm thử bằng `Clock` cố định và không nhầm auditing metadata với optimistic locking. Bốn field auditing cho biết ai tạo và ai sửa gần nhất; nếu cần lịch sử mọi thay đổi hoặc bằng chứng chống sửa đổi, hãy bổ sung audit event/index chuyên biệt.

## Tài liệu tham khảo

- [Spring Data Elasticsearch – Auditing](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/auditing.html)
- [Spring Data Commons – Auditing](https://docs.spring.io/spring-data/commons/reference/auditing.html)
- [Spring Data Elasticsearch – `@EnableElasticsearchAuditing` API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/config/EnableElasticsearchAuditing.html)
- [Spring Data Commons – `AuditorAware` API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/AuditorAware.html)
- [Spring Data Commons – `DateTimeProvider` API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/auditing/DateTimeProvider.html)
- [Spring Data Elasticsearch – Entity callbacks](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/entity-callbacks.html)
