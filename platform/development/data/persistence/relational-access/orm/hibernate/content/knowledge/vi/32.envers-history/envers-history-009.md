# Các chiến lược lưu lịch sử và đánh đổi về truy vấn với dung lượng

Trong một hệ thống dùng Hibernate, nhu cầu lưu lịch sử không chỉ là thêm `createdAt` và `updatedAt` vào bảng nghiệp vụ. Các câu hỏi thường gặp là: **Đơn hàng ở revision 150 có trạng thái gì? Ai đổi giá? Một entity từng bị xóa chưa? Tại ngày chốt sổ, tập bản ghi có dữ liệu như thế nào?**

Hibernate Envers là một phần mở rộng của Hibernate ORM nhằm lưu **lịch sử các phiên bản entity** khi thao tác tạo, sửa, xóa đi qua cơ chế ORM được Envers theo dõi. Khi bật audit, Envers thường lưu các trạng thái đã được audit vào bảng lịch sử, ví dụ `purchase_orders_AUD`, và liên kết với một bảng revision chung như `REVINFO`.

Tuy nhiên, một lịch sử có thể gồm hàng triệu hoặc hàng tỷ phiên bản. Khi quy mô tăng, ta phải đánh đổi giữa:

- **Chi phí ghi:** mỗi entity thay đổi tạo bao nhiêu câu SQL và index updates?
- **Chi phí lưu:** bao nhiêu bản chụp, cột audit, khóa ngoại, index và retention data?
- **Chi phí truy vấn:** muốn biết trạng thái tại một revision phải tìm bản phù hợp bằng subquery hay kiểm tra khoảng hiệu lực?
- **Chi phí vận hành:** partition, archive, cleanup, migration, replication, backup và kiểm toán.
- **Độ đúng:** revision, thời gian giao dịch, actor, quan hệ, xóa, bulk updates và quyền truy cập.

Bài học thuộc chương **Lịch sử với Envers**, tập trung vào **DefaultAuditStrategy** và **ValidityAuditStrategy**, cùng những quyết định khác về snapshot/delta, phạm vi audit, modified flags và retention. Mục tiêu không phải chọn chiến lược “nhanh nhất” theo khẩu hiệu, mà là hiểu dữ liệu được lưu ra sao, SQL lịch sử thường được thực thi như thế nào và cách đánh giá trên workload thật.

---

## 1. Envers giải quyết vấn đề gì?

Giả sử entity:

~~~java
package com.example.orders;

import jakarta.persistence.*;
import org.hibernate.envers.Audited;
import java.math.BigDecimal;

@Entity
@Audited
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal totalAmount;

    @Version
    private long version;

    protected PurchaseOrder() {}

    public void changeStatus(OrderStatus nextStatus) {
        this.status = nextStatus;
    }

    public void changeTotal(BigDecimal nextTotal) {
        this.totalAmount = nextTotal;
    }
}
~~~

~~~java
public enum OrderStatus {
    DRAFT, PAID, COMPLETED, CANCELLED
}
~~~

Nếu entity trải qua:

~~~text
Revision 12: INSERT   Order 9001, status=DRAFT,     total=100
Revision 19: UPDATE   Order 9001, status=PAID,      total=100
Revision 27: UPDATE   Order 9001, status=PAID,      total=120
Revision 41: UPDATE   Order 9001, status=COMPLETED, total=120
Revision 58: DELETE   Order 9001
~~~

Ta muốn truy vấn:

- Trạng thái của Order 9001 ở revision 25.
- Những revision đã thay đổi Order 9001.
- Ai đã thực hiện revision 27.
- Tại revision 35, có bao nhiêu Order ở trạng thái PAID?
- Khi xóa ở revision 58, audit history còn thông tin nào?

Đó là mục tiêu của Envers: **truy vết các trạng thái của entity qua những revision**.

### 1.1. Envers không thay thế bảng nghiệp vụ

Bảng `purchase_orders` vẫn chứa **trạng thái hiện tại** để phục vụ các yêu cầu đọc/ghi thông thường. Bảng audit ghi lại các revision đã được Envers quan sát.

~~~mermaid
flowchart LR
    A["JPA entity write"] --> B["Hibernate flush"]
    B --> C["purchase_orders: current state"]
    B --> D["Envers audit action"]
    D --> E["purchase_orders_AUD: history"]
    D --> F["REVINFO: revision metadata"]
    G["AuditReader"] --> E
    G --> F
~~~

Không nên thay mọi truy vấn nghiệp vụ hiện tại bằng truy vấn audit: bảng lịch sử phục vụ mục đích khác, có cardinality và index strategy khác.

### 1.2. Revision không phải timestamp

Một revision là một **mốc thay đổi do Envers ghi nhận**. Nhiều entity được sửa trong cùng một transaction có thể thuộc cùng một revision. Revision entity có thể chứa timestamp và metadata của lần ghi.

Revision number không phải đồng hồ thực và không tự đảm bảo giống thứ tự commit trong mọi kịch bản concurrency. Nếu cần legal ordering theo thời điểm commit chính xác, phải xác minh contract transaction/database cụ thể; Envers không phải một global commit-order log tuyệt đối.

### 1.3. Lịch sử trạng thái khác sự kiện nghiệp vụ

Một bản audit ghi:

~~~text
status: DRAFT → PAID
~~~

không tự giải thích **vì sao** thay đổi hoặc đảm bảo đã có một PaymentSucceeded event bên ngoài DB. Envers lưu entity-state history, không phải đầy đủ event sourcing, message delivery hay immutable compliance log.

## 2. Thiết lập Envers cơ bản

Trong dự án Maven dùng Hibernate ORM 6.x, thêm module Envers có phiên bản tương thích với Hibernate core (thường do BOM/dependency management quản lý):

~~~xml
<dependency>
    <groupId>org.hibernate.orm</groupId>
    <artifactId>hibernate-envers</artifactId>
</dependency>
~~~

Với Hibernate 5.x, tọa độ group/artifact và cấu hình có thể khác. Luôn giữ Envers và ORM cùng dòng phiên bản được hỗ trợ.

Annotation cơ bản:

~~~java
import org.hibernate.envers.Audited;

@Entity
@Audited
public class Customer {
    @Id
    private Long id;

    private String name;
}
~~~

Envers theo dõi các thay đổi của những entity/properties đã được cấu hình audit qua **đường ghi ORM thông thường**.

### 2.1. Các bảng thường được tạo

Ví dụ minh họa cấu trúc, không phải DDL chính xác mọi dialect:

~~~sql
CREATE TABLE REVINFO (
    REV INTEGER PRIMARY KEY,
    REVTSTMP BIGINT NOT NULL
);

CREATE TABLE purchase_orders_AUD (
    id BIGINT NOT NULL,
    REV INTEGER NOT NULL,
    REVTYPE SMALLINT,
    status VARCHAR(30),
    total_amount DECIMAL(19,2),
    PRIMARY KEY (id, REV),
    FOREIGN KEY (REV) REFERENCES REVINFO(REV)
);
~~~

Tên bảng/cột, kiểu khóa, constraints và chiến lược ID phụ thuộc naming strategies, Envers config, mapping và database. Một số schema có thêm cột quan hệ, column flags hoặc end-revision columns.

### 2.2. Ý nghĩa ba thành phần chung

| Cột | Vai trò |
| --- | --- |
| `id` | Định danh entity được audit |
| `REV` | Revision mà phiên bản này xuất hiện |
| `REVTYPE` | Loại thao tác ADD, MOD, DEL |

Envers biểu diễn `RevisionType` thông thường là:

- `ADD`: entity được tạo.
- `MOD`: entity được sửa.
- `DEL`: entity bị xóa.

Các mã lưu trữ thường là 0/1/2 tương ứng, nhưng application code nên dùng API/enum thay vì phụ thuộc raw number không được version hóa trong contract của mình.

## 3. Envers lưu snapshot hay delta?

Một hiểu nhầm quan trọng là “Envers chỉ ghi những cột đã đổi”. Với mô hình audit entity thông thường, Envers lưu **trạng thái của các thuộc tính được audit** tại revision, tức gần với *full-state snapshot theo mỗi lần thay đổi*, không phải một diff chỉ gồm changed properties.

Giả sử Order có:

~~~text
id = 9001
status = PAID
totalAmount = 100
customerId = 77
shippingAddress = "A"
~~~

Nếu chỉ đổi `totalAmount`, audit row mới vẫn thường có:

~~~text
id = 9001
REV = 27
REVTYPE = MOD
status = PAID
totalAmount = 120
customerId = 77
shippingAddress = "A"
~~~

### 3.1. Vì sao snapshot giúp truy vấn?

Muốn biết trạng thái entity ở revision 27, chỉ cần tìm **phiên bản audit có hiệu lực tại revision đó**. Không nhất thiết replay mọi delta từ lúc entity được tạo.

### 3.2. Giá phải trả

Nếu entity có 30 audited fields, mỗi lần chỉ đổi 1 field, bản audit mới vẫn thường lưu các giá trị của nhiều field không đổi. Với hàng triệu updates, chi phí lưu trữ có thể đáng kể.

### 3.3. Modified flags không biến Envers thành delta log

Khi bật modified flags, Envers bổ sung thông tin **trường nào đã thay đổi** tại revision. Cơ chế này không có nghĩa toàn bộ cột không đổi được loại bỏ khỏi audit row.

Ví dụ:

~~~java
@Entity
@Audited(withModifiedFlag = true)
public class PurchaseOrder {
    // ...
}
~~~

Audit table có thể thêm các cột như:

~~~text
status_MOD
totalAmount_MOD
shippingAddress_MOD
~~~

Một row sau khi đổi amount có thể là:

~~~text
status_MOD = false
totalAmount_MOD = true
shippingAddress_MOD = false
~~~

Snapshot vẫn lưu các giá trị audited cùng những flag bổ sung. Như vậy **dễ truy vấn “đổi field nào?” hơn nhưng tốn thêm dung lượng và write overhead**.

## 4. Hai chiến lược audit chính của Envers

Envers cung cấp hai chiến lược đáng chú ý:

1. **DefaultAuditStrategy**.
2. **ValidityAuditStrategy**.

Cả hai vẫn lưu revision history; khác nhau chủ yếu ở cách **xác định phiên bản nào có hiệu lực ở một revision lịch sử**.

### 4.1. Bảng so sánh ý tưởng

| Khía cạnh | DefaultAuditStrategy | ValidityAuditStrategy |
| --- | --- | --- |
| Audit row có `REV` | Có | Có |
| Audit row có end revision `REVEND` | Không theo mặc định | Có |
| Tìm state tại revision R | Chọn revision lớn nhất không vượt R | Kiểm tra khoảng `REV <= R < REVEND` |
| Số lần ghi khi update entity | Thường INSERT audit row mới | INSERT row mới **và UPDATE** end revision của row trước |
| Chi phí ghi | Thường thấp hơn | Thường cao hơn |
| Chi phí lưu một row | Ít cột hơn | Có thêm end-revision metadata |
| Query lịch sử | Có thể dùng correlated subquery | Có thể dùng range predicates |
| Index/partition | Tối ưu theo id, revision | Tối ưu theo id, REV/REVEND và timestamp nếu bật |
| Dùng cho bảng audit đọc nhiều | Có thể tốt nếu workload nhỏ/index hợp | Thường đáng thử khi as-of queries lớn/phổ biến |
| Dùng cho workload ghi cực nhiều | Thường lợi về ghi | Cần đo overhead update row lịch sử |
| Migration từ strategy khác | Không tự chuyển dữ liệu | Cần backfill end revision và kiểm thử |

