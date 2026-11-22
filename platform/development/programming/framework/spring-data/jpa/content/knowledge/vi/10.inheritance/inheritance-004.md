# Chiến lược JOINED và chi phí kết nối bảng trong Spring Data JPA

JPA cung cấp nhiều cách ánh xạ kế thừa giữa các lớp entity và bảng quan hệ. Với chiến lược **JOINED**, mỗi lớp entity trong hệ thống kế thừa có bảng riêng; bảng của lớp con dùng khóa chính đồng thời làm khóa ngoại tham chiếu bảng của lớp cha. Cách này chuẩn hóa dữ liệu và giữ các cột đặc thù ở đúng bảng, nhưng các truy vấn cần dựng một entity từ nhiều cấp kế thừa thường phải JOIN nhiều bảng.

Cần phân biệt rõ **JOINED inheritance** với association join table. JOINED là cách lưu trữ quan hệ *is-a* giữa các lớp trong một hierarchy. `@JoinTable` thường dùng để lưu một association như many-to-many hoặc một số quan hệ một chiều. Hai cơ chế có mục đích và cấu trúc schema khác nhau.

Tài liệu dùng Jakarta Persistence (`jakarta.persistence`) và Spring Data JPA trong Spring Boot 3 / Spring Framework 6 trở lên. Dự án Spring Boot 2 cũ thường dùng namespace `javax.persistence`.

## 1. Ba chiến lược kế thừa của JPA

JPA có ba chiến lược phổ biến được khai báo bằng `@Inheritance`:

| Chiến lược | Cấu trúc bảng | Cách lưu thuộc tính | Đặc điểm truy vấn |
|---|---|---|---|
| `SINGLE_TABLE` | Một bảng cho cả hierarchy | Cột của lớp cha và mọi lớp con nằm chung một bảng | Ít JOIN; cột riêng của subtype thường phải nullable |
| `JOINED` | Mỗi entity class trong hierarchy có bảng riêng | Bảng lớp con chứa PK dùng chung và FK tới bảng cha | Chuẩn hóa tốt; truy vấn polymorphic có thể JOIN nhiều bảng |
| `TABLE_PER_CLASS` | Mỗi lớp concrete có bảng riêng chứa cả thuộc tính kế thừa | Thuộc tính lớp cha có thể được lặp trong các bảng con | Truy vấn lớp cha thường cần UNION hoặc cơ chế tương đương |

`SINGLE_TABLE` thường giảm số JOIN khi đọc, nhưng bảng có nhiều cột nullable và có thể khó áp constraint riêng cho từng subtype. `TABLE_PER_CLASS` tránh JOIN cha-con khi truy vấn riêng từng subtype, nhưng lặp dữ liệu chung và truy vấn polymorphic có thể cần UNION. `JOINED` cân bằng tính chuẩn hóa với khả năng truy vấn đa hình, đổi lại có chi phí kết nối bảng.

JPA mặc định dùng `SINGLE_TABLE` nếu không khai báo chiến lược. Hãy khai báo rõ `@Inheritance(strategy = InheritanceType.JOINED)` khi muốn dùng JOINED.

## 2. Cấu trúc dữ liệu của JOINED

Giả sử hệ thống có một loại thanh toán chung và hai loại cụ thể:

- `Payment`: lớp entity cha, chứa mã, số tiền và thời điểm tạo.
- `CardPayment`: thanh toán bằng thẻ, có bốn số cuối và mã tham chiếu.
- `BankTransferPayment`: chuyển khoản, có mã ngân hàng và số tài khoản nhận.

Với JOINED, schema có thể được biểu diễn như sau:

```sql
create table payment (
    id bigint primary key,
    amount decimal(19, 2) not null,
    created_at timestamp not null
);

create table card_payment (
    id bigint primary key,
    card_last4 varchar(4) not null,
    authorization_code varchar(80),
    constraint fk_card_payment_payment
        foreign key (id) references payment(id)
);

create table bank_transfer_payment (
    id bigint primary key,
    bank_code varchar(20) not null,
    destination_account varchar(40) not null,
    constraint fk_bank_transfer_payment
        foreign key (id) references payment(id)
);
```

