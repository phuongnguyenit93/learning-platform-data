# AuditorAware, DateTimeProvider và ngữ cảnh người thao tác

Auditing giúp document lưu lại ai đã tạo, ai sửa gần nhất và thời điểm các thao tác đó diễn ra. Trong Spring Data Elasticsearch, cơ chế này được tích hợp với entity callbacks: khi entity được lưu qua đường xử lý Spring Data có hỗ trợ auditing, các field được đánh dấu sẽ được tự động điền trước khi ghi document.

Hai thành phần quyết định metadata auditing:

- **`AuditorAware<T>`** cung cấp danh tính người hoặc tiến trình đang thực hiện thao tác.
- **`DateTimeProvider`** cung cấp thời điểm hiện tại để điền các field ngày tạo và ngày sửa.

Muốn auditing có ý nghĩa trong ứng dụng thực tế, cần thiết kế rõ ngữ cảnh người thao tác: request từ người dùng, scheduled job, batch import, message consumer hay thao tác quản trị. Không phải mọi thao tác ghi Elasticsearch đều có thông tin đăng nhập của người dùng, và không nên tự gán một người dùng giả chỉ để field audit luôn có giá trị.

## 1. Auditing lưu những thông tin nào?

Một document nghiệp vụ thường cần bốn field audit:

| Annotation | Ý nghĩa | Ví dụ |
|---|---|---|
| `@CreatedBy` | Danh tính tạo document | `user-1024` |
| `@LastModifiedBy` | Danh tính sửa gần nhất | `admin-17` |
| `@CreatedDate` | Thời điểm tạo | `2026-11-13T09:30:00Z` |
| `@LastModifiedDate` | Thời điểm sửa gần nhất | `2026-11-13T10:15:00Z` |

Ví dụ document sau khi được tạo:

~~~json
{
  "id": "DOC-1001",
  "title": "Inventory policy",
  "createdBy": "user-1024",
  "createdDate": "2026-11-13T09:30:00Z",
  "lastModifiedBy": "user-1024",
  "lastModifiedDate": "2026-11-13T09:30:00Z"
}
~~~

Sau khi một quản trị viên cập nhật document, các field có thể trở thành:

~~~json
{
  "id": "DOC-1001",
  "title": "Inventory policy v2",
  "createdBy": "user-1024",
  "createdDate": "2026-11-13T09:30:00Z",
  "lastModifiedBy": "admin-17",
  "lastModifiedDate": "2026-11-13T10:15:00Z"
}
~~~

Các field tạo ban đầu được giữ lại; các field sửa gần nhất phản ánh thao tác mới. Điều này giúp truy vết lịch sử cơ bản, nhưng không thay thế audit log bất biến nếu hệ thống cần lưu mọi lần thay đổi.

## 2. Bật auditing cho Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp annotation `@EnableElasticsearchAuditing` để kích hoạt auditing.

Ví dụ cấu hình:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.config.EnableElasticsearchAuditing;

@Configuration
@EnableElasticsearchAuditing(
        auditorAwareRef = "auditorAware",
        dateTimeProviderRef = "auditingDateTimeProvider",
        modifyOnCreate = true
)
public class ElasticsearchAuditingConfiguration {
}
~~~

Các thuộc tính quan trọng:

- `auditorAwareRef`: tên bean cung cấp `AuditorAware<?>`.
- `dateTimeProviderRef`: tên bean cung cấp `DateTimeProvider`.
- `modifyOnCreate`: quy định có điền thông tin sửa ngay khi tạo entity hay không. Mặc định là `true` trong cấu hình auditing thông thường.
- `setDates`: bật/tắt việc điền các field ngày tạo và ngày sửa; mặc định là bật.

Nếu không chỉ định bean riêng, Spring Data có thể tìm bean phù hợp theo quy tắc mặc định. Khai báo tên rõ ràng qua các thuộc tính ref giúp tránh nhầm khi ứng dụng có nhiều bean auditing.

Chỉ cần cấu hình auditing một lần trong application context. Tránh khai báo `@EnableElasticsearchAuditing` lặp lại ở nhiều configuration class vì có thể tạo cấu hình không rõ ràng.

