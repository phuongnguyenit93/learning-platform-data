# Giá trị kiểm toán khi nhập dữ liệu nền hoặc chạy tác vụ định kỳ

Spring Data JPA Auditing tự ghi nhận một số metadata của entity trong vòng đời lưu trữ, thường gồm thời điểm tạo, thời điểm cập nhật, người tạo và người cập nhật. Với request web, danh tính người dùng có thể lấy từ security context. Nhưng khi dữ liệu được nhập từ file, đồng bộ từ hệ thống khác, chạy theo lịch hoặc xử lý bằng worker nền, thường không có người dùng đang đăng nhập.

Nếu không thiết kế rõ danh tính thực hiện tác vụ, các trường `createdBy` và `lastModifiedBy` có thể bị để trống, gán nhầm người dùng, hoặc tất cả bản ghi đều mang một giá trị chung khó truy vết. Bài này trình bày cách xác định actor cho tác vụ nền, cấu hình `AuditorAware`, xử lý thời gian, nhập dữ liệu theo lô và các giới hạn khi dùng bulk SQL.

## 1. Spring Data JPA Auditing ghi nhận điều gì?

Auditing của Spring Data JPA thường quản lý bốn loại thông tin:

| Annotation | Ý nghĩa | Thời điểm điển hình |
|---|---|---|
| `@CreatedDate` | Thời điểm entity được tạo | Khi entity được persist lần đầu |
| `@LastModifiedDate` | Thời điểm entity được sửa gần nhất | Khi tạo và mỗi lần cập nhật entity |
| `@CreatedBy` | Actor tạo entity | Khi entity được tạo |
| `@LastModifiedBy` | Actor sửa entity gần nhất | Khi tạo và mỗi lần cập nhật entity |

Các trường này mô tả metadata của entity trong ứng dụng. Chúng không tự tạo một lịch sử đầy đủ cho từng thay đổi. Ví dụ, `lastModifiedBy` chỉ giữ actor gần nhất, không lưu tất cả actor trước đó hoặc giá trị cũ/mới của từng thuộc tính.

Cần phân biệt ba khái niệm khi nhập dữ liệu:

- **Actor thực thi:** tài khoản hoặc tiến trình thực sự chạy import, ví dụ `job:nightly-import`.
- **Người khởi tạo:** người đã yêu cầu hoặc phê duyệt lần import, ví dụ một quản trị viên.
- **Nguồn gốc dữ liệu:** hệ thống hoặc file cung cấp bản ghi, ví dụ `legacy-crm` hoặc `partner-feed`.

Không nên mặc định ba giá trị này là một. `@CreatedBy` thường nên phản ánh actor thực sự ghi entity vào database. Nếu cần biết ai khởi tạo import hoặc dữ liệu đến từ đâu, hãy lưu riêng các trường như `requestedBy`, `importJobId`, `sourceSystem` hoặc `sourceRecordId`.

## 2. Cấu hình các trường auditing trên entity

Bật auditing bằng `@EnableJpaAuditing`, đăng ký `AuditingEntityListener` và đánh dấu các trường cần theo dõi.

Có thể đặt các trường chung trong một lớp `@MappedSuperclass` để nhiều entity tái sử dụng:

```java
import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.EntityListeners;
import jakarta.persistence.MappedSuperclass;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

@MappedSuperclass
@EntityListeners(AuditingEntityListener.class)
public abstract class AuditableEntity {

    @CreatedDate
    @Column(nullable = false, updatable = false)
    private Instant createdAt;

    @LastModifiedDate
    @Column(nullable = false)
    private Instant lastModifiedAt;

    @CreatedBy
    @Column(length = 100, updatable = false)
    private String createdBy;

    @LastModifiedBy
    @Column(length = 100)
    private String lastModifiedBy;

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getLastModifiedAt() {
        return lastModifiedAt;
    }

    public String getCreatedBy() {
        return createdBy;
    }

    public String getLastModifiedBy() {
        return lastModifiedBy;
    }
}
```

Một entity nghiệp vụ kế thừa lớp này:

```java
@Entity
public class Customer extends AuditableEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String externalCode;
    private String fullName;
    private String status;

    // Constructor, getter và phương thức nghiệp vụ
}
```

