# Phân biệt entity, đối tượng giá trị, DTO và bản ghi trong bảng

Trong ứng dụng Java lưu dữ liệu bằng cơ sở dữ liệu quan hệ, cùng một thông tin có thể xuất hiện ở nhiều hình thức: **entity** đang được JPA quản lý, **đối tượng giá trị** nằm trong entity, **DTO** gửi cho API và **bản ghi (row)** được lưu trong bảng SQL. Bốn khái niệm này có thể chứa các trường trông giống nhau nhưng **khác nhau về danh tính, trách nhiệm, vòng đời và cách cập nhật**.

Bài học đặt chúng trong ngữ cảnh ORM (Object–Relational Mapping) với Jakarta Persistence API (JPA). Mục tiêu là hiểu bản chất từng loại, nhận ra ranh giới giữa mô hình đối tượng và mô hình quan hệ, đồng thời chọn cách biểu diễn dữ liệu phù hợp khi thiết kế ứng dụng.

## 1. Bức tranh tổng thể: một khách hàng, bốn góc nhìn

Giả sử hệ thống lưu thông tin khách hàng:

- Khách hàng có mã định danh `101`, tên `An`, địa chỉ `12 Nguyễn Trãi, Hà Nội, 100000`.
- Một khách hàng vẫn là **cùng khách hàng đó** khi đổi tên hoặc chuyển nhà.
- Địa chỉ có thể được mô tả bằng bộ ba `(đường, thành phố, mã bưu chính)`.
- API danh sách khách hàng chỉ trả `id`, `name` và `city`.
- Trong cơ sở dữ liệu, các cột này nằm trong một hoặc nhiều hàng của bảng.

Nhìn vào thông tin trên ta có:

| Khái niệm | Ví dụ | Câu hỏi cốt lõi |
|---|---|---|
| **Entity** | `Customer` có `id = 101` | Đây là **khách hàng nào**, và trạng thái của khách hàng thay đổi thế nào? |
| **Đối tượng giá trị** (*value object*) | `Address("12 Nguyễn Trãi", "Hà Nội", "100000")` | **Giá trị địa chỉ** là gì? |
| **DTO** (*Data Transfer Object*) | `CustomerSummaryDto(101, "An", "Hà Nội")` | Bên nhận **cần trao đổi những dữ liệu nào**? |
| **Bản ghi trong bảng** (*database row*) | Hàng `id=101` của bảng `customer` | Dữ liệu được **lưu dưới dạng cột và ràng buộc SQL** ra sao? |

Một mô hình trực quan:

```text
                  ỨNG DỤNG JAVA

     Customer (entity, id=101)
         |
         +-- name = "An"
         |
         +-- Address (value object)
               street, city, postalCode
         |
         +-- JPA quản lý trạng thái và ánh xạ
                   |
                   v
             CƠ SỞ DỮ LIỆU
             bảng customer
             +-----+------+----------------+--------+-------------+
             | id  | name | street         | city   | postal_code |
             +-----+------+----------------+--------+-------------+
             | 101 | An   | 12 Nguyễn Trãi | Hà Nội | 100000      |
             +-----+------+----------------+--------+-------------+

     API có thể đọc Customer và tạo:
     CustomerSummaryDto(101, "An", "Hà Nội")
```

Sơ đồ thể hiện một cách ánh xạ phổ biến; không có quy tắc buộc mọi entity phải tương ứng đúng một hàng, hay mọi đối tượng giá trị phải nằm trong cùng bảng với entity.

## 2. Entity: có danh tính và vòng đời

### 2.1. Danh tính quan trọng hơn bộ thuộc tính

**Entity** là đối tượng được nhận diện bằng **danh tính** (*identity*), thường tiếp tục tồn tại qua nhiều lần thay đổi thuộc tính.

Ví dụ, khách hàng `101` hôm nay tên `An`, ngày mai đổi thành `An Nguyễn`. Trạng thái đã đổi nhưng về mặt nghiệp vụ đó vẫn là một khách hàng. Ngược lại, hai khách hàng cùng tên, cùng địa chỉ vẫn là hai entity khác nhau nếu danh tính của họ khác nhau.

Trong JPA, lớp được ánh xạ như một entity thường có:

- `@Entity` để khai báo loại đối tượng có thể được persistence provider quản lý.
- `@Id` hoặc `@EmbeddedId` để mô tả **khóa định danh trong ánh xạ JPA**.
- `@Table`, `@Column`, `@ManyToOne`, `@OneToMany` và các annotation khác khi cần cấu hình ánh xạ sang mô hình quan hệ.
- Constructor không tham số có mức truy cập `public` hoặc `protected` theo yêu cầu phổ biến của JPA; lớp entity chuẩn cũng không được khai báo `final`.

