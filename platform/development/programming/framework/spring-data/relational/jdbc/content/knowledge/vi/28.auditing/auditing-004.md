# Cung cấp người thao tác bằng AuditorAware

Trong Spring Data JDBC, auditing giúp ghi nhận ai đã tạo hoặc cập nhật một aggregate. Các annotation **@CreatedBy** và **@LastModifiedBy** đánh dấu property chứa người thao tác; **AuditorAware<T>** cung cấp giá trị actor hiện tại cho auditing infrastructure.

AuditorAware là cầu nối giữa danh tính mà ứng dụng đã xác thực và metadata auditing. Nó không tự xác thực người dùng, không tạo tài khoản và không suy đoán danh tính. Ứng dụng chịu trách nhiệm xác định actor từ Spring Security, service account hoặc context của tác vụ nền.

Bài này trình bày cách cấu hình AuditorAware cho Spring Data JDBC, tích hợp với Spring Security, lựa chọn định danh actor và các giới hạn khi ghi dữ liệu bằng SQL trực tiếp.

## 1. AuditorAware là gì?

AuditorAware<T> thuộc package org.springframework.data.domain. Interface cung cấp một phương thức:

~~~java
public interface AuditorAware<T> {
    Optional<T> getCurrentAuditor();
}
~~~

T là kiểu dữ liệu đại diện cho người thao tác. Ví dụ:

- AuditorAware<String> nếu lưu username hoặc mã người dùng dạng chuỗi.
- AuditorAware<UUID> nếu lưu ID người dùng kiểu UUID.
- AuditorAware<Long> nếu hệ thống dùng ID số nguyên dài.
- AuditorAware<User> nếu mô hình và mapping thực sự lưu một đối tượng User phù hợp.

Phương thức trả về Optional<T> vì không phải mọi thao tác đều có người dùng đã đăng nhập. Một tác vụ chạy theo lịch, migration, batch import hoặc tiến trình hệ thống có thể không có Authentication gắn với request.

Spring Data auditing gọi AuditorAware khi cần điền các trường auditor được đánh dấu. Interface chỉ cung cấp danh tính mà ứng dụng đã xác định ở thời điểm lưu.

## 2. Phân biệt auditor với các trường thời gian

Auditing thường ghi hai nhóm thông tin:

| Nhóm | Annotation | Ý nghĩa |
|---|---|---|
| Người thao tác | @CreatedBy | Actor tạo aggregate |
| Người thao tác | @LastModifiedBy | Actor thực hiện lần cập nhật gần nhất |
| Thời gian | @CreatedDate | Thời điểm tạo aggregate |
| Thời gian | @LastModifiedDate | Thời điểm cập nhật gần nhất |

AuditorAware chỉ cung cấp giá trị người thao tác cho @CreatedBy và @LastModifiedBy. Nó không cung cấp thời gian. Spring Data auditing dùng DateTimeProvider hoặc clock mặc định để điền các trường ngày giờ.

Ví dụ entity aggregate root:

~~~java
import java.time.Instant;
import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public record PurchaseOrder(
        @Id Long id,
        String orderNumber,
        String status,
        @CreatedBy String createdBy,
        @LastModifiedBy String lastModifiedBy,
        @CreatedDate Instant createdAt,
        @LastModifiedDate Instant lastModifiedAt
) {}
~~~

Khi lưu aggregate mới, auditing có thể điền actor tạo và thời điểm tạo. Khi lưu aggregate đã tồn tại, auditing cập nhật actor và thời điểm sửa gần nhất theo cấu hình auditing.

## 3. Bật auditing cho Spring Data JDBC

Spring Data JDBC cung cấp annotation @EnableJdbcAuditing để đăng ký auditing infrastructure.

Ví dụ cấu hình:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.EnableJdbcAuditing;

@Configuration
@EnableJdbcAuditing(auditorAwareRef = "auditorProvider")
public class JdbcAuditingConfiguration {
}
~~~

Thuộc tính auditorAwareRef chỉ rõ bean AuditorAware mà auditing sẽ sử dụng. Tên auditorProvider phải khớp với tên bean được khai báo.

