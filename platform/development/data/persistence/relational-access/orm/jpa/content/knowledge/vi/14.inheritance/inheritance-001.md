# Phân biệt kế thừa Java và kế thừa trong mô hình lưu trữ

> **Chủ đề:** Data Persistence – Relational Access, ORM, JPA  
> **Nhóm kiến thức:** Kế thừa

Trong Java, **kế thừa** là quan hệ giữa các **kiểu dữ liệu**: lớp con kế thừa thuộc tính, phương thức, có thể ghi đè hành vi và được dùng qua tham chiếu lớp cha. Trong cơ sở dữ liệu quan hệ, dữ liệu được tổ chức bằng **bảng, cột, hàng, khóa chính, khóa ngoại và ràng buộc**. Database không tự suy ra rằng hai bảng có quan hệ kế thừa chỉ vì hai class Java có từ khóa **extends**.

Khi dùng Jakarta Persistence (JPA), một lớp Java kế thừa lớp khác **chưa đủ để xác định dữ liệu được lưu ở đâu**. Ta còn cần chọn **cách ánh xạ**: chỉ tái sử dụng metadata với **@MappedSuperclass**, hoặc thiết lập một **entity inheritance hierarchy** với **SINGLE_TABLE**, **JOINED** hay **TABLE_PER_CLASS**.

Ví dụ mô hình Java:

~~~java
public abstract class Payment {
    private BigDecimal amount;
}

public class CardPayment extends Payment {
    private String lastFourDigits;
}

public class BankTransferPayment extends Payment {
    private String bankReference;
}
~~~

Những class ấy có thể dẫn tới các kiểu lưu trữ rất khác nhau:

~~~text
A. @MappedSuperclass: tái sử dụng mapping, không có entity root
   card_payments                 bank_transfer_payments
   id, amount, last_four_digits  id, amount, bank_reference

B. SINGLE_TABLE: một bảng cho cả phân cấp
   payments
   id, payment_kind, amount, last_four_digits, bank_reference

C. JOINED: một bảng root và bảng cho từng subtype
   payments(id, amount, created_at)
       ├── card_payments(payment_id, last_four_digits)
       └── bank_transfer_payments(payment_id, bank_reference)

D. TABLE_PER_CLASS: bảng cho từng concrete entity
   card_payments                 bank_transfer_payments
   id, amount, last_four_digits  id, amount, bank_reference
   (nhưng Payment vẫn là entity root để query đa hình)
~~~

Cách A và D có thể tạo các bảng trông giống nhau, nhưng **ngữ nghĩa persistence khác nhau**. Với **@MappedSuperclass**, lớp cha không phải entity nên không có truy vấn JPQL root qua lớp cha. Với **TABLE_PER_CLASS**, lớp cha là entity trong một phân cấp JPA, cho phép query tất cả subtype từ root.

Bài học này giúp phân biệt **kế thừa ngôn ngữ Java** với **kế thừa trong mô hình ORM**, hiểu schema/SQL của từng chiến lược, lựa chọn giải pháp theo query và ràng buộc dữ liệu thực tế, cũng như tránh những lỗi thường gặp khi phát triển hoặc migration hệ thống.

## 1. Kế thừa trong Java làm được những gì?

### 1.1. is-a, thuộc tính và đa hình

~~~java
public abstract class Payment {
    private final BigDecimal amount;

    protected Payment(BigDecimal amount) {
        this.amount = amount;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public abstract String methodCode();
}
~~~

~~~java
public final class CardPayment extends Payment {
    private final String lastFourDigits;

    public CardPayment(BigDecimal amount, String lastFourDigits) {
        super(amount);
        this.lastFourDigits = lastFourDigits;
    }

    @Override
    public String methodCode() {
        return "CARD";
    }
}
~~~

~~~java
public final class BankTransferPayment extends Payment {
    private final String bankReference;

    public BankTransferPayment(BigDecimal amount, String bankReference) {
        super(amount);
        this.bankReference = bankReference;
    }

    @Override
    public String methodCode() {
        return "TRANSFER";
    }
}
~~~

Sử dụng:

~~~java
Payment payment = new CardPayment(
    new BigDecimal("150000.00"), "1234");

System.out.println(payment.methodCode()); // CARD
~~~

**Payment** là kiểu tham chiếu; instance thực sự là **CardPayment**. Java chọn hành vi override theo runtime type, gọi là **polymorphism**.

Từ khóa **extends** giúp:

- Tái sử dụng state và method có thể truy cập từ superclass.
- Khai báo/ghi đè hành vi của subclass.
- Xử lý nhiều subtype qua một type chung.
- Mô hình hóa quan hệ **CardPayment is-a Payment**.
- Áp dụng các quy tắc về constructor, access modifier, abstract/final và method dispatch của Java.

Nó **không** tự chọn tên bảng, cột discriminator, cấu trúc khóa chính hay SQL để lưu object. Chương trình Java không có JPA vẫn sử dụng kế thừa bình thường.

### 1.2. Kế thừa khác composition

~~~java
class CardPayment extends Payment { }
~~~

là quan hệ **is-a**, còn:

~~~java
class Order {
    private Address shippingAddress;
}
~~~

là quan hệ **has-a**: Order **chứa** Address, không phải một loại Address. Với value object như địa chỉ, tiền tệ hoặc tọa độ, JPA có **@Embeddable/@Embedded**; không phải cứ muốn tái sử dụng class thì tạo entity inheritance.

Quy tắc thiết kế: chỉ dùng kế thừa khi subtype thực sự có thể thay thế superclass theo ý nghĩa miền dữ liệu, thay vì chọn kế thừa chỉ để giảm trùng vài dòng khai báo field.

### 1.3. Interface không tự tạo entity hierarchy

~~~java
public interface Payable {
    BigDecimal getAmount();
}

public class Invoice implements Payable { /* ... */ }
public class SubscriptionFee implements Payable { /* ... */ }
~~~

Hai class cùng **implements Payable** có hợp đồng Java chung, nhưng JPA không vì vậy tự cung cấp một entity root Payable để query tất cả Invoice và SubscriptionFee. Một interface không thay thế **@Entity**, **@Inheritance** hay metadata persistence của các concrete classes.

### 1.4. Kế thừa lớp không đồng nghĩa kế thừa bảng

Trong SQL, hai bảng có cùng cột:

~~~sql
CREATE TABLE card_payments (
    id BIGINT PRIMARY KEY,
    amount NUMERIC(19, 2) NOT NULL,
    last_four_digits VARCHAR(4) NOT NULL
);

CREATE TABLE bank_transfer_payments (
    id BIGINT PRIMARY KEY,
    amount NUMERIC(19, 2) NOT NULL,
    bank_reference VARCHAR(100) NOT NULL
);
~~~

không tự có quan hệ “bank_transfer_payments extends card_payments”. Truy vấn **card_payments** không tự trả các row của bảng còn lại. Muốn đọc cả hai bằng SQL có thể dùng **UNION ALL**, view hoặc một mô hình bảng gốc/bảng con được thiết kế rõ ràng.

Một số RDBMS có tính năng table inheritance đặc thù, nhưng không nên đồng nhất với các chiến lược kế thừa chuẩn JPA. Khi nói “kế thừa trong cơ sở dữ liệu” ở bài này, ta đang nói **cách ORM biểu diễn một hierarchy Java trong schema quan hệ**, không giả định RDBMS hỗ trợ Java-style inheritance.

## 2. Ba câu hỏi độc lập phải trả lời

| Câu hỏi | Lớp chịu trách nhiệm | Ví dụ |
|---|---|---|
| CardPayment có phải một Payment? | Java type system | CardPayment extends Payment |
| CardPayment được lưu trong bảng nào? | JPA mapping + DB schema | SINGLE_TABLE/JOINED/TABLE_PER_CLASS |
| Query Payment có trả CardPayment? | JPA entity inheritance | Có khi Payment là entity root |
| Có query được superclass dùng chung metadata? | JPA managed type | Không nếu chỉ là @MappedSuperclass |
| Tham chiếu Payment bằng FK được không? | Entity mapping + DB schema | Dễ hơn khi có bảng Payment chung |
| Bảng có UNIQUE/CHECK/FK thật không? | Database migration | Phải tạo và kiểm tra tại DB |

Một file Java compile thành công không chứng minh mapping JPA hợp lệ, và một mapping JPA hợp lệ không chứng minh các constraint đã có trong database production. Cần hiểu **Java type**, **ORM entity model**, **physical relational model** là ba tầng có mối liên hệ nhưng không đồng nhất.

## 3. Những lựa chọn trong JPA

| Cơ chế | Annotation | Lớp cha là entity? | Lưu trữ thường gặp | Truy vấn đa hình từ lớp cha? |
|---|---|---|---|---|
| Tái sử dụng mapping | @MappedSuperclass | Không | Field cha lặp trong bảng entity con | Không |
| Một bảng chung | @Entity + @Inheritance(SINGLE_TABLE) | Có | Một bảng, cột discriminator | Có |
| Bảng cha/con | @Entity + @Inheritance(JOINED) | Có | Bảng root và bảng subtype nối PK | Có |
| Một bảng cho mỗi concrete class | @Entity + @Inheritance(TABLE_PER_CLASS) | Có | Mỗi bảng concrete chứa inherited fields | Có, thường UNION |
| Nhúng giá trị | @Embeddable/@Embedded | Không | Field giá trị trong bảng owner | Không như entity độc lập |
| Một entity dùng nhiều bảng | @SecondaryTable | Một entity | Các cột của một entity nằm ở nhiều bảng | Không tự tạo hierarchy |

**abstract class** không quyết định mapping. Một superclass abstract có thể chỉ là class Java bình thường, có thể đánh dấu **@MappedSuperclass**, hoặc có thể là **@Entity** làm root được truy vấn đa hình.

### 3.1. Mặc định entity inheritance

Nếu một entity extends một entity khác và root không chỉ định **@Inheritance**, chiến lược mặc định theo JPA là **SINGLE_TABLE**. Nên khai báo rõ trên root để tránh cấu trúc lưu trữ quan trọng bị phụ thuộc vào việc người đọc nhớ default:

~~~java
@Entity
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
public abstract class Payment {
    // ...
}
~~~

Không thể tùy ý chọn SINGLE_TABLE cho một subclass và JOINED cho subclass khác trong cùng một hierarchy chuẩn mà mong provider áp dụng mỗi nhánh riêng; chiến lược áp dụng cho cả entity inheritance hierarchy.

## 4. @MappedSuperclass: tái sử dụng mapping, không tạo entity root

Nhiều entity không liên quan đều cần **id, createdAt, updatedAt**. Ví dụ Customer và Product đều được tạo/sửa theo thời gian, nhưng Product không phải một loại Customer và không có nhu cầu query mọi “BaseRecord”.

### 4.1. Lớp cha chỉ giữ metadata

~~~java
package com.example.common;

import jakarta.persistence.*;
import java.time.Instant;

@MappedSuperclass
public abstract class BaseRecord {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at")
    private Instant updatedAt;

    protected BaseRecord() { }

