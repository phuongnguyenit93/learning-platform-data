# Đánh giá ảnh hưởng chiến lược sinh khóa đến hiệu năng ghi trong JPA

Trong ứng dụng Java Persistence API (JPA), mọi entity cần có một **identity** để persistence context phân biệt đối tượng và để database duy trì khóa chính, khóa ngoại cùng các ràng buộc liên quan. Các chiến lược sinh khóa như `IDENTITY`, `SEQUENCE`, `TABLE`, `AUTO` và `UUID` không chỉ khác nhau ở cách nhận một giá trị ID. Chúng còn tác động đến **thời điểm thực hiện INSERT, số lần trao đổi với database, khả năng JDBC batching, lock contention, kích thước index, cách cascade lưu graph và hiệu năng khi ghi đồng thời**.

Ví dụ, cùng lưu 10.000 Orders:

- Nếu provider cần thực hiện từng `INSERT` để nhận ID do cột `IDENTITY` tạo ra, nó có thể khó gom nhiều INSERT vào cùng một JDBC batch.
- Nếu ID được cấp trước qua database sequence với cơ chế pooling, provider có thể gom nhiều entity INSERT theo SQL shape.
- Nếu sử dụng bảng phát số và mỗi ID cần cập nhật một row trong bảng generator, row đó có thể trở thành điểm tranh chấp giữa nhiều workers.
- Nếu dùng UUID sinh tại ứng dụng, có thể bỏ bước xin ID từ DB, nhưng dạng khóa ngẫu nhiên có thể ảnh hưởng độ phân mảnh và kích thước B-tree indexes tùy DB/storage engine.
- Nếu chọn `AUTO`, provider có quyền quyết định chiến lược tùy dialect và phiên bản; hiệu năng có thể thay đổi khi nâng thư viện hoặc đổi database.

Không có chiến lược nào **luôn nhanh nhất** cho mọi workload. Bài học thuộc chương **Hiệu năng** của chủ đề **Data Persistence Relational Access ORM JPA**, tập trung vào cách đánh giá chiến lược sinh khóa theo workload thực, provider thực, database thực và yêu cầu về concurrency, tính đúng dữ liệu.

Mục tiêu sau bài học:

1. Hiểu `@Id`, `@GeneratedValue` và từng `GenerationType` thực sự quyết định điều gì.
2. Phân biệt **cấp giá trị ID** với **INSERT, flush và commit**.
3. Hiểu vì sao thời điểm có ID ảnh hưởng JDBC insert batching và cách lưu quan hệ cha–con.
4. Biết vai trò `@SequenceGenerator(allocationSize)` và generator pooling, cũng như các rủi ro cấu hình không khớp sequence.
5. Nhận ra lock hotspot của `TABLE` generator và các tác động index locality của integer/UUID keys.
6. Thiết kế benchmark công bằng: SQL round trips, throughput, p95/p99 latency, lock waits, batch utilization, CPU, memory và index size.
7. Đưa ra lựa chọn có điều kiện cho PostgreSQL, MySQL, SQL Server, Oracle hoặc những database khác.
8. Tránh nhầm ID được cấp với transaction đã commit và không dùng ID kỹ thuật làm số thứ tự nghiệp vụ bắt buộc liên tục.

---

## 1. Vì sao sinh khóa là một yếu tố của hiệu năng ghi?

Giả sử service tạo một Order:

```java
PurchaseOrder order = new PurchaseOrder(...);

em.persist(order);

em.flush();
```

Provider cần bảo đảm mỗi entity persistent có identity phù hợp. Nhưng **trình tự nhận identity** khác nhau theo strategy:

```text
Chiến lược A: ID từ INSERT
Application -> INSERT -> Database cấp ID -> Provider đọc ID

Chiến lược B: ID từ SEQUENCE
Application -> NEXT VALUE -> Provider có ID
            -> INSERT (có thể batch)

Chiến lược C: ID từ APP
Application tạo UUID/ID
            -> INSERT (có thể batch)

Chiến lược D: ID từ bảng phát số
Application -> khóa/đọc/cập nhật generator row -> Provider có ID
            -> INSERT
```

Mỗi mũi tên trao đổi với database có thể là một network round trip hoặc một phần của statement/batch. Provider, driver và database có thể tối ưu các bước khác nhau; sơ đồ chỉ thể hiện cơ chế cơ bản.

### 1.1. ID generation không chỉ là một hàm tạo số

Ảnh hưởng gián tiếp thường lớn hơn chi phí tạo một số:

- Provider có thể phải `INSERT` sớm để biết ID.
- JDBC statement có thể phải lấy `getGeneratedKeys()`.
- Nhiều entity INSERT không thể gom trong cùng batch theo cách provider mong muốn.
- Một global generator row có thể phải lock khi nhiều transactions cùng cấp ID.
- Primary key type ảnh hưởng FK width và secondary index storage.
- Random-key insertion có thể ảnh hưởng B-tree page splits/cache locality.
- Phải đợi keys để gắn quan hệ cha–con hoặc ghi outbox.
- Các generator caches/blocks có thể gây khoảng trống trong dãy số khi rollback/restart.

### 1.2. Đánh giá phải bao gồm tính đúng

Một ID generator không được phép sinh duplicate ID. Một chiến lược nhanh nhưng làm mất uniqueness, xung đột cluster IDs hoặc tạo sai FK không phải lựa chọn hợp lệ.

---

## 2. Phân biệt entity ID và business identifier

Một Order có thể có hai trường:

```java
@Id
private Long id;

@Column(name = "order_number", unique = true)
private String orderNumber;
```

`id` là **technical primary key**, dùng cho identity của entity và relationships. `orderNumber` là **business identifier**, có thể được hiển thị cho khách hàng và cần những quy tắc như duy nhất trong tenant, có tiền tố năm hoặc phải dễ đọc.

### 2.1. Technical ID không nhất thiết liên tục

Database sequences, identity counters và UUIDs có thể tạo **gaps** vì rollback, restart, cache loss hoặc transactions cạnh tranh. Gaps thường không phải lỗi.

### 2.2. Không dùng ID gap để suy luận transaction nào thất bại

Một sequence có thể đã cấp ID nhưng transaction rollback; số đó không được hoàn lại. Một ID có giá trị không có nghĩa row đã commit.

### 2.3. Nếu nghiệp vụ cần số hóa đơn theo quy định riêng

Một yêu cầu “số hóa đơn không được trùng, có quy tắc phân bổ/ghi nhận chính thức” cần giải pháp nghiệp vụ, ledger và kiểm soát concurrency riêng. Không mặc định `@GeneratedValue` bảo đảm dãy không thiếu số.

### 2.4. Surrogate key và unique business key có thể cùng tồn tại

Thiết kế thường rõ ràng:

```sql
PRIMARY KEY (id),
UNIQUE (tenant_id, order_number)
```

Chọn ID để tối ưu quan hệ và lưu trữ, đồng thời dùng unique constraint riêng để bảo vệ business identity.

---

## 3. Tổng quan GenerationType chuẩn JPA

Các chiến lược thường gặp:

```java
GenerationType.IDENTITY
GenerationType.SEQUENCE
GenerationType.TABLE
GenerationType.AUTO
GenerationType.UUID
```

`GenerationType.UUID` là lựa chọn được chuẩn hóa từ **Jakarta Persistence 3.1**; nếu codebase dùng JPA 2.x hoặc Jakarta Persistence 3.0, enum này không nhất thiết có. Phải xác nhận API version và provider hỗ trợ trước khi áp dụng.

| Strategy | Nguồn ID chính | ID thường biết trước INSERT? | Điều cần đánh giá |
|---|---|---|---|
| `IDENTITY` | Cột identity/auto-increment của DB | Thường không | INSERT sớm, generated keys, batching |
| `SEQUENCE` | Database sequence | Thường có | NEXTVAL calls, allocation/pooling |
| `TABLE` | Generator table mô phỏng sequence | Thường có sau thao tác generator | Contention, row locks, extra DML |
| `AUTO` | Provider/dialect quyết định | Không cố định | Portability, cấu hình, nâng version |
| `UUID` | Generator UUID theo provider/spec | Thường có thể trước INSERT | App/DB generation, key size, index locality |

“Thường” ở cột thời điểm là mô tả hành vi phổ biến, **không phải cam kết về SQL timing cho mọi JPA implementation**.

---

## 4. @Id và @GeneratedValue

Một entity đơn giản:

```java
import jakarta.persistence.*;

@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String status;

    protected PurchaseOrder() {}

    public Long getId() { return id; }
}
```

`@Id` xác định identifier mapping; `@GeneratedValue` chỉ định chiến lược sinh giá trị với provider.

### 4.1. GeneratedValue không đồng nghĩa database trigger

Một số strategies cần database tạo ID tại INSERT; các strategies khác có thể lấy giá trị trước INSERT qua sequence/table hoặc provider generator. Không nên hiểu mọi `@GeneratedValue` đều là một SQL trigger.

### 4.2. Primitive và wrapper ID

Một entity mới thường có `Long id == null` khi chưa cấp ID, trong khi `long id` có default `0`. Wrapper dễ phân biệt new/assigned state hơn trong nhiều designs, nhưng cần hiểu `isNew` semantics của repository/provider và codebase.

### 4.3. Không set generated ID thủ công tùy tiện

Nếu entity dùng provider-generated identity, tự gán một ID arbitrary có thể khiến provider coi entity là detached hoặc xử lý persist/merge khác dự kiến. Nếu muốn application-assigned IDs, thiết kế strategy và new-entity detection rõ.

### 4.4. ID phải ổn định sau khi cấp

Primary key không nên được business code sửa khi entity đã managed/persistent. Relationships, equality và persistence context identity phụ thuộc giá trị này.

---

## 5. IDENTITY hoạt động như thế nào?

Ví dụ:

```java
@Entity
public class IdentityOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String orderNumber;
}
```

Database có cột identity:

```sql
CREATE TABLE identity_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(80) NOT NULL
);
```

SQL trên theo một dialect hỗ trợ syntax tương ứng, chẳng hạn PostgreSQL; MySQL thường dùng `AUTO_INCREMENT` và SQL Server có cú pháp `IDENTITY` riêng.

### 5.1. ID do INSERT tạo

