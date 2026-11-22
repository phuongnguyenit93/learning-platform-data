# Chi phí truy vấn khi số kiểu con hoặc độ sâu kế thừa tăng trong Hibernate ORM

## 1. Mục tiêu: hiểu chi phí của cả cây kế thừa, không chỉ của một entity

Kế thừa trong Java cho phép biểu diễn một khái niệm chung bằng lớp cha và nhiều lớp con. Trong Hibernate ORM, khi lớp cha cũng là **entity**, một truy vấn kiểu cha có thể phải trả về những **thực thể thuộc nhiều kiểu con khác nhau**. Hibernate cần vừa lấy các cột dữ liệu vừa xác định object cụ thể cần tạo. Khi số kiểu con hoặc độ sâu của cây tăng, phần SQL mà database phải xử lý có thể phình to đáng kể.

Ví dụ hệ thống thanh toán của ứng dụng đặt hàng có lớp **Payment** và các kiểu:

- **CardPayment**: thanh toán thẻ, có bốn số cuối và thông tin cổng xử lý.
- **WalletPayment**: ví điện tử, có tên ví và mã giao dịch.
- **BankTransferPayment**: chuyển khoản, có mã tham chiếu ngân hàng.
- **CashPayment**: tiền mặt, có người thu.

CardPayment và WalletPayment còn cùng kế thừa **DigitalPayment**, một loại thanh toán điện tử có thông tin gateway chung.

~~~mermaid
classDiagram
    Payment <|-- DigitalPayment
    Payment <|-- BankTransferPayment
    Payment <|-- CashPayment
    DigitalPayment <|-- CardPayment
    DigitalPayment <|-- WalletPayment
    class Payment {
      +Long id
      +Long orderId
      +BigDecimal amount
      +Instant occurredAt
    }
    class DigitalPayment {
      +String gatewayCode
    }
    class CardPayment {
      +String cardLast4
    }
    class WalletPayment {
      +String walletProvider
    }
    class BankTransferPayment {
      +String bankReference
    }
    class CashPayment {
      +String collectedBy
    }
~~~

Giả sử màn hình “Tất cả thanh toán” thực hiện JPQL:

~~~java
select p from Payment p
where p.orderId = :orderId
order by p.occurredAt desc, p.id desc
~~~

Đây là **truy vấn đa hình (polymorphic query)**. Hibernate cần trả về CardPayment, WalletPayment, BankTransferPayment hoặc CashPayment tùy hàng dữ liệu. Nếu cùng hệ thống chỉ truy vấn CardPayment, phạm vi dữ liệu cần đọc khác hẳn. Với một cây có 4 kiểu con, có thể chưa thấy rõ vấn đề; khi cây tăng thành 20–50 kiểu con và sâu 4–6 tầng, chiến lược ánh xạ quyết định cấu trúc SQL và khả năng mở rộng.

Sau bài này, bạn sẽ:

1. Hiểu vì sao truy vấn từ **entity cha** có thể đắt hơn truy vấn từ **entity con cụ thể**.
2. So sánh ba chiến lược JPA/Hibernate: **SINGLE_TABLE**, **JOINED**, **TABLE_PER_CLASS**.
3. Phân tích tác động của **số kiểu con**, **độ sâu**, **số hàng**, **bề rộng dòng** và **kiểu truy vấn**.
4. Biết cách dùng **TYPE**, **TREAT**, projection DTO, phân trang và fetch plan để giới hạn dữ liệu truy vấn.
5. Đọc SQL Hibernate sinh ra, dùng **EXPLAIN (ANALYZE, BUFFERS)** và các chỉ số Hibernate để đánh giá bằng dữ liệu thật.
6. Nhận biết khi nào nên giảm mức kế thừa, tách dữ liệu thành composition hoặc dùng **@MappedSuperclass**.

**Phạm vi ví dụ:** Java 17+, Jakarta Persistence (package **jakarta.persistence**), Hibernate ORM 6.x, PostgreSQL. SQL dưới đây mô tả **hình dạng truy vấn có thể phát sinh**, không khẳng định Hibernate sẽ sinh chính xác từng alias, JOIN hay kế hoạch thực thi trên mọi phiên bản/dialect.

## 2. Tại sao “thêm một subclass” có thể làm truy vấn cũ chậm đi?

Một repository truy vấn:

~~~java
List<Payment> payments = entityManager.createQuery(
    "select p from Payment p where p.orderId = :orderId",
    Payment.class
).setParameter("orderId", orderId)
 .getResultList();
~~~

Khi hệ thống có thêm một lớp con như CryptoPayment, code JPQL trên **không đổi**. Nhưng tùy chiến lược kế thừa, Hibernate có thể phải:

- Đọc thêm cột mới trên một bảng rộng.
- JOIN thêm bảng subclass mới để lấy field riêng hoặc xác định kiểu cụ thể.
- Thêm một nhánh **UNION ALL** đại diện cho một bảng concrete subclass.
- Thay đổi kế hoạch sort, count, phân trang, memory và số byte truyền giữa DB và Java.

Chi phí còn có thể tăng ở phía ứng dụng: Hibernate hydrate nhiều kiểu object hơn, quản lý entity trong persistence context, tạo proxy/liên kết và phân bổ bộ nhớ cho result set lớn. Do đó **số câu SQL không phải đơn vị đo chi phí duy nhất**: một SQL có thể chứa hàng chục JOIN, một UNION nhiều nhánh hoặc trả hàng triệu byte.

Phân biệt các đại lượng:

| Đại lượng | Ký hiệu tham khảo | Tác động chính |
|---|---|---|
| Số concrete subclass | **C** | Số loại thực thể có bản ghi thật; ảnh hưởng số nhánh UNION của TABLE_PER_CLASS |
| Số bảng subclass trong JOINED | **T** | Có thể làm tăng số JOIN ở truy vấn đa hình |
| Độ sâu đường kế thừa | **D** | Số tầng cha–con phải lần theo khi truy vấn một kiểu con sâu |
| Số hàng phù hợp bộ lọc | **R** | Ảnh hưởng scan, sort, memory, network, hydration |
| Số cột thuộc toàn hierarchy | **W** | Ảnh hưởng bề rộng row trong SINGLE_TABLE hoặc schema UNION |
| Số collection fetch thêm | **F** | Có thể nhân số hàng SQL qua JOIN FETCH, độc lập với inheritance |

Các ký hiệu chỉ dùng để **tư duy về xu hướng**, không tạo thành công thức thời gian chạy. Query plan, chỉ mục, phân bố dữ liệu, độ chọn lọc của điều kiện, cache, IO và phần cứng thường quyết định độ trễ thực tế nhiều hơn một con số C hay D.

## 3. Cấu hình một hierarchy mẫu bằng Jakarta Persistence

### 3.1. Entity cha dùng chung

Bắt đầu với chiến lược **SINGLE_TABLE** để nhìn rõ các thành phần. Các ví dụ JOINED/TABLE_PER_CLASS ở phần sau là **những phương án thay thế** cho cùng mô hình nghiệp vụ, không phải ba annotation cùng đặt lên một entity.

~~~java
package com.example.shop.payment;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;

@Entity
@Table(name = "payments")
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(name = "payment_type",
    discriminatorType = DiscriminatorType.STRING, length = 32)
public abstract class Payment {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE, generator = "payment_seq")
    @SequenceGenerator(name = "payment_seq",
        sequenceName = "payment_seq", allocationSize = 50)
    private Long id;

    @Column(name = "order_id", nullable = false)
    private Long orderId;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal amount;

    @Column(name = "occurred_at", nullable = false)
    private Instant occurredAt;

    protected Payment() {}

    protected Payment(Long orderId, BigDecimal amount, Instant occurredAt) {
        if (orderId == null || amount == null || amount.signum() < 0) {
            throw new IllegalArgumentException("Thanh toán không hợp lệ");
        }
        this.orderId = orderId;
        this.amount = amount;
        this.occurredAt = Objects.requireNonNull(occurredAt);
    }

    public Long getId() { return id; }
    public Long getOrderId() { return orderId; }
    public BigDecimal getAmount() { return amount; }
    public Instant getOccurredAt() { return occurredAt; }
}
~~~

Khi quản lý schema bằng migration, sequence **payment_seq** thật phải phù hợp với chiến lược cấp phát của Hibernate. Đoạn này dùng một sequence chung để việc so sánh ba chiến lược rõ ràng; không phụ thuộc vào identity tăng độc lập trên mỗi bảng concrete subclass.

### 3.2. Lớp trung gian và các lớp con

~~~java
package com.example.shop.payment;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;

@Entity
@DiscriminatorValue("DIGITAL")
public abstract class DigitalPayment extends Payment {
    @Column(name = "gateway_code", length = 80)
    private String gatewayCode;

    protected DigitalPayment() {}

    protected DigitalPayment(Long orderId, BigDecimal amount,
                             Instant occurredAt, String gatewayCode) {
        super(orderId, amount, occurredAt);
        this.gatewayCode = Objects.requireNonNull(gatewayCode);
    }

    public String getGatewayCode() { return gatewayCode; }
}
~~~

~~~java
package com.example.shop.payment;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;

@Entity
@DiscriminatorValue("CARD")
public class CardPayment extends DigitalPayment {
    @Column(name = "card_last4", length = 4)
    private String cardLast4;

    protected CardPayment() {}

