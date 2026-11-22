# Phân biệt gom thao tác ghi của provider và bảo đảm của chuẩn JPA

Khi cần nhập hàng nghìn bản ghi bằng Jakarta Persistence (JPA), lập trình viên thường hỏi: “Nếu gọi `persist()` 1.000 lần thì ORM có gửi 1.000 câu `INSERT` hay tự gom chúng thành một batch?”. Câu trả lời không thể suy ra chỉ từ tên API JPA.

**JPA định nghĩa cách quản lý entity, persistence context, đồng bộ thay đổi và tham gia giao dịch; JPA không bắt buộc một provider phải gom các thao tác ghi thành JDBC batch, cũng không cam kết số round trip đến database.**

Ví dụ:

```java
em.getTransaction().begin();

for (int i = 0; i < 1_000; i++) {
    em.persist(new SensorReading("sensor-A", i));
}

em.getTransaction().commit();
```

Code trên biểu đạt ý định tạo 1.000 entities trong một transaction. Nó **không tự chứng minh** rằng provider sẽ gửi 1.000 separate network round trips, 20 batches, một multi-row `INSERT`, hay một hình thức ghi cụ thể khác.

Ngược lại, bật một property như:

```properties
hibernate.jdbc.batch_size=50
```

là yêu cầu tối ưu hóa cho **Hibernate**, không phải một tùy chọn bắt buộc của đặc tả Jakarta Persistence. Hiệu quả thực tế còn phụ thuộc chiến lược sinh khóa, SQL shape, ordering, JDBC driver, dialect, transaction và database.

Bài này thuộc chủ đề **Data Persistence Relational Access ORM JPA**, chương **Hiệu năng**, với đề bài trực tiếp **“Phân biệt gom thao tác ghi của provider và bảo đảm của chuẩn JPA”**.

Sau bài học, bạn có thể:

- Phân biệt `persist`, dirty checking, `flush`, `commit`, một JDBC batch và một transaction.
- Nêu chính xác đâu là bảo đảm thuộc JPA, đâu là tối ưu triển khai của provider.
- Hiểu vì sao `hibernate.jdbc.batch_size`, `order_inserts`, `order_updates` có thể cải thiện hoặc không cải thiện workload.
- Phân biệt `IDENTITY`, `SEQUENCE`, khóa tự cấp và ảnh hưởng lên khả năng gom `INSERT`.
- Thiết kế vòng lặp `flush`/`clear` phù hợp về memory và transaction semantics.
- Nhận biết các trở ngại: quan hệ khóa ngoại, nhiều SQL shapes, optimistic locking, cascade, dynamic insert/update và native bulk DML.
- Đo đúng JDBC batch executions, prepared statements, SQL rows và transaction outcomes.
- Kiểm thử **tính đúng đắn** tách biệt với kiểm thử **hiệu năng đặc thù provider**.
- Tránh kết luận sai từ số câu SQL log hoặc annotation như `@BatchSize`.

**Thông điệp trung tâm:** *Một transaction, một lần `flush`, một lời gọi `saveAll` và một JDBC batch là bốn khái niệm khác nhau. Hành vi ghi đúng được JPA và database giao dịch ràng buộc; cách gom SQL là quyết định tối ưu của provider/driver, phải cấu hình và đo.*

---

## 1. Năm tầng của một thao tác ghi

Một thao tác ghi trong ứng dụng JPA thường đi qua các tầng:

```text
Application code
    |
    | persist / setter / remove / saveAll
    v
Persistence context
    |
    | managed entities, dirty checking,
    | action queue, pending mutations
    v
Flush / SQL generation
    |
    | INSERT / UPDATE / DELETE
    v
JDBC
    |
    | prepareStatement / addBatch / executeBatch
    | hoặc executeUpdate riêng lẻ
    v
Database transaction
    |
    | constraints, locks, commit / rollback
    v
Committed data
```

Không phải mọi bước ở tầng trên tương ứng một bước duy nhất ở tầng dưới.

### 1.1. `persist()` là thao tác JPA, không phải lời hứa một `INSERT` tức thì

```java
em.persist(entity);
```

Khi thành công theo semantics JPA, lời gọi đưa entity mới vào trạng thái managed và khiến entity đủ điều kiện được ghi trong đơn vị công việc.

Tuy nhiên, provider có thể:

- Trì hoãn SQL INSERT đến flush.
- Gửi INSERT sớm vì cần generated ID hoặc ràng buộc triển khai khác.
- Tạo thêm câu SQL cho sequence/identifier generation.
- Sắp xếp pending inserts để đáp ứng khóa ngoại.
- Gom SQL thành batches khi điều kiện cho phép.

Không dự đoán số SQL chỉ từ số lần `persist()`.

### 1.2. Dirty checking không đồng nghĩa một UPDATE cho mọi setter

```java
order.setStatus(OrderStatus.CONFIRMED);
order.setNote("Checked");
```

Nhiều setters trên **cùng managed entity** có thể được tổng hợp thành một SQL `UPDATE` khi flush.

Nếu giá trị cuối không khác snapshot theo cơ chế dirty checking, provider có thể không phát `UPDATE`.

Điều này khác với **JDBC batching**: dirty checking giảm số operations cần ghi, còn batching gom nhiều SQL operations đã được tạo ra để thực thi hiệu quả hơn.

### 1.3. `flush()` đồng bộ persistence context, không commit

```java
em.flush();
```

Flush đồng bộ pending changes xuống database theo transaction context.

Nó **không** bảo đảm:

- Dữ liệu đã commit.
- Chỉ có đúng một câu SQL.
- Có đúng một JDBC batch.
- Một thứ tự INSERT/UPDATE/DELETE cố định.
- Network đã chỉ đi một round trip.
- Exception không thể xuất hiện ở commit.

### 1.4. `commit()` kết thúc transaction, không phải `flush()`

```java
em.getTransaction().commit();
```

Khi thành công, transaction hoàn tất theo bảo đảm của DB/JPA transaction handling. Provider có thể flush pending changes trước khi commit.

Một transaction có thể chứa nhiều flushes. Một flush có thể có nhiều batches. Một batch có thể chỉ chứa một loại SQL và chưa commit.

### 1.5. JDBC batch là cơ chế của tầng JDBC

Một ví dụ JDBC trực tiếp:

```java
try (PreparedStatement ps = connection.prepareStatement(
        """
        INSERT INTO sensor_readings
            (sensor_key, reading_value)
        VALUES (?, ?)
        """)) {

    for (int value = 0; value < 1_000; value++) {
        ps.setString(1, "sensor-A");
        ps.setInt(2, value);
        ps.addBatch();
    }

    int[] updateCounts = ps.executeBatch();
}
```

Code gọi `addBatch()` nhiều lần và `executeBatch()` để driver xử lý nhóm statements.

JPA **không yêu cầu** provider phải thực hiện chuỗi gọi JDBC này cho bất kỳ số lần `persist()` nào.

---

## 2. Bảng so sánh các khái niệm thường bị đánh đồng

| Khái niệm | Đơn vị | Điều khẳng định được | Không khẳng định được |
| --- | --- | --- | --- |
| `persist(entity)` | Entity lifecycle operation | Đưa entity mới vào management theo semantics JPA | Một INSERT ngay |
| Dirty checking | Managed entity state | Theo dõi thay đổi để đồng bộ | Mỗi setter là một UPDATE |
| `flush()` | Persistence context synchronization | Đồng bộ pending changes đến DB | Transaction đã commit |
| `commit()` | Transaction | Hoàn tất giao dịch thành công hoặc báo lỗi | Một JDBC batch duy nhất |
| JDBC `addBatch()` | Statement parameters/commands | Thêm operation vào JDBC batch | Đã gửi SQL/commit |
| JDBC `executeBatch()` | Driver batch execution | Yêu cầu thực thi batch | Bao nhiêu network round trips bên dưới driver |
| ORM SQL ordering | Provider optimization | Có thể gom statements tương đồng | Giữ source-code call order |
| `saveAll()` | Spring Data repository API | Xử lý tập entities theo implementation | Sử dụng JDBC batching |
| JPQL bulk `UPDATE` | Query-level mutation | Có thể cập nhật nhiều rows bằng một query | Lifecycle/dirty checking cho từng entity |

**Đếm entities, SQL statements, prepared statements, JDBC batch executions, database rows và transactions là những số đo khác nhau.**

---

## 3. Những bảo đảm của Jakarta Persistence

JPA có những hợp đồng chuẩn rất có giá trị, nhưng chúng không phải một performance specification buộc provider gửi SQL theo cách cố định.

### 3.1. Persistence context và entity states

Các entity thường đi qua:

```text
new / transient
      |
      | persist
      v
managed
      |
      | remove
      v
removed

managed --detach/clear/close--> detached
```

Provider chịu trách nhiệm quản lý identity, thay đổi của managed entities và đồng bộ phù hợp với transaction.

Một managed entity có thể được sửa nhiều lần trước flush:

```java
Order order = em.find(Order.class, id);
order.setStatus(OrderStatus.PROCESSING);
order.setStatus(OrderStatus.CONFIRMED);
```

Nếu chỉ có trạng thái cuối được đồng bộ thành SQL, đó là tác dụng của unit-of-work/dirty checking; **không chứng minh JDBC batching**.

### 3.2. Flush mode

JPA định nghĩa:

```java
FlushModeType.AUTO
FlushModeType.COMMIT
```

Với `AUTO`, provider có trách nhiệm bảo đảm các thay đổi thuộc persistence context có thể ảnh hưởng kết quả query được thể hiện phù hợp theo semantics của flush mode; provider có thể thực hiện flush trước query.

Với `COMMIT`, thời điểm đồng bộ thay đổi với query trước commit có semantics khác và không nên dựa vào việc query luôn nhìn thấy pending changes như `AUTO`.

