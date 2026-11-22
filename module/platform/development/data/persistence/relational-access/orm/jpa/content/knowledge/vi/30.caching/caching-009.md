# Đánh giá tương tác giữa cache, giao dịch và mức cô lập trong JPA

Khi ứng dụng dùng Jakarta Persistence (JPA), dữ liệu được nhìn thấy bởi một đoạn Java code không chỉ phụ thuộc vào những gì đang nằm trong bảng cơ sở dữ liệu. Kết quả còn chịu ảnh hưởng của:

- **Persistence context**, thường được gọi là **cache cấp 1 (L1)**, nơi JPA quản lý các entity instances theo identity.
- **Shared cache**, thường gọi là **cache cấp 2 (L2)**, được chia sẻ giữa các persistence contexts khi provider và cấu hình hỗ trợ.
- **Query cache** hoặc cache kết quả truy vấn, vốn thường là tính năng **riêng của provider**, không đồng nhất với L2 entity cache.
- **Transaction** đang mở, thời điểm `flush`/`commit`/`rollback` và cách transaction manager quản lý `EntityManager`.
- **Mức cô lập (isolation level)** cùng cơ chế MVCC/locking của database.
- Các writers khác: JPA sessions, native SQL, stored procedures, batch jobs, dịch vụ khác hoặc quản trị viên thao tác trực tiếp vào bảng.

Một tình huống thường gặp:

```text
Transaction A                     Transaction B
---------------------------------------------------------
find(Product#42) -> price=100

                                  update Product#42
                                  price=120
                                  COMMIT

find(Product#42) lần nữa
-> vẫn có thể thấy price=100
   trong cùng EntityManager A
---------------------------------------------------------
```

Kết quả đó **không nhất thiết chứng minh database đang ở REPEATABLE READ**. Ngay cả với database **READ COMMITTED**, lần `find` thứ hai có thể trả lại **cùng managed entity** trong persistence context của A, không gửi SQL đọc lại. Nói cách khác, **database isolation và trạng thái JPA đã được quản lý là hai lớp khác nhau**.

Ở chiều ngược lại, việc gọi `em.clear()` hoặc dùng cache hint `BYPASS` cũng **không tự biến transaction REPEATABLE READ thành READ COMMITTED**. Lần truy vấn mới vẫn bị giới hạn bởi snapshot/locking semantics của database.

Bài học này thuộc chương **Bộ nhớ đệm** của module *Data Persistence Relational Access ORM JPA*. Mục tiêu là xây một mô hình tư duy để **đánh giá đúng độ mới, tính nhất quán, mức cô lập và hiệu năng** khi JPA cache tương tác với transaction.

> **Nguyên tắc cốt lõi:** Muốn biết một kết quả đọc có “mới” và “nhất quán” không, phải hỏi đồng thời: **entity đã có trong persistence context chưa; shared/query cache có tham gia không; transaction đang ở mức isolation nào; và đã có transaction khác commit hay chưa?**

---

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt rõ persistence context/L1, L2 shared entity cache và query cache.
2. Giải thích vì sao gọi `EntityManager.find` nhiều lần có thể không tạo SQL mới.
3. Phân tích dữ liệu mà hai transactions nhìn thấy sau khi một bên cập nhật và commit.
4. Không nhầm **identity map repeatability** với bảo đảm **REPEATABLE READ của database**.
5. Hiểu các mức READ COMMITTED, REPEATABLE READ, SERIALIZABLE cùng những giới hạn theo DB.
6. Hiểu `flush` khác `commit` và vì sao flush chưa làm dữ liệu “được commit cho transaction khác”.
7. Dùng `refresh`, `clear`, `detach` và `CacheRetrieveMode`/`CacheStoreMode` đúng mục tiêu.
8. Đánh giá tác động của `@Version`, optimistic locking, pessimistic locking và bulk DML tới cache.
9. Biết vì sao native SQL hoặc ứng dụng ngoài JPA có thể làm dữ liệu cache bị stale.
10. Thiết kế cache strategy cho reference data, danh mục sản phẩm, tồn kho, đơn hàng và dữ liệu đa tenant.
11. Xây integration tests dùng hai `EntityManager` và transaction thực để kiểm tra tính mới/consistency.
12. Phân biệt lựa chọn correctness và lựa chọn performance, không thay thế transaction semantics bằng TTL.

## 2. Sơ đồ toàn cảnh: một lần đọc entity đi qua những lớp nào?

Một sơ đồ khái niệm:

```text
Application / Repository
          |
          v
       EntityManager
          |
          +-----------------------------+
          | Persistence Context / L1    |
          | Managed entity identity map |
          +-----------------------------+
          |
          | Nếu cần resolve entity state
          v
    Shared Entity Cache / L2
    (optional; provider-managed)
          |
          | Cache miss / bypass / refresh
          v
      JDBC / SQL query
          |
          v
   Database transaction layer
       +--------------------+
       | Isolation + MVCC   |
       | Locks + constraints|
       +--------------------+
          |
          v
       Committed / visible rows
```

Đây chỉ là **mô hình khái niệm**, không phải thứ tự bắt buộc của mọi SQL/query trong mọi provider. Ví dụ:

- JPQL query có thể vẫn chạy SQL để tìm danh sách IDs dù các entity instances đã có trong L1.
- L2 cache có thể chỉ lưu một phần entity/association state.
- Query cache có thể lưu identifiers/scalars tùy provider.
- Flush trước query có thể ghi SQL DML.
- Load với lock, refresh hoặc vendor-specific hints có thể đổi đường đi.
- JPA provider có thể tối ưu khác nhau theo mapping và configuration.

Tuy nhiên, mô hình này đủ để ngăn một nhầm lẫn rất phổ biến: **“Isolation level điều khiển trực tiếp mọi lần đọc field của một Java entity.”** Không. Java object đang managed có trạng thái của nó; database isolation điều khiển những database operations trong transaction.

## 3. Bốn loại “mới” thường bị trộn lẫn

Khi business nói “cần dữ liệu mới nhất”, cần làm rõ “mới” ở nghĩa nào.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Managed-object freshness** | Java entity có phản ánh DB state mà ta muốn không? | `product.getPrice()` có còn là giá cũ? |
| **Database read visibility** | Transaction được phép thấy commit nào theo isolation? | READ COMMITTED có thể thấy commit của B ở statement sau |
| **Shared-cache freshness** | L2/query cache có theo kịp các thay đổi đã commit không? | Writer ngoài JPA cập nhật giá nhưng L2 còn giá cũ |
| **Business consistency** | Các dữ liệu được đọc cùng nhau có thỏa invariant không? | Giá + tồn kho + promotion có thuộc một quyết định nhất quán? |

Không giải quyết tất cả bốn thứ bằng cùng một nút như `CacheRetrieveMode.BYPASS`, `@Transactional` hoặc `@Version`.

### 3.1. Freshness không đồng nghĩa serializability

Một lần đọc có thể mới hơn nhưng tập các phép đọc/ghi vẫn vi phạm invariant nhiều dòng nếu không có đúng transaction isolation/locking/constraints.

### 3.2. Repeatable value không nhất thiết là repeatable database read

Một managed entity có thể trả cùng giá trị hai lần vì Java object chưa được refresh, dù cơ sở dữ liệu đã thay đổi. Đó là **identity map**, không phải bằng chứng database đã bảo vệ repeatable read.

### 3.3. Cache hit không phải transaction commit

Một giá trị có trong cache không chứng minh giao dịch tạo ra nó đã commit theo đúng nguồn sự thật, trừ khi provider/cache strategy có bảo đảm transaction synchronization phù hợp.

---

## 4. Mô hình entity dùng trong bài

Ta dùng hai loại dữ liệu đối lập:

- **ProductCategory**: tên danh mục ít thay đổi, thường phù hợp để cân nhắc shared cache.
- **InventoryItem**: lượng hàng thường xuyên được nhiều transactions ghi, cần concurrency strategy chặt.

### 4.1. ProductCategory — reference data có thể cache

```java
package com.example.shop.domain;

import jakarta.persistence.*;

@Entity
@Table(name = "product_category")
@Cacheable(true)
public class ProductCategory {

    @Id
    private Long id;

    @Column(name = "category_name", nullable = false)
    private String name;

    @Version
    @Column(name = "row_version", nullable = false)
    private Long version;

    protected ProductCategory() {
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public Long getVersion() {
        return version;
    }

    public void rename(String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException(
                "Name must not be blank"
            );
        }
        this.name = newName;
    }
}
```

`@Cacheable(true)` thể hiện ý định entity được phép tham gia **shared entity cache**, khi shared-cache mode của persistence unit và provider cho phép. Annotation này **không bắt buộc mọi provider lúc nào cũng lưu sẵn mọi ProductCategory vào L2**.

### 4.2. InventoryItem — dữ liệu cạnh tranh cao

```java
package com.example.shop.domain;

import jakarta.persistence.*;

@Entity
@Table(name = "inventory_item")
@Cacheable(false)
public class InventoryItem {

    @Id
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @Column(name = "sku", nullable = false)
    private String sku;

    @Column(name = "available_quantity", nullable = false)
    private int availableQuantity;

    @Version
    @Column(name = "row_version", nullable = false)
    private Long version;

    protected InventoryItem() {
    }

    public Long getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public int getAvailableQuantity() {
        return availableQuantity;
    }

    public Long getVersion() {
        return version;
    }

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive"
            );
        }
        if (quantity > availableQuantity) {
            throw new IllegalStateException(
                "Insufficient stock"
            );
        }
        availableQuantity -= quantity;
    }
}
```

Với `@Cacheable(false)`, chủ đích là **không chia sẻ entity state này qua L2** trong mode hỗ trợ lựa chọn đó. Nhưng **L1 persistence context vẫn tồn tại**. Tắt L2 không khiến `find` mỗi lần đều đi thẳng tới DB trong cùng EntityManager.

### 4.3. Schema minh họa

```sql
CREATE TABLE product_category (
    id BIGINT PRIMARY KEY,
    category_name VARCHAR(200) NOT NULL,
    row_version BIGINT NOT NULL
);

CREATE TABLE inventory_item (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    sku VARCHAR(128) NOT NULL,
    available_quantity INTEGER NOT NULL,
    row_version BIGINT NOT NULL,
    CONSTRAINT uq_inventory_tenant_sku
      UNIQUE (tenant_id, sku),
    CONSTRAINT ck_inventory_not_negative
      CHECK (available_quantity >= 0)
);
```

Ví dụ giả định:

```text
ProductCategory#10: name="Books", version=3
InventoryItem#42: tenant="shop-a", sku="BOOK-JPA",
                  availableQuantity=10, version=7
```

`@Version` bảo vệ entity-level stale writes khi provider quản lý cập nhật; nó không tự làm mọi dữ liệu trong L1/L2 luôn mới ở mỗi lần getter.

## 5. Persistence context (L1 cache): điểm bắt đầu quan trọng nhất

Mỗi persistence context quản lý các entity instances theo persistent identity. Trong một context, JPA bảo đảm có **một managed entity instance đại diện cho cùng persistent identity**, theo contract identity map.

```java
ProductCategory first =
    em.find(ProductCategory.class, 10L);

ProductCategory second =
    em.find(ProductCategory.class, 10L);

System.out.println(first == second); // true trong cùng context
```

Trong điều kiện entity vẫn managed và không bị `clear`/`detach`, hai references thường là chính cùng Java object.

### 5.1. L1 không phải tùy chọn “bật/tắt cache” đơn giản

Persistence context là cơ chế cốt lõi của JPA:

- Quản lý managed entities.
- Giữ identity nhất quán.
- Theo dõi dirty state theo provider.
- Điều phối flush.
- Trả cùng instance khi truy cập cùng entity trong context.

Không nên xem L1 chỉ là một hiệu năng optimization có thể tắt tương đương L2.

### 5.2. @Cacheable(false) không tắt L1

```java
@Cacheable(false)
@Entity
class InventoryItem {
    // ...
}
```

Dù L2 không áp dụng, hai lần:

```java
InventoryItem a = em.find(InventoryItem.class, 42L);
InventoryItem b = em.find(InventoryItem.class, 42L);
```

vẫn có thể là `a == b` trong cùng persistence context và không thực hiện SQL `SELECT` lần hai.

### 5.3. Getter không phải database read

```java
int quantity = item.getAvailableQuantity();
```

là đọc field của Java object. Nó không tự phát SQL để hỏi xem database vừa đổi số lượng hay chưa. Với lazy field/association thì có thể xảy ra truy vấn khi truy cập lần đầu, nhưng **đừng coi mọi getter là truy vấn cập nhật trạng thái entity hiện tại**.

### 5.4. L1 là nhất quán về identity, không phải tuyên bố toàn bộ snapshot DB

Trong một context có thể có entity A đã load hôm trước trong một extended context và entity B mới load. Chúng không nhất thiết đại diện cho một snapshot DB duy nhất nếu transaction boundaries và cách đọc không được quản lý đúng.

Đây là lý do không được xem “cùng persistence context” như “toàn bộ dữ liệu có snapshot isolation”.

---

## 6. Timeline 1: READ COMMITTED nhưng EntityManager vẫn đọc state cũ

Giả sử database được cấu hình READ COMMITTED. Hai `EntityManager` độc lập:

```text
Database lúc đầu:
  Category#10 name="Books", version=3

Transaction A                       Transaction B
-----------------------------------------------------------
BEGIN
find(Category#10)
-> "Books" (managed trong L1 A)

                                    BEGIN
                                    find(Category#10)
                                    rename("Programming")
                                    COMMIT
                                    DB: version=4

find(Category#10) lần nữa
-> cùng managed instance A
-> vẫn có thể là "Books"

COMMIT
-----------------------------------------------------------
```

Nhiều người mong `find` lần hai trả “Programming” vì READ COMMITTED cho phép statement sau nhìn thấy commit mới. Nhưng **không nhất thiết có statement SQL mới**: L1 đã có managed entity.

### 6.1. Điểm nào thuộc database isolation?

Nếu Transaction A **thực sự thực hiện một SQL SELECT mới** sau khi B commit, READ COMMITTED thường cho phép thấy state mới theo semantics DB. Nhưng `em.find` từ L1 không buộc tạo SELECT.

