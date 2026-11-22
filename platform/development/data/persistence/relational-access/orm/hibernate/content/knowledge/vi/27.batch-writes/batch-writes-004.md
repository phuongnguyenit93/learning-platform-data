# Chiến lược sinh định danh ảnh hưởng thế nào đến gom INSERT trong Hibernate

## 1. Bài toán: lưu nhiều entity nhưng tốc độ rất khác nhau

Giả sử một hệ thống nhập hàng nhận 10.000 sản phẩm và cần ghi vào cơ sở dữ liệu. Code có thể trông rất đơn giản:

```java
for (Product product : incomingProducts) {
    entityManager.persist(product);
}
```

Nhưng thời gian thực thi không chỉ phụ thuộc số entity. Nó còn phụ thuộc vào **cách Hibernate tạo khóa chính (identifier)**, thời điểm cần biết giá trị ID, khả năng gom các INSERT ở tầng JDBC, thứ tự SQL và số lần trao đổi với database.

Hai entity có cùng cột nghiệp vụ, cùng số bản ghi, cùng transaction và cùng cấu hình `hibernate.jdbc.batch_size` có thể cho hiệu năng rất khác nếu một entity dùng `GenerationType.IDENTITY` còn entity kia dùng `GenerationType.SEQUENCE` với cấp phát ID theo nhóm.

**Trọng tâm của bài:** lựa chọn chiến lược sinh định danh có thể khiến Hibernate phải gửi từng INSERT riêng lẻ, hoặc cho phép Hibernate biết ID trước, trì hoãn INSERT tới flush và gom các lệnh cùng kiểu thành JDBC batches.

### 1.1. Phân biệt ba khái niệm

**Sinh định danh** (*identifier generation*) là cách entity có giá trị primary key, ví dụ từ identity column, database sequence, table generator, UUID hoặc do ứng dụng gán.

**Gom INSERT ở JDBC** (*JDBC insert batching*) là việc Hibernate đưa nhiều thao tác SQL có cấu trúc tương thích vào một nhóm gọi `PreparedStatement.addBatch()` rồi `executeBatch()`. Mục đích thường là giảm overhead và số lần trao đổi với database.

**Bulk insert dạng set-based** là cách database thực hiện một lệnh SQL cho nhiều dòng, ví dụ `INSERT INTO ... SELECT ...` hoặc một câu `INSERT ... VALUES (...), (...), ...`. Nó không đồng nghĩa với JDBC batching. JDBC driver có thể tối ưu/rewrite batch thành dạng nhiều VALUES tùy cấu hình, nhưng ứng dụng không nên mặc định điều đó xảy ra.

Một cách ghi nhớ:

```text
Chiến lược ID
       |
       v
ID có biết trước INSERT không?
       |
       +-- Không, ID chỉ có sau INSERT -> có thể cần INSERT ngay
       |                                -> khó gom JDBC INSERT
       |
       +-- Có -> Hibernate có thể chờ flush
                 -> gom INSERT cùng SQL thành batches
```

Đây là sơ đồ khái niệm. Quyết định thực tế còn phụ thuộc Hibernate version, generator, dialect, flush mode, relationship graph và JDBC driver.

## 2. JDBC batching hoạt động ra sao?

### 2.1. Không phải cứ có 100 INSERT là Hibernate gọi database 100 lượt

Nếu JDBC batching được bật, Hibernate có thể chuẩn bị một statement INSERT rồi lần lượt đưa nhiều bộ tham số vào batch:

```java
PreparedStatement ps = connection.prepareStatement(
        "insert into products (id, sku, name) values (?, ?, ?)"
);

for (ProductData item : items) {
    ps.setLong(1, item.id());
    ps.setString(2, item.sku());
    ps.setString(3, item.name());
    ps.addBatch();
}

ps.executeBatch();
```

Đây là JDBC minh họa, không phải cách viết repository khi Hibernate đã quản lý persistence. Ý nghĩa là SQL text có thể giống nhau, còn giá trị bind khác nhau.

Trong Hibernate, cách thông thường là:

```java
for (Product product : products) {
    entityManager.persist(product);
}
```

Khi flush, Hibernate tổ chức các database operations theo action queue rồi có thể sử dụng JDBC batching nếu cấu hình và mapping cho phép.

### 2.2. Cấu hình cơ bản

Ví dụ cấu hình Hibernate:

```properties
hibernate.jdbc.batch_size=50
hibernate.order_inserts=true
```

- `hibernate.jdbc.batch_size=50`: cho phép Hibernate gom tối đa khoảng 50 thao tác JDBC tương thích trong một batch; đây không phải cam kết mọi batch đều đủ 50.
- `hibernate.order_inserts=true`: cho phép Hibernate sắp xếp INSERT để tăng khả năng gom các statement cùng kiểu, trong phạm vi các ràng buộc về thứ tự và quan hệ.
- Không cấu hình batch size hợp lệ lớn hơn 0 thì không thể kỳ vọng cơ chế JDBC batching thông thường tự hoạt động.
- Với một số môi trường, thuộc tính được truyền dưới dạng `jakarta.persistence.jdbc.*` hay Hibernate properties trong `persistence.xml`; tên batch size vẫn là thuộc tính Hibernate.

Ví dụ `persistence.xml`:

```xml
<properties>
    <property name="hibernate.jdbc.batch_size" value="50"/>
    <property name="hibernate.order_inserts" value="true"/>
</properties>
```

Batch size cần chọn theo workload, driver, database, giới hạn statement và memory; 50 chỉ là giá trị ví dụ.

### 2.3. Batch cần các statement tương thích

Hibernate thường gom các thao tác có cùng SQL statement shape. Nếu queue luân phiên nhiều entity type:

```text
INSERT Product
INSERT Category
INSERT Product
INSERT Category
INSERT Product
```

khả năng gom có thể thấp hơn thứ tự:

```text
INSERT Product
INSERT Product
INSERT Product
INSERT Category
INSERT Category
```

`hibernate.order_inserts` có thể cải thiện điều này, nhưng không thể tự “vá” mọi generator IDENTITY hay mọi dependency FK.

### 2.4. Một batch có thể vẫn hiện nhiều dòng INSERT trong log

Khi bật `hibernate.show_sql`, người học có thể nhìn thấy hàng trăm dòng INSERT và kết luận không có batching. Kết luận này **chưa đủ cơ sở**: log SQL cho biết statement được thực thi/chuẩn bị, nhưng không nhất thiết hiện rõ mỗi lệnh `addBatch` và `executeBatch`. Muốn xác nhận batching cần đo JDBC execution/batch hoặc log cấp driver/datasource phù hợp.

## 3. Vì sao Hibernate cần biết ID?

Hibernate nhận dạng một entity managed thông qua entity type và identifier. Trong persistence context, ID cần được xác định để quản lý identity map, liên kết FK, cascade, flush ordering và trạng thái entity.

Ví dụ:

```java
PurchaseOrder order = new PurchaseOrder();
entityManager.persist(order);

OrderLine line = new OrderLine();
line.assignOrder(order);
entityManager.persist(line);
```

Nếu khóa chính `order.id` chỉ xuất hiện khi database thực hiện INSERT, Hibernate có thể phải INSERT order để lấy ID trước khi ghi các line chứa FK. Nếu ID đã được tạo trước (sequence preallocation, UUID hoặc assigned ID), Hibernate có thể xếp nhiều INSERT vào action queue rồi flush theo thứ tự phù hợp.

