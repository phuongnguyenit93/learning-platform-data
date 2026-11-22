# Truy vấn đa hình và phạm vi entity được trả về

Trong lập trình hướng đối tượng, **đa hình** (*polymorphism*) cho phép một biến được khai báo theo kiểu cha nhưng chứa một đối tượng thuộc lớp con. JPA áp dụng nguyên lý tương tự cho **entity inheritance**: khi truy vấn một entity ở cấp cha trong hệ phân cấp kế thừa, kết quả có thể bao gồm các entity thuộc **mọi lớp con được ánh xạ** của nó.

Điều này rất khác với việc chỉ đọc các hàng lưu trực tiếp trong một bảng tên giống entity cha. Một câu JPQL như `select p from Payment p` có thể trả về `CardPayment`, `BankTransferPayment` và các entity thuộc nhánh kế thừa khác. Tập kết quả phụ thuộc vào **kiểu entity được chọn làm gốc truy vấn**, **các nhánh kế thừa được JPA quản lý**, và **điều kiện lọc kiểu** như `TYPE` hoặc `TREAT`.

Hiểu phạm vi đa hình giúp giải quyết những câu hỏi thực tế:

- Nếu `Payment` là lớp `abstract`, truy vấn `Payment` có trả kết quả không?
- Truy vấn `CardPayment` có lấy cả `BankTransferPayment` không?
- Muốn chỉ lấy một loại thanh toán, dùng `TYPE(p)` hay `TREAT`?
- `@MappedSuperclass` có thể đứng sau `FROM` trong JPQL không?
- Các chiến lược `SINGLE_TABLE`, `JOINED` và `TABLE_PER_CLASS` ảnh hưởng thế nào tới SQL mà **không làm đổi ngữ nghĩa kiểu trả về**?
- `TypedQuery<Payment>` có bảo đảm mọi instance thực tế có class đúng bằng `Payment` không?
- Khi chỉ cần tổng hợp hoặc dữ liệu API, có nên trả nguyên một hệ phân cấp entity không?

Bài học sẽ xây dựng mô hình kế thừa cụ thể, truy vấn bằng JPQL/Criteria API, phân tích giới hạn phạm vi, rồi mở rộng sang association, hiệu năng, phân trang và những lỗi thường gặp.

## 1. Đa hình trong Java và đa hình trong truy vấn JPA

Xét mô hình nghiệp vụ thanh toán:

```text
                      Payment
                    (abstract entity)
                     /           \
                    /             \
            CardPayment       BankTransferPayment
              (entity)              (entity)
```

Trong Java:

```java
Payment first = new CardPayment(/* ... */);
Payment second = new BankTransferPayment(/* ... */);
```

Biến `first` và `second` đều có kiểu khai báo `Payment`, nhưng object thực tế thuộc hai subclass khác nhau. Nếu gọi một phương thức đa hình được override, Java chọn hành vi theo object tương ứng.

Trong JPA, khi `Payment` được khai báo `@Entity` và hai subclass được ánh xạ thành entity, **một truy vấn bắt đầu từ `Payment` mặc định bao gồm cả hierarchy**:

```java
List<Payment> payments = em.createQuery(
        "select p from Payment p",
        Payment.class
    )
    .getResultList();
```

Kết quả có thể gồm những instance của `CardPayment` và `BankTransferPayment`. Không cần viết `UNION` trong JPQL hay chạy hai truy vấn riêng chỉ để biểu diễn tập kết quả đa hình.

### Đa hình không có nghĩa “mọi entity trong ứng dụng”

`FROM Payment p` chọn **entity `Payment` và những subtype được ánh xạ trong hierarchy của nó**. Nó không tự lấy `Customer`, `Invoice` hoặc mọi entity cùng triển khai một Java interface nào đó nhưng **không thuộc hierarchy entity tương ứng**.

Một truy vấn đa hình luôn có một **phạm vi kiểu** rõ ràng. Phạm vi này có thể được mở rộng bằng cách chọn entity cha cao hơn hoặc thu hẹp bằng cách chọn entity con/đặt điều kiện kiểu.

## 2. Mô hình ví dụ: `Payment`, `CardPayment`, `BankTransferPayment`

Ta sử dụng namespace `jakarta.persistence` và một hierarchy có chiến lược `SINGLE_TABLE` để làm ví dụ ban đầu. Những truy vấn JPQL bên dưới về cơ bản vẫn có ngữ nghĩa đa hình tương ứng khi đổi sang `JOINED` hoặc `TABLE_PER_CLASS`; khác biệt quan trọng nằm ở cách provider tạo SQL.

### 2.1. Entity gốc trừu tượng

```java
package example.billing.domain;

import jakarta.persistence.Column;
import jakarta.persistence.DiscriminatorColumn;
import jakarta.persistence.DiscriminatorType;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Inheritance;
import jakarta.persistence.InheritanceType;
import jakarta.persistence.Table;
import java.math.BigDecimal;

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
    @GeneratedValue(strategy = GenerationType.AUTO)
    private Long id;

    @Column(name = "amount", nullable = false, precision = 18, scale = 2)
    private BigDecimal amount;

    protected Payment() {
        // JPA provider dùng khi tạo entity từ hàng dữ liệu.
    }

    protected Payment(BigDecimal amount) {
        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException("Amount must be positive");
        }
        this.amount = amount;
    }

    public Long getId() {
        return id;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public abstract String describeChannel();
}
```

Các điểm then chốt:

1. `Payment` có `@Entity` nên là **một entity type có thể truy vấn bằng JPQL**, dù Java class là `abstract`.
2. `@Inheritance` khai báo chiến lược lưu hierarchy; ở đây là một bảng cho cả hierarchy.
3. `@DiscriminatorColumn` chỉ định cột giúp provider phân biệt kiểu cụ thể của từng row trong `SINGLE_TABLE`.
4. `id` và `amount` là persistent attributes chung của các subclass.
5. Vì lớp `Payment` là `abstract`, ứng dụng không thể tạo một instance `Payment` thuần bằng `new Payment(...)`, nhưng vẫn có thể **truy vấn entity `Payment`** để nhận các subclass.

### 2.2. Subclass thanh toán thẻ

```java
package example.billing.domain;

import jakarta.persistence.Column;
import jakarta.persistence.DiscriminatorValue;
import jakarta.persistence.Entity;
import java.math.BigDecimal;

@Entity
@DiscriminatorValue("CARD")
public class CardPayment extends Payment {
    @Column(name = "card_last_four", length = 4)
    private String lastFourDigits;

    protected CardPayment() {
    }

    public CardPayment(BigDecimal amount, String lastFourDigits) {
        super(amount);
        if (lastFourDigits == null || lastFourDigits.length() != 4) {
            throw new IllegalArgumentException("Four digits required");
        }
        this.lastFourDigits = lastFourDigits;
    }

    public String getLastFourDigits() {
        return lastFourDigits;
    }

    @Override
    public String describeChannel() {
        return "Card ending " + lastFourDigits;
    }
}
```

`CardPayment` **kế thừa** ID và amount từ `Payment`, đồng thời bổ sung `lastFourDigits`.

### 2.3. Subclass chuyển khoản

```java
package example.billing.domain;

import jakarta.persistence.Column;
import jakarta.persistence.DiscriminatorValue;
import jakarta.persistence.Entity;
import java.math.BigDecimal;

@Entity
@DiscriminatorValue("BANK_TRANSFER")
public class BankTransferPayment extends Payment {
    @Column(name = "bank_reference", length = 100)
    private String bankReference;

    protected BankTransferPayment() {
    }

    public BankTransferPayment(BigDecimal amount, String bankReference) {
        super(amount);
        if (bankReference == null || bankReference.isBlank()) {
            throw new IllegalArgumentException("Bank reference required");
        }
        this.bankReference = bankReference;
    }

    public String getBankReference() {
        return bankReference;
    }

    @Override
    public String describeChannel() {
        return "Transfer " + bankReference;
    }
}
```

### 2.4. Hình dạng dữ liệu với `SINGLE_TABLE`

Một bảng minh họa:

```text
payments
+----+---------------+----------+----------------+----------------+
| id | payment_kind  | amount   | card_last_four | bank_reference |
+----+---------------+----------+----------------+----------------+
| 10 | CARD          | 150.00   | 4242           | NULL           |
| 11 | BANK_TRANSFER | 450.00   | NULL           | TXN-001        |
| 12 | CARD          | 200.00   | 1888           | NULL           |
+----+---------------+----------+----------------+----------------+
```

Mỗi hàng là một entity cụ thể. Cột `payment_kind` cung cấp thông tin phân biệt kiểu. Các cột chỉ dùng cho một subclass có thể null đối với những row thuộc subclass khác. Vì vậy, với `SINGLE_TABLE`, không nên khai báo `NOT NULL` ở database cho cột chỉ thuộc một subclass mà mọi subtype khác cần để null, trừ khi có constraint theo điều kiện discriminator phù hợp.

## 3. Truy vấn polymorphic mặc định bắt đầu từ entity cha

JPQL:

```java
List<Payment> payments = em.createQuery(
        "select p from Payment p order by p.id",
        Payment.class
    )
    .getResultList();
```

Nếu database có ba hàng như ví dụ, kết quả logic sẽ là:

```text
payments[0] -> CardPayment        (id = 10)
payments[1] -> BankTransferPayment (id = 11)
payments[2] -> CardPayment        (id = 12)
```