## 3. Khai báo field audit trên entity

Các annotation audit nằm trong package `org.springframework.data.annotation`, không phải package annotation riêng của Elasticsearch.

~~~java
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;

import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "documents")
public class DocumentRecord {

    @Id
    private String id;

    private String title;

    @CreatedBy
    private String createdBy;

    @LastModifiedBy
    private String lastModifiedBy;

    @CreatedDate
    @Field(type = FieldType.Date)
    private Instant createdDate;

    @LastModifiedDate
    @Field(type = FieldType.Date)
    private Instant lastModifiedDate;

    // Constructors, getters and setters
}
~~~

Giải thích:

- `@CreatedBy` và `@LastModifiedBy` nhận giá trị từ `AuditorAware`.
- `@CreatedDate` và `@LastModifiedDate` nhận giá trị từ `DateTimeProvider`.
- `Instant` biểu diễn thời điểm tuyệt đối và phù hợp cho metadata audit.
- `@Field(type = FieldType.Date)` khai báo mapping Elasticsearch cho field ngày.

Nên dùng một kiểu danh tính thống nhất cho các field người thao tác, ví dụ user ID dạng String hoặc UUID. Đừng lúc lưu username, lúc lưu email và lúc lưu display name vào cùng một field; việc truy vấn và đối soát sau này sẽ khó hơn.

Nếu hệ thống cần lưu cả mã người dùng và tên hiển thị, hãy lưu chúng thành các field riêng hoặc giữ ID ổn định trong audit field rồi tra tên từ hệ thống danh tính.

## 4. AuditorAware<T> cung cấp danh tính người thao tác

`AuditorAware<T>` là interface của Spring Data, với phương thức:

~~~java
Optional<T> getCurrentAuditor();
~~~

Spring Data gọi phương thức này khi cần điền `@CreatedBy` hoặc `@LastModifiedBy`. Kiểu `T` phải tương thích với kiểu field audit trong entity.

Ví dụ ứng dụng lưu user ID dạng String:

~~~java
import java.util.Optional;

import org.springframework.data.domain.AuditorAware;
import org.springframework.stereotype.Component;

@Component("auditorAware")
public class CurrentAuditorAware implements AuditorAware<String> {

    @Override
    public Optional<String> getCurrentAuditor() {
        return Optional.of("user-1024");
    }
}
~~~

Đây chỉ là ví dụ minh họa. Trong ứng dụng thực tế, không nên hard-code một user ID vì mọi thao tác sẽ bị ghi nhận như cùng một người. Auditor cần được lấy từ security context hoặc ngữ cảnh thực thi đáng tin cậy.

Nếu không có auditor, có thể trả về `Optional.empty()`. Khi đó Spring Data không có giá trị để điền field người thao tác. Hãy quyết định rõ field có được phép null hay ứng dụng phải cung cấp actor cho mọi luồng ghi.

## 5. Lấy auditor từ Spring Security

Trong ứng dụng Spring Security dạng servlet, danh tính xác thực thường có trong `SecurityContextHolder`.

Ví dụ:

~~~java
import java.util.Optional;

import org.springframework.data.domain.AuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;

@Component("auditorAware")
public class SecurityAuditorAware implements AuditorAware<String> {

    @Override
    public Optional<String> getCurrentAuditor() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return Optional.empty();
        }

        return Optional.ofNullable(authentication.getName());
    }
}
~~~

Các bước:

1. Đọc `Authentication` hiện tại.
2. Kiểm tra authentication có tồn tại và đã xác thực không.
3. Loại trừ `AnonymousAuthenticationToken`; anonymous token có thể báo `isAuthenticated() = true`.
4. Lấy tên principal bằng `getName()`.
5. Trả `Optional.empty()` nếu không có người dùng phù hợp.

`authentication.getName()` thường trả username hoặc tên định danh theo cấu hình authentication. Nếu audit cần user ID bất biến, hãy lấy ID từ custom principal thay vì mặc định dùng username.

Ví dụ với principal riêng của ứng dụng:

~~~java
public interface ApplicationPrincipal {
    String userId();
}
~~~

