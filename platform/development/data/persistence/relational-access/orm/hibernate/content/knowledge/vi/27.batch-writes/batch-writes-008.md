# Các bảo đảm, callback và khả năng batching của StatelessSession theo phiên bản

## 1. Đặt vấn đề: ghi hàng loạt không chỉ là gọi insert() nhiều lần

Khi nhập một triệu dòng giao dịch, đồng bộ dữ liệu từ hệ thống khác hoặc sửa hàng trăm nghìn bản ghi, cách làm thông thường:

```java
for (ImportRow row : rows) {
    entityManager.persist(toEntity(row));
}
```

có thể giữ quá nhiều managed entities trong Persistence Context, làm tăng memory, dirty checking và thời gian flush. Hibernate có các lựa chọn khác nhau để xử lý:

1. **Session stateful + JDBC batching + flush/clear định kỳ** khi cần entity lifecycle đầy đủ.
2. **StatelessSession** khi muốn làm việc theo từng lệnh tường minh, không giữ first-level cache.
3. **Bulk HQL/Criteria/native SQL** khi muốn cập nhật/xóa cả một tập hàng bằng predicate mà không materialize từng entity.
4. **JDBC hoặc cơ chế bulk import của database** khi workload đòi hỏi tối ưu thấp hơn mức ORM.

Vấn đề dễ nhầm là xem `StatelessSession` như “Session nhanh hơn nhưng mọi bảo đảm giữ nguyên”. Thực tế, đây là **một mô hình lập trình khác**: không có Persistence Context quản lý entity, không dirty checking, không cascades theo lệnh, cùng những thay đổi đáng kể về **callback, second-level cache và batching giữa Hibernate 6.x và 7.x**.

Ví dụ mong muốn của một job:

```text
CSV / message stream
      |
      v
validate / normalize input
      |
      v
StatelessSession.insert(...) hoặc insertMultiple(...)
      |
      v
Database constraints + transaction
      |
      v
checkpoint / metrics / audit
```

Muốn thiết kế đúng, phải trả lời:

- Thao tác nào được bảo đảm thực thi khi method trả về?
- Entity có còn được Hibernate theo dõi sau `insert()`/`get()` không?
- `@PrePersist`, `@PostPersist`, interceptor và entity listeners có chạy không?
- `hibernate.jdbc.batch_size` ảnh hưởng StatelessSession ở phiên bản nào?
- `insertMultiple()` có đồng nghĩa một SQL statement hoặc một commit không?
- Nếu exception xảy ra, transaction sẽ rollback tự động hay caller phải quyết định?
- Cache, optimistic locking, DB triggers và foreign keys còn bảo vệ những điều gì?

**Phạm vi phiên bản:** bài dùng API Hibernate ORM 6.0–6.6 và 7.0–7.4 làm ví dụ đối chiếu. Đây là tính năng Hibernate-specific, không phải `jakarta.persistence.EntityManager` chuẩn. Hibernate đang được nâng cấp liên tục; với code production, tra đúng Javadocs **của bản Hibernate thực tế trên classpath** và xác nhận bằng integration tests.

## 2. StatelessSession là gì?

`org.hibernate.StatelessSession` là API command-oriented để làm việc với các entity instance **không nằm trong first-level Persistence Context**.

Ví dụ Hibernate 6.6:

```java
import org.hibernate.SessionFactory;
import org.hibernate.StatelessSession;
import org.hibernate.Transaction;

try (StatelessSession ss = sessionFactory.openStatelessSession()) {
    Transaction tx = ss.beginTransaction();
    try {
        OrderArchive archive = new OrderArchive();
        archive.setId(123L);
        archive.setDescription("Imported");

        ss.insert(archive);
        tx.commit();
    } catch (RuntimeException ex) {
        tx.rollback();
        throw ex;
    }
}
```

Entity vừa `insert` không trở thành managed instance được theo dõi dirty checking như khi dùng `Session.persist(...)`.

Ví dụ:

```java
ss.insert(archive);              // Lệnh ghi tường minh.
archive.setDescription("Later"); // Chỉ sửa đối tượng Java.
// Không có auto dirty checking.
ss.update(archive);              // Cần lệnh ghi tường minh nếu muốn update.
```

**Không có `flush()` theo mô hình stateful** vì StatelessSession không giữ hàng chờ thông qua transactional write-behind/diff-based dirty checking của Persistence Context. Một lệnh `insert`/`update`/`delete` thông thường hướng tới SQL trực tiếp; riêng **automatic JDBC batching** có thể trì hoãn việc gửi một số statement khi được chủ động bật, nên phần batching phải được xét riêng.

## 3. So sánh Session và StatelessSession theo trách nhiệm

| Chủ đề | Session / EntityManager stateful | StatelessSession |
|---|---|---|
| First-level Persistence Context | Có | Không |
| Identity map cho entity được load | Có | Không |
| Dirty checking | Có | Không |
| Tự update khi thay đổi managed field rồi flush | Có | Không |
| Transactional write-behind | Có | Không theo mô hình stateful |
| `persist`/`merge`/`remove` | Model quản lý entity | Thay bằng command `insert`/`update`/`delete` phù hợp API |
| Cascade qua association mapping | Có khi cấu hình phù hợp | Không tự cascade theo các command |
| Collection persistence | Hibernate theo dõi collection managed | Không tự theo dõi collection changes |
| Lazy associations | Tự kích hoạt theo mapping/context | Chủ yếu dùng fetch rõ ràng, không giả định transparent loading |
| L2 cache | Tùy cache mode/config | **Khác nhau theo phiên bản**: 6.x tránh cache; 7.x dùng L2 mặc định |
| Lifecycle callbacks/interceptor | Đường sự kiện stateful bình thường | **Khác nhau theo phiên bản và loại callback** |
| JDBC batch mặc định | Phụ thuộc `hibernate.jdbc.batch_size` và mapping | **Khác nhau theo phiên bản**; 7.x có explicit batching riêng |
| Memory cho job nhiều hàng | Cần flush/clear hoặc ngắt context | Không tích lũy managed identity map |

Không đọc bảng này như cam kết rằng StatelessSession “bỏ qua toàn bộ Hibernate”. Nó vẫn dùng mapping, type conversion, dialect, JDBC, transaction, entity metadata và có thể dùng cache/callback ở các phiên bản nhất định.

## 4. Ba loại “batch” cần tách bạch

Từ “batch” thường bị dùng cho ba cơ chế khác nhau.

### 4.1. Xử lý nhiều object ở vòng lặp Java

```java
for (ImportRow row : rows) {
    ss.insert(map(row));
}
```

Đây là một **bulk-processing loop**. Nếu mỗi `insert` chạy một statement riêng, số lệnh và round trip vẫn có thể gần bằng số object. Vòng lặp Java tự nó không đồng nghĩa JDBC batching.

### 4.2. JDBC batching

Driver được gửi nhiều sets of parameters cho một statement tương thích:

```text
INSERT INTO archived_orders(id, description) VALUES (?, ?)
  batch values: (1, "A")
  batch values: (2, "B")
  batch values: (3, "C")
```

Mục tiêu là giảm overhead của việc gửi/executing nhiều lần statement tương tự. JDBC batch **không bảo đảm** chỉ có một SQL statement, một network round trip hay một transaction.

### 4.3. Bulk DML theo predicate

```hql
update OrderArchive a
set a.status = :newStatus
where a.createdAt < :cutoff
```

Một query có thể cập nhật rất nhiều row trực tiếp trong DB, **không** cần tạo một Java object cho từng row. Đây là set-based operation, khác với danh sách `insert(entity)` và khác với JDBC batching.

### So sánh ngắn

| Cách | Input | Công việc chính | Trách nhiệm |
|---|---|---|---|
| Loop `ss.insert(entity)` | N entity objects | N lệnh entity command | Chọn thứ tự, transaction, event/callback theo version |
| JDBC batch | N parameter sets | Nhóm lệnh SQL tương thích | Driver, batch size, update counts |
| `ss.insertMultiple(list)` (7.x) | Một list entity | Explicit multi-operation API | Hibernate tổ chức thao tác theo API |
| HQL `update ... where ...` | Predicate | Bulk DB mutation | Cẩn thận lifecycle/cache/version |
| DB COPY/bulk loader | Stream/file | Vendor bulk import | Dialect, validation và staging riêng |

## 5. Mốc phiên bản: không nói chung “StatelessSession luôn bỏ qua callbacks”

**Đây là phần quan trọng nhất của bài.** Các nguồn tài liệu Hibernate đã thay đổi theo version, thậm chí ở 6.6 có chỗ tài liệu khái quát và Javadocs biểu đạt khác nhau. Không nên biến một câu trong tài liệu của bản cũ thành quy tắc cho mọi bản.

