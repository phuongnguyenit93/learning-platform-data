# Phân biệt khóa đã cấp và dữ liệu đã được commit trong JPA

Trong JPA, một entity có thể đã có giá trị `id` mặc dù bản ghi tương ứng **chưa được commit** vào cơ sở dữ liệu. Trường hợp này xuất hiện với nhiều chiến lược sinh khóa: `SEQUENCE` có thể cấp ID trước câu lệnh `INSERT`; `IDENTITY` thường nhận ID khi database thực thi `INSERT`; `UUID` thậm chí có thể được tạo hoàn toàn ở phía ứng dụng. Bất kể khóa được cấp theo cách nào, giao dịch vẫn có thể thất bại hoặc bị rollback.

Điểm cần ghi nhớ ngay từ đầu:

> **Khóa đã cấp chứng minh entity có một giá trị định danh, không chứng minh dữ liệu đã được lưu thành công.**

Để hiểu ranh giới này, cần phân biệt bốn mốc: **cấp định danh**, **quản lý entity bằng `persist`**, **đồng bộ SQL bằng `flush`**, và **xác nhận giao dịch bằng `commit`**. Mỗi mốc giải quyết một nhiệm vụ khác nhau.

## 1. Khóa đã cấp là gì? Commit là gì?

### 1.1. Khóa đã cấp (generated/allocated identifier)

Khóa chính của entity được khai báo bằng `@Id` hoặc `@EmbeddedId`. Khi dùng `@GeneratedValue`, JPA provider và/hoặc cơ sở dữ liệu có thể tạo giá trị khóa theo một chiến lược phù hợp.

Ví dụ:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.SEQUENCE)
private Long id;
~~~

Nếu `id = 101` thì ứng dụng đã biết **giá trị định danh được chọn cho entity này**. Chưa thể từ đó kết luận rằng có một dòng đã được commit mang ID 101.

Giá trị ID thậm chí có thể được ứng dụng tự gán từ trước khi gọi `persist()`:

~~~java
Invoice invoice = new Invoice("INV-2026-0001");
// Chưa hề có giao dịch INSERT, nhưng mã định danh đã tồn tại.
~~~

Vì vậy, **có ID** và **tồn tại bản ghi đã commit** là hai điều kiện độc lập về mặt khái niệm.

### 1.2. Dữ liệu đã được commit (committed data)

Một transaction chứa thao tác `INSERT` được commit khi hệ thống quản lý transaction và database xác nhận giao dịch thành công. Đối với một giao dịch cơ sở dữ liệu quan hệ hỗ trợ ACID, commit thành công là ranh giới xác nhận những thay đổi thuộc giao dịch.

SQL minh họa:

~~~sql
BEGIN;

INSERT INTO purchase_order (id, description)
VALUES (101, 'Bàn phím cơ');

COMMIT;
~~~

Nếu thay `COMMIT` bằng `ROLLBACK` thì thao tác insert trong transaction bị hủy:

~~~sql
BEGIN;

INSERT INTO purchase_order (id, description)
VALUES (102, 'Chuột không dây');

ROLLBACK;
~~~

Ở cả hai ví dụ, số ID đều đã biết. Chỉ giao dịch đầu tiên được commit thành công.

### 1.3. Bảng đối chiếu

| Câu hỏi | Khóa đã cấp | Dữ liệu đã commit |
|---|---|---|
| Có giá trị định danh? | Có | Thường có với entity dùng khóa chính |
| SQL `INSERT` bắt buộc đã chạy? | Không | Có, nếu transaction tạo bản ghi được commit thành công |
| Ràng buộc DB chắc chắn đã vượt qua? | Không | Đã vượt qua những kiểm tra cần thiết để commit thành công |
| Transaction vẫn có thể rollback? | Có | Giao dịch đã commit không thể bị rollback theo cách của transaction đó |
| Transaction khác có thể đọc bản ghi? | Chưa chắc | Tùy isolation/snapshot và khả năng truy cập DB, nhưng dữ liệu đã là dữ liệu committed |
| Chứng minh nghiệp vụ thanh toán/giao hàng hoàn tất? | Không | Không; còn phụ thuộc trạng thái nghiệp vụ và hệ thống khác |

Từ bảng trên, `entity.getId() != null` chỉ trả lời câu hỏi về **giá trị định danh**, không phải tình trạng commit.

## 2. Vòng đời entity, flush và transaction không trùng nhau

Hình dung một luồng đơn giản:

~~~text
new PurchaseOrder(...)
        |
        |  Java object mới tạo
        v
entityManager.persist(order)
        |
        |  entity được persistence context quản lý
        |  khóa có thể được cấp trước hoặc sau bước này
        v
entityManager.flush()
        |
        |  provider gửi/thực thi SQL cần thiết trong transaction
        |  INSERT có thể đã chạy sớm hơn nếu dùng IDENTITY
        v
transaction.commit()
        |
        |  DB xác nhận transaction thành công
        v
Bản ghi đã commit
~~~

Nếu ở bất cứ thời điểm thích hợp nào trước commit ứng dụng gọi `rollback()`, thao tác ghi dữ liệu trong transaction sẽ bị hủy. Giá trị khóa đã cấp có thể vẫn còn ở phía ứng dụng, và trình cấp khóa có thể đã tăng.

### 2.1. `persist()`: Đưa entity vào persistence context

~~~java
tx.begin();

PurchaseOrder order = new PurchaseOrder("Giá đỡ màn hình");
em.persist(order);
~~~