**Flush mode không phải batch size.**

### 3.3. Flush có thể xảy ra nhiều lần

```java
em.persist(a);
em.flush();

em.persist(b);
em.flush();

em.getTransaction().commit();
```

Có hai explicit flushes trong cùng transaction. Cấu hình JDBC batching không thể gom hai statements vào một JDBC batch nếu chúng đã bị thực thi ở các flush boundaries tách biệt.

### 3.4. Không có chuẩn JPA cho `hibernate.jdbc.batch_size`

Không có lời hứa portable rằng:

```java
for (...) {
    em.persist(x);
}
```

sẽ trở thành một batch cố định 20, 50 hay 100 operations.

Các properties như `hibernate.jdbc.batch_size` hoặc `hibernate.order_inserts` thuộc Hibernate và có thể không tồn tại hoặc có cách viết khác trong EclipseLink/OpenJPA/provider khác.

### 3.5. Không có thứ tự SQL tuyệt đối theo thứ tự gọi Java

```java
em.persist(child);
em.persist(parent);
```

không chứng minh provider sẽ gửi INSERT child trước parent. Provider phải đồng bộ phù hợp với mapping, foreign-key constraints và lifecycle semantics, nhưng có thể sắp xếp/gom SQL theo kế hoạch riêng.

**Thứ tự mà application gọi setters/persist không phải hợp đồng portable về thứ tự SQL log.**

### 3.6. Giao dịch vẫn phải đúng khi batching tắt

Nếu provider không batch, ứng dụng vẫn phải đúng về entity relationships, constraints, rollback và committed state.

**Batching là tối ưu tùy chọn, không được trở thành điều kiện để business invariants hoạt động đúng.**

---

## 4. Mô hình minh họa: ghi nhiều bản đọc cảm biến

Dùng entity ít quan hệ để phân tích batch INSERT không bị nhiễu bởi cascade/foreign keys.

```java
package com.example.metrics.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.SequenceGenerator;
import jakarta.persistence.Table;
import java.time.Instant;

@Entity
@Table(name = "sensor_readings")
public class SensorReading {

    @Id
    @SequenceGenerator(
        name = "sensor_reading_seq_gen",
        sequenceName = "sensor_reading_seq",
        allocationSize = 50
    )
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "sensor_reading_seq_gen"
    )
    private Long id;

    @Column(name = "sensor_key", nullable = false)
    private String sensorKey;

    @Column(name = "reading_value", nullable = false)
    private int readingValue;

    @Column(name = "recorded_at", nullable = false)
    private Instant recordedAt;

    protected SensorReading() {
    }

    public SensorReading(
            String sensorKey,
            int readingValue,
            Instant recordedAt) {

        this.sensorKey = sensorKey;
        this.readingValue = readingValue;
        this.recordedAt = recordedAt;
    }

    public Long getId() {
        return id;
    }

    public String getSensorKey() {
        return sensorKey;
    }

    public int getReadingValue() {
        return readingValue;
    }

    public Instant getRecordedAt() {
        return recordedAt;
    }
}
```

Schema PostgreSQL mang tính minh họa:

```sql
CREATE SEQUENCE sensor_reading_seq
    START WITH 1
    INCREMENT BY 50;

CREATE TABLE sensor_readings (
    id BIGINT PRIMARY KEY,
    sensor_key VARCHAR(255) NOT NULL,
    reading_value INTEGER NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL
);
```

**Lưu ý:** sequence increment/optimizer/allocation phải nhất quán với Hibernate version/configuration/migration đang dùng. Ví dụ đặt `INCREMENT BY 50` nhằm minh họa cấu hình liên quan; không áp dụng tùy tiện vào một sequence đã tồn tại hoặc đang được nhiều applications dùng.

### 4.1. Vì sao chọn SEQUENCE cho ví dụ?

Khi provider có thể lấy/gán identifiers trước khi gửi INSERT, nó thường thuận tiện hơn để gom nhiều INSERT cùng SQL shape.

`SEQUENCE` cũng **không tự bảo đảm batching**: cần cấu hình provider, driver, đủ mutations trong cùng flush window và không có yếu tố phá nhóm.

### 4.2. Mục tiêu là ghi nhiều rows nhưng vẫn đúng transaction

Ví dụ tạo 1.000 readings trong một transaction:

```java
EntityManager em = emf.createEntityManager();

try {
    em.getTransaction().begin();

    for (int i = 0; i < 1_000; i++) {
        em.persist(new SensorReading(
            "sensor-A",
            i,
            Instant.now()
        ));
    }

    em.getTransaction().commit();

} catch (RuntimeException ex) {
    if (em.getTransaction().isActive()) {
        em.getTransaction().rollback();
    }
    throw ex;

} finally {
    em.close();
}
```

Kết quả nghiệp vụ mong muốn là 1.000 rows committed khi transaction thành công, **không phải “chính xác 20 JDBC batches” theo chuẩn JPA**.

---

# Phần I — Provider thực hiện gom ghi thế nào?

## 5. Hibernate JDBC batching

Hibernate có cấu hình phổ biến:

```properties
hibernate.jdbc.batch_size=50
```

Giá trị dương cho phép Hibernate xem xét gom nhiều statement operations thành JDBC batches theo provider implementation.

**Giá trị 50 không có nghĩa Hibernate luôn gom đúng 50 rows trong mọi lần thực thi.**

Batch có thể nhỏ hơn khi:

- Chỉ còn 17 pending INSERTs ở cuối.
- SQL shape thay đổi.
- Entity type thay đổi.
- Có flush boundary khác.
- Database/generated-key strategy buộc thực thi sớm.
- Dependencies hoặc ordering buộc tách nhóm.
- Driver/provider/dialect không hỗ trợ đầy đủ một trường hợp.
- Dynamic SQL/optimistic locks làm thay đổi grouping.

### 5.1. Các cấu hình liên quan

Trong Hibernate, ví dụ:

```properties
hibernate.jdbc.batch_size=50
hibernate.order_inserts=true
hibernate.order_updates=true
```

Các properties trên là Hibernate-specific. Tên/cách hỗ trợ nên được đối chiếu với **phiên bản Hibernate đang dùng** trước khi đưa vào production.

`order_inserts` và `order_updates` cho phép Hibernate **xem xét sắp xếp mutation statements** theo hướng cải thiện grouping. Không bảo đảm một thứ tự tuyệt đối và có thể gây thêm CPU/memory overhead.

### 5.2. Ví dụ gom cùng SQL shape

Giả sử Hibernate cần thực thi:

```sql
INSERT INTO sensor_readings
  (id, sensor_key, reading_value, recorded_at)
VALUES (?, ?, ?, ?)
```

1.000 lần với các parameter sets khác nhau.

Khi JDBC batching hoạt động, cùng một prepared statement shape có thể nhận nhiều parameter sets qua `addBatch`, rồi được thực thi bằng `executeBatch`.

Điều này khác với một SQL:

```sql
INSERT INTO sensor_readings (...) VALUES
    (...),
    (...),
    (...);
```

Một JDBC batch **không nhất thiết** được log dưới dạng một SQL multi-row INSERT. JDBC driver có thể dùng protocol batching, rewrite statements hoặc gửi nhiều operations theo cách khác.

### 5.3. Kích thước batch là lựa chọn workload-specific

Một điểm bắt đầu như 20–50 operations thường được dùng trong thực tế, nhưng **không có một kích thước tối ưu cho mọi ứng dụng**.

Batch lớn quá có thể:

- Tăng memory cho pending statements/parameters.
- Gây transaction kéo dài và lock retention.
- Tăng nguy cơ packet/message size limits ở driver/DB.
- Làm error attribution trong batch khó hơn.
- Tăng tail latency khi database contention.
- Giảm hiệu quả nếu phần lớn SQL shapes khác nhau.

Hãy benchmark trên số rows, độ rộng row, network RTT, DB capacity và SLO thực.

---

## 6. `order_inserts` và `order_updates` giải quyết điều gì?

Giả sử trong cùng persistence context có:

```text
INSERT Order A
INSERT Reading A
INSERT Order B
INSERT Reading B
INSERT Order C
INSERT Reading C
```

Nếu provider thực thi xen kẽ nhiều SQL shapes, mỗi group có thể ngắn. Khi ordering hợp lệ, có thể trở thành:

```text
INSERT Order A
INSERT Order B
INSERT Order C

INSERT Reading A
INSERT Reading B
INSERT Reading C
```

Khi đó batching cho từng prepared statement dễ hơn.

### 6.1. Sắp xếp SQL là optimization, không phải nghiệp vụ

Không được dựa vào log thứ tự để biểu đạt:

> “Order A phải được tạo trước Reading A vì Java đã gọi persist(Order A) trước.”

Nếu business cần causal ordering, phải biểu diễn bằng relationships, constraints, application workflow và transaction semantics phù hợp.

### 6.2. Thứ tự ảnh hưởng deadlocks

Ordering nhất quán theo identifiers có thể **giảm** deadlock trong một số workloads. Nhưng reordering cũng có chi phí và không loại bỏ mọi deadlock.

Đo:

- Batch size thực tế.
- Throughput/latency.
- Deadlock rate.
- Lock wait time.
- CPU/memory overhead.

### 6.3. Relationship dependencies có quyền ưu tiên

Nếu `OrderLine` có foreign key tới `PurchaseOrder`, SQL phải tuân thủ ràng buộc. Provider không thể tùy ý gửi mọi child INSERT trước parent khi database đang kiểm tra FK ngay.

Ordering optimization vẫn phải tôn trọng dependencies và database constraints.

---

## 7. Khóa sinh tự động ảnh hưởng batching

