# Bộ sinh giá trị hoặc định danh tùy chỉnh theo SPI được hỗ trợ trong Hibernate

Trong ứng dụng Java dùng Hibernate, không phải mọi giá trị được lưu xuống cơ sở dữ liệu đều do người dùng hoặc business service điền trực tiếp. Một số thuộc tính cần được **sinh tự động** tại thời điểm Hibernate thực hiện lệnh `INSERT` hoặc `UPDATE`: khóa chính, mã tham chiếu, correlation code, timestamp, mã nghiệp vụ hoặc giá trị do database trigger/default tạo ra.

Ví dụ:

- Một bản ghi `Invoice` cần ID duy nhất trước khi gửi SQL `INSERT`.
- Một `AuditEvent` cần correlation code sinh đúng một lần khi thêm mới.
- Một thuộc tính `lastChangedAt` cần được cập nhật khi Hibernate thực hiện UPDATE.
- Database có cột `created_at DEFAULT CURRENT_TIMESTAMP`, và sau khi INSERT ứng dụng cần đọc lại thời điểm do DB quyết định.
- Một hệ thống cũ có generator ID riêng, nay muốn chuyển sang extension point hiện đại của Hibernate.

Hibernate cung cấp **Generator SPI** để mở rộng cơ chế sinh giá trị một cách có chủ đích. Trong Hibernate ORM hiện đại, hai nhánh chính là:

- `BeforeExecutionGenerator`: Java tạo giá trị **trước** khi SQL tương ứng được thực thi; giá trị có thể được bind qua JDBC như một thuộc tính bình thường.
- `OnExecutionGenerator`: database tạo giá trị **trong khi** INSERT/UPDATE được thực thi, chẳng hạn bằng default, trigger, identity hoặc SQL expression; Hibernate phối hợp lấy giá trị vừa sinh.

Các annotation `@IdGeneratorType` và `@ValueGenerationType` kết nối một custom generator với thuộc tính entity. Đây là các extension points được Hibernate công khai hỗ trợ, tốt hơn việc can thiệp vào chi tiết triển khai nội bộ hoặc tự sửa SQL bằng event listener chỉ để tạo ID.

**Nguyên tắc quan trọng nhất:** sử dụng generator có sẵn của JPA/Hibernate khi nó đáp ứng yêu cầu. Chỉ viết custom generator nếu business contract thực sự không thể biểu đạt đầy đủ bằng `@GeneratedValue`, `@SequenceGenerator`, `@UuidGenerator`, `@CreationTimestamp`, `@UpdateTimestamp` hoặc `@Generated`.

> **Phạm vi phiên bản:** các ví dụ dùng `jakarta.persistence` và hướng SPI của Hibernate ORM 6.2–6.6/7.x. `@IdGeneratorType` được giới thiệu ở Hibernate 6.0; giao diện Generator SPI chung với `BeforeExecutionGenerator` và `OnExecutionGenerator` được mô tả từ Hibernate 6.2. Hibernate 5.x có API cũ như `IdentifierGenerator` và `@GenericGenerator`. Hãy đối chiếu Javadocs đúng `hibernate-core` đang chạy trước khi dùng import hoặc chữ ký phương thức.

---

## 1. Phân biệt “giá trị được sinh” với “định danh được sinh”

Không phải mọi trường tự sinh đều có cùng yêu cầu.

| Trường | Ví dụ | Mục đích | Thời điểm sinh thường gặp |
| --- | --- | --- | --- |
| Identifier | `id` | Định danh entity ổn định | INSERT, không được thay sau khi tạo |
| Correlation code | `eventCode` | Theo dõi sự kiện qua dịch vụ | INSERT |
| Creation timestamp | `createdAt` | Ghi thời điểm tạo | INSERT |
| Update timestamp | `updatedAt` | Ghi thời điểm cập nhật | INSERT và UPDATE |
| Version | `@Version` | Optimistic locking | INSERT và UPDATE, theo quy tắc ORM |
| Database calculated column | `lineTotal` | Giá trị tính từ các cột khác | INSERT/UPDATE ở DB |
| Business number | `invoiceNumber` | Số hóa đơn theo quy tắc pháp lý/nghiệp vụ | Phụ thuộc state machine, có thể cần service/DB riêng |

**Khóa chính** phải đủ duy nhất và bất biến trong phạm vi được quy định. **Business number** đôi khi có quy tắc định dạng, cấp số theo năm, chi nhánh hoặc chỉ được phát hành khi chứng từ chuyển trạng thái. Không nên tự đồng nhất hai khái niệm ấy.

Ví dụ: một hóa đơn mới có thể nhận `id=UUID` ngay khi persist, còn số hóa đơn chính thức chỉ được cấp khi nghiệp vụ xác nhận và được bảo vệ bởi transaction/unique constraint. Viết một generator ID tự tăng “không có khoảng trống” không phải lời giải cho số chứng từ pháp lý.

## 2. Những lựa chọn có sẵn trước khi viết SPI

JPA và Hibernate có nhiều chiến lược sinh giá trị tiêu chuẩn.

### 2.1. Database identity

```java
@Entity
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
}
```

Database tạo ID khi INSERT. Hibernate dùng cơ chế lấy generated key tương thích driver/dialect.

Phù hợp khi database dùng identity/auto-increment. Nhược điểm có thể là giới hạn khả năng gom batch INSERT và thời điểm phải thực hiện INSERT để biết ID, tùy Hibernate/DBMS.

### 2.2. Database sequence

```java
@Entity
public class PurchaseOrder {

    @Id
    @SequenceGenerator(
        name = "purchaseOrderSeq",
        sequenceName = "purchase_order_seq",
        allocationSize = 50
    )
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "purchaseOrderSeq"
    )
    private Long id;
}
```

Thích hợp khi DBMS hỗ trợ sequence. Hibernate có các optimizer giúp giảm số round trips, nhưng cấu hình sequence và allocation size phải phù hợp với DDL và những writers cùng sử dụng sequence.

### 2.3. UUID

```java
@Entity
public class Payment {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;
}
```

`GenerationType.UUID` thuộc Jakarta Persistence 3.1, chỉ áp dụng nếu stack JPA/Hibernate hỗ trợ.

Hibernate cũng có:

```java
@Entity
public class Payment {

    @Id
    @org.hibernate.annotations.UuidGenerator
    private UUID id;
}
```

`@UuidGenerator` của Hibernate cho phép lựa chọn strategy/algorithm theo phiên bản. Với UUID thông thường, **không cần tự viết `BeforeExecutionGenerator` chỉ để gọi `UUID.randomUUID()`**.

### 2.4. Timestamp và giá trị do DB tạo

```java
@CreationTimestamp
private Instant createdAt;

@UpdateTimestamp
private Instant updatedAt;
```

Hoặc để database tạo:

```java
@CurrentTimestamp(source = SourceType.DB)
private Instant modifiedAt;
```

Tùy Hibernate version, mapping và mong muốn sử dụng thời gian JVM hay DB, lựa chọn annotation phù hợp. Một timestamp dùng cho audit không nhất thiết được sinh bằng custom SPI.

### 2.5. Bảng lựa chọn nhanh

| Nhu cầu | Lựa chọn nên xem trước | Khi nào custom SPI có ích? |
| --- | --- | --- |
| ID tự tăng ở DB | `IDENTITY` | Hiếm khi; ưu tiên DB/provider |
| ID bằng sequence | `SEQUENCE` + `@SequenceGenerator` | Cần chiến lược đặc thù không biểu đạt được bằng chuẩn |
| ID dạng UUID | `GenerationType.UUID` / `@UuidGenerator` | Cần cấu trúc/thuật toán ID độc quyền có contract rõ |
| Created/updated timestamp | `@CreationTimestamp` / `@UpdateTimestamp` | Cần timestamp theo logic khác có kiểm thử |
| DB default/trigger | `@Generated` / `@GeneratedColumn` | Chỉ custom OnExecution khi mapping có sẵn không đáp ứng |
| Correlation code tự động | Service/domain method hoặc custom value generator | Khi gắn chặt vào lifecycle INSERT và nhiều entity dùng lại |
| Số chứng từ không trùng | DB allocator/sequence + unique constraint | Custom SPI chỉ là một phần; business transaction vẫn cần |

**Không viết generator chỉ vì có thể viết.** Mỗi custom SPI là một phần code gắn với vòng đời ORM, phải duy trì qua các lần nâng Hibernate.

## 3. “SPI được hỗ trợ” có nghĩa gì?

SPI (*Service Provider Interface*) là giao diện mở rộng mà framework công khai để ứng dụng hoặc thư viện triển khai. Với generator, Hibernate công bố các kiểu trong `org.hibernate.generator` và meta-annotations trong `org.hibernate.annotations`.

Một cách tiếp cận có chủ đích:

```text
Entity field
   |
   v
Custom annotation @SalesId / @GenerateCode
   |
   v
@IdGeneratorType / @ValueGenerationType
   |
   v
Generator implementation
   |                      |
   v                      v
BeforeExecutionGenerator  OnExecutionGenerator
   |                      |
   v                      v
Java tạo giá trị          Database tạo giá trị
   |                      |
   v                      v
Bind vào INSERT/UPDATE     SQL/trigger/default/identity
                          |
                          v
                    Hibernate lấy giá trị về
```

Mục tiêu là dùng API có contract công khai:

- Không sửa subclass/hàm nội bộ của Hibernate khi không được thiết kế làm extension point.
- Không phụ thuộc thứ tự callback nội bộ không được bảo đảm.
- Không tự gọi JDBC `commit`/`close` trong generator.
- Không sửa metadata mapping đã khởi tạo bằng reflection runtime.
- Không dùng `@PrePersist` như cách thay thế mù quáng cho chiến lược sinh identifier chuẩn.

API SPI vẫn có thể thay đổi giữa major/minor versions theo chính sách của Hibernate. Vì vậy luôn ghim dependency và kiểm tra migration guide/Javadocs khi nâng phiên bản.

## 4. Hợp đồng `Generator`

Trong Hibernate 6.x, giao diện gốc của hệ thống sinh giá trị là:

```java
org.hibernate.generator.Generator
```

Hai nhánh mở rộng quan trọng:

```java
org.hibernate.generator.BeforeExecutionGenerator
org.hibernate.generator.OnExecutionGenerator
```

Một generator thường cung cấp:

- `getEventTypes()`: những sự kiện nào làm nó sinh lại giá trị.
- `generatedOnExecution()`: giá trị sinh trong DB khi SQL chạy hay sinh trước ở Java.
- Với `BeforeExecutionGenerator`: `generate(...)`.
- Với `OnExecutionGenerator`: cách biểu diễn cột/SQL expression và cơ chế lấy generated values do Hibernate phối hợp.

### Các sự kiện sinh giá trị

```java
org.hibernate.generator.EventType
org.hibernate.generator.EventTypeSets
```

Những tập được cung cấp:

| Event set | Ý nghĩa |
| --- | --- |
| `EventTypeSets.INSERT_ONLY` | Sinh khi Hibernate INSERT |
| `EventTypeSets.UPDATE_ONLY` | Sinh khi Hibernate UPDATE |
| `EventTypeSets.INSERT_AND_UPDATE` | Sinh ở cả hai |
| `EventTypeSets.NONE` | Không tham gia generation event |
| `EventTypeSets.ALL` | Tập sự kiện được SPI hỗ trợ |

**Identifier generator phải dùng INSERT-only** vì ID của một entity không được tùy tiện đổi qua UPDATE.

### Không nhầm generation event với event listener

`EventType.INSERT` của Generator SPI mô tả thời điểm sinh giá trị theo SQL lifecycle. Nó không phải `PostInsertEventListener` hoặc cơ chế publish domain event, và cũng không nghĩa “ngay lúc gọi constructor entity”.

## 5. `BeforeExecutionGenerator` hoạt động thế nào?

Giao diện có phương thức cốt lõi:

```java
Object generate(
    SharedSessionContractImplementor session,
    Object owner,
    Object currentValue,
    EventType eventType
);
```

Ý nghĩa tham số:

| Tham số | Vai trò |
| --- | --- |
| `session` | Session Hibernate đang điều phối thao tác |
| `owner` | Entity sở hữu field được sinh |
| `currentValue` | Giá trị đang gán cho field, có thể null |
| `eventType` | INSERT hoặc UPDATE dẫn đến generation |

