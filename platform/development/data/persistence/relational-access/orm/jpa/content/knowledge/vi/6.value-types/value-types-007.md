# Biểu diễn null trong cấu trúc có nhiều thuộc tính

Trong mô hình đối tượng Java, một **kiểu giá trị** (*value object*) thường gom nhiều thuộc tính có ý nghĩa chung. Ví dụ, địa chỉ giao hàng có `street` (đường), `city` (thành phố) và `postalCode` (mã bưu chính). Java cho phép tham chiếu đến cả đối tượng địa chỉ bằng `null`, đồng thời cũng cho phép một đối tượng địa chỉ tồn tại nhưng một hoặc nhiều trường bên trong có giá trị `null`.

Khi lưu kiểu giá trị đó bằng **JPA (Jakarta Persistence)**, sự khác biệt trở nên quan trọng: một đối tượng được khai báo `@Embeddable` thường được ánh xạ thành **nhiều cột trên cùng bảng của entity sở hữu**. Cơ sở dữ liệu quan hệ có `NULL` cho từng cột, nhưng không mặc nhiên có một cột riêng cho biết “đối tượng địa chỉ này có tồn tại hay không”.

Bài học này giải thích **cách biểu diễn `null` trong cấu trúc có nhiều thuộc tính**, đặc biệt đối với `@Embeddable` và `@Embedded`, khi nào có thể mất sự phân biệt giữa đối tượng `null` và đối tượng có mọi thuộc tính `null`, và cách thiết kế ánh xạ cùng ràng buộc để phản ánh đúng nghiệp vụ.

## 1. Phân biệt ba mức độ null

Trước tiên cần phân biệt ba câu hỏi độc lập:

1. **Tham chiếu đến cả value object có `null` không?** Ví dụ `order.getShippingAddress() == null`.
2. **Value object có tồn tại nhưng thuộc tính bên trong có `null` không?** Ví dụ `address != null` và `address.getCity() == null`.
3. **Cột trong cơ sở dữ liệu có chứa SQL `NULL` không?** Ví dụ `ship_city IS NULL`.

Ba câu hỏi tương ứng với những tầng khác nhau:

```text
Tầng Java
---------
shippingAddress = null
      hoặc
shippingAddress = Address(
    street = null,
    city = null,
    postalCode = null
)
      hoặc
shippingAddress = Address(
    street = "12 Nguyễn Trãi",
    city = "Hà Nội",
    postalCode = null
)

Tầng database (các cột của cùng một hàng)
------------------------------------------
ship_street       ship_city      ship_postal_code
NULL              NULL           NULL
"12 Nguyễn Trãi"  "Hà Nội"       NULL
```

Trong Java, hai biểu thức sau **không tương đương**:

```java
Address absent = null;
Address empty = new Address(null, null, null);

System.out.println(absent == null); // true
System.out.println(empty == null);  // false
```

Ở trường hợp thứ hai, một instance `Address` thực sự tồn tại. Các phương thức trên instance có thể được gọi, object có định danh tham chiếu riêng và domain code có thể phân biệt nó với `null`.

Tuy nhiên, nếu cả hai giá trị trên cùng được ánh xạ vào **ba cột** và không có cột đánh dấu sự tồn tại của cả cấu trúc, chúng có thể tạo ra **cùng một trạng thái dữ liệu quan hệ**: ba cột đều là SQL `NULL`.

Đây là nguyên nhân quan trọng nhất khiến việc biểu diễn `null` cho kiểu giá trị nhiều thuộc tính cần được thiết kế cẩn thận.

## 2. @Embeddable biểu diễn nhiều thuộc tính bằng nhiều cột như thế nào?

JPA hỗ trợ nhúng một kiểu giá trị vào entity bằng hai annotation:

- `@Embeddable`: khai báo lớp có thể được nhúng và có các thuộc tính được ánh xạ.
- `@Embedded`: khai báo thuộc tính bên trong entity sử dụng một kiểu nhúng.

Đối với cách ánh xạ thông thường, các trường của embedded object không tạo thành một bảng độc lập. Thay vào đó, **các cột tương ứng nằm trên bảng của entity sở hữu**.

### 2.1. Khai báo value object Address

```java
package com.example.domain;

import jakarta.persistence.Embeddable;

@Embeddable
public class Address {
    private String street;
    private String city;
    private String postalCode;

    protected Address() {
        // Constructor không tham số dành cho JPA.
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
```

`Address` là một **kiểu giá trị**, không có `@Entity` và `@Id` riêng. Các thuộc tính `street`, `city`, `postalCode` được ánh xạ như một phần trạng thái của entity chứa nó.

Ví dụ một đơn hàng có thể được giao tận nơi hoặc khách tự đến nhận. Đối với hình thức tự đến nhận, địa chỉ giao hàng có thể không tồn tại:

```java
package com.example.domain;

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
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "delivery_mode", nullable = false, length = 20)
    private String deliveryMode;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(
            name = "street",
            column = @Column(name = "ship_street", length = 200)
        ),
        @AttributeOverride(
            name = "city",
            column = @Column(name = "ship_city", length = 100)
        ),
        @AttributeOverride(
            name = "postalCode",
            column = @Column(name = "ship_postal_code", length = 20)
        )
    })
    private Address shippingAddress;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String deliveryMode, Address shippingAddress) {
        this.deliveryMode = deliveryMode;
        this.shippingAddress = shippingAddress;
    }

    public Long getId() {
        return id;
    }

    public String getDeliveryMode() {
        return deliveryMode;
    }

    public Address getShippingAddress() {
        return shippingAddress;
    }

    public void changeShippingAddress(Address shippingAddress) {
        this.shippingAddress = shippingAddress;
    }
}
```