    @PrePersist
    protected void onCreate() {
        Instant now = Instant.now();
        createdAt = now;
        updatedAt = now;
    }

    @PreUpdate
    protected void onUpdate() {
        updatedAt = Instant.now();
    }

    public Long getId() { return id; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
}
~~~

Hai entity độc lập:

~~~java
@Entity
@Table(name = "customers")
public class Customer extends BaseRecord {
    @Column(name = "email", nullable = false, unique = true)
    private String email;

    protected Customer() { }
}
~~~

~~~java
@Entity
@Table(name = "products")
public class Product extends BaseRecord {
    @Column(name = "sku", nullable = false, unique = true)
    private String sku;

    protected Product() { }
}
~~~

Schema có thể là:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE,
    email VARCHAR(200) NOT NULL UNIQUE
);

CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE,
    sku VARCHAR(100) NOT NULL UNIQUE
);
~~~

Không có bảng **base_records**. JPA dùng mapping định nghĩa trong BaseRecord để ánh xạ từng concrete entity. Hai bảng có thể tự tăng ID độc lập vì chúng **không thuộc chung một entity inheritance hierarchy**.

### 4.2. Không truy vấn trực tiếp BaseRecord như một entity

~~~java
// Không hợp lệ như root JPQL chuẩn khi BaseRecord chỉ là @MappedSuperclass.
em.createQuery("select b from BaseRecord b", BaseRecord.class);
~~~

Và:

~~~java
// Không thể dùng một @MappedSuperclass làm đích entity association chung.
@ManyToOne
private BaseRecord target;
~~~

Vì **BaseRecord không phải @Entity**, nó không có identity/entity name độc lập để JPA query hoặc làm target association. Dù Java cho phép:

~~~java
BaseRecord record = new Product();
~~~

câu lệnh **select b from BaseRecord b** không tự có nghĩa “UNION customers và products”.

Đây là khác biệt rất dễ nhầm: **đa hình trong Java** vẫn tồn tại, nhưng **truy vấn đa hình trong JPA** chỉ có khi có entity root được mapping phù hợp.

### 4.3. Override mapping kế thừa

Một entity legacy muốn đổi cột createdAt:

~~~java
@Entity
@Table(name = "legacy_customers")
@AttributeOverride(
    name = "createdAt",
    column = @Column(
        name = "date_created",
        nullable = false,
        updatable = false
    )
)
public class LegacyCustomer extends BaseRecord {
    // ...
}
~~~

**@AttributeOverride** chỉ thay metadata cột của thuộc tính basic. Khi định nghĩa override, nên nêu đầy đủ cấu hình quan trọng như **nullable**, **updatable**, length/precision/scale nếu có. Nếu superclass chứa association cần override join mapping, dùng **@AssociationOverride** ở vị trí thích hợp.

Mapped superclass có thể dùng chung **@Id**, **@Version**, lifecycle callback và mapping được phép. Không nên đưa quá nhiều hành vi không liên quan vào một superclass chỉ vì nhiều entity cần một vài cột giống nhau.

### 4.4. Trường hợp phù hợp

Chọn **@MappedSuperclass** khi chỉ cần chia sẻ mapping và logic nền như audit timestamps, ID hoặc version, còn các entity:

- có bảng và vòng đời độc lập;
- không cần truy vấn qua một root entity;
- không cần association tới lớp cha;
- không thực sự là các subtype cùng một khái niệm nghiệp vụ.

Chú ý nếu thay đổi một field trong superclass, migration có thể phải cập nhật **nhiều bảng con**; dùng chung mã không có nghĩa schema tự đồng bộ.

## 5. @Entity ở superclass: thiết lập một entity hierarchy

Giả sử Payment thực sự là một khái niệm trong miền nghiệp vụ, CardPayment và BankTransferPayment là các loại cụ thể. Ứng dụng cần:

~~~java
List<Payment> payments = em.createQuery(
    "select p from Payment p", Payment.class
).getResultList();
~~~

và muốn entity khác tham chiếu một Payment bất kể loại:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "payment_id")
private Payment payment;
~~~

Đây là trường hợp cân nhắc **@Entity ở superclass**. Root có thể **abstract** để không tạo Payment “chung chung”, nhưng vẫn là managed entity type để truy vấn đa hình.

### 5.1. Ví dụ root Payment với SINGLE_TABLE

~~~java
package com.example.billing;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;

@Entity
@Table(name = "payments")
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(
    name = "payment_kind",
    discriminatorType = DiscriminatorType.STRING,
    length = 24
)
public abstract class Payment {
    @Id
    @SequenceGenerator(
        name = "payment_id_generator",
        sequenceName = "payment_id_seq",
        allocationSize = 1
    )
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "payment_id_generator"
    )
    private Long id;

    @Column(name = "amount", nullable = false, precision = 19, scale = 2)
    private BigDecimal amount;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    protected Payment() { }

    protected Payment(BigDecimal amount, Instant createdAt) {
        Objects.requireNonNull(amount);
        Objects.requireNonNull(createdAt);
        if (amount.signum() < 0) {
            throw new IllegalArgumentException("Số tiền không được âm");
        }
        this.amount = amount;
        this.createdAt = createdAt;
    }

    public Long getId() { return id; }
    public BigDecimal getAmount() { return amount; }
    public Instant getCreatedAt() { return createdAt; }

    public abstract String methodCode();
}
~~~

Subclass:

~~~java
@Entity
@DiscriminatorValue("CARD")
public class CardPayment extends Payment {
    @Column(name = "last_four_digits", length = 4)
    private String lastFourDigits;

    protected CardPayment() { }

    public CardPayment(
            BigDecimal amount, Instant createdAt, String digits) {
        super(amount, createdAt);
        if (digits == null || !digits.matches("[0-9]{4}")) {
            throw new IllegalArgumentException("Cần đúng bốn chữ số");
        }
        this.lastFourDigits = digits;
    }

    public String getLastFourDigits() { return lastFourDigits; }

    @Override
    public String methodCode() { return "CARD"; }
}
~~~

~~~java
@Entity
@DiscriminatorValue("TRANSFER")
public class BankTransferPayment extends Payment {
    @Column(name = "bank_reference", length = 100)
    private String bankReference;

    protected BankTransferPayment() { }

    public BankTransferPayment(
            BigDecimal amount, Instant createdAt, String reference) {
        super(amount, createdAt);
        if (reference == null || reference.isBlank()) {
            throw new IllegalArgumentException("Thiếu mã giao dịch");
        }
        this.bankReference = reference;
    }

    public String getBankReference() { return bankReference; }

    @Override
    public String methodCode() { return "TRANSFER"; }
}
~~~

Ví dụ này dùng **GenerationType.SEQUENCE** với sequence được định nghĩa ở DB, để minh họa một nguồn ID chung và có thể so sánh với TABLE_PER_CLASS. Với DB không hỗ trợ sequence, cần chọn chiến lược ID khác thích hợp và đảm bảo provider hỗ trợ. Đây là mã dùng để hiểu cấu trúc mapping; mỗi chiến lược được trình bày ở các phần sau là **biến thể thay thế**, không đăng ký ba biến thể cùng lúc trong một persistence unit.

### 5.2. Root abstract vẫn query được

~~~java
Payment payment = em.find(Payment.class, paymentId);
List<Payment> payments = em.createQuery(
    "select p from Payment p order by p.createdAt desc",
    Payment.class
).getResultList();
~~~

Payment là abstract nên không thể **new Payment(...)**, nhưng là **@Entity**, nên JPA có thể truy vấn polymorphic root. Những object được trả về có concrete type là CardPayment hoặc BankTransferPayment tùy dữ liệu.

Entity inheritance còn cho phép association tới root Payment, điều mà @MappedSuperclass không làm được với tư cách target entity chung.

## 6. SINGLE_TABLE: một bảng cho toàn bộ hierarchy

SINGLE_TABLE lưu inherited attributes và mọi subtype-specific attributes vào cùng một bảng. Một cột **discriminator** cho biết mỗi hàng thuộc subtype nào.

### 6.1. Mapping

~~~java
@Entity
@Table(name = "payments")
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(
    name = "payment_kind",
    discriminatorType = DiscriminatorType.STRING,
    length = 24
)
public abstract class Payment { /* id, amount, createdAt ... */ }
~~~

~~~java
@Entity
@DiscriminatorValue("CARD")
public class CardPayment extends Payment { /* lastFourDigits ... */ }
~~~

~~~java
@Entity
@DiscriminatorValue("TRANSFER")
public class BankTransferPayment extends Payment { /* bankReference ... */ }
~~~

Discriminator value nên được đặt rõ để bảo đảm tương thích với dữ liệu và deployment, tránh phụ thuộc tên class tự động khi refactor.

### 6.2. Schema và dữ liệu

~~~sql
CREATE SEQUENCE payment_id_seq START WITH 1 INCREMENT BY 1;

CREATE TABLE payments (
    id BIGINT PRIMARY KEY,
    payment_kind VARCHAR(24) NOT NULL,
    amount NUMERIC(19, 2) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,

    last_four_digits VARCHAR(4),
    bank_reference VARCHAR(100),

    CONSTRAINT chk_payment_kind CHECK (
        payment_kind IN ('CARD', 'TRANSFER')
    ),

    CONSTRAINT chk_payment_subtype_fields CHECK (
        (
            payment_kind = 'CARD'
            AND last_four_digits IS NOT NULL
            AND bank_reference IS NULL
        )
        OR
        (
            payment_kind = 'TRANSFER'
            AND bank_reference IS NOT NULL
            AND last_four_digits IS NULL
        )
    ),

    CONSTRAINT chk_payment_amount CHECK (amount >= 0)
);
~~~

DDL là ví dụ PostgreSQL nhằm giải thích cấu trúc. Dữ liệu:

| id | payment_kind | amount | last_four_digits | bank_reference |
|---:|---|---:|---|---|
| 101 | CARD | 150000.00 | 1234 | NULL |
| 102 | TRANSFER | 420000.00 | NULL | TXN-A7 |

Một hàng CARD không có bankReference, và một hàng TRANSFER không có lastFourDigits. Vì thế **các cột chỉ thuộc subtype phải thường cho phép NULL ở mức bảng**, trong khi nghiệp vụ có thể yêu cầu không null **khi subtype tương ứng được chọn**.

Nếu đặt **@Column(nullable=false)** trực tiếp cho field CardPayment.lastFourDigits trong SINGLE_TABLE và provider tạo DDL không có điều kiện, bảng chung có thể không lưu nổi BankTransferPayment. Phải thiết kế **CHECK phụ thuộc discriminator** và validation theo subtype, thay vì chỉ đặt NOT NULL vô điều kiện.

### 6.3. SQL minh họa

Persist:

~~~java
Payment p = new CardPayment(
    new BigDecimal("150000.00"), Instant.now(), "1234");
em.persist(p);
~~~

SQL có thể tương tự:

~~~sql
INSERT INTO payments (
    id, payment_kind, amount, created_at, last_four_digits
)
VALUES (?, 'CARD', 150000.00, ?, '1234');
~~~

Query root:

~~~sql
SELECT id, payment_kind, amount, created_at,
       last_four_digits, bank_reference
