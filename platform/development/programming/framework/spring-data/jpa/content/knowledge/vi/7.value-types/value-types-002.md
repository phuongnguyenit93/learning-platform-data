# Tái sử dụng nhóm thuộc tính bằng @Embeddable và @Embedded

Trong mô hình hướng đối tượng, một entity thường có nhiều nhóm thuộc tính cùng mô tả một khái niệm. Ví dụ một đơn hàng có địa chỉ thanh toán và địa chỉ giao hàng; một khách hàng có địa chỉ liên hệ; một sản phẩm có thông tin kích thước hoặc tiền tệ. Nếu mỗi entity tự khai báo lại các field giống nhau, code dễ lặp và quy tắc dữ liệu có thể không nhất quán.

JPA cung cấp **@Embeddable** và **@Embedded** để gom một nhóm thuộc tính thành một kiểu giá trị có thể tái sử dụng:

- **@Embeddable** đánh dấu lớp mô tả nhóm thuộc tính có thể được nhúng vào entity hoặc một embeddable khác.
- **@Embedded** đặt một thuộc tính của kiểu embeddable bên trong entity hoặc embeddable sở hữu nó.

Một embeddable không có định danh độc lập như entity. Nó tồn tại như một phần của đối tượng sở hữu và thường được ánh xạ thành các cột trong cùng bảng với entity đó. Cách tổ chức này giúp mô hình domain rõ ràng, tái sử dụng mapping và gom các quy tắc liên quan vào một kiểu có ý nghĩa.

**Điều kiện của ví dụ:** các đoạn mã dùng Spring Boot 3.x, Java 17 trở lên và Jakarta Persistence. Ứng dụng cần dependency **spring-boot-starter-data-jpa**, DataSource và schema tương ứng. Các khối mã là những tệp nguồn riêng trong ứng dụng Spring Boot, không phải chương trình độc lập có thể chạy chỉ bằng **javac**.

## 1. Entity và embeddable khác nhau thế nào?

Entity đại diện cho một đối tượng có danh tính và vòng đời được persistence context quản lý. Embeddable đại diện cho một nhóm giá trị thuộc về entity hoặc embeddable khác.

| Đặc điểm | Entity | Embeddable |
|---|---|---|
| Định danh JPA | Có khóa chính, thường dùng **@Id** | Không có khóa chính độc lập |
| Vòng đời | Có thể được persist, find, remove độc lập | Đi cùng vòng đời của đối tượng sở hữu |
| Repository riêng | Có thể có repository | Không có repository riêng |
| Mapping phổ biến | Một bảng hoặc chiến lược kế thừa | Các cột được nhúng vào bảng của đối tượng sở hữu |
| Annotation chính | **@Entity** | **@Embeddable** |
| Cách sử dụng | Được quản lý như một entity | Được khai báo bằng **@Embedded** hoặc dùng trong các mapping embeddable phù hợp |

Ví dụ: một khách hàng là entity vì hệ thống cần định danh và tìm khách hàng theo ID. Địa chỉ của khách hàng thường là một value object: nó mô tả nơi ở hoặc nơi liên hệ và được quản lý cùng khách hàng. Địa chỉ không nhất thiết cần một ID riêng hay một repository riêng.

Nếu địa chỉ cần được chia sẻ, quản lý và cập nhật độc lập bởi nhiều entity, đó có thể là dấu hiệu cho thấy địa chỉ nên được mô hình hóa thành entity riêng. Việc chọn entity hay embeddable phụ thuộc vào ý nghĩa nghiệp vụ và vòng đời dữ liệu, không chỉ phụ thuộc số lượng field.

## 2. Khai báo lớp @Embeddable

Giả sử hệ thống có nhiều entity cần dùng địa chỉ. Ta tạo một lớp Address:

~~~java
package com.example.customer.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

import java.util.Objects;

@Embeddable
public class Address {

    @Column(name = "street", nullable = false, length = 150)
    private String street;

    @Column(name = "city", nullable = false, length = 100)
    private String city;

    @Column(name = "postal_code", length = 20)
    private String postalCode;

    protected Address() {
        // Constructor cho JPA.
    }

