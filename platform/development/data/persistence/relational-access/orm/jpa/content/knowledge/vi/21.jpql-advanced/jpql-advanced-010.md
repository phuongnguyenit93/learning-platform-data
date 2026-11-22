# Truy vấn đa hình bằng `TYPE` và `TREAT`

Trong các ứng dụng sử dụng JPA, một hệ thống đôi khi có **nhiều kiểu entity khác nhau nhưng cùng chia sẻ một mô hình nghiệp vụ**. Ví dụ, tất cả giao dịch thanh toán đều có mã giao dịch, số tiền và thời điểm tạo, nhưng thanh toán bằng thẻ có mã ủy quyền, chuyển khoản có mã tham chiếu ngân hàng, còn ví điện tử có định danh nhà cung cấp. Khi các kiểu này được ánh xạ bằng **entity inheritance**, JPQL cho phép truy vấn chúng theo kiểu đa hình (*polymorphism*).

Hai công cụ đặc biệt quan trọng là:

- **`TYPE(expression)`**: xem **kiểu entity thực tế** mà một biểu thức entity đại diện, thường dùng để lọc hoặc phân loại kết quả theo subtype.
- **`TREAT(path AS Subtype)`**: **thu hẹp kiểu** (*downcast*) của một đường dẫn entity trong JPQL để có thể truy cập các thuộc tính/association chỉ được khai báo trên subtype đó.

Ví dụ:

```sql
-- Lấy mọi thanh toán có kiểu entity thực tế là CardPayment.
select p
from Payment p
where type(p) = CardPayment
```

```sql
-- Lọc trên thuộc tính chỉ CardPayment mới có.
select p
from Payment p
where treat(p as CardPayment).authorizationCode = :code
```

Hai query đều có thể trả thanh toán bằng thẻ nhưng **trả lời những câu hỏi khác nhau**. `TYPE` trả lời “entity này thuộc kiểu nào?”, còn `TREAT` trả lời “tôi muốn dùng biểu thức này như subtype để truy cập trường của subtype”. Để sử dụng chính xác, cần hiểu cấu trúc kế thừa, phạm vi kết quả của query, cách mapping xuống SQL và ngữ nghĩa khi một entity **không thuộc subtype được TREAT**.

Bài học thuộc phần **JPQL nâng cao** của chủ đề **Data Persistence Relational Access ORM JPA**. Nội dung dùng namespace `jakarta.persistence` và các ví dụ có thể áp dụng cho môi trường JPA tương thích. Những phần liên quan tới SQL sinh ra, giới hạn cú pháp hoặc hành vi tối ưu của provider được trình bày như những vấn đề cần nhận biết, không coi chúng là hợp đồng SQL giống nhau cho mọi phiên bản Hibernate, EclipseLink và mọi RDBMS.

## 1. Vì sao truy vấn đa hình xuất hiện?

Giả sử hệ thống có ba hình thức thanh toán:

```text
                    Payment
              id, amount, status
                      |
        +-------------+--------------+
        |             |              |
    CardPayment  BankTransferPayment  WalletPayment
    cardBrand    bankReference        providerCode
    authCode     senderAccount        walletAccount
```

Một trang quản trị cần xem **tất cả thanh toán**. Một màn hình đối soát ngân hàng chỉ cần **BankTransferPayment**. Một báo cáo tra soát thẻ cần lọc theo **authorizationCode**, thuộc tính không tồn tại trên `Payment`.

Nếu không có hỗ trợ đa hình, code có thể buộc phải chạy ba query riêng rồi trộn kết quả trong bộ nhớ:

```java
List<CardPayment> cards = /* query card payments */;
List<BankTransferPayment> transfers = /* query transfers */;
List<WalletPayment> wallets = /* query wallets */;
// Gộp và tự sắp xếp, phân trang, thống kê...
```

Việc này dễ gây lỗi: phân trang tổng thể không chính xác, giới hạn query không áp dụng cho toàn tập, thiếu subtype mới, hoặc cần lặp lại điều kiện chung ở nhiều nơi.

Với JPA inheritance:

```java
List<Payment> payments = em.createQuery(
        "select p from Payment p order by p.id",
        Payment.class)
    .getResultList();
```

Query xuất phát từ root entity `Payment` có thể trả về instance thuộc các concrete entity subclass phù hợp. Đây là **polymorphic query mặc định**. `TYPE` và `TREAT` bổ sung khả năng lọc theo kiểu hoặc khai thác trường chuyên biệt.

## 2. Điều kiện nền tảng: entity inheritance thực sự

Để học `TYPE` và `TREAT`, trước hết cần có một hierarchy mà **lớp cha là entity**:

```java
package example.payment;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;

@Entity
@Table(name = "payments")
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(
    name = "payment_kind",
    discriminatorType = DiscriminatorType.STRING,
    length = 30
)
public abstract class Payment {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @Column(name = "amount", nullable = false,
            precision = 15, scale = 2)
    private BigDecimal amount;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 30)
    private PaymentStatus status;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    protected Payment() {}

    protected Payment(BigDecimal amount, PurchaseOrder order) {
        if (amount == null || amount.signum() < 0) {
            throw new IllegalArgumentException("Invalid payment amount");
        }
        this.amount = amount;
        this.order = order;
        this.status = PaymentStatus.PENDING;
        this.createdAt = Instant.now();
    }

    public Long getId() { return id; }
    public BigDecimal getAmount() { return amount; }
    public PaymentStatus getStatus() { return status; }
    public Instant getCreatedAt() { return createdAt; }
    public PurchaseOrder getOrder() { return order; }
}
```

Các enum và relationship liên quan:

```java
package example.payment;

public enum PaymentStatus {
    PENDING, SUCCEEDED, FAILED
}
```

```java
package example.payment;

import jakarta.persistence.*;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @OneToMany(mappedBy = "order")
    private List<Payment> payments = new ArrayList<>();

    protected PurchaseOrder() {}

    public Long getId() { return id; }
}
```

Các subtype:

```java
package example.payment;

import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@DiscriminatorValue("CARD")
public class CardPayment extends Payment {

    @Column(name = "card_brand", length = 30)
    private String cardBrand;

    @Column(name = "authorization_code", length = 80)
    private String authorizationCode;

    protected CardPayment() {}

    public CardPayment(
            BigDecimal amount,
            PurchaseOrder order,
            String cardBrand,
            String authorizationCode) {
        super(amount, order);
        this.cardBrand = cardBrand;
        this.authorizationCode = authorizationCode;
    }

    public String getCardBrand() { return cardBrand; }
    public String getAuthorizationCode() { return authorizationCode; }
}
```

```java
package example.payment;

import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@DiscriminatorValue("BANK")
public class BankTransferPayment extends Payment {

    @Column(name = "bank_reference", length = 100)
    private String bankReference;

    @Column(name = "sender_account", length = 80)
    private String senderAccount;

    protected BankTransferPayment() {}

    public BankTransferPayment(
            BigDecimal amount,
            PurchaseOrder order,
            String reference) {
        super(amount, order);
        this.bankReference = reference;
    }

    public String getBankReference() { return bankReference; }
}
```

```java
package example.payment;

import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@DiscriminatorValue("WALLET")
public class WalletPayment extends Payment {

    @Column(name = "provider_code", length = 50)
    private String providerCode;

    @Column(name = "wallet_account", length = 100)
    private String walletAccount;

    protected WalletPayment() {}

    public WalletPayment(
            BigDecimal amount,
            PurchaseOrder order,
            String providerCode) {
        super(amount, order);
        this.providerCode = providerCode;
    }

    public String getProviderCode() { return providerCode; }
}
```

Các đoạn code minh họa mapping. Trong một dự án thực tế, còn cần cấu hình persistence unit, dependency JPA provider, database và cách tạo schema. Annotation `@Inheritance` chỉ có ý nghĩa khi gốc của hierarchy là một `@Entity` thích hợp.

### 2.1. SQL mô hình `SINGLE_TABLE`

Với chiến lược `SINGLE_TABLE`, dữ liệu subtype có thể nằm trong cùng bảng:

```sql
CREATE TABLE payments (
    id                 BIGINT PRIMARY KEY,
    payment_kind       VARCHAR(30) NOT NULL,
    amount             DECIMAL(15, 2) NOT NULL,
    status             VARCHAR(30) NOT NULL,
    created_at         TIMESTAMP NOT NULL,
    order_id           BIGINT NOT NULL,
    card_brand         VARCHAR(30),
    authorization_code VARCHAR(80),
    bank_reference     VARCHAR(100),
    sender_account     VARCHAR(80),
    provider_code      VARCHAR(50),
    wallet_account     VARCHAR(100),
    FOREIGN KEY (order_id) REFERENCES purchase_orders(id)
);
```

Ví dụ dữ liệu:

| id | payment_kind | amount | card_brand | authorization_code | bank_reference |
|---|---|---:|---|---|---|
| 10 | `CARD` | 120.00 | VISA | A-123 | NULL |
| 11 | `BANK` | 500.00 | NULL | NULL | B-456 |
| 12 | `WALLET` | 75.00 | NULL | NULL | NULL |
| 13 | `CARD` | 220.00 | MASTERCARD | A-789 | NULL |

`payment_kind` là discriminator của ánh xạ. Giá trị `CARD`, `BANK` và `WALLET` là **giá trị lưu trữ**, không phải trực tiếp là tên entity literal của JPQL. Chi tiết nullability của các cột chuyên biệt cần được thiết kế với mô hình một bảng chứa nhiều subtype.

## 3. Query trên lớp cha là query đa hình mặc định

JPQL:

```java
List<Payment> payments = em.createQuery(
        "select p from Payment p " +
        "where p.status = :status " +
        "order by p.id",
        Payment.class)
    .setParameter("status", PaymentStatus.SUCCEEDED)
    .getResultList();
```

Một `Payment` là **entity root** của hierarchy, nên query này có thể trả về các instance:

```text
Payment p
  -> CardPayment
  -> BankTransferPayment
  -> WalletPayment
```

Mặc dù `Payment` là abstract class và không được khởi tạo trực tiếp, nó vẫn là một entity hợp lệ để làm root của JPQL query. Kết quả `List<Payment>` có thể chứa những Java object concrete subclass.

```java
for (Payment payment : payments) {
    System.out.println(payment.getId());
    System.out.println(payment.getAmount());
}
```

Ta có thể truy cập các field chung vì `Payment` khai báo chúng. Nhưng không thể viết:

```java
payment.getAuthorizationCode(); // Không có trên Payment.
```

vì `authorizationCode` chỉ thuộc `CardPayment`. Đó là nơi `TYPE` và `TREAT` phát huy tác dụng.

### 3.1. Query trên subtype

Nếu chỉ cần card payments và không cần khởi tạo root `Payment`:

```java
List<CardPayment> cards = em.createQuery(
        "select c from CardPayment c " +
        "where c.cardBrand = :brand",
        CardPayment.class)
    .setParameter("brand", "VISA")
    .getResultList();
```

Đây cũng là cách hợp lệ. Query trực tiếp từ subtype thường dễ đọc khi **toàn bộ truy vấn** chỉ làm việc với một kiểu cụ thể.

Vậy khi nào dùng `TYPE` và `TREAT`?

- **`TYPE`**: khi query bắt đầu từ root chung nhưng cần **phân biệt subtype**, kết hợp các kiểu hoặc tham số hóa kiểu.
- **`TREAT`**: khi đường dẫn ở mức root (hoặc một association được khai báo theo root) nhưng điều kiện/select/join cần truy cập **thuộc tính chỉ có trên subtype**.