Generator trả về một giá trị Java tương thích kiểu thuộc tính được mapping. Hibernate xử lý việc đưa giá trị ấy vào SQL tương ứng.

Ví dụ ở mức ngữ nghĩa:

```text
Entity.persist / flush
      |
      v
Hibernate xác định INSERT cần chạy
      |
      v
BeforeExecutionGenerator.generate(...)
      |
      v
id = "SO_..." hoặc eventCode = "EVT_..."
      |
      v
INSERT ... VALUES (?, ?, ...)
      |
      v
Database
```

**Sinh trước execution không có nghĩa callback chạy chính xác lúc gọi `persist()` ở mọi chiến lược.** Thời điểm Hibernate phải có giá trị và thời điểm phát SQL phụ thuộc generator/mapping/flush. Không thiết kế logic nghiệp vụ dựa vào một thứ tự “thấy trong log” của một version.

## 6. Custom ID generator dùng annotation type-safe

Ví dụ yêu cầu nghiệp vụ: ID của `SalesDocument` được lưu dạng chuỗi có prefix `SO_` và thành phần ngẫu nhiên đủ dài, ví dụ:

```text
SO_37e51c8e1e954365af6707b306cd4e7d
```

Đây là **surrogate ID** có prefix để phân biệt loại đối tượng trong logs. Không dùng nó như một số thứ tự kinh doanh có tính liên tục hoặc làm khóa sắp xếp theo thời gian.

Ta triển khai bằng:

1. Meta-annotation `@IdGeneratorType`.
2. Custom annotation `@SalesId`.
3. Class `SalesIdGenerator implements BeforeExecutionGenerator`.
4. Entity field `@Id @SalesId(...)`.

Ví dụ dành cho Hibernate 6.2+.

### 6.1. Khai báo annotation `@SalesId`

```java
package com.example.sales.id;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.hibernate.annotations.IdGeneratorType;

@IdGeneratorType(SalesIdGenerator.class)
@Target({ElementType.FIELD, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
public @interface SalesId {
    String prefix() default "SO_";
}
```

Giải thích:

- `@IdGeneratorType(SalesIdGenerator.class)` liên kết annotation với Generator SPI.
- `@Target` cho phép đặt trên field hoặc getter theo access type của entity.
- `@Retention(RUNTIME)` bắt buộc để Hibernate đọc annotation khi bootstrap.
- Member `prefix` là cấu hình tường minh và có kiểu.

`@SalesId` **không cần** `@GeneratedValue(generator = "...")`, vì bản thân custom annotation đã khai báo ID generator.

### 6.2. Triển khai `SalesIdGenerator`

```java
package com.example.sales.id;

import java.lang.reflect.Member;
import java.util.EnumSet;
import java.util.UUID;

import org.hibernate.engine.spi.SharedSessionContractImplementor;
import org.hibernate.generator.BeforeExecutionGenerator;
import org.hibernate.generator.EventType;
import org.hibernate.generator.EventTypeSets;
import org.hibernate.generator.GeneratorCreationContext;

public class SalesIdGenerator implements BeforeExecutionGenerator {

    private final String prefix;

    public SalesIdGenerator(
            SalesId annotation,
            Member annotatedMember,
            GeneratorCreationContext context) {

        String configuredPrefix = annotation.prefix();

        if (!configuredPrefix.matches("[A-Z]{2,8}_")) {
            throw new IllegalArgumentException(
                "SalesId prefix phải như SO_ hoặc ORDER_"
            );
        }

        this.prefix = configuredPrefix;
    }

    @Override
    public EnumSet<EventType> getEventTypes() {
        return EventTypeSets.INSERT_ONLY;
    }

    @Override
    public Object generate(
            SharedSessionContractImplementor session,
            Object owner,
            Object currentValue,
            EventType eventType) {

        String randomPart = UUID.randomUUID()
            .toString()
            .replace("-", "");

        return prefix + randomPart;
    }
}
```

Đây là generator Java-side:

- Hibernate tạo/khởi tạo generator từ metadata annotation.
- Constructor nhận annotation configuration, annotated member và creation context.
- `getEventTypes()` trả INSERT-only.
- `generate(...)` trả String ID trước SQL INSERT.
- Không tự lấy connection, mở transaction hoặc gọi `session.persist()` từ trong generator.

`Member` và `GeneratorCreationContext` được truyền cho trường hợp cần validate mapping/metadata. Ví dụ không dùng chúng vì chỉ cần prefix. Nếu build bằng một phiên bản Hibernate khác, kiểm tra chữ ký constructor được hỗ trợ của version đó.

### 6.3. Áp dụng vào entity

```java
package com.example.sales.model;

import com.example.sales.id.SalesId;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "sales_documents")
public class SalesDocument {

    @Id
    @SalesId(prefix = "SO_")
    @Column(name = "id", length = 48, nullable = false)
    private String id;

    @Column(nullable = false)
    private String title;

    protected SalesDocument() {}

    public SalesDocument(String title) {
        this.title = title;
    }

    public String getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }
}
```

Ví dụ này trả chuỗi có 3 ký tự prefix và 32 ký tự hex, tổng 35 ký tự; cột dài 48 đủ cho `SO_`. Nếu annotation cho phép prefix dài hơn, schema phải có giới hạn tương ứng. Không thay đổi prefix không kiểm soát khi đã có dữ liệu production.

### 6.4. Sử dụng

```java
@Transactional
public String createDocument(String title) {
    SalesDocument doc = new SalesDocument(title);

    entityManager.persist(doc);
    entityManager.flush();

    return doc.getId();
}
```

`flush()` được đưa vào ví dụ để buộc Hibernate thực hiện các thao tác pending và surface lỗi constraint sớm trong transaction. Nó **không phải commit**; outer `@Transactional` mới điều phối commit. Với generator before-execution, ID có thể sẵn sàng trước thời điểm flush, nhưng đừng dùng điều đó làm giả định về tất cả generator.

### 6.5. Đây chỉ là ví dụ học SPI

Nếu yêu cầu duy nhất là “ID duy nhất toàn cục”, `UUID` gốc + `@UuidGenerator` thường tốt hơn custom String ID. Prefix string:

- Dài hơn và chiếm nhiều bytes ở PK/FK/index.
- Làm locality của index kém nếu phần sau là random UUID.
- Không phù hợp cho sorted-by-creation semantics.
- Cần unique constraint ở database để bảo vệ collision.
- Có thể khiến khách hàng phụ thuộc format ID không phải business contract.

**Chỉ chọn ID format có prefix khi lợi ích vượt chi phí và đã chấp nhận migration/operational constraints.**

## 7. Tại sao phải có unique constraint ở database?

Một generator có thể làm xác suất collision cực thấp, nhưng code Java không thể thay thế ràng buộc duy nhất của database.

```sql
CREATE TABLE sales_documents (
    id VARCHAR(48) PRIMARY KEY,
    title VARCHAR(255) NOT NULL
);
```

Primary key constraint chặn hai transaction chèn cùng ID.

Không được viết:

```java
String id = generator.generate(...);

if (!repository.existsById(id)) {
    repository.save(doc);
}
```

rồi coi đây là bảo đảm concurrency. Giữa `existsById` và INSERT, một transaction khác có thể sử dụng ID đó (**check-then-act race**).

Với collision thực sự xảy ra, hãy để unique violation được phát hiện; rollback transaction hỏng và chỉ retry toàn unit of work trong transaction mới nếu policy cho phép, đảm bảo idempotency của các side effects liên quan.

## 8. Giới hạn của UUID random và các format ID đặc thù

Random UUID có xác suất trùng cực nhỏ trong mô hình phù hợp, nhưng:

- Không tạo thứ tự kinh doanh liên tục.
- Không mã hóa tenant hoặc quyền truy cập.
- Không chứng minh một entity tồn tại.
- Không thay thế idempotency key.
- Không dùng làm secret.
- Không bảo đảm dữ liệu được sắp theo thời gian tạo.
- Việc lộ dạng ID khác nhau có thể làm lộ loại đối tượng nếu prefix mang nghĩa nội bộ.

Nếu cần ID có tính sắp xếp theo thời gian, hãy đánh giá UUID version/time-sortable algorithm được hỗ trợ bởi thư viện có kiểm chứng và database indexes thực tế. Không tự ghép `System.currentTimeMillis()` với vài chữ số ngẫu nhiên rồi tuyên bố nó “unique trong cluster”.

## 9. Cách khác: implement `AnnotationBasedGenerator<A>`

Thay vì constructor ba tham số, Hibernate công bố `AnnotationBasedGenerator<A>` để generator nhận cấu hình một cách có kiểu.

Ví dụ khái niệm dùng lại `@SalesId`:

```java
public final class ConfigurableSalesIdGenerator
        implements BeforeExecutionGenerator,
                   AnnotationBasedGenerator<SalesId> {

    private String prefix;

    public ConfigurableSalesIdGenerator() {
    }

    @Override
    public void initialize(
            SalesId annotation,
            Member member,
            GeneratorCreationContext context) {

        String candidate = annotation.prefix();

        if (!candidate.matches("[A-Z]{2,8}_")) {
            throw new IllegalArgumentException(
                "Prefix không hợp lệ"
            );
        }

        this.prefix = candidate;
    }

    @Override
    public EnumSet<EventType> getEventTypes() {
        return EventTypeSets.INSERT_ONLY;
    }

    @Override
    public Object generate(
            SharedSessionContractImplementor session,
            Object owner,
            Object currentValue,
            EventType eventType) {

        return prefix +
            UUID.randomUUID().toString().replace("-", "");
    }
}
```

Để dùng biến thể này, đổi meta-annotation:

```java
@IdGeneratorType(ConfigurableSalesIdGenerator.class)
public @interface SalesId {
    String prefix() default "SO_";
}
```

Trong code thực, bổ sung imports như ở ví dụ trước.

### Constructor hay `initialize`?

| Cách | Đặc điểm |
| --- | --- |
| Constructor `(Annotation, Member, GeneratorCreationContext)` | Nhận config lúc tạo; có thể lưu field `final` |
| `AnnotationBasedGenerator<A>.initialize(...)` | Kiểu A được compiler kiểm tra; thuận tiện cho cấu hình/initialization |
| Constructor chỉ nhận annotation | Một số Hibernate version hỗ trợ, kiểm tra Javadocs |
| Constructor mặc định | Phù hợp nếu generator không có config cần truyền |

Không tự sáng tạo một cơ chế khởi tạo bằng reflection được Hibernate không công bố. Mỗi custom generator nên chọn **một** cách nhận cấu hình rõ ràng.

## 10. Generator không nên giữ state tăng dần trong instance

Một ví dụ sai:

```java
public class UnsafeSequentialGenerator
        implements BeforeExecutionGenerator {

    private long next = 1L;

    @Override
    public Object generate(
            SharedSessionContractImplementor session,
            Object owner,
            Object currentValue,
            EventType eventType) {
        return next++;
    }

    // ...
}
```

Vấn đề:

- Hai process/JVM đều có `next=1`.
- Sau restart bộ đếm khởi động lại.
- Nếu instance dùng chung qua threads, `next++` không atomic.
- Failover và scale-out có thể gây trùng.
- Cách reset dữ liệu giữa test/prod không rõ.

`AtomicLong` chỉ sửa race **trong một JVM**, không giải quyết uniqueness xuyên nhiều instance hay restart.

**Muốn ID numeric nhiều node, dùng database sequence/identity hoặc ID service có giao thức phân bổ độc quyền rõ ràng, không dùng biến local trong generator.**

## 11. Custom generator sử dụng sequence: nên ưu tiên SPI sẵn có

Một yêu cầu như “ID của SalesDocument lấy từ sequence `sales_doc_seq` và cộng prefix” thường hấp dẫn để viết JDBC trong `generate`.

Tuy nhiên, Hibernate đã có sequence generation/optimizers được kiểm chứng. Nếu muốn numeric ID, dùng `@SequenceGenerator` trước. Nếu muốn chuỗi hiển thị có prefix, có thể:

- Giữ PK numeric sequence.
- Tạo business/display code riêng, dựa trên ID trong bước nghiệp vụ thích hợp.
- Dùng một unique index cho display code.
- Không biến code hiển thị thành PK nếu không có lợi ích rõ.