Đây là một nguyên nhân phổ biến khiến “đã bật batch size 50 nhưng log vẫn có INSERT lẻ”.

JPA hỗ trợ các lựa chọn identifier generation, trong đó có:

```java
GenerationType.IDENTITY
GenerationType.SEQUENCE
GenerationType.TABLE
GenerationType.AUTO
```

Tác động thực tế phụ thuộc provider và database.

### 7.1. IDENTITY thường làm khó gom INSERT trong Hibernate

Ví dụ:

```java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
```

Với nhiều cấu hình Hibernate, INSERT phải được thực thi sớm để lấy database-generated identity value; vì vậy Hibernate có thể không batch các entity INSERT dùng `IDENTITY` theo cách như SEQUENCE-based writes.

**Không biến kết luận này thành quy luật bắt buộc của chuẩn JPA hoặc mọi Hibernate version/driver.** Điều cần nhớ là generated ID requirements ảnh hưởng trực tiếp đến khả năng trì hoãn SQL và gom statements.

### 7.2. SEQUENCE có thể cho ID trước INSERT

Ví dụ:

```java
@Id
@SequenceGenerator(
    name = "reading_seq",
    sequenceName = "sensor_reading_seq",
    allocationSize = 50
)
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "reading_seq"
)
private Long id;
```

Nếu provider/DB hỗ trợ sequence và allocation strategy phù hợp, entity có thể nhận ID trước khi INSERT row.

### 7.3. `allocationSize` không phải JDBC batch size

```java
allocationSize = 50
```

liên quan chiến lược cấp phát identifier values của sequence generator, **không** có nghĩa một `executeBatch()` sẽ chứa 50 INSERTs.

Hai con số có thể tình cờ bằng nhau nhưng giải quyết **hai vấn đề độc lập**.

### 7.4. TABLE generator không tự tối ưu INSERT batching

`GenerationType.TABLE` có thể dùng bảng đặc biệt để cấp identifiers. Nó có contention/SQL overhead riêng tùy provider/configuration và không phải bảo đảm batch inserts hiệu quả.

### 7.5. AUTO không có cùng hành vi trên mọi database

`GenerationType.AUTO` giao lựa chọn chiến lược cho provider/dialect. PostgreSQL có sequence support, MySQL thường có identity-style options; đừng giả định cùng code AUTO sẽ có batch behavior giống nhau.

### 7.6. Khóa tự cấp từ application

Một entity dùng ID do ứng dụng sinh trước có thể giảm nhu cầu SELECT/INSERT trước chỉ để lấy key. Tuy nhiên, tự cấp UUID/snowflake/key cũng có tradeoffs về index locality, kích thước index và tính đúng của uniqueness.

Không đổi identifier strategy chỉ vì một benchmark nhỏ mà chưa xem migration và operational impact.

---

## 8. Khi nào SQL được tạo trong vòng lặp?

Hai đoạn code có thể có hiệu năng khác nhau:

**Vòng lặp không gọi flush thủ công:**

```java
for (int i = 0; i < count; i++) {
    em.persist(new SensorReading(
        "sensor-A", i, now
    ));
}

em.flush();
```

**Flush sau từng entity:**

```java
for (int i = 0; i < count; i++) {
    em.persist(new SensorReading(
        "sensor-A", i, now
    ));
    em.flush();
}
```

Trong đoạn thứ hai, mỗi flush có thể buộc provider thực thi pending statement sớm, làm mất cơ hội gom nhiều INSERTs trong một batch window.

### 8.1. `flush` trong vòng lặp không đồng nghĩa “nhanh hơn”

Có thể cần flush sớm để:

- Phát hiện constraint violation trước một bước nghiệp vụ tiếp theo.
- Đồng bộ SQL trước truy vấn có phụ thuộc.
- Quản lý memory theo chunk.
- Đáp ứng khóa ngoại/identifier flows cụ thể.

Nhưng flush sau mỗi record thường bất lợi cho batching và có thể tăng round trips.

### 8.2. Không gọi `flush` chỉ để bảo đảm đã commit

Flush vẫn nằm trong transaction. Nếu transaction rollback, SQL đã flush cũng không trở thành committed data.

---

## 9. `flush()` và `clear()` theo chunk

Khi nhập nhiều entities, persistence context giữ nhiều managed instances/snapshots. Nếu giữ hàng trăm nghìn objects đến cuối transaction, memory và dirty checking overhead có thể tăng.

Một pattern Hibernate/JPA thường thấy là flush và clear theo chunk.

```java
EntityManager em = emf.createEntityManager();

int chunkSize = 50;

try {
    em.getTransaction().begin();

    Instant recordedAt = Instant.now();

    for (int i = 0; i < 10_000; i++) {
        em.persist(new SensorReading(
            "sensor-A", i, recordedAt
        ));

        if ((i + 1) % chunkSize == 0) {
            em.flush();
            em.clear();
        }
    }

    // Đồng bộ phần dư chưa được flush.
    em.flush();

    em.getTransaction().commit();

} catch (RuntimeException ex) {
    if (em.getTransaction().isActive()) {
        em.getTransaction().rollback();
    }
    throw ex;

} finally {
    em.close();
}
```

### 9.1. `chunkSize` và JDBC `batch_size` là hai tham số riêng

Có thể chọn cả hai là 50 để dễ hình dung, nhưng:

- `chunkSize` kiểm soát application flush/clear boundary và managed-entity memory.
- `hibernate.jdbc.batch_size` kiểm soát provider-side JDBC batching opportunities.

Không nên tự đồng nhất hai giá trị trong logic hoặc test.

### 9.2. `clear()` detach toàn bộ managed entities

Sau:

```java
em.clear();
```

những entity references được giữ bên ngoài sẽ trở thành detached. Việc sửa fields sau đó **không tự được đồng bộ** qua context như trước.

Nếu vòng lặp có quan hệ với entities còn cần dùng, `clear()` có thể phá cách code dựa vào `em.contains(...)`, lazy access hoặc cascades tiếp theo.

### 9.3. Flush/clear không chia nhỏ transaction

Code ở trên vẫn có **một transaction lớn**. Nếu record thứ 9.999 gây lỗi và transaction rollback, toàn bộ 10.000 rows chưa commit có thể rollback.

Sơ đồ:

```text
BEGIN
  persist 50 -> flush/clear
  persist 50 -> flush/clear
  ...
  persist 50 -> flush/clear
COMMIT

Một transaction duy nhất.
```

**Flush/clear chunking** không đồng nghĩa **commit chunking**.

### 9.4. Commit theo nhiều chunks là một quyết định khác

Nếu muốn mỗi 500 records commit độc lập, cần transaction boundaries riêng:

```text
Transaction A: rows 1..500 -> commit
Transaction B: rows 501..1000 -> commit
...
```

Khi một chunk thất bại, các chunks trước đó đã commit. Không còn all-or-nothing cho toàn import; cần business contract, checkpoint, idempotency và retry policy riêng.

---

## 10. Spring Data JPA `saveAll` không bảo đảm JDBC batching

Một repository:

```java
public interface SensorReadingRepository
        extends JpaRepository<SensorReading, Long> {
}
```

Ứng dụng:

```java
List<SensorReading> items = ...;
repository.saveAll(items);
```

`saveAll` là **API xử lý nhiều entities**, không phải chuẩn JPA JDBC batching guarantee.

Spring Data JPA thường xử lý các entities qua persistence operations như `save`; khả năng Hibernate gom SQL phụ thuộc setup dưới repository.

### 10.1. Một `saveAll` có thể vẫn có nhiều INSERT executions

Các yếu tố ảnh hưởng:

- `hibernate.jdbc.batch_size`.
- Key generation: `IDENTITY` hay `SEQUENCE`.
- Transaction boundaries.
- SQL shape.
- Cascades and associations.
- Provider/dialect.
- Driver settings.

### 10.2. `saveAllAndFlush` cũng không phải “batch all”

```java
repository.saveAllAndFlush(items);
```

Nó đẩy việc flush ở thời điểm khác, **không tự hứa batch size hoặc number of network calls**.

### 10.3. Outer transaction quan trọng

Khi import:

```java
@Transactional
public void importData(List<ReadingInput> inputs) {
    List<SensorReading> items = ...;
    repository.saveAll(items);
}
```

Toàn bộ import có thể chia sẻ transaction/context của service. Nếu gọi repository từng record mà không có outer transaction, các transaction boundaries có thể khác và cơ hội batching kém hơn.

Đừng ngộ nhận `@Transactional` biến nhiều repository methods thành một prepared statement duy nhất; nó chỉ điều phối transaction boundary.

### 10.4. Spring proxy self-invocation

Trong Spring proxy-based mode:

```java
this.importData(inputs);
```

có thể bỏ qua `@Transactional` advice của method gọi nội bộ. Nếu transaction boundary không như mong muốn, behavior batching/flush cũng thay đổi.

Hãy kiểm tra service thực sự chạy qua proxy hoặc dùng transaction orchestration phù hợp.

---

## 11. Insert batching khác update batching

### 11.1. Batch INSERT

Có nhiều new entities:

```java
for (ReadingInput input : inputs) {
    em.persist(new SensorReading(
        input.sensorKey(),
        input.value(),
        input.recordedAt()
    ));
}
```

Provider có thể gom những INSERT cùng SQL shape.

### 11.2. Batch UPDATE

Có nhiều managed entities được tải và sửa:

```java
for (Long id : readingIds) {
    SensorReading reading =
        em.find(SensorReading.class, id);

    // Giả sử entity có domain method điều chỉnh dữ liệu.
    reading.correctValue(newValue);
}
```

Provider dirty checking có thể tạo nhiều UPDATE statements và gom chúng nếu đủ điều kiện.

