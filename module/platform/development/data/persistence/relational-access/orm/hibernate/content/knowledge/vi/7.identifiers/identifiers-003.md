# So sánh chiến lược IDENTITY, SEQUENCE, TABLE và AUTO trong Hibernate

Khi lưu một thực thể mới bằng Hibernate, ứng dụng cần xác định **khóa chính (primary key)** để nhận diện bản ghi. Nếu khóa chính do hệ thống tự cấp, lập trình viên thường chỉ viết `@Id` và `@GeneratedValue` mà không trực tiếp tạo giá trị ID. Tuy nhiên, lựa chọn `GenerationType.IDENTITY`, `SEQUENCE`, `TABLE` hoặc `AUTO` ảnh hưởng đáng kể đến **thời điểm Hibernate nhận được ID**, **SQL gửi đến database**, **khả năng gom JDBC batch**, **mức độ phụ thuộc hệ quản trị cơ sở dữ liệu**, cũng như **hiệu năng khi chèn nhiều dòng đồng thời**.

Bốn chiến lược này thuộc API Jakarta Persistence (JPA), còn Hibernate là provider hiện thực chúng. Vì thế, cần phân biệt **cam kết ở mức annotation** với **cách Hibernate và database thực sự triển khai**. Một giá trị ID đã có trong Java không đồng nghĩa dữ liệu đã commit; một lệnh `persist()` cũng không nhất thiết tương ứng với đúng một `INSERT` được gửi ngay.

> **Phạm vi:** Các ví dụ sử dụng `jakarta.persistence` và cách hoạt động phổ biến của Hibernate ORM 6.x. Hibernate 5 dùng gói `javax.persistence`; các phiên bản, dialect và generator optimizer khác nhau có thể phát sinh SQL khác nhau. Những câu SQL minh họa chủ yếu dùng PostgreSQL và một ví dụ MySQL; cần kiểm tra mapping, cấu hình và DDL của đúng môi trường đang chạy.

## 1. Bốn chiến lược khác nhau ở điểm nào?

| Chiến lược | Nơi cung cấp ID | Hibernate thường biết ID vào lúc nào? | JDBC insert batching | Điểm cần chú ý |
|---|---|---|---|---|
| `IDENTITY` | Cột identity/auto-increment của bảng dữ liệu | Sau khi DB thực hiện `INSERT` sinh khóa | Thường bị hạn chế/không gom được insert entity dùng identity theo cách batching thông thường | Phụ thuộc hỗ trợ identity của DB; insert có thể diễn ra sớm để lấy ID. |
| `SEQUENCE` | Database sequence hoặc cơ chế tương đương mà generator hỗ trợ | Có thể biết **trước khi insert** bằng cách lấy giá trị từ sequence | Thường thuận lợi cho insert batching | Quan tâm `@SequenceGenerator`, `allocationSize` và optimizer/DDL sequence. |
| `TABLE` | Một bảng riêng chứa giá trị/bộ đếm ID | Có thể biết **trước khi insert**, sau khi generator truy cập bảng cấp ID | Có thể batch insert entity, nhưng generator table có chi phí riêng | Tranh chấp row/lock và round trip ở bảng cấp số khi tải ghi lớn. |
| `AUTO` | Provider tự chọn theo kiểu ID, dialect và cấu hình | **Phụ thuộc** chiến lược thực sự được chọn | **Phụ thuộc** generator được chọn | Tiện cho code đơn giản, nhưng hành vi không cố định giữa môi trường/provider. |

Ví dụ tổng quát:

~~~java
import jakarta.persistence.*;

@Entity
public class Invoice {
    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    // Các field còn lại ...
}
~~~

Đổi `SEQUENCE` thành `IDENTITY`, `TABLE` hoặc `AUTO` có thể giữ nguyên cách ứng dụng gọi `persist()`, nhưng sẽ thay đổi cách Hibernate xử lý việc cấp ID.

### ID do database cấp khác gì ID nghiệp vụ?

Khóa chính `id` thường là **surrogate key** dùng để liên kết các bảng và nhận diện entity. Mã đơn hàng hiển thị cho khách, số hóa đơn pháp lý, mã giao dịch hoặc mã có yêu cầu **không được mất số** thuộc các bài toán nghiệp vụ khác. Không nên sử dụng giá trị từ identity/sequence như bằng chứng một giao dịch đã commit, hoặc làm số thứ tự nghiệp vụ bắt buộc liên tục không có khoảng trống.

ID phải **duy nhất trong phạm vi khóa chính**, nhưng không nhất thiết tăng chính xác theo thứ tự commit, không bảo đảm liên tiếp và không mặc định có ý nghĩa thời gian.

## 2. Bức tranh luồng cấp ID và ghi SQL

~~~mermaid
flowchart TD
    A["Java: new Entity()"] --> B["entityManager.persist(entity)"]
    B --> C{"Chiến lược cấp ID"}
    C -- "IDENTITY" --> D["INSERT để DB sinh giá trị ID"]
    D --> E["Hibernate nhận ID từ JDBC/DB"]
    C -- "SEQUENCE" --> F["Lấy ID/khối ID từ sequence"]
    C -- "TABLE" --> G["Đọc/cập nhật bảng cấp số"]
    C -- "AUTO" --> H["Provider chọn generator"]
    H --> D
    H --> F
    H --> G
    F --> I["Đưa INSERT entity vào luồng flush"]
    G --> I
    I --> J["flush: có thể batch và gửi INSERT"]
    E --> K["Entity có ID trong persistence context"]
    J --> K
    K --> L["Transaction commit hoặc rollback"]
~~~

Sơ đồ chỉ là cách đọc kiến trúc: trong một số bối cảnh Hibernate có thể hoãn việc insert của `IDENTITY`; `SEQUENCE` có thể sử dụng optimizer cấp trước nhiều ID, và các thao tác SQL phục vụ generator có thể xuất hiện ở thời điểm khác nhau. `AUTO` không nhất thiết thử cả ba nhánh tại runtime: provider quyết định generator dựa vào metadata khi khởi tạo mapping.

Phân biệt ba mốc:

1. **Identifier được gán:** entity có giá trị `id` trong bộ nhớ.
2. **INSERT entity đã chạy:** DB đã nhận thao tác ghi, có thể mới trong transaction đang mở.
3. **Commit hoàn tất:** transaction xác nhận thao tác; dữ liệu mới trở thành phần dữ liệu đã commit.

Ví dụ `entity.getId() != null` chỉ chứng minh Hibernate đã có identifier; **không chứng minh bản ghi đã được commit**, đặc biệt rõ với `SEQUENCE` và `TABLE`.

## 3. Ngữ pháp chung của `@GeneratedValue`

Để Hibernate biết ID được sinh tự động, đặt `@GeneratedValue` cùng với `@Id`:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class Shipment {
    @Id
    @GeneratedValue(strategy = GenerationType.AUTO)
    private Long id;

    protected Shipment() {}
    public Long getId() { return id; }
}
~~~

`@GeneratedValue` có các thành phần thường dùng:

| Thuộc tính | Vai trò |
|---|---|
| `strategy` | Chọn `GenerationType.IDENTITY`, `SEQUENCE`, `TABLE`, `AUTO` (hoặc chiến lược khác được API hiện hành hỗ trợ). |
| `generator` | Tên generator đã khai báo để gắn với chiến lược cụ thể, ví dụ `@SequenceGenerator(name = "shipment_gen", ...)`. |

Khai báo `generator = "..."` phải khớp tên generator đã đăng ký. Không nhầm **tên generator trong metadata JPA** với **tên database sequence/table vật lý**.

Ví dụ:

~~~java
@SequenceGenerator(
    name = "shipment_gen",         // tên logical trong JPA
    sequenceName = "shipment_seq", // tên sequence vật lý
    allocationSize = 1
)
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "shipment_gen"
)
private Long id;
~~~

Đối với các ví dụ có schema SQL đi kèm, nên viết tường minh tên generator, tên đối tượng database và cách cấp phát để hiểu chính xác mô hình đang học. Khi chỉ ghi `@GeneratedValue` hoặc `AUTO`, tên và loại generator mặc định có thể phụ thuộc provider/naming conventions.

### Chọn kiểu Java cho identifier

`Long` và `Integer` thường phù hợp khóa số; `Long` có khoảng giá trị lớn hơn. Dùng wrapper `Long` thay vì primitive `long` giúp biểu diễn trạng thái **chưa có ID** bằng `null` khi entity còn transient. Không nên dựa vào `0` hay `-1` như quy ước phổ quát “chưa được lưu” vì generator/provider có thể có quy tắc unsaved-value khác nhau.

JPA hiện đại còn có `GenerationType.UUID` cho các trường hợp phù hợp, nhưng đây là **chiến lược khác**, nằm ngoài bốn chiến lược đang so sánh. `UUID` không phải là một dạng của `SEQUENCE` hay `IDENTITY`.

## 4. IDENTITY: ID sinh bởi lúc INSERT vào bảng dữ liệu

Với `GenerationType.IDENTITY`, Hibernate dựa vào khả năng tạo khóa tự động của cột database. Thao tác insert phải diễn ra để DB có thể trả về ID đã sinh.

### Mapping Java

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "identity_order")
public class IdentityOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "description", nullable = false)
    private String description;

    protected IdentityOrder() {}

    public IdentityOrder(String description) {
        this.description = description;
    }

    public Long getId() { return id; }
}
~~~

### DDL theo database

PostgreSQL hiện đại hỗ trợ identity columns:

~~~sql
CREATE TABLE identity_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    description VARCHAR(255) NOT NULL
);
~~~

MySQL dùng `AUTO_INCREMENT`:

~~~sql
CREATE TABLE identity_order (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    description VARCHAR(255) NOT NULL
);
~~~

Hai ví dụ DDL đều có ý tưởng “database sinh khóa khi insert”, nhưng cú pháp và khả năng explicit insert/returning của từng hệ quản trị khác nhau. Hibernate dialect biết chọn phương thức lấy khóa tương thích với DB và JDBC driver.

### Luồng thực thi

~~~java
EntityTransaction tx = entityManager.getTransaction();
tx.begin();

IdentityOrder order = new IdentityOrder("New laptop");
entityManager.persist(order);

Long generatedId = order.getId();
tx.commit();
~~~

Trong môi trường transaction và provider thông thường, Hibernate cần insert để có khóa từ DB, có thể phát sinh:

~~~sql
INSERT INTO identity_order (description) VALUES (?);
-- driver / DB trả generated key, ví dụ id = 123
~~~

Hibernate lấy giá trị thông qua khả năng trả khóa của database/JDBC, chẳng hạn generated keys hoặc cú pháp returning do dialect hỗ trợ. Tùy phiên bản và hoàn cảnh, insert có thể xảy ra ngay trong `persist()` hoặc bị hoãn đến một thời điểm thích hợp; **không viết business logic giả định mọi lời gọi `persist()` ở mọi môi trường đều ngay lập tức chạy SQL**.

### Vì sao IDENTITY hạn chế JDBC batching?

Để biết ID của mỗi entity, Hibernate thông thường phải lấy kết quả sinh khóa của từng `INSERT`. Vì cơ chế này gắn chặt với thao tác insert, Hibernate thường **không gom insert entity dùng IDENTITY vào JDBC batch** theo cách có thể làm với sequence/preallocated ID.

~~~java
tx.begin();
for (int i = 0; i < 1_000; i++) {
    entityManager.persist(new IdentityOrder("Order " + i));
}
tx.commit();
~~~

Dù cấu hình `hibernate.jdbc.batch_size=50`, không nên kỳ vọng 1.000 lệnh insert identity được gom thành 20 JDBC batches. Đó là lý do chiến lược này có thể trở thành yếu tố cản trở hiệu năng trong ứng dụng ghi khối lượng lớn.

### Khi nào IDENTITY hợp lý?

- Schema đang có cột identity/auto-increment và ứng dụng cần tương thích trực tiếp.
- Lượng insert vừa phải, không có yêu cầu batch throughput cao.
- Hệ quản trị database hỗ trợ identity tốt và kiến trúc không cần cấp trước ID trước khi insert.

Không nên chọn chỉ vì cú pháp annotation ngắn. Với workload import hàng chục nghìn dòng, cần đo hiệu năng insert và cân nhắc chiến lược ID cho phép preallocation nếu DB hỗ trợ.

## 5. SEQUENCE: xin ID từ sequence trước khi chèn entity

`GenerationType.SEQUENCE` sử dụng sequence để cấp giá trị identifier. Database sequence là một đối tượng cấp số độc lập với bảng dữ liệu, thường cho phép nhiều transaction lấy số đồng thời. Hibernate có thể lấy ID trước khi chạy `INSERT` entity, rồi sắp xếp/batch các thao tác ghi.

### Mapping Java

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "sequence_order")
@SequenceGenerator(
    name = "sequence_order_gen",
    sequenceName = "sequence_order_seq",
    allocationSize = 1
)
public class SequenceOrder {
    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "sequence_order_gen"
    )
    private Long id;

    @Column(nullable = false)
    private String description;

    protected SequenceOrder() {}

    public SequenceOrder(String description) {
        this.description = description;
    }

    public Long getId() { return id; }
}
~~~

### PostgreSQL DDL

~~~sql
CREATE SEQUENCE sequence_order_seq START WITH 1 INCREMENT BY 1;

CREATE TABLE sequence_order (
    id BIGINT PRIMARY KEY,
    description VARCHAR(255) NOT NULL
);
~~~

Với `allocationSize = 1` và chuỗi tăng 1, một luồng đơn giản có thể là:

~~~sql
SELECT nextval('sequence_order_seq');       -- id = 41
-- Hibernate đã gán id=41 cho entity trong bộ nhớ.

INSERT INTO sequence_order(id, description)
VALUES (?, ?);                               -- bind (41, 'Order A')
~~~

`nextval(...)` là cú pháp PostgreSQL; Oracle hoặc hệ khác có cú pháp riêng. Hibernate dialect giúp ánh xạ yêu cầu sequence sang cú pháp phù hợp.

### ID được gán lúc nào?

~~~java
tx.begin();
SequenceOrder order = new SequenceOrder("Order A");

entityManager.persist(order);
Long idAfterPersist = order.getId(); // thường đã có ID

entityManager.flush();               // INSERT entity thường chạy ở đây
tx.commit();
~~~

Giá trị ID có thể xuất hiện ngay sau `persist()` bởi Hibernate lấy giá trị sequence trước, **mặc dù hàng trong `sequence_order` chưa được insert**. Đây là khác biệt cốt lõi với IDENTITY.

### Lợi ích với JDBC batch

Khi nhiều ID đã được xác định trước, Hibernate có thể trì hoãn lệnh insert đến flush rồi gom các lệnh có SQL shape tương tự:

~~~java
tx.begin();
for (int i = 0; i < 1_000; i++) {
    entityManager.persist(new SequenceOrder("Order " + i));
}
tx.commit();
~~~

Với JDBC batching được bật và driver/mapping phù hợp, insert của các entity này có cơ hội được thực thi theo batch. Tuy nhiên, **đừng nhầm batching của insert với việc cấp ID**: nếu `allocationSize=1`, Hibernate vẫn có thể phải gọi sequence cho từng ID; preallocation giúp giảm số lần phải lấy giá trị từ database.