Có thể kiểm tra kiểu principal:

~~~java
Object principal = authentication.getPrincipal();

if (principal instanceof ApplicationPrincipal applicationPrincipal) {
    return Optional.of(applicationPrincipal.userId());
}

return Optional.ofNullable(authentication.getName());
~~~

Tên interface và cách lấy ID phải khớp với principal thực tế của ứng dụng. Không ép kiểu principal tùy tiện vì một số cơ chế xác thực có thể trả về String, UserDetails hoặc kiểu custom khác.

## 6. Xử lý request không có người dùng đăng nhập

Không phải mọi thao tác đều bắt nguồn từ một request HTTP có người dùng:

- Scheduled job chạy theo lịch.
- Batch import dữ liệu.
- Message consumer xử lý event.
- Đồng bộ dữ liệu từ hệ thống bên ngoài.
- Tiến trình bảo trì hoặc migration.
- Tác vụ quản trị do service khác gọi.

Có hai chính sách phổ biến:

| Chính sách | Khi không có authentication | Khi phù hợp |
|---|---|---|
| Không có auditor | Trả `Optional.empty()` | Field người thao tác được phép thiếu hoặc luồng hệ thống không cần actor |
| System actor | Trả ID như `system:nightly-import` | Cần truy vết rõ tiến trình hệ thống đã ghi document |

Nếu dùng system actor, hãy xác định actor theo tác vụ hoặc service, không dùng chung một chuỗi `system` cho mọi loại công việc nếu cần phân biệt nguồn thay đổi.

Ví dụ:

- `system:nightly-import`
- `system:inventory-reconciliation`
- `service:catalog-sync`

Không dùng `anonymous` để biểu diễn job hệ thống. Anonymous có nghĩa không xác định được danh tính người dùng, còn system actor là một tiến trình có danh tính nghiệp vụ rõ ràng.

### Không lấy actor từ dữ liệu client tùy ý

Không nên cho request gửi `createdBy` hoặc `lastModifiedBy` rồi tin trực tiếp giá trị đó. Người dùng có thể giả mạo ID của người khác.

Auditor phải đến từ security context đã xác thực hoặc một context hệ thống do server kiểm soát. Nếu một service ghi thay mặt người dùng, cần xác định rõ đó là actor người dùng, service thực hiện hay cả hai; đừng ghi nhầm danh tính.

## 7. DateTimeProvider kiểm soát thời điểm auditing

`DateTimeProvider` thuộc package `org.springframework.data.auditing`. Interface này cung cấp thời điểm hiện tại dưới dạng `Optional<TemporalAccessor>`.

~~~java
import java.time.Instant;
import java.util.Optional;

import org.springframework.data.auditing.DateTimeProvider;

public class UtcDateTimeProvider implements DateTimeProvider {

    @Override
    public Optional<TemporalAccessor> getNow() {
        return Optional.of(Instant.now());
    }
}
~~~

Nếu triển khai trực tiếp, cần import `java.time.temporal.TemporalAccessor`. Trong thực tế, nên inject `Clock` để kiểm soát múi giờ và test dễ dàng hơn.

Ví dụ cấu hình bean:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;

@Configuration
public class AuditTimeConfiguration {

    @Bean
    Clock auditingClock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider auditingDateTimeProvider(Clock auditingClock) {
        return () -> Optional.of(Instant.now(auditingClock));
    }
}
~~~

Ở đây:

- `Clock.systemUTC()` cung cấp clock theo UTC.
- `Instant.now(clock)` lấy thời điểm theo clock được inject.
- `DateTimeProvider` trả về một `TemporalAccessor` để auditing handler sử dụng.

Kết hợp bean này với `dateTimeProviderRef = "auditingDateTimeProvider"` trong `@EnableElasticsearchAuditing`.

## 8. Vì sao nên inject Clock thay vì gọi Instant.now() trực tiếp?

Gọi `Instant.now()` trực tiếp trong code khiến thời gian phụ thuộc đồng hồ hệ thống. Test phải dựa vào thời điểm thực tế, dễ gây khó khăn khi kiểm tra chính xác ngày tạo hoặc ngày sửa.