Một CardPayment được lưu bằng hai hàng có cùng ID:

```text
payment
+----+--------+---------------------+
| id | amount | created_at          |
+----+--------+---------------------+
| 10 | 250.00 | 2026-11-09 10:00:00 |
+----+--------+---------------------+

card_payment
+----+-------------+-------------------+
| id | card_last4  | authorization_code|
+----+-------------+-------------------+
| 10 | 4242        | AUTH-001          |
+----+-------------+-------------------+
```

Cột `card_payment.id` vừa là primary key của bảng con, vừa là foreign key tới `payment.id`. Vì primary key là duy nhất, một hàng CardPayment chỉ tương ứng với một hàng Payment. Bảng con không tạo một ID độc lập khác cho cùng entity.

Nếu có một lớp entity trung gian trong hierarchy, ví dụ `OnlinePayment extends Payment`, thì bảng cho lớp trung gian cũng có thể xuất hiện. Một entity thuộc lớp lá có thể cần một hàng trong từng bảng entity dọc theo chuỗi kế thừa.

## 3. Ánh xạ JOINED bằng annotation

### 3.1. Lớp entity cha

```java
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;

@Entity
@Table(name = "payment")
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class Payment {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE,
                    generator = "payment_seq")
    @SequenceGenerator(
        name = "payment_seq",
        sequenceName = "payment_seq",
        allocationSize = 50
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

`@Inheritance(strategy = JOINED)` đặt ở entity root của hierarchy. Các lớp con là entity và kế thừa từ root. Thuộc tính khai báo ở lớp cha được lưu trong bảng cha; thuộc tính khai báo ở lớp con được lưu trong bảng con tương ứng.

Ví dụ dùng sequence để minh họa việc cấp ID trước khi insert. Chiến lược ID phụ thuộc database và provider. Với `IDENTITY`, provider có thể phải insert hàng cha trước để lấy ID rồi mới insert hàng con; điều đó có thể ảnh hưởng batching. Không có một generator tối ưu cho mọi database.

### 3.2. Lớp con CardPayment

```java
@Entity
@Table(name = "card_payment")
@PrimaryKeyJoinColumn(
    name = "id",
    referencedColumnName = "id"
)
public class CardPayment extends Payment {

    @Column(name = "card_last4", nullable = false, length = 4)
    private String cardLast4;

    @Column(name = "authorization_code", length = 80)
    private String authorizationCode;

    protected CardPayment() {
    }

    public CardPayment(
            BigDecimal amount,
            Instant createdAt,
            String cardLast4,
            String authorizationCode) {
        super(amount, createdAt);
        this.cardLast4 = cardLast4;
        this.authorizationCode = authorizationCode;
    }

    public String getCardLast4() {
        return cardLast4;
    }

    public String getAuthorizationCode() {
        return authorizationCode;
    }
}
```

### 3.3. Lớp con BankTransferPayment

```java
@Entity
@Table(name = "bank_transfer_payment")
@PrimaryKeyJoinColumn(
    name = "id",
    referencedColumnName = "id"
)
public class BankTransferPayment extends Payment {

    @Column(name = "bank_code", nullable = false, length = 20)
    private String bankCode;

    @Column(name = "destination_account",
            nullable = false, length = 40)
    private String destinationAccount;

    protected BankTransferPayment() {
    }

    public BankTransferPayment(
            BigDecimal amount,
            Instant createdAt,
            String bankCode,
            String destinationAccount) {
        super(amount, createdAt);
        this.bankCode = bankCode;
        this.destinationAccount = destinationAccount;
    }

    public String getBankCode() {
        return bankCode;
    }

