# Đánh đổi giữa toàn vẹn dữ liệu, khả năng mở rộng và hiệu năng

## Mục tiêu

Sau bài này, bạn có thể đánh giá cách ánh xạ kế thừa entity trong JPA theo ba tiêu chí: toàn vẹn dữ liệu, khả năng phát triển mô hình và hiệu năng đọc/ghi. Bạn sẽ phân biệt `SINGLE_TABLE`, `JOINED`, `TABLE_PER_CLASS` và `@MappedSuperclass`; hiểu tác động của từng lựa chọn lên schema, khóa ngoại, constraint, truy vấn đa hình và migration; từ đó chọn chiến lược phù hợp với vòng đời dữ liệu và tải thực tế của ứng dụng.

## 1. Bài toán kế thừa trong JPA

Trong Java, kế thừa cho phép một lớp con dùng lại thuộc tính và hành vi của lớp cha. Ví dụ, `CardPayment` và `BankTransfer` đều là một loại `PaymentMethod`, nhưng mỗi loại có dữ liệu riêng.

```java
public abstract class PaymentMethod {
    private Long id;
    private String owner;
}

public class CardPayment extends PaymentMethod {
    private String lastFourDigits;
}

public class BankTransfer extends PaymentMethod {
    private String bankCode;
}
```

Đoạn code trên mới mô tả quan hệ object-oriented. Để JPA lưu một entity hierarchy, cần xác định cách các thuộc tính của lớp cha và lớp con được ánh xạ vào bảng. Lựa chọn đó ảnh hưởng trực tiếp đến cấu trúc database và SQL mà provider sinh ra.

JPA định nghĩa ba chiến lược kế thừa entity:

- `InheritanceType.SINGLE_TABLE`: toàn bộ hierarchy nằm trong một bảng.
- `InheritanceType.JOINED`: lớp cha và mỗi lớp con có bảng riêng, liên kết bằng khóa chính/khóa ngoại.
- `InheritanceType.TABLE_PER_CLASS`: mỗi lớp entity cụ thể có bảng riêng, bao gồm cả các thuộc tính kế thừa.

Ngoài ra, `@MappedSuperclass` cho phép chia sẻ mapping từ một lớp cha mà không tạo entity/table riêng cho lớp cha. Đây là cơ chế tái sử dụng mapping, không phải một giá trị của `InheritanceType`.

## 2. Bốn cách tổ chức mapping

### 2.1. SINGLE_TABLE: một bảng cho toàn bộ hierarchy

`SINGLE_TABLE` lưu thuộc tính chung và thuộc tính riêng của mọi lớp con trong cùng một bảng. Cột phân biệt loại entity thường được khai báo bằng `@DiscriminatorColumn`; giá trị của mỗi lớp con được khai báo bằng `@DiscriminatorValue`.

Ví dụ:

```java
package com.example.learning.payment;

import jakarta.persistence.Column;
import jakarta.persistence.DiscriminatorColumn;
import jakarta.persistence.DiscriminatorType;
import jakarta.persistence.DiscriminatorValue;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Inheritance;
import jakarta.persistence.InheritanceType;

@Entity
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(
    name = "payment_type",
    discriminatorType = DiscriminatorType.STRING
)
public abstract class PaymentMethod {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String owner;

    protected PaymentMethod() {
    }

    protected PaymentMethod(String owner) {
        this.owner = owner;
    }

    public Long getId() {
        return id;
    }

    public String getOwner() {
        return owner;
    }
}
```

Lớp con:

```java
package com.example.learning.payment;

import jakarta.persistence.Column;
import jakarta.persistence.DiscriminatorValue;
import jakarta.persistence.Entity;

@Entity
@DiscriminatorValue("CARD")
public class CardPayment extends PaymentMethod {
    @Column(name = "last_four_digits", length = 4)
    private String lastFourDigits;

    protected CardPayment() {
    }

    public CardPayment(String owner, String lastFourDigits) {
        super(owner);
        this.lastFourDigits = lastFourDigits;
    }

    public String getLastFourDigits() {
        return lastFourDigits;
    }
}
```

```java
package com.example.learning.payment;

import jakarta.persistence.Column;
import jakarta.persistence.DiscriminatorValue;
import jakarta.persistence.Entity;

@Entity
@DiscriminatorValue("BANK")
public class BankTransfer extends PaymentMethod {
    @Column(name = "bank_code", length = 20)
    private String bankCode;

    protected BankTransfer() {
    }

    public BankTransfer(String owner, String bankCode) {
        super(owner);
        this.bankCode = bankCode;
    }

    public String getBankCode() {
        return bankCode;
    }
}
```

