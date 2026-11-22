# Biểu thức theo kiểu, truy vấn đa hình và xử lý kiểu con

## 1. Đặt vấn đề: một truy vấn cần làm việc với nhiều loại entity

Trong ứng dụng thực tế, một khái niệm nghiệp vụ có thể có nhiều kiểu chuyên biệt. Ví dụ hệ thống thanh toán hỗ trợ thẻ, ví điện tử và chuyển khoản:

```text
                    Payment
                   /   |   \
                  /    |    \
                 v     v     v
          CardPayment WalletPayment BankTransferPayment
```

Mọi thanh toán có mã định danh, số tiền, trạng thái và thời điểm tạo. Nhưng thanh toán thẻ có `lastFour` và `issuer`; ví điện tử có `walletProvider`; chuyển khoản có `bankReference`.

Những câu hỏi HQL thường xuất hiện:

- Liệt kê **tất cả** thanh toán, bất kể loại cụ thể.
- Chỉ lấy thanh toán thẻ mà không mất khả năng truy vấn các trường chung.
- Lọc những hàng có **kiểu entity cụ thể** là CardPayment hoặc WalletPayment.
- Dùng thuộc tính riêng như `issuer` trong một query bắt đầu từ lớp cha Payment.
- Truy vấn một association tới Payment nhưng chỉ join trường hợp đối tượng đích là CardPayment.
- Tạo báo cáo kết hợp thông tin chung và thông tin chuyên biệt mà không tải mọi entity vào bộ nhớ rồi gọi `instanceof`.

Hibernate Query Language (**HQL**) có những công cụ phù hợp:

1. **Truy vấn đa hình** (*polymorphic query*) từ một root entity trong hệ phân cấp.
2. **`type()` / `TYPE()`** để xét kiểu entity tại thời điểm truy vấn.
3. **`treat()` / `TREAT()`** để thu hẹp kiểu một biểu thức entity và truy cập thuộc tính riêng của subtype.
4. Các root/association/join được định kiểu rõ, kết hợp `CASE`, projection và Criteria API.

Bài này trình bày cách dùng, giới hạn và sự khác biệt giữa hành vi HQL/Jakarta Persistence với cách database hiện thực qua `SINGLE_TABLE`, `JOINED` hoặc `TABLE_PER_CLASS`.

> Ví dụ chính dùng Java hiện đại, `jakarta.persistence.*` và Hibernate ORM 6.x. HQL là ngôn ngữ của Hibernate; một số ví dụ trùng với JPQL chuẩn, nhưng các tính năng mở rộng và SQL được sinh có thể khác giữa các phiên bản hoặc dialect. Cần dùng tài liệu đúng phiên bản đang chạy khi triển khai thật.

## 2. Trước hết: entity inheritance khác kế thừa Java thuần

Khi một class Java kế thừa class khác, điều đó chưa tự biến cả hai thành entity query root. Hibernate chỉ có thể áp dụng truy vấn đa hình trên **kiểu được ánh xạ vào mô hình entity**.

Giả sử:

```java
@Entity
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
public abstract class Payment {
    @Id
    private Long id;

    private BigDecimal amount;
}

@Entity
public class CardPayment extends Payment {
    private String lastFour;
}
```

`Payment` là một entity root dù `abstract`; `CardPayment` là entity subtype. Truy vấn:

```hql
from Payment p
```

theo ngữ nghĩa đa hình có thể trả các instance thuộc những subtype đã được ánh xạ, như `CardPayment`, `WalletPayment` hay `BankTransferPayment`.

### @MappedSuperclass không phải polymorphic query root

Ví dụ:

```java
@MappedSuperclass
public abstract class AuditedEntity {
    @Column(name = "created_at")
    private Instant createdAt;
}

@Entity
public class Payment extends AuditedEntity {
    // ...
}
```

`AuditedEntity` chỉ đóng góp mapping thuộc tính cho subclass; nó **không phải entity độc lập**. Không thể coi `from AuditedEntity a` là truy vấn entity root chuẩn của Jakarta Persistence.

Với trường hợp nhiều entity cùng implement một interface hoặc kế thừa một class không ánh xạ entity, Hibernate có một số khả năng polymorphism đặc thù theo phiên bản; không nên nhầm chúng với polymorphic query qua một root `@Entity` chuẩn. Nếu cần truy vấn thống nhất, một mapped entity hierarchy thường dễ dự đoán hơn.

## 3. Mô hình xuyên suốt: Payment và các kiểu con

Định nghĩa enum:

```java
package com.example.payments;

public enum PaymentStatus {
    PENDING,
    CONFIRMED,
    FAILED
}
```

Entity root:

```java
package com.example.payments;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;

@Entity
@Table(name = "payments")
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(
    name = "payment_kind",
    discriminatorType = DiscriminatorType.STRING
)
public abstract class Payment {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, precision = 18, scale = 2)
    private BigDecimal amount;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private PaymentStatus status;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected Payment() {}

    protected Payment(BigDecimal amount) {
        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException("Invalid amount");
        }
        this.amount = amount;
        this.status = PaymentStatus.PENDING;
        this.createdAt = Instant.now();
    }

    public Long getId() { return id; }
    public BigDecimal getAmount() { return amount; }
    public PaymentStatus getStatus() { return status; }
    public Instant getCreatedAt() { return createdAt; }
}
```

Thanh toán thẻ:

```java
@Entity
@DiscriminatorValue("CARD")
public class CardPayment extends Payment {

    @Column(name = "card_last_four", length = 4)
    private String lastFour;

    @Column(name = "card_issuer", length = 50)
    private String issuer;

    protected CardPayment() {}

    public CardPayment(
            BigDecimal amount,
            String lastFour,
            String issuer) {
        super(amount);
        this.lastFour = lastFour;
        this.issuer = issuer;
    }

    public String getLastFour() { return lastFour; }
    public String getIssuer() { return issuer; }
}
```

Ví điện tử:

```java
@Entity
@DiscriminatorValue("WALLET")
public class WalletPayment extends Payment {

    @Column(name = "wallet_provider", length = 60)
    private String walletProvider;

    protected WalletPayment() {}

    public WalletPayment(
            BigDecimal amount,
            String walletProvider) {
        super(amount);
        this.walletProvider = walletProvider;
    }

    public String getWalletProvider() { return walletProvider; }
}
```

Chuyển khoản:

```java
@Entity
@DiscriminatorValue("BANK")
public class BankTransferPayment extends Payment {

    @Column(name = "bank_reference", length = 100)
    private String bankReference;

    protected BankTransferPayment() {}

    public BankTransferPayment(
            BigDecimal amount,
            String bankReference) {
        super(amount);
        this.bankReference = bankReference;
    }

    public String getBankReference() { return bankReference; }
}
```

Các subclass ở trên dùng cùng package hoặc có import phù hợp cho `@Entity`, `@DiscriminatorValue`, `@Column` và `BigDecimal`. Đó là các class ví dụ cho nội dung bài, không phải toàn bộ source của một dự án có thể biên dịch chỉ bằng một file.

### Tại sao chỉ lưu lastFour?

Ví dụ thẻ cố ý lưu bốn chữ số cuối, không lưu số thẻ đầy đủ hoặc dữ liệu xác thực nhạy cảm. Mục đích bài là HQL type handling; việc lưu trữ dữ liệu thanh toán thật phải tuân theo chính sách bảo mật và hệ thống thanh toán được dùng.

