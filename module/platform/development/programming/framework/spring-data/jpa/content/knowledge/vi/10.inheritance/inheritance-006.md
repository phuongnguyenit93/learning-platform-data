# Cấu hình @Inheritance, @DiscriminatorColumn và @DiscriminatorValue

## Mục tiêu

Kế thừa trong Java cho phép một class con nhận thuộc tính và hành vi từ class cha. Trong JPA, khi một entity class kế thừa entity class khác, ta cần chọn cách ánh xạ cây kế thừa đó xuống các bảng quan hệ.

JPA cung cấp ba chiến lược chính qua `@Inheritance`:

- `SINGLE_TABLE`: toàn bộ hierarchy lưu trong một bảng.
- `JOINED`: class cha và mỗi class con lưu ở bảng riêng, liên kết bằng khóa chính/khóa ngoại.
- `TABLE_PER_CLASS`: mỗi concrete entity class có bảng riêng, chứa cả thuộc tính kế thừa.

Với `SINGLE_TABLE` và `JOINED`, discriminator có thể giúp phân biệt loại entity trong hierarchy. Ta khai báo cột discriminator bằng `@DiscriminatorColumn` và giá trị của từng entity class bằng `@DiscriminatorValue`.

Sau bài này, bạn có thể:

- Chọn chiến lược kế thừa phù hợp với mô hình dữ liệu.
- Đặt `@Inheritance` đúng tại entity root.
- Cấu hình tên, kiểu và giá trị discriminator.
- Hiểu schema được tạo ra với từng chiến lược.
- Truy vấn đa hình qua entity cha.
- Tránh các lỗi mapping, nullability, migration và tương thích provider.

Ví dụ sử dụng Java 17+, Spring Boot 3.x, Jakarta Persistence và Spring Data JPA.

## 1. Kế thừa entity trong JPA

Giả sử ứng dụng có nhiều hình thức thanh toán. Tất cả hình thức đều có mã thanh toán và số tiền, nhưng mỗi loại có thông tin riêng:

- Thanh toán bằng thẻ có bốn số cuối của thẻ.
- Chuyển khoản ngân hàng có số tài khoản nhận.

Trong Java, có thể biểu diễn bằng một class cha `Payment` và các class con `CardPayment`, `BankTransferPayment`:

```java
public abstract class Payment {
    private Long id;
    private BigDecimal amount;
}

public class CardPayment extends Payment {
    private String cardLastFour;
}

public class BankTransferPayment extends Payment {
    private String bankAccount;
}
```

Nếu các class này là entity JPA, database cần lưu dữ liệu sao cho có thể khôi phục đúng loại entity khi đọc. JPA gọi đây là entity inheritance mapping.

Điểm quan trọng: kế thừa Java tự nó không quyết định cấu trúc bảng. Chiến lược `@Inheritance` mới quy định cách provider ánh xạ hierarchy xuống schema quan hệ.

## 2. @Inheritance và các chiến lược

`@Inheritance` được đặt trên entity root của hierarchy, tức entity cha cao nhất trong cây kế thừa mà JPA quản lý. Các class con được đánh dấu `@Entity` và kế thừa từ entity cha.

Nếu không khai báo `@Inheritance`, chiến lược mặc định của JPA là `SINGLE_TABLE`. Dù vậy, nên khai báo tường minh để người đọc hiểu chủ ý thiết kế.

### 2.1. SINGLE_TABLE

Tất cả entity trong hierarchy được lưu trong cùng một bảng. Một cột discriminator phân biệt loại entity của mỗi hàng.

Ví dụ schema khái niệm:

```sql
CREATE TABLE payments (
    id BIGINT PRIMARY KEY,
    amount DECIMAL(19, 2) NOT NULL,
    payment_type VARCHAR(24) NOT NULL,
    card_last_four VARCHAR(4),
    bank_account VARCHAR(40)
);
```

Dữ liệu:

| id | amount | payment_type | card_last_four | bank_account |
|---:|---:|---|---|---|
| 1 | 120.00 | CARD | 1234 | NULL |
| 2 | 250.00 | BANK_TRANSFER | NULL | 00123456 |

