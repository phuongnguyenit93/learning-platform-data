# Ánh xạ cấu trúc nhúng lồng nhau

> **Chủ đề:** Data Persistence – Relational Access, ORM, JPA  
> **Nhóm kiến thức:** Kiểu giá trị

Trong ứng dụng Java, một đối tượng nghiệp vụ thường chứa những **kiểu giá trị** (value type) có cấu trúc riêng. Đơn hàng có địa chỉ giao hàng; địa chỉ gồm tên đường, thành phố và tọa độ; tọa độ lại gồm vĩ độ và kinh độ. Việc tách cấu trúc thành nhiều class giúp mô hình dễ hiểu, nhưng không nhất thiết mỗi class phải có một bảng, một ID và một vòng đời lưu trữ độc lập.

**Jakarta Persistence (JPA)** hỗ trợ **@Embeddable** và **@Embedded** để ánh xạ những cấu trúc như vậy. Một embeddable có thể chứa embeddable khác; toàn bộ các thuộc tính cơ bản bên trong được ánh xạ thành các cột thuộc bảng của entity sở hữu (trừ khi mapping chỉ rõ một bố trí khác được JPA hỗ trợ).

Ví dụ:

~~~text
Java object graph                                 Bảng purchase_orders

PurchaseOrder                                     id
 ├── id                                           reference_code
 ├── referenceCode                                shipping_street
 └── shippingAddress: Address                     shipping_city
       ├── street                                 shipping_postal_code
       ├── city                                   shipping_latitude
       ├── postalCode                             shipping_longitude
       └── coordinates: GeoPoint                  billing_street
             ├── latitude                         billing_city
             └── longitude                        billing_postal_code
                                                 billing_latitude
                                                 billing_longitude
~~~

Mục tiêu bài học là sử dụng **cấu trúc nhúng lồng nhau**, xử lý những tình huống một kiểu giá trị được nhúng nhiều lần, override tên cột theo đường dẫn thuộc tính, hiểu null và vòng đời persistence, cũng như thiết kế validation, truy vấn, migration và kiểm thử phù hợp.

## 1. Embeddable là kiểu giá trị được lưu như một phần của entity

Ba annotation cần phân biệt:

| Annotation | Đặt ở đâu? | Ý nghĩa |
|---|---|---|
| **@Embeddable** | Trên class | Khai báo class có thể được nhúng vào một entity hoặc embeddable khác |
| **@Embedded** | Trên field/getter được mapping | Sử dụng một embeddable làm thuộc tính của object sở hữu |
| **@AttributeOverride / @AttributeOverrides** | Trên vị trí dùng embeddable hoặc entity mapping thích hợp | Ghi đè ánh xạ cột của một thuộc tính cơ bản, kể cả thuộc tính sâu trong embeddable |

Ví dụ một kiểu giá trị đơn giản:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import java.math.BigDecimal;

@Embeddable
public class GeoPoint {
    @Column(name = "latitude", precision = 10, scale = 7)
    private BigDecimal latitude;

    @Column(name = "longitude", precision = 10, scale = 7)
    private BigDecimal longitude;

    protected GeoPoint() { } // Constructor không tham số cho JPA.

    public GeoPoint(BigDecimal latitude, BigDecimal longitude) {
        this.latitude = latitude;
        this.longitude = longitude;
    }

    public BigDecimal getLatitude() { return latitude; }
    public BigDecimal getLongitude() { return longitude; }
}
~~~

Một entity có thể sử dụng:

~~~java
@Entity
public class Warehouse {
    @Id
    private Long id;

    @Embedded
    private GeoPoint location;
}
~~~

Nếu không đổi tên cột, **GeoPoint.latitude** và **GeoPoint.longitude** được lưu thành hai cột tương ứng của bảng warehouse. Không có bảng **geo_point** hay khóa ngoại bắt buộc cho riêng tọa độ.

Đây là điểm khác biệt căn bản giữa **@Embeddable** và **@Entity**:

| Đặc điểm | Embeddable/value type | Entity |
|---|---|---|
| Danh tính persistence độc lập | Thông thường không có | Có, qua **@Id** hoặc **@EmbeddedId** |
| Bảng riêng chỉ vì là một class | Không | Thường được ánh xạ thành một bảng hoặc cấu trúc entity table thích hợp |
| Vòng đời persist/remove riêng | Đi theo owner | Có vòng đời persistence của entity |
| Truy cập trực tiếp qua **EntityManager.find** | Không tìm độc lập theo ID | Có thể tìm theo class và ID |
| Quan hệ với owner | Quan hệ thành phần của giá trị | Có thể là association giữa các entity |
| Thay đổi thuộc tính | Là thay đổi trạng thái của owner | Là thay đổi trạng thái entity có identity riêng |

Một **Address** thường thích hợp làm embeddable khi nó chỉ mô tả địa chỉ trong một đơn hàng. Nếu địa chỉ có ID riêng, được nhiều tài khoản cùng tham chiếu và có vòng đời độc lập, có thể cần entity riêng. Không phải cứ cấu trúc lồng sâu là phải biến thành quan hệ giữa các bảng.

## 2. Embeddable có thể nhúng embeddable khác

Thiết kế ba cấp:

~~~text
PurchaseOrder (@Entity)
  └── shippingAddress (@Embedded Address)
        └── coordinates (@Embedded GeoPoint)
              ├── latitude
              └── longitude
~~~

**Address.java**:

~~~java
package com.example.orders.model;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import jakarta.persistence.Embedded;
import java.util.Objects;

@Embeddable
public class Address {
    @Column(name = "street", nullable = false, length = 200)
    private String street;

    @Column(name = "city", nullable = false, length = 100)
    private String city;

    @Column(name = "postal_code", nullable = false, length = 20)
    private String postalCode;

    @Embedded
    private GeoPoint coordinates;

    protected Address() { }

    public Address(
            String street, String city, String postalCode, GeoPoint coordinates
    ) {
        this.street = Objects.requireNonNull(street);
        this.city = Objects.requireNonNull(city);
        this.postalCode = Objects.requireNonNull(postalCode);
        this.coordinates = Objects.requireNonNull(coordinates);
    }

    public String getStreet() { return street; }
    public String getCity() { return city; }
    public String getPostalCode() { return postalCode; }
    public GeoPoint getCoordinates() { return coordinates; }
}
~~~

**GeoPoint.java** trong cùng package:

~~~java
package com.example.orders.model;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import java.math.BigDecimal;
import java.util.Objects;

@Embeddable
public class GeoPoint {
    @Column(name = "latitude", nullable = false, precision = 10, scale = 7)
    private BigDecimal latitude;

    @Column(name = "longitude", nullable = false, precision = 10, scale = 7)
    private BigDecimal longitude;

    protected GeoPoint() { }

    public GeoPoint(BigDecimal latitude, BigDecimal longitude) {
        this.latitude = Objects.requireNonNull(latitude);
        this.longitude = Objects.requireNonNull(longitude);

        if (latitude.compareTo(new BigDecimal("-90")) < 0
                || latitude.compareTo(new BigDecimal("90")) > 0) {
            throw new IllegalArgumentException("Vĩ độ phải nằm trong [-90, 90]");
        }
        if (longitude.compareTo(new BigDecimal("-180")) < 0
                || longitude.compareTo(new BigDecimal("180")) > 0) {
            throw new IllegalArgumentException("Kinh độ phải nằm trong [-180, 180]");
        }
    }

    public BigDecimal getLatitude() { return latitude; }
    public BigDecimal getLongitude() { return longitude; }
}
~~~

Đây là hai class thông thường dùng **field access**, vì annotation mapping nằm trên field. Constructor **protected** không tham số đáp ứng nhu cầu JPA khởi tạo embeddable trong các triển khai phổ biến; constructor nghiệp vụ kiểm tra đầu vào. Khi ORM nạp dữ liệu, nó có thể đặt field theo cơ chế persistence, nên ràng buộc dữ liệu quan trọng vẫn phải được đảm bảo tại schema.