| Dòng phiên bản | Cache | Callback/interceptor | Batching |
|---|---|---|---|
| **6.0–6.5** | Không tương tác L2 theo mô tả API | Javadocs mô tả bypass event model, lifecycle callbacks và interceptors | Không có nhóm `insertMultiple/updateMultiple/deleteMultiple` của 7.0; kiểm tra hành vi batch ở bản thực tế |
| **6.6** | Javadocs mô tả không tương tác L2 | Javadocs `StatelessSession` ghi rõ `@PostPersist`, `@PostUpdate`, `@PostRemove`; `Interceptor` cũng có callback dành cho stateless; User Guide lại có đoạn mô tả “bypass event model/interceptors” | Chưa có explicit multi-methods của 7.0; không suy diễn batch chỉ từ việc đặt property |
| **7.0 trở lên** | Dùng second-level cache mặc định; có thể đặt `CacheMode.IGNORE` | Javadocs mô tả một số Post callbacks và `Interceptor` dạng stateless | `hibernate.jdbc.batch_size` **không tác động** StatelessSession; ưu tiên `insertMultiple`/`updateMultiple`/`deleteMultiple`; có thể bật automatic batching qua `setJdbcBatchSize` |

Nguồn gốc sự khác biệt:

- Hibernate ORM **6.5 Javadocs** còn nói thao tác StatelessSession bỏ qua lifecycle callbacks và interceptors.
- Hibernate ORM **6.6 Javadocs** mô tả callback `PostPersist`/`PostUpdate`/`PostRemove` sau thao tác thành công; Javadocs `Interceptor` có `onInsert`, `onUpdate`, `onUpsert`, `onDelete` cho StatelessSession.
- Hibernate **7.0 Migration Guide** ghi rõ thay đổi L2 cache mặc định và `hibernate.jdbc.batch_size` không còn tác động StatelessSession.
- Hibernate **7.x StatelessSession Javadocs** xác nhận các multi-method mới từ 7.0.

Vì thế, khi một framework/service dựa vào `@PrePersist` để sinh audit fields, `@PostPersist` để cập nhật state, hoặc một `Interceptor` để can thiệp SQL, **phải kiểm thử riêng callback được kỳ vọng** trên đúng artifact version. Không đưa chữ “callback” vào một khẳng định chung “có tất cả” hoặc “không có gì”.

## 6. Cách nhận biết Hibernate version thật của dự án

Không lấy phiên bản Spring Boot hoặc Hibernate Validator để đoán Hibernate ORM core. Dependency transitive, overrides và runtime packaging có thể làm lệch version dự tính.

Trong code Hibernate:

```java
import org.hibernate.Version;

String hibernateVersion = Version.getVersionString();
System.out.println("Hibernate ORM = " + hibernateVersion);
```

Có thể xem dependency tree/build lock theo Gradle/Maven của ứng dụng. API docs cần mở URL gắn version, ví dụ:

- `https://docs.hibernate.org/orm/6.5/javadocs/org/hibernate/StatelessSession.html`
- `https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/StatelessSession.html`
- `https://docs.hibernate.org/orm/7.4/javadocs/org/hibernate/StatelessSession.html`

Không dựa vào `/current/` một cách mù quáng nếu dự án còn chạy 6.4 hoặc 6.6. Một thay đổi hành vi giữa versions có thể ảnh hưởng cả correctness lẫn hiệu năng.

## 7. First-level cache và identity map: điều StatelessSession không có

Với `Session` stateful:

```java
OrderArchive a = session.find(OrderArchive.class, 100L);
OrderArchive b = session.find(OrderArchive.class, 100L);

// Trong cùng Persistence Context, thường a == b.
```

`Session` quản lý cùng một entity identity bằng cùng managed instance trong một context.

Với `StatelessSession`:

```java
OrderArchive a = ss.get(OrderArchive.class, 100L);
OrderArchive b = ss.get(OrderArchive.class, 100L);

// Không có identity map bảo đảm a == b.
```

Hai object có thể đại diện cùng database row mà không cùng Java identity, hoặc chứa state lấy ở hai thời điểm khác nhau. Đây là **data aliasing**.

### Tại sao data aliasing đáng lo?

```java
OrderArchive older = ss.get(OrderArchive.class, 100L);
OrderArchive newer = ss.get(OrderArchive.class, 100L);

older.setDescription("A");
newer.setDescription("B");

ss.update(older);
ss.update(newer);
```

Hai lệnh update tường minh có thể viết lần lượt các state khác nhau lên cùng hàng. Không có một managed object duy nhất và một dirty checker để hợp nhất ý định.

Trong bulk job, cần:

- Không xử lý cùng ID vô tình nhiều lần.
- Xác định duplicate policy của dữ liệu nhập.
- Cân nhắc version/optimistic locking hoặc SQL condition.
- Sắp xếp/khóa/deduplicate input theo business key nếu cần.
- Không dùng `==` để quyết định hai entity có đại diện cùng row hay không.

## 8. Không dirty checking, không tự flush thay đổi

`StatelessSession#get()` trả một detached object:

```java
try (StatelessSession ss = factory.openStatelessSession()) {
    Transaction tx = ss.beginTransaction();
    try {
        OrderArchive order = ss.get(OrderArchive.class, 100L);

        order.setDescription("Recalculated");

        // Chỉ thay đổi đối tượng Java, chưa có lệnh update.
        ss.update(order);

        tx.commit();
    } catch (RuntimeException ex) {
        tx.rollback();
        throw ex;
    }
}
```

Không có chuỗi:

```text
get -> sửa field -> commit -> auto dirty checking -> SQL update
```

như stateful Session.

Thay vào đó:

```text
get -> sửa field -> update(entity) -> SQL update
```

Điều này vừa giúp predictable operation flow vừa khiến caller phải chịu trách nhiệm gọi đủ lệnh.

### Có nên gọi flush()/clear() mỗi 50 hàng?

Đây là kỹ thuật của `Session` stateful để giới hạn Persistence Context:

```java
session.flush();
session.clear();
```

**Không áp dụng nguyên mẫu này cho StatelessSession**: không có stateful first-level cache để clear và không có flush dirty changes tương ứng. Batch size, transaction chunk size và resource lifecycle phải được thiết kế bằng những khái niệm phù hợp StatelessSession.

## 9. Không cascade entity operations qua association

Giả sử:

```java
@Entity
public class ImportBatch {
    @Id
    private Long id;

    @OneToMany(
        mappedBy = "batch",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<ImportItem> items = new ArrayList<>();
}
```

Với stateful Session, `persist(batch)` có thể cascade `PERSIST` tới ImportItem theo mapping.

Với stateless:

```java
ss.insert(batch);
```

**Không tự động insert toàn bộ `batch.getItems()`** chỉ vì có `cascade = CascadeType.ALL`. Đó là giới hạn thiết kế đã được nhấn mạnh trong Javadocs.

### Cách xử lý tường minh

```java
ss.insert(batch);

for (ImportItem item : batch.getItems()) {
    item.setBatch(batch);
    ss.insert(item);
}
```

Thứ tự insert phải phù hợp foreign keys, ID generation và constraints. Nếu child tham chiếu parent bằng ID generated, cần kiểm tra identifier được tạo/gán đúng lúc theo mapping.

### Database cascade vẫn khác ORM cascade

`ON DELETE CASCADE` trên foreign key là cơ chế **database**. Nó vẫn có thể chạy khi một câu DELETE từ stateless session xóa parent, dù `CascadeType.REMOVE` của ORM không được áp dụng.

Không nhầm:

- ORM cascade = Hibernate đi qua entity associations để phát thêm entity operations.
- DB cascade = database tự thực thi hành vi theo foreign key constraint.

Việc DB cascade xóa child không đồng nghĩa callbacks trên các child Java object sẽ được gọi.

## 10. Collections không được tự quản lý

Ví dụ:

```java
ImportBatch batch = ss.get(ImportBatch.class, 10L);
batch.getItems().add(new ImportItem());

// Không có persistent collection dirty checking.
```

StatelessSession không theo dõi collection changes để tự sinh INSERT/DELETE cho các phần tử như stateful Session. Nếu cần ghi child rows, phải thực hiện các thao tác phù hợp trực tiếp trên từng child hoặc chọn HQL/JDBC/native SQL.

Một số association lazy có thể được fetch tường minh:

```java
ss.fetch(batch.getItems());
```

`fetch(Object)` dùng để initialize lazy association/proxy khi mapping và phiên bản hỗ trợ. **Nạp association không đồng nghĩa bật collection dirty tracking hoặc cascade**.

Với use case cần sửa cả object graph phức tạp, stateful `Session` thường phù hợp hơn StatelessSession.

## 11. Callback có những loại nào?

Từ “callback” được dùng cho nhiều cơ chế khác nhau:

### 11.1. Jakarta Persistence entity callbacks

Các annotation thường gặp:

```java
@PrePersist
@PostPersist
@PreUpdate
@PostUpdate
@PreRemove
@PostRemove
@PostLoad
```

Có thể nằm trên entity hoặc trên listener class trong `@EntityListeners`.

### 11.2. Hibernate Interceptor

`org.hibernate.Interceptor` có các method cho thao tác stateful và các callback dành riêng cho stateless như `onInsert`, `onUpdate` và `onUpsert` ở những phiên bản tương ứng.

### 11.3. Hibernate event system

Các listener nội bộ như pre-insert, post-insert và những event pipeline stateful. Không coi tất cả đều tương đương JPA annotated callbacks hoặc `Interceptor`.

