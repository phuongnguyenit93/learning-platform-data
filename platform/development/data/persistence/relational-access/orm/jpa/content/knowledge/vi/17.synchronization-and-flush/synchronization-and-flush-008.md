# Ảnh hưởng của chiến lược sinh khóa tới thao tác ghi

Trong Java Persistence API (JPA), khóa chính không chỉ dùng để nhận diện một entity. **Cách sinh giá trị khóa chính quyết định nhiều chi tiết quan trọng của quá trình ghi dữ liệu:** khi nào JPA có thể biết ID, lúc nào cần gửi `INSERT`, liệu nhiều câu `INSERT` có được gom thành JDBC batch, có cần round-trip tới database trước khi flush, và các entity có quan hệ khóa ngoại được ghi theo thứ tự nào.

Một ứng dụng có thể viết cùng một đoạn code:

~~~java
entityManager.persist(order);
entityManager.persist(invoice);
entityManager.flush();
~~~

nhưng đường đi xuống database có thể khác đáng kể nếu entity dùng:

- `GenerationType.IDENTITY`: database thường cấp khóa khi thực hiện `INSERT`.
- `GenerationType.SEQUENCE`: có thể lấy giá trị từ sequence trước khi thực hiện `INSERT`, rồi trì hoãn việc ghi tới flush.
- `GenerationType.TABLE`: dùng bảng cấp phát giá trị, có thể phải khóa/cập nhật dòng bộ đếm.
- `GenerationType.AUTO`: provider quyết định cơ chế phù hợp theo dialect và phiên bản.
- `GenerationType.UUID`: có thể sinh định danh UUID mà không cần chờ cột auto-increment của database.
- Khóa tự gán: ứng dụng chủ động cung cấp ID; không cần generator JPA nhưng phải chịu trách nhiệm về tính duy nhất và vòng đời khóa.

Mục tiêu của bài là hiểu **mối quan hệ giữa chiến lược sinh khóa, persistence context, flush, commit, SQL thực tế và hiệu năng ghi**, thay vì cho rằng mọi annotation `@GeneratedValue` chỉ khác nhau ở cách tạo một số nguyên.

---

## 1. Bối cảnh: persist(), flush() và commit() là ba việc khác nhau

Giả sử entity:

~~~java
import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String description;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected PurchaseOrder() {}

    public PurchaseOrder(String description, Instant createdAt) {
        this.description = description;
        this.createdAt = createdAt;
    }

    public Long getId() {
        return id;
    }
}
~~~

Ở cấp API, một transaction có thể viết:

~~~java
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    PurchaseOrder order =
        new PurchaseOrder("Đơn mới", Instant.now());

    em.persist(order);
    // Entity được đưa vào persistence context.
    // Thời điểm có ID và thời điểm INSERT phụ thuộc chiến lược/provider.

    em.flush();
    // Đồng bộ các thay đổi đang chờ xuống database.
    // Vẫn chưa đồng nghĩa commit.

    tx.commit();
    // Transaction được xác nhận.
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
~~~

Ba khái niệm không được đồng nhất:

| Thao tác | Mục đích | Có bắt buộc INSERT ngay? | Đã commit? |
|---|---|---|---|
| `persist(entity)` | Chuyển entity mới vào phạm vi quản lý và đăng ký thao tác lưu | **Không nhất thiết**; có thể phải insert sớm theo chiến lược sinh khóa | Không |
| `flush()` | Đồng bộ các thay đổi pending bằng SQL | Thường có, đối với entity chưa ghi | Không |
| `commit()` | Kết thúc transaction thành công, thực hiện flush cần thiết | Có thể kích hoạt các SQL chưa được flush | Có nếu thành công |
| `rollback()` | Hoàn tác các thay đổi DB trong transaction chưa commit | Không phải thao tác cấp khóa | Không |

Một điểm tinh tế: **flush không nhất thiết là lần đầu database được truy cập để ghi hoặc cấp ID**. Nếu khóa do database sinh trong `INSERT` (như IDENTITY), provider có thể phải đưa INSERT xuống sớm hơn chỉ để biết primary key. Với SEQUENCE, provider có thể gọi `nextval()` trước flush, nhưng đó là thao tác **cấp số**, chưa phải INSERT hàng dữ liệu nghiệp vụ.

### 1.1. Ba câu hỏi nên hỏi khi đọc một mapping

Khi thấy:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.SEQUENCE)
private Long id;
~~~

hãy hỏi:

1. **Ai tạo ID?** Ứng dụng, ORM hay database?
2. **Khi nào ID có thể được biết?** Trước INSERT, khi INSERT thực hiện hay sau một cơ chế trả kết quả của database?
3. **Khi nào SQL ghi hàng được gửi?** Tại persist, flush, trước một query, hoặc lúc commit?

Câu trả lời ảnh hưởng trực tiếp tới transaction, batching, quan hệ parent–child và hiệu năng ghi hàng loạt.

---

## 2. Tổng quan các chiến lược sinh khóa

JPA chuẩn khai báo:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
~~~

hoặc:

~~~java
@Id
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "order_id_generator"
)
@SequenceGenerator(
    name = "order_id_generator",
    sequenceName = "order_id_seq",
    allocationSize = 50
)
private Long id;
~~~

Bảng so sánh thực hành:

| Chiến lược | Nơi tạo ID thường gặp | Có thể biết ID trước INSERT? | Ảnh hưởng thao tác ghi |
|---|---|---|---|
| `IDENTITY` | Identity/auto-increment của DBMS | Thường không | Provider thường cần INSERT để lấy ID; hạn chế JDBC insert batching trong nhiều cấu hình Hibernate |
| `SEQUENCE` | Database sequence, có thể kèm ORM optimizer | Có thể | Cấp ID trước, cho phép trì hoãn INSERT và gom batch tốt hơn |
| `TABLE` | Một bảng quản lý bộ cấp phát | Có thể | Thêm thao tác truy cập/cập nhật bộ đếm; có thể gây tranh chấp |
| `AUTO` | Provider chọn | Tùy chiến lược được chọn | Không nên suy đoán hành vi nếu chưa kiểm tra mapping/dialect |
| `UUID` | Generator UUID, thường có thể ở JVM | Thường có thể | Không cần identity insert để nhận khóa; hiệu ứng index/lưu trữ phụ thuộc kiểu UUID và DB |
| **Assigned ID** | Code nghiệp vụ tự gán | Có | Không cần generator, nhưng phải bảo vệ uniqueness/không tái dùng |

Lưu ý phiên bản: `GenerationType.UUID` được chuẩn hóa ở **Jakarta Persistence 3.1**. Trong dự án sử dụng JPA/Jakarta Persistence cũ hơn, UUID có thể được cấu hình qua tính năng của provider hoặc cách gán thủ công. Các ví dụ bên dưới dùng namespace `jakarta.persistence`; dự án cũ dùng `javax.persistence` cần điều chỉnh import tương ứng.

Không có chiến lược nào tự động bảo đảm số khóa chính **liên tục, không có khoảng trống**. Cấp phát trước, rollback, cache và transaction thất bại có thể để lại các giá trị không xuất hiện trong bảng.

---

## 3. IDENTITY: vì sao INSERT có thể diễn ra rất sớm?

Với IDENTITY:

~~~java
@Entity
@Table(name = "identity_orders")
public class IdentityOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String description;

    protected IdentityOrder() {}

    public IdentityOrder(String description) {
        this.description = description;
    }

    public Long getId() {
        return id;
    }
}
~~~

Schema PostgreSQL minh họa:

~~~sql
CREATE TABLE identity_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    description VARCHAR(255) NOT NULL
);
~~~

Ở database này, cột identity có cơ chế cấp giá trị khi hàng được chèn. Một luồng SQL có thể là:

~~~sql
INSERT INTO identity_orders (description)
VALUES ('Đơn A')
RETURNING id;
~~~

Cú pháp `RETURNING` là một cơ chế PostgreSQL có thể dùng để nhận lại ID; provider/driver cũng có thể dùng JDBC generated keys hoặc câu SQL khác. **SQL cụ thể không được quy định cố định bởi JPA.**

### 3.1. Chuỗi sự kiện thường gặp trong Hibernate

Giả sử:

~~~java
tx.begin();

IdentityOrder a = new IdentityOrder("A");
em.persist(a);

System.out.println(a.getId());

tx.commit();
~~~

Với Hibernate ở một cấu hình transaction thông thường, việc sinh khóa `IDENTITY` có thể dẫn tới:

~~~text
persist(a)
   |
   | Cần ID do database tạo
   v
INSERT identity_orders ...
   |
   | Driver/provider nhận generated key
   v
a.id được gán
   |
   v
commit() xác nhận transaction
~~~

Điều này giải thích tại sao Hibernate có thể gửi `INSERT` **ngay khi gọi `persist()`** thay vì chờ tới `flush()` cuối transaction. Nhưng không nên biến mô tả này thành một bảo đảm tuyệt đối của toàn bộ JPA: Hibernate có các tình huống trì hoãn identity insert, và thời điểm chính xác còn phụ thuộc phiên bản, transaction, flush mode, session API và dialect.

**Ý nghĩa chính:** nếu provider không thể cấp ID mà không INSERT, nó khó giữ tất cả INSERT đến cuối transaction rồi gom batch như trường hợp có khóa đã biết trước.

### 3.2. Tác động lên JDBC batching

Xét:

~~~java
tx.begin();

for (int i = 0; i < 100; i++) {
    em.persist(new IdentityOrder("Order " + i));
}

tx.commit();
~~~

Nếu Hibernate phải thực hiện từng INSERT để lấy generated ID, nó khó thực hiện JDBC batch insert theo cơ chế batch thông thường. Trong nhiều phiên bản Hibernate, JDBC **insert batching bị vô hiệu hóa đối với entity dùng IDENTITY**, dù có đặt `hibernate.jdbc.batch_size`.

Cần phân biệt:

- **JDBC batch**: driver nhận nhiều câu statement/parameter set để thực hiện theo lô.
- **Batch ở tầng service**: một method Java xử lý 100 entity trong cùng transaction.
- **Multi-row INSERT**: một câu SQL chèn nhiều hàng, như `INSERT INTO ... VALUES (...), (...)`.

Viết vòng `for` và mở một transaction không đồng nghĩa đã có JDBC batching. Với IDENTITY, câu INSERT có thể xảy ra nhiều lần riêng lẻ.

Không kết luận rằng IDENTITY **luôn chậm**. Với vài bản ghi mỗi request, cơ chế này rất đơn giản và có thể đủ nhanh. Vấn đề chủ yếu nổi lên ở workload ghi số lượng lớn, latency DB cao và ứng dụng cần batch insert.

### 3.3. Tác động lên việc quan sát ID và lỗi

Khi INSERT diễn ra sớm:

- ID có thể có giá trị ngay sau `persist()` trong một cấu hình cụ thể.
- Các constraint như `NOT NULL`, `CHECK`, `UNIQUE` có thể báo lỗi sớm hơn dự kiến.
- Nhưng **ID đã có không đồng nghĩa transaction commit thành công**.
- Nếu rollback, ID identity được cấp có thể không được hoàn lại.

Ví dụ:

~~~java
tx.begin();

IdentityOrder order = new IdentityOrder("A");
em.persist(order);

Long generatedId = order.getId();

tx.rollback();
// Không được dùng generatedId như bằng chứng có bản ghi đã commit.
~~~

Ngay cả khi `generatedId != null` tại thời điểm kiểm tra, database vẫn có thể không còn hàng với ID ấy sau rollback.

### 3.4. IDENTITY trên các DBMS khác

MySQL thường dùng `AUTO_INCREMENT`, SQL Server có identity column, PostgreSQL có `GENERATED ... AS IDENTITY`. Mỗi DBMS/driver có đặc điểm khác nhau về cách nhận generated key và batching.

Từ annotation `GenerationType.IDENTITY` không thể suy ra mọi hệ thống đều phát **đúng cùng SQL**, cùng số round-trip hoặc cùng chiến lược batch. Phải xem SQL và cấu hình dialect/driver thực tế.

---

## 4. SEQUENCE: cấp khóa trước, ghi hàng sau

Với SEQUENCE, provider có thể nhận ID từ **database sequence** trước khi thực hiện INSERT entity. Nhờ vậy, entity đã có ID trong persistence context mà chưa nhất thiết được ghi thành một hàng.

Ví dụ:

~~~java
@Entity
@Table(name = "sequence_orders")
public class SequenceOrder {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "sequence_order_gen"
    )
    @SequenceGenerator(
        name = "sequence_order_gen",
        sequenceName = "sequence_order_id_seq",
        allocationSize = 1
    )
    private Long id;

    @Column(nullable = false)
    private String description;

    protected SequenceOrder() {}

    public SequenceOrder(String description) {
        this.description = description;
    }

    public Long getId() {
        return id;
    }
}
~~~

Schema:

~~~sql
CREATE SEQUENCE sequence_order_id_seq
    START WITH 1
    INCREMENT BY 1;

CREATE TABLE sequence_orders (
    id BIGINT PRIMARY KEY,
    description VARCHAR(255) NOT NULL
);
~~~

Một chuỗi thao tác minh họa với PostgreSQL/Hibernate:

~~~text
em.persist(sequenceOrder)
      |
      v
SELECT nextval('sequence_order_id_seq')
      |
      v
sequenceOrder.id = 1
      |
      | Entity đang managed, INSERT có thể còn pending
      v
em.flush() hoặc commit()
      |
      v
INSERT INTO sequence_orders (id, description)
VALUES (1, 'A')
~~~

Ở đây, **cấp ID** và **INSERT hàng** là hai hành động có thể tách rời. Đây là ưu điểm quan trọng đối với thứ tự flush, nhiều entity phụ thuộc và JDBC batching.

### 4.1. Không phải gọi nextval() sau mỗi persist()

Nếu `allocationSize = 1`, provider có thể cần truy cập sequence thường xuyên để lấy từng khóa.

Khi dùng `allocationSize > 1`, Hibernate có thể dùng optimizer để lấy giá trị theo **nhóm**:

~~~java
@SequenceGenerator(
    name = "sequence_order_gen",
    sequenceName = "sequence_order_id_seq",
    allocationSize = 50
)
~~~

Một lượt phối hợp với sequence có thể giúp ORM chuẩn bị nhiều giá trị ID mà không gọi database cho từng entity. Điều đó giảm số lượt cấp khóa và cho phép hàng loạt INSERT được sắp vào action queue cho flush.

Khái niệm:

~~~text
Lần 1: ORM nhận thông tin cấp một nhóm ID
        |-- Order A nhận ID
        |-- Order B nhận ID
        |-- Order C nhận ID
        ...
        |-- Tới khi hết nhóm thì mới xin nhóm khác

Flush: Các INSERT với ID đã biết được gửi xuống DB.
~~~

Thuật toán cụ thể của `pooled`, `pooled-lo`, bước tăng sequence, tính toán miền ID và trạng thái restart phụ thuộc phiên bản Hibernate/provider. Không giả định “`allocationSize = 50` chắc chắn tạo đúng dãy 1..50 trong bộ nhớ” ở mọi cấu hình.

### 4.2. Khớp allocationSize với database sequence

Một mapping:

~~~java
@SequenceGenerator(
    name = "order_gen",
    sequenceName = "order_id_seq",
    allocationSize = 50
)
~~~

thường cần sequence vật lý và optimizer **tương thích về bước cấp phát**. Với một cấu hình Hibernate pooled phổ biến, sequence có thể được tạo như:

~~~sql
CREATE SEQUENCE order_id_seq
    START WITH 1
    INCREMENT BY 50;
~~~

Nhưng đây là ví dụ cho một cơ chế pooled phù hợp, không phải quy tắc bắt buộc mọi provider hoặc optimizer đều dùng `INCREMENT BY 50`. Một số optimizer có kỳ vọng khác về giá trị sequence vật lý.

Nếu mã Java giả định cấp phát theo lô 50 còn sequence thực tế hoạt động với bước không phù hợp, hệ thống có thể báo lỗi schema validation hoặc gặp nguy cơ cấu hình cấp ID không chính xác. **Không thay đổi allocationSize hay DDL sequence riêng lẻ khi chưa kiểm tra provider, optimizer và migration.**

### 4.3. SEQUENCE cải thiện batching như thế nào?

Ví dụ:

~~~java
tx.begin();

for (int i = 0; i < 100; i++) {
    em.persist(new SequenceOrder("Order " + i));
}

tx.commit();
~~~

Trong trường hợp Hibernate đã cấp ID cho 100 entity, các INSERT có thể được giữ lại trong persistence context/action queue. Ở thời điểm flush, Hibernate có điều kiện thuận lợi để gom các INSERT cùng SQL shape thành JDBC batch:

~~~text
persist A -> biết ID -> chờ INSERT
persist B -> biết ID -> chờ INSERT
persist C -> biết ID -> chờ INSERT
...
flush     -> xử lý INSERT theo batch
~~~

Tuy vậy, **SEQUENCE không tự động bảo đảm batching**. Còn phụ thuộc:

- `hibernate.jdbc.batch_size` có được bật không.
- Phiên bản Hibernate, JDBC driver và dialect.
- Các entity có cùng kiểu INSERT/SQL shape hay không.
- Thứ tự action queue và tùy chọn `hibernate.order_inserts`.
- Có thao tác/query/flush chen giữa hay không.
- Có thuộc tính/chiến lược sinh giá trị khác buộc INSERT và RETURNING sớm hay không.
- Có transaction hợp lệ, connection phù hợp, driver hỗ trợ batching hay không.

Đây là lý do benchmark phải xem **số SQL statement, số JDBC batches và số round-trip**, không chỉ đếm lời gọi `persist()`.

### 4.4. Sequence gaps và rollback

Trong PostgreSQL, `nextval()` không rollback cùng transaction:

~~~sql
BEGIN;
SELECT nextval('order_id_seq');
ROLLBACK;
~~~

Số vừa được cấp không nhất thiết được hoàn lại. Sequence có cache hoặc ORM preallocation còn có thể tạo khoảng trống khi ứng dụng dừng hoặc không dùng hết nhóm ID. Do đó **SEQUENCE không phải bộ đánh số chứng từ không gián đoạn**.

---

## 5. TABLE: dùng bảng để cấp phát ID

Khi không có sequence phù hợp hoặc cần một cơ chế portable ở một mức nhất định, JPA cung cấp `GenerationType.TABLE`.

Ví dụ mapping:

~~~java
@Entity
@Table(name = "table_orders")
public class TableOrder {

    @Id
    @GeneratedValue(
        strategy = GenerationType.TABLE,
        generator = "table_order_id_gen"
    )
    @TableGenerator(
        name = "table_order_id_gen",
        table = "id_generators",
        pkColumnName = "generator_name",
        valueColumnName = "next_value",
        pkColumnValue = "table_orders",
        allocationSize = 20
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

Bảng cấp phát có thể có dạng:

~~~sql
CREATE TABLE id_generators (
    generator_name VARCHAR(100) PRIMARY KEY,
    next_value BIGINT NOT NULL
);
~~~

Cần để provider/schema migration thiết lập **giá trị ban đầu đúng theo semantics của `@TableGenerator` và optimizer**, không tùy tiện giả định cột `next_value` luôn mang nghĩa “ID chắc chắn dùng tiếp theo”.

Cơ chế khái quát:

~~~text
Tạo entity mới
    |
    v
Provider cần một ID
    |
    v
Đọc/khóa và cập nhật một hàng trong bảng id_generators
    |
    v
Nhận giá trị hoặc vùng giá trị cấp phát
    |
    v
Gán ID cho entity
    |
    v
INSERT entity ở thời điểm flush/commit thích hợp
~~~

Điểm mạnh: có thể dùng trên nhiều cơ sở dữ liệu quan hệ mà không phụ thuộc sequence native trong cùng cách.

Đánh đổi:

- Cần **bảng bổ sung** và thao tác trên nó.
- Một hoặc vài hàng generator có thể trở thành điểm tranh chấp khi nhiều transaction cùng cấp số.
- Nếu cấp phát nhóm lớn, giảm số lần truy cập counter nhưng vẫn có khả năng bỏ số chưa dùng.
- Thứ tự và transaction cấp ID tùy provider; không suy đoán TABLE generator đảm bảo gapless.
- Có thể tạo thêm write load và lock contention so với database sequence native.

Trong nhiều dự án có DBMS hỗ trợ sequence tốt và workload ghi cao, SEQUENCE thường là lựa chọn nên xem xét trước TABLE. Nhưng phải đánh giá điều kiện thật của hệ thống.

---

## 6. AUTO: lựa chọn do provider quyết định

Mapping:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.AUTO)
private Long id;
~~~

hoặc khi không chỉ định chiến lược ở một số khai báo:

~~~java
@Id
@GeneratedValue
private Long id;
~~~

Ý nghĩa là giao cho provider lựa chọn chiến lược theo quy tắc hỗ trợ của nó. Với Hibernate, lựa chọn có thể thay đổi theo:

- Version Hibernate/JPA/Jakarta Persistence.
- Kiểu Java của ID, ví dụ `Long` hay `UUID`.
- Database dialect và khả năng sequence/identity.
- Các generator/custom annotation khác đang được áp dụng.
- Thông số cấu hình tương thích với hệ thống cũ.

**Đừng viết rằng AUTO luôn dùng IDENTITY trên MySQL hoặc SEQUENCE trên PostgreSQL trong mọi phiên bản**. Để biết hành vi thực, phải kiểm tra mapping/generator đã được provider chọn và SQL sinh ra.

### 6.1. AUTO và tính ổn định giữa môi trường

Nếu môi trường phát triển dùng H2 còn production dùng PostgreSQL/MySQL, provider có thể sử dụng cách tạo khóa khác nhau. Hệ quả:

- Thời điểm nhận ID có thể khác.
- SQL INSERT được flush vào những thời điểm khác nhau.
- Năng lực batch insert có thể khác.
- DDL sequence/identity khác nhau.
- Một số lỗi đồng bộ hoặc constraint có thể xuất hiện vào thời điểm khác.

Vì vậy với hệ thống cần tính dự đoán cao, **khai báo chiến lược rõ ràng và chạy integration test với DBMS gần production** là lựa chọn tốt hơn việc dựa hoàn toàn vào AUTO.

Không có nghĩa AUTO luôn sai: nó có thể phù hợp với hệ thống nhỏ, môi trường đồng nhất hoặc khi provider được chọn có chính sách ổn định. Điểm quan trọng là **hiểu quyền lựa chọn đã được ủy cho provider**.

---

## 7. UUID và khóa tự gán: biết ID mà không cần identity INSERT

Một entity dùng UUID theo Jakarta Persistence 3.1:

~~~java
import jakarta.persistence.*;
import java.util.UUID;

@Entity
@Table(name = "events")
public class EventRecord {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(nullable = false)
    private String eventType;

    protected EventRecord() {}

    public EventRecord(String eventType) {
        this.eventType = eventType;
    }

    public UUID getId() {
        return id;
    }
}
~~~

Khi provider tạo UUID ở phía ứng dụng, nó có thể cấp ID mà không cần gửi INSERT chỉ để lấy khóa. Các INSERT vì thế có thể được trì hoãn và batch, tương tự lợi ích “đã biết ID” của SEQUENCE.

Nhưng UUID không mặc định là một số tuần tự nhỏ gọn:

- Kiểu lưu trữ có thể là UUID native, binary hoặc chuỗi, tùy DBMS/provider/mapping.
- UUID ngẫu nhiên có thể ảnh hưởng locality của index, kích thước index và hiệu năng ghi.
- Những phiên bản UUID có tính sắp xếp theo thời gian có đặc điểm khác với UUID ngẫu nhiên thuần túy; khả năng sinh, cấu hình và loại UUID được hỗ trợ phụ thuộc provider.
- UUID không cho phép suy ra số lượng bản ghi hoặc thứ tự commit bằng cách nhìn giá trị.

### 7.1. Assigned ID: ứng dụng tự cung cấp khóa

Nếu hệ thống dùng khóa nghiệp vụ ổn định:

~~~java
@Entity
@Table(name = "countries")
public class Country {

    @Id
    @Column(name = "iso_code", length = 2)
    private String code;

    @Column(nullable = false)
    private String name;

    protected Country() {}