**Không có quy tắc “Validity luôn nhanh hơn”.** Cần xét loại query, phân bố dữ liệu, indexes, database optimizer, concurrency, storage và retention.

## 5. DefaultAuditStrategy: lưu REV bắt đầu

Hãy theo dõi Order 9001 qua các revisions:

| id | REV | REVTYPE | status | total_amount |
| ---: | ---: | --- | --- | ---: |
| 9001 | 12 | ADD | DRAFT | 100 |
| 9001 | 19 | MOD | PAID | 100 |
| 9001 | 27 | MOD | PAID | 120 |
| 9001 | 41 | MOD | COMPLETED | 120 |
| 9001 | 58 | DEL | *không lưu dữ liệu chi tiết mặc định* | — |

Muốn trả trạng thái ở revision 35, chọn revision lớn nhất `<= 35`, tức **27**.

### 5.1. SQL khái niệm của default strategy

~~~sql
SELECT a.*
FROM purchase_orders_AUD a
WHERE a.id = :orderId
  AND a.REV = (
      SELECT MAX(x.REV)
      FROM purchase_orders_AUD x
      WHERE x.id = a.id
        AND x.REV <= :targetRevision
  )
  AND a.REVTYPE <> 2;
~~~

Đây là SQL **minh họa semantics**, không phải cam kết Hibernate tạo đúng từng alias hoặc subquery với mọi mapping/dialect.

Điều kiện `REVTYPE <> DEL` loại row deletion. Sau revision 58, revision lớn nhất là DEL nên entity không còn tồn tại ở snapshot tương ứng.

### 5.2. Truy vấn một entity theo ID có thể chấp nhận tốt

Nếu có index:

~~~sql
CREATE INDEX idx_orders_aud_id_rev
ON purchase_orders_AUD (id, REV DESC);
~~~

database có thể tìm revision gần nhất của một ID tương đối hiệu quả. Với workloads chủ yếu “mở lịch sử của một đơn hàng”, default strategy vẫn có thể đáp ứng tốt.

Không suy ra default luôn chậm chỉ vì có subquery. Index phù hợp, ít revisions/entity và query planner hiện đại có thể giúp đáng kể.

### 5.3. Truy vấn as-of cho nhiều entities khó hơn

Một câu hỏi:

> Ở revision 50.000, tất cả đơn hàng của tenant 42 có trạng thái PAID là những đơn nào?

Yêu cầu chọn **bản audit mới nhất <= 50.000 cho mỗi entity**, rồi lọc status/tenant phù hợp. Đây không phải chỉ một lookup theo ID, mà là bài toán nhiều key groups.

Một correlated max revision pattern trên bảng lịch sử lớn có thể tốn chi phí. Optimizer, distribution, filter selectivity và index design quyết định mức tốn thực tế.

## 6. ValidityAuditStrategy: thêm end revision

Validity strategy tạo thêm ranh giới kết thúc hiệu lực của mỗi phiên bản.

Ví dụ:

| id | REV | REVEND | REVTYPE | status | total_amount |
| ---: | ---: | ---: | --- | --- | ---: |
| 9001 | 12 | 19 | ADD | DRAFT | 100 |
| 9001 | 19 | 27 | MOD | PAID | 100 |
| 9001 | 27 | 41 | MOD | PAID | 120 |
| 9001 | 41 | 58 | MOD | COMPLETED | 120 |
| 9001 | 58 | NULL | DEL | — | — |

Mỗi audit row nói rằng phiên bản bắt đầu ở `REV` và kết thúc **trước** `REVEND`.

Ví dụ row REV 27 có hiệu lực tại:

~~~text
27 <= targetRevision < 41
~~~

Row mới nhất thường có `REVEND = NULL` vì chưa có revision audit tiếp theo cho entity đó. Sau DELETE, row deletion có thể là phiên bản cuối và giúp Envers biết entity không còn tồn tại.

### 6.1. Công thức khoảng nửa mở

Với revision R:

\[
\mathrm{REV} \le R \land
(\mathrm{REVEND} > R \lor \mathrm{REVEND\ IS\ NULL})
\]

Dạng `[REV, REVEND)` giúp mỗi revision chỉ khớp một phiên bản hợp lệ của một entity nếu dữ liệu lịch sử nhất quán.

### 6.2. SQL khái niệm

~~~sql
SELECT a.*
FROM purchase_orders_AUD a
WHERE a.id = :orderId
  AND a.REV <= :targetRevision
  AND (
      a.REVEND > :targetRevision
      OR a.REVEND IS NULL
  )
  AND a.REVTYPE <> 2;
~~~

SQL này thường rõ ràng hơn về hiệu lực phiên bản và có thể cho database dùng range predicates/indexes phù hợp. Nhưng predicate có `OR ... IS NULL`, độ chọn lọc và index layout vẫn cần benchmark.

### 6.3. Vì sao chi phí ghi cao hơn?

Khi cập nhật Order tại revision 41, strategy cần:

1. Thêm audit row mới bắt đầu ở 41.
2. Đóng row trước đó bằng `REVEND = 41`.

SQL khái niệm:

~~~sql
UPDATE purchase_orders_AUD
SET REVEND = 41
WHERE id = 9001 AND REV = 27;

INSERT INTO purchase_orders_AUD
    (id, REV, REVEND, REVTYPE, status, total_amount)
VALUES
    (9001, 41, NULL, 1, 'COMPLETED', 120);
~~~

Đây là **thêm một UPDATE vào bảng lịch sử** so với chiến lược chỉ thêm audit row. Nó có thể tăng:

- Write amplification.
- WAL/redo/transaction log.
- Index maintenance.
- Row locks trên audit row trước.
- Chi phí vacuum/bloat tùy database.
- Độ phức tạp rollback và migration.

Không nên chỉ nhìn audit table có thêm một cột rồi cho rằng storage overhead của validity chỉ là kích thước `REVEND`. UPDATE row cũ cũng có chi phí vận hành.

## 7. Cấu hình Default và Validity trong Hibernate

Cấu hình `DefaultAuditStrategy` dùng class của Envers:

~~~properties
org.hibernate.envers.audit_strategy=org.hibernate.envers.strategy.DefaultAuditStrategy
~~~

Chuyển sang validity:

~~~properties
org.hibernate.envers.audit_strategy=org.hibernate.envers.strategy.ValidityAuditStrategy
~~~

Ví dụ Spring Boot `application.yml`:

~~~yaml
spring:
  jpa:
    properties:
      org.hibernate.envers.audit_strategy: org.hibernate.envers.strategy.ValidityAuditStrategy
      org.hibernate.envers.audit_strategy_validity_store_revend_timestamp: true
~~~

Tên property này thuộc cấu hình Envers của các phiên bản Hibernate tương ứng. Cần kiểm tra tài liệu cho version ORM/Envers thực tế, đặc biệt khi nâng từ Hibernate 5 sang 6/7.

### 7.1. Không coi việc đổi config là migration dữ liệu

Nếu ứng dụng đã có bảng `_AUD` theo default strategy, chỉ đổi property sang validity **không tự điền `REVEND` cho toàn bộ audit history cũ**.

Cần:

- Thêm các cột/schema liên quan.
- Backfill end revisions cho từng entity key.
- Kiểm tra thứ tự revisions và deletion rows.
- Thực hiện migration trong điều kiện concurrency được kiểm soát.
- Xác nhận kết quả AuditReader trước/sau.
- Có rollback plan và backup.

Bỏ qua bước này có thể làm as-of queries trả nhiều phiên bản hoặc kết quả sai.

### 7.2. Tùy chỉnh tên cột end revision

Envers có các properties hỗ trợ đặt tên cột end revision và timestamp trong những phiên bản thích hợp, ví dụ naming theo `REVEND`, `REVEND_TSTMP`. Nếu dùng naming strategy hoặc schema conventions riêng, xác minh DDL được tạo thực tế thay vì đoán tên cố định.

### 7.3. Một persistence unit cần một chiến lược nhất quán

Không nên giả định có thể tùy ý dùng default cho một audited entity và validity cho entity khác trong cùng cấu hình Envers mà không có extension/kiến trúc đặc biệt. Audit strategy được chọn ở mức cấu hình Envers của persistence unit/session factory; cần tính đến toàn bộ bảng lịch sử khi migration.

## 8. REVEND_TSTMP: thời điểm kết thúc cho vận hành dữ liệu

Validity strategy có thể lưu thêm timestamp của revision kết thúc:

~~~properties
org.hibernate.envers.audit_strategy_validity_store_revend_timestamp=true
~~~

Khi được cấu hình, mỗi audit row có thể có cột tương ứng như `REVEND_TSTMP`.

### 8.1. REVEND khác REVEND_TSTMP

- `REVEND`: số revision tiếp theo đã kết thúc phiên bản này.
- `REVEND_TSTMP`: timestamp gắn với end revision, hữu ích cho vận hành/partitioning/retention theo thời gian.
- `REVINFO.REVTSTMP`: timestamp của revision bắt đầu/được ghi nhận.

`REVEND_TSTMP` không phải “thời gian entity được user sửa lần đầu” và cũng không tự là commit timestamp tuyệt đối.

### 8.2. Vì sao lưu thêm timestamp?

Để quản lý bảng audit theo thời gian, có thể muốn biết những version nào **đã kết thúc hiệu lực trước một mốc cutoff**. Khi đó có thể thuận lợi hơn cho partitioning/archiving so với phải join `REVINFO` để suy timestamp end revision của từng row.

### 8.3. Cái giá phải trả

- Thêm cột cho audit rows.
- Có thể thêm index.
- UPDATE audit row trước phải ghi thêm timestamp khi kết thúc.
- Timestamp conversion/precision cần nhất quán.
- Migration backfill phải tra timestamp của revision kết thúc.
- Các row đang còn hiệu lực có `REVEND_TSTMP = NULL`.

### 8.4. Không thể purge mọi row cũ chỉ dựa trên created timestamp

Một row bắt đầu ở revision năm 2020 nhưng vẫn là phiên bản có hiệu lực đến năm 2026. Nếu xóa vì `REVINFO.REVTSTMP` của nó quá cũ, truy vấn hiện tại hoặc truy vấn as-of gần đây có thể mất baseline.

Retention/partitioning phải dựa trên **phạm vi phiên bản còn cần thiết**, không đơn thuần trên ngày tạo của audit row.

## 9. Minh họa trực quan hai chiến lược

~~~mermaid
flowchart TD
    A["Revision 12: ADD"] --> B["Revision 19: MOD"]
    B --> C["Revision 27: MOD"]
    C --> D["Revision 41: MOD"]
    D --> E["Revision 58: DEL"]
    F["Default strategy"] --> G["Mỗi lần thêm audit row REV"]
    H["Validity strategy"] --> I["Thêm row REV + đóng row trước bằng REVEND"]
    G --> J["Query as-of: MAX REV <= target"]
    I --> K["Query as-of: REV <= target < REVEND"]
~~~

Một kết luận quan trọng:

**Cả hai chiến lược đều có một phiên bản audit mới mỗi khi một thay đổi được audit. Validity không xóa bớt snapshots; nó thêm metadata về khoảng hiệu lực để cải thiện một số kiểu truy vấn.**

## 10. AuditReader: đọc phiên bản lịch sử

