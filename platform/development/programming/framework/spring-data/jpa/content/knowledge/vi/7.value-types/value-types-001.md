# Phân biệt Entity và đối tượng giá trị

## Mục tiêu

Sau bài này, bạn có thể phân biệt Entity và Value Object trong mô hình domain; giải thích identity, vòng đời và quy tắc so sánh của mỗi loại; chọn cách ánh xạ bằng `@Entity`, `@Embeddable`, `@Embedded` và `@ElementCollection`; đồng thời tránh biến mọi object thành entity hoặc tạo bảng riêng cho những giá trị không có danh tính độc lập.

## 1. Vì sao cần phân biệt Entity và Value Object?

Một mô hình nghiệp vụ thường chứa nhiều loại object. Có object đại diện cho một đối tượng tồn tại độc lập qua thời gian, chẳng hạn khách hàng hoặc đơn hàng. Có object chỉ mô tả một giá trị, chẳng hạn địa chỉ giao hàng, khoảng thời gian, số tiền hoặc tọa độ.

Nếu coi tất cả object đều là entity, mô hình sẽ có nhiều khóa chính, repository, quan hệ và bảng hơn mức cần thiết. Nếu coi mọi thứ là value object, ứng dụng có thể làm mất danh tính, lịch sử và khả năng tham chiếu của những đối tượng cần được quản lý độc lập.

Phân biệt hai loại này giúp quyết định object có cần identity ổn định hay không, có vòng đời riêng hay không, thay đổi là cập nhật object hay thay thế một giá trị mới, và có cần repository/bảng riêng hay chỉ cần nhúng vào entity sở hữu.

## 2. Entity là gì?

**Entity** là object có danh tính (identity) riêng. Hai entity có thể chứa cùng dữ liệu nhưng vẫn là hai đối tượng khác nhau nếu identity của chúng khác nhau.

Ví dụ, hai khách hàng có cùng tên và cùng địa chỉ vẫn có thể là hai khách hàng khác nhau. Họ có thể được phân biệt bằng mã khách hàng, số định danh hoặc khóa chính trong hệ thống.

Đặc điểm thường gặp của entity:

1. Có identity ổn định trong phạm vi nghiệp vụ hoặc hệ thống.
2. Có vòng đời riêng: được tạo, cập nhật, có thể bị vô hiệu hóa hoặc xóa.
3. Trạng thái có thể thay đổi trong khi identity vẫn giữ nguyên.
4. Các object khác có thể tham chiếu đến entity đó.
5. Việc so sánh hai entity chủ yếu dựa trên identity hoặc khóa nghiệp vụ được chọn, không dựa trên việc mọi field hiện tại có giống nhau hay không.

Trong JPA, entity được đánh dấu bằng `@Entity` và phải có định danh được đánh dấu bằng `@Id` hoặc `@EmbeddedId`. JPA provider quản lý vòng đời persistence của entity và ánh xạ entity vào bảng hoặc cấu trúc lưu trữ tương ứng.

Ví dụ: `Customer` có `id` riêng. Khi đổi địa chỉ, khách hàng vẫn là cùng một khách hàng; chỉ trạng thái của entity thay đổi.

## 3. Value Object là gì?

**Value Object (đối tượng giá trị)** được nhận diện bằng giá trị mà nó mang, không có identity độc lập trong mô hình nghiệp vụ. Hai value object có cùng các thành phần giá trị được xem là tương đương theo quy tắc equality của kiểu đó.

Ví dụ, hai giá trị `Money(100000, "VND")` có thể được xem là bằng nhau nếu cùng số tiền và cùng đơn vị tiền tệ. Một `Address` gồm cùng số nhà, đường và thành phố cũng có thể được xem là cùng một giá trị địa chỉ.

Đặc điểm thường gặp của value object:

1. Không có identity độc lập trong domain.
2. Equality dựa trên toàn bộ thành phần tạo nên giá trị.
3. Thường bất biến (immutable): thay đổi một thành phần tạo ra value object mới.
4. Vòng đời thường phụ thuộc vào entity hoặc aggregate sở hữu nó.
5. Thường không cần repository riêng hoặc khóa chính riêng.

