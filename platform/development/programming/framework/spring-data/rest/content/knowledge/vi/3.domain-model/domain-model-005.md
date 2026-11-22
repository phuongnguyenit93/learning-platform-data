# Thuộc tính đơn, đối tượng lồng và quan hệ giữa các thực thể

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt thuộc tính đơn, value object được nhúng và quan hệ giữa các entity.
- Chọn đúng mapping JPA cho từng loại dữ liệu.
- Giải thích dữ liệu nào xuất hiện trực tiếp trong JSON và dữ liệu nào được Spring Data REST biểu diễn bằng HAL link.
- Thiết kế quan hệ một-một, một-nhiều, nhiều-một và nhiều-nhiều.
- Dùng association resource để đọc và thay đổi quan hệ qua HTTP.
- Tránh lỗi về owning side, cascade, vòng lặp JSON, lazy loading và lộ dữ liệu.

## 1. Phân loại thuộc tính trong domain model

Một entity thường chứa nhiều loại thông tin. Ví dụ một đơn hàng có mã đơn, ngày tạo, trạng thái, địa chỉ giao hàng và khách hàng đặt đơn. Dù tất cả đều xuất hiện dưới dạng field trong Java, chúng không có cùng ý nghĩa trong mô hình miền.

Với Jakarta Persistence, trạng thái của entity có thể được phân loại thành:

| Loại thuộc tính | Ví dụ | Ý nghĩa |
|---|---|---|
| BASIC (thuộc tính đơn) | orderNumber, status, createdAt, totalAmount | Giá trị thuộc trực tiếp về entity |
| EMBEDDED (đối tượng nhúng) | shippingAddress, money, contactInfo | Nhóm giá trị mô tả một phần trạng thái của entity, không có identity riêng |
| ELEMENT_COLLECTION | tags, phoneNumbers, danh sách mã phụ | Tập hợp giá trị đơn hoặc embeddable, không phải tập hợp entity |
| ENTITY RELATIONSHIP | customer, items, assignedEmployee | Tham chiếu tới entity khác có identity riêng |

Sự phân loại này quyết định cách JPA lưu dữ liệu và cách Spring Data REST biểu diễn domain model qua HTTP.

Ví dụ:

- orderNumber là một giá trị đơn, được trả về như property trong JSON.
- shippingAddress là một value object, thường được trả về như object JSON lồng bên trong đơn hàng.
- customer là một entity khác, nên Spring Data REST thường tạo HAL link để client truy cập customer resource.
- items có thể là quan hệ tới các entity OrderItem, hoặc element collection, tùy theo identity và ý nghĩa nghiệp vụ của từng item.

Đừng quyết định chỉ dựa trên việc dữ liệu trông giống một object JSON. Hãy hỏi: đối tượng này có identity và vòng đời độc lập không? Nó có thể được tham chiếu từ nhiều entity không? Người dùng có thể truy cập hoặc cập nhật nó như một tài nguyên độc lập không?

## 2. Thuộc tính đơn (basic attributes)

Thuộc tính đơn là những giá trị thuộc trực tiếp về entity, không cần một entity khác để biểu diễn.

Các kiểu Java thường gặp gồm:

- Chuỗi: String.
- Số nguyên: int, long, Integer, Long.
- Số thập phân: BigDecimal, thường phù hợp với tiền và số cần độ chính xác.
- Boolean: boolean, Boolean.
- Ngày giờ: LocalDate, LocalDateTime, Instant, OffsetDateTime.
- Enum: trạng thái, loại nghiệp vụ, nhóm phân loại.
- UUID và các kiểu cơ bản được Jakarta Persistence hỗ trợ.

Ví dụ:

```java
@Entity
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 40)
    private String orderNumber;

    @Column(nullable = false, precision = 15, scale = 2)
    private BigDecimal totalAmount;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private OrderStatus status;

    private Instant createdAt;

    protected PurchaseOrder() {
    }
}
```

Một vài điểm cần chú ý:

- @Column(nullable = false) mô tả ràng buộc cột trong schema; hãy dùng thêm Bean Validation như @NotBlank, @NotNull hoặc @Positive khi cần xác thực dữ liệu đầu vào ở tầng ứng dụng.
- Với tiền, dùng BigDecimal thay vì double để tránh sai số biểu diễn số thực. Khai báo precision và scale phù hợp với quy tắc nghiệp vụ.
- Với enum, @Enumerated(EnumType.STRING) lưu tên enum. Cách này dễ đọc và ổn định hơn ORDINAL, vì thay đổi thứ tự khai báo enum không làm đổi ý nghĩa dữ liệu cũ.
- Dùng Instant cho thời điểm tuyệt đối hoặc OffsetDateTime khi cần giữ offset. Dùng LocalDate cho ngày lịch không có thời gian hay múi giờ.
- @Column(name = "...") đổi tên cột trong cơ sở dữ liệu; nó không tự đổi tên property JSON. Hợp đồng JSON được quyết định bởi tên property và cấu hình Jackson.

Trong representation của Spring Data REST, các thuộc tính đơn thường xuất hiện trực tiếp trong document:

```json
{
  "orderNumber": "PO-1001",
  "totalAmount": 1250000.00,
  "status": "DRAFT",
  "createdAt": "2026-11-11T07:30:00Z"
}
```

Đây là các giá trị của chính order. Chúng không tạo collection endpoint hoặc association link riêng.

## 3. Đối tượng lồng và value object với @Embeddable

### 3.1. Khi nào nên dùng đối tượng nhúng?

Một value object gom các giá trị liên quan thành một khái niệm có ý nghĩa trong domain model, nhưng không cần identity độc lập.

Ví dụ:

- Địa chỉ gồm đường, thành phố, mã bưu chính và quốc gia.
- Khoảng thời gian gồm thời điểm bắt đầu và kết thúc.
- Tiền tệ gồm số tiền và đơn vị tiền.
- Tọa độ gồm vĩ độ và kinh độ.

Địa chỉ giao hàng của một đơn hàng thường là một phần trạng thái của đơn hàng. Nếu không có yêu cầu nghiệp vụ để quản lý địa chỉ như tài nguyên độc lập, tạo một entity Address chỉ để gom bốn field có thể làm mô hình phức tạp không cần thiết.

Trong JPA:

- Đánh dấu lớp value object bằng @Embeddable.
- Đánh dấu field chứa nó trong entity bằng @Embedded.
- Các field của embeddable được ánh xạ vào bảng của entity sở hữu nó.
- Embeddable không có khóa chính và identity persistent riêng.
- Một embeddable thuộc về entity sở hữu nó; không dùng cùng một instance như một entity độc lập được chia sẻ giữa nhiều entity.

### 3.2. Ví dụ Address

File Address.java:

```java
package com.example.orders.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

@Embeddable
public class Address {

    @Column(nullable = false, length = 180)
    private String street;

    @Column(nullable = false, length = 100)
    private String city;

    @Column(length = 20)
    private String postalCode;

    @Column(nullable = false, length = 2)
    private String countryCode;

    protected Address() {
    }

    public Address(
            String street,
            String city,
            String postalCode,
            String countryCode) {
        this.street = street;
        this.city = city;
        this.postalCode = postalCode;
        this.countryCode = countryCode;
    }

    public String getStreet() {
        return street;
    }

    public void setStreet(String street) {
        this.street = street;
    }

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }

    public String getPostalCode() {
        return postalCode;
    }

    public void setPostalCode(String postalCode) {
        this.postalCode = postalCode;
    }

    public String getCountryCode() {
        return countryCode;
    }

    public void setCountryCode(String countryCode) {
        this.countryCode = countryCode;
    }
}
```

File Customer.java sử dụng Address:

```java
package com.example.orders.domain;

import jakarta.persistence.Column;
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

    @Column(nullable = false, length = 120)
    private String fullName;

    @Column(nullable = false, unique = true, length = 180)
    private String email;

    @Embedded
    private Address address;

    protected Customer() {
    }

    public Customer(String fullName, String email, Address address) {
        this.fullName = fullName;
        this.email = email;
        this.address = address;
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public void setFullName(String fullName) {
        this.fullName = fullName;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public Address getAddress() {
        return address;
    }

    public void setAddress(Address address) {
        this.address = address;
    }
}
```