## 4. `TYPE` là gì?

Cú pháp JPQL thường dùng:

```sql
TYPE(entity_expression)
```

Ví dụ:

```sql
select p
from Payment p
where type(p) = CardPayment
```

`TYPE(p)` trả thông tin kiểu entity thực tế của `p` theo hierarchy JPA. Phần `CardPayment` ở vế phải là **entity type literal** (tên entity), không phải một chuỗi ký tự.

So sánh:

```sql
-- Đúng về mô hình JPQL khi entity name là CardPayment.
where type(p) = CardPayment

-- Không dùng discriminator string làm entity type literal.
where type(p) = 'CARD'
```

Trong mapping `@DiscriminatorValue("CARD")`, chuỗi `"CARD"` là giá trị DB lưu cho subtype; query JPQL tiêu chuẩn vẫn dựa trên **entity type**, không phụ thuộc việc discriminator column được đặt tên hay chứa chuỗi nào.

### 4.1. `TYPE` dùng để kiểm tra kiểu cụ thể

```java
List<Payment> cards = em.createQuery(
        "select p from Payment p " +
        "where type(p) = CardPayment",
        Payment.class)
    .getResultList();
```

Kết quả có static Java type là `List<Payment>` theo `TypedQuery<Payment>`, nhưng các entity thỏa điều kiện có runtime entity type tương ứng `CardPayment`.

Nếu muốn method công khai kiểu `CardPayment`, query trực tiếp từ subtype thường rõ ràng hơn:

```java
List<CardPayment> cards = em.createQuery(
        "select c from CardPayment c",
        CardPayment.class)
    .getResultList();
```

Lựa chọn không chỉ là vấn đề hiệu năng; còn liên quan **hợp đồng kiểu của repository**.

### 4.2. `TYPE` có thể dùng với `IN`

```java
List<Payment> nonWallet = em.createQuery(
        "select p from Payment p " +
        "where type(p) in (CardPayment, BankTransferPayment) " +
        "order by p.createdAt desc, p.id desc",
        Payment.class)
    .getResultList();
```

Query này lọc tập hợp các entity type được liệt kê. Nó hữu ích khi báo cáo chỉ cho phép một số payment channels.

Đừng suy ra rằng `IN` ở đây là phép so sánh chuỗi với discriminator:

```sql
-- Không phải cách viết entity type literal của JPQL:
where type(p) in ('CARD', 'BANK')
```

### 4.3. `TYPE` với điều kiện phủ định

```java
List<Payment> others = em.createQuery(
        "select p from Payment p " +
        "where type(p) <> WalletPayment",
        Payment.class)
    .getResultList();
```

Query lấy những payment không có kiểu thực tế là `WalletPayment`. Nhưng cần lưu ý khi hierarchy mở rộng: nếu sau này thêm `CryptoPayment`, query phủ định `WalletPayment` cũng có thể tự động lấy thêm kiểu mới, dù báo cáo ban đầu chỉ định card và bank.

Khi nghiệp vụ chỉ cho phép **một tập subtype hữu hạn**, `IN (CardPayment, BankTransferPayment)` diễn đạt ý định rõ hơn `<> WalletPayment`.

## 5. `TYPE` với tham số kiểu entity

Không phải lúc nào service cũng cố định subtype trong chuỗi JPQL. Có thể yêu cầu loại thanh toán từ một filter được kiểm soát:

```java
public List<Payment> findByEntityType(
        EntityManager em,
        Class<? extends Payment> paymentType) {

    return em.createQuery(
            "select p from Payment p " +
            "where type(p) = :paymentType " +
            "order by p.id",
            Payment.class)
        .setParameter("paymentType", paymentType)
        .getResultList();
}
```

Ví dụ:

```java
List<Payment> cards = findByEntityType(em, CardPayment.class);
List<Payment> banks = findByEntityType(
    em, BankTransferPayment.class);
```

Đây là cách tham số hóa **giá trị kiểu entity** của `TYPE` theo API JPA phù hợp. Phải truyền một Java entity class được mapping; không truyền một Java class không phải entity hoặc chuỗi tùy ý rồi kỳ vọng provider nhận là kiểu entity hợp lệ.

### 5.1. Không nối tên class đến từ request trực tiếp vào JPQL

Tránh:

```java
String query = "select p from Payment p where type(p) = " + userInput;
```

Làm vậy trộn dữ liệu bên ngoài vào cú pháp JPQL, gây rủi ro injection hoặc query hỏng. Nếu ứng dụng cần filter theo lựa chọn của người dùng, sử dụng whitelist:

```java
public Class<? extends Payment> resolvePaymentType(String input) {
    return switch (input) {
        case "card" -> CardPayment.class;
        case "bank" -> BankTransferPayment.class;
        case "wallet" -> WalletPayment.class;
        default -> throw new IllegalArgumentException(
            "Unsupported payment type");
    };
}
```

Sau đó truyền `Class` đã được xác định vào named parameter. Đừng cho client chọn mọi class trong classpath hoặc mọi entity name.

### 5.2. `TYPE` không phải `Class.forName()`

`TYPE(p)` là biểu thức JPQL trên **entity type**, không phải reflection API của JVM. Provider chuyển nó thành điều kiện SQL thích hợp với inheritance strategy. Dùng `Class.forName(userInput)` để tìm Java class không tự xác định được entity nào có quyền truy vấn và không thay cho chính sách validation/authorization.

## 6. Kiểu thực tế và quy tắc kế thừa nhiều tầng

Giả sử có thêm:

```java
@Entity
@DiscriminatorValue("PREMIUM_CARD")
public class PremiumCardPayment extends CardPayment {
    private String loyaltyTier;

    protected PremiumCardPayment() {}
}
```

Hierarchy:

```text
Payment
  ├── CardPayment
  │     └── PremiumCardPayment
  ├── BankTransferPayment
  └── WalletPayment
```

Ý nghĩa quan trọng:

- `from Payment p` là **polymorphic root**: bao gồm các concrete subtype trong hierarchy.
- `from CardPayment c` cũng có tính đa hình đối với các entity subtype của `CardPayment`, nếu có.
- `TYPE(p) = CardPayment` kiểm tra **kiểu entity thực tế**; một instance có kiểu thực tế `PremiumCardPayment` không có TYPE bằng `CardPayment`.
- `TREAT(p AS CardPayment)` có ý nghĩa downcast tới `CardPayment`, nên về mô hình kiểu nó áp dụng được cho instance `CardPayment` và subtype của nó như `PremiumCardPayment`.

Đừng dùng `TYPE(p) = CardPayment` khi nghiệp vụ thật sự là “mọi loại thanh toán có thể được xem là CardPayment, kể cả premium”. Trong hierarchy sâu, **so sánh kiểu chính xác** và **kiểm tra thuộc nhánh kế thừa** là hai ý tưởng khác nhau.

Một giải pháp rõ về mặt nghiệp vụ có thể là query từ root subtype:

```java
List<CardPayment> cardsIncludingPremium = em.createQuery(
        "select c from CardPayment c",
        CardPayment.class)
    .getResultList();
```

Nếu cần kết hợp root `Payment` với trường riêng subtype hoặc nhiều subtype, dùng `TREAT` phù hợp với cách provider biểu diễn sự thu hẹp kiểu trong JPQL.

## 7. `TREAT` là gì?

`TREAT` cho phép downcast một biểu thức entity/path trong JPQL tới subtype:

```sql
TREAT(path_expression AS Subtype)
```

Ví dụ:

```sql
select p
from Payment p
where treat(p as CardPayment).cardBrand = :brand
```

`Payment` không có thuộc tính `cardBrand`. Không thể viết:

```sql
-- Sai vì p được khai báo dưới kiểu Payment.
select p from Payment p where p.cardBrand = :brand
```

`TREAT(p AS CardPayment)` biểu diễn `p` như một `CardPayment` để JPQL có thể đi tiếp tới `.cardBrand`. Điều kiện WHERE sau đó chỉ giữ các kết quả thỏa giá trị brand.

### 7.1. `TREAT` không chuyển entity thành loại khác

`TREAT` là thao tác **thu hẹp kiểu biểu thức truy vấn**, không phải:

- Lệnh tạo một `CardPayment` mới từ một `BankTransferPayment`.
- Migration đổi discriminator của bản ghi hiện tại.
- Một setter giúp sửa class Java của object.
- Chỉ dẫn update database.

Entity vẫn giữ runtime type/persistence identity thực tế của nó. Không thể đổi payment “BANK” thành “CARD” bằng một câu `TREAT`.

### 7.2. `TREAT` không phải cast kiểu scalar

Ví dụ chuyển `String` sang `Integer` hoặc đổi `BigDecimal` sang chuỗi SQL không phải mục tiêu của `TREAT`.

```sql
-- Không dùng TREAT để ép số sang chuỗi.
-- TREAT dành cho subtype entity trong inheritance mapping.
```

Một số JPA provider có các hàm cast scalar riêng hoặc khả năng `CAST` theo API/phiên bản; đừng đánh đồng chúng với downcast entity inheritance.

## 8. `TREAT` truy cập thuộc tính chỉ có trên subtype

Đặt bài toán: tìm tất cả payment mà authorization code bằng giá trị do hệ thống đối soát cung cấp.

JPQL:

```java
List<Payment> payments = em.createQuery(
        "select p from Payment p " +
        "where treat(p as CardPayment).authorizationCode = :code",
        Payment.class)
    .setParameter("code", "A-123")
    .getResultList();
```

Ý nghĩa:

1. Root query `Payment p` đại diện cho hierarchy.
2. `TREAT(p AS CardPayment)` thu hẹp type của `p` thành `CardPayment`.
3. `authorizationCode` là field persistent riêng của subtype.
4. Điều kiện lọc những payment có giá trị phù hợp.

Với SQL theo `SINGLE_TABLE`, provider thường có thể dùng discriminator hoặc một biểu thức/điều kiện tương đương kết hợp cột `authorization_code`. Nhưng đừng yêu cầu ứng dụng phải thấy chính xác chuỗi SQL nào nếu không cố tình dùng một provider cụ thể.

### 8.1. Khi subtype field có thể null

Giả sử một `CardPayment` chưa nhận được `authorizationCode` nên field là null.

```sql
where treat(p as CardPayment).authorizationCode = :code
```

Điều kiện equality không khớp null theo logic SQL thông thường. Không thể suy luận chỉ từ **số kết quả bằng 0** rằng database không có `CardPayment` nào; có thể có card payments nhưng authorization code chưa được cấp.

Nếu muốn tìm những card payments chưa có authorization:

```java
List<Payment> pendingCards = em.createQuery(
        "select p from Payment p " +
        "where type(p) = CardPayment " +
        "and treat(p as CardPayment).authorizationCode is null",
        Payment.class)
    .getResultList();
```

Ở đây, `TYPE` nói rõ yêu cầu chỉ là `CardPayment`; `TREAT` cho phép xem thuộc tính riêng `authorizationCode` và kiểm tra null. Việc kết hợp hai biểu thức có thể giúp tránh hiểu nhầm “null vì không đúng subtype” với “null vì thuộc tính thật sự chưa có giá trị”, nhất là trong các điều kiện `IS NULL` phức tạp.

### 8.2. Kết hợp nhiều điều kiện chung và riêng

```java
List<Payment> results = em.createQuery(
        "select p from Payment p " +
        "where p.status = :status " +
        "and p.amount >= :minimum " +
        "and treat(p as CardPayment).cardBrand = :brand " +
        "order by p.createdAt desc, p.id desc",
        Payment.class)
    .setParameter("status", PaymentStatus.SUCCEEDED)
    .setParameter("minimum", new BigDecimal("100.00"))
    .setParameter("brand", "VISA")
    .getResultList();
```