Ưu điểm:

- Truy vấn toàn bộ hierarchy thường đơn giản vì chỉ cần đọc một bảng.
- Không cần JOIN giữa bảng cha và bảng con khi đọc entity.
- Dễ thực hiện truy vấn đa hình.
- Phù hợp khi số lượng subclass vừa phải và các thuộc tính chung chiếm phần lớn.

Nhược điểm:

- Cột riêng của từng subclass thường phải cho phép null vì hàng của subclass khác không sử dụng cột đó.
- Bảng có thể có nhiều cột thưa khi hierarchy lớn.
- Ràng buộc bắt buộc theo từng subclass khó biểu diễn bằng một NOT NULL đơn giản.
- Thay đổi hierarchy có thể làm bảng trung tâm ngày càng rộng.

Với `SINGLE_TABLE`, discriminator là cơ chế quan trọng để provider biết mỗi hàng thuộc entity class nào.

### 2.2. JOINED

Entity cha được lưu trong một bảng; mỗi subclass có bảng riêng chứa các thuộc tính riêng. Bảng subclass dùng khóa chính đồng thời là khóa ngoại tham chiếu bảng cha.

Ví dụ schema khái niệm:

```sql
CREATE TABLE payments (
    id BIGINT PRIMARY KEY,
    amount DECIMAL(19, 2) NOT NULL,
    payment_type VARCHAR(24)
);

CREATE TABLE card_payments (
    payment_id BIGINT PRIMARY KEY REFERENCES payments(id),
    card_last_four VARCHAR(4) NOT NULL
);

CREATE TABLE bank_transfer_payments (
    payment_id BIGINT PRIMARY KEY REFERENCES payments(id),
    bank_account VARCHAR(40) NOT NULL
);
```

Một thanh toán bằng thẻ cần một hàng trong `payments` và một hàng tương ứng trong `card_payments`. Khóa `card_payments.payment_id` chính là ID của hàng cha.

Ưu điểm:

- Dữ liệu chung chỉ lưu một lần ở bảng cha.
- Các cột riêng của subclass nằm trong bảng tương ứng.
- Có thể áp dụng NOT NULL và constraint phù hợp cho các thuộc tính subclass.
- Schema được chuẩn hóa hơn so với SINGLE_TABLE.

Nhược điểm:

- Truy vấn entity subclass thường cần JOIN bảng cha với bảng subclass.
- Truy vấn đa hình có thể cần JOIN nhiều bảng.
- Lưu hoặc xóa entity có thể tác động nhiều bảng.
- Số lượng bảng tăng theo số subclass.

Trong `JOINED`, discriminator column có thể được khai báo để phân biệt loại entity. JPA cho phép `@DiscriminatorColumn` trên root của hierarchy dùng SINGLE_TABLE hoặc JOINED. Với JOINED, provider có thể xác định subtype qua cấu trúc bảng join nếu không khai báo discriminator; việc khai báo rõ discriminator hữu ích khi mapping/provider cần dùng cột này.

### 2.3. TABLE_PER_CLASS

Mỗi concrete entity class có bảng riêng. Mỗi bảng chứa cả thuộc tính kế thừa từ class cha lẫn thuộc tính riêng của class đó.

Ví dụ schema khái niệm:

```sql
CREATE TABLE card_payments (
    id BIGINT PRIMARY KEY,
    amount DECIMAL(19, 2) NOT NULL,
    card_last_four VARCHAR(4) NOT NULL
);

CREATE TABLE bank_transfer_payments (
    id BIGINT PRIMARY KEY,
    amount DECIMAL(19, 2) NOT NULL,
    bank_account VARCHAR(40) NOT NULL
);
```

Không có bảng `payments` chung trong mô hình này. Thuộc tính `amount` được lặp lại trong mỗi bảng concrete subclass.

Ưu điểm:

- Mỗi bảng concrete chứa đầy đủ dữ liệu của loại entity đó.
- Đọc một subclass cụ thể không cần JOIN với bảng cha.
- Các thuộc tính riêng có thể được đặt NOT NULL tự nhiên trong bảng tương ứng.