FROM payments
ORDER BY created_at DESC;
~~~

Provider dựa trên **payment_kind** để dựng concrete subtype. Không cần JOIN các bảng subtype vì chúng không tồn tại.

### 6.4. Ưu điểm và nhược điểm

**Ưu điểm:** một bảng và một ID namespace chung; polymorphic SELECT đơn giản; FK từ Order/Refund tới Payment có thể trỏ thẳng **payments(id)**; ghi một Payment thường chỉ cần một hàng; thuận tiện nếu các subtype chia sẻ nhiều field và hệ thống thường query mọi Payment.

**Nhược điểm:** nhiều cột NULL khi subtype có field riêng; constraint đặc thù subtype khó biểu diễn bằng NOT NULL đơn thuần; bảng có thể rất rộng; schema chung bị ảnh hưởng khi thêm subtype; discriminator trở thành dữ liệu quan trọng phải migration khi đổi mã loại; workload/retention của các subtype có thể rất khác nhau nhưng chia sẻ một bảng.

### 6.5. Khi nào chọn?

SINGLE_TABLE phù hợp nếu:

- Phần lớn field/hành vi chung có ý nghĩa thật.
- Polymorphic query và polymorphic FK tới root là nhu cầu lớn.
- Số subclass và số field riêng được kiểm soát.
- Có thể dùng CHECK/validation để bảo vệ subtype-specific rules.
- Độ đơn giản của truy vấn chung quan trọng hơn phân tách vật lý các subtype.

Không chọn chỉ vì đây là default nếu schema sẽ thành một bảng rất rộng, nhiều loại khác biệt và constraint khó bảo trì.

## 7. JOINED: bảng gốc và các bảng subtype

Với **JOINED**, các field khai báo ở entity root được lưu trong bảng gốc. Field riêng của mỗi subclass nằm trong bảng phụ của subclass. Một concrete object được biểu diễn bằng **một row root + một row subtype**, dùng cùng giá trị khóa chính.

### 7.1. Mapping JPA

Đổi cấu hình root so với SINGLE_TABLE:

~~~java
@Entity
@Table(name = "payments")
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class Payment {
    // @Id, amount, createdAt, ...
}
~~~

Các subclass:

~~~java
@Entity
@Table(name = "card_payments")
@PrimaryKeyJoinColumn(name = "payment_id")
public class CardPayment extends Payment {
    @Column(name = "last_four_digits", nullable = false, length = 4)
    private String lastFourDigits;
    // Constructor/getter...
}
~~~

~~~java
@Entity
@Table(name = "bank_transfer_payments")
@PrimaryKeyJoinColumn(name = "payment_id")
public class BankTransferPayment extends Payment {
    @Column(name = "bank_reference", nullable = false, length = 100)
    private String bankReference;
    // Constructor/getter...
}
~~~

Đây là **mapping thay thế** cho ví dụ SINGLE_TABLE: không khai báo đồng thời hai bộ entity có cùng tên trong một persistence unit. **@PrimaryKeyJoinColumn** chỉ tên PK/FK của bảng subclass tham chiếu bảng root. Nếu default name phù hợp, annotation này có thể được lược bỏ; khai báo tường minh giúp kiểm soát schema.

Với JOINED, discriminator có thể được sử dụng tùy cấu hình và provider nhưng không phải cách phân biệt duy nhất như SINGLE_TABLE: sự tồn tại hàng ở bảng subtype có thể là cơ sở xác định concrete type.

### 7.2. Relational schema

~~~sql
CREATE SEQUENCE payment_id_seq START WITH 1 INCREMENT BY 1;

CREATE TABLE payments (
    id BIGINT PRIMARY KEY,
    amount NUMERIC(19, 2) NOT NULL CHECK (amount >= 0),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE card_payments (
    payment_id BIGINT PRIMARY KEY,
    last_four_digits VARCHAR(4) NOT NULL,

    CONSTRAINT fk_card_payment_base
        FOREIGN KEY (payment_id) REFERENCES payments(id)
);

CREATE TABLE bank_transfer_payments (
    payment_id BIGINT PRIMARY KEY,
    bank_reference VARCHAR(100) NOT NULL,

    CONSTRAINT fk_transfer_payment_base
        FOREIGN KEY (payment_id) REFERENCES payments(id)
);
~~~

Dữ liệu tương ứng:

~~~text
payments
id    amount       created_at
101   150000.00    ...
102   420000.00    ...

card_payments
payment_id   last_four_digits
101          1234

bank_transfer_payments
payment_id   bank_reference
102          TXN-A7
~~~

Một **CardPayment** là **một entity JPA**, dù dữ liệu nằm trên hai hàng của hai bảng. Đây không phải hai entity độc lập có quan hệ @OneToOne. Đối tượng Java vẫn có một ID và một identity trong persistence context.

### 7.3. INSERT/SELECT minh họa

Persist CardPayment có thể dẫn đến:

~~~sql
INSERT INTO payments (id, amount, created_at)
VALUES (101, 150000.00, ?);

INSERT INTO card_payments (payment_id, last_four_digits)
VALUES (101, '1234');
~~~

Hai INSERT thuộc **một transaction**; nếu INSERT subtype thất bại, transaction cần rollback để tránh root row không đầy đủ.

Query CardPayment bằng ID:

~~~sql
SELECT p.id, p.amount, p.created_at,
       cp.last_four_digits
FROM payments p
JOIN card_payments cp ON cp.payment_id = p.id
WHERE p.id = 101;
~~~

Query root **select p from Payment p** có thể yêu cầu JOIN các bảng subtype hoặc một SQL strategy khác của provider để xác định type và lấy subclass fields. SQL thực tế phụ thuộc JPA provider, dialect, fetch plan, discriminator và hierarchy; hai statement trên chỉ nhằm giải thích cấu trúc.

### 7.4. Điểm mạnh

- Field chung được chuẩn hóa vào một bảng root.
- Field riêng của subtype có bảng riêng, nên **NOT NULL** và **CHECK** đơn giản hơn.
- Có một **payments.id** chung để FK từ Order/Refund tham chiếu mọi loại Payment.
- Bổ sung field chung thường sửa bảng root, field riêng sửa bảng con.
- Bảng con có thể có index, constraint và chiến lược vận hành phù hợp subtype.
- Hệ thống có nhiều nghiệp vụ dùng entity root vẫn có một identity chung.

### 7.5. Điểm yếu và giới hạn DB constraints

- Query subtype và polymorphic query thường đắt hơn vì JOIN.
- INSERT/DELETE có thể cần thao tác trên nhiều bảng.
- Hierarchy nhiều tầng làm join chain sâu hơn.
- Schema/migration phức tạp hơn một bảng chung.
- Foreign key từ bảng con đến root chỉ bảo đảm **bảng con không tham chiếu root không tồn tại**; nó không tự bảo đảm mỗi root luôn có đúng một row ở một bảng con.
- Nếu SQL ngoài ORM có quyền, có thể cố tình tạo cùng root ID ở hai bảng subtype. Muốn DB chặn trạng thái đó cần thêm policy/discriminator consistency/trigger hoặc giới hạn đường ghi.

Ví dụ dữ liệu về mặt FK vẫn có thể hợp lệ nhưng trái với mô hình subtype:

~~~text
payments.id = 101
card_payments.payment_id = 101
bank_transfer_payments.payment_id = 101
~~~

JPA coi một instance có một concrete class; schema với hai FK độc lập không tự thực thi “đúng một subtype”. Đây là minh họa rõ về khoảng cách giữa **entity hierarchy** và **toàn vẹn quan hệ vật lý**.

### 7.6. Khi chọn JOINED?

Phù hợp khi:

- Nhiều field chung thực sự thuộc một root domain entity.
- Có nhiều field subtype-specific bắt buộc.
- Cần FK đa hình tới một bảng root ổn định.
- Muốn tách các thuộc tính subtype khỏi bảng dữ liệu chung.
- Sẵn sàng trả chi phí JOIN và migration nhiều bảng.

## 8. TABLE_PER_CLASS: bảng theo concrete class nhưng có entity hierarchy

**TABLE_PER_CLASS** lưu inherited fields cùng với field riêng trong **mỗi bảng concrete subtype**, nhưng **root vẫn là @Entity**. Vì vậy query JPA có thể chạy qua root Payment.

### 8.1. Mapping

~~~java
@Entity
@Inheritance(strategy = InheritanceType.TABLE_PER_CLASS)
public abstract class Payment {
    @Id
    @SequenceGenerator(
        name = "payment_id_generator",
        sequenceName = "payment_id_seq",
        allocationSize = 1
    )
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "payment_id_generator"
    )
    private Long id;

    @Column(name = "amount", nullable = false, precision = 19, scale = 2)
    private BigDecimal amount;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    // Constructors/getters...
}
~~~

~~~java
@Entity
@Table(name = "card_payments")
public class CardPayment extends Payment {
    @Column(name = "last_four_digits", nullable = false)
    private String lastFourDigits;
    // ...
}
~~~

~~~java
@Entity
@Table(name = "bank_transfer_payments")
public class BankTransferPayment extends Payment {
    @Column(name = "bank_reference", nullable = false)
    private String bankReference;
    // ...
}
~~~

Trong ví dụ **Payment là abstract**, nên về ý tưởng các bản ghi Payment concrete nằm ở hai bảng con. Những chi tiết DDL khi lớp root abstract phụ thuộc provider và metadata khác; không lấy ví dụ này làm script tự động có thể chạy trên mọi RDBMS.

### 8.2. Schema minh họa

~~~sql
CREATE SEQUENCE payment_id_seq START WITH 1 INCREMENT BY 1;

CREATE TABLE card_payments (
    id BIGINT PRIMARY KEY,
    amount NUMERIC(19, 2) NOT NULL CHECK (amount >= 0),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    last_four_digits VARCHAR(4) NOT NULL
);

CREATE TABLE bank_transfer_payments (
    id BIGINT PRIMARY KEY,
    amount NUMERIC(19, 2) NOT NULL CHECK (amount >= 0),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    bank_reference VARCHAR(100) NOT NULL
);
~~~

Không cần discriminator trên từng bảng: tên bảng giúp xác định loại concrete trong SQL đọc trực tiếp. Nhưng query **Payment** phải hợp nhất các bảng.

### 8.3. Query đa hình có thể cần UNION

~~~java
List<Payment> payments = em.createQuery(
    "select p from Payment p order by p.createdAt desc",
    Payment.class
).getResultList();
~~~

SQL ý tưởng:

~~~sql
SELECT id, amount, created_at,
       last_four_digits,
       NULL AS bank_reference,
       'CARD' AS kind
FROM card_payments

UNION ALL

SELECT id, amount, created_at,
       NULL AS last_four_digits,
       bank_reference,
       'TRANSFER' AS kind
FROM bank_transfer_payments;
~~~

Đây là SQL minh họa; provider có thể sinh thêm lớp query lồng ngoài, ép kiểu NULL, thêm alias, điều kiện, phân trang hoặc cách truy vấn khác. Khi có nhiều subtype, query root ngày càng phải hợp nhất nhiều nguồn.

