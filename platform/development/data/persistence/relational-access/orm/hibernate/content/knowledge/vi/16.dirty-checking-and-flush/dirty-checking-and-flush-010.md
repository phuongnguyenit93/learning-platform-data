# Trường sinh tự động, giá trị mặc định và thời điểm đồng bộ trở lại trong Hibernate

## 1. Một giá trị đã có trong database không có nghĩa entity đã thấy nó

Trong ứng dụng sử dụng Hibernate, một entity có thể chứa những thuộc tính mà **ứng dụng không tự gán**, thay vào đó database hoặc ORM tự tạo giá trị. Ví dụ:

- `id` được sinh bằng identity column hoặc sequence.
- `created_at` mặc định theo thời gian của database.
- `status` mặc định bằng `'NEW'` khi INSERT không truyền giá trị.
- `updated_at` được trigger cập nhật mỗi lần ghi.
- `line_total` là generated column tính `quantity * unit_price`.
- `version` được Hibernate tăng khi kiểm soát cập nhật đồng thời.

Điểm khó là có **hai thời điểm khác nhau**:

1. **Thời điểm giá trị được sinh hoặc cập nhật**: có thể ở Java trước câu SQL, khi Hibernate gửi INSERT/UPDATE, hoặc bên trong database lúc xử lý câu lệnh.
2. **Thời điểm giá trị được đưa trở lại Java entity**: có thể ngay sau thao tác SQL nếu Hibernate biết thuộc tính là generated và có cơ chế lấy giá trị, hoặc chỉ sau `refresh()`/truy vấn trong một persistence context mới.

Giả sử một entity có:

```java
private String status; // null khi new

// Database: status VARCHAR(24) DEFAULT 'NEW'
```

Nếu Hibernate phát:

```sql
INSERT INTO orders (status, description)
VALUES (NULL, 'Đơn hàng thử');
```

thì **DEFAULT thông thường không được kích hoạt** do cột đã được truyền giá trị `NULL` một cách tường minh. Ngược lại, nếu phát:

```sql
INSERT INTO orders (description)
VALUES ('Đơn hàng thử');
```

và schema có `DEFAULT 'NEW'`, database có thể tạo `status = 'NEW'`. Nhưng entity Java vẫn có thể giữ `status == null` nếu Hibernate **không được cấu hình lấy giá trị sinh từ database trở lại**.

Ba câu hỏi cần luôn đặt ra:

- **Cột có bị bỏ khỏi INSERT/UPDATE không?**
- **Database hoặc Hibernate thực sự tạo giá trị bằng cách nào?**
- **Khi nào persistence context biết giá trị cuối cùng?**

Đây là trọng tâm của bài học về *Dirty Checking và Flush*: phải hiểu cả chiều **đưa thay đổi xuống database** lẫn chiều **đồng bộ giá trị database sinh ra trở lại entity**.

## 2. Phân loại nguồn sinh giá trị

Một thuộc tính “tự động” có thể do nhiều cơ chế khác nhau tạo ra.

| Nguồn giá trị | Ví dụ | Thời điểm tạo giá trị | Hibernate có tự thấy ngay không? |
|---|---|---|---|
| Constructor/field initializer Java | `status = OrderStatus.NEW` | Khi tạo object | **Có**, vì object đã có giá trị |
| Callback JPA | `@PrePersist` gán `createdAt` | Trước thao tác persist/INSERT theo lifecycle | Có, vì callback sửa entity Java |
| Hibernate tạo bằng JVM | `@CreationTimestamp(source = VM)` | Theo lifecycle insert của ORM | Hibernate có thể quản lý giá trị vì nó tạo ra |
| Hibernate dùng biểu thức DB | `@CreationTimestamp(source = DB)` | Khi database thực thi biểu thức thời gian | Hibernate lấy giá trị theo cơ chế generated mapping tương ứng |
| Database `DEFAULT` | `status DEFAULT 'NEW'` | Khi INSERT không cung cấp giá trị cho cột | **Không bảo đảm** nếu mapping không khai báo giá trị generated |
| Trigger database | `updated_at = CURRENT_TIMESTAMP` | Trong INSERT/UPDATE do trigger xử lý | Cần cơ chế readback hoặc refresh |
| Generated/computed column | `amount GENERATED ALWAYS AS (...)` | Theo cơ chế của database | Cần mapping phù hợp để lấy kết quả |
| Khóa chính identity | `id GENERATED ... AS IDENTITY` | Khi INSERT | Hibernate cần lấy ID để quản lý identity |
| Khóa chính sequence | `nextval(...)` | Khi generator lấy số | ID có thể xuất hiện trước INSERT |
| Hibernate optimistic version | `@Version` | Khi ORM quản lý INSERT/UPDATE version | Thường do Hibernate tự quản lý theo mapping |

**“Giá trị mặc định”**, **“giá trị được sinh”** và **“giá trị Hibernate đã tải”** là những khái niệm liên quan nhưng không đồng nhất.

### 2.1. Minh họa bằng dòng thời gian

```mermaid
sequenceDiagram
    participant App as Application
    participant PC as Hibernate Persistence Context
    participant DB as Database

    App->>PC: new Order(); persist(order)
    Note over PC: Có thể giữ status=null
    App->>PC: flush()
    PC->>DB: INSERT (bỏ cột status)
    DB->>DB: DEFAULT status='NEW'
    DB-->>PC: Kết quả INSERT
    alt Mapping khai báo generated, DB/dialect hỗ trợ lấy giá trị
        PC->>DB: RETURNING hoặc SELECT bổ sung khi cần
        DB-->>PC: status='NEW'
    else Không cấu hình readback
        Note over PC: status có thể vẫn null
    end
    App->>PC: getStatus()
    Note over App,PC: Kết quả phụ thuộc mapping và readback
```

Hibernate có thể dùng `INSERT ... RETURNING`, JDBC generated values hoặc một `SELECT` bổ sung để lấy thông tin cần thiết, tùy version, dialect, driver và loại giá trị. Không nên giả định mọi database đều dùng cùng một chuỗi SQL.

## 3. Dirty checking, flush và commit nằm ở đâu?

### 3.1. Entity managed được theo dõi thay đổi

Giả sử:

```java
Order order = em.find(Order.class, id);
order.changeDescription("Đã xác nhận");
```

Nếu `order` đang **managed** và transaction hợp lệ, Hibernate theo dõi sự thay đổi của mapped attributes. Câu `UPDATE` có thể được tạo khi `flush` xảy ra.

```text
Java setter -> managed state bị thay đổi
          |
Hibernate dirty checking / action queue
          |
       flush()
          |
          v
SQL UPDATE/INSERT/DELETE được thực thi
          |
       commit()
          |
          v
Transaction thành công, thay đổi được commit
```

Thời điểm SQL chạy phụ thuộc flush mode, ID generator, query, transaction và cấu hình ORM. `flush()` **không đồng nghĩa với `commit()`**: SQL có thể đã chạy nhưng vẫn bị rollback.

### 3.2. Giá trị do database sinh thường cần một bước đi ngược lại

Đối với field `updatedAt` được trigger sửa:

```text
order.description = "Đã xác nhận"       (Java đổi)
            |
            v
Hibernate flush -> SQL UPDATE          (Java -> DB)
            |
            v
DB trigger -> updated_at thay đổi      (DB nội bộ)
            |
            v
Hibernate phải biết đọc lại giá trị    (DB -> Java)
```

Nếu Hibernate **không biết field được DB sinh**, managed object có thể tiếp tục giữ timestamp cũ. Dirty checking chỉ giải quyết phần thay đổi theo dõi từ Java; nó **không tự phát hiện mọi trigger hoặc DEFAULT** trong database.

### 3.3. Hai khái niệm “tự đồng bộ” cần tách riêng

- **Flush:** đẩy các thay đổi đang chờ từ persistence context xuống database.
- **Readback/refresh generated values:** đưa giá trị do database tính hoặc sinh trở lại entity Java.

Một lần `flush` có thể kéo theo cả hai **nếu mapping khai báo generated attribute và Hibernate có cơ chế xử lý tương ứng**. Nếu không, application có thể cần `refresh` sau flush. Không xem `flush` là lệnh “đọc lại mọi cột” mặc định.

## 4. Database `DEFAULT`: chỉ chạy khi cột không được cung cấp

### 4.1. Schema mẫu

Ví dụ bảng đơn hàng, có default do database quản lý:

```sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    description VARCHAR(200) NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'NEW',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);
```

Cú pháp DDL, precision và kiểu timestamp khác nhau tùy database. Để thảo luận các trường do DB sinh, trước hết xét riêng `status` và `created_at`.

Ba câu SQL cho ba kết quả khác nhau:

```sql
-- Trường hợp A: bỏ cột status.
INSERT INTO purchase_orders (description)
VALUES ('Đơn A');
-- status dùng DEFAULT 'NEW'.

-- Trường hợp B: truyền NULL tường minh.
INSERT INTO purchase_orders (description, status)
VALUES ('Đơn B', NULL);
-- Với NOT NULL, có thể bị từ chối; DEFAULT không cứu giá trị NULL.

-- Trường hợp C: truyền một giá trị.
INSERT INTO purchase_orders (description, status)
VALUES ('Đơn C', 'APPROVED');
-- status = 'APPROVED', không dùng DEFAULT.
```

