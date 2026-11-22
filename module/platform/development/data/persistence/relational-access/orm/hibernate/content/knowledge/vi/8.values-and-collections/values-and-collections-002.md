# Ghi đè tên cột khi nhúng cùng một kiểu ở nhiều vị trí trong Hibernate

Trong mô hình hướng đối tượng, một kiểu giá trị có thể được tái sử dụng nhiều lần trong cùng một thực thể. Ví dụ, đơn hàng có **địa chỉ thanh toán** và **địa chỉ giao hàng**, cùng dùng kiểu Java `PostalAddress`. Nếu địa chỉ được mô hình hóa bằng `@Embeddable` và nhúng bằng `@Embedded`, Hibernate cần ánh xạ các thuộc tính của cả hai địa chỉ vào những cột riêng của bảng. Mặc định, hai lần nhúng cùng một kiểu có thể cố sử dụng cùng các tên cột như `street`, `city`, `postal_code` và làm ánh xạ bị trùng.

Giải pháp theo Jakarta Persistence (JPA) là sử dụng **`@AttributeOverride`** hoặc **`@AttributeOverrides`** tại từng vị trí nhúng để chỉ định tên cột thực tế. Cách này giữ nguyên định nghĩa value object, không cần tạo hai lớp `BillingAddress` và `ShippingAddress` chỉ khác tên cột, đồng thời giúp Hibernate biết mỗi đường dẫn thuộc tính được lưu ở đâu.

Bài học tập trung vào việc **ghi đè tên cột khi cùng một `@Embeddable` xuất hiện nhiều lần**, bao gồm cú pháp, cơ chế ánh xạ, SQL đọc/ghi, thuộc tính nhúng lồng nhau, `@ElementCollection`, quan hệ nằm trong embeddable và những lỗi thường gặp.

> **Phiên bản:** Ví dụ dùng `jakarta.persistence` và Hibernate ORM 6.x. Nếu ứng dụng dùng Hibernate 5 với JPA cũ, package annotation thường là `javax.persistence`. `@AttributeOverride` là tính năng chuẩn JPA; một số quy ước đặt tên ngầm định và phần mở rộng của Hibernate có thể khác theo phiên bản và `ImplicitNamingStrategy`/`PhysicalNamingStrategy`.

## 1. Từ kiểu giá trị trong Java đến các cột SQL

Xét kiểu `PostalAddress`:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

@Embeddable
public class PostalAddress {
    @Column(name = "street", nullable = false, length = 200)
    private String street;

    @Column(name = "city", nullable = false, length = 100)
    private String city;

    @Column(name = "postal_code", length = 20)
    private String postalCode;

    protected PostalAddress() {
        // JPA cần constructor không tham số có mức truy cập phù hợp.
    }

    public PostalAddress(String street, String city, String postalCode) {
        this.street = street;
        this.city = city;
        this.postalCode = postalCode;
    }

    public String getStreet() { return street; }
    public String getCity() { return city; }
    public String getPostalCode() { return postalCode; }
}
~~~

`@Embeddable` mô tả một **kiểu giá trị được lưu như một phần của entity sở hữu**. `PostalAddress` không có `@Id`, không có identity độc lập và không tự mở một bảng riêng chỉ vì được đánh dấu `@Embeddable`.

Nếu một entity chỉ nhúng một lần:

~~~java
@Entity
@Table(name = "customer")
public class Customer {
    @Id
    private Long id;

    @Embedded
    private PostalAddress address;
}
~~~

Một ánh xạ thông thường là:

| Đường dẫn Java | Bảng | Cột |
|---|---|---|
| `Customer.id` | `customer` | `id` |
| `Customer.address.street` | `customer` | `street` |
| `Customer.address.city` | `customer` | `city` |
| `Customer.address.postalCode` | `customer` | `postal_code` |

Các thuộc tính của embeddable được “trải phẳng” thành cột của entity sở hữu. Hibernate quản lý object `PostalAddress` như một phần state của `Customer`.

### Khi nhúng cùng một kiểu hai lần

~~~java
@Entity
@Table(name = "delivery_order")
public class DeliveryOrder {
    @Id
    private Long id;

    @Embedded
    private PostalAddress billingAddress;

    @Embedded
    private PostalAddress shippingAddress;
}
~~~

Nếu mỗi lần nhúng đều dùng tên cột nội bộ của `PostalAddress`, cả hai cùng muốn ánh xạ:

~~~text
billingAddress.street   -> delivery_order.street
shippingAddress.street  -> delivery_order.street

billingAddress.city     -> delivery_order.city
shippingAddress.city    -> delivery_order.city

billingAddress.postalCode  -> delivery_order.postal_code
shippingAddress.postalCode -> delivery_order.postal_code
~~~

Hai vai trò địa chỉ khác nhau không thể được lưu độc lập nếu chúng cùng trỏ vào đúng một bộ cột. Hibernate có thể báo lỗi mapping trùng cột khi khởi tạo `SessionFactory` hoặc áp dụng một quy tắc implicit naming khác tùy cấu hình; dù trong trường hợp nào, **không nên phụ thuộc vào cách tự đặt tên không được kiểm soát** khi schema yêu cầu rõ `billing_*` và `shipping_*`.

Schema mong muốn:

~~~text
delivery_order
+--------------------------+
| id                       |
| billing_street           |
| billing_city             |
| billing_postal_code      |
| shipping_street          |
| shipping_city            |
| shipping_postal_code     |
+--------------------------+
~~~

## 2. `@AttributeOverride` và `@AttributeOverrides` giải quyết xung đột

`@AttributeOverride` ghi đè **metadata ánh xạ cột của một thuộc tính persistent** tại vị trí đang sử dụng. `@AttributeOverrides` là container chứa nhiều `@AttributeOverride`.

~~~java
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
    )
})
private PostalAddress billingAddress;
~~~

Hãy phân biệt hai thuộc tính thường dễ nhầm:

| Thành phần annotation | Chỉ đến | Ví dụ |
|---|---|---|
| `@AttributeOverride(name = "...")` | **Tên thuộc tính Java** trong `@Embeddable`, theo access strategy đang dùng | `street`, `city`, `postalCode` |
| `@Column(name = "...")` | **Tên cột vật lý/logical mapping** ứng với thuộc tính tại lần nhúng đó | `billing_street`, `billing_city`, `billing_postal_code` |

`name = "postalCode"` là chính xác vì `PostalAddress` có field Java `postalCode`. Viết `name = "postal_code"` là nhầm tên cột với tên thuộc tính, có thể dẫn đến mapping không hợp lệ hoặc override không tác động vào thuộc tính dự định.

`@AttributeOverride` không tạo bản sao object, không tạo association, không thay đổi kiểu dữ liệu Java và không làm một embeddable có identity riêng. Nó thay đổi **cách cột của một thuộc tính được ánh xạ ở vị trí sử dụng cụ thể**.

### Một thuộc tính thì dùng `@AttributeOverride` đơn

Nếu chỉ một tên cột cần khác:

~~~java
@Embedded
@AttributeOverride(
    name = "postalCode",
    column = @Column(name = "shipping_postal_code")
)
private PostalAddress shippingAddress;
~~~

Tuy nhiên, khi nhúng cùng một kiểu hai lần vào một bảng và **nhiều cột mặc định bị trùng**, chỉ override một cột là chưa đủ. Cần xử lý các cột còn lại bằng annotation hoặc một chiến lược naming nhất quán đã được kiểm chứng.

## 3. Ví dụ hoàn chỉnh: địa chỉ thanh toán và giao hàng

Giả sử yêu cầu nghiệp vụ:

- Một đơn hàng có đúng một ID.
- Mỗi đơn có địa chỉ thanh toán và địa chỉ giao hàng.
- Hai địa chỉ cùng cấu trúc dữ liệu, nhưng giá trị có thể khác nhau.
- Các cột được lưu trực tiếp trong bảng `delivery_order`.

Entity:

~~~java
import jakarta.persistence.AttributeOverride;
import jakarta.persistence.AttributeOverrides;
import jakarta.persistence.Column;
import jakarta.persistence.Embedded;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.SequenceGenerator;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "delivery_order")
@SequenceGenerator(
    name = "delivery_order_gen",
    sequenceName = "delivery_order_seq",
    allocationSize = 1
)
public class DeliveryOrder {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "delivery_order_gen"
    )
    private Long id;

    @Version
    private long version;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(
            name = "street",
            column = @Column(
                name = "billing_street", nullable = false, length = 200
            )
        ),
        @AttributeOverride(
            name = "city",
            column = @Column(
                name = "billing_city", nullable = false, length = 100
            )
        ),
        @AttributeOverride(
            name = "postalCode",
            column = @Column(
                name = "billing_postal_code", length = 20
            )
        )
    })
    private PostalAddress billingAddress;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(
            name = "street",
            column = @Column(
                name = "shipping_street", nullable = false, length = 200
            )
        ),
        @AttributeOverride(
            name = "city",
            column = @Column(
                name = "shipping_city", nullable = false, length = 100
            )
        ),
        @AttributeOverride(
            name = "postalCode",
            column = @Column(
                name = "shipping_postal_code", length = 20
            )
        )
    })
    private PostalAddress shippingAddress;

    protected DeliveryOrder() {}

    public DeliveryOrder(
            PostalAddress billingAddress,
            PostalAddress shippingAddress) {
        this.billingAddress = billingAddress;
        this.shippingAddress = shippingAddress;
    }

    public Long getId() { return id; }
    public PostalAddress getBillingAddress() { return billingAddress; }
    public PostalAddress getShippingAddress() { return shippingAddress; }

    public void changeShippingAddress(PostalAddress newAddress) {
        this.shippingAddress = newAddress;
    }

    public void changeBillingAddress(PostalAddress newAddress) {
        this.billingAddress = newAddress;
    }
}
~~~

Ở đây:

1. Hibernate tạo **một** entity metadata cho `DeliveryOrder`.
2. Hai field `billingAddress` và `shippingAddress` cùng có kiểu `PostalAddress`.
3. Hai annotation `@AttributeOverrides` định nghĩa sáu cột khác nhau.
4. `@Id` và `@Version` thuộc `DeliveryOrder`, không nằm ở embeddable.
5. Thay đổi một địa chỉ là thay đổi state của cùng entity, được quản lý bởi persistence context và transaction của entity đó.

### DDL PostgreSQL tương ứng

~~~sql
CREATE SEQUENCE delivery_order_seq
    START WITH 1 INCREMENT BY 1;

CREATE TABLE delivery_order (
    id                    BIGINT PRIMARY KEY,
    version               BIGINT NOT NULL,
    billing_street        VARCHAR(200) NOT NULL,
    billing_city          VARCHAR(100) NOT NULL,
    billing_postal_code   VARCHAR(20),
    shipping_street       VARCHAR(200) NOT NULL,
    shipping_city         VARCHAR(100) NOT NULL,
    shipping_postal_code  VARCHAR(20)
);
~~~

Schema được quản lý bằng migration phải khớp metadata thực tế. `@Column(nullable = false)` mô tả ràng buộc cột; trong production, ràng buộc `NOT NULL` thật sự do database quyết định. Nếu chạy với schema do migration tạo, Hibernate không thể biến một cột database sai tên thành đúng chỉ bằng annotation.

### Bản đồ ánh xạ cuối cùng

| Đường dẫn object | Cột SQL |
|---|---|
| `order.id` | `id` |
| `order.version` | `version` |
| `order.billingAddress.street` | `billing_street` |
| `order.billingAddress.city` | `billing_city` |
| `order.billingAddress.postalCode` | `billing_postal_code` |
| `order.shippingAddress.street` | `shipping_street` |
| `order.shippingAddress.city` | `shipping_city` |
| `order.shippingAddress.postalCode` | `shipping_postal_code` |

Không tồn tại `billing_address_id` hoặc `shipping_address_id` ở ví dụ này. Hai địa chỉ là **value objects**, chứ không phải hai entity `Address` với foreign key.

## 4. Đường đi từ `persist()` đến `INSERT`

Ứng dụng sử dụng entity như một object thống nhất:

~~~java
PostalAddress billing = new PostalAddress(
    "12 Nguyen Hue", "Ho Chi Minh City", "700000"
);

PostalAddress shipping = new PostalAddress(
    "45 Le Loi", "Da Nang", "550000"
);

EntityTransaction tx = entityManager.getTransaction();
tx.begin();

DeliveryOrder order = new DeliveryOrder(billing, shipping);
entityManager.persist(order);
tx.commit();
~~~

Hibernate cần lấy/gán identifier theo generator và phát sinh SQL tương tự:

~~~sql
-- Với @SequenceGenerator(allocationSize = 1), có thể lấy ID trước:
SELECT nextval('delivery_order_seq');

-- Khi flush:
INSERT INTO delivery_order (
    billing_city,
    billing_postal_code,
    billing_street,
    shipping_city,
    shipping_postal_code,
    shipping_street,
    version,
    id
) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
~~~

Danh sách/thứ tự cột và thời điểm SQL chính xác phụ thuộc Hibernate version, mapping và generator. Điểm cần quan sát là **một `INSERT` vào một bảng có cả hai nhóm cột**, dù trong Java có hai object `PostalAddress`.

Một bản ghi có thể trông như sau:

~~~text
id = 100
billing_street = "12 Nguyen Hue"
billing_city = "Ho Chi Minh City"
billing_postal_code = "700000"
shipping_street = "45 Le Loi"
shipping_city = "Da Nang"
shipping_postal_code = "550000"
~~~

Không cần gọi `persist(billing)` hoặc `persist(shipping)` vì hai object này không phải entity. Hibernate đưa các field của chúng vào lệnh lưu `DeliveryOrder`.

### Khi thay đổi một địa chỉ

~~~java
tx.begin();

DeliveryOrder managed =
    entityManager.find(DeliveryOrder.class, orderId);

managed.changeShippingAddress(new PostalAddress(
    "99 Tran Phu", "Hue", "530000"
));

tx.commit();
~~~

Hibernate dirty checking state của entity. Trong một số cấu hình, `UPDATE` có thể bao gồm nhiều cột có thể cập nhật; nếu dùng cơ chế dynamic update, Hibernate có thể giới hạn tập cột thay đổi. Vì thế không nên coi “chỉ đổi shippingAddress” là cam kết Hibernate luôn chỉ gửi đúng ba cột `shipping_*`:

~~~sql
-- Ví dụ SQL có thể xuất hiện khi tối ưu update theo cột:
UPDATE delivery_order
SET shipping_street = ?,
    shipping_city = ?,
    shipping_postal_code = ?,
    version = ?
WHERE id = ? AND version = ?;
~~~

`@AttributeOverrides` quyết định **cột nào lưu field nào**; nó không trực tiếp quyết định Hibernate tối ưu `UPDATE` theo từng cột ra sao.

## 5. Cú pháp đường dẫn trong `name`: thuộc tính Java, không phải cột

Một lỗi rất phổ biến là viết:

~~~java
@AttributeOverride(
    name = "postal_code", // Sai: đây là tên SQL, không phải field Java.
    column = @Column(name = "shipping_postal_code")
)
~~~

Với `PostalAddress`, phải viết:

~~~java
@AttributeOverride(
    name = "postalCode",  // Đúng: tên thuộc tính persistent của embeddable.
    column = @Column(name = "shipping_postal_code")
)
~~~

Trong `@AttributeOverride` đặt trực tiếp trên field `shippingAddress`, đường dẫn `name` bắt đầu **bên trong** `PostalAddress`. Vì vậy:

~~~text
@Embedded field: shippingAddress
    |
    +-- name = "street"
    +-- name = "city"
    +-- name = "postalCode"
~~~

Không cần viết `name = "shippingAddress.street"` khi annotation nằm ngay trên chính field `shippingAddress`; tiền tố field chỉ cần trong những ngữ cảnh annotation ở cấp entity hay một đường dẫn chứa nhiều mức.

### Ghi đè ở cấp entity

JPA cũng cho phép khai báo đường dẫn đầy đủ ở cấp kiểu entity, ví dụ:

~~~java
@Entity
@Table(name = "delivery_order")
@AttributeOverrides({
    @AttributeOverride(
        name = "billingAddress.street",
        column = @Column(name = "billing_street")
    ),
    @AttributeOverride(
        name = "shippingAddress.street",
        column = @Column(name = "shipping_street")
    )
})
public class OrderWithClassLevelOverrides {
    @Id
    private Long id;

    @Embedded
    private PostalAddress billingAddress;

    @Embedded
    private PostalAddress shippingAddress;
}
~~~

Ví dụ này chỉ ghi đè `street` để minh họa **đường dẫn ở cấp entity**; nếu các field `city` và `postalCode` cũng xung đột, phải ghi đè tiếp hoặc có naming strategy xử lý đúng. Trong ứng dụng thực tế, việc đặt `@AttributeOverrides` ngay tại từng `@Embedded` thường dễ đọc hơn khi có nhiều vai trò cùng kiểu.

## 6. Giữ nguyên định nghĩa kiểu giá trị và tái sử dụng theo ngữ cảnh

`@Embeddable` mô tả **ý nghĩa giá trị**:

~~~java
@Embeddable
public class MonetaryAmount {
    @Column(name = "amount_value", precision = 19, scale = 2)
    private BigDecimal amount;

    @Column(name = "currency_code", length = 3)
    private String currency;

    protected MonetaryAmount() {}

    public MonetaryAmount(BigDecimal amount, String currency) {
        this.amount = amount;
        this.currency = currency;
    }
}
~~~

Một `InvoiceLine` có thể dùng cùng kiểu cho **đơn giá** và **giá giảm**:

~~~java
@Entity
@Table(name = "invoice_line")
public class InvoiceLine {
    @Id
    private Long id;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(
            name = "amount",
            column = @Column(
                name = "unit_price_amount", precision = 19, scale = 2
            )
        ),
        @AttributeOverride(
            name = "currency",
            column = @Column(
                name = "unit_price_currency", length = 3
            )
        )
    })
    private MonetaryAmount unitPrice;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(
            name = "amount",
            column = @Column(
                name = "discount_amount", precision = 19, scale = 2
            )
        ),
        @AttributeOverride(
            name = "currency",
            column = @Column(
                name = "discount_currency", length = 3
            )
        )
    })
    private MonetaryAmount discount;
}
~~~

| Field Java | Các cột SQL |
|---|---|
| `unitPrice` | `unit_price_amount`, `unit_price_currency` |
| `discount` | `discount_amount`, `discount_currency` |

Tái sử dụng kiểu `MonetaryAmount` có lợi khi quy tắc dữ liệu giống nhau. Nếu discount mang ngữ nghĩa khác hẳn amount (chẳng hạn phần trăm từ 0 đến 100), có thể cần kiểu value object riêng như `DiscountRate`. `@AttributeOverride` giải quyết tên cột, **không thay thế thiết kế domain đúng**.

### Một kiểu có thể được nhúng ở nhiều entity

`PostalAddress` cũng có thể xuất hiện trong `Customer`, `Supplier`, `Warehouse` và `DeliveryOrder`. Mỗi lần sử dụng có thể có tên cột riêng; mapping ở một entity không tự sửa mapping của các entity còn lại. Điều này cho phép giữ lớp value object chung mà vẫn tương thích nhiều schema lịch sử.

## 7. Embeddable lồng nhau: `name = "nested.field"`

Tình huống phức tạp hơn: một địa chỉ có tọa độ `GeoPoint`, và một tuyến giao hàng có **điểm đi** cùng **điểm đến**. Cả hai dùng cùng kiểu `LocatedAddress` chứa một embeddable lồng bên trong.

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import jakarta.persistence.Embedded;
import java.math.BigDecimal;

@Embeddable
public class GeoPoint {
    @Column(name = "latitude", precision = 10, scale = 7)
    private BigDecimal latitude;

    @Column(name = "longitude", precision = 10, scale = 7)
    private BigDecimal longitude;

    protected GeoPoint() {}

    public GeoPoint(BigDecimal latitude, BigDecimal longitude) {
        this.latitude = latitude;
        this.longitude = longitude;
    }
}

@Embeddable
public class LocatedAddress {
    @Column(name = "city", length = 100)
    private String city;

    @Embedded
    private GeoPoint coordinates;

    protected LocatedAddress() {}

    public LocatedAddress(String city, GeoPoint coordinates) {
        this.city = city;
        this.coordinates = coordinates;
    }
}
~~~

Ánh xạ trong một entity:

~~~java
@Entity
@Table(name = "delivery_route")
public class DeliveryRoute {
    @Id
    private Long id;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(
            name = "city",
            column = @Column(name = "origin_city", length = 100)
        ),
        @AttributeOverride(
            name = "coordinates.latitude",
            column = @Column(
                name = "origin_lat", precision = 10, scale = 7
            )
        ),
        @AttributeOverride(
            name = "coordinates.longitude",
            column = @Column(
                name = "origin_lon", precision = 10, scale = 7
            )
        )
    })
    private LocatedAddress origin;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(
            name = "city",
            column = @Column(name = "destination_city", length = 100)
        ),
        @AttributeOverride(
            name = "coordinates.latitude",
            column = @Column(
                name = "destination_lat", precision = 10, scale = 7
            )
        ),
        @AttributeOverride(
            name = "coordinates.longitude",
            column = @Column(
                name = "destination_lon", precision = 10, scale = 7
            )
        )
    })
    private LocatedAddress destination;
}
~~~

Đường dẫn `coordinates.latitude` có hai phần:

~~~text
DeliveryRoute.origin (Embedded LocatedAddress)
    |
    +-- city
    |
    +-- coordinates (Embedded GeoPoint)
            |
            +-- latitude  -> origin_lat
            +-- longitude -> origin_lon

DeliveryRoute.destination (Embedded LocatedAddress)
    |
    +-- city
    |
    +-- coordinates (Embedded GeoPoint)
            |
            +-- latitude  -> destination_lat
            +-- longitude -> destination_lon
~~~

**Quy tắc:** Khi `@AttributeOverrides` đặt trên field `origin`, `name` là đường dẫn **tương đối với kiểu của field đó**. Dùng dấu chấm nối tên các thuộc tính nhúng ở các mức. Viết `name = "origin.coordinates.latitude"` ngay tại field `origin` thường sai vì lặp tiền tố; còn nếu khai báo ở cấp entity, đường dẫn đầy đủ có thể cần tiền tố `origin.`.

### DDL của ví dụ lồng nhau

~~~sql
CREATE TABLE delivery_route (
    id BIGINT PRIMARY KEY,
    origin_city VARCHAR(100),
    origin_lat NUMERIC(10, 7),
    origin_lon NUMERIC(10, 7),
    destination_city VARCHAR(100),
    destination_lat NUMERIC(10, 7),
    destination_lon NUMERIC(10, 7)
);
~~~

