# Ánh xạ tập đối tượng nhúng bằng `@CollectionTable` trong JPA

## 1. Vì sao cần ánh xạ một tập hợp các đối tượng giá trị?

Trong mô hình **Data Persistence / Relational Access / ORM / JPA**, không phải mọi đối tượng Java đều cần trở thành một entity có khóa chính riêng. Có những đối tượng chỉ có ý nghĩa như **giá trị thuộc về một entity khác**, chẳng hạn:

- Một khách hàng có nhiều địa chỉ giao hàng.
- Một sản phẩm có các khoảng kích thước hoặc thuộc tính kỹ thuật.
- Một hồ sơ có nhiều số điện thoại, mỗi số gồm mã vùng và số thuê bao.
- Một cấu hình có một `Map` gồm nhãn và thông tin cấu hình chi tiết.

Nếu chỉ có **một** địa chỉ, có thể nhúng đối tượng bằng `@Embedded` và lưu các trường của địa chỉ ngay trong bảng `customers`. Nhưng nếu một khách hàng có **nhiều địa chỉ**, một hàng của bảng `customers` không thể chứa số lượng cột cố định đủ cho mọi trường hợp.

Giải pháp chuẩn của Jakarta Persistence là:

- `@Embeddable`: mô tả **kiểu đối tượng giá trị nhúng**.
- `@ElementCollection`: khai báo một tập hợp các phần tử là kiểu cơ bản hoặc embeddable.
- `@CollectionTable`: mô tả **bảng phụ** lưu các phần tử đó và cột khóa ngoại liên kết tới entity sở hữu.

Ví dụ:

```text
           Entity Customer
           id = 42
           name = "Lan"
           shippingAddresses: Set<ShippingAddress>
                |
                | @ElementCollection
                v
     customer_shipping_addresses
     +-------------+-------------------+--------+-------------+
     | customer_id | street            | city   | postal_code |
     +-------------+-------------------+--------+-------------+
     | 42          | 12 Nguyễn Huệ     | HCM    | 700000      |
     | 42          | 80 Lê Lợi         | HCM    | 700000      |
     +-------------+-------------------+--------+-------------+
         |
         +-- customer_id là FK đến customers.id
             (không phải ID độc lập của ShippingAddress)
```

Trong Java, từng hàng của bảng phụ được biểu diễn bằng một `ShippingAddress`; trong JPA, **chủ sở hữu** của tập địa chỉ vẫn là `Customer`.

**Trọng tâm:** `@CollectionTable` không biến các phần tử thành entity riêng. Nó chỉ định vị trí lưu các **element** trong một collection thuộc entity.

## 2. Phân biệt entity, embeddable và element collection

Các khái niệm liên quan nhưng không thể thay thế tùy tiện:

| Thành phần | Vai trò | Có `@Id` riêng? | Có thể `em.persist(...)` trực tiếp? |
|---|---|---|---|
| `@Entity` | Đối tượng có định danh và vòng đời persistence riêng. | Có định danh hợp lệ. | Có. |
| `@Embeddable` | Kiểu giá trị được nhúng trong entity hoặc trong phần tử collection. | Không có `@Id` riêng như entity. | Không. |
| `@Embedded` | Nhúng **một** đối tượng giá trị vào entity. | Dùng định danh của entity sở hữu. | Không áp dụng cho đối tượng nhúng. |
| `@ElementCollection` | Ánh xạ **nhiều** giá trị cơ bản hoặc embeddable. | Phần tử không phải entity độc lập. | Không persist phần tử riêng lẻ. |
| `@CollectionTable` | Cấu hình bảng lưu element collection và FK đến owner. | Không định nghĩa khóa chính Java của một element. | Không phải đối tượng có thể persist. |
| `@OneToMany` | Quan hệ đến **nhiều entity** có identity riêng. | Mỗi entity đích có ID riêng. | Có thể persist entity đích, tùy cascade. |

Một địa chỉ thường là **value object**: hai địa chỉ có cùng thông tin có thể được xem là cùng một giá trị, không nhất thiết cần ID độc lập. Trong khi đó, một `Order` có mã, trạng thái, lịch sử và vòng đời riêng thường phải là **entity**, do đó quan hệ `Customer.orders` thích hợp với `@OneToMany` hơn `@ElementCollection`.

Với `@ElementCollection`, các phần tử **phụ thuộc vào entity sở hữu**. Chúng không có entity identity và không được JPA quản lý như một tập các entity độc lập. Sự thay đổi collection được phát hiện và đồng bộ qua owner đang `managed`.

## 3. Ba annotation phối hợp với nhau thế nào?

### 3.1. `@Embeddable`

Annotation này đặt trên class giá trị có nhiều thuộc tính mà JPA sẽ lưu:

```java
import jakarta.persistence.Embeddable;

@Embeddable
public class ShippingAddress {
    private String street;
    private String city;
    private String postalCode;

    protected ShippingAddress() {
        // JPA khởi tạo đối tượng khi đọc dữ liệu.
    }
}
```

`ShippingAddress` không cần `@Entity` và `@Id`. Các trường của nó được xem là thành phần giá trị thuộc về `Customer`; khi được dùng trong element collection, chúng thường trở thành **các cột ở collection table**.

### 3.2. `@ElementCollection`

Annotation này đặt trên thuộc tính collection của entity:

```java
@ElementCollection
private Set<ShippingAddress> shippingAddresses = new HashSet<>();
```

JPA biết rằng các phần tử không phải quan hệ entity; chúng được quản lý theo semantics của **element collection**.

`@ElementCollection` hỗ trợ các dạng collection như `Collection`, `List`, `Set` và `Map` theo các quy tắc kiểu khóa/giá trị tương ứng. Mặc định `fetch` của `@ElementCollection` là **`FetchType.LAZY`**, nhưng thực thi LAZY có thể phụ thuộc provider.

### 3.3. `@CollectionTable`

Annotation này xác định bảng và cột nối với owner:

```java
@ElementCollection(fetch = FetchType.LAZY)
@CollectionTable(
    name = "customer_shipping_addresses",
    joinColumns = @JoinColumn(name = "customer_id")
)
private Set<ShippingAddress> shippingAddresses = new HashSet<>();
```

Trong đó:

- `name`: tên bảng chứa phần tử.
- `joinColumns`: một hoặc nhiều cột **ở collection table** tham chiếu về owner.
- `@JoinColumn(name = "customer_id")`: tên cột FK nằm trong `customer_shipping_addresses`; nó trỏ về primary key của `Customer` theo mapping mặc định.
- `schema`, `catalog` và `foreignKey`: các tùy chọn bổ sung để chỉ rõ vị trí bảng và ràng buộc FK.
- `uniqueConstraints` và `indexes`: metadata dành cho schema generation khi cần.

`@CollectionTable` chỉ nói về **bảng và liên kết đến owner**. Tên cột của các trường `ShippingAddress` thường được quy định bằng `@Column` trong embeddable, hoặc được override khi dùng collection.

### 3.4. Sơ đồ từ annotation đến SQL

```text
Customer (@Entity)
  id: Long (@Id)
  name: String
  shippingAddresses: Set<ShippingAddress>
       |
       +-- @ElementCollection: các element là giá trị được lưu
       |
       +-- @CollectionTable(
       |       name="customer_shipping_addresses",
       |       joinColumns=@JoinColumn(name="customer_id"))
       |          |
       |          +-- bảng riêng
       |          +-- FK customer_id -> customers.id
       |
       +-- ShippingAddress (@Embeddable)
               street     -> cột street
               city       -> cột city
               postalCode -> cột postal_code
```

**Không phải thêm `@JoinTable` vào cùng thuộc tính.** `@JoinTable` thường dùng để ánh xạ quan hệ entity qua bảng liên kết, còn `@CollectionTable` được thiết kế cho collection các basic/embeddable value.

## 4. Ví dụ đầy đủ: khách hàng có nhiều địa chỉ giao hàng

Bài toán: một khách hàng có thể lưu nhiều địa chỉ, mỗi địa chỉ chứa đường phố, thành phố, mã bưu chính và mã quốc gia. Mỗi địa chỉ chỉ có ý nghĩa trong tập địa chỉ của khách hàng đó; không có một quy trình độc lập để sửa địa chỉ bằng ID riêng.

### 4.1. Tạo lớp giá trị `ShippingAddress`

