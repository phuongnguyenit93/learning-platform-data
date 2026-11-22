# Kế thừa thực thể với JOINED trong Hibernate

Trong Jakarta Persistence (JPA) và Hibernate ORM, `InheritanceType.JOINED` cho phép ánh xạ **một cây kế thừa entity Java** thành **nhiều bảng quan hệ**. Bảng của entity gốc chứa thuộc tính chung; mỗi entity lớp con có bảng lưu các thuộc tính riêng. Bản ghi con nối tới bản ghi cha bằng **cùng giá trị khóa chính** (*shared primary key*). Khi đọc, Hibernate ghép các bảng để tái tạo đúng đối tượng Java, kể cả khi truy vấn qua kiểu lớp cha.

Đây là một lựa chọn quan trọng trong thiết kế persistence: nó thể hiện quan hệ **“là một” (is-a)** trong domain, giữ các cột riêng của subtype tách biệt, nhưng làm tăng số bảng và phép join. Bài học dùng API `jakarta.persistence.*` và giải thích theo Hibernate ORM 6.x; tên bảng, SQL phát sinh và một số tối ưu có thể thay đổi theo phiên bản Hibernate, JDBC driver và `Dialect`.

## 1. Từ cây lớp Java đến cấu trúc bảng

Giả sử một hệ thống thanh toán có các hình thức:

- `CardPayment` lưu bốn số cuối của thẻ và mã giao dịch cổng thanh toán.
- `BankTransferPayment` lưu mã tham chiếu của ngân hàng.
- Cả hai đều là một `Payment`: có ID, số tiền, đơn vị tiền tệ và phiên bản cập nhật.

~~~text
                     Payment (abstract)
                     /                \
              CardPayment       BankTransferPayment
~~~

Nếu tất cả nằm trong một bảng, phần lớn cột riêng của subtype có thể bị null. Nếu mỗi subclass có bảng độc lập chứa tất cả cột chung, schema lặp lại và truy vấn đa hình phức tạp hơn. `JOINED` chia dữ liệu thành:

~~~mermaid
flowchart TD
    P["payments: id, amount_minor, currency_code, version"]
    C["card_payments: payment_id, card_last4, gateway_reference"]
    B["bank_transfer_payments: payment_id, bank_reference"]
    P -->|"id = payment_id (PK + FK)"| C
    P -->|"id = payment_id (PK + FK)"| B
~~~

**Một `CardPayment` là một entity, dù nó có hai hàng vật lý trong database.** Khóa `card_payments.payment_id` là khóa chính của bảng con đồng thời là khóa ngoại tới `payments.id`. Hibernate không tạo một ID thứ hai cho subclass.

### 1.1. Những điều JOINED giải quyết

| Nhu cầu | JOINED đáp ứng thế nào? |
| --- | --- |
| Chia sẻ thuộc tính giữa các subtype | Đặt thuộc tính chung ở bảng entity gốc. |
| Thuộc tính riêng theo từng loại | Lưu ở bảng tương ứng với subclass; có thể có ràng buộc cột riêng. |
| Tham chiếu đa hình từ entity khác | Association trỏ đến bảng gốc; kiểu thực tế có thể là bất kỳ subclass phù hợp. |
| Truy vấn mọi subtype | HQL/JPQL query trên entity gốc lấy cả entity thuộc các subclass. |
| Định danh thống nhất | ID được khai báo ở gốc và dùng lại làm PK/FK trong bảng con. |
| Phân biệt kiểu Java khi tải | Hibernate kết hợp metadata và dữ liệu bảng con; discriminator có thể dùng nhưng không bắt buộc ở mọi JOINED mapping. |

## 2. Khai báo đầy đủ với JPA annotation

### 2.1. Entity gốc: `Payment`

**Payment.java**

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Inheritance;
import jakarta.persistence.InheritanceType;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "payments")
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class Payment {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "amount_minor", nullable = false)
    private long amountMinor;

    @Column(name = "currency_code", length = 3, nullable = false)
    private String currencyCode;

    @Version
    private long version;

    protected Payment() {
        // Constructor không tham số dành cho JPA.
    }

    protected Payment(long amountMinor, String currencyCode) {
        this.amountMinor = amountMinor;
        this.currencyCode = currencyCode;
    }

    public Long getId() {
        return id;
    }

    public long getAmountMinor() {
        return amountMinor;
    }

    public String getCurrencyCode() {
        return currencyCode;
    }

    public long getVersion() {
        return version;
    }
}
~~~

Trong ví dụ, số tiền được lưu theo đơn vị nhỏ nhất bằng `long`, chỉ là lựa chọn nghiệp vụ minh họa. Có thể dùng `BigDecimal` với cấu hình precision/scale phù hợp.

Các điểm cần nhớ:

- `@Entity` trên `Payment` tạo **entity root có mapping bảng**. Dù Java class là `abstract`, bảng `payments` vẫn tồn tại.
- `@Inheritance(strategy = InheritanceType.JOINED)` đặt chiến lược cho toàn bộ cây entity.
- `@Id` và identifier generator nằm ở **gốc**; subclass kế thừa ID này.
- `@Version` có thể đặt ở gốc để quản lý optimistic locking cho entity thuộc mọi subclass.
- `GenerationType.IDENTITY` là lựa chọn đơn giản để minh họa SQL; dùng `SEQUENCE`/`AUTO` có thể phù hợp hơn với DBMS và yêu cầu JDBC batching cụ thể.

Không đặt thêm một `@Id` độc lập ở `CardPayment` chỉ vì subclass có bảng riêng: điều đó phá vỡ ý nghĩa **một định danh cho một entity**.

### 2.2. Entity con: `CardPayment`

**CardPayment.java**

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.PrimaryKeyJoinColumn;
import jakarta.persistence.Table;

@Entity
@Table(name = "card_payments")
@PrimaryKeyJoinColumn(
    name = "payment_id",
    referencedColumnName = "id"
)
public class CardPayment extends Payment {

    @Column(name = "card_last4", nullable = false, length = 4)
    private String cardLast4;

    @Column(name = "gateway_reference", nullable = false, length = 100)
    private String gatewayReference;

    protected CardPayment() {
    }

    public CardPayment(
            long amountMinor,
            String currencyCode,
            String cardLast4,
            String gatewayReference
    ) {
        super(amountMinor, currencyCode);
        this.cardLast4 = cardLast4;
        this.gatewayReference = gatewayReference;
    }

    public String getCardLast4() {
        return cardLast4;
    }

    public String getGatewayReference() {
        return gatewayReference;
    }

    public void changeGatewayReference(String newReference) {
        this.gatewayReference = newReference;
    }
}
~~~

`@PrimaryKeyJoinColumn` chỉ định cột ở bảng subclass nối tới primary key của bảng root:

~~~text
card_payments.payment_id  →  payments.id
~~~

Annotation này **không khai báo quan hệ `@OneToOne` giữa hai entity**. Hai bảng chứa các phần của cùng một entity được quản lý bằng `JOINED`. Khi tên khóa của subclass trùng theo quy tắc mặc định, có thể bỏ `@PrimaryKeyJoinColumn`; ở ví dụ này ta khai báo để dùng tên `payment_id` khác `id` của bảng gốc.

### 2.3. Entity con: `BankTransferPayment`

**BankTransferPayment.java**

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.PrimaryKeyJoinColumn;
import jakarta.persistence.Table;

@Entity
@Table(name = "bank_transfer_payments")
@PrimaryKeyJoinColumn(
    name = "payment_id",
    referencedColumnName = "id"
)
public class BankTransferPayment extends Payment {

    @Column(name = "bank_reference", nullable = false, length = 100)
    private String bankReference;

    protected BankTransferPayment() {
    }

    public BankTransferPayment(
            long amountMinor,
            String currencyCode,
            String bankReference
    ) {
        super(amountMinor, currencyCode);
        this.bankReference = bankReference;
    }

    public String getBankReference() {
        return bankReference;
    }
}
~~~

Các lớp con chỉ khai báo cột riêng. Những field gốc như `id`, `amountMinor`, `currencyCode`, `version` được kế thừa trong Java và lưu ở `payments`.

## 3. Schema vật lý và shared primary key

DDL minh họa theo cú pháp kiểu PostgreSQL hiện đại (cú pháp identity, kiểu cột và tên constraint có thể khác ở DBMS khác):

~~~sql
create table payments (
    id bigint generated by default as identity primary key,
    amount_minor bigint not null,
    currency_code varchar(3) not null,
    version bigint not null
);

create table card_payments (
    payment_id bigint primary key,
    card_last4 varchar(4) not null,
    gateway_reference varchar(100) not null,
    constraint fk_card_payment_parent
        foreign key (payment_id) references payments(id)
);

create table bank_transfer_payments (
    payment_id bigint primary key,
    bank_reference varchar(100) not null,
    constraint fk_transfer_payment_parent
        foreign key (payment_id) references payments(id)
);
~~~

Một `CardPayment` ID 1001 có thể có các dòng sau:

**payments**

| id | amount_minor | currency_code | version |
| ---: | ---: | --- | ---: |
| 1001 | 5999 | USD | 0 |
| 1002 | 125000 | VND | 0 |

**card_payments**

| payment_id | card_last4 | gateway_reference |
| ---: | --- | --- |
| 1001 | 4242 | gw-card-901 |

**bank_transfer_payments**

| payment_id | bank_reference |
| ---: | --- |
| 1002 | bank-trf-882 |

Như vậy, hai hàng liên quan đến ID 1001 mô tả **một `CardPayment`**. Không có hàng `bank_transfer_payments(1001)` cho giao dịch đó khi dữ liệu nhất quán.

### 3.1. PK và FK trên cùng một cột

Cột `card_payments.payment_id` có hai ràng buộc:

1. **Primary key**: không có hai hàng `card_payments` cùng ID.
2. **Foreign key**: khi constraint được thực thi, không thể có hàng `card_payments` trỏ đến `payments.id` không tồn tại.

Đó là nền tảng integrity của `JOINED`. Nhưng lưu ý: hai FK độc lập từ hai bảng con **không ngăn** ID 1001 xuất hiện ở cả `card_payments` và `bank_transfer_payments`. Chúng cũng không bắt buộc mọi hàng `payments` phải có hàng ở đúng một bảng con. Hibernate quản lý tính nhất quán của hierarchy qua ORM; nếu có nhiều đường ghi SQL bên ngoài, cần thêm quy trình và/hoặc ràng buộc phù hợp để bảo đảm một entity chỉ thuộc một subtype.

### 3.2. Lớp cha `abstract` có tạo bảng không?

**Có.** `@Entity` + `JOINED` khiến `Payment` có bảng gốc ngay cả khi không thể gọi `new Payment()`. `abstract` là quy tắc phía Java, không tự ngăn script SQL chèn một hàng `payments` không có subtype.

Điều này khác `@MappedSuperclass`: mapped superclass chia sẻ khai báo cột cho các lớp con nhưng không trở thành entity được quản lý độc lập, không có bảng riêng và không thể được dùng làm polymorphic query root kiểu `from Payment` nếu chỉ có `@MappedSuperclass`.

## 4. Persist một entity JOINED: ghi nhiều bảng trong một transaction

~~~java
EntityManager entityManager = entityManagerFactory.createEntityManager();

try {
    entityManager.getTransaction().begin();

    CardPayment card = new CardPayment(
            5999L,
            "USD",
            "4242",
            "gw-card-901"
    );
    entityManager.persist(card);

    entityManager.getTransaction().commit();

    System.out.println(card.getId());
} catch (RuntimeException ex) {
    if (entityManager.getTransaction().isActive()) {
        entityManager.getTransaction().rollback();
    }
    throw ex;
} finally {
    entityManager.close();
}
~~~

Đoạn code giả định một `EntityManagerFactory` đã được cấu hình và sử dụng **resource-local transactions**. Trong Spring hoặc JTA, transaction thường do container/framework quản lý; ví dụ này không đại diện cho mọi cơ chế transaction.

Khi lưu `CardPayment`, Hibernate cần ghi:

~~~sql
-- Bước 1: tạo phần chung; DB sinh id.
insert into payments (amount_minor, currency_code, version)
values (?, ?, ?);

-- Bước 2: dùng id đó để ghi phần riêng của subclass.
insert into card_payments (
    payment_id, card_last4, gateway_reference
)
values (?, ?, ?);
~~~

Hai `INSERT` có thể diễn ra vào thời điểm khác nhau tùy `flush` và identifier generation, nhưng chúng nằm trong cùng transaction ORM đang quản lý. Nếu bước ghi bảng con lỗi, ứng dụng cần rollback; không commit bảng cha riêng vì sẽ có thể để lại dữ liệu chưa đầy đủ.

### 4.1. Khóa chính được sinh một lần tại root

Với `GenerationType.IDENTITY`, database tạo ID ở `payments`. Hibernate lấy giá trị đó để chèn `card_payments.payment_id`. Subclass **không cần một generator khác**.

Nếu sử dụng `SEQUENCE`, có thể cấu hình sequence ở gốc. Một số DBMS/Hibernate setup cho phép chuẩn bị trước ID và cải thiện batching; ngược lại `IDENTITY` thường đòi hỏi `INSERT` để nhận ID, ảnh hưởng khả năng batch. Chọn dựa trên DBMS, tải ghi và migration, không áp dụng quy tắc “mọi JOINED đều cần IDENTITY”.

### 4.2. Cây ba cấp

Nếu mở rộng thành:

~~~text
Payment
  └── OnlinePayment
        └── CardPayment
~~~

và mỗi lớp là `@Entity` có bảng theo `JOINED`, một `CardPayment` có thể cần chèn vào **ba bảng** thuộc đường kế thừa. Hệ quả này càng quan trọng khi cây nhiều cấp hoặc yêu cầu ingest hàng loạt với throughput cao.

## 5. Đọc dữ liệu: join để dựng đúng kiểu đối tượng

### 5.1. Tải một subclass cụ thể

~~~java
CardPayment card =
        entityManager.find(CardPayment.class, 1001L);

System.out.println(card.getAmountMinor()); // Từ payments
System.out.println(card.getCardLast4());    // Từ card_payments
~~~

Một SQL minh họa:

~~~sql
select
    p.id,
    p.amount_minor,
    p.currency_code,
    p.version,
    c.card_last4,
    c.gateway_reference
from card_payments c
join payments p on p.id = c.payment_id
where c.payment_id = ?;
~~~

Hibernate lấy phần chung từ `payments`, phần riêng từ `card_payments` và tạo một `CardPayment` managed. Query trực tiếp subclass có thể chỉ cần các bảng trên đường kế thừa đó.