    public Country(String code, String name) {
        this.code = code;
        this.name = name;
    }
}
~~~

Code:

~~~java
Country country = new Country("VN", "Viet Nam");
em.persist(country);
~~~

Vì `code` đã được gán, JPA không cần generator để biết khóa. Tuy nhiên:

- Ứng dụng phải bảo đảm giá trị là duy nhất và phù hợp constraint.
- Không được tự thay đổi ID của managed entity như cập nhật một field thông thường.
- Business key có thể thay đổi theo nghiệp vụ; nếu nó làm PK, việc thay đổi ảnh hưởng FK và tích hợp.
- Cách Spring Data JPA nhận biết entity mới/detached với assigned ID có thể cần cấu hình hoặc giao ước riêng.

Biết ID trước INSERT **không đồng nghĩa hàng đã tồn tại trong database**.

### 7.2. UUID do database sinh qua default/trigger

Nếu ID có default/trigger ở DB thay vì do JVM sinh, provider có thể cần INSERT/RETURNING hoặc cơ chế generated keys để nhận ID. Vì vậy, “ID kiểu UUID” **không tự bảo đảm sinh trước INSERT**; yếu tố quyết định là **nơi và thời điểm generator thực sự hoạt động**.

---

## 8. Minh họa thời điểm phát SQL theo từng chiến lược

Giả sử có ba bản ghi mới, ứng dụng gọi:

~~~java
tx.begin();

em.persist(a);
em.persist(b);
em.persist(c);

em.flush();
tx.commit();
~~~

### 8.1. Một luồng IDENTITY thường gặp

~~~text
BEGIN
persist(a) -> INSERT a -> DB trả id(a)
persist(b) -> INSERT b -> DB trả id(b)
persist(c) -> INSERT c -> DB trả id(c)
flush()    -> xử lý các thay đổi khác nếu có
COMMIT
~~~

### 8.2. Một luồng SEQUENCE thường gặp với allocationSize = 1

~~~text
BEGIN
persist(a) -> lấy sequence value -> gán id(a)
persist(b) -> lấy sequence value -> gán id(b)
persist(c) -> lấy sequence value -> gán id(c)
flush()    -> INSERT a, INSERT b, INSERT c (có thể batch)
COMMIT
~~~

### 8.3. Một luồng SEQUENCE có pooled allocation

~~~text
BEGIN
persist(a) -> nhận một nhóm ID khi cần -> gán id(a)
persist(b) -> lấy ID đã cấp sẵn       -> gán id(b)
persist(c) -> lấy ID đã cấp sẵn       -> gán id(c)
flush()    -> INSERT a, INSERT b, INSERT c (có thể batch)
COMMIT
~~~

### 8.4. Một luồng UUID sinh tại JVM

~~~text
BEGIN
persist(a) -> tạo UUID(a) ở ứng dụng
persist(b) -> tạo UUID(b) ở ứng dụng
persist(c) -> tạo UUID(c) ở ứng dụng
flush()    -> INSERT a, INSERT b, INSERT c (có thể batch)
COMMIT
~~~

**Các sơ đồ chỉ là luồng điển hình để giải thích.** JPA không cam kết số SQL statement đúng như hình. Provider có thể flush sớm, query xen vào, dùng cơ chế RETURNING, batch driver khác nhau hoặc chọn phương án cấp khóa khác.

### 8.5. Bảng ảnh hưởng tổng hợp

| Câu hỏi | IDENTITY | SEQUENCE | TABLE | UUID tại JVM |
|---|---|---|---|---|
| Có cần INSERT để biết ID? | Thường có | Thường không | Thường không | Không |
| Có thể cấp ID trước khi INSERT entity? | Thường khó | Có | Có | Có |
| Có thể giữ INSERT tới flush? | Bị ràng buộc bởi sinh ID | Thường thuận lợi | Thường thuận lợi sau cấp ID | Thường thuận lợi |
| Có cần thao tác DB để cấp ID? | INSERT | nextval hoặc lượt cấp vùng | Truy cập/cập nhật bảng generator | Không |
| Có thể giảm round-trip cấp ID bằng allocation? | Không theo cơ chế sequence allocation thông thường | Có | Có | Không cần lượt cấp DB |
| Batch INSERT trong Hibernate? | Thường bị hạn chế | Thường thuận lợi nếu cấu hình đúng | Tùy cấu hình và chi phí generator | Thường thuận lợi |
| Có thể có khoảng trống ID? | Có | Có | Có thể | Không áp dụng dãy số nguyên |
| Độ dự đoán hành vi | Phụ thuộc DB/provider | Phụ thuộc provider/optimizer | Phụ thuộc provider | Phụ thuộc generator/provider |

---

## 9. FlushMode và thời điểm phải gửi INSERT

Chiến lược sinh khóa không hoạt động độc lập với `FlushModeType`. JPA phổ biến có các chế độ:

~~~java
em.setFlushMode(FlushModeType.AUTO);
~~~

hoặc:

~~~java
em.setFlushMode(FlushModeType.COMMIT);
~~~

Trong `AUTO`, provider phải đảm bảo semantics nhất quán của persistence context đối với những truy vấn được thực hiện trong transaction. Nó có thể flush trước truy vấn nếu cần để kết quả phản ánh các thay đổi pending.

Ví dụ:

~~~java
tx.begin();

SequenceOrder order = new SequenceOrder("A");
em.persist(order);

Long count = em.createQuery(
        "SELECT COUNT(o) FROM SequenceOrder o",
        Long.class
    )
    .getSingleResult();

tx.commit();
~~~

Với `AUTO` và Hibernate trên một mapping phù hợp, truy vấn `COUNT` có thể làm provider flush INSERT pending trước khi chạy SELECT, vì kết quả query cần tính tới order mới.

Còn với IDENTITY, INSERT có thể **đã được gửi từ lúc persist** để lấy ID, nên timeline khác.

### 9.1. COMMIT không có nghĩa mọi câu INSERT chắc chắn chờ commit

`FlushModeType.COMMIT` chủ yếu điều chỉnh thời điểm đồng bộ tự động trước query; tác động của thay đổi pending lên kết quả query không được xác định như AUTO. Nhưng nếu IDENTITY cần INSERT để nhận khóa, provider vẫn có thể phải thực hiện INSERT sớm hơn.

Tương tự, explicit `em.flush()` vẫn yêu cầu đồng bộ theo semantics của API dù flush mode là COMMIT.

Đừng sử dụng `COMMIT` như một cách “ép IDENTITY batch được” hoặc “không bao giờ viết DB trước commit”. Đó là các kết luận sai.

### 9.2. Thời điểm báo lỗi constraint

Với SEQUENCE:

~~~java
em.persist(order); // Có thể chỉ cấp ID, chưa INSERT.
em.flush();         // Lỗi NOT NULL/UNIQUE có thể xuất hiện tại đây.
~~~

Với IDENTITY, provider có thể gửi INSERT trong `persist()` nên lỗi có thể xuất hiện sớm hơn. Nếu cơ sở dữ liệu có deferred constraints, một số lỗi có thể chỉ xuất hiện lúc commit.

**Thời điểm exception phát sinh là chi tiết quan trọng đối với error handling**, nhưng ứng dụng vẫn phải xử lý transaction đúng: nếu transaction đã thất bại/rollback-only, không bắt exception rồi cố commit tiếp.

---

## 10. Quan hệ cha–con và thứ tự INSERT khi ID được sinh

Một tình huống thường gặp là tạo `Order` cùng nhiều `OrderItem` trong một transaction.

Entity cha:

~~~java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "purchase_order_gen"
    )
    @SequenceGenerator(
        name = "purchase_order_gen",
        sequenceName = "purchase_order_seq",
        allocationSize = 50
    )
    private Long id;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.PERSIST,
        orphanRemoval = true
    )
    private List<OrderItem> items = new ArrayList<>();

    protected PurchaseOrder() {}

    public void addItem(OrderItem item) {
        items.add(item);
        item.setOrder(this);
    }

    public Long getId() {
        return id;
    }
}
~~~

Entity con:

~~~java
@Entity
@Table(name = "order_items")
public class OrderItem {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "order_item_gen"
    )
    @SequenceGenerator(
        name = "order_item_gen",
        sequenceName = "order_item_seq",
        allocationSize = 50
    )
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(name = "product_sku", nullable = false)
    private String productSku;

    @Column(nullable = false)
    private int quantity;

    protected OrderItem() {}

    public OrderItem(String productSku, int quantity) {
        this.productSku = productSku;
        this.quantity = quantity;
    }

    void setOrder(PurchaseOrder order) {
        this.order = order;
    }
}
~~~

Những code block giả định có import `jakarta.persistence.*`, `java.util.List`, `java.util.ArrayList`. Trong ứng dụng thực tế nên có constructors/validation phù hợp với domain.

Code ghi:

~~~java
tx.begin();

PurchaseOrder order = new PurchaseOrder();
order.addItem(new OrderItem("BOOK-001", 2));
order.addItem(new OrderItem("BOOK-002", 1));

em.persist(order);
em.flush();

tx.commit();
~~~

Nhờ `cascade = PERSIST`, JPA có thể persist các OrderItem theo quan hệ từ parent, còn foreign key được ánh xạ qua **phía owning `OrderItem.order`**.