Điều này giải thích tại sao **thời điểm có identifier** thường ảnh hưởng trực tiếp tới thời điểm SQL INSERT phải được gửi.

## 4. GenerationType.IDENTITY: tiện nhưng thường phá vỡ JDBC INSERT batching

### 4.1. Cơ chế của IDENTITY

`IDENTITY` sử dụng cơ chế database sinh khóa ngay khi INSERT vào hàng, ví dụ identity column hoặc auto-increment.

Entity:

```java
import jakarta.persistence.*;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String code;

    protected PurchaseOrder() {}

    public PurchaseOrder(String code) {
        this.code = code;
    }

    public Long getId() { return id; }
}
```

DDL minh họa trên PostgreSQL:

```sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    code VARCHAR(100) NOT NULL
);
```

Với IDENTITY, Hibernate không biết ID chính xác cho tới khi database xử lý INSERT. Provider thường phải gửi INSERT sớm và nhận generated key thông qua JDBC hoặc cơ chế SQL của dialect.

### 4.2. Hành vi minh họa

```java
for (int i = 0; i < 100; i++) {
    entityManager.persist(
        new PurchaseOrder("PO-" + i)
    );
}
```

Dù đã bật:

```properties
hibernate.jdbc.batch_size=50
```

Hibernate trong cấu hình IDENTITY thông thường **không thể gom các INSERT sinh IDENTITY thành JDBC batch như các ID được biết trước**. Hướng dẫn Hibernate mô tả tình huống identifier generator kiểu IDENTITY khiến insert batching bị vô hiệu hóa cho các entity đó.

SQL có thể trông như:

```sql
INSERT INTO purchase_orders (code) VALUES (?);
-- Nhận generated id cho entity thứ nhất.

INSERT INTO purchase_orders (code) VALUES (?);
-- Nhận generated id cho entity thứ hai.

INSERT INTO purchase_orders (code) VALUES (?);
-- Tiếp tục...
```

Số INSERT vẫn là 100 và mỗi ID cần được nhận sau INSERT tương ứng. Không nên lấy batch size=50 rồi mặc định nghĩ Hibernate sẽ thực hiện hai JDBC batches.

### 4.3. “Gửi INSERT sớm” không có nghĩa mọi persist luôn INSERT ngay

Thời điểm SQL cụ thể có thể phụ thuộc trạng thái transaction, flush mode và Hibernate version. Một số tình huống có thể trì hoãn thao tác identity tới flush. Điều quan trọng hơn là **cơ chế phải thu ID sinh từ INSERT** thường ngăn Hibernate gom IDENTITY INSERT theo đường JDBC batching thông thường.

Đây là khuyến nghị về cơ chế Hibernate phổ biến, không phải tuyên bố mọi provider hoặc phiên bản sau này đều không thể hỗ trợ bất kỳ kỹ thuật insert-returning/batch nào.

### 4.4. AUTO_INCREMENT/IDENTITY phù hợp khi nào?

IDENTITY vẫn có ưu điểm:

- Schema dễ hiểu trên nhiều database.
- Database trực tiếp cấp khóa, không phải quản lý sequence object riêng ở những hệ thống không hỗ trợ sequence.
- Hợp với luồng ghi ít bản ghi mỗi transaction.
- Không cần cấu hình allocation pool và phối hợp sequence increment.

Nếu ứng dụng chỉ tạo một đơn hàng mỗi lần, chi phí thiếu batching có thể không đáng kể. Nếu import hàng trăm nghìn dòng, IDENTITY có thể là yếu tố giới hạn thông lượng.

### 4.5. order_inserts không sửa được hạn chế IDENTITY

Bật:

```properties
hibernate.order_inserts=true
hibernate.jdbc.batch_size=50
```

có thể giúp gom INSERT của entity khác có ID biết trước; nó **không khiến IDENTITY được sinh trước khi INSERT**. Vì thế không thể xem `order_inserts` là giải pháp thay thế cho generator phù hợp.

## 5. GenerationType.SEQUENCE: biết ID trước khi INSERT

### 5.1. Cơ chế cơ bản

Database sequence là đối tượng cấp số độc lập với việc INSERT row. Hibernate có thể gọi sequence để lấy ID **trước khi** ghi entity.

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "purchase_order_seq_gen"
    )
    @SequenceGenerator(
        name = "purchase_order_seq_gen",
        sequenceName = "purchase_order_seq",
        allocationSize = 50
    )
    private Long id;

    @Column(nullable = false)
    private String code;

    protected PurchaseOrder() {}

    public PurchaseOrder(String code) {
        this.code = code;
    }

    public Long getId() { return id; }
}
```

DDL PostgreSQL mang tính minh họa:

```sql
CREATE SEQUENCE purchase_order_seq
    START WITH 1
    INCREMENT BY 50;

CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    code VARCHAR(100) NOT NULL
);
```

**Lưu ý quan trọng:** ví dụ DDL trên minh họa cơ chế cấp phát nhóm với optimizer thích hợp. Cấu hình sequence increment, allocation size và optimizer phải tương thích với nhau. Không nên copy câu `INCREMENT BY 50` vào mọi database mà bỏ qua Hibernate schema generation/validation và generator configuration của dự án.

### 5.2. Dòng chảy xử lý

```text
Hibernate cần ID cho PurchaseOrder
            |
            v
Lấy hoặc cấp phát ID từ database sequence
            |
            v
Đã biết ID trong Java trước INSERT
            |
            v
persist(entity) -> đặt INSERT vào action queue
            |
            v
flush -> sắp xếp/gom INSERT theo batch
            |
            v
Database nhận các INSERT có ID đã bind
```

SQL minh họa:

```sql
-- Có thể có truy vấn lấy giá trị sequence.
SELECT nextval('purchase_order_seq');