### 6.2. Đây có phải lỗi JPA?

Không. JPA giữ một managed instance cho cùng entity identity trong context, để code có lifecycle/dirty checking nhất quán. Nếu mọi lần `find` tự thay state Java object từ DB thì thay đổi chưa flush của ứng dụng có thể bị ghi đè bất ngờ.

### 6.3. Bài học

**Đừng dùng một entity đã managed quá lâu làm bằng chứng giá trị “mới nhất” của DB**. Xác định transaction/context scope và thao tác refresh thích hợp.

## 7. Timeline 2: Đọc lại sau khi clear ở READ COMMITTED

Nếu A chưa sửa entity và muốn một lần truy vấn mới:

```java
ProductCategory oldValue =
    em.find(ProductCategory.class, 10L);

em.clear();

ProductCategory reloaded =
    em.find(ProductCategory.class, 10L);
```

Sau `em.clear()`:

- Các managed instances hiện có bị **detached**.
- L1 không còn entry managed cho identity trong context.
- Lần `find` sau cần resolve entity state từ L2 hoặc database.

**Nhưng chưa chắc reloaded đến từ database**, bởi L2 có thể chứa state. Và nếu DB isolation là REPEATABLE READ, một SQL mới có thể vẫn thấy snapshot cũ.

### 7.1. Muốn tránh L2 khi tải lại?

Có thể dùng shared-cache retrieve hint:

```java
ProductCategory freshAttempt = em.find(
    ProductCategory.class,
    10L,
    java.util.Map.of(
        "jakarta.persistence.cache.retrieveMode",
        CacheRetrieveMode.BYPASS
    )
);
```

`BYPASS` yêu cầu **bỏ qua shared cache để lấy entity state** theo hint semantics, không phải một công tắc bỏ qua L1 trong trường hợp entity đã managed, cũng không vượt qua isolation của DB.

### 7.2. Cẩn thận clear khi có thay đổi pending

Nếu A đã:

```java
category.rename("New Books"); // managed, chưa flush
em.clear();
```

thì `clear` detach entity và những thay đổi chưa đồng bộ có thể bị bỏ, không tự flush. Chỉ `clear` khi hiểu rõ pending changes; nếu muốn lưu thay đổi, hãy quyết định `flush`/commit hoặc rollback theo workflow.

### 7.3. Đừng “clear mọi nơi” để chống stale data

`clear` toàn persistence context khiến các entity đang managed bị detach, có thể làm mất dirty changes, tăng SQL và phá assumptions của service. Nó không phải lựa chọn mặc định mỗi lần muốn đọc thuộc tính mới.

## 8. Timeline 3: REPEATABLE READ vẫn có snapshot cũ dù cache bị bỏ qua

Giả sử DB có transaction-level snapshot tương ứng với một triển khai REPEATABLE READ (chi tiết khác theo DB):

```text
Database: Category#10 = "Books"

Transaction A                            Transaction B
----------------------------------------------------------------
BEGIN (REPEATABLE READ)
SELECT Category#10 -> "Books"
                                      UPDATE -> "Programming"
                                      COMMIT
A clear L1, bypass L2
A SELECT Category#10 lần nữa
-> DB có thể tiếp tục trả "Books"
   theo snapshot của A
COMMIT
----------------------------------------------------------------
```

**Tắt cache không thay đổi database snapshot.**

### 8.1. Vì sao?

Transaction isolation được database áp dụng cho truy vấn. Với kiểu REPEATABLE READ dựa trên MVCC snapshot, transaction có thể giữ một ảnh chụp logic từ thời điểm nhất định. Một query mới vẫn có thể thấy snapshot trước commit của B.

### 8.2. Các database không giống hệt nhau

- PostgreSQL có hành vi snapshot-based REPEATABLE READ riêng.
- MySQL/InnoDB có khác biệt giữa consistent reads và locking reads.
- SQL Server có nhiều lựa chọn locking/versioning isolation.
- Oracle có các semantics nhất quán đọc đặc thù.

Do đó không coi bảng khái niệm isolation là mô tả chính xác mọi truy vấn trên mọi hệ quản trị.

### 8.3. Muốn thấy commit mới sau snapshot cũ?

Thông thường cần hoàn tất transaction cũ và mở transaction mới với isolation phù hợp. **Không có JPA cache hint portable nào buộc database phá vỡ isolation snapshot của transaction đang chạy.**

## 9. So sánh READ COMMITTED, REPEATABLE READ và SERIALIZABLE

| Isolation level | Ý tưởng tổng quát | Tương tác đáng chú ý với JPA cache |
|---|---|---|
| READ UNCOMMITTED | Có thể cho phép một số dirty reads tùy DB; nhiều DB nâng/biến đổi semantics | L1 vẫn giữ managed instances |
| READ COMMITTED | Không đọc dữ liệu chưa commit; các statement sau có thể thấy commit mới | `find` từ L1 không nhất thiết gửi statement sau |
| REPEATABLE READ | Tăng tính ổn định của các reads; snapshot/locking phụ thuộc DB | Clear/bypass L2 không tự phá snapshot DB |
| SERIALIZABLE | Nhằm tạo kết quả tương đương một thứ tự thực thi tuần tự; có thể abort transaction và yêu cầu retry | Cache không thay DB serialization checks; dữ liệu cache ngoài DB có thể không thuộc snapshot |

### 9.1. Một số anomalies cần phân biệt

| Hiện tượng | Tóm tắt |
|---|---|
| Dirty read | Đọc thay đổi chưa commit của transaction khác |
| Non-repeatable read | Hai lần đọc cùng row trong một transaction cho giá trị khác do concurrent commit |
| Phantom | Truy vấn cùng predicate cho tập rows khác do concurrent insert/delete |
| Lost update | Một write dựa trên state cũ ghi đè hoặc bỏ qua update khác |
| Write skew | Các transactions sửa những rows khác nhau và làm vi phạm invariant tổng thể |
| Read skew | Đọc các rows ở những thời điểm không đồng bộ với nhau |

**L1 có thể che khuất non-repeatable read của một managed entity**, nhưng không vì thế mà nó ngăn được phantom inserts, write skew hoặc các anomalies trên nhiều rows.

### 9.2. SERIALIZABLE có cần retry không?

Có thể. Nhiều database phát hiện một số xung đột serializability bằng cách abort một transaction. Một transaction thất bại phải được rollback; nếu retry hợp lệ, chạy lại **toàn bộ unit of work** trong transaction/context mới.

### 9.3. Không lấy tên isolation làm bằng chứng

Chỉ nhìn cấu hình `Isolation.REPEATABLE_READ` chưa đủ. Cần biết:

- Transaction manager có thực sự áp setting đó cho JDBC connection không?
- Database có hỗ trợ không?
- Method có join một transaction đã mở trước đó không?
- Cache L1/L2 có tham gia?
- Query có khóa hay là snapshot read?
- Provider dùng SQL/optimizations gì?

Đánh giá đúng phải dựa trên một test của stack thực tế.

---

## 10. Persistence context lifetime: một transaction hay nhiều transaction?

Mặc định trong nhiều ứng dụng Spring/JPA, một EntityManager giao dịch được gắn với request/service transaction. Nhưng JPA còn hỗ trợ **extended persistence context**, và web frameworks có thể dùng Open-EntityManager-in-View (OSIV).

### 10.1. Transaction-scoped persistence context

```text
Request 1:
  txA + EM_A
  load category -> managed in EM_A
  commit/close context

Request 2:
  txB + EM_B
  load category -> managed in EM_B
```

Nếu mỗi request có context riêng, stale L1 giữa các requests thường ít rủi ro hơn. Tuy nhiên L2 shared cache vẫn có thể tham gia lần load tiếp theo.

### 10.2. Extended persistence context

Một context kéo dài qua nhiều transactions có thể giữ managed instances cũ:

```text
EM_extended:
  Transaction 1: load Product#42
  --> context vẫn giữ Product#42
  Transaction 2: thao tác tiếp Product#42
  --> có thể dùng managed state cũ
```

Extended contexts hợp lý cho một số conversational workflows, nhưng phải thiết kế `refresh`/conflict checking, `@Version` và detached/request boundaries rõ. Không giả định context kéo dài tự phát hiện mọi external update.

### 10.3. OSIV không phải isolation strategy

Open Session/EntityManager in View thường cho phép persistence context tồn tại qua một phần xử lý web view/serialization. Điều này có thể cho phép lazy loads muộn, nhưng cũng khiến query phát sinh ngoài nơi bạn dự kiến và dễ che lỗi fetch planning.

OSIV **không** bảo đảm các entity trong một response nhất quán theo một snapshot nghiệp vụ. Cần fetch plan/DTO + transaction boundary rõ.

### 10.4. Không dùng EntityManager chung giữa threads

`EntityManagerFactory` được thiết kế cho việc sử dụng chia sẻ phù hợp; `EntityManager` thì không phải object thread-safe cho nhiều concurrent requests. Một request không được “tiết kiệm cache” bằng cách reuse cùng EntityManager trên nhiều threads.

---

## 11. Flush, commit và rollback: đừng nhầm ba thời điểm

Ví dụ Transaction A:

```java
EntityTransaction tx = em.getTransaction();

tx.begin();

InventoryItem item =
    em.find(InventoryItem.class, 42L);

item.reserve(2);

em.flush();

tx.commit();
```

Trong đó:

1. `reserve(2)` sửa managed entity trong memory.
2. `flush()` yêu cầu đồng bộ pending changes xuống database **trong transaction**.
3. `commit()` mới xác nhận transaction được database chấp nhận.

### 11.1. Flush không công bố dữ liệu đã commit

Transaction B ở READ COMMITTED thường **không được nhìn thấy thay đổi chưa commit** của A, dù A đã `flush()`.

```text
A: BEGIN
A: qty = 8
A: FLUSH (SQL UPDATE đã được gửi)
B: SELECT qty (READ COMMITTED)
   -> có thể vẫn thấy qty=10 theo committed state
A: COMMIT
B: SELECT lần sau -> có thể thấy qty=8 nếu thực sự query DB
```

Hành vi chờ/block còn tùy SQL/DB/locking, nhưng flush **không** tương đương commit.

### 11.2. Flush có thể xảy ra tự động

Với `FlushModeType.AUTO`, provider phải bảo đảm những thay đổi pending phù hợp được tính đến khi thực thi query trong các trường hợp cần theo contract; provider có thể flush trước query để bảo đảm kết quả.

```java
em.setFlushMode(FlushModeType.AUTO);
```

Điều này có nghĩa một JPQL query “chỉ đọc” có thể gây SQL UPDATE trước nó nếu trong context có dirty managed entities.

### 11.3. FlushModeType.COMMIT

```java
em.setFlushMode(FlushModeType.COMMIT);
```

Có thể trì hoãn flush đến commit, và ảnh hưởng của pending updates đối với query result trước commit không được đảm bảo như AUTO trong mọi tình huống. Không tự cho rằng query luôn nhìn thấy local pending changes trong kết quả SQL khi dùng COMMIT.

### 11.4. Rollback không tự “phục hồi” Java object như mới

Nếu một transaction cập nhật entity rồi rollback, không nên tiếp tục dùng persistence context/managed instances cũ như thể chúng đã được đồng bộ chính xác về state ban đầu. Entity state, generated values và caches có thể cần context mới/clear/close theo lifecycle.

Một quy tắc an toàn trong application services: **rollback → kết thúc attempt → mở transaction/persistence context mới khi retry**.

### 11.5. Cache sau rollback

Một provider/cache strategy đúng phải phối hợp transactional updates theo semantics được hỗ trợ; không nên thiết kế application code tự ghi vào một shared cache thủ công trước commit rồi hy vọng JPA rollback sẽ thu hồi giá trị đó.

Nếu bạn kết hợp Redis/local application cache bên ngoài JPA, rollback JPA transaction **không tự rollback Redis write**.

---

## 12. Khi nào JPQL query đọc state mới còn EntityManager.find thì không?

Giả sử A đang giữ managed ProductCategory#10 tên “Books”. B cập nhật thành “Programming” và commit.

Sau đó A chạy một JPQL query:

```java
List<ProductCategory> categories = em.createQuery(
    """
    select c
    from ProductCategory c
    where c.id = :id
    """,
    ProductCategory.class
)
.setParameter("id", 10L)
.getResultList();
```

JPA có thể gửi SQL query tới DB để xác định rows, nhưng khi materialize ProductCategory#10, persistence context đã có managed instance của identity đó. Provider thường sử dụng managed instance này theo identity semantics; **đừng suy ra entity fields nhất định đã được refresh**.

### 12.1. Scalar projection có thể khác managed entity state

```java
String currentName = em.createQuery(
    """
    select c.name
    from ProductCategory c
    where c.id = :id
    """,
    String.class
)
.setParameter("id", 10L)
.getSingleResult();
```

Nếu query thực sự đọc database (không bị query cache/timing khác chi phối), `currentName` có thể là “Programming”, trong khi:

```java
category.getName()
```

trong L1 vẫn là “Books”.

Điều này **không phải JPA tự mâu thuẫn**; hai values đến từ hai lớp/truy vấn khác nhau và được quản lý theo semantics khác nhau.

### 12.2. Query result cache làm tình huống phức tạp hơn

Nếu một provider bật query cache, scalar query có thể được lấy từ cache phụ thuộc chiến lược invalidation. Khi đó ngay cả scalar projection cũng không có nghĩa chắc chắn tạo SQL mới.

### 12.3. Không dùng “query lại cùng entity” thay cho refresh

Nếu thực sự cần đồng bộ lại **managed object**, dùng `em.refresh(entity)` trong tình huống thích hợp hoặc một context mới, đồng thời hiểu database isolation đang áp dụng.

---

## 13. EntityManager.refresh: khi cần tải lại state của managed entity

```java
ProductCategory category =
    em.find(ProductCategory.class, 10L);

em.refresh(category);
```

`refresh` yêu cầu đồng bộ state của managed entity từ database theo semantics JPA, thay vì chỉ trả lại managed instance trong L1 như một lần `find` thông thường.

### 13.1. Những tình huống có ích