```java
package com.example.customer;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import java.util.Objects;

@Embeddable
public class ShippingAddress {

    @Column(name = "street", nullable = false, length = 160)
    private String street;

    @Column(name = "city", nullable = false, length = 100)
    private String city;

    @Column(name = "postal_code", nullable = false, length = 20)
    private String postalCode;

    @Column(name = "country_code", nullable = false, length = 2)
    private String countryCode;

    protected ShippingAddress() {
        // Constructor không tham số dành cho JPA.
    }

    public ShippingAddress(
            String street,
            String city,
            String postalCode,
            String countryCode
    ) {
        this.street = requireText(street, "street");
        this.city = requireText(city, "city");
        this.postalCode = requireText(postalCode, "postalCode");
        this.countryCode = requireText(countryCode, "countryCode");
    }

    private static String requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " không được trống");
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

    public String getCountryCode() {
        return countryCode;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof ShippingAddress that)) {
            return false;
        }
        return Objects.equals(street, that.street)
                && Objects.equals(city, that.city)
                && Objects.equals(postalCode, that.postalCode)
                && Objects.equals(countryCode, that.countryCode);
    }

    @Override
    public int hashCode() {
        return Objects.hash(street, city, postalCode, countryCode);
    }
}
```

Các điểm cần hiểu:

- `@Embeddable` đánh dấu lớp là giá trị nhúng, **không phải entity**.
- `@Column` đặt tên, độ dài và nullability cho từng thuộc tính; khi `ShippingAddress` được dùng trong collection, các cột này nằm trong **collection table**.
- Constructor `protected` không tham số giúp JPA provider khôi phục đối tượng.
- Không cung cấp setter công khai: code nghiệp vụ tạo đối tượng địa chỉ mới thay vì thay đổi lén từng trường. Đây là lựa chọn giúp dễ giữ giá trị ổn định trong `Set`.
- `equals/hashCode` dùng các trường biểu diễn giá trị; đặc biệt quan trọng với `Set<ShippingAddress>`.

Ví dụ kiểm tra `postalCode` chỉ yêu cầu chuỗi không trống; các quốc gia có quy tắc mã bưu chính khác nhau nên không nên coi một biểu thức chính quy đơn giản là chuẩn chung cho mọi trường hợp.

### 4.2. Tạo entity `Customer` sở hữu tập địa chỉ

```java
package com.example.customer;

import jakarta.persistence.CollectionTable;
import jakarta.persistence.Column;
import jakarta.persistence.ElementCollection;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.Table;

import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.Objects;
import java.util.Set;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "full_name", nullable = false, length = 120)
    private String fullName;

    @ElementCollection(fetch = FetchType.LAZY)
    @CollectionTable(
        name = "customer_shipping_addresses",
        joinColumns = @JoinColumn(
            name = "customer_id",
            referencedColumnName = "id",
            nullable = false
        )
    )
    private Set<ShippingAddress> shippingAddresses =
            new LinkedHashSet<>();

    protected Customer() {
        // JPA constructor.
    }

    public Customer(String fullName) {
        if (fullName == null || fullName.isBlank()) {
            throw new IllegalArgumentException("Tên khách hàng không hợp lệ");
        }
        this.fullName = fullName.trim();
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public Set<ShippingAddress> getShippingAddresses() {
        return Collections.unmodifiableSet(shippingAddresses);
    }

    public boolean addShippingAddress(ShippingAddress address) {
        return shippingAddresses.add(
                Objects.requireNonNull(address, "address")
        );
    }

    public boolean removeShippingAddress(ShippingAddress address) {
        return shippingAddresses.remove(address);
    }
}
```

Ý nghĩa của mapping:

1. `Customer.id` là **khóa chính** của bảng `customers`.
2. `shippingAddresses` là một **collection thuộc Customer**.
3. `@ElementCollection` chỉ rõ các phần tử `ShippingAddress` được lưu bằng value collection, không phải quan hệ tới entity riêng.
4. `@CollectionTable(name = "customer_shipping_addresses")` cho biết mỗi phần tử được lưu vào bảng `customer_shipping_addresses`.
5. `joinColumns = @JoinColumn(name = "customer_id")` tạo hoặc mô tả FK từ từng hàng địa chỉ về `Customer`.
6. Các `@Column` trong `ShippingAddress` xác định các cột thông tin của từng hàng trong bảng phụ.

Chọn `LinkedHashSet` giúp giữ thứ tự thêm **trong collection Java hiện tại**; điều này **không bảo đảm thứ tự lưu/đọc từ SQL** vì `Set` vốn không có thứ tự persistence mặc định. Nếu thứ tự hiển thị là yêu cầu nghiệp vụ, xem cách dùng `List` và `@OrderColumn` ở phần sau.

**Lưu ý về JPA-managed collection:** Provider có thể thay collection field bằng một đối tượng wrapper theo dõi thay đổi. Không nên dựa vào implementation luôn là `LinkedHashSet`. Method `getShippingAddresses()` trả view không sửa trực tiếp, và mã nghiệp vụ thay đổi thông qua `addShippingAddress`/`removeShippingAddress`.

### 4.3. Hình dạng bảng SQL

Một DDL minh họa phù hợp với ví dụ:

```sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL
);

CREATE TABLE customer_shipping_addresses (
    customer_id BIGINT NOT NULL,
    street VARCHAR(160) NOT NULL,
    city VARCHAR(100) NOT NULL,
    postal_code VARCHAR(20) NOT NULL,
    country_code VARCHAR(2) NOT NULL,

    CONSTRAINT fk_shipping_address_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(id)
);
```

DDL này cố tình **không thêm ID riêng cho từng địa chỉ**. Ở cấp JPA, phần tử có giá trị là tổ hợp các thuộc tính; ở cấp SQL, mỗi hàng là dữ liệu thuộc một customer. Provider có thể sinh thêm index hoặc constraint khác tùy cách cấu hình.

Ví dụ dữ liệu:

```text
customers
+----+----------------+
| id | full_name      |
+----+----------------+
| 42 | Nguyễn Lan     |
+----+----------------+

customer_shipping_addresses
+-------------+---------------------+----------+-------------+--------------+
| customer_id | street              | city     | postal_code | country_code |
+-------------+---------------------+----------+-------------+--------------+
| 42          | 12 Nguyễn Huệ       | TP.HCM   | 700000      | VN           |
| 42          | 80 Lê Lợi           | TP.HCM   | 700000      | VN           |
+-------------+---------------------+----------+-------------+--------------+
```

`customer_id` ở đây xác định **owner** chứ không phải một entity `ShippingAddress`. Không thể thực hiện `em.find(ShippingAddress.class, ...)` vì `ShippingAddress` không có entity identity.

### 4.4. Có cần khóa chính ở bảng collection không?

JPA element collection không yêu cầu một **`@Id` riêng cho từng phần tử**, nhưng database vẫn cần được thiết kế để giữ toàn vẹn dữ liệu. Tùy mục đích và dạng collection:

- Với `Set`, một constraint UNIQUE trên `(customer_id, street, city, postal_code, country_code)` có thể giúp ngăn hàng trùng nếu đó đúng là quy tắc nghiệp vụ.
- Với `List` có `@OrderColumn`, cặp `(customer_id, sort_index)` thường có thể dùng làm khóa/unique constraint trong schema.
- Với `Map`, cặp `(customer_id, map_key)` thường cần duy nhất để không có hai giá trị cho cùng key thuộc một owner.
- Có schema để database tạo bảng collection không có primary key tường minh; thiết kế này vẫn có thể hoạt động, nhưng việc định vị hàng khi update/delete và kiểm soát duplicate cần được đánh giá kỹ.

`@CollectionTable(uniqueConstraints = ...)` cho phép mô tả constraint để provider sinh DDL; nếu database production đã tồn tại, cần migration riêng để bảo đảm constraint thực sự hiện diện.

## 5. Lưu và đọc element collection

### 5.1. Persist owner cùng các embeddable elements

Giả sử `EntityManagerFactory emf` đã được khởi tạo cho persistence unit `RESOURCE_LOCAL` chứa `Customer`:

```java
EntityManager em = emf.createEntityManager();

try {
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        Customer customer = new Customer("Nguyễn Lan");

        customer.addShippingAddress(new ShippingAddress(
            "12 Nguyễn Huệ", "TP.HCM", "700000", "VN"
        ));
        customer.addShippingAddress(new ShippingAddress(
            "80 Lê Lợi", "TP.HCM", "700000", "VN"
        ));

        em.persist(customer);
        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw ex;
    }
} finally {
    em.close();
}
```

Điều quan trọng: mã **chỉ gọi `em.persist(customer)`**, không gọi `persist` cho từng địa chỉ. JPA theo dõi element collection của managed owner và ghi các hàng liên quan trong transaction.

`@ElementCollection` không cần `cascade = PERSIST` như quan hệ `@OneToMany` để lưu giá trị mới. Các phần tử không phải entity độc lập mà được lưu **như một phần trạng thái của owner**.

Provider có thể thực thi các lệnh như:

```sql
INSERT INTO customers (full_name) VALUES ('Nguyễn Lan');

-- Giả sử customer được cấp id = 42.
INSERT INTO customer_shipping_addresses
    (customer_id, street, city, postal_code, country_code)
VALUES (42, '12 Nguyễn Huệ', 'TP.HCM', '700000', 'VN');

INSERT INTO customer_shipping_addresses
    (customer_id, street, city, postal_code, country_code)
VALUES (42, '80 Lê Lợi', 'TP.HCM', '700000', 'VN');
```