`persist` yêu cầu JPA quản lý một entity mới và đưa nó vào tiến trình lưu. Một số chiến lược có thể cần phát SQL sớm, trong khi các chiến lược khác có thể hoãn `INSERT` đến flush/commit.

Lời gọi `persist` không ném exception **không bảo đảm** rằng ràng buộc UNIQUE, FOREIGN KEY hay NOT NULL đã được kiểm tra, và cũng không bảo đảm transaction sẽ commit.

### 2.2. `flush()`: Đồng bộ thay đổi với database

~~~java
em.flush();
~~~

Flush yêu cầu JPA provider đồng bộ các thay đổi đang chờ trong persistence context với database. Những câu `INSERT`, `UPDATE`, `DELETE` cần thiết có thể được thực thi trong transaction hiện tại.

Một số lỗi về dữ liệu có thể bộc lộ ngay lúc flush; tuy nhiên constraint deferred, xung đột giao dịch hoặc lỗi commit vẫn có thể xuất hiện sau đó.

**Flush thành công không đồng nghĩa commit thành công.** Sau flush, transaction vẫn có thể rollback.

### 2.3. `commit()`: Xác nhận transaction

~~~java
tx.commit();
~~~

Trong JPA resource-local transaction, `commit` yêu cầu kết thúc thành công giao dịch hiện tại, thường bao gồm flush cần thiết. Nếu commit trả về thành công, ứng dụng có cơ sở coi các thay đổi dữ liệu trong giao dịch đã được xác nhận theo ngữ nghĩa của DB.

Commit có thể thất bại do constraint, deadlock, timeout hoặc sự cố kết nối. Khi commit báo exception, phải xử lý theo ngữ cảnh cụ thể; trường hợp mất phản hồi kết nối đúng lúc commit có thể khiến ứng dụng **chưa biết chắc** DB đã commit hay chưa.

### 2.4. `rollback()`: Hủy thao tác dữ liệu nhưng không nhất thiết hủy ID

~~~java
tx.rollback();
~~~

Rollback hủy tác động ghi thuộc giao dịch DB theo các bảo đảm của hệ quản trị. Nó **không nhất thiết**:

- Đưa `id` của object Java về `null`.
- Thu hồi các số đã cấp từ database sequence.
- Làm bộ đếm identity/auto-increment giảm trở lại.
- Thu hồi email, request HTTP hoặc message đã gửi sang hệ thống bên ngoài.
- Đảm bảo có thể dùng lại object entity cũ trong một transaction mới.

## 3. Ví dụ entity dùng khóa sinh tự động

Một entity đơn hàng có thể được khai báo như sau:

~~~java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.SequenceGenerator;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "purchase_order_generator"
    )
    @SequenceGenerator(
        name = "purchase_order_generator",
        sequenceName = "purchase_order_seq",
        allocationSize = 1
    )
    private Long id;

    @Column(name = "description", length = 200, nullable = false)
    private String description;

    protected PurchaseOrder() {
        // Constructor cho JPA
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
}
~~~

Trong PostgreSQL, schema minh họa có thể là:

~~~sql
CREATE SEQUENCE purchase_order_seq
    START WITH 1 INCREMENT BY 1;

CREATE TABLE purchase_order (
    id BIGINT PRIMARY KEY,
    description VARCHAR(200) NOT NULL
);
~~~

`@Id` định nghĩa khóa chính, `@GeneratedValue` chọn cơ chế sinh khóa, còn `@SequenceGenerator` khai báo sequence mà provider sử dụng. Không annotation nào trong số đó xác nhận trạng thái commit của giao dịch.

Việc dùng `allocationSize = 1` ở đây chỉ nhằm làm ví dụ cấp số dễ quan sát. Trong ứng dụng thật có thể sử dụng optimizer cấp phát theo khối; cấu hình của provider và bước tăng của sequence tại DB phải phù hợp.

## 4. `GenerationType.SEQUENCE`: Khóa có thể được cấp trước INSERT

Với chiến lược `SEQUENCE`, provider thường phải biết ID trước khi tạo lệnh `INSERT`. Nó có thể yêu cầu số từ database sequence hoặc dùng một giá trị đã được cấp phát trước đó.

Ví dụ PostgreSQL:

~~~sql
BEGIN;

SELECT nextval('purchase_order_seq'); -- giả sử nhận 501

INSERT INTO purchase_order (id, description)
VALUES (501, 'Sổ tay');

ROLLBACK;
~~~

Kết quả:

1. Sequence đã trả về số `501`.
2. `INSERT` đã chạy trong transaction.
3. Transaction bị rollback.
4. Bảng không có bản ghi đã commit do giao dịch này tạo ra với ID 501.
5. Trong PostgreSQL, `nextval` không bị rollback cùng transaction thông thường, nên 501 có thể tạo ra khoảng trống trong dãy khóa.

Một tình huống còn rõ hơn:

~~~sql
BEGIN;
SELECT nextval('purchase_order_seq'); -- cấp 502
ROLLBACK;
~~~

Dù không hề có `INSERT`, giá trị 502 đã được cấp. Đây là bằng chứng thực tế rằng **cấp ID và lưu bản ghi là hai thao tác khác nhau**.

### 4.1. Vì sao ID có thể có ngay sau `persist`?

Với nhiều provider dùng SEQUENCE:

~~~java
tx.begin();

PurchaseOrder order = new PurchaseOrder("Tai nghe");
em.persist(order);

Long id = order.getId(); // Có thể đã khác null tại đây
~~~