Khi inject `Clock`, có thể thay clock bằng một clock cố định:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock fixedClock = Clock.fixed(
        Instant.parse("2026-11-13T09:30:00Z"),
        ZoneOffset.UTC
);

Instant now = Instant.now(fixedClock);
~~~

Kết quả luôn là thời điểm đã chỉ định. Điều này hữu ích khi kiểm thử:

- Ngày tạo có đúng bằng thời điểm mong đợi không.
- Ngày sửa có được cập nhật khi save lần tiếp theo không.
- Hai thao tác có thứ tự thời gian đúng không.
- Dữ liệu lưu ở UTC có được chuyển đổi nhất quán không.

Trong test integration, có thể cung cấp một clock điều khiển được bằng `AtomicReference<Instant>`; mỗi lần test đổi giá trị reference trước khi save để kiểm tra ngày tạo và ngày sửa.

## 9. Chọn kiểu dữ liệu ngày giờ

Các kiểu Java thường gặp:

| Kiểu | Ý nghĩa | Khuyến nghị cho audit |
|---|---|---|
| `Instant` | Thời điểm tuyệt đối trên timeline UTC | Lựa chọn phù hợp cho created/modified timestamp |
| `OffsetDateTime` | Ngày giờ kèm UTC offset | Dùng khi cần giữ offset đầu vào |
| `LocalDateTime` | Ngày giờ không kèm múi giờ | Cần quy ước timezone rõ ràng |
| `java.util.Date` | Thời điểm dạng legacy | Có thể dùng trong hệ thống cũ |
| `Long` | Epoch value | Chỉ dùng khi hợp đồng dữ liệu quy định rõ đơn vị |

Với audit metadata, `Instant` thường là lựa chọn dễ đối chiếu giữa nhiều service và timezone. Nếu lưu `LocalDateTime`, hai hệ thống ở múi giờ khác nhau có thể hiểu cùng một giá trị theo những thời điểm khác nhau.

Elasticsearch field type `date` thường có độ phân giải millisecond. Nếu nghiệp vụ cần lưu độ phân giải nanosecond, cần xem xét `date_nanos` và xác nhận mapping/conversion của phiên bản Spring Data đang dùng. Không nên giả định chỉ vì Java `Instant` có nanosecond precision thì index `date` cũng giữ nguyên độ chính xác đó.

## 10. Quy tắc khi tạo mới và cập nhật

Khi auditing được bật, các annotation xác định vai trò của từng field:

- `@CreatedBy`: danh tính lúc tạo.
- `@CreatedDate`: thời điểm lúc tạo.
- `@LastModifiedBy`: danh tính sửa gần nhất.
- `@LastModifiedDate`: thời điểm sửa gần nhất.

Với `modifyOnCreate = true`, thông tin sửa cũng được điền khi entity được tạo. Vì vậy, một document mới có thể có `createdDate` và `lastModifiedDate` bằng nhau, đồng thời `createdBy` và `lastModifiedBy` cũng bằng nhau.

Nếu đặt `modifyOnCreate = false`, auditing handler không điền thông tin modification trên lần tạo theo chính sách đó. Chọn cấu hình dựa trên ý nghĩa dữ liệu và cách API của ứng dụng sử dụng các field.

Ví dụ:

| Thao tác | createdBy | createdDate | lastModifiedBy | lastModifiedDate |
|---|---|---|---|---|
| Tạo bởi user A | user A | thời điểm T1 | user A nếu modifyOnCreate bật | T1 |
| Sửa bởi user B | user A | giữ T1 | user B | T2 |
| Sửa bởi system job | user A | giữ T1 | system actor hoặc empty theo policy | T3 |

Không nên tự cập nhật `createdBy` hoặc `createdDate` trong logic thông thường. Đây là metadata tạo ban đầu, nên giữ nguyên sau khi document đã được tạo.

## 11. Entity callbacks là cơ chế thực thi auditing

Spring Data Elasticsearch tích hợp auditing qua entity callback. Callback auditing được áp dụng trong quá trình chuyển entity sang document khi sử dụng các API Spring Data có hỗ trợ callback.