Ví dụ rút gọn:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    protected Customer() { } // Cho JPA

    public Customer(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public void rename(String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException("Tên không được để trống");
        }
        this.name = newName;
    }
}
```

Ở đây, `id` dùng để định danh một bản thể `Customer` đã được lưu. Phương thức `rename` mô tả thay đổi trạng thái theo ngữ nghĩa nghiệp vụ; không nhất thiết phải cung cấp setter tùy ý cho mọi thuộc tính.

**Phân biệt ba dạng danh tính dễ bị nhầm lẫn:**

1. **Danh tính nghiệp vụ:** quy tắc xác định một thực thể ngoài đời, như mã khách hàng do hệ thống cấp. Nó có thể trùng hoặc không trùng với khóa lưu trữ.
2. **Định danh JPA:** thuộc tính được đánh dấu `@Id`/`@EmbeddedId`, dùng để nhận diện entity trong mô hình persistence.
3. **Danh tính đối tượng Java:** so sánh tham chiếu bằng `==`, chỉ trả lời hai biến có trỏ đến cùng một instance trong bộ nhớ hay không.

Trong một **persistence context**, JPA duy trì một instance được quản lý cho mỗi cặp loại entity và khóa định danh. Nhưng sau khi tách entity khỏi context, ở transaction khác hoặc sau khi tải lại, có thể có nhiều instance Java biểu diễn cùng một hàng dữ liệu. Vì vậy, `==` không phải phép kiểm tra chung để xác định hai entity có cùng định danh nghiệp vụ.

### 2.2. Entity có trạng thái quản lý của JPA

Một entity có thể trải qua các trạng thái thông dụng:

| Trạng thái | Ý nghĩa | Hệ quả cần nhớ |
|---|---|---|
| **New / transient** | Đối tượng vừa được tạo bằng `new`, chưa được persistence context quản lý | Thay đổi của đối tượng chưa tự tạo lệnh SQL |
| **Managed / persistent** | Entity đang được một persistence context quản lý | JPA có thể phát hiện thay đổi và đồng bộ qua *dirty checking* |
| **Detached** | Entity từng được quản lý nhưng hiện không còn gắn với context đó | Sửa trực tiếp không tự động cập nhật cơ sở dữ liệu |
| **Removed** | Entity được đánh dấu xóa trong context | Lệnh xóa được đồng bộ theo quy tắc flush/transaction |

Ví dụ trong một transaction:

```java
Customer customer = entityManager.find(Customer.class, 101L);
customer.rename("An Nguyễn");

// customer đang managed: JPA có thể nhận biết name đã đổi.
entityManager.flush(); // Đồng bộ thay đổi xuống DB trong transaction.
```

Không nhất thiết phải gọi `UPDATE` bằng tay mỗi khi chỉnh một entity managed. Tuy nhiên, **`flush()` không đồng nghĩa `commit()`**: SQL có thể đã được gửi đi, nhưng việc xác nhận transaction và khả năng nhìn thấy từ transaction khác còn phụ thuộc commit và mức cô lập.

Sau `entityManager.clear()` hoặc khi persistence context kết thúc, đối tượng có thể trở thành *detached*. Việc sửa một instance detached không tự động được lưu; `merge` có thể sao chép trạng thái của detached entity sang một instance managed và trả về instance managed đó.

### 2.3. Entity có thể mang hành vi nghiệp vụ

Entity không bắt buộc chỉ là một túi dữ liệu. Với bài toán có quy tắc, các thao tác như `cancelOrder()`, `changeShippingAddress()` hoặc `increaseQuantity()` có thể được đóng gói trong entity để bảo vệ tính hợp lệ của trạng thái.

Trong thiết kế theo Domain-Driven Design (DDD), *domain entity* là khái niệm nghiệp vụ được nhận diện theo danh tính. **JPA entity** là khái niệm của công nghệ lưu trữ. Một lớp có thể đồng thời đảm nhiệm cả hai vai trò, nhưng chúng không luôn là một: hệ thống phức tạp có thể dùng mô hình domain riêng và entity riêng cho tầng persistence.

## 3. Đối tượng giá trị: định nghĩa bằng thuộc tính, không bằng danh tính

### 3.1. Hai địa chỉ giống nhau có thể là cùng một giá trị

**Value object** mô tả một khái niệm bằng **tập thuộc tính cấu thành giá trị**. Ví dụ:

```text
Address("12 Nguyễn Trãi", "Hà Nội", "100000")
Address("12 Nguyễn Trãi", "Hà Nội", "100000")
                        => cùng giá trị địa chỉ
```

Ta thường không quan tâm “địa chỉ instance A có phải chính địa chỉ instance B hay không”; điều cần biết là chúng có cùng đường, thành phố và mã bưu chính hay không.

Một value object tốt thường:

- Có **ngữ nghĩa nghiệp vụ rõ ràng**: `Money`, `Address`, `DateRange`, `EmailAddress`.
- So sánh bằng **giá trị các thành phần**, không dựa vào ID do cơ sở dữ liệu cấp.
- Được đối xử theo hướng **bất biến** (*immutable*): muốn đổi giá trị, tạo giá trị mới và thay thế giá trị cũ.
- Kiểm tra các bất biến phù hợp, chẳng hạn khoảng ngày phải có `start <= end`.
- Không có vòng đời độc lập chỉ vì nó là một phần của entity sở hữu.

Không phải mọi lớp có vài thuộc tính hay mọi lớp bất biến đều tự động là value object. Điều quyết định là **vai trò và ngữ nghĩa trong miền nghiệp vụ**.

### 3.2. Biểu diễn value object bằng `@Embeddable`

JPA cung cấp `@Embeddable` và `@Embedded` để ánh xạ một nhóm thuộc tính vào entity sở hữu. Ví dụ địa chỉ:

```java
package com.example.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import java.util.Objects;

