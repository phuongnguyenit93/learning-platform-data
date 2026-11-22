# Giới hạn auditing khi cập nhật trực tiếp bằng SQL

Spring Data R2DBC hỗ trợ auditing để ghi nhận người tạo, thời điểm tạo, người sửa và thời điểm sửa của entity. Cơ chế này hoạt động thông qua metadata auditing và entity callback trong quy trình lưu entity của Spring Data.

Khi ứng dụng cập nhật dữ liệu trực tiếp bằng SQL, ví dụ repository method có @Modifying @Query, DatabaseClient hoặc R2dbcEntityTemplate.update(Query, Update), thao tác thường không đi qua cùng quy trình lưu một entity đầy đủ. Vì vậy, các annotation @LastModifiedDate và @LastModifiedBy không tự động được áp dụng chỉ vì câu SQL đã thay đổi hàng.

Nếu câu SQL không cập nhật các cột audit và database không có trigger xử lý chúng, dữ liệu nghiệp vụ có thể đổi nhưng last_modified_at và last_modified_by vẫn giữ giá trị cũ. Muốn audit nhất quán, hãy cập nhật audit columns tường minh trong câu SQL, dùng database trigger có quy ước rõ ràng, hoặc chuyển thao tác về đường lưu entity khi phù hợp.

## 1. Auditing trong Spring Data R2DBC hoạt động như thế nào?

Auditing ghi lại thông tin vòng đời của entity. Các annotation thường dùng:

| Annotation | Ý nghĩa |
| --- | --- |
| @CreatedDate | Thời điểm entity được tạo |
| @CreatedBy | Người hoặc actor tạo entity |
| @LastModifiedDate | Thời điểm entity được sửa gần nhất |
| @LastModifiedBy | Người hoặc actor sửa entity gần nhất |

Ví dụ entity:

~~~java
@Table("customers")
public class Customer {

    @Id
    private Long id;

    private String name;
    private String status;

    @CreatedDate
    @Column("created_at")
    private Instant createdAt;

    @CreatedBy
    @Column("created_by")
    private String createdBy;

    @LastModifiedDate
    @Column("last_modified_at")
    private Instant lastModifiedAt;

    @LastModifiedBy
    @Column("last_modified_by")
    private String lastModifiedBy;

    // Constructor, getter và setter được lược bớt.
}
~~~

Khi entity được lưu qua đường xử lý entity của Spring Data R2DBC, auditing callback có thể điền các trường tương ứng:

- Khi tạo entity mới, createdAt và createdBy được thiết lập; lastModifiedAt và lastModifiedBy cũng thường được thiết lập cho lần ghi đầu tiên.
- Khi cập nhật entity đã tồn tại, các trường last-modified được cập nhật.
- Các trường created biểu diễn thời điểm và actor tạo ban đầu, nên không bị thay đổi trong một lần sửa thông thường.

Các giá trị cụ thể phụ thuộc cấu hình auditing, kiểu entity, callback và phiên bản Spring Data đang dùng.

### 1.1. Bật R2DBC auditing

Khai báo cấu hình:

~~~java
@Configuration
@EnableR2dbcAuditing(
        auditorAwareRef = "auditorAware",
        dateTimeProviderRef = "dateTimeProvider"
)
public class R2dbcAuditingConfiguration {

    @Bean
    ReactiveAuditorAware<String> auditorAware() {
        return () -> ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .filter(Authentication::isAuthenticated)
                .map(Authentication::getName);
    }

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider dateTimeProvider(Clock clock) {
        return () -> Optional.of(Instant.now(clock));
    }
}
~~~

ReactiveAuditorAware<T> cho phép lấy actor hiện tại bằng một publisher reactive. Trong ví dụ, actor được lấy từ reactive security context. Nếu ứng dụng không dùng Spring Security, có thể triển khai provider từ request context, message context hoặc một nguồn actor khác.

DateTimeProvider cung cấp thời gian cho auditing. Inject Clock giúp ứng dụng thống nhất nguồn thời gian và dễ kiểm thử.

Các import quan trọng:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.domain.ReactiveAuditorAware;
import org.springframework.data.r2dbc.config.EnableR2dbcAuditing;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
~~~