- Cần thấy thay đổi do transaction khác đã commit khi DB isolation cho phép.
- Một stored procedure/native SQL đã sửa row và managed entity có thể stale.
- Database trigger/server-generated columns đã thay đổi theo cách mapping không tự đồng bộ.
- Một workflow đọc phải xác nhận state hiện hành trước khi quyết định.
- Cần lấy lại state sau một thao tác DB bên ngoài persistence context.

### 13.2. Rủi ro: mất local changes

```java
category.rename("Books for Developers");

// Nếu chưa flush:
em.refresh(category);
```

Refresh có thể ghi đè `name` về state DB, khiến local change bị mất. Không dùng `refresh` như một thao tác “chắc chắn vô hại”.

### 13.3. Refresh vẫn bị chi phối bởi database isolation

Nếu database transaction đang ở snapshot REPEATABLE READ, một refresh không mặc nhiên có quyền quan sát commit nằm ngoài snapshot ấy. Phải xác minh trên database/isolation cụ thể.

### 13.4. Refresh entity khác với refresh cả query cache

`em.refresh(category)` không có nghĩa mọi kết quả aggregate/report/query cache liên quan tự được invalidate theo cách ứng dụng tùy ý mong muốn. L2/query-cache invalidation cần hiểu provider strategy.

### 13.5. Refresh với lock

Nếu cần khóa khi đọc lại:

```java
em.refresh(
    category,
    LockModeType.PESSIMISTIC_WRITE
);
```

Cần transaction hợp lệ và kiểm soát local pending changes. Đây không phải cách chung để đọc reference data; chỉ dùng khi workflow thực sự cần write lock.

---

## 14. clear, detach và close: khác nhau thế nào?

| Thao tác | Tác động |
|---|---|
| `em.clear()` | Detach mọi entities đang managed trong persistence context |
| `em.detach(entity)` | Detach một entity cụ thể |
| `em.close()` | Đóng EntityManager; managed entities không còn được quản lý bởi context ấy |
| `em.refresh(entity)` | Reload state cho một managed entity theo JPA semantics |
| `em.flush()` | Đồng bộ pending changes từ persistence context xuống DB transaction |
| `emf.getCache().evict(...)` | Evict entry khỏi **shared cache**, không xóa instance đã managed ở L1 |

### 14.1. clear không phải flush

```java
item.reserve(1);
em.clear();
```

có thể làm mất local change chưa flush. Nếu muốn tránh điều đó:

```java
em.flush();
em.clear();
```

nhưng **flush không commit** và không mặc định safe nếu các domain side effects/constraints chưa được xử lý. Mẫu `flush→clear` thường xuất hiện trong batch processing có transaction rõ, không phải công thức áp dụng cho mọi business service.

### 14.2. detach một entity

```java
em.detach(category);
```

Entity trở thành detached; lần `find` tiếp có thể resolve một managed instance mới. Nhưng nếu L2 còn cache state và DB snapshot chưa mới, vẫn có rủi ro đọc state không như mong muốn.

### 14.3. evict L2 không detach L1

```java
emf.getCache().evict(ProductCategory.class, 10L);
```

không khiến `category` đã managed trong EntityManager đang mở tự đổi tên. Hai caches có phạm vi khác nhau.

### 14.4. close sau rollback

Sau rollback/failure quan trọng, thường nên kết thúc persistence context/transaction attempt và mở context mới, thay vì cố làm “sạch” một context lỗi bằng nhiều lời gọi refresh tùy ý.

## 15. Shared cache (L2): tồn tại ngoài một EntityManager

L1 gắn với persistence context. **L2 shared cache** được chia sẻ giữa nhiều contexts nếu provider hỗ trợ/bật theo cấu hình.

```text
EntityManager A -> L1 A ----+
                             |
                             v
                        Shared L2
                             ^
                             |
EntityManager B -> L1 B ----+
                             |
                             v
                          Database
```

Ví dụ:

1. EM_A load ProductCategory#10 từ DB.
2. Provider có thể đưa state vào L2.
3. EM_A đóng.
4. EM_B load ProductCategory#10.
5. Nếu cache policy cho phép, provider có thể resolve state từ L2 mà không gửi SQL load entity.

### 15.1. L2 thường lưu entity state, không phải Java instance chia sẻ y hệt

Một provider thường cache dữ liệu/snapshot, không làm hai EntityManagers dùng chung một managed Java object mutable. Trong mỗi context:

```java
ProductCategory a = emA.find(ProductCategory.class, 10L);
ProductCategory b = emB.find(ProductCategory.class, 10L);
```

`a` và `b` thường là **hai Java instances riêng**, mỗi instance được quản lý bởi context riêng. Đừng đồng nhất L2 sharing với object sharing.

### 15.2. L2 không nên được xem là nguồn sự thật tuyệt đối

DB là nguồn dữ liệu persisted; L2 là optimization có consistency/invalidation policy. Nó có thể hữu ích cho reference entities ít thay đổi, nhưng không bảo đảm mọi external writer được phát hiện ngay.

### 15.3. Provider vẫn quản lý entry lifecycle

Không phải mọi `find` đều hit L2, và một lần entity load cũng không nhất thiết đồng nghĩa cache entry luôn được giữ vô hạn. L2 có thể evict do memory pressure, TTL, policy hoặc cập nhật/transaction synchronization.

---

## 16. Cấu hình shared cache theo Jakarta Persistence

JPA có `SharedCacheMode` với các lựa chọn chính:

| Mode | Ý nghĩa ý định |
|---|---|
| `ALL` | Đề nghị tất cả entities được cache theo shared cache |
| `NONE` | Không dùng shared cache cho entities |
| `ENABLE_SELECTIVE` | Chỉ các entity được chọn bằng `@Cacheable(true)` tham gia |
| `DISABLE_SELECTIVE` | Cache entities trừ các entity được loại qua `@Cacheable(false)` |
| `UNSPECIFIED` | Để provider quyết định semantics mặc định |

Một `persistence.xml` minh họa:

```xml
<persistence
    xmlns="https://jakarta.ee/xml/ns/persistence"
    version="3.0">
    <persistence-unit name="shopPU">
        <provider>org.hibernate.jpa.HibernatePersistenceProvider</provider>
        <class>com.example.shop.domain.ProductCategory</class>
        <class>com.example.shop.domain.InventoryItem</class>
        <shared-cache-mode>ENABLE_SELECTIVE</shared-cache-mode>
    </persistence-unit>
</persistence>
```

Ví dụ XML chỉ minh họa khai báo mode; dự án thật cần datasource, transaction type, provider/classpath và những cấu hình khác phù hợp. Không mặc định JPA shared-cache mode làm provider tự có một cache backend production đầy đủ.

### 16.1. @Cacheable(true) có nghĩa gì khi ENABLE_SELECTIVE?

`ProductCategory` được phép cache. `InventoryItem` không được chọn vào shared cache theo cơ chế selective này.

### 16.2. @Cacheable(false) có tác dụng với mọi mode?

Annotation được diễn giải trong ngữ cảnh shared-cache mode. Ví dụ `DISABLE_SELECTIVE` tôn trọng việc loại trừ rõ ràng; `ALL` định hướng cache mọi entity. Không chọn ngẫu nhiên một mode rồi mặc định tất cả annotation có cùng tác động độc lập mode.

### 16.3. SharedCacheMode không cấu hình query cache

Query cache là cơ chế khác, thường vendor-specific. Chỉ vì L2 bật không có nghĩa JPQL reports sẽ được cache nguyên kết quả `COUNT/SUM`.

### 16.4. Cache backend cần được cấu hình riêng

Với Hibernate, ngoài `@Cacheable`, việc dùng L2 thực tế còn phụ thuộc version, region factory, cache provider/backend, entity cache concurrency strategy và cấu hình. Những chi tiết đó **không thuộc API portable của Jakarta Persistence** và phải kiểm tra theo Hibernate version đang chạy.

---

## 17. L2 cache và transaction commit

Một provider có thể phối hợp cập nhật/invalidation L2 khi transaction commit, dựa trên cache concurrency strategy. Nhưng không được tự suy rằng “L2 luôn chứa dữ liệu mới nhất ở mọi thời điểm”.

### 17.1. Timeline khi chỉ có JPA provider quản lý ghi

```text
EM_A / Tx A                  Shared L2                  EM_B / Tx B
-------------------------------------------------------------------
load Category#10 ----------> cache load
rename("Programming")
flush / commit
                             provider synchronize/
                             update/evict entry
                                                        load Category#10
                                                        theo cache policy
-------------------------------------------------------------------
```

Ở đây, một provider với strategy thích hợp có thể cập nhật hoặc invalidate L2, bảo đảm contract nhất quán theo mức hỗ trợ.

**Điều không nên giả định:** mọi provider/strategy đều cập nhật cùng thời điểm, cùng cách, trên tất cả nodes và đối với mọi dạng query/bulk DML.

### 17.2. Transaction A chưa commit

Nếu A thay đổi entity, EM_B không được “thấy dirty data” chỉ vì A đã làm L1 dirty. Cache strategy đúng phải tránh công bố phiên bản chưa commit theo consistency policy tương ứng; với provider extensions hoặc external caches, phải xác định cụ thể cơ chế transaction synchronization.

### 17.3. Có nhiều application instances?

Nếu mỗi instance dùng một cache local riêng, các instances khác có thể chưa được invalidate khi một instance ghi DB, trừ khi cache provider có replication/invalidation cluster protocol hoặc cache strategy phù hợp.

Không suy luận rằng “cùng persistence unit” có nghĩa mọi JVM chia sẻ một cache đồng bộ.

### 17.4. Distributed cache vẫn không thay transaction isolation

Ngay cả khi có Redis/Infinispan/Hazelcast hoặc provider-specific clustered cache, sự nhất quán của cache không tự tạo serializable DB transactions hay bảo vệ cross-row invariants.

## 18. Những chiến lược concurrency của L2 là provider-specific

Một số provider, tiêu biểu Hibernate, hỗ trợ những chiến lược như:

- Read-only.
- Read-write.
- Non-strict read-write.
- Transactional (tùy backend/strategy).

Các tên này là **ví dụ hệ sinh thái provider**, không phải các enum chuẩn của Jakarta Persistence cho shared cache mode.

### 18.1. Reference data chỉ đọc

Một region read-only có thể hiệu quả cho entity về mặt domain **không được sửa** sau khi tạo. Nhưng nếu code vẫn update row qua JPA/native SQL, read-only cache configuration không còn phù hợp.

### 18.2. Read-write strategy

Có thể hỗ trợ caching cho mutable entities với cơ chế phối hợp/invalidation để giảm stale reads theo contract của provider. Chi phí thường cao hơn read-only caching.

### 18.3. Non-strict read-write

Thường chấp nhận một cửa sổ stale data nhất định. Không thích hợp khi một giá trị cũ có thể gây sai invariant tài chính/tồn kho nghiêm trọng.

### 18.4. Transactional cache

Chỉ chọn khi cache backend/provider/transaction manager hỗ trợ đúng cơ chế giao dịch và yêu cầu consistency. Không tự coi “transactional L2” là bằng chứng tất cả services/databases được serializable.

### 18.5. Chọn cache strategy theo business contract

Không nên bật chiến lược “nhanh nhất” cho Account balance hay Inventory quantity trước khi có test correctness. **Tính chấp nhận được của dữ liệu cũ là một yêu cầu nghiệp vụ, không phải chỉ là tham số hiệu năng.**

---

## 19. Query cache: khác L2 entity cache

L2 thường liên quan cached entity state theo identity. **Query cache** liên quan kết quả một query theo parameters/order/shape.

Giả sử:

```jpql
select c.id
from ProductCategory c
where c.name like :prefix
order by c.id
```

Provider-specific query cache có thể lưu danh sách IDs hoặc kết quả query theo cách riêng.

### 19.1. Một query cache hit không chắc entity cache hit

Nếu query cache giữ IDs nhưng L2 entity cache không có entity state, provider vẫn có thể phải load từng entity ID từ DB.

### 19.2. L2 hit không chắc query cache hit

Nếu chạy JPQL predicate/order, provider có thể vẫn cần SQL tìm IDs, rồi sử dụng L2 để materialize entity state.

### 19.3. Aggregate query cache nhạy cảm với stale data

Ví dụ:

```jpql
select sum(o.totalAmount)
from SalesOrder o
where o.tenantId = :tenant
  and o.status = :paid
```

Một kết quả cached “revenue=500000” có thể sai sau khi có Order mới, refund hoặc bulk/native update. Cần hiểu query cache invalidation dependency và stale policy.

### 19.4. Jakarta Persistence có query-cache chuẩn không?

Không có một API portable chung tương đương mọi tính năng vendor query-result cache. Cấu hình query cache thường là **provider extension**. Ví dụ Hibernate có query cache configuration/hints riêng; tên property/annotation cần đối chiếu đúng phiên bản.

### 19.5. Không nhầm @Cacheable với cache JPQL query

`@Cacheable` trên entity không nói rằng `select count(...)` tự được cache hay `where` không cần SQL.

## 20. Cache retrieval và store modes của JPA

Jakarta Persistence định nghĩa:

```java
import jakarta.persistence.CacheRetrieveMode;
import jakarta.persistence.CacheStoreMode;
```

Hai chiều:

- **Retrieve mode:** có cho phép lấy entity state từ shared cache không?
- **Store mode:** có nên ghi/refesh dữ liệu vào shared cache theo policy không?

| Mode | Ý định |
|---|---|
| `CacheRetrieveMode.USE` | Cho phép dùng shared cache khi phù hợp |
| `CacheRetrieveMode.BYPASS` | Yêu cầu không đọc entity state từ shared cache |
| `CacheStoreMode.USE` | Sử dụng shared cache bình thường khi lưu state |
| `CacheStoreMode.BYPASS` | Bỏ qua việc đưa data vào shared cache theo hint |
| `CacheStoreMode.REFRESH` | Yêu cầu làm mới cache state theo semantics refresh |

### 20.1. Đọc bỏ qua L2

```java
ProductCategory category = em.find(
    ProductCategory.class,
    10L,
    java.util.Map.of(
        "jakarta.persistence.cache.retrieveMode",
        CacheRetrieveMode.BYPASS
    )
);
```

