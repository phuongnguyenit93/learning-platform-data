# Vai trò của callback và entity listener

Trong JPA, một entity không chỉ chứa dữ liệu được ánh xạ thành các cột. Entity còn trải qua **vòng đời**: được tạo mới, đưa vào persistence context, tải từ database, thay đổi, đồng bộ bằng flush và bị xóa. JPA cung cấp **lifecycle callbacks** và **entity listeners** để ứng dụng thực thi một lượng xử lý có kiểm soát tại các mốc của vòng đời đó.

Ví dụ, trước khi lưu một Book mới, ứng dụng muốn chuẩn hóa tiêu đề và ghi thời gian tạo:

```java
@PrePersist
void beforeInsert() {
    title = title.trim();
    createdAt = Instant.now();
}
```

Hoặc muốn tái sử dụng cùng quy tắc ghi thời gian trên nhiều entity, ta đưa logic ra một listener:

```java
@EntityListeners(AuditListener.class)
@Entity
public class Book {
    // ...
}
```

Hai cơ chế có liên hệ nhưng vai trò khác nhau:

- **Lifecycle callback trong entity**: phương thức của chính entity, thường dùng khi quy tắc gắn chặt với trạng thái và bất biến cục bộ của loại entity đó.
- **Entity listener**: class riêng, được JPA gọi khi entity đi qua sự kiện vòng đời, phù hợp logic lặp lại giữa nhiều loại entity như chuẩn hóa trường, timestamp hoặc audit metadata đơn giản.

Điều quan trọng là **callback không phải một phương thức chạy sau commit, cũng không phải một business event handler tổng quát**. Nó có thể chạy trước SQL, sau SQL nhưng **trước khi transaction commit**, hoặc tại thời điểm entity được tải vào context. Nếu transaction rollback, JPA không tự “undo” tác dụng phụ ngoài database mà callback đã thực hiện.

Bài **“Vai trò của callback và entity listener”**, thuộc chương **Sự kiện vòng đời** trong chủ đề **Data Persistence Relational Access ORM JPA**, giải thích đầy đủ bảy callback events chuẩn, cách viết callback trong entity và listener riêng, thứ tự gọi/kế thừa, giới hạn của callback code, liên hệ với flush, cascade, merge, bulk DML, native SQL, audit, Spring Data JPA và cách kiểm thử tích hợp.

Các ví dụ dùng Java 17+ và Jakarta Persistence (`jakarta.persistence`). Dự án JPA 2.x dùng namespace `javax.persistence` tương ứng. Thời điểm phát SQL, bytecode enhancement và một số tối ưu là chi tiết **provider-specific**, nên với logic phụ thuộc thứ tự SQL phải đo và kiểm thử đúng implementation.

---

## 1. Callback nằm ở đâu trong vòng đời entity?

Hãy hình dung một Book:

```text
new Book(...)
      │
      ▼
Transient/new: chưa managed
      │
      │ em.persist(book)
      ▼
@PrePersist
      │
      ▼
Managed trong persistence context
      │
      │ SQL INSERT (có thể tại persist/flush)
      ▼
@PostPersist
      │
      │ SQL SELECT/refresh khi nạp entity
      ▼
@PostLoad
      │
      │ Sửa thuộc tính persistent trên managed Book
      ▼
Dirty managed state
      │
      │ flush / auto-flush / commit
      ▼
@PreUpdate
      │
      ▼
SQL UPDATE
      │
      ▼
@PostUpdate
      │
      │ em.remove(book)
      ▼
@PreRemove
      │
      │ SQL DELETE (có thể tại flush)
      ▼
@PostRemove
      │
      ▼
Transaction có thể COMMIT hoặc ROLLBACK
```

Đây là **sơ đồ minh họa các nhánh**, không phải mọi entity đều đi qua tất cả sự kiện theo một đường thẳng. Ví dụ:

- Entity được tạo rồi xóa trước khi có INSERT có thể không có cặp SQL/callback như một entity đã tồn tại.
- `@PostLoad` diễn ra khi entity được load hoặc refresh; một entity mới persist không cần trải qua `@PostLoad` trước khi insert.
- `@PreUpdate`/`@PostUpdate` gắn với thao tác update entity, không chạy chỉ vì setter được gọi nếu không có cập nhật persistent thực sự.
- `@PostPersist`/`@PostUpdate`/`@PostRemove` nói về kết quả thao tác persistence tương ứng, **không khẳng định transaction đã commit**.
- Với cascading, callbacks của các entity liên quan có thể được kích hoạt riêng; không được tự suy thứ tự SQL/callback giữa mọi parent và child.

Hãy đọc mỗi annotation như một **mốc để chèn xử lý cục bộ**, không phải lifecycle engine độc lập quản lý transaction thay cho JPA.

## 2. Bảy lifecycle callback chuẩn

Các annotation cơ bản:

```java
import jakarta.persistence.PrePersist;
import jakarta.persistence.PostPersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.PostUpdate;
import jakarta.persistence.PreRemove;
import jakarta.persistence.PostRemove;
import jakarta.persistence.PostLoad;
```

| Callback | Khi nào có ý nghĩa | Vai trò phù hợp |
| --- | --- | --- |
| `@PrePersist` | Trước khi entity được persist/cascaded persist | Khởi tạo giá trị mặc định, chuẩn hóa thuộc tính, timestamp tạo |
| `@PostPersist` | Sau thao tác insert của entity | Quan sát trạng thái sau insert, bao gồm ID đã sinh theo semantics |
| `@PreUpdate` | Trước thao tác update persistent entity | Chuẩn hóa field, gắn thời gian sửa, kiểm tra state cục bộ |
| `@PostUpdate` | Sau thao tác update persistent entity | Xử lý cục bộ sau update, **không coi là after commit** |
| `@PreRemove` | Trước thao tác remove entity | Kiểm tra trạng thái cục bộ trước xóa |
| `@PostRemove` | Sau thao tác delete entity | Xử lý cục bộ sau delete, **không coi là after commit** |
| `@PostLoad` | Sau khi entity được load/refreshed trong context | Tính lại dữ liệu `@Transient` hoặc chuẩn bị state chỉ đọc |

Bảng thể hiện **ngữ nghĩa sự kiện**, không cố định mỗi annotation vào đúng một lời gọi Java hay một số lượng SQL cụ thể. Ví dụ provider có thể thực hiện insert ngay khi `persist()` cần lấy ID từ `GenerationType.IDENTITY`, hoặc để tới flush.

JPA chuẩn **không có `@PostCommit` hay `@PostRollback` lifecycle annotation** trong nhóm bảy callback entity này. Nếu cần hành động sau commit, dùng cơ chế giao dịch/application event/outbox phù hợp.

## 3. Callback trong entity khác gì listener riêng?

Một callback trong entity:

```java
@Entity
@Table(name = "books")
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String title;

    @PrePersist
    private void normalizeOnInsert() {
        title = title.trim();
    }
}
```

Phương thức callback biết trực tiếp state của chính Book và có thể sửa non-relationship persistent fields của Book theo những giới hạn portable của JPA.

Listener riêng:

```java
public class BookListener {

    @PrePersist
    public void normalize(Book book) {
        book.normalizeTitle();
    }
}
```

Đăng ký:

```java
@Entity
@EntityListeners(BookListener.class)
public class Book {
    // ...
    public void normalizeTitle() {
        title = title.trim();
    }
}
```

**Callback trong entity** phù hợp khi:

- Logic chỉ dùng cho Book.
- Quy tắc thuộc về bất biến state của Book.
- Không cần tái sử dụng qua nhiều entity types.
- Muốn tránh class bên ngoài phụ thuộc các field private.

**Entity listener** phù hợp khi:

- Nhiều entity có quy tắc audit/timestamp tương tự.
- Muốn tách cross-cutting concern khỏi domain entity.
- Muốn thay cấu hình qua annotation/XML.
- Muốn khai báo thứ tự callback listeners rõ ràng.

Cả hai **không tự có quyền gọi database hoặc dịch vụ bất kỳ một cách portable**.

## 4. Một entity mẫu đầy đủ

Ta dùng Book, có ID, version, title, price và audit fields:

```java
package com.example.domain;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;

@Entity
@Table(name = "books")
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private Long version;

    @Column(nullable = false, length = 200)
    private String title;

    @Column(nullable = false, precision = 14, scale = 2)
    private BigDecimal price;

    @Column(nullable = false, updatable = false)
    private Instant createdAt;

    @Column(nullable = false)
    private Instant updatedAt;

    protected Book() {}

    public Book(String title, BigDecimal price) {
        rename(title);
        changePrice(price);
    }

    public Long getId() { return id; }
    public Long getVersion() { return version; }
    public String getTitle() { return title; }
    public BigDecimal getPrice() { return price; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }

    public void rename(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Title is required");
        }
        title = value.trim();
    }

    public void changePrice(BigDecimal value) {
        Objects.requireNonNull(value, "price");
        if (value.signum() < 0) {
            throw new IllegalArgumentException("Negative price");
        }
        price = value;
    }

    @PrePersist
    private void onCreate() {
        Instant now = Instant.now();
        createdAt = now;
        updatedAt = now;
    }

    @PreUpdate
    private void onUpdate() {
        updatedAt = Instant.now();
    }
}
```

Schema tham khảo:

```sql
CREATE TABLE books (
    id BIGINT PRIMARY KEY,
    version BIGINT NOT NULL,
    title VARCHAR(200) NOT NULL,
    price DECIMAL(14,2) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
```

Cú pháp sinh khóa, kiểu `TIMESTAMP` và cách ánh xạ `Instant` phụ thuộc RDBMS/dialect. DDL ở trên mô tả cấu trúc logic, không phải script tạo ID đầy đủ cho mọi database.

### Vì sao timestamp ở callback?

- `@PrePersist` chạy trước insert, phù hợp đặt `createdAt` và `updatedAt` nếu entity mới.
- `@PreUpdate` chạy khi provider xử lý update entity, phù hợp sửa `updatedAt`.
- Không phải mọi setter gọi trên managed Book đều chắc chắn dẫn tới SQL UPDATE.
- Native/bulk SQL đi thẳng database sẽ không chạy hai callback này.
- Nếu transaction rollback, các giá trị thời gian trong Book Java object có thể đã thay đổi nhưng DB không commit.

Khi ứng dụng cần đồng nhất timezone/clock hoặc audit với một user cụ thể, cần có cách tổ chức bổ sung; `Instant.now()` chỉ minh họa cơ chế và không đảm bảo lấy cùng clock cho toàn hệ thống.

## 5. Quy tắc chữ ký callback đặt trong entity

Một lifecycle callback method trên **entity** hoặc **mapped superclass** theo dạng không có tham số và trả `void`:

```java
@PrePersist
void beforePersist() {
    // ...
}
```

JPA cho phép callback methods có các mức truy cập thông dụng và không nhất thiết `public`; sử dụng `private` trong entity class là khả thi theo cơ chế callback. Cần tuân thủ các ràng buộc của specification/provider với phương thức không được static/final và số callback cùng event trong hierarchy.

Một chữ ký sai:

```java
@PrePersist
String beforePersist() {
    return "created";
}
```

Một chữ ký sai khác:

```java
@PrePersist
void beforePersist(Book other) {
    // Entity callback không nhận tham số này.
}
```

Callback trong entity không nên phụ thuộc vào việc có một context/framework truyền tham số ẩn. Nó dùng trực tiếp `this`.

### Mỗi event trên cùng class

Không khai báo hai callback methods cùng event trong cùng entity class rồi suy chúng luôn chạy theo thứ tự bạn mong muốn:

```java
@PrePersist void a() {}
@PrePersist void b() {} // Không theo quy tắc callback hợp lệ cho cùng event.
```

Khi cần nhiều bước:

```java
@PrePersist
private void beforePersist() {
    normalizeTitle();
    initializeAuditFields();
}
```

Hoặc tách các concern sang listener classes, với thứ tự listener được định nghĩa phù hợp.

## 6. Chữ ký callback ở entity listener