Trong code thực tế, cần xử lý rõ trường hợp không có authentication. Có thể trả Mono.empty() nếu actor không xác định, dùng actor hệ thống cho job nền, hoặc từ chối thao tác nếu nghiệp vụ bắt buộc phải có người thực hiện. Không nên lấy createdBy/lastModifiedBy trực tiếp từ body do client gửi mà không xác thực.

### 1.2. Auditing được gọi qua entity callback

Spring Data Relational tích hợp auditing với entity callback. Auditing callback thường chạy trước khi entity được chuyển đổi thành dữ liệu lưu trữ, đọc metadata annotation và điền các property tương ứng.

Điểm quan trọng là callback cần một entity đi qua quy trình lưu có hỗ trợ callback. Annotation trên class chỉ mô tả metadata; chúng không phải trigger của database và không tự giám sát mọi câu lệnh SQL chạy trên bảng.

Vì vậy, cần phân biệt:

- Lưu một entity qua repository hoặc entity-oriented template operation: Spring Data có entity để chạy mapping và callback.
- Cập nhật một tập cột bằng SQL hoặc query/update builder: ứng dụng chỉ cung cấp câu lệnh và tham số, không có entity đầy đủ để auditing callback cập nhật.

## 2. Vì sao cập nhật trực tiếp bằng SQL không tự chạy auditing?

Hãy xem một modifying query:

~~~java
@Modifying
@Query("UPDATE customers SET status = :status WHERE id = :id")
Mono<Integer> updateStatus(
        @Param("id") Long id,
        @Param("status") String status);
~~~

Method này gửi một câu SQL update tới database và nhận số hàng bị tác động. Spring Data không cần tạo một Customer đầy đủ để thực hiện câu lệnh. Do đó, không có entity tương ứng được đưa qua auditing callback để điền @LastModifiedDate hoặc @LastModifiedBy.

Nếu bảng có các cột:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    created_by VARCHAR(120),
    last_modified_at TIMESTAMP,
    last_modified_by VARCHAR(120)
);
~~~

Thì câu update phía trên chỉ thay đổi status. Hai cột last_modified_at và last_modified_by không tự đổi chỉ vì entity class có annotation tương ứng.

### 2.1. Các đường ghi thường không tự kích hoạt entity auditing

| Cách ghi | Có entity đầy đủ đi qua auditing callback? | Hành vi audit |
| --- | --- | --- |
| Repository save(entity) | Có, qua quy trình lưu entity | Auditing có thể điền các trường được cấu hình |
| Entity-oriented insert/save qua template | Có entity và đi qua mapping/callback tương ứng | Auditing có thể được áp dụng |
| Repository @Modifying @Query | Không | Phải cập nhật audit columns rõ ràng hoặc dùng trigger |
| DatabaseClient.sql(...).fetch() | Không | Phải cập nhật audit columns rõ ràng hoặc dùng trigger |
| R2dbcEntityTemplate.update(Query, Update) | Không có entity cần audit trong thao tác partial update | Phải thêm audit fields vào Update hoặc dùng trigger |
| SQL chạy trực tiếp ngoài ứng dụng | Không đi qua Spring Data callback | Chỉ database-side auditing mới có thể áp dụng đồng nhất |

Bảng này mô tả khác biệt giữa lưu entity và lệnh DML trực tiếp. Hãy kiểm tra API cụ thể trong phiên bản Spring Data R2DBC của dự án nếu đang dùng một overload đặc biệt có nhận entity.

### 2.2. @Modifying không có nghĩa là auditing tự động

@Modifying đánh dấu repository query là câu lệnh thay đổi dữ liệu như UPDATE hoặc DELETE. Annotation này không yêu cầu Spring Data tải entity, không tự gọi ReactiveAuditorAware và không tự thêm last_modified_at vào SQL.

Ví dụ:

~~~java
@Modifying
@Query("""
       UPDATE customers
       SET status = :status
       WHERE id = :id
       """)
Mono<Integer> updateStatus(
        @Param("id") Long id,
        @Param("status") String status);