Các field chung `status`/`amount`/`createdAt` đi qua `Payment p`; field riêng `cardBrand` đi qua `TREAT`. Đây là lợi ích quan trọng khi query kết hợp dữ liệu chung và dữ liệu riêng một subtype.

## 9. Phân biệt `TYPE` và `TREAT` bằng bảng

| Tiêu chí | `TYPE` | `TREAT` |
|---|---|---|
| Mục đích | Xác định/lọc runtime entity type | Thu hẹp đường dẫn xuống subtype |
| Hình thức | `TYPE(p) = CardPayment` | `TREAT(p AS CardPayment).cardBrand` |
| Kết quả khái niệm | Một biểu thức kiểu entity | Một biểu thức/path có type là subtype |
| Dùng để đọc thuộc tính riêng subtype? | **Không trực tiếp** | **Có** |
| Dùng làm điều kiện loại entity? | **Có, rất rõ ràng** | Có thể dùng trong path/join với semantics type restriction |
| Dùng parameter class? | Có thể với `TYPE(p) = :entityType` | Phần `AS Subtype` phải là tên subtype entity, không phải parameter thông thường |
| Có tác dụng đổi class/row trong DB? | Không | Không |
| Có phụ thuộc inheritance mapping? | Có | Có |
| Cần chú ý hierarchy nhiều tầng? | Kiểm tra entity type thực tế | Downcast tới một subtype, có thể phù hợp cả subtype sâu hơn |

Tư duy ngắn:

```text
TYPE = "Entity thực tế có kiểu nào?"
TREAT = "Cho phép đi qua đường dẫn như kiểu con nào?"
```

Ví dụ Java để liên hệ khái niệm:

```java
if (payment instanceof CardPayment card) {
    System.out.println(card.getCardBrand());
}
```

Trong Java, `instanceof` rồi binding/cast giúp truy cập subtype. Trong JPQL, `TYPE` và `TREAT` giúp thể hiện ý tưởng tương tự **ở tầng truy vấn database**, trước khi tải object vào ứng dụng. Tuy vậy, hai hệ thống không có cú pháp hoặc semantics hoàn toàn giống nhau: `TYPE` có phép so sánh kiểu entity thực tế; `TREAT` tham gia quy tắc query-path và join của JPQL.

## 10. `TYPE` trên association entity

Không nhất thiết root query phải là `Payment`. Nếu `PurchaseOrder` chứa:

```java
@OneToMany(mappedBy = "order")
private List<Payment> payments = new ArrayList<>();
```

ta có thể lọc theo subtype của các payment liên quan.

### 10.1. Query các order có ít nhất một CardPayment

```java
List<PurchaseOrder> orders = em.createQuery(
        "select distinct o from PurchaseOrder o " +
        "join o.payments p " +
        "where type(p) = CardPayment",
        PurchaseOrder.class)
    .getResultList();
```

`JOIN o.payments p` duyệt association và tạo alias `p` kiểu `Payment`. `TYPE(p)` kiểm tra type entity thực tế của mỗi payment.

**Vì sao có `DISTINCT`?** Một order có thể chứa nhiều card payments, nên SQL JOIN có thể tạo nhiều row cho cùng order. `select distinct o` diễn đạt yêu cầu “mỗi order xuất hiện một lần”, không phải mỗi payment một dòng trong kết quả.

### 10.2. Query order có transfer theo bank reference

```java
List<PurchaseOrder> orders = em.createQuery(
        "select distinct o from PurchaseOrder o " +
        "join o.payments p " +
        "where type(p) = BankTransferPayment " +
        "and treat(p as BankTransferPayment).bankReference = :ref",
        PurchaseOrder.class)
    .setParameter("ref", "B-456")
    .getResultList();
```

Đây là query kết hợp `TYPE` và `TREAT`:

- `TYPE(p)` lọc subtype yêu cầu.
- `TREAT(p AS BankTransferPayment).bankReference` truy cập field riêng.
- `DISTINCT` tránh trùng root order khi có nhiều payment thỏa điều kiện.

Nếu chỉ cần trả payment, không cần root order, có thể query trực tiếp `BankTransferPayment` để đơn giản hóa.

## 11. `JOIN TREAT`: thu hẹp association ngay tại JOIN

Một dạng cú pháp JPQL nâng cao rất hữu ích là **treat join**:

```sql
join treat(o.payments as CardPayment) card
```

Ý tưởng: association `o.payments` được khai báo là `List<Payment>`. Trong query này, ta chỉ quan tâm các phần tử có thể được xem là `CardPayment`, và alias `card` có type của subtype.

Ví dụ:

```java
List<PurchaseOrder> orders = em.createQuery(
        "select distinct o from PurchaseOrder o " +
        "join treat(o.payments as CardPayment) card " +
        "where card.cardBrand = :brand",
        PurchaseOrder.class)
    .setParameter("brand", "VISA")
    .getResultList();
```

Các điểm cần hiểu:

1. `o.payments` là association tới base entity `Payment`.
2. `TREAT(... AS CardPayment)` thu hẹp association path.
3. `card` là alias của join được xem theo subtype để truy cập `cardBrand`.
4. Inner join chỉ giữ những order có phần tử join phù hợp với điều kiện.
5. `DISTINCT` được dùng vì một order có thể có nhiều card payments.

So sánh với cách viết `TYPE` và `TREAT` riêng:

```sql
select distinct o
from PurchaseOrder o
join o.payments p
where type(p) = CardPayment
  and treat(p as CardPayment).cardBrand = :brand
```

Hai cách có thể diễn đạt cùng nhu cầu đối với hierarchy đơn giản, nhưng không nên mặc định provider luôn tạo SQL giống hệt nhau hoặc mọi tổ hợp subtype/LEFT JOIN đều có cùng hành vi trong các phiên bản provider. Khi truy vấn phức tạp, kiểm tra semantics và SQL trên môi trường thực tế trong bước kiểm thử tích hợp.

### 11.1. Không phải downcast mọi collection đều đúng

`TREAT(o.payments AS CardPayment)` chỉ có ý nghĩa khi element type của `o.payments` là một entity base mà `CardPayment` thật sự là subtype. Nếu association là `List<String>` hoặc `List<PaymentMethodCode>` (enum), không thể dùng `TREAT` để biến chuỗi/enum thành entity subtype.

### 11.2. Dùng join alias để tránh lặp biểu thức

Không nên làm query dài với nhiều lần viết:

```sql
treat(p as CardPayment).cardBrand
treat(p as CardPayment).authorizationCode
treat(p as CardPayment).someOtherField
```

nếu một treat join rõ ràng có thể cung cấp alias:

```sql
join treat(o.payments as CardPayment) card
where card.cardBrand = :brand
  and card.authorizationCode = :code
```

Alias giúp query dễ đọc hơn và cho phép người đọc nhìn thấy kiểu chuyên biệt ngay tại phần FROM/JOIN.

## 12. INNER JOIN và LEFT JOIN với `TREAT`

Khi query trên association, loại JOIN ảnh hưởng cardinality:

- **INNER JOIN**: chỉ giữ root có matching association rows.
- **LEFT JOIN**: cho phép giữ root ngay cả khi không có association row phù hợp với điều kiện JOIN, nhưng các điều kiện WHERE trên alias có thể loại bỏ root đó.

Ví dụ:

```sql
select o
from PurchaseOrder o
left join treat(o.payments as CardPayment) card
```

Ý tưởng là cho phép giữ những order không có card payments. Nhưng nếu thêm:

```sql
where card.cardBrand = :brand
```

thì những order có `card` null không thỏa điều kiện, và kết quả thường gần với inner join về mặt root được giữ.

### 12.1. Muốn giữ order không có card payment thì phải nói rõ

Một biểu thức:

```sql
where card.id is null
```

có thể được dùng trong các trường hợp left join để tìm root không có phần tử join phù hợp. Nhưng **điều kiện join và cách TREAT được diễn dịch** phải được xác nhận với query thực tế, nhất là khi inheritance strategy tạo nhiều bảng và query có additional predicates.

Với bài toán “order không có CardPayment”, cách biểu đạt thường dễ suy luận và ít phụ thuộc cách tối ưu JOIN hơn là `NOT EXISTS`:

```java
List<PurchaseOrder> withoutCards = em.createQuery(
        "select o from PurchaseOrder o " +
        "where not exists (" +
        "  select p.id from Payment p " +
        "  where p.order = o and type(p) = CardPayment" +
        ")",
        PurchaseOrder.class)
    .getResultList();
```

Đây là cách kết hợp subquery với `TYPE` để diễn đạt **không tồn tại một payment thuộc subtype cụ thể** mà không phụ thuộc vào cách lọc alias của `LEFT JOIN TREAT`.

### 12.2. `ON` trong JOIN và `WHERE` không giống nhau

Khi cần giữ outer rows, khác biệt giữa filter trong `JOIN ON` và filter trong `WHERE` rất quan trọng.

Ví dụ về ý tưởng:

```sql
left join o.payments p on type(p) = CardPayment
```

phân biệt với:

```sql
left join o.payments p
where type(p) = CardPayment
```

Vế `WHERE` có thể loại những root không có payment phù hợp; `ON` kiểm soát match của join và giữ outer root theo semantics left join. Những kết hợp chi tiết giữa `TREAT`, `ON` và alias cần được chọn sao cho yêu cầu “có/không có phần tử” được thể hiện rõ và portable với Jakarta Persistence version đang dùng.

## 13. Lọc theo kiểu cụ thể hay theo khả năng downcast?

Trong hierarchy đơn giản chỉ có ba concrete subtype, `TYPE(p) = CardPayment` và query trên `CardPayment` có thể trả cùng tập entity card. Nhưng khi thêm subtype sâu như `PremiumCardPayment`, cần phân biệt:

```text
                 Payment
                    |
              CardPayment
                    |
           PremiumCardPayment
```

Tình huống:

1. **Chỉ đúng kiểu CardPayment**, không lấy PremiumCardPayment: yêu cầu kiểm tra type chính xác.
2. **Mọi payment thuộc nhánh CardPayment**, bao gồm Premium: query polymorphic từ `CardPayment` hoặc downcast phù hợp.
3. **Bất kỳ Payment có trường cardBrand khớp**, trong đó field chỉ có ở CardPayment và các subtype của nó: có thể dùng `TREAT`.

### 13.1. Cần lọc subtype chính xác trong nhánh

```java
List<Payment> onlyBaseCard = em.createQuery(
        "select p from Payment p " +
        "where type(p) = CardPayment",
        Payment.class)
    .getResultList();
```

### 13.2. Cần toàn bộ nhánh

```java
List<CardPayment> allCardFamily = em.createQuery(
        "select c from CardPayment c",
        CardPayment.class)
    .getResultList();
```

Hoặc, khi query root phải là `Payment` vì còn nhiều điều kiện chung:

```java
List<Payment> allCardFamily = em.createQuery(
        "select p from Payment p " +
        "where treat(p as CardPayment).cardBrand = :brand",
        Payment.class)
    .setParameter("brand", "VISA")
    .getResultList();
```

Cách thứ hai biểu diễn **điều kiện trên thuộc tính subtype** chứ không phải một phép kiểm tra kind tổng quát. Nếu muốn “mọi CardPayment dù cardBrand null”, query polymorphic trực tiếp từ `CardPayment` thường rõ ràng hơn.

