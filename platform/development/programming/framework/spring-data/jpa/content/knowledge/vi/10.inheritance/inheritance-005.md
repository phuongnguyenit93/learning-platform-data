# Chiến lược TABLE_PER_CLASS và truy vấn đa hình

JPA hỗ trợ ba chiến lược ánh xạ kế thừa entity: **SINGLE_TABLE**, **JOINED** và **TABLE_PER_CLASS**. Với TABLE_PER_CLASS, mỗi entity class cụ thể trong hierarchy có một bảng riêng. Các thuộc tính kế thừa từ superclass được lặp lại trong bảng của từng subclass.

Điểm mạnh của chiến lược này là đọc một subclass cụ thể không cần join với bảng cha. Đổi lại, truy vấn trên kiểu cha phải tổng hợp dữ liệu từ nhiều bảng, thường bằng UNION hoặc một câu SQL đa hình tương đương. Vì vậy, TABLE_PER_CLASS cần được chọn dựa trên hình dạng truy vấn, tính toàn vẹn dữ liệu và khả năng của database, không chỉ dựa trên việc muốn tách mỗi loại thành một bảng.

Bài này sử dụng mô hình Payment gồm CardPayment và BankTransferPayment để giải thích mapping, truy vấn đa hình và các giới hạn thực tế trong Spring Data JPA với Hibernate.

## 1. Ba chiến lược kế thừa của JPA

Một hierarchy entity có superclass và các subclass. JPA cần biết dữ liệu của chúng được lưu thành bảng như thế nào.

| Chiến lược | Cách lưu | Đặc điểm |
|---|---|---|
| SINGLE_TABLE | Toàn bộ hierarchy nằm trong một bảng, phân biệt bằng discriminator | Đọc đa hình đơn giản, ít join; cột riêng của từng subclass thường phải cho phép NULL |
| JOINED | Bảng cha lưu thuộc tính chung, mỗi subclass có bảng riêng nối bằng PK/FK | Schema chuẩn hóa hơn; đọc subclass thường cần join |
| TABLE_PER_CLASS | Mỗi lớp cụ thể có bảng riêng, mỗi bảng chứa cả thuộc tính kế thừa | Đọc một subclass không cần join; truy vấn kiểu cha cần hợp nhất nhiều bảng |

Ví dụ hierarchy:

```text
                  Payment (abstract)
                       |
              +--------+--------+
              |                 |
         CardPayment      BankTransferPayment
```

Với TABLE_PER_CLASS, schema có thể là:

```text
card_payments
+----+------------+---------------+----------------+
| id | created_at | amount        | card_last_four |
+----+------------+---------------+----------------+

bank_transfer_payments
+----+------------+---------------+----------------+
| id | created_at | amount        | bank_reference |
+----+------------+---------------+----------------+
```

Hai bảng đều chứa id, created_at và amount vì đó là các thuộc tính được kế thừa từ Payment. Mỗi bảng còn chứa thuộc tính riêng của subclass.

## 2. Khai báo TABLE_PER_CLASS

Chiến lược được đặt trên root entity bằng @Inheritance:

```java
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;

@Entity
@Inheritance(strategy = InheritanceType.TABLE_PER_CLASS)
@SequenceGenerator(
    name = "payment_id_generator",
    sequenceName = "payment_id_seq",
    allocationSize = 50
)
public abstract class Payment {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "payment_id_generator"
    )
    private Long id;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal amount;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected Payment() {
    }

    protected Payment(BigDecimal amount, Instant createdAt) {
        this.amount = amount;
        this.createdAt = createdAt;
    }

    public Long getId() {
        return id;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
```

Root entity phải được đánh dấu @Entity để tham gia hierarchy và hỗ trợ truy vấn đa hình. Root có thể là abstract class để không tạo instance Payment trực tiếp.

Subclass thứ nhất:

```java
@Entity
@Table(name = "card_payments")
public class CardPayment extends Payment {

    @Column(name = "card_last_four", nullable = false, length = 4)
    private String cardLastFour;

    protected CardPayment() {
    }

    public CardPayment(
            BigDecimal amount,
            Instant createdAt,
            String cardLastFour
    ) {
        super(amount, createdAt);
        this.cardLastFour = cardLastFour;
    }

    public String getCardLastFour() {
        return cardLastFour;
    }
}
```

Subclass thứ hai:

```java
@Entity
@Table(name = "bank_transfer_payments")
public class BankTransferPayment extends Payment {

    @Column(name = "bank_reference", nullable = false, length = 80)
    private String bankReference;

    protected BankTransferPayment() {
    }

    public BankTransferPayment(
            BigDecimal amount,
            Instant createdAt,
            String bankReference
    ) {
        super(amount, createdAt);
        this.bankReference = bankReference;
    }

    public String getBankReference() {
        return bankReference;
    }
}
```

Các điểm cần lưu ý:

- @Inheritance(strategy = InheritanceType.TABLE_PER_CLASS) khai báo chiến lược trên root entity.
- Mỗi subclass cụ thể có @Entity và có thể dùng @Table để chỉ định tên bảng riêng.
- Các thuộc tính id, amount và createdAt được kế thừa và ánh xạ vào từng bảng con.
- Không cần tạo một bảng payment chỉ để chứa thuộc tính chung trong chiến lược này.
- Không cần discriminator column như cách thường dùng với SINGLE_TABLE; provider có thể xác định kiểu cụ thể dựa trên bảng nguồn trong truy vấn đa hình.
- Root entity vẫn là một entity JPA, dù là abstract class. Có thể truy vấn root để nhận các instance thuộc subclass.

## 3. Vì sao ID phải duy nhất trên toàn hierarchy?

Truy vấn đa hình trên Payment có thể trả về CardPayment và BankTransferPayment trong cùng một kết quả. Do đó, identity của entity phải phân biệt được các bản ghi trong toàn bộ hierarchy.

Nếu card_payments có id = 100 và bank_transfer_payments cũng có id = 100, một kết quả đa hình có thể chứa hai entity khác loại nhưng cùng ID. Điều này gây vấn đề cho identity map/persistence context và các thao tác quản lý entity.

Vì vậy, ID phải duy nhất trên toàn hierarchy, không chỉ duy nhất trong từng bảng. Dùng chung một sequence generator trên root là cách phù hợp với database hỗ trợ sequence:

```sql
CREATE SEQUENCE payment_id_seq
    START WITH 1
    INCREMENT BY 50;
```

DDL trên minh họa trường hợp Hibernate dùng pooled allocation size 50. Increment thực tế phải tương thích với optimizer và cấu hình Hibernate đang dùng; nếu dùng allocationSize = 1 thì sequence thường có increment 1. Kiểm tra migration và schema validation theo đúng provider/phiên bản.

**Không nên dùng IDENTITY cho TABLE_PER_CLASS với Hibernate.** IDENTITY cấp ID độc lập từ từng bảng; Hibernate cần một không gian ID duy nhất cho hierarchy đa hình và không hỗ trợ cách sinh identity này trong union-subclass mapping. Hãy ưu tiên SEQUENCE trên database hỗ trợ sequence, hoặc TABLE generator khi có lý do tương thích cụ thể. Luôn kiểm tra hỗ trợ của provider và database.

## 4. Schema của từng bảng con

Ví dụ DDL rút gọn trên PostgreSQL:

```sql
CREATE TABLE card_payments (
    id BIGINT PRIMARY KEY,
    amount NUMERIC(19, 2) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    card_last_four VARCHAR(4) NOT NULL
);

CREATE TABLE bank_transfer_payments (
    id BIGINT PRIMARY KEY,
    amount NUMERIC(19, 2) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    bank_reference VARCHAR(80) NOT NULL
);

CREATE SEQUENCE payment_id_seq
    START WITH 1
    INCREMENT BY 50;
```