SQL trên chỉ để hình dung kết quả. Khi thực thi thật, provider có thể thay đổi thứ tự cột, dùng bind parameters, batch INSERT hoặc trì hoãn câu lệnh đến thời điểm flush/commit.

### 5.2. Đọc entity và collection

```java
EntityManager em = emf.createEntityManager();

try {
    Customer customer = em.find(Customer.class, customerId);

    if (customer != null) {
        for (ShippingAddress address : customer.getShippingAddresses()) {
            System.out.println(
                address.getStreet() + ", " + address.getCity()
            );
        }
    }
} finally {
    em.close();
}
```

`Customer` có thể được load trước, còn bảng `customer_shipping_addresses` chỉ được truy vấn khi collection thực sự được truy cập nếu provider thực hiện LAZY. Bởi vậy ví dụ duyệt collection **trước khi đóng entity manager**.

Một lối viết dễ lỗi là:

```java
Customer customer = em.find(Customer.class, customerId);
em.close();

// Nếu collection chưa được tải, truy cập có thể lỗi
// khi không còn persistence context:
customer.getShippingAddresses().size();
```

Trong các provider như Hibernate, tình huống có thể dẫn tới lỗi lazy initialization. Không nên giải quyết bằng cách ép mọi collection thành EAGER; thay vào đó, dùng truy vấn fetch đúng nhu cầu hoặc chuyển dữ liệu thành DTO trong phạm vi persistence context.

### 5.3. Thêm hoặc xóa địa chỉ trên entity managed

```java
EntityManager em = emf.createEntityManager();

try {
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        Customer customer = em.find(Customer.class, customerId);

        customer.addShippingAddress(new ShippingAddress(
            "14 Hai Bà Trưng", "TP.HCM", "700000", "VN"
        ));

        customer.removeShippingAddress(new ShippingAddress(
            "80 Lê Lợi", "TP.HCM", "700000", "VN"
        ));

        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw ex;
    }
} finally {
    em.close();
}
```

Vì `Customer` đang managed, provider có thể phát hiện collection đã thay đổi và đồng bộ bằng `INSERT`/`DELETE` hoặc chiến lược SQL khác khi flush/commit. Mã không gọi `em.remove(address)`, vì `ShippingAddress` không phải entity.

**Không được suy luận provider luôn phát đúng một DELETE và một INSERT.** Với các dạng collection không có hàng định danh riêng, provider có thể xóa nhiều hàng rồi tạo lại để đồng bộ trạng thái. Số câu SQL phụ thuộc loại collection, mapping, database constraint và implementation.

## 6. Vì sao `Set` và `equals/hashCode` quan trọng?

### 6.1. `Set` thể hiện tính không trùng giá trị

Với:

```java
Set<ShippingAddress> shippingAddresses;
```

Java `Set` dùng quy tắc `equals()` và `hashCode()` để kiểm tra phần tử trùng. Nếu hai địa chỉ có cùng `street`, `city`, `postalCode`, `countryCode`, ví dụ `ShippingAddress` sẽ xem chúng là bằng nhau:

```java
ShippingAddress first = new ShippingAddress(
    "12 Nguyễn Huệ", "TP.HCM", "700000", "VN"
);

ShippingAddress sameValue = new ShippingAddress(
    "12 Nguyễn Huệ", "TP.HCM", "700000", "VN"
);

Set<ShippingAddress> addresses = new HashSet<>();

addresses.add(first);      // true
addresses.add(sameValue);  // false, đã có giá trị tương đương
```

Nếu `ShippingAddress` không hiện thực `equals/hashCode` theo giá trị, hai object khác instance có thể được Set xem là khác dù thông tin giống nhau.

### 6.2. Tránh sửa thuộc tính tham gia hash khi đang ở Set

Một nguy cơ lớn:

```java
Set<ShippingAddress> addresses = new HashSet<>();
ShippingAddress a = new ShippingAddress(...);
addresses.add(a);

// Nếu cho phép a.setCity(...) thay đổi thành phần hashCode,
// Set có thể không tìm lại hoặc xóa được a như mong đợi.
```

Vì thế, với embeddable dùng trong `Set`, cách thiết kế đơn giản là **không công khai setter**, và khi muốn sửa địa chỉ thì **xóa giá trị cũ, thêm giá trị mới**:

```java
customer.removeShippingAddress(oldAddress);
customer.addShippingAddress(revisedAddress);
```

JPA vẫn có thể khởi tạo và thiết lập field khi đọc từ database theo cơ chế truy cập field. Việc không có setter public chủ yếu bảo vệ API nghiệp vụ, không có nghĩa các field Java phải `final`.

### 6.3. `Set` không tự tạo UNIQUE constraint SQL

Ở tầng Java, `HashSet` không cho phần tử bằng nhau tồn tại hai lần. Nhưng database có thể bị ghi bằng SQL từ nguồn khác; nếu schema không có UNIQUE constraint, hai hàng dữ liệu trùng vẫn có thể xuất hiện.

Có thể khai báo constraint nếu đây là yêu cầu:

```java
@ElementCollection
@CollectionTable(
    name = "customer_shipping_addresses",
    joinColumns = @JoinColumn(name = "customer_id"),
    uniqueConstraints = @UniqueConstraint(
        name = "uk_customer_address",
        columnNames = {
            "customer_id",
            "street",
            "city",
            "postal_code",
            "country_code"
        }
    )
)
private Set<ShippingAddress> shippingAddresses = new HashSet<>();
```

Đây là quy tắc uniqueness **theo toàn bộ địa chỉ**. Nó có thể không phù hợp nếu nghiệp vụ cho phép cùng một địa chỉ xuất hiện nhiều lần với nhãn/mục đích khác nhau. Với constraint nhiều cột, cần cân nhắc kích thước index, cách so sánh chuỗi, collation và nullability của database.

## 7. Dùng `List<Embeddable>` khi thứ tự và phần tử trùng có ý nghĩa

Một `List` khác `Set` ở hai điểm chính:

- `List` có **thứ tự logic**.
- `List` có thể chứa **các giá trị trùng nhau**.

Giả sử khách hàng cần lưu danh sách địa chỉ theo mức ưu tiên. Ta muốn thứ tự này còn sau khi đóng/mở ứng dụng.

### 7.1. `@OrderColumn`: lưu vị trí của List

```java
@ElementCollection(fetch = FetchType.LAZY)
@CollectionTable(
    name = "customer_preferred_addresses",
    joinColumns = @JoinColumn(name = "customer_id")
)
@OrderColumn(name = "sort_index")
private List<ShippingAddress> preferredAddresses =
        new ArrayList<>();
```

Annotation `@OrderColumn` yêu cầu provider duy trì một cột vị trí cho các phần tử. Sơ đồ:

```text
customer_preferred_addresses
+-------------+------------+--------------------+----------+-------------+
| customer_id | sort_index | street             | city     | postal_code |
+-------------+------------+--------------------+----------+-------------+
| 42          | 0          | 12 Nguyễn Huệ      | TP.HCM   | 700000      |
| 42          | 1          | 80 Lê Lợi          | TP.HCM   | 700000      |
| 42          | 2          | 12 Nguyễn Huệ      | TP.HCM   | 700000      |
+-------------+------------+--------------------+----------+-------------+
```

Hai hàng có nội dung địa chỉ giống nhau vẫn có thể là **hai phần tử List riêng biệt** vì vị trí khác nhau.

`@OrderColumn` không có nghĩa entity `ShippingAddress` sở hữu trường `sortIndex`. Cột thứ tự là metadata do provider quản lý trong collection table; mã Java chỉ cần dùng `List`.

### 7.2. Thay đổi thứ tự có thể tạo nhiều UPDATE

Nếu dùng:

```java
Collections.swap(preferredAddresses, 0, 2);
```

provider phải bảo đảm `sort_index` phản ánh vị trí mới. Một thay đổi nhỏ ở đầu `List` có thể tác động nhiều hàng, tùy chiến lược SQL.

`@OrderColumn` thích hợp khi **thứ tự do người dùng/ứng dụng kiểm soát** cần được lưu. Nếu ứng dụng chỉ cần hiển thị theo giá trị một thuộc tính, dùng `@OrderBy` có thể phù hợp hơn.

### 7.3. `@OrderBy`: sắp xếp theo thuộc tính

Ví dụ:

```java
@ElementCollection
@CollectionTable(
    name = "customer_shipping_addresses",
    joinColumns = @JoinColumn(name = "customer_id")
)
@OrderBy("city ASC, street ASC")
private List<ShippingAddress> addressesByCity =
        new ArrayList<>();
```

`@OrderBy` yêu cầu sắp xếp khi lấy dữ liệu dựa trên thuộc tính được ánh xạ. Nó **không lưu vị trí do người dùng kéo-thả**. Hai địa chỉ có cùng city/street có thể cần thêm tiêu chí để thứ tự kết quả hoàn toàn xác định.