API Envers thường bắt đầu bằng:

~~~java
import jakarta.persistence.EntityManager;
import org.hibernate.envers.AuditReader;
import org.hibernate.envers.AuditReaderFactory;

AuditReader reader = AuditReaderFactory.get(entityManager);
~~~

### 10.1. Tìm một entity tại revision

~~~java
PurchaseOrder stateAt27 =
    reader.find(PurchaseOrder.class, 9001L, 27);
~~~

Kết quả biểu diễn trạng thái lịch sử của entity tại revision 27 theo Envers. Đây không phải một managed live entity để sửa rồi mong dirty checking cập nhật bảng nghiệp vụ hiện tại.

### 10.2. Tìm tất cả revision numbers của entity

~~~java
List<Number> revisions =
    reader.getRevisions(PurchaseOrder.class, 9001L);
~~~

Ví dụ có thể nhận:

~~~text
[12, 19, 27, 41, 58]
~~~

Lịch sử chính xác phụ thuộc những thay đổi nào được Envers audit. Đổi một field `@NotAudited` mà không có audited change khác có thể không tạo revision cho entity đó.

### 10.3. Tra revision metadata

~~~java
import org.hibernate.envers.DefaultRevisionEntity;

DefaultRevisionEntity revision =
    reader.findRevision(DefaultRevisionEntity.class, 27);
~~~

Khi dùng **custom revision entity**, thay `DefaultRevisionEntity.class` bằng class revision tùy biến của dự án. Timestamp/actor metadata hiện diện theo revision entity mapping tương ứng.

### 10.4. As-of tại thời điểm

Envers có API như:

~~~java
Number revisionNumber =
    reader.getRevisionNumberForDate(
        java.util.Date.from(
            java.time.Instant.parse("2026-11-15T08:00:00Z")
        )
    );
~~~

Mốc thời gian được ánh xạ sang revision theo timestamp mà Envers lưu. **Đó không phải time-travel hoàn hảo theo commit timestamp** trong mọi trường hợp concurrency hoặc dữ liệu được backfill. Cần kiểm tra semantics của API/version và xử lý trường hợp thời điểm nằm ngoài phạm vi revision history.

### 10.5. Không đo performance chỉ qua AuditReader API

Hai hệ thống cùng gọi `reader.find()` nhưng một hệ thống dùng default strategy, hệ thống kia validity; SQL và index access paths có thể khác. Cần bật SQL log và xem execution plan để biết truy vấn thực tế.

## 11. AuditQuery: xem nhiều revisions của entity

Ví dụ:

~~~java
import org.hibernate.envers.query.AuditEntity;
import org.hibernate.envers.query.AuditQuery;

AuditQuery query = reader.createQuery()
    .forRevisionsOfEntity(
        PurchaseOrder.class,
        false,
        true
    )
    .add(AuditEntity.id().eq(9001L))
    .addOrder(AuditEntity.revisionNumber().asc());

List<?> results = query.getResultList();
~~~

Trong API `forRevisionsOfEntity(EntityClass, selectEntitiesOnly, selectDeletedEntities)`, khi `selectEntitiesOnly = false`, kết quả thường là các phần tử chứa:

1. Snapshot entity.
2. Revision entity.
3. `RevisionType`.

~~~java
for (Object item : results) {
    Object[] tuple = (Object[]) item;
    PurchaseOrder snapshot = (PurchaseOrder) tuple[0];
    Object revisionEntity = tuple[1];
    org.hibernate.envers.RevisionType type =
        (org.hibernate.envers.RevisionType) tuple[2];

    // Tạo DTO để trả API, không expose trực tiếp JPA graph.
}
~~~

Cấu trúc kết quả và khả năng truy vấn theo property phụ thuộc API/Envers version. Khi xây giao diện revision timeline, nên map thành DTO rõ ràng và giới hạn số revisions mỗi request.

### 11.1. Đọc tất cả versions có thể rất tốn

Nếu một entity bị cập nhật 100.000 lần, truy vấn toàn lịch sử rồi nạp vào memory không phù hợp. Phân trang/tìm theo khoảng revision, giới hạn số dòng và projection các field cần thiết.

### 11.2. Giao diện lịch sử thường cần hai truy vấn

Một thiết kế thường gồm:

- List revision metadata (revision, actor, timestamp, type).
- Khi user mở một revision, lấy snapshot chi tiết.

Cách này có thể giảm bytes và object hydration so với nạp toàn bộ entity snapshots ngay khi mở trang lịch sử.

## 12. Truy vấn trạng thái của một tập entity tại revision

Envers hỗ trợ dạng query:

~~~java
List<?> paidOrders = reader.createQuery()
    .forEntitiesAtRevision(
        PurchaseOrder.class,
        1000
    )
    .add(
        AuditEntity.property("status")
            .eq(OrderStatus.PAID)
    )
    .getResultList();
~~~

Ý nghĩa: lấy những entities được audit có trạng thái thỏa điều kiện **tại revision lịch sử được yêu cầu**.

### 12.1. Khác với query bảng hiện tại

~~~hql
select o
from PurchaseOrder o
where o.status = :status
~~~

Query live chỉ thấy **trạng thái hiện tại**. Envers as-of query phải xác định version hợp lệ cho mỗi entity; chi phí thường lớn hơn.

### 12.2. Default strategy có thể cần subquery cho mỗi group

Với audit history lớn, việc tìm latest revision <= R theo nhiều IDs là một workload quan trọng. Tùy database, correlated subquery/max pattern có thể tạo nhiều index lookups hoặc scan.

### 12.3. Validity strategy biểu diễn state bằng khoảng

Đối với mỗi row:

~~~text
REV <= R
AND (REVEND > R OR REVEND IS NULL)
~~~

Điều kiện khoảng có thể thuận lợi hơn cho query planner trong nhiều trường hợp. Nhưng khi query lọc nhiều properties, join associations và trả hàng trăm nghìn entities, index/physical design vẫn quyết định phần lớn latency.

### 12.4. Query nhiều revision có thể đắt ở cả hai

Nếu báo cáo cần 365 snapshots theo ngày cho 5 triệu entities, kể cả validity strategy vẫn là một khối lượng tính toán lớn. Có thể cần:

- Materialized daily snapshots.
- Warehouse analytics.
- Incremental aggregate tables.
- Partitioned/cold historical storage.
- Bounded reports theo tenant/time.

Không ép mọi báo cáo phân tích lịch sử khối lượng lớn đi qua AuditReader online.

## 13. Khi chỉ muốn biết “field nào thay đổi?”

Envers modified flags có thể hỗ trợ query revisions đã thay đổi một thuộc tính.

### 13.1. Bật ở class

~~~java
@Entity
@Audited(withModifiedFlag = true)
public class PurchaseOrder {
    // ...
}
~~~

Hoặc đánh dấu ở thuộc tính phù hợp theo API Envers version:

~~~java
@Audited(withModifiedFlag = true)
private BigDecimal totalAmount;
~~~

### 13.2. Truy vấn revisions có thay đổi thuộc tính

~~~java
List<?> changes = reader.createQuery()
    .forRevisionsOfEntity(
        PurchaseOrder.class,
        false,
        true
    )
    .add(AuditEntity.id().eq(9001L))
    .add(
        AuditEntity.property("totalAmount").hasChanged()
    )
    .getResultList();
~~~

Đây là một lợi ích rõ ràng khi audit UI cần “những lần thay đổi giá”. Cần bật modified flag cho thuộc tính muốn dùng với predicate `hasChanged()` theo Envers contract.

### 13.3. Chi phí của modified flags

Giả sử một entity có 50 audited properties và bật flag cho tất cả. Audit table có thể có thêm khoảng 50 boolean columns, tăng:

- Row width và schema complexity.
- Data/index storage nếu cần index flags.
- Chi phí INSERT audit rows.
- Migration khi field mới xuất hiện.
- Độ phức tạp truy vấn/reporting.

Vì vậy chỉ bật flags ở các fields phục vụ query thực tế hoặc khi product yêu cầu diff UI rộng. **Modified flag không thay thế lịch sử snapshot**, cũng không tạo một audit event đầy đủ nguyên nhân thay đổi.

### 13.4. Có thể tính diff bằng cách so hai snapshots

Nếu ít revisions, UI có thể tải hai versions liền nhau rồi so các audited fields. Cách này tránh thêm columns flags nhưng tăng chi phí đọc/CPU, đặc biệt khi entity rộng hoặc nhiều requests.

Đây là một trade-off giữa **lưu trước thông tin thay đổi** và **tính khi cần**.

## 14. Phạm vi @Audited và @NotAudited ảnh hưởng dung lượng

Không phải mọi thuộc tính đều đáng lưu ở mọi revision.

Ví dụ:

~~~java
@Entity
@Audited
public class Product {

    @Id
    private Long id;

    private BigDecimal listPrice;

    private String displayName;

    @org.hibernate.envers.NotAudited
    @Lob
    private String htmlDescription;

    @org.hibernate.envers.NotAudited
    private Long transientViewCounter;
}
~~~

Nếu `htmlDescription` rất lớn và `transientViewCounter` tăng liên tục, loại khỏi audit có thể giảm đáng kể dung lượng/tần suất history.

### 14.1. Không audit counter kỹ thuật nếu không có giá trị nghiệp vụ

Các counters tần suất cao như view count, lastSeen, cache refresh timestamp thường không phải lịch sử cần bảo toàn mọi lần. Đưa chúng vào audited entity có thể tạo nhiều audit rows và làm lịch sử nghiệp vụ nhiễu.

Cân nhắc:

- Tách counters sang bảng/entity không audited.
- Dùng aggregate metrics riêng.
- Ghi event sampling nếu cần analytics.
- Audit chỉ business-critical fields.

### 14.2. Đổi phạm vi audit làm thay đổi tính đầy đủ của snapshot

Nếu `htmlDescription` là `@NotAudited`, không được tuyên bố Envers tái tạo **toàn bộ entity** chính xác tại mọi revision. Những trường không audited không có lịch sử tương ứng.

Một số relation target not-audited còn có semantics tra dữ liệu hiện tại thay vì lịch sử; cần review kỹ khi hiển thị “trạng thái năm ngoái”.

### 14.3. Chia aggregate thành các entity phù hợp

Nếu một entity có 100 fields nhưng chỉ 10 fields thay đổi thường xuyên và cần audit, có thể cân nhắc:

- Tách cấu trúc thành các entities/value objects với lifecycle phù hợp.
- Audit phần business-critical.
- Không audit dữ liệu cache/derived.
- Không phá aggregate invariants chỉ để giảm audit rows.

Thiết kế domain đúng vẫn ưu tiên hơn tối ưu dung lượng mù quáng.

## 15. Quan hệ thực thể và bùng nổ lịch sử

Envers không chỉ audit scalar properties. Associations có thể khiến số audit rows và bảng join audit tăng đáng kể.

Giả sử:

~~~java
@Entity
@Audited
public class PurchaseOrder {

    @Id
    private Long id;

    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines;
}
~~~

~~~java
@Entity
@Audited
public class OrderLine {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private PurchaseOrder order;

    private int quantity;
}
~~~

Một transaction có thể thay đổi parent, thêm 10 lines và sửa 5 lines. Tùy mapping, ownership và Envers relation auditing, có thể có nhiều audit rows ở các bảng liên quan, không phải chỉ một row `PurchaseOrder_AUD`.

### 15.1. Khi collection change tạo revision