## 14. `TYPE` trong SELECT và phân nhóm

Ngoài `WHERE`, biểu thức `TYPE` có thể được sử dụng để lấy thông tin kiểu entity.

Ví dụ:

```java
List<Class> types = em.createQuery(
        "select type(p) from Payment p",
        Class.class)
    .getResultList();
```

Giá trị biểu thức type là entity type; ứng dụng nhận thông tin kiểu Java của entity theo mapping. Khi định dạng kết quả API, thường không nên trả nguyên một `Class` object đến client; hãy chuyển sang enum/string nghiệp vụ ổn định.

### 14.1. Trả nhãn thân thiện với client

Ví dụ:

```java
public String toApiPaymentKind(Class<?> entityType) {
    if (entityType == CardPayment.class) return "card";
    if (entityType == BankTransferPayment.class) return "bank";
    if (entityType == WalletPayment.class) return "wallet";
    return "other";
}
```

Khi hierarchy có subtype sâu, quyết định dùng `==` (exact class) hay `isAssignableFrom` (cùng nhánh inheritance) theo nghiệp vụ, không tự trộn hai khái niệm.

### 14.2. Thống kê theo entity type

Một nhu cầu thường gặp là đếm số thanh toán theo từng loại. Có thể cân nhắc:

```sql
select type(p), count(p)
from Payment p
group by type(p)
```

Với provider/JPQL version hỗ trợ cách group theo biểu thức entity type này, query trả mỗi nhóm tương ứng một type và số lượng. Khi cần portability cao hoặc gặp hạn chế GROUP BY của provider, một cách rõ ràng khác là chạy các count query cho từng entity type:

```java
Long cardCount = em.createQuery(
        "select count(p) from Payment p " +
        "where type(p) = CardPayment",
        Long.class)
    .getSingleResult();

Long bankCount = em.createQuery(
        "select count(p) from Payment p " +
        "where type(p) = BankTransferPayment",
        Long.class)
    .getSingleResult();
```

**Lưu ý:** `COUNT` không có `GROUP BY` trả một kết quả số lượng, kể cả khi không có entity matching. Đối với query group by, số nhóm có thể là 0..N nên dùng `getResultList()`, không dùng `getSingleResult()` nếu không có ràng buộc chỉ một nhóm.

## 15. `TREAT` trên đường dẫn singular association

Không phải quan hệ nào cũng là collection. Giả sử `Refund` tham chiếu một payment bất kỳ:

```java
@Entity
public class Refund {
    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    private Payment payment;

    protected Refund() {}
}
```

`Refund.payment` có static type `Payment`. Nếu muốn tìm refund của card payment có card brand VISA:

```java
List<Refund> refunds = em.createQuery(
        "select r from Refund r " +
        "where treat(r.payment as CardPayment).cardBrand = :brand",
        Refund.class)
    .setParameter("brand", "VISA")
    .getResultList();
```

Ý tưởng:

- Đường dẫn `r.payment` là association tới base entity `Payment`.
- `TREAT(r.payment AS CardPayment)` thu hẹp type tại query.
- Ta truy cập `cardBrand` mà không cần tải tất cả Refund và tự `instanceof` sau đó.

Nếu provider/phiên bản có giới hạn với downcast singular path, có thể diễn đạt query bằng explicit join và `TYPE`:

```java
List<Refund> refunds = em.createQuery(
        "select r from Refund r " +
        "join r.payment p " +
        "where type(p) = CardPayment " +
        "and treat(p as CardPayment).cardBrand = :brand",
        Refund.class)
    .setParameter("brand", "VISA")
    .getResultList();
```

Không dùng `TREAT` để cast một `@ManyToOne` sang một class **không kế thừa từ target entity của association**. JPA downcast phải hợp lệ trong entity inheritance hierarchy.

## 16. `TREAT` trong SELECT: đừng coi non-matching subtype là object mới

Về mặt biểu thức, `TREAT` có thể xuất hiện ở những vị trí được ngữ pháp phiên bản JPA cho phép. Tuy nhiên, nếu query chọn trực tiếp biểu thức downcast và một số root entity **không phải subtype**, semantics của non-matching type, `null` và cách provider biến đổi query có thể phức tạp hơn cách dùng `TREAT` trong điều kiện WHERE.

Thay vì cố khai thác các kết quả null khó hiểu, hãy viết query nêu rõ tập mong muốn:

```java
List<CardPayment> cards = em.createQuery(
        "select c from CardPayment c " +
        "where c.cardBrand = :brand",
        CardPayment.class)
    .setParameter("brand", "VISA")
    .getResultList();
```

Hoặc nếu buộc dùng root `Payment`, dùng `TYPE`/`TREAT` để filter rồi lấy những trường cần thiết:

```java
List<String> authorizationCodes = em.createQuery(
        "select treat(p as CardPayment).authorizationCode " +
        "from Payment p " +
        "where type(p) = CardPayment " +
        "and treat(p as CardPayment).authorizationCode is not null",
        String.class)
    .getResultList();
```

Ví dụ làm rõ cả **loại entity** và **điều kiện về thuộc tính**. Nếu chỉ cần danh sách codes từ card, query trực tiếp `CardPayment` còn ngắn hơn.

## 17. Chọn entity hay DTO projection?

Một query đa hình có thể trả `Payment` managed entities:

```java
List<Payment> payments = em.createQuery(
        "select p from Payment p " +
        "order by p.createdAt desc",
        Payment.class)
    .setMaxResults(50)
    .getResultList();
```

Khi chuẩn bị REST response, không nhất thiết trả nguyên object graph. Ta có thể chọn DTO với field chung:

```java
package example.api;

import java.math.BigDecimal;
import java.time.Instant;

public record PaymentRow(
    Long id,
    BigDecimal amount,
    Instant createdAt
) {}
```

```java
List<PaymentRow> rows = em.createQuery(
        "select new example.api.PaymentRow(" +
        "  p.id, p.amount, p.createdAt" +
        ") " +
        "from Payment p " +
        "where p.status = :status " +
        "order by p.createdAt desc, p.id desc",
        PaymentRow.class)
    .setParameter("status", PaymentStatus.SUCCEEDED)
    .setMaxResults(50)
    .getResultList();
```

DTO không phải entity managed. Nếu muốn một response chứa **loại thanh toán** và các trường chuyên biệt, có một số thiết kế:

- Query `TYPE` rồi map entity type thành API enum/string.
- Query nhiều subtype theo use case và ánh xạ mỗi subtype sang DTO riêng.
- Dùng DTO chung có field tùy chọn, nhưng phải kiểm tra tình huống null và không để schema API phản ánh trực tiếp internal discriminator.
- Với dashboard nhiều trường subtype, cân nhắc query projection theo nhu cầu thực tế thay vì tải toàn bộ graph.

Không nên phát tán tên Java class hoặc Hibernate discriminator như hợp đồng API công khai nếu client cần một mã nghiệp vụ ổn định.

## 18. `TREAT` không thay thế `instanceof` trong Java

Sau một polymorphic query:

```java
List<Payment> payments = em.createQuery(
        "select p from Payment p",
        Payment.class)
    .getResultList();
```

Ta có thể dùng Java pattern matching khi xử lý mỗi entity:

```java
for (Payment payment : payments) {
    if (payment instanceof CardPayment card) {
        System.out.println(card.getCardBrand());
    } else if (payment instanceof BankTransferPayment bank) {
        System.out.println(bank.getBankReference());
    }
}
```

Điều này **không sai** nếu ứng dụng thực sự cần tải và xử lý tất cả payments. Nhưng nếu chỉ muốn card payments hoặc chỉ cần bank references, để DB lọc trước thường tiết kiệm hơn:

```java
List<BankTransferPayment> transfers = em.createQuery(
        "select p from BankTransferPayment p " +
        "where p.bankReference = :ref",
        BankTransferPayment.class)
    .setParameter("ref", "B-456")
    .getResultList();
```

`TYPE`/`TREAT` giải quyết chọn dữ liệu **ở JPQL/database layer**; `instanceof` giải quyết logic trên object **đã được đưa vào JVM**. Chọn vị trí xử lý dựa theo kích thước dữ liệu và công việc thực tế.

### 18.1. Proxy và Java class

Một managed association lazy có thể được biểu diễn bằng proxy hoặc cơ chế lazy loading khác của provider. Khi debugging, `payment.getClass()` không phải lúc nào cũng là cách portable nhất để suy luận subtype entity, vì provider có thể sử dụng class proxy/enhancement.

Trong JPQL, `TYPE(p)` dựa trên **entity type trong mô hình persistence**, không phải thao tác đọc tên class bytecode của proxy được giữ trong biến Java. Đừng xây query bằng cách so sánh chuỗi `getClass().getSimpleName()` với tên discriminator.

## 19. `@MappedSuperclass` không phải polymorphic query root

Một nhầm lẫn thường gặp là kế thừa Java giống kế thừa entity JPA.

Ví dụ:

```java
@MappedSuperclass
public abstract class AuditedRecord {
    private Instant createdAt;
}
```

```java
@Entity
public class Product extends AuditedRecord {
    @Id
    private Long id;
}

@Entity
public class Invoice extends AuditedRecord {
    @Id
    private Long id;
}
```

`AuditedRecord` là mapped superclass: các mapping thuộc tính có thể được các subclass entity thừa hưởng, nhưng bản thân nó **không phải entity** và không có polymorphic query root theo cách:

```sql
-- Không hợp lệ như query entity root khi AuditedRecord chỉ @MappedSuperclass:
select a from AuditedRecord a
```

Vì không có một entity hierarchy với `AuditedRecord` làm entity root, không thể tự động dùng `TYPE(a)` hoặc `TREAT(a AS Product)` để query mọi entity kế thừa Java class đó.

Nếu nghiệp vụ thật sự yêu cầu query polymorphic qua base type, cần thiết kế base type là `@Entity` và chọn inheritance strategy phù hợp, hoặc thiết kế query riêng cho các entity không thuộc cùng hierarchy.

### 19.1. Interface Java không tự là entity hierarchy

Giả sử `CardPayment` và `BankTransferPayment` cùng implement:

```java
public interface Chargeable {
    BigDecimal getAmount();
}
```

Điều này không tự cho phép:

```sql
select c from Chargeable c
```

vì `Chargeable` là Java interface, không phải entity name của một hierarchy. Một số provider có tiện ích truy vấn interface riêng, nhưng đó không phải quy tắc JPQL chuẩn thay thế entity inheritance.

## 20. Ba chiến lược inheritance ảnh hưởng cách provider sinh SQL

JPA có ba chiến lược inheritance entity phổ biến:

1. `SINGLE_TABLE`
2. `JOINED`
3. `TABLE_PER_CLASS`

`TYPE` và `TREAT` là **biểu thức mức JPQL**, nhưng cách provider triển khai xuống SQL thay đổi tùy schema.

### 20.1. `SINGLE_TABLE`

```java
@Entity
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(name = "payment_kind")
public abstract class Payment { ... }
```

Đặc điểm:

- Một bảng chứa state chung và các cột của subtype.
- Thường có discriminator xác định loại entity của mỗi row.
- `TYPE` có thể được dịch thành điều kiện trên discriminator.
- `TREAT` đọc các cột chuyên biệt trong cùng bảng (kết hợp điều kiện type phù hợp).
- Các cột chỉ có ở một subtype thường cần cho phép null đối với các row thuộc subtype khác.

SQL **minh họa ý tưởng**:

```sql
SELECT id, amount, status
FROM payments
WHERE payment_kind = 'CARD';
```

