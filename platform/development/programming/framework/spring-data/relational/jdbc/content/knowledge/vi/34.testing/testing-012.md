# Kiểm thử callback, auditing và SQL ghi trực tiếp

Spring Data JDBC có nhiều điểm mở rộng trong vòng đời persistence. Entity callback có thể bổ sung hoặc thay đổi dữ liệu trước/sau khi lưu; auditing tự điền actor và timestamp; còn repository query hoặc SQL trực tiếp có thể thay đổi database theo một đường thực thi khác.

Một test chỉ xác nhận hàng đã được ghi vào database chưa đủ chứng minh các hành vi này hoạt động đúng. Cần kiểm tra riêng:

1. Callback nào được gọi, ở thời điểm nào và cho aggregate nào.
2. Metadata auditing có được tạo/cập nhật đúng actor và thời gian không.
3. Repository save có kích hoạt lifecycle nhưng @Modifying, JdbcTemplate hoặc JdbcClient có đi qua lifecycle đó hay không.
4. Nếu một bước ghi thất bại, transaction có rollback các thay đổi liên quan không.

Bài học này trình bày pipeline callback của Spring Data JDBC, cách viết test với @DataJdbcTest, cách cố định AuditorAware và DateTimeProvider, cách kiểm tra auditing bằng dữ liệu đã đọc lại từ database, và cách xác nhận giới hạn của direct SQL.

## 1. Phân biệt callback, event và auditing

Ba khái niệm liên quan nhưng có mục đích khác nhau.

| Cơ chế | Mục đích | Ví dụ |
|---|---|---|
| Entity callback | Can thiệp đồng bộ vào lifecycle của entity | Gán giá trị mặc định trước khi save |
| Lifecycle event | Thông báo một giai đoạn persistence đã xảy ra | Ghi log khi aggregate được lưu |
| Auditing | Điền actor và timestamp vào metadata | @CreatedBy, @LastModifiedDate |

Entity callback có thể trả về entity đã sửa đổi và được gọi theo chuỗi đồng bộ. Lifecycle event thường dùng để thông báo cho listener; nếu ApplicationEventMulticaster được cấu hình với TaskExecutor, việc xử lý event có thể diễn ra bất đồng bộ.

Auditing của Spring Data JDBC được tích hợp qua entity callback. Vì vậy, khi kiểm thử auditing, cần kiểm tra đường repository/template thực sự chạy callback.

## 2. Pipeline callback khi Spring Data JDBC lưu aggregate

Một lần save aggregate có trình tự khái quát:

~~~text
repository.save(aggregate)
          |
          v
Xác định aggregate mới hay đã tồn tại
          |
          v
BeforeConvertCallback / BeforeConvertEvent
          |
          v
Tạo AggregateChange và các DbAction
          |
          v
BeforeSaveCallback / BeforeSaveEvent
          |
          v
Thực thi SQL trên database
          |
          v
AfterSaveCallback / AfterSaveEvent
          |
          v
Trả aggregate đã lưu
~~~

Các callback quan trọng:

| Callback | Thời điểm | Dùng khi |
|---|---|---|
| BeforeConvertCallback | Trước khi aggregate được chuyển thành database change | Chuẩn hóa dữ liệu hoặc tạo ID ứng dụng |
| BeforeSaveCallback | Sau khi đã tạo AggregateChange, trước khi SQL chạy | Kiểm tra hoặc điều chỉnh change plan |
| AfterSaveCallback | Sau khi SQL save aggregate chạy | Quan sát kết quả persistence |
| AfterConvertCallback | Sau khi aggregate được tạo từ ResultSet | Bổ sung dữ liệu sau khi đọc |
| BeforeDeleteCallback | Trước khi xóa aggregate | Kiểm tra hoặc ghi nhận ý định xóa |
| AfterDeleteCallback | Sau khi aggregate bị xóa | Quan sát kết quả xóa |

### 2.1. Chọn callback đúng thời điểm

Nếu cần thay đổi thuộc tính persistent trước khi framework tạo SQL, dùng BeforeConvertCallback.

BeforeSaveCallback được gọi sau khi Spring Data JDBC đã tạo AggregateChange. Nếu thay đổi một thuộc tính persistent của aggregate tại thời điểm này, thay đổi đó có thể không còn được đưa vào các DbAction đã tạo. Callback này phù hợp khi cần thao tác trên MutableAggregateChange, nhưng không phải điểm chung để sửa tùy ý mọi field trước khi mapping.