Với chiến lược này, database có một bảng chứa các cột như `id`, `owner`, `payment_type`, `last_four_digits` và `bank_code`. Một hàng `CARD` dùng `last_four_digits`; một hàng `BANK` dùng `bank_code`. Các cột riêng của loại còn lại thường phải cho phép `NULL` vì chúng không áp dụng cho mọi hàng.

JPA mặc định dùng `SINGLE_TABLE` nếu entity hierarchy có kế thừa mà không khai báo `@Inheritance` ở root. Dù vậy, nên khai báo tường minh để người đọc hiểu rõ ý định và tránh phụ thuộc vào kiến thức mặc định.

**Ưu điểm:**

- Truy vấn đa hình trên `PaymentMethod` thường đọc từ một bảng, không cần join các bảng con.
- Đọc một entity cụ thể thường đơn giản và ít phép join.
- Thêm một lớp con thường không cần tạo bảng mới; thường chỉ cần thêm cột và discriminator value.
- Dễ phân trang danh sách toàn bộ payment method vì dữ liệu nằm trong một bảng.

**Hạn chế:**

- Bảng có thể rất rộng và nhiều cột `NULL` khi hierarchy có nhiều loại con với dữ liệu riêng.
- Constraint `NOT NULL` thông thường khó áp dụng cho cột chỉ bắt buộc với một subtype.
- Thay đổi schema cho một loại con ảnh hưởng tới bảng dùng chung của toàn hierarchy.
- Một số loại dữ liệu hoặc quy tắc uniqueness riêng cho subtype cần constraint có điều kiện, phụ thuộc khả năng của database.

Ví dụ constraint có điều kiện trên PostgreSQL:

```sql
ALTER TABLE payment_method
    ADD CONSTRAINT ck_card_requires_last_four
    CHECK (payment_type <> 'CARD' OR last_four_digits IS NOT NULL);

ALTER TABLE payment_method
    ADD CONSTRAINT ck_bank_requires_bank_code
    CHECK (payment_type <> 'BANK' OR bank_code IS NOT NULL);
```

Đây là ví dụ minh họa cách giữ toàn vẹn dữ liệu cho cột riêng của subtype. Cần điều chỉnh cú pháp, tên bảng/cột và constraint theo database thực tế. Nếu có yêu cầu mỗi loại có một unique key riêng, có thể cần unique index có điều kiện hoặc cơ chế tương đương của hệ quản trị.

### 2.2. JOINED: tách bảng cha và bảng con

`JOINED` lưu thuộc tính chung trong bảng của lớp cha, còn thuộc tính riêng của từng lớp con trong bảng tương ứng. Khóa chính của bảng con đồng thời là khóa ngoại tham chiếu khóa chính của bảng cha.

Ví dụ root entity:

```java
package com.example.learning.payment;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Inheritance;
import jakarta.persistence.InheritanceType;
import jakarta.persistence.Table;

@Entity
@Table(name = "payment_methods")
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class PaymentMethod {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String owner;

    protected PaymentMethod() {
    }

    protected PaymentMethod(String owner) {
        this.owner = owner;
    }

    public Long getId() {
        return id;
    }

    public String getOwner() {
        return owner;
    }
}
```

```java
package com.example.learning.payment;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.PrimaryKeyJoinColumn;
import jakarta.persistence.Table;

@Entity
@Table(name = "card_payments")
@PrimaryKeyJoinColumn(name = "payment_method_id")
public class CardPayment extends PaymentMethod {
    @Column(name = "last_four_digits", nullable = false, length = 4)
    private String lastFourDigits;

    protected CardPayment() {
    }

    public CardPayment(String owner, String lastFourDigits) {
        super(owner);
        this.lastFourDigits = lastFourDigits;
    }
}
```

```java
package com.example.learning.payment;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.PrimaryKeyJoinColumn;
import jakarta.persistence.Table;

@Entity
@Table(name = "bank_transfers")
@PrimaryKeyJoinColumn(name = "payment_method_id")
public class BankTransfer extends PaymentMethod {
    @Column(name = "bank_code", nullable = false, length = 20)
    private String bankCode;

    protected BankTransfer() {
    }

    public BankTransfer(String owner, String bankCode) {
        super(owner);
        this.bankCode = bankCode;
    }
}
```

Schema khái niệm:

```sql
CREATE TABLE payment_methods (
    id BIGINT PRIMARY KEY,
    owner VARCHAR(255) NOT NULL
);

CREATE TABLE card_payments (
    payment_method_id BIGINT PRIMARY KEY
        REFERENCES payment_methods(id),
    last_four_digits VARCHAR(4) NOT NULL
);

CREATE TABLE bank_transfers (
    payment_method_id BIGINT PRIMARY KEY
        REFERENCES payment_methods(id),
    bank_code VARCHAR(20) NOT NULL
);
```

DDL trên mô tả quan hệ khóa chính/khóa ngoại để giải thích mô hình. Câu lệnh tạo khóa và identity cụ thể sẽ khác nhau theo database và chiến lược sinh ID.

**Ưu điểm:**

- Mỗi bảng chỉ chứa các cột có ý nghĩa với loại dữ liệu của nó.
- Cột bắt buộc của subtype có thể khai báo `NOT NULL` ở bảng con.
- Dữ liệu chung được lưu một lần ở bảng cha, giảm lặp cột và hỗ trợ chuẩn hóa.
- Khóa ngoại từ bảng con tới bảng cha giúp database bảo đảm mỗi hàng con có một hàng cha tương ứng.
- Thêm một subtype thường là thêm bảng mới, ít làm thay đổi các bảng subtype hiện có.

**Hạn chế:**

- Đọc một subtype thường cần join bảng cha và bảng con.
- Truy vấn đa hình trên lớp cha có thể cần join nhiều bảng con để tạo đối tượng đầy đủ.
- Ghi một entity con thường gồm insert/update ở bảng cha và bảng con trong cùng transaction.
- Nhiều lớp con làm số lượng join và độ phức tạp truy vấn tăng lên.

`JOINED` thường là lựa chọn cân bằng khi các subtype có dữ liệu riêng đáng kể và cần constraint quan hệ mạnh. Tuy nhiên, hãy đo truy vấn đa hình và các đường đọc phổ biến trước khi quyết định.

### 2.3. TABLE_PER_CLASS: mỗi lớp cụ thể có bảng riêng

`TABLE_PER_CLASS` tạo một bảng cho mỗi entity class cụ thể. Các cột được kế thừa từ lớp cha được lặp lại trong bảng của từng lớp con. Một bảng chung cho root không cần thiết đối với hierarchy chỉ có lớp cha trừu tượng.

Ví dụ:

```java
package com.example.learning.payment;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Inheritance;
import jakarta.persistence.InheritanceType;

@Entity
@Inheritance(strategy = InheritanceType.TABLE_PER_CLASS)
public abstract class PaymentMethod {
    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @Column(nullable = false)
    private String owner;

    protected PaymentMethod() {
    }

    protected PaymentMethod(String owner) {
        this.owner = owner;
    }
}
```

```java
package com.example.learning.payment;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

@Entity
@Table(name = "card_payments")
public class CardPayment extends PaymentMethod {
    @Column(name = "last_four_digits", nullable = false, length = 4)
    private String lastFourDigits;

    protected CardPayment() {
    }

    public CardPayment(String owner, String lastFourDigits) {
        super(owner);
        this.lastFourDigits = lastFourDigits;
    }
}
```

```java
package com.example.learning.payment;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

@Entity
@Table(name = "bank_transfers")
public class BankTransfer extends PaymentMethod {
    @Column(name = "bank_code", nullable = false, length = 20)
    private String bankCode;

    protected BankTransfer() {
    }

    public BankTransfer(String owner, String bankCode) {
        super(owner);
        this.bankCode = bankCode;
    }
}
```

Trong mô hình này, `card_payments` có cả `id`, `owner`, `last_four_digits`; `bank_transfers` có `id`, `owner`, `bank_code`. Các cột chung như `owner` bị lặp lại ở nhiều bảng.

**Ưu điểm:**

- Mỗi bảng chứa một loại entity cụ thể, không cần discriminator hoặc cột subtype không dùng.
- Truy vấn một subtype có thể đọc từ một bảng mà không join bảng cha.
- Có thể thêm subtype mới bằng bảng riêng mà ít ảnh hưởng tới bảng khác.

**Hạn chế:**

- Các cột chung bị lặp lại, nên thay đổi kiểu hoặc quy tắc của thuộc tính cha có thể cần migration trên nhiều bảng.
- Truy vấn đa hình qua `PaymentMethod` có thể cần `UNION` giữa các bảng con; chi phí và SQL phụ thuộc provider/database.
- Khó tạo một foreign key duy nhất từ bảng khác tới mọi bảng con vì database không có một bảng cha chung chứa tất cả ID.
- Bảo đảm uniqueness trên toàn hierarchy khó hơn vì unique constraint của từng bảng chỉ kiểm soát trong bảng đó.
- Việc sinh ID phải bảo đảm không trùng giữa các bảng. Hãy dùng chiến lược ID có tính duy nhất toàn hierarchy, chẳng hạn sequence chung hoặc UUID phù hợp provider; không giả định các identity counter độc lập sẽ không bao giờ trùng.