Trong một persistence context, JPA dựng instance của **entity class phù hợp** với row. Mặc dù biến kết quả có kiểu khai báo `Payment`, object thực tế có thể thuộc subclass tương ứng.

```java
for (Payment p : payments) {
    System.out.println(
        p.getId() + " / " + p.describeChannel()
    );
}
```

Phương thức `describeChannel()` được gọi theo đa hình Java. `CardPayment` và `BankTransferPayment` triển khai hành vi khác nhau mà vòng lặp không cần ép kiểu chỉ để gọi hành vi chung.

### 3.1. Abstract entity có thể làm query root

Câu hỏi thường gặp: “`Payment` là abstract thì bảng nào chứa các `Payment` được truy vấn?”

Điều JPA cần không phải là có thể gọi `new Payment()`, mà là `Payment` là một **entity type** trong persistence unit. Do đó:

```java
@Entity
public abstract class Payment {
    // ...
}
```

vẫn là một JPQL root hợp lệ:

```sql
-- Minh họa ý nghĩa; đây không phải JPQL.
SELECT ... FROM payments WHERE ...;
```

Ở `SINGLE_TABLE`, provider đọc từ bảng chung và dùng discriminator để tạo subclass. Với `JOINED` và `TABLE_PER_CLASS`, SQL thực tế có thể phức tạp hơn.

**Vì `Payment` là abstract, kết quả sẽ không chứa một instance trực tiếp của `Payment`.** Nếu Payment là class cụ thể được ánh xạ, query root cũng có thể bao gồm các entity trực tiếp thuộc Payment bên cạnh subclass.

### 3.2. Truy vấn thuộc tính chung trên cha

```java
List<Payment> expensive = em.createQuery(
        "select p from Payment p " +
        "where p.amount >= :minimum " +
        "order by p.amount desc, p.id asc",
        Payment.class
    )
    .setParameter("minimum", new BigDecimal("200.00"))
    .getResultList();
```

Vì `amount` là thuộc tính persistent khai báo ở `Payment`, mọi subtype đều có thể dùng trong điều kiện. Truy vấn trả các loại thanh toán thỏa số tiền, không chỉ một subclass.

### 3.3. `COUNT` trên entity cha cũng là đa hình

```java
Long count = em.createQuery(
        "select count(p) from Payment p",
        Long.class
    )
    .getSingleResult();
```

`count` đếm các entity thuộc phạm vi truy vấn `Payment`, tức gồm các nhánh con được ánh xạ và không bị loại bởi điều kiện. Không cần cộng thủ công số lượng của từng subclass.

Nếu có filter theo tenant, soft delete, quyền truy cập hoặc các điều kiện bổ sung ở ứng dụng/provider, tập kết quả có thể bị thu hẹp. Mô hình đa hình quyết định **các kiểu có thể tham gia**, còn điều kiện truy vấn và cấu hình runtime quyết định **những row thực sự khớp**.

## 4. Truy vấn từ subclass: phạm vi tự động hẹp hơn

Khi JPQL bắt đầu từ `CardPayment`:

```java
List<CardPayment> cards = em.createQuery(
        "select c from CardPayment c " +
        "where c.lastFourDigits = :lastFour " +
        "order by c.id",
        CardPayment.class
    )
    .setParameter("lastFour", "4242")
    .getResultList();
```

Truy vấn chỉ xét **`CardPayment` và những subtype entity của nó**, nếu có hierarchy sâu hơn. Nó **không** trả `BankTransferPayment` bởi subclass này là một nhánh anh em, không kế thừa từ `CardPayment`.

Đặt query root chính là cách tự nhiên để giới hạn một hierarchy:

| JPQL root | Những entity có thể nằm trong kết quả |
|---|---|
| `FROM Payment p` | `Payment` nếu concrete, `CardPayment`, `BankTransferPayment` và mọi subtype entity bên dưới |
| `FROM CardPayment c` | `CardPayment` và những subclass entity của `CardPayment` |
| `FROM BankTransferPayment b` | `BankTransferPayment` và subclass entity của nó |
| `FROM Invoice i` | `Invoice` và subtype entity của `Invoice`; không tự có Payment |

Nếu ứng dụng thêm `MobileWalletPayment extends Payment` trong tương lai và khai báo entity đó trong persistence unit, **truy vấn `FROM Payment` có thể bắt đầu trả về thêm kiểu này mà không cần sửa JPQL**. Đây là lợi ích của đa hình, đồng thời là điều phải tính tới khi tầng service/DTO giả định hệ thống chỉ có hai subtype.

### 4.1. Truy vấn subclass vẫn được dùng thuộc tính của superclass

```java
List<CardPayment> cards = em.createQuery(
        "select c from CardPayment c " +
        "where c.amount > :minAmount " +
        "and c.lastFourDigits = :lastFour",
        CardPayment.class
    )
    .setParameter("minAmount", new BigDecimal("100.00"))
    .setParameter("lastFour", "4242")
    .getResultList();
```

`c.amount` nằm ở `Payment`, còn `c.lastFourDigits` nằm ở `CardPayment`. Vì JPQL root là CardPayment, cả hai thuộc tính đều hợp lệ trong path expression.

### 4.2. Truy vấn cha không tự nhìn thấy thuộc tính chỉ có ở con

Đoạn sau không phải một cách viết portable đúng:

```java
// Không hợp lệ: alias p có entity type Payment, không có thuộc tính lastFourDigits.
String jpql = "select p from Payment p " +
              "where p.lastFourDigits = :lastFour";
```

Dù kết quả của `Payment` có thể chứa `CardPayment`, **type khai báo của path expression vẫn là `Payment`**. Nếu muốn điều kiện trên field chỉ xuất hiện ở subtype, hãy dùng:

- Root `FROM CardPayment` khi chỉ quan tâm loại thanh toán thẻ.
- `TYPE(p)` để lọc kiểu cụ thể.
- `TREAT(p AS CardPayment)` để điều hướng thuộc tính đặc thù của subtype trong một truy vấn gốc từ cha.

## 5. `TYPE`: lọc chính xác entity type

JPQL có toán tử `TYPE` để kiểm tra **kiểu entity runtime** của một entity được chọn hoặc một đường dẫn entity.

Ví dụ chỉ lấy `CardPayment` từ truy vấn gốc Payment:

```java
List<Payment> cards = em.createQuery(
        "select p from Payment p " +
        "where TYPE(p) = CardPayment",
        Payment.class
    )
    .getResultList();
```

Ở đây:

- `TYPE(p)` biểu diễn entity type của object thực tế.
- `CardPayment` là **entity type literal** trong JPQL, không phải chuỗi `"CARD"` của discriminator.
- `select p` vẫn có kiểu khai báo `Payment`.
- Điều kiện `TYPE(p) = CardPayment` giữ những entity có kiểu chính xác là `CardPayment`.

### 5.1. Lọc nhiều entity types

```java
List<Payment> selected = em.createQuery(
        "select p from Payment p " +
        "where TYPE(p) IN (CardPayment, BankTransferPayment) " +
        "order by p.id",
        Payment.class
    )
    .getResultList();
```

Cách này hữu ích khi hierarchy có nhiều subtype nhưng màn hình chỉ xử lý một tập loại cụ thể.

### 5.2. Exact type và toàn bộ nhánh subtype không giống nhau

Giả sử sau này có:

```text
Payment
  ├─ CardPayment
  |    └─ VirtualCardPayment
  └─ BankTransferPayment
```

Giả sử `VirtualCardPayment` cũng được khai báo `@Entity`. Khi đó:

- `FROM CardPayment c` là **polymorphic query**: kết quả có thể có `CardPayment` và `VirtualCardPayment`.
- `TYPE(p) = CardPayment` là điều kiện **kiểu entity chính xác**: không tự bao gồm `VirtualCardPayment`.
- `TYPE(p) IN (CardPayment, VirtualCardPayment)` bao gồm cả hai kiểu được liệt kê.
- `TREAT(p AS CardPayment)` dùng để điều hướng theo lớp CardPayment và có thể hợp lệ với instance thuộc các subtype của CardPayment.

Nếu yêu cầu là “mọi thanh toán bằng thẻ, kể cả biến thể thẻ trong tương lai”, chọn root `CardPayment` hoặc cơ chế theo **nhánh kế thừa**, thay vì hardcode một điều kiện exact `TYPE` duy nhất.

### 5.3. Không so sánh `TYPE` với giá trị discriminator như chuỗi

Ví dụ bảng `payments` có `payment_kind = 'CARD'` nhưng trong JPQL:

```java
// Không dùng chuỗi discriminator thay cho entity type literal:
String wrong = "select p from Payment p where TYPE(p) = 'CARD'";

// Đúng: TYPE so sánh với entity type.
String correct = "select p from Payment p where TYPE(p) = CardPayment";
```

`@DiscriminatorValue("CARD")` là metadata biểu diễn kiểu trong cơ sở dữ liệu, còn `CardPayment` trong `TYPE` là tên entity type của JPQL.

Một số provider có cú pháp mở rộng để truy vấn trực tiếp discriminator, nhưng không nên phụ thuộc vào đó khi muốn mã portable theo JPA.

### 5.4. Lọc kiểu chính xác của base entity

Nếu `Payment` là class concrete được phép lưu trực tiếp:

```java
List<Payment> baseOnly = em.createQuery(
        "select p from Payment p " +
        "where TYPE(p) = Payment",
        Payment.class
    )
    .getResultList();
```