Nhược điểm:

- Thuộc tính kế thừa bị lặp lại trong nhiều bảng.
- Truy vấn đa hình trên class cha có thể cần UNION giữa các bảng con.
- Thay đổi thuộc tính chung phải cập nhật nhiều bảng.
- Sinh ID duy nhất cho toàn hierarchy và các thao tác polymorphic có thể phức tạp hơn; một số chiến lược ID/provider có giới hạn.

`TABLE_PER_CLASS` không dùng discriminator column theo mô hình chuẩn thông thường. Không đặt `@DiscriminatorColumn` để mong provider phân loại các hàng trong chiến lược này.

### 2.4. So sánh nhanh

| Tiêu chí | SINGLE_TABLE | JOINED | TABLE_PER_CLASS |
|---|---|---|---|
| Số bảng | Một bảng cho hierarchy | Bảng cha và bảng cho mỗi subclass | Một bảng cho mỗi concrete class |
| Cột chung | Lưu một lần | Lưu trong bảng cha | Lặp ở từng bảng con |
| Thuộc tính riêng | Các cột nullable trong bảng chung | Nằm ở bảng subclass | Nằm ở bảng concrete |
| Đọc subclass | Thường không cần JOIN | Thường cần JOIN | Không cần JOIN bảng cha |
| Truy vấn đa hình | Đơn giản | Có thể cần nhiều JOIN | Có thể cần UNION |
| Discriminator | Cần để phân biệt loại hàng | Có thể khai báo; không bắt buộc trong mọi mapping | Không dùng theo mô hình chuẩn |
| Phù hợp | Hierarchy đơn giản, truy vấn đa hình thường xuyên | Schema chuẩn hóa, thuộc tính subclass cần constraint | Concrete class ít cần truy vấn đa hình |

Không có chiến lược tốt nhất cho mọi ứng dụng. Hãy xem xét số subclass, số lượng dữ liệu, tần suất truy vấn đa hình, constraint và khả năng migration trước khi chọn.

## 3. @DiscriminatorColumn và @DiscriminatorValue

Discriminator là thông tin để JPA/provider xác định entity class cụ thể mà một hàng thuộc về trong hierarchy.

Với SINGLE_TABLE, cùng một bảng chứa nhiều loại entity. Một cột discriminator ghi giá trị phân biệt loại đó.

Ví dụ:

| id | amount | payment_type |
|---:|---:|---|
| 1 | 120.00 | CARD |
| 2 | 250.00 | BANK_TRANSFER |

Khi tải hàng ID 1 qua entity root `Payment`, provider đọc `payment_type = CARD` và khởi tạo `CardPayment`.

### 3.1. @DiscriminatorColumn

`@DiscriminatorColumn` được đặt trên entity root:

```java
@Entity
@Table(name = "payments")
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(
    name = "payment_type",
    discriminatorType = DiscriminatorType.STRING,
    length = 24
)
public abstract class Payment {
    // Thuộc tính dùng chung.
}
```

Các thuộc tính thường dùng:

| Thuộc tính | Ý nghĩa |
|---|---|
| `name` | Tên cột discriminator |
| `discriminatorType` | Kiểu dữ liệu discriminator: STRING, CHAR hoặc INTEGER |
| `columnDefinition` | Định nghĩa SQL tùy chọn cho cột |
| `length` | Độ dài cột; chủ yếu có ý nghĩa với kiểu STRING |

Nếu không khai báo `@DiscriminatorColumn`, JPA mặc định dùng tên cột `DTYPE` và kiểu discriminator STRING cho chiến lược cần discriminator. Khai báo tường minh giúp schema và code dễ hiểu hơn.

Chỉ đặt `@DiscriminatorColumn` trên root entity class của hierarchy, không lặp lại ở từng subclass. Annotation này được JPA hỗ trợ cho hierarchy dùng SINGLE_TABLE hoặc JOINED.

### 3.2. @DiscriminatorValue