    public String getDestinationAccount() {
        return destinationAccount;
    }
}
```

`@PrimaryKeyJoinColumn` chỉ rõ cột PK/FK ở bảng con và cột được tham chiếu ở bảng cha. Nếu bỏ annotation, provider áp dụng tên mặc định theo mapping; khai báo rõ giúp schema và migration dễ đọc hơn.

Các đoạn code trên là những entity snippet cần dependency Jakarta Persistence, provider (ví dụ Hibernate), cấu hình DataSource và các import tương ứng trong project Spring. Chúng không phải chương trình Java độc lập có thể chạy chỉ bằng `javac`.

## 4. Discriminator trong JOINED

Discriminator giúp provider nhận biết subtype của một hàng trong hierarchy. Với JOINED, discriminator column có thể được khai báo ở entity root:

```java
@Entity
@Table(name = "payment")
@Inheritance(strategy = InheritanceType.JOINED)
@DiscriminatorColumn(
    name = "payment_type",
    discriminatorType = DiscriminatorType.STRING,
    length = 30
)
public abstract class Payment {
    // id, amount, createdAt
}
```

Các subtype có thể chỉ định giá trị:

```java
@Entity
@Table(name = "card_payment")
@DiscriminatorValue("CARD")
public class CardPayment extends Payment {
    // card-specific fields
}

@Entity
@Table(name = "bank_transfer_payment")
@DiscriminatorValue("BANK_TRANSFER")
public class BankTransferPayment extends Payment {
    // transfer-specific fields
}
```

Discriminator không thay thế bảng con và PK/FK liên kết của JOINED. Nó là thông tin nhận dạng subtype; khả năng sử dụng, DDL và SQL chính xác phụ thuộc provider và cấu hình. Không nên giả định discriminator tự loại bỏ mọi JOIN cần thiết để đọc thuộc tính subtype.

Nếu schema đã được quản lý bằng migration, hãy bảo đảm migration tạo discriminator column và các giá trị tương ứng nếu mapping/provider cần nó. Không chỉ thêm annotation rồi giả định schema production đã thay đổi.

## 5. Repository và truy vấn đa hình

Vì Payment là entity root, repository có thể nhận kiểu cha:

```java
import org.springframework.data.jpa.repository.JpaRepository;

public interface PaymentRepository
        extends JpaRepository<Payment, Long> {
}
```

Tìm theo ID:

```java
Payment payment = paymentRepository.findById(id)
    .orElseThrow(() -> new EntityNotFoundException("Payment not found"));

if (payment instanceof CardPayment cardPayment) {
    String last4 = cardPayment.getCardLast4();
}
```

JPA thực hiện polymorphic query: truy vấn theo entity cha có thể trả về các instance thuộc subtype cụ thể. Provider phải xác định loại thực tế và nạp các thuộc tính tương ứng.

JPQL có thể lọc theo loại entity:

```java
@Query("select p from Payment p where type(p) = CardPayment")
List<Payment> findCardPayments();
```

Có thể dùng `TREAT` để truy cập thuộc tính subtype trong truy vấn, nếu cú pháp/provider hỗ trợ cho biểu thức đó:

```java
@Query("""
    select p
    from Payment p
    where treat(p as CardPayment).cardLast4 = :last4
    """)
List<Payment> findByCardLast4(@Param("last4") String last4);
```

Khi truy vấn một subtype cụ thể:

```java
List<CardPayment> cards = entityManager
    .createQuery(
        "select c from CardPayment c where c.cardLast4 = :last4",
        CardPayment.class
    )
    .setParameter("last4", "4242")
    .getResultList();
```

Không nên chỉ nhìn JPQL để kết luận chi phí. Hãy xem SQL provider sinh ra, vì một truy vấn theo root và một truy vấn theo subtype có thể tạo hình dạng JOIN khác nhau.

## 6. JOIN phát sinh ở đâu?

### 6.1. Tải một subtype cụ thể

Để dựng CardPayment đầy đủ, provider cần dữ liệu ở bảng payment và card_payment. SQL minh họa:

```sql
select
    p.id,
    p.amount,
    p.created_at,
    c.card_last4,
    c.authorization_code
from payment p
join card_payment c on c.id = p.id
where p.id = ?;
```

Đây là JOIN cần thiết để ghép thuộc tính kế thừa từ bảng cha với thuộc tính đặc thù ở bảng con.

### 6.2. Truy vấn entity root

Truy vấn Payment có thể trả về CardPayment và BankTransferPayment. Provider cần xác định subtype cho từng hàng. Một dạng SQL minh họa có thể dùng LEFT JOIN tới các bảng con:

```sql
select
    p.id,
    p.amount,
    p.created_at,
    c.card_last4,
    c.authorization_code,
    b.bank_code,
    b.destination_account
