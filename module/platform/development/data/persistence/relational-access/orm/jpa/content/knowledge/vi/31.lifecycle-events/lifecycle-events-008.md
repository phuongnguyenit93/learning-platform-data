# Quản lý trường thời gian và dấu vết thay đổi theo cách có thể kiểm thử

> **Chủ đề:** Data Persistence Relational Access ORM JPA  
> **Chương:** Sự kiện vòng đời

Một ứng dụng lưu trữ dữ liệu bằng JPA thường cần biết **bản ghi được tạo khi nào, thay đổi lần cuối khi nào, ai tạo và ai sửa**. Những trường như `createdAt`, `updatedAt`, `createdBy` và `updatedBy` tưởng chừng chỉ cần gọi `Instant.now()` trong `@PrePersist` hoặc `@PreUpdate`. Tuy nhiên, một hệ thống thực tế phải giải quyết nhiều vấn đề hơn:

- Đồng hồ trong ứng dụng có thể khác đồng hồ database; test không nên phụ thuộc thời gian thật.
- Callback có thể chạy ở thời điểm `flush()`, **không phải thời điểm commit thành công**.
- `@PreUpdate` không có nghĩa “mọi lần gọi repository.save()”; nó gắn với một hoạt động UPDATE thực tế theo lifecycle của provider.
- JPQL bulk update, native SQL, triggers và writers bên ngoài có thể **bỏ qua callback JPA**.
- Security principal có thể không tồn tại trong scheduled job hoặc asynchronous worker.
- Hai giao dịch cập nhật cùng entity cần cơ chế concurrency control; `updatedAt` không thay thế `@Version`.
- Một cặp “người sửa cuối/thời điểm sửa cuối” **không phải toàn bộ lịch sử thay đổi**, và callback “sau UPDATE” cũng **không phải sau COMMIT**.
- Muốn kiểm thử chính xác, cần một nguồn thời gian có thể thay thế (`Clock`), một nguồn actor có hợp đồng rõ ràng và phép thử persistence thật có `flush`/`clear`.

Bài học này xây dựng một chiến lược audit có thể kiểm thử ở cả mức unit và integration: xác định semantics trước, chọn nơi gán dấu vết phù hợp, tách thời gian và người dùng ra khỏi static global state, rồi chứng minh hành vi qua transaction và database.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Định nghĩa chính xác các trường `createdAt`, `updatedAt`, `createdBy` và `updatedBy`.
2. Phân biệt **last-modified metadata**, **optimistic version**, **audit event/history** và **business event**.
3. Giải thích lifecycle callbacks `@PrePersist`, `@PreUpdate`, `@PostPersist`, `@PostUpdate`, `@PostLoad` và giới hạn của chúng.
4. Biết khi nào `@PreUpdate` có thể không chạy vì entity không có thay đổi dẫn tới UPDATE.
5. Dùng `java.time.Clock` thay cho gọi trực tiếp `Instant.now()` trong logic cần test.
6. Tách nguồn actor qua một interface để test không phụ thuộc SecurityContext thật.
7. Triển khai entity và service gán audit metadata **theo một thời điểm cố định trong test**.
8. Viết unit test không dùng `Thread.sleep()` hay khoảng thời gian phỏng đoán.
9. Viết integration test với `EntityManager.flush()` và `clear()` để quan sát state persisted.
10. Kiểm thử create, update, no-op, rollback, bulk update và concurrency conflict.
11. Dùng `@Column(updatable=false)` phù hợp cho các trường chỉ tạo một lần, đồng thời hiểu giới hạn của mapping.
12. Hiểu `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy`, `@LastModifiedBy` của Spring Data JPA auditing.
13. Cung cấp `DateTimeProvider`/`AuditorAware` có thể kiểm thử khi sử dụng Spring Data auditing.
14. Phân biệt thời điểm do ứng dụng sinh với thời điểm do database default/trigger sinh.
15. Lựa chọn `Instant`, `OffsetDateTime`, `LocalDateTime`, loại cột SQL và độ chính xác phù hợp.
16. Hiểu vì sao transaction rollback không được để lại audit event như một thay đổi đã commit.
17. Biết khi nào cần audit history table, Hibernate Envers, CDC hoặc transactional outbox.
18. Thiết kế test matrix đủ để phát hiện lỗi “timestamp đúng trên object nhưng sai trong DB”.
19. Bảo vệ tenant identity, user ID và thông tin nhạy cảm trong metadata.
20. Ghi lại giới hạn của giải pháp khi có native SQL, migration hoặc external writers.

## 2. Bắt đầu từ ý nghĩa nghiệp vụ, không bắt đầu từ annotation

Từ “thời gian thay đổi” có thể chỉ nhiều mốc khác nhau:

| Trường/mốc | Câu hỏi | Mức bảo đảm nên định nghĩa |
|---|---|---|
| `createdAt` | Bản ghi được tạo ở hệ thống vào lúc nào? | Thường một lần, không sửa |
| `updatedAt` | Lần ghi nghiệp vụ cuối được ghi nhận là lúc nào? | Thay đổi khi có update theo policy |
| `createdBy` | Actor nào tạo bản ghi? | Actor ID/nguồn tạo có thể audit |
| `updatedBy` | Actor nào thực hiện thay đổi cuối? | Cần update cùng updatedAt |
| `version` | Bản ghi đã qua bao nhiêu lần cập nhật có kiểm soát optimistic concurrency? | Dùng `@Version`/lock contract |
| `deletedAt` | Bản ghi được soft-delete khi nào? | Chỉ khi dùng soft delete |
| `effectiveAt` | Nghiệp vụ xem thay đổi có hiệu lực từ lúc nào? | Có thể khác thời điểm ghi |
| `committedAt` | Giao dịch commit thành công lúc nào? | Không thể suy chính xác bằng `@PreUpdate` |
| Audit event timestamp | Sự kiện thay đổi được ghi nhận khi nào? | Phụ thuộc chính sách event/history |

Một hệ thống có thể cần một số trường này, nhưng chúng **không thay thế nhau**.

### 2.1. Một ví dụ dễ nhầm

Người dùng nhấn “Lưu” lúc 10:00:00.000. Service kiểm tra dữ liệu trong 300 ms, gán `updatedAt` lúc 10:00:00.300, transaction chờ khóa thêm 500 ms và commit lúc 10:00:00.800.

Trong trường hợp đó:

```text
Action received:     10:00:00.000
Application stamped: 10:00:00.300
Database flush:      10:00:00.600
Commit completed:    10:00:00.800
```

Nếu trường mang tên `updatedAt` theo hợp đồng “thời điểm ứng dụng chấp nhận thay đổi” thì 10:00:00.300 có thể hợp lý. Nếu hợp đồng yêu cầu **commit timestamp chính xác**, gọi `Clock.instant()` hoặc `@PreUpdate` không đáp ứng yêu cầu ấy.

### 2.2. Audit metadata tối thiểu không phải lịch sử đầy đủ

Một row:

```text
Document#42
  createdAt = ...
  createdBy = "user-17"
  updatedAt = ...
  updatedBy = "user-93"
```

không trả lời:

- Ai sửa ở lần thứ hai?
- Giá trị cũ của title là gì?
- Vì sao thay đổi?
- Những lần sửa nào bị rollback?
- Có UPDATE ngoài ORM xảy ra không?

Để trả lời, cần một **audit history** có từng revision/event, không chỉ bốn cột trên entity.

---

## 3. Một nguyên tắc thiết kế: chọn nguồn chân lý

Trước khi viết code, quyết định **ai chịu trách nhiệm sinh timestamp và actor**.

Các lựa chọn phổ biến:

1. **Application service:** service lấy `Clock` và current actor, gán lên entity khi nghiệp vụ thay đổi.
2. **JPA lifecycle callback/entity listener:** callback gán trước INSERT/UPDATE theo lifecycle event.
3. **Spring Data JPA Auditing:** listener do Spring Data cung cấp, hỗ trợ nguồn thời gian và actor.
4. **Database default/trigger:** database gán timestamp, kể cả với những writers không đi qua ORM nếu mọi write path tuân thủ schema/trigger.
5. **Hybrid có chủ đích:** ví dụ application gán `createdBy`, database gán `updatedAt`, hoặc service vừa ghi metadata vừa ghi revision/outbox.

Không có lựa chọn duy nhất đúng cho mọi hệ thống. Mỗi lựa chọn có điểm mạnh/giới hạn.

| Tiêu chí | Service + Clock | JPA callback | Spring Data Auditing | DB trigger |
|---|---|---|---|---|
| Test thời gian bằng fake Clock | Rất thuận tiện | Cần thiết kế dependency injection riêng | Có thể qua DateTimeProvider | Cần kiểm soát DB time/test DB |
| Tự chạy khi entity dirty flush | Phải gán ở write path | Có | Có với lifecycle integration | Có khi DB UPDATE |
| Có current actor | Truyền qua abstraction | Không có sẵn portable | AuditorAware | Cần session context/app truyền |
| Áp dụng với JPQL bulk update | Không nếu không viết riêng | Không | Không | Có nếu trigger phù hợp |
| Áp dụng với JDBC/external writer | Không | Không | Không | Có nếu cùng DB/trigger |
| Dễ kiểm tra đơn vị (unit test) | Cao | Trung bình | Có thể, cần cấu hình | Thấp hơn, cần integration DB |
| Khả năng ghi full history | Có thể kết hợp | Không tự đủ | Không tự đủ | Có thể, nhưng thêm độ phức tạp |
| Phụ thuộc framework | JPA thuần + Clock | JPA thuần | Spring Data JPA | DBMS-specific |

Trong bài, ví dụ chính dùng **service + injected Clock**, sau đó đối chiếu với callbacks/Spring Data/database. Đây là cách minh họa rõ nhất tiêu chí **có thể kiểm thử** mà không cần giả định injection magic vào entity.

---

## 4. Các sự kiện vòng đời JPA liên quan

Jakarta Persistence hỗ trợ callbacks ở entity hoặc entity listener.

| Callback | Bối cảnh | Dùng cho audit? |
|---|---|---|
| `@PrePersist` | Trước khi INSERT entity mới, theo lifecycle của provider | Có thể gán createdAt/createdBy |
| `@PostPersist` | Sau thao tác INSERT tương ứng | Không phải after commit |
| `@PreUpdate` | Trước khi UPDATE entity được thực thi theo lifecycle | Có thể gán updatedAt/updatedBy |
| `@PostUpdate` | Sau UPDATE tương ứng | Không chứng minh transaction đã commit |
| `@PreRemove` | Trước DELETE entity qua lifecycle | Có thể chuẩn bị logic, nhưng không tự lưu lịch sử bền vững |
| `@PostRemove` | Sau DELETE tương ứng | Không phải after commit |
| `@PostLoad` | Sau khi entity được nạp | Thường dùng logic nội bộ, không nên gán audit modification |
| `@PrePersist` + `@PreUpdate` | Có thể gắn nhiều callback type cho method theo khai báo hợp lệ | Nên tách logic để tránh thay createdAt khi update |

### 4.1. Các callback chỉ phản ánh một phần write paths

Ví dụ:

```java
entityManager.persist(document);
entityManager.flush();
```

có thể kích hoạt `@PrePersist` trước SQL INSERT.

Khi sửa managed entity:

```java
Document document = entityManager.find(Document.class, id);
document.rename(...);
entityManager.flush();
```

provider có thể kích hoạt `@PreUpdate` trước SQL UPDATE.

Nhưng câu lệnh:

```java
entityManager.createQuery(
    "UPDATE Document d SET d.title = :title WHERE d.id = :id")
    .setParameter("title", "Bulk")
    .setParameter("id", id)
    .executeUpdate();
```

là **bulk JPQL DML**, không thực hiện lifecycle callbacks cho từng entity như thay đổi state managed entity.

### 4.2. Callback không đồng nghĩa commit

Một đường đi:

```text
Service method
   |
   v
em.persist / mutate managed entity
   |
   v
flush
   |
   +-- @PrePersist / @PreUpdate
   |
   +-- SQL INSERT / UPDATE
   |
   +-- @PostPersist / @PostUpdate
   |
   v
... transaction còn đang mở ...
   |
   +-- COMMIT thành công
   |
   hoặc
   +-- ROLLBACK
```

`@PostUpdate` đã chạy **không có nghĩa thay đổi được commit**. Một constraint, deadlock hoặc lỗi hệ thống ở giai đoạn sau vẫn có thể khiến transaction rollback.

---

## 5. @PrePersist: gán thời điểm tạo

Một implementation tối giản:

```java
@Entity
public class Note {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, updatable = false)
    private Instant createdAt;

    @Column(nullable = false)
    private Instant updatedAt;

    @PrePersist
    void beforeInsert() {
        Instant now = Instant.now();
        createdAt = now;
        updatedAt = now;
    }
}
```

Đoạn code này cho thấy cơ chế lifecycle callback nhưng **không phải lựa chọn tối ưu cho deterministic testing**: method tự gọi `Instant.now()` (system clock) và test khó gán chính xác mốc thời gian.

### 5.1. Ý định đúng của createdAt

Thông thường:

- Gán **một lần** khi tạo.
- Không cho API request tự sửa lại tùy tiện.
- Không cập nhật trong `@PreUpdate`.
- Không dựa vào ID được sinh trước khi `@PrePersist`; thời điểm sinh key phụ thuộc strategy/provider.

### 5.2. Tại sao createdAt và updatedAt thường bằng nhau khi tạo?

Nếu contract định nghĩa `updatedAt` là “thời điểm tạo hoặc sửa cuối”, thì một bản ghi vừa tạo có:

```text
createdAt = 2026-11-15T03:00:00Z
updatedAt = 2026-11-15T03:00:00Z
```

Nên lấy **một** giá trị `now` rồi gán cả hai, thay vì gọi đồng hồ hai lần:

```java
createdAt = clock.instant();
updatedAt = clock.instant();
```

Hai lần gọi có thể lệch nanosecond và khiến test/analytics có sai khác vô nghĩa. Với một thao tác tạo, dùng **cùng một Instant** giúp contract rõ hơn.

### 5.3. Trường createdBy

Nếu metadata yêu cầu actor, `@PrePersist` thuần JPA không tự cung cấp username. Phải đưa actor vào ở nơi có security context hoặc cấu hình listener với dependency injection được môi trường hỗ trợ.

Đừng viết:

```java
createdBy = System.getProperty("user.name");
```

để đại diện người dùng nghiệp vụ: đó thường là user của tiến trình OS, không phải người đang thao tác.

---

## 6. @PreUpdate: gán thời điểm sửa

Ví dụ:

```java
@PreUpdate
void beforeUpdate() {
    updatedAt = Instant.now();
}
```

Đây là một callback thông dụng, nhưng cần hiểu rõ:

1. Nó không nhất thiết chạy tại lúc gọi setter.
2. Nó liên quan hoạt động UPDATE entity do provider thực thi.
3. Nó có thể chạy khi `flush()` tự động diễn ra trước query hoặc commit.
4. Một entity không bị thay đổi theo dirty checking có thể không có UPDATE và không gọi callback.
5. Nó không chạy cho từng hàng bị tác động bởi bulk JPQL update.
6. Nếu thay đổi chỉ ảnh hưởng quan hệ/collection ở bảng khác, callback UPDATE của owner entity không mặc nhiên phải chạy.
7. Việc provider phát UPDATE vì lý do riêng và thời điểm gọi callback cần xác nhận qua integration test trên stack thật.