Nếu chỉ muốn quan sát kết quả sau khi lưu, dùng AfterSaveCallback.

### 2.2. Callback gắn với aggregate root

Spring Data JDBC phát lifecycle callback/event cho aggregate root. Nếu cần xử lý entity con, thường thực hiện thông qua aggregate root hoặc listener nhận aggregate chứa entity con.

Không viết test giả định rằng mỗi OrderLine trong collection sẽ có một lượt AfterSaveCallback riêng như một entity độc lập.

## 3. Viết một callback có thể kiểm thử

Ví dụ callback gán mã xử lý trước khi aggregate được chuyển thành database change:

~~~java
public class OrderReferenceCallback
        implements BeforeConvertCallback<PurchaseOrder> {

    @Override
    public PurchaseOrder onBeforeConvert(PurchaseOrder order) {
        if (order.getReference() == null) {
            order.setReference("ORD-" + order.getIdempotencyKey());
        }

        return order;
    }
}
~~~

Callback có thể được đăng ký thành bean:

~~~java
@Configuration
class OrderCallbackConfiguration {

    @Bean
    OrderReferenceCallback orderReferenceCallback() {
        return new OrderReferenceCallback();
    }
}
~~~

Trong ứng dụng thật, callback nên thực hiện công việc ngắn, xác định và dễ kiểm thử. Tránh gọi HTTP service hoặc gửi message trực tiếp trong callback. Nếu callback chạy trong transaction rồi ném exception, thao tác save có thể rollback; side effect bên ngoài database không tự rollback theo.

### 3.1. Thứ tự nhiều callback

Nếu có nhiều callback cùng loại cho một domain type, thứ tự mặc định không được bảo đảm. Có thể quy định thứ tự bằng @Order hoặc implement Ordered.

~~~java
@Component
@Order(100)
class NormalizeOrderCallback
        implements BeforeConvertCallback<PurchaseOrder> {

    @Override
    public PurchaseOrder onBeforeConvert(PurchaseOrder order) {
        order.normalizeReference();
        return order;
    }
}
~~~

Callback được thực thi tuần tự; kết quả callback trước được truyền cho callback sau. Khi thứ tự có ý nghĩa nghiệp vụ, hãy kiểm thử thứ tự đó thay vì dựa vào thứ tự bean được khởi tạo.

## 4. Kiểm thử callback bằng @DataJdbcTest

Với Spring Boot, @DataJdbcTest là test slice dành cho Spring Data JDBC. Nó tự cấu hình repository, JdbcTemplate và thường dùng embedded database nếu có trên classpath. Test được chạy trong transaction và mặc định rollback khi kết thúc.

Ví dụ:

~~~java
@DataJdbcTest
@Import(OrderCallbackConfiguration.class)
class PurchaseOrderCallbackTest {

    @Autowired
    PurchaseOrderRepository repository;

    @Test
    void appliesReferenceCallbackBeforeInsert() {
        PurchaseOrder order = PurchaseOrder.draft("key-101");

        PurchaseOrder saved = repository.save(order);

        assertThat(saved.getReference()).isEqualTo("ORD-key-101");
    }
}
~~~

Test slice không quét toàn bộ component như một @SpringBootTest. Các callback/configuration riêng thường cần được đưa vào bằng @Import.

Nếu callback là component trong production nhưng test slice không nạp nó, test sẽ không chạy callback. Khi đó lỗi nằm ở cấu hình test, không nhất thiết nằm ở implementation callback.

### 4.1. Kiểm tra cả object và database

Một callback có thể trả về object đã sửa đổi. Để xác nhận giá trị thật sự được ghi, đọc lại aggregate hoặc dùng JdbcTemplate truy vấn trực tiếp:

~~~java
@Test
void persistsCallbackValue() {
    PurchaseOrder order = repository.save(
            PurchaseOrder.draft("key-102")
    );

    String reference = jdbcTemplate.queryForObject(
            "SELECT reference FROM purchase_orders WHERE id = ?",
            String.class,
            order.getId()
    );

    assertThat(reference).isEqualTo("ORD-key-102");
}
~~~

Đọc lại từ database giúp tránh trường hợp test chỉ kiểm tra object trong bộ nhớ mà không chứng minh SQL đã ghi đúng.

## 5. Kiểm thử auditing với actor và thời gian cố định

Auditing thường phụ thuộc vào hai nguồn dữ liệu:

- AuditorAware<T> cung cấp actor hiện tại.
- DateTimeProvider cung cấp thời điểm tạo/sửa.