-- INSERT có ID sẵn dưới dạng bind parameter.
INSERT INTO purchase_orders (id, code) VALUES (?, ?);
INSERT INTO purchase_orders (id, code) VALUES (?, ?);
INSERT INTO purchase_orders (id, code) VALUES (?, ?);
```

Hibernate có cơ hội gom các INSERT vì không cần đợi database trả lại ID từ từng INSERT.

### 5.3. SEQUENCE cho phép batching, nhưng không bảo đảm batching

Dùng SEQUENCE giải quyết một rào cản lớn: ID có thể được xác định trước INSERT. Tuy nhiên batching vẫn cần:

- `hibernate.jdbc.batch_size` được bật.
- Nhiều INSERT tương thích xuất hiện trong một khoảng flush.
- Driver/dialect và Hibernate batching được hỗ trợ.
- Không có generator/SQL đặc thù khác đòi thực thi từng row.
- Thứ tự entity/association cho phép nhóm statement hợp lý.

Nói chính xác là: **SEQUENCE thường tạo điều kiện thuận lợi cho JDBC INSERT batching**, không phải SEQUENCE tự động làm mọi insert thành một batch.

## 6. Sequence allocationSize: giảm chi phí lấy ID, không chỉ gom INSERT

### 6.1. allocationSize=1

Ví dụ:

```java
@SequenceGenerator(
    name = "order_seq",
    sequenceName = "order_id_seq",
    allocationSize = 1
)
```

Với cách cấp phát không gom ID, Hibernate thường phải truy vấn database sequence cho mỗi ID:

```text
Lấy ID 1 từ sequence
Lấy ID 2 từ sequence
Lấy ID 3 từ sequence
...
Sau đó INSERT có thể vẫn được JDBC batch
```

Vì ID được biết trước INSERT, **allocationSize=1 không tự vô hiệu hóa JDBC INSERT batching**. Nhưng nó thêm nhiều lần lấy ID từ database, có thể làm throughput kém dù phần INSERT đã được batch.

### 6.2. allocationSize lớn hơn 1

Ví dụ:

```java
@SequenceGenerator(
    name = "order_seq",
    sequenceName = "order_id_seq",
    allocationSize = 50
)
```

Hibernate có thể dùng **pooled optimizer** để lấy một phần giá trị từ sequence, rồi cấp phát nhiều ID trong JVM từ pool. Trong một cấu hình được phối hợp đúng, 100 entity có thể cần khoảng hai lần cấp phát block thay vì 100 lần `nextval`.

Đây là **minh họa định tính**: số lần gọi sequence chính xác phụ thuộc optimizer (`pooled`, `pooled-lo`...), giá trị sequence ban đầu, trạng thái pool, phiên bản Hibernate và số instance ứng dụng.

### 6.3. Hai lớp batching độc lập

Giả sử có 100 order:

- Batch size JDBC: 25.
- Sequence allocation size: 50.
- Entity insert SQL tương thích.
- Không có association đặc biệt cắt batch.

Đường thực thi khái niệm:

```text
100 entity
  |
  +-- Lấy ID:
  |      dùng pooled sequence, ~2 lần cấp phát block
  |
  +-- INSERT:
         ~4 JDBC batches, mỗi batch tối đa 25 rows
```

**Đừng đồng nhất allocationSize với jdbc.batch_size**:

- `allocationSize` điều khiển **cấp phát ID**.
- `hibernate.jdbc.batch_size` điều khiển **gom thao tác JDBC**.

Có thể cấu hình `allocationSize=50` nhưng `jdbc.batch_size=0`: ít lần lấy ID nhưng INSERT không được batch. Ngược lại, `allocationSize=1` và `jdbc.batch_size=50`: INSERT có thể được batch, nhưng mỗi entity vẫn cần lấy ID riêng.

### 6.4. Pooled optimizer và sequence increment

Các optimizer như pooled hoặc pooled-lo giữ các nhóm ID trong JVM. Để tránh cấp trùng ID, trình sinh ID của Hibernate và database sequence phải thống nhất cách nhảy giá trị.

Một mapping:

```java
@SequenceGenerator(
    name = "order_seq_gen",
    sequenceName = "order_id_seq",
    allocationSize = 50
)
```

không nên được ghép tùy tiện với sequence đã tồn tại có `INCREMENT BY 1` rồi giả định mọi chiến lược đều an toàn. Hibernate có cơ chế kiểm tra mismatch trong nhiều cấu hình; schema validation có thể báo lỗi, hoặc generator cần được cấu hình phù hợp.

Khi quản lý database bằng Flyway/Liquibase, hãy đồng bộ DDL sequence, allocationSize và optimizer. Khi có nhiều application instances, chúng phải sử dụng chiến lược tương thích để mỗi instance có vùng ID không trùng nhau.

### 6.5. Gaps là bình thường

Khi JVM cấp trước block 50 ID nhưng chỉ dùng 13 rồi crash, các ID còn lại trong block có thể bị bỏ. Sequence database nói chung cũng có thể tạo gaps do rollback hoặc caching. **Primary key không phải dãy số liên tục để hiển thị cho khách hàng**.

Nếu nghiệp vụ yêu cầu số chứng từ không bỏ số, hãy thiết kế một cơ chế numbering riêng theo yêu cầu pháp lý/nghiệp vụ; không lạm dụng primary key generator để bảo đảm tính liên tục.



## 7. GenerationType.TABLE: có thể cấp ID trước nhưng thường gây thêm contention

Khi không có database sequence, Jakarta Persistence hỗ trợ table generator: dùng một bảng để lưu giá trị cấp ID.

Ví dụ:

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(
        strategy = GenerationType.TABLE,
        generator = "order_table_gen"
    )
    @TableGenerator(
        name = "order_table_gen",
        table = "id_generators",
        pkColumnName = "generator_name",
        valueColumnName = "next_value",
        pkColumnValue = "purchase_order",
        allocationSize = 50
    )
    private Long id;

    private String code;
}
```

Bảng generator có thể chứa:

| generator_name | next_value |
|---|---:|
| purchase_order | 1501 |
| invoice | 801 |

Hibernate cần đọc/cập nhật giá trị cấp ID trong bảng này theo một cơ chế đồng bộ/locking phù hợp. Với nhiều thread hoặc nhiều node cùng xin ID, bảng generator có thể trở thành điểm tranh chấp.

### 7.1. TABLE có làm JDBC INSERT batching được không?

Có thể: vì Hibernate thường xác định ID thông qua bảng generator trước khi INSERT entity. Do đó các INSERT nghiệp vụ **có thể** được gom JDBC batch.

Tuy nhiên, tổng thông lượng còn bị ảnh hưởng bởi việc lấy ID:

- SELECT/UPDATE hoặc thao tác khóa trên generator table.
- Transaction/lock contention.
- Số lần cấp phát block.
- Tải hệ thống khi nhiều instance đồng thời.

`allocationSize` lớn có thể giảm số lần chạm bảng generator, nhưng không xóa hoàn toàn contention. Nếu database có native sequence, sequence thường là lựa chọn tốt hơn cho workload ghi lớn.

### 7.2. TABLE không giống bảng nghiệp vụ

`id_generators` chỉ quản lý giá trị cấp phát ID, không phải bảng order. Việc batch INSERT vào `purchase_orders` không biến các thao tác cập nhật generator table thành một batch giống nhau.

## 8. UUID hoặc ID do ứng dụng tạo: biết định danh trước INSERT

### 8.1. UUID được sinh trước khi ghi

Jakarta Persistence 3.1 đưa ra `GenerationType.UUID`; Hibernate cũng có công cụ riêng như `@UuidGenerator` tùy phiên bản.

Ví dụ:

```java
@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(nullable = false, unique = true)
    private String sku;
}
```

Trong cách sinh UUID ở ứng dụng phổ biến, ID có thể xác định trước INSERT, nên Hibernate có thể gom JDBC INSERT nếu các điều kiện batching khác được thỏa.

**Không suy luận rằng bất kỳ cột UUID nào cũng mặc nhiên batch được.** Nếu UUID thật sự chỉ được tạo trong database tại thời điểm INSERT thông qua default function và Hibernate cần đọc lại generated key, cơ chế có thể giống một dạng ID phát sinh sau INSERT. Phải xem generator thực tế.

### 8.2. Assigned ID: ứng dụng tự gán ID

```java
@Entity
@Table(name = "warehouse_items")
public class WarehouseItem {
    @Id
    private String id;

    private String sku;

    protected WarehouseItem() {}

    public WarehouseItem(String id, String sku) {
        this.id = id;
        this.sku = sku;
    }
}
```

```java
WarehouseItem item = new WarehouseItem("WH-00001", "SKU-123");
entityManager.persist(item);
```