Luồng khái quát:

~~~mermaid
flowchart TD
    A["Repository.save(entity) hoặc operations.save(entity)"] --> B["Spring Data nhận entity"]
    B --> C["Auditing entity callback"]
    C --> D["AuditorAware lấy actor"]
    C --> E["DateTimeProvider lấy thời điểm"]
    D --> F["Điền CreatedBy / LastModifiedBy"]
    E --> G["Điền CreatedDate / LastModifiedDate"]
    F --> H["Entity được chuyển thành Elasticsearch document"]
    G --> H
    H --> I["Index API ghi document"]
~~~

Vì auditing gắn với callback của Spring Data, cần phân biệt các đường ghi:

| Đường ghi | Có nên kỳ vọng auditing tự chạy? |
|---|---|
| Repository `save(entity)` | Có, khi auditing đã được bật và entity metadata được nhận diện |
| `ElasticsearchOperations.save(entity)` | Có, qua callback của Spring Data |
| Gửi request bằng Java API Client trực tiếp | Không; không đi qua entity callback Spring Data |
| Gửi REST request trực tiếp | Không |
| Script update bằng `UpdateQuery` | Không nên giả định callback entity sẽ điền field audit |
| Bulk API cấp thấp | Không nên giả định callback sẽ chạy cho từng object |

Với partial update hoặc script update, nếu cần thay đổi `lastModifiedBy` và `lastModifiedDate`, hãy truyền các giá trị đó vào update một cách tường minh hoặc dùng một đường ghi entity có callback phù hợp.

Với bulk ingestion, xác nhận chính xác API bulk đang sử dụng có kích hoạt entity callbacks trong phiên bản Spring Data của dự án hay không. Nếu bulk path bỏ qua callback, hãy điền metadata trước khi tạo bulk request. Không dựa vào việc auditing đã bật để suy ra mọi request ghi đều được audit tự động.

## 12. Ngữ cảnh người thao tác trong request đồng bộ

Với request HTTP đồng bộ, SecurityContext thường được thiết lập trong quá trình xác thực và có thể được đọc trong cùng thread xử lý.

Luồng thường gặp:

~~~text
HTTP request
   |
   v
Authentication filter
   |
   v
SecurityContextHolder
   |
   v
Controller / Service
   |
   v
Repository.save(entity)
   |
   v
AuditorAware.getCurrentAuditor()
   |
   v
createdBy / lastModifiedBy
~~~

Không truyền danh tính người dùng qua một field request body rồi dùng field đó làm auditor. Auditor phải đến từ security context đã xác thực hoặc cơ chế server-side tương đương.

Nếu một service thực hiện thay mặt user, cần phân biệt:

- **Actor**: người dùng khởi tạo yêu cầu.
- **Executor**: service hoặc worker thực sự thực hiện thao tác.
- **Tenant**: phạm vi dữ liệu mà thao tác thuộc về.

Bốn field auditing mặc định chỉ lưu actor và thời điểm. Nếu cần cả actor lẫn executor, hãy bổ sung field nghiệp vụ riêng như `executedBy` hoặc lưu thông tin đó trong audit event.

## 13. Ngữ cảnh trong @Async, executor và message consumer

Security context thường gắn với thread. Khi công việc chuyển sang thread khác, không nên giả định `SecurityContextHolder` tự động có cùng authentication.

Ví dụ:

~~~text
Request thread:
  user-1024
      |
      +---- submit task
                 |
                 v
             Worker thread:
             không có SecurityContext mặc định
~~~

Các trường hợp cần xử lý:

- `@Async` chạy trên thread pool.
- Scheduled job.
- Kafka/RabbitMQ listener.
- Batch worker.
- Executor tự tạo.
- Công việc được đẩy vào queue rồi chạy ở process khác.

Có một số cách thiết kế:

1. Dùng cơ chế truyền SecurityContext được Spring Security hỗ trợ cho executor khi thực sự cần giữ context request.
2. Truyền actor ID tường minh trong command/message do server tạo và xác thực.
3. Dùng system actor cho job chạy độc lập với người dùng.
4. Tạo một abstraction actor context để service không phụ thuộc trực tiếp vào `SecurityContextHolder`.