### 11.4. Database trigger

Trigger `BEFORE INSERT`, `AFTER UPDATE` v.v. là **database feature**, không phải JPA/Hibernate callback. Nếu SQL thật được gửi đến database và trigger đã được cấu hình, trigger có thể chạy theo semantics của DB bất kể ORM event model.

### 11.5. Application/domain callbacks

Method do ứng dụng tự gọi:

```java
validate(row);
normalize(row);
ss.insert(entity);
emitImportResult(entity.getId());
```

Đây là logic ứng dụng tường minh; luôn dễ kiểm soát hơn việc phụ thuộc vào một callback provider-specific nếu invariant quan trọng cho job.

**Không được dùng một kết quả test “@PostPersist chạy” để kết luận rằng @PrePersist, Interceptor, Hibernate event listener và DB trigger đều có cùng behavior.**

## 12. Điểm khác biệt 6.5 với 6.6 về callback

Tài liệu Javadocs 6.5 mô tả StatelessSession bypass:

```text
Hibernate event model
Lifecycle callbacks
Interceptors
```

Ở 6.6, **Javadocs interface đã mô tả rõ**:

- `insert(entity)`: `@PostPersist` callback được kích hoạt khi thao tác thành công.
- `update(entity)`: `@PostUpdate` callback được kích hoạt khi thao tác thành công.
- `delete(entity)`: `@PostRemove` callback được kích hoạt khi thao tác thành công.
- `Interceptor` Javadocs phân biệt callback cho stateful với stateless.

Đồng thời, **6.6 User Guide phần batching** vẫn có mô tả khái quát rằng stateless operations bypass Hibernate event model và interceptors.

### Đọc tài liệu mâu thuẫn như thế nào?

1. Đọc **Javadocs của interface/method chính xác** trên bản đang dùng.
2. Kiểm tra callback mà ứng dụng thực sự yêu cầu (`Pre` hay `Post`? entity listener hay Interceptor?).
3. Tạo integration test nhỏ với đúng Hibernate runtime, DB, mapping và callback class.
4. Coi hành vi quan sát được cộng contract phiên bản là cơ sở thiết kế.
5. Với invariant trọng yếu, bảo đảm bằng service validation/DB constraint, không chỉ trông chờ callback có lịch sử thay đổi.

**Không kết luận rằng từ 6.6 mọi @Pre... callback đều được hỗ trợ** chỉ vì Javadocs ghi các @Post... callback. Cũng không kết luận “StatelessSession không có bất cứ callback nào” khi dùng Javadocs 6.6+.

## 13. Tại sao @PostPersist không thể thay thế @PrePersist?

Ví dụ entity:

```java
@Entity
public class OrderArchive {
    @Id
    private Long id;

    private Instant importedAt;

    @PrePersist
    public void setImportedAt() {
        importedAt = Instant.now();
    }
}
```

Nếu batch job phụ thuộc `@PrePersist` để điền cột `imported_at NOT NULL`, một khác biệt callback giữa version có thể khiến INSERT thất bại hoặc dữ liệu bị NULL.

### Cách vững hơn cho import stateless

```java
OrderArchive entity = new OrderArchive();
entity.setId(row.id());
entity.setImportedAt(clock.instant());
entity.setDescription(row.description());

validateRequiredFields(entity);
ss.insert(entity);
```

Ở đây dữ liệu bắt buộc được gán **trước lệnh insert**, độc lập với việc `@PrePersist` được gọi hay không.

Nếu hệ thống cần bảo đảm mạnh hơn, thêm:

```sql
imported_at TIMESTAMP NOT NULL
```

hoặc default/database trigger phù hợp. DB constraint là lớp bảo vệ cuối cùng ngay cả khi application code có bug.

### Callback sau SQL không phải after-commit callback

Nếu một `@PostPersist` được gọi sau INSERT thành công, transaction vẫn có thể rollback. Không nên:

```java
@PostPersist
void sendEmail() {
    externalEmailService.send(...);
}
```

rồi giả định email chỉ gửi khi transaction đã commit.

Với tác vụ external side effect, dùng transactional outbox hoặc cơ chế after-commit được thiết kế riêng; callback “Post” chỉ nói về lifecycle operation, **không tự bảo đảm durable commit**.

## 14. Thiết kế bài test callback theo ma trận

Entity thử nghiệm:

```java
@Entity
@Table(name = "callback_probe")
public class CallbackProbe {
    @Id
    private Long id;

    private String description;

    @Transient
    private final List<String> events = new ArrayList<>();

    @PrePersist
    void prePersist() { events.add("prePersist"); }

    @PostPersist
    void postPersist() { events.add("postPersist"); }

    @PreUpdate
    void preUpdate() { events.add("preUpdate"); }

    @PostUpdate
    void postUpdate() { events.add("postUpdate"); }

    @PreRemove
    void preRemove() { events.add("preRemove"); }

    @PostRemove
    void postRemove() { events.add("postRemove"); }
}
```

Đây là mẫu để quan sát callback trong **cùng instance mà job truyền vào**. Lớp entity thực tế cần constructor, getter và cách inject recorder phù hợp nếu muốn ghi nhận callback trong lifecycle listener khác. Một test khác có thể dùng static/test-scoped recorder để quan sát instance được Hibernate tạo khi query.

Test mô hình:

```java
CallbackProbe probe = new CallbackProbe();
probe.setId(1L);
probe.setDescription("first");

try (StatelessSession ss = factory.openStatelessSession()) {
    Transaction tx = ss.beginTransaction();
    try {
        ss.insert(probe);
        probe.setDescription("changed");
        ss.update(probe);
        ss.delete(probe);
        tx.commit();
    } catch (RuntimeException ex) {
        tx.rollback();
        throw ex;
    }
}

// Assert event list theo contract phiên bản đang test.
```

### Ma trận cần lập

| API | Callback trước | Callback sau | Interceptor | Ghi chú |
|---|---|---|---|---|
| `insert()` | `PrePersist`? | `PostPersist`? | `onInsert`? | Đánh dấu kết quả đúng phiên bản |
| `update()` | `PreUpdate`? | `PostUpdate`? | `onUpdate`? | Phân biệt với dirty checking |
| `delete()` | `PreRemove`? | `PostRemove`? | `onDelete`? | Kiểm tra DB cascade riêng |
| `get()` | — | `PostLoad`? | `onLoad`? | Có thể khác so với `Session` |
| `insertMultiple()` (7.x) | Theo từng phần tử? | Theo từng phần tử? | Callback nào? | Không mặc định suy luận từ `insert()` |
| `upsert()` | Theo nhánh insert hay update? | Callback nào? | `onUpsert`? | Dialect và method riêng |

**Các dấu `?` là những yêu cầu kiểm chứng**, không phải khẳng định callback không chạy. Dùng `@EntityListeners` nếu dự án thực sự dùng listener; test chúng riêng với callback trên entity.

## 15. Hibernate Interceptor không phải JPA callback

Trong các Javadocs 6.6 và 7.x, `Interceptor` có nhóm method khác nhau cho stateful và stateless:

```text
Stateful:
  onLoad
  onPersist
  onRemove
  onFlushDirty

Stateless:
  onLoad
  onInsert
  onUpdate
  onUpsert
  onDelete
```

Đừng chuyển một interceptor dựa trên `onFlushDirty()` sang StatelessSession rồi mong method ấy được gọi sau khi `ss.update(entity)`. StatelessSession không tạo flush dirty event theo mô hình stateful.

Khi dùng interceptor để chuẩn hóa/audit/kiểm quyền, cần xác nhận:

- Callback stateless tương ứng có trong **phiên bản** không?
- Nó có được đăng ký vào `SessionFactory` hoặc Session hiện tại không?
- Callback chạy trước hay sau SQL và được phép sửa state nào?
- Khi batching tường minh, thứ tự callback so với execution có như kỳ vọng không?
- Callback có gọi Hibernate Session/lazy loading gây reentrancy hay không?

Một business invariant an toàn nên có DB constraints/logic ứng dụng tường minh, còn interceptor thường phù hợp cho concern kỹ thuật đã được kiểm thử.

## 16. Bảo đảm transaction: có DB transaction nhưng không phải auto-rollback

StatelessSession **không tự động xóa khái niệm transaction**. Nếu thao tác cần nguyên tử cùng nhau, dùng transaction bình thường:

```java
try (StatelessSession ss = factory.openStatelessSession()) {
    Transaction tx = ss.beginTransaction();
    try {
        ss.insert(first);
        ss.insert(second);

        tx.commit();
    } catch (RuntimeException ex) {
        tx.rollback();
        throw ex;
    }
}
```

Nếu database và transaction hỗ trợ, commit/rollback quyết định việc lưu hai INSERT.

### Hai điều cần phân biệt

- `ss.insert(entity)` chạy statement thành công **không đồng nghĩa transaction đã commit**.
- Javadocs StatelessSession nêu rằng exception trong stateless session **không tự động đánh dấu transaction rollback-only theo cùng cách stateful Session**.