    public Address(String street, String city, String postalCode) {
        this.street = requireText(street, "street");
        this.city = requireText(city, "city");
        this.postalCode = postalCode;
    }

    private static String requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        return value.trim();
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

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof Address address)) {
            return false;
        }
        return Objects.equals(street, address.street)
            && Objects.equals(city, address.city)
            && Objects.equals(postalCode, address.postalCode);
    }

    @Override
    public int hashCode() {
        return Objects.hash(street, city, postalCode);
    }
}
~~~

Một số điểm cần chú ý:

- **@Embeddable** đánh dấu lớp là kiểu có thể được nhúng.
- Các annotation mapping như **@Column** có thể được khai báo ngay trên field của embeddable.
- Constructor không tham số có phạm vi **public** hoặc **protected** để JPA có thể khởi tạo.
- Ví dụ dùng field access vì annotation được đặt trên field. Nếu chọn property access, hãy đặt mapping annotation nhất quán trên getter.
- Lớp không khai báo **@Id** và không có repository riêng.
- **equals()** và **hashCode()** dựa trên các giá trị tạo nên địa chỉ. Đây là cách phù hợp với value object bất biến hoặc ít thay đổi.

JPA quản lý trạng thái của entity sở hữu. Khi entity được tải, embeddable cũng được khôi phục như một phần của entity đó.

## 3. Nhúng bằng @Embedded

Entity Customer có thể dùng Address như sau:

~~~java
package com.example.customer.domain;

import jakarta.persistence.Embedded;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String fullName;

    @Embedded
    private Address address;

    protected Customer() {
    }

    public Customer(String fullName, Address address) {
        this.fullName = fullName;
        this.address = address;
    }

    public void changeAddress(Address newAddress) {
        if (newAddress == null) {
            throw new IllegalArgumentException("address must not be null");
        }
        this.address = newAddress;
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public Address getAddress() {
        return address;
    }
}
~~~

**@Embedded** đánh dấu thuộc tính có kiểu embeddable. Với mapping mặc định, các field của Address được ánh xạ thành các cột trong bảng **customers**. JPA không bắt buộc tạo một bảng Address riêng.

Hình dung schema:

~~~text
customers
+----+-----------+----------------+------------+-------------+
| id | full_name | street         | city       | postal_code |
+----+-----------+----------------+------------+-------------+
|  1 | An Nguyen | 10 Le Loi      | Da Nang    | 550000      |
+----+-----------+----------------+------------+-------------+
~~~

Ở đây:

- **Customer.id** là khóa chính của entity.
- **Address** không có khóa chính riêng.
- Các cột **street**, **city**, **postal_code** thuộc hàng của khách hàng.
- Tải một Customer sẽ tải các giá trị Address theo mapping của entity.

Đây là điểm quan trọng: **@Embedded** không có nghĩa là tạo bảng con. Nó nhúng các thuộc tính vào cấu trúc lưu trữ của đối tượng sở hữu.

## 4. Tái sử dụng cùng một embeddable nhiều lần

Một đơn hàng có thể có địa chỉ thanh toán và địa chỉ giao hàng. Cả hai đều dùng kiểu Address, nhưng không thể cùng ánh xạ vào một bộ tên cột mặc định như **street**, **city** và **postal_code**. Ta cần đổi tên cột cho từng thuộc tính nhúng bằng **@AttributeOverride**.

~~~java
package com.example.order.domain;

import com.example.customer.domain.Address;
import jakarta.persistence.AttributeOverride;
import jakarta.persistence.AttributeOverrides;
import jakarta.persistence.Column;
import jakarta.persistence.Embedded;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(
            name = "street",
            column = @Column(name = "billing_street", nullable = false, length = 150)
        ),
        @AttributeOverride(
            name = "city",
            column = @Column(name = "billing_city", nullable = false, length = 100)
        ),
        @AttributeOverride(
            name = "postalCode",
            column = @Column(name = "billing_postal_code", length = 20)
        )
    })
    private Address billingAddress;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(
            name = "street",
            column = @Column(name = "shipping_street", nullable = false, length = 150)
        ),
        @AttributeOverride(
            name = "city",
            column = @Column(name = "shipping_city", nullable = false, length = 100)
        ),
        @AttributeOverride(
            name = "postalCode",
            column = @Column(name = "shipping_postal_code", length = 20)
        )
    })
    private Address shippingAddress;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(Address billingAddress, Address shippingAddress) {
        this.billingAddress = billingAddress;
        this.shippingAddress = shippingAddress;
    }
}
~~~