`@DiscriminatorValue` xác định giá trị discriminator đại diện cho một entity class.

Ví dụ:

```java
@Entity
@DiscriminatorValue("CARD")
public class CardPayment extends Payment {
}

@Entity
@DiscriminatorValue("BANK_TRANSFER")
public class BankTransferPayment extends Payment {
}
```

Khi provider lưu một CardPayment, cột `payment_type` mang giá trị `CARD`. Khi đọc hàng có giá trị đó, provider tạo đối tượng CardPayment.

Nếu không khai báo `@DiscriminatorValue`, JPA/provider sử dụng giá trị mặc định theo entity name đối với discriminator kiểu STRING. Dùng giá trị tường minh giúp tránh phụ thuộc vào tên class/entity và giúp schema dễ đọc.

Giá trị discriminator cần duy nhất trong hierarchy và phải phù hợp kiểu/độ dài cột. Nếu dùng STRING, chọn độ dài đủ cho giá trị dài nhất.

### 3.3. Các kiểu discriminator

JPA hỗ trợ:

- `DiscriminatorType.STRING`: giá trị chuỗi, thường dễ đọc và dễ quản lý.
- `DiscriminatorType.CHAR`: một ký tự.
- `DiscriminatorType.INTEGER`: số nguyên.

Ví dụ kiểu INTEGER:

```java
@DiscriminatorColumn(
    name = "payment_kind",
    discriminatorType = DiscriminatorType.INTEGER
)
```

```java
@Entity
@DiscriminatorValue("1")
public class CardPayment extends Payment {
}
```

Với kiểu INTEGER, annotation vẫn nhận giá trị dưới dạng chuỗi; provider chuyển đổi theo kiểu discriminator đã khai báo. Chuỗi dễ đọc như `CARD` thường thân thiện hơn khi kiểm tra dữ liệu bằng SQL, nhưng quyết định cuối cùng nên thống nhất với schema và hệ thống hiện có.

## 4. Ví dụ hoàn chỉnh với SINGLE_TABLE

### 4.1. Entity root Payment

```java
package com.example.demo.payment;

import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "payments")
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(
    name = "payment_type",
    discriminatorType = DiscriminatorType.STRING,
    length = 24
)
public abstract class Payment {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal amount;

    protected Payment() {
    }

    protected Payment(BigDecimal amount) {
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

Root entity được đánh dấu `@Entity` dù là abstract class. JPA dùng nó như một phần của hierarchy và có thể truy vấn polymorphic qua kiểu Payment. Không thể tạo trực tiếp một instance abstract Payment.

### 4.2. Subclass CardPayment

```java
package com.example.demo.payment;

import jakarta.persistence.Column;
import jakarta.persistence.DiscriminatorValue;
import jakarta.persistence.Entity;

import java.math.BigDecimal;

@Entity
@DiscriminatorValue("CARD")
public class CardPayment extends Payment {

    @Column(name = "card_last_four", length = 4)
    private String cardLastFour;

    protected CardPayment() {
    }

    public CardPayment(BigDecimal amount, String cardLastFour) {
        super(amount);
        this.cardLastFour = cardLastFour;
    }

    public String getCardLastFour() {
        return cardLastFour;
    }
}
```

### 4.3. Subclass BankTransferPayment

```java
package com.example.demo.payment;

import jakarta.persistence.Column;
import jakarta.persistence.DiscriminatorValue;
import jakarta.persistence.Entity;

import java.math.BigDecimal;

@Entity
@DiscriminatorValue("BANK_TRANSFER")
public class BankTransferPayment extends Payment {

    @Column(name = "bank_account", length = 40)
    private String bankAccount;

    protected BankTransferPayment() {
    }

    public BankTransferPayment(BigDecimal amount, String bankAccount) {
        super(amount);
        this.bankAccount = bankAccount;
    }

    public String getBankAccount() {
        return bankAccount;
    }
}
```

Các class entity đều có constructor không tham số protected để JPA sử dụng. Mỗi subclass khai báo discriminator value riêng. Không đặt `@DiscriminatorColumn` ở subclass.

### 4.4. Repository và truy vấn polymorphic

```java
package com.example.demo.payment;