`@AttributeOverrides` đổi tên các cột từ thuộc tính của `Address` sang `ship_street`, `ship_city` và `ship_postal_code`. Các `@Column` ở đây không khai báo `nullable = false`, vì ví dụ cho phép không có địa chỉ giao hàng. Điều này chỉ thiết lập một phần metadata mapping; schema database thực tế cần được quản lý đồng bộ bằng migration hoặc cơ chế tạo schema phù hợp.

Một schema PostgreSQL minh họa:

```sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    delivery_mode VARCHAR(20) NOT NULL,
    ship_street VARCHAR(200),
    ship_city VARCHAR(100),
    ship_postal_code VARCHAR(20)
);
```

Khi dùng mapping này, không có một cột tên `shipping_address` nhận toàn bộ object. Giá trị của object được **trải ra** thành ba cột.

### 2.2. Các trường hợp dữ liệu thực tế

| Giá trị Java | ship_street | ship_city | ship_postal_code | Ý nghĩa nghiệp vụ có thể có |
| --- | --- | --- | --- | --- |
| `shippingAddress = null` | `NULL` | `NULL` | `NULL` | Không có địa chỉ giao hàng, ví dụ nhận tại cửa hàng. |
| `new Address(null, null, null)` | `NULL` | `NULL` | `NULL` | Có object nhưng không có thông tin trong bất kỳ trường nào. |
| `new Address("12 Nguyễn Trãi", "Hà Nội", null)` | `"12 Nguyễn Trãi"` | `"Hà Nội"` | `NULL` | Địa chỉ có một thuộc tính chưa cung cấp. |
| `new Address("12 Nguyễn Trãi", "Hà Nội", "100000")` | `"12 Nguyễn Trãi"` | `"Hà Nội"` | `"100000"` | Địa chỉ có đủ ba thuộc tính của mô hình ví dụ. |

Hai hàng đầu **không phân biệt được chỉ bằng ba cột này**. Khi ứng dụng đọc lại dữ liệu, nó không có đủ thông tin trong các cột để biết trước đây object là `null` hay là một `Address` có toàn bộ trường `null`.

## 3. Null của cả embedded object và null của từng thành phần

Với một giá trị đa thuộc tính, cần xác định rõ ngữ nghĩa ở mức tổng thể.

### 3.1. Trường hợp toàn bộ object là null

```java
PurchaseOrder pickup = new PurchaseOrder("PICKUP", null);
```

Từ góc nhìn JPA, không có giá trị địa chỉ để lưu. Khi được ghi xuống database, các cột tương ứng với địa chỉ sẽ mang `NULL`, giả sử schema cho phép:

```sql
INSERT INTO purchase_orders (
    delivery_mode,
    ship_street,
    ship_city,
    ship_postal_code
) VALUES (
    'PICKUP',
    NULL,
    NULL,
    NULL
);
```

SQL này minh họa ý nghĩa lưu trữ, không phải lời bảo đảm provider sẽ phát đúng câu lệnh theo cú pháp hoặc thứ tự cột như trên. SQL thực tế thường dùng các tham số và có thể cần thao tác lấy khóa tự sinh.

### 3.2. Trường hợp object khác null nhưng tất cả thành phần đều null

```java
PurchaseOrder draft = new PurchaseOrder(
    "DELIVERY",
    new Address(null, null, null)
);
```

Nếu không có trường đánh dấu riêng, các cột địa chỉ vẫn có thể được lưu thành:

```text
ship_street = NULL
ship_city = NULL
ship_postal_code = NULL
```

Do đó, hai trạng thái Java khác nhau có thể **hội tụ về một trạng thái quan hệ**. Đây là vấn đề không thể giải quyết chỉ bằng việc đặt tên annotation khác nhau, vì thông tin về sự hiện diện của object không được mã hóa trong dữ liệu đã lưu.

### 3.3. Khi đọc lại: có nhận được null hay Address rỗng?

Cách provider JPA dựng lại embedded object từ một nhóm cột đều `NULL` có thể phụ thuộc vào nhà cung cấp ORM, phiên bản và cách ánh xạ. Một số provider, trong đó có những cấu hình Hibernate, xem một nhóm cột nhúng đều `NULL` là dấu hiệu cho giá trị nhúng `null`; các cơ chế hoặc cấu hình khác có thể khởi tạo object rỗng trong một số tình huống.

Vì vậy, **không nên viết nghiệp vụ bắt buộc phải giữ nguyên phân biệt** giữa:

```java
order.getShippingAddress() == null
```

và:

```java
order.getShippingAddress() != null
    && order.getShippingAddress().getStreet() == null
    && order.getShippingAddress().getCity() == null
    && order.getShippingAddress().getPostalCode() == null
```

sau một chu trình lưu rồi tải, khi schema chỉ có các cột chứa giá trị thành phần. Nếu ứng dụng cần phân biệt hai trạng thái, phải **mã hóa sự khác biệt một cách rõ ràng** trong mô hình dữ liệu.

Quy tắc này không chỉ áp dụng cho `Address`. Nó cũng xuất hiện với `Money` gồm số tiền và đơn vị tiền, `GeoCoordinate` gồm vĩ độ và kinh độ, `DateRange` gồm ngày bắt đầu và ngày kết thúc, hoặc những giá trị tổng hợp nhiều trường khác.

## 4. Một số giá trị null, một số giá trị khác null

Một tình huống khác với “toàn bộ cột đều `NULL`” là **chỉ một số thành phần bị thiếu**:

```java
Address partial = new Address(
    "12 Nguyễn Trãi",
    "Hà Nội",
    null
);
```

Cách biểu diễn ở database:

```text
ship_street      = "12 Nguyễn Trãi"
ship_city        = "Hà Nội"
ship_postal_code = NULL
```

Khi còn ít nhất một trường có giá trị, có thể phân biệt trạng thái này với nhóm cột đều `NULL`. Nhưng dữ liệu **có hợp lệ hay không** phụ thuộc yêu cầu nghiệp vụ:

- Nếu mã bưu chính là tùy chọn tại thị trường đang phục vụ, địa chỉ trên có thể hợp lệ.
- Nếu cả ba trường đều bắt buộc khi giao tận nơi, đây là địa chỉ chưa đầy đủ.
- Nếu địa chỉ không được phép tồn tại một nửa, việc ghi một tập cột chỉ có một phần giá trị phải được chặn.

JPA cho phép biểu diễn dữ liệu; nó **không tự quyết định** nghiệp vụ có chấp nhận “địa chỉ một phần” hay không. Quy tắc này thuộc domain model, validation và các ràng buộc dữ liệu.

### 4.1. Không nhầm null với chuỗi rỗng

`null`, `""` và `"   "` là những giá trị khác nhau ở phía Java:

```java
String missing = null;
String empty = "";
String spaces = "   ";
```

Nhiều cơ sở dữ liệu cũng phân biệt SQL `NULL` với chuỗi rỗng, nhưng quy tắc cụ thể có thể khác giữa các hệ quản trị. Ví dụ, Oracle Database có hành vi đặc thù khi xử lý chuỗi ký tự độ dài bằng không. Do đó, nếu nghiệp vụ muốn xem chuỗi rỗng hoặc toàn khoảng trắng là “chưa nhập”, hãy chuẩn hóa hoặc validate tại ranh giới nhập dữ liệu một cách có chủ đích.

Ví dụ chính sách ứng dụng:

```java
public static String blankToNull(String value) {
    if (value == null || value.isBlank()) {
        return null;
    }
    return value.trim();
}
```

Đây là một chính sách minh họa, không phải yêu cầu bắt buộc của JPA. Việc cắt khoảng trắng, chấp nhận `null` hay giữ nguyên chuỗi nhập phải phù hợp từng loại dữ liệu.

## 5. Ánh xạ nullable ở mức cột khác với optional ở mức value object

Với `@Embedded`, nullability có thể được nhìn ở hai tầng:

1. **Mức cột:** mỗi `ship_street`, `ship_city`, `ship_postal_code` có cho phép SQL `NULL` hay không.
2. **Mức aggregate:** một địa chỉ giao hàng có thể vắng mặt hoàn toàn hay không, và nếu có thì cần đủ những trường nào.

`@Embedded` không cung cấp một tham số `optional` có tác dụng như `@ManyToOne(optional = ...)` để tự định nghĩa đầy đủ quy tắc cho cả cụm nhiều cột. Nếu muốn một địa chỉ bắt buộc, chỉ dựa vào annotation `@Embedded` là chưa đủ để diễn đạt ràng buộc đó trong mọi tầng.

### 5.1. @Column(nullable = false) áp dụng cho cột

Ví dụ:

```java
@Embedded
@AttributeOverrides({
    @AttributeOverride(
        name = "street",
        column = @Column(name = "ship_street", nullable = false)
    ),
    @AttributeOverride(
        name = "city",
        column = @Column(name = "ship_city", nullable = false)
    ),
    @AttributeOverride(
        name = "postalCode",
        column = @Column(name = "ship_postal_code", nullable = false)
    )
})
private Address shippingAddress;
```

Cấu hình này mô tả ba cột **không nhận SQL `NULL`**. Nếu schema thực sự có ràng buộc `NOT NULL` tương ứng thì một đơn hàng không có địa chỉ sẽ không được phép ghi thành công. Cách này phù hợp khi **mọi đơn hàng luôn phải có địa chỉ**, nhưng không phù hợp với ví dụ đơn hàng `PICKUP` không cần địa chỉ.

Bản thân `nullable = false` chủ yếu là metadata ánh xạ/schema. Việc tạo và cập nhật bảng tự động tùy cách triển khai. **Ràng buộc của database thực tế** mới là lớp bảo vệ cuối cùng trước dữ liệu không hợp lệ do những nguồn ghi khác tạo ra.

### 5.2. Validation ở mức object và các thành phần

Nếu địa chỉ là **tùy chọn**, nhưng *một khi đã cung cấp thì các trường phải đầy đủ*, có thể sử dụng Bean Validation:

```java
import jakarta.persistence.Embeddable;
import jakarta.validation.constraints.NotBlank;

@Embeddable
public class Address {
    @NotBlank
    private String street;

    @NotBlank
    private String city;

    @NotBlank
    private String postalCode;

    protected Address() {
    }

    public Address(String street, String city, String postalCode) {
        this.street = street;
        this.city = city;
        this.postalCode = postalCode;
    }
}
```

Trong entity:

```java
import jakarta.persistence.Embedded;
import jakarta.validation.Valid;

@Valid
@Embedded
private Address shippingAddress;
```

Với Jakarta Bean Validation, `@Valid` yêu cầu kiểm tra sâu các trường của `Address` khi validation được thực hiện. Theo cơ chế cascade validation thông thường, **giá trị `shippingAddress == null` sẽ được bỏ qua**, còn instance `Address` có các trường `null` hoặc toàn khoảng trắng sẽ vi phạm `@NotBlank`.

Một điểm cần phân biệt:

- `@NotBlank` kiểm tra **giá trị String** trong quá trình validation.
- `@Valid` cho phép validation đi vào object lồng nhau; nó không tự yêu cầu object phải khác `null`.
- `@NotNull` đặt trên `shippingAddress` nếu **toàn bộ địa chỉ bắt buộc phải tồn tại**.
- `@Column(nullable = false)` thể hiện yêu cầu về **SQL NULL của cột**; nó không tương đương `@NotBlank` đối với chuỗi rỗng và khoảng trắng.

