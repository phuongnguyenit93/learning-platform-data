# Kiểm thử thời gian và người thao tác một cách xác định

Trong **Spring Data Relational JDBC**, auditing ghi nhận ai tạo hoặc cập nhật một entity và thời điểm thao tác diễn ra. Các annotation `@CreatedBy`, `@CreatedDate`, `@LastModifiedBy` và `@LastModifiedDate` giúp Spring Data điền metadata khi lưu aggregate.

Auditing mặc định lấy thời gian hiện tại và người thao tác từ các provider trong ApplicationContext. Điều đó phù hợp khi chạy ứng dụng thật, nhưng có thể khiến test phụ thuộc đồng hồ hệ thống, múi giờ, SecurityContext hoặc thứ tự chạy. Một test tốt cần kiểm soát được hai đầu vào:

- **Thời gian:** cung cấp một `DateTimeProvider` trả về thời điểm do test chọn.
- **Người thao tác:** cung cấp một `AuditorAware<T>` trả về actor do test chọn.

Khi hai provider này được điều khiển, test có thể xác nhận chính xác metadata lúc insert và update, kiểm tra `createdAt` không bị ghi đè, xác nhận `lastModifiedAt` thay đổi và kiểm thử trường hợp không có actor. Không cần đợi đồng hồ chạy qua một khoảng thời gian hoặc phụ thuộc tài khoản đang đăng nhập trên máy test.

## 1. Auditing trong Spring Data JDBC hoạt động ở đâu?

Auditing là một phần của lifecycle mapping/persistence do Spring Data quản lý. Khi repository hoặc `JdbcAggregateTemplate` lưu aggregate, auditing infrastructure có thể điền các trường được đánh dấu annotation trước khi dữ liệu được ghi.

| Annotation | Ý nghĩa |
| --- | --- |
| `@CreatedBy` | Người tạo entity |
| `@CreatedDate` | Thời điểm tạo entity |
| `@LastModifiedBy` | Người thao tác trong lần lưu gần nhất |
| `@LastModifiedDate` | Thời điểm lưu gần nhất |

Ví dụ entity:

```java
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.relational.core.mapping.Table;

@Table("audited_document")
public class AuditedDocument {

    @Id
    private Long id;

    private String title;

    @CreatedBy
    private String createdBy;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedBy
    private String lastModifiedBy;

    @LastModifiedDate
    private Instant lastModifiedAt;

    protected AuditedDocument() {
    }

    public AuditedDocument(String title) {
        this.title = title;
    }

    public Long getId() { return id; }
    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }
    public String getCreatedBy() { return createdBy; }
    public Instant getCreatedAt() { return createdAt; }
    public String getLastModifiedBy() { return lastModifiedBy; }
    public Instant getLastModifiedAt() { return lastModifiedAt; }
}
```

`String` được dùng cho actor để ví dụ đơn giản. Nếu ứng dụng dùng kiểu `UserId` hoặc entity người dùng, kiểu generic của `AuditorAware<T>` phải tương thích với kiểu property mang `@CreatedBy` và `@LastModifiedBy`.

`Instant` phù hợp khi muốn lưu một thời điểm tuyệt đối. Spring Data cũng hỗ trợ một số kiểu ngày giờ Java khác; hãy chọn kiểu tương thích với schema và JDBC driver của ứng dụng.

## 2. Bật auditing cho Spring Data JDBC

Thêm `@EnableJdbcAuditing` vào cấu hình:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.EnableJdbcAuditing;

@Configuration
@EnableJdbcAuditing
public class JdbcAuditingConfiguration {
}
```

Nếu entity chỉ có `@CreatedDate` và `@LastModifiedDate`, ứng dụng không bắt buộc phải cung cấp `AuditorAware`. Khi dùng `@CreatedBy` hoặc `@LastModifiedBy`, auditing infrastructure cần một `AuditorAware` để biết actor hiện tại.

Ví dụ cấu hình rõ hai provider:

```java
import java.time.Clock;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.jdbc.repository.config.EnableJdbcAuditing;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