Envers có configuration liên quan `revision_on_collection_change` để quyết định xử lý một số thay đổi ở phía collection không sở hữu quan hệ. Default behavior và chi tiết tùy Envers version/mapping.

Với aggregate có collection thay đổi thường xuyên, cần đo:

- Số revision rows ở parent.
- Số revision rows ở child.
- Số rows trong audit join table.
- Write amplification của validity.
- SQL truy vấn tái tạo relation tại revision cũ.

### 15.2. @ManyToMany và audit join table

Một association nhiều-nhiều có thể cần một audit table riêng để lưu lịch sử liên kết. Việc thêm/bỏ N links có thể tăng row count khác với số entities nghiệp vụ được thay đổi.

Không dự đoán storage chỉ bằng “mỗi entity update = 1 audit row” nếu graph có collections.

### 15.3. Audited relation trỏ tới non-audited target

Trong các tình huống được hỗ trợ, Envers có API như:

~~~java
@Audited(
    targetAuditMode =
        org.hibernate.envers.RelationTargetAuditMode.NOT_AUDITED
)
@ManyToOne(fetch = FetchType.LAZY)
private Currency currency;
~~~

Nếu relation target không audited, lịch sử có thể tham chiếu **giá trị hiện tại của target** thay vì trạng thái target ở revision cũ. Điều này có thể phù hợp cho lookup table bất biến (`Currency`), nhưng nguy hiểm nếu target thay đổi tên/thuộc tính theo thời gian.

Dù bảng audit nhỏ hơn, lịch sử quan hệ có thể không còn biểu diễn “đúng dữ liệu tại thời điểm đó” theo nghĩa người dùng mong đợi.

## 16. Revision entity và actor metadata

Envers cho phép custom revision entity để ghi actor, tenant, request ID hoặc source system.

Ví dụ:

~~~java
import jakarta.persistence.*;
import org.hibernate.envers.*;

@Entity
@RevisionEntity(ActorRevisionListener.class)
@Table(name = "audit_revision")
public class ActorRevision {

    @Id
    @GeneratedValue
    @RevisionNumber
    private int id;

    @RevisionTimestamp
    private long timestamp;

    @Column(name = "actor_id", length = 100)
    private String actorId;

    @Column(name = "source_system", length = 50)
    private String sourceSystem;

    public void setActorId(String actorId) {
        this.actorId = actorId;
    }

    public void setSourceSystem(String sourceSystem) {
        this.sourceSystem = sourceSystem;
    }
}
~~~

Listener:

~~~java
import org.hibernate.envers.RevisionListener;

public class ActorRevisionListener
        implements RevisionListener {

    @Override
    public void newRevision(Object revisionEntity) {
        ActorRevision rev = (ActorRevision) revisionEntity;

        AuditActor actor = AuditActorContext.current();
        rev.setActorId(actor.id());
        rev.setSourceSystem(actor.sourceSystem());
    }
}
~~~

`AuditActor` và `AuditActorContext` là abstraction ứng dụng phải triển khai, lấy dữ liệu từ context đã được xác thực. Không giả định Envers listener tự là Spring bean hoặc luôn inject được `SecurityContext` như service bình thường.

### 16.1. Revision entity dùng chung cho nhiều entity changes

Một transaction cập nhật nhiều audited entities có thể cùng dùng một revision entity. Vì vậy actor, timestamp, request ID ở revision level phù hợp khi các changes thuộc cùng một thao tác.

Nếu cần **actor khác nhau cho từng thay đổi trong cùng transaction**, revision-level metadata có thể không đủ. Cần thiết kế per-change audit event hoặc metadata riêng.

### 16.2. Revision entity không nên quá rộng

Nếu mỗi revision chứa payload JSON hàng KB, bảng revision cũng lớn hơn và joins trong audit queries nặng hơn.

Thường chỉ lưu định danh/correlation metadata quan trọng trong revision entity; payload chi tiết có thể nằm ở event storage riêng, với quyền truy cập/retention phù hợp.

### 16.3. Không dựa vào client-supplied actor

Actor ID phải đến từ principal/job context được server xác minh. Một HTTP request gửi `updatedBy = admin` không nên có quyền quyết định audit author.

### 16.4. Thread và async boundaries

Security context hoặc custom `ThreadLocal` không tự lan sang thread khác trong job/`@Async`. Nếu audit listener chạy trong worker, cần truyền context an toàn và giải phóng sau mỗi task, tránh nhầm actor giữa requests.

## 17. Vì sao Validity có thể đọc nhanh hơn nhưng ghi chậm hơn?

### 17.1. Default: nhiều việc lúc SELECT

Default strategy thường lưu:

~~~text
(id, REV, REVTYPE, audited fields...)
~~~

Khi as-of query, database cần xác định row có REV lớn nhất không vượt target cho mỗi entity. Một số dạng query có thể được tối ưu nhờ index; với một tập rất nhiều entity groups, chi phí tìm MAX có thể tăng.

### 17.2. Validity: nhiều việc lúc UPDATE

Validity lưu:

~~~text
(id, REV, REVEND, REVTYPE, audited fields...)
~~~

Khi ghi version mới, end revision của row trước được cập nhật trước/đồng thời trong transaction. Công việc xác định khoảng hiệu lực được **trả trước lúc ghi**.

### 17.3. Quy tắc trade-off

> Default thường đánh đổi **ít work khi ghi** lấy **nhiều work khi đọc lịch sử**. Validity thường đánh đổi **thêm work khi ghi và lưu** để **đơn giản hóa một số truy vấn as-of**.

Đây là khuynh hướng, không phải bảo đảm tuyệt đối. Một workload chủ yếu xem revision timeline theo ID có thể không hưởng lợi rõ từ Validity; ngược lại, một báo cáo as-of nhiều entities có thể hưởng lợi.

## 18. Mô hình ước lượng dung lượng

Đặt:

- `E`: số audited entities được tạo trong khoảng giữ lịch sử.
- `U`: tổng số audited entity updates.
- `D`: số deletes có audit rows.
- `W`: kích thước audit row trung bình đã gồm audited columns và metadata cơ bản, **chưa tính indexes/storage overhead**.
- `V`: dung lượng thêm trung bình cho validity end revision/timestamp.
- `F`: dung lượng thêm cho modified flags.
- `I`: index/WAL/TOAST/partition/storage overhead, phụ thuộc DB.

Ước lượng thô:

\[
N_{\text{audit}} \approx E + U + D
\]

\[
S_{\text{default}} \approx N_{\text{audit}}\times W + I
\]

\[
S_{\text{validity}} \approx
N_{\text{audit}}\times (W+V+F) + I'
\]

`I'` có thể lớn hơn `I` vì index trên `REVEND`/timestamp và write amplification, nhưng còn tùy DB compression/physical design.

### 18.1. Ví dụ định lượng

Giả sử:

- 20 triệu Orders được tạo.
- Tổng cộng 80 triệu lần update audited fields.
- 5 triệu lần xóa có audit record.
- Trung bình 500 bytes dữ liệu vật lý/audit row trong giả định đơn giản.

Khi đó:

~~~text
Audit rows ≈ 20M + 80M + 5M = 105M rows

Dữ liệu audit thô ≈ 105M × 500 bytes
                     = 52.5 tỷ bytes
                     ≈ 52.5 GB (decimal)
~~~

Con số **không** bao gồm index, page overhead, TOAST/LOB, WAL, replication, vacuum bloat, backup và thông tin revision table. Kích thước thực tế có thể khác rất lớn.

Nếu thêm 24 bytes/row cho end metadata/flags theo một giả định minh họa:

~~~text
105M × 24 bytes ≈ 2.52 GB dữ liệu thô bổ sung
~~~

Đó chỉ là **storage rows**; validity strategy còn UPDATE những row trước và có thể làm phát sinh WAL/index work, không được đánh giá chỉ bằng 2.52 GB.

### 18.2. Cái quan trọng thường là update frequency

Một bảng có 50 triệu rows nhưng mỗi row gần như không đổi có thể có audit history nhỏ hơn bảng 1 triệu rows bị update hàng trăm lần.

Cần đo:

- Số audited changes/entity/ngày.
- Distribution: phần lớn entities ít sửa hay một số hot entities sửa cực nhiều?
- Kích thước audited columns.
- Collection/link churn.
- Retention duration.
- Số snapshots truy vấn mỗi ngày.
- Tỷ lệ read/write trong audit workload.

## 19. Tần suất thay đổi và hot entities

Một order thường chỉ đổi vài lần: DRAFT → PAID → SHIPPED → COMPLETED. Nhưng một tài khoản tổng hợp, counter hoặc mutable configuration record có thể đổi hàng nghìn lần mỗi giờ.

Nếu Envers audit cả hai như nhau, hot entity có thể tạo audit table rất lớn và tăng write contention.

### 19.1. Tách dữ liệu nhiều biến động

Nếu `viewCounter` thay đổi 10.000 lần/ngày nhưng không cần pháp lý lưu mọi lần, tách nó khỏi audited entity hoặc đánh dấu `@NotAudited` giúp hạn chế audit churn.

### 19.2. Validity update có thể gây contention

Mỗi version mới cần đóng row trước; nếu nhiều transactions cùng sửa cùng entity, bản thân entity version/DB lock đã tạo contention, nhưng validity còn có thao tác trên audit row trước. Cần test hotspot scenarios với isolation và optimistic locking, không chỉ benchmark ghi các IDs độc lập.

### 19.3. Bỏ audit một field cần hiểu trade-off

Nếu thay đổi chỉ ở field `@NotAudited`, Envers có thể không tạo revision mới cho entity. Điều này giúp tiết kiệm nhưng cũng có nghĩa lịch sử không phản ánh mọi write operation của entity.

Cần có hợp đồng rõ “lịch sử những trường nào”, không gắn tên “full audit” cho một tập dữ liệu đã loại nhiều fields.

## 20. Chỉ số hiệu năng cần so sánh

Không chỉ benchmark một lần gọi `reader.find()`.

| Chỉ số | Tại sao quan trọng |
| --- | --- |
| Entity writes/second | Throughput của transaction nghiệp vụ |
| P95/P99 write latency | Validity có làm write path chậm ở tail không? |
| JDBC statements/update | Thấy thêm UPDATE audit row không? |
| Audit rows/transaction | Collection/relation changes tạo thêm bao nhiêu? |
| WAL/redo bytes/second | Ước lượng write amplification |
| Index page reads/writes | Thực tế index hoạt động ra sao |
| P95 as-of entity lookup | Lịch sử theo một ID |
| P95 as-of list/report | Lịch sử theo tập nhiều IDs |
| Revision timeline latency | Đọc toàn bộ revisions hoặc khoảng revision |
| Audit table/index size | Dung lượng và backup |
| Deadlocks/lock waits | Hot entities và concurrency |
| DB CPU/IO/memory | Chi phí query plans |
| Retention/archival duration | Khả năng vận hành dữ liệu lớn |

### 20.1. Đo cùng dataset và workload

So sánh hai chiến lược trên dữ liệu khác nhau có thể gây sai lệch. Benchmark cần:

- Cùng tỷ lệ updates/deletes per entity.
- Cùng kích thước columns/relations.
- Cùng page caches và DB versions.
- Cùng transactions/concurrency/isolation.
- Cùng indexes phù hợp từng chiến lược.
- Cùng truy vấn as-of theo ID và tập entities.

Kết quả nên được lưu cùng SQL EXPLAIN/metrics, không chỉ một bảng “Validity nhanh hơn 3 lần” thiếu bối cảnh.