## 6. `allocationSize`: tạo một khối ID thay vì xin từng ID

`@SequenceGenerator` có `allocationSize`, mô tả kích thước phân bổ identifier theo cơ chế generator. Giá trị mặc định trong JPA là **50** nếu không chỉ định. Tùy Hibernate generator và optimizer, provider có thể lấy một giá trị sequence để cấp một **khối ID** cho nhiều entity, thay vì thực thi query lấy số mỗi lần `persist()`.

~~~java
@SequenceGenerator(
    name = "bulk_order_gen",
    sequenceName = "bulk_order_seq",
    allocationSize = 50
)
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "bulk_order_gen"
)
private Long id;
~~~

Ý tưởng cấp phát:

~~~text
Ứng dụng cần lưu 120 entity
        |
        v
Generator lấy/cấp một khối ID (kích thước khoảng 50)
        |
        +--> ID nội bộ cho nhiều entity mà không cần round trip mỗi entity
        |
        +--> Khi hết khối, xin khối tiếp theo
        |
        v
Các INSERT entity vẫn được đồng bộ tại flush/commit
~~~

Đừng giả định ID được cấp trong một khối nhất thiết liên tiếp theo đúng giá trị sequence `nextval()` hiển thị. Hibernate hỗ trợ nhiều optimizer khác nhau, như `pooled` và `pooled-lo`, với cách diễn giải giá trị sequence là cận trên hoặc cận dưới của khối. Quy tắc cụ thể phụ thuộc generator và Hibernate version.

### Cấu hình DDL và mapping phải thống nhất

Với các kiểu optimizer pooled thông thường, database sequence có thể cần `INCREMENT BY` khớp với kích thước phân bổ. Ví dụ một cấu hình Hibernate dự kiến allocation size 50 có thể đi cùng:

~~~sql
CREATE SEQUENCE bulk_order_seq START WITH 1 INCREMENT BY 50;
~~~

Nếu schema thực tế dùng `INCREMENT BY 1` nhưng mapping yêu cầu `allocationSize = 50` với một optimizer đòi tăng 50, Hibernate có thể phát hiện chênh lệch khi boot/validate hoặc gặp vấn đề khi nhiều tiến trình cấp ID theo các giả định không tương thích.

**Không sửa chỉ một phía** bằng cách thay `allocationSize` mà bỏ qua DDL sequence hoặc hệ thống khác cũng đang gọi sequence đó. Với sequence đã tồn tại, phải đối chiếu thuật toán generator, cấu hình pooled optimizer, quy ước next value và migration. `allocationSize = 1` giúp ví dụ đơn giản nhưng có thêm round trip, không phải lựa chọn tối ưu mặc định cho mọi workload.

### Vì sao ID có khoảng trống?

Giả sử một instance đã được cấp khối ID 1001–1050 nhưng chỉ sử dụng 10 số rồi ứng dụng restart. Các số còn lại có thể bị bỏ qua. Tương tự, sequence database thường **không rollback giá trị đã cấp** khi transaction rollback; DB sequence cache cũng có thể khiến số nhảy sau restart/failover. Đó là hành vi bình thường đối với surrogate key:

~~~text
ID đã cấp:         1001 1002 1003 1004 1005 ...
Row đã commit:     1001 ---- 1003 ---- 1005 ...
                       rollback   ID chưa dùng
~~~

Không nên lấy gaps làm bằng chứng Hibernate mất dữ liệu hoặc đã xóa bản ghi. Nếu cần số hóa đơn pháp lý không có khoảng trống, phải thiết kế một **cơ chế đánh số nghiệp vụ riêng** với quy tắc commit/khôi phục phù hợp.

## 7. TABLE: cấp ID bằng một bảng generator riêng

`GenerationType.TABLE` không có nghĩa “dùng chính bảng entity để cấp ID”. Nó sử dụng **một bảng lưu trạng thái bộ đếm/giá trị cấp phát**, thường là các row xác định bởi một segment key. Hibernate cần thực hiện thao tác đọc/cập nhật trên bảng này để có ID rồi mới insert entity.

### Mapping Java

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "table_order")
@TableGenerator(
    name = "table_order_gen",    // tên generator JPA
    table = "id_generator",      // tên bảng cấp ID vật lý
    pkColumnName = "segment_key",
    valueColumnName = "next_value",
    pkColumnValue = "table_order",
    allocationSize = 1
)
public class TableOrder {
    @Id
    @GeneratedValue(
        strategy = GenerationType.TABLE,
        generator = "table_order_gen"
    )
    private Long id;

    @Column(nullable = false)
    private String description;

    protected TableOrder() {}

    public TableOrder(String description) {
        this.description = description;
    }
}
~~~

Trong `@TableGenerator`:

| Thuộc tính | Ý nghĩa |
|---|---|
| `name` | Tên generator logic trong JPA để `@GeneratedValue(generator = "...")` tham chiếu. |
| `table` | Bảng vật lý chứa số cấp phát, ví dụ `id_generator`. |
| `pkColumnName` | Cột nhận diện từng bộ đếm/segment. |
| `valueColumnName` | Cột chứa giá trị generator. |
| `pkColumnValue` | Giá trị segment ứng với entity/nhóm entity đang sử dụng generator. |
| `allocationSize` | Số ID phân bổ theo mỗi đợt/cơ chế của generator. |
| `initialValue` | Giá trị khởi tạo theo semantics của generator; cần kiểm tra khi tự tạo dữ liệu seed và mapping. |

`@TableGenerator` cũng có các thuộc tính metadata khác như schema, catalog và unique constraints; cấu trúc cụ thể của bảng generator cần nhất quán với provider.

### Schema minh họa

~~~sql
CREATE TABLE id_generator (
    segment_key VARCHAR(100) PRIMARY KEY,
    next_value BIGINT NOT NULL
);

CREATE TABLE table_order (
    id BIGINT PRIMARY KEY,
    description VARCHAR(255) NOT NULL
);
~~~

Bảng `id_generator` có thể chứa:

~~~text
segment_key       | next_value
------------------+-----------
table_order       | 101
customer_account  | 401
payment_record    | 901
~~~

Các con số chỉ minh họa. `next_value` có thể là cận hoặc số cấp phát theo thuật toán của provider; **không tự suy luận** rằng row chứa “ID kế tiếp được sử dụng” nếu chưa biết semantics của optimizer. Với bảng generator do Hibernate tạo/khởi tạo, cấu trúc và giá trị seed phải đi theo cách Hibernate hiểu.

### Dòng chảy SQL minh họa

Để tránh hai transaction lấy cùng một ID, generator phải điều phối cạnh tranh trên row bộ đếm. Một mô hình ý tưởng là:

~~~sql
-- Tương đương về ý tưởng, không phải SQL cố định của Hibernate:
SELECT next_value
FROM id_generator
WHERE segment_key = 'table_order'
FOR UPDATE;

UPDATE id_generator
SET next_value = ?
WHERE segment_key = 'table_order';

-- Sau khi generator đã cấp ID:
INSERT INTO table_order(id, description)
VALUES (?, ?);
~~~

Hibernate có thể dùng transaction riêng phục vụ phát ID, cơ chế compare-and-swap hoặc hình thức lock/SQL khác tùy dialect, isolation và generator. Vì vậy đoạn SQL trên chỉ mô tả yêu cầu **cấp số đồng thời không trùng**, không phải một cam kết triển khai.

### Ưu và nhược điểm của TABLE

Ưu điểm là dùng được trong môi trường không có database sequence và có thể cấp ID trước khi insert. Tuy nhiên, bảng generator trở thành **điểm tranh chấp** nếu rất nhiều transaction/instance cùng phải cập nhật một segment row:

- Nhiều transaction cần đọc/cập nhật một row chia sẻ và có thể chờ lock.
- Có thêm round trip và transaction work để cấp số.
- Việc table generator tạo row/seed/counter ban đầu phải được triển khai nhất quán giữa các instance.
- Trong hệ thống có nhiều ứng dụng sử dụng chung generator, sai cấu hình `pkColumnValue` hoặc thuật toán cấp phát có thể dẫn đến va chạm ID.

Tăng `allocationSize` giúp giảm tần suất tương tác với bảng generator trong nhiều cấu hình, nhưng không loại bỏ hoàn toàn contention và cũng có thể tạo gaps như khi preallocate sequence.

### Khi nào dùng TABLE?

Phù hợp khi DBMS hoặc schema cũ không hỗ trợ/không sử dụng được sequence, nhưng ứng dụng cần chiến lược cấp ID trước insert và có thể chấp nhận cơ chế bộ đếm ở bảng riêng. Với database hỗ trợ sequence tốt và workload ghi lớn, `SEQUENCE` thường là điểm bắt đầu đáng cân nhắc hơn.

## 8. AUTO: provider quyết định chứ không phải một thuật toán thứ tư

`GenerationType.AUTO` yêu cầu JPA provider chọn chiến lược phù hợp. Khi viết:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.AUTO)
private Long id;
~~~

Bạn **chưa chỉ định trực tiếp** nơi cấp ID là identity column, sequence hay generator table. Hibernate xét kiểu identifier, phiên bản, dialect, cấu hình generator và metadata để xác định cơ chế thực tế.

Trong nhiều cấu hình Hibernate hiện đại, `AUTO` cho identifier số sử dụng một cơ chế **sequence-style**: ưu tiên database sequence nếu dialect hỗ trợ, hoặc cơ chế bảng thay thế khi cần. Nhưng đây không phải một quy tắc JPA bất biến; behavior lịch sử của Hibernate, việc nâng phiên bản và môi trường DB khác nhau có thể khiến lựa chọn thay đổi. Không nên khẳng định “AUTO luôn là IDENTITY trên MySQL” hoặc “AUTO luôn là SEQUENCE trên mọi database”.

### Tại sao AUTO tiện?

- Ví dụ demo hoặc ứng dụng đơn giản không phải quyết định generator vật lý ngay từ đầu.
- Provider có thể chọn generator phù hợp với dialect.
- Code entity ít phụ thuộc cú pháp tên sequence/table cụ thể.

### Tại sao AUTO có thể gây bất ngờ?

- Chuyển DBMS hoặc Hibernate version có thể làm đổi DDL và loại SQL.
- Một môi trường có sequence còn môi trường khác phải dùng generator table.
- Hiệu năng insert/batching khác nhau do generator thực sự được chọn.
- Migrating dữ liệu và điều chỉnh sequence/table counter phức tạp hơn nếu naming conventions tự động thay đổi.

**Khi ứng dụng production cần SQL và schema nhất quán**, khai báo tường minh chiến lược và generator thường giúp migrations, performance tests và vận hành dễ dự đoán hơn. `AUTO` vẫn hợp lệ và có ích, nhưng ứng dụng phải hiểu lựa chọn thực sự của Hibernate thay vì coi “tự động” đồng nghĩa “giống nhau trên mọi môi trường”.

### `AUTO` có chọn IDENTITY khi gặp cột auto-increment đã tồn tại?

Không thể suy luận từ riêng annotation. Nếu schema có cột identity nhưng Hibernate quyết định dùng sequence/table, SQL có thể không khớp DDL hoặc đòi generator object không tồn tại. Khi map một bảng legacy có identity column, chọn `GenerationType.IDENTITY` tường minh thường phản ánh schema chính xác hơn.

## 9. So sánh bốn chiến lược theo một thao tác `persist()`

Xét mã ứng dụng:

~~~java
var tx = entityManager.getTransaction();
tx.begin();

var order = new ExampleOrder("Purchase A");
entityManager.persist(order);
System.out.println("ID: " + order.getId());

entityManager.flush();
tx.commit();
~~~

Giả sử `ExampleOrder` lần lượt dùng mỗi chiến lược và không có trigger/tùy chỉnh khác:

| Thời điểm | IDENTITY | SEQUENCE | TABLE | AUTO |
|---|---|---|---|---|
| `new ExampleOrder()` | ID thường null. | ID thường null. | ID thường null. | Theo kiểu ID/generator, thường null trước persist. |
| `persist()` | Có thể cần insert để lấy generated key. | Thường lấy ID/khối ID, có thể chạy SQL lấy sequence. | Thường truy cập generator table để cấp ID. | Tùy generator thực tế. |
| Trước flush | Có thể entity row đã insert. | Thường ID đã có nhưng entity row chưa insert. | Thường ID đã có nhưng entity row chưa insert. | Tùy generator. |
| `flush()` | Đồng bộ thao tác còn chờ; insert có thể đã chạy. | Thường thực hiện insert entity. | Thường thực hiện insert entity. | Phụ thuộc generator và flush. |
| `commit()` | Xác nhận transaction. | Xác nhận transaction. | Xác nhận transaction. | Xác nhận transaction. |

Đối với `IDENTITY`, SQL insert sớm là hành vi phổ biến do cần ID ngay, nhưng thời điểm chính xác có các ngoại lệ theo cấu hình và trạng thái transaction. Với `SEQUENCE`/`TABLE`, ID trước insert là mục tiêu chính, nhưng các tối ưu hóa và yêu cầu generator quyết định số lần truy cập database.

### Nếu chạy `persist()` mà chưa begin transaction?

Không nên dùng đó làm phép thử để suy luận thời điểm cấp ID. Với transaction-scoped persistence context, thao tác persist bên ngoài transaction có những giới hạn theo JPA và môi trường. Một số Hibernate session mode có thể trì hoãn insert IDENTITY khi chưa có transaction. Hành vi phát sinh còn tùy `EntityManager`/`Session`, flush mode, connection và provider version. Để kiểm tra chiến lược thực tế, hãy dùng transaction rõ ràng.

## 10. JDBC batching: khác biệt quan trọng trong workload ghi lớn

JDBC batching cho phép Hibernate gửi nhiều statement có SQL shape tương tự qua API batch của JDBC. Điều này có thể giảm số round trip giữa ứng dụng và DB khi chèn/cập nhật hàng loạt.

Ví dụ cấu hình thường gặp:

~~~properties
hibernate.jdbc.batch_size=50
hibernate.order_inserts=true
hibernate.order_updates=true
~~~

Giải thích:

- `hibernate.jdbc.batch_size` đặt kích thước batch Hibernate sử dụng khi thích hợp.
- `hibernate.order_inserts` có thể sắp xếp các insert tương tự để tăng cơ hội batching.
- `hibernate.order_updates` tương tự cho update, nhưng có chi phí sắp xếp và cần đo.

Với 1.000 entity có SQL insert giống nhau:

~~~java
tx.begin();
for (int i = 0; i < 1_000; i++) {
    entityManager.persist(new SequenceOrder("Line " + i));
}
tx.commit();
~~~

**SEQUENCE:** Hibernate thường có thể cấp ID trước, trì hoãn insert đến flush rồi gom thành batches. Nếu optimizer preallocate 50 IDs, còn có thể giảm số query sequence.

**TABLE:** Có thể batch insert entity vì ID được cấp trước, nhưng chi phí generator-table row locking/update vẫn tồn tại. Việc batch insert không có nghĩa tổng chi phí của TABLE thấp.

**IDENTITY:** Thường phải insert từng entity để nhận ID, nên Hibernate không gom các identity inserts theo cách batch entity insert truyền thống. Dù Hibernate hoặc JDBC driver có tối ưu riêng, cần quan sát thực nghiệm thay vì giả định cấu hình batch_size sẽ có tác dụng đầy đủ.