    public CardPayment(Long orderId, BigDecimal amount, Instant time,
                       String gatewayCode, String cardLast4) {
        super(orderId, amount, time, gatewayCode);
        if (cardLast4 == null || !cardLast4.matches("[0-9]{4}")) {
            throw new IllegalArgumentException("Bốn số cuối thẻ không hợp lệ");
        }
        this.cardLast4 = cardLast4;
    }

    public String getCardLast4() { return cardLast4; }
}

@Entity
@DiscriminatorValue("WALLET")
class WalletPayment extends DigitalPayment {
    @Column(name = "wallet_provider", length = 80)
    private String walletProvider;

    protected WalletPayment() {}

    WalletPayment(Long orderId, BigDecimal amount, Instant time,
                  String gatewayCode, String walletProvider) {
        super(orderId, amount, time, gatewayCode);
        this.walletProvider = Objects.requireNonNull(walletProvider);
    }

    public String getWalletProvider() { return walletProvider; }
}

@Entity
@DiscriminatorValue("BANK")
class BankTransferPayment extends Payment {
    @Column(name = "bank_reference", length = 100)
    private String bankReference;

    protected BankTransferPayment() {}

    BankTransferPayment(Long orderId, BigDecimal amount, Instant time,
                        String bankReference) {
        super(orderId, amount, time);
        this.bankReference = Objects.requireNonNull(bankReference);
    }

    public String getBankReference() { return bankReference; }
}

@Entity
@DiscriminatorValue("CASH")
class CashPayment extends Payment {
    @Column(name = "collected_by", length = 100)
    private String collectedBy;

    protected CashPayment() {}

    CashPayment(Long orderId, BigDecimal amount, Instant time,
                String collectedBy) {
        super(orderId, amount, time);
        this.collectedBy = Objects.requireNonNull(collectedBy);
    }

    public String getCollectedBy() { return collectedBy; }
}
~~~

Đoạn sau dùng nhiều class package-private trong cùng package để cô đọng ví dụ. Trong ứng dụng thật, có thể đặt mỗi concrete entity trong một file riêng và công khai API tạo object theo nhu cầu. Mỗi entity có constructor không tham số phù hợp cho JPA, không khai báo class **final** để tương thích các cơ chế proxy thông thường.

Lưu ý rằng **DigitalPayment là abstract entity**: nó tạo một tầng kế thừa nhưng không có bản ghi mang kiểu trừu tượng đó. Vẫn có thể query DigitalPayment và nhận CardPayment/WalletPayment; một tầng trừu tượng vẫn ảnh hưởng thiết kế bảng trong một số chiến lược.

## 4. Chiến lược SINGLE_TABLE: số subclass tăng thì bảng rộng hơn

Với:

~~~java
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(name = "payment_type")
~~~

toàn bộ hierarchy dùng **một bảng payments**. Các cột riêng của từng subclass xuất hiện trên cùng bảng; cột **payment_type** xác định object Java cần dựng.

### 4.1. Hình dạng schema

~~~sql
CREATE TABLE payments (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    amount NUMERIC(19, 2) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    payment_type VARCHAR(32) NOT NULL,
    gateway_code VARCHAR(80),
    card_last4 VARCHAR(4),
    wallet_provider VARCHAR(80),
    bank_reference VARCHAR(100),
    collected_by VARCHAR(100)
);

CREATE INDEX idx_payments_order_time
    ON payments(order_id, occurred_at DESC, id DESC);
CREATE INDEX idx_payments_type_order
    ON payments(payment_type, order_id);
~~~

Ví dụ dữ liệu:

| payment_type | gateway_code | card_last4 | wallet_provider | bank_reference | collected_by |
|---|---|---|---|---|---|
| CARD | gateway-a | 1234 | NULL | NULL | NULL |
| WALLET | gateway-b | NULL | wallet-x | NULL | NULL |
| BANK | NULL | NULL | NULL | bank-7381 | NULL |
| CASH | NULL | NULL | NULL | NULL | cashier-01 |

Trong SINGLE_TABLE, các cột chỉ dành cho một subtype thường phải **nullable ở cấp schema**, dù trong subtype tương ứng chúng bắt buộc theo nghiệp vụ. Nếu muốn bảo vệ dữ liệu, có thể dùng **CHECK điều kiện theo discriminator**:

~~~sql
ALTER TABLE payments
ADD CONSTRAINT ck_card_last4
CHECK (payment_type <> 'CARD' OR card_last4 IS NOT NULL);
~~~

Đây là constraint minh họa của PostgreSQL, chưa kiểm tra toàn bộ cột/rule khác. Mỗi subtype mới có thể kéo theo migration thêm cột, default, constraint và index.

### 4.2. Truy vấn đa hình ở lớp cha

JPQL:

~~~java
select p from Payment p
where p.orderId = :orderId
order by p.occurredAt desc, p.id desc
~~~

SQL có thể có dạng:

~~~sql
SELECT p.id, p.order_id, p.amount, p.occurred_at, p.payment_type,
       p.gateway_code, p.card_last4, p.wallet_provider,
       p.bank_reference, p.collected_by
FROM payments p
WHERE p.order_id = ?
ORDER BY p.occurred_at DESC, p.id DESC;
~~~

**Không có JOIN giữa các bảng subtype và không có UNION**. Hibernate đọc discriminator rồi hydrate entity tương ứng. Khi số concrete subclass tăng từ 4 lên 20:

- Số bảng đọc vẫn là **1**.
- Số cột tùy subclass có thể tăng mạnh.
- SQL lấy trọn entity có thể chọn thêm nhiều cột; bề rộng result set và chi phí hydrate có thể tăng.
- Một bảng chứa nhiều loại dữ liệu, dẫn tới nhiều cột NULL và nhiều chỉ mục/constraint theo loại.
- Tổng số hàng và pattern truy cập của các subtype chia sẻ cùng heap/index/storage.

**Độ sâu D** gần như không tự tạo thêm JOIN vì các field kế thừa vẫn nằm trong bảng duy nhất. Đây là ưu điểm lớn của SINGLE_TABLE khi hệ thống thường truy vấn qua lớp cha.

### 4.3. Truy vấn theo subtype

~~~java
select p from CardPayment p
where p.orderId = :orderId
~~~

SQL có thể lọc discriminator:

~~~sql
SELECT p.id, p.order_id, p.amount, p.occurred_at,
       p.gateway_code, p.card_last4
FROM payments p
WHERE p.payment_type = 'CARD' AND p.order_id = ?;
~~~

Khi query một concrete subclass, Hibernate có thể giảm số cột cần đọc so với query lớp cha. Chỉ mục theo **(payment_type, order_id)** có thể giúp khi truy vấn này phổ biến và có tính chọn lọc. Không tự động lập index cho mọi subtype nếu tổng chi phí ghi/không gian lưu trữ vượt lợi ích.

### 4.4. Chi phí khi thêm nhiều subclass

SINGLE_TABLE thường có **đường đọc ngắn** cho polymorphism, nhưng khi W tăng rất cao:

1. Bảng rộng có thể làm một lần SELECT toàn entity mang nhiều cột và tăng lưu lượng mạng.
2. Trong PostgreSQL, giá trị NULL và cơ chế lưu trữ thực tế không đồng nghĩa mọi cột NULL tiêu thụ đầy đủ kích thước kiểu dữ liệu; tuy nhiên row layout, metadata và việc chọn nhiều field vẫn có chi phí.
3. Những field lớn như JSON, text dài hoặc byte[] nên được thiết kế theo nhu cầu truy cập; không đưa tất cả vào base entity chỉ vì dùng cùng bảng.
4. Thêm loại mới có thể yêu cầu migration trên bảng thanh toán chung đang rất lớn.
5. Ràng buộc bắt buộc của riêng subclass khó diễn đạt chỉ bằng NOT NULL đơn giản; phải dùng conditional check/validation.

Nếu query chỉ cần **id, amount, occurredAt**, projection DTO sẽ giúp giảm bề rộng dữ liệu ngay cả với SINGLE_TABLE.

## 5. Chiến lược JOINED: số bảng và độ sâu quyết định số JOIN

Đổi mapping của Payment thành:

~~~java
@Entity
@Table(name = "payments")
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class Payment {
    // Các field và constructor dùng chung như phần trước.
}
~~~

Các subclass vẫn là entity kế thừa Payment. Có thể khai báo **@Table** rõ ràng trên từng subclass để kiểm soát tên bảng; với JOINED có thể khai báo **@PrimaryKeyJoinColumn** khi cần thay tên cột PK/FK.

### 5.1. Mỗi tầng có bảng riêng

Một thiết kế SQL minh họa:

~~~sql
CREATE TABLE payments (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    amount NUMERIC(19, 2) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE digital_payments (
    id BIGINT PRIMARY KEY REFERENCES payments(id),
    gateway_code VARCHAR(80) NOT NULL
);

CREATE TABLE card_payments (
    id BIGINT PRIMARY KEY REFERENCES digital_payments(id),
    card_last4 VARCHAR(4) NOT NULL
);

CREATE TABLE wallet_payments (
    id BIGINT PRIMARY KEY REFERENCES digital_payments(id),
    wallet_provider VARCHAR(80) NOT NULL
);

CREATE TABLE bank_transfer_payments (
    id BIGINT PRIMARY KEY REFERENCES payments(id),
    bank_reference VARCHAR(100) NOT NULL
);

CREATE TABLE cash_payments (
    id BIGINT PRIMARY KEY REFERENCES payments(id),
    collected_by VARCHAR(100) NOT NULL
);
~~~

Với CardPayment, một bản ghi cùng ID xuất hiện ở **payments → digital_payments → card_payments**. Các trường của từng tầng nằm tại bảng tương ứng. Trong DB thật, migration, tên bảng và cấu hình discriminator có thể khác theo mapping; SQL minh họa tập trung vào quan hệ khóa chung.

### 5.2. Truy vấn một kiểu con sâu

JPQL:

~~~java
select p from CardPayment p
where p.orderId = :orderId
~~~

SQL có thể cần nối ba tầng:

~~~sql
SELECT p.id, p.order_id, p.amount, p.occurred_at,
       d.gateway_code, c.card_last4
FROM card_payments c
JOIN digital_payments d ON d.id = c.id
JOIN payments p ON p.id = d.id
WHERE p.order_id = ?;
~~~

Với lớp con ở độ sâu **D**, truy vấn lấy trọn object thường phải nối các bảng trên đường từ subclass đến root. Nếu thêm một tầng **AuthenticatedCardPayment** rồi **TokenizedCardPayment**, truy vấn subtype sâu có thể cần nhiều JOIN hơn nữa.

Mặc dù mỗi JOIN thường dùng khóa chính/khóa ngoại và có index hỗ trợ, việc thêm tầng vẫn làm optimizer có thêm thao tác và có thể tăng IO, CPU, độ phức tạp kế hoạch. Không thể nói chi phí bằng đúng D lần một truy vấn: planner có thể tối ưu, dữ liệu có thể đã ở cache, và điều kiện lọc có thể loại phần lớn hàng.

### 5.3. Truy vấn đa hình từ root

JPQL:

~~~java
select p from Payment p
where p.orderId = :orderId
~~~

Để materialize đầy đủ các concrete subtype, Hibernate thường phải lấy thông tin từ các bảng subclass. Một cấu trúc SQL khả dĩ:

~~~sql
SELECT p.id, p.order_id, p.amount, p.occurred_at,
       d.gateway_code, c.card_last4, w.wallet_provider,
       b.bank_reference, h.collected_by
FROM payments p
LEFT JOIN digital_payments d ON d.id = p.id
LEFT JOIN card_payments c ON c.id = d.id
LEFT JOIN wallet_payments w ON w.id = d.id
LEFT JOIN bank_transfer_payments b ON b.id = p.id
LEFT JOIN cash_payments h ON h.id = p.id
WHERE p.order_id = ?;
~~~

Ở đây nhiều LEFT JOIN **không** có nghĩa mỗi payment thực sự có dữ liệu ở mọi bảng. Các bảng khác nhánh chỉ trả cột NULL. Hibernate dựa vào metadata/discriminator hoặc sự hiện diện của hàng subclass để xác định concrete type.

Khi thêm một subtype mới ở nhánh khác, **truy vấn cũ từ Payment** có thể phải bao gồm bảng mới để tạo entity đầy đủ. Khi thêm một tầng ở một nhánh, truy vấn subtype của nhánh đó cũng cần thêm đường JOIN.

Không phải mọi query ở root luôn join tất cả bảng:

- Query chỉ lấy vài field chung qua **DTO projection** có thể tránh hydrate các subclass và không cần toàn bộ JOIN.
- Một query aggregate, count hoặc filter bằng root fields có thể được optimizer hoặc Hibernate xử lý ngắn hơn.
- Cách xác định concrete type, đặc biệt khi có discriminator và query-specific fetch plan, phụ thuộc mapping/Hibernate version.

Vì vậy kết luận đúng là **truy vấn materialize toàn bộ hierarchy có nguy cơ tăng số JOIN theo số bảng subtype**, chứ không phải mọi câu query từ Payment luôn join đúng T bảng.

### 5.4. Khi JOINED hữu ích

JOINED phù hợp khi:

- Có nhiều thuộc tính đặc thù nhưng mỗi subtype thường được truy vấn riêng.
- Cần NOT NULL, unique constraint và index rõ ràng cho trường của từng subclass.
- Muốn tránh một bảng khổng lồ chứa mọi field của mọi subtype.
- Cây kế thừa tương đối ổn định, không quá sâu, và polymorphic root query không phải đường truy cập nóng nhất.

Nhược điểm:

- **Root polymorphic query** có thể có nhiều LEFT JOIN.
- **Subtype sâu** phải join dọc cây.
- Insert hoặc delete concrete entity chạm nhiều bảng; flush có thể phát sinh nhiều SQL.
- Bộ kế hoạch tối ưu có thể phức tạp hơn, đặc biệt khi lọc bằng thuộc tính ở nhiều nhánh.

JOINED thường là lựa chọn cân bằng về chuẩn hóa dữ liệu, nhưng không nên mặc định là nhanh nhất khi hierarchy phình rộng và sâu.

## 6. Chiến lược TABLE_PER_CLASS: số concrete subclass quyết định UNION

Đổi mapping:

~~~java
@Entity
@Inheritance(strategy = InheritanceType.TABLE_PER_CLASS)
public abstract class Payment {
    // Các field, constructor, ID generator dùng chung như phần trước.
}
~~~

Không sử dụng discriminator column của SINGLE_TABLE cho chiến lược này; các bảng concrete tự xác định type. Mỗi concrete subclass có **bảng riêng, chứa cả các field kế thừa**. Với root abstract, thường không có hàng Payment thuần, và query đa hình được tổng hợp từ bảng concrete. Abstract DigitalPayment cũng không đại diện loại thanh toán có thể lưu riêng.

### 6.1. Hình dạng schema

~~~text
card_payments:
    id, order_id, amount, occurred_at, gateway_code, card_last4

wallet_payments:
    id, order_id, amount, occurred_at, gateway_code, wallet_provider

bank_transfer_payments:
    id, order_id, amount, occurred_at, bank_reference

cash_payments:
    id, order_id, amount, occurred_at, collected_by
~~~

Các cột chung như **order_id**, **amount**, **occurred_at** được lặp lại trên các bảng concrete. Với TABLE_PER_CLASS, giữ ID duy nhất trong cả hierarchy là quan trọng; một **sequence chung** cho mọi subclass là lựa chọn thông dụng. Dùng IDENTITY độc lập trên từng bảng có thể sinh ID trùng giữa các loại và không phù hợp với yêu cầu danh tính đa hình trong nhiều mô hình/provider.

### 6.2. Query subtype cụ thể

~~~java
select p from CardPayment p
where p.orderId = :orderId
~~~

SQL có thể rất đơn giản:

~~~sql
SELECT p.id, p.order_id, p.amount, p.occurred_at,
       p.gateway_code, p.card_last4
FROM card_payments p
WHERE p.order_id = ?;
~~~

Không cần join bảng root hay bảng digital vì mọi field liên quan đã được sao chép xuống bảng concrete. Độ sâu kế thừa không trực tiếp biến truy vấn subtype cụ thể thành D JOIN.

### 6.3. Query root đa hình

Ngược lại:

~~~java
select p from Payment p
where p.orderId = :orderId
order by p.occurredAt desc
~~~

Hibernate thường phải tổng hợp hàng từ các bảng concrete bằng **UNION ALL** với các cột đồng nhất; những cột không có ở một nhánh được đưa giá trị NULL với kiểu phù hợp:

~~~sql
SELECT u.id, u.order_id, u.amount, u.occurred_at,
       u.gateway_code, u.card_last4, u.wallet_provider,
       u.bank_reference, u.collected_by, u.type_marker
FROM (
    SELECT id, order_id, amount, occurred_at,
           gateway_code, card_last4,
           CAST(NULL AS VARCHAR(80)) AS wallet_provider,
           CAST(NULL AS VARCHAR(100)) AS bank_reference,
           CAST(NULL AS VARCHAR(100)) AS collected_by,
           1 AS type_marker
    FROM card_payments

    UNION ALL

    SELECT id, order_id, amount, occurred_at,
           gateway_code,
           CAST(NULL AS VARCHAR(4)),
           wallet_provider,
           CAST(NULL AS VARCHAR(100)),
           CAST(NULL AS VARCHAR(100)),
           2
    FROM wallet_payments

    UNION ALL

    SELECT id, order_id, amount, occurred_at,
           CAST(NULL AS VARCHAR(80)),
           CAST(NULL AS VARCHAR(4)),
           CAST(NULL AS VARCHAR(80)),
           bank_reference,
           CAST(NULL AS VARCHAR(100)),
           3
    FROM bank_transfer_payments

    UNION ALL

    SELECT id, order_id, amount, occurred_at,
           CAST(NULL AS VARCHAR(80)),
           CAST(NULL AS VARCHAR(4)),
           CAST(NULL AS VARCHAR(80)),
           CAST(NULL AS VARCHAR(100)),
           collected_by, 4
    FROM cash_payments
) u
WHERE u.order_id = ?
ORDER BY u.occurred_at DESC;
~~~

Đây là SQL **giản lược để diễn giải**, không phải bản sao nguyên văn SQL Hibernate sinh. Với PostgreSQL/Hibernate, SQL thực tế có thể đẩy predicate vào các nhánh hoặc chọn cách render khác. Nhưng phần chi phí quan trọng vẫn là **nhiều nguồn dữ liệu cần được hợp nhất**.

Khi số concrete subtype tăng từ **C = 4** lên **C = 30**, root query có thể có **30 nhánh UNION ALL**, mỗi nhánh có plan scan/index riêng. Với ORDER BY và LIMIT trên kết quả toàn hierarchy, database cần phối hợp thứ tự giữa các bảng, có thể dùng sort, append hoặc merge tùy planner và index. Phân trang sâu với OFFSET có thể phải đọc/bỏ qua nhiều hàng hơn.

### 6.4. Ảnh hưởng của độ sâu

Về cấu trúc query subtype cụ thể, một tầng con mới không nhất thiết thêm JOIN. Nhưng các field của lớp cha và các lớp trung gian được lặp lại xuống bảng concrete. Khi thay đổi một field chung trong hierarchy:

- Schema của **nhiều bảng concrete** có thể cần migration.
- Index/constraint cho field chung có thể phải được áp dụng trên mọi bảng.
- Query đa hình vẫn cần hợp nhất các nhánh concrete.

Vì vậy TABLE_PER_CLASS đổi **chi phí JOIN** thành **chi phí UNION, nhân bản schema và quản trị nhiều bảng**.

### 6.5. Khi TABLE_PER_CLASS thích hợp

Nó có thể hợp lý khi:

- Phần lớn use case truy vấn **một subtype cụ thể**.
- Các subtype khá độc lập, dữ liệu không cần join xuyên hierarchy thường xuyên.
- Mỗi bảng cần index/retention và vận hành riêng.

Nó thường kém hấp dẫn khi hệ thống thường xuyên cần “tất cả Payment”, phân trang toàn hierarchy, aggregate toàn hierarchy hoặc có nhiều concrete subtype. Một tính năng chung mới trên lớp cha cũng có chi phí migration lặp lại.

## 7. So sánh trực tiếp theo số kiểu con và độ sâu

| Khía cạnh | SINGLE_TABLE | JOINED | TABLE_PER_CLASS |
|---|---|---|---|
| Lưu dữ liệu | Một bảng cho cả hierarchy | Bảng root và bảng cho các tầng subclass | Mỗi concrete subclass một bảng có cả field kế thừa |
| Root polymorphic full-entity query | Thường một SELECT từ một bảng | Có thể nhiều LEFT JOIN tới bảng subclass | Thường UNION ALL nhiều bảng concrete |
| Khi **C** tăng | Số cột, kiểu discriminator, nullability/index có thể tăng | Số bảng cần JOIN cho materialization có thể tăng | Số nhánh UNION tăng gần số concrete type |
| Khi **D** tăng | Không tự làm tăng số bảng JOIN | Truy vấn subclass sâu cần nhiều JOIN trên đường kế thừa | Không tự thêm JOIN; các field kế thừa bị nhân bản |
| Query một concrete subclass | Lọc discriminator, vẫn ở bảng chung | JOIN đường từ leaf đến root | Thường đọc một bảng concrete |
| Insert một concrete entity | Thường một bảng | Nhiều bảng dọc đường kế thừa | Một bảng concrete |
| Constraint field riêng | Khó dùng NOT NULL vô điều kiện | Dễ đặt tại bảng subclass | Dễ đặt tại bảng concrete |
| Field chung | Một bản sao | Một bản sao ở bảng root/tầng chung | Lặp lại trên nhiều concrete table |
| Index phục vụ subtype | Có thể dùng discriminator/partial index | Index của bảng tương ứng + PK/FK join | Index riêng cho từng bảng concrete |
| Nguy cơ nổi bật | Bảng quá rộng, nhiều cột nullable | JOIN lớn, chiều sâu, flush nhiều bảng | UNION lớn, phân trang toàn hierarchy, schema lặp |

**Không có chiến lược nhanh nhất trong mọi truy vấn.** Nếu 95% traffic chỉ truy vấn CardPayment, TABLE_PER_CLASS có thể mạnh; nếu phần lớn API đọc Payment chung, SINGLE_TABLE thường dễ tối ưu hơn. JOINED có thể rất tốt khi truy vấn subtype tương đối ít tầng và cần schema chuẩn hóa, nhưng root full-entity query trên hierarchy rộng là điểm phải đo.

## 8. Phân tích tăng trưởng theo những tình huống cụ thể

### 8.1. Thêm nhiều sibling subtype nhưng giữ độ sâu

Ban đầu Payment có 4 loại cùng một tầng; sau đó thành 24 loại cùng một tầng.

~~~text
Payment
  |- CardPayment
  |- WalletPayment
  |- CashPayment
  |- BankTransferPayment
  |- ...
  \- Type24Payment
~~~

- **SINGLE_TABLE:** vẫn có một bảng; số cột riêng và discriminator values có thể tăng. Query root chịu ảnh hưởng bề rộng row và số hàng hơn là số JOIN.
- **JOINED:** nếu query cần full entity, số LEFT JOIN đến các bảng subtype có thể tăng từ khoảng 4 lên khoảng 24.
- **TABLE_PER_CLASS:** root query có thể tăng từ 4 lên 24 nhánh UNION ALL.

Nếu query trả một trang chỉ gồm 20 bản ghi nhưng SQL cần chọn nhiều bảng và sắp xếp ở cấp hierarchy, chi phí **đọc/tổng hợp trước LIMIT** có thể đáng kể. Một LIMIT nhỏ không tự bảo đảm query rẻ.

### 8.2. Giữ số leaf, tăng độ sâu

Ban đầu:

~~~text
Payment -> CardPayment
~~~

Sau đó:

~~~text
Payment -> DigitalPayment -> AuthorizedPayment
        -> CardPayment -> TokenizedCardPayment
~~~

- **SINGLE_TABLE:** các thuộc tính của tầng trung gian thành cột trên cùng bảng; không tạo chuỗi JOIN.
- **JOINED:** để hydrate TokenizedCardPayment, phải đọc dữ liệu ở các tầng có bảng trên đường kế thừa.
- **TABLE_PER_CLASS:** bảng TokenizedCardPayment thường chứa cả field ở các tầng cha; query riêng subtype không cần join dọc hierarchy, nhưng schema leaf rộng và field chung lặp lại.

Một cây sâu 5 nhưng chỉ có 2 concrete type có thể tạo rất ít UNION ở TABLE_PER_CLASS, trong khi một cây nông với 30 concrete type có nhiều nhánh UNION. **Số kiểu con và độ sâu là hai trục độc lập**, phải đánh giá riêng.

### 8.3. Thêm cả chiều rộng lẫn chiều sâu

Trong hierarchy lớn, một root query có thể chịu ảnh hưởng của:

- Cây JOINED có nhiều nhánh và nhiều tầng.
- Nhiều liên kết entity khác (Customer, Order, Account) cần eager/fetch join.
- Bộ lọc theo field của subtype, khiến SQL cần tham chiếu các bảng con.
- Sort theo trường riêng của subtype hoặc biểu thức computed.
- Phân trang kết quả polymorphic.

Khi kết hợp các yếu tố, chi phí có thể phức tạp hơn tăng tuyến tính đơn giản. Ví dụ nhiều **collection JOIN FETCH** còn có thể nhân số hàng kết quả. Vì vậy không dùng một ước lượng “mỗi subclass thêm đúng một mili giây” hay “mỗi tầng làm query chậm gấp đôi”; phải xem execution plan.

## 9. Chọn đúng kiểu truy vấn: root, subclass, TYPE và TREAT

### 9.1. Truy vấn root mặc định là polymorphic

~~~java
List<Payment> payments = em.createQuery(
    "select p from Payment p where p.orderId = :orderId",
    Payment.class
).setParameter("orderId", orderId)
 .getResultList();
~~~

Hibernate có thể trả về hỗn hợp CardPayment, WalletPayment, CashPayment... theo dữ liệu trong DB. Khi use case chỉ cần thanh toán bằng thẻ, truy vấn root rồi lọc bằng **instanceof** trong Java là lãng phí:

~~~java
// Không nên tải tất cả Payment chỉ để lọc CardPayment trong memory.
List<Payment> all = /* root query */;
List<CardPayment> cards = all.stream()
    .filter(CardPayment.class::isInstance)
    .map(CardPayment.class::cast)
    .toList();
~~~

Thay bằng truy vấn subtype:

~~~java
List<CardPayment> cards = em.createQuery(
    "select c from CardPayment c where c.orderId = :orderId",
    CardPayment.class
).setParameter("orderId", orderId)
 .getResultList();
~~~

Trong **SINGLE_TABLE**, nó có thể thêm điều kiện discriminator; trong **JOINED**, join đường subtype; trong **TABLE_PER_CLASS**, thường đọc bảng concrete trực tiếp. Cách truy vấn này cho database cơ hội giới hạn dữ liệu sớm hơn.

### 9.2. Dùng TYPE để lọc theo loại

JPQL hỗ trợ **TYPE** để kiểm tra kiểu entity:

~~~java
select p from Payment p
where type(p) = CardPayment
  and p.orderId = :orderId
~~~

Trong ví dụ, nếu chỉ cần CardPayment, truy vấn trực tiếp **from CardPayment** thường dễ diễn đạt hơn. **TYPE** hữu ích khi cấu trúc query bắt buộc bắt đầu từ root hoặc cần kiểm tra loại trong biểu thức phức tạp. Với các provider/strategy khác nhau, việc lọc TYPE có thể biến thành điều kiện discriminator hoặc lựa chọn nhánh subtype; kiểm tra SQL thực tế.

### 9.3. Dùng TREAT khi cần thuộc tính chỉ có ở subclass

Giả sử cần các khoản thanh toán thẻ có 4 số cuối nhất định:

~~~java
select p from Payment p
where treat(p as CardPayment).cardLast4 = :last4
~~~

**TREAT** cho phép truy cập thuộc tính của subclass trong JPQL. Trong JOINED, nó có thể kéo theo JOIN/điều kiện trên bảng CardPayment; trong TABLE_PER_CLASS, Hibernate có thể phải giới hạn hoặc xử lý nhánh phù hợp. Cú pháp TREAT và SQL sinh ra có những khác biệt theo provider/phiên bản, nên khi bài toán chỉ liên quan một subclass, query trực tiếp subtype vẫn thường đơn giản hơn.

### 9.4. Projection DTO chỉ lấy field của root

Màn hình lịch sử thanh toán thường chỉ cần ID, số tiền và thời gian. Không nhất thiết phải tạo full entity từ mọi subclass:

~~~java
package com.example.shop.payment;

import java.math.BigDecimal;
import java.time.Instant;

public record PaymentListRow(
    Long id, Long orderId, BigDecimal amount, Instant occurredAt
) {}
~~~

JPQL:

~~~java
select new com.example.shop.payment.PaymentListRow(
    p.id, p.orderId, p.amount, p.occurredAt
)
from Payment p
where p.orderId = :orderId
order by p.occurredAt desc, p.id desc
~~~

DTO projection tránh hydrate và theo dõi toàn bộ entity graph. Với JOINED, Hibernate hoặc database có thể bỏ những JOIN không cần thiết khi chỉ lấy field root; với TABLE_PER_CLASS, query root vẫn có thể cần UNION để đọc các bảng concrete vì **không có một bảng root chứa toàn bộ hàng**. Hãy đọc SQL kế tiếp để biết cụ thể.

**DTO không phải thuốc chữa tuyệt đối:** projection cần field của từng subtype hoặc truy vấn gốc TABLE_PER_CLASS có nhiều nhánh vẫn có thể đắt, nhưng đây thường là bước tối ưu đúng hướng cho API chỉ đọc.

## 10. Phân trang trên hierarchy: một LIMIT nhỏ vẫn có thể đắt

Giả sử UI hiển thị 20 khoản thanh toán mỗi trang trên tất cả kiểu con.

~~~java
@Query("""
    select p from Payment p
    where p.orderId = :orderId
    order by p.occurredAt desc, p.id desc
    """)
Page<Payment> findByOrderId(Long orderId, Pageable pageable);
~~~

Đây là ví dụ một phương thức trong Spring Data JPA repository (cần import **Page**, **Pageable**, **@Query**). Thứ tự theo **occurredAt + id** giúp kết quả ổn định hơn so với chỉ sort một timestamp có thể trùng.

### 10.1. Chiến lược tác động đến paging thế nào?

| Strategy | Điều DB có thể phải làm trước hoặc trong phân trang |
|---|---|
| SINGLE_TABLE | Dùng index chung theo order/time, lọc/sort trên một bảng; chi phí hydrate full entity vẫn tùy bề rộng |
| JOINED | Xác định/đọc subclass phù hợp, có thể nối nhiều bảng cho các hàng trong trang, tùy SQL/fetch plan |
| TABLE_PER_CLASS | Đọc dữ liệu từ nhiều bảng rồi hợp nhất/sort ở cấp UNION để chọn trang toàn hierarchy |

**COUNT query** đi kèm Page có thể là chi phí riêng. Trong TABLE_PER_CLASS, đếm tất cả payment có thể cần tổng hợp từ nhiều bảng concrete. Trong JOINED, nếu điều kiện chỉ dùng field root và schema bảo đảm một row root cho mỗi entity, count có thể chỉ cần root; đừng đồng nhất count với SQL full-entity.

Nếu giao diện chỉ cần biết “còn trang sau không”, **Slice** có thể tránh count query của Page. Nếu cần phân trang sâu trên dữ liệu lớn, cân nhắc **keyset pagination** theo (occurredAt, id), nhưng với TABLE_PER_CLASS vẫn cần điều phối dữ liệu nhiều bảng; phải kiểm tra tính đúng và kế hoạch SQL ở dialect thực tế.

### 10.2. FETCH JOIN collection làm vấn đề nặng thêm

Giả sử Payment còn có danh sách PaymentEvent:

~~~java
@OneToMany(mappedBy = "payment", fetch = FetchType.LAZY)
private List<PaymentEvent> events = new ArrayList<>();
~~~

Nếu dùng:

~~~java
select distinct p from Payment p
left join fetch p.events
order by p.occurredAt desc
~~~

mỗi Payment có nhiều Event, số hàng SQL có thể **nhân lên** theo số event. Kết hợp collection JOIN FETCH với Pageable có thể buộc Hibernate phân trang trong bộ nhớ hoặc cảnh báo/từ chối tùy cấu hình. Khi hierarchy đã có nhiều JOIN hoặc UNION, việc fetch collection có thể làm SQL còn nặng hơn.

Một chiến lược an toàn hơn cho danh sách:

1. Truy vấn trang ID hoặc DTO payment cần hiển thị, không fetch collection.
2. Nếu cần event của các ID thuộc trang, truy vấn riêng theo tập ID.
3. Gắn kết quả theo ID trong service rồi trả DTO, giữ đúng thứ tự trang.

Với màn hình chi tiết **một Payment**, fetch association có thể phù hợp hơn vì không phải phân trang nhiều entity cha.

## 11. Quan hệ LAZY trỏ đến entity cha: chi phí khó nhìn thấy

Không phải chỉ query **from Payment** mới phải trả giá cho hierarchy. Một entity khác có thể tham chiếu:

~~~java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "payment_id", nullable = false)
private Payment payment;
~~~