Một flow thường gặp:

```text
em.persist(order)
    |
    v
INSERT INTO identity_order (order_number)
VALUES (?)
    |
    v
DB sinh ID (ví dụ 10421)
    |
    v
Provider nhận generated key
    |
    v
order.id = 10421
```

Provider có thể thực hiện INSERT sớm khi cần generated key. Điều này làm thời điểm SQL khác với sequence/app-assigned IDs vốn có thể biết ID trước.

### 5.2. Vì sao ảnh hưởng batching?

Đối với một ORM như Hibernate, identity-generated IDs thường hạn chế hoặc vô hiệu hóa JDBC INSERT batching cho các entity tương ứng, do provider phải lấy ID cho từng INSERT để quản lý identity và cascade. Đây là **hành vi triển khai phổ biến cần kiểm tra theo provider/version**, không phải mệnh đề rằng mọi JDBC driver hoặc mọi database tuyệt đối không thể batch INSERT có generated keys.

### 5.3. JDBC `getGeneratedKeys()`

JDBC có cơ chế nhận generated keys từ INSERT, nhưng chi phí/thời điểm nhận keys phụ thuộc driver và database. Có driver hỗ trợ multi-row INSERT và RETURNING/generated-key retrieval tốt hơn; ORM có dùng được chúng cho entity identity hay không là câu hỏi khác.

### 5.4. Ưu điểm

- Đơn giản, tự nhiên trên DB có auto-increment/identity.
- Database quản lý uniqueness của ID.
- Không cần cấu hình sequence name/allocation cho entity ở phía JPA.
- Có thể phù hợp workload ghi ít hoặc vừa, đặc biệt khi database không có native sequences.

### 5.5. Chi phí tiềm ẩn

- Nhiều INSERT round trips khi ghi hàng loạt.
- Ít khả năng gom inserts cùng SQL shape trong một JDBC batch trên một số ORM.
- Phải nhận generated keys trước khi provider xử lý một số references.
- Khó tận dụng write-behind toàn diện cho những entities cần identity ngay.

### 5.6. Đừng suy ra IDENTITY luôn kém

Nếu workload chỉ tạo một entity mỗi request, network thấp, business logic/I/O khác chiếm đa số, chênh lệch batching có thể không đáng kể. Khi database/driver/provider có tối ưu đặc biệt, kết quả thực nghiệm có thể khác kỳ vọng.

---

## 6. SEQUENCE hoạt động như thế nào?

Ví dụ:

```java
@Entity
public class SequenceOrder {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "order_seq_generator"
    )
    @SequenceGenerator(
        name = "order_seq_generator",
        sequenceName = "order_id_seq",
        allocationSize = 50
    )
    private Long id;

    private String orderNumber;
}
```

Giả sử database hỗ trợ native sequence. JPA provider có thể lấy ID qua sequence trước khi INSERT.

### 6.1. Luồng cơ bản

```text
Provider cần ID
     |
     v
NEXT VALUE / NEXTVAL từ database sequence
     |
     v
Provider biết entity.id
     |
     v
Xếp INSERT vào batch/action queue
     |
     v
Flush/commit -> INSERT theo chiến lược batching
```

### 6.2. Tại sao sequence thường thuận lợi cho batching?

Vì provider biết ID trước INSERT, nó có thể đưa nhiều entity INSERT có cùng SQL shape vào JDBC batch. Việc lấy ID và việc gửi INSERT được tách thành hai giai đoạn.

### 6.3. Một sequence call cho mỗi ID vẫn tốn chi phí

Nếu generator gọi DB để lấy NEXTVAL cho từng entity, 10.000 entities có thể cần khoảng 10.000 bước cấp ID, chưa kể INSERT. Do đó `allocationSize` và provider optimizer đáng xem xét.

### 6.4. SEQUENCE không phổ biến như nhau trên mọi DB

PostgreSQL và Oracle có native sequences. Một số database/versions khác có cơ chế tương đương nhưng syntax và driver semantics khác nhau. MySQL thông thường dùng auto-increment và không có native sequence object theo cách PostgreSQL hỗ trợ, vì vậy lựa chọn SEQUENCE cần kiểm tra dialect/provider.

---

## 7. @SequenceGenerator và allocationSize

Annotation:

```java
@SequenceGenerator(
    name = "order_seq_generator",
    sequenceName = "order_id_seq",
    initialValue = 1,
    allocationSize = 50
)
```

`allocationSize` mô tả số giá trị ID được cấp trong một nhóm allocation theo generator semantics. Giá trị mặc định của JPA `@SequenceGenerator` là **50**, nhưng không nên suy rằng mọi provider có cùng optimizer algorithm.

### 7.1. Ý nghĩa khi pooling

Nếu provider sử dụng allocation/pooling, nó có thể nhận một giá trị sequence từ DB để cấp **nhiều ID trong memory** thay vì thực hiện một database round trip cho mỗi ID.

Một cách hình dung:

```text
Nhận block cho khoảng ID 1001..1050
    -> Order A = 1001
    -> Order B = 1002
    -> ...
    -> Order Z = 1050

Hết block -> xin block mới
```

Sơ đồ chỉ mô tả ý tưởng. Các optimizers như pooled, pooled-lo hoặc hi/lo có cách tính boundary khác nhau, phụ thuộc implementation.

### 7.2. Hiệu năng cải thiện ở đâu?

Giảm số round trips dành cho ID allocation. Đồng thời ID vẫn có thể được biết trước INSERT, giúp provider tiếp tục gom JDBC batches.

### 7.3. allocationSize không đồng nghĩa batch_size

Hai thông số giải quyết hai vấn đề:

- **`allocationSize`**: provider xin/cấp một nhóm ID như thế nào.
- **JDBC `batch_size`**: provider gửi bao nhiêu SQL executions chung một batch.

Tăng allocationSize không tự bật JDBC batching; bật JDBC batching không tự tối ưu sequence allocation.

### 7.4. allocationSize=1

Thông thường không khai thác pooling nhiều ID mỗi sequence fetch. Có thể dễ kiểm soát khi migration legacy sequence, nhưng tăng số lần liên hệ DB dưới workload ghi lớn.

### 7.5. allocationSize lớn

Giảm allocation round trips trong nhiều implementations nhưng có thể gây **lãng phí các ID chưa dùng** khi app instance restart/crash và có thể khiến gaps lớn hơn. Với surrogate ID, gaps thường chấp nhận được.

### 7.6. Không coi allocationSize là “số row được ghi mỗi lần”

Nếu `allocationSize = 50` và chỉ persist 1 entity, provider không nhất thiết INSERT 50 rows. Nó chỉ có thể dành trước **khả năng cấp IDs**.

---

## 8. Phân biệt JPA allocationSize và database SEQUENCE CACHE

Database sequence có thể có cấu hình:

```sql
CREATE SEQUENCE order_id_seq
    START WITH 1
    INCREMENT BY 50
    CACHE 100;
```

Đây là **DDL minh họa** cho một cấu hình cần được khớp với optimizer JPA/provider; không phải câu lệnh bắt buộc cho mọi `@SequenceGenerator`.

Có ít nhất hai cơ chế liên quan nhưng khác nhau:

1. Provider-level ID allocation/pooling: provider giữ một block IDs cho application.
2. Database sequence cache: DB cache sequence metadata/values để giảm I/O nội bộ của sequence implementation.

### 8.1. `CACHE 100` không có nghĩa Hibernate nhận 100 IDs mỗi NEXTVAL

Database cache có thể làm NEXTVAL nhanh hơn bên trong DB, nhưng không nhất thiết giảm số lần application gửi NEXTVAL. Muốn giảm network calls phải xem provider allocation optimizer.

### 8.2. `INCREMENT BY` phải tương thích optimizer

Một số Hibernate pooled optimizers yêu cầu database sequence increment phù hợp với allocationSize, ví dụ 50. Nếu JPA config allocationSize=50 nhưng database sequence thực tế increment=1 trong một chiến lược cần increment 50, provider có thể báo mismatch khi startup hoặc có nguy cơ cấp ID sai khi cấu hình không được kiểm soát.

**Không áp dụng “set increment=50” như quy tắc portable cho mọi provider.** Cần đọc provider/version generator algorithm và khớp DDL/metadata. Một số generator patterns dùng hi/lo hoặc pooling khác.

### 8.3. Nhiều application nodes

Nếu nhiều instances cùng lấy IDs, generator algorithm phải tránh overlap các blocks. Dùng native sequence đúng cấu hình là một cách thuận lợi. Tự viết cache block trong Java mà không khóa nguồn cấp đúng dễ tạo duplicate IDs giữa nodes.

### 8.4. Sequence gaps sau restart

Database cache loss và provider local allocation loss có thể gây gaps, ngay cả khi transaction rollback hoặc application chưa persist hết block. Không biến sequence ID thành business number bắt buộc liên tục.

---

## 9. Ví dụ so sánh SEQUENCE allocationSize=1 và 50

Giả sử provider có một cơ chế pooling thích hợp và ghi 5.000 Orders.

| Thành phần | allocationSize=1 | allocationSize=50 |
|---|---|---|
| Số ID cần dùng | 5.000 | 5.000 |
| Số lần cấp qua DB | Có thể gần 5.000 | Có thể gần 100 |
| INSERT rows | Vẫn 5.000 | Vẫn 5.000 |
| Khả năng batch INSERT | Phụ thuộc config/provider | Phụ thuộc config/provider |
| Gaps khi restart | Thường ít hơn | Có thể nhiều hơn |
| Phụ thuộc generator config | Có | Có; phải khớp DDL/optimizer |

Đây là **phép tính lý thuyết** cho một optimizer cấp đúng 50 ID mỗi lần, không phải số đo benchmark và không phải behavior được JPA đảm bảo cho mọi implementation.

### 9.1. Nút cổ chai có thể chuyển vị trí

Khi sequence calls giảm, giới hạn throughput có thể chuyển sang JDBC INSERT batching, disk WAL, index contention, FK checks hoặc transaction commit latency.

### 9.2. Đo cả SQL và network

Một provider có thể gửi NEXTVAL qua một lệnh riêng hoặc dùng cách cấp ID khác. SQL logs, statement counters và driver instrumentation giúp xác định thực tế, không đoán từ tên annotation.