Đoạn này mô tả tình huống với một domain method bổ sung; entity `SensorReading` ở phần 4 có immutable-style API và không định nghĩa `correctValue`. Trong dự án thật, khai báo method hoặc dùng một entity mutable riêng phù hợp.

### 11.3. N lần SELECT trước UPDATE là chi phí riêng

Nếu vòng lặp trên N IDs gọi `em.find()` N lần, bạn có thể tiết kiệm phần UPDATE bằng JDBC batching nhưng vẫn phát N SELECTs khi các IDs chưa nằm trong L1/L2.

Khi tối ưu, cần đo cả:

- SELECT count/rows.
- UPDATE batch executions.
- Entity hydration overhead.
- Database lock contention.
- Total latency.

### 11.4. Bulk JPQL UPDATE là một cơ chế khác

```java
int affected = em.createQuery(
    """
    UPDATE InventoryItem i
    SET i.quantity = i.quantity + :increment
    WHERE i.category = :category
    """
)
.setParameter("increment", 1)
.setParameter("category", category)
.executeUpdate();
```

Một bulk JPQL UPDATE có thể ảnh hưởng nhiều rows bằng **một SQL UPDATE**, nhưng không tương đương batch nhiều managed entity UPDATEs.

Bulk DML thường bypass normal entity dirty checking/lifecycle callbacks cho từng row và có thể khiến entities đã managed trong L1 stale. Cần xem versioning, audit, cache invalidation và transaction correctness.

### 11.5. Đừng dùng bulk để né business invariants

Nếu mỗi entity update cần domain validation/callbacks hoặc optimistic version check, đổi toàn bộ sang bulk SQL có thể làm thay đổi tính đúng đắn. Performance gain phải được đánh giá cùng correctness.

---

## 12. Batch DELETE và quan hệ khóa ngoại

Nhiều `em.remove(entity)` có thể tạo nhiều DELETE statements. Provider có thể gom nếu SQL shapes và dependencies cho phép.

Tuy nhiên, deletion liên quan:

- Foreign key constraints.
- Cascades `REMOVE`.
- Orphan removal.
- Join tables.
- Child rows cần xóa trước parent.
- Entity lifecycle callbacks.
- Versioned DELETE semantics.

### 12.1. Một remove có thể sinh nhiều SQL

```java
em.remove(order);
```

với một aggregate có children có thể cần:

```text
DELETE order_lines ...
DELETE order_tags ...
DELETE orders ...
```

Không thể suy từ `remove` một entity rằng JDBC chỉ thực thi một DELETE.

### 12.2. SQL ordering phải tuân thủ dependencies

Provider có thể phải xử lý child rows/association tables trước parent để thỏa foreign key. Điều này giới hạn khả năng gom tất cả DELETEs theo một thứ tự tùy ý.

### 12.3. Bulk DELETE khác entity remove

```java
em.createQuery(
    "DELETE FROM PurchaseOrder o WHERE o.status = :status"
)
.setParameter("status", OrderStatus.CANCELLED)
.executeUpdate();
```

Bulk DELETE không có cùng per-entity lifecycle/cascade semantics như gọi `em.remove()` trên từng managed entity. Cần hiểu database cascading, JPA cascades, orphan removal, versioning và L1 state trước khi dùng.

---

## 13. Relationship/cascade và batching

Giả sử:

```java
@Entity
class PurchaseOrder {

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.PERSIST
    )
    private List<OrderLine> lines = new ArrayList<>();
}
```

Mỗi order có 10 lines. Nếu tạo 100 orders, thực tế có thể có:

```text
100 INSERT purchase_orders
1000 INSERT order_lines
```

chưa kể IDs, join tables hoặc additional mapped tables.

### 13.1. Một `persist(order)` không đồng nghĩa một INSERT

Cascade có thể làm provider persist nhiều child entities.

### 13.2. Dependency ảnh hưởng ordering

`OrderLine` có FK `order_id`. Khi provider chưa biết parent ID hoặc database yêu cầu parent tồn tại, thứ tự SQL có thể cần được điều phối.

### 13.3. `IDENTITY` ở parent có thể ảnh hưởng children

Nếu parent ID phải lấy từ INSERT sớm, batching opportunities có thể thấp hơn so với preallocated identifiers.

### 13.4. Cẩn thận khi `clear` trong aggregate processing

Sau flush/clear, parent/children bị detached. Các domain methods như `order.addLine(...)` trên detached graph sẽ không tự động tạo managed child INSERT trừ khi có thao tác reattach/persist phù hợp.

### 13.5. Quan hệ cần được giữ đúng cả khi tắt batching

Đừng phụ thuộc vào một optimization SQL order để tình cờ tránh foreign key violation. Mapping và transaction design phải đúng bất kể provider có reordering hay không.

---

## 14. Dynamic INSERT/UPDATE có thể làm SQL shapes khác nhau

JDBC batch thường gom tốt khi các operations có cùng prepared SQL form.

Giả sử hai entities cùng type nhưng Hibernate tạo các SQL khác nhau:

```sql
INSERT INTO products (id, sku, name)
VALUES (?, ?, ?);

INSERT INTO products (id, sku, name, description)
VALUES (?, ?, ?, ?);
```

Nếu SQL text khác nhau, chúng không thể dùng **cùng prepared statement batch** theo cách đơn giản.

### 14.1. Hibernate `@DynamicInsert`

Hibernate có extension `@DynamicInsert` trong một số tình huống, khiến column set của INSERT phụ thuộc những giá trị không null/semantics dynamic generation. Điều này có thể tạo nhiều SQL shapes và làm giảm cơ hội batching.

### 14.2. Hibernate `@DynamicUpdate`

`@DynamicUpdate` có thể tạo UPDATE chỉ cho các cột dirty, khiến SQL forms thay đổi giữa các entities. Nó có thể giảm số bytes/cột cập nhật nhưng cũng có tradeoff về prepared-statement reuse và batching.

### 14.3. Không tuyên bố dynamic SQL luôn chậm

Với rows rộng và chỉ ít cột thay đổi, dynamic update có thể có lợi. Cần benchmark end-to-end theo workload cụ thể.

---

## 15. Optimistic locking và JDBC batch update counts

JPA `@Version` kiểm soát optimistic concurrency:

```java
@Version
private Long version;
```

Khi UPDATE, provider thường cần biết row đã được cập nhật đúng theo version hay chưa.

Ví dụ SQL dạng khái niệm:

```sql
UPDATE inventory_items
SET quantity = ?, version = ?
WHERE id = ? AND version = ?;
```

Nếu affected row count là 0, provider có thể phát hiện optimistic conflict.

### 15.1. Batch UPDATE cần kết quả phù hợp

Một JDBC driver có thể trả batch update counts với các giá trị như `SUCCESS_NO_INFO` hoặc những semantics riêng. Provider phải xử lý đúng optimistic locking theo khả năng của driver/dialect.

Vì vậy batching trên versioned entities có thể được provider/version điều chỉnh hoặc hạn chế. Không giả định tất cả versioned updates được gom hệt non-versioned updates.

### 15.2. Không tắt optimistic locking để tăng throughput

Nếu nghiệp vụ cần phát hiện concurrent updates, việc bỏ `@Version` chỉ để tăng batch rate có thể gây lost updates.

### 15.3. Rollback cả transaction khi một entity conflict

Khi một batch có optimistic conflict/SQL violation, transaction có thể phải rollback. Dù một số SQL trong batch đã được thực thi trong transaction, chúng chưa nhất thiết committed.

Phục hồi đúng là rollback failed attempt, context mới, reload state và quyết định retry/merge nghiệp vụ; không tiếp tục flush với context đã lỗi.

### 15.4. Không dùng `rowCount == batchSize` làm invariant portable

Một số drivers trả counts không cho thông tin chi tiết từng operation, và provider có chiến lược khác nhau. Cần test optimistic behavior, không chỉ số đếm.

---

## 16. SQL batching không thay thế transaction isolation

Hai giao dịch cùng update/insert business key vẫn có thể cạnh tranh, dù batching bật.

Ví dụ:

```text
Transaction A: batch INSERT 50 order codes
Transaction B: batch INSERT 50 order codes

Một key xuất hiện ở cả hai batches
```

Database UNIQUE constraint phải bảo vệ invariant. Batching không tự giải quyết:

- Duplicate business keys.
- Race conditions.
- Optimistic conflicts.
- Foreign key references.
- Deadlocks.
- Serialization failures.
- Read/write isolation.

### 16.1. Một batch có thể thất bại giữa chừng

JDBC `BatchUpdateException` có thể kèm update counts cho một số operations. Không coi những counts đó là committed result khi transaction chưa commit.

### 16.2. Batching và idempotency

Nếu một import transaction bị mất kết nối ở commit, ứng dụng có thể không biết database đã commit hay chưa. Retry cùng dữ liệu có thể tạo duplicates hoặc conflicts.

Giải pháp là business idempotency keys, UNIQUE constraints, reconciliation hoặc staging workflows chứ không phải tăng `batch_size`.

---

# Phần II — Đo lường đúng

## 17. Không đếm `persist` calls rồi gọi đó là số SQL

Ví dụ:

```java
for (int i = 0; i < 100; i++) {
    em.persist(...);
}
```

Bộ đếm Java nhận 100 calls. Nhưng:

- Có thể chưa phát INSERT ngay.
- Có thể phát SELECT sequence operations.
- Có thể flush khi commit.
- Provider có thể batch prepared statements.
- Có thể có nhiều SQL per entity vì mapping.
- Có thể thiếu INSERT nếu business code throw trước flush.
- Có thể rollback toàn transaction.

**100 `persist` calls không tương đương 100 JDBC executions hoặc 100 committed rows.**

---

## 18. Hibernate Statistics không trực tiếp bằng số JDBC batch executions