Chiến lược này phù hợp hơn khi truy vấn chủ yếu nhắm vào từng lớp cụ thể, số lượng subtype ổn định và ít cần quan hệ/constraint tham chiếu tới lớp cha. Nó kém phù hợp nếu ứng dụng thường xuyên tìm kiếm, phân trang hoặc liên kết polymorphic qua root entity.

### 2.4. @MappedSuperclass: chia sẻ mapping, không tạo entity cha

`@MappedSuperclass` dùng khi muốn tái sử dụng các thuộc tính persistence chung, chẳng hạn ID, thời gian tạo hoặc thông tin audit, nhưng không cần coi lớp cha là một entity độc lập.

```java
package com.example.learning.common;

import java.time.Instant;
import jakarta.persistence.Column;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.MappedSuperclass;

@MappedSuperclass
public abstract class AuditedEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    public Long getId() {
        return id;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
```

Entity cụ thể kế thừa mapping:

```java
package com.example.learning.catalog;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;
import com.example.learning.common.AuditedEntity;

@Entity
@Table(name = "products")
public class Product extends AuditedEntity {
    @Column(nullable = false, length = 160)
    private String name;

    protected Product() {
    }

    public Product(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}
```

Ở đây `AuditedEntity` không có bảng riêng và không được truy vấn trực tiếp bằng `EntityManager.find(AuditedEntity.class, id)`. Các cột được khai báo ở mapped superclass trở thành cột trong bảng của từng entity cụ thể. Nếu `Order` cũng kế thừa `AuditedEntity`, bảng `orders` cũng có các cột `id` và `created_at`.

**Ưu điểm:**

- Chia sẻ mapping và hành vi chung mà không cần bảng cha.
- Không phát sinh join chỉ để lấy các thuộc tính audit.
- Mỗi entity cụ thể có bảng riêng và có thể đặt constraint trực tiếp trên bảng đó.

**Hạn chế:**

- Không có entity cha để truy vấn đa hình hoặc tạo quan hệ JPA tới kiểu cha.
- Cột chung được lặp lại trong từng bảng entity.
- Thay đổi mapping chung có thể cần migration trên nhiều bảng.

Dùng `@MappedSuperclass` cho phần dùng chung mang tính kỹ thuật như ID, audit fields hoặc metadata. Nếu cần truy vấn tất cả subtype qua một kiểu cha hoặc khai báo quan hệ tới kiểu cha, hãy dùng entity inheritance thay vì mapped superclass.

## 3. So sánh theo toàn vẹn dữ liệu, mở rộng và hiệu năng

| Tiêu chí | SINGLE_TABLE | JOINED | TABLE_PER_CLASS | @MappedSuperclass |
| --- | --- | --- | --- | --- |
| Số bảng cho hierarchy | Một bảng | Bảng cha và bảng cho từng lớp con | Một bảng cho mỗi lớp cụ thể | Mỗi entity cụ thể có bảng riêng |
| Thuộc tính chung | Lưu một lần | Lưu trong bảng cha | Lặp lại trong từng bảng con | Lặp lại trong bảng entity cụ thể |
| Cột subtype | Nhiều cột có thể NULL | Nằm trong bảng subtype | Nằm trong bảng lớp cụ thể | Tùy entity con |
| Constraint subtype NOT NULL | Khó hơn; thường cần CHECK có điều kiện | Dễ đặt NOT NULL ở bảng con | Dễ đặt NOT NULL trong từng bảng | Dễ đặt trên từng bảng entity |
| Khóa ngoại subtype | Không có bảng subtype riêng | FK từ bảng con tới bảng cha | Không có bảng cha chung để tham chiếu | Không có bảng cha |
| Truy vấn một subtype | Thường đơn giản | Thường cần join bảng cha | Đọc bảng subtype | Đọc bảng entity |
| Truy vấn đa hình | Thường đơn giản | Có thể cần join | Có thể cần UNION | Không hỗ trợ truy vấn polymorphic qua mapped superclass |
| Thêm subtype | Thường thêm cột và discriminator value | Thêm bảng con | Thêm bảng mới | Thêm entity/table mới |
| Rủi ro schema | Bảng rộng, cột NULL | Nhiều bảng và join | Lặp cột, khó uniqueness toàn hierarchy | Lặp mapping/cột chung |

