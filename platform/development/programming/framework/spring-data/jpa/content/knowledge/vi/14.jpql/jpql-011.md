# Truy vấn đa hình với TYPE và TREAT

## Mục tiêu

Khi các entity có quan hệ kế thừa, một truy vấn trên entity cha trong JPA thường trả về cả instance của các class con. Đây là truy vấn đa hình (polymorphic query). JPQL cung cấp hai biểu thức quan trọng để làm việc với hierarchy:

- `TYPE(entity)` kiểm tra kiểu entity thực tế của một hàng và cho phép lọc theo entity type.
- `TREAT(path AS Subtype)` thu hẹp một entity hoặc association path về subtype để truy cập thuộc tính chỉ có ở class con.

Ví dụ, hệ thống thanh toán có entity cha `Payment` và hai entity con `CardPayment` và `BankTransferPayment`. Ứng dụng có thể truy vấn mọi Payment, chỉ lấy CardPayment, hoặc tìm theo `cardLastFour` vốn chỉ tồn tại trên CardPayment.

Sau bài này, bạn có thể:

- Hiểu truy vấn đa hình trong JPQL.
- Dùng `TYPE` để lọc theo entity type.
- Dùng `TREAT` để truy cập thuộc tính và quan hệ của subtype.
- Phân biệt entity type với discriminator value trong database.
- Kết hợp TYPE/TREAT với JOIN, điều kiện và repository `@Query`.
- Hiểu ảnh hưởng của chiến lược inheritance tới SQL được sinh.
- Kiểm thử truy vấn subtype và xử lý lỗi thường gặp.

Ví dụ sử dụng Java 17+, Spring Boot 3.x, Jakarta Persistence và Spring Data JPA.

## 1. Truy vấn đa hình là gì?

Giả sử có hierarchy:

- `Payment`: entity cha, chứa ID, số tiền và thời điểm tạo.
- `CardPayment`: thanh toán bằng thẻ, có thêm bốn số cuối của thẻ.
- `BankTransferPayment`: chuyển khoản, có thêm tài khoản ngân hàng nhận.

Một JPQL query trên `Payment` có tính đa hình:

```java
select p
from Payment p
```

Kết quả có thể chứa `CardPayment` và `BankTransferPayment`. Khi provider nạp từng hàng, nó khởi tạo concrete entity class tương ứng với dữ liệu và mapping inheritance.

Đây là hành vi mặc định của truy vấn trên entity cha trong JPA. Nếu chỉ muốn một loại con hoặc muốn dùng thuộc tính riêng của subclass, hãy dùng `TYPE` hoặc `TREAT`.

## 2. Ví dụ entity hierarchy

Ví dụ dưới đây dùng chiến lược `SINGLE_TABLE` để minh họa discriminator. Hai biểu thức TYPE và TREAT là tính năng JPQL; cách dùng chúng không bị giới hạn ở riêng SINGLE_TABLE.

### 2.1. Entity cha Payment

```java
package com.example.demo.payment;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;

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

    @Column(nullable = false)
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

### 2.2. Subclass CardPayment

```java
package com.example.demo.payment;

import jakarta.persistence.*;

import java.math.BigDecimal;
import java.time.Instant;

@Entity
@DiscriminatorValue("CARD")
public class CardPayment extends Payment {