Các trường ngày giờ dùng `Instant` để biểu diễn một thời điểm trên trục thời gian. Khi ánh xạ xuống database, hãy thống nhất kiểu cột, cách lưu UTC và quy tắc hiển thị theo múi giờ của người dùng. Không nên lấy giờ local của máy chạy job rồi lưu như thể đó là UTC.

`updatable = false` giúp JPA không đưa trường tạo vào câu UPDATE thông thường. Đây là một lớp bảo vệ ở mức mapping; các câu SQL trực tiếp vẫn có thể sửa trường này nếu được viết như vậy.

## 3. Cung cấp actor bằng AuditorAware

Spring Data JPA lấy actor hiện tại thông qua interface `AuditorAware<T>`. Kiểu `T` phải phù hợp với kiểu của các trường `@CreatedBy` và `@LastModifiedBy`.

Ví dụ dưới đây ưu tiên actor được gắn rõ cho tác vụ nền, sau đó mới lấy danh tính người dùng từ Spring Security. Nếu không có người dùng hoặc job context, ứng dụng dùng actor kỹ thuật `system`. Hãy thay giá trị dự phòng theo quy ước nhận diện của hệ thống.

```java
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

@Configuration
@EnableJpaAuditing(auditorAwareRef = "auditorAware")
public class JpaAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorAware() {
        return () -> AuditActorContext.current().or(() -> {
            Authentication authentication =
                    SecurityContextHolder.getContext().getAuthentication();

            if (authentication == null
                    || !authentication.isAuthenticated()
                    || authentication instanceof AnonymousAuthenticationToken) {
                return Optional.of("system");
            }

            return Optional.ofNullable(authentication.getName())
                    .filter(name -> !name.isBlank())
                    .or(() -> Optional.of("system"));
        });
    }
}
```

Ví dụ này giả định ứng dụng đã dùng Spring Security. Nếu ứng dụng không có Spring Security, hãy thay phần đọc `SecurityContextHolder` bằng nguồn danh tính phù hợp, hoặc chỉ dùng job context cho tác vụ nền. Không thêm dependency Security chỉ để lấy auditing actor nếu hệ thống không cần nó.

Nên lưu một định danh ổn định như user ID, subject hoặc service account ID. Tên hiển thị có thể thay đổi theo thời gian; nếu lưu tên hiển thị làm khóa truy vết, việc đối chiếu dữ liệu cũ có thể khó hơn.

### 3.1. Bật auditing và cấu hình thời gian

Spring Data có thể lấy thời gian hiện tại mặc định. Nếu muốn kiểm soát múi giờ và làm test xác định được, hãy cung cấp `DateTimeProvider` dựa trên `Clock`:

```java
import java.time.Clock;
import java.time.Instant;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;

@Configuration
@EnableJpaAuditing(
        auditorAwareRef = "auditorAware",
        dateTimeProviderRef = "auditingDateTimeProvider"
)
public class JpaAuditingTimeConfiguration {

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

Nếu đã khai báo `@EnableJpaAuditing` trong lớp cấu hình actor, chỉ giữ một cấu hình bật auditing và thêm các bean `Clock`/ `DateTimeProvider` vào đó. Không khai báo nhiều cấu hình `@EnableJpaAuditing` độc lập một cách tùy tiện.

Dùng một `Clock` có thể thay thế trong kiểm thử để xác minh chính xác `createdAt` và `lastModifiedAt`. Điều này dễ kiểm soát hơn việc chờ thời gian thực thay đổi giữa hai thao tác.

## 4. Gán danh tính cho tác vụ nền và scheduler

Một scheduler thường chạy mà không có HTTP request và không có người dùng đăng nhập. Nếu `AuditorAware` chỉ đọc SecurityContext, kết quả có thể là `Optional.empty()`. Nếu cột audit bắt buộc có giá trị, điều này có thể làm thao tác lưu thất bại hoặc khiến dữ liệu audit không đầy đủ.

Có thể dùng một context theo thread để đặt actor rõ ràng cho từng lần chạy. Context phải được dọn khi hoàn tất để thread dùng lại không mang danh tính của job trước.

```java
import java.util.Optional;

public final class AuditActorContext {

    private static final ThreadLocal<String> CURRENT = new ThreadLocal<>();