Vì thế, khi một lệnh thất bại, code phải quyết định rollback/không tiếp tục; DB có thể tự chuyển transaction vào trạng thái aborted sau lỗi SQL (ví dụ một số PostgreSQL errors), và cách xử lý phụ thuộc dialect/transaction manager.

### Tại sao không tiếp tục “cố làm nốt” sau lỗi?

Nếu job đã insert 499 hàng rồi hàng 500 vi phạm unique constraint, tiếp tục insert hàng 501 mà không định nghĩa rõ failure semantics có thể khiến:

- Transaction đã bị database đánh dấu failed.
- Một phần dữ liệu được commit trái ý định khi dùng nhiều transaction.
- Audit/checkpoint sai lệch.
- Import retry gây duplicate.

Quy định trước:

1. **All-or-nothing**: rollback cả batch transaction khi một hàng lỗi.
2. **Best-effort theo chunk**: rollback chunk lỗi, chuyển lỗi sang dead-letter/quarantine, tiếp tục chunk khác.
3. **Idempotent retry**: dùng natural key/unique key và checkpoint để tránh ghi trùng.

Không để ngoại lệ vô tình quyết định chính sách nghiệp vụ.

## 17. Flush khác commit; stateless không miễn phí transaction

Trong stateful Session, `flush()` gửi pending changes nhưng không commit.

Trong StatelessSession, lệnh `insert`/`update` thông thường được thực hiện trực tiếp khi gọi; không cần flush để “đánh thức” dirty checking. Nhưng:

- Transaction vẫn giữ locks và rollback state đến commit.
- Driver/database vẫn phải xử lý WAL/redo, index, foreign keys.
- `setJdbcBatchSize()` có thể trì hoãn statement execution khi automatic batching được bật.
- Một explicit multi-operation method có thể thực thi theo lô trong phạm vi call.

**Đừng đo thời gian riêng từng `insert` rồi kết luận tất cả đã durable**. Muốn đo throughput chính xác, tính cả commit, batch execution và DB synchronization theo policy.

## 18. Batching trong Hibernate 6.x: đọc đúng giới hạn tài liệu

Trong Hibernate 6.x, stateless API truyền thống có `insert`, `update`, `delete`, `get` và từ 6.3 có `upsert` (incubating). Bộ method `insertMultiple`/`updateMultiple`/`deleteMultiple` được ghi là **Since 7.0**, nên không dùng chúng trong code muốn tương thích 6.6.

Các đoạn Javadocs/User Guide 6.6 nhấn mạnh command thường chạy đồng bộ và trực tiếp. Tuy nhiên, cấu hình batching chi tiết của stateless trong dòng 6.x, gồm ảnh hưởng của `hibernate.jdbc.batch_size` và `setJdbcBatchSize` trong một môi trường cụ thể, cần xác nhận bằng tài liệu/version/SQL trace của chính runtime. Hibernate 7.0 Migration Guide nói rõ behavior đã thay đổi ở 7.0; **không nên suy ngược rằng mọi bản 6.x có batching y hệt nhau**.

### Một vòng lặp 6.6

```java
try (StatelessSession ss = factory.openStatelessSession()) {
    Transaction tx = ss.beginTransaction();
    try {
        for (OrderArchive archive : chunk) {
            ss.insert(archive);
        }
        tx.commit();
    } catch (RuntimeException ex) {
        tx.rollback();
        throw ex;
    }
}
```

Đo:

- N statement executions hay ít hơn?
- Hibernate có dùng JDBC `addBatch/executeBatch` không?
- Round trips thế nào?
- Có statement bị execute ngay do ID generation hay khác SQL shape?
- Batch size và update counts có đúng kỳ vọng không?

Nếu muốn chắc chắn một mô hình tương thích 6.x có bulk JDBC behavior, có thể cân nhắc stateful Session với batching hoặc JDBC trực tiếp; đừng giả định loop stateless tự biến thành batch.

## 19. Hibernate 7.x: hibernate.jdbc.batch_size không tác động stateless

**Thay đổi chính thức từ Hibernate 7.0:** `hibernate.jdbc.batch_size` **không có tác dụng với StatelessSession**.

Điều này không phủ nhận cấu hình ấy còn quan trọng đối với **stateful Session batching**. Nó chỉ nói về đường thực thi stateless ở Hibernate 7.x.

Ví dụ cấu hình:

```properties
hibernate.jdbc.batch_size=50
```

Không được đọc configuration này rồi kết luận:

```java
for (OrderArchive entity : entities) {
    ss.insert(entity);
}
```

sẽ tự nhóm thành JDBC batches theo kích thước 50 khi dùng StatelessSession 7.x.

### Hai lựa chọn Hibernate 7.x

1. **Ưu tiên explicit multiple operations** `insertMultiple`, `updateMultiple`, `deleteMultiple`.
2. Nếu thật sự cần automatic batching, **chủ động** gọi `ss.setJdbcBatchSize(n)`, đồng thời chấp nhận semantics deferred execution.

Javadocs mô tả explicit multi-methods là phương án **preferred**; automatic batching có thể làm các operation vốn synchronous trở nên trì hoãn thực thi, khiến việc suy luận lỗi và thứ tự khó hơn.

## 20. Hibernate 7.x: insertMultiple(), updateMultiple(), deleteMultiple()

Từ Hibernate 7.0:

```java
import org.hibernate.StatelessSession;

List<OrderArchive> chunk = getNextChunk();

try (StatelessSession ss = factory.openStatelessSession()) {
    Transaction tx = ss.beginTransaction();
    try {
        ss.insertMultiple(chunk);
        tx.commit();
    } catch (RuntimeException ex) {
        tx.rollback();
        throw ex;
    }
}
```

Theo Javadocs 7.x, các method này thực hiện nhiều record operations dựa trên list được truyền vào:

```java
ss.insertMultiple(toInsert);
ss.updateMultiple(toUpdate);
ss.deleteMultiple(toDelete);
```

Các API được đánh dấu `@Incubating` ở một số phiên bản 7.x; cần kiểm tra API stability khi nâng cấp.

### Những điều KHÔNG được suy luận

- Một `insertMultiple(list)` **không bảo đảm một SQL INSERT duy nhất**.
- Không bảo đảm một lần gọi JDBC hay một round-trip duy nhất.
- Không bảo đảm tự commit sau method.
- Không bảo đảm cascade relationship graph.
- Không bảo đảm mọi callback stateful đều chạy.
- Không bảo đảm không gặp vấn đề ID generation/DB constraints.

**Danh sách nhiều entity** là phạm vi explicit operation; các statement thực tế và cách batching do Hibernate/driver/dialect quyết định.

### Thứ tự trong list

Javadocs mô tả xử lý theo thứ tự entity trong list. Nhưng cần phân biệt **thứ tự lập trình** và **thứ tự record visible giữa các transaction**. DB concurrency, triggers, retries và isolation vẫn có thể ảnh hưởng kết quả quan sát.

Nếu parent/child cần thứ tự insert vì foreign key, nên tách phases có chủ đích và kiểm chứng SQL/constraints.

## 21. Hibernate 7.x: upsertMultiple() và các trường hợp khác

Javadocs 7.4 còn có:

```java
ss.upsert(entity);
ss.upsertMultiple(entities);
```

`upsertMultiple` được ghi từ 7.0. `upsert` là operation với semantics insert-or-update theo database/dialect, không giống `merge` của stateful Session.

Điểm cần lưu ý:

- `upsert` không thực hiện generated-ID creation trong đường này và yêu cầu identifier được gán phù hợp.
- Không xem upsert là cơ chế optimistic concurrency tự động.
- Cần bảo đảm unique key/ID và conflict policy đúng.
- Một DB có thể dùng SQL `MERGE` hoặc cú pháp tương đương theo dialect.
- Khi dữ liệu nhập có duplicate business keys, xác định rõ “last wins”, reject hay merge theo trường.
- Triggers và constraints DB vẫn áp dụng.

Không dùng `upsertMultiple` để bỏ qua thiết kế idempotency; nó chỉ là primitive data operation.

## 22. Automatic batching bằng setJdbcBatchSize(): đánh đổi tính đồng bộ

Hibernate 7.x Javadocs cho phép bật automatic JDBC batching tường minh:

```java
try (StatelessSession ss = factory.openStatelessSession()) {
    ss.setJdbcBatchSize(32);

    Transaction tx = ss.beginTransaction();
    try {
        for (OrderArchive archive : chunk) {
            ss.insert(archive);
        }
        tx.commit();
    } catch (RuntimeException ex) {
        tx.rollback();
        throw ex;
    }
}
```

Mẫu này **khác** ví dụ bình thường ở cách gửi SQL:

```text
Không automatic batching:
  insert(a) -> execute SQL a
  insert(b) -> execute SQL b
  insert(c) -> execute SQL c

Có automatic batching:
  insert(a) -> queue JDBC params
  insert(b) -> queue JDBC params
  insert(c) -> queue JDBC params
  ...
  executeBatch khi đủ điều kiện/đóng batch/transaction completion
```

Hệ quả:

- Lỗi SQL của một record có thể xuất hiện **muộn hơn** method `insert(record)` tương ứng.
- Timing của ID generation, returning values và callbacks cần kiểm chứng.
- Không suy luận rằng lệnh sau đã nhìn thấy row của lệnh trước trước khi batch thực thi, trừ khi API/DB bảo đảm rõ.
- Khi debug, có thể khó xác định row gây lỗi nếu batch execution báo lỗi tổng hợp.

Vì thế, với Hibernate 7.x, **ưu tiên explicit multi-methods** cho những lô rõ ràng; chỉ bật automatic batching khi đã hiểu semantics và thực nghiệm với driver.

## 23. Cỡ lô JDBC và cỡ transaction là hai số khác nhau

Ví dụ:

```text
JDBC batch size       = 40 statements
Entity chunk size     = 200 entities
Transaction chunk     = 2,000 entities
Import job            = 2,000,000 entities
```

Các khái niệm:

| Kích thước | Tác động |
|---|---|
| JDBC batch size | Số parameter sets/SQL executions tương thích được nhóm |
| Explicit list size | Số entity đưa vào một `insertMultiple` |
| Transaction chunk size | Số thao tác commit/rollback cùng nhau |
| Read fetch size | Gợi ý JDBC driver fetch result rows; **không phải** JDBC write batch |
| Application queue buffer | Số input rows giữ trong RAM |

Một transaction chứa 2.000 entity có thể gọi 10 lần `insertMultiple(listOf200)`. Điều đó **không có nghĩa 10 commit**. Ngược lại, mỗi chunk 200 entity có thể là một transaction riêng nếu job được thiết kế như vậy.

Chọn transaction chunk theo:

- Giới hạn rollback/retry.
- Dung lượng redo/WAL và thời gian lock.
- Connection pool/timeout.
- Khả năng checkpoint.
- Idempotency và consistency của domain.

Đừng tăng mọi giá trị lên 10.000 chỉ vì muốn ít method calls.

## 24. Streaming dữ liệu lớn không cần giữ hết entity trong RAM

StatelessSession loại bỏ first-level cache, **nhưng application vẫn có thể tự giữ quá nhiều object**:

```java
List<OrderArchive> all = loadAllTenMillionRows();
ss.insertMultiple(all);
```

Nếu list chứa mười triệu object, memory có thể cạn dù Hibernate không quản lý entity.

Thay vào đó:

```text
Source reader
  -> đọc 200 rows
  -> validate/map
  -> insertMultiple(chunk)
  -> clear application list / release references
  -> đọc 200 rows tiếp
```

Mẫu Java:

```java
List<OrderArchive> chunk = new ArrayList<>(200);

for (ImportRow row : sourceRows) {
    chunk.add(toEntity(row));

    if (chunk.size() == 200) {
        ss.insertMultiple(chunk);
        chunk.clear();
    }
}

if (!chunk.isEmpty()) {
    ss.insertMultiple(chunk);
    chunk.clear();
}
```

Đoạn này dành cho Hibernate **7.x**, đặt bên trong transaction boundary được quản lý. `sourceRows` cần hỗ trợ đọc incremental; nếu nó đã là List chứa tất cả dữ liệu, lợi ích RAM sẽ giảm. Batch method phải hoàn tất thao tác liên quan đến list trước khi tái sử dụng/clear list; tuân theo hợp đồng của method cụ thể.

## 25. Không dùng scroll/stream mà quên đóng JDBC resources

Với một job đọc từ database rồi ghi sau xử lý:

```java
try (StatelessSession ss = factory.openStatelessSession()) {
    Transaction tx = ss.beginTransaction();
    try (ScrollableResults<OrderArchive> cursor =
            ss.createSelectionQuery(
                "from OrderArchive a order by a.id",
                OrderArchive.class
            ).scroll(ScrollMode.FORWARD_ONLY)) {

        while (cursor.next()) {
            OrderArchive record = cursor.get();
            transform(record);
            ss.update(record);
        }
        tx.commit();
    } catch (RuntimeException ex) {
        tx.rollback();
        throw ex;
    }
}
```

Ví dụ mô tả API kiểu Hibernate 6.6 và nên được điều chỉnh nếu phiên bản mới thay đổi `ScrollableResults`/query overload. Trong job lớn, **đọc và ghi vào cùng bảng đang được scroll** có thể có hạn chế driver/lock/cursor visibility; cần test đúng DB.

Lưu ý:

- Stateless không giữ first-level cache, nhưng JDBC cursor vẫn tiêu thụ connection/resources.
- `ScrollMode.FORWARD_ONLY` phù hợp đọc tiến nếu driver thực sự hỗ trợ server-side cursor/fetch size.
- Transaction có thể kéo dài trong suốt quá trình scroll.
- Không giữ cùng transaction/cursor hàng giờ mà không đánh giá timeout và lock/MVCC impact.
- Với job có resume/retry, keyset/chunked reads theo stable ID có thể đơn giản hơn giữ một cursor mở lâu.

## 26. ID generation và khả năng batching

Hibernate mapping ID có thể ảnh hưởng hiệu năng ghi lô.

### 26.1. Assigned ID

```java
@Id
private Long id;
```

Ứng dụng cấp ID trước khi gọi insert; Hibernate không cần đợi database trả ID mới. Đây có thể là điều kiện thuận lợi cho một số batch paths, nhưng cần bảo đảm uniqueness, consistency và ID allocation strategy.

### 26.2. SEQUENCE hoặc pooled generator

```java
@Id
@GeneratedValue(strategy = GenerationType.SEQUENCE)
private Long id;
```

Một số sequence/pooled generators có thể cấp nhiều ID hiệu quả hơn, tạo cơ hội batching. Nhưng chi tiết phụ thuộc database dialect, generator mapping và version.

### 26.3. IDENTITY

```java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
```

Ở một số Hibernate/JDBC paths, cần thực thi INSERT sớm để nhận generated ID; điều này có thể giới hạn batch execution. Các tính năng generated keys, RETURNING và multi-insert phụ thuộc provider/driver.

**Đừng chọn ID strategy chỉ để ép một benchmark JDBC batch tốt hơn** mà bỏ qua uniqueness, DB constraints, scale và migration.

## 27. Optimistic locking và @Version không phải dirty checking

Một entity:

```java
@Entity
public class OrderArchive {
    @Id
    private Long id;

    @Version
    private long version;

    private String description;
}
```

`@Version` là cơ chế concurrency mapping. Nhưng trong StatelessSession:

- Không có managed snapshot/diff để tự phát hiện field thay đổi.
- `update(entity)` là command explicit.
- Update SQL, version checks và generation behavior phụ thuộc mapping/version và operation.
- Với `upsert`/native/bulk DML, **không giả định** mọi optimistic locking semantics giống update managed entity.

### Kịch bản cần test

1. Hai transaction đọc cùng hàng và version.
2. Transaction A gọi `update(entityA)` và commit.
3. Transaction B dùng version cũ gọi `update(entityB)`.
4. Xem Hibernate có phát optimistic locking failure hay không.
5. Quan sát version của entity sau update và state DB.

Nếu use case có invariant “không được ghi đè cập nhật từ transaction khác”, phải đặt yêu cầu đó thành test; không chỉ quan sát có annotation `@Version` rồi kết luận là đủ cho mọi đường đi.

## 28. SQL constraints, triggers và transaction vẫn bảo vệ dữ liệu

Không có Persistence Context **không có nghĩa bỏ qua database constraints**.

Ví dụ:

```sql
CREATE TABLE archived_orders (
    id BIGINT PRIMARY KEY,
    external_key VARCHAR(80) NOT NULL UNIQUE,
    amount NUMERIC(18, 2) NOT NULL CHECK (amount >= 0),
    customer_id BIGINT NOT NULL REFERENCES customers(id)
);
```

Các quy tắc database:

- `PRIMARY KEY`.
- `UNIQUE`.
- `NOT NULL`.
- `CHECK`.
- `FOREIGN KEY`.
- Trigger và row-level security khi được cấu hình.

vẫn áp dụng khi SQL được thực thi qua StatelessSession.

### Entity validation có thể khác DB validation

Nếu ứng dụng dựa vào Bean Validation/Jakarta Persistence callback để validate entity trước `persist`, cần xem lại điểm tích hợp khi chuyển sang stateless. **Không mặc định `@NotNull`, `@Valid` và `@PrePersist` sẽ tạo cùng cơ chế auto-validation cho mọi stateless operation và phiên bản**.

Giải pháp an toàn:

- Gọi validator/domain validation tường minh trước lệnh.
- Duy trì DB constraints cho invariant bắt buộc.
- Xử lý exception và map lỗi về input record để báo cáo.

## 29. Second-level cache: thay đổi lớn từ Hibernate 7.0

### Hibernate 6.x

Theo Javadocs 6.5/6.6, StatelessSession không tương tác với second-level cache.

Hệ quả truyền thống:

- Tối ưu bulk streaming không phải duy trì entity trong L2 theo đường stateless.
- Đừng dùng một stateless import để kỳ vọng tự populate mọi cache entity.
- Nếu cùng lúc có stateful Sessions với cache, cần kiểm tra cache invalidation/staleness của thao tác dữ liệu khác.

### Hibernate 7.x

**StatelessSession dùng second-level cache mặc định**.