## 4. Dữ liệu tương ứng khi dùng SINGLE_TABLE

Với `InheritanceType.SINGLE_TABLE`, cả hierarchy có thể nằm trên một bảng. DDL PostgreSQL minh họa:

```sql
CREATE TABLE payments (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    payment_kind VARCHAR(20) NOT NULL,
    amount NUMERIC(18, 2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    card_last_four VARCHAR(4),
    card_issuer VARCHAR(50),
    wallet_provider VARCHAR(60),
    bank_reference VARCHAR(100)
);

CREATE INDEX ix_payments_kind_status_time
    ON payments(payment_kind, status, created_at);
```

Dữ liệu minh họa:

| id | payment_kind | amount | status | card_last_four | wallet_provider | bank_reference |
|---:|---|---:|---|---|---|---|
| 101 | CARD | 250000 | CONFIRMED | 1234 | NULL | NULL |
| 102 | WALLET | 90000 | PENDING | NULL | MOMO | NULL |
| 103 | BANK | 700000 | CONFIRMED | NULL | NULL | TX-456 |
| 104 | CARD | 180000 | FAILED | 5678 | NULL | NULL |

Một hàng có `payment_kind = 'CARD'` tương ứng CardPayment; `'WALLET'` tương ứng WalletPayment; `'BANK'` tương ứng BankTransferPayment.

Khi dùng subclass-specific column trong một bảng chung, các cột như `card_last_four` thường phải cho phép `NULL` ở mức toàn bảng vì những subtype khác không có thuộc tính này. Nếu trường bắt buộc với đúng một subtype, schema có thể dùng CHECK constraint điều kiện theo discriminator, ví dụ:

```sql
ALTER TABLE payments
ADD CONSTRAINT ck_card_last_four
CHECK (
    payment_kind <> 'CARD'
    OR card_last_four IS NOT NULL
);
```

Đây là một trade-off của SINGLE_TABLE; `@Column(nullable = false)` trên field chỉ thuộc subclass không phải lúc nào cũng có thể biểu diễn thành `NOT NULL` toàn bảng một cách đúng đắn.

## 5. Truy vấn đa hình mặc định

HQL:

```hql
from Payment p
```

Ví dụ Java:

```java
List<Payment> payments = session.createQuery(
    "from Payment p order by p.createdAt desc",
    Payment.class
).getResultList();
```

Với mapping ở trên, kết quả có thể chứa đối tượng runtime:

```text
CardPayment#101
WalletPayment#102
BankTransferPayment#103
CardPayment#104
```

**Truy vấn từ entity cha tự mang tính đa hình**: không cần viết một query riêng cho mỗi subtype rồi ghép danh sách thủ công.

### Root abstract vẫn dùng làm query root

`Payment` là abstract class nên không tạo trực tiếp một instance `new Payment()`. Nhưng nó vẫn là `@Entity` hợp lệ, chứa những thuộc tính chung và có thể là root HQL:

```hql
select p.id, p.amount, p.status
from Payment p
where p.amount >= :minimum
order by p.createdAt desc
```

Kết quả query không yêu cầu có một hàng tương ứng đối tượng Payment thuần. Nó có thể đại diện cho bất kỳ concrete subtype nào thuộc hierarchy.

### Query từ subtype

```hql
from CardPayment c
where c.issuer = :issuer
```

Query này xuất phát trực tiếp từ CardPayment, vì vậy HQL cho phép tham chiếu `c.issuer` và `c.lastFour` mà không cần ép kiểu.

Nếu CardPayment có thêm entity subclass được ánh xạ, truy vấn `from CardPayment c` cũng có thể đa hình theo các subtype con của CardPayment. Để lọc **đúng một kiểu concrete duy nhất**, phải hiểu thêm `type()` ở phần sau.

## 6. TYPE(): hỏi kiểu entity thực tế trong truy vấn

Biểu thức `type()` là một công cụ quan trọng trong HQL/JPQL để xét entity type. Ví dụ:

```hql
select p
from Payment p
where type(p) = CardPayment
```

Nghĩa là chỉ lấy những Payment có kiểu entity khớp CardPayment.

Trong hierarchy SINGLE_TABLE đang xét, Hibernate có thể chuyển điều kiện này thành predicate trên discriminator:

```sql
SELECT p.*
FROM payments p
WHERE p.payment_kind = 'CARD';
```

**Đây là SQL minh họa.** HQL `type(p)` mô tả kiểu **entity**, không phải một lệnh bắt buộc phải truy cập một cột vật lý tên `payment_kind`. Với JOINED hoặc TABLE_PER_CLASS, Hibernate có thể dùng join, discriminator hoặc biểu thức SQL khác để nhận diện subtype.

### 6.1. Lọc nhiều kiểu bằng IN

```hql
select p
from Payment p
where type(p) in (CardPayment, WalletPayment)
order by p.createdAt desc
```

Trong ví dụ, query loại bỏ BankTransferPayment và giữ hai loại thẻ/ví.

### 6.2. Kết hợp type với điều kiện trên thuộc tính chung

```hql
select p
from Payment p
where p.status = :status
  and type(p) in (CardPayment, WalletPayment)
  and p.amount >= :minimum
```

Java:

```java
List<Payment> payments = session.createQuery(
    "select p from Payment p " +
    "where p.status = :status " +
    "and type(p) in (CardPayment, WalletPayment) " +
    "and p.amount >= :minimum",
    Payment.class
)
.setParameter("status", PaymentStatus.CONFIRMED)
.setParameter("minimum", new BigDecimal("100000"))
.getResultList();
```

Ở đây `type(p)` quyết định subtype nào được chọn; `status` và `amount` là những thuộc tính chung của Payment.

## 7. Entity type không phải string discriminator

Một lỗi phổ biến:

```hql
where type(p) = 'CARD'
```

Đây là cách nhầm **kiểu entity trong mô hình ORM** với **giá trị discriminator trong schema database**.

Khi viết HQL/JPQL kiểu:

```hql
where type(p) = CardPayment
```

`CardPayment` biểu diễn entity type được ánh xạ. `@DiscriminatorValue("CARD")` là chi tiết mapping giúp Hibernate nhận biết hàng dữ liệu. Không được coi chuỗi `"CARD"` là một thay thế tổng quát cho entity type expression.

### Tham số kiểu entity

Có thể dùng parameter theo ngữ nghĩa entity type, chẳng hạn:

```java
List<Payment> payments = session.createQuery(
    "from Payment p where type(p) = :paymentType",
    Payment.class
)
.setParameter("paymentType", CardPayment.class)
.getResultList();
```

Khả năng bind kiểu entity bằng `Class` và suy luận parameter type cần được kiểm chứng với phiên bản Hibernate/provider đang dùng. Đây là cách biểu đạt có chủ đích khác với nối tên class từ dữ liệu người dùng vào HQL.

Nếu client gửi lựa chọn `CARD`, ứng dụng nên ánh xạ qua allow-list:

```java
Class<? extends Payment> entityType = switch (requestedKind) {
    case CARD -> CardPayment.class;
    case WALLET -> WalletPayment.class;
    case BANK -> BankTransferPayment.class;
};
```