import org.springframework.data.jpa.repository.JpaRepository;

public interface PaymentRepository
        extends JpaRepository<Payment, Long> {
}
```

Có thể truy vấn tất cả loại payment thông qua root repository:

```java
List<Payment> payments = paymentRepository.findAll();

for (Payment payment : payments) {
    if (payment instanceof CardPayment card) {
        System.out.println(card.getCardLastFour());
    } else if (payment instanceof BankTransferPayment transfer) {
        System.out.println(transfer.getBankAccount());
    }
}
```

Với SINGLE_TABLE, provider đọc discriminator để khởi tạo đúng subclass. JPQL cũng có thể lọc theo kiểu entity:

```java
@Query("select p from Payment p where type(p) = CardPayment")
List<Payment> findCardPayments();
```

Trong JPQL, `TYPE` kiểm tra entity type. Có thể dùng `TREAT` khi cần truy cập thuộc tính subclass trong một biểu thức query phù hợp.

Không nên dựa vào chuỗi discriminator trong code nghiệp vụ. Hãy dùng kiểu entity, query theo type hoặc mô hình domain rõ ràng.

## 5. Schema và constraint với SINGLE_TABLE

Với SINGLE_TABLE, schema có một bảng chung:

```sql
CREATE TABLE payments (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    amount DECIMAL(19, 2) NOT NULL,
    payment_type VARCHAR(24) NOT NULL,
    card_last_four VARCHAR(4),
    bank_account VARCHAR(40)
);
```

Các cột riêng của subclass thường cho phép null vì một hàng thuộc loại khác không sử dụng chúng. Ví dụ hàng CARD có `bank_account = NULL`.

Điều này tạo ra một vấn đề: không thể đơn giản đặt `card_last_four NOT NULL` cho toàn bảng, vì các hàng BANK_TRANSFER cũng phải tồn tại trong cùng bảng và không có card_last_four.

Có thể bảo vệ dữ liệu bằng CHECK constraint theo discriminator, ví dụ với database hỗ trợ:

```sql
ALTER TABLE payments
ADD CONSTRAINT ck_card_payment_details
CHECK (
    payment_type <> 'CARD'
    OR card_last_four IS NOT NULL
);

ALTER TABLE payments
ADD CONSTRAINT ck_bank_transfer_details
CHECK (
    payment_type <> 'BANK_TRANSFER'
    OR bank_account IS NOT NULL
);
```

Các constraint này minh họa cách ràng buộc dữ liệu theo loại entity. Cú pháp và khả năng của CHECK constraint tùy database. Hãy quản lý schema bằng Flyway/Liquibase khi cần constraint chính xác.

Nếu hierarchy có nhiều subclass và nhiều cột riêng, SINGLE_TABLE có thể tạo bảng rất rộng. Đây là một lý do để cân nhắc JOINED.

## 6. Mapping JOINED và discriminator

Với JOINED, dữ liệu chung nằm ở bảng root và thuộc tính subclass nằm trong bảng con. Ví dụ:

```java
@Entity
@Table(name = "payments")
@Inheritance(strategy = InheritanceType.JOINED)
@DiscriminatorColumn(
    name = "payment_type",
    discriminatorType = DiscriminatorType.STRING,
    length = 24
)
public abstract class Payment {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal amount;

    protected Payment() {
    }
}
```

Subclass:

```java
@Entity
@Table(name = "card_payments")
@PrimaryKeyJoinColumn(name = "payment_id")
@DiscriminatorValue("CARD")
public class CardPayment extends Payment {
    @Column(name = "card_last_four", nullable = false, length = 4)
    private String cardLastFour;

    protected CardPayment() {
    }
}
```

Schema khái niệm:

```sql
CREATE TABLE payments (
    id BIGINT PRIMARY KEY,
    amount DECIMAL(19, 2) NOT NULL,
    payment_type VARCHAR(24)
);