Nhờ override, cả `GeoPoint` lẫn `LocatedAddress` có thể tái sử dụng mà không tạo các class Java chỉ để đổi tên cột ở từng mức.

## 8. Khi embeddable chứa association: cần `@AssociationOverride`

`@AttributeOverride` được dùng để ghi đè **mapping của thuộc tính cơ bản (basic attribute)**, chẳng hạn `String`, `BigDecimal` hoặc các thuộc tính của embeddable được triển khai thành cột thông thường. Nếu embeddable chứa `@ManyToOne` hoặc `@OneToOne`, việc đổi tên **join column** cần **`@AssociationOverride`** hoặc `@AssociationOverrides`.

Ví dụ một địa chỉ tham chiếu entity `Country`:

~~~java
@Entity
public class Country {
    @Id
    private Long id;

    @Column(nullable = false)
    private String name;

    protected Country() {}
}

@Embeddable
public class AddressWithCountry {
    @Column(name = "street", length = 200)
    private String street;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "country_id")
    private Country country;

    protected AddressWithCountry() {}
}
~~~

Trong một entity có `origin` và `destination`:

~~~java
@Entity
@Table(name = "parcel")
public class Parcel {
    @Id
    private Long id;

    @Embedded
    @AttributeOverride(
        name = "street",
        column = @Column(name = "origin_street")
    )
    @AssociationOverride(
        name = "country",
        joinColumns = @JoinColumn(name = "origin_country_id")
    )
    private AddressWithCountry origin;

    @Embedded
    @AttributeOverride(
        name = "street",
        column = @Column(name = "destination_street")
    )
    @AssociationOverride(
        name = "country",
        joinColumns = @JoinColumn(name = "destination_country_id")
    )
    private AddressWithCountry destination;
}
~~~

Kết quả:

| Thuộc tính | Cơ chế override | Cột |
|---|---|---|
| `origin.street` | `@AttributeOverride` | `origin_street` |
| `origin.country` | `@AssociationOverride` | `origin_country_id` |
| `destination.street` | `@AttributeOverride` | `destination_street` |
| `destination.country` | `@AssociationOverride` | `destination_country_id` |

Một lỗi thường gặp là viết `@AttributeOverride(name = "country", column = @Column(...))` rồi chờ Hibernate đổi FK. `country` là association chứ không phải basic field; dùng sai loại annotation có thể bị từ chối khi khởi tạo mapping hoặc không giải quyết được join column.

Nếu association nằm sâu hơn, `name` của `@AssociationOverride` cũng có thể sử dụng đường dẫn thành phần được nhúng, ví dụ `contact.country` tương đối với embeddable chứa `contact`. Cần phân biệt **đường dẫn thuộc tính Java** và **tên foreign key trong database** ở mọi mức.

## 9. `@Column` gốc và `@Column` trong override: cái nào có hiệu lực?

Ví dụ kiểu giá trị định nghĩa:

~~~java
@Embeddable
public class CodeValue {
    @Column(name = "code", nullable = false, length = 16)
    private String code;
}
~~~

Một nơi nhúng ghi đè:

~~~java
@Embedded
@AttributeOverride(
    name = "code",
    column = @Column(name = "external_code", length = 32)
)
private CodeValue externalCode;
~~~

`@AttributeOverride` cung cấp metadata `@Column` mới cho vị trí này. Khi cần bảo đảm các đặc tính quan trọng như `nullable`, `length`, `precision`, `scale`, `insertable` và `updatable`, nên khai báo **tường minh** trong override thay vì giả định Hibernate sẽ tự lấy mọi giá trị từ annotation gốc. Chẳng hạn:

~~~java
@Embedded
@AttributeOverride(
    name = "code",
    column = @Column(
        name = "external_code",
        nullable = false,
        length = 32,
        insertable = true,
        updatable = true
    )
)
private CodeValue externalCode;
~~~

Điều quan trọng là metadata cuối phải khớp schema vật lý:

~~~sql
external_code VARCHAR(32) NOT NULL
~~~

### Các thuộc tính đáng chú ý của `@Column`

| Thuộc tính | Tác động trong mapping |
|---|---|
| `name` | Tên cột được ánh xạ tại vị trí nhúng. |
| `nullable` | Mô tả khả năng cột chứa `NULL`; schema thật phải có constraint tương ứng nếu cần. |
| `length` | Chiều dài cột string khi tạo schema và làm metadata mapping. |
| `precision`, `scale` | Đặc tính cột số thập phân, quan trọng với `BigDecimal`. |
| `insertable` | Hibernate có đưa cột này vào `INSERT` từ mapping hay không. |
| `updatable` | Hibernate có đưa cột này vào `UPDATE` từ mapping hay không. |
| `table` | Bảng chứa cột, quan trọng nếu entity dùng bảng phụ. |

Việc đặt `insertable = false, updatable = false` để “né” lỗi trùng cột **không phải là cách giải quyết đúng** cho hai địa chỉ độc lập. Hai thuộc tính vẫn có thể trỏ cùng cột, chỉ một nơi được ghi, và kết quả đọc dễ gây hiểu nhầm. Nếu nghiệp vụ yêu cầu hai dữ liệu độc lập, hãy ánh xạ vào hai bộ cột độc lập.

## 10. Field access, property access và tên thuộc tính

JPA hỗ trợ hai cách truy cập persistent state:

- **Field access:** annotation mapping được đặt trên field (thường nhận biết qua vị trí `@Id`); `name` trong override trỏ đến tên field.
- **Property access:** annotation mapping được đặt trên getter JavaBeans; `name` trong override trỏ đến tên property tương ứng với getter.

Ví dụ field access:

~~~java
@Embeddable
public class PersonName {
    @Column(name = "first_name")
    private String givenName;

    @Column(name = "last_name")
    private String familyName;
}

@Embedded
@AttributeOverrides({
    @AttributeOverride(
        name = "givenName",
        column = @Column(name = "primary_given_name")
    ),
    @AttributeOverride(
        name = "familyName",
        column = @Column(name = "primary_family_name")
    )
})
private PersonName primaryName;
~~~

Phải dùng `givenName`/`familyName`, không dùng `first_name`/`last_name`.

Ví dụ property access:

~~~java
@Embeddable
@Access(AccessType.PROPERTY)
public class ContactName {
    private String first;

    protected ContactName() {}

    @Column(name = "first_name")
    public String getFirstName() {
        return first;
    }

    public void setFirstName(String firstName) {
        this.first = firstName;
    }
}
~~~

Property persistent ở đây là `firstName` từ `getFirstName()`, không phải field nội bộ `first`. Khi override:

~~~java
@Embedded
@AttributeOverride(
    name = "firstName",
    column = @Column(name = "contact_first_name")
)
private ContactName contactName;
~~~

Trong hệ thống có kế thừa access strategy hoặc `@Access` đặt riêng, việc nhìn vào tên field mà không xét access type có thể khiến override trỏ sai thuộc tính. Nên thống nhất một phong cách annotation trong entity/embeddable hoặc khai báo `@Access` có chủ đích.

## 11. Value object và tính độc lập của hai vị trí nhúng

Hai địa chỉ dùng cùng kiểu `PostalAddress` nhưng đại diện **hai giá trị khác nhau**:

~~~java
PostalAddress billing = new PostalAddress(
    "12 Nguyen Hue", "HCM", "700000"
);
PostalAddress shipping = new PostalAddress(
    "45 Le Loi", "Da Nang", "550000"
);

DeliveryOrder order = new DeliveryOrder(billing, shipping);
~~~