### Vì sao không tự chạy `SELECT MAX(id)+1`?

```sql
SELECT MAX(id) + 1
FROM sales_documents;
```

Hai transaction đồng thời có thể cùng thấy một max. Ngay cả khi đặt trong `generate`, câu SQL đó không trở thành allocator an toàn.

Có thể dùng lock hoặc bảng cấp số riêng, nhưng phải thiết kế isolation, deadlock retry, throughput, migration và multi-node semantics. Đó là một hệ thống cấp số, không chỉ một vài dòng generator.

### Sequence có thể có khoảng trống

Database sequences thường không rollback giá trị đã cấp, và Hibernate sequence optimizer có thể preallocate blocks. Khi một transaction thất bại hoặc process crash, số có thể bị bỏ qua.

Không viết nghiệp vụ yêu cầu “ID không có lỗ hổng” bằng cách cấm rollback hoặc giảm allocationSize về 1 mà chưa hiểu throughput và các tình huống thất bại. Nếu pháp lý yêu cầu số chứng từ liên tục, cần một quy trình cấp số chuyên biệt, có chính sách hủy/void.

## 12. Hỗ trợ multi-tenancy và namespace ID

Một hệ thống có thể dùng:

- Database riêng cho từng tenant.
- Schema riêng cho từng tenant.
- Shared schema có cột `tenant_id`.
- Hybrid routing hoặc sharding.

Generator phải hiểu **phạm vi duy nhất** của ID.

| Mô hình | Phạm vi PK | Điều cần chú ý |
| --- | --- | --- |
| Một database chung | Thường global trong bảng | DB PK bảo vệ uniqueness |
| Schema per tenant | PK có thể trùng giữa schemas | Khi gộp dữ liệu phải thêm tenant context |
| Shared schema | PK toàn cục hoặc composite `(tenant_id, id)` | Mapping và FK phải đồng nhất |
| Nhiều shard | Mỗi shard có allocator riêng | Tránh collision khi merge hoặc di chuyển |
| Offline client ID | Client có thể phát sinh ID | Validation và conflict handling ở server |

Nếu muốn prefix tenant vào ID, không lấy tenant từ field user-controlled thiếu kiểm tra. Sử dụng tenant context do authentication/routing tin cậy cung cấp theo API của phiên bản tương ứng, và không thiết kế logic phụ thuộc thread-local tùy tiện nếu chạy async.

### ID không phải authorization

Biết một ID của tenant A không cho phép đọc/sửa record của A từ tenant B. Repository/query vẫn phải enforce tenant và permission.

### Tránh gọi HTTP để cấp ID trong generator

Gọi service phát ID qua mạng ngay trong `generate` có thể:

- Chặn thread flush/persist.
- Kéo dài transaction.
- Thêm failure mode/timeout.
- Dễ phát ID trùng khi retry không idempotent.
- Tạo coupling giữa ORM và external service.

Nếu business bắt buộc dùng remote allocator, cân nhắc cấp ID ở application boundary trước khi persist, dùng idempotent API và quản lý retries rõ. Không đưa toàn bộ quy trình phân tán vào một SPI callback khó quan sát.

## 13. `@ValueGenerationType` cho thuộc tính không phải ID

Một non-ID field có thể được sinh tự động khi ORM INSERT hoặc UPDATE. Hibernate dùng:

```java
@ValueGenerationType(generatedBy = SomeGenerator.class)
```

để khai báo meta-annotation cho các value generators.

Ví dụ: `AuditEvent` cần mã correlation có dạng `EVT_` + UUID hex, sinh một lần khi INSERT.

### 13.1. Annotation

```java
package com.example.audit;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.hibernate.annotations.ValueGenerationType;

@ValueGenerationType(generatedBy = CorrelationCodeGenerator.class)
@Target({ElementType.FIELD, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
public @interface GeneratedCorrelationCode {
    String prefix() default "EVT_";
}
```

### 13.2. Generator

```java
package com.example.audit;

import java.lang.reflect.Member;
import java.util.EnumSet;
import java.util.UUID;

import org.hibernate.engine.spi.SharedSessionContractImplementor;
import org.hibernate.generator.BeforeExecutionGenerator;
import org.hibernate.generator.EventType;
import org.hibernate.generator.EventTypeSets;
import org.hibernate.generator.GeneratorCreationContext;

public final class CorrelationCodeGenerator
        implements BeforeExecutionGenerator {

    private final String prefix;

    public CorrelationCodeGenerator(
            GeneratedCorrelationCode annotation,
            Member member,
            GeneratorCreationContext context) {

        String candidate = annotation.prefix();

        if (!candidate.matches("[A-Z]{2,8}_")) {
            throw new IllegalArgumentException(
                "Invalid code prefix"
            );
        }

        this.prefix = candidate;
    }

    @Override
    public EnumSet<EventType> getEventTypes() {
        return EventTypeSets.INSERT_ONLY;
    }

    @Override
    public Object generate(
            SharedSessionContractImplementor session,
            Object owner,
            Object currentValue,
            EventType eventType) {

        return prefix +
            UUID.randomUUID().toString().replace("-", "");
    }
}
```

### 13.3. Entity mapping

```java
@Entity
@Table(
    name = "audit_events",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_audit_event_code",
        columnNames = "correlation_code"
    )
)
public class AuditEvent {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @GeneratedCorrelationCode(prefix = "EVT_")
    @Column(
        name = "correlation_code",
        nullable = false,
        updatable = false,
        length = 48
    )
    private String correlationCode;

    @Column(nullable = false)
    private String action;

    protected AuditEvent() {}

    public AuditEvent(String action) {
        this.action = action;
    }

    public String getCorrelationCode() {
        return correlationCode;
    }
}
```

Các imports của `jakarta.persistence.*` cần thêm ở file entity tương ứng.

Ở đây có **hai** generator độc lập:

- ID numeric do database identity tạo theo `@GeneratedValue`.
- `correlationCode` string do custom value generator Java sinh trước INSERT.

Hai generator không cần dùng cùng chiến lược và không có lý do biến correlation code thành PK.

### 13.4. Contract của generated property

`correlationCode` là value do framework sinh ở INSERT, không được application tự set tùy tiện nếu mapping không hỗ trợ assigned value. Nếu nghiệp vụ cần import một mã đã có, phải thiết kế riêng import path và API/SPI hỗ trợ assigned value đúng nghĩa; không dựa vào việc gán field trước persist rồi hy vọng generator “thấy có thì bỏ qua” trong mọi case.

## 14. Sinh giá trị cho UPDATE

Nếu field cần tái sinh khi entity được UPDATE, generator khai báo:

```java
@Override
public EnumSet<EventType> getEventTypes() {
    return EventTypeSets.INSERT_AND_UPDATE;
}
```

Ví dụ minh họa generator tạo dấu thời gian tại JVM:

```java
public final class VmTouchGenerator
        implements BeforeExecutionGenerator {

    @Override
    public EnumSet<EventType> getEventTypes() {
        return EventTypeSets.INSERT_AND_UPDATE;
    }

    @Override
    public Object generate(
            SharedSessionContractImplementor session,
            Object owner,
            Object currentValue,
            EventType eventType) {

        return Instant.now();
    }
}
```

Để gắn generator, khai báo custom annotation:

```java
@ValueGenerationType(generatedBy = VmTouchGenerator.class)
@Target({ElementType.FIELD, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
public @interface GeneratedTouchTime {
}
```

Áp dụng:

```java
@GeneratedTouchTime
@Column(name = "touched_at")
private Instant touchedAt;
```

Imports cần thiết gồm `java.time.Instant`, `java.util.EnumSet`, annotations Java và các kiểu SPI ở ví dụ trước. `VmTouchGenerator` có no-arg constructor mặc định vì annotation không truyền configuration.

**Ví dụ chỉ minh họa SPI:** với thời điểm tạo/cập nhật thông thường, Hibernate `@CreationTimestamp` và `@UpdateTimestamp` phù hợp hơn.

### UPDATE event chỉ xuất hiện khi có UPDATE

Một entity không dirty không nhất thiết khiến Hibernate phát SQL UPDATE chỉ vì đã đọc hoặc gọi `flush()`. Generator UPDATE không phải đồng hồ tự chạy mỗi request.

Bulk HQL/JPQL/native SQL cũng có thể không đi qua entity lifecycle generator của từng entity. Nếu yêu cầu mọi database UPDATE bất kể nguồn đều đổi timestamp, database trigger hoặc generated column có thể phù hợp hơn.

## 15. Value generator không thay thế domain invariants

Không phải bất kỳ thuộc tính nào cũng nên sinh tại flush time.

Ví dụ một mã giảm giá phải:

- Được kiểm tra với hạn mức.
- Có thể do người dùng nhập.
- Được reserve trước khi thanh toán.
- Phải giữ nguyên qua retry.
- Chỉ phát hành sau khi đáp ứng một điều kiện nghiệp vụ.

Đây có thể là trách nhiệm của **application/domain service** chứ không phải generic persistence generator.

Các dấu hiệu nên đưa logic ra ngoài SPI:

- Cần gọi network API.
- Cần phối hợp nhiều aggregates.
- Cần kiểm soát thứ tự nghiệp vụ rõ.
- Cần user identity, authorization hoặc request payload.
- Cần idempotency key từ bên ngoài.
- Cần nâng/hủy một trạng thái theo workflow.
- Giá trị cần biết trước thời điểm thực hiện persistence.

Generator phù hợp hơn cho **giá trị được xác định bởi chính thao tác persistence**, ít phụ thuộc hệ thống bên ngoài và có thể kiểm thử độc lập.

## 16. Sinh trước SQL khác sinh trong database

Đây là khác biệt quan trọng nhất giữa hai nhánh Generator SPI.

| Thuộc tính | `BeforeExecutionGenerator` | `OnExecutionGenerator` |
| --- | --- | --- |
| Nơi sinh | Trong Java trước SQL (có thể hỏi DB) | Trong database khi SQL chạy |
| Cách truyền giá trị | Hibernate có thể bind qua JDBC parameter | Cột được omit/default hoặc SQL expression/trigger |
| Cần lấy giá trị DB sau SQL? | Thường không cho chính giá trị đã trả | Thường cần hoặc dùng generated keys/RETURNING |
| Ví dụ | UUID, code, JVM timestamp, sequence ID đã xin trước | Identity, DB default, trigger, generated column |
| Điều quan trọng | Uniqueness, thread safety, event timing | SQL generation, dialect, retrieval strategy |
| Custom implementation | Thường tương đối đơn giản | Phức tạp hơn, phụ thuộc database/provider |

`BeforeExecutionGenerator` không đồng nghĩa “không chạm database”. Nó có thể dùng DB sequence để lấy ID trước INSERT. Nhưng không vì vậy mà application được tự commit/close connection hoặc tạo transaction độc lập.

`OnExecutionGenerator` không đồng nghĩa “sinh sau commit”. Giá trị được tạo như một phần SQL INSERT/UPDATE; nó có thể tồn tại trong transaction chưa commit và bị rollback nếu transaction thất bại.

## 17. Dùng `@Generated` khi database tạo giá trị

Giả sử cột `created_at` có DDL default:

```sql
CREATE TABLE external_receipts (
    id BIGINT PRIMARY KEY,
    receipt_code VARCHAR(64) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);
```

Có thể mapping:

```java
@Entity
@Table(name = "external_receipts")
public class ExternalReceipt {

    @Id
    private Long id;

    private String receiptCode;

    @org.hibernate.annotations.Generated(
        event = org.hibernate.generator.EventType.INSERT
    )
    @Column(
        name = "created_at",
        insertable = false,
        updatable = false
    )
    private LocalDateTime createdAt;
}
```

Hibernate biết `createdAt` được DB tạo khi INSERT và có thể đọc giá trị về theo khả năng dialect/driver. Chi tiết việc dùng SELECT bổ sung, RETURNING hoặc các chiến lược retrieval khác phụ thuộc version và DBMS.

**Không viết một custom OnExecutionGenerator chỉ để mô tả một cột default đơn giản** khi `@Generated` đã đủ.

### Nếu DB trigger tạo lại giá trị khi UPDATE

```java
@Generated(
    event = {
        EventType.INSERT,
        EventType.UPDATE
    }
)
@Column(name = "modified_at", insertable = false, updatable = false)
private Instant modifiedAt;
```

