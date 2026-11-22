# Giới hạn auditing với bulk DML và cập nhật ngoài JPA

## 1. Vấn đề cần hiểu

Trong Spring Data JPA, auditing thường tự điền thông tin **ai tạo/sửa** và **khi nào tạo/sửa** entity thông qua `@CreatedBy`, `@CreatedDate`, `@LastModifiedBy` và `@LastModifiedDate`. Cơ chế này gắn với vòng đời entity do JPA quản lý, thường thông qua `AuditingEntityListener` và các sự kiện như `@PrePersist`, `@PreUpdate`.

**Giới hạn cốt lõi:** Khi thực hiện *bulk DML* (một lệnh `UPDATE`/`DELETE` tác động trực tiếp lên tập bản ghi) hoặc cập nhật database bằng con đường ngoài vòng đời JPA, **không có bảo đảm rằng auditing listener sẽ chạy cho từng entity**. Vì vậy, chỉ khai báo các annotation auditing không đủ để mọi thay đổi đều có dấu vết chính xác.

Ví dụ: một bản ghi có `updated_at = 10:00`, `updated_by = "alice"`. Lúc 11:00, công việc nền chạy `UPDATE account SET locked = true WHERE ...`. Giá trị `locked` thay đổi, nhưng nếu câu lệnh không tự cập nhật hai cột audit thì chúng vẫn có thể ghi 10:00 và "alice". Người đọc dữ liệu có thể tưởng thay đổi gần nhất do Alice thực hiện.

Phân biệt hai khái niệm:
- **Audit metadata:** các cột `created_at`, `created_by`, `updated_at`, `updated_by` chỉ phản ánh trạng thái metadata hiện tại; chúng không phải lịch sử đầy đủ.
- **Audit trail/history:** nhật ký bất biến hoặc các bản ghi phiên bản ghi nhận lần thay đổi, trạng thái trước/sau, tác nhân và thời điểm; cần thiết kế riêng nếu yêu cầu truy vết nhiều lần thay đổi.

## 2. Khi nào auditing tự động chạy và khi nào bị bỏ qua?

| Cách thay đổi dữ liệu | Entity lifecycle/auditing | Điều cần lưu ý |
| --- | --- | --- |
| Nạp entity bằng `findById`, sửa thuộc tính, để dirty checking phát sinh `UPDATE` khi flush | Thông thường **có** `@PreUpdate` và Spring Data JPA auditing, nếu đã cấu hình | Nếu thực tế không có thay đổi cần update, callback có thể không chạy |
| `save` / `saveAll` với entity thông qua hoạt động `persist`/`merge` | Theo vòng đời entity bình thường | `saveAll` không đồng nghĩa với một bulk JPQL `UPDATE`; JDBC batching chỉ tối ưu cách gửi SQL |
| `@Modifying @Query("update ...")`, `EntityManager.createQuery(...).executeUpdate()` | **Không chạy callback cho từng entity** | Phải tự đặt audit fields cần thiết |
| JPQL `DELETE`, `CriteriaUpdate` / `CriteriaDelete` | **Không chạy callback cho từng entity** | Cẩn thận với `@PreRemove`, quan hệ và cache |
| `@Query(nativeQuery = true)` cập nhật trực tiếp, `JdbcTemplate`, SQL migration/script, stored procedure, hệ thống khác ghi DB | **Không đi qua auditing listener của JPA** | Dùng audit column do SQL/DB bảo đảm và xác định tác nhân |
| `deleteAllInBatch(...)` của `JpaRepository` | Không phát JPA lifecycle events cho từng entity | Javadoc cũng lưu ý không tuân theo cascade semantics của JPA |
| Trigger trong database | Không kích hoạt listener JPA; trigger có cơ chế riêng | Trigger có thể ghi timestamp/audit table nếu được thiết kế đúng |

Một khác biệt dễ nhầm: **bulk DML** là câu lệnh cập nhật/xóa trực tiếp theo tập bản ghi; **JDBC batching** có thể gom nhiều câu lệnh SQL phát sinh từ các thay đổi entity bình thường để tối ưu hiệu năng. Không thể suy luận rằng mọi thao tác có chữ "batch" đều bỏ qua auditing.