`@AttributeOverrides` bảo đảm dữ liệu của mỗi lần nhúng có cột riêng. Tuy nhiên, nếu object value type **mutable** và ứng dụng truyền cùng một instance cho cả hai field, việc sửa instance đó bằng setter có thể ảnh hưởng cả hai vị trí trong bộ nhớ:

~~~java
PostalAddress shared = new PostalAddress(
    "12 Nguyen Hue", "HCM", "700000"
);

DeliveryOrder order = new DeliveryOrder(shared, shared);
// billingAddress và shippingAddress trỏ cùng instance shared.
~~~

Đây là vấn đề **aliasing ở Java**, khác với vấn đề tên cột SQL. Một thực hành tốt là xem embeddable như **value object**, tránh thay đổi trực tiếp từng field từ bên ngoài, và thay bằng một instance mới khi muốn sửa một vai trò:

~~~java
order.changeShippingAddress(
    new PostalAddress("99 Tran Phu", "Hue", "530000")
);
~~~

Cách này làm rõ ý nghĩa “đổi địa chỉ giao hàng nhưng giữ nguyên địa chỉ thanh toán”.

### `equals()` và `hashCode()` cho embeddable

Vì embeddable là kiểu giá trị, `equals()` và `hashCode()` theo các thành phần giá trị có thể hữu ích cho business logic và collections. Nếu dùng embeddable làm khóa Map hoặc thuộc một tập hợp dựa trên hash, cần đặc biệt chú ý tính ổn định của giá trị. Hibernate có thể sử dụng so sánh thành phần/dirty checking theo mapping; không nên dựa vào identity Java (`==`) như tiêu chuẩn duy nhất để xác định hai địa chỉ bằng nhau.

Tính nhất quán của value object không thay đổi quy tắc cơ bản: cùng lớp `PostalAddress` có thể được nhúng nhiều lần, còn ánh xạ cột được định nghĩa riêng cho từng vai trò.

## 12. `@ElementCollection`: cùng embeddable trong bảng collection

`@AttributeOverride` không chỉ dùng khi có hai `@Embedded` trên một entity. Một entity có thể lưu **danh sách các giá trị embeddable** bằng `@ElementCollection` trong bảng collection. Khi đó, có thể ghi đè tên cột của từng giá trị trong bảng collection.

Ví dụ đơn hàng có nhiều địa chỉ liên hệ phụ:

~~~java
@Entity
@Table(name = "delivery_order")
public class DeliveryOrderWithContacts {
    @Id
    private Long id;

    @ElementCollection
    @CollectionTable(
        name = "order_contact_address",
        joinColumns = @JoinColumn(name = "order_id")
    )
    @OrderColumn(name = "position")
    @AttributeOverrides({
        @AttributeOverride(
            name = "street",
            column = @Column(
                name = "contact_street", nullable = false, length = 200
            )
        ),
        @AttributeOverride(
            name = "city",
            column = @Column(
                name = "contact_city", nullable = false, length = 100
            )
        ),
        @AttributeOverride(
            name = "postalCode",
            column = @Column(name = "contact_postal_code", length = 20)
        )
    })
    private List<PostalAddress> contacts = new ArrayList<>();
}
~~~

DDL tương ứng có thể là:

~~~sql
CREATE TABLE order_contact_address (
    order_id             BIGINT NOT NULL,
    position             INTEGER NOT NULL,
    contact_street       VARCHAR(200) NOT NULL,
    contact_city         VARCHAR(100) NOT NULL,
    contact_postal_code  VARCHAR(20),
    PRIMARY KEY (order_id, position),
    FOREIGN KEY (order_id) REFERENCES delivery_order(id)
);
~~~

Đây là mô hình **một entity có nhiều phần tử giá trị**. `@ElementCollection` khác `@Embedded`:

| Đặc điểm | `@Embedded` | `@ElementCollection` |
|---|---|---|
| Số giá trị ở một field | Một object embeddable | Nhiều phần tử (collection). |
| Nơi lưu mặc định | Cột của bảng entity sở hữu | Bảng collection riêng. |
| Identity độc lập cho value object | Không | Không; phần tử vẫn là giá trị, được quản lý qua owner. |
| Cách override | `@AttributeOverrides` trên field nhúng | `@AttributeOverrides` trên field collection embeddables. |
| Quan hệ DB | Không tạo FK riêng chỉ vì nhúng | Bảng collection có FK về owner. |

Tính đúng đắn khi xóa/thêm phần tử và chi phí SQL phụ thuộc collection type, ordering và Hibernate mapping. Không nên hiểu `@ElementCollection` là bảng phụ `@SecondaryTable`; số hàng collection có thể nhiều, còn bảng phụ của entity thường dùng shared primary key.

## 13. Map với giá trị embeddable: tiền tố `value.` và `key.`

JPA có quy tắc đường dẫn riêng khi một embeddable được dùng trong `Map`: muốn ghi đè cột của **map value**, dùng tiền tố `value.`; đối với **map key** là embeddable, dùng tiền tố `key.`.

Ví dụ đơn hàng lưu các địa chỉ theo vai trò `HOME`, `OFFICE`, `ALTERNATE`:

~~~java
@ElementCollection
@CollectionTable(
    name = "order_named_address",
    joinColumns = @JoinColumn(name = "order_id")
)
@MapKeyColumn(name = "address_role")
@AttributeOverrides({
    @AttributeOverride(
        name = "value.street",
        column = @Column(name = "address_street", length = 200)
    ),
    @AttributeOverride(
        name = "value.city",
        column = @Column(name = "address_city", length = 100)
    ),
    @AttributeOverride(
        name = "value.postalCode",
        column = @Column(name = "address_postal_code", length = 20)
    )
})
private Map<String, PostalAddress> namedAddresses = new HashMap<>();
~~~

Ở đây:

~~~text
namedAddresses key (String)   -> address_role
namedAddresses value.street   -> address_street
namedAddresses value.city     -> address_city
namedAddresses value.postalCode -> address_postal_code
~~~

Với key kiểu `String`, `@MapKeyColumn` mô tả cột key. Nếu key bản thân là `@Embeddable`, `@AttributeOverride(name = "key.someField", ...)` dùng để xác định cột cho field của key theo quy tắc tương ứng.

Phân biệt:

- `name = "street"`: đường dẫn trong embeddable dùng ở field `@Embedded` trực tiếp hoặc collection không phải Map.
- `name = "coordinates.latitude"`: thuộc tính lồng trong embeddable.
- `name = "value.street"`: thuộc tính của embeddable ở **Map value**.
- `name = "key.code"`: thuộc tính của embeddable ở **Map key**.

Quy tắc tiền tố này thuộc cách JPA biểu diễn map-valued element collections; không nên áp dụng `value.` vô điều kiện cho mọi `@Embedded` thông thường.

## 14. Khi các cột nằm ở bảng phụ `@SecondaryTable`

Ghi đè tên cột và chọn **bảng lưu cột** là hai quyết định khác nhau. Nếu entity dùng bảng phụ, `@Column(table = "...")` trong `@AttributeOverride` có thể chỉ rõ các field nhúng thuộc bảng nào.

Ví dụ:

~~~java
@Entity
@Table(name = "customer_account")
@SecondaryTable(
    name = "customer_contact",
    pkJoinColumns = @PrimaryKeyJoinColumn(
        name = "account_id",
        referencedColumnName = "id"
    )
)
public class CustomerAccountWithAddress {
    @Id
    private Long id;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(
            name = "street",
            column = @Column(
                name = "mailing_street",
                table = "customer_contact"
            )
        ),
        @AttributeOverride(
            name = "city",
            column = @Column(
                name = "mailing_city",
                table = "customer_contact"
            )
        ),
        @AttributeOverride(
            name = "postalCode",
            column = @Column(
                name = "mailing_postal_code",
                table = "customer_contact"
            )
        )
    })
    private PostalAddress mailingAddress;
}
~~~