Đây là quy tắc SQL quan trọng nhất khi phối hợp database default và Hibernate. Một default ở DDL **không có nghĩa Hibernate sẽ tự bỏ trường null khỏi INSERT**.

### 4.2. `@ColumnDefault` dùng để làm gì?

Hibernate có annotation:

```java
import org.hibernate.annotations.ColumnDefault;
```

Ví dụ:

```java
@ColumnDefault("'NEW'")
@Column(name = "status", nullable = false, length = 24)
private String status;
```

`@ColumnDefault` mô tả biểu thức DEFAULT phục vụ **DDL do Hibernate sinh**. Nó **không** tự đặt giá trị `"NEW"` cho field Java khi gọi constructor; cũng không tự động ép Hibernate bỏ cột status khỏi mọi câu INSERT.

Trong dự án dùng Flyway, Liquibase hoặc migration SQL, vẫn phải đảm bảo schema production có default thực tế. Cấu hình annotation không thay thế migration đã triển khai.

Một nhầm lẫn hay gặp:

```java
@SideEffectFree // Không phải annotation thực tế: minh họa ý tưởng sai.
@ColumnDefault("'NEW'")
private String status;
```

Không có cơ chế ngầm rằng chỉ cần thêm annotation DDL thì `new Order().getStatus()` sẽ trả `NEW`. Field Java vẫn tuân theo quy tắc khởi tạo Java trừ khi code hoặc ORM gán nó.

### 4.3. Mặc định ở Java hay mặc định ở database?

Nếu trạng thái mặc định là một **quy tắc domain ổn định**, có thể đặt ngay trong constructor:

```java
public PurchaseOrder(String description) {
    this.description = description;
    this.status = "NEW";
}
```

Ưu điểm: code Java biết giá trị ngay cả trước `persist`; application không phải chờ SQL readback để hiển thị trạng thái ban đầu.

Nếu nhiều ứng dụng cùng ghi một bảng và cần một **fallback ở database**, default SQL có thể bảo vệ các writer bỏ qua cột. Có thể phối hợp **Java default và database default**, nhưng phải định nghĩa rõ nguồn nào được ưu tiên và kiểm tra khả năng hai quy tắc bị lệch.

Nếu ứng dụng cho phép trạng thái ban đầu thay đổi theo tenant/request, hard-code default Java hoặc default database có thể không phù hợp; nên định nghĩa ở business service.

## 5. `@DynamicInsert` và sự khác nhau giữa “null” với “không ghi cột”

Hibernate có annotation `@DynamicInsert` để tạo câu INSERT dựa trên các field cần được đưa vào, đặc biệt hỗ trợ **bỏ các thuộc tính null** thay vì ghi `NULL` tường minh.

### 5.1. Entity minh họa chỉ dùng default SQL

```java
package com.example.orders;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import org.hibernate.annotations.ColumnDefault;
import org.hibernate.annotations.DynamicInsert;

@Entity
@Table(name = "purchase_orders")
@DynamicInsert
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "description", nullable = false, length = 200)
    private String description;

    @ColumnDefault("'NEW'")
    @Column(name = "status", nullable = false, length = 24)
    private String status;

    @ColumnDefault("CURRENT_TIMESTAMP")
    @Column(name = "created_at")
    private java.time.LocalDateTime createdAt;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String description) {
        this.description = description;
        // status và createdAt vẫn null ở Java.
    }

    public Long getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }

    public java.time.LocalDateTime getCreatedAt() {
        return createdAt;
    }
}
```

Khi Hibernate tạo SQL INSERT cho các field null trong ví dụ, có thể tạo:

```sql
INSERT INTO purchase_orders (description)
VALUES (?);
```

Khi `status` và `created_at` không có mặt trong INSERT, database có thể dùng hai default đã khai báo.

**Nhưng:** `@DynamicInsert` chỉ tác động đến SQL INSERT, không tự bảo đảm entity Java được cập nhật bằng những giá trị database vừa sinh. Vì thế:

```java
em.persist(order);
em.flush();

System.out.println(order.getStatus());
// Có thể vẫn là null nếu chưa có cơ chế readback hoặc refresh.
```

Để nhận giá trị database, cần mapping generated field hoặc gọi `refresh` có chủ đích.

### 5.2. Những giới hạn của `@DynamicInsert`

- Các thuộc tính **non-null** vẫn có thể xuất hiện trong INSERT; database default không được dùng cho những field đó.
- Với **primitive** như `int`, giá trị mặc định Java là `0`, không phải `null`, nên có thể được gửi tới database. Khi cần phân biệt “không cung cấp” với “đã cung cấp 0”, dùng wrapper `Integer` và nghiệp vụ phù hợp.
- Hibernate có thể tạo nhiều biến thể SQL INSERT theo tổ hợp field null/non-null; điều này có thể tác động hiệu năng statement cache và JDBC batching.
- Nó không tự động giải quyết giá trị sinh từ UPDATE trigger.
- Nếu schema thật không có DEFAULT hoặc trigger, bỏ cột sẽ cho kết quả khác mong đợi hoặc vi phạm NOT NULL.
- Không nhầm `@DynamicInsert` với `@DynamicUpdate`. `@DynamicUpdate` thay đổi tập cột trong SQL UPDATE theo những thuộc tính dirty; SQL DEFAULT thông thường **không tự chạy lại** khi UPDATE.

### 5.3. Không dùng `@DynamicInsert` để che giấu validation

Nếu `status` là một giá trị bắt buộc do business service phải chọn, bỏ null khỏi INSERT và để database tự gán có thể che mất lỗi code không gán trạng thái.

Hãy dùng default SQL khi đó thật sự là **chính sách hợp lệ**; còn khi thiếu giá trị là lỗi nghiệp vụ, validate trước persist.

## 6. `@Generated`: nói với Hibernate rằng database đã sinh giá trị

Một cách Hibernate hỗ trợ đồng bộ lại các field được database tạo là annotation:

```java
import org.hibernate.annotations.Generated;
import org.hibernate.generator.EventType;
```

Trong Hibernate 6.x hiện đại, `@Generated` có thể khai báo sự kiện mà database sinh giá trị, chẳng hạn INSERT và UPDATE. Ví dụ:

```java
@Generated(event = EventType.INSERT)
@Column(name = "status", insertable = false, updatable = false)
private String status;
```

Khi Hibernate thực hiện INSERT với mapping này:

1. `status` không được đưa vào INSERT vì `insertable = false`.
2. Database sử dụng DEFAULT hoặc cơ chế sinh đã thiết kế.
3. Hibernate biết thuộc tính này có giá trị **được database sinh sau INSERT**.
4. Hibernate có thể lấy kết quả về và gán lại cho entity bằng cơ chế phù hợp (ví dụ RETURNING hoặc SELECT).

**Lưu ý về phiên bản:** cú pháp `@Generated(event = EventType.INSERT)` là API Hibernate 6.x. Các ví dụ Hibernate cũ có thể dùng `GenerationTime.INSERT` hoặc `@Generated(GenerationTime.ALWAYS)`. Không áp dụng cú pháp từ phiên bản khác khi chưa kiểm tra thư viện Hibernate thực tế.

### 6.1. Ví dụ trường database default và readback sau INSERT

```java
package com.example.orders;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import org.hibernate.annotations.ColumnDefault;
import org.hibernate.annotations.Generated;
import org.hibernate.generator.EventType;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "description", nullable = false, length = 200)
    private String description;

    @ColumnDefault("'NEW'")
    @Generated(event = EventType.INSERT)
    @Column(
        name = "status",
        nullable = false,
        length = 24,
        insertable = false,
        updatable = false
    )
    private String status;

    @ColumnDefault("CURRENT_TIMESTAMP")
    @Generated(event = EventType.INSERT)
    @Column(
        name = "created_at",
        insertable = false,
        updatable = false
    )
    private java.time.LocalDateTime createdAt;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String description) {
        this.description = description;
    }

    public Long getId() {
        return id;
    }

    public String getDescription() {
        return description;
    }

    public String getStatus() {
        return status;
    }

    public java.time.LocalDateTime getCreatedAt() {
        return createdAt;
    }
}
```

Cách sử dụng trong transaction `RESOURCE_LOCAL`:

```java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    PurchaseOrder order =
            new PurchaseOrder("Đơn hàng kiểm thử");

    System.out.println(order.getStatus()); // null: chưa persist.

    em.persist(order);
    em.flush();

    // Hibernate biết status và createdAt là generated fields.
    // Sau khi INSERT và readback hoàn tất, các getter có thể
    // phản ánh dữ liệu database vừa tạo.
    System.out.println(order.getStatus());    // NEW
    System.out.println(order.getCreatedAt()); // DB timestamp

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
```