Bảng customers có các cột tương ứng với fullName, email, street, city, postalCode và countryCode. Không có bảng addresses chỉ vì code có lớp Address.

### 3.3. Representation JSON của đối tượng nhúng

Khi Spring Data REST trả về customer, address là object lồng:

```json
{
  "fullName": "Nguyen An",
  "email": "an@example.com",
  "address": {
    "street": "12 Le Loi",
    "city": "Ho Chi Minh City",
    "postalCode": "700000",
    "countryCode": "VN"
  }
}
```

Client gửi object lồng tương ứng khi tạo hoặc cập nhật customer. Đây là dữ liệu của customer; không cần gọi endpoint /addresses để tạo address riêng.

Điều này khác với quan hệ entity: entity liên quan có identity và repository riêng, vì vậy Spring Data REST có thể xuất bản link để client điều hướng tới tài nguyên đó.

### 3.4. Dùng lại một embeddable type nhiều lần

Một entity có thể chứa nhiều field cùng kiểu Address, chẳng hạn billingAddress và shippingAddress. Khi đó các field trong embeddable cần ánh xạ vào những cột khác nhau. Dùng @AttributeOverride để đặt tên cột:

```java
@Embedded
@AttributeOverrides({
    @AttributeOverride(
        name = "street",
        column = @Column(name = "billing_street")
    ),
    @AttributeOverride(
        name = "city",
        column = @Column(name = "billing_city")
    ),
    @AttributeOverride(
        name = "postalCode",
        column = @Column(name = "billing_postal_code")
    ),
    @AttributeOverride(
        name = "countryCode",
        column = @Column(name = "billing_country_code")
    )
})
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
    ),
    @AttributeOverride(
        name = "countryCode",
        column = @Column(name = "shipping_country_code")
    )
})
private Address shippingAddress;
```

Các field vẫn thuộc entity sở hữu; billingAddress và shippingAddress không trở thành hai entity có ID riêng.

### 3.5. Collection của giá trị đơn hoặc embeddable

Nếu entity có nhiều giá trị đơn hoặc value object nhưng mỗi phần tử không cần identity riêng, cân nhắc @ElementCollection.

Ví dụ:

```java
@ElementCollection
@CollectionTable(
    name = "customer_tags",
    joinColumns = @JoinColumn(name = "customer_id")
)
@Column(name = "tag")
private Set<String> tags = new LinkedHashSet<>();
```

@ElementCollection ánh xạ collection sang collection table. Nếu mỗi phần tử cần được tham chiếu độc lập, có trạng thái riêng hoặc có vòng đời độc lập, hãy cân nhắc entity thay vì element collection.

## 4. Quan hệ giữa các entity

### 4.1. Khi nào một đối tượng nên là entity?

Một đối tượng nên là entity khi nó có identity riêng và được quản lý như một đối tượng nghiệp vụ độc lập.

Ví dụ:

- Một PurchaseOrder có mã đơn và vòng đời riêng.
- Một Customer có thể được nhiều đơn hàng tham chiếu.
- Một Product có thể xuất hiện trong nhiều đơn hàng.
- Một Employee có thể được phân công cho nhiều nhiệm vụ.

Trong JPA, các quan hệ entity có bốn dạng chính:

| Annotation | Ý nghĩa | Ví dụ |
|---|---|---|
| @OneToOne | Một entity liên kết tối đa một entity khác | User và UserProfile |
| @ManyToOne | Nhiều entity cùng tham chiếu một entity | Nhiều đơn hàng thuộc một customer |
| @OneToMany | Một entity liên kết với nhiều entity khác | Một customer có nhiều đơn hàng |
| @ManyToMany | Nhiều entity ở hai phía liên kết nhiều-nhiều | Student và Course |

Quan hệ trong object model được ánh xạ xuống khóa ngoại hoặc bảng nối. Spring Data REST nhận diện các association này và cung cấp link/association resource khi repository liên quan được export.

### 4.2. Ví dụ Many-to-One và One-to-Many

Giả sử mỗi đơn hàng thuộc một customer, và một customer có thể có nhiều đơn hàng.

Quan hệ nghiệp vụ:

```text
Customer 1 ─────────── * PurchaseOrder
          một-nhiều

PurchaseOrder * ───── 1 Customer
              nhiều-một
```