Value Object giúp diễn đạt ý nghĩa nghiệp vụ rõ hơn. Thay vì truyền chuỗi `"100000"` cùng chuỗi `"VND"` rời rạc, kiểu `Money` thể hiện đây là một giá trị tiền tệ có quy tắc riêng. Kiểu `Address` gom các thành phần địa chỉ thành một khái niệm thống nhất.

## 4. So sánh Entity và Value Object

| Tiêu chí | Entity | Value Object |
| --- | --- | --- |
| Cách nhận diện | Identity riêng | Giá trị của các thành phần |
| Equality | Theo identity hoặc khóa nghiệp vụ ổn định | Theo các thành phần giá trị |
| Vòng đời | Có thể tồn tại độc lập và được tham chiếu | Thường phụ thuộc entity sở hữu |
| Thay đổi trạng thái | Cập nhật cùng một identity | Thường thay bằng một giá trị mới |
| Khóa chính | Thường cần `@Id`/`@EmbeddedId` trong JPA | Không cần identity riêng |
| Repository | Thường có repository nếu cần truy vấn/quản lý độc lập | Thường truy cập qua entity sở hữu |
| Ánh xạ JPA phổ biến | `@Entity` | `@Embeddable`, `@Embedded`, `@ElementCollection` hoặc kiểu cơ bản/converter |
| Ví dụ | Customer, Product, Order | Money, Address, DateRange, Coordinates |

Đây là quy tắc thiết kế domain, không phải phân loại dựa trên số lượng field. Một object chỉ có một field vẫn có thể là value object; một entity có thể có nhiều field giống nhau nhưng vẫn được nhận diện bằng identity.

## 5. Đừng nhầm khái niệm domain với annotation JPA

Entity và Value Object là khái niệm thiết kế domain, thường được nhắc đến trong Domain-Driven Design (DDD). `@Entity` và `@Embeddable` là các annotation ánh xạ persistence của Jakarta Persistence.

Trong mô hình thông thường, Domain Entity thường được ánh xạ bằng JPA `@Entity`; Domain Value Object thường được ánh xạ bằng `@Embeddable`/`@Embedded`, hoặc lưu như kiểu cơ bản, `@ElementCollection`, converter hay cấu trúc phù hợp khác.

Hai cặp khái niệm không hoàn toàn đồng nhất. Một kiểu domain value object có thể được lưu bằng converter hoặc JSON thay vì `@Embeddable`. Một JPA entity cũng không tự động trở thành aggregate root trong DDD. Aggregate root là quyết định về ranh giới nhất quán nghiệp vụ, không phải tên annotation.

## 6. Ánh xạ Entity bằng @Entity

Ví dụ `CustomerEntity` là entity vì khách hàng có identity riêng, có thể được đơn hàng tham chiếu và có vòng đời quản lý độc lập.

```java
package com.example.learning.customer;

import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer_identity_examples")
@Access(AccessType.FIELD)
public class CustomerEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    protected CustomerEntity() {
        // Constructor dành cho JPA.
    }

    public CustomerEntity(String name) {
        this.name = requireText(name, "name");
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public void rename(String newName) {
        this.name = requireText(newName, "newName");
    }

    private static String requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        return value.trim();
    }
}
```

`id` là identity được database sinh ra. Khi tên khách hàng thay đổi qua `rename`, identity vẫn giữ nguyên. JPA theo dõi trạng thái entity trong persistence context và đồng bộ thay đổi xuống database khi flush.

Entity thường được truy cập qua repository:

```java
package com.example.learning.customer;

import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerEntityRepository
        extends JpaRepository<CustomerEntity, Long> {
}
```

Repository thao tác entity theo khóa chính. Đây là khác biệt quan trọng so với value object: ta thường hỏi “Customer có id nào?” hoặc “Tìm Customer theo email?”, còn với Address ta thường đọc hoặc thay thế giá trị địa chỉ của một Customer.