Các câu SELECT/RETURNING cụ thể tùy dialect; đây là **mô hình hành vi dự kiến của generated mapping**, không phải cam kết một SQL y hệt trên mọi database. Nếu transaction chưa commit, các giá trị đã được nạp lại vẫn chỉ phản ánh transaction hiện tại; chúng **không chứng minh dữ liệu đã bền vững sau commit**.

### 6.2. Vì sao chỉ khai báo `@ColumnDefault` là chưa đủ?

So sánh:

```java
// A: DDL default, không tự nói rõ cơ chế readback.
@ColumnDefault("'NEW'")
private String status;

// B: database default được dùng do không INSERT field,
// và Hibernate biết field generated sau INSERT.
@ColumnDefault("'NEW'")
@Generated(event = EventType.INSERT)
@Column(insertable = false, updatable = false)
private String status;
```

Ở A, Hibernate vẫn có thể gửi `NULL` nếu mapping/SQL không bỏ cột. Dù database có default, entity không tự được refresh. Ở B, mô hình thể hiện tường minh **nguồn giá trị nằm ở database** và **thời điểm cần đọc lại là sau INSERT**.

### 6.3. `insertable = false` và `updatable = false` có ý nghĩa gì?

`@Column(insertable = false, updatable = false)` hướng dẫn Hibernate **không đưa field vào INSERT/UPDATE** thông thường. Nó thích hợp với field mà database sở hữu giá trị như default bất biến, trigger-generated audit column, generated column.

Nó **không** biến database column thành bất biến đối với mọi writer khác và không tự sinh DEFAULT/trigger. Một câu SQL trực tiếp vẫn có thể ghi nếu database cho phép.

Nếu field **được database sinh ở INSERT nhưng sau này nghiệp vụ cần sửa**, không đặt `updatable = false` một cách máy móc. Chọn mapping và setter theo chính sách nguồn dữ liệu. Ngược lại, đừng để cả Hibernate và trigger cùng tranh quyền cập nhật một trường nếu chưa thiết kế rõ nguồn sự thật.

## 7. Trigger sinh giá trị sau INSERT hoặc UPDATE

### 7.1. Trường `updatedAt` được trigger sở hữu

Giả sử database có trigger đặt `updated_at` bằng thời gian của database mỗi khi cập nhật hàng. Entity:

```java
import java.time.LocalDateTime;

import jakarta.persistence.Column;

import org.hibernate.annotations.Generated;
import org.hibernate.generator.EventType;

@Generated(event = {EventType.INSERT, EventType.UPDATE})
@Column(
    name = "updated_at",
    insertable = false,
    updatable = false
)
private LocalDateTime updatedAt;
```

Khai báo này cho Hibernate biết trường được sinh sau các sự kiện INSERT và UPDATE. Giá trị chỉ có ý nghĩa khi schema thật có default/trigger hoặc cơ chế tương ứng tạo ra nó.

### 7.2. SQL trigger minh họa trên PostgreSQL

Ví dụ trong PostgreSQL (cú pháp đặc thù vendor):

```sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    description VARCHAR(200) NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'NEW',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE OR REPLACE FUNCTION set_purchase_order_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_purchase_orders_updated_at
BEFORE UPDATE ON purchase_orders
FOR EACH ROW
EXECUTE FUNCTION set_purchase_order_updated_at();
```

Ở đây:

- `created_at` và `updated_at` nhận default khi INSERT bỏ cột.
- Mỗi câu UPDATE chạy trên hàng kích hoạt trigger `BEFORE UPDATE` đặt `updated_at`.
- `CURRENT_TIMESTAMP` trong PostgreSQL gắn với thời điểm bắt đầu transaction; nếu cần thời gian đồng hồ biến động theo thời gian thực, PostgreSQL có các hàm như `clock_timestamp()` với semantics khác. Cần chọn theo yêu cầu kiểm toán.
- Ví dụ SQL dùng `TIMESTAMPTZ`; khi mapping sang Java nên lựa chọn kiểu `Instant` hoặc kiểu thời gian phù hợp với chính sách timezone.
- Với `@Generated(event={INSERT,UPDATE})`, Hibernate có cơ sở đọc lại field sau các lệnh SQL tương ứng do ORM phát ra.

Nếu trigger không tồn tại trong database thật, `@Generated` không có khả năng tự tạo giá trị đó. **Annotation readback không thay thế DDL trigger.**

### 7.3. Vì sao field có thể vẫn cũ ngay sau setter?

```java
PurchaseOrder order = em.find(PurchaseOrder.class, orderId);

LocalDateTime before = order.getUpdatedAt();
order.changeDescription("Đã sửa");

// Chưa có nghĩa trigger đã chạy.
LocalDateTime immediately = order.getUpdatedAt();
```

Trong lúc chỉ đổi property Java:

1. Hibernate ghi nhận state dirty của managed entity.
2. `updated_at` ở database thường **chưa đổi** cho đến khi UPDATE thực sự được thực thi.
3. Vì vậy không có giá trị timestamp mới để Hibernate đọc lại.

Khi `flush` khiến UPDATE chạy và mapping khai báo đúng generated event, Hibernate có thể đồng bộ trường mới trở lại entity. Nếu không có generated mapping, entity có thể giữ giá trị cũ cho đến `refresh` hoặc lần tải trong context mới.

### 7.4. `@Generated(event = INSERT)` khác `INSERT + UPDATE`

Nếu một giá trị chỉ được tạo một lần khi INSERT, chọn:

```java
@Generated(event = EventType.INSERT)
private Instant createdAt;
```

Nếu trường được DB sinh lại ở mọi UPDATE phù hợp, chọn:

```java
@Generated(event = {EventType.INSERT, EventType.UPDATE})
private Instant updatedAt;
```

Đừng đánh dấu một trường chỉ có default khi INSERT như thể nó được database **sinh lại ở UPDATE** nếu không có cơ chế tương ứng. Điều này làm Hibernate phải xử lý readback không cần thiết và khiến người đọc mapping hiểu sai trách nhiệm dữ liệu.

## 8. `@CreationTimestamp` và `@UpdateTimestamp`: ORM chủ động tạo timestamp

Hibernate cung cấp hai annotation chuyên biệt:

- `@CreationTimestamp`: timestamp tạo entity.
- `@UpdateTimestamp`: timestamp trong lifecycle update.

Chúng khác với một DB default thuần túy bởi **Hibernate chủ động tham gia điều khiển việc sinh timestamp**, với nguồn thời gian được cấu hình.

### 8.1. Dùng đồng hồ của JVM

```java
import java.time.Instant;

import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;

@CreationTimestamp
private Instant createdAt;

@UpdateTimestamp
private Instant updatedAt;
```

Trong Hibernate 6.x, mặc định các annotation này dùng nguồn thời gian JVM trong cấu hình thông dụng. Hibernate quản lý timestamp theo sự kiện insert/update phù hợp.

Ưu điểm:

- Không cần trigger riêng để tạo timestamp.
- Entity và ORM có thể biết giá trị mà chúng chủ động sinh.
- Cách viết tương đối ngắn gọn.

Nhược điểm tiềm năng:

- Nếu nhiều JVM lệch đồng hồ, các timestamp được tạo có thể không đồng nhất với thời gian database.
- Những writer SQL trực tiếp ngoài Hibernate **không tự chạy annotation Java**.
- Semantics chính xác của “updated” là sự kiện ORM phát UPDATE, không nhất thiết tương ứng mọi chỉnh sửa nghiệp vụ ở ngoài database.

### 8.2. Dùng đồng hồ database với `SourceType.DB`

Hibernate 6.x hỗ trợ chọn nguồn thời gian:

```java
import java.time.Instant;

import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.SourceType;
import org.hibernate.annotations.UpdateTimestamp;

@CreationTimestamp(source = SourceType.DB)
private Instant createdAt;

@UpdateTimestamp(source = SourceType.DB)
private Instant updatedAt;
```

Cấu hình `source = SourceType.DB` yêu cầu Hibernate lấy giá trị thời gian từ database khi sinh timestamp theo lifecycle; việc này khác với để JVM gọi `Instant.now()`.

**Phân biệt ba lựa chọn:**

| Cách làm | Ai quyết định thời điểm? | Writer ngoài Hibernate được áp dụng? | Cần schema default/trigger riêng? |
|---|---|---|---|
| `@CreationTimestamp` mặc định | Hibernate/JVM | Không | Không cần |
| `@CreationTimestamp(source = DB)` | Hibernate yêu cầu DB sinh thời gian | Không tự áp dụng cho writer ngoài ORM | Không nhất thiết |
| Database `DEFAULT CURRENT_TIMESTAMP` | Schema của database | Có, nếu INSERT bỏ cột | **Có** |
| Trigger `BEFORE UPDATE` | Database trigger | Có, nếu trigger được kích hoạt | **Có** |
| `@PrePersist` đặt timestamp Java | Callback ứng dụng/JPA | Không | Không cần |

Một annotation `@UpdateTimestamp(source=DB)` **không tự tạo trigger** để mọi ứng dụng khác cập nhật `updated_at`. Nếu yêu cầu *mọi writer trong hệ thống* đều có cùng quy tắc cập nhật, database trigger hoặc quy trình ghi thống nhất cần được thiết kế riêng.