Mỗi bảng có primary key riêng, nhưng giá trị ID được cấp từ cùng một sequence. Các thuộc tính chung xuất hiện lặp lại trong cả hai bảng. Migration phải tạo sequence và các bảng phù hợp với cấu hình provider.

Nếu dùng Flyway hoặc Liquibase, hãy để migration là nguồn sự thật của schema. @Table, @Column và @SequenceGenerator mô tả mapping; chúng không tự bảo đảm production đã có đúng cấu trúc khi ứng dụng chạy với ddl-auto=validate.

## 5. Truy vấn đa hình qua superclass

Một lợi ích quan trọng của TABLE_PER_CLASS là có thể truy vấn root entity để lấy mọi loại payment:

```java
List<Payment> payments = entityManager
    .createQuery(
        "select p from Payment p order by p.createdAt desc",
        Payment.class
    )
    .getResultList();
```

Dù Payment là abstract class, JPQL vẫn có thể truy vấn Payment. Provider tìm dữ liệu trong các bảng concrete subclass và tạo đúng kiểu Java cho từng kết quả.

Với Hibernate, truy vấn này thường được triển khai bằng một derived table kết hợp các bảng subclass qua UNION/UNION ALL hoặc SQL đa hình tương đương. SQL chính xác phụ thuộc Hibernate version, dialect, mapping và query. Các cột không tồn tại ở một subclass có thể được biểu diễn bằng giá trị NULL trong phần select tương ứng.

Kết quả có thể chứa:

- CardPayment cho các dòng lấy từ card_payments.
- BankTransferPayment cho các dòng lấy từ bank_transfer_payments.

Code có thể kiểm tra kiểu thực tế:

```java
for (Payment payment : payments) {
    if (payment instanceof CardPayment card) {
        System.out.println(card.getCardLastFour());
    } else if (payment instanceof BankTransferPayment transfer) {
        System.out.println(transfer.getBankReference());
    }
}
```

Không cần tự query từng bảng rồi ghép danh sách bằng Java nếu yêu cầu nghiệp vụ thực sự là truy vấn đa hình. Hãy để JPA quản lý hierarchy và identity.

## 6. Spring Data repository cho root và subclass

Có thể tạo repository cho root để đọc đa hình:

```java
public interface PaymentRepository
        extends JpaRepository<Payment, Long> {
}
```

Gọi:

```java
List<Payment> payments = paymentRepository.findAll();
```

sẽ truy vấn các entity concrete trong hierarchy. Vì Payment là abstract, không thể tạo một Payment trực tiếp bằng new Payment(); việc lưu phải sử dụng instance của subclass.

Có thể tạo repository riêng cho từng loại:

```java
public interface CardPaymentRepository
        extends JpaRepository<CardPayment, Long> {
}

public interface BankTransferPaymentRepository
        extends JpaRepository<BankTransferPayment, Long> {
}
```

Repository subclass thường phù hợp với thao tác tạo và truy vấn chuyên biệt. Root repository phù hợp với use case đọc hoặc xử lý mọi loại Payment.

Một repository method trên root có thể lọc thuộc tính chung:

```java
List<Payment> findByAmountGreaterThan(BigDecimal amount);
```

Method dùng property amount được khai báo ở root entity. Provider vẫn phải tìm các bản ghi phù hợp trong hierarchy.

## 7. Dùng TYPE để lọc subclass

JPQL có toán tử TYPE để kiểm tra kiểu entity thực tế:

```java
@Query("""
    select p
    from Payment p
    where type(p) = CardPayment
    order by p.createdAt desc
    """)
List<Payment> findCardPayments();
```

Entity type literal CardPayment tham chiếu entity name của subclass, không phải table name card_payments. Có thể truyền entity class làm tham số trong các truy vấn phù hợp:

```java
TypedQuery<Payment> query = entityManager.createQuery("""
    select p
    from Payment p
    where type(p) = :paymentType
    """, Payment.class);

query.setParameter("paymentType", CardPayment.class);
```