Kết quả chỉ gồm instance thực sự thuộc entity type `Payment`, không bao gồm CardPayment. Với mô hình ví dụ ở trên `Payment` là `abstract`, không có instance Payment trực tiếp, nên điều kiện này không trả row nào.

## 6. `TREAT`: điều hướng thuộc tính của subtype

`TYPE` giúp biết object thuộc entity type nào. `TREAT` giải quyết bài toán khác: **ép kiểu biểu thức đường dẫn entity xuống một subtype** để truy cập thuộc tính mà superclass không khai báo.

Ví dụ, muốn truy vấn từ `Payment` nhưng lọc theo bốn chữ số cuối thẻ:

```java
List<Payment> payments = em.createQuery(
        "select p from Payment p " +
        "where TREAT(p AS CardPayment).lastFourDigits = :lastFour " +
        "order by p.id",
        Payment.class
    )
    .setParameter("lastFour", "4242")
    .getResultList();
```

Ý nghĩa:

1. `FROM Payment p` xác định phạm vi xuất phát từ hierarchy Payment.
2. `TREAT(p AS CardPayment)` cho phép dùng những thuộc tính định nghĩa trên CardPayment.
3. Những instance không thuộc nhánh CardPayment không có `lastFourDigits` tương ứng, nên không thỏa điều kiện so sánh trong `WHERE` này.
4. Kết quả chọn vẫn là `p` nên kiểu trả về của query là `Payment`.

### 6.1. Khi nào dùng `TREAT` thay vì root subclass?

Nếu truy vấn chỉ xử lý thanh toán thẻ, cách ngắn gọn hơn thường là:

```java
List<CardPayment> cards = em.createQuery(
        "select c from CardPayment c " +
        "where c.lastFourDigits = :lastFour",
        CardPayment.class
    )
    .setParameter("lastFour", "4242")
    .getResultList();
```

`TREAT` hữu ích khi:

- Truy vấn vốn bắt đầu từ entity cha và vẫn cần các thuộc tính chung.
- Có association được khai báo theo superclass nhưng muốn xét thuộc tính đặc thù của subtype.
- Dùng JPQL/Criteria phức tạp với nhiều nhánh kế thừa, điều kiện hoặc join.
- Muốn giữ kiểu kết quả theo superclass để các tầng gọi không bị ràng buộc vào một subtype cụ thể.

### 6.2. `TREAT` không đổi object thành một class mới

`TREAT` **không tạo ra instance CardPayment mới**, cũng không biến một BankTransferPayment thành CardPayment. Nó là phép điều hướng/kiểm tra kiểu trong ngữ cảnh truy vấn.

Trong Java:

```java
Payment payment = em.find(Payment.class, id);

if (payment instanceof CardPayment) {
    CardPayment card = (CardPayment) payment;
    System.out.println(card.getLastFourDigits());
}
```

Đây là thao tác kiểm tra kiểu ở Java sau khi entity đã được tải. Trong JPQL, `TREAT` cho phép **lọc ở database trước khi dữ liệu được trả về**; thường phù hợp hơn việc tải toàn bộ Payment rồi dùng `instanceof` để loại bỏ phần tử trong Java.

## 7. Phạm vi kiểu của kết quả: `TypedQuery<T>` không có nghĩa class chính xác là `T`

Hai khái niệm cần phân biệt:

1. **Kiểu khai báo của kết quả**: kiểu generic mà Java và JPA API dùng để kiểm tra cách gọi.
2. **Kiểu entity runtime**: subclass cụ thể được provider tạo theo mapping.

Ví dụ:

```java
TypedQuery<Payment> query = em.createQuery(
    "select p from Payment p",
    Payment.class
);

List<Payment> result = query.getResultList();

for (Payment p : result) {
    if (p instanceof CardPayment) {
        // Một object thuộc CardPayment.
    } else if (p instanceof BankTransferPayment) {
        // Một object thuộc BankTransferPayment.
    }
}
```

`TypedQuery<Payment>` đảm bảo phần tử kết quả phù hợp với kiểu Java `Payment`, không yêu cầu `p.getClass() == Payment.class`. Subclass là một `Payment` hợp lệ theo Java.

### 7.1. Đừng ép kiểu cả danh sách

Không nên:

```java
List<Payment> payments = em.createQuery(
    "select p from Payment p",
    Payment.class
).getResultList();

// Sai về assumptions: không thể coi mọi phần tử đều là CardPayment.
for (Payment p : payments) {
    CardPayment card = (CardPayment) p;
    // Có thể ClassCastException với BankTransferPayment.
}
```

Nếu chỉ cần CardPayment, chọn `FROM CardPayment` hoặc lọc subtype ở query. Nếu cần xử lý nhiều loại, thiết kế business method chung được override hoặc visitor/handler phù hợp thay vì ép kiểu không kiểm tra.

### 7.2. Proxy và class runtime

Đối với entity lazy association, một số provider sử dụng proxy hoặc bytecode enhancement. Vì vậy, `entity.getClass()` đôi khi không phải cách đáng tin cậy nhất để suy luận entity type trong mọi tình huống provider.

Để lọc tại database theo JPA, dùng `TYPE`/`TREAT`. Ở Java, `instanceof` có thể thích hợp với những entity đã được tải, nhưng nếu cần xác định class persistent một cách chính xác qua proxy, nên dùng API metadata/provider tương ứng và hiểu vòng đời proxy.

Không được xem `TYPE(p)` trong JPQL là thao tác đơn giản gọi `getClass()` trên object đã tải; provider có thể thực hiện kiểm tra ngay trong SQL dựa trên metadata inheritance.

## 8. `@MappedSuperclass` không phải query root đa hình

Một nhầm lẫn rất phổ biến là cho rằng mọi Java superclass của các entity đều có thể dùng trong `FROM`.

Ví dụ:

```java
import jakarta.persistence.Column;
import jakarta.persistence.MappedSuperclass;
import java.time.Instant;

@MappedSuperclass
public abstract class AuditableRecord {
    @Column(name = "created_at", nullable = false)
    protected Instant createdAt;

    public Instant getCreatedAt() {
        return createdAt;
    }
}
```

Hai entity kế thừa lớp này:

```java
@Entity
public class Invoice extends AuditableRecord {
    @Id
    private Long id;

    protected Invoice() {}
}

@Entity
public class Shipment extends AuditableRecord {
    @Id
    private Long id;

    protected Shipment() {}
}
```

`@MappedSuperclass` **đóng góp mapping thuộc tính** cho các entity con, nhưng chính `AuditableRecord` không có entity identity hay một entity type độc lập trong persistence unit.

Do đó:

```java
// Không hợp lệ theo JPQL chuẩn: AuditableRecord không phải entity.
String invalid = "select a from AuditableRecord a";
```

Các truy vấn hợp lệ:

```java
List<Invoice> invoices = em.createQuery(
        "select i from Invoice i " +
        "where i.createdAt >= :from",
        Invoice.class
    )
    .setParameter("from", fromInstant)
    .getResultList();

List<Shipment> shipments = em.createQuery(
        "select s from Shipment s",
        Shipment.class
    )
    .getResultList();
```

`Invoice` và `Shipment` **không trở thành một hierarchy entity có chung query root** chỉ vì cả hai kế thừa cùng `@MappedSuperclass`.

### Bảng so sánh

| Kiểu lớp cha | Có entity identity? | Dùng làm JPQL root? | Truy vấn root có bao gồm entity con? |
|---|---|---|---|
| `@Entity abstract Payment` | Là entity type; các instance cụ thể có identity | **Có** | **Có**, polymorphic mặc định |
| `@Entity concrete Payment` | Có | **Có** | **Có**, gồm base và subtype |
| `@MappedSuperclass AuditableRecord` | Không phải entity type | **Không** | Không có polymorphic query root |
| Java class cha không được JPA ánh xạ làm entity | Không phải entity type | **Không** | Không |
| Java interface do entity triển khai | Không tự trở thành entity type | **Không** theo query root chuẩn | Không có phạm vi JPQL entity mặc định |

**Điểm cốt lõi:** đa hình của JPA dựa trên **entity inheritance hierarchy trong metadata**, không chỉ dựa trên quan hệ `extends` hoặc `implements` của Java.

## 9. `@Entity(name = "...")` và tên entity trong JPQL

Nếu khai báo:

```java
@Entity(name = "BillingPayment")
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class Payment {
    // ...
}
```

Trong persistence unit đó, **entity name** được chỉ định là `BillingPayment`. JPQL root phải dùng tên entity:

```java
String jpql = "select p from BillingPayment p";
```

Không tự giả định `FROM Payment` luôn là tên hợp lệ sau khi đổi `@Entity(name)`. `@Table(name)` quy định tên bảng SQL, còn `@Entity(name)` quy định tên entity dùng trong JPQL. Hai tên có nhiệm vụ khác nhau:

| Annotation/định danh | Phạm vi |
|---|---|
| Java class `Payment` | Kiểu của object trong ứng dụng |
| `@Entity(name = "BillingPayment")` | Tên entity trong JPQL |
| `@Table(name = "payments")` | Tên bảng quan hệ |
| `@DiscriminatorValue("CARD")` | Giá trị phân biệt kiểu ở bảng, không phải JPQL entity name |

Các ví dụ còn lại dùng entity name mặc định bằng tên class đơn giản, vì vậy vẫn viết `FROM Payment`, `FROM CardPayment`.

### Một class được đánh dấu `@Entity` nhưng không thuộc persistence unit?