Provider có thể lấy số sequence trước để giữ ID cho entity. Tuy nhiên, thời điểm chính xác mà khóa trở nên khả dụng phụ thuộc chiến lược và triển khai; đừng viết logic dựa vào giả định mọi provider cấp khóa ngay sau `persist`.

Nếu cần bảo đảm provider đã đồng bộ thao tác insert cần thiết trong transaction, hãy dùng `flush()` phù hợp, nhưng vẫn nhớ **flush chưa commit**.

### 4.2. Khoảng trống không phải bằng chứng dữ liệu bị mất

Giả sử sau nhiều transaction bảng chứa:

~~~text
id   description
---  --------------
501  Đơn hàng A
503  Đơn hàng C
507  Đơn hàng G
~~~

Việc thiếu 502, 504–506 có thể đến từ rollback, lỗi constraint, sequence cache, phân bổ trước theo khối hoặc nhiều instance ứng dụng cùng sử dụng bộ cấp số. Không thể kết luận các ID bị thiếu từng là đơn hàng đã commit rồi bị xóa.

Sequence cũng không phản ánh chắc chắn **thứ tự commit**. Transaction A có thể cấp ID 600 trước transaction B cấp 601, nhưng B commit trước A.

## 5. `GenerationType.IDENTITY`: INSERT có thể chạy sớm, nhưng chưa commit

Với `IDENTITY`, database thường cấp khóa khi thực thi `INSERT`. Ví dụ PostgreSQL:

~~~sql
CREATE TABLE purchase_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    description VARCHAR(200) NOT NULL
);
~~~

Ánh xạ JPA:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
~~~

Provider thường cần gửi `INSERT` hoặc dùng cơ chế nhận generated key của JDBC/database để biết ID; vì thế lệnh SQL có thể phải chạy sớm hơn so với SEQUENCE.

~~~sql
BEGIN;

INSERT INTO purchase_order (description)
VALUES ('Ổ cứng SSD')
RETURNING id; -- giả sử trả về 700

ROLLBACK;
~~~

Dù database đã trả ID 700, `ROLLBACK` vẫn hủy dòng vừa insert trong giao dịch. Tùy hệ DB, bộ đếm identity/auto-increment thường không được thu hồi hoàn toàn khi rollback; không dựa vào tính liên tục hay khả năng tái sử dụng khóa nếu hệ thống không cam kết.

Cần tránh suy luận “IDENTITY sinh khóa sau INSERT, vậy có ID nghĩa là đã lưu thành công”. **INSERT thành công trong transaction chưa phải commit**.

### 5.1. SQL có thể được gửi tại `persist` hoặc `flush`

Tùy Hibernate/EclipseLink, trạng thái transaction, JDBC driver và cấu hình, provider có thể thực hiện SQL sớm để lấy ID, hoặc hoãn đến thời điểm đồng bộ thích hợp. Vì vậy không cố định một lịch trình SQL duy nhất cho mọi triển khai.

Nguyên tắc bất biến là: ID được trả về trước commit vẫn chưa chứng minh transaction sẽ hoàn tất thành công.

### 5.2. Quan hệ với batching

IDENTITY có thể làm khó việc tối ưu JDBC INSERT batching vì provider cần nhận generated key cho mỗi bản ghi. Chi tiết tùy provider/driver/database; đây là khác biệt hiệu năng, không ảnh hưởng ranh giới commit.

## 6. `TABLE`, `UUID`, `AUTO` và khóa tự gán

| Chiến lược | Cách cấp ID điển hình | Có thể có ID trước commit? | Điểm cần chú ý |
|---|---|---|---|
| `SEQUENCE` | Dãy số database hoặc khối số reserve | Có | Các giá trị cấp có thể bị bỏ trống |
| `IDENTITY` | Cột tự sinh khi INSERT | Có, sau khi nhận generated key | INSERT có thể chạy trước commit |
| `TABLE` | Bảng generator cấp phát ID | Có | Tác động locking/hiệu năng và cách cấp phụ thuộc provider |
| `UUID` | Provider sinh UUID | Có | ID có thể được tạo mà chưa ghi DB |
| `AUTO` | Provider lựa chọn chiến lược | Có thể | Không nên đoán chiến lược nếu chưa kiểm tra |
| Tự gán | Ứng dụng đặt `@Id` | Có, trước cả `persist` | ID tự gán không chứng minh có bản ghi |

### 6.1. `GenerationType.TABLE`

Ví dụ:

~~~java
@Id
@GeneratedValue(
    strategy = GenerationType.TABLE,
    generator = "order_table_gen"
)
@TableGenerator(
    name = "order_table_gen",
    table = "id_generator",
    pkColumnName = "generator_name",
    valueColumnName = "next_value",
    pkColumnValue = "purchase_order",
    allocationSize = 10
)
private Long id;
~~~

Provider dùng bảng `id_generator` để cấp giá trị cho `PurchaseOrder`. Việc cập nhật hàng trong bảng generator, cách khóa hàng và cách quản lý transaction cho phần cấp số phụ thuộc provider và DB. Một giá trị đã được cấp bởi bảng generator vẫn chưa chứng minh rằng bản ghi nghiệp vụ đã commit.

### 6.2. `GenerationType.UUID`

Jakarta Persistence 3.1 cung cấp chiến lược `UUID`:

~~~java
import java.util.UUID;

@Id
@GeneratedValue(strategy = GenerationType.UUID)
private UUID id;
~~~