CREATE TABLE card_payments (
    payment_id BIGINT PRIMARY KEY REFERENCES payments(id),
    card_last_four VARCHAR(4) NOT NULL
);
```

JPA cho phép discriminator column trên root của hierarchy dùng JOINED. Với JOINED, discriminator không bắt buộc trong mọi mapping; provider có thể xác định subtype thông qua các bảng join. Nếu khai báo discriminator, cần kiểm tra provider và schema hiện có có hỗ trợ mapping như mong đợi.

`@PrimaryKeyJoinColumn` chỉ rõ cột khóa chính ở bảng subclass đồng thời tham chiếu primary key của bảng root. Nếu không khai báo, provider áp dụng quy tắc mặc định.

## 7. TABLE_PER_CLASS và discriminator

Với `TABLE_PER_CLASS`, mỗi concrete subclass có bảng riêng chứa cả thuộc tính kế thừa. Ví dụ bảng card_payments có cả id, amount và card_last_four; bank_transfer_payments có id, amount và bank_account.

`TABLE_PER_CLASS` không dùng discriminator column theo mô hình chuẩn thông thường. Không khai báo `@DiscriminatorColumn` để mong phân loại hàng trong chiến lược này. Truy vấn polymorphic có thể yêu cầu UNION giữa các bảng concrete class.

Chiến lược này có thể phù hợp khi concrete class ít và truy vấn đa hình không thường xuyên, nhưng cần cân nhắc trùng lặp cột, sinh ID duy nhất và hiệu năng. Một số chiến lược ID có giới hạn với TABLE_PER_CLASS; hãy kiểm tra database/provider trước khi chọn.

## 8. Khi nào dùng @MappedSuperclass?

Nếu class cha chỉ nhằm chia sẻ thuộc tính như `id`, `createdAt` và `updatedAt`, nhưng không cần truy vấn polymorphic qua kiểu cha, có thể dùng `@MappedSuperclass` thay vì entity inheritance.

Ví dụ:

```java
@MappedSuperclass
public abstract class AuditableEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private Instant createdAt;
}
```

```java
@Entity
@Table(name = "customers")
public class Customer extends AuditableEntity {
    private String email;
}
```

`@MappedSuperclass` không phải entity và không có bảng riêng. Mapping thuộc tính được kế thừa vào bảng của entity con. Không thể tạo repository cho AuditableEntity như một entity root và không có polymorphic query qua class này.

Hãy chọn entity inheritance khi các subclass thực sự là những loại entity của cùng một hierarchy và cần hành vi đa hình. Chọn mapped superclass khi chỉ muốn tái sử dụng mapping thuộc tính.

## 9. Truy vấn và hiệu năng

Truy vấn qua root entity trong SINGLE_TABLE thường đọc một bảng. Với JOINED, provider có thể JOIN nhiều bảng để khôi phục đúng subclass. Với TABLE_PER_CLASS, truy vấn qua root có thể dùng UNION.

Các điểm cần xem xét:

- Tần suất truy vấn theo root hay theo subclass.
- Số lượng subclass và thuộc tính riêng.
- Kích thước bảng và độ thưa của cột.
- Chi phí JOIN/UNION.
- Constraint có thể áp dụng cho từng loại entity.
- Cách migration khi thêm hoặc đổi subclass.

Dùng index phù hợp cho các cột discriminator hoặc cột query thường xuyên nếu số liệu thực tế cho thấy cần thiết. Không thêm index chỉ vì một cột tồn tại; index làm tăng chi phí ghi và lưu trữ.

## 10. Kiểm thử inheritance mapping

Có thể dùng `@DataJpaTest` để kiểm tra lưu, đọc và truy vấn polymorphic.

Ví dụ:

```java
@DataJpaTest
class PaymentRepositoryTest {