Khi truy cập **invoice.getPayment()**, Hibernate có thể tạo proxy của Payment chưa được nạp. Nếu sau đó cần một field của subclass, proxy được khởi tạo và Hibernate phải tìm đúng concrete type. Với JOINED có thể cần nhiều JOIN; với TABLE_PER_CLASS có thể cần polymorphic lookup/UNION hoặc chiến lược xác định subtype phù hợp. Cơ chế thực tế phụ thuộc provider, bytecode enhancement và mapping.

Trong vòng lặp:

~~~java
for (Invoice invoice : invoices) {
    System.out.println(invoice.getPayment().getAmount());
}
~~~

còn có nguy cơ **N+1**: một query lấy invoices rồi nhiều query riêng lấy Payment. Khi Payment là root của hierarchy rộng, **mỗi query bổ sung** có thể là một SELECT đắt. Đừng chỉ đếm số subclass mà bỏ qua số lần truy cập đến hierarchy.

Biện pháp:

- DTO projection hoặc JOIN hợp lý nếu dữ liệu root cần thiết trong danh sách.
- Batch fetching theo mapping/use case để giảm số lần round-trip khi lazy reference được truy cập nhiều lần.
- Truy vấn theo ID/thao tác đơn lẻ nếu use case không cần toàn bộ graph.
- Tránh đánh dấu mọi quan hệ thành EAGER: nó có thể làm các query khác tải thừa dữ liệu.

