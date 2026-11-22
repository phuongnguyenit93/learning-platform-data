# Lựa chọn kế thừa Entity hoặc kết hợp đối tượng

## Mục tiêu

Sau bài học này, bạn có thể:

- Phân biệt quan hệ “is-a” của kế thừa với quan hệ “has-a” của kết hợp đối tượng.
- Hiểu bốn cách mô hình hóa phổ biến trong JPA: entity inheritance, `@MappedSuperclass`, `@Embeddable` và entity association.
- Chọn chiến lược `SINGLE_TABLE`, `JOINED` hoặc `TABLE_PER_CLASS` theo cấu trúc dữ liệu và truy vấn.
- Nhận biết tác động của discriminator, join, nullability, cascade và vòng đời entity.
- Thiết kế mô hình có thể mở rộng mà không tạo cây kế thừa cứng nhắc.
- Kiểm thử mapping, truy vấn đa hình và quan hệ giữa các đối tượng.

## 1. Kế thừa và kết hợp đối tượng khác nhau thế nào?

Kế thừa mô tả quan hệ “là một loại của” (is-a). Ví dụ:

- Car là một loại Vehicle.
- CreditCardPayment là một loại PaymentMethod.
- SavingsAccount là một loại BankAccount.

Kết hợp đối tượng mô tả quan hệ “có một” hoặc “sử dụng một” (has-a/uses-a). Ví dụ:

- Customer có một Address.
- PurchaseOrder có nhiều OrderLine.
- Payment có một PaymentMethod.
- Product có một PricingPolicy.

Trong thiết kế hướng đối tượng, kế thừa cho phép lớp con nhận trạng thái và hành vi từ lớp cha. Kết hợp đối tượng cho phép một đối tượng chứa hoặc tham chiếu đến các thành phần khác, rồi phối hợp hành vi thông qua các collaborator.

JPA cung cấp nhiều cách ánh xạ những cấu trúc này xuống database. Không phải mọi quan hệ kế thừa Java đều cần dùng entity inheritance, và không phải mọi trường dữ liệu dùng chung đều cần một entity cha.

### Ví dụ về lựa chọn mô hình

Giả sử hệ thống bán hàng có nhiều loại phương thức thanh toán:

- CreditCardPayment có số token thẻ và mã tham chiếu giao dịch.
- BankTransferPayment có mã ngân hàng và tài khoản nhận.
- CashPayment có thể có thông tin thu ngân.

Nếu mọi loại thanh toán đều có chung identity, vòng đời và hành vi của PaymentMethod, đồng thời ứng dụng thường truy vấn “tất cả phương thức thanh toán”, entity inheritance có thể hợp lý.

Ngược lại, nếu Customer có địa chỉ giao hàng, địa chỉ là một giá trị thuộc Customer, không có vòng đời hay identity độc lập, thì `@Embeddable` phù hợp hơn.

Nếu Customer có một Profile có thể được quản lý, chia sẻ hoặc truy vấn độc lập, dùng association tới một entity khác sẽ rõ nghĩa hơn.

## 2. Entity inheritance trong JPA

Entity inheritance cho phép một entity class kế thừa từ entity class khác. JPA hỗ trợ ba chiến lược lưu trữ chính:

1. `SINGLE_TABLE`: toàn bộ hierarchy nằm trong một bảng.
2. `JOINED`: lớp cha và từng lớp con có bảng riêng, nối bằng khóa chính.
3. `TABLE_PER_CLASS`: mỗi concrete entity class có bảng riêng, lặp lại các cột kế thừa.

`@Inheritance` được khai báo ở root entity của hierarchy. Nếu không chỉ định strategy, JPA mặc định dùng `SINGLE_TABLE`.

### 2.1. SINGLE_TABLE

Mọi entity trong hierarchy được lưu trong cùng một bảng. Một cột discriminator phân biệt loại entity.

Ví dụ:

~~~java
package com.example.fleet;

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

@Entity
@Table(name = "vehicles")
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(
    name = "vehicle_type",
    discriminatorType = DiscriminatorType.STRING
)
public abstract class Vehicle {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 100)
    private String manufacturer;

    protected Vehicle() {
    }

    protected Vehicle(String manufacturer) {
        this.manufacturer = manufacturer;
    }

    public Long getId() {
        return id;
    }

    public String getManufacturer() {
        return manufacturer;
    }
}
~~~

