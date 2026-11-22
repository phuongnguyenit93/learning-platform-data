# Bật auditing phản ứng bằng `@EnableR2dbcAuditing`

Spring Data Relational R2DBC cung cấp auditing để tự động ghi nhận ai tạo một entity, ai sửa entity và thời điểm tạo/sửa. Trong ứng dụng reactive, auditing được bật bằng `@EnableR2dbcAuditing`. Cấu hình này đăng ký infrastructure cần thiết để Spring Data áp dụng metadata auditing trong quá trình persistence của entity.

Auditing thường dùng bốn annotation trên entity:

- `@CreatedBy`: người hoặc principal tạo bản ghi.
- `@CreatedDate`: thời điểm tạo bản ghi.
- `@LastModifiedBy`: người hoặc principal sửa bản ghi gần nhất.
- `@LastModifiedDate`: thời điểm sửa bản ghi gần nhất.

Điểm khác biệt quan trọng trong ứng dụng R2DBC là thông tin auditor có thể phụ thuộc vào request/security context reactive. Vì vậy, nguồn cung cấp người thực hiện nên triển khai `ReactiveAuditorAware<T>` và trả về `Mono<T>`, thay vì dựa vào `ThreadLocal` như một số cách làm trong ứng dụng đồng bộ.

Auditing được áp dụng trong đường lưu entity do Spring Data quản lý. Một câu SQL ghi trực tiếp qua `DatabaseClient` hoặc `@Modifying @Query` không tự kích hoạt callback auditing cho từng hàng; nếu dùng bulk SQL, ứng dụng phải cập nhật cột audit tường minh trong câu lệnh.

## 1. Auditing giải quyết vấn đề gì?

Trong nhiều hệ thống, mỗi bản ghi cần lưu lại thông tin nguồn gốc và lịch sử sửa đổi. Ví dụ bảng `customer` có thể cần:

| Cột | Ý nghĩa |
| --- | --- |
| `created_by` | Tài khoản tạo customer |
| `created_at` | Thời điểm tạo customer |
| `last_modified_by` | Tài khoản sửa gần nhất |
| `last_modified_at` | Thời điểm sửa gần nhất |

Nếu mỗi service tự gán các field này, code có thể lặp lại và dễ bỏ sót. Spring Data auditing đưa logic đó vào lifecycle persistence của entity. Khi entity được lưu theo đường mapping phù hợp, framework xác định entity mới hay đã tồn tại và cập nhật các trường audit theo cấu hình.

Auditing hữu ích cho:

- Truy vết người tạo và người sửa dữ liệu.
- Hiển thị thời điểm tạo/cập nhật trong API và giao diện.
- Hỗ trợ điều tra lỗi và lịch sử thay đổi ở mức metadata.
- Giữ quy tắc audit nhất quán giữa nhiều repository/service.
- Chuẩn hóa thời gian và nguồn người dùng trong các thao tác entity.

Auditing không tự tạo lịch sử phiên bản đầy đủ của từng thay đổi. Bốn field audit chỉ lưu thông tin tạo và lần sửa gần nhất. Nếu cần audit trail bất biến, lưu giá trị cũ/mới, lý do thay đổi hoặc sự kiện nghiệp vụ, cần một bảng lịch sử, event log hoặc giải pháp auditing chuyên biệt.

## 2. Bật auditing bằng `@EnableR2dbcAuditing`

Đặt annotation trên một lớp cấu hình Spring:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.r2dbc.config.EnableR2dbcAuditing;