**Hibernate cache cấp 1** giúp dùng lại entity managed trong cùng persistence context. Cache cấp 2 nếu được cấu hình có thể giảm một số lần truy cập DB, nhưng không làm chi phí của những polymorphic query chưa được cache biến mất. Không coi cache là cách sửa một schema/mapping không phù hợp.

## 12. Hiểu chi phí của truy vấn COUNT, aggregate và filter

### 12.1. Đếm tất cả Payment

~~~java
select count(p) from Payment p
where p.orderId = :orderId
~~~

SINGLE_TABLE thường có thể dùng một bảng và index phù hợp. JOINED có một bảng root chứa tất cả row Payment nên truy vấn count chỉ dựa vào root fields có thể rất nhẹ. TABLE_PER_CLASS có thể cần tính trên nhiều concrete tables, dù SQL được tối ưu bằng aggregate trên từng nhánh.

### 12.2. Tính tổng tiền

~~~java
select sum(p.amount) from Payment p
where p.occurredAt >= :fromTime
  and p.occurredAt < :toTime
~~~

Tương tự, aggregate trên root fields không đòi materialize full Java entity. Nên để database tính tổng thay vì tải hàng nghìn Payment về rồi cộng trong memory. Với TABLE_PER_CLASS, tổng vẫn có thể cần đọc dữ liệu ở mọi concrete table; từng nhánh cần index theo bộ lọc nếu workload có lợi.

### 12.3. Filter theo subtype làm thay đổi plan

Ví dụ report chỉ thanh toán điện tử:

~~~java
select sum(p.amount) from DigitalPayment p
where p.occurredAt >= :fromTime
  and p.occurredAt < :toTime
~~~

Với SINGLE_TABLE có thể lọc các discriminator thuộc nhánh digital. JOINED có thể cần bảng DigitalPayment để xác định membership của nhánh. TABLE_PER_CLASS thường hợp nhất những concrete table là con của DigitalPayment (CardPayment và WalletPayment), ít hơn tổng tất cả loại Payment nếu Hibernate cắt đúng phạm vi polymorphism.

Điểm cần học là **kiểu entity trong FROM clause ảnh hưởng phạm vi polymorphic query**. Không nên luôn bắt đầu từ lớp cha sâu nhất nếu use case chỉ dùng một nhóm con.