Sơ đồ:

~~~text
customer_account                 customer_contact
+-------------------+            +-----------------------+
| id (PK)           |<-----------| account_id (PK, FK)  |
+-------------------+            | mailing_street        |
                                 | mailing_city          |
                                 | mailing_postal_code   |
                                 +-----------------------+
~~~

`@AttributeOverride` ở đây vừa đặt tên cột, vừa chỉ định bảng phụ thông qua `@Column(table = "customer_contact")`. Nếu bỏ `table`, ORM có thể mặc định tìm các cột ở bảng chính và không khớp schema. Đây vẫn là **một entity `CustomerAccountWithAddress`**; `PostalAddress` không biến thành entity `@OneToOne`.

Khi yêu cầu nhiều địa chỉ ở cùng bảng phụ, mỗi địa chỉ cần bộ cột riêng trong bảng phụ, hệt như trường hợp hai địa chỉ ở bảng chính.

## 15. Hibernate naming strategy có làm `@AttributeOverride` trở nên thừa?

Hibernate có thể sử dụng `ImplicitNamingStrategy` để suy ra logical column names khi ứng dụng không chỉ định tên, và `PhysicalNamingStrategy` để biến logical names thành tên vật lý phù hợp quy ước schema. Một số cấu hình naming strategy tạo tên cột có thêm đường dẫn embeddable, ví dụ:

~~~text
billingAddress.street  -> billing_address_street
shippingAddress.street -> shipping_address_street
~~~

Nhờ đó, việc nhúng cùng kiểu có thể không gây xung đột trong cấu hình cụ thể. Tuy nhiên:

1. **Không phải mọi Hibernate configuration đều dùng implicit path-based naming.**
2. Khi `@Column(name = "street")` đã khai báo trong embeddable, việc xử lý tên explicit và implicit không giống nhau.
3. Production schema có thể dùng tên cột lịch sử khác naming convention, chẳng hạn `bill_street_1` hoặc `ship_addr_line`.
4. Thay `PhysicalNamingStrategy`, nâng Hibernate hoặc chuyển framework có thể đổi cách suy ra tên vật lý nếu application phụ thuộc vào implicit defaults.

`@AttributeOverride` là cách JPA **tường minh và gắn với từng vị trí nhúng**, hữu ích khi schema không thể suy ra an toàn chỉ từ tên field. Naming strategy phù hợp cho quy ước toàn ứng dụng; override phù hợp cho ngoại lệ hoặc khi cần mô tả chính xác mapping.

### Tên logical và tên vật lý

Trong Hibernate, explicit `@Column(name = "billingStreet")` có thể tiếp tục chịu ảnh hưởng của physical naming strategy để thành tên DB `billing_street`. Vì vậy khi đối chiếu schema, phải xét cả annotation và Hibernate naming configuration. Đừng kết luận tất cả tên trong annotation sẽ được gửi nguyên xi tới database nếu application đang dùng physical naming strategy biến đổi tên.

Nếu tên bảng/cột chứa chữ hoa hoặc trùng từ khóa SQL, cần hiểu quy tắc identifier quoting của DB/dialect. Tốt nhất dùng naming convention đơn giản và thống nhất; tránh dựa vào cách quote khác nhau giữa DBMS.

## 16. Cột bị trùng: nguyên nhân và cách đọc lỗi mapping

Ví dụ sai:

~~~java
@Entity
class WrongDeliveryOrder {
    @Id
    private Long id;

    @Embedded
    private PostalAddress billingAddress;

    @Embedded
    private PostalAddress shippingAddress;
}
~~~

Tùy cấu hình, Hibernate có thể ném exception về việc một column được ánh xạ nhiều lần trong cùng entity, chẳng hạn thông điệp liên quan `Repeated column in mapping for entity`, hoặc tên cột không khớp schema khi SQL thực thi.

Nguyên nhân thường có thể được truy theo chuỗi:

~~~text
Entity: WrongDeliveryOrder
     |
     +-- Embedded billingAddress
     |       +-- PostalAddress.street -> street
     |       +-- PostalAddress.city   -> city
     |
     +-- Embedded shippingAddress
             +-- PostalAddress.street -> street  (trùng)
             +-- PostalAddress.city   -> city    (trùng)
~~~

Cách xử lý:

1. Liệt kê từng đường dẫn Java của các embeddable được nhúng.
2. Xác định tên cột DB cần có cho **mỗi** đường dẫn, bao gồm schema/table nếu có bảng phụ.
3. Thêm `@AttributeOverrides` theo từng vị trí, sử dụng tên **thuộc tính Java** trong `name`.
4. Đối chiếu tên vật lý cuối sau naming strategy với schema migration.
5. Kiểm tra các cột cùng kiểu có đặc tính `nullable`/`length`/`precision` phù hợp.

Đừng dùng `insertable = false, updatable = false` như cách sửa mặc định. Khi hai giá trị độc lập cùng trỏ vào một cột, bỏ ghi ở một phía chỉ che triệu chứng, không lưu được hai địa chỉ khác nhau.

### Nếu lỗi là “Unknown column”

Một lỗi truy vấn nói không tìm thấy `billing_street` có thể xuất phát từ:

- Annotation override đúng nhưng migration chưa tạo cột.
- Physical naming strategy làm tên cột thay đổi.
- `@Column(table = ...)` trỏ sang sai bảng.
- Tên `@SecondaryTable`/schema không khớp hoặc database chưa được migrate.
- Entity dùng access strategy khác dự kiến nên override không áp dụng đúng thuộc tính.

Không nên chỉ thêm cột bằng tay lên database đang chạy mà không cập nhật migration; cần giữ schema của các môi trường nhất quán.

## 17. Ghi đè tên cột không thay đổi vòng đời của value object

Một `@Embeddable` không có identifier độc lập:

~~~java
PostalAddress address = new PostalAddress(
    "12 Nguyen Hue", "HCM", "700000"
);

DeliveryOrder order = new DeliveryOrder(address, address);
entityManager.persist(order);
~~~

Hibernate lưu các thành phần của `PostalAddress` thông qua cột thuộc `DeliveryOrder`. Không có lời gọi:

~~~java
entityManager.persist(address); // Sai về mô hình: address không phải entity.
~~~

Các thao tác vòng đời diễn ra ở entity sở hữu:

| Thao tác | Hệ quả với embeddable |
|---|---|
| `persist(order)` | Lưu các cột của những địa chỉ vào hàng `delivery_order`. |
| Sửa field/đổi value object của managed `order` | Hibernate dirty checking và đồng bộ cột liên quan khi flush. |
| `remove(order)` | Xóa hàng entity; các cột địa chỉ cũng biến mất cùng hàng đó. |
| `detach(order)` | Entity không còn được theo dõi; sửa embeddable bên trong không tự cập nhật DB. |
| `merge(detachedOrder)` | Hibernate sao chép state của entity/embedded values vào managed instance thích hợp theo mapping. |

Không tồn tại “cascade persist” riêng từ entity đến embeddable như association giữa hai entity. Các cột của embeddable là một phần của state entity sở hữu.

### Null và embeddable

Nếu `billingAddress == null`, Hibernate xử lý các cột embedded theo khả năng null và mapping; với cột `NOT NULL` như ví dụ đầy đủ, việc cố lưu địa chỉ null sẽ gây lỗi validation/constraint ở thời điểm phù hợp.

Khi **tất cả cột của một embeddable đều SQL NULL**, Hibernate có thể khôi phục field embedded thành `null` theo cơ chế mapping/provider; điều này có thể khác giữa phiên bản/cấu hình. Không nên dựa vào việc luôn có object rỗng sau khi load.