    private AuditActorContext() {
    }

    public static Optional<String> current() {
        return Optional.ofNullable(CURRENT.get());
    }

    public static Scope use(String actor) {
        if (actor == null || actor.isBlank()) {
            throw new IllegalArgumentException("actor must not be blank");
        }

        String previous = CURRENT.get();
        CURRENT.set(actor);

        return () -> {
            if (previous == null) {
                CURRENT.remove();
            } else {
                CURRENT.set(previous);
            }
        };
    }

    @FunctionalInterface
    public interface Scope extends AutoCloseable {
        @Override
        void close();
    }
}
```

Dùng context trong scheduler:

```java
@Component
public class NightlyImportJob {

    private final ImportChunkService importChunkService;

    public NightlyImportJob(ImportChunkService importChunkService) {
        this.importChunkService = importChunkService;
    }

    @Scheduled(cron = "0 0 2 * * *")
    public void run() {
        try (AuditActorContext.Scope ignored =
                     AuditActorContext.use("job:nightly-import")) {
            importChunkService.importNextChunk();
        }
    }
}
```

Service ghi dữ liệu nằm trong một Spring bean khác để lời gọi đi qua proxy transaction:

```java
@Service
public class ImportChunkService {

    private final CustomerRepository customerRepository;

    public ImportChunkService(CustomerRepository customerRepository) {
        this.customerRepository = customerRepository;
    }

    @Transactional
    public void importNextChunk() {
        // Đọc một chunk từ nguồn và tạo/cập nhật các Customer.
        // Các thao tác repository chạy trong transaction của chunk.
    }
}
```

Trong ví dụ, `job:nightly-import` là actor của lần ghi dữ liệu. Nếu import được người dùng yêu cầu, có thể lưu thêm `requestedBy` để giữ danh tính người khởi tạo. Không nên thay actor thực thi bằng tên người dùng trong dữ liệu nguồn nếu người đó không thực sự chạy thao tác ghi.

`ThreadLocal` phù hợp khi job và transaction chạy đồng bộ trên cùng thread. Nếu chuyển việc sang executor, `@Async`, worker pool hoặc thread khác, context không tự truyền sang thread mới. Hãy truyền actor tường minh trong message/command hoặc dùng `TaskDecorator` để sao chép context và khôi phục context cũ sau khi chạy. Không truyền context bằng cách giữ một giá trị static không được dọn dẹp.

## 5. Auditing khi nhập dữ liệu bằng repository

Khi lưu entity qua vòng đời JPA thông thường, auditing listener có cơ hội điền các trường metadata.

Ví dụ, import một bản ghi mới:

```java
Customer customer = new Customer();
customer.setExternalCode(row.externalCode());
customer.setFullName(row.fullName());
customer.setStatus("ACTIVE");

customerRepository.save(customer);
```

Nếu entity được tạo mới và được persist trong persistence context, `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy` và `@LastModifiedBy` được xử lý theo cấu hình auditing. Với actor context đang là `job:nightly-import`, các trường người tạo/người sửa phản ánh actor đó.

Khi cập nhật bản ghi đã tồn tại, nên tải entity đang được quản lý rồi thay đổi các thuộc tính nghiệp vụ:

```java
Customer customer = customerRepository
        .findByExternalCode(row.externalCode())
        .orElseGet(Customer::new);

customer.setExternalCode(row.externalCode());
customer.setFullName(row.fullName());
customer.setStatus(row.status());

// Nếu là entity mới, save để persist.
// Nếu đã được tải và đang managed, dirty checking sẽ ghi thay đổi khi flush.
customerRepository.save(customer);
```

Trong trường hợp entity mới, Spring Data JPA dùng `save()` để persist hoặc merge tùy trạng thái mà repository xác định. Với entity đang được quản lý trong transaction, gọi `save()` lần nữa thường không cần thiết; thay đổi được dirty checking phát hiện khi flush.

Khi cập nhật entity đã tồn tại, auditing thường giữ nguyên `createdAt` và `createdBy`, đồng thời cập nhật `lastModifiedAt` và `lastModifiedBy`. Không tự gán lại các trường tạo trong logic import.

Nếu import có chế độ upsert, hãy xác định rõ trường hợp nào là tạo mới và trường hợp nào là cập nhật. Khóa đối chiếu nên ổn định, ví dụ mã từ hệ thống nguồn. Tránh tạo bản ghi mới mỗi lần chạy chỉ vì không nhận diện được bản ghi đã nhập trước đó.

## 6. Nhập dữ liệu lớn: chia chunk và kiểm soát persistence context

Không nên mặc định đưa hàng trăm nghìn entity vào một transaction hoặc persistence context duy nhất. Cách đó có thể làm tăng bộ nhớ, thời gian giữ transaction và chi phí rollback khi một bản ghi lỗi.

Với import lớn, hãy chia dữ liệu thành các chunk có kích thước phù hợp:

```text
Nguồn dữ liệu
    |
    v