Nếu ứng dụng chỉ có một bean AuditorAware phù hợp, có thể để Spring Data tự tìm bean theo cơ chế cấu hình của phiên bản đang dùng. Khai báo auditorAwareRef tường minh thường dễ đọc hơn khi ứng dụng có nhiều nguồn auditor hoặc nhiều cấu hình persistence.

@EnableJdbcAuditing kích hoạt cơ chế auditing của Spring Data JDBC. Chỉ khai báo annotation @CreatedBy trên entity mà không bật auditing thì chưa đủ để các giá trị được tự động điền.

## 4. Cung cấp AuditorAware đơn giản

Nếu ứng dụng chưa tích hợp Spring Security hoặc chỉ cần actor cố định trong một tác vụ cụ thể, có thể khai báo bean:

~~~java
import java.util.Optional;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.jdbc.repository.config.EnableJdbcAuditing;

@Configuration
@EnableJdbcAuditing(auditorAwareRef = "auditorProvider")
public class JdbcAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorProvider() {
        return () -> Optional.of("system");
    }
}
~~~

Mọi thao tác được auditing xử lý trong cấu hình này sẽ nhận actor system. Cách này hữu ích cho ví dụ hoặc ứng dụng chỉ có một actor hệ thống, nhưng không phù hợp nếu cần phân biệt nhiều người dùng thực tế.

Không nên hard-code một username cố định cho toàn bộ ứng dụng nếu audit log được dùng để truy vết trách nhiệm. Giá trị auditor phải phản ánh nguồn danh tính thật của thao tác.

## 5. Lấy auditor hiện tại từ Spring Security

Trong ứng dụng web dùng Spring Security, người dùng đã xác thực thường được biểu diễn bởi Authentication trong SecurityContextHolder. AuditorAware có thể đọc Authentication tại thời điểm auditing cần giá trị.

Ví dụ dùng tên principal:

~~~java
import java.util.Optional;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.jdbc.repository.config.EnableJdbcAuditing;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

@Configuration
@EnableJdbcAuditing(auditorAwareRef = "auditorProvider")
public class JdbcAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorProvider() {
        return () -> Optional.ofNullable(
                        SecurityContextHolder.getContext().getAuthentication()
                )
                .filter(Authentication::isAuthenticated)
                .filter(authentication ->
                        !(authentication instanceof AnonymousAuthenticationToken))
                .map(Authentication::getName)
                .filter(name -> !name.isBlank());
    }
}
~~~

Các bước xử lý:

1. Lấy Authentication hiện tại từ SecurityContextHolder.
2. Nếu không có Authentication, Optional rỗng.
3. Chỉ chấp nhận Authentication đã xác thực.
4. Loại AnonymousAuthenticationToken vì người dùng anonymous không phải actor đã đăng nhập.
5. Lấy tên định danh qua Authentication.getName().
6. Loại tên rỗng trước khi trả auditor.

Không nên chỉ kiểm tra authentication khác null. Ứng dụng có thể có anonymous authentication được tạo tự động; nếu không loại trường hợp này, audit có thể ghi anonymousUser như thể đó là người dùng thật.

Authentication.getName() thường trả username, subject hoặc tên định danh theo cơ chế authentication. Hãy xác nhận giá trị đó đúng với hợp đồng cột audit của ứng dụng.

## 6. Lưu ID ổn định hay username?

Một lựa chọn thiết kế quan trọng là lưu username hiển thị hay ID bất biến của người dùng.

| Giá trị auditor | Ưu điểm | Hạn chế |
|---|---|---|
| Username | Dễ đọc log, dễ tra cứu thủ công | Có thể đổi tên hoặc được tái sử dụng |
| Email | Dễ nhận biết trong hệ thống nhỏ | Có thể thay đổi và thường là dữ liệu cá nhân |
| User ID dạng UUID/Long | Ổn định, phù hợp liên kết tới bảng người dùng | Cần tra cứu để hiển thị tên |
| Mã service/client | Phân biệt tác vụ do service account thực hiện | Cần quy ước đặt tên và quản lý vòng đời service identity |

Nếu audit phục vụ truy vết lâu dài, nên ưu tiên một ID ổn định, duy nhất. Có thể lưu cả actor ID và snapshot tên hiển thị nếu yêu cầu nghiệp vụ cần đọc lịch sử mà không phải tra cứu thông tin người dùng hiện tại.