Đây là cách khai báo thời điểm giá trị được database sinh, **không tự tạo trigger**. Phải có DDL/trigger thực tế và kiểm tra transaction/precision/timezone.

### Cột computed/generated

Nếu DB hỗ trợ `GENERATED ALWAYS AS`, Hibernate có `@GeneratedColumn` trong phiên bản phù hợp để mô tả generated column. Ưu tiên API sẵn có trước khi viết SQL expression generator riêng.

## 18. `OnExecutionGenerator` phải phối hợp với SQL writer

Một custom implementation của `OnExecutionGenerator` có thể cần khai báo:

```java
boolean referenceColumnsInSql(Dialect dialect);

boolean writePropertyValue();

String[] getReferencedColumnValues(Dialect dialect);
```

Đây là **các phương thức SPI tiêu biểu** của Hibernate 6.2–6.6. Chúng nói cho Hibernate biết:

- Có đưa cột được sinh vào `INSERT/UPDATE` hay không.
- Có bind giá trị hiện tại bằng dấu `?` hay không.
- Nếu đưa cột vào SQL, expression nào được dùng, ví dụ `current_timestamp` hay marker `default`.

Ví dụ ngữ nghĩa:

```text
DB default:
  INSERT INTO table(other_field) VALUES (?)
  -> Không cần đưa generated column vào SQL.

DB expression:
  INSERT INTO table(created_at, other_field)
  VALUES (current_timestamp, ?)
  -> Cột có mặt trong SQL, nhưng expression do DB tính.

Writable generated:
  SQL có thể chứa '?' cho giá trị Java
  -> DB trigger/column transformer biến đổi rồi trả giá trị thật.
```

**Không đưa raw user input vào SQL expression của generator.** SQL fragment phải do code/config tin cậy chọn, có xử lý dialect phù hợp.

### Vì sao không tự trình bày một OnExecutionGenerator “chỉ 5 dòng”?

Một custom OnExecutionGenerator muốn hoạt động đúng còn phụ thuộc:

- Mapping của generated column.
- Identifier vs non-ID.
- SQL dialect.
- Cách provider lấy generated values (`RETURNING`, `getGeneratedKeys`, SELECT bổ sung).
- INSERT/UPDATE event.
- Trigger/default behavior.
- Multi-table entity mappings.

Nếu use case chỉ cần default/trigger, `@Generated` là điểm bắt đầu an toàn và dễ kiểm thử hơn.

## 19. Mối quan hệ với `IdentifierGenerator` truyền thống

Hibernate có extension point lâu đời:

```java
org.hibernate.id.IdentifierGenerator
```

Trong Hibernate 6.x, `IdentifierGenerator` mở rộng/đi cùng mô hình `BeforeExecutionGenerator` và tiếp tục được hỗ trợ cho code cũ. Các generator nội bộ như sequence/table cũng có lịch sử dựa trên interface này.

Một ví dụ kiểu truyền thống:

```java
public final class LegacyStringIdGenerator
        implements IdentifierGenerator {

    @Override
    public Object generate(
            SharedSessionContractImplementor session,
            Object owner) {

        return "LEG_" +
            UUID.randomUUID().toString().replace("-", "");
    }
}
```

Trong code thật cần import interface và session type từ đúng Hibernate version, cùng lifecycle/configuration nếu generator cần tham số.

### Cách gắn bằng `@GenericGenerator`

Ở những dự án legacy có thể gặp:

```java
@GenericGenerator(
    name = "legacy-id",
    strategy = "com.example.LegacyStringIdGenerator"
)
@Id
@GeneratedValue(generator = "legacy-id")
private String id;
```

Đây là **cú pháp dành cho migration/đọc hiểu code cũ**. Tham số `strategy` dạng String đã bị deprecated ở Hibernate 6.2; `@GenericGenerator` bị deprecated từ Hibernate 6.5, với khuyến nghị dùng `@IdGeneratorType`.

Nếu dự án còn Hibernate 5.x, code cũ có thể là contract đúng của version đó. Không xóa nó chỉ vì bài viết dùng SPI mới; lập kế hoạch nâng version và integration test trước.

## 20. So sánh các thế hệ API

| Phiên bản/nhóm | Extension point thường thấy | Cách cấu hình | Ghi chú |
| --- | --- | --- | --- |
| Hibernate 5.x | `IdentifierGenerator`, `@GenericGenerator` | Tên/strategy/parameters | Phù hợp code legacy |
| Hibernate 6.0–6.1 | `@IdGeneratorType` đã xuất hiện; các kiểu SPI còn phát triển | Custom annotation | Kiểm tra chính xác Javadocs phiên bản |
| Hibernate 6.2–6.4 | `Generator`, `BeforeExecutionGenerator`, `OnExecutionGenerator` | `@IdGeneratorType`, `@ValueGenerationType` | Hướng mở rộng hiện đại |
| Hibernate 6.5–6.6 | SPI hiện đại; `@GenericGenerator` deprecated | Custom annotation type-safe | Đường ưu tiên cho dự án mới |
| Hibernate 7.x | Generator SPI tiếp tục được tài liệu hóa | Theo Javadocs 7.x | Kiểm tra thay đổi minor/patch |

Không viết một class vừa trộn API `org.hibernate.tuple.ValueGenerator` cũ, `GenerationTime` cũ và `Generator` mới rồi kỳ vọng compiler/ORM tự hiểu thời điểm sinh.

Các API đời cũ có thể tồn tại để tương thích, nhưng code mới nên chọn một contract thích hợp với version mục tiêu.

## 21. Không nên nhầm `@GeneratorType` cũ với `@ValueGenerationType`

Trong một số ví dụ trên mạng, bạn có thể thấy:

```java
@GeneratorType(...)
```

được dùng cho thuộc tính non-ID.

Cơ chế này đã bị deprecated trong các phiên bản Hibernate mới. Hướng hiện đại là:

```java
@ValueGenerationType(generatedBy = MyGenerator.class)
```

với một implementation `BeforeExecutionGenerator` hoặc `OnExecutionGenerator`.

Đừng dựa vào đoạn blog cũ mà không đọc release/Javadocs của Hibernate version đang dùng.

## 22. Vì sao không dùng `@PrePersist` để thay thế mọi generator?

Một entity có thể khai báo:

```java
@PrePersist
void beforeInsert() {
    if (externalCode == null) {
        externalCode = "CODE_" + UUID.randomUUID();
    }
}
```

JPA lifecycle callbacks hữu ích cho một số giá trị nội bộ, nhưng **không tương đương với Identifier Generator SPI**.

| Cơ chế | Mục đích |
| --- | --- |
| `@PrePersist` / `@PreUpdate` | Callback vòng đời entity |
| `BeforeExecutionGenerator` | Tạo field value tương ứng SQL INSERT/UPDATE |
| `@IdGeneratorType` | Gắn contract custom identifier generator |
| `@ValueGenerationType` | Gắn contract custom property generator |
| Hibernate event listener | Hook những sự kiện ORM rộng hơn |
| Domain service | Điều phối rule nghiệp vụ và transactions |

Một identifier được Hibernate quản lý có thể cần có giá trị trong những giai đoạn riêng của persistence lifecycle. Việc cố tạo ID trong callback/constructor có thể tương tác khác với unsaved-value detection, cascade, merge hoặc flush.

Nếu mục đích là custom generated primary key, **sử dụng `@IdGeneratorType` hoặc chiến lược ID có sẵn**.

Nếu mục đích chỉ là field đơn giản trong một entity mà không cần tái sử dụng/integration đặc biệt, domain method/`@PrePersist` có thể đủ; không ép mọi logic vào Generator SPI.

## 23. Khi nào dùng Hibernate event listener thay vì generator?

Ở chương *Sự kiện và mở rộng*, hai loại SPI thường bị đánh đồng.

- Generator: sinh một giá trị của một mapped attribute.
- Listener/Interceptor: quan sát hoặc can thiệp một lifecycle event rộng hơn, có thể liên quan nhiều properties/entities.

Ví dụ:

- Muốn một ID string mới → generator.
- Muốn `createdAt` → built-in timestamp.
- Muốn xác thực một rule nghiệp vụ phức tạp trước chuyển trạng thái → domain/application layer.
- Muốn ghi audit toàn hệ thống → audit framework/Envers/event architecture phù hợp.
- Muốn tạo nhiều rows nghiệp vụ khác sau update → service transaction hoặc outbox, không nhồi vào generator.

**Một generator không phải transaction orchestrator.** Đừng gọi một loạt `persist()` khác, gửi email hoặc publish Kafka từ `generate(...)`; nó có thể được gọi trước SQL/commit, bị retry hoặc không đồng bộ với business boundary.

## 24. Không tự commit, rollback hoặc close JDBC Connection trong generator

`BeforeExecutionGenerator.generate(...)` nhận Hibernate Session/SharedSessionContract. Dù SPI cho phép thực hiện Java code phức tạp và có thể truy cập database trong những trường hợp được hỗ trợ, generator **không có quyền sở hữu transaction/connection lifecycle**.

Sai:

```java
Connection connection = ...;
connection.commit(); // Không được chiếm transaction của Hibernate.
connection.close();  // Không được tự đóng managed connection.
```

Điều đúng:

- Dùng API Hibernate/sequence generator có sẵn nếu cần sequence.
- Để transaction manager xử lý commit/rollback.
- Nếu phải dùng JDBC qua một API được hỗ trợ, chỉ đóng Statement/ResultSet do mình tạo.
- Không tạo một transaction độc lập để cấp ID khi thao tác entity dự kiến atomic với transaction hiện tại, trừ khi kiến trúc allocator được thiết kế riêng với semantics rõ.
- Không giữ Connection/Session trong field của generator.

### Đừng dựa vào transaction luôn tồn tại

Cơ chế ID generation có thể được Hibernate kích hoạt ở thời điểm khác nhau tùy strategy; nếu code generator chạy query DB, phải hiểu transaction coordinator và dialect. Không tự mở/commit một transaction để “bảo đảm có ID” khi chưa xét Hibernate lifecycle.

## 25. Generator không được gây N+1 tùy tiện

Giả sử một batch insert 10.000 entities. Nếu mỗi lần `generate(...)` gọi:

```sql
SELECT next_value FROM custom_counter WHERE name = ?;
UPDATE custom_counter SET next_value = ...;
```

bằng hai round trips riêng, throughput có thể giảm mạnh, lock contention tăng và deadlock xuất hiện.

Database sequence với allocation optimizer thường hiệu quả hơn tự viết khóa bảng cấp số.

Nếu custom generator cần DB access, hãy đo:

- Số round trips mỗi generated value.
- Lock waiting.
- Sequence cache/allocation size.
- Tác động JDBC batch.
- Throughput nhiều threads/nodes.
- Rollback/retry cost.
- Timeouts và deadlocks.
- Recovery sau crash.

Một generator chạy đúng với 100 records trong local test chưa chắc phù hợp production throughput.

## 26. `allocationSize`, sequence optimizer và tính duy nhất

Hibernate có thể dùng pooled sequence optimizer để cấp trước một dải identifiers.

```java
@SequenceGenerator(
    name = "orderSeq",
    sequenceName = "order_sequence",
    allocationSize = 50
)
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "orderSeq"
)
private Long id;
```

Các điểm cần hiểu:

- Sequence thực tế phải được cấu hình phù hợp optimizer/increment semantics.
- Nếu nhiều writers ngoài Hibernate cùng dùng sequence, phải tuân theo cùng contract.
- Allocation có thể tạo gaps khi rollback/crash.
- Điều chỉnh `allocationSize` không phải chỉ là một thay đổi Java vô hại nếu DB sequence increment khác.
- Trên nhiều instance, sequence provider phối hợp cấp giá trị duy nhất; biến local counter thì không.

Nếu nghiệp vụ cần dạng ID custom nhưng nguồn vẫn là sequence, nên tái sử dụng generator/optimizer Hibernate thay vì tự triển khai vòng lặp nextval.

## 27. Database-generated ID vs before-generated ID

### Before-generated ID

Ví dụ custom SalesId Generator:

```text
Hibernate biết ID trước INSERT
    -> bind ID vào INSERT
    -> database ràng buộc PRIMARY KEY
```