### 5.2. Truy vấn đa hình qua entity root

~~~java
List<Payment> payments = entityManager
        .createQuery(
            "select p from Payment p order by p.id",
            Payment.class
        )
        .getResultList();

for (Payment payment : payments) {
    if (payment instanceof CardPayment card) {
        System.out.println("Card " + card.getCardLast4());
    } else if (payment instanceof BankTransferPayment transfer) {
        System.out.println("Bank " + transfer.getBankReference());
    }
}
~~~

HQL/JPQL trên `Payment` có thể trả về mọi subclass trong hierarchy. Nếu phải nạp đầy đủ các loại, một dạng SQL có thể là:

~~~sql
select
    p.id,
    p.amount_minor,
    p.currency_code,
    p.version,
    c.card_last4,
    c.gateway_reference,
    b.bank_reference
from payments p
left join card_payments c on c.payment_id = p.id
left join bank_transfer_payments b on b.payment_id = p.id
order by p.id;
~~~

SQL này minh họa **tại sao query đa hình có thể tốn nhiều join**. Hibernate có thể thay đổi cách tạo SQL và cách phân biệt subclass, ví dụ thêm biểu thức `CASE`, tùy mapping và phiên bản. Không được coi số và thứ tự các `JOIN` trong ví dụ là cam kết cố định.

### 5.3. Lọc theo loại bằng `TYPE` và truy cập field riêng với `TREAT`

Khi chỉ cần CardPayment, có thể query trực tiếp:

~~~java
List<CardPayment> cards = entityManager
        .createQuery(
            "select c from CardPayment c " +
            "where c.gatewayReference = :reference",
            CardPayment.class
        )
        .setParameter("reference", "gw-card-901")
        .getResultList();
~~~

Nếu cần kiểu trả về `Payment` nhưng chỉ lấy subtype thẻ:

~~~java
List<Payment> cardsAsPayments = entityManager
        .createQuery(
            "select p from Payment p where type(p) = CardPayment",
            Payment.class
        )
        .getResultList();
~~~

JPQL cung cấp `TYPE` để xét entity type. `TREAT` có thể dùng để downcast trong truy vấn:

~~~java
List<Payment> matching = entityManager
        .createQuery(
            "select p from Payment p " +
            "where treat(p as CardPayment).cardLast4 = :last4",
            Payment.class
        )
        .setParameter("last4", "4242")
        .getResultList();
~~~

Đây là downcast **ở mức truy vấn**, không phải ép kiểu Java sau khi lấy mọi row về RAM. Hibernate quyết định phần bảng subtype nào cần tham gia SQL tương ứng.

### 5.4. JOINED không phải fetch join của association

Join `payments` với `card_payments` là phép nối hai phần của **một entity**. Nó không đồng nghĩa với việc các association bên trong `CardPayment`, ví dụ `@ManyToOne Merchant` hay `@OneToMany Refund`, đều được eager fetch. Những association đó có fetch plan riêng và có thể gây N+1 query khi truy cập tuần tự.

## 6. Quan hệ tới lớp gốc: một FK cho mọi subtype

Một `Invoice` có thể tham chiếu một khoản thanh toán bất kỳ:

~~~java
@Entity
@Table(name = "invoices")
public class Invoice {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "payment_id", nullable = false)
    private Payment payment;

    protected Invoice() {}

    public Payment getPayment() {
        return payment;
    }
}
~~~

Đây là ví dụ độc lập; cần các import từ `jakarta.persistence.*`. FK của bảng `invoices` tham chiếu bảng **gốc**:

~~~sql
create table invoices (
    id bigint primary key,
    payment_id bigint not null,
    constraint fk_invoice_payment
        foreign key (payment_id) references payments(id)
);
~~~

Khi tải `Invoice.payment`, entity thực có thể là `CardPayment` hoặc `BankTransferPayment`. Caller chỉ cần hợp đồng của lớp cha để xử lý hành vi chung. Nếu ứng dụng thiết kế một FK cho thẻ và một FK cho chuyển khoản, nó phải tự kiểm soát “chỉ một FK được điền”; sử dụng hierarchy có root entity giúp biểu diễn tốt hơn quan hệ is-a.

Nếu association cố tình chỉ cho phép `CardPayment`, target type và integrity cần thiết kế theo subtype tương ứng. Không suy luận rằng mọi FK tới root sẽ tự bảo đảm business rule “chỉ được thanh toán bằng thẻ”.

## 7. Discriminator: tùy chọn với JOINED

Với `SINGLE_TABLE`, các subtype nằm chung một bảng nên cần cơ chế phân biệt loại. Với `JOINED`, **sự tồn tại của hàng ở bảng con giúp Hibernate suy ra subtype**, vì vậy một mapping JOINED bình thường **không bắt buộc tự khai báo `@DiscriminatorColumn`**.

Một biến thể khác là lưu loại payment ngay tại root:

~~~java
@Entity
@Table(name = "payments")
@Inheritance(strategy = InheritanceType.JOINED)
@DiscriminatorColumn(
    name = "payment_kind",
    discriminatorType = DiscriminatorType.STRING,
    length = 24
)
public abstract class Payment {
    // Các thuộc tính gốc
}

@Entity
@Table(name = "card_payments")
@DiscriminatorValue("CARD")
public class CardPayment extends Payment {
    // Thuộc tính thẻ
}

@Entity
@Table(name = "bank_transfer_payments")
@DiscriminatorValue("BANK")
public class BankTransferPayment extends Payment {
    // Thuộc tính chuyển khoản
}
~~~

Đây là **phương án thay thế** cho những khai báo ở phần 2. Đoạn rút gọn không phải toàn bộ ba source file chạy độc lập. Khi dùng phương án này, schema cần cột `payment_kind` và dữ liệu phải giữ giá trị tương ứng với subtype. Hibernate có hỗ trợ discriminator cho JOINED, nhưng hành vi mặc định, cách xử lý và SQL có thể thay đổi theo phiên bản/provider.

Cột discriminator **không thay thế** primary-key join hay foreign-key constraint. Một hàng `payments` ghi `payment_kind = 'CARD'` nhưng lại có hàng `bank_transfer_payments` là dữ liệu mâu thuẫn. DB FK đơn giản không tự so sánh enum discriminator với bảng subtype; ứng dụng cần ngăn dữ liệu sai ở mọi đường ghi, và có thể phải dùng thêm ràng buộc/trigger nếu có ghi trực tiếp bằng SQL.

Không thêm discriminator chỉ vì đã quen với `SINGLE_TABLE`: hãy xác định lợi ích thực tế về schema, tương thích hệ thống hay truy vấn.

## 8. Thao tác UPDATE, DELETE và optimistic locking

### 8.1. Thay đổi thuộc tính subclass

~~~java
CardPayment card = entityManager.find(CardPayment.class, paymentId);
card.changeGatewayReference("gw-card-902");
~~~

Hibernate dirty-check entity managed và phát DML tùy mapping. Mặc dù field `gatewayReference` nằm ở `card_payments`, `@Version` nằm ở bảng `payments`: Hibernate cần bảo vệ optimistic locking trên toàn entity, không chỉ một nửa của nó.

SQL có thể bao gồm cập nhật thuộc tính riêng và câu lệnh kiểm tra/tăng version ở bảng root:

~~~sql
-- Phác họa logic; thứ tự và số statement thực tế không cố định:
update card_payments
set gateway_reference = ?
where payment_id = ?;

update payments
set version = ?
where id = ? and version = ?;
~~~

Không dùng SQL minh họa này để thay thế cách Hibernate quản lý version. Nếu hai transaction sửa cùng entity đồng thời, transaction đến sau có thể gặp `OptimisticLockException` hoặc exception Hibernate tương ứng. Khi dùng native SQL để sửa bảng con, cần xử lý version theo cùng chính sách ứng dụng nếu muốn tránh bypass optimistic locking.

### 8.2. Xóa một entity lớp con

~~~java
CardPayment card = entityManager.find(CardPayment.class, paymentId);
entityManager.remove(card);
~~~

Về mặt vật lý, xóa một entity JOINED thường cần xóa các hàng thuộc nó ở bảng con và bảng gốc, với thứ tự tuân thủ FK:

~~~sql
delete from card_payments where payment_id = ?;
delete from payments where id = ?;
~~~

Hibernate có thể có điều kiện version và thêm thao tác liên quan tới association/cascade tùy mapping. Nếu `invoices` còn FK tới `payments.id`, DB có thể ngăn xóa parent, vì vậy phải thiết kế chính sách giữ lịch sử thanh toán và hành vi xóa trước khi sử dụng remove.

**`CascadeType.REMOVE` không phải cơ chế gắn hai hàng `payments` và `card_payments`.** Hibernate đã biết chúng là một entity theo metadata JOINED; cascade chỉ áp dụng đối với những entity khác được tham chiếu bởi association.

### 8.3. Bulk HQL và native SQL

Bulk update/delete có thể được Hibernate chuyển thành nhiều statement khi hierarchy trải trên nhiều bảng. Chúng không có cùng semantics persistence context, callback và optimistic locking như thao tác từng managed entity. Sau bulk DML, các entity đang managed có thể bị stale.

Native SQL như:

~~~sql
delete from payments where id = 1001;
~~~

không nhất thiết xóa được các hàng subclass: tùy FK, lệnh có thể bị từ chối hoặc DB áp dụng `ON DELETE` đã cấu hình. Không dùng SQL chỉ tác động root khi muốn thay thế `entityManager.remove(subclass)` mà chưa thiết kế toàn bộ phụ thuộc.

## 9. Đánh đổi hiệu năng của JOINED