Ví dụ entity lưu UUID:

~~~java
@CreatedBy
private UUID createdBy;
~~~

Khi đó bean phải khai báo cùng generic type:

~~~java
@Bean
AuditorAware<UUID> auditorProvider() {
    return () -> currentUserId();
}
~~~

Không khai báo AuditorAware<String> rồi kỳ vọng Spring tự chuyển username thành UUID hoặc Long. Generic type của auditor cần tương thích với kiểu property được đánh dấu @CreatedBy/@LastModifiedBy và mapping converter tương ứng.

## 7. Lấy user ID từ custom principal

Trong ứng dụng thực tế, Authentication thường chứa một custom principal có ID người dùng. Ví dụ:

~~~java
public record AppPrincipal(
        UUID userId,
        String username
) {}
~~~

AuditorAware có thể trích xuất ID:

~~~java
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.domain.AuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

public class CurrentUserAuditorAware implements AuditorAware<UUID> {

    @Override
    public Optional<UUID> getCurrentAuditor() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return Optional.empty();
        }

        Object principal = authentication.getPrincipal();

        if (principal instanceof AppPrincipal appPrincipal) {
            return Optional.of(appPrincipal.userId());
        }

        return Optional.empty();
    }
}
~~~

Đăng ký bean:

~~~java
@Bean
AuditorAware<UUID> auditorProvider() {
    return new CurrentUserAuditorAware();
}
~~~

Cách này tránh phụ thuộc username có thể thay đổi. Nếu ứng dụng hỗ trợ nhiều loại principal (UserDetails, JWT, service account), hãy xử lý từng loại một cách tường minh. Không nên gọi toString() trên một principal tùy ý rồi lưu kết quả làm actor ID; toString() không phải contract định danh ổn định.

## 8. DDL và kiểu dữ liệu phải khớp với auditor

Với entity dùng String auditor:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    status VARCHAR(30) NOT NULL,
    created_by VARCHAR(120),
    last_modified_by VARCHAR(120),
    created_at TIMESTAMP,
    last_modified_at TIMESTAMP
);
~~~

Các cột audit phải có tên và kiểu phù hợp với mapping của entity. Nếu dùng UUID, cột vật lý cần có kiểu UUID hoặc kiểu tương thích theo database/driver và converter đã cấu hình.

Ví dụ:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    created_by UUID,
    last_modified_by UUID
);
~~~

Cú pháp kiểu UUID và timestamp khác nhau giữa database. Hãy điều chỉnh DDL theo DBMS và naming strategy thực tế.

### Có nên đặt NOT NULL cho cột auditor?

Chỉ đặt NOT NULL nếu mọi đường tạo dữ liệu đều có auditor hợp lệ. Nếu có migration, import, scheduler hoặc thao tác hệ thống không gắn người dùng, AuditorAware có thể trả Optional.empty(). Khi đó cột NOT NULL có thể làm INSERT thất bại.

Có ba cách thiết kế phổ biến:

- Cho phép null khi actor thực sự không xác định.
- Cung cấp actor hệ thống rõ ràng cho các tác vụ nền.
- Bắt buộc mọi use case tạo/sửa phải có actor và từ chối thao tác nếu không có.

Không nên tự động gán system cho mọi trường hợp Optional.empty() nếu điều đó che giấu lỗi mất SecurityContext. Hãy phân biệt actor hệ thống thực sự với request đáng lẽ phải có người dùng đăng nhập.

## 9. Optional.empty() có ý nghĩa gì?

AuditorAware trả Optional<T> thay vì T để biểu diễn trường hợp không tìm được actor.

Ví dụ:

~~~java
@Override
public Optional<String> getCurrentAuditor() {
    return Optional.empty();
}
~~~

Khi auditor không có giá trị, auditing infrastructure không có actor để gán vào property @CreatedBy hoặc @LastModifiedBy. Nó không tự tạo username, không truy vấn bảng người dùng và cũng không suy đoán actor từ thread.

Hành vi đối với dữ liệu còn phụ thuộc entity hiện tại và schema:

- Khi insert mới, property auditor có thể vẫn null nếu không có giá trị khác.
- Nếu cột database là NOT NULL, INSERT có thể thất bại.
- Khi update, nếu không có auditor mới, giá trị hiện tại có thể được giữ nguyên theo cơ chế auditing/property access.
- Các trường ngày giờ vẫn có thể được cập nhật độc lập với auditor nếu date auditing đang bật.