**AUTO:** Batching phụ thuộc generator Hibernate thực tế chọn.

### Bảng so sánh hiệu năng mang tính định tính

| Tiêu chí | IDENTITY | SEQUENCE với pooling | TABLE với pooling | AUTO |
|---|---|---|---|---|
| Cấp ID trước insert | Thường không | Có | Có | Tùy |
| Cơ hội batch insert | Thường thấp | Thường tốt | Có, nhưng generator có overhead | Tùy |
| Truy cập DB để xin ID | Gắn với insert | Ít lần hơn nhờ block allocation | Ít lần hơn nhờ block allocation nhưng phải cập nhật bảng | Tùy |
| Tranh chấp tại nguồn ID | Do cơ chế identity của DB | Sequence thường phù hợp concurrency cao | Có thể là hot row ở generator table | Tùy |
| Tính đơn giản với schema cũ auto-increment | Tốt | Cần schema/sequence khác | Cần bảng generator | Không chắc |

Không thể kết luận từ bảng rằng sequence luôn nhanh hơn identity với mọi số lượng bản ghi hoặc mọi DB. Với insert nhỏ, overhead từ ORM, connection/transaction, index, constraint và network có thể lớn hơn chênh lệch generator. Cần benchmark trên workload thực tế.

## 11. Flush, commit và rollback với ID được sinh tự động

Một hiểu nhầm phổ biến là **entity có ID tức đã lưu thành công**. Thực tế, sequence có thể cấp ID trước khi insert, IDENTITY có thể insert trước commit, và cả hai đều có thể rollback.

~~~java
EntityTransaction tx = entityManager.getTransaction();
tx.begin();

SequenceOrder order = new SequenceOrder("Will rollback");
entityManager.persist(order);
Long allocatedId = order.getId();

entityManager.flush(); // INSERT có thể đã được thực thi.
tx.rollback();         // Bản ghi không được commit.
~~~

Sau rollback, ID đã cấp có thể không được tái sử dụng:

- **SEQUENCE:** Database sequence thường không nằm trong rollback transaction theo cách một row insert/update thông thường được rollback.
- **IDENTITY:** Bộ đếm auto-increment/identity của DB có thể tiến dù transaction rollback; chi tiết phụ thuộc DBMS.
- **TABLE:** Việc cấp số có thể được quản lý bằng transaction/locking tách biệt hoặc cơ chế chuyên biệt; không dựa vào giả định rollback entity insert sẽ hoàn nguyên chắc chắn bộ đếm.
- **AUTO:** Kế thừa hành vi nguồn ID đã chọn.

**Không chọn chiến lược sinh ID với mục tiêu “không bao giờ thiếu số”**. Nếu yêu cầu nghiệp vụ là số thứ tự liên tục không mất số, nó cần một thiết kế riêng về serialization, commit và phục hồi. Primary key kỹ thuật thường chỉ cần uniqueness và tính ổn định.

## 12. Thứ tự ID không phải thứ tự commit

Ví dụ hai transaction cùng lấy ID:

~~~text
Transaction A: lấy ID=100 ----- xử lý dài ----- commit sau
Transaction B:        lấy ID=101 -- commit trước
~~~

Khi query:

~~~sql
SELECT *
FROM sequence_order
ORDER BY id DESC;
~~~

ID lớn hơn không nhất thiết có nghĩa “được commit gần nhất”. Với sequence caching, block allocation giữa các application instances và transaction rollback, sự khác nhau càng rõ. Nếu muốn sắp xếp theo thời điểm nghiệp vụ, lưu cột thời gian phù hợp (và giải quyết khi có cùng timestamp), hoặc dùng thứ tự commit/event được thiết kế riêng nếu cần chặt chẽ.

Điều tương tự có thể xảy ra với IDENTITY do transaction concurrency. `AUTO` không có bảo đảm thứ tự bổ sung nào.

## 13. Quan hệ parent-child và thời điểm cần ID

Giả sử `PurchaseOrder` có nhiều `OrderLine` với khóa ngoại `order_id`:

~~~java
@Entity
class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    Long id;

    @OneToMany(mappedBy = "order", cascade = CascadeType.PERSIST)
    List<OrderLine> lines = new ArrayList<>();

    void addLine(OrderLine line) {
        lines.add(line);
        line.order = this;
    }
}

@Entity
class OrderLine {
    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    Long id;

    @ManyToOne(optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    PurchaseOrder order;
}
~~~

Khi:

~~~java
PurchaseOrder order = new PurchaseOrder();
order.addLine(new OrderLine());
entityManager.persist(order);
entityManager.flush();
~~~

Hibernate cần biết khóa `order.id` để đặt `order_id` cho line. Với `SEQUENCE`, ID của order có thể được cấp trước khi SQL insert được gửi; Hibernate có thể sắp xếp các inserts theo dependency và batching. Với `IDENTITY`, việc cần ID của order thường khiến Hibernate insert order để lấy generated key trước khi chèn order lines.

Điều này giải thích vì sao chiến lược ID ảnh hưởng thứ tự SQL, số lần gửi statement, cơ hội batching và các hành vi được quan sát ở ActionQueue, dù **mô hình quan hệ Java không thay đổi**.

### Lưu ý cascade

`CascadeType.PERSIST` quyết định thao tác persist được truyền từ parent sang child, còn chiến lược ID quyết định cách nhận khóa cho mỗi entity. Hai cơ chế riêng biệt; cascade không làm IDENTITY trở thành generator có thể cấp ID trước insert.

## 14. Tương thích database và tính portable

| Database / môi trường | IDENTITY | SEQUENCE | TABLE |
|---|---|---|---|
| PostgreSQL hiện đại | Có identity column | Có sequence mạnh | Có bảng generator thông thường |
| Oracle hiện đại | Có identity column | Có sequence | Có bảng generator thông thường |
| MySQL thông thường | Có `AUTO_INCREMENT` | Không có sequence độc lập theo kiểu PostgreSQL/Oracle trong MySQL phổ biến | Có bảng generator thông thường |
| SQL Server | Có identity column | Có sequence ở các phiên bản hiện đại | Có bảng generator thông thường |
| H2 dùng cho test | Có các cơ chế tương đương | Có sequence | Có bảng generator |

Bảng nhằm minh họa khả năng phổ biến, không nói rằng mọi version, edition hoặc dialect đều có syntax và behavior giống nhau. **Mariadb** có khả năng sequence ở những phiên bản nhất định, không nên gộp hoàn toàn với MySQL khi chọn generator.

Về mặt Java, `GenerationType` là enum chuẩn, nhưng **portability của schema/SQL thực tế** vẫn phụ thuộc database:

- IDENTITY cần cột được tạo đúng đặc tính identity/auto-increment của DB.
- SEQUENCE cần sequence phù hợp với generator và optimizer, hoặc cơ chế sequence-style tương thích được provider hỗ trợ.
- TABLE cần generator table có cấu trúc/counter/locking chính xác.
- AUTO để provider chọn nhưng vì vậy schema phát sinh có thể khác qua môi trường.

Một application chạy với H2 trong test mà production dùng PostgreSQL/MySQL **không tự bảo đảm** mọi giả định về DDL, batching và ID allocation đều được kiểm chứng. Với quyết định ảnh hưởng concurrency hoặc migration, nên có bài test tích hợp trên cùng loại database với production.

## 15. Legacy schema: chọn generator theo DDL có sẵn

Trong dự án đang vận hành, database thường đã tồn tại trước khi mapping được viết. Khi đó hãy bắt đầu từ schema:

**Trường hợp A – Bảng có IDENTITY/AUTO_INCREMENT:**

~~~sql
-- Ví dụ PostgreSQL:
CREATE TABLE legacy_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    description VARCHAR(255)
);
~~~