Nếu ID đã được cung cấp, Hibernate không cần gửi INSERT để nhận khóa. Batching có thể hoạt động theo cấu hình.

Tuy vậy, assigned ID có trách nhiệm khác:

- Ứng dụng phải bảo đảm tính duy nhất và xử lý collision.
- Thứ tự ID và thiết kế index ảnh hưởng B-tree locality/fragmentation.
- ID nghiệp vụ có thể đổi hoặc chứa dữ liệu nhạy cảm; không nên gán làm PK chỉ vì muốn batch.
- Khi dùng repository API có cơ chế `merge`/`saveOrUpdate` để xác định entity tồn tại, có thể phát sinh SELECT không cần thiết; khi tạo mới rõ ràng, `persist` thường diễn đạt đúng ý nghĩa.

### 8.3. UUID ngẫu nhiên và hiệu năng index

UUID v4 ngẫu nhiên có thể tăng chi phí ghi index so với số nguyên tăng dần trong một số schema/index. UUID có tính thuận tiện khi tạo ở nhiều node độc lập nhưng có overhead lưu trữ và locality tùy database/type.

Cần xem mục tiêu tổng thể: **thêm khả năng JDBC batch không tự đảm bảo UUID nhanh hơn sequence pooled**. Nếu dùng UUID cho distributed IDs, hãy so sánh kích thước index, throughput INSERT, backup, replication và cách lưu UUID của database.

## 9. GenerationType.AUTO không phải lời hứa batching

`GenerationType.AUTO` để persistence provider lựa chọn chiến lược phù hợp. Với Hibernate, lựa chọn phụ thuộc loại identifier Java, dialect, generator mapping và phiên bản.

Ví dụ:

```java
@Id
@GeneratedValue(strategy = GenerationType.AUTO)
private Long id;
```

Không được kết luận chắc chắn AUTO sẽ luôn dùng IDENTITY, hoặc luôn dùng SEQUENCE, hoặc sẽ batch được trên mọi database. Để tối ưu insert throughput, hãy **xác nhận generator được chọn** thông qua mapping, metadata và SQL log.

Nếu cần kiểm soát rõ, cấu hình tường minh `SEQUENCE` trên database hỗ trợ sequence, cùng allocation size phù hợp. Không thay đổi AUTO sang SEQUENCE một cách mù quáng khi hệ thống đã có data/schema production; cần migration có kế hoạch.

## 10. So sánh các chiến lược

| Chiến lược ID | ID có trước INSERT? | Khả năng JDBC INSERT batching trong Hibernate | Điểm đánh đổi |
|---|---|---|---|
| `IDENTITY` | Thường không, cần INSERT để biết key | **Thường không** cho entity dùng identity generator | Đơn giản, nhưng hạn chế gom ghi |
| `SEQUENCE`, allocationSize=1 | Có, thường lấy sequence từng ID | **Có thể** | Thêm nhiều lượt lấy sequence |
| `SEQUENCE`, allocationSize lớn/pooled | Có, cấp phát theo block | **Có thể**, thường thuận lợi | Cần đồng bộ increment/optimizer; có gaps |
| `TABLE` generator | Có, từ bảng cấp ID | **Có thể** | Lock/contestion ở generator table |
| UUID tạo tại ứng dụng | Có | **Có thể** | Kích thước ID/index, tính cục bộ của key |
| Assigned ID | Có | **Có thể** | Ứng dụng chịu trách nhiệm cấp ID |
| `AUTO` | Tùy generator thực tế | **Tùy** | Phụ thuộc provider/dialect/version |

Bảng trên nói về cơ chế **JDBC INSERT batching với entity đang persist**, không phải tốc độ chung của từng loại PK trong mọi database.

## 11. Ví dụ định lượng: 100 INSERT, batch size 25

Giả sử có đúng 100 entity mới, một loại INSERT, một transaction, không có extra statements do cascade hoặc lifecycle. Đây là mô hình minh họa để thấy sự khác biệt, **không phải cam kết số database round-trips**.

| Mapping | Lấy ID trước INSERT | Thực hiện INSERT | Batch execution có thể quan sát |
|---|---|---|---|
| IDENTITY | ID nhận sau từng INSERT | 100 INSERT | Thường 100 thao tác insert không gom thành batch |
| SEQUENCE không pooled | Gần 100 lần xin sequence | 100 INSERT | Có thể khoảng 4 JDBC batches × 25 |
| SEQUENCE pooled, allocationSize=50 | Khoảng 2 lần cấp phát block trong điều kiện đơn giản | 100 INSERT | Có thể khoảng 4 JDBC batches × 25 |
| Assigned ID hoặc UUID sinh trước | Không cần xin ID từ database cho từng row | 100 INSERT | Có thể khoảng 4 JDBC batches × 25 |

**Điểm cần đọc đúng:**

- Tất cả vẫn tạo **100 rows**; JDBC batching không làm giảm số row phải INSERT.
- “4 batches” là 4 lần gửi nhóm JDBC theo cấu hình lý tưởng, không có nghĩa database chắc chắn nhận đúng bốn network packets.
- Driver có thể rewrite SQL batch hoặc giao tiếp với server theo cách riêng.
- Hibernate có thể cắt batch khi statement shape thay đổi, entity khác xen vào, hoặc flush boundaries thay đổi.
- Số lần cấp phát block của pooled sequence phụ thuộc pool/optimizer; không đưa con số 2 thành bất biến.
- Database và driver có thể có instrumentation khác nhau về prepared statements, execution calls và network round-trips.

## 12. Cấu hình Hibernate để thực sự có JDBC batching

Trong một persistence unit đơn giản:

```xml
<persistence-unit name="inventoryPU" transaction-type="RESOURCE_LOCAL">
    <provider>org.hibernate.jpa.HibernatePersistenceProvider</provider>

    <properties>
        <property name="hibernate.jdbc.batch_size" value="50"/>
        <property name="hibernate.order_inserts" value="true"/>
        <property name="hibernate.generate_statistics" value="true"/>
    </properties>
</persistence-unit>
```

Ví dụ XML chỉ làm nổi bật batching properties; một persistence unit thực tế cần datasource/JDBC connectivity, entity discovery hoặc class registration, dialect/schema management và các cấu hình khác tùy môi trường.

### 12.1. batch_size bao nhiêu là tốt?

Một số thường được dùng thử nghiệm là 20, 30, 50, 100, nhưng **không có một batch size tối ưu chung**:

- Batch nhỏ: ít memory hơn, nhiều lần gửi nhóm hơn.
- Batch lớn: có thể giảm overhead nhưng tăng memory, parameter handling và thời gian giữ tài nguyên.
- Row lớn/BLOB có thể khiến batch quá lớn kém hiệu quả.
- Driver/database có giới hạn và các tối ưu riêng.
- Một transaction có nhiều loại entity có thể tạo batch nhỏ hơn cấu hình.

Chọn giá trị qua benchmark có dữ liệu giống production.

### 12.2. Session-level batch size

Trong Hibernate 6, `Session` có thể có API như `setJdbcBatchSize(int)` để điều chỉnh batch size trên một session cụ thể, nếu phiên bản đang dùng hỗ trợ.

```java
Session session = entityManager.unwrap(Session.class);
session.setJdbcBatchSize(50);
```