TYPE hữu ích khi repository hoặc service làm việc với root nhưng cần lọc một subtype cụ thể. Nếu use case chỉ thao tác CardPayment, repository CardPaymentRepository thường dễ đọc và có thể tránh truy vấn đa hình toàn bộ hierarchy.

## 8. Dùng TREAT để truy cập thuộc tính riêng của subclass

Root Payment không có cardLastFour. Nếu JPQL cần lọc theo thuộc tính chỉ có ở CardPayment, có thể dùng TREAT để downcast:

```java
@Query("""
    select p
    from Payment p
    where treat(p as CardPayment).cardLastFour = :lastFour
    """)
List<Payment> findByCardLastFour(
    @Param("lastFour") String lastFour
);
```

TREAT cho phép biểu đạt điều kiện trên subtype trong truy vấn đa hình. Cú pháp và khả năng hỗ trợ một số dạng downcast phụ thuộc JPA provider và phiên bản. Với truy vấn chuyên biệt chỉ dành cho CardPayment, query trực tiếp từ CardPayment thường đơn giản hơn:

```java
List<CardPayment> findByCardLastFour(String lastFour);
```

Không dùng tên table hoặc column trong TREAT; vẫn dùng entity type và property Java.

## 9. Quan hệ giữa TABLE_PER_CLASS và khóa ngoại

TABLE_PER_CLASS có một giới hạn quan trọng về toàn vẹn tham chiếu trong database.

Giả sử một bảng invoice muốn tham chiếu tới Payment bất kỳ. Payment có thể nằm ở card_payments hoặc bank_transfer_payments. Database thông thường chỉ cho phép một foreign key tham chiếu tới một bảng cụ thể; nó không thể tạo một FK duy nhất trỏ tới "một trong nhiều bảng subclass".

Hibernate có thể hỗ trợ một số polymorphic association bằng cơ chế truy vấn đa hình, nhưng database không thể bảo đảm một FK vật lý thông thường tới union của các bảng. Điều này làm giảm khả năng bảo vệ tham chiếu ở tầng database.

Nếu cần quan hệ tới một loại cụ thể, ví dụ invoice luôn tham chiếu CardPayment, có thể tạo FK tới card_payments. Nếu cần tham chiếu bất kỳ Payment nào và muốn FK database rõ ràng, cân nhắc JOINED hoặc SINGLE_TABLE để có một bảng gốc chung.

Đây là một trade-off kiến trúc quan trọng, không chỉ là chi tiết mapping.

## 10. Unique constraint và index trên toàn hierarchy

Mỗi bảng con có thể có unique constraint riêng, nhưng không thể dùng hai unique constraint độc lập để bảo đảm một giá trị duy nhất trên toàn hierarchy.

Ví dụ, nếu cả CardPayment và BankTransferPayment đều có externalReference, khai báo UNIQUE trên từng bảng chỉ bảo đảm không trùng trong từng bảng. Cùng một externalReference vẫn có thể xuất hiện một lần ở mỗi bảng.

Tương tự, index trên từng bảng hỗ trợ truy vấn trong bảng đó, nhưng truy vấn đa hình vẫn phải hợp nhất kết quả. Provider có thể dùng index của từng nhánh, song chi phí UNION và sort/count vẫn tồn tại.

Nếu nghiệp vụ yêu cầu uniqueness toàn hierarchy, có thể:

- Dùng một bảng registry/common table lưu externalReference duy nhất và liên kết tới bản ghi cụ thể.
- Chuyển sang SINGLE_TABLE hoặc JOINED để có bảng gốc chứa khóa/thuộc tính chung.
- Thiết kế một cơ chế cấp/đăng ký mã tập trung có transaction và constraint phù hợp.

Không dựa vào kiểm tra Java kiểu "đã tồn tại chưa rồi mới insert" nếu nhiều transaction có thể chạy đồng thời; cần constraint hoặc cơ chế khóa ở database.

## 11. Hiệu năng của truy vấn đa hình

Truy vấn trực tiếp một subclass thường chỉ cần bảng tương ứng:

```java
List<CardPayment> cards = cardPaymentRepository.findAll();
```

Truy vấn root có thể cần hợp nhất nhiều bảng:

```java
List<Payment> all = paymentRepository.findAll();
```

Khi hierarchy có nhiều subclass, query đa hình phức tạp hơn vì provider phải:

1. Đọc các nhánh bảng concrete.
2. Chuẩn hóa số lượng và kiểu cột trong mỗi nhánh.
3. Hợp nhất kết quả.
4. Áp dụng điều kiện, sort, pagination hoặc count trên kết quả hợp nhất.

Điều này có thể ảnh hưởng rõ tới danh sách lớn và truy vấn báo cáo. TABLE_PER_CLASS thường phù hợp khi truy vấn theo subtype là chủ đạo, thuộc tính chung ít thay đổi và không cần nhiều association đa hình.

Khi truy vấn root thường xuyên, cần đo SQL thực tế. Index phải được tạo trên từng bảng concrete cho các thuộc tính lọc/sắp xếp quan trọng. Pagination trên union cũng có thể tốn kém, nhất là khi cần count toàn bộ hierarchy.

## 12. So sánh với SINGLE_TABLE và JOINED

| Tiêu chí | SINGLE_TABLE | JOINED | TABLE_PER_CLASS |
|---|---|---|---|
| Bảng lưu thuộc tính chung | Một bảng | Bảng root | Lặp lại ở mỗi bảng concrete |
| Bảng riêng cho subtype | Không | Có | Có |
| Discriminator | Thường cần | Có thể dùng theo mapping | Không cần để phân biệt bảng nguồn |
| Đọc một subtype | Không cần join | Thường cần join | Không cần join |
| Đọc toàn bộ hierarchy | Một bảng | Join root và subtype | Hợp nhất nhiều bảng |
| FK tới root entity | Có bảng root | Có bảng root | Khó có FK vật lý chung |
| Unique constraint chung toàn hierarchy | Có thể đặt trên bảng chung | Có thể đặt trên bảng root | Không thể chỉ dùng unique riêng từng bảng |
| Dư thừa thuộc tính chung | Không | Không | Có |
| Độ phức tạp query đa hình | Thấp | Trung bình | Có thể cao khi nhiều subtype |

Không chọn TABLE_PER_CLASS chỉ vì muốn "mỗi class một bảng". Nếu dữ liệu có nhiều quan hệ tới superclass, cần uniqueness toàn hierarchy hoặc truy vấn root thường xuyên, JOINED hoặc SINGLE_TABLE có thể phù hợp hơn.

## 13. Bulk operation và cập nhật đa hình

Khi chạy JPQL bulk update/delete trên root entity, provider phải xử lý các bảng concrete có liên quan. Với TABLE_PER_CLASS, một thao tác trên Payment có thể được triển khai thành nhiều câu SQL hoặc một cấu trúc truy vấn phức tạp tùy provider.

Bulk operation không đi qua dirty checking của từng entity và có thể làm persistence context giữ trạng thái cũ. Sau bulk update/delete, cần xem xét clear hoặc refresh EntityManager phù hợp. Không giả định một JPQL bulk query trên root luôn tương đương với việc gọi setter trên từng entity.

Nếu thao tác chỉ áp dụng cho CardPayment, truy vấn trực tiếp subtype có thể rõ ràng và ít tốn kém hơn.

## 14. Kiểm thử mapping và truy vấn

Nên có integration test trên database cùng loại với production để xác minh:

- Persist từng subclass tạo đúng bảng concrete.
- Các field kế thừa được lưu ở từng bảng.
- ID duy nhất trên toàn hierarchy.
- Root repository trả về đúng kiểu subclass.
- TYPE lọc đúng subtype.
- TREAT truy cập đúng thuộc tính riêng của subtype.
- Sort, pagination và count hoạt động trên truy vấn đa hình.
- Native SQL sử dụng đúng tên bảng/cột vật lý.
- Các quan hệ tới root không tạo kỳ vọng sai về FK database.

