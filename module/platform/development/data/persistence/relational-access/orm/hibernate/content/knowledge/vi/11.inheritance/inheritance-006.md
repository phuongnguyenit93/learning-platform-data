# Truy vấn đa hình và các bảng hoặc phép nối được sử dụng trong Hibernate

Một mô hình kế thừa trong Java cho phép khai báo biến kiểu cha nhưng chứa đối tượng của lớp con. Hibernate mở rộng ý tưởng đó sang truy vấn ORM: khi chạy `select p from Payment p`, kết quả có thể chứa `CardPayment`, `BankTransferPayment` và `CashPayment`, dù câu HQL/JPQL chỉ gọi tên `Payment`. Đây là **truy vấn đa hình (polymorphic query)**.

Điều đáng chú ý là **cùng một câu truy vấn Java có thể được Hibernate chuyển thành những cấu trúc SQL rất khác nhau**, tùy chiến lược ánh xạ kế thừa:

- **`SINGLE_TABLE`:** các lớp trong hierarchy cùng nằm ở **một bảng**; một discriminator hoặc cách nhận diện type tương đương cho biết row thuộc lớp con nào.
- **`JOINED`:** dữ liệu chung nằm trong **bảng gốc**, dữ liệu đặc thù của lớp con nằm ở **bảng con có khóa chính đồng thời tham chiếu bảng gốc**; truy vấn cần đọc state của nhiều subtype có thể phải **JOIN** các bảng này.
- **`TABLE_PER_CLASS`:** các lớp concrete có **bảng riêng chứa cả cột kế thừa**; truy vấn từ kiểu cha thường cần **`UNION ALL`** hoặc một cấu trúc SQL tương đương trên các bảng con.
- **`@MappedSuperclass`:** chỉ tái sử dụng mapping cho lớp con; bản thân superclass **không phải entity**, nên không có truy vấn đa hình JPA từ superclass đó.

Bài học tập trung vào cách Hibernate xác định **tập các subtype cần truy vấn, những bảng nào phải truy cập, những phép JOIN/UNION nào được tạo và chi phí đọc dữ liệu**. Việc nhìn SQL thực tế và execution plan là cách kiểm chứng cuối cùng.

> Ví dụ sử dụng `jakarta.persistence` và cơ chế Hibernate ORM 6.x; Hibernate 5 dùng `javax.persistence`. SQL minh họa theo PostgreSQL và được đơn giản hóa để dễ học. Tên alias, cột discriminator, biểu thức `CASE`, cách đưa điều kiện vào nhánh `UNION` và số câu SQL thực tế có thể thay đổi theo Hibernate version, dialect, mapping, fetch plan và optimizer database. Không nên kiểm thử nghiệp vụ bằng cách buộc SQL phải giống hệt một ví dụ minh họa.

## 1. Truy vấn đa hình là truy vấn điều gì?

Giả sử hệ thống thanh toán có cấu trúc lớp:

~~~mermaid
classDiagram
    class Payment {
        <<abstract>>
        Long id
        BigDecimal amount
    }
    class CardPayment {
        String cardLastFour
    }
    class BankTransferPayment {
        String bankReference
    }
    class CashPayment {
        String receiptCode
    }
    Payment <|-- CardPayment
    Payment <|-- BankTransferPayment
    Payment <|-- CashPayment
~~~

Một payment bằng thẻ là `CardPayment`, **đồng thời** là `Payment`. Do đó:

~~~java
List<Payment> payments = entityManager.createQuery(
    "select p from Payment p",
    Payment.class
).getResultList();
~~~

Danh sách này có thể chứa:

~~~text
payments[0] -> CardPayment          (id=101, amount=120.00)
payments[1] -> BankTransferPayment  (id=102, amount=300.00)
payments[2] -> CashPayment          (id=103, amount=45.00)
~~~

Hibernate không trả về một bản sao `Payment` “mất thông tin subtype” nếu hàng dữ liệu đại diện `CardPayment`. Khi truy vấn trả entity, ORM phải xác định **loại concrete** thích hợp để tạo/tra cứu một đối tượng managed trong persistence context.

### Ba dạng truy vấn nên phân biệt

| HQL/JPQL | Ý nghĩa | Tập kết quả |
|---|---|---|
| `from Payment p` | Truy vấn root entity và các subtype thuộc hierarchy. | Payment thuộc mọi lớp concrete nằm dưới `Payment`. |
| `from CardPayment p` | Truy vấn một subtype cụ thể; nếu subtype có lớp con entity, truy vấn cũng có tính đa hình trong nhánh đó. | Các payment kiểu CardPayment hoặc subtype của nó. |
| `from Payment p where type(p) = CardPayment` | Truy vấn root nhưng lọc theo entity type cụ thể. | Các entity có runtime entity type đúng `CardPayment`; khác với phép kiểm tra Java `instanceof` nếu còn nhiều cấp kế thừa. |

Một query **trả subtype qua kiểu cha** có tính đa hình, nhưng bản thân `SELECT` chỉ là biểu thức ORM. SQL được phát sinh phụ thuộc sơ đồ bảng được mapping.

## 2. Mẫu entity chung để đọc các ví dụ

Phần đầu sử dụng `SINGLE_TABLE` để có một mẫu class cụ thể. Trong các phần kế tiếp, ta **thay riêng chiến lược mapping và DDL** nhưng vẫn giữ cùng hierarchy Java. Các phương án là **lựa chọn thay thế nhau**, không phải ba `@Inheritance` đặt đồng thời trên cùng một entity.

~~~java
import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "payment")
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(
    name = "payment_kind",
    discriminatorType = DiscriminatorType.STRING,
    length = 20
)
@SequenceGenerator(
    name = "payment_id_gen",
    sequenceName = "payment_seq",
    allocationSize = 1
)
public abstract class Payment {
    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "payment_id_gen"
    )
    private Long id;

    @Column(name = "amount", nullable = false, precision = 15, scale = 2)
    private BigDecimal amount;

    protected Payment() {}

    protected Payment(BigDecimal amount) {
        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        this.amount = amount;
    }

    public Long getId() { return id; }
    public BigDecimal getAmount() { return amount; }
}
~~~

Ba subtype:

~~~java
import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@DiscriminatorValue("CARD")
public class CardPayment extends Payment {
    @Column(name = "card_last_four", length = 4)
    private String cardLastFour;

    protected CardPayment() {}

    public CardPayment(BigDecimal amount, String cardLastFour) {
        super(amount);
        this.cardLastFour = cardLastFour;
    }

    public String getCardLastFour() { return cardLastFour; }
}

@Entity
@DiscriminatorValue("BANK")
public class BankTransferPayment extends Payment {
    @Column(name = "bank_reference", length = 80)
    private String bankReference;

    protected BankTransferPayment() {}

    public BankTransferPayment(BigDecimal amount, String bankReference) {
        super(amount);
        this.bankReference = bankReference;
    }

    public String getBankReference() { return bankReference; }
}

@Entity
@DiscriminatorValue("CASH")
public class CashPayment extends Payment {
    @Column(name = "receipt_code", length = 80)
    private String receiptCode;

    protected CashPayment() {}

    public CashPayment(BigDecimal amount, String receiptCode) {
        super(amount);
        this.receiptCode = receiptCode;
    }

    public String getReceiptCode() { return receiptCode; }
}
~~~

Mỗi `@Entity` có entity name mặc định là tên lớp Java. `Payment` dù `abstract` vẫn là **entity root hợp lệ để viết query**, khác với `@MappedSuperclass`.

### Tạo dữ liệu và truy vấn trong transaction

~~~java
EntityTransaction tx = entityManager.getTransaction();
tx.begin();

entityManager.persist(
    new CardPayment(new BigDecimal("120.00"), "4242")
);
entityManager.persist(
    new BankTransferPayment(new BigDecimal("300.00"), "BANK-778")
);
entityManager.persist(
    new CashPayment(new BigDecimal("45.00"), "CASH-013")
);

tx.commit();

List<Payment> all = entityManager.createQuery(
    "select p from Payment p order by p.id",
    Payment.class
).getResultList();
~~~

Với `SEQUENCE`, Hibernate có thể lấy ID trước khi thực hiện `INSERT`. Mục tiêu ở đây là so sánh **SQL khi đọc polymorphic entities**, nên ví dụ dùng generator đơn giản; trên hệ thống thật, identifier strategy và batching cũng ảnh hưởng SQL ghi.

## 3. Từ câu truy vấn entity đến SQL của hierarchy

Các bước logic:

~~~mermaid
flowchart TD
    A["JPQL: select p from Payment p"] --> B["Hibernate hiểu Payment là entity root"]
    B --> C["Metadata: các subtype và inheritance strategy"]
    C --> D{"Chiến lược"}
    D -- "SINGLE_TABLE" --> E["SELECT từ một bảng + type discriminator"]
    D -- "JOINED" --> F["SELECT bảng gốc + JOIN bảng subtype cần thiết"]
    D -- "TABLE_PER_CLASS" --> G["SELECT/UNION các bảng concrete"]
    E --> H["JDBC ResultSet"]
    F --> H
    G --> H
    H --> I["Xác định entity type và ID"]
    I --> J["Lắp state của subtype vào managed entity"]
~~~

Hibernate có metadata về `@Inheritance`, các lớp concrete, cột/table của từng thuộc tính, discriminator (nếu có) và các association. Khi xử lý HQL/JPQL, ORM xây dựng biểu diễn truy vấn rồi chuyển sang SQL AST/phương án thực thi tương thích dialect. Kết quả JDBC được dùng để xác định identity và nạp entity thuộc đúng subtype.

**Không phải lúc nào `select p from Payment p` cũng phải lấy tất cả các cột của tất cả bảng subtype.** Nếu query chỉ chọn `p.id`, `count(p)` hoặc một projection DTO, Hibernate có thể dùng SQL đơn giản hơn do không cần xây đầy đủ subtype entity. Truy vấn `select p` trả **entity** và truy vấn `select p.id` trả **scalar** có yêu cầu dữ liệu khác nhau.

Các phần tiếp theo nhìn rõ sự khác biệt đó theo từng inheritance strategy.

## 4. SINGLE_TABLE: một bảng đủ biểu diễn cả hierarchy

### 4.1. Schema

Với `InheritanceType.SINGLE_TABLE`, toàn bộ dữ liệu của mọi `Payment` nằm trong **một** bảng:

~~~sql
CREATE SEQUENCE payment_seq START WITH 1 INCREMENT BY 1;

CREATE TABLE payment (
    id BIGINT PRIMARY KEY,
    amount NUMERIC(15, 2) NOT NULL,
    payment_kind VARCHAR(20) NOT NULL,
    card_last_four VARCHAR(4),
    bank_reference VARCHAR(80),
    receipt_code VARCHAR(80)
);
~~~

Dữ liệu:

~~~text
payment
+-----+--------+--------------+----------------+----------------+--------------+
| id  | amount | payment_kind | card_last_four | bank_reference | receipt_code |
+-----+--------+--------------+----------------+----------------+--------------+
| 101 | 120.00 | CARD         | 4242           | NULL           | NULL         |
| 102 | 300.00 | BANK         | NULL           | BANK-778       | NULL         |
| 103 | 45.00  | CASH         | NULL           | NULL           | CASH-013     |
+-----+--------+--------------+----------------+----------------+--------------+
~~~

Discriminator `payment_kind` cho Hibernate biết row là `CardPayment`, `BankTransferPayment` hay `CashPayment`. Ở root có `@DiscriminatorColumn`; mỗi lớp con có `@DiscriminatorValue` tương ứng. Nếu bỏ cấu hình tường minh, Hibernate có các mặc định về discriminator, nhưng không nên dựa vào tên cột/giá trị mặc định khi schema đã tồn tại.

### 4.2. Truy vấn đa hình từ root

JPQL:

~~~java
List<Payment> payments = entityManager.createQuery(
    "select p from Payment p order by p.id",
    Payment.class
).getResultList();
~~~

SQL minh họa:

~~~sql
SELECT
    p.id,
    p.amount,
    p.payment_kind,
    p.card_last_four,
    p.bank_reference,
    p.receipt_code
FROM payment p
ORDER BY p.id;
~~~

**Không cần JOIN bảng kế thừa hoặc UNION.** SQL đọc một bảng, sau đó Hibernate nhìn `payment_kind` để xác định Java entity subtype khi materialize mỗi row.

Nếu query lọc theo số tiền:

~~~java
List<Payment> large = entityManager.createQuery(
    "select p from Payment p where p.amount >= :min",
    Payment.class
).setParameter("min", new BigDecimal("100.00"))
 .getResultList();
~~~

Database chỉ cần đọc `payment` và dùng `amount`; không có điều kiện subtype thì kết quả vẫn chứa các loại payment.

### 4.3. Truy vấn một lớp con

~~~java
List<CardPayment> cards = entityManager.createQuery(
    "select c from CardPayment c",
    CardPayment.class
).getResultList();
~~~

SQL tương đương:

~~~sql
SELECT p.id, p.amount, p.payment_kind, p.card_last_four
FROM payment p
WHERE p.payment_kind = 'CARD';
~~~

Hibernate dùng discriminator để giới hạn row của subtype. Nếu có nhiều cấp con bên dưới `CardPayment`, điều kiện subtype query phải bao phủ những concrete descendants theo hierarchy; không nhất thiết chỉ là một giá trị discriminator.

### 4.4. Lọc type khi vẫn truy vấn root

~~~java
List<Payment> cards = entityManager.createQuery(
    "select p from Payment p where type(p) = CardPayment",
    Payment.class
).getResultList();
~~~

Với `SINGLE_TABLE`, điều kiện `TYPE` có thể dịch thành:

~~~sql
SELECT ...
FROM payment p
WHERE p.payment_kind = 'CARD';
~~~

Đây là một ưu thế về cấu trúc SQL: bộ lọc theo type có thể dựa vào cột discriminator trong cùng bảng; database có thể dùng index hoặc statistics của cột đó khi phù hợp.

### 4.5. Chi phí và ràng buộc

SINGLE_TABLE đơn giản cho các truy vấn đa hình vì **một bảng chứa tất cả subtype**. Đổi lại:

- Bảng có thể rất rộng khi hierarchy có nhiều subtype với các field đặc thù.
- Các cột chỉ dùng cho một subtype thường phải nullable ở mức bảng để row các subtype khác được lưu.
- `@Column(nullable = false)` cho field chỉ thuộc `CardPayment` không thể tự động biến cột đó thành `NOT NULL` toàn bảng mà vẫn cho phép `BANK`/`CASH` lưu dữ liệu. Nếu cần bắt buộc theo subtype, cân nhắc constraint dạng `CHECK` dựa vào discriminator hoặc validation thích hợp.
- Index trên các cột subtype chỉ hữu ích cho một số loại row; cần đo kích thước, selectivity và execution plan.

Ví dụ một ràng buộc kiểm tra theo discriminator trong PostgreSQL:

~~~sql
ALTER TABLE payment ADD CONSTRAINT ck_payment_card
CHECK (
    payment_kind <> 'CARD'
    OR card_last_four IS NOT NULL
);
~~~

Constraint này bổ sung invariant “nếu là CARD thì phải có card_last_four”, không làm cột thành `NOT NULL` cho mọi row. Mapping JPA và DDL cần nhất quán.

## 5. JOINED: một bảng gốc và bảng riêng cho mỗi subtype

### 5.1. Mapping

Với cùng hierarchy `Payment`, thay annotation ở root:

~~~java
@Entity
@Table(name = "payment")
@Inheritance(strategy = InheritanceType.JOINED)
@SequenceGenerator(
    name = "payment_id_gen",
    sequenceName = "payment_seq",
    allocationSize = 1
)
public abstract class Payment {
    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "payment_id_gen"
    )
    private Long id;

    @Column(name = "amount", nullable = false, precision = 15, scale = 2)
    private BigDecimal amount;
    // constructor/getter như ví dụ chung
}
~~~

Trên các subtype, khai báo tên bảng và khóa nối:

~~~java
@Entity
@Table(name = "card_payment")
@PrimaryKeyJoinColumn(name = "payment_id")
public class CardPayment extends Payment {
    @Column(name = "card_last_four", nullable = false, length = 4)
    private String cardLastFour;
    // constructor/getter ...
}

@Entity
@Table(name = "bank_payment")
@PrimaryKeyJoinColumn(name = "payment_id")
public class BankTransferPayment extends Payment {
    @Column(name = "bank_reference", nullable = false, length = 80)
    private String bankReference;
    // constructor/getter ...
}

@Entity
@Table(name = "cash_payment")
@PrimaryKeyJoinColumn(name = "payment_id")
public class CashPayment extends Payment {
    @Column(name = "receipt_code", nullable = false, length = 80)
    private String receiptCode;
    // constructor/getter ...
}
~~~

Code trên là **mapping minh họa riêng cho phương án JOINED**. Khi triển khai, các subtype vẫn cần constructors/các field và logic như ở ví dụ `SINGLE_TABLE`; không giữ annotation `@DiscriminatorValue` bắt buộc từ phương án trước chỉ vì copy code. Hibernate có thể sử dụng discriminator tường minh trong JOINED nếu cấu hình, nhưng JOINED không cần phải có discriminator vật lý để hiểu subtype.