Không coi SQL minh họa này là SQL bắt buộc do mọi JPA provider sinh; provider còn có thể bổ sung cột version, discriminator hoặc các expression khác.

### 20.2. `JOINED`

Thay mapping:

```java
@Entity
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class Payment { ... }
```

Schema có thể là:

```text
payments(id PK, amount, status, ...)
card_payments(id PK/FK -> payments.id, card_brand, authorization_code)
bank_transfer_payments(id PK/FK -> payments.id, bank_reference)
wallet_payments(id PK/FK -> payments.id, provider_code)
```

Khi query `from Payment p`, provider cần xác định runtime subtype và có thể phải JOIN các subtype tables hoặc dùng discriminator nếu đã cấu hình. `TREAT(p AS CardPayment).cardBrand` có thể yêu cầu truy cập `card_payments`.

SQL ý tưởng:

```sql
SELECT p.id, p.amount, c.card_brand
FROM payments p
JOIN card_payments c ON c.id = p.id
WHERE c.card_brand = ?;
```

**Không phải mọi query đều cần JOIN toàn bộ subtype tables**. Provider có thể tối ưu theo thuộc tính cần đọc, chiến lược fetch và metadata hierarchy. Nhưng cần biết rằng `TREAT` với JOINED có thể làm query kế thừa phức tạp hơn so với chỉ đọc base fields.

### 20.3. `TABLE_PER_CLASS`

```java
@Entity
@Inheritance(strategy = InheritanceType.TABLE_PER_CLASS)
public abstract class Payment { ... }
```

Mỗi concrete subclass có bảng riêng, chứa các cột kế thừa cần thiết. Query polymorphic trên base type có thể cần kết hợp dữ liệu từ nhiều bảng, thường bằng SQL `UNION` hoặc một kế hoạch tương đương.

SQL minh họa:

```sql
SELECT id, amount, 'CARD' AS payment_kind
FROM card_payments
UNION ALL
SELECT id, amount, 'BANK' AS payment_kind
FROM bank_transfer_payments;
```

Ví dụ chỉ minh họa cách gom hai subtype; hệ thống thực tế còn wallet và các cột/kiểu kết quả phải tương thích, provider quyết định truy vấn cụ thể.

### 20.4. Ma trận thiết kế

| Tiêu chí | `SINGLE_TABLE` | `JOINED` | `TABLE_PER_CLASS` |
|---|---|---|---|
| Lưu state hierarchy | Một bảng | Base table + subtype tables | Bảng riêng cho concrete class |
| Query polymorphic root | Thường thuận tiện | Có thể cần JOIN | Có thể cần UNION |
| `TYPE` | Thường dùng discriminator | Phụ thuộc discriminator/join strategy | Phụ thuộc table branch/type mapping |
| `TREAT` lấy field subtype | Cột trong bảng chung | JOIN tới subtype table | Điều kiện trên branch/bảng subtype |
| Constraint subtype field | Cần chú ý nhiều cột nullable | Có thể đặt ở bảng subtype | Đặt riêng theo concrete table |
| Trade-off | Bảng rộng và nhiều null | Nhiều join | Polymorphic query và ID/constraint phức tạp |

Không chọn inheritance strategy chỉ để một biểu thức `TYPE` đơn giản hơn. Quyết định phải tính tới schema, dữ liệu lớn, write patterns, query patterns, ràng buộc dữ liệu và khả năng phát triển hierarchy.

## 21. `TYPE` và discriminator: hai cấp độ abstraction khác nhau

Một ý dễ nhầm:

```java
@DiscriminatorValue("CARD")
public class CardPayment extends Payment {}
```

Nhưng JPQL dùng:

```sql
where type(p) = CardPayment
```

chứ không dùng:

```sql
where p.payment_kind = 'CARD'
```

Lý do:

- `payment_kind` là cột vật lý của database, không nhất thiết là Java persistent attribute của `Payment`.
- `TYPE` là biểu thức thuộc query language, để provider quyết định cách nhận diện entity type.
- `@DiscriminatorValue` có thể thay đổi trong migration trong khi ý nghĩa business của CardPayment vẫn giữ nguyên.
- `JOINED` hoặc `TABLE_PER_CLASS` có thể không dựa trên cùng cơ chế discriminator column như `SINGLE_TABLE`.

Nếu cố mapping trực tiếp discriminator column thành một mutable field trong entity, có thể gây xung đột giữa inheritance discriminator do provider quản lý và giá trị application tự thay đổi. Không thiết kế business flow bằng cách “update field discriminator rồi entity đổi class”.

### 21.1. Có nên đặt tên entity khác class name?

Có thể khai báo:

```java
@Entity(name = "CardCharge")
@DiscriminatorValue("CARD")
public class CardPayment extends Payment { ... }
```

Khi đó, tên entity được dùng trong JPQL là `CardCharge`, không còn nhất thiết là `CardPayment`:

```sql
select p from Payment p where type(p) = CardCharge
```

Đồng thời, Java class parameter có thể vẫn là `CardPayment.class` vì đó là class thực của entity. Đây là lý do cần phân biệt **entity name**, **Java class name** và **discriminator value**.

## 22. Kết hợp `TYPE`, `TREAT` với điều kiện động

Một hệ thống tìm kiếm payment có thể nhận:

```text
status = SUCCEEDED
paymentKind = card | bank | wallet | all
cardBrand = VISA (optional)
bankReference = B-456 (optional)
```

Đừng viết một chuỗi JPQL khổng lồ có mọi loại subtype field rồi cố gán mọi parameter null. Thay vào đó, chọn query shape theo loại filter.

### 22.1. Chỉ lọc kind

```java
public List<Payment> filterByKind(
        EntityManager em, Class<? extends Payment> type) {

    return em.createQuery(
            "select p from Payment p " +
            "where type(p) = :type " +
            "order by p.createdAt desc, p.id desc",
            Payment.class)
        .setParameter("type", type)
        .setMaxResults(100)
        .getResultList();
}
```

Nếu filter là “all”, hãy dùng query khác **không có điều kiện TYPE**, thay vì tự coi null class parameter là “mọi loại”.

### 22.2. Lọc thuộc tính riêng của thẻ

```java
public List<Payment> filterCardsByBrand(
        EntityManager em, String brand) {

    return em.createQuery(
            "select p from Payment p " +
            "where treat(p as CardPayment).cardBrand = :brand " +
            "order by p.id",
            Payment.class)
        .setParameter("brand", brand)
        .getResultList();
}
```

Hoặc query trực tiếp `CardPayment` nếu service trả đúng kiểu này.

### 22.3. Lọc nhiều subtype với OR

```java
List<Payment> matches = em.createQuery(
        "select p from Payment p " +
        "where (type(p) = CardPayment " +
        "       and treat(p as CardPayment).authorizationCode = :cardCode) " +
        "   or (type(p) = BankTransferPayment " +
        "       and treat(p as BankTransferPayment).bankReference = :bankRef) " +
        "order by p.id",
        Payment.class)
    .setParameter("cardCode", "A-123")
    .setParameter("bankRef", "B-456")
    .getResultList();
```

Cú pháp trên biểu diễn **hai nhánh điều kiện khác nhau**, mỗi nhánh giới hạn type và đọc subtype field. Nếu hierarchy có `PremiumCardPayment`, điều kiện `TYPE(p) = CardPayment` có thể loại nó; cần chọn đúng khái niệm “đúng kiểu” hay “thuộc nhánh” theo nghiệp vụ.

### 22.4. Query phức tạp nên dùng Criteria API?

Nếu có nhiều bộ lọc tùy chọn và cần tránh nối nhiều chuỗi JPQL, Criteria API có thể giúp xây điều kiện có cấu trúc. Tuy nhiên, Criteria API không làm mất đi yêu cầu hiểu chính xác entity inheritance, type narrowing và cardinality; nó chỉ đổi cách diễn đạt query.

## 23. `TYPE` và `TREAT` trong Criteria API

JPQL có các phép tương ứng trong Criteria API.

### 23.1. Kiểm tra entity type

```java
import jakarta.persistence.criteria.*;

CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Payment> cq = cb.createQuery(Payment.class);
Root<Payment> payment = cq.from(Payment.class);

cq.select(payment)
  .where(cb.equal(payment.type(), CardPayment.class));

List<Payment> cards = em.createQuery(cq).getResultList();
```

`payment.type()` biểu diễn entity type expression trong Criteria API. So sánh với `CardPayment.class` tương ứng ý tưởng:

```sql
where TYPE(p) = CardPayment
```

### 23.2. Thu hẹp root bằng `CriteriaBuilder.treat`

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Payment> cq = cb.createQuery(Payment.class);
Root<Payment> root = cq.from(Payment.class);

Root<CardPayment> card = cb.treat(root, CardPayment.class);

cq.select(root)
  .where(cb.equal(card.get("cardBrand"), "VISA"));

List<Payment> cards = em.createQuery(cq).getResultList();
```

`cb.treat(root, CardPayment.class)` biểu diễn downcast của root để truy cập `cardBrand`, tương đương ý tưởng JPQL:

```sql
where treat(p as CardPayment).cardBrand = :brand
```

### 23.3. Thu hẹp JOIN bằng `CriteriaBuilder.treat`

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);

Root<PurchaseOrder> order = cq.from(PurchaseOrder.class);
Join<PurchaseOrder, Payment> payment =
    order.join("payments", JoinType.INNER);

Join<PurchaseOrder, CardPayment> card =
    cb.treat(payment, CardPayment.class);

cq.select(order)
  .distinct(true)
  .where(cb.equal(card.get("cardBrand"), "VISA"));

List<PurchaseOrder> orders = em.createQuery(cq).getResultList();
```

Đây là minh họa Criteria join-based treat; cú pháp cụ thể có thể được biểu diễn bằng typed metamodel nếu dự án sinh JPA static metamodel thay vì dùng chuỗi `"payments"` và `"cardBrand"`. Một số provider có giới hạn với treat trên join hoặc nhiều alias; với hệ thống production, kiểm thử các truy vấn inheritance quan trọng trên provider/database mục tiêu.

### 23.4. JPQL và Criteria chọn cách nào?

| Tiêu chí | JPQL | Criteria API |
|---|---|---|
| Dễ đọc query cố định | Thường rõ ràng, gần SQL | Dài hơn |
| Filter động theo nhiều điều kiện | Phải xây query có chủ đích | Tạo predicates linh hoạt |
| Kiểm tra entity type | `TYPE(p)` | `Path.type()` / `Root.type()` |
| Downcast subtype | `TREAT(... AS Subtype)` | `CriteriaBuilder.treat(...)` |
| Dễ quan sát query logic | Chuỗi câu truy vấn | Cấu trúc object query |
| Portability | Phụ thuộc mức hỗ trợ JPQL của version/provider | Cũng phụ thuộc implementation/version với các phép đặc biệt |

Không nên chọn Criteria chỉ để “query nhanh hơn”: cả hai là cách mô tả query, provider vẫn quyết định SQL và execution plan.

## 24. Repository patterns cho truy vấn đa hình

Một repository có thể chia thành ba nhóm API rõ ràng.

### 24.1. Danh sách thanh toán tổng quát

```java
public List<Payment> findAllSuccessful(
        EntityManager em, int max) {

    if (max < 1 || max > 500) {
        throw new IllegalArgumentException("Invalid max");
    }

    return em.createQuery(
            "select p from Payment p " +
            "where p.status = :status " +
            "order by p.createdAt desc, p.id desc",
            Payment.class)
        .setParameter("status", PaymentStatus.SUCCEEDED)
        .setMaxResults(max)
        .getResultList();
}
```