Nếu test dùng SecurityContext thật hoặc đồng hồ hệ thống, kết quả có thể phụ thuộc môi trường chạy. Nên thay hai nguồn này bằng provider có thể điều khiển trong test.

Ví dụ entity:

~~~java
@Table("audit_orders")
public class AuditOrder {

    @Id
    private Long id;

    private String status;

    @CreatedBy
    @Column("created_by")
    private String createdBy;

    @CreatedDate
    @Column("created_at")
    private Instant createdAt;

    @LastModifiedBy
    @Column("modified_by")
    private String modifiedBy;

    @LastModifiedDate
    @Column("modified_at")
    private Instant modifiedAt;

    public static AuditOrder draft() {
        AuditOrder order = new AuditOrder();
        order.status = "DRAFT";
        return order;
    }

    public void confirm() {
        this.status = "CONFIRMED";
    }

    public Long getId() {
        return id;
    }

    public String getCreatedBy() {
        return createdBy;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public String getModifiedBy() {
        return modifiedBy;
    }

    public Instant getModifiedAt() {
        return modifiedAt;
    }
}
~~~

Cấu hình auditing cho test:

~~~java
@TestConfiguration
@EnableJdbcAuditing(
        auditorAwareRef = "testAuditorAware",
        dateTimeProviderRef = "testDateTimeProvider"
)
class AuditTestConfiguration {

    @Bean
    MutableAuditValues mutableAuditValues() {
        return new MutableAuditValues();
    }

    @Bean
    AuditorAware<String> testAuditorAware(MutableAuditValues values) {
        return () -> Optional.of(values.actor());
    }

    @Bean
    DateTimeProvider testDateTimeProvider(MutableAuditValues values) {
        return () -> Optional.of(values.now());
    }
}
~~~

Provider điều khiển được:

~~~java
public class MutableAuditValues {

    private final AtomicReference<String> actor =
            new AtomicReference<>("user-101");

    private final AtomicReference<Instant> now =
            new AtomicReference<>(
                    Instant.parse("2026-11-13T08:00:00Z")
            );

    public String actor() {
        return actor.get();
    }

    public Instant now() {
        return now.get();
    }

    public void setActor(String value) {
        actor.set(value);
    }

    public void setNow(Instant value) {
        now.set(value);
    }
}
~~~

Trong test, import rõ cấu hình:

~~~java
@DataJdbcTest
@Import({AuditTestConfiguration.class, CallbackTestConfiguration.class})
class AuditOrderRepositoryTest {

    @Autowired
    AuditOrderRepository repository;

    @Autowired
    MutableAuditValues auditValues;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Autowired
    CountingAfterSaveCallback countingCallback;

    @Test
    void recordsCreatorAndLastModifier() {
        AuditOrder order = AuditOrder.draft();

        AuditOrder created = repository.save(order);

        assertThat(created.getCreatedBy()).isEqualTo("user-101");
        assertThat(created.getModifiedBy()).isEqualTo("user-101");
        assertThat(created.getCreatedAt())
                .isEqualTo(Instant.parse("2026-11-13T08:00:00Z"));

        auditValues.setActor("user-202");
        auditValues.setNow(Instant.parse("2026-11-13T09:30:00Z"));

        AuditOrder loaded = repository.findById(created.getId())
                .orElseThrow();

        loaded.confirm();
        repository.save(loaded);

        AuditOrder reloaded = repository.findById(created.getId())
                .orElseThrow();

        assertThat(reloaded.getCreatedBy()).isEqualTo("user-101");
        assertThat(reloaded.getModifiedBy()).isEqualTo("user-202");
        assertThat(reloaded.getCreatedAt())
                .isEqualTo(Instant.parse("2026-11-13T08:00:00Z"));
        assertThat(reloaded.getModifiedAt())
                .isEqualTo(Instant.parse("2026-11-13T09:30:00Z"));
    }
}
~~~

Ví dụ giả định schema test có các cột tương ứng và repository được cấu hình trong test slice.

### 5.1. Vì sao phải đọc lại entity?

Không chỉ assert trên object truyền vào save. Auditing callback có thể trả về một instance đã được bổ sung metadata. Cần kiểm tra object trả về và/hoặc đọc lại database để chứng minh các giá trị đã được persist.

### 5.2. Kiểm tra modify-on-create

@EnableJdbcAuditing có thuộc tính modifyOnCreate. Mặc định, entity có thể được đánh dấu modified ngay lúc tạo.

Nếu nghiệp vụ muốn modifiedBy/modifiedAt chỉ xuất hiện sau lần sửa đầu tiên, hãy cấu hình modifyOnCreate = false và viết test xác nhận hành vi đó. Đừng để test dựa trên mặc định mà không thể hiện rõ chính sách của ứng dụng.

## 6. Đếm callback để xác nhận lifecycle

Một callback ghi nhận số lần được gọi giúp kiểm tra đường save có đi qua lifecycle hay không.

~~~java
public class CountingAfterSaveCallback
        implements AfterSaveCallback<AuditOrder> {

    private final AtomicInteger calls = new AtomicInteger();

    @Override
    public AuditOrder onAfterSave(AuditOrder aggregate) {
        calls.incrementAndGet();
        return aggregate;
    }

    public int calls() {
        return calls.get();
    }
}
~~~

Đăng ký callback trong test:

~~~java
@TestConfiguration
class CallbackTestConfiguration {