Một **listener class** là Java class riêng, có lifecycle callback method nhận **một tham số entity instance** và trả `void`:

```java
public class BookAuditListener {

    @PrePersist
    public void prePersist(Book book) {
        book.initializeAuditTime();
    }

    @PreUpdate
    public void preUpdate(Book book) {
        book.updateAuditTime();
    }
}
```

Một cách reusable hơn là nhận kiểu interface/base type:

```java
public interface Timestamped {
    void markCreated(Instant now);
    void markUpdated(Instant now);
}
```

```java
public class TimestampListener {

    @PrePersist
    public void beforeInsert(Object entity) {
        if (entity instanceof Timestamped value) {
            value.markCreated(Instant.now());
        }
    }

    @PreUpdate
    public void beforeUpdate(Object entity) {
        if (entity instanceof Timestamped value) {
            value.markUpdated(Instant.now());
        }
    }
}
```

Đây là cách dùng `Object` listener parameter cho nhiều types; logic tự kiểm tra interface để quyết định thao tác. Một dự án có thể thay bằng một mapped-superclass/base class callback để giảm check kiểu.

**Lưu ý:** Đối với callback trong listener, tham số là entity; đối với callback trong entity, method không có tham số. Hai chữ ký không hoán đổi cho nhau.

## 7. Đăng ký bằng `@EntityListeners`

```java
import jakarta.persistence.Entity;
import jakarta.persistence.EntityListeners;

@Entity
@EntityListeners(TimestampListener.class)
public class Book implements Timestamped {
    // ...
}
```

Có thể khai báo nhiều listeners:

```java
@Entity
@EntityListeners({
    NormalizeListener.class,
    TimestampListener.class
})
public class Book {
    // ...
}
```

Các listener trong array được xử lý theo thứ tự khai báo trong phạm vi thứ tự callback listeners áp dụng theo JPA. Tuy nhiên khi có inheritance/default listeners/XML, cần xét đầy đủ **callback order** thay vì nhìn duy nhất array ở entity.

Một listener class phải đáp ứng khả năng tạo instance của provider, thông thường có constructor không tham số phù hợp. Một listener được quản lý qua CDI trong môi trường hỗ trợ còn có quy tắc lifecycle/injection riêng; không nên viết listener dựa vào một Spring service tự được inject khi chạy trong Java SE thuần.

### Listener không giống Spring application event listener

`@EntityListeners` là annotation của JPA gắn vào entity lifecycle. `@EventListener` hay `@TransactionalEventListener` của Spring là cơ chế application events, không cùng phạm vi contract.

Listener JPA không được coi là người nhận một “sự kiện business đã commit”.

## 8. Vai trò của `@PrePersist`

`@PrePersist` gắn với việc entity được persist, bao gồm các thao tác cascade persist phù hợp.

```java
@Entity
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    private String displayName;

    @PrePersist
    void normalizeName() {
        displayName = displayName.trim();
    }
}
```

Khi gọi:

```java
Customer customer = new Customer(...);

em.getTransaction().begin();
em.persist(customer);
em.getTransaction().commit();
```

callback có thể chạy khi xử lý `persist`, trước SQL INSERT.

### Phù hợp để làm gì?

- Trim/canonicalize scalar attributes.
- Đặt giá trị mặc định của field chưa có.
- Khởi tạo timestamp.
- Kiểm tra một bất biến cục bộ cuối cùng trước insert.
- Tạo một giá trị derived persistent đơn giản từ state hiện có của chính entity.

### Không nên làm gì?

- Gọi `em.persist(...)` thêm entity khác.
- Chạy query để hỏi database có ID/username bị trùng không.
- Gửi email hoặc HTTP request.
- Sửa relationship graph trong callback.
- Mở transaction mới.
- Thay đổi global static state để biểu thị đã commit.

Những việc này hoặc không portable hoặc làm timing/transaction khó kiểm soát.

## 9. `@PrePersist` và ID được tạo tự động

Một lỗi thường gặp:

```java
@PrePersist
void beforePersist() {
    auditLog("Creating book " + id);
}
```

Nếu ID được sinh bởi database như `GenerationType.IDENTITY`, **ID có thể chưa có ở `@PrePersist`**. Cơ chế ID generation khác (sequence, table, assigned ID, UUID/provider-specific) có thời điểm gán khác nhau.

Trong khi đó `@PostPersist` thường là mốc phù hợp để quan sát primary key đã được gán sau thao tác insert.

Ví dụ:

```java
@PostPersist
void afterInsert() {
    // Có thể đọc id đã được provider gán sau INSERT.
}
```

Nhưng không nên dùng `@PostPersist` để gửi thông báo “Book đã được lưu vĩnh viễn”, vì transaction **vẫn có thể rollback**.

### Tại sao timestamp không cần ID?

`@PrePersist` phù hợp gán timestamps hoặc dữ liệu không phụ thuộc DB-generated ID. Nếu cần tạo một external ID độc lập, ứng dụng có thể sinh UUID trong constructor/domain factory hoặc callback có kiểm soát, thay vì dựa vào database ID tại `@PrePersist`.

## 10. Vai trò của `@PostPersist`

`@PostPersist` được gọi sau khi JPA thực hiện insert entity tương ứng. Thời điểm có thể là lúc persist cần gửi INSERT sớm, khi flush hoặc trong quá trình commit.

```java
@PostPersist
void afterInsert() {
    // Quan sát state sau persistence INSERT.
}
```

Các ứng dụng đôi khi dùng callback này để cập nhật một trường `@Transient` có tính toán từ ID. Nhưng việc sửa persistent fields thêm lần nữa sau INSERT có thể gây thêm UPDATE hoặc tương tác provider-specific, nên không nên làm như một kỹ thuật phổ quát.

**@PostPersist không phải after transaction commit.**

Xét:

```java
em.getTransaction().begin();

em.persist(book);
em.flush(); // SQL INSERT có thể chạy, @PostPersist có thể đã gọi.

em.getTransaction().rollback();
```

Ngay cả khi `@PostPersist` đã xảy ra, Book vẫn chưa được commit bền vững. Nếu callback gửi email ở thời điểm đó, email không tự rollback.

### Mốc cần nhớ

```text
@PrePersist
    ↓
SQL INSERT
    ↓
@PostPersist
    ↓
Transaction có thể COMMIT hoặc ROLLBACK
```

Đừng đặt logic tích hợp bên ngoài transaction chỉ dựa vào annotation mang chữ `Post`.

## 11. Vai trò của `@PreUpdate`

`@PreUpdate` chạy trước thao tác database update cho một entity theo lifecycle managed persistence.

```java
@PreUpdate
void beforeUpdate() {
    updatedAt = Instant.now();
}
```

Giả sử:

```java
Book book = em.find(Book.class, id);
book.rename("Tên mới");

em.flush();
```

Một provider có thể phát hiện Book dirty và gọi `@PreUpdate` trong quá trình flush, ngay trước SQL UPDATE.

### Có chạy ngay khi setter được gọi không?

Không.

```java
book.rename("Tên mới");
```

là domain operation trên Java object; setter không tự phát lifecycle callback.

### Có chạy nếu không có cập nhật persistent?

Không nên giả định `@PreUpdate` chạy chỉ vì entity được tải hoặc vì bạn gọi một method không thay đổi state.

```java
Book book = em.find(Book.class, id);
book.getTitle();

em.flush();
```

Nếu entity không có state dirty cần update, thường không có UPDATE và không có `@PreUpdate`.

### Cẩn trọng khi persist và update trong cùng transaction

Nếu entity mới được persist rồi thay đổi ngay trước flush, có thể provider gom thay đổi vào INSERT thay vì phát UPDATE riêng. Thứ tự/xuất hiện của `@PreUpdate` trong các tình huống mới-persist/removed/trạng thái chuyển tiếp là chi tiết cần được kiểm tra theo spec/provider.

Đừng viết business rule bắt buộc `@PreUpdate` chạy một lần cho mỗi setter hoặc mỗi lời gọi `save()`.

## 12. `@PreUpdate` có bảo đảm updatedAt đổi trong mọi thao tác ghi?

Không. Nó chỉ được gọi trong đường **entity update lifecycle** mà JPA xử lý.

Những tình huống có thể không gọi:

- Bulk JPQL UPDATE.
- CriteriaUpdate.
- Native SQL UPDATE.
- Trigger hoặc job bên ngoài ORM.
- Sửa một bảng association/join table nhưng không update persistent row của entity chứa `updatedAt`.
- Một managed entity không thực sự dirty.
- Một transaction rollback trước khi flush tới UPDATE.

Nếu yêu cầu nghiệp vụ là **mọi thay đổi dữ liệu trong DB đều phải cập nhật timestamp**, callback đơn lẻ có thể chưa đủ. Cân nhắc:

- Centralized write paths.
- Application service updates.
- Database triggers/defaults nếu phù hợp.
- Versioning/audit policy được thiết kế trên toàn bộ đường ghi.
- Integration tests cho từng loại DML.

Một câu native SQL trực tiếp không tự chạy `@PreUpdate` của JPA.

## 13. Vai trò của `@PostUpdate`

`@PostUpdate` chạy sau update entity tương ứng được thực hiện.

```java
@PostUpdate
void afterUpdate() {
    // Có thể quan sát state sau update.
}
```

Tuy nhiên, giữa `@PostUpdate` và commit vẫn có thể còn:

- SQL UPDATE của entity khác.
- Constraint check ở transaction.
- Optimistic lock conflict của một entity khác.
- Lỗi deadlock hoặc transaction timeout.
- Ứng dụng chủ động rollback.

Ví dụ:

```text
Book A UPDATE → @PostUpdate A
Book B UPDATE → DB constraint violation
ROLLBACK transaction
```

Nếu trong `@PostUpdate A` đã gửi webhook “Book A cập nhật thành công”, webhook có thể thông báo một sự kiện **chưa từng được commit**.

Vì vậy nên coi `@PostUpdate` là một lifecycle hook **sau database update trong đơn vị transaction**, không phải một delivery confirmation sau commit.

## 14. Vai trò của `@PreRemove`

`@PreRemove` là callback trước thao tác remove entity:

```java
@PreRemove
void beforeDelete() {
    if (lockedByBusinessRule) {
        throw new IllegalStateException("Book cannot be deleted");
    }
}
```

Nó có thể là điểm kiểm tra một điều kiện **trên chính entity** trước khi thực hiện remove.

Nhưng có những giới hạn:

- Nếu việc xóa phải kiểm tra nhiều entities hoặc external state, logic thuộc service/domain layer phối hợp transaction.
- Bulk JPQL/Criteria/native DELETE không đi qua entity callback.
- Referential constraints/cascade ở DB vẫn phải được thiết kế.
- Listener không thay thế authorization, tenant checking hoặc rule enforcement ở mọi đường API.
- Nếu business lock chỉ lưu trong object Java nhưng có thể thay đổi đồng thời, phải có concurrency/locking/versioning phù hợp.

Ví dụ:

```java
em.getTransaction().begin();

Book book = em.find(Book.class, id);
em.remove(book);

em.getTransaction().commit();
```

`@PreRemove` có thể được gọi khi xử lý `remove` trước khi SQL DELETE được gửi ở flush.

## 15. Vai trò của `@PostRemove`

`@PostRemove` là mốc sau thao tác delete entity trong lifecycle JPA:

```java
@PostRemove
void afterDelete() {
    // Không gửi email hay xóa file vật lý tại đây.
}
```

Nếu SQL DELETE chạy thành công trong transaction, nhưng transaction rollback sau đó, hàng database có thể được khôi phục bởi rollback. Một tác động ngoài database đã xảy ra trong `@PostRemove` không tự được phục hồi.

Ví dụ nguy hiểm:

```java
@PostRemove
void deleteFile() {
    fileStorage.delete(filePath); // Side effect không transaction-aware.
}
```

Nếu DB rollback, Book còn lại nhưng file đã bị xóa vĩnh viễn.