Schema tương ứng có thể có dạng:

~~~text
orders
+----+----------------+--------------+---------------------+
| id | billing_street | billing_city | billing_postal_code |
+----+----------------+--------------+---------------------+

+-----------------+---------------+----------------------+
| shipping_street | shipping_city | shipping_postal_code |
+-----------------+---------------+----------------------+
~~~

**@AttributeOverride** thay đổi mapping của một thuộc tính bên trong embeddable tại vị trí được nhúng. Thuộc tính **name** là tên thuộc tính Java trong lớp embeddable, ví dụ **postalCode**; thuộc tính **column.name** là tên cột database, ví dụ **billing_postal_code**.

Một số lưu ý:

1. Tên trong **@AttributeOverride(name = ...)** phải khớp tên persistent attribute của embeddable, bao gồm chữ hoa/chữ thường.
2. Khi cùng một kiểu embeddable được dùng nhiều lần trong cùng entity, hãy override các tên cột có khả năng xung đột.
3. Có thể override thêm thuộc tính khác như **nullable**, **length**, **precision** hoặc **scale** nếu mapping tại vị trí nhúng cần khác.
4. Override chỉ tác động đến vị trí sử dụng cụ thể; nó không thay đổi mapping mặc định của lớp Address ở các entity khác.

## 5. Nested embeddable và override thuộc tính lồng nhau

Một embeddable có thể chứa một embeddable khác. Ví dụ ContactInfo chứa Address:

~~~java
@Embeddable
public class ContactInfo {

    @Column(name = "contact_email", length = 150)
    private String email;

    @Embedded
    private Address address;

    protected ContactInfo() {
    }

    public ContactInfo(String email, Address address) {
        this.email = email;
        this.address = address;
    }
}
~~~

Entity có thể nhúng ContactInfo:

~~~java
@Entity
@Table(name = "suppliers")
public class Supplier {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Embedded
    private ContactInfo contactInfo;

    protected Supplier() {
    }
}
~~~

Các thuộc tính của ContactInfo và Address vẫn được ánh xạ vào bảng **suppliers**. Nếu cần đổi tên thuộc tính lồng nhau, dùng tên đường dẫn trong **@AttributeOverride**:

~~~java
@Embedded
@AttributeOverrides({
    @AttributeOverride(
        name = "email",
        column = @Column(name = "primary_email", length = 150)
    ),
    @AttributeOverride(
        name = "address.street",
        column = @Column(name = "primary_street", nullable = false, length = 150)
    ),
    @AttributeOverride(
        name = "address.city",
        column = @Column(name = "primary_city", nullable = false, length = 100)
    ),
    @AttributeOverride(
        name = "address.postalCode",
        column = @Column(name = "primary_postal_code", length = 20)
    )
})
private ContactInfo primaryContact;
~~~

Đường dẫn **address.street** có nghĩa là thuộc tính **street** bên trong thuộc tính nhúng **address** của ContactInfo. Cách viết này hữu ích khi mô hình có nhiều lớp giá trị lồng nhau. Nếu có nhiều tầng lồng, tên override cần thể hiện đầy đủ đường dẫn thuộc tính theo cấu trúc embeddable.

Không nên lồng quá nhiều cấp nếu nó làm mapping khó đọc. Một embeddable nên gom nhóm giá trị có ý nghĩa nghiệp vụ rõ ràng, chẳng hạn Address, Money, Dimensions hoặc DateRange.

## 6. @AttributeOverride và @AssociationOverride khác nhau

**@AttributeOverride** thay đổi mapping của thuộc tính cơ bản (basic attribute) bên trong embeddable. Nếu embeddable chứa quan hệ tới entity khác, có thể cần **@AssociationOverride** để thay đổi mapping của quan hệ đó.