### 2.1. Chỉ nhúng một lần: cấu hình đơn giản

~~~java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Embedded
    private Address shippingAddress;

    protected PurchaseOrder() { }
}
~~~

Với mapping đơn giản như vậy, provider có thể sử dụng các tên cột khai báo sẵn trong **Address** và **GeoPoint**:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    street VARCHAR(200),
    city VARCHAR(100),
    postal_code VARCHAR(20),
    latitude NUMERIC(10, 7),
    longitude NUMERIC(10, 7)
);
~~~

DDL này nhằm minh họa cách **flatten** cấu trúc vào một bảng; phần constraints sẽ được thiết kế đầy đủ ở ví dụ tiếp theo. Tên cột thực tế có thể khác nếu dự án sử dụng naming strategy hoặc override. Dù đối tượng Java có ba cấp, mô hình này chỉ có một hàng dữ liệu thuộc **purchase_orders**.

### 2.2. JPA ánh xạ theo đường dẫn thuộc tính

Một đường dẫn thuộc tính trong Java:

~~~text
order.shippingAddress.coordinates.latitude
~~~

gồm:

1. **order:** entity PurchaseOrder.
2. **shippingAddress:** thuộc tính kiểu Address được nhúng vào entity.
3. **coordinates:** thuộc tính kiểu GeoPoint được nhúng vào Address.
4. **latitude:** thuộc tính cơ bản BigDecimal được lưu vào cột database.

Chính đường dẫn này là cơ sở để override các cột lồng sâu và viết truy vấn JPQL. Không có JOIN giữa các bảng chỉ vì hai class **Address** và **GeoPoint** được nhúng.

## 3. Nhúng cùng một kiểu giá trị nhiều lần: vấn đề trùng tên cột

Đơn hàng có thể cần cả **shippingAddress** và **billingAddress**:

~~~java
@Embedded
private Address shippingAddress;

@Embedded
private Address billingAddress;
~~~

Nếu cả hai cùng dùng mapping cột mặc định **street**, **city**, **postal_code**, **latitude**, **longitude**, provider có thể phát hiện **nhiều thuộc tính cùng ánh xạ một cột vật lý** và báo lỗi khi khởi động. Cũng không có căn cứ để biết cột **street** tương ứng địa chỉ nào.

Cách biểu diễn rõ ràng là thêm prefix:

~~~text
shippingAddress.street                  -> shipping_street
shippingAddress.city                    -> shipping_city
shippingAddress.postalCode              -> shipping_postal_code
shippingAddress.coordinates.latitude    -> shipping_latitude
shippingAddress.coordinates.longitude   -> shipping_longitude

billingAddress.street                   -> billing_street
billingAddress.city                     -> billing_city
billingAddress.postalCode               -> billing_postal_code
billingAddress.coordinates.latitude     -> billing_latitude
billingAddress.coordinates.longitude    -> billing_longitude
~~~

JPA có **@AttributeOverride** để thay đổi metadata cột theo **vị trí sử dụng** một embeddable, mà không cần nhân bản các class Address, ShippingAddress và BillingAddress với những field giống hệt nhau.

## 4. Dùng @AttributeOverrides với đường dẫn lồng sâu

Trên entity **PurchaseOrder**, khai báo đầy đủ:

~~~java
package com.example.orders.model;

import jakarta.persistence.AttributeOverride;
import jakarta.persistence.AttributeOverrides;
import jakarta.persistence.Column;
import jakarta.persistence.Embedded;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.util.Objects;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "reference_code", nullable = false, unique = true, length = 64)
    private String referenceCode;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(
            name = "street",
            column = @Column(name = "shipping_street", nullable = false, length = 200)
        ),
        @AttributeOverride(
            name = "city",
            column = @Column(name = "shipping_city", nullable = false, length = 100)
        ),
        @AttributeOverride(
            name = "postalCode",
            column = @Column(name = "shipping_postal_code", nullable = false, length = 20)
        ),
        @AttributeOverride(
            name = "coordinates.latitude",
            column = @Column(
                name = "shipping_latitude", nullable = false,
                precision = 10, scale = 7
            )
        ),
        @AttributeOverride(
            name = "coordinates.longitude",
            column = @Column(
                name = "shipping_longitude", nullable = false,
                precision = 10, scale = 7
            )
        )
    })
    private Address shippingAddress;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(
            name = "street",
            column = @Column(name = "billing_street", length = 200)
        ),
        @AttributeOverride(
            name = "city",
            column = @Column(name = "billing_city", length = 100)
        ),
        @AttributeOverride(
            name = "postalCode",
            column = @Column(name = "billing_postal_code", length = 20)
        ),
        @AttributeOverride(
            name = "coordinates.latitude",
            column = @Column(name = "billing_latitude", precision = 10, scale = 7)
        ),
        @AttributeOverride(
            name = "coordinates.longitude",
            column = @Column(name = "billing_longitude", precision = 10, scale = 7)
        )
    })
    private Address billingAddress;

    protected PurchaseOrder() { }

    public PurchaseOrder(
            String referenceCode, Address shippingAddress, Address billingAddress
    ) {
        this.referenceCode = Objects.requireNonNull(referenceCode);
        this.shippingAddress = Objects.requireNonNull(shippingAddress);
        this.billingAddress = billingAddress; // Có thể không cung cấp.
    }

    public Long getId() { return id; }
    public String getReferenceCode() { return referenceCode; }
    public Address getShippingAddress() { return shippingAddress; }
    public Address getBillingAddress() { return billingAddress; }

    public void changeShippingAddress(Address newAddress) {
        this.shippingAddress = Objects.requireNonNull(newAddress);
    }

    public void changeBillingAddress(Address newAddress) {
        this.billingAddress = newAddress;
    }
}
~~~

### 4.1. Cách đọc phần name trong @AttributeOverride

Khi annotation nằm trên **shippingAddress**, thuộc tính **name** được diễn đạt **tương đối từ Address**:

| name | Thuộc tính Java đích | Column |
|---|---|---|
| **"street"** | Address.street | shipping_street |
| **"city"** | Address.city | shipping_city |
| **"postalCode"** | Address.postalCode | shipping_postal_code |
| **"coordinates.latitude"** | Address.coordinates.latitude | shipping_latitude |
| **"coordinates.longitude"** | Address.coordinates.longitude | shipping_longitude |

Điểm quan trọng nhất là **dấu chấm** trong **"coordinates.latitude"**. Vì **coordinates** là một embeddable bên trong Address, JPA cho phép ghi đè basic attribute sâu bằng đường dẫn:

~~~java
@AttributeOverride(
    name = "coordinates.latitude",
    column = @Column(name = "shipping_latitude")
)
~~~

Tên **name** dùng tên thuộc tính Java đã mapping, không dùng tên cột gốc. Ở ví dụ này **postalCode** mới đúng; **postal_code** là tên cột SQL và không phải đường dẫn property. Khi đổi tên field Java, các override dạng chuỗi này cũng phải được cập nhật.

### 4.2. Override toàn bộ @Column metadata liên quan

Một override cung cấp **@Column** mới cho thuộc tính tương ứng. Không nên nghĩ rằng việc đổi riêng **name** luôn kế thừa mọi thiết lập **nullable**, **length**, **precision**, **scale** của **@Column** ban đầu. Vì vậy ví dụ trên khai báo rõ các thông số quan trọng ở từng cột được override.

Đặc biệt:

- **shippingAddress** bắt buộc trong nghiệp vụ; các cột shipping đặt **nullable=false**.
- **billingAddress** có thể null; các cột billing được cho phép null trong schema.
- **GeoPoint** yêu cầu độ chính xác 7 chữ số thập phân cho vị trí, nên override vẫn giữ **precision=10, scale=7**.
- Có thể dùng **insertable/updatable** trong **@Column** của override nếu một cột được DB sinh hoặc chỉ đọc, nhưng phải hiểu trách nhiệm ghi của từng mapping.

Để thay đổi tên cột FK thuộc **@ManyToOne** trong embeddable, dùng **@AssociationOverride**, không dùng **@AttributeOverride** cho association. Nội dung này được giới thiệu ở phần nâng cao.

### 4.3. Có thể override ngay tại embeddable bên trong

Nếu chỉ có một Address và muốn đổi tên cột của GeoPoint trong mọi lần dùng Address, có thể đặt override trên **Address.coordinates**:

~~~java
@Embeddable
public class Address {
    @Column(name = "street")
    private String street;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(
            name = "latitude",
            column = @Column(name = "coordinate_latitude", precision = 10, scale = 7)
        ),
        @AttributeOverride(
            name = "longitude",
            column = @Column(name = "coordinate_longitude", precision = 10, scale = 7)
        )
    })
    private GeoPoint coordinates;
}
~~~

Ở vị trí này **name="latitude"** đã đủ, vì annotation nằm trực tiếp trên **coordinates**. Khi đặt override tại owner **PurchaseOrder.shippingAddress**, đường dẫn cần ghi **"coordinates.latitude"**. Chọn nơi override theo phạm vi tái sử dụng: quy tắc dùng chung đặt gần embeddable, quy tắc chỉ thuộc một field nhúng đặt tại nơi field đó được khai báo.

Đây là ví dụ thay thế để thấy phạm vi override, không phải yêu cầu chồng thêm nguyên văn lên toàn bộ code ở phần 4.

## 5. Schema thực tế: tất cả các cấp đều thành cột của một bảng

Với PurchaseOrder trong phần 4, một cấu trúc PostgreSQL tương ứng có thể là:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    reference_code VARCHAR(64) NOT NULL UNIQUE,

    shipping_street VARCHAR(200) NOT NULL,
    shipping_city VARCHAR(100) NOT NULL,
    shipping_postal_code VARCHAR(20) NOT NULL,
    shipping_latitude NUMERIC(10, 7) NOT NULL,
    shipping_longitude NUMERIC(10, 7) NOT NULL,

    billing_street VARCHAR(200),
    billing_city VARCHAR(100),
    billing_postal_code VARCHAR(20),
    billing_latitude NUMERIC(10, 7),
    billing_longitude NUMERIC(10, 7),

    CONSTRAINT chk_shipping_coordinates CHECK (
        shipping_latitude BETWEEN -90 AND 90
        AND shipping_longitude BETWEEN -180 AND 180
    ),

    CONSTRAINT chk_billing_coordinates CHECK (
        (billing_latitude IS NULL
         AND billing_longitude IS NULL)
        OR
        (billing_latitude BETWEEN -90 AND 90
         AND billing_longitude BETWEEN -180 AND 180)
    ),

    CONSTRAINT chk_billing_all_or_none CHECK (
        (
            billing_street IS NULL
            AND billing_city IS NULL
            AND billing_postal_code IS NULL
            AND billing_latitude IS NULL
            AND billing_longitude IS NULL
        )
        OR
        (
            billing_street IS NOT NULL
            AND billing_city IS NOT NULL
            AND billing_postal_code IS NOT NULL
            AND billing_latitude IS NOT NULL
            AND billing_longitude IS NOT NULL
        )
    )
);
~~~

Những constraint ở đây chỉ minh họa một chính sách nghiệp vụ:

- Shipping bắt buộc đầy đủ, tọa độ nằm trong giới hạn hợp lệ.
- Billing có thể không có; nếu có thì phải đủ tất cả thành phần.
- Database kiểm soát dữ liệu đến từ bất kỳ client nào, không phụ thuộc riêng vào JPA.

**@Column(nullable=false)** là metadata mapping, có thể được provider dùng khi tạo DDL, nhưng **không tự sửa bảng đang tồn tại**. Trong dự án thật phải tạo và cập nhật schema bằng migration; khi sửa số cấp nhúng hoặc tên cột cần đổi migration cùng lúc.

### 5.1. SQL INSERT khi lưu object graph

~~~java
Address shipping = new Address(
    "12 Đường Số 3",
    "TP. Hồ Chí Minh",
    "700000",
    new GeoPoint(
        new BigDecimal("10.7769000"),
        new BigDecimal("106.7009000")
    )
);

PurchaseOrder order = new PurchaseOrder("ORD-001", shipping, null);
em.persist(order);
~~~

Giả sử EntityManager đang tham gia transaction hợp lệ, một câu INSERT có thể tương đương:

~~~sql
INSERT INTO purchase_orders (
    reference_code,
    shipping_street,
    shipping_city,
    shipping_postal_code,
    shipping_latitude,
    shipping_longitude
) VALUES (
    'ORD-001',
    '12 Đường Số 3',
    'TP. Hồ Chí Minh',
    '700000',
    10.7769000,
    106.7009000
);
~~~

Trong SQL do provider phát ra, các cột billing có thể được gửi với **NULL** hoặc bị bỏ khỏi statement theo chiến lược sinh INSERT; dữ liệu cuối cùng phải hợp lệ theo schema. Cột ID do database cấp trong ví dụ dùng **IDENTITY**. Quan trọng: **không có thêm INSERT vào bảng Address hoặc GeoPoint**, vì hai class đó là embeddable chứ không phải entity độc lập.

### 5.2. SQL UPDATE khi thay một nhánh nhúng

~~~java
PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
order.changeShippingAddress(new Address(
    "34 Nguyễn Huệ",
    "TP. Hồ Chí Minh",
    "700000",
    new GeoPoint(
        new BigDecimal("10.7753000"),
        new BigDecimal("106.7021000")
    )
));
// Khi transaction flush, các cột tương ứng của purchase_orders được cập nhật.
~~~

Một dạng SQL minh họa:

~~~sql
UPDATE purchase_orders
SET shipping_street = ?,
    shipping_city = ?,
    shipping_postal_code = ?,
    shipping_latitude = ?,
    shipping_longitude = ?
WHERE id = ?;
~~~

Provider có thể cập nhật thêm cột khác của entity (tùy chiến lược dynamic update, version và mapping). Điểm cốt lõi là dữ liệu embeddable được lưu **trên hàng của owner**, không được quản lý bằng một transaction hay bảng riêng.

## 6. Vòng đời, dirty checking và giá trị lồng nhau

### 6.1. Embeddable không có EntityManager riêng

Các thao tác:

~~~java
em.persist(order);
em.remove(order);
em.find(PurchaseOrder.class, id);
~~~

áp dụng cho **PurchaseOrder** là entity. Không gọi:

~~~java
em.persist(new GeoPoint(...));           // Sai: GeoPoint không phải entity.
em.find(Address.class, addressId);      // Sai: Address không có @Id độc lập.
~~~

Embeddable được xử lý thông qua entity chứa nó. JPA không cần **CascadeType.PERSIST** chỉ để lưu phần dữ liệu basic nằm bên trong một Address nhúng. Nếu một embeddable có **association tới entity khác**, cascade của association đó là câu chuyện riêng.

### 6.2. Dirty checking có thể quan sát thay đổi sâu

Trong một persistence context:

~~~java
PurchaseOrder order = em.find(PurchaseOrder.class, id);
Address address = order.getShippingAddress();
// Nếu Address cho phép sửa:
address.changeCity("Đà Nẵng");
// Provider có thể phát UPDATE cho purchase_orders khi flush.
~~~

