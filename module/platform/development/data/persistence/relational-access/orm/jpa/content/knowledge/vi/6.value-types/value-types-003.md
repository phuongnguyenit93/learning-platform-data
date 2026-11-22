# Nhúng nhiều lần cùng kiểu và dùng AttributeOverride trong JPA

Trong **Jakarta Persistence (JPA)**, không phải kiểu dữ liệu nào lưu xuống cơ sở dữ liệu cũng cần có một bảng và một định danh riêng. Nhiều giá trị thuộc về entity như địa chỉ, khoảng thời gian, thông số kích thước hoặc số tiền có thể được đóng gói thành **value type** bằng `@Embeddable`, sau đó được nhúng vào entity bằng `@Embedded`.

Vấn đề thường xuất hiện khi một entity có **hai hoặc nhiều thuộc tính cùng kiểu embeddable**, chẳng hạn đơn hàng có cả **địa chỉ thanh toán** và **địa chỉ giao hàng**. Hai thuộc tính Java đều dùng `Address`, nhưng dữ liệu của chúng cần nằm ở **các cột khác nhau** trong cùng bảng. `@AttributeOverride` và `@AttributeOverrides` cho phép xác định ánh xạ cột riêng cho từng vị trí nhúng.

Bài học tập trung vào cách một kiểu giá trị có thể được tái sử dụng, cách ánh xạ các thuộc tính lặp lại mà không bị trùng cột và những điểm cần lưu ý khi truy vấn, cập nhật hoặc thay đổi cấu trúc database.

## 1. Tại sao cần nhúng cùng một kiểu nhiều lần?

Giả sử hệ thống bán hàng có bảng `purchase_orders`, mỗi đơn hàng phải lưu hai địa chỉ:

- **Billing address:** địa chỉ dùng trên hóa đơn.
- **Shipping address:** địa chỉ nơi giao hàng.

Cả hai địa chỉ đều gồm đường, thành phố, mã bưu chính và mã quốc gia. Viết các thuộc tính phẳng trong entity sẽ dẫn tới việc nhân đôi mã:

~~~java
// Hình thức không dùng embeddable, chỉ để thấy sự lặp lại.
private String billingStreet;
private String billingCity;
private String billingPostalCode;
private String billingCountryCode;

private String shippingStreet;
private String shippingCity;
private String shippingPostalCode;
private String shippingCountryCode;
~~~

Mỗi địa chỉ là một **cụm giá trị có ý nghĩa nghiệp vụ**, vì vậy có thể gom thành một kiểu `Address`:

~~~text
                          PurchaseOrder
                         /             \
                        /               \
               billingAddress        shippingAddress
                   Address               Address
                   - street              - street
                   - city                - city
                   - postalCode          - postalCode
                   - countryCode         - countryCode
                        \               /
                         \             /
                  purchase_orders (một bảng)
                  billing_* và shipping_* columns
~~~

Entity giữ hai đối tượng `Address` khác nhau, nhưng cả hai được ánh xạ vào những nhóm cột thuộc **cùng một dòng** của `purchase_orders`.

Đây là **composition theo kiểu giá trị**:

- `PurchaseOrder` là entity, có `@Id` và vòng đời persistence.
- `Address` là embeddable, không có định danh entity độc lập.
- Một instance `Address` thường có ý nghĩa thông qua entity và vị trí chứa nó.
- Không tự sinh bảng `address` hoặc khóa ngoại `address_id` chỉ vì có `@Embedded`.

## 2. Định nghĩa một kiểu giá trị bằng @Embeddable

Tạo lớp `Address`:

~~~java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import java.util.Objects;

@Embeddable
public class Address {

    @Column(name = "street", length = 160, nullable = false)
    private String street;

    @Column(name = "city", length = 100, nullable = false)
    private String city;

    @Column(name = "postal_code", length = 20, nullable = false)
    private String postalCode;

    @Column(name = "country_code", length = 2, nullable = false)
    private String countryCode;