Trong khi đó:

~~~java
List<CardPayment> cards = em.createQuery(
    "select c from CardPayment c", CardPayment.class
).getResultList();
~~~

thường chỉ cần bảng **card_payments** và không join root.

### 8.4. Identity trên toàn hierarchy

Nếu hai bảng đều dùng IDENTITY/sequence riêng:

~~~text
card_payments.id = 7
bank_transfer_payments.id = 7
~~~

hai bản ghi có thể dùng cùng giá trị ID nhưng thuộc subtype khác nhau. Với một hierarchy cần query polymorphic, persist qua root và quan hệ tới root, **chiến lược identity nên được xác định ở phạm vi hierarchy**; một nguồn ID chung như sequence/UUID có thể tránh xung đột.

**GenerationType.IDENTITY** trên từng concrete table không được hỗ trợ/tương thích giống nhau với TABLE_PER_CLASS ở các provider, bởi nó không bảo đảm không gian ID chung. Cần chọn generator và version provider dựa trên khả năng thực tế. Ví dụ dùng sequence chung để minh họa.

### 8.5. FK đa hình là vấn đề lớn

Với SINGLE_TABLE và JOINED, một bảng **payments(id)** chung làm đích FK:

~~~text
orders.payment_id → payments.id
~~~

Với TABLE_PER_CLASS, nếu không có bảng payments vật lý chứa mọi ID, một khóa ngoại chuẩn:

~~~sql
FOREIGN KEY (payment_id) REFERENCES payments(id)
~~~

không tự có đích tồn tại. DB không thể dùng một FK đơn giản trỏ tùy ý tới **card_payments** hoặc **bank_transfer_payments** dựa trên type.

Muốn một Order tham chiếu Payment đa hình và bảo vệ bằng FK, có thể cần đổi chiến lược inheritance, tách các FK theo subtype, hoặc thiết kế reference+type/registry riêng với validation/constraint thích hợp. Không dựa vào mapping Java để giả định DB có thể tạo một FK trỏ vào nhiều bảng.

### 8.6. Ưu điểm và nhược điểm

**Ưu điểm:** bảng concrete có đủ cột riêng, dễ đặt NOT NULL; query subtype thường gọn; mỗi bảng có thể tối ưu index/retention riêng.

**Nhược điểm:** inherited fields lặp trong nhiều schema; migration chung phải chạy trên nhiều bảng; root query thường UNION; FK đa hình khó; identity cần quản lý chung; nhiều subtype khiến query root phức tạp hơn.

TABLE_PER_CLASS có thể hợp lý khi dữ liệu của các subtype vận hành tương đối độc lập và **ít cần query/association polymorphic**. Nếu root Payment là trung tâm giao dịch và nhiều module cần tham chiếu, thường phải cân nhắc kỹ hai chiến lược còn lại.

## 9. Bảng so sánh toàn diện

| Tiêu chí | SINGLE_TABLE | JOINED | TABLE_PER_CLASS |
|---|---|---|---|
| Bảng vật lý | Một bảng chung | Root + bảng subtype | Bảng cho mỗi concrete subtype |
| Nơi lưu inherited fields | Bảng chung | Root | Lặp trong mỗi bảng concrete |
| Field subtype | Cột trong bảng chung | Bảng subtype | Bảng concrete |
| Đọc subtype | Lọc discriminator | JOIN root + subtype | Thường một bảng |
| Đọc root đa hình | Thường một bảng | JOIN/SQL kế thừa của provider | Thường UNION |
| Ghi một subtype | Thường một row | Root + row subtype | Một row concrete |
| Constraint subtype-specific | CHECK theo loại | NOT NULL ở bảng subtype | NOT NULL ở bảng concrete |
| FK tới root Payment | Đơn giản qua bảng chung | Đơn giản qua bảng root | Khó nếu không có bảng root |
| Thêm field chung | Một bảng | Root | Nhiều bảng |
| Thêm subtype mới | Thêm cột trong bảng chung | Tạo bảng subtype | Tạo bảng concrete |
| ID chung | Tự nhiên | Root cung cấp | Cần thiết kế generator/global uniqueness |
| Khả năng phân tách vận hành | Hạn chế | Trung bình | Cao hơn giữa các subtype |
| Độ đơn giản của query đa hình | Thường tốt | Trung bình | Thường phức tạp hơn |

Đây là **trade-off khái niệm**, không phải benchmark hiệu năng. Query thật chịu ảnh hưởng index, cardinality, provider, database, cache, số subtype, phân trang và thống kê tối ưu truy vấn.

### 9.1. Một API, ba SQL patterns

Một service có thể gọi:

~~~java
Payment payment = em.find(Payment.class, paymentId);
~~~

nhưng cách thực thi có thể là:

~~~text
SINGLE_TABLE:
    SELECT ... FROM payments WHERE id = ?

JOINED:
    SELECT ... FROM payments p
    LEFT JOIN card_payments ...
    LEFT JOIN bank_transfer_payments ...
    WHERE p.id = ?
    (hoặc SQL provider chọn tương đương)

TABLE_PER_CLASS:
    SELECT ... FROM (
        SELECT ... FROM card_payments
        UNION ALL
        SELECT ... FROM bank_transfer_payments
    ) p WHERE p.id = ?
    (hoặc SQL provider chọn tương đương)
~~~

Java API không nói lên chi phí SQL. Muốn tối ưu, cần hiểu mapping và đo trên database thật.

## 10. Phân biệt @MappedSuperclass và TABLE_PER_CLASS

Đây là cặp gây nhầm nhiều nhất vì **schema có thể trông giống nhau**.

~~~java
@MappedSuperclass
abstract class BasePayment {
    @Id Long id;
    BigDecimal amount;
}

@Entity
class CardPayment extends BasePayment { ... }

@Entity
class BankTransferPayment extends BasePayment { ... }
~~~

so với:

~~~java
@Entity
@Inheritance(strategy = InheritanceType.TABLE_PER_CLASS)
abstract class Payment {
    @Id Long id;
    BigDecimal amount;
}

@Entity
class CardPayment extends Payment { ... }

@Entity
class BankTransferPayment extends Payment { ... }
~~~

Sự khác biệt:

| | @MappedSuperclass | TABLE_PER_CLASS |
|---|---|---|
| Root có @Entity | Không | Có |
| Root là managed entity type | Không | Có |
| Query **select p from Root p** | Không phải JPQL entity root hợp lệ | Có, truy vấn polymorphic |
| Entity khác có thể association tới root | Không qua root mapped superclass | Có ở mô hình JPA, nhưng FK DB có thể khó |
| Root có entity identity | Không | Có |
| Field inherited lưu ở từng bảng concrete | Có thể có | Có |
| Mục đích | Chia sẻ mapping | Biểu diễn hierarchy entity |

Nếu mục tiêu chỉ là chia sẻ **id, createdAt** giữa những class khác loại, **@MappedSuperclass** là công cụ đúng và đơn giản hơn. Nếu mục tiêu là **truy vấn mọi Payment**, cần entity hierarchy thực sự.

## 11. Polymorphic JPQL, TYPE và truy vấn subtype

### 11.1. Query root trả nhiều concrete types

~~~java
List<Payment> payments = em.createQuery(
    """
    select p
    from Payment p
    where p.amount >= :minimum
    order by p.createdAt desc
    """,
    Payment.class
)
.setParameter("minimum", new BigDecimal("100000.00"))
.getResultList();
~~~

Nếu Payment là entity root, result có thể chứa nhiều concrete subtype. Khi gọi:

~~~java
for (Payment p : payments) {
    System.out.println(p.methodCode());
}
~~~

Java dispatch tới implementation của CardPayment/BankTransferPayment theo runtime type. Đây là chỗ **Java polymorphism** và **JPA polymorphic query** kết hợp với nhau.

### 11.2. Query một subclass cụ thể

~~~java
List<CardPayment> cards = em.createQuery(
    """
    select c
    from CardPayment c
    where c.lastFourDigits = :digits
    """,
    CardPayment.class
)
.setParameter("digits", "1234")
.getResultList();
~~~

Query subtype có thể được tối ưu khác tùy strategy. Với SINGLE_TABLE, provider lọc discriminator; với JOINED có thể join bảng root; với TABLE_PER_CLASS thường đọc bảng subtype.

### 11.3. TYPE để lọc subtype

~~~java
List<Payment> onlyCards = em.createQuery(
    """
    select p
    from Payment p
    where type(p) = CardPayment
    """,
    Payment.class
).getResultList();
~~~

**TYPE(p)** trong JPQL diễn đạt kiểu entity cụ thể của p. Nó không yêu cầu bạn so sánh một chuỗi discriminator hard-code như “CARD” trong domain query. Provider chuyển expression sang SQL tùy inheritance strategy.

Với type hierarchy mở rộng nhiều tầng, điều kiện type equality khác với việc chọn mọi descendant của một nhánh; cần xác định chính xác ý nghĩa nghiệp vụ và entity types mong muốn.

### 11.4. TREAT để truy cập thuộc tính của subtype

Khi đã có alias root Payment mà cần dùng field chỉ thuộc CardPayment, JPA có cơ chế **TREAT** để downcast expression sang entity subtype:

~~~java
List<Payment> matching = em.createQuery(
    """
    select p
    from Payment p
    where treat(p as CardPayment).lastFourDigits = :digits
    """,
    Payment.class
)
.setParameter("digits", "1234")
.getResultList();
~~~

Syntax và tối ưu SQL cụ thể cần tương thích với phiên bản JPA/provider đang dùng. Trong bài toán đơn giản, query thẳng **from CardPayment c** như phần trước dễ đọc hơn. TREAT hữu ích khi query phức tạp bắt đầu từ root/association polymorphic.

### 11.5. Entity inheritance không có nghĩa mọi truy vấn phải dùng root

Nếu màn hình chỉ hiện thanh toán chuyển khoản:

~~~java
select t from BankTransferPayment t
~~~

thì query trực tiếp subclass phù hợp hơn **select p from Payment p** rồi dùng **instanceof** để lọc trong Java. Đẩy điều kiện xuống DB giúp tránh tải dữ liệu thừa và tận dụng index.

Đồng thời, không nên trả entity graph trực tiếp cho API JSON nếu có lazy associations hoặc thông tin nhạy cảm; dùng DTO/projection với field đã được chọn.

## 12. Association tới superclass và ràng buộc FK

Giả sử Order lưu Payment:

~~~java
@Entity
@Table(name = "orders")
public class Order {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "payment_id", nullable = false)
    private Payment payment;

    protected Order() { }
}
~~~

Nhờ Payment là entity root, code có thể:

~~~java
Order order = em.find(Order.class, orderId);
Payment payment = order.getPayment();

if (payment instanceof CardPayment card) {
    System.out.println(card.getLastFourDigits());
}
~~~

Nhưng physical FK khác nhau giữa các chiến lược.

### 12.1. SINGLE_TABLE

~~~sql
ALTER TABLE orders
    ADD CONSTRAINT fk_order_payment
    FOREIGN KEY (payment_id) REFERENCES payments(id);
~~~