## 7. Ánh xạ Value Object bằng @Embeddable và @Embedded

JPA cho phép mô tả một nhóm field như một kiểu có thể nhúng vào entity. Lớp giá trị được đánh dấu `@Embeddable`; thuộc tính của entity dùng `@Embedded` để nhúng các cột của nó vào bảng của entity sở hữu.

Ví dụ `Address` không có khóa chính riêng và không có vòng đời độc lập. Nó chỉ mô tả địa chỉ hiện tại của khách hàng:

```java
package com.example.learning.customer;

import java.util.Objects;
import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

@Embeddable
@Access(AccessType.FIELD)
public class Address {
    @Column(name = "street_name", nullable = false, length = 160)
    private String street;

    @Column(name = "city_name", nullable = false, length = 100)
    private String city;

    protected Address() {
        // Constructor dành cho JPA.
    }

    public Address(String street, String city) {
        this.street = requireText(street, "street");
        this.city = requireText(city, "city");
    }

    public String getStreet() {
        return street;
    }

    public String getCity() {
        return city;
    }

    public Address withCity(String newCity) {
        return new Address(street, newCity);
    }

    private static String requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        return value.trim();
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
            && Objects.equals(city, address.city);
    }

    @Override
    public int hashCode() {
        return Objects.hash(street, city);
    }
}
```

`Address` có constructor không tham số `protected` cho JPA, còn code nghiệp vụ tạo object qua constructor có kiểm tra dữ liệu. Không có `@Id`, vì Address không có identity độc lập trong mô hình này. `equals` và `hashCode` dựa trên các thành phần giá trị.

Entity nhúng Address:

```java
package com.example.learning.customer;

import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
import jakarta.persistence.Embedded;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers_with_address")
@Access(AccessType.FIELD)
public class CustomerWithAddress {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    @Embedded
    private Address address;

    protected CustomerWithAddress() {
    }

    public CustomerWithAddress(String name, Address address) {
        this.name = name;
        this.address = requireAddress(address);
    }

    public Long getId() {
        return id;
    }

    public Address getAddress() {
        return address;
    }

    public void changeAddress(Address newAddress) {
        this.address = requireAddress(newAddress);
    }

    private static Address requireAddress(Address address) {
        if (address == null) {
            throw new IllegalArgumentException("address must not be null");
        }
        return address;
    }
}
```

Với field access, Hibernate đọc các field của Address và ánh xạ chúng thành các cột trong cùng bảng `customers_with_address`. Không có bảng `addresses` chỉ vì có một class `Address`. Khi đổi địa chỉ, entity vẫn là cùng Customer; giá trị Address được thay thế.

Với entity có field tính toán không lưu vào database, có thể đánh dấu member được chọn làm persistent access point bằng `@Transient`. Ví dụ `displayLabel` được tính từ `street` và `city` có thể là thuộc tính dẫn xuất; nó không cần cột riêng. Đặt `@Transient` trên field khi dùng FIELD access hoặc trên getter khi dùng PROPERTY access.

### 7.1. Nhúng cùng một kiểu nhiều lần bằng @AttributeOverride

Nếu Customer có cả địa chỉ thanh toán và địa chỉ giao hàng, cùng kiểu `Address` được nhúng hai lần. Vì hai nhóm cột cần tên riêng, dùng `@AttributeOverride` hoặc `@AttributeOverrides` để đổi tên cột:

```java
@Embedded
@AttributeOverrides({
    @AttributeOverride(
        name = "street",
        column = @Column(name = "billing_street", nullable = false)
    ),
    @AttributeOverride(
        name = "city",
        column = @Column(name = "billing_city", nullable = false)
    )
})
private Address billingAddress;

@Embedded
@AttributeOverrides({
    @AttributeOverride(
        name = "street",
        column = @Column(name = "shipping_street", nullable = false)
    ),
    @AttributeOverride(
        name = "city",
        column = @Column(name = "shipping_city", nullable = false)
    )
})
private Address shippingAddress;
```