~~~

Muốn ghi audit, câu lệnh cần được mở rộng:

~~~java
@Modifying
@Query("""
       UPDATE customers
       SET status = :status,
           last_modified_at = :modifiedAt,
           last_modified_by = :modifiedBy
       WHERE id = :id
       """)
Mono<Integer> updateStatusAndAudit(
        @Param("id") Long id,
        @Param("status") String status,
        @Param("modifiedAt") Instant modifiedAt,
        @Param("modifiedBy") String modifiedBy);
~~~

### 2.3. DatabaseClient cũng không tự biết actor hiện tại

DatabaseClient thực thi SQL trực tiếp:

~~~java
databaseClient.sql("""
        UPDATE customers
        SET status = :status
        WHERE id = :id
        """)
        .bind("status", status)
        .bind("id", id)
        .fetch()
        .rowsUpdated();
~~~

API này không có entity để đọc @LastModifiedBy hoặc @LastModifiedDate. Nếu dùng DatabaseClient, ứng dụng phải truyền các giá trị audit vào câu SQL hoặc dựa vào trigger ở database.

## 3. Cách 1: cập nhật audit columns ngay trong SQL

Đây là cách trực tiếp và dễ nhìn thấy nhất. Mọi câu update cần audit đều đưa các cột audit vào phần SET.

~~~sql
UPDATE customers
SET status = :status,
    last_modified_at = :modifiedAt,
    last_modified_by = :modifiedBy
WHERE id = :id;
~~~

Ưu điểm:

- Câu SQL thể hiện đầy đủ dữ liệu nghiệp vụ và audit được thay đổi.
- Không phụ thuộc callback entity.
- Dễ kiểm tra trong code review và integration test.
- Có thể dùng cùng một thời điểm/actor cho toàn bộ batch update.

Nhược điểm:

- Mỗi query ghi phải nhớ cập nhật audit columns.
- Các service hoặc repository khác nhau có thể quên một trường.
- Cần có quy ước chung về actor, timezone và thời điểm.
- Nếu có nhiều ứng dụng ghi cùng bảng, từng ứng dụng phải tuân thủ cùng hợp đồng hoặc dùng cơ chế database-side.

### 3.1. Lấy actor từ reactive security context

Trong ứng dụng WebFlux, không nên dùng SecurityContextHolder.getContext() theo kiểu thread-local để lấy principal trong một pipeline reactive. Hãy dùng ReactiveSecurityContextHolder hoặc nguồn context reactive tương ứng.

~~~java
public Mono<Void> changeStatus(Long customerId, String status) {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Authentication::isAuthenticated)
            .map(Authentication::getName)
            .switchIfEmpty(Mono.error(
                    new IllegalStateException("No authenticated auditor")))
            .flatMap(actor -> {
                Instant now = clock.instant();
                return customerRepository.updateStatusAndAudit(
                        customerId, status, now, actor);
            })
            .flatMap(rows -> {
                if (rows == 0) {
                    return Mono.error(new CustomerNotFoundException(customerId));
                }
                if (rows != 1) {
                    return Mono.error(new IllegalStateException(
                            "Expected one customer to be updated"));
                }
                return Mono.empty();
            });
}
~~~

Ví dụ giả định id là khóa duy nhất và clock là Clock được inject. Instant được bind vào kiểu cột tương thích với driver/database. Nếu schema dùng TIMESTAMP WITHOUT TIME ZONE, TIMESTAMP WITH TIME ZONE hoặc kiểu thời gian khác, hãy chọn kiểu Java và converter phù hợp.

### 3.2. Tái sử dụng ReactiveAuditorAware

Nếu ứng dụng đã có bean ReactiveAuditorAware<String> cho entity auditing, có thể inject cùng provider vào service để lấy actor cho direct SQL:

~~~java
public Mono<Void> changeStatus(Long customerId, String status) {
    return auditorAware.getCurrentAuditor()
            .switchIfEmpty(Mono.error(
                    new IllegalStateException("Auditor is required")))
            .flatMap(actor -> customerRepository.updateStatusAndAudit(
                    customerId,
                    status,
                    clock.instant(),
                    actor))
            .flatMap(this::requireOneUpdatedRow);
}
~~~