from payment p
left join card_payment c on c.id = p.id
left join bank_transfer_payment b on b.id = p.id;
```

Đây là sơ đồ để hình dung, không phải SQL cố định của mọi provider. Hibernate và các provider khác có thể dùng discriminator, CASE expression, join khác nhau hoặc tối ưu dựa trên query, dialect và phiên bản.

### 6.3. JOIN nhiều cấp kế thừa

Giả sử hierarchy là:

```text
Payment
  └── OnlinePayment
        └── CardPayment
```

Một CardPayment có thể cần hàng trong cả ba bảng. Khi đọc subtype đầy đủ, provider phải ghép các bảng tương ứng. Số cấp entity trong chuỗi kế thừa càng sâu, đường JOIN để lấy một entity hoàn chỉnh càng dài.

Không phải mọi truy vấn đều nhất thiết phải JOIN mọi bảng trong hierarchy. Nếu truy vấn chỉ cần thuộc tính ở root, provider có thể tạo SQL đơn giản hơn. SQL thực tế cần được quan sát trên provider và dialect đang dùng.

## 7. Chi phí ghi dữ liệu với JOINED

### 7.1. INSERT

Tạo một CardPayment thường cần:

1. Cấp phát ID.
2. INSERT hàng vào bảng payment.
3. INSERT hàng vào bảng card_payment với cùng ID.
4. Commit trong cùng transaction.

Ví dụ SQL minh họa:

```sql
insert into payment(id, amount, created_at)
values (10, 250.00, current_timestamp);

insert into card_payment(id, card_last4, authorization_code)
values (10, '4242', 'AUTH-001');
```

Một entity logic nhưng có thể cần nhiều lệnh INSERT. Với hierarchy nhiều cấp, số lệnh ghi có thể tăng theo số bảng trong chuỗi kế thừa.

### 7.2. UPDATE

Nếu chỉ đổi amount ở root, provider có thể chỉ cần cập nhật bảng payment. Nếu đổi cardLast4, provider cập nhật card_payment. Nếu thay đổi thuộc tính ở cả cha và con, có thể phát sinh UPDATE ở cả hai bảng.

```sql
update payment
set amount = 275.00
where id = 10;