@Embeddable
public class Address {
    @Column(name = "street", nullable = false)
    private String street;

    @Column(name = "city", nullable = false)
    private String city;

    @Column(name = "postal_code", nullable = false)
    private String postalCode;

    protected Address() { } // JPA cần khởi tạo đối tượng

    public Address(String street, String city, String postalCode) {
        this.street = requireText(street, "street");
        this.city = requireText(city, "city");
        this.postalCode = requireText(postalCode, "postalCode");
    }

    private static String requireText(String text, String field) {
        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException(field + " không được trống");
        }
        return text;
    }

    public String getStreet() { return street; }
    public String getCity() { return city; }
    public String getPostalCode() { return postalCode; }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof Address that)) return false;
        return Objects.equals(street, that.street)
            && Objects.equals(city, that.city)
            && Objects.equals(postalCode, that.postalCode);
    }

    @Override
    public int hashCode() {
        return Objects.hash(street, city, postalCode);
    }
}
```

Lớp trên **bất biến ở mức API nghiệp vụ**: không công khai setter, mọi giá trị cần thiết được cung cấp qua constructor. Tuy vậy, để hỗ trợ ánh xạ JPA theo cách phổ biến và dễ mang sang nhiều provider, các trường không khai báo `final`, có constructor không tham số và JPA có thể nạp giá trị qua cơ chế persistence. Nếu muốn sử dụng Java `record` hoặc lớp thực sự bất biến làm embeddable, phải kiểm tra phiên bản Jakarta Persistence và khả năng của provider cụ thể.

Một entity có thể chứa value object này:

```java
package com.example.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Embedded;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 150)
    private String name;

    @Embedded
    private Address address;

    protected Customer() { }

    public Customer(String name, Address address) {
        rename(name);
        moveTo(address);
    }

    public Long getId() { return id; }
    public String getName() { return name; }
    public Address getAddress() { return address; }

    public void rename(String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException("Tên không hợp lệ");
        }
        this.name = newName;
    }

    public void moveTo(Address newAddress) {
        if (newAddress == null) {
            throw new IllegalArgumentException("Phải có địa chỉ");
        }
        this.address = newAddress; // Thay thế bằng giá trị mới
    }
}
```

Ví dụ:

```java
Customer customer = entityManager.find(Customer.class, 101L);
Address newAddress = new Address("5 Lê Lợi", "Đà Nẵng", "550000");
customer.moveTo(newAddress);

// JPA ghi nhận thay đổi trên entity Customer đang managed.
// Address không phải một entity được persist độc lập trong ví dụ này.
```

Ở cách ánh xạ mặc định vừa nêu, các trường của `Address` thường trở thành các cột `street`, `city`, `postal_code` trong bảng `customer`. Không có bảng `address` riêng chỉ vì ta đã tạo lớp `Address`.

### 3.3. Value object khác entity ở đâu?

Xem hai trường hợp:

- **Địa chỉ giao hàng** của một đơn hàng: giá trị có thể được chụp lại tại thời điểm đặt hàng và thay thế nếu người dùng đổi địa chỉ. Cách thiết kế value object thường phù hợp.
- **Kho hàng** có mã kho, nhân viên, tồn kho và vòng đời riêng: ngay cả khi hai kho cùng nằm trên một địa chỉ, chúng vẫn là hai đối tượng khác nhau. Kho hàng nên là entity.

Cùng một dữ liệu “tên đường, thành phố” có thể thuộc value object hoặc entity tùy yêu cầu. **Có bảng riêng không đủ để kết luận đó là entity nghiệp vụ**; ngược lại, có thể có entity ánh xạ qua nhiều bảng.

Ngoài `@Embeddable`, giá trị đơn giản có thể được ánh xạ qua `@Convert`/`AttributeConverter` (ví dụ `EmailAddress` ↔ một cột chuỗi). Một tập hợp value object có thể được ánh xạ qua `@ElementCollection`, khi đó JPA thường dùng bảng collection riêng. Cách lưu khác nhau không làm mất ý nghĩa “được nhận diện bằng giá trị”.

## 4. DTO: dữ liệu được thiết kế cho một ranh giới giao tiếp

### 4.1. DTO nhằm chuyển dữ liệu

**DTO (Data Transfer Object)** là kiểu dữ liệu dùng để chuyển thông tin giữa các tầng, tiến trình hoặc hệ thống, ví dụ:

- Controller trả dữ liệu JSON cho trình duyệt.
- Service nhận dữ liệu đã được phân tích từ request.
- Hai dịch vụ trao đổi message.
- Tầng truy vấn trả một phép chiếu (*projection*) chỉ gồm các trường cần hiển thị.

DTO không nhất thiết phản ánh toàn bộ cấu trúc entity hay cấu trúc bảng. Nó được quyết định bởi **hợp đồng giao tiếp** (*contract*) của nơi gửi và nơi nhận.

Ví dụ, trang danh sách khách hàng chỉ cần mã, tên và thành phố:

```java
package com.example.api;