Lớp con:

~~~java
@Entity
@DiscriminatorValue("CAR")
public class Car extends Vehicle {

    @Column(name = "seat_count")
    private Integer seatCount;

    protected Car() {
    }

    public Car(String manufacturer, int seatCount) {
        super(manufacturer);
        this.seatCount = seatCount;
    }

    public Integer getSeatCount() {
        return seatCount;
    }
}
~~~

~~~java
@Entity
@DiscriminatorValue("TRUCK")
public class Truck extends Vehicle {

    @Column(name = "load_capacity_kg")
    private Integer loadCapacityKg;

    protected Truck() {
    }

    public Truck(String manufacturer, int loadCapacityKg) {
        super(manufacturer);
        this.loadCapacityKg = loadCapacityKg;
    }

    public Integer getLoadCapacityKg() {
        return loadCapacityKg;
    }
}
~~~

Bảng `vehicles` có thể chứa dữ liệu như sau:

| id | vehicle_type | manufacturer | seat_count | load_capacity_kg |
|---:|---|---|---:|---:|
| 1 | CAR | Toyota | 5 | NULL |
| 2 | TRUCK | Volvo | NULL | 12000 |

**Ưu điểm**

- Truy vấn toàn bộ hierarchy thường không cần join.
- Đọc một entity con có thể lấy dữ liệu từ một bảng.
- Cấu trúc đơn giản, dễ hiểu và thường có hiệu năng tốt cho truy vấn đa hình.

**Hạn chế**

- Các cột chỉ áp dụng cho một subtype thường phải cho phép NULL.
- Bảng có thể rộng khi số subtype và số thuộc tính riêng tăng.
- Khó áp dụng NOT NULL đơn giản cho cột chỉ bắt buộc ở một subtype.
- Các subtype có thể làm bảng chứa nhiều cột ít được sử dụng.

Nếu cần bảo đảm thuộc tính riêng theo subtype, có thể dùng CHECK constraint trong migration. Ví dụ, khi `vehicle_type = 'CAR'`, `seat_count` phải có giá trị; khi là TRUCK, `load_capacity_kg` phải có giá trị. Đừng chỉ dựa vào validation ở Java nếu database cũng cần bảo vệ dữ liệu.

### 2.2. JOINED

Bảng root lưu các thuộc tính chung. Mỗi lớp con có bảng riêng, dùng cùng khóa chính làm khóa ngoại tham chiếu về bảng cha.

Ví dụ:

~~~java
@Entity
@Table(name = "payment_methods")
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class PaymentMethod {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String ownerName;

    protected PaymentMethod() {
    }

    protected PaymentMethod(String ownerName) {
        this.ownerName = ownerName;
    }
}
~~~

~~~java
@Entity
@Table(name = "credit_card_payments")
@PrimaryKeyJoinColumn(name = "payment_method_id")
public class CreditCardPayment extends PaymentMethod {

    @Column(nullable = false, length = 80)
    private String cardToken;

    protected CreditCardPayment() {
    }

    public CreditCardPayment(String ownerName, String cardToken) {
        super(ownerName);
        this.cardToken = cardToken;
    }
}
~~~

~~~java
@Entity
@Table(name = "bank_transfer_payments")
@PrimaryKeyJoinColumn(name = "payment_method_id")
public class BankTransferPayment extends PaymentMethod {

    @Column(nullable = false, length = 30)
    private String bankCode;

    protected BankTransferPayment() {
    }

    public BankTransferPayment(String ownerName, String bankCode) {
        super(ownerName);
        this.bankCode = bankCode;
    }
}
~~~

Cấu trúc dữ liệu khái quát:

~~~text
payment_methods
---------------
id (PK)
owner_name

credit_card_payments
--------------------
payment_method_id (PK, FK -> payment_methods.id)
card_token

bank_transfer_payments
----------------------
payment_method_id (PK, FK -> payment_methods.id)
bank_code
~~~

**Ưu điểm**

- Thuộc tính riêng của subtype nằm ở bảng riêng, dễ đặt NOT NULL.
- Tránh bảng root quá rộng với nhiều cột subtype.
- Cấu trúc quan hệ gần với mô hình chuẩn hóa.