    protected Address() {
        // Constructor không tham số cho JPA.
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
        if (!(other instanceof Address that)) {
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
~~~

Các chi tiết cần hiểu:

| Khai báo | Chức năng |
| --- | --- |
| `@Embeddable` | Khai báo kiểu Java được nhúng như một thành phần giá trị của entity/embeddable khác |
| `@Column` | Khai báo mapping cột mặc định cho thuộc tính của kiểu giá trị |
| Constructor không tham số | Để JPA provider có thể tạo instance khi đọc dữ liệu |
| Không có `@Id` | `Address` không có entity identity riêng trong mô hình này |
| `equals()` và `hashCode()` theo trường | Diễn đạt ngữ nghĩa **value equality**: hai địa chỉ có cùng giá trị thì bằng nhau |

Ví dụ viết trên dùng **field access**, vì các annotation mapping được đặt trên trường. JPA truy cập những trường này khi cần materialize và theo dõi giá trị. Từ bên ngoài, API chỉ cung cấp getter và constructor; khi muốn sửa địa chỉ, ứng dụng có thể tạo một `Address` mới rồi thay toàn bộ value object.

Lưu ý: lớp ví dụ không dùng `final` cho các trường lưu trữ vì muốn giữ khả năng làm việc theo cách phổ biến, portable với JPA provider. “Value object” ở đây nói đến **vai trò miền nghiệp vụ**; không bắt buộc mọi embeddable phải là Java record hoặc bất biến tuyệt đối ở tầng triển khai.

## 3. Vì sao chỉ khai báo hai @Embedded là chưa đủ?

Giả sử entity có cấu trúc ban đầu:

~~~java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    private Long id;

    @Embedded
    private Address billingAddress;

    @Embedded
    private Address shippingAddress;
}
~~~

Ở mức Java, hai trường `billingAddress` và `shippingAddress` hoàn toàn khác nhau. Nhưng theo mapping của `Address`, mỗi instance đều có các thuộc tính `street`, `city`, `postalCode`, `countryCode` và các tên cột mặc định là:

~~~text
Address:
    street       -> street
    city         -> city
    postalCode   -> postal_code
    countryCode  -> country_code
~~~

Nếu cả hai vị trí nhúng đều dùng nguyên tên cột đó, provider có thể gặp **ánh xạ trùng cột** trong cùng bảng:

~~~text
billingAddress.street  ----\
                            >---- column street     (trùng)
shippingAddress.street ----/

billingAddress.city    ----\
                            >---- column city       (trùng)
shippingAddress.city   ----/
~~~

Một số ORM có chiến lược đặt tên mặc định theo đường dẫn thành phần để giảm đụng độ, nhưng không nên để kết quả ánh xạ phụ thuộc ngầm vào chiến lược riêng của provider. Với JPA portable và schema rõ ràng, **khai báo tên cột riêng bằng `@AttributeOverride`** tại từng nơi nhúng.

## 4. Dùng @AttributeOverrides cho từng vị trí nhúng

Khai báo đầy đủ `PurchaseOrder`:

~~~java
package com.example.shop.domain;

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

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(
            name = "street",
            column = @Column(
                name = "billing_street",
                length = 160,
                nullable = false
            )
        ),
        @AttributeOverride(
            name = "city",
            column = @Column(
                name = "billing_city",
                length = 100,
                nullable = false
            )
        ),
        @AttributeOverride(
            name = "postalCode",
            column = @Column(
                name = "billing_postal_code",
                length = 20,
                nullable = false
            )
        ),
        @AttributeOverride(
            name = "countryCode",
            column = @Column(
                name = "billing_country_code",
                length = 2,
                nullable = false
            )
        )
    })
    private Address billingAddress;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(
            name = "street",
            column = @Column(
                name = "shipping_street",
                length = 160,
                nullable = false
            )
        ),
        @AttributeOverride(
            name = "city",
            column = @Column(
                name = "shipping_city",
                length = 100,
                nullable = false
            )
        ),
        @AttributeOverride(
            name = "postalCode",
            column = @Column(
                name = "shipping_postal_code",
                length = 20,
                nullable = false
            )
        ),
        @AttributeOverride(
            name = "countryCode",
            column = @Column(
                name = "shipping_country_code",
                length = 2,
                nullable = false
            )
        )
    })
    private Address shippingAddress;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(
            Address billingAddress,
            Address shippingAddress) {
        this.billingAddress = billingAddress;
        this.shippingAddress = shippingAddress;
    }

    public Long getId() {
        return id;
    }

    public Address getBillingAddress() {
        return billingAddress;
    }

    public Address getShippingAddress() {
        return shippingAddress;
    }

    public void changeShippingAddress(Address newAddress) {
        this.shippingAddress = newAddress;
    }
}
~~~

Bây giờ cùng một kiểu `Address` được **nhúng hai lần**, nhưng mỗi lần nhúng được ánh xạ vào các cột riêng:

| Thuộc tính trong `Address` | Vị trí `billingAddress` | Vị trí `shippingAddress` |
| --- | --- | --- |
| `street` | `billing_street` | `shipping_street` |
| `city` | `billing_city` | `shipping_city` |
| `postalCode` | `billing_postal_code` | `shipping_postal_code` |
| `countryCode` | `billing_country_code` | `shipping_country_code` |

Lưu ý cú pháp:

- `@Embedded` đánh dấu vị trí nhúng một value type vào entity.
- `@AttributeOverride(name = "street", ...)` chọn **thuộc tính Java có tên `street`** bên trong `Address`.
- `column = @Column(name = "billing_street", ...)` chỉ định cột vật lý dùng riêng tại vị trí nhúng này.
- `@AttributeOverrides({ ... })` gom nhiều `@AttributeOverride`.
- Hai khối override độc lập vì chúng đặt trên **hai trường nhúng khác nhau**.

**Tên trong thuộc tính `name` là tên thuộc tính Java, không phải tên cột SQL.** Trong ví dụ, phải ghi `name = "postalCode"` chứ không phải `name = "postal_code"`. Tên SQL thuộc về `@Column(name = "...")`.

### 4.1. Không phải khai báo lại lớp Address

Chỉ có **một** định nghĩa `Address`. Không cần tạo hai lớp `BillingAddress` và `ShippingAddress` nếu chúng có cùng cấu trúc và quy tắc giá trị. Sự khác nhau về **vị trí lưu trữ** được thể hiện bằng metadata của entity chứa chúng.

Khi nào nên tách hai lớp? Khi billing address và shipping address thực sự có **khác biệt trong luật nghiệp vụ**, thuộc tính hay hành vi, không đơn thuần khác tiền tố cột. Khi đó tách kiểu có thể diễn đạt mô hình miền rõ hơn. `@AttributeOverride` giải quyết bài toán ánh xạ cột, không có nhiệm vụ che giấu các khác biệt nghiệp vụ quan trọng.

### 4.2. Chỉ ghi những override cần thiết?

Về cú pháp, `@AttributeOverride` có thể chỉ áp dụng cho một hoặc vài thuộc tính; các thuộc tính không override giữ mapping được khai báo trong embeddable hoặc mapping mặc định.

Tuy nhiên, nếu nhúng **hai lần** một embeddable vào **cùng bảng**, mỗi nhóm thuộc tính cần đi tới các cột không xung đột. Vì vậy trong ví dụ này chúng ta override **toàn bộ bốn thuộc tính ở cả hai vị trí** để kết quả trực quan và độc lập với quy tắc đặt tên ngầm của ORM.

## 5. Schema quan hệ tương ứng

Với PostgreSQL, bảng tương ứng có thể được chuẩn bị như sau:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,

    billing_street VARCHAR(160) NOT NULL,
    billing_city VARCHAR(100) NOT NULL,
    billing_postal_code VARCHAR(20) NOT NULL,
    billing_country_code VARCHAR(2) NOT NULL,

    shipping_street VARCHAR(160) NOT NULL,
    shipping_city VARCHAR(100) NOT NULL,
    shipping_postal_code VARCHAR(20) NOT NULL,
    shipping_country_code VARCHAR(2) NOT NULL
);
~~~

Một bản ghi cụ thể có thể được đọc theo hai nhóm:

~~~text
purchase_orders
+----+----------------------+--------------+---------------------+
| id | billing_city         | shipping_city| ...                 |
+----+----------------------+--------------+---------------------+
|  1 | Ho Chi Minh City     | Da Nang      | các cột còn lại    |
+----+----------------------+--------------+---------------------+
             |                     |
             v                     v
      billingAddress          shippingAddress
      Address(...)            Address(...)
~~~

Ở đây:

1. **Một dòng `purchase_orders`** ứng với một `PurchaseOrder` có ID.
2. Mỗi nhóm cột được dùng để tạo một **giá trị `Address`**.
3. Không tồn tại khóa chính cho từng địa chỉ.
4. Không cần bảng riêng hoặc foreign key từ đơn hàng tới bảng địa chỉ.

Khi dùng migration, việc đổi tên cột trong annotation không tự sửa database đã triển khai. Nếu trước đây bảng dùng tên khác, phải cập nhật migration/schema tương ứng. `@AttributeOverride` chỉ thay cách **ORM đọc và ghi một cột**; nó không phải lệnh chuyển dữ liệu.

## 6. Persist và đọc entity có hai embedded value

Đoạn code sau minh họa ứng dụng Java SE với persistence unit dùng kiểu giao dịch `RESOURCE_LOCAL`; giả định đã cấu hình JPA provider, DataSource/JDBC và schema đúng:

~~~java
Address billing = new Address(
    "12 Nguyen Trai",
    "Ho Chi Minh City",
    "700000",
    "VN"
);

Address shipping = new Address(
    "45 Hai Ba Trung",
    "Da Nang",
    "550000",
    "VN"
);