---

## 10. TABLE generator hoạt động như thế nào?

`TABLE` sử dụng một table để lưu các giá trị phát số và mô phỏng một nguồn identity.

```java
@Entity
public class TableOrder {

    @Id
    @GeneratedValue(
        strategy = GenerationType.TABLE,
        generator = "order_table_generator"
    )
    @TableGenerator(
        name = "order_table_generator",
        table = "id_generator",
        pkColumnName = "generator_name",
        valueColumnName = "next_id",
        pkColumnValue = "order",
        allocationSize = 50
    )
    private Long id;
}
```

Bảng minh họa:

```sql
CREATE TABLE id_generator (
    generator_name VARCHAR(100) PRIMARY KEY,
    next_id BIGINT NOT NULL
);
```

Có thể có row:

```text
generator_name | next_id
order          | 10001
invoice        | 50001
```

### 10.1. Cấp ID qua cập nhật bảng

Một provider có thể thực hiện logic tương tự:

```text
BEGIN generator operation
  SELECT next_id ... FOR UPDATE
  UPDATE id_generator SET next_id = next_id + block_size
COMMIT generator operation
```

Chi tiết locking, transactions và SQL strategy phụ thuộc provider/dialect. Không coi ví dụ này là SQL template chung cho mọi TABLE generator.

### 10.2. Điểm tranh chấp

Nếu nhiều workers cùng muốn cấp Order IDs, các operations có thể tranh chấp cùng row `generator_name='order'`. Trong workload ghi đồng thời, lock waits có thể lớn hơn chi phí đơn giản của lấy số.

### 10.3. allocationSize có thể giúp nhưng không xóa contention

Pooling nhiều IDs mỗi generator operation giảm số lần lock/update row, nhưng vẫn có shared generator state và DML overhead.

### 10.4. Khi nào TABLE có thể hữu ích?

Khi database không hỗ trợ sequence phù hợp và yêu cầu portability/legacy design khiến TABLE là lựa chọn chấp nhận được, sau khi đã đo concurrency. Không mặc định chọn TABLE chỉ vì nó hoạt động trên nhiều dialects.

### 10.5. Rủi ro global generator row

Nếu mọi entity types dùng cùng một row generator, contention có thể tăng thêm. Tách segments/rows có thể giảm tranh chấp nhưng làm cấu hình và vận hành phức tạp hơn.

---

## 11. AUTO: Thuận tiện nhưng không cố định cost model

```java
@Id
@GeneratedValue(strategy = GenerationType.AUTO)
private Long id;
```

`AUTO` giao việc chọn chiến lược cho provider tùy database, generator metadata, mapping và phiên bản.

### 11.1. Không suy ra AUTO = IDENTITY

Trên một số Hibernate/dialect combinations, AUTO có thể chọn sequence-based strategy; môi trường khác có thể dùng table/identity hoặc provider-specific generator.

### 11.2. Migration có thể đổi behavior

Khi chuyển database hoặc nâng Hibernate/EclipseLink, generated DDL, naming convention, default allocation size hoặc optimizer có thể khác. Do đó benchmark nên ghi **effective generator** chứ không chỉ annotation `AUTO`.

### 11.3. Khi nào chấp nhận AUTO?

Khi application không có yêu cầu hiệu năng/portability đặc biệt và đã xác minh generator thực tế. Với write-intensive service, explicit strategy giúp giảm bất ngờ và thuận tiện đối chiếu DDL.

### 11.4. Đừng nhầm khả năng chạy với tối ưu

AUTO có thể giúp cùng source code chạy trên nhiều DB, nhưng mỗi DB có bottleneck và strategy thích hợp khác nhau. Portability thường cần kiểm thử và cấu hình per dialect, không chỉ một annotation.

---

## 12. UUID được chuẩn hóa trong Jakarta Persistence 3.1

Ví dụ:

```java
@Entity
public class UuidOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    private String orderNumber;
}
```

Từ Jakarta Persistence 3.1, `GenerationType.UUID` là chiến lược chuẩn. Nếu codebase vẫn dùng `javax.persistence` hoặc Jakarta Persistence 3.0, cần kiểm tra các generator extensions cụ thể.

### 12.1. UUID giúp gì cho write path?

Nếu UUID được sinh ở application/provider trước INSERT, không cần round trip riêng để lấy ID từ database. Provider có thể gom INSERT operations theo khả năng batching.

### 12.2. Không tự giả định UUID version

`GenerationType.UUID` mô tả yêu cầu tạo UUID, nhưng không nên khẳng định mọi provider luôn tạo UUIDv4 hay UUIDv7. Phải kiểm tra spec/version/provider behavior.

### 12.3. UUID không loại bỏ DB uniqueness

Vẫn cần primary key/unique constraint. Khả năng collision rất thấp với generator chuẩn và entropy đủ, nhưng correctness vẫn dựa vào constraints cùng triển khai đúng.

### 12.4. UUID có thể phù hợp nhiều nodes

Mỗi node có thể tạo IDs không cần round trip tới một central sequence, giúp giảm phụ thuộc network/DB ở bước ID allocation. Tuy nhiên, cần tin cậy thư viện, random source hoặc thuật toán phân tán được sử dụng.

---

## 13. Application-assigned IDs

Một cách khác là tự cấp ID trước khi gọi JPA:

```java
@Entity
public class AssignedUuidOrder {

    @Id
    private UUID id;

    private String orderNumber;

    protected AssignedUuidOrder() {}

    public AssignedUuidOrder(String orderNumber) {
        this.id = UUID.randomUUID();
        this.orderNumber = orderNumber;
    }
}
```

Không sử dụng `@GeneratedValue`; ID được application gán.

### 13.1. Đặc điểm

- ID có sẵn trước persist.
- Không có DB ID allocation round trip.
- Có thể hỗ trợ batching nếu provider/mappings cho phép.
- Database vẫn kiểm tra primary key uniqueness.
- Application chịu trách nhiệm sinh đúng type, uniqueness và lifecycle.

### 13.2. Spring Data save và new detection

Với assigned ID không null ngay khi tạo entity, một số đường `JpaRepository.save()` có thể dựa vào ID/null hoặc version/Persistable để quyết định `persist` hay `merge`. Nếu bị nhận nhầm là existing entity, có thể phát SELECT/merge work không mong muốn.

**Benchmark phải xem operation thực sự là persist hay merge**, không kết luận “UUID chậm” khi nguyên nhân là repository new-state detection.

### 13.3. UUID.randomUUID không phải Generator của mọi provider

Đây là Java application API. Không có nghĩa nó hoàn toàn giống `GenerationType.UUID` hoặc annotation UUID riêng của Hibernate ở mọi version.

---

## 14. UUID ngẫu nhiên và hiệu năng index

Một UUID thường chiếm 128 bits, tức **16 bytes** ở dạng nhị phân. Nếu lưu dưới dạng canonical text, chuỗi UUID thường có **36 ký tự** gồm dấu gạch nối, có thể tốn nhiều bytes hơn tùy charset/index representation.

### 14.1. So với BIGINT

Một `BIGINT` thường chiếm 8 bytes. UUID dạng binary 16 bytes có kích thước key lớn hơn và có thể làm:
- Primary key index lớn hơn.
- Foreign key columns/indexes rộng hơn.
- Secondary indexes tốn thêm dung lượng ở một số storage engines.
- Memory/cache locality và disk I/O bị ảnh hưởng.

Mức ảnh hưởng thực tế phụ thuộc cách DB tổ chức clustered index/heap/secondary indexes.

### 14.2. Random insertion vs sequential insertion

Random UUIDs có thể làm B-tree inserts trải đều nhiều pages, tăng page splits/cache misses ở workload lớn. Sequential numeric IDs thường thuận lợi cho locality tại rightmost pages, nhưng cũng có thể gặp contention trên hot append pages dưới concurrency cao.

### 14.3. Đừng khẳng định UUID luôn chậm

Với workload nhỏ hoặc medium, khác biệt có thể không đáng kể. Database engine, fillfactor, clustering, SSD, WAL, page cache và indexing choices đều ảnh hưởng kết quả.

### 14.4. UUID storage mapping

Trên PostgreSQL có native `uuid` type; một số databases có `BINARY(16)` hoặc các cách biểu diễn khác. Một JPA `UUID` field không đảm bảo physical column type giống nhau trên mọi dialect.

### 14.5. Không dùng UUID như security control

Một ID khó đoán không thay authentication/authorization. API phải kiểm tra tenant/resource permissions ngay cả khi key là UUID.

---

## 15. UUIDv7 và các khóa có thứ tự thời gian

Một số hệ thống lựa chọn UUIDv7 hoặc các time-ordered identifiers để kết hợp phân tán ID generation với index locality tốt hơn random UUIDv4.

### 15.1. Không đồng nhất với GenerationType.UUID mặc định

Việc chọn UUIDv7 cụ thể có thể cần application generator, provider extension hoặc library tương thích. Không mặc định `@GeneratedValue(strategy=UUID)` cho UUIDv7 trên mọi stack.

### 15.2. Lợi ích tiềm năng

Timestamp-ordered keys có thể làm insertion patterns gần theo thời gian, giảm một phần random-page writes ở một số indexes.

### 15.3. Trade-offs

- Timestamp làm lộ một phần thông tin thời gian tạo record.
- Clock drift và concurrency cần được generator xử lý.
- Time ordering không bảo đảm tuyệt đối theo transaction commit order.
- Representation trong DB phải giữ ordering semantics nếu muốn lợi ích index.

### 15.4. Benchmark thay vì suy từ tên thuật toán

So sánh UUIDv4, UUIDv7 và BIGINT trên **cùng schema, DB, indexing và concurrency profile**. Một index design khác có thể đảo ngược kết quả kỳ vọng.

---

## 16. Snowflake/ULID/KSUID và các ID phân tán khác

Ngoài chiến lược JPA chuẩn, application có thể sử dụng các thuật toán cấp ID phân tán.

Ví dụ:

```java
@Id
private Long id;  // Được application gán từ ID service.
```

Hoặc:

```java
@Id
private String id; // Một ID dạng chuỗi, nếu đã cân nhắc schema.
```

### 16.1. Lợi ích