Việc tái sử dụng provider giúp repository save và direct SQL dùng cùng một nguồn actor. Tuy nhiên, ReactiveAuditorAware không tự chạy trong modifying query; service chủ động gọi nó và truyền kết quả vào câu SQL.

### 3.3. Dùng actor hệ thống cho job nền

Một scheduled job hoặc message consumer có thể không có HTTP authentication context. Hãy xác định actor theo nguồn xử lý:

- system:reconciliation cho job đối soát.
- system:expiry-worker cho job hết hạn.
- Service identity đã xác thực cho message consumer.

Không dùng một giá trị chung chung nếu cần truy vết loại tác vụ. Actor hệ thống nên được tạo từ cấu hình/identity tin cậy, không lấy từ payload không được xác thực.

### 3.4. Tạo timestamp một lần cho một thao tác

Nếu một request cập nhật nhiều hàng, thường nên tạo một timestamp trước khi thực thi query và dùng cùng giá trị cho toàn bộ hàng:

~~~java
Instant modifiedAt = clock.instant();

return repository.updateManyStatuses(
        ids, status, modifiedAt, actor);
~~~

Điều này giúp các hàng trong cùng một thao tác có cùng mốc thời gian audit. Nếu nghiệp vụ cần thời gian riêng cho từng hàng, hãy xác định rõ quy tắc và để database hoặc câu lệnh tạo giá trị tương ứng.

## 4. Cách 2: cập nhật audit với R2dbcEntityTemplate

R2dbcEntityTemplate.update(Query, Update) cho phép cập nhật một số property mà không tải entity đầy đủ. Vì không có entity được lưu qua callback auditing, hãy thêm các property audit vào Update.

~~~java
public Mono<Long> updateCustomerStatus(
        Long customerId,
        String status,
        String actor) {

    Update changes = Update.update("status", status)
            .set("lastModifiedAt", clock.instant())
            .set("lastModifiedBy", actor);

    Query condition = query(where("id").is(customerId));

    return template.update(Customer.class)
            .matching(condition)
            .apply(changes);
}
~~~

Ở đây status, lastModifiedAt và lastModifiedBy là property name trong entity. Mapping metadata chuyển chúng sang tên cột database tương ứng.

Nếu entity khai báo:

~~~java
@LastModifiedDate
@Column("last_modified_at")
private Instant lastModifiedAt;
~~~

thì trong Update dùng lastModifiedAt, không cần hard-code tên cột vật lý last_modified_at.

### 4.1. Giữ điều kiện update chặt chẽ

Audit không thay thế kiểm tra quyền hoặc điều kiện nghiệp vụ. Với ứng dụng multi-tenant, hãy thêm tenant vào predicate:

~~~java
Query condition = query(
        where("id").is(customerId)
                .and("tenantId").is(tenantId)
);
~~~

tenantId phải đến từ security context đã xác thực. Không tin tenant ID do client gửi trong body.

### 4.2. Kiểm tra số hàng được cập nhật

apply() trả về Mono<Long> chứa số hàng database báo đã cập nhật:

~~~java
return template.update(Customer.class)
        .matching(query(where("id").is(customerId)))
        .apply(changes)
        .flatMap(rows -> {
            if (rows == 0) {
                return Mono.error(new CustomerNotFoundException(customerId));
            }
            if (rows != 1) {
                return Mono.error(new IllegalStateException(
                        "Unexpected number of updated rows: " + rows));
            }
            return Mono.just(rows);
        });
~~~

Nếu update dùng predicate theo trạng thái hoặc tenant, số hàng bằng 0 có thể biểu thị không tồn tại, không thuộc tenant, hoặc không còn thỏa điều kiện. Hãy chuyển thành lỗi nghiệp vụ phù hợp thay vì luôn báo not found nếu cần phân biệt các trường hợp.

## 5. Cách 3: dùng trigger ở database