@Configuration
@EnableR2dbcAuditing
public class R2dbcAuditingConfiguration {
}
```

Khi application context khởi động, annotation đăng ký các thành phần auditing cho Spring Data R2DBC. Các entity có annotation `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy` hoặc `@LastModifiedBy` sẽ được xử lý trong lifecycle persistence phù hợp.

Nếu cần chỉ định bean cung cấp auditor hoặc thời gian, có thể tham chiếu tên bean qua thuộc tính của annotation:

```java
@Configuration
@EnableR2dbcAuditing(
        auditorAwareRef = "auditorAware",
        dateTimeProviderRef = "dateTimeProvider"
)
public class R2dbcAuditingConfiguration {
}
```

`auditorAwareRef` chỉ bean cung cấp auditor; `dateTimeProviderRef` chỉ bean cung cấp thời gian. Nếu ứng dụng chỉ cần timestamp và không cần lưu người thực hiện, có thể bật auditing mà không khai báo `ReactiveAuditorAware` tùy chỉnh. Nếu có nhiều bean cùng kiểu, đặt tên và tham chiếu rõ ràng để tránh Spring chọn nhầm.

### Các thuộc tính cấu hình thường dùng

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `auditorAwareRef` | Tên bean cung cấp auditor hiện tại |
| `dateTimeProviderRef` | Tên bean cung cấp thời gian hiện tại |
| `modifyOnCreate` | Có cập nhật thông tin sửa đổi trong lần tạo mới hay không |
| `setDates` | Có tự đặt các field ngày/giờ auditing hay không |
| `mappingContextRef` | Chỉ định mapping context nếu ứng dụng cần cấu hình riêng |

`modifyOnCreate` thường mặc định là `true`, nghĩa là các field sửa đổi có thể được đặt ngay cả khi entity được tạo mới. Nếu muốn chỉ có `createdAt`/`createdBy` ở lần insert và chỉ đặt `lastModifiedAt`/`lastModifiedBy` từ lần update tiếp theo, có thể cấu hình `modifyOnCreate = false`.

`setDates = false` tắt việc đặt field ngày/giờ, trong khi auditor metadata có thể vẫn được xử lý theo cấu hình. Hãy xác định rõ yêu cầu và kiểm tra thuộc tính của phiên bản Spring Data đang sử dụng.

## 3. Khai báo các trường auditing trên entity

Ví dụ entity `Customer`:

```java
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public class Customer {

    @Id
    private Long id;

    private String name;

    @CreatedBy
    @Column("created_by")
    private String createdBy;

    @CreatedDate
    @Column("created_at")
    private Instant createdAt;

    @LastModifiedBy
    @Column("last_modified_by")
    private String lastModifiedBy;

    @LastModifiedDate
    @Column("last_modified_at")
    private Instant lastModifiedAt;

    // Constructor, getter và setter.
}
```

Annotation auditing thuộc `org.springframework.data.annotation`. `@Table`, `@Column` thuộc mapping của Spring Data Relational. Tên property Java có thể khác tên cột SQL; dùng `@Column` để ánh xạ rõ khi schema sử dụng snake_case hoặc tên cột khác.

### Schema database

Các cột tương ứng cần tồn tại trong bảng:

```sql
CREATE TABLE customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    created_by VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE,
    last_modified_by VARCHAR(100),
    last_modified_at TIMESTAMP WITH TIME ZONE
);
```

Kiểu SQL cần phù hợp với kiểu Java và driver. Ví dụ `Instant` thường được dùng cho thời điểm tuyệt đối; kiểu SQL và codec cụ thể phụ thuộc database. Với PostgreSQL, có thể dùng `TIMESTAMPTZ`; với database khác, hãy chọn kiểu timestamp có semantics tương ứng.

Auditing không tự tạo hoặc tự migrate cột. Schema migration vẫn cần khai báo các field tương ứng trước khi entity được lưu.

## 4. `ReactiveAuditorAware<T>` cung cấp ai đang thực hiện thao tác

Để tự động điền `@CreatedBy` và `@LastModifiedBy`, Spring Data R2DBC có thể sử dụng bean triển khai `ReactiveAuditorAware<T>`. Interface này trả về `Mono<T>` để lấy auditor theo reactive flow.

Ví dụ đơn giản dùng một auditor cố định cho môi trường thử nghiệm:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.data.domain.ReactiveAuditorAware;

@Bean
ReactiveAuditorAware<String> auditorAware() {
    return () -> Mono.just("system");
}
```

Khi entity được lưu, auditing infrastructure subscribe publisher auditor và dùng giá trị phát ra để gán field có `@CreatedBy` hoặc `@LastModifiedBy`. Kiểu generic `String` phải tương thích với kiểu field audit trên entity.

Trong ứng dụng thật, auditor thường là user ID, username, service account hoặc principal ID. Nên chọn một định danh ổn định thay vì lưu object Authentication phức tạp vào entity.

### Không có auditor hiện tại

Nếu request chạy trong một ngữ cảnh không có người dùng, `ReactiveAuditorAware` có thể trả `Mono.empty()`:

```java
@Bean
ReactiveAuditorAware<String> auditorAware() {
    return () -> resolveCurrentUser()
            .map(UserIdentity::id);
}
```

Nếu `resolveCurrentUser()` không có auditor, publisher hoàn tất empty. Khi đó Spring Data không có giá trị để gán cho field auditor; field có thể giữ giá trị hiện có hoặc null tùy entity và trạng thái persistence. Hãy quyết định chính sách rõ ràng cho job nền, scheduled task, import và request anonymous.

Không nên phát một chuỗi rỗng hoặc giá trị giả chỉ để tránh null nếu dữ liệu audit cần phản ánh đúng nguồn thực hiện. Có thể dùng service account như `batch-import` hoặc `system` khi đó là một actor hợp lệ của nghiệp vụ.

## 5. Lấy auditor từ Spring Security reactive context