Nếu muốn địa chỉ là bắt buộc, kiểm soát invariant ở constructor/domain methods, Bean Validation nếu dùng, và constraint tại database. Chỉ ghi `@Embedded` không tự đảm bảo toàn bộ thành phần đều `NOT NULL`.

## 18. Có cần `@AttributeOverrides` cho từng thuộc tính không?

Không nhất thiết phải ghi đè **mọi** thuộc tính; chỉ cần những thuộc tính cần mapping khác với mặc định. Nhưng với hai lần nhúng cùng `PostalAddress` trong một bảng và cùng các tên mặc định, thường phải đảm bảo **mọi cột đang trùng** được tách ra.

Ví dụ:

~~~java
@Embedded
@AttributeOverride(
    name = "street",
    column = @Column(name = "shipping_street")
)
private PostalAddress shippingAddress;
~~~

Nếu không có naming strategy xử lý, `shippingAddress.city` và `billingAddress.city` vẫn có thể cùng dùng cột `city`. Ghi đè chỉ `street` chưa làm ánh xạ toàn bộ địa chỉ độc lập.

Một cách lập bảng để tránh thiếu:

| Thành phần của embeddable | Billing | Shipping |
|---|---|---|
| `street` | `billing_street` | `shipping_street` |
| `city` | `billing_city` | `shipping_city` |
| `postalCode` | `billing_postal_code` | `shipping_postal_code` |

Khi thêm field mới vào `PostalAddress`, chẳng hạn `countryCode`, cần xét lại tất cả nơi nhúng cùng kiểu và cập nhật mapping/migration nếu tên cột mặc định không phù hợp. Đây là một chi phí bảo trì hợp lý để đổi lại một kiểu giá trị dùng chung.

## 19. Tương tác với `@Convert` và kiểu dữ liệu custom

Đôi khi một giá trị cần conversion trước khi Hibernate bind vào JDBC, ví dụ enum/currency code hoặc kiểu domain chuyên biệt. `@Convert`/`AttributeConverter` giải quyết **chuyển đổi giữa kiểu Java và kiểu DB**, còn `@AttributeOverride` giải quyết **mapping cột**.

Ví dụ `CurrencyCode` có thể được chuyển thành chuỗi ISO; hai field cùng dùng converter nhưng ở hai cột khác nhau:

~~~java
@Converter
public class CurrencyCodeConverter
        implements AttributeConverter<CurrencyCode, String> {
    @Override
    public String convertToDatabaseColumn(CurrencyCode attribute) {
        return attribute == null ? null : attribute.value();
    }

    @Override
    public CurrencyCode convertToEntityAttribute(String dbData) {
        return dbData == null ? null : new CurrencyCode(dbData);
    }
}
~~~

Giả sử:

~~~java
@Embeddable
public class MonetaryAmount {
    private BigDecimal amount;

    @Convert(converter = CurrencyCodeConverter.class)
    private CurrencyCode currency;
}
~~~

Hai lần nhúng `MonetaryAmount` vẫn cần tên cột tách biệt như `unit_price_currency` và `discount_currency`. Converter chỉ quy định cách chuyển đổi **giá trị của cột**, không tự phân biệt cột đang thuộc lần nhúng nào.

Các loại mapping tùy biến như JSON, composite user type hoặc schema generated columns có thể có cách ánh xạ riêng; không nên mặc định mọi kiểu đặc biệt đều chỉ cần một `@AttributeOverride` để hoạt động. Ví dụ trên minh họa hai trách nhiệm độc lập của mapping.

## 20. Migration schema khi thêm lần nhúng thứ hai

Giả sử bảng `delivery_order` trước đây chỉ có địa chỉ giao hàng:

~~~sql
CREATE TABLE delivery_order (
    id BIGINT PRIMARY KEY,
    version BIGINT NOT NULL,
    street VARCHAR(200) NOT NULL,
    city VARCHAR(100) NOT NULL,
    postal_code VARCHAR(20)
);
~~~

Phiên bản mới muốn có `billingAddress` và `shippingAddress` với tên rõ ràng. Thay Java mapping mà không migration sẽ khiến SQL nhắm tới cột chưa tồn tại. Một quy trình an toàn thường gồm:

1. **Xác định mapping cũ:** `street`/`city`/`postal_code` có ý nghĩa shipping, billing hay địa chỉ chung? Không tự suy luận nếu nghiệp vụ chưa rõ.
2. **Thêm các cột mới** bằng migration theo tên mong muốn, ban đầu cân nhắc cho phép null để có thời gian backfill.
3. **Backfill dữ liệu** từ các cột cũ sang `shipping_*`, và sang `billing_*` theo quy tắc nghiệp vụ rõ ràng.
4. **Đối chiếu dữ liệu**: đếm số hàng, kiểm tra giá trị null, chiều dài dữ liệu, các bản ghi thiếu địa chỉ.
5. **Triển khai mapping mới** theo chiến lược phù hợp với cách deploy (đặc biệt khi code cũ và mới cùng chạy).
6. **Thêm constraint `NOT NULL`** khi dữ liệu đã đủ và nghiệp vụ yêu cầu.
7. **Gỡ cột cũ** sau khi các phiên bản ứng dụng/job không còn đọc hoặc ghi vào đó.

Ví dụ PostgreSQL cho giai đoạn thêm cột:

~~~sql
ALTER TABLE delivery_order
    ADD COLUMN shipping_street VARCHAR(200),
    ADD COLUMN shipping_city VARCHAR(100),
    ADD COLUMN shipping_postal_code VARCHAR(20),
    ADD COLUMN billing_street VARCHAR(200),
    ADD COLUMN billing_city VARCHAR(100),
    ADD COLUMN billing_postal_code VARCHAR(20);

UPDATE delivery_order
SET
    shipping_street = street,
    shipping_city = city,
    shipping_postal_code = postal_code;
~~~

Cách backfill billing phụ thuộc business requirement: có thể sao chép shipping khi lịch sử không có billing riêng, nhưng đó là **quyết định nghiệp vụ cần được xác nhận**, không phải điều Hibernate tự định nghĩa. Nếu ứng dụng đang ghi đồng thời vào cột cũ, cần kế hoạch đồng bộ/dual-write hoặc lịch deployment để tránh dữ liệu bị lệch trong thời gian chuyển đổi.

### Mapping là contract với schema

JPA annotation mô tả vị trí lưu dữ liệu. Database migration thực sự tạo và chuyển dữ liệu. Hibernate `hbm2ddl.auto=update` không thay thế migration production có kiểm soát, đặc biệt khi cần backfill, rename hoặc rollout qua nhiều phiên bản ứng dụng.

## 21. Truy vấn theo thuộc tính của hai lần nhúng

JPQL/HQL làm việc với **đường dẫn Java**, không viết trực tiếp tên cột đã override:

~~~java
List<DeliveryOrder> orders = entityManager.createQuery(
    """
    select o
    from DeliveryOrder o
    where o.billingAddress.city = :billingCity
      and o.shippingAddress.city = :shippingCity
    """,
    DeliveryOrder.class
)
.setParameter("billingCity", "Ho Chi Minh City")
.setParameter("shippingCity", "Da Nang")
.getResultList();
~~~

Hibernate dựa vào metadata để chuyển:

~~~text
o.billingAddress.city  -> billing_city
o.shippingAddress.city -> shipping_city
~~~

SQL tương ứng về ý nghĩa:

~~~sql
SELECT ...
FROM delivery_order o
WHERE o.billing_city = ?
  AND o.shipping_city = ?;
~~~

Vì thế, thay tên cột vật lý bằng migration và `@AttributeOverrides` có thể giữ nguyên phần lớn query JPQL đang viết theo domain properties, miễn các tên thuộc tính Java và semantics không đổi.