Không nên giữ một request security context trong một job chạy lâu sau khi request đã kết thúc nếu chính sách bảo mật không cho phép. Với message qua process khác, hãy truyền metadata actor đã được xác thực trong envelope và kiểm tra nguồn phát message.

### Ví dụ actor context cho job hệ thống

Có thể định nghĩa một abstraction:

~~~java
public interface ActorContext {
    Optional<String> currentActorId();
}
~~~

Một implementation cho request có thể đọc Spring Security. Một implementation khác cho job có thể trả system actor theo tên tác vụ.

Service auditing chỉ phụ thuộc `ActorContext` thông qua `AuditorAware`, giúp tách logic danh tính khỏi cơ chế chạy cụ thể.

Nếu dùng ThreadLocal cho actor context trong worker, phải xóa context trong `finally` sau mỗi task. Nếu không, thread pool tái sử dụng thread có thể khiến actor của task trước bị rò sang task sau.

## 14. Thiết kế AuditorAware cho cả user và system actor

Một ứng dụng có thể có nhiều loại actor. Thay vì nhét toàn bộ logic vào một class dài, tách việc lấy actor thành một abstraction.

~~~java
public interface ActorProvider {
    Optional<String> currentActorId();
}
~~~

Auditor:

~~~java
import java.util.Optional;

import org.springframework.data.domain.AuditorAware;
import org.springframework.stereotype.Component;

@Component("auditorAware")
public class ApplicationAuditorAware implements AuditorAware<String> {

    private final ActorProvider actorProvider;

    public ApplicationAuditorAware(ActorProvider actorProvider) {
        this.actorProvider = actorProvider;
    }

    @Override
    public Optional<String> getCurrentAuditor() {
        return actorProvider.currentActorId();
    }
}
~~~

Một `ActorProvider` có thể ưu tiên actor từ request đã xác thực; nếu không có, kiểm tra job context do ứng dụng thiết lập; cuối cùng trả empty hoặc system actor theo policy.

Điều quan trọng là policy phải rõ ràng. Không tự động gán `system` cho mọi request không có authentication vì điều đó có thể che giấu lỗi cấu hình bảo mật hoặc mất context.

## 15. Tách audit metadata khỏi lịch sử thay đổi bất biến

Bốn field auditing chỉ giữ trạng thái hiện tại:

- Ai tạo document.
- Khi nào document được tạo.
- Ai sửa gần nhất.
- Khi nào document được sửa gần nhất.

Nếu document được sửa 20 lần, `@LastModifiedBy` chỉ giữ actor của lần sửa cuối. Nó không lưu 20 lần thay đổi.

Nếu cần lịch sử đầy đủ, nên dùng audit event hoặc change log riêng:

~~~json
{
  "eventId": "audit-evt-1001",
  "entityId": "DOC-1001",
  "action": "TITLE_CHANGED",
  "actorId": "admin-17",
  "occurredAt": "2026-11-13T10:15:00Z",
  "changes": {
    "title": {
      "old": "Inventory policy",
      "new": "Inventory policy v2"
    }
  }
}
~~~

Audit event cần được thiết kế về quyền ghi, retention, chống sửa/xóa và liên kết với thao tác nghiệp vụ. Không coi các field `@CreatedBy`/`@LastModifiedBy` là một hệ thống audit log bất biến.

Nếu cần bảo đảm document và audit event được ghi cùng nhau, Elasticsearch không cung cấp transaction nhiều document cho hai thao tác độc lập. Hãy dùng outbox hoặc cơ chế phát sự kiện phù hợp với nguồn dữ liệu chính.

## 16. Kiểm thử AuditorAware

`AuditorAware` là một interface đơn giản nên có thể kiểm thử riêng mà không cần Elasticsearch.

Ví dụ kiểm thử khi không có authentication:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Optional;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.context.SecurityContextHolder;

class SecurityAuditorAwareTest {

    private final SecurityAuditorAware auditorAware =
            new SecurityAuditorAware();