`Payment` là polymorphic query root, kết quả có thể chứa nhiều subtype.

### 24.2. Danh sách subtype cụ thể

```java
public List<BankTransferPayment> findBankTransfers(
        EntityManager em, String reference) {

    return em.createQuery(
            "select p from BankTransferPayment p " +
            "where p.bankReference = :reference",
            BankTransferPayment.class)
        .setParameter("reference", reference)
        .getResultList();
}
```

Nếu toàn bộ use case thuộc subtype, query thẳng từ subtype tránh không cần thiết phải viết `TYPE`/`TREAT`.

### 24.3. Query root chung có subtype filter linh hoạt

```java
public List<Payment> findByType(
        EntityManager em,
        Class<? extends Payment> type) {

    return em.createQuery(
            "select p from Payment p " +
            "where type(p) = :entityType",
            Payment.class)
        .setParameter("entityType", type)
        .getResultList();
}
```

Đây là nơi `TYPE` hữu ích: một query chung đáp ứng nhiều lựa chọn kiểu entity.

### 24.4. Query root chung nhưng lọc một subtype field

```java
public List<Payment> findByAuthorization(
        EntityManager em, String authorizationCode) {

    return em.createQuery(
            "select p from Payment p " +
            "where treat(p as CardPayment).authorizationCode = :code",
            Payment.class)
        .setParameter("code", authorizationCode)
        .getResultList();
}
```

Đây là nơi `TREAT` cho phép query ở mức root chung nhưng xét thuộc tính subtype.

### 24.5. Phải hiểu cardinality

Nếu mã `authorizationCode` unique theo nghiệp vụ, repository có thể trả `Optional<CardPayment>` hoặc yêu cầu đúng một. Nhưng `TYPE`/`TREAT` **không tự tạo unique constraint**; cần bảo đảm uniqueness trong database và phạm vi tenant/provider.

Nếu authorization code chỉ unique trong từng ngân hàng/processor, query phải có điều kiện processor tương ứng và schema cần unique constraint đúng phạm vi. Không gọi `getSingleResult()` cho điều kiện thực tế có thể trả nhiều card payments.

## 25. Phân trang trong polymorphic query

Một bảng quản trị có hàng triệu payment, gồm nhiều subtype. Không nên:

```java
List<Payment> all = em.createQuery(
    "select p from Payment p",
    Payment.class
).getResultList();
// Rồi lọc instanceof và subList ở Java.
```

Thay vào đó, lọc và phân trang ngay trong JPQL:

```java
public List<Payment> pageByType(
        EntityManager em,
        Class<? extends Payment> type,
        int offset,
        int size) {

    if (offset < 0 || size < 1 || size > 200) {
        throw new IllegalArgumentException("Invalid page");
    }

    return em.createQuery(
            "select p from Payment p " +
            "where type(p) = :type " +
            "order by p.createdAt desc, p.id desc",
            Payment.class)
        .setParameter("type", type)
        .setFirstResult(offset)
        .setMaxResults(size)
        .getResultList();
}
```

`ORDER BY` có tie-breaker `id` để giảm sự không ổn định khi nhiều payment cùng `createdAt`. Với dữ liệu rất lớn và nhiều trang, keyset pagination có thể hiệu quả hơn offset:

```java
List<Payment> nextPage = em.createQuery(
        "select p from Payment p " +
        "where type(p) = :type " +
        "and p.id > :lastId " +
        "order by p.id",
        Payment.class)
    .setParameter("type", CardPayment.class)
    .setParameter("lastId", lastSeenId)
    .setMaxResults(100)
    .getResultList();
```

Ví dụ keyset này dùng ID tăng dần để đơn giản hóa. Nếu cần sort `createdAt DESC, id DESC`, điều kiện keyset phải tương ứng **cả hai giá trị**; không thể chỉ dùng `id > :lastId` mà vẫn giữ đúng thứ tự kết hợp.

### 25.1. `JOIN TREAT` và duplicate roots

Nếu một order có ba `CardPayment` matching, query:

```sql
select o
from PurchaseOrder o
join treat(o.payments as CardPayment) card
where card.cardBrand = :brand
```

có thể tạo nhiều join rows cho cùng order. Nếu cần mỗi order một lần, `select distinct o` là điều kiện quan trọng.

**Không phân trang một collection fetch join lớn như một query parent thường** mà không hiểu SQL row multiplication và giới hạn của provider; có nguy cơ phân trang ở RAM hoặc sai số lượng root thực tế. Thường nên phân trang parent IDs rồi tải dữ liệu liên quan riêng theo batch.

## 26. Hiệu năng của `TYPE` và `TREAT`

Không thể kết luận `TYPE` luôn nhanh hơn `TREAT` hoặc ngược lại nếu không xem inheritance strategy và SQL.

### 26.1. Với `SINGLE_TABLE`

Type filter có thể trở thành điều kiện trên discriminator:

```sql
SELECT p.id, p.amount
FROM payments p
WHERE p.payment_kind = 'CARD'
  AND p.status = 'SUCCEEDED';
```

Nếu báo cáo chủ yếu lọc theo type, status và createdAt, một index phù hợp có thể giúp:

```sql
CREATE INDEX idx_payments_kind_status_created
ON payments(payment_kind, status, created_at);
```

Đây chỉ là ví dụ index; điều kiện sử dụng thực tế còn phụ thuộc selectivity, kích thước bảng, sort direction, RDBMS và execution plan. Không tạo index chỉ vì thấy `TYPE` xuất hiện trong JPQL mà chưa đo workload.

### 26.2. Với `JOINED`

`TREAT` để đọc subtype field có thể khiến SQL phải JOIN subtype table. Nếu query yêu cầu nhiều trường riêng từ nhiều subtype, số join có thể tăng và làm query phức tạp hơn.

Một lựa chọn là query trực tiếp subtype thay vì root:

```java
List<CardPayment> cards = em.createQuery(
        "select c from CardPayment c where c.cardBrand = :brand",
        CardPayment.class)
    .setParameter("brand", "VISA")
    .getResultList();
```

Nó có thể cho SQL đơn giản hơn khi service chỉ quan tâm CardPayment, nhưng không khẳng định **luôn** nhanh hơn: provider, joins, indexes và fetch plan mới quyết định.

### 26.3. Với `TABLE_PER_CLASS`

Polymorphic root query có thể tạo `UNION` qua nhiều subclass tables. Khi số subtype tăng, việc query tất cả có thể tốn chi phí. `TYPE` filter có thể cho provider cơ hội giảm số branch, nhưng mức tối ưu thực tế không được bảo đảm bởi cú pháp Java.

### 26.4. Đo thay vì suy đoán

Khi tối ưu:

1. Bật SQL logging ở môi trường dev/test.
2. Quan sát SQL thực tế của `TYPE` và `TREAT`.
3. Dùng `EXPLAIN`/execution plan của database.
4. Kiểm tra số row, join, sort, index và statement count.
5. So sánh query trên base entity với query trực tiếp subtype.
6. Đo memory của persistence context khi trả managed entity.
7. Dùng DTO projection khi không cần dirty checking.

Khi query bị chậm, đừng lập tức đổi sang Java `instanceof` và tải tất cả bản ghi. Thường vấn đề cần xử lý ở SQL plan, index, fetch strategy hoặc giới hạn dữ liệu.

## 27. Tương thích phiên bản Jakarta Persistence và provider

`TYPE` và `TREAT` là những khái niệm thuộc JPQL/JPA, không phải tên hàm riêng của Hibernate HQL. Tuy nhiên, **phạm vi cú pháp được hỗ trợ, cách xử lý treat join, alias, outer join và kế hoạch SQL** có thể khác nhau giữa các phiên bản provider.

Những nguyên tắc thực hành:

- Dùng `jakarta.persistence` cho các dự án Jakarta Persistence hiện đại; dự án JPA 2.x cũ dùng `javax.persistence`.
- Kiểm tra API/JPA version mà project thực sự phụ thuộc, không chỉ đọc một tài liệu của phiên bản mới nhất.
- Dùng cú pháp chuẩn `TYPE(p)` và `TREAT(path AS Subtype)` thay vì HQL extension khi cần portability.
- Tại query quan trọng có `JOIN TREAT`, `LEFT JOIN TREAT` hoặc nhiều inheritance levels, nên kiểm thử tích hợp với provider và database mục tiêu.
- Không dựa vào chuỗi SQL cụ thể mà Hibernate/EclipseLink sinh ra nếu nghiệp vụ chỉ cần kết quả JPQL theo chuẩn.
- Nếu có provider-specific annotation/hint, ghi rõ chúng là extension thay vì coi là Jakarta Persistence portable.

### 27.1. Hibernate HQL mở rộng khác JPQL

Hibernate HQL có thể hỗ trợ thêm các cú pháp/built-in functions riêng. Đừng lấy một cú pháp HQL đang chạy rồi tự mặc định nó portable trên mọi Jakarta Persistence provider.

Ví dụ, `TYPE` là biểu thức phù hợp để kiểm tra entity type trong JPQL. Nếu gặp code legacy dùng tên property đặc biệt hoặc cú pháp Hibernate-specific để đọc discriminator, nên cân nhắc cách diễn đạt theo `TYPE` khi cần tính portable.

### 27.2. Entity inheritance không đồng nghĩa database inheritance

`@Inheritance` của JPA là mapping từ **Java entity hierarchy** sang relational tables. Nó không yêu cầu database phải có một cơ chế table inheritance độc lập như một số hệ quản trị hỗ trợ. `TYPE` và `TREAT` dựa trên metadata entity của JPA, không dựa vào một operator inheritance tùy RDBMS.

## 28. Những lỗi phổ biến với `TYPE` và `TREAT`

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| JPQL báo unknown entity trong `TYPE(p) = CardPayment` | Tên entity không trùng Java class name do `@Entity(name=...)` hoặc chưa đăng ký entity | Dùng entity name thực sự; kiểm tra persistence unit |
| `TYPE(p) = 'CARD'` lỗi hoặc sai kết quả | Đang so sánh entity type với discriminator string | Dùng `TYPE(p) = CardPayment` |
| `p.cardBrand` không hợp lệ khi `p` là `Payment` | Base entity không khai báo field | Dùng `TREAT(p AS CardPayment).cardBrand` hoặc query subtype |
| Query `TREAT` không ra kết quả | Không có subtype phù hợp hoặc field filter không khớp | Kiểm tra hierarchy, dữ liệu và WHERE |
| Bị mất PremiumCardPayment | Dùng `TYPE(p) = CardPayment` nhưng cần cả nhánh kế thừa | Query từ `CardPayment` hoặc thể hiện semantics nhánh |
| Subtype thêm mới xuất hiện trong query `TYPE <> WalletPayment` | Điều kiện phủ định tự bao gồm type mới | Dùng whitelist `TYPE IN (...)` |
| `LEFT JOIN TREAT` không giữ order như kỳ vọng | Điều kiện WHERE lọc alias null, hoặc ngữ nghĩa treat join phức tạp | Xem lại `ON/WHERE` và dùng `EXISTS/NOT EXISTS` khi thích hợp |
| Dữ liệu order trùng sau JOIN | Một order có nhiều matching payments | `select distinct o` hoặc EXISTS |
| Query đa hình rất chậm trên `JOINED` | Provider cần JOIN subtype tables | Đo SQL/explain; cân nhắc query subtype trực tiếp |
| Query root rất chậm trên `TABLE_PER_CLASS` | Polymorphic UNION nhiều tables | Phân tích plan, filter/limit và cấu trúc hierarchy |
| `TREAT` với `@MappedSuperclass` không chạy | Superclass không phải entity query root | Dùng entity hierarchy thật hoặc query riêng |
| Truy vấn với kiểu lấy từ input lỗi | Input chưa map sang entity class hợp lệ | Whitelist class/entity type |
| `ClassCastException` khi lấy kết quả | `TypedQuery<Payment>` bị ép tùy tiện sang subtype | Dùng query trực tiếp subtype hoặc validate runtime type |
| Cardinality sai sau JOIN TREAT | Một root có nhiều child matching | Hiểu join multiplicity, DISTINCT và result shape |
| SQL logs không có discriminator column như tưởng | Mapping strategy/provider không dùng đúng một cột discriminator | Đọc schema và provider SQL thực tế |