| Trường hợp | Chi phí thường gặp | Hướng đánh giá |
| --- | --- | --- |
| Lưu một subclass | Chèn bảng root và bảng subclass (nhiều cấp thì nhiều bảng) | Số statement/transaction, ID generator, batch support |
| Tải một subclass theo ID | Join root với các bảng trên đường kế thừa | Index trên shared PK/FK, execution plan |
| Query tất cả root `Payment` | Có thể outer join nhiều bảng subclass để nhận diện/nạp loại | Số subtype, width, pagination, filter |
| Query chỉ một subtype | Có thể tránh bảng của những subtype khác | Query cụ thể, execution plan thực tế |
| Lọc theo cột chung | Dữ liệu nằm ở bảng root | Projection, index trên cột root, SQL Hibernate sinh |
| Lọc theo cột subclass | Cần truy cập bảng subclass | Index theo điều kiện lọc, `TYPE`/`TREAT` |
| Cập nhật field subclass | Có thể cập nhật thêm version ở root | Locking, contention, số DML |
| Xóa subclass | Nhiều bảng và các FK phụ thuộc | Quy tắc xóa, transaction, retention |

### 9.1. Cây kế thừa rộng làm tăng join

Một truy vấn `select p from Payment p` trên hierarchy có 20 subtype có thể cần nhiều phép join, dù caller chỉ hiển thị `id` và `amountMinor`. Hibernate và optimizer có thể giảm một phần chi phí tùy projection; kết quả không thể khẳng định chỉ dựa trên mapping.

Nên cân nhắc:

- Query trực tiếp subtype khi nghiệp vụ biết rõ loại.
- Dùng DTO/projection nếu chỉ cần vài cột; kiểm tra SQL thay vì giả định Hibernate luôn chỉ đọc bảng root.
- Phân trang và chỉ nạp chi tiết khi cần.
- Xây index cho điều kiện lọc ở root và subtype; shared PK ở child đã phục vụ join chính, nhưng cột như `gateway_reference` có thể cần index riêng.
- Đo `EXPLAIN`/query plan, DB CPU/I/O và latency dưới tập dữ liệu thật.
- Giữ độ sâu và số nhánh kế thừa phù hợp, tránh thêm subtype chỉ để tái sử dụng vài method Java.

### 9.2. JOINED không giải quyết N+1 association

Phép join root/subclass là chi phí **inheritance loading**. Nếu mỗi payment có một `merchant` lazy và khi duyệt 100 payment ứng dụng lại gọi `getMerchant()`, có thể phát sinh N+1 queries do association. Dùng fetch plan/DTO/entity graph hoặc batch fetching phù hợp cho association; chỉ thay inheritance strategy chưa chắc giải quyết N+1.

### 9.3. Chi phí ghi và `IDENTITY`

Trong ví dụ `IDENTITY` khiến DB sinh ID ở root; Hibernate phải có ID đó để chèn child. Việc chèn hàng loạt JOINED entity có thể chịu tác động của số bảng, khả năng gom statement cùng loại, thứ tự insert và JDBC batching. Nếu throughput quan trọng, đo với `SEQUENCE` hoặc generator phù hợp DBMS thay vì chỉ tối ưu câu `SELECT`.

## 10. So sánh với các chiến lược khác

| Mô hình | Bảng | Polymorphic query qua root entity? | Ưu điểm | Đánh đổi |
| --- | --- | --- | --- | --- |
| `SINGLE_TABLE` | Một bảng cho cả hierarchy | Có | Dữ liệu của một entity trong một hàng; tránh join inheritance | Cột đặc thù thường nullable; constraint theo subtype khó hơn |
| **`JOINED`** | Root + bảng mỗi subclass, nối bằng PK | Có | Schema chuẩn hóa; ràng buộc cột theo subtype | Ghi nhiều bảng và query đa hình có join |
| `TABLE_PER_CLASS` | Mỗi concrete entity có bảng riêng chứa cả cột kế thừa | Có, nhưng thường dùng `UNION` hoặc dạng tương đương | Không cần nối root/subclass để đọc subtype | Lặp cột chung, truy vấn đa hình và ID generation phức tạp hơn |
| `@MappedSuperclass` | Không tạo bảng cho mapped superclass | **Không** theo tên mapped superclass | Tái sử dụng field và mapping Java | Không có root entity đa hình |
| `@SecondaryTable` | Một entity chia dữ liệu qua nhiều bảng | Không tạo thêm subtype | Tách cột của **một entity type** | Không biểu diễn kế thừa is-a |
| Composition + association | Các entity/value object liên kết | Tùy thiết kế | Quan hệ và vòng đời linh hoạt | Không có polymorphism theo subclass mặc định |

### 10.1. Phân biệt với `@MappedSuperclass`

~~~java
@MappedSuperclass
public abstract class AuditedEntity {
    @Column(name = "created_at")
    protected java.time.Instant createdAt;
}

@Entity
public class Product extends AuditedEntity {
    @Id
    private Long id;
}
~~~