Ví dụ test đa hình:

```java
@DataJpaTest
class PaymentRepositoryTest {

    @Autowired
    PaymentRepository paymentRepository;

    @Autowired
    CardPaymentRepository cardPaymentRepository;

    @Test
    void rootRepositoryReturnsConcreteSubtypes() {
        cardPaymentRepository.saveAndFlush(
            new CardPayment(
                new BigDecimal("120.00"),
                Instant.parse("2025-01-01T10:00:00Z"),
                "1234"
            )
        );

        List<Payment> payments = paymentRepository.findAll();

        assertThat(payments).hasSize(1);
        assertThat(payments.get(0)).isInstanceOf(CardPayment.class);
    }
}
```

Đây là khung minh họa; constructor, ID generator, field bắt buộc và test database cần khớp mapping thật. Nếu dùng sequence allocation, hãy tạo sequence đúng trong test schema hoặc để database test tạo schema theo cấu hình đã xác minh.

## 15. Lỗi thường gặp

| Biểu hiện | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Root repository không tìm thấy subtype | Subclass chưa là @Entity hoặc không thuộc persistence unit | Kiểm tra entity scan và mapping inheritance |
| Query root chậm khi hierarchy lớn | Provider hợp nhất nhiều bảng | Đo SQL, index từng bảng hoặc cân nhắc chiến lược khác |
| ID trùng giữa hai subclass | Các bảng dùng generator độc lập | Dùng generator chung bảo đảm uniqueness toàn hierarchy |
| Dùng IDENTITY bị lỗi với Hibernate | IDENTITY không phù hợp union-subclass vì cần ID duy nhất toàn hierarchy | Ưu tiên SEQUENCE/TABLE theo provider và database |
| FK không thể tham chiếu mọi subtype | Không có bảng vật lý chung cho root | Cân nhắc JOINED/SINGLE_TABLE hoặc registry table |
| Unique constraint không duy nhất toàn hierarchy | UNIQUE chỉ áp dụng trong từng bảng | Dùng bảng chung/registry hoặc đổi inheritance strategy |
| JPQL dùng tên bảng | Nhầm entity name với table name | JPQL dùng entity name; native SQL dùng table name |
| TYPE không lọc đúng | Dùng sai entity name hoặc query nhầm subtype | Kiểm tra @Entity name và provider query |
| Pagination đa hình tốn kém | UNION và count trên nhiều bảng | Đo, giới hạn phạm vi subtype hoặc thiết kế query chuyên biệt |

## 16. Bài tập thực hành

1. Tạo abstract Payment và hai entity CardPayment, BankTransferPayment.
2. Đặt TABLE_PER_CLASS trên root và @Table riêng cho mỗi subclass.
3. Tạo sequence dùng chung và xác nhận ID không trùng giữa hai bảng.
4. Tạo PaymentRepository và kiểm tra findAll trả về đúng subtype.
5. Viết JPQL dùng TYPE để chỉ lấy CardPayment.
6. Viết truy vấn dùng TREAT để lọc thuộc tính riêng của subtype.
7. So sánh SQL khi gọi repository của subtype và repository của root.
8. Tạo unique constraint riêng ở hai bảng và chứng minh nó không bảo đảm uniqueness toàn hierarchy.
9. Thử thiết kế FK tới Payment root và giải thích giới hạn của database.
10. Đo pagination/count trên hierarchy có nhiều bảng và so sánh với SINGLE_TABLE hoặc JOINED.

**Nguyên tắc xuyên suốt:** TABLE_PER_CLASS tạo bảng cho mỗi entity concrete và lặp lại các thuộc tính kế thừa. Truy vấn root là truy vấn đa hình, thường phải hợp nhất nhiều bảng. Hãy bảo đảm ID duy nhất toàn hierarchy, cân nhắc FK/unique constraint không thể đặt trên một bảng chung, và chỉ chọn chiến lược này khi mô hình truy vấn thực tế phù hợp.
