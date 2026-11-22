# Sinh khóa bằng SEQUENCE và cấu hình `SequenceGenerator` trong JPA

## 1. Khóa chính được sinh tự động để làm gì?

Trong ứng dụng dùng **Jakarta Persistence (JPA)**, mỗi entity cần có **định danh** (*identifier*, thường là khóa chính của một hàng trong bảng quan hệ). Ví dụ mỗi đơn mua hàng `PurchaseOrder` có một thuộc tính `id` kiểu `Long` được ánh xạ đến cột `purchase_orders.id`.

Nếu ứng dụng tự tính khóa theo cách như `MAX(id) + 1`, hai transaction chạy đồng thời có thể cùng nhìn thấy cùng một giá trị lớn nhất rồi cố gắng chèn hai bản ghi trùng khóa. Database còn phải giải quyết cạnh tranh trên bảng dữ liệu. Việc tự cấp mã như vậy dễ dẫn đến lỗi đồng thời và khó mở rộng.

Một lựa chọn tốt với những hệ quản trị có hỗ trợ là **database sequence**: đối tượng nằm trong database, chuyên cấp ra các số theo một quy tắc tăng. JPA sử dụng:

- `@Id` để xác định thuộc tính khóa chính.
- `@GeneratedValue(strategy = GenerationType.SEQUENCE, generator = "...")` để yêu cầu sinh định danh theo chiến lược **SEQUENCE**.
- `@SequenceGenerator` để cấu hình **generator** mà `@GeneratedValue` tham chiếu: tên, tên database sequence, giá trị khởi đầu và kích thước cấp phát.

Ví dụ ngắn nhất có khai báo rõ ràng:

```java
@Id
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "purchase_order_pk"
)
@SequenceGenerator(
    name = "purchase_order_pk",
    sequenceName = "purchase_order_id_seq",
    allocationSize = 1
)
private Long id;
```

Ở đây, JPA dùng sequence tên `purchase_order_id_seq` trong database để lấy giá trị cho khóa `id`. **Sequence chỉ cấp số; nó không tự chèn hàng vào bảng.** JPA provider vẫn chịu trách nhiệm thực hiện SQL `INSERT` để lưu entity.

Bài học này tập trung vào **khóa và chiến lược sinh khóa** trong JPA. Mã minh họa dùng gói `jakarta.persistence`; tài liệu JPA cũ dùng `javax.persistence` với API tương đương. Hãy chọn dependency API và provider nhất quán với phiên bản của dự án.

## 2. Database SEQUENCE là gì?

### 2.1. Sequence là đối tượng riêng của database

Sequence được hệ quản trị dùng để cấp giá trị số. Nó thường được khai báo độc lập với bảng:

```sql
CREATE SEQUENCE purchase_order_id_seq
    START WITH 1
    INCREMENT BY 1;
```

DDL này minh họa cú pháp thường được các hệ quản trị có hỗ trợ sequence chấp nhận. Cú pháp đầy đủ, giới hạn giá trị, quyền truy cập, cách cache và từ khóa cụ thể có thể khác nhau giữa các database.

Với PostgreSQL, có thể minh họa việc xin một số trực tiếp:

```sql
SELECT nextval('purchase_order_id_seq');
```

Một số hệ quản trị khác có cú pháp riêng; ví dụ Oracle truyền thống dùng biểu thức `purchase_order_id_seq.NEXTVAL`. Trong ứng dụng JPA, code Java không cần trực tiếp gọi `nextval`: provider tạo câu lệnh SQL thích hợp theo SQL dialect.

Sequence thông thường có các đặc trưng:

- **Có state cấp số riêng** với dữ liệu của bảng.
- **Hỗ trợ concurrent access**: nhiều phiên hoặc tiến trình có thể xin các giá trị khác nhau.
- **Có cấu hình bước nhảy** (`INCREMENT BY`), khởi đầu, phạm vi và tùy chọn cache theo khả năng database.
- **Không gắn với một bảng duy nhất** theo bản chất: nhiều bảng có thể cùng dùng một sequence nếu được thiết kế như vậy.
- **Không có nghĩa là danh sách ID liên tục, không bị thiếu số**; rollback, cache, lỗi kết nối và cấp phát theo khối đều có thể tạo khoảng trống.

Khóa chính `PRIMARY KEY` / `UNIQUE` trên bảng vẫn cần thiết để database bảo vệ tính duy nhất. Sequence giúp **sinh số**, còn ràng buộc khóa chính bảo vệ **tính toàn vẹn của hàng dữ liệu**.

### 2.2. Luồng sinh khóa qua JPA

```text
             Ứng dụng Java
                  |
                  | new PurchaseOrder(...)
                  | em.persist(order)
                  v
           JPA EntityManager
                  |
                  | Cần cấp identifier
                  v
       SEQUENCE identifier generator
                  |
                  | SQL lấy giá trị từ sequence
                  v
             RDBMS sequence
             purchase_order_id_seq
                  |
                  | Trả một số / cấp một khối số
                  v
        Provider gán order.id
                  |
                  | INSERT theo thời điểm flush/commit
                  v
          Bảng purchase_orders
```

Với chiến lược `SEQUENCE`, provider thường có thể biết ID **trước khi thực hiện `INSERT`** vì số đến từ sequence riêng. Đây là một khác biệt hữu ích so với `IDENTITY`, nơi khóa thường gắn với thao tác insert row.

Tuy vậy, không nên viết logic nghiệp vụ phụ thuộc cứng vào **đúng số lần SQL xin sequence**, **thời điểm provider flush**, hay **số ID cụ thể sau mỗi lần restart**. Những chi tiết đó phụ thuộc vào provider, cơ chế tối ưu và trạng thái thực tế của database sequence.

## 3. Phân tích `@GeneratedValue` và `@SequenceGenerator`

### 3.1. `@GeneratedValue(strategy = SEQUENCE)`

Annotation `@GeneratedValue` được khai báo trên thuộc tính định danh:

```java
@Id
@GeneratedValue(strategy = GenerationType.SEQUENCE)
private Long id;
```