Có thể tạo IDs trước INSERT, tránh round trip tới database trong hot write path, hỗ trợ phân tán theo node nếu thuật toán đúng.

### 16.2. Rủi ro

- Worker/node IDs trùng nhau.
- Clock rollback hoặc clock drift.
- Sequence per timestamp overflow.
- Generator central service trở thành bottleneck.
- ID format thay đổi gây migration khó.
- String key làm index/FK rộng.

### 16.3. Không phải tất cả đều portable JPA generators

JPA có thể ánh xạ **giá trị ID đã được application gán**, nhưng cụ thể thuật toán Snowflake/ULID/KSUID không phải các giá trị `GenerationType` chuẩn. Provider extension có thể cần nếu muốn tự động gọi generator trong lifecycle.

### 16.4. Uniqueness phải được kiểm tra tại DB

Ngay cả khi generator được cho là không bao giờ trùng, PK/UNIQUE vẫn là hàng rào bảo vệ cuối.

---

## 17. Natural key và composite key có chi phí gì?

Không phải entity nào cũng dùng generated surrogate ID. Ví dụ:

```java
@EmbeddedId
private OrderLineKey id;
```

hoặc `@IdClass` với `(orderId, lineNumber)`.

### 17.1. Khi có lợi

Composite key có thể diễn đạt identity tự nhiên ở một số join tables, association entities hoặc models có stable composite identifiers.

### 17.2. Khi có chi phí

- Foreign key/index rộng nếu key gồm nhiều columns.
- Query joins cần nhiều predicates.
- Mutable business fields không nên nằm trong primary key.
- Equality/hashCode phức tạp hơn.
- Batching không tự tốt chỉ vì không gọi sequence.

### 17.3. Unique natural key + surrogate key

Một thiết kế thường dễ vận hành là giữ generated narrow PK cho relationships và unique constraint riêng trên business key.

### 17.4. Benchmark tổng chi phí của graph

Một Order ID kiểu BIGINT được tham chiếu bởi hàng triệu OrderLines có thể tiết kiệm index bytes so với một UUID/text key rộng; nhưng điều này phải đo trên schema và workload thực.

---

## 18. Thời điểm có ID ảnh hưởng quan hệ cha–con

Giả sử:

```java
@Entity
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.PERSIST
    )
    private List<OrderLine> lines = new ArrayList<>();

    public void addLine(OrderLine line) {
        lines.add(line);
        line.attachTo(this);
    }
}
```

```java
@Entity
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @ManyToOne(optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    public void attachTo(PurchaseOrder value) {
        this.order = value;
    }
}
```

### 18.1. Với SEQUENCE

Provider thường biết IDs của Order và Lines trước INSERT. Nó có thể lên lịch INSERT theo FK dependency và gom statements cùng loại khi có batching.

### 18.2. Với IDENTITY

Provider có thể phải INSERT parent sớm để lấy ID trước khi INSERT children sử dụng FK. Điều này ảnh hưởng khả năng dồn SQL vào một batch lớn.

### 18.3. ID trước INSERT không bỏ quy tắc FK

Dù Order có UUID đã biết, database vẫn cần parent row tồn tại trước child insert nếu FK constraints không deferred. Provider phải sắp xếp SQL phù hợp.

### 18.4. Owning side quyết định FK mapping

`OrderLine.order` là phía sở hữu FK trong ví dụ. Việc gọi `order.addLine()` cập nhật cả hai phía trước persist; generator strategy không thay quy tắc owning/inverse sides của JPA.

### 18.5. Cascade graph làm benchmark phức tạp

So sánh 10.000 single-column entities có thể cho kết quả khác so với 1.000 Orders x 10 Lines, do FK checks, SQL shapes, allocation nhiều entity types và flush ordering.

---

## 19. JDBC batching: Đòn bẩy thường lớn hơn chi phí tạo ID

JDBC batching cho phép gửi nhiều parameterized executions cùng SQL statement theo nhóm thay vì mỗi row một round trip riêng.

Khái niệm:

```text
INSERT INTO orders(id, status) VALUES (?, ?)
    Params #1
    Params #2
    Params #3
    ...
    Params #50

=> Một JDBC batch, nhiều row effects
```

### 19.1. JPA không bắt buộc mọi provider batch INSERT

JPA mô tả persistence operations; **SQL batching là khả năng implementation/driver-specific**. Không thể suy rằng gọi `persist` trong vòng lặp đồng nghĩa provider đã batch.

### 19.2. Hibernate properties thường gặp

Trong một số version Hibernate, cấu hình:

```properties
hibernate.jdbc.batch_size=50
hibernate.order_inserts=true
hibernate.order_updates=true
```

có thể hỗ trợ gom INSERT/UPDATE. Đây là **Hibernate-specific**, không phải JPA standard properties.

### 19.3. Spring Boot mapping ví dụ

```properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.generate_statistics=true
```

Những settings này chỉ có tác dụng khi ứng dụng thực sự dùng Hibernate và configuration đang được runtime áp dụng. Với EclipseLink, phải xem các batch-writing properties riêng.

### 19.4. Không có batching nếu SQL shape khác nhau

Provider thường gom SQL statements có cùng shape. Xen kẽ nhiều entity types hoặc dynamic INSERT columns có thể làm batch grouping kém. `order_inserts=true` có thể sắp lại thứ tự trong giới hạn provider, nhưng phải xem correctness với FKs/constraints.

### 19.5. Batch size không có nghĩa đúng số rows mỗi network packet

JDBC driver có thể encode/rewrite batches theo cách khác nhau. Có thể vẫn có nhiều server-side executions; cần đo round trips và DB operations thực thay vì suy từ configuration.

---

## 20. IDENTITY và JDBC batching: Nhận định có điều kiện

Có một câu thường gặp: “Hibernate không batch INSERT khi dùng IDENTITY”. Với nhiều cấu hình Hibernate ORM, nhận định này mô tả đúng một **hạn chế thực tế quan trọng**, vì provider cần nhận generated keys và thường thực hiện từng INSERT.

Nhưng khi đánh giá cần nói chính xác:

1. Đây là behavior của **provider/version/driver path** cụ thể, không phải giới hạn tuyệt đối của SQL/JDBC.
2. Một database có thể hỗ trợ `INSERT ... RETURNING`, multi-row INSERT và generated keys, nhưng ORM phải biết dùng cơ chế đó.
3. Một số bulk insert/native SQL APIs có thể batch tốt ngay cả khi bảng có identity column, vì chúng **không tuân cùng entity lifecycle path**.
4. Nếu application ghi một Order mỗi request, batch utilization vốn thấp; chuyển sang SEQUENCE không chắc mang lại thay đổi lớn.
5. Nếu ghi hàng chục nghìn entities trong một unit of work, hạn chế batching có thể trở thành nút cổ chai lớn.

**Cách xác minh:** bật SQL/JDBC instrumentation và đo actual batches, prepared statements, `getGeneratedKeys()` behavior, throughput và DB metrics.

---

## 21. Ví dụ flush/clear khi ghi nhiều entities

Ghi 10.000 entities trong một persistence context mà không clear có thể tiêu tốn memory cho managed objects, snapshots và dirty checking.

```java
public void insertMany(
        EntityManager em,
        List<OrderInput> inputs,
        int flushChunkSize) {

    int index = 0;

    for (OrderInput input : inputs) {
        PurchaseOrder order =
            createOrderEntity(input);

        em.persist(order);
        index++;

        if (index % flushChunkSize == 0) {
            em.flush();
            em.clear();
        }
    }

    em.flush();
    em.clear();
}
```

Đoạn trên giả định caller đã mở transaction và `createOrderEntity` là factory phù hợp. Cần kiểm tra relationships, cascades và những references còn được giữ bởi caller trước khi clear.

### 21.1. flushChunkSize khác JDBC batch_size

`flushChunkSize` quyết định bao nhiêu managed entities được xử lý mỗi flush/clear. `batch_size` quyết định provider/driver nhóm SQL ra sao. Thường có liên hệ nhưng không đồng nghĩa.

### 21.2. clear làm detach entities

Sau `em.clear()`, các entity references trước đó không còn managed. Nếu application định tiếp tục sửa chúng hoặc dựa vào lazy associations, behavior thay đổi.

### 21.3. Không flush/clear mỗi row nếu muốn tối ưu

Flush sau mỗi `persist` có thể phá batching/write-behind. Hãy đo chunk sizes phù hợp với memory và transaction budget.

### 21.4. Transaction size vẫn quan trọng

Một transaction lớn có thể giữ locks lâu, tạo WAL/undo lớn và tăng thời gian rollback khi lỗi. Một benchmark tốt thử cả batch sizes và transaction sizes thay vì chỉ tối ưu ID generator.

---

## 22. Vì sao nhiều entity types có thể làm batching kém?

Ví dụ persist xen kẽ:

```java
for (OrderInput input : inputs) {
    em.persist(new PurchaseOrder(...));
    em.persist(new OrderAudit(...));
    em.persist(new OutboxMessage(...));
}
```

Các INSERT có thể xen kẽ ba SQL statements khác nhau:

```text
INSERT orders(...)
INSERT audit(...)
INSERT outbox(...)
INSERT orders(...)
INSERT audit(...)
INSERT outbox(...)
```

Nếu provider không reorder, mỗi nhóm SQL có thể ngắn. Với `SEQUENCE`/assigned IDs, provider thường có thêm tự do sắp xếp INSERT; `IDENTITY` có thể buộc một số statements chạy sớm hơn.

### 22.1. order_inserts có trade-off

Hibernate `hibernate.order_inserts` có thể giúp gom statements cùng entity type nhưng tốn sorting/preparation work. Điều kiện FK, cascade và entity graph vẫn cần được provider tôn trọng.

### 22.2. Đo trên graph thật

Một benchmark chỉ ghi `SimpleEntity(id,name)` không thể đại diện workload có Order, Lines, Audit và Outbox.

### 22.3. Không tự reorder quan hệ trái constraint

Nếu child FK chưa có parent row và constraints được kiểm tra ngay, việc gửi child INSERT trước parent sẽ thất bại. Không tự sửa SQL queue của ORM chỉ để có batch size lớn hơn.

---