### Projection để lấy từng nhóm cột

~~~java
List<String> shippingCities = entityManager.createQuery(
    "select o.shippingAddress.city from DeliveryOrder o",
    String.class
).getResultList();
~~~

Hibernate có thể chọn chỉ những cột cần cho projection. Đây là một lợi ích của việc giữ query ở mức đường dẫn thuộc tính, không gắn code ứng dụng với tên `shipping_city` trong native SQL.

## 22. Kiểm chứng ánh xạ bằng SQL và metadata

Để hiểu tên cột thật sự Hibernate dùng, bật SQL logging trong môi trường phát triển:

~~~properties
# Ví dụ Spring Boot + Hibernate 6:
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Trong các phiên bản Hibernate khác, logger bind parameters có thể dùng tên khác. Bind trace có thể lộ dữ liệu cá nhân/địa chỉ, do đó không nên bật đại trà ở production.

Sau khi persist:

~~~java
DeliveryOrder order = new DeliveryOrder(
    new PostalAddress("A Street", "Hanoi", "100000"),
    new PostalAddress("B Street", "Hue", "530000")
);
entityManager.persist(order);
entityManager.flush();
~~~

Quan sát tên cột của `INSERT` và bind values, đồng thời truy vấn DB:

~~~sql
SELECT
    billing_street,
    billing_city,
    billing_postal_code,
    shipping_street,
    shipping_city,
    shipping_postal_code
FROM delivery_order
WHERE id = ?;
~~~

Giá trị kỳ vọng:

| Cột | Giá trị |
|---|---|
| `billing_street` | `A Street` |
| `billing_city` | `Hanoi` |
| `billing_postal_code` | `100000` |
| `shipping_street` | `B Street` |
| `shipping_city` | `Hue` |
| `shipping_postal_code` | `530000` |

Nếu cả hai cột street cùng nhận một giá trị không mong muốn, hãy kiểm tra trước hết **hai object Java có trỏ cùng instance và bị sửa qua reference chung không**, sau đó mới đến mapping. Nếu SQL chỉ có một cột street, kiểm tra `@AttributeOverrides` và naming strategy.

### Phân biệt lỗi boot-time và lỗi runtime

| Thời điểm | Dấu hiệu | Hướng xác định |
|---|---|---|
| Khởi tạo `SessionFactory` | MappingException hoặc duplicate column | Xem các lần `@Embedded` cùng kiểu và tên cột cuối. |
| Khởi tạo/validate schema | Missing column/type mismatch | Đối chiếu migration với tên cột sau naming strategy. |
| `INSERT`/flush | Constraint violation, column not found | Xem nullable/length/schema thực tế và bind values. |
| `SELECT`/query | Không thấy cột, dữ liệu hai địa chỉ sai | Kiểm tra đường dẫn Java, annotations, data migration và aliasing. |
| Update managed entity | Không cập nhật cột dự định | Xem access type, `insertable/updatable`, dirty checking và transaction. |

Không cần thay đổi field Java chỉ để tên SQL giống field. Vai trò của `@AttributeOverride` là tách hai lớp tên này một cách có chủ đích.

## 23. Thực hành: từ lỗi trùng cột đến mapping hoàn chỉnh

### Bài A — Thử thiếu override

Tạo một entity có:

~~~java
@Embedded
private PostalAddress pickupAddress;

@Embedded
private PostalAddress dropoffAddress;
~~~

Không khai báo override, chạy chương trình khởi tạo Hibernate với schema có `pickup_street`, `dropoff_street`. Quan sát Hibernate muốn map các cột nào hoặc báo lỗi gì tùy naming strategy.

### Bài B — Bổ sung toàn bộ override

Thiết kế các cột:

~~~text
pickup_street, pickup_city, pickup_postal_code
dropoff_street, dropoff_city, dropoff_postal_code
~~~

Đặt `@AttributeOverrides` tại từng field và bảo đảm `name` dùng đúng `street`, `city` và `postalCode`. Persist một entity có pickup và dropoff khác nhau, rồi load lại trong persistence context mới.

### Bài C — Đổi chỉ địa chỉ giao hàng

Trong transaction mới, load entity và gọi:

~~~java
order.changeShippingAddress(
    new PostalAddress("New Street", "Can Tho", "900000")
);
~~~

Sau flush/commit, đọc lại `billing_*` và `shipping_*`. Xác nhận địa chỉ thanh toán không đổi. SQL `UPDATE` có thể chứa nhiều cột, nhưng **giá trị cuối cùng** ở hai nhóm cột phải đúng.

### Bài D — Embeddable lồng nhau

Với `LocatedAddress` có `GeoPoint`, thêm hai field `origin` và `destination`; thử cố tình viết `name = "latitude"` thay vì `name = "coordinates.latitude"` và quan sát mapping/SQL. Sau đó dùng đường dẫn đúng và tạo các cột `origin_lat`, `destination_lat`.

### Bài E — Map các địa chỉ theo vai trò

Dùng `Map<String, PostalAddress>` với `@ElementCollection`, `@MapKeyColumn` và `@AttributeOverride(name = "value.city", ...)`. Thêm hai vai trò vào map, rồi kiểm tra các hàng trong bảng collection.

### Bài F — Rà soát schema cũ

Cho bảng cũ chỉ có `street`, `city`, `postal_code`. Vẽ bản đồ mapping và migration nếu ứng dụng cần thêm địa chỉ thứ hai. Nêu rõ nguồn dữ liệu để backfill địa chỉ mới; không mặc định sao chép theo cảm tính.

## 24. Checklist tư duy khi cùng một embeddable xuất hiện nhiều lần

Mỗi khi thấy hai field cùng kiểu `@Embeddable` trong một entity, hãy trả lời các câu hỏi:

1. **Vai trò domain khác nhau ở đâu?** Ví dụ billing/shipping, origin/destination, unitPrice/discount.
2. **Mỗi vai trò cần những cột vật lý nào?** Lập bảng từ đường dẫn Java đến cột SQL.
3. **Annotation đặt ở đâu?** Nếu trên từng `@Embedded`, `name` tương đối với embeddable; nếu trên entity, dùng đường dẫn đầy đủ thích hợp.
4. **Có embeddable lồng nhau không?** Dùng dấu chấm như `coordinates.latitude`.
5. **Có association trong embeddable không?** Dùng `@AssociationOverride` cho join columns thay vì `@AttributeOverride`.
6. **Có collection hoặc Map không?** Phân biệt `@ElementCollection`, `@MapKeyColumn` và các tiền tố `key.`/`value.`.
7. **Cột nằm ở bảng chính hay bảng phụ?** Đặt `@Column(table = "...")` khi mapping yêu cầu.
8. **Các ràng buộc cột có được mô tả đúng không?** Nullable, length, precision, scale, update/insert behavior phải khớp DDL.
9. **Naming strategy và migration có thống nhất không?** Kiểm tra tên cột cuối mà Hibernate thực sự gửi SQL.
10. **Có shared mutable references gây lẫn giá trị không?** Hai field có cột riêng nhưng cùng trỏ một object vẫn có thể gây bug trong Java.

Kỹ thuật này giúp **giữ một value object nhất quán trong domain model** đồng thời lưu mỗi lần xuất hiện của nó vào **những cột độc lập và có tên đúng với schema**. Khi hiểu rõ đường dẫn thuộc tính của `@AttributeOverride` và sự khác nhau giữa tên Java với tên cột SQL, bạn có thể tái sử dụng embeddable an toàn trong nhiều vai trò, nhiều mức lồng nhau và nhiều mô hình collection mà không phải nhân bản các lớp giá trị chỉ để đổi tên cột.