Lợi điểm: ID có thể sẵn sàng để quản lý associations trước SQL insert theo chiến lược cụ thể.

### Identity-generated ID

```text
Hibernate thực hiện INSERT
    -> database cấp ID
    -> Hibernate đọc generated key
    -> cập nhật entity identifier
```

Không thể giả định mọi generator có ID trước INSERT. Nếu code cần ID để build một message, hãy hoàn thành thao tác persistence và thiết kế after-commit/outbox phù hợp, không dựa vào gọi `persist()` luôn trả ID ngay trong mọi strategy.

## 28. ID của entity phải ổn định qua UPDATE

Một identifier generator bắt buộc đáp ứng INSERT-only trong Generator SPI:

```java
@Override
public EnumSet<EventType> getEventTypes() {
    return EventTypeSets.INSERT_ONLY;
}
```

Không viết generator ID dùng `INSERT_AND_UPDATE` để “làm mới ID khi entity thay đổi”.

Hậu quả đổi ID:

- Foreign keys trỏ sang ID cũ.
- Identity map trong Persistence Context không còn đúng.
- L2 cache và associations theo ID bị phá.
- Equality/hashCode dựa vào ID mất ổn định.
- Business events/references dùng ID cũ không còn tìm được entity.

Nếu một mã hiển thị cần thay đổi, hãy mô hình hóa thành **một property khác với unique constraint phù hợp**. Không đổi primary key sau khi entity đã persistent.

## 29. Gán ID bằng application và custom generated ID không giống nhau

Có các kiểu:

- Assigned ID: application đưa giá trị trước khi gọi persist.
- Before-execution generated ID: Hibernate generator tạo giá trị.
- On-execution ID: DB tạo giá trị khi INSERT.

Ví dụ assigned UUID:

```java
@Entity
public class ExternalImport {

    @Id
    private UUID id;

    protected ExternalImport() {}

    public ExternalImport(UUID id) {
        this.id = Objects.requireNonNull(id);
    }
}
```

Ở đây application/import process chịu trách nhiệm cấp ID. Không nên đồng thời gắn `@GeneratedValue` hoặc `@SalesId` lên cùng field nếu policy là caller-assigned.

Hibernate Generator SPI có những khả năng hỗ trợ nhận assigned ID trong một số trường hợp/version, nhưng phải hiểu `allowAssignedIdentifiers()`, unsaved-value, detached/merge semantics và unit tests tương ứng. Không tự tạo hybrid “có ID thì giữ, null thì sinh” mà không chọn rõ contract.

## 30. Custom generator và `currentValue`

`BeforeExecutionGenerator.generate(...)` nhận `currentValue`. Nó có thể là null hoặc giá trị hiện tại của property, tùy event/mapping.

Đừng mặc định:

```java
if (currentValue != null) {
    return currentValue;
}
```

luôn là chính sách đúng.

Các trường hợp khác nhau:

- ID luôn do generator quản lý: assigned value có thể cần bị từ chối.
- Correlation code sinh một lần: trước INSERT nếu field có giá trị do caller điền, policy phải rõ.
- Update timestamp: phải **thay** giá trị cũ khi có UPDATE.
- Immutable external reference: có thể cần giữ giá trị ban đầu.
- Import legacy: có thể cần một đường riêng để giữ ID lịch sử.

Phân biệt policy của domain với mặc định của generator; test các trường hợp field null/nonnull được truyền vào persist/merge.

## 31. `@Version` là một trường hợp đặc biệt

Hibernate quản lý optimistic locking bằng `@Version`.

```java
@Version
private long version;
```

Không nên dùng custom value generator để ghi ngẫu nhiên một giá trị version mỗi lần entity update khi chưa hiểu Hibernate version protocol.

Version phải phục vụ phát hiện thay đổi đồng thời. Một custom version generator nếu được cấu hình phải sinh đúng theo INSERT và UPDATE, tuân theo contract của Hibernate và DB, đồng thời không làm mất optimistic locking.

Nếu chỉ cần numeric increment thông thường, **dùng @Version sẵn có**. Nếu cần timestamp versioning hoặc DB trigger, kiểm tra các APIs đã được Hibernate hỗ trợ và integration test concurrent updates.

### Version khác ID và business version

- `@Id`: identity bất biến.
- `@Version`: optimistic lock state.
- `schemaVersion` hoặc `payloadVersion`: định dạng dữ liệu/payload.

Không đưa một generator vào cả ba mục đích chỉ vì các trường đều có tên “version”.

## 32. Generated value và SQL triggers

Một DB trigger có thể cập nhật `updated_at` hoặc tạo `receipt_code`.

Nếu mapping Hibernate không được khai báo rằng cột do DB sinh, object trong Session có thể giữ giá trị cũ/null sau INSERT/UPDATE.

`@Generated` giúp thông báo cho Hibernate về giá trị do DB tạo, theo những events được chỉ định.

Nhưng:

- Trigger phải thật sự tồn tại trong schema.
- Trigger phải phát sinh đúng ở INSERT/UPDATE dự kiến.
- Hibernate phải có cách retrieve giá trị do DB tạo.
- Nếu trigger đổi ID, điều đó có những yêu cầu đặc thù về generated key handling.
- Nếu external SQL updates trigger, entity đang managed trong một Session khác vẫn có thể stale.
- Query cache/L2 cache có thể cần invalidation phù hợp.

**Custom OnExecutionGenerator không tự tạo trigger hoặc bảo đảm database đã được migrate đúng.**

## 33. Dùng `@CurrentTimestamp` khi cần nguồn thời gian rõ

Hibernate 6 có annotation:

```java
@CurrentTimestamp(source = SourceType.VM)
private Instant touchedAt;
```

hoặc:

```java
@CurrentTimestamp(source = SourceType.DB)
private Instant touchedAt;
```

Nguồn VM và DB có đánh đổi:

| Nguồn | Ưu điểm | Điểm cần lưu ý |
| --- | --- | --- |
| JVM clock | Có thể tránh DB round trip và đơn giản khi generate | Lệch giờ giữa nodes; không là nguồn timestamp tuyệt đối |
| Database clock | Đồng nhất theo DB primary trong nhiều trường hợp | Chi phí đọc lại, DB-specific precision/timezone |
| Trường truyền từ domain | Dễ test bằng `Clock`, mang semantics nghiệp vụ | Không phải timestamp của SQL execution |
| External time source | Có thể đáp ứng một số compliance requirement | Network failure, latency, protocol |

Nếu mục đích là **thời điểm nghiệp vụ phát sinh**, có thể nên ghi ở application boundary qua `Clock` được inject thay vì chỉ đánh dấu thời điểm INSERT/UPDATE của ORM.

## 34. Tránh dùng custom ID như business sequence liên tục

Ví dụ yêu cầu:

> Mỗi hóa đơn có số “INV-2026-000001”, không trùng, được cấp theo từng chi nhánh, có thể rollback và không có lỗ hổng.

Đó không chỉ là format ID. Phải trả lời:

- Số cấp khi tạo draft hay khi phát hành?
- Khi rollback có thu hồi số không?
- Khi hủy hóa đơn có giữ “voided number” không?
- Có hai máy phát hành cùng chi nhánh không?
- Số theo năm trên timezone nào?
- Có nhân rộng/sharding không?
- Yêu cầu audit và pháp lý địa phương là gì?

Cách thực tế thường là:

- PK surrogate ổn định, ví dụ UUID/sequence.
- Một bảng allocator/sequence hoặc service phát hành số riêng theo tenant/chi nhánh/kỳ.
- Unique constraint đúng phạm vi.
- Transaction và idempotency.
- Audit trail của số đã cấp/hủy.

Không cố giải tất cả bằng `generate(...)` chạy trong một callback mà không có business context.

## 35. Transaction, rollback và generator side effects

Một transaction:

```java
@Transactional
public void createSale() {
    SalesDocument doc = new SalesDocument("Sale");
    em.persist(doc);

    chargeInventory(doc);

    // Transaction có thể rollback nếu chargeInventory thất bại.
}
```

ID có thể đã được generator tạo ngay cả khi transaction cuối cùng rollback.

Điều này có nghĩa:

- **ID được sinh** không chứng minh entity đã được commit.
- Sequence value có thể đã tiêu thụ mà rollback không hoàn lại.
- Một log/message chứa ID chưa chắc trỏ tới row tồn tại.
- Không publish event ra Kafka hoặc gửi email trong generator.
- Nếu need publish after commit, dùng transaction event/outbox.
- Retry một transaction có thể sinh ID mới; liên kết request idempotency là một vấn đề riêng.

### Khi cần ID ổn định qua retry

Nếu HTTP client retry cùng yêu cầu tạo đơn, nên dùng idempotency key do caller/application sinh và enforce uniqueness, có thể lưu cùng request fingerprint. Không dựa chỉ vào việc custom generator cấp ID nhanh.

## 36. Side effects trong generator có thể chạy nhiều lần?

Không nên xây nghiệp vụ dựa trên “generate chắc chắn chỉ gọi đúng một lần trên mọi code path”.

Các lý do cần thận trọng:

- Persistence operations có thể bị retry ở application level.
- Transaction có thể rollback sau khi ID đã được tạo.
- Một import tool hoặc batch process có thể gọi mã mapping theo cách khác.
- Reattachment/merge có lifecycle riêng.
- Flush có thể chạy trước thời điểm caller dự đoán.
- Cấu hình/version generator có thể có tối ưu hóa khác nhau.

Vì vậy generator nên **không có side effects ngoài việc tạo giá trị** hoặc chỉ có side effects được thiết kế, transactionally safe/idempotent theo contract rõ.

Không gửi HTTP request, ghi audit ngoại vi, cập nhật counters trong memory làm source of truth hoặc phát domain event trong `generate`.

## 37. Thread safety và lifecycle của generator

Hibernate có thể tạo generator khi xây metadata/SessionFactory và sử dụng qua nhiều persistence operations. Đừng giả định có **một generator instance mới cho từng entity**.

Thiết kế tốt:

- Trường cấu hình bất biến, ví dụ `private final String prefix`.
- Các đối tượng helper thread-safe.
- Không lưu `currentEntity`, `currentSession` hoặc transaction state trong fields.
- Không dùng shared mutable counter.
- Không ghi state thay đổi theo từng invocation vào generator instance.
- Không cache JDBC Connection trong generator.
- Không tạo static cache map không giới hạn theo tenant.

Ví dụ:

```java
private final String prefix;

@Override
public Object generate(...) {
    return prefix + UUID.randomUUID();
}
```

an toàn hơn một generator có `StringBuilder` instance chung bị nhiều threads append.

Nếu generator dùng một random algorithm hoặc allocator cần thread safety, chọn thư viện đã công bố guarantees và test concurrency.

## 38. Validate configuration từ lúc bootstrap

Custom annotation có thể có các thông số:

```java
@SalesId(prefix = "SO_")
private String id;
```

Generator constructor nên kiểm tra những bất biến của cấu hình, ví dụ:

- Prefix có hợp lệ không?
- Result type có tương thích field không?
- Max length có phù hợp với DB column không?
- Strategy có hỗ trợ DB dialect không?
- Sequence/table name có hợp lệ không?
- Tham số allocation có dương không?
- EventType có đúng cho ID/value không?

Không đợi tới khi request thứ 1 triệu chạy vào một nhánh hiếm gặp mới ném lỗi “invalid prefix”.

### Giữ cấu hình an toàn

Không nhận raw table/sequence name từ input của mỗi request rồi nối vào SQL. Các identifier SQL không bind được như JDBC values; nếu phải cấu hình động, chỉ chấp nhận whitelist trusted schema identifiers hoặc sử dụng APIs Dialect/metadata phù hợp.

## 39. Chiến lược lỗi: nên fail fast

Nếu generator không thể tạo ID, Hibernate không thể persist entity đúng yêu cầu.

Ví dụ sai:

```java
try {
    return externalAllocator.nextId();
} catch (Exception ex) {
    return "UNKNOWN";
}
```

Một fallback ID cố định sẽ tạo duplicate và có thể gây lỗi sâu hơn.

Đúng hơn:

- Ném exception có thông tin kỹ thuật phù hợp.
- Để transaction rollback theo policy.
- Không nuốt lỗi chỉ để INSERT một giá trị giả.
- Nếu cần retry, retry unit of work ở boundary ngoài.
- Phân biệt lỗi tạm thời (timeout/sequence unavailable) với lỗi cấu hình (invalid mapping).