UUID có thể được provider sinh ở phía ứng dụng. Việc tạo một UUID thành công hoàn toàn không cần một bản ghi đã được commit. UUID hữu ích với những bài toán cần khóa không tuần tự, nhưng **không phải cờ báo lưu thành công**.

### 6.3. `GenerationType.AUTO`

~~~java
@Id
@GeneratedValue(strategy = GenerationType.AUTO)
private Long id;
~~~

`AUTO` để provider chọn chiến lược phù hợp theo cấu hình và database. Tại hệ DB khác hoặc sau khi nâng cấp provider, cách cấp ID có thể thay đổi. Muốn tìm hiểu thời điểm sinh khóa, kiểm tra metadata, log SQL và giao dịch thực tế.

### 6.4. Khóa do code tự gán

~~~java
@Entity
public class Shipment {

    @Id
    private String shipmentId;

    protected Shipment() {
    }

    public Shipment(String shipmentId) {
        this.shipmentId = shipmentId;
    }
}
~~~

Chỉ cần gọi:

~~~java
Shipment shipment = new Shipment("SHIP-0009");
~~~

Object đã có `shipmentId` nhưng chưa chắc từng được JPA quản lý. Không có `persist`, SQL hay commit trong ví dụ này. Đây là trường hợp dễ nhìn nhất cho sự độc lập giữa **giá trị ID** và **trạng thái lưu**.

## 7. Code JPA: Có ID rồi rollback

Giả sử entity `PurchaseOrder` ở phần trước dùng SEQUENCE và `emf` là `EntityManagerFactory` cấu hình `RESOURCE_LOCAL`.

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityTransaction;

EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

Long allocatedId = null;

try {
    tx.begin();

    PurchaseOrder order = new PurchaseOrder("Bàn phím");
    em.persist(order);

    // Flush yêu cầu thực thi các SQL còn chờ trong transaction.
    em.flush();

    allocatedId = order.getId();
    System.out.println("Allocated ID: " + allocatedId);

    // Giả lập người dùng hủy nghiệp vụ:
    tx.rollback();
} finally {
    if (tx.isActive()) {
        tx.rollback();
    }
    em.close();
}
~~~

Sau `flush()`, ID có thể đã được cấp và SQL `INSERT` đã chạy. Nhưng khi `rollback()` thành công, các thay đổi ghi của transaction bị hủy. `allocatedId` vẫn là giá trị Java được lưu trong biến, không phải minh chứng DB đã commit.

### 7.1. Kiểm tra ở persistence context khác

Nếu muốn đọc lại dữ liệu thực sự sau rollback, hãy tạo `EntityManager` mới:

~~~java
EntityManager reader = emf.createEntityManager();

try {
    PurchaseOrder persisted =
        reader.find(PurchaseOrder.class, allocatedId);

    // Trong một bài test cô lập, với ID chưa được dùng lại,
    // persisted sẽ là null sau rollback.
} finally {
    reader.close();
}
~~~

Phải bảo đảm bài test dùng schema/dữ liệu cô lập và không có transaction khác tạo dòng cùng ID. Đây chỉ là ví dụ quan sát, không chứng minh quy luật về việc sequence tăng hay không tăng sau rollback.

### 7.2. Đừng tiếp tục sử dụng entity cũ sau rollback như bình thường

Khi rollback, object Java có thể vẫn giữ ID đã cấp. JPA không bảo đảm mọi thuộc tính object tự trở về đúng giá trị trước transaction. Trạng thái quản lý của entity và persistence context cũng có thể thay đổi theo loại context/transaction.

Một cách thực tế là **kết thúc unit of work lỗi**, rồi nếu nghiệp vụ cần retry thì bắt đầu transaction mới, tạo hoặc truy vấn lại object phù hợp. Không tự tin rằng có thể gọi `persist` trên nguyên object sau rollback mà mọi provider sẽ xử lý giống nhau.

## 8. Code JPA: Chỉ trả ID sau khi commit thành công

Nếu muốn một phương thức tạo đơn hàng trả ID như kết quả lưu thành công, có thể đặt ranh giới commit trước khi trả kết quả.

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;

public final class PurchaseOrderWriter {

    private final EntityManagerFactory emf;

    public PurchaseOrderWriter(EntityManagerFactory emf) {
        this.emf = emf;
    }

    public Long createAndCommit(String description) {
        EntityManager em = emf.createEntityManager();
        EntityTransaction tx = em.getTransaction();

        try {
            tx.begin();

            PurchaseOrder order = new PurchaseOrder(description);
            em.persist(order);
            em.flush();

            Long generatedId = order.getId();

            tx.commit(); // Thành công mới trả ID cho caller.
            return generatedId;

        } catch (RuntimeException ex) {
            if (tx.isActive()) {
                try {
                    tx.rollback();
                } catch (RuntimeException rollbackError) {
                    ex.addSuppressed(rollbackError);
                }
            }
            throw ex;
        } finally {
            em.close();
        }
    }
}
~~~

Trong cách viết này, ID có thể đã được cấp trước `tx.commit()`, nhưng phương thức chỉ trả bình thường **sau khi `commit` trả thành công**. Khi `flush`/`commit` thất bại, phương thức báo lỗi thay vì trả ID như tín hiệu thành công.

Ví dụ không xử lý đặc biệt trường hợp **kết quả commit chưa xác định vì đứt kết nối**. Nếu yêu cầu tạo đơn có thể được retry, nên có khóa idempotency hoặc mã nghiệp vụ duy nhất để xác minh trạng thái transaction trước khi tạo lại.