### 5.2. Schema

~~~sql
CREATE SEQUENCE payment_seq START WITH 1 INCREMENT BY 1;

CREATE TABLE payment (
    id BIGINT PRIMARY KEY,
    amount NUMERIC(15,2) NOT NULL
);

CREATE TABLE card_payment (
    payment_id BIGINT PRIMARY KEY,
    card_last_four VARCHAR(4) NOT NULL,
    CONSTRAINT fk_card_payment
        FOREIGN KEY (payment_id) REFERENCES payment(id)
);

CREATE TABLE bank_payment (
    payment_id BIGINT PRIMARY KEY,
    bank_reference VARCHAR(80) NOT NULL,
    CONSTRAINT fk_bank_payment
        FOREIGN KEY (payment_id) REFERENCES payment(id)
);

CREATE TABLE cash_payment (
    payment_id BIGINT PRIMARY KEY,
    receipt_code VARCHAR(80) NOT NULL,
    CONSTRAINT fk_cash_payment
        FOREIGN KEY (payment_id) REFERENCES payment(id)
);
~~~

~~~text
payment                  card_payment        bank_payment        cash_payment
+-----+--------+         +------------+     +------------+      +------------+
| id  | amount |         | payment_id |     | payment_id |      | payment_id |
+-----+--------+         +------------+     +------------+      +------------+
| 101 | 120.00 |<--------| 101        |     |            |      |            |
| 102 | 300.00 |<------------------------------- 102       |      |            |
| 103 | 45.00  |<--------------------------------------------------- 103      |
+-----+--------+
~~~

Mỗi concrete entity gồm **một row ở bảng gốc** và **một row ở bảng subtype tương ứng**, sử dụng cùng một ID. Cột `card_payment.payment_id` là **primary key và foreign key** tới `payment.id`; các field chung như `amount` không lặp lại trong bảng subtype.

### 5.3. Truy vấn đa hình từ root có thể cần nhiều LEFT JOIN

JPQL vẫn giữ nguyên:

~~~java
List<Payment> payments = entityManager.createQuery(
    "select p from Payment p",
    Payment.class
).getResultList();
~~~

Một SQL minh họa:

~~~sql
SELECT
    p.id,
    p.amount,
    c.card_last_four,
    b.bank_reference,
    x.receipt_code,
    CASE
        WHEN c.payment_id IS NOT NULL THEN 'CARD'
        WHEN b.payment_id IS NOT NULL THEN 'BANK'
        WHEN x.payment_id IS NOT NULL THEN 'CASH'
    END AS concrete_type
FROM payment p
LEFT JOIN card_payment c ON c.payment_id = p.id
LEFT JOIN bank_payment b ON b.payment_id = p.id
LEFT JOIN cash_payment x ON x.payment_id = p.id;
~~~

Hibernate cần biết subtype của mỗi `Payment` để materialize đối tượng đúng. Khi không có discriminator lưu ở bảng cha, một cách xác định subtype là nhìn row ở bảng con nào tồn tại, có thể biểu diễn qua `CASE` và các `LEFT JOIN`. Với Hibernate mapping có discriminator vật lý, cách xác định type có thể khác. Một số truy vấn/projection còn được tối ưu để chỉ join các bảng thật sự cần.

**Vì sao là LEFT JOIN?** Khi đọc mọi payment, một row của `CardPayment` không có row trong `bank_payment` hay `cash_payment`. Dùng `INNER JOIN` với mọi bảng con sẽ loại mất row thuộc các subtype khác.

Với hierarchy có nhiều subtype, phép đọc full entity từ root có thể trở thành một SQL nhiều JOIN. Nhưng không nên kết luận Hibernate luôn join mọi subclass table trong mọi query: projection, filters, discriminator và cách SQL AST xây dựng có thể loại bỏ hoặc thay đổi các join không cần thiết.

### 5.4. Truy vấn một subtype dùng JOIN bảng gốc với bảng con

~~~java
List<CardPayment> cards = entityManager.createQuery(
    "select c from CardPayment c",
    CardPayment.class
).getResultList();
~~~

SQL khái quát:

~~~sql
SELECT p.id, p.amount, c.card_last_four
FROM card_payment c
JOIN payment p ON p.id = c.payment_id;
~~~

Một `CardPayment` cần cả `amount` (bảng gốc) và `card_last_four` (bảng con), vì thế join giữa hai bảng là điều tự nhiên. Không cần join `bank_payment` hoặc `cash_payment` khi subtype cụ thể đã được cố định và query không yêu cầu điều gì liên quan những bảng đó.

### 5.5. Chỉ chọn field chung có thể không cần join con

~~~java
List<BigDecimal> amounts = entityManager.createQuery(
    "select p.amount from Payment p",
    BigDecimal.class
).getResultList();
~~~

SQL tối giản có thể là:

~~~sql
SELECT p.amount FROM payment p;
~~~

Bởi projection chỉ lấy một scalar `amount` trong bảng gốc, database không nhất thiết phải truy cập bảng subtype. Điều này khác với `select p`: trả về **managed concrete entity** đòi hỏi Hibernate biết loại và state phù hợp.

### 5.6. Chi phí và quy tắc dữ liệu

JOINED giữ schema chuẩn hóa tốt hơn, cho phép `NOT NULL` ở các cột đặc thù của từng bảng con. Đổi lại:

- Truy vấn root trả full entity có thể có nhiều `LEFT JOIN`.
- Insert một subtype thường yêu cầu insert row ở bảng gốc rồi ở bảng con; delete phải giữ đúng quan hệ FK.
- Bộ lọc hoặc sorting theo field subtype có thể cần join bảng tương ứng.
- Khóa chính của các bảng con là PK/FK nên nên có ràng buộc/index phù hợp.
- Khóa FK từ subtype đến root **không tự bảo đảm** mọi row root có đúng một row subtype; nếu DB có dữ liệu sửa thủ công, schema phải được kiểm soát để không có parent row mồ côi subtype hoặc ID xuất hiện ở nhiều bảng subtype.

Nếu root là abstract, database vẫn có thể chứa row `payment` chưa có row subtype nếu script chèn sai và không có kiểm soát bổ sung. ORM không thay thế hoàn toàn chiến lược toàn vẹn dữ liệu.

## 6. TABLE_PER_CLASS: mỗi lớp concrete tự chứa tất cả cột

### 6.1. Mapping

Trong phương án độc lập này, đổi root thành:

~~~java
@Entity
@Inheritance(strategy = InheritanceType.TABLE_PER_CLASS)
@SequenceGenerator(
    name = "payment_id_gen",
    sequenceName = "payment_seq",
    allocationSize = 1
)
public abstract class Payment {
    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "payment_id_gen"
    )
    private Long id;

    @Column(name = "amount", nullable = false, precision = 15, scale = 2)
    private BigDecimal amount;
    // constructors/getters ...
}
~~~

Subtype:

~~~java
@Entity
@Table(name = "card_payment")
public class CardPayment extends Payment {
    @Column(name = "card_last_four", nullable = false, length = 4)
    private String cardLastFour;
}

@Entity
@Table(name = "bank_payment")
public class BankTransferPayment extends Payment {
    @Column(name = "bank_reference", nullable = false, length = 80)
    private String bankReference;
}

@Entity
@Table(name = "cash_payment")
public class CashPayment extends Payment {
    @Column(name = "receipt_code", nullable = false, length = 80)
    private String receiptCode;
}
~~~

Những snippet ngắn chỉ tập trung vào annotation; thực thể đầy đủ vẫn cần constructor không tham số, field, getter và domain methods như phần mẫu. Với `TABLE_PER_CLASS`, không dựa vào discriminator column chung ở bảng gốc vì **không có bảng gốc vật lý** nếu root abstract.

### 6.2. Schema

~~~sql
CREATE SEQUENCE payment_seq START WITH 1 INCREMENT BY 1;

CREATE TABLE card_payment (
    id BIGINT PRIMARY KEY,
    amount NUMERIC(15,2) NOT NULL,
    card_last_four VARCHAR(4) NOT NULL
);

CREATE TABLE bank_payment (
    id BIGINT PRIMARY KEY,
    amount NUMERIC(15,2) NOT NULL,
    bank_reference VARCHAR(80) NOT NULL
);

CREATE TABLE cash_payment (
    id BIGINT PRIMARY KEY,
    amount NUMERIC(15,2) NOT NULL,
    receipt_code VARCHAR(80) NOT NULL
);
~~~

Các cột kế thừa như `id` và `amount` **được lặp về mặt schema** ở từng bảng concrete. Không có bảng `payment` để join với bảng con khi chỉ đọc một subtype.

### 6.3. Truy vấn subtype cụ thể chỉ cần bảng của subtype