## 21. Index cho DefaultAuditStrategy

Đối với timeline hoặc tìm phiên bản theo entity ID:

~~~sql
CREATE INDEX idx_orders_aud_id_rev_desc
ON purchase_orders_AUD (id, REV DESC);
~~~

Index này có thể hỗ trợ truy vấn:

~~~sql
SELECT *
FROM purchase_orders_AUD
WHERE id = :id
  AND REV <= :revision
ORDER BY REV DESC
FETCH FIRST 1 ROW ONLY;
~~~

SQL dùng `FETCH FIRST` mang tính minh họa; syntax và plan phụ thuộc DB.

### 21.1. Index chỉ trên REV thường chưa đủ

Nếu workload luôn hỏi lịch sử theo một ID, composite index `(id,REV)` thường hợp lý hơn chỉ `(REV)`. Nhưng revision timeline theo thời gian hoặc audit analytics toàn hệ thống có thể cần index khác.

### 21.2. Không index mọi audited property

Nếu audit table có 50 fields mà tạo index cho tất cả, storage/write overhead có thể vượt lợi ích. Chọn indexes theo query patterns thực, ví dụ actor/time, status tại revision hay ID/revision.

### 21.3. As-of list queries cần kế hoạch riêng

Một index `(id,REV)` rất tốt cho single-ID lookup chưa chắc giải quyết được báo cáo “mọi entities tại R với status X”. Có thể cần index/projection/reporting path khác; xem `EXPLAIN (ANALYZE, BUFFERS)` trên database mục tiêu.

## 22. Index cho ValidityAuditStrategy

Validity query thường có:

~~~sql
WHERE a.id = :id
  AND a.REV <= :target
  AND (a.REVEND > :target OR a.REVEND IS NULL)
~~~

Ứng viên index:

~~~sql
CREATE INDEX idx_orders_aud_id_rev_revend
ON purchase_orders_AUD (id, REV, REVEND);
~~~

Hoặc tách:

~~~sql
CREATE INDEX idx_orders_aud_id_rev
ON purchase_orders_AUD (id, REV);

CREATE INDEX idx_orders_aud_id_revend
ON purchase_orders_AUD (id, REVEND);
~~~

Không tạo cả hai biến thể vô điều kiện. Index selection phụ thuộc query selectivity, table size, DB capabilities và execution plans.

### 22.1. REVEND có nhiều NULL

Row hiện đang có hiệu lực có thể có `REVEND IS NULL`. Tỷ lệ NULL phụ thuộc số entities còn live và số historical versions. Index behavior với NULL khác nhau theo DB; có thể cân nhắc partial indexes khi DB hỗ trợ, nhưng phải benchmark.

### 22.2. End timestamp index cho retention

Khi bật `REVEND_TSTMP`:

~~~sql
CREATE INDEX idx_orders_aud_end_time
ON purchase_orders_AUD (REVEND_TSTMP);
~~~

Index này có thể giúp identify những rows đã kết thúc trước cutoff. Tuy nhiên, chi phí update/index và kế hoạch partition phải cân nhắc; với partition pruning tốt có thể không cần thêm index giống nhau trên mọi partitions.

## 23. Partitioning audit tables

Khi audit table lớn, partitioning có thể giúp:

- Prune partitions khi queries/filter phù hợp.
- Archive/drop những partitions hết retention.
- Giảm kích thước indexes riêng từng partition.
- Cải thiện maintenance và backup strategy trong một số hệ thống.

### 23.1. Vì sao partition theo REV đơn giản nhưng cleanup khó?

Nếu partition theo `REV` lúc bắt đầu phiên bản, một row bắt đầu năm 2020 có thể vẫn là phiên bản cần dùng cho as-of năm 2026. Xóa toàn partition 2020 có thể làm mất baseline cho các phiên bản sau.

### 23.2. REVEND_TSTMP hữu ích khi phiên bản đã kết thúc

Với ValidityAuditStrategy và end timestamp, có thể nghiên cứu partition/retention dựa trên **thời điểm kết thúc hiệu lực**, sao cho những phiên bản đã kết thúc trước cutoff được xác định dễ hơn.

Nhưng thiết kế thực tế vẫn phức tạp:

- Row còn active có `REVEND_TSTMP=NULL`.
- Partition key có thể thay đổi khi row kết thúc, kéo theo row movement tùy DB.
- Foreign keys tới revision table có thể cản drop partitions.
- Audit query cần baseline cho cutoff đầu tiên.
- Lịch sử quan hệ/child tables có thể cần giữ lâu hơn root.
- Một số revision metadata có thể dùng chung nhiều audit tables.

Không mô tả “bật REVEND_TSTMP rồi drop partition cũ là xong” như một tính năng tự động của Envers.

### 23.3. Cold archive không giữ AuditReader hoạt động tự động

Nếu chuyển audit rows sang object storage hoặc warehouse rồi xóa khỏi DB chính, `AuditReader` kết nối DB hiện tại sẽ không tự tìm lịch sử đã archive.

Cần một contract API rõ: dữ liệu gần đây đọc online, lịch sử cũ truy vấn archive service hoặc được restore theo quy trình. Các giới hạn này phải được sản phẩm chấp nhận.

### 23.4. PostgreSQL partitioning có giới hạn schema riêng

Khả năng tạo primary key/unique constraints trên partitioned tables, foreign keys, update partition key và index locality phụ thuộc database version/cấu hình. Trước khi chuyển bảng `_AUD` sang partitioning, thử migration/DDL/query Envers trên DB version thực; không chỉ viết DDL giả định.

## 24. Retention: giữ lịch sử bao lâu?

Có các yêu cầu khác nhau:

- 30–90 ngày cho debug hoạt động gần đây.
- 1–3 năm cho hỗ trợ khách hàng.
- 5–10 năm hoặc lâu hơn cho tài chính/tuân thủ tùy quy định.
- Legal hold yêu cầu giữ một số records lâu hơn.
- Privacy policies có thể đòi xóa/ẩn danh dữ liệu cá nhân.

### 24.1. Envers không tự áp TTL theo entity

Một entity có `@Audited` không tự được dọn sạch audit rows sau 365 ngày. Retention là quyết định vận hành/application riêng.

### 24.2. Không DELETE audit rows tùy tiện

Ví dụ nguy hiểm:

~~~sql
DELETE FROM purchase_orders_AUD
WHERE REV < :cutoffRevision;
~~~

Với default strategy, có thể xóa **bản audit cuối cùng trước cutoff** của một entity vẫn còn tồn tại, khiến query as-of sau cutoff không biết baseline.

Với validity strategy, xóa rows dựa vào REV mà không xét `REVEND` và các relation cũng có thể phá tính đúng đắn.

### 24.3. Cần policy baseline

Khi thu ngắn lịch sử, phải xác định:

- Có cho phép as-of queries trước cutoff không?
- Có giữ một baseline snapshot tại cutoff cho mỗi entity không?
- Các entities đã xóa trước cutoff được xử lý thế nào?
- Các relationships và reference history còn phù hợp không?
- Có cần chỉnh range boundaries hoặc revision mapping không?
- AuditReader sẽ trả gì khi người dùng yêu cầu revision bị purge?

Retention có thể cần **tái tạo snapshot mốc** hoặc thiết kế archive, không chỉ xóa row cũ.

### 24.4. REVINFO chứa revisions dùng chung

Một revision có thể được tham chiếu bởi nhiều audit tables. Xóa `REVINFO` rows vì một audit table đã purge có thể phá các FK/history của entity khác.

Phải tính reference graph của revision metadata, retention khác nhau giữa entities và delete order.

## 25. Xóa entity và store_data_at_delete

Theo cấu hình thường gặp, một audit row loại DEL lưu ID và revision type, trong khi nhiều audited field values của deletion row là NULL. Vì snapshot trước deletion thường đã có dữ liệu, có thể suy trạng thái trước xóa từ revision liền trước.

Envers có property:

~~~properties
org.hibernate.envers.store_data_at_delete=true
~~~

để lưu thêm entity data trong deletion revision theo khả năng/version tương ứng.

### 25.1. Ưu điểm

Khi xem một deletion event, audit row xóa có thể chứa dữ liệu ngay tại thời điểm xóa mà không cần truy lại row trước đó để trình bày chi tiết.

### 25.2. Chi phí

- Lặp lại dữ liệu đã có ở revision trước.
- Tăng kích thước deletion audit rows.
- Có thể tăng thời gian ghi/backup.
- Có thể ảnh hưởng dữ liệu nhạy cảm cần retention/xóa.

Nếu deletes hiếm, chi phí có thể nhỏ. Nếu hệ thống tạo/xóa dữ liệu rất nhiều, cần cân nhắc.

### 25.3. Delete không đồng nghĩa purge audit

Xóa entity ở bảng chính không tự xóa lịch sử Envers. Nếu cần quyền xóa dữ liệu cá nhân, phải có quy trình riêng cho audit history, ràng buộc retention/legal hold và kiểm tra tất cả copies/backups.

## 26. @NotAudited và privacy

Audit history có thể chứa những phiên bản cũ của:

- Email, số điện thoại, địa chỉ.
- Thông tin thanh toán.
- Token/secret (không nên lưu).
- Nội dung do người dùng tạo.
- PII đã được sửa hoặc xóa ở bảng chính.

Nếu bật `@Audited` cho entity chứa dữ liệu nhạy cảm, các giá trị cũ có thể tồn tại lâu trong bảng audit.

### 26.1. Không audit secrets

Không lưu mật khẩu, API tokens, session secrets, encryption keys hoặc dữ liệu bí mật trong audit table chỉ vì entity chứa chúng. Chọn `@NotAudited` hoặc tách storage/masking phù hợp.

### 26.2. Mã hóa không thay retention

Encrypted audit row vẫn có thể là dữ liệu thuộc privacy policy. Cần quản trị khóa, quyền truy cập, retention và quy trình deletion/erasure có chủ đích.

### 26.3. Envers không tự là tamper-proof audit log

Audit tables là database tables. User có đủ quyền SQL có thể UPDATE/DELETE rows nếu không có kiểm soát. `@Audited` không tự cung cấp cryptographic integrity chain, WORM storage hay legal evidence bảo đảm chống sửa.

Nếu cần non-repudiation/compliance, cân nhắc append-only storage, DB privileges, signed logs, external archival và monitoring độc lập.

## 27. Bulk HQL, native SQL và những thay đổi không được Envers ghi lại

Một rủi ro nghiêm trọng đối với mọi chiến lược:

~~~java
int affected = em.createQuery("""
    update PurchaseOrder o
       set o.status = :newStatus
     where o.status = :oldStatus
    """)
    .setParameter("newStatus", OrderStatus.COMPLETED)
    .setParameter("oldStatus", OrderStatus.PAID)
    .executeUpdate();
~~~

Bulk HQL/JPQL DML không vận hành như dirty checking trên từng managed entity, nên **không mặc định tạo audit revisions cho mỗi entity theo Envers lifecycle path**.

Tương tự:

~~~sql
UPDATE purchase_orders
SET status = 'COMPLETED'
WHERE status = 'PAID';
~~~

khi chạy bằng JDBC/native SQL/script ngoài ORM không tự được Envers audit.

### 27.1. Hệ quả với tính đúng đắn lịch sử