update card_payment
set card_last4 = '1234'
where id = 10;
```

SQL cụ thể còn phụ thuộc dirty checking, dynamic update, batching và provider. JOINED không có nghĩa mọi lần update luôn phải ghi tất cả bảng.

### 7.3. DELETE

Khi xóa một subtype, provider cần xóa các hàng bảng con trước rồi xóa hàng ở bảng cha, trừ khi schema/cấu hình hỗ trợ một cơ chế khác:

```sql
delete from card_payment where id = 10;
delete from payment where id = 10;
```

Thứ tự này tránh vi phạm foreign key từ bảng con tới bảng cha. Xóa entity cha theo kiểu polymorphic cũng phải xử lý đúng hàng thuộc subtype.

Không nhầm việc provider xóa hàng trong hierarchy với `CascadeType.REMOVE` giữa các association entity. Inheritance hierarchy và association graph là hai quan hệ khác nhau.

## 8. Những nguồn chi phí JOINED

| Nguồn chi phí | Vì sao phát sinh | Tác động |
|---|---|---|
| JOIN khi đọc subtype | Phải ghép bảng cha và bảng con | Tăng chi phí truy vấn và xử lý kết quả |
| JOIN khi truy vấn root | Cần xác định và nạp subtype đa hình | SQL có thể nhiều LEFT JOIN hoặc logic phân loại |
| INSERT nhiều bảng | Một entity được lưu ở nhiều bảng | Tăng số lệnh ghi và round trip nếu không batching |
| UPDATE phân tán | Thuộc tính nằm ở các bảng khác nhau | Có thể phát sinh nhiều UPDATE |
| DELETE nhiều bảng | Phải xóa các hàng con và cha đúng thứ tự | Tăng số thao tác ghi |
| Hierarchy sâu | Mỗi cấp entity thêm một bảng | Số JOIN có thể tăng |
| Pagination và count | Query đa hình cần JOIN hoặc phân loại | Count query có thể nặng và kế hoạch thực thi phức tạp |
| Index và FK | Mỗi bảng con cần khóa liên kết với cha | Cần quản lý index, thống kê và kế hoạch JOIN |

JOIN có chi phí thực tế phụ thuộc số hàng, selectivity, index, cache, cardinality estimate, loại JOIN, network latency và execution plan. Không thể chỉ đếm số JOIN rồi kết luận hiệu năng.

## 9. Index và khóa ngoại trong hierarchy

Trong JOINED, cột PK ở bảng con cũng là FK tới PK bảng cha. PK thường đã tạo index, nên việc JOIN theo ID thường có đường truy cập tốt. Tuy nhiên, cần kiểm tra quy tắc index của database và các truy vấn thực tế.

Khuyến nghị:

- Bảo đảm PK của bảng cha có index.
- Bảo đảm PK của bảng con là đúng cột được dùng làm FK.
- Đặt tên FK rõ ràng và kiểm tra constraint thật trong schema.
- Index các cột lọc thường xuyên ở bảng subtype, ví dụ card_last4 hoặc bank_code khi có truy vấn phù hợp.
- Tránh thêm index tràn lan vì index tăng chi phí INSERT/UPDATE/DELETE và dung lượng.
- Chạy EXPLAIN/EXPLAIN ANALYZE với dữ liệu gần production để xem join order, scan type, row estimate và actual row count.

Ví dụ index cho truy vấn lọc theo subtype:

```sql
create index ix_card_payment_last4
on card_payment(card_last4);
```

Index này hữu ích khi truy vấn lọc theo card_last4 đủ chọn lọc và planner dùng nó. Nó không bảo đảm mọi truy vấn sẽ nhanh hơn; cần kiểm tra execution plan.

## 10. Pagination, projection và truy vấn báo cáo

Pagination trên entity root có thể phức tạp hơn khi provider phải JOIN subtype để phân loại và nạp entity. Count query có thể có cấu trúc khác với data query. Khi hierarchy lớn hoặc dữ liệu nhiều, hãy quan sát cả hai.

Một số hướng tối ưu:

- Nếu use case chỉ cần ID, loại payment và amount, cân nhắc DTO projection hoặc native query lấy đúng cột.
- Nếu use case chỉ làm việc với CardPayment, truy vấn subtype trực tiếp thay vì truy vấn root rồi lọc ở Java.
- Nếu cần dữ liệu báo cáo tổng hợp, cân nhắc query DTO/native SQL thay vì dựng toàn bộ entity graph.
- Tránh gọi repository nhiều lần trong vòng lặp gây N+1 ở các association khác.
- Kiểm tra count query khi dùng `Page<T>`; có thể dùng `Slice<T>` nếu không cần tổng số trang.
- Đảm bảo ORDER BY ổn định khi phân trang, ví dụ thêm ID làm tiêu chí phụ.
- Không dùng fetch join collection một cách tùy tiện với pagination; kết quả có thể nhân bản hàng và provider có thể phải phân trang trong bộ nhớ hoặc cảnh báo.

Ví dụ DTO projection:

```java
public record PaymentSummary(
    Long id,
    BigDecimal amount,
    Instant createdAt
) {}
```

Truy vấn projection JPQL:

```java
@Query("""
    select new com.example.payment.PaymentSummary(
        p.id, p.amount, p.createdAt
    )
    from Payment p
    order by p.createdAt desc, p.id desc
    """)