### 10.1. Khi ID cha đã biết trước INSERT

Với SEQUENCE, provider có thể cấp Order ID và Item IDs trước khi gửi INSERT. Vì vậy về mặt dữ liệu, các khóa ngoại đã có thể được xác định khi tổ chức action queue.

Một lịch SQL khái niệm:

~~~text
Lấy ID order từ sequence/allocator
Lấy ID item1, item2 từ sequence/allocator

flush:
  INSERT purchase_orders (id, ...) ...
  INSERT order_items (id, order_id, ...) ...
  INSERT order_items (id, order_id, ...) ...
~~~

Điều này hỗ trợ provider sắp xếp thao tác cho đúng constraint FK và có cơ hội gom batch những INSERT tương tự.

### 10.2. Khi ID cha do IDENTITY tạo

Với IDENTITY, provider thường cần chèn Order trước để nhận ID:

~~~text
persist Order
  -> INSERT parent -> nhận order.id

persist/cascade Item 1, 2
  -> cần order.id để tạo FK
  -> INSERT items vào thời điểm phù hợp
~~~

Đây là một lý do khác khiến IDENTITY ảnh hưởng thứ tự ghi và khả năng batching. Nếu tất cả Order/Item đều dùng IDENTITY, mỗi lần nhận generated key có thể phá khả năng gom batch như khi biết trước ID.

Tuy vậy, một provider vẫn có nhiều tối ưu và cơ chế xử lý dependency. **Không dự đoán số SQL hoặc thời điểm chính xác chỉ từ thứ tự lời gọi Java.**

### 10.3. Không gán FK thủ công nếu entity đã có association

Tránh mô hình hai nguồn dữ liệu có thể bất đồng:

~~~java
private Long orderId;

@ManyToOne
private PurchaseOrder order;
~~~

Nếu vừa tự gán `orderId` vừa dùng `order` mà không định nghĩa clearly cách mapping read-only/updatable, hai field có thể mâu thuẫn hoặc gây lỗi mapping duplicate column.

Trong mô hình quan hệ JPA thông thường, nên điều khiển quan hệ qua:

~~~java
item.setOrder(order);
~~~

và để provider ánh xạ `order_id` theo entity identity của Order, thay vì đọc `order.getId()` rồi tự viết FK trước khi ID có sẵn. Việc dùng FK thô có thể hợp lý với kiến trúc khác, nhưng phải là một lựa chọn có chủ đích.

---

## 11. @MapsId và khóa chính phụ thuộc

Một tình huống đặc biệt: entity con dùng **khóa chính chia sẻ** với entity cha. Ví dụ mỗi `User` có tối đa một `UserProfile` với `user_profiles.user_id` vừa là PK vừa là FK.

~~~java
@Entity
@Table(name = "users")
public class User {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    protected User() {}

    public Long getId() {
        return id;
    }
}
~~~

~~~java
@Entity
@Table(name = "user_profiles")
public class UserProfile {

    @Id
    @Column(name = "user_id")
    private Long id;

    @MapsId
    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false)
    private User user;

    @Column(nullable = false)
    private String displayName;

    protected UserProfile() {}

    public UserProfile(User user, String displayName) {
        this.user = user;
        this.displayName = displayName;
    }
}
~~~

Ở `UserProfile`:

- Không cần generator ID độc lập.
- `@MapsId` diễn đạt rằng ID hồ sơ được lấy từ ID của User được tham chiếu.
- Provider cần đảm bảo User có identity để ghi hàng Profile và FK đúng.

Nếu User dùng IDENTITY, nó có thể phải được INSERT để nhận ID trước khi Profile được ghi. Nếu User dùng SEQUENCE/UUID, ID có thể được xác định sớm hơn mà chưa INSERT, dù database vẫn phải nhận hàng User trước hàng Profile để thỏa FK.

**ID đã biết không đồng nghĩa được phép INSERT child trước parent**. Thứ tự SQL cuối cùng phải phù hợp ràng buộc dữ liệu và semantics của provider.

---

## 12. Hibernate batching: chiến lược sinh khóa là một trong nhiều điều kiện

Giả sử muốn nhập 10.000 hàng. Ta cấu hình Hibernate:

~~~properties
hibernate.jdbc.batch_size=50
hibernate.order_inserts=true
hibernate.order_updates=true
~~~

Trong Spring Boot, những thuộc tính Hibernate có thể được truyền qua namespace cấu hình framework, chẳng hạn:

~~~properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
~~~

Cần hiểu từng thuộc tính:

- `hibernate.jdbc.batch_size`: kích thước batch JDBC tối đa mà Hibernate xem xét sử dụng cho những statement đủ điều kiện.
- `hibernate.order_inserts`: có thể sắp xếp các INSERT để tăng số statement cùng kiểu có thể gom batch, đồng thời tôn trọng các dependency cần thiết.
- `hibernate.order_updates`: tương tự đối với các UPDATE có thể batch.
- Một số DBMS/driver cần thêm cấu hình driver để tối ưu khả năng truyền batch qua mạng.

**Đặt `batch_size=50` không có nghĩa tất cả INSERT được gom thành đúng 50 hàng/lần.** Nếu entity dùng IDENTITY hoặc SQL shape bị phân tán, kết quả khác.

### 12.1. Ví dụ batch có flush/clear định kỳ

~~~java
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    int batchSize = 50;

    for (int i = 0; i < 10_000; i++) {
        SequenceOrder order =
            new SequenceOrder("Order " + i);

        em.persist(order);

        if ((i + 1) % batchSize == 0) {
            em.flush();
            em.clear();
        }
    }

    em.flush();
    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) tx.rollback();
    throw ex;
}
~~~

Mục tiêu:

1. Giảm số entity managed giữ trong first-level cache quá lâu.
2. Cho Hibernate cơ hội gửi các statement pending theo batch.
3. Tránh một persistence context chứa hàng chục nghìn object cùng lúc.

Cảnh báo:

- `clear()` detach toàn bộ entity; đừng tiếp tục sửa các instance cũ rồi kỳ vọng dirty checking ghi chúng.
- Phải flush trước clear nếu có thay đổi pending cần giữ.
- Batch size của vòng Java không tự động bằng batch size JDBC.
- Nếu trong vòng có nhiều entity với FK phụ thuộc, cần đảm bảo không làm hỏng object graph hoặc ranh giới các hành động cần cùng context.
- Một transaction duy nhất với 10.000 hàng vẫn có thể lớn về lock, WAL/redo log và thời gian rollback; cần thiết kế theo workload.

### 12.2. So sánh với IDENTITY

Nếu thay mọi `SequenceOrder` thành `IdentityOrder`:

~~~java
for (int i = 0; i < 10_000; i++) {
    em.persist(new IdentityOrder("Order " + i));
}
~~~

Trong Hibernate phổ biến, mỗi entity IDENTITY có thể phải INSERT riêng để lấy key, làm mất lợi ích chính của JDBC insert batching. Flush/clear vẫn hữu ích cho quản lý bộ nhớ, nhưng không tự khôi phục batching vốn bị hạn chế vì generator.

Đừng sửa chiến lược khóa chỉ vì benchmark một lần trên H2. Hãy dùng database, driver, kích thước transaction và mapping gần production để đo.

### 12.3. Order inserts không giải quyết mọi ràng buộc

Nếu application xen kẽ:

~~~java
em.persist(orderA);
em.persist(itemA);
em.persist(orderB);
em.persist(itemB);
~~~

Hibernate có thể sắp lại SQL để gom INSERT cùng bảng trong giới hạn dependency cho phép. Nhưng FK yêu cầu parent được ghi trước child; unique constraints, triggers, generated columns và custom callbacks có thể tạo thêm ràng buộc. Không suy ra `order_inserts=true` bảo đảm gom hết mọi INSERT cùng loại trong một batch duy nhất.

---

## 13. @GeneratedValue và thời điểm ID xuất hiện

Một câu hỏi thường gặp:

~~~java
em.persist(order);
System.out.println(order.getId());
~~~

Giá trị này có chắc khác `null` không?

**Không nên biến một thời điểm quan sát cụ thể thành hợp đồng chung cho mọi chiến lược và provider.** Tuy nhiên, có những xu hướng hữu ích:

- **SEQUENCE**: Hibernate thường cấp ID khi persist để quản lý entity và có thể trì hoãn INSERT.
- **IDENTITY**: Hibernate thường gửi INSERT để nhận generated ID, có thể xuất hiện sớm, nhưng có những điều kiện trì hoãn.
- **UUID do JVM sinh**: thường có thể cấp ID trước INSERT.
- **TABLE**: có thể cấp ID sau thao tác truy cập bảng generator trước INSERT.
- **Assigned ID**: ứng dụng gán khóa từ lúc tạo object.