    @Bean
    CountingAfterSaveCallback countingAfterSaveCallback() {
        return new CountingAfterSaveCallback();
    }
}
~~~

Test có thể xác nhận:

- Một lần repository save tạo một lần callback cho aggregate root.
- Một lần repository save thứ hai làm bộ đếm tăng thêm.
- Load aggregate không gọi AfterSaveCallback.
- Direct SQL update không làm bộ đếm tăng.

Nếu saveAll lưu nhiều aggregate, callback được gọi cho từng aggregate root được lưu. Không suy ra rằng callback sẽ chạy riêng cho từng child row.

## 7. Lifecycle event và callback không giống nhau

Spring Data JDBC cũng công bố event như BeforeSaveEvent và AfterSaveEvent.

| Tiêu chí | Entity callback | Lifecycle event |
|---|---|---|
| Mục đích chính | Thay đổi hoặc kiểm soát entity trong lifecycle | Thông báo sự kiện cho listener |
| Giá trị trả về | Có thể trả entity đã sửa đổi | Listener không thay thế entity trong persistence pipeline |
| Thứ tự | Có thể điều khiển bằng @Order/Ordered | Phụ thuộc ApplicationEventMulticaster |
| Async | Callback chạy theo pipeline đồng bộ | Có thể async nếu multicaster có TaskExecutor |
| Auditing | Được Spring Data JDBC tích hợp qua callback | Không phải cơ chế auditing chính |

Nếu logic cần chạy trước khi SQL được tạo, ưu tiên callback phù hợp. Nếu chỉ cần gửi thông báo hoặc cập nhật read model sau một sự kiện, listener/event có thể phù hợp hơn.

Không dùng asynchronous event listener để thay thế việc cập nhật metadata cần nằm trong cùng transaction với aggregate.

## 8. Callback chỉ áp dụng cho đường persistence của Spring Data JDBC

Đây là điểm cần kiểm thử rõ khi dự án có nhiều cách ghi dữ liệu.

Các đường ghi sau không tương đương:

~~~text
repository.save(aggregate)
       |
       v
Spring Data JDBC lifecycle
       |
       +-- BeforeConvert
       +-- BeforeSave
       +-- SQL
       +-- AfterSave
       +-- Auditing callback

@Modifying @Query / JdbcTemplate / JdbcClient
       |
       v
SQL trực tiếp
       |
       +-- SQL chạy theo câu lệnh đã viết
       +-- Không tự gọi aggregate lifecycle callback
       +-- Không tự điền auditing metadata
       +-- Không tự áp dụng @Version của aggregate
~~~

Tài liệu Spring Data JDBC nêu rõ các callback/event liên quan đến save/delete không được gọi cho derived query methods hoặc annotated queries, vì framework không có cách hiệu quả để xác định các aggregate bị ảnh hưởng.

SQL qua JdbcTemplate, NamedParameterJdbcTemplate hoặc JdbcClient cũng không đi qua repository/template lifecycle.

## 9. Kiểm thử @Modifying query không gọi callback

Repository:

~~~java
public interface AuditOrderRepository
        extends CrudRepository<AuditOrder, Long> {

    @Modifying
    @Query("""
        UPDATE audit_orders
        SET status = :status
        WHERE id = :id
        """)
    int updateStatusDirectly(
            @Param("id") Long id,
            @Param("status") String status
    );
}
~~~

Test:

~~~java
@Test
void modifyingQueryDoesNotInvokeSaveCallbackOrAuditing() {
    AuditOrder created = repository.save(AuditOrder.draft());
    int callbackCountBefore = countingCallback.calls();

    auditValues.setActor("user-999");
    auditValues.setNow(Instant.parse("2026-11-13T10:00:00Z"));

    int changed = repository.updateStatusDirectly(
            created.getId(),
            "CANCELLED"
    );

    assertThat(changed).isEqualTo(1);
    assertThat(countingCallback.calls()).isEqualTo(callbackCountBefore);

    AuditOrder reloaded = repository.findById(created.getId())
            .orElseThrow();

    assertThat(reloaded.getStatus()).isEqualTo("CANCELLED");

    // Direct SQL không tự cập nhật metadata auditing.
    assertThat(reloaded.getModifiedBy()).isEqualTo("user-101");
    assertThat(reloaded.getModifiedAt())
            .isEqualTo(Instant.parse("2026-11-13T08:00:00Z"));
}
~~~

Test này chứng minh hai điều:

1. Câu UPDATE đã thay đổi dữ liệu.
2. Callback/auditing của repository không tự chạy cho câu annotated query.

Nếu direct query được thiết kế để thay đổi aggregate, ứng dụng phải quyết định cách cập nhật modified_by, modified_at, version và side effect liên quan.

## 10. Kiểm thử JdbcTemplate ghi trực tiếp

Cùng nguyên tắc áp dụng cho JDBC template:

~~~java
@Test
void jdbcTemplateUpdateBypassesAggregateCallbacks() {
    AuditOrder created = repository.save(AuditOrder.draft());
    int callbackCountBefore = countingCallback.calls();

    jdbcTemplate.update(
            """
            UPDATE audit_orders
            SET status = ?
            WHERE id = ?
            """,
            "CANCELLED",
            created.getId()
    );

    assertThat(countingCallback.calls()).isEqualTo(callbackCountBefore);

    AuditOrder reloaded = repository.findById(created.getId())
            .orElseThrow();

    assertThat(reloaded.getStatus()).isEqualTo("CANCELLED");
}
~~~

Khi test repository và JdbcTemplate cùng dùng datasource/transaction manager trong @DataJdbcTest, chúng tham gia cùng transaction test. Test mặc định rollback khi kết thúc.

Nếu production dùng nhiều datasource hoặc transaction manager, test phải cấu hình đúng datasource mà từng adapter thực sự sử dụng.

## 11. Nếu direct SQL cần cập nhật auditing metadata

Có hai cách thường dùng:

- Đưa metadata vào câu SQL.
- Dùng database trigger theo quy ước thống nhất.

Ví dụ cập nhật metadata trực tiếp:

~~~java
int changed = jdbcTemplate.update(
        """
        UPDATE audit_orders
        SET status = ?,
            modified_by = ?,
            modified_at = ?
        WHERE id = ?
        """,
        "CANCELLED",
        actorId,
        clock.instant(),
        orderId
);
~~~

Nếu aggregate có version, câu SQL cần kiểm tra và tăng version:

~~~sql
UPDATE audit_orders
SET status = :status,
    modified_by = :actor,
    modified_at = :modifiedAt,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion;
~~~

Test phải xác nhận:

- Số hàng bị ảnh hưởng đúng.
- Metadata được cập nhật đúng actor/time.
- Version tăng theo chính sách.
- Request dùng version cũ không thể ghi đè thay đổi mới.
- Các bước phụ thuộc cùng rollback nếu một bước thất bại.

Không chỉ assert câu SQL trả về một hàng. Hãy đọc lại dữ liệu và xác nhận toàn bộ metadata/version.

## 12. Kiểm thử auditing cho background job

AuditorAware thường lấy actor từ SecurityContext. Background job, scheduler hoặc message consumer có thể không có SecurityContext của người dùng cuối.

Test cần xác nhận chính sách actor cho từng luồng:

| Luồng | Actor test mong đợi |
|---|---|
| HTTP request có đăng nhập | User ID |
| Scheduled job | Service actor, ví dụ system:archive-job |
| Import từ đối tác | Integration identity |
| Migration | Migration identity |
| Không có actor | Optional.empty, NULL hoặc lỗi theo chính sách |

Không để test chỉ chạy với một user cố định rồi giả định background job sẽ tự có actor đó trong production.

Với async task, security context không nhất thiết tự được truyền sang thread khác. Hãy truyền actor context tường minh hoặc cấu hình context propagation và kiểm thử nó.

## 13. Kiểm thử transaction và rollback

Callback, repository save, auditing metadata và direct SQL có thể cùng tham gia một transaction nếu dùng chung datasource và transaction manager.

Một test transaction có thể kiểm tra:

~~~text
@Transactional test/use case
        |
        +-- repository.save(order)
        |       |
        |       +-- callbacks
        |       +-- auditing metadata
        |
        +-- jdbcTemplate.update(...)
        |
        +-- phát sinh exception
                |
                v
             ROLLBACK
                |
                +-- root không đổi
                +-- direct SQL không còn hiệu lực
                +-- audit row cùng transaction không tồn tại
~~~

Ví dụ:

~~~java
@Transactional
public void saveAndUpdateThenFail(Long orderId) {
    AuditOrder order = repository.findById(orderId)
            .orElseThrow();

    order.confirm();
    repository.save(order);

    jdbcTemplate.update(
            "UPDATE audit_orders SET status = ? WHERE id = ?",
            "ARCHIVED",
            orderId
    );

    throw new IllegalStateException("Force rollback");
}
~~~

Trong integration test, gọi phương thức qua Spring proxy để transaction interceptor hoạt động. Sau khi transaction rollback hoàn tất, mở transaction/đọc mới rồi xác nhận trạng thái database.

Lưu ý: nếu test method bản thân đã được @DataJdbcTest bọc trong transaction, cần hiểu propagation và cách kết thúc transaction khi kiểm tra kết quả commit/rollback độc lập. Không dùng một lần đọc trong cùng transaction chưa kết thúc để kết luận dữ liệu đã rollback ở database.

## 14. Hạn chế của H2 và khi cần database thật

@DataJdbcTest thường dùng embedded database để chạy nhanh. Nó phù hợp để kiểm tra mapping cơ bản, callback và auditing.

Nhưng H2 có thể khác database production về:

- SQL dialect.
- Generated key và sequence.
- Timestamp/timezone conversion.
- JSON/array/custom type.
- Constraint và locking.
- Batch update count.
- Trigger.
- DDL và migration behavior.

Nếu ứng dụng dựa vào hành vi riêng của PostgreSQL, MySQL hoặc SQL Server, hãy thêm integration test chạy trên engine thật, thường qua Testcontainers hoặc database test chuyên dụng.

Ví dụ cấu hình để không thay datasource do test auto-configure:

~~~java
@DataJdbcTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
class PostgreSqlAuditIntegrationTest {
    // Test dùng datasource PostgreSQL đã cấu hình cho test.
}
~~~

Test trên database thật đặc biệt cần thiết khi xác nhận direct SQL, batch, trigger, generated key hoặc locking.

## 15. Kiểm tra callback order và event timing

Khi nhiều callback cùng xử lý một aggregate, có thể dùng @Order hoặc Ordered để định nghĩa thứ tự.

Ví dụ:

~~~java
@Component
@Order(100)
class NormalizeCallback implements BeforeConvertCallback<AuditOrder> {

