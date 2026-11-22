# Kế thừa thực thể với SINGLE_TABLE

Trong lập trình hướng đối tượng, nhiều lớp có thể cùng chia sẻ thuộc tính và hành vi qua **kế thừa**. Với Hibernate/JPA, khi các lớp đó là entity, ta còn phải quyết định cách lưu toàn bộ hệ phân cấp xuống cơ sở dữ liệu quan hệ. Chiến lược `SINGLE_TABLE` ánh xạ **một hệ phân cấp entity vào một bảng duy nhất**, phân biệt kiểu đối tượng bằng một cột discriminator.

Ví dụ, hệ thống thanh toán có ba loại giao dịch: thanh toán thẻ (`CardPayment`), chuyển khoản (`BankTransferPayment`) và tiền mặt (`CashPayment`). Cả ba đều có ID, số tiền, trạng thái và thời gian tạo; riêng mỗi loại có thông tin bổ sung. Với `SINGLE_TABLE`, tất cả được lưu trong bảng `payments`.

Bài học giải thích cách khai báo `@Inheritance(strategy = InheritanceType.SINGLE_TABLE)`, vai trò của `@DiscriminatorColumn` và `@DiscriminatorValue`, cách Hibernate persist/load/query entity đa hình, đặc điểm schema và constraint, các đánh đổi hiệu năng, cũng như khi nào nên chọn chiến lược khác.

## 1. Bài toán: kế thừa Java gặp bảng quan hệ

Trong Java, hệ phân cấp có thể được mô tả:

~~~text
                     Payment
                   /    |     \
                  /     |      \
       CardPayment  BankTransferPayment  CashPayment
~~~

`Payment` giữ thuộc tính chung:

- `id`: định danh giao dịch.
- `amount`: số tiền.
- `status`: trạng thái xử lý.
- `createdAt`: thời gian tạo.

`CardPayment` thêm mã tham chiếu từ đơn vị xử lý và nhãn loại thẻ. `BankTransferPayment` thêm mã ngân hàng, tham chiếu chuyển khoản. `CashPayment` không nhất thiết có thuộc tính riêng.

Trong Java, một biến kiểu `Payment` có thể tham chiếu tới đối tượng của bất cứ lớp con nào:

~~~java
Payment payment = new CardPayment(...);
~~~

Cơ sở dữ liệu quan hệ lại lưu **hàng và cột**, không lưu trực tiếp một cây lớp Java. Hibernate cần một chiến lược ánh xạ để biết:

1. Thuộc tính chung và riêng nằm ở cột nào?
2. Hàng nào đại diện cho lớp con nào?
3. Khi đọc một hàng, phải tạo `CardPayment` hay `BankTransferPayment`?
4. Khi truy vấn `Payment`, làm sao lấy được tất cả subtype?
5. Khi cập nhật/xóa một entity, cần thao tác trên những bảng nào?

`SINGLE_TABLE` trả lời bằng cách đặt mọi cột vào một bảng chung và dùng discriminator để nhận diện subtype.

## 2. SINGLE_TABLE hoạt động như thế nào?

Giả sử bảng `payments` có dữ liệu:

| id | payment_type | amount | status | processor_token | card_brand | bank_code | transfer_reference |
| ---: | --- | ---: | --- | --- | --- | --- | --- |
| 101 | CARD | 250000.00 | COMPLETED | tok_101 | VISA | NULL | NULL |
| 102 | BANK | 500000.00 | PENDING | NULL | NULL | VCB | trf_102 |
| 103 | CASH | 80000.00 | COMPLETED | NULL | NULL | NULL | NULL |

Ở đây:

- **Mỗi hàng là một entity** thuộc một subtype cụ thể.
- `id` là khóa chính chung trên toàn bảng; không có bảng `card_payments` hoặc `bank_transfer_payments` riêng.
- `payment_type` là **discriminator** giúp Hibernate xác định class Java tương ứng.
- Các cột riêng cho subtype khác thường nhận SQL `NULL`.
- Các cột chung như `amount` và `status` tồn tại cho mọi loại thanh toán.

~~~mermaid
flowchart TD
    A["Payment @Entity<br/>@Inheritance(SINGLE_TABLE)"] --> B["CardPayment<br/>@DiscriminatorValue('CARD')"]
    A --> C["BankTransferPayment<br/>@DiscriminatorValue('BANK')"]
    A --> D["CashPayment<br/>@DiscriminatorValue('CASH')"]
    B --> T[("payments: một bảng<br/>id + payment_type + cột chung + cột riêng")]
    C --> T
    D --> T
~~~

**SINGLE_TABLE là một mapping strategy ở cấp hệ phân cấp entity**, không phải lời yêu cầu mọi entity trong ứng dụng phải nằm chung một bảng. Mỗi cây kế thừa có root riêng có thể có bảng riêng.

### 2.1. Vì sao phải có discriminator?

Khi Hibernate đọc hàng có `payment_type = 'CARD'`, nó cần tạo `CardPayment`, khôi phục những thuộc tính chung từ `Payment` và các thuộc tính riêng của `CardPayment`. Nếu `payment_type = 'BANK'`, nó tạo `BankTransferPayment`.

Discriminator thường là một cột đặc biệt trong bảng. Giá trị của nó là **metadata về subtype**, khác với một enum nghiệp vụ như `status = PENDING`. Một giao dịch có thể đổi trạng thái PENDING → COMPLETED mà không đổi subtype CARD → BANK.

Thông thường, một hàng đã thuộc subtype nào thì thuộc subtype đó trong vòng đời entity. Thay discriminator bằng SQL thủ công có thể làm dữ liệu không còn tương thích với các cột và quy tắc của subtype.

## 3. Annotation chính và vị trí khai báo

Ba annotation cốt lõi:

~~~java
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(name = "payment_type")
@DiscriminatorValue("CARD")
~~~

| Annotation | Đặt ở đâu? | Tác dụng |
| --- | --- | --- |
| `@Inheritance(strategy = InheritanceType.SINGLE_TABLE)` | Root entity của cây kế thừa | Chọn lưu mọi lớp con vào một bảng |
| `@DiscriminatorColumn` | Root entity | Xác định cột nhận diện subtype và loại discriminator |
| `@DiscriminatorValue` | Một entity trong cây, thường mỗi lớp con | Xác định giá trị discriminator của lớp đó |
| `@Table` | Root entity | Chỉ định tên bảng chung cho toàn hệ phân cấp |
| `@Entity` | Root và các lớp con là entity | Đăng ký từng lớp trong mô hình JPA |

JPA mặc định dùng chiến lược `SINGLE_TABLE` cho entity inheritance nếu không chỉ rõ chiến lược, nhưng **nên khai báo tường minh** để người đọc biết chủ đích và tránh hiểu nhầm với `JOINED` hoặc `TABLE_PER_CLASS`.