Nếu ứng dụng **thật sự cần ID tại một thời điểm cụ thể**, hãy:

1. Xác định provider, version và chiến lược sinh khóa đã chọn.
2. Thiết kế transaction cho phù hợp.
3. Dùng `em.flush()` khi cần buộc đồng bộ thao tác ghi trong transaction.
4. Xác minh hành vi bằng integration test trên DBMS thật.
5. Không dùng việc `id != null` như bằng chứng commit thành công.

### 13.1. ID tồn tại trước INSERT có tạo được URL ngay không?

Có thể dùng ID đã cấp để dựng một URL nội bộ hoặc tham chiếu trong object graph. Nhưng nếu transaction rollback, URL đó có thể trỏ tới tài nguyên không tồn tại. Không phát email hoặc event “Order đã tạo thành công” dựa hoàn toàn vào `getId() != null` trước commit.

Một hệ thống đáng tin cậy thường phát thông báo sau commit hoặc dùng transactional outbox để gắn event với kết quả transaction.

### 13.2. persist() không mặc định ghi ngay mọi cột

Ngay cả khi IDENTITY dẫn đến một INSERT sớm cho entity cha, các thao tác với entity khác vẫn có thể đang pending; Hibernate không buộc mọi entity trong context phải ghi ngay cùng một lúc chỉ vì một ID cần được nhận sớm. Hiểu khác biệt giữa **một thao tác sinh khóa thúc đẩy SQL** và **flush toàn bộ persistence context**.

---

## 14. Phân biệt flush với commit và rollback trong từng chiến lược

Cùng một transaction:

~~~java
tx.begin();

SequenceOrder order = new SequenceOrder("New order");
em.persist(order);

Long id = order.getId();

em.flush();
// INSERT đã được đồng bộ nếu thành công.

tx.rollback();
// Database không giữ bản ghi order vừa INSERT.
~~~

Với SEQUENCE, `id` có thể đã được cấp trước flush. Sau rollback:

- Bản ghi Order chưa commit không tồn tại trong database.
- Giá trị sequence đã cấp có thể không được trả lại.
- Object Java vẫn có thể giữ giá trị ID, nhưng không được xem là entity đã commit.
- EntityManager/context sau rollback cần được xử lý theo quy tắc provider; thường nên kết thúc unit of work và tạo mới.
- Retry nghiệp vụ có thể lấy ID khác; không có hợp đồng gapless.

Với IDENTITY, database có thể đã cấp identity tại INSERT sớm; rollback bản ghi không tự bảo đảm trả lại identity.

### 14.1. Không dùng ID tăng dần làm số chứng từ gapless

Một số nghiệp vụ muốn hóa đơn có số chính thức:

~~~text
INV-2026-000001
INV-2026-000002
INV-2026-000003
~~~

Các generator `IDENTITY` và `SEQUENCE` không bảo đảm rằng mọi số cấp ra đều nằm trong một hàng đã commit. Nếu cần chuỗi phát hành không gián đoạn theo một scope và chính sách xác định, phải xây **mã nghiệp vụ riêng** được cấp theo transaction phát hành, audit và quy tắc VOID/hủy phù hợp.

Khóa chính kỹ thuật nên tập trung vào uniqueness, FK và ORM identity; mã chứng từ có thể cần cơ chế transactional counter hoặc dịch vụ phát hành được thiết kế chuyên biệt. Không làm giảm tính nhất quán bằng cách cố “lấp” các số sequence bị bỏ qua sau rollback.

---

## 15. Generated key và lỗi UNIQUE/NOT NULL/foreign key

Lỗi database có thể xuất hiện ở những thời điểm khác nhau tùy generator:

### Trường hợp A — IDENTITY

~~~java
tx.begin();
em.persist(new IdentityOrder(null));
~~~

Nếu `description` là `NOT NULL` và provider thực hiện INSERT để lấy ID ngay, có thể phát sinh lỗi tại `persist()` hoặc một thao tác bên dưới nó.

### Trường hợp B — SEQUENCE

~~~java
tx.begin();
em.persist(new SequenceOrder(null));

em.flush(); // INSERT có thể diễn ra ở đây và báo lỗi NOT NULL.
~~~

Với SEQUENCE, bước cấp ID có thể thành công nhưng INSERT thất bại về sau.

Đây chỉ là các tình huống thường gặp; DB có thể kiểm tra deferred constraints lúc commit, provider có thể flush sớm, và đường lỗi phụ thuộc dialect.

### 15.1. Không bắt exception rồi tiếp tục commit

Ví dụ sai về mặt transaction:

~~~java
try {
    em.flush();
} catch (PersistenceException ex) {
    // Không được giả định transaction vẫn an toàn.
}

// Cố tiếp tục ghi entity khác và commit...
~~~

Nếu SQL đã thất bại, database transaction có thể ở trạng thái lỗi và JPA provider/transaction manager có thể đánh dấu rollback-only. Cách đúng thường là rollback, giải phóng unit of work và nếu nghiệp vụ cho phép thì retry trong transaction mới.

### 15.2. UNIQUE constraint vẫn là bắt buộc

Dù ID được sinh bằng bất kỳ generator nào, các quy tắc khác như `UNIQUE(sku)` hay `UNIQUE(order_code)` cần được thực thi ở database nếu yêu cầu uniqueness. Generator chỉ tạo khóa chính theo chính sách của nó; nó không làm mọi thuộc tính nghiệp vụ trở nên duy nhất.

---

## 16. Generated identifier và equals()/hashCode() trong collection

ID tự sinh có thể chưa có giá trị trước `persist()`. Nếu một entity dùng `id` để tính `hashCode()`, việc ID được gán sau khi object đã vào `HashSet` có thể làm collection hoạt động sai.

Ví dụ dễ lỗi:

~~~java
@Override
public int hashCode() {
    return Objects.hashCode(id);
}
~~~

Chuỗi sự kiện:

~~~text
new Product(...) -> id = null, hashCode = h1
add vào HashSet
persist -> id được gán, hashCode = h2
contains/remove theo hash mới có thể không tìm được object
~~~

Đây là vấn đề chung của generated identifiers, nhưng chiến lược sinh khóa ảnh hưởng **thời điểm chuyển từ null sang ID có giá trị**.

Nếu implement equality theo ID:

- Hai entity mới có `id == null` không nên bị coi là bằng nhau chỉ vì cùng null.
- Không dùng `@Data` của Lombok một cách máy móc trên JPA entity, làm `equals/hashCode/toString` duyệt cả quan hệ lazy.
- Cân nhắc business key ổn định và bất biến nếu thực sự phù hợp domain.
- Hoặc dùng một chiến lược equality dựa trên identity đã được cấp với hash ổn định và hỗ trợ proxy/provider đúng.
- Kiểm thử với entity transient, managed, detached và collection dùng HashSet/HashMap.

Không có một công thức `equals/hashCode` duy nhất phù hợp mọi mô hình JPA. Điều phải hiểu là **generated ID có thể thay đổi trạng thái từ chưa biết sang đã biết trong vòng đời object**, nên cách so sánh phải không phá cấu trúc collection.

---

## 17. Spring Data JPA: save(), saveAndFlush() và generator

Một service Spring Data JPA thường gọi:

~~~java
@Service
public class OrderService {
    private final OrderRepository orders;

    public OrderService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public Long createOrder(String description) {
        PurchaseOrder order =
            new PurchaseOrder(description, Instant.now());

        PurchaseOrder managed = orders.save(order);

        return managed.getId();
    }
}
~~~

Tùy cấu hình Spring Data JPA và trạng thái mới/detached, `save()` thường chuyển sang `persist()` hoặc `merge()` của JPA. Nhưng `save()` **không mặc định đồng nghĩa flush hoặc commit**.

Khi method transaction kết thúc thành công, transaction manager commit. Với IDENTITY, INSERT có thể được thúc đẩy sớm để lấy ID; với SEQUENCE, giá trị ID có thể được cấp trước rồi INSERT chờ flush.

### 17.1. saveAndFlush() khác save() thế nào?

~~~java
PurchaseOrder persisted = orders.saveAndFlush(order);
~~~

Thao tác này yêu cầu flush thay đổi trong persistence context theo semantics của repository. Nó có thể giúp phát hiện constraint violation sớm hơn trước khi transaction method kết thúc.