Điểm cần nhớ: **nếu cùng entity đã managed ở L1, BYPASS L2 không có nghĩa tự refresh nó**. Dùng `refresh` hoặc context mới khi muốn nạp lại managed state, đồng thời xét isolation DB.

### 20.2. Không lưu vào L2

```java
ProductCategory category = em.find(
    ProductCategory.class,
    10L,
    java.util.Map.of(
        "jakarta.persistence.cache.storeMode",
        CacheStoreMode.BYPASS
    )
);
```

Mục đích là điều chỉnh store policy cho thao tác này, nhưng không tự bảo đảm mọi cache backend/query cache đã bị tắt hoàn toàn.

### 20.3. Yêu cầu refresh L2 state

```java
ProductCategory category = em.find(
    ProductCategory.class,
    10L,
    java.util.Map.of(
        "jakarta.persistence.cache.retrieveMode",
        CacheRetrieveMode.BYPASS,
        "jakarta.persistence.cache.storeMode",
        CacheStoreMode.REFRESH
    )
);
```

Ý định là bỏ qua cached entity state khi retrieve và điều chỉnh cách refresh shared cache. **Độ mới cuối cùng vẫn phụ thuộc DB transaction visibility.**

### 20.4. Hints với JPQL query

```java
List<ProductCategory> categories = em.createQuery(
    """
    select c
    from ProductCategory c
    where c.id >= :fromId
    order by c.id
    """,
    ProductCategory.class
)
.setParameter("fromId", 1L)
.setHint(
    "jakarta.persistence.cache.retrieveMode",
    CacheRetrieveMode.BYPASS
)
.setHint(
    "jakarta.persistence.cache.storeMode",
    CacheStoreMode.BYPASS
)
.getResultList();
```

Cache hints trên query điều chỉnh **shared entity cache semantics** theo JPA và provider. Không nên coi chúng là lệnh universal tắt query cache vendor-specific hay bỏ identity map L1.

### 20.5. Namespace phụ thuộc JPA version

Jakarta Persistence mới dùng `jakarta.persistence.*`. Dự án legacy `javax.persistence.*` có tên hint tương ứng `javax.persistence.cache.retrieveMode`/`storeMode`. Không trộn hai namespace khi code và dependencies thuộc hai thế hệ khác nhau.

---

## 21. API quản lý shared cache: EntityManagerFactory.getCache()

JPA cung cấp:

```java
Cache cache = emf.getCache();
```

Một số thao tác phổ biến:

```java
boolean contains =
    cache.contains(ProductCategory.class, 10L);

cache.evict(ProductCategory.class, 10L);
cache.evict(ProductCategory.class);
cache.evictAll();
```

### 21.1. contains có ý nghĩa gì?

Nó giúp kiểm tra entity có entry phù hợp trong shared cache **tại thời điểm gọi**, theo implementation. Nó **không** bảo đảm:

- Entry đã là giá trị mới nhất so với DB.
- Lần find sau chắc chắn cache hit.
- Entity cùng ID không đang managed trong L1.
- Không có transaction khác đang cập nhật.
- Query cache có cùng trạng thái.

### 21.2. Evict một entity ID

```java
emf.getCache().evict(
    ProductCategory.class,
    10L
);
```

có thể hữu ích khi có thao tác ngoài provider thay đổi một row và bạn biết chính xác identity ảnh hưởng.

Nhưng eviction **không refresh Java objects đã managed**, và không tự bảo đảm invalidation trên cache local của các application nodes khác nếu backend không chia sẻ.

### 21.3. Evict cả entity class

```java
cache.evict(ProductCategory.class);
```

có thể phù hợp sau batch thay đổi tất cả Categories, nhưng chi phí cache misses lớn hơn evict theo ID.

### 21.4. EvictAll rất mạnh tay

```java
cache.evictAll();
```

có thể tạo stampede khi hàng nghìn requests cùng phải tải lại reference entities. Không dùng toàn bộ cache eviction như mặc định để “chắc dữ liệu mới”.

### 21.5. Evict không tự có transaction rollback

Nếu bạn gọi eviction trước khi transaction update tương ứng commit rồi transaction rollback, cache entries có thể đã bị loại không cần thiết. Vì vậy cần xét transaction lifecycle/after-commit policy, chứ không đối xử với `Cache.evict` như một SQL operation tự rollback với transaction.

## 22. Truy cập dữ liệu trong transaction chỉ đọc

```java
@Transactional(readOnly = true)
public ProductCategoryView getCategory(long id) {
    ProductCategory category =
        em.find(ProductCategory.class, id);

    return new ProductCategoryView(
        category.getId(),
        category.getName()
    );
}
```

Trong Spring, `readOnly = true` là **transaction hint/optimization** tùy transaction manager/provider, không phải JPA portability guarantee rằng DB sẽ từ chối mọi UPDATE hoặc rằng tất cả cache reads “mới hơn”.

### 22.1. Read-only không đồng nghĩa fresh

Một method read-only có thể lấy managed entity từ L1 hoặc L2. Nếu cache stale theo chính sách ứng dụng, read-only không tự sửa được.

### 22.2. Read-only không đồng nghĩa snapshot nhất quán toàn request

Nếu service gọi nhiều repository methods dưới các transaction khác nhau hoặc query ngoài transaction, không tự có cùng một snapshot. Ngược lại, cùng transaction có isolation/managed-state semantics cụ thể.

### 22.3. Dùng DTO projection để giảm entity hydration

Một màn hình danh sách chỉ cần ID, name, status:

```jpql
select new com.example.shop.api.CategoryRow(
    c.id, c.name
)
from ProductCategory c
order by c.id
```

DTO projection có thể tránh phải quản lý toàn entity state, nhưng **không tự làm DB isolation mạnh hơn**. Nếu query cache vendor đang bật, cần đánh giá riêng.

### 22.4. Chọn data source replica

Nếu ứng dụng đọc từ read replica, replica có thể **chậm hơn primary** do replication lag. Bỏ L2 và đặt READ COMMITTED trên replica cũng không tạo read-your-write guarantee xuyên DB primary/replica nếu không có cơ chế routing/waiting thích hợp.

---

## 23. Cache và transaction boundary: các loại consistency cần gọi đúng tên

Trong hệ thống nghiệp vụ, ta thường muốn:

- **Read-your-writes:** sau khi chính mình ghi thành công, lần đọc tiếp thấy kết quả của mình.
- **Monotonic reads:** một client không thấy phiên bản dữ liệu “lùi lại” theo thời gian.
- **Repeatable reads:** đọc cùng đối tượng trong transaction cho state ổn định theo semantics isolation.
- **Atomic visibility:** không thấy một phần thay đổi trong transaction chưa commit.
- **Cross-entity invariant consistency:** các rows được đọc/ghi thỏa một quy tắc nghiệp vụ chung.

### 23.1. L1 có thể hỗ trợ đọc lại local changes

Trong transaction:

```java
InventoryItem item =
    em.find(InventoryItem.class, 42L);

item.reserve(1);

int current = item.getAvailableQuantity();
```

`current` phản ánh field đã sửa trong managed object, ngay cả trước flush. Đây là local object state, không chứng minh transaction khác có thể nhìn thấy giá trị đó.

### 23.2. Read-your-writes xuyên HTTP requests

Nếu request A commit vào primary, request B chạy trên replica lag hoặc cache local khác, B có thể vẫn thấy data cũ. Để bảo đảm read-your-writes sau commit, cần chiến lược routing/invalidation/version tokens phù hợp **toàn kiến trúc**, không chỉ JPA L1.

### 23.3. Monotonic reads với nhiều nodes

Client đọc price=120 trên Node A rồi chuyển sang Node B có L2 stale price=100; nếu không có đồng bộ/version-aware routing, client có thể thấy giá “lùi lại”.

### 23.4. Cross-entity consistency không tự có nhờ caching

Một view hiển thị:

```text
Order.status = SHIPPED
Payment.status = PENDING
```

có thể là combination được đọc ở các thời điểm khác nhau, từ nhiều caches/queries/DBs. Nếu business cần snapshot nhất quán, cần transaction/isolation/reporting model hoặc read model theo event version/cutoff thích hợp.

---

## 24. @Version: phát hiện stale writes nhưng không tự bảo đảm fresh reads

Một versioned entity:

```java
@Version
@Column(name = "row_version", nullable = false)
private Long version;
```

Khi JPA update managed entity, provider kiểm tra version theo optimistic locking semantics, thường bằng SQL có ý định:

```sql
UPDATE inventory_item
SET available_quantity = ?,
    row_version = ?
WHERE id = ?
  AND row_version = ?;
```

Nếu state từ L1 cũ bị transaction khác thay đổi rồi commit, một managed update có thể dẫn tới `OptimisticLockException` khi flush/commit.

### 24.1. Nhưng đọc state cũ trước khi ghi vẫn có hậu quả

```java
InventoryItem item =
    em.find(InventoryItem.class, id);

int seenQuantity = item.getAvailableQuantity();

// Một transaction khác cập nhật qty/commits.

if (seenQuantity >= requestedQuantity) {
    sendExternalConfirmation(); // Sai: external side effect trước commit.
    item.reserve(requestedQuantity);
}
```

Version có thể chặn stale DB write, nhưng **không rút lại được email/payment** đã gửi trước đó. Cần transaction workflow và outbox/idempotency phù hợp.

### 24.2. Optimistic locking không thay isolation nhiều rows

Một `@Version` trên Account#1 không tự bảo vệ invariant tổng trên Account#1 và Account#2 nếu hai transactions sửa hai rows khác nhau. Có thể cần DB constraints, locks, serializable isolation hoặc aggregate design.

### 24.3. @Version không làm L2 luôn mới

Provider có thể dùng version trong cache concurrency strategy, nhưng out-of-band writer không tăng version hoặc không invalidate cache có thể gây stale state. **Tính đúng đắn của shared-cache strategy vẫn phụ thuộc mọi writers và provider integration.**

### 24.4. Khi người dùng sửa form trong nhiều phút

Không giữ DB transaction suốt thời gian họ nhập dữ liệu. Một pattern tốt:

1. GET trả DTO + expected version.
2. User chỉnh sửa ngoài transaction.
3. PATCH/PUT gửi expectedVersion hoặc ETag/If-Match.
4. Transaction cập nhật đối chiếu version và authorization.
5. Nếu conflict, trả outcome theo API contract.

L1/L2 caching không thay thế concurrency token trong workflow dài.

## 25. Pessimistic locking và cache: khóa phải thực sự xuống database

Khi business cần serialize thao tác ghi:

```java
InventoryItem item = em.find(
    InventoryItem.class,
    id,
    LockModeType.PESSIMISTIC_WRITE
);
```

JPA phải thực hiện lock semantics phù hợp với database/provider. **Không thể chỉ lấy một value từ L2 rồi coi đó là đã nắm DB row lock**.

### 25.1. Không preload state cũ rồi mới dựa vào lock

```java
InventoryItem item = em.find(
    InventoryItem.class,
    id
);

int beforeLock = item.getAvailableQuantity();

em.lock(
    item,
    LockModeType.PESSIMISTIC_WRITE
);

if (beforeLock >= requestedQuantity) {
    // Quyết định từ giá trị cũ là rủi ro.
}
```

Nếu cần current state sau khi lấy lock, load with lock ngay từ đầu hoặc refresh dưới lock phù hợp. `em.lock` không mặc định refresh toàn bộ managed fields.

### 25.2. Lock không thay business validation

Ngay cả khi lấy khóa thành công, vẫn phải kiểm tra availableQuantity, status, tenant, quota và các điều kiện domain dưới state được bảo vệ.

### 25.3. Lock không khiến L2 query cache tự bảo vệ aggregate

Khóa một InventoryItem không tự serialize một `SUM` query về mọi orders hoặc một counter nằm ở bảng khác. Phải chọn đúng resource/invariant.

### 25.4. Transaction phải active

Pessimistic locks có transaction requirements. Nếu không có transaction phù hợp, API có thể ném `TransactionRequiredException`.

---

## 26. Bulk JPQL/Criteria DML: lý do lớn gây cache stale

Ví dụ:

```java
int updated = em.createQuery(
    """
    update InventoryItem i
    set i.availableQuantity = :newQuantity
    where i.id = :id
    """
)
.setParameter("newQuantity", 25)
.setParameter("id", 42L)
.executeUpdate();
```

Bulk JPQL UPDATE chạy trực tiếp ở database theo query, **không cập nhật từng managed object đang có trong L1**.

### 26.1. Timeline stale L1

```text
EM_A:
  find InventoryItem#42 -> quantity=10
  bulk update #42 -> quantity=25
  item.getAvailableQuantity() -> có thể vẫn là 10
```

Không có quy tắc “vì query cũng chạy từ EM_A nên managed entity sẽ tự đổi state”.

### 26.2. Bulk DML và @Version

JPQL bulk UPDATE **không tự áp entity-level optimistic version management**. Nếu cần version strategy, phải thiết kế explicit increment/check cho numeric version, hoặc dùng managed entity update.

```jpql
update InventoryItem i
set i.availableQuantity = :qty,
    i.version = i.version + 1
where i.id = :id
  and i.version = :expectedVersion
```

Điều kiện trên là một **manual conditional update**, không phải JPA tự phát hiện stale state trong một vòng lặp entities.

### 26.3. Bulk DML và L2/query cache

Provider có thể nhận biết các entity/tables liên quan và evict/invalidate một số cache entries khi bulk JPQL/Criteria DML. Nhưng phạm vi, thời điểm và hiệu quả invalidation **phụ thuộc provider**, query shape, cache backend và strategy.

Không đặt correctness của ứng dụng trên giả định “mọi bulk update chắc chắn đã invalidate tất cả caches” khi chưa kiểm chứng.

### 26.4. Persistence context sau bulk update

Một cách tổ chức:

```java
em.flush(); // Nếu còn pending managed changes cần đồng bộ.

int changed = em.createQuery(
    """
    update InventoryItem i
    set i.availableQuantity = :qty,
        i.version = i.version + 1
    where i.id = :id
    """
)
.setParameter("qty", 25)
.setParameter("id", 42L)
.executeUpdate();

em.clear(); // Detach mọi managed entities; phải có chủ đích.
```