### 28.1. Sai: dùng discriminator value trong JPQL

```sql
-- Sai ở cấp độ entity type:
select p from Payment p where type(p) = 'CARD'
```

Sửa:

```sql
select p from Payment p where type(p) = CardPayment
```

### 28.2. Sai: giả định class name luôn là entity name

```java
@Entity(name = "CardCharge")
public class CardPayment extends Payment { ... }
```

Query entity literal phải theo **entity name**, tức `CardCharge`. `CardPayment.class` là một Java class, còn `"CARD"` là discriminator. Ba tên này không phải một.

### 28.3. Sai: downcast không thuộc hierarchy

```sql
-- Product không kế thừa Payment; đây không phải downcast hợp lệ.
treat(p as Product)
```

`TREAT` chỉ áp dụng khi subtype là loại entity thích hợp trong cùng inheritance hierarchy.

### 28.4. Sai: lọc subtype bằng Java sau khi tải cả bảng

```java
List<Payment> all = em.createQuery(
    "select p from Payment p", Payment.class
).getResultList();

List<CardPayment> cards = all.stream()
    .filter(CardPayment.class::isInstance)
    .map(CardPayment.class::cast)
    .toList();
```

Với tập nhỏ để xử lý nghiệp vụ tổng hợp, cách này có thể chấp nhận. Nhưng nếu chỉ cần cards trong bảng rất lớn, query trực tiếp subtype hoặc lọc bằng `TYPE/TREAT` sẽ tránh nạp nhiều entity không cần thiết.

### 28.5. Sai: dùng `TYPE` để đọc trường subtype

```sql
-- TYPE không biến p thành CardPayment để truy cập cardBrand:
select p from Payment p
where type(p) = CardPayment and p.cardBrand = :brand
```

Sửa bằng `TREAT`:

```sql
select p from Payment p
where type(p) = CardPayment
  and treat(p as CardPayment).cardBrand = :brand
```

Hoặc query trực tiếp từ subtype:

```sql
select c from CardPayment c
where c.cardBrand = :brand
```

## 29. Một ca thực tế: đối soát nhiều kênh thanh toán

Giả sử phòng kế toán cần ba báo cáo:

1. **Tổng số tiền** của mọi thanh toán đã thành công.
2. **Danh sách card payments** từ VISA chưa có authorization code.
3. **Danh sách đơn hàng** có ít nhất một bank transfer mang reference nghi vấn.

### 29.1. Báo cáo chung cho mọi subtype

```java
BigDecimal total = em.createQuery(
        "select sum(p.amount) from Payment p " +
        "where p.status = :status",
        BigDecimal.class)
    .setParameter("status", PaymentStatus.SUCCEEDED)
    .getSingleResult();

if (total == null) {
    total = BigDecimal.ZERO;
}
```

Không cần `TYPE` khi nghiệp vụ lấy **tất cả subtype**. Đó chính là lợi ích của polymorphic root.

### 29.2. Báo cáo card với thuộc tính riêng

```java
List<CardPayment> cards = em.createQuery(
        "select c from CardPayment c " +
        "where c.cardBrand = :brand " +
        "and c.authorizationCode is null " +
        "order by c.createdAt, c.id",
        CardPayment.class)
    .setParameter("brand", "VISA")
    .getResultList();
```

Ở đây query trực tiếp subtype đơn giản nhất. Nếu có phần query dùng base alias và cần trường card thì mới cần `TREAT`.

Tương đương về mục tiêu ở root:

```java
List<Payment> cardsFromRoot = em.createQuery(
        "select p from Payment p " +
        "where type(p) = CardPayment " +
        "and treat(p as CardPayment).cardBrand = :brand " +
        "and treat(p as CardPayment).authorizationCode is null",
        Payment.class)
    .setParameter("brand", "VISA")
    .getResultList();
```

### 29.3. Báo cáo order có bank reference nghi vấn

```java
List<PurchaseOrder> orders = em.createQuery(
        "select distinct o from PurchaseOrder o " +
        "join treat(o.payments as BankTransferPayment) bank " +
        "where bank.bankReference = :reference",
        PurchaseOrder.class)
    .setParameter("reference", "B-456")
    .getResultList();
```

Đây là trường hợp `JOIN TREAT` hữu ích: root cần trả là `PurchaseOrder`, association có kiểu `Payment`, nhưng điều kiện nằm trên subtype field.

Nếu báo cáo còn cần các order **không có** transfer, thiết kế riêng query với `NOT EXISTS` và `TYPE` thay vì tùy tiện đổi join thành `LEFT JOIN` rồi giữ nguyên điều kiện WHERE.

### 29.4. Tại sao không gom tất cả vào một câu JPQL?

Ba báo cáo có result shape khác nhau:

- Một scalar aggregate `BigDecimal`.
- Một danh sách entity `CardPayment`.
- Một danh sách root `PurchaseOrder`.

Ép chúng dùng một query rất phức tạp có thể làm code khó kiểm thử và tăng nguy cơ join multiplication. Nên thiết kế query theo **mục đích và cardinality của kết quả**. `TYPE`/`TREAT` là công cụ để diễn đạt điều kiện đúng, không phải mục tiêu phải có trong mọi câu JPQL.

## 30. Một ca thực tế khác: nhân sự với subtype

Để thấy `TYPE`/`TREAT` không chỉ áp dụng thanh toán, xét:

```text
Employee
  id, name, department
  |
  +-- FullTimeEmployee
  |       annualSalary
  |
  +-- ContractEmployee
          hourlyRate
          contractEndDate
```

Mapping:

```java
@Entity
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class Employee {
    @Id
    private Long id;
    private String name;
}

@Entity
public class FullTimeEmployee extends Employee {
    private BigDecimal annualSalary;
}

@Entity
public class ContractEmployee extends Employee {
    private BigDecimal hourlyRate;
    private LocalDate contractEndDate;
}
```

Truy vấn toàn bộ nhân viên:

```sql
select e from Employee e
```

Truy vấn nhân viên hợp đồng:

```sql
select e from Employee e
where type(e) = ContractEmployee
```

Truy vấn hợp đồng sắp hết hạn:

```sql
select e from Employee e
where treat(e as ContractEmployee).contractEndDate < :cutoff
```

Hoặc:

```sql
select c from ContractEmployee c
where c.contractEndDate < :cutoff
```

Nếu báo cáo cần cả nhân viên full-time và contract nhưng áp dụng điều kiện riêng theo từng subtype, có thể kết hợp `TYPE` và `TREAT` trong các nhánh OR có dấu ngoặc rõ ràng.

### 30.1. Mức độ phù hợp của inheritance

Không phải mọi khác biệt nghiệp vụ đều nên mô hình bằng entity subclasses. Nếu loại hợp đồng chỉ khác một vài giá trị cấu hình và có thể thay đổi thường xuyên, một entity `Employee` với association `ContractPolicy` hoặc strategy/configuration riêng có thể dễ duy trì hơn.

`TYPE` và `TREAT` hữu ích **khi đã có entity inheritance đúng về domain và persistence**. Không nên tạo hierarchy chỉ để được sử dụng hai biểu thức truy vấn này.

## 31. Bài tập thực hành

### Bài 1 — Polymorphic root

Cho `Payment` là abstract entity và ba subtype `CardPayment`, `BankTransferPayment`, `WalletPayment`.

**Yêu cầu:**

1. Viết JPQL trả tất cả payment đã thành công, sắp xếp theo `createdAt DESC` và `id DESC`.
2. Giải thích vì sao kết quả có thể chứa nhiều Java concrete classes.
3. Giải thích vì sao không cần `TYPE` nếu muốn lấy tất cả subtype.

**Gợi ý:**

```sql
select p from Payment p
where p.status = :status
order by p.createdAt desc, p.id desc
```

### Bài 2 — Lọc đúng một entity type

Viết JPQL chỉ lấy `BankTransferPayment` từ root `Payment`.

**Gợi ý:**

```sql
select p from Payment p
where type(p) = BankTransferPayment
```

Sau đó viết query trực tiếp:

```sql
select b from BankTransferPayment b
```

So sánh static Java result type và khả năng tái sử dụng trong repository.

### Bài 3 — Dùng `TREAT` với subtype field

Giả sử `CardPayment` có `cardBrand` và `authorizationCode`. Viết query từ `Payment` để tìm những card payment có brand `VISA`.

**Gợi ý:**

```sql
select p from Payment p
where treat(p as CardPayment).cardBrand = :brand
```

Giải thích vì sao `p.cardBrand` không hợp lệ khi alias `p` có static type `Payment`.

### Bài 4 — Tách null subtype và null field

Một số `CardPayment` chưa có `authorizationCode`. Viết query tìm đúng những card payment đó.

**Gợi ý:**

```sql
select p from Payment p
where type(p) = CardPayment
  and treat(p as CardPayment).authorizationCode is null
```

Giải thích vì sao chỉ dùng `IS NULL` trên một downcast path mà không làm rõ loại entity có thể khiến người đọc hiểu nhầm ý nghĩa của dữ liệu null.

### Bài 5 — `JOIN TREAT`

`PurchaseOrder` có `List<Payment> payments`. Viết query tìm những order có card payments mang `authorizationCode = :code`.

**Gợi ý:**

```sql
select distinct o
from PurchaseOrder o
join treat(o.payments as CardPayment) card
where card.authorizationCode = :code
```

Giải thích vì sao cần `DISTINCT` khi một order có nhiều card payments phù hợp.

### Bài 6 — Không tồn tại subtype

Viết JPQL lấy những order không có `WalletPayment`.

**Gợi ý:**

```sql
select o from PurchaseOrder o
where not exists (
    select p.id from Payment p
    where p.order = o and type(p) = WalletPayment
)
```

Giải thích lợi ích của `NOT EXISTS` trong trường hợp so với tự viết `LEFT JOIN` và điều kiện nullable alias phức tạp.

### Bài 7 — Entity name và discriminator

Thay `CardPayment` thành:

```java
@Entity(name = "CardCharge")
@DiscriminatorValue("CARD")
public class CardPayment extends Payment { ... }
```

**Yêu cầu:** viết đúng entity type literal cho `TYPE` và giải thích ba khái niệm:

1. `CardPayment.class`: Java class.
2. `CardCharge`: JPQL entity name.
3. `CARD`: database discriminator value.

### Bài 8 — Hierarchy nhiều tầng

Thêm `PremiumCardPayment extends CardPayment`.

**Yêu cầu:** phân biệt:

- Query `TYPE(p) = CardPayment`.
- Query `FROM CardPayment c`.
- Query `TREAT(p AS CardPayment).cardBrand = :brand`.

Giải thích query nào đòi **exact runtime entity type** và query nào làm việc với **nhánh subtype**.