### 8.3. Không trộn hai cơ chế sinh timestamp vô ý

Ví dụ vừa có:

```java
@UpdateTimestamp
private Instant updatedAt;
```

vừa có trigger database tự gán `updated_at` có thể khiến hai bên áp dụng thời gian khác nhau. SQL UPDATE do Hibernate gửi có thể mang giá trị của JVM, sau đó trigger thay bằng thời gian DB; nếu mapping không phản ánh DB-generated field, entity Java có thể giữ giá trị khác với database.

Nên chọn một **nguồn sự thật**: Hibernate-managed timestamp hoặc DB-managed timestamp. Nếu cần kết hợp vì legacy, phải mô tả rõ thứ tự xử lý và kiểm tra readback.

## 9. Generated/computed column và `@GeneratedColumn`

Một loại khác của trường tự sinh là **cột được database tính từ những cột khác**. Ví dụ `line_total` = `quantity * unit_price`.

Một schema hỗ trợ generated columns có thể có cú pháp:

```sql
CREATE TABLE invoice_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(19, 2) NOT NULL,
    line_total DECIMAL(21, 2)
        GENERATED ALWAYS AS (quantity * unit_price) STORED
);
```

Đây là ví dụ theo họ cú pháp được một số DB hỗ trợ; không phải SQL portable cho tất cả dialect. Database có thể cung cấp **virtual** hoặc **stored** generated column với ngữ nghĩa lưu/index khác nhau.

### 9.1. Ánh xạ bằng Hibernate `@GeneratedColumn`

Ở các phiên bản Hibernate có hỗ trợ `org.hibernate.annotations.GeneratedColumn`:

```java
import java.math.BigDecimal;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

import org.hibernate.annotations.GeneratedColumn;

@Entity
public class InvoiceLine {

    @Id
    private Long id;

    private int quantity;

    @Column(precision = 19, scale = 2)
    private BigDecimal unitPrice;

    @GeneratedColumn("quantity * unit_price")
    private BigDecimal lineTotal;
}
```

`@GeneratedColumn` mô tả generated column trong schema do Hibernate quản lý và cho Hibernate biết giá trị cần được nạp từ database sau các thao tác liên quan. Khả năng sinh đúng DDL và cách đọc lại phụ thuộc Hibernate version/dialect; khi dùng migration tool cần bảo đảm bảng thực tế có cột generated tương ứng.

Với schema đã được quản lý thủ công, một lựa chọn khác là mapping cột read-only và dùng `@Generated` cho các sự kiện làm thay đổi giá trị:

```java
@Generated(event = {EventType.INSERT, EventType.UPDATE})
@Column(name = "line_total", insertable = false, updatable = false)
private BigDecimal lineTotal;
```

Ở cách này, database phải có generated column/trigger sinh `line_total` thật sự.

### 9.2. Generated column khác `@Formula`

| Tiêu chí | Generated column | `@Formula` |
|---|---|---|
| Có cột được khai báo trong schema? | **Có** | Không cần |
| Database định nghĩa công thức ở đâu? | Trong DDL generated column | Trong chuỗi SQL mapping `@Formula` |
| Được tính khi nào? | Theo cơ chế generated column của DB | Khi thực thi SELECT chứa expression |
| Có thể được index? | Tùy DB, loại generated column | Thường cần expression index/thiết kế riêng |
| Hibernate có thể đọc lại sau INSERT/UPDATE? | Có nếu mapping generated đúng | Formula cần lần SELECT/refresh phù hợp; không mặc định recompute ngay sau setter |
| Mức portable | Phụ thuộc DDL/dialect | Phụ thuộc biểu thức SQL/dialect |

`@Formula("quantity * unit_price")` không tạo generated column trong database. Nó ánh xạ một scalar expression dùng khi **đọc**. Ngược lại, generated column là một thành phần schema mà DB quản lý.

### 9.3. Precision và null của giá trị tính

Phép `DECIMAL * INTEGER` có thể có precision và scale khác tùy database. Trường Java `BigDecimal` nên khớp ngữ nghĩa kiểu SQL. Nếu `quantity` hoặc `unit_price` nullable, công thức có thể trả NULL; nếu muốn zero hay một chính sách fallback, định nghĩa rõ trong công thức/DDL.

Không giả định Hibernate luôn giữ nguyên nanosecond đối với timestamp hoặc scale đối với decimal sau round-trip. Kiểu JDBC và độ chính xác storage có thể khiến giá trị được làm tròn/cắt.

## 10. Khóa chính được sinh: trường hợp đặc biệt của readback

ID cũng là một giá trị được sinh tự động, nhưng có vai trò đặc biệt trong persistence identity.

### 10.1. `GenerationType.IDENTITY`

```java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
```

Database sinh ID khi INSERT. Hibernate cần lấy ID để phân biệt entity managed và tạo liên kết FK; việc lấy khóa có thể dùng JDBC generated keys hoặc cơ chế được dialect hỗ trợ.

Với `IDENTITY`, INSERT thường có thể được thực thi sớm để lấy ID. Không coi việc `id != null` là bằng chứng transaction đã commit, vì rollback vẫn có thể diễn ra.

### 10.2. `GenerationType.SEQUENCE`

```java
@Id
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "order_seq_gen"
)
@SequenceGenerator(
    name = "order_seq_gen",
    sequenceName = "order_seq",
    allocationSize = 50
)
private Long id;
```

Hibernate có thể lấy trước một hoặc một nhóm giá trị sequence, rồi trì hoãn INSERT đến flush. Khi đó ID đã có trong Java nhưng row chưa chắc đã được ghi xuống database.

### 10.3. Khóa chính không giống các field default thông thường

Hibernate phải nhận diện entity bằng primary key để quản lý persistence context. Vì vậy cơ chế lấy generated ID là bắt buộc trong các mapping phù hợp. Điều này **không** kéo theo việc Hibernate tự đọc mọi cột có DEFAULT hoặc trigger nếu không được khai báo.

Không sử dụng `@Generated` lên ID thay thế tùy tiện cơ chế `@GeneratedValue`/identifier generator phù hợp. Identifier generation có hợp đồng riêng.

## 11. `@Version`: generated value phục vụ optimistic locking

`@Version` cũng là field thường được cập nhật tự động trong lifecycle:

```java
import jakarta.persistence.Version;

@Version
private Long version;
```

Với versioning do Hibernate quản lý, khi update managed entity:

```sql
UPDATE purchase_orders
SET description = ?, version = ?
WHERE id = ? AND version = ?;
```

Hibernate dùng version cũ trong `WHERE` để phát hiện thay đổi đồng thời và quản lý version mới. Đây không phải một SQL `DEFAULT` bình thường và cũng không đồng nghĩa trigger database.

Một số hệ thống legacy có version do DB trigger sinh. Mapping cần thể hiện rằng version thực sự do database quản lý, và cơ chế optimistic locking phải đọc version mới đúng thời điểm. Đừng vừa yêu cầu Hibernate tăng version vừa để trigger tự sửa theo quy tắc khác mà không kiểm soát sự nhất quán.

**Version không phải timestamp kiểm toán**: mặc dù cả hai có thể được cập nhật ở thời điểm ghi, version phục vụ phát hiện cạnh tranh; `updated_at` phục vụ thông tin thời gian. Không thay `@Version` bằng một timestamp trigger chỉ vì nó thay đổi khi UPDATE.

## 12. Thời điểm dữ liệu thực sự trở lại entity

Có ít nhất năm tình huống cần phân biệt.

### 12.1. Giá trị được Java gán trước khi persist

```java
Order order = new Order("Đơn thử");
System.out.println(order.getStatus()); // NEW nếu constructor gán.
```

Ứng dụng biết giá trị ngay, không cần round-trip.

### 12.2. Giá trị DB-generated được Hibernate nhận diện

```java
@Generated(event = EventType.INSERT)
@Column(insertable = false, updatable = false)
private String referenceCode;
```

Khi Hibernate phát INSERT, mapping cho biết cần nạp lại `referenceCode` sau sự kiện tương ứng. Hibernate có thể dùng RETURNING/JDBC hoặc SELECT bổ sung, tùy môi trường.

### 12.3. Database sinh giá trị nhưng Hibernate không biết

```java
@Column(name = "status")
private String status;
```

Nếu database có trigger/default nhưng Hibernate không được cấu hình generated property, object managed có thể vẫn mang giá trị cũ hoặc null.

Cần dùng `refresh` có chủ đích hoặc đọc bằng context mới khi cần đồng bộ.

### 12.4. `em.refresh(entity)`

Ví dụ:

```java
EntityTransaction tx = em.getTransaction();
tx.begin();

try {
    PurchaseOrder order =
            em.find(PurchaseOrder.class, orderId);

    order.changeDescription("Đã xử lý");

    em.flush();       // DB nhận UPDATE, trigger chạy nếu có.
    em.refresh(order); // Nạp lại state từ DB.

    System.out.println(order.getUpdatedAt());

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
```