Page<PaymentSummary> findSummaries(Pageable pageable);
```

Đây là ví dụ JPQL projection cần package name và kiểu dữ liệu đúng với entity thực tế. Provider có thể tránh hydrate entity đầy đủ, nhưng vẫn cần kiểm tra SQL và JOIN mà query root yêu cầu trên provider cụ thể.

## 11. So sánh với SINGLE_TABLE và TABLE_PER_CLASS

| Tiêu chí | SINGLE_TABLE | JOINED | TABLE_PER_CLASS |
|---|---|---|---|
| Số bảng | Một | Một bảng cho mỗi entity class trong hierarchy | Một bảng cho mỗi concrete entity class |
| Cột chung | Một bản sao | Nằm ở bảng cha | Có thể lặp ở các bảng concrete |
| Cột subtype | Cột nullable trong bảng chung | Chỉ ở bảng subtype | Nằm trong bảng concrete |
| Đọc subtype | Thường ít JOIN | JOIN bảng cha và subtype | Đọc bảng subtype |
| Đọc root polymorphic | Một bảng, cần nhận diện subtype | Có thể JOIN các bảng con | Thường cần UNION |
| NOT NULL cho cột subtype | Khó áp theo subtype trong cùng bảng | Có thể đặt NOT NULL ở bảng subtype | Có thể đặt NOT NULL ở từng bảng |
| Ghi entity | Thường một bảng | Nhiều bảng theo hierarchy | Một bảng concrete |
| Chuẩn hóa | Ít chuẩn hóa cột subtype | Chuẩn hóa hơn | Lặp thuộc tính chung |

Chọn JOINED khi:

- Các subtype có nhiều thuộc tính riêng và muốn schema chuẩn hóa.
- Cần constraint phù hợp cho từng bảng subtype.
- Truy vấn theo subtype hoặc hierarchy không quá nhạy với chi phí JOIN.
- Domain thực sự là quan hệ kế thừa *is-a*.

Cân nhắc SINGLE_TABLE khi đọc đa hình thường xuyên, hierarchy nhỏ và chấp nhận cột nullable. Cân nhắc TABLE_PER_CLASS khi truy vấn concrete type chiếm ưu thế và provider/database xử lý UNION phù hợp. Đừng chọn chỉ dựa trên số bảng; cần benchmark với workload thật.

## 12. JOINED inheritance không phải association JoinTable

Hai annotation có tên dễ gây nhầm:

- `@Inheritance(strategy = InheritanceType.JOINED)`: ánh xạ kế thừa giữa entity cha và entity con.
- `@JoinTable`: định nghĩa bảng trung gian cho association giữa các entity, thường gặp ở many-to-many hoặc one-to-many một chiều.

Với JOINED, bảng con dùng PK/FK trỏ về bảng cha. Không cần tạo một bảng liên kết độc lập chỉ để thể hiện subtype.

Nếu một Payment có nhiều Tag, đó là association, có thể cần `@ManyToMany` và `@JoinTable`. Nhưng CardPayment kế thừa Payment là quan hệ is-a, dùng inheritance strategy.

Khi domain không phải quan hệ is-a rõ ràng, composition/association thường dễ hiểu và linh hoạt hơn inheritance. Ví dụ Payment có một PaymentMethod có thể là association tới entity riêng, thay vì tạo hierarchy chỉ để tái sử dụng vài trường.

## 13. Kiểm tra SQL và đo hiệu năng

Không tối ưu JOINED bằng cảm tính. Hãy đo trên database, provider và dữ liệu gần production.

Với Hibernate, có thể bật log SQL trong môi trường phát triển:

```properties
spring.jpa.show-sql=false
spring.jpa.properties.hibernate.format_sql=true

logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Bind parameter logging có thể làm lộ dữ liệu nhạy cảm; chỉ bật ở môi trường an toàn và tắt khi không cần. Cách đặt logger có thể thay đổi theo phiên bản Hibernate.

Đo các tình huống đại diện:

1. Tạo một entity subtype và đếm số INSERT.
2. Cập nhật thuộc tính ở root và ở subtype riêng.
3. Tải một subtype theo ID.
4. Tải danh sách entity root có nhiều subtype khác nhau.
5. Phân trang root và đo data query lẫn count query.
6. Lọc theo cột riêng của subtype.
7. Xóa entity subtype.
8. So sánh với mapping SINGLE_TABLE trên cùng dữ liệu và workload nếu đang cân nhắc đổi strategy.

Ghi nhận:

- Số SQL statement và số round trip.
- Tổng thời gian ở application và database.
- Số hàng thực tế được đọc, số hàng trả về.
- Execution plan, index scan/table scan và join algorithm.
- Connection pool wait, transaction duration và CPU.
- Tác động của cache và warm/cold run.