    @Override
    public AuditOrder onBeforeConvert(AuditOrder order) {
        order.normalizeStatus();
        return order;
    }
}
~~~

~~~java
@Component
@Order(200)
class ValidateCallback implements BeforeConvertCallback<AuditOrder> {

    @Override
    public AuditOrder onBeforeConvert(AuditOrder order) {
        order.validate();
        return order;
    }
}
~~~

Test có thể ghi lại thứ tự gọi trong một list hoặc probe bean, sau đó xác nhận:

~~~text
normalize -> validate -> convert -> before-save -> SQL -> after-save
~~~

Đây là thứ tự khái quát của các điểm trong pipeline, không phải một lời hứa rằng mọi event listener bất đồng bộ sẽ hoàn tất theo cùng thứ tự.

Nếu dùng event listener với TaskExecutor, không kiểm tra thứ tự bằng một list dùng chung mà không đồng bộ hóa. Event có thể được xử lý trên thread khác.

## 16. Những lỗi thường gặp khi kiểm thử

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ kiểm tra object sau save | Không chứng minh dữ liệu đã persist | Đọc lại database |
| Test slice không import callback config | Callback không được đăng ký | Dùng @Import |
| Dùng đồng hồ hệ thống | Test phụ thuộc thời điểm chạy | Cố định DateTimeProvider |
| Không kiểm soát actor | Test có thể nhận actor NULL hoặc môi trường | Cung cấp AuditorAware test |
| Mong callback chạy cho @Modifying | Test kỳ vọng sai lifecycle | Kiểm tra hành vi direct query riêng |
| Mong callback chạy cho JdbcTemplate | SQL trực tiếp không gọi entity lifecycle | Cập nhật metadata trong SQL hoặc dùng repository |
| Kiểm tra callback cho từng child | Callback gắn với aggregate root | Kiểm tra qua root |
| Dùng ApplicationEvent thay callback đồng bộ | Event có thể async và không đảm bảo thứ tự | Dùng EntityCallback cho thay đổi lifecycle |
| Chỉ dùng H2 cho database-specific SQL | Bỏ sót khác biệt dialect/driver | Thêm integration test với database mục tiêu |
| Test rollback trong cùng transaction chưa kết thúc | Đọc kết quả không phản ánh trạng thái sau rollback | Kết thúc transaction rồi đọc bằng transaction mới |
| Không test background actor | Metadata thiếu danh tính ở job | Test service actor và async context |

## 17. Ma trận kiểm thử nên có

| Đường ghi | Callback | Auditing | SQL | Transaction |
|---|---|---|---|---|
| repository.save | Có | Có nếu bật | Framework tạo | Theo transaction Spring |
| JdbcAggregateTemplate.insert/update | Có | Có nếu bật | Framework tạo | Theo transaction Spring |
| repository.saveAll | Có cho từng aggregate root | Có nếu bật | Framework batch-aware | Theo transaction Spring |
| @Modifying @Query | Save/delete callback không chạy | Không tự cập nhật | SQL đã khai báo | Theo transaction repository/caller |
| Derived modifying query | Save/delete callback không chạy | Không tự cập nhật | SQL framework tạo | Theo transaction repository/caller |
| JdbcTemplate.update | Không | Không | SQL trực tiếp | Nếu cùng datasource/manager |
| NamedParameterJdbcTemplate.batchUpdate | Không | Không | JDBC batch trực tiếp | Nếu cùng datasource/manager |
| JdbcClient.update | Không | Không | SQL trực tiếp | Nếu cùng datasource/manager |

Ma trận này giúp xác định test nào cần có cho mỗi đường ghi đang tồn tại trong ứng dụng.

## 18. Quy trình viết test callback, auditing và direct SQL

**Bước 1 — Chọn aggregate đại diện.** Dùng một aggregate có metadata và callback cần kiểm tra.

**Bước 2 — Cấu hình test slice.** Dùng @DataJdbcTest và import rõ auditing/callback configuration.

**Bước 3 — Cố định actor và clock.** Tạo AuditorAware và DateTimeProvider có thể điều khiển.

**Bước 4 — Kiểm tra callback.** Dùng callback probe để xác nhận đúng callback được gọi và đúng thứ tự.

**Bước 5 — Kiểm tra auditing.** Save mới, đổi actor/time, save lần nữa, rồi đọc lại database để xác nhận created fields giữ nguyên và modified fields đổi.

**Bước 6 — Kiểm tra direct query.** Gọi @Modifying hoặc JdbcTemplate và xác nhận callback/auditing không tự chạy.

**Bước 7 — Kiểm tra SQL tự cập nhật metadata.** Nếu direct SQL được thiết kế để ghi audit fields/version, xác nhận các cột được cập nhật đúng.

**Bước 8 — Kiểm tra rollback.** Cho một bước sau thất bại và xác nhận toàn bộ thao tác trong transaction được rollback.

**Bước 9 — Kiểm tra database thật.** Chạy test bổ sung với dialect/driver production khi có SQL đặc thù.

~~~text
@DataJdbcTest + imported test configuration
                  |
                  v
       Fixed AuditorAware + DateTimeProvider
                  |
                  v
             repository.save
                  |
                  +---- callback probe
                  |
                  +---- auditing columns
                  |
                  v
             Read back from DB
                  |
                  v
        Direct @Modifying / JDBC SQL
                  |
                  +---- assert no lifecycle callback
                  +---- assert no automatic auditing
                  |
                  v
         Test explicit metadata update
                  |
                  v
        Test transaction rollback
                  |
                  v
       Repeat on production database
~~~

## 19. Bài tập tự suy luận

**Tình huống A — Callback không chạy**

Một test gọi @Modifying @Query để đổi trạng thái. AfterSaveCallback không được gọi. Đây có phải lỗi framework không?

**Gợi ý:** Không. Derived/annotated query methods không đi qua aggregate save lifecycle nên save/delete callback và event tương ứng không được gọi.

**Tình huống B — createdBy luôn NULL**

Repository save chạy được nhưng createdBy không có giá trị. Cần kiểm tra gì?

**Gợi ý:** Kiểm tra @EnableJdbcAuditing, kiểu generic của AuditorAware, bean có được import vào test context không, và provider có trả actor hay không.

**Tình huống C — modifiedAt không đổi trong test**

Hai lần save xảy ra trong cùng một thời điểm theo clock cố định. Có thể kết luận auditing không hoạt động không?

**Gợi ý:** Không. Dùng DateTimeProvider có thể điều khiển và tăng thời gian rõ ràng giữa hai lần save.

**Tình huống D — Direct SQL cập nhật status**

JdbcTemplate.update đổi status thành công nhưng modifiedBy vẫn giữ giá trị cũ. Vì sao?

**Gợi ý:** Direct SQL không gọi auditing callback. Cần cập nhật metadata trong SQL hoặc chuyển thao tác qua repository/template.

**Tình huống E — Event listener xử lý chậm**

Một AfterSaveEvent listener chạy trên executor riêng. Test kiểm tra list ngay sau repository.save nhưng list chưa có event. Vì sao?

**Gợi ý:** Event có thể được xử lý bất đồng bộ. Nếu cần thay đổi entity đồng bộ, dùng callback; nếu test event async, cần đồng bộ chờ theo cơ chế test rõ ràng.

**Tình huống F — H2 test qua, PostgreSQL lỗi**

Một câu SQL direct update hoạt động trong H2 nhưng lỗi ở PostgreSQL. Cần bổ sung gì?

**Gợi ý:** Integration test trên PostgreSQL thật hoặc Testcontainers để xác nhận dialect, type, lock và driver behavior.

## 20. Ghi nhớ

| Thành phần | Vai trò |
|---|---|
| BeforeConvertCallback | Sửa entity trước khi tạo database change |
| BeforeSaveCallback | Can thiệp sau khi AggregateChange đã được tạo |
| AfterSaveCallback | Xử lý sau khi aggregate được lưu |
| AfterConvertCallback | Xử lý sau khi aggregate được materialize |
| BeforeDeleteCallback / AfterDeleteCallback | Hook trước/sau xóa aggregate |
| Lifecycle event | Thông báo các giai đoạn persistence |
| @EnableJdbcAuditing | Bật auditing cho Spring Data JDBC |
| AuditorAware | Cung cấp actor cho metadata |
| DateTimeProvider | Cung cấp thời gian có thể điều khiển |
| @DataJdbcTest | Test slice cho Spring Data JDBC |
| @Import | Đưa callback/auditing test configuration vào context |
| @Modifying | SQL ghi trực tiếp qua repository, không chạy save/delete callbacks |
| JdbcTemplate / JdbcClient | SQL trực tiếp, không tự đi qua aggregate lifecycle |
| Integration test trên DB thật | Xác nhận dialect, driver, transaction và SQL thực tế |

**Muốn kiểm thử đúng callback và auditing, hãy kiểm tra cả lifecycle lẫn dữ liệu đã ghi trong database.** Repository/template save đi qua callback và auditing; derived/annotated modifying query cùng JDBC trực tiếp không tự kích hoạt save/delete lifecycle. Dùng actor và clock cố định để test xác định, kiểm tra direct SQL như một đường ghi riêng, và xác nhận transaction rollback trên datasource/driver phù hợp.

## Tài liệu tham khảo

- [Spring Data Relational — Lifecycle Events and EntityCallbacks](https://docs.spring.io/spring-data/relational/reference/jdbc/events.html): callback pipeline, lifecycle events, aggregate root scope và giới hạn của derived/annotated query methods.
- [Spring Data Relational — Auditing](https://docs.spring.io/spring-data/relational/reference/jdbc/auditing.html): @EnableJdbcAuditing, actor provider và auditing metadata.
- [Spring Data Relational — BeforeConvertCallback Javadoc](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/mapping/event/BeforeConvertCallback.html): thời điểm và chữ ký callback.
- [Spring Data Relational — BeforeSaveCallback Javadoc](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/mapping/event/BeforeSaveCallback.html): AggregateChange đã được tạo trước khi callback chạy.
- [Spring Data Commons — Entity Callbacks](https://docs.spring.io/spring-data/commons/reference/entity-callbacks.html): đăng ký, ordering và synchronous callback semantics.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): @DataJdbcTest, auto-configuration và transaction rollback mặc định.