Trong ứng dụng Spring Security WebFlux, thông tin Authentication được lưu trong reactive security context. Có thể triển khai `ReactiveAuditorAware<String>` bằng `ReactiveSecurityContextHolder`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.data.domain.ReactiveAuditorAware;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;

@Bean
ReactiveAuditorAware<String> auditorAware() {
    return () -> ReactiveSecurityContextHolder.getContext()
            .map(securityContext -> securityContext.getAuthentication())
            .filter(Authentication::isAuthenticated)
            .map(Authentication::getName);
}
```

Đoạn code này lấy Authentication từ Reactor Context, kiểm tra đã authenticated và dùng `getName()` làm auditor. Trong ứng dụng có anonymous authentication, cần quyết định có coi anonymous principal là actor hợp lệ hay không; có thể lọc thêm theo loại Authentication hoặc principal cụ thể.

Nếu entity lưu user ID dạng UUID hoặc Long, map principal sang ID tương ứng:

```java
@Bean
ReactiveAuditorAware<UUID> auditorAware() {
    return () -> ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication())
            .filter(Authentication::isAuthenticated)
            .map(Authentication::getPrincipal)
            .cast(ApplicationPrincipal.class)
            .map(ApplicationPrincipal::userId);
}
```

`ApplicationPrincipal` là kiểu principal của ứng dụng. Nếu Authentication có principal không đúng kiểu, `cast` có thể làm publisher phát lỗi. Có thể dùng `ofType(ApplicationPrincipal.class)` hoặc kiểm tra kiểu trước khi chuyển đổi để xử lý nhiều loại principal an toàn hơn.

### Vì sao không dùng `SecurityContextHolder` đồng bộ?

Trong WebFlux, không nên mặc định lấy người dùng từ `SecurityContextHolder.getContext()` dựa trên `ThreadLocal`. Reactive pipeline có thể chuyển thread; context bảo mật được truyền theo Reactor Context. `ReactiveSecurityContextHolder` là API phù hợp để truy cập security context trong reactive flow.

Nếu `ReactiveAuditorAware` trả về `Mono.empty()` trong khi request đã authenticated, hãy kiểm tra:

- Security filter chain có đưa security context vào reactive context không.
- Repository save có chạy trong cùng reactive pipeline với request không.
- Có đoạn code tự gọi `subscribe()` hoặc chuyển sang callback executor ngoài Reactor không.
- Có tạo subscription mới làm mất context propagation không.
- Principal có đúng kiểu và trạng thái authenticated như mong đợi không.

## 6. Cấu hình `DateTimeProvider` và `Clock`

Nếu không khai báo provider riêng, auditing sử dụng nguồn thời gian mặc định của Spring Data. Ứng dụng có thể cung cấp `DateTimeProvider` để kiểm soát thời gian, timezone và kiểm thử.

Ví dụ dùng `Clock`:

```java
import java.time.Clock;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.data.auditing.DateTimeProvider;

@Bean
Clock auditingClock() {
    return Clock.systemUTC();
}