Nếu nhiều ứng dụng hoặc công cụ khác nhau cùng ghi một bảng, việc yêu cầu từng nơi tự cập nhật audit columns có thể không đủ tin cậy. Database trigger có thể tự cập nhật last_modified_at khi hàng bị update, bất kể lệnh đến từ Spring Data, SQL script hay một ứng dụng khác.

Ví dụ khái niệm:

~~~sql
-- Pseudocode: cú pháp trigger phụ thuộc hệ quản trị database.
BEFORE UPDATE ON customers
FOR EACH ROW
BEGIN
    NEW.last_modified_at = CURRENT_TIMESTAMP;
END;
~~~

Trigger có thể đảm bảo thời gian sửa được ghi ở database. Tuy nhiên, actor sửa là ai vẫn cần được truyền tới database theo một cơ chế đáng tin cậy.

### 5.1. Thời gian do database quản lý

Trigger có thể dùng CURRENT_TIMESTAMP hoặc hàm thời gian tương ứng để thống nhất nguồn thời gian cho tất cả writer. Cần xác định semantics của hàm thời gian: thời gian bắt đầu transaction, thời gian statement hay đồng hồ thực tại thời điểm gọi có thể khác nhau giữa database.

### 5.2. Actor cần được truyền tường minh

Database thường không tự biết principal HTTP hoặc người dùng ứng dụng. Có thể truyền actor bằng:

- Cột last_modified_by trong câu SQL.
- Session variable hoặc transaction-local setting của database.
- Database role/service identity nếu chỉ cần biết ứng dụng nào ghi.
- Trigger tra cứu actor từ một context đã được xác thực.

Không nên suy ra người dùng cuối từ database login chung của connection pool nếu mọi request dùng cùng một service account.

### 5.3. Ví dụ PostgreSQL với transaction-local setting

PostgreSQL hỗ trợ set_config với tham số is_local = true, để thiết lập giá trị chỉ có hiệu lực trong transaction hiện tại. Có thể đặt actor trước câu update:

~~~sql
SELECT set_config('app.actor_id', :actor, true);

UPDATE customers
SET status = :status
WHERE id = :id;
~~~

Trigger PostgreSQL có thể đọc context:

~~~sql
NEW.last_modified_by := current_setting('app.actor_id', true);
NEW.last_modified_at := CURRENT_TIMESTAMP;
~~~

Đây là ví dụ đặc thù PostgreSQL, không phải SQL portable. Cả lệnh set_config và câu update phải chạy trong cùng transaction/connection để setting transaction-local còn hiệu lực. Reactive transaction manager cần bảo đảm các thao tác dùng cùng connection được bind vào transaction.

Với connection pool, tránh dùng session setting tồn tại lâu mà không reset; giá trị actor của request trước có thể rò sang request sau nếu dùng sai phạm vi. Transaction-local setting giảm rủi ro đó, nhưng vẫn cần test với pool và transaction manager thực tế.

### 5.4. Trigger và cập nhật audit ở ứng dụng không nên tranh quyền

Nếu trigger luôn ghi last_modified_at, giá trị timestamp do ứng dụng bind có thể bị trigger ghi đè. Nếu cả ứng dụng và trigger đều cập nhật last_modified_by, kết quả cuối phụ thuộc thứ tự trigger và câu SQL.

Hãy chọn một nguồn có thẩm quyền cho từng trường:

- Database trigger quản lý thời gian, ứng dụng truyền actor.
- Ứng dụng quản lý cả thời gian và actor.
- Database quản lý cả thời gian và actor từ transaction context.

Ghi rõ hợp đồng trong schema và tài liệu vận hành để mọi writer hiểu cùng một quy tắc.

## 6. Bulk update và giới hạn của auditing entity

Một bulk update có thể thay đổi hàng trăm hoặc hàng nghìn bản ghi bằng một câu lệnh:

~~~sql
UPDATE customers
SET status = 'INACTIVE'
WHERE last_login_at < :cutoff;
~~~

Không có một entity riêng được tải và lưu cho từng hàng. Do đó, auditing callback của entity không tự chạy một lần cho mỗi bản ghi.

Nếu cần audit:

~~~sql
UPDATE customers
SET status = 'INACTIVE',
    last_modified_at = :modifiedAt,
    last_modified_by = :actor