Đây chỉ là mẫu kỹ thuật khi workflow phù hợp. `flush` không commit, `clear` có thể bỏ các pending changes không flush và bulk update trên entity khác vẫn có side effects. Với service thông thường, có thể dùng transaction/context ngắn riêng cho bulk job để tránh pha trộn state.

### 26.5. CriteriaUpdate cũng tương tự

`CriteriaUpdate` không biến bulk DML thành managed entity dirty checking. Cần cùng cách đánh giá version, cache/context và domain callbacks.

## 27. Native SQL, stored procedures và writers ngoài JPA

Một admin job:

```sql
UPDATE inventory_item
SET available_quantity = 100
WHERE id = 42;
```

Nếu executed qua JDBC bên ngoài JPA, JPA provider **không nhất thiết biết** row đã thay đổi. Những state đã có trong:

- L1 của EntityManagers đang mở.
- L2 local/shared cache.
- Query cache vendor-specific.
- Application/Redis cache.

có thể vẫn là state cũ.

### 27.1. Đối với L1

Lần `find` thứ hai có thể trả managed instance cũ. Khi cần state mới, dùng `refresh`/context mới theo transaction isolation phù hợp.

### 27.2. Đối với L2

Có thể cần:

```java
emf.getCache().evict(
    InventoryItem.class,
    42L
);
```

nhưng eviction này chỉ ảnh hưởng shared cache instance/backend được gọi theo semantics provider. Một external writer có thể chạy trên node khác mà không phát thông báo invalidation.

### 27.3. Đối với query cache

Query cache có thể cần invalidation riêng. Evict L2 entity entry không nhất thiết evict tất cả cached scalar aggregates hoặc cached query ID lists.

### 27.4. Version phải được quản lý nhất quán

Nếu native writer sửa row nhưng không tăng `row_version`, ứng dụng có thể bỏ mất lớp optimistic concurrency protection kỳ vọng. Một manual conditional update có thể dùng:

```sql
UPDATE inventory_item
SET available_quantity = ?,
    row_version = row_version + 1
WHERE id = ?
  AND row_version = ?;
```

Nhưng nguyên tắc này phải được thống nhất giữa mọi writers, không chỉ riêng JPA service.

### 27.5. Phương án tích hợp lâu dài

- Dồn ownership của dữ liệu vào một service/repository.
- Dùng outbox/change-data-capture để phát invalidation events khi có writes.
- Có cache version/TTL nếu business cho phép stale.
- Với các values không được stale, đọc DB authoritative/disable L2 cho domain tương ứng.
- Tách các workflows DB transaction và external events bằng idempotent coordination.

Không có một lệnh `evictAll` cho mỗi lần UPDATE là thiết kế bền vững với hệ thống lớn.

---

## 28. Cache consistency trong hệ thống nhiều instances

Giả sử có hai application nodes:

```text
Node A: L2_A                  Node B: L2_B
    |                            |
    +------------+---------------+
                 |
               Database
```

Node A sửa Category#10 và commit. Nếu cache là **local-only**:

- Node A có thể invalidate/update L2_A.
- Node B có thể vẫn giữ L2_B cũ.
- DB đã có state mới, nhưng Node B cache chưa biết.

### 28.1. Các phương án

| Phương án | Ưu điểm | Đổi lại |
|---|---|---|
| Không cache entity mutable | Đơn giản, nguồn dữ liệu rõ | Tăng DB reads |
| Shared/distributed cache provider | Các nodes cùng quan sát vùng cache theo backend | Phức tạp, latency/network, consistency guarantees riêng |
| Invalidation events | Hỗ trợ local caches trên nhiều nodes | Delivery/order/retry gaps |
| TTL ngắn | Giới hạn stale window phần nào | Không bảo đảm đọc ngay sau commit |
| Versioned cache key | Dễ phân biệt bản cũ/bản mới nếu token biết được | Cần nguồn version tin cậy và invalidation |
| Read from DB authoritative ở critical path | Tăng correctness cho quyết định quan trọng | Tăng DB load/latency |

### 28.2. TTL không tạo strong consistency

Nếu cache TTL 30 giây, người dùng vẫn có thể thấy data cũ trong 30 giây (hoặc lâu hơn tùy stale policies). Khi “không được bán quá stock” là invariant, TTL không thể thay atomic update/lock.

### 28.3. Invalidation event có thể đến muộn

A commit DB rồi process crash trước khi publish invalidation. Nếu không có outbox/CDC/retry, Node B có thể giữ stale cache vô hạn cho tới eviction khác. Event-driven invalidation cần thiết kế durability, ordering và idempotency.

### 28.4. Multi-region/replica lag là tầng khác

Dữ liệu lưu trên DB replica có thể chưa bắt kịp primary. Ngay cả khi caches được invalidate tức thì, query đọc replica vẫn có thể trả state cũ. Phải định nghĩa consistency SLA của hệ thống end-to-end.

## 29. Multi-tenant: cache key và authorization

Một shared cache có thể sống lâu và phục vụ nhiều tenants. Nếu entity ID hoặc natural/business key không được namespace đúng, sai cache key có thể dẫn tới **rò rỉ dữ liệu nghiêm trọng**.

### 29.1. ID thường phải định danh đúng entity trong persistence unit

Nếu Product#42 thuộc shop-a và Product#42 khác thuộc shop-b nhưng cả hai dùng cùng global entity ID trên một schema mà mapping không phản ánh tenant, thiết kế identity có thể không đủ. Tùy mô hình:

- ID globally unique.
- Composite key gồm tenant ID.
- Multi-tenancy feature/provider-specific tenant discriminator.
- Separate schema/database theo tenant.

Không được chỉ dùng `Cache.contains(Product.class, 42L)` làm một authorization check.

### 29.2. Query cache theo tenant

```jpql
select o from SalesOrder o
where o.tenantId = :tenant
```

Query cache nếu bật phải phân biệt parameters/tenant context đúng theo provider. Nếu code application cache tự tạo key chỉ bằng tên query `"orders"` mà quên tenant, dữ liệu dễ bị chia sẻ sai.

### 29.3. Authorization luôn kiểm tra ở service/request boundary

Một cache hit không chứng minh user đang được phép đọc entity. Role, tenant membership và permissions có thể thay đổi độc lập với entity state. Cần security policy tin cậy, không tin cache như nguồn xác thực quyền khi cache không có consistency contract tương ứng.

### 29.4. Sensitive data thường nên hạn chế caching

Customer PII, balance, token, secrets, invoice detail có thể cần chính sách cache chuyên biệt hoặc không cache, tùy risk/privacy/data-retention requirements. Đừng dùng L2 chỉ vì `@Cacheable(true)` có sẵn.

## 30. Query cache và transaction isolation: tình huống khó nhận biết

Giả sử Transaction A cần report số đơn đã thanh toán:

```jpql
select count(o)
from SalesOrder o
where o.tenantId = :tenant
  and o.status = :paid
```

Nếu query cache của provider lưu kết quả count:

1. A lấy count=50 từ cache.
2. Transaction B commit một PAID order mới, database count=51.
3. A chạy query lại.
4. Nếu cache chưa được invalidate/refresh theo strategy, A có thể vẫn nhận count=50.

Câu hỏi “A đang ở READ COMMITTED hay REPEATABLE READ?” **chưa đủ**. Phải biết liệu query có thực sự chạy SQL hay không.

### 30.1. Không buộc database giải quyết stale cached aggregate

Nếu không có SQL lần hai, isolation của DB không trực tiếp kiểm soát giá trị scalar trả từ query cache.

### 30.2. Query invalidation có thể theo table/query-space

Một số providers đánh dấu vùng bảng/entities liên quan và tự invalidation cho updates do chính provider biết. Nhưng native SQL bên ngoài hoặc những query transformations khác có thể không được phát hiện đúng. Kiểm tra provider-specific behavior.

### 30.3. Báo cáo tài chính cần source of truth nào?

Với báo cáo phục vụ quyết toán, cân nhắc snapshot/read model/ledger với cutoff, database transaction phù hợp và explicit report version. Không chỉ dùng query cache có TTL rồi gọi số liệu “chính xác tại thời điểm hiện tại”.

## 31. Entity association collections và cache

Một ProductCategory có thể có `@OneToMany` Products. Provider cache có thể bao gồm:

- State của ProductCategory.
- State của từng Product.
- Collection membership / foreign keys.
- Query result chứa Product IDs.

Đây là những vùng cache/logical resources khác nhau tùy provider.

### 31.1. Cache parent không tự cache toàn collection

`@Cacheable(true)` trên Category không có nghĩa `category.getProducts()` sẽ hoàn toàn khỏi DB hoặc tất cả child entities được cache.

### 31.2. Thêm một Product mới có thể làm collection cache stale

Nếu một external writer INSERT Product mới, parent Category row có thể không đổi. Nếu collection membership đang cached, provider có thể chưa biết có child mới.

### 31.3. Collection cache invalidation là provider-specific

Khi JPA cập nhật association qua managed entities, provider có thể invalidation collection region phù hợp. Native/bulk DML hoặc foreign writer có thể bypass detection. Không đồng nhất entity cache eviction với collection/query cache invalidation.

### 31.4. Fetch plan khác freshness

`JOIN FETCH` giải quyết việc tải association để tránh N+1 trong một use case, **không** tự bảo đảm snapshot mới nhất trong mọi transaction và không sửa cache invalidation policy.

### 31.5. Lazy loading sau transaction boundary

Nếu association lazy được truy cập khi context đã đóng, có thể gặp lazy-loading exception của provider. Bật L2 không bảo đảm proxy tự dùng cache để truy cập ngoài persistence context an toàn. Thiết kế DTO/fetch plan trong transaction phù hợp.

---

## 32. READ COMMITTED + L1: bài toán “đọc lại” trong cùng request

Giả sử service:

```java
@Transactional
public void process(long itemId) {
    InventoryItem item =
        em.find(InventoryItem.class, itemId);

    callAnotherServiceWithinSameTransaction();

    InventoryItem again =
        em.find(InventoryItem.class, itemId);

    // again == item; không mặc định state đã được refresh.
}
```

Nếu `callAnotherServiceWithinSameTransaction` chạy bulk/native SQL, hoặc một writer khác commit giữa hai lệnh, `again` có thể giữ state cũ.

### 32.1. Nếu transaction khác commit trong lúc xử lý?

`em.find` lần hai không chứng minh bạn thấy commit đó. Dùng re-read strategy nếu nghiệp vụ cần.

### 32.2. Nếu code tự sửa item ở giữa?

L1 giúp service tiếp tục nhìn thấy local change của mình:

```java
item.reserve(1);
int qty = again.getAvailableQuantity();
```

Điều này là mong muốn. Nếu `find` luôn làm reload DB, nó có thể làm mất local state.

### 32.3. Khi nào cần transaction mới?

Nếu business yêu cầu “thấy chính xác trạng thái mới nhất sau khi một job khác hoàn thành”, có thể cần kết thúc transaction hiện tại và mở transaction mới, đọc DB authoritative, hoặc yêu cầu lock/consistency token. Chỉ gọi `find` nhiều lần trong cùng context không đủ.

## 33. Extended persistence context và form chỉnh sửa lâu

Một màn hình có thể mở khi Category#10 tên “Books”. User chỉnh thành “Programming” trong 3 phút. Trong thời gian đó, admin khác đổi thành “Technical Books”.

Không nên giữ DB transaction và pessimistic row lock suốt thời gian người dùng nhập form. Một approach thường hợp lý:

```text
GET:
    đọc DTO + version=3

User chỉnh sửa:
    không mở transaction dài

PATCH:
    nhận expectedVersion=3
    transaction mới
    load/check version
    nếu DB version=4 -> conflict
    nếu vẫn 3 -> apply + commit
```

### 33.1. L2 có thể hỗ trợ GET nhưng update cần authoritative check

Nếu GET trả một version cũ do cache stale, PATCH phải kiểm tra với state/optimistic version khi ghi. Cần quyết định UX conflict/reload.

### 33.2. Tránh merge entity detached cũ mà không phân biệt fields

`em.merge(detached)` có thể copy nhiều persistent fields từ detached snapshot vào managed instance. Khi version stale, JPA có thể phát hiện optimistic conflict; khi không có version hoặc mapping/DTO không rõ, có nguy cơ ghi đè dữ liệu không được chỉnh.

### 33.3. DTO expectedVersion không thay authorization

Client version là precondition, không phải bằng chứng có quyền sửa Category. Server vẫn phải kiểm tra identity/tenant/role.

## 34. Native DB trigger, generated columns và refresh

Giả sử database trigger cập nhật `last_modified_at` khi row thay đổi.

JPA code:

```java
category.rename("Programming");
em.flush();
```

Managed entity có thể chưa phản ánh chính xác DB-generated value nếu mapping/provider không đồng bộ nó tự động.

### 34.1. Refresh sau flush

```java
em.flush();
em.refresh(category);
```

có thể dùng để đọc lại generated state trong transaction, nếu provider/isolation và mapping phù hợp.

### 34.2. Flush trước refresh khi cần giữ change

Nếu gọi refresh **trước flush**, local pending change có thể bị overwrite. Hãy định nghĩa rõ data flow.

### 34.3. Sau commit với context mới

Nhiều use cases có thể đơn giản hơn nếu commit rồi đọc lại ở transaction mới khi thực sự cần generated value được xác nhận. Nhưng round trips và consistency requirements phải được cân nhắc.

### 34.4. Trigger và @Version

Một trigger tự tăng version đồng thời provider JPA cũng tăng có thể tạo xung đột. Nếu DB-generated version được chọn, cần mapping/strategy provider hỗ trợ, không ghép tùy ý hai cơ chế.

---

## 35. Cache-aside ngoài JPA: thêm một lớp consistency khác

Nhiều ứng dụng còn có Redis/application-level cache:

```text
Controller
    |
    +--> Application cache / Redis
    |
    +--> JPA EntityManager
             |
             +--> L1
             +--> L2
             +--> Database
```

Ví dụ cache-aside:

```java
ProductView cached = redisCache.get(productKey);

if (cached != null) {
    return cached;
}

ProductView loaded = repository.getProductView(id);
redisCache.put(productKey, loaded);
return loaded;
```