Mapping dễ hiểu nhất thường là:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
~~~

**Trường hợp B – Database đã có sequence được dùng để cấp khóa:**

~~~sql
CREATE SEQUENCE legacy_order_seq START WITH 1 INCREMENT BY 1;
~~~

Map `SEQUENCE` và đặt `@SequenceGenerator(sequenceName = "legacy_order_seq", allocationSize = 1)` nếu muốn khớp cách cấp phát từng ID. Nếu sequence dùng `INCREMENT BY 50`, cần map đúng optimizer/allocation settings và cách các ứng dụng khác sử dụng chung.

**Trường hợp C – Hệ thống cũ dùng một bảng `id_generator`:**

Map `TABLE` với tên bảng, cột, segment và giá trị khởi tạo phù hợp. Không tự đặt thêm một `@TableGenerator` với segment mặc định mà chưa kiểm tra counter đã có; hai ứng dụng cấp ID không cùng quy tắc có thể va chạm.

**Trường hợp D – Không quan tâm vật lý do database do Hibernate quản lý trong demo:**

`AUTO` có thể tiện, nhưng cần xem schema thực tế và không chuyển mặc định đó sang production mà bỏ qua migration review.

## 16. Lỗi thường gặp khi thiết kế sequence

### 16.1. `allocationSize` và `INCREMENT BY` không khớp

Ví dụ:

~~~java
@SequenceGenerator(
    name = "order_seq_gen",
    sequenceName = "order_seq",
    allocationSize = 50
)
~~~

Nhưng:

~~~sql
CREATE SEQUENCE order_seq INCREMENT BY 1;
~~~

Tùy optimizer được chọn, đây có thể là mismatch mà Hibernate báo khi validate hoặc khiến chiến lược cấp khối không hoạt động theo dự kiến. Để sửa, phải xác định optimizer và cách sequence đang được sử dụng, rồi migration **đồng bộ mapping và DB**. Không nên bật/tắt validation chỉ để che sai lệch.

### 16.2. Seed sequence thấp hơn ID hiện có

Giả sử bảng đã import các hàng có `id` đến 50.000, nhưng sequence vẫn cấp 1, 2, 3... Hibernate sẽ đưa ID trùng xuống DB và nhận unique/primary-key violation.

Khi import/migrate data, cần:

1. Kiểm tra `MAX(id)` trong bảng tương ứng.
2. Xác định sequence value và optimizer/allocation đang dùng.
3. Điều chỉnh sequence/counter theo quy tắc phù hợp với tất cả ứng dụng đang ghi.
4. Đảm bảo không có writer đồng thời có thể sử dụng vùng ID cũ trong lúc chuyển đổi.

Không copy một câu `setval(...)` ngẫu nhiên mà không hiểu ý nghĩa tham số `is_called`, `START`, `INCREMENT` và mức ID cần dự trữ.

### 16.3. Nhiều instance dùng sequence nhưng cấu hình khác nhau

Instance A có thể dùng pooled optimizer với `allocationSize=50` trong khi instance B cấp từng ID và cùng truy cập một sequence. Một số tổ hợp cấu hình có thể gây vùng cấp phát không tương thích; vì thế phải thống nhất sequence DDL, optimizer và cách đặt giá trị của mọi writer. Đồng thời phải tránh tình trạng ứng dụng tự gán ID vào vùng mà generator cũng đang cấp.

### 16.4. Giả định sequence quay lại số đã cấp khi rollback

PostgreSQL/Oracle database sequences thường không rollback như table rows. Thấy gaps là điều bình thường; không nên dùng khoảng trống trong dãy ID để đo số giao dịch thất bại.

## 17. Lỗi thường gặp khi dùng TABLE generator

### 17.1. Không tạo hoặc seed bảng cấp ID

Nếu Hibernate mapping yêu cầu bảng `id_generator` nhưng schema migration không tạo bảng hoặc segment tương ứng, lần persist đầu có thể lỗi SQL hoặc Hibernate phải thực hiện một quá trình khởi tạo riêng theo khả năng provider. Trên production nên quản lý migration rõ ràng và không phụ thuộc vào việc Hibernate tự sửa schema.

### 17.2. `pkColumnValue` dùng chung ngoài ý muốn

~~~java
@TableGenerator(
    name = "a_gen",
    table = "id_generator",
    pkColumnValue = "shared"
)
~~~

Hai entity có thể cố ý dùng cùng một bộ đếm hoặc cần hai bộ đếm độc lập. Chọn `pkColumnValue` rõ ràng. Nếu nhiều entity có cùng segment, chúng dùng chung không gian cấp số theo cấu hình generator và phải chấp nhận phân phối ID theo một chuỗi chung.

### 17.3. Generator table thành điểm nóng

Trong hệ thống nhiều transaction ghi, row bộ đếm có thể phải khóa/cập nhật liên tục. Biểu hiện là latency tăng, lock waits hoặc throughput không tăng khi tăng số worker. Cần đo connection/DB metrics, tăng allocation size thích hợp hoặc chuyển sang database sequence khi có thể.

### 17.4. Chọn TABLE chỉ vì “portable nhất”

TABLE có thể dùng ở nhiều DBMS, nhưng portability phải cân đối với locking, SQL, migrations, performance và khả năng vận hành. Portability ở mức annotation không có nghĩa tổng chi phí thấp nhất.

## 18. Lỗi thường gặp với IDENTITY và AUTO

### 18.1. Bật batch size nhưng vẫn có hàng nghìn INSERT riêng

~~~properties
hibernate.jdbc.batch_size=100
~~~

Nếu entity dùng IDENTITY, việc cần ID sinh từ mỗi insert làm cơ chế batch insert thông thường của Hibernate bị hạn chế. Phải xác nhận generator thực tế, SQL log và driver trước khi kết luận Hibernate “bỏ qua cấu hình” do bug.

### 18.2. Đọc ID sau persist rồi suy ra dữ liệu đã commit

Một entity IDENTITY có thể đã insert trong transaction nhưng chưa commit; sequence có thể cấp ID dù insert chưa xảy ra. Không dùng `getId() != null` như cờ thành công của nghiệp vụ.

### 18.3. Dùng AUTO rồi thay Hibernate version/DBMS

Khi nâng phiên bản Hibernate, tên sequence mặc định, lựa chọn generator hoặc optimizer có thể khác. Một schema cũ không chắc phù hợp tên/cấu trúc Hibernate mới mong đợi. Hãy so sánh DDL/mapping và migration trước khi deploy, đặc biệt khi nâng từ những cấu hình cũ về identifier generation.

### 18.4. Tự sửa giá trị @Id sau khi entity đã managed

Primary key đại diện identity của entity. Không tùy ý đổi `entity.id` sau khi đã persist; làm vậy có thể phá vỡ identity map, quan hệ FK hoặc dẫn đến lỗi ORM. Nếu yêu cầu đổi mã nghiệp vụ, nên có field business key riêng thay vì sửa surrogate primary key.

### 18.5. Gán ID bằng tay cho entity dùng generated strategy

~~~java
Order order = new Order();
order.setId(42L); // không phù hợp nếu ID do generator quản lý
entityManager.persist(order);
~~~

Với entity dùng `@GeneratedValue`, nên để provider kiểm soát giá trị ID. Việc truyền object mang ID cố định có thể bị nhận diện là detached, gây lỗi, hoặc xung đột với DB tùy generator/session API. Muốn nhập dữ liệu có ID cố định cần kế hoạch migration riêng và đồng bộ lại generator sau đó.

## 19. `persist()`, `merge()` và trạng thái entity