### Bài 9 — So sánh inheritance SQL

Ánh xạ cùng hierarchy `Payment` bằng `SINGLE_TABLE` và `JOINED` trên database thử nghiệm.

**Yêu cầu:** so sánh schema và dạng SQL cho:

```sql
select p from Payment p where type(p) = CardPayment
```

```sql
select p from Payment p
where treat(p as CardPayment).cardBrand = :brand
```

Đừng khẳng định SQL giống nhau giữa hai chiến lược; mục tiêu là hiểu điều kiện discriminator so với truy cập subtype table.

### Bài 10 — Criteria API

Tạo hai Criteria queries:

1. Dùng `root.type()` để lọc `CardPayment.class`.
2. Dùng `cb.treat(root, CardPayment.class)` để lọc `cardBrand`.

**Mục tiêu:** liên hệ `TYPE`/`TREAT` với Criteria API, không biến Criteria thành một bài toán domain khác.

### Bài 11 — Phân trang

Truy vấn những `BankTransferPayment` có `status=SUCCEEDED`, lấy 25 kết quả mỗi trang, theo `createdAt DESC` và `id DESC`.

**Yêu cầu:** sử dụng `setFirstResult/setMaxResults`; giải thích tại sao phải có thứ tự xác định và vì sao không nên nạp toàn bộ payments rồi lọc Java `instanceof`.

### Bài 12 — Lựa chọn mô hình

Một hệ thống có hai kiểu invoice chỉ khác thuế suất theo từng quốc gia. Bạn có nhất thiết phải tạo `DomesticInvoice extends Invoice` và `ForeignInvoice extends Invoice` để dùng `TYPE/TREAT` không?

**Gợi ý:** không. Xác định liệu sự khác biệt là **entity identity/behavior/inheritance thực sự** hay chỉ là policy/configuration; nếu chỉ là một trường hợp cấu hình, association hoặc enum/policy model có thể thích hợp hơn.

## 32. Câu hỏi tự kiểm tra

**1. Query `FROM Payment p` có bao gồm các subtype entity không?**

Có, đó là polymorphic query trên một entity root trong hierarchy. Nó có thể trả các concrete subclass phù hợp.

**2. `TYPE(p)` dùng để làm gì?**

Xác định entity type thực tế của một biểu thức entity, thường để lọc hoặc phân loại theo subtype.

**3. `TYPE(p) = CardPayment` có so sánh với chuỗi `"CARD"` không?**

Không. `CardPayment` là entity type literal; `"CARD"` là discriminator value của database trong mapping minh họa.

**4. `TREAT(p AS CardPayment)` làm gì?**

Thu hẹp một biểu thức/path entity về subtype `CardPayment`, cho phép truy cập thuộc tính chỉ subtype đó khai báo.

**5. `TREAT` có đổi một BankTransferPayment thành CardPayment trong DB không?**

Không. Nó chỉ ảnh hưởng cách biểu thức truy vấn được diễn giải.

**6. Nếu `Payment` không khai báo `cardBrand`, có thể viết `p.cardBrand` trong JPQL từ root Payment không?**

Không. Cần query từ `CardPayment` hoặc dùng `TREAT` để truy cập field chuyên biệt.

**7. `TYPE(p) = CardPayment` có nhất thiết bao gồm `PremiumCardPayment extends CardPayment` không?**

Không. `TYPE` kiểm tra entity type thực tế; instance có runtime entity type PremiumCardPayment là kiểu khác CardPayment.

**8. Query `FROM CardPayment c` có tính đa hình với subclass `PremiumCardPayment` không?**

Có, vì `CardPayment` cũng là entity root của một nhánh inheritance.

**9. `@MappedSuperclass` có thể làm root `FROM AuditedRecord a` không?**

Không nếu `AuditedRecord` chỉ là mapped superclass, không phải entity.

**10. `JOIN TREAT(o.payments AS CardPayment) card` dùng để làm gì?**

Thu hẹp association collection từ `Payment` sang `CardPayment` ngay trong join, cho phép dùng `card.cardBrand` và các thuộc tính subtype.

**11. Tại sao cần `DISTINCT` khi select order qua JOIN payments?**

Một order có thể có nhiều payment khớp điều kiện, tạo nhiều join rows cho cùng order.

**12. `LEFT JOIN TREAT` có tự bảo đảm giữ root khi WHERE lọc một thuộc tính alias không?**

Không. Predicate trong WHERE có thể loại các row có alias null; phải xét điều kiện join và cardinality.

**13. Khi nào query trực tiếp `FROM CardPayment` tốt hơn `FROM Payment ... TREAT`?**

Khi toàn bộ use case chỉ làm việc với CardPayment và không cần alias/base relationship đa hình.

**14. `TREAT` có cast một basic string thành entity subtype được không?**

Không. Đây là downcast entity trong inheritance hierarchy, không phải scalar cast.

**15. `TYPE(p) = :type` có thể gán `CardPayment.class` không?**

Có, theo cơ chế entity type parameter được JPA hỗ trợ, miễn class là mapped entity type hợp lệ.

**16. Có nên chèn trực tiếp tên class từ HTTP query parameter vào JPQL không?**

Không. Dùng whitelist để map lựa chọn nghiệp vụ sang class hoặc query được cho phép.

**17. `SINGLE_TABLE` thường biểu diễn subtype bằng gì?**

Một bảng và discriminator; `TYPE` có thể được dịch thành điều kiện discriminator.

**18. `JOINED` có thể khiến `TREAT` dùng tới subtype table không?**

Có. Các trường riêng subtype nằm ở bảng riêng, provider có thể phải tạo JOIN tương ứng.

**19. `TABLE_PER_CLASS` có thể tác động hiệu năng polymorphic query thế nào?**

Provider có thể cần kết hợp nhiều bảng qua UNION hoặc một query plan tương đương.

**20. `TYPE` có thay thế `@Version` hay database unique constraint không?**

Không. Nó là biểu thức query, không phải cơ chế locking hoặc uniqueness.

**21. Có thể dùng `TYPE` với Criteria API không?**

Có. `root.type()` biểu diễn entity type expression và có thể được so sánh với entity class.

**22. Cách tương ứng của `TREAT` trong Criteria API là gì?**

`CriteriaBuilder.treat(...)` với root/join/path phù hợp.

**23. Có nên dùng Java `instanceof` để lọc hàng triệu entity đã tải nếu DB làm được điều đó?**

Thường không. Nên lọc ở query, phân trang và projection để giảm dữ liệu và managed objects.

**24. Nếu thêm một subtype mới, điều kiện `TYPE(p) <> WalletPayment` sẽ ra sao?**

Nó có thể bao gồm subtype mới, nên một whitelist `IN(...)` phù hợp hơn khi nghiệp vụ chỉ cho phép các loại đã nêu.

**25. Tại sao không được suy luận hiệu năng chỉ từ cú pháp `TYPE/TREAT`?**

Vì SQL phụ thuộc inheritance strategy, provider, index, join, data distribution, fetch plan và execution plan.

## 33. Nguyên tắc thiết kế truy vấn đa hình

Khi đọc yêu cầu nghiệp vụ, hãy tự hỏi lần lượt:

1. **Mô hình có phải entity inheritance thật không?** Nếu lớp cha chỉ `@MappedSuperclass`, JPQL không thể query nó như entity root.
2. **Có cần tất cả subtype hay không?** Nếu có, query base entity thường đã đủ.
3. **Có cần một subtype cố định không?** Nếu có, query trực tiếp subtype thường dễ đọc nhất.
4. **Có cần lọc theo entity type từ một điều kiện chung không?** `TYPE` là biểu thức thích hợp.
5. **Có cần trường/association chỉ có ở subtype trong cùng query không?** `TREAT` giúp downcast.
6. **Có query từ parent chứa association tới base entity không?** `JOIN TREAT` hoặc JOIN rồi `TYPE/TREAT` có thể phù hợp.
7. **Có hierarchy nhiều tầng không?** Phân biệt so sánh exact runtime type và truy vấn toàn bộ nhánh subtype.
8. **Có outer join/điều kiện null không?** Cẩn thận khác biệt `JOIN ON`, `WHERE`, `EXISTS` và `NOT EXISTS`.
9. **Có duplicate root do join collection không?** Cân nhắc `DISTINCT` và đúng result shape.
10. **Có cần phân trang/DTO để giảm dữ liệu không?** Không tải cả hierarchy chỉ để lọc ở Java.
11. **Inheritance strategy tạo SQL nào?** `SINGLE_TABLE`, `JOINED` và `TABLE_PER_CLASS` có trade-off rất khác.
12. **Có phụ thuộc extension của provider không?** Kiểm tra khả năng hỗ trợ các treat joins phức tạp, nhất là khi cần chạy trên nhiều provider.

Các câu hỏi này giúp tách **ý nghĩa nghiệp vụ**, **JPQL semantics** và **chi phí SQL** thành ba tầng riêng. Một query ngắn nhưng chọn sai kiểu hoặc sai cardinality có thể nguy hiểm hơn một query dài nhưng rõ ràng.

## 34. Tổng kết

**JPQL là ngôn ngữ truy vấn entity có hỗ trợ đa hình.** Khi base class được ánh xạ thành `@Entity` trong một inheritance hierarchy, query `FROM BaseEntity` có thể trả các concrete subclass mà không cần viết các query riêng và gộp kết quả trong Java.

Hai biểu thức quan trọng:

- **`TYPE(p)`** cho biết **entity type thực tế** của biểu thức `p`; dùng để lọc theo class, `IN` nhiều type hoặc phân loại kết quả. Entity type literal là **entity name**, không phải discriminator string. Có thể tham số hóa với một mapped entity class.
- **`TREAT(path AS Subtype)`** thu hẹp kiểu của một path entity để **truy cập field/association riêng của subtype**. Nó không thay Java object, không chuyển đổi dữ liệu trong database và không thay thế scalar casting.

Những điều cần đặc biệt nhớ:

1. **Không bắt buộc dùng `TYPE` để lấy mọi subtype.** Query polymorphic trên base entity vốn đã làm được.
2. **Nếu chỉ truy vấn một subtype, query trực tiếp subtype thường đơn giản hơn.**
3. **`TYPE` và `TREAT` giải quyết hai nhu cầu khác nhau.** TYPE xét kind; TREAT cho phép đi tiếp xuống subtype property.
4. **`JOIN TREAT` hữu ích khi association được khai báo theo base entity nhưng điều kiện nằm trên subtype.**
5. **Hierarchy nhiều tầng đòi hỏi phân biệt exact type và toàn bộ nhánh subtype.**
6. **`@MappedSuperclass` không phải entity root**, dù Java classes có cùng một superclass.
7. **Inheritance strategy ảnh hưởng mạnh tới SQL**: `SINGLE_TABLE` thường dùng discriminator, `JOINED` có thể cần join subtype table, `TABLE_PER_CLASS` có thể cần union.
8. **Query đúng vẫn cần kiểm soát cardinality, transaction, index và fetch plan.** `TYPE/TREAT` không tạo uniqueness, không thay concurrency control và không tự tối ưu mọi query.

Khi nắm chắc sự khác nhau giữa “**entity có kiểu gì**” và “**tôi muốn đọc thuộc tính của subtype nào**”, bạn có thể dùng `TYPE` và `TREAT` để viết những truy vấn JPQL vừa phản ánh đúng mô hình hướng đối tượng, vừa giao cho database thực hiện phần lọc dữ liệu thích hợp thay vì tải cả object graph rồi kiểm tra kiểu trong Java.