Với mô hình này, `refresh`/`CacheRetrieveMode.BYPASS` trong JPA **không có tác dụng gì** nếu request đã return ngay từ Redis trước khi vào repository.

### 35.1. Update rồi invalidate Redis

Một hướng thông dụng là commit DB update rồi invalidate cache key. Tuy nhiên có race/crash window giữa commit và invalidation. Muốn consistency mạnh hơn, cần versioned keys/outbox/CDC hoặc architectural contract khác.

### 35.2. Cache stampede

Nếu một popular category entry hết hạn, nhiều requests cùng miss và chạy DB query. Đây là vấn đề performance, không phải transaction isolation. Có thể dùng request coalescing/single-flight/soft TTL theo thiết kế, nhưng không được cho phép stale value khi business không chấp nhận.

### 35.3. Cache coherence toàn hệ thống

Đừng báo “JPA cache đã disabled” rồi tin tất cả response sẽ đọc DB. Cần liệt kê mọi cache layer: CDN, gateway, Redis, L2, query cache, L1 và read replica.

## 36. Chọn cache cho từng loại dữ liệu

| Loại dữ liệu | Đặc điểm | Hướng đánh giá |
|---|---|---|
| Danh mục sản phẩm ít thay đổi | Read-heavy, stale ngắn có thể chấp nhận | Cân nhắc L2 + invalidation |
| Danh sách tỉnh/thành/mã quốc gia | Reference data hiếm đổi | Shared/read-only caching phù hợp nếu versioning rõ |
| Giá sản phẩm đang flash sale | Mutable, stale gây sai giá | Chọn authoritative pricing/version & TTL rất thận trọng |
| Số lượng tồn kho | Hot writes, điều kiện cạnh tranh | Thường tránh L2 cho critical decision; dùng atomic DML/locking |
| Số dư tài khoản | Consistency rất quan trọng | Đọc authoritative state, transaction/locking/constraints rõ |
| Profile user | Thay đổi vừa phải, có PII | Cache theo privacy/permission/invalidation contract |
| Dashboard aggregate | Expensive query, có thể eventual consistency | Query/report cache theo freshness SLA |
| Order status đang xử lý | State transitions cạnh tranh | Version/lock + scoped queries, cache có coherence rõ |
| Session/authorization state | Quyền có thể bị thu hồi | Chính sách cache riêng, invalidation đáng tin |
| Audit ledger | Tính chính xác/immutable | Thiết kế append-only, authoritative query/snapshot |

### 36.1. Cache chính là một quyết định nghiệp vụ

Đặt câu hỏi: “Người dùng có thể thấy giá trị cũ tối đa bao lâu mà không gây sai quyết định?” Nếu câu trả lời là “không được cũ”, không nên bật stale-friendly L2/query cache rồi hy vọng ít khi xảy ra race.

### 36.2. Bật cache theo đo lường

Trước khi bật L2 cho một entity class:

1. Đo SQL count và database load.
2. Xác định miss/hit behavior.
3. Đo write frequency.
4. Xác định invalidation strategy.
5. Test consistency theo concurrency cases.
6. Theo dõi p95/p99 latency và memory.
7. Có rollback plan nếu cache làm stale business data.

---

## 37. Transaction isolation không phải tham số của EntityManager.find

API JPA portable không có một `em.setIsolationLevel(READ_COMMITTED)` chung cho mọi transaction.

Trong Spring:

```java
@Transactional(
    isolation = Isolation.REPEATABLE_READ,
    readOnly = true
)
public ReportView loadReport(...) {
    // ...
}
```

đây là cấu hình **của Spring transaction manager**, không phải annotation tiêu chuẩn JPA độc lập.

### 37.1. Propagation có thể ảnh hưởng isolation thực tế

Nếu method tham gia một transaction đã mở từ caller (ví dụ propagation REQUIRED), một isolation setting trên method con không nhất thiết tạo transaction mới hay đổi isolation của connection đang dùng.

### 37.2. Connection pool và driver

Transaction manager cấu hình JDBC connection/isolation; database và driver quyết định semantics cuối cùng. Không suy luận từ annotation duy nhất.

### 37.3. “Read only” không đồng nghĩa database serializable

`readOnly=true` có thể gợi ý tối ưu và làm thay đổi flush behavior theo provider, nhưng không nâng isolation và không đảm bảo transaction đọc snapshot nhất quán theo business contract.

### 37.4. Phải test sau khi cấu hình

Kiểm tra stack thật: database, dialect, transaction propagation, cache backend, L2 enabled/disabled, query cache status, connection settings.

## 38. Tính nhất quán giữa hai lần đọc khác entity

Một service:

```java
Account account = em.find(Account.class, accountId);
PaymentSummary payment = em.find(
    PaymentSummary.class, paymentId
);
```

Nếu Account ở L1 từ trước và PaymentSummary vừa được load từ DB, hai objects có thể không thuộc cùng thời điểm logic.

### 38.1. Đọc một entity lặp lại không chứng minh snapshot toàn tập

L1 có thể làm Account ổn định trong memory, nhưng PaymentSummary lại mới hơn. Nếu business cần hai states nhất quán, phải thiết kế transaction/isolation/locking thích hợp và/hoặc read model snapshot.

### 38.2. SERIALIZABLE với L2 stale là chuyện cần đánh giá riêng

Nếu provider trả entity state từ L2 không gắn với snapshot/locking của current DB transaction theo expectation, query không chứng minh tất cả thông tin ở cùng serializable snapshot. Provider cache concurrency strategy phải tương thích yêu cầu consistency.

Khi use case có rủi ro cao, có thể **bypass shared/query caches, dùng DB reads/locks và test** thay vì mặc định mọi cache strategy đều phối hợp như một serializable DB query.

### 38.3. Transaction mới không xóa mọi cache tự động

Một EntityManager mới có L1 mới, nhưng vẫn có thể dùng L2/query cache của provider. Muốn kết quả đọc authoritative, cần cả transaction mới **và** chính sách shared-cache phù hợp.

---

## 39. Một ví dụ service đọc cần “freshness” có kiểm soát

Giả sử màn hình admin cần xem trạng thái tồn kho mới nhất có thể trong database READ COMMITTED.

```java
@Service
public class InventoryReadService {

    @PersistenceContext
    private EntityManager em;

    @Transactional(readOnly = true)
    public InventorySnapshot readCurrent(
            long itemId,
            String authorizedTenantId
    ) {
        List<InventoryItem> rows = em.createQuery(
            """
            select i
            from InventoryItem i
            where i.id = :id
              and i.tenantId = :tenant
            """,
            InventoryItem.class
        )
        .setParameter("id", itemId)
        .setParameter("tenant", authorizedTenantId)
        .setHint(
            "jakarta.persistence.cache.retrieveMode",
            CacheRetrieveMode.BYPASS
        )
        .getResultList();

        if (rows.isEmpty()) {
            throw new ItemNotFoundException(itemId);
        }

        InventoryItem item = rows.get(0);

        return new InventorySnapshot(
            item.getId(),
            item.getAvailableQuantity(),
            item.getVersion()
        );
    }
}
```

DTO:

```java
public record InventorySnapshot(
    Long itemId,
    int availableQuantity,
    Long version
) { }
```

### 39.1. Giới hạn quan trọng của ví dụ

Nếu EntityManager đã có InventoryItem#42 managed trong cùng persistence context, một JPQL query dù BYPASS L2 vẫn có thể trả entity managed đó. Để có freshness semantics rõ, **thiết kế transaction/persistence context ngắn không preload entity**, hoặc chủ động refresh khi phù hợp.

### 39.2. “Freshness” không phải transaction serializability

Ngay sau khi service đọc xong, writer khác có thể update stock. DTO được trả chỉ là snapshot tại một thời điểm, không phải lời hứa số lượng vẫn như vậy khi user click mua 2 giây sau.

### 39.3. Critical write phải kiểm tra lại

Checkout phải dùng atomic conditional update/pessimistic lock/optimistic version để revalidate current stock, không tin InventorySnapshot từ GET như source of truth.

---

## 40. Một ví dụ service ghi có optimistic versioning

```java
@Transactional
public void reserve(
        long itemId,
        String authorizedTenantId,
        int quantity
) {
    InventoryItem item = em.createQuery(
        """
        select i
        from InventoryItem i
        where i.id = :id
          and i.tenantId = :tenant
        """,
        InventoryItem.class
    )
    .setParameter("id", itemId)
    .setParameter("tenant", authorizedTenantId)
    .getSingleResult();

    item.reserve(quantity);

    // Không setVersion: @Version được JPA quản lý
    // trong entity-level dirty checking/flush.
}
```

Khi hai transactions load cùng version:

```text
A: qty=10 v7 -> reserve(6)
B: qty=10 v7 -> reserve(6)
A: commit qty=4 v8
B: update theo v7 -> optimistic conflict
```

Nếu B nhận `OptimisticLockException`, rollback, rồi retry nếu nghiệp vụ cho phép:

1. Transaction mới.
2. Load qty=4 v8.
3. Validate reserve(6) → không đủ hàng.
4. Trả business rejection, không replay qty=4 từ snapshot cũ như thành công.

### 40.1. Version không loại bỏ mọi cache stale

Nếu initial load lấy data cache cũ theo strategy không còn nhất quán, provider vẫn cần bảo đảm versioned write check khi update. Nhưng với logic đọc/side effects trước commit, state cũ vẫn có thể gây quyết định không đáng tin cậy. Critical workflow phải dựa vào concurrency policy rõ.

### 40.2. Khi conflict cao

Có thể dùng `PESSIMISTIC_WRITE` hoặc atomic conditional UPDATE thay cho retry optimistic, tùy workload. Không dùng TTL cache để giải quyết overselling.

## 41. Một ví dụ atomic update tránh stale entity decision

Nếu chỉ cần trừ tồn kho:

```java
@Transactional
public boolean reserveAtomically(
        long itemId,
        String tenant,
        int quantity
) {
    if (quantity <= 0) {
        throw new IllegalArgumentException(
            "Quantity must be positive"
        );
    }

    int count = em.createQuery(
        """
        update InventoryItem i
        set i.availableQuantity =
                i.availableQuantity - :q,
            i.version = i.version + 1
        where i.id = :id
          and i.tenantId = :tenant
          and i.availableQuantity >= :q
        """
    )
    .setParameter("q", quantity)
    .setParameter("id", itemId)
    .setParameter("tenant", tenant)
    .executeUpdate();

    return count == 1;
}
```

Ở đây, JPQL bulk update là **manual numeric version increment**, không tự sử dụng managed entity lifecycle.

### 41.1. Không cần load/cache entity trước khi quyết định

Predicate `availableQuantity >= q` được DB đánh giá atomically cùng update. Điều này giảm phụ thuộc vào cached Java field.

### 41.2. Nếu count=0?

Có thể là item không tồn tại, sai tenant hoặc không đủ hàng. Chọn response theo security/business policy và có thể query thêm khi cần.

### 41.3. Cẩn thận stale L1

Nếu cùng EntityManager trước đó đã load InventoryItem#42, object đó không tự cập nhật. Tách bulk operation vào transaction/context phù hợp hoặc refresh/clear có chủ đích.

### 41.4. Không quên thêm các business conditions

Nếu Item.status phải ACTIVE, query cần predicate trạng thái tương ứng. Atomic UPDATE chỉ đúng nếu **đủ invariant nằm trong WHERE/SET/constraints**.

---

## 42. Quy trình đánh giá cache–transaction–isolation cho một use case

Một cách tiếp cận có cấu trúc:

**Bước 1. Xác định nguồn sự thật.**

Dữ liệu được ghi tại đâu? Primary DB, read replica, service khác hay Redis?

**Bước 2. Xác định yêu cầu nhất quán.**

- Có được stale vài giây không?
- Có cần read-your-writes không?
- Có cần transactionally consistent cross-entity snapshot không?
- Có invariant tài chính/tồn kho không được vi phạm không?

**Bước 3. Liệt kê mọi cache.**

- L1 persistence context.
- L2 entity cache.
- Query cache.
- Application Redis/cache.
- CDN/gateway.
- Read replica (dù không phải cache JPA, vẫn có lag).

**Bước 4. Xác định transaction scope và isolation thực tế.**

- Có transaction đang mở?
- Persistence context sống bao lâu?
- Có OSIV/extended context?
- Transaction manager propagation gì?
- Database isolation nào thực sự áp dụng?

**Bước 5. Xác định writers.**

- JPA managed updates.
- Bulk JPQL/CriteriaUpdate.
- Native SQL.
- Triggers/stored procedures.
- Admin scripts.
- Other services/nodes.

**Bước 6. Thiết kế read path.**

- Có thể nhận L2/query cache không?
- Cần BYPASS/REFRESH không?
- Có dùng projection không?
- Có thể đọc replica không?
- Có cần consistent snapshot không?

**Bước 7. Thiết kế write path.**

- `@Version` hay pessimistic lock?
- Atomic conditional DML?
- Database constraints?
- Outbox/invalidation?
- Retry/idempotency?

**Bước 8. Kiểm chứng bằng concurrent integration tests.**

Dùng hai EntityManagers/transactions; đo SQL, cache hits/misses, state cuối và business outcomes. Test trên database/provider mục tiêu.

## 43. Sơ đồ quyết định cho một yêu cầu đọc

```text
           Cần đọc entity?
                 |
                 v
        Đã có managed instance
        trong persistence context?
           /              \
          Có              Không
          |                 |
          v                 v
    Có cần state mới?     L2/query cache
       /       \           cho phép?
     Không      Có         /       \
      |          |       Có        Không
      v          v        |          |
   Dùng L1   refresh /    v          v
              context   Cache path   SQL DB
              mới         |          |
               |          +----+-----+
               |               |
               v               v
        Isolation DB có cho thấy
          commit mới không?
            /            \
          Có              Không
           |                |
           v                v
       Dùng kết quả     Kết thúc TX cũ /
       được đọc lại     mở TX mới hoặc
                        đổi consistency design
```

Sơ đồ này chỉ là hướng tư duy. Không phải mọi read/query đều đi qua L2 theo thứ tự y hệt; query cache và entity cache có thể có những paths khác nhau.