WHERE last_login_at < :cutoff;
~~~

Một timestamp và actor có thể đại diện cho toàn bộ batch. Nếu cần lịch sử chi tiết cho từng hàng, hãy thiết kế bảng audit/event riêng hoặc trigger ghi lịch sử.

### 6.1. Không cố tải hàng nghìn entity chỉ để chạy auditing callback

Một cách làm là tìm tất cả entity, sửa từng entity rồi gọi save cho từng phần tử. Cách này có thể tạo nhiều round trip, tăng memory pressure và làm batch chậm.

Nếu nghiệp vụ chỉ thay đổi một trạng thái đồng nhất theo predicate, một bulk update có audit columns rõ ràng thường phù hợp hơn. Nếu mỗi entity cần quy tắc domain riêng, cần xử lý theo batch có giới hạn và cân nhắc transaction size.

### 6.2. Bulk update có thể bỏ qua optimistic locking của entity

Một câu SQL update trực tiếp không tự động áp dụng @Version như entity save. Nếu cần optimistic locking cho bulk update, hãy đưa version hoặc predicate phù hợp vào câu lệnh, hoặc thiết kế update có điều kiện và kiểm tra số hàng bị tác động.

Ví dụ:

~~~sql
UPDATE customers
SET status = :newStatus,
    version = version + 1,
    last_modified_at = :modifiedAt,
    last_modified_by = :actor
WHERE id = :id
  AND version = :expectedVersion;
~~~

Nếu số hàng cập nhật là 0, bản ghi có thể không tồn tại hoặc version đã thay đổi. Câu lệnh tự tăng version trong cùng thao tác giúp kiểm tra và ghi diễn ra nguyên tử.

## 7. Auditing không đồng nghĩa với lịch sử thay đổi đầy đủ

Các trường createdBy, createdAt, lastModifiedBy và lastModifiedAt cho biết ai tạo và ai sửa gần nhất. Chúng không lưu lại toàn bộ giá trị cũ, giá trị mới hoặc mọi lần thay đổi.

Ví dụ:

| Thời điểm | Actor | Thay đổi |
| --- | --- | --- |
| 09:00 | user-10 | Tạo customer, status = NEW |
| 09:15 | user-22 | Đổi status thành ACTIVE |
| 10:30 | system:sync | Đổi email |

Sau lần cuối, các cột last-modified chỉ còn system:sync và thời gian 10:30. Không thể biết từ các cột đó rằng trước đó user-22 đã đổi status thành ACTIVE.

Nếu cần lịch sử đầy đủ, hãy dùng audit table, event log, CDC hoặc cơ chế versioning phù hợp. Direct SQL update cần được thiết kế để ghi lịch sử theo cùng transaction nếu yêu cầu không được mất event.

### 7.1. Audit table

Ví dụ schema:

~~~sql
CREATE TABLE customer_audit (
    audit_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    action VARCHAR(30) NOT NULL,
    changed_at TIMESTAMP NOT NULL,
    changed_by VARCHAR(120),
    old_status VARCHAR(30),
    new_status VARCHAR(30)
);
~~~

Service có thể update customer rồi insert audit row trong cùng transaction. Nếu một bước thất bại, cả hai rollback:

~~~java
@Transactional
public Mono<Void> changeStatus(
        Long customerId,
        String newStatus,
        String actor) {

    Instant now = clock.instant();

    return customerRepository.updateStatusAndAudit(
                    customerId, newStatus, now, actor)
            .flatMap(rows -> {
                if (rows != 1) {
                    return Mono.error(new CustomerNotFoundException(customerId));
                }

                return customerAuditRepository.insertStatusChange(
                        customerId, now, actor, newStatus);
            })
            .then();
}
~~~

Ví dụ rút gọn không hiển thị việc đọc trạng thái cũ. Nếu audit cần old value chính xác, hãy thiết kế câu lệnh hoặc trigger để lấy old/new từ cùng thao tác update, tránh đọc trước rồi ghi audit sau trong một transaction có isolation không đủ mạnh.

## 8. Chọn cách ghi audit phù hợp