@Bean
DateTimeProvider dateTimeProvider(Clock auditingClock) {
    return () -> Optional.of(auditingClock.instant());
}
```

`DateTimeProvider` trả `Optional<TemporalAccessor>`. `Instant` triển khai `TemporalAccessor`, vì vậy có thể dùng làm nguồn thời gian. `Clock.systemUTC()` giúp quy ước thời gian nhất quán và tránh phụ thuộc timezone mặc định của máy chạy ứng dụng.

Liên kết bean với annotation:

```java
@Configuration
@EnableR2dbcAuditing(
        auditorAwareRef = "auditorAware",
        dateTimeProviderRef = "dateTimeProvider"
)
public class R2dbcAuditingConfiguration {
}
```

Nếu không cần auditor, có thể bỏ `auditorAwareRef`; nếu không cần thời gian tùy chỉnh, có thể bỏ `dateTimeProviderRef`.

### Dùng thời gian cố định trong test

Có thể thay bean `Clock` bằng `Clock.fixed(...)` trong integration test:

```java
Clock fixedClock = Clock.fixed(
        Instant.parse("2026-01-15T10:00:00Z"),
        ZoneOffset.UTC
);
```

Khi đó, `@CreatedDate` và `@LastModifiedDate` được gán theo mốc đã biết, giúp assertion không phụ thuộc thời gian thực thi test. Khi kiểm tra lần update, thay clock sang một mốc sau hoặc dùng clock có thể điều khiển để xác nhận timestamp thay đổi đúng.

## 7. `@CreatedDate` và `@LastModifiedDate` khác nhau thế nào?

Hai annotation này biểu diễn hai mốc thời gian khác nhau:

| Annotation | Khi tạo mới | Khi cập nhật entity |
| --- | --- | --- |
| `@CreatedDate` | Ghi thời điểm tạo | Giữ nguyên giá trị tạo ban đầu |
| `@LastModifiedDate` | Được đặt khi `modifyOnCreate` bật | Cập nhật thời điểm sửa |

Ví dụ:

1. 10:00: customer được insert; `createdAt = 10:00`.
2. 10:30: customer được update; `createdAt` vẫn 10:00, `lastModifiedAt = 10:30`.
3. 11:15: customer được update lần nữa; `createdAt` vẫn 10:00, `lastModifiedAt = 11:15`.

Không nên dùng `@LastModifiedDate` thay cho `@CreatedDate` nếu API cần giữ thời điểm tạo ban đầu. Khi tạo mới, giá trị `lastModifiedAt` có phụ thuộc `modifyOnCreate`; nếu tắt thuộc tính này, field sửa đổi có thể chưa được đặt ở lần insert.

## 8. `@CreatedBy` và `@LastModifiedBy`

Hai annotation auditor có semantics tương tự timestamp:

| Annotation | Khi tạo mới | Khi cập nhật entity |
| --- | --- | --- |
| `@CreatedBy` | Ghi actor tạo | Giữ actor tạo ban đầu |
| `@LastModifiedBy` | Được đặt khi `modifyOnCreate` bật | Cập nhật actor sửa gần nhất |

Ví dụ một customer được tạo bởi `alice`, sau đó được sửa bởi `bob`:

```text
created_by       = alice
last_modified_by = bob
```

`@CreatedBy` không nên bị thay đổi thành `bob` chỉ vì entity được update. Field này giữ nguồn tạo ban đầu. `@LastModifiedBy` phản ánh actor của lần sửa gần nhất.

Nếu không có auditor trong context, các field auditor không tự có một giá trị mặc định đáng tin cậy. Chính sách có thể là cho phép null, dùng actor hệ thống cho job nền, hoặc yêu cầu authentication trước khi thao tác.

## 9. `modifyOnCreate` và `setDates`

Có thể điều chỉnh hành vi tạo metadata:

```java
@Configuration
@EnableR2dbcAuditing(
        auditorAwareRef = "auditorAware",
        dateTimeProviderRef = "dateTimeProvider",
        modifyOnCreate = false,
        setDates = true
)
public class R2dbcAuditingConfiguration {
}
```

Với `modifyOnCreate = false`, metadata “last modified” không được đặt chỉ vì entity đang được tạo mới. `createdBy` và `createdDate` vẫn được dùng cho trạng thái tạo mới nếu có provider tương ứng. Khi entity được update, các field sửa đổi mới được cập nhật.

Với `setDates = false`, auditing không tự đặt field ngày/giờ. Điều này có thể phù hợp khi thời gian do database trigger hoặc một hệ thống khác quản lý. Khi tắt, đừng mong `@CreatedDate`/`@LastModifiedDate` được tự điền chỉ từ annotation trên field.

Hãy kiểm tra cấu hình trong integration test thay vì suy luận chỉ từ tên thuộc tính. Một số khác biệt có thể phụ thuộc phiên bản Spring Data và cách entity được lưu.

## 10. Auditing chạy trong entity lifecycle

Auditing của Spring Data R2DBC được tích hợp vào quá trình persistence entity. Khi entity đi qua repository hoặc entity-oriented operation phù hợp, callback auditing có thể xác định trạng thái mới/cũ và gán metadata trước khi entity được ghi.

Ví dụ:

```java
return customerRepository.findById(id)
        .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)))
        .flatMap(customer -> {
            customer.setName(newName);
            return customerRepository.save(customer);
        });
```

Khi `save` được thực thi, auditing callback có thể cập nhật `lastModifiedBy` và `lastModifiedAt` dựa trên auditor/time provider. Setter `setName` tự nó không kích hoạt auditing và cũng không ghi dữ liệu xuống database.

### Các thao tác entity thường đi qua auditing

Những thao tác entity-oriented của Spring Data như `repository.save(entity)` hoặc `R2dbcEntityTemplate` insert/update entity có thể kích hoạt lifecycle callbacks. Hành vi chính xác còn phụ thuộc API và phiên bản, vì vậy hãy kiểm thử đường ghi mà ứng dụng thực sự dùng.

### Direct SQL không tự chạy auditing callback

Ví dụ:

```java
databaseClient.sql("""
        UPDATE customer
        SET name = :name
        WHERE id = :id
        """)
    .bind("name", newName)
    .bind("id", id)
    .fetch()
    .rowsUpdated();