## 44. Các lỗi thường gặp

### 44.1. Nghĩ READ COMMITTED buộc find lần hai tạo SQL

L1 có thể trả managed instance cũ. Phải hiểu persistence context identity map.

### 44.2. Nghĩ REPEATABLE READ được thực hiện bởi L1

Database isolation và managed object repeatability là hai cơ chế khác nhau. L1 không ngăn phantoms hoặc write skew.

### 44.3. Nghĩ clear L1 là đọc DB mới

L2 có thể vẫn trả cached state; DB transaction cũng có thể giữ snapshot cũ.

### 44.4. Nghĩ BYPASS L2 bỏ qua mọi cache

Nó không tự loại managed entity đã tồn tại trong L1 hoặc cache ngoài JPA như Redis/CDN.

### 44.5. Nghĩ @Cacheable(false) tắt persistence context

L1 vẫn quản lý entity identity và dirty checking.

### 44.6. Nghĩ @Cacheable(true) luôn cache mọi JPQL query

Entity cache và query-result cache là hai thứ khác.

### 44.7. Nghĩ em.refresh luôn thấy commit mới ở mọi isolation

Database snapshot/locks có thể giới hạn visibility; refresh cũng có thể mất local changes.

### 44.8. Nghĩ flush đồng nghĩa commit

Flush gửi DML trong transaction, chưa công bố committed state.

### 44.9. Nghĩ rollback tự sửa Java object về DB state

Sau failure, cần transaction/persistence context mới theo workflow; không tiếp tục stale state tùy ý.

### 44.10. Evict L2 rồi đọc managed entity cũ

Evict không detach/refresh object đang trong L1.

### 44.11. Bật L2 cho hot inventory mà không có consistency policy

Một cached quantity cũ có thể làm sai quyết định ở đường đọc; critical write phải kiểm tra authoritative state.

### 44.12. Cho rằng @Version làm read luôn fresh

Version giúp phát hiện stale writes, không tự refresh mọi read.

### 44.13. Bulk JPQL UPDATE xong dùng lại managed entity

Bulk DML bỏ qua per-entity state sync; L1 có thể stale.

### 44.14. Native SQL writer không tăng version

Có thể phá optimistic concurrency contract, ngoài chuyện cache invalidation.

### 44.15. Native SQL bên ngoài provider được kỳ vọng invalidate L2

Không có bảo đảm tự động như vậy.

### 44.16. Nghĩ L2 local trên mọi nodes tự đồng bộ

Cần backend/cluster invalidation mechanism.

### 44.17. Chỉ đặt TTL để bảo vệ tiền/tồn kho

TTL không thay transactional constraints/atomic operations.

### 44.18. Dùng @Transactional(readOnly=true) như cơ chế cấm UPDATE

Đó thường là hint/optimization, không phải validation/security/constraint universal.

### 44.19. Query count từ cache dùng như dữ liệu “tuyệt đối hiện tại”

Báo cáo aggregate có freshness requirements riêng; query cache có thể stale.

### 44.20. Lock một entity và nghĩ mọi associations đã fresh/locked

Fetch plan, cache state và lock scope khác nhau.

### 44.21. Em.lock sau khi đã dùng state cũ

Một lock không tự làm biến local cập nhật; cần revalidate fresh state.

### 44.22. Không phân biệt read replica lag với JPA cache stale

Cùng biểu hiện giá cũ nhưng cách khắc phục khác nhau.

### 44.23. Xóa toàn bộ shared cache khi một row đổi

Có thể gây stampede và tăng DB load; ưu tiên targeted invalidation nếu correctness cho phép.

### 44.24. Dùng EntityManager chung giữa nhiều threads để tận dụng cache

Không thread-safe; sai transaction ownership.

### 44.25. Dùng mỗi một EntityManager trong concurrency test

Không mô phỏng hai independent persistence contexts/snapshots.

### 44.26. Chỉ đếm SQL query mà không đo cache hit, DB locks và freshness

Ít SQL không đồng nghĩa dữ liệu đúng hoặc latency thấp.

### 44.27. Cho rằng session cache không thể chứa PII

Entity cached state có thể chứa dữ liệu cá nhân; cần security/privacy policy.

### 44.28. Cache key không gắn tenant

Có thể gây rò rỉ dữ liệu giữa tenants nếu cache/application key thiết kế sai.

### 44.29. Idempotency key không được lưu bền

Hai retry HTTP có thể tạo duplicate effects dù DB cache và locks hoạt động đúng.

### 44.30. Serializability được suy ra từ cached read mà không DB transaction

Một cache hit không tự tham gia đầy đủ serialization checks của database transaction.

---

## 45. Chiến lược kiểm thử: không chỉ kiểm tra số truy vấn

Các test có mục tiêu khác nhau:

| Test | Cần kiểm tra |
|---|---|
| L1 identity | Hai `find` cùng context có cùng managed instance |
| L1 stale sau external commit | B commit, A find lần hai vẫn có thể giữ state cũ |
| Refresh | State được đọc lại theo DB isolation; local pending changes bị xử lý đúng |
| Clear | Entity bị detach và lần load sau resolve theo L2/DB |
| L2 enabled | Một context mới có thể hit shared cache theo provider |
| L2 bypass | Query/find theo hint không đọc shared cache theo semantics hỗ trợ |
| Bulk DML | Managed entity cũ không tự được sync |
| Native writer | Cache invalidation/versioning behavior được kiểm chứng |
| Versioned update | Stale write bị phát hiện |
| Transaction rollback | Không có committed DB partial update |
| READ COMMITTED | Statement SQL mới có thể thấy commit theo semantics DB |
| REPEATABLE READ | DB snapshot behavior đúng target DB |
| SERIALIZABLE | Serialization failure/retry được xử lý |
| Multi-node cache | Invalidation/TTL theo SLA |
| Multi-tenant | Không cross-tenant cache leak |
| Query cache | Cached aggregate có invalidation/freshness contract |
| Read replica | Read-your-writes routing/lag policy |

### 45.1. L1 identity test

```java
EntityManager em = emf.createEntityManager();
try {
    ProductCategory a =
        em.find(ProductCategory.class, 10L);

    ProductCategory b =
        em.find(ProductCategory.class, 10L);

    assertSame(a, b);
} finally {
    em.close();
}
```

Đây là test về **persistence context identity**, không phải test database isolation.

### 45.2. Test hai transaction READ COMMITTED

Một kịch bản:

```text
T1 / EM_A:
  begin
  load Category#10 name="Books"

T2 / EM_B:
  begin
  load Category#10
  rename("Programming")
  commit

T1:
  find Category#10 lần nữa
  -> có thể vẫn managed old state

T1:
  refresh entity hoặc clear/bypass L2, query lại
  -> theo visibility DB/isolation/provider

T1:
  commit
```

Để test có kết luận đáng tin, cần biết chính xác L2 có bật không và DB isolation nào đang dùng.

### 45.3. Test bulk update

```java
InventoryItem item =
    em.find(InventoryItem.class, 42L);

int before = item.getAvailableQuantity();

em.createQuery(
    """
    update InventoryItem i
    set i.availableQuantity = 25
    where i.id = 42
    """
).executeUpdate();

int inMemory = item.getAvailableQuantity();
```

Nếu `item` đã managed và không refresh, `inMemory` thường vẫn là `before`. Test không nên dựa vào provider-specific L2 effects để che sự khác biệt L1.

### 45.4. Test read across two EntityManagers

```java
EntityManager a = emf.createEntityManager();
EntityManager b = emf.createEntityManager();

try {
    ProductCategory categoryA =
        a.find(ProductCategory.class, 10L);

    EntityTransaction txB = b.getTransaction();
    txB.begin();

    ProductCategory categoryB =
        b.find(ProductCategory.class, 10L);

    categoryB.rename("Programming");
    txB.commit();

    // A còn managed instance của identity đó.
    String oldOrCurrent =
        categoryA.getName();

    // Không khẳng định getter đã tự query DB.
} finally {
    a.close();
    b.close();
}
```

Kịch bản resource-local transaction minh họa. Để kiểm tra isolation, đặt A trong transaction tương ứng, bảo đảm timing bằng latches/barriers và kiểm tra SQL/caches.

### 45.5. Concurrency tests cần hai contexts khác nhau

Không chia sẻ một `EntityManager` giữa threads. Dùng hai EMs, hai transactions và synchronization có timeouts. Tránh `Thread.sleep` như bằng chứng tuyệt đối rằng một thread đã commit trước thread kia.

### 45.6. Test trên DB/provider mục tiêu

H2/in-memory DB có thể khác PostgreSQL/MySQL/SQL Server/Oracle về isolation, MVCC, write conflicts và locking. Với correctness quan trọng, test database/version dùng ở production, có thể qua Testcontainers.

### 45.7. Tests này không phải Content QA

Các đoạn code trên là kiến thức trong bài. Việc soạn Markdown ở STEP 4 không đồng nghĩa đã chạy unit tests, Gradle hoặc QA nội dung tài liệu.

## 46. Một kịch bản tích hợp cache + transaction + isolation có hướng giải

Giả sử ứng dụng:

- Spring + Hibernate JPA.
- PostgreSQL READ COMMITTED.
- L2 bật cho `ProductCategory`, không bật cho `InventoryItem`.
- Query cache chỉ bật cho một số báo cáo.
- Một job JDBC ngoài ứng dụng sửa `ProductCategory.name` mỗi đêm.

Vấn đề:

```text
Ngày trước: category name = "Books"
Job đêm: UPDATE name = "Programming"
Sáng sau: một số nodes vẫn trả "Books"
```

### 46.1. Xác định nguồn stale

Không nên đoán ngay DB transaction isolation.

Hỏi theo thứ tự:

1. Job đã **commit** chưa?
2. Truy vấn trực tiếp primary DB trả tên gì?
3. Request trả từ Redis/CDN hay vào JPA?
4. Entity có ở L1 của long-lived persistence context không?
5. L2 local trên node còn giữ state cũ không?
6. Query cache có lưu result cũ không?
7. Node đang đọc primary hay replica lag?
8. Job có phát invalidation/CDC event không?

### 46.2. Biện pháp ngắn hạn

Có thể evict đúng ProductCategory entity entries sau job và dùng context mới/bypass cache cho các reads cần xác minh. Nhưng **chỉ làm khi đã biết phạm vi ảnh hưởng**, có thể phải evict trên mọi nodes hoặc cache backend dùng chung.

### 46.3. Biện pháp dài hạn

- Đồng bộ invalidation với external writer (outbox/CDC/event).
- Xem lại cache backend và consistency mode.
- Đặt freshness SLA cho reference data.
- Nếu dữ liệu không chấp nhận stale, tắt caching phù hợp.
- Cập nhật runbook điều tra đa lớp, không chỉ “restart service để sạch cache”.

### 46.4. Vì sao tăng isolation không giải quyết?

L2 local có thể trả giá trị cũ **mà không query DB**. Đổi database từ READ COMMITTED sang REPEATABLE READ không tự invalidate L2; thậm chí snapshot mạnh hơn có thể khiến SQL trong transaction không nhìn commit mới theo mong đợi.

---

## 47. Những câu hỏi phải hỏi khi điều tra “dữ liệu cũ”

1. Dữ liệu hiện tại trong primary DB là gì?
2. Ai đã sửa dữ liệu, bằng JPA, bulk SQL, trigger hay external service?
3. Transaction writer đã commit lúc nào?
4. Request reader có transaction không? Bắt đầu lúc nào?
5. Reader đang ở isolation nào và có query DB thật không?
6. Entity identity đã managed trong L1 chưa?
7. Có L2 entity cache? Entity class được cache theo shared-cache mode nào?
8. Có provider query cache hoặc Redis/cache ngoài JPA?
9. Lần load có dùng `CacheRetrieveMode.BYPASS`/`refresh` không?
10. Còn read replica hoặc CDN cache không?
11. Cache có đồng bộ giữa nhiều nodes không?
12. Có cache invalidation event bị mất/chậm không?
13. Version column có được tất cả writers tăng đúng không?
14. Business cần latest value hay cần snapshot nhất quán ở mốc cố định?
15. Có trường hợp chỉ là data race trước commit/rollback không?

Trả lời đủ các câu này thường hiệu quả hơn việc lập tức thêm `em.clear()` vào mọi repository method.

## 48. Các bài tập thực hành

### Bài 1 — Hai lần find

```java
ProductCategory a = em.find(ProductCategory.class, 10L);
ProductCategory b = em.find(ProductCategory.class, 10L);
```

**Câu hỏi:** Có phải hai lần SQL SELECT?

**Gợi ý:** Không bắt buộc; cùng context thường trả cùng managed instance từ L1.

### Bài 2 — @Cacheable(false)

InventoryItem có `@Cacheable(false)`. Gọi `em.find` hai lần trong cùng context.

**Đáp án:** L1 vẫn hoạt động; `@Cacheable(false)` không tắt persistence context.

### Bài 3 — READ COMMITTED và managed state

A load Category#10 “Books”, B commit đổi thành “Programming”, A gọi `find` lại.

**Gợi ý:** A có thể vẫn thấy “Books” vì L1; không đủ để kết luận DB isolation là REPEATABLE READ.

### Bài 4 — clear

A `em.clear()` rồi load Category#10.

**Câu hỏi:** Có chắc đọc primary DB không?

**Gợi ý:** Không; L2 có thể tham gia, DB replica/isolation cũng cần xét.

### Bài 5 — clear khi dirty

```java
category.rename("Programming");
em.clear();
```

**Câu hỏi:** Có rủi ro gì?

**Gợi ý:** Pending changes chưa flush có thể bị bỏ.

### Bài 6 — refresh

Muốn cập nhật state managed entity từ DB.

```java
em.refresh(category);
```

**Gợi ý:** Hiểu rằng refresh có thể ghi đè local unflushed changes.

### Bài 7 — REPEATABLE READ snapshot

A đã có transaction snapshot cũ, B commit update. A clear/bypass cache rồi query lại.

**Gợi ý:** SQL vẫn có thể thấy snapshot cũ theo DB semantics; cache hints không vượt isolation.

### Bài 8 — Flush và commit

A gọi `flush` sau UPDATE nhưng chưa commit. B READ COMMITTED query row.