EntityManager em = emf.createEntityManager();
try {
    em.getTransaction().begin();

    PurchaseOrder order = new PurchaseOrder(billing, shipping);
    em.persist(order);

    em.getTransaction().commit();
} catch (RuntimeException ex) {
    if (em.getTransaction().isActive()) {
        em.getTransaction().rollback();
    }
    throw ex;
} finally {
    em.close();
}
~~~

Provider sử dụng metadata `@AttributeOverride` để tạo lệnh chèn dữ liệu vào đúng cột. SQL minh họa, thứ tự cột thực tế do provider quyết định:

~~~sql
INSERT INTO purchase_orders (
    billing_street,
    billing_city,
    billing_postal_code,
    billing_country_code,
    shipping_street,
    shipping_city,
    shipping_postal_code,
    shipping_country_code
) VALUES (
    '12 Nguyen Trai',
    'Ho Chi Minh City',
    '700000',
    'VN',
    '45 Hai Ba Trung',
    'Da Nang',
    '550000',
    'VN'
);
~~~

Với `GenerationType.IDENTITY`, khóa chính có thể được sinh tại thời điểm INSERT theo yêu cầu của cơ sở dữ liệu. Thời điểm SQL chạy không nhất thiết trùng chính xác với lệnh `em.persist()` trong tất cả provider.

Khi đọc lại:

~~~java
PurchaseOrder order = em.find(PurchaseOrder.class, 1L);

if (order != null) {
    String billingCity = order.getBillingAddress().getCity();
    String shippingCity = order.getShippingAddress().getCity();

    System.out.println(billingCity);
    System.out.println(shippingCity);
}
~~~

Kết quả hai giá trị `city` đến từ **hai cột khác nhau**, mặc dù hai getter đều thuộc class `Address`.

### 6.1. Cập nhật chỉ một embedded value

Bên trong transaction đang hoạt động:

~~~java
PurchaseOrder order = em.find(PurchaseOrder.class, 1L);

Address replacement = new Address(
    "99 Bach Dang",
    "Da Nang",
    "550000",
    "VN"
);

order.changeShippingAddress(replacement);

// Khi flush/commit, provider đồng bộ các thay đổi cần thiết
// của nhóm shipping_* trong cùng dòng purchase_orders.
~~~

Lệnh `changeShippingAddress` thay một kiểu giá trị trong managed entity. Không cần gọi `em.persist(replacement)` vì `Address` là **embeddable, không phải entity**.

Trong mô hình này, một địa chỉ không được quản lý như entity độc lập. Nếu muốn có kho địa chỉ dùng chung, cập nhật một địa chỉ tác động đến nhiều đối tượng cùng tham chiếu, hoặc truy vấn/định danh riêng từng địa chỉ, nên cân nhắc **Address entity với `@ManyToOne` hoặc `@OneToMany`** thay vì embeddable.

## 7. Truy vấn bằng đường dẫn thuộc tính Java

JPA Query Language (JPQL) làm việc với **tên entity và tên thuộc tính Java**, không dùng trực tiếp tên cột vật lý do `@AttributeOverride` khai báo.

Ví dụ tìm các đơn hàng có địa chỉ giao hàng ở Đà Nẵng:

~~~java
List<PurchaseOrder> orders = em.createQuery(
    """
    SELECT o
    FROM PurchaseOrder o
    WHERE o.shippingAddress.city = :city
    ORDER BY o.id
    """,
    PurchaseOrder.class
).setParameter("city", "Da Nang")
 .getResultList();
~~~

Biểu thức `o.shippingAddress.city` được provider ánh xạ sang cột `shipping_city`. Tương tự, `o.billingAddress.city` tương ứng `billing_city`:

~~~jpql
SELECT o
FROM PurchaseOrder o
WHERE o.billingAddress.countryCode = :country
  AND o.shippingAddress.countryCode = :country
~~~

Đường dẫn `billingAddress.countryCode` được xác định qua **tên property trong object model**, dù SQL có thể dùng tên `billing_country_code`.

Criteria API cũng truy cập thuộc tính theo đường dẫn:

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<PurchaseOrder> query =
    cb.createQuery(PurchaseOrder.class);

Root<PurchaseOrder> root = query.from(PurchaseOrder.class);

query.select(root)
     .where(cb.equal(
         root.get("shippingAddress").get("city"),
         "Da Nang"
     ));

List<PurchaseOrder> orders =
    em.createQuery(query).getResultList();
~~~

Nếu đã sinh JPA static metamodel, có thể dùng thuộc tính metamodel thay chuỗi để có thêm kiểm tra kiểu lúc biên dịch. Dù viết JPQL hay Criteria, phần SQL cụ thể vẫn do provider xây dựng từ metadata mapping.