Nếu quy tắc nghiệp vụ yêu cầu actor bắt buộc, nên kiểm tra rõ ở application service hoặc cấu hình nguồn auditor để thao tác không có actor bị từ chối với thông báo phù hợp.

## 10. Tác vụ nền và service account

Không phải mọi lần save đều xuất phát từ HTTP request. Các trường hợp thường gặp:

- Scheduled task chạy theo @Scheduled.
- Batch import dữ liệu.
- Message listener xử lý message từ broker.
- Job đồng bộ dữ liệu từ hệ thống khác.
- Migration hoặc tác vụ quản trị.
- Service-to-service request.

Các luồng này có thể không có SecurityContext. Cần xác định actor theo nguồn kích hoạt:

| Loại thao tác | Auditor gợi ý |
|---|---|
| Người dùng đăng nhập thao tác qua web/API | User ID hoặc principal ID |
| Scheduler | Service account có tên ổn định như service:daily-reconciliation |
| Batch import | Mã job/import batch hoặc service account |
| Message consumer | Service identity hoặc actor được xác thực trong message metadata |
| Migration | Actor migration riêng, hoặc không gán user nếu schema cho phép |
| Tác vụ quản trị | ID người quản trị đã xác thực |

Không nên dùng một giá trị chung cho mọi background job nếu cần biết chính xác job nào đã thay đổi dữ liệu.

### Không dựa vào SecurityContext của request cho async task

SecurityContextHolder thường lưu context theo thread. Khi chuyển công việc sang executor, scheduler hoặc message listener, context của request ban đầu có thể không được truyền tự động.

Nếu cần giữ actor của request khi chạy bất đồng bộ, phải truyền danh tính một cách có chủ đích bằng cơ chế security context propagation phù hợp hoặc đưa actor ID đã xác thực vào command/message. Không nên giả định thread mới sẽ nhìn thấy Authentication của thread HTTP.

## 11. Cung cấp auditor cho tác vụ hệ thống một cách tường minh

Có thể dùng một principal hệ thống cho các job đã được phân loại. Ví dụ bean sau là một lựa chọn nếu ứng dụng thực sự chạy một tác vụ nền chuyên biệt và không có người dùng:

~~~java
@Bean
AuditorAware<String> batchAuditorProvider() {
    return () -> Optional.of("service:customer-import");
}
~~~

Nếu cùng ứng dụng vừa xử lý request người dùng vừa chạy job nền, không nên thay AuditorAware toàn cục bằng giá trị cố định. Thay vào đó, có thể dùng một nguồn actor theo context của ứng dụng hoặc tách các job vào service/configuration có quy ước rõ.

Một lựa chọn là đặt actor hệ thống vào context được quản lý trong phạm vi job:

~~~java
public final class AuditActorContext {
    private static final ThreadLocal<String> ACTOR = new ThreadLocal<>();

    private AuditActorContext() {}

    public static void set(String actor) {
        ACTOR.set(actor);
    }

    public static Optional<String> currentActor() {
        return Optional.ofNullable(ACTOR.get());
    }

    public static void clear() {
        ACTOR.remove();
    }
}
~~~

AuditorAware có thể ưu tiên actor được đặt tường minh rồi mới đọc SecurityContext:

~~~java
@Bean
AuditorAware<String> auditorProvider() {
    return () -> AuditActorContext.currentActor()
            .or(() -> currentAuthenticatedUsername());
}
~~~

Khi chạy job:

~~~java
try {
    AuditActorContext.set("service:nightly-import");
    importService.run();
} finally {
    AuditActorContext.clear();
}
~~~

Đây là mẫu minh họa cho context đồng bộ theo thread. ThreadLocal phải luôn được clear trong finally vì thread pool tái sử dụng thread. Nếu tác vụ chạy bất đồng bộ, context cần được truyền qua executor/message một cách tường minh; ThreadLocal không tự lan sang thread khác.

Trong ứng dụng đơn giản, có thể chọn cách khác phù hợp hơn như truyền actor ID vào command/service method. Không cần xây ThreadLocal nếu một tham số tường minh đã giải quyết được yêu cầu.