### 6.1. Không nên hiểu save() là đồng nghĩa @PreUpdate

Trong Spring Data JPA, `save(entity)` có thể dẫn tới persist hoặc merge tùy trạng thái entity. Với managed entity, dirty checking và flush quyết định các SQL cần phát. Không phải “gọi save” là một event thay đổi dữ liệu đã commit.

### 6.2. Test no-op cần rõ contract

Giả sử:

```java
document.rename("Draft");
document.rename("Draft");
```

Nếu lần thứ hai không thay đổi dữ liệu, một yêu cầu hợp lý là **updatedAt không đổi**. Nhưng nếu ứng dụng có policy “mỗi request save đều ghi lại modifiedAt”, điều đó lại là một contract khác. Không áp mọi hệ thống cùng một kết luận.

Trong bài chọn contract: **updatedAt chỉ thay đổi khi một sửa đổi nghiệp vụ thực sự được chấp nhận**.

### 6.3. Không tự đặt updatedAt trong @PostUpdate

Nếu chỉ gán `updatedAt` sau SQL UPDATE, thay đổi field mới có thể chưa nằm trong UPDATE vừa thực hiện; sẽ cần flush tiếp hoặc dẫn tới trạng thái không nhất quán. Vì vậy nếu dùng callback cho column được update, `@PreUpdate` là lựa chọn thông thường hơn `@PostUpdate`.

---

## 7. Vì sao nên tiêm Clock thay vì dùng thời gian thật?

`java.time.Clock` là abstraction chuẩn JDK:

```java
Clock clock = Clock.systemUTC();
Instant now = clock.instant();
```

Trong test, có thể dùng:

```java
Clock clock = Clock.fixed(
    Instant.parse("2026-11-15T09:30:00Z"),
    ZoneOffset.UTC
);
```

Bất kỳ lần gọi `clock.instant()` nào đều trả đúng mốc đã chọn.

### 7.1. Lợi ích cho kiểm thử

- So sánh `assertEquals(expectedInstant, actualInstant)` chính xác.
- Không phải dùng `Thread.sleep()` để chờ đồng hồ chạy.
- Không phụ thuộc tốc độ máy CI hoặc scheduling.
- Có thể tái hiện tình huống timestamp trước/sau.
- Có thể thử clock skew, leap/timezone presentation rules.
- Test nhanh, không có khoảng sleep dài.
- Ghi rõ giả định UTC của ứng dụng.

### 7.2. Clock.fixed và Clock.offset

```java
Clock base = Clock.fixed(
    Instant.parse("2026-01-01T00:00:00Z"),
    ZoneOffset.UTC
);

Clock fiveMinutesLater =
    Clock.offset(base, Duration.ofMinutes(5));
```

`fiveMinutesLater.instant()` có mốc năm phút sau, vẫn deterministic.

### 7.3. Không sửa system clock trong test

Không thay đổi timezone/đồng hồ máy của CI hoặc mock static `Instant.now()` nếu có thể thay bằng Clock; các cách đó dễ tạo phụ thuộc toàn cục và test flaky, đặc biệt khi chạy song song.

---

## 8. Tách nguồn actor khỏi security framework

Hệ thống cần biết ai thực hiện thay đổi, nhưng entity không nên trực tiếp biết `SecurityContextHolder`, HTTP request hay token claims.

Định nghĩa một interface nhỏ:

```java
package demo.audit;

public interface CurrentActor {

    /** Trả một định danh actor ổn định cho audit. */
    String requireActorId();
}
```

Implementation production có thể đọc từ authentication context của ứng dụng, còn test dùng stub:

```java
CurrentActor fakeActor = () -> "test-user-17";
```

### 8.1. Dùng ID ổn định, không dùng display name

`createdBy = "Trần Văn A"` có thể thay đổi khi người dùng đổi tên hiển thị. Nếu cần truy vết, nên lưu một ID bất biến như `user-17`, `service-billing` hoặc ID subject tương ứng.

### 8.2. Không giả định mọi thao tác đều có principal người dùng

Một scheduled job, migration, consumer hoặc batch process có thể không có web authentication. Hợp đồng cần quyết định:

- Từ chối nếu thiếu actor đối với thao tác user-driven.
- Cho phép actor dịch vụ như `system:billing-job` trong luồng background đã xác thực.
- Yêu cầu actor explicit từ command context.
- Có fallback được kiểm soát và log, không âm thầm dùng `anonymous` cho mọi thay đổi.

### 8.3. Không tin actor ID do client tự gửi

Nếu HTTP request có JSON:

```json
{
  "title": "Plan",
  "updatedBy": "admin"
}
```

server không nên gán `updatedBy` trực tiếp từ field tự khai của client. Actor phải đến từ authentication/authorization context đáng tin hoặc workflow service đã kiểm chứng.

---

## 9. Entity hoàn chỉnh theo hướng service stamping

Bây giờ xây entity `Document` quản lý bốn trường audit.

```java
package demo.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

import java.time.Instant;
import java.util.Objects;

@Entity
@Table(name = "documents")
public class Document {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 200)
    private String title;

    @Column(name = "created_at",
            nullable = false,
            updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @Column(name = "created_by",
            nullable = false,
            updatable = false,
            length = 100)
    private String createdBy;

    @Column(name = "updated_by",
            nullable = false,
            length = 100)
    private String updatedBy;

    @Version
    @Column(name = "version", nullable = false)
    private long version;

    protected Document() {
        // JPA constructor
    }

    public Document(String title) {
        this.title = validTitle(title);
    }

    private static String validTitle(String value) {
        Objects.requireNonNull(value, "title");
        String trimmed = value.trim();

        if (trimmed.isEmpty() || trimmed.length() > 200) {
            throw new IllegalArgumentException("Invalid title");
        }

        return trimmed;
    }

    private static String validActor(String value) {
        Objects.requireNonNull(value, "actorId");
        String trimmed = value.trim();

        if (trimmed.isEmpty() || trimmed.length() > 100) {
            throw new IllegalArgumentException("Invalid actor");
        }

        return trimmed;
    }

    /** Gọi một lần trước khi persist document mới. */
    public void markCreated(Instant at, String actorId) {
        Objects.requireNonNull(at, "created time");

        if (createdAt != null) {
            throw new IllegalStateException(
                "Document already has creation metadata");
        }

        String actor = validActor(actorId);

        createdAt = at;
        updatedAt = at;
        createdBy = actor;
        updatedBy = actor;
    }

    /**
     * Chỉ ghi nhận dấu vết khi tên thực sự đổi.
     * Giá trị thời gian và actor được caller cấp.
     */
    public boolean rename(
            String nextTitle,
            Instant at,
            String actorId) {

        if (createdAt == null) {
            throw new IllegalStateException(
                "Creation metadata is missing");
        }

        String normalized = validTitle(nextTitle);

        if (title.equals(normalized)) {
            return false;
        }

        Objects.requireNonNull(at, "update time");
        String actor = validActor(actorId);

        title = normalized;
        updatedAt = at;
        updatedBy = actor;

        return true;
    }

    public Long getId() { return id; }
    public String getTitle() { return title; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
    public String getCreatedBy() { return createdBy; }
    public String getUpdatedBy() { return updatedBy; }
    public long getVersion() { return version; }
}
```

### 9.1. Tại sao không đặt setter public cho createdAt?

`createdAt` thuộc quy tắc chỉ được thiết lập một lần. Nếu expose `setCreatedAt(...)` công khai, bất kỳ tầng nào cũng có thể sửa metadata tạo bản ghi. Method `markCreated` diễn đạt rõ lifecycle và bảo vệ invariant trong domain model.

### 9.2. Tại sao @Column(updatable=false) cho createdAt/createdBy?

Nó hướng dẫn ORM không đưa hai cột này vào UPDATE SQL mà ORM sinh. Đây là một **bảo vệ bổ sung ở mapping**, không phải constraint tuyệt đối ở database:

- Native SQL vẫn có thể update.
- Trigger hoặc external writer vẫn có thể thay.
- Migration có thể sửa.
- Database permissions/constraints mới có thể cung cấp bảo vệ độc lập nếu yêu cầu.

### 9.3. Tại sao có @Version dù đã có updatedAt?

`@Version` phục vụ optimistic locking. Hai updates có thể dùng cùng `Instant` nếu precision bị làm tròn hoặc clock cố định trong test; timestamp không phải một concurrency token an toàn. Version giúp phát hiện stale concurrent writes ở luồng ORM tương ứng.

### 9.4. Tại sao không dùng @PreUpdate ở entity này?

Ví dụ chọn **service/domain update stamping bằng Clock** làm nguồn audit metadata. Nếu đồng thời thêm `@PreUpdate` tự gọi `Instant.now()`, test và production sẽ có hai nguồn thời gian cạnh tranh.

Một hệ thống nên chọn policy thống nhất; không nên vừa stamp trong service vừa stamp lại trong lifecycle callback mà không có lý do.

---

## 10. Service lấy Clock và CurrentActor qua dependency injection

Ví dụ với Spring transaction management:

```java
package demo.service;

import demo.audit.CurrentActor;
import demo.domain.Document;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Clock;
import java.util.Objects;

@Service
public class DocumentService {

    @PersistenceContext
    private EntityManager em;

    private final Clock clock;
    private final CurrentActor currentActor;

    public DocumentService(
            Clock clock,
            CurrentActor currentActor) {
        this.clock = Objects.requireNonNull(clock);
        this.currentActor = Objects.requireNonNull(currentActor);
    }

    @Transactional
    public Long create(String title) {
        String actor = currentActor.requireActorId();
        var doc = new Document(title);

        doc.markCreated(clock.instant(), actor);

        em.persist(doc);

        // Dùng flush để có ID chắc chắn trong ví dụ,
        // không phải commit và không bắt buộc mọi project cần.
        em.flush();

        return doc.getId();
    }

    @Transactional
    public boolean rename(Long id, String nextTitle) {
        Objects.requireNonNull(id, "id");

        Document doc = em.find(Document.class, id);
        if (doc == null) {
            throw new IllegalArgumentException(
                "Document does not exist: " + id);
        }

        // Kiểm tra no-op trước khi yêu cầu actor/time.
        // Vì vậy retry một giá trị giống nhau không cập nhật audit.
        if (doc.getTitle().equals(nextTitle.trim())) {
            return false;
        }

        String actor = currentActor.requireActorId();

        return doc.rename(
            nextTitle,
            clock.instant(),
            actor
        );
        // Dirty checking ghi UPDATE ở flush/commit.
    }
}
```

### 10.1. Lưu ý về validate đầu vào

Đoạn code `nextTitle.trim()` yêu cầu `nextTitle != null`. Với API production nên validate request ở boundary hoặc gọi `Objects.requireNonNull(nextTitle)` trước khi kiểm tra no-op để tránh `NullPointerException` không có thông điệp phù hợp. Bài thực hành có thể bổ sung validation này. Domain method vẫn validate kỹ trước khi mutate.

### 10.2. Thời điểm gán metadata ở service

Ở create:

```text
actor = currentActor.requireActorId()
now   = clock.instant()

Document(...).markCreated(now, actor)
em.persist(document)
flush/commit
```

Ở update:

```text
load Document
kiểm tra title thật sự khác
actor = currentActor.requireActorId()
now   = clock.instant()
doc.rename(newTitle, now, actor)
flush/commit
```

Không có static clock hoặc static security context bên trong entity.

### 10.3. Không bắt buộc gọi repository.save() cho managed entity

Sau `em.find`, entity đang managed trong persistence context. Nếu method chạy trong transaction và thay đổi state, JPA dirty checking sẽ phát UPDATE khi flush thích hợp. Gọi thêm `save()` không phải yếu tố bắt buộc để audit fields được update.

### 10.4. Một write path mới phải đi qua domain rule

Nếu sau này thêm `changeBody`, `changeStatus` hoặc `archive` nhưng không gọi logic audit, service stamping có thể bị bỏ sót. Có thể tập trung mọi mutation qua domain methods nhận `AuditContext`, hoặc chọn Spring Data auditing/lifecycle callback nếu ưu tiên tự động hóa. Đó là trade-off rõ ràng.

---

## 11. Bean Clock trong production

Trong ứng dụng Spring:

```java
package demo.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import java.time.Clock;

@Configuration
public class TimeConfig {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
```

### 11.1. Vì sao Clock.systemUTC()?

`Instant` đại diện mốc thời gian tuyệt đối, không có timezone hiển thị. `Clock.systemUTC()` cung cấp nguồn thời gian theo UTC convention, giúp tránh nhầm lẫn giữa timezone máy chủ và timezone người dùng.

### 11.2. UTC không giải quyết clock skew

Hai ứng dụng cùng dùng UTC nhưng đồng hồ máy sai vài giây vẫn có timestamp lệch nhau. UTC giải quyết cách diễn giải trục thời gian, không tự đồng bộ đồng hồ. Với hệ thống phân tán, cần hạ tầng time synchronization và policy xử lý clock drift.

### 11.3. Business “ngày địa phương” khác audit instant

Nếu nghiệp vụ cần “hết hạn lúc 23:59 theo giờ Việt Nam”, đó là `LocalDate` + `ZoneId`/business rule. Không dùng `LocalDateTime.now()` ở server rồi coi đó là audit instant phổ quát.

---

## 12. MutableClock cho test nhiều mốc thời gian

`Clock.fixed` đủ cho test một mốc; để test create và update theo thứ tự, có thể xây một Clock chỉ dành cho test:

```java
package demo.testutil;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;

public final class MutableClock extends Clock {

    private final AtomicReference<Instant> current;
    private final ZoneId zone;

    public MutableClock(Instant initial) {
        this(new AtomicReference<>(
            Objects.requireNonNull(initial)),
            ZoneOffset.UTC);
    }

    private MutableClock(
            AtomicReference<Instant> current,
            ZoneId zone) {
        this.current = current;
        this.zone = zone;
    }

    public void set(Instant next) {
        current.set(Objects.requireNonNull(next));
    }

    @Override
    public Instant instant() {
        return current.get();
    }

    @Override
    public ZoneId getZone() {
        return zone;
    }

    @Override
    public Clock withZone(ZoneId zone) {
        return new MutableClock(
            current, Objects.requireNonNull(zone));
    }
}
```

### 12.1. Điều khiển thời gian không dùng sleep

```java
MutableClock clock = new MutableClock(
    Instant.parse("2026-11-15T09:00:00Z")
);

Instant first = clock.instant();

clock.set(
    Instant.parse("2026-11-15T10:15:00Z")
);

Instant second = clock.instant();
```

Test có hai mốc tường minh, không cần `Thread.sleep(4500)`.

### 12.2. Thread safety của clock test

Ví dụ dùng `AtomicReference` để truy xuất thời điểm an toàn giữa threads. Tuy vậy, shared mutable clock giữa các tests chạy song song vẫn có thể gây interference. Trong mỗi test fixture nên cung cấp một Clock instance riêng hoặc cô lập test configuration.

### 12.3. Kiểm soát vùng giờ

`withZone` trả instance cùng nguồn mốc Instant với ZoneId mới. `Instant` không bị biến thành “giờ địa phương” khi đổi zone; zone ảnh hưởng các phép lấy ngày/giờ từ Clock, không đổi epoch instant.