@Configuration
@EnableJdbcAuditing(
        dateTimeProviderRef = "dateTimeProvider",
        auditorAwareRef = "auditorAware"
)
public class JdbcAuditingConfiguration {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider dateTimeProvider(Clock applicationClock) {
        return () -> Optional.of(applicationClock.instant());
    }

    @Bean
    AuditorAware<String> auditorAware() {
        return () -> {
            Authentication authentication =
                    SecurityContextHolder.getContext().getAuthentication();

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

`DateTimeProvider` trả về `Optional<TemporalAccessor>`. Ví dụ dùng `Clock` để có thể thay đồng hồ trong test; production sử dụng `Clock.systemUTC()`. `AuditorAware<String>` lấy tên principal từ Spring Security và trả `Optional.empty()` khi không có người dùng hợp lệ.

Nếu hệ thống không dùng Spring Security, thay implementation `AuditorAware` bằng cơ chế lấy actor của ứng dụng, chẳng hạn user context, request context hoặc một actor hệ thống cho batch job.

### 2.1. Cấu hình modifyOnCreate

`@EnableJdbcAuditing` có thuộc tính `modifyOnCreate`. Giá trị mặc định là `true`, nghĩa là entity được xem là đã modified ngay lúc tạo:

- `@CreatedDate` và `@CreatedBy` được thiết lập lúc insert.
- `@LastModifiedDate` và `@LastModifiedBy` cũng được thiết lập lúc insert nếu `modifyOnCreate = true`.

Nếu muốn các trường modified chỉ có giá trị sau lần cập nhật đầu tiên, cấu hình:

```java
@EnableJdbcAuditing(
        dateTimeProviderRef = "dateTimeProvider",
        auditorAwareRef = "auditorAware",
        modifyOnCreate = false
)
```

Test phải phản ánh chính sách này. Không nên viết assertion cho `lastModifiedAt` lúc insert mà quên rằng dự án có thể chủ động tắt `modifyOnCreate`.

## 3. Vì sao test không nên dùng đồng hồ hệ thống?

Một test kiểu:

```java
AuditedDocument saved = repository.save(new AuditedDocument("draft"));

assertThat(saved.getCreatedAt()).isCloseTo(
        Instant.now(),
        within(1, ChronoUnit.SECONDS)
);
```

có thể qua ở máy này nhưng thất bại ở máy khác do đồng hồ hệ thống lệch hoặc bị điều chỉnh, test chạy chậm trên CI, độ chính xác timestamp của database khác độ chính xác `Instant`, test song song làm thứ tự khó dự đoán hoặc múi giờ JVM/database không giống nhau.

Không dùng `Thread.sleep()` để chờ `lastModifiedAt` khác `createdAt`. Sleep vừa làm test chậm vừa không bảo đảm timestamp mới khác nhau nếu database làm tròn hoặc truncate độ chính xác.

Thay vào đó, truyền một thời điểm cố định cho `DateTimeProvider`. Test có thể đặt `t0` khi insert, sau đó đổi thành `t1` trước update. Kết quả hoàn toàn xác định.

## 4. Tạo DateTimeProvider và AuditorAware có thể điều khiển trong test

Một test context nhỏ có thể triển khai cả hai interface. Nó giữ thời điểm và actor trong `AtomicReference`, cho phép test đổi giá trị giữa các lần lưu:

```java
import java.time.Instant;
import java.time.temporal.TemporalAccessor;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.domain.AuditorAware;

public class TestAuditContext
        implements DateTimeProvider, AuditorAware<String> {

    private final AtomicReference<Instant> now =
            new AtomicReference<>();

    private final AtomicReference<String> actor =
            new AtomicReference<>();

    public void set(Instant instant, String username) {
        now.set(instant);
        actor.set(username);
    }

    @Override
    public Optional<TemporalAccessor> getNow() {
        return Optional.ofNullable(now.get());
    }

    @Override
    public Optional<String> getCurrentAuditor() {
        return Optional.ofNullable(actor.get());
    }
}
```

Hai interface được triển khai bởi cùng một class để test có một nơi điều khiển cả thời gian và actor. `AtomicReference` giúp các giá trị được đọc/ghi an toàn giữa các thread, nhưng nếu test context dùng chung cho nhiều test chạy song song, mỗi test vẫn cần context riêng hoặc cơ chế cô lập phù hợp.

Đăng ký context này trong test configuration:

```java
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.data.jdbc.repository.config.EnableJdbcAuditing;

@TestConfiguration
@EnableJdbcAuditing(
        dateTimeProviderRef = "testAuditContext",
        auditorAwareRef = "testAuditContext"
)
public class AuditingTestConfiguration {

    @Bean
    TestAuditContext testAuditContext() {
        return new TestAuditContext();
    }
}
```

Spring Data sẽ dùng bean `testAuditContext` cho cả hai vai trò. Test có thể đặt giá trị mong muốn trước mỗi thao tác repository.

Nếu test context đã nạp cấu hình production có `@EnableJdbcAuditing`, hãy bảo đảm chỉ có một cấu hình auditing phù hợp trong context. Với test slice, import test configuration tường minh và kiểm tra các cấu hình được nạp để tránh đăng ký auditing infrastructure trùng lặp.

## 5. Kiểm thử insert và update với thời gian, actor cố định

Repository:

```java
import org.springframework.data.repository.CrudRepository;

public interface AuditedDocumentRepository
        extends CrudRepository<AuditedDocument, Long> {
}
```

Schema PostgreSQL minh họa:

```sql
CREATE TABLE audited_document (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    created_by VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE,
    last_modified_by VARCHAR(100),
    last_modified_at TIMESTAMP WITH TIME ZONE
);
```

Test:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.jdbc.DataJdbcTest;
import org.springframework.context.annotation.Import;

@DataJdbcTest
@Import(AuditingTestConfiguration.class)
class AuditedDocumentRepositoryTest {

    private static final Instant T0 =
            Instant.parse("2026-01-10T10:00:00Z");

    private static final Instant T1 =
            Instant.parse("2026-01-10T10:05:00Z");

    @Autowired
    AuditedDocumentRepository repository;

    @Autowired
    TestAuditContext auditContext;

    @Test
    void keepsCreationMetadataAndUpdatesModificationMetadata() {
        auditContext.set(T0, "alice");

        AuditedDocument created =
                repository.save(new AuditedDocument("Draft"));

        assertThat(created.getId()).isNotNull();
        assertThat(created.getCreatedBy()).isEqualTo("alice");
        assertThat(created.getCreatedAt()).isEqualTo(T0);
        assertThat(created.getLastModifiedBy()).isEqualTo("alice");
        assertThat(created.getLastModifiedAt()).isEqualTo(T0);

        auditContext.set(T1, "bob");
        created.setTitle("Reviewed");
        repository.save(created);

        AuditedDocument reloaded = repository.findById(created.getId())
                .orElseThrow();

        assertThat(reloaded.getTitle()).isEqualTo("Reviewed");
        assertThat(reloaded.getCreatedBy()).isEqualTo("alice");
        assertThat(reloaded.getCreatedAt()).isEqualTo(T0);
        assertThat(reloaded.getLastModifiedBy()).isEqualTo("bob");
        assertThat(reloaded.getLastModifiedAt()).isEqualTo(T1);
    }
}
```

Test chứng minh:

1. Lần insert dùng `T0` và actor `alice`.
2. `createdBy` và `createdAt` lưu thông tin lúc tạo.
3. Lần update dùng `T1` và actor `bob`.
4. Metadata tạo ban đầu được giữ nguyên.
5. Metadata sửa đổi phản ánh lần update mới.

Ở đây `modifyOnCreate` mặc định là `true`, nên `lastModifiedBy` và `lastModifiedAt` cũng có giá trị `alice`/`T0` ngay khi insert. Nếu dự án cấu hình `modifyOnCreate = false`, điều chỉnh hai assertion lúc tạo cho phù hợp; sau lần update, metadata sửa đổi vẫn phải là `bob`/`T1`.

`@DataJdbcTest` thường chạy test trong transaction và rollback sau test. Nếu cần xác minh chính xác kiểu PostgreSQL hoặc driver-specific behavior, cấu hình test datasource dùng cùng loại database với production, chẳng hạn PostgreSQL Testcontainers. Với ví dụ auditing cơ bản, điều quan trọng là auditing callbacks và schema thực tế đều được nạp trong test context.

## 6. Kiểm thử DateTimeProvider bằng Clock cố định

Nếu ứng dụng đã dùng `Clock` trong production configuration, có thể kiểm soát thời gian bằng `Clock.fixed` thay vì tạo class test riêng:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock fixedClock = Clock.fixed(
        Instant.parse("2026-01-10T10:00:00Z"),
        ZoneOffset.UTC
);
```

DateTimeProvider:

```java
DateTimeProvider dateTimeProvider(Clock clock) {
    return () -> Optional.of(clock.instant());
}
```

Trong test, inject một `Clock` fixed vào cấu hình auditing. Để kiểm thử nhiều mốc thời gian, dùng một clock có thể điều chỉnh trong test hoặc tạo context riêng cho từng thao tác. Không thay đổi clock hệ thống của máy chạy test.

Một `Clock` cố định luôn trả cùng thời điểm; vì vậy nó rất phù hợp cho test insert hoặc một thao tác đơn lẻ. Để kiểm tra insert rồi update ở hai thời điểm khác nhau, cần clock có thể thay đổi hoặc `DateTimeProvider` có state như `TestAuditContext`.

## 7. Kiểm thử actor mà không phụ thuộc SecurityContext thật

Nếu production dùng Spring Security, `AuditorAware` thường lấy principal từ `SecurityContextHolder`. Test repository không nhất thiết phải khởi tạo toàn bộ cơ chế đăng nhập chỉ để kiểm tra auditing.

Có thể kiểm thử theo hai lớp:

- **Repository/auditing test:** dùng `TestAuditContext` để cung cấp actor giả lập, ví dụ `alice`, `bob`, `batch-import`.
- **Security integration test:** kiểm tra riêng adapter `AuditorAware` có đọc đúng principal từ `SecurityContext` hay không.

Ví dụ kiểm thử adapter:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Optional;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;

class SecurityAuditorAwareTest {

    private final SecurityAuditorAware auditorAware =
            new SecurityAuditorAware();

    @AfterEach
    void clearSecurityContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void returnsAuthenticatedUsername() {
        var authentication =
                UsernamePasswordAuthenticationToken.authenticated(
                        "alice",
                        "n/a",
                        List.of()
                );

        SecurityContextHolder.getContext()
                .setAuthentication(authentication);

        assertThat(auditorAware.getCurrentAuditor())
                .isEqualTo(Optional.of("alice"));
    }
}
```

`SecurityAuditorAware` là implementation của ứng dụng:

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
            return Optional.empty();
        }

        return Optional.of(authentication.getName());
    }
}
```

Test này xác nhận adapter lấy đúng username và dọn SecurityContext sau mỗi test. Nó không cần gọi database. Repository test phía trên mới kiểm tra auditing metadata được ghi xuống database.

Trong ứng dụng bất đồng bộ, SecurityContext thường gắn với thread. Nếu tác vụ chuyển sang executor hoặc message listener, phải truyền actor context theo cách phù hợp; nếu không, `AuditorAware` có thể trả `Optional.empty()` dù request ban đầu có người dùng.

## 8. Kiểm thử trường hợp không có actor

`AuditorAware<T>` trả `Optional<T>`. Khi không có principal, trả `Optional.empty()` thay vì một chuỗi giả như `unknown` trừ khi đó là quy ước nghiệp vụ có chủ đích.

Các trường `@CreatedBy`/`@LastModifiedBy` có thể không được thiết lập khi không có auditor. Vì vậy schema nên cho phép null nếu ứng dụng thực sự có luồng system job không gắn với người dùng, hoặc provider cần trả một actor hệ thống rõ ràng.

| Tình huống | Actor phù hợp |
| --- | --- |
| Người dùng đăng nhập thao tác | User ID hoặc username ổn định |
| Job định kỳ | `system:scheduler` hoặc service account |
| Import dữ liệu | `system:import` hoặc mã batch |
| Migration | `system:migration` |
| Không xác định actor và schema cho phép | `Optional.empty()` |

Không dùng display name có thể đổi làm khóa auditor nếu ứng dụng cần truy vết lâu dài. ID người dùng ổn định thường phù hợp hơn.

## 9. Độ chính xác timestamp, timezone và so sánh trong test

`Instant` biểu diễn thời điểm tuyệt đối và giúp tránh nhầm lẫn múi giờ địa phương. Tuy nhiên, database có thể lưu timestamp với độ chính xác thấp hơn nanosecond của Java.

Ví dụ PostgreSQL thường lưu `timestamp` với độ chính xác microsecond. Nếu test dùng:

```java
Instant expected = Instant.parse("2026-01-10T10:00:00.123456789Z");
```

giá trị đọc lại có thể đã được làm tròn hoặc truncate theo độ chính xác cột/driver. Để test ổn định:

- Dùng mốc thời gian tròn giây hoặc microsecond.
- Hoặc chuẩn hóa expected theo độ chính xác của database trước khi so sánh.
- Dùng `Instant`/UTC khi cần so sánh thời điểm tuyệt đối.
- Nếu dùng `LocalDateTime`, quy định rõ timezone chuyển đổi giữa JVM, JDBC và database.

Ví dụ chuẩn hóa microsecond:

```java
Instant expected = original.truncatedTo(ChronoUnit.MICROS);
```

Đừng nới tolerance quá lớn để che lỗi timezone hoặc mapping. Mục tiêu là kiểm tra chính xác giá trị đã được chuẩn hóa theo schema, không phải làm assertion luôn qua.

## 10. Kiểm thử modifyOnCreate

Mặc định `modifyOnCreate = true`. Nếu nghiệp vụ muốn trường modified chỉ phản ánh lần cập nhật sau khi tạo, đặt `modifyOnCreate = false` và viết test thể hiện contract:

```java
@EnableJdbcAuditing(
        dateTimeProviderRef = "testAuditContext",
        auditorAwareRef = "testAuditContext",
        modifyOnCreate = false
)
```

Assertion khi insert:

```java
assertThat(saved.getCreatedAt()).isEqualTo(T0);
assertThat(saved.getCreatedBy()).isEqualTo("alice");
assertThat(saved.getLastModifiedAt()).isNull();
assertThat(saved.getLastModifiedBy()).isNull();
```

Sau update với `T1`/`bob`:

```java
assertThat(updated.getCreatedAt()).isEqualTo(T0);
assertThat(updated.getCreatedBy()).isEqualTo("alice");
assertThat(updated.getLastModifiedAt()).isEqualTo(T1);
assertThat(updated.getLastModifiedBy()).isEqualTo("bob");
```

Hai chính sách đều hợp lệ. Điều quan trọng là cấu hình và test cùng phản ánh quy ước mà sản phẩm mong muốn.

## 11. Những đường ghi không tự chạy auditing callbacks

Auditing của Spring Data JDBC gắn với lifecycle persistence do Spring Data quản lý. Nếu ứng dụng ghi bằng `JdbcTemplate`, native SQL, stored procedure hoặc một ứng dụng khác, các callback auditing của Spring Data không tự chạy.

Ví dụ:

```java
jdbcTemplate.update(
        "UPDATE audited_document SET title = ? WHERE id = ?",
        "Changed directly",
        id
);
```

Câu SQL trên không tự gọi `DateTimeProvider` hoặc `AuditorAware`. Nếu custom SQL cần duy trì audit columns, phải cập nhật các cột đó một cách tường minh, hoặc dùng database trigger với một quy ước actor/time rõ ràng.

Khi có cả Spring Data repository và SQL trực tiếp, hãy kiểm tra mọi đường ghi để không tạo ra bản ghi có `lastModifiedAt` hoặc `lastModifiedBy` lỗi thời.

## 12. Delete và audit metadata

Các annotation `@Created...` và `@LastModified...` không tự tạo `@DeletedBy` hay `@DeletedDate`. Xóa một entity bằng repository không đồng nghĩa Spring Data tự lưu người xóa và thời điểm xóa vào một bản ghi audit.

Nếu nghiệp vụ cần truy vết xóa, có thể dùng soft delete với các trường `deletedAt`, `deletedBy`, `deleted`; ghi audit event riêng; dùng outbox/audit table; hoặc dùng database trigger nếu muốn ghi nhận mọi đường xóa ở cấp database.

Soft delete phải được thiết kế cùng điều kiện truy vấn để dữ liệu đã xóa không xuất hiện trong các màn hình thông thường. Với audit event, cần xác định transaction và xử lý lỗi để không ghi event mà thao tác xóa thất bại hoặc ngược lại.

## 13. Test auditing theo từng lớp

| Lớp test | Kiểm tra | Công cụ/đầu vào |
| --- | --- | --- |
| Unit test `AuditorAware` | Principal được ánh xạ thành actor đúng | SecurityContext giả lập |
| Unit test `DateTimeProvider` | Provider trả thời điểm đúng | Clock cố định |
| Repository slice test | Annotation auditing được áp dụng khi insert/update | `@DataJdbcTest`, test provider, database |
| Integration test | Timestamp/actor round-trip đúng với schema và driver production | PostgreSQL/Testcontainers hoặc DB mục tiêu |
| Service test | Command truyền đúng actor/time context và xử lý lỗi | Mock repository hoặc Spring context |

Không cần mock `DateTimeProvider` và `AuditorAware` cùng lúc trong mọi test. Chọn đúng lớp test cho câu hỏi cần trả lời. Test repository nên dùng provider thật nhưng có đầu vào cố định; test adapter security không cần khởi tạo database.

## 14. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `@CreatedDate` luôn null | Chưa bật `@EnableJdbcAuditing` hoặc entity không đi qua Spring Data persistence lifecycle | Kiểm tra cấu hình và gọi repository/template |
| `@CreatedBy` luôn null | Thiếu `AuditorAware`, principal không có hoặc trả `Optional.empty()` | Đăng ký auditor provider và kiểm tra actor context |
| Test phụ thuộc username của developer | Lấy SecurityContext thật trong repository test | Dùng `TestAuditContext` hoặc principal giả lập |
| Timestamp thay đổi giữa các lần chạy | Dùng `Instant.now()`/đồng hồ hệ thống trực tiếp | Inject `DateTimeProvider` hoặc `Clock` cố định |
| `lastModifiedAt` đã có ngay khi insert | `modifyOnCreate` mặc định là true | Giữ behavior hoặc đặt false và cập nhật test |
| `createdAt` bị thay đổi sau update | Mapping/auditing config hoặc custom SQL ghi đè trường creation | Kiểm tra lifecycle callback và mọi đường ghi |
| Assertion timestamp thất bại vài microsecond | Database precision khác nanosecond của Instant | Dùng mốc chính xác theo schema hoặc truncate expected |
| Test song song ghi actor của nhau | Dùng chung mutable test context | Tách context hoặc cô lập test; không chia sẻ state giữa test song song |
| Async job không có auditor | SecurityContext không được truyền sang thread mới | Truyền actor rõ ràng hoặc dùng system auditor |
| SQL trực tiếp không cập nhật audit field | JdbcTemplate không chạy auditing callbacks | Cập nhật cột tường minh hoặc dùng trigger |
| Xóa rồi không tìm thấy thông tin người xóa | Auditing annotations không tự ghi delete metadata | Dùng soft delete hoặc audit event/table riêng |

## 15. Quy trình kiểm thử xác định

Khi viết test cho auditing:

1. Xác định field nào cần theo dõi: thời điểm, actor hay cả hai.
2. Bật `@EnableJdbcAuditing` trong context phù hợp.
3. Chọn kiểu dữ liệu audit tương thích schema, ví dụ `Instant` và `String`/user ID.
4. Cung cấp `DateTimeProvider` cố định hoặc có thể điều khiển.
5. Cung cấp `AuditorAware` giả lập với actor xác định.
6. Đặt `T0`/`alice` trước insert và xác nhận metadata tạo.
7. Đặt `T1`/`bob` trước update và xác nhận metadata tạo được giữ, metadata sửa đổi thay đổi.
8. Kiểm tra `modifyOnCreate` theo cấu hình.
9. Dùng timestamp phù hợp precision database.
10. Nếu production dùng custom SQL hoặc driver-specific behavior, kiểm thử riêng đường ghi đó trên database mục tiêu.

## 16. Bài tập thực hành

**Bài 1 — Bật auditing.** Tạo entity có bốn trường `@CreatedBy`, `@CreatedDate`, `@LastModifiedBy`, `@LastModifiedDate`. Bật `@EnableJdbcAuditing` và xác nhận metadata được ghi khi repository insert.

**Bài 2 — Thời gian cố định.** Viết `DateTimeProvider` trả về `Instant` cố định. Chạy test nhiều lần và xác nhận `createdAt` luôn giống nhau.

**Bài 3 — Actor giả lập.** Viết `AuditorAware<String>` trả actor do test thiết lập. Insert với `alice`, update với `bob`, rồi kiểm tra cả bốn trường audit.

**Bài 4 — modifyOnCreate.** Chạy test với `modifyOnCreate = true` và `false`. So sánh `lastModifiedAt`/`lastModifiedBy` lúc insert và update.

**Bài 5 — Không có principal.** Cho `AuditorAware` trả `Optional.empty()`. Xác nhận schema và ứng dụng xử lý trường auditor null theo đúng chính sách.

**Bài 6 — Độ chính xác thời gian.** Dùng timestamp có nanosecond, lưu xuống database rồi đọc lại. Xác định precision của cột và chuẩn hóa assertion.

**Bài 7 — Security adapter.** Viết unit test cho implementation `AuditorAware` dùng `SecurityContextHolder`, xác nhận anonymous authentication không bị ghi thành actor thật.

**Bài 8 — SQL trực tiếp.** Cập nhật một bản ghi bằng `JdbcTemplate`. Quan sát auditing callback không tự chạy, sau đó bổ sung cách ghi audit metadata tường minh hoặc trigger.

### Tài liệu tham khảo

- [Spring Data Relational — JDBC Auditing](https://docs.spring.io/spring-data/relational/reference/jdbc/auditing.html): bật auditing, `AuditorAware` và metadata cho Spring Data JDBC.
- [Spring Data Commons — Auditing](https://docs.spring.io/spring-data/commons/reference/auditing.html): `@CreatedBy`, `@CreatedDate`, `@LastModifiedBy`, `@LastModifiedDate`, `DateTimeProvider` và `AuditorAware`.
- [EnableJdbcAuditing API](https://docs.spring.io/spring-data/jdbc/docs/current/api/org/springframework/data/jdbc/repository/config/EnableJdbcAuditing.html): `auditorAwareRef`, `dateTimeProviderRef`, `modifyOnCreate` và `setDates`.