Identifier generation gắn với việc **tạo entity mới**. Nó không phải cơ chế cấp một ID mới mỗi khi object được cập nhật.

~~~java
// New/transient:
SequenceOrder fresh = new SequenceOrder("A");
entityManager.persist(fresh); // generator cấp ID mới

// Managed:
SequenceOrder existing =
    entityManager.find(SequenceOrder.class, 100L);
// sửa các field hiện có: ORM dùng identity cũ để UPDATE
~~~

Với detached entity, `merge()` sao chép state vào managed instance thích hợp và trả về managed instance. Không nên gọi `persist()` cho detached object đã có identity rồi kỳ vọng Hibernate tự tạo bản ghi mới với một ID khác.

~~~java
SequenceOrder managed = entityManager.merge(detachedOrder);
// managed là instance cần tiếp tục thao tác trong persistence context.
~~~

Với generated IDs, **object có ID không đủ để xác định tuyệt đối là detached** trong mọi trường hợp và không có ID không tự giải quyết mọi quan hệ/cascade. Hibernate xét mapping, unsaved-value, trạng thái persistence context và DB khi cần. Tuy nhiên, đối với code nghiệp vụ bình thường, nên tách rõ luồng **tạo mới** và **cập nhật bản ghi có sẵn**, thay vì thao tác trực tiếp trên ID.

### `equals()` và `hashCode()` với ID sinh tự động

Nếu entity dùng ID generated, `id` có thể null trước `persist()` rồi đổi thành một số sau đó. Viết `hashCode()` dựa hoàn toàn vào ID thay đổi có thể làm entity thất lạc khi nó đã được đưa vào `HashSet` trước khi persist.

~~~java
Set<SequenceOrder> orders = new HashSet<>();
SequenceOrder order = new SequenceOrder("A");
orders.add(order);             // lúc này id có thể null
entityManager.persist(order);  // id được cấp
~~~

Cách thiết kế equality cần cân nhắc entity lifecycle, business key bất biến và đặc điểm Hibernate proxies. Không nên chọn chiến lược ID chỉ để “sửa” một cách viết `equals()/hashCode()` thiếu ổn định; hai vấn đề liên quan nhưng có trách nhiệm riêng.

## 20. Quan sát chiến lược thực tế qua SQL log

Đừng chỉ đọc annotation rồi kết luận toàn bộ đường đi. Trong môi trường thử nghiệm, bật SQL và bind logging của Hibernate:

~~~properties
# Ví dụ trong Spring Boot + Hibernate 6:
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Với Hibernate 5, tên category dùng để log bind values có thể khác. Log tham số có thể chứa dữ liệu nhạy cảm; chỉ bật theo chính sách môi trường và bảo mật phù hợp.

Các mẫu log thường gặp:

**IDENTITY:**

~~~sql
INSERT INTO identity_order (description) VALUES (?);
-- Driver/DB trả ID sinh tự động.
~~~

**SEQUENCE:**

~~~sql
SELECT nextval('sequence_order_seq');
INSERT INTO sequence_order (description, id) VALUES (?, ?);
~~~

**TABLE:**

~~~sql
-- SQL thực tế khác nhau theo dialect/generator:
SELECT next_value FROM id_generator
WHERE segment_key = ? FOR UPDATE;
UPDATE id_generator SET next_value = ?
WHERE segment_key = ?;
INSERT INTO table_order(description, id) VALUES (?, ?);
~~~

**AUTO:** Quan sát xem Hibernate phát sinh query sequence, truy cập generator table hay insert lấy generated key, rồi đối chiếu với metadata/dialect.

### Dùng thống kê Hibernate để xem batching

Có thể kích hoạt statistics khi thử nghiệm:

~~~properties
hibernate.generate_statistics=true
~~~

Và dùng `SessionFactory.getStatistics()` hoặc công cụ monitoring của framework để xem số statement, số entity insert và các chỉ số liên quan; phiên bản Hibernate khác nhau cung cấp các counters/logging khác nhau. Để biết số round trip và batch thật sự, kết hợp Hibernate statistics với JDBC/driver monitoring và log database. Một dòng SQL được in ra không nhất thiết tương đương một round trip độc lập.

## 21. Quy trình lựa chọn chiến lược cho dự án

Không có một lựa chọn đúng cho mọi schema. Quyết định nên dựa trên những câu hỏi theo thứ tự:

1. **DBMS và schema hiện tại đang cấp ID theo cách nào?** Nếu có auto-increment cố định, IDENTITY thường rõ ràng; nếu có sequence chuẩn, SEQUENCE là lựa chọn tự nhiên.
2. **Workload ghi bao lớn?** Nếu cần insert hàng nghìn/hàng triệu entity, đánh giá JDBC batching, pooling và giới hạn của identity.
3. **Có bao nhiêu ứng dụng/instance cùng cấp ID?** Cần hiểu cấp phát block, locking, sequence cache và consistency giữa writers.
4. **Ai quản lý DDL/migration?** Nếu dùng Flyway/Liquibase, khai báo và kiểm chứng schema khớp với Hibernate generator.
5. **Có yêu cầu portability sang DB khác không?** AUTO/TABLE có thể giúp ở một số bối cảnh, nhưng hãy cân nhắc cả performance và migration semantics.
6. **Có yêu cầu số nghiệp vụ liên tục không?** Nếu có, tách bài toán đó ra khỏi surrogate primary key.

### Gợi ý chọn theo tình huống

| Tình huống | Ứng viên ưu tiên | Vì sao |
|---|---|---|
| PostgreSQL/Oracle, ghi nhiều, muốn JDBC batching | `SEQUENCE` với allocation/optimizer phù hợp | Có thể cấp ID trước và giảm số lần lấy số từ DB. |
| MySQL schema legacy dùng `AUTO_INCREMENT` | `IDENTITY` | Khớp trực tiếp cơ chế sinh khóa của bảng có sẵn. |
| DB/schema không có sequence, không muốn dùng identity | `TABLE` nếu chi phí bộ đếm chấp nhận được | Cấp ID trước insert bằng bảng riêng. |
| Demo nhanh, provider kiểm soát schema | `AUTO` | Cú pháp gọn, có thể để provider chọn generator. |
| Hệ thống lớn chạy nhiều instance, DB có sequence | Thường bắt đầu từ `SEQUENCE` | Khả năng concurrent allocation tốt, có tùy chọn preallocation. |
| Một số bản ghi mỗi phút, schema identity đơn giản | `IDENTITY` | Dễ tương thích; giới hạn batching có thể không quan trọng. |

Đây là gợi ý, không phải bảng xếp hạng tuyệt đối. Hãy đo trên đúng database, driver, Hibernate version, cấu hình connection pool và nghiệp vụ thực tế.

## 22. Migration khi đổi chiến lược sinh ID

Đổi `IDENTITY` sang `SEQUENCE` hoặc `TABLE` không chỉ là sửa enum:

~~~java
// Trước:
@GeneratedValue(strategy = GenerationType.IDENTITY)

// Sau:
@GeneratedValue(strategy = GenerationType.SEQUENCE,
                generator = "order_seq_gen")
~~~

Nếu DB đang dùng identity column, thêm sequence không tự động khiến Hibernate và schema hoạt động thống nhất. Những việc cần xem xét:

- Tạo đối tượng sequence/table generator và quyền truy cập thích hợp.
- Điều chỉnh DDL của bảng entity theo ý đồ cấp ID mới, tránh hai nguồn ID cùng cấp chồng lấn.
- Đặt giá trị bắt đầu cao hơn vùng ID đã có và cao hơn vùng đang được instance khác dự trữ.
- Đảm bảo `allocationSize`, `INCREMENT BY` và optimizer khớp nhau.
- Xử lý rolling deployments có instance cũ và mới cùng ghi trong một giai đoạn.
- Chạy migration theo cách kiểm soát writer concurrent để tránh cấp ID trùng.
- Kiểm tra logic phụ thuộc thời điểm có ID như event payload, cascade parent-child và batch jobs.