## 23. Sequence pooling trong hệ thống nhiều application instances

Giả sử có ba pods cùng ghi Order:

```text
Pod A --+
Pod B --+--> Database sequence / generator
Pod C --+
```

Nếu provider pooling đúng:

```text
Pod A nhận block A
Pod B nhận block B
Pod C nhận block C
```

Các blocks không được overlap.

### 23.1. Provider/DB phải thống nhất thuật toán

Không thể tùy tiện đặt một giá trị `allocationSize` ở Java nhưng giữ cấu hình DB sequence không tương thích. Cần xác minh DDL, generator optimizer, application versions và migration order.

### 23.2. Rolling deployment gây rủi ro cấu hình lệch

Nếu pod mới dùng pooled allocation 50 còn pod cũ dùng một allocation pattern khác trên cùng sequence, migration phải được lên kế hoạch cẩn thận. Không chỉ đổi annotation và deploy dần mà không kiểm tra compatibility.

### 23.3. Gaps giữa blocks là bình thường

Pod A restart khi còn 20 unused IDs; chúng có thể bị bỏ qua. Đừng coi gaps là duplicate hoặc lost business transactions.

### 23.4. Không cần global ordering tuyệt đối

ID của Order A nhỏ hơn Order B không đảm bảo A commit trước B. Sequence allocation, transaction duration và concurrency có thể làm commit order khác key order.

---

## 24. TABLE generator trong nhiều nodes

Khi nhiều pods cùng sử dụng một generator row, có thể thấy:

```text
Pod A SELECT/UPDATE id_generator row -> lock
Pod B chờ row lock
Pod C chờ row lock
...
```

### 24.1. Hotspot trên generator table

Ngay cả khi Orders được ghi vào nhiều partitions, việc cấp ID có thể phải đi qua một row chung, khiến throughput bị giới hạn ở serialization point.

### 24.2. allocationSize làm giảm tần suất lock

Nếu một generator operation cấp nhiều IDs, số lần khóa row có thể giảm. Nhưng vẫn cần đo p95/p99 allocator latency và lock waits.

### 24.3. Không nhầm row contention với DB CPU

Một hệ thống có throughput thấp nhưng CPU database chưa cao có thể đang đợi locks hoặc network round trips. Quan sát wait events, lock queues và transaction durations.

### 24.4. Shared generator table là một quyết định kiến trúc

Nếu generator rows phân biệt entity types theo segment, contention có thể giảm. Nhưng JPA provider vẫn phải duy trì tính đúng khi nhiều instances và rollback.

---

## 25. So sánh bằng mô hình chi phí định tính

Tổng latency khi ghi có thể hình dung:

```text
Total write latency
  ~= ID allocation cost
   + SQL statement preparation
   + network/driver round trips
   + DB INSERT/constraint/index work
   + lock waits
   + flush and persistence context work
   + transaction COMMIT
   + application business work
```

Đây là **mô hình định tính**, không phải công thức dự báo chính xác.

### 25.1. Không tối ưu yếu tố nhỏ nhất

Nếu mỗi request gọi payment gateway mất 300 ms còn ID allocation chỉ 1 ms, thay strategy có thể không cải thiện p95 endpoint đáng kể.

### 25.2. Nhưng batch writes có cost distribution khác

Nếu tạo 100.000 rows mà mỗi row cần riêng một ID allocation call, chi phí mạng có thể tích lũy đáng kể. Pooling/batching lúc này quan trọng hơn.

### 25.3. Throughput và latency không giống nhau

Một strategy có thể tăng tổng rows/s nhưng p99 dưới concurrency cao tăng vì lock waits. Benchmark cần đo cả hai.

### 25.4. CPU/disk và network

Một strategy giảm network round trips nhưng làm random index writes tăng có thể không tốt ở IO-bound workload. Kết quả đo toàn stack mới đáng tin.

---

## 26. Ma trận ưu/nhược điểm định tính

| Tiêu chí | IDENTITY | SEQUENCE có pooling | TABLE có pooling | App UUID/assigned |
|---|---|---|---|---|
| ID có trước INSERT | Thường không | Thường có | Thường có | Có |
| Cấp ID cần SQL riêng | Không nhất thiết, ID từ INSERT | Theo block allocation | Theo generator table | Không nếu local |
| JDBC insert batching trong Hibernate phổ biến | Thường hạn chế | Thường thuận lợi | Có thể thuận lợi | Có thể thuận lợi |
| Hotspot tại generator row | Không | Không có row generator riêng | Có thể cao | Không nếu local |
| Database sequence object cần thiết | Không | Có | Không | Không |
| ID gaps sau rollback/restart | Có thể | Có | Có | Không theo dãy, nhưng không áp dụng notion gap |
| Index locality | Thường tăng dần | Thường tăng dần theo allocation, không tuyệt đối theo commit order | Thường tăng dần | Tùy UUID/random/time ordered |
| PK/FK width | Thường BIGINT | Thường BIGINT | Thường BIGINT | UUID binary rộng hơn BIGINT |
| Multi-node uniqueness | DB đảm bảo | DB/provider algorithm | Row lock/DB | Generator + DB constraint |
| Khả năng portability khi đổi DB | Tùy dialect | Phụ thuộc sequence support | Rộng hơn về cấu trúc nhưng vẫn vendor details | UUID type/generator mapping tùy DB |
| Khả năng tuning | Identity/driver/ORM | allocation/pooling/batching | allocation/lock partition | Format/generator/index |

Đây là bảng định hướng **không thay benchmark**. Đặc biệt, “SEQUENCE có pooling” không đồng nghĩa mọi sequence generator đều đã được cấu hình đúng pooled optimizer.

---

## 27. Database-specific considerations

### 27.1. PostgreSQL

PostgreSQL hỗ trợ identity columns, sequences, native `uuid` type và các dạng `INSERT ... RETURNING`. Dùng `IDENTITY` ở JPA có thể đi qua identity-generated-key path dù phía DB identity được hỗ trợ bằng sequence machinery. Điều quan trọng là **provider chọn cách lấy ID và batching** nào.

Với workload INSERT lớn, một sequence strategy được cấu hình pooling/batching đúng thường đáng thử.

### 27.2. MySQL

MySQL phổ biến với `AUTO_INCREMENT`. Lựa chọn `IDENTITY` có thể là tự nhiên, nhưng nếu Hibernate insert batching là yêu cầu lớn, cần đo giải pháp bulk JDBC, assigned IDs hoặc generator phù hợp. Không mặc định PostgreSQL SEQUENCE config có thể copy nguyên sang MySQL.

### 27.3. Oracle

Oracle có native sequences và nhiều khả năng tối ưu theo driver/DB version. Sequence-based generators thường là lựa chọn đáng đánh giá; `RETURNING`/batching APIs và JDBC version cũng ảnh hưởng performance.

### 27.4. SQL Server

SQL Server hỗ trợ identity và sequence objects trong các versions phù hợp. ORM dialect và driver strategy quyết định generated-key retrieval/batching. Cần đo trên SQL Server thật và index design tương ứng.

### 27.5. H2 và test database

H2 tiện cho integration tests nhưng thường không đại diện cho lock behavior, SQL dialect, network RTT hoặc optimizer của production database. Không chọn chiến lược production chỉ dựa trên benchmark H2 in-memory.

### 27.6. Distributed SQL databases

Một số distributed SQL engines có identity/sequence/locality semantics riêng. Cần hiểu khả năng cấp IDs, hotspot distribution và transaction retry protocol. Không mặc định một SEQUENCE hoặc UUID theo tên có cost giống single-node PostgreSQL.

---

## 28. Định nghĩa workload trước khi benchmark

Một benchmark công bằng phải bắt đầu từ câu hỏi:

- Ghi một entity mỗi request hay nhiều entities mỗi transaction?
- Mỗi Order có bao nhiêu Lines?
- Bao nhiêu tenants và app nodes?
- Write-only hay read/write mixed?
- Inserts xen kẽ updates/deletes không?
- Có high-cardinality indexes/unique constraints không?
- 95th percentile transaction chứa bao nhiêu rows?
- Database đặt cùng data center hay qua WAN?
- Throughput mục tiêu là bao nhiêu Orders/s và rows/s?
- P95/P99 latency budget?
- Node count, CPU, heap, connection pool và driver version?
- Các yếu tố business I/O khác có làm kết quả bị che không?

### 28.1. Benchmark giả lập phải giống SQL shape thực

Nếu production ghi Order + 10 Lines + 1 Audit + 1 Outbox, benchmark nên có một profile tương ứng, không chỉ persist 100.000 entity chỉ có `name`.

### 28.2. Không dùng query count thay throughput

Query count giảm không nhất thiết p95 giảm khi bottleneck là disk I/O hoặc index contention. Ngược lại, một sequence call thêm có thể không đáng kể nếu JDBC batching giảm round trips lớn.

### 28.3. Dùng cùng schema/constraints

So sánh `IDENTITY` trên bảng có nhiều indexes với `SEQUENCE` trên bảng đơn giản sẽ không công bằng. Hãy giữ cấu trúc bảng, columns, indexes, FK constraints và data distribution tương đương tối đa.

---

## 29. Thiết kế một ma trận benchmark tối thiểu

| Profile | Rows/transaction | Concurrent workers | Strategy | Allocation | JDBC batch | Ghi chú |
|---|---:|---:|---|---:|---:|---|
| A | 1 | 1 | IDENTITY | N/A | Theo provider | Baseline request lẻ |
| B | 1 | 1 | SEQUENCE | 1 | 1 | Sequence từng ID |
| C | 1 | 1 | SEQUENCE | 50 | 50 | Pooling có thể ít lợi khi chỉ một row |
| D | 100 | 1 | IDENTITY | N/A | 50 | Đo actual utilization |
| E | 100 | 1 | SEQUENCE | 50 | 50 | Kiểm tra pooling/batching |
| F | 100 | 16 | SEQUENCE | 50 | 50 | Concurrency |
| G | 100 | 16 | TABLE | 50 | 50 | Contention |
| H | 100 | 16 | UUID app-assigned | N/A | 50 | Index trade-off |
| I | 10 | 16 | IDENTITY vs SEQUENCE | Theo config | 50 | Parent + children |
| J | 1000 | 4 | SEQUENCE | 50/100 | 25/50/100 | Tuning sensitivity |

