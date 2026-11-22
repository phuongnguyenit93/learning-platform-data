# Vai trò của cột phân biệt và giá trị phân biệt trong kế thừa JPA

## 1. Vì sao JPA cần cột phân biệt khi lưu các lớp kế thừa?

Trong Java, **kế thừa** cho phép nhiều kiểu đối tượng có chung thuộc tính và hành vi. Ví dụ hệ thống thanh toán có lớp cơ sở `Payment`, cùng các lớp con `CardPayment` và `BankTransferPayment`:

```text
                    Payment
               (id, amount)
                   /    \
                  /      \
       CardPayment        BankTransferPayment
       (cardLastFour)     (bankReference)
```

Tại thời điểm chạy, một biến kiểu `Payment` có thể chứa đối tượng `CardPayment` hoặc `BankTransferPayment`. Khi dữ liệu được lưu trong database, **JPA provider cần biết mỗi hàng thuộc kiểu entity cụ thể nào để tạo đúng đối tượng Java khi đọc**.

Với chiến lược kế thừa **`SINGLE_TABLE`**, các lớp trong cùng một entity hierarchy được lưu **chung một bảng**. Một hàng có thể mang dữ liệu của thẻ, hàng khác mang dữ liệu chuyển khoản. Vì cùng bảng nên chỉ nhìn `id` và `amount` chưa đủ biết hàng đó là kiểu con nào.

Đây là lúc **discriminator column — cột phân biệt** phát huy tác dụng:

```text
payments
+----+----------+--------------+----------------+----------------+
| id | amount   | payment_kind | card_last_four | bank_reference |
+----+----------+--------------+----------------+----------------+
| 11 | 120000   | CARD         | 1234           | NULL           |
| 12 | 350000   | BANK         | NULL           | TXN-2026-001   |
| 13 |  50000   | CARD         | 9876           | NULL           |
+----+----------+--------------+----------------+----------------+

payment_kind = "CARD" -> CardPayment
payment_kind = "BANK" -> BankTransferPayment
```

**Cột phân biệt** chứa một mã thể hiện loại entity của hàng. **Giá trị phân biệt** là mã cụ thể được ánh xạ cho mỗi lớp trong hierarchy.

JPA cung cấp hai annotation quan trọng:

- **`@DiscriminatorColumn`**: cấu hình tên và loại dữ liệu của cột phân biệt.
- **`@DiscriminatorValue`**: cấu hình giá trị dùng để nhận diện một entity class cụ thể.

Hai annotation được dùng trong ngữ cảnh **kế thừa entity** và metadata ORM. Chúng **không** phải annotation dùng để tự động tạo khóa chính, cũng không tương đương cột trạng thái nghiệp vụ.

## 2. Ba chiến lược kế thừa và vị trí của discriminator

Trước khi chọn cột phân biệt, cần hiểu ba chiến lược ánh xạ kế thừa chuẩn JPA.

| Chiến lược | Cách lưu dữ liệu | Vai trò của discriminator |
|---|---|---|
| `InheritanceType.SINGLE_TABLE` | Toàn bộ hierarchy dùng **một bảng**. | **Đặc biệt quan trọng** để xác định loại entity của từng hàng trong cùng bảng. |
| `InheritanceType.JOINED` | Lớp cơ sở có bảng riêng; lớp con có bảng riêng, thường nối với bảng cha bằng khóa chính/khóa ngoại. | **Có thể sử dụng** discriminator; không phải mô hình nào cũng cần cột này vì kiểu con có thể suy ra từ các bảng được join. |
| `InheritanceType.TABLE_PER_CLASS` | Mỗi lớp entity cụ thể có bảng riêng chứa cả những thuộc tính được kế thừa. | **Không dùng discriminator theo mô hình chuẩn này**; nguồn bảng giúp xác định kiểu entity. |

Sơ đồ ý tưởng:

```text
SINGLE_TABLE
payments
  id | kind | amount | card_last_four | bank_reference
   1 | CARD | ...
   2 | BANK | ...

JOINED
payments           card_payments           bank_payments
  id | amount       payment_id | last4      payment_id | reference
   1 | ...     <---     1 | 1234
   2 | ...     <--------------------------    2 | TXN-...

TABLE_PER_CLASS
card_payments                  bank_payments
  id | amount | last4            id | amount | reference
   1 | ...    | 1234             2 | ...    | TXN-...
```

`SINGLE_TABLE` là chiến lược mặc định cho một hierarchy entity khi không chỉ định `@Inheritance` theo quy tắc JPA. Dù vậy, trong bài học và dự án thực tế nên khai báo `@Inheritance(strategy = InheritanceType.SINGLE_TABLE)` tường minh để người đọc không phải đoán.

**Trọng tâm bài này là discriminator trong `SINGLE_TABLE`**, sau đó mở rộng sang `JOINED` và các điểm khác biệt của `TABLE_PER_CLASS`.

## 3. `@DiscriminatorColumn`: định nghĩa cột nhận diện loại entity

### 3.1. Khai báo trên lớp gốc của entity hierarchy

Với mô hình thanh toán, `Payment` là entity gốc (*root entity*):

```java
import jakarta.persistence.DiscriminatorColumn;
import jakarta.persistence.DiscriminatorType;
import jakarta.persistence.Entity;
import jakarta.persistence.Inheritance;
import jakarta.persistence.InheritanceType;
import jakarta.persistence.Table;

@Entity
@Table(name = "payments")
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(
    name = "payment_kind",
    discriminatorType = DiscriminatorType.STRING,
    length = 16
)
public abstract class Payment {
    // Các thuộc tính chung.
}
```

`@DiscriminatorColumn` được đặt trên **root của entity hierarchy**, nơi JPA xác định cách lưu cả nhóm lớp kế thừa.

Các thuộc tính chính của annotation:

| Thuộc tính | Ý nghĩa |
|---|---|
| `name` | Tên cột discriminator trong bảng, ví dụ `payment_kind`. |
| `discriminatorType` | Kiểu giá trị phân biệt: `STRING`, `CHAR` hoặc `INTEGER`. |
| `length` | Chiều dài cột khi sử dụng `DiscriminatorType.STRING`. |
| `columnDefinition` | SQL fragment mô tả kiểu cột khi cần DDL riêng của database; có thể làm giảm tính di động. |

Giả sử cấu hình:

```java
@DiscriminatorColumn(
    name = "payment_kind",
    discriminatorType = DiscriminatorType.STRING,
    length = 16
)
```

Provider thường tạo cột SQL tương tự:

```sql
payment_kind VARCHAR(16)
```

Kiểu SQL chính xác và ràng buộc được sinh ra phụ thuộc provider, SQL dialect và chế độ schema generation.

### 3.2. Mặc định của cột discriminator

Khi dùng `SINGLE_TABLE` nhưng không khai báo `@DiscriminatorColumn`, provider có thể sử dụng metadata mặc định theo quy tắc của Jakarta Persistence; các thiết lập thông dụng là:

- Tên cột: **`DTYPE`**.
- Loại discriminator: **`DiscriminatorType.STRING`**.
- Độ dài chuỗi mặc định của `@DiscriminatorColumn`: **31** ký tự.

Ví dụ:

```java
@Entity
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
public abstract class Payment {
    // Không khai báo @DiscriminatorColumn.
}
```

Khi đó một schema do JPA tạo có thể có cột:

```sql
DTYPE VARCHAR(31)
```

Dù tên mặc định được hỗ trợ, **đặt tên tường minh có lợi khi database cần được quản lý qua migration hoặc chia sẻ với ứng dụng khác**. Một cột tên `payment_kind` dễ hiểu hơn `DTYPE` đối với DBA và các hệ thống đọc SQL trực tiếp.

### 3.3. Tại sao annotation thường chỉ khai báo một lần?