Đây là đoạn trích để đặt trong entity đã khai báo `@Entity` và có các import Jakarta Persistence tương ứng. `name` trong `@AttributeOverride` là tên thuộc tính Java của embeddable (`street`, `city`), còn `column.name` là tên cột trong bảng entity sở hữu.

## 8. Collection các Value Object bằng @ElementCollection

Khi entity sở hữu nhiều giá trị cùng loại, có thể dùng `@ElementCollection`. Các giá trị cơ bản hoặc embeddable được lưu trong collection table và gắn với entity sở hữu thông qua khóa ngoại.

Ví dụ khách hàng có nhiều tag dạng chuỗi:

```java
@ElementCollection
@CollectionTable(
    name = "customer_tags",
    joinColumns = @JoinColumn(name = "customer_id")
)
@Column(name = "tag_value", nullable = false, length = 50)
private Set<String> tags = new HashSet<>();
```

Đây là đoạn trích đặt trong entity Customer. Các import cần có gồm `jakarta.persistence.ElementCollection`, `CollectionTable`, `JoinColumn`, `Column` và `java.util.Set`/`HashSet`.

Collection table `customer_tags` có cột liên kết `customer_id` và cột giá trị `tag_value`. Mỗi tag không cần một entity hay repository riêng. Khi Customer bị xóa, các hàng thuộc collection thường được xử lý theo quan hệ sở hữu của collection mapping.

Có thể dùng collection của embeddable khi giá trị có nhiều thành phần:

```java
package com.example.learning.customer;

import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

@Embeddable
@Access(AccessType.FIELD)
public class ContactPoint {
    @Column(name = "contact_type", nullable = false, length = 30)
    private String type;

    @Column(name = "contact_value", nullable = false, length = 160)
    private String value;

    protected ContactPoint() {
    }

    public ContactPoint(String type, String value) {
        this.type = type;
        this.value = value;
    }
}
```

Trong entity:

```java
@ElementCollection
@CollectionTable(
    name = "customer_contact_points",
    joinColumns = @JoinColumn(name = "customer_id")
)
@OrderColumn(name = "position_index")
private List<ContactPoint> contactPoints = new ArrayList<>();
```

`@OrderColumn` lưu thứ tự phần tử của List. Nếu thứ tự không có ý nghĩa, có thể chọn `Set` và triển khai equality/hashCode phù hợp cho embeddable. Các collection value vẫn thuộc vòng đời của Customer, không có identity độc lập.

## 9. Equality: identity của Entity và giá trị của Value Object

Đây là khác biệt quan trọng nhất khi thiết kế `equals()` và `hashCode()`.

### Value Object

Value Object so sánh theo toàn bộ thành phần có ý nghĩa của giá trị. Với Address, hai object có cùng street và city có thể bằng nhau dù được tạo ở hai thời điểm khác nhau.

Value Object thường nên bất biến. Thay vì sửa một Address đang nằm trong `HashSet`, hãy tạo Address mới và thay thế giá trị cũ. Nếu một object được dùng làm key của `HashMap` hoặc phần tử `HashSet`, thay đổi field tham gia `hashCode` sau khi thêm vào collection có thể khiến không tìm lại được phần tử.

### Entity

Entity được nhận diện bằng identity. Hai Customer có cùng tên và địa chỉ nhưng id khác nhau vẫn là hai entity khác nhau. Ngược lại, một Customer đổi tên hoặc địa chỉ vẫn là cùng entity nếu identity không đổi.

Viết `equals()` cho entity JPA cần cẩn trọng:

- ID do database sinh có thể là `null` trước khi persist; hai entity mới không được xem là bằng nhau chỉ vì cả hai cùng có id null.
- Nếu `hashCode()` thay đổi sau khi persist và entity đang nằm trong `HashSet`, collection có thể bị hỏng về mặt tra cứu.
- Hibernate có thể dùng proxy subclass; so sánh class bằng `getClass()` một cách ngây thơ có thể tạo kết quả không mong muốn với proxy.
- Dùng field có thể thay đổi như `name` hoặc `address` làm equality sẽ khiến entity thay đổi danh tính theo dữ liệu.