Trong cơ sở dữ liệu, khóa ngoại customer_id thường nằm ở bảng purchase_orders.

File PurchaseOrder.java:

```java
package com.example.orders.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 40)
    private String orderNumber;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private OrderStatus status;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(
            String orderNumber,
            OrderStatus status,
            Customer customer) {
        this.orderNumber = orderNumber;
        this.status = status;
        this.customer = customer;
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public void setOrderNumber(String orderNumber) {
        this.orderNumber = orderNumber;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public void setStatus(OrderStatus status) {
        this.status = status;
    }

    public Customer getCustomer() {
        return customer;
    }

    public void setCustomer(Customer customer) {
        this.customer = customer;
    }
}
```

File OrderStatus.java:

```java
package com.example.orders.domain;

public enum OrderStatus {
    DRAFT,
    CONFIRMED,
    SHIPPED,
    CANCELLED
}
```

Thêm phía ngược lại vào Customer.java:

```java
@OneToMany(mappedBy = "customer")
private List<PurchaseOrder> orders = new ArrayList<>();

public List<PurchaseOrder> getOrders() {
    return orders;
}

public void addOrder(PurchaseOrder order) {
    orders.add(order);
    order.setCustomer(this);
}
```

Nhớ thêm import:

```java
import java.util.ArrayList;
import java.util.List;
import jakarta.persistence.OneToMany;
```

Giải thích:

- PurchaseOrder.customer dùng @ManyToOne và là owning side trong ví dụ này vì nó chứa khóa ngoại customer_id.
- Customer.orders dùng @OneToMany(mappedBy = "customer"). mappedBy trỏ tới tên field ở owning side, không phải tên cột database.
- Khi thay đổi quan hệ trong code Java, hãy cập nhật cả hai phía của quan hệ hai chiều. addOrder làm việc đó bằng cách thêm order vào collection và gán customer cho order.
- FetchType.LAZY tránh tải customer cùng mọi order trong các truy vấn không cần quan hệ đó. Hãy thiết kế truy vấn và transaction phù hợp với cách ứng dụng sử dụng dữ liệu.

### 4.3. One-to-One

Dùng @OneToOne khi mỗi phía liên kết tối đa một đối tượng ở phía còn lại. Ví dụ một user có một profile riêng. Thông thường database cần một khóa ngoại có unique constraint hoặc một chiến lược shared primary key.

Không dùng One-to-One chỉ vì hai object thường xuất hiện cạnh nhau trong JSON. Nếu dữ liệu không có identity riêng và chỉ là một phần trạng thái của user, @Embedded có thể phù hợp hơn.

### 4.4. Many-to-Many

Dùng @ManyToMany khi nhiều entity phía A có thể liên kết nhiều entity phía B, và bản thân mối liên kết không cần thuộc tính nghiệp vụ riêng. JPA thường ánh xạ quan hệ này bằng join table.

Ví dụ Student và Course có thể có quan hệ nhiều-nhiều. Nếu quan hệ đăng ký học cần các thuộc tính như enrolledAt, grade, status hoặc attemptNumber, hãy mô hình hóa một entity trung gian như Enrollment thay vì giữ một @ManyToMany đơn giản.

### 4.5. Khi quan hệ cần trở thành entity riêng

Giả sử một đơn hàng có nhiều sản phẩm. Nếu mỗi dòng hàng cần số lượng, giá tại thời điểm mua, chiết khấu và trạng thái thực hiện, OrderItem là một entity hoặc child entity có dữ liệu nghiệp vụ riêng:

```text
PurchaseOrder 1 ───── * OrderItem * ───── 1 Product

OrderItem:
- quantity
- unitPriceAtPurchase
- discount
- fulfillmentStatus
```

Mối quan hệ giữa order và product giờ được biểu diễn qua OrderItem. Điều này giúp lưu lịch sử giá và thông tin của từng dòng hàng mà một field List<Product> không thể mô tả đầy đủ.

## 5. Spring Data REST biểu diễn đối tượng nhúng và quan hệ entity thế nào?

Spring Data REST mặc định dùng HAL cho representation JSON. HAL đặt các liên kết dưới property _links. Client đọc link để khám phá và điều hướng tới tài nguyên liên quan.