public record CustomerSummaryDto(
    Long id,
    String name,
    String city
) { }
```

`CustomerSummaryDto` ở đây là một Java `record`, nhưng **Java record không phải là “bản ghi SQL”**. Đây là cú pháp Java tạo một kiểu mang dữ liệu, có constructor, accessor, `equals`, `hashCode` và `toString` theo các thành phần khai báo. Tên `record` trong Java và “row/record” trong quan hệ SQL chỉ trùng từ vựng; chúng là hai khái niệm khác nhau.

DTO có thể dùng `record`, lớp thường, hoặc kiểu khác phù hợp thư viện truyền dữ liệu. **DTO là một vai trò kiến trúc, không phải annotation JPA.**

### 4.2. Lấy DTO từ entity hoặc truy vấn trực tiếp

Có hai cách phổ biến để xây `CustomerSummaryDto`.

**Cách 1: ánh xạ từ entity đã tải.**

```java
Customer customer = entityManager.find(Customer.class, 101L);

CustomerSummaryDto dto = new CustomerSummaryDto(
    customer.getId(),
    customer.getName(),
    customer.getAddress().getCity()
);
```

Ưu điểm là dễ hiểu, có thể dùng logic của entity. Nhược điểm là nếu màn hình chỉ cần ba trường mà tải cả graph lớn, việc lấy entity có thể tốn truy vấn hoặc bộ nhớ không cần thiết.

**Cách 2: JPQL constructor projection, tạo DTO trực tiếp từ kết quả truy vấn.**

```java
var result = entityManager.createQuery(
    """
    select new com.example.api.CustomerSummaryDto(
        c.id, c.name, c.address.city
    )
    from Customer c
    where c.address.city = :city
    """,
    CustomerSummaryDto.class
)
.setParameter("city", "Hà Nội")
.getResultList();
```

Trong truy vấn này, JPA tạo `CustomerSummaryDto` theo constructor khớp tham số. Danh sách trả về **không gồm các entity `Customer` managed** chỉ vì nguồn dữ liệu đến từ bảng của entity.

Lưu ý: `CustomerSummaryDto` cần tên lớp đầy đủ trong JPQL constructor expression và constructor phù hợp với kiểu dữ liệu được chọn. Khi dùng truy vấn native SQL, cách ánh xạ sang DTO phụ thuộc API hoặc cấu hình mapping khác; không tự động giống JPQL constructor projection.

### 4.3. DTO đầu vào và DTO đầu ra có thể khác nhau

Ví dụ:

```java
public record CreateCustomerRequest(
    String name,
    String street,
    String city,
    String postalCode
) { }