**Hạn chế**

- Truy vấn subtype thường cần join bảng cha và bảng con.
- Truy vấn đa hình trên root có thể cần nhiều join.
- Insert/update/delete liên quan nhiều bảng hơn.
- Migration hierarchy cần giữ khóa chính/khóa ngoại nhất quán.

JOINED phù hợp khi các subtype có nhiều thuộc tính riêng và cần ràng buộc dữ liệu rõ ràng, đồng thời chi phí join chấp nhận được.

### 2.3. TABLE_PER_CLASS

Mỗi concrete entity class có bảng riêng và lặp lại cả thuộc tính kế thừa. Không có bảng chung bắt buộc cho root entity.

Ví dụ khái quát:

~~~java
@Entity
@Inheritance(strategy = InheritanceType.TABLE_PER_CLASS)
public abstract class Document {

    @Id
    private UUID id;

    private String title;
}
~~~

~~~java
@Entity
@Table(name = "invoices")
public class Invoice extends Document {

    private BigDecimal total;
}
~~~

~~~java
@Entity
@Table(name = "delivery_notes")
public class DeliveryNote extends Document {

    private LocalDate deliveredOn;
}
~~~

Bảng invoices và delivery_notes đều có các cột kế thừa như id và title, cùng các cột riêng của lớp con.

**Ưu điểm**

- Mỗi concrete subtype có bảng độc lập.
- Truy vấn một subtype cụ thể không cần join bảng cha.
- Có thể phù hợp khi các subtype được lưu trữ và truy vấn gần như độc lập.

**Hạn chế**

- Dữ liệu chung bị lặp trong nhiều bảng.
- Truy vấn đa hình qua root có thể phải hợp nhất dữ liệu từ nhiều bảng, thường bằng UNION.
- Foreign key tham chiếu đến một root abstract không đơn giản vì không có một bảng root duy nhất.
- Sinh khóa và truy vấn đa hình có các giới hạn về tính di động và phụ thuộc provider/database.

Chỉ chọn TABLE_PER_CLASS khi có lý do rõ ràng và đã kiểm tra khả năng hỗ trợ của provider, chiến lược ID, truy vấn đa hình và quan hệ tham chiếu. Không nên chọn chỉ vì muốn mỗi subtype có bảng riêng.

### So sánh ba chiến lược

| Tiêu chí | SINGLE_TABLE | JOINED | TABLE_PER_CLASS |
|---|---|---|---|
| Số bảng | Một bảng cho hierarchy | Bảng root và bảng từng subtype | Bảng từng concrete subtype |
| Truy vấn đa hình | Thường đơn giản, không join | Cần join | Có thể cần UNION |
| Cột subtype | Nhiều cột nullable | Nằm ở bảng con | Lặp ở từng bảng |
| Ràng buộc NOT NULL theo subtype | Khó hơn, thường cần CHECK | Dễ đặt ở bảng con | Dễ đặt ở từng bảng |
| Ghi dữ liệu | Thường một bảng | Nhiều bảng | Một bảng subtype |
| Chuẩn hóa | Ít chuẩn hóa hơn | Chuẩn hóa hơn | Lặp dữ liệu chung |
| Khi phù hợp | Hierarchy nhỏ, truy vấn đa hình thường xuyên | Nhiều thuộc tính riêng, cần ràng buộc rõ | Subtype độc lập và ít truy vấn chung |

## 3. Khi nào dùng @MappedSuperclass?

Đôi khi các entity chỉ cần chia sẻ mapping chung như ID, thời gian tạo, thời gian cập nhật hoặc người tạo. Điều đó không có nghĩa chúng phải là các subtype của cùng một entity trong domain.

`@MappedSuperclass` cho phép lớp cha cung cấp mapping cho entity con nhưng bản thân lớp cha không phải entity và không có bảng riêng.

Ví dụ:

~~~java
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

    @Column(nullable = false, updatable = false)
    private Instant createdAt;

    public Long getId() {
        return id;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
~~~

Entity con kế thừa mapping:

~~~java
@Entity
@Table(name = "customers")
public class Customer extends AuditedEntity {

    @Column(nullable = false)
    private String name;

    protected Customer() {
    }
}
~~~

Các cột id và createdAt được ánh xạ vào bảng customers. Nếu Product cũng kế thừa AuditedEntity, các cột đó sẽ được ánh xạ vào bảng products.

Dùng `@MappedSuperclass` khi:

- Chỉ muốn tái sử dụng trạng thái và mapping.
- Lớp cha không cần truy vấn đa hình.
- Các lớp con không thực sự là những subtype của một entity domain chung.
- Không cần quan hệ JPA tham chiếu đến lớp cha.

Không thể viết JPQL query trên AuditedEntity như một entity root, vì nó không phải entity. Không thể khai báo quan hệ JPA có target entity là mapped superclass.

## 4. Khi nào dùng composition với @Embeddable?

Composition thường phù hợp khi một phần dữ liệu là value object: có giá trị và thuộc về entity chứa nó, nhưng không cần identity riêng.

Ví dụ Address là một value object của Customer:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

@Embeddable
public class Address {

    @Column(name = "street", length = 160)
    private String street;

    @Column(name = "city", length = 100)
    private String city;

    @Column(name = "postal_code", length = 20)
    private String postalCode;

    protected Address() {
    }

    public Address(String street, String city, String postalCode) {
        this.street = street;
        this.city = city;
        this.postalCode = postalCode;
    }

    public String getStreet() {
        return street;
    }

    public String getCity() {
        return city;
    }

    public String getPostalCode() {
        return postalCode;
    }
}
~~~

Customer nhúng Address:

~~~java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Embedded
    private Address billingAddress;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(
            name = "street",
            column = @Column(name = "shipping_street")
        ),
        @AttributeOverride(
            name = "city",
            column = @Column(name = "shipping_city")
        ),
        @AttributeOverride(
            name = "postalCode",
            column = @Column(name = "shipping_postal_code")
        )
    })
    private Address shippingAddress;

    protected Customer() {
    }
}
~~~

Các field của Address được lưu ngay trong bảng customers. Khi nhúng cùng một kiểu hai lần, `@AttributeOverrides` đổi tên cột để tránh trùng.

Value object không có primary key riêng và không được truy vấn như entity độc lập. Nếu Address cần được chia sẻ, quản lý vòng đời riêng, audit riêng hoặc được tham chiếu bởi nhiều entity, hãy cân nhắc mô hình hóa thành entity thay vì embeddable.

### Collection của value object

Nếu entity có một tập giá trị không cần identity, có thể dùng `@ElementCollection`:

~~~java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ElementCollection
    @CollectionTable(
        name = "customer_tags",
        joinColumns = @JoinColumn(name = "customer_id")
    )
    @Column(name = "tag", nullable = false)
    private Set<String> tags = new HashSet<>();

    protected Customer() {
    }
}
~~~

Các tag được lưu trong collection table và gắn với customer. Chúng không phải entity độc lập và không có ID riêng. Nếu mỗi tag cần trạng thái, quan hệ, lịch sử hoặc được quản lý độc lập, hãy tạo entity.

## 5. Khi nào composition cần association tới entity khác?

Không phải mọi composition đều dùng `@Embeddable`. Nếu đối tượng thành phần có identity riêng hoặc cần được truy vấn, tham chiếu độc lập, hãy dùng association.

Ví dụ Customer có một LoyaltyAccount:

~~~java
@Entity
@Table(name = "loyalty_accounts")
public class LoyaltyAccount {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String accountNumber;

    protected LoyaltyAccount() {
    }
}
~~~

Customer có thể tham chiếu tài khoản:

~~~java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "loyalty_account_id", unique = true)
    private LoyaltyAccount loyaltyAccount;

    protected Customer() {
    }
}
~~~

Đây là association giữa hai entity có identity. Nếu tài khoản có thể sống độc lập, không đặt cascade REMOVE hoặc orphanRemoval một cách tùy tiện. Nếu nó thực sự là thành phần phụ thuộc vào Customer, hãy xác định rõ vòng đời, quyền sở hữu và thao tác xóa.

Composition trong thiết kế domain nói về quan hệ và vòng đời đối tượng. JPA association chỉ là một cách ánh xạ quan hệ đó; cascade và orphanRemoval phải phản ánh đúng quy tắc nghiệp vụ.