Sau đó bind kiểu entity được phép, thay vì nối input tự do vào cú pháp HQL. Điều này giúp giữ query ổn định và tránh tình huống người dùng chọn class/entity không thuộc phạm vi API.

## 8. TYPE() khi so sánh kiểu chính xác và phân cấp con sâu hơn

Giả sử mở rộng hierarchy:

```text
Payment
  ├── CardPayment
  │      ├── DebitCardPayment
  │      └── CreditCardPayment
  └── WalletPayment
```

Hai truy vấn này không nhất thiết có cùng tập kết quả:

```hql
from CardPayment c
```

và

```hql
from Payment p
where type(p) = CardPayment
```

Root `CardPayment` có thể tham gia truy vấn đa hình và bao gồm các concrete subclass của nó. Trong khi đó `type(p) = CardPayment` là một **phép so sánh kiểu entity**, thường được hiểu là khớp đúng type; DebitCardPayment/CreditCardPayment có entity type riêng.

Nếu mục tiêu là “mọi thanh toán thuộc nhánh CardPayment”, kể cả subclass sâu hơn, **truy vấn từ CardPayment** thường diễn đạt ý định rõ hơn. Nếu muốn tập subtype cụ thể, có thể liệt kê:

```hql
where type(p) in (DebitCardPayment, CreditCardPayment)
```

Đừng đánh đồng `type(p) = SomeClass` với toán tử Java `instanceof SomeClass` ở mọi trường hợp. Java `instanceof` nhận cả subclass; entity type equality là một phép so sánh loại cụ thể trong mô hình query.

## 9. TREAT(): thu hẹp kiểu để truy cập thuộc tính subtype

Giả sử query root là Payment:

```hql
from Payment p
```

Alias `p` được định kiểu Payment; thuộc tính `lastFour` chỉ tồn tại ở CardPayment. Nếu cần đọc thuộc tính ấy mà vẫn bắt đầu từ root Payment, dùng:

```hql
treat(p as CardPayment)
```

Ví dụ:

```hql
select p.id, treat(p as CardPayment).lastFour
from Payment p
where type(p) = CardPayment
```

`treat(p as CardPayment)` cho phép HQL diễn đạt rằng ở vị trí này `p` được nhìn như CardPayment, nên có thể truy cập `lastFour`.

### TREAT khác TYPE

| Công cụ | Hỏi/diễn đạt điều gì? | Ví dụ |
|---|---|---|
| `type(p)` | Kiểu entity của `p` là gì? | `type(p) = CardPayment` |
| `treat(p as CardPayment)` | Nhìn biểu thức `p` như subtype CardPayment để dùng member riêng | `treat(p as CardPayment).lastFour` |
| Root subtype | Query trực tiếp trên subtype và các subtype con phù hợp | `from CardPayment c` |
| Java `instanceof` | Kiểm tra object đã được tải trong JVM | `payment instanceof CardPayment` |
| SQL `CAST` hoặc HQL `cast()` | Chuyển đổi **giá trị scalar** giữa các kiểu SQL/HQL | `cast(p.amount as String)` |

`TREAT` là cơ chế thu hẹp **kiểu entity/path** trong query, không phải lệnh chuyển BigDecimal sang String và cũng không phải một Java cast thực thi trên từng object trong vòng lặp.

### Vì sao ví dụ dùng cả TYPE và TREAT?

Điều kiện `where type(p) = CardPayment` làm rõ những hàng nào được chọn. `treat(...)` giúp tham chiếu field thuộc subclass.

Trong một số ngữ cảnh, bản thân treated path hoặc treated join có thể ảnh hưởng đến điều kiện subtype và những giá trị không thuộc subtype. Nhưng để code dễ hiểu và giảm phụ thuộc chi tiết SQL khi bắt đầu học, kết hợp điều kiện type rõ ràng là một lựa chọn tốt.

## 10. Lọc theo field riêng của subtype

Ví dụ lấy Payment có loại thẻ do issuer `VISA`:

```hql
select p
from Payment p
where type(p) = CardPayment
  and treat(p as CardPayment).issuer = :issuer
```

Java:

```java
List<Payment> visaPayments = session.createQuery(
    "select p from Payment p " +
    "where type(p) = CardPayment " +
    "and treat(p as CardPayment).issuer = :issuer",
    Payment.class
)
.setParameter("issuer", "VISA")
.getResultList();
```

Nếu chỉ cần CardPayment, cách trực tiếp hơn:

```hql
select c
from CardPayment c
where c.issuer = :issuer
```

Chọn query root là subtype khi use case **chỉ** làm việc với subtype ấy; dùng `type()` hoặc `treat()` khi query root/association cần tiếp tục đại diện nhiều loại Payment.

### Không dựa vào implicit subtype field access

Một số phiên bản HQL có khả năng suy luận và hỗ trợ truy cập thuộc tính chỉ xuất hiện ở subtype trong những trường hợp cụ thể. Tuy nhiên, JPQL portable không nên dựa vào việc alias kiểu Payment tự có field `issuer`.

Để biểu đạt rõ ràng, dùng `treat(p as CardPayment).issuer` hoặc chuyển root sang `CardPayment`. Điều này còn hữu ích khi nhiều subtype có field trùng tên nhưng khác ngữ nghĩa.

## 11. TREAT một association trong JOIN

Giả sử một đơn hàng tham chiếu tới thanh toán:

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "payment_id")
    private Payment payment;

    private String orderCode;
}
```

`PurchaseOrder.payment` được khai báo kiểu Payment vì đơn có thể thanh toán bằng bất kỳ subtype.

HQL:

```hql
select o.orderCode, c.lastFour
from PurchaseOrder o
join treat(o.payment as CardPayment) c
where c.issuer = :issuer
```

`join treat(o.payment as CardPayment) c` diễn đạt join tới payment và xử lý target như CardPayment, cho phép dùng `c.lastFour`, `c.issuer`.

### Khi nào nên dùng JOIN TREAT?

- Query root là entity khác, ví dụ PurchaseOrder.
- Association đích được khai báo bằng kiểu cha Payment.
- Chỉ cần thao tác với một subtype cụ thể của association.
- Muốn database thực hiện lọc/projection thay vì tải Payment rồi kiểm tra `instanceof` ở Java.

### JOIN thường và JOIN TREAT

```hql
select o
from PurchaseOrder o
join o.payment p
where p.status = :status
```

Query trên chỉ dùng field chung của Payment nên không cần TREAT.

Khi cần field riêng CardPayment:

```hql
select o.orderCode, c.issuer
from PurchaseOrder o
join treat(o.payment as CardPayment) c
```

Đây là lúc narrowing làm rõ semantics query.

## 12. LEFT JOIN TREAT và ý nghĩa của NULL

Giả sử yêu cầu lấy mọi đơn hàng, kèm bốn số cuối nếu phương thức thanh toán là thẻ:

```hql
select o.orderCode, c.lastFour
from PurchaseOrder o
left join treat(o.payment as CardPayment) c
order by o.orderCode
```

Về ý định, `LEFT JOIN` giữ những PurchaseOrder không có CardPayment phù hợp, còn `c.lastFour` là `NULL` khi không có matched CardPayment.

### Bẫy WHERE trên alias của LEFT JOIN

Thêm:

```hql
where c.issuer = :issuer
```

thì những hàng có `c` là `NULL` không vượt qua predicate, nên điều kiện WHERE có thể khiến kết quả hành xử như inner join với CardPayment.

Nếu muốn giữ mọi đơn hàng và chỉ điều kiện hóa phần join, cần xem xét `ON` predicate trong HQL phù hợp:

```hql
select o.orderCode, c.lastFour
from PurchaseOrder o
left join treat(o.payment as CardPayment) c
     on c.issuer = :issuer