Không log secret/user data trong exception message.

## 40. Định dạng ID và schema migration

Khi thay từ `BIGINT IDENTITY` sang String custom IDs:

- Foreign key tables có thể đang dùng BIGINT.
- API clients có thể giả định ID là số.
- Cache keys và message payloads có thể phụ thuộc ID cũ.
- Existing entities đã có ID không được đổi tùy tiện.
- ORM associations và indexes cần migration.
- Dữ liệu replication/backup có thể chứa format cũ.

Không chỉ sửa:

```java
private Long id;
```

thành:

```java
private String id;
```

và thêm custom generator trong một release rolling mà không có migration plan.

Một hướng ít rủi ro hơn có thể là giữ PK hiện tại, thêm một publicReferenceCode (unique) được sinh mới. Nếu cần đổi PK thực, đó là migration lược đồ/dữ liệu lớn, không chỉ bài toán SPI.

## 41. Mapping access type và vị trí annotation

Nếu `@Id` được đặt trên field, JPA thường dùng field access cho entity:

```java
@Id
@SalesId
private String id;
```

Nếu `@Id` đặt trên getter, access type có thể là property access:

```java
@Id
@SalesId
public String getId() {
    return id;
}
```

Đừng đặt `@Id` ở getter còn `@SalesId` ở field rồi giả định Hibernate tự kết hợp cả hai trong mọi mapping. Hãy đặt generator annotation nhất quán với access type và kiểm tra metadata bootstrap.

## 42. Không gắn nhiều generator annotations trên cùng thuộc tính

Ví dụ không nên:

```java
@Id
@GeneratedValue(strategy = GenerationType.UUID)
@SalesId
private String id;
```

Vì cả hai đang cố kiểm soát một ID.

Tương tự, không gắn hai `@ValueGenerationType`-based annotations trên một thuộc tính rồi kỳ vọng chúng tạo thành pipeline hai bước. Hibernate công bố constraint không nhiều hơn một generator annotation trên một property.

Chọn **một owner** cho generation semantics; nếu cần combine logic, đóng gói trong một generator được thiết kế rõ.

## 43. Đồng bộ giá trị được sinh với entity state

Với before-execution generator, giá trị Java được trả về để Hibernate đưa vào persistence state.

Với on-execution generator, DB sinh giá trị rồi Hibernate có thể phải đọc lại từ DB để state của entity phản ánh nó.

Trong cả hai trường hợp:

- Giá trị trước commit chưa đồng nghĩa dữ liệu đã bền vững.
- Một bulk/native SQL update ngoài ORM có thể không gọi generator.
- Một entity đã detached không tự cập nhật khi DB trigger chạy ở transaction khác.
- Cần refresh/new Session khi muốn đọc thay đổi ngoại vi.
- L2/query cache có thể cần invalidation nếu external writer thay dữ liệu.

### Không sửa generated fields thủ công trong business code

```java
entity.setCreatedAt(Instant.now());
```

có thể xung đột generator/database default nếu field đã được cấu hình là generated. Đặt một contract rõ: ai là nguồn có thẩm quyền cho field này?

Nếu business cần cho phép override generated value, phải thiết kế API và mapping cho use case đó thay vì ngẫu nhiên thêm setter.

## 44. DTO không cần chứa toàn bộ chi tiết sinh ID

Trong API, có thể trả:

```java
public record SalesDocumentResponse(
    String id,
    String title
) {}
```

Không cần expose tên generator class, sequence allocation, trạng thái L2 hoặc các chi tiết hạ tầng.

Tuy nhiên, nếu API đã công bố ID là Long, chuyển sang String có thể là breaking change. Định dạng ID là một phần hợp đồng bên ngoài nếu client dùng nó.

Nếu muốn giữ khả năng đổi strategy nội bộ về sau, hạn chế encode business meaning vào primary key, và định nghĩa public reference riêng nếu cần.

## 45. Monitoring generator trong production

Một số metric hữu ích:

```text
id_generation_failures_total{generator="sales-id"}
id_generation_latency_seconds{generator="sales-id"}
id_generation_collision_total{generator="sales-id"}
db_sequence_allocations_total{sequence="sales_doc_seq"}
persist_failures_total{entity="SalesDocument",reason="constraint"}
```

Chỉ dùng labels cardinality thấp, không dùng actual ID hoặc tenant/customer ID tùy ý làm metric label.

Với built-in sequence/identity, sử dụng JDBC/DB metrics phù hợp. Với generator thuần UUID rất nhanh, instrumentation quá nặng có thể tự làm giảm throughput; không cần đo mỗi invocation bằng network request.

### Những dấu hiệu cần điều tra

- Unique constraint violations tăng bất thường.
- P95 transaction latency tăng sau đổi generator.
- Hệ thống chạy nhiều node bắt đầu sinh ID trùng.
- Tốc độ cấp số giảm vì lock contention.
- INSERT batch bị phân tán.
- ID generation phụ thuộc external service bị timeout.
- Mismatch sequence increment/allocationSize sau migration.
- Thay đổi data type ID làm tăng chi phí index.

## 46. Test đơn vị cho generator logic

Đối với một custom Generator dùng UUID random, unit test có thể kiểm tra format, event set và tính bất biến của config.

Ví dụ ý tưởng:

```java
@Test
void generatorUsesOnlyInsertEvent() {
    SalesIdGenerator generator = new SalesIdGenerator(
        salesIdAnnotation("SO_"),
        idMember(),
        creationContext()
    );

    assertEquals(
        EventTypeSets.INSERT_ONLY,
        generator.getEventTypes()
    );
}
```

Các hàm `salesIdAnnotation`, `idMember`, `creationContext` là fixtures của test project; đây là ví dụ về assertion, không phải full JUnit class chạy độc lập.

Nếu muốn test đơn vị gọn hơn, tách logic sinh phần String/validate prefix vào helper thuần Java để test mà không cần mock GeneratorCreationContext.

### Kiểm tra format

```java
String id = generateBusinessId("SO_");

assertTrue(id.matches("SO_[0-9a-f]{32}"));
```

Kiểm tra format chỉ chứng minh representation, **không chứng minh uniqueness toàn hệ thống**.

## 47. Integration test với Hibernate thật

Một test quan trọng hơn là khởi động EntityManagerFactory/SessionFactory và persist thật trên database.

```java
@DataJpaTest
class SalesIdGenerationTest {

    @Autowired
    TestEntityManager testEntityManager;

    @Test
    void persistsWithGeneratedId() {
        SalesDocument doc =
            new SalesDocument("First order");

        testEntityManager.persistAndFlush(doc);

        String id = doc.getId();

        assertNotNull(id);
        assertTrue(id.startsWith("SO_"));

        testEntityManager.clear();

        SalesDocument loaded =
            testEntityManager.find(SalesDocument.class, id);

        assertNotNull(loaded);
        assertEquals("First order", loaded.getTitle());
    }
}
```

Ví dụ Spring Boot test cần đúng test dependencies và entity scanning. `TestEntityManager` của Spring Boot được hỗ trợ trong các stack tương ứng; không phải phần của JPA/Hibernate core.

Điểm quan trọng của test:

1. Generator annotation được Hibernate bootstrap nhận diện.
2. INSERT thành công với ID sinh.
3. ID tồn tại trong DB.
4. Entity có thể tải lại theo ID.
5. SQL/column type và length thực tế khớp mapping.

**Không chạy test trên bài viết STEP 4**; đây là nội dung hướng dẫn cho người học triển khai.

## 48. Test sự kiện INSERT và UPDATE

Với `GeneratedCorrelationCode`:

```text
T1: INSERT AuditEvent -> correlationCode được sinh.
T2: Load lại entity.
T3: UPDATE action.
T4: correlationCode phải giữ nguyên vì INSERT_ONLY.
```

Với `GeneratedTouchTime`:

```text
T1: INSERT entity -> touchedAt có giá trị.
T2: Load lại entity trong Session mới.
T3: Thay đổi field business, flush UPDATE.
T4: touchedAt được sinh lại.
```

Không nên assert timestamp mới **luôn lớn hơn** cũ nếu hai updates diễn ra sát nhau với clock precision hạn chế; có thể dùng Clock có kiểm soát hoặc chờ có chủ đích trong test integration. Với DB-generated timestamp, kiểm tra độ chính xác/precision thực tế của cột và dialect.

## 49. Test uniqueness ở nhiều threads và nhiều nodes

Chạy một test local 1000 IDs khác nhau có ích nhưng không chứng minh toàn bộ correctness của allocator.

Các lớp test cần phân biệt:

- **Unit/property tests:** format, type, null handling.
- **Concurrency tests trong JVM:** nhiều threads gọi generator.
- **Integration tests với database:** PK/unique constraints và transaction rollback.
- **Multi-instance tests:** hai ứng dụng dùng chung DB/allocator.
- **Crash/restart tests:** generator sau restart không lặp dải ID.
- **Rollout tests:** binary cũ/mới cùng ghi nếu cần compatibility.

Đối với UUID random, xác suất collision cực thấp nhưng vẫn cần DB constraint. Đối với numeric allocator tự thiết kế, multi-node và restart tests là bắt buộc.

## 50. Test sequence và transaction rollback

Một kịch bản với sequence:

```text
T1: bắt đầu transaction, persist Order#1, lấy sequence value.
T2: rollback transaction.
T3: transaction mới persist Order#2.
T4: xác nhận ID không trùng và INSERT thành công.
```

Không assert `id2 == id1` hoặc `id2 == id1 + 1`. Sequence/optimizer có thể tiêu thụ số không rollback và tạo gaps. Test đúng là **uniqueness + transactional correctness**, không phải liên tục tuyệt đối.

### Rollback của generated property

Nếu transaction chứa AuditEvent correlation code rollback, Java object có thể vẫn giữ generated code. Nhưng DB row không tồn tại. Không coi chuỗi đã sinh trong RAM là biên lai commit thành công.

## 51. Test database-generated value

Giả sử DB có DEFAULT hoặc trigger cho `createdAt`:

1. Tạo schema migration đúng.
2. Persist entity mà không set `createdAt`.
3. Flush INSERT.
4. Xác nhận Hibernate nhận generated value, hoặc reload trong Session mới.
5. So sánh kết quả với dữ liệu database.
6. Test UPDATE trigger nếu mapping ghi `EventType.UPDATE`.
7. Chạy trên DB engine/version mục tiêu; H2 không đại diện cho mọi cơ chế RETURNING/trigger.

Nếu test thấy field null sau INSERT, kiểm tra annotation, dialect, DDL trigger/default, insertable/updatable flags và transaction/flush timing.

## 52. Hibernate 5 → Hibernate 6/7: chiến lược chuyển đổi

Một codebase lâu năm có thể có:

```java
@GenericGenerator(
    name = "old-code",
    strategy = "com.example.LegacyStringIdGenerator"
)
@GeneratedValue(generator = "old-code")
```

Cách di chuyển có kiểm soát:

1. Xác định chính xác Hibernate 5/6/7 runtime version.
2. Đọc implementation `IdentifierGenerator` hiện có: kết quả, uniqueness, sequence allocation, parameter names.
3. Chốt contract format ID và các ràng buộc DB.
4. Viết custom annotation `@IdGeneratorType` và Generator SPI cho Hibernate version mới.
5. Giữ ID **cũ** đọc được, không đổi PK data type chỉ vì đổi API.
6. Test create/load/update/delete và associations.
7. Test concurrency/multi-instance và rollback.
8. So sánh INSERT batching/SQL/latency.
9. Deploy cùng migration/rollout plan; tránh hai strategies sinh ID trùng trong thời gian mixed-version writers.
10. Chỉ loại API deprecated khi test hoàn tất.

Nếu generator cũ vẫn hoạt động và không cần sửa, có thể để nguyên trong giai đoạn nâng ORM rồi tách việc migrate generator sang một release khác. Không buộc đồng thời nâng Hibernate, đổi DB schema và đổi ID format.

## 53. Một số giới hạn cần biết về API version