## 6. Chọn inheritance hay composition?

Hãy bắt đầu từ mô hình nghiệp vụ, sau đó mới chọn annotation.

| Câu hỏi thiết kế | Entity inheritance | Composition |
|---|---|---|
| Quan hệ có phải “is-a” thật sự không? | Có, subtype có thể thay thế base type | Không cần quan hệ subtype |
| Có cần truy vấn đa hình trên lớp cha không? | Có thể rất phù hợp | Thường truy vấn qua association hoặc root riêng |
| Các loại có cùng identity và vòng đời không? | Thường có | Thành phần có thể có vòng đời riêng hoặc chỉ là value |
| Thuộc tính chung có cần bảng/identity chung không? | Tùy chiến lược inheritance | Có thể dùng embedded hoặc mapped superclass |
| Có cần thêm biến thể hành vi lúc runtime không? | Có thể làm cây lớp cứng nhắc | Có thể thay collaborator hoặc policy dễ hơn |
| Cấu trúc dữ liệu | SINGLE_TABLE, JOINED hoặc TABLE_PER_CLASS | Cột nhúng, collection table hoặc bảng entity liên quan |

### Quy tắc lựa chọn

- Chọn entity inheritance khi subtype là phân loại domain ổn định, có thể thay thế base type và ứng dụng cần truy vấn đa hình.
- Chọn `@MappedSuperclass` khi chỉ muốn tái sử dụng mapping chung mà không cần entity root.
- Chọn `@Embeddable` khi thành phần là value object không có identity riêng.
- Chọn association tới entity khác khi thành phần có identity hoặc vòng đời độc lập.
- Chọn composition khi muốn kết hợp hành vi có thể thay đổi, ví dụ Payment sử dụng PricingPolicy hoặc Notification sử dụng DeliveryChannel.
- Tránh tạo cây entity inheritance chỉ để chia sẻ vài field hoặc vài method tiện ích.

Một subtype tốt phải tuân thủ hợp đồng của base type. Nếu các subtype có quy tắc bắt buộc khác nhau đến mức caller phải liên tục kiểm tra kiểu cụ thể, mô hình có thể đang dùng inheritance sai chỗ.

## 7. Truy vấn và quan hệ đa hình

Với entity inheritance, JPQL có thể truy vấn root entity và nhận các subtype. Ví dụ:

~~~java
List<Vehicle> vehicles =
        entityManager.createQuery(
            "select v from Vehicle v",
            Vehicle.class
        ).getResultList();
~~~

Nếu cần lọc subtype, có thể dùng `TYPE`:

~~~java
List<Vehicle> cars =
        entityManager.createQuery(
            "select v from Vehicle v where type(v) = Car",
            Vehicle.class
        ).getResultList();
~~~

Tùy chiến lược inheritance, SQL có thể rất khác:

- SINGLE_TABLE lọc bằng discriminator trên một bảng.
- JOINED cần join bảng subtype để dựng entity cụ thể.
- TABLE_PER_CLASS có thể phải hợp nhất kết quả từ nhiều bảng.

Không chỉ nhìn số bảng để quyết định. Hãy xem các truy vấn chính, số bản ghi, tần suất truy vấn root và dữ liệu subtype thực tế.

Với composition, truy vấn thường đi qua association hoặc projection. Nếu chỉ cần vài thuộc tính của component, có thể dùng DTO projection để tránh tải toàn bộ object graph.

## 8. Cascade, vòng đời và aggregate

Inheritance không quyết định cascade. Cascade thuộc về quan hệ association giữa các entity. Composition trong domain có thể gợi ý vòng đời phụ thuộc, nhưng không tự động có nghĩa phải dùng `CascadeType.ALL`.

Trước khi bật cascade hoặc orphanRemoval, hãy trả lời:

- Component/entity con có thể tồn tại nếu parent bị xóa không?
- Nó có thể được chia sẻ bởi nhiều parent không?
- Có cần lưu lịch sử độc lập không?
- Việc gỡ khỏi collection có nghĩa là xóa bản ghi không?
- Có thao tác chuyển component sang parent khác không?