Một FK có thể tham chiếu mọi subtype vì chúng nằm chung bảng payments.

### 12.2. JOINED

Tương tự, bảng root payments giữ tất cả ID; FK tới **payments(id)** bảo vệ việc Order phải có Payment tồn tại. Khi load subtype, ORM có thể cần join thêm bảng con.

### 12.3. TABLE_PER_CLASS

Không có một bảng root vật lý chứa mọi payment ID trong schema mẫu, nên FK chuẩn tới Payment polymorphic không đơn giản. **JPA association biểu diễn được mong muốn object-oriented**, nhưng **DB schema vẫn cần lời giải riêng** cho referential integrity.

Nếu nghiệp vụ có nhiều quan hệ tham chiếu root, đây có thể là lý do quan trọng để tránh TABLE_PER_CLASS.

### 12.4. @MappedSuperclass không làm target association

~~~java
@MappedSuperclass
abstract class BaseRecord { ... }
~~~

Không thể dùng **@ManyToOne BaseRecord** như một quan hệ entity polymorphic, vì BaseRecord không phải entity. Nếu các concrete classes không thực sự thuộc một domain hierarchy, nên để nhiều association rõ ràng hoặc mô hình hóa một entity chung khác, thay vì thêm @Entity lên BaseRecord chỉ để làm FK.

## 13. Ràng buộc dữ liệu thật và chiến lược kế thừa

JPA annotation không thay thế được constraints thực sự đã tạo trong DB. Mỗi strategy thay đổi **constraint nào có thể đặt tự nhiên**.

### 13.1. Điều kiện NOT NULL khác nhau

Với SINGLE_TABLE, thuộc tính riêng của subtype như **last_four_digits** phải nullable cho hàng TRANSFER. Nếu muốn CardPayment luôn có lastFourDigits, dùng CHECK dựa trên **payment_kind**.

Với JOINED hoặc TABLE_PER_CLASS, lastFourDigits nằm trong bảng card_payments nên NOT NULL có thể áp dụng trực tiếp.

### 13.2. Unique trên inherited business key

Giả sử mọi Payment có **externalReference**, và yêu cầu unique **trên toàn hierarchy**:

- **SINGLE_TABLE:** một unique constraint trên cột chung có thể bảo vệ cả hierarchy.
- **JOINED:** unique constraint trên bảng root bảo vệ cả hierarchy.
- **TABLE_PER_CLASS:** unique riêng trên mỗi bảng subtype **không tự cấm** cùng externalReference ở subtype khác. Cần cơ chế chung như registry/bảng riêng hoặc thiết kế khác.

Đây là lý do lựa chọn inheritance strategy là quyết định về **data integrity**, không chỉ hiệu năng.

### 13.3. CHECK và enum không phải discriminator

Một field nghiệp vụ:

~~~java
@Enumerated(EnumType.STRING)
private PaymentStatus status;
~~~

khác với discriminator dùng xác định **concrete entity type**. **status=COMPLETED** là trạng thái của Payment; **payment_kind=CARD** là loại entity. Không nên nhập hai khái niệm này làm một nếu chúng có lifecycle khác nhau.

### 13.4. Cập nhật subtype không đồng nghĩa thay type

Không nên làm:

~~~java
payment.setPaymentKind("TRANSFER");
~~~

và nghĩ rằng một instance CardPayment tự biến thành BankTransferPayment. **Concrete Java class** được xác định khi tạo object; đổi discriminator trực tiếp bằng native SQL hoặc cập nhật cột bằng code sai có thể làm database không còn tương thích với các field đã lưu.

Nếu nghiệp vụ yêu cầu đổi “phương thức thanh toán”, thường nên tạo một Payment subtype mới hoặc đưa **payment method** thành value object/association thay vì biến đổi identity và Java class của entity cũ. Cần giữ rõ luật audit, lịch sử, khóa ngoại và transaction.

## 14. Transaction, @Version và entity identity

Dù chọn inheritance strategy nào, JPA vẫn quản lý trạng thái của **một entity object** trong persistence context. Một CardPayment không trở thành hai entity chỉ vì JOINED dùng hai bảng.

### 14.1. Persist một instance, transaction ghi nhiều bảng nếu cần