| Chi tiết | Cần xác minh |
| --- | --- |
| `@IdGeneratorType` | Có từ Hibernate 6.0, hướng custom annotation |
| `BeforeExecutionGenerator` | Documented Generator SPI từ Hibernate 6.2 |
| `OnExecutionGenerator` | Documented Generator SPI từ Hibernate 6.2 |
| `AnnotationBasedGenerator` | API type-safe cho annotation config |
| `@ValueGenerationType` | Hibernate custom value generation; loại implementation khác theo đời |
| `@GenericGenerator` | Legacy; deprecated từ Hibernate 6.5 |
| `GeneratorType` legacy | Deprecated; tránh cho code mới |
| `@Generated(event=...)` | Dùng `EventType` hiện đại, tránh enum cũ `GenerationTime` |
| `@UuidGenerator` | Hibernate 6+ built-in UUID |
| `GenerationType.UUID` | Cần Jakarta Persistence 3.1/provider phù hợp |
| `OnExecutionGenerator` method signatures | Kiểm tra đúng Javadocs 6.x/7.x, nhất là ID retrieval |
| `GeneratorCreationContext` | Bootstrap context, không phải runtime Session |

Không đưa code ví dụ của Hibernate 7.x vào dự án Hibernate 5 rồi chỉ sửa package import. Những phiên bản có khác biệt API thực sự.

## 54. Những lỗi phổ biến

### Lỗi 1: tự viết custom UUID generator dù built-in đã đủ

Tăng maintenance, testing và coupling mà không thêm giá trị nghiệp vụ.

**Cách sửa:** dùng `@UuidGenerator` hoặc JPA `GenerationType.UUID`.

### Lỗi 2: đặt `@IdGeneratorType` trên field trực tiếp

`@IdGeneratorType` là **meta-annotation** dành cho một annotation mới, không phải annotation đặt trực tiếp lên entity field.

**Cách sửa:** tạo `@SalesId` có `@IdGeneratorType(SalesIdGenerator.class)`, rồi đặt `@SalesId` trên `@Id`.

### Lỗi 3: thiếu `@Retention(RUNTIME)`

Hibernate không nhận được custom annotation theo metadata runtime như mong đợi.

**Cách sửa:** khai báo retention runtime.

### Lỗi 4: dùng `@ValueGenerationType` cho ID như property thường

Không làm rõ identifier semantics.

**Cách sửa:** dùng `@IdGeneratorType` cho ID, `@ValueGenerationType` cho non-ID field.

### Lỗi 5: dùng UPDATE event cho ID

Có thể phá identity map/foreign keys.

**Cách sửa:** `EventTypeSets.INSERT_ONLY`.

### Lỗi 6: gán hai generators lên một field

Hibernate không có contract “chain hai generator annotations trên một property”.

**Cách sửa:** một generator owner duy nhất.

### Lỗi 7: generator giữ `long counter++` trong instance

Không an toàn với concurrency, restart hoặc nhiều JVM.

**Cách sửa:** DB sequence hoặc allocator/UUID được kiểm chứng.

### Lỗi 8: dùng `MAX(id)+1`

Race condition giữa transactions.

**Cách sửa:** dùng allocator có atomicity và unique constraint.

### Lỗi 9: bỏ primary key constraint vì generator “không bao giờ trùng”

Code không thể thay DB integrity constraint.

**Cách sửa:** PK/unique constraint ở database.

### Lỗi 10: sinh ID bằng đồng hồ cộng random quá ngắn

Dễ collision khi multi-node, clock rollback hoặc burst traffic.

**Cách sửa:** thuật toán đã kiểm chứng, test multi-node, tránh tự invent.

### Lỗi 11: tự commit/close Connection trong generator

Phá transaction của Hibernate.

**Cách sửa:** tôn trọng transaction manager và lifecycle JDBC managed.

### Lỗi 12: gọi HTTP/Kafka trong `generate`

Side effects ngoài transaction, timeout và idempotency phức tạp.

**Cách sửa:** domain service/outbox, hoặc cấp trước khi persist qua boundary được quản lý.

### Lỗi 13: dùng `@PrePersist` như ID SPI chính thức

Không bảo đảm mọi nhu cầu identity management của Hibernate.

**Cách sửa:** dùng built-in ID strategy hoặc `@IdGeneratorType`.

### Lỗi 14: viết OnExecutionGenerator chỉ để lấy DB default

Tăng coupling với dialect/SQL retrieval.

**Cách sửa:** `@Generated`, `@GeneratedColumn`, `@ColumnDefault` theo trường hợp.

### Lỗi 15: nghĩ `@Generated` tự tạo trigger

Annotation thông báo Hibernate về DB-generated value; trigger/DDL phải tồn tại riêng.

**Cách sửa:** migration schema và integration test.

### Lỗi 16: nghĩ `BeforeExecutionGenerator` luôn chạy đúng tại `persist()`

Thời điểm sinh phụ thuộc persistence lifecycle/strategy.

**Cách sửa:** dựa trên hợp đồng INSERT/UPDATE, không dựa vào thời điểm log ngẫu nhiên.

### Lỗi 17: nghĩ ID đã sinh nghĩa là transaction đã commit

ID có thể tồn tại trong RAM rồi transaction rollback.

**Cách sửa:** phát sự kiện thành công sau commit hoặc outbox.

### Lỗi 18: không phân biệt assigned ID với generated ID

Caller tự gán ID trong khi generator cũng muốn sinh mới.

**Cách sửa:** một chính sách ID rõ.

### Lỗi 19: format ID không khớp column length

INSERT bị truncate/lỗi constraint.

**Cách sửa:** validate prefix/result length và DDL.

### Lỗi 20: sequence allocation mismatch

Có thể tạo ID không như kỳ vọng hoặc làm bootstrap/insert lỗi.

**Cách sửa:** kiểm tra increment/optimizer/DDL.

### Lỗi 21: coi `@Version` như một field custom timestamp bình thường

Có thể phá optimistic locking.

**Cách sửa:** dùng version management có sẵn hoặc SPI có contract đúng.

### Lỗi 22: quên rằng bulk SQL bỏ qua entity generator

Native UPDATE không gọi callback generation của từng entity.

**Cách sửa:** nếu mọi writer phải cập nhật field, dùng DB trigger/constraint hoặc rewrite thích hợp.

### Lỗi 23: generator dựa vào mutable static field

Race, memory leak hoặc state giữa tenants.

**Cách sửa:** immutable configuration và nguồn uniqueness tin cậy.

### Lỗi 24: test một Session rồi kết luận generator đúng

Chưa kiểm chứng restart, multi-thread, DB constraints và transaction.

**Cách sửa:** test integration, concurrency và multi-instance.

### Lỗi 25: nâng Hibernate cùng lúc đổi ID format

Thay đổi quá nhiều contract và rủi ro migration.

**Cách sửa:** tách bước nâng ORM và bước đổi data representation.

### Lỗi 26: dùng ID để suy ra quyền truy cập

ID không phải security capability mặc định.

**Cách sửa:** enforce tenant/authorization trong query/service.

### Lỗi 27: generator luôn trả một giá trị mặc định khi lỗi

Có thể phát duplicate hoặc ghi dữ liệu sai.

**Cách sửa:** fail fast và rollback, retry tại boundary hợp lệ.

### Lỗi 28: không đo tác động đến INSERT batching

Generator cần DB round trip từng entity có thể giảm throughput.

**Cách sửa:** đo performance và cân nhắc sequence optimizer.

## 55. Bài thực hành 1 — Chọn built-in hay custom

Cho các yêu cầu:

1. ID BIGINT tự tăng.
2. UUID ID.
3. CreatedAt.
4. LastModifiedAt.
5. Prefix reference code.
6. Số hóa đơn pháp lý theo chi nhánh.

Hãy chọn lựa:

- IDENTITY / SEQUENCE / UUID.
- Creation/UpdateTimestamp.
- Custom generator non-ID.
- Business numbering service.

Giải thích vì sao **không phải mọi yêu cầu đều cần SPI**.

## 56. Bài thực hành 2 — Viết `@SalesId`

Tạo custom annotation với prefix, liên kết `@IdGeneratorType` và `SalesIdGenerator`.

Yêu cầu:

- `RetentionPolicy.RUNTIME`.
- Field/getter target.
- `EventTypeSets.INSERT_ONLY`.
- Result type là String.
- Không dùng mutable counter.
- Database PK constraint.

Kiểm tra annotation hiện trên metadata Hibernate bằng integration test.

## 57. Bài thực hành 3 — So sánh constructor và `AnnotationBasedGenerator`

Viết hai biến thể của generator nhận cùng `prefix`:

- Constructor `(SalesId, Member, GeneratorCreationContext)`.
- `implements AnnotationBasedGenerator<SalesId>` với `initialize(...)`.

So sánh khả năng validate config, cách nhận annotation và nơi giữ immutable state.

## 58. Bài thực hành 4 — Sinh mã correlation khi INSERT

Dùng `@ValueGenerationType` để tạo `GeneratedCorrelationCode` cho field `AuditEvent.correlationCode`, không phải ID.

Thực hiện INSERT, UPDATE và xác nhận:

- Code được sinh khi INSERT.
- Code không đổi khi UPDATE.
- ID database identity vẫn đúng.
- Unique constraint bảo vệ collision.

## 59. Bài thực hành 5 — UPDATE timestamp generator

Tạo `@GeneratedTouchTime` dùng `INSERT_AND_UPDATE`, đặt trên field `Instant touchedAt`.

Thử cập nhật business field rồi flush. So sánh với `@UpdateTimestamp` và `@CurrentTimestamp` để quyết định có cần custom code thật không.

## 60. Bài thực hành 6 — Database default

Tạo cột `created_at DEFAULT CURRENT_TIMESTAMP` bằng schema migration. Dùng `@Generated(event=INSERT)` để đọc giá trị sau INSERT.

So sánh:

- DB default.
- JVM timestamp.
- Custom BeforeExecutionGenerator.
- Custom OnExecutionGenerator.

Đánh giá chi phí và độ chính xác.

## 61. Bài thực hành 7 — Race condition của counter

Viết một generator sai dùng:

```java
private long nextId = 0;

long next() {
    return ++nextId;
}
```

Chạy nhiều threads, nhiều process/restart và chứng minh vì sao nguồn này không thể đảm bảo uniqueness toàn hệ thống.

Sửa bằng database sequence hoặc ID algorithm phân tán được kiểm chứng.

## 62. Bài thực hành 8 — Sequence rollback

Tạo hai transactions: transaction đầu lấy ID rồi rollback; transaction sau persist thành công.

Không yêu cầu hai ID liên tục. Xác minh uniqueness, commit/rollback và primary key constraint.

## 63. Bài thực hành 9 — Multi-tenancy

Giả sử hai tenants dùng schema riêng đều có numeric ID=1.

Chọn một trong hai:

- PK unique trong từng schema + tenant context ở giao tiếp ngoài.
- Global ID strategy.
- Composite identifier được mapping rõ.

Giải thích vì sao tenant ID từ client không đáng tin để sinh ID.

## 64. Bài thực hành 10 — Legacy generator migration

Cho code `@GenericGenerator` Hibernate 5:

1. Xác định semantics thực tế.
2. Viết phiên bản `@IdGeneratorType` cho Hibernate 6.6.
3. Không đổi ID column type.
4. Kiểm tra dữ liệu cũ vẫn load được.
5. Test rolling deploy nếu writers cũ/mới cùng tồn tại.

## 65. Bài thực hành 11 — Side effect và idempotency

Mô tả một callback `generate(...)` gọi remote allocator rồi publish Kafka.

Chỉ ra failure modes nếu transaction rollback sau khi publish. Thiết kế lại bằng application boundary và transactional outbox.

## 66. Bài thực hành 12 — Verify field length

Annotation cho phép prefix từ 2 đến 8 chữ cái và dấu gạch dưới; random part gồm 32 hex digits.

Tính max length của ID, đối chiếu database column, unique index, FK columns và API validation.

## 67. Bài thực hành 13 — Event types

Cho ba fields:

- `id`.
- `createdAt`.
- `updatedAt`.

Chọn event set:

- `INSERT_ONLY`.
- `INSERT_AND_UPDATE`.

Giải thích tại sao `@Id` không bao giờ dùng UPDATE event.

## 68. Bài thực hành 14 — Bulk update ngoài ORM

Chạy native SQL thay đổi một entity và kiểm tra `touchedAt` có tự đổi theo Java generator hay không.