**Thứ tự quan trọng:** nếu gọi `refresh` khi còn những thay đổi Java chưa được flush, các giá trị chưa lưu có thể bị ghi đè bởi state trong database. Vì vậy chỉ refresh sau khi đã quyết định đồng bộ các thay đổi cần giữ hoặc khi chủ ý muốn hủy state Java hiện tại.

### 12.5. Đọc lại trong persistence context mới

```java
EntityManager first = emf.createEntityManager();
// ... Thực hiện transaction và commit.
// ... Đóng first.

EntityManager second = emf.createEntityManager();

try {
    PurchaseOrder fresh =
            second.find(PurchaseOrder.class, orderId);
    System.out.println(fresh.getUpdatedAt());
} finally {
    second.close();
}
```

Context mới loại bỏ ảnh hưởng first-level cache cũ, nhưng cần nhớ second-level cache có thể giữ state theo cấu hình. Khi đánh giá độ mới dữ liệu, xét cả cache và các writer ngoài Hibernate.

## 13. `RETURNING`, JDBC generated keys và SELECT bổ sung

Khi Hibernate cần giá trị database vừa sinh, nó có thể lựa chọn chiến lược đọc lại khác nhau:

```sql
-- Cách 1: SQL có RETURNING, với dialect hỗ trợ.
INSERT INTO purchase_orders (description)
VALUES (?)
RETURNING id, status, created_at;
```

```sql
-- Cách 2: INSERT rồi SELECT theo primary key.
INSERT INTO purchase_orders (description)
VALUES (?);

SELECT status, created_at
FROM purchase_orders
WHERE id = ?;
```

Một số database/driver có cách khác để trả generated keys hoặc các giá trị do database sinh. Đây là **SQL minh họa**, không có bảo đảm Hibernate sẽ chọn đúng một trong hai chuỗi như viết ở trên.

Đôi khi câu INSERT trả ID nhưng **không trả mọi cột trigger-generated**, vì vậy Hibernate cần thêm SELECT. Khi tối ưu hiệu năng, quan sát:

- SQL Hibernate thực sự phát.
- Round-trip JDBC giữa ứng dụng và database.
- Loại generator và dialect.
- Những field được đánh dấu generated ở INSERT/UPDATE.
- Driver có hỗ trợ lấy nhiều generated values không.
- Cache và flush mode.

Không nên giả định thêm `@Generated` là “miễn phí” về SQL; nó có thể tạo thêm truy vấn sau INSERT/UPDATE để lấy giá trị.

## 14. `@PrePersist`/`@PreUpdate`: default ở tầng entity lifecycle

Jakarta Persistence có lifecycle callback:

```java
import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;

@Entity
public class AuditRecord {

    @Id
    @GeneratedValue
    private Long id;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @PrePersist
    void beforeInsert() {
        Instant now = Instant.now();
        createdAt = now;
        updatedAt = now;
    }

    @PreUpdate
    void beforeUpdate() {
        updatedAt = Instant.now();
    }
}
```

Callback này thay đổi **entity Java trước khi ORM ghi SQL**. Nó không phải database DEFAULT hay trigger.

Ưu điểm:

- Code Java thấy giá trị do chính callback gán theo lifecycle.
- Không cần database trả cột generated để biết giá trị mới.
- Dùng được với nhiều database theo API JPA chuẩn.

Lưu ý:

- `Instant.now()` sử dụng đồng hồ JVM; trong code nghiệp vụ yêu cầu test với `Clock` nên cân nhắc service/auditing component thay vì gọi đồng hồ tĩnh trong entity.
- Callback không chạy khi một writer khác cập nhật database trực tiếp.
- `@PreUpdate` gắn với sự kiện update theo quy tắc ORM, không phải mỗi lần gọi setter. Nếu không có cập nhật thực sự, callback update có thể không chạy.
- Không đặt các thao tác nặng, I/O hoặc truy vấn ngoài mục đích lifecycle vào callback nếu không có thiết kế rõ ràng.
- Không dùng cùng lúc callback sửa `updated_at` và trigger DB sửa cùng cột mà không giải thích quyền ưu tiên.

## 15. Giá trị mặc định khi thực thể bị cập nhật

SQL `DEFAULT` trên cột thường phục vụ **INSERT**, không phải tự “tái áp dụng” cho mọi UPDATE.

Ví dụ:

```sql
CREATE TABLE tasks (
    id BIGINT PRIMARY KEY,
    status VARCHAR(24) DEFAULT 'NEW'
);
```

Khi UPDATE:

```sql
UPDATE tasks
SET status = NULL
WHERE id = 1;
```

Database thường sẽ đặt `NULL` (hoặc từ chối nếu NOT NULL); nó **không** tự thay NULL bằng `'NEW'` chỉ vì cột có DEFAULT.

Nếu cần `updated_at` thay đổi ở mọi UPDATE, có các lựa chọn:

1. ORM sinh timestamp bằng `@UpdateTimestamp`.
2. Database trigger sinh timestamp.
3. SQL/ứng dụng đặt giá trị tại mỗi lệnh UPDATE.
4. Generated column khi giá trị là biểu thức tính từ những cột khác và DB hỗ trợ.

Chọn theo nguồn sự thật và các writer có quyền sửa bảng.

### 15.1. `@DynamicUpdate` làm gì?

`@DynamicUpdate` có thể khiến Hibernate chỉ đưa các cột dirty vào SQL UPDATE, thay vì một tập cột cố định lớn hơn.

```java
import org.hibernate.annotations.DynamicUpdate;

@Entity
@DynamicUpdate
public class PurchaseOrder {
    // ...
}
```

Điều này có thể làm giảm việc ghi các cột không thay đổi trong một số workload, nhưng:

- Nó **không tự động tạo DB default** khi UPDATE.
- Trigger `BEFORE UPDATE` vẫn có thể chạy khi một dòng được UPDATE, bất kể số cột trong SET.
- Những trường được DB sinh vẫn cần mapping/readback phù hợp.
- SQL động có thể ảnh hưởng statement reuse và batching.
- Không nên dùng `@DynamicUpdate` để chữa một mapping generated field sai.

### 15.2. Tác động của dirty checking tới trigger

Nếu managed entity không dirty, Hibernate có thể không phát UPDATE. Khi đó trigger `BEFORE UPDATE` **không có lệnh UPDATE để kích hoạt**. Vì vậy `updated_at` được trigger sở hữu không nhất thiết thay đổi chỉ vì ứng dụng “đã đi qua một transaction” hoặc đã gọi một method.

Nếu muốn ghi thời điểm “người dùng đã xác nhận nhưng dữ liệu không đổi”, cần thể hiện **sự kiện nghiệp vụ** thành một thao tác ghi được xác định rõ, không dựa vào một setter gán lại cùng giá trị và mong Hibernate chắc chắn UPDATE.

## 16. Mô hình nhất quán: ai sở hữu trường?

Không phải mọi field cần cùng nguồn sinh. Một chính sách rõ ràng cho hệ thống đa dịch vụ có thể phân công:

| Field | Nguồn sự thật thường hợp lý | Quy tắc ghi | Cách đồng bộ Java |
|---|---|---|---|
| `id` | Database identity/sequence hoặc UUID được ứng dụng gán | Qua identifier generator | Hibernate lấy ID theo mapping |
| `status` là trạng thái nghiệp vụ | Domain/service Java | Đặt giá trị rõ trước persist/update | Có ngay trong entity |
| `createdAt` | ORM clock hoặc DB clock | Một lần ở INSERT | Annotation timestamp hoặc generated mapping |
| `updatedAt` | ORM hoặc DB trigger | Khi update hợp lệ | `@UpdateTimestamp` hoặc `@Generated(UPDATE)` |
| `lineTotal` | DB generated column hoặc domain calculation | Không ghi trực tiếp vào cột generated | Mapping generated/readback hoặc Java getter |
| `version` | Hibernate optimistic locking | ORM quản lý tăng version | `@Version` |
| `externalRef` do hệ thống khác cấp | API/service tích hợp | Validate trước persist | Entity có giá trị từ ứng dụng |
| `serverCode` trigger cấp | DB trigger | Bỏ cột khi INSERT | `@Generated(INSERT)` hoặc refresh |

Điểm cốt lõi: **mỗi trường nên có một chính sách nhất quán về quyền tạo, quyền sửa và quyền đọc lại**.

### 16.1. Những tổ hợp thường nên tránh

- Field có Java initializer cố định nhưng schema trigger luôn ghi đè bằng giá trị khác.
- `@UpdateTimestamp` từ JVM cùng với trigger đặt timestamp của DB mà không có readback.
- `@ColumnDefault` nhưng Hibernate luôn INSERT NULL, rồi kỳ vọng default được dùng.
- `@DynamicInsert` nhưng không kiểm tra default/NOT NULL đã có trên database thật.
- Cột computed/generated do database sở hữu nhưng service lại gọi setter như thể đó là cột bình thường.
- Field được trigger thay đổi từ SQL trực tiếp ở service khác nhưng entity/second-level cache không có chiến lược làm mới.