### 5.1. Giá trị đơn và embeddable nằm trong representation

Các field đơn và value object được sao chép vào representation của entity. Ví dụ customer có thể có nội dung:

```json
{
  "fullName": "Nguyen An",
  "email": "an@example.com",
  "address": {
    "street": "12 Le Loi",
    "city": "Ho Chi Minh City",
    "postalCode": "700000",
    "countryCode": "VN"
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/customers/1"
    },
    "orders": {
      "href": "http://localhost:8080/api/customers/1/orders"
    }
  }
}
```

Trong ví dụ này:

- fullName, email là thuộc tính đơn.
- address là đối tượng nhúng.
- orders là quan hệ tới các entity PurchaseOrder, nên xuất hiện thành link.
- Link orders trỏ tới association resource của customer.

### 5.2. Quan hệ entity xuất hiện dưới dạng link

Một order có thể được trả về như sau:

```json
{
  "orderNumber": "PO-1001",
  "status": "DRAFT",
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/orders/1"
    },
    "customer": {
      "href": "http://localhost:8080/api/orders/1/customer"
    }
  }
}
```

Property customer không cần chứa toàn bộ object customer. Client theo link /api/orders/1/customer để lấy trạng thái quan hệ, rồi theo link được trả về để truy cập customer resource.

Cách biểu diễn này giúp API không phải serialize toàn bộ object graph mỗi lần đọc một entity. Client chỉ truy cập tài nguyên liên quan khi cần.

Lưu ý: _embedded trong HAL là nơi chứa tài nguyên được embed theo quy tắc representation/projection. Không được suy luận rằng mọi @Embedded của JPA sẽ được đặt trong HAL _embedded; một JPA embeddable thông thường là property object trong nội dung JSON, còn HAL _links biểu diễn liên kết tới tài nguyên khác.

### 5.3. Association resource

Với mỗi item resource, Spring Data REST có thể tạo sub-resource cho các association của entity. Path và relation name mặc định dựa trên tên property; có thể tùy chỉnh bằng @RestResource.

Với field PurchaseOrder.customer, association resource mặc định có dạng:

/api/orders/{orderId}/customer

Với field Customer.orders, association resource mặc định có dạng:

/api/customers/{customerId}/orders

Association resource hỗ trợ:

| HTTP method | Dùng cho | Nội dung |
|---|---|---|
| GET | To-one hoặc collection association | Đọc trạng thái quan hệ |
| PUT | Gắn resource URI vào quan hệ | Dùng text/uri-list; với to-one chỉ gửi một URI |
| POST | Collection association | Thêm một resource vào collection |
| DELETE | Association có thể tháo liên kết | Gỡ quan hệ; không xóa entity đích |

Ví dụ đổi customer của order 1 sang customer 2:

```bash
curl -i -X PUT \
  -H "Content-Type: text/uri-list" \
  --data "http://localhost:8080/api/customers/2" \
  http://localhost:8080/api/orders/1/customer
```

Body là URI của customer cần liên kết, không phải JSON object customer. Nếu association là bắt buộc (optional = false), thao tác DELETE để tháo liên kết có thể bị từ chối vì quan hệ không được phép rỗng.

Với collection association, POST thêm một resource đã tồn tại vào collection:

```bash
curl -i -X POST \
  -H "Content-Type: text/uri-list" \
  --data "http://localhost:8080/api/orders/1" \
  http://localhost:8080/api/customers/2/orders
```

Các thao tác này chỉ thay đổi quan hệ theo mapping và quy tắc của ứng dụng. Chúng không tự quyết định cascade remove, cascade persist hay các quy tắc nghiệp vụ khác.

## 6. Ví dụ ứng dụng chạy được

Ví dụ dưới đây dùng Spring Boot 4.1.2, Java 17+, Spring Data JPA, Spring Data REST và H2. Hai repository được export là Customer và PurchaseOrder. Address chỉ là embeddable, không có repository riêng.

### 6.1. Cấu trúc dự án