So sánh:

| Nhu cầu | Giải pháp |
|---|---|
| Không cần thứ tự, không muốn trùng giá trị | `Set<ShippingAddress>`, `equals/hashCode` theo giá trị. |
| Cần vị trí do người dùng lựa chọn và có thể đảo thứ tự | `List<ShippingAddress> + @OrderColumn`. |
| Chỉ cần kết quả luôn sắp xếp theo city/street | `@OrderBy` trên collection phù hợp. |
| Cần tra cứu theo nhãn duy nhất như `home`, `office` | `Map<String, ShippingAddress>` và `@MapKeyColumn`. |

Không nên mặc định một `List` không có `@OrderColumn`/`@OrderBy` sẽ khôi phục đúng thứ tự insert từ database. SQL không bảo đảm thứ tự hàng nếu không có tiêu chí ordering.

## 8. Ánh xạ `Map<String, Embeddable>` bằng `@CollectionTable`

Bởi chủ đề nằm trong chương **Tập hợp và Map**, cần hiểu rằng element collection có thể là một `Map`: mỗi owner giữ **nhiều giá trị embeddable, được tra theo một key cơ bản**.

Bài toán: một khách hàng có nhiều địa chỉ được gắn nhãn `"home"`, `"office"`, `"pickup"`.

### 8.1. Ánh xạ Map

```java
@Entity
@Table(name = "customer_profiles")
public class CustomerProfile {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ElementCollection(fetch = FetchType.LAZY)
    @CollectionTable(
        name = "customer_address_book",
        joinColumns = @JoinColumn(name = "customer_id")
    )
    @MapKeyColumn(name = "address_label", length = 30, nullable = false)
    private Map<String, ShippingAddress> addressBook =
            new LinkedHashMap<>();

    protected CustomerProfile() {}

    public void putAddress(String label, ShippingAddress address) {
        if (label == null || label.isBlank()) {
            throw new IllegalArgumentException("Nhãn địa chỉ không hợp lệ");
        }
        addressBook.put(label, Objects.requireNonNull(address));
    }

    public ShippingAddress getAddress(String label) {
        return addressBook.get(label);
    }
}
```

Các import cần thiết gồm `jakarta.persistence.*`, `java.util.LinkedHashMap`, `java.util.Map` và `java.util.Objects`.

Vai trò từng annotation:

- `@ElementCollection`: các **Map value** là kiểu `ShippingAddress`, không phải entity.
- `@CollectionTable`: bảng `customer_address_book` chứa các phần tử.
- `@MapKeyColumn(name = "address_label")`: một cột trong bảng giữ **Map key** kiểu `String`.
- Các field `ShippingAddress` được lưu ở những cột còn lại của bảng.

### 8.2. Cấu trúc SQL tương ứng

```sql
CREATE TABLE customer_address_book (
    customer_id BIGINT NOT NULL,
    address_label VARCHAR(30) NOT NULL,
    street VARCHAR(160) NOT NULL,
    city VARCHAR(100) NOT NULL,
    postal_code VARCHAR(20) NOT NULL,
    country_code VARCHAR(2) NOT NULL,

    CONSTRAINT pk_customer_address_book
        PRIMARY KEY (customer_id, address_label),

    CONSTRAINT fk_address_book_customer
        FOREIGN KEY (customer_id)
        REFERENCES customer_profiles(id)
);
```

Bảng này có thể chứa:

```text
+-------------+---------------+-------------------+--------+
| customer_id | address_label | street            | city   |
+-------------+---------------+-------------------+--------+
| 42          | home          | 12 Nguyễn Huệ     | TP.HCM |
| 42          | office        | 80 Lê Lợi         | TP.HCM |
+-------------+---------------+-------------------+--------+
```

Hai bản ghi của cùng owner không được có cùng `address_label` nếu đã có ràng buộc khóa chính hoặc UNIQUE trên `(customer_id, address_label)`. Mã `Map.put("home", newAddress)` thay thế giá trị của key `home` thay vì tạo hai mục cùng key.

`@MapKeyColumn` dùng cho key kiểu cơ bản như `String`. Với key phức tạp hoặc key lấy từ thuộc tính của entity, JPA có các quy tắc và annotation khác; không nên nhầm `@MapKeyColumn` với `@MapKey(name = "...")`.

### 8.3. Sự khác nhau giữa Map key và Map value

Một entry:

```java
addressBook.put(
    "home",
    new ShippingAddress(
        "12 Nguyễn Huệ",
        "TP.HCM",
        "700000",
        "VN"
    )
);
```

được phân tách thành:

```text
"home"                     -> @MapKeyColumn address_label
ShippingAddress.street     -> column street
ShippingAddress.city       -> column city
ShippingAddress.postalCode -> column postal_code
ShippingAddress.countryCode-> column country_code
CustomerProfile.id         -> join column customer_id
```

Map key và value có đời sống trong **cùng collection table**; không cần một entity trung gian chỉ vì muốn đặt nhãn cho địa chỉ, trừ khi từng entry thực sự có identity/vòng đời riêng.

## 9. Điều chỉnh tên cột với `@AttributeOverride`

Một lớp `@Embeddable` có thể được tái sử dụng ở nhiều nơi. Nhưng không phải mọi nơi đều muốn các cột có cùng tên.

Ví dụ cùng kiểu `ShippingAddress` được dùng:

- Trong bảng `customer_shipping_addresses`, muốn tên `postal_code`.
- Trong bảng `supplier_delivery_places`, schema legacy muốn tên `zip_code`.

Có thể tùy biến mapping cho collection cụ thể bằng `@AttributeOverride` hoặc `@AttributeOverrides` ở thuộc tính collection.

Một ví dụ ý tưởng:

```java
@ElementCollection
@CollectionTable(
    name = "supplier_delivery_places",
    joinColumns = @JoinColumn(name = "supplier_id")
)
@AttributeOverrides({
    @AttributeOverride(
        name = "street",
        column = @Column(name = "street_address", length = 160)
    ),
    @AttributeOverride(
        name = "postalCode",
        column = @Column(name = "zip_code", length = 20)
    )
})
private Set<ShippingAddress> deliveryPlaces = new HashSet<>();
```

Ở đây:

- `@CollectionTable` đặt tên bảng phụ và FK về owner.
- `@AttributeOverride` điều chỉnh cột của **thuộc tính nằm trong embeddable**, chứ không đổi FK tới owner.
- `name = "postalCode"` chỉ **tên thuộc tính Java** của `ShippingAddress`, không phải tên cột `postal_code`.
- Tùy trường hợp mapping lồng nhau hoặc Map, đường dẫn attribute cần được chỉ rõ theo quy tắc tên thuộc tính của đặc tả, bao gồm các tiền tố dành cho Map key/value khi áp dụng.

Khi ghi đè một `@Column`, cần khai báo lại các thông tin quan trọng mà schema yêu cầu (như `nullable`, `length`, `precision`), vì override mô tả một column mapping cho vị trí sử dụng đó.

Nếu chỉ cần cùng một bộ tên cột ở mọi nơi, đặt `@Column` trong `ShippingAddress` như ví dụ chính là đủ, không cần override.

### 9.1. Embeddable lồng nhau

Một kiểu giá trị có thể chứa một embeddable khác:

```java
@Embeddable
public class GeographicPoint {
    private BigDecimal latitude;
    private BigDecimal longitude;

    protected GeographicPoint() {}
}

@Embeddable
public class ShippingAddress {
    private String street;
    private String city;

    @Embedded
    private GeographicPoint point;

    protected ShippingAddress() {}
}
```

Các thuộc tính lồng nhau vẫn là **dữ liệu của collection element** và thông thường được trải ra thành cột trong cùng collection table. Khi cần đổi cột cho thuộc tính lồng nhau, đường dẫn attribute có thể dùng dạng `point.latitude` và `point.longitude` theo quy tắc mapping của JPA.

Với hai embedded objects có tên cột trùng nhau sau khi trải phẳng, cần dùng override hợp lệ để tránh collision. Đặt prefix cho từng cột từ đầu là một cách làm dễ vận hành.

## 10. `@CollectionTable` với khóa chính owner là khóa ghép

Một owner không phải lúc nào cũng chỉ có `Long id`. Giả sử `Warehouse` dùng khóa ghép:

```text
WarehouseId = (companyId, warehouseCode)
```

Collection table cần đủ các cột FK để tham chiếu **toàn bộ khóa của owner**.

```java
@ElementCollection
@CollectionTable(
    name = "warehouse_contact_points",
    joinColumns = {
        @JoinColumn(
            name = "owner_company_id",
            referencedColumnName = "company_id"
        ),
        @JoinColumn(
            name = "owner_warehouse_code",
            referencedColumnName = "warehouse_code"
        )
    }
)
private Set<ContactPoint> contactPoints = new HashSet<>();
```

DDL mang tính ý tưởng:

```sql
CREATE TABLE warehouse_contact_points (
    owner_company_id BIGINT NOT NULL,
    owner_warehouse_code VARCHAR(30) NOT NULL,
    contact_type VARCHAR(20) NOT NULL,
    contact_value VARCHAR(120) NOT NULL,

    FOREIGN KEY (owner_company_id, owner_warehouse_code)
        REFERENCES warehouses(company_id, warehouse_code)
);
```

Các điểm chính:

- `joinColumns` có **nhiều `@JoinColumn`** vì owner có khóa chính ghép.
- Mỗi `referencedColumnName` chỉ cột tương ứng ở bảng owner.
- Thứ tự và kiểu các cột FK cần khớp khóa được tham chiếu.
- `ContactPoint` vẫn chỉ là embeddable, dù bảng phụ dùng FK nhiều cột.

Không được lẫn `joinColumns` của `@CollectionTable` với `@JoinColumns` trên một quan hệ entity: ý nghĩa chung là mô tả FK nhưng metadata nằm ở loại mapping khác nhau.

## 11. Các lựa chọn fetch khi đọc nhiều customer

### 11.1. Mặc định LAZY

`@ElementCollection` mặc định là `FetchType.LAZY`. Ví dụ:

```java
@ElementCollection
@CollectionTable(
    name = "customer_shipping_addresses",
    joinColumns = @JoinColumn(name = "customer_id")
)
private Set<ShippingAddress> shippingAddresses = new HashSet<>();
```

Một truy vấn lấy danh sách customer:

```java
List<Customer> customers = em.createQuery(
    "SELECT c FROM Customer c", Customer.class
).getResultList();
```

có thể chưa tải tất cả hàng ở `customer_shipping_addresses`. Khi ứng dụng duyệt từng collection, provider có thể phát truy vấn phụ.

### 11.2. N+1 queries

```text
SELECT * FROM customers;                -- 1 query

SELECT * FROM customer_shipping_addresses
 WHERE customer_id = 1;                 -- query phụ

SELECT * FROM customer_shipping_addresses
 WHERE customer_id = 2;                 -- query phụ

SELECT * FROM customer_shipping_addresses
 WHERE customer_id = 3;                 -- query phụ
...
```

Nếu lấy N customers và mỗi lần duyệt collection tạo một truy vấn riêng, ứng dụng có thể gặp **N+1**. Cần đo hành vi provider và cân nhắc chiến lược truy vấn theo use case.

### 11.3. `JOIN FETCH` cho trường hợp cần collection

Khi service thực sự cần lấy địa chỉ cùng customer, có thể dùng JPQL:

```java
List<Customer> customers = em.createQuery(
    """
    SELECT DISTINCT c
    FROM Customer c
    LEFT JOIN FETCH c.shippingAddresses
    WHERE c.id IN :ids
    """,
    Customer.class
)
.setParameter("ids", customerIds)
.getResultList();
```

`LEFT JOIN FETCH` giữ cả customer không có địa chỉ. `DISTINCT` được dùng để thể hiện yêu cầu kết quả owner không lặp về mặt entity, vì phép join có thể tạo nhiều hàng SQL cho một customer; cơ chế khử trùng ở SQL/in-memory tùy provider và phiên bản.

**Không lạm dụng fetch join collection với phân trang** (`setFirstResult`, `setMaxResults`) vì join làm nhân số hàng, provider có thể cần xử lý phân trang trong bộ nhớ hoặc cảnh báo. Với trang danh sách lớn, một chiến lược thường dùng là:

1. Truy vấn trang ID customer trước.
2. Truy vấn các customer trong danh sách ID cùng collection cần thiết.
3. Chuyển kết quả thành DTO và giữ thứ tự hiển thị theo yêu cầu.

Có thể dùng entity graph, batch fetching hoặc subselect fetching tùy provider. Những lựa chọn này tối ưu cách **đọc**, không thay đổi bản chất element collection.

### 11.4. DTO và response API

Nếu API chỉ cần số lượng địa chỉ, không nhất thiết tải toàn bộ object graph:

```java
List<Object[]> counts = em.createQuery(
    """
    SELECT c.id, COUNT(a)
    FROM Customer c
    LEFT JOIN c.shippingAddresses a
    GROUP BY c.id
    """,
    Object[].class
).getResultList();
```

Dữ liệu trả về gồm ID của customer và số phần tử liên quan. Nếu cần kiểm tra một điều kiện cụ thể trong địa chỉ, có thể dùng phép join và đường dẫn thuộc tính embeddable trong JPQL.

## 12. Truy vấn vào thuộc tính của collection embeddable

### 12.1. Tìm customer theo thành phố trong địa chỉ

```java
List<Customer> customers = em.createQuery(
    """
    SELECT DISTINCT c
    FROM Customer c
    JOIN c.shippingAddresses a
    WHERE a.city = :city
    """,
    Customer.class
)
.setParameter("city", "TP.HCM")
.getResultList();
```

Trong JPQL:

- `c.shippingAddresses` là tên collection trong entity Java.
- `a.city` là thuộc tính của `ShippingAddress`.
- `customer_shipping_addresses` và `customer_id` là tên SQL, không được viết trực tiếp thay đường dẫn entity trong JPQL.

Đây là lợi ích của mapping element collection: dù phần tử không phải entity, ta vẫn có thể lọc theo **các thuộc tính basic của embeddable**.

### 12.2. Tìm customer có địa chỉ thuộc quốc gia nhất định

```java
List<Customer> customers = em.createQuery(
    """
    SELECT DISTINCT c
    FROM Customer c
    JOIN c.shippingAddresses a
    WHERE a.countryCode = :country
    """,
    Customer.class
)
.setParameter("country", "VN")
.getResultList();
```

Nếu một khách hàng có ba địa chỉ ở Việt Nam, join có thể sinh ba hàng kết quả SQL cho cùng customer. `DISTINCT` diễn đạt yêu cầu trả customer một lần.

### 12.3. `MEMBER OF` với value collection

Với embeddable value, có thể biểu diễn membership theo object giá trị:

```java
ShippingAddress address = new ShippingAddress(
    "12 Nguyễn Huệ", "TP.HCM", "700000", "VN"
);

List<Customer> customers = em.createQuery(
    """
    SELECT c FROM Customer c
    WHERE :address MEMBER OF c.shippingAddresses
    """,
    Customer.class
)
.setParameter("address", address)
.getResultList();
```

Với các embeddable gồm nhiều cột, khả năng biểu diễn so sánh toàn bộ giá trị trong query có thể phụ thuộc mức hỗ trợ của provider và database dialect. Khi cần tính di động cao, truy vấn theo **từng thuộc tính** bằng `JOIN ... WHERE a.street = ... AND a.city = ...` thường minh bạch hơn và dễ kiểm soát index.

### 12.4. Criteria API

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<Customer> query =
        cb.createQuery(Customer.class);

Root<Customer> customer = query.from(Customer.class);
SetJoin<Customer, ShippingAddress> address =
        customer.joinSet("shippingAddresses");

query.select(customer)
        .distinct(true)
        .where(cb.equal(address.get("city"), "TP.HCM"));

List<Customer> result = em.createQuery(query).getResultList();
```

Các import tương ứng nằm trong `jakarta.persistence.criteria`. Khi dùng typed static metamodel, có thể thay các chuỗi `"shippingAddresses"` và `"city"` bằng thuộc tính metamodel.

## 13. Vòng đời, xóa dữ liệu và transaction

### 13.1. Phần tử không có vòng đời entity riêng

Với `@OneToMany`, mỗi phần tử là entity có thể `persist`, `merge`, `remove` bằng API JPA theo identity của nó. Còn trong `@ElementCollection`:

```java
Customer customer = em.find(Customer.class, id);
customer.addShippingAddress(new ShippingAddress(...));
```

`ShippingAddress` là một **giá trị** trong state của `Customer`. Không có `EntityManager.remove(shippingAddress)` và không có entity ID của riêng nó.

Khi mã thay đổi collection của **managed Customer** trong transaction, JPA provider có trách nhiệm đồng bộ collection state. Khi `Customer` là detached, sửa collection không tự ghi vào database trừ khi entity được đưa trở lại phạm vi quản lý qua cơ chế phù hợp.

### 13.2. Xóa owner

Nếu `Customer` bị xóa trong transaction:

```java
Customer customer = em.find(Customer.class, customerId);