## 17. First-level cache, second-level cache và giá trị cũ

### 17.1. First-level cache giữ managed instance

```java
PurchaseOrder first = em.find(PurchaseOrder.class, id);

// Một dịch vụ khác cập nhật updated_at trong DB.

PurchaseOrder again = em.find(PurchaseOrder.class, id);
```

Nếu entity vẫn managed trong cùng persistence context, `again` thường là cùng Java instance. Giá trị `updatedAt` có thể cũ. `find` lần hai **không buộc database tải lại**.

Để đọc lại có chủ đích:

```java
em.refresh(first);
```

`refresh` có thể gây SELECT và ghi đè state chưa flush. Dùng khi đã hiểu transaction và nhu cầu độ mới.

### 17.2. Cache cấp hai cũng cần chính sách invalidation

Nếu Hibernate second-level cache giữ trạng thái entity, một trigger/batch update thực hiện từ ngoài Hibernate không mặc nhiên thông báo chính xác cho mọi cache entry. Khi yêu cầu data freshness cao, cần quyết định chiến lược cập nhật, TTL, evict/refresh hoặc hạn chế cache ở entity có trường thay đổi bên ngoài.

Một generated field được Hibernate nạp đúng ngay sau INSERT do chính ORM phát **không giải quyết toàn bộ vấn đề cache khi writer khác thay đổi bản ghi sau đó**.

### 17.3. Transaction isolation ảnh hưởng “đọc mới”

Ngay cả khi ứng dụng gọi `refresh` hoặc dùng context mới, kết quả vẫn chịu ảnh hưởng transaction isolation, thời điểm commit của writer khác và cơ chế MVCC của database. Không thể suy rằng một SELECT luôn thấy thay đổi chưa commit từ transaction khác.

## 18. Bulk UPDATE, native SQL và trigger: Hibernate có biết giá trị mới không?

Một truy vấn bulk có thể cập nhật nhiều hàng trực tiếp:

```java
int updated = em.createQuery(
        """
        update PurchaseOrder o
        set o.description = :description
        where o.status = :status
        """
    )
    .setParameter("description", "Đang xử lý")
    .setParameter("status", "NEW")
    .executeUpdate();
```

Bulk JPQL DML không đi qua dirty checking từng entity theo cách setter trên managed entity. Nếu database trigger sinh `updated_at` cho các hàng bị UPDATE, Hibernate **không tự chạy cơ chế generated-field readback cho từng managed object đã có trong context** như một entity update thông thường.

Nếu persistence context đã nạp các order này, state Java có thể bị stale. Các biện pháp tùy tình huống:

- `em.clear()` sau khi xử lý pending changes phù hợp, rồi tải lại.
- `em.refresh(entity)` đối với từng entity cần đọc mới.
- Dùng context mới trong một đơn vị công việc khác.
- Cấu hình/bảo trì cache cấp hai khi chạy bulk/native DML.

**Không tự động gọi `clear()` khi còn thay đổi chưa flush**, vì có thể làm mất pending changes ở context.

SQL native hoặc batch job ngoài Hibernate cũng có vấn đề tương tự. Điều đó không làm trigger sai; chỉ cho thấy ORM không quan sát mọi writer.

## 19. Rollback sau khi giá trị generated đã được đọc về

Giả sử:

```java
tx.begin();

PurchaseOrder order = new PurchaseOrder("Đơn rollback");
em.persist(order);
em.flush();

// Hibernate đã lấy status='NEW', createdAt=...
System.out.println(order.getStatus());

tx.rollback();
```

Sau rollback:

- Java object có thể vẫn giữ ID, status và timestamp đã được gán/readback.
- Row vừa insert có thể **không tồn tại** trong database vì transaction không commit.
- Giá trị identity/sequence đã cấp có thể không được tái sử dụng.
- Persistence context sau transaction thất bại/rollback không nên được tiếp tục dùng như một nguồn trạng thái chắc chắn của database.

Vì vậy **giá trị đã “đồng bộ trở lại Java” không đồng nghĩa row đã được commit thành công**. Nên kết thúc đơn vị công việc sau rollback, tránh đưa entity cũ vào quy trình tiếp theo mà không xác minh lại trạng thái.

## 20. Thực hành trọn vẹn với default và trigger

Để thấy rõ sự khác nhau, sử dụng một entity với các field được database sở hữu. Giả định schema có default/trigger như mục 7, và application sử dụng Hibernate ORM 6.x/Jakarta Persistence.

### 20.1. Entity mô hình hóa nguồn giá trị từ DB

```java
package com.example.orders;

import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import org.hibernate.annotations.Generated;
import org.hibernate.generator.EventType;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "description", nullable = false, length = 200)
    private String description;

    @Generated(event = EventType.INSERT)
    @Column(
        name = "status",
        nullable = false,
        insertable = false,
        updatable = false
    )
    private String status;

    @Generated(event = EventType.INSERT)
    @Column(
        name = "created_at",
        insertable = false,
        updatable = false
    )
    private Instant createdAt;

    @Generated(event = {EventType.INSERT, EventType.UPDATE})
    @Column(
        name = "updated_at",
        insertable = false,
        updatable = false
    )
    private Instant updatedAt;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String description) {
        this.description = description;
    }

    public Long getId() {
        return id;
    }

    public String getDescription() {
        return description;
    }

    public String getStatus() {
        return status;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }

    public void changeDescription(String next) {
        if (next == null || next.isBlank()) {
            throw new IllegalArgumentException("Description is required");
        }
        description = next;
    }
}
```

Ví dụ này chọn một quy tắc đơn giản: `status` chỉ có default lúc tạo và không cho Hibernate sửa. Một hệ thống thật cần chuyển trạng thái nghiệp vụ không nên giữ `status` mãi ở read-only nếu trạng thái phải đổi. Khi đó cân nhắc tách field mặc định với field trạng thái được ứng dụng quản lý hoặc thiết kế nguồn cập nhật phù hợp.

Timestamp dùng `Instant` để chỉ một thời điểm trên trục UTC. Khi database sử dụng `TIMESTAMPTZ`, cách JDBC/Hibernate ánh xạ và timezone storage cần được cấu hình/kiểm tra theo dialect/version. Đừng trộn ngày giờ địa phương không có timezone với `Instant` mà không có quy ước chuyển đổi rõ.

### 20.2. Service dùng transaction và quan sát từng giai đoạn

```java
package com.example.orders;

import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;

public final class PurchaseOrderService {

    private final EntityManagerFactory emf;

    public PurchaseOrderService(EntityManagerFactory emf) {
        this.emf = emf;
    }

    public Long create() {
        EntityManager em = emf.createEntityManager();
        EntityTransaction tx = em.getTransaction();

        try {
            tx.begin();

            PurchaseOrder order =
                    new PurchaseOrder("Đơn hàng demo");

            logState("NEW", order);

            em.persist(order);
            logState("AFTER persist", order);

            em.flush();
            logState("AFTER flush", order);

            tx.commit();

            logState("AFTER commit", order);

            return order.getId();
        } catch (RuntimeException ex) {
            if (tx.isActive()) {
                tx.rollback();
            }
            throw ex;
        } finally {
            em.close();
        }
    }

    public void update(Long id) {
        EntityManager em = emf.createEntityManager();
        EntityTransaction tx = em.getTransaction();

        try {
            tx.begin();

            PurchaseOrder order =
                    em.find(PurchaseOrder.class, id);

            if (order == null) {
                throw new IllegalArgumentException("Order not found");
            }

            logState("LOADED", order);

            order.changeDescription("Đơn hàng cập nhật");
            logState("AFTER setter", order);

            em.flush(); // UPDATE + trigger nếu state dirty.
            logState("AFTER flush", order);

            // Có thể thêm em.refresh(order) nếu cần
            // xác minh lại bằng SELECT thực sự.
            em.refresh(order);
            logState("AFTER refresh", order);

            tx.commit();
        } catch (RuntimeException ex) {
            if (tx.isActive()) {
                tx.rollback();
            }
            throw ex;
        } finally {
            em.close();
        }
    }

    private static void logState(
            String stage, PurchaseOrder order) {

        System.out.printf(
            "%s | id=%s status=%s createdAt=%s updatedAt=%s%n",
            stage,
            order.getId(),
            order.getStatus(),
            order.getCreatedAt(),
            order.getUpdatedAt()
        );
    }
}
```

Trong môi trường `RESOURCE_LOCAL`, code minh họa quản lý transaction và EntityManager rõ ràng. Với Spring/JTA, framework/container thường quản lý transaction/context thay cho service tự mở/đóng.

### 20.3. Đọc dòng thời gian