## 9. Spring `@Transactional`: Ranh giới commit có thể nằm ngoài method body

Trong Spring Boot/JPA, thường dùng transaction manager thay vì gọi `getTransaction()`:

~~~java
import jakarta.persistence.EntityManager;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PurchaseOrderService {

    private final EntityManager entityManager;

    public PurchaseOrderService(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Transactional
    public Long createOrder(String description) {
        PurchaseOrder order = new PurchaseOrder(description);
        entityManager.persist(order);
        entityManager.flush();

        return order.getId();
    }
}
~~~

Trong thân method, `return order.getId()` được thực hiện khi transaction còn trong sự quản lý của Spring. Nếu lời gọi đi qua Spring proxy và chính lời gọi đó **mở transaction ngoài cùng**, Spring sẽ xử lý commit trên đường quay về caller. Caller thông thường chỉ nhận kết quả sau khi commit thành công; nếu commit lỗi, caller thường nhận exception.

Tuy nhiên, khi phương thức này tham gia một transaction đang tồn tại (ví dụ propagation `REQUIRED`), ID có thể được trả cho phương thức gọi bên ngoài **trước commit của transaction ngoài**:

~~~java
@Transactional
public void checkout() {
    Long orderId = purchaseOrderService.createOrder("Bàn phím");

    // Đã có orderId, nhưng transaction ngoài chưa kết thúc.
    inventoryService.reserve(orderId);

    // Nếu có exception cần rollback ở phía sau,
    // INSERT trước đó có thể cũng bị rollback.
}
~~~

Do đó, **nhận ID từ một service con không phải bằng chứng transaction tổng thể đã commit**.

Ngoài ra, cơ chế `@Transactional` của Spring thường dựa vào proxy/AOP; lời gọi nội bộ giữa các method trên cùng instance (*self-invocation*) có thể không đi qua proxy. Phải xác định ranh giới transaction thật của ứng dụng khi phân tích log.

### 9.1. `save()` và `saveAndFlush()` trong Spring Data JPA

~~~java
PurchaseOrder saved = repository.save(order);
Long id = saved.getId();
~~~

`save` sử dụng `persist` hoặc `merge` tùy Spring Data xác định entity là mới hay cũ. Với `merge`, instance trả về có thể khác object truyền vào; vì vậy nên dùng giá trị trả về khi cần lấy trạng thái/ID.

~~~java
PurchaseOrder saved = repository.saveAndFlush(order);
Long id = saved.getId();
~~~

`saveAndFlush` yêu cầu đồng bộ SQL, **không cam kết một transaction bao ngoài đã kết thúc**. Nếu đang tham gia transaction lớn hơn, toàn bộ thay đổi có thể bị rollback sau khi method trả entity.

Các dấu hiệu sau đều **chưa đủ** để khẳng định đã commit:

- Repository trả entity có ID.
- `saveAndFlush` không ném exception tại chỗ.
- Log đã hiển thị câu `INSERT`.
- `entityManager.find(...)` tìm thấy entity trong cùng persistence context.
- Một method service con trả về ID cho method service cha.

## 10. Vì sao `find()` thấy entity vẫn chưa chứng minh commit?

Một persistence context có **first-level cache**. Nếu entity đang managed:

~~~java
tx.begin();

PurchaseOrder order = new PurchaseOrder("Máy in");
em.persist(order);
em.flush();

PurchaseOrder same =
    em.find(PurchaseOrder.class, order.getId());

System.out.println(same == order); // thường true
~~~

`find` có thể trả lại chính object trong persistence context mà không cần đọc mới từ database. Kết quả đó chứng minh entity đang được quản lý, **không chứng minh đã commit**.

Ngay cả truy vấn SQL trong **cùng transaction** cũng có thể thấy dòng vừa insert chưa commit:

~~~sql
BEGIN;
INSERT INTO purchase_order (id, description)
VALUES (900, 'Màn hình');

SELECT * FROM purchase_order WHERE id = 900;
-- Transaction này có thể thấy bản ghi do chính nó ghi.

ROLLBACK;
~~~

Một transaction khác ở mức cô lập `READ COMMITTED` thông thường không nhìn thấy dòng chưa commit, dù transaction ghi có thể thấy. Ở những mức cô lập/snapshot khác nhau, thời điểm quan sát dữ liệu committed cũng khác; không suy ra kết quả của một giao dịch chỉ từ dữ liệu cache của giao dịch khác.

### 10.1. Hai transaction và thứ tự quan sát

~~~text
Thời điểm   Transaction A                        Transaction B
---------   ---------------------------------    ---------------------------
T1          BEGIN                                BEGIN
T2          INSERT order(id=901)
T3          SELECT id=901 -> thấy
T4                                               SELECT id=901
                                                 -> thường chưa thấy
T5          COMMIT
T6                                               Query mới có thể thấy,
                                                 tùy isolation/snapshot
~~~

Trong T4, có thể đã tồn tại ID trong cả Java và DB transaction A, nhưng dữ liệu chưa commit. Không thể đánh đồng khả năng “đọc lại trong transaction A” với “đã được mọi transaction khác đọc thấy”.

## 11. Lỗi có thể xảy ra sau khi ID được cấp

### 11.1. Ràng buộc database

Ví dụ entity có mã đơn hàng nghiệp vụ duy nhất:

~~~java
@Column(name = "external_code", nullable = false, unique = true)
private String externalCode;
~~~

Hai request đồng thời có thể được cấp **hai ID kỹ thuật khác nhau**, nhưng cùng muốn lưu `externalCode` giống nhau. Một request sẽ gặp lỗi UNIQUE khi SQL thực thi hoặc lúc commit tùy cơ chế constraint. Việc ID của request đó đã có giá trị **không giúp nó vượt qua constraint**.

Tương tự, lỗi FOREIGN KEY, NOT NULL, deadlock, serialization failure hoặc timeout có thể làm transaction không hoàn tất dù khóa đã được cấp.

### 11.2. Constraint có thể được kiểm tra muộn

`em.flush()` giúp bộc lộ nhiều lỗi sớm, nhưng không cam kết tất cả constraint đã được kiểm tra. Một số ràng buộc có thể deferred đến commit. Do đó, nếu nghiệp vụ cần xác nhận thành công, phải quan sát **kết quả commit**, không chỉ kết quả flush.

### 11.3. Khi mất kết nối lúc commit

Có một tình huống khác rollback thông thường:

~~~text
Ứng dụng                     Database
   |                            |
   |------ COMMIT request ----->|
   |                            | có thể commit thành công
   |<---- phản hồi bị mất -------X
   |
   | nhận lỗi mạng
   v
Không biết chắc transaction đã commit hay chưa
~~~

Nếu driver/app không thể xác định kết quả do mất kết nối, không nên kết luận chắc chắn rằng transaction rollback. Lần retry mù quáng có thể tạo đơn hàng thứ hai.

Giải pháp thường dùng:

- Lưu một **idempotency key** hoặc mã nghiệp vụ duy nhất cùng dữ liệu đơn hàng.
- Khi xảy ra trạng thái chưa xác định, tra cứu trạng thái theo khóa ổn định này.
- Dùng UNIQUE constraint và logic retry có kiểm soát để tránh nhân đôi đơn hàng.
- Tách trạng thái “đang xử lý/chưa xác định/hoàn tất” theo yêu cầu nghiệp vụ.

## 12. Không dùng khóa chính như số chứng từ liên tục

Một số hệ thống muốn khóa chính tăng đều để hiển thị:

~~~text
Đơn 1001, 1002, 1003, 1004, ...
~~~

Nhưng trong thực tế:

~~~text
Khóa đã cấp:       1001   1002   1003   1004   1005
Commit thành công: 1001          1003          1005
Rollback/lỗi:             1002          1004
~~~

Khoảng trống có thể do transaction thất bại, sequence cache, pooled optimizer, database restart hoặc phân bổ khóa theo khối. Đây thường là điều bình thường, không phải bằng chứng có bản ghi bị xóa.

| Giá trị | Vai trò | Có cần liên tục? |
|---|---|---|
| Primary key kỹ thuật | Xác định entity/bản ghi, phục vụ quan hệ và truy vấn | Thông thường không |
| Số chứng từ nghiệp vụ | Hiển thị, đối soát hoặc kiểm toán theo quy định | Tùy quy tắc nghiệp vụ/pháp lý |
| Idempotency key | Định danh yêu cầu tạo nghiệp vụ để retry an toàn | Không; chỉ cần độc lập, ổn định và phù hợp phạm vi |

Nếu doanh nghiệp có yêu cầu đặc biệt về số chứng từ không được bỏ số, cần thiết kế cơ chế đánh số nghiệp vụ riêng với giao dịch, đồng thời xử lý rollback, hủy chứng từ, audit và concurrency. Không có bảo đảm rằng đổi `SEQUENCE` thành `IDENTITY` sẽ làm số tự động liên tục.

### 12.1. Thứ tự ID và thứ tự commit

Giả sử:

~~~text
T1: Transaction A lấy ID 200
T2: Transaction B lấy ID 201
T3: Transaction B commit
T4: Transaction A commit
~~~

ID 200 nhỏ hơn 201 nhưng commit sau. Không dùng ID tăng dần để khẳng định thời điểm hoàn tất giao dịch. Nếu cần thứ tự sự kiện chính xác, hãy thiết kế dữ liệu và cơ chế ghi nhận riêng, với ngữ nghĩa transaction rõ ràng.

## 13. Không gửi hiệu ứng bên ngoài trước khi transaction commit

Ví dụ rủi ro trong service:

~~~java
@Transactional
public Long createOrder(String description) {
    PurchaseOrder order = new PurchaseOrder(description);
    entityManager.persist(order);
    entityManager.flush();

    Long orderId = order.getId();

    emailGateway.sendOrderConfirmation(orderId); // Quá sớm
    return orderId;
}
~~~

Nếu email đã gửi mà transaction DB sau đó rollback, người nhận có thông báo về đơn hàng chưa từng được commit. Tương tự khi gửi message lên queue, gọi API giao hàng, gửi yêu cầu thanh toán hoặc tạo file ở hệ thống bên ngoài.

### 13.1. Sự kiện sau commit trong Spring

Trong một ứng dụng Spring phù hợp, có thể phát domain event trong transaction rồi xử lý ở pha sau commit:

~~~java
public record OrderCreated(Long orderId) {
}
~~~

Trong service:

~~~java
@Transactional
public Long createOrder(String description) {
    PurchaseOrder order = new PurchaseOrder(description);
    entityManager.persist(order);
    entityManager.flush();

    publisher.publishEvent(new OrderCreated(order.getId()));
    return order.getId();
}
~~~

Listener:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.event.TransactionPhase;

@Component
public class OrderCreatedListener {

    private final EmailGateway emailGateway;

    public OrderCreatedListener(EmailGateway emailGateway) {
        this.emailGateway = emailGateway;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void notifyOrder(OrderCreated event) {
        emailGateway.sendOrderConfirmation(event.orderId());
    }
}
~~~

`publisher` và `EmailGateway` là các dependency giả định do ứng dụng cung cấp. `@TransactionalEventListener` liên kết việc xử lý sự kiện với pha hoàn tất giao dịch khi có transaction tương ứng.

Phương pháp này giảm nguy cơ gửi sự kiện khi transaction rollback, nhưng callback sau commit **không tự bảo đảm delivery** nếu tiến trình chết ngay sau commit. Với hệ thống cần phát message đáng tin cậy, cân nhắc **transactional outbox**: ghi bản ghi đơn hàng và một dòng outbox trong cùng transaction, sau đó worker gửi sự kiện từ outbox với retry/idempotency phù hợp.

### 13.2. Khóa không phải trạng thái nghiệp vụ

Kể cả đơn hàng đã commit, chưa thể kết luận đơn đã được thanh toán, đặt hàng với nhà cung cấp hoặc giao đi. Những bước này có trạng thái nghiệp vụ riêng, ví dụ `CREATED`, `PAID`, `SHIPPED`. ID chỉ giúp tham chiếu chính xác đến đơn.

## 14. Kiểm thử sự khác biệt giữa cấp ID và commit

### 14.1. Test dùng rollback

Trong Spring Test, một test có `@Transactional` thường được rollback sau khi kết thúc:

~~~java
@SpringBootTest
@Transactional
class PurchaseOrderRepositoryTest {

    @Autowired
    private EntityManager entityManager;

    @Test
    void idCanExistBeforeRollback() {
        PurchaseOrder order = new PurchaseOrder("Tạo trong test");

        entityManager.persist(order);
        entityManager.flush();

        assertNotNull(order.getId());
        // Test vẫn có thể rollback transaction sau khi hoàn thành.
    }
}
~~~

`assertNotNull(order.getId())` chỉ chứng minh khóa đã được sinh. Nó **không kiểm tra rằng dòng vẫn tồn tại sau commit**, vì không có commit thành công trong test rollback mặc định.

Khi cần integration test commit, tổ chức transaction riêng để thực sự commit, sau đó mở transaction hoặc persistence context mới và đọc lại bản ghi. Một test chỉ kiểm tra SQL được log cũng không chứng minh commit.

### 14.2. Test rollback với JPA resource-local

~~~java
Long attemptedId;

EntityManager writer = emf.createEntityManager();
EntityTransaction tx = writer.getTransaction();

try {
    tx.begin();

    PurchaseOrder order = new PurchaseOrder("Thử rollback");
    writer.persist(order);
    writer.flush();

    attemptedId = order.getId();
    tx.rollback();
} finally {
    if (tx.isActive()) {
        tx.rollback();
    }
    writer.close();
}

EntityManager reader = emf.createEntityManager();

try {
    PurchaseOrder found =
        reader.find(PurchaseOrder.class, attemptedId);

    // Trong DB test cô lập, khi ID chưa được dùng lại:
    assert found == null;
} finally {
    reader.close();
}
~~~

Dùng persistence context mới để tránh đọc lại object managed từ first-level cache của transaction trước. Điều kiện test phải cô lập và tránh hoạt động đồng thời có thể dùng lại ID. Không suy luận quy tắc của sequence từ kết quả kiểm tra bản ghi.

### 14.3. Những mốc nên quan sát khi kiểm thử

- ID trước `persist`, sau `persist` và sau `flush`.
- SQL phát sinh: `SELECT nextval`, `INSERT`, `COMMIT` hoặc `ROLLBACK`.
- Trạng thái của bản ghi khi truy vấn bằng transaction mới.
- Ảnh hưởng của UNIQUE/FK constraint khi flush và commit.
- Khác biệt giữa PostgreSQL/MySQL/SQL Server/Oracle với provider/driver thật.

Không giả định mọi kết quả trên database in-memory dùng cho test đại diện hoàn toàn cho cơ sở dữ liệu production.

## 15. Bảng chẩn đoán nhanh

| Hiện tượng | Điều có thể xảy ra | Cách suy luận |
|---|---|---|
| `id != null` ngay sau `persist` | Provider đã cấp số/UUID | Chưa biết SQL hay commit |
| `id != null` sau `flush` | SQL ghi đã được đồng bộ | Chưa biết commit thành công |
| `INSERT` có trong SQL log | SQL đã được phát | Chưa biết transaction rollback hay commit |
| `find` trong cùng context trả entity | First-level cache hoặc dữ liệu cùng transaction | Không chứng minh dữ liệu committed |
| Transaction khác chưa thấy dòng | Chưa commit, isolation hoặc snapshot | Xác định ranh giới transaction |
| ID tăng nhưng không có dòng tương ứng | Sequence/identity đã cấp số cho transaction rollback/lỗi | Không mặc định dữ liệu bị xóa |
| `saveAndFlush` trả ID | JPA đã đồng bộ | Transaction bao ngoài vẫn có thể rollback |
| Commit báo lỗi constraint | Giao dịch không được xác nhận thành công | Xử lý exception và rollback theo transaction manager |
| Commit báo lỗi mạng | Có thể chưa biết chắc kết quả DB | Xác minh bằng khóa nghiệp vụ/idempotency |
| Callback/email chạy trước commit | Side effect có thể xảy ra dù rollback | Dời sang sau commit hoặc dùng outbox |

## 16. Bài tập thực hành

### Bài 1: SEQUENCE và rollback

Giả sử transaction cấp `id = 55` bằng sequence, sau đó `INSERT` được thực thi thành công nhưng transaction rollback.

**Câu hỏi:** ID 55 có thể còn trong object Java không? Bảng có chắc chắn chứa dòng 55 đã commit không? Sequence có phải trả lại 55 ở lần kế tiếp không?

**Đáp án:** Object Java có thể vẫn giữ 55. Dòng vừa INSERT thuộc transaction đã rollback không phải bản ghi committed. Với sequence như PostgreSQL, giá trị đã lấy thường không được hoàn trả, nên có thể xuất hiện khoảng trống.

### Bài 2: IDENTITY và flush

~~~java
tx.begin();
em.persist(order);
em.flush();

Long id = order.getId(); // 81
tx.rollback();
~~~

**Câu hỏi:** Có thể trả HTTP `201 Created` với kết quả “đơn hàng 81 đã lưu thành công” không?

**Đáp án:** Không. `id = 81` và flush không chứng minh đã commit; thực tế transaction đã rollback.

### Bài 3: Spring transaction ngoài

~~~java
@Transactional
public void checkout() {
    Long id = orderService.createOrder("Laptop");
    inventoryService.reserve(id); // ném RuntimeException
}
~~~

Giả sử `createOrder` tham gia transaction ngoài bằng propagation `REQUIRED`.

**Câu hỏi:** Vì sao `createOrder` trả ID vẫn không chứng minh đơn hàng đã lưu?

**Đáp án:** Transaction ngoài chưa commit khi method con trả ID. Nếu exception làm transaction ngoài rollback, insert của đơn hàng trong cùng transaction bị hủy.

### Bài 4: Query trong cùng context

~~~java
tx.begin();
em.persist(order);
em.flush();

PurchaseOrder same =
    em.find(PurchaseOrder.class, order.getId());
~~~

**Câu hỏi:** `same != null` có nghĩa transaction khác sẽ nhìn thấy bản ghi không?

**Đáp án:** Không. Persistence context có thể trả entity từ first-level cache; bản ghi chưa commit còn chịu isolation của transaction khác.

### Bài 5: Retry sau lỗi mạng

Sau khi ứng dụng gửi lệnh `COMMIT`, kết nối bị mất. Ứng dụng nhận exception, nhưng chưa biết database đã commit hay chưa.

**Câu hỏi:** Có nên gửi lại toàn bộ thao tác tạo đơn với ID mới ngay lập tức?

**Đáp án:** Không nên. Nếu giao dịch đầu đã commit, thao tác lại có thể tạo đơn trùng. Nên dùng idempotency key hoặc mã nghiệp vụ duy nhất để tra cứu và xử lý retry có kiểm soát.

### Bài 6: Số khóa bị nhảy

Database lưu đơn hàng có ID 100, 102 và 105, thiếu 101, 103 và 104.

**Câu hỏi:** Đây có phải bằng chứng các đơn bị thiếu đã bị xóa?

**Đáp án:** Không. Các khoảng trống có thể là số được cấp cho transaction rollback, lỗi insert, sequence cache hoặc cơ chế tối ưu cấp phát. Không thể rút ra lịch sử nghiệp vụ chỉ từ dãy khóa.

## 17. Những nguyên tắc cần ghi nhớ

~~~text
Có object Java
       |
       v
Có giá trị ID
       |  ID có thể đến từ sequence, identity,
       |  UUID, bảng generator hoặc code tự gán
       v
SQL INSERT được thực thi
       |  Transaction vẫn có thể rollback
       v
COMMIT trả thành công
       |
       v
Các thay đổi trong transaction đã được xác nhận
~~~

- **`@Id` và `@GeneratedValue` xác định cách định danh entity**, không báo trạng thái transaction.
- **`persist` đưa entity mới vào quá trình persistence**, không tự chứng minh SQL đã chạy hoặc đã commit.
- **`flush` đồng bộ SQL nhưng không thay thế commit**; các lỗi vẫn có thể xảy ra sau flush.
- **Commit thành công là ranh giới xác nhận giao dịch DB**; các side effect ngoài DB cần cơ chế bảo đảm riêng.
- **Rollback có thể hủy bản ghi mà không thu hồi ID đã cấp**, gây khoảng trống bình thường trong sequence/identity.
- **SEQUENCE, IDENTITY, TABLE, UUID và AUTO khác nhau về thời điểm cấp khóa**, nhưng cùng tuân theo sự phân biệt giữa ID và transaction.
- **Spring `saveAndFlush` có thể trả ID trong transaction chưa kết thúc**; xác định giao dịch ngoài cùng trước khi báo nghiệp vụ thành công.
- **Đừng dùng khóa kỹ thuật làm số chứng từ bắt buộc liên tục** hoặc làm tín hiệu đã hoàn tất thanh toán/giao hàng.
- **Khi commit có kết quả chưa xác định**, dùng khóa nghiệp vụ/idempotency và cơ chế xác minh, không retry tạo bản ghi một cách mù quáng.

Phân biệt đúng **“khóa đã cấp”** và **“dữ liệu đã được commit”** giúp ứng dụng JPA xử lý rollback an toàn, giải thích chính xác các khoảng trống trong dãy khóa, thiết kế API tạo bản ghi đáng tin cậy và tránh thông báo thành công khi giao dịch vẫn có thể thất bại.
