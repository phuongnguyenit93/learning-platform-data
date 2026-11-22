# Truy vấn theo lớp cha và xử lý lớp con trong Spring Data JPA

Trong mô hình hướng đối tượng, nhiều entity có thể chia sẻ thuộc tính chung nhưng vẫn có dữ liệu và hành vi riêng. Ví dụ Payment có các lớp con CardPayment và BankTransfer. Khi truy vấn Payment, ứng dụng thường cần lấy mọi loại thanh toán; ở tình huống khác, ứng dụng chỉ muốn lấy giao dịch thẻ hoặc lọc theo thuộc tính chỉ có ở lớp con.

JPA hỗ trợ kế thừa entity và truy vấn đa hình (polymorphic query). Spring Data JPA kế thừa khả năng đó thông qua repository. Bài học này trình bày cách mô hình hóa hệ thống kế thừa, truy vấn lớp cha, lọc theo kiểu thực tế bằng TYPE, truy cập thuộc tính lớp con bằng TREAT, tạo repository riêng và lựa chọn chiến lược kế thừa.

## 1. Entity inheritance là gì?

Entity inheritance cho phép một entity kế thừa thuộc tính và mapping từ entity cha. Mọi lớp entity trong cùng hierarchy đều có thể được truy vấn theo kiểu lớp cha nếu lớp cha là một entity.

Ví dụ miền thanh toán:

- Payment lưu thông tin chung: ID, số tiền, trạng thái và thời điểm tạo.
- CardPayment bổ sung bốn chữ số cuối của thẻ và mạng thẻ.
- BankTransfer bổ sung mã ngân hàng và mã tham chiếu chuyển khoản.

Sơ đồ lớp:

~~~mermaid
classDiagram
    class Payment {
        Long id
        BigDecimal amount
        PaymentStatus status
        Instant createdAt
    }
    class CardPayment {
        String cardLast4
        String network
    }
    class BankTransfer {
        String bankCode
        String transferReference
    }
    Payment <|-- CardPayment
    Payment <|-- BankTransfer
~~~

Cả CardPayment và BankTransfer đều là Payment, vì vậy có thể xử lý qua kiểu Payment khi chỉ cần thông tin chung. Khi cần trường riêng của lớp con, phải truy cập đúng kiểu con hoặc dùng truy vấn có cơ chế downcast.

## 2. Khai báo hierarchy bằng JPA

JPA đặt @Inheritance trên entity gốc. Có ba chiến lược chính:

- SINGLE_TABLE: toàn bộ hierarchy nằm trong một bảng, phân biệt bằng discriminator.
- JOINED: bảng của lớp cha và mỗi lớp con được nối bằng khóa chính.
- TABLE_PER_CLASS: mỗi lớp cụ thể có bảng riêng, lặp lại các cột kế thừa.

Nếu không chỉ định strategy, JPA mặc định SINGLE_TABLE.

### Ví dụ dùng SINGLE_TABLE

Đây là ví dụ để thấy rõ discriminator và truy vấn đa hình:

~~~java
package com.example.payments;

import java.math.BigDecimal;
import java.time.Instant;

import jakarta.persistence.*;

@Entity
@Table(name = "payments")
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(name = "payment_type")
public abstract class Payment {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal amount;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private PaymentStatus status;

    @Column(nullable = false)
    private Instant createdAt;

    protected Payment() {
    }

    protected Payment(
            BigDecimal amount,
            PaymentStatus status,
            Instant createdAt) {
        this.amount = amount;
        this.status = status;
        this.createdAt = createdAt;
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
}
~~~

Enum dùng chung:

~~~java
package com.example.payments;

public enum PaymentStatus {
    PENDING,
    COMPLETED,
    FAILED
}
~~~

Lớp con CardPayment:

~~~java
package com.example.payments;

import java.math.BigDecimal;
import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.DiscriminatorValue;
import jakarta.persistence.Entity;

@Entity
@DiscriminatorValue("CARD")
public class CardPayment extends Payment {

    @Column(name = "card_last4", length = 4)
    private String cardLast4;

    @Column(name = "card_network", length = 30)
    private String network;

    protected CardPayment() {
    }

    public CardPayment(
            BigDecimal amount,
            PaymentStatus status,
            Instant createdAt,
            String cardLast4,
            String network) {
        super(amount, status, createdAt);
        this.cardLast4 = cardLast4;
        this.network = network;
    }