```

Lệnh này không tải entity và không đi qua callback auditing cho entity. `lastModifiedAt` và `lastModifiedBy` sẽ không tự được cập nhật. Nếu direct SQL là lựa chọn có chủ đích, hãy đưa các cột audit vào câu lệnh:

```java
databaseClient.sql("""
        UPDATE customer
        SET name = :name,
            last_modified_at = :modifiedAt,
            last_modified_by = :modifiedBy
        WHERE id = :id
        """)
    .bind("name", newName)
    .bind("modifiedAt", clock.instant())
    .bind("modifiedBy", actorId)
    .bind("id", id)
    .fetch()
    .rowsUpdated();
```

Tương tự, bulk update qua `@Modifying @Query`, `DatabaseClient` hoặc fluent update không tự gọi auditing callback cho từng hàng. Nếu dùng bulk SQL, ứng dụng cần tự cập nhật metadata audit hoặc dùng trigger/database policy đã được thiết kế rõ.

## 11. Entity mới/cũ ảnh hưởng tới auditing

Auditing cần biết entity đang được tạo mới hay sửa. Spring Data Relational xác định trạng thái entity theo quy tắc newness detection: `Persistable.isNew()` nếu entity triển khai `Persistable`; nếu không, `@Version` được ưu tiên; nếu không có version, `@Id` được dùng.

Nếu trạng thái newness bị xác định sai, cả lựa chọn INSERT/UPDATE lẫn metadata created/modified có thể không như mong đợi.

Ví dụ entity dùng assigned ID:

```java
@Table("customer")
public class Customer implements Persistable<UUID> {

    @Id
    private UUID id;

    @Transient
    private boolean newEntity;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant lastModifiedAt;

    @Override
    public UUID getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return newEntity;
    }
}
```

Đây chỉ là ví dụ khái niệm; constructor/callback cần đặt `newEntity` đúng và chuyển trạng thái sau khi insert. `@Transient` của Spring Data Relational loại property khỏi mapping persistence. Không dùng `Persistable` nếu không cần custom newness logic.

Với entity có ID được gán trước khi insert, chỉ nhìn ID có thể khiến framework coi entity là cũ. Nếu entity mới nhưng `isNew()` trả false, thao tác có thể đi vào update path và auditing không xử lý như lần tạo mới. Hãy kiểm tra newness detection khi audit metadata bị thiếu hoặc `createdAt` bị thay đổi ngoài dự kiến.

## 12. Auditing với entity bất biến

Entity bất biến không cho phép sửa field trực tiếp. Spring Data có thể tạo instance mới thông qua constructor/persistent creator hoặc property accessor khi callback bổ sung audit metadata. Vì vậy, các field audit cần có mặt trong constructor hoặc cơ chế wither/property mapping mà Spring Data có thể sử dụng.

Ví dụ record:

```java
@Table("customer")
public record Customer(
        @Id Long id,
        String name,
        @CreatedBy String createdBy,
        @CreatedDate Instant createdAt,
        @LastModifiedBy String lastModifiedBy,
        @LastModifiedDate Instant lastModifiedAt
) {
}
```

Record có constructor canonical chứa các field audit. Khi Spring Data tạo instance sau callback, các giá trị audit có thể được truyền qua constructor theo mapping metadata. Hãy dùng entity được phát ra từ `save` vì nó phản ánh instance sau persistence/callback và có thể chứa ID/version mới.

Với class immutable tự viết, bảo đảm có constructor phù hợp và tên/kiểu property được Spring Data nhận diện. Nếu callback không thể cập nhật field do thiết kế entity, hãy kiểm tra constructor mapping, property accessor và cách triển khai wither.

## 13. Auditing trong tác vụ nền và scheduled job

Không phải mọi thao tác persistence đều xuất phát từ HTTP request có người dùng đăng nhập. Các tác vụ nền có thể chạy trong scheduler, consumer hoặc batch import mà không có reactive security context.

Có thể cung cấp actor hệ thống trong những luồng đó. Một cách là đặt giá trị actor vào Reactor Context của pipeline:

```java
return importCustomers()
        .contextWrite(context -> context.put("auditActor", "customer-import-job"));