## 12. Kết hợp @CreatedBy và @LastModifiedBy

Entity có thể khai báo cả hai property:

~~~java
@Table("customers")
public record Customer(
        @Id Long id,
        String name,
        @CreatedBy String createdBy,
        @LastModifiedBy String lastModifiedBy
) {}
~~~

Ý nghĩa:

- createdBy ghi nhận actor lúc tạo.
- lastModifiedBy ghi nhận actor của lần thay đổi gần nhất.
- Khi tạo mới, cấu hình mặc định của auditing thường cập nhật các trường modified ngay lúc tạo; thuộc tính modifyOnCreate có thể điều chỉnh hành vi này.
- Khi cập nhật aggregate đã tồn tại, createdBy giữ giá trị ban đầu, còn lastModifiedBy được cập nhật theo auditor hiện tại.

Không tự gán lại createdBy ở mọi lần update. Đây là thông tin lịch sử tạo bản ghi, cần được bảo toàn.

Nếu ứng dụng cần biết cả người tạo và các lần sửa trước đó, hai trường hiện tại chỉ giữ người tạo và người sửa cuối. Muốn có lịch sử đầy đủ, cần audit table/event log riêng; không thể suy ra toàn bộ lịch sử từ @CreatedBy và @LastModifiedBy.

## 13. AuditorAware và DateTimeProvider

AuditorAware cung cấp actor; DateTimeProvider cung cấp thời gian hiện tại. Hai abstraction độc lập nhưng thường được cấu hình cùng auditing infrastructure.

Ví dụ DateTimeProvider tùy chỉnh dùng Clock:

~~~java
import java.time.Clock;
import java.time.temporal.TemporalAccessor;
import java.util.Optional;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.context.annotation.Bean;

@Bean
Clock auditClock() {
    return Clock.systemUTC();
}

@Bean
DateTimeProvider dateTimeProvider(Clock auditClock) {
    return () -> Optional.<TemporalAccessor>of(auditClock.instant());
}
~~~

Có thể tham chiếu bean này trong cấu hình auditing:

~~~java
@EnableJdbcAuditing(
    auditorAwareRef = "auditorProvider",
    dateTimeProviderRef = "dateTimeProvider"
)
~~~

Cấu hình Clock giúp test thời gian ổn định và tránh gọi trực tiếp system clock trong nhiều nơi. Nếu không cần tùy chỉnh, auditing có thể sử dụng time provider mặc định.

AuditorAware không nên trả timestamp và DateTimeProvider không nên trả username. Giữ hai trách nhiệm riêng làm cho entity metadata dễ hiểu và test độc lập hơn.

## 14. AuditorAware không tự chạy cho SQL trực tiếp

Auditing của Spring Data JDBC được tích hợp vào lifecycle persistence của aggregate. Khi repository.save(...) hoặc JdbcAggregateTemplate lưu aggregate, auditing callback có thể điền @CreatedBy, @LastModifiedBy và các trường ngày giờ.

Một câu lệnh direct SQL:

~~~java
@Modifying
@Query("""
    UPDATE customers
    SET name = :name
    WHERE id = :id
    """)
int updateName(Long id, String name);
~~~

không tự chạy aggregate auditing callback cho từng hàng bị update. AuditorAware không được gọi chỉ vì câu UPDATE đó được thực thi.

Nếu dùng @Query DML hoặc JdbcTemplate để cập nhật bảng có audit columns, SQL phải tự cập nhật các cột đó hoặc use case phải điều phối audit riêng:

~~~sql
UPDATE customers
SET name = :name,
    last_modified_by = :actor,
    last_modified_at = CURRENT_TIMESTAMP
WHERE id = :id;
~~~

Giá trị actor cần được lấy từ nguồn xác thực phù hợp và bind như tham số. Không nối chuỗi actor vào SQL.

Nếu cần auditing đồng nhất trên nhiều đường ghi, hãy chọn một chiến lược rõ: ưu tiên repository/template cho aggregate thông thường; với direct SQL, dùng helper chung để lấy actor/thời gian và cập nhật audit columns, hoặc chuyển thao tác qua một service có trách nhiệm audit.

## 15. AuditorAware và aggregate root