    @Column(name = "card_last_four", length = 4)
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

### 2.3. Subclass BankTransferPayment

```java
package com.example.demo.payment;

import jakarta.persistence.*;

import java.math.BigDecimal;
import java.time.Instant;

@Entity
@DiscriminatorValue("BANK_TRANSFER")
public class BankTransferPayment extends Payment {

    @Column(name = "bank_account", length = 40)
    private String bankAccount;

    protected BankTransferPayment() {
    }

    public BankTransferPayment(
            BigDecimal amount,
            Instant createdAt,
            String bankAccount
    ) {
        super(amount, createdAt);
        this.bankAccount = bankAccount;
    }

    public String getBankAccount() {
        return bankAccount;
    }
}
```

Root entity và các subclass đều được đánh dấu `@Entity`. Mỗi subclass có discriminator value riêng để provider xác định loại entity trong bảng chung.

Repository:

```java
package com.example.demo.payment;

import org.springframework.data.jpa.repository.JpaRepository;

public interface PaymentRepository
        extends JpaRepository<Payment, Long> {
}
```

## 3. TYPE: kiểm tra entity type thực tế

`TYPE` là JPQL type expression. Nó trả về entity type thực tế của entity expression được truyền vào. Có thể so sánh kết quả với entity type literal trong JPQL.

Ví dụ chỉ lấy thanh toán bằng thẻ:

```java
@Query("""
       select p
       from Payment p
       where type(p) = CardPayment
       """)
List<Payment> findCardPayments();
```

Trong query:

- `p` là alias của entity Payment.
- `TYPE(p)` lấy entity type thực tế của từng payment.
- `CardPayment` là entity type literal, theo entity name trong mapping.
- Kết quả vẫn là danh sách Payment; mỗi phần tử thực tế có thể là instance CardPayment.

Có thể lọc nhiều subtype:

```java
@Query("""
       select p
       from Payment p
       where type(p) in (CardPayment, BankTransferPayment)
       """)
List<Payment> findSupportedPaymentTypes();
```

### 3.1. Entity type literal là gì?

Trong JPQL, `CardPayment` là entity type literal, không phải chuỗi discriminator và cũng không phải cú pháp Java `CardPayment.class`.

Nếu entity khai báo entity name tùy chỉnh:

```java
@Entity(name = "CardTransaction")
public class CardPayment extends Payment {
    // ...
}
```

thì JPQL dùng entity name `CardTransaction`:

```java
@Query("""
       select p
       from Payment p
       where type(p) = CardTransaction
       """)
List<Payment> findCardTransactions();
```

Tên bảng trong `@Table` và giá trị trong `@DiscriminatorValue` không thay thế entity name trong biểu thức TYPE.

### 3.2. TYPE và discriminator value khác nhau

Trong ví dụ mapping:

```java
@DiscriminatorValue("CARD")
public class CardPayment extends Payment {
}
```

Query JPQL vẫn viết:

```java
where type(p) = CardPayment
```

Không viết:

```java
where type(p) = 'CARD'
```

`CARD` là giá trị discriminator được dùng trong schema/provider mapping. `CardPayment` là entity type literal mà JPQL sử dụng. Giữ query ở mức entity giúp code không phụ thuộc trực tiếp vào cách discriminator được lưu.

### 3.3. TYPE so sánh kiểu chính xác

`TYPE(p) = CardPayment` kiểm tra entity có đúng entity type CardPayment. Nếu hierarchy có class con sâu hơn, ví dụ `PremiumCardPayment extends CardPayment`, TYPE trả về kiểu thực tế cụ thể của entity đó; phép so sánh bằng CardPayment không nên được hiểu như kiểm tra “có thể gán cho CardPayment”.

Khi muốn thu hẹp một path về subtype và chấp nhận các subtype con của nó, dùng `TREAT` phù hợp hơn. Hãy thiết kế điều kiện theo đúng ý nghĩa nghiệp vụ: kiểu chính xác hay một nhánh của cây kế thừa.

## 4. TREAT: downcast entity path trong JPQL

Trong Java, có thể dùng `instanceof` và cast object để truy cập thuộc tính subclass. Trong JPQL, ta dùng `TREAT` để thu hẹp entity path về subtype.

Cú pháp:

```text
TREAT(<entity_or_association_path> AS <Subtype>)
```

Ví dụ:

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

`TREAT(p AS CardPayment)` cho phép truy cập thuộc tính `cardLastFour` vốn chỉ khai báo trong CardPayment.

Về ý nghĩa, query chỉ khớp những Payment có thể được xem là CardPayment (bao gồm các entity thuộc nhánh subtype tương ứng). Với entity không thuộc subtype đó, treated path không có giá trị phù hợp; điều kiện so sánh trong WHERE không khớp.

### 4.1. TYPE và TREAT giải quyết hai việc khác nhau

| Biểu thức | Mục đích | Ví dụ |
|---|---|---|
| `TYPE(p)` | Lấy entity type thực tế để so sánh/lọc | `TYPE(p) = CardPayment` |
| `TREAT(p AS CardPayment)` | Thu hẹp path về subtype để truy cập thuộc tính riêng | `TREAT(p AS CardPayment).cardLastFour` |

Dùng TYPE khi câu hỏi là “entity này thuộc đúng loại nào?”. Dùng TREAT khi câu hỏi là “trên nhánh subtype này, hãy truy cập thuộc tính hoặc association riêng của nó”.

Có thể kết hợp hai biểu thức, dù nhiều query chỉ cần TREAT:

```java
@Query("""
       select p
       from Payment p
       where type(p) = CardPayment
         and treat(p as CardPayment).cardLastFour = :lastFour
       """)
List<Payment> findExactCardTypeByLastFour(
        @Param("lastFour") String lastFour
);
```

Điều kiện TYPE trong ví dụ giới hạn vào đúng CardPayment. Nếu muốn bao gồm các class kế thừa từ CardPayment, hãy xem xét chỉ dùng điều kiện TREAT.

## 5. TREAT trên association path

TREAT có thể áp dụng cho entity-valued association path. Ví dụ một đơn hàng tham chiếu tới Payment, nhưng chỉ một số đơn hàng có CardPayment.

Entity PurchaseOrder:

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "payment_id")
    private Payment payment;

    protected PurchaseOrder() {
    }

    public Long getId() {
        return id;
    }

    public Payment getPayment() {
        return payment;
    }
}
```

Query tìm đơn hàng theo bốn số cuối của thẻ:

```java
@Query("""
       select o
       from PurchaseOrder o
       where treat(o.payment as CardPayment).cardLastFour = :lastFour
       """)