Giải pháp thường là thiết kế **sự kiện nghiệp vụ được ghi cùng transaction** hoặc một cơ chế after-commit có độ tin cậy phù hợp, không dùng entity callback làm bộ xử lý side effect không thể rollback.

## 16. Vai trò của `@PostLoad`

`@PostLoad` chạy khi một entity được load vào persistence context hoặc refresh theo ngữ nghĩa JPA.

Ví dụ Book có `price` và `discountPercent` nhưng muốn có field không persistent để hiển thị:

```java
@Entity
public class Book {

    @Id
    private Long id;

    private BigDecimal price;
    private int discountPercent;

    @Transient
    private BigDecimal discountedPrice;

    @PostLoad
    private void calculateDisplayPrice() {
        discountedPrice = price.multiply(
            BigDecimal.valueOf(100 - discountPercent)
        ).divide(
            BigDecimal.valueOf(100)
        );
    }

    public BigDecimal getDiscountedPrice() {
        return discountedPrice;
    }
}
```

Ở đây `discountedPrice` được đánh dấu `@Transient` nên không tự ghi xuống database. Callback tính lại giá trị sau khi entity được nạp từ DB.

### Khi nào `@PostLoad` không nên dùng?

Nếu giá hiển thị phụ thuộc dữ liệu thay đổi sau load, ví dụ `book.changePrice(...)`, giá trị transient đã tính tại `@PostLoad` có thể stale nếu không tính lại khi setter chạy.

Đôi khi đơn giản hơn:

```java
public BigDecimal getDiscountedPrice() {
    return price.multiply(...);
}
```

hoặc chuyển sang DTO projection để tính tại tầng presentation.

`@PostLoad` thích hợp cho derived state có lifecycle rõ, không nên lạm dụng làm trình tải thêm toàn bộ graph.

## 17. `@PostLoad` không nhất thiết chạy lại mỗi lần `find()`

Giả sử:

```java
Book first = em.find(Book.class, 42L);
Book second = em.find(Book.class, 42L);
```

Trong cùng persistence context, `first` và `second` thường là cùng managed instance. Nếu Book đã được tải từ trước, `find` lần hai có thể chỉ trả lại object trong identity map, không tải lại SQL và không cần một lượt `@PostLoad` mới.

Nếu muốn bắt đầu lại vòng load:

- Tạo EntityManager mới.
- Hoặc detach/clear theo mục tiêu và đọc lại.
- Hoặc dùng `em.refresh(book)` để làm mới state có chủ đích.

Nhưng gọi refresh có thể ghi đè local changes chưa flush. **Đừng dùng refresh chỉ để “bắt PostLoad chạy lại” nếu còn dirty state quan trọng.**

### Lazy proxies

`getReference` có thể trả reference/proxy chưa nạp đủ state. `@PostLoad` gắn với việc provider thực sự load entity state, không mặc nhiên chạy tại mọi lần trả proxy. Timing khởi tạo lazy state là chi tiết provider cần kiểm thử.

## 18. Các event gắn với `flush` và commit khác nhau

Một transaction:

```java
em.getTransaction().begin();

Book book = em.find(Book.class, id);
book.rename("Tên mới");

em.flush();

em.getTransaction().commit();
```

Timeline có thể là:

```text
find()              → SELECT, @PostLoad
rename()            → Chỉ Java managed state
flush()             → @PreUpdate, UPDATE, @PostUpdate
commit()            → Transaction được xác nhận
```

Nếu bỏ explicit flush, provider thường flush các thay đổi cần thiết trong quá trình commit.

Nếu chạy JPQL query giữa rename và commit:

```java
List<Book> result = em.createQuery(
    "SELECT b FROM Book b WHERE b.title = :title",
    Book.class
).setParameter("title", "Tên mới")
 .getResultList();
```

với `FlushModeType.AUTO` trong joined transaction, query có thể kích hoạt auto-flush. Khi đó `@PreUpdate`/`@PostUpdate` có thể diễn ra **tại lời gọi `getResultList()`**, trước commit.

**Vị trí callback trong stack trace không nhất thiết là nơi ứng dụng gọi setter.**

## 19. `FlushModeType.AUTO` và `COMMIT` liên quan thế nào?

JPA có:

```java
em.setFlushMode(FlushModeType.AUTO);
em.setFlushMode(FlushModeType.COMMIT);
```

### AUTO

Provider phải xử lý những thay đổi pending ảnh hưởng query trong persistence context tham gia transaction. Một query có thể khiến flush, nên callbacks của dirty entities có thể chạy trước khi SELECT.

### COMMIT

Tác động của pending changes lên query trước commit không có cùng bảo đảm như AUTO, nên một callback update có thể được trì hoãn tới flush/commit. Nhưng COMMIT không đồng nghĩa “không bao giờ SQL sớm”: explicit `flush()` và những tình huống như ID generation vẫn có thể tạo SQL.

Ví dụ:

```java
book.rename("Tên mới");

em.setFlushMode(FlushModeType.COMMIT);

em.createQuery("SELECT b FROM Book b", Book.class)
  .getResultList();

em.getTransaction().commit();
```

Không dùng `@PreUpdate` như một đồng hồ chắc chắn chạy trước hay sau câu SELECT mà không xét provider/transaction.

**Callback lifecycle phụ thuộc thời điểm persistence operation xảy ra; flush mode có thể ảnh hưởng thời điểm ấy.**

## 20. Callback không phải transaction completion callback

Đây là phân biệt quan trọng nhất:

| Sự kiện | Đã có DB operation? | Transaction đã commit? |
| --- | --- | --- |
| `@PrePersist` | INSERT chưa hoàn tất | Không |
| `@PostPersist` | INSERT tương ứng đã xảy ra | **Không bảo đảm** |
| `@PreUpdate` | UPDATE tương ứng chưa hoàn tất | Không |
| `@PostUpdate` | UPDATE tương ứng đã xảy ra | **Không bảo đảm** |
| `@PreRemove` | DELETE tương ứng chưa hoàn tất | Không |
| `@PostRemove` | DELETE tương ứng đã xảy ra | **Không bảo đảm** |
| `@PostLoad` | Entity state đã được load/refreshed | Không liên quan commit ghi |
| Transaction after-commit hook của framework | Nằm sau commit thành công | Có theo hook/contract |
| Transactional outbox event được worker phát sau commit | Outbox row đã commit trước khi publish | Thiết kế nhằm đảm bảo không publish trước commit |

`@Post*` chỉ có nghĩa “sau thao tác lifecycle tương ứng”, **không có nghĩa sau khi transaction được commit bền vững**.

Nếu cần cập nhật một hệ thống khác sau commit, hãy dùng transaction synchronization của framework có kiểm soát hoặc transactional outbox, không xem entity listener như một after-commit bus.

## 21. Callback và rollback

Giả sử:

```java
em.getTransaction().begin();

Book book = new Book("JPA", new BigDecimal("100000"));

em.persist(book);
em.flush(); // @PrePersist, @PostPersist có thể đã chạy.

em.getTransaction().rollback();
```

Sau rollback:

- SQL INSERT thuộc transaction không được commit.
- Object Java `book` vẫn tồn tại trong heap.
- Các fields callback đã gán có thể vẫn giữ giá trị.
- JPA không tự gọi một sự kiện `@PostRollback` chuẩn để đảo lại fields.
- Nếu callback đã gọi external service, side effect đó có thể vẫn tồn tại.
- Không tiếp tục coi entity từ transaction lỗi là bằng chứng dữ liệu đã được lưu.

Khi cần đọc state đã commit, mở EntityManager/transaction mới và truy vấn lại.

### Transaction thất bại do exception trong callback

Nếu callback ném runtime exception trong quá trình lifecycle/flush, transaction liên quan có thể bị đánh dấu rollback-only, và quá trình persistence dừng với exception tương ứng. Không thử “sửa state rồi flush tiếp” trên một transaction đã lỗi mà không xem transaction status.

## 22. Có nên đặt validation trong callback?

Có những invariant cục bộ phù hợp kiểm tra ở callback:

```java
@PrePersist
@PreUpdate
void validateState() {
    if (title == null || title.isBlank()) {
        throw new IllegalStateException("Book title is required");
    }
}
```

Nhưng có giới hạn:

1. Callback không được gọi trên mọi bulk/native DML.
2. Validation có thể xảy ra muộn tới flush/commit.
3. Mỗi annotation không thay thế Bean Validation.
4. Nếu rule phụ thuộc database/tenant/quyền, callback không phải nơi portable để query.
5. Exception trong callback có thể khiến transaction rollback.
6. Validation đơn giản nên được đặt ở domain method/constructor để báo lỗi sớm hơn.
7. DB constraints vẫn cần cho bất biến thiết yếu.

Một thiết kế thường kết hợp:

- Domain methods: kiểm tra bất biến ngay khi ứng dụng thay đổi state.
- Jakarta Bean Validation: kiểm tra constraints theo lifecycle tích hợp khi được cấu hình.
- JPA callback: normalization/audit/last-line local checks.
- Database constraints: bảo vệ bất biến cơ bản cho mọi đường ghi.

**Không giao toàn bộ tính đúng của dữ liệu cho callback.**

## 23. Bean Validation và lifecycle callbacks không phải cùng cơ chế

Ví dụ:

```java
@Entity
public class Book {

    @NotBlank
    private String title;

    @PrePersist
    void normalize() {
        title = title.trim();
    }
}
```

`@NotBlank` thuộc Jakarta Bean Validation, không phải JPA lifecycle callback annotation. Trong môi trường có tích hợp Bean Validation, các constraint validations có thể được kích hoạt tự động ở các lifecycle operations phù hợp.

Cần biết:

- Provider/framework quyết định tích hợp Bean Validation, validation groups và event configuration theo specification.
- Callback normalization và Bean Validation có thứ tự xử lý theo các quy tắc lifecycle; không nên dựa vào thứ tự không được kiểm chứng của extension.
- Validation không phải DB constraint thay thế.
- Bulk SQL thường bypass entity-level callback và Bean Validation trên từng entity.

Nếu quy tắc phải áp mọi lần nhập, domain/API layer có thể validate sớm, còn DB bảo vệ dữ liệu cuối cùng.

## 24. Giới hạn portable khi viết callback

Jakarta Persistence có các ràng buộc để lifecycle callback ổn định và portable. Một callback method **nên tránh**:

- Gọi `EntityManager` hoặc `Query`.
- Truy cập hoặc thay đổi các entity instances khác trong cùng persistence context.
- Sửa relationship/association của chính entity.
- Thực hiện lifecycle operations mới (`persist`, `remove`, `merge`) từ trong callback.
- Đóng/mở transaction, gọi commit/rollback.
- Gọi dịch vụ chậm, network hoặc filesystem.
- Dựa vào thứ tự SQL giữa các entities không được spec bảo đảm.
- Thay đổi global static state như business audit source.

Một callback có thể **sửa non-relationship state của chính entity được gọi**, chẳng hạn `title = title.trim()` hay `updatedAt = Instant.now()`.

### Vì sao có những giới hạn đó?

Lifecycle callback được JPA gọi **đang trong quá trình quản lý persistence operation**. Gọi thêm một query hoặc sửa graph có thể khiến flush lồng nhau, thay đổi dirty state bất ngờ hoặc tạo thứ tự cascade khó xác định. Provider không bắt buộc hỗ trợ mọi reentrant persistence operation trong callback.

Nếu logic cần phối hợp nhiều entities, hãy làm ở application/domain service trước khi flush; nếu cần publish sau commit, dùng một cơ chế sau commit/outbox.

## 25. Đừng sửa association graph trong listener

Ví dụ nguy hiểm:

```java
@PrePersist
void autoAddReview() {
    reviews.add(new Review(this, 5));
}
```

Điều này thay đổi collection relationship trong khi JPA đang xử lý persistence operations/cascade. Tính portable và thứ tự cascade có thể trở nên khó dự đoán.

Tốt hơn:

```java
Book book = new Book("JPA", price);

book.addReview(new Review(book, 5));

em.persist(book);
```

Nếu `Book.reviews` có cascade PERSIST phù hợp và helper giữ hai phía đồng bộ, provider có thể persist graph theo mapping.