```

Sau đó `ReactiveAuditorAware` đọc context:

```java
@Bean
ReactiveAuditorAware<String> auditorAware() {
    return () -> Mono.deferContextual(context ->
            Mono.justOrEmpty(context.<String>getOrEmpty("auditActor"))
    );
}
```

Trong ứng dụng thật, có thể ưu tiên user principal khi có security context và dùng actor job khi pipeline có key `auditActor`. Cần định nghĩa thứ tự ưu tiên rõ ràng, tránh vô tình gán `system` cho request có người dùng thật.

Nếu không có actor, có thể trả `Mono.empty()` và cho phép field auditor null; hoặc yêu cầu mọi thao tác ghi phải có actor. Quyết định này nên được phản ánh trong schema (`NOT NULL` hay nullable) và kiểm thử.

Không dựa vào `ThreadLocal` để truyền actor qua reactive pipeline. Dùng `ReactiveAuditorAware` và Reactor Context hoặc reactive security context tương ứng.

## 14. Tách auditor theo tenant hoặc nguồn request

Một số hệ thống lưu cả actor và tenant. `ReactiveAuditorAware` chỉ chịu trách nhiệm trả giá trị auditor; tenant metadata có thể được xử lý riêng qua service/domain hoặc callback tùy thiết kế.

Ví dụ nếu cần auditor gồm cả user và tenant:

```java
public record AuditActor(String userId, String tenantId) {
}
```

Entity có thể lưu hai field riêng `created_by` và `created_tenant`, hoặc lưu một định danh actor ổn định. Tránh serialize toàn bộ SecurityContext vào một cột audit.

Nếu `ReactiveAuditorAware` đọc tenant từ Reactor Context, bảo đảm context được đặt ở biên request và không bị mất khi code chuyển sang API callback bên ngoài Reactor. Các thao tác R2DBC phải vẫn nằm trong reactive chain để auditing callback đọc được context.

## 15. Thứ tự callback và phối hợp với callback tùy chỉnh

Spring Data R2DBC có lifecycle callback cho các thời điểm trong quá trình đọc/ghi entity. Auditing được tích hợp như một callback để gán metadata. Ứng dụng cũng có thể khai báo callback tùy chỉnh để chuẩn hóa field, sinh mã hoặc áp dụng quy tắc trước khi lưu.

Ví dụ callback tùy chỉnh:

```java
@Component
public class CustomerNormalizeCallback
        implements BeforeConvertCallback<Customer> {

    @Override
    public Customer onBeforeConvert(Customer customer) {
        customer.setName(customer.getName().trim());
        return customer;
    }
}
```

Đây là callback đồng bộ minh họa cho entity mutable; reactive callback tương ứng có thể dùng nếu cần xử lý bất đồng bộ. Khi phối hợp callback tự viết với auditing, cần chú ý thứ tự thực thi và không ghi đè các field audit sau khi auditing đã đặt chúng. Nếu callback phụ thuộc thứ tự, dùng cơ chế ordering được hỗ trợ trong phiên bản Spring Data thay vì dựa vào thứ tự khởi tạo bean.

Không nên thực hiện truy vấn database blocking trong callback. Callback thuộc reactive persistence path; nếu cần thao tác bất đồng bộ, sử dụng reactive callback API được Spring Data cung cấp cho phiên bản tương ứng.

## 16. Auditing không thay thế lịch sử thay đổi

Các field `created*` và `lastModified*` chỉ cho biết actor/thời điểm đầu tiên và gần nhất. Chúng không giữ lại các lần sửa trung gian.

Ví dụ:

```text
10:00 alice tạo customer, name = "Lan"
10:30 bob đổi name = "Lan Nguyen"
11:15 carol đổi name = "Lan N."
```

Sau lần cuối, entity có thể chỉ còn:

```text
created_by       = alice
created_at       = 10:00
last_modified_by = carol
last_modified_at = 11:15
```

Thông tin `bob` và giá trị tên trước đó không còn trong bốn field này. Nếu cần lưu mọi thay đổi, có thể thiết kế bảng audit history:

```sql
CREATE TABLE customer_audit (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    actor_id VARCHAR(100),
    action VARCHAR(50) NOT NULL,
    changed_at TIMESTAMP WITH TIME ZONE NOT NULL,
    old_value JSONB,
    new_value JSONB
);
```

Bảng này là ví dụ PostgreSQL; kiểu JSON và cấu trúc dữ liệu phụ thuộc database. Ghi lịch sử nên được phối hợp transaction với thay đổi entity nếu yêu cầu không để xảy ra trạng thái một bên đã ghi, một bên chưa ghi. Với thao tác direct SQL/bulk, cần ghi audit history tường minh hoặc dùng trigger/outbox phù hợp.

## 17. Auditing và cập nhật hàng loạt

Khi cập nhật hàng loạt bằng SQL:

```sql
UPDATE customer
SET status = 'INACTIVE'
WHERE last_login < :cutoff;
```

Spring Data không tạo entity cho từng hàng bị tác động và không chạy callback auditing cho từng entity. Nếu cần cập nhật metadata:

```sql
UPDATE customer
SET status = :status,
    last_modified_at = :modifiedAt,
    last_modified_by = :actor