Cả hierarchy dùng chung một cơ chế phân biệt kiểu. Nếu mỗi subclass tự chọn cột discriminator khác nhau, các hàng trong một bảng không còn được xác định bằng một quy ước thống nhất.

Vì vậy:

- Đặt `@Inheritance` và `@DiscriminatorColumn` trên **root entity**.
- Dùng `@DiscriminatorValue` ở root và/hoặc các subclass nếu cần chọn mã cụ thể.
- Không đặt `@DiscriminatorColumn` độc lập trên từng subclass để cố thay đổi cột nhận diện cho từng nhánh cùng hierarchy.

Cách này giúp các lớp con thống nhất một ánh xạ:

```text
Payment
  @DiscriminatorColumn(name="payment_kind")
                 |
           payment_kind
            /       \
           /         \
         CARD        BANK
          |            |
     CardPayment   BankTransferPayment
```

## 4. `@DiscriminatorValue`: gắn một giá trị với một entity class

`@DiscriminatorValue` cho biết giá trị nào trong cột discriminator đại diện cho một lớp entity.

Ví dụ:

```java
@Entity
@DiscriminatorValue("CARD")
public class CardPayment extends Payment {
    // ...
}
```

và:

```java
@Entity
@DiscriminatorValue("BANK")
public class BankTransferPayment extends Payment {
    // ...
}
```

Khi provider ghi một `CardPayment` vào bảng `payments`, nó dùng giá trị `CARD` cho cột `payment_kind`. Khi đọc một hàng có `payment_kind = 'BANK'`, provider biết hàng đó thuộc `BankTransferPayment`.

### 4.1. `@DiscriminatorValue` dùng chuỗi ngay cả với kiểu số

Thuộc tính `value` của `@DiscriminatorValue` có kiểu Java `String` trong annotation. Nếu discriminator column là `INTEGER`, giá trị khai báo vẫn viết trong dấu ngoặc kép:

```java
@DiscriminatorColumn(
    name = "kind_code",
    discriminatorType = DiscriminatorType.INTEGER
)
```

```java
@DiscriminatorValue("1")
public class CardPayment extends Payment {
    // ...
}
```

```java
@DiscriminatorValue("2")
public class BankTransferPayment extends Payment {
    // ...
}
```

Provider diễn giải chuỗi `"1"`, `"2"` thành giá trị số phù hợp khi ánh xạ sang cột `INTEGER`.

Với `DiscriminatorType.CHAR`, các giá trị phải tương ứng một ký tự:

```java
@DiscriminatorColumn(
    name = "kind_code",
    discriminatorType = DiscriminatorType.CHAR
)
```

```java
@DiscriminatorValue("C") // Thẻ.
```

```java
@DiscriminatorValue("B") // Chuyển khoản.
```

Không dùng ký tự đa chữ cái như `"CARD"` cho cột discriminator kiểu `CHAR` nếu nó được thiết kế chỉ lưu một ký tự.

### 4.2. Điều gì xảy ra nếu không khai báo `@DiscriminatorValue`?

Với discriminator dạng `STRING`, JPA có quy tắc mặc định dựa trên **entity name**. Entity name mặc định thường là tên lớp Java đơn giản; nếu khai báo `@Entity(name = "...")`, tên entity dùng trong JPQL sẽ thay đổi.

Ví dụ:

```java
@Entity(name = "CardMethod")
public class CardPayment extends Payment {
    // Không khai báo @DiscriminatorValue.
}
```

Trong cơ chế mặc định dùng entity name, giá trị discriminator dự kiến là `CardMethod`, **không nhất thiết là `CardPayment`**.

Với `INTEGER` và `CHAR`, không nên suy đoán giá trị mặc định giữa các provider. Khi muốn schema ổn định và dễ vận hành, **khai báo giá trị tường minh cho từng subclass** thay vì để những giá trị nhận diện lâu dài phụ thuộc cách đặt tên entity hoặc quyết định của provider.

### 4.3. Giá trị của mỗi lớp phải phân biệt

Trong cùng hierarchy, mỗi kiểu entity cụ thể cần một discriminator value không xung đột:

```text
CARD -> CardPayment
BANK -> BankTransferPayment
CASH -> CashPayment
```

Cấu hình sai về ý nghĩa:

```java
@Entity
@DiscriminatorValue("CARD")
public class CardPayment extends Payment {}

@Entity
@DiscriminatorValue("CARD") // Trùng với CardPayment.
public class BankTransferPayment extends Payment {}
```

Provider có thể báo xung đột metadata, hoặc không thể xác định một hàng `CARD` phải được ánh xạ về lớp nào. Hãy xem discriminator value như **một mã định danh kiểu trong schema**, có phạm vi và quy ước ổn định.

### 4.4. Giá trị dành cho lớp root

Nếu root entity là lớp **concrete** và có thể lưu bản ghi trực tiếp, nó cũng cần được nhận diện riêng. Có thể cấu hình:

```java
@Entity
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(name = "payment_kind")
@DiscriminatorValue("BASE")
public class Payment {
    // ...
}
```

Khi lưu trực tiếp một `Payment`, hàng có thể chứa `payment_kind = 'BASE'`.

Nếu root là `abstract` như ví dụ chính, ứng dụng không tạo instance trực tiếp bằng `new Payment(...)`. Trong trường hợp đó, các hàng thường thuộc những subclass cụ thể. Việc khai báo discriminator value riêng cho root abstract không phải lúc nào cũng cần thiết, nhưng các subclass vẫn cần ánh xạ rõ ràng.

## 5. Ví dụ entity hoàn chỉnh với `SINGLE_TABLE`

Bộ mã ví dụ sau dùng Java và Jakarta Persistence. Toàn bộ các entity được ánh xạ vào **một bảng `payments`**.

### 5.1. Root entity `Payment`

```java
package com.example.payment;

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
    length = 16
)
public abstract class Payment {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "amount", nullable = false,
            precision = 15, scale = 2)
    private BigDecimal amount;

    protected Payment() {
        // Constructor không tham số cho JPA.
    }

    protected Payment(BigDecimal amount) {
        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException(
                "Số tiền thanh toán phải dương"
            );
        }
        this.amount = amount;
    }

    public Long getId() {
        return id;
    }

    public BigDecimal getAmount() {
        return amount;
    }
}
```

Phân tích:

- `Payment` là entity root nhưng `abstract`: không tạo trực tiếp object Payment.
- `@Inheritance(strategy = SINGLE_TABLE)`: các subtype dùng chung bảng.
- `@DiscriminatorColumn(...)`: chỉ định cột nhận biết loại payment.
- `@Id` và `@GeneratedValue` ở root: mọi subtype cùng dùng một cơ chế identity trên bảng `payments`.
- `amount` là thuộc tính chung, có trong mọi hàng, nên `nullable = false` phù hợp.

### 5.2. Subclass `CardPayment`

```java
package com.example.payment;

import jakarta.persistence.Column;
import jakarta.persistence.DiscriminatorValue;
import jakarta.persistence.Entity;

@Entity
@DiscriminatorValue("CARD")
public class CardPayment extends Payment {

    @Column(name = "card_last_four", length = 4)
    private String cardLastFour;

    protected CardPayment() {
        // Constructor cho JPA.
    }

    public CardPayment(BigDecimal amount, String cardLastFour) {
        super(amount);
        if (cardLastFour == null
                || !cardLastFour.matches("[0-9]{4}")) {
            throw new IllegalArgumentException(
                "Cần đúng 4 chữ số cuối của thẻ"
            );
        }
        this.cardLastFour = cardLastFour;
    }

    public String getCardLastFour() {
        return cardLastFour;
    }
}
```

Trong source file thực tế, cần import `java.math.BigDecimal`.

Chỉ lưu bốn chữ số cuối để minh họa metadata của phương thức thanh toán; đây **không phải** thiết kế đầy đủ cho xử lý thông tin thẻ. Thông tin thanh toán nhạy cảm đòi hỏi hệ thống xử lý an toàn và các yêu cầu tuân thủ riêng.