Đây là API Hibernate-specific, không phải API chuẩn `EntityManager`. Chỉ sử dụng khi kiến trúc và version tương ứng; không cần nếu cấu hình batch size toàn cục đã phù hợp.

### 12.3. order_inserts và dependency FK

Bật `hibernate.order_inserts=true` có thể nhóm các INSERT theo entity type/PK để làm batch dài hơn. Tuy nhiên Hibernate vẫn phải bảo toàn thứ tự cần thiết do FK, cascade hoặc ràng buộc khác. Không giả định SQL sẽ được sắp xếp đúng theo thứ tự Java `persist`.

Nếu muốn đảm bảo một thứ tự nghiệp vụ cho số chứng từ hoặc audit, không dựa vào thứ tự action queue hay thứ tự generated ID thay cho transaction/business sequence.



## 13. Mẫu nhập hàng loạt với SEQUENCE pooled

### 13.1. Entity

```java
package com.example.inventory;

import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "inventory_items")
public class InventoryItem {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "inventory_item_id_gen"
    )
    @SequenceGenerator(
        name = "inventory_item_id_gen",
        sequenceName = "inventory_item_id_seq",
        allocationSize = 50
    )
    private Long id;

    @Column(nullable = false, unique = true)
    private String sku;

    @Column(nullable = false, precision = 16, scale = 2)
    private BigDecimal price;

    protected InventoryItem() {}

    public InventoryItem(String sku, BigDecimal price) {
        this.sku = sku;
        this.price = price;
    }

    public Long getId() { return id; }
}
```

Nếu quản lý DDL thủ công, hãy tạo `inventory_item_id_seq` với increment/optimizer tương thích với cấu hình Hibernate. Tên sequence, dialect và schema có thể khác khi chạy trên H2, PostgreSQL, Oracle hoặc database khác.

### 13.2. Transaction và flush/clear theo cửa sổ

Ví dụ Java SE dùng resource-local transaction:

```java
public void importItems(
        EntityManagerFactory emf,
        List<ItemInput> inputs
) {
    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    final int flushWindow = 250;

    try {
        tx.begin();

        for (int i = 0; i < inputs.size(); i++) {
            ItemInput input = inputs.get(i);

            InventoryItem item = new InventoryItem(
                input.sku(),
                input.price()
            );

            em.persist(item);

            if ((i + 1) % flushWindow == 0) {
                em.flush();
                em.clear();
            }
        }

        em.flush();
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
```

DTO input:

```java
public record ItemInput(
        String sku,
        BigDecimal price
) {}
```

Ở ví dụ này:

- `hibernate.jdbc.batch_size=50` có thể gom INSERT thành các nhóm tối đa 50.
- `flushWindow=250` giới hạn số entity managed tích lũy trước khi flush/clear.
- Cứ 250 item, Hibernate flush các INSERT chưa thực thi rồi clear persistence context.
- Mọi INSERT vẫn nằm trong một transaction bao trùm cho tới `commit`.
- `em.flush()` sau vòng lặp xử lý số item cuối cùng không chia hết cho 250.
- `em.clear()` làm các entity trước đó thành detached; không tiếp tục thao tác trên chúng như entity managed nếu không chủ động reattach.

**flushWindow và batch_size là hai tham số khác nhau.** Đặt flushWindow=250 không có nghĩa Hibernate gom một JDBC batch 250. Khi batch_size=50, cửa sổ 250 item có thể chia thành nhiều JDBC batches nhỏ hơn.

### 13.3. Tại sao cần clear định kỳ?

Persistence context giữ các entity managed và snapshot để hỗ trợ dirty checking, cascade và identity map. Nếu persist 500.000 entity trong một transaction mà không clear, memory có thể tăng rất lớn ngay cả khi JDBC batching đang hoạt động.

`flush()` đẩy những thay đổi tới database; `clear()` giải phóng việc quản lý entity state trong context. Khi dùng parent-child association, cần cẩn trọng: clear parent sớm có thể làm các entity mới tham chiếu detached parent; chiến lược flush/clear phải phù hợp vòng đời object graph.

### 13.4. Flush không phải commit

`em.flush()` yêu cầu Hibernate đồng bộ SQL với database trong transaction; nó **không** tự commit. Nếu transaction rollback, các INSERT đã flush thường cũng rollback theo quy tắc transaction và database.

Nếu mục tiêu là chia commit thành nhiều transaction nhỏ để giảm transaction log/locks, đó là thiết kế khác, có đánh đổi về atomicity và partial failure. Không nhầm `flush/clear` với chia transaction.

### 13.5. Không nên kỳ vọng IDENTITY hưởng lợi như SEQUENCE

Đổi entity trên sang:

```java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
```

rồi giữ nguyên import loop, batch size, flush/clear vẫn **không loại bỏ nhu cầu nhận ID sau mỗi INSERT** của IDENTITY. Việc flush theo cửa sổ có thể giúp memory/lifecycle, nhưng không tự khôi phục JDBC INSERT batching cho identity generator.

## 14. Parent-child, cascade và thứ tự INSERT

### 14.1. Cha IDENTITY, con SEQUENCE

Ví dụ PurchaseOrder có nhiều OrderLine:

```java
@Entity
class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToMany(
        mappedBy = "purchaseOrder",
        cascade = CascadeType.PERSIST
    )
    private List<OrderLine> lines = new ArrayList<>();
}

@Entity
class OrderLine {
    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "order_line_gen"
    )
    @SequenceGenerator(
        name = "order_line_gen",
        sequenceName = "order_line_seq",
        allocationSize = 50
    )
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "purchase_order_id", nullable = false)
    private PurchaseOrder purchaseOrder;
}
```

Khi persist order và cascade lines, Hibernate thường phải biết `purchase_order.id` để bind FK cho các line. Nếu order dùng IDENTITY, nó có thể phải INSERT parent sớm; các INSERT của line dùng SEQUENCE vẫn **có khả năng** được batch nếu action queue có đủ statement cùng loại.

Điều này cho thấy batching phụ thuộc **từng entity mapping và quan hệ**, không chỉ một annotation trên aggregate root.

### 14.2. Cả cha và con SEQUENCE

Nếu cả hai đều được cấp ID trước INSERT, Hibernate có thể xếp action insert cho nhiều parent và child rồi thực hiện theo thứ tự FK an toàn. Bật `order_inserts` có thể cải thiện gom theo loại entity, nhưng mức độ còn phụ thuộc thứ tự và constraint.

Không được suy luận rằng hai entity có ID trước là có thể INSERT child trước parent trong mọi database. FK vẫn phải được bảo đảm.

### 14.3. Quan hệ hai chiều: nhớ owning side

```java
public void addLine(OrderLine line) {
    lines.add(line);
    line.setPurchaseOrder(this);
}
```

Bên `@ManyToOne` thường chứa FK và là owning side. Chỉ thêm vào inverse collection nhưng không đặt FK đúng có thể dẫn tới INSERT thiếu FK hoặc UPDATE bổ sung. Batching không sửa lỗi mapping quan hệ.

### 14.4. Cascades có thể xen kẽ nhiều statement shape

Một vòng lặp `persist(order)` có thể thêm Order, OrderLine, Shipment, AuditRecord... vào action queue. Mỗi entity có generator riêng, bảng riêng, constraints riêng. Một entity dùng IDENTITY ở giữa graph có thể buộc thực thi một phần SQL sớm hơn, tạo thêm ranh giới batch.