Phạm vi query còn phụ thuộc metadata của persistence unit. Các entity phải được provider phát hiện/đăng ký phù hợp với cấu hình application/container. Nếu một subclass chưa được khai báo/scan vào persistence unit, không thể coi nó là một entity subtype mà JPQL chắc chắn sẽ đọc. Khi thêm module/entity mới, cần kiểm tra việc đăng ký class, migration bảng và đồng bộ phiên bản triển khai.

## 10. Chiến lược kế thừa thay đổi SQL, không tự thay đổi ngữ nghĩa đa hình

JPA có ba chiến lược inheritance nổi bật:

- `InheritanceType.SINGLE_TABLE`
- `InheritanceType.JOINED`
- `InheritanceType.TABLE_PER_CLASS`

Cùng một câu:

```java
List<Payment> all = em.createQuery(
    "select p from Payment p",
    Payment.class
).getResultList();
```

về mặt mô hình vẫn là **truy vấn entity Payment và các subclass**. Nhưng cách provider tìm dữ liệu từ database khác nhau.

### 10.1. `SINGLE_TABLE`

Tất cả các entity trong hierarchy lưu vào một bảng, phân biệt kiểu bằng discriminator.

```text
payments
  id
  payment_kind
  amount
  card_last_four
  bank_reference
```

Một truy vấn gốc `Payment` có thể đọc bảng `payments` và dựng subclass theo `payment_kind`. Query subtype có thể thêm điều kiện discriminator.

**Ưu điểm thường gặp:**

- Truy vấn đa hình có thể đơn giản hơn, không cần JOIN nhiều bảng con.
- Một bảng chung có thể thuận tiện cho truy vấn theo thuộc tính của superclass.

**Đánh đổi:**

- Bảng rộng nếu nhiều subclass có nhiều trường riêng.
- Cột chỉ thuộc subtype thường phải nullable cho các row không cùng loại.
- Ràng buộc toàn vẹn dành riêng cho từng subtype có thể khó diễn đạt bằng `NOT NULL` chung, cần check constraint hoặc validation phù hợp.

### 10.2. `JOINED`

Superclass có bảng riêng chứa các thuộc tính chung; subclass có bảng riêng chứa các thuộc tính riêng, thường nối bằng khóa chính.

```text
payments
  id (PK)
  amount
  [discriminator nếu mapping dùng]

card_payments
  id (PK, FK -> payments.id)
  card_last_four

bank_transfer_payments
  id (PK, FK -> payments.id)
  bank_reference
```

Truy vấn `FROM Payment` có thể phải JOIN các bảng subtype hoặc dùng những cách đọc bổ sung để xác định và dựng subtype. Truy vấn `FROM CardPayment` có thể cần join bảng `payments` với `card_payments`.

**Ưu điểm thường gặp:**

- Phân tách các cột riêng của subtype; tránh nhiều cột null trong bảng chung.
- Schema phản ánh inheritance rõ theo các bảng.

**Đánh đổi:**

- Truy vấn polymorphic có thể phải truy cập nhiều bảng.
- Query phức tạp với nhiều subtype và association có thể tốn thêm JOIN hoặc SQL.
- Thêm subclass tạo thêm bảng và có thể làm thay đổi kế hoạch truy vấn.

### 10.3. `TABLE_PER_CLASS`

Mỗi lớp entity cụ thể có bảng riêng, thường chứa cả các thuộc tính được kế thừa. Nếu root abstract, có thể không có bảng chứa row của root.

```text
card_payments
  id
  amount
  card_last_four

bank_transfer_payments
  id
  amount
  bank_reference
```

Truy vấn `FROM Payment` phải kết hợp những row có thể thuộc các bảng concrete subtype. Nhiều provider hiện thực điều đó bằng SQL **`UNION` / `UNION ALL`** hoặc cách kết hợp truy vấn thích hợp.

**Ưu điểm có thể có:**

- Bảng từng subtype độc lập hơn, không cần cột nullable của subtype khác.
- Truy vấn chỉ một concrete subtype có thể chạm ít bảng hơn, tùy mapping.

**Đánh đổi:**

- Polymorphic query có thể cần UNION trên nhiều bảng và trở nên tốn kém khi hierarchy lớn.
- Yêu cầu về cấp khóa chính phải đảm bảo identity nhất quán trên toàn hierarchy; các ID generator cục bộ độc lập dễ dẫn đến xung đột/khó xử lý.
- Thay đổi thuộc tính chung có thể ảnh hưởng schema nhiều bảng.
- Tương thích và tối ưu hóa cụ thể tùy provider/database.

### 10.4. Bảng so sánh tác động đến truy vấn

| Tiêu chí | `SINGLE_TABLE` | `JOINED` | `TABLE_PER_CLASS` |
|---|---|---|---|
| Cấu trúc lưu trữ | Một bảng chung | Bảng root + bảng subtype | Bảng cho từng concrete entity |
| Xác định subtype | Thường dùng discriminator | Dựa trên discriminator/join/metadata | Từ bảng concrete tương ứng |
| JPQL `FROM Payment` có đa hình không? | Có | Có | Có |
| SQL có thể dùng | Một bảng + điều kiện type | Join nhiều bảng | Union hoặc nhiều nhánh |
| Truy vấn riêng subclass | Thường lọc discriminator | Join root/subtype | Thường đọc bảng subtype |
| Vấn đề nổi bật | Bảng rộng, cột subtype null | Nhiều join | UNION và quản lý khóa toàn hierarchy |

**Không có chiến lược nào “tắt” đa hình JPQL chỉ vì nó lưu vào bảng riêng.** Nếu yêu cầu nghiệp vụ chỉ lấy subtype cụ thể, phải chọn query root hoặc đặt điều kiện kiểu phù hợp; không phụ thuộc vào chiến lược bảng.

## 11. Truy vấn đa hình qua association được khai báo theo superclass

Đa hình không chỉ xuất hiện trong `FROM Payment`. Một entity khác có thể giữ association kiểu `Payment`:

```java
package example.billing.domain;

import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.OneToOne;

@Entity
public class Invoice {
    @Id
    @GeneratedValue(strategy = GenerationType.AUTO)
    private Long id;

    @OneToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "payment_id")
    private Payment payment;

    protected Invoice() {}

    public Payment getPayment() {
        return payment;
    }
}
```

`Invoice.payment` có kiểu Java khai báo là `Payment`, nhưng row tham chiếu có thể là CardPayment hoặc BankTransferPayment. Khi provider tải association này, object thực tế được dựng theo entity type của row target.

Truy vấn:

```java
List<Invoice> invoices = em.createQuery(
        "select i from Invoice i " +
        "join i.payment p " +
        "where p.amount >= :minimum",
        Invoice.class
    )
    .setParameter("minimum", new BigDecimal("100.00"))
    .getResultList();
```

`p` ở đây có kiểu entity khai báo `Payment`. Provider có thể join/lọc trên hierarchy Payment; không buộc mọi invoice phải chỉ thanh toán thẻ.

### 11.1. Lọc theo subtype của association

```java
List<Invoice> cardInvoices = em.createQuery(
        "select i from Invoice i " +
        "join i.payment p " +
        "where TYPE(p) = CardPayment",
        Invoice.class
    )
    .getResultList();
```

Kết quả là Invoice có payment thuộc chính xác entity type CardPayment. `select i` vẫn trả **Invoice**, không phải CardPayment.

Nếu cần lọc theo thuộc tính đặc thù của payment thẻ:

```java
List<Invoice> invoices = em.createQuery(
        "select i from Invoice i " +
        "where TREAT(i.payment AS CardPayment).lastFourDigits = :lastFour",
        Invoice.class
    )
    .setParameter("lastFour", "4242")
    .getResultList();
```

Ở đây `TREAT` hoạt động trên một **single-valued association path** có kiểu Payment. Provider tạo SQL phù hợp với chiến lược kế thừa đang dùng.

### 11.2. Association declaration và object runtime

| Phần | Kiểu/giá trị |
|---|---|
| `Invoice.payment` | Khai báo theo `Payment` |
| Row được tham chiếu | Có thể thuộc `CardPayment` hoặc `BankTransferPayment` |
| `i.getPayment()` | Trả một `Payment` theo kiểu khai báo |
| Thực thể được tải | Là concrete subtype thích hợp |
| `TYPE(p)` | Cho phép lọc theo entity type của association |
| `TREAT(i.payment AS CardPayment)` | Cho phép điều hướng thuộc tính subtype |

Điều này cho phép một quan hệ được mở rộng thêm các phương thức thanh toán mới mà không phải thay kiểu field ở `Invoice`.

## 12. Criteria API: phạm vi truy vấn đa hình giống JPQL

Criteria API là cách dựng truy vấn có kiểu bằng Java thay vì ghép chuỗi JPQL. Ngữ nghĩa đa hình vẫn gắn với **root entity class**.

### 12.1. Chọn root superclass

```java
import jakarta.persistence.criteria.CriteriaBuilder;
import jakarta.persistence.criteria.CriteriaQuery;
import jakarta.persistence.criteria.Root;

CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Payment> cq = cb.createQuery(Payment.class);
Root<Payment> p = cq.from(Payment.class);

cq.select(p);

List<Payment> payments = em.createQuery(cq).getResultList();
```

`cq.from(Payment.class)` có phạm vi tương đương `FROM Payment p`: xét Payment và các entity subtype.

### 12.2. Chỉ lấy một entity type bằng `type()`

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Payment> cq = cb.createQuery(Payment.class);
Root<Payment> p = cq.from(Payment.class);