Ứng dụng cần cấu hình Bean Validation phù hợp. Khi có tích hợp với JPA, các constraint có thể được kiểm tra ở lifecycle event; đối với request API, cũng thường cần validation trước khi đưa dữ liệu vào entity. Ràng buộc ở tầng database vẫn hữu ích để bảo vệ dữ liệu từ mọi đường ghi.

### 5.3. Ràng buộc “hoặc tất cả null, hoặc tất cả đầy đủ”

Nếu database phải chấp nhận không có địa chỉ, nhưng không chấp nhận một địa chỉ thiếu từng phần, có thể đặt ràng buộc `CHECK`. Ví dụ PostgreSQL:

```sql
ALTER TABLE purchase_orders
ADD CONSTRAINT ck_shipping_address_complete
CHECK (
    (
        ship_street IS NULL
        AND ship_city IS NULL
        AND ship_postal_code IS NULL
    )
    OR
    (
        ship_street IS NOT NULL
        AND ship_city IS NOT NULL
        AND ship_postal_code IS NOT NULL
    )
);
```

Bảng trạng thái hợp lệ theo ràng buộc này:

| ship_street | ship_city | ship_postal_code | Được chấp nhận? |
| --- | --- | --- | --- |
| `NULL` | `NULL` | `NULL` | Có: không có địa chỉ. |
| Có giá trị | Có giá trị | Có giá trị | Có: địa chỉ đầy đủ theo định nghĩa ba trường. |
| Có giá trị | `NULL` | Có giá trị | Không: địa chỉ một phần. |
| `NULL` | Có giá trị | `NULL` | Không: địa chỉ một phần. |

Ràng buộc trên chỉ kiểm tra `NULL`, không ngăn chuỗi `""` hoặc khoảng trắng. Nếu cần chặn cả dữ liệu rỗng, kết hợp validation ứng dụng và ràng buộc database thích hợp.

Nếu `postalCode` là tùy chọn, quy tắc có thể đổi thành: **cả địa chỉ không có** hoặc **street và city đều có**, còn postal code được phép `NULL`. Ràng buộc phải phản ánh chính xác mô hình nghiệp vụ.

## 6. Thiết kế trạng thái vắng mặt rõ ràng trong domain model

Khi một value object là tùy chọn, ứng dụng nên xác định **một quy ước nhất quán**. Ví dụ:

- `null` có nghĩa **không có địa chỉ** (khách chọn nhận tại cửa hàng).
- `Address` khác `null` có nghĩa **có địa chỉ hợp lệ**.
- `Address(null, null, null)` và địa chỉ một phần **không được phép** đi vào trạng thái đã xác nhận của đơn hàng.

Quy ước này giải quyết vấn đề từ phía domain: không cần bảo toàn sự khác biệt giữa “đối tượng rỗng” và “không có đối tượng”, bởi ứng dụng chủ động loại bỏ trạng thái rỗng không mang ý nghĩa.

Có thể dùng factory method để xác thực khi tạo giá trị:

```java
import jakarta.persistence.Embeddable;

@Embeddable
public class Address {
    private String street;
    private String city;
    private String postalCode;

    protected Address() {
    }

    private Address(String street, String city, String postalCode) {
        this.street = street;
        this.city = city;
        this.postalCode = postalCode;
    }

    public static Address of(
            String street,
            String city,
            String postalCode) {
        if (street == null || street.isBlank()) {
            throw new IllegalArgumentException("Street is required");
        }
        if (city == null || city.isBlank()) {
            throw new IllegalArgumentException("City is required");
        }
        if (postalCode == null || postalCode.isBlank()) {
            throw new IllegalArgumentException("Postal code is required");
        }
        return new Address(
            street.trim(),
            city.trim(),
            postalCode.trim()
        );
    }
}
```

Đây là **một phiên bản thiết kế khác** của lớp `Address` trong ví dụ đầu tiên. Các ví dụ Java độc lập minh họa những chính sách khác nhau, không phải tất cả được ghép vào một file đồng thời.

Khi dùng value object như trên:

```java
PurchaseOrder pickup = new PurchaseOrder("PICKUP", null);

PurchaseOrder delivery = new PurchaseOrder(
    "DELIVERY",
    Address.of("12 Nguyễn Trãi", "Hà Nội", "100000")
);
```

Các thao tác nghiệp vụ phải thực sự đi qua API tạo object hợp lệ. JPA vẫn có thể khởi tạo entity/embeddable bằng cơ chế riêng khi tải dữ liệu, và những nguồn ghi ngoài JPA có thể đi vòng qua factory. Vì vậy, cần kết hợp domain invariant với validation và database constraint.

**Không nên dùng `Optional<Address>` trực tiếp làm một trường `@Embedded` với giả định mọi provider JPA sẽ tự ánh xạ portable.** Có thể dùng `Optional<Address>` ở phương thức đọc hoặc tầng service:

```java
public java.util.Optional<Address> shippingAddress() {
    return java.util.Optional.ofNullable(this.shippingAddress);
}
```

Còn trường persistent bên dưới vẫn là `Address` có thể `null`, theo cách ánh xạ được JPA hỗ trợ.

## 7. Nếu phải phân biệt “không tồn tại” và “tồn tại nhưng rỗng” thì sao?

Đôi khi **cả hai trạng thái đều có ý nghĩa nghiệp vụ**. Ví dụ một quy trình nhập liệu có ba trạng thái:

1. **Chưa bắt đầu nhập địa chỉ**.
2. **Đã mở phần địa chỉ nhưng chưa nhập trường nào**.
3. **Đã nhập thông tin địa chỉ**.

Nếu chỉ lưu ba cột `ship_street`, `ship_city` và `ship_postal_code`, trạng thái (1) và (2) đều có thể được ghi thành ba `NULL`. Để khôi phục chính xác, cần **lưu thêm thông tin**.

### 7.1. Thêm cột trạng thái cho cả cấu trúc

Có thể dùng enum hoặc mã trạng thái:

```sql
ALTER TABLE purchase_orders
ADD COLUMN address_state VARCHAR(16) NOT NULL DEFAULT 'ABSENT';

ALTER TABLE purchase_orders
ADD CONSTRAINT ck_address_state
CHECK (address_state IN ('ABSENT', 'EMPTY', 'PROVIDED'));
```

Dữ liệu giờ có thể là:

| address_state | ship_street | ship_city | ship_postal_code | Ý nghĩa |
| --- | --- | --- | --- | --- |
| `ABSENT` | `NULL` | `NULL` | `NULL` | Chưa bắt đầu nhập. |
| `EMPTY` | `NULL` | `NULL` | `NULL` | Đã khởi tạo phần địa chỉ, chưa có giá trị. |
| `PROVIDED` | Có giá trị | Có giá trị | Có giá trị | Địa chỉ đã được cung cấp. |

Có thể ánh xạ trường trạng thái của entity như một enum:

```java
public enum AddressState {
    ABSENT,
    EMPTY,
    PROVIDED
}
```

Trong entity, phần bổ sung có thể là:

```java
@jakarta.persistence.Enumerated(jakarta.persistence.EnumType.STRING)
@jakarta.persistence.Column(
    name = "address_state",
    nullable = false,
    length = 16
)
private AddressState addressState;
```

Khi đọc dữ liệu, nghiệp vụ dùng `addressState` làm nguồn thông tin về **sự hiện diện logic của địa chỉ**. Ngay cả nếu provider trả về `shippingAddress == null` khi mọi cột nhúng đều `NULL`, ứng dụng vẫn phân biệt được `ABSENT` với `EMPTY` dựa trên cột trạng thái. Khi xây dựng DTO, có thể biểu diễn `EMPTY` bằng một cấu trúc rỗng theo hợp đồng API mà không cần bắt JPA phải khôi phục một instance `Address` rỗng.

Nếu muốn bảo đảm các trạng thái và cột không mâu thuẫn, cần thêm validation hoặc `CHECK` phù hợp. Cột trạng thái không tự bảo vệ khỏi dữ liệu `address_state = 'PROVIDED'` nhưng các cột địa chỉ lại `NULL`.

### 7.2. Dùng quan hệ sang bảng riêng khi cần định danh cho sự tồn tại

Một giải pháp khác là lưu địa chỉ trong **bảng riêng** và dùng quan hệ tùy chọn, ví dụ `@OneToOne`. Khi một dòng địa chỉ tồn tại, bản thân sự tồn tại của dòng/khóa ngoại có thể biểu diễn việc “có địa chỉ”, kể cả khi một số cột của dòng đó `NULL`.

Điều này **thay đổi mô hình**: địa chỉ không còn là kiểu nhúng đơn giản trải trên cùng bảng, mà là dữ liệu trong một entity/bảng riêng có vòng đời và ràng buộc quan hệ. Cách này chỉ phù hợp khi nghiệp vụ và thiết kế dữ liệu cần tính độc lập đó; không nên tạo bảng riêng chỉ vì chưa thống nhất ý nghĩa của `null`.

### 7.3. Không tự giả định JSON có thể giải quyết ánh xạ nhiều cột

Một số hệ quản trị hỗ trợ cột `JSON` hoặc kiểu dữ liệu cấu trúc. Trong một biểu diễn JSON, có thể phân biệt giá trị không tồn tại, giá trị `null` và object có các field `null` theo quy tắc riêng của JSON và API.

Tuy nhiên, đây là **chiến lược lưu trữ khác** với `@Embedded` trải ra nhiều cột. Việc ánh xạ value object vào một cột JSON phụ thuộc provider, dialect hoặc custom converter. Không nên suy luận rằng mọi cấu trúc `@Embeddable` tự động được lưu thành JSON hay tự bảo toàn đầy đủ các trạng thái `null`.

## 8. Cách truy vấn các cột NULL của cấu trúc nhiều thuộc tính

SQL sử dụng `IS NULL` để kiểm tra giá trị `NULL`; `= NULL` không phải cách kiểm tra đúng do logic ba giá trị của SQL.

Để tìm các đơn hàng mà **cả ba cột địa chỉ đều `NULL`**, có thể viết:

```sql
SELECT id, delivery_mode
FROM purchase_orders
WHERE ship_street IS NULL
  AND ship_city IS NULL
  AND ship_postal_code IS NULL;
```

Để tìm những dòng có **ít nhất một phần thông tin địa chỉ nhưng chưa đầy đủ**, có thể kiểm tra có ít nhất một cột khác `NULL` và ít nhất một cột bằng `NULL`:

```sql
SELECT id
FROM purchase_orders
WHERE (
      ship_street IS NOT NULL
   OR ship_city IS NOT NULL
   OR ship_postal_code IS NOT NULL
)
AND (
      ship_street IS NULL
   OR ship_city IS NULL
   OR ship_postal_code IS NULL
);
```

Một truy vấn phân loại trực tiếp:

```sql
SELECT
    id,
    CASE
        WHEN ship_street IS NULL
         AND ship_city IS NULL
         AND ship_postal_code IS NULL
            THEN 'ABSENT_OR_EMPTY'
        WHEN ship_street IS NOT NULL
         AND ship_city IS NOT NULL
         AND ship_postal_code IS NOT NULL
            THEN 'COMPLETE'
        ELSE 'PARTIAL'
    END AS address_completeness
FROM purchase_orders;
```

Tên `ABSENT_OR_EMPTY` được chọn có chủ đích: **chỉ nhìn các cột thành phần thì không biết object Java trước đó `null` hay rỗng**.

### 8.1. Cẩn trọng với truy vấn null của embedded object trong JPQL

Trong JPQL hoặc Criteria API, một biểu thức biểu diễn cả `Address` gồm nhiều cột có thể không được xử lý như một cột SQL scalar duy nhất. Hỗ trợ cho điều kiện kiểm tra trực tiếp cả đối tượng nhúng, chẳng hạn dạng:

```sql
-- Ví dụ ý tưởng, KHÔNG coi là JPQL di động giữa mọi provider:
-- WHERE o.shippingAddress IS NULL
```

có thể phụ thuộc cách provider dịch một path đa cột. Nếu cần định nghĩa chính xác “mọi cột đều `NULL`”, truy vấn SQL với điều kiện từng cột là cách biểu diễn rõ ràng; hoặc kiểm tra hỗ trợ của JPQL/Criteria và SQL được sinh ra trong môi trường ORM đã chọn.

Nếu yêu cầu chính là **trạng thái nghiệp vụ** như `ABSENT` và `EMPTY`, hãy truy vấn cột trạng thái được lưu riêng thay vì suy luận từ các trường nhúng.

## 9. Hai hoặc nhiều embedded object trong cùng entity

Một entity có thể nhúng nhiều giá trị cùng một kiểu, như **địa chỉ thanh toán** và **địa chỉ giao hàng**:

```text
PurchaseOrder
  billingAddress  : Address(street, city, postalCode)
  shippingAddress : Address(street, city, postalCode)
```

Khi trải ra bảng, phải có các nhóm cột phân biệt:

```text
bill_street   bill_city   bill_postal_code
ship_street   ship_city   ship_postal_code
```

JPA sử dụng `@AttributeOverride` để ánh xạ chính xác từng thuộc tính:

```java
@Embedded
@AttributeOverrides({
    @AttributeOverride(
        name = "street",
        column = @Column(name = "bill_street")
    ),
    @AttributeOverride(
        name = "city",
        column = @Column(name = "bill_city")
    ),
    @AttributeOverride(
        name = "postalCode",
        column = @Column(name = "bill_postal_code")
    )
})
private Address billingAddress;
```

Với `shippingAddress` có thể dùng bộ override `ship_*` như ví dụ đầu bài. Khi cả hai nhúng cùng kiểu, mỗi nhóm cột **có nullability và quy tắc đầy đủ riêng**.

Ví dụ, địa chỉ thanh toán có thể luôn bắt buộc, còn địa chỉ giao hàng được phép vắng mặt nếu khách nhận tại cửa hàng. Khi đó, không nên dùng một quy tắc `nullable = false` duy nhất cho mọi chỗ nhúng `Address`; cần đặt quy tắc đúng theo từng ngữ cảnh sử dụng.

Nếu có **embedded object lồng bên trong embedded object khác**, JPA có thể ánh xạ tiếp các thành phần lồng nhau vào bảng của entity sở hữu. Vấn đề các cột đều `NULL` tiếp tục xuất hiện tại những mức cấu trúc đó. Càng có nhiều thuộc tính con và nhiều mức lồng, ứng dụng càng cần quy định cụ thể ý nghĩa “vắng mặt”, “rỗng” và “đã điền đủ”.

## 10. Phân biệt null của kiểu giá trị với null của các mapping khác

Không phải mọi thuộc tính của entity đều có cùng cách biểu diễn `null`.

| Thuộc tính | Ánh xạ thường gặp | Biểu diễn null điển hình |
| --- | --- | --- |
| Giá trị đơn, như `String note` | `@Basic` / `@Column` | Một cột nhận SQL `NULL`. |
| Kiểu nhúng `Address` gồm ba trường | `@Embedded` | Nhiều cột thành phần có thể `NULL`. |
| Quan hệ nhiều về một, như `Customer customer` | `@ManyToOne` / `@JoinColumn` | Khóa ngoại có thể `NULL` nếu quan hệ tùy chọn. |
| Tập hợp kiểu nhúng | `@ElementCollection` | Thường là các hàng trong collection table; “tập hợp rỗng” khác với một giá trị nhúng `null`. |
| Khóa chính tổng hợp | `@EmbeddedId` | Các thành phần khóa chính phải xác định được danh tính; **không dùng embedded ID `null` như một value object tùy chọn**. |
| Kiểu giá trị lưu trong một cột nhờ converter | `@Convert`, provider-specific mapping | Nullability của cột đơn và cách converter xử lý dữ liệu. |

Lưu ý `@EmbeddedId` có thể sử dụng một class `@Embeddable`, nhưng **vai trò hoàn toàn khác**: nó biểu diễn khóa chính của entity. SQL primary key không chấp nhận `NULL` ở các thành phần khóa, và JPA cần định danh hợp lệ cho entity. Không áp dụng mô hình “địa chỉ tùy chọn” cho khóa chính tổng hợp.

Đối với `@ManyToOne`, một khóa ngoại `NULL` thường diễn đạt không có liên kết. Với `@Embedded`, không có một khóa ngoại riêng để dùng làm dấu hiệu “có/không có object”; vì thế sự mơ hồ của nhóm cột đều `NULL` xuất hiện rõ hơn.

## 11. Null trong DTO, API cập nhật và dữ liệu nhập chưa hoàn chỉnh