```

HQL hỗ trợ các dạng join predicate, nhưng **SQL và semantics subtype filtering trong treated left join phụ thuộc mapping/version/dialect**. Hãy kiểm tra statement thực tế và dữ liệu thử cho cả card, wallet, bank và order không có payment. Đừng chỉ nhìn từ khóa LEFT rồi kết luận tất cả order sẽ luôn được giữ trong mọi biến thể query.

### Bảng minh họa

| Order | Payment runtime type | Card issuer | Kết quả LEFT JOIN mong đợi |
|---|---|---|---|
| O-1 | CardPayment | VISA | Có dữ liệu card |
| O-2 | WalletPayment | — | Phần card là NULL |
| O-3 | BankTransferPayment | — | Phần card là NULL |
| O-4 | Không có payment | — | Phần card là NULL |

Đây là **mục tiêu truy vấn** để kiểm tra, không phải bảo đảm rằng mọi cách viết TREAT + LEFT JOIN ở mọi phiên bản Hibernate sẽ sinh cùng một SQL. Với những case giữ toàn bộ root là yêu cầu bắt buộc, phải test query bằng integration test trên database thật.

## 13. TREAT và JPQL path expression

`TREAT` thuộc nhóm công cụ truy vấn theo kiểu entity được hỗ trợ trong JPQL/HQL. Nó thường hữu ích với:

- Identification variable của root entity.
- Single-valued association path tới superclass entity.
- Join path tới entity subtype.
- Tập entity có inheritance và thuộc tính được khai báo ở subclass.

Ví dụ typed root:

```hql
select treat(p as CardPayment).issuer
from Payment p
where type(p) = CardPayment
```

Ví dụ association:

```hql
select o.orderCode
from PurchaseOrder o
where type(o.payment) = CardPayment
```

`type(o.payment)` xét entity type của target association theo semantics provider. Nếu association nullable, các giá trị NULL cần được xử lý cẩn thận; phép so sánh với type sẽ không khớp target không tồn tại.

Khi sử dụng `treat()` trên đường dẫn nhiều tầng hoặc collection element, cú pháp cụ thể và những ràng buộc parser có thể khác giữa các thế hệ JPQL/Hibernate. Nên viết query đơn giản, định danh alias rõ, và kiểm tra bằng integration test theo đúng version.

## 14. CASE kết hợp TYPE cho báo cáo nhiều kiểu

Một dashboard có thể cần cột nhãn loại thanh toán:

```hql
select
    p.id,
    p.amount,
    case
        when type(p) = CardPayment then 'CARD'
        when type(p) = WalletPayment then 'WALLET'
        when type(p) = BankTransferPayment then 'BANK'
        else 'OTHER'
    end
from Payment p
order by p.createdAt desc
```

Với hierarchy đã ánh xạ, database/Hibernate có thể sử dụng discriminator hoặc biểu thức nhận diện subtype để tính CASE.

Java:

```java
List<Object[]> rows = session.createQuery(
    "select p.id, p.amount, " +
    "case " +
    "when type(p) = CardPayment then 'CARD' " +
    "when type(p) = WalletPayment then 'WALLET' " +
    "when type(p) = BankTransferPayment then 'BANK' " +
    "else 'OTHER' end " +
    "from Payment p order by p.createdAt desc",
    Object[].class
).getResultList();
```

`CASE` giúp trả nhãn từ query mà không cần tải mọi entity rồi kiểm tra Java runtime type. Nhưng `Object[]` có thể khó bảo trì nếu nhiều cột; nên cân nhắc typed DTO projection.

### TYPE không nhất thiết bằng nhãn nghiệp vụ

Nếu API contract trả enum `PaymentMethod.CARD`, không nên gắn chặt cả hợp đồng API vào tên Java class. Tên entity và discriminator có thể thay đổi khi refactor mapping. Một trường nghiệp vụ riêng hoặc một lớp mapping DTO có thể giữ hợp đồng ổn định hơn.

## 15. DTO projection với subtype

Giả sử chỉ cần các thanh toán thẻ:

```java
public record CardPaymentRow(
    Long id,
    BigDecimal amount,
    String lastFour,
    String issuer
) {}
```

HQL:

```hql
select new com.example.payments.CardPaymentRow(
    c.id,
    c.amount,
    c.lastFour,
    c.issuer
)
from CardPayment c
where c.status = :status
order by c.createdAt desc
```

Java:

```java
List<CardPaymentRow> cards = session.createQuery(
    "select new com.example.payments.CardPaymentRow(" +
    "c.id, c.amount, c.lastFour, c.issuer) " +
    "from CardPayment c " +
    "where c.status = :status " +
    "order by c.createdAt desc",
    CardPaymentRow.class
)
.setParameter("status", PaymentStatus.CONFIRMED)
.getResultList();
```

Projection hữu ích khi:

- API chỉ cần một số field.
- Không cần dirty checking hoặc entity graph managed.
- Muốn tránh lazy association bị serialize ngoài service.
- Muốn giảm dữ liệu truyền về so với SELECT toàn bộ entity hierarchy.

### DTO chung cho nhiều subtype

Có thể định nghĩa:

```java
public record PaymentSummary(
    Long id,
    BigDecimal amount,
    String kind,
    String cardLastFour
) {}
```

Rồi dùng `CASE` cho kind và `TREAT` cho card field. Nhưng cần quyết định rõ ý nghĩa `null`: với WalletPayment, cardLastFour không áp dụng; với CardPayment dữ liệu còn thiếu, đó có thể là lỗi dữ liệu. Đừng gộp cả hai trường hợp thành một giá trị không phân biệt nếu domain yêu cầu độ chính xác cao.

Đối với các DTO phức tạp, nhiều query chuyên biệt theo subtype rồi hợp nhất ở tầng application có thể dễ bảo trì hơn một query CASE/TREAT rất dài.

## 16. Truy vấn đa hình dưới ba chiến lược inheritance

Mã HQL:

```hql
from Payment p
where p.amount > :minimum
```

vẫn biểu đạt cùng một tập entity về mặt domain, nhưng SQL rất khác nhau theo `@Inheritance(strategy = ...)`.

### 16.1. SINGLE_TABLE

Một bảng chung chứa toàn bộ field của root và subtype:

```text
payments
  id
  payment_kind
  amount
  card_last_four
  wallet_provider
  bank_reference
```

Điển hình:

```sql
SELECT ...
FROM payments p
WHERE p.amount > ?;
```

`type(p) = CardPayment` có thể thành predicate trên discriminator:

```sql
WHERE p.payment_kind = 'CARD'
```

Ưu điểm: polymorphic read thường đơn giản, dễ lọc trên cột chung, không cần join giữa root/subtype. Nhược điểm: nhiều cột subtype không áp dụng cho hàng loại khác, bảng có thể rộng, constraint subtype cần thiết kế kỹ.

### 16.2. JOINED

Một bảng root và các bảng subtype:

```text
payments
  id, amount, status, created_at