Spring Data JDBC tổ chức persistence theo aggregate root. Auditing metadata được xử lý trên aggregate root trong đường save của Spring Data JDBC.

Nếu root chứa collection child qua @MappedCollection, đừng mặc định rằng một AuditorAware riêng sẽ được gọi cho từng child entity như một lần save độc lập. Các trường audit của child cần được thiết kế theo cách mapping và lifecycle mà ứng dụng thực sự sử dụng.

Nếu child cần ghi nhận người tạo/người sửa riêng, hãy kiểm tra hỗ trợ mapping/lifecycle của phiên bản Spring Data Relational đang dùng và cân nhắc mô hình hóa child có vòng đời độc lập thành aggregate riêng khi điều đó phù hợp với domain. Không tách aggregate chỉ để né một annotation.

## 16. Kiểm thử AuditorAware

Nên kiểm tra ít nhất ba trường hợp:

1. Có actor hợp lệ: auditor trả đúng ID/username.
2. Không có Authentication hoặc anonymous: auditor trả Optional.empty() hoặc actor fallback theo quy ước đã chọn.
3. Background job: auditor trả service identity đúng nếu job cần ghi nhận actor hệ thống.

Unit test cho implementation đọc SecurityContext có thể thiết lập Authentication giả:

~~~java
@Test
void returnsAuthenticatedUsername() {
    Authentication authentication =
            new UsernamePasswordAuthenticationToken(
                    "lan",
                    "n/a",
                    List.of(new SimpleGrantedAuthority("ROLE_USER"))
            );

    SecurityContextHolder.getContext().setAuthentication(authentication);

    try {
        assertEquals(
                Optional.of("lan"),
                auditorAware.getCurrentAuditor()
        );
    } finally {
        SecurityContextHolder.clearContext();
    }
}
~~~

Test thực tế cần import JUnit, assertion và Spring Security classes tương ứng. Luôn clear SecurityContext sau test để tránh trạng thái rò rỉ sang test khác.

### Integration test với repository

Để xác nhận auditing thực sự được bật, cần lưu aggregate qua repository trong Spring context:

~~~java
@Test
void recordsCreatedAndModifiedAuditors() {
    setAuthenticatedUser("lan");

    Customer saved = customerRepository.save(
            new Customer(null, "Lan", null, null)
    );

    assertEquals("lan", saved.createdBy());
    assertEquals("lan", saved.lastModifiedBy());

    setAuthenticatedUser("minh");

    Customer changed = new Customer(
            saved.id(),
            "Lan Nguyen",
            saved.createdBy(),
            saved.lastModifiedBy()
    );

    Customer updated = customerRepository.save(changed);

    assertEquals("lan", updated.createdBy());
    assertEquals("minh", updated.lastModifiedBy());
}
~~~

Đây là ví dụ về ý tưởng kiểm thử; constructor và các property của Customer phải khớp entity thực tế. Nếu dùng immutable record, dùng instance trả về từ save để lấy giá trị audit đã được điền.

Integration test cần kiểm tra cả dữ liệu đọc lại từ database nếu mục tiêu là xác nhận mapping và persistence, không chỉ kiểm tra object trả về.

## 17. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| createdBy luôn null | Chưa bật @EnableJdbcAuditing hoặc chưa có AuditorAware bean | Kiểm tra cấu hình auditing và bean reference |
| lastModifiedBy không đổi | Update không đi qua aggregate save lifecycle hoặc auditor rỗng | Kiểm tra đường ghi và SecurityContext |
| Lưu lỗi NOT NULL ở cột auditor | AuditorAware trả Optional.empty() nhưng schema bắt buộc giá trị | Chọn fallback có chủ đích hoặc cho phép null |
| Audit lưu anonymousUser | Không loại AnonymousAuthenticationToken | Lọc anonymous authentication |
| Lưu username nhưng cần user ID | AuditorAware trả sai định danh | Dùng custom principal và AuditorAware<UUID/Long> |
| Không map được auditor type | Generic type không khớp property hoặc converter | Đồng bộ kiểu Java, kiểu SQL và converter |
| Job nền ghi null actor | Job không có SecurityContext | Dùng service identity hoặc truyền actor tường minh |
| Async task mất actor | SecurityContext/ThreadLocal không được truyền sang thread mới | Dùng context propagation hoặc truyền actor trong message/command |
| Direct UPDATE không đổi lastModifiedBy | @Query DML không gọi auditing callback | Cập nhật audit columns trong SQL hoặc điều phối riêng |
| createdBy bị thay đổi ngoài ý muốn | Gán lại trường created trong logic update | Bảo toàn giá trị ban đầu |
| Test ảnh hưởng lẫn nhau | Không clear SecurityContext | Clear context trong finally/tearDown |
| Audit lưu email cá nhân ngoài ý muốn | Chọn email làm định danh lâu dài | Cân nhắc ID ổn định và chính sách lưu dữ liệu |