~~~java
List<CardPayment> cards = entityManager.createQuery(
    "select c from CardPayment c",
    CardPayment.class
).getResultList();
~~~

SQL minh họa:

~~~sql
SELECT c.id, c.amount, c.card_last_four
FROM card_payment c;
~~~

Không có `JOIN payment` vì dữ liệu chung đã nằm ngay trong bảng `card_payment`. Nếu ứng dụng chủ yếu truy vấn từng subtype riêng biệt, dạng query này có thể đơn giản.

### 6.4. Truy vấn root phải kết hợp các bảng concrete

~~~java
List<Payment> payments = entityManager.createQuery(
    "select p from Payment p order by p.id",
    Payment.class
).getResultList();
~~~

SQL khái niệm có thể dùng `UNION ALL`:

~~~sql
SELECT u.id,
       u.amount,
       u.card_last_four,
       u.bank_reference,
       u.receipt_code,
       u.entity_type
FROM (
    SELECT c.id,
           c.amount,
           c.card_last_four,
           CAST(NULL AS VARCHAR(80)) AS bank_reference,
           CAST(NULL AS VARCHAR(80)) AS receipt_code,
           'CARD' AS entity_type
    FROM card_payment c

    UNION ALL

    SELECT b.id,
           b.amount,
           CAST(NULL AS VARCHAR(4)) AS card_last_four,
           b.bank_reference,
           CAST(NULL AS VARCHAR(80)) AS receipt_code,
           'BANK' AS entity_type
    FROM bank_payment b

    UNION ALL

    SELECT x.id,
           x.amount,
           CAST(NULL AS VARCHAR(4)) AS card_last_four,
           CAST(NULL AS VARCHAR(80)) AS bank_reference,
           x.receipt_code,
           'CASH' AS entity_type
    FROM cash_payment x
) u
ORDER BY u.id;
~~~

Mỗi nhánh SELECT phải tạo ra **số cột và kiểu dữ liệu tương thích**. Giá trị `NULL` cho field của subtype khác có thể được ép kiểu, còn cột `entity_type` (tên tùy cách Hibernate tạo SQL) giúp ORM nhận ra row bắt nguồn từ nhánh bảng nào. Truy vấn chỉ chọn field chung có thể cần `UNION ALL` ít cột hơn; không phải mọi root query đều ghép đủ mọi field.

**`UNION ALL` khác `UNION`:** `UNION ALL` giữ nguyên các row từ mọi nhánh, không thực hiện loại bản ghi trùng trên toàn bộ output như `UNION`. Với inheritance này, Hibernate phải phân biệt các concrete entities bằng identity/type, do đó việc giữ đủ row của từng bảng là phù hợp. Database có thể có kế hoạch scan, append và sort tùy truy vấn.

### 6.5. Lọc subtype trong truy vấn root

~~~java
List<Payment> cards = entityManager.createQuery(
    "select p from Payment p where type(p) = CardPayment",
    Payment.class
).getResultList();
~~~

Hibernate có thể đơn giản hóa kế hoạch để chỉ truy vấn bảng `card_payment` hoặc dùng predicate loại những nhánh `UNION` khác. Không nên giả định truy vấn root có `TYPE` luôn phải đọc tất cả bảng: trình chuyển HQL/SQL và optimizer DB có thể hạn chế các nhánh không liên quan.

### 6.6. Một namespace ID cho toàn hierarchy

Vì không có bảng parent thống nhất để bảo đảm uniqueness bằng một PK chung, các subtype cần quy tắc cấp ID nhất quán nếu application nhận diện đối tượng bằng `Payment` + ID. Hibernate thường yêu cầu generator có thể cấp khóa **duy nhất trên toàn hierarchy**; ví dụ dùng một sequence `payment_seq` chung.

Không nên cho mỗi bảng concrete sử dụng `IDENTITY` riêng với dãy bắt đầu từ 1 rồi giả định `Payment(1)` luôn chỉ có một entity: `card_payment.id = 1` và `bank_payment.id = 1` có thể cùng tồn tại, gây xung đột semantics nhận diện polymorphic entity. Trong Hibernate, identity generation không phù hợp/không được hỗ trợ cho mô hình union-subclass thông thường theo cách đó; ưu tiên sequence/table generator chung.

### 6.7. Khó khăn với quan hệ FK đến kiểu cha

Giả sử bảng `refund` có cột `payment_id` và muốn `@ManyToOne Payment payment`. Với `SINGLE_TABLE` hoặc `JOINED`, DB có bảng `payment(id)` để foreign key tham chiếu. Nhưng `TABLE_PER_CLASS` với abstract root **không có bảng `payment`**:

~~~text
refund.payment_id --> ?
                      card_payment.id
                      bank_payment.id
                      cash_payment.id
~~~

Một FK quan hệ thông thường không thể tự động tham chiếu “một trong ba bảng” theo một khóa duy nhất. Hibernate có thể có cơ chế ánh xạ/truy vấn polymorphic association phù hợp cho một số tình huống, nhưng **database-level FK integrity** phức tạp và thường phải đổi thiết kế (ví dụ root table riêng, tách association, hoặc loại schema khác).

Đây là yếu tố kiến trúc quan trọng khi chọn `TABLE_PER_CLASS`, ngoài chi phí `UNION ALL` của query.

## 7. MAPPED_SUPERCLASS: dùng chung field nhưng không truy vấn root

Một lớp có `@MappedSuperclass` chỉ cung cấp các field/mapping cho entity con:

~~~java
import jakarta.persistence.*;
import java.math.BigDecimal;

@MappedSuperclass
public abstract class BasePaymentFields {
    @Id
    private Long id;

    @Column(nullable = false, precision = 15, scale = 2)
    private BigDecimal amount;
}

@Entity
@Table(name = "card_payment")
public class CardPayment extends BasePaymentFields {
    private String cardLastFour;
}

@Entity
@Table(name = "bank_payment")
public class BankTransferPayment extends BasePaymentFields {
    private String bankReference;
}
~~~

Đối với cách này:

~~~java
entityManager.createQuery(
    "select p from BasePaymentFields p",
    BasePaymentFields.class
);
~~~

không phải truy vấn entity root JPA hợp lệ, vì `BasePaymentFields` **không phải entity**. Một số mở rộng HQL của Hibernate hỗ trợ implicit polymorphism qua interface/non-entity types theo các quy tắc riêng, nhưng không nên nhầm cơ chế mở rộng đó với `@Inheritance` trên một entity root chuẩn JPA, cũng không dựa vào nó để thiết kế repository portable.

Nếu muốn truy vấn:

~~~java
List<CardPayment> cards = entityManager.createQuery(
    "select c from CardPayment c",
    CardPayment.class
).getResultList();
~~~

thì `CardPayment` có thể được map vào một bảng riêng với các cột được kế thừa. Nhưng một `select p from BasePaymentFields p` không tự thành `UNION ALL` JPA chỉ vì nhiều entity kế thừa chung superclass.

**Quy tắc nhớ:** `@Entity + @Inheritance` tạo một hierarchy entity có khả năng truy vấn đa hình; `@MappedSuperclass` tái sử dụng mapping field nhưng không tạo entity type/query root.

## 8. Bảng tổng hợp: root query truy cập bảng gì?

Với câu:

~~~jpql
select p from Payment p
~~~

và hierarchy ba subtype, cấu trúc SQL chính thường là:

| Chiến lược | Bảng dữ liệu | Cách trả mọi subtype | Cách xác định subtype |
|---|---|---|---|
| `SINGLE_TABLE` | Một bảng `payment` | Một `SELECT FROM payment`; không cần join inheritance | Discriminator cột `payment_kind` hoặc equivalent type metadata. |
| `JOINED` | `payment` và các bảng `card_payment`, `bank_payment`, `cash_payment` | `SELECT` bảng root kèm các `LEFT JOIN` cần để nạp subtype/nhận dạng, hoặc kế hoạch tương đương | Discriminator nếu có, hoặc sự hiện diện row ở các bảng subtype. |
| `TABLE_PER_CLASS` | Các bảng concrete, không có root table khi root abstract | `UNION ALL` các nhánh concrete hoặc cấu trúc tương đương | Nhánh bảng được chọn/synthetic discriminator. |
| `@MappedSuperclass` | Các bảng entity con độc lập | Không có root query JPA tương ứng | Không có entity root theo superclass. |

So sánh khi query **chỉ một subtype**:

| Chiến lược | `select c from CardPayment c` có thể dùng |
|---|---|
| `SINGLE_TABLE` | Bảng `payment` + điều kiện `payment_kind = 'CARD'`. |
| `JOINED` | `card_payment JOIN payment` bằng PK/FK; không cần các sibling tables. |
| `TABLE_PER_CLASS` | Chỉ bảng `card_payment`; không cần union nếu không có subtype con. |
| `@MappedSuperclass` | Bảng của `CardPayment`, vì truy vấn subtype là một entity hợp lệ. |