Tối ưu nên bắt đầu từ đo các statement thực tế của use case, không chỉ nhìn batch size trong cấu hình.

## 15. Các tình huống làm batch bị phân mảnh

### 15.1. INSERT vào bảng khác nhau

Hai statement:

```sql
INSERT INTO products (id, sku) VALUES (?, ?);
INSERT INTO categories (id, name) VALUES (?, ?);
```

không thể gom vào cùng một JDBC PreparedStatement batch vì SQL text khác nhau.

### 15.2. Dynamic insert

Nếu dùng `@DynamicInsert`, Hibernate có thể sinh SQL chỉ chứa các cột cần ghi với từng entity. Khi các entity có những tổ hợp cột null/giá trị khác nhau, SQL text có thể khác nhau, chia thành nhiều nhóm batch.

```java
@DynamicInsert
@Entity
class Product {
    // ...
}
```

Không tự bật `@DynamicInsert` vì nghĩ nó luôn giúp insert nhanh hơn. Nó có thể giảm số cột ghi nhưng làm số statement shape tăng, giảm hiệu quả batching. Cần benchmark theo dữ liệu thật.

### 15.3. Secondary tables và entity inheritance

Một entity mapping `@SecondaryTable` hoặc inheritance strategy có thể cần nhiều statement INSERT cho một logical entity. Các statement đó thuộc các bảng khác nhau và có thể có dependency. Batching có thể hoạt động từng nhóm tương thích nhưng không gộp mọi SQL thành một batch.

### 15.4. Flush giữa vòng lặp

```java
for (Product p : products) {
    em.persist(p);
    em.flush(); // Mỗi lần flush có thể cắt cơ hội gom nhiều INSERT.
}
```

Nếu mỗi flush chỉ có một INSERT cùng loại, batch size=50 vẫn không giúp tạo batch lớn. Hãy flush theo cửa sổ đủ lớn nếu memory và domain cho phép.

### 15.5. Query giữa các thao tác persist

Trong FlushMode.AUTO, một query có thể khiến Hibernate flush trước khi chạy để bảo đảm consistency theo query spaces/semantics. Nếu vòng lặp persist thỉnh thoảng chạy query, batch có thể được thực thi sớm.

Đừng thay flush mode bừa bãi để “né” SQL; flush mode là quyết định về tính đúng đắn của dữ liệu được query trong transaction.

### 15.6. Constraint, trigger và generated columns

Unique constraints, FK, triggers, generated columns hoặc insert-returning requirements có thể làm hiệu năng ghi khác nhau. Một batch thất bại có thể báo exception ở thời điểm `executeBatch`/flush/commit; vị trí row lỗi không phải lúc nào cũng rõ như INSERT từng row. Cần thiết kế transaction retry/idempotency và xử lý exception phù hợp.

## 16. Xác minh Hibernate có batch thật hay không

### 16.1. SQL log chỉ là dấu hiệu

Có thể bật trong môi trường phát triển:

```properties
hibernate.show_sql=true
hibernate.format_sql=true
hibernate.generate_statistics=true
```

Hoặc dùng logging backend cho các category Hibernate SQL/bind. Không bật log bind chứa PII/secrets trong production một cách vô điều kiện.

SQL log cho biết SQL nào xuất hiện; **nó không đủ để khẳng định mỗi nhóm JDBC batch đã thực thi như thế nào**.

### 16.2. Hibernate Statistics

Ví dụ:

```java
SessionFactory sessionFactory =
        entityManagerFactory.unwrap(SessionFactory.class);

Statistics stats = sessionFactory.getStatistics();
stats.setStatisticsEnabled(true);
stats.clear();

// Chạy use case nhập dữ liệu cần đo.

long insertedEntities = stats.getEntityInsertCount();
long preparedStatements = stats.getPrepareStatementCount();

System.out.println("entities inserted = " + insertedEntities);
System.out.println("prepared statements = " + preparedStatements);
```

`getEntityInsertCount()` cho thấy số entity được insert, không phải số JDBC batches. `getPrepareStatementCount()` là số prepared statements, cũng **không tự bằng số network round-trips hoặc executeBatch calls**. Với Hibernate version tương ứng, session metrics log có thể có thống kê thời gian/số batch thực thi; dùng datasource proxy/JDBC instrumentation để đếm `addBatch`/`executeBatch` khi cần chứng cứ chắc chắn.

Statistics cấp SessionFactory có thể bị nhiễu nếu request/test khác chạy song song; cô lập workload khi đo.

### 16.3. Đo đúng thứ cần đo

Một benchmark tốt nên ghi:

- Số entity mới và kích thước từng row.
- Generator strategy và allocationSize.
- Cấu hình `jdbc.batch_size`, `order_inserts`.
- Số sequence calls, INSERT statements, JDBC batch executions.
- Tổng thời gian transaction và throughput rows/s.
- Database CPU/IO, locks, WAL/redo log, connection pool.
- Batch sizes thực tế và số batch bị cắt do statement changes.
- Memory/GC và kích thước persistence context.

Chạy ít nhất hai cấu hình trên cùng máy/dataset, warm-up và reset dữ liệu phù hợp. Không so thời gian của 1.000 IDENTITY records trên database remote với 1.000 SEQUENCE records trên database embedded rồi kết luận do ID strategy.

### 16.4. Kiểm tra SQL của sequence

Với PostgreSQL, có thể thấy dạng:

```sql
select nextval('inventory_item_id_seq');
```

Nếu dùng non-pooled sequence, lệnh này có thể xuất hiện gần mỗi entity; với pooled optimizer, số lần gọi có thể ít hơn rõ rệt. SQL chính xác phụ thuộc dialect và Hibernate.

### 16.5. Test riêng từng mapping

Một integration test có thể tạo 200 entity ở mỗi strategy trong một transaction, flush, rồi dùng datasource proxy đếm:

1. INSERT statements được bind.
2. Số `executeBatch` và batch sizes.
3. Số lần truy cập sequence.
4. Thời gian thực hiện và memory.
5. Số rows cuối cùng trong database.

Khi test có cache hoặc nhiều thread, cần cô lập số liệu. Với IDENTITY, kỳ vọng thường là không thấy JDBC INSERT batching giống trường hợp SEQUENCE; nếu provider/driver có cơ chế đặc biệt, ghi nhận đó là đặc điểm của stack hiện tại.



## 17. Các giới hạn khi chuyển từ IDENTITY sang SEQUENCE

Đổi generator không chỉ là sửa annotation.

### 17.1. Database phải hỗ trợ sequence

Không phải database nào cũng hỗ trợ sequence theo cùng cách. Nếu dialect/database không hỗ trợ, `GenerationType.SEQUENCE` có thể không khả dụng theo kỳ vọng. `TABLE` hoặc assigned IDs có thể là lựa chọn khác, nhưng cần so trade-offs.

### 17.2. Đồng bộ sequence với dữ liệu hiện có

Giả sử bảng có ID lớn nhất là 5.000. Khi chuyển sang sequence, phải bảo đảm ID tiếp theo không trùng các giá trị đã dùng. Với PostgreSQL, thao tác điều chỉnh sequence có thể dựa trên `setval(...)`, nhưng script chính xác phụ thuộc tên sequence, increment, optimizer và dữ liệu đang ghi.