**Entity lifecycle callback không phải nơi để dựng mới object graph.** Domain constructor/factory/helper/service là nơi rõ ý định hơn.

## 26. Cascade có kích hoạt callback của entity con không?

Giả sử Order có cascade PERSIST tới OrderLine:

```java
@Entity
public class PurchaseOrder {

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.PERSIST
    )
    private List<OrderLine> lines = new ArrayList<>();
}
```

Khi:

```java
em.persist(order);
```

JPA có thể cascade persist tới các OrderLine và áp dụng lifecycle callbacks tương ứng trên **từng entity** được persist.

Ví dụ:

```java
@Entity
public class OrderLine {

    @PrePersist
    void beforeInsert() {
        // Xử lý scalar state của chính OrderLine.
    }
}
```

Cần phân biệt:

- Parent callback của PurchaseOrder.
- Child callback của OrderLine.
- Thứ tự SQL INSERT giữa parent/child theo FK, ID generation và provider.
- Thứ tự callback giữa các entity graph nodes, không nên suy từ thứ tự list Java.

Không thiết kế logic mà OrderLine `@PrePersist` đòi Parent `@PostPersist` chắc chắn đã chạy trước theo một thứ tự toàn cục trừ khi contract/spec mapping đảm bảo điều đó.

## 27. Orphan removal và callbacks

Với mapping:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<OrderLine> lines = new ArrayList<>();
```

Khi gỡ một child khỏi managed association theo ownership đúng:

```java
order.removeLine(line);
```

provider có thể lập lịch xóa OrderLine khi flush; các lifecycle delete callbacks tương ứng có thể tham gia khi entity removal được xử lý.

Nhưng không nên coi `order.removeLine` gọi ngay `@PreRemove`/`@PostRemove` tại dòng Java đó. Với orphanRemoval, timing của remove operation/SQL phụ thuộc lifecycle/flush semantics.

Ngoài ra:

- Database `ON DELETE CASCADE` không đi qua JPA remove callbacks của child.
- Native `DELETE FROM order_lines` không đi qua callbacks.
- Bulk JPQL/Criteria delete không đi qua callbacks cho từng child.
- Nếu SQL xóa child trực tiếp ngoài ORM, Java graph và L1/L2 caches có thể stale.

Nếu auditing việc xóa phải đủ cho **mọi đường xóa**, chỉ dựa vào callbacks không đủ.

## 28. Merge detached entity và listener

Một entity detached:

```java
Book detached = loadBookAndCloseContext(id);

detached.rename("Tên ở ngoài transaction");
```

Khi:

```java
Book managedCopy = em.merge(detached);
```

JPA áp dụng merge semantics: copy state từ detached instance vào managed representative hoặc tạo managed copy phù hợp. Lifecycle callbacks có thể được gọi trên **managed target** khi nó được load/persist/update theo thực thi, không phải một quy tắc “gọi callback của original detached object” ngay sau `merge`.

Ví dụ:

- Nếu merge làm managed Book dirty, `@PreUpdate` có thể chạy ở flush.
- Nếu merge tạo một managed representation mới cần INSERT, `@PrePersist` có thể liên quan.
- Khi provider load managed target từ DB, `@PostLoad` có thể chạy.
- `merge()` trả về không chứng minh transaction đã flush/commit.

**Không dùng entity listeners để tự quyết định merge đối tượng stale hay kiểm tra quyền**; những việc đó thuộc service và optimistic versioning.

### Không dùng DTO với `merge`

DTO không phải entity chỉ vì chứa ID. Nếu API nhận `BookUpdateRequest`, service nên load managed Book, validate và áp dụng domain methods thay vì `em.merge(dto)`.

## 29. `@PreUpdate` có chạy khi đổi collection không?

Giả sử Book có `@OneToMany reviews`. Trong một transaction, ứng dụng chỉ thêm Review mới:

```java
book.addReview(review);
```

Việc thay đổi association collection có thể dẫn đến SQL `INSERT` ở `reviews` hoặc join table, **nhưng không nhất thiết phát UPDATE trên row `books`**.

Vì vậy `@PreUpdate` của Book không được coi là callback “bất kỳ child/collection nào thay đổi thì cha phải chạy”.

Nếu nghiệp vụ muốn updatedAt/version của aggregate root thay đổi khi child đổi:

- Chủ động gọi một domain method trên root cập nhật scalar field phù hợp.
- Dùng version forcing như `OPTIMISTIC_FORCE_INCREMENT` khi semantics phù hợp.
- Thiết kế application event/audit ở service.
- Cần kiểm tra cả association row SQL và optimistic locking.
- Không dựa vào side effects không được JPA hứa ở `@PreUpdate` của parent.

Đây là một nguyên nhân khiến audit timestamp ở root không đổi dù OrderLine đã được cập nhật.

## 30. JPQL bulk UPDATE/DELETE bypass entity callback

Ví dụ:

```java
int changed = em.createQuery(
    "UPDATE Book b " +
    "SET b.price = :price " +
    "WHERE b.id = :id"
).setParameter("price", new BigDecimal("150000"))
 .setParameter("id", id)
 .executeUpdate();
```

Bulk JPQL DML hoạt động trực tiếp lên database rows, không biến từng Book tương ứng thành một managed entity rồi gọi setters/callbacks.

Hệ quả:

- Không kỳ vọng `Book.@PreUpdate` hay `@PostUpdate` chạy cho từng row.
- `updatedAt` từ callback có thể không được cập nhật.
- Entity state đang managed trong persistence context có thể stale.
- `@Version` không tự áp dụng toàn bộ per-entity version handling cho bulk DML.
- Entity listeners không thay thế bulk SQL audit/validation.

Tương tự:

```java
em.createQuery(
    "DELETE FROM Book b WHERE b.price < :min"
).setParameter("min", minimumPrice)
 .executeUpdate();
```

không tự gọi `@PreRemove`/`@PostRemove` trên từng Book bị xóa.

**Sự kiện vòng đời của entity và thao tác bulk DML là hai cơ chế khác nhau.**

## 31. CriteriaUpdate/CriteriaDelete cũng bypass

Criteria API có các dạng bulk:

```java
CriteriaUpdate<Book> update =
    cb.createCriteriaUpdate(Book.class);

Root<Book> root = update.from(Book.class);

update.set(root.get("price"), newPrice);
update.where(cb.equal(root.get("id"), id));

em.createQuery(update).executeUpdate();
```

Dù được viết bằng JPA Criteria API thay vì chuỗi JPQL, đây vẫn là **bulk update**, không phải per-entity dirty-checking lifecycle. Không kỳ vọng callback chạy trên mỗi Book bị tác động.

Một CriteriaDelete cũng có đặc điểm tương tự về entity lifecycle callbacks.

Cần phân biệt:

- `CriteriaQuery<Book>` trả entity rồi sửa managed object.
- `CriteriaUpdate<Book>` thực thi bulk UPDATE SQL trực tiếp.

Chúng đều mang tên Criteria nhưng có callback semantics rất khác.

## 32. Native SQL hoàn toàn không phải entity lifecycle

Ví dụ:

```java
em.createNativeQuery(
    "UPDATE books SET title = ? WHERE id = ?"
).setParameter(1, "Native update")
 .setParameter(2, 42L)
 .executeUpdate();
```

Câu SQL do ứng dụng viết không gọi `@PreUpdate` hay `@PostUpdate` của Book.

Đối với DELETE:

```java
em.createNativeQuery(
    "DELETE FROM books WHERE id = ?"
).setParameter(1, 42L)
 .executeUpdate();
```

nó không chạy `@PreRemove` hay `@PostRemove` cho Book.

Nếu muốn audit mọi thay đổi DB bất kể nguồn, cân nhắc:

- Database trigger hoặc CDC cho những thông tin cần bắt ở database.
- Consistent application service write policies.
- Transactional outbox khi event cần được công bố sau commit.
- SQL updates bổ sung audit columns.
- Kiểm soát các batch jobs/external writers.

Không có một JPA listener annotation chuẩn nào tự biến native SQL thành managed entity operation.

## 33. Database trigger khác JPA lifecycle listener

Hai hệ thống đều có thể xử lý quanh INSERT/UPDATE/DELETE, nhưng nơi thực thi và phạm vi khác nhau.

| Đặc điểm | JPA entity callback/listener | Database trigger |
| --- | --- | --- |
| Chạy ở đâu? | Trong JPA provider/application process | Trong database engine |
| Kích hoạt bởi managed entity operation? | Có, theo JPA lifecycle | Có nếu SQL tương ứng chạy và trigger được định nghĩa |
| Kích hoạt bởi native/bulk SQL? | Không theo per-entity lifecycle | Có thể, khi SQL đụng table/operation |
| Có Java entity object? | Có | Không |
| Có thể dễ dùng domain methods? | Có, trong giới hạn callback | Không trực tiếp |
| Có thể bị bypass bởi writers ngoài ORM? | Có | Không nếu trigger áp dụng ở DB và không bị disable |
| Transaction/rollback | Gắn với JPA operation và surrounding transaction | Phụ thuộc DB transaction/trigger semantics |
| Phù hợp | Local normalization/audit metadata | DB-wide invariants/audit theo DB policy |

Một ứng dụng có thể dùng cả hai, nhưng phải tránh trùng logic khiến timestamp bị set hai lần hoặc audit events bị duplicate.

### Trigger có cập nhật entity Java tự động không?

Nếu trigger tự thay một cột sau INSERT/UPDATE, managed entity trong Java **không tự được cập nhật chỉ vì trigger chạy**, trừ khi mapping/provider readback/generated-column strategy được cấu hình tương ứng. Có thể cần `refresh()` hoặc truy vấn mới.

## 34. Entity listener có được inject service không?

Trong môi trường Jakarta Persistence tích hợp CDI, entity listener instances có thể được quản lý theo cơ chế CDI và sử dụng injection theo quy định tương ứng.

Ví dụ ý tưởng:

```java
public class AuditListener {

    @Inject
    private AuditClock auditClock;

    @PrePersist
    public void created(Object entity) {
        // ...
    }
}
```

Tuy nhiên:

- Không phải mọi Java SE bootstrap `Persistence.createEntityManagerFactory(...)` có CDI container.
- Spring dependency injection vào entity listeners không tự tương đương CDI support của JPA.
- Những class được khởi tạo trực tiếp bởi provider có thể không đi qua Spring bean lifecycle.
- Nếu injection không được cấu hình, field có thể null.
- Không nên dựa vào listener để gọi repository/query từ callback, ngay cả khi service injection hoạt động.

**Injection support không xóa các giới hạn portable về database access và relationship manipulation trong callback.**

Nếu callback cần nhiều dependencies và phối hợp nghiệp vụ, đó là dấu hiệu cân nhắc đưa logic sang application service hoặc domain event processor thay vì entity listener.

## 35. Listener có cần stateless không?

Thường là có: hãy thiết kế listener không lưu mutable per-entity/per-transaction state trong fields của listener instance.

Ví dụ dễ lỗi:

```java
public class BadListener {

    private Long lastBookId;

    @PostPersist
    public void after(Book book) {
        lastBookId = book.getId();
    }
}
```

Nếu một listener instance được tái sử dụng giữa các callbacks hoặc threads theo provider/container lifecycle, state như `lastBookId` có thể gây race hoặc lẫn dữ liệu giữa các entities.

Tốt hơn:

```java
public class BookListener {

    @PrePersist
    public void before(Book book) {
        book.normalizeTitle();
    }
}
```

Không có mutable internal state. Đầu vào là entity, tác động chỉ lên state phù hợp của chính entity.

Nếu cần audit context (user ID, tenant, correlation ID), hãy chọn thiết kế explicit service/context propagation và đảm bảo thread safety; không đưa giá trị “request hiện tại” vào một mutable listener field dùng chung.

## 36. Thứ tự callback khi có nhiều listeners

Giả sử:

```java
@Entity
@EntityListeners({
    NormalizeListener.class,
    AuditListener.class
})
public class Book {
    @PrePersist
    void localBeforeInsert() {
        // ...
    }
}
```

Khi một `@PrePersist` được xử lý, các listener methods được xét theo quy tắc ordering của JPA. Trong phạm vi listeners trực tiếp khai báo, thứ tự từ trái sang phải có ý nghĩa.

Mô hình khái quát:

```text
Default listeners (nếu có và không bị exclude)
        ↓