---

## 13. Unit test domain model không cần database

Vì entity nhận mốc thời gian/actor qua method, có thể test trực tiếp:

```java
package demo.domain;

import org.junit.jupiter.api.Test;
import java.time.Instant;

import static org.junit.jupiter.api.Assertions.*;

class DocumentTest {

    @Test
    void creation_uses_the_same_instant_and_actor() {
        Instant t0 = Instant.parse(
            "2026-11-15T09:00:00Z");

        Document doc = new Document("Draft");
        doc.markCreated(t0, "user-7");

        assertEquals(t0, doc.getCreatedAt());
        assertEquals(t0, doc.getUpdatedAt());
        assertEquals("user-7", doc.getCreatedBy());
        assertEquals("user-7", doc.getUpdatedBy());
    }

    @Test
    void rename_only_updates_modification_metadata() {
        Instant t0 = Instant.parse(
            "2026-11-15T09:00:00Z");
        Instant t1 = Instant.parse(
            "2026-11-16T10:30:00Z");

        Document doc = new Document("Draft");
        doc.markCreated(t0, "user-7");

        boolean changed = doc.rename(
            "Reviewed", t1, "editor-2");

        assertTrue(changed);
        assertEquals("Reviewed", doc.getTitle());
        assertEquals(t0, doc.getCreatedAt());
        assertEquals("user-7", doc.getCreatedBy());
        assertEquals(t1, doc.getUpdatedAt());
        assertEquals("editor-2", doc.getUpdatedBy());
    }

    @Test
    void no_op_does_not_modify_updated_at() {
        Instant t0 = Instant.parse(
            "2026-11-15T09:00:00Z");

        Document doc = new Document("Draft");
        doc.markCreated(t0, "user-7");

        boolean changed = doc.rename(
            "Draft",
            t0.plusSeconds(60),
            "editor-2"
        );

        assertFalse(changed);
        assertEquals(t0, doc.getUpdatedAt());
        assertEquals("user-7", doc.getUpdatedBy());
    }
}
```

### 13.1. Unit test chứng minh điều gì?

Nó chứng minh domain methods lưu metadata đúng với **input do caller cấp**. Nó không chứng minh:

- JPA mapping ghi đúng các cột.
- Transaction commit thành công.
- Database giữ timestamp đủ precision.
- `@Version` được tăng.
- Callback nào được gọi.
- Native SQL/bulk update cũng cập nhật metadata.

Những điều đó cần integration tests.

### 13.2. Tại sao assert equals tốt hơn assert within 2 seconds?

Khi thời gian đã được inject, ta có thể so sánh tuyệt đối. Dùng khoảng “giữa before/after” khi có Clock kiểm soát được thường làm test kém chặt và che lỗi gán timestamp sai.

---

## 14. Integration test phải vượt qua persistence context

Một test phổ biến:

```java
Document doc = new Document("Draft");
doc.markCreated(t0, "user-7");
em.persist(doc);

assertEquals(t0, doc.getCreatedAt());
```

chỉ kiểm tra **Java object**. Nó chưa chứng minh database có giá trị đúng.

### 14.1. Ghi rồi đọc lại bằng context sạch

```java
em.persist(doc);
em.flush();
Long id = doc.getId();
em.clear();

Document reloaded = em.find(Document.class, id);

assertEquals(t0, reloaded.getCreatedAt());
assertEquals("user-7", reloaded.getCreatedBy());
```

`flush()` gửi các thay đổi pending tới database trong transaction. `clear()` detach các managed instances để lần `find` mới không chỉ trả lại object đã ở L1.

### 14.2. flush chưa phải commit

Test trên có thể vẫn ở transaction test và sau test bị rollback (ví dụ Spring `@DataJpaTest`). Nó chứng minh mapping/SQL trong transaction, **không chứng minh dữ liệu đã commit và được transaction khác nhìn thấy**.

Nếu cần xác nhận transaction outcome, hãy thiết kế test riêng với commit thực và đọc ở transaction mới.

### 14.3. Đọc lại cùng EM không đủ

```java
Document reloaded = em.find(Document.class, id);
```

nếu không `clear`/detach và entity vẫn managed, có thể trả cùng instance ban đầu, khiến test pass dù mapping cột SQL hoặc database default có vấn đề.

---

## 15. Ví dụ Spring integration test với Clock test

Với Spring Boot test configuration phù hợp, cung cấp một bean `MutableClock` thay bean Clock production:

```java
@TestConfiguration
public class FixedAuditClockConfig {

    @Bean
    @Primary
    MutableClock testClock() {
        return new MutableClock(
            Instant.parse("2026-11-15T09:00:00Z"));
    }
}
```

Nếu service constructor yêu cầu `Clock`, bean `MutableClock` cũng hợp lệ vì nó extends Clock. Cần import Spring `@TestConfiguration`, `@Bean`, `@Primary` và JDK `Instant`.

### 15.1. Test tạo và sửa qua service

```java
@SpringBootTest
@Import(FixedAuditClockConfig.class)
@Transactional
class DocumentServiceJpaTest {

    @Autowired
    DocumentService service;

    @Autowired
    MutableClock clock;

    @PersistenceContext
    EntityManager em;

    @Test
    void metadata_is_persisted_at_controlled_times() {
        Instant created = Instant.parse(
            "2026-11-15T09:00:00Z");

        Long id = service.create("Draft");

        em.flush();
        em.clear();

        Document first = em.find(Document.class, id);

        assertEquals(created, first.getCreatedAt());
        assertEquals(created, first.getUpdatedAt());
        assertEquals("test-user-17", first.getCreatedBy());

        clock.set(
            Instant.parse("2026-11-15T11:30:00Z"));

        service.rename(id, "Reviewed");

        em.flush();
        em.clear();

        Document second = em.find(Document.class, id);

        assertEquals(created, second.getCreatedAt());
        assertEquals("test-user-17", second.getCreatedBy());
        assertEquals(
            Instant.parse("2026-11-15T11:30:00Z"),
            second.getUpdatedAt());
        assertEquals("Reviewed", second.getTitle());
    }
}
```

Ở ví dụ này, test context cần thêm một **bean CurrentActor giả** trả `"test-user-17"`, có thể khai báo trong `FixedAuditClockConfig`:

```java
@Bean
@Primary
CurrentActor testCurrentActor() {
    return () -> "test-user-17";
}
```

### 15.2. Test class phải nhập đúng dependencies

Khi triển khai, thêm imports JUnit `@Test`/assertions; Spring `@SpringBootTest`, `@Import`, `@Autowired`; Spring `@Transactional`; JPA `EntityManager`/`@PersistenceContext`; các domain/service types. Test trên minh họa workflow, không phải dự án hoàn chỉnh với dependency/build files.

### 15.3. Transaction test có thể bị rollback cuối test

Ở ví dụ `@Transactional` đặt trên test, service `@Transactional` với propagation mặc định thường tham gia cùng transaction. Test tập trung vào persisted state **sau flush trong cùng transaction**. Để thử commit, cần test khác với transaction lifecycle được quản lý rõ.

### 15.4. Cache có thể che kết quả?

Với một context mới nhưng second-level cache enabled, dữ liệu vẫn có thể được phục vụ từ L2. Với test muốn đối chiếu DB storage sau flush, có thể dùng native SQL select, bypass shared cache hoặc cấu hình test cache phù hợp. Không kết luận “mở EM mới chắc chắn SQL SELECT” khi L2 cache đang hoạt động.

---

## 16. Test no-op ở mức persistence

Contract đã chọn: gọi rename với cùng giá trị không làm cập nhật `updatedAt`.

Scenario:

```text
T0:
  create Document("Draft")
  createdAt=T0, updatedAt=T0

T1:
  rename(Document, "Draft") -> false
  updatedAt phải vẫn bằng T0

T2:
  rename(Document, "Reviewed") -> true
  updatedAt=T2

T3:
  rename(Document, "Reviewed") -> false
  updatedAt phải vẫn bằng T2
```

### 16.1. Điều cần kiểm tra

- Java domain return true/false.
- Persisted `updatedAt`.
- Persisted `updatedBy`.
- Version của entity **không đổi khi no-op**, nếu provider không phát UPDATE vì lý do khác.
- Không có SQL UPDATE không cần thiết do logic service.
- Audit history (nếu có) không ghi revision cho no-op.

### 16.2. Đừng phụ thuộc tuyệt đối vào số SQL khi có cấu hình khác

Một provider có thể flush những cập nhật khác trong cùng context hoặc có cascades/triggers khác. Nếu assert SQL UPDATE count chính xác, test cần cô lập transaction, dữ liệu và provider. Contract nghiệp vụ vẫn là dấu vết và persisted state tương ứng.

---

## 17. Test rollback: dữ liệu đã flush nhưng không commit

Một trường hợp quan trọng:

```text
begin transaction
  create document
  set createdAt/createdBy
  flush INSERT
  throw exception
rollback transaction
```

Nếu rollback đúng, bản ghi và audit metadata trong cùng row không tồn tại như dữ liệu đã commit.

### 17.1. Dùng TransactionTemplate để kiểm soát outcome

Ví dụ Spring:

```java
TransactionTemplate txTemplate =
    new TransactionTemplate(transactionManager);

assertThrows(
    IllegalStateException.class,
    () -> txTemplate.executeWithoutResult(status -> {
        Document document = new Document("Temporary");
        document.markCreated(
            fixedClock.instant(), "test-user");
        em.persist(document);
        em.flush();

        throw new IllegalStateException("Abort");
    })
);
```

Sau đó, dùng transaction khác kiểm tra bản ghi chưa commit không tồn tại (tìm bằng ID hoặc một business key test đã biết). Nếu entity dùng IDENTITY, ID sequence có thể **không quay lại** sau rollback tùy DBMS; đó không phải bằng chứng bản ghi đã commit.

### 17.2. Test callback không đồng nghĩa test commit

`@PostPersist` có thể chạy trước rollback. Nếu listener gửi email hoặc ghi external audit log không transactional ngay ở `@PostPersist`, email/log bên ngoài có thể đã phát dù database rollback. Đây là một lỗi thiết kế thường gặp.

### 17.3. Khi ghi lịch sử cùng transaction

Nếu revision/audit history row được ghi trong **cùng transaction** đúng cách, khi rollback cả entity và history rows sẽ rollback. Không ghi lịch sử “thành công” ra external system trước khi transaction outcome được xử lý phù hợp.

---

## 18. Callback trong @MappedSuperclass cho nhiều entity

Một hướng phổ biến là dùng base class:

```java
package demo.audit;

import jakarta.persistence.Column;
import jakarta.persistence.MappedSuperclass;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;

import java.time.Instant;

@MappedSuperclass
public abstract class TimestampedEntity {

    @Column(name = "created_at",
            nullable = false,
            updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @PrePersist
    protected void onCreate() {
        Instant now = Instant.now();

        if (createdAt == null) {
            createdAt = now;
        }

        updatedAt = now;
    }

    @PreUpdate
    protected void onUpdate() {
        updatedAt = Instant.now();
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }
}
```

### 18.1. Ưu điểm

- Cấu hình gọn.
- Các entity kế thừa có createdAt/updatedAt.
- Không cần mọi service nhớ gọi touch cho mỗi managed update.
- Phù hợp khi chỉ cần timestamp convention đơn giản.

### 18.2. Hạn chế đối với testability

`Instant.now()` được hard-code trong entity superclass. Unit test muốn assert mốc chính xác phải dùng time-window assertion hoặc static mocking. Nếu cần deterministic test cao, nên thay bằng giải pháp injectable hoặc sử dụng Spring Data auditing DateTimeProvider.

### 18.3. Có thể inject Clock vào @MappedSuperclass không?

Entity là đối tượng do JPA quản lý, không được mặc định là Spring singleton bean có constructor injection hoạt động như service. Đừng tự thêm:

```java
@Autowired
private Clock clock;
```

rồi cho rằng mọi JPA runtime sẽ inject field đó vào entity. Cách dependency injection vào entity listeners có khác biệt giữa Jakarta EE CDI, Spring integration và provider. Cần xác nhận môi trường thực tế.

### 18.4. Không trộn base class callbacks với service stamping vô tình

Nếu entity vừa kế thừa `TimestampedEntity` gọi `Instant.now()` vừa được service gán `updatedAt=clock.instant()`, một flush callback có thể ghi đè thời gian fake của test. Chọn **một nguồn thời gian chủ đạo**.

---

## 19. @EntityListeners: tách callback khỏi entity

Có thể viết:

```java
@Entity
@EntityListeners(AuditListener.class)
public class Article {
    // ...
}
```

Listener:

```java
public class AuditListener {

    @PrePersist
    public void beforeCreate(Article entity) {
        // Gán các scalar audit fields của entity.
    }

    @PreUpdate
    public void beforeUpdate(Article entity) {
        // Gán last modification metadata.
    }
}
```

### 19.1. Listener giúp tái sử dụng lifecycle logic

Nó tách logic khỏi entity class, hữu ích khi nhiều entities dùng cùng convention hoặc muốn áp dụng callback ở một nơi.

### 19.2. Nhưng listener vẫn cần Clock và CurrentActor

Nếu listener tự gọi `Instant.now()` và `SecurityContextHolder`, code vẫn khó unit test và phụ thuộc môi trường. Muốn inject dependency vào listener, phải xác nhận JPA provider/container hỗ trợ và cách cấu hình lifecycle injection phù hợp.

Không giả định Spring constructor injection tự chạy trong bất kỳ `@EntityListeners` nào chỉ vì listener có annotation `@Component`.

### 19.3. Không thao tác EntityManager tùy tiện trong callback

JPA lifecycle callbacks có những hạn chế về khả năng gọi operations trên EntityManager/query/relationships trong cùng persistence context. Một quy tắc an toàn và portable là **giới hạn callback vào basic, non-relationship state của entity đang được xử lý**, tránh query DB, persist entity khác, mở transaction hoặc sửa associations bên trong callback.

Nếu nghiệp vụ cần lưu audit history row hoặc gọi service khác, hãy đưa logic ra service/transaction listener hoặc một audit framework có hỗ trợ cụ thể.

---

## 20. Spring Data JPA Auditing: một lựa chọn hỗ trợ injection

Nếu dự án dùng Spring Data JPA, có sẵn annotations:

- `@CreatedDate`.
- `@LastModifiedDate`.
- `@CreatedBy`.
- `@LastModifiedBy`.

Và:

- `@EnableJpaAuditing`.
- `AuditingEntityListener`.
- `AuditorAware<T>`.
- `DateTimeProvider`.

Đây là **Spring Data annotations**, không phải annotation chuẩn Jakarta Persistence. Chúng sử dụng cơ chế JPA entity listeners cùng hỗ trợ của Spring Data.

### 20.1. Entity dùng Spring Data Auditing

```java
package demo.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EntityListeners;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

import java.time.Instant;

@Entity
@EntityListeners(AuditingEntityListener.class)
public class AuditedTask {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String title;

    @CreatedDate
    @Column(nullable = false, updatable = false)
    private Instant createdAt;

    @LastModifiedDate
    @Column(nullable = false)
    private Instant updatedAt;

    @CreatedBy
    @Column(nullable = false, updatable = false)
    private String createdBy;

    @LastModifiedBy
    @Column(nullable = false)
    private String updatedBy;

    @Version
    private long version;

    protected AuditedTask() {}

    public AuditedTask(String title) {
        this.title = title;
    }
}
```