Giả sử Order ở revision 27 có `status=PAID`. Một native UPDATE đổi sang COMPLETED mà Envers không ghi. Sau đó AuditReader as-of có thể vẫn thấy PAID trong lịch sử dù bảng chính đã là COMPLETED.

Không phải do Default/Validity query sai; **đường ghi không được audit**.

### 27.2. Các cách xử lý

- Với thay đổi cần Envers audit, dùng managed entity updates trong transaction phù hợp.
- Nếu bulk DML bắt buộc, thiết kế audit strategy riêng ở DB/application level và kiểm thử.
- Nếu nhiều writers ngoài ORM, cân nhắc DB triggers/CDC hoặc một audit service thống nhất.
- Nếu lịch sử phải đầy đủ tuyệt đối, không tuyên bố Envers là single source of truth khi có non-ORM writers.

### 27.3. Không tự INSERT vào *_AUD tùy tiện

Tự ghi vào audit table để “bù history” có thể phải tạo revision entity, xử lý revision order, REVTYPE, associations, validity REVEND update và các constraints. Không làm bằng một raw INSERT không được thiết kế; dễ phá invariants của Envers.

Nếu phải nhập lịch sử legacy, cần migration đặc biệt có invariant checks và backup/rollback plan.

## 28. Default vs Validity khi dữ liệu được xóa và tạo lại

Nếu entity bị xóa rồi một entity khác được tạo với cùng identifier (ví dụ ID tái sử dụng trong legacy system), audit history có thể có nhiều chu kỳ ADD/DEL cho một ID.

Hai chiến lược phải xử lý:

- ADD/DEL đúng revisions.
- Snapshot null sau delete.
- ADD mới sau đó.
- End intervals không chồng nhau.
- Query theo ID và revision không trộn sai các chu kỳ.

**Không khuyến khích tái sử dụng primary key** nếu có thể tránh, nhất là trong hệ thống cần lịch sử rõ ràng. Khi migration từ hệ thống cũ, phải kiểm tra đặc thù ID reuse và Envers data model.

## 29. Tối ưu query lịch sử: đọc đúng thứ cần thiết

Các kiểu query:

1. **Timeline theo ID:** liệt kê revision và actor của một entity.
2. **Snapshot theo ID + revision:** lấy trạng thái tại R.
3. **Diff hai revisions:** xem property changes.
4. **As-of query nhiều entities:** lọc trạng thái lịch sử của một tập.
5. **Audit activity feed:** xem thay đổi gần đây theo actor/time.
6. **Báo cáo tuân thủ:** truy xuất nhiều năm với aggregate/cross-entity relations.

Chiến lược tối ưu khác nhau cho từng kiểu.

### 29.1. Với timeline: đọc revision metadata trước

Thay vì hydrate 100 revisions full entity/collections, truy vấn revisions rồi chỉ tải snapshot khi user mở. Điều này giảm data transfer và heap pressure.

### 29.2. Với diff: modified flag hay so snapshot?

- Ít diff requests: so hai snapshots có thể đủ.
- Rất nhiều requests lọc theo changed property: modified flags có thể đáng giá.
- Delta compression thực sự: cân nhắc audit/event storage chuyên biệt nếu Envers row snapshots quá tốn.

### 29.3. Với as-of report lớn: materialize

Nếu thường xuyên cần “trạng thái mọi hợp đồng cuối tháng”, có thể tạo monthly snapshots/materialized views riêng từ hệ thống nguồn đúng, thay vì chạy cùng một as-of query trên hàng trăm triệu audit rows mỗi lần.

Cần kiểm soát correctness, refresh policy và khả năng truy vết snapshot source revision.

### 29.4. Không fetch toàn graph khi không cần

Một audited entity có quan hệ sâu; việc deserialize toàn graph có thể phát sinh nhiều SQL hoặc chi phí hydrate lớn. Trả DTO projection hoặc giới hạn fields và dùng query path phù hợp. API historical query phải có pagination, timeout/limits và authorization.

## 30. Tối ưu read bằng EXPLAIN

Ví dụ PostgreSQL minh họa default strategy:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT a.*
FROM purchase_orders_AUD a
WHERE a.id = 9001
  AND a.REV = (
      SELECT MAX(x.REV)
      FROM purchase_orders_AUD x
      WHERE x.id = a.id
        AND x.REV <= 50000
  )
  AND a.REVTYPE <> 2;
~~~

Validity:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT a.*
FROM purchase_orders_AUD a
WHERE a.id = 9001
  AND a.REV <= 50000
  AND (a.REVEND > 50000 OR a.REVEND IS NULL)
  AND a.REVTYPE <> 2;
~~~

Đây là queries minh họa semantics, không thay thế SQL thực tế do Envers sinh. Kiểm tra:

- Index scan hoặc sequential scan?
- Rows examined vs rows returned?
- Nested loops/subplan executions?
- Buffers shared hit/read?
- Sort/hash aggregate?
- Latency P95 trên queries đại diện?
- Có khác biệt đáng kể khi revision cũ/mới?
- Query có xử lý tenant/authorization scope đầy đủ không?

### 30.1. EXPLAIN trên dữ liệu đại diện

Benchmark một entity có 4 revisions không phản ánh một entity có 20.000 revisions. Tương tự, hệ thống có 1 triệu entities mỗi entity 2 revisions khác hệ thống có 10.000 entities mỗi entity 200 revisions.

Nên có các test populations:

- Long-tail ít thay đổi.
- Hot entities rất nhiều revisions.
- Tập dữ liệu đã bị xóa.
- Relations nhiều changes.
- Queries trả một row và queries trả hàng loạt.

### 30.2. SQL đẹp không luôn nhanh

Validity predicate có vẻ đơn giản hơn, nhưng nếu database không chọn index phù hợp, có thể vẫn scan lớn. Ngược lại, correlated max query có thể được tối ưu tốt nhờ index. **Lấy kết quả đo làm quyết định.**

## 31. Migration từ Default sang Validity

Một dự án ban đầu dùng default vì muốn ghi nhanh, sau vài năm lịch sử lớn và as-of reports chậm. Việc chuyển sang validity cần kế hoạch.

### 31.1. Phân tích trước migration

- Tổng audit tables và row counts.
- Những entities có composite ID.
- Có deletion/recreate với cùng ID không.
- Có audit join tables/relations không.
- Revision table chứa metadata gì.
- DB có đủ disk/transaction log cho backfill không.
- Có thể dừng writers hoặc chạy migration theo batches nhất quán không.
- Ràng buộc downtime và dual-write/backfill.
- Kết quả as-of hiện tại có baseline đủ không.

### 31.2. Backfill REVEND theo revision kế tiếp

Ý tưởng quan hệ:

~~~sql
WITH next_versions AS (
    SELECT
        id,
        REV,
        LEAD(REV) OVER (
            PARTITION BY id
            ORDER BY REV
        ) AS next_rev
    FROM purchase_orders_AUD
)
UPDATE purchase_orders_AUD a
SET REVEND = n.next_rev
FROM next_versions n
WHERE a.id = n.id
  AND a.REV = n.REV;
~~~

Đây là **SQL PostgreSQL minh họa thuật toán**, không phải migration được phép chạy thẳng trên production. Có thể cần syntax khác, batching, constraints, table locks, logical IDs nhiều cột, correct delete semantics và xử lý không có next revision.

Nếu bật `REVEND_TSTMP`, phải join revision table để tìm timestamp tương ứng với `next_rev`, cùng precision/type mapping đúng.

### 31.3. Chạy thử trên bản sao DB

- Backup trước.
- Migrate trên clone production-like.
- Compare AuditReader.find() cho một bộ IDs/revisions đủ lớn.
- Compare revision timelines/deletion semantics.
- Compare relation history.
- Run EXPLAIN và write load tests.
- Verify không có overlapping ranges hoặc gaps bất ngờ.
- Kiểm tra rollback migration strategy.

### 31.4. Không đổi strategy giữa nhiều application nodes tùy tiện

Trong rolling deployment, nếu một số nodes chạy default, một số chạy validity vào cùng audit schema, các nodes có thể ghi khác invariants. Cần kế hoạch cutover có coordination rõ ràng, tránh mixed writers không tương thích.

### 31.5. Có thể tách workload đọc thay vì đổi strategy

Nếu chỉ một loại báo cáo lịch sử cực nặng, đôi khi rẻ hơn khi xây materialized snapshot/reporting store, giữ default audit để giảm rủi ro migration toàn bộ audit tables.

## 32. Migration từ Validity về Default

Đổi ngược cũng không chỉ là gỡ columns. Nếu ứng dụng đã dùng validity, các reporting tools, retention partitions hoặc indexes có thể phụ thuộc `REVEND`/`REVEND_TSTMP`.

Trước khi chuyển về default:

- Xác minh AuditReader query semantics với dữ liệu cũ.
- Đánh giá hiệu năng as-of queries không có end-range.
- Xác định retention/backfill history đã purge.
- Giữ historical columns trong giai đoạn tương thích nếu cần.
- Đặt lịch schema cleanup có rollback.

Trong thực tế, đôi khi retention và storage management sẽ có tác động lớn hơn việc đổi audit strategy sau nhiều năm dữ liệu tích lũy.

## 33. Envers so với các mô hình lưu lịch sử khác

Để chọn đúng chiến lược, cần phân biệt vài kiến trúc:

| Mô hình | Cách lưu | Ưu điểm | Chi phí/giới hạn |
| --- | --- | --- | --- |
| Envers Default | Snapshot audited state tại REV | Ghi thường đơn giản hơn, ORM-integrated | As-of queries có thể cần max-rev subqueries |
| Envers Validity | Snapshot + end revision | Range-as-of queries thuận lợi | Extra UPDATE, end metadata, index overhead |
| Application diff log | Chỉ lưu những thay đổi | Dung lượng thay đổi có thể nhỏ | Reconstruct state cần replay/baseline, logic phức tạp |
| Periodic full snapshots | Snapshot theo ngày/tháng | Báo cáo mốc định kỳ nhanh | Không đủ mọi revision, storage thêm |
| Event sourcing | Business events append-only | Lưu nguyên nhân/nguồn hành vi, replay business events | Thiết kế domain và event evolution phức tạp |
| DB temporal/system-versioned tables | DB tự quản lý history theo tính năng riêng | Bao phủ nhiều SQL writes tùy DB | Vendor dependence, semantics/retention khác |
| CDC log | Capture DB changes từ log | Phù hợp streaming, analytics | Không tự có actor/domain meaning, retention/outcome khác |
| Audit trigger | Trigger ghi before/after | Có thể bao phủ SQL writers | DB code, maintenance, auditing consistency phức tạp |

### 33.1. Envers không phải event sourcing

Envers audit snapshot entity state. Event sourcing lưu domain events như `PaymentCaptured`, `OrderShipped`. Một thay đổi state có thể xuất phát từ nhiều nguyên nhân nghiệp vụ và Envers không tự ghi nguyên nhân đó.

### 33.2. Envers không tự là bitemporal database

Bitemporal data thường phân biệt:

- **Transaction time:** lúc hệ thống ghi nhận phiên bản.
- **Valid time:** khoảng thời gian dữ liệu có hiệu lực theo nghiệp vụ, có thể khác thời điểm hệ thống ghi.

Envers revision history chủ yếu theo những mốc thay đổi được audit trong ORM. `REVEND` của validity là **kết thúc theo revision**, không tự là business valid-time end.