card_payments
  id (PK, FK payments.id), last_four, issuer

wallet_payments
  id (PK, FK payments.id), wallet_provider

bank_transfer_payments
  id (PK, FK payments.id), bank_reference
```

Khi truy vấn toàn bộ hierarchy, Hibernate có thể cần LEFT JOIN các bảng subtype để xác định type và lấy trạng thái subclass.

```sql
SELECT ...
FROM payments p
LEFT JOIN card_payments c ON c.id = p.id
LEFT JOIN wallet_payments w ON w.id = p.id
LEFT JOIN bank_transfer_payments b ON b.id = p.id
WHERE p.amount > ?;
```

Đây là SQL minh họa, không phải SQL cố định. Hibernate có thể tối ưu các join tùy select list, query subtype và dialect.

`type(p)` có thể được suy ra từ bảng subtype có hàng hoặc từ discriminator nếu schema hỗ trợ. Vì vậy đừng mặc định `TYPE()` luôn bằng một cột vật lý duy nhất.

### 16.3. TABLE_PER_CLASS

Mỗi concrete subtype có bảng chứa cả field chung và field riêng:

```text
card_payments
  id, amount, status, ..., last_four, issuer

wallet_payments
  id, amount, status, ..., wallet_provider

bank_transfer_payments
  id, amount, status, ..., bank_reference
```

Khi query từ Payment, Hibernate có thể dùng các dạng `UNION` / `UNION ALL` hoặc chiến lược SQL tương đương để gộp các bảng cụ thể:

```sql
SELECT id, amount, status, ...
FROM card_payments
UNION ALL
SELECT id, amount, status, ...
FROM wallet_payments
UNION ALL
SELECT id, amount, status, ...
FROM bank_transfer_payments;
```

Đây cũng là mô hình giải thích. Query thực tế có thể thêm cột nhận diện kiểu, ép kiểu NULL, projection tương thích và các điều kiện tương ứng mỗi nhánh.

Vì một truy vấn đa hình có thể cần nhiều nhánh UNION, pagination, sort, count hoặc group by trên hierarchy có thể tốn kém. Cách cấp ID và uniqueness toàn hierarchy cũng cần thiết kế riêng.

### Bảng so sánh

| Chiến lược | SQL đa hình thường gặp | TYPE/TREAT cần gì? | Đánh đổi điển hình |
|---|---|---|---|
| SINGLE_TABLE | SELECT một bảng + discriminator | Predicate/column của bảng chung | Bảng rộng, cột subtype nullable |
| JOINED | JOIN root với bảng subtype | Join hoặc nhận diện subtype | Join nhiều khi query cả hierarchy |
| TABLE_PER_CLASS | UNION các bảng concrete | Nhận diện nhánh concrete, union/join khác | Polymorphic query có thể rất nặng |

**Không chọn inheritance strategy chỉ dựa trên độ ngắn của HQL.** Phải cân nhắc schema, số subtype, tần suất query polymorphic và subtype-specific, index, migration và tải thực tế.

## 17. Khi nào Hibernate tạo đúng subclass instance?

Một query từ Payment:

```java
Payment payment = session.find(Payment.class, 101L);
```

về mặt mapping phải biểu diễn entity tương ứng hàng dữ liệu. Nếu hàng thuộc discriminator `CARD`, Hibernate có thể materialize `CardPayment` chứ không tạo một Payment abstract.

Đồng thời Persistence Context có identity map cho entity key, giúp một entity trong cùng context không bị tạo thành nhiều managed instance chỉ vì được truy vấn qua các root khác nhau.

### Đừng dùng getClass() trên proxy để thay TYPE()

```java
Payment paymentRef = session.getReference(Payment.class, 101L);
System.out.println(paymentRef.getClass());
```

Một Hibernate proxy có thể là subclass kỹ thuật của entity class, nên `getClass()` có thể trả proxy class thay vì concrete mapped entity type bạn mong đợi. Một số helper xác định class thực của proxy có thể làm initialize proxy. Không nên xử lý truy vấn đa hình bằng cách tải hàng loạt entity rồi so sánh Java class trên proxy.

Muốn lọc theo kiểu ngay tại database, dùng `TYPE()` hoặc root subtype trong HQL. Muốn xử lý object đã được tải ở tầng Java, phân biệt mapped runtime type, proxy và các phương thức helper phù hợp Hibernate version.

## 18. TYPE() và TREAT() không phải giải pháp thay thế inheritance mapping

Giả sử Payment chỉ là interface Java:

```java
public interface Payment {
    BigDecimal amount();
}
```

và mỗi CardPayment, WalletPayment là entity không nằm trong cùng mapped hierarchy, không có association mapping rõ theo root entity.

Không thể tự suy ra rằng:

```hql
from Payment p
```

sẽ có cùng SQL/behavior/portability như `@Entity abstract class Payment` với `@Inheritance`.

Nếu muốn query tập entity khác bảng không thuộc inheritance mapping, có thể:

- Thiết kế mapped inheritance hierarchy.
- Truy vấn riêng từng entity rồi hợp nhất theo domain.
- Dùng DTO + HQL set operations khi phiên bản Hibernate hỗ trợ và SQL phù hợp.
- Dùng database view/native query như một read model.

Việc HQL trong một số phiên bản có hỗ trợ implicit polymorphism qua interface hoặc superclass không được ánh xạ phải được xem là **Hibernate-specific**, không đồng nghĩa JPQL chuẩn và có thể có giới hạn join, fetching, type resolution hay query optimization.

## 19. Criteria API: type() và treat() với kiểu Java

Nếu muốn xây query động có type safety tốt hơn nối chuỗi HQL, Jakarta Persistence Criteria API hỗ trợ cơ chế tương ứng.

### 19.1. Lọc theo entity type

```java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();
CriteriaQuery<Payment> cq =
    cb.createQuery(Payment.class);

Root<Payment> payment = cq.from(Payment.class);

cq.select(payment).where(
    cb.equal(payment.type(), CardPayment.class)
);

List<Payment> results =
    entityManager.createQuery(cq).getResultList();
```

`payment.type()` là Criteria expression biểu thị entity type. Nó tương đương ý tưởng HQL `type(p)`.

### 19.2. Thu hẹp root bằng treat()

```java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();
CriteriaQuery<CardPayment> cq =
    cb.createQuery(CardPayment.class);

Root<Payment> payment = cq.from(Payment.class);
Root<CardPayment> card = cb.treat(
    payment,
    CardPayment.class
);

cq.select(card).where(
    cb.equal(payment.type(), CardPayment.class),
    cb.equal(card.get("issuer"), "VISA")
);

List<CardPayment> results =
    entityManager.createQuery(cq).getResultList();
```

`cb.treat(payment, CardPayment.class)` biểu diễn typed downcast trong Criteria tree. Điều kiện `payment.type()` làm rõ rằng chỉ lấy entity đúng loại thẻ của hierarchy ví dụ.

Khi Criteria query có nhiều join hoặc collection, overload `treat` tương ứng với `Root`, `Join` hoặc path expression cần được chọn đúng. Tránh tự cast Java generic type vì `(Root<CardPayment>) payment` không tạo ra semantic downcast trong query.

## 20. TYPE() trên association và xử lý NULL

Trong thực tế association có thể là optional:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = true)
private Payment payment;
```