Nếu không khai báo `@DiscriminatorColumn`, JPA thường dùng discriminator mặc định kiểu STRING với tên `DTYPE`. Khi không khai báo `@DiscriminatorValue` cho một entity, provider sẽ dùng quy tắc mặc định theo entity name đối với discriminator chuỗi. Đối với schema thật hoặc dữ liệu tồn tại, nên chỉ rõ tên và giá trị để ổn định qua các lần đổi tên lớp.

### 3.1. @DiscriminatorColumn định nghĩa những gì?

Ví dụ:

~~~java
@DiscriminatorColumn(
    name = "payment_type",
    discriminatorType = DiscriminatorType.STRING,
    length = 16
)
~~~

- `name`: tên cột trong bảng chung.
- `discriminatorType`: loại discriminator JPA; thường `STRING`, cũng có `CHAR` hoặc `INTEGER`.
- `length`: độ dài cột cho discriminator chuỗi khi sinh DDL, không phải số lượng subtype tối đa.

Khai báo `STRING` với các mã ổn định như `CARD`, `BANK`, `CASH` thường dễ đọc, hỗ trợ điều tra dữ liệu trực tiếp và tránh gắn ý nghĩa business với số nguyên khó nhận diện.

## 4. Ví dụ hoàn chỉnh: Payment và ba subtype

Ví dụ sử dụng Jakarta Persistence (`jakarta.persistence.*`), phù hợp với ứng dụng Hibernate/JPA dùng namespace Jakarta. Nếu dự án thuộc thế hệ JPA cũ, import sẽ dùng `javax.persistence.*` tương ứng.

### 4.1. Root entity Payment

~~~java
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;

@Entity
@Table(name = "payments")
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(
    name = "payment_type",
    discriminatorType = DiscriminatorType.STRING,
    length = 16
)
public abstract class Payment {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal amount;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private PaymentStatus status = PaymentStatus.PENDING;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Version
    private long version;

    protected Payment() {
        // JPA cần constructor không tham số.
    }