Những con số về số bảng được dùng là **mô hình thông thường cho load full entity**, không phải cam kết rằng mọi query Hibernate phát sinh số JOIN bằng số subtype. Query projection, `TYPE` filters, fetch plan, cache và SQL optimizer có thể làm kế hoạch thực tế khác.

## 9. `TYPE()`: truy vấn theo entity subtype

JPQL có biểu thức `TYPE(entityAlias)` để lọc/nhóm theo entity type.

### Lấy đúng một subtype

~~~java
List<Payment> cards = entityManager.createQuery(
    "select p from Payment p where type(p) = CardPayment",
    Payment.class
).getResultList();
~~~

`CardPayment` trong HQL/JPQL là **tên entity type**, không phải một chuỗi `'CARD'`. Việc discriminator vật lý có giá trị `CARD` là chi tiết mapping; Hibernate chuyển biểu thức type thành điều kiện SQL phù hợp với từng inheritance strategy.

### Lấy một tập subtype

~~~java
List<Payment> nonCash = entityManager.createQuery(
    """
    select p
    from Payment p
    where type(p) in (CardPayment, BankTransferPayment)
    """,
    Payment.class
).getResultList();
~~~

Với `SINGLE_TABLE`, SQL có thể:

~~~sql
SELECT ...
FROM payment p
WHERE p.payment_kind IN ('CARD', 'BANK');
~~~

Với `JOINED`, điều kiện type có thể dựa trên discriminator/các bảng con. Với `TABLE_PER_CLASS`, Hibernate có thể bỏ qua nhánh `cash_payment` khỏi `UNION`. Kết quả Java thể hiện cùng điều kiện, nhưng đường đi SQL khác nhau.

### Thống kê theo subtype

~~~java
List<Object[]> counts = entityManager.createQuery(
    """
    select type(p), count(p)
    from Payment p
    group by type(p)
    """,
    Object[].class
).getResultList();
~~~

Kết quả logical có thể là ba cặp (entity class, count). SQL `GROUP BY` phía database có thể nhóm theo discriminator, case expression hoặc synthetic type column của union. Dạng query này giúp báo cáo số lượng theo loại, nhưng cần hiểu optimizer có thể scan phần lớn dữ liệu hierarchy.

### Nếu subtype có lớp con sâu hơn?

Giả sử `PremiumCardPayment extends CardPayment` là một `@Entity`. Truy vấn `from CardPayment` bao gồm các descendant phù hợp, còn `type(p) = CardPayment` yêu cầu **exact entity type** tương ứng theo semantics `TYPE`. Nếu muốn cả `CardPayment` và các con của nó, truy vấn từ subtype hoặc điều kiện type bao phủ các concrete types mong muốn. Không dùng `TYPE` exact khi nghiệp vụ cần mọi lớp kế thừa trong nhánh.

## 10. `TREAT()`: truy cập thuộc tính riêng của lớp con

Khi biến HQL `p` có kiểu khai báo `Payment`, các field như `cardLastFour` **không nằm trong lớp cha**. Muốn truy cập field subtype một cách chuẩn tường minh, có thể dùng `TREAT`:

~~~java
List<Payment> matched = entityManager.createQuery(
    """
    select p
    from Payment p
    where type(p) = CardPayment
      and treat(p as CardPayment).cardLastFour = :lastFour
    """,
    Payment.class
).setParameter("lastFour", "4242")
 .getResultList();
~~~

`TREAT(p AS CardPayment)` là phép **downcast có điều kiện theo entity type** trong query. Nó không biến các row khác subtype thành `CardPayment` trong database; Hibernate dùng nó để biết SQL cần tham chiếu thuộc tính `cardLastFour` ở đâu.

Tùy strategy, biểu thức liên quan đến:

- `SINGLE_TABLE`: cột `payment.card_last_four`, thường kết hợp điều kiện discriminator.
- `JOINED`: cột `card_payment.card_last_four`, yêu cầu truy cập/join bảng subtype khi query root.
- `TABLE_PER_CLASS`: cột ở nhánh `card_payment` trong union, hoặc một query được rút gọn về nhánh đó.

### Vì sao thêm điều kiện `TYPE` rõ ràng?

Semantics `TREAT` và null handling, đặc biệt khi được dùng trong các loại join khác nhau, có những quy tắc JPA/provider cụ thể. Với bài toán “chỉ lấy card payment có 4 số cuối ...”, điều kiện `TYPE(p) = CardPayment` thể hiện rõ ràng ý định lọc. Khi muốn bao gồm các subtype con, cần điều chỉnh điều kiện type cho đúng yêu cầu.

### HQL có thể có cú pháp riêng

Hibernate HQL hỗ trợ nhiều biểu thức polymorphism và downcast mở rộng. Tuy nhiên, khi muốn code portable giữa providers, ưu tiên biểu thức JPQL chuẩn `TYPE`/`TREAT` được phiên bản Jakarta Persistence đang dùng hỗ trợ. Với truy vấn phức tạp, hãy xem SQL thực tế thay vì giả định Hibernate luôn sử dụng cùng một JOIN.

## 11. Truy vấn gốc, subtype và projection: ba chi phí khác nhau

Xét ba câu HQL:

~~~jpql
-- A: trả full entity ở root hierarchy
select p from Payment p

-- B: trả full entity thuộc một subtype
select c from CardPayment c

-- C: chỉ lấy scalar được định nghĩa ở root
select p.id, p.amount from Payment p
~~~

Với `JOINED`:

- A có thể cần JOIN nhiều subtype tables để biết concrete type và nạp đầy đủ entity state.
- B thường chỉ cần JOIN bảng `payment` với `card_payment`.
- C có thể chỉ đọc bảng `payment` và không động tới bảng subtype.

Với `TABLE_PER_CLASS`:

- A thường cần `UNION ALL` các bảng concrete, có thể kèm cột loại subtype.
- B thường đọc một bảng `card_payment`.
- C vẫn có thể cần `UNION ALL` vì các cột `id` và `amount` tồn tại rải ở **nhiều bảng concrete**.

Với `SINGLE_TABLE`:

- Cả ba dạng thường chỉ truy cập `payment`; sự khác biệt chính nằm ở cột SELECT, discriminator filter và index/plan.

**Bài học tối ưu query:** Nếu endpoint chỉ cần danh sách ID, tổng số tiền hoặc một DTO nhỏ, **projection** có thể giảm đáng kể lượng dữ liệu Hibernate cần hydrate, đặc biệt trong `JOINED` và những entity có nhiều association. Đừng tự động dùng `select p` rồi map object sang DTO nếu có thể select trực tiếp các giá trị cần thiết.

### DTO projection minh họa

~~~java
public record PaymentSummary(Long id, BigDecimal amount) {}
~~~

~~~java
List<PaymentSummary> summaries = entityManager.createQuery(
    """
    select new com.example.dto.PaymentSummary(p.id, p.amount)
    from Payment p
    order by p.id
    """,
    PaymentSummary.class
).getResultList();
~~~

Giả định `PaymentSummary` được đặt đúng package `com.example.dto` và constructor của record khớp projection. Query trả DTO, không tạo managed entity `Payment` cho mỗi row. Với strategy khác nhau, Hibernate vẫn tạo SQL tương ứng để lấy scalar từ một hay nhiều bảng.

## 12. Truy vấn association đến hierarchy đa hình

Truy vấn đa hình còn xuất hiện **gián tiếp** khi một entity khác có association tới `Payment`. Giả sử:

~~~java
@Entity
public class Refund {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "payment_id")
    private Payment payment;
}
~~~

Khi query:

~~~java
List<Refund> refunds = entityManager.createQuery(
    """
    select r
    from Refund r
    join r.payment p
    where p.amount >= :min
    """,
    Refund.class
).setParameter("min", new BigDecimal("100.00"))
 .getResultList();
~~~

ORM phải hiểu `r.payment` có thể trỏ tới nhiều subtype:

- **SINGLE_TABLE:** có thể join `refund.payment_id` với `payment.id`; nếu phải hydrate concrete payment thì dùng discriminator trong bảng `payment`.
- **JOINED:** `refund` có thể FK tới root `payment(id)`. Nếu query chỉ lọc `p.amount`, có thể join root table; nếu fetch concrete payment, có thể cần thêm subtype joins.
- **TABLE_PER_CLASS:** root abstract không có bảng PK chung cho FK tham chiếu. ORM có thể phải join với polymorphic union hoặc dùng cơ chế riêng, trong khi enforce FK trực tiếp ở database phức tạp. Đây là lý do TABLE_PER_CLASS có hạn chế kiến trúc khi các entity khác cần association tới root.