if (customer != null) {
    em.remove(customer);
}
```

Provider phải xử lý các hàng collection phụ thuộc owner để duy trì semantics của mapping, theo cách SQL và ràng buộc phù hợp. Trong ví dụ bảng phụ có FK đến customer, các hàng địa chỉ không còn parent và phải được xóa/giải quyết trong cùng đơn vị công việc.

Không cần `cascade = REMOVE` trên `@ElementCollection`; đây không phải quan hệ tới entity độc lập. Cách thực hiện có thể là DELETE từng phần tử, DELETE theo `customer_id` hoặc sử dụng cơ chế database tùy cấu hình.

### 13.3. Đổi owner cho một giá trị

Một `ShippingAddress` không có ID riêng để “chuyển quyền sở hữu” như một entity. Nếu địa chỉ của khách hàng A cũng cần dùng cho khách hàng B, có thể tạo một đối tượng giá trị tương đương và thêm vào collection của B:

```java
customerB.addShippingAddress(new ShippingAddress(
    source.getStreet(),
    source.getCity(),
    source.getPostalCode(),
    source.getCountryCode()
));
```

Không có khái niệm một hàng `ShippingAddress` độc lập được cả hai customer cùng tham chiếu theo foreign key. Nếu domain cần **một địa chỉ là entity được nhiều customer cùng tham chiếu**, mô hình phù hợp phải khác, ví dụ `@Entity Address` kết hợp các quan hệ entity.

### 13.4. Flush và rollback

Khi dùng transaction:

```text
tx.begin()
  |
  +-- customer.addShippingAddress(address)
  |
  +-- em.flush()  -> SQL có thể được gửi xuống database
  |
  +-- lỗi nghiệp vụ
  |
tx.rollback()
```

Dù `flush()` đã phát SQL, transaction vẫn có thể rollback; các hàng mới chưa commit không trở thành dữ liệu bền vững. Element collection tuân theo transaction của owner; không tự tạo transaction riêng cho từng phần tử.

Sau rollback, entity/object Java trong persistence context có thể không phản ánh đúng state database. Với application-managed entity manager, cách đơn giản là đóng entity manager của đơn vị công việc thất bại và dùng một entity manager mới khi xử lý lại.

## 14. `@ElementCollection` so với `@OneToMany`

Sự giống nhau về việc “có nhiều phần tử” dễ gây nhầm lẫn.

| Tiêu chí | `@ElementCollection` với `@Embeddable` | `@OneToMany` tới `@Entity` |
|---|---|---|
| Phần tử | Giá trị không có entity identity riêng. | Entity có định danh riêng. |
| Bảng lưu | `@CollectionTable`. | Bảng entity đích, có thể có FK hoặc join table theo mapping. |
| Khóa chính của phần tử | Không cần `@Id` trong embeddable. | Entity đích có `@Id`/`@EmbeddedId`. |
| Quản lý bằng `EntityManager` | Thao tác qua collection của owner. | Có thể persist/find/remove entity đích độc lập. |
| Vòng đời | Phụ thuộc owner, được đồng bộ như state của owner. | Tùy cascade/orphanRemoval và quy tắc nghiệp vụ. |
| Chia sẻ phần tử | Giá trị có thể giống nhau, nhưng không phải cùng một hàng entity được tham chiếu. | Một entity có thể tham gia các quan hệ theo cardinality/mapping hợp lệ. |
| Truy vấn | Join và lọc theo thuộc tính basic của embeddable; không query root như entity riêng. | Có thể query trực tiếp entity đích bằng JPQL. |
| Sửa một phần tử | Có thể phải thay giá trị hoặc update collection; SQL tùy provider. | Có entity identity nên cập nhật hàng đích thường được định vị theo PK. |
| Dùng khi | Địa chỉ, số điện thoại dạng value, các thông số gắn với owner. | Đơn hàng, dòng nghiệp vụ có identity độc lập, lịch sử, quyền truy cập riêng. |

### 14.1. Khi nào nên đổi embeddable thành entity?

Cân nhắc `@Entity` cho phần tử khi:

- Cần API như `GET /addresses/{addressId}` với định danh ổn định cho từng địa chỉ.
- Một địa chỉ được chia sẻ bởi nhiều khách hàng qua reference chung.
- Phần tử có trạng thái và lịch sử độc lập, ví dụ xác minh địa chỉ, duyệt, hết hạn.
- Nhiều bảng khác cần foreign key đến chính phần tử.
- Cần cập nhật từng row bằng ID độc lập để giảm chi phí thay đổi collection lớn.
- Collection value đã trở thành đối tượng nghiệp vụ quan trọng với vòng đời riêng.

Một kiểu giá trị có nhiều field **không tự bắt buộc** phải là entity. Câu hỏi quyết định là **nó có identity và vòng đời độc lập hay không?**

### 14.2. Trường hợp trung gian: association entity

Nếu mỗi khách hàng có nhiều địa chỉ và mỗi địa chỉ còn có thuộc tính quan hệ như `isDefault`, `verifiedAt`, `createdBy`, còn địa chỉ có thể dùng chung, một entity trung gian `CustomerAddress` có thể thích hợp hơn. Nó biểu diễn quan hệ có identity và metadata riêng, thay vì một `Set<ShippingAddress>` thuần giá trị.

Đừng lạm dụng `@ElementCollection` chỉ để giảm số class khi domain thực sự có thực thể độc lập.

## 15. Ràng buộc dữ liệu và validation

### 15.1. `@Column(nullable = false)` trên trường embeddable

Như trong `ShippingAddress`:

```java
@Column(name = "city", nullable = false, length = 100)
private String city;
```

Thuộc tính này mô tả ràng buộc ở tầng mapping/schema generation. Nếu database thật đã được tạo thủ công, cần bảo đảm DDL tương ứng có `NOT NULL` và độ dài phù hợp.

Tuy nhiên, `@Column` **không thay thế** kiểm tra mọi input. Constructor của `ShippingAddress` là nơi có thể kiểm tra quy tắc miền nghiệp vụ trước khi đưa giá trị vào collection.

### 15.2. Bean Validation với embeddable

Nếu project có Jakarta Bean Validation và integration phù hợp, có thể dùng:

```java
@Embeddable
public class ShippingAddress {

    @NotBlank
    @Size(max = 160)
    private String street;

    @NotBlank
    @Size(max = 100)
    private String city;

    @NotBlank
    @Size(max = 20)
    private String postalCode;

    protected ShippingAddress() {}
}
```

Các annotation `@NotBlank` và `@Size` thuộc `jakarta.validation.constraints`, không phải JPA. Để cascade validation vào element collection, có thể khai báo `@Valid` đúng theo vị trí mà Bean Validation hỗ trợ:

```java
@Valid
@ElementCollection
private Set<ShippingAddress> shippingAddresses = new HashSet<>();
```

Việc kiểm tra thực tế phụ thuộc Bean Validation provider, integration và thời điểm validate. Ràng buộc database vẫn cần thiết để bảo vệ dữ liệu ghi từ ngoài ứng dụng Java.

### 15.3. Null element và null field

Các tình huống khác nhau:

- `Customer.shippingAddresses == null`: thường không mong muốn; nên khởi tạo collection rỗng để code nghiệp vụ dễ dùng.
- Collection **rỗng**: customer không có địa chỉ, collection table không có hàng tương ứng.
- Một phần tử `ShippingAddress` là `null`: không nên dựa vào hành vi ánh xạ nhất quán cho phần tử null trong embeddable collection. Chủ động từ chối null qua method thêm phần tử.
- Một trường `ShippingAddress.city == null`: nếu cột có `NOT NULL`, database sẽ từ chối khi ghi; nên validate sớm ở domain.

Vì element collection ánh xạ qua nhiều cột, một hàng mà **tất cả** cột của embeddable là NULL có thể có semantics khác nhau tùy provider/mapping; nên tránh dữ liệu thiếu cấu trúc và mô hình hóa sự vắng mặt bằng collection rỗng khi đó là yêu cầu nghiệp vụ.

## 16. Thay đổi embeddable và hiệu quả SQL

Vì embeddable element không có khóa chính entity, việc update một phần tử có thể phức tạp hơn update entity thông thường.

### 16.1. Sửa trực tiếp object hay thay value?

Nếu embeddable có setter:

```java
ShippingAddress address = ...;
address.setCity("Hà Nội");
```

provider có thể nhận biết thay đổi của giá trị được quản lý, nhưng cách dirty checking và SQL cập nhật phần tử phụ thuộc implementation, đặc biệt với `Set` và `equals/hashCode`.

Nếu object này đang nằm trong `HashSet`, sửa field tham gia hash là **nguy hiểm**: container Java có thể không tìm đúng phần tử nữa.

Một cách dễ hiểu:

```java
customer.removeShippingAddress(oldAddress);
customer.addShippingAddress(new ShippingAddress(
    "12 Nguyễn Huệ", "Hà Nội", "100000", "VN"
));
```

Ở cấp value model, đây là **thay thế giá trị cũ bằng giá trị mới**, không phải thay ID của entity.

### 16.2. Vì sao provider có thể DELETE rồi INSERT?

Giả sử collection table có những hàng chỉ gồm `customer_id` và các cột giá trị, **không có một khóa hàng độc lập**. Để xác định chính xác hàng cần cập nhật, provider phải dựa vào owner và giá trị trước đó, hoặc xóa/tạo lại một phần collection.

Vì vậy, có provider chọn:

```sql
DELETE FROM customer_shipping_addresses
WHERE customer_id = ?;