Không thực hiện migration theo giả định sequence bắt đầu từ 1 trên database đã có dữ liệu.

### 17.3. Đồng bộ allocationSize và DDL

Nếu mapping dùng `allocationSize=50`, DB sequence và optimizer phải phối hợp đúng. Hệ thống có nhiều node chạy phiên bản cũ/mới song song cần kế hoạch rollout an toàn; hai generator không tương thích có thể cấp ID trùng hoặc tạo lỗi xác thực schema.

### 17.4. Không xem primary key là số thứ tự nghiệp vụ

Sequence pooled có thể nhảy số, và ID được cấp trước INSERT không phản ánh thứ tự commit của transaction. Nếu cần số chứng từ theo quy định hoặc thứ tự nghiệp vụ, hãy thiết kế một trường riêng và quy trình cấp số đúng yêu cầu.

### 17.5. Tác động lên replication, trigger và ứng dụng khác

Nếu ứng dụng khác viết trực tiếp vào bảng bằng identity/default/trigger, cần đảm bảo chúng phối hợp cùng sequence strategy. Một hệ thống có cả Hibernate và ETL scripts cần một nguồn cấp ID nhất quán; không để client tự gán trong vùng có thể trùng với sequence.

### 17.6. Có nhất thiết đổi không?

Không. Với ứng dụng chủ yếu ghi 1–3 entity mỗi transaction, IDENTITY có thể đơn giản và đáp ứng SLA. Chỉ thay generator khi đo được bottleneck đáng kể, có kế hoạch migration và đã xét tác động tổng thể.

## 18. Bulk HQL, StatelessSession và JDBC batching là ba bài toán khác nhau

### 18.1. INSERT ... SELECT trong HQL

Hibernate hỗ trợ một số dạng HQL insert-select:

```hql
insert into ArchivedOrder (id, code)
select o.id, o.code
from PurchaseOrder o
where o.archived = true
```

Đây là thao tác set-based ở database, khác vòng lặp `em.persist(entity)` với JDBC batching. Nó có ràng buộc về entity target, identifier generation và cú pháp HQL theo Hibernate version; không phải phép thay thế tổng quát cho mọi import từ CSV/API.

Nếu cần copy dữ liệu giữa bảng, set-based SQL có thể phù hợp. Nếu cần thực thi domain events, entity callbacks hoặc kiểm tra từng object, phải xem lại semantics của bulk operation.

### 18.2. StatelessSession

Hibernate có `StatelessSession` cho các thao tác dữ liệu không cần persistence context thông thường. Nó có trade-offs: không có cùng dirty checking/cascades/event behavior như stateful Session, và hành vi batching phụ thuộc phiên bản/API.

**Không mặc định cho rằng dùng StatelessSession sẽ bỏ qua giới hạn IDENTITY hoặc tự batch mọi SQL.** Chọn nó sau khi xác nhận semantics, generator và JDBC operations trong stack hiện tại.

### 18.3. Native JDBC/driver-specific bulk loader

Với ETL khối lượng rất lớn, một database loader như PostgreSQL COPY hoặc driver bulk protocol có thể vượt throughput ORM persist loop. Đổi lại, bạn có thể bỏ qua entity lifecycle, cascades, validation và một số cơ chế ORM.

Lựa chọn phải dựa trên yêu cầu transaction, validation, audit, data integrity và throughput. Không đánh đồng “bulk loader nhanh hơn” với “Hibernate nên luôn bị bỏ qua”.

## 19. Trường hợp lỗi và cách khắc phục

| Hiện tượng | Nguyên nhân có thể | Việc cần làm |
|---|---|---|
| Đã đặt `batch_size=50` nhưng mỗi INSERT vẫn riêng | Entity dùng IDENTITY generator | Kiểm tra mapping và generated-key path; cân nhắc SEQUENCE/assigned nếu phù hợp |
| SEQUENCE nhưng insert chậm | Lấy ID từ sequence từng bản ghi | Xem allocationSize/optimizer và sequence calls |
| Bật pooled allocation nhưng startup lỗi validation sequence | DB increment không khớp mapping/optimizer | Đồng bộ migration DDL và mapping |
| Generator cấp ID trùng khi nhiều node | Các client dùng generator/sequence không tương thích | Đồng bộ chiến lược cấp ID trên toàn hệ thống |
| Batch size lớn nhưng batch thực tế nhỏ | SQL shape khác nhau, xen entity, flush giữa vòng | Xem order_inserts, dynamic insert, flush windows |
| Bật order_inserts nhưng IDENTITY không batch | ID vẫn chỉ có sau INSERT | Đổi chiến lược khi có cơ sở hiệu năng |
| TABLE generator chậm khi nhiều node | Lock/contention tại generator table | Cân nhắc database sequence pooled |
| Query count nhiều dù INSERT đã batch | Mỗi SEQUENCE ID cần một SELECT riêng | Dùng pooled allocation nếu hợp lệ |
| Memory tăng khi nhập nhiều entity | Persistence context giữ quá nhiều entity | Flush/clear theo cửa sổ phù hợp |
| Đã flush nhưng transaction rollback | Flush không phải commit | Kiểm tra transaction boundaries và retry |
| Batch lỗi khó xác định row | Driver trả BatchUpdateException khi executeBatch | Log ID nghiệp vụ, chunking và cơ chế retry |
| UUID batch nhưng index ghi kém | Random key locality/size | Benchmark UUID strategy và index layout |
| Giao diện hiển thị ID bị nhảy số | Sequence pooled/rollback/cache tạo gaps | Tách business number khỏi PK |
| AUTO cho hiệu năng khác giữa databases | Provider/dialect chọn generator khác | Cấu hình tường minh hoặc xác nhận mapping thực tế |
| SQL log vẫn hiện N dòng INSERT | Log statements không phản ánh trực tiếp executeBatch | Dùng JDBC proxy/statistics phù hợp |

## 20. Phương pháp chọn chiến lược cho một hệ thống

Nếu database có sequence và workload cần ghi nhiều entity mới trong mỗi transaction, **SEQUENCE kết hợp pooled allocation** thường là điểm xuất phát tốt để benchmark:

```properties
hibernate.jdbc.batch_size=50
hibernate.order_inserts=true
```

```java
@Id
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "item_seq_gen"
)
@SequenceGenerator(
    name = "item_seq_gen",
    sequenceName = "item_seq",
    allocationSize = 50
)
private Long id;
```

Cần bảo đảm DDL sequence/optimizer tương thích, vòng lặp persist có transaction và flush/clear được quản lý. Không chọn sequence chỉ vì muốn tránh gaps; primary key gaps là hiện tượng bình thường.

Nếu không có sequence, hãy so assigned ID, UUID generator hoặc TABLE với chi phí và ràng buộc riêng. Nếu throughput ghi thấp hoặc migration quá rủi ro, giữ IDENTITY cũng có thể đúng.

Quyết định dựa trên **workload đo được**, không dựa vào câu “IDENTITY luôn xấu, SEQUENCE luôn tốt”.

## 21. Bài tập thực hành

**Bài 1 — IDENTITY.** Tạo entity có `@GeneratedValue(IDENTITY)`; bật batch size 25, persist 100 bản ghi trong một transaction. Dùng JDBC proxy hoặc session metrics quan sát batch executions thay vì chỉ đếm dòng SQL log.