Nhưng:

- Flush **không commit**.
- Một lỗi sau `saveAndFlush()` vẫn có thể khiến transaction rollback.
- ID đã có sau `saveAndFlush()` không chứng minh bản ghi đã bền vững.
- Dùng `saveAndFlush()` trong vòng lặp có thể làm giảm cơ hội JDBC batching nếu mỗi lần flush chỉ có một INSERT.

### 17.2. saveAll() không bảo đảm batch insert

~~~java
orders.saveAll(listOfOrders);
~~~

Method này giúp xử lý một tập entity ở tầng repository, nhưng **không tự bảo đảm driver gửi JDBC batch**. Với IDENTITY, Hibernate có thể vẫn thực hiện INSERT riêng lẻ để nhận generated IDs.

Muốn tối ưu, phải xem strategy, `hibernate.jdbc.batch_size`, transaction boundary, SQL log, driver và biểu đồ hiệu năng thực tế.

### 17.3. Transaction propagation có thể thay đổi số lần flush/commit

Nếu mỗi lần lưu một Order đi vào một transaction độc lập, khả năng gom nhiều INSERT vào một batch có thể bị giới hạn ngay cả khi dùng SEQUENCE.

Ngược lại, một service `@Transactional` bao quanh nhiều lời gọi repository có thể cho Hibernate cơ hội gom flush theo một đơn vị công việc. Nhưng transaction lớn cũng có chi phí và rủi ro; không tăng kích thước vô hạn chỉ để có batch.

---

## 18. Quan sát SQL thực tế thay vì suy đoán

Để xác minh chiến lược sinh khóa ảnh hưởng thao tác ghi thế nào, có thể tạo hai entity cùng cấu trúc nhưng khác generator và chạy các thao tác giống nhau.

Một thí nghiệm đơn giản:

1. Tạo `IdentityOrder` với `GenerationType.IDENTITY`.
2. Tạo `SequenceOrder` với `GenerationType.SEQUENCE`.
3. Trong transaction riêng, persist 10 entity mỗi loại.
4. Ghi lại thời điểm gọi `persist()`, `flush()`, `commit()` và giá trị ID quan sát được.
5. Bật SQL logging và Hibernate statistics phù hợp.
6. So sánh số statement, việc có gọi sequence và JDBC batching thực tế.

Ví dụ cấu hình log Spring Boot/Hibernate thường gặp:

~~~properties
spring.jpa.show-sql=false
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
spring.jpa.properties.hibernate.generate_statistics=true
~~~

Tên logger và thông tin thống kê có thể khác theo phiên bản Hibernate. Với Hibernate 5, tên logger bind parameter thường khác Hibernate 6. Không copy cấu hình log mà không kiểm tra version và mức bảo mật dữ liệu của môi trường.

**Không bật log bind parameter trong production mà không xem xét dữ liệu nhạy cảm.** Những giá trị được ghi ra có thể chứa PII, token hoặc payload nghiệp vụ.

### 18.1. SQL log chưa chắc thể hiện batch round-trip

Khi Hibernate log nhiều câu `INSERT` trông giống nhau, điều đó không nhất thiết có nghĩa JDBC driver gửi mỗi câu bằng một round-trip. Batch có thể được truyền ở tầng JDBC/driver dù logger hiển thị từng SQL statement.

Muốn đánh giá batching đúng:

- Dùng statistics của Hibernate/provider nếu có.
- Dùng profiler JDBC hoặc datasource proxy có hỗ trợ quan sát batch.
- Theo dõi thời gian thực thi và số network round-trip nếu công cụ cho phép.
- So sánh execution plan/throughput trên DBMS thật.
- Chạy workload đủ lớn, warm-up và cấu hình ổn định.

### 18.2. Không suy ra “ít SELECT hơn” đồng nghĩa “ghi nhanh hơn”

SEQUENCE với `allocationSize = 1` có thể có thêm nhiều lệnh `nextval`; IDENTITY có thể không gọi sequence riêng nhưng phải INSERT sớm. Với pooled SEQUENCE, lượt cấp số giảm, batch tăng; hiệu năng cuối cùng phụ thuộc latency, driver, index, trigger, DB load và concurrency.

Chỉ benchmark tổng thời gian khi đã hiểu cấu hình và chi phí từng bước.

---

## 19. Các ngộ nhận phổ biến

### 19.1. “persist() chỉ ghi vào bộ nhớ, không bao giờ SQL ngay”

Không đúng với mọi chiến lược. IDENTITY có thể cần thực hiện INSERT ngay để nhận generated key.

### 19.2. “flush() mới tạo ID”

Không luôn đúng. SEQUENCE, TABLE hoặc UUID có thể cấp ID trước INSERT; IDENTITY thường cần INSERT để nhận ID, đôi khi trước flush.

### 19.3. “Đã có ID nghĩa là commit thành công”

Sai. ID có thể được cấp trong transaction về sau rollback hoặc trước khi hàng được INSERT. Chỉ commit thành công mới xác nhận transaction.

### 19.4. “IDENTITY không bao giờ batch trên mọi stack”

Trong nhiều phiên bản Hibernate, JDBC insert batching cho entity IDENTITY bị hạn chế/vô hiệu hóa. Nhưng đây là hành vi triển khai của ORM/driver, không phải định lý của mọi JPA provider và DBMS. Cần kiểm tra stack cụ thể.

### 19.5. “SEQUENCE luôn nhanh hơn IDENTITY”

Không phải mọi workload. SEQUENCE có lợi cho preallocation và batching, nhưng với vài INSERT nhỏ, cấu hình sequence không phù hợp hoặc database có chi phí khác, kết quả benchmark có thể thay đổi.

### 19.6. “allocationSize = 50 là 50 hàng được INSERT cùng lúc”

Sai. Allocation size liên quan **cấp vùng ID**, không phải số bản ghi trong JDBC batch. `hibernate.jdbc.batch_size` là cấu hình khác và vẫn có các điều kiện về SQL shape/driver.

### 19.7. “AUTO là chiến lược cố định”

Không. AUTO ủy quyền cho provider; dialect, kiểu ID và phiên bản có thể thay đổi lựa chọn thực.

### 19.8. “Đặt FlushModeType.COMMIT sẽ trì hoãn mọi INSERT”

Không. Sinh khóa hoặc các dependency có thể vẫn thúc đẩy SQL sớm. COMMIT không thay IDENTITY thành SEQUENCE.

### 19.9. “Đổi IDENTITY sang SEQUENCE chỉ sửa annotation”

Không. Phải đánh giá DDL, dữ liệu hiện có, đồng bộ sequence với max ID theo quy trình an toàn, concurrency, các writer khác, migration và cách ánh xạ khóa ở các FK.

### 19.10. “Database sequence đảm bảo mã đơn không nhảy số”

Không. Rollback, cache, allocation và restart có thể tạo khoảng trống. Cần bộ đánh số nghiệp vụ riêng nếu có yêu cầu gapless thật sự.

### 19.11. “saveAll() mặc định là JDBC batch”

Không. saveAll chỉ là API repository xử lý nhiều entity. Batching phụ thuộc generator, Hibernate và driver.

### 19.12. “Một câu lệnh SQL được log ra nghĩa là một round-trip”

Không nhất thiết. Driver có thể gom câu lệnh hoặc dùng protocol tối ưu. Phải đo ở đúng tầng.

---

## 20. Chọn chiến lược sinh khóa theo nhu cầu

Không có chiến lược tốt nhất trong mọi ứng dụng. Một bảng gợi ý:

| Tình huống | Gợi ý cần đánh giá | Vì sao |
|---|---|---|
| Ứng dụng CRUD nhỏ, DB có identity tốt | `IDENTITY` | Đơn giản; batching không phải nhu cầu chính |
| Nhiều INSERT, cần JDBC batching | `SEQUENCE` + allocation phù hợp | Có thể biết ID trước INSERT, cho phép gom lệnh ghi |
| Database có sequence native và latency cao | Pooled SEQUENCE | Giảm round-trip cấp ID |
| DBMS không có sequence thích hợp | `IDENTITY` hoặc TABLE nếu có lý do | Cân nhắc hiệu năng/portability/locking |
| Định danh phân tán nhiều node | UUID hoặc ID generator được thiết kế phân tán | Có thể cấp ID mà không phối hợp cột identity ở một DB |
| Dữ liệu danh mục với mã ổn định | Assigned business key | Không cần generator nếu mã là identity bất biến và unique |
| Chứng từ cần mã chính thức liên tục | Business serial riêng, không dùng PK generator làm quy trình phát hành | Generator PK không có hợp đồng gapless |
| Nhiều quan hệ parent–child và bulk insert | SEQUENCE/UUID có thể thuận lợi | Có ID sớm và khả năng sắp thứ tự SQL theo dependency |
| Chuyển DBMS/provider | Khai báo rõ strategy và integration test | AUTO/identity/sequence semantics có thể khác |