### 20.2. Ghi nhớ cấu hình

Chỉ đặt annotations trên fields **chưa đủ**. Cần bật auditing, đăng ký listener đúng, cấu hình nguồn actor và (nếu muốn deterministic test) nguồn thời gian. Tùy Spring Data version, cần thêm thành phần wiring/bytecode aspect hoặc dependencies phù hợp; kiểm tra framework đang dùng.

---

## 21. Cấu hình AuditorAware và DateTimeProvider

Một cấu hình Spring mẫu:

```java
package demo.config;

import demo.audit.CurrentActor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

import java.time.Clock;
import java.time.Instant;
import java.util.Optional;

@Configuration
@EnableJpaAuditing(
    auditorAwareRef = "auditorAware",
    dateTimeProviderRef = "auditDateTimeProvider"
)
public class AuditConfig {

    @Bean
    AuditorAware<String> auditorAware(CurrentActor actor) {
        return () -> Optional.of(actor.requireActorId());
    }

    @Bean
    DateTimeProvider auditDateTimeProvider(Clock clock) {
        return () -> Optional.of(Instant.now(clock));
    }
}
```

### 21.1. Vì sao DateTimeProvider giúp test?

Thay bean `Clock` production bằng fixed/mutable clock trong test. `@CreatedDate` và `@LastModifiedDate` nhận đúng mốc từ provider, không phụ thuộc wall clock của JVM.

### 21.2. Vì sao AuditorAware giúp test?

Thay `CurrentActor` bằng stub trả `"test-user-17"`. Listener có actor ổn định dù test không có web authentication thực.

### 21.3. Không coi Optional.empty() là mặc nhiên hợp lệ

Nếu `AuditorAware` trả `Optional.empty()` và fields `createdBy/updatedBy` có `nullable=false`, việc persist có thể thất bại. Chính sách của application phải quyết định actor nào được sử dụng cho scheduled jobs hoặc khi người dùng không xác thực.

### 21.4. Mốc created/modified khi INSERT

Spring Data có cấu hình hành vi “modify on create” trong các phiên bản hỗ trợ, nên `@LastModifiedDate` có thể được gán khi INSERT. Nếu hợp đồng yêu cầu `updatedAt=createdAt` ở lần tạo, cần cấu hình và kiểm thử rõ, không tự giả định behavior của mọi phiên bản.

---

## 22. Unit test Spring Data auditing khác integration test listener

Nếu chỉ test `DateTimeProvider`:

```java
Clock fixed = Clock.fixed(
    Instant.parse("2026-11-15T09:00:00Z"),
    ZoneOffset.UTC
);

DateTimeProvider provider =
    () -> Optional.of(Instant.now(fixed));

assertEquals(
    Instant.parse("2026-11-15T09:00:00Z"),
    provider.getNow().orElseThrow()
);
```

test này chứng minh provider trả thời gian đúng, **chưa chứng minh JPA listener được gọi và persist field**.

Một integration test cần:

1. Bật `@EnableJpaAuditing`.
2. Dùng entity có `@EntityListeners(AuditingEntityListener.class)`.
3. Persist qua EntityManager/repository.
4. `flush()` để kích hoạt SQL INSERT.
5. `clear()` rồi đọc lại persisted state.
6. Update field nghiệp vụ.
7. Dịch Clock trong fixture.
8. `flush/clear` rồi so sánh created/modified metadata.
9. Thử no-op và ghi nhận behavior của provider.
10. Thử rollback và bulk JPQL update.

### 22.1. Không dùng fixed Clock “một mốc” để chứng minh cập nhật thời gian

Nếu Clock vẫn ở một mốc khi create và update, `createdAt` và `updatedAt` đều có thể giống nhau. Test không biết listener `@PreUpdate`/auditing có chạy hay không. Để kiểm chứng update, dùng **hai mốc khác nhau**.

### 22.2. Test actor chuyển từ A sang B

Lượt create actor A, lượt update actor B, rồi xác nhận:

```text
createdBy = A
updatedBy = B
```

Nếu chỉ test một actor cố định, dễ bỏ sót bug gán đè `createdBy` khi update.

---

## 23. Database là nguồn thời gian: DEFAULT và trigger

Đôi khi hệ thống yêu cầu **mọi writer** — ứng dụng JPA, JDBC, migration, service khác — đều tạo timestamp theo database.

Một bảng ví dụ theo SQL chung, có thể điều chỉnh theo DBMS:

```sql
CREATE TABLE documents (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100) NOT NULL,
    updated_by VARCHAR(100) NOT NULL,
    version BIGINT NOT NULL
);
```

### 23.1. DEFAULT chỉ tự áp dụng khi INSERT

`DEFAULT CURRENT_TIMESTAMP` thường áp dụng khi INSERT không cung cấp cột. Nó **không tự làm `updated_at` đổi trên mọi UPDATE**. Nếu cần database quản lý updatedAt khi update, phải dùng trigger hoặc tính năng tự cập nhật cột của DBMS cụ thể.

### 23.2. Mapping cho cột do DB sinh

Nếu application không gán timestamps mà DB default chịu trách nhiệm:

```java
@Column(
    name = "created_at",
    insertable = false,
    updatable = false
)
private Instant createdAt;
```

Khi field không được gửi trong INSERT, DB default mới có cơ hội hoạt động. Sau persist/flush, JPA object **không mặc nhiên** có ngay giá trị DB-generated nếu provider không có mapping/generated-value fetching tương ứng.

### 23.3. Khi nào refresh cần thiết?

```java
em.persist(document);
em.flush();
em.refresh(document);
```

có thể được dùng để tải state DB sinh, nếu mapping và transaction cho phép. Một số providers có annotations/generated-property mechanisms riêng để đọc về giá trị này hiệu quả hơn. Không giả định mọi `DEFAULT` đều tự được đồng bộ vào Java field ngay lập tức.

### 23.4. CURRENT_TIMESTAMP không phải commit timestamp

Một số DBMS định nghĩa `CURRENT_TIMESTAMP`/`now()` theo thời điểm transaction hoặc statement, và timezone/precision cũng khác. Ví dụ PostgreSQL `now()` thường phản ánh thời điểm bắt đầu transaction. Không dùng default timestamp như bằng chứng commit thực tế trừ khi DBMS cung cấp một cơ chế chuyên biệt đáp ứng contract.

---

## 24. Application Clock hay Database Clock?

| Yếu tố | Clock ứng dụng | Đồng hồ database |
|---|---|---|
| Dễ unit test | Cao | Thấp hơn |
| Chỉ một nguồn clock cho nhiều app nodes? | Phải đồng bộ các máy | Có thể tập trung ở DB instance, nhưng vẫn có topology/replica |
| Được áp dụng cho external SQL writers? | Không | Có, nếu default/trigger đúng |
| Audit actor từ security context | Dễ lấy ở service | Cần truyền qua session/statement/DB mechanism |
| Kiểm soát format/type | Java time API | SQL types/DB dialect |
| Không lệch khỏi domain command time | Dễ lấy tại command | Phụ thuộc khi SQL chạy |
| Có commit timestamp chính xác | Không tự có | Không tự có nếu chỉ dùng CURRENT_TIMESTAMP |
| Dễ tích hợp mock clock | Có | Cần fake DB time/trigger testing hoặc assertion khác |

### 24.1. Không tạo hai nguồn clock ngầm định

Nếu Java gán `updatedAt=clock.instant()` nhưng DB trigger ghi đè `updated_at=CURRENT_TIMESTAMP`, API response trong cùng persistence context có thể chứa thời gian Java trong khi DB đã lưu thời gian khác.

Khi chọn DB làm authority, cần mapping và refresh/re-read strategy rõ. Khi chọn application làm authority, cần tránh trigger lặng lẽ ghi đè hoặc chấp nhận/chú thích cơ chế đó.

### 24.2. Một hệ thống có thể cần cả hai mốc

Ví dụ:

- `requestedAt`: thời điểm service nhận command.
- `recordedAt`: thời điểm database ghi row.
- `effectiveAt`: thời điểm nghiệp vụ có hiệu lực.

Nếu thật sự cần nhiều ý nghĩa, hãy dùng **tên trường khác nhau** thay vì cố gán một field có ba semantics.

---

## 25. Chọn kiểu thời gian Java

Các kiểu phổ biến:

| Java type | Ý nghĩa | Phù hợp với |
|---|---|---|
| `Instant` | Một mốc tuyệt đối trên UTC timeline | Audit timestamps |
| `OffsetDateTime` | Date-time cùng offset | API cần giữ offset được diễn đạt |
| `ZonedDateTime` | Date-time cùng ZoneId và rules | Lịch nghiệp vụ/tái diễn theo múi giờ |
| `LocalDateTime` | Ngày/giờ **không có timezone** | Lịch địa phương theo ngữ cảnh quy ước |
| `LocalDate` | Ngày không kèm giờ | Ngày nghiệp vụ |
| `java.util.Date`/`Timestamp` | Legacy temporal types | Tích hợp legacy, ít ưu tiên cho thiết kế mới |

### 25.1. Vì sao Instant thường là default phù hợp cho audit?

Với `Instant`, `2026-11-15T09:30:00Z` là một mốc tuyệt đối. Khi hiển thị cho người dùng, có thể chuyển sang timezone:

```java
Instant savedAt = document.getUpdatedAt();

ZonedDateTime displayed =
    savedAt.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
```

Điều này không làm đổi instant đã lưu.

### 25.2. LocalDateTime có thể gây hiểu nhầm

`2026-11-15T09:30:00` không có thông tin UTC hay HCM. Nếu máy A coi là UTC và máy B coi là local HCM, phép diễn giải có thể lệch 7 giờ.

Nếu phải dùng `LocalDateTime`, quy định rõ convention và conversion ở boundary.

### 25.3. Database column type

PostgreSQL có `TIMESTAMP WITH TIME ZONE` (tên dễ gây hiểu nhầm: nó lưu một mốc, không giữ timezone ID gốc của người dùng). Các DBMS khác có types và JDBC mapping khác. Kiểm tra mapping `Instant` với provider/DBMS/version thực tế thay vì suy từ tên cột.

---

## 26. Precision: Java nanosecond và database timestamp

`Instant` biểu diễn được nanosecond, nhưng nhiều database columns lưu microsecond, millisecond hoặc precision khác.

Ví dụ:

```text
Java Clock:
  2026-11-15T09:30:00.123456789Z

Database column (microsecond):
  2026-11-15T09:30:00.123457Z
  hoặc 2026-11-15T09:30:00.123456Z
  tùy DB/driver rounding-truncation semantics
```

### 26.1. Assertion có thể fail dù logic ứng dụng đúng

Một integration test:

```java
assertEquals(clock.instant(), reloaded.getUpdatedAt());
```

có thể fail nếu DB làm tròn/cắt fraction.

Giải pháp:

- Dùng mốc test nằm đúng precision DB hỗ trợ, ví dụ giây hoặc millisecond tròn.
- Hoặc normalize expected value theo **quy tắc DB đã biết**.
- Hoặc so sánh theo tolerance được yêu cầu bởi schema, nhưng phải giải thích chính sách; không tự đặt 2 giây để che mọi lỗi.

### 26.2. Mốc theo giây cho integration example

```java
Instant t0 = Instant.parse("2026-11-15T09:00:00Z");
Instant t1 = Instant.parse("2026-11-15T10:00:00Z");
```

Dùng whole-second values giúp nhiều DBs lưu/đọc thống nhất hơn. Nó không thay thế việc kiểm chứng production precision nếu ứng dụng thực sự cần microseconds.

### 26.3. updatedAt không phải khóa sắp xếp unique

Hai rows có thể cùng `updatedAt`, đặc biệt khi test dùng fixed clock hoặc DB precision thấp. Nếu phân trang theo thời gian:

```jpql
ORDER BY d.updatedAt DESC, d.id DESC
```

thì cần unique tie-breaker ID và policy khi timestamp thay đổi.

---

## 27. Đồng hồ đi lùi và monotonicity

Không phải mọi thời điểm lấy từ system clock đều tăng theo thời gian thực trong mọi tình huống. NTP corrections, cấu hình sai, migration hoặc nhiều app nodes có thể làm timestamp sau **nhỏ hơn** timestamp trước.

### 27.1. Hợp đồng cần chọn

Có thể yêu cầu:

- `updatedAt` là **mốc wall-clock khi xử lý**; có thể đi lùi trong sự cố clock.
- `updatedAt >= createdAt` phải luôn đúng; enforce qua domain logic/database.
- Mỗi mutation phải có thứ tự tăng bằng `@Version`, không dùng timestamp để quyết định version ordering.
- Một ordered event log có sequence/transaction IDs riêng.

### 27.2. Không âm thầm sửa clock skew bằng cách tăng 1 ns

Một giải pháp “updatedAt = max(now, old+1ns)” có thể làm timestamp không phản ánh giờ thực, và DB precision có thể cắt nanosecond. Nếu yêu cầu monotonic ordering là cốt lõi, dùng version/sequence phù hợp.

### 27.3. Test clock skew

```text
Create at T1
Set test Clock to T0 where T0 < T1
Try update
```

Nếu domain yêu cầu updatedAt không thể nhỏ hơn createdAt, test phải mong một lỗi business rõ ràng hoặc một policy documented. Nếu domain chấp nhận mốc system-clock thực tế, test xác nhận behavior đó và không nhầm với version.

---

## 28. @Version giúp phân biệt thứ tự thay đổi

Một entity:

```java
@Version
private long version;
```

JPA provider dùng version để kiểm tra optimistic concurrency theo semantics của mapping. Khi hai giao dịch tải cùng Document phiên bản N và sửa cạnh tranh, một giao dịch có thể thất bại với optimistic conflict khi flush/commit.

### 28.1. Tại sao updatedAt không thay thế @Version?

Nếu Clock fixed:

```text
Transaction A updatedAt = T
Transaction B updatedAt = T
```

timestamp bằng nhau không chứng minh hai giao dịch tương đương. Dùng updatedAt làm optimistic lock token có thể không phát hiện lost update, nhất là khi precision thấp.

### 28.2. Version không tự là audit history

`version = 7` cho biết một số lần cập nhật theo cơ chế versioning; nó không nói actor của các revisions cũ, field nào đổi hoặc vì sao. Cần audit trail nếu nghiệp vụ cần lịch sử.

### 28.3. Khi test optimistic conflict

Dùng hai EntityManagers/transactions độc lập:

```text
A load Document#42(version=0)
B load Document#42(version=0)

A changes title + audit metadata
A commit -> version advances

B changes title + audit metadata based on stale version
B flush/commit -> optimistic conflict
B rollback
```

Sau cùng, đọc document ở context mới. Audit metadata phải phản ánh **giao dịch thắng đã commit**, không phải actor/timestamp của giao dịch thua.

---

## 29. Không ghi external audit event trực tiếp trong @PostUpdate

Một anti-pattern:

```java
@PostUpdate
void afterUpdate() {
    externalMessageBroker.publish("Document updated");
}
```

Nếu transaction sau đó rollback, message đã gửi ra ngoài không tự rollback. Hệ thống khác có thể nhìn thấy một sự kiện “đã cập nhật” trong khi DB không lưu thay đổi.