cq.select(p)
  .where(cb.equal(p.type(), CardPayment.class));

List<Payment> cards = em.createQuery(cq).getResultList();
```

`p.type()` là biểu thức Criteria biểu diễn entity type; nó tương ứng với `TYPE(p)` trong JPQL. Điều kiện dùng `CardPayment.class` để chọn entity type chính xác.

### 12.3. `CriteriaBuilder.treat` để dùng thuộc tính con

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Payment> cq = cb.createQuery(Payment.class);
Root<Payment> p = cq.from(Payment.class);

Root<CardPayment> card = cb.treat(p, CardPayment.class);

cq.select(p)
  .where(cb.equal(card.get("lastFourDigits"), "4242"));

List<Payment> results = em.createQuery(cq).getResultList();
```

`cb.treat(p, CardPayment.class)` cho phép điều hướng thuộc tính `lastFourDigits` của subtype CardPayment. Trong dự án dùng static metamodel, có thể thay chuỗi tên field bằng đường dẫn có kiểu để hạn chế lỗi gõ sai tên thuộc tính.

### 12.4. Root subclass

Nếu chỉ cần CardPayment, chọn trực tiếp:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<CardPayment> cq =
    cb.createQuery(CardPayment.class);
Root<CardPayment> card = cq.from(CardPayment.class);

cq.select(card)
  .where(cb.equal(card.get("lastFourDigits"), "4242"));

List<CardPayment> results = em.createQuery(cq).getResultList();
```

Cách này diễn đạt phạm vi hẹp nhất bằng chính kiểu root và kiểu kết quả.

## 13. Entity query khác DTO/scalar projection về kiểu trả về

Khi viết:

```java
List<Payment> payments = em.createQuery(
    "select p from Payment p",
    Payment.class
).getResultList();
```

Kết quả là **managed entities** trong persistence context (khi query được thực hiện trong một context đang hoạt động), có identity và hành vi/lifecycle JPA.

Khi viết:

```java
List<Long> ids = em.createQuery(
    "select p.id from Payment p",
    Long.class
).getResultList();
```

Kết quả là **scalar Long**, không phải các entity Payment. Truy vấn vẫn dùng phạm vi đa hình từ `Payment` để tìm row, nhưng `SELECT` chỉ lấy ID.

### 13.1. DTO projection cho báo cáo

Một DTO:

```java
package example.billing.api;

import java.math.BigDecimal;

public record PaymentSummary(Long id, BigDecimal amount) {}
```

JPQL:

```java
List<PaymentSummary> summaries = em.createQuery(
        "select new example.billing.api.PaymentSummary(" +
        "p.id, p.amount) " +
        "from Payment p " +
        "order by p.id",
        PaymentSummary.class
    )
    .getResultList();
```

Query `FROM Payment` vẫn xem xét mọi subtype, nhưng `select new ...` tạo **PaymentSummary DTO**, không phải object CardPayment hay BankTransferPayment. DTO không được JPA theo dõi dirty checking; thay đổi DTO không đồng nghĩa cập nhật database.

### 13.2. Không nên cast DTO thành entity con

`PaymentSummary` không có `@Entity` và không thuộc hierarchy Payment. Dù dữ liệu của DTO đến từ row CardPayment, nó vẫn là một object Java độc lập. Nếu API cần thông tin phân loại, có thể thêm trường hoặc xây projection cụ thể theo yêu cầu, thay vì trả entity raw rồi ép kiểu ở layer ngoài.

### 13.3. Truy vấn subtype cụ thể và DTO khác nhau

| Nhu cầu | Câu truy vấn phù hợp | Kiểu kết quả |
|---|---|---|
| Xử lý nghiệp vụ chung của mọi Payment | `SELECT p FROM Payment p` | `Payment`, object có thể là subtype |
| Chỉ xử lý CardPayment | `SELECT c FROM CardPayment c` | `CardPayment` và subtype của nó |
| Báo cáo số tiền tất cả loại Payment | `SELECT NEW ... FROM Payment p` | DTO |
| Chỉ lấy khóa mọi Payment | `SELECT p.id FROM Payment p` | `Long` |
| Đếm tất cả Payment | `SELECT COUNT(p) FROM Payment p` | `Long` |
| Lấy invoice có payment thẻ | `SELECT i ... JOIN i.payment p WHERE TYPE(p)=CardPayment` | `Invoice` |

## 14. Phân trang và sắp xếp kết quả đa hình

Một câu truy vấn đa hình có thể trả hàng trăm nghìn entity thuộc nhiều subtype. Không nên tải toàn bộ chỉ để hiển thị một trang.

```java
List<Payment> page = em.createQuery(
        "select p from Payment p " +
        "order by p.id",
        Payment.class
    )
    .setFirstResult(100)
    .setMaxResults(50)
    .getResultList();
```

Trong ví dụ này, trang có **tối đa 50 Payment**, bất kể thuộc subtype nào. Một trang có thể chứa nhiều CardPayment, BankTransferPayment xen kẽ. JPA không tự phân mỗi subtype thành một trang riêng.

### 14.1. Thứ tự phải xác định

Truy vấn `FROM Payment` không có `ORDER BY` không bảo đảm thứ tự row. Nếu dùng offset pagination, cần một thứ tự ổn định và tốt nhất có một tie-breaker unique:

```java
List<Payment> page = em.createQuery(
        "select p from Payment p " +
        "where p.amount >= :minimum " +
        "order by p.amount desc, p.id asc",
        Payment.class
    )
    .setParameter("minimum", new BigDecimal("100.00"))
    .setFirstResult(0)
    .setMaxResults(50)
    .getResultList();
```

Nếu các subtype lưu ở những bảng riêng theo `TABLE_PER_CLASS`, cần bảo đảm chiến lược ID và thứ tự thực sự phân biệt các entity trên toàn hierarchy theo semantics của provider.

### 14.2. Offset sâu và dữ liệu thay đổi

`setFirstResult(100000)` giới hạn số entity Java trả về nhưng database có thể phải đọc/sắp xếp nhiều row để đến offset. Với truy vấn `TABLE_PER_CLASS` sinh `UNION`, chi phí trên nhiều bảng có thể càng đáng kể.

Khi cần quét nhiều Payment theo thứ tự tăng ID, có thể dùng keyset nếu ID có thứ tự toàn hierarchy phù hợp:

```java
List<Payment> next = em.createQuery(
        "select p from Payment p " +
        "where p.id > :lastSeenId " +
        "order by p.id",
        Payment.class
    )
    .setParameter("lastSeenId", lastSeenId)
    .setMaxResults(100)
    .getResultList();
```

`lastSeenId` là ID cuối của trang trước. Cách này giả định ID có so sánh thứ tự phù hợp và đủ duy nhất trên phạm vi query. Nếu sort theo nhiều thuộc tính, cursor phải phản ánh tất cả thuộc tính sắp xếp và tie-breaker.

### 14.3. Pagination không tạo snapshot bất biến

Giữa hai request, các bản ghi mới có thể được thêm vào hoặc thay đổi trạng thái. Dù dùng offset hay keyset, dữ liệu có thể thay đổi giữa các lần tải. Nếu báo cáo cần ảnh chụp thống nhất tại một thời điểm, hãy chọn transaction isolation/snapshot hoặc chiến lược báo cáo phù hợp, không mặc định JPA pagination tự cung cấp consistency đó.

## 15. Query polymorphic, fetching và nguy cơ N+1

Kết quả subtype có thể có association riêng:

```text
CardPayment
  -> cardIssuer (association)

BankTransferPayment
  -> receivingBank (association)
```

Nếu truy vấn `FROM Payment` rồi vòng lặp truy cập các association của từng subtype, provider có thể phát sinh thêm truy vấn để tải association lazy. N+1 không được giải quyết chỉ nhờ inheritance mapping.

Ví dụ:

```java
List<Payment> payments = em.createQuery(
        "select p from Payment p order by p.id",
        Payment.class
    )
    .getResultList();

for (Payment p : payments) {
    System.out.println(p.describeChannel());
    // Nếu implementation subtype truy cập association lazy,
    // có thể phát sinh thêm SQL.
}
```

Trong ví dụ entity ban đầu `describeChannel()` chỉ đọc basic fields, nên không nhất thiết có N+1. Nhưng khi phương thức nghiệp vụ được mở rộng để đọc entity liên quan, hành vi query có thể đổi.

### 15.1. Fetch join quan hệ chung

Nếu `Payment` có một association chung như `merchant`:

```java
List<Payment> payments = em.createQuery(
        "select p from Payment p " +
        "join fetch p.merchant " +
        "order by p.id",
        Payment.class
    )
    .getResultList();