Các thành phần:

- `@Id`: thuộc tính là định danh chính của entity.
- `strategy = GenerationType.SEQUENCE`: chọn cơ chế sinh khóa dựa trên database sequence.
- `generator = "purchase_order_pk"`: nếu khai báo, đây là **tên logic của generator** đã cấu hình qua `@SequenceGenerator`.

`@GeneratedValue` là annotation **kích hoạt cơ chế sinh khóa**. Chỉ khai báo `@SequenceGenerator` nhưng bỏ `@GeneratedValue` thì không tự làm cho `@Id` được sinh bằng sequence.

Để mã rõ ràng và dễ dùng lại, nên định nghĩa generator thay vì dựa vào tên sequence mặc định do provider chọn.

### 3.2. Hai tên dễ nhầm: `name` và `sequenceName`

```java
@SequenceGenerator(
    name = "purchase_order_pk",
    sequenceName = "purchase_order_id_seq",
    allocationSize = 1
)
```

- `name = "purchase_order_pk"` là **tên logic ở phía JPA**. Giá trị này được dùng bởi `@GeneratedValue(generator = "purchase_order_pk")`.
- `sequenceName = "purchase_order_id_seq"` là **tên sequence ở database** mà provider sẽ tham chiếu.

Hai tên **không cần giống nhau**. Ví dụ:

```text
@Entity PurchaseOrder
      |
      +-- @GeneratedValue(generator = "purchase_order_pk")
                    |
                    +-- @SequenceGenerator(name = "purchase_order_pk")
                                         |
                                         +-- sequenceName =
                                             "purchase_order_id_seq"
                                                     |
                                                     v
                                               Database SEQUENCE
```

Nếu `generator` trong `@GeneratedValue` không khớp với `name` của generator đã khai báo, provider có thể báo không tìm thấy generator hoặc dùng cơ chế dự phòng theo quy tắc triển khai; đó không phải cấu hình cần dựa vào.

### 3.3. Các thuộc tính quan trọng của `@SequenceGenerator`

| Thuộc tính | Ý nghĩa | Ghi chú |
|---|---|---|
| `name` | Tên logic để các `@GeneratedValue` tham chiếu. | Nên đặt duy nhất và có ý nghĩa trong persistence unit. |
| `sequenceName` | Tên database sequence được sử dụng. | Nếu bỏ trống, provider/JPA có quy tắc tên mặc định phụ thuộc phiên bản và cấu hình. |
| `schema` | Schema chứa sequence. | Phụ thuộc cách database tổ chức schema và quyền truy cập. |
| `catalog` | Catalog chứa sequence. | Không phải database nào cũng hỗ trợ theo cùng cách. |
| `initialValue` | Giá trị khởi đầu mong muốn khi provider tạo sequence. | **Mặc định 1**; không đặt lại sequence đã tồn tại chỉ bằng cách đổi annotation. |
| `allocationSize` | Số giá trị định danh được generator cấp phát theo một lần phân bổ/nhóm. | **Mặc định 50**; ảnh hưởng cơ chế tối ưu và cần phù hợp với sequence thực tế. |

`@SequenceGenerator` có thể được đặt ở lớp entity hoặc tại thuộc tính định danh được ánh xạ, tùy cách tổ chức metadata của dự án.

Ví dụ đặt ở cấp entity:

```java
@Entity
@SequenceGenerator(
    name = "order_key_generator",
    sequenceName = "order_key_seq",
    initialValue = 1000,
    allocationSize = 1
)
public class PurchaseOrder {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "order_key_generator"
    )
    private Long id;

    protected PurchaseOrder() {}
}
```

Trong đoạn mã này, `initialValue = 1000` có ý nghĩa với **tạo sequence mới** bằng cơ chế sinh schema phù hợp. Nếu `order_key_seq` đã có từ trước, annotation không tự bảo đảm database sẽ khởi đầu lại từ 1000.

### 3.4. Phạm vi của tên generator

Tên generator `@SequenceGenerator(name = ...)` được quản lý trong phạm vi metadata persistence unit. Vì thế, không nên đặt cùng một tên logic cho các định nghĩa generator khác nhau rồi mong annotation trên từng entity giữ chúng độc lập.

Ví dụ nên đặt:

```text
purchase_order_pk -> purchase_order_id_seq
invoice_pk        -> invoice_id_seq
customer_pk       -> customer_id_seq
```

Nếu chủ ý dùng **một sequence chung** để sinh ID cho nhiều entity, có thể thiết kế như vậy, nhưng cần cấu hình rõ ràng, tránh xung đột tên generator, đồng thời hiểu rằng số được cấp sẽ đan xen giữa các bảng.

## 4. Ví dụ entity hoàn chỉnh: đơn mua hàng dùng SEQUENCE

Tạo entity `PurchaseOrder` có khóa chính `Long`, thông tin khách hàng và giá trị đơn hàng:

```java
package com.example.orders;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.SequenceGenerator;
import jakarta.persistence.Table;

import java.math.BigDecimal;

@Entity
@Table(name = "purchase_orders")
@SequenceGenerator(
    name = "purchase_order_pk",
    sequenceName = "purchase_order_id_seq",
    initialValue = 1,
    allocationSize = 1
)
public class PurchaseOrder {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "purchase_order_pk"
    )
    private Long id;

    @Column(name = "customer_name", nullable = false, length = 120)
    private String customerName;

    @Column(
        name = "total_amount",
        nullable = false,
        precision = 15,
        scale = 2
    )
    private BigDecimal totalAmount;

    protected PurchaseOrder() {
        // Constructor không tham số cho JPA.
    }

    public PurchaseOrder(String customerName, BigDecimal totalAmount) {
        if (customerName == null || customerName.isBlank()) {
            throw new IllegalArgumentException("Tên khách hàng không hợp lệ");
        }
        if (totalAmount == null || totalAmount.signum() < 0) {
            throw new IllegalArgumentException("Tổng tiền không hợp lệ");
        }
        this.customerName = customerName;
        this.totalAmount = totalAmount;
    }

    public Long getId() {
        return id;
    }

    public String getCustomerName() {
        return customerName;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }
}
```