**Bài 2 — SEQUENCE không pooling.** Đổi sang `SEQUENCE` với `allocationSize=1` trên database hỗ trợ; lặp lại bài test. Đếm thêm số sequence calls.

**Bài 3 — SEQUENCE pooled.** Đổi `allocationSize=50`, đồng bộ DDL sequence increment/optimizer. Persist 100–1.000 entity. Đo số lần lấy block ID và số JDBC batch executions.

**Bài 4 — order_inserts.** Persist xen kẽ Product và Category có ID biết trước. So số batch khi bật/tắt `hibernate.order_inserts`; quan sát SQL shape.

**Bài 5 — flush window.** So flush mỗi row, flush mỗi 25 row và flush mỗi 250 row trong một transaction. Quan sát batching, memory và tổng thời gian.

**Bài 6 — IDENTITY trong graph.** Tạo Order IDENTITY và OrderLine SEQUENCE, persist theo cascade; xem khi nào parent phải INSERT và có gom child INSERT được không.

**Bài 7 — TABLE generator.** Tạo generator table với allocationSize 1 và 50, chạy nhiều thread; quan sát lock contention và compare với sequence nếu database hỗ trợ.

**Bài 8 — UUID.** Dùng `GenerationType.UUID` rồi benchmark với numeric pooled sequence. So insert batching, kích thước PK/index và performance.

**Bài 9 — AUTO.** Dùng `GenerationType.AUTO` trên hai dialect thử nghiệm; quan sát Hibernate chọn generator nào, không tự đoán.

**Bài 10 — Migration.** Lập kế hoạch chuyển một bảng đã có 5.000 rows từ IDENTITY sang SEQUENCE: đồng bộ sequence position, allocationSize, trigger/default, nhiều node và rollback plan.

**Bài 11 — Batch failure.** Tạo một row vi phạm unique constraint trong batch; quan sát thời điểm exception và cách rollback/retry đảm bảo không nhân đôi dữ liệu.

**Bài 12 — Bulk load alternative.** So JDBC batching với một lệnh set-based insert hoặc bulk loader của database trong môi trường thử nghiệm; ghi rõ những lifecycle ORM bị bỏ qua.

## 22. Câu hỏi tự kiểm tra

**1. Vì sao IDENTITY thường không batch INSERT trong Hibernate?**

Vì ID chỉ có sau khi INSERT; Hibernate thường phải gửi statement và nhận generated key trước khi tiếp tục quản lý entity.

**2. SEQUENCE khác IDENTITY ở điểm quyết định nào?**

Sequence có thể cấp ID trước khi INSERT, giúp Hibernate trì hoãn/gom INSERT.

**3. `allocationSize=1` có tự tắt JDBC batching không?**

Không. INSERT vẫn có thể batch, nhưng mỗi ID có thể cần một lượt lấy sequence riêng.

**4. `allocationSize=50` và `hibernate.jdbc.batch_size=50` có cùng ý nghĩa không?**

Không. Một cái cấp phát ID theo block; cái kia gom các thao tác JDBC.

**5. Dùng TABLE generator có thể batch không?**

Có thể vì ID được biết trước; nhưng generator table có thể tạo lock/contention.

**6. UUID tạo trong ứng dụng có thể batch INSERT không?**

Có thể, vì ID được biết trước; hiệu năng index lại là câu chuyện khác.

**7. Bật `order_inserts` có chữa hạn chế IDENTITY không?**

Không. Nó giúp nhóm statement tương thích chứ không sinh trước IDENTITY key.

**8. SQL log có 100 INSERT có chứng minh không batching không?**

Không. Cần quan sát JDBC batch executions hoặc driver instrumentation.

**9. Vì sao cần flush/clear định kỳ khi nhập hàng loạt?**

Để không giữ quá nhiều managed entities trong persistence context, đồng thời flush các lệnh thành nhóm có kiểm soát.

**10. Flush có đồng nghĩa commit không?**

Không. Flush thực thi SQL trong transaction; commit mới hoàn tất transaction.

**11. Primary key sequence có bảo đảm liên tục và theo thứ tự commit không?**

Không. Pooled blocks, cache, rollback, concurrency có thể tạo gaps và thứ tự khác commit.

**12. Khi nào không nên chuyển IDENTITY sang SEQUENCE?**

Khi database không hỗ trợ, migration có rủi ro hoặc workload ghi nhỏ khiến lợi ích không đáng chi phí, trừ khi có nhu cầu khác.

## 23. Ghi nhớ

- JDBC INSERT batching và chiến lược sinh ID liên quan nhau vì **thời điểm Hibernate biết identifier** quyết định khả năng trì hoãn INSERT.
- `IDENTITY` thông thường buộc Hibernate lấy ID sau INSERT và **ngăn gom INSERT bằng JDBC batching thông thường cho entity đó**.
- `SEQUENCE` có thể cấp ID trước INSERT, cho phép batching; `allocationSize` và pooled optimizer giảm riêng chi phí lấy ID.
- `allocationSize=1` không tự vô hiệu hóa INSERT batching nhưng có thể tạo nhiều sequence round-trips.
- `TABLE` và assigned/UUID ID có thể cho phép batching, song có những rủi ro riêng như contention, collision hoặc index locality.
- `AUTO` phụ thuộc generator mà Hibernate chọn; không suy luận batching chỉ từ chữ AUTO.
- Bật `hibernate.jdbc.batch_size` và cân nhắc `hibernate.order_inserts`, nhưng batching vẫn phụ thuộc SQL shape, flush boundaries, mapping quan hệ và driver.
- Flush/clear theo cửa sổ giúp kiểm soát persistence context, không phải commit và không tự khắc phục IDENTITY.
- SQL log hiển thị nhiều INSERT không đủ để kết luận batching; dùng JDBC instrumentation/Statistics và benchmark có kiểm soát.
- Chọn generator theo đặc tính database, migration safety, tính duy nhất, concurrency, throughput và yêu cầu nghiệp vụ; không chỉ nhìn một con số batch size.

### Tài liệu tham khảo

- [Hibernate ORM 6.6 User Guide — JDBC batching](https://docs.jboss.org/hibernate/orm/6.6/userguide/html_single/Hibernate_User_Guide.html#batch)
- [Hibernate ORM 6.6 User Guide — Identifiers](https://docs.jboss.org/hibernate/orm/6.6/userguide/html_single/Hibernate_User_Guide.html#identifiers)
- [Hibernate ORM 6.6 User Guide — Generated identifier values](https://docs.jboss.org/hibernate/orm/6.6/userguide/html_single/Hibernate_User_Guide.html#identifiers-generators)
- [Hibernate ORM 6.6 JavaDoc — SequenceStyleGenerator](https://docs.jboss.org/hibernate/orm/6.6/javadocs/org/hibernate/id/enhanced/SequenceStyleGenerator.html)
- [Hibernate ORM 6.6 JavaDoc — Optimizer](https://docs.jboss.org/hibernate/orm/6.6/javadocs/org/hibernate/id/enhanced/Optimizer.html)
- [Jakarta Persistence 3.1 Specification — Identifier generation](https://jakarta.ee/specifications/persistence/3.1/jakarta-persistence-spec-3.1)
- [PostgreSQL Documentation — Sequence manipulation](https://www.postgresql.org/docs/current/functions-sequence.html)