INSERT INTO customer_shipping_addresses (...);
INSERT INTO customer_shipping_addresses (...);
```

cho một thay đổi có vẻ rất nhỏ ở Java. Ví dụ trên chỉ minh họa một chiến lược khả dĩ, không phải JPA bắt buộc luôn thực hiện như vậy. Với `List` có `@OrderColumn` hoặc `Map` có key rõ ràng, provider có thể xác định hàng và tối ưu khác.

Khi collection rất lớn hoặc thường xuyên sửa từng phần tử, cần cân nhắc liệu `@ElementCollection` còn là cấu trúc phù hợp hay nên chuyển sang entity có ID riêng.

### 16.3. Đừng thay hẳn collection tùy tiện

Một số provider bọc collection để theo dõi thay đổi. Thay field managed bằng một `HashSet` hoàn toàn mới có thể ảnh hưởng dirty checking, orphan handling hoặc tạo lượng SQL lớn.

Thường dễ kiểm soát hơn nếu dùng helper trên entity:

```java
public void replaceAllAddresses(Set<ShippingAddress> replacement) {
    Objects.requireNonNull(replacement);
    this.shippingAddresses.clear();
    replacement.forEach(this::addShippingAddress);
}
```

Đối với trường hợp cần thay toàn bộ dữ liệu, việc clear/add là có chủ đích. Nhưng nó cũng có thể khiến provider ghi nhiều SQL, nên không dùng như chiến lược cập nhật nhỏ lẻ nếu chỉ một phần tử thay đổi.

## 17. Cấu hình schema và ví dụ persistence unit

Một dự án Java SE dùng Hibernate/EclipseLink tương thích và H2 có thể đăng ký entity `Customer` trong `META-INF/persistence.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             version="3.1">
    <persistence-unit name="customersPU"
                      transaction-type="RESOURCE_LOCAL">
        <class>com.example.customer.Customer</class>

        <properties>
            <property name="jakarta.persistence.jdbc.driver"
                      value="org.h2.Driver"/>
            <property name="jakarta.persistence.jdbc.url"
                      value="jdbc:h2:mem:customers;DB_CLOSE_DELAY=-1"/>
            <property name="jakarta.persistence.jdbc.user" value="sa"/>
            <property name="jakarta.persistence.jdbc.password" value=""/>
            <property
                name="jakarta.persistence.schema-generation.database.action"
                value="drop-and-create"/>
        </properties>
    </persistence-unit>
</persistence>
```

`ShippingAddress` là một `@Embeddable` được dùng trong mapped element collection của `Customer`; provider cần biết metadata tương ứng khi xử lý entity. Tùy môi trường, các managed classes và embeddables có thể được phát hiện qua scanning hoặc được cấu hình tường minh. Nếu project dùng Spring Boot, phạm vi entity scanning và bootstrap thường được framework thiết lập, còn ý nghĩa của `@ElementCollection`/`@CollectionTable` vẫn giữ nguyên.

Để tạo factory trong Java SE:

```java
EntityManagerFactory emf =
        Persistence.createEntityManagerFactory("customersPU");

try {
    // Thao tác persist/find trong EntityManager.
} finally {
    emf.close();
}
```

Ví dụ `drop-and-create` chỉ dùng cho bài thực hành vì có thể **xóa dữ liệu hiện có**. Trong production, nên dùng schema migration có kiểm soát (Flyway, Liquibase hoặc script SQL) để tạo collection table, FK, UNIQUE/index và các cột đúng như mapping.

**Chú ý về tên bảng mặc định:** Nếu bỏ `@CollectionTable(name=...)`, JPA/provider có thể dùng quy tắc tên mặc định dựa trên entity và collection attribute. Với schema phải tương thích dài hạn, đặt tên tường minh giúp tránh phụ thuộc vào naming strategy, dialect và phiên bản provider.

## 18. Thiết kế schema cho dữ liệu lớn

### 18.1. Index theo owner

Đường truy vấn phổ biến nhất là lấy các địa chỉ của một customer:

```sql
SELECT street, city, postal_code, country_code
FROM customer_shipping_addresses
WHERE customer_id = ?;
```

Một index trên `customer_id` thường hữu ích:

```sql
CREATE INDEX ix_customer_addresses_customer
ON customer_shipping_addresses(customer_id);
```

Một số database tự có index cho unique/primary key composite bắt đầu bằng `customer_id`; cũng có hệ không tự tạo index chỉ vì foreign key tồn tại. Cần kiểm tra schema thực tế, không mặc nhiên thêm index trùng lặp.

### 18.2. Index cho truy vấn theo city

Nếu ứng dụng thường tìm customer có địa chỉ trong thành phố cụ thể:

```sql
SELECT DISTINCT c.id
FROM customers c
JOIN customer_shipping_addresses a
  ON a.customer_id = c.id
WHERE a.city = ?;
```

Có thể đánh giá index `(city, customer_id)` nếu workload và dữ liệu đủ lớn. Chọn index dựa trên plan truy vấn, phân bố giá trị, tần suất cập nhật và khả năng database; không phải cứ có field `city` thì luôn cần index.

### 18.3. Quy mô collection

Element collection phù hợp khi số phần tử mỗi owner không quá lớn và chủ yếu được đọc/ghi như **một phần aggregate**. Với hàng nghìn/hàng triệu phần tử có lifecycle riêng và thao tác cập nhật độc lập, việc giữ collection trong entity có thể gây:

- Chi phí tải nhiều hàng.
- Dirty checking và đồng bộ collection tốn kém.
- Nhiều DELETE/INSERT cho các thao tác nhỏ.
- Vấn đề lock/contention khi nhiều transaction cùng sửa collection của một owner.
- Khó phân trang từng phần tử trong API.

Khi đó cân nhắc entity độc lập và repository/query trực tiếp trên bảng phần tử.

## 19. Lỗi thường gặp khi ánh xạ `@CollectionTable`

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| Provider xem `ShippingAddress` là kiểu không ánh xạ được | Thiếu `@Embeddable` hoặc `@ElementCollection`. | Đặt đúng hai annotation theo vị trí class và collection field. |
| Provider cố tạo cột chứa cả `Set` trong bảng owner | Collection chưa được nhận diện là element collection. | Dùng `@ElementCollection` và `@CollectionTable` đúng cách. |
| Bảng phụ tham chiếu FK sai tên | Nhầm tên cột owner với tên cột ở collection table hoặc naming strategy khác. | Khai báo rõ `@JoinColumn(name=..., referencedColumnName=...)`. |
| Gặp lỗi `Not an entity` khi `em.persist(address)` | `ShippingAddress` là embeddable, không phải entity. | Chỉ persist `Customer`; thêm address vào collection. |
| Có bản ghi trùng dù field là `Set` | `equals/hashCode` không dựa trên giá trị hoặc DB thiếu UNIQUE khi có nguồn ghi khác. | Định nghĩa equality phù hợp và constraint DB nếu cần. |
| `HashSet.remove(oldAddress)` không hoạt động sau khi sửa address | Thay đổi field tham gia `hashCode` trong Set. | Tránh mutation; remove giá trị cũ rồi add giá trị mới. |
| Thứ tự List bị thay đổi sau reload | Không có `@OrderColumn` hoặc `@OrderBy`. | Chọn cách lưu/sắp xếp thứ tự rõ ràng. |
| `Map` ghi đè entry không mong muốn | Cùng key như `"home"` được dùng lại. | Làm rõ ngữ nghĩa key; đặt constraint `(owner_id,key)` khi phù hợp. |
| Collection LAZY gây exception sau khi đóng EntityManager | Chưa tải collection trước khi thoát persistence context. | Fetch đúng nhu cầu trong service, map sang DTO. |
| Đọc danh sách customer gây N+1 | Truy cập collection LAZY của từng owner. | Dùng fetch join có cân nhắc, batch fetching, entity graph hoặc query DTO. |
| Chỉ sửa một element nhưng thấy nhiều DELETE/INSERT | Provider thiếu row identity độc lập cho collection table. | Đánh giá cách update, collection type, schema hoặc chuyển sang entity. |
| Mất dữ liệu khi xóa Customer | Collection phụ thuộc owner nên các hàng collection cũng bị xóa. | Nếu phần tử phải tồn tại độc lập, dùng entity thay vì element collection. |
| Schema không có tên cột mong muốn | Bỏ `@Column` hoặc `@AttributeOverride`, provider dùng default. | Khai báo cột tường minh và dùng migration. |
| Chỉ thêm `@CollectionTable` nhưng không có bảng ở DB production | Schema không tự tạo/cập nhật khi deploy. | Tạo bảng/FK/index bằng migration đúng phiên bản. |
| Cột Map key thiếu hoặc không biết dùng annotation nào | Thiếu `@MapKeyColumn` cho basic map key. | Dùng `@MapKeyColumn`, kiểm tra key type và constraint. |
| Giá trị embeddable có field null vi phạm DDL | Cột `NOT NULL` nhưng object không được validate. | Kiểm tra tại constructor/method và dùng Bean Validation nếu cần. |
| Hai collection cùng default table gây tên trùng | Phụ thuộc naming strategy hoặc schema legacy. | Đặt `@CollectionTable(name=...)` riêng cho từng collection. |
| Dùng `@OneToMany` cho embeddable rồi báo lỗi mapping | `@OneToMany` đích cần entity; embeddable không phải entity. | Thay bằng `@ElementCollection` hoặc chuyển phần tử thành `@Entity`. |

## 20. Ba tình huống thực hành

### Tình huống A: Số điện thoại có mã vùng

Một `PhoneNumber` gồm `countryCallingCode` và `localNumber`, không có ID riêng. Mỗi nhân viên có nhiều số liên hệ:

```java
@Embeddable
public class PhoneNumber {
    @Column(name = "calling_code", length = 8, nullable = false)
    private String callingCode;