WHERE last_login < :cutoff;
```

Ở đây một timestamp/actor được dùng cho cả batch. Nếu yêu cầu actor hoặc thời điểm khác nhau cho từng hàng, cần một thiết kế SQL hoặc xử lý theo entity phù hợp.

Nếu database trigger tự cập nhật timestamp, cần quyết định field nào do database sở hữu và field nào do Spring Data auditing sở hữu. Tránh để cả callback lẫn trigger ghi cùng một cột theo các clock khác nhau, vì giá trị cuối cùng có thể phụ thuộc thứ tự thực thi.

## 18. Cấu hình đầy đủ minh họa

Ví dụ tổng hợp cấu hình auditor từ reactive security context và thời gian UTC:

```java
@Configuration
@EnableR2dbcAuditing(
        auditorAwareRef = "auditorAware",
        dateTimeProviderRef = "dateTimeProvider",
        modifyOnCreate = true,
        setDates = true
)
public class R2dbcAuditingConfiguration {

    @Bean
    ReactiveAuditorAware<String> auditorAware() {
        return () -> ReactiveSecurityContextHolder.getContext()
                .map(context -> context.getAuthentication())
                .filter(Authentication::isAuthenticated)
                .map(Authentication::getName);
    }

    @Bean
    Clock auditingClock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider dateTimeProvider(Clock auditingClock) {
        return () -> Optional.of(auditingClock.instant());
    }
}
```

Imports chính:

```java
import java.time.Clock;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.domain.ReactiveAuditorAware;
import org.springframework.data.r2dbc.config.EnableR2dbcAuditing;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
```

Đoạn cấu hình giả định ứng dụng dùng Spring Security WebFlux và có principal phù hợp với `Authentication.getName()`. Nếu không dùng Spring Security, thay `ReactiveAuditorAware` bằng nguồn actor của ứng dụng. Nếu không cần auditor, có thể bỏ bean và thuộc tính `auditorAwareRef`.

## 19. Kiểm thử auditing

Nên kiểm thử bằng repository R2DBC và database/driver thật, vì mục tiêu là xác nhận callback được tích hợp trong persistence path thực tế.

### Kiểm thử timestamp khi insert

Với `Clock` cố định:

```java
Instant expected = Instant.parse("2026-01-15T10:00:00Z");

StepVerifier.create(customerRepository.save(new Customer("Lan")))
        .assertNext(saved -> {
            assertThat(saved.getCreatedAt()).isEqualTo(expected);
            assertThat(saved.getLastModifiedAt()).isEqualTo(expected);
        })
        .verifyComplete();