Không có chiến lược thắng trên mọi tiêu chí. Chọn sai thường xuất hiện ở một trong ba nơi: database không thể bảo đảm constraint như mong muốn, truy vấn phổ biến phải làm quá nhiều join/union, hoặc mỗi thay đổi domain buộc phải sửa quá nhiều bảng.

## 4. Đánh đổi về toàn vẹn dữ liệu

Toàn vẹn dữ liệu không chỉ là việc entity hợp lệ trong Java. Database cần bảo đảm dữ liệu vẫn hợp lệ khi có nhiều ứng dụng, batch job hoặc câu SQL trực tiếp cùng ghi.

### 4.1. SINGLE_TABLE

Vì mọi subtype nằm chung một bảng, khóa chính, khóa ngoại và constraint chung có thể được định nghĩa tập trung. Tuy nhiên, cột riêng của subtype thường phải nullable. Nếu `last_four_digits` bắt buộc với `CARD`, constraint `NOT NULL` đơn giản sẽ từ chối cả các hàng `BANK`.

Giải pháp là dùng `CHECK` có điều kiện theo discriminator, hoặc trigger/constraint đặc thù database nếu quy tắc phức tạp. Cần lưu ý kiểm tra `CHECK` có xử lý `NULL` theo đúng logic mong muốn hay không; viết điều kiện tường minh cho từng subtype.

Unique constraint riêng subtype cũng có thể cần partial/filtered unique index. Ví dụ, chỉ các hàng `CARD` mới cần duy nhất theo một mã thẻ. Cú pháp và khả năng hỗ trợ khác nhau giữa PostgreSQL, SQL Server, MySQL và các hệ quản trị khác.

### 4.2. JOINED

Thông tin chung ở bảng cha, thông tin bắt buộc riêng ở bảng con. Bảng con có thể dùng `NOT NULL` cho cột subtype, còn khóa ngoại từ khóa chính bảng con về bảng cha bảo đảm không có bản ghi con mồ côi.

Database vẫn cần bảo đảm một ID cha không bị xuất hiện đồng thời trong hai subtype nếu nghiệp vụ quy định mỗi payment method chỉ có một loại cụ thể. Tùy provider và schema, có thể cần discriminator hoặc constraint bổ sung để bảo vệ quy tắc loại trừ này. Không nên mặc định rằng chỉ có khóa ngoại là đủ để biểu đạt mọi invariant của hierarchy.

### 4.3. TABLE_PER_CLASS

Mỗi bảng tự bảo đảm constraint của loại dữ liệu đó. Nhưng một quy tắc áp dụng cho toàn hierarchy, chẳng hạn ID phải duy nhất hoặc một mã nghiệp vụ không được trùng giữa `CardPayment` và `BankTransfer`, khó được một unique constraint đơn giản bảo đảm vì các hàng nằm ở các bảng khác nhau.

Nếu một bảng nghiệp vụ khác cần tham chiếu tới `PaymentMethod`, database không thể tạo một foreign key thông thường trỏ tới một tập hợp nhiều bảng con. Có thể phải dùng một bảng registry chung, đổi chiến lược mapping hoặc thiết kế lại quan hệ.

### 4.4. @MappedSuperclass

Không có bảng cha để tham chiếu. Constraint của thuộc tính kế thừa nằm trong bảng của từng entity cụ thể. Nếu cần bảo đảm cùng một quy tắc trên nhiều bảng, phải áp dụng migration/constraint cho tất cả bảng đó.

## 5. Đánh đổi về khả năng mở rộng và thay đổi domain

Ở đây, khả năng mở rộng gồm cả việc thêm loại entity mới, thay đổi thuộc tính chung, mở rộng quy tắc nghiệp vụ và phát triển schema khi dữ liệu đã tồn tại.

- `SINGLE_TABLE`: thêm subtype có thể ít thao tác DDL ban đầu, nhưng bảng chung ngày càng rộng. Thay đổi thuộc tính subtype dễ tác động tới cùng một bảng lớn và các constraint theo discriminator.
- `JOINED`: thêm subtype thường là thêm bảng và mapping mới; các bảng subtype hiện tại ít bị ảnh hưởng. Tuy nhiên, hierarchy lớn làm truy vấn đa hình và mapping phức tạp hơn.
- `TABLE_PER_CLASS`: thêm subtype là thêm bảng độc lập; thuận tiện khi các loại gần như độc lập. Đổi thuộc tính chung cần đồng bộ schema ở nhiều bảng và kiểm tra mọi truy vấn polymorphic.
- `@MappedSuperclass`: rất tiện cho thuộc tính kỹ thuật dùng chung. Khi thay đổi field chung, phải migration từng bảng entity đang kế thừa.