Ví dụ một embeddable giữ thông tin người phụ trách:

~~~java
@Embeddable
public class AssignmentInfo {

    @Column(name = "assigned_at")
    private Instant assignedAt;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "assignee_id")
    private Employee assignee;

    protected AssignmentInfo() {
    }
}
~~~

Nếu entity nhúng AssignmentInfo nhưng muốn dùng tên cột khóa ngoại khác:

~~~java
@Embedded
@AssociationOverride(
    name = "assignee",
    joinColumns = @JoinColumn(name = "reviewer_id")
)
private AssignmentInfo reviewAssignment;
~~~

Trong trường hợp này:

- **assignedAt** là thuộc tính cơ bản, override bằng **@AttributeOverride** nếu cần.
- **assignee** là association tới entity Employee, override bằng **@AssociationOverride**.
- **joinColumns** xác định cột liên kết mới.

Embeddable có thể chứa mapping quan hệ được JPA cho phép, nhưng quan hệ vẫn được quản lý trong ngữ cảnh entity sở hữu. Không vì thế mà embeddable trở thành entity độc lập.

## 7. Dùng embeddable trong collection: @ElementCollection

Khi một entity có nhiều value object cùng loại, ví dụ một khách hàng có nhiều địa chỉ nhận hàng, có thể dùng **@ElementCollection**. Khác với **@Embedded** đơn lẻ, collection thường được lưu trong một collection table riêng.

~~~java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String fullName;

    @ElementCollection
    @CollectionTable(
        name = "customer_addresses",
        joinColumns = @JoinColumn(name = "customer_id")
    )
    private List<Address> deliveryAddresses = new ArrayList<>();

    protected Customer() {
    }
}
~~~

Bảng lưu trữ có thể có dạng:

~~~text
customers
+----+-----------+
| id | full_name |
+----+-----------+

customer_addresses
+-------------+----------------+----------+-------------+
| customer_id | street         | city     | postal_code |
+-------------+----------------+----------+-------------+
~~~

Ở đây **Address** vẫn là embeddable và không có ID entity riêng. Collection table lưu các giá trị Address cùng khóa ngoại trỏ về Customer. Không nên nhầm collection table của **@ElementCollection** với một entity table độc lập.

Nếu từng địa chỉ cần được tham chiếu độc lập, có vòng đời riêng hoặc cần repository riêng, hãy cân nhắc mô hình Address thành entity và dùng quan hệ **@OneToMany** thay vì value collection.

## 8. Khóa chính dạng nhóm giá trị: @EmbeddedId

Một ứng dụng có thể dùng embeddable làm khóa chính tổng hợp (composite key). Trường hợp này dùng **@EmbeddedId** thay cho **@Embedded** thông thường.

Ví dụ khóa gồm mã kho và mã sản phẩm:

~~~java
@Embeddable
public class StockId implements Serializable {

    private String warehouseCode;

    private String productCode;

    protected StockId() {
    }

    public StockId(String warehouseCode, String productCode) {
        this.warehouseCode = warehouseCode;
        this.productCode = productCode;
    }

    // equals() và hashCode() dựa trên cả hai thành phần khóa.
}
~~~

Entity:

~~~java
@Entity
@Table(name = "stock")
public class Stock {

    @EmbeddedId
    private StockId id;

    private Integer quantity;

    protected Stock() {
    }
}
~~~

Khác biệt:

- **@Embedded** nhúng một nhóm thuộc tính vào entity.
- **@EmbeddedId** dùng một embeddable làm khóa chính tổng hợp của entity.
- **@EmbeddedId** vẫn tạo một entity có định danh; chính nhóm giá trị trong embeddable là định danh đó.

Composite key cần triển khai **equals()** và **hashCode()** nhất quán dựa trên các thành phần khóa. Các giá trị khóa phải ổn định sau khi entity được tạo và không nên thay đổi trong vòng đời persistence.

Không dùng **@EmbeddedId** chỉ để gom các field cho gọn. Nếu nhóm field không phải khóa chính, dùng **@Embeddable** và **@Embedded** thông thường.

## 9. Null và vòng đời của embeddable

Embeddable không có identity riêng, vì vậy trạng thái của nó gắn với entity sở hữu.