`AuditedEntity` chỉ cung cấp mapping dùng chung, không có bảng và không phải entity query root. Nếu mục tiêu chỉ là chia sẻ `createdAt`, đừng tạo hierarchy JOINED với bảng riêng chỉ để tái sử dụng mã.

### 10.2. Phân biệt với `@SecondaryTable`

~~~java
@Entity
@Table(name = "orders")
@SecondaryTable(
    name = "order_audit",
    pkJoinColumns = @PrimaryKeyJoinColumn(name = "order_id")
)
public class Order {
    @Id
    private Long id;

    @Column(table = "order_audit")
    private String auditSource;
}
~~~

Ở đây chỉ có **một loại entity Order**, nhưng cột nằm ở hai bảng. Không có `CardPayment extends Payment` hay subclass nào. Nếu ứng dụng cần subtype thực sự, `JOINED` phản ánh mô hình tốt hơn; nếu chỉ muốn tách nhóm cột, `@SecondaryTable` có thể phù hợp.

### 10.3. Khi nào nên chọn composition?

Nếu phần “thẻ”, “chuyển khoản”, “ngân hàng” có vòng đời riêng, được thay đổi độc lập hoặc đến từ hệ thống bên ngoài, mô hình composition có thể tự nhiên hơn inheritance. Đừng dùng `JOINED` chỉ vì hai đối tượng có vài thuộc tính trùng nhau. Nó phù hợp khi có một **identity, lifecycle và hợp đồng type chung** thật sự.

## 11. Migration từ SINGLE_TABLE hoặc schema legacy sang JOINED

Giả sử hiện tại `payments` chứa mọi cột:

~~~text
payments
    id, kind, amount_minor, currency_code, version,
    card_last4, gateway_reference, bank_reference
~~~

Đổi annotation thành `JOINED` **không tự di chuyển** `card_last4` và `bank_reference` sang bảng mới. Cần migration dữ liệu:

1. Kiểm kê các loại payment và dữ liệu đặc thù; xác nhận `kind` hợp lệ, các trường bắt buộc không bị thiếu.
2. Tạo bảng subclass với shared PK/FK, constraint và index thích hợp.
3. Backfill dữ liệu riêng theo từng loại.
4. Kiểm tra mỗi root payment có đúng subtype mong đợi; kiểm tra PK/FK và những hàng sai.
5. Đồng bộ đường ghi trong thời gian triển khai để tránh dữ liệu mới chỉ xuất hiện ở schema cũ hoặc schema mới.
6. Triển khai mapping JOINED và đối chiếu SQL ghi/đọc.
7. Chỉ loại bỏ cột cũ sau khi chuyển đổi ổn định, có kế hoạch rollback/khôi phục.

SQL backfill chỉ minh họa, giả định bảng mới rỗng và dữ liệu nguồn đã được làm sạch:

~~~sql
insert into card_payments (
    payment_id, card_last4, gateway_reference
)
select id, card_last4, gateway_reference
from payments
where kind = 'CARD';

insert into bank_transfer_payments (
    payment_id, bank_reference
)
select id, bank_reference
from payments
where kind = 'BANK';
~~~

Đối với database lớn, cần xử lý lock, batch/chunking, dữ liệu phát sinh trong quá trình backfill và idempotency khi chạy lại script.

### 11.1. Kiểm tra các hàng root có số subtype sai

Với **chỉ hai subclass** ở ví dụ và nghiệp vụ yêu cầu root luôn có **đúng một** subtype:

~~~sql
select p.id
from payments p
left join card_payments c
       on c.payment_id = p.id
left join bank_transfer_payments b
       on b.payment_id = p.id
where
    (case when c.payment_id is null then 0 else 1 end
   + case when b.payment_id is null then 0 else 1 end) <> 1;
~~~

Truy vấn sẽ tìm root có **0 hoặc 2** hàng subclass. Nếu có thêm subclass, hoặc root là concrete entity có thể tồn tại độc lập, điều kiện phải đổi cho đúng domain.

Kiểm tra hướng ngược khi chưa có FK vật lý:

~~~sql
select c.payment_id
from card_payments c
left join payments p on p.id = c.payment_id
where p.id is null;
~~~

Khi FK thực sự được thực thi, trường hợp child không có parent bị chặn bởi DB. Với dữ liệu legacy trước khi áp constraint, câu kiểm kê vẫn có ích.

### 11.2. Hibernate không phải công cụ migration dữ liệu

`hibernate.hbm2ddl.auto=update` không bảo đảm sẽ tách cột, backfill, xác nhận subtype đúng hoặc bảo toàn toàn bộ index/constraint khi đổi inheritance strategy. Hãy dùng công cụ migration có version, chẳng hạn Flyway/Liquibase, rồi có thể dùng schema validation của Hibernate như lớp kiểm tra bổ sung. Schema validation **không chứng minh** mọi invariant cross-table hoặc dữ liệu lịch sử đều hợp lệ.