Hibernate có API:

```java
SessionFactory sessionFactory =
    emf.unwrap(SessionFactory.class);

Statistics statistics =
    sessionFactory.getStatistics();

statistics.setStatisticsEnabled(true);
statistics.clear();
```

Một số counters thông dụng:

```java
long inserts =
    statistics.getEntityInsertCount();

long updates =
    statistics.getEntityUpdateCount();

long deletes =
    statistics.getEntityDeleteCount();

long prepared =
    statistics.getPrepareStatementCount();
```

Đây là **Hibernate-specific API**.

### 18.1. Entity counters đếm events ở cấp entity

Nếu `getEntityInsertCount()` tăng 1.000, điều này cho biết Hibernate ghi nhận các insert events, **không đồng nghĩa đã gọi `executeBatch()` 1.000 lần hoặc chỉ một lần**.

### 18.2. Prepared statement count không phải batch count

`getPrepareStatementCount()` đếm prepared statements theo semantics Hibernate statistics. Nó không phải số `executeBatch()` và càng không phải số network round trips.

Một prepared statement có thể được tái sử dụng cho nhiều parameter sets.

### 18.3. Stats cần cô lập

`Statistics` thường ở scope `SessionFactory`. Nếu parallel tests/background requests cùng dùng factory, counters bị nhiễu.

Cần đo trong một cửa sổ cô lập; `statistics.clear()` chỉ reset counters, không tự truncate tables/close connections/clear DB caches.

---

## 19. SQL logs vẫn hiển thị nhiều INSERT khi batching hoạt động

Nếu Hibernate log:

```sql
insert into sensor_readings (...) values (?, ?, ?, ?)
insert into sensor_readings (...) values (?, ?, ?, ?)
insert into sensor_readings (...) values (?, ?, ?, ?)
```

không thể kết luận ba network round trips.

Provider có thể log SQL form theo mỗi ORM operation, trong khi JDBC driver gom executions qua `addBatch`/`executeBatch`.

### 19.1. Log SQL và executed JDBC calls là hai lớp

```text
ORM generated SQL text:
  INSERT (parameters set A)
  INSERT (parameters set B)
  INSERT (parameters set C)

JDBC:
  prepareStatement(SQL)
  addBatch(A)
  addBatch(B)
  addBatch(C)
  executeBatch()
```

Đây là sơ đồ khái niệm, không hứa provider luôn gọi JDBC theo đúng số bước trên.

### 19.2. Driver có thể rewrite batching

Một số JDBC drivers có tối ưu rewrite batches thành multi-row forms hoặc wire-protocol operations. Cấu hình/behavior tùy driver.

Vì vậy ngay cả số lần `executeBatch()` cũng **không nhất thiết bằng** số physical network round trips.

---

## 20. Dùng JDBC-level instrumentation để thấy batching

Để kiểm tra một Hibernate/JDBC configuration có batch thật:

- Dùng DataSource proxy/wrapper hoặc JDBC observer có khả năng đếm `addBatch` và `executeBatch`.
- Ghi batch size distributions.
- Phân biệt SELECT/INSERT/UPDATE/DELETE.
- Đếm số DB rows affected.
- Quan sát SQL errors, retries và transaction outcomes.
- Bổ sung DB-side metrics và latency.

### 20.1. Không coi StatementInspector là JDBC batch counter

Hibernate `StatementInspector` quan sát SQL được provider chuẩn bị/điều chỉnh ở tầng ORM, không phải công cụ bảo đảm đếm chính xác `executeBatch` tại JDBC boundary.

Nó hữu ích để xem query shape, nhưng **không đủ để chứng minh batch count hoặc wire round trips**.

### 20.2. DataSource proxy phải được đặt đúng nơi

Sơ đồ:

```text
Hibernate
   |
   v
JDBC DataSource proxy
  - record prepareStatement
  - record addBatch
  - record executeBatch
   |
   v
JDBC Driver
   |
   v
Database
```

Nếu một test query chạy qua một DataSource khác proxy đang quan sát, số đếm sẽ sai. Cần đảm bảo ứng dụng thật dùng instrumentation DataSource.

### 20.3. Đơn vị đo cần ghi rõ

| Metric | Có thể nói gì? | Không thể tự nói gì? |
| --- | --- | --- |
| Entities persisted | Java intent count | Số INSERT/round trips |
| Hibernate entity insert count | ORM entity insert events | JDBC batch executions |
| JDBC addBatch calls | Parameter sets được thêm | Commit/success |
| JDBC executeBatch calls | Driver batch API invocations | Physical network RTT chắc chắn |
| JDBC executeUpdate calls | Executions ngoài batch | Rows committed |
| DB rows inserted | Rows affected/observed | Số round trips |
| Transaction commits | Committed transaction count | Batch size |
| p95 latency | User-facing performance | Cache/batch đã hoạt động |
| DB lock wait | Contention | Tính đúng của dữ liệu |

---

## 21. Bảng báo cáo thí nghiệm đúng cách

Giả sử chạy 10.000 sensor readings, nên ghi:

| Trường | Ví dụ |
| --- | --- |
| Provider | Hibernate 6.x |
| Database | PostgreSQL phiên bản mục tiêu |
| Driver | PostgreSQL JDBC version đã ghi nhận |
| ID generation | SEQUENCE allocationSize 50 |
| Entity mapping | Không cascade/collection |
| Transaction | Một RESOURCE_LOCAL transaction |
| JDBC batch config | 50 |
| Insert ordering | Enabled |
| Flush chunk | 50 |
| Entity input | 10.000 |
| JDBC batch executions | **Số đo thực tế** |
| Batch sizes observed | **Distribution thực tế** |
| INSERT count | **Số đo thực tế** |
| Rows committed | 10.000 nếu success |
| Total duration | **Số đo thực tế** |
| Memory/GC | **Số đo thực tế** |
| SQL errors | 0 hoặc lỗi cụ thể |

Đừng điền giả số batch executions chỉ vì `10000 / 50 = 200`. Đó là **một ước lượng lý tưởng**, không phải kết quả đo.

---

## 22. So sánh cấu hình bật/tắt batching

Một benchmark hữu ích có ít nhất hai cấu hình:

**Case A — không batch:**

```properties
hibernate.jdbc.batch_size=0
```

**Case B — batch enabled:**

```properties
hibernate.jdbc.batch_size=50
hibernate.order_inserts=true
```

Các property là Hibernate-specific. Kết quả phụ thuộc provider version và batchability của entity mapping.

Giữ các yếu tố khác tương đương:

- Cùng database và schema.
- Cùng entity model.
- Cùng ID generator.
- Cùng lượng rows và kích thước payload.
- Cùng transaction boundaries.
- Cùng connection pool settings.
- Cùng indexes/constraints.
- Cùng machine/network conditions.
- Cùng warm-up/caching conditions.

### 22.1. Không chỉ nhìn thời gian của một lần chạy

Lần đầu có thể gồm JVM JIT, connection pool startup, DB buffer/cache warm-up, query plan compilation. Chạy nhiều iterations và xem distribution thay vì kết luận từ 1 lần.

### 22.2. Throughput và p95 latency có thể đi ngược chiều

Một batch lớn có thể tăng records/second nhưng làm một request chờ lâu hơn. Chọn theo SLO: bulk ingestion hay online create API có mục tiêu khác nhau.

### 22.3. Đếm cả rows/s và resource usage

Báo cáo:

- Rows committed/s.
- Time to commit N rows.
- JDBC batch execution count.
- Lock wait and deadlocks.
- Connection occupancy.
- Heap/GC.
- DB CPU/I/O/network.
- SQL errors/retry counts.

“SQL log ít dòng hơn” không phải benchmark.

---

# Phần III — Tính đúng đắn và transaction

## 23. Thứ tự của SQL không phải thứ tự của business events

Nếu gọi:

```java
em.persist(orderA);
em.persist(orderB);
em.persist(orderC);
```

provider có thể trì hoãn/gom INSERTs. Business logic không được suy ra thứ tự phát sinh event ngoài DB từ thứ tự JDBC executions.

### 23.1. Trigger có thể quan sát SQL execution order

Nếu database trigger phụ thuộc thứ tự INSERT, provider SQL ordering có thể ảnh hưởng hành vi cụ thể. Đó là lý do càng phải:

- Thiết kế logic trigger không phụ thuộc thứ tự không được hứa.
- Có ràng buộc dữ liệu rõ.
- Test trên provider/database mục tiêu.
- Tránh dùng order_inserts như một cơ chế business sequencing.

### 23.2. Timestamps không nên suy từ SQL ordering

Một entity có `createdAt` được set ở Java trước flush. Các SQL statements có thể được thực thi theo thứ tự khác. Timestamp/business order nên được định nghĩa bằng dữ liệu/domain contract, không bằng thứ tự log của provider.

### 23.3. Generated IDs không nhất thiết bằng thứ tự nghiệp vụ

Sequence values có thể có gaps do caching/rollback, và thứ tự cấp ID không nhất thiết bằng thứ tự commit.

Không dùng `id` tăng dần làm bằng chứng thứ tự hoàn tất transaction nếu business yêu cầu một sequencing contract mạnh.

---

## 24. Error trong JDBC batch không đồng nghĩa nửa transaction đã commit

Nếu một statement trong batch bị unique violation:

```text
BEGIN
  Batch:
    INSERT A
    INSERT B
    INSERT C -> UNIQUE violation
  ...
  ROLLBACK
```

Database có thể đã thực thi một số statement operations trước khi exception, nhưng nếu chúng thuộc cùng transaction chưa commit và transaction rollback, những thay đổi đó không trở thành committed state.

### 24.1. BatchUpdateException update counts có giới hạn