Truy vấn:

```hql
select o
from PurchaseOrder o
where type(o.payment) = CardPayment
```

về ý định chọn những order có payment thuộc kiểu CardPayment. Nếu payment là `NULL`, biểu thức type không có một entity target để khớp và order ấy không được chọn bởi điều kiện equality.

Nếu muốn giữ order không có payment:

```hql
select o
from PurchaseOrder o
where o.payment is null
   or type(o.payment) = CardPayment
```

### Phân biệt JOIN và LEFT JOIN

Truy cập đường dẫn association trong HQL có thể sinh implicit join theo semantics path. Nếu query phải giữ root có association NULL, cân nhắc explicit LEFT JOIN và kiểm tra WHERE/ON.

Ví dụ HQL:

```hql
select o
from PurchaseOrder o
left join o.payment p
where p is null or type(p) = CardPayment
```

Query shape, đặc biệt với `TREAT` và type predicates trên JOINED/TABLE_PER_CLASS, cần được quan sát trên database thực tế. Đừng chỉ nhìn `left join` mà bỏ qua điều kiện WHERE có thể loại hàng NULL.

## 21. GROUP BY và thống kê theo kiểu entity

Nếu cần thống kê số thanh toán theo subtype:

```hql
select type(p), count(p)
from Payment p
group by type(p)
```

Về mặt domain, kết quả nhóm theo entity type. Hibernate có thể dịch thành nhóm theo discriminator hoặc một biểu thức nhận diện subtype tương đương.

Ví dụ khác theo loại và trạng thái:

```hql
select type(p), p.status, count(p), sum(p.amount)
from Payment p
group by type(p), p.status
order by p.status
```

### Những điểm cần lưu ý

- Giá trị `type(p)` là entity type expression, không mặc định là một string phù hợp API.
- `count(p)` có kiểu số nguyên dài trong kết quả query tiêu chuẩn; `sum(p.amount)` có kiểu numeric theo trường được aggregate.
- Với TABLE_PER_CLASS, query nhóm có thể phải đọc/union nhiều bảng.
- Một index trên discriminator/status có thể giúp SINGLE_TABLE, nhưng phải đo query plan.
- Khi dashboard lớn, một read model/materialized view hoặc bảng aggregate có thể phù hợp hơn.

Nếu API chỉ cần nhãn `CARD/WALLET/BANK`, có thể map class/entity type sang enum ở service hoặc dùng CASE với nhãn nghiệp vụ có kiểm soát.

## 22. Kết hợp TYPE() với điều kiện động

Giả sử API tìm thanh toán có tham số optional `paymentKind` và `status`.

Không nên xây HQL bằng cách nối trực tiếp tên class đến từ HTTP request:

```java
// Không nên làm:
String hql = "from Payment p where type(p) = " +
    userSuppliedTypeName;
```

Thay vào đó:

1. Parse giá trị input sang enum nghiệp vụ.
2. Ánh xạ enum sang các mapped entity classes được cho phép.
3. Dùng named parameter cho scalar và entity type.
4. Hoặc xây Criteria predicate có type safety.

Ví dụ:

```java
String hql =
    "select p from Payment p " +
    "where p.status = :status " +
    "and type(p) = :paymentType";

List<Payment> result = session.createQuery(
    hql,
    Payment.class
)
.setParameter("status", PaymentStatus.CONFIRMED)
.setParameter("paymentType", CardPayment.class)
.getResultList();
```

Đối với danh sách type động, Hibernate có `setParameterList` trên query thích hợp; việc bind danh sách `Class` cần xác nhận type inference theo phiên bản. Criteria API với `type().in(...)` là một phương án rõ nghĩa:

```java
Predicate kindFilter = payment.type().in(
    CardPayment.class,
    WalletPayment.class
);
```

Không tin tưởng class name do client gửi để chọn bất cứ entity nào trong SessionFactory. Chỉ cho phép tập entity được thiết kế trong API.

## 23. Bulk UPDATE/DELETE trên hierarchy cần đặc biệt cẩn thận

HQL cho phép bulk mutation, nhưng đó không phải quá trình update từng managed entity bằng dirty checking.

Ví dụ bulk update subtype:

```hql
update CardPayment c
set c.status = :newStatus
where c.status = :oldStatus
```

Những vấn đề cần hiểu:

- Query từ subtype ảnh hưởng tập entity tương ứng theo mapping; SQL có thể khác theo inheritance strategy.
- Với JOINED/TABLE_PER_CLASS hoặc các mapping liên quan nhiều bảng, Hibernate có thể cần cơ chế multi-table mutation/SQL bổ sung.
- Bulk DML không tự sửa những managed entity đã load trong Persistence Context.
- Bulk update thông thường không tăng `@Version` theo cùng cơ chế dirty checking của mỗi entity.
- Lifecycle callbacks ở mức entity không nên được giả định chạy cho từng hàng.
- Số hàng trả về bởi bulk mutation ở Hibernate có thể diễn đạt số entity bị ảnh hưởng, không nhất thiết đúng số SQL rows nếu mutation trải nhiều bảng.

Nếu cần optimistic locking ở bulk update, hãy thiết kế điều kiện version hoặc quy trình cập nhật riêng theo mapping/version. Nếu cần xử lý lifecycle callback và invariant từng entity, có thể phù hợp hơn khi cập nhật managed entities.

**Không lấy `type()` làm công cụ bảo đảm mọi bulk UPDATE đều an toàn về concurrency.** Type filtering chỉ chọn đối tượng/nhánh hierarchy; concurrency là yêu cầu khác.

## 24. Fetch join và đa hình: tránh tải graph quá lớn

HQL:

```hql
select p
from Payment p
left join fetch p.someAssociation
```

chỉ có ý nghĩa nếu association thực sự được ánh xạ trên root hoặc đường dẫn được treat phù hợp. Nếu association riêng của CardPayment, query phải thể hiện kiểu con rõ ràng.

Khi kết hợp polymorphism với collection fetch joins, có thể gặp:

- Nhân số hàng SQL cho các collection.
- N+1 ở association không được fetch.
- Vấn đề phân trang trên collection fetch join.
- Multiple bag fetch khi muốn join nhiều bag.
- Entity graph khổng lồ bị hydrate dù UI chỉ cần vài field.

Với dashboard nhiều loại thanh toán, DTO projection của field chung thường hiệu quả hơn việc hydrate mọi subtype và association. Với màn hình chi tiết thanh toán thẻ, query trực tiếp CardPayment cùng fetch plan cụ thể sẽ dễ tối ưu hơn.

## 25. Pagination trên polymorphic query

Ví dụ:

```java
List<Payment> page = session.createQuery(
    "from Payment p " +
    "where p.status = :status " +
    "order by p.createdAt desc, p.id desc",
    Payment.class
)
.setParameter("status", PaymentStatus.CONFIRMED)
.setFirstResult(0)
.setMaxResults(20)
.getResultList();
```

Thêm `p.id` vào ORDER BY để thứ tự ổn định hơn khi nhiều thanh toán có cùng timestamp; các khóa sort vẫn cần được thiết kế để tạo total order phù hợp dữ liệu thực.

### Điểm cần kiểm chứng theo inheritance strategy