Trong bulk job nếu không muốn tương tác cache:

```java
try (StatelessSession ss = factory.openStatelessSession()) {
    ss.setCacheMode(CacheMode.IGNORE);
    // ... bulk operations ...
}
```

Theo migration guide:

- `CacheMode.IGNORE`: bỏ qua second-level cache theo hướng dẫn migration.
- `CacheMode.GET`: có thể phù hợp nếu muốn tránh cache puts nhưng vẫn cho phép reads.
- Các property `jakarta.persistence.cache.retrieveMode` và `jakarta.persistence.cache.storeMode` với `BYPASS` có thể được dùng theo hướng dẫn cache.

### Đừng nhầm các cache mode

`IGNORE` và `GET` không có cùng mục tiêu. Nếu job cập nhật hàng triệu entity, việc tạo cache entry không cần thiết có thể gây cache churn/memory. Nếu job đọc hàng hot đã cache, bỏ qua cache có thể tăng DB reads.

Chọn theo throughput và consistency; test với cấu hình L2 thực tế. Đặc biệt nếu ứng dụng trộn stateful và stateless, cần hiểu phạm vi cache invalidation và thứ tự transaction commit.

## 30. Trộn stateful Session và StatelessSession trong một ứng dụng

Hoàn toàn có thể dùng cả hai trong một hệ thống, nhưng chúng **không chia sẻ first-level Persistence Context**.

```java
OrderArchive managed = statefulSession.find(
    OrderArchive.class,
    100L
);

OrderArchive imported = statelessSession.get(
    OrderArchive.class,
    100L
);

imported.setDescription("Updated by import");
statelessSession.update(imported);
```

State của `managed` trong stateful Session **có thể vẫn cũ**. Việc update qua stateless không tự sửa object đã managed ở context khác.

Nếu tiếp tục dùng `managed`, cần quyết định:

- `statefulSession.refresh(managed)`.
- `statefulSession.clear()` rồi load lại.
- Tách các unit of work/transactions.
- Dùng optimistic locking để tránh lost updates.
- Kiểm tra L2 cache khi bật.

Không khuyến nghị dùng hai Sessions và hai connections mà mặc định cho rằng chúng **cùng transaction**. Nếu muốn transaction chung, phải cấu hình/JTA/connection propagation phù hợp và test.

## 31. StatelessSession không biến query thành set-based bulk DML

Nếu muốn đổi trạng thái một triệu rows cùng điều kiện:

```hql
update OrderArchive a
set a.status = :status
where a.createdAt < :cutoff
```

thường đáng thử **bulk mutation** trước khi:

1. Load một triệu entity.
2. Sửa từng Java object.
3. Gọi `ss.update(entity)` một triệu lần.

Điểm khác:

| Bài toán | Lựa chọn cần cân nhắc |
|---|---|
 Mọi hàng cùng đổi trạng thái theo predicate | Bulk HQL/native UPDATE |
 Từng hàng cần transformation riêng từ source | StatelessSession hoặc JDBC batching |
 Cần cascade, callback và dirty checking | Stateful Session |
 Cần read + modify + write theo từng record nhưng không muốn identity map lớn | StatelessSession |
 Import siêu lớn cần vendor bulk loader | JDBC COPY/bulk API |

StatelessSession thích hợp với **entity-oriented commands** không cần managed lifecycle; không mặc định là nhanh nhất cho mọi loại bulk mutation.

## 32. Batching và transaction/commit performance

Giả sử mỗi transaction commit đúng một INSERT:

```text
INSERT row1; COMMIT
INSERT row2; COMMIT
INSERT row3; COMMIT
...
```

Dù dùng StatelessSession, throughput có thể kém vì commit overhead rất lớn.

Với chunk transactions:

```text
BEGIN
  insertMultiple(200 rows)
  insertMultiple(200 rows)
  insertMultiple(200 rows)
COMMIT
```

Thao tác trên giảm số transaction boundaries. Nhưng transaction quá lớn có thể:

- Giữ locks lâu.
- Tạo WAL/redo lớn.
- Tăng rollback cost.
- Tăng thời gian chờ các transaction khác.
- Khó retry một phần.

Với import cần tiếp tục sau lỗi, chọn kích thước chunk và checkpoint:

```text
chunk 001 -> COMMIT -> checkpoint 001
chunk 002 -> COMMIT -> checkpoint 002
chunk 003 -> ROLLBACK -> retry/quarantine
chunk 004 -> ...
```

Checkpoint chỉ được đánh dấu thành công **sau commit thật sự**, không chỉ sau khi gọi `insertMultiple` xong. Nếu checkpoint ở hệ thống ngoài DB, cần cơ chế idempotency để xử lý crash giữa commit và checkpoint.

## 33. Import có retry và duplicate dữ liệu

Một job có thể được chạy lại vì timeout/crash.

Nếu nhập:

```text
source id = EXT-1001
source id = EXT-1002
source id = EXT-1003
```

rồi job retry toàn chunk, cần tránh duplicate.

Cách làm:

1. Định nghĩa unique business key/ID trên database.
2. Xác định insert-only, reject duplicate hay upsert.
3. Kiểm tra payload khi cùng key nhưng dữ liệu khác.
4. Dùng transaction chunk rõ ràng.
5. Có retry policy cho deadlocks/transient errors.
6. Dùng checkpoint và idempotency key khi tích hợp message queue.

Không xem `ss.upsert()`/`ss.upsertMultiple()` là đủ cho mọi trường hợp. Upsert có thể giải quyết row existence, nhưng không tự quyết định conflict policy, external side effects hoặc thứ tự sự kiện.

## 34. Đồng thời và thứ tự ghi: những bảo đảm không nên suy diễn

StatelessSession không có identity map hoặc dirty checker, nhưng database vẫn có concurrency control.

Không suy luận:

- Cứ gọi `insert(A)` trước `insert(B)` thì người dùng transaction khác luôn nhìn thấy A trước B.
- Dùng `insertMultiple(list)` đồng nghĩa record thứ 1 đã commit khi record thứ 2 bắt đầu.
- Batch luôn ghi đúng thứ tự callback/DB trigger ở mọi driver tối ưu.
- Không có first-level cache nghĩa là không thể có lost updates.
- Không có auto rollback nghĩa là sau mọi lỗi có thể tiếp tục transaction.

Nếu thứ tự là invariant nghiệp vụ, diễn đạt bằng:

- Foreign key / unique constraints.
- Explicit transaction/order of commands.
- Sequence number hoặc monotonic event version.
- Optimistic/pessimistic concurrency phù hợp.
- Integration tests với nhiều transaction.

Không dựa vào thời gian callback hoặc log output làm bằng chứng về committed ordering.

## 35. Bảo mật, tenant và filters khi xử lý stateless

Một import job thường có quyền ghi nhiều dữ liệu hơn HTTP request thông thường.

Kiểm tra:

- Tenant identifier có được truyền vào SessionFactory/session context đúng không?
- Schema/database routing có đúng không?
- Các Hibernate filters hoặc `@SQLRestriction` được áp vào query/load/mutation cụ thể không?
- Có row-level security ở database không?
- Job có dùng elevated service account không?
- Có audit đối với những thay đổi phải truy vết không?

StatelessSession không phải cách bỏ qua toàn bộ mapping restrictions một cách có chủ đích. Nhưng cũng **không được giả định mọi automatic filter/authorization của một repository stateful đều áp dụng y hệt** cho từng stateless command và bulk SQL.

Với hệ thống multi-tenant, nên:

1. Chỉ lấy tenant từ nguồn tin cậy.
2. Xác định session/connection tenant context.
3. Seed dữ liệu hai tenant và test không đọc/ghi chéo.
4. Test delete/update bằng ID trùng logic giữa tenants nếu schema cho phép.
5. Xem SQL thật thay vì chỉ tin API naming.

DB constraints/RLS có thể tạo lớp bảo vệ độc lập nếu được cấu hình đúng.

## 36. Chọn cách xử lý validation và audit khi không muốn phụ thuộc callback

Mẫu ingest tách hai bước:

```java
public OrderArchive mapValidated(
        ImportRow row,
        Clock clock) {

    if (row.externalId() == null || row.externalId().isBlank()) {
        throw new ValidationException("Missing external ID");
    }

    OrderArchive entity = new OrderArchive();
    entity.setExternalId(row.externalId());
    entity.setDescription(row.description());
    entity.setImportedAt(clock.instant());
    return entity;
}
```

Sau đó:

```java
List<OrderArchive> entities = rows.stream()
    .map(row -> mapValidated(row, clock))
    .toList();

ss.insertMultiple(entities); // Hibernate 7.x
```

Nếu audit bắt buộc gồm `who/when/sourceJobId`, truyền các field rõ ràng hoặc ghi audit/outbox record trong cùng DB transaction. Không đặt mọi invariant vào `@PrePersist` rồi giả định StatelessSession sẽ luôn gọi nó.

### Tại sao cũng không chỉ dựa vào DB defaults?

DB defaults/trigger bảo vệ row, nhưng business validation vẫn cần thông báo lỗi có ý nghĩa cho từng input record. Kết hợp:

- Application validation: lỗi gần nguồn.
- DB constraints: lớp bảo vệ cuối.
- Transaction: tính nguyên tử.
- Audit/outbox: khả năng truy vết và side effects.

## 37. Kiểm thử batching bằng JDBC thay vì chỉ đếm câu log SQL

Một log:

```text
insert into archived_orders (...) values (...)
insert into archived_orders (...) values (...)
insert into archived_orders (...) values (...)
```

không tự chứng minh driver đã/không batch: một số logger ghi statement khi chuẩn bị/bind, không thể hiện số `executeBatch()` chính xác.

Muốn xác nhận, cần theo dõi:

- JDBC `addBatch` và `executeBatch` calls (DataSource proxy/driver metrics phù hợp).
- Số prepared statement executions và round trips.
- Hibernate statistics ở mức có ý nghĩa, nhưng hiểu phạm vi từng counter.
- Database-side execution/latency/rows affected.
- Driver properties (ví dụ chế độ rewrite batched statements nếu DB driver hỗ trợ).
- SQL generated keys/RETURNING và error behavior.

### Phân biệt batch size và throughput

Batch size 100 không chắc nhanh hơn 25:

- Driver có thể giới hạn packets/parameters.
- Câu SQL phức tạp có thể làm batch chậm.
- Index/foreign keys/triggers quyết định phần lớn DB time.
- Hàng quá rộng làm bộ nhớ và network packet tăng.
- Transaction chunk lớn có thể làm lock contention tăng.

Hãy benchmark ở ít nhất một số giá trị đại diện như 20, 50, 100 trên database mục tiêu.

## 38. Test hồi quy khi nâng cấp từ 6.x sang 7.x

Do 7.0 thay đổi `hibernate.jdbc.batch_size` và second-level cache, cần test những điều sau:

| Tình huống | Test cần thiết |
|---|---|
| `hibernate.jdbc.batch_size=50` với stateless loop | Xác nhận thực tế batching không còn do property này điều khiển |
| Chuyển sang `insertMultiple` | Xác nhận SQL count, rows, transaction boundaries |
| Dùng `setJdbcBatchSize` | Xác nhận deferred execution và timing lỗi |
| Có `@PostPersist`/`@PostUpdate` | Xác nhận callback thực tế trên version mới |
| Có `@PrePersist` | Không mặc định được gọi; test và chuyển validation bắt buộc ra ngoài |
| Có custom `Interceptor` | Xác nhận callback stateless, không chỉ stateful |
| Bật second-level cache | Kiểm tra puts/gets/evictions và staleness |
| Trộn Session và StatelessSession | Xác nhận managed state/cache được refresh đúng |
| Entity có `@Version` | Test concurrent updates và stale version |
| IDENTITY/SEQUENCE | Test generated keys và batching eligibility |
| Parent/child cascade | Xác nhận không tự cascade từ stateless command |
| Lỗi trong chunk | Xác nhận rollback/checkpoint/retry |

Đặc biệt cần đối chiếu hiệu năng **trước và sau nâng cấp** vì cache mặc định và batching có thể thay đổi cả DB I/O lẫn memory footprint.

## 39. Một phương án import bằng Session stateful

Nếu cần callback/cascade đầy đủ, stateful Session với batch là lựa chọn đáng cân nhắc:

```java
try (Session session = factory.openSession()) {
    Transaction tx = session.beginTransaction();
    try {
        int count = 0;

        for (ImportRow row : rows) {
            session.persist(toEntity(row));

            if (++count % 50 == 0) {
                session.flush();
                session.clear();
            }
        }

        session.flush();
        tx.commit();
    } catch (RuntimeException ex) {
        tx.rollback();
        throw ex;
    }
}
```

Khi cấu hình phù hợp, stateful Session có thể dùng `hibernate.jdbc.batch_size` và những batching optimizations khác. Sau mỗi 50 entities, `flush/clear` giới hạn số managed objects.

### Những trade-off

- Entity callbacks và cascades theo stateful lifecycle.
- Identity map và dirty checking khi cần.
- Memory phải được quản lý bằng flush/clear.
- ID generation và entity relationships ảnh hưởng thứ tự/batch.
- Không miễn trừ transaction/DB errors.

**Không chọn StatelessSession chỉ để tránh viết `flush/clear`**, nếu use case thực sự phụ thuộc những bảo đảm stateful.

## 40. Khi nào chọn bulk HQL/native SQL thay vì StatelessSession?

Giả sử cần cập nhật tất cả OrderArchive quá hạn:

```hql
update OrderArchive a
set a.status = :archived
where a.status = :active
  and a.createdAt < :cutoff
```

Một set-based statement có thể xử lý rất nhiều rows hiệu quả hơn:

```java
List<OrderArchive> all = ...;
for (OrderArchive entity : all) {
    entity.setStatus(ARCHIVED);
    ss.update(entity);
}
```

Tuy nhiên bulk HQL/native cũng bypass phần lớn managed entity lifecycle và phải xử lý:

- First-level cache và L2/cache invalidation.
- `@Version`/optimistic concurrency.
- Callbacks per entity không được thực hiện như managed update.
- Database constraints/triggers.
- Audit và outbox nghiệp vụ.

Kết luận: chọn **bulk set-based** cho phép biến đổi thống nhất và không cần xử lý từng object; chọn **StatelessSession** khi cần ORM mapping và xử lý riêng từng entity mà không muốn giữ Persistence Context.

## 41. Những hiểu nhầm thường gặp

### “StatelessSession không có transaction”

Sai. Nó vẫn có thể tham gia JDBC/JTA transaction; phải begin/commit/rollback theo transaction manager.

### “StatelessSession luôn bỏ qua mọi callback”

Không đúng xuyên phiên bản. Javadocs 6.5 nêu bypass; 6.6 và 7.x mô tả một số Post callbacks và Interceptor stateless.

### “Có @PostPersist thì chắc chắn có @PrePersist”

Không suy ra được. Test riêng từng callback.

### “PostPersist chạy nghĩa là dữ liệu đã commit”

Không. Callback có thể xảy ra trước transaction commit; rollback vẫn có thể xảy ra.

### “StatelessSession update khi tôi sửa field rồi commit”

Không. Cần `update(entity)` tường minh.

### “StatelessSession thực hiện cascade = ALL”

Không. Entity operation không tự cascade; phải thao tác child explicit hoặc dựa vào DB cascade có chủ đích.

### “StatelessSession không bao giờ dùng L2 cache”

Không còn đúng từ Hibernate 7.0: L2 cache được dùng mặc định.

### “hibernate.jdbc.batch_size=100 sẽ batch stateless ở Hibernate 7”

Không. Từ 7.0 property này không tác động StatelessSession.

### “insertMultiple là một SQL statement”

Không có bảo đảm như vậy. Nó là API nhiều entity operations.

### “Tăng JDBC batch size đồng nghĩa tăng transaction size”

Không. Đó là hai kích thước độc lập.

### “Không có Persistence Context thì không có stale data”

Không. Một stateful Session khác có thể giữ object cũ; cùng một StatelessSession có thể trả nhiều instance độc lập đại diện một row.

### “Không tự mark rollback là có thể tiếp tục sau mọi lỗi”

Không. Database/transaction manager vẫn có thể buộc rollback; ứng dụng phải có failure policy.

### “insertMultiple tự validate toàn bộ entity và gửi audit”

Không được mặc định. Validation/callback/side effects theo phiên bản và tích hợp riêng.

## 42. Bài thực hành 1: xác nhận detached behavior

Tạo entity `OrderArchive` với `id` và `description`.

1. Mở StatelessSession và transaction.
2. `get(OrderArchive.class, 1L)`.
3. Sửa `description` nhưng **không gọi update**; commit.
4. Đọc từ Session mới, xác nhận DB không thay đổi.
5. Lặp lại với `ss.update(entity)`.
6. Gọi hai lần `get` cùng ID và so sánh Java identity.

Giải thích vì sao không có dirty checking và identity map.

## 43. Bài thực hành 2: callback matrix theo phiên bản

Chạy cùng entity/listener test trên hai bản Hibernate mà dự án hỗ trợ (ví dụ một bản 6.x và 7.x), mỗi lần dùng database tương thích.

Ghi bảng:

| Event | 6.x test result | 7.x test result |
|---|---|---|
| @PrePersist | Đo thực tế | Đo thực tế |
| @PostPersist | Đo thực tế | Đo thực tế |
| @PreUpdate | Đo thực tế | Đo thực tế |
| @PostUpdate | Đo thực tế | Đo thực tế |
| @PreRemove | Đo thực tế | Đo thực tế |
| @PostRemove | Đo thực tế | Đo thực tế |
| @PostLoad | Đo thực tế | Đo thực tế |
| Interceptor onInsert | Đo thực tế | Đo thực tế |
| Interceptor onUpdate | Đo thực tế | Đo thực tế |

Mục tiêu: chứng minh vì sao **không thể viết một câu “StatelessSession bỏ qua callback” cho mọi phiên bản**.

## 44. Bài thực hành 3: benchmark batching

Seed 20.000 input rows và so sánh:

1. Hibernate 6.6 stateless loop `insert`.
2. Hibernate 7.x stateless loop `insert` với `hibernate.jdbc.batch_size=50`.
3. Hibernate 7.x `insertMultiple` với các list size 25, 50, 100.
4. Hibernate 7.x `setJdbcBatchSize(50)` + loop `insert`.
5. Stateful Session với `hibernate.jdbc.batch_size=50`, flush/clear.
6. JDBC PreparedStatement batch nếu được phép.

Đo:

- Tổng thời gian (bao gồm commit).
- JDBC addBatch/executeBatch counts.
- Số statement và DB round trips.
- Heap/GC peak.
- Số row insert thành công.
- Hành vi khi hàng thứ 501 vi phạm constraint.
- Hành vi generated ID.

Không so sánh chỉ dựa vào SQL logger. Dùng driver/DB thực tế và schema/index tương đương.

## 45. Bài thực hành 4: kiểm tra L2 cache sau khi nâng cấp

1. Bật L2 cache cho OrderArchive.
2. Nạp OrderArchive bằng stateful Session để tạo cache entry.
3. Đọc/update qua StatelessSession 6.x theo hệ test.
4. Đọc/update qua StatelessSession 7.x.
5. Lặp lại với `ss.setCacheMode(CacheMode.IGNORE)`.
6. Đo cache puts/gets/misses/evictions và kiểm tra state sau commit.
7. Mở một Session mới và xem DB/cache trả dữ liệu đúng không.

Chú ý: `CacheMode.IGNORE` là lựa chọn rõ cho bulk job muốn bypass cache trong 7.x. Không kết luận CacheMode chỉ ảnh hưởng hiệu năng mà bỏ qua consistency.

## 46. Bài thực hành 5: xử lý lỗi, rollback và checkpoint

Tạo 1.000 ImportRow, trong đó row 501 trùng unique business key.

Yêu cầu:

1. Chính sách all-or-nothing: tất cả 1.000 rows cùng một transaction.
2. Quan sát exception và rollback.
3. Chính sách chunked 200 rows: khi chunk chứa row 501 lỗi, rollback chunk đó.
4. Ghi quarantine record cho row lỗi và retry những row hợp lệ bằng policy rõ.
5. Chỉ ghi checkpoint cho chunk sau commit.
6. Restart job và xác nhận không import duplicate.
7. Nếu dùng automatic batching, quan sát lỗi có thể phát sinh muộn hơn khi executeBatch.

Từ đó thiết kế API import trả:

```java
public record ImportResult(
    long received,
    long committed,
    long rejected,
    String checkpoint
) {}
```

Không dùng `received == committed` nếu job có policy partial success.

## 47. Bài thực hành 6: cascade và validation

Tạo `ImportBatch` chứa `ImportItem` với `cascade = CascadeType.ALL` và database foreign key.

1. Chạy `session.persist(batch)` bằng Session stateful.
2. So sánh `ss.insert(batch)` bằng StatelessSession.
3. Kiểm tra child rows tồn tại không.
4. Viết code insert children tường minh.
5. Thêm `@PrePersist` điền field bắt buộc, so sánh behavior hai đường.
6. Đổi sang set field trước lệnh + DB `NOT NULL` constraint.
7. Test DB `ON DELETE CASCADE` riêng và xác nhận đó không phải ORM cascade.

Mục tiêu phân biệt ba lớp: **mapping cascade, application validation và database constraints**.

## 48. Checklist trước khi đưa StatelessSession vào production

| Kiểm tra | Câu hỏi |
|---|---|
| Version | Runtime thực tế là Hibernate 6.x hay 7.x? |
| API | `insertMultiple/updateMultiple/deleteMultiple` có sẵn chưa? |
| Dirty checking | Job có gọi `update` explicit cho mọi thay đổi cần lưu không? |
| Entity graph | Có phụ thuộc cascade hoặc orphanRemoval không? |
| Callback | `@Pre...`, `@Post...`, interceptor nào thật sự chạy? |
| Validation | Invariant bắt buộc đã có application validation + DB constraints chưa? |
| Cache | 7.x có cần `CacheMode.IGNORE`/GET không? |
| Batch setting | Có nhầm `hibernate.jdbc.batch_size` với stateless 7.x không? |
| JDBC execution | Đã đo addBatch/executeBatch/round trips chưa? |
| IDs | Identifier generator có ảnh hưởng batching không? |
| Optimistic lock | `@Version` có được kiểm thử bằng conflict thực tế không? |
| Transaction | Rollback policy và chunk boundaries rõ chưa? |
| Exception | Nếu DB transaction failed, có retry trong context mới không? |
| Duplicate rows | Có unique key/idempotency không? |
| Resource lifetime | Cursor, Session, transaction được đóng đúng không? |
| Tenant/security | Tenant/filter/RLS có đúng với stateless commands không? |
| Audit/outbox | Có phụ thuộc callback sau SQL như thể đã commit không? |
| Migration | Đã chạy regression tests khi đổi 6.x → 7.x chưa? |
| Performance | Có benchmark với DB/version/schema thật không? |

## 49. Nguyên tắc cần ghi nhớ

1. **StatelessSession là command-oriented API không có Persistence Context**, không phải stateful Session với một cờ “bật tốc độ”.
2. **Không có first-level cache, identity map, dirty checking hay transactional write-behind như Session.** Ghi/sửa/xóa cần các command tường minh.
3. **Không tự cascade và không theo dõi thay đổi collection**; cần chủ động xử lý child entities và foreign key order.
4. **Callback behavior có khác biệt theo phiên bản và tài liệu.** 6.5 mô tả bypass; 6.6/7.x Javadocs mô tả một số `@Post...` callbacks và stateless Interceptor methods. Test riêng từng callback.
5. **@PostPersist không phải after-commit**; side effects như gửi email cần outbox/after-commit policy phù hợp.
6. **Từ Hibernate 7.0, `hibernate.jdbc.batch_size` không tác động StatelessSession.** Ưu tiên `insertMultiple`, `updateMultiple`, `deleteMultiple`, với API có thể được đánh dấu incubating.
7. **`setJdbcBatchSize` có thể bật automatic batching ở 7.x, nhưng làm thay đổi tính đồng bộ thông thường của commands.** Phải kiểm tra thời điểm SQL/error.
8. **JDBC batch size, list size và transaction chunk size là những khái niệm độc lập**; đừng lẫn batching với commit.
9. **Hibernate 7.x tương tác second-level cache mặc định**; bulk jobs cần chủ động chọn cache mode, ví dụ `CacheMode.IGNORE`.
10. **Database constraints/transaction vẫn có hiệu lực.** Nhưng exception không tự quyết định failure policy; ứng dụng phải rollback/retry/checkpoint đúng.
11. **StatelessSession có nguy cơ data aliasing**, và nếu trộn với stateful Session phải xử lý stale managed instances cùng cache.
12. **Không phải bulk workload nào cũng cần StatelessSession.** Set-based HQL/native UPDATE hoặc JDBC bulk loader có thể phù hợp hơn khi không cần từng entity object.
13. **Benchmark trên đúng version và DB/driver mục tiêu.** Kiểm chứng callbacks, JDBC batching và cache bằng test chứ không suy luận từ tên API.

Khi thiết kế một job ghi hàng loạt, hãy phân biệt **“cần bảo đảm lifecycle nào?”, “thực tế SQL được batch ra sao?”, và “transaction/commit và cache hoạt động theo version nào?”**. Chỉ khi trả lời được ba câu hỏi ấy mới có thể dùng `StatelessSession` vừa nhanh, vừa đúng, mà không đánh mất những invariant nghiệp vụ đã được stateful Session đảm nhiệm trước đó.

### Tài liệu tham khảo theo phiên bản

- [Hibernate ORM 6.5 Javadocs — StatelessSession](https://docs.hibernate.org/orm/6.5/javadocs/org/hibernate/StatelessSession.html)
- [Hibernate ORM 6.6 Javadocs — StatelessSession](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/StatelessSession.html)
- [Hibernate ORM 6.6 Javadocs — Interceptor](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/Interceptor.html)
- [Hibernate ORM 6.6 User Guide — StatelessSession và batching](https://docs.hibernate.org/orm/6.6/userguide/html_single/#batch-stateless-session)
- [Hibernate ORM 7.0 Migration Guide — StatelessSession behavior](https://docs.hibernate.org/orm/7.0/migration-guide/#stateless-session-behavior)
- [Hibernate ORM 7.0 What's New — Batch operations và L2 cache](https://docs.hibernate.org/orm/7.0/whats-new/)
- [Hibernate ORM 7.4 Javadocs — StatelessSession](https://docs.hibernate.org/orm/7.4/javadocs/org/hibernate/StatelessSession.html)
- [Hibernate ORM 7.4 Javadocs — Interceptor](https://docs.hibernate.org/orm/7.4/javadocs/org/hibernate/Interceptor.html)
- [Hibernate ORM User Guide — Batching](https://docs.hibernate.org/orm/7.4/userguide/html_single/#batch)
- [Jakarta Persistence specification](https://jakarta.ee/specifications/persistence/)