## 3. Ba hệ quả kỹ thuật của bulk DML

### 3.1. Các cột audit không được điền tự động

Các annotation `@LastModifiedDate` và `@LastModifiedBy` chỉ phát huy khi auditing infrastructure nhận được sự kiện entity phù hợp. Một câu JPQL như sau không tự thêm `updated_at`/`updated_by`:

```java
@Modifying
@Query("update CustomerAccount a set a.locked = true where a.id = :id")
int lockWithoutAudit(@Param("id") Long id);
```

Giả sử listener đã được bật đầy đủ, lệnh trên vẫn chỉ cập nhật `locked` như đã khai báo. Với SQL chạy từ bên ngoài ứng dụng, `AuditorAware` cũng không được gọi: nó không thể tự suy ra user của một lệnh database độc lập.

### 3.2. `@Version` và optimistic locking không tự được áp dụng

Theo Jakarta Persistence, bulk `UPDATE`/`DELETE` đi thẳng tới database, **bỏ qua optimistic-lock checks** của thao tác entity. Provider không tự bảo đảm `where version = ...` hoặc tăng `version` cho bulk DML. Với entity có `@Version`, câu bulk update không cập nhật version có thể khiến dữ liệu và cơ chế phát hiện ghi đè xung đột mất nhất quán.

Nếu cần kiểm tra cạnh tranh trên một bản ghi, hãy tự đưa điều kiện version vào `WHERE`, tăng version trong `SET` và kiểm tra số bản ghi bị tác động. Nếu `UPDATE` trả về `0` hàng, không mặc định báo thành công: có thể id không tồn tại hoặc dữ liệu đã bị sửa bởi giao dịch khác. Cơ chế này **do ứng dụng tự triển khai**; nó không tự biến `0` thành một `OptimisticLockException`.

Khi cập nhật hàng loạt theo điều kiện rộng, việc chỉ tăng version của mỗi hàng vẫn **không tương đương** kiểm tra expected version cho từng hàng. Chọn chiến lược cạnh tranh phù hợp với nghiệp vụ và transaction isolation.

### 3.3. Persistence context có thể giữ dữ liệu cũ

Ví dụ trong cùng một transaction:
1. `EntityManager` đã nạp `CustomerAccount#42` vào first-level cache với `locked=false`.
2. Bulk `UPDATE` sửa hàng #42 thành `locked=true` trong database.
3. Tham chiếu entity đã nạp có thể vẫn báo `locked=false`; bulk DML **không đồng bộ** persistence context.

Spring Data JPA cung cấp `@Modifying(flushAutomatically = true, clearAutomatically = true)`:
- `flushAutomatically=true`: flush các thay đổi đang chờ **trước** khi chạy modifying query.
- `clearAutomatically=true`: clear persistence context **sau** khi chạy query, làm các entity cũ trở thành detached; cần **truy vấn lại** để có dữ liệu mới. Nó không làm cho auditing listener chạy.

`clear()` có thể làm mất các thay đổi chưa flush và tách cả những entity không liên quan; hãy sử dụng trong transaction đã được thiết kế cho bulk operation. Với SQL viết ngoài JPA, cần chủ động `refresh`/`clear`/nạp lại vào thời điểm phù hợp. Nếu dùng second-level cache, phải xem xét chiến lược vô hiệu hóa cache theo provider; writer bên ngoài thường không báo cho ORM biết.

## 4. Ví dụ Spring Data JPA: cập nhật có audit và version tường minh

Các đoạn sau là những file minh họa để đặt trong **ứng dụng Spring Boot đã có Spring Data JPA, driver database và cấu hình datasource**; chúng không phải chương trình Java độc lập chạy chỉ với `javac`. Ví dụ dùng Java 17+, `jakarta.persistence` và cách đánh dấu audit thường gặp.

**`CustomerAccount.java`** — một entity có audit metadata và version:

```java
package example.audit;

import jakarta.persistence.*;
import java.time.Instant;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

@Entity
@EntityListeners(AuditingEntityListener.class)
public class CustomerAccount {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private Long version;

    private boolean locked;

    @CreatedDate
    @Column(name = "created_at", updatable = false)
    private Instant createdAt;

    @LastModifiedDate
    @Column(name = "updated_at")
    private Instant updatedAt;

    @LastModifiedBy
    @Column(name = "updated_by")
    private String updatedBy;

    protected CustomerAccount() {}

    public void lock() {
        this.locked = true;
    }
}
```

**`AuditConfig.java`** — bật auditing. Bean trong ví dụ trả về danh tính hệ thống; ứng dụng thật nên lấy user/service identity đã được xác thực, đồng thời quy định identity cho job nền:

```java
package example.audit;

import java.util.Optional;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

@Configuration
@EnableJpaAuditing
class AuditConfig {
    @Bean
    AuditorAware<String> auditorAware() {
        return () -> Optional.of("system-job");
    }
}
```

Trong đường đi **entity thông thường**, lấy entity rồi gọi `account.lock()` bên trong transaction. Nếu từ `false` sang `true`, dirty checking sẽ tạo lệnh cập nhật và auditing listener có cơ hội điền `updatedAt`/`updatedBy` khi flush. `@CreatedDate` được xử lý lúc tạo entity, không phải mỗi lần cập nhật.

**`CustomerAccountRepository.java`** — cách viết bulk DML có chủ ý cập nhật đủ dữ liệu audit và version:

```java
package example.audit;

import java.time.Instant;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface CustomerAccountRepository
        extends JpaRepository<CustomerAccount, Long> {

    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
        update CustomerAccount a
           set a.locked = true,
               a.updatedAt = :changedAt,
               a.updatedBy = :actor,
               a.version = a.version + 1
         where a.id = :id
           and a.version = :expectedVersion
        """)
    int lockWithAudit(
            @Param("id") Long id,
            @Param("expectedVersion") Long expectedVersion,
            @Param("changedAt") Instant changedAt,
            @Param("actor") String actor);
}
```

**`CustomerAccountService.java`** — kiểm tra kết quả trong transaction:

```java
package example.audit;

import java.time.Instant;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerAccountService {
    private final CustomerAccountRepository repository;

    public CustomerAccountService(CustomerAccountRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void lock(Long id, Long expectedVersion, String trustedActor) {
        int affected = repository.lockWithAudit(
                id, expectedVersion, Instant.now(), trustedActor);

        if (affected != 1) {
            throw new IllegalStateException(
                    "Bản ghi không tồn tại hoặc phiên bản đã thay đổi");
        }
    }
}
```

Giải thích:
- `@Modifying` hướng dẫn Spring Data chạy `@Query` như lệnh thay đổi dữ liệu; annotation này **không tự thực hiện auditing**.
- `:changedAt` và `:actor` được truyền rõ ràng; dùng timestamp/identity nhất quán trong toàn bộ hệ thống. `trustedActor` phải do tầng xác thực hoặc job context đáng tin cậy cung cấp, không lấy nguyên giá trị từ request của client.
- `a.version = a.version + 1` thích hợp khi version có kiểu số như `Long`. Với chiến lược version khác, cần cách xử lý tương ứng.
- `where a.version = :expectedVersion` cộng với `affected == 1` là cách kiểm tra xung đột cho **một** record. Lỗi của ví dụ được ném bằng `IllegalStateException` để minh họa; ứng dụng có thể chuyển thành lỗi xung đột nghiệp vụ/HTTP 409.
- Sau khi `clearAutomatically` chạy, tránh đọc lại trạng thái từ biến entity cũ; gọi repository truy vấn lại nếu cần giá trị mới.

Không nên chép nguyên mẫu vào một lệnh cập nhật hàng triệu bản ghi nếu chưa quyết định transaction size, isolation, lock contention, index lọc và cách xác định actor. Bulk update nhanh hơn trong nhiều trường hợp, nhưng đổi lại phải quản lý rõ những quy tắc lifecycle bị bỏ qua.