### 5.3. Subclass `BankTransferPayment`

```java
package com.example.payment;

import jakarta.persistence.Column;
import jakarta.persistence.DiscriminatorValue;
import jakarta.persistence.Entity;
import java.math.BigDecimal;

@Entity
@DiscriminatorValue("BANK")
public class BankTransferPayment extends Payment {

    @Column(name = "bank_reference", length = 64)
    private String bankReference;

    protected BankTransferPayment() {
        // Constructor cho JPA.
    }

    public BankTransferPayment(
            BigDecimal amount,
            String bankReference
    ) {
        super(amount);
        if (bankReference == null || bankReference.isBlank()) {
            throw new IllegalArgumentException(
                "Mã tham chiếu ngân hàng không hợp lệ"
            );
        }
        this.bankReference = bankReference;
    }

    public String getBankReference() {
        return bankReference;
    }
}
```

Một lưu ý quan trọng: **không đặt `nullable = false` trên các cột chỉ dành cho một subtype** khi dùng bảng chung, nếu các subtype khác phải có `NULL` ở cột đó.

Trong bảng `payments`:

- Hàng `CARD` có thể có `card_last_four` và `bank_reference = NULL`.
- Hàng `BANK` có thể có `bank_reference` và `card_last_four = NULL`.

Do đó `card_last_four` và `bank_reference` được phép NULL ở **cấp schema chung**, dù constructor của từng subclass kiểm tra chúng bắt buộc tại **cấp nghiệp vụ của subtype đó**.

## 6. DDL và dữ liệu của bảng đơn

DDL minh họa cho hệ quản trị hỗ trợ cú pháp identity tương ứng:

```sql
CREATE TABLE payments (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    payment_kind VARCHAR(16) NOT NULL,
    amount DECIMAL(15, 2) NOT NULL,
    card_last_four VARCHAR(4),
    bank_reference VARCHAR(64)
);
```

Các cột có vai trò:

| Cột | Vai trò | Dữ liệu dự kiến |
|---|---|---|
| `id` | Khóa chính chung cho mọi entity trong hierarchy. | `1`, `2`, `3`, ... |
| `payment_kind` | **Cột phân biệt**. | `CARD`, `BANK`. |
| `amount` | Thuộc tính chung được khai báo ở `Payment`. | `120000.00`, `350000.00`. |
| `card_last_four` | Thuộc tính riêng của `CardPayment`. | `1234` với hàng CARD, NULL với hàng BANK. |
| `bank_reference` | Thuộc tính riêng của `BankTransferPayment`. | NULL với hàng CARD, `TXN-2026-001` với hàng BANK. |

Các hàng có thể trông như sau:

```sql
-- Chỉ minh họa hình dạng dữ liệu sau khi JPA persist,
-- không phải cách khuyến nghị để thay thế thao tác EntityManager.
INSERT INTO payments
    (payment_kind, amount, card_last_four, bank_reference)
VALUES
    ('CARD', 120000.00, '1234', NULL);

INSERT INTO payments
    (payment_kind, amount, card_last_four, bank_reference)
VALUES
    ('BANK', 350000.00, NULL, 'TXN-2026-001');
```

Tùy provider và database, SQL `INSERT` thực tế có thể khác về tên cột, vị trí ID hoặc cách bind parameters. Điều quan trọng là **cột discriminator được gán phù hợp với lớp Java được persist**.

### 6.1. Bảo vệ tính nhất quán theo subtype bằng constraint

Nếu database cần bảo vệ các cột dành riêng cho mỗi kiểu, có thể cân nhắc các ràng buộc `CHECK` (nếu RDBMS hỗ trợ):

```sql
ALTER TABLE payments
ADD CONSTRAINT ck_payment_kind
CHECK (payment_kind IN ('CARD', 'BANK'));

ALTER TABLE payments
ADD CONSTRAINT ck_card_has_last_four
CHECK (
    payment_kind <> 'CARD'
    OR card_last_four IS NOT NULL
);

ALTER TABLE payments
ADD CONSTRAINT ck_bank_has_reference
CHECK (
    payment_kind <> 'BANK'
    OR bank_reference IS NOT NULL
);
```

Các constraint này chỉ minh họa **những điều kiện tối thiểu**. Chúng không tự bảo đảm các cột không liên quan luôn NULL, không kiểm tra đầy đủ định dạng reference và phải được mở rộng khi thêm subtype mới.

Không nên dựa vào JPA metadata để tự sinh toàn bộ business constraint theo subtype. Những ràng buộc đặc biệt cần được thiết kế và đưa vào migration schema rõ ràng.

## 7. Lưu và đọc entity có discriminator

### 7.1. Persist các lớp con

Giả sử `EntityManagerFactory emf` đã cấu hình cho persistence unit `RESOURCE_LOCAL`:

```java
EntityManager em = emf.createEntityManager();

try {
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        Payment card = new CardPayment(
            new BigDecimal("120000.00"),
            "1234"
        );

        Payment bank = new BankTransferPayment(
            new BigDecimal("350000.00"),
            "TXN-2026-001"
        );

        em.persist(card);
        em.persist(bank);

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
```

Code này cần các import `jakarta.persistence.EntityManager`, `jakarta.persistence.EntityTransaction` và `java.math.BigDecimal`.

Ứng dụng tạo các instance theo kiểu thực tế:

- `new CardPayment(...)` → provider dùng discriminator value `CARD`.
- `new BankTransferPayment(...)` → provider dùng discriminator value `BANK`.

**Ứng dụng không tự gọi `setPaymentKind("CARD")`.** Discriminator là metadata do JPA provider quản lý dựa trên **loại entity của đối tượng**, không phải một field mà domain tùy ý thay đổi.

### 7.2. Đọc theo root type

```java
List<Payment> payments = em.createQuery(
    "SELECT p FROM Payment p ORDER BY p.id",
    Payment.class
).getResultList();

for (Payment payment : payments) {
    if (payment instanceof CardPayment card) {
        System.out.println(
            "CARD: " + card.getCardLastFour()
        );
    } else if (payment instanceof BankTransferPayment bank) {
        System.out.println(
            "BANK: " + bank.getBankReference()
        );
    }
}
```

Truy vấn `FROM Payment` là **đa hình** (*polymorphic*): nó có thể trả về cả `CardPayment` và `BankTransferPayment`. Provider dựa vào discriminator để khôi phục đúng subtype trong bộ nhớ.

Ngay cả khi `Payment` là `abstract`, vẫn có thể query entity root. Kết quả chứa những instance thuộc các entity subclass cụ thể.

Đừng hiểu `SELECT p FROM Payment p` là chỉ lấy những hàng có discriminator của riêng lớp `Payment`. Theo semantics truy vấn entity inheritance, root query bao gồm các subtype phù hợp.

### 7.3. Đọc theo subclass

```java
List<CardPayment> cards = em.createQuery(
    "SELECT c FROM CardPayment c",
    CardPayment.class
).getResultList();
```

Với `SINGLE_TABLE`, provider có thể thêm điều kiện dựa trên discriminator, ví dụ ý tưởng SQL:

```sql
SELECT p.*
FROM payments p
WHERE p.payment_kind = 'CARD';
```

Đây là SQL minh họa. Provider có thể dùng predicate khác, nhất là khi hierarchy có nhiều mức hoặc query sử dụng polymorphism.

### 7.4. `EntityManager.find` theo khóa và kiểu entity

Một hàng `payments.id = 11` với `payment_kind = CARD` đại diện cho `CardPayment`. Có thể truy vấn:

```java
Payment payment = em.find(Payment.class, 11L);
```

JPA provider dùng discriminator để tạo đúng subtype. Khóa chính vẫn là `id = 11`, không cần tổ hợp `(id, payment_kind)` để làm entity ID.