```text
orders-api/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/example/orders/
        │       ├── OrdersApplication.java
        │       ├── domain/
        │       │   ├── Address.java
        │       │   ├── Customer.java
        │       │   ├── OrderStatus.java
        │       │   └── PurchaseOrder.java
        │       └── repository/
        │           ├── CustomerRepository.java
        │           └── PurchaseOrderRepository.java
        └── resources/
            └── application.properties
```

### 6.2. Maven dependencies

File pom.xml:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>orders-api</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-rest</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Không khai báo version riêng cho các starter và H2 vì Spring Boot dependency management quản lý các phiên bản tương thích.

### 6.3. Repositories

File CustomerRepository.java:

```java
package com.example.orders.repository;

import com.example.orders.domain.Customer;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(
    path = "customers",
    collectionResourceRel = "customers"
)
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
```

File PurchaseOrderRepository.java:

```java
package com.example.orders.repository;

import com.example.orders.domain.PurchaseOrder;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(
    path = "orders",
    collectionResourceRel = "orders"
)
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {
}
```

### 6.4. Main application và dữ liệu mẫu

File OrdersApplication.java:

```java
package com.example.orders;

import com.example.orders.domain.Address;
import com.example.orders.domain.Customer;
import com.example.orders.domain.OrderStatus;
import com.example.orders.domain.PurchaseOrder;
import com.example.orders.repository.CustomerRepository;
import com.example.orders.repository.PurchaseOrderRepository;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }

    @Bean
    CommandLineRunner seedData(
            CustomerRepository customers,
            PurchaseOrderRepository orders) {

        return args -> {
            if (customers.count() == 0) {
                Customer first = customers.save(new Customer(
                    "Nguyen An",
                    "an@example.com",
                    new Address(
                        "12 Le Loi",
                        "Ho Chi Minh City",
                        "700000",
                        "VN"
                    )
                ));

                customers.save(new Customer(
                    "Tran Binh",
                    "binh@example.com",
                    new Address(
                        "25 Nguyen Hue",
                        "Ho Chi Minh City",
                        "700000",
                        "VN"
                    )
                ));

                orders.save(new PurchaseOrder(
                    "PO-1001",
                    OrderStatus.DRAFT,
                    first
                ));
            }
        };
    }
}
```

Dữ liệu mẫu tạo hai customer và một order thuộc customer thứ nhất. Dữ liệu được tạo một lần khi database H2 còn trống.

### 6.5. Cấu hình H2

File application.properties:

```properties
spring.datasource.url=jdbc:h2:mem:orders;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=

spring.jpa.hibernate.ddl-auto=create-drop
spring.data.rest.base-path=/api
```

create-drop chỉ phù hợp cho ví dụ và môi trường phát triển. Với dữ liệu thật, dùng migration tool như Flyway hoặc Liquibase và không để ứng dụng tự xóa schema khi tắt.

### 6.6. Chạy ứng dụng

Yêu cầu Java 17+ và Maven 3.6.3+ theo cấu hình Spring Boot 4.1.2.

```bash
./mvnw spring-boot:run
```

Trên Windows:

```powershell
.\mvnw.cmd spring-boot:run
```

Kiểm tra JDK và Maven Wrapper trước khi chạy:

```bash
java -version
./mvnw -version
```

### 6.7. Thử các resource

Đọc root resource để khám phá repository:

```bash
curl -H "Accept: application/hal+json" http://localhost:8080/api
```

Đọc customer 1:

```bash
curl -H "Accept: application/hal+json" http://localhost:8080/api/customers/1
```

Bạn sẽ thấy các property đơn, object address lồng và link tới collection orders.

Đọc order 1:

```bash
curl -H "Accept: application/hal+json" http://localhost:8080/api/orders/1
```

Representation có orderNumber, status và link customer. Theo link association để truy cập customer được liên kết.

Đọc trạng thái quan hệ:

```bash
curl -H "Accept: application/hal+json" http://localhost:8080/api/orders/1/customer
```

Đổi quan hệ sang customer 2:

```bash
curl -i -X PUT \
  -H "Content-Type: text/uri-list" \
  --data "http://localhost:8080/api/customers/2" \
  http://localhost:8080/api/orders/1/customer
```

Đọc lại order hoặc association resource để xác nhận customer đã được đổi.

## 7. Quy tắc thiết kế quan hệ an toàn