Đoạn minh họa giả định Address có method **changeCity**; class Address trong ví dụ chính ở trên chưa định nghĩa method này. Với value object thiết kế bất biến về mặt nghiệp vụ, thay cả Address qua **order.changeShippingAddress(newAddress)** thường giúp kiểm soát trạng thái và validation dễ hơn.

Provider JPA phát hiện sự thay đổi của trạng thái được mapping bên trong embeddable khi entity owner đang managed. Không nên dựa vào các thao tác trên entity **detached** để tự ghi dữ liệu: sau khi persistence context đóng, thay đổi object graph sẽ không tự tạo SQL trong transaction cũ.

### 6.3. Không đồng nhất identity của value object với identity của entity

Giả sử hai đơn hàng cùng có địa chỉ:

~~~java
Address address = new Address(...);

PurchaseOrder first = new PurchaseOrder("ORD-A", address, null);
PurchaseOrder second = new PurchaseOrder("ORD-B", address, null);
~~~

Hai entity có thể chia sẻ **cùng tham chiếu Java** tới Address ở thời điểm khởi tạo, nhưng database lưu **hai bộ cột riêng trong hai hàng**. Không có FK để ràng buộc chúng tới một bản ghi Address duy nhất. Nếu Address mutable, sửa qua một reference có thể làm cả hai object graph thay đổi và dẫn tới hành vi khó dự đoán.

Với value object, khuyến khích cách sử dụng **không chia sẻ trạng thái có thể sửa**: xây dựng object từ giá trị đã kiểm tra, cung cấp getter, thay cả object khi cần, hoặc sao chép khi đưa giá trị mutable vào object. Không mặc định Hibernate/JPA xem một embeddable Java mutable là immutable trong bộ nhớ.

### 6.4. equals(), hashCode() và ngữ nghĩa giá trị

Kiểu giá trị thường được so sánh theo nội dung:

~~~java
GeoPoint p1 = new GeoPoint(
    new BigDecimal("10.0000000"), new BigDecimal("106.0000000"));
GeoPoint p2 = new GeoPoint(
    new BigDecimal("10.0000000"), new BigDecimal("106.0000000"));
// Theo ngữ nghĩa value object, mong muốn p1 tương đương p2.
~~~

Nếu domain cần so sánh value object, có thể triển khai **equals/hashCode** nhất quán theo các thuộc tính. Với **BigDecimal**, **equals** còn xét scale, trong khi **compareTo** so sánh giá trị số; phải quyết định chuẩn hóa scale hoặc định nghĩa equality phù hợp. Tránh để value object mutable thay đổi hashCode sau khi đã được dùng làm phần tử HashSet hoặc key trong HashMap.

JPA không yêu cầu mọi embeddable có equals/hashCode giống nhau cho mọi trường hợp, nhưng việc định nghĩa equality rõ ràng giúp nghiệp vụ và test dễ hiểu. Với **@EmbeddedId**, equals/hashCode lại đặc biệt quan trọng vì embeddable là định danh tổng hợp.

## 7. Vấn đề NULL ở các cấp lồng nhau

Nested embeddable là một cây object Java, nhưng database thường có các cột riêng rẽ. Đây là nguồn của nhiều trường hợp cần xử lý cẩn thận.

### 7.1. Cả một nhánh bằng null

~~~java
PurchaseOrder order = new PurchaseOrder(
    "ORD-002", shippingAddress, null /* billingAddress */);
~~~

Ở Java, **billingAddress = null**. Trong database, các cột **billing_street**, **billing_city**, **billing_postal_code**, **billing_latitude**, **billing_longitude** đều có thể được lưu **NULL**.

Khi đọc lại, cách provider tái tạo một embeddable có tất cả các cột NULL có thể khác theo provider và cấu hình: có nơi trả về **null**, có nơi có thể khởi tạo object embeddable chứa các field null. Vì vậy ứng dụng không nên dựa vào một hành vi không được kiểm chứng khi logic nghiệp vụ phụ thuộc vào “không có địa chỉ billing”.

Nếu cần phân biệt **không khai báo địa chỉ** và **địa chỉ có field trống**, phải thiết kế quy tắc rõ, đồng bộ Java và schema, và thử nghiệm hành vi của provider đang dùng.

### 7.2. Null ở giữa cây object

Ví dụ:

~~~java
Address address = new Address("12 A", "Hà Nội", "100000", null);
~~~

Nếu constructor cho phép **coordinates=null**, các cột tọa độ có thể được ghi null. Nhưng với schema shipping ở phần 5, điều đó vi phạm NOT NULL. Constructor Address mẫu đang dùng **Objects.requireNonNull(coordinates)** để chặn từ ứng dụng; database vẫn có **NOT NULL** để bảo vệ các nguồn ghi ngoài JPA.

Một validation có chủ đích:

~~~java
@Embeddable
public class Address {
    @NotBlank
    private String street;

    @NotBlank
    private String city;

    @NotBlank
    private String postalCode;

    @NotNull
    @Valid
    @Embedded
    private GeoPoint coordinates;
}
~~~

Trong entity:

~~~java
@NotNull
@Valid
@Embedded
private Address shippingAddress;

@Valid
@Embedded
private Address billingAddress; // Có thể null; nếu khác null, validate bên trong.
~~~

**@NotBlank** và **@NotNull** thuộc **jakarta.validation.constraints**, **@Valid** thuộc **jakarta.validation**. Chúng hỗ trợ Bean Validation khi validation được kích hoạt và tích hợp vào lifecycle; chúng không tự tạo đầy đủ CHECK/NOT NULL/logic toàn nhánh tại DB. Ví dụ này minh họa validation, không phải yêu cầu thêm một class Address trùng tên vào cùng source file.

### 7.3. Partial NULL và tính toàn vẹn dữ liệu

Một dòng trong database có thể ở trạng thái:

~~~text
billing_street = "25 Lê Lợi"
billing_city = NULL
billing_postal_code = "700000"
billing_latitude = NULL
billing_longitude = NULL
~~~

Nếu schema chỉ cho phép mọi cột billing nullable mà không có CHECK, dòng này có thể hợp lệ ở mức DB nhưng không tạo thành Address hợp lệ theo business rule. Một ràng buộc **all-or-none** như phần 5 giúp bảo vệ cấu trúc như một khối.

Điểm tinh tế: **@Embedded** tự nó không tạo ra một constraint “toàn bộ nhánh phải có hoặc không có”. Đây là yêu cầu bổ sung ở Java validation/DB schema. Khi thông tin địa chỉ có rất nhiều trường optional, cần điều chỉnh quy tắc all-or-none cho phù hợp thực tế.

## 8. @AttributeOverride với cấu trúc nhúng sâu hơn ba cấp

Giả sử có mô hình:

~~~text
Account
 └── profile: Profile
      └── contact: ContactDetails
           └── phone: PhoneNumber
                ├── countryCode
                └── localNumber
~~~

Khai báo class có thể là:

~~~java
@Embeddable
public class PhoneNumber {
    private String countryCode;
    private String localNumber;
}

@Embeddable
public class ContactDetails {
    @Embedded
    private PhoneNumber phone;
}

@Embeddable
public class Profile {
    @Embedded
    private ContactDetails contact;
}
~~~

Ở entity **Account**:

~~~java
@Embedded
@AttributeOverrides({
    @AttributeOverride(
        name = "contact.phone.countryCode",
        column = @Column(name = "profile_phone_country_code", length = 8)
    ),
    @AttributeOverride(
        name = "contact.phone.localNumber",
        column = @Column(name = "profile_phone_number", length = 32)
    )
})
private Profile profile;
~~~

Quy tắc không đổi: dùng **đường dẫn thuộc tính Java nối bằng dấu chấm**, tương đối từ object được nhúng tại vị trí annotation. Chiều sâu của cấu trúc không yêu cầu tạo thêm bảng. Tuy nhiên, nếu mô hình lồng quá sâu đến mức migration, query và validation khó hiểu, có thể đã đến lúc xem lại ranh giới value object hoặc thiết kế aggregate.