Vòng đời của một value object JPA khác với trạng thái yêu cầu HTTP. Ví dụ trong một yêu cầu cập nhật từng phần (PATCH), ứng dụng có thể cần phân biệt:

```json
{}
```

với:

```json
{"shippingAddress": null}
```

và:

```json
{
  "shippingAddress": {
    "street": null,
    "city": null,
    "postalCode": null
  }
}
```

Chúng có thể mang ba ý nghĩa khác nhau:

- **Không có trường `shippingAddress` trong request:** giữ nguyên địa chỉ cũ.
- **Có trường với `null`:** xóa địa chỉ hiện tại.
- **Có object nhưng mọi field `null`:** người dùng đã gửi một cấu trúc rỗng; có thể cần báo lỗi validation hoặc lưu trạng thái bản nháp riêng.

Nếu cả ba trường hợp được đưa thẳng vào một thuộc tính `@Embedded` mà không có quy tắc chuyển đổi, nghiệp vụ có thể vô tình mất thông tin về **trường không xuất hiện** so với **trường đã được cung cấp với null**.

Một thiết kế thích hợp là dùng **request DTO/command** ở tầng API để ghi nhận ý định cập nhật và validation, sau đó mới chuyển thành entity/value object đã chuẩn hóa. Không nên kỳ vọng `@Embedded` hoặc database tự giải quyết ngữ nghĩa PATCH.

Đặc biệt, khi người dùng đang nhập form theo nhiều bước, dữ liệu chưa đầy đủ không nhất thiết nên được biểu diễn như một `Address` hoàn chỉnh trong entity đã xác nhận. Có thể tách mô hình **draft input** cho phép các trường rỗng khỏi mô hình **confirmed Address** yêu cầu những trường cần thiết.

## 12. Ví dụ ứng dụng: đơn hàng tự nhận và giao tận nơi

Giả sử hệ thống quy định:

- Với `deliveryMode = "PICKUP"`: không có địa chỉ giao hàng.
- Với `deliveryMode = "DELIVERY"`: phải cung cấp đầy đủ `street`, `city` và `postalCode`.
- Không chấp nhận một địa chỉ chỉ có một hoặc hai trường.

Mô hình Java minh họa:

```java
// Address.of(...) là factory method bảo đảm ba trường hợp lệ.
PurchaseOrder pickup = new PurchaseOrder("PICKUP", null);

PurchaseOrder delivery = new PurchaseOrder(
    "DELIVERY",
    Address.of("12 Nguyễn Trãi", "Hà Nội", "100000")
);
```

Ở tầng service, có thể kiểm tra quy tắc trước khi persist:

```java
public static void validateDelivery(PurchaseOrder order) {
    boolean hasAddress = order.getShippingAddress() != null;

    if ("PICKUP".equals(order.getDeliveryMode()) && hasAddress) {
        throw new IllegalArgumentException(
            "Pickup order must not have a shipping address"
        );
    }

    if ("DELIVERY".equals(order.getDeliveryMode()) && !hasAddress) {
        throw new IllegalArgumentException(
            "Delivery order requires a shipping address"
        );
    }
}
```

Đoạn này giả định `Address.of(...)` bảo đảm object được tạo qua API nghiệp vụ đã có giá trị đầy đủ. Trong ứng dụng thật, phải đảm bảo các luồng nạp dữ liệu khác cũng được validate trước khi lưu.

Để database thực thi một phần quy tắc, PostgreSQL có thể dùng `CHECK` gắn với `delivery_mode`:

```sql
ALTER TABLE purchase_orders
ADD CONSTRAINT ck_delivery_address_by_mode
CHECK (
    (
        delivery_mode = 'PICKUP'
        AND ship_street IS NULL
        AND ship_city IS NULL
        AND ship_postal_code IS NULL
    )
    OR
    (
        delivery_mode = 'DELIVERY'
        AND ship_street IS NOT NULL
        AND ship_city IS NOT NULL
        AND ship_postal_code IS NOT NULL
    )
);
```

Ràng buộc này giả định ứng dụng chỉ sử dụng hai giá trị `PICKUP` và `DELIVERY`. Nếu có các hình thức khác, quy tắc cần được mở rộng tương ứng. Khi thêm ràng buộc vào hệ thống đã có dữ liệu, các dòng cũ phải thỏa mãn điều kiện trước khi migration thành công.

Những trường hợp được kiểm soát:

| delivery_mode | Trạng thái cột địa chỉ | Kết quả |
| --- | --- | --- |
| `PICKUP` | Tất cả `NULL` | Hợp lệ. |
| `PICKUP` | Có ít nhất một giá trị | Không hợp lệ. |
| `DELIVERY` | Tất cả có giá trị | Hợp lệ theo kiểm tra `NULL`. |
| `DELIVERY` | Tất cả `NULL` | Không hợp lệ. |
| `DELIVERY` | Chỉ một phần có giá trị | Không hợp lệ. |

Ở đây, thiết kế cố ý **không coi một địa chỉ rỗng khác null là trạng thái hợp lệ**. Nhờ đó, việc không lưu riêng dấu hiệu tồn tại của embedded object không còn gây mơ hồ trong nghiệp vụ.

## 13. Những sai lầm thường gặp

### 13.1. Cho rằng null của object có một cột SQL riêng

`@Embedded` thông thường trải nhiều trường lên bảng chủ. Nếu không thiết kế cột trạng thái, giá trị `null` của cả object không có nơi lưu riêng ngoài những cột thành phần.

### 13.2. Cho rằng new Address(null, null, null) luôn được tải lại thành object khác null

Các cột đều `NULL` không chứa thông tin về việc object Java từng được khởi tạo. Cách provider khôi phục embedded object có thể khác nhau; không xây dựng hợp đồng nghiệp vụ dựa vào giả định này.