Đừng chỉ đếm số class con dự kiến. Hãy xem tốc độ thay đổi của thuộc tính chung, mức độ khác biệt dữ liệu giữa các subtype và các truy vấn/quan hệ mà ứng dụng cần trong nhiều năm.

## 6. Đánh đổi về hiệu năng đọc và ghi

### Đọc một subtype cụ thể

- `SINGLE_TABLE` thường đọc từ một bảng và lọc theo discriminator.
- `JOINED` thường join bảng cha với bảng subtype để lấy đầy đủ thuộc tính.
- `TABLE_PER_CLASS` đọc từ bảng của lớp cụ thể.
- `@MappedSuperclass` đọc bảng entity cụ thể, vì không có bảng cha.

### Đọc danh sách đa hình

Ví dụ truy vấn:

```java
List<PaymentMethod> methods = entityManager
    .createQuery("select p from PaymentMethod p", PaymentMethod.class)
    .getResultList();
```

Đây là truy vấn đa hình vì kiểu truy vấn là root entity. Với `SINGLE_TABLE`, provider có thể đọc từ bảng chung. Với `JOINED`, provider phải kết hợp thông tin bảng cha và các bảng con liên quan. Với `TABLE_PER_CLASS`, provider có thể tạo một câu SQL kết hợp kết quả các bảng con bằng `UNION` hoặc cơ chế tương đương. SQL thực tế phụ thuộc provider và database.

### Ghi dữ liệu

- `SINGLE_TABLE`: insert/update thường tác động một hàng trong bảng hierarchy.
- `JOINED`: insert entity con thường cần ghi bảng cha và bảng con; update thuộc tính chung/riêng có thể tác động nhiều bảng.
- `TABLE_PER_CLASS`: ghi vào bảng cụ thể, nhưng các cột chung lặp lại ở bảng đó.
- `@MappedSuperclass`: ghi một bảng entity cụ thể, vì các thuộc tính cha đã được đưa vào bảng đó.

Không nên kết luận `SINGLE_TABLE` luôn nhanh nhất. Bảng rất rộng, nhiều index, nhiều cột NULL hoặc một truy vấn chỉ cần một subtype có thể làm lợi thế giảm đi. Tương tự, join trong `JOINED` có thể tối ưu tốt với index và số subtype vừa phải. Hãy đo các truy vấn quan trọng trên dữ liệu gần với quy mô thật.

## 7. Index và thiết kế truy vấn

Chiến lược kế thừa không thay thế thiết kế index. Cần lập danh sách truy vấn thường dùng:

- Tìm entity theo ID.
- Lấy danh sách tất cả subtype có phân trang.
- Lấy riêng một subtype theo trạng thái, thời gian hoặc chủ sở hữu.
- Join từ entity khác tới root entity.
- Báo cáo tổng hợp trên các subtype.

Với `SINGLE_TABLE`, có thể cần index kết hợp discriminator và điều kiện lọc, ví dụ `(payment_type, owner)` hoặc `(payment_type, created_at)`. Với `JOINED`, cần index trên khóa ngoại/khóa chính của bảng con và các cột lọc. Với `TABLE_PER_CLASS`, cần index riêng cho từng bảng và đánh giá chi phí `UNION`.

Ví dụ index minh họa cho bảng single table:

```sql
CREATE INDEX idx_payment_type_owner
    ON payment_method (payment_type, owner);
```

Index phù hợp phụ thuộc thứ tự lọc, độ chọn lọc và kế hoạch truy vấn của database. Không tạo index chỉ vì một cột tồn tại; index làm tăng chi phí ghi và dung lượng lưu trữ.

## 8. Migration và thay đổi schema

JPA mapping là mô tả object-relational; nó không tự giải quyết mọi bước migration an toàn cho dữ liệu hiện có. Khi thay đổi inheritance strategy hoặc thêm subtype, cần lập kế hoạch migration riêng.

Ví dụ thêm một subtype mới:

1. Xác định dữ liệu subtype cần lưu và các invariant bắt buộc.
2. Chọn nơi lưu thuộc tính chung và riêng theo strategy hiện tại.
3. Tạo migration thêm cột, bảng, khóa ngoại, discriminator value hoặc index cần thiết.
4. Triển khai code đọc/ghi tương thích với schema trong giai đoạn chuyển đổi.
5. Backfill dữ liệu nếu cần; kiểm tra số lượng bản ghi, giá trị NULL, orphan và duplicate.
6. Chuyển ứng dụng sang mapping mới sau khi schema đã sẵn sàng.
7. Xóa cấu trúc cũ chỉ sau khi không còn phiên bản ứng dụng nào sử dụng.