Các quyết định thiết kế chính:

1. `Long` được dùng cho khóa tự sinh. Entity mới thường có `id == null`, giúp phân biệt đối tượng chưa được cấp ID.
2. `@SequenceGenerator` ở mức class cho phép đọc cấu hình cấp ID ngay cạnh entity.
3. `@GeneratedValue(generator = "purchase_order_pk")` tham chiếu **đúng tên logic** của generator.
4. `sequenceName = "purchase_order_id_seq"` xác định database sequence cần có hoặc cần được provider tạo.
5. `allocationSize = 1` ưu tiên cách hiểu đơn giản: mỗi lần xin số mới theo cơ chế sequence mà provider sử dụng, không tối ưu cấp theo khối.
6. Cột tiền `BigDecimal` dùng `DECIMAL(15,2)` theo ý định ánh xạ; nó độc lập với việc sinh khóa `SEQUENCE`.

Tên bảng `purchase_orders` được chọn để tránh trùng với từ khóa SQL như `ORDER` trong nhiều hệ quản trị.

## 5. Cấu hình database và persistence unit

Có hai cách thường gặp để chuẩn bị sequence và bảng: **tự quản lý DDL bằng migration**, hoặc **cho provider sinh schema ở môi trường thực hành**. Không nên đồng thời tạo cùng một object theo hai nguồn độc lập mà không kiểm soát.

### 5.1. DDL tự tạo trước

Một ví dụ SQL dành cho hệ quản trị có hỗ trợ cú pháp tương ứng:

```sql
CREATE SEQUENCE purchase_order_id_seq
    START WITH 1
    INCREMENT BY 1;

CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    customer_name VARCHAR(120) NOT NULL,
    total_amount DECIMAL(15, 2) NOT NULL
);
```

Đây là DDL **minh họa** để khớp với entity `PurchaseOrder` và `allocationSize = 1`.

Với một số hệ quản trị, có thể bổ sung `CACHE`, `MINVALUE`, `MAXVALUE`, `CYCLE` hoặc `NO CYCLE` khi tạo sequence. Tên và semantics chính xác cần theo tài liệu của database đó.

Quan sát đặc biệt: cột `id` không nhất thiết phải có `IDENTITY` hay `AUTO_INCREMENT`. Với JPA `SEQUENCE`, provider **lấy ID trước rồi gửi ID như giá trị của cột `id` trong câu lệnh INSERT**.

Nếu dùng migration tool như Flyway hoặc Liquibase, script tạo sequence và bảng nên nằm trong lịch sử migration và phù hợp với cấu hình entity. Với production, đây thường là cách kiểm soát thay đổi schema tốt hơn.

### 5.2. `persistence.xml` minh họa cho Java SE và H2

Trong ví dụ thực hành Java SE, có thể dùng cơ sở dữ liệu H2 trong bộ nhớ:

```xml
<!-- src/main/resources/META-INF/persistence.xml -->
<?xml version="1.0" encoding="UTF-8"?>
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             version="3.1">
    <persistence-unit name="ordersPU"
                      transaction-type="RESOURCE_LOCAL">
        <class>com.example.orders.PurchaseOrder</class>

        <properties>
            <property name="jakarta.persistence.jdbc.driver"
                      value="org.h2.Driver"/>
            <property name="jakarta.persistence.jdbc.url"
                      value="jdbc:h2:mem:orders;DB_CLOSE_DELAY=-1"/>
            <property name="jakarta.persistence.jdbc.user"
                      value="sa"/>
            <property name="jakarta.persistence.jdbc.password"
                      value=""/>

            <property
                name="jakarta.persistence.schema-generation.database.action"
                value="drop-and-create"/>
        </properties>
    </persistence-unit>
</persistence>
```

Ví dụ này cần ba nhóm dependency phù hợp: **Jakarta Persistence API**, **JPA provider** và **H2 JDBC driver**. Thông số `drop-and-create` dành cho **môi trường thử nghiệm**: nó có thể xóa và tạo lại schema, làm mất dữ liệu cũ.

Nếu muốn dùng DDL thủ công ở mục 5.1, hãy thiết lập schema-generation tương ứng (ví dụ `none` hoặc không bật tính năng sinh schema), tạo đối tượng database qua migration, rồi khởi động JPA. Dù theo cách nào, cấu hình entity và database sequence cần thống nhất về tên, bước nhảy và trạng thái hiện tại.

### 5.3. Sequence ở schema khác

Khi database có nhiều schema, có thể định nghĩa:

```java
@SequenceGenerator(
    name = "purchase_order_pk",
    sequenceName = "purchase_order_id_seq",
    schema = "sales",
    allocationSize = 1
)
```

Ý định là dùng sequence `sales.purchase_order_id_seq`. Nếu bảng cũng ở schema `sales`, cần khai báo mapping bảng phù hợp, ví dụ `@Table(name = "purchase_orders", schema = "sales")`.

Tên được trích dẫn/không trích dẫn, chữ hoa/chữ thường, quyền gọi sequence và default schema có thể khác tùy database. Khi chạy trong môi trường có schema riêng, nên kiểm tra tên object thực tế và quyền của tài khoản ứng dụng.

## 6. Từ `new` đến `persist`, `flush` và `commit`

Để thấy cách sinh khóa diễn ra trong một đơn vị công việc, xét ví dụ Java SE dùng transaction cục bộ:

```java
package com.example.orders;

import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;
import jakarta.persistence.Persistence;

import java.math.BigDecimal;

public class SequenceDemo {

    public static void main(String[] args) {
        EntityManagerFactory emf =
                Persistence.createEntityManagerFactory("ordersPU");

        try {
            EntityManager em = emf.createEntityManager();

            try {
                EntityTransaction tx = em.getTransaction();

                try {
                    tx.begin();

                    PurchaseOrder order = new PurchaseOrder(
                            "Công ty An Bình",
                            new BigDecimal("1250000.00")
                    );

                    // Trước khi persist: object mới, id thường null.
                    em.persist(order);

                    // Provider lấy ID theo cơ chế SEQUENCE.
                    // Bảo đảm đồng bộ dữ liệu đang chờ trong transaction.
                    em.flush();

                    Long generatedId = order.getId();
                    System.out.println("ID được cấp: " + generatedId);

                    tx.commit();
                } catch (RuntimeException ex) {
                    if (tx.isActive()) {
                        tx.rollback();
                    }
                    throw ex;
                }
            } finally {
                em.close();
            }
        } finally {
            emf.close();
        }
    }
}
```