public record CustomerDetailResponse(
    Long id,
    String name,
    String street,
    String city,
    String postalCode
) { }
```

Request tạo mới không chứa ID do máy chủ tự cấp; response chứa ID được công bố cho client. Một endpoint quản trị có thể trả thêm dữ liệu mà endpoint công khai không trả. Việc có các DTO phù hợp từng use case giúp kiểm soát dữ liệu được tiếp nhận/công bố và tránh buộc client phụ thuộc chặt vào cấu trúc persistence.

Khi tạo mới, service chuyển DTO sang entity và value object:

```java
public CustomerDetailResponse create(
    CreateCustomerRequest request,
    EntityManager entityManager
) {
    Address address = new Address(
        request.street(), request.city(), request.postalCode()
    );
    Customer customer = new Customer(request.name(), address);
    entityManager.persist(customer);

    // Giả định phương thức chạy trong transaction thích hợp;
    // thời điểm có ID phụ thuộc chiến lược sinh khóa/provider.
    return new CustomerDetailResponse(
        customer.getId(),
        customer.getName(),
        customer.getAddress().getStreet(),
        customer.getAddress().getCity(),
        customer.getAddress().getPostalCode()
    );
}
```

Đây là minh họa cách chuyển đổi; trong ứng dụng thực tế thường đặt logic transaction ở service và kiểm tra dữ liệu đầu vào tại ranh giới API. Với chiến lược sinh khóa hoặc provider khác, có thể cần flush trước khi chắc chắn ID đã sẵn sàng.

### 4.4. Vì sao không trả thẳng JPA entity qua API?

Việc trả entity trực tiếp đôi khi vẫn chạy được trong ví dụ nhỏ, nhưng có những rủi ro thiết kế cụ thể:

- **Lộ dữ liệu ngoài hợp đồng:** entity có thể chứa các trường nội bộ mà client không được phép xem.
- **Quan hệ hai chiều và vòng lặp serialization:** `Customer -> orders -> customer` có thể tạo vòng tham chiếu.
- **Lazy loading:** serializer đụng vào quan hệ chưa tải khi persistence context đã đóng có thể gây lỗi; nếu context còn mở lại có thể phát sinh các truy vấn ngoài dự tính.
- **Ràng buộc API vào persistence:** đổi tên cột ánh xạ, thay quan hệ hoặc tách entity có thể vô tình làm thay đổi JSON.
- **Nhận dữ liệu quá mức:** bind trực tiếp request vào entity có thể khiến các thuộc tính nội bộ bị thay đổi nếu không kiểm soát.

DTO tạo ra một ranh giới rõ ràng. Dù DTO có `id`, nó **không trở thành entity**: JPA không dirty-check đối tượng DTO và không tự lưu thay đổi của DTO vào bảng.

## 5. Bản ghi trong bảng: biểu diễn quan hệ ở tầng lưu trữ

### 5.1. Row là một bộ giá trị cột

Trong cơ sở dữ liệu quan hệ, bảng gồm các cột và các hàng. Một **row** là một bộ giá trị tương ứng với lược đồ bảng; nó không có phương thức Java, constructor Java hay trạng thái `managed/detached` của JPA.

Với ánh xạ `Customer` + `Address` ở trên, một lược đồ minh họa có thể là:

```sql
CREATE TABLE customer (
    id          BIGINT PRIMARY KEY,
    name        VARCHAR(150) NOT NULL,
    street      VARCHAR(255) NOT NULL,
    city        VARCHAR(255) NOT NULL,
    postal_code VARCHAR(30) NOT NULL
);
```

Ví dụ dữ liệu:

| id | name | street | city | postal_code |
|---:|---|---|---|---|
| 101 | An | 12 Nguyễn Trãi | Hà Nội | 100000 |
| 102 | Bình | 8 Trần Phú | Huế | 530000 |

DDL được đơn giản hóa để làm rõ cấu trúc; cú pháp tạo ID tự động khác nhau giữa PostgreSQL, Oracle, MySQL và các hệ quản trị khác. Khi sử dụng `@GeneratedValue(strategy = IDENTITY)`, cần cấu hình cột sinh giá trị theo hệ quản trị/provider phù hợp.

Trong bảng này:

- Cột `id` là khóa chính (*primary key*) của bảng `customer`.
- Bộ ba cột `street`, `city`, `postal_code` diễn tả value object `Address` được nhúng trong `Customer`.
- JPA đọc giá trị các cột để dựng lại entity và embedded object.
- Truy vấn SQL có thể chỉ chọn một số cột, ghép nhiều bảng hoặc tính toán trường phát sinh; kết quả truy vấn không bắt buộc tương ứng với nguyên một entity.

### 5.2. Một entity không luôn bằng một hàng

Ví dụ một entity `Order` có nhiều `OrderLine`:

```text
Java:
Order(id=500)
    -> OrderLine(id=1, product="Sách", quantity=2)
    -> OrderLine(id=2, product="Bút",  quantity=3)

SQL:
orders
  id=500
order_line
  id=1, order_id=500, product="Sách", quantity=2
  id=2, order_id=500, product="Bút",  quantity=3