    @AfterEach
    void clearSecurityContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void returnsEmptyWhenNoAuthenticationExists() {
        assertThat(auditorAware.getCurrentAuditor())
                .isEqualTo(Optional.empty());
    }
}
~~~

Nếu constructor của implementation nhận dependency hoặc principal custom, điều chỉnh test theo class thực tế.

Các test nên có:

- Không có authentication.
- Authentication chưa xác thực.
- Anonymous authentication.
- User đã xác thực.
- Principal custom có user ID.
- Principal không đúng kiểu dự kiến.
- Job context có system actor.
- Context được xóa sau khi task hoàn tất.

Mỗi test cần dọn SecurityContext để tránh trạng thái thread-local rò sang test tiếp theo.

## 17. Kiểm thử DateTimeProvider với Clock cố định

Date provider có thể kiểm tra độc lập:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;
import org.springframework.data.auditing.DateTimeProvider;

class AuditingDateTimeProviderTest {

    @Test
    void returnsTimeFromInjectedClock() {
        Instant expected =
                Instant.parse("2026-11-13T09:30:00Z");

        Clock clock = Clock.fixed(expected, ZoneOffset.UTC);

        DateTimeProvider provider =
                () -> Optional.of(Instant.now(clock));

        assertThat(provider.getNow())
                .contains(expected);
    }
}
~~~

Trong test integration với Elasticsearch, nên dùng một clock điều khiển được để kiểm tra:

1. Lưu entity lần đầu.
2. Kiểm tra `createdDate` và `lastModifiedDate`.
3. Thay thời điểm clock.
4. Cập nhật entity.
5. Kiểm tra `createdDate` được giữ nguyên.
6. Kiểm tra `lastModifiedDate` thay đổi.
7. Kiểm tra `createdBy` giữ actor ban đầu và `lastModifiedBy` nhận actor mới.

Test này cần chạy qua Repository hoặc `ElasticsearchOperations.save(...)` để xác nhận entity callback thực sự được gọi.

## 18. Kiểm thử auditing trên đường ghi thực tế

Một unit test cho `AuditorAware` không chứng minh auditing được bật trong application context. Cần có integration test xác nhận toàn bộ đường đi.

Một kịch bản:

~~~java
@Test
void writesAuditFieldsOnCreateAndUpdate() {
    // 1. Thiết lập actor = user-1024 và thời điểm T1.
    // 2. Save entity mới.
    // 3. Đọc lại document và xác nhận created/modified = user-1024, T1.
    // 4. Đổi actor = admin-17 và thời điểm T2.
    // 5. Save entity đã cập nhật.
    // 6. Đọc lại và xác nhận created giữ nguyên, modified = admin-17, T2.
}
~~~

Ngoài happy path, cần test:

- `AuditorAware` trả empty.
- `modifyOnCreate = false`.
- Entity có ID được gán trước.
- Entity có version.
- Update bằng `UpdateQuery` hoặc script.
- Bulk ingestion.
- Job không có user authentication.
- Security context trong executor/message listener.

Đặc biệt, entity có ID được gán trước có thể ảnh hưởng cách Spring Data xác định entity mới hay đã tồn tại. Cơ chế xác định trạng thái mới phụ thuộc metadata như version và ID. Nếu dùng deterministic ID, hãy kiểm thử `@CreatedDate`/`@CreatedBy` trên lần tạo đầu; không giả định entity có ID sẵn luôn được xem là mới.

## 19. Những lỗi thường gặp

### Quên bật @EnableElasticsearchAuditing

Có annotation trên entity nhưng không có auditing configuration thì các field có thể không được điền. Bật auditing trong application context và xác nhận bean được khởi tạo.

### Dùng sai package annotation

`@CreatedBy`, `@CreatedDate`, `@LastModifiedBy` và `@LastModifiedDate` thuộc `org.springframework.data.annotation`. Không nhầm với annotation mapping của Elasticsearch.

### Hard-code auditor

Một auditor cố định làm mọi document có cùng người tạo/sửa. Lấy actor từ security context hoặc actor context do server quản lý.