## 8. Khi nhúng lồng nhau: dùng đường dẫn với dấu chấm

`@AttributeOverride` không chỉ áp dụng với thuộc tính trực tiếp. Nếu một embeddable chứa **một embeddable khác**, ta có thể override thuộc tính lồng nhau bằng **đường dẫn thuộc tính cách nhau bởi dấu chấm**.

Ví dụ biến thể độc lập của `Address`, có thêm tọa độ:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

@Embeddable
public class GeoPoint {
    @Column(precision = 10, scale = 7)
    private java.math.BigDecimal latitude;

    @Column(precision = 10, scale = 7)
    private java.math.BigDecimal longitude;

    protected GeoPoint() {
    }

    public GeoPoint(
            java.math.BigDecimal latitude,
            java.math.BigDecimal longitude) {
        this.latitude = latitude;
        this.longitude = longitude;
    }
}
~~~

Giả sử khai báo thêm trong `Address`:

~~~java
@Embedded
private GeoPoint location;
~~~

Khi đó, ở entity chứa `billingAddress`, có thể viết thêm hai override vào cùng khối `@AttributeOverrides`:

~~~java
@AttributeOverride(
    name = "location.latitude",
    column = @Column(
        name = "billing_latitude",
        precision = 10,
        scale = 7
    )
),
@AttributeOverride(
    name = "location.longitude",
    column = @Column(
        name = "billing_longitude",
        precision = 10,
        scale = 7
    )
)
~~~

Ở `shippingAddress`, dùng đúng đường dẫn Java nhưng đổi tên cột:

~~~java
@AttributeOverride(
    name = "location.latitude",
    column = @Column(
        name = "shipping_latitude",
        precision = 10,
        scale = 7
    )
),
@AttributeOverride(
    name = "location.longitude",
    column = @Column(
        name = "shipping_longitude",
        precision = 10,
        scale = 7
    )
)
~~~

Các đoạn trên là phần **bổ sung vào ví dụ trước**, không phải một phiên bản hoàn chỉnh thay thế class `Address` ở mục 2. Nếu bổ sung `location` vào model thực tế, cần khai báo thêm `@Embedded`, constructor/getter phù hợp và các cột tọa độ trong schema.

Đường dẫn được diễn giải như sau:

~~~text
billingAddress              (property của PurchaseOrder)
  -> location               (property @Embedded của Address)
      -> latitude           (property của GeoPoint)

@AttributeOverride(name = "location.latitude", ...)
                              |
                              v
                     billing_latitude
~~~

Khi đặt `@AttributeOverride` **trên chính thuộc tính `billingAddress`**, đường dẫn bắt đầu **bên trong kiểu Address**, do đó ghi `"location.latitude"`. Nếu đặt override ở cấp **entity class**, đường dẫn phải bao gồm tên thuộc tính nhúng của entity, ví dụ `"billingAddress.location.latitude"`.

Điểm quan trọng: dấu chấm phân tách **tên thuộc tính Java lồng nhau**, không phải schema/table của SQL.

## 9. Đặt override trên thuộc tính hay trên class?

Thông thường, đặt overrides ngay tại **thuộc tính `@Embedded`** dễ nhìn vì mỗi nhóm ánh xạ nằm bên cạnh nơi sử dụng. JPA cũng hỗ trợ khai báo override ở cấp entity class bằng đường dẫn đầy đủ.

Ví dụ ngắn:

~~~java
@Entity
@Table(name = "customer_profiles")
@AttributeOverrides({
    @AttributeOverride(
        name = "homeAddress.city",
        column = @Column(name = "home_city")
    ),
    @AttributeOverride(
        name = "workAddress.city",
        column = @Column(name = "work_city")
    )
})
public class CustomerProfile {

    @Id
    private Long id;

    @Embedded
    private Address homeAddress;

    @Embedded
    private Address workAddress;

    // Những thuộc tính còn lại phải được ánh xạ phù hợp.
}
~~~

Ví dụ này chỉ cho thấy **cú pháp đường dẫn ở cấp class**; nếu dùng nguyên lớp `Address` trong mục 2 và nhúng hai lần, cần tiếp tục override các thuộc tính khác để tránh trùng cột. Không coi đây là mapping đầy đủ cho bảng `customer_profiles`.

So sánh:

| Vị trí khai báo | Giá trị `name` | Cách hiểu |
| --- | --- | --- |
| Trên field `billingAddress` | `"city"` | Thuộc tính `city` bên trong `Address` |
| Trên class `PurchaseOrder` | `"billingAddress.city"` | Từ entity đi qua field `billingAddress` rồi tới `city` |
| Trên field `billingAddress` với embedded lồng nhau | `"location.latitude"` | Từ `Address` qua `location` tới `latitude` |
| Trên class `PurchaseOrder` với embedded lồng nhau | `"billingAddress.location.latitude"` | Đường dẫn đầy đủ tính từ entity |