Các mốc quan trọng:

- `new PurchaseOrder(...)` tạo object Java ở trạng thái *new/transient*.
- `em.persist(order)` đưa entity vào persistence context. Với SEQUENCE, JPA provider thường lấy ID từ sequence khi cần cấp định danh, có thể trước khi phát `INSERT`.
- `em.flush()` yêu cầu provider đồng bộ những thay đổi đang chờ. Flush **không xác nhận transaction**.
- `tx.commit()` xác nhận transaction; nếu có lỗi thì mã xử lý rollback khi transaction vẫn hoạt động.
- `em.close()` đóng entity manager của đơn vị công việc; `emf.close()` đóng factory lúc kết thúc chương trình.

Không nên dựa vào việc ID là `1` ở lần chạy đầu. Giá trị thực tế phụ thuộc sequence đã có dữ liệu hay chưa, có thực thể/phiên khác xin số hay không và cơ chế cấp phát của provider/database.

Trong **Jakarta EE dùng JTA**, entity manager thường do container cấp bằng `@PersistenceContext`, transaction do container quản lý. Khi đó không dùng `em.getTransaction().begin()` trong service. Cách generator sinh ID bằng SEQUENCE vẫn là nội dung mapping JPA, không phụ thuộc vào việc transaction được quản lý theo RESOURCE_LOCAL hay JTA.

## 7. `allocationSize`: cấp phát khóa theo khối

### 7.1. Vì sao cần tối ưu cấp phát?

Nếu mỗi entity mới đều yêu cầu một lệnh SQL riêng để xin giá trị sequence, ứng dụng ghi hàng nghìn entity sẽ phải thêm nhiều lượt đi lại giữa application và database.

`@SequenceGenerator(allocationSize = N)` cung cấp tham số để provider **tối ưu quá trình cấp ID theo nhóm**. Mặc định theo annotation chuẩn là **50**; giá trị thực tế có thể được thay đổi tường minh trong mapping.

```java
@SequenceGenerator(
    name = "purchase_order_pk",
    sequenceName = "purchase_order_id_seq",
    allocationSize = 50
)
```

Một provider có chiến lược pooled phù hợp có thể xin giá trị sequence tương đối ít lần, rồi gán nhiều ID từ nhóm đã được cấp. Điều đó có thể giúp giảm round-trip SQL khi insert nhiều entity, đặc biệt khi dùng JDBC batching.

### 7.2. So sánh `allocationSize = 1` và `allocationSize = 50`

| Cấu hình | Cách hiểu thực tế | Ưu điểm | Đổi lại |
|---|---|---|---|
| `allocationSize = 1` | Cấp từng ID theo từng nhu cầu thông thường; không sử dụng khối ID lớn ở mức JPA. | Dễ hiểu và dễ đồng bộ với sequence `INCREMENT BY 1`. | Nhiều lượt xin sequence hơn khi ghi rất nhiều entity. |
| `allocationSize = 50` | Provider có thể quản lý từng khối khoảng 50 định danh với thuật toán tối ưu của nó. | Có thể giảm số lần chạm sequence và tăng thông lượng insert. | Phải hiểu thuật toán của provider và đối chiếu cấu hình sequence database; có thể tạo khoảng trống ID lớn hơn. |

Sơ đồ mang tính ý tưởng, không phải log SQL bắt buộc của mọi provider:

```text
allocationSize = 1
  persist(A) -> lấy ID từ sequence
  persist(B) -> lấy ID từ sequence
  persist(C) -> lấy ID từ sequence

allocationSize = 50 (provider dùng cơ chế pooled phù hợp)
  yêu cầu một giá trị/khối từ database sequence
       |
       +-- cấp các ID cho nhiều entity trong khối
       |
  khi hết khối -> yêu cầu giá trị/khối tiếp theo
```

**`allocationSize` không đồng nghĩa với `CACHE` của database sequence.**

- `allocationSize` là cấu hình **ở tầng JPA generator/provider**.
- `CACHE` là cấu hình **ở tầng database** giúp sequence giữ sẵn các giá trị để giảm chi phí cấp số nội bộ.

Hai cơ chế khác tầng và có thể được dùng cùng nhau. Một sequence có `CACHE 20` không tự có nghĩa `allocationSize = 20`.

### 7.3. Đồng bộ `allocationSize` với bước nhảy của sequence

Với cấu hình minh họa `allocationSize = 1`, DDL thường tương ứng:

```sql
CREATE SEQUENCE purchase_order_id_seq
    START WITH 1
    INCREMENT BY 1;
```

Với **Hibernate dùng trình tối ưu pooled/pooled-lo tương ứng**, nhiều cấu hình khuyến nghị để sequence database có bước nhảy phù hợp với kích thước cấp phát, ví dụ:

```java
@SequenceGenerator(
    name = "purchase_order_pk",
    sequenceName = "purchase_order_id_seq",
    allocationSize = 50
)
```

```sql
CREATE SEQUENCE purchase_order_id_seq
    START WITH 1
    INCREMENT BY 50;
```

Đây là **cặp cấu hình minh họa cho cơ chế pooled của provider**, không phải quy tắc SQL độc lập có thể áp dụng máy móc cho mọi provider/optimizer. Hibernate có thể kiểm tra mức `INCREMENT BY` thực tế và báo lỗi khi không khớp với mapping; các provider/phiên bản khác có thể dùng thuật toán cấp phát khác.