    @Column(name = "local_number", length = 30, nullable = false)
    private String localNumber;

    protected PhoneNumber() {}

    // Constructors, getters và equals/hashCode theo giá trị.
}
```

```java
@ElementCollection
@CollectionTable(
    name = "employee_phone_numbers",
    joinColumns = @JoinColumn(name = "employee_id")
)
private Set<PhoneNumber> phoneNumbers = new HashSet<>();
```

Schema:

```sql
employee_phone_numbers (
    employee_id,
    calling_code,
    local_number
)
```

Từng số điện thoại là **giá trị thuộc employee**. Nếu hệ thống cần quản lý tình trạng xác minh riêng cho từng số, lưu lịch sử đổi số hoặc tham chiếu đến một số bằng ID, hãy cân nhắc entity `EmployeePhone`.

### Tình huống B: Danh sách các mốc thời gian dạng value

Một chiến dịch có danh sách các giai đoạn, mỗi giai đoạn gồm tên và ngày dự kiến, và người dùng cần thay đổi thứ tự:

```java
@Embeddable
public class CampaignMilestone {
    private String title;
    private LocalDate plannedDate;

    protected CampaignMilestone() {}
}
```

```java
@ElementCollection
@CollectionTable(
    name = "campaign_milestones",
    joinColumns = @JoinColumn(name = "campaign_id")
)
@OrderColumn(name = "position")
private List<CampaignMilestone> milestones = new ArrayList<>();
```

Cột `position` lưu thứ tự do user chọn; đây là lý do dùng `List + @OrderColumn` thay vì `Set`. Nếu từng milestone có người phụ trách, trạng thái phê duyệt, comments và ID dùng trong API, có thể nó đã phù hợp hơn với entity.

### Tình huống C: Map cấu hình nhiều trường

Mỗi feature flag có các policy theo nhãn môi trường:

```java
@Embeddable
public class PolicyValue {
    private String rule;
    private Integer timeoutSeconds;

    protected PolicyValue() {}
}
```

```java
@ElementCollection
@CollectionTable(
    name = "feature_policies",
    joinColumns = @JoinColumn(name = "feature_id")
)
@MapKeyColumn(name = "environment_name")
private Map<String, PolicyValue> policies = new HashMap<>();
```

Dữ liệu một owner có thể gồm:

```text
environment_name = dev   -> (rule="allow", timeoutSeconds=10)
environment_name = prod  -> (rule="deny",  timeoutSeconds=30)
```

Trường `environment_name` là Map key trong collection table. `rule` và `timeoutSeconds` là các cột thuộc embeddable value. Nếu cần audit và version riêng cho mỗi policy, hãy cân nhắc entity độc lập.

## 21. Câu hỏi tự kiểm tra

**1. `@ElementCollection` khác `@OneToMany` quan trọng nhất ở đâu?**

`@ElementCollection` chứa basic/embeddable values **không có entity identity riêng**; `@OneToMany` chứa các entity có định danh và vòng đời của chúng.

**2. `@CollectionTable(joinColumns = @JoinColumn(name = "customer_id"))` tạo cột ở bảng nào?**

Cột `customer_id` nằm trong **collection table**, ví dụ `customer_shipping_addresses`, và tham chiếu tới khóa của entity `Customer`.

**3. Có cần đặt `@Id` trong `ShippingAddress` không?**

Không. `ShippingAddress` là embeddable, các hàng của element collection thuộc về `Customer`; phần tử không có entity ID riêng.

**4. Muốn lưu nhiều địa chỉ mà không cho trùng theo giá trị, chọn Set hay List?**

Thường chọn `Set<ShippingAddress>` và hiện thực `equals/hashCode` đúng ngữ nghĩa giá trị. Nếu cần chống trùng với dữ liệu ghi từ ngoài JPA, thêm UNIQUE constraint thích hợp ở database.

**5. `Set` có bảo đảm các địa chỉ được trả theo thứ tự thêm vào không?**

Không. Thứ tự collection Java có thể khác thứ tự SQL khi reload. Nếu thứ tự cần được lưu, cân nhắc `List + @OrderColumn`.

**6. `@OrderColumn` và `@OrderBy` khác nhau gì?**

`@OrderColumn` lưu **vị trí** do collection List quản lý; `@OrderBy` yêu cầu sắp xếp theo một hoặc nhiều **thuộc tính đã lưu** khi truy vấn.

**7. Muốn `Map<String, ShippingAddress>` có key là `"home"`, annotation nào ánh xạ key?**

`@MapKeyColumn(name = "address_label")` cho biết cột lưu Map key cơ bản ở collection table.

**8. Khi xóa một ShippingAddress khỏi customer, có cần `em.remove(address)`?**

Không. `ShippingAddress` không phải entity. Thay đổi collection của managed `Customer` trong transaction, provider đồng bộ các hàng liên quan.

**9. Vì sao update một phần tử có thể phát nhiều DELETE/INSERT?**

Các element không có identity riêng như entity; provider có thể cần đồng bộ cả phần collection, tùy kiểu collection, schema và thuật toán dirty checking.

**10. `@CollectionTable` có tự tạo bảng production sau khi thêm annotation không?**

Không có bảo đảm chung. Nó là metadata cho JPA/schema generation; với database đã tồn tại, cần kiểm soát migration và xác nhận bảng, FK, index, constraint thật.

**11. Vì sao `ShippingAddress` không nên có setter cho các field nằm trong `hashCode` nếu dùng `Set`?**

Vì đổi giá trị sau khi đưa object vào hash-based Set có thể khiến `remove`/`contains` hoạt động sai do hash thay đổi.

**12. Nếu địa chỉ cần được nhiều khách hàng cùng tham chiếu như cùng một đối tượng có ID, còn dùng `@ElementCollection` không?**

Không phù hợp. Khi có identity và tham chiếu chung, nên mô hình hóa `Address` là entity và dùng các quan hệ entity tương ứng.

## 22. Tổng kết

**`@CollectionTable` ánh xạ bảng phụ lưu một tập hợp các giá trị cơ bản hoặc đối tượng `@Embeddable` thuộc một entity.** Cơ chế hoàn chỉnh có ba tầng:

1. **Java domain:** `Customer` chứa `Set<ShippingAddress>`, `List<ShippingAddress>` hoặc `Map<String, ShippingAddress>`; `ShippingAddress` là kiểu giá trị không có ID riêng.
2. **JPA metadata:** `@ElementCollection` khai báo collection giá trị, `@CollectionTable` chọn bảng và FK đến owner, còn `@Column` / `@AttributeOverride` ánh xạ các trường của embeddable. Với List và Map, `@OrderColumn` hoặc `@MapKeyColumn` bổ sung metadata cần thiết.
3. **Database:** collection table có FK về owner, các cột biểu diễn giá trị phần tử, cùng constraint/index cần thiết để bảo vệ dữ liệu và tối ưu truy vấn.

Mẫu cấu hình dễ ghi nhớ:

```java
@ElementCollection(fetch = FetchType.LAZY)
@CollectionTable(
    name = "customer_shipping_addresses",
    joinColumns = @JoinColumn(name = "customer_id")
)
private Set<ShippingAddress> shippingAddresses =
        new HashSet<>();
```

Một value collection phù hợp khi phần tử **không có vòng đời hoặc định danh độc lập**, có thể được quản lý như một phần trạng thái của owner. Khi nhu cầu chuyển sang truy vấn/sửa/xóa phần tử theo ID riêng, chia sẻ giữa nhiều owner hoặc audit độc lập, nên cân nhắc chuyển sang entity và `@OneToMany`/quan hệ phù hợp.

### Tài liệu tham khảo

- [Jakarta Persistence — trang đặc tả chính thức](https://jakarta.ee/specifications/persistence/)
- [Jakarta Persistence API — `@ElementCollection`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/elementcollection)
- [Jakarta Persistence API — `@CollectionTable`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/collectiontable)
- [Jakarta Persistence API — `@Embeddable`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/embeddable)