Trong bảng chung, khóa chính là **duy nhất trên toàn hierarchy**, nên không thể có hàng CARD `id = 11` và hàng BANK `id = 11` tồn tại đồng thời.

## 8. Discriminator trong JPQL: `TYPE`, `TREAT` và polymorphism

### 8.1. `TYPE(entity)` kiểm tra loại entity

JPQL cung cấp biểu thức `TYPE` để lọc theo kiểu entity:

```java
List<Payment> cardPayments = em.createQuery(
    """
    SELECT p
    FROM Payment p
    WHERE TYPE(p) = CardPayment
    """,
    Payment.class
).getResultList();
```

`CardPayment` ở đây là tên entity trong mô hình JPA, không phải chuỗi discriminator value `"CARD"`.

Provider có thể hiện thực phép lọc bằng điều kiện trên `payment_kind` khi dùng `SINGLE_TABLE`, nhưng cách viết JPQL vẫn là **dựa trên entity type**, không dựa trên tên cột SQL.

Một truy vấn khác:

```java
List<Payment> result = em.createQuery(
    """
    SELECT p
    FROM Payment p
    WHERE TYPE(p) IN (CardPayment, BankTransferPayment)
    """,
    Payment.class
).getResultList();
```

Điểm có lợi là code truy vấn không bị ràng buộc trực tiếp với mã SQL `CARD` hoặc `BANK` nếu business không cần dùng đến chúng.

### 8.2. `TREAT` để truy cập thuộc tính riêng của subtype

Khi query từ root, `Payment` không khai báo `cardLastFour` nên không thể viết `p.cardLastFour` trực tiếp theo kiểu tĩnh của JPQL.

Có thể dùng `TREAT` để xem một instance root như subtype:

```java
List<Payment> found = em.createQuery(
    """
    SELECT p
    FROM Payment p
    WHERE TREAT(p AS CardPayment).cardLastFour = :lastFour
    """,
    Payment.class
)
.setParameter("lastFour", "1234")
.getResultList();
```

`TREAT(p AS CardPayment)` cho phép truy cập thuộc tính `cardLastFour` chỉ xuất hiện ở `CardPayment`. Tính tương thích và SQL tối ưu phụ thuộc provider/JPA version/dialect, nhưng đây là cú pháp JPQL dành cho truy vấn đa hình theo subtype.

Nếu ứng dụng chỉ muốn dữ liệu thẻ, cách viết `FROM CardPayment` thường đơn giản hơn.

### 8.3. Không nhầm `TYPE` với cột discriminator SQL

| Mục tiêu | Cách làm |
|---|---|
| Chọn tất cả payments theo hệ phân cấp | `SELECT p FROM Payment p` |
| Chọn entity đúng subtype | `SELECT c FROM CardPayment c` |
| Lọc theo kiểu ở mức JPQL | `WHERE TYPE(p) = CardPayment` |
| Truy cập trường riêng của subtype từ root | `TREAT(p AS CardPayment).cardLastFour` |
| Đọc báo cáo bằng SQL trực tiếp | Query cột thực `payment_kind` và giá trị `CARD`, `BANK` |

**`TYPE(p) = CardPayment` là điều kiện theo type của JPA; `payment_kind = 'CARD'` là điều kiện dữ liệu SQL.** Chúng có thể tương ứng trong schema hiện tại nhưng không phải cú pháp thay thế cho nhau trong cùng một ngôn ngữ truy vấn.

## 9. `@Entity(name)`, tên bảng và giá trị discriminator là ba thứ khác nhau

Một nguồn nhầm lẫn thường gặp là cùng một entity có nhiều loại tên:

```java
@Entity(name = "CardTxn")
@DiscriminatorValue("CARD")
public class CardPayment extends Payment {
    // ...
}
```

Nếu root dùng:

```java
@Table(name = "payments")
```

thì:

| Tên | Giá trị | Mục đích |
|---|---|---|
| Java class | `CardPayment` | Kiểu đối tượng và kế thừa trong Java. |
| Entity name | `CardTxn` | Tên được dùng trong JPQL khi gọi entity trực tiếp. |
| Table name | `payments` | Bảng SQL dùng chung của hierarchy `SINGLE_TABLE`. |
| Discriminator column | `payment_kind` | Cột SQL nhận diện subtype. |
| Discriminator value | `CARD` | Mã SQL dành cho `CardPayment`. |

Truy vấn JPQL:

```java
SELECT c FROM CardTxn c
```

khác với SQL:

```sql
SELECT * FROM payments WHERE payment_kind = 'CARD';
```

Việc đổi `@Entity(name)` không tự đổi `@DiscriminatorValue("CARD")` khi value đã được khai báo tường minh. Đây là một lợi ích quan trọng của **discriminator value ổn định**: tên Java/entity có thể được refactor mà **không bắt buộc đổi dữ liệu discriminator**.

Ngược lại, nếu dựa vào giá trị mặc định bằng entity name cho discriminator kiểu STRING, đổi `@Entity(name)` có thể ảnh hưởng khả năng đọc những hàng đã tồn tại. Vì vậy nên đặt value cụ thể khi schema là hợp đồng dữ liệu lâu dài.

## 10. Cột discriminator không phải một field nghiệp vụ bình thường

Dù cột `payment_kind` nằm trong database, không nhất thiết khai báo một field `String paymentKind` trong entity để điều khiển nó.

Cách phổ biến:

```java
@Entity
@DiscriminatorValue("CARD")
public class CardPayment extends Payment {
    // Không có String paymentKind;
}
```

Provider biết subtype qua **runtime Java class và mapping metadata**. Nếu khai báo thêm:

```java
@Column(name = "payment_kind")
private String paymentKind;
```

trên cùng hierarchy mà không có thiết kế đặc biệt, provider có thể phát hiện ánh xạ trùng cột hoặc tạo hai nguồn có khả năng ghi vào cùng dữ liệu. Điều này không cần thiết để dùng inheritance mapping chuẩn.

Nếu API cần trả về loại payment, có thể trình bày nó qua một phương thức domain hoặc DTO:

```java
public String typeLabel(Payment payment) {
    if (payment instanceof CardPayment) {
        return "CARD";
    }
    if (payment instanceof BankTransferPayment) {
        return "BANK";
    }
    throw new IllegalArgumentException("Loại thanh toán chưa hỗ trợ");
}
```

Đây là ví dụ đơn giản về **representation ở tầng ứng dụng**; không làm thay đổi cột discriminator. Trong hệ thống thật, có thể dùng thiết kế DTO hoặc cơ chế type mapping phù hợp để giảm các nhánh `instanceof`.

### 10.1. Có thể sửa discriminator trực tiếp để đổi entity type không?

Không nên thực hiện:

```sql
UPDATE payments
SET payment_kind = 'BANK'
WHERE id = 11;
```

nếu hàng `11` thực chất là CardPayment với dữ liệu `card_last_four`. Đổi discriminator chỉ thay mã phân loại, **không tự chuyển dữ liệu nghiệp vụ và object graph sang cấu trúc của subtype mới**.

Khi đọc lại, provider có thể tạo `BankTransferPayment` nhưng `bank_reference` bị NULL hoặc không hợp lệ. Nếu persistence context đang giữ `CardPayment` của cùng ID, việc sửa SQL ngoài JPA còn làm state trong bộ nhớ khác với database.

**Kiểu entity sau khi persist nên được xem là ổn định.** Nếu một thanh toán phải đổi phương thức xử lý, thường phù hợp hơn khi mô hình hóa **trạng thái/chi tiết xử lý** hoặc tạo entity phù hợp theo quy tắc nghiệp vụ, thay vì cưỡng ép đổi cột discriminator.

## 11. Phân biệt discriminator với enum trạng thái nghiệp vụ

Một entity thanh toán có thể có **loại thanh toán** và **trạng thái xử lý**:

```text
payment_kind = CARD | BANK
status       = PENDING | COMPLETED | FAILED
```

Hai thông tin khác nhau:

- `payment_kind` là discriminator do JPA inheritance sử dụng để xác định **Java entity subtype**.
- `status` là state nghiệp vụ thay đổi được trong vòng đời của cùng một entity.

Ví dụ:

```java
public enum PaymentStatus {
    PENDING, COMPLETED, FAILED
}
```

```java
@Enumerated(EnumType.STRING)
@Column(name = "status", nullable = false, length = 16)
private PaymentStatus status;
```

Một `CardPayment` vẫn là `CardPayment` khi trạng thái chuyển từ `PENDING` sang `COMPLETED`. `@DiscriminatorValue("CARD")` không đổi.

Không dùng discriminator để lưu mọi trạng thái biến động của hệ thống. Nếu tạo subclass `PendingPayment`, `CompletedPayment` chỉ để phản ánh trạng thái, ứng dụng có thể phải thay đổi Java type của một entity khi state chuyển đổi — điều không phù hợp với mô hình identity/persistence thông thường.

### 11.1. Khi nào inheritance là lựa chọn hợp lý?

Inheritance thích hợp khi subtype có cấu trúc và hành vi **khác nhau theo loại đối tượng**:

- `CardPayment` có thông tin phương thức thẻ.
- `BankTransferPayment` có mã tham chiếu chuyển khoản.
- Các loại thanh toán có logic xử lý chuyên biệt.

Nếu tất cả payments chỉ khác một enum `paymentMethod` và không có cấu trúc/hành vi riêng đáng kể, một entity `Payment` có field enum có thể đơn giản hơn inheritance. Discriminator không phải giải pháp bắt buộc chỉ vì muốn lưu một mã phân loại.

## 12. Discriminator trong `JOINED`

### 12.1. Dữ liệu nằm ở những bảng nào?

Với `JOINED`, mỗi subclass có bảng riêng chứa thuộc tính riêng. Bảng root giữ các thuộc tính chung:

```text
payments
+----+----------+--------------+
| id | amount   | payment_kind |
+----+----------+--------------+
| 11 | 120000   | CARD         |
| 12 | 350000   | BANK         |
+----+----------+--------------+
       |                  |
       |                  |
       v                  v
card_payments       bank_payments
+------------+      +------------+----------------+
| payment_id |      | payment_id | bank_reference |
| last_four  |      +------------+----------------+
+------------+      | 12         | TXN-2026-001   |
| 11         |      +------------+----------------+
| 1234       |
+------------+
```

Trong trường hợp này, subtype có thể được xác định từ bảng con tương ứng sau khi join. Vì thế **`JOINED` không nhất thiết cần cột discriminator trong mọi cấu hình JPA**, nhưng có thể dùng để biểu diễn loại entity trong bảng root hoặc giúp provider xử lý subtype theo ánh xạ đã chọn.

### 12.2. Khai báo thay thế cho `JOINED`

Đây là một **biến thể thiết kế khác**, không đặt cùng lúc với bộ entity `SINGLE_TABLE` trước đó:

```java
@Entity
@Table(name = "payments")
@Inheritance(strategy = InheritanceType.JOINED)
@DiscriminatorColumn(
    name = "payment_kind",
    discriminatorType = DiscriminatorType.STRING,
    length = 16
)
public abstract class Payment {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private BigDecimal amount;

    protected Payment() {}
}
```

Subclass:

```java
@Entity
@Table(name = "card_payments")
@PrimaryKeyJoinColumn(name = "payment_id")
@DiscriminatorValue("CARD")
public class CardPayment extends Payment {

    @Column(name = "last_four", length = 4)
    private String cardLastFour;

    protected CardPayment() {}
}
```

Trong source thật cần các import thuộc `jakarta.persistence` và `java.math.BigDecimal`.

Với `@PrimaryKeyJoinColumn(name = "payment_id")`, khóa chính ở `card_payments` cũng là FK đến `payments.id` theo cấu trúc JOINED. Provider có thể lưu một CardPayment bằng thao tác ghi vào **cả bảng root và bảng subclass**.

Khi dùng discriminator trong JOINED, cấu hình value phải thống nhất với các hàng ở bảng root và các bản ghi subclass. Không nên tự sửa discriminator mà bỏ qua hàng ở bảng con.

### 12.3. Điểm cân nhắc hiệu năng

`SINGLE_TABLE` thường dễ đọc dữ liệu root vì không phải join bảng subtype để phân loại hàng, nhưng có thể tạo **nhiều cột nullable**. `JOINED` chuẩn hóa các thuộc tính riêng vào bảng con và có thể giảm nhiều ô NULL, nhưng truy vấn đa hình có thể cần **join nhiều bảng** hoặc SQL phức tạp hơn.

Không nên cho rằng thêm `@DiscriminatorColumn` vào JOINED chắc chắn sẽ loại bỏ mọi join. Provider vẫn cần đọc các cột riêng của subtype khi tạo object đầy đủ.

## 13. Vì sao `TABLE_PER_CLASS` không dùng cùng mô hình discriminator?

Với `TABLE_PER_CLASS`, các lớp cụ thể được lưu ở bảng riêng và bao gồm các trường được kế thừa:

```text
card_payments
+----+----------+----------------+
| id | amount   | card_last_four |
+----+----------+----------------+

bank_payments
+----+----------+----------------+
| id | amount   | bank_reference |
+----+----------+----------------+
```

Cùng một hàng chỉ nằm trong một bảng subtype, nên bảng đã cho biết nó là loại nào. Không có một cột discriminator chung trong một bảng duy nhất như `SINGLE_TABLE`.

Ví dụ dạng tối giản:

```java
@Entity
@Inheritance(strategy = InheritanceType.TABLE_PER_CLASS)
public abstract class Payment {
    @Id
    private Long id;

    // Thuộc tính chung...
}
```

Các entity con có bảng riêng. Khi query `FROM Payment`, provider có thể cần thực hiện truy vấn kết hợp dữ liệu từ nhiều bảng (ví dụ qua SQL `UNION`, tùy provider).

Với `TABLE_PER_CLASS`, phải đặc biệt cân nhắc **chiến lược sinh ID duy nhất trên toàn hierarchy**. Việc dùng hai identity column độc lập ở hai bảng có thể tạo cùng giá trị ID cho hai entity trong những trường hợp mà mô hình JPA/provider yêu cầu danh tính không xung đột khi truy vấn đa hình.

Discriminator column không giải quyết vấn đề sinh khóa ở nhiều bảng. Nếu dùng `TABLE_PER_CLASS`, hãy thiết kế ID generator và truy vấn theo đúng khả năng của provider/database.

## 14. Root entity và `@MappedSuperclass`: không nhầm hai kiểu kế thừa

JPA phân biệt:

1. **Entity inheritance hierarchy**: root và subclass là `@Entity`, có thể dùng `@Inheritance` và discriminator thích hợp.
2. **`@MappedSuperclass`**: lớp cơ sở cung cấp các mapping kế thừa nhưng **không phải entity độc lập để query**.

Ví dụ:

```java
@MappedSuperclass
public abstract class BaseRecord {
    @Id
    private Long id;
}
```

```java
@Entity
public class Customer extends BaseRecord {
    private String name;
}
```

`BaseRecord` không tự tạo một entity hierarchy có query root `FROM BaseRecord` và không cần discriminator riêng. `Customer` thừa hưởng mapping ID, nhưng không vì thế mà có bảng `BaseRecord` chứa discriminator.

Ngược lại:

```java
@Entity
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(name = "record_kind")
public abstract class BaseRecord {
    @Id
    private Long id;
}
```

```java
@Entity
@DiscriminatorValue("CUSTOMER")
public class Customer extends BaseRecord {
    private String name;
}
```

lúc này `BaseRecord` là entity root có thể được truy vấn đa hình; discriminator xác định hàng trong hierarchy.