- SINGLE_TABLE: database có thể áp limit/offset trên một bảng.
- JOINED: query có thể cần join các bảng subtype trước khi sort/page.
- TABLE_PER_CLASS: query có thể cần union nhiều nhánh rồi sort/page toàn kết quả.
- Nếu fetch collection đồng thời, pagination có thể gây vấn đề hoặc áp trong bộ nhớ.
- Nếu chỉ cần count, query `select count(p)` có thể có SQL plan khác query lấy entity.

Không chỉ đo tốc độ trang đầu. Với offset lớn và polymorphic UNION/JOIN, có thể cân nhắc keyset pagination nếu bộ lọc/sort và thư viện hỗ trợ.

## 26. Những tình huống dễ nhầm khi dùng TYPE/TREAT

### “from Payment chỉ trả instance Payment”

Không. Với mapped entity hierarchy, query root Payment mang tính đa hình và có thể trả các concrete subtype.

### “Payment abstract thì không query được”

Không đúng. `@Entity abstract Payment` vẫn có thể là HQL query root. Nó chỉ không được instantiate như một concrete entity.

### “TYPE(p) trả chuỗi discriminator”

Không phải ngữ nghĩa chung. `TYPE` là entity type expression; discriminator chỉ là một cách mapping/database hiện thực.

### “TYPE(p) = CardPayment giống Java instanceof”

Không hoàn toàn. So sánh entity type thường nhắm tới kiểu cụ thể, còn Java instanceof nhận cả subclass. Root subtype có thể đa hình theo nhánh kế thừa.

### “TREAT là chuyển đổi scalar giống CAST”

Không. `TREAT` thu hẹp entity/path type để truy cập subtype members; `CAST` chuyển biểu thức giá trị.

### “Đã dùng WHERE type thì mọi subtype field đều truy cập trực tiếp được từ alias cha”

Không nên giả định kiểu alias HQL được narrow tự động như compiler Java. Dùng `treat(p as CardPayment).issuer` hoặc root CardPayment.

### “LEFT JOIN TREAT chắc chắn giữ mọi root dù có WHERE trên alias”

Không. `WHERE c.issuer = ...` có thể loại hàng khi `c` NULL. Phân biệt join predicate và post-join filter.

### “Inheritance strategy chỉ ảnh hưởng DDL, không ảnh hưởng query”

Sai. SINGLE_TABLE, JOINED và TABLE_PER_CLASS có SQL plan rất khác cho cùng một HQL.

### “Có thể query từ @MappedSuperclass như entity root”

Không theo JPQL chuẩn. `@MappedSuperclass` không phải entity query root.

### “Dùng instanceof sau khi load cũng hiệu quả như TYPE()”

Không. Nếu database có thể lọc theo type, tải tất cả entity rồi kiểm tra tại JVM có thể tốn SQL, mạng và bộ nhớ.

### “HQL type predicates tự bảo vệ dữ liệu multi-tenant”

Không. Type predicate chỉ phân biệt entity types, không phải authorization hoặc tenant isolation. Điều kiện tenant/security phải được thực thi bằng mapping, query và kiểm tra quyền riêng.

### “TREAT luôn nhanh hơn query trực tiếp subtype”

Không. SQL thực tế phụ thuộc mapping và optimizer. Nếu use case chỉ cần CardPayment, query root CardPayment thường rõ ràng và dễ tối ưu.

## 27. Cách chẩn đoán query TYPE/TREAT không hoạt động như mong đợi

Khi query trả sai tập bản ghi, gặp lỗi parser hoặc chạy chậm:

1. **Xác định root entity type.** `Payment` có `@Entity` hay chỉ `@MappedSuperclass`?
2. **Xác định hierarchy.** Những subclass nào có `@Entity`, `@DiscriminatorValue` và inheritance strategy nào?
3. **Kiểm tra tên entity HQL.** Nếu class dùng `@Entity(name = "...")`, tên entity trong HQL có thể khác Java simple class name.
4. **Phân biệt exact type và branch.** Bạn cần đúng concrete type hay mọi subclass của CardPayment?
5. **Kiểm tra subtype field.** Thuộc tính có nằm trên CardPayment hay một entity khác? Có cần `TREAT` không?
6. **Đọc SQL thật.** Hibernate đang dùng discriminator, JOIN, UNION hoặc truy vấn bổ sung?
7. **Kiểm tra NULL và join semantics.** Predicate ở `WHERE` có vô tình loại root của LEFT JOIN?
8. **Kiểm tra data/migration.** Discriminator value trên database có đúng mapping hay có giá trị không được ánh xạ?
9. **Xem query plan và index.** TYPE filter có dùng index? JOINED có nhiều join? TABLE_PER_CLASS có union lớn?
10. **Kiểm tra context và cache.** Entity đã managed có dữ liệu cũ? Query projection khác query entity thế nào?
11. **Kiểm tra phiên bản Hibernate/dialect.** Cú pháp treated joins, Criteria treat và type parameter có được hỗ trợ theo cách đang dùng không?
12. **Kiểm tra test kết quả.** Có bao phủ từng subtype, optional association và các subclass sâu hơn không?

### SQL logging

Ví dụ trong Spring Boot với Hibernate ORM 6:

```properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Chỉ bật bind logging chi tiết trong môi trường kiểm soát vì query parameters có thể chứa dữ liệu nhạy cảm.

### Query plan

Quan sát `EXPLAIN`/`EXPLAIN ANALYZE` trên database thật:

- Filter trên discriminator có dùng index phù hợp không?
- JOINED đang join mấy bảng và số hàng trung gian bao nhiêu?
- TABLE_PER_CLASS có dùng UNION và sort lớn không?
- Predicate subtype có được push down vào nhánh phù hợp không?
- HQL projection có tránh đọc cột/association không cần thiết không?

**Một câu HQL gọn không bảo đảm SQL nhẹ.** Query theo kiểu entity phải được đánh giá cùng mapping strategy và workload.

## 28. Bài thực hành 1: lọc và tổng hợp nhiều subtype

Tạo dữ liệu:

```text
Payment#101: CardPayment, amount=250000, CONFIRMED, issuer=VISA
Payment#102: WalletPayment, amount=90000, PENDING, provider=MOMO
Payment#103: BankTransferPayment, amount=700000, CONFIRMED
Payment#104: CardPayment, amount=180000, FAILED, issuer=MASTERCARD
```

Thực hiện:

1. Query `from Payment p`, kiểm tra danh sách và class entity concrete được materialize.
2. Query `from CardPayment c`.
3. Query `where type(p) = CardPayment`.
4. Query `where type(p) in (CardPayment, WalletPayment)`.
5. Dùng `CASE` với `type(p)` để tạo nhãn kiểu.
6. Dùng `GROUP BY type(p)` để đếm các loại payment.
7. So sánh số hàng và SQL được phát.

### Câu hỏi

- Root Payment abstract có cản trở truy vấn không?
- Tại sao query từ CardPayment có thể không cần TREAT?
- Tên `CARD` trong discriminator và `CardPayment` trong HQL có cùng vai trò không?
- Nếu CardPayment có subclass CreditCardPayment, hai truy vấn lọc exact type và từ CardPayment khác nhau ra sao?

## 29. Bài thực hành 2: xử lý thuộc tính kiểu con

Viết query lấy bốn số cuối và issuer của những thanh toán thẻ đã CONFIRMED.

**Cách A — query root subtype:**

```hql
select c.lastFour, c.issuer
from CardPayment c
where c.status = :status
```

**Cách B — query root superclass với TREAT:**

```hql
select treat(p as CardPayment).lastFour,
       treat(p as CardPayment).issuer