### 20.1. Checklist trước khi thay đổi generator

Trước khi chuyển từ IDENTITY sang SEQUENCE hoặc đổi allocation size trong production:

1. Xác định DBMS, dialect, Hibernate/JPA version.
2. Kiểm tra schema thực tế và dữ liệu đã có.
3. Xác định generator cho **từng entity**, không chỉ một annotation chung.
4. Kiểm tra sequence/table generator và migration tương ứng.
5. Xác định các ứng dụng khác cùng ghi vào bảng hay sử dụng chung sequence.
6. Đánh giá hiệu ứng lên batching và thứ tự INSERT/FK.
7. Kiểm tra idempotency, event, external ID và tác động rollback.
8. Kiểm tra optimistic locking, duplicate key và transaction concurrency.
9. Thực hiện integration test trên DBMS gần production.
10. Chạy migration có kiểm soát, không reset ID hoặc đụng sequence khi writer còn hoạt động mà chưa phối hợp.

### 20.2. Phân biệt tối ưu generator với tối ưu toàn bộ write path

Ngay cả khi dùng pooled SEQUENCE, tốc độ ghi còn phụ thuộc:

- Số lượng index và unique constraints.
- Transaction isolation/locking.
- Kích thước entity và kiểu cột.
- Triggers, computed columns và callbacks.
- FK và thứ tự ghi parent–child.
- Network latency, connection pool và driver.
- Batch size, flush cadence và persistence-context memory.
- Concurrent writers và DB capacity.

Đừng chọn chiến lược sinh khóa như một “mẹo tăng tốc” mà bỏ qua những phần còn lại của write pipeline.

---

## 21. Bài tập thực hành

### Bài tập 1 — Khi nào IDENTITY thực hiện INSERT?

Cho entity có:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
~~~

Sau khi gọi `em.persist(entity)`, vì sao Hibernate có thể phải gửi INSERT trước khi `flush()`? Điều đó ảnh hưởng thế nào tới batching?

**Gợi ý:** ID do database tạo khi INSERT; provider phải nhận generated key. Trong Hibernate phổ biến, điều đó hạn chế JDBC insert batching.

### Bài tập 2 — SEQUENCE và flush

Cho entity:

~~~java
@Id
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "product_seq_gen"
)
@SequenceGenerator(
    name = "product_seq_gen",
    sequenceName = "product_id_seq",
    allocationSize = 1
)
private Long id;
~~~

Giải thích vì sao có thể có ID trước INSERT, `flush()` sẽ làm gì, và `rollback()` có thể gây khoảng trống sequence thế nào.

### Bài tập 3 — allocationSize khác jdbc.batch_size

Một nhóm cấu hình:

~~~properties
hibernate.jdbc.batch_size=40
~~~

và mapping:

~~~java
@SequenceGenerator(
    name = "my_gen",
    sequenceName = "my_seq",
    allocationSize = 50
)
~~~

Hai số 40 và 50 có cùng nghĩa không? Giá trị nào điều khiển cấp vùng ID, giá trị nào điều khiển nhóm câu lệnh JDBC?

**Gợi ý:** Đây là hai cơ chế độc lập. Cấp ID không tự quyết định batch INSERT.

### Bài tập 4 — Thứ tự ghi parent–child

Order dùng IDENTITY, OrderItem có FK NOT NULL tới Order. Khi persist Order cùng ba Item, tại sao ORM có thể cần INSERT Order sớm để lấy ID? Nếu Order dùng SEQUENCE, điều gì thay đổi về thời điểm nhận ID và khả năng tổ chức action queue?

### Bài tập 5 — saveAndFlush chưa commit

Một service gọi `repository.saveAndFlush(order)`, thấy ID và nhận kết quả thành công, sau đó ném exception khiến transaction rollback. Trong database cuối cùng có Order không? Có được gửi event “đã tạo Order” ngay sau saveAndFlush không?

**Gợi ý:** Flush không commit; cần dựa vào kết quả transaction, hoặc outbox.

### Bài tập 6 — AUTO giữa H2 và PostgreSQL

Ứng dụng dùng AUTO, integration test trên H2 còn production trên PostgreSQL. Hãy nêu lý do có thể gặp hành vi khác về thời điểm INSERT và batching, và đề xuất cách kiểm tra.

### Bài tập 7 — Benchmark 1.000 INSERT

Thiết kế thí nghiệm so sánh IDENTITY và pooled SEQUENCE với 1.000 entity:

- Transaction scope thế nào?
- Bật các cấu hình Hibernate nào?
- Cần xem những chỉ số gì ngoài tổng thời gian?
- Vì sao phải chạy trên DBMS thật?
- Cần kiểm soát flush cadence và first-level cache ra sao?

### Bài tập 8 — Chuyển chiến lược trong production

Bảng có 10 triệu hàng và IDENTITY. Đội phát triển muốn đổi sang SEQUENCE để hỗ trợ batching. Liệt kê các bước migration tối thiểu trước khi đổi annotation: xác định sequence mới bắt đầu từ đâu, kiểm tra writer song song, xử lý schema, phiên bản provider, triển khai và rollback plan.

### Bài tập 9 — Dãy ID thiếu số

Một bảng có ID 101, 103, 104. Có thể kết luận hàng 102 bị xóa không? Những yếu tố nào trong generator/transaction có thể tạo ra gap?

**Gợi ý:** Rollback, cache, allocation, insert lỗi và restart; không kết luận từ ID đơn thuần.

---

## 22. Ghi nhớ

- **Chiến lược sinh khóa ảnh hưởng tới write path**, không chỉ giá trị ID.
- **IDENTITY** thường cần INSERT để database cấp ID; với Hibernate nó có thể buộc INSERT sớm và hạn chế JDBC insert batching.
- **SEQUENCE** có thể cấp ID trước INSERT, cho phép trì hoãn INSERT đến flush và tạo điều kiện cho batching.
- **allocationSize** quản lý cấp vùng ID; **jdbc.batch_size** quản lý nhóm statement JDBC — chúng không phải cùng một cấu hình.
- **TABLE** dùng bảng cấp phát ID, có thêm thao tác cập nhật và khả năng tranh chấp.
- **AUTO** phụ thuộc provider, dialect, version và kiểu ID; không suy đoán chiến lược thật từ annotation đơn lẻ.
- **UUID sinh tại JVM** và **assigned ID** có thể được biết trước khi ghi hàng, nhưng không tự nói lên tính bền vững hay thứ tự của bản ghi.
- **persist(), flush() và commit() khác nhau**. Có ID hoặc đã flush không đồng nghĩa dữ liệu đã commit.
- **FlushMode.AUTO/COMMIT** ảnh hưởng thời điểm đồng bộ, nhưng không xóa bỏ yêu cầu cấp ID của chiến lược đã chọn.
- **Quan hệ parent–child** có thể buộc thứ tự INSERT theo FK. ID được cấp trước giúp tổ chức write queue, nhưng không cho phép INSERT child trước parent nếu FK cấm.
- **Rollback có thể để lại khoảng trống khóa**; không dùng IDENTITY/SEQUENCE như mã chứng từ gapless.
- **saveAll() không đồng nghĩa JDBC batch**. Quan sát SQL, driver, Hibernate statistics và database thực tế.
- Trước khi thay generator trong production, phải xem cả **schema, dữ liệu, sequence increment, phiên bản Hibernate, transaction, concurrency và migration**.

**Kết luận:** JPA ghi dữ liệu theo mô hình persistence context và transaction, còn chiến lược sinh khóa quyết định lúc nào có thể cấp identity cho entity. IDENTITY thường liên kết việc cấp khóa với INSERT; SEQUENCE và một số generator khác có thể tách hai bước này, nhờ đó ảnh hưởng đến cách flush, sắp xếp SQL và batching. Hiểu rõ sự khác biệt giúp lựa chọn generator dựa trên workload thực tế, bảo toàn tính đúng đắn của quan hệ và tránh nhầm ID đã được cấp với một bản ghi đã commit.