Ví dụ:

~~~java
Customer customer = new Customer();
customer.changeAddress(
    new Address("10 Le Loi", "Da Nang", "550000")
);
~~~

Khi Customer được persist, các thuộc tính Address được ghi cùng entity theo mapping. Khi thay đổi một field của Address đang thuộc entity managed, JPA có thể phát hiện thay đổi và đồng bộ khi flush.

~~~java
customer.getAddress().changeCity("Hue");
~~~

Đoạn trên giả định Address cung cấp phương thức **changeCity** và Customer đang managed trong transaction. Không cần repository riêng cho Address.

### Embeddable null

Một thuộc tính **@Embedded** có thể được gán null nếu mapping và quy tắc nghiệp vụ cho phép. Tuy nhiên, khi tất cả cột của một embeddable trong hàng đều null, cách provider khôi phục giá trị embeddable có thể phụ thuộc mapping và provider. Vì vậy:

- Nếu nhóm giá trị là bắt buộc, hãy bảo vệ invariant ở domain/Bean Validation và khai báo các cột cần thiết là NOT NULL trong schema.
- Nếu nhóm giá trị là tùy chọn, hãy thiết kế để ứng dụng xử lý trường hợp object null rõ ràng.
- Không giả định rằng chỉ cần **@Embedded** là mọi thuộc tính con sẽ tự có giá trị mặc định.
- Kiểm tra hành vi thực tế với Hibernate và database của dự án, nhất là khi dùng nested embeddable hoặc collection.

**@Embedded** không có thuộc tính **optional** như **@ManyToOne(optional = ...)**. Tính bắt buộc của nhóm giá trị thường được biểu đạt qua invariant domain, Bean Validation và nullability của các cột.

## 10. Thiết kế embeddable như value object

Embeddable thường phù hợp với mô hình value object: hai giá trị được xem là bằng nhau nếu các thuộc tính cấu thành của chúng bằng nhau, không cần một ID riêng.

Ví dụ Money:

~~~java
@Embeddable
public class Money {

    @Column(name = "amount", precision = 12, scale = 2)
    private BigDecimal amount;

    @Column(name = "currency", length = 3)
    private String currency;

    protected Money() {
    }

    public Money(BigDecimal amount, String currency) {
        if (amount == null || amount.signum() < 0) {
            throw new IllegalArgumentException("amount must be non-negative");
        }
        if (currency == null || !currency.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException("currency must be a 3-letter uppercase code");
        }
        this.amount = amount;
        this.currency = currency;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public String getCurrency() {
        return currency;
    }
}
~~~

Một số nguyên tắc thiết kế:

1. Gom các thuộc tính có quan hệ ngữ nghĩa, không chỉ gom field vì chúng xuất hiện cạnh nhau.
2. Giữ constructor hoặc factory method để bảo vệ invariant.
3. Ưu tiên thiết kế bất biến (immutable) ở mức API domain nếu phù hợp; JPA vẫn cần khả năng khởi tạo theo quy định của provider.
4. Cài đặt **equals()** và **hashCode()** theo giá trị nếu ứng dụng cần so sánh value object.
5. Tránh dùng thuộc tính có thể thay đổi làm khóa của **HashMap** hoặc phần tử **HashSet** sau khi đã thêm vào collection.
6. Không thêm repository hoặc ID riêng cho embeddable chỉ để thao tác nó thuận tiện hơn.

Lưu ý với tiền: **BigDecimal.equals()** so sánh cả giá trị và scale, nên **new BigDecimal("10.0")** không bằng **new BigDecimal("10.00")** theo equals, dù **compareTo()** trả về 0. Nếu Money cần quy tắc equality theo giá trị tiền, hãy chuẩn hóa scale/currency hoặc triển khai equality có chủ đích.

## 11. Validation và mapping trên embeddable

Có thể đặt Bean Validation constraint trên thuộc tính của embeddable:

~~~java
@Embeddable
public class Address {

    @NotBlank
    @Size(max = 150)
    @Column(nullable = false, length = 150)
    private String street;

    @NotBlank
    @Size(max = 100)
    @Column(nullable = false, length = 100)
    private String city;