## 9. Kết hợp @AssociationOverride khi embeddable chứa quan hệ

Một embeddable không nhất thiết chỉ chứa String hoặc BigDecimal. Trong những trường hợp được mapping thích hợp, nó có thể có association tới entity, chẳng hạn người phụ trách hoặc phòng ban của một hành động.

~~~java
@Entity
public class Department {
    @Id
    private Long id;
}

@Embeddable
public class ActorDetails {
    private String displayName;

    @ManyToOne(fetch = FetchType.LAZY)
    private Department department;
}

@Embeddable
public class AuditDetails {
    @Embedded
    private ActorDetails actor;
}
~~~

Khi một entity chứa nhiều AuditDetails, cần định nghĩa cột FK khác nhau:

~~~java
@Entity
public class ApprovalRequest {
    @Id
    private Long id;

    @Embedded
    @AssociationOverride(
        name = "actor.department",
        joinColumns = @JoinColumn(name = "created_department_id")
    )
    @AttributeOverride(
        name = "actor.displayName",
        column = @Column(name = "created_actor_name")
    )
    private AuditDetails createdBy;

    @Embedded
    @AssociationOverride(
        name = "actor.department",
        joinColumns = @JoinColumn(name = "approved_department_id")
    )
    @AttributeOverride(
        name = "actor.displayName",
        column = @Column(name = "approved_actor_name")
    )
    private AuditDetails approvedBy;
}
~~~

Hai nhóm annotation có vai trò khác nhau:

| Loại thuộc tính trong embeddable | Annotation override | Ánh xạ đến |
|---|---|---|
| Basic attribute như **displayName** | **@AttributeOverride** | **@Column** |
| Entity association như **department** | **@AssociationOverride** | **@JoinColumn** hoặc join table phù hợp |

Trong ví dụ, **ApprovalRequest** lưu các cột **created_department_id**, **approved_department_id** là FK tới **Department**. Nếu một embeddable chứa association thì SQL có thể cần JOIN khi tải entity liên quan; việc “flatten” chỉ áp dụng cho các thuộc tính giá trị, không biến entity được tham chiếu thành những cột đầy đủ của owner.

Không dùng association trực tiếp tới entity thuộc persistence unit hoặc database độc lập với owner mà mặc định JPA sẽ tự giải quyết quan hệ xuyên nguồn. Hãy xác định ranh giới persistence và transaction khi thiết kế.

## 10. Nested embeddable trong @ElementCollection

Đôi khi một entity sở hữu **nhiều value object**, thay vì một nhánh cố định. Ví dụ khách hàng có danh sách điểm nhận hàng, mỗi điểm nhận là một value object chứa tọa độ.

~~~java
@Embeddable
public class PickupPoint {
    private String label;

    @Embedded
    private GeoPoint coordinates;
}
~~~

Trong Customer:

~~~java
@Entity
@Table(name = "customers")
public class Customer {
    @Id
    private Long id;

    @ElementCollection
    @CollectionTable(
        name = "customer_pickup_points",
        joinColumns = @JoinColumn(name = "customer_id")
    )
    @AttributeOverrides({
        @AttributeOverride(
            name = "label",
            column = @Column(name = "point_label", length = 100)
        ),
        @AttributeOverride(
            name = "coordinates.latitude",
            column = @Column(name = "point_latitude", precision = 10, scale = 7)
        ),
        @AttributeOverride(
            name = "coordinates.longitude",
            column = @Column(name = "point_longitude", precision = 10, scale = 7)
        )
    })
    private List<PickupPoint> pickupPoints = new ArrayList<>();
}
~~~

Đây là sự khác biệt so với **một @Embedded Address**:

~~~text
Customer (@Entity)
  ├── @Embedded Address
  │     └── các cột nằm trên hàng customers
  │
  └── @ElementCollection List<PickupPoint>
        └── nhiều hàng trong customer_pickup_points
             ├── customer_id (FK)
             ├── point_label
             ├── point_latitude
             └── point_longitude
~~~

Các phần tử PickupPoint vẫn là value object không có entity identity riêng. Collection table là để lưu nhiều giá trị. Nếu phần tử có lifecycle, identity hoặc quan hệ nghiệp vụ độc lập, cân nhắc **@OneToMany** với một entity có khóa chính.

Khi dùng List trong element collection, thứ tự truy xuất chỉ được đảm bảo nếu mapping lưu thứ tự thích hợp, ví dụ **@OrderColumn**, hoặc query có quy tắc thứ tự. Các thao tác trên collection có thể dẫn đến SQL DELETE/INSERT nhiều hàng tùy provider và mapping; cần quan sát khi collection lớn.

## 11. Nested embeddable và định danh tổng hợp @EmbeddedId

**@Embedded** mô tả một giá trị nằm trong entity. **@EmbeddedId** cũng sử dụng embeddable nhưng có chức năng khác: **toàn bộ value object biểu diễn khóa chính tổng hợp của entity**.

Ví dụ bảng **inventory_balance** có khóa gồm mã kho và mã SKU:

~~~java
@Embeddable
public class InventoryKey implements java.io.Serializable {
    @Column(name = "warehouse_code", length = 30)
    private String warehouseCode;

    @Column(name = "sku", length = 64)
    private String sku;

    protected InventoryKey() {}
    // Constructor, getter, equals và hashCode.
}

@Entity
@Table(name = "inventory_balance")
public class InventoryBalance {
    @EmbeddedId
    private InventoryKey id;

    @Column(nullable = false)
    private Integer quantity;
}
~~~

Embeddable cho ID cần tuân thủ các quy tắc về khóa chính của JPA, trong đó triển khai **equals/hashCode** phù hợp và tính ổn định của định danh là rất quan trọng. Không coi **@EmbeddedId** như một @Embedded ngẫu nhiên có thể thay cả ID sau khi entity đang persistent.

Với một số mô hình khóa phức tạp, **@MapsId** liên kết association với một phần khóa; nên dùng thiết kế composite key được đặc tả hỗ trợ thay vì cố sửa trùng tên cột bằng hàng loạt **insertable=false, updatable=false** không có cơ sở.

## 12. Fetch, query và hiệu năng

### 12.1. Không có JOIN chỉ vì nhiều lớp nhúng

Với mô hình **PurchaseOrder → Address → GeoPoint** lưu cùng bảng, JPA có thể đọc các cột giá trị qua SELECT trên **purchase_orders**:

~~~sql
SELECT
    id,
    reference_code,
    shipping_street,
    shipping_city,
    shipping_postal_code,
    shipping_latitude,
    shipping_longitude
FROM purchase_orders
WHERE id = ?;
~~~

Không có JOIN tới **addresses** hay **geo_points** vì hai bảng đó không tồn tại trong mapping đang xét. Ngược lại, một association **@ManyToOne Department** bên trong embeddable có thể dẫn đến SQL bổ sung khi truy cập theo fetch strategy.

### 12.2. Dùng đường dẫn thuộc tính trong JPQL

JPQL dùng tên **thuộc tính Java**, không dùng tên cột SQL.

~~~java
List<PurchaseOrder> orders = em.createQuery(
    """
    select o
    from PurchaseOrder o
    where o.shippingAddress.city = :city
      and o.shippingAddress.coordinates.latitude >= :minLat
    order by o.id desc
    """,
    PurchaseOrder.class
)
.setParameter("city", "TP. Hồ Chí Minh")
.setParameter("minLat", new BigDecimal("10.7000000"))
.getResultList();
~~~

SQL tương ứng thường lọc theo **shipping_city** và **shipping_latitude** trong **purchase_orders**. Không viết JPQL kiểu **o.shipping_city**, vì đó là tên cột vật lý do **@AttributeOverride** tạo ra.