Tránh khai báo nhiều override mâu thuẫn cho cùng một mapping tại các vị trí khác nhau; chọn một phong cách rõ ràng cho mỗi entity.

## 10. @AttributeOverride không thay thế @AssociationOverride

`@AttributeOverride` dùng để thay đổi **mapping cột của thuộc tính cơ bản** hoặc thuộc tính cơ bản nằm sâu trong embedded value. Nếu một embeddable chứa **quan hệ tới entity khác** bằng `@ManyToOne` hoặc `@OneToOne`, việc thay đổi cột join cần dùng **`@AssociationOverride`**.

Ví dụ tách biệt:

~~~java
@Embeddable
public class ContactLocation {
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "country_id")
    private Country country;

    protected ContactLocation() {
    }
}
~~~

Nếu một entity nhúng `ContactLocation` tại hai vị trí, mỗi vị trí muốn có khóa ngoại riêng:

~~~java
@Embedded
@AssociationOverride(
    name = "country",
    joinColumns = @JoinColumn(name = "billing_country_id")
)
private ContactLocation billingLocation;

@Embedded
@AssociationOverride(
    name = "country",
    joinColumns = @JoinColumn(name = "shipping_country_id")
)
private ContactLocation shippingLocation;
~~~

Trong trường hợp này, `Country` là một entity có định danh, còn `ContactLocation` là embeddable. `billing_country_id` và `shipping_country_id` là các **foreign-key column** do quan hệ entity sử dụng.

| Nhu cầu | Annotation phù hợp |
| --- | --- |
| Đổi tên cột `Address.city` | `@AttributeOverride` + `@Column` |
| Đổi tên cột lồng `Address.location.latitude` | `@AttributeOverride` với `name` dạng đường dẫn |
| Đổi cột join cho `ContactLocation.country` | `@AssociationOverride` + `@JoinColumn` |
| Đổi tên bảng cho entity `Country` | Xem mapping `@Table` của entity, không dùng `@AttributeOverride` |

## 11. Mức độ ưu tiên giữa mapping mặc định và override

Giả sử `Address` có:

~~~java
@Column(name = "postal_code", length = 20, nullable = false)
private String postalCode;
~~~

Tại vị trí nhúng:

~~~java
@AttributeOverride(
    name = "postalCode",
    column = @Column(
        name = "shipping_zip",
        length = 16,
        nullable = false
    )
)
~~~

Ánh xạ áp dụng cho trường này tại `shippingAddress` sử dụng tên cột `shipping_zip` và thông số được khai báo ở `@Column` mới. Một vị trí nhúng khác không override `postalCode` sẽ vẫn sử dụng mapping từ `Address` (hoặc cơ chế mặc định theo provider nếu không có annotation cột).

**Không nên giả định chỉ có thuộc tính `name` trong `@Column` được thay đổi còn mọi tùy chọn khác tự động kế thừa như mong muốn.** Khi override cột, hãy nêu rõ những thuộc tính quan trọng cho schema như `nullable`, `length`, `precision`, `scale`, khả năng insert/update nếu mô hình yêu cầu.

Điều này quan trọng nếu cùng một kiểu embeddable được dùng ở các bảng hoặc ngữ cảnh khác nhau, mỗi vị trí có độ dài cột hay ràng buộc riêng. Khi có khác biệt về ý nghĩa nghiệp vụ quá lớn, cân nhắc tách thành các kiểu value object khác nhau.

## 12. Null, validation và việc thay thế embedded value

### 12.1. Embedded object có thể null không?

`@Embedded` tự nó không khai báo thuộc tính `optional` tương đương với `@ManyToOne(optional = ...)`. Nếu một địa chỉ là bắt buộc, hãy thiết kế invariant ở tầng nghiệp vụ, dùng validation phù hợp và đặt ràng buộc cột khi cần.

Ví dụ:

~~~java
@Embedded
@jakarta.validation.Valid
@jakarta.validation.constraints.NotNull
private Address shippingAddress;
~~~

Với Bean Validation, `@NotNull` kiểm tra bản thân reference và `@Valid` cho phép kiểm tra các ràng buộc khai báo trên những thành phần bên trong `Address`. Đây là một lớp kiểm tra **bổ sung**, không thay cho các `NOT NULL` constraint của database khi cần bảo đảm tính toàn vẹn.