### 12.4. Nhãn loại trong DTO

Một query chỉ lấy TYPE hoặc discriminator để hiển thị tên kiểu có thể hữu ích, nhưng đừng để UI phụ thuộc trực tiếp tên Java class. Nếu cần API ổn định, có thể tạo một giá trị **paymentKind** nghiệp vụ rõ nghĩa được định nghĩa trong domain/DTO; tránh ràng buộc client vào chi tiết ánh xạ inheritance.

## 13. Chỉ mục: từ join/union tới khả năng lọc sớm

Số subtype không quyết định mọi thứ. Một index tốt có thể làm query nhiều bảng nhanh hơn query một bảng quét toàn bộ dữ liệu.

### 13.1. SINGLE_TABLE

Nếu màn hình thường lấy payment theo order, sắp xếp mới nhất:

~~~sql
CREATE INDEX idx_payments_order_time
ON payments(order_id, occurred_at DESC, id DESC);
~~~

Nếu thường truy vấn CardPayment:

~~~sql
CREATE INDEX idx_card_payments_order_time
ON payments(order_id, occurred_at DESC, id DESC)
WHERE payment_type = 'CARD';
~~~

Đây là **partial index PostgreSQL**. Chỉ mục có điều kiện phù hợp khi subtype có pattern truy cập rõ và đủ chọn lọc. Với hàng chục subtype, không nhất thiết tạo hàng chục index mà không có số liệu.

### 13.2. JOINED

Các bảng subclass thường có PK cùng ID với bảng cha và FK reference. Join theo khóa chính có thể dùng index PK. Nhưng nếu WHERE lọc field riêng của CardPayment, index ở bảng card (ví dụ cardLast4) có thể giúp; planner vẫn phải join bảng cha để lấy orderId/time hoặc các field chung.

### 13.3. TABLE_PER_CLASS

Mỗi concrete table có thể cần index riêng theo **(order_id, occurred_at, id)**. Khi root query UNION cả 20 bảng, thiết kế index chung không tồn tại ở một chỗ. Thêm kiểu mới đòi hỏi xem xét index và maintenance cho bảng mới.

### 13.4. Kế hoạch thực thi quan trọng hơn số JOIN

Một query gồm 5 JOIN theo PK trên vài trăm hàng có thể rất nhanh; một query một bảng nhưng quét hàng triệu hàng và sort ra disk có thể rất chậm. Đừng tối ưu bằng cách đếm JOIN như một luật cứng. Hãy đo **actual rows**, **loops**, **buffers**, **sort method**, **temp reads/writes** và thời gian thực thi trong execution plan.

## 14. Chọn chiến lược trên dữ liệu lệch phân bố

Giả sử 98% thanh toán là CardPayment, 1% WalletPayment, phần còn lại là Cash/BankTransfer.

- SINGLE_TABLE chứa chủ yếu hàng CARD; index theo subtype hoặc order có thể phục vụ rất tốt luồng chính. Nhưng các field hiếm từ subtype khác vẫn nằm trên schema bảng chung.
- JOINED có nhiều hàng trong bảng card và ít ở các bảng khác. Query CardPayment chỉ join root/digital/card; query root có thể vẫn chứa join cho những nhánh rất ít dữ liệu.
- TABLE_PER_CLASS có bảng card rất lớn, các bảng còn lại nhỏ. Query card trực tiếp có thể đơn giản; query “tất cả thanh toán” phải hợp nhất các bảng, nhưng chi phí có thể tập trung vào bảng card.

Một thử nghiệm phân bố **đều 25% mỗi subtype** có thể dẫn tới kết luận khác với production nơi một subtype chiếm 98%. Khi benchmark, phải mô phỏng phân bố thực tế và sự tăng trưởng trong tương lai.

Đặc biệt, kích thước theo **byte**, không chỉ số row, ảnh hưởng tới IO và network. Một bảng single-table có một cột JSON lớn cho một subtype có thể rất khác bảng chứa vài chuỗi nhỏ, ngay cả khi số cột là như nhau.

## 15. Chi phí ghi dữ liệu và thay đổi schema

Bài học tập trung vào query, nhưng lựa chọn strategy còn tác động đến ghi và việc triển khai:

| Hoạt động | SINGLE_TABLE | JOINED | TABLE_PER_CLASS |
|---|---|---|---|
| Insert CardPayment | Ghi một hàng payments | Ghi payments, digital_payments, card_payments | Ghi card_payments |
| Update field chung amount | UPDATE một hàng payments | UPDATE ở bảng root | UPDATE ở bảng concrete tương ứng |
| Update field cardLast4 | UPDATE một hàng payments | UPDATE bảng card_payments | UPDATE bảng card_payments |
| Delete concrete entity | Một bảng | Nhiều bảng dọc cây | Một bảng concrete |
| Thêm field vào Payment | ALTER một bảng | ALTER bảng root | Có thể ALTER mọi bảng concrete |
| Thêm subtype | Thêm cột/discriminator/constraint trong bảng chung | Thêm bảng subclass, liên kết PK/FK | Thêm bảng concrete với các cột chung |
| Di chuyển field từ cha xuống con | Có thể phải migrate dữ liệu theo discriminator | Di chuyển cột/bảng và migration FK | Điều chỉnh nhiều bảng cụ thể |

Với JOINED, một insert có nhiều statement vẫn có thể được Hibernate/JDBC xử lý trong transaction; số statement không tự phản ánh latency nếu batching và DB cache tốt. Với TABLE_PER_CLASS, write một concrete subtype có thể đơn giản nhưng migration field chung khó hơn khi số subclass lớn.

**Đổi chiến lược trên hệ thống đang chạy là migration lớn**, thường phải di chuyển dữ liệu, tái tạo PK/FK/index, kiểm tra ID toàn hierarchy, chuyển code/query và đảm bảo giao dịch diễn ra an toàn. Không đổi chỉ bằng một dòng annotation rồi mong Hibernate tự giữ nguyên dữ liệu production.

## 16. Đo hiệu năng với SQL Hibernate và PostgreSQL

Tối ưu đúng bắt đầu từ **truy vấn thực tế**, không từ hình dạng class diagram.

### 16.1. Bật log trong môi trường phát triển

~~~yaml
spring:
  jpa:
    open-in-view: false
    show-sql: false
    properties:
      hibernate:
        format_sql: true
        generate_statistics: true

logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
~~~

- **org.hibernate.SQL** cho biết cấu trúc SQL: một bảng, nhiều LEFT JOIN hay UNION ALL.
- **org.hibernate.orm.jdbc.bind** ở TRACE trong Hibernate 6 cho biết tham số bind. Nó có thể lộ dữ liệu người dùng nên chỉ bật ngắn hạn ở môi trường phù hợp.
- **generate_statistics** bật thống kê Hibernate; tắt lại khi không cần vì thu thập số liệu có chi phí.

Khi tập trung vào kế thừa, hãy lưu log **cùng một use case** trên ba mapping tương đương. Đảm bảo dữ liệu và điều kiện lọc tương đương để có cơ sở so sánh.

### 16.2. Thống kê từ SessionFactory

~~~java
import jakarta.persistence.EntityManagerFactory;
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;

SessionFactory sessionFactory = emf.unwrap(SessionFactory.class);
Statistics stats = sessionFactory.getStatistics();

long beforeStatements = stats.getPrepareStatementCount();
long beforeLoads = stats.getEntityLoadCount();

// Thực thi use case trong transaction/test cô lập, flush nếu cần.

long statementDelta =
    stats.getPrepareStatementCount() - beforeStatements;
long loadedEntityDelta =
    stats.getEntityLoadCount() - beforeLoads;
~~~

Đoạn trên giả định có **EntityManagerFactory emf** được inject/khởi tạo sẵn. Statistics là bộ đếm **tích lũy toàn SessionFactory**; phép trừ before/after chỉ đại diện một use case nếu test cô lập, không có request khác chạy cùng. **prepareStatementCount không đo trực tiếp số JOIN, số nhánh UNION, số row hay thời gian database**. Hai truy vấn đều chuẩn bị một statement nhưng SQL bên trong có thể khác nhau một trời một vực.

Để đo đúng hơn, kết hợp:

- Thời gian request/service và p50/p95 latency.
- Số prepared statements, entity loads, collection fetches.
- Số row trả về và kích thước dữ liệu.
- Actual execution plan, buffers và thời gian query ở database.
- CPU/memory và tác động của caching, pooling, batching.

### 16.3. Đọc execution plan trong PostgreSQL

Sau khi lấy SQL thực tế và bind parameter, chạy trong môi trường kiểm soát:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT p.id, p.order_id, p.amount, p.occurred_at
FROM payments p
WHERE p.order_id = 1001
ORDER BY p.occurred_at DESC, p.id DESC
LIMIT 20;
~~~

**EXPLAIN ANALYZE thực thi câu SELECT**, nên có chi phí thật; với DML còn có thể gây tác động dữ liệu nếu không kiểm soát transaction. Phần trên là truy vấn đọc. Những chỉ số cần xem:

| Thông tin plan | Ý nghĩa khi so sánh strategy |
|---|---|
| Seq Scan / Index Scan | Có dùng index phù hợp với WHERE và ORDER BY không? |
| Nested Loop / Hash Join / Merge Join | Cách DB kết hợp bảng trong JOINED, số lần lặp và kích thước dữ liệu |
| Append / Merge Append / Set operation | Cách DB xử lý nhánh UNION trong TABLE_PER_CLASS |
| Sort / Incremental Sort | Chi phí ORDER BY sau JOIN/UNION |
| actual rows / loops | Cardinality thực, tác động điều kiện lọc |
| shared hit/read, temp read/write | Dữ liệu lấy từ cache hay phải IO/tạm ghi ra disk |
| Execution Time | Thời gian DB thực thi query trong lần thử đó |

Đừng chỉ đọc **estimated cost** của planner như thời gian mili giây. Đó là thước đo chi phí nội bộ tương đối của PostgreSQL; để đánh giá thời gian thực phải xem actual timings và lặp lại trên điều kiện đại diện.

## 17. Thiết kế thí nghiệm có thể so sánh

Không thể đánh giá “JOINED nhanh hơn SINGLE_TABLE” chỉ bằng một lần chạy vài entity H2. Hãy tạo **ba phiên bản mapping hoặc ba persistence unit/schema riêng** chứa cùng tập payment tương đương. Không ánh xạ ba class khác strategy vào cùng một bảng đang dùng trong một phép thử.

### 17.1. Ma trận dữ liệu

Thay đổi từng trục:

| Biến | Kịch bản nhỏ | Kịch bản vừa | Kịch bản lớn |
|---|---:|---:|---:|
| Số concrete type C | 2 | 8 | 24 |
| Độ sâu tối đa D | 1 | 3 | 5 |
| Tổng bản ghi R | 10.000 | 100.000 | 1.000.000 |
| Phân bố subtype | Đều | Một type 80% | Một type 98% |
| Số cột riêng/type | 2–3 | 8–12 | 20+ |
| Trang danh sách | 20 | 50 | 100 |

Không nhất thiết chạy toàn bộ tổ hợp. Chọn vài lát cắt: **giữ D và R cố định, tăng C**; **giữ C và R cố định, tăng D**; **giữ C/D, tăng R**; cuối cùng kiểm tra phân bố lệch.

### 17.2. Các phép đo

1. **findById** một Payment đã biết subtype.
2. **SELECT root full entity** theo order/time.
3. **SELECT root DTO** chỉ field chung.
4. **SELECT CardPayment** riêng.
5. **COUNT root** và **SUM amount** theo khoảng thời gian.
6. **Page<Payment>** toàn hierarchy, trang đầu và trang sâu.
7. **Slice DTO** thay Page khi không cần total count.
8. **Load một danh sách entity khác tham chiếu Payment LAZY**, đo N+1.

Mỗi phép thử cần dữ liệu fixture, index và giới hạn kết nối tương đương. Làm ấm JVM/DB cache trước, chạy nhiều lần, thống kê độ trễ thay vì dùng một con số ngẫu nhiên. Nếu dùng JMH, cần cẩn trọng vì benchmark ORM có IO, transaction, pool và DB nằm ngoài phạm vi phép đo microbenchmark thông thường; một integration performance test có workload thực tế có thể hữu ích hơn.

### 17.3. Mẫu báo cáo

| Strategy | C | D | Query | SQL shape | Statements | DB time p95 | Rows | Buffers |
|---|---:|---:|---|---|---:|---:|---:|---|
| SINGLE_TABLE | Điền | Điền | Root page | Một bảng | Đo | Đo | Đo | Đo |
| JOINED | Điền | Điền | Root page | LEFT JOIN | Đo | Đo | Đo | Đo |
| TABLE_PER_CLASS | Điền | Điền | Root page | UNION ALL | Đo | Đo | Đo | Đo |
| SINGLE_TABLE | Điền | Điền | Subtype query | Discriminator | Đo | Đo | Đo | Đo |
| JOINED | Điền | Điền | Subtype query | JOIN dọc cây | Đo | Đo | Đo | Đo |
| TABLE_PER_CLASS | Điền | Điền | Subtype query | Concrete table | Đo | Đo | Đo | Đo |

Các ô **Đo** phải được điền bằng số liệu thực sau khi chạy; bài học không giả định một kết quả benchmark cố định. Quan trọng nhất là từ số liệu tìm ra **query nóng** và thành phần chi phí có thể thay đổi bằng thiết kế.

## 18. Một ví dụ đọc kết quả và chọn hướng tối ưu

Giả sử dự án có 18 concrete subtype, query root mỗi request nhưng UI chỉ hiện:

~~~text
Payment ID | Order ID | Amount | Occurred At | Trạng thái
~~~

Nếu đang dùng JOINED, SQL có thể chứa nhiều LEFT JOIN dù UI không hiển thị các field riêng; với TABLE_PER_CLASS có thể có nhiều UNION. Các hướng thay đổi theo mức độ can thiệp:

**Bước 1: Chọn DTO projection.** Không hydrate toàn bộ hierarchy khi chỉ cần field chung. Đo lại SQL, row width và latency; Hibernate có thể bỏ được các JOIN không cần thiết trong JOINED.

**Bước 2: Phân trang đúng.** Chỉ lấy trang nhỏ với ORDER BY ổn định; tránh collection FETCH JOIN trên danh sách; dùng Slice nếu không cần count.

**Bước 3: Index theo điều kiện thật.** Với JOINED/SINGLE_TABLE, đảm bảo có index trên root/order/time và phân tích execution plan; TABLE_PER_CLASS cần cân nhắc index cho từng concrete table.

**Bước 4: Đánh giá lại mô hình.** Nếu 18 subtype chủ yếu khác nhau ở một vài trường/enum và root polymorphic list là use case chính, SINGLE_TABLE hoặc composition có thể hợp hơn. Nếu subtype hoàn toàn độc lập và ít khi query root, giữ TABLE_PER_CLASS có thể hợp lý.

**Bước 5: Migration có kế hoạch.** Nếu đổi inheritance strategy, phải kiểm tra schema, ID, constraint, data backfill, đường ghi mới, deployment và rollback. Không đổi chỉ vì một benchmark nhỏ.

Quan trọng là **tối ưu query trước khi thay đổi mô hình toàn hệ thống**, vì đổi inheritance strategy thường tốn công và có rủi ro dữ liệu lớn.

## 19. Khi nào không nên dùng entity inheritance?

Không phải mọi quan hệ “is-a” trong Java đều phải trở thành kế thừa entity. Hibernate/JPA có hai lựa chọn khác đáng cân nhắc.

### 19.1. @MappedSuperclass: dùng chung field mà không tạo polymorphic entity root

~~~java
import jakarta.persistence.*;
import java.time.Instant;

@MappedSuperclass
public abstract class AuditedRecord {
    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected AuditedRecord() {}

    protected AuditedRecord(Instant createdAt) {
        this.createdAt = createdAt;
    }

    public Instant getCreatedAt() { return createdAt; }
}

@Entity
public class CustomerRecord extends AuditedRecord {
    @Id
    private Long id;

    protected CustomerRecord() {}
}

@Entity
public class ProductRecord extends AuditedRecord {
    @Id
    private Long id;

    protected ProductRecord() {}
}
~~~

Các subclass kế thừa mapping field từ AuditedRecord nhưng **AuditedRecord không phải entity độc lập để truy vấn bằng JPQL**. Không thể làm **select a from AuditedRecord a** như với một @Entity root. Vì thế @MappedSuperclass phù hợp khi mục tiêu chỉ là **tái sử dụng cấu trúc field**, chứ không cần truy vấn đa hình trên một hierarchy.

**Lưu ý:** ví dụ ánh xạ từng subclass vào bảng riêng; schema và ID strategy phải được hoàn thiện theo dự án thật. Nếu hệ thống cần tra cứu chung mọi loại audited record bằng một query, @MappedSuperclass không cung cấp sẵn khả năng ấy.

### 19.2. Composition và bảng chi tiết theo loại

Một phương án khác là entity Payment **không có subclass JPA**, chứa field chung và discriminator nghiệp vụ:

~~~java
@Entity
@Table(name = "payments")
public class Payment {
    @Id
    private Long id;

    @Enumerated(EnumType.STRING)
    private PaymentKind kind;

    private BigDecimal amount;
    private Instant occurredAt;

    // Các field chung và business method.
}
~~~

Dữ liệu chi tiết có thể nằm trong **CardPaymentDetails**, **WalletPaymentDetails**... dưới dạng entity có quan hệ one-to-one hoặc bảng riêng theo nhu cầu. Root query về danh sách Payment chỉ đọc một bảng **nhỏ và ổn định**, còn chi tiết subtype được đọc khi thực sự cần. Đổi lại, ứng dụng phải tự đảm bảo:

- Kind phù hợp với detail record được tạo.
- Một payment không có hai loại detail trái nhau.
- Khi đổi trạng thái, transaction cập nhật phần chung và phần chi tiết nhất quán.
- API/domain service diễn đạt đúng quy tắc riêng của mỗi loại.

Composition không tự động “nhanh hơn inheritance” trong mọi trường hợp: nếu use case luôn đọc mọi detail và phải join hàng loạt, chi phí vẫn tồn tại. Nó giúp **kiểm soát đường truy cập** khi phần lớn use case dùng field chung, và tránh bắt ORM tự materialize polymorphic object graph trên mọi query.

### 19.3. Entity kế thừa sâu có thể là dấu hiệu domain đang gộp nhiều khái niệm