```

`Order` được thể hiện bởi một hàng ở bảng `orders`, còn collection của nó được liên kết tới nhiều hàng `order_line`. Với `@SecondaryTable`, một entity có thể lấy thuộc tính từ nhiều bảng. Với `@ElementCollection`, một tập value object có thể có bảng riêng. Với chiến lược kế thừa entity, dữ liệu cũng có thể phân bố ở một hoặc nhiều bảng tùy mapping.

**Không nên suy luận “mỗi object Java tương ứng một row SQL”**. ORM làm nhiệm vụ ánh xạ giữa hai mô hình có quy tắc khác nhau, trong đó quan hệ đối tượng, collection, kế thừa và identity phải được diễn giải thành cột, khóa và quan hệ giữa bảng.

### 5.3. Row thay đổi khi nào?

Giả sử có entity managed:

```java
Customer customer = entityManager.find(Customer.class, 101L);
customer.rename("An Nguyễn");
```

Trong bộ nhớ, thuộc tính `name` đã đổi. JPA thường phát hiện thay đổi ở giai đoạn *flush* và phát SQL tương đương:

```sql
UPDATE customer
SET name = 'An Nguyễn'
WHERE id = 101;
```

SQL ở đây chỉ là diễn giải ý nghĩa; provider có thể cập nhật nhiều cột, batch lệnh hoặc dùng câu SQL khác tùy cấu hình. Nếu transaction rollback, việc đồng bộ đó không trở thành thay đổi đã commit. Ngược lại, một câu SQL thực thi ngoài persistence context có thể sửa row mà các entity đã được tải trong context **chưa tự biết**; khi đó cần quan tâm đến làm mới trạng thái, cache và tính nhất quán.

### 5.4. Row không mang toàn bộ ý nghĩa của entity

Database bảo vệ dữ liệu bằng primary key, foreign key, unique constraint, `NOT NULL`, check constraint và transaction. Entity có thể thêm các hành vi nghiệp vụ và bất biến mà một row riêng lẻ không biểu đạt hết.

Ví dụ, điều kiện “đơn hàng đã giao thì không được hủy” có thể là một phương thức `cancel()` trong mô hình domain, đồng thời cần chiến lược transaction và ràng buộc lưu trữ phù hợp để tránh vi phạm khi nhiều thao tác đồng thời. Chỉ nhìn vào một hàng `orders` không thể suy ra mọi quy tắc vận hành của ứng dụng.

## 6. So sánh theo những tiêu chí quyết định

| Tiêu chí | Entity | Value object | DTO | Row trong bảng |
|---|---|---|---|---|
| **Mục đích** | Mô hình hóa đối tượng có danh tính và trạng thái | Mô hình hóa một giá trị có ý nghĩa | Chuyển dữ liệu qua ranh giới | Lưu một bộ giá trị theo lược đồ quan hệ |
| **Danh tính** | Có danh tính ổn định theo miền nghiệp vụ/ánh xạ | Không cần danh tính riêng; nhận diện qua giá trị | Không có danh tính JPA, dù có trường `id` | Xác định bằng khóa/thuộc tính trong mô hình quan hệ |
| **So sánh** | Theo chính sách identity thích hợp | Thường theo các thành phần giá trị | Theo nhu cầu contract; Java `record` so sánh thành phần | So sánh giá trị cột theo SQL/quy tắc khóa |
| **Thay đổi** | Giữ identity, đổi trạng thái | Thường thay cả giá trị bằng instance mới | Tạo bản chuyển dữ liệu khác hoặc cập nhật dữ liệu DTO | `INSERT`, `UPDATE`, `DELETE` trong transaction |
| **JPA quản lý vòng đời** | Có: managed, detached, removed… | Là một phần mapping của chủ sở hữu khi nhúng | Không, nếu chỉ là DTO | Không; do DBMS quản lý |
| **Ánh xạ** | `@Entity`, `@Id`, quan hệ… | `@Embeddable`, `@Convert`, `@ElementCollection`… | Có thể ánh xạ thủ công hoặc projection | Lược đồ bảng, cột, khóa, constraint |
| **Ví dụ** | `Customer`, `Order` | `Address`, `Money` | `CustomerSummaryDto` | Một hàng trong `customer` |

Một câu hỏi thực dụng để lựa chọn:

> **Nếu mọi thuộc tính thay đổi, đối tượng có vẫn là “chính nó” không?** Nếu có, nhiều khả năng cần một entity. Nếu thay đổi thuộc tính nghĩa là có một giá trị khác, cân nhắc value object. Nếu chỉ cần mang dữ liệu đi qua ranh giới, dùng DTO. Nếu đang nói đến dữ liệu hiện diện ở các cột vật lý của database, đó là row.

Đây là tiêu chí tư duy, không phải thuật toán tự động: yêu cầu nghiệp vụ và chiến lược lưu trữ mới quyết định thiết kế cuối cùng.

## 7. Đi xuyên suốt một yêu cầu: từ request đến database rồi trở về DTO

Giả sử client gọi API tạo khách hàng. Luồng xử lý có thể là:

```text
HTTP POST /customers
{
  "name": "An",
  "street": "12 Nguyễn Trãi",
  "city": "Hà Nội",
  "postalCode": "100000"
}
        |
        v
CreateCustomerRequest        <-- DTO đầu vào
        |
        | kiểm tra dữ liệu, tạo giá trị nghiệp vụ
        v
Address                      <-- Value object
        |
        | new Customer(name, address)
        v
Customer                     <-- Entity chưa managed
        |
        | entityManager.persist(...) trong transaction
        v
Customer được quản lý        <-- Persistence context
        |
        | flush / SQL INSERT / commit
        v
row trong bảng customer      <-- Database
        |
        | truy vấn/ánh xạ kết quả
        v
CustomerDetailResponse       <-- DTO đầu ra
        |
        v