Đọc chunk 1 --> transaction 1 --> commit
    |
    v
Đọc chunk 2 --> transaction 2 --> commit
    |
    v
Đọc chunk 3 --> transaction 3 --> commit
    |
    v
Hoàn tất import
```

Một chunk có thể được xử lý bằng một phương thức service `@Transactional`. Khi chunk thành công, transaction commit; nếu chunk lỗi, chỉ chunk đó rollback. Nếu yêu cầu nghiệp vụ là toàn bộ file phải thành công hoặc thất bại cùng nhau, cần cân nhắc transaction lớn, staging table hoặc cơ chế import có trạng thái để hỗ trợ retry và phục hồi.

Khi xử lý nhiều entity trong cùng transaction, có thể dùng `flush()` và `clear()` theo từng nhóm để giảm persistence context:

```java
for (int i = 0; i < rows.size(); i++) {
    Customer customer = mapRow(rows.get(i));
    customerRepository.save(customer);

    if ((i + 1) % 500 == 0) {
        customerRepository.flush();
        entityManager.clear();
    }
}

customerRepository.flush();
```

Đây là ví dụ minh họa cho một chunk có kích thước vừa phải; cần tiêm `EntityManager` vào service. `flush()` đẩy SQL đang chờ xuống database nhưng không commit. `clear()` detach toàn bộ entity đang managed, vì vậy sau khi clear không tiếp tục dùng các object cũ như thể chúng còn được quản lý. Nếu cần cập nhật entity đã có, hãy xử lý thứ tự tải, thay đổi, flush và clear phù hợp.

`saveAll()` tiện cho mã nguồn nhưng không đồng nghĩa với một câu SQL batch duy nhất. Spring Data có thể gọi thao tác save cho từng entity; khả năng JDBC batching còn phụ thuộc Hibernate, driver và cấu hình. Hãy đo hiệu năng thực tế và cấu hình batch size phù hợp với provider/database.

Với Spring Batch, actor nên ổn định theo job/step hoặc lần chạy import. Nếu mỗi chunk chạy trên thread riêng, hãy truyền actor theo execution context của job thay vì dựa vào ThreadLocal trên thread khởi tạo.

## 7. Bulk JPQL, native SQL và JDBC có tự chạy auditing không?

Không. Các thao tác bulk update/delete của JPQL, native SQL và câu lệnh JDBC đi thẳng tới database, bỏ qua vòng đời từng entity. Vì vậy, `AuditingEntityListener` không được gọi cho từng hàng và các annotation `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy`, `@LastModifiedBy` không tự điền giá trị.

Ví dụ bulk JPQL:

```java
@Modifying
@Query("""
    update Customer c
       set c.status = :status,
           c.lastModifiedAt = :modifiedAt,
           c.lastModifiedBy = :actor
     where c.id in :ids
    """)
int updateStatusBulk(
        @Param("ids") Collection<Long> ids,
        @Param("status") String status,
        @Param("modifiedAt") Instant modifiedAt,
        @Param("actor") String actor
);
```

Với bulk query, ứng dụng phải truyền rõ thời điểm và actor. Có thể lấy actor qua cùng một dịch vụ cung cấp auditing context và lấy thời gian từ `Clock` dùng chung. Sau bulk update, persistence context có thể đang giữ entity cũ; hãy flush thay đổi cần giữ trước bulk operation và clear/refresh các entity liên quan khi cần.

Cấu hình `@Modifying(flushAutomatically = true, clearAutomatically = true)` có thể hỗ trợ đồng bộ persistence context trước/sau câu lệnh bulk, nhưng không làm auditing listener chạy cho từng hàng. Flush/clear chỉ giải quyết trạng thái persistence context.

Với JDBC, cũng phải cập nhật metadata trực tiếp:

```sql
UPDATE customer
SET status = ?,
    last_modified_at = ?,
    last_modified_by = ?