**Gợi ý:** B không được coi uncommitted A data là committed; flush không phải commit.

### Bài 9 — Rollback

A flush UPDATE, sau đó rollback.

**Câu hỏi:** Có nên tiếp tục dùng managed state cũ để ghi ở transaction mới?

**Gợi ý:** Không nên; dùng context/transaction mới sau failure.

### Bài 10 — L2 entity cache

EM_A load Category#10, đóng; EM_B load lại. Provider có thể tránh SQL không?

**Đáp án:** Có thể nếu L2 được bật, entry có sẵn và policy cho phép.

### Bài 11 — Java identity giữa EntityManagers

`categoryA == categoryB` với a và b từ hai EMs độc lập?

**Gợi ý:** Không được mong cùng managed Java instance chỉ vì L2 shared cache.

### Bài 12 — Query cache

`@Cacheable(true)` có tự cache `select count(c)` không?

**Đáp án:** Không; query cache là một lớp khác và thường provider-specific.

### Bài 13 — SharedCacheMode

Muốn chỉ cache những entities đánh dấu `@Cacheable(true)`.

**Đáp án:** Xem `SharedCacheMode.ENABLE_SELECTIVE` và cấu hình provider tương ứng.

### Bài 14 — DISABLE_SELECTIVE

Muốn phần lớn entities cache, nhưng loại InventoryItem.

**Gợi ý:** `DISABLE_SELECTIVE` + `@Cacheable(false)` theo mode semantics và provider configuration.

### Bài 15 — BYPASS

```java
em.find(
    ProductCategory.class,
    id,
    Map.of(
      "jakarta.persistence.cache.retrieveMode",
      CacheRetrieveMode.BYPASS
    )
);
```

**Câu hỏi:** Nó bỏ qua cái gì?

**Gợi ý:** Shared cache retrieve; không tự bỏ L1 hay database isolation.

### Bài 16 — CacheStoreMode.REFRESH

**Câu hỏi:** Điều gì vẫn không được bảo đảm khi muốn đọc một commit mới?

**Gợi ý:** Nếu DB transaction isolation chưa cho commit ấy hiện ra, refresh cache mode không phá snapshot.

### Bài 17 — Evict

```java
emf.getCache().evict(ProductCategory.class, 10L);
```

**Câu hỏi:** Entity đã managed trong EM_A có tự đổi name không?

**Đáp án:** Không.

### Bài 18 — evictAll

Một Category thay đổi, service evictAll mọi cache entries.

**Gợi ý:** Có thể gây cache stampede; targeted invalidation thường đáng cân nhắc hơn.

### Bài 19 — JPQL scalar vs managed entity

A có Category entity managed tên cũ, chạy `select c.name` sau B commit.

**Gợi ý:** Scalar query có thể đọc DB value mới trong READ COMMITTED, trong khi managed object vẫn cũ. Cần xét query cache/provider.

### Bài 20 — Bulk update

Một InventoryItem đã managed. Chạy JPQL bulk UPDATE đổi quantity.

**Gợi ý:** L1 không tự sync per-entity state. Dùng context strategy/refresh phù hợp.

### Bài 21 — @Version

T1 có Item version 7, T2 commit version 8, T1 sửa và flush.

**Gợi ý:** Optimistic locking có thể phát hiện stale write; nhưng `@Version` không tự làm T1 getter thấy version 8 trước đó.

### Bài 22 — Native writer

JDBC job đổi row nhưng không tăng version.

**Gợi ý:** Có thể phá optimistic concurrency contract và làm cache stale.

### Bài 23 — Redis trước JPA

Controller trả response từ Redis trước khi gọi repository.

**Câu hỏi:** `CacheRetrieveMode.BYPASS` trong JPA có giúp không?

**Đáp án:** Không với request đã return ở Redis layer.

### Bài 24 — Multi-node L2

Node A invalidate cache local, Node B vẫn giữ entry.

**Gợi ý:** Cần shared cache/invalidation propagation hoặc stale SLA được chấp nhận.

### Bài 25 — Read replica

A commit primary, B đọc replica ngay và thấy state cũ.

**Gợi ý:** Replica lag không nhất thiết là JPA cache stale; cần routing/lag policy nếu muốn read-your-writes.

### Bài 26 — Query cache aggregate

Một revenue report dùng cached SUM; external SQL INSERT giao dịch mới.

**Gợi ý:** Query result có thể stale nếu invalidation không biết thay đổi.

### Bài 27 — @Transactional(readOnly=true)

**Câu hỏi:** Nó có bảo đảm không có stale reads?

**Đáp án:** Không.

### Bài 28 — SERIALIZABLE

**Câu hỏi:** Serializable transaction có luôn commit không?

**Gợi ý:** Không. Database có thể phát hiện serialization anomaly và yêu cầu rollback/retry.

### Bài 29 — Pessimistic lock

Service đã load InventoryItem cũ trước khi gọi `em.lock(item, PESSIMISTIC_WRITE)`.

**Gợi ý:** Lock không tự refresh managed fields; cân nhắc load-with-lock/refresh.

### Bài 30 — Cache và quota

Hai Orders khác nhau cùng tiêu thụ một quota cuối, quota được cache ở L2.

**Gợi ý:** Cache không bảo vệ invariant; cần atomic counter update/lock/DB constraint/isolation đúng resource.

### Bài 31 — Multi-tenant cache

Application cache key chỉ là `productId`, nhưng IDs có thể trùng giữa tenants.

**Gợi ý:** Thiết kế identity/tenant namespace; không cross-tenant data leakage.

### Bài 32 — PII

User profile có PII và shared L2 enabled.

**Gợi ý:** Kiểm tra security, privacy, invalidation và retention; cache hit không thay authorization.

### Bài 33 — OSIV

OSIV bật nên serializer có thể đọc lazy relation muộn.

**Câu hỏi:** Điều đó đảm bảo dữ liệu nhất quán cùng snapshot không?

**Đáp án:** Không.

### Bài 34 — FlushModeType.COMMIT

Có pending managed changes và query trước commit.

**Gợi ý:** Không giả định query luôn phản ánh pending state như AUTO; semantics phải theo spec/provider.

### Bài 35 — L2 + collection cache

External SQL thêm Product vào Category. Parent Category vẫn có cache entry đúng.

**Gợi ý:** Membership của Products collection/query cache có thể stale dù parent fields không đổi.

### Bài 36 — Dữ liệu giá

Giá hiển thị stale 5 giây có thể chấp nhận, nhưng checkout phải dùng giá authoritative.

**Gợi ý:** Tách read/display freshness SLA khỏi write/commit validation.

### Bài 37 — Concurrency test

Thiết kế test hai EMs, A đọc, B update/commit, A đọc lại, rồi refresh.

**Gợi ý:** Tách assertions về L1, DB isolation, L2 state. Test với cache on/off để xác định nguồn data.

### Bài 38 — Cache hit metrics

L2 hit rate tăng, SQL count giảm nhưng người dùng thấy giá cũ.

**Gợi ý:** Performance tốt không đủ; đo stale-read rate/consistency SLA.

### Bài 39 — Retry trên dữ liệu cũ

Một optimistic conflict xảy ra sau khi service tính qty mới dựa trên state cũ.

**Gợi ý:** Retry trong transaction mới và chạy lại business validation, không replay stale value.

### Bài 40 — Tắt L2

Tắt hoàn toàn shared-cache entity, nhưng method vẫn thấy old value sau B commit.

**Gợi ý:** Kiểm tra L1/persistence context, transaction snapshot và read replica; không quy mọi stale read cho L2.

---

## 49. Checklist triển khai và vận hành

Khi thiết kế một JPA service có cache, kiểm tra:

- [ ] Entity thuộc lớp reference/read-mostly hay mutable/hot-write?
- [ ] Business có chấp nhận stale không? Tối đa bao lâu?
- [ ] Cần read-your-writes, monotonic reads hay consistent snapshot?
- [ ] Persistence context sống trong một transaction, request hay extended workflow?
- [ ] Có OSIV kéo dài thời gian managed entities tồn tại?
- [ ] L1 identity map có thể trả stale managed instance không?
- [ ] SharedCacheMode và `@Cacheable` có phù hợp không?
- [ ] L2 provider/backend/concurrency strategy được khai báo rõ?
- [ ] Query cache có bật không; invalidate thế nào?
- [ ] Có Redis/CDN/application cache nằm trước JPA?
- [ ] Có đọc từ replica và replication lag không?
- [ ] Database isolation được transaction manager áp thực tế không?
- [ ] Có cần query DB authoritative/bypass L2/refresh không?
- [ ] `clear`/`refresh` có thể làm mất pending changes không?
- [ ] Code có phân biệt flush với commit không?
- [ ] Bulk JPQL/Criteria/native SQL có được quản lý version/invalidation không?
- [ ] Mọi writers ngoài JPA có cùng concurrency contract không?
- [ ] Cache trên nhiều nodes có invalidate/replicate nhất quán không?
- [ ] Có xử lý rollback/retry bằng transaction mới không?
- [ ] Có database constraints, optimistic/pessimistic locks hoặc atomic DML cho critical invariants không?
- [ ] Tenant ID/authorization được xử lý đúng trong cache keys và queries không?
- [ ] Có metrics cache hits/misses, stale incidents, SQL count, lock waits và DB load không?
- [ ] Có integration tests nhiều EntityManagers, nhiều transactions và target database không?
- [ ] Có kế hoạch invalidation/disable cache khi phát hiện stale incident không?

## 50. Bảng tra cứu nhanh

| Cần làm gì? | API hoặc hướng tiếp cận |
|---|---|
| Đọc entity theo identity | `em.find(Entity.class, id)` |
| Cùng entity trong L1 | Identity map của persistence context |
| Cấu hình shared cache mode | `SharedCacheMode` / `<shared-cache-mode>` |
| Chọn entity có thể vào L2 | `@Cacheable(true)` theo mode |
| Loại entity khỏi L2 | `@Cacheable(false)` theo mode |
| Bỏ shared-cache retrieval | `CacheRetrieveMode.BYPASS` |
| Bỏ shared-cache store | `CacheStoreMode.BYPASS` |
| Yêu cầu refresh shared-cache entry | `CacheStoreMode.REFRESH` |
| Xem shared cache API | `emf.getCache()` |
| Evict một entity ID khỏi L2 | `cache.evict(Entity.class, id)` |
| Evict cả entity class khỏi L2 | `cache.evict(Entity.class)` |
| Evict mọi L2 entries | `cache.evictAll()` |
| Tải lại managed entity | `em.refresh(entity)` |
| Detach một entity | `em.detach(entity)` |
| Detach tất cả entities trong context | `em.clear()` |
| Đồng bộ pending changes với DB transaction | `em.flush()` |
| Chốt DB transaction | `commit()` / transaction manager |
| Undo transaction | `rollback()` |
| Phát hiện stale managed write | `@Version` optimistic locking |
| Đọc/sửa under pessimistic lock | `LockModeType.PESSIMISTIC_WRITE` |
| Atomic conditional update | `UPDATE ... WHERE condition` |
| Transaction isolation trong Spring | `@Transactional(isolation = ...)` |
| Query cache | Provider-specific config/hints |
| Query đọc một DTO | JPQL constructor/Criteria DTO projection |
| Bảo vệ uniqueness | Database UNIQUE constraint |
| Xử lý external cache invalidation | Event/outbox/CDC/cache strategy |
| Xác minh cache/isolation | 2 EMs, SQL logging, integration tests |

## 51. Tổng kết

Những điểm quan trọng nhất:

1. **L1 persistence context là cơ chế quản lý entity identity** trong JPA; nó không chỉ là tùy chọn performance cache.
2. **L2 shared cache là tùy chọn/provider-managed** và có thể tái sử dụng entity state giữa nhiều EntityManagers, nhưng không tự làm dữ liệu luôn mới.
3. **Query cache khác entity cache**; `@Cacheable` không mặc định cache mọi JPQL result.
4. **READ COMMITTED không bắt buộc `find` lần hai tạo SQL** khi entity vẫn managed ở L1.
5. **REPEATABLE READ snapshot có thể tiếp tục trả state cũ ngay cả khi đã clear/bypass caches**; đó là database isolation, không phải lỗi cache.
6. **flush không phải commit**; transaction khác không được coi pending changes là đã committed.
7. **`refresh` nạp lại managed entity theo JPA semantics nhưng có thể ghi đè local changes**; việc thấy commit mới còn phụ thuộc DB visibility.
8. **`clear` và L2 eviction có tác động khác nhau**; evict shared cache không cập nhật managed Java object.
9. **`CacheRetrieveMode.BYPASS` chỉ giải quyết shared cache retrieval**, không phải mọi tầng cache và không phá DB isolation.
10. **`@Version` phát hiện stale writes, không bảo đảm fresh reads**; critical decisions vẫn cần transaction/concurrency policy đúng.
11. **Bulk JPQL/native SQL có thể làm L1/L2/query caches stale**, và cần tự đánh giá version/invalidation/refresh strategy.
12. **Nhiều instances, read replicas và Redis/CDN** làm yêu cầu consistency phức tạp hơn phạm vi JPA.
13. **Không dùng cache/TTL thay database constraints, atomic updates, locking hoặc serializable isolation** khi invariant không cho phép sai.
14. **Đánh giá correctness bằng concurrency integration tests**, không chỉ bằng SQL count hay cache hit rate.

**Kết luận:** Để đánh giá đúng tương tác giữa **cache, giao dịch và mức cô lập** trong JPA, cần theo dõi đường đi của dữ liệu từ **managed entity trong persistence context**, qua **shared/query cache**, tới **database transaction snapshot**. Một lần đọc “nhanh hơn” không nhất thiết là “mới hơn”; một kết quả “không đổi” không nhất thiết chứng minh REPEATABLE READ; và một lần flush không có nghĩa dữ liệu đã commit. Khi phân biệt rõ từng lớp, kiểm soát transaction boundary, chọn cache policy theo mức stale chấp nhận được, đồng bộ các writers và kiểm thử trên stack thật, ứng dụng vừa có thể **tận dụng hiệu năng cache** vừa **bảo vệ tính nhất quán của dữ liệu nghiệp vụ**.