~~~java
EntityTransaction tx = em.getTransaction();
try {
    tx.begin();

    Payment payment = new CardPayment(
        new BigDecimal("150000.00"),
        Instant.now(),
        "1234"
    );

    em.persist(payment);
    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
~~~

Với resource-local EntityManager, **commit** kết thúc transaction. Với JTA/container, transaction do manager điều phối. Số lượng câu SQL phụ thuộc strategy, nhưng các thao tác ghi của một Payment cần nằm trong transaction thích hợp để giữ nhất quán.

### 14.2. Một ID và một persistence identity

Trong JOINED:

~~~text
payments.id = 101
card_payments.payment_id = 101
~~~

đó vẫn là **CardPayment id=101**, không phải Payment id=101 và CardPayment id=101 độc lập. Không tạo repository riêng để persist “hai nửa” của cùng object bằng hai EntityManager khác nhau.

Trong SINGLE_TABLE, một row tương ứng một entity. Trong TABLE_PER_CLASS, mỗi row subtype là một entity nhưng hierarchy chung làm việc định danh/query polymorphic cần thiết kế rõ.

### 14.3. @Version trong hierarchy

Root có thể khai báo:

~~~java
@Version
private Long version;
~~~

Các subtype kế thừa version mapping. Provider dùng version để phát hiện cập nhật đồng thời xung đột theo semantics optimistic locking:

~~~sql
UPDATE payments
SET amount = ?, version = ?
WHERE id = ? AND version = ?;
~~~

Ví dụ SQL thuộc trường hợp version nằm ở bảng root. Với SINGLE_TABLE, version nằm bảng chung; với JOINED, phần inherited version thường nằm root; với TABLE_PER_CLASS, cột version lặp trong các bảng concrete.

Không đặt mỗi subclass một @Version riêng cho cùng một entity hierarchy như thể đó là những entity không liên quan. Và **@Version không tự bảo vệ bất biến nhiều hàng** hoặc những bulk SQL/native SQL nằm ngoài optimistic locking của entity provider.

### 14.4. Dirty checking vẫn hoạt động theo concrete type

~~~java
CardPayment card = em.find(CardPayment.class, id);
card.changeSomeBusinessField(...);
~~~

Nếu CardPayment đang managed trong transaction, provider nhận biết sự thay đổi và phát UPDATE theo mapping. Ví dụ class ở trên cố tình chưa expose setter cho lastFourDigits; cần cung cấp một domain method nếu field được phép sửa.

Trong JOINED, thay field inherited **amount** thường cập nhật bảng root; thay field subtype **lastFourDigits** thường cập nhật bảng con. Trong SINGLE_TABLE, cả hai cùng nằm bảng chung. Trong TABLE_PER_CLASS, cả hai thuộc bảng concrete.

### 14.5. Bulk updates có thể bỏ qua vòng đời entity

~~~java
em.createQuery(
    "update CardPayment c set c.someAttribute = :value"
).executeUpdate();
~~~

Đây là dạng minh họa (cần thuộc tính thực tế và parameter tương ứng). JPQL bulk DML không giống dirty checking từng entity, có thể không đồng bộ các managed instances đã load và có quy tắc xử lý version/callback khác. Khi cần bulk update, phải cân nhắc clear/refresh, transaction boundary, concurrency và inheritance strategy. SQL UPDATE subtype trong JOINED/TABLE_PER_CLASS còn có thêm giới hạn về khả năng cập nhật nhiều bảng của dialect/provider.

Không xem các field read-only trong mapping hay callback JPA là cơ chế bảo vệ khỏi mọi SQL bên ngoài ứng dụng.

## 15. Những cơ chế giống kế thừa nhưng phục vụ mục đích khác

### 15.1. @Embedded là composition, không phải subtype

Giả sử Payment có địa chỉ người thanh toán:

~~~java
@Embeddable
public class BillingAddress {
    private String street;
    private String city;

    protected BillingAddress() { }
}

@Entity
public class CardPayment extends Payment {
    @Embedded
    private BillingAddress billingAddress;
}
~~~

**BillingAddress** là value object **nằm trong** CardPayment. Nó không phải một subclass của Payment, không có entity ID riêng và không thể **em.find(BillingAddress.class, id)**.

Trong schema SINGLE_TABLE, các cột address có thể nằm trong bảng payments. Với JOINED, field được khai báo ở subtype có thể nằm trong bảng card_payments. Với TABLE_PER_CLASS, field nằm trong bảng concrete. Đây là hai trục khác nhau:

- **Inheritance:** CardPayment **là một loại** Payment.
- **Composition:** CardPayment **có** một BillingAddress.

Một thiết kế có thể dùng cả inheritance và composition, nhưng nên chọn đúng quan hệ nghiệp vụ thay vì ép toàn bộ mô hình thành cây class.

### 15.2. @SecondaryTable là chia cột của một entity, không phải tạo subtype

Giả sử Customer có nhiều trường ít truy cập và muốn tách thành bảng phụ mà không có các subclass:

~~~java
@Entity
@Table(name = "customers")
@SecondaryTable(
    name = "customer_details",
    pkJoinColumns = @PrimaryKeyJoinColumn(name = "customer_id")
)
public class Customer {
    @Id
    private Long id;

    @Column(name = "display_name")
    private String displayName;

    @Column(table = "customer_details", name = "description")
    private String description;
}
~~~

Đây vẫn là **một Customer entity**; bảng phụ chứa các thuộc tính của cùng một entity, không có cột type để phân biệt subclass. JOINED inheritance cũng dùng bảng root và các bảng mở rộng, nhưng **mỗi bảng con biểu diễn một Java subtype**, còn @SecondaryTable chỉ mở rộng thông tin của entity đó.

Nếu các subclass khác nhau chỉ vì cần tách dữ liệu “hiếm dùng” về mặt vật lý, không có hành vi is-a thực, **@SecondaryTable** hoặc composition có thể hợp lý hơn inheritance.

### 15.3. Nhiều class cùng kế thừa một Java class không nhất thiết là một hierarchy JPA

Hai entity đều có:

~~~java
public class CardPayment extends CommonFields { }
public class BankTransferPayment extends CommonFields { }
~~~

nếu **CommonFields** không phải @Entity và cũng không được khai báo metadata JPA phù hợp, không có query Payment chung chỉ vì code giống nhau. Nếu CommonFields là **@MappedSuperclass**, mapping inherited fields được tái sử dụng, nhưng class ấy vẫn không là entity root.

Khi muốn query chung nhiều loại, cần thực sự cân nhắc một **@Entity root** thay vì dựa vào tên hoặc hình thức cây Java.

### 15.4. Dùng class inheritance không thay thế phân quyền

Có thể dùng subclass **AdminUser extends User**, nhưng quyền admin thay đổi theo thời gian thường là **role/permission assignment**, không phải một lần chuyển concrete Java class của một hàng dữ liệu. Nếu một người dùng có thể được cấp hoặc gỡ nhiều role, mô hình association **UserRole** có thể phù hợp hơn entity inheritance. Đây là ví dụ quan trọng về quyết định **model theo domain**, không theo sự thuận tiện của annotation.

## 16. Kế thừa field, association và access type

### 16.1. Inherited basic fields được quản lý như thuộc tính entity

Trong entity inheritance, các field được khai báo ở Payment vẫn thuộc state của CardPayment:

~~~java
Payment p = em.find(Payment.class, id);
System.out.println(p.getAmount());
~~~

**amount** không trở thành một entity con hay association. Cách đặt cột amount do inheritance strategy quy định, nhưng ở Java đó vẫn là basic property được kế thừa.

### 16.2. Association định nghĩa ở root được kế thừa

Ví dụ mỗi Payment liên quan tới một Order:

~~~java
@Entity
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class Payment {
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    // ...
}
~~~

Association này áp dụng cho các subtype. Với JOINED, cột **order_id** thường thuộc root payments; với SINGLE_TABLE thuộc bảng chung; với TABLE_PER_CLASS được đưa vào mỗi bảng concrete theo mapping.

Ràng buộc FK ở database phải theo đúng **bảng thực tế chứa cột**, không theo class Java có chứa field trong source code.

### 16.3. AttributeOverride và AssociationOverride

Nếu subclass hoặc concrete entity cần đổi mapping inherited property trong trường hợp mà JPA cho phép, có thể dùng **@AttributeOverride** cho basic attribute, **@AssociationOverride** cho association mapping.

Ví dụ với @MappedSuperclass:

~~~java
@MappedSuperclass
public abstract class LegacyBase {
    @Column(name = "reference_code")
    private String referenceCode;
}
~~~

~~~java
@Entity
@Table(name = "external_documents")
@AttributeOverride(
    name = "referenceCode",
    column = @Column(name = "external_ref", length = 64)
)
public class ExternalDocument extends LegacyBase {
    // ...
}
~~~

Đừng sử dụng override để ép hai subtype trong SINGLE_TABLE có **hai cột khác nhau cho cùng một inherited field** khi chúng được định nghĩa là **một property persistence chung** của hierarchy; schema và semantics phải được xem xét theo strategy. Override giúp điều chỉnh mapping trong những tình huống được hỗ trợ, không thay đổi quy tắc cơ bản của một entity hierarchy.

### 16.4. Field access và property access

~~~java
@Id
private Long id;
~~~

thường dẫn đến **field access**. Nếu annotation @Id nằm trên getter, JPA thường dùng **property access**. Khi kế thừa giữa các class, cần nhất quán kiểu access hoặc dùng **@Access(AccessType.FIELD/PROPERTY)** rõ ràng.

Trộn annotation trên field ở superclass rồi getter ở subclass một cách tùy tiện có thể khiến thuộc tính bị bỏ qua, ánh xạ trùng hoặc có tên property không như mong đợi. Với @MappedSuperclass, field được kế thừa vẫn tuân theo access strategy đã chọn.

### 16.5. Constructor và khả năng mở rộng class

Entity JPA cần constructor không tham số public/protected theo quy tắc của JPA. Subclass cần gọi được constructor superclass thích hợp. Vì provider có thể sử dụng proxy/enhancement để hỗ trợ lazy loading, không nên mặc định thiết kế entity class final, method final và record theo cách thuần Java mà bỏ qua giới hạn của JPA provider đang dùng.

Các ví dụ Java thuần ở phần 1 dùng final fields/class để minh họa value semantics; khi chuyển sang entity, đã đổi sang **protected no-arg constructor** và field có thể được provider quản lý. Đây là một khác biệt giữa “class Java có thể kế thừa” và “class được một ORM quản lý” cần chủ động chấp nhận.

## 17. equals, hashCode, proxy và subtype identity

### 17.1. Entity equality khác value-object equality

Hai object CardPayment trong Java có thể cùng **amount**, nhưng không vì thế là cùng một Payment. Entity được phân biệt bằng **identity**, thường là primary key và ngữ cảnh kiểu entity, không chỉ bằng giá trị field nghiệp vụ.

Không dùng Lombok **@Data** trực tiếp lên entity hierarchy để tự động đưa mọi field và association vào equals/hashCode, vì:

- Có thể gây vòng đệ quy qua quan hệ hai chiều.
- Có thể vô tình tải lazy association.
- Field mutable đổi làm hashCode đổi khi object đang trong HashSet.
- ID được sinh sau persist có thể đổi từ null thành số thật.
- Cách so sánh class thực tế có thể gặp proxy do provider.

### 17.2. Có nên dùng getClass hay instanceof?

Với một inheritance hierarchy thực, nếu so sánh **CardPayment** và **BankTransferPayment** theo ID, cần ngữ nghĩa nhất quán giữa subtype, root và proxy. Dùng **instanceof Payment** có thể cho phép so sánh hai subtype có cùng id dù chúng khác loại; dùng **getClass()** tuyệt đối có thể gặp khác biệt do proxy.

Không có một template equals/hashCode phù hợp mọi provider và mọi ID strategy. Quy tắc thực dụng:

- Xác định identity từ domain và database.
- Không đưa collection/association mutable vào equality.
- Với ID generated, không phụ thuộc hashCode thay đổi sau persist.
- Thử nghiệm với proxy, detached object và nhiều persistence context.
- Không dùng equality làm thay thế unique constraint trong DB.

### 17.3. Same row, same persistence context

JPA identity map đảm bảo một managed entity có database identity tương ứng được quản lý nhất quán trong cùng persistence context. Với JOINED, root và subclass rows thuộc **một entity**, nên không được hiểu là hai instances độc lập. Một query root và query concrete subtype có thể cùng hướng về đối tượng managed đó theo provider và entity identity.

Khi làm việc với hai EntityManager khác nhau, hai Java references có thể đại diện cùng row DB nhưng không dùng **==** để suy ra đó là cùng object. Vấn đề này độc lập với chiến lược lưu bảng.

## 18. Hiệu năng: một hierarchy không đồng nghĩa một SQL plan

### 18.1. Polymorphic query có chi phí khác nhau

Một màn hình báo cáo “100 Payment mới nhất”:

~~~java
List<Payment> recent = em.createQuery(
    """
    select p
    from Payment p
    where p.createdAt >= :from
    order by p.createdAt desc, p.id desc
    """,
    Payment.class
)
.setParameter("from", fromInstant)
.setMaxResults(100)
.getResultList();
~~~

Với SINGLE_TABLE, DB có thể lọc **payments.created_at** trên một bảng. Với JOINED, provider có thể cần đọc thêm bảng subtype để biết concrete type/field. Với TABLE_PER_CLASS, có thể phải hợp nhất nhiều concrete tables trước khi sắp xếp và giới hạn 100 bản ghi.

Điều này không có nghĩa SINGLE_TABLE chắc chắn nhanh hơn mọi trường hợp. Một query chỉ đọc các CardPayment với field đặc thù và index tốt trên card_payments có thể có kết quả khác.

### 18.2. Index phải phù hợp kiểu query

SINGLE_TABLE:

~~~sql
CREATE INDEX idx_payments_kind_created
    ON payments(payment_kind, created_at);
~~~

JOINED:

~~~sql
CREATE INDEX idx_payments_created
    ON payments(created_at);

-- PK ở card_payments.payment_id đã được index theo cách DB triển khai PK.
~~~

TABLE_PER_CLASS:

~~~sql
CREATE INDEX idx_card_payments_created
    ON card_payments(created_at);

CREATE INDEX idx_transfer_payments_created
    ON bank_transfer_payments(created_at);
~~~

Không thêm tất cả các index trên mọi bảng theo công thức cố định. Dùng thống kê DB, **EXPLAIN/EXPLAIN ANALYZE** khi phù hợp, hiểu chiều phân bố dữ liệu và selectivity. Index hỗ trợ đọc nhưng làm tăng chi phí INSERT/UPDATE và lưu trữ.

### 18.3. N+1 từ association không biến mất vì inheritance

Nếu Payment có association tới Order hoặc Customer:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;
~~~

thì duyệt nhiều Payment và truy cập **payment.getCustomer().getName()** có thể gây N+1, bất kể SINGLE_TABLE, JOINED hay TABLE_PER_CLASS.

Dùng projection, join fetch/entity graph có kiểm soát, batch fetching theo provider, hoặc viết query phục vụ use case. Đừng dùng inheritance strategy để giải quyết lỗi fetch plan và đừng dùng fetch EAGER cho mọi association để “né” lazy loading.

### 18.4. Cache và đối tượng đa hình

Một hierarchy có thể được cache ở mức entity/persistence context. Với SINGLE_TABLE, discriminator cùng dữ liệu hàng giúp xác định subtype; với JOINED/TABLE_PER_CLASS, provider quản lý metadata nhiều bảng. Cache cấp 2 và cách invalidation phụ thuộc cấu hình provider, đặc biệt khi database còn bị cập nhật từ native SQL/batch job.

Không suy từ “chung superclass” rằng mọi subtype phải có cùng chính sách cache hoặc rằng cache sẽ tự đồng bộ nếu một ứng dụng khác sửa bảng.

### 18.5. Khi nào tránh inheritance vì hiệu năng và độ phức tạp?

Nếu có hàng chục loại sự kiện rất khác nhau, mỗi loại có hàng chục field riêng và nhu cầu query chung chỉ để hiển thị một dòng log, có thể dùng:

- Một entity **EventRecord** chung với các cột metadata chuẩn + payload phù hợp;
- Một entity root với các loại được quản lý theo enum/type và composition;
- Các bảng entity độc lập cùng một service/query read model;
- Một hierarchy JPA nếu đa hình và ràng buộc vẫn thật sự đáng giá.

Không nên mặc định rằng một cây class 100 subclass là cách tốt nhất để biểu diễn 100 biến thể dữ liệu cần phân tích thống kê.

## 19. Migration khi thay đổi chiến lược lưu trữ

Chuyển chiến lược JPA trên ứng dụng có dữ liệu production **không phải chỉ đổi một enum**. Schema, ID, FK, dữ liệu và query cũ đều phải được di chuyển có kế hoạch.

### 19.1. SINGLE_TABLE sang JOINED

Ban đầu:

~~~text
payments(
  id, payment_kind, amount, created_at,
  last_four_digits, bank_reference
)
~~~

Mục tiêu:

~~~text
payments(id, amount, created_at)
card_payments(payment_id, last_four_digits)
bank_transfer_payments(payment_id, bank_reference)
~~~

Các công việc cần thiết:

1. Tạo bảng subtype và constraint FK/PK phù hợp.
2. Backfill các row subtype từ bảng payments dựa trên payment_kind.
3. Đối chiếu counts, IDs, NULL/invalid states và toàn vẹn từng subtype.
4. Chuyển code mới sang **@Inheritance(JOINED)** và cập nhật query/DAO phụ thuộc cột cũ.
5. Điều phối việc hai phiên bản ứng dụng có thể chạy đồng thời trong giai đoạn rollout.
6. Chỉ xóa các cột subtype cũ khỏi payments sau khi không còn đường ghi/đọc cũ.
7. Kiểm tra hiệu năng query polymorphic sau khi dữ liệu được phân tách.

Backfill minh họa:

~~~sql
INSERT INTO card_payments (payment_id, last_four_digits)
SELECT id, last_four_digits
FROM payments
WHERE payment_kind = 'CARD';

INSERT INTO bank_transfer_payments (payment_id, bank_reference)
SELECT id, bank_reference
FROM payments
WHERE payment_kind = 'TRANSFER';
~~~

Đây chỉ là hai bước minh họa: cần xử lý row có dữ liệu null, trùng ID, các subtype khác, và vấn đề nhất quán nếu ứng dụng vẫn ghi trong khi backfill. Không chạy nguyên xi trên production nếu chưa có phương án khóa/dual-write/cutover, backup và test tương thích.

### 19.2. JOINED sang SINGLE_TABLE

Chiều ngược lại yêu cầu:

- Thêm discriminator và các cột subtype vào bảng root.
- Backfill từ bảng con bằng JOIN theo root ID.
- Thiết lập CHECK dựa trên discriminator để bảo vệ subtype-specific invariants.
- Thay đổi entity mapping và query.
- Sau khi cutover an toàn, mới loại bỏ các bảng subtype cũ.

Khi hai subtype dùng cột cùng tên nhưng **ý nghĩa hoặc kiểu dữ liệu khác**, không nên tự động gộp vào một cột mà chưa thiết kế ngữ nghĩa chung. Cột **reference** của Transfer có thể khác với reference của Card; tên giống nhau không làm chúng trở thành cùng một property.

### 19.3. TABLE_PER_CLASS sang JOINED

Cần tạo root payments và phân bổ/copy toàn bộ các ID. Nếu hai bảng concrete có cùng ID, phải giải quyết va chạm **trước** khi thiết lập root PK; những FK hoặc API đã lưu ID cũ có thể cần bản đồ chuyển đổi. Đây là ví dụ tại sao **ID generation** phải được xem xét ngay khi chọn TABLE_PER_CLASS.

### 19.4. Đổi @MappedSuperclass thành @Entity không phải thay annotation đơn giản

Nếu Customer và Product cùng extends BaseRecord, sau đó đổi:

~~~java
@MappedSuperclass
abstract class BaseRecord { ... }
~~~

thành:

~~~java
@Entity
abstract class BaseRecord { ... }
~~~

bạn đã thay đổi **persistence model**, không chỉ thêm khả năng query. JPA giờ coi Customer và Product thuộc một entity hierarchy, và áp dụng inheritance strategy. Schema, ID, association và truy vấn có thể thay đổi rất lớn. Nếu Customer và Product không phải cùng domain entity type, không nên làm vậy chỉ để tạo repository BaseRecord chung.

### 19.5. Rename class và discriminator

Khi dùng SINGLE_TABLE, cần ổn định **@DiscriminatorValue**:

~~~java
@DiscriminatorValue("CARD")
public class CardPayment extends Payment { ... }
~~~

Nếu đổi class thành **CreditCardPayment** nhưng giữ discriminator CARD, dữ liệu cũ có thể tiếp tục dùng mapping mới sau migration/test phù hợp. Nếu discriminator dựa vào tên class mặc định, việc rename dễ làm dữ liệu có giá trị discriminator cũ không còn match.

Nên coi các discriminator code đã lưu như một phần **hợp đồng dữ liệu**, có migration khi đổi, không chỉ là nhãn hiển thị.

### 19.6. Migration và nhiều phiên bản ứng dụng cùng chạy

Khi rolling deployment, app cũ và mới có thể tạm thời dùng mapping khác nhau. Ví dụ app cũ ghi card field vào payments, app mới ghi vào card_payments. Chỉ thêm bảng con chưa đồng nghĩa cả hai nguồn ghi đồng bộ.

Một kế hoạch **expand → backfill → cutover → contract** cần xác định:
- ai là nguồn ghi chính tại từng giai đoạn;
- có cần tạm dừng write hoặc dual-write đáng tin cậy không;
- xử lý replay/backfill liên tục như thế nào;
- khi nào an toàn đổi đọc sang schema mới;
- thời điểm xóa cột/bảng cũ;
- cách rollback deployment mà không làm mất dữ liệu.

Không dùng **hibernate.hbm2ddl.auto=create** trên dữ liệu cần giữ. Quản lý schema bằng migration có kiểm soát và xác minh bằng integration tests trên loại DB thật.

## 20. Chọn kế thừa hay các thiết kế khác?

### 20.1. Ví dụ Product–DigitalProduct–PhysicalProduct

Có thể có:

~~~text
Product
 ├── DigitalProduct(downloadUrl, licenseKeyPolicy)
 └── PhysicalProduct(weight, dimensions)
~~~

Nếu tất cả Product đều có SKU, name, price và hệ thống tìm kiếm thường hiển thị cùng một catalog, entity inheritance có thể hợp lý.

Nhưng nếu PhysicalProduct lại có inventory, shipping, batch và DigitalProduct có licensing, fulfillment riêng biệt, cần xem:
- Bao nhiêu field chung?
- Query chung hay query riêng thường xuyên hơn?
- Các subtype có cùng identity, lifecycle, owner và retention?
- Có Product FK chung từ OrderLine?
- Có cần chuyển một Product từ digital sang physical khi kinh doanh thay đổi không?

Nếu “digital/physical” là một **thuộc tính có thể thay đổi** thay vì một kiểu entity cố định, có thể dùng một Product entity với component hoặc association tới thông tin fulfillment phù hợp, tránh khó khăn khi phải “chuyển concrete Java class” của entity.

### 20.2. Ví dụ AuditRecord–LoginEvent–PaymentEvent

Nếu hệ thống chỉ cần đọc tất cả event theo thời gian và subtype có metadata rất khác, SINGLE_TABLE có thể trở nên cực rộng. Một bảng log chuẩn có **eventType, occurredAt, actorId, payload** cũng là lựa chọn; query thống kê subtype-specific có thể sử dụng bảng chuyên biệt. Không có mặc định inheritance tốt nhất cho hệ thống event lớn.

### 20.3. Ví dụ nhân sự PermanentEmployee/Contractor

Nếu PermanentEmployee và Contractor có cùng employment identity và nhiều quy trình chung, hierarchy có thể phù hợp. Nhưng nếu một người chuyển từ contractor sang permanent mà vẫn giữ hồ sơ, lịch sử, quyền truy cập, việc đổi Java subtype/row strategy không tự thực hiện quy trình chuyển đổi đó.

Một mô hình **Employee** với **EmploymentContract** hoặc lịch sử **ContractAssignment** thường diễn đạt chuyển trạng thái theo thời gian tốt hơn. Chọn class inheritance khi đó thực sự là phân loại bản chất ổn định, không chỉ trạng thái nghiệp vụ tạm thời.

### 20.4. Decision matrix theo câu hỏi nghiệp vụ

| Câu hỏi | Nếu “có” | Gợi ý |
|---|---|---|
| Các class chỉ dùng chung id/timestamp? | Có | @MappedSuperclass |
| Các class thực sự is-a cùng một entity type? | Có | Cân nhắc @Entity inheritance |
| Query root polymorphic thường xuyên? | Có | SINGLE_TABLE hoặc JOINED thường phù hợp hơn TABLE_PER_CLASS |
| Nhiều FK trỏ root type? | Có | Ưu tiên chiến lược có bảng root chung |
| Subtype có nhiều field bắt buộc riêng? | Có | JOINED hoặc TABLE_PER_CLASS có lợi về NOT NULL |
| Concrete subtype gần như độc lập? | Có | TABLE_PER_CLASS hoặc entity độc lập |
| Một biến thể có thể thay đổi trong lifecycle? | Có | Cân nhắc composition/state thay vì subtype |
| Chỉ cần chứa value object có cấu trúc? | Có | @Embedded, không phải inheritance |
| Muốn tách cột phụ nhưng không có subtype? | Có | @SecondaryTable hoặc mô hình khác |
| Cần một ID chung xuyên mọi subtype? | Có | SINGLE_TABLE/JOINED thuận tiện hơn |

## 21. Lỗi phổ biến khi làm việc với inheritance mapping

| Dấu hiệu | Nguyên nhân thường gặp | Hướng giải quyết |
|---|---|---|
| Query root trả lỗi “not an entity” | Superclass chỉ là @MappedSuperclass | Dùng @Entity hierarchy hoặc query từng concrete entity |
| Bảng chung có rất nhiều NULL | SINGLE_TABLE với subtype-specific fields | Dùng CHECK phù hợp hoặc cân nhắc JOINED |
| Subclass insert lỗi NOT NULL ở field subtype khác | SINGLE_TABLE có NOT NULL vô điều kiện | Đổi DDL, dùng conditional CHECK |
| JOINED query chậm | JOIN nhiều subtype/root, index thiếu | Xem SQL plan, projection, index, cân nhắc chiến lược |
| TABLE_PER_CLASS query root phức tạp | Phải hợp nhất các concrete tables | Query subtype khi có thể hoặc đổi strategy |
| Cannot resolve discriminator value | Dữ liệu type cũ không match mapping | Migration discriminator, ổn định @DiscriminatorValue |
| @ManyToOne BaseRecord không hợp lệ | BaseRecord là @MappedSuperclass | Target phải là @Entity |
| FK Order.payment_id không tạo được với TABLE_PER_CLASS | Không có bảng root chung | Thiết kế lại association/schema/strategy |
| Cùng ID ở nhiều concrete tables | ID generator độc lập trong TABLE_PER_CLASS | Dùng strategy ID chung và migrate collision |
| Update “payment kind” không đổi Java subtype | Discriminator không phải business setter | Tạo entity mới hoặc mô hình trạng thái khác |
| Lombok equals/toString đệ quy | Auto include inherited fields/associations | Cài equality/toString có chủ đích |
| Mapping bị trùng cột | Override/hierarchy metadata sai | Kiểm tra access type, @AttributeOverride và bảng thực |
| Entity class final gây vấn đề lazy proxy | Proxy/enhancement có giới hạn | Tuân theo yêu cầu của provider/JPA |
| Dữ liệu cũ mất sau đổi annotation | Đổi inheritance strategy không migration | Expand/backfill/cutover/contract |
| Unique ở subtype nhưng vẫn trùng xuyên hierarchy | TABLE_PER_CLASS chỉ unique từng bảng | Registry/constraint chung hoặc đổi chiến lược |
| N+1 khi duyệt subtype associations | Fetch plan không phù hợp | Join fetch, projection, batching |
| Một row root JOINED không có subtype hợp lệ | SQL ngoài ORM ghi sai/incomplete | Constraint, giao dịch, kiểm soát đường ghi |
| Query API trả field không phù hợp subtype | Đọc entity trực tiếp thay vì DTO | DTO/type-specific projection |
| Schema thật khác annotations | Migration chưa áp dụng | Kiểm tra metadata DB, script và deployment |
| Tự dùng class name làm type DB | Rename class thay discriminator | Dùng code discriminator ổn định |

### 21.1. Khi lỗi xuất hiện ở đâu?

Lỗi mapping/metadata có thể xuất hiện lúc bootstrap EntityManagerFactory. Lỗi SQL constraint có thể xuất hiện khi provider gửi statement ở flush hoặc khi transaction commit, tùy thời điểm DB kiểm tra constraint. Một service chỉ gọi **persist** chưa chứng minh dữ liệu đã được commit thành công.

Khi chẩn đoán, bắt đầu từ:
1. JPA root và subclass annotations;
2. entity classes được persistence unit quản lý;
3. SQL/schema thực tế;
4. discriminator và ID generator;
5. transaction/flush timing;
6. query plan và ràng buộc DB.

Không “sửa” bằng cách bật tự tạo schema phá dữ liệu.

## 22. Bài tập thực hành

### Bài 1. Phân biệt hai kiểu kế thừa

Cho:

~~~java
@MappedSuperclass
abstract class AuditedRecord {
    @Id Long id;
    Instant createdAt;
}

@Entity
class Customer extends AuditedRecord { }

@Entity
class Product extends AuditedRecord { }
~~~

**Câu hỏi:**
1. Có bảng AuditedRecord không?
2. Query **select a from AuditedRecord a** có hợp lệ như entity root không?
3. Java có thể giữ Customer trong biến AuditedRecord không?
4. @ManyToOne AuditedRecord có phải target entity hợp lệ không?

**Gợi ý:** Java cho phép tham chiếu superclass; JPA chỉ áp dụng metadata kế thừa vào bảng Customer/Product. AuditedRecord không phải managed entity root và không hỗ trợ JPQL/association polymorphic trực tiếp.

### Bài 2. Dự đoán bảng khi dùng SINGLE_TABLE

Cho:

~~~java
@Entity
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(name = "asset_type")
abstract class Asset {
    @Id Long id;
    String code;
}

@Entity
@DiscriminatorValue("BOOK")
class Book extends Asset {
    String isbn;
}

@Entity
@DiscriminatorValue("DEVICE")
class Device extends Asset {
    String serialNo;
}
~~~

Vẽ bảng SQL gồm **id, asset_type, code, isbn, serial_no** và hai hàng thuộc BOOK/DEVICE. Vì sao không thể đặt **isbn NOT NULL** vô điều kiện cho mọi hàng? Hãy đề xuất CHECK theo asset_type.

### Bài 3. Dự đoán SQL cho JOINED

Với:

~~~text
Asset(id, code)
  ├── Book(isbn)
  └── Device(serialNo)
~~~

và JOINED, hãy vẽ ba bảng, nêu PK/FK, và hai INSERT cần thiết khi persist Book. Giải thích tại sao root Asset và Book không trở thành hai entity Java độc lập.

### Bài 4. Query đa hình với TABLE_PER_CLASS

Bạn có ba concrete subtype cùng kế thừa Payment:

~~~text
CardPayment
BankTransferPayment
CashPayment
~~~

Hãy giải thích:
1. Query **select p from Payment p** cần đọc bảng nào?
2. Vì sao provider có thể phải dùng UNION?
3. Vì sao **@ManyToOne Payment** có thể khó bảo đảm FK ở DB?
4. Một sequence chung có lợi thế gì so với IDENTITY độc lập mỗi bảng?

### Bài 5. Đổi subtype trong vòng đời

Hệ thống dùng CardPayment và BankTransferPayment subclasses. Khi khách đổi phương thức thanh toán, developer muốn:

~~~java
payment.setKind(PaymentKind.TRANSFER);
~~~

Hãy chỉ ra vì sao một enum setter không thể biến runtime class CardPayment thành BankTransferPayment, và phân biệt **payment status** với **entity discriminator**. Đề xuất tạo Payment mới hoặc thiết kế Payment chứa PaymentMethod nếu phương thức cần thay đổi.

### Bài 6. Chọn mapping phù hợp

Ba trường hợp:
- **A:** Customer và Product chỉ chung id, createdAt;
- **B:** CardPayment và BankTransferPayment chung amount, status, thường được thống kê chung, Refund cần FK tới Payment;
- **C:** EventA/EventB rất khác nhau, mỗi loại xử lý ở bảng riêng, hiếm query chung.

Hãy chọn giữa @MappedSuperclass, SINGLE_TABLE, JOINED, TABLE_PER_CLASS hoặc entity độc lập, giải thích bằng query, identity và constraint thay vì chỉ bằng số dòng Java code.

**Định hướng:** A thường @MappedSuperclass; B thường SINGLE_TABLE/JOINED tùy số field riêng; C cần cân nhắc TABLE_PER_CLASS hoặc entities độc lập, không áp đặt một lựa chọn duy nhất.

### Bài 7. Unique constraint xuyên hierarchy

Một businessRef phải duy nhất trên tất cả subtype Payment. Với SINGLE_TABLE, JOINED và TABLE_PER_CLASS, unique sẽ đặt ở đâu? Vì sao unique riêng từng concrete table không bảo đảm không trùng xuyên toàn bộ hierarchy?

### Bài 8. Migration SINGLE_TABLE sang JOINED

Bảng hiện tại:

~~~text
payments(id, payment_kind, amount, last_four_digits, bank_reference)
~~~

Hãy viết kế hoạch:
1. Tạo bảng card_payments và bank_transfer_payments;
2. Backfill row theo discriminator;
3. Kiểm tra lỗi dữ liệu/subtype không xác định;
4. Điều phối đường ghi khi app cũ và mới cùng chạy;
5. Chuyển mapping;
6. Sau khi ổn định mới drop cột cũ.

Nêu nguy cơ nếu chỉ đổi **@Inheritance(SINGLE_TABLE)** thành **JOINED** mà không migration.

### Bài 9. So sánh @Embedded và @Inheritance

Một PurchaseOrder có shippingAddress, billingAddress; không có nhu cầu lưu Address riêng hoặc truy vấn Address bằng ID. Đây có phải là quan hệ **PurchaseOrder extends Address** không? Hãy giải thích vì sao **@Embedded** là mô hình tự nhiên hơn và cách override tên cột khi nhúng Address hai lần.

### Bài 10. Entity equality và proxy

Một hệ thống có CardPayment dùng ID generated sau persist và được thêm vào HashSet trước persist. Developer viết:

~~~java
@Override
public int hashCode() {
    return Objects.hash(id);
}
~~~

Thảo luận nguy cơ khi ID từ null thành số thật sau persist. Vì sao dùng tất cả subclass fields và associations trong equals/hashCode cũng có thể gặp lỗi? Nêu chiến lược thiết kế equality ổn định và kiểm thử cùng JPA proxy đang dùng.

### Bài 11. Polymorphic query và TYPE

Viết JPQL:
- Lấy tất cả Payment có amount lớn hơn 100000;
- Chỉ lấy CardPayment;
- Chỉ lấy Payment có concrete type CardPayment dùng TYPE;
- Chọn những CardPayment có lastFourDigits bằng “1234”.

Giải thích query root khác query subtype thế nào về số lượng loại entity và SQL strategy.

### Bài 12. Thực nghiệm so sánh ba chiến lược

Tạo ba biến thể project JPA độc lập với cùng hierarchy Payment, mỗi biến thể chọn một inheritance strategy. Với mỗi biến thể:

1. Tạo schema phù hợp bằng migration.
2. Persist một CardPayment và một BankTransferPayment.
3. Gọi **flush**, sau đó **clear**, nạp Payment bằng root class.
4. Query tất cả Payment.
5. Quan sát SQL INSERT/SELECT.
6. Xem schema tables, FK và constraints.
7. So sánh query root/subtype và đo EXPLAIN khi có đủ dữ liệu.

Đừng cùng lúc khai báo ba biến thể mapping vào một persistence unit với class/entity name trùng; làm thí nghiệm riêng hoặc đổi tên entity/schema rõ ràng.

## 23. Quy trình lựa chọn mô hình kế thừa

Khi gặp nhiều class Java trông giống nhau, hãy xác định theo trình tự:

1. **Đúng quan hệ domain chưa?** Đây có thực sự là is-a, hay chỉ has-a/composition hoặc các entity tình cờ chung field?
2. **Có cần một root entity không?** Có query mọi subtype, repository polymorphic hoặc FK tới superclass?
3. **Nếu chỉ cần code/mapping chung:** cân nhắc @MappedSuperclass, không tự thêm @Entity.
4. **Nếu cần entity hierarchy:** xác định số subtype, mức độ khác nhau của field và yêu cầu ràng buộc dữ liệu.
5. **Đo trọng tâm query:** root polymorphic thường xuyên hay subtype-specific chiếm đa số?
6. **Kiểm tra FK:** entity khác có cần tham chiếu một Payment bất kể subtype không?
7. **Thiết kế ID:** một namespace chung hay các bảng độc lập? IDENTITY/sequence/UUID có tương thích strategy không?
8. **Thiết kế constraint:** NOT NULL cho subtype, UNIQUE trên root, CHECK discriminator, FK và các bất biến xuyên hàng.
9. **Chọn strategy:** SINGLE_TABLE cho polymorphism truy cập đơn giản; JOINED cho subtype constraints và root FK; TABLE_PER_CLASS khi concrete tables độc lập và root query ít.
10. **Đảm bảo Java object lifecycle:** constructor, access type, proxy, equals/hashCode, transaction, version, lazy fetch.
11. **Lập migration:** schema thực tế phải tương thích mapping và dữ liệu hiện hữu, không chỉ thêm annotation.
12. **Kiểm chứng bằng integration test:** persist, flush/clear, query root/subtype, FK, constraints và SQL plan.

Một bảng ghi nhớ nhanh:

~~~text
Java extends
    → quan hệ giữa kiểu Java; không tự xác định table.

@MappedSuperclass
    → tái sử dụng metadata; superclass không phải entity.

@Entity + @Inheritance(SINGLE_TABLE)
    → một bảng, discriminator, query polymorphic đơn giản,
      subtype-specific constraint cần lưu ý.

@Entity + @Inheritance(JOINED)
    → bảng root + bảng subtype, chung PK,
      query thường có JOIN, FK tới root rõ ràng.

@Entity + @Inheritance(TABLE_PER_CLASS)
    → mỗi concrete entity một bảng,
      polymorphic query thường UNION,
      ID chung và FK tới root cần cân nhắc.

@Embedded
    → object giá trị nằm trong owner, không phải subclass.

@SecondaryTable
    → một entity trải cột qua nhiều bảng, không phải inheritance.
~~~

**Kết luận:** **kế thừa Java** giải quyết quan hệ kiểu và đa hình trong chương trình, còn **kế thừa lưu trữ** là quyết định ánh xạ giữa một entity hierarchy và các bảng quan hệ. **@MappedSuperclass** chỉ dùng chung mapping; **@Entity/@Inheritance** tạo một hệ thống entity có thể truy vấn đa hình. SINGLE_TABLE, JOINED và TABLE_PER_CLASS đem lại những lựa chọn khác nhau về số bảng, constraint, FK, ID, SQL và chi phí vận hành. Chọn đúng cần xuất phát từ **ngữ nghĩa domain, cách truy vấn dữ liệu và tính toàn vẹn database**, rồi mới tối ưu sự tiện lợi của Java code.