Nếu nghiệp vụ cần backdated contracts hoặc hiệu lực pháp lý trong quá khứ/tương lai, phải mô hình hóa `validFrom`/`validTo` hoặc temporal tables riêng với semantics rõ.

### 33.3. Kết hợp nhiều mô hình có thể hợp lý

Ví dụ:

- Envers lưu lịch sử nghiệp vụ đơn hàng.
- Outbox phát domain events.
- Warehouse lưu daily revenue snapshots.
- CDC đưa dữ liệu từ DB sang analytics.
- DB trigger quản lý timestamp cho writers ngoài ORM.

Nhưng mỗi lớp cần ownership, retention và consistency contract; không giữ 5 bản sao history vô hạn mà không có lý do.

## 34. Multi-tenant audit và quyền truy cập

Một hệ thống nhiều tenant có thể lưu audit rows chung. Lịch sử thường chứa dữ liệu nhạy cảm hơn bảng hiện tại vì giữ giá trị cũ.

### 34.1. Không dựa vào việc entity live đã được filter

Một API nhận:

~~~http
GET /orders/9001/history
~~~

không được gọi `AuditReader.find()` rồi trả kết quả chỉ vì người dùng biết ID. Cần kiểm tra quyền xem lịch sử của đúng tenant/subject.

### 34.2. Historical authorization và current authorization

Cần policy:

- Người dùng được phép xem order hiện tại thì có được xem mọi lịch sử của order không?
- Nếu order đã chuyển tenant hoặc ownership, dùng quyền tại thời điểm nào?
- Nếu record đã bị xóa, ai được phép truy xuất lịch sử?
- Support/admin có thể xem fields đã bị ẩn ở bảng live không?

Envers không tự quyết định câu trả lời nghiệp vụ. Đặt authorization ở service/reporting layer và kiểm thử mọi query paths.

### 34.3. Tenant trong revision metadata chưa đủ

Nếu revision entity có `tenantId` nhưng một transaction có thể sửa nhiều tenants (ví dụ background maintenance), một revision-level tenant field có thể không mô tả chính xác mọi audit rows. Cân nhắc tenant ở audited entity hoặc một per-change scope model phù hợp.

### 34.4. AuditReader và filters

Không giả định Hibernate filter/soft-delete/tenant restrictions của entity live được áp dụng y hệt cho mọi Envers audit query. Kiểm tra SQL thực tế và bổ sung authorization predicates/partitioning cần thiết.

## 35. Truy vấn lịch sử sau schema evolution

Entity Java thay đổi qua các phiên bản ứng dụng:

~~~text
v1: Order(id, status, amount)
v2: Order(id, status, amount, currency)
v3: Order(id, status, grossAmount, taxAmount, currency)
~~~

Bảng audit cũng phải được migration theo schema mapping.

### 35.1. Thêm audited field

Nếu thêm `currency` vào audited entity, audit rows cũ không có giá trị lịch sử thực sự cho field mới. Backfill có thể chỉ suy đoán, không tạo được history thật.

Cần chọn policy:

- NULL/unknown cho revisions cũ.
- Giá trị default được gắn nhãn inferred.
- Migration từ nguồn dữ liệu lịch sử đáng tin.
- Tạo reporting DTO biết revision schema version.

### 35.2. Đổi tên hoặc kiểu field

Đổi `amount` sang `grossAmount` không chỉ sửa Java; cần migration audit table, indexes, queries và history consumers. Nếu thay đổi semantics (gross khác net), không đơn giản rename rồi coi lịch sử luôn tương đương.

### 35.3. Thay đổi strategy trong lúc đổi schema càng rủi ro

Đừng gộp Default→Validity, thay đổi entity inheritance, thêm modified flags và migration partition vào một deploy thiếu tests. Tách migration có thể rollback và có checkpoints độc lập.

## 36. Sự nhất quán transaction của audit và entity

Với ghi entity qua Hibernate/Envers đúng cách, audit rows được ghi cùng transaction với thay đổi entity; nếu transaction rollback, audit insert/update cũng rollback.

Điều này giúp tránh có audit state “thành công” cho một entity write bị rollback, **nhưng không bảo đảm mọi business side effect bên ngoài DB đều atomic**.

### 36.1. Không gửi email trực tiếp trong Envers listener

Ngay cả khi revision row được tạo, transaction còn có thể rollback. Gửi email/webhook trước commit có thể tạo thông báo sai.

Nếu cần sự kiện sau commit đáng tin, dùng outbox cùng transaction hoặc cơ chế after-commit với hiểu biết về failure window.

### 36.2. Envers không tự audit mọi SQL writer

Nếu administrator trực tiếp UPDATE bảng live, Envers không có một ORM transaction event để ghi bản lịch sử tương ứng. Cần kiểm soát quyền ghi DB hoặc bổ sung database-level auditing.

### 36.3. Retry và duplicate effects

Khi transaction lỗi, caller retry thao tác trong transaction mới. Envers thường chỉ giữ committed audit changes của transactions thành công, nhưng các business events bên ngoài phải idempotent. Không coi sự tồn tại revision như chứng cứ external message chỉ được gửi một lần.

## 37. Revision timestamp và lịch sử theo ngày

Một chức năng:

> Cho xem trạng thái đơn hàng “lúc 00:00 ngày 1/11”.

Cần phân biệt:

- Mốc thời gian theo timezone nào?
- Revision timestamp đến từ clock nào?
- Envers đang ghi timestamp lúc bắt đầu revision hay tại commit?
- Có concurrency làm revision ordering lệch thứ tự wall-clock?
- Có data migration/backfill tạo revisions theo thứ tự khác business time?

### 37.1. Không dùng REV như một Unix timestamp

`REV = 50000` là số thứ tự revision, không phải thời gian epoch. Muốn lọc theo thời gian, dùng revision entity timestamp hoặc API time-to-revision phù hợp.

### 37.2. Business as-of khác transaction as-of

Nếu hợp đồng có hiệu lực từ ngày 1/1 nhưng được nhập hệ thống ngày 5/1, Envers ghi lúc nhập; business validFrom phải là field riêng.

Một báo cáo pháp lý cần đúng business effective dates có thể phải kết hợp Envers transaction history với temporal business model.

## 38. Phân trang lịch sử lớn

Một endpoint trả mọi revisions của entity trong một lần có thể gây:

- Heap pressure.
- N+1 khi truy vấn relations.
- Response JSON lớn.
- Query latency cao.
- Khó giới hạn tenant/authorization.
- Timeout và connection pool contention.

### 38.1. Phân trang theo revision

Với revision timeline một entity:

~~~sql
SELECT REV, REVTYPE
FROM purchase_orders_AUD
WHERE id = :id
  AND REV < :beforeRevision
ORDER BY REV DESC
LIMIT 50;
~~~

SQL minh họa PostgreSQL-style syntax. Nếu `REV` duy nhất trong timeline của entity, keyset pagination theo REV rất phù hợp để đọc revisions cũ mà không OFFSET sâu.

### 38.2. Tách metadata list và snapshot detail

Trả:

~~~json
{
  "items": [
    { "revision": 41, "type": "MOD", "actor": "user-17" },
    { "revision": 27, "type": "MOD", "actor": "batch-2026" }
  ],
  "nextBeforeRevision": 27
}
~~~

Chỉ khi client chọn revision 27 mới gọi `AuditReader.find()` để tải snapshot chi tiết. Cách này giúp giảm chi phí nạp dữ liệu.

### 38.3. Search theo field đã đổi

Nếu product yêu cầu “chỉ xem những revision đổi giá”, modified flags có thể hỗ trợ tốt hơn so hai snapshot cho mọi revision. Nhưng chỉ bật flags cho những field cần query; test query result/index/storage.

## 39. Vận hành backup, replication và disaster recovery

Bảng audit thường lớn hơn bảng live sau vài năm. Các quyết định:

- Backup full hay incremental?
- Có restore cả REVINFO và *_AUD đồng bộ không?
- Audit tables có cùng replication policy với live tables không?
- Có legal hold/retention khác live data không?
- Rebuild indexes mất bao lâu?
- Có thể khôi phục về thời điểm đủ gần không?

### 39.1. Không restore audit và live ở hai mốc không tương thích

Nếu restore bảng live tại thời điểm T nhưng audit tại T+2 giờ, AuditReader có thể hiển thị những revisions không có trạng thái live tương ứng, hoặc thiếu lịch sử một giai đoạn. Cần disaster-recovery plan cho **tập schema liên quan**.

### 39.2. Validity write amplification ảnh hưởng replica

Thêm UPDATE previous audit row làm tăng WAL/redo và replication traffic. Với DB có replicas nhiều hoặc workload ghi lớn, đây là thành phần chi phí cần đo.

### 39.3. Backup size cũng là storage cost

Không chỉ dung lượng đĩa chính: audit indexes, full/incremental backups, offsite copies, restore time và cold storage đều có thể quyết định total cost of ownership.

## 40. Ma trận quyết định chọn chiến lược

| Hoàn cảnh | Lựa chọn thường nên đánh giá trước | Vì sao |
| --- | --- | --- |
| Audit viết nhiều, hiếm khi đọc as-of | Default | Giảm work cập nhật previous audit row |
| Lịch sử chủ yếu theo một ID | Default hoặc Validity | Index ID+REV có thể đủ; benchmark |
| Thường xuyên truy vấn as-of hàng loạt entities | Validity | Range predicates có thể giảm subquery cost |
| Cần partition retention dựa trên end-of-validity | Validity + REVEND_TSTMP | Có metadata end time; cần thiết kế partition thật |
| Bảng có hot entities cập nhật liên tục | Benchmark đặc biệt | Validity thêm UPDATE/row locks/WAL |
| Có nhiều audited LOB fields | Giảm phạm vi audit/tách data | Strategy không loại bỏ full snapshot overhead |
| Cần query “field nào đổi?” nhiều | Modified flags có chọn lọc | Giảm so snapshot lúc đọc, tăng row width |
| Cần legal immutable logs | Không chỉ Envers | Bảo vệ tamper/retention/provenance |
| Nhiều SQL writers ngoài Hibernate | DB-level audit/CDC hoặc policy thống nhất | Envers không tự thấy direct SQL |
| Báo cáo lịch sử nhiều năm, dữ liệu rất lớn | Reporting snapshots/warehouse | AuditReader online có thể quá tốn |
| Hệ thống sắp đổi ORM/DB | Cân nhắc portability | Envers/validity là extension Hibernate |
| Đã có history theo Default nhiều năm | Migration có kiểm thử hoặc reporting path riêng | Đổi config không tự backfill REVEND |

**Quyết định cuối phải dựa trên read/write mix, dữ liệu đại diện, chính sách giữ lịch sử và capability DB**, không chỉ số cột audit.

## 41. Checklist thiết kế Envers cho production