    protected Address() {
    }
}
~~~

Entity nhúng Address:

~~~java
@Entity
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    @Embedded
    @Valid
    private Address address;

    protected Customer() {
    }
}
~~~

**@Valid** yêu cầu Bean Validation cascade vào các thuộc tính lồng nhau khi validator xử lý Customer. Với JPA lifecycle validation, provider và validation integration cần được cấu hình phù hợp; các group và lifecycle event cũng ảnh hưởng thời điểm kiểm tra.

Không nhầm **@Valid** với **@Embedded**:

- **@Embedded** là annotation mapping JPA, xác định nhóm thuộc tính được nhúng.
- **@Valid** là annotation Bean Validation, yêu cầu cascade validation vào object lồng nhau.

Hai annotation có thể cùng xuất hiện vì chúng làm hai nhiệm vụ khác nhau.

## 12. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Entity không có bảng/cột như mong đợi | Embeddable chưa được nhúng hoặc schema không khớp | Kiểm tra **@Embeddable**, **@Embedded** và migration |
| Trùng tên cột khi nhúng hai lần | Dùng cùng default column names | Dùng **@AttributeOverrides** cho từng vị trí nhúng |
| Không tìm thấy constructor | Embeddable thiếu constructor không tham số phù hợp | Thêm constructor **protected** hoặc **public** |
| Cố inject AddressRepository | Nhầm embeddable với entity | Quản lý qua entity sở hữu hoặc chuyển thành entity nếu cần vòng đời riêng |
| Validation không đi vào object lồng | Thiếu **@Valid** hoặc provider/configuration | Kiểm tra cascade validation và lifecycle integration |
| Thay đổi object nhưng không lưu | Entity sở hữu detached hoặc ngoài transaction | Tải entity managed trong transaction rồi thay đổi |
| Collection value object không có bảng riêng | Dùng **@Embedded** đơn lẻ thay vì **@ElementCollection** | Chọn mapping theo cardinality và vòng đời |
| Composite key hoạt động không ổn định | **equals/hashCode** thiếu thành phần hoặc khóa bị thay đổi | Dựa trên toàn bộ thành phần khóa và giữ khóa bất biến |

## 13. Checklist khi dùng @Embeddable và @Embedded

- [ ] Xác định nhóm field có thực sự là value object thuộc entity sở hữu không.
- [ ] Đánh dấu lớp bằng **@Embeddable**.
- [ ] Khai báo constructor không tham số phù hợp cho JPA.
- [ ] Dùng **@Embedded** tại thuộc tính sở hữu.
- [ ] Kiểm tra tên cột mặc định và xung đột khi nhúng nhiều lần.
- [ ] Dùng **@AttributeOverride** cho basic attribute cần đổi mapping.
- [ ] Dùng **@AssociationOverride** khi cần đổi mapping association bên trong embeddable.
- [ ] Dùng **@ElementCollection** nếu cần collection của value object.
- [ ] Dùng **@EmbeddedId** chỉ khi embeddable thực sự là composite primary key.
- [ ] Xác định rõ nullability và hành vi khi embeddable null.
- [ ] Bảo vệ invariant domain và validation lồng nhau bằng **@Valid** khi cần.
- [ ] Đồng bộ mapping với migration/schema thực tế.
- [ ] Viết test persist, load và update entity có embeddable.

## 14. Kết luận

**@Embeddable** định nghĩa một nhóm thuộc tính có thể tái sử dụng; **@Embedded** đặt nhóm thuộc tính đó vào entity hoặc embeddable sở hữu. Các field thường được ánh xạ thành cột trong bảng của đối tượng sở hữu, không cần một entity hay repository riêng. Khi nhúng cùng một kiểu nhiều lần, dùng **@AttributeOverride** để tránh xung đột tên cột; với association, dùng **@AssociationOverride**.

Chọn embeddable khi nhóm giá trị không có danh tính và vòng đời độc lập. Chọn entity khi đối tượng cần ID, được tham chiếu hoặc quản lý riêng. Quyết định đúng giúp mô hình JPA phản ánh rõ domain và giữ mapping dễ tái sử dụng.