Lưu ý: `JOIN` trong JPQL dùng để **đi qua association** khác với `JOIN` giữa bảng root và bảng subtype do chiến lược `JOINED` tạo ra. Cùng một SQL cuối cùng có thể chứa cả hai loại join, nhưng chúng xuất phát từ hai lý do khác nhau.

### `JOIN FETCH` không đồng nghĩa JOIN kế thừa

~~~jpql
select r from Refund r join fetch r.payment
~~~

`join fetch r.payment` yêu cầu Hibernate tải association `payment` cùng kết quả. Với `JOINED`, Hibernate vẫn cần xử lý subtype của payment để hydrate đúng concrete instance. Việc thêm fetch join có thể làm SQL dài hơn: join association `refund -> payment` rồi join bảng subtype nếu cần. Đây là hai tầng truy cập dữ liệu khác nhau.

## 13. Tác động của kế thừa lên phân trang và sắp xếp

Ví dụ:

~~~java
List<Payment> page = entityManager.createQuery(
    "select p from Payment p order by p.id",
    Payment.class
).setFirstResult(100)
 .setMaxResults(20)
 .getResultList();
~~~

Mức độ phức tạp phụ thuộc strategy:

| Strategy | SQL phân trang có thể phải xử lý |
|---|---|
| `SINGLE_TABLE` | Một bảng, `ORDER BY`/`OFFSET`/`FETCH` hoặc giới hạn tương đương theo dialect. |
| `JOINED` | Root table cùng những subtype joins cần để materialize; join 1:1 theo PK thông thường không nhân số row của root, nhưng thêm collection fetch joins có thể làm pagination phức tạp. |
| `TABLE_PER_CLASS` | `UNION ALL` các bảng concrete, sau đó cần thứ tự/giới hạn toàn cục để lấy đúng một page đa hình. |

Với `TABLE_PER_CLASS`, nếu ba bảng đều có dữ liệu, database thường không thể đơn giản lấy “20 row đầu từ mỗi bảng rồi ghép lại” mà luôn đảm bảo đúng 20 row cuối cùng theo `ORDER BY p.id`. Nó có thể phải kết hợp/sort hoặc dùng kế hoạch tối ưu khác.

### Dùng thứ tự ổn định

Nên có `ORDER BY` khi phân trang; nếu sort theo một thuộc tính không unique như `amount`, bổ sung `id` để thứ tự ổn định:

~~~jpql
select p from Payment p order by p.amount desc, p.id asc
~~~

Khi dữ liệu biến động trong lúc người dùng phân trang, offset pagination vẫn có thể bỏ sót/trùng row; nếu cần tính ổn định cao, cân nhắc keyset pagination theo một thứ tự thích hợp. Với polymorphic union và sort trên field subtype, cần đo plan cụ thể.

### COUNT cũng phải đi qua các bảng phù hợp

~~~java
Long total = entityManager.createQuery(
    "select count(p) from Payment p",
    Long.class
).getSingleResult();
~~~

- `SINGLE_TABLE`: có thể là `count(*)` trên `payment`.
- `JOINED`: root table thường đủ để đếm nếu mọi row đại diện entity hợp lệ.
- `TABLE_PER_CLASS`: phải đếm trên các bảng concrete, qua `UNION` hoặc kế hoạch tương đương như cộng các counts; Hibernate chọn SQL tương ứng.

`count(p)` không mặc nhiên rẻ trên mọi hierarchy chỉ vì projection là một số.

## 14. Kế thừa nhiều cấp làm SQL thay đổi ra sao?

Giả sử `CardPayment` có subtype `CorporateCardPayment`:

~~~mermaid
classDiagram
    Payment <|-- CardPayment
    Payment <|-- BankTransferPayment
    Payment <|-- CashPayment
    CardPayment <|-- CorporateCardPayment
~~~

- **SINGLE_TABLE:** vẫn một bảng `payment`; có thêm discriminator value cho `CorporateCardPayment` và thêm các cột đặc thù nếu cần. Query `from CardPayment` bao gồm concrete CardPayment và CorporateCardPayment.
- **JOINED:** có thể thêm bảng `corporate_card_payment` với PK/FK nối tới `card_payment` (và gián tiếp tới root); hydrate entity sâu hơn cần join qua các cấp kế thừa phù hợp.
- **TABLE_PER_CLASS:** mỗi concrete subtype có bảng chứa các cột kế thừa của toàn chuỗi; query root thêm nhánh tương ứng trong polymorphic union, còn query `from CardPayment` có thể kết hợp các bảng của concrete descendants thuộc nhánh card.

Do đó chi phí không chỉ phụ thuộc **số lớp**, mà phụ thuộc số **concrete tables/columns** và **độ sâu hierarchy**. Một hierarchy có 2 subtype nhẹ khác đáng kể một hierarchy có 30 subtype, nhiều lớp trung gian và các field độc lập.

### Root trừu tượng vẫn có query đa hình

~~~java
@Entity
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class Payment { ... }
~~~

Mặc dù `new Payment()` không hợp lệ, `select p from Payment p` vẫn hợp lệ vì `Payment` là **mapped entity root**. Hibernate truy vấn các concrete instances nằm dưới root.

Điều này khác `@MappedSuperclass`, vốn không phải entity root.

## 15. Phép JOIN của kế thừa khác phép JOIN quan hệ một–nhiều

Trong `JOINED`, mỗi instance của `CardPayment` thường có đúng:

~~~text
payment.id = 101
card_payment.payment_id = 101
~~~

Đó là **join 1:1 theo PK/FK** giữa các bảng của cùng một entity. Nếu dữ liệu đúng ràng buộc, một root row không bị nhân thành nhiều result rows vì join bảng subtype.

Trong `@OneToMany`, một root entity có thể join với **nhiều** child rows:

~~~text
order.id = 5
order_line(order_id=5) -> 3 rows
~~~

JOIN vào collection như vậy làm các cột order lặp lại ở SQL result set, và có thể gây vấn đề pagination nếu fetch join. Cần phân biệt:

1. **Inheritance join:** ghép nhiều bảng để dựng **một** concrete entity.
2. **Association join:** nối **những entity khác nhau** theo FK, có thể 1:1, N:1 hoặc 1:N.

Một query `select p from Payment p join fetch p.customer` trong mapping `JOINED` có thể chứa join đến `customer` vì association và join đến `card_payment`, `bank_payment` vì inheritance. Hai loại join tồn tại cùng lúc nhưng xử lý hai chiều khác nhau của dữ liệu.

### Hibernate có thể tải subtype qua query khác không?

Một số mapping/fetch plan đặc biệt có thể thay đổi cách lấy row từ bảng subtype, hoặc dùng lazy basic attributes với bytecode enhancement khi hỗ trợ. Không nên suy luận mọi query Hibernate luôn phát sinh cùng số join; **đọc SQL generated** là cách xác nhận chính xác.

## 16. Định danh và first-level cache trong query đa hình

Một persistence context có cơ chế nhận diện managed entity theo entity identity. Khi query `Payment` trả một row thực chất là `CardPayment`, Hibernate phải trả đối tượng thuộc concrete subtype đúng.

Ví dụ:

~~~java
Payment payment = entityManager.find(Payment.class, 101L);
CardPayment card = entityManager.find(CardPayment.class, 101L);
~~~

Khi ID `101` thực sự là CardPayment và cả hai thao tác được hỗ trợ trong cùng persistence context, Hibernate sẽ quản lý identity nhất quán, tránh tạo hai bản ghi managed khác nhau đại diện cùng row. Tuy vậy, do proxy/lazy loading và cách provider dựng reference, không nên viết business logic so sánh Java `getClass()` với một concrete class hoặc kết luận chỉ từ việc hai tham chiếu là cùng object trong mọi ngữ cảnh proxy.

### Cẩn thận với `instanceof` trên lazy proxy

Giả sử một association khai báo kiểu `Payment`, Hibernate có thể trả proxy chưa được initialize với type hiển thị theo superclass/metadata. Các thao tác Java `instanceof CardPayment` có thể không cho kết quả mong muốn với một số proxy/loading patterns. Nếu cần lọc **trong database**, dùng:

~~~jpql
where type(p) = CardPayment
~~~

Nếu cần áp dụng hành vi subtype trên object đã tải, có thể thiết kế polymorphic methods ở `Payment` để tránh client phụ thuộc downcast; khi thật sự cần kiểm tra concrete class, sử dụng API phù hợp của provider và hiểu ảnh hưởng của proxy/initialization.

## 17. SQL mutation khác SQL truy vấn nhưng cùng phụ thuộc strategy

Mục tiêu chính của bài là **truy vấn đọc**, song cách dữ liệu được ghi quyết định bảng nào tồn tại để query:

| Strategy | Persist một `CardPayment` | Xóa một `CardPayment` |
|---|---|---|
| `SINGLE_TABLE` | Thường một `INSERT payment` với discriminator CARD và cột thẻ. | Thường một `DELETE payment`. |
| `JOINED` | Một `INSERT payment` rồi một `INSERT card_payment` trong transaction. | Xóa row subtype/root đúng thứ tự FK hoặc cơ chế phù hợp. |
| `TABLE_PER_CLASS` | Thường một `INSERT card_payment` với cả `id`, `amount` và `card_last_four`. | Thường một `DELETE card_payment`. |

Giả sử `Payment` có `@Version`, Hibernate cũng phải duy trì optimistic locking theo mapping của hierarchy; trong JOINED version có thể nằm ở root table và những update subtype có thể kéo theo thao tác check/update version. Không kết luận một field subtype bị sửa thì Hibernate chắc chắn chỉ tác động đúng một bảng.

### Flush ảnh hưởng query thấy dữ liệu gì

Trong flush mode mặc định `AUTO`, Hibernate có thể flush pending inserts/updates trước một HQL/JPQL query nếu cần đảm bảo tính nhất quán. Nếu đã `persist(new CardPayment(...))` nhưng chưa gọi `flush()`, một query đa hình `from Payment` có thể kích hoạt flush trước khi đọc.

~~~java
tx.begin();
entityManager.persist(new CardPayment(new BigDecimal("99.00"), "1111"));

List<Payment> payments = entityManager.createQuery(
    "select p from Payment p",
    Payment.class
).getResultList();

tx.commit();
~~~

Khả năng query làm SQL insert chạy **không có nghĩa transaction đã commit**. Nếu rollback, dữ liệu insert vẫn có thể bị hủy. Ngoài ra, query `AUTO` có thể không cần flush trong một số trường hợp không liên quan bảng pending; nên phân biệt query execution và transaction synchronization.

## 18. Hiệu năng: chiến lược nào phù hợp workload nào?

Không thể kết luận duy nhất từ số JOIN/UNION rằng một strategy luôn nhanh hơn. SQL planner, indexes, số row mỗi subtype, tỷ lệ truy vấn root so với subtype, kích thước row và môi trường DB quyết định chi phí.

| Workload chủ đạo | SINGLE_TABLE | JOINED | TABLE_PER_CLASS |
|---|---|---|---|
| `from Payment` lấy mọi loại | Thường gọn: một bảng | Có thể nhiều subtype joins | Có thể union nhiều bảng |
| `from CardPayment` | Một bảng + discriminator | Join root với bảng card | Một bảng card |
| Projection chỉ chọn field chung | Một bảng | Có thể chỉ root table | Thường phải kết hợp nhiều bảng |
| Lọc theo type | Discriminator rất trực tiếp | Discriminator/exists/join subtype tùy mapping | Có thể giới hạn union branch |
| Chỉ đọc field đặc thù của một subtype | Một bảng rộng | Root + subtype | Một bảng subtype |
| Schema nhiều field chỉ có ở mỗi subtype | Nhiều cột nullable | Cột tách theo bảng con, ràng buộc rõ | Cột chung lặp lại mỗi bảng |
| Thêm subtype mới | Thêm discriminator + cột liên quan | Thêm bảng con, có thể tăng joins root | Thêm bảng concrete và nhánh union |
| Quan hệ FK từ bảng khác tới `Payment` | Thuận tiện: root table | Thuận tiện: root table | Khó enforce bằng FK tới một root table không tồn tại |

Một số định hướng:

**SINGLE_TABLE** thường phù hợp hierarchy vừa/nhỏ, truy vấn root thường xuyên, subtype khác biệt không quá lớn và chấp nhận bảng rộng. Việc có nhiều row với NULL ở các cột subtype không tự động khiến database chậm; phải đo row/page storage và index thực tế.

**JOINED** phù hợp khi muốn schema chuẩn hóa, các subtype có dữ liệu lớn hoặc ràng buộc riêng và truy vấn thường chọn subtype cụ thể/projection. Khi root query full entity rất thường xuyên trên hierarchy nhiều subtype, cần quan sát tác động các join.

**TABLE_PER_CLASS** có thể thuận tiện khi phần lớn truy vấn làm việc độc lập với từng concrete type, nhưng polymorphic root query, pagination và FK associations trở nên phức tạp. Đừng chọn TABLE_PER_CLASS chỉ vì muốn “mỗi lớp có bảng riêng” mà không đánh giá việc query từ root.

### Dùng index đúng với SQL

- SINGLE_TABLE: index trên `payment_kind` có thể giúp lọc subtype; composite index như `(payment_kind, amount)` phù hợp nếu query theo loại và khoảng số tiền thường xuyên, tùy thống kê.
- JOINED: root PK index và các bảng subtype PK/FK index là cơ sở cho join; các field subtype thường lọc như `bank_reference` có thể cần index riêng.
- TABLE_PER_CLASS: từng bảng cần index phù hợp query trực tiếp; một `UNION ALL` và `ORDER BY` toàn cục không được tối ưu chỉ bằng index của một bảng.

Đừng tạo quá nhiều index theo “cảm giác”: index chiếm dung lượng và tăng chi phí ghi. Sử dụng `EXPLAIN (ANALYZE, BUFFERS)` trong môi trường thử nghiệm phù hợp để đo thực tế.

## 19. Cách quan sát SQL Hibernate sinh ra

Khi học hoặc điều tra hiệu năng, bật SQL logging trong môi trường kiểm thử. Ví dụ với Spring Boot + Hibernate 6:

~~~properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Với Hibernate 5, logger bind parameters có tên khác. Giá trị bind có thể chứa dữ liệu nhạy cảm; chỉ bật trace khi chính sách môi trường cho phép.

Trong mỗi thí nghiệm, ghi lại:

1. **Câu HQL/JPQL:** truy vấn root, subtype, TYPE, TREAT hay projection?
2. **Mapping inheritance:** SINGLE_TABLE, JOINED hay TABLE_PER_CLASS?
3. **SQL tables:** đọc bảng nào; có `JOIN` các bảng subclass, `UNION ALL`, thêm association joins không?
4. **Bộ lọc:** điều kiện discriminator hoặc type, amount, subtype-specific field được dịch ra sao?
5. **Result shape:** trả scalar, DTO hay managed concrete entity?
6. **Số result rows và câu SQL:** có lazy association loads/N+1 hay không?
7. **Execution plan:** DB quét index/sequence scan, hash join/nested loop, append/union hay sort toàn cục?

Ví dụ so sánh ba truy vấn trên cùng mapping:

~~~jpql
select p from Payment p
select p.id from Payment p
select p from Payment p where type(p) = CardPayment
~~~

Nếu chỉ nhìn mapping mà không xem SQL, dễ kết luận sai rằng cả ba đều phải join/tổ hợp mọi bảng trong hierarchy.

### Quan sát `EXPLAIN`

Với PostgreSQL trong môi trường thử nghiệm, lấy SQL **thật** từ log và chạy:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT ...;
~~~

`EXPLAIN ANALYZE` sẽ thực thi câu query để thu thống kê runtime; đối với `SELECT` thử nghiệm thông thường điều này phù hợp, nhưng không tùy ý chạy đối với DML production hoặc truy vấn nặng. Đọc các chỉ số như actual rows, loops, scan nodes, join nodes, sort spill và buffer hits. Với Hibernate prepared statements, cần dùng tham số/giá trị đại diện đúng dữ liệu workload khi phân tích plan.

## 20. Những nhầm lẫn phổ biến

### 20.1. “`select p from Payment` chỉ trả về object Payment”

Sai với mapped entity hierarchy: truy vấn từ root có tính đa hình, bao gồm subtype concrete. `Payment` có thể là abstract mà truy vấn vẫn hợp lệ.

### 20.2. “Kế thừa Java thì Hibernate luôn tạo JOIN”

Chỉ có chiến lược JOINED mới dựa vào các bảng kế thừa chia sẻ PK/FK; SINGLE_TABLE có một bảng, còn TABLE_PER_CLASS thường dùng union khi truy vấn root. JOIN của association là một vấn đề riêng.

### 20.3. “TABLE_PER_CLASS truy vấn root chỉ cần SELECT bảng cha”

Với root abstract, không có bảng cha vật lý; dữ liệu ở các bảng concrete. Hibernate phải kết hợp các bảng này để truy vấn đa hình.

### 20.4. “Chỉ cần `@MappedSuperclass` là query được superclass”

`@MappedSuperclass` không phải entity; JPQL chuẩn không cho root query theo tên class này. Muốn polymorphic JPQL từ root, root phải là `@Entity` với inheritance mapping phù hợp.