## 18. Quy trình thiết lập AuditorAware

Khi thêm auditing vào ứng dụng Spring Data JDBC:

1. Xác định kiểu actor cần lưu: username, UUID, Long hoặc service identity.
2. Khai báo các property audit với @CreatedBy và @LastModifiedBy.
3. Tạo cột database có tên, kiểu và nullability tương thích.
4. Bật @EnableJdbcAuditing và tham chiếu đúng bean AuditorAware.
5. Đọc actor từ nguồn xác thực tại thời điểm callback được gọi.
6. Loại anonymous hoặc principal không hợp lệ.
7. Quy định rõ Optional.empty() được chấp nhận hay phải thay bằng service actor.
8. Xử lý scheduler, batch, message consumer và async task.
9. Đảm bảo direct SQL có quy tắc cập nhật audit columns riêng.
10. Viết unit test cho AuditorAware và integration test qua repository.

~~~mermaid
flowchart TD
    A[Aggregate được save] --> B[Spring Data JDBC auditing]
    B --> C[AuditorAware.getCurrentAuditor]
    C --> D{Có actor hợp lệ?}
    D -->|Có| E[Trả Optional.of(actor)]
    D -->|Không| F[Trả Optional.empty hoặc fallback đã định nghĩa]
    E --> G[Gán CreatedBy / LastModifiedBy]
    F --> G
    G --> H[Mapping và SQL persistence]
    H --> I[Database]
~~~

## 19. Nguyên tắc ghi nhớ

- AuditorAware<T> trả Optional<T> đại diện người thao tác hiện tại.
- @CreatedBy và @LastModifiedBy dùng auditor; @CreatedDate và @LastModifiedDate dùng date/time provider.
- Bật auditing cho Spring Data JDBC bằng @EnableJdbcAuditing.
- Generic type của AuditorAware phải tương thích với kiểu property audit.
- SecurityContextHolder có thể không có Authentication; phải xử lý null, unauthenticated và anonymous.
- Nên ưu tiên định danh ổn định như user ID nếu audit cần truy vết lâu dài.
- Optional.empty() không tự tạo actor; hãy quy định rõ schema có cho phép null hay không.
- Background job và async task cần service identity hoặc cơ chế truyền actor tường minh.
- AuditorAware và auditing callbacks không tự chạy cho direct SQL hoặc @Query DML.
- @CreatedBy giữ actor tạo; @LastModifiedBy thay đổi theo lần sửa gần nhất.
- After-save hoặc auditing callback không phải cơ chế phát hành side effect sau commit.
- Kiểm thử cả implementation AuditorAware và persistence thực tế qua repository.

AuditorAware là cầu nối giữa danh tính mà ứng dụng đã xác thực và metadata auditing của Spring Data JDBC. Hãy chọn một định danh ổn định, xử lý rõ trường hợp không có người dùng, phân biệt request với tác vụ hệ thống và giữ cùng quy tắc trên mọi đường ghi dữ liệu. Khi cấu hình đúng, @CreatedBy và @LastModifiedBy có thể ghi lại actor nhất quán mà application service không phải tự gán các trường này trong từng use case.

## Tài liệu tham khảo

- [Spring Data Relational — Auditing](https://docs.spring.io/spring-data/relational/reference/jdbc/auditing.html)
- [Spring Data Commons — Auditing](https://docs.spring.io/spring-data/commons/reference/auditing.html)
- [AuditorAware API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/AuditorAware.html)
- [EnableJdbcAuditing API](https://docs.spring.io/spring-data/relational/docs/current/api/org/springframework/data/jdbc/repository/config/EnableJdbcAuditing.html)