```

Đoạn này giả định `Payment` có field association `merchant` được ánh xạ. `JOIN FETCH` làm association được tải cùng query theo semantics JPA; dùng `LEFT JOIN FETCH` nếu Payment có thể không có merchant và muốn giữ những Payment đó.

Các association riêng của từng subtype cần cách fetch/query tương ứng, có thể dùng entity graph/subgraph hoặc truy vấn cụ thể theo subtype. Không tự giả định fetch join association của superclass sẽ tải mọi association của mọi subtype.

### 15.2. Không lạm dụng fetch join collection cùng phân trang

Nếu một Payment có collection lớn, query `JOIN FETCH p.events` cùng `setMaxResults` có thể khiến SQL nhân số hàng hoặc provider phải phân trang trong memory. Với inheritance và nhiều subtype, kết quả càng khó kiểm soát.

Giải pháp thường là:

1. Phân trang Payment theo thuộc tính chung.
2. Chỉ tải association cần thiết cho những Payment đã chọn.
3. Dùng DTO projection hoặc query chuyên biệt cho màn hình.
4. Quan sát SQL, số row và memory thay vì chỉ đếm số câu JPQL.

## 16. SQL discriminator không phải là API để đổi kiểu entity

Trong `SINGLE_TABLE`, một row có `payment_kind = 'CARD'` có thể được provider dựng thành `CardPayment`. Nhưng ứng dụng không nên tự thay `payment_kind` từ `CARD` sang `BANK_TRANSFER` bằng SQL rồi kỳ vọng một managed entity CardPayment đang ở trong persistence context tự biến thành BankTransferPayment.

**Entity type là một phần identity và mapping của object trong runtime.** Đổi subtype của một entity đã persistent không phải thao tác cập nhật thuộc tính bình thường được JPA bảo đảm.

Nếu nghiệp vụ cần đổi phương thức thanh toán từ thẻ sang chuyển khoản, hướng thiết kế thường là:

- Tạo một entity thanh toán khác thuộc subtype phù hợp.
- Thay association tham chiếu nếu mô hình cho phép.
- Hủy/ghi lịch sử giao dịch cũ theo business rule.
- Thực hiện các thay đổi trong transaction và ràng buộc database thích hợp.

Đừng dùng việc “đổi discriminator” như một cơ chế đa hình động để thay class của object đang managed.

### 16.1. Không tự coi discriminator là thuộc tính nghiệp vụ

Discriminator chủ yếu giúp provider phân biệt kiểu mapping. Nếu ứng dụng cần một trạng thái thanh toán như `PENDING`, `CONFIRMED` hoặc `FAILED`, đó thường là **một thuộc tính nghiệp vụ riêng**, không phải discriminator.

Ví dụ, `CardPayment` và `BankTransferPayment` đều có thể ở trạng thái `PENDING`. Loại entity và trạng thái xử lý là hai chiều thông tin khác nhau.

## 17. Phạm vi truy vấn khi hierarchy có nhiều tầng

Giả sử mô hình được mở rộng:

```text
                 Payment (abstract entity)
                    /           \
                   /             \
          CardPayment         BankTransferPayment
             /                     \
       VirtualCardPayment       InternationalTransferPayment
```

Giả định mọi lớp trong sơ đồ đều được đánh dấu `@Entity` phù hợp (trừ việc Payment là abstract).

| Truy vấn | Bao gồm những kiểu nào? |
|---|---|
| `FROM Payment p` | Mọi subtype được ánh xạ trong hai nhánh |
| `FROM CardPayment c` | CardPayment và VirtualCardPayment |
| `FROM BankTransferPayment b` | BankTransferPayment và InternationalTransferPayment |
| `FROM VirtualCardPayment v` | VirtualCardPayment và các subtype nếu có |
| `FROM Payment p WHERE TYPE(p) = CardPayment` | Chỉ exact CardPayment |
| `FROM Payment p WHERE TYPE(p) IN (CardPayment, VirtualCardPayment)` | Hai entity types đã liệt kê |
| `FROM Payment p WHERE TREAT(p AS CardPayment).lastFourDigits = :digits` | Các instance thuộc nhánh CardPayment có thuộc tính phù hợp |

Ví dụ này cho thấy:

- **Root class** lựa chọn toàn nhánh kế thừa.
- **`TYPE`** lựa chọn entity type chính xác.
- **`TREAT`** cho phép thao tác trên path của subtype và các instance thuộc subtype tương ứng.
- **`SELECT`** quyết định kiểu object/giá trị được trả; `FROM` và `WHERE` quyết định phạm vi row.

### Nếu superclass không được khai báo `@Entity`?

Nếu `Payment` chỉ là một Java abstract class hoặc `@MappedSuperclass`, không thể dùng `FROM Payment` theo JPQL chuẩn để lấy mọi subclass entity. Khi cần một query root chung, phải có một **entity superclass** hợp lệ trong hierarchy (hoặc thực hiện các truy vấn riêng / union bằng cơ chế thích hợp).

## 18. Mối quan hệ giữa `find`, entity identity và polymorphic query

Truy vấn JPQL không phải cách duy nhất lấy entity. Một entity hierarchy vẫn có các thao tác `EntityManager.find` theo entity class và primary key.

Ví dụ:

```java
Payment payment = em.find(Payment.class, 10L);
```

Nếu row có ID 10 tương ứng với `CardPayment`, provider có thể trả một instance CardPayment được gán vào biến Payment. Tương tự, truy vấn polymorphic root cũng có thể trả entity đó.

Trong cùng một persistence context, JPA duy trì identity mapping để các lần tải cùng một persistence identity không tùy tiện tạo hai managed object riêng rẽ cùng đại diện cho cùng row.

### 18.1. `find` theo subtype và sự khác biệt

```java
CardPayment card = em.find(CardPayment.class, 10L);
```

Thao tác theo CardPayment chỉ có ý nghĩa khi ID đó thực sự tương ứng với entity thuộc kiểu CardPayment/subtype phù hợp. Không thể lấy BankTransferPayment rồi ép thành CardPayment chỉ vì hai entity cùng kế thừa Payment.

### 18.2. Có nên suy từ `id` ra subtype?

Không. ID chỉ xác định entity theo mapping; không nên sử dụng các dải số như “ID dưới 1000 là card, từ 1000 trở lên là bank transfer” trừ khi mô hình nghiệp vụ cố ý định nghĩa và bảo vệ điều đó. Với `SINGLE_TABLE`, provider dựa vào discriminator, không dựa vào số ID để xác định subtype.

Với `TABLE_PER_CLASS`, dữ liệu nằm ở nhiều bảng; chiến lược khóa cần bảo đảm tính nhất quán identity trong hierarchy. Thiết kế ID không đúng có thể gây vấn đề khi query root cần hợp nhất nhiều loại row.

## 19. Bulk update và delete trên entity cha có phạm vi rộng

Một rủi ro vận hành là dùng entity root trong câu **bulk mutation** mà không nhận ra nó có phạm vi đa hình.

Ví dụ:

```java
int removed = em.createQuery(
        "delete from Payment p " +
        "where p.amount < :minimum"
    )
    .setParameter("minimum", new BigDecimal("1.00"))
    .executeUpdate();
```

Về mặt query root, thao tác xét **Payment hierarchy**, chứ không chỉ các row trực tiếp của lớp cha abstract. Provider có thể phải sinh nhiều SQL statement khi inheritance dùng nhiều bảng, nhưng chủ đích logic vẫn là xóa những entity Payment thuộc phạm vi và điều kiện.

### 19.1. Không áp dụng lifecycle theo từng entity như `remove`

JPQL bulk update/delete:

- Thực hiện thao tác ở database thay vì tải từng entity rồi gọi business method.
- Không tự kích hoạt entity lifecycle callback theo từng managed instance như `@PreRemove`/`@PreUpdate` trong luồng thay đổi thông thường.
- Không tự đồng bộ tất cả instance đã managed trong persistence context; object có thể bị **stale** sau bulk operation.
- Có thể không áp dụng cascade/orphan removal JPA theo cách `em.remove(entity)`.
- Không tự áp dụng optimistic locking `@Version` của từng entity như dirty checking thông thường.

Với inheritance, phạm vi rộng còn có thể tác động nhiều subtype và nhiều bảng. Trước một bulk delete trên root, phải xác định rõ quy tắc nghiệp vụ, association FK, audit và transaction.

### 19.2. Thu hẹp khi chỉ muốn một subtype

Ví dụ:

```java
int removed = em.createQuery(
        "delete from CardPayment c " +
        "where c.amount < :minimum"
    )
    .setParameter("minimum", new BigDecimal("1.00"))
    .executeUpdate();