WHERE id = ?
```

Với lệnh upsert, chỉ cập nhật `last_modified_*` ở nhánh update; giữ nguyên `created_*` của bản ghi đã tồn tại. Ở nhánh insert, gán cả thông tin tạo và cập nhật theo quy ước của hệ thống.

Nếu dùng database trigger để tự ghi audit, hãy xác định trigger hay ứng dụng là nguồn sự thật cho từng trường. Không để JPA và trigger ghi đè lẫn nhau mà không có quy tắc rõ ràng. Sau khi trigger sửa dữ liệu, entity đang nằm trong persistence context cũng có thể cần refresh.

## 8. Xác định actor và nguồn dữ liệu cho đúng nghiệp vụ

Một số tình huống phổ biến:

| Tình huống | Actor nên ghi nhận | Thông tin bổ sung có thể lưu |
|---|---|---|
| Người dùng tải file và hệ thống import đồng bộ | Service account hoặc actor thực thi import theo chính sách | `requestedBy`, tên file, mã lần import |
| Job chạy mỗi đêm | `job:nightly-import` | `jobExecutionId`, thời điểm chạy, nguồn dữ liệu |
| Đồng bộ từ hệ thống đối tác | `integration:partner-a` | `sourceSystem`, `sourceRecordId` |
| Worker xử lý message | Service/worker identity của consumer | Message ID, correlation ID |
| Quản trị viên sửa dữ liệu trên giao diện | User ID ổn định của quản trị viên | Request ID nếu cần truy vết |

Nếu cần lưu ai đã yêu cầu job, hãy chụp lại danh tính đó lúc tạo job và truyền cùng metadata của job. Scheduler chạy sau đó không thể tự biết người dùng ban đầu nếu context đã kết thúc.

Không dùng một giá trị `system` duy nhất cho mọi job nếu cần phân biệt tác vụ. Các actor như `job:nightly-import`, `job:reconcile-orders` hoặc `integration:partner-a` dễ truy vết hơn. Đồng thời, giữ quy ước đặt tên ổn định để báo cáo audit không bị phân mảnh do các cách viết khác nhau.

Nếu dữ liệu import mang trường `createdBy` từ hệ thống cũ, cần quyết định trường đó biểu diễn người tạo ở hệ thống nguồn hay actor tạo bản ghi trong hệ thống hiện tại. Nếu là nguồn cũ, nên lưu thành `sourceCreatedBy` hoặc metadata nguồn. Không ghi đè `@CreatedBy` của hệ thống hiện tại bằng giá trị không được xác thực.

## 9. Kiểm thử auditing cho import và tác vụ định kỳ

Nên kiểm tra ít nhất các trường hợp sau:

1. Tạo entity trong actor context của job: `createdBy` và `lastModifiedBy` mang đúng actor; các trường thời gian được điền.
2. Cập nhật entity đã tồn tại: `createdBy` không đổi, `lastModifiedBy` chuyển sang actor hiện tại và thời gian cập nhật được làm mới.
3. Chạy tác vụ không có người dùng đăng nhập: actor dự phòng được áp dụng theo chính sách.
4. Xử lý lỗi trong chunk: transaction rollback theo ranh giới đã thiết kế; context actor vẫn được dọn trong `finally`/try-with-resources.
5. Chạy bulk JPQL hoặc JDBC: xác nhận câu lệnh tự cập nhật metadata vì listener không chạy.
6. Chạy các job đồng thời: mỗi job ghi đúng actor của chính nó, không rò rỉ ThreadLocal sang job khác.

Ví dụ kiểm thử phần actor context:

```java
@Test
void shouldUseJobActorForImportedEntity() {
    try (AuditActorContext.Scope ignored =
                 AuditActorContext.use("job:test-import")) {

        Customer customer = new Customer();
        customer.setExternalCode("C-100");
        customer.setFullName("Example");
        customerRepository.saveAndFlush(customer);

        assertThat(customer.getCreatedBy())
                .isEqualTo("job:test-import");
        assertThat(customer.getLastModifiedBy())
                .isEqualTo("job:test-import");
        assertThat(customer.getCreatedAt()).isNotNull();
        assertThat(customer.getLastModifiedAt()).isNotNull();
    }
}
```

Đoạn test giả định repository và entity có getter cần thiết, auditing được bật trong test context và transaction được flush trước khi assert. Nếu transaction test được rollback sau test, điều đó không làm mất ý nghĩa kiểm tra callback trong persistence context.

Để kiểm tra thời gian cập nhật, dùng `Clock` giả lập có thể điều khiển được: tạo entity ở thời điểm T1, chuyển clock sang T2, sửa entity và flush; xác nhận `createdAt` vẫn là T1 còn `lastModifiedAt` là T2. Với bulk SQL, kiểm tra riêng các giá trị actor và timestamp được truyền vào câu lệnh.

## 10. Auditing metadata không thay thế lịch sử thay đổi

Spring Data JPA Auditing trả lời những câu hỏi như:

- Bản ghi được tạo lúc nào?
- Actor nào đã tạo bản ghi?
- Lần cập nhật gần nhất diễn ra lúc nào và do ai?

Nó không tự trả lời:

- Một trường đã thay đổi từ giá trị nào sang giá trị nào?
- Ai đã sửa bản ghi ở tất cả các lần trước?
- Bản ghi đã bị xóa lúc nào?
- Những thay đổi nào thuộc cùng một lần import hoặc một nghiệp vụ?

Nếu cần lịch sử đầy đủ, hãy thiết kế thêm cơ chế phù hợp:

- **Hibernate Envers** để lưu revision của entity theo cấu hình và hỗ trợ truy vấn lịch sử.
- **Bảng audit bất biến** để lưu từng sự kiện thay đổi, actor, thời điểm, giá trị cần truy vết và correlation ID.
- **Outbox/event log** để ghi nhận sự kiện nghiệp vụ cùng transaction rồi chuyển tiếp an toàn.
- **Database trigger** khi cần theo dõi thay đổi ở mức database, kể cả từ ứng dụng khác.

Chọn giải pháp theo yêu cầu lưu giữ, truy vấn, hiệu năng và phạm vi hệ thống. Không nên thêm toàn bộ cơ chế lịch sử nếu yêu cầu chỉ cần bốn trường metadata cơ bản.

## 11. Checklist triển khai

- [ ] Entity có `AuditingEntityListener` và các trường auditing đúng kiểu dữ liệu.
- [ ] Ứng dụng bật `@EnableJpaAuditing` và khai báo `AuditorAware` rõ ràng.
- [ ] Job, scheduler, integration và worker có actor ổn định, dễ truy vết.
- [ ] Actor của người khởi tạo được lưu riêng nếu khác actor thực thi.
- [ ] Context theo thread được khôi phục và dọn sau tác vụ; async có cơ chế truyền actor.
- [ ] Timestamp dùng quy ước UTC/Instant nhất quán và có thể kiểm thử bằng Clock.
- [ ] Import được chia chunk hợp lý; transaction và retry có ranh giới rõ ràng.
- [ ] Không giả định `saveAll()` luôn tạo một batch SQL duy nhất.
- [ ] Bulk JPQL, native SQL và JDBC tự cập nhật các trường audit cần thiết.
- [ ] Có kiểm thử cho tạo mới, cập nhật, actor nền, lỗi chunk và bulk update.
- [ ] Nếu cần lịch sử từng thay đổi, đã chọn Envers, audit table, outbox hoặc trigger phù hợp.

Spring Data JPA Auditing có thể ghi nhận chính xác tác vụ import và scheduler nếu ứng dụng cung cấp actor và thời gian có chủ đích. Với thao tác entity thông thường, listener sẽ điền metadata theo vòng đời JPA; với bulk SQL/JDBC, ứng dụng phải tự cập nhật các trường đó. Việc phân biệt actor thực thi, người khởi tạo và nguồn dữ liệu giúp dữ liệu kiểm toán có ý nghĩa và hỗ trợ truy vết khi tác vụ chạy tự động hoặc được retry.