Nguyên tắc vận hành là **xác định provider và thuật toán tối ưu đang dùng, rồi tạo sequence theo đúng cấu hình được provider hỗ trợ**. Nếu dùng sequence đã có từ trước, đừng chỉ tăng `allocationSize` trên annotation mà bỏ qua bước nhảy và trạng thái sequence ở database.

### 7.4. Vì sao có khoảng trống ID?

Giả sử provider đã giữ một nhóm giá trị ID trong bộ nhớ. Ứng dụng bị dừng trước khi dùng hết nhóm; số chưa sử dụng có thể bị bỏ qua. Thậm chí khi không có pooling, số sequence đã cấp có thể **không được hoàn lại khi transaction rollback** (điển hình với PostgreSQL và Oracle).

Vì thế:

```text
ID được cấp: 101, 102, 103, 107, 108, ...
                         ^^^
                Khoảng trống hoàn toàn có thể xảy ra
```

Không nên xem khoảng trống là bằng chứng mất bản ghi. Trong thiết kế JPA, ID do sequence sinh nên được hiểu là **định danh kỹ thuật**, không phải bộ đếm nghiệp vụ liên tục.

## 8. Khóa tự sinh và transaction: hai vòng đời khác nhau

Một transaction có thể lấy ID trước khi INSERT hoặc trước khi commit. Nếu transaction rollback, database có thể hủy bản ghi nhưng không hoàn lại số đã lấy từ sequence.

Ví dụ tình huống:

```text
Transaction T1:
  xin ID = 100
  INSERT purchase_orders(id=100)
  một thao tác khác gặp lỗi
  ROLLBACK

Transaction T2:
  xin ID = 101
  INSERT purchase_orders(id=101)
  COMMIT

Kết quả:
  bảng có order id=101
  id=100 không có bản ghi đã commit
```

Đây là hành vi thường gặp và **đúng** đối với sequence. Không thể dựa vào `id` để biết có bao nhiêu giao dịch thành công, cũng không thể dùng `MAX(id)` làm số lượng bản ghi.

Nếu nghiệp vụ bắt buộc chứng từ có số **liên tục, kiểm soát được khoảng trống** (ví dụ số hóa đơn theo một chế độ pháp lý cụ thể), hãy thiết kế cơ chế cấp **số chứng từ nghiệp vụ** riêng với quy trình phát hành, khóa, hủy và đối soát thích hợp. Khóa chính do `SEQUENCE` sinh vẫn có thể tồn tại song song.

### 8.1. ID tăng không bảo đảm thứ tự commit

Hai transaction chạy đồng thời có thể xin ID theo một thứ tự rồi commit theo thứ tự khác:

```text
T1 xin id=501, xử lý chậm
T2 xin id=502, commit trước
T1 commit sau
```

Do đó, `ORDER BY id` có thể là một cách sắp xếp theo giá trị khóa nhưng **không phải bảo đảm thời gian commit thực tế**. Nếu cần sắp xếp theo thời điểm nghiệp vụ, lưu thuộc tính thời gian/tính thứ tự phù hợp và có quy tắc rõ ràng cho tình huống trùng thời gian.

### 8.2. Sequence và đồng thời nhiều instance

Database sequence được thiết kế để phối hợp cấp giá trị giữa các kết nối/phiên trong cùng database. Khi nhiều instance ứng dụng cùng dùng một sequence:

- Mỗi instance phải dùng mapping và thuật toán generator **tương thích**.
- Nếu dùng pooling, các khối ID không được chồng nhau do cấu hình lệch giữa instance.
- Trong quá trình triển khai phiên bản mới, việc thay `allocationSize` mà các instance cũ còn chạy có thể gây rủi ro nếu các thuật toán không tương thích.
- Ràng buộc `PRIMARY KEY` của database vẫn là lớp bảo vệ cuối cùng.

Không tự tạo ID bằng cách đọc giá trị lớn nhất trong bảng rồi cộng một, ngay cả khi ứng dụng có vẻ chỉ chạy một instance.

## 9. So sánh `SEQUENCE` với `IDENTITY`, `TABLE` và `AUTO`

JPA hỗ trợ nhiều chiến lược sinh khóa và lựa chọn phù hợp phụ thuộc vào khả năng database.

| Chiến lược | Cơ chế ý tưởng | Điểm cần lưu ý |
|---|---|---|
| `GenerationType.SEQUENCE` | Lấy định danh từ database sequence. | Cần database/provider hỗ trợ sequence; có thể tối ưu cấp phát theo nhóm và thường biết ID trước INSERT. |
| `GenerationType.IDENTITY` | Khóa sinh trực tiếp khi insert hàng, ví dụ identity/auto-increment column. | ID thường phải đợi thao tác INSERT; cách thực thi có thể hạn chế tối ưu batching của provider. |
| `GenerationType.TABLE` | Dùng bảng riêng để lưu trạng thái cấp khóa. | Có thể chạy trên nhiều database hơn nhưng có thêm truy vấn/khóa trên bảng cấp ID, cần cân nhắc cạnh tranh. |
| `GenerationType.AUTO` | Để provider chọn chiến lược dựa vào database và cấu hình. | Ít cấu hình hơn nhưng hành vi/DDL cụ thể phụ thuộc provider, phiên bản và dialect. |

Ví dụ hai cách khai báo:

```java
// Dùng database sequence:
@Id
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "purchase_order_pk"
)
private Long id;
```

```java
// Dùng identity column:
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
```

Cả hai đều phục vụ sinh khóa chính. **Chúng không phải cú pháp thay thế hoàn toàn** vì chiến lược cấp số, schema và thời điểm phát lệnh SQL khác nhau.

### 9.1. Hệ quản trị nào phù hợp với SEQUENCE?

Các RDBMS như PostgreSQL, Oracle, H2 và SQL Server có hỗ trợ sequence với cú pháp/cách sử dụng khác nhau. Không phải mọi hệ quản trị đều có sequence độc lập giống nhau; chẳng hạn MySQL phổ biến dựa vào `AUTO_INCREMENT` cho định danh tăng tự động, còn MariaDB và các hệ khác có mức hỗ trợ riêng.