### 12.3. Criteria API cũng đi qua từng cấp

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<PurchaseOrder> query = cb.createQuery(PurchaseOrder.class);
Root<PurchaseOrder> root = query.from(PurchaseOrder.class);

Path<String> city = root.get("shippingAddress").get("city");
query.select(root).where(cb.equal(city, "Đà Nẵng"));

List<PurchaseOrder> result = em.createQuery(query).getResultList();
~~~

Các import thuộc **jakarta.persistence.criteria** và các class Java/JPA tương ứng. Với static metamodel, một số đường dẫn có thể được kiểm tra kiểu tốt hơn; ví dụ dùng chuỗi đơn giản để thể hiện cây property.

### 12.4. Index phải dựa trên cột thực tế

Nếu ứng dụng thường tìm đơn theo thành phố giao hàng:

~~~sql
CREATE INDEX idx_orders_shipping_city
    ON purchase_orders(shipping_city);
~~~

Không tạo index cho **Address** hay **GeoPoint** như thể chúng là các bảng. Chọn index theo truy vấn SQL thực tế, phân bố dữ liệu và kế hoạch thực thi. Với tọa độ địa lý và truy vấn bán kính/phạm vi phức tạp, chỉ hai cột NUMERIC thông thường có thể không tối ưu; có thể cần kiểu không gian/index của database như PostGIS tùy yêu cầu. Điều đó là một quyết định về lưu trữ và truy vấn, độc lập với việc Java tổ chức GeoPoint thành embeddable.

## 13. Quy tắc access type, constructor và tính bất biến

### 13.1. Field access so với property access

Trong ví dụ:

~~~java
@Id
private Long id;
~~~

JPA thường dùng **field access** cho entity. Các annotation mapping của embeddable được đặt trên field, cùng phong cách với owner. Nếu dự án dùng property access, annotation đặt trên getter và cần getter/setter phù hợp.

Không trộn vị trí annotation một cách tùy tiện giữa class cha và class nhúng. Nếu cần chuyển loại access, dùng **@Access(AccessType.FIELD)** hoặc **@Access(AccessType.PROPERTY)** ở nơi phù hợp, rồi xác định lại property name dùng trong **@AttributeOverride**.

Ví dụ:

~~~java
@Embeddable
@Access(AccessType.FIELD)
public class GeoPoint {
    private BigDecimal latitude;
    private BigDecimal longitude;
    protected GeoPoint() {}
}
~~~

Tên đường dẫn override phải khớp tên thuộc tính JPA đã xác định. Không dựa vào tên field không được mapping nếu class dùng property access và getter có tên logic khác.

### 13.2. Value object nên dễ sử dụng như giá trị

Trong thiết kế miền dữ liệu, value object thường được mong đợi:

- Không có định danh riêng ngoài các thành phần giá trị.
- Có quy tắc hợp lệ rõ trong constructor hoặc factory.
- So sánh theo giá trị khi nghiệp vụ cần.
- Hạn chế thay đổi tại chỗ; khi thay đổi, tạo một giá trị mới và gán cho owner.

JPA truyền thống yêu cầu khả năng khởi tạo và truy cập trạng thái theo quy tắc của provider. Nếu muốn dùng **Java record** làm embeddable hoặc field final hoàn toàn bất biến, cần xem khả năng hỗ trợ của **phiên bản Jakarta Persistence và provider** cụ thể; không giả định mọi Hibernate/JPA version hỗ trợ records giống nhau. Dùng class thông thường với constructor không tham số và public API hạn chế sửa là cách tương thích rộng hơn.

Không nhầm **value object không có setter public** với **bảo đảm database bất biến**: SQL ngoài ứng dụng vẫn có thể cập nhật các cột của entity nếu có quyền, trừ khi DB áp dụng chính sách tương ứng.

### 13.3. Đừng tạo chu trình nhúng vô hạn

Mô hình như:

~~~text
@Embeddable A -> @Embedded B -> @Embedded A -> ...
~~~

không thể flatten thành số cột hữu hạn theo cách thông thường. Nếu một cấu trúc thực sự đệ quy (cây danh mục, node cha-con), cần mô hình entity relationship hoặc cách lưu dữ liệu chuyên biệt, không biểu diễn bằng vòng lặp các **@Embedded**.

## 14. @Convert và kiểu dữ liệu trong cấu trúc nhúng

Một embeddable có thể chứa kiểu Java cần chuyển đổi trước khi lưu, chẳng hạn code vùng theo một value object riêng.

~~~java
public record CountryCode(String value) { }

@Converter
public class CountryCodeConverter
        implements AttributeConverter<CountryCode, String> {
    @Override
    public String convertToDatabaseColumn(CountryCode attribute) {
        return attribute == null ? null : attribute.value();
    }

    @Override
    public CountryCode convertToEntityAttribute(String dbValue) {
        return dbValue == null ? null : new CountryCode(dbValue);
    }
}
~~~

Trong Address:

~~~java
@Convert(converter = CountryCodeConverter.class)
@Column(name = "country_code", length = 2)
private CountryCode countryCode;
~~~

**AttributeConverter** biến **một basic attribute** thành một giá trị cột, khác với **@Embeddable**, nơi một object có thể được trải thành nhiều cột. Hai cơ chế có thể kết hợp: Address vẫn là embeddable, còn **countryCode** dùng converter để lưu vào VARCHAR. Class CountryCode dùng record chỉ như một **kiểu thuộc tính được converter xử lý**, không phải một embeddable JPA.

Nếu Address được nhúng hai lần, cần override tên cột **countryCode** ở từng nơi dùng Address giống những field khác. Converter vẫn được áp dụng theo mapping attribute, với những giới hạn của JPA dành cho AttributeConverter và kiểu đặc biệt.

### 14.1. Nested embeddable khác với lưu JSON

Các hệ quản trị hiện đại có thể lưu JSON trong một cột. Khi đó Java có thể biểu diễn Address bằng object lồng nhau, nhưng mapping và query hoàn toàn khác:

| Cách lưu | Ví dụ vật lý | Ưu điểm | Giới hạn |
|---|---|---|---|
| **Nested @Embedded** | Nhiều cột shipping_street, shipping_city, shipping_latitude | Constraint, index và SQL trên từng cột rõ ràng | Schema thay đổi khi thêm/bỏ field |
| **JSON column** | Một cột shipping_address JSON/JSONB | Cấu trúc linh hoạt theo payload | Query/index/constraint phụ thuộc DB và provider; không dùng cùng semantics @AttributeOverride |
| **Entity relationship** | FK shipping_address_id tới bảng addresses | Chia sẻ address entity, identity/vòng đời riêng | JOIN, cascade, transaction và ownership phức tạp hơn |

Không tự động thay **@Embedded** bằng JSON vì Java object có cấu trúc lồng nhau. Chọn cách lưu theo query, constraints, độ ổn định schema, khả năng chia sẻ và vòng đời dữ liệu.

## 15. Thay đổi schema khi cấu trúc nhúng tiến hóa

Giả sử phiên bản đầu lưu:

~~~java
@Embedded
private Address shippingAddress;
~~~

và Address chỉ có **street, city, postalCode**. Sau đó, ứng dụng bổ sung:

~~~java
@Embedded
private GeoPoint coordinates;
~~~

Trong mapping flatten, schema của **purchase_orders** cần thêm cột tọa độ:

~~~sql
ALTER TABLE purchase_orders
    ADD COLUMN shipping_latitude NUMERIC(10, 7),
    ADD COLUMN shipping_longitude NUMERIC(10, 7);
~~~

Nếu dữ liệu cũ chưa có tọa độ, thêm **NOT NULL ngay lập tức** có thể thất bại hoặc khiến ứng dụng đọc dữ liệu không phù hợp. Một hướng rollout an toàn:

1. Tạo cột mới nullable với migration.
2. Triển khai mã có khả năng đọc những hàng chưa có tọa độ.
3. Backfill giá trị hợp lệ nếu nghiệp vụ có đủ thông tin.
4. Xác nhận tất cả đường ghi mới tạo tọa độ và dữ liệu cũ đã được xử lý.
5. Chỉ sau đó cân nhắc thêm NOT NULL/CHECK hoặc cắt bỏ đường tương thích cũ.

**Tên class không phải tên bảng**, nên đổi Address thành DeliveryAddress trong Java không nhất thiết đổi schema nếu column mappings không đổi. Nhưng đổi tên property như **coordinates** thành **geoLocation** làm chuỗi override **"coordinates.latitude"** không còn trỏ tới thuộc tính hợp lệ; phải cập nhật mapping.

### 15.1. Di chuyển một embeddable sang entity riêng

Nếu về sau Address cần identity và nhiều order cùng tham chiếu, có thể phải chuyển:

~~~java
@Embedded
private Address shippingAddress;
~~~

thành:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "shipping_address_id")
private AddressEntity shippingAddress;
~~~

Đây **không phải chỉ thay một annotation**. Schema phải thêm bảng/ID/FK, di chuyển dữ liệu từ các cột cũ, quyết định ownership, uniqueness và xử lý quan hệ; update/query cũng có thể đổi thành JOIN. Trước khi thực hiện nên cân nhắc: địa chỉ lịch sử trong đơn hàng thường cần lưu snapshot không thay đổi theo địa chỉ hiện tại của người dùng, vì thế “chia sẻ một AddressEntity mutable” có thể làm sai lịch sử.

## 16. Các lỗi thường gặp khi ánh xạ lồng nhau

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra hoặc xử lý |
|---|---|---|
| **Repeated column in mapping** | Nhúng Address hai lần nhưng cả hai vẫn dùng cùng các cột mặc định | Thêm **@AttributeOverrides** với tên cột riêng cho từng nhánh |
| **Unable to locate attribute** khi bootstrap | Đường dẫn override sai, dùng tên cột SQL thay cho property Java, hoặc đổi tên field | Kiểm tra **name="coordinates.latitude"** theo cây thuộc tính |
| Giá trị longitude xuất hiện ở cột sai | Override nhầm field/cột, naming strategy khác dự kiến | Xem mapping, SQL phát sinh và metadata schema |
| INSERT lỗi **NOT NULL** | Nhánh nhúng null nhưng cột DB bắt buộc | Đồng bộ quy tắc optional và constraints; validate object trước persist |
| Giá trị Address sau reload thành null hoặc object rỗng | Tất cả cột của nhánh đều null, provider xử lý khác kỳ vọng | Xác định quy tắc null, test trên đúng provider/version |
| Sửa nested object nhưng không có UPDATE | Owner detached, không flush/transaction, hoặc property không được mapping | Kiểm tra entity state, transaction và access type |
| UPDATE quá nhiều cột | Embeddable nằm trên hàng owner; provider có thể update nhiều cột theo chiến lược SQL | Quan sát SQL, cân nhắc dynamic update/provider và yêu cầu hiệu năng |
| Query JPQL không nhận ra **shipping_city** | JPQL dùng property path chứ không dùng column name | Dùng **o.shippingAddress.city** |
| Truy vấn unexpectedly join nhiều bảng | Bên trong embeddable có entity association chứ không chỉ basic value | Xem **@ManyToOne**, fetch type và SQL |
| Schema ở môi trường chạy thiếu cột nested mới | Có sửa class nhưng thiếu migration tương ứng | Kiểm tra migration, schema thật và deploy order |
| Ghi đè thông số độ dài/precision | Override **@Column** mới nhưng không khai báo lại metadata cần thiết | Đặt rõ nullable, length, precision, scale trong override |
| Lỗi validation không nêu field lồng nhau | Chưa cascade Bean Validation bằng **@Valid** hoặc không kích hoạt provider | Kiểm tra annotation và cấu hình validation |
| Dùng chung Address mutable trên hai order tạo cập nhật bất ngờ | Hai Java object graph chia sẻ cùng tham chiếu value object | Dùng value object bất biến ở API hoặc sao chép |
| JSON serializer đi sâu vào association trong embeddable | Embeddable có @ManyToOne lazy hoặc cấu trúc vòng | Dùng DTO/projection, kiểm soát serialization và fetch |

## 17. Kiểm thử mapping và dữ liệu lồng nhau

Khi có nhiều cấp nhúng, chỉ kiểm thử constructor là chưa đủ: cần xác nhận đúng mapping từ object graph xuống những cột vật lý mong đợi và ngược lại. Ví dụ tích hợp (trong môi trường có **EntityManager**, schema và transaction):

~~~java
@Test
void persistsNestedAddressFields() {
    Address shipping = new Address(
        "10 Trần Hưng Đạo",
        "Hà Nội",
        "100000",
        new GeoPoint(
            new BigDecimal("21.0285000"),
            new BigDecimal("105.8542000")
        )
    );

    PurchaseOrder order = new PurchaseOrder("TEST-001", shipping, null);

    em.persist(order);
    em.flush();
    Long id = order.getId();
    em.clear();

    PurchaseOrder reloaded = em.find(PurchaseOrder.class, id);
    assertEquals("Hà Nội", reloaded.getShippingAddress().getCity());
    assertEquals(
        0,
        new BigDecimal("21.0285000").compareTo(
            reloaded.getShippingAddress().getCoordinates().getLatitude()
        )
    );
}
~~~

Ví dụ chỉ minh họa logic JUnit, cần import tương ứng và test transaction/database được cấu hình đúng. **flush + clear** buộc truy vấn lại dữ liệu thay vì chỉ kiểm tra object đang managed trong persistence context, giúp đánh giá phép ánh xạ lưu và đọc.

### 17.1. Những tình huống nên kiểm tra

| Ca kiểm thử | Kỳ vọng |
|---|---|
| Lưu shippingAddress và billingAddress khác nhau | Các cột shipping/billing chứa đúng giá trị, không ghi chồng |
| Lưu billingAddress=null | Schema cho phép và ứng dụng xử lý trạng thái không có billing đúng cách |
| Đọc dữ liệu có tọa độ âm hoặc giá trị biên | BigDecimal/precision/scale và quy tắc giới hạn được xử lý đúng |
| Đổi shippingAddress khi entity managed | Các cột owner được cập nhật sau flush/commit |
| Dùng property path sâu trong JPQL | Trả đúng đơn theo city/latitude |
| Một cột bị đổi tên trong migration | Mapping @AttributeOverride phản ánh tên cột mới |
| Thêm constraint all-or-none | Database từ chối billing address bị điền một phần |
| Dùng @AssociationOverride trong nested embeddable | FK được ánh xạ đúng cột và entity association đúng đích |

Trong các ca mà null behavior, access type hoặc generated SQL quan trọng, kiểm thử trên **cùng phiên bản JPA provider và database** dự kiến dùng ở production sẽ có giá trị hơn một bài test hoàn toàn dùng mock.

## 18. Bài tập thực hành

### Bài 1: Xác định vị trí lưu dữ liệu

Cho mô hình:

~~~java
@Entity
class Employee {
    @Id Long id;
    @Embedded PersonalInfo personalInfo;
}

@Embeddable
class PersonalInfo {
    String displayName;
    @Embedded ContactInfo contact;
}

@Embeddable
class ContactInfo {
    String email;
    String phone;
}
~~~

Hãy trả lời:

1. Có bao nhiêu entity có identity riêng?
2. Cần bao nhiêu bảng nếu chỉ có những mapping này, không thêm collection/association?
3. Để đổi tên cột cho **personalInfo.contact.email** thành **personal_email**, dùng override ở đâu và name là gì?