**Chọn `@MappedSuperclass` khi chỉ cần tái sử dụng mapping**, không cần polymorphic entity query/lifecycle cho superclass. Chọn `@Entity` root với `@Inheritance` khi hierarchy thực sự là một mô hình entity kế thừa.

## 15. Cấu hình persistence unit và ví dụ Java SE

Một file `src/main/resources/META-INF/persistence.xml` minh họa để chạy các entity `Payment`, `CardPayment` và `BankTransferPayment` với H2:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             version="3.1">
    <persistence-unit name="paymentsPU"
                      transaction-type="RESOURCE_LOCAL">
        <class>com.example.payment.Payment</class>
        <class>com.example.payment.CardPayment</class>
        <class>com.example.payment.BankTransferPayment</class>

        <properties>
            <property name="jakarta.persistence.jdbc.driver"
                      value="org.h2.Driver"/>
            <property name="jakarta.persistence.jdbc.url"
                      value="jdbc:h2:mem:payments;DB_CLOSE_DELAY=-1"/>
            <property name="jakarta.persistence.jdbc.user" value="sa"/>
            <property name="jakarta.persistence.jdbc.password" value=""/>
            <property
                name="jakarta.persistence.schema-generation.database.action"
                value="drop-and-create"/>
        </properties>
    </persistence-unit>
</persistence>
```

Cần Jakarta Persistence API, một provider tương thích và JDBC driver H2. Với container Jakarta EE hoặc Spring Boot, cách đăng ký entity có thể dựa vào quét class/package hoặc cấu hình framework; semantics của discriminator vẫn do JPA mapping quản lý.

**`drop-and-create` chỉ dành cho thực hành** vì có thể xóa toàn bộ dữ liệu cũ. Trong production, dùng migration quản lý cột `payment_kind`, các bảng và constraint theo phiên bản ứng dụng.

Khởi tạo factory trong Java SE:

```java
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.Persistence;

EntityManagerFactory emf =
        Persistence.createEntityManagerFactory("paymentsPU");

try {
    // Tạo EntityManager, persist/find/query.
} finally {
    emf.close();
}
```

Provider cần phát hiện **toàn bộ các entity subclass** trong hierarchy. Nếu thiếu đăng ký một subclass, một hàng có discriminator value tương ứng có thể không được nhận diện đúng khi đọc.

## 16. Dữ liệu legacy và quá trình thêm cột discriminator

Giả sử ứng dụng trước đây có một bảng `payments` chỉ chứa `id`, `amount` và `payment_method` là chuỗi nghiệp vụ:

```text
payments
+----+----------+----------------+
| id | amount   | payment_method |
+----+----------+----------------+
| 11 | 120000   | card           |
| 12 | 350000   | bank_transfer  |
+----+----------+----------------+
```

Ứng dụng mới chuyển sang hierarchy `CardPayment` / `BankTransferPayment` và cần cột `payment_kind` với giá trị `CARD` / `BANK`.

**Chỉ thêm annotation vào mã Java chưa đủ**. Khi đọc dữ liệu hiện hữu, provider phải có giá trị discriminator đúng theo mapping; nếu column chưa tồn tại hoặc các hàng chưa được cập nhật, query có thể lỗi.

### 16.1. Tạo cột và điền giá trị phân biệt

Một migration ý tưởng:

```sql
ALTER TABLE payments
ADD COLUMN payment_kind VARCHAR(16);

UPDATE payments
SET payment_kind = CASE
    WHEN payment_method = 'card' THEN 'CARD'
    WHEN payment_method = 'bank_transfer' THEN 'BANK'
    ELSE NULL
END;
```

Sau đó cần xác định cách xử lý các hàng còn NULL hoặc mã lạ, chuyển dữ liệu subtype vào những cột cần thiết, rồi mới đặt `NOT NULL`/`CHECK` nếu đó là constraint nghiệp vụ. Cú pháp SQL migration cụ thể khác nhau giữa các RDBMS; thao tác này phải có phương án thử nghiệm và rollback phù hợp.

Nếu cột `payment_method` cũ vẫn được dùng bởi nhiều ứng dụng, cần kế hoạch chuyển đổi phiên bản để tránh ghi lệch giữa hai cơ chế.

### 16.2. Đổi discriminator value là thay đổi hợp đồng dữ liệu

Giả sử trước đây dùng:

```java
@DiscriminatorValue("CARD")
```

Sau này đổi thành:

```java
@DiscriminatorValue("CARD_PAYMENT")
```

Nếu database vẫn có hàng `payment_kind = 'CARD'`, provider theo mapping mới có thể không nhận diện được loại entity của các hàng cũ. Một migration có kiểm soát có thể cần:

```sql
UPDATE payments
SET payment_kind = 'CARD_PAYMENT'
WHERE payment_kind = 'CARD';
```

Nhưng việc cập nhật phải xét các ứng dụng khác còn đọc giá trị cũ, độ dài cột `payment_kind` và constraint hiện có. Nếu đổi từ `CARD` sang `CARD_PAYMENT`, `length = 16` vẫn phù hợp; nếu dùng value dài hơn, phải điều chỉnh độ dài cột tương ứng.

**Không đổi discriminator value chỉ để làm đẹp tên** nếu không có kế hoạch migration. Giá trị này có thể là hợp đồng lưu trữ của nhiều năm dữ liệu.

### 16.3. Thêm một subtype mới

Giả sử thêm `WalletPayment` với:

```java
@Entity
@DiscriminatorValue("WALLET")
public class WalletPayment extends Payment {
    // Thuộc tính riêng của ví điện tử.
}
```

Trong `SINGLE_TABLE`, cần:

1. Bảo đảm lớp mới được provider tìm thấy.
2. Bổ sung các cột subtype nếu có.
3. Mở rộng `CHECK(payment_kind IN (...))` khi database có constraint.
4. Bảo đảm hệ thống đọc/ghi hỗ trợ mã `WALLET`, kể cả các ứng dụng chạy phiên bản cũ trong giai đoạn rolling deployment.
5. Cân nhắc index, report, API serialization và các quy tắc nghiệp vụ liên quan.

Thêm subclass là thay đổi cả **mô hình Java và hợp đồng dữ liệu** chứ không chỉ là thêm một file source.

## 17. Dữ liệu discriminator không hợp lệ hoặc thiếu

Một số lỗi thường gặp:

| Giá trị cột | Kỳ vọng | Vấn đề |
|---|---|---|
| `CARD` | `CardPayment` | Hợp lệ nếu mapping có `@DiscriminatorValue("CARD")`. |
| `BANK` | `BankTransferPayment` | Hợp lệ nếu mapping có `@DiscriminatorValue("BANK")`. |
| `CARDD` | Không có entity tương ứng. | Có thể gây lỗi đọc entity hoặc hành vi không được mong muốn. |
| `NULL` | Không có mã loại. | Có thể không xác định được subtype theo mapping; nên kiểm soát schema/dữ liệu. |
| `CARD_PAYMENT` | Mã mới chưa được mọi phiên bản ứng dụng hỗ trợ. | Nguy cơ không tương thích khi triển khai nhiều phiên bản. |

Không nên mặc định provider sẽ tự chọn một subtype hợp lệ nếu giá trị discriminator không nhận biết được. Tùy provider, kết quả có thể là exception hoặc hành vi riêng của implementation. Với yêu cầu portable, cần giữ dữ liệu đúng mapping và constraint.

Một công cụ kiểm tra dữ liệu có thể dùng SQL:

```sql
SELECT payment_kind, COUNT(*) AS total
FROM payments
GROUP BY payment_kind
ORDER BY payment_kind;
```

Nếu chỉ cho phép `CARD` và `BANK`:

```sql
SELECT id, payment_kind
FROM payments
WHERE payment_kind IS NULL
   OR payment_kind NOT IN ('CARD', 'BANK');