Không có một implementation `equals/hashCode` phù hợp cho mọi entity. Hãy chọn chiến lược identity hoặc natural key ổn định, duy nhất, bất biến theo nghiệp vụ; cân nhắc proxy của provider; và kiểm thử cả trạng thái transient, managed, detached. Nếu chưa cần entity làm phần tử của hash collection, đừng tự viết equality phức tạp theo một mẫu sao chép mà không hiểu hệ quả.

## 10. Khi nào một Value Object nên trở thành Entity?

Một giá trị có thể bắt đầu như Value Object rồi trở thành Entity khi yêu cầu nghiệp vụ thay đổi. Ví dụ `Address` ban đầu chỉ là địa chỉ nhúng trong Customer. Nhưng nếu hệ thống cần:

- Định danh địa chỉ và cho phép nhiều khách hàng cùng tham chiếu một địa chỉ đã xác minh.
- Quản lý lịch sử, trạng thái xác minh, người xác minh hoặc thời điểm hiệu lực riêng.
- Liên kết địa chỉ với đơn giao hàng, khu vực, tuyến vận chuyển hoặc hồ sơ khác.
- Cập nhật địa chỉ độc lập mà không thay thế trạng thái của Customer.

thì một entity `Address` có identity và repository riêng có thể phù hợp hơn. Lúc đó cần quyết định quan hệ sở hữu, khóa ngoại, cascade và chính sách xóa rõ ràng.

Ngược lại, đừng tạo Entity chỉ vì một object có nhiều field hoặc vì muốn đặt nó vào một bảng riêng. Hãy hỏi object có identity và vòng đời nghiệp vụ riêng hay không.

## 11. Quan hệ Entity với Value Object

Entity thường sở hữu hoặc chứa value object:

```text
Customer (Entity, customer_id)
├── name
├── Address (Value Object)
│   ├── street
│   └── city
└── tags (Collection of Value Objects)
    ├── "priority"
    └── "newsletter"
```

Trong ví dụ này, Customer có identity và vòng đời riêng; Address mô tả giá trị địa chỉ hiện tại; Tags là các giá trị thuộc Customer. Nếu Customer thay đổi Address hoặc tag, Customer vẫn giữ identity.

Trong DDD, entity sở hữu value object thường nằm trong cùng aggregate. Aggregate root kiểm soát các thay đổi để bảo vệ invariant. Tuy nhiên, không phải cứ `@Embedded` là aggregate root, và không phải mọi quan hệ JPA đều tương đương ranh giới aggregate. Hãy xác định ranh giới nghiệp vụ trước rồi mới chọn mapping.

## 12. Lỗi thiết kế và ánh xạ thường gặp

| Cách làm | Vấn đề | Cách cải thiện |
| --- | --- | --- |
| Tạo `@Entity` cho mọi class | Sinh quá nhiều identity, repository và quan hệ | Chỉ dùng Entity khi có identity/vòng đời riêng |
| Dùng `@Embeddable` cho object cần được tham chiếu độc lập | Không có identity để các entity khác tham chiếu trực tiếp | Chuyển thành entity nếu yêu cầu nghiệp vụ cần định danh |
| Value Object có setter công khai và bị sửa tùy ý | Equality và invariant dễ thay đổi ngoài kiểm soát | Ưu tiên API bất biến, thay object mới |
| Không override cột khi nhúng cùng kiểu hai lần | Trùng tên cột trong cùng bảng | Dùng `@AttributeOverride(s)` |
| Dùng `Set` cho embeddable nhưng không có equality phù hợp | Phần tử trùng giá trị hoặc hành vi collection khó đoán | Triển khai equality/hashCode theo giá trị |
| Dùng field mutable của Entity trong hashCode | Entity đổi hash khi trạng thái đổi | Dựa trên identity/natural key ổn định và hiểu vòng đời ID |
| Cho rằng `@Embeddable` luôn tạo bảng riêng | Hiểu sai mapping | `@Embedded` thường đưa các cột vào bảng của entity sở hữu; `@ElementCollection` dùng collection table |
| Cho rằng Value Object không bao giờ có thể lưu riêng | Nhầm khái niệm domain với cách lưu | Chọn converter, JSON hoặc mapping phù hợp; nếu cần identity riêng, đánh giá lại thành Entity |