Listeners khai báo ở các lớp cha phù hợp
        ↓
Listeners khai báo ở entity hiện tại
        ↓
Callback methods trong mapped superclass/entity hierarchy
        ↓
Hoàn thành lifecycle operation tương ứng
```

Khi entity hierarchy có callbacks ở nhiều cấp, JPA quy định ordering từ superclass tới subclass, với một số quy tắc override/exclusion. XML mapping có thể bổ sung/điều chỉnh cấu hình.

**Không viết logic bắt buộc callback của một entity khác phải chạy trước**, vì ordering callbacks trong cùng entity không đồng nghĩa global ordering giữa nhiều entities khi cascade/flush.

### Khi listener A phụ thuộc kết quả listener B

Nếu NormalizeListener sửa `title` và AuditListener cần hash từ title, phải làm rõ thứ tự và test trên entity hierarchy thực tế. Một cách bền hơn là gộp hai bước thành một callback/domain method có trình tự tường minh nếu cả hai là một invariant chặt.

## 37. Callback trong mapped superclass

Đối với audit fields dùng chung, `@MappedSuperclass` thường là nơi tự nhiên:

```java
@MappedSuperclass
public abstract class AuditedEntity {

    @Column(nullable = false, updatable = false)
    protected Instant createdAt;

    @Column(nullable = false)
    protected Instant updatedAt;

    @PrePersist
    protected void beforeInsert() {
        Instant now = Instant.now();
        createdAt = now;
        updatedAt = now;
    }

    @PreUpdate
    protected void beforeUpdate() {
        updatedAt = Instant.now();
    }
}
```

Entity:

```java
@Entity
public class Book extends AuditedEntity {

    @Id
    @GeneratedValue
    private Long id;

    private String title;
}
```

Ý nghĩa:

- Audit fields được ánh xạ vào entity tables tương ứng.
- Callback methods ở superclass có thể áp dụng cho các entity subclasses theo lifecycle rules.
- Không phải class AuditedEntity là một entity có table riêng.
- Có thể tránh lặp `@PrePersist` và `@PreUpdate` trên mọi entity.

Nhưng nếu subclass cũng khai báo callback của cùng event, cần hiểu quy tắc hierarchy và override. Không tự dùng hai methods cùng tên/signature ở các cấp với hy vọng chắc chắn cả hai được gọi. Test inheritance scenario nếu timing/order có ý nghĩa.

## 38. `@EntityListeners` ở superclass

Ngoài callback methods, một entity hoặc mapped superclass có thể khai báo listeners:

```java
@MappedSuperclass
@EntityListeners(AuditListener.class)
public abstract class BaseEntity {
    // ...
}
```

```java
@Entity
public class Book extends BaseEntity {
    // ...
}
```

Listener ở superclass có thể áp dụng cho subclass entity theo listener inheritance rules, trừ khi bị loại trừ bằng annotation tương ứng hoặc cấu hình XML.

Vì vậy khi một entity nhận **hai lần audit callback** ngoài dự kiến, hãy kiểm tra:

- Listener khai báo trực tiếp trên entity.
- Listener kế thừa từ entity superclass.
- Listener kế thừa từ mapped superclass.
- Default listeners trong XML.
- Callback methods trong entity và superclasses.
- Spring/Hibernate-specific auditing đang được cấu hình thêm.

Một entity có thể chịu nhiều callback sources dù class hiện tại chỉ có một annotation.

## 39. `@ExcludeDefaultListeners`

JPA có annotation:

```java
import jakarta.persistence.ExcludeDefaultListeners;
```

Ví dụ:

```java
@Entity
@ExcludeDefaultListeners
public class InternalJobLog {
    @Id
    private Long id;
}
```

Nó cho phép loại trừ **default lifecycle listeners** được cấu hình ở persistence unit, ví dụ qua ORM XML, đối với entity/hierarchy liên quan theo quy tắc JPA.

Dùng khi:

- Một loại entity không nên chịu global audit/normalization listener.
- Default listener không phù hợp với một data model đặc biệt.
- Cần tránh tác động của cross-cutting listener trên entity chuyên dụng.

Nhưng không nên nghĩ annotation này **tự tắt mọi callback được định nghĩa trong chính entity**. Nó nhắm vào default listeners, không phải một lệnh “disable JPA lifecycle” tổng quát.

## 40. `@ExcludeSuperclassListeners`

JPA có:

```java
import jakarta.persistence.ExcludeSuperclassListeners;
```

Ví dụ:

```java
@Entity
@ExcludeSuperclassListeners
public class IndependentAuditEntity extends BaseEntity {
    // ...
}
```

Mục đích là loại trừ **entity listeners được khai báo ở các superclass** theo listener inheritance rules.

Phân biệt:

- `@ExcludeDefaultListeners`: loại trừ default listeners.
- `@ExcludeSuperclassListeners`: loại trừ superclass listeners.
- Cả hai không phải cơ chế bỏ qua mọi callback methods trực tiếp định nghĩa trong entity.
- Callback methods trong superclass và listener classes khai báo ở superclass có semantics khác nhau; đừng nhầm hai khái niệm.

Nếu muốn thay đổi toàn bộ behavior ở một hierarchy, cần thiết kế lại callback declarations và kiểm tra chính xác semantics của mapping hiện hành, không chỉ thêm một annotation exclude rồi đoán.

## 41. Default entity listeners qua ORM XML

Ngoài annotation trên từng entity, JPA hỗ trợ khai báo default listeners cho persistence unit qua ORM mapping XML.

Cấu trúc ý tưởng:

```xml
<entity-mappings
    xmlns="https://jakarta.ee/xml/ns/persistence/orm"
    version="3.1">

    <persistence-unit-metadata>
        <persistence-unit-defaults>
            <entity-listeners>
                <entity-listener
                    class="com.example.audit.AuditListener"/>
            </entity-listeners>
        </persistence-unit-defaults>
    </persistence-unit-metadata>

</entity-mappings>
```

XML này minh họa vị trí **default entity listeners**. Một cấu hình chạy thật phải khai báo ORM mapping file theo `persistence.xml`/bootstrap và khớp Jakarta Persistence XML schema/version đang dùng; cú pháp callback methods trong XML có thể cần khai báo nếu không sử dụng annotation trên listener methods.

Default listener có thể áp dụng rộng cho entity types trong persistence unit, trừ những entity/hierarchy loại trừ theo quy tắc.

### Vì sao phải kiểm tra XML?

Có dự án entity class không khai báo `@EntityListeners`, nhưng callbacks vẫn chạy vì default listeners từ `orm.xml`. Nếu chỉ tìm annotation trong Java code, rất dễ bỏ sót nguồn cấu hình.

Ngược lại, một entity có `@ExcludeDefaultListeners` có thể không nhận callback global dù listener class có mặt trong project.

## 42. Entity callback và listener có thể cùng dùng một event

Ví dụ:

```java
@Entity
@EntityListeners(AuditListener.class)
public class Book {

    @PrePersist
    void normalize() {
        title = title.trim();
    }
}
```

```java
public class AuditListener {

    @PrePersist
    public void created(Book book) {
        book.markCreated();
    }
}
```

Hai callback ở hai nguồn khác nhau không mâu thuẫn: JPA có callback order rules để xử lý.

Tuy nhiên, nếu cả hai đều chỉnh `createdAt` với clock khác nhau, kết quả có thể bị gán hai lần. Nên phân chia trách nhiệm rõ:

- Entity method: chuẩn hóa title/domain-local invariants.
- Listener: audit timestamps dùng chung.
- Service: kiểm tra authorization/transaction/other entities.
- Database: constraints.

Không giữ hai hệ thống audit thực hiện cùng một tác vụ chỉ vì cả hai đều được gọi.

## 43. Audit timestamps: chọn entity callback hay listener?

Hai thiết kế hợp lý nhưng khác trade-offs.

### Cách A: callback ở mapped superclass

```java
@MappedSuperclass
public abstract class AuditedEntity {

    @Column(nullable = false, updatable = false)
    protected Instant createdAt;

    @Column(nullable = false)
    protected Instant updatedAt;

    @PrePersist
    void created() {
        Instant now = Instant.now();
        createdAt = now;
        updatedAt = now;
    }

    @PreUpdate
    void modified() {
        updatedAt = Instant.now();
    }
}
```

Ưu điểm: đơn giản, dữ liệu và callbacks cùng một class, dễ thấy quy tắc.

### Cách B: listener riêng

```java
public interface Auditable {
    void setCreatedAt(Instant value);
    void setUpdatedAt(Instant value);
}
```

```java
public class TimestampListener {

    @PrePersist
    public void onCreate(Object entity) {
        if (entity instanceof Auditable a) {
            Instant now = Instant.now();
            a.setCreatedAt(now);
            a.setUpdatedAt(now);
        }
    }

    @PreUpdate
    public void onUpdate(Object entity) {
        if (entity instanceof Auditable a) {
            a.setUpdatedAt(Instant.now());
        }
    }
}
```

Ưu điểm: logic tách biệt và có thể dùng trên nhiều entity classes không cùng superclass.

Nhược điểm: cần bảo đảm entities có setters phù hợp và thời gian được tạo ở đúng domain/clock policy. Nếu dự án dùng auditing framework, phải hiểu listener có thể phụ thuộc môi trường DI.

## 44. CreatedBy và UpdatedBy có khó hơn timestamps không?

Có. Timestamp có thể tạo từ clock cục bộ; **actor identity** thường phụ thuộc request/session/security context.

Ví dụ một audit field:

```java
@Column(name = "updated_by")
private String updatedBy;
```

Entity listener muốn gọi:

```java
SecurityContextHolder.getContext()...
```

Điều này ghép entity persistence code với Spring Security/thread context; khi chạy batch job hoặc asynchronous worker, context có thể không tồn tại, khác hoặc bị truyền sai.

Một thiết kế rõ hơn:

- Service quyết định actor ID từ principal đã xác thực.
- Command/use case áp dụng actor ID cho entity qua domain method.
- Listener chỉ ghi timestamp hoặc xử lý scalar state cục bộ.
- Nếu dùng Spring Data auditing, cấu hình `AuditorAware`/listener theo tài liệu framework, test cả HTTP và batch contexts.
- Không dùng global mutable static field “currentUser” trong listener.

**Audit “ai sửa” là câu hỏi về application identity; callback không tự biết user hiện tại một cách portable.**

## 45. So sánh với Spring Data JPA auditing

Spring Data JPA có những annotation và listener riêng, ví dụ:

```java
@CreatedDate
private Instant createdAt;