```

Đây là các truy vấn vận hành để tìm dữ liệu bất thường, không phải bước bắt buộc của JPA. Các hệ quản trị có collation không phân biệt hoa/thường có thể so sánh chuỗi theo quy tắc riêng; nên dùng mã canonical nhất quán ngay khi ghi.

## 18. Các lỗi cấu hình thường gặp

| Lỗi / triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| Cùng bảng có nhiều kiểu payment nhưng khi đọc không ra đúng subclass | Thiếu metadata inheritance/discriminator, entity chưa được phát hiện hoặc giá trị DB sai. | Kiểm tra root `@Inheritance`, cột `@DiscriminatorColumn`, `@DiscriminatorValue` và đăng ký subclass. |
| Provider báo không tìm thấy cột `DTYPE` | Root dùng mặc định nhưng schema thật có cột tên khác. | Đặt `@DiscriminatorColumn(name = "payment_kind")` khớp schema. |
| Giá trị `CARD` bị từ chối vì cột quá ngắn | `length` hoặc DDL không đủ cho discriminator value. | Chọn độ dài đủ lớn, migration cột và constraint. |
| Hai subclass đều dùng `@DiscriminatorValue("CARD")` | Giá trị discriminator không duy nhất. | Dùng mã riêng cho từng entity type trong hierarchy. |
| Đổi tên entity rồi dữ liệu cũ không đọc được | Discriminator kiểu STRING dựa vào entity name mặc định. | Dùng `@DiscriminatorValue` tường minh và migration nếu đổi mã. |
| Cố đặt `@DiscriminatorColumn` trên mọi subclass | Nhầm phạm vi annotation với `@DiscriminatorValue`. | Đặt discriminator column trên root entity. |
| DB có cột `payment_kind` nhưng JPA báo duplicate column mapping | Vừa dùng discriminator metadata, vừa ánh xạ một field writable tới cùng cột. | Để provider quản lý discriminator; không ánh xạ ghi trùng không cần thiết. |
| Dùng `@Enumerated` để thay `@DiscriminatorValue` | Nhầm enum state với identity của subclass. | Chọn inheritance mapping cho Java subtype; enum cho trạng thái/loại nghiệp vụ thông thường. |
| `@Column(nullable = false)` trên field chỉ thuộc CardPayment làm INSERT BankPayment lỗi | Bảng `SINGLE_TABLE` cần cột subtype cho phép NULL đối với hàng loại khác. | Đặt nullability phù hợp và dùng `CHECK` phụ thuộc discriminator nếu cần. |
| Thêm subtype nhưng bị lỗi `CHECK` | Constraint DB chỉ cho phép các mã cũ. | Migrate constraint và schema trước/đồng bộ với rollout. |
| `FROM Payment` trả nhiều loại object | Đây là polymorphic query, không phải lỗi. | Dùng `FROM CardPayment` hoặc `TYPE(p)` khi chỉ muốn một subtype. |
| Truy vấn JPQL `p.payment_kind = 'CARD'` không hợp lệ | `payment_kind` là tên cột SQL, không phải thuộc tính entity. | Dùng `TYPE(p) = CardPayment` hoặc SQL native. |
| Đổi giá trị discriminator bằng SQL nhưng object đang managed vẫn là subtype cũ | Thay đổi ngoài persistence context và thay đổi phân loại không phải entity lifecycle bình thường. | Không đổi discriminator thủ công; thiết kế migration/quy tắc entity mới. |
| Dùng `TABLE_PER_CLASS` rồi chờ cột `DTYPE` trong một bảng root | Cách lưu mỗi lớp một bảng không dùng discriminator chung như SINGLE_TABLE. | Chọn chiến lược kế thừa trước, cấu hình discriminator đúng phạm vi. |
| Dùng `@MappedSuperclass` rồi query polymorphic root | Mapped superclass không phải entity. | Nếu cần polymorphic entity root, dùng `@Entity` với inheritance mapping phù hợp. |
| Một hàng có mã discriminator lạ | Dữ liệu cũ hoặc ứng dụng khác ghi mã chưa đăng ký. | Kiểm tra bản đồ giá trị, constraint và kế hoạch tương thích phiên bản. |

## 19. Một số lưu ý về tối ưu truy vấn

### 19.1. Lọc subtype và index

Với `SINGLE_TABLE`, một truy vấn thường gặp là:

```sql
SELECT *
FROM payments
WHERE payment_kind = 'CARD';
```

Nếu bảng lớn và thường xuyên lọc theo loại payment, có thể cân nhắc index:

```sql
CREATE INDEX ix_payments_kind
ON payments(payment_kind);
```

Tuy nhiên, không phải cứ có discriminator column là index này hữu ích. Nếu có rất ít loại và số hàng mỗi loại rất lớn, optimizer có thể chọn scan thay vì index. Lựa chọn phụ thuộc phân bố dữ liệu, kích thước bảng, điều kiện lọc kết hợp và database.

Nếu thường lọc theo loại và khoảng thời gian:

```sql
SELECT *
FROM payments
WHERE payment_kind = 'CARD'
  AND created_at >= ?;