JDBC `BatchUpdateException` có thể cung cấp `getUpdateCounts()` hoặc related metadata. Với driver, một số entries có thể là `SUCCESS_NO_INFO` hoặc `EXECUTE_FAILED`.

Không dùng update counts đơn lẻ để kết luận **rows committed**.

### 24.2. Không tiếp tục dùng failed EntityManager/transaction

Sau Hibernate/JPA flush error, transaction có thể rollback-only hoặc database transaction aborted.

Không viết:

```java
try {
    em.flush();
} catch (PersistenceException ex) {
    log.warn("Skip one record", ex);
    em.persist(nextRecord);
}
```

trong cùng context lỗi.

Rollback/discard context, rồi chọn transaction/chunk retry policy phù hợp.

### 24.3. Per-row skip cần thiết kế từ đầu

Nếu nghiệp vụ cần “bỏ qua 10 rows lỗi, nhập 990 rows đúng”, có thể:

- Validate trước khi ghi.
- Dùng staging table và error-reporting.
- Chia transactions thành chunks/records.
- Dùng database-specific conflict handling có semantics rõ.
- Dùng savepoint/nested tx chỉ khi provider/driver hỗ trợ và đã test.

Không biến việc catch một flush exception thành “partial success” mơ hồ.

---

## 25. Commit một batch không luôn có nghĩa mọi external effects đã thành công

Transaction database có thể commit nhưng email, message broker, search index hoặc API khác chưa nhận thay đổi.

Nếu batch import cần publish 1.000 events, gửi event trực tiếp trong entity callbacks có thể làm event đi trước commit. Nếu commit rollback, side effects không tự rollback.

Các lựa chọn:

- Ghi audit nội bộ trong cùng transaction.
- Transactional outbox ghi event intent cùng business rows.
- Worker gửi event sau commit với retry/idempotency.
- Kết hợp CDC nếu kiến trúc phù hợp.

Batching JDBC không cung cấp distributed atomicity với hệ thống ngoài.

---

## 26. Hibernate `@BatchSize` không phải write batching

Một nguồn nhầm lẫn phổ biến:

```java
@org.hibernate.annotations.BatchSize(size = 20)
@OneToMany(mappedBy = "order")
private List<OrderLine> lines;
```

Trong Hibernate, `@BatchSize` chủ yếu gắn với **batch fetching** — giảm số SELECT khi load entities/collections lười (LAZY) theo nhóm.

Nó **không phải** cấu hình rằng 20 INSERT/UPDATE sẽ được gom thành một JDBC write batch.

### 26.1. Đọc vs ghi

| Công cụ | Chủ đích |
| --- | --- |
| Hibernate `@BatchSize` | Batch fetch khi đọc |
| `hibernate.default_batch_fetch_size` | Fetch batching default |
| `JOIN FETCH` | Fetch plan của query |
| JPA EntityGraph | Kiểm soát fetching theo graph |
| `hibernate.jdbc.batch_size` | JDBC write batching |
| `hibernate.order_inserts` | SQL insert ordering optimization |
| `hibernate.order_updates` | SQL update ordering optimization |

Không trả lời câu hỏi “cách tăng tốc 10.000 INSERT” bằng cách chỉ thêm `@BatchSize` lên collection.

### 26.2. N+1 SELECT khác N INSERT

Nếu một request đọc 100 orders rồi truy cập lazy children, có thể phát N+1 SELECT. Fix liên quan fetch plan/batch fetching. Nếu request tạo 1000 rows, write batching giải quyết loại chi phí khác.

---

# Phần IV — Kiểm thử minh họa

## 27. Test portable: kiểm tra committed rows, không assert batch count

Một integration test **theo hợp đồng JPA** nên xác nhận dữ liệu đúng:

```java
@Test
void persistingManyReadingsCommitsExpectedRows() {
    String sensorKey =
        "test-" + UUID.randomUUID();

    int count = 120;

    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        for (int i = 0; i < count; i++) {
            em.persist(new SensorReading(
                sensorKey,
                i,
                Instant.now()
            ));
        }

        em.getTransaction().commit();

    } catch (RuntimeException ex) {
        if (em.getTransaction().isActive()) {
            em.getTransaction().rollback();
        }
        throw ex;

    } finally {
        em.close();
    }

    EntityManager verify = emf.createEntityManager();

    try {
        Long rows = verify.createQuery(
            """
            SELECT COUNT(r)
            FROM SensorReading r
            WHERE r.sensorKey = :key
            """,
            Long.class
        )
        .setParameter("key", sensorKey)
        .getSingleResult();

        assertEquals((long) count, rows);

    } finally {
        verify.close();
    }
}
```

Đây là test chức năng. Nó **không assert Hibernate đã gọi `executeBatch` đúng ba lần**.

### 27.1. Tại sao không assert SQL execution count trong test portable?

JPA không quy định số SQL statements, JDBC batch sizes hoặc network round trips. Test portable không nên thất bại chỉ vì provider thay implementation mà vẫn bảo đảm dữ liệu đúng.

### 27.2. Kiểm tra dữ liệu thực, không chỉ count

Nếu use case yêu cầu mọi `readingValue` từ 0 đến 119, test tốt hơn còn verify các values và mapping. `COUNT` chỉ là assertion đầu tiên.

### 27.3. Transaction phải được commit trước verify

Đừng dùng cùng EntityManager của transaction đang chưa commit để kết luận rows đã committed. Đóng transaction tạo dữ liệu rồi query ở context mới.

---

## 28. Test provider-specific: instrument JDBC batching

Nếu muốn khẳng định Hibernate configuration thực sự batch:

1. Tạo DataSource proxy/wrapper có thể ghi `addBatch`, `executeBatch`.
2. Khởi động JPA provider với `hibernate.jdbc.batch_size=50`.
3. Chạy 120 INSERT cùng SQL shape trong một transaction.
4. Đo actual batch executions và batch-size distribution.
5. Assert một mục tiêu **có điều kiện theo provider/driver version**, không dùng assertion portable JPA.
6. Verify 120 rows committed trong DB.
7. Ghi rõ DB/driver/dialect/ID generator/flush plan.

### 28.1. Test harness khái niệm

```java
record BatchObservation(
    long addBatchCalls,
    long executeBatchCalls,
    List<Integer> observedBatchSizes
) {
}
```

Đây chỉ là DTO nhận dữ liệu từ instrumentation, **không phải bộ đếm có sẵn của Jakarta Persistence**.

Một test có thể có assertions dạng:

```java
assertEquals(120, rowsCommitted);
assertTrue(observation.addBatchCalls() > 0);
assertTrue(observation.executeBatchCalls() > 0);
```

Khi không có JDBC proxy được cấu hình, **không gọi** các assertions trên. Trong provider/driver khác, `addBatch` có thể không phải chiến lược tối ưu được dùng; tiêu chí phải được định nghĩa theo stack mục tiêu.

### 28.2. Không tự tính `ceil(120/50)` làm số đo

Về lý tưởng, 120 operations chia theo batch size 50 có thể thành nhóm 50, 50, 20. Nhưng SQL shape, flush windows, generated IDs và driver decisions có thể làm kết quả khác.

Một assertion “chính xác 3 executeBatch” chỉ phù hợp khi test harness/provider config được đặc tả và behavior đã được xác định, không phải một điều kiện chuẩn JPA.

---

## 29. Test tình huống IDENTITY vs SEQUENCE

Để so sánh:

- Tạo hai entity mappings tương đương về dữ liệu nhưng khác ID strategy.
- Dùng cùng database/driver/provider version.
- Cùng transaction/row count.
- Cùng JDBC batch setting.
- Instrument `executeBatch` và SQL.
- Verify rows committed.
- Đo throughput và memory.

### 29.1. Không tự đổi ID strategy của bảng production để thử

Đổi từ IDENTITY sang SEQUENCE có thể cần:

- Schema migration.
- Xử lý sequence hiện tại.
- Kiểm tra key allocation giữa nhiều app instances.
- Đổi insert ordering và generated key handling.
- Tính toán lộ trình rollback migration.

Benchmark trên test schema riêng trước.

### 29.2. SEQUENCE cũng có chi phí

Provider có thể gọi sequence để lấy ID, dù dùng allocation optimization. Tách số sequence fetches và INSERT batch executions khi báo cáo.

---

## 30. Test flush/clear chunking

Kịch bản:

1. Tạo 125 readings.
2. Chunk size = 50.
3. `flush/clear` ở 50, 100, cuối 125.
4. Commit.
5. Query từ EntityManager mới.
6. Assert đúng 125 rows và values.

### 30.1. Test Java object detached state

Sau `clear()`:

```java
SensorReading first = ...;
em.persist(first);
em.flush();
em.clear();

assertFalse(em.contains(first));
```

Object `first` detached. Dù bạn vẫn giữ Java reference, thay đổi field trên nó sau clear không tự được dirty-check trong context hiện tại.

### 30.2. Test rollback cuối transaction

Dù đã flush nhiều chunks, nếu có exception buộc toàn transaction rollback thì DB phải không giữ những rows từ transaction đó.

Không nhầm `flush/clear` với chunk commits.

### 30.3. Test per-chunk commit là một contract khác

Nếu 3 chunks được commit ở 3 transactions, chunk 1 và 2 có thể vẫn tồn tại khi chunk 3 thất bại. Test cần kiểm tra checkpoint/resume và idempotency, không mong all-or-nothing cho toàn batch.

---

## 31. Test optimistic locking khi batch updates

Một test provider-specific cần:

- Entities có `@Version`.
- Hai transactions đọc cùng entity version.
- Transaction A update và commit.
- Transaction B có stale version, cố flush/commit.
- Assert optimistic conflict theo provider.
- Verify database state từ context mới.
- Không để batching che/version bypass conflict.