from Payment p
where type(p) = CardPayment
  and p.status = :status
```

So sánh SQL và plan. Với hierarchy SINGLE_TABLE, hai cách có thể rất gần nhau; với JOINED hoặc TABLE_PER_CLASS, hình dạng SQL có thể khác đáng kể.

**Cách C — DTO projection:** tạo `CardPaymentRow` để tránh truyền entity về REST controller. So sánh dữ liệu được đọc với query SELECT toàn bộ CardPayment.

## 30. Bài thực hành 3: JOIN TREAT trên đơn hàng

Tạo PurchaseOrder có association `payment: Payment`. Seed:

```text
O-1 -> CardPayment#101
O-2 -> WalletPayment#102
O-3 -> BankTransferPayment#103
O-4 -> NULL
```

Viết các query:

1. Join tất cả Payment và lọc theo `p.status`.
2. Join treated CardPayment và lấy `c.lastFour`.
3. LEFT JOIN treated CardPayment và xem order nào được giữ.
4. Thêm `WHERE c.issuer = 'VISA'` rồi quan sát số order thay đổi.
5. Nếu phiên bản hỗ trợ, chuyển predicate phù hợp sang `ON` và quan sát sự khác biệt.

Mục tiêu là hiểu **kiểu của association target**, **downcast bằng TREAT**, và **khác biệt giữa LEFT JOIN với filter trong WHERE**.

## 31. Bài thực hành 4: so sánh SQL của ba inheritance strategies

Tạo ba bộ mapping thử nghiệm tách biệt với cùng dữ liệu nghiệp vụ, lần lượt dùng:

- `InheritanceType.SINGLE_TABLE`.
- `InheritanceType.JOINED`.
- `InheritanceType.TABLE_PER_CLASS`.

Chạy cùng nhóm query:

```hql
from Payment p
where p.amount >= :minimum
```

```hql
from Payment p
where type(p) = CardPayment
```

```hql
select type(p), count(p)
from Payment p
group by type(p)
```

Quan sát:

- Số bảng được đọc.
- Discriminator, JOIN hoặc UNION trong SQL.
- Số hàng trung gian.
- Query plan và thời gian xử lý.
- Query count/latency khi chỉ lấy subtype.
- Kết quả pagination/sort theo thuộc tính chung.

Không lấy kết quả từ H2 để kết luận tuyệt đối cho PostgreSQL/MySQL/Oracle; dialect và optimizer khác nhau.

## 32. Câu hỏi tự kiểm tra

1. Truy vấn `from Payment p` có trả CardPayment không nếu Payment là mapped entity root?
2. `@MappedSuperclass` có phải query root JPQL chuẩn không?
3. `type(p)` biểu diễn discriminator string hay entity type?
4. `type(p) = CardPayment` có luôn tương đương Java `instanceof CardPayment` với hierarchy nhiều cấp không?
5. Khi query root Payment nhưng cần `lastFour` của CardPayment, nên dùng công cụ nào?
6. `treat(p as CardPayment)` có giống `cast(p.amount as String)` không?
7. Khi nào nên query trực tiếp `from CardPayment c`?
8. `LEFT JOIN TREAT` và `WHERE` trên treated alias có thể ảnh hưởng hàng NULL thế nào?
9. HQL đa hình dùng một SQL giống nhau trên SINGLE_TABLE, JOINED và TABLE_PER_CLASS không?
10. Tại sao TABLE_PER_CLASS có thể tốn kém với sort/pagination toàn hierarchy?
11. Có nên dùng `getClass()` trên proxy để thay `TYPE()` lọc trong DB không?
12. Vì sao typed DTO projection thường phù hợp API hơn việc trả nguyên entity graph?

**Gợi ý:** (1) có; (2) không; (3) entity type; (4) không hoàn toàn; (5) `TREAT`; (6) không; (7) khi use case chỉ cần subtype; (8) WHERE có thể loại root khi alias NULL; (9) không; (10) có thể cần UNION và sort nhiều nhánh; (11) không; (12) dữ liệu rõ ràng, giảm hydration/serialization ngoài ý muốn.

## 33. Những nguyên tắc quan trọng cần nhớ

1. **HQL truy vấn mapped entity hierarchy theo ngữ nghĩa đa hình.** Query từ root có thể trả nhiều concrete subtype; root có thể là abstract entity.
2. **`TYPE()` xét entity type**, không phải cột discriminator string hay Java `getClass()` trên proxy.
3. **Root subtype và so sánh exact type không nhất thiết giống nhau** khi hierarchy có nhiều cấp kế thừa.
4. **`TREAT()` thu hẹp entity/path type** để dùng member của subtype trong SELECT, WHERE, JOIN và các cấu trúc query phù hợp.
5. **`TREAT()` khác `CAST()`**; một bên thao tác trên entity hierarchy, một bên chuyển đổi scalar value.
6. **Khi chỉ cần một subtype, query trực tiếp subtype thường rõ ràng hơn**; khi root/association vẫn mang kiểu cha, `TYPE` và `TREAT` giúp diễn đạt điều kiện.
7. **LEFT JOIN và predicate WHERE có semantics riêng.** Điều kiện trên treated alias có thể loại hàng không có subtype khớp.
8. **Inheritance mapping quyết định SQL shape.** SINGLE_TABLE thường dựa discriminator; JOINED có thể join bảng con; TABLE_PER_CLASS có thể union bảng concrete.
9. **Lọc theo kiểu không thay thế kiểm soát transaction, version hay authorization.** Chọn đúng subtype là một phần của query semantics, không phải toàn bộ invariant.
10. **Kiểm chứng bằng SQL log, query plan và integration test.** Cùng một câu HQL có thể khác lớn về hiệu năng và hình dạng SQL giữa các mapping/dialect/version.

Khi gặp yêu cầu truy vấn nhiều kiểu thanh toán, hãy phân biệt ba câu hỏi: **“Tôi muốn toàn bộ hierarchy hay chỉ một nhánh?”, “Tôi cần lọc theo type hay truy cập thuộc tính subtype?”, và “Inheritance mapping của tôi khiến database phải đọc những bảng nào?”**. Chọn đúng root entity, `TYPE()` và `TREAT()` sẽ giúp HQL biểu đạt chính xác nghiệp vụ mà không phải tải mọi entity rồi phân loại trong Java.

### Tài liệu tham khảo chính thức

- [Hibernate ORM Query Language — HQL](https://docs.jboss.org/hibernate/orm/current/querylanguage/html_single/Hibernate_Query_Language.html)
- [Hibernate ORM User Guide — Inheritance](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html#entity-inheritance)
- [Hibernate ORM User Guide — HQL](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html#hql)
- [Hibernate ORM User Guide — Criteria](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html#criteria)
- [Hibernate ORM User Guide — Bulk mutation queries](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html#batch-bulk)
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/)
- [Jakarta Persistence API — CriteriaBuilder](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/criteria/criteriabuilder)