Đây là **ma trận đề xuất**, không phải benchmark kết quả đã đo. Những giá trị như 16 workers hay 50 batch size chỉ là tham số thử, cần điều chỉnh theo production profile.

### 29.1. Warm-up

JIT compilation, connection pool, DB buffer cache và statement cache có thể ảnh hưởng những phút đầu. Thử cold và steady-state riêng.

### 29.2. Run đủ dài để quan sát p99

Một vài trăm inserts thường không đủ để kết luận tail latency dưới contention.

### 29.3. Lặp lại và ghi độ phân tán

Nếu một profile chạy nhanh trong một lần nhưng chậm trong lần khác do DB background work, nên ghi nhiều runs và spread, không chỉ lấy “best run”.

### 29.4. Quản lý dữ liệu benchmark

Mỗi run cần có dataset strategy tránh duplicate constraints, index bloat từ những runs trước hoặc transaction cleanup làm lệch kết quả.

---

## 30. Những metrics cần đo

| Metric | Tại sao quan trọng |
|---|---|
| Orders/s hoặc rows/s | Throughput tổng |
| P50/P95/P99 commit latency | Tail latency người dùng/worker thấy |
| JDBC prepared statements | Hiểu chi phí chuẩn bị SQL |
| SQL executions/round trips | Quan sát cấp ID và INSERT |
| JDBC batch execution count và batch size thực | Xác nhận batching có xảy ra |
| Sequence NEXTVAL calls | Đo allocation overhead |
| TABLE generator lock wait time | Phát hiện hotspot |
| DB CPU | CPU-bound vs lock/network-bound |
| DB WAL/redo bytes, fsync | Chi phí durable writes |
| Index size/page splits | Ảnh hưởng key locality |
| Connection pool wait time | Bottleneck connection allocation |
| Heap/GC allocation | Tác động persistence context/generator |
| Transaction rollback rate | Tính ổn định và cost failures |
| Duplicate PK/constraint failures | Correctness |
| Latency của ID allocation | Tách cost generator |
| Network RTT | Hiểu giá trị của giảm round trips |

### 30.1. Không đọc SQL log như JDBC batch telemetry hoàn chỉnh

ORM SQL log có thể in cùng INSERT nhiều lần dù driver gom batch. Cần instrumentation phù hợp cho JDBC batches và DB-side statements nếu muốn kết luận batch utilization.

### 30.2. Hibernate Statistics

Một số phiên bản Hibernate hỗ trợ statistics APIs và logging để quan sát entity inserts, prepared statements và related metrics. Chúng là Hibernate-specific, không thuộc JPA `EntityManager` portable API.

### 30.3. DB-side metrics

PostgreSQL có các views/extensions quan sát waits/queries/WAL; MySQL/Oracle/SQL Server có diagnostics riêng. Phải đọc actual metrics của DB target để kiểm chứng bottleneck.

### 30.4. Không quên end-to-end latency

Nếu insert batch tăng throughput nhưng request p99 tăng đáng kể do queueing hoặc transaction size, cần cân bằng theo service SLO.

---

## 31. Benchmark code khung với EntityManager

Một harness minh họa, chạy trong môi trường test độc lập:

```java
public record InsertResult(
    int inserted,
    long elapsedNanos
) {}

public InsertResult runInsertBatch(
        EntityManagerFactory emf,
        int count,
        int flushChunk) {

    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    long start = System.nanoTime();

    try {
        tx.begin();

        for (int i = 0; i < count; i++) {
            BenchOrder order =
                new BenchOrder("batch-" + i);

            em.persist(order);

            if ((i + 1) % flushChunk == 0) {
                em.flush();
                em.clear();
            }
        }

        em.flush();
        tx.commit();

        return new InsertResult(
            count,
            System.nanoTime() - start
        );

    } catch (RuntimeException failure) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw failure;

    } finally {
        em.close();
    }
}
```

`BenchOrder` cần được ánh xạ với chiến lược ID tương ứng; command này chỉ đo một workload đơn giản, không có FK/extra effects. `transaction commit` nằm trong timing, nhưng nếu cần tách DB ID allocation/flush/commit overhead hãy instrument rõ từng phase.

### 31.1. Chọn transaction size có chủ đích

Ví dụ này dùng **một transaction** cho count entities, với flush/clear định kỳ. Production có thể chia thành nhiều transactions để giảm lock durations/rollback cost; cần benchmark thêm profile đó.

### 31.2. Đừng bỏ commit ra khỏi phép đo một cách vô tình

Thời điểm kết thúc transaction ảnh hưởng latency và durable write throughput. Một microbenchmark chỉ đo `em.persist()` có thể chỉ đo scheduling trong memory.

### 31.3. Tránh trùng order number giữa runs

Một value `"batch-"+i` lặp lại qua runs sẽ vi phạm UNIQUE nếu không reset schema hoặc tạo run ID. Benchmark harness phải thiết kế dữ liệu riêng cho mỗi run.

### 31.4. Không sử dụng 1 shared EntityManager giữa threads

`EntityManager` không thread-safe. Mỗi worker cần EntityManager/transaction riêng theo framework contract.

---

## 32. Benchmark nhiều threads và app nodes

Một benchmark concurrency cần kiểm soát:

```text
Worker 1: EntityManager A -> transactions
Worker 2: EntityManager B -> transactions
Worker 3: EntityManager C -> transactions
...
Worker N: EntityManager N -> transactions
```

### 32.1. Tăng concurrency theo bậc

Thử 1, 2, 4, 8, 16, 32 workers (tham số minh họa) và đo throughput/latency/lock waits. Đừng bắt đầu ngay 500 workers rồi quy mọi lỗi cho generator.

### 32.2. Connection pool đủ nhưng không quá lớn

Nếu pool chỉ có 5 connections, 100 workers có thể chủ yếu chờ pool thay vì cạnh tranh sequence/table generator. Ngược lại pool quá lớn có thể làm DB quá tải.

### 32.3. Đa node mới phát hiện một số contention

TABLE generator row và pooled sequence blocks có behavior khác khi nhiều JVMs. Nếu production có 10 pods, test 1 JVM vẫn chưa đủ.

### 32.4. Ràng buộc CPU/network

Nếu benchmark chạy app và DB cùng máy, network latency quá thấp có thể che lợi ích của batching/round-trip reduction so với topology production.

### 32.5. Database isolation và lock waits

Ghi cùng một set của business keys có thể gây unique conflicts che kết quả generator benchmark. Cần dữ liệu phân phối hợp lý và đo riêng test contention.

---

## 33. So sánh JPA entity inserts với JDBC/native bulk inserts

Một ứng dụng nhập dữ liệu lớn có thể lựa chọn:

1. `em.persist` nhiều managed entities.
2. Hibernate `StatelessSession` hoặc provider-specific bulk API.
3. JDBC `PreparedStatement.addBatch`/`executeBatch`.
4. Native multi-row INSERT, `COPY`/bulk loader hoặc cơ chế DB riêng.

### 33.1. Không so sánh thiếu công bằng

JPA entity persist còn thực hiện identity management, cascades, lifecycle callbacks, dirty checking và mapping. Native bulk INSERT có thể bỏ qua các cơ chế đó, nên thường có cost model khác.

### 33.2. Khi IDENTITY gây hạn chế JPA batching

JDBC batch/native bulk loader có thể vẫn ghi nhiều rows vào identity table nhanh, do driver/SQL có chiến lược khác. Điều đó không có nghĩa JPA IDENTITY path đã tự batch.

### 33.3. Bulk JPQL UPDATE không giúp sinh ID

JPQL bulk UPDATE/DELETE xử lý các rows tồn tại, không phải một API portable chuẩn cho bulk INSERT entities mới. Không dùng nó làm “giải pháp” trực tiếp cho id generation.

### 33.4. Lifecycle và integrity

Nếu chọn native bulk load, cần bảo đảm business validation, audit fields, versioning, unique/FK constraints và event generation được xử lý ở tầng tương ứng.

---

## 34. Migration từ IDENTITY sang SEQUENCE

Một hệ thống đã dùng `IDENTITY` nhiều năm có thể muốn chuyển sang SEQUENCE để cải thiện batching. Nhưng migration không chỉ đổi annotation.

### 34.1. Những vấn đề cần kiểm tra

- DB có hỗ trợ sequence và default generator semantics phù hợp?
- Existing PK lớn nhất là bao nhiêu?
- Sequence start/next value có tránh trùng IDs hiện hữu?
- ORM version có hỗ trợ pooled optimizer đã chọn?
- Database sequence increment có khớp allocationSize?
- Các services/jobs khác còn dùng identity default cũ?
- Rolling deployment có thể trộn hai strategies trong thời gian chuyển đổi không?
- Schema migrations, backup/rollback plan và data recovery?
- Foreign keys/reference semantics có giữ nguyên không?
- Có consumers ngoài hệ thống phụ thuộc ID tăng liên tục/ordering không?

### 34.2. Đừng reset sequence về 1 khi bảng đã có dữ liệu

Cần start sequence sau phạm vi IDs hiện hữu, với kế hoạch bảo vệ concurrent inserts.

### 34.3. Đừng kết hợp ID allocators không đồng bộ

Một service tiếp tục dùng identity default, service khác lấy explicit sequence ID nhưng cả hai không chia sẻ allocator protocol có thể tạo collisions. Cần thiết kế migration toàn hệ thống.

### 34.4. Rollback deployment không chỉ là revert code

Nếu database schema/generator đã đổi, phiên bản cũ có thể không tương thích. Migration cần version compatibility plan.

---

## 35. Migration sang UUID cần nhìn cả toàn bộ schema

Chuyển `BIGINT` PK sang UUID có thể phải thay:

- PK columns.
- FKs ở các bảng children.
- Join tables.
- Composite indexes.
- Message payloads.
- API identifiers và client caches.
- Data warehouse/analytics keys.
- Audit logs và external integrations.
- Backfill rules và dual-write/dual-read migration.

### 35.1. Không chỉ thêm một @GeneratedValue

Một entity thay `Long id` thành `UUID id` làm thay domain types, mapping, queries và serialization contracts.

### 35.2. Index/storage cost cộng dồn