```

Truy vấn từ CardPayment chỉ nhằm vào nhánh này (gồm subtype của CardPayment nếu có). Điều kiện kiểu chính xác qua `TYPE` có thể hữu ích khi muốn lọc trong hierarchy; hãy xem tính hỗ trợ của provider đối với JPQL bulk mutation phức tạp và SQL thực tế, đặc biệt với `JOINED`/`TABLE_PER_CLASS`.

**Một thao tác phá hủy dữ liệu không nên lấy ranh giới subtype từ suy đoán về bảng vật lý.** Khai báo query root đúng là bước đầu tiên.

## 20. Spring Data JPA và repository kế thừa

Trong Spring Data JPA, repository được khai báo theo entity class cũng phản ánh khả năng truy vấn đa hình từ root.

Ví dụ:

```java
public interface PaymentRepository
        extends JpaRepository<Payment, Long> {

    List<Payment> findByAmountGreaterThan(BigDecimal minimum);
}
```

Nếu `Payment` là entity root, các truy vấn theo Payment có thể trả subtype entities. Một repository riêng:

```java
public interface CardPaymentRepository
        extends JpaRepository<CardPayment, Long> {

    List<CardPayment> findByLastFourDigits(String lastFourDigits);
}
```

sẽ làm việc với hierarchy CardPayment.

**Spring Data không thay đổi nguyên lý gốc của JPA**: đối tượng nào được xem là entity subtype, query root và phạm vi kiểu đều dựa trên metadata JPA. Các method như `findAll()`, `findBy...` vẫn cần phân trang/điều kiện phù hợp để tránh tải quá nhiều hàng.

### 20.1. Return type của repository và subtype runtime

`List<Payment>` do `PaymentRepository` trả có thể chứa các class con. Không phải lỗi typing. Nếu tầng API cần schema cố định để serialize, nên dùng DTO với trường phân loại rõ ràng hoặc thiết kế response polymorphic có quy tắc deserialize/serialize minh bạch, thay vì mặc định mọi Payment đều có cùng field subtype.

### 20.2. Không đưa entity proxy trực tiếp ra response

Tầng REST thường nên trả DTO/projection thay vì trực tiếp serialize một entity hierarchy có association lazy. Nếu serialize toàn bộ entity, có thể vô tình tải nhiều quan hệ, rơi vào vòng lặp bidirectional association hoặc lỗi khi persistence context đã đóng.

## 21. Chi phí thực tế của polymorphic query

Một JPQL query ngắn không đồng nghĩa một SQL query luôn rẻ:

```java
List<Payment> all = em.createQuery(
    "select p from Payment p",
    Payment.class
).getResultList();
```

Nếu `Payment` có hàng triệu row, truy vấn này có thể tốn rất nhiều bộ nhớ, bất kể strategy. Ngoài ra:

- Với `SINGLE_TABLE`, bảng rộng và nhiều cột subtype có thể làm I/O lớn.
- Với `JOINED`, truy vấn root có thể có nhiều join để dựng subtype.
- Với `TABLE_PER_CLASS`, provider có thể phải union nhiều bảng, khiến sort/count/page phức tạp hơn.
- Với association eager hoặc truy cập lazy trong vòng lặp, có thể phát sinh thêm truy vấn.
- Khi có nhiều entity subtype, metadata và SQL ngày càng phức tạp.

### 21.1. Ba mức tối ưu theo mục tiêu

| Mục tiêu | Hướng xử lý |
|---|---|
| Thực thi hành vi nghiệp vụ chung của mọi Payment | Query root Payment với điều kiện và giới hạn kết quả |
| Chỉ cần một subtype cụ thể | Query trực tiếp subclass; cân nhắc `TYPE`/`TREAT` nếu truy vấn phức tạp |
| Chỉ cần báo cáo danh sách/tổng hợp | DTO/scalar projection thay vì managed entity |

### 21.2. Quan sát SQL quan trọng hơn đoán qua JPQL

Trong quá trình tối ưu, có thể theo dõi:

1. SQL provider phát ra khi query Payment.
2. Số lượng row thực tế, join/union và lượng dữ liệu trả.
3. Kế hoạch thực thi của database (`EXPLAIN` hoặc công cụ tương đương).
4. Index phù hợp trên cột dùng để lọc/sort, bao gồm discriminator nếu có và database hưởng lợi.
5. Số statement bổ sung khi truy cập association.
6. Số managed entity trong persistence context, heap và thời gian request.

Đừng kết luận `TABLE_PER_CLASS` chậm hơn `SINGLE_TABLE` trong mọi truy vấn cụ thể: một query chỉ đọc subtype có thể tận dụng bảng riêng tốt, trong khi một query root polymorphic có thể phải union. Quyết định chiến lược cần nhìn vào **tập truy vấn thực tế** và tính chất dữ liệu, không chỉ nhìn một câu SQL.

## 22. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách hiểu/khắc phục |
|---|---|---|
| Query `FROM Payment` trả cả CardPayment và BankTransferPayment | JPQL mặc định polymorphic trong hierarchy | Chọn subtype root hoặc lọc `TYPE` nếu muốn giới hạn |
| Query entity abstract lại trả kết quả | Entity type abstract vẫn là query root hợp lệ | Kết quả là instance của concrete entity subtype |
| JPQL báo `AuditableRecord is not an entity` | Lớp chỉ có `@MappedSuperclass` | Query các entity concrete hoặc thiết kế entity superclass |
| Query `FROM CardPayment` không trả BankTransferPayment | Hai class là nhánh anh em | Muốn cả hai, query ancestor entity `Payment` |
| Lỗi path `p.lastFourDigits` | `p` có kiểu entity `Payment`, thiếu thuộc tính subtype | Chọn CardPayment root hoặc `TREAT` |
| `TYPE(p) = 'CARD'` không hoạt động portable | Nhầm entity type với discriminator string | Dùng `TYPE(p) = CardPayment` |
| Subtype mới làm tăng số loại result | Root query bao gồm toàn hierarchy | Thiết kế consumer mở rộng hoặc lọc subtype rõ ràng |
| `ClassCastException` khi cast Payment sang CardPayment | Result có nhiều subtype | Kiểm tra kiểu hoặc query subtype trực tiếp |
| `@Entity(name=...)` khiến JPQL không tìm thấy Payment | Query dùng class name thay entity name đã khai báo | Dùng entity name đúng |
| Query Payment rất chậm ở `JOINED` | Nhiều join/subtype tables/associations | Quan sát SQL, filter, DTO, index và chiến lược mapping |
| Query Payment chậm ở `TABLE_PER_CLASS` | UNION qua nhiều bảng/subtype | Chọn subtype nếu có thể, cân nhắc schema và query plan |
| Phân trang trả không ổn định | Không có order/tie-breaker, dữ liệu đổi giữa các request | `ORDER BY` xác định; cursor/snapshot khi cần |
| DTO trả cùng cấu trúc dù row khác subtype | `SELECT NEW ...` tạo DTO | Đây là semantics projection, không phải mất inheritance |
| Association `Payment` tải ra class khác class khai báo | Object runtime là subtype | Đa hình là hành vi đúng của entity relationship |
| `LAZY` không loại N+1 | Lazy được truy cập nhiều lần theo vòng lặp | Fetch plan, projection và query thích hợp |
| Bulk delete trên Payment xóa cả subtype | Query root có phạm vi polymorphic | Đặt subtype root/điều kiện kiểu và kiểm tra rủi ro |
| Đổi discriminator trong DB làm object managed không đúng | JPA không hỗ trợ đổi class runtime qua UPDATE discriminator tùy ý | Thay bằng tạo entity subtype mới/quy trình nghiệp vụ |

### 22.1. Sai: nghĩ `@Inheritance` chỉ ảnh hưởng cấu trúc bảng

Inheritance mapping còn xác định **hệ phân cấp entity type** để JPQL hiểu `Payment` gồm các subclass. Chọn strategy có thể thay SQL, nhưng không xóa khái niệm polymorphic query.

### 22.2. Sai: nghĩ query cha luôn trả đúng class cha

```java
List<Payment> result = em.createQuery(
    "select p from Payment p",
    Payment.class
).getResultList();
```

`Payment` chỉ là **kiểu khai báo**; instance có thể là bất kỳ subtype entity phù hợp.

### 22.3. Sai: query `@MappedSuperclass` để tổng hợp mọi lớp con

```java
String wrong = "select a from AuditableRecord a";
```

Nếu lớp cha chỉ có `@MappedSuperclass`, nó không phải query root. Muốn truy vấn một hierarchy thống nhất, cần mô hình entity root hoặc cơ chế truy vấn tổng hợp khác.

### 22.4. Sai: trả tất cả Payment rồi lọc kiểu ở Java

```java
List<Payment> all = em.createQuery(
    "select p from Payment p",
    Payment.class
).getResultList();

List<CardPayment> cards = all.stream()
    .filter(CardPayment.class::isInstance)
    .map(CardPayment.class::cast)
    .toList();
```

Cách này có thể tải rất nhiều entity không cần thiết. Khi chỉ cần CardPayment, query trực tiếp `FROM CardPayment` hoặc lọc ở JPQL.

### 22.5. Sai: dựa vào thứ tự type trong database

Nếu query không có `ORDER BY`, database không bảo đảm CardPayment luôn đứng trước BankTransferPayment, ngay cả khi `SINGLE_TABLE` lưu cùng bảng hoặc các ID được sinh tăng. Không viết nghiệp vụ phụ thuộc thứ tự tình cờ đó.

## 23. Tình huống thiết kế: màn hình quản lý nhiều phương thức thanh toán

Giả sử ứng dụng có giao diện quản trị gồm ba tab:

1. **Tất cả thanh toán:** xem tổng hợp ngày, số tiền và trạng thái xử lý.
2. **Thanh toán bằng thẻ:** tìm theo bốn chữ số cuối.
3. **Chuyển khoản:** tìm theo mã tham chiếu ngân hàng.

### Tab tất cả: polymorphic root + DTO

```java
List<PaymentSummary> page = em.createQuery(
        "select new example.billing.api.PaymentSummary(" +
        "p.id, p.amount) " +
        "from Payment p order by p.id",
        PaymentSummary.class
    )
    .setFirstResult(0)
    .setMaxResults(50)
    .getResultList();
```

Tab này lấy cả CardPayment và BankTransferPayment. Vì chỉ cần ID/số tiền, DTO giúp tránh tải entity đầy đủ để hiển thị.

### Tab thẻ: subtype root

```java
List<CardPayment> cards = em.createQuery(
        "select c from CardPayment c " +
        "where c.lastFourDigits = :digits " +
        "order by c.id",
        CardPayment.class
    )
    .setParameter("digits", "4242")
    .setMaxResults(50)
    .getResultList();
```

Truy vấn dùng trường đặc thù của CardPayment mà không cần `TREAT` vì query root đã là subtype.

### Tab chuyển khoản: subtype root

```java
List<BankTransferPayment> transfers = em.createQuery(
        "select t from BankTransferPayment t " +
        "where t.bankReference = :reference",
        BankTransferPayment.class
    )
    .setParameter("reference", "TXN-001")
    .setMaxResults(50)
    .getResultList();