@LastModifiedDate
private Instant updatedAt;
```

Kết hợp với framework listener như:

```java
@EntityListeners(AuditingEntityListener.class)
```

và cấu hình auditing tương ứng.

Nhưng:

- `@CreatedDate` và `@LastModifiedDate` **không phải annotation lifecycle chuẩn của Jakarta Persistence**.
- `AuditingEntityListener` ở đây thuộc Spring Data.
- Nó phụ thuộc cấu hình Spring/Data JPA và có thể dùng `AuditorAware` để biết actor.
- Nó vẫn chạy trong lifecycle update/persist tương ứng; bulk JPQL/native SQL có thể bypass per-entity callbacks.
- Nó không biến `@PostPersist` thành after commit.

Khi viết library JPA portable, dùng annotation JPA chuẩn hoặc tách auditing service. Khi ứng dụng đã dùng Spring Data JPA, có thể tái sử dụng auditing feature nhưng phải kiểm thử theo integration stack thật.

## 46. So sánh với Hibernate-specific listeners

Hibernate còn có một hệ thống event listeners/interceptors riêng và annotations mở rộng như `@CreationTimestamp`/`@UpdateTimestamp`.

Các khả năng này có thể hữu ích cho:

- SQL event instrumentation.
- Timestamp generation.
- Entity change tracking.
- Specialized caching/audit integration.
- Observability khi cần SQL-level events.

Nhưng chúng không cùng contract portable với bảy Jakarta Persistence lifecycle callback annotations.

Không nên dựa vào một Hibernate event hook đặc thù rồi khẳng định mọi JPA provider đều có cùng thứ tự hoặc cùng cách xử lý bulk operations.

### Chọn đúng cơ chế

| Nhu cầu | Công cụ thường phù hợp |
| --- | --- |
| Trim title khi persist/update managed entity | JPA entity callback/domain method |
| Dùng chung timestamps across entities | Mapped superclass hoặc JPA entity listener |
| Auditing với Spring Security principal | Spring Data auditing + `AuditorAware` hoặc service |
| Theo dõi mọi SQL update bất kể đường ghi | Database trigger/CDC và audit policy |
| Publish domain event sau commit đáng tin | Transactional outbox |
| Quan sát Hibernate-specific SQL events | Hibernate event SPI |
| Validation ở application boundary | DTO + Bean Validation/domain service |
| Ràng buộc bắt buộc ở DB | Database constraints |

## 47. Callback có thể ném exception không?

Một callback có thể phát hiện state cục bộ không hợp lệ và ném unchecked exception:

```java
@PrePersist
@PreUpdate
void rejectNegativePrice() {
    if (price.signum() < 0) {
        throw new IllegalStateException(
            "Price must not be negative"
        );
    }
}
```

Trong lifecycle persistence, exception này có thể được provider lan truyền/gói lại và transaction liên quan bị đánh dấu rollback-only.

Vì vậy:

- Đừng bắt rồi tiếp tục flush như chưa có gì xảy ra.
- Rollback transaction theo transaction manager.
- Không tiếp tục dùng cùng context sau lỗi persistence nghiêm trọng.
- Nếu thông báo lỗi cần thân thiện, validate sớm trong domain/application/API và phân loại exception ở boundary.
- Đặt database constraint như `CHECK(price >= 0)` để bảo vệ mọi đường ghi.

**Callback exception không phải thay thế cho một Result/Validation API rõ ràng của nghiệp vụ.**

## 48. Performance: callback có thể làm chậm cả batch

Nếu mỗi entity có `@PreUpdate`:

```java
@PreUpdate
void onUpdate() {
    // Tính toán cục bộ rất nhỏ là phù hợp.
}
```

và một batch xử lý 100.000 entities, callback có thể được gọi rất nhiều lần. Chỉ một thao tác CPU nhỏ cũng cộng dồn thành chi phí đáng kể.

Nguy hiểm hơn, callback gọi external API/DB query cho mỗi entity có thể biến một batch thành hàng trăm nghìn lượt I/O, gây:

- N+1 truy vấn.
- Deadlocks hoặc flush reentrancy không portable.
- Kéo dài transaction và giữ database connections.
- Timeout.
- Side effects xảy ra trước commit.
- Khó kiểm soát retry.

Thiết kế callback **nhỏ, xác định được và tránh I/O**. Logic cần dữ liệu từ nhiều entities nên được batch ở service/repository nơi có transaction và fetch plan rõ.

## 49. Một listener có thể tạo N+1 không?

Có nếu vi phạm nguyên tắc tránh truy cập quan hệ:

```java
@PostLoad
void afterLoad() {
    for (OrderLine line : order.getLines()) {
        // Có thể lazy-load collection.
    }
}
```

Khi một truy vấn tải 100 Orders, mỗi `@PostLoad` cố truy cập `lines`, provider có thể phát thêm nhiều SELECT (hoặc gặp reentrancy/lazy lifecycle problems).

Đây là lý do `@PostLoad` nên xử lý local scalar/transient derived fields thay vì tự fetch graph.

Nếu UI cần Order + Lines:

- Dùng fetch join/entity graph đúng use case.
- Query DTO projection.
- Batch fetching nếu provider hỗ trợ.
- Map DTO trong application service.
- Đo query count và SQL rows.

Không đưa fetch plan vào entity callback, vì nó làm việc load một Order phụ thuộc hành vi ngầm rất khó tối ưu.

## 50. Callback và caching

Một Book có thể được trả từ shared cache cấp hai (L2) rồi trở thành managed entity trong context mới.

Các chi tiết về `@PostLoad` và state rehydration khi load từ cache có thể phụ thuộc provider và cách nó tạo/khởi tạo instances. Không nên coi bộ đếm callback như phép đo cache miss chuẩn.

Ngược lại:

- Entity `@Cacheable` không tự thay đổi callback lifecycle rules.
- `em.clear()` không phải transaction commit.
- L2 eviction không tự gọi `@PreRemove`/`@PostRemove`.
- `em.refresh(book)` có thể gọi `@PostLoad` theo semantics refresh.
- Khi bulk/native SQL làm cached state stale, listener không tự được chạy để invalidates cache.

Nếu mục tiêu là đo cache, dùng JPA Cache API và provider statistics. Nếu mục tiêu là quan sát callbacks, kiểm thử lifecycle operations với context state rõ ràng.

## 51. Callback và `@Version`

Book:

```java
@Version
private Long version;
```

và:

```java
@PreUpdate
void modified() {
    updatedAt = Instant.now();
}
```

Khi Book dirty và update, JPA provider có thể kiểm tra optimistic locking và tăng version. Nhưng callback `@PreUpdate` **không được phép thay thế versioning bằng việc tự set version**.

Không nên:

```java
@PreUpdate
void badVersionManagement() {
    version = version + 1; // Không tự quản lý @Version ở đây.
}
```

Provider quản lý version field để đảm bảo optimistic update semantics. Tự sửa làm xung đột, đứt đồng bộ hoặc gặp lỗi portability.

Một transaction stale có thể ném `OptimisticLockException` trong flush, trước khi update hoàn tất. Không giả định `@PostUpdate` luôn chạy nếu optimistic version check đã thất bại.

**`@Version` bảo vệ concurrency ở persistence layer; listener chủ yếu xử lý local lifecycle state.**

## 52. Callback không thay thế event sourcing

Một số dự án muốn ghi mọi thay đổi vào audit log bằng `@PostUpdate`:

```java
@PostUpdate
void logChange() {
    auditService.log(this);
}
```

Ngoài vấn đề hạn chế callback, cách này **không cho biết chắc “old value vs new value” đầy đủ** theo contract JPA portable. Entity callback thường thấy state hiện tại, không phải structured change set do provider cung cấp. Nếu cần history đầy đủ:

- Domain events ghi ý định nghiệp vụ.
- Transactional audit/outbox records.
- Database CDC/change data capture.
- Provider-specific dirty-state introspection khi có căn cứ.
- JPA auditing libraries được cấu hình rõ (ví dụ Hibernate Envers, provider-specific).

Callback đơn giản có thể đặt `updatedAt`, nhưng **không tự trở thành event sourcing platform**.

## 53. Callback và người gọi REST/controller

Một controller nhận request:

```java
@PutMapping("/books/{id}")
public BookDto rename(
        @PathVariable Long id,
        @RequestBody RenameBookCommand command) {
    return service.rename(id, command);
}
```

Service:

```java
@Transactional
public BookDto rename(
        Long id, RenameBookCommand command) {

    Book book = repository.findById(id)
        .orElseThrow();

    book.rename(command.title());

    return toDto(book);
}
```

Nếu transaction do Spring quản lý, `@PreUpdate` có thể chạy ở flush/commit sau khi method body trả về. DTO tạo trước flush có thể chứa `updatedAt` cũ, nếu field được cập nhật chỉ ở callback.

Cần quyết định contract:

- Nếu response cần thời điểm update chính xác, chủ động cập nhật timestamp trong service/domain method hoặc flush trước DTO mapping khi phù hợp (vẫn không phải commit), hoặc query lại sau commit theo thiết kế.
- Không cho rằng callback đã chạy ngay sau setter.
- Không gửi side effects thành công trước transaction completion.
- Bắt commit failure ở transaction/API boundary vì lỗi có thể xảy ra sau method body.

Đây là lý do một logic phụ thuộc timestamp mới đôi khi không nên chỉ giấu trong `@PreUpdate`.

## 54. Callback trước/sau load và mapping dữ liệu

Một entity có field:

```java
@Column(name = "birth_date")
private LocalDate birthDate;

@Transient
private Integer ageAtLoad;
```

`@PostLoad` có thể tính:

```java
@PostLoad
void computeAge() {
    ageAtLoad = birthDate == null
        ? null
        : Period.between(
            birthDate,
            LocalDate.now()
        ).getYears();
}
```

Nhưng:

- Age thay đổi theo ngày; nếu entity giữ lâu trong extended context, `ageAtLoad` có thể stale.
- Nếu `birthDate` đổi sau load, ageAtLoad không tự cập nhật.
- Timezone/clock cần quy định rõ.
- Một DTO có thể tính tuổi khi mapping theo clock của API.

Khi kết quả thay đổi theo thời gian ngay cả khi DB không đổi, getter tính toán hoặc service projection thường dễ hiểu hơn cache một transient value chỉ tại `@PostLoad`.

## 55. Các timeline thực tế

### Timeline A: insert và commit

```text
new Book(...)
  → em.persist(book)
  → @PrePersist
  → SQL INSERT (persist/flush tùy strategy)
  → @PostPersist
  → commit thành công
```

### Timeline B: update khi query auto-flush

```text
em.find(Book)
  → @PostLoad (khi load entity state)
  → book.rename()
  → JPQL query được thực thi
  → @PreUpdate
  → SQL UPDATE
  → @PostUpdate
  → SQL/query result
  → commit hoặc rollback
```

### Timeline C: remove rồi rollback

```text
em.find(Book)
  → @PostLoad
  → em.remove(Book)
  → @PreRemove
  → SQL DELETE (flush)
  → @PostRemove
  → rollback
```

Kết quả DB sau rollback có thể vẫn giữ Book; Java objects vẫn có thể mang state của transaction thất bại.

### Timeline D: bulk update

```text
JPQL UPDATE Book SET title=...
  → SQL UPDATE nhiều rows
  → KHÔNG gọi @PreUpdate/@PostUpdate cho từng Book
  → managed Book instances có thể stale
```

Các timeline thể hiện khả năng thường gặp, không phải mọi JPA provider phải phát cùng sequence SQL ở từng dòng Java.

## 56. Một hướng kiểm thử tích hợp đơn giản

Nên kiểm tra callback bằng **kết quả persistence thực tế** thay vì chỉ gọi method callback như unit test.

Giả sử Book ở mục 4 dùng timestamps, integration test có `EntityManagerFactory emf` được cấu hình với Book và database phù hợp.

Helper:

```java
public final class JpaTransactions {

    private final EntityManagerFactory emf;

    public JpaTransactions(EntityManagerFactory emf) {
        this.emf = emf;
    }