Một Order ID được tham chiếu bởi hàng triệu Lines/Events có thể làm FK indexes lớn hơn khi đổi từ BIGINT sang UUID. Nên đo toàn bộ schema chứ không chỉ bảng Orders.

### 35.3. Thứ tự tăng không còn mặc định

Nếu application đang sort theo `id DESC` để lấy record mới nhất, random UUID phá giả định đó. Dùng `createdAt` + stable tie-breaker hoặc ordered ID design phù hợp.

---

## 36. Hiệu năng và tính nhất quán khi transaction rollback

Sequence/identity allocation có thể tạo ID chưa được sử dụng:

```text
Transaction A: lấy ID 100
Transaction A: INSERT
Transaction A: ROLLBACK

Transaction B: lấy ID 101
Transaction B: COMMIT
```

Row 100 có thể không tồn tại; đây là behavior bình thường của nhiều generators.

### 36.1. Không chờ “trả lại” ID

Database sequences nói chung không transactional theo nghĩa hoàn lại NEXTVAL đã cấp khi transaction rollback. Trả lại/đánh lại ID có thể gây race và phá uniqueness.

### 36.2. ID không chứng minh commit

Một entity có assigned UUID hoặc sequence ID trước khi persist không có nghĩa bản ghi đã xuất hiện trong DB. Flush thành công vẫn chưa có commit.

### 36.3. Commit ACK loss là bài toán khác

Nếu connection bị đứt khi COMMIT, transaction có thể đã commit dù client nhận exception. Cần idempotency/business request keys/transaction receipt nếu muốn retry tạo Order an toàn, không chỉ nhìn ID generator.

### 36.4. Reusing generated ID sau failure không đơn giản

Một detached entity từ transaction hỏng có thể giữ ID dù row không tồn tại, hoặc row đã commit nhưng client chưa biết. Không tự gọi `persist` lại bằng ID cũ trong cùng EntityManager với giả định rollback chắc chắn; recovery phải theo hợp đồng transaction và business identity.

---

## 37. ID generation và idempotent retry

Một request tạo Order nên có **business request ID** ổn định, độc lập với strategy sinh technical primary key.

Ví dụ:

```java
@Entity
@Table(
    name = "purchase_order",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_order_tenant_request",
        columnNames = {"tenant_id", "request_id"}
    )
)
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(name = "request_id", nullable = false)
    private String requestId;
}
```

Nếu client retry cùng request sau network failure, UNIQUE `(tenant_id,request_id)` mới bảo vệ “một command không tạo hai Orders”; kỹ thuật `SEQUENCE` hay `IDENTITY` chỉ bảo vệ technical primary key uniqueness.

### 37.1. Technical ID mới không làm retry business operation mới

Một request có thể được gửi lại nhiều lần với cùng operation key, và service phải trả cùng result nếu first attempt đã thành công.

### 37.2. Không gửi email/charge trước commit

Dù ID đã có sớm, external side effects phải dùng outbox/after-commit/other transaction-aware design. Sinh khóa nhanh không giải quyết distributed consistency.

### 37.3. Business uniqueness cần ràng buộc DB

Hai transactions đều `SELECT` thấy chưa có request_id có thể cùng INSERT. Unique constraint quyết định.

---

## 38. Lưu ý equals/hashCode khi ID được sinh muộn

Một entity với:

```java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
```

thường có `id == null` trước persist.

### 38.1. HashSet và ID thay đổi

Nếu `hashCode()` dựa hoàn toàn vào generated ID và object được đưa vào HashSet khi ID null, sau persist ID xuất hiện có thể thay hash code và làm `HashSet.contains()` hoạt động sai.

### 38.2. Không dùng mutable generated ID trong hashCode thiếu cân nhắc

Entity equality strategy cần nhất quán theo lifecycle, inheritance và proxy semantics. Có nhiều pattern, không có một cách chung hoàn hảo cho mọi entity.

### 38.3. Application-assigned IDs có thể đơn giản hóa một phần

UUID được tạo ngay trong constructor giúp ID ổn định trước persist, nhưng còn vấn đề merge/detach, persistence identity và domain equality.

### 38.4. Benchmark không để equality bug ảnh hưởng data graph

Nếu quan hệ `Set<OrderLine>` vô tình mất item do hashCode đổi sau persist, kết quả insert count sai. Test correctness trước khi đo throughput.

---

## 39. Thứ tự ID và order thời gian không giống nhau

Ngay cả với sequence tăng dần:

```text
Tx A cấp ID=100, xử lý chậm
Tx B cấp ID=101, commit trước
Tx A commit sau
```

Bản ghi có ID lớn hơn có thể được commit trước. Vì vậy:

```sql
ORDER BY id DESC
```

không phải một định nghĩa portable rằng “record mới commit gần đây nhất”.

### 39.1. Dùng thời gian và tie-breaker phù hợp

Nếu requirement là latest by creation time, dùng `created_at DESC, id DESC` khi fields có contract tương ứng. Nếu cần **commit order** thực sự, phải thiết kế cơ chế khác theo DB/event log semantics.

### 39.2. Sequence caches có thể làm ID ordering không đều giữa nodes

Một pod có thể giữ block IDs thấp hơn trong khi pod khác đã cấp những IDs cao hơn. Thứ tự cấp ID giữa nodes không phải thứ tự transaction completion.

### 39.3. UUIDv7 cũng không phải commit-order oracle

Time-ordered UUID có thể phản ánh generator time, không bảo đảm transaction start/commit order tuyệt đối.

---

## 40. Những lỗi cấu hình thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Ghi hàng loạt vẫn có 1 INSERT/round trip | IDENTITY path không batch | JDBC/provider metrics |
| Đổi sang SEQUENCE nhưng vẫn chậm | allocationSize=1, bottleneck khác | NEXTVAL count, batch utilization |
| Hibernate báo sequence increment mismatch | DDL khác optimizer allocation | Cấu hình sequence và annotation |
| Duplicate PK sau đổi generator | Phối hợp allocator sai/migration | DB sequence state, rolling deploy |
| TABLE generator p99 tăng mạnh | Shared generator row lock | DB lock waits |
| UUID benchmark memory cao | Index/key size, persistence context | Heap/DB index size |
| Random UUID query index chậm | Page fragmentation/cache locality | DB physical metrics |
| @GeneratedValue(AUTO) đổi SQL sau upgrade | Provider strategy thay | Effective generator/DDL |
| Spring Data `save` phát SELECT trước INSERT | Assigned ID bị coi là existing | isNew/merge semantics |
| Đổi allocationSize nhưng không nhanh | Network/DB WRITE là bottleneck khác | Tracing end-to-end |
| Chỉ đo persist() thấy cực nhanh | SQL deferred tới flush/commit | Đo commit |
| Batch_size=50 nhưng actual batches nhỏ | SQL interleaving/dialect/identity | Driver/provider stats |
| EntityManager heap tăng | Quá nhiều managed entities | Flush/clear chunk |
| `OrderLine` FK lỗi | SQL ordering/owning side sai | Graph mapping, flush order |
| Gaps trong sequence bị coi là data loss | Allocation/cache/rollback | Phân biệt ID với business sequence |
| ID tồn tại nhưng Order chưa commit | ID cấp trước commit | Transaction status/readback |
| Benchmark H2 khác production | Dialect/network/storage khác | Test DB target |
| Throughput tăng nhưng p99 xấu | Lock contention/queueing | Tail latency/waits |
| Sequence generator nóng khi nhiều nodes | Pooling/config/RTT | Block allocation metrics |
| Snowflake IDs trùng sau deploy | Node ID/clock bug | Unique constraint/generator logs |

---

## 41. Bài tập thực hành

### Bài 1. IDENTITY có ID trước INSERT không?

**Đáp án:** Thông thường database cấp key trong INSERT; provider cần lấy generated key sau/đồng thời INSERT, nên có thể phải chạy INSERT sớm.

### Bài 2. SEQUENCE giúp batch vì sao?

**Đáp án:** Provider thường có thể lấy ID trước INSERT và xếp nhiều entity inserts để JDBC batch.

### Bài 3. allocationSize=50 là batch_size=50?

**Đáp án:** Không. Một cái liên quan ID allocation, cái kia liên quan SQL batching.

### Bài 4. PostgreSQL sequence CACHE 100 có thay provider pooling?

**Đáp án:** Không. Database sequence cache tối ưu nội bộ DB; nó không bảo đảm provider chỉ gọi NEXTVAL một lần cho 100 entities.

### Bài 5. Tại sao DB sequence increment phải được kiểm tra?

**Đáp án:** Một số pooled optimizers cần increment khớp allocationSize. Sai config có thể startup fail hoặc rủi ro cấp ID sai tùy provider.

### Bài 6. TABLE generator bị chậm ở 32 workers?

**Đáp án:** Có thể do lock hotspot tại generator row. Đo DB lock waits và thử pooling/alternative generator.

### Bài 7. IDENTITY luôn chậm hơn UUID?

**Đáp án:** Không thể khẳng định. Workload, provider/driver, DB index strategy và batch usage quyết định.

### Bài 8. AUTO chọn chiến lược gì?

**Đáp án:** Provider/dialect/version quyết định. Phải xác minh effective generator.

### Bài 9. `GenerationType.UUID` có trong JPA 2.2?

**Đáp án:** Không phải API chuẩn của JPA 2.2; UUID strategy được chuẩn hóa ở Jakarta Persistence 3.1.

### Bài 10. UUID có chi phí index nào?

**Đáp án:** Key rộng hơn BIGINT, random UUID có thể giảm B-tree locality; mức tác động tùy DB/storage/indexes.

### Bài 11. UUIDv7 có luôn được JPA GenerationType.UUID sinh không?

**Đáp án:** Không. Phải kiểm tra/version/provider hoặc dùng generator riêng.

### Bài 12. Assigned UUID và Spring Data save phát SELECT?

**Đáp án:** Có thể do isNew detection coi non-null ID như existing, dẫn đến merge path. Kiểm tra repository semantics.

### Bài 13. Batch insert 10.000 rows phải đo thời gian nào?

**Đáp án:** Đo end-to-end gồm flush/commit, không chỉ vòng lặp persist.

### Bài 14. Tại sao phải có unique request ID?