```

### Khi thêm một subtype mới

Nếu hệ thống thêm `MobileWalletPayment`:

- Tab **tất cả** dựa vào `FROM Payment` tự có khả năng bao gồm subtype mới (nếu entity được đăng ký).
- Tab **thẻ** vẫn chỉ quan tâm nhánh CardPayment.
- Tab **chuyển khoản** vẫn chỉ quan tâm nhánh BankTransferPayment.
- Nếu API cần biểu diễn loại thanh toán, phải cập nhật chính sách projection/serialization hoặc logic hiển thị tương ứng; đừng giả định hệ phân cấp luôn cố định ở hai loại.

Đây chính là giá trị của việc chọn query root và phạm vi kiểu có chủ đích.

## 24. Bài tập thực hành

### Bài tập A: động vật nuôi và inheritance

Thiết kế:

```text
Animal (@Entity abstract)
  ├─ Dog (@Entity)
  └─ Cat (@Entity)
```

Hãy xác định kiểu có thể xuất hiện trong kết quả:

```java
em.createQuery("select a from Animal a", Animal.class)
    .getResultList();

em.createQuery("select d from Dog d", Dog.class)
    .getResultList();
```

**Gợi ý:** query Animal là polymorphic, lấy Dog và Cat; query Dog chỉ lấy Dog và subtype của Dog nếu có.

### Bài tập B: abstract entity và mapped superclass

Có hai khai báo:

```java
@Entity
abstract class Document { /*...*/ }

@MappedSuperclass
abstract class Auditable { /*...*/ }
```

Hãy giải thích vì sao `FROM Document` hợp lệ khi Document được đăng ký là entity, còn `FROM Auditable` không hợp lệ theo JPQL chuẩn. Điều gì sẽ thay đổi nếu `Document` là một class concrete entity?

### Bài tập C: phân biệt `TYPE` và `TREAT`

Một hierarchy:

```text
Payment
  ├─ CardPayment
  |    └─ VirtualCardPayment
  └─ BankTransferPayment
```

Hãy xác định khác biệt giữa:

```java
String q1 = "select p from Payment p where TYPE(p) = CardPayment";
String q2 = "select c from CardPayment c";
String q3 = "select p from Payment p " +
            "where TREAT(p AS CardPayment).lastFourDigits = :digits";
```

**Gợi ý:** `TYPE` kiểm tra entity type chính xác; root CardPayment gồm mọi mapped subtype; `TREAT` cho phép dùng attribute của CardPayment để lọc theo điều kiện.

### Bài tập D: đọc SQL theo inheritance strategy

Giả sử đã có ba Payment subtype với một triệu row, trong đó đa số là BankTransferPayment. Hãy phân tích truy vấn `FROM Payment` và `FROM CardPayment` dưới ba chiến lược `SINGLE_TABLE`, `JOINED` và `TABLE_PER_CLASS`.

**Gợi ý:** phạm vi kiểu theo JPQL vẫn giữ nguyên, nhưng SQL có thể là đọc bảng chung, join bảng subtype hoặc union những bảng concrete. Hãy xem index và query plan trước khi quyết định.

### Bài tập E: chọn projection cho dashboard

Dashboard cần tổng số payment và 50 payment gần nhất, chỉ hiển thị ID, số tiền. Hãy so sánh:

```java
SELECT p FROM Payment p
SELECT COUNT(p) FROM Payment p
SELECT NEW example.billing.api.PaymentSummary(p.id, p.amount)
       FROM Payment p ORDER BY p.id DESC
```

**Gợi ý:** chỉ lấy entity khi thực sự cần lifecycle/hành vi entity; đếm bằng COUNT, hiển thị bảng bằng DTO có phân trang.

## 25. Câu hỏi tự kiểm tra

**1. Query `FROM Payment` có trả các subclass entity không?**

Có. Một JPQL root là entity superclass mặc định có phạm vi đa hình: bao gồm class được chọn và các entity subtype đã được ánh xạ.

**2. Nếu `Payment` là `abstract @Entity`, query đó có hợp lệ không?**

Có. Payment là entity type có thể truy vấn; kết quả gồm các concrete subtype, không có instance trực tiếp của abstract Payment.

**3. `@MappedSuperclass` có được truy vấn như entity root không?**

Không. Nó chia sẻ metadata mapping nhưng không là entity type có identity riêng và không có JPQL root độc lập.

**4. `FROM CardPayment` có lấy BankTransferPayment không?**

Không. Hai class là nhánh anh em. Query CardPayment chỉ xét CardPayment và subtype của nó.

**5. `TypedQuery<Payment>` có bảo đảm `p.getClass() == Payment.class` cho từng kết quả không?**

Không. Kiểu khai báo Payment cho phép trả instance của subclass, và một số provider còn dùng proxy/enhancement.

**6. `TYPE(p) = CardPayment` tương đương với `FROM CardPayment` trong hierarchy nhiều tầng không?**

Không hoàn toàn. `TYPE` là so sánh entity type chính xác; root CardPayment còn có thể bao gồm entity subtype của CardPayment.

**7. Dùng `TYPE(p) = 'CARD'` có portable không?**

Không. `'CARD'` là discriminator string trong ví dụ; JPQL `TYPE` so sánh với entity type literal như `CardPayment`.

**8. `TREAT` dùng để làm gì?**

Nó cho phép biểu thức path có kiểu superclass được điều hướng theo một subtype để dùng thuộc tính/mapping riêng của subtype trong JPQL/Criteria.

**9. `SINGLE_TABLE`, `JOINED`, `TABLE_PER_CLASS` có làm đổi tập entity type mà `FROM Payment` bao gồm không?**

Không về semantics đa hình cơ bản. Chúng chủ yếu thay cách lưu bảng và cách provider sinh SQL, dù hiệu năng/tính năng cụ thể có thể khác nhau.

**10. `SELECT NEW PaymentSummary(...) FROM Payment` trả entity Payment hay DTO?**

Trả DTO `PaymentSummary`. Phạm vi đọc row vẫn đa hình theo root Payment, nhưng object kết quả không được JPA quản lý như entity.

**11. Association `Invoice.payment` có kiểu Payment có tham chiếu CardPayment được không?**

Có, vì CardPayment là subtype của Payment. Runtime entity được nạp phù hợp với mapping/discriminator.

**12. Vì sao truy vấn một entity superclass trong inheritance dễ tác động rộng khi bulk delete?**

Vì query root gồm cả subtype được ánh xạ. Bulk delete từ superclass có thể xóa những row thuộc nhiều loại thực thể và không chạy các lifecycle callbacks như xóa từng managed entity.

**13. Chỉ dùng `LAZY` có bảo đảm không có N+1 khi xử lý kết quả đa hình không?**

Không. Truy cập association của từng subclass có thể phát sinh SQL bổ sung; cần thiết kế fetch plan/query/projection.

**14. Nếu mới thêm một entity subclass và `FROM Payment` không thấy nó, cần nghĩ tới điều gì?**

Kiểm tra entity đó đã được ánh xạ và đăng ký trong persistence unit chưa, dữ liệu/migration đã có chưa, query có filter loại nó không, và provider đang dùng có hỗ trợ cấu hình inheritance tương ứng không.

**15. Vì sao không nên đổi trực tiếp cột discriminator để chuyển CardPayment sang BankTransferPayment?**

Vì đổi entity type không phải thao tác thay thuộc tính managed thông thường. Nó làm lệch mapping và trạng thái của object hiện tại; nên dùng workflow tạo/thay entity đúng loại theo nghiệp vụ.

## 26. Tổng kết

**Truy vấn đa hình trong JPA bắt đầu từ một entity type và mặc định bao gồm các entity subclass của nó trong cùng hierarchy.** Vì vậy, `FROM Payment` có thể trả CardPayment, BankTransferPayment và các nhánh con khác; còn `FROM CardPayment` thu hẹp phạm vi vào nhánh CardPayment. Một entity superclass `abstract` vẫn là query root hợp lệ, nhưng `@MappedSuperclass` thì không.

Để xác định chính xác phạm vi kết quả:

1. **Chọn query root đúng**: ancestor entity khi cần nhiều loại, concrete/subtype entity khi chỉ cần một nhánh.
2. **Dùng `TYPE`** khi cần so sánh exact entity type hoặc chọn tập entity types cụ thể.
3. **Dùng `TREAT`** khi cần truy cập thuộc tính riêng của subtype trong câu query bắt đầu từ superclass/association có kiểu cha.
4. **Phân biệt typed entity query với DTO/scalar projection**: `List<Payment>` có thể chứa nhiều subclass; `SELECT NEW` tạo DTO, không tạo managed entity.
5. **Hiểu inheritance strategy tác động tới SQL**: `SINGLE_TABLE`, `JOINED` và `TABLE_PER_CLASS` giữ ngữ nghĩa đa hình cơ bản nhưng có chi phí bảng/joins/unions khác nhau.
6. **Kiểm soát hiệu năng và phạm vi thao tác**: giới hạn kết quả, sắp xếp ổn định, xem fetch plan và cẩn trọng khi bulk update/delete từ superclass.

Khi nhận thức rằng **kiểu khai báo của câu query không nhất thiết là class runtime chính xác của mỗi phần tử**, ta có thể xây dựng repository, service và API linh hoạt trước việc bổ sung subtype mới, mà vẫn tránh các lỗi ép kiểu và các truy vấn quá rộng ngoài ý định.