## 12. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Hibernate báo không có cột `payment_id` | Tên `@PrimaryKeyJoinColumn` khác schema | Đối chiếu DDL, mapping, naming strategy và migration |
| Không tải đúng subclass | Root thiếu child, có nhiều child hoặc discriminator lệch | Kiểm kê dữ liệu và mọi đường ghi SQL |
| `ConstraintViolationException` khi persist | Trùng PK child, FK chưa có parent hoặc giá trị riêng không hợp lệ | Xem constraint name, transaction và dữ liệu |
| Query `from Payment` chậm | Nhiều phép join cho subclass, thiếu index/giới hạn | Quan sát SQL và execution plan, dùng projection khi thích hợp |
| Đổi trường con nhưng SQL cập nhật root | `@Version` đặt ở root cho optimistic locking | Kiểm tra versioning, đừng xem ngay là truy vấn thừa |
| Xóa parent bằng SQL không thành công | FK từ child hoặc invoice giữ root | Thiết kế delete/retention theo quan hệ đầy đủ |
| `@MappedSuperclass` không query được | Superclass không là entity | Dùng root `@Entity` nếu cần query/association đa hình |
| Lớp con có `@Id` riêng dẫn đến mapping sai | Nhầm shared PK với entity độc lập | Khai báo ID ở root; child kế thừa |
| Thêm subclass nhưng query/DDL lỗi | Entity chưa được đăng ký hoặc bảng mới chưa migration | Đồng bộ bootstrap, schema và code truy vấn |

### 12.1. Quan sát SQL do Hibernate phát sinh

Trong môi trường phát triển, logger `org.hibernate.SQL` ở mức `DEBUG` có thể giúp nhìn statement; Hibernate 6 có logger `org.hibernate.orm.jdbc.bind` ở mức `TRACE` để điều tra tham số JDBC nếu thật sự cần. Tên cấu hình logger cụ thể phụ thuộc logging framework. Không bật bind trace rộng rãi khi có dữ liệu thanh toán nhạy cảm.

Khi đo chi phí JOINED, cần đọc **SQL thực tế**, số bảng có trong plan, số row đã đọc, latency và số statement mỗi transaction. Không kết luận hiệu năng chỉ từ số annotation hoặc số subclass Java.

## 13. Bài tập suy luận

**Bài 1.** Một `CardPayment` có ID 27. Những hàng vật lý nào phải có trong sơ đồ bảng JOINED hai cấp? Vì sao không tạo thêm `cardId` bằng một generator riêng?

**Bài 2.** Một ID xuất hiện ở `payments` nhưng không xuất hiện ở bảng con nào, trong khi `Payment` là abstract. FK từ child tới root có tự phát hiện thiếu subtype không? Cần đối chiếu dữ liệu thế nào?

**Bài 3.** Một màn hình liệt kê hàng triệu payment và chỉ hiển thị `id`, `amountMinor`. Nên query entity đầy đủ hay dùng projection và kiểm tra SQL? Điều gì làm join inheritance trở nên đáng chú ý?

**Bài 4.** Cùng một root ID có mặt ở cả bảng thẻ và bảng chuyển khoản. PK/FK trên mỗi bảng con có ngăn tình trạng này không? Nếu không, cần kiểm soát integrity ở đâu?

**Bài 5.** Khi đổi từ `SINGLE_TABLE` sang `JOINED`, có thể chỉ sửa annotation rồi chạy `ddl-auto=update` để chuyển dữ liệu không? Những bước migration cần thiết là gì?

Gợi ý: (1) hai hàng có ID thống nhất; (2) không, FK hướng child→parent không bắt buộc phải có child; (3) projection và đo plan giúp tránh nạp không cần thiết; (4) hai bảng con độc lập có thể cùng chứa một ID nếu không có bảo vệ bổ sung; (5) cần tạo bảng, backfill, kiểm kê, quản lý traffic cutover rồi dọn schema.

## 14. Tài liệu và nguyên tắc thiết kế

- [Hibernate ORM 6.6 User Guide – entity inheritance](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html#entity-inheritance): các chiến lược SINGLE_TABLE, JOINED, TABLE_PER_CLASS.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/): các hợp đồng `@Entity`, `@Inheritance`, `@PrimaryKeyJoinColumn`, `@DiscriminatorColumn`, `@MappedSuperclass` và query đa hình.
- [Hibernate ORM Documentation](https://hibernate.org/orm/documentation/): chọn user guide, Javadoc và migration guide cho đúng phiên bản Hibernate đang dùng.

**Quy tắc cốt lõi:** `JOINED` lưu **một entity** trên **nhiều bảng có cùng primary key**. Nó phù hợp khi domain có subtype bền vững, cần polymorphism và muốn chuẩn hóa thuộc tính riêng. Đổi lại, mỗi thao tác ghi và truy vấn đa hình có thể cần nhiều statement/join hơn. Thiết kế shared PK/FK chính xác, giữ ranh giới transaction rõ ràng và kiểm tra SQL cùng schema thực tế sẽ giúp dùng `JOINED` có chủ đích.