```

Assertion `lastModifiedAt` khi insert giả định `modifyOnCreate = true`. Nếu cấu hình false, không nên mong field này được đặt trong lần tạo mới.

### Kiểm thử actor

Với test context có auditor `test-user`, xác nhận:

```java
assertThat(saved.getCreatedBy()).isEqualTo("test-user");
assertThat(saved.getLastModifiedBy()).isEqualTo("test-user");
```

Nếu dùng `ReactiveSecurityContextHolder`, có thể tạo security context trong test bằng cơ chế test support của Spring Security hoặc đặt context phù hợp trên publisher. Đừng chỉ mock `ReactiveAuditorAware` nếu mục tiêu là kiểm tra việc context request thực sự được truyền tới callback.

### Kiểm thử update giữ nguyên created fields

1. Insert entity với actor `alice` và thời gian `t1`.
2. Thay context actor thành `bob`, clock thành `t2`.
3. Đọc entity, thay đổi một property và gọi `save`.
4. Xác nhận `createdBy = alice`, `createdAt = t1`, `lastModifiedBy = bob`, `lastModifiedAt = t2`.

Test này xác nhận cả nguồn auditor, DateTimeProvider và semantics created/modified.

### Kiểm thử direct SQL không tự kích hoạt auditing

Thực hiện update bằng `DatabaseClient` mà không cập nhật cột audit; đọc lại entity và xác nhận `lastModifiedAt`/`lastModifiedBy` không tự đổi. Sau đó cập nhật SQL để set rõ các cột này và xác nhận kết quả. Test giúp tránh giả định sai rằng annotation auditing có hiệu lực cho mọi lệnh SQL trong ứng dụng.

## 20. Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `createdAt` hoặc `lastModifiedAt` luôn null | Chưa bật `@EnableR2dbcAuditing`, thiếu field annotation hoặc cột chưa được mapping | Kiểm tra configuration, annotation và schema |
| `@CreatedBy` không được điền | Chưa có `ReactiveAuditorAware` hoặc publisher auditor empty | Kiểm tra bean, kiểu field và context |
| Auditor luôn là anonymous | Security filter/context dùng anonymous principal được đánh dấu authenticated | Lọc loại principal hoặc định nghĩa actor policy |
| Auditor có trong request nhưng mất trong repository callback | Subscription tách rời hoặc rời reactive context | Nối publisher; tránh `subscribe()`/callback executor độc lập |
| Lỗi kiểu khi gán auditor | Generic của `ReactiveAuditorAware<T>` không khớp field | Dùng kiểu ID/principal nhất quán |
| `createdAt` thay đổi khi update | Entity bị coi là mới hoặc logic callback/custom code ghi đè field | Kiểm tra `isNew`, `@Version`, `@Id` và callback |
| `lastModifiedAt` không đổi khi insert | `modifyOnCreate = false` | Xác nhận cấu hình và kỳ vọng nghiệp vụ |
| Direct update không cập nhật audit fields | SQL không đi qua entity lifecycle | Ghi cột audit trong SQL hoặc dùng entity save |
| Timestamp lệch timezone | Dùng local time/Clock mặc định hoặc kiểu SQL không phù hợp | Chuẩn hóa UTC và kiểm tra codec/database type |
| Entity immutable không nhận audit values | Constructor/persistent creator không chứa property hoặc mapping không nhận diện | Kiểm tra constructor, property accessor và entity kết quả |
| CreatedBy bị ghi đè khi update | Dùng nhầm field hoặc custom callback ghi đè | Tách rõ created và last-modified metadata |
| Audit column không tồn tại | Auditing không tự tạo schema | Thêm migration cho cột audit |

## 21. Quy trình bật auditing trong ứng dụng

1. Xác định thông tin cần lưu: actor, timestamp hay cả hai.
2. Thêm cột tương ứng vào schema bằng migration.
3. Thêm `@CreatedBy`, `@CreatedDate`, `@LastModifiedBy`, `@LastModifiedDate` vào entity.
4. Bật `@EnableR2dbcAuditing` trong configuration được component scan.
5. Nếu cần actor, khai báo `ReactiveAuditorAware<T>` với kiểu phù hợp.
6. Nếu cần kiểm soát thời gian, khai báo `DateTimeProvider` dựa trên `Clock`.
7. Quyết định `modifyOnCreate` và `setDates` theo semantics mong muốn.
8. Bảo đảm repository/template entity operations đi qua cùng Spring Data infrastructure.
9. Với direct SQL/bulk update, cập nhật audit fields tường minh hoặc dùng cơ chế database đã thiết kế.
10. Kiểm thử insert, update, actor không có, job nền, direct SQL và entity immutable bằng integration test.

## 22. Ghi nhớ

- Bật reactive auditing bằng `@EnableR2dbcAuditing` trong Spring configuration.
- `@CreatedBy`, `@CreatedDate`, `@LastModifiedBy` và `@LastModifiedDate` đánh dấu các field audit trên entity.
- `ReactiveAuditorAware<T>` cung cấp actor dưới dạng `Mono<T>`, phù hợp với reactive security/context.
- Trong WebFlux, lấy principal bằng `ReactiveSecurityContextHolder`; không dựa vào `ThreadLocal`/`SecurityContextHolder` đồng bộ.
- `DateTimeProvider` cung cấp thời gian; dùng `Clock.systemUTC()` để chuẩn hóa và `Clock.fixed()` để kiểm thử.
- `modifyOnCreate` quyết định có đặt metadata sửa đổi ngay khi insert; `setDates` điều khiển việc tự đặt các field ngày/giờ.
- Auditing chạy trong entity lifecycle persistence do Spring Data quản lý; setter đơn thuần không ghi database.
- `DatabaseClient`, `@Modifying @Query` và bulk SQL không tự chạy callback auditing cho từng entity; cần cập nhật cột audit rõ ràng.
- Newness detection (`Persistable`, `@Version`, `@Id`) ảnh hưởng cách phân loại created/modified.
- Với entity immutable, cần bảo đảm constructor/property mapping có thể nhận giá trị audit và dùng entity kết quả từ `save`.
- Auditing chỉ lưu metadata tạo và sửa gần nhất; muốn lịch sử đầy đủ cần audit table/event log/outbox hoặc giải pháp riêng.
- Kiểm thử bằng database/driver thật để xác nhận callback, security context, timestamp, update và direct SQL behavior.

Khi bật auditing phản ứng trong Spring Data R2DBC, hãy cấu hình `@EnableR2dbcAuditing`, cung cấp nguồn thời gian và `ReactiveAuditorAware` khi cần actor, rồi đánh dấu các field trên entity. Các giá trị audit được áp dụng khi entity đi qua lifecycle persistence của Spring Data. Những lệnh SQL trực tiếp vẫn cần tự cập nhật metadata, và nguồn actor trong ứng dụng WebFlux phải được lấy từ reactive context để không phụ thuộc vào thread hiện tại.