Nếu chọn `SEQUENCE` trên database hoặc dialect không hỗ trợ, ứng dụng có thể thất bại khi bootstrap generator hoặc khi xin ID. Kiểm tra dialect và khả năng của **phiên bản RDBMS đang triển khai**, thay vì suy luận từ việc SQL “gần giống” nhau.

### 9.2. Lợi ích của SEQUENCE đối với batch insert

Với `IDENTITY`, provider thường cần đưa hàng xuống database để có khóa mới, nên trong một số cấu hình khó trì hoãn INSERT để gộp batch. Với `SEQUENCE`, có thể xin ID trước rồi đưa nhiều câu INSERT vào batch, đặc biệt khi dùng `allocationSize` phù hợp.

Đó là **khả năng tối ưu**, không phải bảo đảm rằng chỉ cần đổi annotation thành `SEQUENCE` thì batching tự bật. Còn phụ thuộc:

- Cấu hình JDBC batching của provider.
- Transaction boundary, flush mode và khối lượng entity.
- Cơ chế ID generator/optimizer cụ thể.
- Quan hệ cascade, khóa ngoại và thứ tự INSERT.
- Driver và database thực tế.

## 10. Những cách dùng `@SequenceGenerator` thường gặp

### 10.1. Generator khai báo ngay trên field `id`

```java
@Entity
public class Invoice {

    @Id
    @SequenceGenerator(
        name = "invoice_pk",
        sequenceName = "invoice_id_seq",
        allocationSize = 1
    )
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "invoice_pk"
    )
    private Long id;

    protected Invoice() {}
}
```

Kiểu khai báo này đặt mọi thông tin cấp ID cạnh field khóa chính. Nó phù hợp với entity đơn giản.

### 10.2. Generator khai báo ở cấp entity

```java
@Entity
@SequenceGenerator(
    name = "invoice_pk",
    sequenceName = "invoice_id_seq",
    allocationSize = 1
)
public class Invoice {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "invoice_pk"
    )
    private Long id;

    protected Invoice() {}
}
```

Hai cách đều nhằm liên kết `@GeneratedValue` với generator được đặt tên; chọn cách nhất quán theo quy ước codebase.

### 10.3. Định nghĩa ID ở `@MappedSuperclass`

Nếu nhiều entity có chung dạng khóa, có thể tổ chức một superclass cung cấp mapping:

```java
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.MappedSuperclass;
import jakarta.persistence.SequenceGenerator;

@MappedSuperclass
@SequenceGenerator(
    name = "shared_pk_generator",
    sequenceName = "shared_entity_id_seq",
    allocationSize = 1
)
public abstract class BaseEntity {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "shared_pk_generator"
    )
    protected Long id;

    protected BaseEntity() {}

    public Long getId() {
        return id;
    }
}
```

Lớp con:

```java
@Entity
@Table(name = "audit_events")
public class AuditEvent extends BaseEntity {

    @Column(nullable = false)
    private String action;

    protected AuditEvent() {}
}
```

Đây là một thiết kế **dùng chung sequence** cho các lớp con theo cấu hình kế thừa. Nó có thể phù hợp nếu muốn định danh toàn cục trên nhiều bảng, nhưng không phải lúc nào cũng nên dùng. Nếu mỗi bảng cần sequence riêng, cần tổ chức generator/mapping tương ứng để tránh ép mọi entity vào cùng sequence.

**`@MappedSuperclass` không phải entity độc lập**; nó cung cấp metadata cho các entity kế thừa. Entity con mới có bảng và vòng đời persistence của riêng mình.

### 10.4. Khóa kép không dùng mẫu này một cách máy móc

Mẫu `@Id + @GeneratedValue(strategy = SEQUENCE)` được dùng điển hình cho **khóa chính đơn** có kiểu số tương thích.

Nếu entity có khóa tổng hợp `@EmbeddedId` hoặc nhiều thuộc tính `@Id`, không nên giả định có thể đặt `@GeneratedValue` trực tiếp lên từng phần rồi mong JPA portable tự cấp số cho cấu trúc khóa. Thiết kế khóa tổng hợp thường cần cơ chế định danh riêng hoặc mapping chuyên biệt được hỗ trợ rõ ràng.

## 11. Sequence đã tồn tại: đồng bộ cấu hình với dữ liệu thật

Trong dự án mới, sequence có thể bắt đầu từ 1 vì bảng trống. Trong dự án thực tế, bảng có thể đã có hàng:

```text
purchase_orders
+-----+------------------+
| id  | customer_name    |
+-----+------------------+
| 100 | Khách A          |
| 101 | Khách B          |
| 102 | Khách C          |
+-----+------------------+
```

Nếu tạo sequence mới lại bắt đầu cấp `1`, một số giá trị ban đầu có thể chưa đụng hàng, nhưng khi tiến đến `100` sẽ vi phạm khóa chính. Vì vậy cần **đồng bộ giá trị tiếp theo của sequence với dữ liệu và thuật toán cấp phát**.

Quy trình tư duy khi migration:

1. Đọc phạm vi khóa hiện đang được lưu ở bảng và xác định các thành phần khác cũng dùng sequence đó.
2. Xác định provider, `allocationSize`, thuật toán optimizer và bước nhảy `INCREMENT BY` được cấu hình.
3. Thiết kế cách đặt sequence sang trạng thái an toàn với mọi ID đã có, bao gồm trường hợp nhiều instance đang chạy và đã giữ khối ID.
4. Thực hiện thay đổi bằng migration có kiểm soát, thích hợp với cú pháp database.
5. Đảm bảo các phiên bản ứng dụng đang chạy thống nhất cấu hình generator trước khi sử dụng sequence mới.

Lệnh điều chỉnh sequence khác nhau giữa PostgreSQL, Oracle và các database khác. Một số hỗ trợ `ALTER SEQUENCE ... RESTART`, một số hỗ trợ hàm đặt trạng thái hoặc cách thay đổi increment rồi gọi `NEXTVAL`. Không nên sao chép một lệnh reset sequence từ database này sang database khác mà không đánh giá semantics của nó.