    public String getCardLast4() {
        return cardLast4;
    }

    public String getNetwork() {
        return network;
    }
}
~~~

Lớp con BankTransfer:

~~~java
package com.example.payments;

import java.math.BigDecimal;
import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.DiscriminatorValue;
import jakarta.persistence.Entity;

@Entity
@DiscriminatorValue("BANK")
public class BankTransfer extends Payment {

    @Column(name = "bank_code", length = 20)
    private String bankCode;

    @Column(name = "transfer_reference", length = 80)
    private String transferReference;

    protected BankTransfer() {
    }

    public BankTransfer(
            BigDecimal amount,
            PaymentStatus status,
            Instant createdAt,
            String bankCode,
            String transferReference) {
        super(amount, status, createdAt);
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

Với SINGLE_TABLE, database chỉ có bảng payments. Các cột riêng của CardPayment và BankTransfer nằm chung bảng; hàng của loại này sẽ không dùng cột của loại kia, vì vậy những cột đó thường phải cho phép NULL. Cột payment_type xác định kiểu entity thực tế khi Hibernate đọc dữ liệu.

## 3. Phân biệt entity cha với @MappedSuperclass

Không phải mọi lớp Java cha đều là entity cha.

**Entity cha** được đánh dấu @Entity và có thể là gốc của hierarchy. Nó có thể được truy vấn trực tiếp bằng JPQL và dùng làm kiểu generic cho JpaRepository.

**@MappedSuperclass** chỉ cung cấp thuộc tính mapping cho entity con. Bản thân lớp đó không phải entity, không có bảng entity riêng và không thể được truy vấn như một entity root.

Ví dụ:

~~~java
@MappedSuperclass
public abstract class AuditableEntity {

    @Column(nullable = false, updatable = false)
    private Instant createdAt;

    private Instant updatedAt;
}

@Entity
public class Customer extends AuditableEntity {
    @Id
    @GeneratedValue
    private Long id;
}
~~~

Customer kế thừa các thuộc tính createdAt và updatedAt, nhưng không thể tạo JpaRepository<AuditableEntity, Long> để truy vấn tất cả entity kế thừa mapped superclass. Nếu cần truy vấn đa hình qua lớp cha, lớp cha phải là @Entity và hierarchy phải được ánh xạ bằng @Inheritance.

## 4. Ba chiến lược kế thừa và tác động tới truy vấn

### SINGLE_TABLE

Toàn bộ hierarchy lưu trong một bảng, có discriminator để nhận diện kiểu thực tế.

Ưu điểm:

- Truy vấn lớp cha đơn giản, thường không cần join.
- Truy vấn đa hình thường nhanh và dễ phân trang.
- Cấu trúc vật lý ít bảng.

Nhược điểm:

- Nhiều cột chỉ dùng cho một số lớp con và phải chấp nhận NULL.
- Khó đặt ràng buộc NOT NULL riêng theo từng subtype bằng mapping thông thường.
- Bảng có thể rất rộng nếu hierarchy lớn.

### JOINED

Lớp cha và từng lớp con có bảng riêng. Bảng con dùng khóa chính đồng thời là khóa ngoại tới bảng cha.

Khai báo trên root:

~~~java
@Entity
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class Payment {
    // Các thuộc tính chung.
}
~~~

Khi truy vấn Payment, JPA provider cần kết hợp bảng cha với bảng con để dựng kiểu cụ thể. Truy vấn theo subtype cũng có thể cần join. Cách này chuẩn hóa dữ liệu tốt hơn SINGLE_TABLE, nhưng polymorphic query có thể tốn nhiều join.

### TABLE_PER_CLASS

Mỗi entity cụ thể có bảng riêng và lặp lại các thuộc tính được kế thừa:

~~~java
@Entity
@Inheritance(strategy = InheritanceType.TABLE_PER_CLASS)
public abstract class Payment {
    // Các thuộc tính chung.
}
~~~

Truy vấn lớp cha có thể cần UNION giữa các bảng con. Các thao tác đa hình, khóa chính và tối ưu hiệu năng cần được kiểm tra kỹ với database và provider. Chiến lược này thường ít được chọn hơn khi ứng dụng cần truy vấn đa hình thường xuyên.

### So sánh

| Tiêu chí | SINGLE_TABLE | JOINED | TABLE_PER_CLASS |
|---|---|---|---|
| Cấu trúc | Một bảng cho cả hierarchy | Bảng cha và bảng con | Mỗi lớp cụ thể một bảng |
| Discriminator | Thường dùng | Có thể dùng nhưng không bắt buộc | Không cần chung một bảng |
| Truy vấn lớp cha | Đơn giản, không cần join | Thường cần join | Có thể cần UNION |
| Cột subtype | Nhiều cột nullable | Nằm ở bảng con | Lặp lại ở từng bảng |
| Chuẩn hóa | Thấp hơn | Tốt hơn | Có trùng lặp |
| Phân trang đa hình | Thường đơn giản | Phụ thuộc join | Có thể phức tạp |
| Phù hợp | Hierarchy nhỏ, đọc đa hình nhiều | Muốn schema chuẩn hóa | Ít truy vấn đa hình, lớp cụ thể độc lập hơn |

Không có strategy tốt nhất cho mọi hệ thống. Chọn theo số lớp con, số cột riêng, kiểu truy vấn thường dùng, khả năng database và kết quả đo hiệu năng.

## 5. Tạo repository cho lớp cha

Khi lớp gốc là @Entity, có thể tạo repository dùng kiểu Payment:

~~~java
package com.example.payments;

import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;

public interface PaymentRepository
        extends JpaRepository<Payment, Long> {

    List<Payment> findByStatus(PaymentStatus status);
}
~~~

Gọi:

~~~java
List<Payment> payments =
        paymentRepository.findByStatus(PaymentStatus.COMPLETED);
~~~

Repository trả về các entity thuộc hierarchy có trạng thái COMPLETED, bao gồm CardPayment và BankTransfer. Mỗi phần tử vẫn có kiểu runtime thực tế tương ứng với lớp con.

Đây là truy vấn đa hình: truy vấn theo kiểu Payment bao gồm các entity của những lớp con cụ thể.

Có thể lưu một đối tượng lớp con qua repository cha:

~~~java
Payment payment = new CardPayment(
        new BigDecimal("125.00"),
        PaymentStatus.PENDING,
        Instant.now(),
        "4242",
        "VISA"
);

Payment saved = paymentRepository.save(payment);
~~~

JPA lưu entity theo kiểu runtime CardPayment. Repository cha không biến đối tượng thành Payment thuần; nó chỉ định nghĩa kiểu truy cập tổng quát.

## 6. Truy vấn lớp cha bằng JPQL và lọc kiểu thực tế bằng TYPE

JPQL truy vấn theo tên entity và thuộc tính Java, không dùng tên bảng/cột vật lý.

Ví dụ lấy mọi payment:

~~~java
@Query("select p from Payment p")
List<Payment> findAllPayments();
~~~

Nếu chỉ muốn lấy chính xác CardPayment, dùng toán tử TYPE:

~~~java
@Query("""
       select p
       from Payment p
       where type(p) = CardPayment
       """)
List<Payment> findCardPayments();
~~~

TYPE trả về entity type thực tế. type(p) = CardPayment lọc đúng kiểu CardPayment. Nếu hierarchy có lớp con sâu hơn như CorporateCardPayment extends CardPayment, điều kiện trên không tự động đồng nghĩa với "CardPayment và mọi subtype của nó"; hãy liệt kê các kiểu cần lấy hoặc dùng truy vấn theo mô hình phù hợp.

Có thể lọc nhiều kiểu:

~~~java
@Query("""
       select p
       from Payment p
       where type(p) in (CardPayment, BankTransfer)
       """)
List<Payment> findSupportedPaymentTypes();
~~~

Entity name mặc định là tên lớp đơn giản. Nếu dùng @Entity(name = "CardTxn"), JPQL phải tham chiếu CardTxn, không phải tên bảng hoặc tên Java class cũ.

TYPE hữu ích khi:

- Lấy dữ liệu từ repository lớp cha nhưng chỉ muốn một subtype.
- Tính tổng hoặc thống kê theo loại entity.
- Áp dụng quy tắc nghiệp vụ khác nhau theo subtype trong một truy vấn.
- Trả dữ liệu về DTO theo loại entity.

## 7. Dùng TREAT để truy cập thuộc tính lớp con

TYPE lọc theo kiểu entity. TREAT dùng để downcast một path expression sang subtype, cho phép truy cập thuộc tính chỉ có ở lớp con.

Ví dụ tìm CardPayment theo bốn số cuối:

~~~java
@Query("""
       select p
       from Payment p
       where treat(p as CardPayment).cardLast4 = :last4
       """)
List<Payment> findCardPaymentsByLast4(
        @Param("last4") String last4);
~~~

TREAT diễn giải p như CardPayment trong biểu thức. Nếu entity không phải kiểu tương thích, nó không thỏa điều kiện subtype đó. Kiểu kết quả của truy vấn vẫn là Payment vì SELECT trả về p.

Có thể kết hợp TYPE với điều kiện chung:

~~~java
@Query("""
       select p
       from Payment p
       where type(p) = CardPayment
         and p.status = :status
       """)
List<Payment> findCardsByStatus(
        @Param("status") PaymentStatus status);
~~~

Với JOINED, provider có thể cần join bảng con để đọc cardLast4. Với SINGLE_TABLE, thuộc tính nằm trong cùng bảng nhưng vẫn cần điều kiện discriminator để chỉ lấy đúng loại. Chi tiết SQL được provider sinh ra.

## 8. Tạo repository riêng cho lớp con

Nếu nhiều thao tác chỉ liên quan tới một subtype, repository riêng giúp API rõ ràng và kiểu trả về chính xác hơn.

~~~java
package com.example.payments;

import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;

public interface CardPaymentRepository
        extends JpaRepository<CardPayment, Long> {

    List<CardPayment> findByCardLast4(String cardLast4);

    List<CardPayment> findByNetworkIgnoreCase(String network);
}
~~~

CardPaymentRepository chỉ truy vấn entity CardPayment. Kết quả là List<CardPayment>, nên code gọi có thể sử dụng trực tiếp các thuộc tính riêng như cardLast4 và network.

Ví dụ:

~~~java
List<CardPayment> cards =
        cardPaymentRepository.findByCardLast4("4242");

for (CardPayment card : cards) {
    System.out.println(card.getNetwork());
}
~~~

Repository riêng phù hợp khi subtype có nhiều query method, service và use case riêng. Không cần tạo repository cho mọi lớp con nếu ứng dụng chỉ thao tác qua PaymentRepository và không có truy vấn riêng.

## 9. Derived query và thuộc tính kế thừa

Spring Data phân tích tên derived query theo thuộc tính entity. Repository lớp cha có thể dùng các thuộc tính được khai báo trong Payment:

~~~java
List<Payment> findByStatusAndCreatedAtAfter(
        PaymentStatus status,
        Instant from);
~~~

Các thuộc tính status và createdAt được kế thừa bởi CardPayment và BankTransfer nên query ở PaymentRepository hợp lệ.

Ngược lại, cardLast4 chỉ được khai báo trong CardPayment. Không thể tùy tiện thêm phương thức sau vào PaymentRepository:

~~~java
// Không hợp lệ nếu Payment không khai báo cardLast4.
List<Payment> findByCardLast4(String cardLast4);
~~~

Spring Data không tìm thấy thuộc tính cardLast4 trên kiểu domain Payment và thường báo lỗi khi tạo repository.

Có hai cách đúng:

1. Khai báo findByCardLast4 trong CardPaymentRepository.
2. Giữ query ở PaymentRepository và dùng @Query với TREAT để downcast.

Ví dụ derived query trên lớp con:

~~~java
public interface CardPaymentRepository
        extends JpaRepository<CardPayment, Long> {

    List<CardPayment> findByCardLast4AndStatus(
            String cardLast4,
            PaymentStatus status);
}
~~~

Tên thuộc tính trong derived query là tên Java của entity, không phải tên cột SQL.

## 10. Kết hợp truy vấn lớp cha với phân trang

Nếu bảng thanh toán lớn, không nên tải toàn bộ Payment vào bộ nhớ. Có thể phân trang ở repository cha:

~~~java
public interface PaymentRepository
        extends JpaRepository<Payment, Long> {

    Page<Payment> findByStatus(
            PaymentStatus status,
            Pageable pageable);
}
~~~

Gọi:

~~~java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Direction.DESC, "createdAt")
);

Page<Payment> result =
        paymentRepository.findByStatus(
                PaymentStatus.COMPLETED,
                pageable
        );
~~~

Page có dữ liệu của trang hiện tại và thông tin tổng số bản ghi/trang. Tùy truy vấn, Spring Data có thể chạy thêm truy vấn COUNT. Nếu chỉ cần biết có trang kế tiếp hay không, cân nhắc Slice để tránh tính tổng số.

Khi phân trang truy vấn đa hình, strategy kế thừa ảnh hưởng SQL. JOINED có thể tạo join; TABLE_PER_CLASS có thể dùng UNION. Hãy xem SQL và đo hiệu năng trên dữ liệu gần với production.

## 11. Truy vấn DTO theo subtype

API thường không nên trả entity trực tiếp. Có thể chiếu dữ liệu cần thiết sang DTO. Với một loại thanh toán cụ thể, JPQL có thể dùng TREAT:

~~~java
public record CardPaymentSummary(
        Long id,
        BigDecimal amount,
        String cardLast4,
        String network
) {
}
~~~

Ví dụ query:

~~~java
@Query("""
       select new com.example.payments.CardPaymentSummary(
           p.id,
           p.amount,
           treat(p as CardPayment).cardLast4,
           treat(p as CardPayment).network
       )
       from Payment p
       where type(p) = CardPayment
       """)
List<CardPaymentSummary> findCardSummaries();
~~~

Constructor expression của JPQL yêu cầu tên lớp DTO đầy đủ và thứ tự/tham số khớp constructor. Nếu query trả nhiều subtype với cấu trúc khác nhau, cân nhắc DTO chung có trường type hoặc tách query theo subtype thay vì tạo DTO chứa quá nhiều trường nullable.

## 12. Quan hệ entity trỏ tới lớp cha

Một entity khác có thể tham chiếu Payment:

~~~java
@Entity
public class Refund {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(optional = false)
    private Payment originalPayment;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal amount;