### 13.3. Cho rằng một cột null đồng nghĩa cả Address null

`ship_postal_code IS NULL` chỉ nói **mã bưu chính** chưa có. `ship_street` và `ship_city` vẫn có thể khác `NULL`. Muốn xác định một nhóm cột hoàn toàn vắng mặt phải xét cả nhóm theo quy ước đang dùng.

### 13.4. Dùng @Column(nullable = false) trong mọi trường hợp để “giải quyết null”

Nếu value object có thể vắng mặt hợp lệ (như địa chỉ của đơn nhận tại cửa hàng), gắn `nullable = false` cho toàn bộ cột khiến trạng thái vắng mặt không lưu được. Nên diễn đạt chính xác quy tắc “vắng mặt hoặc đầy đủ” bằng validation và `CHECK`.

### 13.5. Dùng @NotNull trên Embedded mà không kiểm tra thuộc tính con

`@NotNull` trên object chỉ kiểm tra object tồn tại. Nó không đảm bảo các field con hợp lệ. Khi có Bean Validation, dùng thêm `@Valid` cho object và constraint phù hợp ở các field con, kết hợp ràng buộc database nếu cần.

### 13.6. Dùng getter tính toán để che dữ liệu null không hợp lệ

Một getter như `getCityLabel()` trả về `"Chưa có"` khi `city == null` chỉ đổi cách hiển thị, không biến dữ liệu thiếu thành hợp lệ. Nên tách logic hiển thị và quy tắc xác thực dữ liệu.

### 13.7. Giữ trạng thái nhập liệu nhiều bước bằng embedded object duy nhất

Những trạng thái bản nháp như “chưa mở phần địa chỉ”, “đã mở nhưng bỏ trống” và “đã điền đủ” có thể cần một trạng thái hoặc DTO riêng. Chỉ dùng các cột địa chỉ nullable sẽ không bảo toàn đủ khác biệt nếu tất cả cùng tạo ra bộ cột `NULL`.

### 13.8. Áp dụng quy tắc nullable của Embedded cho EmbeddedId

`@EmbeddedId` đại diện khóa chính tổng hợp, không phải cấu trúc giá trị tùy chọn. Các thành phần định danh phải hợp lệ và không được SQL primary key cho phép `NULL`.

## 14. Câu hỏi tự kiểm tra

**1. `shippingAddress = null` và `new Address(null, null, null)` khác gì trong Java?**

Trường hợp đầu không có object. Trường hợp sau có object `Address`, nhưng tất cả thuộc tính của nó là `null`.

**2. Nếu `Address` ánh xạ vào ba cột và cả ba cột đều `NULL`, có biết ban đầu object là `null` hay object rỗng không?**

Không thể biết chỉ dựa trên ba cột. Muốn phân biệt cần thêm dữ liệu, chẳng hạn cột trạng thái, hoặc thiết kế mô hình khác.

**3. Nếu chỉ `ship_postal_code` là `NULL` thì có chắc `shippingAddress == null` không?**

Không. Các cột còn lại có thể có giá trị, biểu diễn một địa chỉ chưa đủ thông tin hoặc một địa chỉ hợp lệ có mã bưu chính tùy chọn.

**4. Vì sao `@Valid` và `@NotBlank` có thể cần đi cùng nhau?**

`@Valid` yêu cầu validation đi vào object nhúng; `@NotBlank` kiểm tra các thành phần chuỗi. Khi object là `null`, việc cascade validation thông thường bỏ qua object đó; nếu object bắt buộc phải tồn tại, cần thêm `@NotNull` ở trường nhúng.

**5. Có thể dùng `@Column(nullable = false)` cho địa chỉ tùy chọn không?**

Nếu cả object được phép `null`, đặt `NOT NULL` trên từng cột địa chỉ sẽ mâu thuẫn với việc không có địa chỉ. Cần mô hình ràng buộc cho phép **toàn bộ `NULL` hoặc tổ hợp hợp lệ**, thay vì bắt mọi cột luôn khác `NULL`.

**6. Làm sao tìm các hàng không có bất kỳ giá trị địa chỉ nào?**

Dùng SQL `IS NULL` cho **tất cả** cột thành phần. Không dùng phép so sánh `= NULL` và không chỉ kiểm tra một cột.

**7. Khi một form phân biệt “không gửi trường” và “gửi địa chỉ null”, nên xử lý ở đâu?**

Ở tầng API/DTO hoặc command xử lý thay đổi, trước khi chuyển sang entity `@Embedded`. Database không thể suy ra sự khác biệt này nếu chỉ nhận cùng một bộ giá trị cột `NULL`.

## 15. Ghi nhớ cốt lõi

**Null của value object nhiều thuộc tính là bài toán của cả mô hình Java lẫn mô hình quan hệ.** Java có thể phân biệt một tham chiếu `null` với một object tồn tại nhưng mọi field `null`. Khi `@Embedded` trải object thành nhiều cột, hai trạng thái đó có thể được lưu giống hệt nhau bằng một nhóm SQL `NULL`; thông tin về sự tồn tại của object có thể không còn sau khi tải lại.

Cách thiết kế vững chắc là xác định ngay từ đầu: **cả giá trị có được phép vắng mặt không, những thành phần nào bắt buộc khi giá trị tồn tại, và “object rỗng” có mang ý nghĩa riêng không**. Dùng factory/validation để bảo vệ quy tắc domain, ràng buộc database để giữ dữ liệu nhất quán, và lưu dấu hiệu trạng thái riêng khi cần phân biệt những tình huống không thể biểu diễn chỉ bằng các cột thành phần.