Hibernate statistics có thể giúp xem entity load, query count, second-level cache hit và flush. Bật statistics có overhead, vì vậy dùng đúng môi trường và so sánh có kiểm soát. Kết quả benchmark cần cùng dataset, index, concurrency, cache state và cấu hình.

## 14. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Bảng subtype không có hàng sau khi persist | Mapping hierarchy, transaction hoặc entity scan sai | Kiểm tra `@Entity`, `@Inheritance`, SQL log và transaction |
| FK subtype vi phạm khi insert | Hàng cha chưa được tạo hoặc ID mapping sai | Kiểm tra thứ tự insert, generator, PK join column và provider |
| Query root chậm bất thường | Polymorphic JOIN nhiều bảng hoặc dữ liệu lớn | Xem SQL/EXPLAIN, projection, truy vấn subtype riêng nếu hợp use case |
| Query subtype vẫn JOIN nhiều bảng | Cần lấy thuộc tính kế thừa ở root/ancestor | Kiểm tra projection và trường dữ liệu thực sự cần |
| Xóa entity bị lỗi FK | Hàng con chưa được xóa hoặc association khác đang tham chiếu | Xem thứ tự DELETE và FK constraint |
| Schema không có FK như annotation | Schema được quản lý bằng migration hoặc DDL generation tắt | Tạo FK trong migration và xác minh schema thật |
| Discriminator không khớp subtype | Dữ liệu discriminator hoặc cấu hình mapping sai | Kiểm tra giá trị discriminator, migration và provider |
| Pagination chậm | JOIN và count query phức tạp, thiếu index | Kiểm tra cả data/count query, dùng Slice/DTO khi phù hợp |
| Insert chậm khi IDENTITY | Cần lấy ID từ insert trước khi ghi bảng con | Đánh giá sequence phù hợp với database và batching |
| Chọn JOINED nhưng hierarchy quá sâu | Mỗi cấp thêm bảng và join path | Đơn giản hóa hierarchy hoặc cân nhắc chiến lược khác |

## 15. Checklist thiết kế và review

- [ ] Quan hệ giữa lớp cha và lớp con thực sự là *is-a*?
- [ ] Entity root đã khai báo `@Inheritance(strategy = JOINED)`?
- [ ] Mỗi subtype là entity và có bảng phù hợp?
- [ ] PK bảng subtype dùng chung ID và FK tham chiếu PK bảng cha?
- [ ] Tên bảng, PK join column và FK constraint nhất quán với migration?
- [ ] ID generator phù hợp database và workload insert nhiều bảng?
- [ ] Discriminator có được dùng không, giá trị có khớp dữ liệu và provider?
- [ ] Query root polymorphic và query subtype đã được kiểm tra SQL?
- [ ] Index hỗ trợ join/filter/order thực tế đã có?
- [ ] Pagination/count query đã được đo?
- [ ] Xóa subtype/root không vi phạm FK và không dựa nhầm vào association cascade?
- [ ] Có benchmark so sánh với SINGLE_TABLE hoặc TABLE_PER_CLASS khi cần?

## 16. Kết luận

JOINED lưu phần thuộc tính chung trong bảng cha và phần riêng trong bảng subtype. PK của bảng con đồng thời là FK tới PK bảng cha. Cách này chuẩn hóa schema, giữ constraint riêng cho subtype và hỗ trợ truy vấn polymorphic theo mô hình entity. Chi phí là nhiều thao tác ghi hơn và các truy vấn dựng entity đầy đủ có thể cần JOIN nhiều bảng.

Hãy dùng JOINED khi lợi ích về cấu trúc dữ liệu và constraint đáng giá hơn chi phí truy vấn. Tối ưu bằng cách truy vấn đúng subtype, projection đúng dữ liệu cần dùng, index theo điều kiện thực tế, đo execution plan và benchmark workload thật. Nếu JOINED trở thành nút thắt, so sánh lại với SINGLE_TABLE, TABLE_PER_CLASS hoặc composition dựa trên mô hình domain thay vì chỉ thêm index một cách tùy tiện.