Ví dụ OrderLine thường phụ thuộc vào PurchaseOrder nên cascade PERSIST và orphanRemoval có thể hợp lý. Product được nhiều OrderLine tham chiếu thì không nên xóa Product khi một OrderLine bị xóa.

Đối với aggregate, hãy đặt phương thức nghiệp vụ tại root để bảo vệ invariant. Không để code ở nhiều nơi tự sửa collection hoặc foreign key khiến trạng thái domain không nhất quán.

## 9. Thiết kế và kiểm thử

Với inheritance:

- Kiểm tra discriminator và mapping subtype.
- Kiểm tra NOT NULL/CHECK constraint cho field theo subtype.
- Kiểm tra query root có trả về đủ subtype.
- Kiểm tra join và số query của chiến lược JOINED.
- Kiểm tra ID generator dùng chung giữa các bảng trong hierarchy nếu provider/database yêu cầu.

Với composition:

- Kiểm tra value object được persist cùng owner.
- Kiểm tra `@AttributeOverride` tạo đúng tên cột khi embedded nhiều lần.
- Kiểm tra collection table và foreign key.
- Kiểm tra vòng đời của entity component và cascade.
- Kiểm tra association lazy/eager theo use case.

Với mọi mô hình:

- Chạy integration test trên cùng loại database dự kiến triển khai, hoặc Testcontainers nếu cần xác nhận hành vi đặc thù database.
- Kiểm tra schema bằng migration, không chỉ dựa vào auto-DDL.
- Kiểm tra số query để phát hiện N+1.
- Kiểm tra serialization API để tránh vòng lặp object graph.
- Đo truy vấn quan trọng trước khi tối ưu mapping.

## 10. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Cây entity inheritance ngày càng phức tạp | Dùng kế thừa để tái sử dụng code thay vì mô hình hóa subtype | Tách value object hoặc collaborator bằng composition |
| Bảng SINGLE_TABLE có nhiều cột null | Nhiều thuộc tính chỉ áp dụng cho một subtype | Cân nhắc JOINED hoặc tách thành association |
| Truy vấn subtype chậm | JOINED cần join nhiều bảng hoặc TABLE_PER_CLASS cần UNION | Đo query và cân nhắc strategy theo workload |
| Không truy vấn được lớp cha | Dùng @MappedSuperclass thay cho root @Entity | Dùng entity inheritance nếu cần polymorphic query |
| Field nhúng trùng tên cột | Embedded cùng kiểu nhiều lần nhưng không override | Dùng @AttributeOverrides |
| Xóa parent làm mất entity dùng chung | Cascade REMOVE/orphanRemoval đặt sai | Xác định ownership và vòng đời thực |
| Entity con không được tải cùng parent | Fetch plan không phù hợp | Dùng EntityGraph hoặc query fetch theo use case |
| API JSON lặp vô hạn | Association hai chiều serialize qua lại | Dùng DTO hoặc cấu hình serialization rõ ràng |

## Checklist trước khi merge

- [ ] Mô hình “is-a” hoặc “has-a” được xác định theo nghiệp vụ.
- [ ] Entity inheritance chỉ dùng khi cần subtype và identity chung.
- [ ] Chiến lược inheritance được chọn theo truy vấn và ràng buộc dữ liệu.
- [ ] @MappedSuperclass chỉ dùng cho mapping dùng chung, không cần query root.
- [ ] @Embeddable dành cho value object không có identity riêng.
- [ ] Association dùng khi component là entity có identity/vòng đời riêng.
- [ ] Cascade và orphanRemoval phản ánh đúng ownership.
- [ ] Query đa hình, fetch plan và schema đã được kiểm thử.
- [ ] Không có vòng lặp JSON hoặc N+1 query ngoài dự kiến.

## Kết luận

Entity inheritance phù hợp khi các lớp con thật sự là subtype của một entity root và cần identity, vòng đời hoặc truy vấn đa hình chung. Composition phù hợp khi muốn ghép value object, mapping dùng chung hoặc entity collaborator mà không tạo cây kế thừa cứng nhắc. Trong JPA, `@Inheritance`, `@MappedSuperclass`, `@Embeddable` và association có semantics lưu trữ khác nhau; hãy chọn theo domain, truy vấn, vòng đời và ràng buộc database. Kiểm thử schema và query thực tế trước khi chốt mô hình.