### 29.1. @PostUpdate không phải after commit

`@PostUpdate` là JPA lifecycle callback liên quan UPDATE database. Transaction outcome có thể xảy ra sau đó.

### 29.2. Spring @TransactionalEventListener(AFTER_COMMIT)

Spring cho phép xử lý event sau khi transaction commit với `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` trong cấu hình phù hợp.

Điều này giúp tránh phát event quá sớm, nhưng **không tự bảo đảm delivery bền vững**: nếu process crash ngay sau commit nhưng trước khi event handler gửi message, thông báo có thể mất.

### 29.3. Khi cần bảo đảm tin cậy: transactional outbox

Trong cùng transaction:

```text
UPDATE document metadata
INSERT outbox event row
COMMIT cả hai
```

Sau commit, một worker/CDC đọc outbox, gửi event và đánh dấu đã xử lý với retry/idempotency. Lúc rollback, cả Document và outbox row đều rollback.

Đây là một chiến lược khác với callback timestamp đơn giản, được dùng khi cần audit/event integration đáng tin cậy.

---

## 30. Last-modified fields và audit history khác nhau

Một entity có bốn cột audit chỉ lưu **trạng thái gần nhất**.

Nếu nghiệp vụ yêu cầu lịch sử:

```text
Revision 1:
  action=CREATE
  actor=user-7
  at=T0
  title: null -> "Draft"

Revision 2:
  action=UPDATE
  actor=editor-2
  at=T1
  title: "Draft" -> "Reviewed"

Revision 3:
  action=UPDATE
  actor=editor-3
  at=T2
  title: "Reviewed" -> "Approved"
```

cần một bản ghi revision cho mỗi thay đổi phù hợp contract.

### 30.1. Các lựa chọn history

1. Application service ghi `document_revisions` cùng transaction.
2. Hibernate Envers hoặc audit provider tương ứng, theo version/configuration.
3. Database triggers ghi history table.
4. CDC (change data capture) dựa trên database log.
5. Event sourcing nếu domain thật sự yêu cầu event log làm nguồn chân lý.

### 30.2. Chọn đúng mục đích

| Nhu cầu | Công cụ phù hợp |
|---|---|
| Hiện “cập nhật lúc nào bởi ai” | created/updated metadata |
| Phát hiện concurrent writes | `@Version` và transaction strategy |
| Biết giá trị cũ của title | Audit revision/history |
| Phân phối sự kiện cho service khác sau commit | Outbox/CDC |
| Hỗ trợ truy xuất đúng tại thời điểm quá khứ | Temporal/audit history và snapshot policy |
| Xóa dữ liệu cá nhân theo luật | Retention/erasure policy cho cả history |

### 30.3. Không gọi @PreUpdate là một audit log đầy đủ

`@PreUpdate` giúp stamp last-modified fields. Nó không tự capture reliable old/new snapshots, không xử lý mọi bulk/native writes và không có commit-boundary guarantee.

---

## 31. Bulk JPQL update bỏ qua entity callbacks

Ví dụ:

```java
int changed = em.createQuery(
    """
    UPDATE Document d
    SET d.title = :title
    WHERE d.id = :id
    """)
    .setParameter("title", "Imported")
    .setParameter("id", 42L)
    .executeUpdate();
```

Truy vấn này không gọi `Document.rename(...)`, `@PreUpdate` hay Spring Data auditing cho từng entity.

### 31.1. Tự gán audit fields khi bulk update

Nếu chọn application as authority:

```java
Instant at = clock.instant();
String actor = currentActor.requireActorId();

int changed = em.createQuery(
    """
    UPDATE Document d
    SET d.title = :title,
        d.updatedAt = :at,
        d.updatedBy = :actor
    WHERE d.id = :id
    """)
    .setParameter("title", "Imported")
    .setParameter("at", at)
    .setParameter("actor", actor)
    .setParameter("id", 42L)
    .executeUpdate();
```

### 31.2. Đừng quên @Version khi bulk update

Bulk JPQL không tự áp optimistic version checks/increments như dirty-checking updates của managed entities. Nếu consistency cần, query có thể phải cập nhật `version` và dùng version predicate hoặc quy tắc khác. Ví dụ minh họa ý tưởng:

```jpql
UPDATE Document d
SET d.title = :title,
    d.updatedAt = :at,
    d.updatedBy = :actor,
    d.version = d.version + 1
WHERE d.id = :id
  AND d.version = :expectedVersion
```

Sau đó kiểm tra `executeUpdate() == 1` trước khi coi update thành công. Với entity mapping/version type/JPQL provider cụ thể, cần kiểm chứng cú pháp và concurrency behavior trên DB mục tiêu.

### 31.3. L1 vẫn có thể stale

Nếu Document#42 đang managed trong EM trước bulk update, object Java vẫn có title cũ. `clear()/refresh` hoặc transaction boundary phù hợp cần được thiết kế; không mong bulk JPQL tự cập nhật mọi managed instances.

---

## 32. Native SQL, database triggers và writers bên ngoài

Nếu một job dùng JDBC:

```sql
UPDATE documents
SET title = 'Migration'
WHERE id = 42;
```

JPA callbacks và Spring Data auditing không chạy vì thao tác không đi qua managed entity lifecycle.

### 32.1. Hợp đồng “mọi writer” cần một chiến lược nhất quán

Nếu yêu cầu mọi UPDATE, kể cả ngoài ORM, luôn có updatedAt:

- Dùng database trigger đúng schema/engine.
- Hoặc yêu cầu mọi write path tự gán updatedAt và kiểm thử từng đường.
- Hoặc chặn direct writes, cung cấp một write API thống nhất.
- Hoặc kết hợp trigger bảo vệ với application actor metadata, có conflict policy rõ.

### 32.2. Trigger không tự biết người dùng cuối

Database thường biết connection user/service account; nhiều end users cùng dùng một DB principal. Muốn ghi `updatedBy` theo actor nghiệp vụ, phải truyền actor từ ứng dụng qua một cơ chế đáng tin và bảo đảm pooling/session context không rò sang request khác.

### 32.3. Cẩn thận khi ORM cũng tự ghi timestamp

Nếu JPA và DB trigger cùng đặt updatedAt, kết quả persisted có thể khác object state. Phải chọn authority hoặc refresh đồng bộ sau database-generated values.

---

## 33. Soft delete và dấu vết thay đổi

Thay vì DELETE thật, một số domain dùng:

```text
deleted = true
deletedAt = T
deletedBy = user-5
```

Đây là **business state transition**. Có thể dùng domain method:

```java
public void softDelete(Instant now, String actorId) {
    if (deleted) {
        return; // idempotency policy
    }

    deleted = true;
    deletedAt = now;
    deletedBy = actorId;
    updatedAt = now;
    updatedBy = actorId;
}
```

Mẫu này minh họa trên entity **mở rộng** có các fields `deleted`, `deletedAt` và `deletedBy`, không phải method có thể đặt nguyên xi vào `Document` ở phần 9 mà không thêm mapping.

### 33.1. Khi soft delete dùng bulk update

Nếu xóa mềm bằng JPQL bulk UPDATE, callback không chạy. Phải cập nhật `updatedAt/updatedBy/deletedAt/deletedBy` trong cùng bulk query hoặc giao trách nhiệm cho DB trigger.

### 33.2. Khi hard delete

Xóa row làm last-modified fields biến mất khỏi primary table. Nếu cần truy vết ai xóa, phải có audit history/tombstone/event bền vững. `@PreRemove` không tự lưu dữ liệu lịch sử sau khi row đã bị xóa.

### 33.3. Query filter và audit

Nếu repository mặc định lọc `deleted=false`, integration test về soft delete cần biết cách đọc row đã deleted để xác minh metadata. Không nhầm “find không trả kết quả” với “row đã bị xóa vật lý”.

---

## 34. Tách event time khỏi processing time

Trong một hệ thống xử lý message:

```text
User action happened:       09:00
Message received by broker: 09:00:02
Worker processed:           09:07
DB committed:               09:07:01
```

Các mốc này phục vụ nhu cầu khác nhau:

- `occurredAt`: sự kiện xảy ra theo nguồn.
- `receivedAt`: hệ thống nhận.
- `processedAt`: worker xử lý.
- `updatedAt`: ứng dụng ghi modification metadata theo contract.
- `committedAt`: mốc commit nếu có cơ chế đo chuyên biệt.

### 34.1. Không đánh đồng event timestamp do client cung cấp với audit now

Client có thể gửi mốc thời gian do đồng hồ thiết bị sai. Với audit metadata đáng tin, nên sinh từ server/service/DB hoặc ghi riêng `clientOccurredAt` và nguồn tin cậy của nó.

### 34.2. Retry cùng message

Nếu worker retry một event idempotent, cần quyết định:

- Retry mà dữ liệu không đổi có làm updatedAt đổi không?
- Dùng event `occurredAt` cũ hay worker `processedAt` mới?
- Có ghi thêm audit revision cho một event đã xử lý không?
- Làm thế nào dùng idempotency key/version để ngăn xử lý trùng?

Chọn một hợp đồng rồi kiểm thử lại event nhiều lần.

---

## 35. Actor trong HTTP, batch và message consumer

Một interface duy nhất `CurrentActor` có thể có nhiều implementations.

### 35.1. HTTP request

Nguồn actor là authenticated subject ID do security layer cung cấp. Với Spring Security có thể tra `SecurityContextHolder` trong service adapter, nhưng entity không nên phụ thuộc vào API này.

### 35.2. Scheduled job

Nguồn actor có thể là `system:nightly-cleanup` hoặc `service:catalog-sync`. Nếu thiếu identity mà vẫn cập nhật dữ liệu, audit mất ý nghĩa.

### 35.3. Message consumer

Một message có thể mang initiator user ID, nhưng phải xác minh thông tin đó theo trust boundary và service authentication. Có thể lưu cả `initiatedBy` và `processedBy` nếu nghiệp vụ cần.

### 35.4. Asynchronous thread

Thread-local security context có thể không tự truyền qua executor/reactive pipeline. Không giả định gọi `CurrentActor` trên worker thread sẽ thấy cùng principal như HTTP thread. Có thể truyền actor explicit cùng command context hoặc dùng cơ chế context propagation được cấu hình/kiểm chứng.

### 35.5. Test từng nguồn actor

Kiểm tra đủ:

- User hợp lệ.
- Anonymous request bị từ chối khi cần.
- Admin/impersonation: lưu initiator hay effective actor? Cần policy rõ.
- Service account.
- Background job.
- Async consumer.
- Malformed/missing actor ID.
- Tenant mismatch.

---

## 36. Multi-tenancy và audit

Nếu hệ thống phục vụ nhiều tenants, một Document có thể cần:

```text
tenantId
createdBy
updatedBy
createdAt
updatedAt
```

### 36.1. Actor ID có thể trùng giữa tenants

`user-7` có thể chỉ duy nhất trong một tenant. Audit identity nên có scope rõ, ví dụ tuple `(tenantId,userId)` hoặc global user ID, theo mô hình auth.

### 36.2. Không chỉ lưu tenant trong mutable actor string

Nếu cần truy vết chắc chắn, lưu `tenantId` ở field riêng và đảm bảo mọi writes tôn trọng tenant authorization. Audit actor không thay thế tenant filter.

### 36.3. Update cross-tenant phải bị từ chối

Một request tenant A không được update Document tenant B chỉ vì biết ID. Nếu update thất bại do auth, không được để lại audit metadata hay history rows như thể update đã thành công.

### 36.4. Cẩn trọng khi batch migration

Nếu script di chuyển dữ liệu từ tenant A sang B, cần policy bảo toàn createdAt/createdBy cũ hay ghi migration actor/time. Không âm thầm giả rằng mọi metadata cũ đều vẫn diễn giải được sau migration.

---

## 37. “Created” có phải luôn là lúc INSERT?

Tùy nghiệp vụ:

- Nhập một hợp đồng ký ngày hôm qua vào hệ thống hôm nay: `contractSignedAt` là hôm qua, `createdAt` có thể là hôm nay.
- Import dữ liệu legacy có original creation timestamp: có thể muốn bảo toàn `sourceCreatedAt` riêng.
- Replay event log: `eventOccurredAt` không phải `processedAt`.
- Sao chép document template: bản sao là entity mới, có createdAt mới; không sao chép metadata audit của nguồn trừ khi có yêu cầu cụ thể.

### 37.1. Đặt tên rõ cho dữ liệu nguồn

Nếu cần giữ timestamp cũ:

```text
sourceCreatedAt
importedAt
createdAt
```

có thể là ba fields riêng. Dùng createdAt như một “túi chứa mọi loại ngày” sẽ khiến reports và tests khó hiểu.

### 37.2. Migration policy

Khi import 1 triệu rows, hãy ghi rõ:

- Preserve original createdAt hay stamp import time?
- createdBy gốc còn xác định được không?
- Dùng actor import hay actor cũ?
- updatedAt của legacy có giữ không?
- Đặt version khởi tạo thế nào?
- Trigger có ghi đè timestamps không?
- Batch JPQL/native insert có bypass JPA listeners không?

Đó là một phần của thiết kế audit dữ liệu, không chỉ của entity mapping.

---

## 38. Tránh lưu time-sensitive data từ client

Một anti-pattern:

```java
@PostMapping("/documents")
public void create(@RequestBody Document document) {
    repository.save(document);
}
```

Nếu entity được deserialize trực tiếp, client có thể gửi `createdAt`, `createdBy` hoặc `version`. Tùy binder/mapping, dữ liệu không tin cậy có thể đi sâu vào persistence layer.

### 38.1. Dùng request DTO riêng

```java
public record CreateDocumentRequest(String title) {}
```

Controller gọi:

```java
Long id = service.create(request.title());
```

Service tự lấy actor và time. Không dùng entity audit fields làm writable request contract.

### 38.2. Response DTO riêng

```java
public record DocumentResponse(
    Long id,
    String title,
    Instant createdAt,
    Instant updatedAt,
    String createdBy,
    String updatedBy,
    long version
) {}
```

Chọn fields được trả theo authorization/privacy policy. Có thể không expose `createdBy` hoặc `updatedBy` cho user không có quyền.

---

## 39. Mối liên hệ với optimistic locking và REST

Một API update có thể nhận expected version qua ETag/If-Match hoặc request body theo contract:

```text
Document version = 7
Client A update -> version = 8
Client B dựa trên version = 7 -> conflict
```

### 39.1. Version là công cụ concurrency

Dùng optimistic locking để phát hiện stale updates. Audit metadata chỉ ghi nhận actor/time của **giao dịch thành công**.

### 39.2. Không cập nhật audit trước khi kiểm tra quyền

Nếu người dùng không được sửa Document, service phải từ chối mà không thay đổi title/updatedAt. Trong transaction hợp lệ có thể đảm bảo rollback, nhưng tốt hơn là bố trí authorization trước mutations.

### 39.3. Thứ tự actor/time trong service

Để tránh source metadata sai:

```text
authenticate -> authorize
load entity
validate command
detect no-op
get trusted actor/time
mutate + stamp
flush/commit
```

Một số use cases cần lấy time sớm để ghi requestReceivedAt, nhưng khi đó hãy lưu riêng mốc đó.

---

## 40. @PreUpdate và việc thay đổi collection

Giả sử:

```java
@Entity
class Order {

    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines;

    @PreUpdate
    void beforeUpdate() {
        updatedAt = Instant.now();
    }
}
```

Nếu chỉ thêm một `OrderLine` ở bảng con mà không update một basic column của `Order`, provider có thể không phát UPDATE cho Order root; `@PreUpdate` của Order không mặc nhiên chạy chỉ vì graph nghiệp vụ “đơn hàng đã thay đổi”.

### 40.1. Chọn aggregate boundary

Nếu business định nghĩa “updatedAt của Order” phải đổi khi Lines thay đổi, service cần touch Order root (hoặc có cơ chế phù hợp) khi thay đổi child collection.

### 40.2. Mapping ownership

`mappedBy` có nghĩa association ownership ở phía child. SQL UPDATE/INSERT có thể chỉ tác động order_lines. Không dựa vào parent PreUpdate để đại diện toàn bộ child changes.

### 40.3. Test integration với children

- Tạo Order và OrderLine.
- Ghi parent updatedAt.
- Thêm child.
- Flush/commit.
- Đọc lại parent updatedAt.
- Đánh giá có cần change theo contract không.
- Nếu cần, sửa service/aggregate method và test lại.

---

## 41. Callback và transaction ordering

Trong cùng transaction, có thể có nhiều thay đổi:

```text
T0: load Document
T1: rename "Draft" -> "Reviewed"
T2: JPQL query khiến AUTO flush
T3: rename "Reviewed" -> "Approved"
T4: commit gây flush nữa
```

Một `@PreUpdate` chạy theo SQL UPDATE có thể được gọi ở mỗi flush dẫn đến UPDATE, không nhất thiết một lần đúng bằng “một HTTP request”. Vì vậy:

- Nếu cần timestamp “thời điểm cuối SQL update”, callback có behavior gần hơn với flush.
- Nếu cần timestamp “thời điểm business command”, service stamping rõ hơn.
- Nếu cần một audit revision duy nhất cho command, đừng mặc định callback lần nào cũng là một command.
- Nếu nhiều dirty transitions trong một transaction, số callback/UPDATE statements có thể khác suy đoán.

### 41.1. Không dùng callback count làm số thao tác người dùng

Một người dùng có thể thay nhiều fields trong một command, provider có thể phát một UPDATE hoặc nhiều updates vì flushes. Một callback có thể tương ứng một SQL UPDATE, không phải một hành vi giao diện duy nhất.

### 41.2. Retry cả transaction có thể gán timestamp mới

Nếu transaction retry do optimistic conflict/deadlock, service có thể gọi Clock lại, dẫn tới updatedAt mới ở lần retry. Nếu cần giữ “command received time”, đưa timestamp đó vào command context thay vì lấy mới ở mỗi attempt.

---

## 42. Kiểm thử callback bằng counters: thận trọng

Có thể tạo test listener ghi nhận `@PrePersist`, `@PreUpdate` để kiểm tra gọi khi flush. Nhưng một implementation phụ thuộc static counters có thể gây test interference khi chạy song song.

### 42.1. Ưu tiên persisted effects

Test nghiệp vụ thường quan tâm:

- Timestamp trong DB.
- Actor trong DB.
- Version.
- Không bị đổi khi no-op.
- Không tồn tại khi rollback.

Đừng chỉ khẳng định callback method được gọi mà quên hiệu ứng cuối.

### 42.2. Nếu cần thử chính callback count

Dùng test fixture/provider hook có scope theo test, hoặc log/SQL capture; tránh global mutable singleton nếu test chạy concurrent.

### 42.3. Không xem callback ordering giữa các entities là thứ tự tuyệt đối

JPA có quy tắc callback invocation, nhưng thứ tự SQL updates giữa nhiều entities phụ thuộc provider, flush order, cascades, batching. Không thiết kế nghiệp vụ dựa trên giả định “callback của Parent luôn chạy trước callback Child” nếu không có contract thực tế bảo đảm.

---

## 43. Kiểm thử timestamp với dữ liệu database-generated

Nếu `createdAt` do database default sinh, một test deterministic bằng `Clock.fixed` ở Java không kiểm soát được DB clock. Có thể chọn:

1. Dùng test database có cơ chế time injection/override được hỗ trợ.
2. Kiểm tra giá trị nằm trong một khoảng trước/sau statement với tolerance phù hợp và đã hiểu DB semantics.
3. Dùng SQL function giả/test schema tương thích nếu architecture cho phép.
4. Kiểm tra invariant (không NULL, không thay đổi sau update) thay vì exact Instant.
5. Dùng controllable trigger/time-source abstraction trong môi trường integration chuyên dụng.

### 43.1. Không so SQL NOW() với system clock bằng tolerance tùy tiện

Database có thể dùng transaction start time; statement kéo dài; application clock lệch. Một assertion “cách Java now không quá 1 giây” có thể flaky dù DB đúng. Hãy hiểu nguồn thời gian và kiểm soát điều kiện test.

### 43.2. DB trigger và rollback

Nếu trigger ghi vào history table trong **cùng transaction**, những writes thường rollback cùng transaction. Nếu trigger phát ra side effect ngoài DB transactional boundary, cần kiểm tra riêng. Không khẳng định “trigger luôn tạo audit bất biến kể cả khi rollback”.

---

## 44. Trường createdAt có thể null trước flush không?

Tùy chiến lược.

Với service stamping:

```java
Document d = new Document("Draft");
d.markCreated(t0, "user-7");
// createdAt có giá trị ngay, trước em.persist().
```

Với `@PrePersist`:

```java
Document d = new Document("Draft");
// createdAt có thể còn null.
em.persist(d);
// @PrePersist gán khi lifecycle callback chạy theo provider.
```

Với DB default:

```java
Document d = new Document("Draft");
em.persist(d);
// Java field có thể còn null tới khi giá trị DB được fetch/refresh.
```

### 44.1. Không test sai thời điểm

Nếu thiết kế dùng callback/DB default, unit test chỉ kiểm tra `new Document().getCreatedAt()` sẽ không có ý nghĩa “JPA auditing thất bại”. Cần test tại lifecycle boundary phù hợp.

### 44.2. Dữ liệu chưa persist và validation

Có thể thiết kế constructor phải nhận audit metadata hoặc dùng factory method để entity luôn đầy đủ ngay từ lúc tạo. Điều này hợp lý nếu domain yêu cầu audit invariants trước persistence.

---

## 45. Dấu vết “ai sửa” trong Spring Security

Một adapter khái niệm:

```java
@Component
public class SpringSecurityCurrentActor
        implements CurrentActor {

    @Override
    public String requireActorId() {
        Authentication auth =
            SecurityContextHolder.getContext()
                .getAuthentication();

        if (auth == null || !auth.isAuthenticated()
                || auth instanceof AnonymousAuthenticationToken) {
            throw new IllegalStateException(
                "Authenticated actor required");
        }

        return auth.getName();
    }
}
```

Imports (Spring Security):

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
```

### 45.1. auth.getName() là một điểm khởi đầu, không phải luôn global immutable ID

Trong production, nhiều hệ thống cần subject/user ID stable từ custom principal hoặc JWT claim đã xác thực. Username/email có thể thay đổi. Hãy chọn ID đúng với identity model.

### 45.2. Actor context trong async

`SecurityContextHolder` thường dựa trên thread-local trong các cấu hình phổ biến. Nếu code chạy trong async executor mà context không được propagate, adapter có thể không tìm thấy principal. Test cần mô phỏng path thực tế hoặc truyền một `AuditActor` explicit.

### 45.3. Impersonation

Nếu admin thao tác “thay mặt” người khác, có thể cần lưu cả:

```text
effectiveActorId = user-123
initiatingActorId = admin-9
```

Đừng chỉ lưu một tên rồi không phân biệt nguồn truy vết. Đây là quyết định audit/business security.

---

## 46. Dữ liệu sửa ngoài transaction có đúng không?

JPA managed mutations được đồng bộ vào database theo transaction semantics. Nếu code sửa entity sau khi persistence context đã đóng hoặc entity detached:

```java
Document detached = ...;
detached.rename("New", t1, "user-7");
```

metadata đổi trong Java object nhưng **không tự persist**. Nếu code cần lưu, phải dùng transaction/merge hoặc load managed entity rồi apply command đúng cách.

### 46.1. Merge detached state và metadata

`em.merge(detached)` có thể copy state từ detached entity sang managed instance, gồm những fields không mong muốn nếu không kiểm soát. Một detached object từ client không nên được tin để ghi đè createdAt/createdBy/version.

### 46.2. Chọn command-based updates

Ưu tiên:

```text
load managed entity by ID
authorize
apply allowed changes
stamp audit
flush/commit
```

thay vì deserialize toàn bộ entity từ JSON rồi merge tùy tiện.

### 46.3. @Column(updatable=false) không thay access control

Nó có thể ngăn ORM cập nhật cột trong SQL, nhưng không thay thế domain validation, API DTO và bảo vệ dữ liệu audit.

---

## 47. Precision, sorting và kiểm thử biên

Một test nghiêm túc nên bao gồm:

| Trường hợp | Kỳ vọng |
|---|---|
| Tạo và update cùng giây | Metadata có thể bằng timestamp; version riêng |
| Update qua múi giờ DST | `Instant` không bị DST đổi mốc |
| Hiển thị Asia/Ho_Chi_Minh | Chỉ chuyển presentation, không sửa DB instant |
| Ngày 31/12 -> 01/01 | Date formatting không ảnh hưởng epoch |
| DB cắt microseconds | Test dùng precision-aware assertion |
| Clock chạy lùi | Theo policy đã chọn |
| App nodes khác clock | Monitor clock skew, không dùng timestamp làm unique ID |
| Sort theo updatedAt | Tie-breaker với ID |
| User đổi display name | createdBy lưu stable ID |
| Xóa account người dùng | Audit actor retention/privacy policy rõ |

### 47.1. Đừng dùng LocalDateTime.now() để làm audit UTC

`LocalDateTime.now()` phụ thuộc default zone của JVM. Nếu thật sự muốn absolute instant, dùng `Instant.now(clock)` rồi map/serialize theo agreed UTC contract.

### 47.2. Tránh test bằng string thời gian địa phương

Nên assert `Instant` value. Format string/offset là trách nhiệm serialization layer, có test riêng.

---

## 48. Dấu vết nhiều thay đổi trong một transaction

Một service có thể sửa cùng entity hai lần:

```java
document.rename("Reviewed", t1, "editor-1");
document.rename("Approved", t2, "editor-2");
em.flush();
```

Kết quả persisted theo service stamping ví dụ là:

```text
title=Approved
updatedAt=t2
updatedBy=editor-2
```

Đây là **last-modified metadata**. Nó không ghi hai revisions “Reviewed” và “Approved”. Nếu cần lịch sử từng command, application phải ghi revision events/tables tương ứng và quyết định có lưu intermediate state chưa flush hay không.

### 48.1. Một transaction không đồng nghĩa một audit event

Một transaction có thể xử lý nhiều commands, hoặc một command có thể chạm nhiều entities. Phải xác định đơn vị audit revision:

- Một entity update.
- Một business command.
- Một transaction.
- Một field change.
- Một external event.

### 48.2. Một INSERT theo batch

Nếu import 10.000 records với cùng một command time, có thể muốn tất cả cùng `importedAt`. Nếu dùng callback `Instant.now()` từng entity, timestamps có thể hơi khác. Truyền cùng `Clock.instant()`/AuditContext cho batch mang semantics rõ ràng hơn.

---

## 49. Một AuditContext thay vì truyền nhiều tham số

Khi domain methods cần cả actor, time, requestId, source, có thể đóng gói:

```java
package demo.audit;

import java.time.Instant;
import java.util.Objects;

public record AuditContext(
    Instant at,
    String actorId,
    String requestId
) {
    public AuditContext {
        Objects.requireNonNull(at);
        Objects.requireNonNull(actorId);
        Objects.requireNonNull(requestId);
    }
}
```

Một service factory:

```java
public AuditContext currentAuditContext(String requestId) {
    return new AuditContext(
        clock.instant(),
        currentActor.requireActorId(),
        requestId
    );
}
```

### 49.1. Lợi ích

- Một timestamp dùng nhất quán cho các entities trong một business command.
- Actor identity rõ.
- Correlation/request ID có thể lưu ở history/outbox.
- Test dễ cấp một context cố định.
- Giảm khả năng service quên một trong các metadata.

### 49.2. Không đưa mọi field audit vào entity

`requestId` có thể hữu ích ở audit history nhưng không cần xuất hiện trong mọi row nghiệp vụ. Chọn trường nào được lưu theo use case.

### 49.3. AuditContext là dữ liệu, không phải security token

RequestId và actorId do service cấp phải qua auth/trust policy. Không dùng một record này để thay toàn bộ authorization checks.

---

## 50. Test matrix tổng hợp

| Scenario | Kiểm tra trên object | Kiểm tra DB | Ghi chú |
|---|---|---|---|
| CREATE | createdAt=updatedAt=T0 | Persisted cả hai | Actor tạo/sửa |
| UPDATE thật | updatedAt=T1 | persisted update | createdAt không đổi |
| NO-OP update | updatedAt giữ nguyên | Không có metadata đổi | Theo policy |
| ACTOR change | updatedBy actor B | createdBy vẫn actor A | Tách identity |
| ROLLBACK create | Object có stamp | Không có committed row | Flush không commit |
| ROLLBACK update | Object có stamp mới trước rollback | DB giữ giá trị cũ | New EM/transaction |
| @PrePersist | Callback chạy theo lifecycle | Insert fields đúng | Test flush |
| @PreUpdate | Callback khi UPDATE thực tế | timestamp đúng | Không chỉ gọi save |
| Bulk JPQL UPDATE | Callbacks bypass | Audit phải xử lý riêng | Version/state |
| Native SQL UPDATE | Không qua callback | Trigger/app policy | External writers |
| Parent-only field update | Parent audit | Parent row update | ORM dirty checking |
| Child-only update | Parent callback có thể không chạy | Theo aggregate policy | Touch parent nếu cần |
| Clock skew | Domain behavior rõ | Precision-aware | Policy |
| DB-generated timestamp | Object có thể chậm refresh | DB authority | Trigger/default |
| Optimistic conflict | Giao dịch thua bị lỗi | Winner metadata persisted | Rollback/retry |
| Soft delete | deletedAt/deletedBy | Persisted tombstone | No history nếu hard delete |
| Concurrent node clocks | Mốc có thể lệch | Version/sequence | Không thay lock |
| Batch import | Một AuditContext | Fields đúng mọi row | Không dùng global static |
| Async worker | Actor rõ ràng | updatedBy service actor | Context propagation |
| Tenant mismatch | Không mutate | Không có audit write | Authorization |
| Audit history | Revision row/event | Rollback cùng transaction | Outbox nếu external |

---

## 51. Test rollback update riêng biệt

Một integration test có thể:

1. Tạo Document ban đầu với T0, actor A và **commit**.
2. Mở transaction mới.
3. Đặt Clock=T1, actor B.
4. Rename Document và `flush()`.
5. Cố ý throw exception để rollback.
6. Mở EntityManager/transaction mới.
7. Đọc lại Document.
8. Xác nhận title, updatedAt, updatedBy và version vẫn là state committed T0/A.

### 51.1. Không chỉ assert trên object sau rollback

Một managed Java object sau rollback có thể vẫn giữ field values được mutate trước đó hoặc không ở trạng thái đáng tin để tiếp tục làm việc. Mở context mới để kiểm tra DB.

### 51.2. Nếu có history/outbox

Kiểm tra revision/event của update thất bại **không xuất hiện như committed data**. Đây là lý do history/outbox cần được ghi trong cùng transaction hoặc có một cơ chế đảm bảo transaction outcome.

### 51.3. External notification

Không assert “đã gửi email thành công” trước commit. Với outbox, assert outbox row chỉ tồn tại sau commit và worker có idempotency policy.

---

## 52. Test concurrency đúng cách

Một thí nghiệm hai giao dịch dùng hai EntityManagers:

```text
DB ban đầu:
 Document#42 title="Draft", version=0
 updatedAt=T0, updatedBy=A