## 5. Khi một tiến trình ngoài JPA ghi dữ liệu

Một SQL job, `JdbcTemplate`, script migration hay dịch vụ khác ghi cùng bảng có thể đặt metadata tường minh. Ví dụ SQL sau dùng **named parameters do tầng truy cập DB bind** (điều chỉnh cú pháp theo database):

```sql
UPDATE customer_account
   SET locked = TRUE,
       updated_at = CURRENT_TIMESTAMP,
       updated_by = :actor,
       version = version + 1
 WHERE id = :id
   AND version = :expectedVersion;
```

Cần kiểm tra số hàng được cập nhật và rollback khi điều kiện nghiệp vụ không đạt. Khi đồng thời có writer JPA và writer ngoài JPA, thống nhất:
1. **Chủ sở hữu timestamp:** dùng clock của ứng dụng với kiểu `Instant` và UTC, hoặc thời gian của database (`CURRENT_TIMESTAMP`). Nếu phối hợp hai nguồn, kiểm tra độ lệch clock, timezone và precision.
2. **Nguồn actor:** user xác thực, service account hoặc tên job; lưu một quy ước định danh nhất quán. Database không tự biết người dùng ứng dụng nếu tác nhân đó không được truyền qua.
3. **Quy tắc version/concurrency:** mọi writer phải đồng ý có kiểm tra/tăng version hay không. Writer ngoài JPA quên tăng version sẽ làm mất tín hiệu xung đột cho phiên làm việc đang quản lý entity.
4. **Transaction và trạng thái đọc lại:** cột nghiệp vụ và audit nên được cập nhật nguyên tử trong cùng transaction; flush/clear/reload khi quay về ORM, đồng thời xử lý cache nếu cần.
5. **Quy tắc xóa:** hard delete xóa luôn metadata trên hàng. Nếu phải biết ai xóa và giá trị trước khi xóa, cần soft delete, audit table hoặc cơ chế ghi nhận thay đổi phù hợp.

### Có nên dùng trigger database?

**Có thể**, khi nhiều ứng dụng/ETL viết cùng dữ liệu và cần database bảo đảm `updated_at` hoặc ghi audit table. Trigger chạy cả khi thay đổi phát sinh ngoài JPA, nhưng cần xem xét thứ tự trigger, giao dịch, hiệu năng và cách truyền identity. Trigger biết `CURRENT_USER` của database chưa chắc biết user đăng nhập ứng dụng. Nếu code ứng dụng và trigger cùng ghi `updated_at`, cần chỉ định nguồn nào có quyền quyết định để tránh kết quả bất ngờ.

**CDC (Change Data Capture)** có thể quan sát thay đổi đã commit phục vụ đồng bộ hoặc xây dựng lịch sử, nhưng không tự khôi phục identity, lý do thay đổi hay các giá trị không được lưu/phát ra. Nếu cần audit trail có giá trị truy vết, xác định rõ schema sự kiện và độ tin cậy của pipeline.

## 6. Chọn chiến lược theo yêu cầu

| Nhu cầu | Phương án | Đổi lại |
| --- | --- | --- |
| Cần `@PreUpdate`, entity validation, cascade, auditing và nghiệp vụ theo từng bản ghi | Tải entity, thay đổi trạng thái trong transaction; cân nhắc JDBC batching và xử lý theo lô có giới hạn | Nhiều entity/SQL, cần quản lý bộ nhớ và flush |
| Cần đổi trạng thái nhiều bản ghi với chi phí thấp, không cần callback trên từng entity | Bulk JPQL/Criteria/SQL **đi kèm cập nhật audit fields, version và chính sách cache rõ ràng** | Tự chịu trách nhiệm audit/concurrency/business rule |
| Nhiều writer, kể cả bên ngoài Java | Database-managed timestamp/trigger/stored procedure hoặc hợp đồng SQL bắt buộc | Cần quy ước actor, migration, vận hành và kiểm thử ở DB |
| Cần biết **mọi lần** thay đổi, trước/sau và tác nhân | Audit table, event/outbox hoặc CDC được thiết kế đúng | Lưu trữ, tính nhất quán và khả năng truy vấn lịch sử phức tạp hơn |