Đây là bài kiểm tra **correctness của optimistic locking** có hoặc không có batching.

### 31.1. Không đếm updated rows thay cho optimistic guarantee

Driver may report batch counts khác nhau; provider phải thực thi version checks phù hợp. Dùng test competing transactions để chứng minh state không bị ghi đè sai.

### 31.2. Nếu conflict xảy ra

Rollback/discard failed persistence context; muốn retry thì reload entity trong new transaction. Không tiếp tục `flush` cùng context đã lỗi.

---

## 32. SQL constraints và failure attribution trong batch

Khi 100 records được batch và record số 73 trùng unique key:

- Exception có thể là JDBC `BatchUpdateException`/provider wrapper.
- Driver có thể có `getUpdateCounts()`, `getNextException()`.
- Hibernate có thể bọc trong `ConstraintViolationException`.
- Transaction có thể rollback-only.
- Việc tìm record lỗi có thể không đơn giản như khi insert từng row.

### 32.1. Chia chunk vì operational recovery

Nếu yêu cầu báo lỗi chính xác từng row, có thể import qua staging table hoặc chunks có error tracking.

### 32.2. Không chạy SQL chẩn đoán trong failed transaction

Ở PostgreSQL, sau SQL error transaction có thể aborted. Phải rollback trước khi query kiểm tra tiếp, hoặc dùng context/transaction mới.

### 32.3. Nói rõ contract partial success

Một import có thể chọn:

- All-or-nothing toàn file.
- Commit theo chunk.
- Per-row independent operations.
- Conflict-ignore theo chính sách.
- Staging + validation + publish.

JDBC batching không quyết định thay những lựa chọn nghiệp vụ đó.

---

# Phần V — Tình huống vận hành

## 33. Khi bật batch mà throughput không cải thiện

Các nguyên nhân thường gặp:

| Quan sát | Nguyên nhân khả dĩ | Điều tra |
| --- | --- | --- |
| Batch size 50 nhưng không có batch JDBC | IDENTITY/driver/config không hiệu lực | Kiểm tra ID strategy, JDBC instrumentation |
| Batch executions nhỏ | SQL shape xen kẽ | order_inserts, dynamic SQL |
| Ghi chậm dù batch hoạt động | Index/constraint/IO/locks | DB execution metrics |
| Heap tăng mạnh | L1 giữ quá nhiều managed entities | Chunk flush/clear |
| Nhiều SELECT trong insert flow | Sequence/lookup/validation/associations | SQL breakdown |
| `saveAll` vẫn rất chậm | Transaction boundaries hoặc generated IDs | Service transaction/driver |
| Batch tốt nhưng commit rất lâu | Transaction lớn, WAL/constraints/locks | DB wait/commit latency |
| Batch update vẫn N SELECT | Load từng entity theo ID | Fetch plan/DTO/bulk alternative |
| `@BatchSize` không giảm INSERT | Annotation dành cho fetch | Dùng write batching settings |
| SQL log vẫn thấy N INSERT | Logs hiển thị ORM statements | Đếm JDBC executeBatch |
| Versioned updates không batch như kỳ vọng | Driver/provider version row-count handling | Test versioned behavior |
| Deadlocks tăng khi batch lớn | Lock duration/ordering | Đo lock wait, giảm chunk/batch |

### 33.1. Hệ số lớn nhất có thể không nằm ở batching

Ví dụ workload 10.000 rows có 20 indexes và nhiều triggers, database vẫn phải bảo trì tất cả indexes/triggers dù JDBC batching giảm protocol overhead.

Batching không loại chi phí CPU/IO per row ở database.

### 33.2. Database connection pool không tự batch

Tăng HikariCP pool size không có nghĩa mỗi connection sẽ gom nhiều INSERTs. Pool size giải quyết concurrency/connection reuse, không phải JDBC batch construction.

### 33.3. Driver rewrite options là layer khác

Một số drivers cung cấp parameter để rewrite batched INSERTs; cần đối chiếu tài liệu driver version. Bật option không thuộc JPA guarantee và có thể ảnh hưởng SQL shape/returning/generated key behavior.

---

## 34. Khi nào cân nhắc JDBC/native bulk thay vì entity persistence?

JPA entity persistence phù hợp khi:

- Cần lifecycle/cascade/managed relationships.
- Cần dirty checking.
- Cần optimistic locking theo entity.
- Cần domain methods/validation.
- Số records vừa phải hoặc batching đã đủ.

JDBC/native bulk thích hợp hơn khi:

- Ingestion rất lớn và mapping overhead chiếm ưu thế.
- Không cần per-entity callbacks.
- Dữ liệu có schema ổn định.
- Muốn dùng database-specific multi-row INSERT/COPY/bulk loader.
- Có thể kiểm soát transaction, idempotency và error handling riêng.

### 34.1. PostgreSQL COPY là cơ chế khác

`COPY` có thể hiệu quả cho bulk data loading nhưng **không phải JPA `persist` batching**. Nó có constraints/transaction semantics riêng và cần test domain rules.

### 34.2. Native SQL không mặc định an toàn hơn

Native bulk operations có thể:

- Bypass entity lifecycle.
- Làm stale persistence context.
- Bỏ qua application domain validation.
- Cần handle versioning/caching thủ công.
- Gắn chặt database dialect.

Chỉ đổi approach khi đã xác định bottleneck và correctness implications.

---

## 35. Bảng phân biệt chuẩn JPA, Hibernate và database

| Vấn đề | JPA standard | Hibernate/provider | JDBC/DB |
| --- | --- | --- | --- |
| Entity lifecycle `persist/remove` | Có hợp đồng | Implement | N/A |
| Dirty checking managed state | Có semantics | Thuật toán triển khai | SQL |
| `flush()` | Có API và semantics | Chọn SQL generation/order | Thực thi trong transaction |
| `FlushModeType.AUTO/COMMIT` | Có | Chiến lược cụ thể | N/A |
| Transaction commit/rollback | JPA/JTA integration | Phối hợp resource | Database ACID |
| Batch size setting | **Không bắt buộc** | `hibernate.jdbc.batch_size` | JDBC supports batching API |
| Reorder INSERT/UPDATE | **Không hứa thứ tự SQL** | order_inserts/order_updates | Thứ tự driver/DB |
| Identity/sequence generation | Mapping API | Chọn optimizer/SQL | IDENTITY/SEQUENCE support |
| JDBC `addBatch/executeBatch` | Không expose trực tiếp | Có thể gọi | JDBC API |
| Physical network RTT | Không hứa | Phụ thuộc thực thi | Driver/protocol/network |
| Multi-row INSERT rewrite | Không hứa | Có thể phụ thuộc | Driver/dialect |
| Unique/FK/CHECK enforcement | Mapping metadata | Có thể generate DDL | DB ràng buộc thật |
| Optimistic locking | Có contract | Version check implementation | UPDATE counts/constraints |
| SQL log format | Không quy định | Provider logging | Driver/DB logs |
| `@BatchSize` | Không phải JPA standard | Batch fetching | SELECT optimization |

**Không được ghi một provider-specific benchmark thành “JPA specification guarantees X batches”.**

---

# Phần VI — Bài tập thực hành và lời giải

## 36. Các tình huống

### Bài 1. Một nghìn lần persist có nghĩa một nghìn INSERT ngay?

**Đáp án:** Không. Provider có thể trì hoãn SQL, gửi sớm vì ID generation hoặc tạo nhiều SQL per entity. JPA không cam kết thời điểm/chính xác số statements.

### Bài 2. `flush()` có commit không?

**Đáp án:** Không. Flush đồng bộ pending changes trong transaction; rollback có thể hủy chúng.

### Bài 3. `hibernate.jdbc.batch_size=50` có phải thuộc JPA không?

**Đáp án:** Không. Đây là Hibernate-specific configuration.

### Bài 4. `saveAll(1_000 items)` có bảo đảm batch JDBC không?

**Đáp án:** Không. Spring Data API xử lý nhiều entities; batching tùy provider/driver/ID strategy.

### Bài 5. `saveAllAndFlush` có phải một transaction commit không?

**Đáp án:** Không. Flush không đồng nghĩa commit.

### Bài 6. Dùng IDENTITY khiến batch INSERT không hoạt động

**Đáp án:** Với nhiều cấu hình Hibernate, IDENTITY buộc INSERT sớm để lấy ID và hạn chế batching. Kiểm tra provider/version, không coi đó là luật portable JPA.

### Bài 7. `allocationSize=50` có nghĩa JDBC batch 50?

**Đáp án:** Không. Allocation là tối ưu identifier generation.

### Bài 8. SQL log hiển thị 100 INSERT lines

**Đáp án:** Không thể kết luận 100 network round trips. Dùng JDBC instrumentation để đo `addBatch/executeBatch`.

### Bài 9. Hibernate Statistics EntityInsertCount=1000

**Đáp án:** Không đồng nghĩa có 1.000 JDBC executions.

### Bài 10. Một JDBC executeBatch có chắc một network RTT không?

**Đáp án:** Không. Driver/protocol có thể thực thi khác nhau.

### Bài 11. Gọi flush sau từng persist

**Đáp án:** Có thể phá cơ hội batching vì mỗi flush buộc đồng bộ sớm.

### Bài 12. Flush/clear mỗi 50 rows

**Đáp án:** Giúp kiểm soát persistence context memory và flush windows; không tạo 50-row transactions.

### Bài 13. Record cuối bị lỗi sau 10 lần flush trong cùng transaction

**Đáp án:** Nếu rollback toàn transaction, các rows đã flush vẫn chưa committed và có thể bị rollback.

### Bài 14. Bật `@BatchSize(size=20)` trên collection

**Đáp án:** Đó là batch fetching, không phải JDBC write batching.