| Tình huống | Cách tiếp cận nên cân nhắc |
| --- | --- |
| CRUD entity thông thường qua repository save | Spring Data auditing callback |
| Một modifying query cập nhật một số cột | Thêm last_modified_at và last_modified_by vào SQL |
| Partial update qua R2dbcEntityTemplate | Thêm audit property vào Update |
| Nhiều ứng dụng/SQL tool cùng ghi một bảng | Database trigger hoặc quy ước chung ở database |
| Bulk update theo predicate | Ghi audit columns trong câu lệnh hoặc trigger |
| Cần lịch sử old/new cho mọi thay đổi | Audit table, trigger history, event log hoặc CDC |
| Job nền không có HTTP principal | Actor hệ thống rõ ràng |
| Cần optimistic locking trong direct SQL | Thêm version predicate và tăng version nguyên tử |

Không có lựa chọn duy nhất cho mọi hệ thống. Nếu chỉ có một ứng dụng Spring Data ghi dữ liệu, cập nhật audit columns trong service/repository có thể đủ rõ. Nếu có nhiều writer độc lập, database trigger giúp giảm nguy cơ một writer quên cập nhật audit.

## 9. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| lastModifiedAt không đổi sau @Modifying @Query | Modifying query không đi qua auditing entity callback | Thêm audit column vào SQL hoặc dùng trigger |
| lastModifiedBy luôn null | Direct SQL không gọi auditor provider | Lấy actor reactive và bind vào query |
| createdAt bị đổi khi update | Câu SQL hoặc trigger ghi nhầm trường created | Chỉ cập nhật trường last-modified trên update |
| Entity save có audit nhưng bulk update không có | Hai đường ghi có cơ chế khác nhau | Thiết lập quy ước audit cho cả hai đường |
| Actor bị gán thành anonymous | Auditor provider chấp nhận anonymous authentication | Lọc principal và quy định actor fallback |
| Job nền không có actor | Không có SecurityContext của HTTP | Dùng system actor có tên rõ ràng |
| Timestamp lệch múi giờ | Java/database dùng kiểu thời gian hoặc timezone không thống nhất | Chọn Instant/UTC và mapping/schema phù hợp |
| Một số writer quên audit | Audit chỉ được cập nhật thủ công ở từng service | Dùng helper chung, trigger hoặc kiểm thử database |
| Trigger ghi đè timestamp từ ứng dụng | Hai nguồn cùng quản lý một cột | Chỉ định nguồn có thẩm quyền |
| Audit table không khớp dữ liệu chính | Update và insert history không cùng transaction | Gộp trong transaction hoặc dùng trigger |
| Bulk update bỏ qua version | SQL trực tiếp không tự áp dụng @Version | Thêm version predicate/increment rõ ràng |

## 10. Kiểm thử giới hạn auditing khi cập nhật trực tiếp

Nên kiểm thử với database R2DBC thực tế hoặc Testcontainers. Unit test chỉ mock repository không xác nhận auditing callback có chạy hay SQL thực sự cập nhật audit columns.

### 10.1. Kiểm thử repository save có auditing

Với entity có @CreatedDate, @CreatedBy, @LastModifiedDate và @LastModifiedBy, tạo entity qua repository:

~~~java
StepVerifier.create(customerRepository.save(new Customer("Lan", "NEW")))
        .assertNext(saved -> {
            assertThat(saved.getCreatedAt()).isNotNull();
            assertThat(saved.getCreatedBy()).isEqualTo("test-user");
            assertThat(saved.getLastModifiedAt()).isNotNull();
            assertThat(saved.getLastModifiedBy()).isEqualTo("test-user");
        })
        .verifyComplete();
~~~

Test cần cấu hình auditor test xác định, chẳng hạn ReactiveAuditorAware trả Mono.just("test-user"), và cấu hình clock cố định để assertion thời gian ổn định.

### 10.2. Kiểm thử modifying query không tự audit

Tạo một hàng có last_modified_at và last_modified_by xác định, sau đó gọi modifying query chỉ cập nhật status:

~~~java
StepVerifier.create(customerRepository.updateStatus(id, "ACTIVE"))
        .expectNext(1)
        .verifyComplete();