| Mốc | Java entity | Database | SQL có thể thấy |
|---|---|---|---|
| Sau `new` | `id/status/timestamps` null | Chưa có row mới | Không |
| Sau `persist` | Entity managed; ID có thể đã có | IDENTITY có thể đã INSERT | INSERT sớm hoặc chưa, tùy cơ chế |
| Sau `flush` | Generated fields có thể được nạp lại đúng mapping | DEFAULT/trigger đã chạy trong transaction | INSERT và có thể RETURNING/SELECT |
| Sau `commit` | Giá trị đã nạp vẫn còn ở object | Row đã commit nếu transaction thành công | Có thể không thêm SQL đọc |
| Sau setter trên managed entity | `description` đổi, `updatedAt` có thể vẫn cũ | Chưa có UPDATE mới nếu chưa flush | Thường chưa |
| Sau flush của UPDATE | `updatedAt` được đồng bộ nếu generated mapping hoạt động | Trigger đã chạy khi SQL UPDATE | UPDATE, có thể SELECT readback |
| Sau `refresh` | Trạng thái đọc từ DB lại | Giá trị cùng transaction tại thời điểm SELECT | SELECT |
| Sau rollback | Object có thể giữ giá trị readback | DML trong transaction được hoàn tác | SQL đã chạy trước đó vẫn có thể thấy trong log |

Không dựa vào việc `updatedAt` **chắc chắn khác** timestamp trước ở mọi test: nếu thời gian database có độ phân giải giới hạn hoặc hai update ở cùng transaction dùng `CURRENT_TIMESTAMP` (PostgreSQL), hai giá trị có thể bằng nhau. Khi test, nên kiểm tra ngữ nghĩa và precision phù hợp hoặc sử dụng cơ chế tạo giá trị phù hợp với test.

## 21. Cách quan sát SQL và giá trị sinh

Trong một ứng dụng demo, Hibernate có thể bật logging SQL:

```xml
<property name="hibernate.show_sql" value="true"/>
<property name="hibernate.format_sql" value="true"/>
<property name="hibernate.use_sql_comments" value="true"/>
<property name="hibernate.generate_statistics" value="true"/>
```

Khi cần biết bind parameters, Hibernate 6.x dùng logger category như `org.hibernate.orm.jdbc.bind` ở mức TRACE với backend logging tương ứng. Không in thông tin nhạy cảm ra log sản xuất.

### 21.1. Những tín hiệu nên ghi trong bài thực nghiệm

- ID và trạng thái `em.contains(entity)`.
- Field Java **ngay sau constructor**, **sau persist**, **sau flush**, **sau refresh**.
- Transaction active/commit/rollback.
- SQL INSERT có hay không có những cột default.
- SQL UPDATE có cột `updated_at` hay DB trigger tự tạo nó.
- Hibernate có phát SELECT bổ sung hoặc dùng RETURNING để lấy generated field.
- Kết quả đọc trong persistence context mới sau commit.

### 21.2. Không đếm SELECT một cách máy móc

Nếu Hibernate đã đọc giá trị generated qua RETURNING, có thể không cần SELECT sau đó. Nếu dialect không hỗ trợ cách lấy cần thiết, Hibernate có thể SELECT bổ sung. Nếu gọi `em.refresh`, thường có thêm SELECT. Nếu dùng first-level cache, `em.find` lần hai có thể **không** SELECT.

Chỉ một dòng SQL không cho biết toàn bộ vòng đời; cần đối chiếu mapping, transaction và context.

## 22. Các sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Cho rằng `@ColumnDefault` tự gán field Java | `new Entity().getStatus()` vẫn null | Constructor/callback nếu Java sở hữu; generated mapping nếu DB sở hữu |
| Tin rằng SQL DEFAULT chạy khi INSERT NULL | Default không được áp dụng trong nhiều DB; NOT NULL có thể lỗi | Omit cột bằng mapping phù hợp hoặc `@DynamicInsert` |
| Bật `@DynamicInsert` rồi nghĩ entity được readback | DB có giá trị mới nhưng Java field có thể cũ/null | `@Generated` hoặc `refresh` |
| Dùng `int` để biểu diễn “không cung cấp số lượng” | `0` vẫn có thể vào INSERT | Dùng `Integer` nếu cần phân biệt absent với zero |
| Gán Java default rồi kỳ vọng DB default ghi đè | SQL gửi giá trị Java, default không áp dụng | Chọn một nguồn sự thật hoặc bỏ cột có chủ đích |
| Đặt `insertable=false` nhưng DB không có default/trigger | Row có thể lỗi NOT NULL hoặc field null | Đồng bộ schema thực tế với mapping |
| Dùng `@Generated(INSERT)` cho field do trigger sinh khi UPDATE | Giá trị sau update có thể stale | Khai báo đúng event INSERT/UPDATE |
| Dùng `@Generated(UPDATE)` mà DB không sinh lại | Readback thừa, semantic sai | Chỉ khai báo event thực tế |
| Thấy `flush` và cho rằng đã commit | Có thể rollback sau khi SQL chạy | Phân biệt flush với commit |
| Sau setter đọc `updatedAt` và mong trigger đã chạy | Chưa SQL UPDATE thì chưa có trigger | Flush/commit theo transaction, readback khi cần |
| Gọi `refresh` trước flush không có chủ đích | Có thể mất pending changes | Flush trước hoặc chỉ refresh khi muốn bỏ state Java |
| Dùng `@UpdateTimestamp` cùng trigger không rõ ưu tiên | JVM/DB có thể tạo giá trị khác nhau | Chọn DB hoặc ORM làm owner |
| Dùng timestamp trigger làm `@Version` không cấu hình phù hợp | Optimistic locking có thể sai | Thiết kế version generator rõ ràng |
| Dùng `@DynamicUpdate` để mong DEFAULT chạy lại | DEFAULT thường chỉ phục vụ INSERT | Trigger hoặc generator/update logic rõ |
| Bulk UPDATE rồi đọc entity đã managed | Context có thể cũ | Refresh/clear/reload, quản lý cache |
| Cho rằng `@Generated` xử lý mọi writer ngoài Hibernate | Cache/entity vẫn có thể stale sau external SQL | Định nghĩa cơ chế invalidation/freshness |
| Test timestamp bằng `assertNotEquals` sau hai update sát nhau | Precision/semantics DB có thể tạo cùng timestamp | Test với ngữ nghĩa/độ phân giải phù hợp |
| Sử dụng SQL vendor-specific như SQL portable | Lỗi schema/mapping khi đổi DB | Kiểm tra dialect, migration và integration test |

## 23. Quy trình lựa chọn giải pháp

Khi gặp một field cần sinh tự động, đặt ra các câu hỏi sau:

**Bước 1 — Ai phải sinh giá trị?** Nếu chỉ ứng dụng Java cần giá trị và muốn biết ngay khi tạo object, constructor hoặc service/callback phù hợp. Nếu mọi writer phải tuân theo cùng quy tắc, database default/trigger/generated column đáng cân nhắc.

**Bước 2 — Sinh ở sự kiện nào?** Chỉ INSERT, mọi UPDATE, hay khi một cột nguồn thay đổi? Việc này quyết định cơ chế DDL và `@Generated(event=...)`.

**Bước 3 — Hibernate có được ghi vào cột không?** Nếu DB sở hữu hoàn toàn, dùng mapping không ghi vào cột. Nếu ứng dụng được phép đổi giá trị, không vô hiệu hóa update mù quáng.

**Bước 4 — Java cần thấy giá trị khi nào?** Nếu phải trả generated reference/timestamp ngay sau persist, dùng generated mapping/readback. Nếu chỉ cần ở request kế tiếp, có thể đọc từ context mới.

**Bước 5 — Có nhiều writer không?** SQL native, trigger, batch và service ngoài Hibernate đòi hỏi kế hoạch đồng bộ/cache rõ ràng.

**Bước 6 — Chi phí round-trip có đáng kể không?** Nhiều generated fields và refresh lặp lại có thể thêm SELECT/RETURNING; kiểm tra SQL thực tế và tối ưu theo workload.

**Bước 7 — Có ràng buộc portability không?** `@ColumnDefault`, `@Generated`, `@DynamicInsert`, `@GeneratedColumn` là các extension Hibernate; DEFAULT/trigger/generated column có khác biệt theo database. Xác định rõ Hibernate version và dialect trước khi dựa vào cú pháp cụ thể.

### 23.1. Bảng quyết định nhanh

| Yêu cầu | Lựa chọn thường phù hợp |
|---|---|
| Java cần biết trạng thái mặc định ngay khi `new` | Constructor/field initializer hoặc service |
| Tạo audit timestamp bằng JVM | `@CreationTimestamp` / `@UpdateTimestamp` mặc định |
| Dùng giờ database trong lifecycle do Hibernate điều khiển | `@CreationTimestamp(source = DB)` / `@UpdateTimestamp(source = DB)` |
| Mọi writer INSERT bỏ cột đều nhận default | Database `DEFAULT` |
| Hibernate bỏ cột null để DB default chạy | `@DynamicInsert`, khi semantics phù hợp |
| DB sở hữu field và Hibernate phải biết giá trị sau INSERT | `@Generated(event = INSERT)` + mapping/DDL thích hợp |
| DB trigger đổi field sau UPDATE | `@Generated(event = {INSERT, UPDATE})` khi đúng cả hai, hoặc UPDATE-only khi tương ứng |
| Giá trị tính toán có cột schema | Generated column + mapping phù hợp |
| Giá trị suy ra chỉ cần trong SELECT | `@Formula` hoặc DTO projection |
| Đồng bộ giá trị DB hiện tại vào managed entity | `em.refresh(entity)` có chủ đích |
| Đọc dữ liệu đã commit sau một transaction | Context mới với cache/isolation phù hợp |