List<PurchaseOrder> findOrdersPaidByCard(
        @Param("lastFour") String lastFour
);
```

`o.payment` là association được khai báo bằng kiểu Payment. TREAT thu hẹp association đó thành CardPayment để truy cập `cardLastFour`.

Cách này hữu ích khi một association trỏ tới root entity của hierarchy, nhưng truy vấn cần thuộc tính chỉ có ở một subtype.

## 6. TREAT trong JOIN với collection association

Giả sử Customer có collection `payments` chứa nhiều Payment:

```java
@OneToMany(mappedBy = "customer")
private List<Payment> payments = new ArrayList<>();
```

Nếu muốn JOIN chỉ những phần tử thuộc CardPayment, có thể dùng TREAT trên collection path:

```java
@Query("""
       select distinct c
       from Customer c
       join treat(c.payments as CardPayment) p
       where p.cardLastFour = :lastFour
       """)
List<Customer> findCustomersByCardLastFour(
        @Param("lastFour") String lastFour
);
```

Ở đây:

- `c.payments` là collection association có phần tử khai báo ở kiểu Payment.
- `TREAT(c.payments AS CardPayment)` thu hẹp phần tử của collection về CardPayment.
- Alias `p` có thể truy cập thuộc tính `cardLastFour`.
- `distinct` loại bỏ customer trùng nếu một customer có nhiều payment khớp.

Tên property và mapping trong ví dụ cần tồn tại trong entity thực tế. Nếu chỉ có association đơn, dùng TREAT trên path đơn như mục trước; nếu có collection association, dùng cú pháp JOIN TREAT phù hợp.

## 7. TREAT trong SELECT và biểu thức query

TREAT là một biểu thức JPQL có thể dùng ở các vị trí biểu thức được đặc tả cho path. Khi dùng trong SELECT, cần chú ý kiểu kết quả và khả năng entity không thuộc subtype được chỉ định.

Ví dụ khái niệm:

```java
@Query("""
       select treat(p as CardPayment)
       from Payment p
       where type(p) = CardPayment
       """)
List<CardPayment> findCardPaymentEntities();
```

Điều kiện TYPE giúp bảo đảm kết quả chỉ gồm entity có đúng kiểu CardPayment trong ví dụ này. Nếu dùng TREAT mà không có điều kiện lọc, các entity không thuộc subtype có thể cho kết quả treated path null; hãy xác định kiểu trả về và hành vi null rõ ràng.

Trong phần lớn repository method, cách dễ đọc là SELECT entity root rồi dùng TREAT trong WHERE hoặc JOIN để lọc theo thuộc tính subclass. Chỉ chọn TREAT trong SELECT khi thật sự cần kết quả subtype và đã kiểm thử mapping/provider.

## 8. Ảnh hưởng của inheritance strategy

Cách viết JPQL TYPE/TREAT giữ nguyên về mặt ngữ nghĩa khi hierarchy dùng các chiến lược inheritance chuẩn, nhưng SQL provider sinh ra có thể khác.

### 8.1. SINGLE_TABLE

Tất cả subclass nằm trong một bảng. Provider thường dùng discriminator column để xác định loại entity và tạo điều kiện lọc subtype. TYPE/TREAT thường có thể được thực hiện mà không cần JOIN sang bảng subclass.

Ưu điểm là truy vấn đa hình thường đơn giản. Đổi lại, bảng có thể có nhiều cột null cho thuộc tính riêng của từng subtype.

### 8.2. JOINED

Thuộc tính cha và con nằm ở các bảng khác nhau. Khi truy cập thuộc tính subclass qua TREAT, provider có thể cần JOIN bảng subclass để lọc hoặc đọc dữ liệu.

Truy vấn đa hình qua root có thể cần nhiều JOIN. Hãy xem SQL và execution plan khi hierarchy lớn hoặc query chạy thường xuyên.

### 8.3. TABLE_PER_CLASS

Mỗi concrete subclass có bảng riêng. Truy vấn đa hình qua root có thể cần UNION. TYPE/TREAT vẫn thể hiện ý nghĩa ở mức JPQL, nhưng SQL được sinh có thể phức tạp hơn và phụ thuộc provider.

Chiến lược inheritance không thay đổi cách khai báo TYPE/TREAT trong JPQL. Nó thay đổi cấu trúc schema và chi phí thực thi.

## 9. Repository hoàn chỉnh

Ví dụ repository kết hợp các cách dùng:

```java
package com.example.demo.payment;