HTTP response JSON
```

Các điểm cần quan sát:

1. **Request DTO không được lưu nguyên xi:** service giải thích dữ liệu đầu vào theo quy tắc nghiệp vụ, tạo `Address` và `Customer`.
2. **Address không có ID riêng:** nó góp các giá trị vào trạng thái của khách hàng.
3. **Customer có ID và được JPA quản lý:** việc lưu liên quan đến persistence context và transaction.
4. **Row là kết quả lưu trữ:** database lưu những cột và ràng buộc mà mapping quy định.
5. **Response DTO là hợp đồng đầu ra:** có thể khác request DTO, entity và danh sách cột thực tế.

Khi khách hàng chuyển nhà, luồng có thể ngắn hơn:

```java
Customer customer = entityManager.find(Customer.class, 101L);
customer.moveTo(new Address("5 Lê Lợi", "Đà Nẵng", "550000"));
// Khi flush/commit phù hợp: các cột địa chỉ được đồng bộ.
```

Trong ví dụ này, khách hàng vẫn giữ `id = 101`; `Address` cũ bị thay bằng giá trị mới; row tương ứng được cập nhật theo transaction. Nếu trước đó một DTO đã được gửi tới client, **DTO cũ không tự cập nhật** khi entity hay row thay đổi: client cần dữ liệu mới theo giao thức ứng dụng.

## 8. Những nhầm lẫn thường gặp

### 8.1. “Có `id` thì chắc chắn là entity”

Không đúng. `CustomerSummaryDto` có `id` vì client cần biết khách hàng nào, nhưng nó không được JPA quản lý. Ngược lại, nhiều value object cũng có thể chứa chuỗi mã tham chiếu như `currencyCode` mà không có danh tính độc lập. Vai trò mới là điểm phân biệt.

### 8.2. “`@Embeddable` là entity con”

Không chính xác. Một đối tượng `@Embeddable` không tự có định danh JPA và vòng đời entity riêng. Nó đóng góp các thuộc tính vào chủ thể chứa nó. Nếu cần lưu độc lập, truy cập độc lập, phân quyền hoặc lịch sử riêng thì phải xem xét mô hình entity.

### 8.3. “Mỗi bảng ứng với một entity; mỗi dòng là một object”

Không bắt buộc. Một entity có thể trải trên nhiều bảng; collection có thể sinh nhiều row; bảng trung gian chỉ mô tả một quan hệ; native query có thể trả row không ánh xạ vào entity nào. Mối quan hệ giữa mô hình object và relational là **mapping**, không phải tương ứng một-một tuyệt đối.

### 8.4. “Sửa DTO là database tự cập nhật”

Không. DTO không tham gia *dirty checking*. Muốn đổi dữ liệu, service phải tìm hoặc tạo entity thích hợp, áp dụng thay đổi theo quy tắc nghiệp vụ và đồng bộ trong transaction.

```java
CustomerSummaryDto dto = new CustomerSummaryDto(101L, "Tên mới", "Huế");
// Chỉ tạo một đối tượng dữ liệu mới; không có lệnh UPDATE nào.
```

### 8.5. “Entity chỉ cần so sánh tất cả trường bằng `equals`”

Điều này dễ gây lỗi. Khác value object, entity có identity tồn tại qua thay đổi thuộc tính. Dùng toàn bộ trường mutable hoặc collection trong `equals`/`hashCode` có thể khiến kết quả đổi khi entity bị sửa, gây lỗi với `HashSet`/`HashMap`, chạm lazy loading hoặc đi vào vòng lặp quan hệ hai chiều.

Việc hiện thực equality cho entity cần xem xét ID sinh tự động (có thể `null` trước `persist`), khóa nghiệp vụ ổn định, proxy của Hibernate/JPA provider và thời điểm entity detached. Không sao chép máy móc cách `equals` của value object sang entity. Cũng cần thận trọng với annotation sinh tự động `equals`, `hashCode`, `toString` trên mọi trường của entity, ví dụ một số cách dùng Lombok `@Data`.

### 8.6. “Value object luôn không thể thay đổi về mặt kỹ thuật”

**Bất biến** là lựa chọn thiết kế thường được khuyến khích để tránh thay đổi khó kiểm soát, nhưng có những giới hạn ánh xạ trong JPA. Một `@Embeddable` có thể phải có constructor mặc định và trường không `final`; ORM có quyền gán trường khi hydrate dữ liệu. Vì vậy nên phân biệt **bất biến theo giao diện và hành vi nghiệp vụ** với bất biến tuyệt đối của ngôn ngữ Java.

Nếu value object được dùng làm khóa trong `HashMap` hoặc nằm trong `HashSet`, tránh thay đổi các thành phần được đưa vào `equals/hashCode`. Thực hành thay cả value object bằng đối tượng mới thường an toàn, rõ nghĩa hơn.

### 8.7. “Java `record` nghĩa là SQL row”

Không. Một Java `record` như `CustomerSummaryDto` là một kiểu dữ liệu của Java; SQL row là bộ dữ liệu trong bảng hay tập kết quả. Java record phù hợp với nhiều DTO bất biến, nhưng không tự động có annotation `@Entity`, transaction hay identity của JPA.

### 8.8. “`flush` nghĩa là dữ liệu đã lưu vĩnh viễn”

Không. `flush` đồng bộ thay đổi của persistence context thành thao tác với database trong transaction; **commit** mới xác nhận transaction. Rollback có thể hủy thao tác đã flush. Ngoài ra, trong nhiều cấu hình JPA có thể flush tự động trước truy vấn hoặc khi commit.

## 9. Chọn mô hình trong một số tình huống

| Bài toán | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Khách hàng đổi tên nhưng vẫn giữ lịch sử đơn hàng | `Customer` là entity | Cần danh tính ổn định và trạng thái thay đổi |
| Giá tiền gồm số lượng và đơn vị tiền tệ | `Money` là value object | Phép so sánh và phép toán dựa trên giá trị |
| Địa chỉ giao hàng được chụp lúc đặt hàng | `ShippingAddress` là value object của `Order` | Giá trị gắn với đơn hàng, có thể thay bằng bản khác |
| Địa điểm giao nhận dùng chung, có mã, lịch làm việc riêng | `PickupLocation` là entity | Có danh tính và vòng đời độc lập |
| Trả danh sách khách hàng chỉ gồm tên và thành phố | `CustomerListItemDto` | Contract tối giản cho giao diện |
| Gửi yêu cầu thay đổi địa chỉ từ client | `ChangeAddressRequest` DTO | Biểu diễn dữ liệu đầu vào; service phải xác thực và áp dụng |
| Lưu khóa ngoại `customer_id` trong `orders` | Cột SQL, quan hệ giữa bảng | Cấu trúc lưu trữ và tính toàn vẹn tham chiếu |
| Đọc số đơn hàng theo mỗi khách hàng từ truy vấn `GROUP BY` | DTO/projection từ kết quả truy vấn | Đây là dữ liệu tổng hợp, không nhất thiết là entity |

Một số value object cần bảng riêng vì là collection; một số DTO có hàng chục trường vì hợp đồng xuất báo cáo. Do đó, quyết định **entity / value object / DTO** dựa trên vai trò của đối tượng, còn quyết định **bảng / cột / quan hệ** dựa trên mô hình lưu trữ và yêu cầu truy vấn.

## 10. Tự kiểm tra hiểu biết

**Tình huống 1.** Hai khách hàng cùng tên, cùng địa chỉ nhưng có mã khách hàng khác nhau. Chúng là một hay hai entity?

<details>
<summary>Gợi ý trả lời</summary>

Là **hai entity** nếu mã khách hàng là định danh được chọn. Trùng các thuộc tính hiển thị không làm hai entity có cùng identity.

</details>

**Tình huống 2.** Hai đối tượng `Address` được tạo riêng nhưng có cùng `street`, `city`, `postalCode`. Chúng có thể được coi là bằng nhau không?

<details>
<summary>Gợi ý trả lời</summary>

Có. Theo ngữ nghĩa value object, chúng có cùng giá trị; `equals/hashCode` nên dựa vào các thành phần giá trị tương ứng.

</details>

**Tình huống 3.** API trả `CustomerSummaryDto(101, "An", "Hà Nội")`. Sau đó bạn đổi `name` trong DTO. Database có tự cập nhật không?

<details>
<summary>Gợi ý trả lời</summary>

Không. DTO không managed bởi JPA. Service cần áp dụng thay đổi trên entity thích hợp trong transaction và để JPA đồng bộ.

</details>

**Tình huống 4.** `Customer` có `@Embedded Address`. Vậy bắt buộc phải có bảng `address`?

<details>
<summary>Gợi ý trả lời</summary>

Không. Mapping embedded thông thường trải thuộc tính của `Address` thành các cột của bảng entity chủ. `@ElementCollection` và các mapping khác có thể dùng thêm bảng.

</details>

**Tình huống 5.** Một entity `Order` có 15 dòng hàng. Trong cơ sở dữ liệu có nhất thiết chỉ một row chứa mọi dữ liệu của `Order`?

<details>
<summary>Gợi ý trả lời</summary>

Không. `Order` có thể được ánh xạ vào một bảng, còn các dòng hàng nằm ở bảng quan hệ liên kết, hoặc có chiến lược mapping khác.

</details>

**Tình huống 6.** Đã gọi `flush()` sau khi sửa entity. Người dùng khác có chắc chắn thấy dữ liệu mới chưa?

<details>
<summary>Gợi ý trả lời</summary>

Chưa chắc. Transaction có thể chưa commit; khả năng nhìn thấy còn phụ thuộc transaction isolation. Rollback sẽ hủy thay đổi.

</details>

## 11. Ghi nhớ khi thiết kế với JPA

- Dùng **entity** khi đối tượng cần danh tính và vòng đời riêng. Với JPA, quan sát cả ID, persistence context và transaction.
- Dùng **value object** khi ý nghĩa nằm ở các thành phần giá trị. Khuyến khích kiểm tra bất biến và thay thế giá trị khi sửa; `@Embeddable` là một cách ánh xạ thông dụng.
- Dùng **DTO** để định nghĩa dữ liệu trao đổi theo use case. DTO có thể là Java `record`, nhưng không vì thế mà thành entity hay SQL row.
- Hiểu **row** là biểu diễn của dữ liệu trong mô hình quan hệ. Database lưu cột, khóa, constraint và thực thi SQL; ORM chịu trách nhiệm chuyển đổi giữa hai mô hình.
- Không đồng nhất **object trong bộ nhớ**, **entity managed**, **dữ liệu gửi qua API** và **hàng đã commit**. Chúng có thể biểu diễn cùng thông tin ở các thời điểm khác nhau nhưng không có cùng hành vi.

Khi gặp một lớp Java mới trong dự án persistence, hãy hỏi lần lượt: **Nó có danh tính nghiệp vụ không? Nó biểu diễn một giá trị hay một đối tượng có vòng đời? Nó có mục đích truyền dữ liệu? Nó được JPA quản lý theo mapping nào? Những cột và bảng nào thực sự lưu thông tin đó?** Trả lời được các câu hỏi này sẽ tránh phần lớn nhầm lẫn giữa entity, value object, DTO và bản ghi trong bảng.