~~~

Đọc lại hàng và xác nhận các cột last-modified vẫn giữ nguyên. Test này làm rõ giới hạn: auditing annotation không tự bổ sung cột vào câu SQL.

### 10.3. Kiểm thử modifying query có audit tường minh

Gọi method update có nhận modifiedAt và modifiedBy. Đọc lại hàng và xác nhận:

- status có giá trị mới.
- last_modified_at bằng timestamp đã truyền.
- last_modified_by bằng actor đã truyền.
- created_at và created_by vẫn giữ giá trị ban đầu.

### 10.4. Kiểm thử database trigger

Nếu dùng trigger, kiểm thử cả repository save, repository @Modifying @Query, DatabaseClient, bulk update, SQL được chạy ngoài ứng dụng trong môi trường test và actor context không rò giữa hai connection được tái sử dụng từ pool.

### 10.5. Kiểm thử reactive auditor context

Kiểm tra actor lấy đúng từ reactive security context trong pipeline WebFlux. Không chỉ test bằng thread-local hoặc gọi service từ một thread test thông thường, vì cách đó có thể che lỗi mất context khi đổi scheduler.

## 11. Quy trình triển khai auditing nhất quán

1. Xác định bảng và cột audit cần quản lý.
2. Phân biệt metadata entity với quy tắc thực sự ở database.
3. Bật @EnableR2dbcAuditing và cấu hình ReactiveAuditorAware cho đường lưu entity.
4. Liệt kê mọi đường ghi: repository save, modifying query, template update, DatabaseClient, batch job và SQL ngoài ứng dụng.
5. Với direct SQL, thêm audit columns hoặc thiết lập database trigger.
6. Chọn nguồn có thẩm quyền cho actor và timestamp.
7. Không thay đổi created_at/created_by trong update thông thường.
8. Nếu cần lịch sử đầy đủ, ghi audit event/table trong cùng transaction hoặc dùng cơ chế CDC phù hợp.
9. Nếu direct SQL cần optimistic locking, đưa version vào predicate và tăng version trong cùng câu lệnh.
10. Viết integration test cho từng đường ghi và kiểm tra các cột audit thực tế.

## 12. Luồng lựa chọn cơ chế audit

~~~mermaid
flowchart TD
    A[Ứng dụng cần ghi dữ liệu] --> B{Có lưu một entity qua Spring Data?}
    B -->|Có| C[Auditing entity callback]
    B -->|Không, direct SQL hoặc partial update| D{Có thể sửa câu SQL?}
    D -->|Có| E[Bind last_modified_at và last_modified_by]
    D -->|Không hoặc có nhiều writer| F[Database trigger]
    C --> G{Cần lịch sử old/new?}
    E --> G
    F --> G
    G -->|Có| H[Audit table, event log hoặc CDC]
    G -->|Không| I[Giữ created và last-modified metadata]
~~~

## 13. Kết luận

Spring Data R2DBC auditing dựa trên metadata entity và callback trong quy trình lưu entity. Các annotation @CreatedDate, @CreatedBy, @LastModifiedDate và @LastModifiedBy không tự giám sát mọi câu SQL chạy trên database.

Khi dùng @Modifying @Query, DatabaseClient hoặc R2dbcEntityTemplate.update(Query, Update), hãy cập nhật audit columns tường minh hoặc dùng trigger ở database. Lấy actor từ reactive context hoặc identity hệ thống đáng tin cậy, dùng một nguồn thời gian nhất quán, giữ nguyên các trường created khi update và kiểm tra số hàng bị tác động. Nếu cần lịch sử đầy đủ old/new, thiết kế audit table hoặc event log riêng vì last-modified fields chỉ lưu trạng thái sửa gần nhất.

Hãy kiểm thử riêng từng đường ghi. Một entity save có auditing thành công không chứng minh rằng bulk update hoặc native SQL cũng tự ghi audit. Quy ước rõ ràng giữa Spring Data callback, direct SQL và database trigger giúp dữ liệu audit nhất quán dù ứng dụng có nhiều cách cập nhật cùng một bảng.