EM A / Transaction A:
 load Document#42 version=0

EM B / Transaction B:
 load Document#42 version=0

A:
 rename("Reviewed", T1, actor A1)
 flush + commit

B:
 rename("Approved", T2, actor B1)
 flush/commit -> expected conflict với @Version
 rollback

Final:
 title="Reviewed"
 updatedAt=T1
 updatedBy=A1
 version tăng theo successful update
```

### 52.1. Khác với hai lần gọi service tuần tự

Hai calls tuần tự thường chỉ đơn giản đọc version mới sau commit đầu. Muốn tạo optimistic conflict, hai transactions phải **cùng tải state cũ trước khi transaction nào commit**, rồi mới update.

### 52.2. Dùng latch, không dùng sleep

Trong automated test, dùng `CountDownLatch`/barrier để điều phối "both loaded" và "A committed", không dựa vào `Thread.sleep()`.

### 52.3. Phải quan sát exception ở flush/commit

`OptimisticLockException` có thể xuất hiện tại flush hoặc commit, tùy provider/transaction manager. Nếu Spring translate exceptions, class ngoài cùng có thể khác, cần xác nhận root cause/SQL state theo integration stack.

### 52.4. Retry policy

Nếu retry từ B, giao dịch mới phải reload state hiện tại và quyết định áp command thế nào. Không dùng lại stale detached object và audit timestamp của giao dịch thua mà không có policy.

---

## 53. Audit metadata không thay thế event sourcing

Nếu yêu cầu:

> Phải tái dựng toàn bộ trạng thái Document vào ngày trước và biết thứ tự mỗi command đã được xử lý.

bốn cột audit trên row chính **không đủ**.

Event sourcing/audit history đòi hỏi:

- Event identity và order.
- Actor, occurred/recorded time.
- Payload/field changes.
- Schema evolution.
- Transactional integrity.
- Snapshot/replay strategy.
- Retention/privacy policy.
- Idempotency và uniqueness.
- Kiểm thử replay.
- Cách xử lý correction/deletion.

Không chọn event sourcing chỉ vì cần createdAt/updatedAt. Ngược lại, không hứa giải quyết audit pháp lý chỉ bằng hai lifecycle callbacks.

---

## 54. Bảo mật và privacy của audit fields

Audit metadata có thể là thông tin nhạy cảm:

- User IDs.
- Email nếu lỡ dùng làm actor ID.
- Device/request IP.
- Resource ownership.
- Tên nhân viên xử lý dữ liệu.

### 54.1. Không cần expose toàn bộ audit metadata cho client

Một response public có thể chỉ trả `updatedAt`. Back-office admin response có thể được phép xem `updatedBy`. Authorization controls cần áp dụng ở API/DTO layer.

### 54.2. Retention

Nếu có audit history, cần quy định thời gian lưu và chính sách data subject privacy. Không ghi mọi thay đổi vô hạn chỉ vì framework có khả năng.

### 54.3. Log chứa actor/request IDs

Tránh nhét token access, session secrets hoặc full request bodies vào audit history hoặc logs. Correlation ID và stable user ID thường đủ cho nhiều nhu cầu.

### 54.4. Audit trail cần chống sửa?

Nếu yêu cầu compliance, cần xem xét database permissions, write-once policy, signed records hoặc external immutable storage theo threat model. `@Column(updatable=false)` chỉ là hint ORM, không phải bảo đảm chống sửa có giá trị pháp lý.

---

## 55. Performance: dấu vết thời gian có chi phí gì?

Thêm bốn cột audit nhìn chung nhỏ, nhưng có những hệ quả:

- Mỗi update nghiệp vụ có thêm fields được ghi.
- Nếu chỉ thay updatedAt do no-op, DB phải UPDATE không cần thiết.
- Update có thể làm index `updated_at` thay đổi.
- Sorting/filter theo updatedAt cần index phù hợp.
- Audit history có thể tăng gấp nhiều lần lượng records.
- Database triggers thêm latency và lock footprint.
- Outbox/CDC tạo thêm writes/replication work.
- Cache invalidation có thể tăng khi mọi request tạo UPDATE vô nghĩa.

### 55.1. Không touch metadata cho mỗi GET

Một GET chỉ đọc không nên mặc định thay `updatedAt`. Nếu cần theo dõi `lastAccessedAt`, hãy định nghĩa field/collection riêng và cân nhắc tần suất ghi/analytics pipeline. Dùng `updatedAt` cho cả read access sẽ làm sai khái niệm last modified.

### 55.2. Chỉ touch khi business state thay đổi

Nếu contract yêu cầu, domain method return boolean/dirty flag rõ giúp tránh writes không cần.

### 55.3. Index

Ví dụ:

```sql
CREATE INDEX idx_documents_updated_id
ON documents(updated_at DESC, id DESC);
```

Index có thể giúp danh sách “mới sửa nhất” nhưng làm tăng chi phí UPDATE. Cần đo workload thực tế, không tạo index chỉ vì có field audit.

---

## 56. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân phổ biến | Cách xử lý |
|---|---|---|
| Unit test timestamp flaky | `Instant.now()` gắn cứng | Inject Clock, dùng fixed Instant |
| createdAt/updatedAt lệch vài ns khi CREATE | Gọi now hai lần | Lấy một Instant rồi gán cả hai |
| @PreUpdate không chạy khi save | Không có dirty UPDATE/khác lifecycle | Test flush + thay đổi thật |
| @PreUpdate không chạy khi bulk JPQL | Bulk bypass callbacks | Stamp trong query hoặc trigger |
| @PostUpdate gửi event rồi DB rollback | Callback chưa phải after commit | Transactional outbox/after-commit policy |
| updatedAt đổi khi không sửa gì | Service luôn touch | No-op detection, hợp đồng rõ |
| createdBy bị đổi trên UPDATE | Logic setter/callback gán sai | Giữ immutable createdBy |
| JPA @Column(updatable=false) vẫn bị native SQL sửa | Mapping không chặn native writer | DB constraints/permissions/trigger |
| Spring auditing fields NULL | Chưa enable listener/provider | Enable auditing + AuditorAware/DateTimeProvider |
| Batch job không có updatedBy | Không có principal web | Service actor explicit |
| Async audit sai actor | Thread context không propagate | Command context/propagation |
| Đọc lại trong test vẫn thấy object cũ | Persistence context identity map | flush/clear, transaction mới |
| DB timestamp khác expected vài µs | Precision/rounding | Test precision-aware |
| Test đọc default timestamp thấy null | Java chưa refresh generated DB value | fetch generated state/refresh |
| Rollback test vẫn nhìn field đã sửa | Đọc cùng stale Java object | EntityManager mới để kiểm tra DB |
| updatedAt nhỏ hơn createdAt | Clock skew hoặc nguồn time hỗn hợp | Chọn policy/nguồn rõ |
| @Version không tăng ở bulk UPDATE | Bulk bypass version management | Kiểm soát version riêng |
| Parent updatedAt không đổi khi thêm child | Parent SQL không UPDATE | Touch aggregate root khi cần |
| Audit lịch sử thiếu events | Chỉ có last-modified columns | Revision table/Envers |
| CreatedAt giống last imported date | Lẫn business time với system time | Tách fields theo semantics |
| DB trigger ghi đè giá trị Java | Hai nguồn authority | Chọn một nguồn và refresh policy |
| Spring @Cacheable bị nhầm auditing | Tên annotation giống nhau không liên quan | Dùng đúng package |
| Actor từ request body bị giả mạo | Trust boundary sai | Lấy actor từ authenticated context |
| Test pass trên H2 nhưng fail production | Mapping/time precision/dialect khác | Integration test DB mục tiêu |
| SQL ghi updatedAt nhưng transaction chưa commit | Flush chưa commit | Test transaction outcome riêng |

---

## 57. Bài thực hành A — Service stamping và Clock.fixed

1. Tạo entity Document có createdAt, updatedAt, createdBy, updatedBy.
2. Thêm constructor chỉ nhận title.
3. Thêm `markCreated(Instant, actor)` và `rename(title, Instant, actor)`.
4. Viết `CurrentActor` interface.
5. Tạo Clock cố định tại T0.
6. Service create Document với actor A.
7. Assert bốn audit fields trên Java object.
8. Chuyển Clock sang T1 bằng MutableClock.
9. Rename bằng actor B.
10. Assert created fields vẫn T0/A và modified fields là T1/B.
11. Thử rename cùng giá trị, bảo đảm updatedAt không đổi.
12. Không dùng Thread.sleep.

## 58. Bài thực hành B — Từ unit test đến persisted state

1. Tạo schema documents với bốn cột audit.
2. Chạy test `em.persist` và `em.flush`.
3. Lưu ID.
4. Gọi `em.clear()`.
5. Dùng `em.find` nạp lại.
6. Assert các Instant/actor đúng.
7. Dùng mốc whole-second để tránh precision mismatch không cần thiết.
8. Thử update, flush, clear và assert lại.
9. Ghi rõ test rollback cuối test hay commit thật.
10. Thử L2 cache enabled và đọc theo query/native strategy phù hợp.

## 59. Bài thực hành C — @PrePersist/@PreUpdate

1. Tạo `TimestampedEntity` có callbacks.
2. Persist một entity kế thừa.
3. Ghi thời điểm callback chạy so với SQL INSERT.
4. Sửa một basic field.
5. Flush và kiểm tra updatedAt.
6. Gọi save/no-op, ghi có UPDATE/callback không trên provider.
7. Tạo query SELECT khiến AUTO flush, quan sát callback timing.
8. Thử hai flushes trong cùng transaction.
9. Giải thích vì sao callback event không đồng nghĩa business command.
10. So sánh khả năng test chính xác với injectable Clock.

## 60. Bài thực hành D — Spring Data auditing

1. Thêm AuditedTask có `@CreatedDate`/`@LastModifiedDate`.
2. Thêm `@CreatedBy`/`@LastModifiedBy`.
3. Gắn `AuditingEntityListener`.
4. Bật `@EnableJpaAuditing`.
5. Cung cấp `AuditorAware<String>` và `DateTimeProvider`.
6. Trong test, dùng Clock.fixed/MutableClock.
7. Persist với actor A.
8. Flush/clear và assert created metadata.
9. Advance time, update với actor B.
10. Flush/clear và assert modified metadata.
11. Thử không có auditor, kiểm tra policy.
12. Thử bulk JPQL để chứng minh listener không chạy theo từng row.

## 61. Bài thực hành E — Triggers và DB defaults

1. Tạo bảng có DEFAULT CURRENT_TIMESTAMP.
2. Ánh xạ createdAt `insertable=false, updatable=false`.
3. Persist entity không gán createdAt trong Java.
4. Flush rồi refresh/read lại giá trị.
5. Xác định DB timezone và timestamp precision.
6. Update một field và xem DEFAULT có tự update updatedAt không.
7. Thêm trigger update timestamp trên DB test.
8. Lặp thử bằng JDBC trực tiếp.
9. So sánh DB-generated timestamp và application Clock.
10. Quyết định authority và refresh policy.

## 62. Bài thực hành F — Rollback

1. Commit Document ban đầu T0/A.
2. Mở transaction khác.
3. Đổi title T1/B và flush.
4. Ném exception, rollback.
5. Mở EM mới.
6. Đọc Document, xác nhận vẫn T0/A và title cũ.
7. Kiểm tra version persisted không tăng do transaction rollback.
8. Nếu có audit revisions/outbox, xác nhận không có committed row cho update thất bại.
9. Giải thích tại sao `@PostUpdate` không phải after commit.

## 63. Bài thực hành G — Bulk update và @Version

1. Load Document#42 version N.
2. Dùng JPQL bulk UPDATE sửa title mà không set audit fields.
3. Quan sát callback không tự chạy.
4. Đọc DB và xác định metadata/version mismatch.
5. Viết lại bulk query gán updatedAt/updatedBy.
6. Thêm version increment/expectedVersion predicate nếu cần.
7. Kiểm tra affected row count.
8. Clear persistence context và load lại.
9. Giải thích vì sao không thể chỉ dựa vào @PreUpdate.
10. Lặp bằng native SQL/test trigger.

## 64. Bài thực hành H — Concurrency

1. Dùng hai EntityManagers/transactions độc lập.
2. Cả hai load version N trước khi giao dịch nào commit.
3. A sửa title với T1/A1.
4. B sửa title với T2/B1.
5. Cho A commit thành công.
6. Cho B flush/commit và ghi exception.
7. Rollback B.
8. Đọc state từ context mới.
9. Assert metadata của A1/T1, không bị B1/T2 ghi đè.
10. Thử retry transaction B theo policy.
11. Không dùng updatedAt như khóa concurrency thay @Version.

## 65. Bài thực hành I — Aggregate children

1. Tạo Order có Lines.
2. Ghi parent Order updatedAt.
3. Thêm một Line bằng JPA.
4. Flush/commit.
5. Quan sát parent @PreUpdate có chạy không.
6. Định nghĩa business yêu cầu “Order được sửa khi Line thay đổi”.
7. Bổ sung touch parent ở domain/service.
8. Dùng injected Clock cho parent timestamp.
9. Test lại persisted parent audit.
10. Giải thích ownership và SQL operations khác nhau.

## 66. Bài thực hành J — Actor và bảo mật

1. Tạo HTTP command chỉ có title, không có createdBy.
2. Lấy actor từ authenticated principal.
3. Ghi createdBy stable user ID.
4. Tạo update từ actor B.
5. Không cho client sửa createdBy qua request body.
6. Thử anonymous request và xác nhận không ghi metadata giả.
7. Thử scheduled job với service actor.
8. Thử async consumer với explicit audit context.
9. Thử tenant mismatch.
10. Kiểm tra các response DTO không lộ actor ngoài quyền.

## 67. Bài thực hành K — Audit history và outbox

1. Tạo bảng document_revisions.
2. Khi cập nhật Document, ghi một revision row trong cùng transaction.
3. Lưu actor, Instant, old/new title và request ID theo policy.
4. Commit và xác nhận cả Document/revision persisted.
5. Rollback và xác nhận cả hai không tồn tại như committed update.
6. Thêm outbox table cho event DocumentUpdated.
7. Ghi outbox cùng transaction.
8. Viết consumer đọc outbox với retry/idempotency.
9. Giả lập worker crash sau commit nhưng trước publish.
10. Chứng minh outbox còn row để retry.
11. Phân biệt last-modified fields với full history.

## 68. Bài thực hành L — Timezone và precision

1. Dùng Instant T0 có giây tròn.
2. Persist và đọc lại trên DB mục tiêu.
3. Dùng Instant có nanoseconds không tròn.
4. Ghi precision/rounding của DB/driver.
5. Tạo response hiển thị theo Asia/Ho_Chi_Minh.
6. Kiểm tra UTC Instant không đổi sau format.
7. Thử app server với default timezone khác.
8. Tránh dùng `LocalDateTime.now()` cho audit absolute timestamp.
9. Test clock đi lùi và policy monotonic.
10. Thêm unique ID khi sort theo updatedAt.

---

## 69. Checklist trước khi đưa vào production

| Câu hỏi | Cần chốt |
|---|---|
| createdAt nghĩa là mốc nào? | Insert time, processing time hay event time? |
| updatedAt nghĩa là mốc nào? | Business modification, flush, DB update hay commit? |
| createdBy/updatedBy lấy từ đâu? | Authenticated actor/service identity |
| Actor ID có stable không? | Không dùng display name dễ đổi |
| Có actor cho batch jobs không? | Service actor rõ ràng |
| Dùng Clock abstraction chưa? | Không static system time trong core domain |
| Unit test có assert exact Instant không? | Clock.fixed/MutableClock |
| Một CREATE có dùng cùng Instant không? | createdAt=updatedAt theo policy |
| No-op update có làm đổi updatedAt không? | Contract và test rõ |
| Có @Version cho concurrency không? | Timestamp không thay version |
| Có @Column(updatable=false) cho created fields không? | ORM bảo vệ bổ sung |
| Có database constraints không? | NOT NULL, FK, permission/trigger nếu cần |
| JPA callbacks có chạy trên write paths không? | Persist/dirty update vs bulk/native |
| Có Spring Data auditing không? | Listener, enable, DateTimeProvider, AuditorAware |
| Có hai nguồn timestamp không? | App vs DB trigger, chọn authority |
| Có test flush/clear không? | Persisted state chứ không chỉ object |
| Có test commit thật không? | Transaction outcome riêng |
| Có test rollback không? | Không để audit “ma” |
| Có integration DB mục tiêu không? | Precision, timezone, triggers, dialect |
| Có mutable clock trong test không? | Không dùng sleep |
| Có test async actor context không? | Thread propagation/explicit context |
| Có child collections trong aggregate không? | Parent audit nếu business yêu cầu |
| Có JPQL bulk/native writes không? | Stamp/trigger/version riêng |
| Có external writers không? | Coherence strategy |
| Có cần full history không? | Revision/Envers/trigger/CDC |
| Có external events không? | Outbox/after commit policy |
| Có soft delete không? | deletedAt/deletedBy |
| Có audit PII không? | Retention/access control |
| Có sort theo updatedAt không? | Index + unique tie-breaker |
| Có migrations/imports không? | Source vs imported timestamps |
| Có performance đo đạc không? | Avoid no-op writes/index churn |
| Có stress/concurrency test không? | Optimistic conflict winner metadata |

---

## 70. Các hiểu lầm phổ biến

### 70.1. “Đặt Instant.now() trong @PrePersist là đã kiểm thử được hoàn toàn”

Không. Callback có thể chạy đúng nhưng test chỉ kiểm tra khoảng thời gian tương đối, dễ flaky. Nếu cần deterministic test, inject Clock hoặc dùng nguồn thời gian kiểm soát được.

### 70.2. “@PreUpdate chạy sau mỗi save()”

Không. Callback gắn với UPDATE lifecycle, không phải tên method repository. Nếu không có dirty UPDATE, provider có thể không gọi.

### 70.3. “@PostUpdate là sau commit”

Không. Nó chạy ở lifecycle UPDATE, có thể xảy ra trước transaction outcome và rollback sau đó.

### 70.4. “flush tức là audit đã lưu bền vững”

Không. Flush phát SQL trong transaction nhưng vẫn có thể rollback.

### 70.5. “createdAt và updatedAt đều nên gọi Instant.now() riêng khi tạo”

Không cần. Nếu một creation event, lấy một Instant và gán cả hai rõ ràng hơn.

### 70.6. “createdBy lấy từ System.getProperty(user.name)”

Đó thường là user của tiến trình hệ điều hành, không phải authenticated actor nghiệp vụ.

### 70.7. “Client có thể tự gửi updatedBy”

Không nên tin untrusted input để ghi audit identity. Server cần nguồn actor đã xác thực.

### 70.8. “@Column(updatable=false) ngăn mọi SQL sửa createdAt”

Không. Nó ảnh hưởng SQL do ORM quản lý, không phải database constraint cho native/external writes.

### 70.9. “@Version và updatedAt dùng thay nhau”

Không. Version phục vụ concurrency detection; timestamp phục vụ mô tả thời gian, có thể trùng hoặc bị làm tròn.

### 70.10. “Bulk JPQL UPDATE sẽ tự gọi @PreUpdate cho từng row”

Không. Bulk DML bỏ qua entity lifecycle callbacks trên từng managed instance.

### 70.11. “Spring Data @CreatedDate thuộc chuẩn Jakarta Persistence”

Không. Đó là Spring Data auditing extension.

### 70.12. “Gắn @CreatedDate là đủ, không cần enable auditing”

Không. Cần listener và cấu hình Spring Data tương ứng.

### 70.13. “Clock.systemUTC() bảo đảm máy chủ nào cũng có giờ đúng”

Không. UTC convention không đồng bộ physical clocks. Cần hạ tầng time sync và policy clock skew.

### 70.14. “LocalDateTime có thể tự hiểu luôn là UTC”

Không. Nó không mang timezone/offset.

### 70.15. “DB default CURRENT_TIMESTAMP tự đổi trên mọi UPDATE”

Không. DEFAULT thường áp dụng khi INSERT; UPDATE cần trigger/statement/app logic riêng.

### 70.16. “Database-generated timestamp luôn có ngay trong entity sau persist”

Không. Có thể cần generated-value mapping hoặc refresh.

### 70.17. “Mở lại find trong cùng EntityManager chứng minh DB lưu đúng”

Không. L1 có thể trả cùng managed object. Dùng flush/clear hoặc context mới, hiểu L2.

### 70.18. “Một callback update ở parent chắc chắn chạy khi child collection thay đổi”

Không. SQL có thể chỉ cập nhật child/join table; cần test aggregate semantics.

### 70.19. “Mỗi callback tương ứng một thao tác người dùng”

Không. Callbacks gắn với lifecycle persistence, không phải trực tiếp với business command.

### 70.20. “Audit log chỉ cần updatedAt và updatedBy”

Chỉ đủ cho last-modified metadata, không đủ cho full history hoặc compliance trail.

### 70.21. “Gửi event từ @PostPersist bảo đảm không có event của rollback”

Không. Callback không phải sau commit.

### 70.22. “Spring AFTER_COMMIT listener bảo đảm gửi message dù server crash”

Không. Nếu cần guaranteed delivery, dùng transactional outbox/CDC hoặc cơ chế bền vững phù hợp.

### 70.23. “Hễ actor là thread-local nên async sẽ hoạt động”

Không. Context propagation phải được cấu hình/kiểm thử hoặc truyền explicit.

### 70.24. “Không cần test trên DB production-target”

Precision, timestamp mapping, trigger behavior và transaction semantics khác nhau giữa DBMS. Integration test trên target giúp phát hiện lỗi mà in-memory DB không tái hiện.

---

## 71. Câu hỏi ôn tập

1. createdAt, updatedAt, createdBy và updatedBy khác nhau ở ý nghĩa nào?
2. Vì sao “thời điểm sửa” cần được định nghĩa trước khi gắn annotation?
3. @PrePersist được gọi liên quan thao tác nào?
4. @PreUpdate có chạy khi không có dirty UPDATE không?
5. @PostUpdate có thể chạy trước khi transaction rollback không?
6. Tại sao @PostUpdate không thích hợp gửi message external ngay lập tức?
7. Bulk JPQL UPDATE có gọi @PreUpdate từng entity không?
8. Vì sao insert/update native SQL không kích hoạt listener JPA?
9. Có những lựa chọn nguồn thời gian nào ở app/DB?
10. Vì sao dùng Clock thay Instant.now() trong logic cần test?
11. Cách tạo Clock.fixed tại một Instant là gì?
12. MutableClock giúp test create/update ra sao?
13. Vì sao test không cần Thread.sleep()?
14. Tại sao createdAt và updatedAt lúc CREATE nên dùng cùng một Instant theo một số contracts?
15. CurrentActor abstraction có lợi ích gì?
16. Vì sao không dùng tên hiển thị hoặc user OS làm audit ID?
17. Với scheduled job không có web principal, phải thiết kế actor thế nào?
18. Actor trong async thread có tự xuất hiện không?
19. Có nên nhận updatedBy từ JSON request không?
20. @Column(updatable=false) bảo vệ được ở mức nào?
21. Vì sao @Version không thay bằng updatedAt?
22. Timestamp precision thấp ảnh hưởng concurrent version check thế nào?
23. Service stamping giúp deterministic testing thế nào?
24. Điểm yếu của service stamping khi thêm một write path mới là gì?
25. Tại sao cần flush rồi clear khi test persistence?
26. Flush có bằng commit không?
27. Test @Transactional rollback cuối test chứng minh điều gì?
28. Làm sao test commit thật và transaction visibility?
29. Khi rollback, object Java sau mutate có nên dùng để khẳng định persisted state không?
30. Spring Data @CreatedDate và @LastModifiedDate thuộc framework nào?
31. Vai trò của @EnableJpaAuditing là gì?
32. AuditorAware cung cấp dữ liệu nào?
33. DateTimeProvider giúp test thế nào?
34. Nếu AuditorAware trả empty mà createdBy nullable=false, chuyện gì có thể xảy ra?
35. Khi dùng DB DEFAULT CURRENT_TIMESTAMP, tại sao Java field có thể chưa có giá trị ngay?
36. Trigger và service cùng gán timestamp có thể gây lỗi gì?
37. DB CURRENT_TIMESTAMP có chắc là commit timestamp không?
38. Vì sao LocalDateTime không đủ diễn đạt một instant?
39. Tại sao dùng Instant cho audit thường phù hợp hơn?
40. Database precision ảnh hưởng assertEquals như thế nào?
41. Clock.systemUTC có giải quyết clock skew không?
42. Khi clock đi lùi, nên chọn policy ra sao?
43. Tại sao timestamp không nên là unique sort key duy nhất?
44. Parent @PreUpdate có chắc chạy khi thêm OrderLine không?
45. Nếu aggregate yêu cầu parent updatedAt thay đổi, nên làm gì?
46. Audit history khác last-modified metadata ra sao?
47. Khi nào nên dùng revision table/Envers/CDC?
48. Transactional outbox giải quyết vấn đề gì?
49. After-commit event handler có bảo đảm delivery khi process crash không?
50. Trong multi-tenant app, actor identity và tenant context phải thiết kế thế nào?
51. Soft delete cần metadata gì?
52. Hard delete có để lại last-modified columns không?
53. Vì sao bulk update phải xử lý version riêng?
54. Hai transactions update cùng entity cần test optimistic conflict thế nào?
55. Final audit metadata sau conflict thuộc actor nào?
56. Vì sao no-op update cần test?
57. Có nên gán updatedAt trong mọi GET request không?
58. Data migration cần phân biệt createdAt với sourceCreatedAt thế nào?
59. Kiểm thử exact timestamps có thể chặt hơn time-window assertions khi nào?
60. Một test matrix về audit metadata tối thiểu cần những scenarios nào?

---

## 72. Bảng ghi nhớ cuối bài

| Nhu cầu | Giải pháp gợi ý | Giới hạn cần nhớ |
|---|---|---|
| createdAt/updatedAt dễ unit test | Service + injected Clock | Phải bao phủ mọi write path |
| createdBy/updatedBy test được | CurrentActor abstraction | Security context thật có nhiều variants |
| Tự stamp khi JPA insert/update | @PrePersist/@PreUpdate | Không chạy cho bulk/native |
| Dùng Spring Data | @CreatedDate/@LastModifiedDate + AuditingEntityListener | Enable auditing, provider, actor |
| Test thời gian chính xác | Clock.fixed/MutableClock | DB precision cần kiểm chứng |
| Test persisted state | flush/clear + reload | Flush chưa commit |
| Test rollback | TransactionTemplate/EM khác | Đừng đọc stale object |
| Cột tạo chỉ được ghi một lần | @Column(updatable=false) | Không bảo vệ native SQL |
| Mọi writers cần DB timestamp | DEFAULT/trigger | App state cần refresh, DB-specific |
| Tránh lost update | @Version/locking | updatedAt không đủ |
| Khi child đổi, parent cũng được xem là đổi | Touch aggregate root | Không dựa parent callback |
| Bulk JPQL | Set audit fields explicit, version policy | Bypass entity listeners |
| Lưu full lịch sử | Revision table/Envers | Khác four metadata columns |
| Gửi event tin cậy sau commit | Transactional outbox | Worker retry/idempotency |
| Dùng UTC đúng | Instant + timezone conversion tại boundary | Không tự sửa clock skew |
| Audit actor bảo mật | Server-authenticated stable ID | Không tin client field |
| Sắp theo updatedAt | ORDER BY updatedAt, id | Timestamp có thể trùng |
| Đo hiệu năng | SQL logs/metrics | Tránh no-op writes, index churn |

### Sơ đồ quyết định

```text
                   CẦN AUDIT METADATA
                           |
                           v
             Ai là nguồn thời gian/actor?
                /           |           \
           Application    Spring Data     Database
                |         auditing         |
                v             |            v
       Clock + Actor       DateTimeProvider DEFAULT/trigger
       domain/service      AuditorAware     refresh/mapping
                |             |            |
                +-------------+------------+
                              |
                              v
                    Lifecycle write paths
                   /          |          \
            JPA persist    managed UPDATE  bulk/native
                 |             |             |
                 v             v             v
         @PrePersist?     @PreUpdate?     bypass callbacks
                 |             |             |
                 +-------------+-------------+
                               |
                               v
                     TRANSACTION OUTCOME
                        /          \
                     COMMIT       ROLLBACK
                       |             |
                       v             v
                Persist metadata   No committed
                + optional history  change
                       |
                       v
            Test persisted state with new EM
                       |
                       v
             Test concurrency + clock + actor
```

**Nguyên tắc cuối bài:** audit metadata có chất lượng không được quyết định bởi việc chọn `@PreUpdate` hay `@CreatedDate`, mà bởi **hợp đồng ý nghĩa của các trường, nguồn thời gian/actor đáng tin, coverage của tất cả write paths và phép thử transaction thực tế**. Muốn thời gian có thể kiểm thử, hãy tiêm `Clock` hoặc `DateTimeProvider` và dùng mốc cố định; muốn dấu vết actor đáng tin, hãy lấy từ auth/service context qua abstraction; muốn chắc dữ liệu đã lưu, hãy `flush`, tách persistence context và kiểm tra committed state; muốn full history hoặc external events, hãy thiết kế revision/outbox phù hợp. Callback JPA hữu ích nhưng **không phải after commit, không xử lý mọi bulk/native writes và không thay optimistic locking**. Khi những ranh giới đó được hiểu rõ, hệ thống mới có audit fields chính xác, dễ tái hiện và đủ cơ sở để mở rộng.