**Đáp án:** Technical ID generation không ngăn retry cùng business command tạo hai Order IDs.

### Bài 15. Vì sao có gaps?

**Đáp án:** Sequence/identity allocations có thể không transactional, rollback/restart/caching bỏ qua IDs. Gaps không chứng minh data loss.

### Bài 16. `@Version` ngăn duplicate create khi retry?

**Đáp án:** Không. Hai Orders khác IDs không conflict optimistic locking; cần unique business operation key.

### Bài 17. `HashSet` chứa entity với ID null rồi ID thay đổi?

**Đáp án:** hashCode dựa trên mutable generated ID có thể làm set mất khả năng tìm phần tử. Cần equality strategy phù hợp.

### Bài 18. Ghi Order và 10 Lines, IDENTITY vs SEQUENCE?

**Đáp án:** Cần đo insert ordering, generated key retrieval, FK constraints và batching trên graph thật.

### Bài 19. Vì sao TABLE không dùng nếu có sequence?

**Đáp án:** TABLE có thể thêm row lock/DML overhead. Nhưng quyết định thực tế vẫn dựa DB/provider/benchmark.

### Bài 20. Một Order được cấp ID rồi transaction rollback?

**Đáp án:** ID trong Java không chứng minh row đã committed; rollback có thể bỏ row và ID gap còn tồn tại.

### Bài 21. ORDER BY ID DESC có trả commit mới nhất?

**Đáp án:** Không bảo đảm với sequence allocation và concurrency; cần business ordering semantics riêng.

### Bài 22. Batch_size=50 nhưng actual batch count thấp?

**Đáp án:** Có thể do IDENTITY, SQL shape xen kẽ, flush mỗi row hoặc provider/driver limitation.

### Bài 23. Đổi BIGINT sang UUID có dễ không?

**Đáp án:** Không chỉ đổi annotation; phải migrate PK/FK/index/API references và kiểm soát rollout.

### Bài 24. Benchmark trên H2 đủ chưa?

**Đáp án:** Không cho kết luận production performance. Dùng DB/dialect/topology đại diện production.

### Bài 25. NUM workers tăng gấp đôi nhưng throughput không tăng?

**Đáp án:** Có bottleneck DB, pool, locks, generator hoặc I/O; đọc wait events và latency distribution.

### Bài 26. Một app pod giữ unused sequence block rồi restart?

**Đáp án:** Những IDs có thể bị bỏ qua. Đây là trade-off thường chấp nhận cho throughput.

### Bài 27. UUID làm authorization không cần thiết?

**Đáp án:** Không. Dù ID khó đoán, API phải kiểm tra quyền truy cập.

### Bài 28. Một entity chỉ có String name, performance tốt trên SEQUENCE?

**Đáp án:** Chưa đủ kết luận cho workload có relationships, callbacks, audit, outbox, constraints và nhiều indexes.

### Bài 29. `@TableGenerator` dùng nhiều segments?

**Đáp án:** Có thể giảm contention so với một global row; vẫn cần đo locking overhead và provider strategy.

### Bài 30. Khi nào dùng JDBC COPY/bulk loader?

**Đáp án:** Khi nhập dữ liệu lớn và chấp nhận thiết kế riêng xử lý lifecycle, validation, audit, generated keys và constraints. Nó không phải cùng workload với JPA entity persist.

---

## 42. Checklist trước khi chọn chiến lược sinh khóa

1. Đã xác định database/dialect, JPA provider và phiên bản?
2. Đã kiểm tra API version có `GenerationType.UUID`?
3. Đã phân biệt technical PK và business identifier?
4. Có yêu cầu IDs biết trước INSERT?
5. Có workload create 1 row hay nhiều rows mỗi transaction?
6. Có quan hệ parent/children và cascade phức tạp?
7. Có JDBC batching được bật và đang hoạt động thực?
8. Có đo actual batches thay vì chỉ đọc property config?
9. Có đo sequence NEXTVAL calls?
10. Có hiểu provider allocation optimizer?
11. Có khớp allocationSize với DB sequence DDL/optimizer?
12. Có phân biệt DB sequence CACHE với provider pooling?
13. Có chấp nhận ID gaps khi rollback/restart?
14. Có nhiều app nodes dùng chung generator?
15. Có rolling migration giữa các generator versions?
16. Có TABLE generator hotspot tại shared row?
17. Có đánh giá UUID binary/text physical storage?
18. Có đánh giá index width/FK index cost?
19. Có đánh giá random vs ordered ID locality?
20. Có phụ thuộc `ORDER BY id` cho nghiệp vụ thời gian?
21. Có test `@Version` và assigned ID new-state detection?
22. Có tránh hashCode thay đổi khi generated ID được cấp?
23. Có đo JDBC round trips, prepared statements, WAL và DB locks?
24. Có đo p50/p95/p99 và throughput nhiều concurrency levels?
25. Có test trên actual production-like database topology?
26. Có so sánh cùng schema/indexes/constraints?
27. Có benchmark parent/child/audit/outbox graph?
28. Có cân nhắc flush/clear chunk và transaction size?
29. Có kiểm tra generated ID không phải committed proof?
30. Có unique request/business key để retry an toàn?
31. Có test constraint violation/rollback/restart/generator gaps?
32. Có migration/rollback plan nếu thay strategy?
33. Có metrics trước/sau rollout?
34. Có ghi rõ trade-offs về portability và provider-specific settings?
35. Có xác định bottleneck thật trước khi tối ưu generator?

---

## 43. Quy trình ra quyết định

```text
               Cần chọn chiến lược sinh ID cho entity
                                |
                                v
                     Database/provider hỗ trợ gì?
                                |
               +----------------+----------------+
               |                                 |
             Sequence                          Identity
             sẵn có?                           chủ đạo?
               |                                 |
               v                                 v
      Ghi nhiều rows/transaction?       Workload chủ yếu
           /         \                  1 row/request?
          Có         Không               /       \
          |           |                 Có       Không
          v           v                  |         |
    Thử SEQUENCE    Benchmark        IDENTITY   Đánh giá
    + pooling       baseline         có thể đủ  assigned IDs
    + JDBC batch                   nhưng vẫn đo  hoặc bulk path
          |
          v
    Kiểm tra DDL/optimizer
    và generated keys behavior
          |
          +------------------------------------------+
                                                     |
                                                     v
                                     Cần IDs phân tán độc lập DB?
                                            /          \
                                          Có           Không
                                           |             |
                                           v             v
                                   UUID/ordered ID     So sánh actual
                                   + index tests      throughput/latency
                                           |             |
                                           +------+------+
                                                  |
                                                  v
                                     Correctness + FK/index +
                                     concurrency + migration
                                                  |
                                                  v
                                      Chọn profile đáp ứng SLO,
                                      giữ instrumentation và
                                      kiểm thử sau nâng version
```

Trong sơ đồ, `TABLE` là một phương án có điều kiện khi không thể hoặc không muốn dùng native sequence/identity/assigned strategy; cần đánh giá lock contention riêng. `AUTO` có thể là lựa chọn khởi đầu nếu team chấp nhận behavior của provider và đã đo effective generator.

---

## 44. Kết luận

**Sinh khóa là một phần của đường ghi dữ liệu, không chỉ là việc chọn kiểu Long hay UUID cho field `@Id`.** Một strategy ảnh hưởng thời điểm ID xuất hiện, khả năng provider hoãn SQL INSERT, batching, network round trips, lock contention, index locality và chi phí vận hành.

Những điểm quan trọng nhất:

1. **`IDENTITY` thường lấy ID từ INSERT** nên một số ORM như Hibernate có hạn chế batching INSERT đáng kể. Nhưng không kết luận nó luôn chậm ở mọi workload.
2. **`SEQUENCE` thường giúp biết ID trước INSERT**, thuận lợi cho batching; `allocationSize`/pooling có thể giảm NEXTVAL round trips.
3. **`allocationSize` khác JDBC `batch_size`**, và database sequence CACHE khác provider-level ID pooling.
4. **Sequence increment/optimizer phải được cấu hình tương thích**, đặc biệt khi migration hoặc rolling deployment nhiều pods.
5. **`TABLE` generator có thể tạo lock hotspot** do phải cập nhật generator row; pooling có thể giúp nhưng không loại bỏ contention.
6. **`AUTO` phụ thuộc provider/dialect/version**, nên cần xác minh effective strategy thay vì suy luận từ annotation.
7. **`GenerationType.UUID` là chuẩn từ Jakarta Persistence 3.1**; không tự giả định UUIDv7 hoặc một version cụ thể.
8. **UUID/assigned IDs có thể sinh trước INSERT**, nhưng key size, random index writes, FK storage và equality/new-entity detection có trade-offs.
9. **Ghi quan hệ cha–con khác ghi một entity đơn**, vì FK ordering, cascades và SQL shape quyết định batch utilization.
10. **JPA không bắt buộc provider thực hiện batching**, nên phải đo actual JDBC/DB behavior.
11. **Flush/clear chunk và transaction size** ảnh hưởng memory, dirty checking, locks và throughput độc lập với generator.
12. **Benchmark phải bao gồm flush/commit**, DB target, throughput, p95/p99, round trips, lock waits, WAL/index metrics.
13. **ID gaps là bình thường**; sequence/identity values không phải business numbers liên tục và không chứng minh transaction commit.
14. **`@Version` và technical ID uniqueness không thay business idempotency key** khi client retry create operations.
15. **Đổi strategy là migration dữ liệu/DDL/operations**, không chỉ sửa `@GeneratedValue`.
16. **Chọn chiến lược bằng số đo và correctness contract** của ứng dụng, không bằng một câu khẩu quyết “UUID nhanh” hay “IDENTITY chậm”.

Khi đánh giá hiệu năng ghi, hãy đi từ câu hỏi **provider thực sự làm những SQL operations nào để lấy ID và INSERT?**, tiếp theo **bao nhiêu round trips và lock waits được tạo ra?**, cuối cùng **throughput/p95/p99 có cải thiện trên workload đại diện production mà vẫn bảo toàn uniqueness, FK, transaction và retry semantics hay không?**. Đó là cách chọn chiến lược sinh khóa dựa trên bằng chứng thay vì giả định.