import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface PaymentRepository
        extends JpaRepository<Payment, Long> {

    // Truy vấn đa hình: có thể trả về mọi concrete subtype.
    @Query("""
           select p
           from Payment p
           order by p.createdAt desc
           """)
    List<Payment> findAllPayments();

    // Lọc đúng entity type CardPayment.
    @Query("""
           select p
           from Payment p
           where type(p) = CardPayment
           """)
    List<Payment> findCardPayments();

    // Lọc theo thuộc tính riêng của CardPayment.
    @Query("""
           select p
           from Payment p
           where treat(p as CardPayment).cardLastFour = :lastFour
           """)
    List<Payment> findByCardLastFour(
            @Param("lastFour") String lastFour
    );

    // Lọc theo nhiều entity type.
    @Query("""
           select p
           from Payment p
           where type(p) in (CardPayment, BankTransferPayment)
           """)
    List<Payment> findKnownPaymentTypes();
}
```

Các method trả `List<Payment>` vì query chọn entity root Payment. Khi đọc từng phần tử, có thể kiểm tra subtype bằng Java `instanceof` nếu logic ứng dụng thật sự cần xử lý riêng:

```java
for (Payment payment : paymentRepository.findCardPayments()) {
    if (payment instanceof CardPayment cardPayment) {
        System.out.println(cardPayment.getCardLastFour());
    }
}
```

Trong nhiều trường hợp, service có thể chuyển kết quả sang DTO để API không phụ thuộc entity hierarchy.

## 10. Kiểm thử TYPE và TREAT

Nên kiểm tra cả hai biểu thức với nhiều subtype. Ví dụ dùng `@DataJpaTest`:

```java
@DataJpaTest
class PaymentRepositoryTest {

    @Autowired
    private PaymentRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void typeFiltersExactEntityType() {
        repository.save(new CardPayment(
                new BigDecimal("120.00"),
                Instant.parse("2026-01-01T00:00:00Z"),
                "1234"
        ));

        repository.save(new BankTransferPayment(
                new BigDecimal("250.00"),
                Instant.parse("2026-01-02T00:00:00Z"),
                "00123456"
        ));

        entityManager.flush();
        entityManager.clear();

        List<Payment> cards = repository.findCardPayments();

        assertThat(cards).hasSize(1);
        assertThat(cards.get(0)).isInstanceOf(CardPayment.class);
    }