    protected Payment(BigDecimal amount) {
        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException(
                "Số tiền phải lớn hơn 0");
        }
        this.amount = amount;
        this.createdAt = Instant.now();
    }

    public Long getId() {
        return id;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public PaymentStatus getStatus() {
        return status;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public void markCompleted() {
        if (status != PaymentStatus.PENDING) {
            throw new IllegalStateException(
                "Chỉ hoàn tất giao dịch đang chờ");
        }
        status = PaymentStatus.COMPLETED;
    }
}
~~~

Enum:

~~~java
public enum PaymentStatus {
    PENDING,
    COMPLETED,
    FAILED
}
~~~

Một số ý nghĩa quan trọng:

- `Payment` là **abstract entity**: có thể dùng để truy vấn đa hình nhưng không khởi tạo trực tiếp.
- `@Entity` được gắn trên root dù root abstract, vì Hibernate cần metadata entity của lớp cha.
- `@Table(name = "payments")` được đặt ở root, xác định **bảng duy nhất**.
- `@Id` và `@GeneratedValue` định nghĩa ID cho toàn hệ phân cấp; lớp con không khai báo `@Id` mới.
- `@Version` là thuộc tính chung để hỗ trợ optimistic locking.
- `@Inheritance` đặt ở root, không lặp lại ở từng subclass.
- `@DiscriminatorColumn` khai báo cột phân biệt loại, không phải cột trạng thái nghiệp vụ.

Các import/cấu hình của dự án và migration thực tế phải tương thích phiên bản Hibernate và dialect đang dùng. Constructor, validation và trạng thái nghiệp vụ ở đây được đơn giản hóa nhằm làm rõ mapping.

### 4.2. CardPayment

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.DiscriminatorValue;
import jakarta.persistence.Entity;
import java.math.BigDecimal;

@Entity
@DiscriminatorValue("CARD")
public class CardPayment extends Payment {

    @Column(name = "processor_token", length = 120)
    private String processorToken;

    @Column(name = "card_brand", length = 30)
    private String cardBrand;

    protected CardPayment() {}

    public CardPayment(BigDecimal amount,
                       String processorToken,
                       String cardBrand) {
        super(amount);

        if (processorToken == null || processorToken.isBlank()) {
            throw new IllegalArgumentException(
                "Thiếu mã tham chiếu xử lý thẻ");
        }
        if (cardBrand == null || cardBrand.isBlank()) {
            throw new IllegalArgumentException(
                "Thiếu loại thẻ");
        }
        this.processorToken = processorToken;
        this.cardBrand = cardBrand;
    }

    public String getProcessorToken() {
        return processorToken;
    }

    public String getCardBrand() {
        return cardBrand;
    }
}
~~~

`CardPayment` được ánh xạ vào **cùng bảng `payments`**. Hai field của nó trở thành hai cột `processor_token` và `card_brand` trong bảng chung. Chúng chỉ có ý nghĩa đối với các hàng CARD.

Ví dụ chỉ lưu một mã token do bộ xử lý thanh toán cấp, không lưu số thẻ thật hoặc thông tin thẻ nhạy cảm trong mô hình minh họa.

### 4.3. BankTransferPayment

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.DiscriminatorValue;
import jakarta.persistence.Entity;
import java.math.BigDecimal;

@Entity
@DiscriminatorValue("BANK")
public class BankTransferPayment extends Payment {

    @Column(name = "bank_code", length = 20)
    private String bankCode;

    @Column(name = "transfer_reference", length = 100)
    private String transferReference;

    protected BankTransferPayment() {}

    public BankTransferPayment(BigDecimal amount,
                               String bankCode,
                               String transferReference) {
        super(amount);

        if (bankCode == null || bankCode.isBlank()) {
            throw new IllegalArgumentException("Thiếu mã ngân hàng");
        }
        if (transferReference == null ||
                transferReference.isBlank()) {
            throw new IllegalArgumentException(
                "Thiếu tham chiếu chuyển khoản");
        }
        this.bankCode = bankCode;
        this.transferReference = transferReference;
    }

    public String getBankCode() {
        return bankCode;
    }

    public String getTransferReference() {
        return transferReference;
    }
}
~~~

### 4.4. CashPayment

~~~java
import jakarta.persistence.DiscriminatorValue;
import jakarta.persistence.Entity;
import java.math.BigDecimal;

@Entity
@DiscriminatorValue("CASH")
public class CashPayment extends Payment {

    protected CashPayment() {}

    public CashPayment(BigDecimal amount) {
        super(amount);
    }
}
~~~

`CashPayment` không có field riêng nhưng vẫn là một subtype hợp lệ. Hibernate phân biệt nó nhờ discriminator `CASH` và cho phép xử lý nghiệp vụ theo đúng kiểu Java.

### 4.5. Những điều không cần làm trong subclass

Không phải viết:

~~~java
@Entity
@Table(name = "card_payments")
public class CardPayment extends Payment { ... }
~~~

vì chiến lược SINGLE_TABLE **không có bảng riêng cho CardPayment**. Đặt `@Table` riêng ở subclass có thể gây lỗi hoặc bị provider bỏ qua tùy tình huống; không dựa vào cách này để tạo bảng con.

Cũng không cần khai báo `@Id` ở mỗi subclass. ID đã thuộc root `Payment`, và mọi hàng trong bảng chung dùng cùng một không gian khóa chính.

## 5. Schema SQL của SINGLE_TABLE

Với PostgreSQL, một schema minh họa có thể là:

~~~sql
CREATE TABLE payments (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    payment_type VARCHAR(16) NOT NULL,
    amount NUMERIC(19, 2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    version BIGINT NOT NULL,

    processor_token VARCHAR(120),
    card_brand VARCHAR(30),
    bank_code VARCHAR(20),
    transfer_reference VARCHAR(100)
);
~~~

Tên và kiểu SQL cụ thể phụ thuộc dialect và quyết định migration. Ví dụ dùng PostgreSQL để diễn giải cấu trúc; không phải câu DDL bảo đảm khớp mọi cơ sở dữ liệu.

Điểm quan trọng là **một bảng duy nhất** chứa cả các cột chung lẫn các cột riêng của mọi subtype.

### 5.1. Tại sao cột riêng thường phải nullable?

Hàng `BANK` không có token thẻ hoặc card brand, trong khi hàng `CARD` không có bank code. Vì thế:

~~~sql
processor_token VARCHAR(120) NULL,
card_brand VARCHAR(30) NULL,
bank_code VARCHAR(20) NULL,
transfer_reference VARCHAR(100) NULL
~~~

là lựa chọn tự nhiên ở cấp bảng chung.

Nếu đặt:

~~~sql
card_brand VARCHAR(30) NOT NULL
~~~

thì hàng `BANK` và `CASH` sẽ gặp ràng buộc không hợp lệ, vì chúng không có `card_brand`.

Tương tự, gắn `@Column(nullable = false)` trên field chỉ có ở subclass có thể dẫn đến yêu cầu DDL không phù hợp với bảng dùng chung. JPA/Hibernate có thể xử lý hoặc giới hạn một số metadata tùy phiên bản, nhưng **không nên dựa vào NOT NULL toàn cột** cho thuộc tính chỉ áp dụng với một subtype.

### 5.2. Bảo đảm điều kiện riêng bằng CHECK constraint

Các field của `CardPayment` vẫn có thể là **bắt buộc về nghiệp vụ** dù ở database chúng phải nullable đối với các subtype khác. PostgreSQL có thể bảo vệ điều kiện theo discriminator:

~~~sql
ALTER TABLE payments
ADD CONSTRAINT ck_payment_type
CHECK (payment_type IN ('CARD', 'BANK', 'CASH'));

ALTER TABLE payments
ADD CONSTRAINT ck_card_fields
CHECK (
    payment_type <> 'CARD'
    OR (
        processor_token IS NOT NULL
        AND card_brand IS NOT NULL
    )
);

ALTER TABLE payments
ADD CONSTRAINT ck_bank_fields
CHECK (
    payment_type <> 'BANK'
    OR (
        bank_code IS NOT NULL
        AND transfer_reference IS NOT NULL
    )
);
~~~

Đây là **ràng buộc theo từng subtype**: với hàng CARD, hai trường thẻ bắt buộc có giá trị; với hàng BANK, hai trường chuyển khoản bắt buộc có giá trị. Hàng CASH không phải đáp ứng các điều kiện riêng đó.

Nếu muốn ngăn dữ liệu của một subtype xuất hiện trên subtype khác, có thể bổ sung constraint khác, ví dụ:

~~~sql
ALTER TABLE payments
ADD CONSTRAINT ck_card_columns_only_for_cards
CHECK (
    payment_type = 'CARD'
    OR (
        processor_token IS NULL
        AND card_brand IS NULL
    )
);
~~~

Câu CHECK này là lựa chọn **chặt hơn**. Có nên áp dụng hay không phụ thuộc quy tắc domain và cách migration dữ liệu. Tương tự cần thiết kế constraint cho các nhóm cột khác nếu thực sự yêu cầu.

Lưu ý: check constraint phải được hỗ trợ và thực thi trên hệ quản trị đang dùng; dialect và phiên bản database có thể khác nhau. Các ràng buộc nên được tạo/kiểm soát bằng migration.

### 5.3. Unique constraint và index

Nếu `transferReference` phải duy nhất giữa các giao dịch BANK, PostgreSQL có thể dùng partial unique index:

~~~sql
CREATE UNIQUE INDEX uk_bank_transfer_reference
ON payments (transfer_reference)
WHERE payment_type = 'BANK';
~~~

Đây là cú pháp **PostgreSQL-specific**. Database khác có thể cần unique constraint hoặc kỹ thuật tương đương khác.

Nếu ứng dụng thường tìm kiếm giao dịch theo loại và trạng thái:

~~~sql
CREATE INDEX idx_payments_type_status
ON payments (payment_type, status);
~~~

Index có ích hay không phụ thuộc phân bố dữ liệu, mức chọn lọc, workload và kế hoạch truy vấn. Không tạo index cho mọi cột chỉ vì bảng chứa nhiều subtype.

## 6. Persist entity: Hibernate làm gì?

Giả sử `EntityManager em` đang tham gia một transaction hợp lệ:

~~~java
CardPayment card = new CardPayment(
    new BigDecimal("250000.00"),
    "tok_provider_101",
    "VISA"
);

BankTransferPayment bank = new BankTransferPayment(
    new BigDecimal("500000.00"),
    "VCB",
    "trf_2026_001"
);

CashPayment cash = new CashPayment(
    new BigDecimal("80000.00")
);

em.persist(card);
em.persist(bank);
em.persist(cash);
~~~

Hibernate xác định subtype từ **class thực tế** của từng entity và dùng giá trị `@DiscriminatorValue` tương ứng khi insert.

SQL minh họa, rút gọn theo kiểu PostgreSQL:

~~~sql
INSERT INTO payments (
    payment_type, amount, status, created_at, version,
    processor_token, card_brand
)
VALUES (
    'CARD', 250000.00, 'PENDING', ?, 0,
    'tok_provider_101', 'VISA'
);

INSERT INTO payments (
    payment_type, amount, status, created_at, version,
    bank_code, transfer_reference
)
VALUES (
    'BANK', 500000.00, 'PENDING', ?, 0,
    'VCB', 'trf_2026_001'
);
~~~

SQL trên chỉ mô tả ý tưởng; danh sách cột, cách bind, tên tham số, ID generation và các cột NULL do Hibernate thực sự sinh có thể khác. **Không nên kỳ vọng Hibernate luôn phát đúng nguyên văn các câu INSERT này.**

Với `GenerationType.IDENTITY`, Hibernate thường phải thực hiện insert để lấy khóa từ database; điều này cũng có thể ảnh hưởng khả năng JDBC batching khi nhập số lượng lớn.

### 6.1. Không cần tự gán discriminator

Đối với mapping thường gặp, code nghiệp vụ không phải làm như sau:

~~~java
card.setPaymentType("CARD"); // Không cần và không nên làm.
~~~

Discriminator được Hibernate quản lý dựa vào mapping subtype. Nó không phải một thuộc tính domain cần setter.

Nếu muốn client biết loại thanh toán khi trả API, có thể dùng DTO với trường `type` riêng, hoặc API ánh xạ từ class Java sang mã ổn định. Tránh phụ thuộc trực tiếp vào tên mặc định của entity làm hợp đồng công khai.

## 7. Load entity: dữ liệu nào tạo class nào?

Ví dụ:

~~~java
Payment payment = em.find(Payment.class, 101L);
~~~

Nếu hàng có `payment_type = 'CARD'`, Hibernate tạo hoặc trả về entity có kiểu thực tế `CardPayment`. Khi dùng:

~~~java
if (payment instanceof CardPayment cardPayment) {
    System.out.println(cardPayment.getCardBrand());
}
~~~

bạn đang thực hiện hành vi đa hình trong Java dựa trên subtype.

Với `em.find(CardPayment.class, id)`, Hibernate tìm theo entity subtype; nếu ID tồn tại nhưng thuộc subtype khác, không thể hợp lệ trả một `CardPayment` với giá trị discriminator BANK. Hành vi và SQL cụ thể do provider quyết định.

### 7.1. Cần chú ý khi discriminator không hợp lệ

Nếu bảng chứa một hàng có:

~~~text
payment_type = "CRYPTO"
~~~

nhưng không có subclass entity nào được mapping với giá trị đó, Hibernate có thể không biết dựng loại entity nào, dẫn đến lỗi khi load. Dữ liệu không khớp mapping thường là **vấn đề về schema/migration/ghi dữ liệu ngoài ORM**, không phải lỗi của phương thức `find()`.

Thay đổi `@DiscriminatorValue("BANK")` thành `"TRANSFER"` mà không cập nhật dữ liệu cũ có thể khiến bản ghi cũ không được nhận diện đúng. Mã discriminator cần được quản lý như một phần của hợp đồng lưu trữ.

## 8. Truy vấn đa hình bằng JPQL

Một lợi ích lớn của SINGLE_TABLE là **truy vấn entity cha có thể trả về nhiều loại entity con**.

### 8.1. Query root lấy mọi subtype

~~~java
List<Payment> payments = em.createQuery("""
    SELECT p
    FROM Payment p
    ORDER BY p.createdAt DESC
    """, Payment.class)
    .setMaxResults(50)
    .getResultList();
~~~

Danh sách có thể chứa các object `CardPayment`, `BankTransferPayment` và `CashPayment`. Trong SQL, Hibernate chủ yếu đọc từ **một bảng `payments`** và dựa trên discriminator để tạo từng subtype.

Ví dụ loop:

~~~java
for (Payment payment : payments) {
    System.out.println(
        payment.getClass().getSimpleName()
        + ": " + payment.getAmount()
    );
}
~~~

Khi làm việc với proxy/enhancement của Hibernate, `getClass()` có thể không phải cách tốt nhất để suy luận subtype trong mọi ngữ cảnh lazy association; nếu cần API nghiệp vụ theo loại, có thể dùng polymorphic methods, `TYPE` trong JPQL, hoặc cơ chế kiểm tra kiểu tương thích với Hibernate đang dùng.

### 8.2. Query một subclass

~~~java
List<CardPayment> cards = em.createQuery("""
    SELECT c
    FROM CardPayment c
    WHERE c.cardBrand = :brand
    ORDER BY c.id DESC
    """, CardPayment.class)
    .setParameter("brand", "VISA")
    .getResultList();
~~~

Hibernate có thể thêm điều kiện discriminator tương ứng `CARD` để chỉ lấy hàng của subtype. Không cần join bảng riêng cho `CardPayment`, vì các cột subtype nằm ngay ở `payments`.

### 8.3. Lọc theo TYPE trong JPQL

JPA hỗ trợ biểu thức `TYPE` để xét kiểu entity:

~~~java
List<Payment> cardPayments = em.createQuery("""
    SELECT p
    FROM Payment p
    WHERE TYPE(p) = CardPayment
    """, Payment.class)
    .getResultList();
~~~

`CardPayment` ở đây là tên entity trong JPQL, không phải chuỗi SQL discriminator `'CARD'`. Nếu entity được khai báo `@Entity(name = "...")` với tên khác, truy vấn phải theo tên entity phù hợp.

Tùy nhu cầu, truy vấn thẳng `FROM CardPayment` thường đơn giản hơn khi chỉ cần trường riêng của subclass.

### 8.4. TREAT và truy cập thuộc tính subtype

JPA cung cấp `TREAT` để thu hẹp kiểu biểu thức entity trong các truy vấn đa hình. Khi cần truy cập field riêng của subclass qua tham chiếu root, `TREAT` có thể hữu ích, nhưng cú pháp, JOIN và khả năng tối ưu phụ thuộc JPA provider/phiên bản và cấu trúc truy vấn.

Ví dụ tìm tất cả payment có số tiền lớn, không cần `TREAT`:

~~~java
List<Payment> expensive = em.createQuery("""
    SELECT p
    FROM Payment p
    WHERE p.amount > :minAmount
    """, Payment.class)
    .setParameter("minAmount", new BigDecimal("1000000.00"))
    .getResultList();
~~~

Ví dụ chỉ cần field riêng của CardPayment thì truy vấn subclass trực tiếp sẽ dễ đọc hơn:

~~~java
List<String> brands = em.createQuery("""
    SELECT DISTINCT c.cardBrand
    FROM CardPayment c
    """, String.class)
    .getResultList();
~~~

### 8.5. Query projection cho danh sách

Nếu API chỉ cần ID, số tiền, trạng thái và thời gian tạo, có thể dùng DTO projection thay vì nạp toàn bộ entity:

~~~java
List<PaymentSummary> summaries = em.createQuery("""
    SELECT new com.example.PaymentSummary(
        p.id, p.amount, p.status
    )
    FROM Payment p
    ORDER BY p.id DESC
    """, PaymentSummary.class)
    .setMaxResults(20)
    .getResultList();
~~~

Giả định `PaymentSummary` có constructor phù hợp. Việc dùng SINGLE_TABLE không buộc mọi truy vấn phải tải tất cả cột của tất cả subtype. **Projection** phù hợp cho màn hình danh sách và báo cáo chỉ cần vài trường.

## 9. Thay đổi và xóa entity trong SINGLE_TABLE

### 9.1. UPDATE vẫn theo ID của bảng chung

Khi cập nhật trạng thái:

~~~java
Payment payment = em.find(Payment.class, paymentId);
payment.markCompleted();
~~~

Nếu entity đang managed trong transaction, Hibernate theo dõi thay đổi persistent và ghi xuống bảng `payments` lúc flush. Với `@Version`, SQL cập nhật thường tham gia kiểm tra version để phát hiện giao dịch khác đã sửa cùng hàng.

Một câu UPDATE minh họa:

~~~sql
UPDATE payments
SET status = 'COMPLETED', version = version + 1
WHERE id = 101 AND version = 0;
~~~

SQL thật có thể cập nhật thêm cột hoặc có điều kiện khác tùy mapping và cấu hình. Điểm cốt lõi là **không có UPDATE sang bảng subclass riêng**.

### 9.2. DELETE chỉ liên quan bảng chung của hệ phân cấp

Khi gọi:

~~~java
Payment payment = em.find(Payment.class, id);
em.remove(payment);
~~~

Hibernate có thể xóa hàng tương ứng trong bảng `payments`. Dù vậy, nếu entity có quan hệ tới bảng khác, foreign key, cascade và lifecycle callback có thể khiến thao tác phát sinh thêm SQL. SINGLE_TABLE chỉ loại bỏ nhu cầu join giữa các bảng subclass; nó không xóa đi mọi quan hệ khác.

### 9.3. Không đổi subtype bằng cách đổi discriminator

Giả sử một thanh toán thẻ bị hoàn tiền rồi được xử lý lại dưới kênh chuyển khoản. Không nên giải quyết bằng SQL:

~~~sql
UPDATE payments
SET payment_type = 'BANK'
WHERE id = 101;
~~~

Hàng cũ vẫn chứa các giá trị `processor_token`, `card_brand`; thiếu các cột bắt buộc của BANK. Ngoài ra, entity managed trong persistence context vẫn có class `CardPayment`.

Nếu nghiệp vụ thật sự thay đổi phương thức thanh toán, thường nên mô hình hóa đó là **giao dịch mới, yêu cầu thay đổi trạng thái, hoặc một entity khác đại diện cho lựa chọn phương thức**, thay vì ép đổi loại runtime của một entity đã persisted.

## 10. Ưu điểm của SINGLE_TABLE

### 10.1. Không cần JOIN để tái tạo hệ phân cấp

Với `JOINED`, Hibernate thường cần kết hợp bảng cha và bảng con để lấy thông tin subtype. Với SINGLE_TABLE, cột chung và cột riêng đã ở cùng một hàng. Các truy vấn đa hình trên root vì thế có thể đơn giản và nhanh hơn.

### 10.2. Một khóa chính và một bảng dùng chung

Mỗi entity có ID duy nhất trong bảng `payments`. Repository cho root có thể truy cập toàn bộ giao dịch mà không cần hợp nhất dữ liệu từ nhiều bảng.

### 10.3. Phù hợp khi có nhiều truy vấn trên thuộc tính chung

Các báo cáo như “tổng thanh toán theo trạng thái”, “giao dịch trong ngày”, “50 giao dịch gần nhất” chủ yếu đọc các cột chung. Một bảng thống nhất làm những truy vấn này dễ biểu đạt.

### 10.4. Thêm subtype Java có thể tương đối đơn giản

Khi thêm một lớp `WalletPayment`, có thể bổ sung các cột cần thiết vào bảng, khai báo `@Entity` và `@DiscriminatorValue("WALLET")`. Tuy nhiên đây **vẫn là thay đổi schema và hợp đồng dữ liệu**, không phải lúc nào cũng chỉ sửa Java.

## 11. Nhược điểm và giới hạn

### 11.1. Bảng rộng và nhiều NULL

Nếu hệ phân cấp có 20 subtype, mỗi subtype có nhiều thuộc tính riêng, bảng chung có thể chứa hàng trăm cột. Phần lớn cột sẽ là NULL đối với đa số hàng.

Tác động thực tế phụ thuộc database: storage engine có thể biểu diễn NULL khá gọn, nhưng schema rộng vẫn làm migration, index, ORM mapping và việc đọc dữ liệu trở nên phức tạp. Không nên đánh giá chi phí chỉ bằng số ô NULL; cần xem kích thước bảng, I/O và workload.

### 11.2. Ràng buộc NOT NULL riêng của subtype khó áp dụng

Một cột `bank_code` có thể bắt buộc cho BANK nhưng phải NULL ở CARD/CASH. Dùng `NOT NULL` chung không phù hợp; cần CHECK constraint có điều kiện hoặc cơ chế bảo vệ ở tầng domain/application và database phù hợp.

### 11.3. Thay đổi schema ảnh hưởng cả cây kế thừa

Thêm subtype hoặc trường riêng thường phải sửa bảng chung. Khi table rất lớn, một số thao tác migration/index có thể gây lock hoặc ảnh hưởng hiệu năng. Cần cân nhắc chiến lược migration an toàn.

### 11.4. Discriminator là hợp đồng dữ liệu

Giá trị discriminator phải nhất quán giữa Java mapping, dữ liệu cũ, import/export, migration và code chạy song song trong quá trình rollout. Một giá trị lạ có thể làm việc load entity thất bại.

### 11.5. Query quá rộng có thể đọc nhiều cột không cần thiết

Nếu truy vấn nạp toàn bộ root entity, provider có thể phải đọc nhiều cột liên quan đến các subtype để khôi phục instance. Với bảng rộng, nên xem SQL thực tế và dùng projection khi chỉ cần dữ liệu chung.

### 11.6. SINGLE_TABLE không giải quyết N+1 của quan hệ ngoài cây

Nếu `Payment` có `@ManyToOne Customer customer` hoặc mỗi subtype có các quan hệ lazy khác, việc lặp qua danh sách payment rồi gọi quan hệ có thể gây N+1 query. SINGLE_TABLE chỉ quyết định **kế thừa entity**; fetch planning của các association vẫn phải tối ưu độc lập.

## 12. Khi nào SINGLE_TABLE phù hợp?

SINGLE_TABLE đáng cân nhắc khi:

- Các subtype có **nhiều thuộc tính chung** và số thuộc tính riêng không quá lớn.
- Thường xuyên cần **truy vấn đa hình** trên root entity.
- Muốn giảm JOIN giữa các bảng subtype.
- Số subtype tương đối ổn định hoặc việc thêm subtype không làm bảng trở nên khó quản lý.
- Có thể biểu diễn ràng buộc riêng bằng validation nghiệp vụ và constraint có điều kiện.
- Mọi subtype thực sự cùng thuộc **một khái niệm domain có identity và vòng đời tương đồng**.

Ví dụ: `Notification` có `EmailNotification` và `SmsNotification` với nhiều cột chung; `Payment` với một vài phương thức thanh toán; `Document` có một số biến thể với cấu trúc tương đối gần nhau.

Không nên chọn SINGLE_TABLE chỉ vì code Java có từ khóa `extends`. Việc kế thừa trong code không bắt buộc tất cả lớp đều là entity hoặc cần một bảng chung. Trước tiên cần xác định mô hình domain và cách sử dụng dữ liệu.

## 13. So sánh SINGLE_TABLE, JOINED và TABLE_PER_CLASS

JPA có ba chiến lược kế thừa entity thường được nhắc tới:

| Tiêu chí | SINGLE_TABLE | JOINED | TABLE_PER_CLASS |
| --- | --- | --- | --- |
| Tổ chức bảng | Một bảng cho cả cây | Bảng cha + bảng con cho từng subtype | Mỗi lớp concrete có bảng riêng |
| Cột chung | Lưu một lần trong bảng chung | Lưu ở bảng cha | Thường lặp trong các bảng concrete |
| Phân biệt subtype | Thường bằng discriminator | Kết hợp cấu trúc bảng/metadata, có thể có discriminator | Theo bảng concrete |
| Query đa hình | Thường chỉ một bảng | Có thể cần nhiều JOIN | Có thể cần UNION giữa bảng concrete |
| Thuộc tính subtype | Nhiều cột nullable trong bảng chung | Đặt ở bảng con | Đặt tại bảng subtype |
| Ràng buộc NOT NULL cho field riêng | Khó áp dụng trực tiếp; có thể dùng CHECK theo discriminator | Dễ đặt tại bảng subtype | Dễ đặt tại bảng concrete |
| Phù hợp | Nhiều field chung, query polymorphic thường xuyên | Muốn schema chuẩn hóa và subtype khác biệt rõ | Subtype tương đối độc lập, ít truy vấn root |

Ví dụ `JOINED`:

~~~java
@Entity
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class Payment { ... }
~~~

Thường có bảng `payments` cho phần chung và bảng `card_payments`, `bank_transfer_payments` cho phần riêng. Query một CardPayment cần liên kết thông tin ở hai bảng.

Ví dụ `TABLE_PER_CLASS`:

~~~java
@Entity
@Inheritance(strategy = InheritanceType.TABLE_PER_CLASS)
public abstract class Payment { ... }
~~~

Mỗi subtype concrete có bảng lưu các field cần thiết; việc truy vấn `Payment` có thể cần hợp nhất kết quả từ nhiều bảng.

**Không có chiến lược tốt nhất cho mọi hệ thống.** Hãy chọn theo cấu trúc domain, workload truy vấn, yêu cầu constraint và tần suất thay đổi schema.

## 14. SINGLE_TABLE và @MappedSuperclass khác nhau thế nào?

Có thể tái sử dụng thuộc tính mà **không tạo cây kế thừa entity đa hình** bằng `@MappedSuperclass`:

~~~java
@MappedSuperclass
public abstract class AuditedEntity {

    @Column(name = "created_at")
    protected Instant createdAt;
}
~~~

Các entity con nhận mapping của `createdAt`, nhưng `AuditedEntity` không tự trở thành entity có bảng và cũng không được query trực tiếp bằng:

~~~java
SELECT a FROM AuditedEntity a
~~~

theo cách truy vấn root entity của `@Inheritance`.

Trong khi đó, với:

~~~java
@Entity
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
public abstract class Payment { ... }
~~~

`Payment` chính là **root entity** của hệ phân cấp, có thể được sử dụng trong JPQL và làm kiểu tham chiếu polymorphic của association.

Dùng `@MappedSuperclass` khi muốn chia sẻ mapping hoặc trạng thái chung giữa các entity nhưng **không cần một hierarchy entity thống nhất**. Dùng `SINGLE_TABLE` khi các subtype thực sự cùng một hệ phân cấp persistent cần phân biệt bằng discriminator và thường query qua root.

## 15. SINGLE_TABLE với association

Ví dụ một đơn hàng có nhiều payment, có thể tham chiếu tới **root entity**:

~~~java
@Entity
public class Order {

    @Id
    private Long id;

    @OneToMany(mappedBy = "order")
    private List<Payment> payments = new ArrayList<>();
}
~~~

Trong root `Payment` có thể khai báo:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "order_id")
private Order order;
~~~

Một FK `payments.order_id` có thể trỏ tới `orders.id` cho tất cả subtype. Trong code, collection `List<Payment>` có thể chứa CardPayment, BankTransferPayment và CashPayment.

SINGLE_TABLE giúp quan hệ tới root được lưu thống nhất trong một bảng. Nhưng cascade, orphan removal và quyền tạo/xóa payment phải dựa vào **vòng đời nghiệp vụ**, không tự suy ra từ chiến lược inheritance.

Nếu chỉ một subtype có association riêng, field đó có thể nằm ở subclass. FK tương ứng nằm trong bảng chung và sẽ nullable đối với subtype khác; ràng buộc có điều kiện có thể cần được bổ sung.

## 16. Thiết kế discriminator ổn định

Giá trị discriminator nên là **mã lưu trữ ổn định**, ví dụ:

~~~java
@DiscriminatorValue("CARD")
public class CardPayment extends Payment { ... }
~~~

Thay vì phụ thuộc vào tên lớp mặc định, mã tường minh giúp:

1. Đổi tên class Java mà không buộc đổi toàn bộ dữ liệu cũ.
2. Nhìn dữ liệu SQL dễ biết subtype.
3. Kiểm soát migration khi thêm hoặc loại bỏ một subtype.
4. Tránh sự khác biệt ngoài ý muốn khi code thay đổi entity name.

Dù vậy, **không tùy tiện đổi mã** trong production. Đổi từ `BANK` thành `TRANSFER` là một migration dữ liệu, cần xem xét code cũ và code mới trong thời gian rollout.

### 16.1. Có cần ánh xạ discriminator như field thường không?

Thông thường Hibernate quản lý discriminator nên không cần viết:

~~~java
private String paymentType;
~~~

như một thuộc tính persistent độc lập. Nếu khai báo thêm field cùng cột discriminator mà không điều chỉnh mapping cẩn thận, có thể dẫn đến xung đột cột hoặc kỳ vọng sai về khả năng cập nhật.

Nếu nghiệp vụ cần đọc loại payment, có thể sử dụng class/interface đa hình hoặc DTO. Hibernate cũng có cơ chế mapping discriminator nâng cao, nhưng không nên đưa vào mô hình đơn giản khi chưa có yêu cầu rõ ràng.

### 16.2. Hệ thống cũ không có discriminator

Nếu bảng hiện tại phân biệt subtype bằng một biểu thức hoặc nhóm cột khác, việc chuyển sang SINGLE_TABLE với discriminator chuẩn cần migration. Hibernate có extension như `@DiscriminatorFormula` cho tình huống đặc biệt, nhưng đó là tính năng riêng của Hibernate và phụ thuộc SQL/dialect.

Trong thiết kế mới, cột discriminator tường minh thường dễ quản trị và di chuyển dữ liệu hơn.

## 17. Migration một bảng cũ sang SINGLE_TABLE

Giả sử ứng dụng trước đây chỉ có bảng `payments` cho một loại giao dịch, nay muốn mở rộng thành nhiều subtype.

Quy trình minh họa:

1. **Xác định mô hình domain**: subtype nào cần tồn tại, mã discriminator ổn định là gì, các field chung/riêng ra sao.
2. **Bổ sung cột discriminator** vào bảng hiện có. Trước khi ràng buộc NOT NULL, xác định cách gán giá trị cho hàng cũ.
3. **Thêm các cột subtype** với khả năng NULL ở bảng chung.
4. **Backfill dữ liệu cũ** bằng quy tắc đáng tin cậy; không dựa vào suy đoán mơ hồ.
5. **Bổ sung CHECK/UNIQUE/FK** khi dữ liệu đã được làm sạch.
6. **Triển khai code Hibernate** với `@Inheritance` và các `@DiscriminatorValue` tương ứng.
7. **Kiểm tra đường đọc/ghi trong giai đoạn rollout**, nhất là khi nhiều phiên bản ứng dụng chạy song song.
8. **Đo SQL, index, lock và độ trễ** trên bảng thực tế.

Ví dụ câu lệnh ban đầu cho PostgreSQL:

~~~sql
ALTER TABLE payments
ADD COLUMN payment_type VARCHAR(16);

ALTER TABLE payments
ADD COLUMN processor_token VARCHAR(120);

ALTER TABLE payments
ADD COLUMN card_brand VARCHAR(30);

ALTER TABLE payments
ADD COLUMN bank_code VARCHAR(20);

ALTER TABLE payments
ADD COLUMN transfer_reference VARCHAR(100);
~~~

Sau đó phải gán `payment_type` cho các hàng cũ **dựa trên dữ liệu nguồn đáng tin cậy**. Nếu mọi bản ghi cũ đều là thanh toán tiền mặt, có thể:

~~~sql
UPDATE payments
SET payment_type = 'CASH'
WHERE payment_type IS NULL;
~~~

Chỉ áp dụng khi tiền đề đó là sự thật. Nếu dữ liệu cũ gồm nhiều phương thức thanh toán, phải phân loại chính xác từng hàng theo nghiệp vụ.

Khi đã backfill, có thể thêm NOT NULL và CHECK theo loại. Trong hệ thống lớn, cần cân nhắc lock, thời gian migration, tạo index đồng thời nếu database hỗ trợ và kế hoạch rollback.

### 17.1. Vì sao đổi @Inheritance không đủ?

Việc chuyển từ `JOINED` sang `SINGLE_TABLE` hoặc ngược lại thay đổi **địa điểm lưu dữ liệu**. Chỉ đổi annotation sẽ không tự di chuyển hàng từ các bảng subclass sang bảng chung. Cần migration schema, chuyển dữ liệu và kiểm soát nhất quán ID/FK.

Có thể chạy `hibernate.hbm2ddl.auto=validate` để kiểm tra một phần tương thích schema sau migration; `validate` không sửa schema hoặc bảo đảm mọi bản ghi đều có discriminator hợp lệ.

## 18. Những lưu ý hiệu năng và truy vấn thực tế

### 18.1. Query đa hình có thể nhanh, nhưng không miễn phí

Với dữ liệu `Payment` gồm nhiều subtype, truy vấn:

~~~sql
SELECT id, payment_type, amount, status
FROM payments
WHERE status = 'PENDING'
ORDER BY id DESC
LIMIT 50;
~~~

chỉ cần đọc một bảng. Tuy nhiên, khi bảng rất lớn, lựa chọn index và cách phân trang vẫn quyết định hiệu năng. Cần quan sát kế hoạch truy vấn bằng `EXPLAIN` hoặc công cụ phù hợp DB.

### 18.2. Nhiều subtype không tự làm truy vấn tối ưu

Nếu 95% hàng là CARD mà request chỉ đọc BANK, chỉ số `payment_type` có thể mang tính chọn lọc khác so với trường hợp 50–50. Index cần căn cứ vào phân bố và pattern query.

### 18.3. Có thể nạp thừa cột của các subtype

Khi load entity đầy đủ ở root, Hibernate có thể select một tập cột rộng để dựng object thuộc các subclass. Nếu màn hình chỉ cần số tiền và trạng thái, dùng DTO projection. Không nên quy toàn bộ chi phí cho discriminator mà bỏ qua số cột và số hàng thực đọc.

### 18.4. Batch insert và ID generation

SINGLE_TABLE không tự quyết định khả năng batch insert. Với `GenerationType.IDENTITY`, việc cần lấy ID ngay có thể hạn chế batching trong Hibernate tùy phiên bản và driver. Khi xử lý nhập hàng loạt, cần xem cấu hình JDBC batch size, chiến lược sinh khóa và SQL thực tế.

### 18.5. Cache và thay đổi subtype

Second-level cache hoặc persistence context giữ dữ liệu theo entity identity/type mapping. Việc sửa discriminator trực tiếp ngoài ORM có thể để lại object cũ hoặc cache không tương thích. Với nghiệp vụ thông thường, không “đổi loại” entity bằng SQL; nếu migration bắt buộc làm điều đó, phải có kế hoạch cache invalidation và downtime/rollout phù hợp.

## 19. Lỗi thường gặp và cách xác định nguyên nhân

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Hibernate không nhận diện được subtype khi load | Discriminator có giá trị không được mapping | Kiểm tra dữ liệu và `@DiscriminatorValue` |
| Insert BANK báo NOT NULL trên `card_brand` | Cột riêng CARD đặt NOT NULL cho toàn bảng | Dùng constraint có điều kiện theo discriminator |
| Hibernate tìm bảng `card_payments` không như mong đợi | Mapping lớp con không đúng SINGLE_TABLE hoặc cấu hình bị xung đột | Đặt `@Inheritance` và `@Table` tại root phù hợp |
| Subclass lưu thiếu field riêng | Field chưa được mapping đúng access strategy hoặc schema không khớp | Kiểm tra annotation, vị trí `@Id` và cột vật lý |
| JPQL `FROM Payment` không hoạt động | Root là `@MappedSuperclass` thay vì `@Entity`, hoặc entity không được đăng ký | Dùng root entity thật và cấu hình entity scanning |
| Query subclass trả ít hàng | Filter discriminator hoặc dữ liệu chứa mã không tương ứng | Kiểm tra SQL được sinh và dữ liệu thực |
| Migration đổi tên class làm dữ liệu cũ đọc lỗi | Đã phụ thuộc discriminator mặc định theo entity name | Dùng mã tường minh và migration nếu phải đổi |
| Xóa root gây lỗi FK | Các association/bảng khác vẫn tham chiếu hàng | Thiết kế cascade và ràng buộc FK đúng nghiệp vụ |
| Bảng quá rộng, thêm subtype khó | Mỗi subtype có quá nhiều thuộc tính riêng | Xem xét JOINED, composition hoặc tách aggregate |
| Update thông tin phụ thuộc subtype bị ghi đè | Cập nhật dữ liệu trực tiếp/bulk ngoài ORM hoặc concurrent update | Xem transaction, `@Version` và domain invariants |

## 20. Các quyết định thiết kế nên đi trước annotation

Trước khi chọn SINGLE_TABLE, trả lời:

1. **Subtype có thực sự là một “is-a” của root không?** `CardPayment` là một `Payment`; nhưng `Customer` và `Invoice` không phải quan hệ kế thừa.
2. **Tất cả subtype có chung identity/lifecycle không?** Nếu khác biệt quá lớn, có thể nên tách entity hoặc aggregate.
3. **Có bao nhiêu cột chung và riêng?** SINGLE_TABLE hợp lý khi cột chung nhiều, cột riêng không bùng nổ.
4. **Truy vấn root có thường xuyên không?** Nếu đa hình là use case chính, một bảng có thể là lợi thế.
5. **Cần ràng buộc NOT NULL/UNIQUE/FK riêng cho từng subtype không?** Đánh giá khả năng biểu diễn constraint trên bảng chung.
6. **Sẽ thêm subtype nhiều lần chứ?** Xem ảnh hưởng migration trên một bảng lớn.
7. **Schema có đang được các service khác đọc trực tiếp không?** Discriminator là một hợp đồng dữ liệu cần quản lý.
8. **Có cần truy vấn theo subtype thường xuyên không?** Cân nhắc index và projection phù hợp.

Nếu các subtype có cấu trúc khác nhau hoàn toàn và rất nhiều cột bắt buộc riêng, `JOINED` hoặc tách entity độc lập có thể dễ duy trì hơn. Nếu chỉ cần dùng chung một vài field cơ bản mà không cần truy vấn đa hình, `@MappedSuperclass` hoặc composition có thể đơn giản hơn.

## 21. Bài tập thực hành

### Bài 1: Xác định bảng và discriminator

Cho mapping:

~~~java
@Entity
@Table(name = "notifications")
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(name = "kind")
abstract class Notification {
    @Id
    Long id;
    String message;
}

@Entity
@DiscriminatorValue("EMAIL")
class EmailNotification extends Notification {
    String emailAddress;
}

@Entity
@DiscriminatorValue("SMS")
class SmsNotification extends Notification {
    String phoneNumber;
}
~~~

Hãy phác thảo schema một bảng, chỉ ra cột discriminator và giải thích vì sao `emailAddress`/`phoneNumber` thường nullable ở cấp bảng chung.

### Bài 2: Tại sao không đặt NOT NULL đơn giản?

Một hệ thống có `CardPayment.cardBrand` bắt buộc, trong khi `BankTransferPayment` không có cardBrand. Câu `ALTER TABLE payments ALTER COLUMN card_brand SET NOT NULL` gây lỗi gì? Hãy mô tả CHECK constraint phù hợp với discriminator CARD.

### Bài 3: Truy vấn đa hình

Với hệ phân cấp `Payment` ở trên, viết JPQL để:

1. Lấy 20 payment gần nhất, không phân biệt subtype.
2. Lấy tất cả `CardPayment` của brand VISA.
3. Lọc các payment chỉ có subtype BANK bằng `TYPE`.

Giải thích vì sao các truy vấn này không cần join bảng subclass với SINGLE_TABLE.

### Bài 4: Phân biệt inheritance với MappedSuperclass

Giả sử `AuditedEntity` chỉ chứa `createdAt` và `updatedAt` để nhiều entity khác dùng lại, còn các entity đó không cần query chung như một hệ phân cấp. Nên chọn `@MappedSuperclass` hay `@Inheritance(SINGLE_TABLE)`? Vì sao?

### Bài 5: Migration discriminator

Database đã có hàng `payment_type = 'WIRE'`, trong khi code mới đổi tên thành `@DiscriminatorValue("BANK")`. Hệ quả gì có thể xảy ra? Nếu cần đổi mã, bạn sẽ thực hiện những bước migration và rollout nào?

### Gợi ý trả lời

- **Bài 1:** Một bảng `notifications` chứa `id`, `kind`, `message`, `emailAddress` và `phoneNumber`; hai cột riêng subtype thường NULL ở các hàng khác.
- **Bài 2:** NOT NULL toàn cột sẽ chặn BANK/CASH; dùng CHECK theo điều kiện `payment_type <> 'CARD' OR card_brand IS NOT NULL`.
- **Bài 3:** Query `FROM Payment` cho toàn bộ hierarchy; `FROM CardPayment` cho subtype; `WHERE TYPE(p) = BankTransferPayment` cho kiểu BANK.
- **Bài 4:** `@MappedSuperclass` phù hợp vì chỉ cần tái sử dụng mapping, không có nhu cầu truy vấn/identity đa hình qua root.
- **Bài 5:** Giá trị cũ không khớp discriminator mới có thể gây lỗi load; cần backfill mã, kiểm soát code cũ/mới, constraint và kiểm tra dữ liệu.

---

**Ghi nhớ:** Với `@Inheritance(strategy = InheritanceType.SINGLE_TABLE)`, **tất cả entity trong cùng hệ phân cấp được lưu vào một bảng**, cột discriminator xác định subtype và các cột riêng thường phải chấp nhận NULL cho những hàng thuộc subtype khác. Chiến lược này thuận tiện cho truy vấn đa hình và thường tránh JOIN giữa bảng cha–con, nhưng cần thiết kế ràng buộc có điều kiện, migration, index và kích thước bảng phù hợp với nghiệp vụ.