```

một index ghép `(payment_kind, created_at)` có thể được đánh giá theo workload. Đừng tự thêm cột `created_at` chỉ để dùng index; đó là ví dụ mở rộng khi entity thực sự có thời điểm tạo.

### 19.2. Polymorphic query và chi phí hydrate object

Truy vấn `FROM Payment` với `SINGLE_TABLE` có thể trả nhiều cột riêng của subclass. Nếu hierarchy có hàng chục subtype, bảng dễ trở nên rộng và chứa rất nhiều NULL. Provider cần đọc discriminator để quyết định lớp đích và tạo đúng object.

Khi truy vấn chỉ cần các trường chung như `id` và `amount`, có thể dùng projection DTO hoặc scalar query:

```java
List<Object[]> rows = em.createQuery(
    "SELECT p.id, p.amount FROM Payment p",
    Object[].class
).getResultList();
```

Cách này tránh buộc API phải trả về toàn bộ object graph của các subtype nếu không cần. Nhưng nó cũng không tạo ra entity managed `Payment` như truy vấn `SELECT p`; cần chọn đúng theo use case.

### 19.3. Discriminator không phải cơ chế phân quyền

Lọc `WHERE TYPE(p) = CardPayment` chỉ chọn entity type; nó **không thay thế quyền truy cập của người dùng**. Nếu hệ thống multi-tenant, phải có ràng buộc tenant và kiểm soát quyền độc lập.

Không nên dùng discriminator như một hàng rào bảo mật để ngăn xem dữ liệu thuộc tài khoản khác. Nó chỉ làm nhiệm vụ nhận diện kiểu Java.

## 20. Hướng dẫn lựa chọn và đặt mã discriminator

Một quy trình thiết kế thực tế:

**Bước 1 — Xác định có thực sự cần inheritance.** Các subtype có cấu trúc/hành vi khác nhau và cần query polymorphic không? Nếu chỉ là một enum trạng thái, cân nhắc một entity và enum trước.

**Bước 2 — Chọn inheritance strategy.** Nếu nhiều subtype có ít trường riêng, `SINGLE_TABLE` thường đơn giản; nếu nhiều trường riêng và cần phân tách schema, cân nhắc `JOINED`; `TABLE_PER_CLASS` có đánh đổi riêng về query/ID.

**Bước 3 — Đặt tên cột.** Dùng tên có ý nghĩa như `payment_kind`, `document_type` hoặc `notification_type`, tránh phụ thuộc vào cột mặc định khi schema cần được quản lý lâu dài.

**Bước 4 — Chọn discriminator type.** `STRING` thường dễ đọc trong SQL và migration; `INTEGER` gọn nhưng kém trực quan; `CHAR` phù hợp khi có mã một ký tự đã thống nhất.

**Bước 5 — Gán mã tường minh.** Sử dụng những giá trị ổn định như `CARD`, `BANK`, `CASH`. Không gắn mã trực tiếp với tên class có thể refactor.

**Bước 6 — Kiểm tra độ dài và constraint.** Độ dài cột phải đủ cho mã dài nhất; khi dùng `SINGLE_TABLE`, các cột riêng của subtype thường phải NULL được ở hàng thuộc loại khác.

**Bước 7 — Thiết kế migration và rollout.** Trước khi đổi mã hoặc thêm subtype, cần tính tới dữ liệu cũ, code cũ đang chạy và các nguồn ghi SQL ngoài JPA.

**Bước 8 — Đánh giá truy vấn.** Root query, subtype query, `TYPE` và `TREAT` có semantics khác nhau; chọn theo nhu cầu, kiểm soát số bản ghi và kích thước dữ liệu đọc.

### Ví dụ bộ mã ổn định

| Java entity | Discriminator value | Lý do chọn |
|---|---|---|
| `CardPayment` | `CARD` | Mã ngắn, thể hiện phương thức thẻ. |
| `BankTransferPayment` | `BANK` | Mã ngắn, không phụ thuộc tên class Java. |
| `CashPayment` | `CASH` | Có thể thêm vào hierarchy và constraint khi cần. |
| `WalletPayment` | `WALLET` | Có thể được triển khai như một subtype mới. |

Giá trị discriminator nên được quản lý như **một phần schema contract**, giống cách ứng dụng quản lý mã enum lưu trong database: không đổi tùy tiện mà bỏ qua dữ liệu lịch sử.

## 21. Câu hỏi tự kiểm tra

**1. Cột phân biệt có nhiệm vụ gì trong `SINGLE_TABLE`?**

Nó lưu một mã để JPA provider nhận biết mỗi hàng của bảng chung tương ứng với entity class nào trong hierarchy.

**2. `@DiscriminatorColumn` và `@DiscriminatorValue` khác nhau như thế nào?**

`@DiscriminatorColumn` đặt tên/kiểu cột chứa thông tin phân biệt; `@DiscriminatorValue` gắn một giá trị cụ thể với entity class.

**3. Vì sao không cần thêm discriminator vào primary key?**

Khóa chính vẫn nhận diện hàng duy nhất trong bảng chung; discriminator giúp nhận biết **subtype**, không phải định danh bổ sung cho hàng.

**4. Nếu không đặt `@DiscriminatorColumn` trong `SINGLE_TABLE`, tên cột thường là gì?**

Giá trị mặc định chuẩn thường là `DTYPE` với loại `STRING`. Đặt tên rõ như `payment_kind` giúp tương thích schema dễ hơn.

**5. `@DiscriminatorValue("CARD")` có nghĩa lớp CardPayment có một field String tên CARD không?**

Không. Đó là metadata ánh xạ loại entity tới giá trị trong cột discriminator do provider quản lý.

**6. `@DiscriminatorValue("1")` có hợp lệ với discriminator kiểu `INTEGER` không?**

Có. Thuộc tính annotation là `String`, provider diễn giải `"1"` như mã số khi cột có `DiscriminatorType.INTEGER`.

**7. Vì sao trong `SINGLE_TABLE` cột `card_last_four` thường phải nullable?**

Vì hàng `BankTransferPayment` không có thuộc tính đó. Nếu đặt NOT NULL vô điều kiện, insert các hàng BANK có thể thất bại.

**8. `SELECT p FROM Payment p` chỉ lấy những hàng thuộc lớp Payment gốc?**

Không. Query root là polymorphic và có thể lấy các subclass cụ thể như CardPayment, BankTransferPayment.

**9. Khi muốn chỉ lấy CardPayment trong JPQL, có những cách nào?**

Dùng `FROM CardPayment` hoặc lọc `WHERE TYPE(p) = CardPayment` từ root.

**10. Trong `JOINED` có bắt buộc dùng discriminator không?**

Không phải mọi cấu hình JOINED đều cần discriminator. Subtype có thể được suy ra từ bảng con; một số mapping/provider vẫn có thể sử dụng discriminator nếu được cấu hình.

**11. Vì sao không dùng discriminator trong `TABLE_PER_CLASS` theo cách giống `SINGLE_TABLE`?**

Vì mỗi subtype có bảng riêng và bảng có thể xác định loại entity; không có một bảng chung yêu cầu cột mã phân loại cho mọi hàng.

**12. Nếu đổi `@DiscriminatorValue("CARD")` thành `"CARD_PAYMENT"` thì cần lưu ý gì?**

Dữ liệu cũ có thể còn `CARD` nên cần kế hoạch migration, cập nhật độ dài/constraint và bảo đảm các phiên bản ứng dụng đang chạy đọc được định dạng mới.

**13. Có nên dùng discriminator để biểu diễn trạng thái PENDING/COMPLETED không?**

Thường không. Trạng thái thay đổi trong vòng đời một entity nên là thuộc tính nghiệp vụ, ví dụ enum; discriminator biểu diễn **kiểu entity**.

**14. Tại sao `@MappedSuperclass` không tự tạo cột discriminator?**

Vì mapped superclass không phải entity có thể truy vấn độc lập trong một entity inheritance hierarchy; nó chỉ cung cấp mapping kế thừa.

**15. Có thể chuyển CardPayment thành BankTransferPayment bằng cách update `payment_kind` không?**

Không nên. Thay mã không tự biến các cột/đối tượng Java theo đúng subtype; có nguy cơ làm dữ liệu và persistence context không nhất quán.

## 22. Tổng kết

Trong **kế thừa JPA**, discriminator là cơ chế nối giữa **kiểu đối tượng Java** và **biểu diễn của hàng trong cơ sở dữ liệu**.

- **`@DiscriminatorColumn`** xác định cột chứa mã nhận diện subtype; đặt ở root entity của hierarchy.
- **`@DiscriminatorValue`** gán mã cụ thể cho từng entity class trong hierarchy.
- Với **`SINGLE_TABLE`**, các lớp cùng dùng một bảng nên discriminator giúp provider chọn đúng subtype khi đọc và ghi.
- Với **`JOINED`**, có thể dùng discriminator tùy mapping; bảng subclass cũng có thể góp phần xác định subtype.
- Với **`TABLE_PER_CLASS`**, mỗi lớp cụ thể dùng bảng riêng nên không sử dụng discriminator chung theo cách của SINGLE_TABLE.
- Giá trị discriminator là **metadata của entity type**, không phải trường trạng thái nghiệp vụ hay khóa chính, và không nên thay bằng SQL tùy tiện.
- Khi schema đã có dữ liệu, đổi tên cột hoặc mã phân biệt đòi hỏi **migration** và kế hoạch tương thích với các phiên bản ứng dụng.

Mẫu dễ nhớ:

```java
@Entity
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(
    name = "payment_kind",
    discriminatorType = DiscriminatorType.STRING,
    length = 16
)
public abstract class Payment {
    @Id
    private Long id;
}

@Entity
@DiscriminatorValue("CARD")
public class CardPayment extends Payment {
    // ...
}

@Entity
@DiscriminatorValue("BANK")
public class BankTransferPayment extends Payment {
    // ...
}
```

Khi đọc một hàng có `payment_kind = 'CARD'`, provider biết phải khôi phục **`CardPayment`**; với `'BANK'`, provider khôi phục **`BankTransferPayment`**. Đó là vai trò cốt lõi của **cột phân biệt và giá trị phân biệt** trong ánh xạ kế thừa JPA.

### Tài liệu tham khảo

- [Jakarta Persistence — đặc tả chính thức](https://jakarta.ee/specifications/persistence/)
- [Jakarta Persistence API — `@DiscriminatorColumn`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/discriminatorcolumn)
- [Jakarta Persistence API — `@DiscriminatorValue`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/discriminatorvalue)
- [Jakarta Persistence API — `@Inheritance`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/inheritance)