### 11.1. `initialValue` không phải cơ chế sửa dữ liệu lịch sử

```java
@SequenceGenerator(
    name = "purchase_order_pk",
    sequenceName = "purchase_order_id_seq",
    initialValue = 10000,
    allocationSize = 1
)
```

Thay đổi `initialValue` trong source **không bảo đảm** sequence tồn tại sẽ chuyển ngay sang giá trị 10000 khi ứng dụng deploy. Thuộc tính này thể hiện giá trị ban đầu cho **tạo sequence** theo khả năng schema generation của provider. Sequence đã tồn tại cần được điều chỉnh bằng DDL/migration phù hợp.

### 11.2. Đảm bảo quyền truy cập sequence

Một tài khoản ứng dụng có thể được cấp quyền INSERT vào bảng nhưng **chưa được cấp quyền lấy số từ sequence**. Khi đó, provider có thể thất bại lúc `persist` hoặc lúc cấp ID, dù bảng vẫn có thể ghi nếu cung cấp khóa thủ công.

Tùy database, cần quyền như `USAGE` hoặc `SELECT` trên sequence, hoặc quyền tương đương. Quản lý quyền schema cũng phải xét khi ứng dụng dùng tên sequence có schema riêng.

## 12. Lỗi thường gặp và nguyên nhân

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Generator không được tìm thấy | `@GeneratedValue(generator = "...")` khác `@SequenceGenerator(name = "...")`. | Dùng đúng một tên logic; đảm bảo generator được provider khám phá. |
| Báo sequence không tồn tại | `sequenceName` sai, schema sai, sequence chưa được tạo. | Kiểm tra database metadata, tên được trích dẫn, schema và migration. |
| Báo thiếu quyền với sequence | User database có quyền bảng nhưng thiếu quyền đọc/cấp giá trị sequence. | Cấp quyền sequence phù hợp trên đúng schema. |
| Khởi tạo provider báo mismatch giữa allocation và increment | `allocationSize` không tương thích với `INCREMENT BY` theo optimizer của provider. | Đồng bộ cấu hình và schema theo tài liệu đúng provider/phiên bản. |
| ID bất ngờ nhảy xa | Sequence cache, rollback, pooling hoặc ứng dụng khác cùng xin ID. | Hiểu ID là định danh kỹ thuật; không yêu cầu số liên tiếp. |
| `Duplicate key` dù đã dùng SEQUENCE | Sequence đang ở giá trị cũ, nhiều ứng dụng dùng cấu hình generator không nhất quán, hoặc ID bị gán thủ công. | Kiểm tra dữ liệu/sequence hiện có và thiết kế migration an toàn. |
| `initialValue = 1000` nhưng ID không bắt đầu từ 1000 | Sequence đã tồn tại hoặc provider không tái tạo sequence. | Kiểm tra trạng thái sequence; điều chỉnh bằng migration. |
| Mã chạy trên H2 nhưng lỗi trên database khác | DB đích không hỗ trợ sequence hoặc DDL/dialect khác. | Kiểm tra RDBMS, version và provider SQL dialect. |
| `@SequenceGenerator` có nhưng ID không được sinh | Thiếu `@GeneratedValue` hoặc không liên kết generator đúng. | Dùng cả `@Id`, `@GeneratedValue` và generator phù hợp. |
| Hibernate không batch INSERT như kỳ vọng | Chưa bật batching, entity graph/optimizer không phù hợp hoặc các yếu tố khác. | Xem cấu hình batch và chiến lược khóa ở cấp provider, không chỉ annotation. |
| ID đã có rồi nhưng transaction rollback | Sequence cấp ID độc lập với commit transaction. | Đây thường là hành vi đúng; không tái sử dụng ID đã cấp theo suy đoán. |
| Dùng `MAX(id)+1` để lấp khoảng trống | Cạnh tranh đồng thời và giả định ID phải liên tiếp. | Không tự sinh khóa theo cách này; dùng generator/database sequence. |

### 12.1. Bẫy dễ gặp: để nguyên `allocationSize` mặc định

Đoạn mã:

```java
@SequenceGenerator(
    name = "purchase_order_pk",
    sequenceName = "purchase_order_id_seq"
)
```

**Không có nghĩa mặc định `allocationSize = 1`.** Giá trị mặc định của annotation là **50**. Nếu database sequence đã được tạo với `INCREMENT BY 1`, việc để mặc định có thể không phù hợp với optimizer/provider đang dùng, dù cách khai báo thoạt nhìn rất đơn giản.

Với bài học nhập môn, có thể đặt `allocationSize = 1` tường minh để khớp sequence bước nhảy 1. Khi tối ưu hiệu năng, quyết định tăng lên cần đi kèm kiểm tra cấu hình database và tính tương thích trên các phiên bản đang chạy.

### 12.2. Bẫy khác: lấy số sequence để suy ra số bản ghi

Giả sử gọi sequence 50 lần nhưng có 20 transaction rollback, và một số giá trị được giữ trong cache. Không thể lấy `last_value`, `currval` hoặc ID lớn nhất để suy ra chắc chắn số bản ghi đã commit.

Cần đếm theo dữ liệu thực tế, ví dụ `SELECT COUNT(*) FROM purchase_orders` nếu mục tiêu là số hàng hiện có. Cũng không dùng ID làm thứ tự pháp lý của hóa đơn mà chưa có thiết kế đảm bảo yêu cầu liên tục/đối soát.

## 13. Hướng dẫn chọn cấu hình cho một dự án

Để thiết kế generator mới, có thể đi theo thứ tự:

**Bước 1 — Chọn kiểu định danh.** Với ID số có thể tăng, `Long` thường phù hợp và được hỗ trợ rộng. Khóa chính nên là giá trị kỹ thuật ổn định, không chứa ý nghĩa nghiệp vụ dễ đổi.

**Bước 2 — Kiểm tra database có sequence hay không.** PostgreSQL, Oracle, H2 và SQL Server có cơ chế sequence; với một database không có sequence độc lập tương thích, xem xét `IDENTITY` hoặc chiến lược khác.