Nếu đổi từ `AUTO`, trước hết phải **xác định nó đang dùng generator nào** trong môi trường hiện tại. Thay chiến lược khi chưa biết nguồn ID cũ dễ gây lỗi unique key hoặc “sequence/table does not exist”.

### Khi nâng Hibernate phiên bản lớn

Phiên bản Hibernate có thể thay đổi default naming của sequence, generator semantics và giả định cấu hình. Do đó migration cần xét DDL mà phiên bản mới mong đợi, không chỉ xác nhận annotation compile được. Việc dùng `hibernate.hbm2ddl.auto=validate` có thể phát hiện một số mismatch; vẫn nên có migration review và integration tests tương ứng.

## 23. Bài thực hành quan sát bốn generator

Tạo bốn entity `IdentityOrder`, `SequenceOrder`, `TableOrder` và `AutoOrder` có cùng field `description` nhưng mỗi lớp dùng một chiến lược. Chuẩn bị schema bằng migration để đảm bảo DB objects tồn tại và khớp mapping.

### Thí nghiệm A — ID xuất hiện khi nào?

~~~java
tx.begin();
var obj = new SequenceOrder("Experiment A");
System.out.println("before persist = " + obj.getId());

entityManager.persist(obj);
System.out.println("after persist  = " + obj.getId());

entityManager.flush();
System.out.println("after flush    = " + obj.getId());
tx.rollback();
~~~

Lặp lại với IDENTITY, TABLE và AUTO, ghi lại thứ tự SQL. Câu trả lời quan trọng không phải chỉ là “ID có null không”, mà còn là **DB đã insert entity hay mới cấp ID**.

### Thí nghiệm B — Insert nhiều entity

~~~java
tx.begin();
for (int i = 0; i < 500; i++) {
    entityManager.persist(new SequenceOrder("Batch " + i));
    if (i > 0 && i % 50 == 0) {
        entityManager.flush();
        entityManager.clear();
    }
}
tx.commit();
~~~

Thử với `hibernate.jdbc.batch_size=50`, rồi lặp lại với IDENTITY và TABLE. Theo dõi tổng thời gian, SQL generator, số round trip, JDBC batch và DB lock waits nếu có. `clear()` tách entity khỏi persistence context; chỉ dùng khi code không còn cần giữ những entity đó ở trạng thái managed.

### Thí nghiệm C — `allocationSize = 1` và `allocationSize = 50`

Với sequence đã cấu hình DDL phù hợp cho từng thí nghiệm, insert vài trăm entity và so số lần lấy sequence value. Điều chỉnh giá trị sequence/optimizer/mapping đồng bộ, không đổi `allocationSize` trên một schema production đang hoạt động.

### Thí nghiệm D — Rollback có tạo gaps?

~~~java
tx.begin();
SequenceOrder order = new SequenceOrder("Rollback");
entityManager.persist(order);
Long allocatedId = order.getId();
entityManager.flush();
tx.rollback();

System.out.println("allocated ID = " + allocatedId);
~~~

Ở transaction khác, insert một order mới và so ID. Quan sát khoảng trống, nhưng không suy ra số lần rollback chính xác chỉ từ gaps.

### Thí nghiệm E — AUTO qua hai database

Chạy cùng `@GeneratedValue(strategy = AUTO)` trên hai DBMS/dialect được hỗ trợ với schema được chuẩn bị thích hợp. Ghi lại generator objects, SQL và batching. Mục tiêu là thấy AUTO là quyết định của provider, không phải một thuật toán ID cố định ở mọi DB.

## 24. Những câu hỏi thường gặp

**Hỏi: `allocationSize = 50` có nghĩa Hibernate luôn insert 50 row một lần?**

Không. `allocationSize` liên quan **phân bổ identifier**, còn `hibernate.jdbc.batch_size` liên quan **batch JDBC statement**. Có thể dùng allocationSize=50 và batch_size=20, hoặc ngược lại. Chúng tối ưu hai phần khác nhau của pipeline.

**Hỏi: IDENTITY có chắc luôn phát sinh INSERT ngay trong `persist()`?**

Không tuyệt đối. Đó là hành vi phổ biến vì DB phải insert để sinh ID, nhưng Hibernate có ngoại lệ tùy transaction/session và phiên bản. Trong mọi trường hợp, không coi `persist()` và `commit()` là đồng nghĩa.

**Hỏi: SEQUENCE có làm mất ID khi rollback không?**

Sequence/caching/optimizer có thể khiến số bị bỏ qua. Đây thường là đặc điểm thiết kế của nguồn cấp ID; bản ghi DB được bảo vệ bởi transaction vẫn có thể rollback hoàn toàn.

**Hỏi: TABLE có nghĩa mapping entity vào nhiều bảng không?**

Không. `GenerationType.TABLE` là **bảng cấp ID**. Nó khác `@SecondaryTable`, là kỹ thuật ánh xạ thuộc tính của một entity sang bảng phụ.

**Hỏi: AUTO có portable hơn mọi chiến lược khác không?**

AUTO giúp provider chọn generator theo môi trường, nhưng application vẫn phải tương thích DDL và semantics thực tế. Nếu đổi DBMS khiến generator khác đi, migration và batching có thể bị ảnh hưởng.

**Hỏi: Dùng `SEQUENCE` thì không cần sequence có sẵn?**

Điều đó phụ thuộc Hibernate generator, dialect và schema generation configuration. Với schema quản lý thủ công, cần chuẩn bị đối tượng generator mà mapping sử dụng. Không nên cho rằng Hibernate sẽ tự tạo nó ở production.

**Hỏi: Generated ID có làm entity tự động trở thành managed mãi mãi?**

Không. Managed/detached là trạng thái của entity trong persistence context. Sau khi session đóng hoặc entity bị detach, có ID không có nghĩa đối tượng vẫn được dirty-check và tự động update.

**Hỏi: Có thể dùng ID sinh tự động để sắp xếp giao dịch đúng theo thời gian?**

Không có bảo đảm thứ tự commit tuyệt đối. Với concurrent transactions, preallocated blocks và DB caches, ID có thể không phản ánh thứ tự hoàn tất.

## 25. Mô hình ghi nhớ khi lựa chọn

Hãy bắt đầu từ câu hỏi: **“Ai sinh ID, và Hibernate có cần INSERT trước để biết ID không?”**

- **IDENTITY:** chính bảng dữ liệu/DB sinh khóa khi insert; dễ phù hợp auto-increment schema nhưng thường hạn chế batch insert entity.
- **SEQUENCE:** sequence cấp ID độc lập với insert; Hibernate có thể biết ID trước, dùng allocation optimizer và batch insert hiệu quả khi cấu hình phù hợp.
- **TABLE:** một bảng counter cấp ID trước insert; có thể tương thích nhiều DB nhưng gây thêm thao tác/khóa tại row cấp số.
- **AUTO:** Hibernate/provider chọn generator dựa trên mapping và môi trường; cần kiểm chứng lựa chọn thật trước khi dựa vào hiệu năng hoặc DDL.

Bốn chiến lược giải quyết **cách cấp surrogate primary key**, không giải quyết thay transaction, concurrency control của dữ liệu nghiệp vụ hoặc yêu cầu đánh số liên tục. Khi hiểu ranh giới giữa **nhận ID**, **gửi INSERT** và **commit**, bạn có thể dự đoán SQL tốt hơn, giải thích các khoảng trống trong dãy ID, lựa chọn batching phù hợp và xây dựng migration nhất quán giữa entity mapping với database.