Đổi từ `SINGLE_TABLE` sang `JOINED` hoặc `TABLE_PER_CLASS` không chỉ là đổi annotation. Dữ liệu phải được tách/nhân bản sang các bảng mới, khóa và constraint phải được tạo, truy vấn cũ phải được kiểm tra. Hãy dùng Flyway/Liquibase hoặc công cụ migration có version thay vì dựa vào `ddl-auto=update` để thực hiện một thay đổi lớn.

## 9. Cách chọn chiến lược theo tình huống

| Tình huống | Lựa chọn nên cân nhắc | Lý do |
| --- | --- | --- |
| Ít subtype, khác biệt thuộc tính nhỏ, truy vấn đa hình nhiều | `SINGLE_TABLE` | Đọc đơn giản, ít join, dễ phân trang root |
| Subtype có nhiều thuộc tính riêng và cần constraint NOT NULL rõ | `JOINED` | Cột riêng nằm ở bảng riêng; khóa ngoại bảo vệ quan hệ |
| Mỗi subtype gần như độc lập, chủ yếu truy vấn riêng từng loại | `TABLE_PER_CLASS` | Mỗi loại có bảng riêng, không join bảng cha khi đọc subtype |
| Chỉ muốn dùng chung ID/audit fields, không cần truy vấn qua lớp cha | `@MappedSuperclass` | Chia sẻ mapping mà không tạo entity cha |
| Cần quan hệ tới kiểu cha và truy vấn polymorphic | `SINGLE_TABLE` hoặc `JOINED` | Root là entity thật trong hierarchy |
| Cần uniqueness/FK toàn hierarchy do database bảo đảm | Thường ưu tiên `SINGLE_TABLE` hoặc `JOINED` | Có cấu trúc chung để đặt constraint/quan hệ; vẫn cần thiết kế invariant cụ thể |

Đây là hướng lựa chọn ban đầu, không thay thế việc đo tải và kiểm tra constraint thật. Cùng một mô hình có thể phù hợp với nhiều strategy nếu yêu cầu truy vấn và toàn vẹn dữ liệu khác nhau.

## 10. Ví dụ đánh giá một mô hình nghiệp vụ

Giả sử hệ thống có `PaymentMethod`, `CardPayment` và `BankTransfer`. Yêu cầu:

- Người dùng xem tất cả phương thức thanh toán theo chủ sở hữu.
- Mỗi loại có dữ liệu riêng bắt buộc.
- Hệ thống cần lưu lịch sử và có thể bổ sung phương thức mới.
- Có nhiều truy vấn lấy một subtype cụ thể, nhưng màn hình quản trị cũng cần danh sách đa hình.

Phân tích:

1. `SINGLE_TABLE` làm danh sách đa hình đơn giản và phù hợp nếu số subtype ít, cột riêng không quá nhiều. Cần CHECK constraint theo discriminator để bảo vệ các field bắt buộc.
2. `JOINED` phù hợp nếu dữ liệu riêng của từng phương thức lớn, constraint subtype quan trọng và cần FK rõ ràng. Cần benchmark màn hình đa hình vì có thể join nhiều bảng.
3. `TABLE_PER_CLASS` có thể làm truy vấn subtype riêng đơn giản, nhưng truy vấn toàn bộ phương thức và quan hệ tới root phức tạp hơn; uniqueness toàn hierarchy cũng khó bảo đảm.
4. `@MappedSuperclass` chỉ phù hợp nếu `PaymentMethod` không cần là entity có thể truy vấn hoặc tham chiếu. Yêu cầu danh sách đa hình khiến lựa chọn này không phù hợp.

Trong trường hợp này, thường nên so sánh `SINGLE_TABLE` và `JOINED` bằng dữ liệu thực tế. Nếu số subtype ít và truy vấn đa hình chiếm ưu thế, `SINGLE_TABLE` có thể là điểm bắt đầu. Nếu dữ liệu subtype khác biệt nhiều và constraint là ưu tiên hàng đầu, `JOINED` đáng cân nhắc.

## 11. Kiểm thử và đo lường

Không chỉ kiểm thử rằng entity persist thành công. Cần xác nhận database thực sự bảo vệ các invariant:

- Tạo một entity cho mỗi subtype và đọc lại qua root type.
- Kiểm tra discriminator ánh xạ đúng lớp con nếu dùng `SINGLE_TABLE`.
- Kiểm tra FK và NOT NULL ở các bảng con nếu dùng `JOINED`.
- Kiểm tra ID không trùng giữa các bảng nếu dùng `TABLE_PER_CLASS`.
- Thử ghi dữ liệu không hợp lệ bằng SQL trực tiếp để xác nhận constraint database có chặn hay không.
- Chạy truy vấn đa hình với phân trang và sort trên tập dữ liệu đại diện.
- Bật SQL logging trong môi trường test để xem số join/union và số câu lệnh ghi.
- Dùng execution plan của database để đánh giá index và chi phí sort/join.

Ví dụ kiểm tra đa hình trong một test có `EntityManager` được Spring cấu hình:

```java
entityManager.persist(new CardPayment("An", "1234"));
entityManager.persist(new BankTransfer("Bình", "VCB"));
entityManager.flush();
entityManager.clear();

List<PaymentMethod> methods = entityManager.createQuery(
    "select p from PaymentMethod p",
    PaymentMethod.class
).getResultList();

assertThat(methods).hasSize(2);
assertThat(methods).anyMatch(CardPayment.class::isInstance);
assertThat(methods).anyMatch(BankTransfer.class::isInstance);
```

Đây là phần thân test minh họa; nó cần đặt trong test class có inject `EntityManager` và assertion library. Test phải chạy với schema/mapping tương ứng với strategy đang đánh giá.

## 12. Những lỗi thiết kế thường gặp

- **Chọn `SINGLE_TABLE` chỉ vì ít join.** Khi subtype tăng lên, bảng có thể rất rộng và nhiều cột nullable; constraint theo loại cần được thiết kế riêng.
- **Chọn `JOINED` mà không đo truy vấn đa hình.** Nhiều subtype có thể khiến query cần nhiều join và khó phân trang hiệu quả.
- **Chọn `TABLE_PER_CLASS` rồi tạo FK tới root entity.** Không có bảng cha chung để database tham chiếu bằng một FK thông thường.
- **Dùng `@MappedSuperclass` nhưng mong đợi query qua kiểu cha.** Mapped superclass không phải entity và không có bảng riêng.
- **Giả định Java inheritance tự động quyết định schema.** Phải khai báo strategy và mapping rõ ràng.
- **Dựa vào unique constraint ở từng bảng để bảo đảm uniqueness toàn hierarchy.** Constraint đó không kiểm tra các bảng khác.
- **Dùng IDENTITY riêng trên nhiều bảng TABLE_PER_CLASS rồi giả định ID toàn cục không trùng.** Chọn chiến lược sinh ID bảo đảm uniqueness toàn hierarchy.
- **Đổi strategy chỉ bằng cách sửa annotation.** Dữ liệu và schema hiện hữu cần migration có kiểm soát.
- **Chỉ benchmark một câu query đơn giản.** Cần đo cả đọc subtype, đọc đa hình, phân trang, ghi, update và migration.

## 13. Checklist trước khi chốt inheritance strategy

- [ ] Root có cần là entity để truy vấn đa hình hoặc làm đích của quan hệ không?
- [ ] Có bao nhiêu subtype hiện tại và dự kiến trong tương lai?
- [ ] Thuộc tính riêng của subtype chiếm bao nhiêu phần trong schema?
- [ ] Những cột nào phải NOT NULL và database có thể bảo vệ trực tiếp không?
- [ ] Có uniqueness hoặc foreign key cần áp dụng xuyên suốt hierarchy không?
- [ ] Truy vấn phổ biến là theo subtype hay qua root?
- [ ] Tần suất đọc/ghi và chi phí join/union đã được đo trên dữ liệu đại diện chưa?
- [ ] Thay đổi schema có thể triển khai an toàn qua migration không?
- [ ] ID strategy có bảo đảm uniqueness theo phạm vi cần thiết không?
- [ ] Integration test đã kiểm tra constraint, truy vấn đa hình và các subtype chưa?

## Kết luận

`SINGLE_TABLE` ưu tiên truy vấn đơn giản và ít join; `JOINED` ưu tiên cấu trúc chuẩn hóa và constraint rõ ở bảng subtype; `TABLE_PER_CLASS` tách bảng theo lớp cụ thể nhưng làm truy vấn đa hình, quan hệ và uniqueness toàn hierarchy phức tạp hơn; `@MappedSuperclass` chỉ chia sẻ mapping khi không cần entity cha. Hãy bắt đầu từ invariant dữ liệu và các truy vấn thực tế, sau đó đánh giá chi phí schema, migration, đọc và ghi. Một chiến lược tốt là chiến lược mà database có thể bảo vệ quy tắc nghiệp vụ và ứng dụng vẫn đáp ứng được tải dự kiến.