### 7.1. Phân biệt owning side và inverse side

Trong quan hệ hai chiều JPA, một phía sở hữu mapping và phía còn lại tham chiếu nó bằng mappedBy.

Với ví dụ Customer và PurchaseOrder:

- PurchaseOrder.customer là owning side vì nó giữ foreign key.
- Customer.orders là inverse side vì mappedBy = "customer".

Nếu chỉ thêm order vào collection Customer.orders mà không gán PurchaseOrder.customer, thay đổi quan hệ có thể không được ghi như mong muốn. Hãy duy trì cả hai phía trong helper method hoặc application service.

### 7.2. Chọn cascade theo vòng đời nghiệp vụ

Cascade quyết định thao tác persistence nào được lan truyền sang entity liên quan. Nó không phải công cụ để làm cho object graph tự động lưu mọi thứ.

- Không đặt CascadeType.REMOVE từ PurchaseOrder sang Customer nếu customer có thể được nhiều order dùng chung.
- Chỉ dùng cascade persist/merge khi vòng đời child thực sự phụ thuộc parent.
- orphanRemoval = true chỉ phù hợp khi bỏ child khỏi collection đồng nghĩa child phải bị xóa khỏi database.
- Không dùng CascadeType.ALL theo thói quen cho mọi quan hệ.

Trong ví dụ, order tham chiếu customer đã tồn tại nên không cascade remove từ order sang customer.

### 7.3. Tránh lặp vô hạn khi serialize

Quan hệ hai chiều có thể tạo vòng tham chiếu trong Java:

```text
Customer
  └── orders[]
        └── customer
              └── orders[]
                    └── ...
```

Spring Data REST xử lý entity association bằng HAL links theo cơ chế export mặc định. Nếu tự viết controller và serialize entity graph bằng Jackson, cần kiểm soát vòng lặp bằng DTO hoặc cấu hình serialization phù hợp. Không nên trả trực tiếp một object graph không giới hạn ra API.

### 7.4. Không tải toàn bộ object graph mặc định

FetchType.LAZY giúp tránh tải quan hệ khi chưa cần. Tuy nhiên, client có thể theo link association và phát sinh nhiều request nếu phải duyệt hàng trăm entity.

Khi cần representation đọc tổng hợp:

- Dùng projection để định nghĩa tập property mà client cần.
- Dùng excerpt projection cho collection resource khi phù hợp.
- Tạo endpoint/query chuyên biệt nếu cần tổng hợp dữ liệu phức tạp.
- Kiểm tra SQL và số lượng query để phát hiện N+1.
- Không chuyển mọi association sang EAGER chỉ để làm response JSON có vẻ đầy đủ.

### 7.5. Đừng biến mọi entity thành API công khai

Export repository đồng nghĩa Spring Data REST có thể tạo resource cho repository đó. Hãy quyết định rõ aggregate root nào được công khai.

Nếu không muốn export repository:

```java
@RepositoryRestResource(exported = false)
public interface InternalAuditRepository
        extends JpaRepository<InternalAudit, Long> {
}
```

Nếu muốn ẩn một association cụ thể khỏi API:

```java
@ManyToOne(fetch = FetchType.LAZY)
@RestResource(exported = false)
private InternalAudit audit;
```

Đặt @RestResource(path = "...", rel = "...") trên association property nếu cần tùy chỉnh path hoặc relation name. @JsonIgnore tác động đến Jackson serialization; nó không phải công cụ thay thế cho cấu hình export của Spring Data REST khi mục tiêu là quản lý association resource.

### 7.6. Phân biệt mô hình persistence và hợp đồng API

Spring Data REST giúp tạo API nhanh từ repository, nhưng domain entity không phải lúc nào cũng là request/response contract phù hợp.

Cần cân nhắc DTO hoặc controller/service riêng khi:

- API cần nhiều field tổng hợp từ nhiều entity.
- Client chỉ được phép sửa một phần nhỏ của entity.
- Có quy trình nghiệp vụ nhiều bước.
- Cần che field nhạy cảm hoặc thay đổi cấu trúc representation độc lập với database.
- Muốn giữ ổn định API khi đổi tên property hoặc tái cấu trúc domain model.