## 24. Bài tập thực hành

### Bài A — Default không kích hoạt với NULL

Tạo bảng có `status NOT NULL DEFAULT 'NEW'`. Thử `INSERT` bỏ cột và `INSERT` truyền `NULL`. Giải thích vì sao kết quả khác nhau. Sau đó dùng Hibernate entity với `@ColumnDefault` và quan sát INSERT được phát.

### Bài B — Bật và tắt `@DynamicInsert`

Tạo entity có `status == null` và cột DB default. So SQL INSERT khi có/không có `@DynamicInsert`. Đọc lại trong context mới để kiểm tra database đã sinh gì, thay vì chỉ nhìn field Java ngay sau persist.

### Bài C — Thêm `@Generated(INSERT)`

Tạo một field default read-only, đánh dấu `@Generated(event = EventType.INSERT)` và đối chiếu field Java trước/sau flush. Quan sát Hibernate dùng SELECT bổ sung hoặc cơ chế generated-values của dialect.

### Bài D — Trigger ở UPDATE

Tạo trigger cập nhật `updated_at`. Load entity, đổi `description`, xem `updatedAt` ngay sau setter, sau flush, sau refresh và sau commit. Phân tích mốc DB thật sự sinh timestamp.

### Bài E — Timestamp JVM và DB

Thử `@CreationTimestamp` với nguồn JVM và `SourceType.DB`. Ghi nhận khác biệt nguồn đồng hồ, SQL, giá trị Java và yêu cầu khi có nhiều application servers.

### Bài F — Generated column

Tạo cột `line_total` từ `quantity * unit_price`. Mapping bằng annotation/DDL phù hợp, persist rồi thay quantity. Quan sát readback khi generated field được khai báo chính xác.

### Bài G — Flush rồi rollback

Persist entity có ID và DB default, gọi flush rồi rollback. Kiểm tra object Java giữ những gì, và truy vấn lại bằng context mới để xác định dữ liệu được commit hay không.

### Bài H — Bulk update

Load entity có `updated_at`, chạy JPQL bulk UPDATE hoặc native UPDATE. So giá trị trong entity đã managed với database; thực hiện refresh/clear thích hợp và giải thích vì sao generated mapping không tự đồng bộ mọi bulk DML.

### Bài I — Precision timestamp

Chạy hai UPDATE nhanh trong cùng transaction trên PostgreSQL với trigger dùng `CURRENT_TIMESTAMP`. Quan sát vì sao `updated_at` có thể không đổi, rồi cân nhắc quy tắc timestamp và phương pháp test phù hợp.

### Bài J — Đo chi phí readback

Tạo 1.000 entity có nhiều generated fields, so số SQL/round-trip với mapping không cần readback ngay. Phân tích tác động của ID generator, dialect, JDBC batching, statement reuse và chiến lược dùng `refresh`.

## 25. Câu hỏi tự kiểm tra

**1. `@ColumnDefault("'NEW'")` có tự gán `"NEW"` vào Java object khi gọi `new` không?**

Không. Nó chủ yếu mô tả default cho DDL Hibernate tạo. Nếu muốn Java object có trạng thái ngay, gán trong Java; nếu DB sở hữu, cần SQL bỏ cột và đọc lại phù hợp.

**2. Tại sao INSERT truyền NULL không dùng DEFAULT?**

Vì giá trị `NULL` đã được cung cấp tường minh cho cột. SQL DEFAULT thông thường áp dụng khi cột bị bỏ qua hoặc dùng cú pháp `DEFAULT` tương ứng.

**3. `@DynamicInsert` có tự refresh entity không?**

Không. Nó quyết định cách dựng INSERT (trong đó có việc bỏ những field null phù hợp), không tự có nghĩa “DB-generated value đã được tải trở lại”.

**4. `@Generated(event = EventType.INSERT)` có tác dụng gì?**

Nó báo Hibernate thuộc tính được database sinh sau INSERT và cần được lấy lại theo generated-value handling. Database phải thật sự có cơ chế sinh giá trị.

**5. Khi một trigger sửa `updated_at`, tại sao getter có thể còn trả timestamp cũ sau khi gọi setter?**

Vì setter chỉ đổi trạng thái Java. Trigger chạy khi database thực thi UPDATE, thường ở flush/commit, và còn cần readback để field Java nhận giá trị mới.

**6. `flush` có bảo đảm giá trị đã commit?**

Không. Flush thực hiện SQL trong transaction hiện tại, và transaction vẫn có thể rollback.

**7. `@CreationTimestamp(source = SourceType.DB)` có tạo trigger cho writer SQL ngoài Hibernate không?**

Không. Nó là cơ chế ORM yêu cầu nguồn thời gian database cho lifecycle do Hibernate điều khiển. Trigger/default trên schema là vấn đề riêng.

**8. Vì sao `@Version` không nên bị xem là `updatedAt`?**

Version phục vụ optimistic locking, còn timestamp mang thông tin thời điểm. Chúng có thể cùng thay đổi khi UPDATE nhưng khác vai trò và cách kiểm chứng.

**9. Khi nào dùng `em.refresh()`?**

Khi cần đồng bộ một entity managed với state database sau khi đã xử lý các thay đổi đang chờ phù hợp. Gọi refresh không có chủ đích có thể ghi đè state chưa flush.

**10. Bulk UPDATE có khiến tất cả managed entities tự nhận giá trị trigger mới không?**

Không. Bulk DML không cập nhật tự động trạng thái từng managed object như vòng đời update thông thường; cần kế hoạch refresh/clear/reload và cache.

## 26. Ghi nhớ

- **Giá trị tự sinh có nguồn khác nhau:** Java initializer, lifecycle callback, Hibernate timestamp generator, database DEFAULT, trigger, generated column hoặc identifier generator.
- **Database DEFAULT không phải Java default.** Nếu Hibernate ghi `NULL` tường minh, DEFAULT thường không kích hoạt. `@DynamicInsert` có thể giúp bỏ field null nhưng không tự refresh.
- **`@ColumnDefault` chủ yếu là metadata DDL**; cần schema thực tế có default và cơ chế bỏ cột khi INSERT.
- **`@Generated` mô tả trường do database tạo ở INSERT/UPDATE**, giúp Hibernate biết lúc nào phải lấy giá trị trở lại.
- **`@CreationTimestamp`/`@UpdateTimestamp`** là generator do Hibernate quản lý; chọn JVM hay DB clock phù hợp với yêu cầu, không nhầm chúng với trigger cho mọi writer.
- **`flush()` gửi SQL; `commit()` hoàn tất giao dịch.** Readback có thể diễn ra sau INSERT/UPDATE nhưng trước commit và không chứng minh row đã được commit.
- **`refresh()` lấy lại state từ database** nhưng có thể ghi đè pending Java state; dùng có chủ đích.
- **Cache, bulk/native SQL và writer ngoài Hibernate** có thể khiến managed entity cũ; generated mapping không phải cơ chế đồng bộ tự động toàn hệ thống.
- **Kiểm tra SQL thực tế** trên Hibernate version, dialect và database thật trước khi đưa ra giả định về RETURNING, SELECT bổ sung, timestamp precision hoặc trigger behavior.

### Tài liệu tham khảo

- [Hibernate ORM User Guide 6.6 — Generated properties, default values và dynamic SQL](https://docs.jboss.org/hibernate/orm/6.6/userguide/html_single/Hibernate_User_Guide.html)
- [Hibernate ORM JavaDoc 6.6 — `@Generated`](https://docs.jboss.org/hibernate/orm/6.6/javadocs/org/hibernate/annotations/Generated.html)
- [Hibernate ORM JavaDoc 6.6 — `@ColumnDefault`](https://docs.jboss.org/hibernate/orm/6.6/javadocs/org/hibernate/annotations/ColumnDefault.html)
- [Hibernate ORM JavaDoc 6.6 — `@DynamicInsert`](https://docs.jboss.org/hibernate/orm/6.6/javadocs/org/hibernate/annotations/DynamicInsert.html)
- [Hibernate ORM JavaDoc 6.6 — `@CreationTimestamp`](https://docs.jboss.org/hibernate/orm/6.6/javadocs/org/hibernate/annotations/CreationTimestamp.html)
- [Hibernate ORM JavaDoc 6.6 — `@GeneratedColumn`](https://docs.jboss.org/hibernate/orm/6.6/javadocs/org/hibernate/annotations/GeneratedColumn.html)
- [Jakarta Persistence Specification 3.1 — Entity lifecycle, flushing, refresh](https://jakarta.ee/specifications/persistence/3.1/jakarta-persistence-spec-3.1)
- [PostgreSQL Documentation — CREATE TRIGGER và CREATE TABLE](https://www.postgresql.org/docs/current/sql-createtrigger.html)