Nếu tất cả cột của một embedded value đều `NULL`, cách provider materialize giá trị nhúng có thể cần được cân nhắc khi thiết kế và kiểm thử: có provider trả về `null` thay cho instance chứa toàn bộ thuộc tính `null`. Tránh dựa vào “embedded object luôn được tạo” nếu nhóm cột có thể cùng null.

### 12.2. Hai vị trí nhúng có độc lập hoàn toàn không?

Trong cùng một order, `billingAddress` và `shippingAddress` là **hai thuộc tính khác nhau** có thể chứa hai value object khác nhau. Chúng dùng chung **kiểu Java**, không dùng chung **cột database**.

Không nên xây dựng nghiệp vụ dựa vào việc hai thuộc tính có giữ cùng reference Java trong mọi trường hợp hay không. Nếu value object có thể thay đổi trạng thái, dùng chung reference rồi sửa trực tiếp có thể tạo tác dụng phụ khó hiểu. Cách dùng an toàn thường là tạo value object mới và gán riêng vào trường cần thay đổi.

### 12.3. Thay thế đối tượng và cập nhật cột

Với entity đang managed:

~~~java
PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
order.changeShippingAddress(
    new Address("18 Le Loi", "Hue", "530000", "VN")
);
~~~

Provider theo dõi sự thay đổi của managed entity và có thể cập nhật những cột tương ứng khi flush/commit. SQL thực tế có thể cập nhật một số hoặc toàn bộ cột của dòng tùy provider, cấu hình và dirty checking; không nên khẳng định mọi provider chỉ cập nhật đúng một cột đã đổi.

Không gọi `em.merge(address)`, `em.persist(address)` hay `em.remove(address)` với `Address` vì embeddable không phải entity độc lập.

## 13. Các lỗi điển hình khi nhúng nhiều lần

| Dấu hiệu | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| ORM báo cột lặp lại hoặc duplicated column mapping | Hai embedded instances cùng ánh xạ vào `street`, `city`… | Khai báo `@AttributeOverrides` để mỗi vị trí dùng cột riêng |
| Bảng có `billing_city` và `shipping_city` nhưng query gặp missing column | Mapping đang trỏ tới tên cũ hoặc tên do naming strategy sinh ra | Kiểm tra `@AttributeOverride`, schema và migration |
| Override không có hiệu lực | `name` dùng tên cột SQL thay vì tên thuộc tính Java | Đổi thành `name="postalCode"`, không dùng `"postal_code"` |
| Đọc giá trị billing nhưng lại có dữ liệu shipping | Hai nơi vô tình trỏ chung cột | Tách tên cột trên từng `@Embedded` |
| Bổ sung trường mới vào `Address` và startup thất bại | Trường mới chưa được ánh xạ riêng cho hai nơi nhúng | Bổ sung override và migration cho các cột mới |
| Dùng `@AttributeOverride` cho quan hệ `@ManyToOne` | Sai loại mapping | Dùng `@AssociationOverride` / `@JoinColumn` |
| Null address gây lỗi khi truy cập getter | Nhóm cột null hoặc dữ liệu chưa bảo đảm invariant | Kiểm tra validation, ràng buộc DB và cách xử lý null |
| Sửa địa chỉ mà không ghi xuống DB | Entity detached hoặc thao tác ngoài transaction phù hợp | Truy xuất entity managed và thực hiện thay đổi trong transaction |
| Thêm override nhưng schema không đổi | Annotation không tự áp dụng migration ở database đã triển khai | Chạy migration riêng để tạo/đổi tên cột |
| Truy vấn JPQL viết `o.shipping_city` | Nhầm thuộc tính Java với tên cột SQL | Dùng `o.shippingAddress.city` |

## 14. Tình huống mở rộng: nhúng ba lần cùng kiểu

Giả sử cần thêm **địa chỉ trả hàng** (`returnAddress`) cho đơn hàng. Không cần tạo lớp `ReturnAddress` nếu cấu trúc và ngữ nghĩa vẫn giống `Address`.

~~~java
@Embedded
@AttributeOverrides({
    @AttributeOverride(
        name = "street",
        column = @Column(
            name = "return_street",
            length = 160,
            nullable = false
        )
    ),
    @AttributeOverride(
        name = "city",
        column = @Column(
            name = "return_city",
            length = 100,
            nullable = false
        )
    ),
    @AttributeOverride(
        name = "postalCode",
        column = @Column(
            name = "return_postal_code",
            length = 20,
            nullable = false
        )
    ),
    @AttributeOverride(
        name = "countryCode",
        column = @Column(
            name = "return_country_code",
            length = 2,
            nullable = false
        )
    )
})
private Address returnAddress;
~~~