### Bài 15. DynamicUpdate làm SQL shapes khác nhau

**Đáp án:** Có thể giảm grouping opportunities; đánh giá tradeoff giữa ít cột cập nhật và prepared statement reuse.

### Bài 16. Order có 20 OrderLines, gọi persist một lần

**Đáp án:** Cascade có thể tạo nhiều entity INSERTs và SQL dependencies.

### Bài 17. Hibernate reorder INSERTs

**Đáp án:** Không dựa vào SQL log order để biểu đạt business event sequence; provider có quyền tối ưu trong giới hạn correctness.

### Bài 18. Bật order_updates để giảm deadlock?

**Đáp án:** Có thể giúp trong một số workloads nhờ lock ordering, nhưng không loại mọi deadlock và cần đo tradeoffs.

### Bài 19. Batch UPDATE versioned entities

**Đáp án:** Provider phải bảo toàn optimistic locking semantics; batch support/row counts phụ thuộc driver/provider.

### Bài 20. Một entity không dirty

**Đáp án:** Provider có thể không cần UPDATE; dirty checking không giống JDBC batching.

### Bài 21. Gọi em.find cho từng ID rồi update

**Đáp án:** Batch UPDATE có thể vẫn phải trả chi phí nhiều SELECTs; cần đo đầy đủ.

### Bài 22. Dùng bulk JPQL UPDATE để thay updates từng entity

**Đáp án:** Có thể tạo ít SQL hơn nhưng bypass lifecycle/dirty checking và có thể làm L1 stale.

### Bài 23. Batch DELETE có FK dependencies

**Đáp án:** SQL order phải đáp ứng constraints; không gom tùy ý mọi deletes.

### Bài 24. Một JDBC batch gặp unique violation

**Đáp án:** Không dùng partial update counts làm rows committed. Rollback/close failed context và chọn chunk retry/error handling policy.

### Bài 25. Chunk commit từng 500 records

**Đáp án:** Có partial success across chunks. Khác với flush/clear chunks trong một transaction.

### Bài 26. Test portable assert đúng ba JDBC batches

**Đáp án:** Sai phạm vi. JPA không đảm bảo batch count; assertion đó chỉ phù hợp provider-specific test được cấu hình rõ.

### Bài 27. PostgreSQL COPY có phải JPA batching?

**Đáp án:** Không. Đó là DB-specific bulk import path.

### Bài 28. Transaction bị rollback sau nhiều flushes

**Đáp án:** Database không giữ committed rows của transaction rollback; Java objects có thể vẫn mang state đã mutate.

### Bài 29. `GenerationType.AUTO` trên nhiều databases

**Đáp án:** Provider/dialect có thể chọn key strategy khác, làm batchability khác nhau.

### Bài 30. Batch size tăng nhưng p95 latency tệ hơn

**Đáp án:** Lớn hơn không luôn tốt hơn; đo transaction length, locks, memory, JDBC/DB timings.

### Bài 31. JDBC driver rewrite batch thành multi-row SQL

**Đáp án:** Driver optimization, không phải JPA contract. Test trên driver/version đang dùng.

### Bài 32. Một câu UPDATE ảnh hưởng 1000 rows

**Đáp án:** Đó có thể là bulk SQL, không đồng nghĩa 1000 JPA managed entity UPDATEs được JDBC batch.

### Bài 33. Email gửi trong @PostPersist của batch import

**Đáp án:** Có thể gửi trước DB commit; rollback không thu hồi email. Dùng transaction-aware design/outbox.

### Bài 34. Retry batch sau commit mất kết nối

**Đáp án:** Commit outcome có thể unknown. Dùng idempotency/reconciliation, không retry mù.

### Bài 35. Có nên tăng connection pool để thay batching?

**Đáp án:** Không. Pool điều phối connections/concurrency, batching gom operations ở JDBC layer.

---

## 37. Checklist trước khi kết luận “JPA đã batch ghi”

1. Có phân biệt `persist`, flush, commit và JDBC batch chưa?
2. Provider thực tế là Hibernate/EclipseLink/khác?
3. Provider/version/dialect đã được ghi lại?
4. Cấu hình batch size có thật sự có hiệu lực?
5. ID generation dùng IDENTITY, SEQUENCE hay AUTO?
6. Sequence allocation/optimizer có khớp DB migration?
7. Có đúng một transaction bao các operations muốn batch?
8. Có flush quá thường xuyên không?
9. `clear()` có làm detach entities còn cần dùng không?
10. Memory của L1 có tăng mất kiểm soát?
11. Có nhiều SQL shapes khác nhau không?
12. Có dùng DynamicInsert/DynamicUpdate ảnh hưởng grouping không?
13. Có nhiều entity types xen kẽ không?
14. `order_inserts`/`order_updates` có phù hợp không?
15. Có foreign key/cascade dependencies không?
16. Generated IDs có buộc SQL sớm không?
17. Versioned updates có được provider/driver hỗ trợ batch đúng?
18. Hibernate `@BatchSize` có bị hiểu nhầm là write batching không?
19. `saveAll` có bị coi là JDBC batch guarantee không?
20. Có instrumentation thấy `addBatch/executeBatch` thực tế không?
21. SQL logs có bị coi là network round trip count không?
22. Hibernate statistics có bị đọc nhầm thành JDBC batch count không?
23. Có đo rows committed sau commit bằng context mới không?
24. Có test rollback khi batch gặp constraint failure không?
25. Có test optimistic locking khi batching bật không?
26. Có phân biệt flush chunks và commit chunks không?
27. Có kế hoạch partial success/error reporting cho import?
28. Có idempotency nếu retry transaction không?
29. Có đo throughput, p95, memory và lock waits cùng nhau không?
30. Có benchmark với đúng JDBC driver/DB engine production không?
31. Có tránh dựa vào SQL execution order cho nghiệp vụ không?
32. Có kiểm soát events/audit/side effects bên ngoài transaction không?
33. Có đánh giá phương án bulk JPQL/JDBC/COPY và correctness implications không?
34. Có ghi rõ đâu là JPA contract và đâu là provider behavior không?

---

## 38. Sơ đồ lựa chọn chiến lược ghi

```text
                Cần ghi nhiều records
                         |
                         v
             Cần per-entity lifecycle/
             cascade/optimistic checks?
                  /             \
                Có               Không hoặc ít
                |                     |
                v                     v
            JPA entity          Cân nhắc bulk JPQL,
            persistence         JDBC/native/COPY
                |                     |
                v                     v
       Kiểm tra key strategy    Kiểm tra transaction,
       SEQUENCE / IDENTITY      cache/lifecycle semantics
                |
                v
       Provider batching supported?
           /              \
         Có                Không
         |                   |
         v                   v
   Configure provider     Chọn ID strategy/
   + JDBC instrumentation  approach khác nếu cần
         |
         v
   Flush/clear theo chunk hợp lý
         |
         v
   Đo JDBC batch executions,
   rows committed, latency/locks/memory
         |
         v
   Correctness + performance verified
```

**Mục tiêu cuối cùng không phải đạt một con số JDBC batches đẹp, mà là ghi dữ liệu đúng, có hiệu năng tốt và có thể phục hồi khi gặp lỗi.**

---

## 39. Tổng kết

Có hai lớp hợp đồng cần tách biệt.

**Lớp 1 — chuẩn Jakarta Persistence:**

- `persist()` đưa entity vào lifecycle được quản lý.
- Dirty checking theo dõi thay đổi managed state.
- `flush()` đồng bộ pending changes.
- Transaction `commit()`/`rollback()` xác định outcome.
- Mapping, relationships, cascades và optimistic locking có semantics chuẩn.
- JPA **không hứa SQL count, SQL execution order hay JDBC batch size cụ thể**.

**Lớp 2 — provider/JDBC/driver optimization:**

- Hibernate có thể dùng `hibernate.jdbc.batch_size`, `order_inserts` và `order_updates`.
- Generated key strategy, SQL shape và flush windows ảnh hưởng khả năng gom statements.
- JDBC `addBatch()`/`executeBatch()` là API khác với EntityManager operations.
- JDBC driver có thể tối ưu protocol/rewrite SQL.
- Kết quả performance cần đo trên database và driver mục tiêu.

Những nguyên tắc quan trọng nhất:

1. **Một transaction không bằng một batch**.
2. **Một `flush` không bằng một `commit`**.
3. **Một `saveAll` không bảo đảm JDBC batching**.
4. **`allocationSize` không phải `batch_size`**.
5. **`@BatchSize` của Hibernate chủ yếu liên quan batch fetching, không phải write batching**.
6. **SQL log hiển thị N INSERTs không chứng minh N network round trips**.
7. **`IDENTITY` có thể hạn chế batching INSERT trong Hibernate; `SEQUENCE` thường thuận lợi hơn khi phù hợp**.
8. **`flush/clear` theo chunk có thể kiểm soát memory, nhưng không chia transaction nếu chỉ có một commit**.
9. **Optimistic locking, constraints và cascades phải đúng khi batching bật hoặc tắt**.
10. **Chỉ instrumentation ở JDBC/driver/DB mới cho bằng chứng về batching thực tế; không suy từ JPA API calls**.
11. **Retry sau batch failure phải dùng transaction/context mới và chính sách idempotency rõ ràng**.
12. **Benchmark phải đo rows committed, throughput, latency và resource usage cùng nhau**.

**Gom thao tác ghi là một quyết định tối ưu của provider và JDBC driver; bảo đảm của JPA nằm ở cách entity state được quản lý và đồng bộ đúng với giao dịch. Hiểu rõ ranh giới này giúp tối ưu hiệu năng mà không vô tình biến một hành vi riêng của Hibernate thành lời hứa của chuẩn JPA.**