`@LastModifiedDate` không thay thế hệ thống lưu lịch sử; một giá trị ngày sửa cuối không trả lời được "đã sửa những trường nào qua các lần".

## 7. Kiểm thử tích hợp và lỗi phổ biến

Kiểm thử với **database thực tế tương thích môi trường triển khai**, transaction thật và đọc lại bằng persistence context mới hoặc đã `clear`. Đừng chỉ assert lên entity còn nằm trong first-level cache.

Các tình huống cần bao phủ:
1. **Entity path:** cập nhật một entity do JPA quản lý làm `updated_at`/`updated_by` thay đổi và `version` tăng; nếu entity không dirty, không giả định callback luôn được gọi.
2. **Bulk path thiếu audit (kiểm chứng giới hạn):** chạy `@Modifying` chỉ thay trường nghiệp vụ; đọc lại DB cho thấy audit fields không tự thay đổi.
3. **Bulk path đầy đủ:** chạy `lockWithAudit` với đúng version; kết quả `1` hàng, trạng thái/audit/version đều phù hợp.
4. **Phiên bản cũ:** gọi với `expectedVersion` không còn khớp; kết quả `0` và service báo xung đột, không silently overwrite.
5. **Persistence context:** nạp entity trước khi bulk update, chứng minh dữ liệu cũ còn có thể tồn tại trong object; xác nhận việc nạp lại sau `clear` nhận dữ liệu mới.
6. **Writer ngoài JPA:** kiểm thử script/job và trigger (nếu có) để chắc chắn timestamp, actor, version và transaction đúng; kiểm tra cả rollback.
7. **Bulk delete:** xác minh hành vi cascade, ràng buộc khóa ngoại và yêu cầu lưu lịch sử xóa; không trông đợi `@PreRemove` khi xóa bằng bulk query.

Các sai lầm thường gặp:
- Nghĩ rằng `@EnableJpaAuditing` khiến **mọi** câu `UPDATE` trong DB tự cập nhật metadata.
- Nghĩ `@Modifying` tự gọi `@PreUpdate` hoặc `AuditorAware`.
- Chỉ thêm `clearAutomatically=true` để "sửa auditing"; thực tế nó giải quyết trạng thái cache, không tự ghi audit.
- Tăng `version` nhưng không kiểm tra số hàng hoặc không xác định concurrency policy; ngược lại, quên tăng version trên bulk update.
- Dùng `saveAll` và bulk DML như hai thuật ngữ đồng nghĩa; quyết định sai về lifecycle/performance.
- Dùng client-supplied `updated_by` làm nguồn tin cậy hoặc không định danh job nền.
- Chỉ kiểm tra entity đang managed thay vì đọc dữ liệu database sau bulk operation.

## 8. Ghi nhớ

**Auditing tự động của Spring Data JPA phụ thuộc vòng đời entity.** Bulk JPQL/Criteria DML và cập nhật bên ngoài JPA không tự thực hiện entity callbacks, audit-field population, optimistic-lock checks hay đồng bộ first-level cache. Khi lựa chọn các đường ghi trực tiếp, hãy thiết kế tường minh **audit fields + actor/time + version/concurrency + transaction + cache/readback**. Khi cần lịch sử mọi thay đổi, bổ sung cơ chế audit trail thực sự.

### Tài liệu chính thức

- [Spring Data JPA — Auditing](https://docs.spring.io/spring-data/jpa/reference/auditing.html)
- [Spring Data JPA — `@Modifying` API](https://docs.spring.io/spring-data/data-jpa/reference/api/java/org/springframework/data/jpa/repository/Modifying.html)
- [Jakarta Persistence 3.2 — Bulk Update and Delete Operations](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html)
- [Spring Data JPA — `JpaRepository.deleteAllInBatch` API](https://docs.spring.io/spring-data/jpa/reference/api/java/org/springframework/data/jpa/repository/JpaRepository.html)