Nếu yêu cầu mọi UPDATE đều đổi `touchedAt`, thiết kế database trigger/default và mapping `@Generated` phù hợp.

## 69. Bài thực hành 15 — Monitoring và performance

Trên 100.000 inserts:

- Đo identity vs sequence with allocation vs custom UUID.
- Ghi JDBC round trips, SQL batch size, transaction latency.
- Quan sát DB locks, memory và index locality.
- Đánh giá uniqueness dưới concurrency và restart.

Không suy từ benchmark local một thread sang toàn bộ production; thay đổi cần có workload tương đương.

## 70. Câu hỏi tự kiểm tra

**1. Generator SPI dùng để làm gì?**

Để Hibernate tích hợp một chiến lược sinh giá trị cho mapped attribute vào lifecycle INSERT/UPDATE theo contract được công bố.

**2. Custom ID generator và custom value generator khác nhau?**

ID generator tạo primary key, phải có semantics INSERT-only và uniqueness. Value generator tạo property khác có thể sinh khi INSERT, UPDATE hoặc cả hai.

**3. Hai nhánh Generator SPI quan trọng là gì?**

`BeforeExecutionGenerator` và `OnExecutionGenerator`.

**4. `BeforeExecutionGenerator` sinh ở đâu?**

Trong Java trước khi Hibernate thực thi SQL tương ứng, và giá trị được đưa vào SQL theo mapping.

**5. `OnExecutionGenerator` sinh ở đâu?**

Giá trị được database tạo như một phần INSERT/UPDATE, Hibernate phối hợp lấy state về.

**6. `@IdGeneratorType` đặt ở đâu?**

Trên định nghĩa custom annotation, rồi annotation ấy đặt trên `@Id` field/getter.

**7. `@ValueGenerationType` dùng cho trường hợp nào?**

Để gắn generator với non-ID attribute (hoặc những value-generation use cases được SPI hỗ trợ).

**8. Custom annotation cần retention gì?**

`RetentionPolicy.RUNTIME`.

**9. `getEventTypes()` của ID generator thường trả gì?**

`EventTypeSets.INSERT_ONLY`.

**10. `EventTypeSets.INSERT_AND_UPDATE` thường dùng cho gì?**

Những field cần sinh lại lúc Hibernate phát SQL UPDATE, ví dụ update timestamp.

**11. Vì sao không dùng counter instance cho ID?**

Không thread-safe/multi-process/restart safe và dễ trùng.

**12. `AtomicLong` sửa được uniqueness đa node không?**

Không. Nó chỉ đồng bộ trong một JVM.

**13. Vì sao cần PK/unique constraint dù UUID collision rất hiếm?**

Database là lớp cuối cùng bảo vệ tính duy nhất và toàn vẹn.

**14. Khi nào nên dùng `@SequenceGenerator`?**

Khi cần numeric IDs và DB hỗ trợ sequence; thường tốt hơn tự viết JDBC allocator.

**15. Sequence có đảm bảo số liên tục sau rollback không?**

Không. Gaps có thể xảy ra.

**16. `@UuidGenerator` khác custom generator gọi UUID thế nào?**

`@UuidGenerator` là API Hibernate có sẵn, giảm code cần tự duy trì/kiểm thử.

**17. `@Generated` có tự tạo trigger không?**

Không. Nó khai báo rằng database sinh giá trị và giúp Hibernate đồng bộ state; DDL/trigger phải có riêng.

**18. Vì sao tự viết OnExecutionGenerator khó hơn?**

Phải phối hợp SQL expression/column inclusion và retrieval theo dialect/driver/identifier semantics.

**19. `@GenericGenerator` có còn dùng được không?**

Có trong nhiều dự án/versions, nhưng là API legacy; deprecated từ Hibernate 6.5 và không ưu tiên cho code mới.

**20. Hibernate 5 có cùng Generator SPI 6.2 không?**

Không. Code legacy dùng những extension points/chữ ký khác; cần migration có kiểm chứng.

**21. `@PrePersist` có thay thế IdentifierGenerator SPI không?**

Không. Nó là entity lifecycle callback, không có cùng hợp đồng identity generation.

**22. Generator có được gọi `commit` không?**

Không được chiếm quyền transaction của Hibernate/transaction manager.

**23. Có nên gọi remote HTTP trong `generate` không?**

Thường không; làm tăng latency, failure mode và side effects ngoài transaction.

**24. ID đã sinh có chứng minh row commit không?**

Không. Transaction có thể rollback.

**25. Khi nào cần value generator thay vì domain method?**

Khi generation thật sự gắn với INSERT/UPDATE của ORM, có tính cơ học và tái sử dụng tốt.

**26. Generator nên giữ state mutable theo mỗi entity không?**

Không. Nên giữ cấu hình bất biến và tránh mutable state dùng chung.

**27. `@Version` có giống custom code field không?**

Không. Version có protocol optimistic locking; không nên sửa tùy tiện.

**28. Bulk JPQL/native UPDATE có gọi value generator cho từng entity không?**

Không nên giả định. Bulk DML có thể bỏ qua entity lifecycle.

**29. Vì sao cần kiểm tra generated column trong DB thực?**

Vì trigger/default/RETURNING/JDBC generated keys khác nhau giữa dialects.

**30. Một custom generator tốt phải được kiểm thử ở những tầng nào?**

Unit format/config, ORM integration, transaction rollback, concurrency/multi-instance, DB constraints và performance.

**31. Vì sao `@SalesId` chỉ nên gắn trên field/getter theo JPA access type?**

Để Hibernate metadata nhận đúng generator cho mapped attribute.

**32. Có thể gắn `@UuidGenerator` và `@SalesId` cùng một ID không?**

Không nên; đó là hai chiến lược cạnh tranh trên một property.

**33. Nếu muốn mã hóa đơn liên tục theo năm/chi nhánh, nên làm gì?**

Thiết kế business number allocator và transaction/audit riêng, không chỉ custom PK generator.

**34. Vì sao phải tách phiên bản Hibernate khi tham khảo ví dụ?**

Tên interface, annotation, phương thức và deprecation có thay đổi từ 5.x sang 6.x/7.x.

**35. Quy tắc cốt lõi để quyết định custom SPI là gì?**

Nếu built-in đã đáp ứng, dùng built-in. Nếu business thật sự cần mở rộng, chọn SPI được công bố, giữ generator nhỏ, xác định contract và kiểm thử toàn bộ persistence lifecycle.

## 71. Checklist triển khai thực tế

Trước khi merge một custom generator:

1. [ ] Đã xác định Hibernate core version thực thi và đọc Javadocs tương ứng.
2. [ ] Đã đánh giá `@GeneratedValue`, sequence, identity, UUID và timestamp built-ins.
3. [ ] Đã xác định field là ID hay non-ID.
4. [ ] Đã xác định event set INSERT/UPDATE.
5. [ ] Đã dùng custom annotation type-safe nếu code mới dùng SPI 6.2+.
6. [ ] Annotation có runtime retention và target hợp access type.
7. [ ] Generator nhận config bằng constructor/`AnnotationBasedGenerator` được hỗ trợ.
8. [ ] Không giữ Session, Connection, entity hoặc mutable counter trong fields.
9. [ ] Không tự commit/rollback/close managed Connection.
10. [ ] Giá trị trả về phù hợp Java type, JDBC mapping và column length.
11. [ ] DB có PK/unique constraints đúng phạm vi.
12. [ ] Đã kiểm tra restart/multi-node/tenant boundaries.
13. [ ] Không gọi network/publish side effects trong callback generation.
14. [ ] Có policy exception/rollback/retry tại transaction boundary.
15. [ ] Không trùng với một generator annotation khác.
16. [ ] Không làm thay đổi ID sau khi persistent.
17. [ ] Có test INSERT và UPDATE theo đúng event set.
18. [ ] Có test DB-generated default/trigger nếu dùng OnExecution.
19. [ ] Có test rollback/sequence gaps/concurrent persistence.
20. [ ] Có migration plan nếu đổi ID strategy/schema type.
21. [ ] Có benchmark SQL batching/latency khi generator chạy trong workload lớn.
22. [ ] Tài liệu hóa contract ID/code và kế hoạch nâng Hibernate về sau.

## 72. Tổng kết

- Hibernate hỗ trợ **custom value/identifier generation** qua Generator SPI, không cần dùng reflection hoặc hooks nội bộ thiếu contract.
- **`BeforeExecutionGenerator`** tạo giá trị trước SQL; **`OnExecutionGenerator`** biểu diễn giá trị do database sinh khi SQL chạy.
- **`@IdGeneratorType`** dùng custom ID annotation; **`@ValueGenerationType`** dùng custom value annotation.
- **`EventTypeSets.INSERT_ONLY`** là sự kiện phù hợp cho identifier; field update timestamp có thể dùng `INSERT_AND_UPDATE`.
- **Hãy dùng built-ins trước:** `@GeneratedValue`, `@SequenceGenerator`, `@UuidGenerator`, `@CreationTimestamp`, `@UpdateTimestamp`, `@Generated`, `@GeneratedColumn`.
- **`@GenericGenerator`** và `IdentifierGenerator` cũ vẫn hiện diện để tương thích, nhưng code mới ở Hibernate 6.5+ nên ưu tiên type-safe annotation-based generation.
- **Không dùng local counter hoặc SELECT MAX(id)+1** để cấp ID nhiều transaction/nodes.
- **Không tạo transaction, commit, rollback, đóng Connection hoặc phát side effect từ generator.**
- **ID generated không có nghĩa transaction committed.** Phải tách outbox/idempotency và business numbering khỏi ID allocation.
- **Database constraints bảo vệ uniqueness**, còn test concurrency, crash/restart và multi-tenant bảo vệ kiến trúc.
- **Nếu database sinh giá trị qua default/trigger**, ưu tiên annotation mapping sẵn có trước khi tự implement OnExecutionGenerator.
- **Nâng cấp Hibernate phải đối chiếu SPI theo version** và kiểm tra schema/IDs cũ, tránh thay đổi đồng thời format PK và ORM.

Một custom generator tốt là **phần mở rộng nhỏ, rõ event và rõ quyền sở hữu**: nhận cấu hình có kiểu, tạo đúng giá trị cần thiết, trả lại cho Hibernate, không chiếm transaction và không thực hiện nghiệp vụ ngoài phạm vi generation. Khi giữ được ranh giới ấy, ứng dụng có thể mở rộng cách sinh ID hoặc giá trị mà vẫn tận dụng sự nhất quán và cơ chế persistence do Hibernate quản lý.

---

## Tài liệu chính thức để tra cứu theo version

1. [Hibernate ORM 6.6 — Generator SPI](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/generator/Generator.html): giao diện nền, event sets, before/on-execution generation.
2. [Hibernate ORM 6.6 — BeforeExecutionGenerator](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/generator/BeforeExecutionGenerator.html): phương thức `generate(...)` và generation trước SQL.
3. [Hibernate ORM 6.6 — OnExecutionGenerator](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/generator/OnExecutionGenerator.html): xử lý column expression và DB-generated values.
4. [Hibernate ORM 6.6 — @IdGeneratorType](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/annotations/IdGeneratorType.html): meta-annotation cho ID generator.
5. [Hibernate ORM 6.6 — @ValueGenerationType](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/annotations/ValueGenerationType.html): meta-annotation cho custom value generator.
6. [Hibernate ORM 6.6 — AnnotationBasedGenerator](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/generator/AnnotationBasedGenerator.html): initialization từ custom annotation.
7. [Hibernate ORM 6.6 — @Generated](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/annotations/Generated.html): giá trị do DB sinh và được Hibernate truy hồi.
8. [Hibernate ORM 6.6 — @GenericGenerator](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/annotations/GenericGenerator.html): API legacy và deprecation.
9. [Hibernate ORM 7.x — Generator package](https://docs.hibernate.org/stable/core/javadocs/org/hibernate/generator/package-summary.html): kiểm tra đường phát triển của SPI ở dòng mới.

Khi dùng một tài liệu ví dụ, hãy đối chiếu cả **minor version** của Hibernate và phiên bản Jakarta Persistence trong project; thay đổi version có thể ảnh hưởng chữ ký constructor, annotation, bootstrap và cách Hibernate sinh hoặc lấy lại giá trị.