    public <T> T run(Function<EntityManager, T> work) {
        EntityManager em = emf.createEntityManager();

        try {
            em.getTransaction().begin();

            T result = work.apply(em);

            em.getTransaction().commit();

            return result;
        } catch (RuntimeException failure) {
            if (em.getTransaction().isActive()) {
                try {
                    em.getTransaction().rollback();
                } catch (RuntimeException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
            }
            throw failure;
        } finally {
            em.close();
        }
    }
}
```

Helper dùng `java.util.function.Function` và resource-local transaction. Với Spring/JTA-managed EntityManager, dùng transaction manager tương ứng thay vì tự gọi `getTransaction()`.

### Vì sao dùng context mới sau commit?

Nếu chỉ đọc lại cùng Book managed trong context đã persist, test có thể phản ánh state Java đã được callback gán nhưng không chứng minh DB đã commit các giá trị đó. Để test data persistence, commit và dùng EntityManager mới.

## 57. Test `@PrePersist` lưu timestamps

```java
@Test
void prePersistSetsCreatedAndUpdatedAt() {
    JpaTransactions tx = new JpaTransactions(emf);

    Long bookId = tx.run(em -> {
        Book book = new Book(
            "JPA",
            new BigDecimal("150000.00")
        );

        em.persist(book);

        // Với IDENTITY, ID thường có sau INSERT;
        // để bảo đảm key sẵn sàng trong test, flush.
        em.flush();

        return book.getId();
    });

    Book persisted = tx.run(
        em -> em.find(Book.class, bookId)
    );

    assertNotNull(persisted);
    assertNotNull(persisted.getCreatedAt());
    assertNotNull(persisted.getUpdatedAt());
}
```

Test xác minh **dữ liệu đã commit** có audit timestamps. Không dùng một test chỉ assert `book.getCreatedAt() != null` ngay sau `persist()` như bằng chứng duy nhất rằng DB đã lưu field.

Nếu transaction khác có thể xóa Book test, fixture phải cô lập hoặc dùng ID riêng.

## 58. Test `@PreUpdate` và thời điểm flush

```java
@Test
void preUpdateChangesUpdatedAtWhenBookIsDirty() {
    Long id = seedBookAndCommit();

    Instant initialUpdatedAt = inFreshContext(em ->
        em.find(Book.class, id).getUpdatedAt()
    );

    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        Book book = em.find(Book.class, id);
        book.rename("Title changed");

        em.flush();

        assertNotNull(book.getUpdatedAt());

        em.getTransaction().commit();
    } finally {
        if (em.getTransaction().isActive()) {
            em.getTransaction().rollback();
        }
        em.close();
    }

    Instant committedUpdatedAt = inFreshContext(em ->
        em.find(Book.class, id).getUpdatedAt()
    );

    assertNotNull(committedUpdatedAt);
    // Không assert nano-precision bằng clock hệ thống nếu
    // DB TIMESTAMP làm tròn hoặc hai lần thao tác quá gần.
}
```

`seedBookAndCommit` và `inFreshContext` là test helpers cần triển khai. Nếu muốn kiểm tra thời gian thay đổi, dùng deterministic clock/test fixture hoặc khoảng thời gian đủ phân biệt và không dựa vào clock precision quá mức.

Một test quan trọng khác: tải Book rồi không sửa persistent field, flush/commit và kiểm tra listener **không tự tạo update vô hạn**. Chi tiết cần theo provider và mapping.

## 59. Test listener riêng bằng state có thể quan sát

Giả sử listener:

```java
public class NormalizeListener {

    @PrePersist
    public void beforeInsert(Book book) {
        book.normalizeTitle();
    }
}
```

Book:

```java
@Entity
@EntityListeners(NormalizeListener.class)
public class Book {

    private String title;

    public void normalizeTitle() {
        title = title.trim();
    }
}
```

Test:

```java
@Test
void listenerNormalizesTitleBeforeInsert() {
    Long id = transactions.run(em -> {
        Book book = new Book("  JPA  ", price);
        em.persist(book);
        em.flush();
        return book.getId();
    });

    String title = transactions.run(em ->
        em.find(Book.class, id).getTitle()
    );

    assertEquals("JPA", title);
}
```

Mẫu này chỉ mang tính minh họa: ví dụ Book của mục 4 đã trim title ở domain method; trong test listener này constructor nên giữ raw input để chứng minh listener là nơi thực hiện normalize, hoặc nên chọn một field khác chưa được chuẩn hóa. Điều quan trọng là test một hành vi có thể quan sát sau commit.

Không cần dùng static counter để đếm mọi callback nếu mục tiêu nghiệp vụ chỉ là chuẩn hóa field.

## 60. Test `@PostLoad` cho `@Transient`

Giả sử Book có transient derived field:

```java
@Transient
private BigDecimal discountedPrice;

@PostLoad
void calculateDiscountedPrice() {
    discountedPrice = calculateFromPersistentFields();
}
```

Test:

```java
@Test
void postLoadInitializesTransientValue() {
    Long id = seedBookWithDiscountAndCommit();

    EntityManager em = emf.createEntityManager();

    try {
        Book book = em.find(Book.class, id);

        assertNotNull(book.getDiscountedPrice());
        assertEquals(
            expectedDiscountPrice,
            book.getDiscountedPrice()
        );
    } finally {
        em.close();
    }
}
```

Nếu muốn chắc `@PostLoad` chạy do DB load thay vì instance đã managed từ seed, seed trong transaction khác rồi đóng context trước test.

Không dùng callback counter như phép chứng minh cache miss; provider có thể load state từ L2 mà vẫn gọi lifecycle callback theo implementation.

## 61. Test callback không chạy cho bulk JPQL DML

Một test nên chuẩn bị:

1. Entity Book có `@PreUpdate` đặt `updatedAt`.
2. Seed Book và commit.
3. Chạy bulk JPQL `UPDATE Book ...` mà **không trực tiếp sửa updatedAt**.
4. Commit.
5. Mở EntityManager mới kiểm tra title đã đổi nhưng callback-generated updatedAt không tự đổi bởi bulk DML.
6. Kiểm soát DB trigger hoặc column default có thể tự thay timestamp, nếu không test sẽ bị nhiễu.

Ví dụ:

```java
@Test
void bulkUpdateBypassesEntityPreUpdate() {
    Long id = seedBookAndCommit();

    Instant before = loadCommittedUpdatedAt(id);

    transactions.run(em -> {
        int changed = em.createQuery(
            "UPDATE Book b " +
            "SET b.title = :title WHERE b.id = :id"
        ).setParameter("title", "Bulk title")
         .setParameter("id", id)
         .executeUpdate();

        assertEquals(1, changed);
        return null;
    });

    Instant after = loadCommittedUpdatedAt(id);

    assertEquals(before, after);
}
```

Test này giả định DB không có trigger tự cập nhật timestamp. Nó chứng minh sự khác nhau giữa bulk DML và entity lifecycle update, không có nghĩa mọi database bắt buộc không update `updatedAt` khi trigger khác tồn tại.

## 62. Test rollback: Post* không phải after commit

Không nên test bằng cách thật sự gửi email ở callback. Hãy dùng một test-only event recorder được cô lập để xác nhận callback có thể xảy ra trước rollback.

Ví dụ ý tưởng:

```text
Begin transaction
Persist Book, flush
Record @PostPersist đã được kích hoạt (test probe)
Rollback
Use new EntityManager:
    Book không tồn tại ở database
Nhưng test probe có thể đã ghi nhận @PostPersist
```

Nếu dùng static counter để quan sát callback:

- Reset trước test.
- Không chạy test song song dùng chung counter.
- Không sử dụng static probe trong production.
- Đảm bảo event recorder không ảnh hưởng transaction/JPA operations.
- Ghi chú rằng số lượng/thứ tự callbacks có thể khác ở lifecycle graph phức tạp.

Mục tiêu là **chứng minh callback invocation không bằng durable commit**, không dùng listener làm integration event publisher.

## 63. Test callback ordering qua hierarchy

Một project có:

```text
DefaultListener (XML)
    ↓
BaseEntityListener (@MappedSuperclass)
    ↓
BookListener (@Entity)
    ↓
BaseEntity callback
    ↓