### 20.5. “`TYPE(p) = CardPayment` giống `p.paymentKind = 'CARD'`”

`TYPE` là khái niệm **entity type** trong JPA. Discriminator column là một cách triển khai trong SINGLE_TABLE, còn JOINED/TABLE_PER_CLASS có thể dùng cấu trúc khác. Không buộc domain model phải expose discriminator thành field nghiệp vụ chỉ để filter subtype.

### 20.6. “Hễ JOINED là query nào cũng LEFT JOIN mọi subclass”

Một query root trả full entities có thể cần nhiều join; projection chỉ lấy field root có thể chỉ đọc bảng root. Các bộ lọc type, association fetch và provider optimizations còn thay đổi plan.

### 20.7. “`TREAT` luôn gây một JOIN”

Trong SINGLE_TABLE, field subtype nằm cùng bảng nên không cần inheritance join; trong JOINED, cần truy cập bảng chứa field; trong TABLE_PER_CLASS, nhánh cụ thể có thể được chọn. Chi phí đến từ mapping và kết quả query cần, không chỉ từ cú pháp `TREAT`.

### 20.8. “Truy vấn root chậm thì đổi hết sang EAGER”

`FetchType.EAGER` điều khiển association fetch, không biến đổi chiến lược inheritance. EAGER tràn lan có thể làm phát sinh N+1 hoặc SQL nhiều JOIN khác. Để tối ưu query root, xét projection/subtype filters trước, sau đó fetch plan cho các association thực sự cần.

### 20.9. “Sắp xếp ID tăng là sắp xếp thời điểm thanh toán”

`SEQUENCE` và allocation/cache có thể cấp ID không theo thứ tự commit, nhiều transaction có thể hoàn thành ngược thứ tự. Nếu nghiệp vụ cần thời gian thanh toán, dùng field thời gian và chiến lược tie-break phù hợp.

### 20.10. “JOINED không có discriminator nên DB tự biết subtype”

Database chỉ thấy các bảng và khóa. ORM diễn giải row ở bảng subtype hoặc discriminator metadata để chọn Java class. Nếu dữ liệu được chèn trực tiếp không tuân thủ invariant một concrete subtype mỗi root, Hibernate có thể gặp trạng thái không hợp lệ. Cần quản lý schema và migration.

## 21. Thực hành: cùng một HQL, quan sát ba chiến lược

Hãy dựng ba cấu hình **riêng biệt** cho cùng hierarchy `Payment`; mỗi lần chỉ bật một mapping `@Inheritance` và schema tương ứng. Không tạo ba entity root trùng tên `Payment` trong cùng persistence unit rồi mong Hibernate hiểu chúng là một hierarchy.

### Thí nghiệm A — Truy vấn root

~~~java
List<Payment> rows = entityManager.createQuery(
    "select p from Payment p order by p.id",
    Payment.class
).getResultList();
~~~

Dự đoán hình dạng:

| Strategy | Dự đoán SQL chính |
|---|---|
| SINGLE_TABLE | `SELECT FROM payment`. |
| JOINED | `SELECT FROM payment` và các `LEFT JOIN` subtype cần thiết. |
| TABLE_PER_CLASS | `UNION ALL` các concrete subtype tables. |

Quan sát số rows và concrete entity classes; các kết quả nghiệp vụ phải biểu diễn cùng một tập payment đã tạo.

### Thí nghiệm B — Truy vấn CardPayment

~~~java
List<CardPayment> rows = entityManager.createQuery(
    "select c from CardPayment c",
    CardPayment.class
).getResultList();
~~~

Kỳ vọng thường thấy:

- SINGLE_TABLE: một bảng payment + filter discriminator CARD.
- JOINED: `card_payment JOIN payment`.
- TABLE_PER_CLASS: `card_payment` độc lập.

### Thí nghiệm C — Projection chỉ lấy amount

~~~java
List<BigDecimal> amounts = entityManager.createQuery(
    "select p.amount from Payment p",
    BigDecimal.class
).getResultList();
~~~

So sánh các bảng ORM thực sự đọc. Đặc biệt, trong JOINED có thể không cần join bảng con; trong TABLE_PER_CLASS vẫn cần kết hợp nhiều bảng concrete.

### Thí nghiệm D — `TYPE` và `TREAT`

~~~java
List<Payment> cards = entityManager.createQuery(
    """
    select p
    from Payment p
    where type(p) = CardPayment
      and treat(p as CardPayment).cardLastFour = :lastFour
    """,
    Payment.class
).setParameter("lastFour", "4242")
 .getResultList();
~~~

Xem Hibernate lọc discriminator, thêm join subtype hay giới hạn union branch. Xác minh không có bank/cash payment trong kết quả.

### Thí nghiệm E — COUNT và phân trang

~~~java
Long total = entityManager.createQuery(
    "select count(p) from Payment p",
    Long.class
).getSingleResult();

List<Payment> page = entityManager.createQuery(
    "select p from Payment p order by p.amount desc, p.id",
    Payment.class
).setFirstResult(0)
 .setMaxResults(10)
 .getResultList();
~~~

Đọc số bảng, cấu trúc COUNT, JOIN/UNION và sort/limit. Tăng lượng dữ liệu để execution plan có ý nghĩa, nhưng không đánh giá hiệu năng từ một lần chạy trên bộ dữ liệu quá nhỏ.

### Thí nghiệm F — Đọc SQL từ association

Thêm entity có `@ManyToOne Payment payment` trong môi trường mapping phù hợp và query join tới payment. Với SINGLE_TABLE/JOINED, thử xem join association có làm thêm inheritance join không. Với TABLE_PER_CLASS, phân tích ràng buộc FK có thể định nghĩa ở DB trước khi thiết kế association đến abstract root.

## 22. Quy tắc lựa chọn theo loại truy vấn

Trước khi chọn inheritance strategy, hãy trả lời:

1. **Có thường xuyên query từ root `Payment` không?** Nếu có, một bảng SINGLE_TABLE thường đơn giản; JOINED và TABLE_PER_CLASS cần được đo ở mức root query.
2. **Có thường chỉ query một subtype cụ thể không?** TABLE_PER_CLASS có thể dùng một bảng; JOINED dùng join root + subtype; SINGLE_TABLE dùng discriminator filter.
3. **Field chung và field subtype chênh lệch bao nhiêu?** Bảng SINGLE_TABLE có thể rộng; JOINED giữ cột đặc thù riêng; TABLE_PER_CLASS lặp lại các cột chung.
4. **Có nhiều entity khác tham chiếu `Payment` không?** SINGLE_TABLE/JOINED có root table thuận tiện làm đích FK; TABLE_PER_CLASS cần cân nhắc kỹ thiết kế toàn vẹn dữ liệu.
5. **Có cần ràng buộc `NOT NULL` đặc thù mỗi subtype không?** JOINED/TABLE_PER_CLASS thuận lợi cho constraint trên bảng con; SINGLE_TABLE có thể cần `CHECK` theo discriminator.
6. **Có pagination, COUNT hoặc reporting thường xuyên trên mọi loại không?** Đánh giá rõ chi phí JOIN/UNION, sorting và aggregation.
7. **Subtype thường xuyên được thêm mới không?** SINGLE_TABLE thêm discriminator/cột; JOINED thêm bảng và có thể thêm join; TABLE_PER_CLASS thêm bảng/union branch.

### Mô hình ghi nhớ

~~~text
SELECT p FROM Payment p
          |
          +-- SINGLE_TABLE ----> payment
          |                       (một bảng + discriminator)
          |
          +-- JOINED ----------> payment
          |                          |
          |                          +-- LEFT JOIN card_payment
          |                          +-- LEFT JOIN bank_payment
          |                          +-- LEFT JOIN cash_payment
          |                       (chỉ các joins cần để dựng kết quả)
          |
          +-- TABLE_PER_CLASS -> card_payment
                                      UNION ALL
                                  bank_payment
                                      UNION ALL
                                  cash_payment
                                  (mỗi concrete table có cột chung)
~~~

**Truy vấn đa hình** là lời hứa ở cấp ORM rằng query root có thể trả về các subtype cụ thể. **Chiến lược kế thừa** quyết định dữ liệu nằm ở đâu, nên nó cũng quyết định SQL cần một bảng, các JOIN theo PK/FK, hay UNION của nhiều bảng. **Hình dạng kết quả** (entity, projection, subtype, type-filtered query) quyết định Hibernate có phải truy cập đủ mọi bảng để dựng concrete objects hay không. Khi đọc log SQL, hiểu rõ hai lớp quyết định đó sẽ giúp chẩn đoán hiệu năng và chọn mô hình kế thừa phù hợp thay vì suy đoán từ annotation.