**Gợi ý:** chỉ Employee là entity; basic fields có thể nằm trong cùng bảng employee. Trên **Employee.personalInfo**, dùng **@AttributeOverride(name="contact.email", column=@Column(name="personal_email"))**.

### Bài 2: Hai nhánh nhúng cùng kiểu

~~~java
@Embeddable
class Money {
    BigDecimal amount;
    String currency;
}

@Entity
class Subscription {
    @Id Long id;
    @Embedded Money monthlyFee;
    @Embedded Money setupFee;
}
~~~

Hãy viết **@AttributeOverrides** sao cho schema chứa **monthly_amount**, **monthly_currency**, **setup_amount**, **setup_currency**. Giải thích vì sao không thể để cả hai nhánh dùng chung cột **amount** và **currency** nếu chúng đại diện hai giá trị độc lập.

Định hướng:

~~~java
@Embedded
@AttributeOverrides({
    @AttributeOverride(
        name = "amount",
        column = @Column(name = "monthly_amount", precision = 19, scale = 2)
    ),
    @AttributeOverride(
        name = "currency",
        column = @Column(name = "monthly_currency", length = 3)
    )
})
private Money monthlyFee;

@Embedded
@AttributeOverrides({
    @AttributeOverride(
        name = "amount",
        column = @Column(name = "setup_amount", precision = 19, scale = 2)
    ),
    @AttributeOverride(
        name = "currency",
        column = @Column(name = "setup_currency", length = 3)
    )
})
private Money setupFee;
~~~

### Bài 3: Override ở cấp nào?

Giả sử:

~~~text
Order
 └── shippingAddress: Address
       └── coordinates: GeoPoint
             └── latitude
~~~

Bạn muốn dùng cột **shipping_lat**. Hãy phân biệt:

- Đặt **@AttributeOverride** trên **Order.shippingAddress**: **name="coordinates.latitude"**.
- Đặt **@AttributeOverride** trên **Address.coordinates**: **name="latitude"**.

Vì sao hai tên này đều có thể đúng nhưng ở hai vị trí khác nhau? Hãy giải thích phạm vi tương đối của đường dẫn property.

### Bài 4: Phân biệt nested embeddable và association

Mô hình A:

~~~text
Order @Embedded Address @Embedded GeoPoint
~~~

Mô hình B:

~~~text
Order @ManyToOne AddressEntity
AddressEntity @Embedded GeoPoint
~~~

Hãy so sánh số bảng thường cần, sự tồn tại của khóa ngoại, vòng đời Address, khả năng nhiều Order dùng chung Address và nguy cơ thay đổi địa chỉ lịch sử nếu AddressEntity được chia sẻ.

**Gợi ý:** mô hình A lưu snapshot địa chỉ cùng hàng Order; mô hình B trỏ tới một địa chỉ entity có identity độc lập. B có thể chia sẻ nhưng cần chính sách không sửa lịch sử ngoài ý muốn.

### Bài 5: Null và validation

Một đơn hàng có **billingAddress** optional, nhưng khi đã có billingAddress thì không được thiếu city và coordinates. Hãy:

1. Đề xuất constructor/Bean Validation để tránh tạo object sai ở Java.
2. Đề xuất schema cho phép tất cả cột billing null hoặc đầy đủ nhưng chặn trường hợp chỉ có street.
3. Giải thích vì sao **@Embedded** một mình không tự tạo ràng buộc all-or-none.

Định hướng: dùng **@Valid** để cascade vào Address và GeoPoint; dùng CHECK all-or-none cùng constraints thích hợp ở database; xác minh cách provider nạp nhánh all-null.

### Bài 6: Viết truy vấn theo cấu trúc nested

Yêu cầu tìm các đơn có **billingAddress.coordinates.longitude > 105** và shipping city bằng **"Hà Nội"**. Viết JPQL dựa trên property paths, đồng thời nêu tên hai cột vật lý theo ví dụ phần 4.

Đáp án tham khảo:

~~~java
select o
from PurchaseOrder o
where o.billingAddress.coordinates.longitude > :lon
  and o.shippingAddress.city = :city
~~~

Hai cột là **billing_longitude** và **shipping_city**; truy vấn không JOIN đến bảng GeoPoint vì tọa độ là embeddable.

### Bài 7: Phát hiện lỗi sau khi refactor

Developer đổi tên field **Address.coordinates** thành **Address.position** nhưng giữ:

~~~java
@AttributeOverride(
    name = "coordinates.latitude",
    column = @Column(name = "shipping_latitude")
)
~~~

Hãy giải thích vì sao override không còn trỏ đúng thuộc tính. Hãy sửa thành:

~~~java
@AttributeOverride(
    name = "position.latitude",
    column = @Column(name = "shipping_latitude")
)
~~~

Tên cột SQL không cần đổi nếu nghiệp vụ không yêu cầu; chỉ đường dẫn Java trong annotation cần khớp mapping hiện tại.

## 19. Cách lựa chọn cấu trúc nhúng trong dự án thực tế

Khi cần ánh xạ một cấu trúc giá trị có nhiều cấp, có thể đi theo trình tự:

1. **Xác định identity:** phần nào là entity có danh tính/vòng đời riêng, phần nào chỉ là giá trị thuộc owner?
2. **Vẽ cây object:** ghi rõ tên từng field và cấp nhúng; kiểm tra không có vòng nhúng đệ quy.
3. **Thiết kế schema:** xác định bảng owner và tên cột vật lý của từng lá basic; chú ý các nhánh lặp lại như shipping/billing.
4. **Khai báo @Embeddable và @Embedded:** chọn field access hoặc property access nhất quán.
5. **Override tại vị trí dùng:** dùng tên thuộc tính tương đối và dấu chấm cho nhánh lồng sâu; khai báo rõ metadata cột quan trọng.
6. **Thiết kế null và validation:** nhánh nào bắt buộc, nhánh nào optional, partial null có được phép hay không; kết hợp Bean Validation và database constraints.
7. **Quản lý state:** thay value object qua owner, hiểu dirty checking, tránh chia sẻ object mutable và xác định cách equality.
8. **Viết query theo Java path:** dùng JPQL/Criteria dựa trên thuộc tính; index theo cột vật lý sau flatten.
9. **Đưa schema vào migration:** không trông chờ sửa class tự biến đổi database; chuẩn bị rollout cho dữ liệu cũ.
10. **Kiểm thử round trip:** persist, flush, clear, reload, cập nhật nested field, null và truy vấn ở mức SQL thực.

Một quy tắc dễ nhớ:

~~~text
@Embeddable                  → định nghĩa cấu trúc giá trị.
@Embedded                    → đưa cấu trúc ấy vào owner.
@Embedded bên trong          → tạo cấu trúc lồng nhiều cấp trong Java.
@AttributeOverride           → đổi cột của một basic property ở vị trí sử dụng.
name = "a.b.c"              → đi qua các thuộc tính nhúng a, b tới lá c.
@AssociationOverride         → đổi thông tin join của association trong embeddable.
@ElementCollection           → lưu nhiều value object vào collection table.
@EmbeddedId                  → dùng embeddable làm khóa chính tổng hợp, mục đích riêng.
~~~

**Kết luận:** ánh xạ cấu trúc nhúng lồng nhau giúp giữ mô hình Java có ý nghĩa nghiệp vụ mà không ép mỗi value object thành một entity/bảng. Các điểm phải kiểm soát là **đường dẫn thuộc tính khi override**, **tên cột khi nhúng lặp lại**, **null và toàn vẹn dữ liệu ở database**, và **vòng đời thay đổi thông qua entity owner**. Khi những ranh giới này rõ ràng, code Java có thể tổ chức thành những value object nhỏ, dễ tái sử dụng, trong khi schema quan hệ vẫn cụ thể, truy vấn được và vận hành ổn định.