    @Test
    void treatFiltersBySubtypeProperty() {
        repository.save(new CardPayment(
                new BigDecimal("120.00"),
                Instant.parse("2026-01-01T00:00:00Z"),
                "1234"
        ));

        repository.save(new BankTransferPayment(
                new BigDecimal("250.00"),
                Instant.parse("2026-01-02T00:00:00Z"),
                "00123456"
        ));

        entityManager.flush();
        entityManager.clear();

        List<Payment> result = repository.findByCardLastFour("1234");

        assertThat(result).hasSize(1);
        assertThat(result.get(0)).isInstanceOf(CardPayment.class);
    }
}
```

Ví dụ test giả định có các import JUnit 5, AssertJ, Spring Boot JPA test support, BigDecimal, Instant và entity/repository đã được cấu hình. `flush()` gửi thay đổi xuống database; `clear()` buộc query đọc lại từ database thay vì dùng các instance còn managed trong persistence context.

Nên bổ sung test cho:

- Không có subtype nào khớp.
- TYPE với từng subclass.
- TREAT trên association đơn và collection nếu ứng dụng dùng các query đó.
- Hierarchy có nhiều cấp kế thừa.
- Discriminator value và entity name tùy chỉnh.
- Mỗi inheritance strategy đang được ứng dụng sử dụng.

Nếu query dùng cú pháp TREAT trên collection hoặc có nhiều JOIN, kiểm thử bằng đúng JPA provider và version đang chạy. Embedded database có thể xác nhận JPQL nhưng không thay thế kiểm thử hiệu năng trên database production.

## 11. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| TYPE không tìm thấy entity type | Dùng tên bảng, tên class không khớp entity name hoặc chuỗi discriminator | Dùng entity name trong JPQL |
| Query TYPE trả về ít kết quả hơn dự kiến | So sánh bằng kiểm tra kiểu chính xác | Dùng TYPE cho loại chính xác; dùng TREAT khi cần nhánh subtype |
| Không truy cập được thuộc tính subclass | Query chỉ dùng alias của entity cha | Dùng TREAT trước property riêng của subclass |
| TREAT không khớp entity | Entity thực tế không thuộc subtype được chỉ định | Kiểm tra mapping và dữ liệu subtype |
| Query association subtype lỗi | Đường dẫn association hoặc cú pháp TREAT không đúng | Kiểm tra kiểu association và JPQL path |
| Kết quả trùng sau JOIN collection | Một entity cha khớp nhiều phần tử collection | Dùng DISTINCT nếu semantics yêu cầu |
| SQL quá phức tạp | JOINED/TABLE_PER_CLASS tạo JOIN/UNION | Kiểm tra SQL, index và inheritance strategy |
| Provider báo không hỗ trợ TREAT | JPA/provider quá cũ hoặc query không đúng grammar version | Dùng JPA 2.1+ và kiểm tra version provider |
| Query dùng discriminator literal không chạy | Nhầm discriminator value với entity type literal | Dùng tên entity như CardPayment |

## 12. Lưu ý về phiên bản và tính tương thích

`TYPE` là biểu thức JPQL dùng để kiểm tra entity type trong inheritance hierarchy. `TREAT` được bổ sung trong JPA 2.1 để hỗ trợ downcast entity/path trong query. Spring Boot 3.x dùng Jakarta Persistence; hãy đối chiếu version API/provider của dự án khi dùng ứng dụng cũ.

Một số điểm cần kiểm tra khi nâng cấp:

- Import `jakarta.persistence.*` trong Spring Boot 3.x; dự án Spring Boot 2.x thường dùng `javax.persistence.*`.
- Cú pháp TREAT trên association/collection cần được hỗ trợ bởi provider và version cụ thể.
- Tên entity trong query phải khớp `@Entity(name = ...)` nếu đã tùy chỉnh.
- Query phải dùng tên property Java, không dùng tên cột database.
- Hãy kiểm thử query sau khi đổi inheritance strategy hoặc discriminator mapping.

## 13. Checklist trước khi đưa query vào production

- [ ] Truy vấn root entity có thực sự cần trả về mọi subtype không?
- [ ] Dùng TYPE khi cần so sánh entity type chính xác.
- [ ] Dùng TREAT khi cần truy cập thuộc tính/association của subtype.
- [ ] Entity type literal khớp entity name, không phải discriminator value.
- [ ] Association path và collection path được khai báo đúng trong entity.
- [ ] Xác định rõ hành vi khi entity không thuộc subtype được treat.
- [ ] Dùng DISTINCT khi JOIN collection có thể tạo kết quả lặp.
- [ ] Kiểm tra SQL sinh ra với inheritance strategy thực tế.
- [ ] Kiểm thử trên JPA provider/version mà ứng dụng triển khai.
- [ ] Không ghép input người dùng vào JPQL; dùng bind parameter.

## Kết luận

`TYPE` và `TREAT` giúp JPQL truy vấn inheritance hierarchy một cách rõ ràng. TYPE kiểm tra entity type thực tế và phù hợp khi cần lọc đúng một loại entity. TREAT thu hẹp entity hoặc association path về subtype để truy cập thuộc tính riêng của class con.

Khi viết query, hãy dùng entity name trong TYPE, dùng TREAT cho downcast và giữ tham số ở dạng bind parameter. Kết hợp các biểu thức này với JOIN, repository `@Query` và kiểm thử trên provider thực tế giúp truy vấn đa hình dễ đọc, đúng kiểu và ổn định.