Book callback
```

Test có thể dùng một test-only recorder ghi các marker:

```java
events.add("default-pre-persist");
events.add("base-listener-pre-persist");
events.add("book-listener-pre-persist");
events.add("base-entity-pre-persist");
events.add("book-entity-pre-persist");
```

Sau khi persist, assert thứ tự **theo JPA callback ordering rules thực sự có trong mapping**. Cần chuẩn bị đúng XML/default listener inheritance và không dùng global shared recorder nếu các test chạy song song.

Một test khác có `@ExcludeDefaultListeners` để xác minh default callbacks bị loại trừ đúng; test `@ExcludeSuperclassListeners` để xác minh listeners ở superclass không áp dụng theo policy.

Đừng cố chấm thứ tự giữa callbacks của **nhiều entity instances trong cascaded graph** nếu ordering đó không được contract bảo đảm.

## 64. Checklist chọn vị trí đặt logic

Trước khi đưa code vào callback hay listener, hãy hỏi:

1. Logic có gắn với **state cục bộ** của chính entity không?
2. Có cần chạy khi entity được persist, update, remove hay load không?
3. Có chỉ xử lý scalar fields không, hay cần truy cập associations?
4. Có cần `EntityManager`, query hoặc repository không?
5. Có cần dữ liệu của nhiều entities trong cùng transaction không?
6. Có I/O, external API, email, message broker hoặc filesystem không?
7. Có phải chạy **sau commit thành công** không?
8. Có cần áp dụng cho bulk JPQL/native SQL hoặc external writers không?
9. Có cần bảo vệ bằng database constraint/trigger không?
10. Có sẵn domain method để validate sớm hơn không?
11. Callback có thể chạy tại flush/auto-flush thay vì dòng setter không?
12. `@PrePersist` có phụ thuộc database-generated ID chưa có không?
13. `@PostPersist` có bị hiểu sai thành transaction đã commit không?
14. `@PreUpdate` có thể không chạy nếu không có persistent change không?
15. `@PostLoad` có thể tính derived value bị stale sau setter không?
16. Entity có extends mapped superclass chứa callbacks không?
17. Có default listeners trong ORM XML không?
18. Có listener trùng từ superclass và entity không?
19. Có cần `@ExcludeDefaultListeners` hoặc `@ExcludeSuperclassListeners` không?
20. Listener có mutable internal state/thread-safety problem không?
21. Có injection/provider/CDI dependency không portable không?
22. Logic audit có cần actor context và timezone policy rõ không?
23. Có nguy cơ N+1 do lazy associations trong callback không?
24. Có liên quan `@Version`, entity state và rollback không?
25. Có integration test sau commit với EntityManager mới không?
26. Có test native/bulk paths vốn bypass callbacks không?
27. Có test rollback không tạo external side effects giả thành công không?
28. Có quan sát SQL/flush timing khi debug không?
29. Có định nghĩa rõ transaction/error boundary của service không?
30. Có giải pháp after-commit/outbox nếu cần sự kiện nghiệp vụ đáng tin không?

Nếu nhiều câu trả lời cho thấy logic phụ thuộc database/relationships/external services, **application service hoặc transactional outbox** thường phù hợp hơn entity lifecycle callback.

## 65. Các hiểu nhầm thường gặp

### Hiểu nhầm 1: Callback là một Java setter đặc biệt

Không. Callback do JPA provider gọi tại lifecycle operation; setter thông thường không tự kích hoạt `@PreUpdate`.

### Hiểu nhầm 2: `@PreUpdate` luôn gọi mỗi khi `save()`

Không. Cần xem entity state, dirty checking, flush, merge và provider. Không phải mọi `save` tạo SQL UPDATE.

### Hiểu nhầm 3: `@PostPersist` nghĩa là insert đã commit

Sai. SQL INSERT có thể đã chạy nhưng transaction còn có thể rollback.

### Hiểu nhầm 4: `@PostRemove` là nơi xóa file/email an toàn

Không. Side effects ngoài DB không rollback cùng transaction.

### Hiểu nhầm 5: `@PrePersist` chắc chắn có IDENTITY ID

Không. ID do DB sinh có thể chưa được gán tại PrePersist.

### Hiểu nhầm 6: Callback trong entity và listener dùng chung method signature

Không. Entity callback không tham số; listener nhận entity.

### Hiểu nhầm 7: Entity listener tự có Spring DI ở mọi JPA runtime

Không. Phải phân biệt CDI/Jakarta Persistence support, Spring integration và Java SE bootstrap.

### Hiểu nhầm 8: Listener được gọi một lần cho toàn transaction

Không. Lifecycle callbacks gắn với entities và events, không phải một transaction-level listener chung.

### Hiểu nhầm 9: `@PostLoad` chạy mỗi lần gọi `find()`

Không nhất thiết. Identity map có thể trả managed instance đã có.

### Hiểu nhầm 10: `@PostLoad` là nơi tốt để lazy-load mọi associations

Không. Có thể gây N+1 và callback reentrancy.

### Hiểu nhầm 11: Bulk JPQL UPDATE sẽ chạy `@PreUpdate` cho từng row

Không. Bulk DML bỏ qua entity lifecycle callbacks.

### Hiểu nhầm 12: Native SQL DELETE chạy `@PreRemove`

Không. Nó tác động database trực tiếp.

### Hiểu nhầm 13: Database trigger kích hoạt JPA listener

Không. Trigger và listener ở hai tầng khác nhau.

### Hiểu nhầm 14: `@PreUpdate` của Order chạy khi mọi OrderLine thay đổi

Không bảo đảm. Parent row phải có update lifecycle tương ứng hoặc application dùng cơ chế root version/timestamp riêng.

### Hiểu nhầm 15: Callback được phép mở transaction/query tùy ý

Không portable và dễ gây reentrancy/flush issues. Đưa coordination sang service.

### Hiểu nhầm 16: Exception từ listener có thể bỏ qua và tiếp tục commit

Không nên. Transaction có thể rollback-only và persistence state đã thất bại.

### Hiểu nhầm 17: Mapped superclass callbacks giống default listeners

Không. Chúng có nguồn và exclusion rules khác nhau.

### Hiểu nhầm 18: `@ExcludeDefaultListeners` vô hiệu mọi callback

Không. Nó chỉ hướng tới default listeners.

### Hiểu nhầm 19: `@ExcludeSuperclassListeners` xóa mọi behavior của superclass

Không. Nó có phạm vi cụ thể với superclass listeners, không phải lệnh xóa inheritance của entity.

### Hiểu nhầm 20: Callback có thể tự tăng `@Version` để giải quyết concurrency

Không nên. Version field do JPA/provider quản lý.

### Hiểu nhầm 21: Spring Data `@CreatedDate` là JPA lifecycle annotation

Không. Đó là Spring Data auditing feature.

### Hiểu nhầm 22: Listener có thể thay mọi business service validation

Không. Authorization/transaction/multi-entity rules vẫn thuộc service và DB constraints.

### Hiểu nhầm 23: `@PostUpdate` luôn chạy sau cả các SQL khác

Không. Nó chạy theo lifecycle update tương ứng, có thể trước những thao tác khác trong transaction.

### Hiểu nhầm 24: Event recorder trong test chứng minh dữ liệu đã commit

Không. Nó chỉ chứng minh listener đã được gọi.

### Hiểu nhầm 25: Callback order giữa parent/child là thứ tự Java collection

Không portable. Chỉ dựa trên ordering rules được spec áp dụng.

## 66. Bài tập thực hành

### Bài 1: Chọn callback cho createdAt

**Yêu cầu:** Khi INSERT một Book mới bằng JPA managed persistence, tự gán `createdAt` nếu chưa có.

**Gợi ý:** `@PrePersist` trên entity/mapped superclass hoặc listener; ghi `Instant.now()` theo clock policy. Không dựa vào IDENTITY ID.

### Bài 2: Chọn callback cho updatedAt

**Yêu cầu:** Khi một managed Book bị UPDATE, cập nhật `updatedAt`.

**Gợi ý:** `@PreUpdate`. Cần biết bulk/native SQL không chạy nó và chỉ setter không nhất thiết tạo UPDATE.

### Bài 3: Sau INSERT gửi email

**Câu hỏi:** Có dùng `@PostPersist` để gửi email xác nhận tạo Book không?

**Đáp án:** Không nên. Callback có thể chạy trước commit; nếu rollback email đã gửi sai. Dùng after-commit/outbox phù hợp.

### Bài 4: Không thay đổi field

Một transaction `find(Book)`, gọi getter, rồi commit.

**Câu hỏi:** `@PreUpdate` chắc chắn chạy không?

**Đáp án:** Không. Nếu Book không dirty và không có update, không thể dựa vào PreUpdate.

### Bài 5: Callback trong entity có tham số

```java
@PrePersist
void before(Book other) {}
```

**Câu hỏi:** Có phải signature chuẩn của callback trong entity?

**Đáp án:** Không. Callback method trong entity không nhận tham số.

### Bài 6: Listener nhận một entity

```java
@PrePersist
void before(Book book) {}
```

**Câu hỏi:** Có thể dùng trong listener class không?

**Đáp án:** Có, nếu listener được khai báo đúng và đáp ứng JPA callback method requirements.

### Bài 7: Mọi Book tạo được trim

**Câu hỏi:** Đặt trim title ở domain method hay PrePersist?

**Gợi ý:** Domain method giúp validate/normalize sớm. PrePersist có thể là lớp phòng vệ bổ sung cho managed insert. Nếu bulk/native writes cũng tồn tại, cần constraints/SQL rule phù hợp.

### Bài 8: @PostLoad và derived field

Book có `@Transient totalWithTax` tính trong PostLoad. Sau đó code sửa price.

**Câu hỏi:** totalWithTax tự đổi không?

**Đáp án:** Không. Cần tính lại ở setter hoặc dùng computed getter/DTO.

### Bài 9: @PostLoad và identity map

Hai lần `em.find(Book.class, id)` cùng EntityManager.

**Câu hỏi:** Có bắt buộc hai lượt PostLoad không?

**Đáp án:** Không. Lần hai có thể trả managed instance đã load.

### Bài 10: OrderLine orphan removal

Order gỡ line, provider xóa child khi flush.

**Câu hỏi:** Parent `@PreUpdate` chắc chắn chạy?

**Đáp án:** Không. Xóa child không nhất thiết update row parent. Child remove lifecycle mới là mốc liên quan theo operation.

### Bài 11: Native SQL UPDATE

```sql
UPDATE books SET title = ? WHERE id = ?;
```

**Câu hỏi:** `@PreUpdate` có chạy không?

**Đáp án:** Không theo managed entity lifecycle.

### Bài 12: Bulk CriteriaUpdate

Một batch dùng `CriteriaUpdate<Book>`.

**Câu hỏi:** Entity listeners có áp dụng cho từng row không?

**Đáp án:** Không; đó là bulk DML, không phải per-entity lifecycle update.

### Bài 13: Rollback

`@PostPersist` đã được ghi nhận trong test probe, sau đó rollback.

**Câu hỏi:** Database bắt buộc còn Book không?

**Đáp án:** Không. Callback invocation không đồng nghĩa commit.

### Bài 14: Listener cần repository

AuditListener muốn query table Users để lấy tên người sửa.

**Câu hỏi:** Có portable không?

**Đáp án:** Không nên. Callback không phải nơi thực hiện EntityManager/query hoặc truy cập graph khác; lấy actor từ service/auditing context có thiết kế rõ.

### Bài 15: Default listener

Book không khai báo `@EntityListeners` nhưng default listener từ ORM XML vẫn chạy.

**Câu hỏi:** Có sai không?

**Đáp án:** Không. Default listeners được cấu hình ngoài Java entity class.

### Bài 16: Exclude default

Book có `@ExcludeDefaultListeners`.

**Câu hỏi:** Entity-local `@PrePersist` có tự bị tắt không?

**Đáp án:** Không. Annotation loại default listeners theo quy tắc, không tắt mọi entity callbacks.

### Bài 17: Exclude superclass

Một mapped superclass khai báo AuditListener; subclass có `@ExcludeSuperclassListeners`.

**Câu hỏi:** Điều gì bị loại?

**Đáp án:** Superclass listeners theo quy tắc inheritance, không phải mọi phương thức/field của superclass.

### Bài 18: Listener đếm số lần POST update

Một test chạy với Hibernate batching, gọi `save` cho 30 Books rồi commit.

**Câu hỏi:** Có thể assert số callback bằng số gọi save không?

**Đáp án:** Không nên. Cần xem bao nhiêu entity thực sự được update và provider lifecycle; `save` không bảo đảm UPDATE cho mỗi lời gọi.

### Bài 19: Version

Listener `@PreUpdate` tự tăng field `@Version`.

**Câu hỏi:** Có nên không?

**Đáp án:** Không. Version là cơ chế JPA quản lý cho optimistic locking.

### Bài 20: User identity

Batch job không có HTTP principal nhưng listener cố đọc user từ Spring SecurityContext.

**Câu hỏi:** Rủi ro?

**Đáp án:** Context có thể rỗng/sai, gây audit null hoặc gán actor không đúng. Cần explicit actor policy cho batch.

### Bài 21: Domain event

Sau mỗi update Book cần gửi message tới hệ thống tìm kiếm.

**Câu hỏi:** `@PostUpdate` có đủ đảm bảo một message ứng với update committed không?

**Đáp án:** Không. Callback có thể chạy trước rollback, có thể retry và không có delivery guarantee. Xem transactional outbox và consumer idempotency.

### Bài 22: Query auto-flush

Ứng dụng đổi Book.title, rồi gọi JPQL SELECT trong AUTO.

**Câu hỏi:** Vì sao `@PreUpdate` có thể xuất hiện trong stack trace ở SELECT?

**Đáp án:** Query-triggered auto-flush đồng bộ pending Book update trước khi trả kết quả.

### Bài 23: Listener kế thừa

`BaseEntity` có listener và `Book` có listener riêng.

**Câu hỏi:** Cần kiểm tra gì?

**Đáp án:** Thứ tự default/superclass/entity listeners và callback methods, cùng exclusion/override rules.

### Bài 24: Truy cập lazy relation trong PostLoad

`@PostLoad` đọc `book.getReviews().size()` cho 100 Books.

**Câu hỏi:** Có nguy cơ gì?

**Đáp án:** N+1 hoặc reentrant loading, transaction/SQL overhead. Đưa fetch plan/aggregation sang query/service.

### Bài 25: Chọn công cụ

Một hệ thống có cả JPA, JDBC batch và stored procedures; mọi thay đổi price phải được audit.

**Gợi ý:** Không dựa duy nhất vào `@PreUpdate`; xây policy cho mọi đường ghi, database audit/CDC hoặc application transaction audit phù hợp, và test end-to-end.

## Kết luận

**JPA lifecycle callbacks và entity listeners giúp xử lý logic cục bộ tại những mốc của vòng đời entity được quản lý**, không phải một cơ chế thay thế transaction, application service hay database constraints.

Bảy sự kiện chuẩn — `@PrePersist`, `@PostPersist`, `@PreUpdate`, `@PostUpdate`, `@PreRemove`, `@PostRemove` và `@PostLoad` — tương ứng các điểm chèn trước/sau persistence operations hoặc sau khi load entity. Callback trong entity thường phù hợp quy tắc gắn chặt với chính entity; listener riêng phù hợp cross-cutting behavior như timestamps, normalization và một số loại audit metadata. Khi có superclass/default listeners, phải hiểu thứ tự gọi, `@EntityListeners` và các annotation exclusion.

Điểm cần khắc sâu là **callback chạy theo lifecycle của JPA, không theo thời điểm giao dịch đã commit bền vững**. `@PostPersist`/`@PostUpdate`/`@PostRemove` có thể chạy trước commit và không tự rollback tác dụng phụ bên ngoài. `@PreUpdate` không chạy chỉ vì setter được gọi và **không áp dụng cho mọi bulk JPQL/Criteria/native SQL**; `@PostLoad` không chắc chạy mỗi lần `find` nếu entity đã managed trong context.

Một callback tốt nên **nhỏ, xác định được, thao tác chủ yếu trên non-relationship state của entity hiện tại và không gọi database/external services**. Với logic nhiều entities, validation/phân quyền, domain events sau commit hoặc audit trên mọi đường ghi, hãy chọn service, transaction synchronization, outbox, DB constraints hoặc auditing infrastructure phù hợp.

Khi thiết kế, hãy hỏi: **“Đây là sự kiện của entity hay transaction? Logic chỉ cần state cục bộ hay phải truy cập database/relationship? Nó có phải chạy với bulk/native updates không? Nếu transaction rollback sau callback, hệ thống có còn đúng không?”**. Trả lời rõ bốn câu hỏi này là nền tảng để sử dụng callback và entity listener đúng vai trò, dễ kiểm thử và không gây tác dụng phụ ngoài ý muốn.