**Bước 3 — Quyết định cách quản lý schema.** Ở production, migration tạo sequence và bảng thường rõ ràng hơn việc để provider tự đổi schema. Môi trường lab có thể bật schema generation.

**Bước 4 — Đặt tên rõ ràng.** Ví dụ `purchase_order_pk` cho tên logic và `purchase_order_id_seq` cho object database. Giữ nhất quán trong migration và annotation.

**Bước 5 — Chọn `allocationSize` theo nhu cầu.** Nếu ưu tiên hiểu đơn giản hoặc số lượng ghi thấp, bắt đầu bằng `1`; nếu ghi lớn, đánh giá `50` hoặc giá trị phù hợp theo optimizer và database, không chỉ dựa vào số này đơn lẻ.

**Bước 6 — Cấu hình quyền, schema và trạng thái sequence.** Với bảng đã có dữ liệu, đảm bảo sequence không cấp lại khóa cũ. Với nhiều instance, bảo đảm tất cả dùng cấu hình tương thích.

**Bước 7 — Đặt transaction đúng phạm vi nghiệp vụ.** ID có thể được cấp trước commit; vẫn phải rollback transaction khi lưu thất bại. Không sử dụng ID để khẳng định đơn hàng đã được commit.

### Mẫu cấu hình đơn giản

```java
@Entity
@Table(name = "purchase_orders")
@SequenceGenerator(
    name = "purchase_order_pk",
    sequenceName = "purchase_order_id_seq",
    allocationSize = 1
)
public class PurchaseOrder {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "purchase_order_pk"
    )
    private Long id;

    protected PurchaseOrder() {}
}
```

Đồng bộ DDL:

```sql
CREATE SEQUENCE purchase_order_id_seq
    START WITH 1
    INCREMENT BY 1;
```

Đây là một điểm khởi đầu dễ đọc. Nếu dùng default `allocationSize = 50` hoặc chuyển sang pooling, cần điều chỉnh schema theo cơ chế generator thực tế của provider.

## 14. Câu hỏi tự kiểm tra

**1. `@SequenceGenerator(name = "order_gen", sequenceName = "order_seq")` có nghĩa gì?**

`order_gen` là tên logic mà `@GeneratedValue(generator = "order_gen")` tham chiếu. `order_seq` là tên sequence ở database.

**2. Khai báo `@SequenceGenerator` thôi có tự sinh `@Id` không?**

Không. Thuộc tính định danh cần `@Id` và cấu hình `@GeneratedValue(strategy = GenerationType.SEQUENCE, generator = ...)` phù hợp.

**3. `allocationSize` mặc định là bao nhiêu nếu không khai báo?**

Theo API chuẩn, `allocationSize` mặc định **50**. Cấu hình sequence database phải được đối chiếu với cách provider triển khai cơ chế cấp phát.

**4. `allocationSize = 50` có giống database `CACHE 50` không?**

Không. `allocationSize` kiểm soát nhóm cấp phát ở tầng JPA/provider, còn database `CACHE` là bộ nhớ đệm nội bộ của sequence.

**5. Transaction rollback có làm số từ sequence tự được trả lại không?**

Trong nhiều RDBMS thông dụng, sequence đã cấp số không được rollback cùng bản ghi. Khoảng trống ID là bình thường và không chứng minh bị mất dữ liệu.

**6. Nếu bảng đã có `id = 900` nhưng sequence tiếp tục từ 1 thì sao?**

Có nguy cơ cấp giá trị trùng khóa chính khi sequence tiến đến các giá trị đã có. Cần migration điều chỉnh sequence cho phù hợp dữ liệu và thuật toán cấp phát.

**7. Vì sao `SEQUENCE` có thể hỗ trợ batch insert tốt hơn `IDENTITY`?**

Vì provider thường có thể cấp ID trước khi insert row và có thể gom nhiều INSERT để gửi theo batch. Kết quả thực tế phụ thuộc cấu hình provider, JDBC driver và database.

**8. `SEQUENCE` có thể dùng để bảo đảm số hóa đơn liên tục không?**

Không nên. Rollback, cache, pooling và sự cố có thể tạo khoảng trống. Số hóa đơn có quy tắc pháp lý hoặc nghiệp vụ cần cơ chế riêng.

**9. Nếu `@GeneratedValue(generator="order_gen")` và `@SequenceGenerator(name="another_gen")` khác nhau thì sao?**

Mapping không liên kết tới generator mong muốn. Cần đổi một trong hai để tên logic khớp, đồng thời kiểm tra các generator khác trong cùng persistence unit.

**10. Có thể dùng database sequence với `RESOURCE_LOCAL` và `JTA` không?**

Có. Chiến lược sinh ID thuộc mapping JPA; resource-local và JTA khác nhau ở cách transaction được điều phối. Sequence vẫn được provider gọi theo cấu hình thích hợp.

## 15. Ghi nhớ trọng tâm

`GenerationType.SEQUENCE` cho phép JPA **sinh khóa chính bằng database sequence** thay vì tự tính số từ dữ liệu bảng. Cấu hình cần hiểu đủ ba lớp:

1. **Entity:** `@Id` kết hợp `@GeneratedValue(strategy = SEQUENCE, generator = "...")`.
2. **JPA generator:** `@SequenceGenerator(name = "...", sequenceName = "...", allocationSize = ...)`.
3. **Database:** sequence thực tế có tên, schema, quyền, giá trị hiện tại và bước nhảy phù hợp với provider.

Điểm dễ gây lỗi nhất là **nhầm `name` với `sequenceName`**, **quên mặc định `allocationSize = 50`**, hoặc **đổi annotation mà không cập nhật sequence database đang tồn tại**.

Khi các lớp cấu hình nhất quán, `SEQUENCE` mang lại cách sinh khóa an toàn trong môi trường đồng thời và có khả năng tối ưu cho khối lượng ghi lớn. ID được sinh ra phải được xem là **định danh kỹ thuật có thể có khoảng trống**, còn tính toàn vẹn của bản ghi vẫn do transaction và ràng buộc khóa chính của database bảo vệ.