    protected Refund() {
    }
}
~~~

originalPayment có thể tham chiếu CardPayment hoặc BankTransfer. Khi tải Refund, Hibernate có thể dựng đúng subtype của Payment theo mapping inheritance. Nếu cần truy cập thuộc tính riêng, phải kiểm tra kiểu hoặc dùng TREAT trong truy vấn.

Không nên dùng instanceof như cơ chế truy vấn database. instanceof chỉ kiểm tra object đã có trong JVM; nó không lọc dữ liệu ở database. Dùng TYPE/TREAT khi muốn lọc tại tầng truy vấn.

## 13. Lựa chọn strategy theo workload

Hãy đánh giá cả cấu trúc lẫn truy vấn thực tế:

- Chọn SINGLE_TABLE khi hierarchy tương đối gọn, truy vấn lớp cha thường xuyên và chấp nhận cột subtype nullable.
- Chọn JOINED khi muốn mỗi subtype có bảng/cột riêng và schema chuẩn hóa; kiểm tra chi phí join cho truy vấn đa hình.
- Chọn TABLE_PER_CLASS khi lớp cụ thể ít cần truy vấn chung qua root; đánh giá UNION, khóa và hỗ trợ provider.
- Nếu chỉ muốn tái sử dụng thuộc tính audit hoặc thông tin chung mà không cần truy vấn đa hình, cân nhắc @MappedSuperclass.
- Nếu các lớp con chỉ khác một vài giá trị dữ liệu, cân nhắc enum hoặc composition thay cho inheritance.
- Nếu hành vi thay đổi độc lập với cấu trúc dữ liệu, composition thường linh hoạt hơn hierarchy sâu.

Đừng chọn strategy chỉ vì số bảng ít hay nhiều. Đo truy vấn quan trọng, xem execution plan và kiểm tra cách provider tạo SQL.

## 14. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách khắc phục |
|---|---|---|
| Không truy vấn được lớp cha | Lớp cha là @MappedSuperclass | Dùng @Entity nếu cần query root đa hình |
| Không tìm thấy thuộc tính lớp con | Derived query khai báo trên repository của lớp cha | Dùng repository subtype hoặc JPQL TREAT |
| JPQL không nhận entity name | Dùng tên bảng hoặc sai @Entity(name) | Dùng entity name trong JPQL |
| Query trả nhiều loại ngoài mong muốn | Chỉ truy vấn root mà không lọc subtype | Dùng TYPE hoặc repository lớp con |
| Query subtype chậm | JOINED nhiều join hoặc TABLE_PER_CLASS dùng UNION | Kiểm tra SQL, index và execution plan |
| Cột subtype bị NULL | SINGLE_TABLE dùng chung bảng | Thiết kế nullable/constraint phù hợp hoặc cân nhắc JOINED |
| Discriminator không khớp | @DiscriminatorValue không nhất quán với dữ liệu | Kiểm tra mapping và migration |
| Ép kiểu object gây ClassCastException | Kết quả không phải subtype giả định | Dùng TYPE/TREAT hoặc kiểm tra kiểu trước khi cast |
| Không truy vấn được lớp cha dùng chung | Chỉ dùng @MappedSuperclass | Tạo entity root nếu thực sự cần polymorphic query |

## 15. Kiểm thử truy vấn đa hình

Dùng @DataJpaTest để xác nhận repository cha trả đúng các subtype và query lọc subtype hoạt động.

Ví dụ test:

~~~java
package com.example.payments;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class PaymentRepositoryTest {

    @Autowired
    private PaymentRepository paymentRepository;

    @Autowired
    private CardPaymentRepository cardPaymentRepository;

    @Test
    void baseRepositoryReturnsAllSubtypes() {
        paymentRepository.save(new CardPayment(
                new BigDecimal("100.00"),
                PaymentStatus.COMPLETED,
                Instant.parse("2026-01-01T10:00:00Z"),
                "4242",
                "VISA"
        ));

        paymentRepository.save(new BankTransfer(
                new BigDecimal("200.00"),
                PaymentStatus.COMPLETED,
                Instant.parse("2026-01-02T10:00:00Z"),
                "VCB",
                "REF-001"
        ));

        var payments = paymentRepository.findByStatus(
                PaymentStatus.COMPLETED);

        assertThat(payments).hasSize(2);
        assertThat(payments)
                .anyMatch(CardPayment.class::isInstance);
        assertThat(payments)
                .anyMatch(BankTransfer.class::isInstance);
    }

    @Test
    void subtypeRepositoryReturnsOnlyCardPayments() {
        paymentRepository.save(new CardPayment(
                new BigDecimal("100.00"),
                PaymentStatus.PENDING,
                Instant.parse("2026-01-01T10:00:00Z"),
                "4242",
                "VISA"
        ));

        var cards = cardPaymentRepository.findByCardLast4("4242");

        assertThat(cards).hasSize(1);
        assertThat(cards.get(0).getNetwork()).isEqualTo("VISA");
    }
}
~~~

Test thứ nhất kiểm tra truy vấn từ root trả cả hai subtype. Test thứ hai xác nhận repository con chỉ trả CardPayment. Có thể bổ sung test TYPE/TREAT, phân trang, discriminator và truy vấn trên JOINED/TABLE_PER_CLASS nếu dự án dùng các strategy đó.

Khi kiểm thử với @DataJpaTest, database nhúng có thể khác database production. Nếu cần xác minh SQL của strategy kế thừa hoặc index, hãy chạy integration test trên cùng hệ quản trị với môi trường triển khai.

## 16. Checklist tự đánh giá

- [ ] Giải thích được entity inheritance và polymorphic query.
- [ ] Phân biệt @Entity root với @MappedSuperclass.
- [ ] Biết @Inheritance đặt trên entity gốc.
- [ ] Phân biệt SINGLE_TABLE, JOINED và TABLE_PER_CLASS.
- [ ] Tạo được hierarchy Payment, CardPayment và BankTransfer.
- [ ] Tạo repository cho lớp cha và hiểu kết quả bao gồm các lớp con.
- [ ] Truy vấn đúng subtype bằng TYPE.
- [ ] Dùng TREAT để lọc thuộc tính chỉ có ở lớp con.
- [ ] Biết vì sao derived query của lớp cha không thể tự tham chiếu field chỉ có ở lớp con.
- [ ] Tạo repository riêng cho subtype khi cần.
- [ ] Dùng Page/Slice để phân trang truy vấn đa hình.
- [ ] Biết DTO projection cho một subtype.
- [ ] Kiểm thử hành vi polymorphic query và strategy thực tế.

## 17. Kết luận

Khi entity có kế thừa, repository của lớp cha có thể truy vấn đa hình và trả về các instance của lớp con. Đây là cách thuận tiện để xử lý dữ liệu chung mà không cần biết mọi subtype trước.

Dùng TYPE khi cần lọc theo kiểu entity thực tế, TREAT khi cần truy cập thuộc tính lớp con trong JPQL, và repository riêng khi subtype có nhiều query method riêng. @MappedSuperclass chỉ tái sử dụng mapping, không phải entity root để truy vấn. Chọn SINGLE_TABLE, JOINED hoặc TABLE_PER_CLASS theo cấu trúc dữ liệu và workload, rồi xác minh SQL thực tế bằng test và execution plan.