## 13. Quy trình thiết kế

1. Xác định object có identity nghiệp vụ ổn định hay không.
2. Hỏi object có vòng đời độc lập và có cần được tham chiếu từ nhiều nơi không.
3. Nếu chỉ là giá trị, xác định đầy đủ các thành phần tạo nên equality.
4. Ưu tiên bất biến cho Value Object; kiểm tra null, khoảng giá trị, định dạng và quy tắc nghiệp vụ ngay khi tạo.
5. Chọn cách lưu: kiểu cơ bản, `@Embeddable`/`@Embedded`, `@ElementCollection`, converter hoặc cấu trúc phù hợp khác.
6. Nếu nhúng cùng kiểu nhiều lần, đặt tên cột bằng `@AttributeOverride(s)`.
7. Nếu là Entity, xác định identity, quan hệ, cascade, orphan removal và ranh giới transaction.
8. Viết test cho equality, persist, load, update và xóa theo đúng vòng đời.
9. Kiểm tra schema và SQL sinh ra để bảo đảm mapping phản ánh đúng mô hình.

## 14. Ví dụ kiểm thử Value Object và Entity

Test equality của Address:

```java
package com.example.learning.customer;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class AddressTest {
    @Test
    void sameComponentsRepresentSameValue() {
        Address first = new Address("1 Main Street", "Hanoi");
        Address second = new Address("1 Main Street", "Hanoi");

        assertThat(first).isEqualTo(second);
        assertThat(first.hashCode()).isEqualTo(second.hashCode());
    }
}
```

Test này kiểm tra equality theo giá trị. Nó không cần database vì equality của Address là quy tắc domain thuần.

Với Customer, integration test nên xác nhận hai entity được persist có identity khác nhau ngay cả khi các field nghiệp vụ giống nhau, và khi đổi địa chỉ thì id của Customer vẫn giữ nguyên. Có thể dùng `@DataJpaTest` với database kiểm thử và `EntityManager` để kiểm tra.

```java
package com.example.learning.customer;

import static org.assertj.core.api.Assertions.assertThat;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class CustomerWithAddressTest {
    @PersistenceContext
    private EntityManager entityManager;

    @Test
    void customerIdentityRemainsWhenAddressChanges() {
        CustomerWithAddress customer = new CustomerWithAddress(
            "Ada", new Address("1 Main Street", "Hanoi")
        );
        entityManager.persist(customer);
        entityManager.flush();
        Long originalId = customer.getId();

        customer.changeAddress(new Address("2 Lake Road", "Hanoi"));
        entityManager.flush();
        entityManager.clear();

        CustomerWithAddress reloaded = entityManager.find(
            CustomerWithAddress.class, originalId
        );
        assertThat(reloaded.getId()).isEqualTo(originalId);
        assertThat(reloaded.getAddress().getStreet()).isEqualTo("2 Lake Road");
    }
}
```

Đây là test trong cùng package với `CustomerWithAddress` và `Address`, với `spring-boot-starter-data-jpa` cùng database kiểm thử. `flush()` ghi thay đổi xuống database trong transaction test; `clear()` loại entity khỏi persistence context để lần `find` tiếp theo phải nạp lại từ database.

## Kết luận

Entity được nhận diện bằng identity và có vòng đời riêng; Value Object được nhận diện bằng giá trị và thường phụ thuộc entity sở hữu. Trong JPA, dùng `@Entity` cho đối tượng cần định danh, `@Embeddable`/`@Embedded` cho giá trị nhúng, và `@ElementCollection` cho tập hợp giá trị. Hãy để yêu cầu nghiệp vụ quyết định mô hình, giữ Value Object bất biến khi có thể và kiểm thử equality cũng như vòng đời persistence để tránh mapping phức tạp không cần thiết.