Đoạn trên là trường **bổ sung vào class `PurchaseOrder`** cùng constructor/accessor tương ứng khi cần. Phía database phải có thêm bốn cột `return_*` tương ứng.

Như vậy, **một kiểu value object** có thể được dùng ba lần trong một entity, mỗi lần có **một nhóm cột độc lập**:

~~~text
purchase_orders
|
+-- billing_street, billing_city, billing_postal_code, billing_country_code
|          ^
|          |
|      billingAddress: Address
|
+-- shipping_street, shipping_city, shipping_postal_code, shipping_country_code
|          ^
|          |
|      shippingAddress: Address
|
+-- return_street, return_city, return_postal_code, return_country_code
           ^
           |
       returnAddress: Address
~~~

Nếu về sau thêm thuộc tính `district` vào `Address`, cần xem xét cả ba nơi nhúng. Việc tái sử dụng kiểu giúp giảm lặp code Java, nhưng **schema ánh xạ vẫn phải đầy đủ tại mỗi vị trí**.

## 15. Bài tập nhận diện mapping

### Bài 1: Kiểm tra tên cột

Một entity có:

~~~java
@Embedded
@AttributeOverride(
    name = "city",
    column = @Column(name = "office_city")
)
private Address officeAddress;
~~~

**Câu hỏi:** JPQL truy cập thành phố văn phòng thế nào?

**Trả lời:** `o.officeAddress.city` nếu alias entity là `o`. Tên `office_city` chỉ được sử dụng ở cấp SQL/mapping vật lý. Nếu entity còn các field nhúng `Address` khác, các cột còn lại cũng cần ánh xạ nhất quán để tránh xung đột.

### Bài 2: Phân biệt attribute và column

~~~java
@AttributeOverride(
    name = "postal_code",
    column = @Column(name = "shipping_postal_code")
)
~~~

**Câu hỏi:** Vì sao đoạn này sai với class `Address` của bài?

**Trả lời:** Thuộc tính Java tên `postalCode`, không phải `postal_code`. Cần ghi `name = "postalCode"`. Đầu `name` của `@Column` mới chứa tên cột vật lý.

### Bài 3: Có hai bảng địa chỉ không?

Entity có hai trường `@Embedded Address`, một cho thanh toán và một cho giao hàng.

**Trả lời:** Không tự có hai bảng. Với mapping trong bài, cả hai đều nằm trong bảng `purchase_orders`, ở các nhóm cột khác nhau. Muốn địa chỉ có ID và bảng độc lập thì cần thiết kế entity/quan hệ khác.

### Bài 4: Override thuộc tính lồng nhau

Nếu `Address` chứa `@Embedded GeoPoint location`, vậy khi đặt annotation ngay trên `billingAddress`, tên nào dùng để override latitude?

**Trả lời:** `name = "location.latitude"`. Nếu đặt override ở class entity, dùng đường dẫn `"billingAddress.location.latitude"`.

### Bài 5: Thay đổi shippingAddress

Một managed `PurchaseOrder` gọi `changeShippingAddress(new Address(...))` trong transaction.

**Trả lời:** JPA có thể phát hiện thay đổi và đồng bộ sang nhóm cột `shipping_*` khi flush/commit. `Address` không cần và không thể được xử lý như entity riêng bằng `persist()`.

## 16. Ghi nhớ

- `@Embeddable` tạo **kiểu giá trị tái sử dụng**; `@Embedded` đặt kiểu giá trị đó vào một vị trí thuộc entity.
- Một entity được phép nhúng **cùng một kiểu nhiều lần**, ví dụ `billingAddress` và `shippingAddress`.
- Vì các thành phần nhúng nằm **trong bảng của entity sở hữu**, nhiều lần nhúng cùng kiểu có thể làm tên cột bị trùng.
- `@AttributeOverride` xác định cột riêng cho **một thuộc tính Java** tại một vị trí nhúng; `@AttributeOverrides` gom nhiều override.
- `name` tham chiếu **tên thuộc tính hoặc đường dẫn thuộc tính Java** như `"postalCode"`, `"location.latitude"`; `@Column(name = ...)` mới tham chiếu tên cột vật lý.
- Khi embeddable chứa quan hệ entity và cần thay tên cột join, dùng `@AssociationOverride`.
- Entity vẫn nắm **ID, transaction và persistence lifecycle**. Các địa chỉ nhúng là những value object được lưu cùng dòng, không có vòng đời entity riêng.

Ý tưởng thiết kế cần giữ là: **tái sử dụng cấu trúc và hành vi của value object trong Java, đồng thời ánh xạ tường minh từng lần sử dụng sang nhóm cột độc lập trong database**. `@AttributeOverride` chính là công cụ để thực hiện sự phân biệt đó.