- [ ] Xác định entity nào và field nào thật sự cần audit.
- [ ] Phân biệt lịch sử trạng thái với domain events/business valid time.
- [ ] Chọn Default hoặc Validity theo workload đo được.
- [ ] Hiểu `REV` và `REVEND` là revision numbers, không phải commit timestamps.
- [ ] Nếu dùng Validity, hiểu extra UPDATE trước audit row và chi phí WAL/index.
- [ ] Nếu bật `REVEND_TSTMP`, thiết kế retention/partition dựa trên khả năng DB.
- [ ] Không nghĩ modified flags biến snapshots thành delta log.
- [ ] Đánh giá chi phí LOB, collections, link tables và hot entities.
- [ ] Không audit secrets hoặc fields nhạy cảm không cần thiết.
- [ ] Query theo ID/revision có indexes phù hợp.
- [ ] Benchmark cả as-of single ID lẫn as-of nhiều entities.
- [ ] Đo write latency, WAL/redo và table/index size.
- [ ] Có pagination cho revision timelines.
- [ ] Có chính sách actor/source/correlation trong revision metadata.
- [ ] Đảm bảo tenant/authorization cho AuditReader APIs.
- [ ] Kiểm thử bulk HQL/native SQL writers vì chúng có thể bỏ qua Envers.
- [ ] Kiểm thử creation, update, delete, rollback và associations.
- [ ] Không delete audit rows cũ mà bỏ qua baseline/end interval.
- [ ] Có retention, archive, legal hold và privacy policy.
- [ ] Có kế hoạch migration schema/strategy, backfill và rollback.
- [ ] Backup/restore REVINFO và audit tables nhất quán.
- [ ] Nếu yêu cầu anti-tamper, triển khai bảo vệ độc lập.
- [ ] Giới hạn quyền truy cập dữ liệu lịch sử chặt hơn hoặc bằng dữ liệu live.

## 42. Bài tập thực hành

### Bài 1 — Revision snapshot

Order có revisions 12 (ADD, DRAFT), 19 (MOD, PAID), 27 (MOD, PAID amount=120), 41 (MOD, COMPLETED), 58 (DEL). Trạng thái ở revision 35 là gì? Ở revision 59 còn tồn tại không?

### Bài 2 — Default query

Viết SQL minh họa dùng `MAX(REV) <= :targetRevision` để lấy phiên bản của một entity tại revision R. Vì sao `REVTYPE` cần được xét?

### Bài 3 — Validity intervals

Với rows `(REV=12,REVEND=19)`, `(19,27)`, `(27,41)`, `(41,58)`, row nào có hiệu lực tại R=27? Tại R=41?

### Bài 4 — Chi phí Validity ghi

Khi update một entity từ revision 27 sang 41, Default và Validity cần những audit SQL operations nào? Vì sao Validity có thể tốn WAL và lock hơn?

### Bài 5 — Nguồn REVEND_TSTMP

`REVEND` và `REVEND_TSTMP` khác nhau ra sao? Vì sao timestamp này hữu ích cho retention/partitioning nhưng không đồng nghĩa commit timestamp?

### Bài 6 — Modified flags

Một entity có 40 audited fields, bật modified flag cho tất cả. Audit rows có trở thành delta logs chỉ chứa field changed không? Phân tích storage vs query trade-off.

### Bài 7 — Sizing

Một hệ thống có 10 triệu entities, trung bình mỗi entity thêm 8 revisions, audit row trung bình 400 bytes. Ước lượng số rows và dữ liệu thô, chưa tính indexes. Những phần chi phí nào bạn còn thiếu?

### Bài 8 — Hot counter

Một `Product.viewCount` đổi 50.000 lần/ngày nhưng không cần truy vết từng lần. Nên làm gì để giảm audit churn? Việc dùng Validity có tự giải quyết không?

### Bài 9 — As-of nhiều entities

Báo cáo cần lấy trạng thái mọi Orders tại revision 100.000. Vì sao Default có thể đắt hơn? Khi nào Validity vẫn chưa đủ?

### Bài 10 — Index

Đề xuất index cho truy vấn revision timeline theo `id` và `REV`. Với Validity, nên kiểm tra các index ứng viên nào cho predicate `REV <= R AND (REVEND > R OR REVEND IS NULL)`?

### Bài 11 — Relations

Order có 200 OrderLines và nhiều lần thêm/xóa line. Vì sao không thể ước tính audit storage chỉ theo số Order updates? Cần đo những audit tables nào?

### Bài 12 — Not-audited target

Một audited Order trỏ tới non-audited Currency lookup. Nếu Currency.name thay đổi sau một năm, historical Order có thể hiện tên currency nào? Vì sao cần cân nhắc tính bất biến lookup?

### Bài 13 — Bulk HQL

Một job dùng HQL UPDATE đổi trạng thái 1 triệu Orders. Envers có tự tạo revisions cho từng entity không? Cách thiết kế audit nếu bắt buộc có lịch sử?

### Bài 14 — Cleanup

Bảng audit có row của Order bắt đầu năm 2020 và không đổi đến 2026. Vì sao xóa mọi row có REV timestamp trước 2023 có thể phá as-of query năm 2025?

### Bài 15 — Migrate Default→Validity

Liệt kê các bước chuyển strategy cho database 100 triệu audit rows. `LEAD(REV) OVER (PARTITION BY id ORDER BY REV)` giúp backfill thông tin gì?

### Bài 16 — Revision actor

Một transaction sửa 50 entities cho một job. Revision entity lưu actor/jobId có lợi gì? Nếu cùng transaction thay đổi entities của nhiều tenants, revision-level tenantId có thể sai như thế nào?

### Bài 17 — Query timeline lớn

Một entity có 500.000 revisions. Thiết kế endpoint lịch sử phân trang thay vì trả tất cả snapshots. Tại sao keyset theo REV thích hợp?

### Bài 18 — Snapshot vs delta

Khi nào diff log có thể tiết kiệm dung lượng hơn snapshot Envers? Đánh đổi nào xuất hiện khi cần dựng state tại một revision cũ?

### Bài 19 — Privacy

Một audited Customer có phone, address và password hash. Những fields nào có nên được audit không? Envers có tự ngăn DBA sửa bảng *_AUD hay tự thực hiện right-to-erasure không?

### Bài 20 — Business valid time

Một hợp đồng có hiệu lực từ ngày 1/1 nhưng chỉ được nhập vào DB ngày 10/1. REV/REVEND có đủ mô hình hóa hợp đồng có hiệu lực từ 1/1 không? Cần field/model nào khác?

### Bài 21 — Benchmark

Thiết kế benchmark so Default và Validity với: 1 ID có 1.000 revisions, 1 triệu IDs có 3 revisions, 50 concurrent writers và as-of list query. Cần đo latency, buffer reads, WAL và lock waits thế nào?

### Bài 22 — Outbox và Envers

Envers đã audit Order.status=PAID. Điều đó có bảo đảm email “đã thanh toán” chỉ được gửi đúng một lần không? Nếu không, cần cơ chế gì?

### Bài 23 — Schema migration

Thêm field `taxAmount` vào audited Order ở version mới. Những audit revisions cũ có taxAmount chính xác không? Nếu business cần báo cáo tax theo lịch sử, xử lý như thế nào?

### Bài 24 — Chọn strategy cho dự án

Một hệ thống có 200.000 writes/giờ và chỉ 10 yêu cầu đọc lịch sử theo ID/ngày. Một hệ thống khác có 5.000 writes/giờ và 20.000 as-of reports/ngày. Chọn strategy khởi điểm cho mỗi hệ thống và chỉ rõ điều kiện benchmark có thể làm bạn đổi quyết định.

### Gợi ý đáp án

- **Bài 1:** Revision 27; sau DEL ở 58, state sau đó không còn tồn tại.
- **Bài 2:** Chọn MAX REV không vượt R, loại DEL nếu phiên bản cuối là xóa.
- **Bài 3:** R=27 khớp khoảng `[27,41)`; R=41 khớp `[41,58)`.
- **Bài 4:** Default thêm audit row; Validity thêm row và đóng REVEND của row trước.
- **Bài 5:** REVEND là revision number; REVEND_TSTMP là timestamp gắn end revision, không tự là commit time.
- **Bài 6:** Không; snapshots vẫn lưu audited fields, flags thêm columns.
- **Bài 7:** Khoảng 90 triệu rows nếu “8 revisions thêm” sau creation; ~36 GB raw, chưa kể indexes/WAL/relations/backups.
- **Bài 8:** @NotAudited hoặc tách counters; Validity không giảm số snapshots, còn thêm update overhead.
- **Bài 9:** Default tìm latest REV theo từng entity; Validity dùng range, nhưng query nhiều dữ liệu vẫn đắt.
- **Bài 10:** `(id, REV DESC)`, với Validity xem index có `REVEND` và EXPLAIN.
- **Bài 11:** Child/link audit tables, collection change revisions và relations.
- **Bài 12:** Có thể hiện current target values tùy relation audit mode; cần lookup bất biến hoặc audited target.
- **Bài 13:** Bulk DML thường bypass Envers; cần ORM-managed updates hoặc audit path riêng.
- **Bài 14:** Row cũ có thể là baseline còn cần cho các revision mới hơn.
- **Bài 15:** Migration schema, LEAD để tìm next rev, backfill REVEND/timestamp, consistency tests/cutover.
- **Bài 16:** Revision-level actor tiện cho một transaction; tenant field không thể đại diện nhiều tenant thay đổi cùng revision.
- **Bài 17:** Trang timeline theo REV DESC với cursor beforeRevision; chỉ load snapshot detail theo yêu cầu.
- **Bài 18:** Delta nhỏ khi ít field đổi; dựng state cũ phải replay/checkpoint và query phức tạp.
- **Bài 19:** Tránh audit secrets; PII retention cần policy; Envers không tamper-proof.
- **Bài 20:** Không; cần business validFrom/validTo hoặc bitemporal model.
- **Bài 21:** So cùng dataset/DB indexes và đo write/read/IO/WAL/locks, không chỉ API duration.
- **Bài 22:** Không; cần outbox/idempotent delivery.
- **Bài 23:** Không tự có lịch sử thật; cần source backfill đáng tin hoặc đánh dấu unknown.
- **Bài 24:** Hệ ghi dày/ít đọc khởi điểm Default; hệ read-heavy as-of thử Validity, nhưng benchmark quyết định.

---

## Tổng kết

**Envers lưu lịch sử entity qua các revision, nhưng cách xác định phiên bản có hiệu lực ảnh hưởng lớn đến chi phí ghi, truy vấn và dung lượng.**

- **DefaultAuditStrategy** thường chỉ thêm audit row tại mỗi revision và tìm phiên bản lịch sử bằng revision mới nhất không vượt mốc truy vấn. Nó thường thuận lợi cho write-heavy workloads hoặc timeline theo ID với index phù hợp.
- **ValidityAuditStrategy** lưu thêm `REVEND` (và có thể `REVEND_TSTMP`), biểu diễn khoảng hiệu lực theo revision để một số as-of queries dễ tối ưu hơn. Đổi lại, mỗi phiên bản mới thường cần đóng audit row trước, làm tăng write amplification và vận hành indexes.
- **Modified flags** giúp biết trường nào đổi nhưng không biến audit snapshots thành delta log. **@NotAudited** và cấu trúc entity/relations quyết định tốc độ tăng trưởng history.
- **Index, partition và retention** quan trọng như chiến lược audit. Purge thiếu baseline hoặc migration REVEND thiếu kiểm soát có thể phá khả năng tái tạo trạng thái lịch sử.
- **Envers không tự bắt mọi bulk/native SQL, không tự đảm bảo chống sửa, không tự lưu business valid time và không thay thế event sourcing/outbox.** Cần kiểm thử các đường ghi và phân quyền lịch sử chặt chẽ.

Quy tắc lựa chọn: **đo đồng thời throughput ghi, latency truy vấn as-of, dung lượng/IO và chi phí vận hành trên dữ liệu đại diện; sau đó chọn chiến lược phù hợp với yêu cầu lưu giữ lịch sử thực tế, thay vì giả định một strategy luôn tốt hơn strategy kia.**