    @Autowired
    private PaymentRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void loadsConcreteTypesThroughRootRepository() {
        CardPayment card = new CardPayment(
                new BigDecimal("120.00"),
                "1234"
        );

        BankTransferPayment transfer = new BankTransferPayment(
                new BigDecimal("250.00"),
                "00123456"
        );

        repository.save(card);
        repository.save(transfer);

        entityManager.flush();
        entityManager.clear();

        List<Payment> payments = repository.findAll();

        assertThat(payments).hasSize(2);
        assertThat(payments)
                .anyMatch(CardPayment.class::isInstance);
        assertThat(payments)
                .anyMatch(BankTransferPayment.class::isInstance);
    }
}
```

Test giả định root Payment và các subclass được cấu hình trong package được Spring Boot quét, có constructor như ví dụ và đã import JUnit 5, AssertJ, Spring Data JPA test support. `flush()` đẩy dữ liệu xuống database; `clear()` xóa persistence context để lần đọc tiếp theo phải khôi phục entity từ database.

Ngoài test trên, nên kiểm tra:

- Discriminator value được lưu đúng cho từng subclass.
- Đọc hàng bằng root repository tạo đúng concrete class.
- Query lọc theo subtype trả đúng dữ liệu.
- Thuộc tính subclass không bị mất khi update.
- Constraint và migration hoạt động trên database đích.

## 11. Lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Entity subclass không được nhận diện | Subclass thiếu @Entity hoặc không được scan | Đánh dấu entity và kiểm tra package scan |
| Discriminator value không khớp | Giá trị annotation và dữ liệu/schema không đồng bộ | Đặt giá trị tường minh, migration dữ liệu cũ |
| Hàng subclass thiếu cột bắt buộc | SINGLE_TABLE không có constraint theo loại | Dùng CHECK constraint hoặc cân nhắc JOINED |
| Truy vấn root chậm | JOIN/UNION hoặc hierarchy quá lớn | Xem SQL thực tế và chọn chiến lược phù hợp |
| Không thể tạo bảng sau đổi strategy | Schema migration chưa cập nhật | Viết migration chuyển dữ liệu và cấu trúc bảng |
| Dùng @DiscriminatorColumn với TABLE_PER_CLASS | Discriminator không thuộc mô hình chuẩn của strategy này | Bỏ discriminator và dùng mapping phù hợp |
| Query theo subtype không đúng | Sai entity name hoặc query type | Dùng TYPE/TREAT và xác nhận tên entity |
| Thêm subclass làm hỏng dữ liệu cũ | Discriminator value mới hoặc migration thiếu | Cập nhật schema, constraint và dữ liệu có kiểm soát |

## 12. Checklist thiết kế entity inheritance

- [ ] Đánh dấu root và subclass bằng `@Entity` khi chúng là entity.
- [ ] Đặt `@Inheritance` ở root entity.
- [ ] Chọn SINGLE_TABLE, JOINED hoặc TABLE_PER_CLASS dựa trên query và schema.
- [ ] Đặt `@DiscriminatorColumn` ở root khi strategy sử dụng discriminator.
- [ ] Đặt `@DiscriminatorValue` rõ ràng cho từng subclass.
- [ ] Đảm bảo discriminator value duy nhất và độ dài cột đủ.
- [ ] Kiểm tra nullability/constraint của các cột subclass.
- [ ] Quản lý thay đổi hierarchy bằng migration.
- [ ] Kiểm thử lưu và tải polymorphic qua root repository.
- [ ] Kiểm tra SQL và hiệu năng truy vấn theo hierarchy.

## Kết luận

JPA inheritance ánh xạ cây kế thừa entity xuống schema quan hệ. `@Inheritance` chọn cách lưu dữ liệu; `@DiscriminatorColumn` khai báo cột phân biệt loại entity và `@DiscriminatorValue` gán giá trị cho từng loại.

SINGLE_TABLE đơn giản cho truy vấn đa hình nhưng tạo cột nullable; JOINED chuẩn hóa dữ liệu nhưng cần JOIN; TABLE_PER_CLASS lưu từng concrete class riêng và có thể cần UNION. Chọn chiến lược theo cấu trúc dữ liệu, query, constraint và cách vận hành. Khai báo discriminator rõ ràng, quản lý migration và kiểm thử polymorphic behavior giúp hierarchy ổn định khi ứng dụng mở rộng.