Nếu hierarchy liên tục thêm tầng chỉ để tái sử dụng hai field hoặc một phương thức, cân nhắc tách:

- **Value object** như Money, PaymentReference.
- **Service/strategy interface** để xử lý behavior theo loại.
- **@Embeddable** cho nhóm field thuộc giá trị.
- **@MappedSuperclass** cho field audit chung.
- **Entity liên kết** khi bản thân mối quan hệ có thuộc tính.

Kế thừa sâu là một công cụ, không phải mục tiêu. Giữ class diagram gọn không có nghĩa bỏ polymorphism khi domain thật sự cần nó.

## 20. Quyết định thiết kế theo pattern truy vấn

| Pattern chủ đạo | Lựa chọn đáng đánh giá đầu tiên | Điều phải đo/kiểm tra |
|---|---|---|
| Thường query toàn bộ entity qua root | SINGLE_TABLE hoặc root gọn + detail composition | Bề rộng row, index, hydration, số field riêng |
| Nhiều field đặc thù, query subtype là chủ yếu | JOINED hoặc TABLE_PER_CLASS | JOIN theo depth, index subtype, UNION khi query root |
| Cần NOT NULL/index riêng cho mỗi subtype | JOINED hoặc TABLE_PER_CLASS | Chi phí JOIN/UNION so với constraint rõ ràng |
| Root list chỉ cần vài field chung | Projection DTO trên strategy hiện có | SQL thực tế có bỏ JOIN/chọn ít cột không |
| Có nhiều concrete type và root Page thường xuyên | SINGLE_TABLE, composition hoặc read model riêng | Count/sort/pagination trên JOIN hoặc UNION |
| Chỉ cần dùng chung field, không query đa hình | @MappedSuperclass | Không có JPQL root polymorphic |
| Cây ngày càng sâu, nhiều tầng chỉ vì code reuse | Giảm kế thừa, composition | Migration và hợp đồng nghiệp vụ |

**Quy trình chọn thực tế:** liệt kê các truy vấn hot → xác định root/subtype và field cần lấy → ước lượng sự phát triển của C/D/R/W → tạo schema/mapping thử nghiệm → xem SQL và execution plan → quyết định theo dữ liệu đo được.

## 21. Các lỗi suy luận phổ biến

| Nhận định hoặc triệu chứng | Vì sao chưa đúng | Hướng xử lý |
|---|---|---|
| “Chỉ một SQL nên chắc chắn nhanh.” | Một SQL có thể JOIN 20 bảng hoặc UNION 30 nhánh. | Xem SQL shape, plan, row và buffers. |
| “JOINED luôn chậm vì có JOIN.” | JOIN theo PK với ít hàng và index phù hợp có thể rất nhanh. | Đo actual timing và IO. |
| “SINGLE_TABLE luôn nhanh nhất.” | Bảng có thể rất rộng, query full entity tải nhiều cột không cần. | Dùng projection, cân nhắc width/index/constraints. |
| “TABLE_PER_CLASS rất nhanh vì mỗi bảng nhỏ.” | Root query có thể UNION tất cả bảng và sort kết quả chung. | Đo root list, count và paging. |
| “Thêm một subclass không ảnh hưởng query cũ.” | Root polymorphic query có thể rộng hơn/JOINS thêm/UNION thêm. | Kiểm tra SQL sau khi tăng C. |
| “Độ sâu chỉ là thiết kế Java, không tác động SQL.” | JOINED có thể nối qua mọi tầng của subtype sâu. | Đo leaf query theo D. |
| “@ManyToOne LAZY không liên quan inheritance.” | Khi lazy base reference khởi tạo, Hibernate cần xác định và load subclass. | Kiểm tra SQL lazy và N+1. |
| “DTO luôn bỏ hết JOIN/UNION.” | Root TABLE_PER_CLASS vẫn có thể cần UNION; query field subclass vẫn cần truy cập đúng bảng. | Đọc generated SQL của projection. |
| “LIMIT 20 nghĩa là DB chỉ đọc 20 hàng.” | Sort/UNION/joins có thể phải xử lý nhiều hàng trước LIMIT. | Xem actual rows, sort và buffers. |
| “Benchmark H2 sẽ giống PostgreSQL.” | Planner, index, dialect, query execution khác nhau. | Dùng DB mục tiêu hoặc Testcontainers. |
| “Thêm index cho mọi cột subtype là tốt.” | Index tăng chi phí ghi, dung lượng và maintenance. | Chọn index theo workload/plan. |
| “Chỉ đổi @Inheritance là xong migration.” | Cần tái cấu trúc bảng, ID, FK, dữ liệu và query. | Lập migration từng bước và xác minh. |

## 22. Bài tập thực hành với nhiều kiểu con và nhiều tầng

### Bài 1 — Quan sát hình dạng SQL

Tạo Payment với CardPayment, WalletPayment, BankTransferPayment và CashPayment theo SINGLE_TABLE. Insert dữ liệu thử tương đương cho cả bốn loại; chạy:

~~~java
select p from Payment p
select p from CardPayment p
select p.id, p.amount from Payment p
select count(p) from Payment p
~~~

Ghi lại các cột được SELECT, cách lọc discriminator và số statement.

### Bài 2 — Đổi sang JOINED trong schema thí nghiệm riêng

Tạo cùng số lượng bản ghi theo JOINED, đảm bảo các field chung ở root và field riêng trong bảng subtype. Chạy lại bốn query. Thêm một tầng concrete subtype mới bên dưới CardPayment, quan sát số JOIN của query leaf và root. Dùng EXPLAIN ANALYZE trên SQL do Hibernate sinh ra.

### Bài 3 — Đổi sang TABLE_PER_CLASS

Tạo schema mới với mỗi concrete subtype một bảng, dùng shared sequence và field tương đương. Chạy root query, subtype query, count và Page 20 bản ghi. Tăng số concrete type lên 12 hoặc 24 trong phép thử có kiểm soát; ghi số nhánh UNION và sự khác nhau ở plan.

### Bài 4 — Chỉ lấy field cần thiết

Trên cả ba chiến lược, so sánh:

~~~java
select p from Payment p
~~~

với:

~~~java
select new com.example.shop.payment.PaymentListRow(
    p.id, p.orderId, p.amount, p.occurredAt
)
from Payment p
~~~

Giải thích chiến lược nào giảm được JOIN, chiến lược nào vẫn cần UNION, và việc giảm số field có ảnh hưởng thế nào tới bytes truyền/hydration.

### Bài 5 — Gắn lazy reference và kiểm tra N+1

Thêm Invoice trỏ đến Payment, tạo 100 invoices ứng với nhiều payment type; tải danh sách invoice rồi đọc Payment.amount trong vòng lặp. Đếm statement và xem SQL. Sau đó thử projection hoặc batch fetch phù hợp; so sánh lại bằng dữ liệu đo được.

### Bài 6 — Viết kết luận có bằng chứng

Đánh giá một workload giả định:

- **80% request:** trang 20 Payment chỉ cần amount/occurredAt.
- **15% request:** xem chi tiết một CardPayment.
- **5% request:** báo cáo SUM amount theo tháng trên tất cả payment.
- Cây sẽ tăng từ 4 lên 16 subtype; độ sâu từ 2 lên 4.

Trình bày chiến lược bạn chọn, SQL shape ở ba use case, index dự kiến, rủi ro khi C/D tăng, và kết quả benchmark nào có thể khiến bạn đổi quyết định. Không có một đáp án duy nhất nếu chưa biết số lượng bản ghi và phân bố dữ liệu.

## 23. Nguyên tắc ghi nhớ

Khi số lớp con hoặc độ sâu tăng, chi phí truy vấn ORM phải được phân tích theo **hình dạng vật lý của dữ liệu**:

1. **SINGLE_TABLE:** đa hình trên một bảng, không trả giá thêm JOIN/UNION theo độ sâu, nhưng bảng có thể rộng khi số kiểu con và field riêng tăng.
2. **JOINED:** dữ liệu chuẩn hóa qua nhiều bảng; leaf query có thể nối theo độ sâu, root polymorphic full-entity query có thể nối tới nhiều nhánh subclass.
3. **TABLE_PER_CLASS:** leaf query thường đơn giản trên một bảng concrete, nhưng root polymorphic query phải hợp nhất nhiều bảng, thường qua UNION ALL; số concrete subtype làm query tổng hợp phức tạp hơn.
4. **Loại query quyết định chi phí:** đọc root entity đầy đủ, lọc subtype, chỉ lấy DTO, COUNT, aggregate, paging hoặc nạp lazy reference là những bài toán khác nhau.
5. **Không tối ưu theo số annotation:** xem SQL Hibernate sinh, dữ liệu thật, index, execution plan, time và memory. Một query với ít câu SQL chưa chắc rẻ.
6. **Thiết kế lại khi nhu cầu thay đổi:** @MappedSuperclass hoặc composition có thể phù hợp hơn entity inheritance nếu mục tiêu chỉ là reuse field hoặc phần lớn màn hình chỉ cần dữ liệu chung.

Thiết kế kế thừa tốt trong Hibernate là thiết kế mà **số loại cụ thể và chiều sâu có thể phát triển mà những truy vấn quan trọng vẫn có chi phí được hiểu và kiểm soát**. Điều đó cần bắt đầu từ use case, theo dõi SQL đa hình và đo trên cơ sở dữ liệu triển khai, thay vì suy đoán hiệu năng từ sơ đồ class Java.