Projection phù hợp để điều chỉnh representation đọc. Với thao tác ghi phức tạp, dùng command/request model và application service để xác thực quy tắc nghiệp vụ.

## 8. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng @Entity cho một nhóm field chỉ để gom dữ liệu | Tạo thêm identity, bảng và repository không cần thiết | Dùng @Embeddable nếu object chỉ là state của entity sở hữu |
| Dùng @Embedded cho object có vòng đời độc lập | Không thể quản lý object như tài nguyên riêng | Dùng entity và quan hệ JPA phù hợp |
| Nghĩ @Embedded tự tạo endpoint riêng | Tìm endpoint không tồn tại | Chỉ repository của entity được export mới tạo collection resource |
| Nghĩ @ManyToOne sẽ nhúng toàn bộ entity vào JSON | Response có thể chỉ có HAL association link | Follow link association để lấy resource liên quan |
| Đặt mappedBy sai tên field | Hibernate báo mapping lỗi hoặc quan hệ không hoạt động | Dùng đúng tên property ở owning side |
| Chỉ cập nhật inverse side | Foreign key có thể không đổi | Cập nhật owning side và giữ hai phía đồng bộ |
| Cascade REMOVE tới entity dùng chung | Xóa một object có thể xóa dữ liệu đang được entity khác tham chiếu | Chọn cascade theo ownership và vòng đời |
| Dùng CascadeType.ALL cho mọi quan hệ | Thao tác lưu/xóa lan truyền ngoài ý muốn | Chỉ bật từng cascade operation cần thiết |
| Serialize quan hệ hai chiều bằng controller tùy chỉnh | JSON có thể lặp vô hạn hoặc quá lớn | Dùng DTO, HAL link hoặc kiểm soát serialization |
| Đổi tên field mà không xét API contract | JSON property và relation link có thể đổi | Dùng mapping/custom relation hoặc version API có chủ đích |
| Export tất cả repository | Lộ dữ liệu hoặc thao tác ghi không dự kiến | Giới hạn repository và association được export, áp dụng Spring Security |

## 9. Checklist khi thiết kế domain model

Trước khi thêm một field hoặc quan hệ, hãy trả lời:

1. Đây là giá trị đơn, value object, collection giá trị hay entity có identity?
2. Object có thể tồn tại và được tham chiếu độc lập với entity hiện tại không?
3. Nếu là embeddable, nó có thực sự thuộc vòng đời của entity sở hữu không?
4. Nếu là association, cardinality là một-một, một-nhiều hay nhiều-nhiều?
5. Phía nào sở hữu foreign key? mappedBy có đúng không?
6. Cascade và orphan removal có khớp với vòng đời nghiệp vụ không?
7. Spring Data REST sẽ xuất property JSON hay association link?
8. Repository nào được phép export? Client có được phép đọc và ghi quan hệ này không?
9. Response có nguy cơ tải quá nhiều dữ liệu hoặc tạo N+1 không?
10. Có cần projection, DTO hoặc endpoint nghiệp vụ riêng để giữ ổn định API không?

## 10. Tài liệu tham khảo chính thức

- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): collection, item, association resource, HAL links và HTTP methods.
- [Spring Data REST — Project](https://spring.io/projects/spring-data-rest/): cách Spring Data REST phân tích domain model và xuất bản hypermedia resource.
- [Jakarta Persistence 3.2 — Specification](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html): basic attributes, embeddable classes, element collections và entity relationships.
- [Jakarta Persistence — Embeddable API](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/embeddable): yêu cầu và ý nghĩa của @Embeddable.
- [Spring Boot 4.1.2 — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html): yêu cầu Java và build tool cho ví dụ.
- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/4.0/reference/data/sql.html): tích hợp JPA và Spring Data JPA trong Spring Boot.

Hãy dùng domain model để diễn đạt đúng ý nghĩa nghiệp vụ. Thuộc tính đơn lưu giá trị, embeddable gom các giá trị thuộc về entity sở hữu, còn association kết nối các entity có identity riêng. Spring Data REST phản ánh sự khác nhau đó trong JSON và HAL links; thiết kế đúng từ đầu giúp API dễ hiểu và dễ bảo trì.