### Coi anonymous là người dùng đã xác thực

Một anonymous token có thể báo đã authenticated. Loại trừ `AnonymousAuthenticationToken` hoặc kiểm tra loại principal phù hợp.

### Job chạy nền không có actor

Scheduled job và consumer thường không có SecurityContext của request. Chọn policy trả empty hoặc system actor và ghi nhận nguồn tác vụ rõ ràng.

### SecurityContext không được truyền sang thread khác

`SecurityContextHolder` thường gắn với thread. Dùng cơ chế propagation được hỗ trợ hoặc truyền actor ID tường minh; không giả định executor tự mang context.

### Dùng LocalDateTime mà không quy định timezone

Timestamp không có timezone dễ gây nhầm khi nhiều service chạy ở các múi giờ khác nhau. Ưu tiên `Instant` cho thời điểm audit.

### Nghĩ rằng update script tự chạy auditing callback

Script update thay đổi document trực tiếp ở Elasticsearch. Hãy truyền `lastModifiedBy` và `lastModifiedDate` qua script params nếu cần audit metadata cho đường ghi đó.

### Nghĩ rằng bốn field audit là lịch sử bất biến

`@LastModifiedBy` chỉ giữ actor gần nhất. Muốn lưu mọi lần thay đổi, cần audit event hoặc change log riêng.

### Không kiểm thử entity có ID gán sẵn

Entity có deterministic ID có thể ảnh hưởng new-state detection. Kiểm thử Created fields trên lần insert thực tế và cân nhắc version metadata nếu phù hợp.

## 20. Quy trình triển khai auditing

Khi đưa auditing vào một ứng dụng Spring Data Elasticsearch:

1. Chọn định dạng actor ID ổn định, ví dụ user ID hoặc service ID.
2. Quy định policy khi không có authentication.
3. Tạo bean `AuditorAware<T>` lấy actor từ security/actor context.
4. Tạo bean `DateTimeProvider` dùng `Clock` theo UTC.
5. Bật `@EnableElasticsearchAuditing` với đúng bean references.
6. Đánh dấu entity bằng `@CreatedBy`, `@LastModifiedBy`, `@CreatedDate` và `@LastModifiedDate`.
7. Chọn kiểu ngày giờ và mapping phù hợp.
8. Xác định `modifyOnCreate` theo ý nghĩa field.
9. Kiểm tra callback trên Repository và `ElasticsearchOperations.save(...)`.
10. Kiểm tra các đường update, script và bulk có bypass callback không.
11. Truyền actor context an toàn qua async/job/message processing.
12. Kiểm thử create, update, empty auditor, system actor và fixed clock.
13. Nếu cần lịch sử đầy đủ, thiết kế audit event riêng.
14. Theo dõi document thiếu metadata để phát hiện đường ghi bypass auditing.

## Tài liệu tham khảo

- [Spring Data Elasticsearch — Auditing](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/auditing.html)
- [Spring Data Elasticsearch — EnableElasticsearchAuditing API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/config/EnableElasticsearchAuditing.html)
- [Spring Data Commons — Auditing](https://docs.spring.io/spring-data/commons/reference/auditing.html)
- [Spring Data Commons — AuditorAware API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/AuditorAware.html)
- [Spring Data Commons — DateTimeProvider API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/auditing/DateTimeProvider.html)
- [Spring Security — SecurityContextHolder](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)

## Kết luận

`AuditorAware<T>` cung cấp danh tính actor cho các field `@CreatedBy` và `@LastModifiedBy`; `DateTimeProvider` cung cấp thời điểm cho `@CreatedDate` và `@LastModifiedDate`. Bật cơ chế bằng `@EnableElasticsearchAuditing`, lấy user từ security context đã xác thực và dùng `Clock` để kiểm soát thời gian, đặc biệt trong test. Với job nền, message consumer, script update và bulk path, cần truyền actor hoặc điền metadata theo policy rõ ràng vì không phải mọi đường ghi đều đi qua entity callback. Bốn field auditing mô tả người tạo và người sửa gần nhất; nếu cần lịch sử thay đổi đầy đủ, hãy lưu audit event riêng.
